"""Responsiveness analytics: the timing truths of a pull request's life.

For every merged/open PR in the window, split the timeline into:
- time to first review (maintainer responsiveness to YOU)
- time to author re-response after that review (YOUR responsiveness)
- total open time

This answers the question every contributor actually has: when my PR sits,
whose side is the silence on? Per-repo and per-PR medians, from real
timeline data already collected — no extra API calls.
"""
from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from prsnoop.github import GitHubClient
from prsnoop.models import Activity, JsonDict


@dataclass(slots=True)
class LatencyRow:
    """One PR's responsiveness timeline."""

    repo: str
    number: int
    title: str
    state: str
    hours_to_first_review: float | None
    hours_to_author_reply: float | None
    total_open_hours: float | None

    @staticmethod
    def _r(v: float | None) -> float | None:
        return round(v, 1) if v is not None else None

    def to_dict(self) -> JsonDict:
        return {
            "repo": self.repo,
            "number": self.number,
            "title": self.title,
            "state": self.state,
            "hours_to_first_review": self._r(self.hours_to_first_review),
            "hours_to_author_reply": self._r(self.hours_to_author_reply),
            "total_open_hours": self._r(self.total_open_hours),
        }


@dataclass(slots=True)
class ResponsivenessReport:
    """Per-repo and overall responsiveness medians."""

    user: str
    generated_at: datetime
    rows: list[LatencyRow] = field(default_factory=list)
    repo_medians: list[JsonDict] = field(default_factory=list)
    overall_first_review_h: float | None = None
    overall_author_reply_h: float | None = None
    overall_open_h: float | None = None
    verdict: str = ""
    scanned: int = 0  # how many PRs had timeline data

    def to_dict(self) -> JsonDict:
        return {
            "user": self.user,
            "generated_at": self.generated_at.isoformat().replace("+00:00", "Z"),
            "overall_first_review_h": (
                round(self.overall_first_review_h, 1)
                if self.overall_first_review_h is not None else None),
            "overall_author_reply_h": (
                round(self.overall_author_reply_h, 1)
                if self.overall_author_reply_h is not None else None),
            "overall_open_h": (
                round(self.overall_open_h, 1)
                if self.overall_open_h is not None else None),
            "verdict": self.verdict,
            "scanned": self.scanned,
            "repo_medians": self.repo_medians,
            "rows": [r.to_dict() for r in self.rows],
        }


def _fetch_latency(
    client: GitHubClient, repo: str, number: int
) -> tuple[datetime | None, datetime | None]:
    """(hours to first non-author review, hours to author reply after it)."""
    try:
        events = client.get(f"/repos/{repo}/pulls/{number}/reviews")
        issue_comments = client.get(f"/repos/{repo}/issues/{number}/comments")
    except Exception:  # noqa: BLE001
        return None, None
    if not isinstance(events, list):
        return None, None
    first_review_at = None
    for rev in events:
        login = (rev.get("user") or {}).get("login", "")
        submitted = rev.get("submitted_at")
        if submitted and login:
            first_review_at = datetime.fromisoformat(
                submitted.replace("Z", "+00:00"))
            break
    if first_review_at is None and isinstance(issue_comments, list):
        for c in issue_comments:
            login = (c.get("user") or {}).get("login", "")
            created = c.get("created_at")
            if created and login:
                first_review_at = datetime.fromisoformat(
                    created.replace("Z", "+00:00"))
                break
    if first_review_at is None:
        return None, None
    # author reply: first author comment after the first review
    author_reply = None
    if isinstance(issue_comments, list):
        for c in issue_comments:
            login = (c.get("user") or {}).get("login", "")
            created = c.get("created_at")
            if not created:
                continue
            at = datetime.fromisoformat(created.replace("Z", "+00:00"))
            if at > first_review_at:
                author_reply = at
                break
    return first_review_at, author_reply


