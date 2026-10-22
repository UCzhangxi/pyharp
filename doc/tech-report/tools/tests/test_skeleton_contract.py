"""The requested outline and bibliography remain complete without scientific claims."""
import json
import re
from pathlib import Path
import yaml
REPORT = Path(__file__).resolve().parents[2]


def test_all_requested_chapters_and_appendices_are_in_the_book():
    cfg = yaml.safe_load((REPORT / 'book/_quarto.yml').read_text())['book']
    chapters = cfg['chapters'][1:]
    assert [int(Path(c).name[:2]) for c in chapters] == list(range(1, 11))
    assert len(cfg['appendices']) == 6
    for name in chapters + cfg['appendices']:
        text = (REPORT / 'book' / name).read_text()
        assert text.startswith('# ') and '\npending\n' in text
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
