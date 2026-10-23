#!/usr/bin/env python3
"""Chapter 10 check: the inventory of every positivity floor, clamp, max/min bound, epsilon and tiny-value guard
in the pyharp source that the build compiles, and in the pydisort wrapper it calls.

usage: python3 floor_inventory.py <pyharp tree at the pin> [<pydisort tree at its pin>] [--csv <file>]

Scans every line of the compiled C++ (`src/*`, `src/{math,utils,opacity,radiation,rtsolver,integrator}/*`, the
directories `src/CMakeLists.txt` globs; `src/opacity/mwr/` is not compiled), the bindings (`python/csrc/`) and the
Python package (`python/*.py`, `python/spectra/`) for the guard patterns below, outside comments. Each hit must
match one entry of INVENTORY, which names its kind and the check that measures what it changes; a hit that
matches no entry is printed as UNCLASSIFIED and fails the check, so a new floor cannot enter the tree unlisted.
Prints `[F1]` one line per guard (path:line at the tree's HEAD sha), `[F2]` the counts per kind, `[F3]` the
pydisort wrapper, `[F4]` the vendored cdisort guards on the paths these checks exercise, `[F9]` the verdict.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PATTERN = re.compile(
    r"clamp|\bclip\b|fmax|fmin|std::max|std::min|torch::max|torch::min|\bmax\(|\bmin\(|maximum|minimum|epsilon|"
    r"DBL_EPS|FLT_EPS|DBL_MIN|\d\.?\d*[eE]-\d+|where_positive|[=!]= 0\.0\b|== static_cast<T>\(0\)|positivity|"
    r"Negative|torch::where\(|\?\s*[^:]*:\s*static_cast<T>\(0\)|< 35\.0|qext < out\.qsca")
GLOBS = ["src/*.cpp", "src/*.hpp", "src/*.h", "src/*.cuh"] + [
    f"src/{d}/*" for d in ("math", "utils", "opacity", "radiation", "rtsolver", "integrator")] + [
    "python/csrc/*.cpp", "python/*.py", "python/spectra/*.py"]

# kinds
FLOOR = "floor"        # replaces a zero or tiny value by a positive one
CLAMP = "clamp"        # bounds a value to an interval
SWITCH = "switch"      # a threshold that selects another formula
GUARD = "div-guard"    # avoids a division by zero by selecting another value
REFUSE = "refusal"     # stops with an error instead of changing the value
NOT = "not a floor"    # a constant, a unit factor, a size, a tolerance of a non-numerical test

# (path, needle in the line, kind, what it does, the check that measures its effect)
INVENTORY = [
    # --- Toon shortwave kernel
    ("src/rtsolver/toon_mckay89_shortwave_impl.h", "W_IN(i) > 1.0e-12", SWITCH,
     "omega <= 1e-12 in every layer (and A <= 1e-12) selects the beam-only formula", "invariants [T1]; V1"),
    ("src/rtsolver/toon_mckay89_shortwave_impl.h", "w_surf_in > 1.0e-12", SWITCH,
     "A > 1e-12 forces the general solver", "V2"),
    ("src/rtsolver/toon_mckay89_shortwave_impl.h", "g2 = 1.0e-10", FLOOR,
     "gamma_2 = 0 (omega = 0 in the general solver) replaced by 1e-10", "V3 (1e-300), V4 (none)"),
    ("src/rtsolver/toon_mckay89_shortwave_impl.h", "numeric_limits<T>::epsilon()", SWITCH,
     "lam mu0 within sqrt(eps) of 1 moves mu0 to 1 +- sqrt(eps)", "invariants [T4]; B13 (0)"),
    ("src/rtsolver/toon_mckay89_shortwave_impl.h", "fmin(lam * dtau[i], 35.0)", CLAMP,
     "layer exponential capped at exp(35)", "V5 (none)"),
    ("src/rtsolver/toon_mckay89_shortwave_impl.h", "1e-30 * fabs(xk[2 * n + 1])", FLOOR,
     "|xk2| below 1e-30 of xk[2n+1] set to 0", "V6 (none)"),
    ("src/rtsolver/toon_mckay89_shortwave_impl.h", "fmax(dir_k * dir_kp1, (T)0.0)", FLOOR,
     "midpoint beam sqrt(max(dir_k dir_k+1, 0))", "V7 (none)"),
    # --- Toon longwave kernel
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "x == static_cast<T>(0) ? static_cast<T>(1)", SWITCH,
     "expm1(x)/x at x = 0 replaced by its limit 1", "B9 (none)"),
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "exp(-fmin(a, b))", CLAMP,
     "resonant downward ratio uses the smaller exponent", "V15"),
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "dtau[k] <= 1.0e-6", SWITCH,
     "dtau <= 1e-6 takes the Planck function constant across the layer", "invariants [T3], [Z3]; B10 (0)"),
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "fmin(lam[k] * dtau[k], 35.0)", CLAMP,
     "layer exponential capped at exp(35)", "V11 (700)"),
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "1e-30 * fabs(xkk[2 * n + 1])", FLOOR,
     "|xk2| below 1e-30 of xkk[2n+1] set to 0", "V12 (none)"),
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "w0[n] <= 1e-4", SWITCH,
     "omega <= 1e-4 drops the scattering source of the intensity sweep", "invariants [T2]; V9 (0)"),
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "fmin(lam[n] * dtau[n], 35.0)", CLAMP,
     "layer exponential capped at exp(35)", "V11 (700)"),
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "lam[k] * dtau[k] < 35.0", SWITCH,
     "beyond the cap the ratios use the capped exponentials", "V11 (700)"),
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "0.5 * lam[k] * dtau[k] < 35.0", SWITCH,
     "same, half layer", "V11 (700)"),
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "fmin(0.5 * lam[k] * dtau[k], 35.0)", CLAMP,
     "midpoint exponential capped at exp(35)", "V11 (700)"),
    ("src/rtsolver/toon_mckay89_longwave_impl.h", "wsum != 0.0", GUARD,
     "surface reflection divides by the quadrature weight sum", "V13 (none)"),
    ("src/rtsolver/dtridgl_impl.h", "denom = 1e-12", FLOOR, "zero pivot replaced by 1e-12", "V16 (none)"),
    # --- band assembly
    ("src/radiation/radiation_band.cpp", "torch::Tensor divide_where_positive", GUARD,
     "albedo and moments divided only where the weight is > 0, else 0", "invariants [Z1]; B8 (plain division)"),
    ("src/radiation/radiation_band.cpp", "torch::where(positive", GUARD, "body of divide_where_positive",
     "B8"),
    ("src/radiation/radiation_band.cpp", "nmax_prop = std::max", NOT, "size of the property array", "-"),
    ("src/radiation/radiation_band.cpp", "divide_where_positive(moments", GUARD, "call", "B8"),
    ("src/radiation/radiation_band.cpp", "divide_where_positive(scattering", GUARD, "call", "B8"),
    ("src/radiation/radiation_band.cpp", "1.0e-12 : 1.0e-6", CLAMP,
     "single-scattering albedo margin, 1e-12 (double) or 1e-6 (float)", "invariants [E2]; B5 (none)"),
    ("src/radiation/radiation_band.cpp", "clamp_max_(1.0 - ssa_margin)", CLAMP,
     "omega clamped to 1 - margin before the solver", "invariants [E2], [P1]; B5 (none)"),
    ("src/radiation/radiation_band.cpp", "Negative values found in 'tempf'", REFUSE,
     "negative level temperature refused", "-"),
    ("src/radiation/radiation_band.cpp", "check_positivity(true)", REFUSE,
     "layer-to-level temperature must be >= 0, else error", "-"),
    # --- radiation utilities
    ("src/radiation/bbflux.cpp", "temp.min().item<double>() > 0.0", REFUSE, "T <= 0 refused", "-"),
    ("src/radiation/bbflux.cpp", "v[i] < VCUT", SWITCH,
     "band Planck integral: power series below VCUT, exponential series above (PLKAVG)", "invariants [E0]"),
    ("src/radiation/bbflux.cpp", "v[i] > VCUT", SWITCH, "same", "invariants [E0]"),
    ("src/radiation/bbflux.cpp", "smallv ==", SWITCH, "same, combination of the two ends", "invariants [E0]"),
    ("src/radiation/bbflux.cpp", "e-", NOT, "physical constant or unit factor", "-"),
    ("src/radiation/calc_dz_hypsometric.cpp", "check_positivity(false)", NOT, "positivity test off", "-"),
    ("src/radiation/get_direction_grids.hpp", "1.e-3", NOT, "tolerance for matching output directions", "-"),
    ("src/utils/layer2level.cpp", "check_positivity()", REFUSE, "negative interface value refused", "-"),
    ("src/utils/layer2level.cpp", "Negative values found", REFUSE, "message of the refusal", "-"),
    ("src/utils/layer2level.hpp", "check_positivity", NOT, "option declaration (default off)", "-"),
    ("src/math/interpolation.cpp", "diff == 0, torch::ones_like(diff)", GUARD,
     "zero node spacing (a one-node axis) divided by 1 instead", "not reached by these checks (distinct nodes)"),
    ("src/math/interpolation.cpp", "torch::clamp(search_idx - 1", CLAMP, "table index clamped to the table",
     "opacity_probe [Z6]; V27"),
    ("src/math/interpolation.cpp", "torch::clamp(out.index_low + 1", CLAMP, "table index clamped", "V27"),
    ("src/math/interpolation.cpp", "torch::clamp(out.weight_high, 0.0, 1.0)", CLAMP,
     "interpolation weight clamped: constant extrapolation outside the table", "opacity_probe [Z6]; V27"),
    ("src/integrator/radiation_model.cpp", "atm[\"temp\"].clamp_(20, 1000)", CLAMP,
     "atmospheric temperature clamped to [20, 1000] K after each step", "not measured: RadiationModel has no "
     "Python binding and no test at the pin"),
    ("src/integrator/radiation_model.cpp", "bc[\"btemp\"].clamp_(20, 1000)", CLAMP,
     "surface temperature clamped to [20, 1000] K after each step", "not measured (as above)"),
    ("src/integrator/radiation_model.hpp", "kappa) = 2.e-5", NOT, "default thermal diffusivity", "-"),
    # --- opacities
    ("src/opacity/helios.cpp", "clamp_(1.0e-99).log_()", FLOOR, "table zeros stored as 1e-99 before the log",
     "opacity_probe [Z5]"),
    ("src/opacity/picaso_ck.cpp", "clamp_min(1.e-300)", FLOOR, "table zeros stored as 1e-300 before the log",
     "opacity_probe [Z5]; B15"),
    ("src/opacity/respq_table.cpp", "clamp_min(1.e-300)", FLOOR, "table zeros stored as 1e-300 before the log",
     "opacity_probe [Z5]"),
    ("src/opacity/respq_table.cpp", "clamp_max(1. - 1.e-12)", CLAMP, "omega clamped to 1 - 1e-12",
     "redundant with the band clamp (B5)"),
    ("src/opacity/respq_table.cpp", "allclose(total, conc.sum(-1), 1.e-8, 1.e-12)", REFUSE,
     "composition not covered refused", "-"),
    ("src/opacity/respq_table.cpp", "allclose(fraction, reference, 1.e-6, 1.e-8)", REFUSE,
     "composition differs from the table refused", "-"),
    ("src/opacity/respq_table.cpp", "torch::tensor(1., torch::kFloat64), 1.e-8, 1.e-8)", REFUSE,
     "table normalization test", "-"),
    ("src/utils/netcdf_opacity_utils.hpp", "fill_value = 1.0e-300", FLOOR,
     "non-positive table entries stored as 1e-300 before the log", "opacity_probe [Z5]"),
    ("src/utils/netcdf_opacity_utils.hpp", "torch::where(positive_mask", FLOOR, "applies the fill value",
     "opacity_probe [Z5]"),
    ("src/utils/netcdf_opacity_utils.hpp", "1.0e-12 * scale", NOT, "tolerance of the out-of-range warning", "-"),
    ("src/utils/netcdf_opacity_utils.hpp", "std::max({std::abs(table_min)", NOT, "scale of that tolerance", "-"),
    ("src/utils/netcdf_opacity_utils.hpp", "query.min()", NOT, "range of the query (warning only)", "-"),
    ("src/utils/netcdf_opacity_utils.hpp", "query.max()", NOT, "range of the query (warning only)", "-"),
    ("src/utils/netcdf_opacity_utils.hpp", "will be clamped to the nearest table", NOT, "warning text", "-"),
    ("src/utils/netcdf_opacity_utils.hpp", "values * ", NOT, "unit conversion", "-"),
    ("src/opacity/molecule_cia.cpp", "_min = ", NOT, "table range bookkeeping", "-"),
    ("src/opacity/molecule_cia.cpp", "_max = ", NOT, "table range bookkeeping", "-"),
    ("src/opacity/molecule_line.cpp", "_min = ", NOT, "table range bookkeeping", "-"),
    ("src/opacity/molecule_line.cpp", "_max = ", NOT, "table range bookkeeping", "-"),
    ("src/opacity/multiband.cpp", "1.e-4 * constants::Avogadro", NOT, "unit conversion", "-"),
    ("src/opacity/picaso_ck.cpp", "1.e-4 * sigma", NOT, "unit conversion", "-"),
    ("src/opacity/rayleigh.cpp", "e-", NOT, "coefficients of the cross section, unit conversion", "-"),
    ("src/opacity/water_cloud_temperature.cpp", "torch::Tensor divide_where_positive", GUARD,
     "albedo and moments divided only where the weight is > 0", "opacity_probe [Z4]"),
    ("src/opacity/water_cloud_temperature.cpp", "torch::where(positive", GUARD, "body", "opacity_probe [Z4]"),
    ("src/opacity/water_cloud_temperature.cpp", "divide_where_positive(scattering", GUARD, "call",
     "opacity_probe [Z4]"),
    ("src/opacity/water_cloud_temperature.cpp", "divide_where_positive(weighted_moments", GUARD, "call",
     "opacity_probe [Z4]"),
    ("src/opacity/water_cloud_temperature.cpp", ".clamp(0.0, 1.0)", CLAMP,
     "liquid fraction of the condensate in [0, 1] (the 253.15-273.15 K ramp)", "V19 (none)"),
    ("src/opacity/water_ice_fu96_98.cpp", "wavelength.clamp(0.25, 100.0)", CLAMP,
     "lookup wavelength clamped to the support, then masked to 0 outside it", "V22 (none)"),
    ("src/opacity/water_ice_fu96_98.cpp", "torch::where(active, iwc", GUARD,
     "ice-free layers evaluated at IWC = 1 for a finite size (their extinction is 0)", "opacity_probe [Z4]"),
    ("src/opacity/water_ice_fu96_98.cpp", "clamp(kDiagnosedMinDge, kDiagnosedMaxDge)", CLAMP,
     "diagnosed ice size clamped to the table interval", "V23 (none)"),
    ("src/opacity/water_ice_fu96_98.cpp", "torch::where(active, diagnosed_dge", GUARD,
     "size of ice-free layers set to a safe value", "opacity_probe [Z4]"),
    ("src/opacity/water_ice_fu96_98.cpp", "torch::minimum(f96, g96)", CLAMP,
     "delta-function fraction f <= g (Fu96)", "V24 (none)"),
    ("src/opacity/water_ice_fu96_98.cpp", "torch::where(support_mask", CLAMP,
     "optical properties set to 0 outside 0.25-100 um", "opacity_probe [Z4] (dump)"),
    ("src/opacity/water_ice_fu96_98.cpp", ".clamp(0.0, 1.0), 0.0)", CLAMP, "omega in [0, 1]", "V20 (none)"),
    ("src/opacity/water_ice_fu96_98.cpp", ".clamp(-0.999999, 0.999999), 0.0)", CLAMP, "|g| <= 0.999999",
     "V21 (none)"),
    ("src/opacity/water_ice_fu96_98.cpp", "torch::where(fu96_mask", NOT, "selects the Fu96 or Fu98 fit", "-"),
    ("src/opacity/water_ice_fu96_98.cpp", "torch::where(", NOT, "selection between fits or masks", "-"),
    ("src/opacity/water_liquid_mie.cpp", "torch::clamp(upper, 0, grid.size(0) - 1)", CLAMP,
     "table index clamped", "opacity_probe [Z4] (dump)"),
    ("src/opacity/water_liquid_mie.cpp", "torch::clamp(upper - 1, 0, grid.size(0) - 1)", CLAMP,
     "table index clamped", "opacity_probe [Z4] (dump)"),
    ("src/opacity/water_liquid_mie.cpp", "std::max(1, static_cast<int>(max_x", NOT, "number of Mie terms", "-"),
    ("src/opacity/water_liquid_mie.cpp", "re_unique.max() / wavelength.min()", NOT, "largest size parameter", "-"),
    ("src/opacity/water_liquid_mie.cpp", "torch::where(", NOT, "selection", "-"),
    ("src/opacity/water_liquid_mie_impl.h", "DISPATCH_MACRO T clamp_value", CLAMP, "helper", "V25, V26"),
    ("src/opacity/water_liquid_mie_impl.h", "static_cast<T>(1.0e-6)", NOT,
     "convergence tolerance of the continued fraction (float)", "-"),
    ("src/opacity/water_liquid_mie_impl.h", "static_cast<T>(1.0e-12)", NOT,
     "convergence tolerance of the continued fraction (double)", "-"),
    ("src/opacity/water_liquid_mie_impl.h", "x < static_cast<T>(1.0e-3)", SWITCH,
     "size parameter < 1e-3 uses the Rayleigh limit", "opacity_probe [Z4] (dump)"),
    ("src/opacity/water_liquid_mie_impl.h", "? -static_cast<T>(4) * x * alpha.i", FLOOR,
     "Rayleigh-limit absorption floored at 0", "opacity_probe [Z4] (dump)"),
    ("src/opacity/water_liquid_mie_impl.h", "if (out.qext < out.qsca) out.qext = out.qsca", FLOOR,
     "absorption efficiency floored at 0 (qext >= qsca)", "V26 (none)"),
    ("src/opacity/water_liquid_mie_impl.h", "out.g = out.qsca > static_cast<T>(0)", GUARD,
     "g = 0 where qsca = 0", "opacity_probe [Z4]"),
    ("src/opacity/water_liquid_mie_impl.h", "? clamp_value(static_cast<T>(4) * g_sum", CLAMP,
     "|g| <= 0.999999", "V25 (none)"),
    ("src/opacity/water_liquid_mie_impl.h", "if (molar_conc == static_cast<T>(0)) return {0, 0, 0}", GUARD,
     "zero concentration returns zero properties", "opacity_probe [Z4]"),
    ("src/opacity/water_liquid_mie_impl.h", "radius_um * static_cast<T>(1.0e-6)", NOT, "unit conversion", "-"),
    ("src/opacity/water_liquid_mie_impl.h", "? clamp_value(mie.qsca / mie.qext", CLAMP,
     "omega = qsca/qext in [0, 1], 0 where qext = 0", "V26"),
    ("src/opacity/water_liquid_mie_impl.h", "mie.qext > static_cast<T>(0)", GUARD, "omega = 0 where qext = 0",
     "opacity_probe [Z4]"),
    # --- constants and sizes
    ("src/compound.cpp", "weight * 1.e-3", NOT, "g/mol to kg/mol", "-"),
    ("src/constants.h", "E-", NOT, "physical constant", "-"),
    ("src/constants.h", "e-", NOT, "physical constant", "-"),
    ("src/loops.cuh", "numeric_limits", NOT, "index range of the CUDA loop", "-"),
    ("src/utils/write_column_profile.hpp", "1.0e-", NOT, "unit conversion of the printed profile", "-"),
    ("src/utils/write_column_profile.hpp", "std::max<int>", NOT, "column width", "-"),
    ("src/utils/write_spectral_profile.hpp", "std::max<int>", NOT, "column width", "-"),
    # --- Python package
    ("python/atm_profile.py", "e-", NOT, "unit factors", "-"),
    ("python/spectra/blackbody.py", "np.clip(grid_cm1, 0.0, None)", CLAMP, "negative wavenumbers set to 0",
     "not measured: offline spectra tools, not on the band path"),
    ("python/spectra/blackbody.py", "np.clip(exponent, 0.0, 700.0)", CLAMP, "Planck exponent capped at 700",
     "not measured: offline spectra tools"),
    ("python/spectra/blackbody.py", "e-", NOT, "physical constant", "-"),
    ("python/spectra/blackbody.py", "np.max(radiance)", NOT, "plot scale", "-"),
    ("python/spectra/atm_overview.py", "max(0.0, 1.0 - float(h2o_fraction))", FLOOR,
     "foreign-gas fraction floored at 0", "not measured: offline spectra tools"),
    ("python/spectra/mt_ckd_h2o.py", "max(0.0, 1.0 - float(h2o_vmr))", FLOOR, "foreign-gas fraction floored at 0",
     "not measured: offline spectra tools"),
    ("python/spectra/hitran_molecule_utils.py", "np.maximum(profile - pedestal, 0.0)", FLOOR,
     "line-wing cut: the profile minus its value at the cut, floored at 0", "not measured: needs HITRAN data"),
    ("python/spectra/line_kernel.py", "np.maximum(values - pedestal[line_index], 0.0)", FLOOR,
     "line-wing cut, same", "not measured: needs HITRAN data"),
    ("python/spectra/hitran_molecule_utils.py", "max(0.0, band.wavenumber_min_cm1", CLAMP,
     "lower wavenumber of the line window >= 0", "not measured: offline spectra tools"),
    ("python/spectra/hitemp_lines.py", "np.maximum(strongest[sel], strength)", NOT, "running maximum", "-"),
    ("python/spectra/", "min_line_strength", NOT, "line-strength threshold of a plot or selection", "-"),
    ("python/spectra/", "minimum threshold", NOT, "message", "-"),
    ("python/spectra/", "rtol=1e-12", NOT, "comparison tolerance", "-"),
    ("python/spectra/", "atol=1e-12", NOT, "comparison tolerance", "-"),
    ("python/spectra/", "e-", NOT, "physical constant or unit factor", "-"),
    ("python/spectra/", "max(", NOT, "range, size or plot bookkeeping", "-"),
    ("python/spectra/", "min(", NOT, "range, size or plot bookkeeping", "-"),
    ("python/spectra/", ".min()", NOT, "printed range", "-"),
    ("python/spectra/", ".max()", NOT, "printed range", "-"),
    ("python/spectra/", "_min", NOT, "range bookkeeping", "-"),
    ("python/spectra/", "_max", NOT, "range bookkeeping", "-"),
]

# pydisort wrapper (src/) and the vendored cdisort on the paths the checks exercise
PYDISORT = [
    ("src/disort_formatter.hpp", "std::min", NOT, "number of printed waves"),
    ("src/disort.hpp", "accur) = 1.e-6", NOT, "default convergence criterion of the azimuth series"),
]
CDISORT = [
    ("cdisort213/cdisort.c", "dither = 100.*DBL_EPSILON", "omega = 1 moved to 1 - dither in the eigenproblem"),
    ("cdisort213/cdisort.c", "fabs(ds->bc.umu0-CMU(iq))/fabs(ds->bc.umu0) < 1.e-4",
     "umu0 within 1e-4 of a quadrature angle"),
    ("cdisort213/cdisort.c", "ds->bc.umu0 = (1. + 1.E-4)*CMU(iq)", "... is moved off it by 1e-4"),
    ("cdisort213/cdisort.c", "if (fabs((val-oldval)/val) <= 1.e-6) {", "Planck series converged at 1e-6"),
    ("cdisort213/cdisort.c", "if (t < 1.e-4) {", "Planck function of T < 1e-4 K is 0"),
]


def scan(root: Path):
    for g in GLOBS:
        for f in sorted(root.glob(g)):
            if not f.is_file():
                continue
            rel = str(f.relative_to(root))
            for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
                code = line.split("#")[0] if f.suffix == ".py" else line.split("//")[0]
                s = code.strip()
                if not s or s.startswith(("*", "/*")):
                    continue
                if PATTERN.search(code):
                    yield rel, i, s


def classify(rel: str, s: str):
    for path, needle, kind, what, effect in INVENTORY:
        if (rel == path or (path.endswith("/") and rel.startswith(path))) and needle in s:
            return kind, what, effect
    return None


def head(root: Path) -> str:
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True,
                          check=True).stdout.strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pyharp")
    ap.add_argument("pydisort", nargs="?")
    ap.add_argument("--csv")
    args = ap.parse_args()
    root = Path(args.pyharp)
    sha = head(root)
    rows, unclassified, counts = [], [], {}
    for rel, i, s in scan(root):
        c = classify(rel, s)
        if c is None:
            unclassified.append((rel, i, s))
            continue
        kind, what, effect = c
        counts[kind] = counts.get(kind, 0) + 1
        rows.append((rel, i, kind, what, effect, s))
        if kind != NOT:
            print(f"[F1] {rel}:{i}@{sha} | {kind} | {what} | effect: {effect} | `{s[:90]}`")
    print(f"[F2] {sum(counts.values())} hits in the compiled sources and the Python package: "
          + ", ".join(f"{k} {counts.get(k, 0)}" for k in (FLOOR, CLAMP, SWITCH, GUARD, REFUSE, NOT)))
    if args.pydisort:
        proot = Path(args.pydisort)
        psha = head(proot)
        for path, needle, kind, what in PYDISORT:
            for i, line in enumerate((proot / path).read_text(errors="replace").splitlines(), 1):
                if needle in line:
                    print(f"[F3] pydisort {path}:{i}@{psha} | {kind} | {what}")
        src = (proot / "cdisort213/cdisort.c").read_text(errors="replace").splitlines()
        n = sum(1 for l in src if re.search(r"\d\.?\d*[eE]-\d+|DBL_EPSILON|DBL_MIN", l.split("/*")[0]))
        for path, needle, what in CDISORT:
            hits = [i for i, line in enumerate(src, 1) if needle in line]
            print(f"[F4] pydisort {path}:{','.join(map(str, hits))}@{psha} | {what}")
        print(f"[F4] cdisort.c has {n} lines with a small literal or DBL_EPSILON/DBL_MIN in code; the five above lie on "
              f"the paths these checks run (omega -> 1, mu0 at a node, the Planck integral); the rest are not listed")
    for rel, i, s in unclassified:
        print(f"[F1] UNCLASSIFIED {rel}:{i}@{sha} `{s[:100]}`")
    if args.csv:
        with open(args.csv, "w") as f:
            f.write("file,line,kind,what,effect\n")
            for rel, i, kind, what, effect, s in rows:
                if kind != NOT:
                    f.write(f"{rel},{i},{kind},\"{what}\",\"{effect}\"\n")
    ok = not unclassified
    print(f"[F9] {'PASS' if ok else 'FAIL'} every guard of the compiled sources is listed: "
          f"{len(unclassified)} unclassified")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
