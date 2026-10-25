"""ch06 check: liquid-water droplets, Lorenz-Mie (`type: water-liquid-mie`), against an independent reference.

The module is pyharp.opacity.MieWaterLiquid (src/opacity/water_liquid_mie.cpp and water_liquid_mie_impl.h). Its
output is (nwave, ncol, nlyr, 2 + nmom): extinction k [1/m], single-scattering albedo omega and the
Henyey-Greenstein moments g^l. The efficiencies are recovered from k with eq-ch06-mie-k:
Q_ext = k * 4 rho r / (3 c M).

The reference, `mie_reference`, evaluates the Lorenz-Mie coefficients a_n, b_n of Bohren & Huffman (1983,
eq. 4.53) from Riccati-Bessel functions built from mpmath Bessel functions at 40 digits (no recurrence, no
continued fraction), and Q_ext, Q_sca and g from eqs. 4.61, 4.62 and 4.74, with 30 more terms than the code keeps.

  [C1] Q_ext, Q_sca, g (eq-ch06-mie-q, eq-ch06-mie-g) of the module against the reference, for 9 cases
       (m from 0.8 - 0.1i to 1.5 - 0.5i, x from 0.1 to 100, both directions of the D_n recurrence): Q_ext and
       Q_sca to 1e-9 relative, g to 1e-12 absolute. 1e-9 is 1000 times the stopping tolerance 1e-12 of the
       continued fraction that starts the downward recurrence, which the recurrence can amplify.
  [C2] Small droplets, x < 1e-3 (eq-ch06-mie-small): the module returns Q_sca = 8/3 x^4 |alpha|^2,
       Q_abs = -4 x Im(alpha), g = 0 with alpha = (m^2 - 1)/(m^2 + 2), to 1e-14 relative (a dozen roundings);
       at x = 9e-4 these differ from the reference by less than 1e-6 relative (the neglected terms are O(x^2)).
  [C3] Mass extinction (eq-ch06-mie-k): k equals c M 3 Q_ext / (4 rho r) with M of H2O from atomic weights
       (2 x 1.008 + 15.999 g/mol) and Q_ext from the reference, to 1e-9 relative (the tolerance of [C1]); doubling
       `water_density` halves k, and scaling r and the wavelength together by 3 divides k by 3, to 1e-15 relative.
  [C4] Albedo and moments: omega = Q_sca/Q_ext of the reference to 1e-9; the moments are g, g^2, g^3 to 1e-15
       relative; a cell with zero concentration returns k = 0, omega = 0 and zero moments, bitwise.
  [C5] Refractive index of water (eq-ch06-mie-nk): at 6 wavelengths between table points, the default n, k of the
       Segelstein table equal n linear and ln k linear in ln(wavelength) between the bracketing rows (numpy here),
       to 1e-13 relative (one log, one exp).
  [C6] Refusals: a wavelength outside 0.1-1000 um, re = 0, and only one of the two refractive-index overrides are
       refused, each with the message of MieWaterLiquidImpl::forward.
  [C7] CANDIDATE, small droplets with weak absorption: just above x = 1e-3 the full series loses Q_abs to
       cancellation and the clamp Q_ext >= Q_sca sets Q_ext = Q_sca. Printed: the relative error of Q_ext and the
       albedo of module and reference at x = 1.001e-3, 3e-3, 1e-2, 3e-2 for k = 1e-8 and 1e-6, m = 1.33 - ki.

With --data FILE the efficiencies of the module and the reference on a grid of x for three absorption indices are
written as JSON for the figure fig-ch06-mie-accuracy.

Needs torch, numpy, mpmath and a pyharp built from source at the pin of code_pin.yml (ch06_setup.sh).
Run:   python3 check_ch06_mie.py [--data FILE]   (any directory; exits with the number of failed claims)
"""
import argparse
import json
import os
import sys

import mpmath as mp
import numpy as np
import torch
from pyharp.opacity import MieWaterLiquid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch06_common as C  # noqa: E402

mp.mp.dps = 40
RHO = 997.0                         # kg/m^3, kWaterDensity of water_liquid_mie.cpp
M_H2O = (2 * 1.008 + 15.999) / 1e3  # kg/mol from standard atomic weights
R_UM = 1.0                          # droplet radius of the efficiency cases [um]

