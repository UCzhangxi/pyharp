"""The N2 task map: Appendix G generated from the curated reader-task list (tools/gen_reader_tasks.py).

Every row resolves to the labelled section that answers it, or names a reason; the source gate and the rendered
gate (index.aux, index.toc) each fail on a broken anchor, on a chapter roll-up and on a not-provided row without a
reason, and pass on the real list.

Run from the report directory: `python3 -m pytest tools/tests`.
"""
import copy
import shutil
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
REPORT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import gen_reader_tasks as g  # noqa: E402
import gen_task_map as gtm  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "reader-tasks"


@pytest.fixture(scope="module")
def real():
    """The fixture list and its book: a small report on which every source check is shown."""
    book = FIX / "book"
    return g.load((FIX / "tools/reader-tasks.md").read_text(encoding="utf-8")), gtm.labels(book), {}


FBOOK = FIX / "book"


def _row(rows, rid, **change):
    rows = copy.deepcopy(rows)
    next(r for r in rows if r["id"] == rid).update(change)
    return rows


# --- the list ---------------------------------------------------------------------------------------------------

def test_the_real_list_passes_and_the_appendix_is_fresh(capsys):
    assert g.check() == 0
    out = capsys.readouterr().out
    rows = g.load(g.DATA.read_text(encoding="utf-8"))
    assert f"[N2 reader tasks] 0 problem(s); {len(rows)} tasks" in out
    assert "finding" not in out and not (REPORT / "tools/reader-tasks-findings.json").exists()


def test_the_fixture_list_passes_with_its_statuses(real):
    rows, labs, bank = real
    assert g.problems(rows, labs, FBOOK, bank) == []
    assert g.counts(rows, bank) == {"answered": 2, "partly documented": 1, "undocumented": 1,
                                    "unsupported by the code": 0, "outside scope": 0}


@pytest.mark.parametrize("rid,where,note,bank,expected", [
    ("H03", "not provided: content gap: no deck", "", {}, "undocumented"),
    ("Q-007", "not provided: outside scope: a tutorial", "", {}, "outside scope"),
    ("Q-001", "sec-a", "§1", {"Q-001": {"status": "partly documented"}}, "partly documented"),
    ("Q-012a", "sec-a", "§1", {"Q-012": {"status": "answered"}}, "answered"),
    ("Q-004", "sec-a", "§1; partly: no units", {"Q-004": {"status": "answered"}}, "partly documented"),
    ("H20", "sec-a", "§7.6; FLAG PARTIAL", {}, "partly documented"),
    ("DO-x", "sec-a", "§1", {}, "answered"),
    ("H99", "not provided: nothing", "", {}, None),
])
def test_the_status_rule(rid, where, note, bank, expected):
    assert g.status(dict(id=rid, where=where, note=note), bank) == expected


@pytest.mark.parametrize("where,expected", [
    ("not provided: undocumented: no memory estimate (lookup: device memory 0 hits)", "no memory estimate"),
    ("not provided: outside scope: spin-up is a science study (agreed out); lookup: spin-up 0 hits",
     "spin-up is a science study"),
    ("not provided: undocumented: no tutorial; only the contract exists (sec-ch01-initialization)",
     "no tutorial; only the contract exists (@sec-ch01-initialization)"),
    ("not provided: not in the book: no mapping (13-diagnostics.qmd:19, 13-diagnostics.qmd:27)", "no mapping"),
    ("not provided: undocumented: (lookup: 0 hits)", ""),
])
def test_the_printed_reason_drops_the_reviewers_evidence(where, expected):
    assert g.reason(dict(where=where)) == expected


def test_a_broken_anchor_fails(real):
    rows, labs, bank = real
    bad = g.problems(_row(rows, "T-1", where="sec-ch01-nowhere"), labs, FBOOK, bank)
    assert bad == ["T-1: anchor sec-ch01-nowhere is not a label of the book"]


def test_a_roll_up_target_fails(real):
    rows, labs, bank = real
    bad = g.problems(_row(rows, "T-1", where="sec-ch01"), labs, FBOOK, bank)
    assert bad == ["T-1: anchor sec-ch01 is a chapter or appendix roll-up; label the answering section and "
                   "anchor the row there"]


def test_a_not_provided_row_without_a_reason_fails(real):
    rows, labs, bank = real
    bad = g.problems(_row(rows, "T-4", where="not provided: undocumented: (lookup: 0 hits)"), labs, FBOOK, bank)
    assert bad == ["T-4: not provided, but no reason"]
    bad = g.problems(_row(rows, "T-4", where="not provided"), labs, FBOOK, bank)
    assert bad[0].startswith("T-4: no status")


def test_a_roll_up_with_a_matching_finding_still_fails(real, tmp_path):
    """No exemption: an exemption list beside the data is a failure, and the roll-up it names fails too."""
    rows, labs, bank = real
    report = tmp_path / "report"
    (report / "tools").mkdir(parents=True)
    (report / "book").symlink_to(FBOOK)
    (report / "tools/reader-tasks-findings.json").write_text('{"roll-up": {"T-1": "sec-ch01"}}')
    bad = g.problems(_row(rows, "T-1", where="sec-ch01"), labs, report / "book", bank)
    assert bad == ["reader-tasks-findings.json: roll-up targets have no exemption; label the answering sections and "
                   "delete it",
                   "T-1: anchor sec-ch01 is a chapter or appendix roll-up; label the answering section and anchor "
                   "the row there"]


def test_every_anchor_is_a_section_of_its_own():
    rows, labs = g.load(g.DATA.read_text(encoding="utf-8")), gtm.labels(g.BOOK)
    assert [r["id"] for r in rows if not r["where"].startswith("not provided")
            and g.rollup(r["where"], labs, g.BOOK)] == []


