"""ch02 check: the single-scattering-albedo clamp of RadiationBandImpl::forward, measured on the running code.

The chapter states that RadiationBandImpl::forward (src/radiation/radiation_band.cpp) replaces the albedo by
min(omega, 1 - delta_omega), delta_omega = 1e-12 in double and 1e-6 in single precision, before the solver runs, and
that the Toon kernels themselves have no such cap. A text match of the source cannot tell a working clamp from one
that is commented out, has a zero margin, or is joined by a cap inside a kernel; this check runs pyharp instead.

  [C1] Band clamp, double. A RadiationBand with the Toon solver (shortwave, one g-point of weight 1, 4 layers of
       dtau 1, g = 0.5, mu0 = 0.5, albedo 0.2) and a TorchScript opacity that returns omega = 1 exactly. After
       forward, the solver input in the band's `prop` buffer must hold omega = 1 - 1e-12 bitwise, an omega = 0.5 run
       must hold 0.5 bitwise, and the band's fluxes must equal those of the Toon module called directly with
       omega = 1 - 1e-12 (and differ from those with omega = 1).
  [C2] Band clamp, single. The same band in float32 (the band module and its inputs converted with .to): `prop`
       must hold omega = float32(1 - 1e-6) for omega = 1.
  [C3] No cap in the Toon kernels. The Toon module called directly (shortwave; and longwave with `planck`) at
       omega = 1, 1 - 1e-12, 1 - 1e-10, 1 - 1e-8, 1 - 1e-6 and 1 - 1e-4 (one layer of dtau 1, g = 0.5) must give six
       pairwise different F+(TOA); a cap min(omega, 1 - d) with 0 < d <= 1e-4 inside a kernel makes at least two equal.

Needs: torch and a pyharp built from source (derivation-checks/ch04/setup_env.sh).
Run:   python3 check_ch02_clamp_pyharp.py [--work DIR]   (default: a fresh temporary directory). Exit status: failures.
Pins:  PYHARP_WT names the pyharp source tree; its commit is printed.
"""
import argparse
import os
import platform
import subprocess
import sys
import tempfile

import pyharp
import torch

torch.set_num_threads(1)

YAML = """species:
  - name: X
    composition: {{H: 2}}
geometry:
  cells:
    nx1: {nlyr}
opacities:
  slab:
    type: jit
    species: [X]
    nmom: 1
    data: [{pt}]
bands:
  - name: sw
    range: [10000.0, 20000.0]
    opacities: [slab]
    solver: toon
    nwave: 1
"""

NLYR, DZ, DTAU, G, MU0, ALB = 4, 250.0, 1.0, 0.5, 0.5, 0.2


class Slab(torch.nn.Module):
    """extinction k [1/m], single-scattering albedo, first Henyey-Greenstein moment g"""

    def __init__(self, k: float, ssa: float, g: float):
        super().__init__()
        self.k = k
        self.ssa = ssa
        self.g = g

    def forward(self, conc: torch.Tensor) -> torch.Tensor:
        out = torch.zeros((1, conc.shape[0], conc.shape[1], 3), dtype=conc.dtype)
        out[..., 0].fill_(self.k)
        out[..., 1].fill_(self.ssa)
        out[..., 2].fill_(self.g)
        return out


def git_head():
    path = os.environ.get("PYHARP_WT")
    if not path:
        return "unset"
    r = subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "not a git tree"


def band_run(work, ssa, dtype):
    tag = f"{ssa!r}_{dtype}".replace(".", "p")
    pt = os.path.join(work, f"slab_{tag}.pt")
    pyharp.compile(Slab(DTAU / DZ, ssa, G), pt)
    yp = os.path.join(work, f"sw_{tag}.yaml")
    with open(yp, "w") as f:
        f.write(YAML.format(nlyr=NLYR, pt=pt))
    bo = pyharp.RadiationOptions.from_yaml(yp).bands()[0]
    bo.weight([1.0])
    band = pyharp.RadiationBand(bo)
    band.to(dtype)
    conc = torch.ones((1, NLYR, 1), dtype=dtype)
    dz = torch.full((NLYR,), DZ, dtype=dtype)
    bc = {"sw/umu0": torch.tensor([MU0], dtype=dtype), "sw/fbeam": torch.tensor([[1.0]], dtype=dtype),
          "sw/albedo": torch.tensor([[ALB]], dtype=dtype)}
    flx = band.forward(conc, dz, bc, {})
    return band.buffer("prop").clone(), band.buffer("spectrum").clone(), flx


