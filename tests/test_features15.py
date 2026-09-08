"""Tests for 1.5: momentum, serve, team, export, pulse formats."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from prsnoop import cli
from prsnoop.badge import render_pulse_badge
from prsnoop.models import PRRecord
from prsnoop.org import OrgPulse, fetch_org_pulse
from prsnoop.render import render_org_csv, render_org_html, render_table
from prsnoop.serve import build_dashboard_page, make_handler
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


# ---------------------------------------------------------------- momentum


def test_momentum_accelerating():
    # all activity in the second half of the window
    prs = [_pr(1), _pr(2), _pr(3)]
    stats = build_activity("t", prs, [], [], window_days=30).stats
    assert stats.momentum == "accelerating"


def test_momentum_slowing():
    prs = [_pr(25), _pr(27)]
    stats = build_activity("t", prs, [], [], window_days=30).stats
    assert stats.momentum == "slowing"


def test_momentum_steady():
    # each PR lands a created-day and a merged-day entry; spread them so
    # both halves of the window hold equal activity
    prs = [_pr(20), _pr(18), _pr(17), _pr(3), _pr(2), _pr(1)]
    stats = build_activity("t", prs, [], [], window_days=30).stats
    assert stats.momentum == "steady"


def test_momentum_empty_is_none():
    stats = build_activity("t", [], [], [], window_days=30).stats
    assert stats.momentum is None


def test_momentum_in_table_and_markdown():
    prs = [_pr(1), _pr(2), _pr(3)]
    act = build_activity("t", prs, [], [], window_days=30)
    table = render_table(act)
    assert "Momentum" in table and "second half" in table
    md_lines = render_table(act)
    assert "Momentum" in md_lines[0] or "Momentum" in "".join(md_lines)


# ------------------------------------------------------------- pulse badge


def _pulse() -> OrgPulse:
    return OrgPulse(
        org="acme", generated_at=datetime.now(timezone.utc), window_days=30,
        since="2026-08-01", until="2026-08-31",
        prs_opened=10, prs_merged=4, prs_open=6, authors=3, repos=1,
    )


def test_pulse_badge_renders_four():
    out = render_pulse_badge(_pulse())
    assert out.count("data:image/svg+xml") == 4
    assert "prs opened" in out and "authors" in out


# ------------------------------------------------------- org html and csv


class _OrgFake:
    def __init__(self, items: list[dict]) -> None:
        self.items = items

    def paginate(self, path: str, params: dict | None = None) -> list[dict]:
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


def _pulse_with_prs() -> tuple[list, OrgPulse]:
    items = [
        _org_item(1, merged=True, author="alice"),
        _org_item(2, merged=False, author="bob"),
    ]
    return fetch_org_pulse(
        _OrgFake(items), "acme", days=30,
        since="2026-08-01", until="2026-08-31",
    )


def test_org_html_renders_cards_and_chart():
    prs, pulse = _pulse_with_prs()
    html = render_org_html(prs, pulse)
    assert "Repo pulse" not in html
    assert "Org pulse: acme" in html
    assert '<svg class="chart"' in html
    assert "Top authors" in html


def test_org_csv_has_author_column():
    prs, pulse = _pulse_with_prs()
    csv_text = render_org_csv(prs, pulse)
    header = csv_text.splitlines()[0]
    assert "author" in header.split(",")
    assert "alice" in csv_text


# ------------------------------------------------------------------ serve


def test_dashboard_page_has_refresh_and_banner():
    act = build_activity("octocat", [_pr(1)], [], [], window_days=30)
    page = build_dashboard_page(act)
    assert 'http-equiv="refresh" content="300"' in page
    assert "live dashboard" in page
    assert "Contribution report: octocat" in page


def test_handler_serves_endpoints():
    def factory() -> tuple[str, str]:
        act = build_activity("octocat", [_pr(1)], [], [], window_days=30)
        return "application/json", json.dumps(act.to_dict())

    handler_cls = make_handler({"/api/report": factory})
    handler = handler_cls.__new__(handler_cls)

    responses: list[list] = []

    def send_response(code: int) -> None:
        responses.append([code, "", b""])

    def send_header(k: str, v: str) -> None:
        pass

    def end_headers() -> None:
        pass

    def write(body: bytes) -> None:
        responses[-1][2] = body

    handler.send_response = send_response  # type: ignore[method-assign]
    handler.send_header = send_header  # type: ignore[method-assign]
    handler.end_headers = end_headers  # type: ignore[method-assign]
    handler.wfile = type("W", (), {"write": staticmethod(write)})()  # type: ignore[assignment]

    for path, want_code, marker in [
        ("/health", 200, b'"status": "ok"'),
        ("/api/report", 200, b'"user": "octocat"'),
        ("/nope", 404, b"not found"),
    ]:
        responses.clear()
        handler.path = path
        handler.do_GET()
        assert responses[0][0] == want_code, path
        assert marker in responses[0][2], path


def test_parse_target_kinds():
    from prsnoop.serve import _parse_target

    assert _parse_target("simonw") == ("user", "simonw")
    assert _parse_target("org:vueuse") == ("org", "vueuse")
    assert _parse_target("repo:psf/requests") == ("repo", "psf/requests")


# ------------------------------------------------------------------- team


class _TeamFetch:
    def __init__(self) -> None:
        self.users: list[str] = []

    def __call__(self, client, user, days, include_reviews, org=None,
                 since=None, until=None):
        self.users.append(user)
        count = {"simonw": 3, "antfu": 1}.get(user, 0)
        return [_pr(i + 1) for i in range(count)], [], [], True


def test_team_ranks_by_merged(monkeypatch, capsys):
    fetcher = _TeamFetch()
    monkeypatch.setattr(cli, "fetch_user_activity", fetcher)
    code = cli.run(["team", "antfu", "simonw"])
    out = capsys.readouterr().out
    assert code == 0
    assert "1  simonw" in out
    assert "2  antfu" in out
    assert out.index("1  simonw") < out.index("2  antfu")
    assert fetcher.users == ["antfu", "simonw"]  # input order preserved


def test_team_needs_two_users(capsys):
    code = cli.run(["team", "solo"])
    assert code == 2
    assert "two or more" in capsys.readouterr().err


def test_team_rejects_duplicates(capsys):
    code = cli.run(["team", "a", "a"])
    assert code == 2
    assert "duplicate" in capsys.readouterr().err


def test_team_json_and_csv(monkeypatch, capsys):
    monkeypatch.setattr(cli, "fetch_user_activity", _TeamFetch())
    code = cli.run(["team", "simonw", "antfu", "-f", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ranking"][0]["user"] == "simonw"
    assert payload["ranking"][0]["rank"] == 1

    code = cli.run(["team", "simonw", "antfu", "-f", "csv"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("rank,user,prs,merged")
    assert "reviews" not in out.splitlines()[0]


# ----------------------------------------------------------------- export


def test_export_writes_full_pack(monkeypatch, tmp_path):
    def fake_fetch(client, user, days, include_reviews, org=None,
                   since=None, until=None):
        return [_pr(1), _pr(2)], [], [], True

    monkeypatch.setattr(cli, "fetch_user_activity", fake_fetch)
    out_dir = tmp_path / "pack"
    code = cli.run(["export", "octocat", "-o", str(out_dir)])
    assert code == 0
    names = sorted(p.name for p in out_dir.iterdir())
    assert names == [
        "badges.md", "report.csv", "report.html",
        "report.json", "report.md", "report.txt",
    ]
    assert "Contribution report: octocat" in (out_dir / "report.md").read_text()


def test_export_default_folder_name(monkeypatch, tmp_path, monkeypatch2=None):
    monkeypatch.chdir(tmp_path)

    def fake_fetch(client, user, days, include_reviews, org=None,
                   since=None, until=None):
        return [], [], [], True

    monkeypatch.setattr(cli, "fetch_user_activity", fake_fetch)
    code = cli.run(["export", "octocat"])
    assert code == 0
    folders = list(tmp_path.glob("prsnoop-octocat-*"))
    assert len(folders) == 1
