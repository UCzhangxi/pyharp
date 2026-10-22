"""tools/ratchet_gate.py: each check fails on a planted instance (RED) and passes once it is removed (GREEN),
the ratchet fails on a rise, on an unrecorded fall and on a baseline raised without a pin move, and the owner
lock and the review-record writer behave as documented."""
import json
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import ratchet_gate as rg  # noqa: E402

PIN = "6fbb39750f62b83df096058a4746e77d0a634bc5"
OTHER = "e894700ff7aee30b52882e5202b16461413780b0"
RECORD_HEAD = "file\tkind\treviewer\tauthor\tpin\tsha256\tdate\tnote\n"
OWNERS = "chapter\towner\npreface\ted\nch01\treviewer_a\nch02\treviewer_b\n"

CH01 = """# Overview {#sec-ch01}

<!-- PROVENANCE
pin: pyharp@%s
status: %s
author: ReviewerA
-->

## Scheme one {#sec-ch01-one}

The stage calls the flux (see @sec-ch02-two).%s
"""
CH02 = """# Second {#sec-ch02}

## Scheme two {#sec-ch02-two}

It reads the state of @sec-ch01-one and @sec-ch01.%s
"""
PREFACE = "# Preface {.unnumbered}\n\nThe code is cited at the pin.%s\n"


def make(tmp_path, ch01_extra="", ch02_extra="", status="draft", record="", provenance_pin=PIN, preface="",
         owners=OWNERS):
    root = tmp_path / "tr"
    (root / "book" / "chapters").mkdir(parents=True)
    (root / "tools").mkdir()
    (root / "reviews").mkdir()
    (root / "code_pin.yml").write_text(f"repo: chengcli/pyharp\nsha: {PIN}\n")
    (root / "tools" / "package-pins.json").write_text(json.dumps({"pydisort": "c55b13b2" + "0" * 32}))
    if owners is not None:
        (root / "tools" / "chapter-owners.tsv").write_text(owners)
    (root / "book" / "index.qmd").write_text(PREFACE % preface)
    (root / "book" / "chapters" / "01-overview.qmd").write_text(CH01 % (provenance_pin, status, ch01_extra))
    (root / "book" / "chapters" / "02-second.qmd").write_text(CH02 % ch02_extra)
    (root / "reviews" / "review-record.tsv").write_text(RECORD_HEAD + record)
    return root


def counts(root):
    return rg.count(root)


def baseline_zero(root):
    (root / "tools" / "ratchet-baseline.json").write_text(json.dumps({"pin": PIN, "chapters": {}}))


def check(root, *extra):
    return rg.main(["--root", str(root), "check", *extra])


# ---- (a) history phrases ------------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    " Since chengcli/pyharp#303 the slope is centred.",
    " This section describes main after the merge.",
    " The bug is now fixed.",
    " See #307 for the change.",
    # misses of the first version, found in the book
    " It was checked against main at pyharp@" + PIN + ".",
    " The PR head was squash-merged as the pin.",
    " At the previous pin the term was missing.",
    " A consequence recorded in the pull request is the cost.",
    " The default of `some-switch` is now `face`.",
    " The parent cache was introduced in PR 223.",
    " Fixed upstream in pyharp#303.",
    " A run before and after that change does not agree bitwise.",
    " The flag is no longer the default.",
    " See [#303](https://example.org) for the change.",
    # misses of the second version, found in an earlier book
    " Two things changed between the\npins.",                     # a phrase broken across source lines
    " A lesson from the same PR.",
    " The body reports, for commit 4, the same digest.",
    " The scalar flux now passes the face states through the seam.",
    " The corrected term now also runs on curvilinear grids.",
    " The tests that encoded the old off default set the switch.",
    " The note's status line is superseded by the gather.",
    " Five of the cases crashed before the fix.",
    " The test passes at the head on CPU.",
    " The digest is compared against its base.",
    " The implicit part was moved into the implicit operator by a later change.",
    # the three forms the editor's sign-off named
    " The face value was previously taken from the cell centre.",
    " In an earlier version the slope was one-sided.",
    " The limiter used to clip the density at zero.",
])
def test_history_red(tmp_path, text):
    root = make(tmp_path, ch01_extra=text)
    assert counts(root)["ch01"]["history"] >= 1
    baseline_zero(root)
    assert check(root) == 1


