# Contributing

Thanks for wanting to contribute to `tickstore`. The project is intentionally
small, standard-library-only, and offline-testable — please keep it that way.

## Ground rules

- **Zero runtime dependencies.** Code must work on a bare CPython 3.9+.
  `urllib`, `sqlite3`, `csv`, `json`, `dataclasses`, `statistics`: yes.
  Anything else: open a discussion first.
- **No inline comments.** Explain intent in the Google-style docstring, not
  in a `# comment` next to the code.
- **Black-formatted, typed, documented.** 88-column Black style, type hints
  everywhere, Google-style docstrings only.
- **Tests must be offline.** Provider tests inject `FakeTransport`; CLI tests
  use store paths. Never let a test touch the network.

## Setup

```console
git clone https://github.com/honeyamn10-source/tickstore.git
cd tickstore
python -m venv .venv && source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest tests -q
```

All 100+ tests run offline in well under a second.

## Making changes

1. **Fork and branch.** `git checkout -b feat/my-change` from `main`.
2. **Write the test first** where practical. Hand-computed reference values
   belong in the tests as literals — never "borrowed" from a library.
3. **Implement** following existing patterns in the matching module.
4. **Verify:**

```console
python -m pytest tests -q
python examples/quantlab.py   # offline pipeline must still run
```

5. **Update** `CHANGELOG.md` under `[Unreleased]`, and bump `__version__` /
   `pyproject.toml` for releases only.

## Style

- Format with Black (line length 88).
- Docstrings: top-level summary, blank line, `Args:`, `Returns:`, `Raises:`
  sections as applicable. Google style only.
- Public API additions should be exported from `tickstore/__init__.py` and
  documented in `README.md`.
- Keep functions small and pure; prefer returning values over side effects.

## Commit messages

Concise, imperative, prefixed by scope when useful, e.g.:

- `indicators: fix RSI warmup seeding`
- `store: add intervals() listing method`
- `providers: add Yahoo period1 support`

## Pull requests

Use the pull request template (`.github/pull_request_template.md`) and make
sure CI (offline test run) is green. Reference the issue you close, if any.

## Code of conduct

Everyone is expected to follow our [Code of Conduct](CODE_OF_CONDUCT.md). In
short: be respectful, be welcoming, and assume good faith.