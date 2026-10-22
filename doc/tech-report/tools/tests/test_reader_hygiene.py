"""N3 source guard, plus regression cases for literal and rendered markers."""
from pathlib import Path
import sys

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import check_reader_hygiene as hygiene


@pytest.mark.parametrize('marker', ['ISSUES.md', 'NOTATION.md', 'STYLE.md',
    'STYLE section 7', 'NOTATION §4', 'flagged to the editor', 'flags it to the editor',
    'the editor tracks it', 'proposed in the\nnotation issue', '@sec-ch07'])
def test_rendered_markers_fail(marker):
    assert sum(hygiene.counts(marker).values()) > 0


def test_source_references_resolve_but_literal_references_do_not():
    assert not any(hygiene.counts('See @sec-ch07. <!-- ISSUES.md -->', rendered=False).values())
    for text in ['`@sec-ch07`', '```yaml\nx: 1 # @sec-ch07\n```',
                 '~~~~yaml\nx: 1 # @sec-ch07\n~~~~']:
        assert hygiene.counts(text, rendered=False)['raw @sec-'] == 1


def test_execution_caption_is_resolved_prose():
    text = '```{python}\n#| fig-cap: "See @sec-ch07"\nmake_fig()\n```'
    assert hygiene.counts(text, rendered=False)["raw @sec-"] == 0


def test_html_visible_text_only():
    p = hygiene.VisibleHTML()
    p.feed('<script>"@sec-hidden"</script><!-- ISSUES.md --><p>NOTATION<span>.md</span></p>')
    assert hygiene.counts(''.join(p.parts))['NOTATION.md'] == 1
    assert hygiene.counts(''.join(p.parts))['raw @sec-'] == 0


def test_book_inputs_are_reader_prose():
    assert hygiene.main(['--book', str(TOOLS.parent / 'book')]) == 0
