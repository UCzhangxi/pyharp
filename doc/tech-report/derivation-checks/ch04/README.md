# Chapter 4 checks that run pyharp

`toon_pyharp_check.py` runs pyharp's Toon solver and band Planck function and compares them with independent
references (chapter 4, sections "Shortwave", "Longwave", "Band-integrated Planck function" and the zenith-correction
signpost). It imports pyharp, so by STYLE 7 it lives here rather than under `src/pyharp_report/ch04/checks/`, which
holds the numpy/sympy checks of the derivations.

Source pins:

- pyharp: chengcli/pyharp@f34506f9d14ee7b1f2e1222775baa5093ae6967f (the pin of `code_pin.yml`), built from source with
  the repository's CI options (`cmake -B build -DCMAKE_BUILD_TYPE=Release -DNETCDF=ON -DBUILD_TESTS=ON
  -DBUILD_EXAMPLES=OFF`, `cmake --build build --parallel 4`, `pip install --no-build-isolation --no-deps .`),
  CPU only (no CUDA compiler), reporting version 2.7.8.
- pydisort: two builds of pyharp, one against the pydisort 1.7.1 wheel (the version pyharp's CI installs; the
  source pin of `code_pin.yml` is zoeyzyhu/pydisort@8af15242a265a60ea6fb51c29d48e6688a63ab67, and that the wheel was
  built from it was not verified here) and one against the pydisort 1.8.13 wheel. The Toon solver does not call
  pydisort; the two outputs are identical after their version lines.
- Python 3.11.13, torch 2.10.0+cu128 (run on CPU), numpy 2.4.6, mpmath 1.3.0; the full package set is
  `requirements.lock`, and `setup_env.sh` checks the sha256 of the torch and pydisort wheels.

Reproduce everything (from `doc/tech-report`, on a Linux x86_64 host with python3.11, git, gcc and the NetCDF C
library; about 15 minutes per environment, most of it the pyharp build):

```sh
bash derivation-checks/ch04/setup_env.sh /tmp/env171 1.7.1    # venv from requirements.lock + checksummed wheels,
bash derivation-checks/ch04/setup_env.sh /tmp/env1813 1.8.13  # pyharp built from chengcli/pyharp at the pin
bash derivation-checks/ch04_run.sh /tmp/env171 /tmp/env1813
git status --short    # the committed outputs are regenerated in place; no change means a byte-identical rerun
```

`ch04_run.sh` writes `toon_pyharp_check.pydisort-<version>.out` and `defects_pyharp_check.pydisort-<version>.out`
for each environment, `mutations.out` (from `mutations.sh`: each review fix's check with one line mutated, and its
unmodified control, with exit codes), the data file
`src/pyharp_report/ch04/data/shortwave_thick_layer.csv` (read by the figure `fig-ch04-shortwave-thick-layer`), the
outputs of the three numpy/sympy checks under `src/pyharp_report/ch04/checks/`, and draws the chapter's figures with
`tools/render_figures.py --chapters ch04`. Inputs: none beyond the pinned sources and the PyPI wheels named in
`setup_env.sh`; every check builds its cases in code.

The exit status of `toon_pyharp_check.py` is the number of failed core checks `[C1]`-`[C6]`; candidate checks
`[K1]`-`[K6]` print `XFAIL` when the candidate defect is reproduced and never change the exit status. All candidates
are CANDIDATE until a second independent run agrees; they are named by content, not by register number.

`defects_pyharp_check.py` reproduces the pyharp defects P11 (Planck switch hole at v = 1.5) and P12 (infinite fluxes
at an exact longwave resonance in a thick layer, and large or percent-level errors near it and in thick layers) of
`DEFECTS.md` with fixed inputs. Its checks pass while the pinned
pyharp shows the defect and fail once pyharp is fixed, which is the signal to update the chapter's Limits.
