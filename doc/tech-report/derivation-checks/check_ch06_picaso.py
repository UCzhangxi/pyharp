"""ch06 check: pre-mixed correlated-k table (`type: picaso-ck`), through a RadiationBand.

The source is PicasoCKImpl (src/opacity/picaso_ck.cpp); Python reaches it only through a band of a radiation YAML.
After band.forward, the band's `prop` buffer holds k dz in its first column (RadiationBandImpl::forward), so
k = prop[..., 0] / dz is the module's extinction. The tables are written here, in the NetCDF layout the reader
expects (quadrature_wavenumber and quadrature_weight (band, gpoint), wavenumber_lower and wavenumber_upper (band),
pressure, temperature_offset, nominal_temperature (pressure) and kappa); no PICASO data file is needed.

  [C1] A table whose ln kappa is linear in (nu, ln p, Delta T), stored with its four dimensions in reverse order:
       k = 1e-4 kappa(nu, ln p, T - T_nom(p)) * sum_s c_s (eq-ch06-picaso-k, eq-ch06-picaso-interp) at 4 g-points,
       2 columns and 3 layers, to 1e-14 relative: multilinear interpolation of a linear function is exact, so only
       the rounding of a few logs, exps and products remains.
  [C2] A table of random ln kappa: k equals the trilinear interpolation of ln kappa in (nu, ln p, Delta T) done in
       numpy here, with T_nom interpolated as ln T_nom linear in ln p, at 12 points inside the table, to 1e-13
       relative.
  [C3] Outside the table: pressures and temperatures beyond the grid return the value at the nearest edge, to
       1e-13 relative (the edge reference itself has T - T_nom = -50 K only to the rounding of exp(log T_nom)).
  [C4] Pre-mixed: k depends on the concentrations only through their sum; two different splits of the same total
       give bitwise equal k.
  [C5] Refusals: two data files, and a file without `kappa`, are refused when the band is built, each with its
       message.
  [C6] Spectral grid: a band wavenumber halfway between two quadrature points of different bands returns the
       geometric mean of their k, to 1e-14 relative, so the band grid must be the table's quadrature points.

Needs torch, numpy, scipy and a pyharp built from source with NetCDF at the pin of code_pin.yml (ch06_setup.sh).
Run:   python3 check_ch06_picaso.py   (any directory; exits with the number of failed claims)
"""
import os
import sys
import tempfile

import numpy as np
import torch
import pyharp
from scipy.io import netcdf_file

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch06_common as C  # noqa: E402

QW = np.array([[1000.0, 1100.0], [1300.0, 1450.0]])     # quadrature wavenumbers (band, gpoint) [cm^-1]
QWT = np.array([[0.4, 0.6], [0.3, 0.7]])
LO, UP = np.array([950.0, 1250.0]), np.array([1200.0, 1500.0])
P = np.array([1e3, 1e4, 1e5])                           # [Pa]
TOFF = np.array([-50.0, 0.0, 50.0])                     # [K]
TNOM = np.array([200.0, 250.0, 300.0])                  # [K], one per pressure


def lnk_linear(w, lnp, dt):
    return -60.0 + 0.002 * w + 0.5 * lnp + 0.01 * dt    # ln(cm^2/mol)


def write_table(path, lnk, order=("band", "gpoint", "pressure", "temperature_offset"), drop=None):
    """kappa(band, gpoint, pressure, temperature_offset) = exp(lnk), stored with the dimensions in `order`."""
    f = netcdf_file(path, "w")
    for name, n in (("band", 2), ("gpoint", 2), ("pressure", 3), ("temperature_offset", 3)):
        f.createDimension(name, n)

    def var(name, dims, data):
        if name != drop:
            f.createVariable(name, "d", dims)[:] = data

    var("quadrature_wavenumber", ("band", "gpoint"), QW)
    var("quadrature_weight", ("band", "gpoint"), QWT)
    var("wavenumber_lower", ("band",), LO)
    var("wavenumber_upper", ("band",), UP)
    var("pressure", ("pressure",), P)
    var("temperature_offset", ("temperature_offset",), TOFF)
    var("nominal_temperature", ("pressure",), TNOM)
    base = ("band", "gpoint", "pressure", "temperature_offset")
    var("kappa", order, np.exp(lnk).transpose([base.index(d) for d in order]))
    f.close()


