"""ch03 check: the cdisort 2.1.3 test problems (disotest), replayed through the pydisort Python API,
plus cdisort's band-integrated Planck function against an exact quadrature.

Method. pydisort bundles the disotest driver as tests/cdisort213/test_cdisort.c. build.sh (in
ch03_disotest/) compiles it with every c_disort() call routed through dump_shim.c, which writes each
call's exact inputs and C outputs, and every print_test() call's reference values, as JSON lines.
This script builds and runs that driver, rebuilds every case with DisortOptions / Disort.forward /
gather_flx / gather_rad, and compares.

Pass rule (disotest's own print_test.c): every ratio calc/ref lies in [0.99, 1.01], where
ratio = 1 + calc when ref = 0 and ratio = 0 when calc = 0 != ref. Compared: rfldir, rfldn, flup,
dfdt at each output depth and the intensities uu. "maxrel" is the largest relative deviation among
reference values above 1e-6 x max (the Fortran noise floor); the references carry 5-6 digits.

Labels:
  [C1] cases with published references (1-9) pass the ratio rule
  [C2] self-consistency cases 10b and 11b pass
  [C3] case 12b fails in pydisort exactly where it fails in C (it tests the absorption-depth-10 cut)
  [C4] pydisort reproduces the C solver bit for bit on every runnable case
  [C5] c_planck_func2 against CODATA 2018 and against its own constants (tol 5e-6: cdisort states
       "at least 6 significant digits, assuming the physical constants are infinitely accurate")
  [C6] case 13: brute-force albedo and transmissivity match the printed shortcut values (tol 1e-5,
       the 5-digit print precision)
  [P1] CANDIDATE gather_rad() shape when usrtau or usrang is off
  [P2] CANDIDATE c_albtrans() returns the spherical albedo/transmissivity in albmed[0]/trnmed[0]
  Not runnable from Python (listed with the reason): BRDF cases 6d-6h and 7e, the ibcnd shortcut
  13a/13c, and twostr (14b).

Needs: a C compiler (gcc for pydisort 1.7.x, g++ for 1.8.x), torch, numpy, scipy, pydisort, and the
pydisort source tree at the installed version.
Run:   python ch03_disotest.py PYDISORT_SRC [--work DIR]
"""
import argparse, json, os, subprocess, sys, tempfile
import numpy as np, scipy, torch, pydisort
from pydisort import Disort, DisortOptions
from scipy.integrate import quad

FLAGS = ["usrtau", "usrang", "lamber", "planck", "onlyfl", "intensity_correction",
         "old_intensity_correction"]


def unsupported(inp):
    f = inp["flag"]
    if f["ibcnd"]:
        return "ibcnd=SPECIAL_BC: Disort.forward() rejects ibcnd != 0 (albmed/trnmed not exposed)"
    if not f["lamber"] and f["brdf_type"]:
        return f"BRDF surface (brdf_type={f['brdf_type']}): no Python option sets brdf_type"
    if f["spher"]:
        return "pseudo-spherical: zd/radius not exposed"
    if f["general_source"]:
        return "general_source: gensrc arrays not exposed"
    return None


PYD_VER = tuple(int(x) for x in pydisort.__version__.split(".")[:2])


