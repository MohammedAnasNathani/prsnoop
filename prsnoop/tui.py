from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Literal, TextIO, TypeVar

from prsnoop.models import Activity, PRRecord
from prsnoop.render import render_json, render_table

T = TypeVar("T")


@dataclass(slots=True)
class TuiState:
    page_index: int
    view: Literal["table", "json"]
    should_quit: bool
    total_pages: int = 1


def is_tty(stream: TextIO) -> bool:
    return bool(getattr(stream, "isatty", lambda: False)())


def paginate(items: list[T], page_size: int, page_index: int) -> list[T]:
    if page_size <= 0 or not items:
        return []
    total = total_pages(len(items), page_size)
    safe_index = clamp_page(page_index, total)
    start = safe_index * page_size
    end = start + page_size
    return items[start:end]


def total_pages(item_count: int, page_size: int) -> int:
    if page_size <= 0:
        return 1
    if item_count <= 0:
        return 1
    return (item_count + page_size - 1) // page_size


def clamp_page(page_index: int, total: int) -> int:
    if total <= 0:
        return 0
    return max(0, min(page_index, total - 1))


def _table_pr_rows(report: Activity) -> tuple[list[str], int]:
    full_lines = render_table(report).splitlines()
    try:
        marker = next(
            i for i, line in enumerate(full_lines) if "Recent pull requests" in line
        )
    except StopIteration:
        return full_lines, len(full_lines)
    return full_lines[: marker + 1], marker + 1


def format_page_table(
    report: Activity,
    page_items: list[PRRecord],
    page_index: int,
    total: int,
) -> str:
    header, _ = _table_pr_rows(report)
    rows = [
        f"  [{pr.state:>6}] {pr.repo}#{pr.number} {pr.title[:44]}"
        for pr in page_items
    ]
    if not rows:
        rows = ["  (none)"]
    footer = (
        f"[d/u] page  [t] table/json  [q] quit   page {page_index + 1}/{total}"
    )
    return "\n".join(header + rows + [footer])


def format_page_json(report: Activity) -> str:
    return render_json(report)


def handle_key(key: int, state: TuiState) -> TuiState:
    if key == ord("d"):
        return replace(
            state,
            page_index=clamp_page(state.page_index + 1, state.total_pages),
        )
    if key == ord("u"):
        return replace(
            state,
            page_index=clamp_page(state.page_index - 1, state.total_pages),
        )
    if key == ord("t"):
        next_view: Literal["table", "json"] = (
            "json" if state.view == "table" else "table"
        )
        return replace(state, view=next_view)
    if key in (ord("q"), 27):
        return replace(state, should_quit=True)
    return state


def _table_static_height(report: Activity) -> int:
    _, marker = _table_pr_rows(report)
    return marker


def _curses_main(stdscr: Any, report: Activity) -> int:
    import curses

    curses.curs_set(0)
    height, width = stdscr.getmaxyx()
    static_height = _table_static_height(report)
    page_size = max(1, height - static_height - 1)
    state = TuiState(
        page_index=0,
        view="table",
        should_quit=False,
        total_pages=total_pages(len(report.prs), page_size),
    )

    while not state.should_quit:
        stdscr.erase()
        if state.view == "table":
            page_items = paginate(report.prs, page_size, state.page_index)
            content = format_page_table(
                report,
                page_items,
                state.page_index,
                state.total_pages,
            )
        else:
            content = format_page_json(report)
        for row_index, line in enumerate(content.splitlines()[: height]):
            safe = line[: max(width - 1, 0)]
            with contextlib.suppress(curses.error):
                stdscr.addstr(row_index, 0, safe)
        key = stdscr.getch()
        state = handle_key(key, state)
    return 0


def run(
    report: Activity,
    stream: TextIO = sys.stdout,
    is_tty_fn: Callable[[TextIO], bool] = is_tty,
) -> int:
    if not is_tty_fn(stream):
        stream.write(render_table(report))
        stream.write("\n")
        return 0

    try:
        import curses  # noqa: PLC0415
    except ImportError:
        stream.write(render_table(report))
        stream.write("\n")
        stream.write(
            "note: interactive mode requires curses, which isn't available "
            "on this platform -- showing the full report instead\n"
        )
        return 0

    return curses.wrapper(_curses_main, report)
