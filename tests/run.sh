#!/usr/bin/env bash
# Run every DNSmith test suite.
#
# unittest, not pytest: the suites must run on a plain Python with nothing
# installed beyond the hub's own dependencies. Suites that need more say so by
# skipping themselves — see tests/README.md.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec python3 -m unittest discover -s tests -t . "$@"
