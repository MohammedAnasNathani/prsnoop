"""Local live dashboard: prsnoop serve.

A tiny stdlib HTTP server that renders a fresh report on every request
and serves its JSON alongside. It binds 127.0.0.1 only: the dashboard is
for the person running it, never for the network. Responses come from
the same renderers as every other format, and the ETag cache keeps
auto-refreshes nearly free.

Endpoints:
    /           full HTML report, auto-refreshes every 5 minutes
    /api/report full JSON snapshot
    /health     liveness for scripts
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from prsnoop import __version__
from prsnoop.fetch import fetch_user_activity
from prsnoop.github import GitHubClient
from prsnoop.models import Activity
from prsnoop.render import render_html, render_json
from prsnoop.stats import build_activity

log = logging.getLogger("prsnoop")

AUTO_REFRESH_SECONDS = 300


def build_dashboard_page(activity: Activity) -> str:
    """Wrap the standard HTML report with auto-refresh and a banner."""
    page = render_html(activity)
    refresh = (
        f'<meta http-equiv="refresh" content="{AUTO_REFRESH_SECONDS}">'
    )
    banner = (
        "<div class='servebar'>live dashboard | auto-refresh every "
        f"{AUTO_REFRESH_SECONDS // 60} minutes | served locally by "
        f"prsnoop {__version__} on 127.0.0.1</div>"
    )
    style = (
        "<style>.servebar { position: sticky; top: 0; z-index: 9;"
        " background: #1a7f37; color: #fff; font: 600 0.8rem"
        " -apple-system, sans-serif; padding: 0.45rem 1rem;"
        " letter-spacing: 0.03em; }</style>"
    )
    return page.replace("<head>", f"<head>{refresh}{style}", 1).replace(
        "<body>", f"<body>{banner}", 1
    )


def make_handler(
    fetch_report: Callable[[], Activity],
) -> type[BaseHTTPRequestHandler]:
    """Build a request handler around a report factory."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802  stdlib naming
            if self.path == "/health":
                body = json.dumps({"status": "ok"}).encode("utf-8")
                ctype = "application/json"
            elif self.path in ("/", "/index.html"):
                try:
                    activity = fetch_report()
                except Exception as exc:  # noqa: BLE001
                    body = (
                        f"<h1>prsnoop</h1><p>report failed: {exc}</p>"
                        "<p><a href='/'>retry</a></p>"
                    ).encode()
                    self.send_response(500)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                body = build_dashboard_page(activity).encode("utf-8")
                ctype = "text/html; charset=utf-8"
            elif self.path == "/api/report":
                try:
                    activity = fetch_report()
                except Exception as exc:  # noqa: BLE001
                    body = json.dumps({"error": str(exc)}).encode("utf-8")
                    self.send_response(500)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                body = render_json(activity).encode("utf-8")
                ctype = "application/json"
            else:
                body = b"not found"
                self.send_response(404)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            log.debug(format, *args)

    return Handler


def serve(
    user: str,
    days: int = 30,
    port: int = 8642,
    cache_dir: object = None,
    open_browser: bool = False,
) -> None:
    """Block serving the live dashboard until interrupted."""
    client = GitHubClient(
        cache_dir=cache_dir,  # type: ignore[arg-type]
        user_agent=f"prsnoop/{__version__}",
    )

    def fetch_report() -> Activity:
        prs, reviews, issues, _ = fetch_user_activity(
            client, user, days=days, include_reviews=True
        )
        return build_activity(user, prs, reviews, issues, window_days=days)

    handler = make_handler(fetch_report)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    if open_browser:
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
