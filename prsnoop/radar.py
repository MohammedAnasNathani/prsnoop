"""Maintainer triage radar: every open PR on a repo, ranked by waiting age.

The report a maintainer actually wants on Monday morning: which open
pull requests have been sitting the longest, how stale each one is, and
where the queue is piling up. One list endpoint per repo, so the whole
radar costs a handful of API calls even on busy repositories.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from prsnoop.github import GitHubClient
from prsnoop.models import JsonDict

FRESH = "fresh"      # <= 2 days old
AGING = "aging"      # 3 to 13 days
STALE = "stale"      # 14 to 29 days
ANCIENT = "ancient"  # 30 or more

BUCKET_ORDER = (FRESH, AGING, STALE, ANCIENT)
BUCKET_MARK = {FRESH: ".", AGING: "~", STALE: "!", ANCIENT: "##"}


def bucket_for(age_days: int) -> str:
    if age_days <= 2:
        return FRESH
    if age_days <= 13:
        return AGING
    if age_days <= 29:
        return STALE
    return ANCIENT


@dataclass(slots=True)
class RadarEntry:
    """One open pull request waiting on a maintainer."""

    repo: str
    number: int
    title: str
    url: str
    author: str
    created_at: datetime
    updated_at: datetime | None
    age_days: int
    bucket: str
    draft: bool = False
    labels: list[str] = field(default_factory=list)
    comments: int = 0

    @property
    def is_quiet(self) -> bool:
        """No comments and no recent push: the silent, rotting kind."""
        return self.comments == 0 and self.bucket in (STALE, ANCIENT)

    def to_dict(self) -> JsonDict:
        return {
            "repo": self.repo,
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "author": self.author,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": (
                self.updated_at.isoformat().replace("+00:00", "Z")
                if self.updated_at
                else None
            ),
            "age_days": self.age_days,
            "bucket": self.bucket,
            "draft": self.draft,
            "labels": self.labels,
            "comments": self.comments,
            "quiet": self.is_quiet,
        }


@dataclass(slots=True)
class RadarReport:
    """The whole open-queue picture for one repository."""

    repo: str
    generated_at: datetime
    entries: list[RadarEntry] = field(default_factory=list)  # oldest first
    truncated: bool = False

    @property
    def total_open(self) -> int:
        return len(self.entries)

    @property
    def buckets(self) -> dict[str, int]:
        counts = {b: 0 for b in BUCKET_ORDER}
        for e in self.entries:
            counts[e.bucket] += 1
        return counts

    @property
    def median_age_days(self) -> float | None:
        ages = sorted(e.age_days for e in self.entries)
        if not ages:
            return None
        mid = len(ages) // 2
        if len(ages) % 2:
            return float(ages[mid])
        return (ages[mid - 1] + ages[mid]) / 2

    @property
    def quiet_count(self) -> int:
        return sum(1 for e in self.entries if e.is_quiet)

    def to_dict(self) -> JsonDict:
        return {
            "repo": self.repo,
            "generated_at": self.generated_at.isoformat().replace(
                "+00:00", "Z"
            ),
            "total_open": self.total_open,
            "buckets": self.buckets,
            "median_age_days": self.median_age_days,
            "quiet": self.quiet_count,
            "truncated": self.truncated,
            "entries": [e.to_dict() for e in self.entries],
        }


def fetch_radar(
    client: GitHubClient, repo: str, limit: int = 300
) -> RadarReport:
    """Scan the open pull queue of ``repo`` (owner/name)."""
    now = datetime.now(timezone.utc)
    items = client.paginate(
        f"/repos/{repo}/pulls",
        params={"state": "open", "per_page": "100"},
    )
    entries: list[RadarEntry] = []
    for item in items:
        if len(entries) >= limit:
            truncated = True
            break
        created = datetime.fromisoformat(
            item["created_at"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        updated_raw = item.get("updated_at")
        updated = (
            datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            if updated_raw
            else None
        )
        age_days = max(0, (now - created).days)
        entries.append(
            RadarEntry(
                repo=repo,
                number=item["number"],
                title=item.get("title", ""),
                url=item.get("html_url", ""),
                author=(item.get("user") or {}).get("login", "unknown"),
                created_at=created,
                updated_at=updated,
                age_days=age_days,
                bucket=bucket_for(age_days),
                draft=bool(item.get("draft", False)),
                labels=[
                    lb.get("name", "")
                    for lb in (item.get("labels") or [])
                    if lb.get("name")
                ],
                comments=item.get("comments", 0) or 0,
            )
        )
    else:
        truncated = False
    entries.sort(key=lambda e: (-e.age_days, e.number))
    return RadarReport(
        repo=repo, generated_at=now, entries=entries, truncated=truncated
    )


# ------------------------------------------------------------------ renders


def _fmt_entry_title(title: str, width: int = 52) -> str:
    flat = " ".join(title.split())
    if len(flat) > width:
        return flat[: width - 1] + "…"
    return flat


def render_radar_table(report: RadarReport) -> str:
    """The Monday-morning triage list."""
    buckets = report.buckets
    median = report.median_age_days
    lines = [f"prsnoop radar | {report.repo}"]
    if report.total_open == 0:
        lines += ["", "  queue is clear: no open pull requests"]
        return "\n".join(lines)
    head = (
        f"open PRs: {report.total_open} | median age {median:.1f}d"
        if median is not None
        else f"open PRs: {report.total_open}"
    )
    lines += [
        head,
        "buckets: "
        + " | ".join(f"{b} {buckets[b]}" for b in BUCKET_ORDER)
        + f" | quiet (no comments, old): {report.quiet_count}",
        "",
        f"  {'#':>5}  {'age':>4}  {'bucket':<8}{'author':<16} title",
        f"  {'-':>5}  {'-':>4}  {'-':<8}{'-':<16} {'-' * 52}",
    ]
    for e in report.entries[:40]:
        mark = BUCKET_MARK[e.bucket]
        draft = " (draft)" if e.draft else ""
        lines.append(
            f"  {e.number:>5}  {e.age_days:>3}d {mark:<7}"
            f"{e.author:<16} {_fmt_entry_title(e.title)}{draft}"
        )
    if report.truncated:
        lines.append("  ... and more (capped at 40 shown)")
    return "\n".join(lines)


def render_radar_markdown(report: RadarReport) -> str:
    """Paste-ready triage table for issues and standup notes."""
    out = [
        f"# Radar: {report.repo}",
        "",
        "_Generated by [prsnoop](https://github.com/MohammedAnasNathani/prsnoop)_",
        "",
    ]
    if report.total_open == 0:
        out.append("Queue is clear: no open pull requests.")
        return "\n".join(out)
    buckets = report.buckets
    out.append(
        f"**{report.total_open}** open · median age"
        f" **{report.median_age_days:.1f}d** · quiet: {report.quiet_count}"
    )
    out.append("")
    out.append(
        " | ".join(f"{b} {buckets[b]}" for b in BUCKET_ORDER)
    )
    out.append("")
    out += [
        "| # | Age | Bucket | Author | Title |",
        "|---:|---:|---|---|---|",
    ]
    for e in report.entries:
        title = xml_escape(e.title).replace("|", "\\|")
        link = f"[#{e.number}]({e.url})" if e.url else f"#{e.number}"
        draft = " *(draft)*" if e.draft else ""
        out.append(
            f"| {link} | {e.age_days}d | {e.bucket} |"
            f" @{e.author} | {title}{draft} |"
        )
    out.append("")
    return "\n".join(out)


def render_radar_csv(report: RadarReport) -> str:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["number", "age_days", "bucket", "author", "draft", "comments", "title"]
    )
    for e in report.entries:
        writer.writerow(
            [e.number, e.age_days, e.bucket, e.author, e.draft, e.comments,
             e.title]
        )
    return buf.getvalue()