def make_band(lnk, waves=None, files=1, **kw):
    path = os.path.join(tempfile.mkdtemp(prefix="ch06_picaso_"), "table.nc")
    write_table(path, lnk, **kw)
    data = ", ".join([path] * files)
    waves = list(QW.ravel()) if waves is None else waves
    cfg = C.Config(f"""
species:
  - {{name: H2, composition: {{H: 2}}}}
  - {{name: He, composition: {{He: 1}}}}
geometry: {{cells: {{nx1: 3}}}}
opacities:
  pk: {{type: picaso-ck, data: [{data}]}}
bands:
  - {{name: b, range: [950., 1500.], opacities: [pk], solver: disort, nwave: {len(waves)}, nstr: 4, flags: "lamber,quiet,onlyfl"}}
""")
    b = cfg.band()
    b.wavenumber(waves).weight([1.0 / len(waves)] * len(waves)).ncol(2).nlyr(3)
    pyharp.disort_config(b.disort(), 4, 3, 2, len(waves))
    return pyharp.RadiationBand(b), len(waves)


def extinction(band, nwave, conc, pres, temp):
    dz = C.t([10.0, 20.0, 30.0])
    bc = {"b/fbeam": torch.ones((nwave, 2), dtype=torch.float64), "b/umu0": C.t([0.5, 0.5]),
          "b/albedo": torch.zeros((nwave, 2), dtype=torch.float64)}
    # tempf (levels) is the solver's Planck input; the opacity reads the layer temperature temp
    atm = {"pres": C.t(pres), "temp": C.t(temp), "tempf": torch.full((2, 4), 250.0, dtype=torch.float64)}
    band.forward(C.t(conc), dz, bc, atm)
    return (band.buffer("prop")[..., 0] / dz).numpy()


CONC = [[[3.0, 1.0], [2.0, 0.5], [1.0, 1.0]], [[0.2, 0.1], [4.0, 0.0], [0.0, 2.5]]]
PRES = [[3e3, 5e4, 2e4], [1.5e3, 8e4, 1e4]]
TEMP = [[230.0, 260.0, 240.0], [215.0, 290.0, 251.0]]


def tnom(pres):
    return np.exp(np.interp(np.log(pres), np.log(P), np.log(TNOM)))


def check_C1():
    W, LP, DT = np.meshgrid(QW.ravel(), np.log(P), TOFF, indexing="ij")
    lnk = lnk_linear(W, LP, DT).reshape(2, 2, 3, 3)
    band, nw = make_band(lnk, order=("temperature_offset", "pressure", "gpoint", "band"))
    k = extinction(band, nw, CONC, PRES, TEMP)
    pres, temp = np.array(PRES), np.array(TEMP)
    want = 1e-4 * np.exp(lnk_linear(QW.ravel()[:, None, None], np.log(pres)[None], (temp - tnom(pres))[None])) \
        * np.array(CONC).sum(-1)[None]
    err = float(np.max(np.abs(k / want - 1)))
    return C.report(1, err <= 1e-14, f"linear ln kappa, kappa stored as (temperature_offset, pressure, gpoint, band), "
                    f"4 g-points x 2 columns x 3 layers: k / (1e-4 kappa sum c) - 1 {C.bound(err, 1e-14)}")


def trilinear(lnk4, w, lnp, dt):
    """Linear interpolation of lnk4 (nwave, np, nt) on the axes (QW flat, ln P, TOFF), done one axis at a time."""
    axes = [QW.ravel(), np.log(P), TOFF]
    out = []
    for wi, li, di in zip(w, lnp, dt):
        v = lnk4
        for ax, q in zip(axes, (wi, li, di)):
            i = int(np.clip(np.searchsorted(ax, q, side="right") - 1, 0, len(ax) - 2))
            f = (q - ax[i]) / (ax[i + 1] - ax[i])
            v = (1 - f) * v[i] + f * v[i + 1]
        out.append(v)
    return np.array(out)


