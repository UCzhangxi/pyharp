"""ch08 check: reading the radiation configuration file (RadiationOptions.from_yaml, IntegratorOptions.from_yaml).

Every case writes a small YAML file into the work directory and reads it with the pinned pyharp.

  [C1] species molar masses: species_weights()[s] = 1e-3 sum_e nu_{s,e} M_e [kg/mol], with M_e the element table of
       harp::element_weights at the pin (H 1.008, He 4.002602, C 12.011, O 15.999 g/mol); element names in either
       form (symbol or lower-case name). Tolerance 1e-15 relative: three products and a sum in double precision.
  [C2] structure and defaults: nlyr = nx1, ncol = nx2 * nx3 (default 1 each), nstr = 4 when absent, bands in YAML
       order with their names and solvers, wave_lower and wave_upper = the band range for each of the nwave points,
       DISORT flags trimmed of surrounding blanks; a file with no `bands` key gives zero bands (and needs no species).
  [C3] the `integration` block: type, cfl, tlim, nlim and ncycle_out are read; absent keys keep the defaults
       rk3, 0.9, 1e9, -1, 1; max_redo is 5 whatever the file says.
  [C4] refusals: each listed defect in the file stops from_yaml (or the Integrator constructor) with its message.
  [C5] neither `weight` nor a wavenumber grid is read from a band; RadiationBand refuses to run until one is set.
  [C6] the `units` key of a band is not read: `units: um` leaves wave_lower and wave_upper equal to the numbers of
       `range`, which DISORT then takes as wavenumbers [cm^-1].
  [P1] CANDIDATE, nphase is not set: create_disort_config sets nlyr, nstr and nmom of a DISORT band and not nphase,
       which pydisort's options leave uninitialised; cdisort allocates the phase array with it. Read 6 times, the
       nphase of the file's DISORT band is compared with nstr (the value pyharp.disort_config sets); only whether a
       read differs is printed, since the value itself is whatever the memory held.
  [C8] what a large nphase does: in a child process, nphase = 2^29 on the file's DISORT band (nlyr = 8, so the
       product nlyr * nphase overflows a 32-bit int) makes cdisort's c_disort_state_alloc stop the process with
       "dbl_vector, variable ds->phase" on the band's first forward; nphase = nstr runs. This is the failure an unset
       nphase can cause; whether a given read holds such a value depends on the memory contents.
  [C7] the species list is process-wide: reading a second file replaces species_names() and species_weights(), also
       for an options object built before; a file with a `bands` key, even an empty list, sets it.

Needs: torch, numpy, pydisort and a pyharp built against that pydisort.
Run:   python ch08_config.py [--work DIR]   (default: a fresh temporary directory)
"""
import argparse
import os
import subprocess
import sys
import tempfile

import pyharp

from ch08_common import compile_slab, header, write

BASE = """species:
  - name: H2O
    composition: {{H: 2, O: 1}}
  - name: CO2
    composition: {{carbon: 1, oxygen: 2}}
  - name: He
    composition: {{He: 1}}
geometry:
  cells:
    nx1: 8
    nx2: 3
    nx3: 2
opacities:
  o1: {{type: jit, species: [H2O], data: [{pt}]}}
bands:
  - name: first
    range: [100.0, 300.0]
    opacities: [o1]
    solver: disort
    nwave: 3
    flags: "  lamber,quiet,onlyfl,planck  "
  - name: second
    range: [300.0, 900.0]
    opacities: [o1]
    solver: toon
    nwave: 2
    nstr: 2
{extra}"""


def load(work, name, text):
    return pyharp.RadiationOptions.from_yaml(write(work, name, text))


