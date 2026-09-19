"""Forecast: linear-regression projections of contribution volume.

Fits a least-squares line over the daily activity counts, extrapolates the
next N days, and derives pace statements: PRs per week, projected month,
projected year, and whether the trajectory is rising or falling.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from prsnoop.models import Activity, JsonDict


@dataclass(slots=True)
class Forecast:
    """Linear projection of the daily activity series."""

    user: str
    generated_at: datetime
    window_days: int
    horizon_days: int
    daily_slope: float          # items/day trend
    pr_slope: float             # PRs/day trend
    projected_items: int        # items in the next horizon
    projected_prs: int          # PRs in the next horizon
    prs_per_week: float
    prs_per_month: float
    prs_per_year: int
    direction: str              | None  # rising | steady | falling
    confidence: str             # high | medium | low
    r_squared: float

    def to_dict(self) -> JsonDict:
        return {
            "user": self.user,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "window_days": self.window_days,
            "horizon_days": self.horizon_days,
            "daily_slope": round(self.daily_slope, 4),
            "pr_slope": round(self.pr_slope, 4),
            "projected_items": self.projected_items,
            "projected_prs": self.projected_prs,
            "prs_per_week": round(self.prs_per_week, 2),
            "prs_per_month": round(self.prs_per_month, 1),
            "prs_per_year": self.prs_per_year,
            "direction": self.direction,
            "confidence": self.confidence,
            "r_squared": round(self.r_squared, 4),
        }


def _linfit(points: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Least-squares y = a*x + b over points; returns (a, b, r_squared)."""
    n = len(points)
    if n < 2:
        return 0.0, (points[0][1] if points else 0.0), 0.0
    mx = sum(x for x, _ in points) / n
    my = sum(y for _, y in points) / n
    sxx = sum((x - mx) ** 2 for x, _ in points)
    sxy = sum((x - mx) * (y - my) for x, y in points)
    syy = sum((y - my) ** 2 for _, y in points)
    if sxx == 0:
        return 0.0, my, 0.0
    a = sxy / sxx
    b = my - a * mx
    r2 = 0.0 if syy == 0 else (sxy * sxy) / (sxx * syy)
    return a, b, r2


def build_forecast(activity: Activity, horizon_days: int = 30) -> Forecast:
    """Fit the daily series and project the next horizon."""
    s = activity.stats
    total_days = {}
    pr_days = {}
    for da in s.day_activity:
        try:
            d = date.fromisoformat(da.date)
        except ValueError:
            continue
        total_days[d] = da.total
        pr_days[d] = da.prs

    if total_days:
        d_min, d_max = min(total_days), max(total_days)
    else:
        d_max = activity.generated_at.date() if activity.generated_at else date.today()
        d_min = d_max - timedelta(days=s.window_days)

    series: list[tuple[float, float]] = []
    pr_series: list[tuple[float, float]] = []
    span = (d_max - d_min).days
    for k in range(span + 1):
        d = d_min + timedelta(days=k)
        series.append((float(k), float(total_days.get(d, 0))))
        pr_series.append((float(k), float(pr_days.get(d, 0))))

    a, b, r2 = _linfit(series)
    ap, bp, _ = _linfit(pr_series)

    # projections are clamped at zero: negative contribution counts make no sense
    projected_items = max(0, int(round(sum(max(0.0, a * (span + 1 + k) + b)
                                          for k in range(horizon_days)))))
    projected_prs = max(0, int(round(sum(max(0.0, ap * (span + 1 + k) + bp)
                                        for k in range(horizon_days)))))

    prs_per_week = max(0.0, ap * 7)
    direction = None
    if ap > 0.02:
        direction = "rising"
    elif ap < -0.02:
        direction = "falling"
    else:
        direction = "steady"
    confidence = "high" if r2 >= 0.5 and len(series) >= 14 else (
        "medium" if r2 >= 0.2 else "low"
    )

    return Forecast(
        user=activity.user,
        generated_at=activity.generated_at or datetime.now(timezone.utc),
        window_days=s.window_days,
        horizon_days=horizon_days,
        daily_slope=a,
        pr_slope=ap,
        projected_items=projected_items,
        projected_prs=projected_prs,
        prs_per_week=prs_per_week,
        prs_per_month=ap * 30,
        prs_per_year=int(max(0.0, ap * 365)),
        direction=direction,
        confidence=confidence,
        r_squared=r2,
    )


# ------------------------------------------------------------------ renders

CHART_W = 58
CHART_H = 12


def render_ascii_chart(f: Forecast) -> str:
    """Actual daily PRs vs the fitted trend, extended into the horizon."""
    grid = [[" "] * CHART_W for _ in range(CHART_H)]
    a, b = f.pr_slope, 0.0
    n = CHART_W
    # approximate the series for the chart from slope/intercept reconstructed values
    peak = max(1.0, a * n + abs(b), 1.0)
    for x in range(n):
        fit = max(0.0, a * x * (f.window_days / n) + b)
        y = CHART_H - 1 - int(fit / peak * (CHART_H - 1))
        y = max(0, min(CHART_H - 1, y))
        grid[y][x] = "-" if x < n * 0.7 else "~"
    rows = ["".join(r) for r in grid]
    header = f"prs/day trend ({f.direction}, {f.confidence} confidence)"
    out = [header, "+" + "-" * CHART_W + "+"]
    out += ["|" + r + "|" for r in rows]
    out += ["+" + "-" * CHART_W + "+"]
    out.append("past trend '-' -> dashed '~' = projected")
    return "\n".join(out)


def render_forecast_table(f: Forecast) -> str:
    lines = [
        f"prsnoop forecast | {f.user}",
        f"window: last {f.window_days} days -> horizon: next {f.horizon_days} days",
        "",
        f"  trajectory     {f.direction} ({f.confidence} confidence, R2 {f.r_squared:.2f})",
        f"  pace           {f.prs_per_week:.1f} PRs/week · {f.prs_per_month:.1f} PRs/month",
        "",
        f"  next {f.horizon_days} days  ~{f.projected_prs} PRs,"
        f" ~{f.projected_items} items",
        f"  next 365 days  ~{f.prs_per_year} PRs",
        "",
        render_ascii_chart(f),
    ]
    return "\n".join(lines)


def render_forecast_markdown(f: Forecast) -> str:
    out = [
        f"# Forecast: {f.user}",
        "",
        f"Trajectory: **{f.direction}** ({f.confidence} confidence, R2 {f.r_squared:.2f}).",
        "",
        "| Metric | Projection |",
        "|---|---:|",
        f"| PRs per week | {f.prs_per_week:.1f} |",
        f"| PRs per month | {f.prs_per_month:.1f} |",
        f"| PRs next {f.horizon_days} days | ~{f.projected_prs} |",
        f"| PRs next 365 days | ~{f.prs_per_year} |",
        f"| All activity next {f.horizon_days} days | ~{f.projected_items} |",
        "",
        "_Linear least-squares fit over the window's daily series; clamped at zero. "
        "Generated by [prsnoop](https://github.com/MohammedAnasNathani/prsnoop)._",
        "",
    ]
    return "\n".join(out)


def render_forecast_json(f: Forecast) -> str:
    import json

    return json.dumps(f.to_dict(), indent=2)
