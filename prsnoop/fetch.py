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

import json
import logging
import os
import sys
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

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

# Pull requests per GraphQL query. GitHub caps nodes per query, and a smaller
# chunk keeps any one failure cheap to fall back from.
GRAPHQL_CHUNK = 100

# Review pages per pull request. Matches the REST default page size, so the
# batched path reports exactly the numbers the REST path reported.
REVIEW_PAGE = 30

# Distinct from None: "no value was supplied, go and fetch it".
_UNSET: Any = object()


def _repo_of(item: JsonDict) -> str:
    """'https://api.github.com/repos/owner/name' -> 'owner/name'."""
    parts = item["repository_url"].rstrip("/").split("/")
    return f"{parts[-2]}/{parts[-1]}"


def _repo_parts(repo: str) -> tuple[str, str]:
    """'owner/name' -> ('owner', 'name')."""
    owner, _, name = repo.partition("/")
    return owner, name


def _chunked(items: list[T], size: int) -> list[list[T]]:
    """Split a list into consecutive chunks of at most ``size``."""
    return [items[i : i + size] for i in range(0, len(items), size)]


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
    min_parallel: int = _MIN_PARALLEL,
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
    if workers == 1 or total < min_parallel:
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

    # All four searches are independent, and search is the slowest endpoint
    # GitHub offers, so they go out together rather than one after another.
    pr_query = f"author:{user} is:pr{org_qualifier}{range_qualifier}"
    issue_query = f"author:{user} is:issue{org_qualifier}{range_qualifier}"
    reviewed_query = (
        f"reviewed-by:{user} is:pr -author:{user} updated:>={since}{org_qualifier}"
    )
    commenter_query = (
        f"commenter:{user} is:pr -author:{user} updated:>={since}{org_qualifier}"
    )
    jobs: list[Callable[[], list[Any]]] = [
        lambda: client.paginate(SEARCH_PATH, params={"q": pr_query}),
        lambda: client.paginate(SEARCH_PATH, params={"q": issue_query}),
    ]
    if include_reviews:
        jobs.append(lambda: client.paginate(SEARCH_PATH, params={"q": reviewed_query}))
        jobs.append(lambda: client.paginate(SEARCH_PATH, params={"q": commenter_query}))
    search_results = _pmap(lambda job: job(), jobs, min_parallel=2)
    pr_items: list[JsonDict] = search_results[0]
    issue_items: list[JsonDict] = search_results[1]

    prs: list[PRRecord] = _enrich_prs(client, pr_items)
    enriched = len(prs)

    fully_enriched = enriched <= ENRICH_BUDGET
    if not fully_enriched:
        log.warning(
            "%d PRs found; enrichment budget is %d, lines-changed totals are partial",
            len(pr_items),
            ENRICH_BUDGET,
        )

    _attach_languages(client, prs)

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
        involved = list(search_results[2]) + list(search_results[3])
        seen: set[tuple[str, int]] = set()
        targets: list[tuple[str, int, JsonDict]] = []
        for item in involved:
            repo = _repo_of(item)
            number = item["number"]
            if (repo, number) in seen:
                continue
            seen.add((repo, number))
            targets.append((repo, number, item))
        payloads: dict[tuple[str, int], list[JsonDict]] | None = None
        if _can_batch(client) and len(targets) >= _MIN_PARALLEL:
            try:
                payloads = _batched_reviews(client, [(t[0], t[1]) for t in targets])
            except Exception:  # noqa: BLE001
                log.debug("batched reviews unavailable, falling back to per-PR REST")
                payloads = None
        if payloads is not None:
            for repo, number, item in targets:
                already = payloads.get((repo, number), _UNSET)
                reviews.extend(
                    _reviews_on(client, user, repo, number, item, already)
                )
        else:
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


def _pr_record(
    client: GitHubClient,
    item: JsonDict,
    repo: str,
    detail: Any = _UNSET,
) -> PRRecord:
    """Build a PRRecord, enriching with diff stats when available.

    ``detail`` lets a caller hand over a payload it already holds, which is
    how the batched GraphQL path avoids a request per pull request. Leave it
    out and the per-PR REST call is made exactly as before.
    """
    number = item["number"]
    if detail is _UNSET:
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
    # The detail payload carries the repository's primary language under
    # base.repo, so this repository needs no separate /repos request.
    language = _language_of(detail)
    if language:
        record.language = language
    return record


