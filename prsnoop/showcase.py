"""Showcase: generate a full interactive single-file web app.

Design language: surveillance dossier. Radar green on near black, mono
telemetry labels, corner brackets, scanlines, stamp verdicts. One HTML file;
the data rides inside as embedded JSON.
"""
from __future__ import annotations

import json
from datetime import date as date_cls
from datetime import timedelta
from xml.sax.saxutils import escape as x_escape

from prsnoop.achievements import build_report
from prsnoop.forecast import build_forecast
from prsnoop.models import Activity, JsonDict
from prsnoop.score import compute_score


def _series(activity: Activity) -> list[tuple[str, int, int, int, int]]:
    """(date, prs, merged, issues, reviews) per day across the window."""
    s = activity.stats
    buckets: dict[str, list[int]] = {}
    for da in s.day_activity:
        buckets[da.date] = [da.prs, da.merged, da.issues, da.reviews]
    try:
        start = (
            date_cls.fromisoformat(s.since)
            if s.since
            else activity.generated_at.date() - timedelta(days=s.window_days)
        )
        end = (
            date_cls.fromisoformat(s.until)
            if s.until
            else activity.generated_at.date()
        )
    except ValueError:
        start, end = date_cls.today(), date_cls.today()
    out: list[tuple[str, int, int, int, int]] = []
    cur = start
    while cur <= end:
        iso = cur.isoformat()
        p, m, i, r = buckets.get(iso, [0, 0, 0, 0])
        out.append((iso, p, m, i, r))
        cur += timedelta(days=1)
    return out


def build_data(activity: Activity) -> JsonDict:
    """Assemble the JSON payload embedded into the page."""
    s = activity.stats
    hs = compute_score(activity)
    board = build_report(activity)
    fc = build_forecast(activity)
    return {
        "user": activity.user,
        "generated": activity.generated_at.strftime("%Y-%m-%d"),
        "window": s.window_days,
        "stats": {
            "prs": s.prs_authored,
            "merged": s.prs_merged,
            "open": s.prs_open,
            "rate": round(s.merge_rate * 100, 1),
            "reviews": s.reviews_given,
            "issues": s.issues_opened,
            "added": s.lines_added,
            "deleted": s.lines_deleted,
            "active": s.active_days,
            "streak": s.longest_streak_days,
            "repos": s.distinct_repos,
            "langs": s.distinct_languages,
            "median": s.median_days_to_merge,
            "momentum": s.momentum,
        },
        "score": {
            "total": round(hs.total, 1),
            "grade": hs.grade,
            "band": hs.band,
            "risk": hs.burnout_risk,
            "pillars": [p.to_dict() for p in hs.pillars],
        },
        "achievements": [a.to_dict() for a in board.achievements],
        "achScore": board.score,
        "achDone": len(board.unlocked),
        "forecast": {
            "direction": fc.direction,
            "confidence": fc.confidence,
            "perWeek": round(fc.prs_per_week, 2),
            "perMonth": round(fc.prs_per_month, 1),
            "next30": fc.projected_prs,
            "nextYear": fc.prs_per_year,
        },
        "languages": [list(x) for x in s.languages],
        "repos": [list(x) for x in s.top_repos],
        "days": _series(activity),
        "prs": [
            {
                "repo": p.repo,
                "number": p.number,
                "title": p.title,
                "state": p.state,
                "added": p.additions,
                "deleted": p.deletions,
                "comments": p.comments,
                "date": p.created_at.strftime("%Y-%m-%d"),
            }
            for p in sorted(activity.prs, key=lambda p: p.created_at, reverse=True)[:400]
        ],
    }

