"""Renderers: turn an Activity into human-readable output.

Each renderer is a pure function ``render(activity) -> str`` so new formats
are one function away, and output is deterministic for tests.

All output is plain ASCII by design: reports must survive every terminal,
pager, diff view, and legacy Windows console without mangling. States are
marked MERGED / OPEN / CLOSED in text, not symbols.
"""
from __future__ import annotations

import csv
import io
import json
from collections.abc import Callable
from html import escape as html_escape

from prsnoop.badge import render_badge
from prsnoop.models import (
    MERGED,
    OPEN,
    Activity,
    DayActivity,
    PRRecord,
    Stats,
)
from prsnoop.org import OrgPR, OrgPulse
from prsnoop.stats import TrendDelta

Renderer = Callable[[Activity], str]

_STATE_LABEL = {MERGED: "merged", OPEN: "open", "closed": "closed"}

# Trend deltas live on Activity.trend (a list of TrendDelta). Renderers
# read it directly; it is empty when --trend was not passed.
TREND_ATTR = "trend"


def _fmt_days(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}d"


def _fmt_pct(value: float) -> str:
    return f"{value * 100:.0f}%"


def _momentum_text(s: Stats) -> str:
    """'accelerating (+38% second half)' for table/markdown/html rows."""
    pct = "n/a" if s.momentum_pct is None else format(s.momentum_pct, "+.0f")
    return f"{s.momentum} ({pct} second half)"


def _size_letter(median_lines: int) -> str:
    """Letter grade for a typical PR size."""
    if median_lines < 10:
        return "XS"
    if median_lines < 100:
        return "S"
    if median_lines < 1000:
        return "M"
    if median_lines < 5000:
        return "L"
    return "XL"


def _trend_of(activity: Activity) -> list[TrendDelta]:
    """Trend deltas computed for this activity, if any."""
    return [d for d in activity.trend if isinstance(d, TrendDelta)]


def _fmt_trend_value(delta: TrendDelta) -> str:
    """'+3 (12%)' style compact annotation for one delta."""
    d = delta.delta
    if d == 0:
        return "= 0"
    sign = "+" if d > 0 else "-"
    magnitude = abs(d)
    if magnitude >= 100:
        mag_str = f"{magnitude:.0f}"
    else:
        mag_str = f"{magnitude:g}"
    if delta.pct is not None:
        return f"{sign}{mag_str} ({delta.pct:+.0f}%)"
    return f"{sign}{mag_str}"


def _sparkline(days: list[DayActivity], width: int = 30) -> str:
    """Compact one-line activity chart, pure ASCII.

    One character per day bucket, '#' scaled to that day's total, '.' for
    empty days. Buckets squeeze a window longer than ``width`` days so a
    90 day report still fits one line.
    """
    if not days:
        return ""
    if len(days) > width:
        per = len(days) / width
        buckets: list[int] = []
        for i in range(width):
            lo = int(i * per)
            hi = max(lo + 1, int((i + 1) * per))
            buckets.append(sum(d.total for d in days[lo:hi]))
    else:
        buckets = [d.total for d in days]
    peak = max(buckets, default=0)
    if peak == 0:
        return "." * len(buckets)
    levels = " .:;+=xX#"
    chars = []
    for b in buckets:
        if b == 0:
            chars.append(".")
        else:
            idx = max(1, round(b / peak * (len(levels) - 1)))
            chars.append(levels[idx])
    return "".join(chars)


# --------------------------------------------------------------------- table

