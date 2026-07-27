#!/bin/bash
#
# Pre-commit hook: runs the repo's read-only checks via the task runner.
#
# This script deliberately contains no tool commands. `just lint` is the one
# definition of what "clean" means; the hook, CI, and the developer all call
# it. Install with `just hooks-install`.

STAGED=$(git diff --cached --name-only --diff-filter=ACM | grep -E '\.py$' || true)

if [ -z "$STAGED" ]; then
    exit 0
fi

if ! command -v just >/dev/null 2>&1; then
    echo "❌ just is not on PATH; cannot run the pre-commit checks." >&2
    echo "   Install just, or commit with --no-verify if you accept the risk." >&2
    exit 1
fi

echo "---"
echo "Running lint on staged Python files..."
echo "---"

if ! just lint; then
    echo "---"
    echo "❌ Lint failed. Run 'just format' to fix what is fixable."
    exit 1
fi

echo "✅ Lint passed."
exit 0
