#!/usr/bin/env python3
"""Chapter 10 check: invariants of the radiative-transfer path that a defect in a floor, a clamp or a dropped term
breaks (energy closure, flux positivity, the zero-opacity limit and its continuity, and the input thresholds of the
solver kernels).

usage: python -I invariants.py [--dump <file.npz>] [--csv <file.csv>] [--only <label prefix>]

Every case runs the full band path: a TorchScript opacity (`jit`) returns the per-layer extinction, single-scattering
albedo and Henyey-Greenstein moments of the case, `RadiationBand.forward` assembles and regularizes them, and the
band's solver (Toon-McKay89 or DISORT) returns the level fluxes that `Radiation.forward` sums over the band's
quadrature weights. Prints one line per claim, `[Ln] PASS|FAIL <what>: <numbers>`, and exits with the number of
failed claims. `--dump` writes every case's band fluxes, so two builds can be compared (`break_tests.sh`).
Needs a pyharp build of the pin of `code_pin.yml` and its pydisort; CPU, double precision.
"""
from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
import tempfile

import numpy as np
import torch
import pyharp
import pydisort

torch.set_default_dtype(torch.float64)
EPS = float(np.finfo(np.float64).eps)
NLYR = 20                      # layers of every column
NWAVE = 3                      # quadrature points per band, weights below
WEIGHTS = [0.2, 0.5, 0.3]      # band quadrature weights (sum 1)
WN = (500.0, 600.0)            # band range [cm^-1], the Planck integral of the longwave bands
FBEAM = 1000.0                 # beam flux normal to the beam [W m^-2] of every wave
GRAV, CP = 9.81, 1004.0        # gravity [m s^-2] and heat capacity [J kg^-1 K^-1] of the heating rate

# Tolerances, relative to the band's flux scale S (mu0 * FBEAM for a shortwave band, pi * B(T_ref) for a longwave
# band). Each is a bound with a reason, not a fit.
TOL = {
    # closure of a 21-level column: the telescoped sum adds 20 differences of values <= 2 S, so it rounds at
    # ~40 eps S; the boundary rows of the tridiagonal (Toon) or the boundary-condition solve (DISORT) are met to
    # the condition number of the system times eps, which the exp(35) cap of the layer exponentials bounds by
    # ~1e3 for these columns. 1e-10 leaves a factor ~10 over 40 * 1e3 * eps.
    "closure": 1e-10,
    # conservative scattering: the band clamps omega to 1 - 1e-12 (double), so a layer absorbs at most
    # (1 - omega) * dtau * 4 J / S <= 1e-12 * 40 * 4 relative for the thickest (tau = 40) column; plus round-off.
    "conservative": 1e-9,
    # isothermal column with Planck emission at the top and a black surface: net = 0 up to the closure bound.
    "isothermal": 1e-10,
    # positivity: a flux may undershoot zero by the round-off of its own sum (<= 40 eps S).
    "positivity": 1e-12,
    # zero opacity: Toon's pass-through is exact in IEEE arithmetic (exp(0) = 1, every source term multiplies
    # dtau = 0); cdisort still assembles the fluxes from its eigen-solution and particular solution, so round-off of
    # a few eps of S remains. 1e-15 = 4.5 eps.
    "zero": 1e-15,
    # tau -> 0: |F(tau) - F(0)| / (tau S) is the derivative of the flux in tau, O(1/mu0) for a beam and O(1) for
    # diffuse light. A bound of 100 / mu0 fails only where the response is not O(tau) (a jump or a cancellation).
    "slope": 100.0,
}

HERE = os.path.dirname(os.path.abspath(__file__))


class Optics(torch.nn.Module):
    """Returns (nwave, ncol, nlyr, 2 + nmom): extinction [1/m], single-scattering albedo, HG moments g^l."""

    def __init__(self, nmom: int):
        super().__init__()
        self.nmom = nmom

    def forward(self, conc: torch.Tensor, ext: torch.Tensor, ssa: torch.Tensor, gg: torch.Tensor) -> torch.Tensor:
        moments = [ext, ssa]
        for l in range(1, self.nmom + 1):
            moments.append(gg.pow(l))
        return torch.stack(moments, dim=-1)


BANDS = {
    # name: (solver, YAML band body)
    "toon_sw": ("toon", "solver: toon\n"),
    "disort_sw": ("disort", "solver: disort\n    flags: lamber,quiet,onlyfl\n"),
    "toon_lw": ("toon", "solver: toon\n    flags: planck,hard_surface\n    toon:\n      top_emission_flag: 0\n"),
    "toon_lw_top": ("toon", "solver: toon\n    flags: planck,hard_surface\n    toon:\n      top_emission_flag: 1\n"),
    "toon_lw_gg": ("toon", "solver: toon\n    flags: planck\n"),
    "toon_lw_gg_top": ("toon", "solver: toon\n    flags: planck\n    toon:\n      top_emission_flag: 1\n"),
    "disort_lw": ("disort", "solver: disort\n    flags: lamber,quiet,onlyfl,planck\n"),
}
LONGWAVE = {"toon_lw", "toon_lw_top", "toon_lw_gg", "toon_lw_gg_top", "disort_lw"}


