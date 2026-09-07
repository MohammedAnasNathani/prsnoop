name: PULL_REQUEST_TEMPLATE
about: Describe your change
---

## What & why

<!-- What does this change do, and why is it needed? -->

## Checks

<!-- All must pass; CI runs the same. -->

- [ ] `pytest` passes
- [ ] `ruff check .` passes
- [ ] `mypy` passes
- [ ] Tests added/updated (bug fixes need a failing test first)
- [ ] `CHANGELOG.md` updated under **Unreleased** (if user-facing)

## Notes for reviewers

<!-- Anything unusual, edge cases, or how you tested it. -->