_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
*{margin:0;padding:0;box-sizing:border-box}
:root{
--bg:#060a08;--panel:#0a100d;--panel2:#0d1512;--line:#18251e;--line2:#20322a;
--text:#d9e6dc;--dim:#7f948a;--faint:#48584f;
--acc:#3dffa2;--acc-dim:#1d7a51;--amber:#f0b429;--red:#ff5a3c;
--sans:'Space Grotesk',sans-serif;--mono:'IBM Plex Mono',monospace}
body.light{
--bg:#eef1ec;--panel:#f7f9f5;--panel2:#e9ede7;--line:#d3dad1;--line2:#c2cbc0;
--text:#131a15;--dim:#4c5a51;--faint:#93a096;--acc:#0b7a4b;--acc-dim:#0b7a4b}
html{background:var(--bg)}
body{background:var(--bg);color:var(--text);font-family:var(--sans);
min-height:100vh;position:relative}
body:before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
background-image:linear-gradient(var(--line) 1px,transparent 1px),
linear-gradient(90deg,var(--line) 1px,transparent 1px);
background-size:44px 44px;opacity:.35}
body:after{content:"";position:fixed;inset:0;pointer-events:none;z-index:40;
background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(0,0,0,.09) 3px 4px);
mix-blend-mode:overlay}
.wrap{max-width:1040px;margin:0 auto;padding:30px 22px 90px;position:relative;z-index:1}
.topbar{display:flex;justify-content:space-between;align-items:center;
font-family:var(--mono);font-size:10.5px;letter-spacing:.22em;color:var(--faint);
border-bottom:1px solid var(--line2);padding-bottom:12px;text-transform:uppercase}
.topbar .live{color:var(--acc)}
.topbar .live:before{content:"●";margin-right:7px;animation:blink 1.6s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
#theme{background:transparent;border:1px solid var(--line2);color:var(--dim);
font-family:var(--mono);font-size:10.5px;letter-spacing:.18em;padding:6px 14px;
cursor:pointer;text-transform:uppercase}
#theme:hover{color:var(--acc);border-color:var(--acc-dim)}
.subject{margin:44px 0 10px}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.34em;
color:var(--acc);text-transform:uppercase}
.subject h1{font-size:clamp(44px,9vw,96px);font-weight:700;letter-spacing:-2px;
line-height:.95;text-transform:uppercase;margin:10px 0 14px}
.dossier{font-family:var(--mono);font-size:11.5px;color:var(--dim);
display:flex;flex-wrap:wrap;gap:6px 26px;border-top:1px solid var(--line2);
border-bottom:1px solid var(--line2);padding:10px 0}
.dossier b{color:var(--text);font-weight:500}
.panel{position:relative;background:var(--panel);border:1px solid var(--line);
padding:22px 24px;margin:18px 0}
.panel>i{position:absolute;width:14px;height:14px;border:0 solid var(--acc);
opacity:.9}
.panel>i.tl{top:-1px;left:-1px;border-top-width:1px;border-left-width:1px}
.panel>i.tr{top:-1px;right:-1px;border-top-width:1px;border-right-width:1px}
.panel>i.bl{bottom:-1px;left:-1px;border-bottom-width:1px;border-left-width:1px}
.panel>i.br{bottom:-1px;right:-1px;border-bottom-width:1px;border-right-width:1px}
.panel h2{font-family:var(--mono);font-size:10.5px;font-weight:500;
letter-spacing:.3em;color:var(--dim);text-transform:uppercase;
display:flex;justify-content:space-between;margin-bottom:18px;flex-wrap:wrap;gap:6px}
.panel h2 .no{color:var(--acc)}
.panel h2 .hint{font-size:10px;letter-spacing:.12em;color:var(--faint);
text-transform:none}
.strip{display:grid;grid-template-columns:repeat(6,1fr);
border:1px solid var(--line);background:var(--panel)}
.strip .cell{padding:16px 14px 14px;border-right:1px solid var(--line);
position:relative}
.strip .cell:last-child{border-right:0}
.strip .idx{font-family:var(--mono);font-size:9px;letter-spacing:.2em;
color:var(--faint)}
.strip .v{font-size:clamp(20px,3.4vw,34px);font-weight:700;margin-top:6px;
font-variant-numeric:tabular-nums;letter-spacing:-1px}
.strip .v small{font-size:12px;font-weight:400;color:var(--dim)}
.strip .lab{font-family:var(--mono);font-size:9.5px;letter-spacing:.18em;
color:var(--dim);text-transform:uppercase;margin-top:4px}
@media(max-width:820px){.strip{grid-template-columns:repeat(3,1fr)}
.strip .cell:nth-child(3n){border-right:0}
.strip .cell{border-bottom:1px solid var(--line)}}
.assess{display:flex;gap:34px;flex-wrap:wrap;align-items:center}
.stamp{flex:none;width:158px;height:158px;border:2px solid var(--acc);
display:flex;flex-direction:column;align-items:center;justify-content:center;
position:relative;transform:rotate(-2deg)}
.stamp:before{content:"";position:absolute;inset:5px;border:1px solid var(--acc-dim)}
.stamp .g{font-size:64px;font-weight:700;line-height:1;color:var(--acc)}
.stamp .s{font-family:var(--mono);font-size:11px;letter-spacing:.18em;
color:var(--dim);margin-top:6px}
.pillars{flex:1;min-width:260px}
.pillar{margin:13px 0}
.pillar .top{display:flex;justify-content:space-between;
font-family:var(--mono);font-size:11px;letter-spacing:.14em;color:var(--dim);
text-transform:uppercase;margin-bottom:6px}
.pillar .top b{color:var(--text)}
.seg{display:flex;gap:3px}
.seg span{height:9px;flex:1;background:var(--panel2);border:1px solid var(--line)}
.seg span.on{background:var(--acc);border-color:var(--acc);opacity:0;
transition:opacity .2s}
.risk{margin-top:14px;font-family:var(--mono);font-size:11.5px;
letter-spacing:.1em;color:var(--dim);text-transform:uppercase}
.risk b{color:var(--amber);border:1px solid var(--amber);padding:2px 10px;
margin-left:6px}
.risk.low b{color:var(--acc);border-color:var(--acc)}
.risk.high b{color:var(--red);border-color:var(--red)}
#heatmap{display:grid;grid-auto-flow:column;grid-template-rows:repeat(7,12px);
gap:3px;overflow-x:auto;padding-bottom:6px}
#heatmap .cell{width:12px;height:12px;background:var(--panel2);
border:1px solid var(--line);cursor:pointer;transition:transform .1s}
#heatmap .cell:hover{transform:scale(1.4);outline:1px solid var(--acc);z-index:2}
.hm-legend{display:flex;justify-content:flex-end;gap:4px;align-items:center;
font-family:var(--mono);font-size:9.5px;letter-spacing:.16em;color:var(--faint);
margin-top:8px;text-transform:uppercase}
.hm-legend i{width:11px;height:11px;display:inline-block;
border:1px solid var(--line)}
#hm-tip{position:fixed;pointer-events:none;display:none;z-index:60;
background:var(--panel2);border:1px solid var(--acc-dim);color:var(--text);
font-family:var(--mono);font-size:11px;padding:8px 12px;
box-shadow:0 10px 30px rgba(0,0,0,.5)}
#graph{width:100%;height:360px;display:block;background:var(--panel2);
cursor:crosshair}
.mat{display:flex;height:34px;border:1px solid var(--line);overflow:hidden}
.mat div{height:100%;transform:scaleX(0);transform-origin:left;
transition:transform 1.1s cubic-bezier(.22,1,.36,1)}
.mleg{margin-top:14px;display:flex;flex-wrap:wrap;gap:6px 22px}
.mleg span{font-family:var(--mono);font-size:11px;letter-spacing:.08em;
color:var(--dim)}
.mleg i{display:inline-block;width:9px;height:9px;margin-right:7px}
.afilters{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px}
.afilters button{background:transparent;border:1px solid var(--line2);
color:var(--dim);font-family:var(--mono);font-size:10px;letter-spacing:.2em;
padding:6px 15px;cursor:pointer;text-transform:uppercase}
.afilters button.on{color:var(--bg);background:var(--acc);border-color:var(--acc)}
.achgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));
gap:10px}
.ach{display:flex;gap:14px;align-items:flex-start;border:1px solid var(--line);
background:var(--panel2);padding:13px 15px}
.ach .glyph{font-size:20px;line-height:1;color:var(--acc);width:24px;flex:none;
text-align:center}
.ach .bd{flex:1;min-width:0}
.ach .nm{font-weight:700;font-size:13.5px;letter-spacing:.02em}
.ach .ds{font-size:11.5px;color:var(--dim);margin-top:3px;line-height:1.45}
.ach .rr{font-family:var(--mono);font-size:9px;letter-spacing:.24em;
color:var(--faint);margin-top:7px;text-transform:uppercase}
.ach .stamp2{flex:none;font-family:var(--mono);font-size:9px;letter-spacing:.2em;
color:var(--acc);border:1px solid var(--acc);padding:3px 8px;
transform:rotate(4deg);align-self:center}
.ach.locked{opacity:.45}
.ach.locked .glyph{color:var(--faint)}
.ach.locked .stamp2{color:var(--faint);border-color:var(--line2);transform:none}
.ach.r-legendary{border-color:var(--acc-dim)}
.ach.r-legendary .glyph{color:var(--amber)}
.tools{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}
.tools input,.tools select{background:var(--panel2);border:1px solid var(--line2);
color:var(--text);font-family:var(--mono);font-size:12px;padding:8px 12px;
outline:none}
.tools input{flex:1;min-width:180px}
.tools input:focus{border-color:var(--acc-dim)}
.tools select{cursor:pointer}
table{width:100%;border-collapse:collapse;font-family:var(--mono);font-size:12px}
th{font-weight:500;font-size:9.5px;letter-spacing:.22em;color:var(--faint);
text-transform:uppercase;text-align:left;padding:7px 10px;cursor:pointer;
border-bottom:1px solid var(--line2);user-select:none}
th:hover{color:var(--acc)}
td{padding:7px 10px;border-bottom:1px solid var(--line);color:var(--dim)}
td .t{color:var(--text)}
tr:hover td{background:var(--panel2)}
td .idx{color:var(--faint)}
td .st{font-size:10px;letter-spacing:.1em}
.st.M{color:var(--acc)}.st.O{color:var(--amber)}.st.C{color:var(--red)}
#fchart{width:100%;height:180px;display:block}
.fcrow{font-family:var(--mono);font-size:11.5px;letter-spacing:.06em;
color:var(--dim);margin-top:12px;text-transform:uppercase}
.fcrow b{color:var(--text)}
.reveal{opacity:0;transform:translateY(16px);transition:opacity .7s,transform .7s}
.reveal.in{opacity:1;transform:none}
footer{margin-top:46px;border-top:1px solid var(--line2);padding-top:16px;
display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px;
font-family:var(--mono);font-size:10px;letter-spacing:.2em;color:var(--faint);
text-transform:uppercase}
footer a{color:var(--dim);text-decoration:none}
footer a:hover{color:var(--acc)}
@media print{body:after,body:before{display:none}}
"""


def _js() -> str:
    return """
