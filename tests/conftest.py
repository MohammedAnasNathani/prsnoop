"""Shared pytest fixtures: sample API payloads and a fake GitHubClient."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from prsnoop.models import Activity, IssueRecord, PRRecord, ReviewRecord
from prsnoop.stats import build_activity

FIXTURES = Path(__file__).parent / "fixtures"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_prs(now):
    """Three PRs: merged fast, merged slow, still open."""
    return [
        PRRecord(
            repo="aio-libs/yarl", number=1828, title="Fix IndexError on empty host",
            url="https://github.com/aio-libs/yarl/pull/1828", state="merged",
            created_at=now.replace(day=10), merged_at=now.replace(day=12),
            additions=42, deletions=7, changed_files=3,
        ),
        PRRecord(
            repo="agronholm/anyio", number=1247, title="Happy Eyeballs ordering fix",
            url="https://github.com/agronholm/anyio/pull/1247", state="merged",
            created_at=now.replace(day=5), merged_at=now.replace(day=25),
            additions=310, deletions=88, changed_files=6,
        ),
        PRRecord(
            repo="jd/tenacity", number=660, title="Retry cause cycle fix",
            url="https://github.com/jd/tenacity/pull/660", state="open",
            created_at=now.replace(day=28), merged_at=None,
            additions=15, deletions=3, changed_files=1,
        ),
    ]


@pytest.fixture
def sample_reviews(now):
    return [
        ReviewRecord(
            repo="voltagebots/agent-guard", pr_number=9, pr_title="guard rules",
            pr_url="https://github.com/voltagebots/agent-guard/pull/9",
            state="APPROVED", submitted_at=now.replace(day=14),
        ),
    ]


@pytest.fixture
def sample_issues(now):
    return [
        IssueRecord(
            repo="psf/requests", number=7564,
            title="Missing CA cert should raise FileNotFoundError",
            url="https://github.com/psf/requests/issues/7564", state="open",
            created_at=now.replace(day=20), closed_at=None, comments=2,
        ),
    ]


@pytest.fixture
def activity(sample_prs, sample_reviews, sample_issues, now) -> Activity:
    return build_activity("octocat", sample_prs, sample_reviews, sample_issues, now=now)


# --------------------------------------------------------------- API payloads

@pytest.fixture
def search_pr_payload(now) -> dict:
    """A search/issues response for is:pr."""
    return {
        "total_count": 2,
        "items": [
            {
                "number": 1828,
                "title": "Fix IndexError on empty host",
                "html_url": "https://github.com/aio-libs/yarl/pull/1828",
                "state": "closed",
                "created_at": _iso(now.replace(day=10)),
                "closed_at": _iso(now.replace(day=12)),
                "merged_at": _iso(now.replace(day=12)),
                "repository_url": "https://api.github.com/repos/aio-libs/yarl",
                "pull_request": {"merged_at": _iso(now.replace(day=12))},
            },
            {
                "number": 660,
                "title": "Retry cause cycle fix",
                "html_url": "https://github.com/jd/tenacity/pull/660",
                "state": "open",
                "created_at": _iso(now.replace(day=28)),
                "closed_at": None,
                "merged_at": None,
                "repository_url": "https://api.github.com/repos/jd/tenacity",
                "pull_request": {"merged_at": None},
            },
        ],
    }


@pytest.fixture
def pr_detail_payload(now) -> dict:
    return {
        "number": 1828,
        "additions": 42,
        "deletions": 7,
        "changed_files": 3,
    }


@pytest.fixture
def search_issue_payload(now) -> dict:
    return {
        "total_count": 1,
        "items": [
            {
                "number": 7564,
                "title": "Missing CA cert should raise FileNotFoundError",
                "html_url": "https://github.com/psf/requests/issues/7564",
                "state": "open",
                "created_at": _iso(now.replace(day=20)),
                "closed_at": None,
                "comments": 2,
                "repository_url": "https://api.github.com/repos/psf/requests",
            },
        ],
    }


@pytest.fixture
def search_reviewer_payload(now) -> dict:
    """PRs the user commented on but did not author."""
    return {
        "total_count": 1,
        "items": [
            {
                "number": 9,
                "title": "guard rules",
                "html_url": "https://github.com/voltagebots/agent-guard/pull/9",
                "state": "closed",
                "repository_url": "https://api.github.com/repos/voltagebots/agent-guard",
                "pull_request": {"merged_at": _iso(now.replace(day=14))},
            },
        ],
    }


@pytest.fixture
def reviews_payload(now) -> list:
    return [
        {
            "user": {"login": "octocat"},
            "state": "APPROVED",
            "submitted_at": _iso(now.replace(day=14)),
        },
        {
            "user": {"login": "someone-else"},
            "state": "COMMENTED",
            "submitted_at": _iso(now.replace(day=15)),
        },
    ]


# ------------------------------------------------------------ fake client

class FakeClient:
    """In-memory GitHubClient stand-in driven by a path->payload map."""

    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict | None]] = []

    def get(self, path: str, params: dict | None = None, use_cache: bool = True):
        self.calls.append((path, params))
        if path in self.routes:
            return self.routes[path]
        # Match search routes exactly on query keywords ("is:pr", "is:issue").
        if params and "q" in params:
            tokens = set(params["q"].split())
            for pattern, payload in self.routes.items():
                if pattern.startswith("q:"):
                    required = set(pattern[2:].split())
                    if required <= tokens:
                        return payload
        raise KeyError(f"no route for {path} {params}")

    def paginate(self, path: str, params: dict | None = None, max_pages: int = 20):
        result = self.get(path, params)
        return result.get("items", []) if isinstance(result, dict) else result


@pytest.fixture
def fake_client(
    search_pr_payload, pr_detail_payload, search_issue_payload,
    search_reviewer_payload, reviews_payload,
):
    return FakeClient(
        routes={
            "q:author:octocat is:pr": search_pr_payload,
            "q:author:octocat is:issue": search_issue_payload,
            "q:reviewed-by:octocat is:pr": {"total_count": 0, "items": []},
            "q:commenter:octocat is:pr": search_reviewer_payload,
            "/repos/aio-libs/yarl": {"language": "Python"},
            "/repos/jd/tenacity": {"language": "Python"},
            "/repos/agronholm/anyio": {"language": "Python"},
            "/repos/aio-libs/yarl/pulls/1828": pr_detail_payload,
            "/repos/jd/tenacity/pulls/660": {
                "number": 660, "additions": 15, "deletions": 3, "changed_files": 1,
            },
            "/repos/voltagebots/agent-guard/pulls/9/reviews": reviews_payload,
        }
    )


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def dump_fixture(name: str, payload: dict) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{name}.json").write_text(json.dumps(payload, indent=2))
