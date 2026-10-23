#!/bin/bash
# Run every ch08 check against one pydisort version and write the outputs next to the scripts.
# usage: ch08_run.sh PYTHON PYDISORT_SRC PYHARP_WT
#   PYTHON        interpreter whose environment holds torch, numpy, sympy, ninja, the pydisort under test and a
#                 pyharp built from source against it
#   PYDISORT_SRC  pydisort source tree at the installed version (for the record)
#   PYHARP_WT     the pyharp source tree that pyharp was built from, with its build/ directory (for the record, and
#                 for the yaml-cpp and fmt headers the stepper check compiles against)
# Outputs: ch08_<check>.pydisort-<version>.out. Runs on CPU (CUDA_VISIBLE_DEVICES is emptied), each check from a fresh
# temporary directory, as DERIVATION_SPEC.md asks. The stepper check needs a C++17 compiler on PATH; the directory of
# PYTHON is put first on PATH for ninja.
set -u
D=$(cd "$(dirname "$0")" && pwd)
PY=$1
export PYDISORT_SRC=$(cd "$2" && pwd) PYHARP_WT=$(cd "$3" && pwd) CUDA_VISIBLE_DEVICES=
export PATH=$(dirname "$PY"):$PATH
V=$("$PY" -c 'import pydisort; print(pydisort.__version__)')
for c in config radiation spherical stepper actinic; do
  W=$(mktemp -d)
  (cd "$W" && TORCH_EXTENSIONS_DIR="$W/ext" "$PY" "$D/ch08_$c.py" --work "$W/work" > "$D/ch08_$c.pydisort-$V.out" 2>/dev/null)
  echo "ch08_$c (pydisort $V): exit $?"
  rm -rf "$W"
done