def render_table(activity: Activity) -> str:
    """Compact human summary for the terminal."""
    s = activity.stats
    window = s.since or f"last {s.window_days} days"
    if s.until:
        window += f" to {s.until}"
    lines = [
        f"prsnoop | {activity.user}",
        f"window: {window}",
        "",
        f"  Pull requests      {s.prs_authored}",
        f"    merged           {s.prs_merged}",
        f"    open             {s.prs_open}",
        f"    closed           {s.prs_closed_unmerged}",
        f"  Reviews given      {s.reviews_given}",
        f"  Issues opened      {s.issues_opened} (closed: {s.issues_closed})",
        f"  Lines changed      +{s.lines_added} / -{s.lines_deleted}",
        f"  Merge rate         {_fmt_pct(s.merge_rate)}",
        f"  Merge time         median {_fmt_days(s.median_days_to_merge)},"
        f" p90 {_fmt_days(s.p90_days_to_merge)}",
        f"  Active days        {s.active_days} (avg {s.avg_prs_per_active_day} PRs/day)",
        f"  Streaks            longest {s.longest_streak_days}d,"
        f" current {s.current_streak_days}d",
        f"  Repos              {s.distinct_repos}",
    ]
    if s.momentum:
        pct = "-" if s.momentum_pct is None else f"{s.momentum_pct:+.0f}%"
        lines.append(
            f"  Momentum           {s.momentum} ({pct} second half)"
        )
    if s.busiest_day:
        lines.append(
            f"  Busiest day        {s.busiest_day} ({s.busiest_day_count} items)"
        )
    if s.languages:
        mix = ", ".join(f"{lang} {n}" for lang, n in s.languages[:5])
        lines.append(f"  Languages          {mix}")
    if s.size_median_lines is not None:
        dist = " ".join(f"{k} {v}" for k, v in s.size_buckets.items() if v)
        lines.append(
            f"  Typical size       {_size_letter(s.size_median_lines)}"
            f" (median {s.size_median_lines} lines)"
        )
        lines.append(f"  Size spread        {dist}")
    if s.repo_performance:
        lines += ["", "  Where work lands"]
        for r in s.repo_performance[:5]:
            med = _fmt_days(r.median_days_to_merge)
            lines.append(
                f"    {r.repo:<28} {r.prs:>3} prs"
                f"  {r.merge_rate * 100:>3.0f}% merged  median {med}"
            )
    if s.day_activity:
        spark = _sparkline(s.day_activity)
        first, last = s.day_activity[0].date, s.day_activity[-1].date
        lines.append(f"  Activity chart     {spark}")
        lines.append(f"    {first} to {last}, # peak, . quiet")

    trend = _trend_of(activity)
    if trend:
        lines += ["", "  Trend vs previous window"]
        for d in trend:
            mark = "up" if d.improved else ("down" if d.direction else "flat")
            lines.append(
                f"    {d.label:<20} {d.previous:g} -> {d.current:g}"
                f"  {_fmt_trend_value(d):>12}  {mark}"
            )

    lines += ["", "  Recent pull requests"]
    for pr in activity.prs[:10]:
        lines.append(
            f"  [{_STATE_LABEL[pr.state]:>6}] {pr.repo}#{pr.number} {pr.title[:44]}"
        )
    if not activity.prs:
        lines.append("  (none)")
    lines += ["", "  Daily activity"]
    lines += [f"    {da.date}  {'#' * min(da.total, 30)}" for da in s.day_activity[:14]]
    if len(s.day_activity) > 14:
        lines.append(f"    ... {len(s.day_activity) - 14} more days")
    if not s.day_activity:
        lines.append("    (none)")
    return "\n".join(lines)


# ------------------------------------------------------------------ markdown

def _md_pr_row(pr: PRRecord) -> str:
    label = _STATE_LABEL[pr.state]
    return (
        f"| {label} | [{pr.repo}#{pr.number}]({pr.url}) "
        f"| {pr.title} | +{pr.additions}/-{pr.deletions} "
        f"| {_fmt_days(pr.days_to_merge)} |"
    )


