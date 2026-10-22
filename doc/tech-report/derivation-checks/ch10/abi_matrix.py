#!/usr/bin/env python3
"""Chapter 10 check: the pydisort build/run matrix of tests/test_rayleigh.py, from the committed suite outputs.

Reads run_suite.<scenario>.out in this directory for the four combinations of the pydisort a pyharp build was
compiled against and the pydisort installed when it runs, and prints, per combination, the runs of
tests/test_rayleigh.py ([S6] lines) and how many ended in a glibc heap-corruption abort:
  [A1] one line per combination; [A2] the combinations with any abort.
With --csv <file> it also writes the matrix for the chapter's data figure. Standard library only. Exit status 0.
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = [("1.7.1", "1.7.1", "run_suite.pydisort-1.7.1.out"), ("1.8.13", "1.8.13", "run_suite.pydisort-1.8.13.out"),
         ("1.7.1", "1.8.13", "run_suite.built-1.7.1.run-1.8.13.out"),
         ("1.8.13", "1.7.1", "run_suite.built-1.8.13.run-1.7.1.out")]


def main():
    rows = []
    for built, run, name in CASES:
        text = (HERE / name).read_text()
        s0 = re.search(r"\[S0\] .*pydisort ([\d.]+)", text)
        assert s0 and s0.group(1) == run, f"{name}: runtime pydisort {s0.group(1) if s0 else '?'} is not {run}"
        s6 = re.findall(r"^\[S6\] .*$", text, re.M)
        aborts = sum(1 for ln in s6 if "double free" in ln or "free()" in ln)
        passed = sum(1 for ln in s6 if re.search(r"exit 0, 2 passed", ln))
        rows.append((built, run, len(s6), passed, aborts))
        print(f"[A1] built against pydisort {built}, run with {run}: {len(s6)} runs, {passed} clean, {aborts} aborted")
    bad = [f"{b}->{r}" for b, r, _, _, a in rows if a]
    print(f"[A2] combinations with an abort: {', '.join(bad) if bad else 'none'}")
    if "--csv" in sys.argv:
        out = ["built,run,runs,clean,aborted"] + [",".join(map(str, r)) for r in rows]
        Path(sys.argv[sys.argv.index("--csv") + 1]).write_text("\n".join(out) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
