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
- Python 3.11.13, torch 2.10.0+cu128 (run on CPU), numpy 2.4.6, mpmath 1.3.0.

Commands (from `doc/tech-report`):

```sh
python3 derivation-checks/ch04/toon_pyharp_check.py > derivation-checks/ch04/toon_pyharp_check.pydisort-1.7.1.out
python3 derivation-checks/ch04/toon_pyharp_check.py --data src/pyharp_report/ch04/data/shortwave_thick_layer.csv
```

The second command also writes the data file read by the figure `fig-ch04-shortwave-thick-layer`. Exit status is the
number of failed core checks `[C1]`-`[C6]`; candidate checks `[K1]`-`[K6]` print `XFAIL` when the candidate defect is
reproduced and never change the exit status. All candidates are CANDIDATE until a second independent run agrees;
they are named by content, not by register number.
