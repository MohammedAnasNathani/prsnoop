# Contributing to prsnoop

Thanks for considering a contribution: this project is maintained as a
small, readable codebase on purpose, so please keep changes in that spirit.

## Getting started

```bash
git clone https://github.com/MohammedAnasNathani/prsnoop
cd prsnoop
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

All three checks must pass before a PR is merged:

```bash
pytest          # 63 unit tests, all offline (no network)
ruff check .    # lint
mypy            # strict type checking
```

CI runs the same three on every push and pull request.

## Ground rules

1. **Zero runtime dependencies.** The package uses only the standard library
   (`urllib`, `json`, `dataclasses`, …). If you need a third-party library,
   it belongs behind an optional extra: or it does not belong here.
2. **No network in tests.** Every test runs against fakes and fixtures.
   A CI run must pass with networking unplugged.
3. **Keep the public surface small.** `prsnoop.models` types, the
   `GitHubClient`, `fetch_user_activity`, `build_activity`, and the
   `RENDERERS` mapping are the API. Everything else is internal.
4. **Deterministic output.** Renderers are pure functions of an `Activity`.
   If you add randomness or wall-clock reads to a renderer, the tests will
   (rightly) reject it.

## Workflow

1. Look at [open issues](https://github.com/MohammedAnasNathani/prsnoop/issues)
  : `good first issue` is the place to start.
2. Fork, then create a branch:
   ```bash
   git checkout -b feat/short-name
   ```
3. Make your change with tests. Bug fixes need a test that fails without
   the fix; features need tests for the new behavior.
4. Update `CHANGELOG.md` under **Unreleased**.
5. Open a pull request. Fill in the template; small diffs get reviewed faster.

## Adding a renderer

Renderers are one function each, in `prsnoop/render.py`:

```python
def render_yaml(activity: Activity) -> str: ...
```

Register it in `RENDERERS`, add tests in `tests/test_render.py`, list it in
the README, done. The CLI picks it up automatically.

## Adding a metric

Metrics live in `prsnoop/stats.py` (`build_stats`). Add the field to the
`Stats` dataclass, compute it there, and cover both the populated and empty
cases in `tests/test_core.py`. Remember: every metric must serialize cleanly
in `to_dict()` (it ends up in the JSON output).

## Reporting bugs

Open an issue with:

- the command you ran
- prsnoop version (`prsnoop --version`)
- whether a token was set (yes/no: never paste the token itself)
- the traceback or wrong output

## Reporting security issues

Do not open a public issue. Use [GitHub security advisories]
(https://github.com/MohammedAnasNathani/prsnoop/security/advisories).

## License

By contributing you agree that your contributions are licensed under the
[MIT License](LICENSE).
