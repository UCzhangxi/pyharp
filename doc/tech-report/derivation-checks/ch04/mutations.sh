#!/bin/bash
# Mutation and control runs for the chapter 4 checks of the review fixes (B1, B2, B3, N1; defects P11, P12 and its scope).
# usage: mutations.sh ENV   (a directory made by setup_env.sh; its python runs every check)
# Each mutation copies one check to a fresh temporary directory, changes one line with sed, runs it and records the
# exit status and the labels that FAIL; the control runs the same copy unchanged. A mutation must exit non-zero and
# its control must exit 0.
set -u
D=$(cd "$(dirname "$0")" && pwd); R=$(cd "$D/../.." && pwd)
E=$(cd "$1" && pwd); PY="$E/venv/bin/python"
export PYHARP_WT="$E/pyharp" CUDA_VISIBLE_DEVICES=
SW="$R/src/pyharp_report/ch04/checks/shortwave_check.py"
PL="$R/src/pyharp_report/ch04/checks/planck_check.py"
DF="$D/defects_pyharp_check.py"
run() {  # id, what, file, sed expression ('' for the control)
  W=$(mktemp -d); cp "$3" "$W/check.py"
  [ -n "$4" ] && sed -i "$4" "$W/check.py"
  if [ -n "$4" ] && cmp -s "$3" "$W/check.py"; then echo "[$1] ERROR mutation did not apply: $2"; rm -rf "$W"; return; fi
  out=$(cd "$W" && "$PY" -I check.py 2>&1); rc=$?
  fails=$(echo "$out" | grep -o '^\[C[0-9]*\] FAIL' | sed 's/ FAIL//' | tr '\n' ' ')
  echo "[$1] $2: exit $rc; failing: ${fails:-none}"
  rm -rf "$W"
}
run M1 "B3 mutation: shortwave_check ROW2_MULTIPLIER = gamma1 - 1/mu0" "$SW" 's|^ROW2_MULTIPLIER = "gamma2"|ROW2_MULTIPLIER = "gamma1 - 1/mu0"|'
run K1 "B3 control: shortwave_check unchanged" "$SW" ''
run M2 "B1 mutation: planck_check inclusive port written strict (v < VCUT)" "$PL" 's|small = v\[i\] <= VCUT|small = v[i] < VCUT|'
run K2 "B1 control: planck_check unchanged" "$PL" ''
run M3 "P11 mutation: defects check off the switch, T(1 + 1e-12)" "$DF" 's|^T_SWITCH = 300.0 \* 1.438786 / 1.5 |T_SWITCH = 300.0 * 1.438786 / 1.5 * (1 + 1e-12) |'
run M4 "P12 mutation: defects check off the resonance, w(1 - 1e-7)" "$DF" 's|^W_RES = 1.0 - 1.0 / (4.0 \* U_RES \* U_RES)|W_RES = (1.0 - 1.0 / (4.0 * U_RES * U_RES)) * (1 - 1e-7)|'
run K3 "P11/P12 control: defects check unchanged" "$DF" ''
run M5 "N1 mutation: planck_check quotes the relative errors as ratios, STRICT_RATIOS = (-3.04, 11.5)" "$PL" 's|^STRICT_RATIOS = (-2.04, 12.5)|STRICT_RATIOS = (-3.04, 11.5)|'
run M6 "P12 scope mutation: defects check with the earlier claim, SCOPE = exact equality only" "$DF" 's|^SCOPE = "near-resonance and thick layers"|SCOPE = "exact equality only"|'
