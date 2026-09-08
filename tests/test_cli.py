"""CLI behavior tests using the fake client via monkeypatched fetch."""
from __future__ import annotations

import json

import pytest

from prsnoop import cli
from prsnoop.models import PRRecord
from prsnoop.stats import build_activity


@pytest.fixture
def patched_fetch(monkeypatch, activity):
    """Make fetch_user_activity return the fixture activity regardless of input."""
    monkeypatch.setattr(
        cli, "fetch_user_activity",
        lambda client, user, days, include_reviews, org=None,
        since=None, until=None: (
            activity.prs, activity.reviews, activity.issues, True
        ),
    )


def _run(capsys, *argv):
    code = cli.run(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


class TestBasic:
    def test_top_defaults_to_10(self):
        assert cli.build_parser().parse_args(["octocat"]).top == 10

    def test_table_to_stdout(self, patched_fetch, capsys):
        code, out, _ = _run(capsys, "octocat")
        assert code == 0
        assert "octocat" in out
        assert "Pull requests" in out

    def test_markdown_format(self, patched_fetch, capsys):
        code, out, _ = _run(capsys, "octocat", "--format", "markdown")
        assert code == 0
        assert out.startswith("# Contribution report: octocat")

    def test_top_limits_repositories_and_languages(self, monkeypatch, capsys, now):
        prs = [
            PRRecord(
                repo=f"owner/repo-{index}", number=index, title="title", url="url",
                state="open", created_at=now, merged_at=None, additions=0,
                deletions=0, changed_files=0, language=f"Language-{index}",
            )
            for index in range(5)
        ]
        activity = build_activity("octocat", prs, [], [], now=now)
        monkeypatch.setattr(
            cli, "fetch_user_activity",
            lambda *args, **kwargs: (activity.prs, [], [], True),
        )

        code, out, _ = _run(capsys, "octocat", "--top", "3", "--format", "markdown")

        assert code == 0
        assert len(activity.stats.top_repos) == 5
        assert out.count("](https://github.com/owner/repo-") == 3
        assert out.count("| Language-") == 3

    def test_output_file(self, patched_fetch, capsys, tmp_path):
        target = tmp_path / "report.md"
        code, _, err = _run(
            capsys, "octocat", "--format", "markdown", "-o", str(target)
        )
        assert code == 0
        assert "wrote" in err
        assert target.read_text().startswith("# Contribution report")

    def test_days_validation(self, patched_fetch, capsys):
        code, _, err = _run(capsys, "octocat", "--days", "0")
        assert code == 2
        assert "--days" in err

    def test_since_until_requires_since(self, patched_fetch, capsys):
        code, _, err = _run(capsys, "octocat", "--until", "2026-07-01")
        assert code == 2
        assert "--until requires --since" in err

    def test_bad_since_format(self, patched_fetch, capsys):
        with pytest.raises(SystemExit) as excinfo:
            cli.run(["octocat", "--since", "july-1"])
        assert excinfo.value.code == 2

    def test_no_user_shows_help(self, capsys):
        code, _, err = _run(capsys)
        assert code == 2
        assert "usage" in err

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            cli.run(["--version"])
        assert excinfo.value.code == 0


class TestWindows:
    def test_org_flag_passes_through(self, patched_fetch, capsys, monkeypatch):
        seen = {}

        def fake_fetch(
            client, user, days, include_reviews,
            org=None, since=None, until=None,
        ):
            seen["org"] = org
            return [], [], [], True

        monkeypatch.setattr(cli, "fetch_user_activity", fake_fetch)
        code, _, _ = _run(capsys, "octocat", "--org", "aio-libs")
        assert code == 0
        assert seen["org"] == "aio-libs"

    def test_since_until_pass_through(self, patched_fetch, capsys, monkeypatch):
        seen = {}

        def fake_fetch(
            client, user, days, include_reviews,
            org=None, since=None, until=None,
        ):
            seen.update(since=since, until=until)
            return [], [], [], True

        monkeypatch.setattr(cli, "fetch_user_activity", fake_fetch)
        code, _, _ = _run(
            capsys, "octocat", "--since", "2026-06-01", "--until", "2026-07-01"
        )
        assert code == 0
        assert seen == {"since": "2026-06-01", "until": "2026-07-01"}

    def test_partial_enrichment_note(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli, "fetch_user_activity",
            lambda *a, **k: ([], [], [], False),
        )
        code, _, err = _run(capsys, "octocat")
        assert code == 0
        assert "partial" in err


class TestErrors:
    def test_rate_limit_exit_code(self, monkeypatch, capsys):
        from prsnoop.github import RateLimitExceeded

        def boom(*a, **k):
            raise RateLimitExceeded(403, "rate limit exceeded")

        monkeypatch.setattr(cli, "fetch_user_activity", boom)
        code, _, err = _run(capsys, "octocat")
        assert code == 4
        assert "PRSNOOP_TOKEN" in err

    def test_github_error_exit_code(self, monkeypatch, capsys):
        from prsnoop.github import GitHubError

        def boom(*a, **k):
            raise GitHubError(404, "Not Found")

        monkeypatch.setattr(cli, "fetch_user_activity", boom)
        code, _, err = _run(capsys, "octocat")
        assert code == 3
        assert "404" in err


class TestFormatsAll:
    @pytest.mark.parametrize("fmt", ["table", "markdown", "html", "csv", "json"])
    def test_every_format_succeeds(self, patched_fetch, capsys, fmt):
        code, out, _ = _run(capsys, "octocat", "--format", fmt)
        assert code == 0
        assert out.strip()


class TestSnap:
    def test_snap_writes_json(self, patched_fetch, capsys, tmp_path):
        target = tmp_path / "snap.json"
        code, _, err = _run(capsys, "snap", "octocat", "-o", str(target))
        assert code == 0
        data = json.loads(target.read_text())
        assert data["user"] == "octocat"
        assert data["stats"]["prs_authored"] == 3

    def test_snap_requires_output_or_compare(self, patched_fetch, capsys):
        code, _, err = _run(capsys, "snap", "octocat")
        assert code == 2

    def test_snap_compare_deltas(self, patched_fetch, capsys, tmp_path):
        old = tmp_path / "old.json"
        old.write_text(json.dumps({
            "stats": {
                "generated_at": "2026-07-01T00:00:00Z",
                "prs_authored": 2,
                "prs_merged": 1,
                "reviews_given": 0,
                "issues_opened": 0,
                "lines_added": 100,
                "lines_deleted": 10,
            }
        }))
        code, out, _ = _run(capsys, "snap", "octocat", "--compare", str(old))
        assert code == 0
        assert "pull requests" in out
        assert "2 -> 3" in out  # old -> new
