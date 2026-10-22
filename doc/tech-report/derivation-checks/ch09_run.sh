#!/bin/bash
# Regenerate every ch09 output: check_ch09_batch_device_pydisort{171,1813}.out (and the support-matrix cells in
# src/pyharp_report/ch09/data), check_ch09_matrix.out, check_ch09_abi.out and check_ch09_d1.out.
# usage: ch09_run.sh ROOT
#   ROOT  the directory four ch09_setup.sh runs built into:
#           ch09_setup.sh ROOT 1.7.1 cuda          -> venv-1.7.1, pyharp-1.7.1
#           ch09_setup.sh ROOT 1.8.13 cuda         -> venv-1.8.13, pyharp-1.8.13
#           ch09_setup.sh ROOT 1.7.1 cuda 1.8.13   -> venv-1.7.1-drift-1.8.13 (built on 1.7.1, runs 1.8.13)
#           ch09_setup.sh ROOT 1.8.13 cuda 1.7.1   -> venv-1.8.13-drift-1.7.1 (built on 1.8.13, runs 1.7.1)
#         Each environment and source tree can be given instead by VENV_171, VENV_1813, VENV_171D, VENV_1813D and
#         TREE_171, TREE_1813, TREE_171D, TREE_1813D (a venv directory holding env.sh; a pyharp source tree).
# Needs a CUDA GPU for the CUDA comparisons (without one they are reported "not run"), g++ and readelf.
# check_ch09_d1.out records crashes that vary from run to run (see the chapter).
set -u
D=$(cd "$(dirname "$0")" && pwd)
R=${1:-}
DATA=$D/../src/pyharp_report/ch09/data
V171=${VENV_171:-$R/venv-1.7.1};   T171=${TREE_171:-$R/pyharp-1.7.1}
V1813=${VENV_1813:-$R/venv-1.8.13}; T1813=${TREE_1813:-$R/pyharp-1.8.13}
V171D=${VENV_171D:-$R/venv-1.7.1-drift-1.8.13};  T171D=${TREE_171D:-$R/pyharp-1.7.1-drift-1.8.13}
V1813D=${VENV_1813D:-$R/venv-1.8.13-drift-1.7.1}; T1813D=${TREE_1813D:-$R/pyharp-1.8.13-drift-1.7.1}
run() {  # $1 venv, $2 output name, rest: command
  local v=$1 out=$2; shift 2
  local w; w=$(mktemp -d)
  (source "$v/env.sh" && cd "$w" && "$@" > "$D/$out" 2>/dev/null)
  echo "$out: exit $? ($(tail -1 "$D/$out"))"
  rm -rf "$w"
}
run "$V171" check_ch09_batch_device_pydisort171.out env PYHARP_WT="$T171" python "$D/check_ch09_batch_device.py" --data "$DATA"
run "$V1813" check_ch09_batch_device_pydisort1813.out env PYHARP_WT="$T1813" python "$D/check_ch09_batch_device.py" --data "$DATA"
run "$V171" check_ch09_matrix.out python "$D/check_ch09_matrix.py" "$DATA"
sp() { (source "$1/env.sh" && python -c 'import sysconfig; print(sysconfig.get_paths()["platlib"])'); }
run "$V171" check_ch09_abi.out python "$D/check_ch09_abi.py" "$(sp "$V171")" "$(sp "$V1813")"
M=$(mktemp)
cat > "$M" <<SETUP
case "\$1" in
  171) source "$V171/env.sh";; 1813) source "$V1813/env.sh";;
  171b-1813-drift) source "$V171D/env.sh";; 1813b-171-drift) source "$V1813D/env.sh";;
esac
SETUP
run "$V171" check_ch09_d1.out env D1_SETUP="$M" N=3 bash "$D/check_ch09_d1.sh" 171="$T171/tests" \
  1813="$T1813/tests" 171b-1813-drift="$T171D/tests" 1813b-171-drift="$T1813D/tests"
rm -f "$M"
