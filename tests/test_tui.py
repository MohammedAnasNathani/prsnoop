"""The tui command: module wiring that unit tests can actually reach.

The curses drawing itself needs a real terminal, but the bug that shipped
was a plain import problem, and that is cheap to pin.
"""

from __future__ import annotations


def test_curses_is_bound_at_runtime():
    """Regression: _draw is module level, so TYPE_CHECKING alone is not enough.

    run_tui used to do a lazy `import curses` inside the function, which
    binds the name locally and leaves the module level _draw without it.
    Reaching _draw then raised NameError: name 'curses' is not defined, so
    `prsnoop tui` failed on every platform.
    """
    from prsnoop import tui

    assert tui.curses is not None, (
        "curses must be importable at module level, not just under TYPE_CHECKING"
    )


def test_draw_is_a_module_level_function():
    """If _draw ever moves inside run_tui this test is the reminder to revisit."""
    from prsnoop import tui

    assert callable(tui._draw)
    assert tui._draw.__module__ == tui.__name__
