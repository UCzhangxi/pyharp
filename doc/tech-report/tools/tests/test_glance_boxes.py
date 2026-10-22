"""Tests of tools/fix_glance_boxes.py and tools/check_glance_boxes.py (STYLE 2, the "At a glance" box).

Inside an `::: {.callout-note title="At a glance"}` block every line that starts with a bold field label
(`**Purpose.**`, `**Evidence.**`, any `**Word(s).**`) follows a blank line, so each field renders as its own
paragraph. A label directly after the opening fence needs no blank line.

Run from the report directory: `python3 -m pytest tools/tests`.
"""

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))

import check_glance_boxes  # noqa: E402
import fix_glance_boxes  # noqa: E402

JOINED = """## A scheme {#sec-ch99-a}

### Summary

::: {.callout-note title="At a glance"}
**Purpose.** Adds a source; @eq-ch99-a.
**Data.** In: the stage state. Out: the increment
[$\\mathrm{kg\\,m^{-3}}$], continued on a second line.
**Guarantee / limits.** First order in time.
**Evidence.** A test; the check `[C1]`.
:::

Prose after the box.
"""

FIXED = """## A scheme {#sec-ch99-a}

### Summary

::: {.callout-note title="At a glance"}
**Purpose.** Adds a source; @eq-ch99-a.

**Data.** In: the stage state. Out: the increment
[$\\mathrm{kg\\,m^{-3}}$], continued on a second line.

**Guarantee / limits.** First order in time.

**Evidence.** A test; the check `[C1]`.
:::

Prose after the box.
"""


def test_a_joined_box_fails_the_gate():
    problems = check_glance_boxes.problems(JOINED)
    assert [line for line, _ in problems] == [7, 9, 10]


def test_a_fixed_box_passes_the_gate():
    assert check_glance_boxes.problems(FIXED) == []


def test_fix_gives_the_fixed_box():
    assert fix_glance_boxes.fix_text(JOINED) == FIXED


def test_fix_run_twice_is_byte_identical():
    once = fix_glance_boxes.fix_text(JOINED)
    assert fix_glance_boxes.fix_text(once) == once
    assert fix_glance_boxes.fix_text(FIXED) == FIXED


def test_a_label_right_after_the_fence_needs_no_blank_line():
    text = '::: {.callout-note title="At a glance"}\n**Purpose.** One line.\n:::\n'
    assert check_glance_boxes.problems(text) == []
    assert fix_glance_boxes.fix_text(text) == text


def test_a_blank_line_is_not_doubled():
    text = '::: {.callout-note title="At a glance"}\n**Purpose.** A.\n\n**Data.** B.\n:::\n'
    assert fix_glance_boxes.fix_text(text) == text


def test_labels_outside_an_at_a_glance_box_are_untouched():
    text = ("Prose.\n**Purpose.** not in a box.\n"
            '::: {.callout-note title="Definition"}\n**Purpose.** A.\n**Data.** B.\n:::\n'
            '::: {.callout-important title="Test"}\n**Evidence.** A.\n**Coverage.** B.\n:::\n')
    assert fix_glance_boxes.fix_text(text) == text
    assert check_glance_boxes.problems(text) == []


def test_fenced_code_inside_a_box_is_untouched():
    text = ('::: {.callout-note title="At a glance"}\n**Purpose.** A.\n\n'
            "```yaml\n**Data.** not a label\n:::\n**Evidence.** still code\n```\n"
            "**Evidence.** B.\n:::\n")
    want = text.replace("```\n**Evidence.** B.", "```\n\n**Evidence.** B.")
    assert fix_glance_boxes.fix_text(text) == want
    assert [line for line, _ in check_glance_boxes.problems(text)] == [9]
    assert check_glance_boxes.problems(want) == []


