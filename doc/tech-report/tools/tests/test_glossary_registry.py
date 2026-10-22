"""The concept registry (N1/N4): defining sections, the "not defined here" mark and its ratchet, the glossary
appendix, the topic-index line of every concept and the rendered-book gate. Each gate fails on a deliberately
broken input and passes on a small synthetic report (built in a temporary directory) and on the real book.

Run from the report directory: `python3 -m pytest tools/tests`.
"""
import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
REPORT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import check_rendered_glossary as rendered  # noqa: E402
import gen_glossary_appendix as appendix  # noqa: E402
import gen_topic_index as topics  # noqa: E402
import glossary_registry as registry  # noqa: E402

FIX = Path(__file__).resolve().parent / 'fixtures' / 'rendered-glossary'

# --- a synthetic report: one chapter, Appendix A and the two generated appendices -------------------------------
# The chapter defines CPU in its prose, MPI only in its introduction, the key `cfl` in a key table and the named
# concept "Riemann solver" and the reader term "output file" in prose; GPU is used but defined only in a generated
# first-use note, so it is marked "not defined here". SI is defined in a file Appendix A includes at the end of its
# last section (an included file is read after the whole file that includes it); $x$ is a row of NOTATION.md group 1.

SYNTH = {
    'NOTATION.md': """# Notation

## 1. Coordinates and grids

| symbol | meaning | code | source letter |
|---|---|---|---|
| $x$ | horizontal coordinate [m] | | |

## 2. State

| symbol | meaning | code | source letter |
|---|---|---|---|
""",
    'book/_quarto.yml': """project:
  type: book
book:
  chapters:
    - chapters/01-overview.qmd
    - chapters/appendices/appa-notation.qmd
    - chapters/appendices/appf-topic-index.qmd
    - chapters/appendices/apph-glossary.qmd
""",
    'book/chapters/01-overview.qmd': """# Overview {#sec-ch01}

The message passing interface (MPI) spreads one run over many ranks.

## The driver loop {#sec-ch01-driver}

The central processing unit (CPU) runs the driver loop.

A Riemann solver is a function of the two face states. The loop calls the Riemann solver on every face, and the
Riemann solver returns one flux per face.

| key | default | meaning |
|---|---|---|
| `integration/cfl` | 0.9 | the Courant number |

## The output {#sec-ch01-output}

An output file is a record of the state at one time. The CPU writes each output file after the step, whose length
is scaled by `cfl`. The output is gathered over MPI and may be copied from the GPU.

<!-- reader glossary notes -->
[^rg-0123456789ab]: GPU, graphics processing unit.
<!-- end reader glossary notes -->

## Parallel runs with MPI {#sec-ch01-mpi}

Each MPI rank owns one part of the grid.

## Notes

The CPU is idle between steps.
""",
    'book/chapters/appendices/appa-notation.qmd': """# Notation {#sec-appa}

## 1. Coordinates and grids {#sec-appa-1 .unnumbered}

| symbol | meaning |
|---|---|
| $x$ | horizontal coordinate [m] |

## 2. State {#sec-appa-2 .unnumbered}

No symbol yet.

## Notation index {#sec-appa-index}

{{< include _appa-preamble.qmd >}}
""",
    'book/chapters/appendices/_appa-preamble.qmd': 'Units are SI, the International System of Units.\n',
    'book/chapters/appendices/appf-topic-index.qmd': '# Topic index {#sec-appf}\n\n'
                                                     '{{< include _appf-topic-index.qmd >}}\n',
    'book/chapters/appendices/apph-glossary.qmd': '# Glossary {#sec-apph}\n\n{{< include _apph-glossary.qmd >}}\n',
    'tools/topic-index.yaml': """sections:
  sec-ch01-driver:
    - driver loop
  sec-ch01-output:
    - output
  sec-ch01-mpi:
    - parallel runs: [MPI]
  sec-appa-index:
    - notation index
  sec-appa-1:
    - symbols, coordinates and grids
  sec-appa-2:
    - symbols, state
unlabeled:
  - file: chapters/01-overview.qmd
    heading: Notes
    covered-by: sec-ch01
""",
    'tools/not-defined-here-baseline.json': '{"not_defined_here": 1}\n',
}
ENTRIES = [
    {'kind': 'acronym', 'term': 'CPU', 'meaning': 'central processing unit', 'section': 'sec-ch01-driver',
     'not_defined_here': False},
    {'kind': 'acronym', 'term': 'GPU', 'meaning': 'graphics processing unit', 'section': 'sec-ch01-output',
     'not_defined_here': True},
    {'kind': 'acronym', 'term': 'MPI', 'meaning': 'message passing interface', 'section': 'sec-ch01-mpi',
     'not_defined_here': False},
    {'kind': 'acronym', 'term': 'SI', 'meaning': 'International System of Units', 'section': 'sec-appa-index',
     'not_defined_here': False},
    {'kind': 'key', 'term': 'cfl', 'meaning': 'Courant number', 'section': 'sec-ch01-driver',
     'not_defined_here': False},
    {'kind': 'symbol', 'term': '$x$', 'notation_group': '1', 'section': 'sec-appa-1'},
    {'kind': 'concept', 'term': 'Riemann solver', 'section': 'sec-ch01-driver', 'not_defined_here': False},
    {'kind': 'concept', 'term': 'output file', 'section': 'sec-ch01-output', 'not_defined_here': False},
]
NAMED = ['Riemann solver']  # found by `concept_candidates`
READER_TERMS = {'output file': 'sec-ch01-output'}  # added by hand, defined where it routes
INTRO_DEFINED = {'MPI': 'sec-ch01-mpi'}  # defined only in its chapter's introduction: the section titled by it


