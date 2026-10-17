#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
    echo "Source mode needs Python 3.11 or newer. The desktop installer includes Python."
    echo "Install Python with your system package manager, then open this launcher again."
    exit 1
fi
exec python3 "$SCRIPT_DIR/dashboard.py" "$@"