YAML = """
species:
  - {name: H2O(l), composition: {H: 2, O: 1}}
geometry: {cells: {nx1: 1}}
opacities:
  mie: {type: water-liquid-mie, species: ["H2O(l)"], nmom: NMOM}
bands:
  - {name: b, range: [1000., 2000.], opacities: [mie], solver: disort, nwave: 1, nstr: 4, flags: "lamber,quiet,onlyfl"}
"""


def module(nmom=3):
    return MieWaterLiquid(C.Config(YAML.replace("NMOM", str(nmom))).opacity("mie"))


def mie_reference(n, k, x, extra=30):
    """Bohren & Huffman (1983) eqs. 4.53, 4.61, 4.62, 4.74 with m = n + ik (their sign convention; Q and g do
    not depend on it), from mpmath Bessel functions. Returns Q_ext, Q_sca, g as floats."""
    m = mp.mpc(n, k)
    x = mp.mpf(x)
    z = m * x
    nmax = int(float(x) + 4 * float(x) ** (1 / 3) + extra)
    half = mp.mpf(1) / 2

    def psi(order, r):
        return mp.sqrt(mp.pi * r / 2) * mp.besselj(order + half, r)

    def chi(order, r):
        return -mp.sqrt(mp.pi * r / 2) * mp.bessely(order + half, r)

    a, b = [], []
    for j in range(1, nmax + 1):
        px, pxm, pz, pzm = psi(j, x), psi(j - 1, x), psi(j, z), psi(j - 1, z)
        xi, xim = px - 1j * chi(j, x), pxm - 1j * chi(j - 1, x)
        dpx, dpz, dxi = pxm - j * px / x, pzm - j * pz / z, xim - j * xi / x
        a.append((m * pz * dpx - px * dpz) / (m * pz * dxi - xi * dpz))
        b.append((pz * dpx - m * px * dpz) / (pz * dxi - m * xi * dpz))
    qe = 2 / x**2 * mp.fsum((2 * j + 1) * mp.re(a[j - 1] + b[j - 1]) for j in range(1, nmax + 1))
    qs = 2 / x**2 * mp.fsum((2 * j + 1) * (abs(a[j - 1]) ** 2 + abs(b[j - 1]) ** 2) for j in range(1, nmax + 1))
    s = mp.fsum(mp.mpf(j * (j + 2)) / (j + 1) * mp.re(a[j - 1] * mp.conj(a[j]) + b[j - 1] * mp.conj(b[j]))
                for j in range(1, nmax))
    s += mp.fsum(mp.mpf(2 * j + 1) / (j * (j + 1)) * mp.re(a[j - 1] * mp.conj(b[j - 1])) for j in range(1, nmax + 1))
    return float(qe), float(qs), float(4 / (x**2 * qs) * s)


def downward(n, k, x):
    """The branch test of mie_efficiency_device: True where D_n runs downward from Lentz's continued fraction."""
    return n < 1 or n > 10 or k > 10 or x * k >= 3.9 - 10.8 * n + 13.78 * n * n


def run(mod, n, k, wavelength, r=R_UM, conc=None, density=None):
    """Module output for one droplet radius and a list of wavelengths, with the refractive index overridden."""
    kw = {"wavelength": C.t(wavelength), "re": C.t(r), "refractive_index_real": C.t(n),
          "refractive_index_imag": C.t(k)}
    if density is not None:
        kw["water_density"] = C.t(density)
    c = C.t([[[1.0 / M_H2O if conc is None else conc]]])
    return mod.forward(c, kw)[:, 0, 0, :]


def efficiencies(mod, n, k, x):
    """Q_ext, Q_sca, g of the module at size parameter x (radius R_UM, unit mass concentration)."""
    out = run(mod, n, k, [2 * np.pi * R_UM / x])[0]
    qe = out[0].item() * 4 * RHO * R_UM * 1e-6 / 3
    return qe, out[1].item() * qe, out[2].item()