def render_markdown(activity: Activity) -> str:
    """GitHub-flavored Markdown report."""
    s = activity.stats
    window = s.since or f"last {s.window_days} days"
    if s.until:
        window += f" to {s.until}"
    out: list[str] = [
        f"# Contribution report: {activity.user}",
        "",
        f"_Generated by [prsnoop](https://github.com/MohammedAnasNathani/prsnoop)"
        f" on {activity.generated_at.strftime('%Y-%m-%d %H:%M UTC')} | window: {window}_",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Pull requests | {s.prs_authored} |",
        f"| Merged | {s.prs_merged} |",
        f"| Open | {s.prs_open} |",
        f"| Reviews given | {s.reviews_given} |",
        f"| Issues opened | {s.issues_opened} |",
        f"| Lines changed | +{s.lines_added} / -{s.lines_deleted} |",
        f"| Merge rate | {_fmt_pct(s.merge_rate)} |",
        f"| Median time to merge | {_fmt_days(s.median_days_to_merge)} |",
        f"| P90 time to merge | {_fmt_days(s.p90_days_to_merge)} |",
        f"| Active days | {s.active_days} |",
        f"| Longest streak | {s.longest_streak_days} days |",
        f"| Current streak | {s.current_streak_days} days |",
        f"| Distinct repos | {s.distinct_repos} |",
        *( [f"| Momentum | {_momentum_text(s)} |"] if s.momentum else [] ),
        "",
    ]
    if s.top_repos:
        out += ["## Top repositories", "", "| Repository | PRs |", "|---|---:|"]
        out += [f"| [{repo}](https://github.com/{repo}) | {n} |" for repo, n in s.top_repos]
        out.append("")
    trend = _trend_of(activity)
    if trend:
        out += [
            "## Trend vs previous window",
            "",
            "| Metric | Previous | Current | Change |",
            "|---|---:|---:|---|",
        ]
        for d in trend:
            out.append(
                f"| {d.label} | {d.previous:g} | {d.current:g}"
                f" | {_fmt_trend_value(d)} |"
            )
        out.append("")
    if s.repo_performance:
        out += [
            "## Where your work lands",
            "",
            "Per-repository outcomes for every repo with two or more PRs"
            " in the window.",
            "",
            "| Repository | PRs | Merged | Merge rate | Median days |",
            "|---|---:|---:|---:|---:|",
        ]
        for r in s.repo_performance:
            med = "-" if r.median_days_to_merge is None else f"{r.median_days_to_merge:.1f}"
            out.append(
                f"| [{r.repo}](https://github.com/{r.repo}) | {r.prs}"
                f" | {r.merged} | {r.merge_rate * 100:.0f}% | {med} |"
            )
        out.append("")
    if s.size_median_lines is not None:
        dist = " / ".join(f"{k} {v}" for k, v in s.size_buckets.items() if v)
        out += [
            "## PR size profile",
            "",
            f"Typical PR: **{_size_letter(s.size_median_lines)}**"
            f" (median {s.size_median_lines} changed lines). Distribution: {dist}.",
            "",
        ]
    if s.languages:
        out += ["## Languages", "", "| Language | PRs |", "|---|---:|"]
        out += [f"| {lang} | {n} |" for lang, n in s.languages]
        out.append("")
    if s.day_activity:
        out += [
            "## Daily activity",
            "",
            "| Date | PRs | Merged | Issues | Reviews | Total |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        out += [
            f"| {da.date} | {da.prs} | {da.merged} | {da.issues}"
            f" | {da.reviews} | {da.total} |"
            for da in s.day_activity
        ]
        out.append("")
    if activity.prs:
        out += [
            "## Pull requests",
            "",
            "| State | PR | Title | Size | Days to merge |",
            "|---|---|---|---|---|",
        ]
        out += [_md_pr_row(pr) for pr in activity.prs]
        out.append("")
    if activity.reviews:
        out += [
            "## Reviews given",
            "",
            "| PR | Review | When |",
            "|---|---|---|",
        ]
        out += [
            f"| [{r.repo}#{r.pr_number}]({r.pr_url}) | {r.state} | "
            f"{r.submitted_at.strftime('%Y-%m-%d')} |"
            for r in activity.reviews
        ]
        out.append("")
    if activity.issues:
        out += [
            "## Issues opened",
            "",
            "| Issue | State | Comments |",
            "|---|---|---|",
        ]
        out += [
            f"| [{i.repo}#{i.number}]({i.url}) | {i.state} | {i.comments} |"
            for i in activity.issues
        ]
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------- html

