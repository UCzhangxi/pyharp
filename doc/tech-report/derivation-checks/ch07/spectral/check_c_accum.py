"""Check C: the accumulator itself, the per-point spectral units, grid
refinement with spectral structure, and the shortwave (no-Planck) control.

C1  band.forward() in wavenumber mode == numpy trapezoid over nu of
    band.buffer("spectrum")                     -> identifies sum_spectrum
C2  band.forward() in weight mode     == sum_i w_i * spectrum_i
C3  per-point spectrum units: ratio of the from_yaml configuration to the
    spectral-density configuration == B_band / B_nu (the extra factor)
C4  spectral structure (Lorentzian line) + grid refinement: density mode
    converges, the from_yaml wavenumber mode does not converge to it; the
    measured ratio is predicted by int (B_band/B_nu) F_nu dnu / int F_nu dnu
C5  shortwave band (no Planck source): the same accumulator is self-consistent
C6  nwave = 1 in wavenumber mode: the trapezoid is degenerate
"""

import json
import numpy as np
import torch

import pyharp
from pyharp import RadiationBand
from band_lab import (
    compile_grey,
    compile_line,
    make_band,
    isothermal_column,
    run_band,
    toa_up,
)
from ch7_common import planck_wavenumber, planck_flux_band, planck_band_integral

torch.set_default_dtype(torch.float64)
torch.set_num_threads(1)

T = 250.0
NLYR = 8
DZ = 1.0e3
res = {}


def build(solver, wmin, wmax, nwave, mode, opfile, jit_kwargs=("temp",),
          flags=None, nstr=4, tag="c"):
    if flags is None:
        flags = ("lamber,quiet,onlyfl,planck" if solver == "disort"
                 else "planck")
    bo = make_band("bx", wmin, wmax, nwave, NLYR, solver, opfile,
                   jit_kwargs=jit_kwargs, flags=flags, nstr=nstr, tag=tag)
    nu = np.linspace(wmin, wmax, nwave)
    if mode == "weight":
        bo.weight([1.0 / nwave] * nwave)
        bo.wavenumber(list(nu)) if "wavenumber" in jit_kwargs else None
    elif mode == "wavenumber":
        bo.wavenumber(list(nu))
    elif mode == "density":
        bo.wavenumber(list(nu))
        bo.set_wave_lower(list(nu))
        bo.set_wave_upper(list(nu))
    return bo, nu


def run_keep(bo, albedo=0.0, btemp=T, **kw):
    conc, dz, atm = isothermal_column(NLYR, T, DZ)
    nwave = bo.nwave()
    name = bo.name()
    bc = {
        f"{name}/albedo": albedo * torch.ones((nwave, 1), dtype=torch.float64),
        f"{name}/temis": torch.zeros((nwave, 1), dtype=torch.float64),
        "btemp": btemp * torch.ones((1,), dtype=torch.float64),
        "ttemp": torch.zeros((1,), dtype=torch.float64),
    }
    for k, v in kw.items():
        bc[k] = v
    band = RadiationBand(bo)
    flx = band.forward(conc, dz, bc, dict(atm))
    spec = band.buffer("spectrum").clone().numpy()
    return flx, spec


# ------------------------------------------------------------------ C1 / C2
print("== C1/C2: does the band total equal my own accumulation of the spectrum? ==")
wmin, wmax, nwave = 600.0, 800.0, 16
f = compile_grey("c_grey16.pt", nwave, 5.0e-3)

bo, nu = build("disort", wmin, wmax, nwave, "wavenumber", f, tag="c1")
flx, spec = run_keep(bo)
mine = np.trapezoid(spec[:, 0, -1, 0], nu)
res["C1"] = {"band_total": toa_up(flx), "numpy_trapz": float(mine),
             "rel_err": abs(toa_up(flx) - mine) / abs(mine)}
print(f"C1 wavenumber mode: band={toa_up(flx):.12e} trapz={mine:.12e} "
      f"relerr={res['C1']['rel_err']:.3e}")

bo, nu = build("disort", wmin, wmax, nwave, "weight", f, tag="c2")
flx, spec = run_keep(bo)
mine = float(np.sum(spec[:, 0, -1, 0]) / nwave)
res["C2"] = {"band_total": toa_up(flx), "numpy_weighted_sum": mine,
             "rel_err": abs(toa_up(flx) - mine) / abs(mine)}
print(f"C2 weight mode    : band={toa_up(flx):.12e} sum  ={mine:.12e} "
      f"relerr={res['C2']['rel_err']:.3e}")

# ------------------------------------------------------------------ C3
print("\n== C3: per-point spectral units (from_yaml vs density) ==")
bo_n, nu = build("disort", wmin, wmax, nwave, "wavenumber", f, tag="c3n")
_, spec_n = run_keep(bo_n)
bo_d, _ = build("disort", wmin, wmax, nwave, "density", f, tag="c3d")
_, spec_d = run_keep(bo_d)
ratio_pt = spec_n[:, 0, -1, 0] / spec_d[:, 0, -1, 0]
bband, _ = planck_band_integral(wmin, wmax, T)
pred = bband / planck_wavenumber(nu, T)
res["C3"] = {
    "wavenumber_cm": list(nu),
    "point_ratio": list(map(float, ratio_pt)),
    "predicted_B_band_over_B_nu": list(map(float, pred)),
    "max_rel_dev": float(np.max(np.abs(ratio_pt / pred - 1.0))),
}
print(f"   point ratio range  {ratio_pt.min():.4f} .. {ratio_pt.max():.4f}")
print(f"   predicted B_band/B_nu {pred.min():.4f} .. {pred.max():.4f}")
print(f"   max deviation from prediction: {res['C3']['max_rel_dev']:.3e}")

