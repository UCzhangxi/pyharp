"""ch09: batching and CPU/CUDA agreement of Toon89 and of DISORT through pyharp, for the installed pydisort.

1. Toon shortwave and thermal: one batched call (3 wavelengths x 64 columns x 40 layers) against a loop of
   single-column calls and against a loop of single-wavelength calls, in float64 and float32.
2. Toon: CUDA against CPU, float64 and float32; on CUDA, the batch against single-column calls.
3. DISORT through pyharp (pyharp.disort_config + pydisort.Disort; 32 columns x 20 layers, columns 0-3 with
   single-scattering albedo 1), 4, 8, 16 and 32 streams: batch against single-column calls on the CPU, and CUDA
   against CPU, float64 and float32; and DISORT inside pyharp.RadiationBand (tests/rayleigh_test.yaml of the
   pyharp tree at the pin, 8 streams, 4 columns), CUDA against CPU.
4. Writes the support-matrix cells of this pydisort version (--data DIR) for check_ch09_matrix.py.

Metric: nd = max |F_a - F_b| / max |F_b| over every entry. Tolerances, each with its reason:
  batch vs loop    float64 1e-14, float32 1e-6: the same per-column code on the same device, so only a different
                   reduction order could differ; none is expected.
  CUDA vs CPU      float64 1e-12: the same per-column code; contraction to fused multiply-add and the device's
                   exp/log differ by a few roundings, amplified by the tridiagonal or eigen solve.
                   float32: 2 x the solver's own float32 floor (nd of CPU float32 against CPU float64), at least
                   1e-5, because a float32 result cannot be held to better than float32 allows.
  DISORT, omega=1  float64 1e-9: cdisort replaces omega = 1 by 1 - 100 eps_mach, an ill-conditioned problem
                   whose round-off is amplified; columns with omega < 1 keep 1e-12.
Candidate defects the ch09 text records are printed EXPECTED-FAIL when they exceed the tolerance (and FAIL if
they ever pass a check marked as a defect); see the ch09 Limits layers.

Run: PYHARP_WT=<pyharp source tree at the pin> python3 check_ch09_batch_device.py [--data DIR]  (about 1 min).
Exit status: the number of FAIL lines.
"""

import argparse
import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch09_common as C  # noqa: E402
import pyharp  # noqa: E402
import pydisort  # noqa: E402

WLO = [500.0, 1000.0, 1500.0]
WHI = [1000.0, 1500.0, 2000.0]
TOL = {"batch64": 1e-14, "batch32": 1e-6, "dev64": 1e-12, "dev32": 1e-5, "dev64_cons": 1e-9}


def inputs(seed=1, ncol=64, nlyr=40, nwave=3, conservative=0):
    rng = np.random.default_rng(seed)
    x = {"tau": 10 ** rng.uniform(-3, 0.5, (nwave, ncol, nlyr)), "ssa": rng.uniform(0.0, 0.99, (nwave, ncol, nlyr)),
         "g": rng.uniform(0.0, 0.85, (nwave, ncol, nlyr)), "mu0": rng.uniform(0.1, 1.0, ncol),
         "alb": rng.uniform(0.0, 0.5, (nwave, ncol)), "fbeam": rng.uniform(0.5, 2.0, (nwave, ncol)),
         "temf": np.linspace(300.0, 180.0, nlyr + 1)[None, :] + rng.uniform(-5, 5, (ncol, nlyr + 1))}
    if conservative:
        x["ssa"][:, :conservative, :] = 1.0
    return x


# ---------------------------------------------------------------------------------------------------- Toon
def toon(x, lw, dtype, device, sl=slice(None), ws=slice(None)):
    op = pyharp.ToonMcKay89Options()
    op.wave_lower(list(np.array(WLO)[ws]))
    op.wave_upper(list(np.array(WHI)[ws]))
    if lw:
        op.flags("planck,hard_surface")
    m = pyharp.ToonMcKay89(op)
    prop = np.stack([x["tau"], x["ssa"], x["g"]], -1)[ws][:, sl]
    if lw:
        return m(C.t(prop, dtype, device), temf=C.t(x["temf"][sl], dtype, device),
                 albedo=C.t(x["alb"][ws][:, sl], dtype, device))
    return m(C.t(prop, dtype, device), fbeam=C.t(x["fbeam"][ws][:, sl], dtype, device),
             umu0=C.t(x["mu0"][sl], dtype, device), albedo=C.t(x["alb"][ws][:, sl], dtype, device))