def make_radiation(band: str, workdir: str):
    """One Radiation with one band of NWAVE weighted points, built from YAML as a user would."""
    nmom = 4
    pt = os.path.join(workdir, "optics.pt")
    if not os.path.exists(pt):
        pyharp.compile(Optics(nmom), pt)
    body = BANDS[band][1]
    yaml = (
        "species:\n  - name: dummy\n    composition: {H: 1}\n"
        f"geometry:\n  cells:\n    nx1: {NLYR}\n"
        f"opacities:\n  optics:\n    type: jit\n    data: [{pt}]\n    jit_kwargs: [ext, ssa, gg]\n    nmom: {nmom}\n"
        f"bands:\n  - name: {band}\n    range: [{WN[0]}, {WN[1]}]\n    opacities: [optics]\n"
        f"    integration: weight\n    nwave: {NWAVE}\n    nstr: 4\n    {body}"
    )
    fn = os.path.join(workdir, f"{band}.yaml")
    with open(fn, "w") as f:
        f.write(yaml)
    op = pyharp.RadiationOptions.from_yaml(fn)
    for b in op.bands():
        b.weight(WEIGHTS)
        if BANDS[band][0] == "disort":
            # a YAML DISORT band leaves ds.nphase unwritten ([D1]); 0 is the value that allocates no phase table
            b.disort().ds().nphase = 0
    return pyharp.Radiation(op)


def column(tau_total, tlev=(300.0, 200.0)):
    """Pressure levels (bottom first), dz from pyharp's hypsometric routine, level temperatures."""
    plev = torch.logspace(5, 3, NLYR + 1)
    tl = torch.linspace(tlev[0], tlev[1], NLYR + 1)
    tlay = 0.5 * (tl[1:] + tl[:-1])
    play = torch.sqrt(plev[1:] * plev[:-1])
    rd = 287.0
    dz = torch.log(plev[:-1] / plev[1:]) * rd * tlay / GRAV
    return plev, tl, tlay, play, dz


def run_case(rad, band: str, case: dict):
    """Band fluxes (ncol=1): returns dict of numpy arrays up, dn, mid_up, mid_dn (nlev,), and the solver input."""
    tau = torch.as_tensor(case["tau"], dtype=torch.float64).reshape(NWAVE)  # column optical depth per wave
    plev, tl, tlay, play, dz = column(tau, case.get("tlev", (300.0, 200.0)))
    # per-layer optical depth: uniform in pressure, so dtau_k / dz_k is the extinction
    frac = (plev[:-1] - plev[1:]) / (plev[0] - plev[-1])
    dtau = tau.view(NWAVE, 1, 1) * frac.view(1, 1, NLYR)
    ext = dtau / dz.view(1, 1, NLYR)
    ssa = torch.as_tensor(case["ssa"], dtype=torch.float64).reshape(-1, 1, 1).expand(NWAVE, 1, NLYR).clone()
    gg = torch.as_tensor(case.get("g", 0.0), dtype=torch.float64).reshape(-1, 1, 1).expand(NWAVE, 1, NLYR).clone()
    alb = float(case.get("albedo", 0.0))
    mu0 = float(case.get("mu0", 0.6))
    bc = {
        f"{band}/umu0": torch.tensor([mu0]),
        f"{band}/fbeam": torch.full((NWAVE, 1), FBEAM if band not in LONGWAVE else 0.0),
        f"{band}/albedo": torch.full((NWAVE, 1), alb),
    }
    atm = {"ext": ext, "ssa": ssa, "gg": gg}
    # level temperatures always: a DISORT band without them stops in RtSolver dispatch (chapter 3, candidate P3);
    # without the `planck` flag the solver does not read them
    atm["tempf"] = tl.view(1, NLYR + 1)
    if band in LONGWAVE:
        bc["btemp"] = torch.tensor([float(tl[0])])
        bc["ttemp"] = torch.tensor([float(tl[-1])])
        if band == "disort_lw":
            bc[f"{band}/temis"] = torch.full((NWAVE, 1), float(case.get("temis", 0.0)))
    conc = torch.ones(1, NLYR, 1)
    net, sfc_dn, toa_up = rad.forward(conc, dz, bc, atm)
    spec = rad.spectra[0, 0].numpy().copy()  # (nlev, 4), level 0 = surface
    return {
        "up": spec[:, 0], "dn": spec[:, 1], "mid_up": spec[:, 2], "mid_dn": spec[:, 3],
        "net": net[0].numpy().copy(), "sfc_dn": float(sfc_dn[0]), "toa_up": float(toa_up[0]),
        "mu0": mu0, "albedo": alb, "plev": plev.numpy(), "tl": tl.numpy(),
    }


def planck_band(temp: float) -> float:
    """pi B integrated over the band [W m^-2]. `bbflux_wavenumber` (the routine the Toon kernel calls) returns the
    band radiance B [W m^-2 sr^-1]; the kernel's hemispheric quadrature, 2 pi sum_m w_m with sum_m w_m = 1/2,
    turns an isotropic B into the flux pi B."""
    b = pyharp.bbflux_wavenumber(WN[0], WN[1], torch.tensor([[temp]]))
    return math.pi * float(b.reshape(-1)[0])