def build(root):
    """Write the synthetic report under `root` and generate its glossary appendix and topic index."""
    root = Path(root).resolve()
    for rel, text in SYNTH.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding='utf-8')
    (root / registry.REGISTRY).write_text(json.dumps({'version': 1, 'entries': ENTRIES}, indent=2) + '\n',
                                          encoding='utf-8')
    (root / appendix.FRAGMENT.relative_to(REPORT)).write_text(appendix.render(root), encoding='utf-8')
    assert topics.main(['--data', str(root / 'tools/topic-index.yaml'), '--book', str(root / 'book')]) == 0
    return root


@pytest.fixture(scope='module')
def root(tmp_path_factory):
    return build(tmp_path_factory.mktemp('report'))


@pytest.fixture(scope='module')
def data(root):
    return json.loads((root / registry.REGISTRY).read_text(encoding='utf-8'))


def _broken(data, term, **change):
    broken = copy.deepcopy(data)
    item = next(e for e in broken['entries'] if e['term'] == term)
    for key, value in change.items():
        if value is None:
            item.pop(key, None)
        else:
            item[key] = value
    return broken


# --- the registry: every concept has a defining section, or is marked "not defined here" -------------------------

def test_every_concept_has_a_defining_section(root, data):
    assert registry.registry_problems(root, data) == []
    assert all(e.get('section') for e in data['entries'])
    assert len(data['entries']) == len(ENTRIES)


def test_the_real_registry_is_valid():
    real = json.loads((REPORT / registry.REGISTRY).read_text(encoding='utf-8'))
    assert registry.registry_problems(REPORT, real) == []
    assert all(e.get('section') for e in real['entries'])


