from __future__ import annotations

import io
import sys

from prsnoop.render import render_json, render_table
from prsnoop.tui import (
    TuiState,
    clamp_page,
    format_page_json,
    format_page_table,
    handle_key,
    paginate,
    run,
    total_pages,
)


def test_paginate_empty_and_bounded():
    assert paginate([], 10, 0) == []
    assert paginate([1, 2, 3, 4], 2, 0) == [1, 2]
    assert paginate([1, 2, 3, 4], 2, 2) == [3, 4]
    assert paginate([1, 2, 3, 4], 2, 99) == [3, 4]
    assert paginate([1, 2, 3, 4], 2, 1) == [3, 4]


def test_total_pages_handles_empty_and_multiples():
    assert total_pages(0, 10) == 1
    assert total_pages(10, 10) == 1
    assert total_pages(11, 10) == 2
    assert total_pages(21, 10) == 3


def test_clamp_page():
    assert clamp_page(-10, 5) == 0
    assert clamp_page(20, 5) == 4
    assert clamp_page(2, 5) == 2


def test_handle_key_transitions(activity):
    base = TuiState(page_index=1, view="table", should_quit=False, total_pages=3)
    assert handle_key(ord("d"), base).page_index == 2
    assert handle_key(ord("u"), base).page_index == 0
    assert handle_key(ord("t"), base).view == "json"
    assert handle_key(
        ord("t"),
        TuiState(page_index=0, view="json", should_quit=False, total_pages=3),
    ).view == "table"
    assert handle_key(ord("q"), base).should_quit is True
    assert handle_key(27, base).should_quit is True
    assert handle_key(ord("x"), base) == base

    last = TuiState(page_index=2, view="table", should_quit=False, total_pages=3)
    assert handle_key(ord("d"), last).page_index == 2
    assert handle_key(
        ord("u"),
        TuiState(page_index=0, view="table", should_quit=False, total_pages=3),
    ).page_index == 0


def test_format_page_table_and_json(activity):
    table = format_page_table(
        activity,
        activity.prs[:2],
        0,
        total_pages(len(activity.prs), 2),
    )
    assert "page 1/2" in table
    assert "[d/u] page" in table
    assert format_page_json(activity) == render_json(activity)


def test_run_non_tty_falls_back_to_plain_table(activity):
    stream = io.StringIO()
    code = run(activity, stream=stream, is_tty_fn=lambda _s: False)
    assert code == 0
    assert stream.getvalue().strip() == render_table(activity).strip()


def test_run_import_error_falls_back_to_plain_table(activity, monkeypatch):
    stream = io.StringIO()
    monkeypatch.setitem(sys.modules, "curses", None)
    code = run(activity, stream=stream, is_tty_fn=lambda _s: True)
    assert code == 0
    out = stream.getvalue()
    assert "interactive mode requires curses" in out
    assert "windows-curses" not in out.lower()
    assert render_table(activity) in out
