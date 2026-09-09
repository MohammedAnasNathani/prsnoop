"""Shareable SVG stat card: a contributor scoreboard for READMEs.

One self-contained SVG per user and window, built by hand with the same
zero-dependency approach as the badges. Drop it into a profile README,
pin it, or screenshot it; no hosting service and no external requests,
so it renders anywhere GitHub renders markdown.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from xml.sax.saxutils import escape as xml_escape

from prsnoop.models import Activity

THEMES: dict[str, dict[str, str]] = {
    "dark": {
        "bg": "#0d1117",
        "border": "#30363d",
        "text": "#e6edf3",
        "dim": "#8b949e",
        "accent": "#58a6ff",
        "green": "#3fb950",
        "avatar_text": "#0d1117",
        "grid": "#21262d",
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d1d9e0",
        "text": "#1f2328",
        "dim": "#59636e",
        "accent": "#0969da",
        "green": "#1a7f37",
        "avatar_text": "#ffffff",
        "grid": "#eaeef2",
    },
}

_SANS = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"
_MONO = "SFMono-Regular,Menlo,Consolas,Liberation Mono,monospace"

_W, _H = 640, 340
_PAD = 32


def _dense_series(activity: Activity) -> list[int]:
    """Daily totals for every day of the window, gaps included."""
    totals = {da.date: da.total for da in activity.stats.day_activity}
    try:
        start = (
            datetime.strptime(activity.stats.since, "%Y-%m-%d").date()
            if activity.stats.since
            else activity.generated_at.date() - timedelta(days=activity.stats.window_days)
        )
        end = (
            datetime.strptime(activity.stats.until, "%Y-%m-%d").date()
            if activity.stats.until
            else activity.generated_at.date()
        )
    except ValueError:
        return []
    out: list[int] = []
    cursor = start
    while cursor <= end:
        out.append(totals.get(cursor.isoformat(), 0))
        cursor += timedelta(days=1)
    return out


def _sparkline(values: list[int], theme: dict[str, str]) -> str:
    """Area + line chart of the window, GitHub-graph vibes."""
    x0, x1 = _PAD, _W - _PAD
    top, base = 196, 278
    w = x1 - x0
    if len(values) < 2:
        return (
            f"<line x1='{x0}' y1='{base}' x2='{x1}' y2='{base}'"
            f" stroke='{theme['grid']}' stroke-width='2'/>"
        )
    peak = max(values) or 1
    step = w / (len(values) - 1)
    pts = [
        f"{x0 + i * step:.1f},{base - v / peak * (base - top):.1f}"
        for i, v in enumerate(values)
    ]
    area = f"{x0},{base} " + " ".join(pts) + f" {x1},{base}"
    return (
        f"<polygon points='{area}' fill='{theme['accent']}' opacity='0.12'/>"
        f"<polyline points='{' '.join(pts)}' fill='none'"
        f" stroke='{theme['accent']}' stroke-width='2'"
        f" stroke-linejoin='round' stroke-linecap='round'/>"
        f"<line x1='{x0}' y1='{base}' x2='{x1}' y2='{base}'"
        f" stroke='{theme['grid']}' stroke-width='1'/>"
    )


def _stat_col(x: float, label: str, value: str, color: str, theme: dict[str, str]) -> str:
    return (
        f"<text x='{x:.1f}' y='134' font-family='{_SANS}' font-size='10'"
        f" letter-spacing='1.5' fill='{theme['dim']}'>"
        f"{xml_escape(label.upper())}</text>"
        f"<text x='{x:.1f}' y='168' font-family='{_MONO}' font-weight='bold'"
        f" font-size='28' fill='{color}'>{xml_escape(value)}</text>"
    )


def render_card(activity: Activity, theme: str = "dark") -> str:
    """One 640x340 SVG scoreboard for the given activity snapshot."""
    t = THEMES.get(theme, THEMES["dark"])
    s = activity.stats
    user = xml_escape(activity.user)
    window = f"{s.since} to {s.until}" if s.since else f"last {s.window_days} days"
    subtitle = f"{window} · {s.distinct_repos} repos"
    if s.languages:
        subtitle += f" · mostly {xml_escape(str(s.languages[0][0]))}"

    rate = f"{s.merge_rate * 100:.0f}%"
    streak = f"{s.current_streak_days or s.longest_streak_days}d"

    top_repos = (
        " · ".join(f"{repo} ({n})" for repo, n in s.top_repos[:2]) or "no repositories yet"
    )

    cols = [
        (_PAD, "prs", str(s.prs_authored), t["text"]),
        (_PAD + 115.2, "merged", str(s.prs_merged), t["green"]),
        (_PAD + 230.4, "merge rate", rate, t["text"]),
        (_PAD + 345.6, "reviews", str(s.reviews_given), t["text"]),
        (_PAD + 460.8, "streak", streak, t["accent"]),
    ]
    cells = "".join(_stat_col(x, lb, v, c, t) for x, lb, v, c in cols)

    initial = xml_escape((activity.user[:1] or "?").upper())

    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{_W}' height='{_H}'"
        f" viewBox='0 0 {_W} {_H}' role='img'"
        f" aria-label='prsnoop card for {user}'>"
        f"<title>prsnoop: {user}, {window}</title>"
        f"<rect width='{_W}' height='{_H}' rx='16' fill='{t['bg']}'"
        f" stroke='{t['border']}'/>"
        f"<circle cx='58' cy='58' r='26' fill='{t['accent']}'/>"
        f"<text x='58' y='67' text-anchor='middle'"
        f" font-family='{_SANS}' font-weight='bold' font-size='24'"
        f" fill='{t['avatar_text']}'>{initial}</text>"
        f"<text x='98' y='54' font-family='{_SANS}' font-weight='bold'"
        f" font-size='22' fill='{t['text']}'>{user}</text>"
        f"<text x='98' y='76' font-family='{_SANS}' font-size='12'"
        f" fill='{t['dim']}'>{subtitle}</text>"
        f"<line x1='{_PAD}' y1='100' x2='{_W - _PAD}' y2='100'"
        f" stroke='{t['border']}'/>"
        f"{cells}"
        f"{_sparkline(_dense_series(activity), t)}"
        f"<text x='{_PAD}' y='306' font-family='{_SANS}' font-size='11'"
        f" fill='{t['dim']}'>top: {xml_escape(top_repos)}</text>"
        f"<text x='{_PAD}' y='324' font-family='{_SANS}' font-size='10'"
        f" fill='{t['dim']}'>generated by prsnoop ·"
        f" github.com/MohammedAnasNathani/prsnoop</text>"
        f"</svg>"
    )