@pytest.mark.parametrize('term,change,message', [
    ('CPU', {'section': None}, 'acronym CPU: no defining section'),
    ('CPU', {'section': 'sec-ch01-nowhere'}, 'acronym CPU: defining section sec-ch01-nowhere is not a label'),
    ('$x$', {'section': 'sec-appa-2'}, 'defined by Appendix A group 1, not sec-appa-2'),
    ('GPU', {'section': 'sec-ch01-driver'}, 'acronym GPU: not defined here, and section '
                                            'sec-ch01-driver does not use it in prose'),
    ('cfl', {'section': 'sec-ch01-output'}, 'key cfl: section sec-ch01-output does not define it'),
    ('GPU', {'not_defined_here': False}, 'acronym GPU: section sec-ch01-output does not define it'),
    ('CPU', {'not_defined_here': 'yes'}, 'acronym CPU: not_defined_here must be true or false'),
])
def test_a_broken_defining_section_fails(root, data, term, change, message):
    problems = registry.registry_problems(root, _broken(data, term, **change))
    assert any(message in p for p in problems), problems


@pytest.mark.parametrize('kind,term,meaning,paragraph,expected', [
    ('acronym', 'EOS', 'equation of state', 'The equation of state (EOS) converts the state.', True),
    ('acronym', 'WENO', 'weighted essentially non-oscillatory',
     'Acronyms: WENO, weighted essentially non-oscillatory; TVD, total-variation diminishing.', True),
    ('acronym', 'CPU', 'central processing unit', 'The run used one CPU and took 3 s.', False),
    ('key', 'cfl', 'Courant number', '| `integration/cfl` | 0.9 | the Courant number |', True),
    ('key', 'nb2', 'blocks', '| `distribute/layout`, `nb1`, `nb2`, `nb3` | `slab`, 1, 1, 1 | decomposition |', True),
    ('key', 'cfl', 'Courant number', '| block: reduce, `cfl`, redo | `max_time_step` |', False),
    ('key', 'cfl', 'Courant number', 'The step is multiplied by `cfl`, and halved for each redo.', False),
    ('acronym', 'MC', 'monotonised-central limiter', 'TVD, total-variation diminishing; MC, the monotonised-central limiter.',
     True),
    ('key', 'limiter', 'positivity limiter', registry.KEY_TABLE + '| EOS `limiter` | false | positivity correction |', True),
    ('key', 'disable-flux-x3', 'switch', registry.KEY_TABLE + '| `dynamics/disable-flux-x1`, `-x2`, `-x3` | false | gates |',
     True),
    ('key', 'cfl', 'Courant number', '| block: reduce, `cfl`, redo | `max_time_step` |', False),
    ('key', 'nu_iso', 'viscosity', 'With the default `dynamic: false`, `nu_iso` is a kinematic viscosity.', True),
    ('key', 'bot-heat', 'flux', '`body-heat` is a volumetric rate; `top-cool` and `bot-heat` stand for a surface flux.', True),
    ('key', 'gammad', 'ratio', 'the last term; `gammad` is $\\gamma_d$ from the card.', True),
    ('key', 'nx1', 'cells', 'The anchor `nx1` is in the hydro reset.', False),
    ('key', 'uv-solver', 'solver', '**Activation.** `uv-solver` is `auto` (default), `kkt` or `partition`.', False),
    ('concept', 'Riemann solver', '', 'A Riemann solver is a function of the two face states.', True),
    # a named concept that is also a class name is defined in code font (section 1.2)
    ('concept', 'MeshBlock', '', 'A `MeshBlock` is the unit that owns a grid patch and every module that acts on it.',
     True),
    ('concept', 'MeshBlock', '', 'Each `MeshBlock` holds its own stage buffers.', False),
    ('concept', 'MeshBlock', '', 'A `MeshBlockOptions` is a tree of options.', False),
])
def test_the_definition_rule(kind, term, meaning, paragraph, expected):
    assert registry.defines(dict(kind=kind, term=term, meaning=meaning), paragraph) is expected


