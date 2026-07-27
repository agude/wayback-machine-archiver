# AGENTS.md

`CLAUDE.md` and `GEMINI.md` are symlinks to this file.

## Project Overview

Wayback Machine Archiver is a CLI tool that submits web pages to the Internet
Archive's Wayback Machine using the authenticated SPN2 API. It requires
Internet Archive S3-style API keys, supplied via a `.env` file or environment
variables. Published to PyPI as `wayback-machine-archiver`.

## Operations

All work goes through `just` (see the project-standards skill for the verb
contract). Every check has one definition here; the pre-commit hook and CI
call these same recipes rather than restating commands.

```bash
just sync         # install dependencies
just lint         # ruff check + ruff format --check (read-only)
just format       # ruff format + ruff check --fix (mutating)
just type-check   # mypy strict over the package
just test         # pytest with the 90% coverage gate
just check        # everything CI runs: lint + type-check + test
just hooks-install  # install bin/pre-commit.sh into this clone
just help         # archiver --help
```

## Architecture

Layered, in `src/wayback_machine_archiver/`:

- **archiver.py** — entry point (`main()`). Loads credentials, gathers URLs
  from CLI args, sitemaps, and files, then drives the workflow.
- **cli.py** — argument parser; every flag including the SPN2 options.
- **clients.py** — `SPN2Client` handles HTTP with the SPN2 API (submit
  captures, check status, batch status).
- **workflow.py** — `run_archive_workflow()` runs the main loop: submit,
  poll, retry transient errors, count successes and failures.
- **sitemaps.py** — sitemap parsing for both remote URLs and local files
  (prefixed `file://`).

### Workflow pattern

Interleaved submit-and-poll:

1. Submit a URL, receive a `job_id`.
2. Poll pending jobs in batches.
3. Re-queue transient errors, subject to retry limits.
4. Mark permanent errors as failed.

The classifications live in `workflow.py` as `REQUEUE_ERRORS` and
`PERMANENT_ERROR_MESSAGES`.

## Versioning

`src/wayback_machine_archiver/__init__.py` holds `__version__` and is the
single source of it: hatchling reads it at build time and the CLI prints it
for `--version`. Nothing else stores the version.

Releasing: bump `__version__`, commit, tag `vX.Y.Z`, push the tag, publish a
GitHub release. `release.yml` runs CI, verifies the tag matches
`__version__`, then publishes to PyPI via trusted publishing. A tag that
disagrees fails the release job by design.

## Testing notes

`requests-mock` for HTTP, `unittest.mock` for environment and IO. Test files
mirror the module structure (`test_cli.py`, `test_spn2_client.py`, …).

**Known gap:** `type-check` covers the package only. Running mypy over
`tests/` surfaces 26 real errors — mostly test fixtures building plain dicts
where a `PendingJob` TypedDict is expected, plus unannotated empty
collections. Worth fixing, as its own change.