def run_pydisort(inp, explicit=None):
    """explicit: C output record; when given, output depths and polar angles are passed as
    usrtau/usrang with the values cdisort chose (workaround for gather_rad, see below)."""
    f = dict(inp["flag"])
    if explicit is not None:
        f["usrtau"] = f["usrang"] = 1
    flags = [k for k in FLAGS if f[k]] + ["quiet"]
    op = DisortOptions().header(inp["header"][:200]).flags(",".join(flags))
    nlyr, nmom, nstr = inp["nlyr"], inp["nmom"], inp["nstr"]
    # pydisort requires nmom >= nstr (DisortImpl::reset); the padded moments are zero, which is
    # what cdisort uses internally (pmom has nmom_nstr = max(nmom, nstr) rows, zero-filled)
    nmom_py = max(nmom, nstr)
    op.ds().nlyr, op.ds().nstr, op.ds().nmom, op.ds().nphase = nlyr, nstr, nmom_py, inp["nphase"]
    op.accur(inp["accur"])
    if f["usrtau"]:
        op.user_tau(np.array(explicit["utau_out"] if explicit else inp["utau"]))
    if f["usrang"]:
        op.user_mu(np.array(explicit["umu_out"] if explicit else inp["umu"]))
    op.user_phi(np.array(inp["phi"]))
    if f["planck"]:
        op.wave_lower([inp["wvnmlo"]]).wave_upper([inp["wvnmhi"]])
    ds = Disort(op)
    stride = inp["nmom_nstr"] + 1
    pm = np.array(inp["pmom"]).reshape(nlyr, stride)
    prop = torch.zeros((1, 1, nlyr, 2 + nmom_py), dtype=torch.float64)
    prop[0, 0, :, 0] = torch.tensor(inp["dtauc"], dtype=torch.float64)
    prop[0, 0, :, 1] = torch.tensor(inp["ssalb"], dtype=torch.float64)
    prop[0, 0, :, 2:2 + nmom] = torch.tensor(pm[:, 1:nmom + 1])
    b = inp["bc"]
    t1 = lambda v: torch.tensor([v], dtype=torch.float64)
    t2 = lambda v: torch.tensor([[v]], dtype=torch.float64)
    bc = dict(umu0=t1(b["umu0"]), phi0=t1(b["phi0"]), fbeam=t2(b["fbeam"]), albedo=t2(b["albedo"]),
              fluor=t2(b["fluor"]), fisot=t2(b["fisot"]), temis=t2(b["temis"]),
              btemp=t1(b["btemp"]), ttemp=t1(b["ttemp"]))
    temf = torch.tensor([inp["temper"]], dtype=torch.float64) if f["planck"] else None
    flx = ds.forward(prop, "", temf, **bc)[0, 0].numpy()          # (ntau, [flup, rfldir+rfldn])
    ntau = flx.shape[0]
    # pydisort 1.7.x gather_flx() returns nlyr+1 rows of out->rad, which has ntau entries: with
    # ntau < nlyr+1 it reads past the allocation, so it is not called then (1.8 reads ntau rows).
    rad = np.full((ntau, 4), np.nan)
    nrow = 0
    if PYD_VER >= (1, 8) or ntau >= nlyr + 1:
        g = ds.gather_flx()[0, 0, :, :4].numpy()                   # rfldir, rfldn, flup, dfdt
        nrow = min(ntau, g.shape[0])
        rad[:nrow] = g[:nrow]
    uu = uu_note = None
    if not f["onlyfl"]:
        g = ds.gather_rad()[0, 0].numpy()                          # (nphi, ntau, numu)
        nu = len(explicit["umu_out"]) if explicit else (len(inp["umu"]) if f["usrang"] else nstr)
        if g.shape[1:] == (ntau, nu):
            uu = g
        else:  # gather_rad sizes uu from the options (user_tau/user_mu), not from cdisort's ntau/numu
            uu_note = f"gather_rad shape {g.shape} != (nphi, ntau={ntau}, numu={nu})"
    return dict(flx=flx, rad=rad, uu=uu, nrow=nrow, uu_note=uu_note)


def c_ratio(a, b):
    if b == 0.0:
        return 1.0 + a
    if a == 0.0:
        return 0.0
    return a / b


