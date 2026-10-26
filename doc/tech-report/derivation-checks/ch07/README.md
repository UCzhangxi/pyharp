# Chapter 7 evidence and reproduction

The assembly and spectral directories preserve historical measurements. No native solver is invoked by the report
render or the record audit. `../ch07_evidence_check.py` checks hashes, recomputes the Decimal oracle against saved
native outputs, checks paired spectral ratios and proves the worked identities using exact rational arithmetic.
A PASS from this audit does not make the four failed Planck assertions pass.

Run from the report directory:

```sh
python derivation-checks/ch07_evidence_check.py
```

The captured output is `../ch07_evidence_check.out`. `provenance.json` distinguishes original hashes from the one
portability edit, records source pins and versions, and identifies the incomplete spectral binary provenance.
The historical commands were `python check_assembly.py` and `python check_a_planck.py` through
`python check_f_norm.py`, run in their respective directories. Inputs are generated in those scripts.

## Native assembly reproduction (optional; not run during manuscript preparation)

Build both pinned projects from `provenance.json` with the same Torch installation and C++11 ABI. Set
`PYHARP_WT` and `PYDISORT_WT` to clean pinned checkouts. Set `HARP_LIB`, `DISORT_LIB`, `FMT_INCLUDE`,
`TORCH_INCLUDE`, `TORCH_API_INCLUDE` and `TORCH_LIB` to the corresponding build/include directories.
The source layouts expose headers through `harp/` and `disort/` links at their checkout roots.

```sh
cd derivation-checks/ch07/assembly
c++ -std=c++17 -O1 -D_GLIBCXX_USE_CXX11_ABI=1 \
  -I"$PYHARP_WT" -I"$PYDISORT_WT" -I"$FMT_INCLUDE" \
  -I"$TORCH_INCLUDE" -I"$TORCH_API_INCLUDE" assembly_driver.cpp \
  -L"$HARP_LIB" -L"$DISORT_LIB" -L"$TORCH_LIB" \
  -Wl,-rpath,"$HARP_LIB" -Wl,-rpath,"$DISORT_LIB" -Wl,-rpath,"$TORCH_LIB" \
  -lharp_release -ldisort_release -ltorch -ltorch_cpu -lc10 -o assembly_driver
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python check_assembly.py
```

This regenerates the fixtures and outputs, so use a scratch copy. The native driver calls the production band
assembly with manufactured opacities and a capture solver. It does not measure physical flux accuracy.

## Native spectral reproduction (optional; not run during manuscript preparation)

Use a scratch copy of `spectral/`, Python 3.11.13, Torch 2.10.0+cpu, NumPy 2.4.6, SciPy 1.17.1 and NetCDF4 1.7.5.
Build pyharp from the recorded pin with NetCDF enabled and install pydisort 1.7.1. The historical dependency was a
PyPI wheel; rebuilding it from the source pin would be a new experiment, not proof of the historical binary.
The numerical-library versions beyond Python and Torch were recovered from the preserved environment later;
there is no immutable original dependency lock. Scripts generate JIT opacity files and YAML inputs locally.

```sh
python check_a_planck.py
python check_b_band.py
python check_c_accum.py
python check_d_bins.py
python check_e_narrow.py
python check_f_norm.py
```

These historical diagnostic scripts are retained verbatim. Some print FAIL without returning a failing exit code;
read the JSON assertions, not the shell status. The record audit explicitly verifies the four recorded failures.
`band_lab.py` sets `nphase = nstr` on the DISORT YAML path. This is part of the experimental setup.
No real opacity table, CUDA result, or inferred wheel commit is included.

## Draft notation dependency

The shared chapter 2 notation contribution is not present at the manuscript base. Local notation follows its supplied
proposal where applicable: phase moments use chi, the asymmetry parameter uses g, and the albedo cap uses delta-omega.
Absorption rank is locally eta so it cannot collide with angular g. Extinction k, scattering s, absorption a,
interval radiance and per-point interval flux are local symbols for editorial registration. The current shared
register reserves epsilon for relative error, so the proposed chapter 2 emissivity use still requires reconciliation.
No shared notation definition is changed by this contribution.
