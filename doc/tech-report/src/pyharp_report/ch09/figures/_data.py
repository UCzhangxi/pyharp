"""Read the committed cells of derivation-checks/check_ch09_batch_device.py (--data src/pyharp_report/ch09/data)."""
import glob
import json
import os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def cells():
    """{pydisort version: {"Solver|operation": [state, value]}}, versions in sorted order."""
    out = {}
    for f in sorted(glob.glob(os.path.join(DATA, "cells_pydisort_*.json"))):
        with open(f) as fh:
            j = json.load(fh)
        out[j["pydisort"]] = j["cells"]
    return dict(sorted(out.items(), key=lambda kv: [int(x) for x in kv[0].split(".")]))