def toon_direct(w, nlyr=NLYR, dtau=DTAU, planck=False):
    o = pyharp.ToonMcKay89Options()
    o.wave_lower([10000.0 if not planck else 1.0])
    o.wave_upper([20000.0 if not planck else 1.0e5])
    if planck:
        o.flags("planck,hard_surface")
    p = torch.zeros(1, 1, nlyr, 3, dtype=torch.float64)
    p[..., 0] = dtau
    p[..., 1] = w
    p[..., 2] = G
    if planck:
        temf = torch.linspace(300.0, 250.0, nlyr + 1, dtype=torch.float64).view(1, nlyr + 1)
        return pyharp.ToonMcKay89(o)(p, temf=temf, albedo=torch.full((1, 1), ALB, dtype=torch.float64))[0, 0]
    return pyharp.ToonMcKay89(o)(p, fbeam=torch.full((1, 1), 1.0, dtype=torch.float64),
                                 umu0=torch.tensor([MU0], dtype=torch.float64),
                                 albedo=torch.full((1, 1), ALB, dtype=torch.float64))[0, 0]


def report(n, ok, text):
    print(f"[C{n}] {'PASS' if ok else 'FAIL'} {text}")
    return bool(ok)


def check_C1(work):
    prop1, spec1, _ = band_run(work, 1.0, torch.float64)
    prop5, _, _ = band_run(work, 0.5, torch.float64)
    want = 1.0 - 1.0e-12
    held = torch.equal(prop1[..., 1], torch.full_like(prop1[..., 1], want))
    kept = torch.equal(prop5[..., 1], torch.full_like(prop5[..., 1], 0.5))
    ref_clamped, ref_one = toon_direct(want), toon_direct(1.0)
    spec = spec1.reshape(-1, spec1.shape[-1])[:, :2].reshape(ref_clamped.shape[0], 2)
    dev_clamped = (spec - ref_clamped[:, :2]).abs().max().item()
    dev_one = (spec - ref_one[:, :2]).abs().max().item()
    ok = held and kept and dev_clamped <= 1e-15 and dev_one > 1e-6
    return report(1, ok, f"double: prop omega for omega = 1 is {prop1[..., 1].max().item()!r} (want {want!r}: {held}); "
                  f"for 0.5 unchanged: {kept}; band fluxes minus Toon at 1 - 1e-12: {dev_clamped:.1e}, "
                  f"minus Toon at 1: {dev_one:.1e}")


def check_C2(work):
    prop1, _, _ = band_run(work, 1.0, torch.float32)
    want = torch.tensor(1.0 - 1.0e-6, dtype=torch.float32)
    held = prop1.dtype == torch.float32 and torch.equal(prop1[..., 1], torch.full_like(prop1[..., 1], want.item()))
    return report(2, held, f"single: prop dtype {prop1.dtype}, omega for omega = 1 is {prop1[..., 1].max().item()!r} "
                  f"(want float32(1 - 1e-6) = {want.item()!r})")


def check_C3():
    ws = [1.0, 1.0 - 1e-12, 1.0 - 1e-10, 1.0 - 1e-8, 1.0 - 1e-6, 1.0 - 1e-4]
    rows, ok = [], True
    for name, planck in (("shortwave", False), ("longwave", True)):
        toa = [toon_direct(w, nlyr=1, planck=planck)[-1, 0].item() for w in ws]
        gaps = [abs(a - b) for i, a in enumerate(toa) for b in toa[i + 1:]]
        ok &= min(gaps) > 0
        rows.append(f"{name} F+(TOA) " + ", ".join(f"{x:.15e}" for x in toa) + f" (smallest pairwise gap {min(gaps):.1e})")
    return report(3, ok, "Toon kernels respond to omega above 1 - 1e-4: " + "; ".join(rows))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default=None)
    a = ap.parse_args()
    work = a.work or tempfile.mkdtemp(prefix="ch02_clamp_")
    os.makedirs(work, exist_ok=True)
    import pydisort
    print(f"versions: pyharp {pyharp.__version__}, torch {torch.__version__}, Python {platform.python_version()}, "
          f"pydisort {pydisort.__version__}")
    print(f"pyharp source {git_head()}")
    print("device: CPU, threads: 1")
    oks = [check_C1(work), check_C2(work), check_C3()]
    print(f"check_ch02_clamp_pyharp: {sum(oks)} of {len(oks)} claims pass")
    return len(oks) - sum(oks)


if __name__ == "__main__":
    sys.exit(main())