def test_a_generated_first_use_note_is_not_a_definition(root):
    """GPU's meaning appears in the chapter only in a generated first-use note, so the book does not define it."""
    order, paras = registry.paragraphs(root)
    gpu = dict(kind='acronym', term='GPU', meaning='graphics processing unit')
    assert not any(registry.defines(gpu, p) for s in order for p in paras.get(s, []))
    assert 'graphics processing unit' in (root / 'book/chapters/01-overview.qmd').read_text()
    assert registry.defines(gpu, 'GPU, graphics processing unit.')  # the note itself would count, were it prose


def test_definitions_the_book_gives_are_not_marked(root, data):
    """Seeding from the book finds every definition (in a labelled section, in a chapter introduction, in a key
    table, in an included file, in prose) and marks only the entry the book defines nowhere."""
    _, seeded = registry.seed(root)
    got = {(i['kind'], i['term']): (section, mark) for i, section, mark, _ in seeded if i['kind'] != 'symbol'}
    want = {(e['kind'], e['term']): (e['section'], e[registry.MARK]) for e in data['entries'] if e['kind'] != 'symbol'}
    assert got == want
    assert {t for (_, t), (_, mark) in got.items() if mark} == {'GPU'}


def test_the_mark_follows_the_book(root, data):
    """No entry is marked while the book defines it, and the acronyms and keys marked are at most the baseline."""
    marked = [e for e in data['entries'] if e.get(registry.MARK) and e['kind'] in ('acronym', 'key')]
    assert len(marked) <= json.loads((root / registry.BASELINE).read_text())[registry.MARK]
    assert not [e['term'] for e in data['entries'] if e.get('notation_only') and e.get(registry.MARK)]
    fragment = root / appendix.FRAGMENT.relative_to(REPORT)
    assert 'notation only; see @sec-appa. Not defined here' not in fragment.read_text(encoding='utf-8')


def test_no_defining_section_is_a_roll_up(root, data):
    book_labels = registry.labels(root / 'book')
    assert [e['term'] for e in data['entries'] if registry.rollup(e['section'], book_labels)] == []
    assert {e['term']: e['section'] for e in data['entries'] if e['term'] in INTRO_DEFINED} == INTRO_DEFINED


def test_a_roll_up_section_fails_the_registry(root, data):
    problems = registry.registry_problems(root, _broken(data, 'MPI', section='sec-ch01'))
    assert 'acronym MPI: section sec-ch01 is a chapter or appendix heading, not a section of its own' in problems


def test_named_concepts_are_in_the_registry(root, data):
    concepts = sorted(e['term'] for e in data['entries'] if e['kind'] == 'concept' and e['term'] not in READER_TERMS)
    assert concepts == registry.concept_candidates(root) == NAMED
    assert all(e.get('section') and isinstance(e.get(registry.MARK), bool) for e in data['entries']
               if e['kind'] == 'concept')
    fragment = root / appendix.FRAGMENT.relative_to(REPORT)
    assert '## Named concepts {.unnumbered .unlisted}' in fragment.read_text(encoding='utf-8')


def test_reader_terms_are_defined_where_they_route(root, data):
    """Each reader term is in the registry, unmarked, with the section that defines it."""
    have = {e['term']: e for e in data['entries'] if e['kind'] == 'concept'}
    assert {t: have[t]['section'] for t in READER_TERMS if t in have} == READER_TERMS
    assert not any(have[t][registry.MARK] for t in READER_TERMS)
    defs = registry.definitions(root, data)
    assert all(READER_TERMS[t] in defs[('concept', t)] for t in READER_TERMS)
    routes = {(e['kind'], e['term']): (e['section'], e.get(registry.MARK)) for e in data['entries']}
    assert routes[('acronym', 'MPI')] == ('sec-ch01-mpi', False)
    assert routes[('key', 'cfl')] == ('sec-ch01-driver', False)


def test_a_use_under_an_unlabelled_section_has_no_section(root, data):
    """A use under a `##` heading with no label belongs to no section, so no concept's defining section is a label
    that merely covers it."""
    _, uses = registry.prose_uses(root)
    assert ('ch01', None) in uses[('acronym', 'CPU')]
    assert all(e['section'] for e in data['entries'])


