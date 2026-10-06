"""Live terminal watch: the report as a dashboard, not a document.

The frame is a pure function so it is testable without a TTY: given an
Activity it returns the exact ANSI-styled screen the loop prints. The
loop itself refetches every N seconds (the shared ETag cache keeps this
cheap), clears the terminal, redraws, and rings the bell when new pull
requests appear since the previous tick.
"""

from __future__ import annotations

from datetime import datetime, timezone

from prsnoop.ansi import bold, cyan, dim, green, red, yellow
from prsnoop.models import Activity

CLEAR = "\x1b[2J\x1b[H"
BELL = "\a"

_PR_LEVELS = " .:;+=xX#"


def _plain(text: str, enabled: bool = True) -> str:
    return text


def _spark(days: list[tuple[str, int]], width: int = 40) -> str:
    """One-line activity chart over the last ``width`` active-or-not days."""
    if not days:
        return ""
    tail = days[-width:]
    peak = max(n for _, n in tail) or 1
    return "".join(_PR_LEVELS[min(7, int(n / peak * 7.999))] for _, n in tail)


def _age(created: datetime, now: datetime) -> str:
    days = (now - created).total_seconds() / 86400.0 * 10
    return f"{days:.1f}d" if days >= 0 else "now"


def pr_keys(activity: Activity) -> set[str]:
    """Stable identities of this snapshot's PRs, for tick-to-tick diffing."""
    return {f"{p.repo}#{p.number}" for p in activity.prs}


def diff_keys(previous: set[str] | None, current: set[str]) -> tuple[set[str], set[str]]:
    """(new, gone) identities between two ticks."""
    if previous is None:
        return set(), set()
    return current - previous, previous - current


def render_frame(
    activity: Activity,
    *,
    color: bool = True,
    new_keys: set[str] | None = None,
    tick: int = 1,
) -> str:
    """The full watch screen: header, stats, chart, queue, footer."""
    s = activity.stats
    now = activity.generated_at
    window = f"{s.since} to {s.until}" if s.since else f"last {s.window_days} days"
    days = [(da.date, da.total) for da in s.day_activity]

    state_color = {"merged": green, "open": yellow, "closed": red}

    lines = [
        CLEAR + bold(cyan(f"prsnoop watch | {activity.user}", color), color),
        dim(f"  {window} · tick {tick} · ctrl-c to stop", color),
        "",
        f"  prs {bold(str(s.prs_authored), color)}"
        f"  merged {green(str(s.prs_merged), color)}"
        f"  rate {bold(f'{s.merge_rate * 100:.0f}%', color)}"
        f"  reviews {str(s.reviews_given)}"
        f"  issues {str(s.issues_opened)}"
        f"  streak {bold(f'{s.current_streak_days}d', color)}",
        f"  {_spark(days)}",
        "",
    ]
    if s.momentum:
        lines.append(
            f"  momentum {bold(s.momentum, color)}"
            + (f" ({s.momentum_pct:+.0f}%)" if s.momentum_pct is not None else "")
            + dim(" · second half vs first half", color)
        )
        lines.append("")

    lines.append(bold("  queue", color))
    shown = sorted(
        activity.prs,
        key=lambda p: (p.state != "open", -(p.number)),
    )[:8]
    for p in shown:
        state = p.state
        paint = state_color.get(state, _plain)
        age = _age(p.created_at, now)
        title = " ".join(p.title.split())[:44]
        key = f"{p.repo}#{p.number}"
        is_new = new_keys is not None and key in new_keys
        flag = yellow(" new", color) if is_new else ""
        lines.append(f"  #{p.number:<5} {paint(state, color):<8} {age:>5}  {title}{flag}")
    if not shown:
        lines.append(dim("  no pull requests in this window", color))

    lines += [
        "",
        dim(
            f"  updated {now.astimezone(timezone.utc).strftime('%H:%M:%S')}"
            f" UTC · {s.active_days} active days",
            color,
        ),
    ]
    return "\n".join(lines)
