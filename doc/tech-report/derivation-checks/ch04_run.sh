#!/bin/bash
# Regenerate every chapter 4 check output and figure, writing the outputs next to the scripts.
# usage: ch04_run.sh ENV_1.7.1 [ENV_1.8.13]
#   ENV_*  directories made by derivation-checks/ch04/setup_env.sh <dir> <pydisort version>
# Runs on CPU (CUDA_VISIBLE_DEVICES is emptied), each check from a fresh temporary directory, as ch03_run.sh does.
# Writes: ch04/toon_pyharp_check.pydisort-<version>.out and ch04/defects_pyharp_check.pydisort-<version>.out for each
#         environment, ch04/mutations.out (mutation and control runs, first environment),
#         ../src/pyharp_report/ch04/data/shortwave_thick_layer.csv (from the first environment),
#         ../src/pyharp_report/ch04/checks/{shortwave,longwave,planck}_check.out,
#         and draws the chapter's figures with tools/render_figures.py (to build/figures/ch04/).
set -u
D=$(cd "$(dirname "$0")" && pwd); R=$(cd "$D/.." && pwd)
export CUDA_VISIBLE_DEVICES=
first=1
for E in "$@"; do
  E=$(cd "$E" && pwd); PY="$E/venv/bin/python"
  V=$("$PY" -c 'import pydisort; print(pydisort.__version__)')
  export PYHARP_WT="$E/pyharp"
  W=$(mktemp -d)
  args=(); [ $first = 1 ] && args=(--data "$R/src/pyharp_report/ch04/data/shortwave_thick_layer.csv")
  (cd "$W" && "$PY" -I "$D/ch04/toon_pyharp_check.py" "${args[@]}" > "$D/ch04/toon_pyharp_check.pydisort-$V.out")
  echo "toon_pyharp_check (pydisort $V): exit $?"
  (cd "$W" && "$PY" -I "$D/ch04/defects_pyharp_check.py" > "$D/ch04/defects_pyharp_check.pydisort-$V.out")
  echo "defects_pyharp_check (pydisort $V): exit $?"
  rm -rf "$W"; first=0
done
PY="$(cd "$1" && pwd)/venv/bin/python"
for c in shortwave longwave planck; do
  W=$(mktemp -d)
  (cd "$W" && "$PY" -I "$R/src/pyharp_report/ch04/checks/${c}_check.py" > "$R/src/pyharp_report/ch04/checks/${c}_check.out")
  echo "${c}_check: exit $?"
  rm -rf "$W"
done
bash "$D/ch04/mutations.sh" "$1" > "$D/ch04/mutations.out"
echo "mutations: exit $?"
(cd "$R" && PYTHONPATH="$R/src" MPLCONFIGDIR=$(mktemp -d) "$PY" tools/render_figures.py --chapters ch04 > /dev/null)
echo "figures (tools/render_figures.py --chapters ch04): exit $?"
