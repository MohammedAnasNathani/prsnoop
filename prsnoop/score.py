"""Contributor Health Score: one 0-100 number that captures contributor quality.

The score blends five pillars, each scored 0-100 and weighted:
- Output (30%): PR volume, lines shipped, issues opened
- Impact (25%): merge rate, median merge speed of the reviewer side
- Consistency (20%): active days, streak length, momentum
- Collaboration (15%): reviews given, issues closed
- Rhythm (10%): cadence regularity, weekend/night balance

The composite maps to a letter grade and comes with a burnout-risk flag
computed from streak length and workload concentration.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from prsnoop.models import Activity, JsonDict

GRADE_BANDS = (
    (90, "S", "elite"),
    (80, "A", "excellent"),
    (70, "B", "strong"),
    (60, "C", "solid"),
    (45, "D", "developing"),
    (0, "E", "quiet"),
)

WEIGHTS = {
    "output": 0.30,
    "impact": 0.25,
    "consistency": 0.20,
    "collaboration": 0.15,
    "rhythm": 0.10,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _scale(value: float, cap: float) -> float:
    """Linear ramp: 0 at zero, 100 at cap."""
    if cap <= 0:
        return 0.0
    return _clamp(value / cap * 100.0)


@dataclass(slots=True)
class Pillar:
    """One scored dimension of contributor health."""

    name: str
    score: float
    weight: float
    detail: str

    def to_dict(self) -> JsonDict:
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass(slots=True)
class HealthScore:
    """The composite contributor score with breakdown and risk flags."""

    user: str
    generated_at: datetime
    window_days: int
    total: float
    grade: str
    band: str
    pillars: list[Pillar]
    burnout_risk: str  # low | moderate | high
    burnout_reason: str
    percentile_hint: str

    def to_dict(self) -> JsonDict:
        return {
            "user": self.user,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "window_days": self.window_days,
            "total": round(self.total, 1),
            "grade": self.grade,
            "band": self.band,
            "pillars": [p.to_dict() for p in self.pillars],
            "burnout_risk": self.burnout_risk,
            "burnout_reason": self.burnout_reason,
            "percentile_hint": self.percentile_hint,
        }


def _grade_for(total: float) -> tuple[str, str]:
    for floor, grade, band in GRADE_BANDS:
        if total >= floor:
            return grade, band
    return "E", "quiet"


def compute_score(activity: Activity) -> HealthScore:
    """Compute the composite health score for one activity snapshot."""
    s = activity.stats
    days = max(1, s.window_days)

    # ---- output: volume scaled against a generous 60-PR window
    output = (
        _scale(s.prs_authored, 60) * 0.5
        + _scale(s.lines_added, 20000) * 0.3
        + _scale(s.issues_opened, 20) * 0.2
    )

    # ---- impact: merge rate and how fast things merge
    merge_part = s.merge_rate * 100.0
    if s.median_days_to_merge is None:
        speed_part = 50.0  # unknown, neutral
    else:
        speed_part = _scale(max(0.0, 14.0 - s.median_days_to_merge), 14.0)
    impact = merge_part * 0.6 + speed_part * 0.4

    # ---- consistency: active days across the window + streaks + momentum
    active_part = _scale(s.active_days, min(days, 25))
    streak_part = _scale(s.longest_streak_days, 21)
    momentum_part = 50.0
    if s.momentum == "accelerating":
        momentum_part = 100.0
    elif s.momentum == "steady":
        momentum_part = 65.0
    elif s.momentum == "slowing":
        momentum_part = 25.0
    consistency = active_part * 0.5 + streak_part * 0.3 + momentum_part * 0.2

    # ---- collaboration: reviews and issue engagement
    collaboration = _scale(s.reviews_given, 25) * 0.6 + _scale(s.issues_closed, 15) * 0.4

    # ---- rhythm: how regular the cadence is (PRs per active day near 1 is ideal)
    if s.avg_prs_per_active_day <= 0:
        rhythm = 0.0
    else:
        deviation = abs(s.avg_prs_per_active_day - 1.5)
        rhythm = _scale(max(0.0, 3.0 - deviation), 3.0)

    pillars = [
        Pillar("output", output, WEIGHTS["output"],
               f"{s.prs_authored} PRs, +{s.lines_added:,} lines, {s.issues_opened} issues"),
        Pillar("impact", impact, WEIGHTS["impact"],
               f"{s.merge_rate * 100:.0f}% merge rate, "
               f"{s.median_days_to_merge or 0:.1f}d median merge"),
        Pillar("consistency", consistency, WEIGHTS["consistency"],
               f"{s.active_days} active days, {s.longest_streak_days}d streak"),
        Pillar("collaboration", collaboration, WEIGHTS["collaboration"],
               f"{s.reviews_given} reviews, {s.issues_closed} issues closed"),
        Pillar("rhythm", rhythm, WEIGHTS["rhythm"],
               f"{s.avg_prs_per_active_day:.2f} PRs per active day"),
    ]
    total = sum(p.score * p.weight for p in pillars)
    grade, band = _grade_for(total)

    # ---- burnout risk: long unbroken streaks + heavy output concentration
    risk, reason = "low", "healthy pacing across the window"
    if s.longest_streak_days >= 21 and s.prs_authored >= 20:
        risk, reason = "high", (
            f"{s.longest_streak_days}-day streak with {s.prs_authored} PRs: "
            "no visible rest days"
        )
    elif s.longest_streak_days >= 14 and s.prs_authored >= 10:
        risk, reason = "moderate", (
            f"{s.longest_streak_days}-day streak: consider a deliberate rest day"
        )

    hint = "top decile of tracked contributors" if total >= 85 else (
        "above the median contributor" if total >= 65 else
        "around the median contributor" if total >= 45 else
        "below the median contributor"
    )

    return HealthScore(
        user=activity.user,
        generated_at=activity.generated_at or datetime.now(timezone.utc),
        window_days=s.window_days,
        total=total,
        grade=grade,
        band=band,
        pillars=pillars,
        burnout_risk=risk,
        burnout_reason=reason,
        percentile_hint=hint,
    )


# ------------------------------------------------------------------ renders

BAR_W = 28


def _bar(score: float) -> str:
    filled = int(round(score / 100 * BAR_W))
    return "[" + "#" * filled + "." * (BAR_W - filled) + "]"


def render_score_table(hs: HealthScore) -> str:
    lines = [
        f"prsnoop score | {hs.user}",
        f"window: last {hs.window_days} days",
        "",
        f"  SCORE  {hs.total:5.1f} / 100   grade {hs.grade} ({hs.band})",
        "",
    ]
    for p in hs.pillars:
        lines.append(
            f"  {p.name:<14} {p.score:5.1f}  x{p.weight:.2f}  {_bar(p.score)}"
        )
        lines.append(f"  {'':<14} {p.detail}")
        lines.append("")
    lines.append(f"  burnout risk: {hs.burnout_risk} ({hs.burnout_reason})")
    lines.append(f"  standing    : {hs.percentile_hint}")
    return "\n".join(lines)


def render_score_markdown(hs: HealthScore) -> str:
    out = [
        f"# Health Score: {hs.user}",
        "",
        f"**{hs.total:.1f} / 100** · grade **{hs.grade}** ({hs.band}) · "
        f"window: last {hs.window_days} days",
        "",
        "| Pillar | Score | Weight | Detail |",
        "|---|---:|---:|---|",
    ]
    for p in hs.pillars:
        out.append(f"| {p.name} | {p.score:.1f} | {p.weight:.2f} | {p.detail} |")
    out += [
        "",
        f"**Burnout risk:** {hs.burnout_risk} · {hs.burnout_reason}",
        "",
        f"*{hs.percentile_hint}.*",
        "",
    ]
    return "\n".join(out)


def render_score_json(hs: HealthScore) -> str:
    import json

    return json.dumps(hs.to_dict(), indent=2)
