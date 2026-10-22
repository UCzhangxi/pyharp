"""ch05: CPU wall time per column of Toon89 (shortwave and thermal) and of DISORT by stream count.

Columns of NLYR layers with random optical properties (seed 0); NCOL columns per call; the best of REPEAT calls,
for torch.set_num_threads(1) and for torch's default thread count. Time per column = call time / NCOL, and it
includes building the input tensors and the solver object of each call. A measurement on one host, not a gate:
the check fails only if a solver errors or returns a non-finite flux.

Run: python3 check_ch05_cost.py [--data DIR]  (about 30 s). Exit status: the number of FAIL lines.
"""

import argparse
import json
import os
import platform
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch05_common as C  # noqa: E402

NLYR, NCOL, REPEAT = 50, 256, 3
NSTR = [4, 8, 16, 32, 64]


def columns(seed=0):
    rng = np.random.default_rng(seed)
    tau = 10 ** rng.uniform(-3, 0, (NCOL, NLYR))
    ssa = rng.uniform(0.0, 0.99, (NCOL, NLYR))
    g = rng.uniform(0.0, 0.85, (NCOL, NLYR))
    mu0 = rng.uniform(0.1, 1.0, NCOL)
    alb = rng.uniform(0.0, 0.5, NCOL)
    temf = np.linspace(180.0, 300.0, NLYR + 1)[None, :] + rng.uniform(-5, 5, (NCOL, NLYR + 1))
    return tau, ssa, g, mu0, alb, temf


def bench(threads):
    torch.set_num_threads(threads)
    tau, ssa, g, mu0, alb, temf = columns()
    rows = {}
    t, f = C.timed(lambda: C.run_toon_sw(tau, ssa, g, mu0, alb), REPEAT)
    rows["Toon SW"] = (t / NCOL, bool(np.isfinite(f).all()))
    t, f = C.timed(lambda: C.run_toon_lw(tau, ssa, g, temf, alb, 500.0, 1000.0), REPEAT)
    rows["Toon LW"] = (t / NCOL, bool(np.isfinite(f).all()))
    for ns in NSTR:
        pm = C.hg_moments(g, ns)
        t, f = C.timed(lambda: C.run_disort_sw(ns, tau, ssa, pm, mu0, alb), REPEAT)
        rows[f"DISORT SW nstr={ns}"] = (t / NCOL, bool(np.isfinite(f).all()))
        t, f = C.timed(lambda: C.run_disort_lw(ns, tau, ssa, pm, temf, alb, 500.0, 1000.0), REPEAT)
        rows[f"DISORT LW nstr={ns}"] = (t / NCOL, bool(np.isfinite(f).all()))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data")
    a = ap.parse_args()
    print(C.version_line())
    print(C.env_line())
    print(f"host: {platform.processor() or platform.machine()}, {os.cpu_count()} logical CPUs, "
          f"torch default threads {torch.get_num_threads()}")
    ck = C.Checker()
    default = torch.get_num_threads()
    data = {}
    for th in [1, default]:
        rows = bench(th)
        data[str(th)] = {k: v[0] for k, v in rows.items()}
        base = rows["Toon SW"][0]
        for k, (t, ok) in rows.items():
            if ok:
                ck.info(f"{th} thread(s), {NLYR} layers, {NCOL} columns: {k}",
                        f"{t * 1e6:.1f} us/column ({t / base:.1f} x Toon SW)")
            else:
                ck.check(f"{th} thread(s) {k}: non-finite flux", 1.0, 0.0)
    torch.set_num_threads(default)
    if a.data:
        os.makedirs(a.data, exist_ok=True)
        with open(os.path.join(a.data, "cost.json"), "w") as f:
            json.dump({"nstr": NSTR, "threads": data, "nlyr": NLYR, "ncol": NCOL}, f, indent=1)
    sys.exit(ck.done("check_ch05_cost"))


if __name__ == "__main__":
    main()
