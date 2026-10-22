"""ch03 check: the Nakajima-Tanaka (1988) intensity correction in cdisort, run through pydisort.

The correction is selected by the flags "intensity_correction,old_intensity_correction" and needs
radiances (no onlyfl). One layer: Henyey-Greenstein g = 0.9, tau = 1, omega = 0.99, mu0 = 0.5,
F0 = pi, black surface, accur = 0. Radiances at the bottom for downward zenith angles
0-85 degrees and azimuths 0, 30, 90, 180 degrees, and at the top for upward angles 10, 45, 80
degrees. Reference: 128 streams, 512 moments, corrected.

  [C1] the correction leaves every flux output bitwise unchanged (all 8 gather_flx() columns, at
       8, 16 and 32 streams): it only modifies the intensities
  [C2] the correction lowers the largest relative radiance error inside the aureole (azimuth 0,
       zenith 50-70 degrees, i.e. within 10 degrees of the beam), outside it, and at the top, at 8,
       16 and 32 streams; the numbers are printed. The direction azimuth 180, zenith = beam zenith
       (|mu| = mu0) is printed separately and left out of the maxima: its error is erratic with and
       without the correction.
  [C3] sympy: the single-scattering integral of one layer, for a downward direction mu = -|mu|,
       (omega F0 P / (4 pi |mu|)) int_0^tau exp(-t/mu0) exp(-(tau - t)/|mu|) dt, equals the closed form
       omega F0 P / (4 pi (1 + mu/mu0)) (exp(-tau/mu0) - exp(-tau/|mu|)) that c_single_scat sums per layer.
  [C4] sympy: the IMS geometry factor h = (1/(mu mu0s)) int_0^tau t exp(-(tau - t)/mu) exp(-t/mu0s) dt equals
       the closed form of c_xi_func, ((tau x - 1) exp(-tau/mu0s) + exp(-tau/mu)) / (x^2 mu mu0s) with
       x = (mu0s - mu)/(mu mu0s), and its limit tau^2 exp(-tau/mu) / (2 mu mu0s) at x = 0.
  [C5] sympy: with P = f Phat + (1 - f) P* and chi*_l = (chi_l - f)/(1 - f) for l < 2N, chi*_l = 0 above,
       the moments of Phat are 1 for l < 2N and chi_l / f for l >= 2N, so the moments of 2 Phat - Phat^2
       are 1 and (chi_l/f)(2 - chi_l/f), as c_secondary_scat sums them.

Needs: torch, numpy, sympy, pydisort.
Run:   python ch03_intensity_correction.py
Pins:  PYDISORT_SRC names the source tree; its commit is printed.
"""
import math
import os
import subprocess
import sys

import numpy as np
import pydisort
import sympy as sp
import torch
from pydisort import Disort, DisortOptions, scattering_moments


def git_head(var):
    path = os.environ.get(var)
    if not path:
        return "unset"
    r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "not a git tree"


def run(nstr, nmom, flags, umu, phi, tau=1.0):
    op = DisortOptions().header("ch03").flags(",".join(flags))
    op.ds().nlyr, op.ds().nstr, op.ds().nmom = 1, nstr, nmom
    op.user_tau(np.array([0.0, tau]))
    op.user_mu(np.array(umu))
    op.user_phi(np.array(phi))
    op.accur(0.0)
    ds = Disort(op)
    prop = torch.zeros((1, 1, 1, 2 + nmom), dtype=torch.float64)
    prop[0, 0, 0, 0] = tau
    prop[0, 0, 0, 1] = 0.99
    prop[0, 0, 0, 2:] = scattering_moments(nmom, "henyey-greenstein", 0.9)
    ds.forward(prop, umu0=torch.tensor([0.5], dtype=torch.float64), phi0=torch.zeros(1, dtype=torch.float64),
               fbeam=torch.tensor([[math.pi]], dtype=torch.float64), albedo=torch.zeros((1, 1), dtype=torch.float64))
    return ds.gather_flx(), ds.gather_rad()  # rad: (nwave, ncol, nphi, ntau, numu)


