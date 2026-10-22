#!/bin/bash
# Run every ch03 check against one pydisort version and write the outputs next to the scripts.
# usage: ch03_run.sh PYTHON PYDISORT_SRC PYHARP_WT
#   PYTHON        interpreter whose environment holds torch, numpy, scipy, sympy, the pydisort under
#                 test and a pyharp built against it
#   PYDISORT_SRC  pydisort source tree at the installed version (for the disotest driver and the record)
#   PYHARP_WT     the pyharp source tree that pyharp was built from (for the record)
# Outputs: ch03_<check>.pydisort-<version>.out and ch03_ordinates_algebra.out. Runs on CPU
# (CUDA_VISIBLE_DEVICES is emptied), each check from a fresh temporary directory, as DERIVATION_SPEC.md asks.
set -u
D=$(cd "$(dirname "$0")" && pwd)
PY=$1
export PYDISORT_SRC=$(cd "$2" && pwd) PYHARP_WT=$(cd "$3" && pwd) CUDA_VISIBLE_DEVICES=
V=$("$PY" -c 'import pydisort; print(pydisort.__version__)')
for c in e3_slab beam_closure delta_m intensity_correction candidates disotest; do
  W=$(mktemp -d)
  args=(); [ $c = disotest ] && args=("$PYDISORT_SRC")
  (cd "$W" && "$PY" "$D/ch03_$c.py" "${args[@]}" > "$D/ch03_$c.pydisort-$V.out" 2>/dev/null)
  echo "ch03_$c (pydisort $V): exit $?"
  rm -rf "$W"
done
# the algebra check needs neither pydisort nor pyharp: one output, whatever the version
W=$(mktemp -d)
(cd "$W" && "$PY" "$D/ch03_ordinates_algebra.py" > "$D/ch03_ordinates_algebra.out" 2>/dev/null)
echo "ch03_ordinates_algebra: exit $?"
rm -rf "$W"
