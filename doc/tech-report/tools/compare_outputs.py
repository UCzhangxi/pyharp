#!/usr/bin/env python3
"""Compare the committed outputs of a chapter's derivation checks with the ones its run script just regenerated.

A run script (derivation-checks/chNN_run.sh) overwrites the committed `.out` files in place. Compared byte for byte,
a fresh clone never reproduces them: every output also records the machine it ran on (CPU, GPU, compilers), the
toolchain versions, the build date folded into a local version string, and, for the cost and pytest checks, wall
times. This tool removes exactly those parts, by the explicit rules below, and compares everything else verbatim,
so a changed verdict, label, count or check value still fails.

Rules (each one is a regex in VOLATILE_LINES or VALUE_RULES; tools/tests/test_compare_outputs.py pins them):

  dropped lines   the environment description a check prints before its labelled lines: `versions: ...`,
                  `environment: ...` (also `env NAME: environment: ...`), `host: ...`, the bare
                  `python X.Y.Z, torch ...` version line and the `pyharp source <sha>, pydisort source <sha>` line.
  versions        `torch`, `numpy`, `scipy`, `mpmath`, `sympy`, `pytest`, `Python`, `gcc`, `g++`, `cmake` followed
                  by a version become `<name> <ver>`; the newest release a check looked up on PyPI becomes `<ver>`.
                  pyharp and pydisort versions are kept: they name the configuration under test.
  host            the filesystem a check's temporary directory was on, `(temporary directory on tmpfs)`, becomes
                  `(temporary directory on <fs>)`.
  dates           the `.dYYYYMMDD` of a local version string and ISO dates/times become `<date>`.
  timing          a pytest duration (` in 3.22s`) becomes ` in <time>`. On a timing line (one that reports a time per
                  unit, `12.3 us/column`) the times, the `(N x REF)` ratios of those times and the thread counts
                  (the default thread count is the host's core count) are masked; its label, verdict and the rest of
                  the line are kept.

Host-dependent measurements (--host-dependent JSON, derivation-checks/host-dependent.json): some check values are
measurements of the hardware, not of the code: CUDA-vs-CPU differences depend on the GPU, float32 floors and
bitwise-equal fractions on the CPU's vector unit, round-off-level errors on the CPU, and the crash counts of the
D1 check on chance. That file names each such line by a regex, with the reason and the evidence, and the mask to
apply: `values` (every number in scientific notation), `roundoff` (only those below 1e-15), `fraction` (a
`fraction 0.98` value), `counts` (`N failed, M passed` and `no summary`), `abort` (the abort message, except
`none`). Masks apply before the check's own tolerance, `(tol <= T)` or `(defect present when > T)`, which is
kept, as are the label, the verdict and the rest of the line: a measurement that crosses its tolerance flips
the verdict and fails. The comparison reports how many declared lines differed.

Without CUDA (--exclude-cuda REASON, used by ch09_run.sh when the GPU cannot run this torch build's kernels):
lines that mention CUDA are left out on both sides, `[Cn]` label numbers and `== ...: N labels` totals are not
compared (the CUDA labels are absent, so the numbering shifts), files named by --not-compared are reported as not
compared, and the verdict says `REPRODUCED WITHOUT CUDA` with the reason. Every CPU line is still compared verbatim.

usage: compare_outputs.py [--host-dependent JSON] [--exclude-cuda REASON [--not-compared FILE]...] CHAPTER EXPECTED_DIR ACTUAL_DIR FILE...
  FILE is a path relative to both directories. Prints one line per file and a final `CHAPTER: REPRODUCED` or
  `CHAPTER: NOT REPRODUCED`, with the normalised diff of every file that differs. Exit 0 when all files agree,
  1 when any differs or is missing, 2 on a usage error.
       compare_outputs.py [--host-dependent JSON [--as REL]] [--exclude-cuda REASON] --normalise FILE
                                            print FILE as the comparison sees it (REL: its name in JSON)
"""

import argparse
import difflib
import fnmatch
import json
import re
import sys
from pathlib import Path

VOLATILE_LINES = [
    re.compile(r"^versions:"),
    re.compile(r"^(?:env \S+: )?environment:"),
    re.compile(r"^host:"),
    re.compile(r"^python \d+\.\d+(?:\.\d+)?, torch \S+"),
    re.compile(r"^pyharp source [0-9a-f]{40}, pydisort source [0-9a-f]{40}\s*$"),
]

