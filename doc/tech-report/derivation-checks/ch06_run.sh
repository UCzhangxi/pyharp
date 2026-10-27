#!/bin/bash
# Regenerate every chapter 6 output, writing the outputs next to the script.
# usage: ch06_run.sh VENV_1.7.1 [VENV_1.8.13]
#   VENV_*  Python environments made by derivation-checks/ch06_setup.sh ROOT <version> (ROOT/venv-<version>, each
#           holding env.sh)
# Writes: check_ch06_<check>_pydisort<version>.out for the four checks and each environment; the figure data
#         ../src/pyharp_report/ch06/data/rayleigh_sigma.json and mie_accuracy.json (from the first environment);
#         and draws the chapter's figures with tools/render_figures.py --chapters ch06.
# Runs on CPU (CUDA_VISIBLE_DEVICES is emptied), each check from a fresh temporary directory.
# Afterwards the regenerated outputs, the figure data included, are compared with the committed ones (compare.sh,
# tools/compare_outputs.py): version, host and date lines are normalised, and in mie_accuracy.json a relative error
# of Q_ext below 1e-9, the tolerance of check [C1], equals any other below it (host-dependent.json); everything else
# must match. Exit status 0 when the chapter is REPRODUCED, 1 when any output differs.
set -u
D=$(cd "$(dirname "$0")" && pwd); R=$(cd "$D/.." && pwd)
DATA=$R/src/pyharp_report/ch06/data
mkdir -p "$DATA"   # the figure data is generated; git does not keep the empty directory
export CUDA_VISIBLE_DEVICES=
CMP_ROOT=$R; source "$D/compare.sh"
outs=()
for E in "$@"; do
  V=$(source "$(cd "$E" && pwd)/env.sh" && python -c 'import pydisort; print(pydisort.__version__.replace(".", ""))')
  outs+=(derivation-checks/check_ch06_{sources,rayleigh,mie,picaso}_pydisort$V.out)
done
snapshot_outputs "${outs[@]}" src/pyharp_report/ch06/data/{rayleigh_sigma,mie_accuracy}.json
first=1
for E in "$@"; do
  E=$(cd "$E" && pwd)
  for c in sources rayleigh mie picaso; do
    args=()
    if [ $first = 1 ]; then
      [ $c = rayleigh ] && args=(--data "$DATA/rayleigh_sigma.json")
      [ $c = mie ] && args=(--data "$DATA/mie_accuracy.json")
    fi
    W=$(mktemp -d)
    V=$(source "$E/env.sh" && python -c 'import pydisort; print(pydisort.__version__.replace(".", ""))')
    (source "$E/env.sh" && cd "$W" && python -I "$D/check_ch06_$c.py" "${args[@]}" \
      > "$D/check_ch06_${c}_pydisort$V.out" 2>/dev/null)
    echo "check_ch06_$c (pydisort $V): exit $?"
    rm -rf "$W"
  done
  first=0
done
(source "$(cd "$1" && pwd)/env.sh" && cd "$R" && PYTHONPATH="$R/src" MPLCONFIGDIR=$(mktemp -d) \
  python tools/render_figures.py --chapters ch06 > /dev/null)
echo "figures (tools/render_figures.py --chapters ch06): exit $?"
compare_outputs ch06
