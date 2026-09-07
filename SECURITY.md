# Security Policy

## Supported versions

The latest release on `main` is supported.

## Reporting a vulnerability

Please report privately via
[GitHub security advisories](https://github.com/MohammedAnasNathani/prsnoop/security/advisories).
Do not open a public issue for security problems.

You should hear back within a few days. Please include:

- a description of the issue and its impact
- steps or a proof of concept
- affected versions, if known

## Scope notes

- prsnoop sends your token **only** to `api.github.com` over HTTPS.
- The token is read from the environment and never written to disk by
  prsnoop itself.
- API cache files under `~/.cache/prsnoop` contain public API data only
  no credentials.
