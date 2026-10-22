#!/bin/bash
# Regenerate every ch05 output: the .out file of each check and the figure data in src/pyharp_report/ch05/data.
# usage: ch05_run.sh VENV
#   VENV  the Python environment ch05_setup.sh made (pydisort 1.7.1, the report's pin); its env.sh is sourced.
# Each check runs from a fresh temporary directory, as DERIVATION_SPEC.md asks; outputs go next to this script.
# check_ch05_cost.out is a timing on the host that runs it and will differ from the committed one elsewhere.
set -u
D=$(cd "$(dirname "$0")" && pwd)
DATA=$D/../src/pyharp_report/ch05/data
source "$1/env.sh"
for c in convergence gs85 analytic toon_vs_disort cost; do
  W=$(mktemp -d)
  (cd "$W" && python "$D/check_ch05_$c.py" --data "$DATA" > "$D/check_ch05_$c.out" 2>/dev/null)
  echo "check_ch05_$c: exit $? ($(tail -1 "$D/check_ch05_$c.out"))"
  rm -rf "$W"
done
