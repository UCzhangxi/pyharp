#!/bin/bash
# Build and run the RadiationModel probe (model_probe.cpp) against an environment made by ../setup_env.sh.
# usage: run.sh <environment> <scratch dir>     prints the [M1] and [M2] lines
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd); ENV=$(cd "$1" && pwd); S=$(mkdir -p "$2" && cd "$2" && pwd)
export PATH="$ENV/venv/bin:$PATH"
SITE=$(python -c "import pydisort, os; print(os.path.dirname(pydisort.__file__))")
TP=$(python -c "import torch.utils; print(torch.utils.cmake_prefix_path)")
cmake -S "$HERE" -B "$S/build" -DCMAKE_PREFIX_PATH="$TP" -DPYHARP_SRC="$ENV/pyharp" -DPYHARP_BUILD="$ENV/pyharp/build" \
  -DDISORT_INC="$SITE" > "$S/cmake.txt" 2>&1
cmake --build "$S/build" > "$S/build.txt" 2>&1
# the opacity: the jit module of ../invariants.py (extinction, albedo, HG moments from the atmosphere dictionary)
(cd "$S" && python -I -c "
import sys, pyharp; sys.argv = ['x']
import importlib.util as u
s = u.spec_from_file_location('inv', '$HERE/../invariants.py'); m = u.module_from_spec(s); s.loader.exec_module(m)
pyharp.compile(m.Optics(4), 'optics.pt')")
cat > "$S/model.yaml" <<YAML
species:
  - name: dummy
    composition: {H: 1}
geometry:
  cells:
    nx1: 20
opacities:
  optics:
    type: jit
    data: [optics.pt]
    jit_kwargs: [ext, ssa, gg]
    nmom: 4
bands:
  - name: SW
    range: [500., 600.]
    opacities: [optics]
    solver: toon
    integration: weight
    nwave: 3
YAML
(cd "$S" && LD_LIBRARY_PATH="$ENV/pyharp/build/lib:$SITE/lib:$(python -c 'import torch, os; print(os.path.dirname(torch.__file__))')/lib" \
  CUDA_VISIBLE_DEVICES= ./build/model_probe model.yaml)
