#!/bin/bash
# Source-break runs for check_ch02_clamp_pyharp.py: break the albedo clamp in a scratch build of pyharp and run the check.
# usage: ch02_clamp_breaks.sh ENV WORK [TEXT_CHECK]   (ENV made by derivation-checks/ch04/setup_env.sh; WORK a scratch
#        directory; TEXT_CHECK another version of check_ch02_toon_coefficients.py whose [C24] is reported, to compare)
# WORK/pyharp is a git worktree of ENV/pyharp at its commit and WORK/venv a copy of ENV/venv; neither ENV is changed.
# Each break edits one line, rebuilds incrementally and reinstalls pyharp into WORK/venv, then runs
# check_ch02_clamp_pyharp.py and check [C24] of check_ch02_toon_coefficients.py (the text match) against WORK/pyharp. The
# controls are M38 (a margin of 1e-10, which [C1] must catch) and the unchanged source (K0, exit 0). Every break must
# fail check_ch02_clamp_pyharp.py.
# Slow: each rebuild and reinstall takes minutes.
set -u
D=$(cd "$(dirname "$0")" && pwd)
E=$(cd "$1" && pwd); mkdir -p "$2"; W=$(cd "$2" && pwd)
[ -d "$W/pyharp" ] || git -C "$E/pyharp" worktree add -q --detach "$W/pyharp" "$(git -C "$E/pyharp" rev-parse HEAD)"
[ -d "$W/venv" ] || cp -a "$E/venv" "$W/venv"
PY="$W/venv/bin/python"; S="$W/pyharp"
TXT=$(cd "$(dirname "${3:-$D/check_ch02_toon_coefficients.py}")" && pwd)/$(basename "${3:-check_ch02_toon_coefficients.py}")
RB=src/radiation/radiation_band.cpp; SWK=src/rtsolver/toon_mckay89_shortwave_impl.h; LWK=src/rtsolver/toon_mckay89_longwave_impl.h
export CUDA_VISIBLE_DEVICES= PYHARP_WT="$S"
build() {
  (cd "$S" && export PATH="$W/venv/bin:$PATH" &&
   { [ -d build ] || cmake -B build -DCMAKE_BUILD_TYPE=Release -DNETCDF=ON -DBUILD_TESTS=ON -DBUILD_EXAMPLES=OFF; } &&
   cmake --build build --config Release --parallel 4 && python -m pip install -q --no-build-isolation --no-deps .) \
    > "$W/build.log" 2>&1
}
run() {  # id, what, then pairs of (file, sed expression)
  id=$1; what=$2; shift 2
  git -C "$S" checkout -q -- src
  while [ $# -gt 0 ]; do
    cp "$S/$1" "$W/orig"; sed -i "$2" "$S/$1"
    if cmp -s "$W/orig" "$S/$1"; then echo "[$id] ERROR break did not apply to $1: $what"; return; fi
    shift 2
  done
  if ! build; then echo "[$id] ERROR build failed: $what"; return; fi
  T=$(mktemp -d)
  out=$(cd "$T" && "$PY" -I "$D/check_ch02_clamp_pyharp.py" --work "$T" 2>&1); rc=$?
  fails=$(echo "$out" | grep -o '^\[C[0-9]*\] FAIL' | sed 's/ FAIL//' | tr '\n' ' ')
  txt=$(cd "$T" && "$PY" -I "$TXT" 2>&1 | grep -o '^\[C24\] [A-Z]*')
  echo "[$id] $what: check_ch02_clamp_pyharp exit $rc, failing: ${fails:-none}; text match $txt"
  rm -rf "$T"
}
run M39 "clamp line commented out" \
  "$RB" 's|^\( *\)prop.select(-1, disort::ISS).clamp_max_(1.0 - ssa_margin);|\1// prop.select(-1, disort::ISS).clamp_max_(1.0 - ssa_margin);|'
run M40 "the clamp's guard if (nprop > 1) written if (false)" \
  "$RB" '/Conservative scattering is degenerate/,/clamp_max_/ s|if (nprop > 1) {|if (false) {|'
run M41 "cap inside the longwave kernel: w0[k] = fmin(w0[k], 1.0 - 1.0e-12) before alp[k]" \
  "$LWK" 's|^\( *\)alp\[k\] = sqrt((1.0 - w0\[k\]) / (1.0 - w0\[k\] \* hg\[k\]));|\1w0[k] = fmin(w0[k], 1.0 - 1.0e-12);\n\1alp[k] = sqrt((1.0 - w0[k]) / (1.0 - w0[k] * hg[k]));|'
run M38 "control break: double-precision margin 1e-12 written 1e-10" \
  "$RB" 's|torch::kFloat64 ? 1.0e-12 : 1.0e-6;|torch::kFloat64 ? 1.0e-10 : 1.0e-6;|'
run K0 "control: source unchanged"
git -C "$S" checkout -q -- src
