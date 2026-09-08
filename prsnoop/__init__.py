"""prsnoop: snoop GitHub pull requests, issues, and reviews into clean reports.

A zero-dependency CLI that answers "what did I (or my team) actually
contribute?" with terminal tables, Markdown, HTML, CSV, and JSON output.
"""

__version__ = "1.5.0"

from prsnoop.models import Activity, IssueRecord, PRRecord, ReviewRecord, Stats

__all__ = [
    "Activity",
    "IssueRecord",
    "PRRecord",
    "ReviewRecord",
    "Stats",
    "__version__",
]