def _can_batch(client: GitHubClient) -> bool:
    """True when this client can run a GraphQL query.

    Unauthenticated clients and the duck-typed doubles used in tests cannot,
    and both fall back to the REST path.
    """
    return bool(getattr(client, "token", None)) and hasattr(client, "graphql")


def _language_of(detail: Any) -> str | None:
    """Primary language from a pulls detail payload, when it is present."""
    if not isinstance(detail, dict):
        return None
    base = detail.get("base")
    if not isinstance(base, dict):
        return None
    inner = base.get("repo")
    if not isinstance(inner, dict):
        return None
    language = inner.get("language")
    return language if isinstance(language, str) and language else None


def _attach_languages(client: GitHubClient, prs: list[PRRecord]) -> None:
    """Fill in languages the pulls detail payload did not already give us.

    ``_pr_record`` reads base.repo.language out of the detail response, so on
    a normal run every repository is already resolved and this makes no
    requests at all. The fallback covers PRs whose detail call failed. Repos
    that still fail to resolve stay as 'Unknown'.
    """
    missing = sorted({pr.repo for pr in prs if pr.language == "Unknown"})
    if not missing:
        return

    def lang_of(repo: str) -> tuple[str, str]:
        try:
            info = client.get(f"/repos/{repo}")
            if isinstance(info, dict):
                return repo, (info.get("language") or "Unknown")
        except Exception:  # noqa: BLE001
            pass
        return repo, "Unknown"

    cache = dict(_pmap(lang_of, missing))
    for pr in prs:
        if pr.language == "Unknown":
            pr.language = cache.get(pr.repo, "Unknown")


def _reviews_on(
    client: GitHubClient,
    user: str,
    repo: str,
    pr_number: int,
    search_item: JsonDict,
    payload: Any = _UNSET,
) -> list[ReviewRecord]:
    """All reviews by ``user`` on repo#pr_number.

    ``payload`` lets the batched GraphQL path hand over reviews it already
    fetched, in the REST list shape.
    """
    if payload is _UNSET:
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


def _batched_pr_details(
    client: GitHubClient, targets: list[tuple[str, int]]
) -> dict[tuple[str, int], JsonDict]:
    """Diff stats and repo language for many PRs, in a couple of queries.

    Each returned payload is shaped like the REST detail body, so the normal
    record builder consumes it unchanged. Raises on any problem, and the
    caller falls back to the per-PR REST path.
    """
    by_repo: dict[str, list[int]] = {}
    for repo, number in targets:
        by_repo.setdefault(repo, []).append(number)
    if not by_repo:
        return {}

    # One query covering every repository is a single slow round trip, so the
    # repositories are spread across workers and the queries run at once.
    buckets: list[list[tuple[str, list[int]]]] = [
        [] for _ in range(max(1, min(_workers(), len(by_repo))))
    ]
    for i, entry in enumerate(sorted(by_repo.items())):
        buckets[i % len(buckets)].append(entry)
    units = [b for b in buckets if b]

    out: dict[tuple[str, int], JsonDict] = {}
    for part in _pmap(lambda unit: _pr_details_query(client, unit), units, min_parallel=2):
        out.update(part)
    return out


