"""Follow-up to the review of the per-chapter compare: what must be compared, and what must not depend on the host.

  - a version on a check line ([I4], the CI pins read from ci.yml) is a result and is compared;
  - the pydisort version and the pyharp/pydisort source shas of a dropped environment line are compared;
  - check_ch09_abi [C5] gives the same line for a library linked with DT_RPATH or DT_RUNPATH, and a different line
    for a different search path;
  - run_suite.sh truncates a gcc message to 140 characters whatever the locale and coreutils build.

Run from the report directory: `python3 -m pytest tools/tests`.
"""

import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
CHECKS = TOOLS.parent / "derivation-checks"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(CHECKS))

import compare_outputs as co  # noqa: E402


def compare(tmp_path, rel, expected, actual):
    for side, text in (("e", expected), ("a", actual)):
        (tmp_path / side / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / side / rel).write_text(text)
    out = io.StringIO()
    return co.compare("chXX", tmp_path / "e", tmp_path / "a", [rel], stream=out), out.getvalue()


def perturbed(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (path.name, old)
    return text, text.replace(old, new)


# --- [I4]: the CI pins are a check result -----------------------------------------------------------------------
@pytest.mark.parametrize("old,new", [
    ("Python 3.11, pydisort==1.7.1", "Python 3.12, pydisort==1.7.1"),
    ("torch 2.10.0, CUDA build", "torch 2.9.1, CUDA build"),
])
def test_a_changed_ci_pin_on_the_i4_check_line_fails(tmp_path, old, new):
    a, b = perturbed(CHECKS / "ch10" / "test_inventory.out", old, new)
    assert compare(tmp_path, "ch10/test_inventory.out", a, b)[0] == 1


def test_toolchain_versions_on_environment_lines_are_still_masked(tmp_path):
    a, b = perturbed(CHECKS / "ch10" / "invariants.out", "torch 2.10.0+cu128, numpy 2.4.6, Python 3.11.13",
                     "torch 2.10.0+cu126, numpy 2.4.7, Python 3.11.12")
    assert compare(tmp_path, "ch10/invariants.out", a, b)[0] == 0


# --- pydisort provenance on the dropped environment lines -------------------------------------------------------
@pytest.mark.parametrize("rel,old,new", [
    ("check_ch05_analytic.out", "tag commit 8af15242a265a60ea6fb51c29d48e6688a63ab67",
     "tag commit 8af15242a265a60ea6fb51c29d48e6688a63ab68"),
    ("check_ch05_analytic.out", "pydisort 1.7.1, scipy", "pydisort 1.7.2, scipy"),
    ("ch08_config.pydisort-1.8.13.out", "pydisort source 74f8d7e995545a686b04d503b6f81135af48d87c",
     "pydisort source 74f8d7e995545a686b04d503b6f81135af48d87d"),
    ("ch08_config.pydisort-1.8.13.out", "pyharp source f34506f9d14ee7b1f2e1222775baa5093ae6967f, pydisort",
     "pyharp source f34506f9d14ee7b1f2e1222775baa5093ae6967e, pydisort"),
])
def test_a_changed_pydisort_version_or_source_sha_fails(tmp_path, rel, old, new):
    a, b = perturbed(CHECKS / rel, old, new)
    assert compare(tmp_path, rel, a, b)[0] == 1


def test_the_rest_of_an_environment_line_is_still_dropped(tmp_path):
    a, b = perturbed(CHECKS / "check_ch05_analytic.out", "CPU AMD Ryzen 9 7950X 16-Core Processor, 32 logical",
                     "CPU Intel(R) Xeon(R) E-2236 CPU @ 3.40GHz, 12 logical")
    assert compare(tmp_path, "check_ch05_analytic.out", a, b)[0] == 0


# --- check_ch09_abi [C5]: RPATH or RUNPATH ----------------------------------------------------------------------
def test_c5_is_the_same_line_for_rpath_and_runpath_text():
    import check_ch09_abi as abi
    rpath = " 0x000000000000000f (RPATH)              Library rpath: [/a/site/pydisort/lib:/a/site/torch/lib]\n"
    runpath = " 0x000000000000001d (RUNPATH)            Library runpath: [/b/site/pydisort/lib:/b/site/torch/lib]\n"
    (t1, e1), (t2, e2) = abi.search_paths(rpath), abi.search_paths(runpath)
    assert (t1, t2) == (["RPATH"], ["RUNPATH"])
    assert e1 == e2 == ["absolute ending in pydisort/lib", "absolute ending in torch/lib"]


def link(tmp_path, name, rpath, new_dtags):
    src = tmp_path / "x.c"
    src.write_text("int x(void) { return 1; }\n")
    lib = tmp_path / f"lib{name}.so"
    flag = "--enable-new-dtags" if new_dtags else "--disable-new-dtags"
    subprocess.run(["gcc", "-shared", "-fPIC", str(src), "-o", str(lib), f"-Wl,{flag}", f"-Wl,-rpath,{rpath}"],
                   check=True, capture_output=True)
    return subprocess.run(["readelf", "-d", str(lib)], check=True, capture_output=True, text=True).stdout


@pytest.mark.skipif(not (shutil.which("gcc") and shutil.which("readelf")), reason="needs gcc and readelf")
def test_c5_with_real_rpath_and_runpath_libraries(tmp_path):
    import check_ch09_abi as abi
    same = "/opt/x/site-packages/pydisort/lib:/opt/x/site-packages/torch/lib"
    r = abi.search_paths(link(tmp_path, "r", same, False))
    u = abi.search_paths(link(tmp_path, "u", same, True))
    d = abi.search_paths(link(tmp_path, "d", "/opt/x/site-packages/torch/lib:/opt/x/site-packages/pydisort/lib", True))
    assert r[0] == ["RPATH"] and u[0] == ["RUNPATH"]
    assert r[1] == u[1] == ["absolute ending in pydisort/lib", "absolute ending in torch/lib"]
    assert d[1] != r[1]


def c5_output(tags, entries):
    return (f"host: libharp_release.so stores its search path as {' and '.join(tags)}\n"
            f"[C5] INFO pyharp libharp_release.so: NEEDED ['libdisort_release.so']; search path entries "
            f"(DT_RPATH or DT_RUNPATH): {', '.join(entries)}\n")


def test_c5_compare_passes_for_runpath_and_fails_for_another_path_list(tmp_path):
    committed = (CHECKS / "check_ch09_abi.out").read_text()
    c5 = [l for l in committed.splitlines(keepends=True) if l.startswith(("host: libharp", "[C5]"))]
    assert "".join(c5) == c5_output(["RPATH"], ["absolute ending in pydisort/lib", "absolute ending in torch/lib"])
    runpath = committed.replace("".join(c5), c5_output(["RUNPATH"], ["absolute ending in pydisort/lib",
                                                                      "absolute ending in torch/lib"]))
    other = committed.replace("".join(c5), c5_output(["RUNPATH"], ["relative ($ORIGIN) ending in pydisort/lib",
                                                                    "absolute ending in torch/lib"]))
    assert compare(tmp_path, "check_ch09_abi.out", committed, runpath)[0] == 0
    assert compare(tmp_path, "check_ch09_abi.out", committed, other)[0] == 1


# --- run_suite.sh: 140 characters, not bytes --------------------------------------------------------------------
GCC_LINE = ("test_yaml_input.cpp:12:37: error: ‘from_yaml’ is not a member of ‘harp::RadiationOptions’ "
            "{aka ‘std::shared_ptr<harp::RadiationOptionsImpl>’}")


def truncation_pipeline():
    """The shell code run_suite.sh pipes a gcc message through for [S3], with any function it defines for that."""
    text = (CHECKS / "ch10" / "run_suite.sh").read_text()
    line = next(l for l in text.splitlines() if "does not compile |" in l)
    cmd = re.search(r"sed 's/\^\.\*tests\\///' \| (.*?)\)\" \| clean", line).group(1)
    defs = re.findall(r"^\w+\(\) \{.*?; \}$", text, re.M | re.S)
    return "\n".join(d for d in defs if d.split("(")[0] in cmd), cmd


@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize("locale", ["C", "C.UTF-8"])
def test_run_suite_truncates_a_multibyte_gcc_message_to_140_characters(tmp_path, locale):
    defs, cmd = truncation_pipeline()
    script = tmp_path / "t.sh"
    script.write_text(f"{defs}\n{cmd}\n")
    r = subprocess.run(["bash", str(script)], input=(GCC_LINE + "\n").encode(), capture_output=True,
                       env={"PATH": "/usr/bin:/bin:" + str(Path(sys.executable).parent), "LC_ALL": locale})
    assert r.returncode == 0, r.stderr
    assert r.stdout.decode("utf-8") == GCC_LINE[:140] + "\n"


def test_the_committed_run_suite_lines_hold_140_characters():
    for f in sorted((CHECKS / "ch10").glob("run_suite.*.out")):
        line = next(l for l in f.read_text().splitlines() if l.startswith("[S3] test_yaml_input: does not compile"))
        assert line.split(" | ", 1)[1] == GCC_LINE[:140], f.name
