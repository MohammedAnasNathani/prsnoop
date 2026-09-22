"""prsnoop ask: natural-language questions over one activity snapshot.

A small rule-based intent parser answers plain-English questions about the
data locally, no AI service and no API key. Type a question, get a sentence
back computed from the snapshot.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from prsnoop.models import Activity


@dataclass(slots=True)
class Answer:
    """One answered question."""

    question: str
    answer: str
    intent: str

    def to_line(self) -> str:
        return f"Q: {self.question}\nA: {self.answer}"


def _fmt_num(n: float) -> str:
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.1f}"


def _intent_of(q: str) -> str:
    ql = q.lower().strip()
    rules = [
        ("prs_count", (r"\b(how many|number of)\b.*\b(pr|pull request)", r"\bpr count\b")),
        ("merged_count", (r"\b(how many|number of)\b.*\bmerged\b",)),
        ("merge_rate", (r"merge rate", r"\brate\b.*\bmerge",)),
        ("median_merge", (r"median", r"how (fast|long|quick).*merge")),
        ("fastest_merge", (r"fastest",)),
        ("slowest_merge", (r"slowest",)),
        ("top_language", (r"(top|main|favourite|favorite|most).*(language|lang)",)),
        ("languages", (r"\blanguages?\b",)),
        ("top_repo", (r"(top|most|busiest|main).*(repo|repository)",)),
        ("repos", (r"\brepos?\b", r"\brepositories\b")),
        ("streak", (r"streak",)),
        ("active_days", (r"(active|working) days", r"how (many|much).*active")),
        ("momentum", (r"momentum|accelerat|slow|trend|direction",)),
        ("reviews", (r"reviews?\b",)),
        ("net_lines", (r"net lines|net code|net change",)),
        ("deletions", (r"delet|removed lines",)),
        ("lines", (r"lines?\b", r"\bloc\b")),
        ("issues", (r"issues?\b",)),
        ("busiest_day", (r"busiest|most active day|peak",)),
        ("busiest_month", (r"month",)),
        ("busiest_repo", (r"busiest repo",)),
        ("open_prs", (r"\bopen\b.*\b(pr|pull)", r"standing")),
        ("score", (r"score|grade|health",)),
        ("achievements", (r"achievement|badge",)),
        ("best_pr", (r"(biggest|largest|longest).*pr", r"most discussed")),
        ("weekday", (r"(favourite|favorite|preferred) day|which day",)),
        ("size_profile", (r"size|biggest prs|typical pr",)),
        ("closed_rate", (r"issues closed|closing issues",)),
        ("active_ratio", (r"how (often|frequently)|duty|ratio",)),
        ("counts_by", (r"how many (repos|languages)",)),
        ("avg_prs", (r"per day|per active day|daily average",)),
        ("open_standing", (r"open prs|still open|wip",)),
        ("grade", (r"what grade|my grade|letter grade",)),
        ("genome", (r"dna|genome|fingerprint",)),
        ("level", (r"level|rank|xp",)),
        ("help", (r"^help\b", r"what can")),
    ]
    for intent, patterns in rules:
        for pat in patterns:
            if re.search(pat, ql):
                return intent
    return "unknown"


def answer_question(activity: Activity, question: str) -> Answer:
    s = activity.stats
    intent = _intent_of(question)
    user = activity.user
    window = f"last {s.window_days} days"

    def a(text: str) -> Answer:
        return Answer(question, text, intent)

    if intent == "prs_count":
        return a(f"{user} opened {s.prs_authored} pull requests in the {window} "
                 f"({s.prs_merged} merged, {s.prs_open} still open).")
    if intent == "merged_count":
        return a(f"{s.prs_merged} of {s.prs_authored} PRs were merged "
                 f"({s.merge_rate * 100:.0f}% merge rate).")
    if intent == "merge_rate":
        return a(f"The merge rate is {s.merge_rate * 100:.0f}% "
                 f"({s.prs_merged} of {s.prs_authored} PRs).")
    if intent == "median_merge":
        if s.median_days_to_merge is None:
            return a("No merged PRs in this window, so there is no merge time yet.")
        return a(f"The median PR merges in {s.median_days_to_merge} days "
                 f"(p90 {s.p90_days_to_merge} days, fastest {s.fastest_merge_days} days).")
    if intent == "fastest_merge":
        return a(f"The fastest merge took {s.fastest_merge_days} days.")
    if intent == "slowest_merge":
        return a(f"The slowest merge took {s.slowest_merge_days} days.")
    if intent == "top_language":
        if s.languages:
            lang, count = s.languages[0]
            return a(f"The top language is {lang} with {count} PRs.")
        return a("No language data in this window.")
    if intent == "languages":
        langs = ", ".join(f"{lang} ({n})" for lang, n in s.languages[:5]) or "none"
        return a(f"Languages by PR count: {langs}. That is {s.distinct_languages} "
                 "distinct languages.")
    if intent == "top_repo":
        if s.top_repos:
            repo, count = s.top_repos[0]
            return a(f"The busiest repo is {repo} with {count} PRs.")
        return a("No repository data in this window.")
    if intent == "busiest_repo":
        if s.top_repos:
            repo, count = s.top_repos[0]
            return a(f"The busiest repo is {repo} with {count} PRs.")
        return a("No repository data in this window.")
    if intent == "repos":
        tops = ", ".join(f"{repo} ({n})" for repo, n in s.top_repos[:5]) or "none"
        return a(f"{s.distinct_repos} repositories touched. Top: {tops}.")
    if intent == "streak":
        return a(f"Longest streak: {s.longest_streak_days} days. Current streak: "
                 f"{s.current_streak_days} days.")
    if intent == "active_days":
        return a(f"{user} was active on {s.active_days} of the last {s.window_days} days.")
    if intent == "momentum":
        if s.momentum is None:
            return a("Not enough activity to measure momentum yet.")
        pct = ""
        if s.momentum_pct is not None:
            pct = f" ({s.momentum_pct:+.0f}% vs first half)"
        return a(f"Momentum is {s.momentum}{pct}.")
    if intent == "lines":
        return a(f"Lines changed: +{_fmt_num(s.lines_added)} added, "
                 f"-{_fmt_num(s.lines_deleted)} deleted "
                 f"(net {_fmt_num(s.lines_added - s.lines_deleted)}).")
    if intent == "reviews":
        return a(f"{user} left {s.reviews_given} reviews on other people's PRs.")
    if intent == "issues":
        return a(f"{s.issues_opened} issues opened, {s.issues_closed} of them closed.")
    if intent == "busiest_day":
        if s.busiest_day:
            return a(f"The busiest day was {s.busiest_day} with "
                     f"{s.busiest_day_count} items.")
        return a("No activity recorded in this window.")
    if intent == "busiest_month":
        months: dict[str, int] = {}
        for da in s.day_activity:
            months[da.date[:7]] = months.get(da.date[:7], 0) + da.total
        if months:
            m, n = max(months.items(), key=lambda kv: kv[1])
            return a(f"The busiest month was {m} with {n} items.")
        return a("No activity recorded in this window.")
    if intent == "open_prs":
        return a(f"{s.prs_open} PRs are still open.")
    if intent == "score":
        # lazy import avoids a cycle with prsnoop.score
        from prsnoop.score import compute_score
        hs = compute_score(activity)
        return a(f"Health score: {hs.total:.1f}/100, grade {hs.grade} ({hs.band}). "
                 f"Burnout risk: {hs.burnout_risk}.")
    if intent == "achievements":
        from prsnoop.achievements import build_report
        rep = build_report(activity)
        return a(f"{len(rep.unlocked)} of {len(rep.achievements)} achievements unlocked "
                 f"({rep.score} points).")
    if intent == "best_pr":
        if not activity.prs:
            return a("No PRs in this window.")
        biggest = max(activity.prs, key=lambda p: p.additions + p.deletions)
        chattiest = max(activity.prs, key=lambda p: p.comments)
        return a(f"Biggest PR: {biggest.repo}#{biggest.number} "
                 f"({biggest.additions + biggest.deletions:,} lines). Most discussed: "
                 f"{chattiest.repo}#{chattiest.number} ({chattiest.comments} comments).")
    if intent == "weekday":
        days = ["Monday", "Tuesday", "Wednesday", "Thursday",
                "Friday", "Saturday", "Sunday"]
        counts: dict[int, int] = {}
        for p in activity.prs:
            counts[p.created_at.weekday()] = counts.get(p.created_at.weekday(), 0) + 1
        if counts:
            wd = max(counts, key=lambda k: counts[k])
            return a(f"The favourite day to open PRs is {days[wd]} "
                     f"({counts[wd]} PRs).")
        return a("No PRs in this window.")
    if intent == "level":
        from prsnoop.level import compute_level
        lc = compute_level(activity)
        nxt = (f" Next: {lc.next_rank} at level {lc.next_rank_at}."
               if lc.next_rank else " Maximum rank reached.")
        return a(f"Level {lc.level} ({lc.rank}) with {lc.xp:,} XP."
                 + nxt)
    if intent == "genome":
        from prsnoop.dna import build_dna
        d = build_dna(activity)
        return a(f"Genome {d.genome}. Signature: {d.signature}.")
    if intent == "grade":
        from prsnoop.score import compute_score
        hs = compute_score(activity)
        return a(f"Grade {hs.grade} ({hs.band}) at {hs.total:.1f}/100.")
    if intent == "size_profile":
        if s.size_median_lines is None:
            return a("No sized PRs in this window.")
        buckets = ", ".join(f"{k} {v}" for k, v in s.size_buckets.items() if v)
        return a(f"Typical PR: {s.size_median_lines} changed lines. "
                 f"Buckets: {buckets}.")
    if intent == "net_lines":
        return a(f"Net change: {_fmt_num(s.lines_added - s.lines_deleted)} lines.")
    if intent == "deletions":
        return a(f"{_fmt_num(s.lines_deleted)} lines deleted in the {window}.")
    if intent == "closed_rate":
        return a(f"{s.issues_closed} of {s.issues_opened} opened issues were closed.")
    if intent == "active_ratio":
        return a(f"Active {s.active_days} of {s.window_days} days "
                 f"({s.active_days / max(1, s.window_days) * 100:.0f}% duty).")
    if intent == "counts_by":
        return a(f"{s.distinct_repos} repositories and {s.distinct_languages} languages.")
    if intent == "avg_prs":
        return a(f"{s.avg_prs_per_active_day} PRs per active day.")
    if intent == "open_standing":
        return a(f"{s.prs_open} PRs are still open.")
    if intent == "help":
        return a(
            "Try asking: how many PRs, merge rate, median merge time, top language, "
            "busiest repo, longest streak, momentum, lines changed, reviews given, "
            "score, achievements, busiest day, favourite day."
        )
    return a(
        "I did not catch that. Ask about PRs, merges, languages, repos, streaks, "
        "momentum, lines, reviews, issues, score, or achievements. "
        "Type 'help' for the list."
    )


def answer_all(activity: Activity, questions: list[str]) -> list[Answer]:
    return [answer_question(activity, q) for q in questions]


def render_ask(answers: list[Answer]) -> str:
    out = ["prsnoop ask", ""]
    for ans in answers:
        out += [f"  Q: {ans.question}", f"  A: {ans.answer}", ""]
    return "\n".join(out)
