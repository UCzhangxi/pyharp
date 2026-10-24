#!/bin/bash
# Regenerate every chapter 1 output, writing the outputs next to the script.
# usage: ch01_run.sh ENV_1.7.1 [ENV_1.8.13]
#   ENV_*  directories made by derivation-checks/ch04/setup_env.sh <dir> <pydisort version>
# Writes: check_ch01_quickstart_pydisort<version>.out for each environment, the data file
#         ../src/pyharp_report/ch01/data/quickstart_fluxes.csv (from the first environment), and draws the chapter's
#         figures with tools/render_figures.py --chapters ch01.
# Runs on CPU (CUDA_VISIBLE_DEVICES is emptied), each check from a fresh temporary directory.
set -u
D=$(cd "$(dirname "$0")" && pwd); R=$(cd "$D/.." && pwd)
export CUDA_VISIBLE_DEVICES=
first=1
for E in "$@"; do
  E=$(cd "$E" && pwd); PY="$E/venv/bin/python"
  V=$("$PY" -c 'import pydisort; print(pydisort.__version__.replace(".", ""))')
  args=(); [ $first = 1 ] && args=(--data "$R/src/pyharp_report/ch01/data/quickstart_fluxes.csv")
  W=$(mktemp -d)
  (cd "$W" && PYHARP_WT="$E/pyharp" "$PY" -I "$D/check_ch01_quickstart.py" "${args[@]}" > "$D/check_ch01_quickstart_pydisort$V.out")
  echo "check_ch01_quickstart (pydisort $V): exit $?"
  rm -rf "$W"; first=0
done
PY="$(cd "$1" && pwd)/venv/bin/python"
(cd "$R" && PYTHONPATH="$R/src" MPLCONFIGDIR=$(mktemp -d) "$PY" tools/render_figures.py --chapters ch01 > /dev/null)
echo "figures (tools/render_figures.py --chapters ch01): exit $?"
