"""Data models shared across fetchers, stats, and renderers."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

MERGED = "merged"
OPEN = "open"
CLOSED = "closed"

# A parsed GitHub API JSON object / list.
JsonDict = dict[str, Any]
JsonList = list[Any]


def _parse_iso(value: str) -> datetime:
    """Parse a GitHub API timestamp ('2026-07-15T16:51:51Z') into aware UTC."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def _dt(value: datetime) -> str:
    """Serialize to a stable ISO-8601 UTC string."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class PRRecord:
    """A pull request authored by the user."""

    repo: str
    number: int
    title: str
    url: str
    state: str  # MERGED | OPEN | CLOSED
    created_at: datetime
    merged_at: datetime | None
    additions: int
    deletions: int
    changed_files: int
    labels: list[str] = field(default_factory=list)
    comments: int = 0
    draft: bool = False
    language: str = "Unknown"  # primary language of the repo, set by fetcher

    @property
    def days_to_merge(self) -> float | None:
        if self.merged_at is None:
            return None
        return (self.merged_at - self.created_at).total_seconds() / 86400.0

    @property
    def net_lines(self) -> int:
        return self.additions - self.deletions

    @classmethod
    def from_api(cls, pr: JsonDict, repo: str) -> PRRecord:
        merged_at = pr.get("merged_at")
        state = MERGED if merged_at else (OPEN if pr["state"] == "open" else CLOSED)
        raw_labels = pr.get("labels") or []
        labels = [lb.get("name", "") for lb in raw_labels if lb.get("name")]
        return cls(
            repo=repo,
            number=pr["number"],
            title=pr["title"],
            url=pr["html_url"],
            state=state,
            created_at=_parse_iso(pr["created_at"]),
            merged_at=_parse_iso(merged_at) if merged_at else None,
            additions=pr.get("additions", 0) or 0,
            deletions=pr.get("deletions", 0) or 0,
            changed_files=pr.get("changed_files", 0) or 0,
            labels=labels,
            comments=pr.get("comments", 0) or 0,
            draft=bool(pr.get("draft", False)),
        )

    @classmethod
    def from_dict(cls, d: JsonDict) -> PRRecord:
        """Rebuild a PRRecord from to_dict output (offline replay)."""
        merged_at = d.get("merged_at")
        return cls(
            repo=d["repo"],
            number=d["number"],
            title=d["title"],
            url=d["url"],
            state=d["state"],
            created_at=_parse_iso(d["created_at"]),
            merged_at=_parse_iso(merged_at) if merged_at else None,
            additions=d.get("additions", 0) or 0,
            deletions=d.get("deletions", 0) or 0,
            changed_files=d.get("changed_files", 0) or 0,
            labels=list(d.get("labels") or []),
            comments=d.get("comments", 0) or 0,
            draft=bool(d.get("draft", False)),
            language=d.get("language", "Unknown"),
        )

    def to_dict(self) -> JsonDict:
        d = asdict(self)
        d["created_at"] = _dt(self.created_at)
        d["merged_at"] = _dt(self.merged_at) if self.merged_at else None
        return d


@dataclass(slots=True)
class ReviewRecord:
    """A review the user left on someone else's pull request."""

    repo: str
    pr_number: int
    pr_title: str
    pr_url: str
    state: str  # APPROVED | CHANGES_REQUESTED | COMMENTED | DISMISSED
    submitted_at: datetime

    @classmethod
    def from_api(cls, review: JsonDict, repo: str) -> ReviewRecord:
        return cls(
            repo=repo,
            pr_number=review["pr_number"],
            pr_title=review["pr_title"],
            pr_url=review["pr_url"],
            state=review["state"],
            submitted_at=_parse_iso(review["submitted_at"]),
        )

    @classmethod
    def from_dict(cls, d: JsonDict) -> ReviewRecord:
        return cls(
            repo=d["repo"],
            pr_number=d["pr_number"],
            pr_title=d["pr_title"],
            pr_url=d["pr_url"],
            state=d["state"],
            submitted_at=_parse_iso(d["submitted_at"]),
        )

    def to_dict(self) -> JsonDict:
        d = asdict(self)
        d["submitted_at"] = _dt(self.submitted_at)
        return d


@dataclass(slots=True)
class IssueRecord:
    """An issue authored by the user."""

    repo: str
    number: int
    title: str
    url: str
    state: str  # OPEN | CLOSED
    created_at: datetime
    closed_at: datetime | None
    comments: int

    @classmethod
    def from_api(cls, issue: JsonDict, repo: str) -> IssueRecord:
        closed_at = issue.get("closed_at")
        return cls(
            repo=repo,
            number=issue["number"],
            title=issue["title"],
            url=issue["html_url"],
            state=OPEN if issue["state"] == "open" else CLOSED,
            created_at=_parse_iso(issue["created_at"]),
            closed_at=_parse_iso(closed_at) if closed_at else None,
            comments=issue.get("comments", 0) or 0,
        )

    @classmethod
    def from_dict(cls, d: JsonDict) -> IssueRecord:
        closed_at = d.get("closed_at")
        return cls(
            repo=d["repo"],
            number=d["number"],
            title=d["title"],
            url=d["url"],
            state=d["state"],
            created_at=_parse_iso(d["created_at"]),
            closed_at=_parse_iso(closed_at) if closed_at else None,
            comments=d.get("comments", 0) or 0,
        )

    def to_dict(self) -> JsonDict:
        d = asdict(self)
        d["created_at"] = _dt(self.created_at)
        d["closed_at"] = _dt(self.closed_at) if self.closed_at else None
        return d


