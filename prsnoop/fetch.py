"""Fetch a user's PRs, reviews, and issues from the GitHub API.

Strategy
--------
* PRs and issues come from the Search API (``is:pr`` / ``is:issue`` filters)
  with optional ``org:`` scoping and absolute ``--since/--until`` dates.
* Diff stats (additions/deletions/changed_files) are not in search results,
  so each PR is enriched with one cached call to the pulls endpoint. For
  very large result sets the enrichment budget stops early and the report
  notes that lines-changed totals are partial.
* The primary language of each PR's repository is fetched once per repo
  (cached) to build the language mix.
* Reviews cannot be searched directly. We scan the reviews endpoint of each
  PR the user interacted with and keep reviews on PRs they did not author.
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import TypeVar

from prsnoop.github import GitHubClient
from prsnoop.models import (
    IssueRecord,
    JsonDict,
    PRRecord,
    ReviewRecord,
)

log = logging.getLogger("prsnoop")

T = TypeVar("T")
R = TypeVar("R")

# Called as work completes: (done, total).
Progress = Callable[[int, int], None]

SEARCH_PATH = "/search/issues"

# Stop per-PR enrichment beyond this many PRs: high-volume users would
# otherwise spend minutes of API budget for marginal stats.
ENRICH_BUDGET = 300


def _repo_of(item: JsonDict) -> str:
    """'https://api.github.com/repos/owner/name' -> 'owner/name'."""
    parts = item["repository_url"].rstrip("/").split("/")
    return f"{parts[-2]}/{parts[-1]}"


def _cutoff(days: int) -> str:
    """YYYY-MM-DD ``days`` days ago (UTC)."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


# Per-PR detail fetches are one small GET each and dominate wall time, so
# they run concurrently. Eight hides the round-trip latency while staying
# well inside GitHub's secondary rate limits. Override with PRSNOOP_WORKERS.
DEFAULT_WORKERS = 8
_MIN_PARALLEL = 4


def _workers() -> int:
    raw = os.environ.get("PRSNOOP_WORKERS")
    if not raw:
        return DEFAULT_WORKERS
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_WORKERS


def _pmap(
    fn: Callable[[T], R],
    items: Iterable[T],
    progress: Progress | None = None,
) -> list[R]:
    """Order-preserving parallel map for I/O bound work.

    Runs serially for short inputs: below the threshold the pool costs more
    than it saves, and serial also keeps the offline test fakes on one
    thread. Set ``PRSNOOP_WORKERS=1`` to force fully serial behaviour.

    ``progress(done, total)`` is called as work completes if given.
    """
    work = list(items)
    total = len(work)
    if total == 0:
        return []
    workers = _workers()
    if workers == 1 or total < _MIN_PARALLEL:
        out: list[R] = []
        for done, item in enumerate(work, 1):
            out.append(fn(item))
            if progress:
                progress(done, total)
        return out
    results: dict[int, R] = {}
    with ThreadPoolExecutor(max_workers=min(workers, total)) as pool:
        futures = {pool.submit(fn, item): idx for idx, item in enumerate(work)}
        for done, future in enumerate(as_completed(futures), 1):
            results[futures[future]] = future.result()
            if progress:
                progress(done, total)
    return [results[i] for i in range(total)]


def _ticker(label: str) -> Progress | None:
    """Progress callback that writes to stderr only on a real terminal.

    Keeps piped runs, CI, and the test suite byte-for-byte unchanged.
    """
    if not sys.stderr.isatty():
        return None
    width = 0

    def tick(done: int, total: int) -> None:
        nonlocal width
        if done != total and done % 4:
            return
        text = f"  {label} {done}/{total}"
        pad = " " * max(0, width - len(text))
        sys.stderr.write("\r" + text + pad)
        sys.stderr.flush()
        width = len(text)
        if done == total:
            sys.stderr.write("\r" + " " * width + "\r")
            sys.stderr.flush()

    return tick


