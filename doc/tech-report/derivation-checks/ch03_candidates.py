"""ch03 probes for defect CANDIDATES in the pyharp -> pydisort -> cdisort path.

Every probe runs in its own Python subprocess, because several of them end the process (exit(1)
from cdisort, or an abort from the C heap checker). Each prints one line
"[Pn] CANDIDATE reproduced|not reproduced: ..." with the subprocess return code and what it saw.
None of these is a pass/fail check: the script exits 0 whatever the probes find, and exits 1 only
if a probe could not be run at all.

  [P1] moment overflow in pydisort: prop carries more moments than ds.nmom (nstr = nmom = 4, eight
       moments supplied, three layers). With upward = 1 (pyharp's setting) the fluxes change and
       the process then ends abnormally; with upward = 0 they do not change, and the process ends
       abnormally. Heap corruption is not deterministic, so [P1] and [P2] run --repeat times (default
       10) and report how many runs ended abnormally and with which return codes (-6 abort, -11
       segmentation fault).
  [P2] the same overflow reached through pyharp: a Rayleigh opacity with nmom: 8 on a 4-stream
       DISORT band.
  [P3] a DISORT band called without 'tempf' or 'temp' raises (pydisort's default for the temperature
       argument has the wrong type).
  [P4] a DISORT band whose YAML has no 'flags:' key: cdisort is called with lamber off and BRDF type
       0, prints an error and calls exit(1), ending the Python process.
  [P5] the Buras-Emde intensity correction ('intensity_correction' without 'old_intensity_correction')
       from pydisort: with nphase = 0 the process exits; with nphase = nstr (no phase table can be
       passed) the radiances are not finite.
  [P6] an input error cdisort reports (user_mu not in increasing order) is printed, and pydisort
       returns normally with no exception.

Needs: torch, numpy, pydisort and a pyharp built against that pydisort.
Run:   python ch03_candidates.py [--work DIR]
Pins:  PYHARP_WT and PYDISORT_SRC name the source trees; their commits are printed.
"""
import argparse
import os
import subprocess
import sys
import tempfile
import textwrap

import numpy as np
import pydisort
import torch

PRE = """
import json, math, sys, numpy as np, torch
from pydisort import Disort, DisortOptions, scattering_moments
torch.set_num_threads(1)
def say(**k):
    print("RESULT " + json.dumps(k), flush=True)
"""

P1 = PRE + """
keep = []
def run(upward, nprop_mom):
    op = DisortOptions().header("ch03").flags("lamber,quiet,onlyfl")
    op.ds().nlyr, op.ds().nstr, op.ds().nmom = 3, 4, 4
    op.upward(upward)
    ds = Disort(op)
    prop = torch.zeros((1, 1, 3, 2 + nprop_mom), dtype=torch.float64)
    for i, g in enumerate((0.85, 0.3, 0.6)):
        prop[0, 0, i, 0] = 1.0
        prop[0, 0, i, 1] = 0.9
        prop[0, 0, i, 2:] = scattering_moments(nprop_mom, "henyey-greenstein", g)
    keep.append(ds)  # freeing a corrupted solver aborts; keep it alive until the result is printed
    return ds.forward(prop, umu0=torch.tensor([0.5], dtype=torch.float64), phi0=torch.zeros(1, dtype=torch.float64),
                      fbeam=torch.tensor([[math.pi]], dtype=torch.float64), albedo=torch.zeros((1, 1), dtype=torch.float64))
up = int(sys.argv[1])
a = run(up, 4)
b = run(up, 8)
say(upward=up, max_abs_diff=(a - b).abs().max().item(), flup_top_4=a[0, 0, -1 if up else 0, 0].item(),
    flup_top_8=b[0, 0, -1 if up else 0, 0].item())
"""

YAML_RAY = """species:
  - name: H2
    composition: {{H: 2}}
geometry:
  cells:
    nx1: 3
opacities:
  rayleigh:
    type: rayleigh
    species: [H2]
    nmom: {nmom}
bands:
  - name: sw
    range: [19999.5, 20000.5]
    opacities: [rayleigh]
    solver: disort
    nwave: 1
    nstr: 4
    flags: lamber,quiet,onlyfl
"""

P2 = PRE + """
import pyharp
res, keep = {}, []
for n, path in ((4, sys.argv[1]), (8, sys.argv[2])):
    b = pyharp.RadiationOptions.from_yaml(path).bands()[0]
    b.wavenumber([20000.0]); b.weight([1.0])
    b.set_wave_lower([19999.5]); b.set_wave_upper([20000.5])
    band = pyharp.RadiationBand(b)
    flx = band.forward(torch.ones((1, 3, 1), dtype=torch.float64), torch.full((3,), 3.0e3, dtype=torch.float64),
                       {"sw/fbeam": torch.ones((1, 1), dtype=torch.float64),
                        "sw/umu0": torch.tensor([0.5], dtype=torch.float64),
                        "sw/albedo": torch.zeros((1, 1), dtype=torch.float64)},
                       {"temp": torch.full((1, 3), 300.0, dtype=torch.float64)})
    res[n] = flx.clone()
    keep.append(band)  # freeing a corrupted solver aborts; keep it alive until the result is printed
    say(nmom=n, nprop=band.buffer("prop").shape[-1],
        max_abs_diff=(res[4] - res[n]).abs().max().item(), flux_scale=res[4].abs().max().item())
"""