SW_CASES = {
    "nominal": dict(tau=[0.5, 2.0, 8.0], ssa=[0.3, 0.8, 0.95], g=0.6, albedo=0.3, mu0=0.6),
    "w0=0,A=0": dict(tau=[0.5, 2.0, 8.0], ssa=0.0, g=0.0, albedo=0.0, mu0=0.6),
    "w0=0,A=0.3": dict(tau=[0.5, 2.0, 8.0], ssa=0.0, g=0.0, albedo=0.3, mu0=0.6),
    "w0=1": dict(tau=[0.5, 4.0, 40.0], ssa=1.0, g=0.85, albedo=0.3, mu0=0.6),
    "w0=1-1e-6,A=0.99": dict(tau=[0.5, 4.0, 40.0], ssa=1.0 - 1e-6, g=0.9, albedo=0.99, mu0=0.6),
    "A=0": dict(tau=[0.5, 2.0, 8.0], ssa=0.5, g=0.5, albedo=0.0, mu0=0.6),
    "A=1": dict(tau=[0.5, 2.0, 8.0], ssa=0.5, g=0.5, albedo=1.0, mu0=0.6),
    "grazing mu0=0.02": dict(tau=[0.5, 2.0, 8.0], ssa=0.9, g=0.7, albedo=0.3, mu0=0.02),
    "grazing mu0=1e-3": dict(tau=[0.05, 0.2, 1.0], ssa=0.9, g=0.7, albedo=0.3, mu0=1e-3),
    "thick tau=400": dict(tau=[40.0, 100.0, 400.0], ssa=0.9, g=0.7, albedo=0.3, mu0=0.6),
    "tau=0": dict(tau=[0.0, 0.0, 0.0], ssa=0.5, g=0.5, albedo=0.3, mu0=0.6),
}
LW_CASES = {
    "nominal": dict(tau=[0.5, 2.0, 8.0], ssa=[0.3, 0.3, 0.3], g=0.5, albedo=0.1),
    "w0=0": dict(tau=[0.5, 2.0, 8.0], ssa=0.0, g=0.0, albedo=0.1),
    "w0=0.99": dict(tau=[0.5, 2.0, 8.0], ssa=0.99, g=0.8, albedo=0.1),
    "A=0": dict(tau=[0.5, 2.0, 8.0], ssa=0.3, g=0.5, albedo=0.0),
    "A=0.99": dict(tau=[0.5, 2.0, 8.0], ssa=0.3, g=0.5, albedo=0.99),
    "thick tau=400": dict(tau=[40.0, 100.0, 400.0], ssa=0.3, g=0.5, albedo=0.1),
    "tau=0": dict(tau=[0.0, 0.0, 0.0], ssa=0.3, g=0.5, albedo=0.1),
}
ISO_CASE = dict(tau=[0.5, 2.0, 8.0], ssa=[0.0, 0.5, 0.9], g=0.5, albedo=0.0, tlev=(250.0, 250.0), temis=1.0)


class Report:
    def __init__(self):
        self.fails = 0
        self.rows = []

    def line(self, label: str, ok: bool, what: str, numbers: str, quantity: str = "", value=None, tol=None):
        if not ok:
            self.fails += 1
        print(f"[{label}] {'PASS' if ok else 'FAIL'} {what}: {numbers}", flush=True)
        if quantity:
            self.rows.append((label, what, quantity, value, tol, "PASS" if ok else "FAIL"))


def fmt(x: float) -> str:
    if x == 0.0:
        return "0"
    if not math.isfinite(x):
        return str(x)
    return f"{x:.1e}"


def scale_of(band: str, case: dict, res: dict) -> float:
    if band in LONGWAVE:
        return planck_band(float(res["tl"][0]))
    return case.get("mu0", 0.6) * FBEAM


PI_B_SFC = {}  # band -> pi B(T_s) as the band's own solver integrates it (a tau = 0, A = 0 run), set in main()


def closure_terms(band: str, case: dict, res: dict) -> tuple[float, float, float]:
    """(divergence sum, TOA net from the boundary data, surface net from the boundary data) [W m^-2].

    TOA net uses the returned TOA upward flux and the incident flux the boundary condition prescribes (mu0 * FBEAM,
    or the top emission); surface net uses the returned surface downward flux and the upward flux the surface
    condition prescribes (A F_dn for the Lambertian beam band, (1 - A) pi B(T_s) + A F_dn for a hard longwave
    surface, with the solver's own Planck integral). Their difference is the energy the column absorbs; it must equal the sum of the layer divergences.
    """
    net = res["net"]
    div_sum = float(np.sum(net[1:] - net[:-1]))
    if band in LONGWAVE:
        f_in = 0.0
        if band == "toon_lw_top":
            f_in = planck_band(float(res["tl"][-1]))
        up_sfc = (1.0 - res["albedo"]) * PI_B_SFC[band] + res["albedo"] * res["sfc_dn"]
    else:
        f_in = case.get("mu0", 0.6) * FBEAM
        up_sfc = res["albedo"] * res["sfc_dn"]
    toa_net = res["toa_up"] - f_in
    sfc_net = up_sfc - res["sfc_dn"]
    return div_sum, toa_net, sfc_net


def heating_consistency():
    """Ratio of the two heating rates of a layer, (F_k - F_k+1) / (rho_k c_p dz_k) against g (F_k - F_k+1) /
    (c_p dp_k). With p_k the layer pressure (geometric mean of its levels, the grid's own), rho_k = p_k / (R T_k) and
    dz_k = (R T_k / g) x_k, x_k = ln(p_k-1/2 / p_k+1/2) the hypsometric thickness; the ratio is dp_k / (p_k x_k) =
    2 sinh(x_k / 2) / x_k exactly. pyharp's calc_dz_hypsometric rebuilds the level ln p from the layer values
    (second-order extrapolation at the ends), which is exact on a grid uniform in ln p."""
    worst, n, xmax = 0.0, 0, 0.0
    for nl, ptop in ((20, 1e3), (50, 1.0), (8, 5e4)):
        plev = torch.logspace(5, math.log10(ptop), nl + 1)
        play = torch.sqrt(plev[1:] * plev[:-1])
        tlay = torch.linspace(290.0, 180.0, nl)
        rd = 287.0
        dz = pyharp.calc_dz_hypsometric(play, tlay, torch.tensor([GRAV / rd]))
        rho = play / (rd * tlay)
        x = torch.log(plev[:-1] / plev[1:])
        ratio = (plev[:-1] - plev[1:]) / (GRAV * rho * dz)  # H_z / H_p for any flux difference
        expect = 2.0 * torch.sinh(x / 2) / x
        worst = max(worst, float(torch.max(torch.abs(ratio - expect))))
        n += nl
        xmax = max(xmax, float(x.max()))
    return worst, n, xmax


