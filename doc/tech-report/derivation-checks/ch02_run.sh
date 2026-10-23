#!/bin/bash
# Regenerate every ch02 check output, writing the outputs next to the scripts.
# usage: ch02_run.sh ENV_1.7.1 [ENV_1.8.13]
#   ENV_*  directories made by derivation-checks/ch04/setup_env.sh <dir> <pydisort version>
# Writes: check_ch02_{closures,conservation,delta_scaling,toon_coefficients}.out (first environment; they read the
#         pyharp source of this repository), check_ch02_clamp_pyharp_pydisort<version>.out for each environment,
#         ch02_mutations.out (mutation and control runs of [C9] and of the closures check, first environment), and,
#         when CH02_BREAKS_WORK names a scratch directory, ch02_clamp_breaks.out (source-break runs of the clamp check;
#         slow, rebuilds pyharp).
# Runs on CPU (CUDA_VISIBLE_DEVICES is emptied), each check from a fresh temporary directory.
set -u
D=$(cd "$(dirname "$0")" && pwd)
export CUDA_VISIBLE_DEVICES=
E1=$(cd "$1" && pwd)
for c in closures conservation delta_scaling toon_coefficients; do
  W=$(mktemp -d)
  (cd "$W" && "$E1/venv/bin/python" -I "$D/check_ch02_$c.py" > "$D/check_ch02_$c.out")
  echo "check_ch02_$c: exit $?"
  rm -rf "$W"
done
for E in "$@"; do
  E=$(cd "$E" && pwd); PY="$E/venv/bin/python"
  V=$("$PY" -c 'import pydisort; print(pydisort.__version__.replace(".", ""))')
  W=$(mktemp -d)
  (cd "$W" && PYHARP_WT="$E/pyharp" "$PY" -I "$D/check_ch02_clamp_pyharp.py" --work "$W" > "$D/check_ch02_clamp_pyharp_pydisort$V.out")
  echo "check_ch02_clamp_pyharp (pydisort $V): exit $?"
  rm -rf "$W"
done
bash "$D/ch02_mutations.sh" "$E1" > "$D/ch02_mutations.out"
echo "ch02_mutations: exit $?"
if [ -n "${CH02_BREAKS_WORK:-}" ]; then
  bash "$D/ch02_clamp_breaks.sh" "$E1" "$CH02_BREAKS_WORK" > "$D/ch02_clamp_breaks.out"
  echo "ch02_clamp_breaks: exit $?"
fi