_CSS = """\
:root { color-scheme: light dark; --bg: #ffffff; --fg: #1f2328; --dim: #656d76;
  --line: #d0d7de; --panel: #f6f8fa; --green: #1a7f37; --amber: #9a6700; }
@media (prefers-color-scheme: dark) { :root { --bg: #0d1117; --fg: #e6edf3;
  --dim: #8b949e; --line: #30363d; --panel: #161b22; --green: #3fb950;
  --amber: #d29922; } }
* { box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 0;
  background: var(--bg); color: var(--fg); line-height: 1.55; padding: 2rem 1rem; }
main { max-width: 56rem; margin: 0 auto; }
h1 { font-size: 1.6rem; margin: 0 0 0.2rem; }
h2 { font-size: 1.1rem; margin: 2rem 0 0.6rem; }
a { color: var(--green); }
.meta { color: var(--dim); font-size: 0.9rem; margin: 0 0 1.4rem; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  gap: 0.6rem; margin: 1rem 0; }
.card { background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 0.7rem 0.9rem; }
.card .num { font-size: 1.45rem; font-weight: 700; letter-spacing: -0.02em; }
.card .lbl { color: var(--dim); font-size: 0.78rem; text-transform: uppercase;
  letter-spacing: 0.04em; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: 0.92rem; }
th, td { text-align: left; padding: 0.45rem 0.6rem; border: 1px solid var(--line);
  vertical-align: top; }
th { background: var(--panel); }
.state-merged { color: var(--green); font-weight: 600; }
.state-open { color: var(--amber); font-weight: 600; }
.state-closed { color: var(--dim); }
.chart { width: 100%; height: auto; display: block; margin: 0.4rem 0 1rem; }
.trend-up { color: var(--green); font-weight: 600; }
.trend-down { color: #cf222e; font-weight: 600; }
.trend-flat { color: var(--dim); }
footer { color: var(--dim); font-size: 0.85rem; margin-top: 2.5rem;
  border-top: 1px solid var(--line); padding-top: 0.8rem; }
"""


def _svg_chart(days: list[DayActivity]) -> str:
    """Inline daily-activity bar chart, no external assets or JS."""
    if not days:
        return ""
    width, height, pad = 720, 160, 8
    n = len(days)
    gap = 2 if n < 60 else 0
    inner = width - pad * 2
    bar_w = max(1.0, (inner - gap * (n - 1)) / n)
    peak = max(d.total for d in days)
    chart_h = height - pad * 2 - 18
    rects: list[str] = []
    for i, da in enumerate(days):
        h = round(da.total / peak * chart_h, 1) if peak else 0
        x = pad + i * (bar_w + gap)
        y = pad + chart_h - h
        color = "#3fb950" if da.merged else ("#8b949e" if da.total else "#30363d")
        rects.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'fill="{color}" rx="1"><title>{da.date}: {da.total} items</title></rect>'
        )
    first_label = (
        f'<text x="{pad}" y="{height - 4}" font-size="10" '
        f'fill="#8b949e">{days[0].date}</text>'
    )
    last_label = (
        f'<text x="{width - pad}" y="{height - 4}" font-size="10" '
        f'fill="#8b949e" text-anchor="end">{days[-1].date}</text>'
    )
    labels = first_label + last_label
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" '
        f'role="img" aria-label="daily activity chart">{"".join(rects)}{labels}</svg>'
    )