@pytest.mark.parametrize("text", [
    # false hits of the first version: the same words describing physics or code, found in the book
    " The grid is no longer uniform after the faces move.",
    " CMake generates the macro interface used to select compiled readers.",
    " A source can make previously exchanged ghosts stale.",
    " The mass that was removed from the cell is booked as heat.",
    " The provenance is given at the head of the Derivation layer.",
    " Now consider the second face.",
    " The variable `pr` is the pressure.",
    " The column is mixed until the mixture is non-negative.",
    # "used to" in its passive and purpose uses, found in an earlier book
    " This draft performs no registered CTest run, and a visible GPU is not used to infer CUDA support.",
    " The flux limiter is used to bound the face states.",
    " The weights are often used to compute the face average.",
])
def test_history_green_for_physics_wording(tmp_path, text):
    root = make(tmp_path, ch01_extra=text)
    assert counts(root)["ch01"]["history"] == 0


def test_history_green_exempts_footnotes_provenance_shortcodes(tmp_path):
    extra = ("[^src]\n\n[^src]: chengcli/pyharp#303 body, Limits.\n"
             " {{< code src/a.cpp a_function >}}\n\n```python\n# since #303\n```\n")
    root = make(tmp_path, ch01_extra=extra)
    assert counts(root)["ch01"]["history"] == 0


def test_history_overlap_counts_once(tmp_path):
    root = make(tmp_path, ch01_extra=" It changed after #307.")
    assert counts(root)["ch01"]["history"] == 1


# ---- (b) off-pin shas ---------------------------------------------------------------------------------------

def test_offpin_red_and_green_in_body(tmp_path):
    bad = f" [`a.cpp:1`](https://github.com/chengcli/pyharp/blob/{OTHER}/src/a.cpp#L1) and pyharp@{OTHER[:7]}."
    root = make(tmp_path, ch01_extra=bad)
    assert counts(root)["ch01"]["offpin"] == 2
    good = f" [`a.cpp`](https://github.com/chengcli/pyharp/blob/{PIN}/src/a.cpp) and pyharp@{PIN}."
    root2 = make(tmp_path / "g", ch01_extra=good)
    assert counts(root2)["ch01"]["offpin"] == 0


def test_offpin_red_in_provenance_header(tmp_path):
    root = make(tmp_path, provenance_pin=OTHER)
    assert counts(root)["ch01"]["offpin"] == 1
    assert counts(make(tmp_path / "g"))["ch01"]["offpin"] == 0


@pytest.mark.parametrize("extra", [
    f"\n\n<!-- a comment: re-run at pyharp@{OTHER} -->\n",
    f"\n\n```python\n# ported from pyharp@{OTHER}\nx = 1\n```\n",
    f" The note is `docs/derivations/note.md@{OTHER}` §2.",
    f" The run is recorded at `{OTHER}`.",
])
def test_offpin_red_in_comments_code_paths_and_bare_shas(tmp_path, extra):
    root = make(tmp_path, ch01_extra=extra)
    assert counts(root)["ch01"]["offpin"] == 1


def test_offpin_red_in_preface(tmp_path):
    root = make(tmp_path, preface=f" The pin is [`pyharp`](https://github.com/chengcli/pyharp/commit/{OTHER}).")
    assert counts(root)["preface"]["offpin"] == 1
    assert counts(make(tmp_path / "g"))["preface"]["offpin"] == 0


def test_offpin_green_for_pinned_and_shortcodes(tmp_path):
    extra = (f" `docs/derivations/note.md@{PIN}` §2; pydisort@c55b13b2{'0' * 32}; "
             "{{< code src/a.cpp a_function >}}.")
    root = make(tmp_path, ch01_extra=extra)
    assert counts(root)["ch01"]["offpin"] == 0


def test_offpin_other_package(tmp_path):
    root = make(tmp_path, ch01_extra=" pydisort@" + "1" * 40 + " and pydisort@c55b13b2" + "0" * 32 + ".")
    assert counts(root)["ch01"]["offpin"] == 1


# ---- (c) status vs the review record ------------------------------------------------------------------------

def entry(root, kind="review", reviewer="ReviewerB", author="ReviewerA", pin=PIN, note="", sha=None):
    text = (root / "book" / "chapters" / "01-overview.qmd").read_text()
    sha = sha or rg.content_hash(text)
    return f"chapters/01-overview.qmd\t{kind}\t{reviewer}\t{author}\t{pin}\t{sha}\t2026-10-12\t{note}\n"


def with_record(root, *lines):
    (root / "reviews" / "review-record.tsv").write_text(RECORD_HEAD + "".join(lines))
    return root


def test_status_red_without_record(tmp_path):
    root = make(tmp_path, status="reviewed")
    assert counts(root)["ch01"]["status"] == 1


def test_status_green_with_record(tmp_path):
    root = make(tmp_path, status="reviewed")
    with_record(root, entry(root))
    assert counts(root)["ch01"]["status"] == 0


