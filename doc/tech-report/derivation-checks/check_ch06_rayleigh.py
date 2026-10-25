"""ch06 check: Rayleigh scattering opacity (`type: rayleigh`), against the formulas of the chapter.

The module is pyharp.opacity.Rayleigh (src/opacity/rayleigh.cpp, RayleighImpl::forward), built from a radiation
YAML. Its output is (nwave, ncol, nlyr, 2 + nmom): extinction k [1/m], single-scattering albedo, and the phase
moments chi_1 .. chi_nmom.

  [C1] H2 cross section (eq-ch06-rayleigh-sigma, eq-ch06-rayleigh-k): k / c_H2 equals the Dalgarno-Williams sum
       times N_A * 1e-4, with pyharp's N_A, on 41 wavenumbers from 1000 to 50000 cm^-1; to 1e-14 relative
       (three powers, two sums and two products, each rounded once in double: under 10 roundings of 1.1e-16).
  [C2] Species scaling and additivity (eq-ch06-rayleigh-k): for each of He, H2O, CH4, N2, O2, CO2 and NH3 alone,
       k_s / k_H2 at equal concentration equals the scale of the code's table; a mixture of all eight gives the
       sum of the parts. To 1e-15 relative (one product and one quotient).
  [C3] Phase function (eq-ch06-rayleigh-phase), sympy: the moments chi_l = 1/2 int_{-1}^{1} P P_l dmu of
       P = 3/4 (1 + mu^2) are 1, 0, 1/10, 0, 0, 0 for l = 0..5, exactly; the module returns albedo 1 and moments
       (0, 1/10, 0, 0) for nmom = 4, bitwise.
  [C4] Spectral input: a `wavelength` [um] grid gives the same output as the `wavenumber` grid 1e4 / wavelength,
       to 1e-15 relative (one division more on one side).
  [C5] Refusals: nmom = 1, a species without a scale (Ar) and an empty species list are refused when the module
       is built, each with the message of RayleighImpl.
  [C6] INFO: pyharp's Avogadro constant (src/constants.h, `Avogadro`) is 6.02214179e23 [1/mol]; the SI value is
       6.02214076e23 exactly, so every Rayleigh extinction is high by the printed relative amount.

With --data FILE the H2 cross section on a wavelength grid (code and the leading lambda^-4 term) is written as JSON
for the figure fig-ch06-rayleigh-sigma.

Needs torch, numpy, sympy and a pyharp built from source at the pin of code_pin.yml (ch06_setup.sh).
Run:   python3 check_ch06_rayleigh.py [--data FILE]   (any directory; exits with the number of failed claims)
"""
import argparse
import json
import os
import sys

import numpy as np
import sympy as sp
import torch
from pyharp.opacity import Rayleigh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch06_common as C  # noqa: E402

SCALE = {"H2": 1.0, "He": 0.0641, "H2O": 3.3690, "CH4": 10.1509, "N2": 4.6035, "O2": 3.8634, "CO2": 10.5611,
         "NH3": 7.3427}          # the table of species_scale in src/opacity/rayleigh.cpp
COMPOSITION = {"H2": "{H: 2}", "He": "{He: 1}", "H2O": "{H: 2, O: 1}", "CH4": "{C: 1, H: 4}", "N2": "{N: 2}",
               "O2": "{O: 2}", "CO2": "{C: 1, O: 2}", "NH3": "{N: 1, H: 3}"}
NA_PYHARP = 6.02214179e23   # src/constants.h
NA_SI = 6.02214076e23       # exact since the 2019 SI redefinition


def config(species, nmom=4, extra=""):
    sp_lines = "\n".join(f"  - {{name: {s}, composition: {COMPOSITION.get(s, '{Ar: 1}')}}}" for s in species)
    return C.Config(f"""
species:
{sp_lines}
geometry: {{cells: {{nx1: 1}}}}
opacities:
  ray: {{type: rayleigh, species: [{', '.join(species)}], nmom: {nmom}}}{extra}
bands:
  - {{name: b, range: [1000., 50000.], opacities: [ray], solver: disort, nwave: 1, nstr: 4, flags: "lamber,quiet,onlyfl"}}
""")


def sigma_dw(nu):
    """Dalgarno & Williams (1962) H2 cross section [cm^2 per molecule] at wavenumber nu [cm^-1]."""
    lam = 1.0e8 / nu    # Angstrom
    return 8.14e-13 / lam**4 + 1.28e-6 / lam**6 + 1.61 / lam**8


def check_C1(nu):
    r = Rayleigh(config(["H2"]).opacity("ray"))
    out = r.forward(C.t([[[2.5]]]), {"wavenumber": C.t(nu)})
    want = 2.5 * sigma_dw(nu) * NA_PYHARP * 1.0e-4
    err = float(np.max(np.abs(out[:, 0, 0, 0].numpy() / want - 1)))
    return C.report(1, err <= 1e-14, f"H2, {len(nu)} wavenumbers 1000-50000 cm-1: k / (c sigma_DW N_A 1e-4) - 1 "
                    f"{C.bound(err, 1e-14)}")