def toon_checks(ck, cells, cuda):
    x = inputs()
    ncol, nwave = x["mu0"].size, x["tau"].shape[0]
    for lw, name in [(False, "Toon SW"), (True, "Toon LW")]:
        for dn, dt in C.DTYPES.items():
            ref = toon(x, lw, dt, "cpu")
            cells[f"{name}|forward {dn}"] = ["pass" if bool(torch.isfinite(ref).all()) else "fail", "finite"]
            loop = torch.cat([toon(x, lw, dt, "cpu", sl=slice(i, i + 1)) for i in range(ncol)], dim=1)
            d1 = C.nd(ref, loop)
            ok1 = ck.check(f"{name} {dn} batch vs per-column loop, CPU (bitwise-equal fraction "
                           f"{C.bitwise(ref, loop):.4f})", d1, TOL["batch" + dn[1:]])
            wl = torch.cat([toon(x, lw, dt, "cpu", ws=slice(i, i + 1)) for i in range(nwave)], dim=0)
            d2 = C.nd(ref, wl)
            ok2 = ck.check(f"{name} {dn} batch vs per-wavelength loop, CPU", d2, TOL["batch" + dn[1:]])
            cells[f"{name}|batch {dn}"] = ["pass" if ok1 and ok2 else "fail", f"{max(d1, d2):.1e}"]
            if not cuda:
                cells[f"{name}|CUDA {dn}"] = ["not run", "no CUDA device"]
                continue
            gpu = C.attempt(lambda: toon(x, lw, dt, "cuda"))
            if isinstance(gpu, str):
                ck.unsupported(f"{name} {dn} CUDA", gpu)
                cells[f"{name}|CUDA {dn}"] = ["unsupported", gpu]
                continue
            tol = TOL["dev64"]
            if dn == "f32":
                floor = C.nd(ref, toon(x, lw, torch.float64, "cpu"))
                tol = max(TOL["dev32"], 2 * floor)
                ck.info(f"{name} float32 floor, CPU float32 vs CPU float64", f"{floor:.3e} -> tolerance {tol:.2e}")
            d = C.nd(gpu, ref)
            ok = ck.check(f"{name} {dn} CUDA vs CPU", d, tol)
            gl = torch.cat([toon(x, lw, dt, "cuda", sl=slice(i, i + 1)) for i in range(0, ncol, 8)], dim=1)
            ck.check(f"{name} {dn} CUDA batch vs single-column calls (8 columns)", C.nd(gpu[:, ::8], gl),
                     TOL["batch" + dn[1:]])
            cells[f"{name}|CUDA {dn}"] = ["pass" if ok else "fail", f"{d:.1e}"]


# -------------------------------------------------------------------------------------------------- DISORT
def disort(x, lw, nstr, dtype, device, sl=slice(None)):
    tau, ssa, g = x["tau"][:, sl], x["ssa"][:, sl], x["g"][:, sl]
    nwave, ncol, nlyr = tau.shape
    op = pydisort.DisortOptions()
    op.upward(True)
    op.flags("lamber,quiet,onlyfl" + (",planck" if lw else ""))
    if lw:
        op.wave_lower(WLO)
        op.wave_upper(WHI)
    pyharp.disort_config(op, nstr, nlyr, ncol, nwave)
    ds = pydisort.Disort(op)
    prop = np.concatenate([tau[..., None], ssa[..., None], C.hg_moments(g, nstr)], -1)
    if lw:
        return ds(C.t(prop, dtype, device), temf=C.t(x["temf"][sl], dtype, device),
                  albedo=C.t(x["alb"][:, sl], dtype, device), temis=C.t(np.zeros((nwave, ncol)), dtype, device),
                  btemp=C.t(x["temf"][sl, 0], dtype, device), ttemp=C.t(np.zeros(ncol), dtype, device))
    return ds(C.t(prop, dtype, device), fbeam=C.t(x["fbeam"][:, sl], dtype, device),
              umu0=C.t(x["mu0"][sl], dtype, device), albedo=C.t(x["alb"][:, sl], dtype, device))


def judged(ck, label, value, tol, defect):
    """A plain check, or, where the text records a candidate defect, EXPECTED-FAIL when the defect shows."""
    if defect and value > tol:
        return ck.expect_fail(label, value, tol) and False
    return ck.check(label, value, tol)