def _trend_cell(delta: TrendDelta) -> str:
    arrow = {"up": "&#8593;", "down": "&#8595;", "flat": "&#8594;"}
    cls = "flat"
    mark = arrow["flat"]
    if delta.improved and delta.direction:
        cls, mark = "up", arrow["up"]
    elif delta.direction and not delta.improved:
        cls, mark = "down", arrow["down"]
    change = html_escape(_fmt_trend_value(delta))
    return f'<td><span class="trend-{cls}">{mark} {change}</span></td>'


def render_html(activity: Activity) -> str:
    """Standalone HTML report, no external assets."""
    s = activity.stats

    def esc(v: object) -> str:
        return html_escape(str(v))

    cards = [
        ("Pull requests", str(s.prs_authored)),
        ("Merged", str(s.prs_merged)),
        ("Merge rate", _fmt_pct(s.merge_rate)),
        ("Reviews given", str(s.reviews_given)),
        ("Issues opened", str(s.issues_opened)),
        ("Lines", f"+{s.lines_added} / -{s.lines_deleted}"),
    ]
    card_html = "".join(
        f'<div class="card"><div class="num">{esc(v)}</div>'
        f'<div class="lbl">{esc(k)}</div></div>'
        for k, v in cards
    )

    timing_rows = "".join(
        f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>"
        for k, v in (
            ("Median time to merge", _fmt_days(s.median_days_to_merge)),
            ("P90 time to merge", _fmt_days(s.p90_days_to_merge)),
            ("Active days", str(s.active_days)),
            ("Longest streak", f"{s.longest_streak_days} days"),
            ("Current streak", f"{s.current_streak_days} days"),
            ("Distinct repos", str(s.distinct_repos)),
            *( [("Momentum", _momentum_text(s))] if s.momentum else [] ),
        )
    )

    trend_html = ""
    trend = _trend_of(activity)
    if trend:
        trend_html = (
            "<h2>Trend vs previous window</h2><table>"
            "<tr><th>Metric</th><th>Previous</th><th>Current</th><th>Change</th></tr>"
            + "".join(
                f"<tr><td>{esc(d.label)}</td><td>{d.previous:g}</td>"
                f"<td>{d.current:g}</td>{_trend_cell(d)}</tr>"
                for d in trend
            )
            + "</table>"
        )

    def pr_row(pr: PRRecord) -> str:
        label = _STATE_LABEL[pr.state]
        cls = {"merged": "state-merged", "open": "state-open"}.get(label, "state-closed")
        return (
            "<tr>"
            f'<td class="{cls}">{esc(label)}</td>'
            f'<td><a href="{esc(pr.url)}">{esc(f"{pr.repo}#{pr.number}")}</a></td>'
            f"<td>{esc(pr.title)}</td>"
            f"<td>+{pr.additions}/-{pr.deletions}</td>"
            f"<td>{esc(_fmt_days(pr.days_to_merge))}</td>"
            "</tr>"
        )

    pr_rows = "".join(pr_row(pr) for pr in activity.prs)
    review_rows = "".join(
        "<tr>"
        f'<td><a href="{esc(r.pr_url)}">{esc(f"{r.repo}#{r.pr_number}")}</a></td>'
        f"<td>{esc(r.state)}</td>"
        f"<td>{esc(r.submitted_at.strftime('%Y-%m-%d'))}</td>"
        "</tr>"
        for r in activity.reviews
    )
    issue_rows = "".join(
        "<tr>"
        f'<td><a href="{esc(i.url)}">{esc(f"{i.repo}#{i.number}")}</a></td>'
        f"<td>{esc(i.title)}</td>"
        f"<td>{esc(i.state)}</td>"
        f"<td>{i.comments}</td>"
        "</tr>"
        for i in activity.issues
    )

    day_bars = ""
    if s.day_activity:
        day_bars = f"<h2>Daily activity</h2>{_svg_chart(s.day_activity)}"

    prs_html = (
        f"<h2>Pull requests</h2><table>"
        f"<tr><th>State</th><th>PR</th><th>Title</th><th>Size</th><th>Merged in</th></tr>"
        f"{pr_rows}</table>"
        if activity.prs else ""
    )
    repos_html = ""
    if s.repo_performance:
        rows = "".join(
            "<tr>"
            f'<td><a href="https://github.com/{esc(r.repo)}">{esc(r.repo)}</a></td>'
            f"<td>{r.prs}</td><td>{r.merged}</td>"
            f"<td>{r.merge_rate * 100:.0f}%</td>"
            f"<td>{esc(_fmt_days(r.median_days_to_merge))}</td>"
            "</tr>"
            for r in s.repo_performance
        )
        repos_html = (
            "<h2>Where your work lands</h2><table>"
            "<tr><th>Repository</th><th>PRs</th><th>Merged</th>"
            "<th>Merge rate</th><th>Median days</th></tr>"
            f"{rows}</table>"
        )
    sizes_html = ""
    if s.size_median_lines is not None:
        size_cells = "".join(
            f"<td>{esc(k)}: {v}</td>" for k, v in s.size_buckets.items() if v
        )
        sizes_html = (
            f"<h2>PR size profile</h2><table><tr>"
            f"<th>Typical</th><th>Median lines</th><th>Distribution</th></tr>"
            f"<tr><td>{esc(_size_letter(s.size_median_lines))}</td>"
            f"<td>{s.size_median_lines}</td><td>{size_cells}</td></tr></table>"
        )
    reviews_html = (
        f"<h2>Reviews given</h2><table>"
        f"<tr><th>PR</th><th>Review</th><th>When</th></tr>{review_rows}</table>"
        if activity.reviews else ""
    )
    issues_html = (
        f"<h2>Issues opened</h2><table>"
        f"<tr><th>Issue</th><th>Title</th><th>State</th><th>Comments</th></tr>"
        f"{issue_rows}</table>"
        if activity.issues else ""
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>prsnoop | {esc(activity.user)}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<h1>Contribution report: {esc(activity.user)}</h1>
<p class="meta">Generated by <a href="https://github.com/MohammedAnasNathani/prsnoop">prsnoop</a>
on {activity.generated_at.strftime('%Y-%m-%d %H:%M UTC')}</p>
<div class="cards">{card_html}</div>
<table>{timing_rows}</table>
{trend_html}
{repos_html}
{sizes_html}
{prs_html}
{reviews_html}
{issues_html}
{day_bars}
<footer>prsnoop report | zero dependencies | MIT</footer>
</main>
</body>
</html>
"""


# ----------------------------------------------------------------------- csv

def render_csv(activity: Activity) -> str:
    """One CSV row per PR: spreadsheet ready."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["repo", "number", "title", "state", "created_at", "merged_at",
         "additions", "deletions", "changed_files", "labels", "comments",
         "language", "days_to_merge", "url"]
    )
    for pr in activity.prs:
        writer.writerow(
            [pr.repo, pr.number, pr.title, pr.state,
             pr.created_at.strftime("%Y-%m-%d"),
             pr.merged_at.strftime("%Y-%m-%d") if pr.merged_at else "",
             pr.additions, pr.deletions, pr.changed_files,
             ";".join(pr.labels), pr.comments, pr.language,
             f"{pr.days_to_merge:.2f}" if pr.days_to_merge is not None else "",
             pr.url]
        )
    return buf.getvalue()