# --- the "not defined here" ratchet ------------------------------------------------------------------------------

def test_the_baseline_is_the_count_of_marked_entries(root, data):
    base = json.loads((root / registry.BASELINE).read_text())
    assert base == {'not_defined_here': registry.marked(data)} == {'not_defined_here': 1}
    assert registry.ratchet_problems(root) == []


def test_the_real_baseline_is_the_count_of_marked_entries():
    real = json.loads((REPORT / registry.REGISTRY).read_text(encoding='utf-8'))
    assert json.loads((REPORT / registry.BASELINE).read_text()) == {'not_defined_here': registry.marked(real)}
    assert registry.ratchet_problems(REPORT) == []


def test_a_new_not_defined_here_entry_fails(root, data):
    problems = registry.ratchet_problems(root, _broken(data, 'CPU', not_defined_here=True))
    n = registry.marked(data)
    assert problems == [f'{n + 1} entries marked "not defined here", baseline {n}: define the new concepts instead']


def test_an_unrecorded_fall_fails(root, data):
    problems = registry.ratchet_problems(root, _broken(data, 'GPU', not_defined_here=False))
    assert len(problems) == 1 and 'record the verified fall' in problems[0]


def test_a_missing_baseline_fails(tmp_path):
    assert registry.ratchet_problems(REPORT, baseline=tmp_path / 'none.json')[0].endswith('--update')


# --- the glossary appendix: generated from the registry, every link resolves ------------------------------------

def test_the_committed_glossary_appendix_is_fresh_and_its_links_resolve(root):
    assert appendix.problems(REPORT) == []
    assert appendix.problems(root) == []


def test_the_glossary_says_not_defined_here(root, data):
    text = (root / appendix.FRAGMENT.relative_to(REPORT)).read_text(encoding='utf-8')
    assert text.lower().count('not defined here') == registry.marked(data)
    assert '- **CPU**: central processing unit. Defined in [The driver loop](#sec-ch01-driver).' in text
    assert '- **GPU**: graphics processing unit. Not defined here; used in [The output](#sec-ch01-output).' in text


def test_a_glossary_link_that_does_not_resolve_fails(root, data):
    problems = appendix.problems(root, _broken(data, 'CPU', section='sec-ch01-nowhere'))
    assert problems == ["acronym CPU: link target 'sec-ch01-nowhere' is not a section of the book"]


def test_a_stale_glossary_appendix_fails(tmp_path):
    report = build(tmp_path)
    fragment = report / appendix.FRAGMENT.relative_to(REPORT)
    assert appendix.problems(report) == []
    fragment.write_text(fragment.read_text(encoding='utf-8').replace('Defined in', 'Defined at', 1))
    assert appendix.problems(report) == [f'{fragment.name} is stale; run python3 tools/gen_glossary_appendix.py']


# --- the topic index: one line per concept, to its own defining section -----------------------------------------

@pytest.mark.parametrize('which', ['synthetic', 'real'])
def test_every_concept_has_its_own_topic_index_line(root, which):
    """Source preflight of the rendered check: Appendix F has a line per concept, to its defining section."""
    report = root if which == 'synthetic' else REPORT
    entries = json.loads((report / registry.REGISTRY).read_text(encoding='utf-8'))['entries']
    lines = rendered.index_lines(report / 'book/chapters/appendices/_appf-topic-index.qmd')
    for e in entries:
        line = lines[f'`{e["term"]}`' if e['kind'] == 'key' else e['term']]
        assert f'@{e["section"]}' in line or f'(#{e["section"]})' in line, line


def test_a_concept_that_is_also_an_alias_keeps_its_pointer(root):
    lines = rendered.index_lines(root / 'book/chapters/appendices/_appf-topic-index.qmd')
    assert lines['MPI'].endswith('See also **parallel runs**.')