def compare(calc_rad, calc_uu, good, tol):
    """calc_rad (ntau,4) with nan for unavailable; good: dump 'out' record of the reference"""
    grad = np.array(good["rad"])[:, :4]
    nbad, worst, nchk = 0, 0.0, 0
    fmax = np.nanmax(np.abs(grad[:, :3])) if grad.size else 0.0
    bad = []
    for (lu, q), gv in np.ndenumerate(grad):
        cv = calc_rad[lu, q]
        if np.isnan(cv):
            continue
        nchk += 1
        r = c_ratio(cv, gv)
        if r < 1 - tol or r > 1 + tol:
            nbad += 1; bad.append(("rfldir rfldn flup dfdt".split()[q], int(lu), cv, gv))
        if abs(gv) > 1e-6 * fmax:
            worst = max(worst, abs(cv / gv - 1))
    if calc_uu is not None and good["uu"]:
        nphi, ntau, numu = good["nphi"], good["ntau"], good["numu"]
        guu = np.array(good["uu"]).reshape(nphi, ntau, numu)
        if calc_uu.shape != guu.shape:
            raise ValueError(f"uu shape {calc_uu.shape} != reference {guu.shape}")
        umax = guu.max()
        for idx, gv in np.ndenumerate(guu):
            cv = calc_uu[idx]
            nchk += 1
            r = c_ratio(cv, gv)
            if r < 1 - tol or r > 1 + tol:
                nbad += 1; bad.append(("uu", int(idx[1]), cv, gv))
            if abs(gv) > 1e-6 * umax:
                worst = max(worst, abs(cv / gv - 1))
    return nbad, worst, nchk, bad


def bad_depths(bad, utau):
    """utau values at which the failing ratios sit"""
    return sorted({round(utau[lu], 6) for _, lu, _, _ in bad})