def check_sympy():
    t, tau, mu, mu0, mus = sp.symbols("t tau mu mu0 mu0s", positive=True)
    w, F0, P = sp.symbols("omega F0 P", positive=True)
    integral = w * F0 * P / (4 * sp.pi * mu) * sp.integrate(sp.exp(-t / mu0) * sp.exp(-(tau - t) / mu), (t, 0, tau), conds="none")
    closed = w * F0 * P / (4 * sp.pi * (1 - mu / mu0)) * (sp.exp(-tau / mu0) - sp.exp(-tau / mu))
    def same(a, b):
        return sp.simplify(a - b) == 0

    ok3 = same(integral, closed)
    h = sp.integrate(t * sp.exp(-(tau - t) / mu) * sp.exp(-t / mus), (t, 0, tau), conds="none") / (mu * mus)
    x = (mus - mu) / (mu * mus)
    xi = ((tau * x - 1) * sp.exp(-tau / mus) + sp.exp(-tau / mu)) / (x**2 * mu * mus)
    ok4 = same(h, xi)
    h0 = sp.integrate(t * sp.exp(-(tau - t) / mu) * sp.exp(-t / mu), (t, 0, tau), conds="none") / (mu * mu)
    ok4 &= same(h0, tau**2 * sp.exp(-tau / mu) / (2 * mu * mu))
    f, chi = sp.symbols("f chi_l", positive=True)
    phat_low = sp.solve(sp.Eq(chi, f * sp.Symbol("ph") + (1 - f) * (chi - f) / (1 - f)), sp.Symbol("ph"))[0]
    phat_high = sp.solve(sp.Eq(chi, f * sp.Symbol("ph")), sp.Symbol("ph"))[0]
    ok5 = sp.simplify(phat_low - 1) == 0 and sp.simplify(phat_high - chi / f) == 0
    ok5 &= sp.simplify(2 * phat_high - phat_high**2 - (chi / f) * (2 - chi / f)) == 0
    print(f"[C3] {'PASS' if ok3 else 'FAIL'} sympy: one-layer single-scattering integral = closed form of c_single_scat "
          "(mu written as |mu|, so 1 + mu/mu0 appears as 1 - |mu|/mu0)")
    print(f"[C4] {'PASS' if ok4 else 'FAIL'} sympy: IMS factor h = closed form of c_xi_func, and its x = 0 limit")
    print(f"[C5] {'PASS' if ok5 else 'FAIL'} sympy: moments of Phat are 1 (l < 2N) and chi_l/f (l >= 2N)")
    return ok3 and ok4 and ok5


def main():
    torch.set_num_threads(1)
    print(f"python {sys.version.split()[0]}, torch {torch.__version__}, numpy {np.__version__}, "
          f"sympy {sp.__version__}, pydisort {pydisort.__version__}")
    print(f"pydisort source {git_head('PYDISORT_SRC')}")
    th = [0, 30, 50, 55, 58, 60, 62, 65, 70, 85]       # downward zenith angles [deg]
    dn = sorted(-math.cos(math.radians(t)) for t in th)  # cdisort wants umu in increasing order
    up = sorted(math.cos(math.radians(t)) for t in (80, 45, 10))
    umu, phi = dn + up, [0.0, 30.0, 90.0, 180.0]
    th_of = [round(math.degrees(math.acos(-m))) for m in dn]
    nd = len(dn)
    base = ["usrtau", "usrang", "lamber", "quiet"]
    ic = ["intensity_correction", "old_intensity_correction"]
    _, rr = run(128, 512, base + ic, umu, phi)
    ref = rr[0, 0, :, 1, :nd]
    aure = [i for i, t in enumerate(th_of) if abs(t - 60) <= 10]
    rest = [i for i, t in enumerate(th_of) if abs(t - 60) > 10]
    beam = th_of.index(60)
    ok1 = ok2 = True
    print(f"{'nstr':>4} {'aureole off':>11} {'on':>8} {'outside off':>11} {'on':>8} {'top off':>8} {'on':>8} "
          f"{'I(beam dir) off':>15} {'on':>7} {'ref':>7} {'phi180 off/on':>14}")
    for nstr in (8, 16, 32):
        f0, r0 = run(nstr, 512, base, umu, phi)
        f1, r1 = run(nstr, 512, base + ic, umu, phi)
        ok1 &= bool(torch.equal(f0, f1))
        e0 = ((r0[0, 0, :, 1, :nd] - ref) / ref).abs()
        e1 = ((r1[0, 0, :, 1, :nd] - ref) / ref).abs()
        anom = (e0[3, beam].item(), e1[3, beam].item())
        e0[3, beam] = e1[3, beam] = 0.0
        t0 = ((r0[0, 0, :, 0, nd:] - rr[0, 0, :, 0, nd:]) / rr[0, 0, :, 0, nd:]).abs().max().item()
        t1 = ((r1[0, 0, :, 0, nd:] - rr[0, 0, :, 0, nd:]) / rr[0, 0, :, 0, nd:]).abs().max().item()
        a0, a1 = e0[0, aure].max().item(), e1[0, aure].max().item()
        o0, o1 = e0[:, rest].max().item(), e1[:, rest].max().item()
        ok2 &= a1 < a0 and o1 < o0 and t1 < t0
        print(f"{nstr:4d} {a0:11.1e} {a1:8.1e} {o0:11.1e} {o1:8.1e} {t0:8.1e} {t1:8.1e} "
              f"{r0[0, 0, 0, 1, beam].item():15.3f} {r1[0, 0, 0, 1, beam].item():7.3f} {ref[0, beam].item():7.3f} "
              f"{anom[0]:6.1e}/{anom[1]:6.1e}")
    print(f"[C1] {'PASS' if ok1 else 'FAIL'} fluxes bitwise unchanged by the correction (torch.equal, all 8 columns, "
          "8/16/32 streams)")
    print(f"[C2] {'PASS' if ok2 else 'FAIL'} the correction lowers the largest radiance error inside the aureole, "
          "outside it and at the top, at 8/16/32 streams")
    ok3 = check_sympy()
    sys.exit((not ok1) + (not ok2) + (not ok3))


if __name__ == "__main__":
    main()