def fetch_user_activity(
    client: GitHubClient,
    user: str,
    days: int = 30,
    include_reviews: bool = True,
    org: str | None = None,
    since: str | None = None,
    until: str | None = None,
) -> tuple[list[PRRecord], list[ReviewRecord], list[IssueRecord], bool]:
    """Return (prs, reviews, issues, fully_enriched) for ``user``.

    ``since``/``until`` are absolute YYYY-MM-DD bounds; when omitted the
    window is ``days`` back from today. ``org`` restricts everything to one
    GitHub organization or owner.
    """
    since = since or _cutoff(days)
    org_qualifier = f" org:{org}" if org else ""
    range_qualifier = f" created:{since}..{until}" if until else f" created:>={since}"

    pr_items: list[JsonDict] = client.paginate(
        SEARCH_PATH,
        params={"q": f"author:{user} is:pr{org_qualifier}{range_qualifier}"},
    )
    issue_items: list[JsonDict] = client.paginate(
        SEARCH_PATH,
        params={"q": f"author:{user} is:issue{org_qualifier}{range_qualifier}"},
    )

    repos: set[str] = {_repo_of(item) for item in pr_items}
    prs: list[PRRecord] = _pmap(
        lambda item: _pr_record(client, item, _repo_of(item)),
        pr_items,
        _ticker("fetching pull requests"),
    )
    enriched = len(prs)

    fully_enriched = enriched <= ENRICH_BUDGET
    if not fully_enriched:
        log.warning(
            "%d PRs found; enrichment budget is %d, lines-changed totals are partial",
            len(pr_items),
            ENRICH_BUDGET,
        )

    _attach_languages(client, prs, repos)

    issues = [
        IssueRecord.from_api(item, _repo_of(item))
        for item in issue_items
        if "pull_request" not in item
    ]

    reviews: list[ReviewRecord] = []
    if include_reviews:
        # Both review queries are date-bounded: GitHub search caps at 1000
        # results per query, and prolific reviewers blow past an unbounded
        # reviewed-by: query, which fails the whole report with a 422.
        involved = client.paginate(
            SEARCH_PATH,
            params={
                "q": f"reviewed-by:{user} is:pr -author:{user}"
                f" updated:>={since}{org_qualifier}"
            },
        )
        involved += client.paginate(
            SEARCH_PATH,
            params={
                "q": f"commenter:{user} is:pr -author:{user} updated:>={since}"
                f"{org_qualifier}"
            },
        )
        seen: set[tuple[str, int]] = set()
        targets: list[tuple[str, int, JsonDict]] = []
        for item in involved:
            repo = _repo_of(item)
            number = item["number"]
            if (repo, number) in seen:
                continue
            seen.add((repo, number))
            targets.append((repo, number, item))
        for chunk in _pmap(
            lambda target: _reviews_on(client, user, target[0], target[1], target[2]),
            targets,
            _ticker("scanning reviews"),
        ):
            reviews.extend(chunk)
        # The involved-PR search is updated:-bounded, but reviews on those
        # PRs can be years old. Window-filter so counts, daily charts, and
        # streaks only see reviews submitted inside the report window.
        start = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
        end = (
            (datetime.fromisoformat(until).replace(tzinfo=timezone.utc) + timedelta(days=1))
            if until
            else None
        )
        reviews = [
            r
            for r in reviews
            if r.submitted_at >= start and (end is None or r.submitted_at < end)
        ]
    return prs, reviews, issues, fully_enriched


def _pr_record(client: GitHubClient, item: JsonDict, repo: str) -> PRRecord:
    """Build a PRRecord, enriching with diff stats when available."""
    number = item["number"]
    detail_path = f"/repos/{repo}/pulls/{number}"
    try:
        detail = client.get(detail_path)
    except Exception:  # noqa: BLE001  partial data beats no data
        log.debug("no detail for %s#%s", repo, number)
        detail = None
    if isinstance(detail, dict) and detail:
        payload = {**item, **detail}
    else:
        payload = item
    record = PRRecord.from_api(payload, repo)
    # Search items already carry labels; the pulls detail does not.
    if not record.labels:
        record.labels = [lb["name"] for lb in (item.get("labels") or []) if lb.get("name")]
    return record


def _attach_languages(client: GitHubClient, prs: list[PRRecord], repos: set[str]) -> None:
    """Set PRRecord.language from each repository's primary language.

    Uses a per-repo cache so a user with 50 PRs into 3 repos costs 3 calls,
    not 50. Repos that fail to resolve stay as 'Unknown'.
    """
    def lang_of(repo: str) -> tuple[str, str]:
        try:
            info = client.get(f"/repos/{repo}")
            if isinstance(info, dict):
                return repo, (info.get("language") or "Unknown")
        except Exception:  # noqa: BLE001
            pass
        return repo, "Unknown"

    distinct = sorted(set(repos) | {pr.repo for pr in prs})
    cache: dict[str, str] = dict(_pmap(lang_of, distinct))
    for pr in prs:
        pr.language = cache.get(pr.repo, "Unknown")


def _reviews_on(
    client: GitHubClient,
    user: str,
    repo: str,
    pr_number: int,
    search_item: JsonDict,
) -> list[ReviewRecord]:
    """All reviews by ``user`` on repo#pr_number."""
    path = f"/repos/{repo}/pulls/{pr_number}/reviews"
    try:
        payload = client.get(path)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(payload, list):
        return []
    out: list[ReviewRecord] = []
    for review in payload:
        if review.get("user", {}).get("login") != user:
            continue
        out.append(
            ReviewRecord.from_api(
                {
                    "pr_number": pr_number,
                    "pr_title": search_item.get("title", ""),
                    "pr_url": search_item.get("html_url", ""),
                    "state": review["state"],
                    "submitted_at": review["submitted_at"],
                },
                repo,
            )
        )
    return out