CASES = [(1.33, 1e-8, 1.0), (1.33, 1e-8, 10.0), (1.33, 1e-8, 100.0), (1.33, 0.01, 0.1), (1.33, 0.01, 5.0),
         (1.5, 0.5, 3.0), (1.33, 0.5, 40.0), (0.8, 0.1, 10.0), (1.2, 2.0, 20.0)]


def check_C1(mod):
    rows, worst_q, worst_g = [], 0.0, 0.0
    for n, k, x in CASES:
        ref, got = mie_reference(n, k, x), efficiencies(mod, n, k, x)
        eq = max(abs(got[0] / ref[0] - 1), abs(got[1] / ref[1] - 1))
        eg = abs(got[2] - ref[2])
        worst_q, worst_g = max(worst_q, eq), max(worst_g, eg)
        rows.append(f"m={n:g}-{k:g}i x={x:g} {'down' if downward(n, k, x) else 'up'}")
    ok = worst_q <= 1e-9 and worst_g <= 1e-12
    return C.report(1, ok, f"{len(CASES)} cases ({'; '.join(rows)}): Q_ext, Q_sca relative {C.bound(worst_q, 1e-9)}; "
                    f"g absolute {C.bound(worst_g, 1e-12)}")


def check_C2(mod):
    worst = 0.0
    for x in (1e-4, 5e-4, 9e-4):
        for n, k in ((1.33, 1e-8), (1.33, 0.01), (1.5, 0.5)):
            m = complex(n, -k)
            alpha = (m * m - 1) / (m * m + 2)
            qs = 8.0 / 3.0 * x**4 * abs(alpha) ** 2
            qe = qs + max(-4 * x * alpha.imag, 0.0)
            got = efficiencies(mod, n, k, x)
            worst = max(worst, abs(got[0] / qe - 1), abs(got[1] / qs - 1), abs(got[2]))
    ref = mie_reference(1.33, 0.01, 9e-4)
    got = efficiencies(mod, 1.33, 0.01, 9e-4)
    trunc = max(abs(got[0] / ref[0] - 1), abs(got[1] / ref[1] - 1))
    ok = worst <= 1e-14 and trunc <= 1e-6
    return C.report(2, ok, f"x = 1e-4, 5e-4, 9e-4, three m: module against the closed forms {C.bound(worst, 1e-14)}; "
                    f"x = 9e-4, m = 1.33 - 0.01i: closed forms against the reference {C.bound(trunc, 1e-6)}")


def check_C3(mod):
    n, k, x = 1.33, 0.01, 5.0
    lam = 2 * np.pi * R_UM / x
    ref = mie_reference(n, k, x)
    conc = 3.0
    got = run(mod, n, k, [lam], conc=conc)[0, 0].item()
    want = conc * M_H2O * 3 * ref[0] / (4 * RHO * R_UM * 1e-6)
    e1 = abs(got / want - 1)
    half = run(mod, n, k, [lam], conc=conc, density=2 * RHO)[0, 0].item()
    big = run(mod, n, k, [3 * lam], r=3 * R_UM, conc=conc)[0, 0].item()
    e2 = max(abs(half / got - 0.5) / 0.5, abs(big / got - 1 / 3) * 3)
    ok = e1 <= 1e-9 and e2 <= 1e-15
    return C.report(3, ok, f"k against c M 3 Q_ext / (4 rho r), M = 18.015 g/mol: {C.bound(e1, 1e-9)}; "
                    f"2 rho halves k and 3 r at fixed x divides k by 3: {C.bound(e2, 1e-15)}")


def check_C4():
    mod = module(nmom=3)
    n, k, x = 1.33, 0.01, 5.0
    ref = mie_reference(n, k, x)
    out = run(mod, n, k, [2 * np.pi * R_UM / x])[0]
    e_omega = abs(out[1].item() / (ref[1] / ref[0]) - 1)
    g = out[2].item()
    e_mom = max(abs(out[3].item() / g**2 - 1), abs(out[4].item() / g**3 - 1))
    zero = run(mod, n, k, [0.5, 2.0], conc=0.0)
    ok = e_omega <= 1e-9 and e_mom <= 1e-15 and bool(torch.all(zero == 0))
    return C.report(4, ok, f"omega against Q_sca/Q_ext {C.bound(e_omega, 1e-9)}; moments against g, g^2, g^3 "
                    f"{C.bound(e_mom, 1e-15)}; zero concentration gives all zeros: {bool(torch.all(zero == 0))}")


