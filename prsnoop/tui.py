"""prsnoop tui: a full-screen live dashboard in the terminal.

htop-for-GitHub: tabbed views (overview, pull requests, issues, languages),
keyboard navigation, live refresh with the shared ETag cache, and a status
bar. Built on the stdlib curses module, so still zero dependencies.
Keys: 1-4 tabs, j/k or arrows scroll, r refetch, q quit.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import curses

from prsnoop.fetch import fetch_user_activity
from prsnoop.github import GitHubClient
from prsnoop.models import Activity
from prsnoop.score import compute_score
from prsnoop.stats import build_activity

TAB_NAMES = ["overview", "pull requests", "issues", "languages"]


def _fmt(n: int) -> str:
    return f"{n:,}"


class TuiState:
    """Everything the render loop needs between frames."""

    def __init__(self, user: str) -> None:
        self.user = user
        self.activity: Activity | None = None
        self.tab = 0
        self.scroll = 0
        self.error: str | None = None
        self.last_refresh = ""
        self.status = "loading..."


def _fetch(state: TuiState, client: GitHubClient, days: int, org: str | None) -> None:
    try:
        prs, reviews, issues, _ = fetch_user_activity(
            client, state.user, days=days, include_reviews=True, org=org)
        state.activity = build_activity(
            state.user, prs, reviews, issues, window_days=days)
        state.error = None
        state.status = "live"
        state.last_refresh = time.strftime("%H:%M:%S")
    except Exception as exc:  # noqa: BLE001  show the error in the TUI
        state.error = str(exc)[:70]
        state.status = "error"


def _overview_lines(state: TuiState, height: int) -> list[str]:
    assert state.activity is not None
    s = state.activity.stats
    hs = compute_score(state.activity)
    momentum = s.momentum or "no data"
    lines = [
        f"  user          {s.user}",
        f"  window        last {s.window_days} days",
        "",
        f"  health score  {hs.total:.1f}/100  grade {hs.grade} ({hs.band})",
        f"  burnout risk  {hs.burnout_risk}",
        "",
        f"  pull requests {s.prs_authored:>6}   merged {s.prs_merged:>5}   "
        f"open {s.prs_open:>4}",
        f"  merge rate    {s.merge_rate * 100:>5.0f}%   median merge "
        f"{s.median_days_to_merge or 0:>5.1f}d",
        f"  lines         +{_fmt(s.lines_added):>9}  -{_fmt(s.lines_deleted):>9}",
        f"  reviews       {s.reviews_given:>6}   issues {s.issues_opened:>5}   "
        f"closed {s.issues_closed:>4}",
        f"  active days   {s.active_days:>6}   streak {s.longest_streak_days:>5}d   "
        f"momentum {momentum}",
        "",
        "  top repositories",
    ]
    for repo, n in s.top_repos[:8]:
        lines.append(f"    {repo:<34} {n:>4}")
    return lines


def _pr_lines(state: TuiState) -> list[str]:
    assert state.activity is not None
    lines = []
    order = {"open": 0, "merged": 1, "closed": 2}
    prs = sorted(state.activity.prs, key=lambda p: (order.get(p.state, 3), -p.number))
    for p in prs:
        flag = {"open": "O", "merged": "M", "closed": "C"}.get(p.state, "?")
        lines.append(
            f"  [{flag}] {p.repo}#{p.number:<5} {p.title[:52]:<52} "
            f"+{p.additions:<6} -{p.deletions:<6}"
        )
    return lines or ["  (no pull requests in this window)"]


def _issue_lines(state: TuiState) -> list[str]:
    assert state.activity is not None
    lines = []
    for i in state.activity.issues:
        state_mark = "open" if i.state == "OPEN" else "closed"
        lines.append(
            f"  {i.repo}#{i.number:<5} {i.title[:56]:<56} {state_mark}"
        )
    return lines or ["  (no issues in this window)"]


def _lang_lines(state: TuiState) -> list[str]:
    assert state.activity is not None
    s = state.activity.stats
    peak = s.languages[0][1] if s.languages else 1
    lines = []
    for lang, n in s.languages:
        bar = "#" * max(1, int(n / peak * 30))
        lines.append(f"  {lang:<18} {bar:<32} {n}")
    return lines or ["  (no language data)"]


def _draw(stdscr: curses.window, state: TuiState) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_GREEN, -1)
    curses.init_pair(2, curses.COLOR_RED, -1)
    curses.init_pair(3, curses.COLOR_CYAN, -1)
    curses.init_pair(4, curses.COLOR_YELLOW, -1)

    # header
    title = f" prsnoop tui | {state.user} "
    stdscr.attron(curses.color_pair(3) | curses.A_BOLD)
    stdscr.addstr(0, 0, title.ljust(width)[: width - 1])
    stdscr.attroff(curses.color_pair(3) | curses.A_BOLD)

    # tabs
    tabs = ""
    for k, name in enumerate(TAB_NAMES):
        mark = f" {k + 1} {name} "
        if k == state.tab:
            tabs += f"[{mark.strip()}]"
        else:
            tabs += f" {mark.strip()} "
    stdscr.addstr(1, 0, tabs.ljust(width)[: width - 1])

    # body
    body: list[str] = []
    if state.error and state.activity is None:
        body = [f"  error: {state.error}", "", "  press r to retry, q to quit"]
    elif state.activity is not None:
        if state.tab == 0:
            body = _overview_lines(state, height)
        elif state.tab == 1:
            body = _pr_lines(state)
        elif state.tab == 2:
            body = _issue_lines(state)
        else:
            body = _lang_lines(state)
    max_rows = max(1, height - 4)
    state.scroll = max(0, min(state.scroll, max(0, len(body) - max_rows)))
    for row, line in enumerate(body[state.scroll: state.scroll + max_rows]):
        color = 0
        if line.strip().startswith("[M]"):
            color = curses.color_pair(1)
        elif line.strip().startswith("[C]"):
            color = curses.color_pair(2)
        stdscr.addstr(2 + row, 0, line[: width - 1], color)

    # status bar
    parts = [f" {state.status}"]
    if state.activity is not None:
        s = state.activity.stats
        parts.append(
            f"prs {s.prs_authored} · merged {s.prs_merged} · rate "
            f"{s.merge_rate * 100:.0f}% · streak {s.longest_streak_days}d")
    parts.append(f"refreshed {state.last_refresh}")
    parts.append("1-4 tabs · j/k scroll · r refresh · q quit ")
    status = "  ·  ".join(parts)
    stdscr.attron(curses.color_pair(4))
    stdscr.addstr(height - 1, 0, status.ljust(width)[: width - 1])
    stdscr.attroff(curses.color_pair(4))
    stdscr.refresh()


def run_tui(
    user: str,
    days: int = 30,
    org: str | None = None,
    cache_dir: Path | None = None,
    refresh_seconds: int = 300,
) -> None:
    """Blocking curses loop. Returns when the user presses q.

    curses is imported lazily: Windows ships no curses module, so the
    command must fail with a clear message instead of an import error.
    """
    try:
        import curses
    except ImportError as exc:  # pragma: no cover - platform specific
        raise SystemExit(
            "prsnoop tui: the curses module is not available on this platform. "
            "On Windows, use 'prsnoop serve' for the browser dashboard instead."
        ) from exc

    def _loop(stdscr: curses.window) -> None:
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.keypad(True)
        state = TuiState(user)
        client = GitHubClient(cache_dir=cache_dir, user_agent="prsnoop-tui")
        last_fetch = 0.0
        while True:
            now = time.monotonic()
            if now - last_fetch > refresh_seconds or state.activity is None:
                _fetch(state, client, days, org)
                last_fetch = now
            _draw(stdscr, state)
            key = stdscr.getch()
            if key in (ord("q"), ord("Q")):
                return
            elif key in (ord("1"),):
                state.tab, state.scroll = 0, 0
            elif key in (ord("2"),):
                state.tab, state.scroll = 1, 0
            elif key in (ord("3"),):
                state.tab, state.scroll = 2, 0
            elif key in (ord("4"),):
                state.tab, state.scroll = 3, 0
            elif key in (curses.KEY_DOWN, ord("j")):
                state.scroll += 1
            elif key in (curses.KEY_UP, ord("k")):
                state.scroll = max(0, state.scroll - 1)
            elif key in (curses.KEY_NPAGE,):
                state.scroll += 10
            elif key in (curses.KEY_PPAGE,):
                state.scroll = max(0, state.scroll - 10)
            elif key in (ord("r"), ord("R")):
                last_fetch = 0.0
            time.sleep(0.15)

    curses.wrapper(_loop)
