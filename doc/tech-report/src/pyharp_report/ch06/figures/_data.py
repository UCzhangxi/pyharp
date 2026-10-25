"""Read the committed outputs of the ch06 checks (derivation-checks/ch06_run.sh writes src/pyharp_report/ch06/data)."""
import json
import os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)
