#!/bin/bash
# Source-break runs for check [C2] of check_ch01_quickstart.py (the mixing rule of RadiationBandImpl::forward).
# usage: ch01_breaks.sh ENV WORK [CHECK]   (ENV made by derivation-checks/ch04/setup_env.sh; WORK a scratch directory;
#        CHECK another copy of check_ch01_quickstart.py, laid out as derivation-checks/ next to its book/, to compare)
# WORK/pyharp is a git worktree of ENV/pyharp at its commit and WORK/venv a copy of ENV/venv; neither ENV is changed.
# The venv copy carries a completion marker and the compilers are those of ENV's own build, as in ch02_clamp_breaks.sh.
# Each break edits src/radiation/radiation_band.cpp, rebuilds incrementally and reinstalls pyharp into WORK/venv, then
# runs the check against that build and compares the claims that FAIL with the expected set (OK, MISMATCH, CRASH or
# BUILD FAILED). The breaks:
#   M1  plain mean: the band albedo is the unweighted mean of the opacities' albedos; the phase moments keep their
#       weights, so only omega changes (the mutant the review of the chapter found green);
#   M2  complement: the band albedo written 1 - (weighted mean); for the quick start's gas and haze this equals the
#       mean with the two extinctions exchanged, and again only omega changes.
# K0 rebuilds the unchanged source last, so WORK ends with the build of the pin; the md5 of the restored source file
# is printed after it. The script exits with the number of runs that are not OK.
set -u
D=$(cd "$(dirname "$0")" && pwd)
E=$(cd "$1" && pwd); mkdir -p "$2"; W=$(cd "$2" && pwd)
S="$W/pyharp"; PY="$W/venv/bin/python"
SHA=$(git -C "$E/pyharp" rev-parse HEAD)
CK=$(cd "$(dirname "${3:-$D/check_ch01_quickstart.py}")" && pwd)/$(basename "${3:-check_ch01_quickstart.py}")
RB=src/radiation/radiation_band.cpp

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
if [ -f "$S/build/CMakeCache.txt" ] && ! grep -qxF -e "CMAKE_CXX_COMPILER:FILEPATH=$CXX" -e "CMAKE_CXX_COMPILER:STRING=$CXX" "$S/build/CMakeCache.txt"; then
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
  git -C "$S" checkout -q -- src
  while [ $# -gt 0 ]; do
    cp "$S/$1" "$W/orig"; sed -i "$2" "$S/$1"
    if cmp -s "$W/orig" "$S/$1"; then echo "[$id] ERROR break did not apply to $1: $what"; bad=$((bad + 1)); return; fi
    shift 2
  done
  if ! build; then echo "[$id] $what: BUILD FAILED (see build.log in WORK)"; bad=$((bad + 1)); return; fi
  T=$(mktemp -d)
  out=$(cd "$T" && "$PY" -I "$CK" 2>&1); rc=$?
  fails=$(echo "$out" | grep -o '^\[C[0-9]*\] FAIL' | sed 's/ FAIL//' | tr '\n' ' ' | sed 's/ $//')
  c2=$(echo "$out" | grep -o '^\[C2\] [A-Z]* shortwave prop (dtau, omega, g) per layer [^;]*')
  if ! echo "$out" | grep -q 'claims pass$'; then verdict=CRASH
  elif [ "$fails" = "$want" ] && { [ -n "$want" ] || [ "$rc" = 0 ]; }; then verdict=OK
  else verdict=MISMATCH; fi
  [ "$verdict" = OK ] || bad=$((bad + 1))
  echo "[$id] $what: exit $rc, failing: ${fails:-none}; expected: ${want:-none}; $verdict; ${c2#\[C2\] }"
  rm -rf "$T"
}
run M1 "plain mean of the albedos (the moments still weighted)" '[C1] [C2]' \
  "$RB" 's|^\( *\)prop.zero_();$|\1prop.zero_(); auto plain_ssa = torch::zeros_like(prop.select(-1, disort::ISS));|' \
  "$RB" 's|^\( *\)kdata.select(-1, disort::ISS) \* kdata.select(-1, disort::IEX);$|\1kdata.select(-1, disort::ISS) * kdata.select(-1, disort::IEX); plain_ssa += kdata.select(-1, disort::ISS);|' \
  "$RB" 's|scattering.copy_(divide_where_positive(scattering, extinction));|scattering.copy_(plain_ssa / static_cast<double>(opacities.size()));|'
run M2 "complement of the weighted mean (the two extinctions exchanged, for two opacities)" '[C1] [C2]' \
  "$RB" 's|scattering.copy_(divide_where_positive(scattering, extinction));|scattering.copy_(1.0 - divide_where_positive(scattering, extinction));|'
run K0 "control: source unchanged" ''
git -C "$S" checkout -q -- src
echo "restored: $RB md5 $(md5sum < "$S/$RB" | cut -d' ' -f1), git diff of src: $(git -C "$S" diff --stat -- src | wc -l) lines"
echo "ch01_breaks: $bad run(s) not as expected"
exit $bad
