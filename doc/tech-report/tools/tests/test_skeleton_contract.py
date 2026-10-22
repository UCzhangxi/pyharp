"""The requested outline and bibliography remain complete without scientific claims."""
import json
import re
from pathlib import Path
import yaml
REPORT = Path(__file__).resolve().parents[2]


def is_stub(text):
    """A file with nothing but its heading, `pending` and includes; a chapter with content has a line of its own."""
    body = text.splitlines()[1:]
    return all(not l.strip() or l.strip() == 'pending' or re.fullmatch(r'\{\{< include \S+ >\}\}', l.strip())
               for l in body)


def chapter_contract_holds(text):
    """A chapter or appendix file opens with its `#` heading and, while it is a stub, says `pending`."""
    return text.startswith('# ') and ('\npending\n' in text or not is_stub(text))


STUB = '# Overview {#sec-ch01}\n\npending\n'
STUB_WITH_INCLUDE = '# Notation {#sec-appa}\n\npending\n\n{{< include appendices/_appa-notation.qmd >}}\n'
STUB_NOT_PENDING = '# Overview {#sec-ch01}\n\n{{< include 01-overview/_x.qmd >}}\n'
CONTENT = '# DISORT {#sec-ch03}\n\nA band whose YAML says `solver: disort` is solved by DISORT.\n\n' \
          '{{< include 03-disort/_band.qmd >}}\n'


def test_a_stub_chapter_still_has_to_say_pending():
    assert chapter_contract_holds(STUB)
    assert chapter_contract_holds(STUB_WITH_INCLUDE)
    assert not chapter_contract_holds(STUB_NOT_PENDING)
    assert not chapter_contract_holds('pending\n')                    # no heading


def test_a_chapter_with_content_need_not_say_pending():
    assert chapter_contract_holds(CONTENT)


def test_all_requested_chapters_and_appendices_are_in_the_book():
    cfg = yaml.safe_load((REPORT / 'book/_quarto.yml').read_text())['book']
    chapters = cfg['chapters'][1:]
    assert [int(Path(c).name[:2]) for c in chapters] == list(range(1, 11))
    assert len(cfg['appendices']) == 6
    for name in chapters + cfg['appendices']:
        text = (REPORT / 'book' / name).read_text()
        assert chapter_contract_holds(text), name
    assert '| owner |' not in (REPORT / 'OUTLINE.md').read_text()


def test_all_reading_dois_and_crossref_corrections_are_present():
    data = json.loads((REPORT / 'tools/crossref-metadata.json').read_text())
    assert [r['number'] for r in data] == list(range(1, 34))
    assert len({r['message']['DOI'].lower() for r in data}) == 33
    bib = (REPORT / 'book/references.bib').read_text()
    assert len(re.findall(r'^@\w+\{reading\d\d,', bib, re.M)) == 33
    for rec in data:
        assert rec['message']['DOI'] in bib
    works = {r['number']: r['message'] for r in data}
    def year(n):
        d = works[n]
        return next(d[k]['date-parts'][0][0] for k in ('published-print', 'published-online', 'issued') if k in d)
    assert (year(13), year(16), year(30), year(33)) == (2023, 2017, 2021, 2018)
    assert [a['family'] for a in works[15]['author']] == ['Heng', 'Mendonça', 'Lee']
    assert [a['family'] for a in works[16]['author']] == ['Heng', 'Kitzmann']
    assert [a['family'] for a in works[33]['author']] == ['Heng', 'Malik', 'Kitzmann']
