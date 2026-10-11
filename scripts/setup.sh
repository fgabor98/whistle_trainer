#!/usr/bin/env bash
# Creates .venv and installs pinned dependencies. Pass --dev for test tools.
set -euo pipefail
cd "$(dirname "$0")/.."

missing=()
python3 -c 'import venv, ensurepip' 2>/dev/null || missing+=(python3-venv)
ldconfig -p | grep -q 'libpulse\.so\.0' || missing+=(libpulse0)
ldconfig -p | grep -q 'libxcb-cursor\.so\.0' || missing+=(libxcb-cursor0)
if (( ${#missing[@]} )); then
    echo "Missing system packages: ${missing[*]}" >&2
    echo "Install them with: sudo apt install ${missing[*]}" >&2
    exit 1
fi

requirements=requirements.txt
[[ "${1:-}" == "--dev" ]] && requirements=requirements-dev.txt

python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r "$requirements"
echo "Setup complete. Start the app with ./run.sh"
