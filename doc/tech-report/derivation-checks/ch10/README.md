# Chapter 10 checks

These checks read or run pyharp, so by STYLE 7 they live here rather than under `src/pyharp_report/ch10/checks/`.

| script | what it checks | output |
|---|---|---|
| `test_inventory.py <pyharp tree> [--csv f]` | test files, `ctest` registration, the CI job's `pytest` list and matrix | `test_inventory.out` |
| `run_suite.sh <pyharp tree> <scratch>` | every test file: `ctest` with and without GPUs, the unregistered C++ files built out of tree (`extra_tests/CMakeLists.txt`), all Python files, `tests/test_rayleigh.py` three times | `run_suite.<pairing>.out` |
| `abi_matrix.py [--csv f]` | the pydisort build/run matrix from the four `run_suite` outputs | `abi_matrix.out` |
| `bindings_diff.py <pyharp tree> [--csv f]` | C++ options vs Python bindings vs `.pyi` stubs | `bindings_diff.<pydisort>.out` |
| `header_diff.sh <env 1.7.1> <env 1.8.13>` | `DisortImpl` data members that differ between the two wheels; newest pydisort on PyPI | `header_diff.out` |
| `flaky_rerun.sh <pyharp tree> <N>` | the one intermittent spectra test, N reruns | `flaky_rerun.out` |
| `setup_env.sh <dir> <pydisort version>` | builds an environment from `requirements.lock`, checksummed wheels and pyharp at the pin | `<dir>/ENV.txt` |

Source pins and builds:

- pyharp: chengcli/pyharp@f34506f9d14ee7b1f2e1222775baa5093ae6967f (the pin of `code_pin.yml`), built from source with
  the repository's CI options (`cmake -B build -DCMAKE_BUILD_TYPE=Release -DNETCDF=ON -DBUILD_TESTS=ON
  -DBUILD_EXAMPLES=OFF`, `cmake --build build --parallel 4`, `pip install --no-build-isolation --no-deps .`), CPU
  only (no CUDA compiler), reporting version 2.7.8. Two builds: one against the pydisort 1.7.1 wheel (what CI
  installs; the pydisort pin of `code_pin.yml` is zoeyzyhu/pydisort@8af15242a265a60ea6fb51c29d48e6688a63ab67, and
  that the wheel was built from it was not verified), one against the pydisort 1.8.13 wheel (what
  `pydisort>=1.7.1` resolves to).
- The mixed pairings swap the installed wheel after the build with `pip install --no-deps` (done by `ch10_run.sh`):
  `run_suite.built-1.7.1.run-1.8.13.out` and `run_suite.built-1.8.13.run-1.7.1.out`.
- Python 3.11.13, torch 2.10.0+cu128 (PyPI; the pydisort 1.8.13 wheel needs `libtorch_cuda.so`), numpy 2.4.6,
  pytest 9.1.1, cmake 4.4.4 from pip (the full set is `requirements.lock`); a 6-core x86_64 CPU with two GPUs
  visible to torch.

Reproduce everything (from `doc/tech-report`, on a Linux x86_64 host with python3.11, git, gcc and the NetCDF C
library; about 15 minutes per environment for the build and 15 minutes for the run):

```sh
bash derivation-checks/ch10/setup_env.sh /tmp/env171 1.7.1
bash derivation-checks/ch10/setup_env.sh /tmp/env1813 1.8.13
bash derivation-checks/ch10_run.sh /tmp/env171 /tmp/env1813 /tmp/ch10-scratch
git status --short    # the committed outputs are regenerated in place
```

`run_suite.sh` writes paths as `<src>` and `<scratch>`, drops timings and deselects the one intermittent test, so its
output is deterministic on a given host. Two outputs depend on the host or on chance and are not expected to be
byte-identical elsewhere: `[S1]` (ctest with the GPUs visible: the CUDA cases run only where torch sees a GPU; the
committed run saw two NVIDIA Quadro RTX 4000) and `flaky_rerun.out` (a count of random failures).
`header_diff.out` line `[H2]` names the newest pydisort on PyPI at run time.
Candidate defects found by these checks are CANDIDATE until a second independent run agrees, and are named by
content, not by register number.
