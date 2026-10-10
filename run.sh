#!/usr/bin/env bash
# Starts Whistle Trainer from the project's virtual environment.
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
    echo "The app is not set up yet. Run scripts/setup.sh first." >&2
    exit 1
fi
exec .venv/bin/python -m whistle_trainer "$@"
