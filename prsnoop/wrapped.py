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
    """Spotify-Wrapped-style story: vertical slides, auto-advance, one file."""
    slides = [
        ("your year in code", f"{w.user}", "prsnoop wrapped",
         "linear-gradient(160deg,#1a1040,#0d1117)"),
        ("you opened", f"{w.prs}", "pull requests", "linear-gradient(160deg,#0b2545,#0d1117)"),
        ("and landed", f"{w.merged}", "of them merged", "linear-gradient(160deg,#0b3d2e,#0d1117)"),
        ("you shipped", f"+{w.lines_added:,}", "lines of code",
         "linear-gradient(160deg,#40200a,#0d1117)"),
        ("your longest streak", f"{w.longest_streak_days} days", "back to back",
         "linear-gradient(160deg,#3d0f2e,#0d1117)"),
    ]
    if w.busiest_month:
        slides.append(("your hottest month was", w.busiest_month,
                       f"{w.busiest_month_count} items", "linear-gradient(160deg,#401a0a,#0d1117)"))
    if w.top_repo:
        slides.append(("you called home", w.top_repo, f"{w.top_repo_count} PRs",
                       "linear-gradient(160deg,#0a2f3d,#0d1117)"))
    if w.top_language:
        slides.append(("your weapon of choice", w.top_language,
                       f"{w.top_language_count} PRs", "linear-gradient(160deg,#251a45,#0d1117)"))
    if w.biggest_pr_title:
        slides.append(("your monster patch", f"{w.biggest_pr_lines:,} lines",
                       f'"{w.biggest_pr_title[:40]}"',
                       "linear-gradient(160deg,#451a25,#0d1117)"))
    if w.favorite_weekday:
        slides.append(("you peak on", w.favorite_weekday, "s",
                       "linear-gradient(160deg,#12330a,#0d1117)"))
    slides.append(("that was your year.",
                   f"{w.repos} repos · {w.languages} languages",
                   "generated by prsnoop",
                   "linear-gradient(160deg,#111,#0d1117)"))

    slide_html = ""
    for i, (kicker, big, sub, bg) in enumerate(slides):
        slide_html += (
            f'<section class="slide{" active" if i == 0 else ""}" '
            f'style="background:{bg}">'
            f'<div class="kick">{kicker}</div>'
            f'<div class="big">{big}</div>'
            f'<div class="sub">{sub}</div>'
            f'<div class="dots">'
            + "".join(f'<span class="dot{" on" if j == i else ""}"></span>'
                      for j in range(len(slides)))
            + "</div></section>"
        )

    return (
        """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>prsnoop wrapped: __USER__</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%}
body{background:#0d1117;color:#fff;overflow:hidden;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.slide{position:fixed;inset:0;display:none;flex-direction:column;
align-items:center;justify-content:center;text-align:center;padding:30px;
opacity:0;transition:opacity .5s}
.slide.active{display:flex;opacity:1}
.slide.leaving{display:flex;opacity:0}
.kick{font-size:clamp(14px,3vw,20px);letter-spacing:.24em;text-transform:uppercase;
color:rgba(255,255,255,.55);margin-bottom:18px}
.big{font-size:clamp(48px,13vw,120px);font-weight:900;letter-spacing:-3px;line-height:1.05;
background:linear-gradient(90deg,#7ee2b8,#58a6ff,#b58cff);
-webkit-background-clip:text;background-clip:text;color:transparent;
animation:pop .7s cubic-bezier(.22,1.4,.36,1)}
.sub{font-size:clamp(14px,3vw,22px);color:rgba(255,255,255,.65);margin-top:20px;max-width:34ch}
@keyframes pop{0%{transform:scale(.55);opacity:0}100%{transform:scale(1);opacity:1}}
.dots{position:fixed;top:20px;left:0;right:0;display:flex;justify-content:center;gap:7px}
.dot{width:26px;height:4px;border-radius:2px;background:rgba(255,255,255,.22)}
.dot.on{background:#fff}
.next{position:fixed;bottom:26px;left:50%;transform:translateX(-50%);
color:rgba(255,255,255,.5);font-size:13px;letter-spacing:.15em;cursor:pointer;
text-transform:uppercase;border:1px solid rgba(255,255,255,.3);border-radius:20px;
padding:9px 22px;background:transparent}
.next:hover{color:#fff;border-color:#fff}
.brand{position:fixed;bottom:26px;right:24px;color:rgba(255,255,255,.35);font-size:12px}
.brand a{color:rgba(255,255,255,.55);text-decoration:none}
</style></head><body>
__SLIDES__
<button class="next" id="next">next ▸</button>
<div class="brand"><a href="https://github.com/MohammedAnasNathani/prsnoop">prsnoop wrapped</a></div>
<script>
const slides = Array.from(document.querySelectorAll('.slide'));
let idx = 0, timer = null;
function show(n) {
  if (n < 0 || n >= slides.length) { finish(); return; }
  slides.forEach((s, k) => { s.classList.remove('active'); });
  idx = n;
  const s = slides[idx];
  s.classList.add('active');
  const big = s.querySelector('.big');
  big.style.animation = 'none'; void big.offsetWidth; big.style.animation = '';
  document.querySelectorAll('.dot').forEach((d, k) => d.classList.toggle('on', k === idx));
  clearTimeout(timer);
  timer = setTimeout(() => show(idx + 1), 3600);
}
function finish() {
  const b = document.querySelector('.next');
  b.textContent = 'replay ↻';
  clearTimeout(timer);
}
document.getElementById('next').onclick = () => {
  if (idx >= slides.length - 1) { show(0); }
  else { show(idx + 1); }
};
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowRight' || e.key === ' ') document.getElementById('next').click();
  if (e.key === 'ArrowLeft') show(Math.max(0, idx - 1));
});
let tx = null;
addEventListener('touchstart', (e) => { tx = e.touches[0].clientX; }, { passive: true });
addEventListener('touchend', (e) => {
  if (tx === null) return;
  const dx = e.changedTouches[0].clientX - tx;
  if (dx < -40) document.getElementById('next').click();
  else if (dx > 40) show(Math.max(0, idx - 1));
  tx = null;
}, { passive: true });
show(0);
</script></body></html>"""
        .replace("__USER__", w.user)
        .replace("__SLIDES__", slide_html)
    )
