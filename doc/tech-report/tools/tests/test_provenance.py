"""Gate of quoted-result provenance (N7): every provenance tag names a full pyharp sha at or after the code pin that
resolves, and the command; a quoted timing adds its scope and repetitions.

The fixtures under fixtures/provenance are chapter files whose shas are placeholders ({pin}, {later}, {older},
{unknown}, {pin7}); each test fills them with the commits of a small git repository standing in for chengcli/pyharp,
so no test needs the network except the one on the real book, which is skipped when the pin cannot be resolved.

Run from the report directory: `python3 -m pytest tools/tests`.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import check_provenance as cp  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "provenance"
UNKNOWN = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture(scope="module")
def upstream(tmp_path_factory):
    """A stand-in pyharp history: older -> pin -> later."""
    repo = tmp_path_factory.mktemp("upstream")
    env = ["-c", "user.name=t", "-c", "user.email=t@example.org", "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    shas = {}
    for name in ("older", "pin", "later"):
        subprocess.run(["git", "-C", str(repo), *env, "commit", "--quiet", "--allow-empty", "-m", name], check=True)
        shas[name] = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True,
                                    capture_output=True, text=True).stdout.strip()
    return repo, shas


def _report(tmp_path, upstream, *fixtures, baseline=None):
    """A report layout with one chapter file per fixture, the pin in code_pin.yml and an optional baseline."""
    repo, shas = upstream
    report = tmp_path / "report"
    for i, name in enumerate(fixtures, 1):
        text = (FIX / name).read_text()
        for key, sha in {**shas, "pin7": shas["pin"][:7], "unknown": UNKNOWN}.items():
            text = text.replace("{" + key + "}", sha)
        q = report / "book" / "chapters" / f"{i:02d}-{Path(name).stem}.qmd"
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_text(text)
    (report / "tools").mkdir(parents=True)
    (report / "code_pin.yml").write_text(f"repo: chengcli/pyharp\nsha: {shas['pin']}\n")
    if baseline is not None:
        (report / "tools" / "provenance-baseline.json").write_text(json.dumps(baseline))
    return report


def _why(tmp_path, upstream, fixture):
    report = _report(tmp_path, upstream, fixture)
    resolve = cp.Resolver(report, upstream[1]["pin"], fetch=False, local=[upstream[0]])
    return [v["why"] for v in cp.violations(report, resolve)]


# --- RED: each missing piece of a tag fails ---------------------------------------------------------------------

def test_a_short_sha_fails(tmp_path, upstream):
    assert _why(tmp_path, upstream, "short-sha.qmd") == [f"short sha {upstream[1]['pin'][:7]}"]


def test_an_unresolvable_sha_fails(tmp_path, upstream):
    assert _why(tmp_path, upstream, "unresolvable.qmd") == [f"sha {UNKNOWN[:12]} does not resolve in chengcli/pyharp"]


def test_a_sha_before_the_pin_fails(tmp_path, upstream):
    older, pin = upstream[1]["older"], upstream[1]["pin"]
    assert _why(tmp_path, upstream, "before-pin.qmd") == [
        f"sha {older[:12]} is not the code pin {pin[:12]} or a later commit"]


def test_a_missing_command_fails(tmp_path, upstream):
    assert _why(tmp_path, upstream, "no-command.qmd") == ["no command (no `run:` field with a backticked command)"]


def test_a_timing_without_scope_and_repetitions_fails(tmp_path, upstream):
    assert _why(tmp_path, upstream, "timing-no-scope.qmd") == ["timing without `scope:` and `reps:`"]


def test_the_code_pin_phrase_and_another_repositorys_sha_are_not_a_pyharp_sha(tmp_path, upstream):
    assert [w.split(" (")[0] for w in _why(tmp_path, upstream, "code-pin-phrase.qmd")] == ["no full sha"] * 2


# --- GREEN: a complete tag passes -------------------------------------------------------------------------------

def test_complete_tags_pass(tmp_path, upstream):
    assert _why(tmp_path, upstream, "complete.qmd") == []


# --- the ratchet --------------------------------------------------------------------------------------------------

def test_the_check_fails_only_above_the_baseline(tmp_path, upstream):
    report = _report(tmp_path, upstream, "complete.qmd", "no-command.qmd", baseline={"ch02": 1})
    resolve = cp.Resolver(report, upstream[1]["pin"], fetch=False, local=[upstream[0]])
    assert cp.check(report, resolve=resolve)[0] == 0
    (report / "tools" / "provenance-baseline.json").write_text("{}")
    status, msgs, _ = cp.check(report, resolve=resolve)
    assert status == 1
    assert msgs[0].startswith("ch02: 1 tag problem(s), baseline 0; e.g. chapters/02-no-command.qmd:5: no command")


def test_update_writes_the_counts(tmp_path, upstream, monkeypatch):
    monkeypatch.setenv("PYHARP_REPO", str(upstream[0]))
    monkeypatch.setenv("PYHARP_REPORT_CACHE", str(tmp_path / "cache"))
    report = _report(tmp_path, upstream, "complete.qmd", "no-command.qmd", "timing-no-scope.qmd")
    assert cp.main([str(report), "--update"]) == 0
    assert json.loads((report / "tools" / "provenance-baseline.json").read_text()) == {"ch02": 1, "ch03": 1}
    assert cp.main([str(report)]) == 0


def test_the_render_gate_runs_the_provenance_gate(tmp_path, upstream, monkeypatch, capsys):
    import render_gate as rg
    report = _report(tmp_path, upstream, "complete.qmd", "no-command.qmd", baseline={"ch02": 1})
    base = _target(report)
    assert _gate(report, upstream, monkeypatch, base) == 0
    _set(report, {})
    assert _gate(report, upstream, monkeypatch, base) == 1
    assert "no command" in capsys.readouterr().out
    (report / "code_pin.yml").unlink()
    assert rg.gate_provenance(report / "book") == 0   # not the report layout: skipped


# --- the baseline cannot drift: it is present, it does not rise against the target branch, it equals the counts ---

NO_COMMAND = "\nThe flux is 2e-3 [sha: {pin}; deck: `c.yaml`; CPU].\n"


def _git(report, *args):
    return subprocess.run(["git", "-C", str(report), "-c", "user.name=t", "-c", "user.email=t@example.org",
                           "-c", "commit.gpgsign=false", *args], check=True, capture_output=True, text=True).stdout


def _target(report):
    """Commit the report as the target branch and return its sha."""
    _git(report, "init", "--quiet")
    _git(report, "add", "-A")
    _git(report, "commit", "--quiet", "-m", "target")
    return _git(report, "rev-parse", "HEAD").strip()


def _gate(report, upstream, monkeypatch, base_ref):
    import render_gate as rg
    monkeypatch.setenv("PYHARP_REPO", str(upstream[0]))
    monkeypatch.setenv("PYHARP_REPORT_CACHE", str(report.parent / "cache"))
    monkeypatch.setenv("PROVENANCE_BASE_REF", base_ref)
    return rg.gate_provenance(report / "book")


def _set(report, baseline):
    (report / "tools" / "provenance-baseline.json").write_text(json.dumps(baseline))


def test_a_missing_baseline_fails_the_gate(tmp_path, upstream, monkeypatch, capsys):
    report = _report(tmp_path, upstream, "complete.qmd", baseline={})
    base = _target(report)
    (report / "tools" / "provenance-baseline.json").unlink()
    assert _gate(report, upstream, monkeypatch, base) >= 1
    assert "tools/provenance-baseline.json is missing" in capsys.readouterr().out


def test_a_hand_raised_chapter_fails_against_the_target_branch(tmp_path, upstream, monkeypatch, capsys):
    report = _report(tmp_path, upstream, "complete.qmd", "no-command.qmd", baseline={"ch02": 1})
    base = _target(report)
    q = report / "book" / "chapters" / "02-no-command.qmd"
    q.write_text(q.read_text() + NO_COMMAND.replace("{pin}", upstream[1]["pin"]))
    _set(report, {"ch02": 2})          # the baseline equals the new count, but rises against the target
    assert _gate(report, upstream, monkeypatch, base) >= 1
    assert "ch02: the baseline rises 1 -> 2 against" in capsys.readouterr().out


def test_a_new_chapter_entry_is_a_rise_from_zero(tmp_path, upstream, monkeypatch, capsys):
    report = _report(tmp_path, upstream, "complete.qmd", "no-command.qmd", baseline={"ch02": 1})
    base = _target(report)
    (report / "book" / "chapters" / "03-new.qmd").write_text(
        "# New {#sec-ch03}\n" + NO_COMMAND.replace("{pin}", upstream[1]["pin"]))
    _set(report, {"ch02": 1, "ch03": 1})
    assert _gate(report, upstream, monkeypatch, base) >= 1
    assert "ch03: the baseline rises 0 -> 1 against" in capsys.readouterr().out


def test_an_unrecorded_fall_fails(tmp_path, upstream, monkeypatch, capsys):
    report = _report(tmp_path, upstream, "complete.qmd", "no-command.qmd", baseline={"ch02": 2})
    base = _target(report)              # the count is 1 and the baseline still says 2
    assert _gate(report, upstream, monkeypatch, base) >= 1
    assert "ch02: 1 tag problem(s), baseline 2; the baseline must equal the count" in capsys.readouterr().out


def test_a_target_branch_that_is_not_there_fails(tmp_path, upstream, monkeypatch, capsys):
    report = _report(tmp_path, upstream, "complete.qmd", "no-command.qmd", baseline={"ch02": 1})
    _target(report)
    assert _gate(report, upstream, monkeypatch, "origin/no-such-branch") >= 1
    assert "names no commit here" in capsys.readouterr().out


def test_a_recorded_fall_and_a_first_baseline_pass(tmp_path, upstream, monkeypatch):
    report = _report(tmp_path, upstream, "complete.qmd", "no-command.qmd", baseline={"ch02": 2})
    base = _target(report)
    _set(report, {"ch02": 1})           # the fall recorded
    assert _gate(report, upstream, monkeypatch, base) == 0
    _git(report, "rm", "--quiet", "--cached", "tools/provenance-baseline.json")
    _git(report, "commit", "--quiet", "-m", "no baseline at the target")
    assert _gate(report, upstream, monkeypatch, "HEAD") == 0   # the change that introduces the baseline


# --- the real book ------------------------------------------------------------------------------------------------

def test_the_book_is_within_its_baseline():
    report = TOOLS.parent
    resolve = cp.Resolver(report, cp.read_pin(report))
    if resolve(resolve.pin) is not None:
        pytest.skip("the code pin does not resolve here (no clone of pyharp and no network)")
    status, msgs, found = cp.check(report, resolve=resolve)
    assert status == 0, msgs
    base = json.loads((TOOLS / "provenance-baseline.json").read_text())
    assert sum(base.values()) >= len(found)


def test_an_explicit_repository_prefix_on_the_pin_passes():
    pin = cp.read_pin(TOOLS.parent)
    for sha in (f"pyharp@{pin}", f"chengcli/pyharp@{pin}"):
        tag = {"fields": {"sha": sha, "run": "`python3 run.py a.yaml`"}, "text": ""}
        assert not cp.problems(tag, lambda sha: None)


@pytest.mark.parametrize("run", [
    "a Python probe that builds `MeshBlock(MeshBlockOptions.from_yaml(...))` and runs one stage",
    "`MeshBlock(MeshBlockOptions.from_yaml(...))`",
])
def test_api_snippets_are_not_producing_commands(run):
    tag = {"fields": {"sha": UNKNOWN, "run": run}, "text": ""}
    assert cp.problems(tag, lambda sha: None) == [
        "no command (no `run:` field with a backticked command)"]
