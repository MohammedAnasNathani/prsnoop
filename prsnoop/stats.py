"""Stats aggregation over an Activity snapshot.

Everything here is derived from the records the fetchers returned: counts,
rates, timing percentiles, day-by-day activity, streaks, and per-repo /
per-language breakdowns. The language mix is inferred from the primary
language of each PR's repository, which the fetcher enriches.
"""
from __future__ import annotations

import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone

from prsnoop.models import (
    MERGED,
    OPEN,
    Activity,
    DayActivity,
    IssueRecord,
    PRRecord,
    ReviewRecord,
    Stats,
)


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


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
    while (
        datetime.strftime(cursor - timedelta(days=1), "%Y-%m-%d") in dates
    ):
        cursor = cursor - timedelta(days=1)
        current += 1
    return longest, current


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
