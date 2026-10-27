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
# The abort of the whole suite in a drifted build is intermittent (a corrupted heap: which check fires, and
# whether the run aborts at all, is chance; on one host 1 of 3 runs was clean). So in a "-drift" environment the
# whole suite is not reported run by run but run NF times (D1_FULL_RUNS, default 10) as one line, "ended abnormally
# (abort, crash or hung) in k of NF", EXPECTED-FAIL when k >= 1 and PASS when k = 0. A run counts as abnormal when it
# aborts, crashes (exit 134 or 139) or is killed after D1_TIMEOUT seconds (default 600). NF = 10: a run takes 6-37 s
# (32 s on average over 20 runs on one host), so 10 runs cost about 5 minutes; the measured abort rates are 37 of 39,
# 2 of 3 and 3 of 3 on three hosts (host-dependent.json), and even at a rate of 1/2 the chance that 10 runs of a build
# that still has the defect are all clean is 2^-10 = 1e-3 (1.7e-5 at 2/3).
#
# Run: D1_SETUP=<script> N=3 bash check_ch09_d1.sh 171=<tree>/tests 1813=<tree>/tests 171b-1813-drift=<tree>/tests ...
# In each "-drift" environment the two tests of test_rayleigh.py are then also run one at a time, N times each.
# Exit status: the number of FAIL lines.
N=${N:-3}
NF=${D1_FULL_RUNS:-10}
TMO=${D1_TIMEOUT:-600}
n=0
fails=0
abort_of() {  # $1 output, $2 exit status: the abort message, SIGABRT/SIGSEGV, "hung" or nothing
  local a
  a=$(echo "$1" | grep -oE "double free or corruption[^\n]*|corrupted size vs\. prev_size|free\(\): [a-z ]+" | head -1)
  [ -z "$a" ] && [ "$2" = 134 ] && a="SIGABRT"
  [ -z "$a" ] && [ "$2" = 139 ] && a="SIGSEGV"
  [ -z "$a" ] && { [ "$2" = 124 ] || [ "$2" = 137 ]; } && a="hung (killed after $TMO s)"
  echo "$a"
}
echo "versions: per line below (pydisort as imported in each environment); pytest $(python -m pytest --version 2>&1 | head -1)"
for spec in "$@"; do
  name=${spec%%=*}
  tests=${spec#*=}
  envline=$( (source "$D1_SETUP" "$name" >/dev/null 2>&1
             python -c "import sys; sys.path.insert(0, '$(cd "$(dirname "$0")" && pwd)'); import ch09_common; print(ch09_common.env_line())" 2>/dev/null) )
  echo "env $name: $envline"
  whats="rayleigh full"
  [[ "$name" == *-drift ]] && whats=rayleigh   # the whole suite of a drifted build: NF runs, one line, below
  for i in $(seq 1 "$N"); do
    for what in $whats; do
      out=$( (
        source "$D1_SETUP" "$name" >/dev/null 2>&1
        cd "$tests" || exit 99
        pyd=$(python -c "import pydisort; print(pydisort.__version__)" 2>/dev/null)
        echo "PYD=$pyd"
        if [ "$what" = rayleigh ]; then
          timeout --kill-after=10 "$TMO" python -m pytest -v -p no:cacheprovider test_rayleigh.py 2>&1
        else
          timeout --kill-after=10 "$TMO" python -m pytest -q -p no:cacheprovider . 2>&1
        fi
        echo "RC=$?"
      ) 2>&1 )
      rc=$(echo "$out" | sed -n 's/^RC=//p' | tail -1)
      pyd=$(echo "$out" | sed -n 's/^PYD=//p' | head -1)
      summary=$(echo "$out" | grep -E "[0-9]+ (passed|failed)" | tail -1 | tr -d '=' | sed 's/^ *//; s/ *$//')
      abort=$(abort_of "$out" "$rc")
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
  [[ "$name" == *-drift ]] || continue
  k=0; rcs=(); aborts=()
  for i in $(seq 1 "$NF"); do
    out=$( (
      source "$D1_SETUP" "$name" >/dev/null 2>&1
      cd "$tests" || exit 99
      echo "PYD=$(python -c "import pydisort; print(pydisort.__version__)" 2>/dev/null)"
      timeout --kill-after=10 "$TMO" python -m pytest -q -p no:cacheprovider . 2>&1
      echo "RC=$?"
    ) 2>&1 )
    rc=$(echo "$out" | sed -n 's/^RC=//p' | tail -1)
    pyd=$(echo "$out" | sed -n 's/^PYD=//p' | head -1)
    abort=$(abort_of "$out" "$rc")
    rcs+=("$rc")
    [ -n "$abort" ] && { k=$((k + 1)); aborts+=("$abort"); }
  done
  n=$((n + 1))
  verdict=PASS
  [ "$k" -ge 1 ] && verdict=EXPECTED-FAIL
  ab=$(printf '%s\n' "${aborts[@]}" | sed '/^$/d' | sort | uniq -c | sed 's/^ *\([0-9]*\) \(.*\)/\2 x\1/' | paste -sd, - | sed 's/,/, /g')
  echo "[C$n] $verdict env $name (pydisort $pyd) full suite, $NF runs: ended abnormally (abort, crash or hung) in $k of $NF;" \
       "exit codes [$(IFS=,; echo "${rcs[*]}" | sed 's/,/, /g')]; aborts: ${ab:-none}"
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
        timeout --kill-after=10 "$TMO" python -m pytest -q -p no:cacheprovider "test_rayleigh.py::$tid" 2>&1
        echo "RC=$?"
      ) 2>&1 )
      rc=$(echo "$out" | sed -n 's/^RC=//p' | tail -1)
      summary=$(echo "$out" | grep -E "[0-9]+ (passed|failed)" | tail -1 | tr -d '=' | sed 's/^ *//; s/ *$//')
      abort=$(abort_of "$out" "$rc")
      n=$((n + 1))
      verdict=PASS
      [ -n "$abort" ] && verdict=EXPECTED-FAIL
      echo "[C$n] $verdict env $name, $tid alone, run $i: exit $rc; ${summary:-no summary}; abort: ${abort:-none}"
    done
  done
done
echo "== check_ch09_d1: $n labels, $fails FAIL"
exit $fails