# ---------------------------------------------------------------------- json

def render_json(activity: Activity) -> str:
    """Complete snapshot including derived stats and trend deltas."""
    payload = activity.to_dict()
    trend = _trend_of(activity)
    if trend:
        payload["trend"] = [d.to_dict() for d in trend]
    return json.dumps(payload, indent=2, ensure_ascii=True)


RENDERERS: dict[str, Renderer] = {
    "table": render_table,
    "markdown": render_markdown,
    "html": render_html,
    "csv": render_csv,
    "json": render_json,
    "badge": render_badge,
}


# ------------------------------------------------------------------ org pulse

def _org_spark(counts: list[tuple[str, int]], width: int = 30) -> str:
    """One-line activity chart for org day counts, same style as _sparkline."""
    if not counts:
        return ""
    if len(counts) > width:
        per = len(counts) / width
        buckets = []
        for i in range(width):
            lo = int(i * per)
            hi = max(lo + 1, int((i + 1) * per))
            buckets.append(sum(n for _d, n in counts[lo:hi]))
    else:
        buckets = [n for _d, n in counts]
    peak = max(buckets, default=0)
    if peak == 0:
        return "." * len(buckets)
    levels = " .:;+=xX#"
    return "".join(
        "." if b == 0 else levels[max(1, round(b / peak * (len(levels) - 1)))]
        for b in buckets
    )


