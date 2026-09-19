"""Report: a self-contained one-page HTML masterpiece.

Everything inline: styles, sparkline SVG, score bars, achievement chips,
language donut (conic-gradient), forecast strip. One file, no assets,
opens anywhere, prints beautifully.
"""
from __future__ import annotations

from xml.sax.saxutils import escape as x

from prsnoop.achievements import build_report
from prsnoop.forecast import build_forecast
from prsnoop.models import Activity
from prsnoop.score import compute_score

_CSS = """
:root{--bg:#0d1117;--card:#161b22;--edge:#30363d;--text:#e6edf3;--dim:#8b949e;
--green:#3fb950;--blue:#58a6ff;--amber:#d29922;--red:#f85149;--purple:#bc8cff}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--text);
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
padding:40px 20px}
.wrap{max-width:860px;margin:0 auto}
h1{font-size:34px;letter-spacing:-0.5px}
h1 .r{color:var(--red)}
.sub{color:var(--dim);margin:6px 0 28px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
gap:12px;margin:20px 0}
.stat{background:var(--card);border:1px solid var(--edge);border-radius:10px;
padding:14px 16px}
.stat .k{font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:var(--dim)}
.stat .v{font-size:28px;font-weight:700;margin-top:4px}
.stat .v.g{color:var(--green)}.stat .v.b{color:var(--blue)}.stat .v.a{color:var(--amber)}
.card{background:var(--card);border:1px solid var(--edge);border-radius:10px;
padding:18px 20px;margin:14px 0}
.card h2{font-size:15px;margin-bottom:12px;color:var(--dim);text-transform:uppercase;
letter-spacing:1px}
.bar{display:flex;align-items:center;gap:10px;margin:8px 0}
.bar .n{width:110px;font-size:13px;color:var(--dim)}
.bar .t{flex:1;height:8px;background:#21262d;border-radius:4px;overflow:hidden}
.bar .f{height:100%;border-radius:4px;background:var(--blue)}
.bar .s{width:52px;text-align:right;font-size:13px;font-weight:700}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1px solid var(--edge);border-radius:20px;padding:4px 12px;font-size:13px}
.chip.on{border-color:var(--green);color:var(--green)}
.chip.off{color:var(--faint,#484f58)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--edge)}
th{color:var(--dim);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:0.6px}
.grade{font-size:64px;font-weight:800;color:var(--green)}
footer{margin-top:30px;color:var(--dim);font-size:12px;text-align:center}
footer a{color:var(--blue)}
@media print{body{background:#fff;color:#111}.stat,.card{border-color:#ccc;background:#fff}
.sub,footer{color:#555}}
"""


def _sparkline_svg(activity: Activity, w: int = 780, h: int = 120) -> str:
    totals = {da.date: da.total for da in activity.stats.day_activity}
    from datetime import date as d_
    from datetime import timedelta
    s = activity.stats
    try:
        start = d_.fromisoformat(s.since) if s.since else (
            activity.generated_at.date() - timedelta(days=s.window_days))
        end = d_.fromisoformat(s.until) if s.until else activity.generated_at.date()
    except ValueError:
        return ""
    vals: list[int] = []
    cur = start
    while cur <= end:
        vals.append(totals.get(cur.isoformat(), 0))
        cur += timedelta(days=1)
    if len(vals) < 2:
        return ""
    peak = max(vals) or 1
    step = w / (len(vals) - 1)
    pts = [f"{i * step:.1f},{h - v / peak * (h - 12) - 6:.1f}" for i, v in enumerate(vals)]
    area = f"0,{h} " + " ".join(pts) + f" {w},{h}"
    return (
        f"<svg viewBox='0 0 {w} {h}' width='100%' height='{h}' xmlns='"
        "http://www.w3.org/2000/svg'>"
        f"<polygon points='{area}' fill='#58a6ff' opacity='0.12'/>"
        f"<polyline points='{' '.join(pts)}' fill='none' stroke='#58a6ff' "
        "stroke-width='2' stroke-linejoin='round'/></svg>"
    )


