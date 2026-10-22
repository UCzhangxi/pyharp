"""ch09: the support matrix, solver x operation x pydisort version, from the cells check_ch09_batch_device.py
wrote for each pydisort version (src/pyharp_report/ch09/data/cells_pydisort_<version>.json).

Prints one line per (solver, operation) with the state of each version: pass, fail, unsupported or not run, and
the measured number. A `fail` cell is a candidate defect the ch09 text records (check_ch09_batch_device.py marks
those EXPECTED-FAIL); this script fails only when a cell is missing or the two inputs are absent.

Run: python3 check_ch09_matrix.py [DATA_DIR]  (default: ../src/pyharp_report/ch09/data next to this file).
Exit status: the number of FAIL lines.
"""

import glob
import json
import os
import sys

SOLVERS = ["Toon SW", "Toon LW", "DISORT SW", "DISORT LW", "RadiationBand DISORT"]
OPS = ["forward f64", "batch f64", "CUDA f64", "forward f32", "batch f32", "CUDA f32"]


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    data = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "..", "src", "pyharp_report", "ch09", "data")
    runs = {}
    for f in sorted(glob.glob(os.path.join(data, "cells_pydisort_*.json"))):
        with open(f) as fh:
            j = json.load(fh)
        runs[j["pydisort"]] = j
    n, fails = 0, 0
    print(f"versions: pydisort {', '.join(runs)}; torch {', '.join(sorted({r['torch'] for r in runs.values()}))}; "
          f"GPU {', '.join(sorted({str(r['gpu']) for r in runs.values()}))}")
    if len(runs) < 2:
        print("[C1] FAIL two pydisort versions are present: found", list(runs))
        sys.exit(1)
    for s in SOLVERS:
        for op in OPS:
            if s == "RadiationBand DISORT" and op.startswith("batch"):
                continue
            n += 1
            row = []
            for v, r in runs.items():
                st, val = r["cells"].get(f"{s}|{op}", ["missing", ""])
                if "DispatchStub: missing kernel for cuda" in val:
                    val = "no CUDA kernel"
                row.append(f"pydisort {v}: {st} ({val})")
                fails += st == "missing"
            print(f"[C{n}] {'FAIL' if any('missing' in x for x in row) else 'INFO'} {s} | {op} | " + " | ".join(row))
    print(f"== check_ch09_matrix: {n} labels, {fails} FAIL")
    sys.exit(fails)


if __name__ == "__main__":
    main()
