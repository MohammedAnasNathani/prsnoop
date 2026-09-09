"""Local live dashboard: prsnoop serve.

A tiny stdlib HTTP server that renders a fresh report on every request
and serves its JSON alongside. It binds 127.0.0.1 only: the dashboard is
for the person running it, never for the network. Responses come from
the same renderers as every other format, and the ETag cache keeps
auto-refreshes nearly free.

Targets: a bare username, ``org:login``, or ``repo:owner/name``. With
several targets the root path becomes a tab index and each target gets
its own page and JSON route.
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

Route = dict[str, Callable[[], tuple[str, str]]]
"""Map of exact request path to a callable returning (content_type, body)."""


def build_dashboard_page(activity: Activity) -> str:
    """Wrap the standard HTML report with auto-refresh and a banner."""
    page = render_html(activity)
    refresh = f'<meta http-equiv="refresh" content="{AUTO_REFRESH_SECONDS}">'
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


def make_handler(routes: Route) -> type[BaseHTTPRequestHandler]:
    """Build a request handler around a route table.

    Every route callable returns (content_type, body_text); an exception
    becomes a 500 page for HTML routes or a JSON error object. /health is
    always available, unknown paths 404.
    """

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802  stdlib naming
            path = self.path.split("?")[0]
            if path == "/health":
                self._reply(200, "application/json", json.dumps({"status": "ok"}))
                return
            fn = routes.get(path)
            if fn is None:
                self._reply(404, "text/plain", "not found")
                return
            try:
                ctype, text = fn()
            except Exception as exc:  # noqa: BLE001
                if "json" in path:
                    self._reply(
                        500,
                        "application/json",
                        json.dumps({"error": str(exc)}),
                    )
                else:
                    self._reply(
                        500,
                        "text/html; charset=utf-8",
                        f"<h1>prsnoop</h1><p>report failed: {exc}</p>"
                        "<p><a href='/'>retry</a></p>",
                    )
                return
            self._reply(200, ctype, text)

        def _reply(self, code: int, ctype: str, text: str) -> None:
            body = text.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            log.debug(format, *args)

    return Handler


def _parse_target(raw: str) -> tuple[str, str]:
    """'simonw' -> (user, simonw); 'org:X' -> (org, X); 'repo:a/b'."""
    if raw.startswith("org:"):
        return "org", raw[4:]
    if raw.startswith("repo:"):
        return "repo", raw[5:]
    return "user", raw


def _routes_for(
    kind: str,
    name: str,
    days: int,
    client: GitHubClient,
    fetch_user: Callable[[str], Activity],
) -> tuple[Callable[[], tuple[str, str]], Callable[[], tuple[str, str]]]:
    """Build the (html, json) route pair for one dashboard target."""
    if kind == "user":

        def user_html() -> tuple[str, str]:
            return "text/html; charset=utf-8", build_dashboard_page(fetch_user(name))

        def user_json() -> tuple[str, str]:
            return "application/json", render_json(fetch_user(name))

        return user_html, user_json

    from prsnoop.org import fetch_org_pulse, fetch_repo_pulse
    from prsnoop.render import render_org_html

    fetcher = fetch_repo_pulse if kind == "repo" else fetch_org_pulse

    def pulse_html() -> tuple[str, str]:
        prs, pulse = fetcher(client, name, days=days)
        return "text/html; charset=utf-8", render_org_html(prs, pulse)

    def pulse_json() -> tuple[str, str]:
        _prs, pulse = fetcher(client, name, days=days)
        return "application/json", json.dumps(pulse.to_dict(), indent=2)

    return pulse_html, pulse_json


def serve(
    targets: list[str],
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
    parsed = [_parse_target(raw) for raw in targets]

    def fetch_user(login: str) -> Activity:
        prs, reviews, issues, _ = fetch_user_activity(
            client, login, days=days, include_reviews=True
        )
        return build_activity(login, prs, reviews, issues, window_days=days)

    routes: Route = {}
    for i, (kind, name) in enumerate(parsed):
        page_path = "/" if len(parsed) == 1 else f"/t/{i}"
        api_path = "/api/report" if len(parsed) == 1 else f"/api/{i}"
        html_fn, json_fn = _routes_for(kind, name, days, client, fetch_user)
        routes[page_path] = html_fn
        routes[api_path] = json_fn

    if len(parsed) > 1:
        links = "".join(
            f'<p><a class="tab" href="/t/{i}">{kind}: {name}</a></p>'
            for i, (kind, name) in enumerate(parsed)
        )
        index_body = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<title>prsnoop dashboard</title><style>"
            "body { font-family: -apple-system, sans-serif; background:"
            " #0d1117; color: #e6edf3; padding: 3rem; }"
            "h1 { font-size: 1.4rem; }"
            ".tab { color: #3fb950; font-size: 1.05rem;"
            " text-decoration: none; }"
            "</style></head><body><h1>prsnoop live dashboard</h1>"
            f"{links}</body></html>"
        )
        routes["/"] = lambda: ("text/html; charset=utf-8", index_body)

    handler = make_handler(routes)
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
