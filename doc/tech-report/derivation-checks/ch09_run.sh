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
# Without a GPU, or with one the environment's torch has no kernels for (sm_120 under the cu126 pin;
# cuda_capability.py says why), the CUDA legs are reported "not run" with the reason, every leg runs with
# CUDA_VISIBLE_DEVICES=, and the comparison leaves out the CUDA lines and check_ch09_d1.out. ch09_setup.sh installs a torch with sm_120 kernels on
# such a host, so this happens only when that was not done.
# Afterwards the regenerated outputs are compared with the committed ones (compare.sh, tools/compare_outputs.py):
# version, host, timing and date lines are normalised, everything else must match. Exit status 0 when the chapter
# is REPRODUCED (or REPRODUCED WITHOUT CUDA, with the reason), 1 when any check output differs.
set -u
D=$(cd "$(dirname "$0")" && pwd)
R=${1:-}
source "$D/compare.sh"
DATA=$D/../src/pyharp_report/ch09/data
V171=${VENV_171:-$R/venv-1.7.1};   T171=${TREE_171:-$R/pyharp-1.7.1}
V1813=${VENV_1813:-$R/venv-1.8.13}; T1813=${TREE_1813:-$R/pyharp-1.8.13}
V171D=${VENV_171D:-$R/venv-1.7.1-drift-1.8.13};  T171D=${TREE_171D:-$R/pyharp-1.7.1-drift-1.8.13}
V1813D=${VENV_1813D:-$R/venv-1.8.13-drift-1.7.1}; T1813D=${TREE_1813D:-$R/pyharp-1.8.13-drift-1.7.1}
CUDA_SKIP=$(source "$V171/env.sh" && python "$D/cuda_capability.py"); CUDA_RC=$?
echo "CUDA ($(basename "$V171")): $CUDA_SKIP"
CMP_OPTS=()
if [ $CUDA_RC = 3 ]; then
  export CUDA_VISIBLE_DEVICES= CUDA_SKIP_REASON="${CUDA_SKIP#skip: }"
  # the float32 floor lines set the tolerance of a CUDA float32 comparison and are printed only with it
  CMP_OPTS=(--exclude-cuda "$CUDA_SKIP_REASON" --cuda-lines '\bCUDA\b|float32 floor, CPU float32 vs CPU float64'
            --not-compared check_ch09_d1.out)
  echo "ch09: CUDA legs not run: $CUDA_SKIP_REASON"
fi
snapshot_outputs check_ch09_batch_device_pydisort171.out check_ch09_batch_device_pydisort1813.out \
  check_ch09_matrix.out check_ch09_abi.out check_ch09_d1.out
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
compare_outputs ch09 "${CMP_OPTS[@]}"