_NUM = r"\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"
_TIME_UNIT = r"(?:ns|us|µs|ms|s|sec|min)"
TIMING_LINE = re.compile(rf"\b{_NUM}\s?{_TIME_UNIT}/\w+")

VALUE_RULES = [  # (pattern, replacement, applies to timing lines only)
    (re.compile(r"\b(torch|numpy|scipy|mpmath|sympy|pytest|[Pp]ython|gcc|g\+\+|cmake) "
                r"\d+\.\d+(?:\.\d+)?(?:[-+.\w]*\w)?"), r"\1 <ver>", False),
    (re.compile(r"\b(newest \S+ on PyPI: ).*$"), r"\1<ver>", False),
    (re.compile(r"\.d20\d{6}\b"), ".d<date>", False),
    (re.compile(r"(\(temporary directory on )[^)]+\)"), r"\1<fs>)", False),
    (re.compile(r"\b20\d\d-[01]\d-[0-3]\d(?:[ T][0-2]\d:[0-5]\d(?::[0-5]\d(?:\.\d+)?)?)?"), "<date>", False),
    (re.compile(rf" in {_NUM}s\b(?: \(\d+:\d\d(?::\d\d)?\))?"), " in <time>", False),
    (re.compile(rf"\b{_NUM}\s?({_TIME_UNIT})/"), r"<time> \1/", True),
    (re.compile(rf"\({_NUM} x "), "(<ratio> x ", True),
    (re.compile(r"\b\d+ thread\(s\)"), "<n> thread(s)", True),
]


CUDA_LINE = re.compile(r"\bCUDA\b")
NO_CUDA_RULES = [(re.compile(r"^\[C\d+\]"), "[C]"), (re.compile(r"^(== \S+: )\d+ labels"), r"\1<n> labels")]


_SCI = re.compile(r"[-+]?\d\.\d+e[-+]\d+")
_TOLERANCE = re.compile(r" \((?:tol <=|defect present when >) [^)]*\)")
HOST_MASKS = {
    "values": (_SCI, lambda m: "<host>"),
    "roundoff": (_SCI, lambda m: "<roundoff>" if abs(float(m.group())) < 1e-15 else m.group()),
    "fraction": (re.compile(r"(?<=fraction )\d\.\d+"), lambda m: "<host>"),
    "counts": (re.compile(r"\b\d+ failed, \d+ passed(?: in <time>)?|\bno summary\b"), lambda m: "<counts>"),
    "abort": (re.compile(r"(?<=abort: )(?!none\b).+$"), lambda m: "<abort>"),
}


def load_host_dependent(path):
    """{file pattern: [(compiled line regex, [mask names])]} from a host-dependent.json"""
    if not path:
        return {}
    spec = json.loads(Path(path).read_text())["files"]
    rules = {}
    for pattern, entries in spec.items():
        rules[pattern] = []
        for e in entries:
            bad = [m for m in e["mask"] if m not in HOST_MASKS]
            if bad or not e.get("why"):
                raise ValueError(f"{path}: {pattern}: unknown mask {bad} or no 'why'")
            rules[pattern].append((re.compile(e["lines"]), list(e["mask"])))
    return rules


def rules_for(host_rules, rel):
    return [r for pat, rs in host_rules.items() if fnmatch.fnmatch(rel, pat) for r in rs]


def mask_host(line, rules):
    """Apply the declared masks of every rule whose regex matches; the tolerance part is never masked."""
    n = 0
    for rx, masks in rules:
        if not rx.search(line):
            continue
        tol = _TOLERANCE.search(line)
        head, tail = (line[:tol.start()], line[tol.start():]) if tol else (line, "")
        for m in masks:
            pat, rep = HOST_MASKS[m]
            new = pat.sub(rep, head)
            n += new != head
            head = new
        line = head + tail
    return line, n