def render_org_html(prs: list[OrgPR], pulse: OrgPulse) -> str:
    """Standalone HTML page for an org or repo pulse."""
    s = pulse

    def esc(v: object) -> str:
        return html_escape(str(v))

    rate = s.prs_merged / s.prs_opened * 100 if s.prs_opened else 0
    cards = [
        ("PRs opened", str(s.prs_opened)),
        ("Merged", str(s.prs_merged)),
        ("Merge rate", f"{rate:.0f}%"),
        ("Authors", str(s.authors)),
        ("Repositories", str(s.repos)),
        ("Median merge", _fmt_days(s.median_days_to_merge)),
    ]
    card_html = "".join(
        f'<div class="card"><div class="num">{esc(v)}</div>'
        f'<div class="lbl">{esc(k)}</div></div>'
        for k, v in cards
    )
    day_activities = [
        DayActivity(date=d, prs=n) for d, n in s.day_counts
    ]
    chart = _svg_chart(day_activities) if day_activities else ""
    chart_html = f"<h2>Opening activity</h2>{chart}" if chart else ""

    author_rows = "".join(
        f'<tr><td><a href="https://github.com/{esc(a)}">{esc(a)}</a></td>'
        f"<td>{n}</td></tr>"
        for a, n in s.top_authors
    )
    repo_rows = "".join(
        f'<tr><td><a href="https://github.com/{esc(r)}">{esc(r)}</a></td>'
        f"<td>{n}</td></tr>"
        for r, n in s.top_repos
    )
    pr_rows = "".join(
        "<tr>"
        f'<td class="state-{esc(p.state)}">{esc(p.state)}</td>'
        f'<td><a href="{esc(p.url)}">{esc(f"{p.repo}#{p.number}")}</a></td>'
        f"<td>{esc(p.title)}</td>"
        f"<td>{esc(p.author)}</td>"
        "</tr>"
        for p in prs[:30]
    )
    prs_html = (
        "<h2>Recent pull requests</h2><table>"
        "<tr><th>State</th><th>PR</th><th>Title</th><th>Author</th></tr>"
        f"{pr_rows}</table>"
        if prs
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>prsnoop | {esc(s.label)} pulse: {esc(s.org)}</title>
<style>{_CSS}</style>
</head>
<body>
<main>
<h1>{esc(s.label.capitalize())} pulse: {esc(s.org)}</h1>
<p class="meta">
Generated by <a href="https://github.com/MohammedAnasNathani/prsnoop">prsnoop</a>
on {s.generated_at.strftime('%Y-%m-%d %H:%M UTC')}
| window: {esc(s.since)} to {esc(s.until)}</p>
<div class="cards">{card_html}</div>
{chart_html}
<h2>Top authors</h2><table>
<tr><th>Author</th><th>PRs</th></tr>{author_rows}</table>
<h2>Hot repositories</h2><table>
<tr><th>Repository</th><th>PRs</th></tr>{repo_rows}</table>
{prs_html}
<footer>prsnoop report | zero dependencies | MIT</footer>
</main>
</body>
</html>
"""


def render_org_csv(prs: list[OrgPR], pulse: OrgPulse) -> str:
    """One CSV row per pulse PR, with the author column."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["org", "repo", "number", "title", "author", "state",
         "created_at", "merged_at", "days_to_merge", "url"]
    )
    for p in prs:
        writer.writerow(
            [pulse.org, p.repo, p.number, p.title, p.author, p.state,
             p.created_at.strftime("%Y-%m-%d"),
             p.merged_at.strftime("%Y-%m-%d") if p.merged_at else "",
             f"{p.days_to_merge:.2f}" if p.days_to_merge is not None else "",
             p.url]
        )
    return buf.getvalue()


