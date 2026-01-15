# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Wayback Machine Archiver is a CLI tool to submit web pages to the Internet Archive's Wayback Machine using the authenticated SPN2 API. It requires Internet Archive S3-style API keys (via `.env` file or environment variables).

## Development Commands

```bash
# Install for development
pip install -e ".[dev]"

# Run tests
pytest

# Run a single test file
pytest tests/test_cli.py

# Run a specific test
pytest tests/test_cli.py::test_version_action_exits

# Run the CLI
archiver --help
```

## Architecture

The codebase follows a layered architecture in `src/wayback_machine_archiver/`:

- **archiver.py** - Entry point (`main()`). Loads credentials from environment, gathers URLs from CLI args/sitemaps/files, and orchestrates the workflow.
- **cli.py** - Argument parser definition. All CLI flags including SPN2 API options are defined here.
- **clients.py** - `SPN2Client` class handles HTTP communication with the Internet Archive's SPN2 API (submit captures, check status, batch status checks).
- **workflow.py** - `run_archive_workflow()` manages the main loop: submitting URLs, polling job statuses, handling retries for transient errors, and tracking success/failure counts.
- **sitemaps.py** - Sitemap parsing utilities. Handles both remote URLs and local files (prefixed with `file://`).

### Workflow Pattern

The archiver uses an interleaved submit-and-poll pattern:
1. Submit a URL, get a job_id
2. Poll pending jobs in batches
3. Handle transient errors by re-queuing URLs (with retry limits)
4. Handle permanent errors by marking as failed

Error classifications are defined in `workflow.py` as `REQUEUE_ERRORS` (transient) and `PERMANENT_ERROR_MESSAGES` (permanent).

## Version Management

Version is maintained in two places (synced via bump-my-version):
- `pyproject.toml`
- `src/wayback_machine_archiver/__init__.py`

## Testing Notes

Tests use `requests-mock` for HTTP mocking and `unittest.mock` for patching environment/IO. Test files mirror the module structure (e.g., `test_cli.py`, `test_spn2_client.py`).
