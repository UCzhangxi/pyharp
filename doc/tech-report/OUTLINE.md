# pyharp technical report: outline v1

Source pin: chengcli/pyharp at f34506f9d14ee7b1f2e1222775baa5093ae6967f.

| ch | title | covers | first executable check |
|---|---|---|---|
| 1 | Overview and quick start | pipeline opacity -> optical properties -> solver -> fluxes/heating; where pyharp is called from (the Radiation API) | quick-start example runs and its printed fluxes match the chapter |
| 2 | The radiative-transfer problem and its approximations | plane-parallel RTE, thermal and direct-beam sources, boundary conditions, flux and heating-rate definitions, delta scaling (delta-M, delta-Eddington), the two-stream closure family (Meador-Weaver; Eddington, quadrature, hemispheric mean; Coakley-Chylek, Shettle-Weinman, King-Harshvardhan, Wiscombe-Grams) | closure coefficients from the general family reproduce each named closure exactly; conservation identities for the two-stream ODE |
| 3 | DISORT (pydisort) | discrete ordinates, Gauss quadrature, Legendre expansion, eigenproblem, particular solutions (beam, linear-in-tau Planck), scaled boundary-value system, delta-M, Nakajima-Tanaka and Buras corrections; what pydisort wraps (bundled cdisort 2.1.3, batching, flags); delta-M+ and BRDF as context only | grey isothermal slab through RadiationBand+DISORT vs the analytic E3 solution (2e-4 at 32 streams); the cdisort test problems |
| 4 | Toon et al. 1989 two-stream, as implemented | SW: quadrature closure + delta-Eddington; LW: hemispheric mean + 5-point source-function integration, optional delta scaling; tridiagonal system; top_emission_flag 0/1/-1, btop_factor, hard_surface, zenith_correction, area_scale, the lambda*mu0=1 guard, level + midpoint output; Planck integrals (bbflux) | SW vs an independent high-precision solve of the same two-stream ODE (648 cases, 1e-12; 1e-9 single thick layer); LW isothermal equilibrium F = pi B (1e-13) |
| 5 | Solver comparison and accuracy | numerical error vs two-stream approximation error, separated; converged DISORT as reference; analytic cases (Beer-Lambert, isothermal slab, energy closure); a (tau, omega, g, mu0) grid; tolerances tied to Toon 1989's reported errors; cost | DISORT convergence in streams first, then Toon vs converged DISORT on the grid (replaces today's 4-stream, 20 % gate) |
| 6 | Opacity sources | gas: line-by-line toolkit (HITRAN/HITEMP, MT_CKD), c-k tables (pyharp NetCDF layout of PICASO tables, HELIOS-K), multiband-ck, respq-table, wavetemp, fourcolumn, jit, CIA incl. legacy H2 tables; particles: Mie (monodisperse, HG moments from g), Fu ice, temperature-switch water cloud; Rayleigh (fixed ratios to H2); microwave absorbers (in the tree, not compiled) | Mie vs a 60-digit Lorenz-Mie reference and miepython over 5 indices, x 1e-4..100; Rayleigh vs Sneep & Ubachs 2005 |
| 7 | Optical-property assembly and spectral integration | extinction addition, scattering-weighted phase moments, optical-depth conversion, conservative-scattering regularization, spectral weights and units; weight (c-k) mode vs wavenumber-grid mode | manufactured mixtures for extinction and moments; spectral-density vs band-integrated consistency in both modes |
| 8 | Radiation API, configuration, coupling and the column model | YAML and Python API, spherical flux scaling, SSA regularization, boundary temperature handling (btemp), the RK3 column radiative time stepper (src/integrator), actinic flux as input to photochemistry | config round trip: every YAML key reaches the solver option it names; RK3 stepper vs an analytic radiative relaxation |
| 9 | GPU and batching | support matrix by solver x operation x pydisort version; batch vs per-column; f32 vs f64 | Toon batch = per-column loop (1e-14 f64), CPU vs CUDA (1e-12); DISORT CPU vs CUDA on pydisort 1.7.1 and 1.8.13 |
| 10 | Tests, CI, bindings and verification index | which tests exist and which CI runs; packaging (pydisort bound); bindings vs C++ options vs .pyi stubs; the index of every check in this report | full suite on {pydisort 1.7.1, latest} exits 0 with no abort; options/bindings/stubs diff = 0 missing |
| App | notation, derivations, test index, glossary, topic index, task map | generated report reference material | generators run in CI |

## Chapter 1. Overview and quick start

Source files at the pin:

- [src/radiation/radiation.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/radiation/radiation.cpp)
- [src/radiation/radiation_band.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/radiation/radiation_band.cpp)

Existing tests at the pin (coverage starting points; the proposed first check is not claimed complete):

- [tests/test_radiation.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_radiation.cpp)

## Chapter 2. The radiative-transfer problem and its approximations

Source files at the pin:

- [src/rtsolver/toon_mckay89_shortwave_impl.h](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/rtsolver/toon_mckay89_shortwave_impl.h)
- [src/rtsolver/toon_mckay89_longwave_impl.h](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/rtsolver/toon_mckay89_longwave_impl.h)

Existing tests at the pin (coverage starting points; the proposed first check is not claimed complete):

