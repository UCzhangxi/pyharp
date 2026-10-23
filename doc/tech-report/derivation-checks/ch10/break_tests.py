#!/usr/bin/env python3
"""Chapter 10 check: break tests and floor effects for invariants.py, opacity_probe.py and floor_inventory.py.

usage: python3 break_tests.py <environment made by setup_env.sh> <scratch dir> [--only B1,V3,...] [--csv <file>]

Clones the environment's pyharp tree (at the pin of code_pin.yml) into <scratch>/tree, builds libharp there, and
runs the checks against a copy of the installed pyharp package whose libharp is replaced by the scratch build.
Then, one mutation at a time, it edits one line of the scratch tree (MUTATIONS: the exact old text, the new text),
rebuilds, reruns the checks, records which labels go red and how far every flux moves against the unmutated
build, and restores the line. Nothing outside <scratch> is written; the mutated sources are never committed.

B<n>  break test: the mutation removes the term or the floor a check exists for; the check must go red.
V<n>  floor effect: the floor set to 0 or 1e-300, or removed; reports the largest flux shift over every case
      (relative to the case's largest flux) against the closure tolerance 1e-10, and the labels that go red.
Prints `[B0]` the baseline, one `[Bn]`/`[Vn]` line per mutation, `[B99]` the state of the scratch tree. Exits with
the number of break tests whose check stayed green.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PIN = re.search(r"^sha: ([0-9a-f]{40})", (HERE.parent.parent / "code_pin.yml").read_text(), re.M).group(1)
TOL = 1e-10
SW = "src/rtsolver/toon_mckay89_shortwave_impl.h"
LW = "src/rtsolver/toon_mckay89_longwave_impl.h"
BAND = "src/radiation/radiation_band.cpp"

# id, the check it targets (B) or "-" (V), file, old text, new text, replace every occurrence, what it does
MUTATIONS = [
    ("B1", "E1", SW, "T bsurf = w_surf_in * dir[nlev - 1];", "T bsurf = 0.0;", False,
     "drop the surface reflection of the beam (shortwave bottom row)"),
    ("B2", "E2", SW, "FLX_DN(n) = xk1[n] * gam[n] + xk2[n] + Cmm1[n];", "FLX_DN(n) = xk1[n] * gam[n] + xk2[n];",
     False, "drop the particular solution from the level downward flux"),
    ("B3", "E3", LW, "xk[k] * down_ratio + sigma1[k] * (1.0 - em2) +", "xk[k] * down_ratio +", False,
     "drop the layer emission from the downward intensity sweep"),
    ("B4", "E4", "src/radiation/calc_dz_hypsometric.cpp", "return temp * dlnp / g_ov_R;", "return temp / g_ov_R;",
     False, "drop d ln p from the hypsometric thickness"),
    ("B5", "P1", BAND, "prop.select(-1, disort::ISS).clamp_max_(1.0 - ssa_margin);", ";", False,
     "remove the single-scattering albedo clamp (omega = 1 reaches the solvers)"),
    ("B6", "P2", SW, "for (int k = 0; k < nlev; k++) FLX_DN(k) += dir[k];",
     "for (int k = 0; k < nlev; k++) FLX_DN(k) += dir[0];", False,
     "drop the attenuation of the beam added to the downward flux"),
    ("B17", "P4", LW, "(wsum != 0.0 ? a_surf_in * fdn_surf / wsum : 0.0);",
     "(wsum != 0.0 ? 2.0 * a_surf_in * fdn_surf / wsum : 0.0);", False,
     "double the surface reflection of the longwave intensity (reflectance 2A)"),
    ("B8", "Z1", BAND, "torch::where(positive, denominator, torch::ones_like(denominator));", "denominator;", False,
     "divide_where_positive divides by the raw weight (plain division) ..."),
    ("B8b", "Z1", BAND, "return torch::where(positive, numerator / safe_denominator,",
     "return torch::where(torch::ones_like(positive), numerator / safe_denominator,", False,
     "... and keeps the quotient everywhere (applied together with B8)"),
    ("B9", "Z1", LW, "return x == static_cast<T>(0) ? static_cast<T>(1) : expm1(x) / x;", "return expm1(x) / x;",
     False, "remove the x = 0 limit of expm1(x)/x"),
    ("B10", "Z2", LW, "if (dtau[k] <= 1.0e-6) {", "if (dtau[k] <= 0.0) {", False,
     "linear-in-tau Planck function down to dtau = 0 (threshold 1e-6 -> 0)"),
    ("B11", "T1", SW, "FLX_DN(k) = F0_in * MU_IN(nlev - 1) * exp(-tau_in[k] / MU_IN(nlev - 1));",
     "FLX_DN(k) = F0_in * MU_IN(nlev - 1) * exp(-tau_in[k]);", False,
     "drop the slant path 1/mu0 from the beam-only formula"),
    ("B12", "T3", LW, "B0[k] = 0.5 * (BE_IN(k + 1) + BE_IN(k));", "B0[k] = 0.0;", False,
     "drop the emission of the layers on the constant-Planck side of the switch"),
    ("B13", "T4", SW, "T const res_tol = sqrt(std::numeric_limits<T>::epsilon());", "T const res_tol = 0.0;", False,
     "remove the resonance shift of mu0 (sqrt(eps) -> 0)"),
    ("B14", "Z4", "src/opacity/water_cloud_temperature.cpp",
     "torch::where(positive, denominator, torch::ones_like(denominator));", "denominator;", False,
     "the cloud switch's divide_where_positive divides by the raw weight (plain division) ..."),
    ("B14b", "Z4", "src/opacity/water_cloud_temperature.cpp",
     "return torch::where(positive, numerator / safe_denominator,",
     "return torch::where(torch::ones_like(positive), numerator / safe_denominator,", False,
     "... and keeps the quotient everywhere (applied together with B14)"),
    ("B15", "Z5", "src/opacity/picaso_ck.cpp", ".clamp_min(1.e-300)", ".clamp_min(1.e-30)", False,
     "raise the picaso-ck table floor to 1e-30 (the probe reads the constant from the tree)"),
    ("B16", "F9", BAND, "  // run rt solver", "  prop.clamp_min_(1.0e-300);\n  // run rt solver", False,
     "add an unlisted floor (the inventory scans the tree)"),
    ("V1", "-", SW, "if (W_IN(i) > 1.0e-12) {", "if (W_IN(i) > 0.0) {", False, "beam-only switch 1e-12 -> 0"),
    ("V2", "-", SW, "if (w_surf_in > 1.0e-12) {", "if (w_surf_in > 0.0) {", False, "surface-albedo switch 1e-12 -> 0"),
    ("V3", "-", SW, "if (g2 == 0.0) g2 = 1.0e-10;", "if (g2 == 0.0) g2 = 1.0e-300;", False,
     "gamma_2 floor 1e-10 -> 1e-300"),
    ("V4", "-", SW, "if (g2 == 0.0) g2 = 1.0e-10;", ";", False, "gamma_2 floor removed"),
    ("V5", "-", SW, "T exptrm = fmin(lam * dtau[i], 35.0);", "T exptrm = lam * dtau[i];", False,
     "shortwave exp(35) cap removed"),
    ("V6", "-", SW, "if (fabs(xk2[n]) < 1e-30 * fabs(xk[2 * n + 1])) xk2[n] = 0.0;", ";", False,
     "shortwave xk2 zeroing removed"),
    ("V7", "-", SW, "T dir_mid = sqrt(fmax(dir_k * dir_kp1, (T)0.0));", "T dir_mid = sqrt(dir_k * dir_kp1);", False,
     "midpoint beam floor removed"),
    ("V9", "-", LW, "if (w0[n] <= 1e-4) {", "if (w0[n] <= 0.0) {", False, "longwave scattering switch 1e-4 -> 0"),
    ("V11", "-", LW, "35.0", "700.0", True, "longwave exp(35) caps and their thresholds -> 700"),
    ("V12", "-", LW, "if (fabs(xk2[n]) < 1e-30 * fabs(xkk[2 * n + 1])) xk2[n] = 0.0;", ";", False,
     "longwave xk2 zeroing removed"),
    ("V13", "-", LW, "(wsum != 0.0 ? a_surf_in * fdn_surf / wsum : 0.0);", "a_surf_in * fdn_surf / wsum;", False,
     "weight-sum guard removed"),
    ("V15", "-", LW, "return a * exp(-fmin(a, b)) * longwave_exprel(-fabs(delta * a));",
     "return a * exp(-a) * longwave_exprel(-fabs(delta * a));", False, "resonant ratio fmin(a, b) -> a"),
    ("V16", "-", "src/rtsolver/dtridgl_impl.h", "if (denom == 0.0) denom = 1e-12;", ";", False,
     "zero-pivot floor removed"),
    ("V19", "-", "src/opacity/water_cloud_temperature.cpp", ".clamp(0.0, 1.0);", ";", False,
     "liquid-fraction clamp removed"),
    ("V20", "-", "src/opacity/water_ice_fu96_98.cpp", "torch::where(fu96_mask, ssa96, ssa98).clamp(0.0, 1.0), 0.0);",
     "torch::where(fu96_mask, ssa96, ssa98), 0.0);", False, "Fu omega clamp removed"),
    ("V21", "-", "src/opacity/water_ice_fu96_98.cpp", "torch::where(fu96_mask, g96, g98).clamp(-0.999999, 0.999999), 0.0);",
     "torch::where(fu96_mask, g96, g98), 0.0);", False, "Fu g clamp removed"),
    ("V22", "-", "src/opacity/water_ice_fu96_98.cpp", "auto const lookup_wavelength = wavelength.clamp(0.25, 100.0);",
     "auto const lookup_wavelength = wavelength;", False, "Fu lookup-wavelength clamp removed"),
    ("V23", "-", "src/opacity/water_ice_fu96_98.cpp", "sun_rikus_dge(temp, safe_iwc).clamp(kDiagnosedMinDge, kDiagnosedMaxDge);",
     "sun_rikus_dge(temp, safe_iwc);", False, "diagnosed ice-size clamp removed"),
    ("V24", "-", "src/opacity/water_ice_fu96_98.cpp", "f96 = torch::minimum(f96, g96);", ";", False,
     "Fu96 f <= g bound removed"),
    ("V25", "-", "src/opacity/water_liquid_mie_impl.h", "static_cast<T>(-0.999999), static_cast<T>(0.999999))",
     "static_cast<T>(-1e300), static_cast<T>(1e300))", False, "Mie |g| clamp removed (bounds -> +-1e300)"),
    ("V26", "-", "src/opacity/water_liquid_mie_impl.h", "if (out.qext < out.qsca) out.qext = out.qsca;", ";", False,
     "Mie qext >= qsca floor removed"),
    ("V27", "-", "src/math/interpolation.cpp", "out.weight_high = torch::clamp(out.weight_high, 0.0, 1.0);", ";",
     False, "interpolation weight clamp removed (linear extrapolation)"),
]
TOGETHER = {"B8": ["B8b"], "B14": ["B14b"]}  # mutations applied as one
SKIP_ALONE = {"B8b", "B14b"}


def sh(cmd, cwd=None, env=None, log=None):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, shell=isinstance(cmd, str))
    if log:
        Path(log).write_text(r.stdout + r.stderr)
    return r


def line_of(path: Path, text: str) -> int:
    for i, l in enumerate(path.read_text().splitlines(), 1):
        if text.split("\n")[0] in l:
            return i
    return 0


def run_checks(py, pkgdir, tree, scratch, tag):
    """Run the three checks against the scratch package; return {label: status}, candidate lines, dumps."""
    status = {}
    boot = ("import sys, runpy; sys.path.insert(0, {p!r}); sys.argv = [{s!r}] + {a!r}; "
            "runpy.run_path({s!r}, run_name='__main__')")
    outs = {}
    for name, args in (("invariants", ["--dump", f"{scratch}/{tag}.inv.npz", "--csv", f"{scratch}/{tag}.inv.csv"]),
                       ("opacity_probe", ["--tree", str(tree), "--dump", f"{scratch}/{tag}.opa.npz"])):
        script = str(HERE / f"{name}.py")
        r = sh([py, "-I", "-c", boot.format(p=str(pkgdir), s=script, a=args)], cwd=scratch)
        outs[name] = r.stdout + r.stderr
        Path(f"{scratch}/{tag}.{name}.txt").write_text(outs[name])
    r = sh([py, "-I", str(HERE / "floor_inventory.py"), str(tree)])
    outs["floor_inventory"] = r.stdout
    for text in outs.values():
        for m in re.finditer(r"^\[([A-Z]+\d+b?)\] (PASS|FAIL|CANDIDATE (?:reproduced|not reproduced))", text, re.M):
            status[m.group(1)] = m.group(2)
    crashed = [n for n, t in outs.items() if "Traceback" in t]
    return status, crashed, outs


def csv_value(path: Path, label: str):
    """The value and tolerance invariants.py wrote for a label, or (inf, nan) when it wrote none."""
    if path.exists():
        for line in path.read_text().splitlines()[1:]:
            parts = line.rsplit(",", 3)
            if line.startswith(label + ","):
                return float(parts[1]), float(parts[2])
    return float("inf"), float("nan")


def shift(base: dict, new: dict):
    """Largest |new - base| over every case, relative to the case's largest |base| value; non-finite count."""
    worst, where, nonfinite = 0.0, "", 0
    groups = {}
    for k in base.files:
        g = k.rsplit("|", 1)[0] if "|" in k else k
        groups.setdefault(g, []).append(k)
    for g, keys in groups.items():
        S = max(float(np.max(np.abs(base[k]))) for k in keys) or 1.0
        for k in keys:
            if k not in new.files:
                continue
            v = new[k]
            if not np.all(np.isfinite(v)):
                nonfinite += 1
                continue
            d = float(np.max(np.abs(v - base[k]))) / S
            if d > worst:
                worst, where = d, g
    return worst, where, nonfinite


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("env")
    ap.add_argument("scratch")
    ap.add_argument("--only")
    ap.add_argument("--csv")
    args = ap.parse_args()
    table = []
    env = Path(args.env).resolve()
    scr = Path(args.scratch).resolve()
    scr.mkdir(parents=True, exist_ok=True)
    py = str(env / "venv/bin/python")
    site = Path(sh([py, "-c", "import pyharp, os; print(os.path.dirname(pyharp.__file__))"]).stdout.strip())
    tree = scr / "tree"
    if not tree.exists():
        sh(["git", "clone", "-q", str(env / "pyharp"), str(tree)])
        sh(["git", "-C", str(tree), "checkout", "-q", PIN])
    assert sh(["git", "-C", str(tree), "rev-parse", "HEAD"]).stdout.strip() == PIN
    benv = dict(os.environ, PATH=f"{env}/venv/bin:{os.environ['PATH']}")
    if not (tree / "build/CMakeCache.txt").exists():
        r = sh("cmake -B build -DCMAKE_BUILD_TYPE=Release -DNETCDF=ON -DBUILD_TESTS=OFF -DBUILD_EXAMPLES=OFF",
               cwd=tree, env=benv, log=scr / "configure.log")
        assert r.returncode == 0, "configure failed"
    pkg = scr / "py"
    if not (pkg / "pyharp").exists():
        shutil.copytree(site, pkg / "pyharp")

    def build(tag):
        r = sh("cmake --build build --target harp_release --parallel 6", cwd=tree, env=benv,
               log=scr / f"{tag}.build.log")
        if r.returncode != 0:
            return False
        lib = next((tree / "build/lib").glob("libharp_release.so"))
        shutil.copy2(lib, pkg / "pyharp/lib/libharp_release.so")
        return True

    assert build("base"), "the unmutated scratch build failed"
    base_status, crashed, outs = run_checks(py, pkg, tree, scr, "base")
    base_inv = np.load(scr / "base.inv.npz")
    base_opa = np.load(scr / "base.opa.npz")
    fails = [k for k, v in base_status.items() if v == "FAIL"]
    print(f"[B0] unmutated scratch build of pyharp@{PIN}: {len(base_status)} labels, red: {fails or 'none'}; "
          f"imports {outs['invariants'].splitlines()[0][5:60]}...")

    only = set(args.only.split(",")) if args.only else None
    green_breaks = 0
    for mid, target, path, old, new, every, what in MUTATIONS:
        if mid in SKIP_ALONE or (only and mid not in only):
            continue
        group = [(mid, path, old, new, every)] + [(m[0], m[2], m[3], m[4], m[5]) for m in MUTATIONS
                                                  if m[0] in TOGETHER.get(mid, [])]
        saved = {}
        sites = []
        okapply = True
        for gid, gpath, gold, gnew, gevery in group:
            f = tree / gpath
            text = saved.get(gpath, f.read_text())
            saved.setdefault(gpath, text)
            cur = f.read_text()
            n = cur.count(gold)
            if n == 0 or (n > 1 and not gevery):
                okapply = False
                print(f"[{mid}] NOT APPLIED: '{gold}' occurs {n} times in {gpath}")
                break
            sites.append(f"{gpath}:{line_of(tree / gpath, gold)}")
            f.write_text(cur.replace(gold, gnew) if gevery else cur.replace(gold, gnew, 1))
        if okapply:
            built = build(mid)
            if built:
                status, crashed, outs = run_checks(py, pkg, tree, scr, mid)
                red = sorted(k for k, v in status.items() if v == "FAIL" and (k != "F9" or target == "F9"))
                stopped = sorted({m.group(0)[:120] for t in outs.values()
                                  for m in re.finditer(r"(RuntimeError|\*\*error|double free|Segmentation)[^\n]*", t)})
                flips = sorted(k for k, v in status.items() if v.startswith("CANDIDATE") and v != base_status.get(k))
                missing = sorted(k for k in base_status if k not in status)
                try:
                    si = shift(base_inv, np.load(scr / f"{mid}.inv.npz"))
                    so = shift(base_opa, np.load(scr / f"{mid}.opa.npz"))
                except FileNotFoundError:
                    si = so = (float("nan"), "no dump", 0)
                s = max((si, so), key=lambda x: (x[2], x[0]))
                eff = ("no flux dump" if s[1] == "no dump" else f"max shift {s[0]:.1e} of the case's largest flux at {s[1] or '-'}"
                       + (f", {si[2] + so[2]} non-finite arrays" if si[2] + so[2] else ""))
                if target != "-":
                    v, _ = csv_value(scr / f"{mid}.inv.csv", target)
                    b, t = csv_value(scr / "base.inv.csv", target)
                    if b != float("inf"):  # a label of invariants.py (the others print no value table)
                        table.append((mid, target, b, v, t))
                    hit = target in red or target in missing
                    green_breaks += not hit
                    verdict = f"{target} RED" if hit else f"{target} STAYED GREEN"
                elif missing:
                    verdict = "a check stopped"
                else:
                    big = s[0] > TOL or (si[2] + so[2]) > 0
                    verdict = f"{'shifts more than' if big else 'within'} the tolerance {TOL:.0e}"
                print(f"[{mid}] {what} | {'; '.join(sites)}@{PIN} | {verdict} | red: {red or 'none'}"
                      + (f" | no output: {missing}" if missing else "") + (f" | stopped: {stopped}" if stopped else "")
                      + (f" | candidates changed: {flips}" if flips else "")
                      + f" | {eff}")
            else:
                if target != "-":
                    green_breaks += 1
                print(f"[{mid}] {what} | {'; '.join(sites)}@{PIN} | does not compile")
        for gpath, text in saved.items():
            (tree / gpath).write_text(text)
    if args.csv:
        with open(args.csv, "w") as f:
            f.write("id,check,value_pin,value_broken,tolerance\n")
            for mid, target, b, v, t in table:
                f.write(f"{mid},{target},{b:.3e},{v:.3e},{t:.0e}\n")
    build("restore")
    dirty = sh(["git", "-C", str(tree), "status", "--porcelain", "--untracked-files=no"]).stdout.strip()
    print(f"[B99] scratch tree restored to pyharp@{PIN}: {'clean' if not dirty else 'DIRTY ' + dirty}; "
          f"{green_breaks} break tests stayed green")
    return green_breaks


if __name__ == "__main__":
    sys.exit(main())