@pytest.mark.parametrize("kw", [dict(reviewer="ReviewerA"), dict(pin=OTHER), dict(sha="0" * 64)])
def test_status_red_bad_entry(tmp_path, kw):
    root = make(tmp_path, status="reviewed")
    with_record(root, entry(root, **kw))
    assert counts(root)["ch01"]["status"] == 1


def test_status_restamp(tmp_path):
    root = make(tmp_path, status="reviewed")
    first = entry(root)
    (root / "book" / "chapters" / "01-overview.qmd").write_text(
        (root / "book" / "chapters" / "01-overview.qmd").read_text() + "\nOne more sentence.\n")
    with_record(root, first)
    assert counts(root)["ch01"]["status"] == 1  # RED: content moved past the review
    with_record(root, first, entry(root, kind="restamp", reviewer="ReviewerC", note="typo"))
    assert counts(root)["ch01"]["status"] == 1  # RED: re-stamp by someone else
    with_record(root, first, entry(root, kind="restamp", note=""))
    assert counts(root)["ch01"]["status"] == 1  # RED: re-stamp without a note
    with_record(root, first, entry(root, kind="restamp", note="one sentence added"))
    assert counts(root)["ch01"]["status"] == 0  # GREEN


def test_status_edit_keeps_hash():
    a = "<!-- PROVENANCE\nstatus: draft\n-->\ntext\n"
    b = "<!-- PROVENANCE\nstatus: reviewed\nreviewer: ReviewerB\n-->\ntext\n"
    assert rg.content_hash(a) == rg.content_hash(b)


def test_record_command_writes_review_and_restamp(tmp_path):
    root = make(tmp_path, status="reviewed")
    f = "chapters/01-overview.qmd"
    assert counts(root)["ch01"]["status"] == 1
    assert rg.main(["--root", str(root), "record", "review", f, "--reviewer", "ReviewerA", "--author", "ReviewerA"]) == 1
    assert rg.main(["--root", str(root), "record", "review", f, "--reviewer", "ReviewerB", "--author", "ReviewerA"]) == 0
    assert counts(root)["ch01"]["status"] == 0
    p = root / "book" / f
    p.write_text(p.read_text() + "\nA new sentence.\n")
    assert counts(root)["ch01"]["status"] == 1
    assert rg.main(["--root", str(root), "record", "restamp", f, "--reviewer", "ReviewerC", "--note", "x"]) == 1
    assert rg.main(["--root", str(root), "record", "restamp", f, "--reviewer", "ReviewerB"]) == 1
    assert rg.main(["--root", str(root), "record", "restamp", f, "--reviewer", "ReviewerB",
                    "--note", "one sentence added"]) == 0
    assert counts(root)["ch01"]["status"] == 0
    rows = rg.read_record(root)[f]
    assert [r["kind"] for r in rows] == ["review", "restamp"]
    assert rows[-1]["pin"] == PIN and rows[-1]["author"] == "ReviewerA"


# ---- (d) cross-references -----------------------------------------------------------------------------------

def test_xref_green_when_cited_across(tmp_path):
    root = make(tmp_path, ch02_extra=" And @sec-ch02 itself.")
    c = counts(root)
    assert c["ch01"]["xref"] == 0
    assert c["ch02"]["xref"] == 1  # sec-ch02 is cited only from inside ch02


def test_xref_red_dangling(tmp_path):
    root = make(tmp_path, ch01_extra=" See @sec-ch01-missing.")
    assert counts(root)["ch01"]["xref"] == 1


# ---- the ratchet --------------------------------------------------------------------------------------------

def test_ratchet_rise_and_fall(tmp_path):
    root = make(tmp_path, ch01_extra=" The bug is now fixed.")
    assert rg.main(["--root", str(root), "update"]) == 0
    assert check(root) == 0
    (root / "book" / "chapters" / "01-overview.qmd").write_text(
        (root / "book" / "chapters" / "01-overview.qmd").read_text() + " Since #303 too.\n")
    assert check(root) == 1                                   # a rise fails
    assert rg.main(["--root", str(root), "update"]) == 1      # and the baseline cannot be raised
    (root / "book" / "chapters" / "01-overview.qmd").write_text(CH01 % (PIN, "draft", ""))
    assert check(root) == 1                                   # a fall fails until the baseline is lowered
    assert rg.main(["--root", str(root), "update"]) == 0
    assert check(root) == 0


