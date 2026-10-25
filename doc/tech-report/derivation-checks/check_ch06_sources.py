"""ch06 check: how a band selects and builds its opacity sources (the `opacities:` block of a radiation YAML).

OpacityOptionsImpl::from_yaml (src/opacity/opacity_options.cpp) reads one entry of `opacities:`;
RadiationBandImpl::reset (src/radiation/radiation_band.cpp) builds one module per entry the band lists, choosing
the module by `type`, and sizes the band's `prop` buffer.

  [C1] Dispatch and width (eq-ch06-sources-nprop): bands listing rayleigh (nmom 4), water-liquid-mie (nmom 3),
       picaso-ck, and rayleigh with picaso-ck build the module of each type (band.module(name) is found) and
       give `prop` the last dimension max(1, 2 + nmom) over their sources: 6, 5, 1 and 6.
  [C2] Output contract: each source returns a tensor of shape (nwave, ncol, nlyr, nprop), with nprop = 2 + nmom
       for the scattering sources and 1 for the table, and an extinction column that is finite and >= 0, for a
       grid of 3 spectral points, 2 columns and 4 layers. PicasoCK has no Python class, so its output is read as
       prop / dz of a band that holds it alone.
  [C3] Unknown types: `type: foo` and an empty `type` are refused when the band is built, with
       "Unknown opacity type".
  [C4] Helios (sec-ch06-helios): `type: helios` is refused when the band is built, with
       "Mismatch opacity type: helios", and the spellings helios-ck, hel and Helios are refused as unknown types;
       no type string builds the Helios module.
  [C5] YAML: an entry without `type` and a species missing from `species:` are refused when the YAML is read, each
       with the message of OpacityOptionsImpl::from_yaml; `<band>` in a data file name is replaced by the name of
       the band (a table named `table_<band>.nc` is found as `table_b.nc` for band `b`).

Needs torch, numpy, scipy and a pyharp built from source with NetCDF at the pin of code_pin.yml (ch06_setup.sh).
Run:   python3 check_ch06_sources.py   (any directory; exits with the number of failed claims)
"""
import os
import sys
import tempfile

import numpy as np
import torch
import pyharp
from pyharp.opacity import MieWaterLiquid, Rayleigh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ch06_common as C  # noqa: E402
from check_ch06_picaso import write_table  # noqa: E402

SPECIES = """species:
  - {name: H2, composition: {H: 2}}
  - {name: He, composition: {He: 1}}
  - {name: H2O(l), composition: {H: 2, O: 1}}
geometry: {cells: {nx1: 4}}
"""


def table(name="table.nc"):
    d = tempfile.mkdtemp(prefix="ch06_sources_")
    write_table(os.path.join(d, name), np.full((2, 2, 3, 3), -45.0))
    return d


def band_yaml(opacities, names, nmom_ray=4, nmom_mie=3, data="table.nc"):
    entries = {
        "ray": f"ray: {{type: rayleigh, species: [H2, He], nmom: {nmom_ray}}}",
        "mie": f"mie: {{type: water-liquid-mie, species: [\"H2O(l)\"], nmom: {nmom_mie}}}",
        "pk": f"pk: {{type: picaso-ck, data: [{data}]}}",
    }
    body = "\n".join("  " + entries[n] for n in opacities)
    return C.Config(SPECIES + f"""opacities:
{body}
bands:
  - {{name: b, range: [1000., 1500.], opacities: [{', '.join(names)}], solver: disort, nwave: 4, nstr: 4, flags: "lamber,quiet,onlyfl"}}
""")


def build(cfg):
    b = cfg.band()
    b.wavenumber([1000.0, 1100.0, 1300.0, 1450.0]).weight([0.25] * 4)
    return pyharp.RadiationBand(b)


def check_C1():
    d = table()
    results = []
    for names in (["ray"], ["mie"], ["pk"], ["ray", "pk"]):
        cfg = band_yaml(["ray", "mie", "pk"], names, data=os.path.join(d, "table.nc"))
        band = build(cfg)
        found = all(band.module(n) is not None for n in names)
        results.append((names, found, band.buffer("prop").size(-1)))
    widths = [w for _, _, w in results]
    ok = all(f for _, f, _ in results) and widths == [6, 5, 1, 6]
    return C.report(1, ok, "modules built and prop width: " + "; ".join(f"{'+'.join(n)}: {f}, {w}"
                                                                        for n, f, w in results))


