"""Where rendered reports end up.

Documents default to ~/Downloads so a live demo does not have to retype the
same -o path for every command. The interesting cases are the ones that must
NOT move: an explicit -o, a text renderer, and anything non interactive.
"""

from __future__ import annotations

import pytest

from prsnoop import cli


@pytest.fixture
def downloads(tmp_path, monkeypatch):
    """Point the Downloads default at a temp dir and claim interactive use."""
    monkeypatch.setattr(cli, "DOWNLOADS_DIR", tmp_path / "Downloads")
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    monkeypatch.delenv("PRSNOOP_NO_SAVE", raising=False)
    return tmp_path / "Downloads"


def test_document_saves_to_downloads(downloads, capsys):
    cli._emit("<!doctype html><p>hi</p>", None, default_name="prsnoop-report-t.html")
    written = downloads / "prsnoop-report-t.html"
    assert written.read_text(encoding="utf-8") == "<!doctype html><p>hi</p>"
    captured = capsys.readouterr()
    assert "wrote" in captured.err
    assert captured.out == ""


def test_svg_counts_as_a_document(downloads):
    cli._emit("<svg xmlns='x'/>", None, default_name="prsnoop-card-t.svg")
    assert (downloads / "prsnoop-card-t.svg").exists()


def test_leading_whitespace_does_not_hide_the_doctype(downloads):
    cli._emit("\n  <!doctype html>\n<p>x</p>", None, default_name="r.html")
    assert (downloads / "r.html").exists()


def test_explicit_output_wins(downloads, tmp_path):
    target = tmp_path / "chosen.html"
    cli._emit("<!doctype html>", target, default_name="prsnoop-report-t.html")
    assert target.exists()
    assert not (downloads / "prsnoop-report-t.html").exists()


def test_text_renderers_stay_on_stdout(downloads, capsys):
    """A table is meant to be read, not filed away."""
    cli._emit("prsnoop wrapped | octocat\n", None, default_name="prsnoop-wrapped-t.html")
    assert capsys.readouterr().out.startswith("prsnoop wrapped")
    assert not downloads.exists() or not list(downloads.iterdir())


def test_piped_output_stays_on_stdout(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "DOWNLOADS_DIR", tmp_path / "Downloads")
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    cli._emit("<!doctype html>", None, default_name="prsnoop-report-t.html")
    assert capsys.readouterr().out.startswith("<!doctype html>")
    assert not (tmp_path / "Downloads").exists()


def test_no_save_env_var_forces_stdout(downloads, monkeypatch, capsys):
    monkeypatch.setenv("PRSNOOP_NO_SAVE", "1")
    cli._emit("<!doctype html>", None, default_name="prsnoop-report-t.html")
    assert capsys.readouterr().out.startswith("<!doctype html>")
    assert not downloads.exists() or not list(downloads.iterdir())


def test_no_default_name_means_no_surprise_file(downloads, capsys):
    """Commands that were never given a default keep printing."""
    cli._emit("<svg xmlns='x'/>", None)
    assert capsys.readouterr().out.startswith("<svg")


def test_missing_parent_directory_is_created(tmp_path, monkeypatch):
    deep = tmp_path / "a" / "b"
    monkeypatch.setattr(cli, "DOWNLOADS_DIR", deep)
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    cli._emit("<!doctype html>", None, default_name="report.html")
    assert (deep / "report.html").exists()


# --------------------------------------------------------------- export pack


def test_export_defaults_into_downloads(downloads, monkeypatch):
    """export writes a folder, so it cannot go through _emit's file path."""
    monkeypatch.setattr(cli, "fetch_user_activity", _fake_fetch)
    monkeypatch.setattr(cli, "GitHubClient", _FakeClient)
    assert cli.run(["export", "octocat"]) == 0
    packs = list(downloads.glob("prsnoop-octocat-*"))
    assert len(packs) == 1
    names = sorted(p.name for p in packs[0].iterdir())
    assert names == [
        "badges.md",
        "report.csv",
        "report.html",
        "report.json",
        "report.md",
        "report.txt",
    ]


def test_export_keeps_relative_folder_when_piped(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "DOWNLOADS_DIR", tmp_path / "Downloads")
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    monkeypatch.setattr(cli, "fetch_user_activity", _fake_fetch)
    monkeypatch.setattr(cli, "GitHubClient", _FakeClient)
    monkeypatch.chdir(tmp_path)
    assert cli.run(["export", "octocat"]) == 0
    assert list(tmp_path.glob("prsnoop-octocat-*"))
    assert not (tmp_path / "Downloads").exists()


# --------------------------------------------------------------------- stubs


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.token = None

    def paginate(self, *args, **kwargs):  # pragma: no cover - not exercised
        return []

    def get(self, *args, **kwargs):  # pragma: no cover - not exercised
        return {}


def _fake_fetch(client, user, days, include_reviews, org=None, since=None, until=None):
    return [], [], [], True
