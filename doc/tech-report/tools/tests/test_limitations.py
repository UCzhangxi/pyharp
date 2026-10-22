"""N9 advisory detection, structured replacements and include reachability."""
from pathlib import Path
import re
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_limitations as lint


@pytest.mark.parametrize("phrase", ["cannot show", "see elsewhere", "shown elsewhere",
                                    "beyond scope", "beyond the\nscope", "not documented"])
def test_unstructured_deferrals_warn(phrase):
    assert lint.findings("This is " + phrase + ".")


@pytest.mark.parametrize("note", ["Answered at @sec-specific.",
                                  "Not provided: the test cannot show convergence order."])
def test_structured_notes_do_not_warn(note):
    assert not lint.findings(note)


def test_unrelated_link_or_late_note_does_not_hide_deferral():
    assert lint.findings("See elsewhere. @sec-other. Not provided: unrelated.")


def test_comments_and_code_are_not_prose():
    assert not lint.findings("<!-- cannot show -->\n\n```text\nsee elsewhere\n```\n")


def test_data_drives_patterns(tmp_path):
    data = tmp_path / "phrases.json"
    data.write_text('{"phrases": ["deferred answer"]}')
    assert lint.findings("A deferred answer.", data=data)


def test_warning_exit_and_reachable_includes(tmp_path, capsys):
    (tmp_path / "_quarto.yml").write_text("book:\n  chapters: [index.qmd]\n")
    (tmp_path / "index.qmd").write_text("{{< include part.qmd >}}")
    (tmp_path / "part.qmd").write_text("See elsewhere.")
    (tmp_path / "unused.qmd").write_text("Cannot show.")
    assert lint.main(["--book", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "part.qmd:1" in output and "unused" not in output
    assert "1 warning(s)" in output


# A section whose deferrals were converted: every limitation is a structured note, so nothing warns; the same
# section before conversion warns once per deferral.
CONVERTED = """## A scheme {#sec-ch01-a}

The update is exact for a linear source.

**Not provided:** an error bound for a nonlinear source; this chapter does not derive it.

```text
beyond the scope of a code block
```

<!-- reviewer: cannot show the bound -->
"""
UNCONVERTED = """## A scheme {#sec-ch01-a}

The update is exact for a linear source. An error bound for a nonlinear source is beyond the scope of this note.

The general case is discussed elsewhere.
"""


def test_converted_prose_has_no_deferrals():
    assert not lint.findings(CONVERTED)
    assert [phrase for _, phrase in lint.findings(UNCONVERTED)] == ["beyond the scope", "discussed elsewhere"]


def test_rendered_pdf_warns_without_failing(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    def extract(command, **kwargs):
        assert command[0] == "pdftotext"
        return SimpleNamespace(stdout="First page.\fShown elsewhere.\f")
    monkeypatch.setattr(lint.subprocess, "run", extract)
    assert lint.main(["--pdf", str(tmp_path / "book.pdf")]) == 0
    assert "page 2:1: shown elsewhere" in capsys.readouterr().out


def test_numbered_note_and_actual_elsewhere_are_not_deferrals():
    assert not lint.findings("2. **Not provided:** a rationale; this is beyond scope.")
    assert not lint.findings("The field is zero elsewhere.")


def test_task_question_before_structured_note():
    assert not lint.findings("How do I plot? Not provided: plotting is outside scope.")
    assert lint.findings("See elsewhere. Not provided: plotting is outside scope.")


@pytest.mark.parametrize("phrase", ["not derived here", "not established here",
                                    "not measured here", "not derived or measured here",
                                    "cannot say"])
def test_review_deferral_forms_warn(phrase):
    assert lint.findings("This is " + phrase + ".")


# A converted note keeps the limitation and its reason: deleting the wording instead of converting it, or
# dropping the reason, is the repeated review defect this guards against.
NOTES = {
    "one note": ("**Not provided:** an error bound for each closure, without deriving each round-off bound; "
                 "this book does not derive those bounds.\n", 1),
    "two notes": ("**Not provided:** a convergence order; the test checks one resolution.\n\n"
                  "**Not provided:** a GPU timing; no GPU run is recorded at the pin.\n", 2),
}


@pytest.mark.parametrize("name", NOTES)
def test_review_notes_keep_the_limitation_and_reason(name):
    text, count = NOTES[name]
    assert text.count("**Not provided:**") >= count
    assert not lint.findings(text)
    for note in re.findall(r"\*\*Not provided:\*\*([^\n]*)", text):
        assert ";" in note and note.split(";", 1)[1].strip()       # the limitation, then its reason


def test_a_note_without_its_conversion_warns():
    assert lint.findings("An error bound for each closure is not derived here.")