def rel_diff(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = ~np.isnan(a)
    if not m.any():
        return 0.0
    scale = np.max(np.abs(b[m])) or 1.0
    return float(np.max(np.abs(a[m] - b[m]) / np.maximum(np.abs(b[m]), 1e-6 * scale)))


H, C, KB = 6.62607015e-34, 2.99792458e8, 1.380649e-23  # CODATA 2018, exact


def planck_rows(probe):
    """c_planck_func2 against int B_nu dnu with CODATA 2018 constants and with cdisort's own
    sigma-based normalisation (SIGMA = 5.67032e-8, C2 = 1.438786 cm K)."""
    rows = []
    for lo, hi, t in [(500, 700, 300), (500, 700, 250), (100, 3000, 300), (2000, 2500, 300)]:
        cd = float(subprocess.check_output([probe, str(lo), str(hi), str(t)]))
        exact = quad(lambda v: 2 * H * C**2 * (100 * v)**3 / np.expm1(H * C * 100 * v / (KB * t)) * 100,
                     lo, hi, epsabs=0, epsrel=1e-13)[0]
        x0, x1 = 1.438786 * lo / t, 1.438786 * hi / t
        own = 5.67032e-8 / np.pi * t**4 * 15 / np.pi**4 * quad(lambda x: x**3 / np.expm1(x), x0, x1,
                                                               epsabs=0, epsrel=1e-13)[0]
        rows.append((lo, hi, t, cd / exact - 1, cd / own - 1))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pydisort_src")
    ap.add_argument("--work", default=None)
    a = ap.parse_args()
    tol = 0.01
    work = a.work or tempfile.mkdtemp(prefix="ch03_disotest_")
    os.makedirs(work, exist_ok=True)
    torch.set_num_threads(1)
    here = os.path.dirname(os.path.abspath(__file__))
    src = os.path.abspath(a.pydisort_src)
    sha = subprocess.run(["git", "-C", src, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    print(f"python {sys.version.split()[0]}, torch {torch.__version__}, numpy {np.__version__}, "
          f"scipy {scipy.__version__}, pydisort {pydisort.__version__}")
    print(f"pydisort source {sha or 'not a git tree'}")
    subprocess.run([os.path.join(here, "ch03_disotest", "build.sh"), src, work], check=True)
    dump = os.path.join(work, "dump.jsonl")
    clog = subprocess.run([os.path.join(work, "test_cdisort")], cwd=work, capture_output=True, text=True,
                          env=dict(os.environ, DUMP_FILE=dump)).stdout
    recs = [json.loads(line) for line in open(dump)]
    runs = {r["id"]: r for r in recs if r["kind"] == "run"}
    py = {}
    for i, r in runs.items():
        why = unsupported(r["in"])
        if why:
            py[i] = dict(skip=why)
            continue
        try:
            py[i] = run_pydisort(r["in"])
        except Exception as e:  # report, do not stop the suite
            py[i] = dict(skip=f"pydisort error: {str(e).splitlines()[0][:160]}")

    rows, shapes, vs_c_max = [], [], 0.0
    for c in (r for r in recs if r["kind"] == "check"):
        name = c["calc_header"].replace("Test Case No. ", "").split(":")[0].split(",")[0].strip()
        crad = np.array(c["calc"]["rad"])[:, :4]
        cuu = (np.array(c["calc"]["uu"]).reshape(c["calc"]["nphi"], c["calc"]["ntau"], c["calc"]["numu"])
               if c["calc"]["uu"] else None)
        cbad = compare(crad, cuu, c["good"], tol)
        row = dict(case=name, C=cbad)
        pc = py.get(c["calc_run"])
        if pc is None or "skip" in pc:
            row["skip"] = (pc or {}).get("skip", "calc is twostr(): pydisort binds no twostr")
            rows.append(row)
            continue
        rad = pc["rad"].copy()
        rad[:, 2] = pc["flx"][:, 0]  # flup at every output depth, from forward()
        crun = runs[c["calc_run"]]["out"]
        vs_c = max(rel_diff(pc["flx"][:, 0], np.array(crun["rad"])[:, 2]),
                   rel_diff(pc["rad"][:pc["nrow"]], np.array(crun["rad"])[:pc["nrow"], :4]),
                   rel_diff(pc["uu"], np.array(crun["uu"]).reshape(pc["uu"].shape))
                   if pc["uu"] is not None else 0.0)
        vs_c_max = max(vs_c_max, vs_c)
        row["py"] = compare(rad, pc["uu"], c["good"], tol)
        row["vs_c"] = vs_c
        if pc["uu_note"]:  # gather_rad shape: rerun with cdisort's output depths and angles passed
            shapes.append((name, pc["uu_note"]))
            pe = run_pydisort(runs[c["calc_run"]]["in"], explicit=crun)
            rad = pe["rad"].copy()
            rad[:, 2] = pe["flx"][:, 0]
            row["py"] = compare(rad, pe["uu"], c["good"], tol)
            row["explicit"] = True
        rows.append(row)

    print(f"{'case':5} {'C fails':>7} {'C maxrel':>9} {'py fails':>8} {'py maxrel':>9} {'py vs C':>8}")
    for r in rows:
        if "skip" in r:
            print(f"{r['case']:5} {r['C'][0]:7d} {r['C'][1]:9.1e} {'not run':>8}  {r['skip']}")
        else:
            print(f"{r['case']:5} {r['C'][0]:7d} {r['C'][1]:9.1e} {r['py'][0]:8d} {r['py'][1]:9.1e} "
                  f"{r['vs_c']:8.1e}{'  (utau/umu passed explicitly)' if r.get('explicit') else ''}")
    nfail = 0
    pub = [r for r in rows if r["case"][:-1].isdigit() and int(r["case"][:-1]) <= 9 and "skip" not in r]
    ok = all(r["py"][0] == 0 for r in pub)
    nfail += not ok
    print(f"[C1] {'PASS' if ok else 'FAIL'} published-reference cases 1-9: {sum(r['py'][0] == 0 for r in pub)}"
          f" of {len(pub)} runnable cases pass the ratio rule; largest maxrel "
          f"{max(r['py'][1] for r in pub):.1e} (references carry 5-6 digits)")
    sc = [r for r in rows if r["case"] in ("10b", "11b")]
    ok = len(sc) == 2 and all(r["py"][0] == 0 for r in sc)
    nfail += not ok
    print(f"[C2] {'PASS' if ok else 'FAIL'} self-consistency 10b, 11b: maxrel "
          + ", ".join(f"{r['case']} {r['py'][1]:.1e}" for r in sc))
    r12 = [r for r in rows if r["case"] == "12b"]
    ok = len(r12) == 1 and r12[0]["py"][0] == r12[0]["C"][0] > 0
    nfail += not ok
    print(f"[C3] {'PASS' if ok else 'FAIL'} case 12b fails by design, identically: C {r12[0]['C'][0]} "
          f"ratios outside the rule, pydisort {r12[0]['py'][0]}, at utau "
          f"{bad_depths(r12[0]['py'][3], runs[[c for c in recs if c['kind'] == 'check' and 'Test Case No. 12b' in c['calc_header']][0]['calc_run']]['out']['utau_out'])}")
    ok = vs_c_max == 0.0
    nfail += not ok
    print(f"[C4] {'PASS' if ok else 'FAIL'} pydisort vs C on every runnable case: max rel diff {vs_c_max:.1e} (tol 0)")
    pr = planck_rows(os.path.join(work, "planck_probe"))
    ok = max(abs(p[4]) for p in pr) <= 5e-6
    nfail += not ok
    print(f"[C5] {'PASS' if ok else 'FAIL'} c_planck_func2: vs CODATA 2018 "
          + ", ".join(f"[{p[0]},{p[1]}] cm-1 {p[2]} K {p[3]:+.2e}" for p in pr)
          + f"; vs its own constants max {max(abs(p[4]) for p in pr):.1e} (tol 5e-6)")

    # case 13: a/c use the ibcnd shortcut (C only, printed table), b/d the same media by brute force
    printed, case, lines = {}, None, clog.splitlines()
    for i, line in enumerate(lines):
        if "Test Case No. 13" in line:
            case = line.split("Test Case No. ")[1].split(":")[0].strip()
        if "Flux Albedo and/or Transmissivity" in line and case:
            v = lines[i + 2].split()
            printed[case] = (float(v[2]), float(v[3]))
    byname = {r["in"]["header"].replace("Test Case No. ", "").split(":")[0].strip(): (i, r)
              for i, r in runs.items()}
    worst13, returned = 0.0, []
    for s, b in (("13a", "13b"), ("13c", "13d")):
        i, rb = byname[b]
        inc = rb["in"]["bc"]["umu0"] * rb["in"]["bc"]["fbeam"]
        fl = py[i]["flx"]
        alb, trn = fl[0, 0] / inc, fl[-1, 1] / inc
        worst13 = max(worst13, abs(alb / printed[s][0] - 1), abs(trn / printed[s][1] - 1))
        returned.append((s, printed[s][0], byname[s][1]["out"]["albmed"][0], byname[s][1]["out"]["trnmed"][0]))
    ok = worst13 <= 1e-5
    nfail += not ok
    print(f"[C6] {'PASS' if ok else 'FAIL'} case 13 brute force vs printed shortcut albedo/transmissivity: "
          f"max rel dev {worst13:.1e} (tol 1e-5)")
    print(f"[P1] CANDIDATE {'reproduced' if shapes else 'not reproduced'}: gather_rad() shape with usrtau/usrang off: "
          + "; ".join(f"{n} {s}" for n, s in shapes))
    print("[P2] CANDIDATE " + ("reproduced" if any(abs(r[2] / r[1] - 1) > 1e-3 for r in returned) else "not reproduced")
          + ": c_albtrans() albmed[0]/trnmed[0] after the call vs the printed beam albedo: "
          + "; ".join(f"{s} printed {p:.5f}, returned albmed[0] {al:.6f}, trnmed[0] {tr:.6f}" for s, p, al, tr in returned))
    print(f"summary: {len([r for r in rows if 'skip' not in r])} cases run, {len([r for r in rows if 'skip' in r])} not runnable")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