def render_org_table(prs: list[OrgPR], pulse: OrgPulse) -> str:
    """Terminal rendering of an organization pulse."""
    lines = [
        f"prsnoop {pulse.label} | {pulse.org}",
        f"window: {pulse.since} to {pulse.until}",
        "",
        f"  PRs opened        {pulse.prs_opened}",
        f"    merged         {pulse.prs_merged}",
        f"    open           {pulse.prs_open}",
        f"    closed         {pulse.prs_closed_unmerged}",
        f"  Authors           {pulse.authors}",
        f"  Repos             {pulse.repos}",
        f"  Median merge      {_fmt_days(pulse.median_days_to_merge)}",
    ]
    if pulse.top_authors:
        lines += ["", "  Top authors"]
        for author, n in pulse.top_authors[:8]:
            lines.append(f"    {author:<20} {n}")
    if pulse.top_repos:
        lines += ["", "  Hot repositories"]
        for repo, n in pulse.top_repos[:8]:
            lines.append(f"    {repo:<32} {n}")
    if pulse.day_counts:
        spark = _org_spark(pulse.day_counts)
        first, last = pulse.day_counts[0][0], pulse.day_counts[-1][0]
        lines += ["", f"  Activity chart     {spark}",
                 f"    {first} to {last}, # peak, . quiet"]
    if prs:
        lines += ["", "  Recent pull requests"]
        for p in prs[:10]:
            lines.append(f"  [{p.state:>6}] {p.repo}#{p.number} {p.title[:44]}")
    return "\n".join(lines)


def render_org_markdown(prs: list[OrgPR], pulse: OrgPulse) -> str:
    """GitHub-flavored Markdown rendering of an organization pulse."""
    out = [
        f"# {pulse.label.capitalize()} pulse: {pulse.org}",
        "",
        "_Generated by [prsnoop](https://github.com/MohammedAnasNathani/prsnoop)"
        f" | window: {pulse.since} to {pulse.until}_",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| PRs opened | {pulse.prs_opened} |",
        f"| Merged | {pulse.prs_merged} |",
        f"| Open | {pulse.prs_open} |",
        f"| Authors | {pulse.authors} |",
        f"| Repositories | {pulse.repos} |",
        f"| Median time to merge | {_fmt_days(pulse.median_days_to_merge)} |",
        "",
    ]
    if pulse.top_authors:
        out += ["## Top authors", "", "| Author | PRs |", "|---|---:|"]
        out += [f"| [{a}](https://github.com/{a}) | {n} |" for a, n in pulse.top_authors]
        out.append("")
    if pulse.top_repos:
        out += ["## Hot repositories", "", "| Repository | PRs |", "|---|---:|"]
        out += [f"| [{r}](https://github.com/{r}) | {n} |" for r, n in pulse.top_repos]
        out.append("")
    if prs:
        out += ["## Recent pull requests", "",
                "| State | PR | Title | Author |", "|---|---|---|---|"]
        for p in prs[:30]:
            out.append(
                f"| {p.state} | [{p.repo}#{p.number}]({p.url})"
                f" | {p.title} | {p.author} |"
            )
        out.append("")
    return "\n".join(out)
