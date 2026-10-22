#!/bin/bash
# Regenerate every chapter 10 check output and figure, writing the outputs next to the scripts.
# usage: ch10_run.sh ENV_1.7.1 ENV_1.8.13 SCRATCH
#   ENV_*    directories made by derivation-checks/ch10/setup_env.sh <dir> <pydisort version>
#   SCRATCH  an empty directory for build trees and pytest logs (not committed)
# The mixed pairings install the other environment's checksum-verified pydisort wheel with --no-deps for the run,
# then restore the environment's own wheel. ctest runs once with the GPUs visible and once with
# CUDA_VISIBLE_DEVICES= ([S1], [S2]); everything else runs on CPU.
set -u
D=$(cd "$(dirname "$0")" && pwd); C="$D/ch10"; R=$(cd "$D/.." && pwd)
A=$(cd "$1" && pwd); B=$(cd "$2" && pwd); S=$(mkdir -p "$3" && cd "$3" && pwd)
whl() { ls "$1"/wheels/pydisort-*.whl; }
swap() { "$1/venv/bin/python" -m pip install -q --no-deps --force-reinstall "$2" > /dev/null; }
suite() { (PATH="$1/venv/bin:$PATH" bash "$C/run_suite.sh" "$1/pyharp" "$S/$2" > "$C/run_suite.$2.out" 2>&1); echo "run_suite $2: exit $?"; }

python3 "$C/test_inventory.py" "$A/pyharp" --csv "$R/src/pyharp_report/ch10/data/test_inventory.csv" > "$C/test_inventory.out"
echo "test_inventory: exit $?"
suite "$A" pydisort-1.7.1
suite "$B" pydisort-1.8.13
swap "$A" "$(whl "$B")"; suite "$A" built-1.7.1.run-1.8.13; swap "$A" "$(whl "$A")"
swap "$B" "$(whl "$A")"; suite "$B" built-1.8.13.run-1.7.1; swap "$B" "$(whl "$B")"
python3 "$C/abi_matrix.py" --csv "$R/src/pyharp_report/ch10/data/abi_matrix.csv" > "$C/abi_matrix.out"; echo "abi_matrix: exit $?"
for E in "$A" "$B"; do
  V=$("$E/venv/bin/python" -c 'import pydisort; print(pydisort.__version__)')
  args=(); [ "$E" = "$A" ] && args=(--csv "$R/src/pyharp_report/ch10/data/bindings_gaps.csv")
  (cd "$S" && "$E/venv/bin/python" -I "$C/bindings_diff.py" "$E/pyharp" "${args[@]}" > "$C/bindings_diff.pydisort-$V.out")
  echo "bindings_diff (pydisort $V): exit $?"
done
bash "$C/header_diff.sh" "$A" "$B" > "$C/header_diff.out"; echo "header_diff: exit $?"
{ for E in "$A" "$B"; do PATH="$E/venv/bin:$PATH" bash "$C/flaky_rerun.sh" "$E/pyharp" 25; done; } > "$C/flaky_rerun.out"
echo "flaky_rerun: exit $?"
(cd "$R" && PYTHONPATH="$R/src" MPLCONFIGDIR=$(mktemp -d) "$A/venv/bin/python" tools/render_figures.py --chapters ch10 > /dev/null)
echo "figures (tools/render_figures.py --chapters ch10): exit $?"
