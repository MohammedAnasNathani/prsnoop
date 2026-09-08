"""Zero-dependency GitHub REST client with token auth, pagination, and caching.

Uses only urllib from the standard library so prsnoop installs with nothing
else. Cached responses are revalidated with ETag conditional requests: an
unchanged resource returns the stored body without consuming rate limit.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger("prsnoop")

# A parsed GitHub API JSON object / list.
JsonDict = dict[str, Any]
JsonList = list[Any]

API_ROOT = "https://api.github.com"
PER_PAGE = 100
RETRY_STATUSES = {500, 502, 503, 504}
MAX_ATTEMPTS = 3
MAX_RETRY_SLEEP = 8.0  # cap backoff; Retry-After is capped separately


class GitHubError(RuntimeError):
    """Raised when the GitHub API returns an unrecoverable response."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"GitHub API error {status}: {message}")
        self.status = status


class RateLimitExceeded(GitHubError):
    """Raised on HTTP 403/429 caused by an exhausted rate limit."""


class _NotModified(Exception):
    """Internal signal: the server answered 304 for a conditional GET."""


class GitHubClient:
    """Minimal GitHub REST v3 client used by the fetchers."""

    def __init__(
        self,
        token: str | None = None,
        cache_dir: Path | None = None,
        cache_ttl: float = 900.0,
        user_agent: str = "prsnoop",
    ) -> None:
        if token is None:
            token = os.environ.get("PRSNOOP_TOKEN") or os.environ.get("GITHUB_TOKEN")
        self.token = token
        self.cache_dir = cache_dir
        self.cache_ttl = cache_ttl
        self._ratelimit_remaining: int | None = None
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": user_agent,
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    # ------------------------------------------------------------------ cache

    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / f"{key}.json"  # type: ignore[operator]

    def _cache_load(self, url: str) -> dict[str, Any] | None:
        """Return the raw cache entry {saved_at, etag, body} or None."""
        if self.cache_dir is None:
            return None
        path = self._cache_path(url)
        if not path.exists():
            return None
        try:
            entry = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
        if not isinstance(entry, dict) or "body" not in entry:
            return None
        return entry

    def _cache_save(self, url: str, body: JsonDict | JsonList, etag: str | None) -> None:
        if self.cache_dir is None:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_path(url)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"saved_at": time.time(), "etag": etag, "body": body}))
        tmp.replace(path)

    def _cache_touch(self, url: str, etag: str | None) -> None:
        """Re-validate a stored body without re-downloading it."""
        if self.cache_dir is None:
            return
        path = self._cache_path(url)
        entry = self._cache_load(url)
        if entry is None:
            return
        entry["saved_at"] = time.time()
        if etag is not None:
            entry["etag"] = etag
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entry))
        tmp.replace(path)

    # ------------------------------------------------------------------- HTTP

    def _request(
        self, url: str, etag: str | None = None
    ) -> tuple[JsonDict | JsonList, str | None]:
        """GET one URL with transient-failure retries. Returns (body, etag).

        Server errors (500/502/503/504), network hiccups, and GitHub's
        secondary rate limits (the abuse-detection 429s that carry a
        Retry-After header) are retried with backoff. A hard rate-limit
        exhaustion raises immediately: no amount of retrying helps.
        """
        headers = dict(self.headers)
        if etag:
            headers["If-None-Match"] = etag
        last_exc: GitHubError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read()
                    if resp.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    remaining = resp.headers.get("X-RateLimit-Remaining")
                    if remaining is not None:
                        self._ratelimit_remaining = int(remaining)
                    body: JsonDict | JsonList = json.loads(raw or b"{}")
                    return body, resp.headers.get("ETag")
            except urllib.error.HTTPError as exc:
                if exc.code == 304:
                    raise _NotModified from exc
                detail = exc.read().decode("utf-8", "replace")
                try:
                    message = json.loads(detail).get("message", detail)
                except json.JSONDecodeError:
                    message = detail
                if exc.code in (403, 429) and "rate limit" in str(message).lower():
                    retry_after = exc.headers.get("Retry-After") if exc.headers else None
                    if retry_after is not None and attempt < MAX_ATTEMPTS:
                        delay = min(float(retry_after), MAX_RETRY_SLEEP)
                        log.warning(
                            "secondary rate limit, attempt %d/%d, retrying in %.0fs",
                            attempt, MAX_ATTEMPTS, delay,
                        )
                        time.sleep(delay)
                        last_exc = RateLimitExceeded(exc.code, str(message))
                        continue
                    raise RateLimitExceeded(exc.code, str(message)) from exc
                if exc.code in RETRY_STATUSES and attempt < MAX_ATTEMPTS:
                    delay = min(2 ** (attempt - 1), MAX_RETRY_SLEEP)
                    log.warning(
                        "HTTP %d, attempt %d/%d, retrying in %.0fs",
                        exc.code, attempt, MAX_ATTEMPTS, delay,
                    )
                    time.sleep(delay)
                    last_exc = GitHubError(exc.code, str(message))
                    continue
                raise GitHubError(exc.code, str(message)) from exc
            except urllib.error.URLError as exc:
                if attempt < MAX_ATTEMPTS:
                    delay = min(2 ** (attempt - 1), MAX_RETRY_SLEEP)
                    log.warning(
                        "network error (%s), attempt %d/%d, retrying in %.0fs",
                        exc.reason, attempt, MAX_ATTEMPTS, delay,
                    )
                    time.sleep(delay)
                    last_exc = GitHubError(0, f"network error: {exc.reason}")
                    continue
                raise GitHubError(0, f"network error: {exc.reason}") from exc
        assert last_exc is not None
        raise last_exc

    # ----------------------------------------------------------------- public

    def get(
        self, path: str, params: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> JsonDict | JsonList:
        """GET one API path with ETag caching. Returns parsed JSON."""
        url = path if path.startswith("http") else f"{API_ROOT}{path}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        if not use_cache:
            body, etag = self._request(url)
            self._cache_save(url, body, etag)
            return body

        entry = self._cache_load(url)
        if entry is not None and time.time() - entry["saved_at"] < self.cache_ttl:
            cached: JsonDict | JsonList = entry["body"]
            return cached

        etag = entry.get("etag") if entry is not None else None
        try:
            body, new_etag = self._request(url, etag=etag)
        except _NotModified:
            assert entry is not None
            self._cache_touch(url, etag)
            not_modified: JsonDict | JsonList = entry["body"]
            return not_modified
        self._cache_save(url, body, new_etag)
        return body

    def paginate(
        self, path: str, params: dict[str, Any] | None = None, max_pages: int = 20
    ) -> list[Any]:
        """Collect every item across pages for one list API path.

        Search endpoints return an envelope dict (``{"total_count": …,
        "items": […]}``) rather than a bare list, so a dict batch is
        unwrapped to its ``items`` before the page loop continues.
        """
        items: list[Any] = []
        base_params = dict(params or {})
        page = 1
        while page <= max_pages:
            page_params = {**base_params, "per_page": PER_PAGE, "page": page}
            batch = self.get(path, params=page_params)
            if isinstance(batch, dict):
                batch = batch.get("items") or []
            if not isinstance(batch, list) or not batch:
                break
            items.extend(batch)
            if len(batch) < PER_PAGE:
                break
            page += 1
        return items

    @property
    def ratelimit_remaining(self) -> int | None:
        return self._ratelimit_remaining