def test_update_raises_only_with_a_pin_move(tmp_path):
    root = make(tmp_path)
    assert rg.main(["--root", str(root), "update"]) == 0
    p = root / "book" / "chapters" / "01-overview.qmd"
    p.write_text(p.read_text() + f" Re-run at pyharp@{OTHER}.\n")
    assert rg.main(["--root", str(root), "update"]) == 1      # same pin: no rise
    (root / "code_pin.yml").write_text(f"repo: chengcli/pyharp\nsha: {'1' * 40}\n")
    assert rg.main(["--root", str(root), "update"]) == 0      # the pin moves: the rise is allowed
    assert json.loads((root / "tools" / "ratchet-baseline.json").read_text())["pin"] == "1" * 40


def test_check_fails_on_a_stale_baseline_pin(tmp_path):
    root = make(tmp_path)
    assert rg.main(["--root", str(root), "update"]) == 0
    (root / "code_pin.yml").write_text(f"repo: chengcli/pyharp\nsha: {'1' * 40}\n")
    assert check(root) == 1


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin"})


def test_check_base_ref_rejects_a_hand_raised_baseline(tmp_path):
    root = make(tmp_path)
    assert rg.main(["--root", str(root), "update"]) == 0
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "tag", "base")
    # a new instance and the baseline edited by hand to match it: the plain check passes, the base-ref one fails
    p = root / "book" / "chapters" / "01-overview.qmd"
    p.write_text(p.read_text() + " Since #303 too.\n")
    b = json.loads((root / "tools" / "ratchet-baseline.json").read_text())
    b["chapters"]["ch01"]["history"] += 1
    (root / "tools" / "ratchet-baseline.json").write_text(json.dumps(b))
    assert check(root) == 0
    assert check(root, "--base-ref", "base") == 1
    # the same rise together with a pin move is allowed: update writes it, and the base-ref check passes
    (root / "code_pin.yml").write_text(f"repo: chengcli/pyharp\nsha: {'1' * 40}\n")
    assert rg.main(["--root", str(root), "update"]) == 0
    assert check(root, "--base-ref", "base") == 0


def test_check_base_ref_fails_loudly_when_it_names_no_commit(tmp_path, capsys):
    root = make(tmp_path)
    assert rg.main(["--root", str(root), "update"]) == 0
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    assert check(root, "--base-ref", "HEAD") == 0
    # a mistyped or unfetched target must not turn the baseline protection off
    assert check(root, "--base-ref", "origin/no-such-branch") == 1
    assert "names no commit" in capsys.readouterr().out


# ---- owners -------------------------------------------------------------------------------------------------

def test_no_contributor_assignment_file_is_required(tmp_path, capsys):
    root = make(tmp_path, owners=None)
    assert rg.main(["--root", str(root), "update"]) == 0
    assert check(root) == 0
    assert "| owner |" not in capsys.readouterr().out


def test_owner_table_counts_figures_and_tables(tmp_path, capsys):
    fig = "\n```{python}\n#| label: fig-ch01-a\nplot()\n```\n\n![B](b.png){#fig-ch01-b}\n"
    tbl = "\n| a |\n|---|\n| 1 |\n\n: One. {#tbl-ch01-a}\n\n<!-- {#tbl-ch01-hidden} -->\n"
    root = make(tmp_path, ch01_extra=fig + tbl, ch02_extra="\n\n| b |\n|---|\n| 2 |\n\n: Two. {#tbl-ch02-a}\n")
    assert rg.assets(root) == {"preface": {"figures": 0, "tables": 0}, "ch01": {"figures": 2, "tables": 1},
                               "ch02": {"figures": 0, "tables": 1}}
    assert rg.main(["--root", str(root), "counts"]) == 0
    out = capsys.readouterr().out
    assert "| owner |" not in out
    assert "| ch01 |" in out and "| ch02 |" in out


def test_chapter_of():
    assert rg.chapter_of("chapters/06-kinetics/_rates.qmd") == "ch06"
    assert rg.chapter_of("chapters/13-verification.qmd") == "ch13"
    assert rg.chapter_of("chapters/appendices/_appb-derivation-index.qmd") == "appb"
    assert rg.chapter_of("chapters/appb-derivations/_part.qmd") == "appb"
    assert rg.chapter_of("index.qmd") == "preface"


def test_chapter_of_keeps_the_letter_of_a_split_chapter():
    """A split chapter (STYLE 10.1) is its own owner row: `01b-parcel-model` is ch01b, not ch01 or the file name."""
    assert rg.chapter_of("chapters/01b-parcel-model.qmd") == "ch01b"
    assert rg.chapter_of("chapters/01b-parcel-model/_state.qmd") == "ch01b"
    assert rg.chapter_of("chapters/01-overview/_map.qmd") == "ch01"


def test_the_repository_omits_contributor_assignments():
    assert not (rg.ROOT / "tools/chapter-owners.tsv").exists()
