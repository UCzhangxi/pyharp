#!/bin/bash
# Source-break runs for check_ch02_clamp_pyharp.py: break the albedo clamp in a scratch build of pyharp and run the check.
# usage: ch02_clamp_breaks.sh ENV WORK [TEXT_CHECK]   (ENV made by derivation-checks/ch04/setup_env.sh; WORK a scratch
#        directory; TEXT_CHECK another version of check_ch02_toon_coefficients.py whose [C24] is reported, to compare)
# WORK/pyharp is a git worktree of ENV/pyharp at its commit and WORK/venv a copy of ENV/venv; neither ENV is changed.
#   * The copy is made into WORK/venv.partial and renamed when complete, with a marker file; a WORK/venv without the
#     marker (an interrupted copy) or one that cannot import torch and pyharp is removed and copied again.
#   * The compilers are pinned: the C and C++ compilers recorded in ENV's own build (ENV/pyharp/build/CMakeCache.txt)
#     are passed to CMake and to pip, whatever is first on PATH; a WORK build configured with other compilers is
#     configured afresh. Their version is printed.
# Each break edits one line, rebuilds incrementally and reinstalls pyharp into WORK/venv, then runs
# check_ch02_clamp_pyharp.py, and check [C24] of check_ch02_toon_coefficients.py (the text match), against WORK/pyharp.
# The claims that FAIL are compared with the expected set: OK when equal, MISMATCH otherwise, CRASH or BUILD FAILED
# when no result is printed. M38 (a margin of 1e-10, which [C1] must catch) and K0 (the unchanged source) are the
# controls. The script exits with the number of runs that are not OK. ONLY="M41 K0" restricts the runs.
# Slow: each rebuild and reinstall takes minutes; a first build in a new WORK about fifteen.
set -u
D=$(cd "$(dirname "$0")" && pwd)
E=$(cd "$1" && pwd); mkdir -p "$2"; W=$(cd "$2" && pwd)
S="$W/pyharp"; PY="$W/venv/bin/python"
SHA=$(git -C "$E/pyharp" rev-parse HEAD)
TXT=$(cd "$(dirname "${3:-$D/check_ch02_toon_coefficients.py}")" && pwd)/$(basename "${3:-check_ch02_toon_coefficients.py}")
RB=src/radiation/radiation_band.cpp; SWK=src/rtsolver/toon_mckay89_shortwave_impl.h; LWK=src/rtsolver/toon_mckay89_longwave_impl.h

# compilers of ENV's build
CC=$(sed -n 's/^CMAKE_C_COMPILER:FILEPATH=//p' "$E/pyharp/build/CMakeCache.txt")
CXX=$(sed -n 's/^CMAKE_CXX_COMPILER:FILEPATH=//p' "$E/pyharp/build/CMakeCache.txt")
if [ ! -x "$CC" ] || [ ! -x "$CXX" ]; then echo "ERROR compilers of $E not found ('$CC', '$CXX')"; exit 99; fi
export CC CXX
echo "compilers: $CC, $CXX ($("$CXX" --version | head -1))"

# worktree at ENV's commit
if [ -d "$S" ] && [ "$(git -C "$S" rev-parse HEAD 2>/dev/null)" != "$SHA" ]; then
  git -C "$S" checkout -q --detach "$SHA" || { echo "ERROR worktree $S is not at $SHA"; exit 99; }
fi
[ -d "$S" ] || git -C "$E/pyharp" worktree add -q --detach "$S" "$SHA"
git -C "$S" checkout -q -- src

# venv: a complete copy of ENV's
MARK="copied from $E/venv"
if [ -d "$W/venv" ] && { [ "$(cat "$W/venv/.copy-complete" 2>/dev/null)" != "$MARK" ] ||
                         ! "$PY" -c 'import torch, pyharp' > /dev/null 2>&1; }; then
  echo "venv: the copy in WORK is incomplete or broken; copying it again"
  rm -rf "$W/venv"
fi
if [ ! -d "$W/venv" ]; then
  rm -rf "$W/venv.partial"
  cp -a "$E/venv" "$W/venv.partial" && echo "$MARK" > "$W/venv.partial/.copy-complete" && mv "$W/venv.partial" "$W/venv" ||
    { echo "ERROR copying $E/venv"; exit 99; }
fi

# a build configured with other compilers is configured again
if [ -f "$S/build/CMakeCache.txt" ] && ! grep -qx "CMAKE_CXX_COMPILER:FILEPATH=$CXX" "$S/build/CMakeCache.txt"; then
  echo "build: the build in WORK was configured with another compiler; configuring again"
  rm -rf "$S/build"