def check_C2():
    rng = np.random.default_rng(6)
    lnk = rng.uniform(-50.0, -40.0, size=(2, 2, 3, 3))
    band, nw = make_band(lnk)
    k = extinction(band, nw, CONC, PRES, TEMP)
    pres, temp, conc = np.array(PRES), np.array(TEMP), np.array(CONC).sum(-1)
    worst = 0.0
    for j, w in enumerate(QW.ravel()):
        lp, dt = np.log(pres).ravel(), (temp - tnom(pres)).ravel()
        want = 1e-4 * np.exp(trilinear(lnk.reshape(4, 3, 3), [w] * lp.size, lp, dt)) * conc.ravel()
        worst = max(worst, float(np.max(np.abs(k[j].ravel() / want - 1))))
    return C.report(2, worst <= 1e-13, f"random ln kappa, 4 g-points x 6 (p, T) points: k against numpy trilinear "
                    f"interpolation of ln kappa {C.bound(worst, 1e-13)}")


def check_C3():
    rng = np.random.default_rng(7)
    lnk = rng.uniform(-50.0, -40.0, size=(2, 2, 3, 3))
    band, nw = make_band(lnk)
    conc = [[[1.0, 0.0]] * 3] * 2
    out = extinction(band, nw, conc, [[1e2, 1e7, 1e2], [1e7, 1e2, 1e7]], [[100.0, 900.0, 900.0], [100.0, 100.0, 900.0]])
    edge = extinction(band, nw, conc, [[1e3, 1e5, 1e3], [1e5, 1e3, 1e5]], [[150.0, 350.0, 250.0], [250.0, 150.0, 350.0]])
    err = float(np.max(np.abs(out / edge - 1)))
    return C.report(3, err <= 1e-13, f"p 1e2 and 1e7 Pa, T 100 and 900 K against the edge values "
                    f"(1e3, 1e5 Pa; offsets -50, +50 K): {C.bound(err, 1e-13)}")


def check_C4():
    rng = np.random.default_rng(8)
    band, nw = make_band(rng.uniform(-50.0, -40.0, size=(2, 2, 3, 3)))
    a = extinction(band, nw, [[[3.0, 1.0]] * 3] * 2, PRES, TEMP)
    b = extinction(band, nw, [[[0.5, 3.5]] * 3] * 2, PRES, TEMP)
    same = bool(np.array_equal(a, b))
    return C.report(4, same, f"(3, 1) and (0.5, 3.5) mol m-3 of (H2, He): k bitwise equal: {same}")


def check_C5():
    lnk = np.full((2, 2, 3, 3), -45.0)
    msgs = [C.refusal(lambda: make_band(lnk, files=2)), C.refusal(lambda: make_band(lnk, drop="kappa"))]
    want = ["Only one opacity file is allowed", "Missing required variable kappa"]
    ok = all(m is not None and s in m for m, s in zip(msgs, want))
    return C.report(5, ok, "refused: " + "; ".join(f'"{m}"' for m in msgs))


def check_C6():
    rng = np.random.default_rng(9)
    lnk = rng.uniform(-50.0, -40.0, size=(2, 2, 3, 3))
    mid = 0.5 * (QW[0, 1] + QW[1, 0])
    band, nw = make_band(lnk, waves=[QW[0, 1], mid, QW[1, 0]])
    k = extinction(band, nw, CONC, PRES, TEMP)
    err = float(np.max(np.abs(k[1] / np.sqrt(k[0] * k[2]) - 1)))
    return C.report(6, err <= 1e-14, f"nu = {mid:g} cm-1, halfway between the g-points {QW[0, 1]:g} (band 1) and "
                    f"{QW[1, 0]:g} (band 2): k / sqrt(k_1 k_2) - 1 {C.bound(err, 1e-14)}")


def main():
    C.header()
    oks = [check_C1(), check_C2(), check_C3(), check_C4(), check_C5(), check_C6()]
    nfail = oks.count(False)
    print(f"check_ch06_picaso: {len(oks) - nfail} of {len(oks)} claims pass")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
