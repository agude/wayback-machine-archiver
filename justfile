# Task runner for wayback-machine-archiver. See the project-standards skill
# for the verb contract: lint is read-only and total, format is its mutating
# twin, and check is the full gate that CI runs.

# Default: list available recipes
default:
    @just --list

# Install dependencies
sync:
    uv sync --dev

# All read-only static checks
lint:
    uv run ruff check .
    uv run ruff format --check .

# Apply formatting and safe lint fixes
format:
    uv run ruff format .
    uv run ruff check --fix .

# Type check
# Scoped to the package, matching what CI checked before the migration.
# Extending to tests/ surfaces 26 real errors; that is its own change.
type-check:
    uv run mypy src/wayback_machine_archiver/

# Run tests
test *args:
    uv run pytest -vv {{ args }}

# Everything CI runs
check: lint type-check test

# Build the package
build:
    uv build

# Remove build and cache artifacts
clean:
    rm -rf dist/ build/ *.egg-info .pytest_cache .ruff_cache .mypy_cache

# Install the pre-commit hook into this clone
hooks-install:
    @mkdir -p .git/hooks
    @cp bin/pre-commit.sh .git/hooks/pre-commit
    @chmod +x .git/hooks/pre-commit
    @echo "Pre-commit hook installed."

# Show CLI help
help:
    uv run archiver --help
