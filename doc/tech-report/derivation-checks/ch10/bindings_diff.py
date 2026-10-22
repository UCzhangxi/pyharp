#!/usr/bin/env python3
"""Chapter 10 check: C++ option structs against the live Python bindings and the .pyi stubs.

For every struct under src/ of a pyharp source tree, the options it declares with ADD_ARG and the boolean flag
accessors (`bool name() const { return has_flag(...) }`) are compared with
  - the attributes of the Python class of the same name (without the `Impl` suffix) in the installed `pyharp`
    and `pyharp.opacity` modules (the bindings), and
  - the `def` names under the class of the same name in python/*.pyi (the stubs).
Prints one [B1] line per struct, the totals [B2], and the bound classes no stub declares [B3].

Usage: python3 bindings_diff.py <pyharp source tree> [--csv <file>]. The installed pyharp must be built from that
tree. Exit status 0; the counts are the result."""
import re, sys, pathlib, importlib
root = pathlib.Path(sys.argv[1])
fields = {}
for hp in sorted((root / "src").rglob("*.hpp")):
    cur = None
    for line in hp.read_text().splitlines():
        m = re.match(r"\s*struct\s+(\w+)\s*(?::[^{]*)?\{", line)
        if m: cur = m.group(1); continue
        m = re.search(r"ADD_ARG\((.*),\s*(\w+)\)\s*[=;]", line)
        if m and cur: fields.setdefault((cur, hp.relative_to(root).as_posix()), []).append(m.group(2))
        m = re.match(r"\s*bool\s+(\w+)\(\)\s*const\s*\{\s*return\s+has_flag", line)
        if m and cur: fields.setdefault((cur, hp.relative_to(root).as_posix()), []).append(m.group(1))
stubs = {}
for pyi in (root / "python").glob("*.pyi"):
    cur = None
    for line in pyi.read_text().splitlines():
        m = re.match(r"class\s+(\w+)", line)
        if m: cur = m.group(1); stubs.setdefault(cur, set()); continue
        m = re.match(r"\s+def\s+(\w+)\(", line)
        if m and cur: stubs[cur].add(m.group(1))
mods = [importlib.import_module(n) for n in ("pyharp", "pyharp.opacity")]
def pyclass(name):
    for m in mods:
        if hasattr(m, name): return getattr(m, name)
total_bind = total_stub = 0
rows = []
print(f"[B0] {'C++ struct':28} {'file':36} {'n':>3} {'py class':22} {'miss_bind':>9} {'miss_stub':>9}  missing")
for (st, f), names in sorted(fields.items()):
    py = st[:-4] if st.endswith("Impl") else st
    cls = pyclass(py)
    mb = [n for n in names if cls is None or not hasattr(cls, n)]
    ms = [n for n in names if n not in stubs.get(py, set())]
    total_bind += len(mb); total_stub += len(ms)
    print(f"[B1] {st:28} {f:36} {len(names):3d} {py if cls else py+' (unbound)':22} {len(mb):9d} {len(ms):9d}  "
          f"bind:{','.join(mb) or '-'} stub:{','.join(ms) or '-'}")
    rows.append((py, len(names), len(mb), len(ms), cls is not None))
print(f"[B2] missing from bindings: {total_bind}; missing from stubs: {total_stub}")
# module-level classes bound but absent from stubs
bound = sorted(n for m in mods for n in dir(m) if isinstance(getattr(m, n), type) and getattr(m, n).__module__.startswith("pyharp") and not n.startswith("_"))
print("[B3] bound classes absent from any .pyi:", [n for n in bound if n not in stubs])
if "--csv" in sys.argv:
    with open(sys.argv[sys.argv.index("--csv") + 1], "w") as fh:
        fh.write("struct,options,missing_bindings,missing_stubs,bound\n")
        for r in rows:
            fh.write(f"{r[0]},{r[1]},{r[2]},{r[3]},{int(r[4])}\n")