def check_C2():
    names = list(SCALE)
    r = Rayleigh(config(names).opacity("ray"))
    nu = C.t([5000.0, 20000.0])
    eye = torch.eye(len(names), dtype=torch.float64)
    k = [r.forward(eye[i].view(1, 1, -1), {"wavenumber": nu})[:, 0, 0, 0] for i in range(len(names))]
    err = max(float(torch.max(torch.abs(k[i] / k[0] / SCALE[s] - 1))) for i, s in enumerate(names))
    conc = torch.linspace(0.5, 4.0, len(names), dtype=torch.float64).view(1, 1, -1)
    mix = r.forward(conc, {"wavenumber": nu})[:, 0, 0, 0]
    parts = sum(conc[0, 0, i] * k[i] for i in range(len(names)))
    err_mix = float(torch.max(torch.abs(mix / parts - 1)))
    ok = err <= 1e-15 and err_mix <= 1e-15
    return C.report(2, ok, f"{', '.join(names[1:])}: k_s / k_H2 / scale - 1 {C.bound(err, 1e-15)}; "
                    f"mixture of 8 / sum of parts - 1 {C.bound(err_mix, 1e-15)}")


def check_C3():
    mu = sp.Symbol("mu")
    P = sp.Rational(3, 4) * (1 + mu**2)
    chi = [sp.integrate(P * sp.legendre(l, mu), (mu, -1, 1)) / 2 for l in range(6)]
    exact = chi == [1, 0, sp.Rational(1, 10), 0, 0, 0]
    r = Rayleigh(config(["H2"], nmom=4).opacity("ray"))
    out = r.forward(C.t([[[1.0]]]), {"wavenumber": C.t([20000.0])})[0, 0, 0]
    code = bool(out[1].item() == 1.0) and out[2:].tolist() == [0.0, 0.1, 0.0, 0.0]
    return C.report(3, exact and code, f"sympy moments l = 0..5 of 3/4 (1 + mu^2): {[str(c) for c in chi]}; "
                    f"module albedo {out[1].item():g}, moments {out[2:].tolist()}")


def check_C4():
    r = Rayleigh(config(["H2", "N2"]).opacity("ray"))
    lam = C.t([0.3, 0.55, 1.0, 2.5])
    conc = C.t([[[1.0, 2.0]]])
    a = r.forward(conc, {"wavelength": lam})
    b = r.forward(conc, {"wavenumber": 1.0e4 / lam})
    err = float(torch.max(torch.abs(a / torch.where(b == 0, 1.0, b) - torch.where(b == 0, 0.0, 1.0))))
    return C.report(4, err <= 1e-15, f"wavelength [0.3, 0.55, 1.0, 2.5] um against wavenumber 1e4 / wavelength: "
                    f"relative difference {C.bound(err, 1e-15)}")


def check_C5():
    msgs = [C.refusal(lambda: Rayleigh(config(["H2"], nmom=1).opacity("ray"))),
            C.refusal(lambda: Rayleigh(config(["H2", "Ar"]).opacity("ray"))),
            C.refusal(lambda: Rayleigh(C.Config("""
species:
  - {name: H2, composition: {H: 2}}
geometry: {cells: {nx1: 1}}
opacities:
  ray: {type: rayleigh, nmom: 4}
bands:
  - {name: b, range: [1000., 50000.], opacities: [ray], solver: disort, nwave: 1, nstr: 4, flags: "lamber,quiet,onlyfl"}
""").opacity("ray")))]
    want = ["requires nmom >= 2", "does not support species 'Ar'", "requires at least one species"]
    ok = all(m is not None and w in m for m, w in zip(msgs, want))
    return C.report(5, ok, "refused: " + "; ".join(f'"{m}"' for m in msgs))


def check_C6():
    rel = NA_PYHARP / NA_SI - 1
    return C.report(6, True, f"N_A in pyharp 6.02214179e23, SI 6.02214076e23: relative excess {rel:.2e}", kind="INFO")


def write_data(path):
    r = Rayleigh(config(["H2"]).opacity("ray"))
    lam = np.geomspace(0.2, 2.0, 61)
    k = r.forward(C.t([[[1.0]]]), {"wavelength": C.t(lam)})[:, 0, 0, 0].numpy()
    sigma = k / (NA_PYHARP * 1.0e-4)          # cm^2 per molecule, as the code's own formula
    lead = 8.14e-13 / (lam * 1.0e4)**4
    with open(path, "w") as f:
        json.dump({"wavelength_um": lam.round(12).tolist(), "sigma_cm2": [float(f"{s:.10e}") for s in sigma],
                   "lambda4_cm2": [float(f"{s:.10e}") for s in lead]}, f, indent=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    a = ap.parse_args()
    C.header()
    nu = np.linspace(1000.0, 50000.0, 41)
    oks = [check_C1(nu), check_C2(), check_C3(), check_C4(), check_C5(), check_C6()]
    if a.data:
        write_data(a.data)
    nfail = oks.count(False)
    print(f"check_ch06_rayleigh: {len(oks) - nfail} of {len(oks)} claims pass")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
