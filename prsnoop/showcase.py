"""Showcase: generate a full interactive single-file web app.

This is the spectacle command. One HTML file containing:
- animated count-up hero stats
- an interactive GitHub-style contribution heatmap with hover tooltips
- a live force-directed graph of the user's repo network (canvas physics,
  drag nodes, hover labels)
- a language donut rendered on canvas
- an animated health-score gauge
- the achievement wall with rarity filters
- a PR explorer with live search, state filter, and column sorting
- a forecast chart that draws itself
- a dark/light theme toggle

No external assets, no network calls from the page: the data rides inside
the file as embedded JSON.
"""
from __future__ import annotations

import json
from datetime import date as date_cls
from datetime import timedelta

from prsnoop.achievements import build_report
from prsnoop.forecast import build_forecast
from prsnoop.models import Activity, JsonDict
from prsnoop.score import compute_score


def x_escape(text: str) -> str:
    from xml.sax.saxutils import escape

    return escape(text)


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
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0a0c10;--card:#12161d;--card2:#171c24;--edge:#242b36;--text:#e8edf4;
--dim:#8b95a5;--faint:#57616f;--green:#41d67c;--blue:#58a6ff;--amber:#f0b429;
--red:#f4633a;--purple:#b58cff;--pink:#ff7eb6}
body.light{--bg:#f6f7f9;--card:#ffffff;--card2:#f0f2f5;--edge:#dce0e6;
--text:#1a212b;--dim:#5a6572;--faint:#98a1ad}
body{background:var(--bg);color:var(--text);transition:background .35s,color .35s;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
min-height:100vh}
.wrap{max-width:1060px;margin:0 auto;padding:34px 22px 80px}
header{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px}
.logo{font-family:ui-monospace,Menlo,monospace;font-size:13px;letter-spacing:.2em;
color:var(--faint);text-transform:uppercase}
.logo b{color:var(--green)}
h1{font-size:clamp(30px,6vw,52px);letter-spacing:-1.5px;margin:18px 0 4px}
h1 .u{background:linear-gradient(90deg,var(--blue),var(--green));
-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--dim);margin-bottom:8px}
#theme{background:var(--card);border:1px solid var(--edge);color:var(--dim);
border-radius:20px;padding:7px 16px;cursor:pointer;font-size:13px}
#theme:hover{color:var(--text);border-color:var(--blue)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(148px,1fr));
gap:12px;margin:26px 0}
.stat{background:var(--card);border:1px solid var(--edge);border-radius:14px;
padding:16px 18px;position:relative;overflow:hidden}
.stat:after{content:"";position:absolute;inset:0;
background:linear-gradient(120deg,transparent 30%,rgba(88,166,255,.06) 50%,transparent 70%);
transform:translateX(-100%);animation:sheen 6s infinite}
@keyframes sheen{0%,60%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.stat .k{font-size:10.5px;letter-spacing:1.6px;text-transform:uppercase;color:var(--dim)}
.stat .v{font-size:30px;font-weight:800;margin-top:5px;
font-variant-numeric:tabular-nums}
.stat .v.g{color:var(--green)}.stat .v.b{color:var(--blue)}.stat .v.a{color:var(--amber)}
.card{background:var(--card);border:1px solid var(--edge);border-radius:16px;
padding:20px 22px;margin:16px 0}
.card h2{font-size:11.5px;letter-spacing:2px;text-transform:uppercase;
color:var(--dim);margin-bottom:14px;display:flex;justify-content:space-between;align-items:center}
.card h2 .hint{font-size:11px;letter-spacing:0;text-transform:none;color:var(--faint)}
.row2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:760px){.row2{grid-template-columns:1fr}}
/* score gauge */
.gaugewrap{display:flex;align-items:center;gap:26px;flex-wrap:wrap}
.gauge{position:relative;width:170px;height:170px;flex:none}
.gauge svg{transform:rotate(-90deg)}
.gauge .num{position:absolute;inset:0;display:flex;flex-direction:column;
align-items:center;justify-content:center}
.gauge .num b{font-size:44px;line-height:1}
.gauge .num span{font-size:11px;color:var(--dim);letter-spacing:1.5px;text-transform:uppercase}
.pillars{flex:1;min-width:230px}
.pillar{margin:9px 0}
.pillar .top{display:flex;justify-content:space-between;font-size:12.5px;
color:var(--dim);margin-bottom:4px}
.pillar .top b{color:var(--text)}
.pillar .track{height:7px;background:var(--card2);border-radius:4px;overflow:hidden}
.pillar .fill{height:100%;border-radius:4px;width:0;
transition:width 1.2s cubic-bezier(.22,1,.36,1)}
.risk{margin-top:12px;font-size:13px;color:var(--dim)}
.risk b{padding:2px 10px;border-radius:10px;font-size:12px}
.risk.low b{color:var(--green);border:1px solid var(--green)}
.risk.moderate b{color:var(--amber);border:1px solid var(--amber)}
.risk.high b{color:var(--red);border:1px solid var(--red)}
/* heatmap */
#heatmap{display:grid;grid-auto-flow:column;grid-template-rows:repeat(7,13px);
gap:3px;overflow-x:auto;padding-bottom:6px}
#heatmap .cell{width:13px;height:13px;border-radius:3px;background:var(--card2);
cursor:pointer;transition:transform .12s}
#heatmap .cell:hover{transform:scale(1.35);outline:1px solid var(--blue)}
#hm-tip{position:fixed;pointer-events:none;background:var(--card2);color:var(--text);
border:1px solid var(--edge);border-radius:8px;padding:7px 11px;font-size:12px;
display:none;z-index:9;box-shadow:0 6px 20px rgba(0,0,0,.4)}
/* achievements */
.filters{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.filters button{background:var(--card2);border:1px solid var(--edge);color:var(--dim);
padding:5px 14px;border-radius:16px;font-size:12px;cursor:pointer}
.filters button.on{color:var(--text);border-color:var(--blue)}
.achgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
.ach{border:1px solid var(--edge);border-radius:12px;padding:12px 14px;
background:var(--card2);cursor:default;transition:transform .15s}
.ach:hover{transform:translateY(-2px)}
.ach .ic{font-size:22px}
.ach .nm{font-weight:700;font-size:13.5px;margin:6px 0 2px}
.ach .ds{font-size:11.5px;color:var(--dim);line-height:1.4}
.ach .rr{font-size:10px;letter-spacing:1.2px;text-transform:uppercase;margin-top:7px}
.ach.locked{opacity:.42;filter:grayscale(.8)}
.r-common .rr{color:var(--dim)}.r-rare .rr{color:var(--blue)}
.r-epic .rr{color:var(--purple)}.r-legendary .rr{color:var(--amber)}
.ach.r-legendary:not(.locked){border-color:var(--amber);box-shadow:0 0 18px rgba(240,180,41,.15)}
/* pr explorer */
.tools{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.tools input,.tools select{background:var(--card2);border:1px solid var(--edge);
color:var(--text);border-radius:8px;padding:8px 12px;font-size:13px;outline:none}
.tools input{flex:1;min-width:180px}
.tools input:focus{border-color:var(--blue)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{color:var(--faint);font-size:11px;text-transform:uppercase;letter-spacing:1px;
text-align:left;padding:6px 10px;cursor:pointer;user-select:none}
th:hover{color:var(--text)}
td{padding:8px 10px;border-top:1px solid var(--edge)}
td .st{font-size:11px;padding:2px 9px;border-radius:10px}
.st.merged{color:var(--green);border:1px solid var(--green)}
.st.open{color:var(--amber);border:1px solid var(--amber)}
.st.closed{color:var(--red);border:1px solid var(--red)}
/* forecast */
.fcrow{display:flex;gap:26px;flex-wrap:wrap;margin-top:6px}
.fck{font-size:13px;color:var(--dim)}
.fck b{color:var(--text);font-size:17px}
/* footer */
footer{margin-top:34px;text-align:center;color:var(--faint);font-size:12px}
footer a{color:var(--blue);text-decoration:none}
.reveal{opacity:0;transform:translateY(18px);transition:opacity .7s,transform .7s}
.reveal.in{opacity:1;transform:none}
"""


def _js() -> str:
    # Plain string (no f-string) so JS braces survive untouched.
    return """
const D = window.__PRSNOOP__;
const $ = (q) => document.querySelector(q);
const fmt = (n) => n.toLocaleString('en-US');

/* ---------- theme ---------- */
function paintHeatmap() {
  const light = document.body.classList.contains('light');
  document.querySelectorAll('#heatmap .cell').forEach((c) => {
    c.style.background = (light ? LCOLS_L : LCOLS)[+c.dataset.lvl];
  });
}
$('#theme').onclick = () => {
  document.body.classList.toggle('light');
  paintHeatmap();
};

/* ---------- count-up hero ---------- */
function countUp(el, target, suffix) {
  const decimals = Number.isInteger(target) ? 0 : 1;
  const t0 = performance.now(), dur = 1400;
  function tick(t) {
    const p = Math.min(1, (t - t0) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    const val = target * eased;
    el.textContent = (decimals
      ? val.toLocaleString('en-US',
          { minimumFractionDigits: 1, maximumFractionDigits: 1 })
      : fmt(Math.round(val))) + (suffix || '');
    if (p < 1) requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}
const heroMap = [
  ['h-prs', D.stats.prs, ''], ['h-merged', D.stats.merged, ''],
  ['h-rate', D.stats.rate, '%'], ['h-lines', D.stats.added, ''],
  ['h-streak', D.stats.streak, 'd'], ['h-repos', D.stats.repos, ''],
];
const heroObs = new IntersectionObserver((es) => {
  es.forEach((e) => {
    if (!e.isIntersecting) return;
    heroObs.unobserve(e.target);
    const found = heroMap.find(([id]) => id === e.target.id);
    if (found) countUp(e.target, found[1], found[2]);
  });
}, { threshold: 0.4 });
heroMap.forEach(([id]) => heroObs.observe(document.getElementById(id)));

/* ---------- score gauge + pillars ---------- */
const R = 70, CIRC = 2 * Math.PI * R;
const g = $('#g-arc');
g.style.strokeDasharray = CIRC;
setTimeout(() => {
  g.style.transition = 'stroke-dashoffset 1.6s cubic-bezier(.22,1,.36,1)';
  g.style.strokeDashoffset = CIRC * (1 - D.score.total / 100);
}, 250);
$('#g-num').textContent = D.score.total;
$('#g-grade').textContent = 'grade ' + D.score.grade;
const COLORS = { output:'#58a6ff', impact:'#41d67c', consistency:'#f0b429',
                 collaboration:'#b58cff', rhythm:'#ff7eb6' };
const pil = $('#pillars');
D.score.pillars.forEach((p) => {
  const div = document.createElement('div');
  div.className = 'pillar';
  div.innerHTML = `<div class='top'><span>${p.name} · ${p.detail}</span><b>${p.score}</b></div>
    <div class='track'><div class='fill' style='background:${COLORS[p.name] || '#58a6ff'}'></div></div>`;
  pil.appendChild(div);
  setTimeout(() => { div.querySelector('.fill').style.width = p.score + '%'; }, 350);
});
$('#risk').innerHTML = `burnout risk: <b>${D.score.risk}</b>`;

/* ---------- heatmap ---------- */
const hm = $('#heatmap'), tip = $('#hm-tip');
const lvl = (n) => n === 0 ? 0 : n <= 2 ? 1 : n <= 5 ? 2 : n <= 9 ? 3 : 4;
const LCOLS = ['#242b36','#0e4429','#166a38','#2ea043','#56d364'];
const LCOLS_L = ['#e7eaef','#9be3b0','#57cb82','#2ea043','#1a5c33'];
D.days.forEach((d) => {
  const c = document.createElement('div');
  c.className = 'cell';
  const total = d[1] + d[2] + d[3] + d[4];
  c.dataset.lvl = lvl(total);
  c.style.background = LCOLS[lvl(total)];
  c.dataset.tip = `${d[0]} · ${total} item${total === 1 ? '' : 's'} (${d[1]} pr, ${d[2]} merged, ${d[3]} issue, ${d[4]} review)`;
  c.onmousemove = (ev) => {
    tip.style.display = 'block';
    tip.textContent = c.dataset.tip;
    tip.style.left = (ev.clientX + 14) + 'px';
    tip.style.top = (ev.clientY + 14) + 'px';
  };
  c.onmouseleave = () => { tip.style.display = 'none'; };
  hm.appendChild(c);
});
/* ---------- force graph ---------- */
const cv = $('#graph'), ctx = cv.getContext('2d');
function sizeCanvas() {
  cv.width = cv.clientWidth * devicePixelRatio;
  cv.height = cv.clientHeight * devicePixelRatio;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
sizeCanvas();
addEventListener('resize', sizeCanvas);
const nodes = [{ id: 'you', label: D.user, r: 16, x: 0, y: 0, fixed: false, color: '#58a6ff' }];
const W = () => cv.clientWidth, H = () => cv.clientHeight;
nodes[0].x = W() / 2; nodes[0].y = H() / 2;
const maxRepo = Math.max(...D.repos.map((r) => r[1]), 1);
D.repos.slice(0, 12).forEach(([name, n], i) => {
  const ang = (i / Math.min(D.repos.length, 12)) * Math.PI * 2;
  nodes.push({ id: name, label: name, r: 7 + (n / maxRepo) * 16,
    x: W() / 2 + Math.cos(ang) * 130, y: H() / 2 + Math.sin(ang) * 90,
    color: '#41d67c' });
});
const edges = D.repos.slice(0, 12).map(([name]) => ['you', name]);
let drag = null, hover = null, alpha = 1;
function pos(ev) {
  const r = cv.getBoundingClientRect();
  return { x: ev.clientX - r.left, y: ev.clientY - r.top };
}
cv.onmousedown = (ev) => {
  const p = pos(ev);
  drag = nodes.find((n) => Math.hypot(n.x - p.x, n.y - p.y) < n.r + 8) || null;
  if (drag) drag._pin = true;
};
cv.onmousemove = (ev) => {
  const p = pos(ev);
  if (drag) { drag.x = p.x; drag.y = p.y; alpha = 0.6; }
  hover = nodes.find((n) => Math.hypot(n.x - p.x, n.y - p.y) < n.r + 6) || null;
  cv.style.cursor = drag ? 'grabbing' : hover ? 'pointer' : 'default';
};
addEventListener('mouseup', () => { if (drag) { drag._pin = false; drag = null; } });
function physics() {
  if (alpha < 0.012) return;
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      let dist = Math.hypot(dx, dy) || 0.01;
      let rep = 2600 / (dist * dist);
      dx /= dist; dy /= dist;
      if (!a._pin && a.id !== 'you') { a.x -= dx * rep * alpha; a.y -= dy * rep * alpha; }
      if (!b._pin && b.id !== 'you') { b.x += dx * rep * alpha; b.y += dy * rep * alpha; }
    }
  }
  edges.forEach(([s, t]) => {
    const a = nodes.find((n) => n.id === s), b = nodes.find((n) => n.id === t);
    let dx = b.x - a.x, dy = b.y - a.y;
    const dist = Math.hypot(dx, dy) || 0.01;
    const want = 150;
    const f = (dist - want) * 0.012 * alpha;
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
  ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue('--edge');
  edges.forEach(([s, t]) => {
    const a = nodes.find((n) => n.id === s), b = nodes.find((n) => n.id === t);
    ctx.lineWidth = 1.4;
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
  });
  nodes.forEach((n) => {
    ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
    ctx.fillStyle = n.color; ctx.fill();
    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--text');
    ctx.font = (n.id === 'you' ? 'bold ' : '') + '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(n.label.length > 24 ? n.label.slice(0, 23) + '…' : n.label,
                 n.x, n.y + n.r + 15);
  });
  if (hover && hover.id !== 'you') {
    const weight = D.repos.find((r) => r[0] === hover.id);
    if (weight) {
      tip.style.display = 'block';
      tip.textContent = hover.id + ' · ' + weight[1] + ' PRs';
    }
  } else if (!drag) { tip.style.display = 'none'; }
  requestAnimationFrame(drawGraph);
}
requestAnimationFrame(drawGraph);

/* ---------- languages donut ---------- */
const dc = $('#donut'), dctx = dc.getContext('2d');
function sizeDonut() {
  const s = Math.min(dc.clientWidth, 210);
  dc.width = s * devicePixelRatio; dc.height = s * devicePixelRatio;
  dc.style.height = s + 'px';
  dctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
sizeDonut(); addEventListener('resize', sizeDonut);
const DCOL = ['#58a6ff','#41d67c','#f0b429','#b58cff','#ff7eb6','#2dd4bf','#f4633a'];
let donutT = 0;
function drawDonut() {
  const s = Math.min(dc.clientWidth, 210), cx = s / 2, cy = s / 2, r = s / 2 - 12;
  dctx.clearRect(0, 0, s, s);
  const total = D.languages.reduce((a, l) => a + l[1], 0) || 1;
  let a0 = -Math.PI / 2;
  D.languages.forEach(([lang, n], i) => {
    const frac = (n / total) * Math.min(donutT, 1);
    const a1 = a0 + frac * Math.PI * 2;
    dctx.beginPath();
    dctx.arc(cx, cy, r, a0, a1);
    dctx.strokeStyle = DCOL[i % DCOL.length];
    dctx.lineWidth = 26; dctx.stroke();
    a0 = a1;
  });
  dctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--text');
  dctx.font = 'bold 20px sans-serif'; dctx.textAlign = 'center';
  dctx.fillText(D.stats.langs, cx, cy - 2);
  dctx.font = '10px sans-serif';
  dctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--dim');
  dctx.fillText('languages', cx, cy + 16);
  if (donutT < 1) { donutT += 0.03; requestAnimationFrame(drawDonut); }
}
setTimeout(drawDonut, 300);
const legend = $('#dlegend');
D.languages.slice(0, 7).forEach(([lang, n], i) => {
  const sp = document.createElement('span');
  sp.style.cssText = `display:inline-block;margin:3px 10px;font-size:12.5px;color:var(--dim)`;
  sp.innerHTML = `<span style="color:${DCOL[i % DCOL.length]}">■</span> ${lang} (${n})`;
  legend.appendChild(sp);
});

/* ---------- achievements ---------- */
const grid = $('#achgrid');
let rarFilter = 'all';
function renderAch() {
  grid.innerHTML = '';
  D.achievements.filter((a) => rarFilter === 'all' || a.rarity === rarFilter)
   .forEach((a) => {
    const div = document.createElement('div');
    div.className = `ach r-${a.rarity}` + (a.unlocked ? '' : ' locked');
    div.innerHTML = `<div class="ic">${a.icon}</div><div class="nm">${a.name}</div>
      <div class="ds">${a.description}</div>
      <div class="rr">${a.rarity} · ${a.unlocked ? 'unlocked' : a.progress}</div>`;
    grid.appendChild(div);
  });
}
renderAch();
document.querySelectorAll('.filters button').forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll('.filters button').forEach((x) => x.classList.remove('on'));
    b.classList.add('on');
    rarFilter = b.dataset.f;
    renderAch();
  };
});

/* ---------- pr explorer ---------- */
const tbl = $('#prbody');
let sortKey = 'date', sortDir = -1, q = '', stFilter = 'all';
function renderPrs() {
  let rows = D.prs.filter((p) =>
    (stFilter === 'all' || p.state === stFilter) &&
    (!q || (p.title + ' ' + p.repo + '#' + p.number).toLowerCase().includes(q)));
  rows.sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey];
    if (typeof va === 'number') return (va - vb) * sortDir;
    return String(va).localeCompare(String(vb)) * sortDir;
  });
  tbl.innerHTML = rows.slice(0, 80).map((p) =>
    `<tr><td>${p.repo}#${p.number}</td><td>${p.title}</td>
     <td><span class="st ${p.state}">${p.state}</span></td>
     <td style="color:var(--green)">+${fmt(p.added)}</td>
     <td style="color:var(--red)">-${fmt(p.deleted)}</td>
     <td>${p.date}</td></tr>`).join('')
    || '<tr><td colspan="6" style="color:var(--dim)">no matches</td></tr>';
}
renderPrs();
$('#prq').oninput = (e) => { q = e.target.value.toLowerCase(); renderPrs(); };
$('#prst').onchange = (e) => { stFilter = e.target.value; renderPrs(); };
document.querySelectorAll('#prtable th').forEach((th) => {
  th.onclick = () => {
    const k = th.dataset.k;
    if (!k) return;
    sortDir = (sortKey === k) ? -sortDir : -1;
    sortKey = k;
    renderPrs();
  };
});