def heating(res: dict) -> np.ndarray:
    """Layer heating rate [K/day]: (g / c_p) (F_net,k - F_net,k+1) / (p_k - p_k+1), levels bottom first."""
    net, p = res["net"], res["plev"]
    return GRAV / CP * (net[:-1] - net[1:]) / (p[:-1] - p[1:]) * 86400.0


def isolate(band: str, cases: dict, workdir: str) -> dict:
    rad = make_radiation(band, workdir)
    return {name: run_case(rad, band, c) for name, c in cases.items()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump")
    ap.add_argument("--csv")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    rep = Report()
    work = tempfile.mkdtemp(prefix="ch10inv-")
    print(f"[I0] pyharp {pyharp.__version__}, pydisort {pydisort.__version__}, torch {torch.__version__}, "
          f"numpy {np.__version__}, Python {sys.version.split()[0]}; CPU, double; nlyr {NLYR}, nwave {NWAVE}")

    results = {}
    for band in ("toon_sw", "disort_sw"):
        results[band] = isolate(band, SW_CASES, work)
    for band in ("toon_lw", "toon_lw_gg", "disort_lw"):
        results[band] = isolate(band, LW_CASES, work)
    iso = {b: isolate(b, {"iso": ISO_CASE}, work)["iso"] for b in ("toon_lw_top", "toon_lw_gg_top", "disort_lw")}
    for band in ("toon_lw", "disort_lw"):
        ref = isolate(band, {"ref": dict(LW_CASES["tau=0"], albedo=0.0)}, work)["ref"]
        PI_B_SFC[band] = float(ref["up"][0])
    pib = planck_band(300.0)
    print(f"[E0] pi B(300 K) over {WN[0]:.0f}-{WN[1]:.0f} cm^-1: pyharp bbflux_wavenumber {pib:.10g} W m^-2; "
          f"Toon band {PI_B_SFC['toon_lw']:.10g} (relative difference {fmt(abs(PI_B_SFC['toon_lw'] - pib) / pib)}); "
          f"DISORT band {PI_B_SFC['disort_lw']:.10g} (relative difference "
          f"{fmt(abs(PI_B_SFC['disort_lw'] - pib) / pib)}, its own Planck integral)")

    dump = {}
    for band, rs in results.items():
        for name, r in rs.items():
            for k in ("up", "dn", "mid_up", "mid_dn"):
                dump[f"{band}|{name}|{k}"] = r[k]
    for band, r in iso.items():
        for k in ("up", "dn", "mid_up", "mid_dn"):
            dump[f"{band}|iso|{k}"] = r[k]

    # ---- E1: energy closure, every band and case with a prescribed surface condition
    worst = (0.0, "")
    nan_cases = []
    for band, rs in results.items():
        if band == "toon_lw_gg":
            continue  # its lower boundary is an internal-heat flux, not a reflecting surface (E3 covers it)
        cases = SW_CASES if band not in LONGWAVE else LW_CASES
        for name, r in rs.items():
            d, t, s = closure_terms(band, cases[name], r)
            rel = abs(d - (t - s)) / scale_of(band, cases[name], r)
            if not math.isfinite(rel):
                nan_cases.append(f"{band}/{name}")
                rel = math.inf
            if rel >= worst[0]:
                worst = (rel, f"{band}/{name}")
            top = abs(r["dn"][-1] - (cases[name].get("mu0", 0.6) * FBEAM if band not in LONGWAVE else 0.0))
            rel_top = top / scale_of(band, cases[name], r)
            print(f"[E1] {band:9s} {name:18s} closure residual {fmt(rel)}, top-boundary residual {fmt(rel_top)}")
    ok = worst[0] <= TOL["closure"] and not nan_cases
    rep.line("E1", ok, "energy closure, sum of layer divergences = TOA net - surface net (both from the boundary data)",
             f"max |residual| / S = {fmt(worst[0])} at {worst[1]}, tolerance {TOL['closure']:.0e}"
             + (f"; non-finite in {nan_cases}" if nan_cases else ""),
             "max |sum div - (TOA net - sfc net)| / S", worst[0], TOL["closure"])

    # ---- E2: conservative scattering absorbs nothing (shortwave, omega = 1 clamped by the band)
    worst = (0.0, "")
    for band in ("toon_sw", "disort_sw"):
        r = results[band]["w0=1"]
        S = scale_of(band, SW_CASES["w0=1"], r)
        rel = float(np.max(np.abs(r["net"][1:] - r["net"][:-1]))) / S
        rel = rel if math.isfinite(rel) else math.inf
        if rel >= worst[0]:
            worst = (rel, band)
        h = float(np.max(np.abs(heating(r))))
        fourpij = float(np.max(2.0 * (r["up"] + r["dn"]))) / S + 1.0 / SW_CASES["w0=1"]["mu0"]
        print(f"[E2] {band:9s} w0=1 max layer |divergence| / S {fmt(rel)}, max |heating| {fmt(h)} K/day; "
              f"4 pi J / S <= max 2 (F+ + F-) / S + 1 / mu0 = {fourpij:.2f}")
    rep.line("E2", worst[0] <= TOL["conservative"], "conservative scattering, every layer divergence = 0",
             f"max |dF_k| / S = {fmt(worst[0])} at {worst[1]}, tolerance {TOL['conservative']:.0e}",
             "max_k |F_net,k+1 - F_net,k| / S, omega = 1", worst[0], TOL["conservative"])

    # ---- E3: isothermal column in radiative equilibrium (Planck top emission, black surface)
    worst = (0.0, "")
    for band, r in iso.items():
        S = planck_band(250.0)
        rel = float(np.max(np.abs(r["net"]))) / S
        rel = rel if math.isfinite(rel) else math.inf
        relup = float(np.max(np.abs(r["up"] - S))) / S
        if band == "disort_lw":
            relup = float(np.max(np.abs(r["up"] - r["up"][0]))) / S  # DISORT integrates its own Planck function
        if max(rel, relup) >= worst[0]:
            worst = (max(rel, relup), band)
        h = float(np.max(np.abs(heating(r))))
        print(f"[E3] {band:11s} isothermal 250 K: max |F_net| / S {fmt(rel)}, max |F_up - pi B| / S {fmt(relup)}, "
              f"max |heating| {fmt(h)} K/day")
    rep.line("E3", worst[0] <= TOL["isothermal"], "isothermal column, net flux = 0 and F_up = pi B at every level",
             f"max / S = {fmt(worst[0])} at {worst[1]}, tolerance {TOL['isothermal']:.0e}",
             "max_k |F_net,k| / (pi B), isothermal", worst[0], TOL["isothermal"])

    # ---- E4: the heating rate per unit volume (pyharp's hypsometric dz, density from the layer state) equals the
    # heating per unit mass of the pressure grid, layer by layer, up to the exact hypsometric factor
    e4 = heating_consistency()
    rep.line("E4", e4[0] <= TOL["closure"], "heating rate from rho c_p dz (calc_dz_hypsometric) = from c_p dp / g",
             f"max |H_z / H_p - 2 sinh(x/2) / x| = {fmt(e4[0])} over {e4[1]} layers (x = ln(p_k / p_k+1), up to "
             f"{e4[2]:.3f}), tolerance {TOL['closure']:.0e}", "max |H_z / H_p - 2 sinh(x/2)/x|", e4[0], TOL["closure"])

    # ---- P1: no negative or non-finite flux in any channel of any case
    worst = (0.0, "")
    nonfinite = []
    for band, rs in list(results.items()) + [(b, {"iso": r}) for b, r in iso.items()]:
        for name, r in rs.items():
            arr = np.concatenate([r["up"], r["dn"], r["mid_up"], r["mid_dn"]])
            if not np.all(np.isfinite(arr)):
                nonfinite.append(f"{band}/{name}")
                continue
            S = scale_of(band, SW_CASES.get(name, LW_CASES.get(name, ISO_CASE)), r)
            neg = max(0.0, -float(arr.min())) / S
            if neg >= worst[0]:
                worst = (neg, f"{band}/{name}")
    ok = worst[0] <= TOL["positivity"] and not nonfinite
    nsw = sum(len(results[b]) for b in results if b not in LONGWAVE)
    nlw = sum(len(results[b]) for b in results if b in LONGWAVE)
    rep.line("P1", ok, f"fluxes >= 0 and finite (up, down, both midpoint channels; {nsw} shortwave, {nlw} longwave, "
             f"{len(iso)} isothermal band runs)",
             f"max negative / S = {fmt(worst[0])} at {worst[1] or 'none'}, tolerance {TOL['positivity']:.0e}; "
             f"non-finite cases: {len(nonfinite)}" + (f" {nonfinite}" if nonfinite else ""),
             "max(0, -min F) / S", worst[0], TOL["positivity"])

    # ---- P2: in the shortwave no layer emits, so every layer absorbs >= 0
    worst = (0.0, "")
    for band in ("toon_sw", "disort_sw"):
        for name, r in results[band].items():
            a = r["net"][:-1] - r["net"][1:]  # absorbed by layer k [W m^-2]... sign: in - out
            # energy into layer k: F_net,k (bottom, upward) - F_net,k+1 (top); absorbed >= 0 means net_k >= net_k+1
            S = scale_of(band, SW_CASES[name], r)
            neg = max(0.0, -float(np.nanmin(a))) / S if np.all(np.isfinite(a)) else math.inf
            if neg >= worst[0]:
                worst = (neg, f"{band}/{name}")
    rep.line("P2", worst[0] <= TOL["conservative"], "shortwave layer absorption >= 0 (heating >= 0)",
             f"max negative absorption / S = {fmt(worst[0])} at {worst[1]}, tolerance {TOL['conservative']:.0e} "
             "(the conservative-scattering bound: omega = 1 makes the absorption round-off)",
             "max(0, -min_k (F_net,k - F_net,k+1)) / S", worst[0], TOL["conservative"])

    # ---- P4: longwave maximum principle: with a black or grey Lambertian surface, no top illumination and
    # emission at the level temperatures only, no flux exceeds pi B(T_max) (scattering and reflection average)
    worst = (0.0, "")
    for band in ("toon_lw", "disort_lw"):
        for name, r in results[band].items():
            S = PI_B_SFC[band]  # T_max = T_s = 300 K in every longwave case
            over = max(0.0, float(max(np.max(r["up"]), np.max(r["dn"]))) / S - 1.0)
            over = over if np.all(np.isfinite(r["up"])) else math.inf
            if over >= worst[0]:
                worst = (over, f"{band}/{name}")
    rep.line("P4", worst[0] <= TOL["positivity"], "longwave fluxes <= pi B(T_max) (hard surface)",
             f"max (F / pi B(T_max) - 1) = {fmt(worst[0])} at {worst[1]}, tolerance {TOL['positivity']:.0e}",
             "max(0, max F / (pi B(T_max)) - 1)", worst[0], TOL["positivity"])

    # ---- P3: DISORT intensities at user angles >= 0 for the edge cases (the only solver that exposes them)
    p3 = disort_intensities()
    rep.line("P3", p3[0] <= TOL["positivity"] and p3[2] == 0, "DISORT intensities >= 0 at 8 user angles, 6 edge cases",
             f"max negative / (mu0 F0 / pi) = {fmt(p3[0])} at {p3[1]}, non-finite {p3[2]}, tolerance "
             f"{TOL['positivity']:.0e}", "max(0, -min I) / (mu0 F0 / pi)", p3[0], TOL["positivity"])

    # ---- Z1: zero opacity passes the boundary fluxes through unchanged
    z = []
    for band in ("toon_sw", "disort_sw"):
        r = results[band]["tau=0"]
        c = SW_CASES["tau=0"]
        S = c["mu0"] * FBEAM
        dev = max(np.max(np.abs(r["dn"] - S)), np.max(np.abs(r["up"] - c["albedo"] * S)),
                  np.max(np.abs(r["net"][1:] - r["net"][:-1]))) / S
        z.append((float(dev) if np.isfinite(dev) else math.inf, band))
        print(f"[Z1] {band:9s} tau=0: max |F_dn - mu0 F0|, |F_up - A mu0 F0|, |dF| over S = {fmt(z[-1][0])}")
    for band in ("toon_lw", "toon_lw_gg", "disort_lw"):
        r = results[band]["tau=0"]
        c = LW_CASES["tau=0"]
        S = planck_band(300.0)
        up_expect = (1 - c["albedo"]) * S if band == "toon_lw" else (S if band == "toon_lw_gg" else r["up"][0])
        dev = max(np.max(np.abs(r["dn"])), np.max(np.abs(r["up"] - up_expect)),
                  np.max(np.abs(r["net"][1:] - r["net"][:-1]))) / S
        z.append((float(dev) if np.isfinite(dev) else math.inf, band))
        print(f"[Z1] {band:9s} tau=0: max |F_dn - 0|, |F_up - F_up,sfc|, |dF| over S = {fmt(z[-1][0])}")
    w = max(z)
    rep.line("Z1", w[0] <= TOL["zero"], "tau = 0: fluxes pass through unchanged, divergence and heating exactly 0",
             f"max deviation / S = {fmt(w[0])} at {w[1]}, tolerance {TOL['zero']:.0e}; Toon bands "
             f"{fmt(max(v for v, b in z if b.startswith('toon')))} (exact)",
             "max |F(tau=0) - boundary flux| / S", w[0], TOL["zero"])

    # ---- Z2: tau -> 0 is continuous: |F(tau) - F(0)| / (tau S) stays O(1/mu0) down to tau = 1e-14
    slope_max, where, slopes = 0.0, "", {}
    taus = [1e-14, 1e-12, 1e-10, 1e-8, 1e-6, 1e-4, 1e-2]
    for band in ("toon_sw", "disort_sw", "toon_lw", "disort_lw"):
        rad = make_radiation(band, work)
        base = dict(SW_CASES["tau=0"] if band not in LONGWAVE else LW_CASES["tau=0"])
        r0 = run_case(rad, band, base)
        S = scale_of(band, base, r0)
        for t in taus:
            c = dict(base, tau=[t, t, t])
            r = run_case(rad, band, c)
            dev = max(np.max(np.abs(r["up"] - r0["up"])), np.max(np.abs(r["dn"] - r0["dn"]))) / S
            s = float(dev / t) * base.get("mu0", 1.0) if np.isfinite(dev) else math.inf
            slopes[(band, t)] = s
            if s >= slope_max:
                slope_max, where = s, f"{band} tau={t:.0e}"
        print(f"[Z2] {band:10s} mu0 |F(tau) - F(0)| / (tau S) at tau = " +
              ", ".join(f"{t:.0e}: {fmt(slopes[(band, t)])}" for t in taus))
    rep.line("Z2", slope_max <= TOL["slope"], "tau -> 0 continuity, the flux response is O(tau) down to tau = 1e-14",
             f"max mu0 |F(tau) - F(0)| / (tau S) = {fmt(slope_max)} at {where}, bound {TOL['slope']:.0f}",
             "max mu0 |F(tau) - F(0)| / (tau S)", slope_max, TOL["slope"])
    gas_giant_boundary(work)

    # ---- T1-T4: the input thresholds of the kernels (each is a switch of formula; the answer must not jump)
    thresholds(rep, work)

    uninitialized_nphase()

    if args.dump:
        np.savez(args.dump, **dump)
    if args.csv:
        with open(args.csv, "w") as f:
            f.write("label,quantity,value,tolerance,result\n")
            for label, what, q, v, t, res in rep.rows:
                f.write(f"{label},\"{q}\",{v:.3e},{t:.0e},{res}\n")
    print(f"[I9] {rep.fails} failed")
    return rep.fails


def disort_intensities(flags="usrtau,usrang,lamber,quiet,intensity_correction,old_intensity_correction", tag="P3"):
    """Intensities from pydisort directly (pyharp's band runs DISORT with onlyfl): 8 user angles at every level,
    with the intensity-correction flags of pyharp's own shortwave DISORT configuration (`create_disort_config_sw`)."""
    worst, where, nonfinite = 0.0, "", 0
    bad = []
    cases = {
        "w0=0": (0.0, 0.0, 0.3, 0.6), "w0=1-1e-12": (1.0 - 1e-12, 0.85, 0.3, 0.6), "A=0": (0.5, 0.5, 0.0, 0.6),
        "A=1": (0.5, 0.5, 1.0, 0.6), "grazing mu0=0.02": (0.9, 0.7, 0.3, 0.02), "tau=0": (0.5, 0.5, 0.3, 0.6),
    }
    for name, (w0, g, alb, mu0) in cases.items():
        op = pydisort.DisortOptions().flags(flags)
        op.ds().nlyr = NLYR
        op.ds().nstr = 8
        op.ds().nmom = 8
        op.ds().nphase = 8
        tau_layer = 0.0 if name == "tau=0" else 0.1
        op.user_tau(np.linspace(0.0, tau_layer * NLYR, NLYR + 1))
        op.user_mu(np.array([-1.0, -0.6, -0.2, -0.05, 0.05, 0.2, 0.6, 1.0]))
        op.user_phi(np.array([0.0]))
        ds = pydisort.Disort(op)
        prop = torch.zeros(1, 1, NLYR, 2 + 8)
        prop[..., 0] = tau_layer
        prop[..., 1] = w0
        prop[..., 2:] = torch.tensor([g ** l for l in range(1, 9)])
        bc = {"umu0": torch.tensor([mu0]), "phi0": torch.tensor([0.0]), "fbeam": torch.tensor([[FBEAM]]),
              "albedo": torch.tensor([[alb]])}
        ds.forward(prop, **bc)
        rad = ds.gather_rad().numpy()
        if not np.all(np.isfinite(rad)):
            nonfinite += 1
            bad.append(name)
            continue
        neg = max(0.0, -float(rad.min())) / (mu0 * FBEAM / math.pi)
        print(f"[{tag}] disort {name:17s} min I / (mu0 F0 / pi) {float(rad.min()) / (mu0 * FBEAM / math.pi):.3e}")
        if neg >= worst:
            worst, where = neg, name
    return worst, where, nonfinite, bad


def bottom_fraction() -> float:
    """Fraction of the column optical depth in the bottom layer (layers uniform in pressure on a log-p grid)."""
    plev = column(None)[0]
    return float((plev[0] - plev[1]) / (plev[0] - plev[-1]))


def gas_giant_boundary(work: str):
    """Z3: the Toon longwave lower boundary without `hard_surface` is I_up = B_s + B1 u with B1 = dB / dtau of the
    bottom layer (toon_mckay89_longwave_impl.h). Swept over the column optical depth, uniform layers, 300 K -> 200 K."""
    rad = make_radiation("toon_lw_gg", work)
    S = planck_band(300.0)
    out = []
    fb = bottom_fraction()
    for t in [0.99e-6 / fb, 1.01e-6 / fb, 1e-5, 1e-4, 1e-2, 1.0, 100.0]:
        r = run_case(rad, "toon_lw_gg", dict(LW_CASES["w0=0"], tau=[t, t, t]))
        out.append((t, float(r["up"][0]) / S, float(np.max(r["up"])) / S))
    worst = max(out, key=lambda x: x[2])
    print("[Z3] toon_lw_gg F_up,sfc / (pi B_s) at column tau = " +
          ", ".join(f"{t:.1e}: {u:.3g}" for t, u, _ in out))
    print(f"[Z3] CANDIDATE {'reproduced' if worst[2] > 2.0 else 'not reproduced'}: without `hard_surface` the upward "
          f"flux of an optically thin column is unbounded, max F_up / (pi B_s) = {worst[2]:.3g} at column tau = "
          f"{worst[0]:.2e} (bottom-layer dtau {worst[0] * fb:.2e}); it is pi B_s again at bottom-layer dtau <= 1e-6")


def uninitialized_nphase():
    """D1: pydisort's DisortOptions constructor writes the flags, the boundary values and accur of its disort_state
    but not nphase, and pyharp's YAML DISORT band (create_disort_config) does not set it either. cdisort allocates a
    phase table of nlyr * nphase values whenever nphase >= 1 and `old_intensity_correction` is off, so the value
    left in memory decides whether a band allocates, wastes memory or aborts."""
    seen = set()
    junk = []
    for i in range(2000):
        junk.append(bytearray(b"\xab" * (64 + i % 512)))  # freed heap holding a known non-zero byte pattern
        if i % 3 == 0:
            junk.pop(0)
        seen.add(pydisort.DisortOptions().ds().nphase)
    nonzero = any(v != 0 for v in seen)
    print(f"[D1] CANDIDATE {'reproduced' if nonzero else 'not reproduced'}: ds.nphase of a new DisortOptions is never "
          f"written; built 2000 times on a heap holding 0xAB bytes it reads back "
          f"{'nonzero values' if nonzero else 'only 0'}; a YAML DISORT band (create_disort_config) inherits the value, "
          f"so cdisort allocates nlyr * nphase phase values, or aborts when that product overflows")


def thresholds(rep: Report, work: str):
    """The answer on both sides of each input threshold of the kernels; a jump larger than the bound is a defect.

    T1  Toon shortwave: all layers omega <= 1e-12 and A <= 1e-12 select the beam-only formula.
    T2  Toon longwave: omega <= 1e-4 drops the scattering source terms of the intensity sweep.
    T3  Toon longwave: dtau <= 1e-6 takes the Planck function constant across the layer (B1 = 0).
    T4  Toon shortwave: lam mu0 within sqrt(eps) of 1 moves mu0 off the resonance.
    """
    # T1: omega just below and just above 1e-12, A = 0
    rad = make_radiation("toon_sw", work)
    lo = run_case(rad, "toon_sw", dict(SW_CASES["w0=0,A=0"], ssa=0.5e-12))
    hi = run_case(rad, "toon_sw", dict(SW_CASES["w0=0,A=0"], ssa=2.0e-12))
    S = 0.6 * FBEAM
    jump = max(np.max(np.abs(lo["up"] - hi["up"])), np.max(np.abs(lo["dn"] - hi["dn"]))) / S
    # the physical change from omega 0.5e-12 to 2e-12 is O(1.5e-12 tau); the bound adds the closure round-off
    bound = 1.5e-12 * 8.0 * 10 + TOL["closure"]
    rep.line("T1", jump <= bound, "Toon shortwave beam-only switch at omega = 1e-12 is continuous",
             f"max |F(omega=2e-12) - F(omega=0.5e-12)| / S = {fmt(jump)}, bound {bound:.1e}",
             "jump across omega = 1e-12 / S", float(jump), bound)

    # T2: omega = 1e-4 (no scattering source) against 1.0001e-4 (with it)
    rad = make_radiation("toon_lw", work)
    lo = run_case(rad, "toon_lw", dict(LW_CASES["w0=0"], ssa=1.0e-4))
    hi = run_case(rad, "toon_lw", dict(LW_CASES["w0=0"], ssa=1.0001e-4))
    S = planck_band(300.0)
    jump = float(max(np.max(np.abs(lo["up"] - hi["up"])), np.max(np.abs(lo["dn"] - hi["dn"]))) / S)
    smooth = 1e-8 * 10  # the physical change for d omega = 1e-8 is O(d omega), times a factor 10 for the slope
    print(f"[T2] CANDIDATE {'reproduced' if jump > smooth else 'not reproduced'}: the Toon longwave switch at "
          f"omega = 1e-4 (no scattering source at or below it) is a jump: max |F(omega=1.0001e-4) - F(omega=1e-4)| / S "
          f"= {fmt(jump)} against {smooth:.0e} for a continuous response (d omega = 1e-8)")

    # T3: the bottom (thickest) layer at dtau = 0.99e-6 against 1.01e-6
    fb = bottom_fraction()
    lo = run_case(rad, "toon_lw", dict(LW_CASES["nominal"], tau=[0.99e-6 / fb] * 3))
    hi = run_case(rad, "toon_lw", dict(LW_CASES["nominal"], tau=[1.01e-6 / fb] * 3))
    jump = float(max(np.max(np.abs(lo["up"] - hi["up"])), np.max(np.abs(lo["dn"] - hi["dn"]))) / S)
    bound = 0.02e-6 / fb * 10  # O(d tau) change of the column, times 10
    rep.line("T3", jump <= bound, "Toon longwave linear-in-tau Planck switch at dtau = 1e-6 is continuous",
             f"max |F(dtau=1.01e-6) - F(dtau=0.99e-6)| / S = {fmt(jump)}, bound {bound:.0e}",
             "jump across dtau = 1e-6 / S", jump, bound)

    # T4: mu0 swept through the resonance lam mu0 = 1 of a single-wave layer; the response must stay smooth
    rad = make_radiation("toon_sw", work)
    w0, g = 0.9, 0.5
    # lam of the delta-Eddington scaled layer (toon_mckay89_shortwave_impl.h), quarter-step mirror
    w0s = (1 - g * g) * w0 / (1 - w0 * g * g)
    hg = g / (1 + g)
    g1 = math.sqrt(3) / 2 * (2 - w0s * (1 + hg))
    g2 = math.sqrt(3) / 2 * w0s * (1 - hg)
    lam = math.sqrt(g1 * g1 - g2 * g2)
    mu_res = 1.0 / lam
    offs = [-1e-4, -1e-6, -1e-8, -1e-9, 0.0, 1e-9, 1e-8, 1e-6, 1e-4]
    vals = []
    for o in offs:
        r = run_case(rad, "toon_sw", dict(tau=[1.0, 1.0, 1.0], ssa=w0, g=g, albedo=0.3, mu0=mu_res * (1 + o)))
        vals.append(r["up"][-1] / (r["mu0"] * FBEAM))
    vals = np.array(vals)
    # second difference against the linear interpolation of the two outer neighbours at 1e-6
    lin = np.interp(offs, [offs[2 - 1], offs[-2]], [vals[1], vals[-2]])
    dev = float(np.max(np.abs(vals[2:-2] - lin[2:-2])))
    bound = 1e-6  # the linear model is exact to O(d mu^2) = 1e-12 there; sqrt(eps) = 1.5e-8 is the shift's own size
    rep.line("T4", dev <= bound and np.all(np.isfinite(vals)),
             "Toon shortwave resonance lam mu0 = 1 is crossed smoothly",
             f"max |R(mu0) - linear| over |d mu0 / mu0| <= 1e-8 = {fmt(dev)}, bound {bound:.0e}; "
             f"lam = {lam:.6f}, R = TOA reflectance", "deviation from linear across resonance", dev, bound)


if __name__ == "__main__":
    sys.exit(main())
