"""Tests for the caching GitHub client: ETag revalidation, pagination, errors."""
from __future__ import annotations

import io
import json
import time
import urllib.error

import pytest

from prsnoop.github import GitHubClient, GitHubError, RateLimitExceeded


class _Response:
    """urlopen stand-in."""

    def __init__(self, body: dict, etag: str | None = None, status: int = 200):
        self._body = json.dumps(body).encode()
        self.headers = {"ETag": etag} if etag else {}
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _install(monkeypatch, handler):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda req, timeout: handler(req)
    )


class TestCache:
    def test_fresh_cache_skips_network(self, tmp_path, monkeypatch):
        client = GitHubClient(cache_dir=tmp_path)
        calls = []

        def handler(req):
            calls.append(req)
            return _Response({"ok": True}, etag='"v1"')

        _install(monkeypatch, handler)
        assert client.get("/x") == {"ok": True}
        assert client.get("/x") == {"ok": True}
        assert len(calls) == 1  # second call served from cache

    def test_stale_cache_revalidates_with_etag(self, tmp_path, monkeypatch):
        client = GitHubClient(cache_dir=tmp_path)
        requests = []

        def handler(req):
            requests.append(req)
            etag = req.headers.get("If-None-Match")
            if etag:
                # Simulate 304: body unchanged.
                raise urllib.error.HTTPError(
                    req.full_url, 304, "Not Modified", hdrs={}, fp=None
                )
            return _Response({"value": 1}, etag='"v1"')

        _install(monkeypatch, handler)
        first = client.get("/x")
        assert first == {"value": 1}
        # Age the entry past TTL.
        entry_path = next(tmp_path.glob("*.json"))
        entry = json.loads(entry_path.read_text())
        entry["saved_at"] = time.time() - 9999
        entry_path.write_text(json.dumps(entry))
        again = client.get("/x")
        assert again == {"value": 1}  # stale body returned after 304
        assert len(requests) == 2  # but a conditional request was made

    def test_stale_cache_fetches_new_body(self, tmp_path, monkeypatch):
        client = GitHubClient(cache_dir=tmp_path)

        state = {"etag": None}

        def handler(req):
            if state["etag"] and req.headers.get("If-None-Match") == state["etag"]:
                raise urllib.error.HTTPError(
                    req.full_url, 304, "Not Modified", hdrs={}, fp=None
                )
            state["etag"] = '"v2"'
            return _Response({"value": 2}, etag='"v2"')

        _install(monkeypatch, handler)
        client.get("/x")
        # Force staleness.
        entry_path = next(tmp_path.glob("*.json"))
        entry = json.loads(entry_path.read_text())
        entry["saved_at"] = time.time() - 9999
        entry_path.write_text(json.dumps(entry))
        assert client.get("/x") == {"value": 2}

    def test_no_cache_always_hits_network(self, tmp_path, monkeypatch):
        client = GitHubClient(cache_dir=tmp_path)
        calls = []

        def handler(req):
            calls.append(req)
            return _Response({"n": len(calls)})

        _install(monkeypatch, handler)
        client.get("/x", use_cache=False)
        client.get("/x", use_cache=False)
        assert len(calls) == 2


class TestPagination:
    def test_collects_all_pages(self, monkeypatch):
        client = GitHubClient()
        pages = {
            1: [{"i": 1}] * 100,
            2: [{"i": 2}] * 100,
            3: [{"i": 3}] * 37,  # short page ends iteration
        }

        def handler(req):
            from urllib.parse import parse_qs, urlparse

            query = parse_qs(urlparse(req.full_url).query)
            page = int(query["page"][0])
            return _Response(pages[page])

        _install(monkeypatch, handler)
        items = client.paginate("/list")
        assert len(items) == 237

    def test_unwraps_search_envelope(self, monkeypatch):
        """Search endpoints answer {total_count, items}: paginate must unwrap."""
        client = GitHubClient()

        def handler(req):
            return _Response({"total_count": 2, "items": [{"n": 1}, {"n": 2}]})

        _install(monkeypatch, handler)
        items = client.paginate("/search/issues", params={"q": "author:x is:pr"})
        assert items == [{"n": 1}, {"n": 2}]

    def test_stops_at_max_pages(self, monkeypatch):
        client = GitHubClient()

        def handler(req):
            return _Response([{"i": 1}] * 100)

        _install(monkeypatch, handler)
        items = client.paginate("/list", max_pages=3)
        assert len(items) == 300


class TestErrors:
    def test_rate_limit_becomes_specific_error(self, monkeypatch):
        client = GitHubClient()

        def handler(req):
            raise urllib.error.HTTPError(
                req.full_url, 403, "Forbidden", hdrs={},
                fp=io.BytesIO(
                    json.dumps({"message": "API rate limit exceeded"}).encode()
                ),
            )

        _install(monkeypatch, handler)
        with pytest.raises(RateLimitExceeded):
            client.get("/x")

    def test_other_http_error_is_github_error(self, monkeypatch):
        client = GitHubClient()

        def handler(req):
            raise urllib.error.HTTPError(
                req.full_url, 404, "Not Found", hdrs={},
                fp=io.BytesIO(json.dumps({"message": "Not Found"}).encode()),
            )

        _install(monkeypatch, handler)
        with pytest.raises(GitHubError) as excinfo:
            client.get("/x")
        assert excinfo.value.status == 404


class TestToken:
    def test_token_from_env(self, monkeypatch):
        monkeypatch.setenv("PRSNOOP_TOKEN", "t1")
        client = GitHubClient()
        assert client.headers["Authorization"] == "Bearer t1"

    def test_github_token_fallback(self, monkeypatch):
        monkeypatch.delenv("PRSNOOP_TOKEN", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "t2")
        client = GitHubClient()
        assert client.headers["Authorization"] == "Bearer t2"

    def test_no_token_anonymous(self, monkeypatch):
        monkeypatch.delenv("PRSNOOP_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        client = GitHubClient()
        assert "Authorization" not in client.headers