/* ---------- forecast chart ---------- */
const fc = $('#fchart'), fctx = fc.getContext('2d');
function sizeFc() {
  fc.width = fc.clientWidth * devicePixelRatio;
  fc.height = 170 * devicePixelRatio;
  fctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
}
sizeFc(); addEventListener('resize', sizeFc);
let fT = 0;
function drawFc() {
  const w = fc.clientWidth, h = 170;
  fctx.clearRect(0, 0, w, h);
  const days = D.days.slice(-45).map((d) => d[1] + d[2] + d[3] + d[4]);
  const peak = Math.max(...days, 1);
  const pad = 8, step = (w - pad * 2) / (days.length + 14);
  const pts = days.map((v, i) => [pad + i * step, h - 24 - (v / peak) * (h - 46)]);
  const draw = Math.floor(pts.length * Math.min(fT, 0.68) / 0.68);
  fctx.strokeStyle = '#58a6ff'; fctx.lineWidth = 2; fctx.beginPath();
  pts.slice(0, Math.max(2, draw)).forEach(([x, y], i) => {
    if (i === 0) fctx.moveTo(x, y); else fctx.lineTo(x, y);
  });
  fctx.stroke();
  if (fT > 0.6) {
    const last = pts[pts.length - 1];
    const slope = (D.forecast.perWeek / 7);
    const projPeak = Math.max(peak, slope * 14);
    fctx.setLineDash([5, 5]);
    fctx.strokeStyle = '#41d67c';
    fctx.beginPath();
    fctx.moveTo(last[0], last[1]);
    fctx.lineTo(last[0] + 14 * step, h - 24 - (slope * 14 / projPeak) * (h - 46));
    fctx.stroke();
    fctx.setLineDash([]);
    fctx.fillStyle = '#41d67c';
    fctx.font = '11px sans-serif';
    fctx.fillText('projected', last[0] + 14 * step - 52, h - 34 - (slope * 14 / projPeak) * (h - 46));
  }
  if (fT < 1) { fT += 0.02; requestAnimationFrame(drawFc); }
}
setTimeout(drawFc, 500);
$('#fline').innerHTML =
  `trend <b>${D.forecast.direction}</b> · <b>${D.forecast.perWeek}</b> prs/week · ` +
  `~<b>${D.forecast.next30}</b> next 30d · ~<b>${D.forecast.nextYear}</b> next year ` +
  `(${D.forecast.confidence} confidence)`;

