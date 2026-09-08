"""Changelog generator: turn merged pull requests into release notes.

Point it at a repository (optionally from a tag) and it collects the
merged PRs in the window, groups them into human sections by label and
conventional-commit prefix, and emits paste-ready markdown. The output
follows the "What's Changed" shape used by thousands of release notes,
so it drops straight into a release page or CHANGELOG.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape as xml_escape

from prsnoop.github import GitHubClient
from prsnoop.models import JsonDict

CATEGORY_ORDER = (
    "Breaking changes",
    "Added",
    "Fixed",
    "Performance",
    "Changed",
    "Documentation",
    "Tests",
    "Dependencies",
    "Other",
)

_PREFIX_CATEGORIES = (
    ("breaking", "Breaking changes"),
    ("feat", "Added"),
    ("feature", "Added"),
    ("add", "Added"),
    ("fix", "Fixed"),
    ("perf", "Performance"),
    ("refactor", "Changed"),
    ("docs", "Documentation"),
    ("doc", "Documentation"),
    ("test", "Tests"),
    ("deps", "Dependencies"),
    ("dep", "Dependencies"),
    ("bump", "Dependencies"),
)

_LABEL_CATEGORIES = {
    "breaking": "Breaking changes",
    "breaking change": "Breaking changes",
    "feature": "Added",
    "enhancement": "Added",
    "feat": "Added",
    "bug": "Fixed",
    "bugfix": "Fixed",
    "fix": "Fixed",
    "performance": "Performance",
    "perf": "Performance",
    "refactor": "Changed",
    "documentation": "Documentation",
    "docs": "Documentation",
    "tests": "Tests",
    "test": "Tests",
    "dependencies": "Dependencies",
    "dependency": "Dependencies",
    "deps": "Dependencies",
}

# First plain word of a title, for PRs that skip the conventional prefix.
_LEADING_WORD_CATEGORIES = (
    ("add", "Added"),
    ("fix", "Fixed"),
    ("bump", "Dependencies"),
)


def categorize(title: str, labels: list[str]) -> str:
    """Map one merged PR to a changelog section."""
    low_labels = [lb.lower().strip() for lb in labels]
    for lb in low_labels:
        if lb in _LABEL_CATEGORIES:
            return _LABEL_CATEGORIES[lb]
    low_title = title.lower().strip()
    for prefix, category in _PREFIX_CATEGORIES:
        if low_title.startswith(prefix + ":") or low_title.startswith(
            prefix + "("
        ):
            return category
    if "breaking" in low_title:
        return "Breaking changes"
    # Real-world titles rarely carry the colon: 'Fix crash on load',
    # 'Bump requests from 2.0 to 2.1'.
    for word, category in _LEADING_WORD_CATEGORIES:
        if low_title.startswith(word + " "):
            return category
    return "Other"


@dataclass(slots=True)
class ChangelogEntry:
    """One merged PR, ready for a release note bullet."""

    number: int
    title: str
    url: str
    author: str
    labels: list[str] = field(default_factory=list)
    merged_at: datetime | None = None
    category: str = "Other"

    @property
    def flat_title(self) -> str:
        return " ".join(self.title.split())

    def to_dict(self) -> JsonDict:
        return {
            "number": self.number,
            "title": self.title,
            "url": self.url,
            "author": self.author,
            "labels": self.labels,
            "merged_at": (
                self.merged_at.isoformat().replace("+00:00", "Z")
                if self.merged_at
                else None
            ),
            "category": self.category,
        }


@dataclass(slots=True)
class Changelog:
    """Merged-PR release notes for one repository window."""

    repo: str
    since: str  # YYYY-MM-DD or empty
    until: str
    entries: list[ChangelogEntry] = field(default_factory=list)
    truncated: bool = False

    @property
    def categories(self) -> dict[str, list[ChangelogEntry]]:
        grouped: dict[str, list[ChangelogEntry]] = {}
        for cat in CATEGORY_ORDER:
            grouped.setdefault(cat, [])
        for e in self.entries:
            grouped[e.category].append(e)
        return grouped

    @property
    def contributors(self) -> list[str]:
        seen: list[str] = []
        for e in self.entries:
            if e.author and e.author not in seen:
                seen.append(e.author)
        return seen

    def to_dict(self) -> JsonDict:
        return {
            "repo": self.repo,
            "since": self.since,
            "until": self.until,
            "truncated": self.truncated,
            "contributors": self.contributors,
            "entries": [e.to_dict() for e in self.entries],
        }


def resolve_tag_date(
    client: GitHubClient, repo: str, tag: str
) -> datetime | None:
    """The commit date a tag points at, for 'merged since v1.2.0' windows.

    Walks the ref: a lightweight tag points straight at the commit, an
    annotated tag points at a tag object first.
    """
    try:
        ref = client.get(f"/repos/{repo}/git/ref/tags/{tag}")
        if not isinstance(ref, dict):
            return None
        sha = ref["object"]["sha"]
        kind = ref["object"]["type"]
        if kind == "tag":
            obj = client.get(f"/repos/{repo}/git/tags/{sha}")
            if not isinstance(obj, dict):
                return None
            sha = obj["object"]["sha"]
        commit = client.get(f"/repos/{repo}/commits/{sha}")
        if not isinstance(commit, dict):
            return None
        date_raw = commit["commit"]["committer"]["date"]
        return datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001  a bad tag should not kill the report
        return None


def build_changelog(
    client: GitHubClient,
    repo: str,
    days: int = 30,
    since: str | None = None,
    until: str | None = None,
    tag: str | None = None,
    limit: int = 200,
) -> Changelog:
    """Collect merged PRs for ``repo`` in the window and categorize them."""
    now = datetime.now(timezone.utc)
    if since is None:
        if tag:
            tag_date = resolve_tag_date(client, repo, tag)
            if tag_date is not None:
                since = tag_date.strftime("%Y-%m-%d")
        if since is None:
            since = (now - timedelta(days=days)).strftime("%Y-%m-%d")
    bound = f"merged:{since}..{until}" if until else f"merged:>={since}"
    items = client.paginate(
        "/search/issues", params={"q": f"repo:{repo} is:pr is:merged {bound}"}
    )
    entries: list[ChangelogEntry] = []
    truncated = False
    for item in items:
        if len(entries) >= limit:
            truncated = True
            break
        merged_raw = item.get("pull_request", {}).get("merged_at")
        merged_at = (
            datetime.fromisoformat(merged_raw.replace("Z", "+00:00"))
            if merged_raw
            else None
        )
        labels = [
            lb.get("name", "")
            for lb in (item.get("labels") or [])
            if lb.get("name")
        ]
        entries.append(
            ChangelogEntry(
                number=item["number"],
                title=item.get("title", ""),
                url=item.get("html_url", ""),
                author=(item.get("user") or {}).get("login", "unknown"),
                labels=labels,
                merged_at=merged_at,
                category=categorize(item.get("title", ""), labels),
            )
        )
    else:
        truncated = False
    entries.sort(key=lambda e: e.merged_at or now, reverse=True)
    return Changelog(
        repo=repo, since=since, until=until or "", entries=entries,
        truncated=truncated,
    )


def render_changelog_markdown(ch: Changelog) -> str:
    """Paste-ready release notes: one bullet per PR, grouped by type."""
    window = (
        f" from `{ch.since}` to `{ch.until}`"
        if ch.until
        else f" since `{ch.since}`"
    )
    out = [
        "## What's changed",
        "",
        f"_Merged pull requests for `{ch.repo}`{window}_",
        "",
    ]
    for cat, entries in ch.categories.items():
        if not entries:
            continue
        out.append(f"### {cat}")
        out.append("")
        for e in entries:
            title = xml_escape(e.flat_title).replace("|", "\\|")
            link = f"[#{e.number}]({e.url})" if e.url else f"#{e.number}"
            out.append(f"- {title} ({link}) @{e.author}")
        out.append("")
    out.append(
        f"**{len(ch.entries)}** merged pull requests from"
        f" **{len(ch.contributors)}** contributors. Generated by"
        f" [prsnoop](https://github.com/MohammedAnasNathani/prsnoop)."
    )
    if ch.truncated:
        out += ["", "_Note: entry list capped, totals are partial._"]
    return "\n".join(out)


def render_changelog_json(ch: Changelog) -> str:
    import json

    return json.dumps(ch.to_dict(), indent=2)