@dataclass(slots=True)
class DayActivity:
    """Activity counts for one calendar day (UTC)."""

    date: str  # YYYY-MM-DD
    prs: int = 0
    merged: int = 0
    issues: int = 0
    reviews: int = 0

    @property
    def total(self) -> int:
        return self.prs + self.merged + self.issues + self.reviews

    @classmethod
    def from_dict(cls, d: JsonDict) -> DayActivity:
        return cls(
            date=d["date"],
            prs=d.get("prs", 0),
            merged=d.get("merged", 0),
            issues=d.get("issues", 0),
            reviews=d.get("reviews", 0),
        )

    def to_dict(self) -> JsonDict:
        return {
            "date": self.date,
            "prs": self.prs,
            "merged": self.merged,
            "issues": self.issues,
            "reviews": self.reviews,
            "total": self.total,
        }


@dataclass(slots=True)
class RepoPerformance:
    """How one repository treats this contributor's work."""

    repo: str
    prs: int
    merged: int
    merge_rate: float
    median_days_to_merge: float | None

    def to_dict(self) -> JsonDict:
        return {
            "repo": self.repo,
            "prs": self.prs,
            "merged": self.merged,
            "merge_rate": self.merge_rate,
            "median_days_to_merge": self.median_days_to_merge,
        }


@dataclass(slots=True)
class Stats:
    """Aggregated contribution statistics."""

    user: str
    generated_at: datetime
    window_days: int = 30
    since: str = ""  # YYYY-MM-DD
    until: str = ""
    prs_authored: int = 0
    prs_merged: int = 0
    prs_open: int = 0
    prs_closed_unmerged: int = 0
    reviews_given: int = 0
    issues_opened: int = 0
    issues_closed: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    merge_rate: float = 0.0  # merged / authored, 0.0 when nothing authored
    median_days_to_merge: float | None = None
    p90_days_to_merge: float | None = None
    fastest_merge_days: float | None = None
    slowest_merge_days: float | None = None
    first_pr_date: str | None = None
    last_activity_date: str | None = None
    active_days: int = 0
    longest_streak_days: int = 0
    current_streak_days: int = 0
    avg_prs_per_active_day: float = 0.0
    busiest_day: str | None = None  # date with most items
    busiest_day_count: int = 0
    distinct_repos: int = 0
    distinct_languages: int = 0
    top_repos: list[tuple[str, int]] = field(default_factory=list)
    languages: list[tuple[str, int]] = field(default_factory=list)  # (lang, prs)
    day_activity: list[DayActivity] = field(default_factory=list)
    size_median_lines: int | None = None
    size_buckets: dict[str, int] = field(default_factory=dict)
    repo_performance: list[RepoPerformance] = field(default_factory=list)
    momentum: str | None = None  # accelerating | steady | slowing
    momentum_pct: float | None = None  # second half vs first half

    @classmethod
    def from_dict(cls, d: JsonDict) -> Stats:
        """Rebuild Stats from to_dict output (offline replay)."""
        d = dict(d)
        day_activity = [DayActivity.from_dict(da) for da in d.pop("day_activity", [])]
        top_repos = [(t["repo"], t["prs"]) for t in d.pop("top_repos", [])]
        languages = [
            (lang["language"], lang["prs"]) for lang in d.pop("languages", [])
        ]
        repo_performance = [RepoPerformance(**r) for r in d.pop("repo_performance", [])]
        generated_at = _parse_iso(d.pop("generated_at"))
        return cls(
            generated_at=generated_at,
            day_activity=day_activity,
            top_repos=top_repos,
            languages=languages,
            repo_performance=repo_performance,
            **d,
        )

    def to_dict(self) -> JsonDict:
        d = asdict(self)
        d["generated_at"] = _dt(self.generated_at)
        d["top_repos"] = [{"repo": repo, "prs": n} for repo, n in self.top_repos]
        d["languages"] = [{"language": lang, "prs": n} for lang, n in self.languages]
        d["day_activity"] = [da.to_dict() for da in self.day_activity]
        return d


@dataclass(slots=True)
class Activity:
    """Everything we snooped for one user, plus derived stats."""

    user: str
    generated_at: datetime
    prs: list[PRRecord]
    reviews: list[ReviewRecord]
    issues: list[IssueRecord]
    stats: Stats
    trend: list[Any] = field(default_factory=list)  # TrendDelta objects, set by cli

    @classmethod
    def from_dict(cls, d: JsonDict) -> Activity:
        """Rebuild a full Activity from to_dict output (offline replay)."""
        # Imported here so models stays importable without stats (which
        # imports models at module load).
        from prsnoop.stats import TrendDelta

        trend_raw = d.get("trend") or []
        trend = [TrendDelta.from_dict(t) for t in trend_raw]
        return cls(
            user=d["user"],
            generated_at=_parse_iso(d["generated_at"]),
            prs=[PRRecord.from_dict(p) for p in d.get("prs", [])],
            reviews=[ReviewRecord.from_dict(r) for r in d.get("reviews", [])],
            issues=[IssueRecord.from_dict(i) for i in d.get("issues", [])],
            stats=Stats.from_dict(d["stats"]),
            trend=trend,
        )

    def to_dict(self) -> JsonDict:
        d = {
            "user": self.user,
            "generated_at": _dt(self.generated_at),
            "prs": [p.to_dict() for p in self.prs],
            "reviews": [r.to_dict() for r in self.reviews],
            "issues": [i.to_dict() for i in self.issues],
            "stats": self.stats.to_dict(),
        }
        if self.trend:
            d["trend"] = [t.to_dict() if hasattr(t, "to_dict") else t for t in self.trend]
        return d
