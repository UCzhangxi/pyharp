"""Read the committed outputs of the ch05 checks (derivation-checks/check_ch05_*.py --data src/pyharp_report/ch05/data)."""
import json
import os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)
