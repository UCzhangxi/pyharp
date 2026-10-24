"""ch08 check: the column time stepper (Integrator stage weights; RadiationModel.forward).

The Integrator is bound to Python and is run directly. RadiationModel has no Python binding at the pin, so this check
compiles a ten-line pybind11 wrapper (torch.utils.cpp_extension.load_inline) against the installed pyharp library and
its headers; the wrapper builds a RadiationModel from a YAML file and options, sets weight 1 on every band (the YAML
parser reads no spectral grid) and nphase = nstr on a DISORT band (see ch08_config.py [P1]), and calls
forward(xfrac, atm, bc, dt, stage) for every stage of every step. Nothing of the model is re-implemented.

Stage form (integrator.cpp, IntegratorImpl::forward): u^(s) = w0 u^n + w1 u^(s-1) + w2 dt L(u^(s-1)), u^(-1) = u^n.

  [C1] sympy: with the code's weights, one step on du/dt = lambda u multiplies u by R(z), z = lambda dt; R agrees with
       exp(z) through z^p and not z^(p+1), p = 1, 2, 3, 3 for rk1, rk2, rk3, rk3s4; every stage is a convex combination
       (w0, w1, w2 >= 0, w0 + w1 = 1), the form that makes a scheme strong-stability preserving.
  [C2] the Integrator on du/dt = -u^2, u(0) = 1, to t = 1 with 8, 16, 32, 64 steps: the fitted slope of log error
       against log dt is p within 0.15 (error against the exact 1/(1 + t)).
  [C3] RadiationModel, one rk1 step of a grey longwave column: the column energy change equals the flux in minus the
       flux out, sum_i rho_i c_p dz_i dT_i = -dt (F_L - F_0) (net radiative plus diffusive flux at the top and the
       surface; the diffusive flux is zero at both), with rho = p M / (R T) and dz from calc_dz_hypsometric (tol 1e-12
       relative: a telescoping sum of 8 terms). g / R enters as the code builds it, a float32 tensor (see [P3]).
  [C4] the exported diffusive flux, in a run with kappa = 100 m^2/s so that diffusion matters, is zero at the
       surface and the top and equals -kappa rho_(i-1/2) c_p 2 (T_i - T_(i-1)) / (dz_i + dz_(i-1)) in between. The level
       density is computed here independently: ln rho_(i-1/2) is the derivative, at the level height, of the quadratic
       through the cumulative integral of ln rho dz at the three levels around it (the thickness-weighted second-order
       reconstruction layer2level performs). Tolerance 1e-10 relative: the code differentiates a cumulative sum of
       size 1e5 against values of size 1, which costs about 1e-12. The same run's column energy closes as in [C3].
  [C5] the surface update is dT_s = dt / C_s (F^dn_s - sigma T_s^4), with F^dn_s from pyharp.Radiation on the same
       column (tol 1e-12 relative).
  [C6] the model's temperatures converge with the integrator's order: 8 layers, 8, 16, 32, 64 steps to t = 2e5 s
       against 512 rk3 steps; fitted slope 1 for rk1 and 3 for rk3, within 0.15.
  [C7] after every stage the temperatures are clamped to [20, 1000] K: a layer at 1500 K returns at 1000 K, one at
       10 K at 20 K, in one step.
  [C8] the model reads species 0-2 as gases and 3-4 as aerosols: xfrac with 3 species is refused.
  [C9] the layer thickness: calc_dz_hypsometric with layer pressures equals dz_i = (R T_i / (M g)) ln(p_(i-1/2) /
       p_(i+1/2)), with ln p on the levels the mean of the two adjacent layers and extrapolated linearly at the two
       ends, (3 v_0 - v_1)/2 (tol 1e-14 relative: a log, a difference and two products).
  [P2] CANDIDATE, a DISORT band without `ttemp` in bc stops the model at its second forward call: pydisort writes a
       default `ttemp` of shape (1, ncol) into the bc map it is given, and RadiationModel hands the same map to every
       stage, whose next call refuses a `ttemp` that is not one-dimensional.
  [P3] CANDIDATE, the layer thickness uses M g / R rounded to single precision: torch::tensor({M g / R}) takes the
       default dtype, float32; dz is off by the float32 rounding of g / R (relative, printed).
  [P4] CANDIDATE, the level temperatures are never refreshed: RadiationModel updates atm["temp"] only, so a Planck
       band that finds `tempf` in atm uses the initial level temperatures at every stage of every step. The same rk3
       run (64 steps to t = 2e6 s) with and without `tempf` in atm is compared; without it the band interpolates the
       current layer temperatures. All other runs of this check pass no `tempf`.
  [P1] CANDIDATE, the surface budget has no albedo: a non-scattering shortwave column over a surface of albedo 0, 0.5
       and 1 gives the same surface warming, so with albedo A the surface and the column together gain A F^dn_s dt
       more energy per unit area than enters at the top.

Needs: torch, numpy, sympy, pydisort, a pyharp built against that pydisort, a C++17 compiler, ninja, and
PYHARP_WT/build/_deps (yaml-cpp and fmt headers of that pyharp build).
Run:   python ch08_stepper.py [--work DIR]   (default: a fresh temporary directory)
"""
import argparse
import math
import os
import sys
import tempfile

