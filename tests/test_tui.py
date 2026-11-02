"""The tui command: module wiring that unit tests can actually reach.

The curses drawing itself needs a real terminal, but the bug that shipped
was a plain import problem, and that is cheap to pin. On Windows, curses is
legitimately absent, so the binding there is None and run_tui is expected to
exit with a readable message instead.
"""

from __future__ import annotations

import sys


def test_module_binds_curses_at_runtime():
    """Regression: _draw is module level, so TYPE_CHECKING alone is not enough.

    run_tui used to do a lazy `import curses` inside the function, which
    binds the name locally and leaves the module level _draw without it.
    Reaching _draw then raised NameError: name 'curses' is not defined, so
    `prsnoop tui` failed on every platform the moment it drew a frame.
    """
    from prsnoop import tui

    assert hasattr(tui, "curses"), (
        "the module must bind curses at runtime, not only under TYPE_CHECKING"
    )
    if sys.platform == "win32":
        # Windows ships no curses: None is the correct graceful value, and
        # run_tui turns it into a readable message instead of a traceback.
        assert tui.curses is None
    else:
        assert tui.curses is not None


def test_draw_is_a_module_level_function():
    """If _draw ever moves inside run_tui, this is the reminder to revisit."""
    from prsnoop import tui

    assert callable(tui._draw)
    assert tui._draw.__module__ == tui.__name__
