"""Stats aggregation over an Activity snapshot.

Everything here is derived from the records the fetchers returned: counts,
rates, timing percentiles, day-by-day activity, streaks, and per-repo /
per-language breakdowns. The language mix is inferred from the primary
language of each PR's repository, which the fetcher enriches.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from prsnoop.models import (
    MERGED,
    OPEN,
    Activity,
    DayActivity,
    IssueRecord,
    JsonDict,
    PRRecord,
    RepoPerformance,
    ReviewRecord,
    Stats,
)


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


@dataclass(slots=True)
class TrendDelta:
    """Change of one metric against a previous window.

    ``current`` and ``previous`` are raw values; ``direction`` is +1, 0, or
    -1 so renderers never have to recompute signs. Percent changes are
    None when the previous value was zero (a 0 -> 5 jump has no honest
    percentage).
    """

    key: str
    label: str
    current: float
    previous: float
    lower_is_better: bool = False

    @property
    def delta(self) -> float:
        return self.current - self.previous

    @property
    def pct(self) -> float | None:
        if self.previous == 0:
            return None
        return round((self.current - self.previous) / self.previous * 100, 1)

    @property
    def direction(self) -> int:
        if self.current > self.previous:
            return 1
        if self.current < self.previous:
            return -1
        return 0

    @property
    def improved(self) -> bool:
        """True when the change is good news for the contributor."""
        if self.lower_is_better:
            return self.direction < 0
        return self.direction > 0

    @classmethod
    def from_dict(cls, d: JsonDict) -> TrendDelta:
        return cls(
            key=d["key"],
            label=d["label"],
            current=d["current"],
            previous=d["previous"],
            lower_is_better=bool(d.get("lower_is_better", False)),
        )

    def to_dict(self) -> JsonDict:
        return {
            "key": self.key,
            "label": self.label,
            "current": self.current,
            "previous": self.previous,
            "lower_is_better": self.lower_is_better,
            "delta": self.delta,
            "pct": self.pct,
            "direction": self.direction,
            "improved": self.improved,
        }


def _streaks(dates: set[str], today: str) -> tuple[int, int]:
    """Return (longest, current) run of consecutive active days.

    ``current`` counts back from the most recent active day; if that day is
    neither today nor yesterday the current streak is 0.
    """
    if not dates:
        return 0, 0
    ordered = sorted(dates)
    longest = 1
    run = 1
    for prev, cur in zip(ordered, ordered[1:], strict=False):
        d_prev = datetime.strptime(prev, "%Y-%m-%d").date()
        d_cur = datetime.strptime(cur, "%Y-%m-%d").date()
        if (d_cur - d_prev).days == 1:
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    d_today = datetime.strptime(today, "%Y-%m-%d").date()
    last = datetime.strptime(ordered[-1], "%Y-%m-%d").date()
    if (d_today - last).days > 1:
        return longest, 0
    current = 1
    cursor = last
    while datetime.strftime(cursor - timedelta(days=1), "%Y-%m-%d") in dates:
        cursor = cursor - timedelta(days=1)
        current += 1
    return longest, current


def _size_bucket(total_lines: int) -> str:
    """XS < 10 <= S < 100 <= M < 1000 <= L < 5000 <= XL changed lines."""
    if total_lines < 10:
        return "XS"
    if total_lines < 100:
        return "S"
    if total_lines < 1000:
        return "M"
    if total_lines < 5000:
        return "L"
    return "XL"


def build_stats(
    activity: Activity,
    window_days: int = 30,
    since: str = "",
    until: str = "",
    today: str | None = None,
) -> Stats:
    """Derive timing, streak, and breakdown stats for one Activity."""
    prs = activity.prs
    merged = [p for p in prs if p.state == MERGED]
    open_prs = [p for p in prs if p.state == OPEN]
    merge_days = sorted(d for d in (p.days_to_merge for p in merged) if d is not None)

    # ---- day-by-day activity (UTC calendar days) ----
    per_day: dict[str, DayActivity] = {}

    def _day(date_str: str) -> DayActivity:
        return per_day.setdefault(date_str, DayActivity(date_str))

    for pr in prs:
        _day(_date_str(pr.created_at)).prs += 1
    for pr in merged:
        if pr.merged_at:
            _day(_date_str(pr.merged_at)).merged += 1
    for issue in activity.issues:
        _day(_date_str(issue.created_at)).issues += 1
    for review in activity.reviews:
        _day(_date_str(review.submitted_at)).reviews += 1

    day_activity = [per_day[d] for d in sorted(per_day)]
    active_dates = {da.date for da in day_activity if da.total > 0}

    # ---- streaks ----
    if today is None:
        today = _date_str(datetime.now(timezone.utc))
    longest, current = _streaks(active_dates, today)

    # ---- language mix: one count per PR, by its repo's primary language ----
    lang_counts: Counter[str] = Counter(
        (getattr(pr, "language", "") or "Unknown") for pr in prs
    )

    repo_counts = Counter(p.repo for p in prs)
    all_dates = sorted(active_dates)
    busiest = max(day_activity, key=lambda da: da.total, default=None)

    def _p90(values: list[float]) -> float | None:
        if not values:
            return None
        k = max(0, min(len(values) - 1, round(0.9 * (len(values) - 1))))
        return round(sorted(values)[k], 2)

    # ---- PR size profile: buckets over changed lines ----
    # PRs whose diff stats were never enriched (0/0) are excluded so a
    # partial report does not skew the profile.
    sized = [p for p in prs if p.additions or p.deletions]
    size_order = ("XS", "S", "M", "L", "XL")
    size_buckets: dict[str, int] = {k: 0 for k in size_order}
    for p in sized:
        size_buckets[_size_bucket(p.additions + p.deletions)] += 1
    size_median: int | None = None
    if sized:
        size_median = round(statistics.median(p.additions + p.deletions for p in sized))

    # ---- repo performance: where this contributor's work lands ----
    per_repo: dict[str, list[PRRecord]] = {}
    for p in prs:
        per_repo.setdefault(p.repo, []).append(p)
    repo_performance: list[RepoPerformance] = []
    for repo, group in per_repo.items():
        if len(group) < 2:
            continue
        merged_n = sum(1 for p in group if p.state == MERGED)
        merge_days_group = sorted(
            d
            for d in (p.days_to_merge for p in group if p.state == MERGED)
            if d is not None
        )
        repo_performance.append(
            RepoPerformance(
                repo=repo,
                prs=len(group),
                merged=merged_n,
                merge_rate=round(merged_n / len(group), 4),
                median_days_to_merge=(
                    round(statistics.median(merge_days_group), 2)
                    if merge_days_group
                    else None
                ),
            )
        )
    repo_performance.sort(key=lambda r: (-r.prs, r.repo))
    repo_performance = repo_performance[:10]

    # ---- momentum: second half of the window vs first half ----
    span_start = (
        datetime.strptime(since, "%Y-%m-%d").date()
        if since
        else datetime.strptime(today, "%Y-%m-%d").date() - timedelta(days=window_days)
    )
    span_end = datetime.strptime(today, "%Y-%m-%d").date()
    midpoint = span_start + (span_end - span_start) / 2
    per_date: dict[str, int] = {da.date: da.total for da in day_activity}
    first_half = sum(
        n
        for d, n in per_date.items()
        if span_start <= datetime.strptime(d, "%Y-%m-%d").date() < midpoint
    )
    second_half = sum(
        n
        for d, n in per_date.items()
        if midpoint <= datetime.strptime(d, "%Y-%m-%d").date() <= span_end
    )
    momentum: str | None = None
    momentum_pct: float | None = None
    if first_half == 0 and second_half == 0:
        pass
    elif first_half == 0:
        momentum, momentum_pct = "accelerating", None
    else:
        momentum_pct = round((second_half - first_half) / first_half * 100, 1)
        if momentum_pct >= 15:
            momentum = "accelerating"
        elif momentum_pct <= -15:
            momentum = "slowing"
        else:
            momentum = "steady"

    return Stats(
        user=activity.user,
        generated_at=activity.generated_at,
        window_days=window_days,
        since=since,
        until=until,
        prs_authored=len(prs),
        prs_merged=len(merged),
        prs_open=len(open_prs),
        prs_closed_unmerged=len(prs) - len(merged) - len(open_prs),
        reviews_given=len(activity.reviews),
        issues_opened=len(activity.issues),
        issues_closed=sum(1 for i in activity.issues if i.closed_at is not None),
        lines_added=sum(p.additions for p in prs),
        lines_deleted=sum(p.deletions for p in prs),
        merge_rate=round(len(merged) / len(prs), 4) if prs else 0.0,
        median_days_to_merge=(
            round(statistics.median(merge_days), 2) if merge_days else None
        ),
        p90_days_to_merge=_p90(merge_days),
        fastest_merge_days=round(merge_days[0], 2) if merge_days else None,
        slowest_merge_days=round(merge_days[-1], 2) if merge_days else None,
        first_pr_date=_date_str(min(p.created_at for p in prs)) if prs else None,
        last_activity_date=all_dates[-1] if all_dates else None,
        active_days=len(active_dates),
        longest_streak_days=longest,
        current_streak_days=current,
        avg_prs_per_active_day=(
            round(len(prs) / len(active_dates), 2) if active_dates else 0.0
        ),
        busiest_day=busiest.date if busiest and busiest.total > 0 else None,
        busiest_day_count=busiest.total if busiest else 0,
        distinct_repos=len(repo_counts),
        distinct_languages=len(lang_counts),
        top_repos=repo_counts.most_common(10),
        languages=lang_counts.most_common(10),
        day_activity=day_activity,
        size_median_lines=size_median,
        size_buckets=size_buckets,
        repo_performance=repo_performance,
        momentum=momentum,
        momentum_pct=momentum_pct,
    )


def build_activity(
    user: str,
    prs: list[PRRecord],
    reviews: list[ReviewRecord],
    issues: list[IssueRecord],
    now: datetime | None = None,
    window_days: int = 30,
    since: str = "",
    until: str = "",
) -> Activity:
    """Assemble an Activity and compute its Stats in one step."""
    stamp = now or datetime.now(timezone.utc)
    activity = Activity(
        user=user,
        generated_at=stamp,
        prs=prs,
        reviews=reviews,
        issues=issues,
        stats=Stats(user=user, generated_at=stamp),
    )
    activity.stats = build_stats(
        activity,
        window_days=window_days,
        since=since,
        until=until,
        today=_date_str(stamp),
    )
    return activity


_TREND_METRICS = (
    ("prs_authored", "pull requests", False),
    ("prs_merged", "merged", False),
    ("reviews_given", "reviews given", False),
    ("issues_opened", "issues opened", False),
    ("lines_added", "lines added", False),
    ("median_days_to_merge", "median merge time", True),
)


def build_trend(current: Stats, previous: Stats) -> list[TrendDelta]:
    """Compare one window's stats against the window before it.

    ``median_days_to_merge`` is lower-is-better; everything else is
    more-is-better. The previous window must cover a comparable span or
    the deltas are noise, so callers pass windows of the same length.
    """
    out: list[TrendDelta] = []
    for key, label, lower_is_better in _TREND_METRICS:
        cur = getattr(current, key)
        prev = getattr(previous, key)
        if cur is None or prev is None:
            continue
        out.append(
            TrendDelta(
                key=key,
                label=label,
                current=float(cur),
                previous=float(prev),
                lower_is_better=lower_is_better,
            )
        )
    return out


def sort_prs(prs: list[PRRecord], key: str) -> list[PRRecord]:
    """Sort pull requests listing based on the specified sort key."""
    if key == "oldest":
        return sorted(prs, key=lambda pr: pr.created_at)
    if key == "merge-time":
        # Unmerged PRs (days_to_merge is None) sort last
        return sorted(
            prs,
            key=lambda pr: (pr.days_to_merge is None, pr.days_to_merge or 0.0),
        )
    if key == "size":
        return sorted(
            prs,
            key=lambda pr: pr.additions + pr.deletions,
            reverse=True,
        )
    if key == "repo":
        return sorted(prs, key=lambda pr: (pr.repo.lower(), pr.number))
    # Default: "recent" (newest created_at first)
    return sorted(prs, key=lambda pr: pr.created_at, reverse=True)
