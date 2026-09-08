"""Tests for 1.4 features: repo pulse, me, size profile, repo breakdown."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from prsnoop import cli
from prsnoop.models import PRRecord
from prsnoop.org import fetch_repo_pulse
from prsnoop.render import render_html, render_markdown, render_table
from prsnoop.stats import build_activity


def _pr(days_ago: float, repo: str = "acme/app", merged: bool = True,
        adds: int = 150) -> PRRecord:
    created = datetime.now(timezone.utc) - timedelta(days=days_ago)
    merged_at = created + timedelta(days=0.5) if merged else None
    return PRRecord(
        repo=repo, number=1, title="x", url="https://example.com",
        state="merged" if merged else "open", created_at=created,
        merged_at=merged_at, additions=adds, deletions=adds // 3,
        changed_files=2,
    )


def _activity(prs: list[PRRecord]) -> object:
    return build_activity("tester", prs, [], [], window_days=30)


# ------------------------------------------------------------- repo pulse


class _PulseFakeClient:
    def __init__(self, items: list[dict]) -> None:
        self.items = items
        self.queries: list[str] = []

    def paginate(self, path: str, params: dict | None = None) -> list[dict]:
        assert params is not None
        self.queries.append(params["q"])
        return self.items


def _org_item(number: int, merged: bool, author: str) -> dict:
    return {
        "number": number,
        "title": f"pr {number}",
        "html_url": f"https://github.com/acme/app/pull/{number}",
        "state": "closed" if merged else "open",
        "created_at": "2026-08-15T10:00:00Z",
        "closed_at": "2026-08-20T10:00:00Z" if merged else None,
        "user": {"login": author},
        "repository_url": "https://api.github.com/repos/acme/app",
        "pull_request": {
            "merged_at": "2026-08-20T10:00:00Z" if merged else None,
        },
    }


def test_repo_pulse_uses_repo_scope():
    items = [_org_item(1, merged=True, author="alice")]
    client = _PulseFakeClient(items)
    prs, pulse = fetch_repo_pulse(
        client, "acme/app", days=30, since="2026-08-01", until="2026-08-31"
    )
    assert client.queries[0].startswith("repo:acme/app is:pr")
    assert pulse.label == "repo"
    assert pulse.org == "acme/app"
    assert pulse.prs_opened == 1
    assert prs[0].author == "alice"


def test_org_pulse_keeps_org_label():
    from prsnoop.org import fetch_org_pulse

    client = _PulseFakeClient([_org_item(1, merged=True, author="alice")])
    _prs, pulse = fetch_org_pulse(
        client, "acme", days=30, since="2026-08-01", until="2026-08-31"
    )
    assert client.queries[0].startswith("org:acme is:pr")
    assert pulse.label == "org"


def test_repo_pulse_table_header():
    from prsnoop.render import render_org_table

    client = _PulseFakeClient([_org_item(1, merged=True, author="alice")])
    prs, pulse = fetch_repo_pulse(
        client, "acme/app", days=30, since="2026-08-01", until="2026-08-31"
    )
    out = render_org_table(prs, pulse)
    assert out.startswith("prsnoop repo | acme/app")


# ------------------------------------------------------------ size profile


def test_size_buckets_and_median():
    # deletions are adds//3, so totals are 4/3 of adds
    prs = [
        _pr(1, adds=3),      # XS (4 changed)
        _pr(2, adds=24),     # S (32)
        _pr(3, adds=240),    # M (320)
        _pr(4, adds=2400),   # L (3200)
        _pr(5, adds=6000),   # XL (8000)
    ]
    stats = _activity(prs).stats
    assert stats.size_buckets == {"XS": 1, "S": 1, "M": 1, "L": 1, "XL": 1}
    assert stats.size_median_lines == 320


def test_unenriched_prs_excluded_from_size():
    prs = [_pr(1, adds=0), _pr(2, adds=3)]
    stats = _activity(prs).stats
    assert stats.size_buckets == {"XS": 1, "S": 0, "M": 0, "L": 0, "XL": 0}


def test_size_profile_in_markdown_and_table():
    prs = [_pr(1, adds=5), _pr(2, adds=50), _pr(3, adds=50)]
    act = _activity(prs)
    md = render_markdown(act)  # type: ignore[arg-type]
    tbl = render_table(act)  # type: ignore[arg-type]
    assert "PR size profile" in md
    assert "Typical size" in tbl


# -------------------------------------------------------- repo performance


def test_repo_breakdown_groups_and_rates():
    prs = [
        _pr(1, repo="acme/app", merged=True),
        _pr(2, repo="acme/app", merged=False),
        _pr(3, repo="beta/lib", merged=True),
        _pr(4, repo="beta/lib", merged=True),
        _pr(20, repo="solo/one", merged=False),
    ]
    stats = _activity(prs).stats
    by_repo = {r.repo: r for r in stats.repo_performance}
    assert "solo/one" not in by_repo  # single PR repos are skipped
    assert by_repo["acme/app"].prs == 2
    assert by_repo["acme/app"].merge_rate == 0.5
    assert by_repo["beta/lib"].merge_rate == 1.0


def test_where_work_lands_in_markdown_and_html():
    prs = [
        _pr(1, repo="acme/app", merged=True),
        _pr(2, repo="acme/app", merged=False),
    ]
    act = _activity(prs)
    md = render_markdown(act)  # type: ignore[arg-type]
    html = render_html(act)  # type: ignore[arg-type]
    assert "## Where your work lands" in md
    assert "Where your work lands" in html


# --------------------------------------------------------- me and presets


class _MeClient:
    """Stands in for GitHubClient: /user resolves, then fetch is stubbed."""

    def __init__(self, cache_dir=None, user_agent: str = "") -> None:
        self.token = "tok"

    def get(self, path: str) -> object:
        if path == "/user":
            return {"login": "octocat"}
        raise AssertionError(f"unexpected get {path}")


def test_me_resolves_login(monkeypatch, capsys):
    monkeypatch.setattr(cli, "GitHubClient", _MeClient)

    def fake_fetch(client, user, days, include_reviews, org=None,
                   since=None, until=None):
        assert user == "octocat"
        return [_pr(1)], [], [], True

    monkeypatch.setattr(cli, "fetch_user_activity", fake_fetch)
    code = cli.run(["me", "--days", "7"])
    out = capsys.readouterr().out
    assert code == 0
    assert "prsnoop | octocat" in out


def test_last_preset_maps_to_days(monkeypatch, capsys):

    captured: dict = {}

    def fake_fetch(client, user, days, include_reviews, org=None,
                   since=None, until=None):
        captured["days"] = days
        return [], [], [], True

    monkeypatch.setattr(cli, "fetch_user_activity", fake_fetch)
    code = cli.run(["octocat", "--last", "quarter"])
    assert code == 0
    assert captured["days"] == 91


def test_last_preset_on_repo(monkeypatch, capsys):
    import prsnoop.org as org_mod

    client = _PulseFakeClient([_org_item(1, merged=True, author="alice")])
    prs, pulse = fetch_repo_pulse(
        client, "acme/app", days=7, since="2026-08-01", until="2026-08-31"
    )

    def fake_pulse(client, subject, days=30, since=None, until=None):
        return prs, pulse

    seen: dict = {}

    def fake_fetch(client, subject, days=30, since=None, until=None):
        seen["days"] = days
        return prs, pulse

    monkeypatch.setattr(org_mod, "fetch_repo_pulse", fake_fetch)
    code = cli.run(["repo", "acme/app", "--last", "week"])
    assert code == 0
    assert seen["days"] == 7


def test_repo_subcommand_requires_slash(capsys):
    code = cli.run(["repo", "noslash", "--days", "5"])
    assert code == 2
    assert "owner/name" in capsys.readouterr().err


def test_me_without_token_path(monkeypatch):
    class _NoUser(_MeClient):
        def get(self, path: str) -> object:
            from prsnoop.github import GitHubError

            raise GitHubError(401, "bad credentials")

    monkeypatch.setattr(cli, "GitHubClient", _NoUser)
    code = cli.run(["me", "--days", "7"])
    assert code == 3
