#!/bin/bash
# ch06: build, from public pins only, the environment the ch06 checks were run in.
#
# usage: ch06_setup.sh ROOT PYDISORT_VERSION [cpu|cuda]
#   ROOT              an empty directory for the build (venv, wheels, pyharp source tree)
#   PYDISORT_VERSION  1.7.1 (the report's code pin) or 1.8.13 (comparison)
#   cpu|cuda          build pyharp without (default; the recorded runs) or with its CUDA kernels; every ch06 check
#                     runs on the CPU
# Result: ROOT/venv-PYDISORT_VERSION/ (Python environment, with env.sh to source) and ROOT/pyharp-PYDISORT_VERSION/
# (source tree and build).
#
# System prerequisites (not installed here): Linux x86_64; Python 3.11 (the pydisort wheel hashes below are for
# cp311); git; a C/C++ compiler (the recorded runs: gcc 11.5.0); CMake >= 3.20 (installed into the venv below);
# NetCDF C library and headers (nc-config; the PICASO table of the ch06 checks is read through it); for cuda, the
# CUDA toolkit with nvcc on PATH.
#
# Pins: pyharp chengcli/pyharp f34506f9d14ee7b1f2e1222775baa5093ae6967f (v2.7.8); torch 2.10.0+cu126 from the
# PyTorch index; pydisort wheels from PyPI, checked against the sha256 values below:
#   1.7.1   tag commit 8af15242a265a60ea6fb51c29d48e6688a63ab67, wheel sha256 4e613790...
#   1.8.13  tag commit 74f8d7e995545a686b04d503b6f81135af48d87c, wheel sha256 f9470a73...
#
# With `cuda` and an nvcc older than 12.8 the script applies one patch to pyharp's build, and nowhere else:
# pyharp's CMakeLists.txt adds the CUDA architecture 120 for every CUDA toolkit >= 12.0, but nvcc accepts it only
# from 12.8 ("Unsupported gpu architecture 'compute_120'"); ch06_setup/cuda-arch-sm120.patch moves that condition
# to >= 12.8. It changes the list of CUDA architectures only, no source file. The default `cpu` build needs no patch.
set -euo pipefail
ROOT=$1; PV=$2; MODE=${3:-cpu}
HERE=$(cd "$(dirname "$0")" && pwd)
PYHARP_PIN=f34506f9d14ee7b1f2e1222775baa5093ae6967f
declare -A WHEEL_SHA256=(
  [1.7.1]=4e61379008c1769b7ec2c61e08b2d9441eb4385db08e08f47c69abef79d77843
  [1.8.13]=f9470a736baecac5fbb4660abc57fd0ac45963cca46614d242e5f04d78bc1aa6
)
PY=${PYTHON:-python3.11}
NAME=$PV
mkdir -p "$ROOT"; ROOT=$(cd "$ROOT" && pwd)
V=$ROOT/venv-$NAME; S=$ROOT/pyharp-$NAME; WH=$ROOT/wheels
mkdir -p "$WH"

# 1. Python environment. A filesystem without symlinks (exFAT, some network mounts) cannot hold the lib64 link
#    the venv module makes; then make the venv without it.
"$PY" -m venv --copies "$V" 2>/dev/null || "$PY" -c "
import os, sys, venv
os.symlink = lambda *a, **k: None
venv.EnvBuilder(with_pip=True, symlinks=False).create(sys.argv[1])" "$V"
VP=$V/bin/python
"$VP" -m pip -q install --upgrade pip
"$VP" -m pip -q install 'torch==2.10.0' --index-url https://download.pytorch.org/whl/cu126
"$VP" -m pip -q install numpy scipy mpmath pytest netCDF4 matplotlib xarray \
  'cmake>=3.20' ninja setuptools setuptools-scm wheel build

# 2. pydisort from PyPI, by hash
install_pydisort() {  # $1 version, $2 extra pip flags
  local v=$1; rm -rf "$WH/$v"; mkdir -p "$WH/$v"
  "$VP" -m pip -q download --no-deps "pydisort==$v" -d "$WH/$v"
  local w; w=$(ls "$WH/$v"/pydisort-"$v"-*.whl)
  echo "${WHEEL_SHA256[$v]}  $w" | sha256sum -c - >/dev/null || { echo "wheel hash mismatch: $w" >&2; exit 1; }
  "$VP" -m pip -q install --no-deps ${2:-} "$w"
}
install_pydisort "$PV"

# 3. pyharp at the pin
git clone -q https://github.com/chengcli/pyharp "$S"
git -C "$S" checkout -q "$PYHARP_PIN"
for l in harp python/harp; do   # git writes symlinks as plain files where the filesystem has none
  [ -L "$S/$l" ] || { rm -f "$S/$l"; cp -r "$S/src" "$S/$l"; }
done
if [ "$MODE" = cuda ]; then
  NVV=$(nvcc --version | sed -n 's/.*release \([0-9]*\.[0-9]*\).*/\1/p')
  if [ "$(printf '%s\n12.8\n' "$NVV" | sort -V | head -1)" != 12.8 ]; then
    git -C "$S" apply "$HERE/ch06_setup/cuda-arch-sm120.patch"
    echo "applied ch06_setup/cuda-arch-sm120.patch (nvcc $NVV < 12.8)"
  fi
fi

# 4. environment file: the NVIDIA libraries of the torch wheel must be found when pyharp's C++ test programs link
SP=$("$VP" -c 'import sysconfig; print(sysconfig.get_paths()["platlib"])')
cat > "$V/env.sh" <<EOF
export VIRTUAL_ENV=$V
export PATH=$V/bin:\$PATH
export LD_LIBRARY_PATH=\$(ls -d $V/lib*/python3.11/site-packages/nvidia/*/lib $SP/torch/lib 2>/dev/null | tr '\n' ':')\${LD_LIBRARY_PATH:-}
EOF

# 5. build and install pyharp against the installed pydisort
(
  source "$V/env.sh"
  cd "$S"
  cmake -B build -DCMAKE_BUILD_TYPE=Release -DNETCDF=ON -DBUILD_TESTS=ON -DBUILD_EXAMPLES=OFF \
    -DCUDA=$([ "$MODE" = cuda ] && echo ON || echo OFF) > "$ROOT/cmake-$NAME.log"
  cmake --build build --parallel "$(nproc)" > "$ROOT/build-$NAME.log"
  [ -L python/lib ] || { rm -rf python/lib; cp -r build/lib python/lib; }
  CPLUS_INCLUDE_PATH=$SP/pydisort pip -q install --no-build-isolation --no-deps .
)

source "$V/env.sh"
"$VP" -c 'import torch, pydisort, pyharp; print("ready:", "pyharp", pyharp.__version__, "pydisort",
          pydisort.__version__, "torch", torch.__version__)'
echo "activate with: source $V/env.sh"
