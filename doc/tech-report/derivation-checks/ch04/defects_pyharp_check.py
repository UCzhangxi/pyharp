#!/usr/bin/env python3
"""Chapter 4: reproduce the pyharp defects P11 and P12 (DEFECTS.md) on the pinned pyharp, with the reviewer's inputs.

Each check PASSES while pyharp at the pin of code_pin.yml shows the defect and FAILS once the defect is fixed, so a
fix in pyharp turns this script red and the Limits text of chapter 4 has to be updated with it.

  [C1] P11, switch hole of the band Planck function. T_SWITCH = 300 * 1.438786 / 1.5, so the band edge 300 cm-1 has
       v = c2 nu / T = 1.5 exactly and falls in neither series. An isothermal column (4 layers of dtau 1, `planck`,
       `hard_surface`, top_emission_flag 1, band 300-600 cm-1) then returns F+(TOA) = -2.35988e2 W m-2. The check
       asserts that value (relative 1e-4) and prints the neighbour T(1 + 1e-12) and pi * quadrature for comparison.
  [C2] P12, exact longwave resonance in a thick layer. One layer of dtau = 20 (lambda dtau = 35.6 >= 35, so the
       sweep uses the plain quotient), g = 0, w = 1 - 1/(4 u^2) with u = uarr[2] = 0.5620251898, so lambda u = 1;
       `planck`, `hard_surface`, albedo 0.2, temf (600, 300) K, band 1-1e5 cm-1 (the set-up of the pinned gtest
       DeviceTest.longwave_resonance_is_continuous with dtau 20 instead of 1). The check asserts that some fluxes are
       not finite while the neighbours w(1 -+ 1e-7) are finite with F+(TOA) agreeing within 1e-6 relative; it also
       prints the largest relative difference of the neighbours over all channels (the surface and midpoint channels
       lose accuracy next to the resonance).

How to run: `bash derivation-checks/ch04_run.sh <env>` (environment from `derivation-checks/ch04/setup_env.sh`), or
`PYHARP_WT=<pyharp tree> python3 defects_pyharp_check.py`. Exit status: the number of failed checks.
"""
import math
import os
import platform
import subprocess
import sys

import mpmath as mp
import torch
import pyharp

torch.set_default_dtype(torch.float64)
torch.set_num_threads(1)

T_SWITCH = 300.0 * 1.438786 / 1.5          # v = 1.5 at the band edge 300 cm-1
P11_EXPECTED = -2.35988e2                    # F+(TOA) [W m-2] that pyharp returns at T_SWITCH (defect)
U_RES = 0.5620251898                         # uarr[2] of toon_mckay89_longwave
W_RES = 1.0 - 1.0 / (4.0 * U_RES * U_RES)    # lambda * U_RES = 1 for g = 0
DTAU_P12 = 20.0                              # lambda * dtau = 35.6 >= 35: the plain-quotient branch

H, C, KB = 6.62607015e-34, 2.99792458e8, 1.380649e-23


def report(label, ok, text):
    print(f"[{label}] {'PASS' if ok else 'FAIL'} {text}")
    return bool(ok)


def isothermal_toa(T, wlo, whi):
    o = pyharp.ToonMcKay89Options()
    o.wave_lower([wlo])
    o.wave_upper([whi])
    o.flags("planck,hard_surface")
    o.top_emission_flag(1)
    prop = torch.zeros(1, 1, 4, 3)
    prop[..., 0] = 1.0
    f = pyharp.ToonMcKay89(o)(prop, temf=torch.full((1, 5), T), albedo=torch.zeros(1, 1))
    return f[0, 0, -1, 0].item()


def check_C1_planck_switch():
    T = T_SWITCH
    bnu = lambda nu: 2 * H * C ** 2 * (100 * nu) ** 3 / mp.expm1(H * C * 100 * nu / (KB * T)) * 100
    ref = math.pi * float(mp.quad(bnu, [300, 600]))
    at = isothermal_toa(T, 300.0, 600.0)
    near = isothermal_toa(T * (1 + 1e-12), 300.0, 600.0)
    ok = abs(at / P11_EXPECTED - 1) < 1e-4
    return report("C1", ok, f"P11 reproduced: T = {T!r} K, band 300-600 cm-1: F+(TOA) = {at:.6e} W m-2 (defective value "
                  f"{P11_EXPECTED:.5e}); at T(1+1e-12): {near:.6e}; pi * quadrature: {ref:.6e}")


def thick_resonant(w):
    o = pyharp.ToonMcKay89Options()
    o.wave_lower([1.0])
    o.wave_upper([1.0e5])
    o.flags("planck,hard_surface")
    prop = torch.zeros(1, 1, 1, 3)
    prop[..., 0] = DTAU_P12
    prop[..., 1] = w
    return pyharp.ToonMcKay89(o)(prop, temf=torch.tensor([600.0, 300.0]).view(1, 2),
                                 albedo=torch.full((1, 1), 0.2))[0, 0]


def check_C2_lw_resonance():
    lam = 2.0 * math.sqrt(1.0 - W_RES)
    exact = thick_resonant(W_RES)
    below = thick_resonant(W_RES * (1 - 1e-7))
    above = thick_resonant(W_RES * (1 + 1e-7))
    nonfinite = int((~torch.isfinite(exact)).sum().item())
    finite_nb = bool(torch.isfinite(below).all() and torch.isfinite(above).all())
    toa = abs(below[-1, 0].item() / above[-1, 0].item() - 1) if finite_nb else float("inf")
    nz = below.abs() > 0
    spread = ((below - above).abs()[nz] / below.abs()[nz]).max().item() if finite_nb else float("inf")
    ok = nonfinite > 0 and finite_nb and toa < 1e-6
    return report("C2", ok, f"P12 reproduced: dtau = {DTAU_P12}, lambda dtau = {lam * DTAU_P12:.1f}, lambda u - 1 = "
                  f"{lam * U_RES - 1:.1e}: {nonfinite} of {exact.numel()} outputs not finite, F+(TOA) = "
                  f"{exact[-1, 0].item()}; neighbours w(1 -+ 1e-7): F+(TOA) = {below[-1, 0].item():.6e}, "
                  f"{above[-1, 0].item():.6e} (relative difference {toa:.1e}; largest over all nonzero channels {spread:.1e})")


def main():
    import numpy
    wt = os.environ.get("PYHARP_WT")
    src = subprocess.run(["git", "-C", wt, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() \
        if wt else "not recorded (set PYHARP_WT to the pyharp source tree)"
    import pydisort
    print(f"versions: pyharp {pyharp.__version__}, torch {torch.__version__}, mpmath {mp.__version__}, "
          f"numpy {numpy.__version__}, Python {platform.python_version()}, pydisort {pydisort.__version__}")
    print(f"pyharp source {src}")
    print("device: CPU, precision: float64, threads: 1")
    oks = [check_C1_planck_switch(), check_C2_lw_resonance()]
    print(f"RESULT: {sum(oks)}/{len(oks)} defects reproduced")
    return len(oks) - sum(oks)


if __name__ == "__main__":
    sys.exit(main())