def _pr_details_query(
    client: GitHubClient, repos: list[tuple[str, list[int]]]
) -> dict[tuple[str, int], JsonDict]:
    """One GraphQL query covering the given repositories and their PRs."""
    lines = ["query {"]
    mapping: dict[tuple[str, str], tuple[str, int]] = {}
    for i, (repo, numbers) in enumerate(repos):
        owner, name = _repo_parts(repo)
        lines.append(
            f"  r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) {{"
        )
        lines.append("    primaryLanguage { name }")
        for j, number in enumerate(numbers):
            lines.append(
                f"    p{j}: pullRequest(number: {number}) "
                "{ additions deletions changedFiles mergedAt }"
            )
            mapping[(f"r{i}", f"p{j}")] = (repo, number)
        lines.append("  }")
    lines.append("}")
    data = client.graphql("\n".join(lines))
    out: dict[tuple[str, int], JsonDict] = {}
    for (ralias, palias), key in mapping.items():
        node = data.get(ralias)
        if not isinstance(node, dict):
            continue
        payload: JsonDict = {}
        pr = node.get(palias)
        if isinstance(pr, dict):
            # merged_at matters most: PRRecord.from_api derives MERGED from
            # it, and only the detail payload carries it. Without this every
            # merged pull request is recorded as merely closed.
            for key_name, field in (
                ("additions", "additions"),
                ("deletions", "deletions"),
                ("changed_files", "changedFiles"),
                ("merged_at", "mergedAt"),
            ):
                if pr.get(field) is not None:
                    payload[key_name] = pr[field]
        lang = node.get("primaryLanguage")
        if isinstance(lang, dict) and lang.get("name"):
            payload["base"] = {"repo": {"language": lang["name"]}}
        out[key] = payload
    return out


def _batched_reviews(
    client: GitHubClient, targets: list[tuple[str, int]]
) -> dict[tuple[str, int], list[JsonDict]]:
    """Each PR's reviews, in a couple of queries, shaped like the REST list.

    Raises on any problem, and the caller falls back to the per-PR REST path.
    """
    out: dict[tuple[str, int], list[JsonDict]] = {}
    for group in _chunked(targets, GRAPHQL_CHUNK):
        by_repo: dict[str, list[int]] = {}
        for repo, number in group:
            by_repo.setdefault(repo, []).append(number)
        lines = ["query {"]
        mapping: dict[tuple[str, str], tuple[str, int]] = {}
        for i, (repo, numbers) in enumerate(sorted(by_repo.items())):
            owner, name = _repo_parts(repo)
            lines.append(
                f"  r{i}: repository(owner: {json.dumps(owner)}, "
                f"name: {json.dumps(name)}) {{"
            )
            for j, number in enumerate(numbers):
                lines.append(
                    f"    p{j}: pullRequest(number: {number}) {{ "
                    f"reviews(first: {REVIEW_PAGE}) "
                    "{ nodes { author { login } state submittedAt } } }"
                )
                mapping[(f"r{i}", f"p{j}")] = (repo, number)
            lines.append("  }")
        lines.append("}")
        data = client.graphql("\n".join(lines))
        for (ralias, palias), key in mapping.items():
            node = data.get(ralias)
            if not isinstance(node, dict):
                continue
            pr = node.get(palias)
            nodes = pr.get("reviews", {}).get("nodes") if isinstance(pr, dict) else None
            if not isinstance(nodes, list):
                continue
            shaped: list[JsonDict] = []
            for raw in nodes:
                if not isinstance(raw, dict):
                    continue
                author = raw.get("author")
                login = author.get("login") if isinstance(author, dict) else None
                shaped.append(
                    {
                        "user": {"login": login},
                        "state": raw.get("state"),
                        "submitted_at": raw.get("submittedAt"),
                    }
                )
            out[key] = shaped
    return out


def _enrich_prs(client: GitHubClient, pr_items: list[JsonDict]) -> list[PRRecord]:
    """Build a PRRecord for every search hit.

    Prefers one batched GraphQL query over one REST request per pull request.
    Any problem at all, meaning no token, a rejected query, or an unexpected
    response shape, falls through to the per-PR REST path, so this can never
    lose data and can never come back slower than the REST path alone.
    """
    if _can_batch(client) and len(pr_items) >= _MIN_PARALLEL:
        targets = [(_repo_of(item), item["number"]) for item in pr_items]
        try:
            details = _batched_pr_details(client, targets)
        except Exception:  # noqa: BLE001
            log.debug("batched PR details unavailable, falling back to per-PR REST")
        else:
            return [
                _pr_record(
                    client,
                    item,
                    _repo_of(item),
                    detail=details.get((_repo_of(item), item["number"]), _UNSET),
                )
                for item in pr_items
            ]
    return _pmap(
        lambda item: _pr_record(client, item, _repo_of(item)),
        pr_items,
        _ticker("fetching pull requests"),
    )
