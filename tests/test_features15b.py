"""Tests for the 1.5 mega additions: retry, heatmap, wrapped, readme gen."""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import datetime, timedelta, timezone

from prsnoop import cli
from prsnoop.github import GitHubClient, GitHubError, RateLimitExceeded
from prsnoop.models import PRRecord
from prsnoop.render import render_html, render_profile_readme
from prsnoop.stats import build_activity
from prsnoop.wrapped import build_wrapped, render_wrapped_markdown, render_wrapped_table


def _pr(
    days_ago: float,
    repo: str = "acme/app",
    merged: bool = True,
    adds: int = 150,
    title: str = "x",
) -> PRRecord:
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    merged_at = created + timedelta(days=0.5) if merged else None
    return PRRecord(
        repo=repo,
        number=1,
        title=title,
        url="https://example.com",
        state="merged" if merged else "open",
        created_at=created,
        merged_at=merged_at,
        additions=adds,
        deletions=adds // 3,
        changed_files=2,
    )


def _activity(prs: list[PRRecord], window: int = 30):
    return build_activity("octocat", prs, [], [], window_days=window)


# ------------------------------------------------------------------- retry


class _FakeResponse:
    def __init__(self, body: bytes = b"{}") -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    headers: dict = {"ETag": None}


def test_retry_recovers_from_server_error(monkeypatch):

    calls = {"n": 0}

    def flaky(req, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise urllib.error.HTTPError("url", 503, "unavailable", {}, io.BytesIO(b"{}"))
        return _FakeResponse(b'{"ok": true}')

    sleeps: list[float] = []
    monkeypatch.setattr("urllib.request.urlopen", flaky)
    monkeypatch.setattr("prsnoop.github.time.sleep", lambda s: sleeps.append(s))
    client = GitHubClient()
    body = client.get("/repos/a/b")
    assert body == {"ok": True}
    assert calls["n"] == 3
    assert len(sleeps) == 2  # backoff before attempts 2 and 3


def test_retry_gives_up_after_max_attempts(monkeypatch):

    calls = {"n": 0}

    def always_500(req, timeout):
        calls["n"] += 1
        raise urllib.error.HTTPError("url", 500, "broken", {}, io.BytesIO(b"{}"))

    monkeypatch.setattr("urllib.request.urlopen", always_500)
    monkeypatch.setattr("prsnoop.github.time.sleep", lambda s: None)
    client = GitHubClient()
    try:
        client.get("/repos/a/b")
        raised = False
    except GitHubError as exc:
        raised = True
        assert exc.status == 500
    assert raised
    assert calls["n"] == 3


def test_secondary_rate_limit_retries_with_retry_after(monkeypatch):

    calls = {"n": 0}

    def abuse(req, timeout):
        calls["n"] += 1
        if calls["n"] < 2:
            raise urllib.error.HTTPError(
                "url",
                429,
                "rate limit",
                {"Retry-After": "2"},
                io.BytesIO(b'{"message": "You have triggered rate limit"}'),
            )
        return _FakeResponse(b'{"ok": true}')

    sleeps: list[float] = []
    monkeypatch.setattr("urllib.request.urlopen", abuse)
    monkeypatch.setattr("prsnoop.github.time.sleep", lambda s: sleeps.append(s))
    client = GitHubClient()
    body = client.get("/search/issues")
    assert body == {"ok": True}
    assert sleeps and sleeps[0] <= 8.0


def test_hard_rate_limit_raises_immediately(monkeypatch):

    calls = {"n": 0}

    def exhausted(req, timeout):
        calls["n"] += 1
        raise urllib.error.HTTPError(
            "url",
            403,
            "rate limit exceeded",
            {},
            io.BytesIO(b'{"message": "API rate limit exceeded"}'),
        )

    monkeypatch.setattr("urllib.request.urlopen", exhausted)
    monkeypatch.setattr("prsnoop.github.time.sleep", lambda s: None)
    client = GitHubClient()
    try:
        client.get("/repos/a/b")
        raised = False
    except RateLimitExceeded:
        raised = True
    assert raised
    assert calls["n"] == 1  # no retry on primary exhaustion


# ----------------------------------------------------------------- heatmap


def test_heatmap_in_html_for_wide_windows():
    prs = [_pr(60), _pr(90, repo="b/c")]
    act = _activity(prs, window=120)
    act.stats.since = "2026-05-01"
    html = render_html(act)  # type: ignore[arg-type]
    assert '<svg class="hm"' in html
    assert "Contribution calendar" in html


def test_heatmap_absent_for_narrow_windows():
    act = _activity([_pr(1)], window=30)
    act.stats.since = "2026-08-09"
    html = render_html(act)  # type: ignore[arg-type]
    assert '<svg class="hm"' not in html


def test_heatmap_cell_tooltip_present():
    prs = [_pr(60), _pr(90, repo="b/c")]
    act = _activity(prs, window=120)
    act.stats.since = "2026-05-01"
    html = render_html(act)  # type: ignore[arg-type]
    assert "<title>2026-" in html


# ----------------------------------------------------------------- wrapped


def test_wrapped_superlatives():
    prs = [
        _pr(10, repo="big/lib", adds=3000, title="the giant refactor"),
        _pr(5, repo="big/lib", merged=False, title="tiny"),
        _pr(1, repo="small/one", title="small"),
    ]
    act = _activity(prs, window=365)
    w = build_wrapped(act)
    assert w.prs == 3
    assert w.merged == 2
    assert w.top_repo == "big/lib"
    assert w.biggest_pr_lines == 4000
    assert w.biggest_pr_title == "the giant refactor"
    assert w.longest_pr_title == "the giant refactor"
    assert w.favorite_weekday in (
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    )
    assert w.pr_cadence_days is not None


def test_wrapped_table_and_markdown():
    prs = [_pr(10, repo="big/lib", adds=3000, title="the giant refactor")]
    w = build_wrapped(_activity(prs, window=365))
    table = render_wrapped_table(w)
    md = render_wrapped_markdown(w)
    assert "prsnoop wrapped | octocat" in table
    assert "THE YEAR IN PULL REQUESTS" in table
    assert "Biggest patch" in table
    assert "# Wrapped: octocat" in md
    assert "the giant refactor" in md


def test_wrapped_to_dict_roundtrip():
    w = build_wrapped(_activity([_pr(10)], window=365))
    payload = json.loads(json.dumps(w.to_dict()))
    assert payload["user"] == "octocat"
    assert "biggest_pr_lines" in payload


def test_wrapped_cli_table(monkeypatch, capsys):
    def fake_fetch(client, user, days, include_reviews, org=None, since=None, until=None):
        return [_pr(10, repo="big/lib", adds=3000, title="giant")], [], [], True

    monkeypatch.setattr(cli, "fetch_user_activity", fake_fetch)
    code = cli.run(["wrapped", "octocat"])
    out = capsys.readouterr().out
    assert code == 0
    assert "prsnoop wrapped | octocat" in out
    assert "THE YEAR IN PULL REQUESTS" in out


# -------------------------------------------------------------- readme gen


def test_profile_readme_contents():
    prs = [_pr(1), _pr(2), _pr(3, repo="beta/lib")]
    act = _activity(prs)
    out = render_profile_readme(act)  # type: ignore[arg-type]
    assert "generated by prsnoop" in out
    assert "![prs](data:image/svg+xml" in out
    assert "### GitHub activity" in out
    assert "Most active in:" in out
    assert "github.com/MohammedAnasNathani/prsnoop" in out


def test_readme_cli_stdout(monkeypatch, capsys):
    def fake_fetch(client, user, days, include_reviews, org=None, since=None, until=None):
        return [_pr(1)], [], [], True

    monkeypatch.setattr(cli, "fetch_user_activity", fake_fetch)
    code = cli.run(["readme", "octocat"])
    out = capsys.readouterr().out
    assert code == 0
    assert "### GitHub activity" in out