def disort_checks(ck, cells, cuda):
    x = inputs(ncol=32, nlyr=20, conservative=4)
    for lw, name in [(False, "DISORT SW"), (True, "DISORT LW")]:
        for dn, dt in C.DTYPES.items():
            per, ok_b, worst_b, msg = {}, True, 0.0, ""
            for nstr in [4, 8, 16, 32]:
                ref = disort(x, lw, nstr, dt, "cpu")
                cells[f"{name}|forward {dn}"] = ["pass" if bool(torch.isfinite(ref).all()) else "fail", "finite"]
                if nstr in (4, 16):
                    loop = torch.cat([disort(x, lw, nstr, dt, "cpu", sl=slice(i, i + 1)) for i in range(32)], dim=1)
                    d = C.nd(ref, loop)
                    ok_b &= ck.check(f"{name} {dn} nstr={nstr} batch vs per-column, CPU", d, TOL["batch" + dn[1:]])
                    worst_b = max(worst_b, d)
                if not cuda:
                    continue
                gpu = C.attempt(lambda: disort(x, lw, nstr, dt, "cuda"))
                if isinstance(gpu, str):
                    ck.unsupported(f"{name} {dn} nstr={nstr} CUDA", gpu)
                    msg = gpu
                    continue
                den = ref.double().abs().max().item()
                dif = (gpu.double().cpu() - ref.double()).abs()
                d_nc, d_c = dif[:, 4:].max().item() / den, dif[:, :4].max().item() / den
                if dn == "f32":
                    floor = C.nd(ref, disort(x, lw, nstr, torch.float64, "cpu"))
                    tol_nc = tol_c = max(TOL["dev32"], 2 * floor)
                else:
                    tol_nc, tol_c = TOL["dev64"], TOL["dev64_cons"]
                a1 = judged(ck, f"{name} {dn} nstr={nstr} CUDA vs CPU, omega<1 columns", d_nc, tol_nc, nstr == 8)
                a2 = judged(ck, f"{name} {dn} nstr={nstr} CUDA vs CPU, omega=1 columns", d_c, tol_c,
                            nstr == 8 or (lw and dn == "f64"))
                per[nstr] = (a1 and a2, d_nc, d_c)
            cells[f"{name}|batch {dn}"] = ["pass" if ok_b else "fail", f"{worst_b:.1e}"]
            if not cuda:
                cells[f"{name}|CUDA {dn}"] = ["not run", "no CUDA device"]
            elif not per:
                cells[f"{name}|CUDA {dn}"] = ["unsupported", msg]
            else:
                bad = [n for n, r in per.items() if not r[0]]
                txt = "; ".join(f"{n}: {r[1]:.1e}/{r[2]:.1e}" for n, r in per.items())
                cells[f"{name}|CUDA {dn}"] = ["fail" if bad else "pass",
                                              f"omega<1/omega=1 by nstr {txt}" + (f"; fails at {bad}" if bad else "")]


def band_checks(ck, cells, cuda):
    wt = os.environ.get("PYHARP_WT")
    if not wt:
        ck.check("PYHARP_WT is set (the pyharp source tree at the pin, for tests/rayleigh_test.yaml)", 1.0, 0.0)
        return
    yml = os.path.join(wt, "tests", "rayleigh_test.yaml")

    def run(device, dtype):
        band = pyharp.RadiationOptions.from_yaml(yml).bands()[0]
        band.wavenumber([20000.0])
        band.weight([1.0])
        band.set_wave_lower([19999.5])
        band.set_wave_upper([20000.5])
        band.ncol(4)
        band.nlyr(2)
        pyharp.disort_config(band.disort(), 8, 2, 4, 1)
        rb = pyharp.RadiationBand(band)
        if device == "cuda":
            rb.cuda()
        if dtype == torch.float32:
            rb.float()
        kw = dict(dtype=dtype, device=device)
        bc = {"shortwave/fbeam": torch.ones((1, 4), **kw), "shortwave/umu0": torch.tensor([0.2, 0.5, 0.8, 1.0], **kw),
              "shortwave/albedo": torch.full((1, 4), 0.3, **kw)}
        return rb.forward(torch.full((4, 2, 1), 1.0e3, **kw), torch.full((2,), 1.0e3, **kw), bc,
                          {"temp": torch.full((4, 2), 300.0, **kw)})
    for dn, dt in C.DTYPES.items():
        ref = run("cpu", dt)
        cells[f"RadiationBand DISORT|forward {dn}"] = ["pass" if bool(torch.isfinite(ref).all()) else "fail",
                                                       f"shape {tuple(ref.shape)}"]
        if not cuda:
            continue
        gpu = C.attempt(lambda: run("cuda", dt))
        if isinstance(gpu, str):
            ck.unsupported(f"RadiationBand(DISORT) {dn} CUDA", gpu)
            cells[f"RadiationBand DISORT|CUDA {dn}"] = ["unsupported", gpu]
            continue
        # the band clamps omega to 1 - 1e-12 (float64) or 1 - 1e-6 (float32): conservative-column tolerance
        tol = TOL["dev64_cons"] if dn == "f64" else max(TOL["dev32"], 2 * C.nd(ref, run("cpu", torch.float64)))
        d = C.nd(gpu, ref)
        ok = ck.check(f"RadiationBand(DISORT) {dn} CUDA vs CPU", d, tol)
        cells[f"RadiationBand DISORT|CUDA {dn}"] = ["pass" if ok else "fail", f"{d:.1e}"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    a = ap.parse_args()
    print(C.version_line())
    print(C.env_line())
    cuda = torch.cuda.is_available()
    ck = C.Checker()
    cells = {}
    toon_checks(ck, cells, cuda)
    disort_checks(ck, cells, cuda)
    band_checks(ck, cells, cuda)
    for k, (st, val) in cells.items():
        ck.info(f"cell {k}", f"{st} ({val})")
    if a.data:
        os.makedirs(a.data, exist_ok=True)
        with open(os.path.join(a.data, f"cells_pydisort_{pydisort.__version__}.json"), "w") as f:
            json.dump({"pydisort": pydisort.__version__, "torch": torch.__version__,
                       "gpu": torch.cuda.get_device_name(0) if cuda else None, "cells": cells}, f, indent=1)
    sys.exit(ck.done("check_ch09_batch_device"))


if __name__ == "__main__":
    main()
