#!/usr/bin/env python3
"""Chapter 10 check: which pyharp tests exist, which ctest registers, and which CI runs.

Reads a pyharp source tree (the pin of code_pin.yml) and prints, with stable labels:
  [I1] every C++ test file under tests/, whether tests/CMakeLists.txt registers it with `setup_test`, and the
       number of gtest assertion macros (EXPECT_*, ASSERT_*) it contains;
  [I2] every Python test file under tests/ and tests/spectra/, whether ctest runs it (an uncommented `add_test`
       naming it) and whether .github/workflows/ci.yml runs it with pytest;
  [I3] the counts per category, also written as CSV with --csv <file> for the chapter's data figure;
  [I4] the CI matrix read from ci.yml: operating systems, Python version, the pydisort and torch pins, and whether
       any job builds with CUDA.

Usage: python3 test_inventory.py <pyharp source tree> [--csv <file>]. Standard library only. Exit status 0.
"""
import re
import sys
from pathlib import Path


def main():
    root = Path(sys.argv[1])
    cm = (root / "tests/CMakeLists.txt").read_text()
    registered = set(re.findall(r"^\s*setup_test\((\w+)\)", cm, re.M))
    add_test_live = [ln for ln in cm.splitlines() if re.match(r"^\s*add_test", ln)]
    ci = (root / ".github/workflows/ci.yml").read_text()
    ci_py = set(re.findall(r"(tests/[\w/]+\.py)", ci))

    rows = []
    print("[I1] C++ test files (file | registered by setup_test | assertion macros)")
    for f in sorted((root / "tests").glob("*.cpp")):
        n = len(re.findall(r"\b(?:EXPECT|ASSERT)_[A-Z_]+\s*\(", f.read_text()))
        reg = f.stem in registered
        rows.append(("cpp", f.name, reg, reg, n))
        print(f"[I1] {f.name} | {'yes' if reg else 'NO'} | {n}")

    print("[I2] Python test files (file | run by ctest | run by CI)")
    pyfiles = sorted((root / "tests").glob("test_*.py")) + sorted((root / "tests/spectra").glob("test_*.py"))
    for f in pyfiles:
        rel = f.relative_to(root).as_posix()
        in_ctest = any(f.name in ln for ln in add_test_live)
        in_ci = rel in ci_py
        rows.append(("py-spectra" if "spectra" in rel else "py-top", rel, in_ctest, in_ci, None))
        print(f"[I2] {rel} | {'yes' if in_ctest else 'no'} | {'yes' if in_ci else 'no'}")

    print("[I3] counts (category | files | registered in ctest | run by CI | files with zero assertion macros)")
    cats = [("C++", "cpp"), ("Python tests/", "py-top"), ("Python tests/spectra/", "py-spectra")]
    csv = ["category,files,in_ctest,in_ci"]
    for name, key in cats:
        sel = [r for r in rows if r[0] == key]
        files = len(sel)
        in_ctest = sum(1 for r in sel if r[2])
        in_ci = sum(1 for r in sel if (r[3] if key != "cpp" else r[2]))   # CI runs ctest, so C++ = registered
        zero = sum(1 for r in sel if r[4] == 0)
        print(f"[I3] {name} | {files} | {in_ctest} | {in_ci} | {zero if key == 'cpp' else '-'}")
        csv.append(f"{name},{files},{in_ctest},{in_ci}")

    oses = re.search(r"os:\s*\[([^\]]*)\]", ci)
    pyv = re.search(r'PYTHON_VERSION:\s*"([^"]+)"', ci)
    pyd = re.search(r"pydisort==([\d.]+)", ci)
    torch = sorted(set(re.findall(r"torch==([\d.]+)", ci)))
    cuda = bool(re.search(r"-DCUDA=ON|nvcc|cuda-toolkit", ci, re.I))
    print(f"[I4] CI build-and-test: os [{oses.group(1) if oses else '?'}], Python {pyv.group(1) if pyv else '?'}, "
          f"pydisort=={pyd.group(1) if pyd else '?'} (--no-deps), torch {','.join(torch)}, CUDA build: {cuda}")

    if "--csv" in sys.argv:
        Path(sys.argv[sys.argv.index("--csv") + 1]).write_text("\n".join(csv) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
