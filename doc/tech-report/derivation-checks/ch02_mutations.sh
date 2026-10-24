#!/bin/bash
# Mutation and control runs for check [C9] of check_ch02_conservation.py (the two-layer shortwave tridiagonal system)
# and for the beam coefficients of check_ch02_closures.py ([C1]-[C10], [C22]).
# usage: ch02_mutations.sh ENV [CONSERVATION_CHECK [CLOSURES_CHECK]]   (ENV made by derivation-checks/ch04/setup_env.sh;
#        the checks default to this repository's and may name other versions of them, to compare)
# M17-M17e change one entry of the conservation check's transcription, covering all four rows; M17k changes such an
# entry in a copy of the kernel source (toon_mckay89_shortwave_impl.h) that the check reads through PYHARP_WT, and
# M17k2 leaves the correct line behind in a comment. M14 breaks the one-layer closed form, outside [C9]. M7-M7c break
# the derived g4 of check_ch02_closures.py; M2 breaks a printed g3. Each run copies the check to a fresh temporary
# directory, applies one sed expression, runs it and compares the claims that FAIL with the expected set: OK when
# they are equal (a control expects none and exit 0), MISMATCH otherwise, CRASH when the check stops before its
# summary line. The controls K17 and K7 run the copies unchanged. The script exits with the number of runs that are
# not OK. The temporary directories are mktemp's default; the checks need only PYHARP_WT, not their location.
set -u
D=$(cd "$(dirname "$0")" && pwd)
E=$(cd "$1" && pwd); PY="$E/venv/bin/python"
abspath() { echo "$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"; }
CONS=$(abspath "${2:-$D/check_ch02_conservation.py}"); CLOS=$(abspath "${3:-$D/check_ch02_closures.py}")
CK=$CONS
SWK=src/rtsolver/toon_mckay89_shortwave_impl.h
export CUDA_VISIBLE_DEVICES=
run() {  # id, what, expected failing claims ('' for none), sed expression on the check, sed on the kernel copy
  W=$(mktemp -d); cp "$CK" "$W/check.py"; mkdir -p "$W/tree/src/rtsolver"; cp "$E/pyharp/$SWK" "$W/tree/$SWK"
  [ -n "$4" ] && sed -i "$4" "$W/check.py"
  [ -n "$5" ] && sed -i "$5" "$W/tree/$SWK"
  if { [ -n "$4" ] && cmp -s "$CK" "$W/check.py"; } || { [ -n "$5" ] && cmp -s "$E/pyharp/$SWK" "$W/tree/$SWK"; }; then
    echo "[$1] ERROR mutation did not apply: $2"; bad=$((bad + 1)); rm -rf "$W"; return
  fi
  out=$(cd "$W" && PYHARP_WT="$W/tree" "$PY" -I check.py 2>&1); rc=$?
  fails=$(echo "$out" | grep -o '^\[C[0-9]*\] FAIL' | sed 's/ FAIL//' | tr '\n' ' ' | sed 's/ $//')
  if ! echo "$out" | grep -q 'claims pass$'; then
    verdict="CRASH ($(echo "$out" | grep -m1 -E 'Error|error' | cut -c1-80))"
  elif [ "$fails" = "$3" ] && { [ -n "$3" ] || [ "$rc" = 0 ]; }; then
    verdict="OK"
  else
    verdict="MISMATCH"
  fi
  [ "$verdict" = OK ] || bad=$((bad + 1))
  echo "[$1] $2: exit $rc; failing: ${fails:-none}; expected: ${3:-none}; $verdict"
  rm -rf "$W"
}
bad=0
run M17 "row 1 (top): Gamma0 - 1 written Gamma0 + 1" '[C9]' 's|\[\[G0 + 1, G0 - 1, 0, 0\]|[[G0 + 1, G0 + 1, 0, 0]|' ''
run M17b "row 2 (interface F+), column 1: (E1 + E3) written (E1 - E3)" '[C9]' 's|\[(E1 + E3) \* (Gb - 1), (E2 + E4)|[(E1 - E3) * (Gb - 1), (E2 + E4)|' ''
run M17c "row 3 (interface F-), column 2: Gamma of the upper layer written as the lower one's" '[C9]' 's|\[0, 2 \* (1 - G0\*\*2), (E1 - E3)|[0, 2 * (1 - Gb**2), (E1 - E3)|' ''
run M17d "row 3 (interface F-), column 3: (E1 - E3) written (E1 + E3)" '[C9]' 's|(E1 - E3) \* (1 + Gb), (E1 + E3) \* (Gb - 1)\]|(E1 + E3) * (1 + Gb), (E1 + E3) * (Gb - 1)]|' ''
run M17e "row 4 (bottom): columns 3 and 4 swapped" '[C9]' 's|\[0, 0, F1\([^,]*\), F2\([^]]*\)\]\]|[0, 0, F2\2, F1\1]]|' ''
run M17k "kernel copy: Bf of the odd rows with (E1 + E3) for (E1 - E3)" '[C9]' '' 's|Bf\[i - 1\] = (E1\[n_idx\] - E3\[n_idx\]) \* (1.0 + gam\[n_idx + 1\]);|Bf[i - 1] = (E1[n_idx] + E3[n_idx]) * (1.0 + gam[n_idx + 1]);|'
run M17k2 "kernel copy: the same wrong Bf line, followed by the correct one in a comment" '[C9]' '' 's|^\( *\)Bf\[i - 1\] = (E1\[n_idx\] - E3\[n_idx\]) \* (1.0 + gam\[n_idx + 1\]);|\1Bf[i - 1] = (E1[n_idx] + E3[n_idx]) * (1.0 + gam[n_idx + 1]);  // Bf[i - 1] = (E1[n_idx] - E3[n_idx]) * (1.0 + gam[n_idx + 1]);|'
run M14 "control break outside [C9]: closed form's surface row (1 - As Gm) written (1 + As Gm)" '[C19]' 's|mp.exp(L \* ts) \* (1 - As \* Gm)|mp.exp(L * ts) * (1 + As * Gm)|' ''
run K17 "control: check and kernel copy unchanged" '' '' ''
CK=$CLOS
run M7 "closures: Eddington g4 integrates p(mu0, -mu) instead of p(mu0, mu)" '[C1] [C2] [C22]' 's|out\["g4"\] = sp.integrate(p_lin(mu0, mu), (mu, 0, 1))|out["g4"] = sp.integrate(p_lin(mu0, -mu), (mu, 0, 1))|' ''
run M7b "closures: full-phase-function rows with g4 = b0 instead of 1 - b0" '[C3] [C6] [C7] [C8] [C9] [C22]' 's|out\["g3"\], out\["g4"\] = b0, 1 - b0|out["g3"], out["g4"] = b0, b0|' ''
run M7c "closures: quadrature g4 = p(qnode, -mu0)/(2w) instead of p(qnode, mu0)/(2w)" '[C4] [C5] [C22]' 's|p_lin(c\["qnode"\], mu0) / (2 \* w)  # MW eqs. 41, 42|p_lin(c["qnode"], -mu0) / (2 * w)  # MW eqs. 41, 42|' ''
run M2 "control break: printed Eddington g3 with 2 g mu0 for 3 g mu0" '[C1] [C2] [C15]' 's|g3=(2 - 3 \* g \* mu0) / 4)|g3=(2 - 2 * g * mu0) / 4)|' ''
run K7 "control: closures check unchanged" '' '' ''
echo "ch02_mutations: $bad run(s) not as expected"
exit $bad
