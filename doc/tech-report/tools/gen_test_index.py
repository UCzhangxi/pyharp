#!/usr/bin/env python3
"""Generate Appendix C, the test index, from the tests the pinned package's CMake registers at the pin.

The pinned package is the repository `code_pin.yml` names (pyharp). The index is one table row per test that
`ctest` lists for it: its name, its ctest labels, the `add_test` (or `setup_test`, ...) call that defines it,
named as the link's anchor symbol and linked at the pin (STYLE 3.1, 10.6), and its ctest properties a reader
needs (expected to fail, skip code, processes, serial). Rows are sorted by test name. Tests that the build
registers for a fetched dependency (a test suite under `_deps/`) are counted in the header and not listed.

Two committed files, so the docs CI never builds the package:

  * `tools/ctest-index.json`, the fixture: `ctest --show-only=json-v1` of a configured build at
    the pin, reduced to the package's tests and the fields the index uses, with the source and build
    directories replaced by `<source>` and `<build>`, so it holds no machine path (STYLE 9.7). It
    records the pin, the configure switches (every `option()` of the top CMakeLists.txt, and
    CMAKE_BUILD_TYPE) and the ctest version.
  * `book/chapters/appendices/_appc-test-index.qmd`, the fragment, generated from the fixture
    and included by the Appendix C file `book/chapters/appc-test-index.qmd`.

    python3 tools/gen_test_index.py                    # regenerate the fragment from the fixture
    python3 tools/gen_test_index.py --check            # CI: exit 1 if the fragment is not what the fixture gives
    python3 tools/gen_test_index.py --refresh <build>  # when the pin moves: re-read a configured build at the
                                                       # new pin, rewrite the fixture and the fragment
    python3 tools/gen_test_index.py --ctest-n ctest-n.txt   # plain `ctest -N` text: names only, to stdout

`--refresh` needs a build directory configured (`cmake -B <build> -DBUILD_TESTS=ON ...`; building it is not
needed: the Python tests are registered by a glob at configure time, the C++ tests by `setup_test`). The source
is either a clean checkout of the pinned repository, whose HEAD is taken as the pin (a dirty tree is refused), or
a tree exported with `git archive <sha>`, which carries no history: then `--pin <sha>` names it. Configuring
needs torch, pyharp and pydisort importable by the `python` on PATH (the package's FindTorch/FindHarp/FindDisort).
Exit status 0 on success, 1 if `--check` finds a difference, 2 for a usage or input error.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parent.parent
FIXTURE = REPORT / "tools" / "ctest-index.json"
FRAGMENT = REPORT / "book" / "chapters" / "appendices" / "_appc-test-index.qmd"
CODE_PIN = REPORT / "code_pin.yml"


def _repository(pin_file: Path = CODE_PIN) -> str:
    """The `repo:` of code_pin.yml, the one home of the pinned repository's name."""
    m = re.search(r"^repo:\s*(\S+)", pin_file.read_text(), re.M) if pin_file.exists() else None
    if not m:
        raise SystemExit(f"error: {pin_file} names no repo:")
    return m.group(1)


REPOSITORY = _repository()
PACKAGE = REPOSITORY.rsplit("/", 1)[-1]
FORMAT = "pyharp-report ctest index 1"

#: ctest properties shown in the Notes column, and how.
NOTES = {
    "WILL_FAIL": lambda v: "expected to fail" if v else "",
    "SKIP_RETURN_CODE": lambda v: f"skips on exit {v}",
    "PROCESSORS": lambda v: f"{v} processes",
    "RUN_SERIAL": lambda v: "runs alone" if v else "",
    "DISABLED": lambda v: "disabled" if v else "",
}
#: properties kept in the fixture besides LABELS (the rest are machine-specific: paths, environment).
KEPT = ("LABELS", "TIMEOUT", *NOTES)


