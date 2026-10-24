"""ch08 check: summing the bands (Radiation.forward) and the output contract.

Three bands of one grey species over 4 layers: a scattering shortwave DISORT band with a beam (surface albedo 0.3), an
absorbing longwave DISORT band with the Planck source, and the same longwave band solved by Toon (`toon`, `planck`).
Weight mode, one spectral point of weight 1 per band; level temperatures 280 K at the surface to 240 K at the top.

  [C1] the `spectra` buffer has shape (nband, ncol, nlev, 4), and the returned net flux is, level by level,
       sum_b (F^up_b - F^dn_b) of its channels 0 and 1 (torch.equal: the code adds the band tensors in YAML order
       and subtracts once, and this check does the same operations in the same order).
  [C2] the returned surface flux is sum_b F^dn_b at level 0 (the surface) and the returned top flux is
       sum_b F^up_b at level nlyr (torch.equal).
  [C3] each band row of `spectra` equals a RadiationBand built from the same options and run alone (torch.equal):
       the bands do not interact.
  [C4] dz given as (nlyr) and as (ncol, nlyr) gives the same three outputs (torch.equal).
  [C5] the `net_flux_midpt` buffer is sum_b (channel 2 - channel 3) (torch.equal). For the DISORT bands channels 2
       and 3 are copies of channels 0 and 1, so with DISORT bands only it equals the level net flux; with the Toon
       band in the set it adds DISORT level values to Toon midpoint values, and its entry 0 holds no Toon term.
  [C6] Radiation.options.outdirs, when set, is copied into every band at construction.
  [C7] a Toon shortwave band (same scattering opacity and beam as the DISORT shortwave band) also fills channels 2
       and 3 with layer-midpoint fluxes at levels 1 to nlyr, and at level 0 keeps the level values (channels 2, 3
       equal channels 0, 1 bitwise there), so with it `net_flux_midpt` entry 0 does hold a Toon term.

Needs: torch, numpy, pydisort and a pyharp built against that pydisort.
Run:   python ch08_radiation.py [--work DIR]   (default: a fresh temporary directory)
"""
import argparse
import os
import sys
import tempfile

import pyharp
import torch

from ch08_common import F64, header, set_unit_weights, two_band_inputs, two_band_yaml, write

TOON_SW = """  - name: ts
    range: [10000.0, 20000.0]
    opacities: [osw]
    solver: toon
    nwave: 1
"""

TOON = """  - name: tl
    range: [500.0, 700.0]
    opacities: [olw]
    solver: toon
    nwave: 1
    flags: planck
"""


