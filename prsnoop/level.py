"""Level system: XP and a 100-level progression ladder.

Every measurable action earns XP; total XP maps to a level (1-100) and a
named rank. The curve is designed so an active year lands around level 30-50
and a legendary multi-year account pushes toward the top ranks.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from prsnoop.achievements import build_report
from prsnoop.models import Activity, JsonDict
from prsnoop.score import compute_score

XP = {
    "pr_opened": 25,
    "pr_merged": 60,
    "review_given": 15,
    "issue_opened": 10,
    "issue_closed": 20,
    "lines_per_10": 1,
    "streak_day": 50,
    "active_day": 30,
    "repo_touched": 40,
    "language": 60,
    "comment_received": 5,
}

RANKS = (
    (100, "GHOST"),
    (95, "LEGEND"),
    (88, "PHANTOM"),
    (80, "OPERATOR"),
    (70, "SPECIALIST"),
    (60, "VETERAN"),
    (50, "PROFESSIONAL"),
    (40, "CONTRIBUTOR"),
    (30, "REGULAR"),
    (20, "APPRENTICE"),
    (10, "RECRUIT"),
    (1, "DRIFTER"),
)


def level_from_xp(xp: int) -> int:
    """Map total XP to a 1-100 level on a soft-quadratic curve.

    Level L requires 40 * L^1.8 cumulative XP: level 10 ~ 2.5k, level 30
    ~ 17k, level 50 ~ 43k, level 100 ~ 155k.
    """
    if xp <= 0:
        return 1
    level = int((xp / 40) ** (1 / 1.8))
    return max(1, min(100, level))


def xp_for_level(level: int) -> int:
    """Cumulative XP required to reach ``level``."""
    if level <= 1:
        return 0
    return int(40 * level ** 1.8)


def rank_for(level: int) -> str:
    for floor, name in RANKS:
        if level >= floor:
            return name
    return "DRIFTER"


@dataclass(slots=True)
class LevelCard:
    """The full progression readout for one contributor."""

    user: str
    generated_at: datetime
    xp: int
    level: int
    rank: str
    next_rank: str | None
    next_rank_at: int | None
    xp_into_level: int
    xp_for_next: int | None
    progress_pct: float
    breakdown: dict[str, int]
    achievement_points: int
    health_grade: str

    def to_dict(self) -> JsonDict:
        return {
            "user": self.user,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "xp": self.xp,
            "level": self.level,
            "rank": self.rank,
            "next_rank": self.next_rank,
            "next_rank_at": self.next_rank_at,
            "xp_into_level": self.xp_into_level,
            "xp_for_next": self.xp_for_next,
            "progress_pct": round(self.progress_pct, 1),
            "breakdown": self.breakdown,
            "achievement_points": self.achievement_points,
            "health_grade": self.health_grade,
        }


def compute_level(activity: Activity) -> LevelCard:
    """Compute XP and level from one activity snapshot."""
    s = activity.stats
    board = build_report(activity)
    hs = compute_score(activity)

    breakdown = {
        "PRs opened": s.prs_authored * XP["pr_opened"],
        "PRs merged": s.prs_merged * XP["pr_merged"],
        "Reviews given": s.reviews_given * XP["review_given"],
        "Issues opened": s.issues_opened * XP["issue_opened"],
        "Issues closed": s.issues_closed * XP["issue_closed"],
        "Lines shipped": s.lines_added // 10 * XP["lines_per_10"],
        "Streak days": s.longest_streak_days * XP["streak_day"],
        "Active days": s.active_days * XP["active_day"],
        "Repositories": s.distinct_repos * XP["repo_touched"],
        "Languages": s.distinct_languages * XP["language"],
        "Discussion": sum(p.comments for p in activity.prs) * XP["comment_received"],
        "Achievements": getattr(board, "achievement_points", board.score),
    }
    xp = sum(breakdown.values())
    level = level_from_xp(xp)
    rank = rank_for(level)

    next_rank = None
    next_rank_at = None
    for floor, name in RANKS:
        if floor > level:
            next_rank, next_rank_at = name, floor
    if next_rank_at is not None:
        base = xp_for_level(level)
        nxt = xp_for_level(next_rank_at)
        span = max(1, nxt - base)
        into = max(0, xp - base)
        progress = min(100.0, into / span * 100)
        xp_into_level, xp_for_next = into, nxt
    else:
        progress = 100.0
        xp_into_level, xp_for_next = xp, None

    return LevelCard(
        user=activity.user,
        generated_at=activity.generated_at or datetime.now(timezone.utc),
        xp=xp,
        level=level,
        rank=rank,
        next_rank=next_rank,
        next_rank_at=next_rank_at,
        xp_into_level=xp_into_level,
        xp_for_next=xp_for_next,
        progress_pct=progress,
        breakdown=breakdown,
        achievement_points=board.score,
        health_grade=hs.grade,
    )


def render_level_table(lc: LevelCard) -> str:
    lines = [
        f"prsnoop level | {lc.user}",
        "",
        f"  LEVEL {lc.level:>3}   {lc.rank}",
        f"  XP     {lc.xp:>8,}",
        "",
    ]
    if lc.next_rank:
        lines += [
            f"  next rank {lc.next_rank} at level {lc.next_rank_at}",
            f"  progress  {'#' * int(lc.progress_pct // 5):<20} {lc.progress_pct:.0f}%",
            "",
        ]
    else:
        lines += ["  maximum rank reached", ""]
    lines.append("  XP breakdown")
    for source, amount in sorted(lc.breakdown.items(), key=lambda kv: -kv[1]):
        if amount:
            lines.append(f"    {source:<16} {amount:>7,} xp")
    return "\n".join(lines)


def render_level_markdown(lc: LevelCard) -> str:
    out = [
        f"# Level: {lc.user}",
        "",
        f"**Level {lc.level} · {lc.rank}** · {lc.xp:,} XP"
        + (f" · next: {lc.next_rank} at level {lc.next_rank_at}"
           if lc.next_rank else " · max rank"),
        "",
        "| Source | XP |",
        "|---|---:|",
    ]
    for source, amount in sorted(lc.breakdown.items(), key=lambda kv: -kv[1]):
        if amount:
            out.append(f"| {source} | {amount:,} |")
    out += ["", f"Achievement points: **{lc.achievement_points}** · "
             f"health grade: **{lc.health_grade}**", ""]
    return "\n".join(out)


def render_level_json(lc: LevelCard) -> str:
    import json

    return json.dumps(lc.to_dict(), indent=2)