def _git(src: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(src), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def reduce_ctest_json(info: dict, source: str, build: str) -> tuple[list[dict], dict[str, int]]:
    """The package's tests from `ctest --show-only=json-v1`, and the count of the others by origin.

    A test is the package's if no frame of its backtrace is under `<build>/_deps/`. Its definition is the
    outermost frame that has a line: the call in a CMakeLists.txt, not the add_test inside a macro.
    """
    graph = info["backtraceGraph"]
    files, nodes, commands = graph["files"], graph["nodes"], graph["commands"]

    def rel(path: str) -> str:
        path = path.replace(build.rstrip("/"), "<build>", 1) if path.startswith(build) else path
        path = path.replace(source.rstrip("/") + "/", "", 1) if path.startswith(source) else path
        return path

    tests, external = [], {}
    for t in info["tests"]:
        frames, i = [], t.get("backtrace")
        while i is not None:
            n = nodes[i]
            frames.append((rel(files[n["file"]]), n.get("line"), commands[n["command"]] if "command" in n
                           else None))
            i = n.get("parent")
        deps = [f for f, _, _ in frames if f.startswith("<build>/_deps/")]
        if deps:
            origin = deps[0].split("/")[2].removesuffix("-src").removesuffix("-build")
            external[origin] = external.get(origin, 0) + 1
            continue
        where = [(f, line, cmd) for f, line, cmd in frames if line is not None][-1]
        props = {p["name"]: p["value"] for p in t.get("properties", []) if p["name"] in KEPT}
        tests.append({"name": t["name"], "defined_at": f"{where[0]}:{where[1]}", "via": where[2],
                      "properties": props})
    return tests, external


def _is_checkout(src: Path) -> bool:
    r = subprocess.run(["git", "-C", str(src), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return r.returncode == 0 and Path(r.stdout.strip()).resolve() == src.resolve()


def refresh(build: Path, pin: str | None = None) -> dict:
    """The fixture of a configured build directory at the pin: a clean checkout, or an export named by `pin`."""
    cache = (build / "CMakeCache.txt").read_text()
    source = re.search(r"^CMAKE_HOME_DIRECTORY:INTERNAL=(.*)$", cache, re.M).group(1)
    built = re.search(r"^CMAKE_CACHEFILE_DIR:INTERNAL=(.*)$", cache, re.M).group(1)  # the path cmake recorded
    if _is_checkout(Path(source)):
        if _git(Path(source), "status", "--porcelain", "--untracked-files=no"):
            raise SystemExit(f"error: {source} has uncommitted changes; the index must come from the pin")
        sha = _git(Path(source), "rev-parse", "HEAD")
        if pin and not sha.startswith(pin):
            raise SystemExit(f"error: {source} is at {sha}, not at --pin {pin}")
    elif pin and re.fullmatch(r"[0-9a-f]{40}", pin):
        sha = pin  # an exported tree (git archive <sha>): it carries no history to check
    else:
        raise SystemExit(f"error: {source} is not a git checkout; name the exported sha with --pin <40-hex sha>")
    p = subprocess.run(["ctest", "--show-only=json-v1"], cwd=build, capture_output=True, text=True, check=True)
    version = subprocess.run(["ctest", "--version"], capture_output=True, text=True).stdout.split()[2]
    # the switches that decide which tests register: every option() of the top CMakeLists.txt, and the build type
    names = ["CMAKE_BUILD_TYPE", *re.findall(r"^\s*option\s*\(\s*(\w+)",
                                              (Path(source) / "CMakeLists.txt").read_text(), re.M | re.I)]
    options = {k: v for k, v in re.findall(r"^(\w+):\w+=(.*)$", cache, re.M) if k in names}
    tests, external = reduce_ctest_json(json.loads(p.stdout), source, built)
    return {"format": FORMAT, "repository": REPOSITORY, "pin": sha, "ctest_version": version,
            "configure": " ".join(f"-D{k}={v}" for k, v in sorted(options.items())),
            "registered": len(tests) + sum(external.values()), "external": dict(sorted(external.items())),
            "tests": sorted(tests, key=lambda t: t["name"])}


def _code_link(pin: str, defined_at: str) -> str:
    path, line = defined_at.rsplit(":", 1)
    text = "/".join(path.split("/")[-2:]) if path.count("/") else path   # tests/CMakeLists.txt
    return f"[`{text}:{line}`](https://github.com/{REPOSITORY}/blob/{pin}/{path}#L{line})"


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def fragment(fixture: dict) -> str:
    """The Quarto fragment of Appendix C. Same fixture, same bytes."""
    pin, tests = fixture["pin"], fixture["tests"]
    others = ", ".join(f"{k}: {n}" for k, n in fixture["external"].items())
    package = fixture["repository"].rsplit("/", 1)[-1]
    listed = (f"`ctest -N` lists {fixture['registered']}; the other {sum(fixture['external'].values())} are the "
              f"test suites of dependencies the build fetches ({others}), not {package}'s tests."
              if fixture["external"] else
              f"`ctest -N` lists the same {fixture['registered']}: the build registers no test of a fetched dependency.")
    lines = [
        "<!-- GENERATED by tools/gen_test_index.py from tools/ctest-index.json; do not edit.",
        f"     pin: {fixture['repository']} {pin}",
        f"     ctest {fixture['ctest_version']}, configured with {fixture['configure']}",
        "     refresh: python3 tools/gen_test_index.py --refresh <build> -->",
        "",
        f"The {len(tests)} tests that {package}'s CMake registers at "
        f"[`{pin}`](https://github.com/{REPOSITORY}/commit/{pin}), one row each, sorted by name. "
        f"The build was configured with `{fixture['configure']}`; other switches register other tests. " + listed,
        "",
        "| test | labels | defined at | notes |",
        # pandoc sizes the PDF columns by the dashes: 40/19/28/13 per cent of the text width
        "|" + "|".join("-" * n for n in (40, 19, 28, 13)) + "|",
    ]
    for t in tests:
        props = t["properties"]
        labels = ", ".join(props.get("LABELS", [])) or "—"
        notes = "; ".join(n for n in (f(props[k]) for k, f in NOTES.items() if k in props) if n) or ""
        # the CMake call on the cited line is the link's anchor symbol (STYLE 3.1): the test name itself is
        # usually built by a macro or a loop and is not on the line
        defined = f"`{t['via']}` ({_code_link(pin, t['defined_at'])})"
        lines.append(f"| `{_cell(t['name'])}` | {_cell(labels)} | {defined} "
                     f"| {_cell(notes)} |")
    lines += ["", f": The tests registered at {fixture['repository']} {pin}. {{#tbl-appc-tests}}", ""]
    return "\n".join(lines)


def parse_ctest_n(text: str) -> list[str]:
    """Test names from plain `ctest -N` output (`  Test #12: name`), in ctest's order."""
    return re.findall(r"^\s*Test\s+#\d+:\s+(\S+)\s*$", text, re.M)


def _dump(fixture: dict) -> str:
    return json.dumps(fixture, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="exit 1 if the fragment differs from the fixture's")
    mode.add_argument("--refresh", type=Path, metavar="BUILD", help="rewrite the fixture from a configured build")
    ap.add_argument("--pin", metavar="SHA", help="with --refresh: the sha of a tree exported by git archive")
    mode.add_argument("--ctest-n", type=Path, metavar="FILE", help="list the names in plain `ctest -N` output")
    ap.add_argument("--fixture", type=Path, default=FIXTURE)
    ap.add_argument("--fragment", type=Path, default=FRAGMENT)
    args = ap.parse_args(argv)

    if args.ctest_n:
        names = parse_ctest_n(args.ctest_n.read_text())
        print("\n".join(f"| `{_cell(n)}` |" for n in sorted(names)))
        print(f"gen_test_index: {len(names)} tests in {args.ctest_n}", file=sys.stderr)
        return 0
    if args.refresh:
        fixture = refresh(args.refresh, args.pin)
        args.fixture.parent.mkdir(parents=True, exist_ok=True)
        args.fixture.write_text(_dump(fixture))
    try:
        fixture = json.loads(args.fixture.read_text())
    except (OSError, ValueError) as e:
        print(f"error: cannot read the fixture {args.fixture}: {e}", file=sys.stderr)
        return 2
    if fixture.get("format") != FORMAT:
        print(f"error: {args.fixture} is not a '{FORMAT}' fixture", file=sys.stderr)
        return 2
    want = fragment(fixture)
    if args.check:
        have = args.fragment.read_text() if args.fragment.exists() else ""
        if have == want:
            print(f"gen_test_index: {args.fragment.name} is current ({len(fixture['tests'])} tests at "
                  f"{fixture['pin']})", file=sys.stderr)
            return 0
        diff = difflib.unified_diff(have.splitlines(), want.splitlines(), f"{args.fragment.name} (committed)",
                                    f"{args.fragment.name} (from {args.fixture.name})", lineterm="")
        print("\n".join(list(diff)[:60]))
        print(f"gen_test_index: {args.fragment} does not match {args.fixture}; regenerate it with "
              "python3 tools/gen_test_index.py and commit both", file=sys.stderr)
        return 1
    args.fragment.parent.mkdir(parents=True, exist_ok=True)
    args.fragment.write_text(want)
    print(f"gen_test_index: wrote {len(fixture['tests'])} tests at {fixture['pin']} to {args.fragment}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