- [tests/test_toon.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_toon.cpp)
- [tests/test_bbflux.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_bbflux.cpp)

## Chapter 3. DISORT (pydisort)

Source files at the pin:

- [src/radiation/disort_config.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/radiation/disort_config.cpp)
- [src/radiation/radiation_band.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/radiation/radiation_band.cpp)

Existing tests at the pin (coverage starting points; the proposed first check is not claimed complete):

- [tests/test_radiation.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_radiation.cpp)
- [tests/test_toon.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_toon.cpp)

## Chapter 4. Toon et al. 1989 two-stream, as implemented

Source files at the pin:

- [src/rtsolver/toon_mckay89.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/rtsolver/toon_mckay89.cpp)
- [src/rtsolver/toon_mckay89_shortwave_impl.h](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/rtsolver/toon_mckay89_shortwave_impl.h)
- [src/rtsolver/toon_mckay89_longwave_impl.h](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/rtsolver/toon_mckay89_longwave_impl.h)
- [src/radiation/bbflux.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/radiation/bbflux.cpp)

Existing tests at the pin (coverage starting points; the proposed first check is not claimed complete):

- [tests/test_toon.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_toon.cpp)
- [tests/test_toon.py](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_toon.py)
- [tests/test_bbflux.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_bbflux.cpp)
- [tests/test_tridiag.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_tridiag.cpp)

## Chapter 5. Solver comparison and accuracy

Source files at the pin:

- [src/rtsolver/toon_mckay89.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/rtsolver/toon_mckay89.cpp)
- [src/radiation/radiation_band.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/radiation/radiation_band.cpp)

Existing tests at the pin (coverage starting points; the proposed first check is not claimed complete):

- [tests/test_toon.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_toon.cpp)
- [tests/test_toon.py](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_toon.py)

## Chapter 6. Opacity sources

Source files at the pin:

- [src/opacity/opacity_options.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/opacity/opacity_options.cpp)
- [src/opacity/picaso_ck.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/opacity/picaso_ck.cpp)
- [src/opacity/helios.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/opacity/helios.cpp)
- [src/opacity/rayleigh.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/opacity/rayleigh.cpp)
- [src/opacity/water_liquid_mie.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/opacity/water_liquid_mie.cpp)

Existing tests at the pin (coverage starting points; the proposed first check is not claimed complete):

- [tests/test_rayleigh.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_rayleigh.cpp)
- [tests/test_water_liquid_mie.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_water_liquid_mie.cpp)
- [tests/test_helios_ck_read.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_helios_ck_read.cpp)
- [tests/spectra/test_spectrum.py](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/spectra/test_spectrum.py)

## Chapter 7. Optical-property assembly and spectral integration

Source files at the pin:

- [src/radiation/radiation_band.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/radiation/radiation_band.cpp)
- [src/opacity/scattering_functions.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/opacity/scattering_functions.cpp)
- [src/math/trapezoid.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/math/trapezoid.cpp)

Existing tests at the pin (coverage starting points; the proposed first check is not claimed complete):

- [tests/test_radiation.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_radiation.cpp)
- [tests/test_scattering_functions.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_scattering_functions.cpp)
- [tests/test_trapez.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_trapez.cpp)

## Chapter 8. Radiation API, configuration, coupling and the column model

Source files at the pin:

- [src/radiation/radiation.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/radiation/radiation.cpp)
- [src/radiation/radiation.hpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/radiation/radiation.hpp)
- [src/integrator/radiation_model.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/integrator/radiation_model.cpp)
- [src/integrator/integrator.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/integrator/integrator.cpp)
- [src/utils/parse_yaml_input.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/utils/parse_yaml_input.cpp)

Existing tests at the pin (coverage starting points; the proposed first check is not claimed complete):

- [tests/test_radiation.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_radiation.cpp)
- [tests/test_yaml_input.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_yaml_input.cpp)
- [tests/test_read_yaml.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_read_yaml.cpp)

## Chapter 9. GPU and batching

Source files at the pin:

- [src/rtsolver/rtsolver_dispatch.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/rtsolver/rtsolver_dispatch.cpp)
- [src/rtsolver/rtsolver_dispatch.cu](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/rtsolver/rtsolver_dispatch.cu)
- [src/opacity/water_liquid_mie_dispatch.cu](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/src/opacity/water_liquid_mie_dispatch.cu)

Existing tests at the pin (coverage starting points; the proposed first check is not claimed complete):

- [tests/test_toon.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_toon.cpp)
- [tests/device_testing.hpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/device_testing.hpp)
- [tests/test_water_liquid_mie.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_water_liquid_mie.cpp)

## Chapter 10. Tests, CI, bindings and verification index

Source files at the pin:

- [CMakeLists.txt](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/CMakeLists.txt)
- [tests/CMakeLists.txt](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/CMakeLists.txt)
- [setup.py](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/setup.py)
- [.github/workflows/ci.yml](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/.github/workflows/ci.yml)

Existing tests at the pin (coverage starting points; the proposed first check is not claimed complete):

- [tests/test_opacity_options.py](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_opacity_options.py)
- [tests/test_toon.py](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_toon.py)
- [tests/test_radiation.cpp](https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f/tests/test_radiation.cpp)