const D = window.__PRSNOOP__;
const $ = (q) => document.querySelector(q);
const $$ = (q) => Array.from(document.querySelectorAll(q));
const fmt = (n) => Number(n).toLocaleString('en-US');
$$('.panel').forEach((p) => {
  ['tl', 'tr', 'bl', 'br'].forEach((c) => {
    const i = document.createElement('i');
    i.className = c;
    p.appendChild(i);
  });
});
const HEAT = ['#0d1512', '#0e2b1d', '#14522f', '#1d8a45', '#3dffa2'];
const HEAT_L = ['#e2e7e0', '#b5e3c6', '#7fd6a2', '#37a86a', '#0b7a4b'];
$('#theme').onclick = () => {
  document.body.classList.toggle('light');
  const light = document.body.classList.contains('light');
  $$('#heatmap .cell').forEach((c) => {
    c.style.background = (light ? HEAT_L : HEAT)[+c.dataset.lvl];
  });
};
function countUp(el, target, suffix) {
  const dec = Number.isInteger(target) ? 0 : 1;
  const t0 = performance.now(), dur = 1500;
  (function tick(t) {
    const p = Math.min(1, (t - t0) / dur);
    const v = target * (1 - Math.pow(1 - p, 3));
    el.innerHTML = (dec
      ? v.toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
      : fmt(Math.round(v))) + (suffix ? '<small>' + suffix + '</small>' : '');
    if (p < 1) requestAnimationFrame(tick);
  })(performance.now());
}
[['h-prs', D.stats.prs, ''], ['h-merged', D.stats.merged, ''],
 ['h-rate', D.stats.rate, '%'], ['h-lines', D.stats.added, ''],
 ['h-streak', D.stats.streak, 'd'], ['h-repos', D.stats.repos, '']]
