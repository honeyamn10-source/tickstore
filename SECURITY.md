# Security Policy

## Supported versions

The project is currently **alpha** (0.1.x). Security fixes land on the latest
release and are backported on request for 90 days after each release.

| Version | Supported |
| --- | --- |
| 0.1.x | :white_check_mark: |

## Reporting a vulnerability

Please do **not** open a public issue for security problems. Report privately
via GitHub's security advisory flow
([Create a security advisory](https://github.com/honeyamn10-source/tickstore/security/advisories/new)),
or by emailing the maintainers at the address listed on the repository
profile.

You will get an acknowledgement within 5 business days, and a target for
remediation for confirmed issues. Please include:

1. A minimal reproduction (ideally a script or test).
2. The affected version(s) and Python version.
3. Impact assessment (what an attacker could do).

## Scope and posture

`tickstore` is a local-first research library. The security surface is small
by design:

- **No network at import time.** Nothing in `tickstore/__init__.py` performs
  network I/O; fetching happens only when a provider is explicitly called.
- **Every provider request is auditable.** All HTTP goes through a single
  `transport` hook, so it can be proxied, replayed, or stubbed. Production use
  should route the default transport through a firewall/egress proxy.
- **Local SQLite by default.** Databases are just files where you put them;
  set file permissions appropriately (`0600` for sensitive research data).
- **Never log credentials.** There are no API keys in the codebase today. If a
  provider ever needs authentication, keys must enter via environment
  variables only and must never be serialized to the store or logs.

### Data handling recommendations

- Treat downloaded market data as untrusted input: it is parsed with a
  defensive surface (typed coercion with exceptions), but sanitize CSV files
  you did not export yourself before importing.
- Pin your Python patch version in production (e.g. `3.12.x`) to inherit
  security fixes from CPython itself — this project depends on the standard
  library's security posture.