import numpy as np
import pydisort
import pyharp
import sympy as sp
import torch
from torch.utils.cpp_extension import load_inline

from ch08_common import F64, compile_slab, header, set_unit_weights, write

WRAP = r'''
#include <torch/extension.h>
#include <harp/integrator/radiation_model.hpp>
std::tuple<torch::Tensor, torch::Tensor, std::map<std::string, torch::Tensor>>
run(std::string yaml, std::string intg, std::map<std::string, double> par, torch::Tensor xfrac,
    std::map<std::string, torch::Tensor> atm, std::map<std::string, torch::Tensor> bc, double dt, int nstep) {
  auto op = harp::RadiationModelOptionsImpl::create();
  op->ncol(atm["temp"].size(0)).nlyr(atm["temp"].size(1));
  op->grav(par.at("grav")).mean_mol_weight(par.at("mmw")).cp(par.at("cp")).kappa(par.at("kappa")).cSurf(par.at("cSurf"));
  auto rop = harp::RadiationOptionsImpl::from_yaml(yaml);
  for (auto& b : rop->bands()) {
    b->weight(std::vector<double>(b->nwave(), 1.0));
    if (b->solver_name() == "disort") b->disort()->ds().nphase = b->disort()->ds().nstr;
  }
  op->rad(rop);
  auto iop = harp::IntegratorOptionsImpl::create();
  iop->type(intg);
  op->intg(iop);
  harp::RadiationModel m(op);
  int ns = m->pintg->stages.size();
  for (int n = 0; n < nstep; ++n)
    for (int s = 0; s < ns; ++s) m->forward(xfrac, atm, bc, dt, s);
  return {atm["temp"], bc["btemp"], m->results};
}
'''
PAR = {"grav": 3.711, "mmw": 0.044, "cp": 844.0, "kappa": 2e-5, "cSurf": 2e5}   # the RadiationModelOptions defaults
NL = 8


def build(work):
    wt = os.environ.get("PYHARP_WT", "")
    inc = [os.path.dirname(pyharp.__file__), os.path.dirname(pydisort.__file__),
           f"{wt}/build/_deps/yaml-cpp-src/include", f"{wt}/build/_deps/fmt-src/include", f"{wt}/build"]
    lib_h, lib_d = os.path.join(inc[0], "lib"), os.path.join(inc[1], "lib")
    bdir = os.path.join(work, "ext")
    os.makedirs(bdir, exist_ok=True)
    return load_inline("ch08_radiation_model", cpp_sources=[WRAP], functions=["run"], extra_include_paths=inc,
                       extra_ldflags=[f"-L{lib_h}", "-lharp_release", f"-Wl,-rpath,{lib_h}",
                                      f"-L{lib_d}", "-ldisort_release", f"-Wl,-rpath,{lib_d}"],
                       build_directory=bdir, verbose=False)


def lw_yaml(work):
    pt = compile_slab(work, "grey_lw", 2e-6)
    return write(work, "column_lw.yaml", f"""species:
  - name: CO2
    composition: {{C: 1, O: 2}}
geometry:
  cells:
    nx1: {NL}
opacities:
  olw: {{type: jit, species: [CO2], data: [{pt}]}}
bands:
  - name: lw
    range: [1.0, 3000.0]
    opacities: [olw]
    solver: disort
    nwave: 1
    nstr: 4
    flags: lamber,quiet,onlyfl,planck
""")