def normalise(text, without_cuda=False, host=()):
    """(normalised lines, dropped line count, masked value count)"""
    out, dropped, masked = [], 0, 0
    for line in text.splitlines():
        if any(p.search(line) for p in VOLATILE_LINES) or (without_cuda and CUDA_LINE.search(line)):
            dropped += 1
            continue
        if without_cuda:
            for pat, rep in NO_CUDA_RULES:
                line, n = pat.subn(rep, line)
                masked += n
        timing = bool(TIMING_LINE.search(line))
        for pat, rep, timing_only in VALUE_RULES:
            if timing_only and not timing:
                continue
            line, n = pat.subn(rep, line)
            masked += n
        if host:
            line, n = mask_host(line, host)
            masked += n
        out.append(line)
    return out, dropped, masked


def compare(chapter, expected, actual, files, stream=sys.stdout, exclude_cuda=None, not_compared=(), host_rules=None):
    """Print the comparison; return the number of files that differ or are missing."""
    bad = host_diff = 0
    host_rules = host_rules or {}
    nc = exclude_cuda is not None
    print(f"compare {chapter}: {len(files)} outputs, committed copy vs regenerated "
          f"(version, host, timing and date lines normalised)", file=stream)
    if nc:
        print(f"  CUDA legs not run: {exclude_cuda}; lines that mention CUDA are not compared", file=stream)
    for rel in files:
        if rel in not_compared:
            print(f"  not compared  {rel} (needs the CUDA legs)", file=stream)
            continue
        e, a = Path(expected) / rel, Path(actual) / rel
        if not e.is_file() or not a.is_file():
            bad += 1
            print(f"  MISSING  {rel} ({'no committed copy' if not e.is_file() else 'not regenerated'})", file=stream)
            continue
        et, at = e.read_text(errors="replace"), a.read_text(errors="replace")
        host = rules_for(host_rules, rel)
        el, ed, em = normalise(et, nc, host)
        al, ad, am = normalise(at, nc, host)
        if el == al:
            note = ""
            if host:
                strict = difflib.unified_diff(normalise(et, nc)[0], normalise(at, nc)[0], lineterm="", n=0)
                k = sum(1 for d in strict if d.startswith("+") and not d.startswith("+++"))
                host_diff += k
                note = f"; {k} line(s) with declared host-dependent values differ" if k else ""
            print(f"  same     {rel} ({ad} volatile lines dropped, {am} values masked{note})", file=stream)
            continue
        bad += 1
        print(f"  DIFFERS  {rel}", file=stream)
        diff = list(difflib.unified_diff(el, al, "committed (normalised)", "regenerated (normalised)", lineterm="", n=0))
        for d in diff[:60]:
            print(f"    {d}", file=stream)
        if len(diff) > 60:
            print(f"    ... {len(diff) - 60} more diff lines", file=stream)
    if bad:
        verdict = f"NOT REPRODUCED ({bad} of {len(files)} outputs differ or are missing)"
    elif nc:
        verdict = f"REPRODUCED WITHOUT CUDA (CUDA legs not run: {exclude_cuda})"
    else:
        verdict = "REPRODUCED"
    if not bad and host_diff:
        verdict += (f" ({host_diff} line(s) differ only in declared host-dependent values; every label, verdict and "
                    f"tolerance matches)")
    print(f"{chapter}: {verdict}", file=stream)
    return bad


def main(argv):
    ap = argparse.ArgumentParser(usage=__doc__.split("usage: ")[1].split("\n")[0])
    ap.add_argument("--exclude-cuda", metavar="REASON")
    ap.add_argument("--not-compared", action="append", default=[], metavar="FILE")
    ap.add_argument("--host-dependent", metavar="JSON")
    ap.add_argument("--normalise", metavar="FILE")
    ap.add_argument("--as", dest="as_rel", metavar="REL")
    ap.add_argument("args", nargs="*")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    nc = a.exclude_cuda is not None
    host_rules = load_host_dependent(a.host_dependent)
    if a.normalise:
        host = rules_for(host_rules, a.as_rel or Path(a.normalise).name)
        print("\n".join(normalise(Path(a.normalise).read_text(errors="replace"), nc, host)[0]))
        return 0
    if len(a.args) < 4 or (a.not_compared and not nc):
        ap.print_usage(sys.stderr)
        return 2
    chapter, expected, actual, files = a.args[0], a.args[1], a.args[2], a.args[3:]
    return 1 if compare(chapter, expected, actual, files, exclude_cuda=a.exclude_cuda,
                        not_compared=set(a.not_compared), host_rules=host_rules) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