def run(rad, conc, dz, bc, atm):
    bc = {k: v.clone() for k, v in bc.items()}
    atm = {k: v.clone() for k, v in atm.items()}
    out = rad.forward(conc, dz, bc, atm)
    return out, rad.buffer("spectra").clone(), rad.buffer("net_flux_midpt").clone()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default=None)
    work = ap.parse_args().work or tempfile.mkdtemp(prefix="ch08_rad_")
    os.makedirs(work, exist_ok=True)
    torch.set_num_threads(1)
    header(f", pyharp {pyharp.__version__}")
    path = two_band_yaml(work)
    path3 = write(work, "three_band.yaml", open(path).read() + TOON)
    conc, dz, bc, atm = two_band_inputs()
    bc["tl/albedo"] = torch.zeros((1, 1), dtype=F64)
    nfail = 0

    op = set_unit_weights(pyharp.RadiationOptions.from_yaml(path3))
    rad = pyharp.Radiation(op)
    (net, sfc, toa), sp, mid = run(rad, conc, dz, bc, atm)
    nband = sp.shape[0]
    tot = sp[0].clone()
    for b in range(1, nband):
        tot += sp[b]
    ok1 = tuple(sp.shape) == (3, 1, 5, 4) and torch.equal(net, tot[..., 0] - tot[..., 1])
    nfail += not ok1
    print(f"[C1] {'PASS' if ok1 else 'FAIL'} spectra shape {tuple(sp.shape)}; net flux = sum_b (up - down), bitwise; "
          f"net [W m-2] surface to top: " + ", ".join(f"{x:.4f}" for x in net[0].tolist()))
    ok2 = torch.equal(sfc, tot[:, 0, 1]) and torch.equal(toa, tot[:, -1, 0])
    nfail += not ok2
    print(f"[C2] {'PASS' if ok2 else 'FAIL'} surface downward {sfc.item():.4f} = sum_b F^dn at level 0, top upward "
          f"{toa.item():.4f} = sum_b F^up at level nlyr, bitwise")

    alone = []
    for b, bop in enumerate(op.bands()):
        rb = pyharp.RadiationBand(bop)
        f = rb.forward(conc, dz, {k: v.clone() for k, v in bc.items()}, {k: v.clone() for k, v in atm.items()})
        alone.append(torch.equal(f, sp[b]))
    ok3 = all(alone)
    nfail += not ok3
    print(f"[C3] {'PASS' if ok3 else 'FAIL'} each spectra row equals its band run alone, bitwise: "
          + ", ".join(f"{bop.name()} {a}" for bop, a in zip(op.bands(), alone)))

    (net2, sfc2, toa2), _, _ = run(rad, conc, dz.unsqueeze(0), bc, atm)
    ok4 = torch.equal(net, net2) and torch.equal(sfc, sfc2) and torch.equal(toa, toa2)
    nfail += not ok4
    print(f"[C4] {'PASS' if ok4 else 'FAIL'} dz as (nlyr) and as (ncol, nlyr): identical outputs")

    tot_mid = tot[..., 2] - tot[..., 3]
    op2 = set_unit_weights(pyharp.RadiationOptions.from_yaml(path))
    rad2 = pyharp.Radiation(op2)
    (net_d, _, _), sp_d, mid_d = run(rad2, conc, dz, bc, atm)
    disort_copy = all(torch.equal(sp_d[b][..., 2:], sp_d[b][..., :2]) for b in range(sp_d.shape[0]))
    toon0 = sp[2, 0, 0, 2:].abs().max().item()
    dev = (mid - net).abs().max().item()
    ok5 = torch.equal(mid, tot_mid) and disort_copy and torch.equal(mid_d, net_d) and toon0 == 0.0 and dev > 0
    nfail += not ok5
    print(f"[C5] {'PASS' if ok5 else 'FAIL'} net_flux_midpt = sum_b (ch2 - ch3), bitwise; DISORT channels 2, 3 copy "
          f"0, 1: {disort_copy}; DISORT bands only: midpoint = level net flux, bitwise; with the Toon band: max "
          f"|midpoint - level net| {dev:.4f} W m-2, Toon channels 2, 3 at level 0: {toon0:.1f}, entry 0 = "
          f"{mid[0, 0].item():.4f} = DISORT level-0 net {(sp[0, 0, 0, 0] - sp[0, 0, 0, 1] + sp[1, 0, 0, 0] - sp[1, 0, 0, 1]).item():.4f}")

    op3 = set_unit_weights(pyharp.RadiationOptions.from_yaml(path))
    op3.outdirs("(0, 0), (30, 0)")
    rad3 = pyharp.Radiation(op3)
    got = [b.outdirs() for b in rad3.options.bands()]
    ok6 = got == ["(0, 0), (30, 0)"] * 2
    nfail += not ok6
    print(f"[C6] {'PASS' if ok6 else 'FAIL'} options.outdirs copied into every band at construction: {got}")
    path4 = write(work, "toon_sw.yaml", open(path).read() + TOON_SW)
    op4 = set_unit_weights(pyharp.RadiationOptions.from_yaml(path4))
    rb = pyharp.RadiationBand(op4.bands()[2])
    bc4 = {k: v.clone() for k, v in bc.items()}
    bc4.update({"ts/umu0": torch.tensor([0.6], dtype=F64), "ts/fbeam": torch.tensor([[100.0]], dtype=F64),
                "ts/albedo": torch.tensor([[0.3]], dtype=F64)})
    fts = rb.forward(conc, dz, bc4, {k: v.clone() for k, v in atm.items()})[0]
    keep0 = torch.equal(fts[0, 2:], fts[0, :2])
    moved = bool((fts[1:, 2:] != fts[1:, :2]).any(dim=-1).all())
    ok7 = keep0 and moved
    nfail += not ok7
    print(f"[C7] {'PASS' if ok7 else 'FAIL'} Toon shortwave band: level 0 channels 2, 3 = channels 0, 1 bitwise: "
          f"{keep0}; levels 1-{fts.shape[0] - 1} hold midpoint values different from the level values: {moved}; "
          f"midpoint net at entry 0 {(fts[0, 2] - fts[0, 3]).item():.4f} W m-2")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