def build_responsiveness(
    activity: Activity, client: GitHubClient, limit: int = 30
) -> ResponsivenessReport:
    """Build the report; fetches per-PR timelines (1-2 calls per PR)."""
    now = datetime.now(timezone.utc)
    rows: list[LatencyRow] = []
    scanned = 0
    for p in activity.prs[:limit]:
        created = p.created_at
        first_review, author_reply = _fetch_latency(
            client, p.repo, p.number)
        end_time = p.merged_at or (
            now if p.state == "open" else None)
        total_h = (
            (end_time - created).total_seconds() / 3600
            if end_time is not None else None
        )
        h_review = (
            (first_review - created).total_seconds() / 3600
            if first_review is not None else None
        )
        h_reply = (
            (author_reply - first_review).total_seconds() / 3600
            if (first_review is not None and author_reply is not None)
            else None
        )
        if first_review is not None:
            scanned += 1
        rows.append(LatencyRow(
            repo=p.repo, number=p.number, title=p.title, state=p.state,
            hours_to_first_review=h_review,
            hours_to_author_reply=h_reply,
            total_open_hours=total_h,
        ))

    def _median(vals: Iterable[float | None]) -> float | None:
        real = [v for v in vals if v is not None]
        return round(statistics.median(real), 1) if real else None

    overall_review = _median([r.hours_to_first_review for r in rows])
    overall_reply = _median([r.hours_to_author_reply for r in rows])
    open_vals = [r.total_open_hours for r in rows
                 if r.total_open_hours is not None]
    overall_open = _median(open_vals)

    # per-repo medians
    by_repo: dict[str, list[LatencyRow]] = {}
    for r in rows:
        by_repo.setdefault(r.repo, []).append(r)
    repo_medians = []
    for repo, group in sorted(by_repo.items(), key=lambda kv: -len(kv[1])):
        repo_medians.append({
            "repo": repo,
            "prs": len(group),
            "median_first_review_h": _median(
                [g.hours_to_first_review for g in group]),
            "median_author_reply_h": _median(
                [g.hours_to_author_reply for g in group]),
        })

    if overall_review is None:
        verdict = "no review data in this window"
    elif overall_reply is not None and overall_reply > overall_review * 2:
        verdict = "the silence is usually on YOUR side"
    elif overall_review > 72:
        verdict = "maintainers leave you waiting"
    else:
        verdict = "healthy turnaround on both sides"

    return ResponsivenessReport(
        user=activity.user,
        generated_at=now,
        rows=rows,
        repo_medians=repo_medians,
        overall_first_review_h=overall_review,
        overall_author_reply_h=overall_reply,
        overall_open_h=overall_open,
        verdict=verdict,
        scanned=scanned,
    )


def render_responsiveness_table(rep: ResponsivenessReport) -> str:
    def fh(v: float | None) -> str:
        if v is None:
            return "-"
        if v < 1:
            return f"{v * 60:.0f}m"
        if v < 48:
            return f"{v:.1f}h"
        return f"{v / 24:.1f}d"

    lines = [
        f"prsnoop responsiveness | {rep.user}",
        f"scanned {rep.scanned} PRs with review activity",
        "",
        f"  median time to first review : {fh(rep.overall_first_review_h)}",
        f"  median time to your reply   : {fh(rep.overall_author_reply_h)}",
        f"  median total open time      : {fh(rep.overall_open_h)}",
        "",
        f"  verdict: {rep.verdict}",
        "",
    ]
    if rep.repo_medians:
        lines.append("  per-repo medians")
        for rm in rep.repo_medians[:10]:
            lines.append(
                f"    {rm['repo']:<30} review {fh(rm['median_first_review_h']):>8}"
                f"  reply {fh(rm['median_author_reply_h']):>8}  ({rm['prs']} prs)")
        lines.append("")
    lines.append("  slowest open waits")
    open_rows = [r for r in rep.rows if r.total_open_hours is not None]
    slow = sorted(
        open_rows, key=lambda r: r.total_open_hours or 0.0, reverse=True)[:8]
    for r in slow:
        lines.append(
            f"    {r.repo}#{r.number:<5} {fh(r.total_open_hours):>8}"
            f"  first review {fh(r.hours_to_first_review):>8}")
    return "\n".join(lines)


def render_responsiveness_markdown(rep: ResponsivenessReport) -> str:
    def fh(v: float | None) -> str:
        if v is None:
            return "-"
        return f"{v:.1f}h" if v < 48 else f"{v / 24:.1f}d"

    out = [
        f"# Responsiveness: {rep.user}",
        "",
        f"Scanned **{rep.scanned}** PRs with review activity.",
        "",
        "| Metric | Median |",
        "|---|---:|",
        f"| Time to first review | {fh(rep.overall_first_review_h)} |",
        f"| Time to your reply | {fh(rep.overall_author_reply_h)} |",
        f"| Total open time | {fh(rep.overall_open_h)} |",
        "",
        f"**Verdict:** {rep.verdict}.",
        "",
        "| Repo | PRs | First review | Your reply |",
        "|---|---:|---:|---:|",
    ]
    for rm in rep.repo_medians[:10]:
        out.append(
            f"| {rm['repo']} | {rm['prs']} | "
            f"{fh(rm['median_first_review_h'])} | {fh(rm['median_author_reply_h'])} |")
    out.append("")
    return "\n".join(out)