@pytest.mark.parametrize("where,text", [
    ("not provided: outside scope: plotting output is a tutorial, which this report on the code does not give "
     "(scope test; agreed out)", "plotting output is a tutorial, which this report on the code does not give"),
    ("not provided: undocumented: the book states no restart procedure (lookup: restart 0 hits)",
     "the book states no restart procedure"),
])
def test_a_not_provided_reason_stands_on_its_own(where, text):
    """The printed reason says why, and does not send the reader elsewhere for an answer (STYLE N9)."""
    r = dict(id="T-9", where=where)
    assert g.reason(r) == text and "@sec" not in g.reason(r)


# --- the rendered book ------------------------------------------------------------------------------------------

def _rendered(tmp_path, aux=None, data=None, text_edit=None):
    root = tmp_path / "report"
    shutil.copytree(FIX, root)
    book = root / "book"
    if aux is not None:
        (book / "index.aux").write_text(aux)
    rows = g.load(data if data is not None else (root / "tools/reader-tasks.md").read_text())
    # the PDF text: the printed appendix, wrapped and hyphenated as pdftotext returns it
    text = g.render(rows, gtm.labels(book), {}).replace("Not provided: no shock-tube deck", "Not pro-\nvided: no shock-\ntube deck")
    return g.rendered_problems(book, rows, {}, text_edit(text) if text_edit else text)


def test_the_rendered_fixture_passes(tmp_path):
    problems, stats = _rendered(tmp_path)
    assert problems == []
    assert stats == dict(rows=4, anchored=3, not_provided=1, in_toc=3, roll_ups=0, unresolved=0)


def test_a_rendered_anchor_that_does_not_resolve_fails(tmp_path):
    aux = (FIX / "book/index.aux").read_text().replace("\\newlabel{sec-ch01-two}", "\\newlabel{sec-ch01-x}")
    problems, stats = _rendered(tmp_path, aux=aux)
    assert problems == ["T-2: anchor sec-ch01-two does not resolve in index.aux",
                        "T-3: anchor sec-ch01-two does not resolve in index.aux"] and stats["unresolved"] == 2


def test_a_rendered_roll_up_target_fails(tmp_path):
    data = (FIX / "tools/reader-tasks.md").read_text().replace("| T-1 | Run one example | T-1 | sec-ch01-one |",
                                                               "| T-1 | Run one example | T-1 | sec-ch01 |")
    problems, stats = _rendered(tmp_path, data=data)
    assert problems == ["T-1: anchor sec-ch01 lands on chapter.1, a chapter or appendix roll-up"]
    assert stats["roll_ups"] == 1


def test_a_reason_missing_from_the_rendered_pdf_fails(tmp_path):
    problems, _ = _rendered(tmp_path, text_edit=lambda t: t.replace("Not pro-\nvided: no shock-\ntube deck",
                                                                     "Not provided."))
    assert problems == ["T-4: not provided, but the rendered PDF prints no reason"]


def _pdftotext(monkeypatch, book, out):
    """pdf_text on a stand-in PDF whose pdftotext output is `out`."""
    import subprocess
    (book / "_book").mkdir(exist_ok=True)
    (book / "_book" / "report.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=out))
    return g.pdf_text(book)


# pdftotext puts the foot of a page (its number) and the head of the next (the running head) at each form feed
_BREAK = "Not provided: no shock-\n\n901\n\n\fUndocumented\n\ntube deck"


@pytest.mark.parametrize("pages", [
    pytest.param(lambda t: t.replace("## Undocumented {.unnumbered .unlisted}", "Undocumented"),
                 id="head-is-a-heading-of-the-body"),
    pytest.param(lambda t: "Undocumented\n\n" + t, id="head-repeats-on-another-page"),
])
def test_a_reason_split_by_a_page_break_still_matches(tmp_path, monkeypatch, pages):
    root = tmp_path / "report"
    shutil.copytree(FIX, root)
    rows = g.load((root / "tools/reader-tasks.md").read_text())
    text = pages(g.render(rows, gtm.labels(root / "book"), {})).replace("Not provided: no shock-tube deck", _BREAK)
    assert "\f" in text and "901" in text
    problems, stats = g.rendered_problems(root / "book", rows, {}, _pdftotext(monkeypatch, root / "book", text))
    assert problems == [] and stats["not_provided"] == 1


def test_page_furniture_stripping_keeps_the_body(tmp_path, monkeypatch):
    """Only a page number at the foot and a running head that the text prints again are furniture."""
    (tmp_path / "book").mkdir()
    out = ("Setup\n\nStep 3 of\n\n12\n\n\fSetup\n\nthe run.\nSee row\n\n42\n\nin the table.\n\f"
           "Once only\n\nthe end.\n\n13\n\n\f")
    assert _pdftotext(monkeypatch, tmp_path / "book", out) == (
        "Setup\n\nStep 3 of\n\n\n\f\nthe run.\nSee row\n\n42\n\nin the table.\n\fOnce only\n\nthe end.\n\n\n\f")


def test_the_rendered_gate_needs_a_render(tmp_path):
    (tmp_path / "book").mkdir()
    problems, _ = g.rendered_problems(tmp_path / "book", [], {})
    assert problems and "not found" in problems[0]


@pytest.mark.skipif(not (REPORT / "book/index.aux").exists(), reason="needs a local PDF render of the book")
def test_the_real_render_passes(capsys):
    assert g.check_rendered() == 0
    assert "0 unresolved" in capsys.readouterr().out