def test_a_nested_div_does_not_end_the_box():
    text = ('::: {.callout-note title="At a glance"}\n**Purpose.** A.\n\n'
            "::: {.inner}\nnested text\n:::\n**Data.** B.\n:::\n**Data.** after the box.\n")
    want = text.replace(":::\n**Data.** B.", ":::\n\n**Data.** B.")
    assert fix_glance_boxes.fix_text(text) == want
    assert [line for line, _ in check_glance_boxes.problems(text)] == [7]


def test_bold_text_that_is_not_a_line_start_label_is_untouched():
    text = ('::: {.callout-note title="At a glance"}\n**What**: a colon form. **Switch**: none.\n'
            "Text with **Data.** mid-line.\n- **Purpose.** in a list item\n:::\n")
    assert fix_glance_boxes.fix_text(text) == text
    assert check_glance_boxes.problems(text) == []


def test_the_gate_lists_file_and_line(tmp_path, capsys):
    bad = tmp_path / "bad.qmd"
    bad.write_text(JOINED)
    good = tmp_path / "good.qmd"
    good.write_text(importlib.import_module("fix_glance_order").fix_text(FIXED))
    assert check_glance_boxes.main([str(good)]) == 0
    assert check_glance_boxes.main([str(bad), str(good)]) == 1
    out = capsys.readouterr().out
    assert f"{bad}:7:" in out and f"{bad}:9:" in out and f"{bad}:10:" in out and f"{good}:7: field label" not in out


def test_the_fix_script_rewrites_files_in_place(tmp_path):
    p = tmp_path / "a.qmd"
    p.write_text(JOINED)
    assert fix_glance_boxes.main([str(p)]) == 0
    assert p.read_text() == FIXED
    before = p.read_bytes()
    fix_glance_boxes.main([str(p)])
    assert p.read_bytes() == before

# Ordering fixtures also run in the existing ratchet CI test entry point.
import importlib
import pytest

BOX = '::: {.callout-note title="At a glance"}\n**Purpose.** A.\n:::\n\n'

@pytest.mark.parametrize('prefix', [BOX, 'Local symbols: $x$ is a coordinate.\n\n' + BOX,
    '::: {.callout-note title="Local symbols"}\n$x$: coordinate.\n:::\n\n' + BOX])
def test_order_moves_exact_paragraph_and_is_idempotent(prefix):
    order = importlib.import_module('fix_glance_order')
    prose = 'The first paragraph has $x$,  two spaces,\nand a second line.\n\n'
    text = '## Section {#sec-test}\n\n' + prefix + prose + 'Another paragraph.\n'
    want = '## Section {#sec-test}\n\n' + prose + prefix + 'Another paragraph.\n'
    assert order.fix_text(text) == want
    assert order.fix_text(want) == want


def test_order_skips_nonprose_and_keeps_section_boundary():
    order = importlib.import_module('fix_glance_order')
    prefix = ('## A\n\n<!-- provenance\ncomment -->\n\n' + BOX +
              '```python\n## fake\ntext\n```\n\n$$\nx=1\n$$\n\n| A | B |\n|---|---|\n\n- item\n\n')
    text = prefix + '## B\n\nReal prose.\n'
    assert order.fix_text(text) == text
    assert len(order.analyze(text)[1]) == 1


def test_order_local_symbols_before_summary():
    order = importlib.import_module('fix_glance_order')
    text = '## A\n\nLocal symbols: $x$.\n\n### Summary\n\n' + BOX + 'Opening prose.\n\n### Derivation\n\nLater prose.\n'
    assert order.fix_text(text).startswith('## A\n\nOpening prose.\n\nLocal symbols:')


def test_order_gate_and_report_only(tmp_path, capsys):
    order = importlib.import_module('fix_glance_order')
    p = tmp_path / 'order.qmd'
    p.write_text('## A\n\n' + BOX + 'Opening prose.\n')
    assert check_glance_boxes.main([str(p)]) == 1
    order.main([str(p)])
    assert check_glance_boxes.main([str(p)]) == 0
    p.write_text('## Empty\n\n' + BOX.replace('**Purpose.** A.', '\n'.join(['line'] * 7)))
    assert order.main(['--check', str(p)]) == 0
    output = capsys.readouterr().out
    assert 'no prose' in output and 'over 6 lines' in output