def refused(fn, needle):
    try:
        fn()
    except Exception as e:  # noqa: BLE001  (pyharp raises RuntimeError or c10::Error as RuntimeError)
        return needle in str(e)
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--work", default=None)
    work = ap.parse_args().work or tempfile.mkdtemp(prefix="ch08_cfg_")
    os.makedirs(work, exist_ok=True)
    header(f", pyharp {pyharp.__version__}")
    pt = compile_slab(work, "grey", 1e-4)
    base = BASE.format(pt=pt, extra="")
    nfail = 0

    op = load(work, "base.yaml", base)
    m = {"H": 1.008, "He": 4.002602, "C": 12.011, "O": 15.999}
    want = [1e-3 * (2 * m["H"] + m["O"]), 1e-3 * (m["C"] + 2 * m["O"]), 1e-3 * m["He"]]
    got = list(pyharp.species_weights())
    dev = max(abs(g / w - 1) for g, w in zip(got, want))
    ok = list(pyharp.species_names()) == ["H2O", "CO2", "He"] and dev <= 1e-15
    nfail += not ok
    print(f"[C1] {'PASS' if ok else 'FAIL'} species molar mass = 1e-3 sum nu M_e: "
          + ", ".join(f"{n} {g:.6f}" for n, g in zip(pyharp.species_names(), got))
          + f" kg/mol, max rel dev {dev:.1e} (tol 1e-15)")

    b = op.bands()
    checks = [op.nlyr() == 8, op.ncol() == 6, [x.name() for x in b] == ["first", "second"],
              [x.solver_name() for x in b] == ["disort", "toon"], b[0].nstr() == 4, b[1].nstr() == 2,
              list(b[0].disort().wave_lower()) == [100.0] * 3, list(b[0].disort().wave_upper()) == [300.0] * 3,
              b[0].disort().flags() == "lamber,quiet,onlyfl,planck", b[0].disort().nwave() == 3,
              b[0].disort().ncol() == 6, b[0].disort().ds().nstr == 4]
    nobands = load(work, "nobands.yaml", "geometry:\n  cells:\n    nx1: 4\n")
    checks.append(len(nobands.bands()) == 0)
    ok = all(checks)
    nfail += not ok
    print(f"[C2] {'PASS' if ok else 'FAIL'} structure: nlyr {op.nlyr()}, ncol {op.ncol()}, bands "
          f"{[x.name() for x in b]} ({[x.solver_name() for x in b]}), nstr {b[0].nstr()} (absent) and {b[1].nstr()}, "
          f"wave range {list(b[0].disort().wave_lower())[0]}-{list(b[0].disort().wave_upper())[0]} x "
          f"{b[0].disort().nwave()}, flags trimmed; no 'bands' key -> {len(nobands.bands())} bands "
          f"({sum(checks)}/{len(checks)} facts)")

    p0 = write(work, "intg0.yaml", base)
    p1 = write(work, "intg1.yaml", base + "integration:\n  type: rk2\n  cfl: 0.5\n  tlim: 10.0\n  nlim: 7\n"
               "  ncycle_out: 3\n  max_redo: 9\n  verbose: true\n")
    i0 = pyharp.IntegratorOptions.from_yaml(p0)
    i1 = pyharp.IntegratorOptions.from_yaml(p1)
    d0 = (i0.type(), i0.cfl(), i0.tlim(), i0.nlim(), i0.ncycle_out(), i0.max_redo())
    d1 = (i1.type(), i1.cfl(), i1.tlim(), i1.nlim(), i1.ncycle_out(), i1.max_redo())
    ok = d0 == ("rk3", 0.9, 1e9, -1, 1, 5) and d1 == ("rk2", 0.5, 10.0, 7, 3, 5)
    nfail += not ok
    print(f"[C3] {'PASS' if ok else 'FAIL'} integration block (type, cfl, tlim, nlim, ncycle_out, max_redo): "
          f"absent {d0}; given with max_redo 9 {d1}")

    def mutate(old, new):
        assert base.count(old) == 1, old
        return base.replace(old, new)

    bad = [
        ("no species", "geometry:" + base.split("geometry:")[1], "'species' is not defined"),
        ("no opacities", mutate("    opacities: [o1]\n    solver: toon", "    solver: toon"), "opacities not found in band"),
        ("no range", mutate("    range: [300.0, 900.0]\n", ""), "missing spectral range"),
        ("reversed range", mutate("range: [300.0, 900.0]", "range: [900.0, 300.0]"), "invalid spectral range"),
        ("no nwave", mutate("    nwave: 2\n", ""), "'nwave' not found"),
        ("no nx1", mutate("    nx1: 8\n", ""), "'nx1' not found in cells"),
        ("no solver", mutate("    solver: toon\n", ""), "'solver' not found"),
        ("twostr", mutate("solver: toon", "solver: twostr"), "twostr solver not implemented"),
        ("unknown solver", mutate("solver: toon", "solver: lbl"), "unknown solver: lbl"),
        ("unknown element", mutate("{He: 1}", "{Xx: 1}"), "element not found"),
    ]
    res = []
    for i, (lab, text, needle) in enumerate(bad):
        res.append((lab, refused(lambda: load(work, f"bad{i}.yaml", text), needle)))
    iop = pyharp.IntegratorOptions()
    iop.type("rk4")
    res.append(("integrator rk4", refused(lambda: pyharp.Integrator(iop), "Integrator not implemented")))
    ok = all(r for _, r in res)
    nfail += not ok
    print(f"[C4] {'PASS' if ok else 'FAIL'} refusals with their messages: {sum(r for _, r in res)}/{len(res)} ("
          + ", ".join(lab for lab, r in res if r) + ")"
          + ("" if ok else "; missing: " + ", ".join(lab for lab, r in res if not r)))

    one = load(work, "one.yaml", base.replace("    nx2: 3\n    nx3: 2\n", ""))
    band = one.bands()[0]
    no_grid = refused(lambda: pyharp.RadiationBand(band), "Either 'wavenumber' or 'weight' must be set in band first")
    ok = len(band.weight()) == 0 and len(band.wavenumber()) == 0 and no_grid
    nfail += not ok
    print(f"[C5] {'PASS' if ok else 'FAIL'} weight and wavenumber grid after from_yaml: {len(band.weight())} and "
          f"{len(band.wavenumber())} entries; RadiationBand(options) refused until one is set: {no_grid}")

    um = load(work, "units.yaml", mutate("    range: [100.0, 300.0]\n", "    units: um\n    range: [100.0, 300.0]\n"))
    lo, hi = list(um.bands()[0].disort().wave_lower()), list(um.bands()[0].disort().wave_upper())
    ok = lo == [100.0] * 3 and hi == [300.0] * 3
    nfail += not ok
    print(f"[C6] {'PASS' if ok else 'FAIL'} 'units: um' on a band with range [100, 300]: wave_lower {lo[0]}, "
          f"wave_upper {hi[0]} (the numbers of 'range', used as cm^-1); the key is accepted and not read")

    differ = 0
    for i in range(6):
        d = load(work, f"nphase{i}.yaml", base).bands()[0].disort().ds()
        differ += d.nphase != d.nstr
    print(f"[P1] CANDIDATE {'reproduced' if differ else 'not reproduced'} nphase of a DISORT band after from_yaml "
          f"differs from nstr in at least one of 6 reads: {differ > 0} (pyharp.disort_config sets nphase = nstr; "
          f"create_disort_config does not set it)")

    child = """import sys, torch, pyharp
op = pyharp.RadiationOptions.from_yaml(sys.argv[1])
b = op.bands()[0]
b.weight([1.0] * b.nwave())
b.disort().ds().nphase = int(sys.argv[2])
rb = pyharp.RadiationBand(b)
nl = op.nlyr()
rb.forward(torch.ones((1, nl, 3), dtype=torch.float64), torch.full((nl,), 100.0, dtype=torch.float64),
           {"btemp": torch.tensor([280.0], dtype=torch.float64), "ttemp": torch.tensor([0.0], dtype=torch.float64),
            "first/albedo": torch.zeros((3, 1), dtype=torch.float64)},
           {"tempf": torch.full((1, nl + 1), 250.0, dtype=torch.float64)})
print("ran")
"""
    one_col = write(work, "one_col.yaml", base.replace("    nx2: 3\n    nx3: 2\n", ""))
    runs = {}
    for nph in (1 << 29, 4):
        r = subprocess.run([sys.executable, "-c", child, one_col, str(nph)], capture_output=True, text=True)
        runs[nph] = (r.returncode, "dbl_vector, variable ds->phase" in r.stderr, "ran" in r.stdout)
    big, small = runs[1 << 29], runs[4]
    ok = big[0] != 0 and big[1] and not big[2] and small[0] == 0 and small[2]
    nfail += not ok
    print(f"[C8] {'PASS' if ok else 'FAIL'} nphase = 2^29 on an 8-layer DISORT band: process stopped: {big[0] != 0}, "
          f"with 'dbl_vector, variable ds->phase': {big[1]}; nphase = nstr = 4: runs: {small[2]}")

    before = (list(pyharp.species_names()), list(pyharp.species_weights()))
    load(work, "other.yaml", "species:\n  - name: N2\n    composition: {N: 2}\nbands: []\n")
    mid = list(pyharp.species_names())
    load(work, "other2.yaml", BASE.format(pt=pt, extra="").replace("  - name: He\n    composition: {He: 1}\n", ""))
    after = list(pyharp.species_names())
    ok = before[0] == ["H2O", "CO2", "He"] and after == ["H2O", "CO2"] and len(op.bands()) == 2
    nfail += not ok
    print(f"[C7] {'PASS' if ok else 'FAIL'} species registry is global: {before[0]} -> after a second file "
          f"{after} (the first options object still holds {len(op.bands())} bands); a file with an empty 'bands' "
          f"list sets it too: {mid}")
    sys.exit(nfail)


if __name__ == "__main__":
    main()
