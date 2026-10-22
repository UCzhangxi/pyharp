# Chapter 10 checks

These checks read or run pyharp, so by STYLE 7 they live here rather than under `src/pyharp_report/ch10/checks/`.

| script | what it checks | output |
|---|---|---|
| `test_inventory.py <pyharp tree> [--csv f]` | test files, `ctest` registration, the CI job's `pytest` list and matrix | `test_inventory.out` |
| `run_suite.sh <pyharp tree> <scratch>` | every test file: `ctest` with and without GPUs, the unregistered C++ files built out of tree (`extra_tests/CMakeLists.txt`), all Python files, `tests/test_rayleigh.py` three times | `run_suite.<pairing>.out` |
| `abi_matrix.py [--csv f]` | the pydisort build/run matrix from the four `run_suite` outputs | `abi_matrix.out` |
| `bindings_diff.py <pyharp tree> [--csv f]` | C++ options vs Python bindings vs `.pyi` stubs | `bindings_diff.<pydisort>.out` |

Source pins and builds:

- pyharp: chengcli/pyharp@f34506f9d14ee7b1f2e1222775baa5093ae6967f (the pin of `code_pin.yml`), built from source with
  the repository's CI options (`cmake -B build -DCMAKE_BUILD_TYPE=Release -DNETCDF=ON -DBUILD_TESTS=ON
  -DBUILD_EXAMPLES=OFF`, `cmake --build build --parallel 4`, `pip install --no-build-isolation --no-deps .`), CPU
  only (no CUDA compiler), reporting version 2.7.8. Two builds: one against the pydisort 1.7.1 wheel (what CI
  installs; the pydisort pin of `code_pin.yml` is zoeyzyhu/pydisort@8af15242a265a60ea6fb51c29d48e6688a63ab67, and
  that the wheel was built from it was not verified), one against the pydisort 1.8.13 wheel (what
  `pydisort>=1.7.1` resolves to).
- The mixed pairings swap the installed wheel after the build with `pip install --no-deps`:
  `run_suite.built-1.7.1.run-1.8.13.out` and `run_suite.built-1.8.13.run-1.7.1.out`.
- Python 3.11.13, torch 2.10.0+cu128 (PyPI; the pydisort 1.8.13 wheel needs `libtorch_cuda.so`), numpy 2.4.6,
  pytest 9.1.1; a 6-core CPU with two GPUs visible to torch.

`run_suite.sh` writes paths as `<src>` and `<scratch>` and drops timings, so its output can be committed.
Candidate defects found by these checks are CANDIDATE until a second independent run agrees, and are named by
content, not by register number.