def sw_yaml(work):
    pt = compile_slab(work, "grey_sw", 1e-7)
    return write(work, "column_sw.yaml", f"""species:
  - name: CO2
    composition: {{C: 1, O: 2}}
geometry:
  cells:
    nx1: {NL}
opacities:
  osw: {{type: jit, species: [CO2], data: [{pt}]}}
bands:
  - name: sw
    range: [10000.0, 20000.0]
    opacities: [osw]
    solver: disort
    nwave: 1
    nstr: 4
    flags: lamber,quiet,onlyfl
""")


def column(t_top=180.0, t_bot=230.0, t_s=240.0, nspec=5):
    pres = torch.logspace(5.0, 3.0, NL, dtype=F64).unsqueeze(0)
    temp = torch.linspace(t_bot, t_top, NL, dtype=F64).unsqueeze(0)
    xf = torch.zeros((1, NL, nspec), dtype=F64)
    xf[..., 0] = 1.0
    atm = {"pres": pres, "temp": temp}
    bc = {"btemp": torch.tensor([t_s], dtype=F64), "ttemp": torch.zeros(1, dtype=F64),
          "lw/albedo": torch.zeros((1, 1), dtype=F64)}
    return xf, atm, bc


def copy(d):
    return {k: v.clone() for k, v in d.items()}