YAML_SLAB = """species:
  - name: X
    composition: {{H: 2}}
geometry:
  cells:
    nx1: 4
opacities:
  slab:
    type: jit
    species: [X]
    nmom: 4
    data: [{pt}]
bands:
  - name: sw
    range: [10000.0, 20000.0]
    opacities: [slab]
    solver: disort
    nwave: 1
    nstr: 4
{flags}"""

P34 = PRE + """
import pyharp
class Slab(torch.nn.Module):
    def __init__(self):
        super().__init__()
    def forward(self, conc: torch.Tensor) -> torch.Tensor:
        out = torch.zeros((1, conc.shape[0], conc.shape[1], 6), dtype=torch.float64)
        out[..., 0].fill_(1.0e-3)
        out[..., 1].fill_(0.5)
        for m in range(1, 5):
            out[..., 1 + m].fill_(0.5 ** m)
        return out
work, flags, with_t = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
pt = work + "/slab.pt"
pyharp.compile(Slab(), pt)
yp = work + "/slab_" + str(len(flags)) + str(int(with_t)) + ".yaml"
open(yp, "w").write(YAML_SLAB.format(pt=pt, flags=("    flags: " + flags + "\\n") if flags else ""))
bo = pyharp.RadiationOptions.from_yaml(yp).bands()[0]
bo.weight([1.0])
say(flags_seen=bo.disort().flags())
band = pyharp.RadiationBand(bo)
atm = {"tempf": torch.full((1, 5), 250.0, dtype=torch.float64)} if with_t else {}
try:
    f = band.forward(torch.ones((1, 4, 1), dtype=torch.float64), torch.full((4,), 250.0, dtype=torch.float64),
                     {"sw/umu0": torch.tensor([1.0], dtype=torch.float64), "sw/fbeam": torch.tensor([[1.0]], dtype=torch.float64),
                      "sw/albedo": torch.tensor([[0.3]], dtype=torch.float64)}, atm)
    say(ran=True, flup_top=f[0, -1, 0].item())
except Exception as e:
    say(ran=False, error=type(e).__name__ + ": " + str(e).splitlines()[0][:160])
"""

P5 = PRE + """
nphase = int(sys.argv[1])
op = DisortOptions().header("ch03").flags("usrtau,usrang,lamber,quiet,intensity_correction")
op.ds().nlyr, op.ds().nstr, op.ds().nmom, op.ds().nphase = 1, 16, 64, nphase
op.user_tau(np.array([0.0, 1.0])); op.user_mu(np.array([-0.8, -0.5, 0.5])); op.user_phi(np.array([0.0]))
op.accur(0.0)
ds = Disort(op)
prop = torch.zeros((1, 1, 1, 66), dtype=torch.float64)
prop[0, 0, 0, 0] = 1.0; prop[0, 0, 0, 1] = 0.99
prop[0, 0, 0, 2:] = scattering_moments(64, "henyey-greenstein", 0.9)
ds.forward(prop, umu0=torch.tensor([0.5], dtype=torch.float64), phi0=torch.zeros(1, dtype=torch.float64),
           fbeam=torch.tensor([[math.pi]], dtype=torch.float64), albedo=torch.zeros((1, 1), dtype=torch.float64))
r = ds.gather_rad()
say(nphase=nphase, finite=int(torch.isfinite(r).sum()), total=r.numel())
"""

P6 = PRE + """
op = DisortOptions().header("ch03").flags("usrtau,usrang,lamber,quiet")
op.ds().nlyr, op.ds().nstr, op.ds().nmom = 1, 8, 8
op.user_tau(np.array([0.0, 1.0])); op.user_mu(np.array([0.5, -0.5])); op.user_phi(np.array([0.0]))
ds = Disort(op)
prop = torch.zeros((1, 1, 1, 10), dtype=torch.float64)
prop[0, 0, 0, 0] = 1.0; prop[0, 0, 0, 1] = 0.9
prop[0, 0, 0, 2:] = scattering_moments(8, "henyey-greenstein", 0.5)
try:
    f = ds.forward(prop, umu0=torch.tensor([0.5], dtype=torch.float64), phi0=torch.zeros(1, dtype=torch.float64),
                   fbeam=torch.tensor([[1.0]], dtype=torch.float64), albedo=torch.zeros((1, 1), dtype=torch.float64))
    say(raised=False, flux_finite=bool(torch.isfinite(f).all()))
except Exception as e:
    say(raised=True, error=str(e).splitlines()[0][:160])
"""


def git_head(var):
    path = os.environ.get(var)
    if not path:
        return "unset"
    r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "not a git tree"


