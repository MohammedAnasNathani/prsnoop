"""Minimal ANSI styling for live terminal views.

A handful of SGR codes, gated on the output stream being an interactive
terminal. NO_COLOR disables everything, FORCE_COLOR forces color even
when piped (useful for demos and screenshots). No third-party colors
library: this file exists so the live views stay dependency-free.
"""
from __future__ import annotations

import os
import sys

_RESET = "\x1b[0m"


def supports_color(stream: object = None) -> bool:
    """True when ANSI escape codes should be emitted to ``stream``."""
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = stream or sys.stdout
    return getattr(stream, "isatty", lambda: False)()


def _wrap(text: str, code: int, enabled: bool) -> str:
    if not enabled or not text:
        return text
    return f"\x1b[{code}m{text}{_RESET}"


def bold(text: str, enabled: bool = True) -> str:
    return _wrap(text, 1, enabled)


def dim(text: str, enabled: bool = True) -> str:
    return _wrap(text, 2, enabled)


def red(text: str, enabled: bool = True) -> str:
    return _wrap(text, 31, enabled)


def green(text: str, enabled: bool = True) -> str:
    return _wrap(text, 32, enabled)


def yellow(text: str, enabled: bool = True) -> str:
    return _wrap(text, 33, enabled)


def cyan(text: str, enabled: bool = True) -> str:
    return _wrap(text, 36, enabled)