def check_C2():
    d = table()
    cfg = band_yaml(["ray", "mie", "pk"], ["ray", "mie", "pk"], data=os.path.join(d, "table.nc"))
    lam = C.t([1.0e4 / 1000.0, 1.0e4 / 1100.0, 1.0e4 / 1300.0])
    conc = torch.rand((2, 4, 3), dtype=torch.float64, generator=torch.Generator().manual_seed(6))
    shapes = {
        "rayleigh": Rayleigh(cfg.opacity("ray")).forward(conc, {"wavelength": lam}),
        "water-liquid-mie": MieWaterLiquid(cfg.opacity("mie")).forward(conc, {"wavelength": lam, "re": C.t(8.0)}),
    }
    # PicasoCK has no Python class: read it through a band of that source alone, whose prop is k dz (nprop 1)
    cfg_pk = band_yaml(["pk"], ["pk"], data=os.path.join(d, "table.nc"))
    b = cfg_pk.band()
    b.wavenumber([1000.0, 1100.0, 1300.0]).weight([1.0 / 3] * 3).nwave(3).ncol(2).nlyr(4)
    pyharp.disort_config(b.disort(), 4, 4, 2, 3)
    band = pyharp.RadiationBand(b)
    dz = C.t([10.0, 20.0, 30.0, 40.0])
    band.forward(conc, dz, {"b/fbeam": torch.ones((3, 2), dtype=torch.float64), "b/umu0": C.t([0.5, 0.5]),
                            "b/albedo": torch.zeros((3, 2), dtype=torch.float64)},
                 {"pres": torch.full((2, 4), 1e4, dtype=torch.float64),
                  "temp": torch.full((2, 4), 250.0, dtype=torch.float64),
                  "tempf": torch.full((2, 5), 250.0, dtype=torch.float64)})
    shapes["picaso-ck"] = band.buffer("prop") / dz.view(1, 1, -1, 1)
    want = {"rayleigh": (3, 2, 4, 6), "water-liquid-mie": (3, 2, 4, 5), "picaso-ck": (3, 2, 4, 1)}
    ok = all(tuple(v.shape) == want[k] and bool(torch.all(torch.isfinite(v[..., 0]) & (v[..., 0] >= 0)))
             for k, v in shapes.items())
    return C.report(2, ok, "shape (nwave, ncol, nlyr, nprop) and finite k >= 0: " +
                    "; ".join(f"{k} {tuple(v.shape)}" for k, v in shapes.items()))


def type_yaml(typ):
    return C.Config(SPECIES + f"""opacities:
  x: {{type: "{typ}", species: [H2], data: [no-such-file.txt]}}
bands:
  - {{name: b, range: [1000., 1500.], opacities: [x], solver: disort, nwave: 4, nstr: 4, flags: "lamber,quiet,onlyfl"}}
""")


def check_C3():
    msgs = [C.refusal(lambda t=t: build(type_yaml(t))) for t in ("foo", "")]
    ok = all(m is not None and m.startswith("Unknown opacity type") for m in msgs)
    return C.report(3, ok, "refused: " + "; ".join(f'"{m}"' for m in msgs))


def check_C4():
    spellings = ["helios", "helios-ck", "hel", "Helios"]
    msgs = [C.refusal(lambda t=t: build(type_yaml(t))) for t in spellings]
    ok = msgs[0] == "Mismatch opacity type: helios" and all(
        m is not None and m.startswith("Unknown opacity type") for m in msgs[1:])
    return C.report(4, ok, "refused: " + "; ".join(f'{s}: "{m}"' for s, m in zip(spellings, msgs)))


def check_C5():
    no_type = C.refusal(lambda: C.Config(SPECIES + """opacities:
  x: {species: [H2]}
bands:
  - {name: b, range: [1000., 1500.], opacities: [x], solver: disort, nwave: 4, nstr: 4, flags: "lamber,quiet,onlyfl"}
"""))
    no_species = C.refusal(lambda: C.Config(SPECIES + """opacities:
  x: {type: rayleigh, species: [CO2], nmom: 2}
bands:
  - {name: b, range: [1000., 1500.], opacities: [x], solver: disort, nwave: 4, nstr: 4, flags: "lamber,quiet,onlyfl"}
"""))
    d = table("table_b.nc")
    cfg = band_yaml(["pk"], ["pk"], data=os.path.join(d, "table_<band>.nc"))
    files = list(cfg.opacity("pk").opacity_files())
    built = build(cfg).module("pk") is not None
    ok = (no_type is not None and "'type' missing" in no_type and no_species is not None
          and "not found in species list" in no_species and built and files[0].endswith("table_b.nc"))
    return C.report(5, ok, f'refused: "{no_type}"; "{no_species}"; data "table_<band>.nc" read as '
                    f'"{os.path.basename(files[0])}", band built: {built}')


def main():
    C.header()
    oks = [check_C1(), check_C2(), check_C3(), check_C4(), check_C5()]
    nfail = oks.count(False)
    print(f"check_ch06_sources: {len(oks) - nfail} of {len(oks)} claims pass")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