def probe(work, name, code, *args):
    """run code from a file in a fresh interpreter (TorchScript needs the source of the classes it
    compiles); return (rc, [RESULT dicts], up to two lines that mention an error)"""
    import json
    path = os.path.join(work, name + ".py")
    with open(path, "w") as f:
        f.write(code)
    r = subprocess.run([sys.executable, path, *args], capture_output=True, text=True, timeout=600,
                       env=dict(os.environ, CUDA_VISIBLE_DEVICES=""))
    out = r.stdout + r.stderr
    res = [json.loads(line[7:]) for line in r.stdout.splitlines() if line.startswith("RESULT ")]
    msg = [line.strip() for line in out.splitlines()
           if any(k in line.lower() for k in ("error", "corrupt", "free(", "malloc", "invalid", "abort", "not known"))
           and not line.startswith("RESULT ")]
    return r.returncode, res, msg[:2]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default=None)
    ap.add_argument("--repeat", type=int, default=10, help="runs of the memory-corruption probes [P1], [P2]")
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="ch03_cand_")
    os.makedirs(work, exist_ok=True)
    print(f"python {sys.version.split()[0]}, torch {torch.__version__}, numpy {np.__version__}, "
          f"pydisort {pydisort.__version__}")
    print(f"pyharp source {git_head('PYHARP_WT')}, pydisort source {git_head('PYDISORT_SRC')}")
    tag = lambda yes: "reproduced" if yes else "not reproduced"

    for up in (0, 1):
        rcs, seen_flux = [], None
        for rep in range(a.repeat):
            rc, res, msg = probe(work, f"p1_{up}", P1, str(up))
            rcs.append(rc)
            if res and seen_flux is None:
                seen_flux = res[0]
                first_msg = msg
        d = seen_flux["max_abs_diff"] if seen_flux else None
        flux = (f"max |dF| {d:.3f}, top F_up {seen_flux['flup_top_4']:.4f} -> {seen_flux['flup_top_8']:.4f}"
                if seen_flux else "no fluxes returned")
        bad = sum(r != 0 for r in rcs)
        print(f"[P1] CANDIDATE {tag(bad > 0)}: pydisort upward={up}, 8 moments for nmom 4: {flux}; abnormal exit in "
              f"{bad} of {len(rcs)} runs, return codes {sorted(set(rcs))}")

    ys = []
    for n in (4, 8):
        p = os.path.join(work, f"rayleigh_nmom{n}.yaml")
        with open(p, "w") as f:
            f.write(YAML_RAY.format(nmom=n))
        ys.append(p)
    rcs, diff = [], None
    for rep in range(a.repeat):
        rc, res, msg = probe(work, "p2", P2, *ys)
        rcs.append(rc)
        for r in res:
            if r.get("nmom") == 8 and diff is None:
                diff = f"{r['max_abs_diff']:.1e} of {r['flux_scale']:.3f}"
    bad = sum(r != 0 for r in rcs)
    print(f"[P2] CANDIDATE {tag(bad > 0)}: pyharp Rayleigh nmom 8 on a 4-stream DISORT band: abnormal exit in {bad} of "
          f"{len(rcs)} runs, return codes {sorted(set(rcs))}; max |dF| against nmom 4 when the fluxes came back: "
          f"{diff or 'never returned'}")

    code = f"YAML_SLAB = {YAML_SLAB!r}\n" + P34
    rc, res, msg = probe(work, "p3", code, work, "lamber,quiet,onlyfl", "0")
    err = [r["error"] for r in res if "error" in r]
    print(f"[P3] CANDIDATE {tag(bool(err))}: DISORT band without tempf/temp: rc {rc}; "
          f"{err[0] if err else 'ran without error'}")
    rc, res, msg = probe(work, "p4", code, work, "", "1")
    fl = [r["flags_seen"] for r in res if "flags_seen" in r]
    ran = [r for r in res if "ran" in r]
    print(f"[P4] CANDIDATE {tag(rc != 0 and not ran)}: DISORT band with no 'flags:' key: flags {fl[0]!r} "
          f"; rc {rc}; returned to Python: {bool(ran)}; {msg}" if fl else f"[P4] probe failed: rc {rc} {msg}")

    for nph in (0, 16):
        rc, res, msg = probe(work, f"p5_{nph}", P5, str(nph))
        if res:
            seen = res[0]["finite"] < res[0]["total"]
            print(f"[P5] CANDIDATE {tag(seen)}: Buras path, nphase {nph}: rc {rc}; finite radiances "
                  f"{res[0]['finite']} of {res[0]['total']}")
        else:
            print(f"[P5] CANDIDATE {tag(rc != 0)}: Buras path, nphase {nph}: rc {rc}; no result; {msg}")

    rc, res, msg = probe(work, "p6", P6)
    r = res[0] if res else {}
    print(f"[P6] CANDIDATE {tag(rc == 0 and r.get('raised') is False and bool(msg))}: user_mu not increasing: "
          f"cdisort message {msg[:1]}; Python exception raised: {r.get('raised')}; rc {rc}")
    sys.exit(0)


if __name__ == "__main__":
    main()
