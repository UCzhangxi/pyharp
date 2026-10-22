#!/bin/bash
# Build the environment the chapter 10 checks ran in, from public sources only.
#
# usage: setup_env.sh <new directory> <pydisort version: 1.7.1 or 1.8.13>
#
# Creates <dir>/venv (Python 3.11) with requirements.lock, torch 2.10.0 and the pydisort wheel, both downloaded from
# PyPI and checked against the sha256 below; clones chengcli/pyharp at the pin of code_pin.yml into <dir>/pyharp,
# builds it with the options of pyharp's CI (CPU only, Release, NetCDF, tests) against that pydisort, installs it,
# and writes <dir>/ENV.txt.
# Needs on the host: python3.11 with venv, git, a C/C++ compiler (gcc 11.5 was used), the NetCDF C library and
# headers (4.8.1 was used), and network access to pypi.org, files.pythonhosted.org and github.com. The torch wheel
# is PyPI's default (CUDA 12.8) build; the checks run on CPU.
set -euo pipefail
DIR=$(mkdir -p "$1" && cd "$1" && pwd); PYD=$2
HERE=$(cd "$(dirname "$0")" && pwd)
PIN=f34506f9d14ee7b1f2e1222775baa5093ae6967f
case $PYD in
  1.7.1)  PYD_WHL=pydisort-1.7.1-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
          PYD_SHA=4e61379008c1769b7ec2c61e08b2d9441eb4385db08e08f47c69abef79d77843 ;;
  1.8.13) PYD_WHL=pydisort-1.8.13-cp311-cp311-manylinux_2_27_x86_64.whl
          PYD_SHA=f9470a736baecac5fbb4660abc57fd0ac45963cca46614d242e5f04d78bc1aa6 ;;
  *) echo "pydisort version must be 1.7.1 or 1.8.13" >&2; exit 2 ;;
esac
TORCH_WHL=torch-2.10.0-3-cp311-cp311-manylinux_2_28_x86_64.whl
TORCH_SHA=ac5bdcbb074384c66fa160c15b1ead77839e3fe7ed117d667249afce0acabfac

python3.11 -m venv "$DIR/venv"
PY="$DIR/venv/bin/python"
"$PY" -m pip install -q pip==22.3.1 setuptools==84.2.1 wheel==0.48.0
"$PY" -m pip install -q -r "$HERE/requirements.lock"

mkdir -p "$DIR/wheels"
"$PY" -m pip download -q --no-deps --only-binary=:all: -d "$DIR/wheels" torch==2.10.0 "pydisort==$PYD"
(cd "$DIR/wheels" && echo "$TORCH_SHA  $TORCH_WHL" | sha256sum -c - && echo "$PYD_SHA  $PYD_WHL" | sha256sum -c -)
"$PY" -m pip install -q --no-deps "$DIR/wheels/$TORCH_WHL" "$DIR/wheels/$PYD_WHL"

git clone -q https://github.com/chengcli/pyharp "$DIR/pyharp"
git -C "$DIR/pyharp" checkout -q "$PIN"
test "$(git -C "$DIR/pyharp" rev-parse HEAD)" = "$PIN"
(
  cd "$DIR/pyharp"
  export PATH="$DIR/venv/bin:$PATH"
  cmake -B build -DCMAKE_BUILD_TYPE=Release -DNETCDF=ON -DBUILD_TESTS=ON -DBUILD_EXAMPLES=OFF > "$DIR/cmake.log" 2>&1
  cmake --build build --config Release --parallel 4 >> "$DIR/cmake.log" 2>&1
  python -m pip install -q --no-build-isolation --no-deps . >> "$DIR/cmake.log" 2>&1
)
"$PY" - > "$DIR/ENV.txt" <<EOF
import platform, torch, pydisort, pyharp, numpy
print(f"pyharp {pyharp.__version__} built from chengcli/pyharp@$PIN; pydisort {pydisort.__version__} ($PYD_WHL sha256 $PYD_SHA)")
print(f"torch {torch.__version__} ($TORCH_WHL sha256 $TORCH_SHA); numpy {numpy.__version__}; Python {platform.python_version()}")
EOF
cat "$DIR/ENV.txt"
