#!/bin/bash
# Self-test of the ch03 runner (ch03_run.sh) and of the probe harness of ch03_candidates.py.
# usage: ch03_run_selftest.sh PYTHON PYDISORT_SRC PYHARP_WT   (the arguments of ch03_run.sh)
# Works on a copy of the ch03 scripts in a temporary directory, so no committed output is touched.
#   [T1] ch03_run.sh with no arguments prints its usage and exits 2.
#   [T2] a check that fails makes ch03_run.sh exit 1 and name it, and leaves that check's previous output in place;
#        the other checks still run and exit 0 (the checks are replaced by stubs here: this tests the runner only).
#   [T3] a [P1] probe that never exits after printing its result (as a probe whose heap it corrupted can do,
#        deadlocked in free() at interpreter exit) is killed after the probe timeout: ch03_candidates.py --repeat 1
#        exits 0 well inside 400 s and the [P1] line counts the hang. Before, the harness waited 600 s and died.
#   [T4] no ch03 check builds a DISORT solver (pydisort.Disort or pyharp.RadiationBand) whose ds.nphase it left unset.
#        pydisort's DisortOptions and pyharp's YAML band options leave ds.nphase uninitialised (about 5% of new objects
#        carry garbage); a large value overflows nlyr*nphase in cdisort's allocation and the check exits 1. Here every
#        new DisortOptions and YAML band gets a sentinel nphase, and building a solver while it is still there is
#        logged with the calling file and line. The real ch03_run.sh runs on a copy of the scripts; the log must be
#        empty and the run must exit 0. Probes [P2]-[P4] of ch03_candidates.py are exempt: they test a pyharp band
#        as pyharp builds it, ds.nphase included, and their outcome does not set any exit status.
# Exit status: 0 when every test passes, 1 otherwise.
set -u
D=$(cd "$(dirname "$0")" && pwd)
[ $# -eq 3 ] || { echo "usage: $(basename "$0") PYTHON PYDISORT_SRC PYHARP_WT" >&2; exit 2; }
PY=$(cd "$(dirname "$1")" && pwd)/$(basename "$1"); S=$(cd "$2" && pwd); H=$(cd "$3" && pwd)
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
fail=0
verdict() { local ok=$1 t=$2; shift 2; if [ "$ok" = 0 ]; then echo "[$t] PASS: $*"; else echo "[$t] FAIL: $*"; fail=1; fi; }

mkdir "$T/t1"; cp "$D/ch03_run.sh" "$T/t1/"
bash "$T/t1/ch03_run.sh" > "$T/t1.out" 2> "$T/t1.err"; rc=$?
[ $rc = 2 ] && grep -q "^usage: ch03_run.sh PYTHON PYDISORT_SRC PYHARP_WT" "$T/t1.err"; ok=$?
verdict $ok T1 "no arguments: exit $rc, stderr '$(head -1 "$T/t1.err")'"

mkdir "$T/t2"; cp "$D/ch03_run.sh" "$T/t2/"
for c in e3_slab beam_closure delta_m intensity_correction candidates disotest ordinates_algebra; do
  echo 'print("stub")' > "$T/t2/ch03_$c.py"
done
echo 'import sys; print("partial"); sys.exit("selftest: injected failure")' > "$T/t2/ch03_delta_m.py"
V=$("$PY" -c 'import pydisort; print(pydisort.__version__)')
echo "previous output" > "$T/t2/ch03_delta_m.pydisort-$V.out"
bash "$T/t2/ch03_run.sh" "$PY" "$S" "$H" > "$T/t2.out" 2> "$T/t2.err"; rc=$?
others=$(grep -c ": exit 0$" "$T/t2.out")
[ $rc = 1 ] && grep -q "ch03_delta_m" "$T/t2.err" && grep -q "injected failure" "$T/t2.err" \
  && [ "$(cat "$T/t2/ch03_delta_m.pydisort-$V.out")" = "previous output" ] && [ "$others" = 6 ]; ok=$?
verdict $ok T2 "one failing check: exit $rc, $others other checks exit 0, previous output kept:" \
  "$([ "$(cat "$T/t2/ch03_delta_m.pydisort-$V.out")" = "previous output" ] && echo yes || echo no)"

mkdir "$T/t3" "$T/t3/site"; cp "$D/ch03_candidates.py" "$T/t3/"
cat > "$T/t3/site/sitecustomize.py" <<'EOF'
import atexit, os, sys, time
if os.path.basename(sys.argv[0]) == "p1_1.py":  # [P1] upward=1: hang after the result is printed
    atexit.register(lambda: time.sleep(10 ** 6))
EOF
s=$(date +%s)
(cd "$T/t3" && PYTHONPATH="$T/t3/site" PYDISORT_SRC="$S" PYHARP_WT="$H" CUDA_VISIBLE_DEVICES= \
  timeout -s KILL 400 "$PY" ch03_candidates.py --repeat 1 --work "$T/t3/work" > "$T/t3.out" 2> "$T/t3.err"); rc=$?
w=$(( $(date +%s) - s ))
pkill -KILL -f "$T/t3/work/p1_1.py"  # a probe left behind when the harness itself was killed
[ $rc = 0 ] && grep -q "^\[P1\] CANDIDATE reproduced: pydisort upward=1, .*1 hung at exit" "$T/t3.out" \
  && grep -q "^\[P6\]" "$T/t3.out"; ok=$?
verdict $ok T3 "[P1] probe hanging at exit: ch03_candidates exit $rc after $w s; [P1] upward=1 line:" \
  "$(grep "^\[P1\] .*upward=1" "$T/t3.out" | sed 's/.*abnormal exit/abnormal exit/')"

mkdir "$T/t4" "$T/t4/site"; cp "$D"/ch03_*.py "$D/ch03_run.sh" "$T/t4/"; cp -r "$D/ch03_disotest" "$T/t4/"
cat > "$T/t4/site/sitecustomize.py" <<'EOF'
import os, sys
SENTINEL, LOG = 1000003, os.environ["CH03_NPHASE_LOG"]
import pydisort, pyharp
def _log(kind, nphase):
    f = sys._getframe(2)
    if nphase == SENTINEL and os.path.basename(f.f_code.co_filename) not in ("p2.py", "p3.py", "p4.py"):
        with open(LOG, "a") as fh:
            fh.write(f"{kind} built with ds.nphase unset at {os.path.basename(f.f_code.co_filename)}:{f.f_lineno}\n")
_DO, _D, _RB, _FY = pydisort.DisortOptions, pydisort.Disort, pyharp.RadiationBand, pyharp.RadiationOptions.from_yaml
def DisortOptions(*a, **k):
    op = _DO(*a, **k); op.ds().nphase = SENTINEL; return op
def Disort(op, *a, **k):
    _log("pydisort.Disort", op.ds().nphase); return _D(op, *a, **k)
def RadiationBand(bo, *a, **k):
    _log("pyharp.RadiationBand", bo.disort().ds().nphase); return _RB(bo, *a, **k)
def from_yaml(*a, **k):
    ro = _FY(*a, **k)
    for b in ro.bands():
        b.disort().ds().nphase = SENTINEL
    return ro
pydisort.DisortOptions, pydisort.Disort, pyharp.RadiationBand = DisortOptions, Disort, RadiationBand
pyharp.RadiationOptions.from_yaml = staticmethod(from_yaml)
EOF
: > "$T/t4.log"
PYTHONPATH="$T/t4/site" CH03_NPHASE_LOG="$T/t4.log" bash "$T/t4/ch03_run.sh" "$PY" "$S" "$H" > "$T/t4.out" 2> "$T/t4.err"
rc=$?; n=$(sort -u "$T/t4.log" | wc -l)
[ $rc = 0 ] && [ "$n" = 0 ]; ok=$?
verdict $ok T4 "ds.nphase left unset: ch03_run.sh exit $rc, $n distinct call sites" \
  "$(sort -u "$T/t4.log" | sed 's/.* at //' | tr '\n' ' ')"
exit $fail
