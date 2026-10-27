#!/bin/bash
# Run every ch03 check against one pydisort version and write the outputs next to the scripts.
# usage: ch03_run.sh PYTHON PYDISORT_SRC PYHARP_WT
#   PYTHON        interpreter whose environment holds torch, numpy, scipy, sympy, the pydisort under
#                 test and a pyharp built against it
#   PYDISORT_SRC  pydisort source tree at the installed version (for the disotest driver and the record)
#   PYHARP_WT     the pyharp source tree that pyharp was built from (for the record)
# Outputs: ch03_<check>.pydisort-<version>.out and ch03_ordinates_algebra.out. Runs on CPU
# (CUDA_VISIBLE_DEVICES is emptied), each check from a fresh temporary directory, as DERIVATION_SPEC.md asks.
# Afterwards the regenerated outputs are compared with the committed ones (compare.sh, tools/compare_outputs.py):
# version, host and date lines are normalised and the ch03 values declared in host-dependent.json (round-off below
# 64 eps, the crash record of the overflow probes) are masked; everything else must match.
# Exit status: 0 when every check exits 0 and the chapter is REPRODUCED for this pydisort version; 1 when a check
# fails (its name and the end of its stderr are printed, and its previous output is left in place) or an output
# differs; 2 on a usage error. ch03_run_selftest.sh tests this.
set -u
D=$(cd "$(dirname "$0")" && pwd)
usage() { echo "usage: $(basename "$0") PYTHON PYDISORT_SRC PYHARP_WT" >&2; exit 2; }
[ $# -eq 3 ] || usage
[ -f "$1" ] && [ -x "$1" ] || { echo "ch03_run.sh: PYTHON '$1' is not an executable file" >&2; usage; }
[ -d "$2" ] && [ -d "$3" ] || { echo "ch03_run.sh: PYDISORT_SRC and PYHARP_WT must be directories" >&2; usage; }
# absolute, because each check runs from its own directory
PY=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
export PYDISORT_SRC=$(cd "$2" && pwd) PYHARP_WT=$(cd "$3" && pwd) CUDA_VISIBLE_DEVICES=
V=$("$PY" -c 'import pydisort; print(pydisort.__version__)') || { echo "ch03_run.sh: $PY cannot import pydisort" >&2; exit 1; }
source "$D/compare.sh"
OUTS=(ch03_{e3_slab,beam_closure,delta_m,intensity_correction,candidates,disotest}.pydisort-$V.out ch03_ordinates_algebra.out)
snapshot_outputs "${OUTS[@]}"
failed=()
# check SCRIPT LABEL OUTPUT [ARGS...]: run SCRIPT from a fresh temporary directory (also its TMPDIR); OUTPUT is
# replaced only when the check exits 0
check() {
  local s=$1 label=$2 out=$3 W rc; shift 3
  W=$(mktemp -d)
  (cd "$W" && TMPDIR="$W" "$PY" "$D/$s.py" "$@" > "$W/stdout" 2> "$W/stderr")
  rc=$?
  echo "$label: exit $rc"
  if [ $rc = 0 ]; then
    mv "$W/stdout" "$out"
  else
    failed+=("$s"); { echo "$s exited $rc; last lines of its stderr:"; tail -n 5 "$W/stderr"; } >&2
  fi
  rm -rf "$W"
}
for c in e3_slab beam_closure delta_m intensity_correction candidates disotest; do
  if [ $c = disotest ]; then
    check ch03_$c "ch03_$c (pydisort $V)" "$D/ch03_$c.pydisort-$V.out" "$PYDISORT_SRC"
  else
    check ch03_$c "ch03_$c (pydisort $V)" "$D/ch03_$c.pydisort-$V.out"
  fi
done
# the algebra check needs neither pydisort nor pyharp: one output, whatever the version
check ch03_ordinates_algebra ch03_ordinates_algebra "$D/ch03_ordinates_algebra.out"
compare_outputs "ch03 (pydisort $V)"; rc=$?
[ ${#failed[@]} = 0 ] || { echo "ch03_run.sh: failed: ${failed[*]}" >&2; exit 1; }
exit $rc