def test_order_preserves_crlf_bytes(tmp_path):
    order = importlib.import_module('fix_glance_order')
    p = tmp_path / 'crlf.qmd'
    text = ('## A\n\n' + BOX + 'Opening prose.\n\n').replace('\n', '\r\n')
    p.write_bytes(text.encode())
    order.main([str(p)])
    assert p.read_bytes() == ('## A\n\nOpening prose.\n\n' + BOX).replace('\n', '\r\n').encode()


def test_order_table_caption_is_not_prose():
    order = importlib.import_module('fix_glance_order')
    text = '## Table only\n\n' + BOX + '| A | B |\n|---|---|\n\n: Table caption.\n{#tbl-test}\n'
    assert order.fix_text(text) == text
    assert len(order.analyze(text)[1]) == 1


# Regression (1e702ad): the order tool took a paragraph from beyond a table or a "### Derivation" heading and left
# that block opening the section. It may move a paragraph only when nothing but blank lines separates it from the
# box's closing fence; otherwise it leaves the file alone and reports "needs a hand-written opening".
TABLE = '| A | B |\n|---|---|\n| 1 | 2 |\n\n: A table caption. {#tbl-test}\n\n'
ADJACENT_FIXTURES = [
    ('box->paragraph', '## A\n\n### Summary\n\n' + BOX + 'First prose.\n\nLater prose.\n',
     '## A\n\n### Summary\n\nFirst prose.\n\n' + BOX + 'Later prose.\n'),
    ('box->table->paragraph', '## A\n\n### Summary\n\n' + BOX + TABLE + 'Prose after the table.\n', None),
    ('box->### Derivation->paragraph',
     '## A\n\n### Summary\n\n' + BOX + '### Derivation\n\nFirst prose.\n\n### Numerical method\n\nSecond prose.\n', None),
]


@pytest.mark.parametrize('name,text,want', ADJACENT_FIXTURES, ids=[f[0] for f in ADJACENT_FIXTURES])
def test_order_moves_only_a_paragraph_directly_after_the_box(name, text, want, tmp_path, capsys):
    order = importlib.import_module('fix_glance_order')
    p = tmp_path / 'order.qmd'
    p.write_text(text)
    order.main([str(p)])
    out = capsys.readouterr().out
    if want is None:
        assert p.read_text() == text, f'{name}: a paragraph beyond the next block was moved'
        assert 'needs a hand-written opening' in out
        assert order.main(['--check', str(p)]) == 1
        assert 'needs a hand-written opening' in capsys.readouterr().out
    else:
        assert p.read_text() == want
        assert 'needs a hand-written opening' not in out
        assert order.main(['--check', str(p)]) == 0


@pytest.mark.parametrize('prefix', ['```markdown\n', '~~~markdown\n'])
def test_order_ignores_boxes_and_headings_in_code(prefix):
    order = importlib.import_module('fix_glance_order')
    text = prefix + '## Fake\n\n' + BOX + prefix[:3] + '\n\n## Real\n\nProse first.\n\n' + BOX
    assert order.fix_text(text) == text
    assert order.analyze(text)[:2] == ([], [])


def test_order_multiple_sections_and_local_note_without_box():
    order = importlib.import_module('fix_glance_order')
    a = '## A\n\nLocal symbols: $x$.\n\nFirst prose.\n\n'
    b = '## B\n\n' + BOX + 'Second prose.\n\n'
    want = '## A\n\nFirst prose.\n\nLocal symbols: $x$.\n\n## B\n\nSecond prose.\n\n' + BOX
    assert order.fix_text(a + b) == want
    assert order.fix_text(want) == want
