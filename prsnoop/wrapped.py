"""prsnoop wrapped: a year of contributions as a set of superlatives.

The wrapped report answers the questions a profile page never asks: what
was the biggest patch, which month caught fire, how long did the longest
streak run, which repo got the most work. Everything derives from one
Activity snapshot, so it is deterministic and offline-testable.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from prsnoop.models import Activity, JsonDict, PRRecord


@dataclass(slots=True)
class Wrapped:
    """Superlatives over one Activity snapshot (usually a full year)."""

    user: str
    generated_at: datetime
    window_days: int
    since: str
    until: str
    prs: int = 0
    merged: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    reviews: int = 0
    issues: int = 0
    repos: int = 0
    languages: int = 0
    longest_streak_days: int = 0
    active_days: int = 0
    pr_cadence_days: float | None = None  # average days between PRs
    busiest_month: str | None = None
    busiest_month_count: int = 0
    top_repo: str | None = None
    top_repo_count: int = 0
    top_language: str | None = None
    top_language_count: int = 0
    biggest_pr_title: str | None = None
    biggest_pr_lines: int = 0
    biggest_pr_url: str | None = None
    longest_pr_title: str | None = None
    longest_pr_chars: int = 0
    favorite_weekday: str | None = None
    open_standing: int = 0  # PRs still open at snapshot time
    fastest_pr_title: str | None = None
    fastest_pr_days: float | None = None
    fastest_pr_url: str | None = None
    slowest_pr_title: str | None = None
    slowest_pr_days: float | None = None
    slowest_pr_url: str | None = None
    hottest_pr_title: str | None = None
    hottest_pr_comments: int = 0
    hottest_pr_url: str | None = None

    def to_dict(self) -> JsonDict:
        return {
            "user": self.user,
            "window_days": self.window_days,
            "since": self.since,
            "until": self.until,
            "prs": self.prs,
            "merged": self.merged,
            "lines_added": self.lines_added,
            "lines_deleted": self.lines_deleted,
            "reviews": self.reviews,
            "issues": self.issues,
            "repos": self.repos,
            "languages": self.languages,
            "longest_streak_days": self.longest_streak_days,
            "active_days": self.active_days,
            "pr_cadence_days": self.pr_cadence_days,
            "busiest_month": self.busiest_month,
            "busiest_month_count": self.busiest_month_count,
            "top_repo": self.top_repo,
            "top_repo_count": self.top_repo_count,
            "top_language": self.top_language,
            "top_language_count": self.top_language_count,
            "biggest_pr_title": self.biggest_pr_title,
            "biggest_pr_lines": self.biggest_pr_lines,
            "biggest_pr_url": self.biggest_pr_url,
            "longest_pr_title": self.longest_pr_title,
            "longest_pr_chars": self.longest_pr_chars,
            "favorite_weekday": self.favorite_weekday,
            "open_standing": self.open_standing,
            "fastest_pr_title": self.fastest_pr_title,
            "fastest_pr_days": self.fastest_pr_days,
            "fastest_pr_url": self.fastest_pr_url,
            "slowest_pr_title": self.slowest_pr_title,
            "slowest_pr_days": self.slowest_pr_days,
            "slowest_pr_url": self.slowest_pr_url,
            "hottest_pr_title": self.hottest_pr_title,
            "hottest_pr_comments": self.hottest_pr_comments,
            "hottest_pr_url": self.hottest_pr_url,
        }


_WEEKDAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
)


def build_wrapped(activity: Activity) -> Wrapped:
    """Derive every superlative from one Activity snapshot."""
    s = activity.stats
    prs = activity.prs
    merged = [p for p in prs if p.state == "merged"]

    months: Counter[str] = Counter()
    for da in s.day_activity:
        months[da.date[:7]] += da.total
    busiest_month, busiest_count = ("", 0)
    if months:
        busiest_month, busiest_count = months.most_common(1)[0]

    repo_counts: Counter[str] = Counter(p.repo for p in prs)
    lang_counts: Counter[str] = Counter(
        (p.language or "Unknown") for p in prs
    )
    weekday_counts: Counter[str] = Counter(
        p.created_at.strftime("%A") for p in prs
    )

    biggest: PRRecord | None = None
    longest: PRRecord | None = None
    for p in prs:
        if biggest is None or (p.additions + p.deletions) > (
            biggest.additions + biggest.deletions
        ):
            biggest = p
        if longest is None or len(p.title) > len(longest.title):
            longest = p

    # Merge-speed and discussion records: only merged PRs have a merge
    # time, only commented PRs count as discussed.
    fastest: PRRecord | None = None
    slowest: PRRecord | None = None
    for p in merged:
        d = p.days_to_merge
        if d is None:
            continue
        if fastest is None or d < (fastest.days_to_merge or d):
            fastest = p
        if slowest is None or d > (slowest.days_to_merge or d):
            slowest = p
    hottest: PRRecord | None = None
    for p in prs:
        if p.comments <= 0:
            continue
        if hottest is None or p.comments > hottest.comments:
            hottest = p

    cadence: float | None = None
    if len(prs) >= 2:
        span = (
            max(p.created_at for p in prs) - min(p.created_at for p in prs)
        ).total_seconds()
        cadence = round(span / 86400.0 / (len(prs) - 1), 1)

    return Wrapped(
        user=activity.user,
        generated_at=activity.generated_at,
        window_days=s.window_days,
        since=s.since,
        until=s.until,
        prs=len(prs),
        merged=len(merged),
        lines_added=s.lines_added,
        lines_deleted=s.lines_deleted,
        reviews=s.reviews_given,
        issues=s.issues_opened,
        repos=s.distinct_repos,
        languages=s.distinct_languages,
        longest_streak_days=s.longest_streak_days,
        active_days=s.active_days,
        pr_cadence_days=cadence,
        busiest_month=busiest_month or None,
        busiest_month_count=busiest_count,
        top_repo=repo_counts.most_common(1)[0][0] if repo_counts else None,
        top_repo_count=repo_counts.most_common(1)[0][1] if repo_counts else 0,
        top_language=lang_counts.most_common(1)[0][0] if lang_counts else None,
        top_language_count=lang_counts.most_common(1)[0][1] if lang_counts else 0,
        biggest_pr_title=biggest.title if biggest else None,
        biggest_pr_lines=(
            biggest.additions + biggest.deletions if biggest else 0
        ),
        biggest_pr_url=biggest.url if biggest else None,
        longest_pr_title=longest.title if longest else None,
        longest_pr_chars=len(longest.title) if longest else 0,
        favorite_weekday=(
            weekday_counts.most_common(1)[0][0] if weekday_counts else None
        ),
        open_standing=s.prs_open,
        fastest_pr_title=fastest.title if fastest else None,
        fastest_pr_days=(
            round(fastest.days_to_merge, 2)
            if fastest and fastest.days_to_merge is not None
            else None
        ),
        fastest_pr_url=fastest.url if fastest else None,
        slowest_pr_title=slowest.title if slowest else None,
        slowest_pr_days=(
            round(slowest.days_to_merge, 2)
            if slowest and slowest.days_to_merge is not None
            else None
        ),
        slowest_pr_url=slowest.url if slowest else None,
        hottest_pr_title=hottest.title if hottest else None,
        hottest_pr_comments=hottest.comments if hottest else 0,
        hottest_pr_url=hottest.url if hottest else None,
    )


def render_wrapped_table(w: Wrapped) -> str:
    """The big terminal reveal."""
    since = w.since or f"last {w.window_days} days"
    lines = [
        f"prsnoop wrapped | {w.user}",
        f"window: {since}" + (f" to {w.until}" if w.until else ""),
        "",
        "  THE YEAR IN PULL REQUESTS",
        "",
        f"  Pull requests      {w.prs} (merged {w.merged},"
        f" {w.open_standing} still open)",
        f"  Lines changed      +{w.lines_added:,} / -{w.lines_deleted:,}",
        f"  Reviews given      {w.reviews}",
        f"  Issues opened      {w.issues}",
        "",
        f"  Longest streak     {w.longest_streak_days} days",
        f"  Active days        {w.active_days}",
    ]
    if w.pr_cadence_days is not None:
        lines.append(
            f"  Cadence            one PR every {w.pr_cadence_days} days"
        )
    if w.busiest_month:
        lines.append(
            f"  Busiest month      {w.busiest_month} ({w.busiest_month_count} items)"
        )
    if w.top_repo:
        lines.append(f"  Busiest repo       {w.top_repo} ({w.top_repo_count} PRs)")
    if w.top_language:
        lines.append(
            f"  Top language       {w.top_language} ({w.top_language_count} PRs)"
        )
    if w.biggest_pr_title:
        lines.append(
            f"  Biggest patch      {w.biggest_pr_lines:,} lines,"
            f' "{w.biggest_pr_title[:44]}"'
        )
    if w.favorite_weekday:
        lines.append(f"  Favorite day       {w.favorite_weekday}")
    if w.fastest_pr_title and w.fastest_pr_days is not None:
        lines.append(
            f"  Fastest merge      {w.fastest_pr_days:.1f}d,"
            f' "{w.fastest_pr_title[:40]}"'
        )
    if w.slowest_pr_title and w.slowest_pr_days is not None:
        lines.append(
            f"  Slowest merge      {w.slowest_pr_days:.1f}d,"
            f' "{w.slowest_pr_title[:40]}"'
        )
    if w.hottest_pr_title:
        lines.append(
            f"  Most discussed     {w.hottest_pr_comments} comments,"
            f' "{w.hottest_pr_title[:36]}"'
        )
    lines += [
        "",
        f"  across {w.repos} repos and {w.languages} languages",
    ]
    return "\n".join(lines)


def render_wrapped_markdown(w: Wrapped) -> str:
    """Wrapped as a shareable Markdown page."""
    since = w.since or f"last {w.window_days} days"
    out = [
        f"# Wrapped: {w.user}",
        "",
        f"_Generated by [prsnoop](https://github.com/MohammedAnasNathani/prsnoop)"
        f" | window: {since}" + (f" to {w.until}" if w.until else "") + "_",
        "",
        "| Superlative | Value |",
        "|---|---|",
        f"| Pull requests | {w.prs} ({w.merged} merged) |",
        f"| Lines changed | +{w.lines_added:,} / -{w.lines_deleted:,} |",
        f"| Reviews given | {w.reviews} |",
        f"| Issues opened | {w.issues} |",
        f"| Longest streak | {w.longest_streak_days} days |",
        f"| Active days | {w.active_days} |",
    ]
    if w.pr_cadence_days is not None:
        out.append(f"| Cadence | one PR every {w.pr_cadence_days} days |")
    if w.busiest_month:
        out.append(
            f"| Busiest month | {w.busiest_month} ({w.busiest_month_count} items) |"
        )
    if w.top_repo:
        out.append(
            f"| Busiest repo | [{w.top_repo}](https://github.com/{w.top_repo})"
            f" ({w.top_repo_count} PRs) |"
        )
    if w.top_language:
        out.append(f"| Top language | {w.top_language} ({w.top_language_count} PRs) |")
    if w.biggest_pr_title:
        title = w.biggest_pr_title.replace("|", "\\|")
        link = (
            f"[{title}]({w.biggest_pr_url})" if w.biggest_pr_url else title
        )
        out.append(f"| Biggest patch | {w.biggest_pr_lines:,} lines, {link} |")
    if w.favorite_weekday:
        out.append(f"| Favorite day | {w.favorite_weekday} |")
    if w.fastest_pr_title and w.fastest_pr_days is not None:
        title = w.fastest_pr_title.replace("|", "\\|")
        link = f"[{title}]({w.fastest_pr_url})" if w.fastest_pr_url else title
        out.append(f"| Fastest merge | {w.fastest_pr_days:.1f} days, {link} |")
    if w.slowest_pr_title and w.slowest_pr_days is not None:
        title = w.slowest_pr_title.replace("|", "\\|")
        link = f"[{title}]({w.slowest_pr_url})" if w.slowest_pr_url else title
        out.append(f"| Slowest merge | {w.slowest_pr_days:.1f} days, {link} |")
    if w.hottest_pr_title:
        title = w.hottest_pr_title.replace("|", "\\|")
        link = f"[{title}]({w.hottest_pr_url})" if w.hottest_pr_url else title
        out.append(f"| Most discussed | {w.hottest_pr_comments} comments, {link} |")
    out += ["", f"Across **{w.repos} repos** and **{w.languages} languages**.", ""]
    return "\n".join(out)

# ------------------------------------------------------------------ story web


def render_wrapped_story(w: Wrapped) -> str:
    """Wrapped as a surveillance-broadcast story: vertical slides,
    auto-advance, dossier styling. One file."""
    slides = [
        ("intercepting your year", w.user.upper(), "stand by",
         "var(--acc)"),
        ("pull requests opened", str(w.prs), "in the window", "var(--text)"),
        ("merged clean", str(w.merged), "landed on main", "var(--acc)"),
        ("lines shipped", "+" + f"{w.lines_added:,}", "by your own hand", "var(--text)"),
        ("longest streak", str(w.longest_streak_days) + " days",
         "back to back", "var(--acc)"),
    ]
    if w.busiest_month:
        slides.append(("hottest month", w.busiest_month,
                       f"{w.busiest_month_count} items of activity", "var(--text)"))
    if w.top_repo:
        slides.append(("home territory", w.top_repo,
                       f"{w.top_repo_count} pull requests", "var(--acc)"))
    if w.top_language:
        slides.append(("weapon of choice", w.top_language,
                       f"{w.top_language_count} prs", "var(--text)"))
    if w.biggest_pr_title:
        slides.append(("the monster patch",
                       f"{w.biggest_pr_lines:,} lines",
                       '"' + w.biggest_pr_title[:44] + '"', "var(--red)"))
    if w.favorite_weekday:
        slides.append(("you surface on", w.favorite_weekday.upper(),
                       "more than any other day", "var(--acc)"))
    if w.reviews:
        slides.append(("you reviewed for others", str(w.reviews),
                       "times. team player", "var(--text)"))
    if w.pr_cadence_days:
        slides.append(("your cadence", "every " + str(w.pr_cadence_days) + " days",
                       "one pull request", "var(--acc)"))
    net = w.lines_added - w.lines_deleted
    if net != 0:
        slides.append(("net contribution",
                       ("+" if net > 0 else "") + f"{net:,}",
                       "lines, net of deletions", "var(--text)"))
    slides.append(("end of intercept", "DOSSIER CLOSED",
                   f"{w.repos} repos · {w.languages} languages · prsnoop",
                   "var(--acc)"))

    slide_html = ""
    for i, (kicker, big, sub, color) in enumerate(slides):
        slide_html += (
            '<section class="slide' + (" active" if i == 0 else "") + '">'
            '<div class="rec"><span class="dot"></span>REC '
            + String2(i + 1) + "/" + String2(len(slides)) + "</div>"
            '<div class="kick">' + kicker + "</div>"
            '<div class="big" style="color:' + color + '">' + big + "</div>"
            '<div class="sub">' + sub + "</div>"
            '<div class="bar"><i style="width:'
            + str(round((i + 1) / len(slides) * 100)) + '%"></i></div>'
            "</section>"
        )

    return (
        """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PRSNOOP · WRAPPED: __USER__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
