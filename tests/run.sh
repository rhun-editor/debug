#!/bin/sh
# The headless test: tests/real.py builds the extension for this machine, lays it out as rhun
# installs it (tests/layout.sh) and debugs for real against a rhun binary: a Go test at the cursor
# after a prelaunch build task, a Go file outside a module, a Python program reading input in the
# terminal, and a C program. A workflow whose tool is missing is skipped with the reason: dlv (on
# PATH or RHUN_TEST_DLV), a python with debugpy (RHUN_TEST_PYTHON), cc and lldb-dap.
# usage: tests/run.sh [RHUN]   (needs python3)
set -e
cd "$(dirname "$0")/.."
RHUN=${1:-$(command -v rhun || echo "$HOME/.local/bin/rhun")}
case "$(uname -s)-$(uname -m)" in
    Linux-x86_64 | Darwin-arm64) ;;
    *) echo "no target for $(uname -s)-$(uname -m)"; exit 77 ;;
esac
exec python3 tests/real.py "$RHUN" -v
