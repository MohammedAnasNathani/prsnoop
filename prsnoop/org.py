"""Fetch an organization's recent pull request pulse.

One search per window: every PR opened in the org, regardless of author.
From that single result set we derive the org-wide metrics: PRs opened,
merged, still open, unique authors, unique repos, per-author and per-repo
leaderboards, and a day-by-day open/merge chart. No per-PR enrichment is
needed, so even an org with hundreds of PRs in the window costs one
paginated query.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from prsnoop.github import GitHubClient
from prsnoop.models import JsonDict

SEARCH_PATH = "/search/issues"


@dataclass(slots=True)
class OrgPR:
    """One PR opened inside the organization window."""

    repo: str  # org/name
    number: int
    title: str
    url: str
    author: str
    state: str  # merged | open | closed
    created_at: datetime
    merged_at: datetime | None

    @property
    def days_to_merge(self) -> float | None:
        if self.merged_at is None:
            return None
        return (self.merged_at - self.created_at).total_seconds() / 86400.0


@dataclass(slots=True)
class OrgPulse:
    """Derived org-wide statistics for one window.

    ``label`` is "org" or "repo" depending on which subcommand produced
    the pulse; renderers and JSON carry it through.
    """

    org: str
    generated_at: datetime
    window_days: int
    since: str
    until: str
    label: str = "org"
    prs_opened: int = 0
    prs_merged: int = 0
    prs_open: int = 0
    prs_closed_unmerged: int = 0
    authors: int = 0
    repos: int = 0
    median_days_to_merge: float | None = None
    top_authors: list[tuple[str, int]] = field(default_factory=list)
    top_repos: list[tuple[str, int]] = field(default_factory=list)
    day_counts: list[tuple[str, int]] = field(default_factory=list)

    def to_dict(self) -> JsonDict:
        return {
            "org": self.org,
            "label": self.label,
            "generated_at": self.generated_at.isoformat(),
            "window_days": self.window_days,
            "since": self.since,
            "until": self.until,
            "prs_opened": self.prs_opened,
            "prs_merged": self.prs_merged,
            "prs_open": self.prs_open,
            "prs_closed_unmerged": self.prs_closed_unmerged,
            "authors": self.authors,
            "repos": self.repos,
            "median_days_to_merge": self.median_days_to_merge,
            "top_authors": [{"author": a, "prs": n} for a, n in self.top_authors],
            "top_repos": [{"repo": r, "prs": n} for r, n in self.top_repos],
            "day_counts": [{"date": d, "prs": n} for d, n in self.day_counts],
        }


def _parse_iso(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


def fetch_org_pulse(
    client: GitHubClient,
    org: str,
    days: int = 30,
    since: str | None = None,
    until: str | None = None,
) -> tuple[list[OrgPR], OrgPulse]:
    """Return (prs, pulse) for every PR opened in ``org`` within the window."""
    return _fetch_pulse(
        client, f"org:{org}", org, "org", days=days, since=since, until=until
    )


def fetch_repo_pulse(
    client: GitHubClient,
    repo: str,
    days: int = 30,
    since: str | None = None,
    until: str | None = None,
) -> tuple[list[OrgPR], OrgPulse]:
    """Return (prs, pulse) for every PR opened in ``owner/name``.

    Maintainer mode: the same pulse metrics as an org, scoped to one
    repository, so a maintainer sees who is contributing to their project.
    """
    return _fetch_pulse(
        client, f"repo:{repo}", repo, "repo", days=days, since=since, until=until
    )


def _fetch_pulse(
    client: GitHubClient,
    scope: str,
    subject: str,
    label: str,
    days: int = 30,
    since: str | None = None,
    until: str | None = None,
) -> tuple[list[OrgPR], OrgPulse]:
    """Shared pulse fetch for org:X and repo:X search scopes."""
    now = datetime.now(timezone.utc)
    if since is None:
        since = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    if until is None:
        until = now.strftime("%Y-%m-%d")
    range_qualifier = f" created:{since}..{until}"

    items = client.paginate(
        SEARCH_PATH,
        params={"q": f"{scope} is:pr{range_qualifier}"},
    )

    prs: list[OrgPR] = []
    for item in items:
        if "pull_request" not in item:
            continue
        repo_url = item["repository_url"].rstrip("/")
        repo = f"{repo_url.split('/')[-2]}/{repo_url.split('/')[-1]}"
        merged_at = item.get("closed_at") if _was_merged(item) else None
        prs.append(
            OrgPR(
                repo=repo,
                number=item["number"],
                title=item["title"],
                url=item["html_url"],
                author=(item.get("user") or {}).get("login", "unknown"),
                state=_org_state(item),
                created_at=_parse_iso(item["created_at"]),
                merged_at=_parse_iso(merged_at) if merged_at else None,
            )
        )

    pulse = _derive(subject, prs, now, days, since, until)
    pulse.label = label
    return prs, pulse


def _was_merged(item: JsonDict) -> bool:
    pr = item.get("pull_request") or {}
    # Search results carry merged_at only in the pull_request block.
    return bool(pr.get("merged_at"))


def _org_state(item: JsonDict) -> str:
    if _was_merged(item):
        return "merged"
    return "open" if item.get("state") == "open" else "closed"


def _derive(
    org: str,
    prs: list[OrgPR],
    now: datetime,
    window_days: int,
    since: str,
    until: str,
) -> OrgPulse:
    import statistics
    from collections import Counter

    merged = [p for p in prs if p.state == "merged"]
    open_prs = [p for p in prs if p.state == "open"]
    merge_days = sorted(
        d for d in (p.days_to_merge for p in merged) if d is not None
    )
    author_counts = Counter(p.author for p in prs)
    repo_counts = Counter(p.repo for p in prs)
    day_counts = Counter(p.created_at.strftime("%Y-%m-%d") for p in prs)
    ordered_days = sorted(day_counts)

    return OrgPulse(
        org=org,
        generated_at=now,
        window_days=window_days,
        since=since,
        until=until,
        prs_opened=len(prs),
        prs_merged=len(merged),
        prs_open=len(open_prs),
        prs_closed_unmerged=len(prs) - len(merged) - len(open_prs),
        authors=len(author_counts),
        repos=len(repo_counts),
        median_days_to_merge=(
            round(statistics.median(merge_days), 2) if merge_days else None
        ),
        top_authors=author_counts.most_common(10),
        top_repos=repo_counts.most_common(10),
        day_counts=[(d, day_counts[d]) for d in ordered_days],
    )