/* ---------- reveal on scroll ---------- */
const revObs = new IntersectionObserver((es) => {
  es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('in'); } });
}, { threshold: 0.12 });
document.querySelectorAll('.reveal').forEach((el) => revObs.observe(el));
"""


def render_showcase_html(activity: Activity) -> str:
    """The full interactive single-file app."""
    data = build_data(activity)
    payload = json.dumps(data, ensure_ascii=True).replace("</", "<\\/")
    user = x_escape(activity.user)
    page = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>prsnoop showcase: __USER__</title><style>__CSS__</style></head><body>
<div class="wrap">
<header>
  <div class="logo">prsnoop <b>showcase</b></div>
  <button id="theme">◐ theme</button>
</header>
<h1><span class="u">__USER__</span>'s contribution universe</h1>
<p class="sub">window: last __WINDOW__ days · generated __GEN__ · every pixel computed locally</p>
<div class="grid">
  <div class="stat reveal"><div class="k">pull requests</div><div class="v b" id="h-prs">0</div></div>
  <div class="stat reveal"><div class="k">merged</div><div class="v g" id="h-merged">0</div></div>
  <div class="stat reveal"><div class="k">merge rate</div><div class="v a" id="h-rate">0</div></div>
  <div class="stat reveal"><div class="k">lines added</div><div class="v g" id="h-lines">0</div></div>
  <div class="stat reveal"><div class="k">best streak</div><div class="v b" id="h-streak">0</div></div>
  <div class="stat reveal"><div class="k">repositories</div><div class="v" id="h-repos">0</div></div>
</div>

<div class="card reveal"><h2>health score <span class="hint">five weighted pillars</span></h2>
<div class="gaugewrap">
  <div class="gauge">
    <svg width="170" height="170" viewBox="0 0 170 170">
      <circle cx="85" cy="85" r="70" fill="none" stroke="var(--card2)" stroke-width="13"/>
      <circle id="g-arc" cx="85" cy="85" r="70" fill="none" stroke="#41d67c"
              stroke-width="13" stroke-linecap="round"/>
    </svg>
    <div class="num"><b id="g-num">0</b><span id="g-grade"></span></div>
  </div>
  <div class="pillars" id="pillars"></div>
</div>
<p class="risk" id="risk"></p></div>

<div class="card reveal"><h2>activity heatmap <span class="hint">hover any day</span></h2>
<div id="heatmap"></div></div>

<div class="card reveal"><h2>contribution graph <span class="hint">drag the nodes · hover for counts</span></h2>
<canvas id="graph" style="width:100%;height:340px"></canvas></div>

<div class="row2">
<div class="card reveal"><h2>languages</h2><canvas id="donut" style="width:100%"></canvas>
<div id="dlegend" style="text-align:center;margin-top:8px"></div></div>
<div class="card reveal"><h2>forecast <span class="hint">least squares over the window</span></h2>
<canvas id="fchart" style="width:100%;height:170px"></canvas>
<p class="fcrow" id="fline"></p></div>
</div>

<div class="card reveal"><h2>achievements · __ACHDONE__/__ACHTOTAL__ · __ACHSCORE__ pts
<span class="hint">filter by rarity</span></h2>
<div class="filters">
<button class="on" data-f="all">all</button><button data-f="common">common</button>
<button data-f="rare">rare</button><button data-f="epic">epic</button>
<button data-f="legendary">legendary</button></div>
<div class="achgrid" id="achgrid"></div></div>

<div class="card reveal"><h2>pull request explorer <span class="hint">search · filter · click headers to sort</span></h2>
<div class="tools"><input id="prq" placeholder="search title or repo…">
<select id="prst"><option value="all">all states</option><option value="merged">merged</option>
<option value="open">open</option><option value="closed">closed</option></select></div>
<table id="prtable"><thead><tr>
<th data-k="repo">repo</th><th data-k="title">title</th><th data-k="state">state</th>
<th data-k="added">+lines</th><th data-k="deleted">-lines</th><th data-k="date">date</th>
</tr></thead><tbody id="prbody"></tbody></table></div>

<footer>generated by <a href="https://github.com/MohammedAnasNathani/prsnoop">prsnoop</a>
· one file · zero external assets · all computation happened on the machine that made this page</footer>
</div>
<div id="hm-tip"></div>
<script>window.__PRSNOOP__ = __DATA__;</script>
<script>
__JS__
</script>
</body></html>
"""
    replacements = {
        "__USER__": user,
        "__CSS__": _CSS,
        "__DATA__": payload,
        "__JS__": _js(),
        "__WINDOW__": str(data["window"]),
        "__GEN__": str(data["generated"]),
        "__ACHDONE__": str(data["achDone"]),
        "__ACHTOTAL__": str(len(data["achievements"])),
        "__ACHSCORE__": str(data["achScore"]),
    }
    for key, value in replacements.items():
        page = page.replace(key, value)
    return page