# --- the rendered book: every section resolves in the .aux, every concept is reachable ---------------------------

def _rendered(tmp_path, aux=None, toc=None, index=None):
    root = tmp_path / 'report'
    shutil.copytree(FIX, root)
    for name, text in (('book/index.aux', aux), ('book/index.toc', toc), ('book/_appf.qmd', index)):
        if text is not None:
            (root / name).write_text(text)
    return rendered.problems(root / 'book', root, root / 'tools/reader-glossary.json', root / 'book/_apph.qmd',
                             root / 'book/_appf.qmd')


def test_the_rendered_fixture_passes(tmp_path):
    problems, stats = _rendered(tmp_path)
    assert problems == []
    assert stats == dict(concepts=3, via_toc=2, via_topic_index=1, index_entries=3, roll_ups=0, appendix_links=3,
                         unresolved=0)


def test_a_section_missing_from_the_aux_fails(tmp_path):
    aux = (FIX / 'book/index.aux').read_text().replace('\\newlabel{sec-ch01-driver}', '\\newlabel{sec-ch01-x}')
    problems, stats = _rendered(tmp_path, aux=aux)
    assert 'acronym CPU: defining section sec-ch01-driver does not resolve in index.aux' in problems
    assert 'glossary appendix link #sec-ch01-driver does not resolve in index.aux' in problems
    assert stats['unresolved'] == 2


def test_a_concept_without_its_own_index_line_is_unreachable(tmp_path):
    index = (FIX / 'book/_appf.qmd').read_text().replace('**`type`**: Conservation laws, @sec-ch02-laws.\n', '')
    problems, _ = _rendered(tmp_path, index=index)
    assert problems == ['key type: no topic-index line of its own refers to its defining section sec-ch02-laws',
                        'key type: defining section sec-ch02-laws is neither in the table of contents nor in the '
                        'topic index']


def test_an_index_line_to_a_roll_up_fails(tmp_path):
    index = (FIX / 'book/_appf.qmd').read_text().replace('**CPU**: Driver loop, @sec-ch01-driver.',
                                                          '**CPU**: Overview, @sec-ch01.')
    problems, stats = _rendered(tmp_path, index=index)
    assert problems == ['acronym CPU: no topic-index line of its own refers to its defining section sec-ch01-driver']
    assert stats['index_entries'] == 2


def test_a_rendered_roll_up_fails_even_when_registry_and_index_agree(tmp_path):
    registry_text = (FIX / 'tools/reader-glossary.json').read_text().replace('"section": "sec-ch01-driver"',
                                                                            '"section": "sec-ch01"')
    index = (FIX / 'book/_appf.qmd').read_text().replace('**CPU**: Driver loop, @sec-ch01-driver.',
                                                          '**CPU**: Overview, @sec-ch01.')
    root = tmp_path / 'report'
    shutil.copytree(FIX, root)
    (root / 'tools/reader-glossary.json').write_text(registry_text)
    (root / 'book/_appf.qmd').write_text(index)
    problems, stats = rendered.problems(root / 'book', root, root / 'tools/reader-glossary.json',
                                        root / 'book/_apph.qmd', root / 'book/_appf.qmd')
    assert problems == ['acronym CPU: defining section sec-ch01 is a chapter or appendix heading (chapter.1), a roll-up']
    assert stats['roll_ups'] == 1 and stats['index_entries'] == 3


def test_the_rendered_gate_needs_a_render(tmp_path):
    (tmp_path / 'book').mkdir()
    problems, _ = rendered.problems(tmp_path / 'book', tmp_path)
    assert problems and 'not found' in problems[0]


@pytest.mark.skipif(not (REPORT / 'book/index.aux').exists(), reason='needs a local PDF render of the book')
def test_the_real_render_passes():
    problems, stats = rendered.problems(REPORT / 'book')
    assert problems == [] and stats['unresolved'] == 0 and stats['index_entries'] == stats['concepts']