def _donut(languages: list[tuple[str, int]]) -> str:
    colors = ["#58a6ff", "#3fb950", "#d29922", "#bc8cff", "#f85149"]
    top = languages[:5]
    pairs = list(zip(top, colors, strict=False))
    total = sum(n for _, n in top) or 1
    stops: list[str] = []
    acc = 0.0
    for (_lang, n), c in pairs:
        frac = n / total * 100
        stops.append(f"{c} {acc:.0f}% {acc + frac:.0f}%")
        acc += frac
    if acc < 100:
        stops.append(f"#21262d {acc:.0f}% 100%")
    grad = ", ".join(stops)
    legend = "".join(
        f"<span style='color:{c}'>&#9632;</span> {x(lang)} ({n})&nbsp; "
        for (lang, n), c in pairs
    )
    return (
        f"<div style='display:flex;align-items:center;gap:18px'>"
        f"<div style='width:120px;height:120px;border-radius:50%;"
        f"background:conic-gradient({grad})'></div>"
        f"<div style='font-size:13px;color:var(--dim)'>{legend}</div></div>"
    )


def render_report_html(activity: Activity) -> str:
    s = activity.stats
    hs = compute_score(activity)
    board = build_report(activity)
    fc = build_forecast(activity)

    grade_color = ("#3fb950" if hs.total >= 80
                   else "#d29922" if hs.total >= 60 else "#f85149")
    def stat(k: str, v: str, cls: str = "") -> str:
        return (
            f"<div class='stat'><div class='k'>{x(k)}</div>"
            f"<div class='v {cls}'>{v}</div></div>"
        )
    stat_cards = "".join([
        stat("pull requests", str(s.prs_authored)),
        stat("merged", str(s.prs_merged), "g"),
        stat("merge rate", f"{s.merge_rate * 100:.0f}%", "a"),
        stat("reviews", str(s.reviews_given), "b"),
        stat("lines +", f"{s.lines_added:,}", "g"),
        stat("streak", f"{s.longest_streak_days}d", "b"),
    ])

    bars = "".join(
        f"<div class='bar'><div class='n'>{x(p.name)}</div>"
        f"<div class='t'><div class='f' style='width:{p.score:.0f}%'></div></div>"
        f"<div class='s'>{p.score:.0f}</div></div>"
        for p in hs.pillars
    )
    ach_chips = "".join(
        f"<span class='chip {'on' if a.unlocked else 'off'}'>{x(a.icon)} {x(a.name)}</span>"
        for a in board.achievements[:24]
    )
    pr_rows = "".join(
        f"<tr><td>{x(p.repo)}#{p.number}</td><td>{x(p.title[:64])}</td>"
        f"<td>{p.state}</td><td>+{p.additions:,}/-{p.deletions:,}</td></tr>"
        for p in activity.prs[:8]
    )
    forecast_line = (
        f"Trend <b>{x(str(fc.direction))}</b> · {fc.prs_per_week:.1f} PRs/week · "
        f"~{fc.projected_prs} PRs next {fc.horizon_days} days "
        f"({fc.confidence} confidence)"
    )

    window = f"{s.since} to {s.until}" if s.since else f"last {s.window_days} days"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>prsnoop report: {x(activity.user)}</title><style>{_CSS}</style></head>
<body><div class="wrap">
<h1>prsnoop report: <span class="r">{x(activity.user)}</span></h1>
<p class="sub">{x(window)} · {s.distinct_repos} repos · {s.distinct_languages} languages ·
generated {x(activity.generated_at.strftime('%Y-%m-%d'))}</p>
<div class="grid">{stat_cards}</div>
<div class="card"><h2>Activity</h2>{_sparkline_svg(activity)}</div>
<div class="card"><h2>Health score</h2>
<div style="display:flex;align-items:center;gap:26px">
<div style="text-align:center">
<div class="grade" style="color:{grade_color}">{hs.grade}</div>
<div style="color:var(--dim);font-size:13px">{hs.total:.1f} / 100</div></div>
<div style="flex:1">{bars}
<p style="margin-top:10px;font-size:13px;color:var(--dim)">burnout risk:
<b style="color:{grade_color}">{hs.burnout_risk}</b> · {x(hs.burnout_reason)}</p></div>
</div></div>
<div class="card"><h2>Languages</h2>{_donut(s.languages)}</div>
<div class="card"><h2>Achievements ({len(board.unlocked)}/{len(board.achievements)} ·
{board.score} pts)</h2><div class="chips">{ach_chips}</div></div>
<div class="card"><h2>Forecast</h2><p style="font-size:14px">{forecast_line}</p></div>
<div class="card"><h2>Recent pull requests</h2><table>
<tr><th>repo</th><th>title</th><th>state</th><th>lines</th></tr>{pr_rows}</table></div>
<footer>generated by <a href="https://github.com/MohammedAnasNathani/prsnoop">prsnoop</a>
· zero dependencies · one file, no assets</footer>
</div></body></html>
"""