def stability(weights):
    z = sp.Symbol("z")
    un = sp.Integer(1)
    u = un
    for w0, w1, w2 in weights:
        u = sp.expand(sp.nsimplify(w0) * un + sp.nsimplify(w1) * u + sp.nsimplify(w2) * z * u)
    ex = sp.series(sp.exp(z), z, 0, 8).removeO()
    diff = sp.Poly(sp.expand(u - ex), z)
    order = min(m[0] for m in diff.monoms()) - 1
    return order, sp.Poly(u, z).all_coeffs()[::-1]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default=None)
    work = ap.parse_args().work or tempfile.mkdtemp(prefix="ch08_step_")
    os.makedirs(work, exist_ok=True)
    torch.set_num_threads(1)
    header(f", pyharp {pyharp.__version__}, sympy {sp.__version__}")
    nfail = 0

    want = {"rk1": 1, "rk2": 2, "rk3": 3, "rk3s4": 3}
    orders, convex = {}, True
    for t in want:
        iop = pyharp.IntegratorOptions()
        iop.type(t)
        w = [(s.wght0(), s.wght1(), s.wght2()) for s in pyharp.Integrator(iop).stages]
        orders[t], _ = stability(w)
        convex &= all(a >= 0 and b >= 0 and c >= 0 and abs(a + b - 1) == 0 for a, b, c in w)
    ok = orders == want and convex
    nfail += not ok
    print(f"[C1] {'PASS' if ok else 'FAIL'} sympy: R(z) = exp(z) + O(z^(p+1)) with p = "
          + ", ".join(f"{t} {orders[t]}" for t in want) + f"; every stage convex: {convex}")

    slopes = {}
    for t in want:
        iop = pyharp.IntegratorOptions()
        iop.type(t)
        it = pyharp.Integrator(iop)
        errs, hs = [], []
        for n in (8, 16, 32, 64):
            dt = 1.0 / n
            u = torch.tensor([1.0], dtype=F64)
            for _ in range(n):
                u0, u1 = u.clone(), u.clone()
                for s in range(len(it.stages)):
                    u1 = it.forward(s, u0, u1, -dt * u1 * u1)
                u = u1
            errs.append(abs(u.item() - 0.5))
            hs.append(dt)
        slopes[t] = float(np.polyfit(np.log(hs), np.log(errs), 1)[0])
    ok = all(abs(slopes[t] - want[t]) <= 0.15 for t in want)
    nfail += not ok
    print(f"[C2] {'PASS' if ok else 'FAIL'} du/dt = -u^2, 8-64 steps: fitted slopes "
          + ", ".join(f"{t} {slopes[t]:.2f}" for t in want) + " (want 1, 2, 3, 3 within 0.15)")

    mod = build(work)
    ylw = lw_yaml(work)
    xf, atm, bc = column()
    dt = 2e4
    t1, ts1, res = mod.run(ylw, "rk1", PAR, xf, copy(atm), copy(bc), dt, 1)
    g_ov_r = torch.tensor([PAR["mmw"] * PAR["grav"] / pyharp.constants.Rgas], dtype=torch.float32)
    dz = pyharp.calc_dz_hypsometric(atm["pres"], atm["temp"], g_ov_r)
    rho = atm["pres"] * PAR["mmw"] / (pyharp.constants.Rgas * atm["temp"])
    dT = res["dT_atm"]
    ftot = res["netflux"] + res["thermal_diffusion_flux"]
    lhs = (rho * PAR["cp"] * dz * dT).sum().item()
    rhs = -dt * (ftot[0, -1] - ftot[0, 0]).item()
    dev3 = abs(lhs / rhs - 1)
    upd = torch.equal(t1, (atm["temp"] + dT).clamp(20, 1000))
    ok = dev3 <= 1e-12 and upd
    nfail += not ok
    print(f"[C3] {'PASS' if ok else 'FAIL'} column energy, one rk1 step of {dt:.0e} s: sum rho c_p dz dT = "
          f"{lhs:.6e} J m-2, -dt (F_top - F_sfc) = {rhs:.6e} J m-2, rel dev {dev3:.1e} (tol 1e-12); "
          f"T_new = T + dT_atm bitwise: {upd}")

    par_k = dict(PAR, kappa=100.0)
    _, _, rk = mod.run(ylw, "rk1", par_k, xf, copy(atm), copy(bc), dt, 1)
    fd = rk["thermal_diffusion_flux"][0].numpy()
    temp = atm["temp"][0].numpy()
    dzn = dz[0].numpy()
    lnr = np.log(rho[0].numpy())
    zl = np.concatenate([[0.0], np.cumsum(dzn)])               # level heights
    yl = np.concatenate([[0.0], np.cumsum(lnr * dzn)])         # integral of ln rho from the surface
    lnr_h = np.empty(NL - 1)
    for q in range(1, NL):
        x0, x1, x2 = zl[q - 1], zl[q], zl[q + 1]
        y0, y1, y2 = yl[q - 1] - yl[q], 0.0, yl[q + 1] - yl[q]
        lnr_h[q - 1] = (y0 * (x1 - x2) / ((x0 - x1) * (x0 - x2)) + y1 * (2 * x1 - x0 - x2) / ((x1 - x0) * (x1 - x2))
                        + y2 * (x1 - x0) / ((x2 - x0) * (x2 - x1)))
    grad = 2 * (temp[1:] - temp[:-1]) / (dzn[1:] + dzn[:-1])
    want = -par_k["kappa"] * np.exp(lnr_h) * PAR["cp"] * grad
    dev4 = float(np.max(np.abs(fd[1:-1] / want - 1)))
    ftk = rk["netflux"] + rk["thermal_diffusion_flux"]
    ek = abs((rho * PAR["cp"] * dz * rk["dT_atm"]).sum().item() / (-dt * (ftk[0, -1] - ftk[0, 0]).item()) - 1)
    ok = fd[0] == 0 and fd[-1] == 0 and dev4 <= 1e-10 and ek <= 1e-12
    nfail += not ok
    print(f"[C4] {'PASS' if ok else 'FAIL'} diffusive flux, kappa = 100 m^2/s: 0 at the surface and the top; on the "
          f"{NL - 1} interior levels -kappa rho_h c_p dT/dz with rho_h from the quadratic reconstruction of ln rho: max "
          f"rel dev {dev4:.1e} (tol 1e-10); |F_d| up to {np.max(np.abs(fd)):.2f} W m-2; column energy rel dev "
          f"{ek:.1e} (tol 1e-12)")

    rop = set_unit_weights(pyharp.RadiationOptions.from_yaml(ylw))
    rad = pyharp.Radiation(rop)
    conc = xf.clone()
    conc[..., :3] *= (atm["pres"] / (pyharp.constants.Rgas * atm["temp"])).unsqueeze(-1)
    conc[..., 3:5] *= (atm["pres"] / (pyharp.constants.Rgas * atm["temp"])).unsqueeze(-1)
    _, sdn, _ = rad.forward(conc, dz, copy(bc), copy(atm))
    want_s = dt / PAR["cSurf"] * (sdn - pyharp.constants.stefanBoltzmann * bc["btemp"] ** 4)
    dev5 = abs(res["dT_surf"].item() / want_s.item() - 1)
    ok = dev5 <= 1e-12
    nfail += not ok
    print(f"[C5] {'PASS' if ok else 'FAIL'} surface: dT_s = {res['dT_surf'].item():.6e} K, dt/C_s (F_dn - sigma "
          f"T_s^4) = {want_s.item():.6e} K (F_dn {sdn.item():.4f} W m-2), rel dev {dev5:.1e} (tol 1e-12)")

    tend = 2e5
    ref, _, _ = mod.run(ylw, "rk3", PAR, xf, copy(atm), copy(bc), tend / 512, 512)
    conv = {}
    for t in ("rk1", "rk3"):
        errs = []
        for n in (8, 16, 32, 64):
            tn, _, _ = mod.run(ylw, t, PAR, xf, copy(atm), copy(bc), tend / n, n)
            errs.append((tn - ref).abs().max().item())
        conv[t] = (float(np.polyfit(np.log([tend / n for n in (8, 16, 32, 64)]), np.log(errs), 1)[0]), errs)
    ok = abs(conv["rk1"][0] - 1) <= 0.15 and abs(conv["rk3"][0] - 3) <= 0.15
    nfail += not ok
    print(f"[C6] {'PASS' if ok else 'FAIL'} model convergence to t = {tend:.0e} s (8, 16, 32, 64 steps vs 512 rk3): "
          + "; ".join(f"{t} slope {conv[t][0]:.2f}, errors " + ", ".join(f"{e:.2e}" for e in conv[t][1]) + " K"
                      for t in conv) + f"; temperature change {(ref - atm['temp']).abs().max().item():.1f} K")
    for t in conv:
        for n, e in zip((8, 16, 32, 64), conv[t][1]):
            print(f"conv {t} {n} {tend / n:.6e} {e:.6e}")

    xc, atc, bcc = column()
    atc["temp"][0, 3] = 1500.0
    atc["temp"][0, 5] = 10.0
    tc, _, _ = mod.run(ylw, "rk1", PAR, xc, copy(atc), copy(bcc), 1.0, 1)
    ok = tc[0, 3].item() == 1000.0 and tc[0, 5].item() == 20.0
    nfail += not ok
    print(f"[C7] {'PASS' if ok else 'FAIL'} clamp after one 1 s step: 1500 K -> {tc[0, 3].item():.1f} K, "
          f"10 K -> {tc[0, 5].item():.1f} K")

    x3, at3, bc3 = column(nspec=3)
    try:
        mod.run(ylw, "rk1", PAR, x3, copy(at3), copy(bc3), 1.0, 1)
        ok = False
    except Exception:  # noqa: BLE001
        ok = True
    nfail += not ok
    print(f"[C8] {'PASS' if ok else 'FAIL'} xfrac with 3 species refused: {ok}")

    lnp = np.log(atm["pres"][0].numpy())
    lev = np.concatenate([[(3 * lnp[0] - lnp[1]) / 2], (lnp[:-1] + lnp[1:]) / 2, [(3 * lnp[-1] - lnp[-2]) / 2]])
    g64 = PAR["mmw"] * PAR["grav"] / pyharp.constants.Rgas
    dz_ref = atm["temp"][0].numpy() * (lev[:-1] - lev[1:]) / g64
    dz_pyh = pyharp.calc_dz_hypsometric(atm["pres"], atm["temp"], torch.tensor([g64], dtype=F64))[0].numpy()
    dev9 = float(np.max(np.abs(dz_pyh / dz_ref - 1)))
    ok = dev9 <= 1e-14
    nfail += not ok
    print(f"[C9] {'PASS' if ok else 'FAIL'} hypsometric dz = R T ln(p_lo / p_hi) / (M g), level ln p from the layer "
          f"means: max rel dev {dev9:.1e} (tol 1e-14); dz from {dz_ref.min():.1f} to {dz_ref.max():.1f} m")

    ysw = sw_yaml(work)
    dts = []
    for a in (0.0, 0.5, 1.0):
        xs, ats, bcs = column()
        bcs = {"btemp": bcs["btemp"], "sw/umu0": torch.tensor([0.5], dtype=F64),
               "sw/fbeam": torch.tensor([[400.0]], dtype=F64), "sw/albedo": torch.tensor([[a]], dtype=F64)}
        _, _, r = mod.run(ysw, "rk1", PAR, xs, copy(ats), copy(bcs), dt, 1)
        top = r["netflux"][0, -1].item()
        fd_s = PAR["cSurf"] / dt * r["dT_surf"].item() + pyharp.constants.stefanBoltzmann * bcs["btemp"].item() ** 4
        gain = (rho * PAR["cp"] * dz * r["dT_atm"]).sum().item() + PAR["cSurf"] * r["dT_surf"].item()
        dts.append((a, r["dT_surf"].item(), gain / dt + top, fd_s))
    same = all(abs(d[1] - dts[0][1]) <= 1e-12 * abs(dts[0][1]) for d in dts)
    excess = [(d[0], d[2] + pyharp.constants.stefanBoltzmann * 240.0 ** 4, d[0] * d[3]) for d in dts]
    rep = same and abs(excess[2][1] - excess[2][2]) <= 1e-9 * excess[2][2] and abs(excess[0][1]) <= 1e-9 * excess[2][2]
    print(f"[P1] CANDIDATE {'reproduced' if rep else 'not reproduced'} surface warming in one rk1 step with albedo "
          + ", ".join(f"{a:g}: {d:.6e} K" for a, d, _, _ in dts)
          + "; energy gained beyond the top input, per unit time [W m-2]: "
          + ", ".join(f"A {a:g}: {e:.4f} (A F_dn = {w:.4f})" for a, e, w in excess))
    xp, atp, bcp = column()
    del bcp["ttemp"]
    msg = ""
    try:
        mod.run(ylw, "rk3", PAR, xp, copy(atp), copy(bcp), dt, 1)
    except Exception as e:  # noqa: BLE001
        msg = str(e).splitlines()[0]
    rep2 = "ttemp.dim() != 1" in msg
    print(f"[P2] CANDIDATE {'reproduced' if rep2 else 'not reproduced'} rk3 step with no 'ttemp' in bc: "
          f"{msg[:msg.index('!= 1') + 4] if rep2 else (msg or 'no error')}")

    g32 = torch.tensor([g64], dtype=torch.float32).item()
    dz64 = pyharp.calc_dz_hypsometric(atm["pres"], atm["temp"], torch.tensor([g64], dtype=F64))
    ddz = (dz / dz64 - 1).abs().max().item()
    rep3 = ddz > 1e-9 and abs(g32 / g64 - 1) > 1e-9
    print(f"[P3] CANDIDATE {'reproduced' if rep3 else 'not reproduced'} M g/R as built by the model: {g32:.9e} "
          f"(float32) against {g64:.9e}; dz off by {ddz:.1e} relative")
    xq, atq, bcq = column()
    temp0 = atq["temp"]
    atq_f = copy(atq)
    atq_f["tempf"] = torch.cat([temp0[:, :1], 0.5 * (temp0[:, 1:] + temp0[:, :-1]), temp0[:, -1:]], dim=-1)
    t_with, _, _ = mod.run(ylw, "rk3", PAR, xq, atq_f, copy(bcq), 2e6 / 64, 64)
    t_without, _, _ = mod.run(ylw, "rk3", PAR, xq, copy(atq), copy(bcq), 2e6 / 64, 64)
    frozen = torch.equal(atq_f["tempf"], torch.cat([temp0[:, :1], 0.5 * (temp0[:, 1:] + temp0[:, :-1]),
                                                     temp0[:, -1:]], dim=-1))
    d4 = (t_with - t_without).abs().max().item()
    rep4 = frozen and d4 > 0.1
    print(f"[P4] CANDIDATE {'reproduced' if rep4 else 'not reproduced'} rk3, 64 steps to t = 2e6 s: tempf in atm "
          f"tensor unchanged after the run: {frozen}; max |T(with tempf) - T(without)| = {d4:.3f} K; largest temperature "
          f"change with tempf {(t_with - temp0).abs().max().item():.2f} K, without {(t_without - temp0).abs().max().item():.2f} K")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
