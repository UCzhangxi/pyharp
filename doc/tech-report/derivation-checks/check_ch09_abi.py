"""ch09: the binary interface between a pyharp build and the pydisort it loads.

(a) The sizes of the pydisort types pyharp's library allocates and copies (disort_state, disort::DisortImpl,
    disort::DisortOptionsImpl), compiled against the headers of each pydisort installation given on the command
    line, with the torch headers of the running environment. Different sizes mean a pyharp library compiled
    against one version and run against the other lays the objects out differently from the code that fills them.
(b) How the installed pyharp library finds libdisort: the RPATH/RUNPATH entries of pyharp's `libharp_release.so`,
    reported as relative ($ORIGIN) or absolute, without printing the absolute paths themselves.

Run: python3 check_ch09_abi.py <site-packages A> <site-packages B>   (each holding a pydisort/ directory; needs
g++ and readelf). Exit status: the number of FAIL lines.
"""

import glob
import os
import platform
import re
import subprocess
import sys
import tempfile

import torch

SRC = r"""
#include <cstdio>
#include <disort/disort.hpp>
int main() {
  std::printf("%zu %zu %zu\n", sizeof(disort_state), sizeof(disort::DisortImpl),
              sizeof(disort::DisortOptionsImpl));
  return 0;
}
"""


def sizes(site, workdir):
    inc = os.path.join(site, "pydisort")
    meta = glob.glob(os.path.join(site, "pydisort-*.dist-info", "METADATA"))
    ver = "?"
    if meta:
        with open(meta[0]) as f:
            m = re.search(r"^Version:\s*(\S+)", f.read(), re.M)
        ver = m.group(1) if m else "?"
    tdir = os.path.dirname(torch.__file__)
    exe = os.path.join(workdir, f"sz_{abs(hash(site))}")
    src = os.path.join(workdir, "sz.cpp")
    with open(src, "w") as f:
        f.write(SRC)
    cmd = ["g++", "-std=c++17", f"-D_GLIBCXX_USE_CXX11_ABI={int(torch._C._GLIBCXX_USE_CXX11_ABI)}", f"-I{inc}",
           f"-I{tdir}/include", f"-I{tdir}/include/torch/csrc/api/include", src, "-o", exe, f"-L{tdir}/lib",
           "-lc10", "-ltorch_cpu", f"-Wl,-rpath,{tdir}/lib"]
    subprocess.run(cmd, check=True, capture_output=True)
    out = subprocess.run([exe], check=True, capture_output=True, text=True).stdout.split()
    return ver, [int(x) for x in out]


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    print(f"versions: python {platform.python_version()}, torch {torch.__version__}, "
          f"g++ {subprocess.run(['g++', '-dumpfullversion'], capture_output=True, text=True).stdout.strip()}")
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import ch09_common
    print(ch09_common.env_line())
    n, fails = 0, 0
    with tempfile.TemporaryDirectory() as wd:
        (va, sa), (vb, sb) = sizes(sys.argv[1], wd), sizes(sys.argv[2], wd)
    names = ["disort_state", "DisortImpl", "DisortOptionsImpl"]
    for i, nm in enumerate(names):
        n += 1
        print(f"[C{n}] INFO sizeof({nm}): pydisort {va} {sa[i]} bytes, pydisort {vb} {sb[i]} bytes, "
              f"difference {sb[i] - sa[i]:+d}")
    n += 1
    differ = sa != sb
    print(f"[C{n}] INFO the two pydisort versions lay out the types pyharp allocates differently: {differ}")
    import pyharp
    lib = os.path.join(os.path.dirname(pyharp.__file__), "lib", "libharp_release.so")
    n += 1
    if not os.path.exists(lib):
        print(f"[C{n}] FAIL pyharp's libharp_release.so is installed next to the package")
        fails += 1
    else:
        dyn = subprocess.run(["readelf", "-d", lib], capture_output=True, text=True).stdout
        paths = []
        for line in dyn.splitlines():
            m = re.search(r"\((RPATH|RUNPATH)\).*\[(.*)\]", line)
            if m:
                paths += [(m.group(1), p) for p in m.group(2).split(":")]
        desc = ", ".join(f"{k} {'relative ($ORIGIN)' if p.startswith('$ORIGIN') else 'absolute'} "
                         f"ending in {'/'.join(p.rstrip('/').split('/')[-2:])}" for k, p in paths) or "none"
        needed = re.findall(r"\(NEEDED\).*\[(libdisort[^\]]*)\]", dyn)
        print(f"[C{n}] INFO pyharp libharp_release.so: NEEDED {needed}; search path entries: {desc}")
    print(f"== check_ch09_abi: {n} labels, {fails} FAIL")
    sys.exit(fails)


if __name__ == "__main__":
    main()
