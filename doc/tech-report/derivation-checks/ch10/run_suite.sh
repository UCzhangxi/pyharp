#!/bin/bash
# Chapter 10 check: run every pyharp test that exists at the pin, not only those CI runs, and summarise.
#
# usage: run_suite.sh <pyharp source tree, built with -DBUILD_TESTS=ON in ./build> <scratch dir>
#   The python on PATH must import the pyharp built from that tree and the pydisort under test.
#
# Prints labelled summary lines (paths replaced by <src> and <scratch>), so the output can be committed:
#   [S1] ctest with GPUs visible, [S2] ctest with CUDA_VISIBLE_DEVICES= (as on CI's CPU runners),
#   [S3] each unregistered C++ test file built out of tree (extra_tests/CMakeLists.txt) and run,
#   [S4] each top-level Python test file (pytest, from a copy of tests/ as ctest would stage it),
#   [S5] each tests/spectra file (pytest from the source root, as CI runs its three), with the one intermittent test
#        (FLAKY below) deselected so the output is deterministic; flaky_rerun.sh measures that test on its own,
#   [S6] tests/test_rayleigh.py three times: exit status and any glibc heap-corruption abort.
# Exit status 0; the numbers are the result.
SRC=$(cd "$1" && pwd); SCR=$(mkdir -p "$2" && cd "$2" && pwd)
HERE=$(cd "$(dirname "$0")" && pwd)
FLAKY="tests/spectra/test_hitemp_lines.py::test_prepare_reads_zip_and_bz2_and_reuses_cache"
clean() { sed -E -e "s#$SRC#<src>#g" -e "s#$SCR#<scratch>#g" -e 's/ in [0-9.]+s( \([0-9:]+\))?//' -e 's/ +[0-9.]+ sec$//'; }
python -c "import pyharp, pydisort, torch, sys; print(f'[S0] pyharp {pyharp.__version__}, pydisort {pydisort.__version__}, torch {torch.__version__}, Python {sys.version.split()[0]}')"

for mode in visible hidden; do
  label=S1; env=""; [ $mode = hidden ] && { label=S2; env="CUDA_VISIBLE_DEVICES="; }
  out=$(cd "$SRC/build/tests" && env $env ctest 2>&1)
  echo "[$label] ctest, GPUs $mode: $(echo "$out" | grep -E 'tests passed' | head -1)"
  echo "$out" | grep -E '\*\*\*Failed|\*\*\*Exception' | sed "s/^/[$label]   /" | clean
done

EXTRA="test_composition;test_helios_ck_read;test_radiation;test_read_cia_ff;test_read_rayleigh;test_read_stellar_flux;test_read_yaml;test_yaml_input"
SITE=$(python -c "import pydisort,os;print(os.path.dirname(pydisort.__file__))")
TP=$(python -c "import torch.utils;print(torch.utils.cmake_prefix_path)")
cmake -S "$HERE/extra_tests" -B "$SCR/extra" -DCMAKE_PREFIX_PATH="$TP" -DPYHARP_SRC="$SRC" -DPYHARP_BUILD="$SRC/build" \
  -DDISORT_INC="$SITE" "-DEXTRA_TESTS=$EXTRA" > "$SCR/extra_cmake.txt" 2>&1
mkdir -p "$SCR/extra/run"; cp "$SRC"/tests/*.inp "$SRC"/tests/*.yaml "$SCR/extra/run/" 2>/dev/null
for t in ${EXTRA//;/ }; do
  if cmake --build "$SCR/extra" --target $t -j4 > "$SCR/extra_build_$t.txt" 2>&1; then
    (cd "$SCR/extra/run" && CUDA_VISIBLE_DEVICES= timeout 300 ../$t > "$SCR/extra_run_$t.txt" 2>&1); rc=$?
    res=$(grep -E '^\[  (PASSED|FAILED)  \] [0-9]+ test' "$SCR/extra_run_$t.txt" | tr '\n' ' ')
    first=$(grep -m1 -E 'Failed to open|Failure$' -A0 "$SCR/extra_run_$t.txt" | head -1)
    echo "[S3] $t: built, exit $rc ${res:-no gtest summary} ${first:+| first failure: $first}" | clean
  else
    echo "[S3] $t: does not compile | $(grep -m1 -E 'error' "$SCR/extra_build_$t.txt" | sed 's/^.*tests\///' | cut -c1-140)" | clean
  fi
done

mkdir -p "$SCR/run"; cp "$SRC"/tests/*.py "$SRC"/tests/*.yaml "$SCR/run/"
for f in $(cd "$SRC/tests" && ls test_*.py); do
  { (cd "$SCR/run" && timeout 900 python -m pytest -q -p no:cacheprovider "$f" > "$SCR/py_$f.txt" 2>&1); } 2>/dev/null; rc=$?
  abort=$(grep -o -m1 -E 'double free or corruption \([^)]*\)|free\(\): [a-z ]*|Segmentation fault' "$SCR/py_$f.txt")
  echo "[S4] tests/$f: exit $rc, $(grep -E '[0-9]+ (passed|failed)' "$SCR/py_$f.txt" | tail -1 | sed 's/=//g; s/^ *//') ${abort:+| $abort}" | clean
done
for f in $(cd "$SRC/tests/spectra" && ls test_*.py); do
  (cd "$SRC" && timeout 900 python -m pytest -q -p no:cacheprovider --deselect "$FLAKY" "tests/spectra/$f" > "$SCR/sp_$f.txt" 2>&1); rc=$?
  echo "[S5] tests/spectra/$f: exit $rc, $(grep -E '[0-9]+ (passed|failed|deselected)' "$SCR/sp_$f.txt" | tail -1 | sed 's/=//g; s/^ *//')" | clean
  grep -E '^FAILED' "$SCR/sp_$f.txt" | sed 's/ - .*//; s/^/[S5]   /'
done
for i in 1 2 3; do
  { (cd "$SCR/run" && timeout 300 python -m pytest -q -p no:cacheprovider test_rayleigh.py > "$SCR/ray_$i.txt" 2>&1); } 2>/dev/null; rc=$?
  echo "[S6] tests/test_rayleigh.py run $i: exit $rc, $(grep -o -E '[0-9]+ passed|[0-9]+ failed' "$SCR/ray_$i.txt" | tr '\n' ' ')$(grep -o -m1 -E 'double free or corruption \([^)]*\)|free\(\): [a-z ]*' "$SCR/ray_$i.txt")"
done