.forEach(([id, v, sfx]) => countUp(document.getElementById(id), v, sfx));
$('#g-grade').textContent = D.score.grade;
$('#g-band').textContent = D.score.band.toUpperCase() + ' · ' + D.score.total + ' / 100';
const PCOL = { output: '#58a6ff', impact: '#41d67c', consistency: '#f0b429',
               collaboration: '#b58cff', rhythm: '#ff7eb6' };
const pil = $('#pillars');
D.score.pillars.forEach((p, idx) => {
  const div = document.createElement('div');
  div.className = 'pillar';
  const segs = Array.from({ length: 20 }, (_, k) =>
    '<span class="' + (k < Math.round(p.score / 5) ? 'on' : '') + '"></span>').join('');
  div.innerHTML = '<div class="top"><span>' + String(idx + 1).padStart(2, '0') +
    ' · ' + p.name + '</span><b>' + p.score + '</b></div><div class="seg">' + segs + '</div>';
  pil.appendChild(div);
  div.querySelectorAll('.seg span.on').forEach((sp, k) => {
    sp.style.background = PCOL[p.name] || '#58a6ff';
    sp.style.borderColor = PCOL[p.name] || '#58a6ff';
    setTimeout(() => { sp.style.opacity = 1; }, 500 + idx * 120 + k * 45);
  });
});
$('#risk').innerHTML = 'burnout risk <b>' + D.score.risk.toUpperCase() + '</b>';
const hm = $('#heatmap'), tip = $('#hm-tip');
const lvl = (n) => n === 0 ? 0 : n <= 2 ? 1 : n <= 5 ? 2 : n <= 9 ? 3 : 4;
D.days.forEach((d) => {
  const c = document.createElement('div');
  c.className = 'cell';
  const total = d[1] + d[2] + d[3] + d[4];
  c.dataset.lvl = lvl(total);
  c.style.background = HEAT[lvl(total)];
  c.dataset.tip = d[0] + ' · ' + total + ' signals — ' + d[1] + ' pr / ' +
    d[2] + ' merged / ' + d[3] + ' issue / ' + d[4] + ' review';
  c.onmousemove = (ev) => {
    tip.style.display = 'block';
    tip.textContent = c.dataset.tip;
    tip.style.left = Math.min(ev.clientX + 14, innerWidth - 260) + 'px';
    tip.style.top = (ev.clientY + 16) + 'px';
  };
  c.onmouseleave = () => { tip.style.display = 'none'; };
  hm.appendChild(c);
});
const hleg = $('#hm-legend');
['less', '', '', '', 'more'].forEach((t, k) => {
  const i = document.createElement('i');
  i.style.background = HEAT[k];
  hleg.appendChild(i);
});
hleg.firstChild.insertAdjacentText('beforebegin', 'less ');
const cv = $('#graph'), ctx = cv.getContext('2d');
function sizeGraph() {
  cv.width = cv.clientWidth * devicePixelRatio;
  cv.height = cv.clientHeight * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
sizeGraph(); addEventListener('resize', sizeGraph);
const nodes = [{ id: 'you', label: D.user, r: 15, color: '#3dffa2' }];
const W = () => cv.clientWidth, H = () => cv.clientHeight;
nodes[0].x = W() / 2; nodes[0].y = H() / 2;
const maxRepo = Math.max(...D.repos.map((r) => r[1]), 1);
D.repos.slice(0, 12).forEach(([name, n], i) => {
  const ang = (i / Math.min(D.repos.length, 12)) * Math.PI * 2;
  nodes.push({ id: name, label: name, r: 6 + (n / maxRepo) * 15,
    x: W() / 2 + Math.cos(ang) * 140, y: H() / 2 + Math.sin(ang) * 100,
    color: '#41d67c' });
});
const edges = D.repos.slice(0, 12).map(([name]) => ['you', name]);
let drag = null, hoverN = null, alpha = 1;
const pos = (ev) => {
  const r = cv.getBoundingClientRect();
  return { x: ev.clientX - r.left, y: ev.clientY - r.top };
};
cv.onmousedown = (ev) => {
  const p = pos(ev);
  drag = nodes.find((n) => Math.hypot(n.x - p.x, n.y - p.y) < n.r + 10) || null;
  if (drag) drag._pin = true;
};
cv.onmousemove = (ev) => {
  const p = pos(ev);
  if (drag) { drag.x = p.x; drag.y = p.y; alpha = 0.7; }
  hoverN = nodes.find((n) => Math.hypot(n.x - p.x, n.y - p.y) < n.r + 8) || null;
  cv.style.cursor = drag ? 'grabbing'
    : hoverN && hoverN.id !== 'you' ? 'pointer' : 'crosshair';
};
addEventListener('mouseup', () => { if (drag) { drag._pin = false; drag = null; } });
function css(v) { return getComputedStyle(document.body).getPropertyValue(v); }
function physics() {
  if (alpha < 0.012) return;
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      const dist = Math.hypot(dx, dy) || 0.01;
      const rep = 2400 / (dist * dist);
      dx /= dist; dy /= dist;
      if (!a._pin && a.id !== 'you') { a.x -= dx * rep * alpha; a.y -= dy * rep * alpha; }
      if (!b._pin && b.id !== 'you') { b.x += dx * rep * alpha; b.y += dy * rep * alpha; }
    }
  }
  edges.forEach(([s, t]) => {
    const a = nodes.find((n) => n.id === s), b = nodes.find((n) => n.id === t);
    let dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.hypot(dx, dy) || 0.01;
    const f = (dist - 150) * 0.012 * alpha;
    dx /= dist; dy /= dist;
    if (!a._pin && a.id !== 'you') { a.x += dx * f; a.y += dy * f; }
    if (!b._pin && b.id !== 'you') { b.x -= dx * f; b.y -= dy * f; }
  });
  nodes.forEach((n) => {
    if (n.id === 'you') { n.x = W() / 2; n.y = H() / 2; return; }
    if (!n._pin) {
      n.x += (W() / 2 - n.x) * 0.004 * alpha;
      n.y += (H() / 2 - n.y) * 0.004 * alpha;
    }
  });
  alpha *= 0.995;
}
function drawGraph() {
  physics();
  ctx.clearRect(0, 0, W(), H());
  const cx = W() / 2, cy = H() / 2;
  ctx.strokeStyle = css('--line2'); ctx.lineWidth = 1;
  [55, 110, 165].forEach((r) => {
    ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
  });
  ctx.setLineDash([2, 5]);
  ctx.beginPath();
  ctx.moveTo(cx, 0); ctx.lineTo(cx, H());
  ctx.moveTo(0, cy); ctx.lineTo(W(), cy);
  ctx.stroke();
  ctx.setLineDash([]);
  edges.forEach(([s, t]) => {
    const a = nodes.find((n) => n.id === s), b = nodes.find((n) => n.id === t);
    ctx.strokeStyle = css('--line2'); ctx.lineWidth = 1;
    ctx.setLineDash([3, 4]);
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    ctx.setLineDash([]);
  });
  nodes.forEach((n) => {
    if (n.id === 'you') {
      ctx.strokeStyle = '#3dffa2'; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.arc(n.x, n.y, 20, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.arc(n.x, n.y, 11, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(n.x - 26, n.y); ctx.lineTo(n.x - 15, n.y);
      ctx.moveTo(n.x + 15, n.y); ctx.lineTo(n.x + 26, n.y);
      ctx.moveTo(n.x, n.y - 26); ctx.lineTo(n.x, n.y - 15);
      ctx.moveTo(n.x, n.y + 15); ctx.lineTo(n.x, n.y + 26);
      ctx.stroke();
    } else {
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
      ctx.fillStyle = css('--panel');
      ctx.fill(); ctx.strokeStyle = n.color; ctx.lineWidth = 1.6; ctx.stroke();
      ctx.beginPath(); ctx.arc(n.x, n.y, 2.5, 0, Math.PI * 2);
      ctx.fillStyle = n.color; ctx.fill();
    }
    ctx.fillStyle = n.id === 'you' ? '#3dffa2' : css('--dim');
    ctx.font = '10px IBM Plex Mono, monospace';
    ctx.textAlign = 'center';
    ctx.fillText(n.label.length > 22 ? n.label.slice(0, 21) + '…' : n.label,
                 n.x, n.y + n.r + 16);
  });
  if (hoverN && hoverN.id !== 'you') {
    const w = D.repos.find((r) => r[0] === hoverN.id);
    if (w) {
      tip.style.display = 'block';
      tip.textContent = 'TARGET ' + hoverN.id + ' · ' + w[1] + ' INTERCEPTS';
      tip.style.left = (hoverN.x + 20) + 'px';
      tip.style.top = (hoverN.y - 14) + 'px';
    }
  } else if (!drag) tip.style.display = 'none';
  requestAnimationFrame(drawGraph);
}
requestAnimationFrame(drawGraph);
const mat = $('#mat'), mleg = $('#mleg');
const MCOL = ['#3dffa2', '#41d67c', '#f0b429', '#b58cff', '#ff7eb6', '#2dd4bf', '#f4633a'];
const mtotal = D.languages.reduce((a, l) => a + l[1], 0) || 1;
D.languages.slice(0, 7).forEach(([lang, n], i) => {
  const d = document.createElement('div');
  d.style.cssText = 'width:' + (n / mtotal * 100).toFixed(2) +
    '%;background:' + MCOL[i];
  mat.appendChild(d);
  const sp = document.createElement('span');
  sp.innerHTML = '<i style="background:' + MCOL[i] + '"></i>' + lang +
    ' · ' + (n / mtotal * 100).toFixed(0) + '%';
  mleg.appendChild(sp);
});
setTimeout(() => {
  $$('#mat div').forEach((d, i) => {
    d.style.transitionDelay = (i * 90) + 'ms';
    d.style.transform = 'scaleX(1)';
  });
}, 400);
const GLYPH = { common: '◇', rare: '◆', epic: '✦', legendary: '★' };
let rarFilter = 'all';
function renderAch() {
  const grid = $('#achgrid');
  grid.innerHTML = '';
  D.achievements.filter((a) => rarFilter === 'all' || a.rarity === rarFilter)
    .forEach((a, i) => {
      const div = document.createElement('div');
      div.className = 'ach r-' + a.rarity + (a.unlocked ? '' : ' locked');
      div.style.opacity = 0;
      div.innerHTML = '<div class="glyph">' + GLYPH[a.rarity] + '</div>' +
        '<div class="bd"><div class="nm">' + a.name + '</div>' +
        '<div class="ds">' + a.description + '</div>' +
        '<div class="rr">' + a.rarity + ' · ' +
        (a.unlocked ? 'granted' : 'pending · ' + a.progress) + '</div></div>' +
        '<div class="stamp2">' + (a.unlocked ? 'granted' : 'pending') + '</div>';
      grid.appendChild(div);
      setTimeout(() => {
        div.style.transition = 'opacity .4s'; div.style.opacity = '';
      }, Math.min(i * 28, 600));
    });
}
renderAch();
$$('.afilters button').forEach((b) => {
  b.onclick = () => {
    $$('.afilters button').forEach((x) => x.classList.remove('on'));
    b.classList.add('on');
    rarFilter = b.dataset.f;
    renderAch();
  };
});
let sortKey = 'date', sortDir = -1, q = '', stFilter = 'all';
function renderPrs() {
  let rows = D.prs.filter((p) =>
    (stFilter === 'all' || p.state === stFilter) &&
    (!q || (p.title + ' ' + p.repo + ' ' + p.number).toLowerCase().includes(q)));
  rows.sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey];
    if (typeof va === 'number') return (va - vb) * sortDir;
    return String(va).localeCompare(String(vb)) * sortDir;
  });
  $('#prbody').innerHTML = rows.slice(0, 80).map((p, i) =>
    '<tr><td class="idx">' + String(i + 1).padStart(3, '0') + '</td>' +
    '<td>' + p.repo + '#' + p.number + '</td>' +
    '<td><span class="t">' + p.title + '</span></td>' +
    '<td><span class="st ' + p.state[0].toUpperCase() + '">[' +
    p.state[0].toUpperCase() + ']</span></td>' +
    '<td>+' + fmt(p.added) + '</td><td>-' + fmt(p.deleted) + '</td>' +
    '<td>' + p.date + '</td></tr>').join('')
    || '<tr><td colspan="7" style="color:var(--faint)">no intercepts match</td></tr>';
}
renderPrs();
$('#prq').oninput = (e) => { q = e.target.value.toLowerCase(); renderPrs(); };
$('#prst').onchange = (e) => { stFilter = e.target.value; renderPrs(); };
$$('#prtable th').forEach((th) => {
  th.onclick = () => {
    const k = th.dataset.k;
    if (!k) return;
    sortDir = (sortKey === k) ? -sortDir : -1;
    sortKey = k;
    renderPrs();
  };
});
const fc = $('#fchart'), fctx = fc.getContext('2d');
function sizeFc() {
  fc.width = fc.clientWidth * devicePixelRatio;
  fc.height = 180 * devicePixelRatio;
  fctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
sizeFc(); addEventListener('resize', sizeFc);
let fT = 0;
function drawFc() {
  const w = fc.clientWidth, h = 180;
  fctx.clearRect(0, 0, w, h);
  const days = D.days.slice(-45).map((d) => d[1] + d[2] + d[3] + d[4]);
  const peak = Math.max(...days, 1);
  const pad = 6, step = (w - pad * 2) / (days.length + 14);
  const pts = days.map((v, i) => [pad + i * step, h - 26 - (v / peak) * (h - 52)]);
  fctx.strokeStyle = css('--line');
  [0.25, 0.5, 0.75].forEach((fr) => {
    const y = 12 + (h - 46) * fr;
    fctx.beginPath(); fctx.moveTo(0, y); fctx.lineTo(w, y); fctx.stroke();
  });
  const draw = Math.floor(pts.length * Math.min(fT, 0.68) / 0.68);
  if (draw > 1) {
    fctx.beginPath();
    fctx.moveTo(pts[0][0], h - 26);
    pts.slice(0, draw).forEach(([x, y]) => fctx.lineTo(x, y));
    fctx.lineTo(pts[draw - 1][0], h - 26);
    fctx.closePath();
    fctx.fillStyle = 'rgba(61,255,162,.07)';
    fctx.fill();
  }
  fctx.strokeStyle = '#3dffa2'; fctx.lineWidth = 1.6;
  fctx.beginPath();
  pts.slice(0, Math.max(2, draw)).forEach(([x, y], i) => {
    if (i === 0) fctx.moveTo(x, y); else fctx.lineTo(x, y);
  });
  fctx.stroke();
  if (fT > 0.6) {
    const last = pts[pts.length - 1];
    const slope = D.forecast.perWeek / 7;
    const projPeak = Math.max(peak, slope * 14);
    const ex = last[0] + 14 * step;
    const ey = h - 26 - Math.max(0, slope * 14 / projPeak) * (h - 46);
    fctx.setLineDash([4, 5]);
    fctx.strokeStyle = '#f0b429'; fctx.lineWidth = 1.4;
    fctx.beginPath(); fctx.moveTo(last[0], last[1]); fctx.lineTo(ex, ey); fctx.stroke();
    fctx.setLineDash([]);
    fctx.fillStyle = '#f0b429';
    fctx.font = '9px IBM Plex Mono, monospace';
    fctx.fillText('PROJECTED →', ex - 74, ey - 8);
    fctx.strokeStyle = css('--line2');
    fctx.setLineDash([2, 4]);
    fctx.beginPath(); fctx.moveTo(last[0], 12); fctx.lineTo(last[0], h - 26); fctx.stroke();
    fctx.setLineDash([]);
  }
  if (fT < 1) { fT += 0.02; requestAnimationFrame(drawFc); }
}
setTimeout(drawFc, 500);
$('#fline').innerHTML =
  'trajectory <b>' + D.forecast.direction + '</b> · <b>' + D.forecast.perWeek +
  '</b> prs/week · ~<b>' + D.forecast.next30 + '</b> next 30d · ~<b>' +
  D.forecast.nextYear + '</b> next year · ' + D.forecast.confidence + ' confidence';
const revObs = new IntersectionObserver((es) => {
  es.forEach((e) => { if (e.isIntersecting) e.target.classList.add('in'); });
}, { threshold: 0.1 });
$$('.reveal').forEach((el) => revObs.observe(el));
"""


def render_showcase_html(activity: Activity) -> str:
    """The full interactive single-file app, dossier edition."""
    data = build_data(activity)
    payload = json.dumps(data, ensure_ascii=True).replace("</", "<\\/")
    user = x_escape(activity.user)
    page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PRSNOOP · DOSSIER: __USER__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>__CSS__</style></head><body>
<div class="wrap">
<div class="topbar">
  <span>PRSNOOP · FIELD DOSSIER · <span class="live">LIVE INTERCEPT</span></span>
  <button id="theme">invert</button>
</div>

<div class="subject">
  <p class="eyebrow">subject profile // clearance granted</p>
  <h1>__USER__</h1>
  <div class="dossier">
    <span>SURVEILLANCE WINDOW <b>__WINDOW__ DAYS</b></span>
    <span>DOSSIER COMPILED <b>__GEN__</b></span>
    <span>MOMENTUM <b>__MOMENTUM__</b></span>
    <span>CLEARANCE <b>__GRADE__</b></span>
  </div>
</div>

<div class="strip reveal">
  <div class="cell"><div class="idx">01</div><div class="v" id="h-prs">0</div><div class="lab">pull requests</div></div>
  <div class="cell"><div class="idx">02</div><div class="v" id="h-merged">0</div><div class="lab">merged</div></div>
  <div class="cell"><div class="idx">03</div><div class="v" id="h-rate">0</div><div class="lab">merge rate</div></div>
  <div class="cell"><div class="idx">04</div><div class="v" id="h-lines">0</div><div class="lab">lines added</div></div>
  <div class="cell"><div class="idx">05</div><div class="v" id="h-streak">0</div><div class="lab">best streak</div></div>
  <div class="cell"><div class="idx">06</div><div class="v" id="h-repos">0</div><div class="lab">repositories</div></div>
</div>

<div class="panel reveal"><h2><span><span class="no">01</span> · TARGET ASSESSMENT</span>
<span class="hint">five weighted pillars</span></h2>
<div class="assess">
  <div class="stamp"><div class="g" id="g-grade"></div>
  <div class="s" id="g-band"></div><div class="s" id="g-score"></div></div>
  <div class="pillars" id="pillars"></div>
</div>
<p class="risk" id="risk"></p></div>

<div class="panel reveal"><h2><span><span class="no">02</span> · DAILY INTERCEPTS</span>
<span class="hint">hover any day</span></h2>
<div id="heatmap"></div>
<div class="hm-legend" id="hm-legend"></div></div>

<div class="panel reveal"><h2><span><span class="no">03</span> · NETWORK MAP</span>
<span class="hint">drag the nodes · hover for counts</span></h2>
<canvas id="graph"></canvas></div>

<div class="panel reveal"><h2><span><span class="no">04</span> · MATERIAL ANALYSIS</span>
<span class="hint">languages by intercept volume</span></h2>
<div class="mat" id="mat"></div><div class="mleg" id="mleg"></div></div>

<div class="panel reveal"><h2><span><span class="no">05</span> · TRAJECTORY PROJECTION</span>
<span class="hint">least squares over the window</span></h2>
<canvas id="fchart"></canvas><p class="fcrow" id="fline"></p></div>

<div class="panel reveal"><h2><span><span class="no">06</span> · COMMENDATIONS · __ACHDONE__/__ACHTOTAL__ · __ACHSCORE__ PTS</span>
<span class="hint">filter by rarity</span></h2>
<div class="afilters">
<button class="on" data-f="all">all</button><button data-f="common">common</button>
<button data-f="rare">rare</button><button data-f="epic">epic</button>
<button data-f="legendary">legendary</button></div>
<div class="achgrid" id="achgrid"></div></div>

<div class="panel reveal"><h2><span><span class="no">07</span> · INTERCEPT LOG</span>
<span class="hint">search · filter · sort</span></h2>
<div class="tools"><input id="prq" placeholder="grep intercepts…">
<select id="prst"><option value="all">all states</option><option value="merged">merged</option>
<option value="open">open</option><option value="closed">closed</option></select></div>
<table id="prtable"><thead><tr>
<th data-k="repo">target</th><th data-k="title">transmission</th><th data-k="state">status</th>
<th data-k="added">+lines</th><th data-k="deleted">-lines</th><th data-k="date">date</th>
</tr></thead><tbody id="prbody"></tbody></table></div>

<footer>
<span>END OF DOSSIER</span>
<span><a href="https://github.com/MohammedAnasNathani/prsnoop">COMPILED BY PRSNOOP</a> · ZERO DEPENDENCIES · ALL DATA INTERCEPTED LOCALLY</span>
</footer>
</div>
<div id="hm-tip"></div>
<script>window.__PRSNOOP__ = __DATA__;</script>
<script>
__JS__
</script>
</body></html>
"""
    replacements = {
        "__USER__": user.upper(),
        "__CSS__": _CSS,
        "__DATA__": payload,
        "__JS__": _js(),
        "__WINDOW__": str(data["window"]),
        "__GEN__": str(data["generated"]),
        "__ACHDONE__": str(data["achDone"]),
        "__ACHTOTAL__": str(len(data["achievements"])),
        "__ACHSCORE__": str(data["achScore"]),
        "__MOMENTUM__": str(data["stats"]["momentum"] or "pending").upper(),
        "__GRADE__": "GRADE {} · {}/100".format(
            data["score"]["grade"], data["score"]["total"]),
    }
    for key, value in replacements.items():
        page = page.replace(key, value)
    return page