:root{--bg:#060a08;--line:#18251e;--text:#d9e6dc;--dim:#7f948a;
--acc:#3dffa2;--red:#ff5a3c;
--sans:'Space Grotesk',sans-serif;--mono:'IBM Plex Mono',monospace}
body{background:var(--bg);color:var(--text);overflow:hidden;
font-family:var(--sans);position:relative}
body:before{content:"";position:fixed;inset:0;pointer-events:none;z-index:1;
background-image:linear-gradient(var(--line) 1px,transparent 1px),
linear-gradient(90deg,var(--line) 1px,transparent 1px);
background-size:44px 44px;opacity:.4}
body:after{content:"";position:fixed;inset:0;pointer-events:none;z-index:30;
background:repeating-linear-gradient(0deg,transparent 0 3px,rgba(0,0,0,.1) 3px 4px);
mix-blend-mode:overlay}
.slide{position:fixed;inset:0;display:none;flex-direction:column;
align-items:center;justify-content:center;text-align:center;padding:30px;
z-index:2}
.slide.active{display:flex}
.rec{position:fixed;top:22px;left:26px;font-family:var(--mono);
font-size:11px;letter-spacing:.28em;color:var(--dim)}
.rec .dot{display:inline-block;width:9px;height:9px;border-radius:50%;
background:var(--red);margin-right:9px;animation:blink 1.4s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.15}}
.kick{font-family:var(--mono);font-size:clamp(11px,2.4vw,14px);
letter-spacing:.34em;text-transform:uppercase;color:var(--acc);
margin-bottom:24px}
.big{font-size:clamp(46px,12vw,116px);font-weight:700;letter-spacing:-2px;
line-height:1.02;text-transform:uppercase;
animation:pop .6s cubic-bezier(.22,1.4,.36,1)}
.sub{font-family:var(--mono);font-size:clamp(12px,2.6vw,16px);
letter-spacing:.14em;color:var(--dim);margin-top:22px;text-transform:uppercase}
@keyframes pop{0%{transform:scale(.6);opacity:0}100%{transform:scale(1);opacity:1}}
.bar{position:fixed;top:0;left:0;right:0;height:3px;z-index:20;
background:rgba(255,255,255,.08)}
.bar i{display:block;height:100%;background:var(--acc);width:0;
transition:width .5s cubic-bezier(.22,1,.36,1)}
.next{position:fixed;bottom:26px;left:50%;transform:translateX(-50%);
font-family:var(--mono);font-size:10.5px;letter-spacing:.28em;
color:var(--dim);background:transparent;border:1px solid var(--line);
padding:10px 24px;cursor:pointer;text-transform:uppercase;z-index:10}
.next:hover{color:var(--acc);border-color:var(--acc-dim)}
.brand{position:fixed;bottom:30px;right:26px;font-family:var(--mono);
font-size:10px;letter-spacing:.2em;z-index:10}
.brand a{color:var(--dim);text-decoration:none}
.brand a:hover{color:var(--acc)}
</style></head><body>
__SLIDES__
<button class="next" id="next">next ▸</button>
<div class="brand"><a href="https://github.com/MohammedAnasNathani/prsnoop">PRSNOOP</a></div>
<script>
const slides = Array.from(document.querySelectorAll('.slide'));
let idx = 0, timer = null;
function show(n) {
  if (n < 0 || n >= slides.length) { finish(); return; }
  slides.forEach((s) => s.classList.remove('active'));
  idx = n;
  slides[idx].classList.add('active');
  const big = slides[idx].querySelector('.big');
  big.style.animation = 'none'; void big.offsetWidth; big.style.animation = '';
  slides[idx].querySelector('.bar i').style.width =
    slides[idx].querySelector('.bar i').style.width;
  clearTimeout(timer);
  timer = setTimeout(() => show(idx + 1), 3600);
}
function finish() {
  const b = document.getElementById('next');
  b.textContent = 'replay ↻';
  clearTimeout(timer);
}
document.getElementById('next').onclick = () => {
  if (idx >= slides.length - 1) show(0); else show(idx + 1);
};
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight' || e.key === ' ')
    document.getElementById('next').click();
  if (e.key === 'ArrowLeft') show(Math.max(0, idx - 1));
});
let tx = null;
addEventListener('touchstart', (e) => { tx = e.touches[0].clientX; },
  { passive: true });
addEventListener('touchend', (e) => {
  if (tx === null) return;
  const dx = e.changedTouches[0].clientX - tx;
  if (dx < -40) document.getElementById('next').click();
  else if (dx > 40) show(Math.max(0, idx - 1));
  tx = null;
}, { passive: true });
show(0);
</script></body></html>"""
        .replace("__USER__", x_escape_wrap(w.user))
        .replace("__SLIDES__", slide_html)
    )


def String2(n: int) -> str:
    return f"{n:02d}"


def x_escape_wrap(text: str) -> str:
    from xml.sax.saxutils import escape

    return escape(text)