# ------------------------------------------------------------------ C4
print("\n== C4: Lorentzian line, grid refinement (DISORT) ==")
# k(nu) = 1e-6 + 2e-2 * hw^2/((nu-700)^2+hw^2) [1/m]; tau_tot 8e-3 .. 160.
# The surface is held at 150 K while the air is at 250 K, so the emergent
# spectrum carries the line shape instead of collapsing to pi*B.
lf = compile_line("c_line.pt", 1.0e-6, 2.0e-2, 700.0, 3.0)
c4 = []
for n in (16, 32, 64, 128, 256, 512, 1024, 2048):
    bo_d, nu = build("disort", wmin, wmax, n, "density", lf,
                     jit_kwargs=("wavenumber", "temp"), tag=f"c4d{n}")
    flx_d, spec_d = run_keep(bo_d, btemp=150.0)
    bo_n, _ = build("disort", wmin, wmax, n, "wavenumber", lf,
                    jit_kwargs=("wavenumber", "temp"), tag=f"c4n{n}")
    flx_n, spec_n = run_keep(bo_n, btemp=150.0)
    Fnu = spec_d[:, 0, -1, 0]
    weight = bband / planck_wavenumber(nu, T)
    predicted = np.trapezoid(weight * Fnu, nu) / np.trapezoid(Fnu, nu)
    c4.append({
        "nwave": n,
        "density_mode": toa_up(flx_d),
        "fromyaml_mode": toa_up(flx_n),
        "ratio": toa_up(flx_n) / toa_up(flx_d),
        "predicted_ratio": float(predicted),
    })
    print(f"   n={n:5d} density={toa_up(flx_d):14.8e} "
          f"from_yaml={toa_up(flx_n):14.8e} ratio={c4[-1]['ratio']:12.6f} "
          f"predicted={predicted:12.6f}")
ref_conv = c4[-1]["density_mode"]
for r in c4:
    r["density_rel_to_converged"] = r["density_mode"] / ref_conv - 1.0
    r["fromyaml_rel_to_converged"] = r["fromyaml_mode"] / c4[-1]["fromyaml_mode"] - 1.0
res["C4"] = c4
print("   refinement of the density mode (relative to n=2048):")
for r in c4:
    print(f"     n={r['nwave']:5d}  {r['density_rel_to_converged']:+.3e}")

# ------------------------------------------------------------------ C5
print("\n== C5: shortwave band (no Planck): accumulator self-consistency ==")
nwave = 32
fsw = compile_grey("c_sw.pt", nwave, 1.0e-5)
bo, nu = build("toon", wmin, wmax, nwave, "wavenumber", fsw, flags="", tag="c5")
S = 1.0 + 0.5 * np.sin((nu - wmin) / (wmax - wmin) * 2 * np.pi)  # W/m^2/cm^-1
bc_extra = {
    "bx/fbeam": torch.tensor(S, dtype=torch.float64).view(nwave, 1),
    "bx/umu0": torch.ones((1,), dtype=torch.float64),
}
conc, dz, atm = isothermal_column(NLYR, T, DZ)
band = RadiationBand(bo)
bc = {"bx/albedo": torch.zeros((nwave, 1), dtype=torch.float64)}
bc.update(bc_extra)
flx = band.forward(conc, dz, bc, dict(atm))
spec = band.buffer("spectrum").clone().numpy()
dn_toa = float(flx[0, -1, 1])
res["C5"] = {
    "band_down_toa": dn_toa,
    "trapz_of_supplied_fbeam": float(np.trapezoid(S, nu)),
    "ratio": dn_toa / float(np.trapezoid(S, nu)),
    "trapz_of_spectrum": float(np.trapezoid(spec[:, 0, -1, 1], nu)),
}
print(f"   TOA down = {dn_toa:.8e}; trapz of supplied fbeam density = "
      f"{np.trapezoid(S, nu):.8e}; ratio = {res['C5']['ratio']:.8f}")

# ------------------------------------------------------------------ C6
print("\n== C6: nwave = 1 in wavenumber mode ==")
f1 = compile_grey("c_one.pt", 1, 5.0e-3)
bo, nu = build("disort", wmin, wmax, 1, "wavenumber", f1, tag="c6")
flx, spec = run_keep(bo)
ref, _ = planck_flux_band(wmin, wmax, T)
res["C6"] = {"band_total": toa_up(flx), "per_point_spectrum":
             float(spec[0, 0, -1, 0]), "reference_pi_int_B": ref}
print(f"   band total = {toa_up(flx):.6e}  (per-point spectrum = "
      f"{spec[0,0,-1,0]:.6e}, pi*int B = {ref:.6e})")

json.dump(res, open("results_c_accum.json", "w"), indent=1)
print("\nwrote results_c_accum.json")
