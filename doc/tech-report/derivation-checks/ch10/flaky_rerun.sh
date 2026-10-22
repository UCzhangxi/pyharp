#!/bin/bash
# Chapter 10 check: rerun the one intermittent spectra test N times and count failures.
# usage: flaky_rerun.sh <pyharp source tree> <N>   (python on PATH: the environment under test)
# Prints [F0] the environment and [F1] the count. The count is a sample of a random event and is not expected to be
# the same on a rerun; the chapter quotes the committed output as one observation.
SRC=$(cd "$1" && pwd); N=$2
T="tests/spectra/test_hitemp_lines.py::test_prepare_reads_zip_and_bz2_and_reuses_cache"
python -c "import pyharp, pydisort, sys; print(f'[F0] pyharp {pyharp.__version__}, pydisort {pydisort.__version__}, Python {sys.version.split()[0]}')"
fail=0
for i in $(seq 1 "$N"); do
  (cd "$SRC" && python -m pytest -q -p no:cacheprovider "$T" > /dev/null 2>&1) || fail=$((fail + 1))
done
echo "[F1] $T: $fail failed of $N runs (temporary directory on $(stat -f -c %T "${TMPDIR:-/tmp}"))"