def check_C5():
    mod = module()
    from pyharp import find_resource
    table = np.loadtxt(find_resource("opacity/cloud/segelstein_water.txt"))
    w, nn, kk = table[:, 0], table[:, 1], table[:, 2]
    probes = [0.3, 0.55, 2.9, 6.1, 11.0, 350.0]
    j = np.searchsorted(w, probes, side="right")
    f = (np.log(probes) - np.log(w[j - 1])) / (np.log(w[j]) - np.log(w[j - 1]))
    n_ref = nn[j - 1] + f * (nn[j] - nn[j - 1])
    k_ref = np.exp(np.log(kk[j - 1]) + f * (np.log(kk[j]) - np.log(kk[j - 1])))
    kw = {"wavelength": C.t(probes), "re": C.t(5.0)}
    c = C.t([[[1.0 / M_H2O]]])
    default = mod.forward(c, kw)
    over = mod.forward(c, dict(kw, refractive_index_real=C.t(n_ref), refractive_index_imag=C.t(k_ref)))
    err = float(torch.max(torch.abs(default / torch.where(over == 0, 1.0, over) - torch.where(over == 0, 0.0, 1.0))))
    return C.report(5, err <= 1e-13, f"{len(table)} table rows, {probes[0]}-{probes[-1]} um: wavelengths "
                    f"{probes} um, default against the numpy interpolation {C.bound(err, 1e-13)}")


def check_C6():
    mod = module()
    c = C.t([[[1.0]]])
    msgs = [C.refusal(lambda: mod.forward(c, {"wavelength": C.t([1500.0]), "re": C.t(5.0)})),
            C.refusal(lambda: mod.forward(c, {"wavelength": C.t([1.0]), "re": C.t(0.0)})),
            C.refusal(lambda: mod.forward(c, {"wavelength": C.t([1.0]), "re": C.t(5.0),
                                              "refractive_index_real": C.t(1.33)}))]
    want = ["supports wavelength 0.1--1000 um", "re must be finite and positive",
            "Provide both refractive_index_real and refractive_index_imag"]
    ok = all(m is not None and s in m for m, s in zip(msgs, want))
    return C.report(6, ok, "refused: " + "; ".join(f'"{m}"' for m in msgs))


def check_C7(mod):
    rows = []
    for k in (1e-8, 1e-6):
        for x in (1.001e-3, 3e-3, 1e-2, 3e-2):
            ref, got = mie_reference(1.33, k, x), efficiencies(mod, 1.33, k, x)
            rows.append(f"k={k:g} x={x:g}: Q_ext rel err {abs(got[0] / ref[0] - 1):.1e}, omega {got[1] / got[0]:.3f} "
                        f"(reference {ref[1] / ref[0]:.3f})")
    return C.report(7, True, "small droplets, weak absorption, m = 1.33 - ki: " + "; ".join(rows), kind="CANDIDATE")


def write_data(path, mod):
    xs = np.geomspace(1e-2, 100.0, 33)
    out = {"x": xs.round(12).tolist(), "cases": []}
    for k in (1e-8, 1e-4, 0.1):
        rows = [(mie_reference(1.33, k, x), efficiencies(mod, 1.33, k, x)) for x in xs]
        out["cases"].append({"n": 1.33, "k": k,
                             "qext_ref": [float(f"{r[0]:.10e}") for r, _ in rows],
                             "qext_rel_err": [float(f"{abs(c[0] / r[0] - 1):.3e}") for r, c in rows],
                             "g_ref": [float(f"{r[2]:.10e}") for r, _ in rows]})
    with open(path, "w") as f:
        json.dump(out, f, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    a = ap.parse_args()
    C.header()
    mod = module()
    oks = [check_C1(mod), check_C2(mod), check_C3(mod), check_C4(), check_C5(), check_C6(), check_C7(mod)]
    if a.data:
        write_data(a.data, mod)
    nfail = oks.count(False)
    print(f"check_ch06_mie: {len(oks) - nfail} of {len(oks)} claims pass")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
