#!/bin/bash
# ch09: rerun of the defect-register item D1 (an abort, "double free or corruption", after pyharp's
# tests/test_rayleigh.py under pydisort 1.8.13).
#
# For each environment given as NAME=TESTS_DIR, where TESTS_DIR is the tests/ directory of the pyharp source tree
# (at the code pin) that environment's pyharp was built from, run N times (default 3):
#   * python -m pytest -v tests/test_rayleigh.py
#   * python -m pytest -q tests/        (the whole Python suite)
# and report the exit status, the pytest summary and any crash: a heap-corruption abort, SIGABRT (exit 134) or
# SIGSEGV (exit 139). D1_SETUP names a bash script that,
# sourced with NAME as its one argument, activates the Python environment NAME (PATH, LD_LIBRARY_PATH).
# An environment whose name ends in "-drift" is one in which pydisort was replaced in place after pyharp was built
# (pip install --no-deps --force-reinstall pydisort==<other version>); an abort there is printed EXPECTED-FAIL,
# an abort anywhere else is FAIL. Failures of the spectra and sonora tests (network, data files) are reported in
# the summary and do not decide the verdict, which is about the abort only.
#
# Run: D1_SETUP=<script> N=3 bash check_ch09_d1.sh 171=<tree>/tests 1813=<tree>/tests 171b-1813-drift=<tree>/tests ...
# In each "-drift" environment the two tests of test_rayleigh.py are then also run one at a time, N times each.
# Exit status: the number of FAIL lines.
N=${N:-3}
n=0
fails=0
echo "versions: per line below (pydisort as imported in each environment); pytest $(python -m pytest --version 2>&1 | head -1)"
for spec in "$@"; do
  name=${spec%%=*}
  tests=${spec#*=}
  envline=$( (source "$D1_SETUP" "$name" >/dev/null 2>&1
             python -c "import sys; sys.path.insert(0, '$(cd "$(dirname "$0")" && pwd)'); import ch09_common; print(ch09_common.env_line())" 2>/dev/null) )
  echo "env $name: $envline"
  for i in $(seq 1 "$N"); do
    for what in rayleigh full; do
      out=$( (
        source "$D1_SETUP" "$name" >/dev/null 2>&1
        cd "$tests" || exit 99
        pyd=$(python -c "import pydisort; print(pydisort.__version__)" 2>/dev/null)
        echo "PYD=$pyd"
        if [ "$what" = rayleigh ]; then
          python -m pytest -v -p no:cacheprovider test_rayleigh.py 2>&1
        else
          python -m pytest -q -p no:cacheprovider . 2>&1
        fi
        echo "RC=$?"
      ) 2>&1 )
      rc=$(echo "$out" | sed -n 's/^RC=//p' | tail -1)
      pyd=$(echo "$out" | sed -n 's/^PYD=//p' | head -1)
      summary=$(echo "$out" | grep -E "[0-9]+ (passed|failed)" | tail -1 | tr -d '=' | sed 's/^ *//; s/ *$//')
      abort=$(echo "$out" | grep -oE "double free or corruption[^\n]*|corrupted size vs\. prev_size|free\(\): [a-z ]+" | head -1)
      [ -z "$abort" ] && [ "$rc" = 134 ] && abort="SIGABRT"
      [ -z "$abort" ] && [ "$rc" = 139 ] && abort="SIGSEGV"
      n=$((n + 1))
      if [ -z "$abort" ]; then
        verdict=PASS
      elif [[ "$name" == *-drift ]]; then
        verdict=EXPECTED-FAIL
      else
        verdict=FAIL
        fails=$((fails + 1))
      fi
      echo "[C$n] $verdict env $name (pydisort $pyd) $what run $i: exit $rc; ${summary:-no summary}; abort: ${abort:-none}"
    done
  done
done
# Isolation: in each "-drift" environment, run the two tests of test_rayleigh.py one at a time, N times each.
for spec in "$@"; do
  name=${spec%%=*}
  tests=${spec#*=}
  [[ "$name" == *-drift ]] || continue
  for tid in test_radiation_band_regularizes_conservative_ssa_for_disort \
             test_rayleigh_python_binding_matches_reference_cross_section; do
    for i in $(seq 1 "$N"); do
      out=$( (
        source "$D1_SETUP" "$name" >/dev/null 2>&1
        cd "$tests" || exit 99
        python -m pytest -q -p no:cacheprovider "test_rayleigh.py::$tid" 2>&1
        echo "RC=$?"
      ) 2>&1 )
      rc=$(echo "$out" | sed -n 's/^RC=//p' | tail -1)
      summary=$(echo "$out" | grep -E "[0-9]+ (passed|failed)" | tail -1 | tr -d '=' | sed 's/^ *//; s/ *$//')
      abort=$(echo "$out" | grep -oE "double free or corruption[^\n]*|corrupted size vs\. prev_size|free\(\): [a-z ]+" | head -1)
      [ -z "$abort" ] && [ "$rc" = 134 ] && abort="SIGABRT"
      [ -z "$abort" ] && [ "$rc" = 139 ] && abort="SIGSEGV"
      n=$((n + 1))
      verdict=PASS
      [ -n "$abort" ] && verdict=EXPECTED-FAIL
      echo "[C$n] $verdict env $name, $tid alone, run $i: exit $rc; ${summary:-no summary}; abort: ${abort:-none}"
    done
  done
done
echo "== check_ch09_d1: $n labels, $fails FAIL"
exit $fails