fi
export CUDA_VISIBLE_DEVICES= PYHARP_WT="$S"
build() {
  (cd "$S" && export PATH="$W/venv/bin:$PATH" &&
   { [ -d build ] || cmake -B build -DCMAKE_BUILD_TYPE=Release -DNETCDF=ON -DBUILD_TESTS=ON -DBUILD_EXAMPLES=OFF \
                       -DCMAKE_C_COMPILER="$CC" -DCMAKE_CXX_COMPILER="$CXX"; } &&
   cmake --build build --config Release --parallel 4 && python -m pip install -q --no-build-isolation --no-deps .) \
    > "$W/build.log" 2>&1
}
bad=0
run() {  # id, what, expected failing claims ('' for none), then pairs of (file, sed expression)
  id=$1; what=$2; want=$3; shift 3
  if [ -n "${ONLY:-}" ] && ! [[ " $ONLY " == *" $id "* ]]; then return; fi
  git -C "$S" checkout -q -- src
  while [ $# -gt 0 ]; do
    cp "$S/$1" "$W/orig"; sed -i "$2" "$S/$1"
    if cmp -s "$W/orig" "$S/$1"; then echo "[$id] ERROR break did not apply to $1: $what"; bad=$((bad + 1)); return; fi
    shift 2
  done
  if ! build; then echo "[$id] $what: BUILD FAILED (see build.log in WORK)"; bad=$((bad + 1)); return; fi
  T=$(mktemp -d)
  out=$(cd "$T" && "$PY" -I "$D/check_ch02_clamp_pyharp.py" --work "$T" 2>&1); rc=$?
  fails=$(echo "$out" | grep -o '^\[C[0-9]*\] FAIL' | sed 's/ FAIL//' | tr '\n' ' ' | sed 's/ $//')
  txt=$(cd "$T" && "$PY" -I "$TXT" 2>&1 | grep -o '^\[C24\] [A-Z]*')
  if ! echo "$out" | grep -q 'claims pass$'; then verdict=CRASH
  elif [ "$fails" = "$want" ] && { [ -n "$want" ] || [ "$rc" = 0 ]; }; then verdict=OK
  else verdict=MISMATCH; fi
  [ "$verdict" = OK ] || bad=$((bad + 1))
  echo "[$id] $what: check_ch02_clamp_pyharp exit $rc, failing: ${fails:-none}; expected: ${want:-none}; $verdict; text match $txt"
  rm -rf "$T"
}
run M39 "clamp line commented out" '[C1] [C2]' \
  "$RB" 's|^\( *\)prop.select(-1, disort::ISS).clamp_max_(1.0 - ssa_margin);|\1// prop.select(-1, disort::ISS).clamp_max_(1.0 - ssa_margin);|'
run M40 "the clamp's guard if (nprop > 1) written if (false)" '[C1] [C2]' \
  "$RB" '/Conservative scattering is degenerate/,/clamp_max_/ s|if (nprop > 1) {|if (false) {|'
run M41 "cap inside the longwave kernel: w0[k] = fmin(w0[k], 1.0 - 1.0e-12) before alp[k]" '[C3]' \
  "$LWK" 's|^\( *\)alp\[k\] = sqrt((1.0 - w0\[k\]) / (1.0 - w0\[k\] \* hg\[k\]));|\1w0[k] = fmin(w0[k], 1.0 - 1.0e-12);\n\1alp[k] = sqrt((1.0 - w0[k]) / (1.0 - w0[k] * hg[k]));|'
run M42 "tighter cap inside the longwave kernel: w0[k] = fmin(w0[k], 1.0 - 1.0e-13) before alp[k]" '[C3]' \
  "$LWK" 's|^\( *\)alp\[k\] = sqrt((1.0 - w0\[k\]) / (1.0 - w0\[k\] \* hg\[k\]));|\1w0[k] = fmin(w0[k], 1.0 - 1.0e-13);\n\1alp[k] = sqrt((1.0 - w0[k]) / (1.0 - w0[k] * hg[k]));|'
run M38 "control break: double-precision margin 1e-12 written 1e-10" '[C1]' \
  "$RB" 's|torch::kFloat64 ? 1.0e-12 : 1.0e-6;|torch::kFloat64 ? 1.0e-10 : 1.0e-6;|'
run K0 "control: source unchanged" ''
git -C "$S" checkout -q -- src
echo "ch02_clamp_breaks: $bad run(s) not as expected"
exit $bad
