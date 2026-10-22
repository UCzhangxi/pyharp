"""First-use glossary notes: registry validation, file-local senses and pinned sources."""
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gen_reader_reference as g

PIN = 'https://github.com/chengcli/pyharp/blob/f34506f9d14ee7b1f2e1222775baa5093ae6967f'
SOURCE = PIN + '/src/radiation/bbflux.cpp#L164-L166'


def report(tmp_path, entries, chapter='Prose names the GPU and the `order` key.\n'):
    (tmp_path / 'tools').mkdir()
    (tmp_path / 'book/chapters').mkdir(parents=True)
    (tmp_path / 'NOTATION.md').write_text((g.REPORT / 'NOTATION.md').read_text())
    (tmp_path / 'book/_quarto.yml').write_text(
        'book:\n  chapters:\n    - index.qmd\n    - chapters/01-a.qmd\n')
    (tmp_path / 'book/index.qmd').write_text('# Preface\n')
    (tmp_path / 'book/chapters/01-a.qmd').write_text('# A {#sec-ch01}\n\n' + chapter)
    (tmp_path / 'tools/reader-glossary.json').write_text(json.dumps({'version': 1, 'entries': entries}))
    return tmp_path


def test_committed_registry_is_valid():
    assert isinstance(g.glossary_entries(g.REPORT), list)
    assert g.check_glossary(g.REPORT) == 0


def test_empty_registry_attaches_nothing(tmp_path):
    root = report(tmp_path, [])
    outputs, uses, entries = g.glossary_outputs(root)
    assert (uses, entries) == (0, 0)


def test_first_use_note_and_local_sense(tmp_path):
    root = report(tmp_path, [
        dict(kind='acronym', term='GPU', meaning='graphics processing unit'),
        dict(kind='key', term='order', meaning='reaction order',
             meaning_by_file={'chapters/01-a.qmd': 'local sense of order'}, source=SOURCE)])
    outputs, uses, _ = g.glossary_outputs(root)
    text = outputs[root / 'book/chapters/01-a.qmd']
    assert uses == 2
    assert 'GPU — graphics processing unit' in text
    assert 'order — local sense of order; [source](' + SOURCE + ')' in text


@pytest.mark.parametrize('metadata', [
    {'source': 'https://github.com/chengcli/pyharp/blob/main/src/radiation/bbflux.cpp#L1'},
    {'source': SOURCE, 'notation_only': True},
    {'source': 'https://github.com/someone/pyharp/blob/' + '0' * 40 + '/src/a.cpp#L1'},
])
def test_glossary_source_refuses_ambiguous_provenance(tmp_path, metadata):
    root = report(tmp_path, [dict(kind='acronym', term='CPU', meaning='central processing unit', **metadata)])
    with pytest.raises(ValueError, match='invalid pinned glossary source'):
        g.glossary_entries(root)


def test_symbol_must_be_in_notation(tmp_path):
    root = report(tmp_path, [dict(kind='symbol', term='$q_{\\mathrm{none}}$', notation_group='1')])
    with pytest.raises(ValueError, match='absent from Appendix A'):
        g.glossary_entries(root)


@pytest.mark.parametrize('key', ['name', 'equation'])
def test_yaml_list_key_requires_definition(tmp_path, key):
    root = report(tmp_path, [], f'```yaml\n- {key}: example\n```\n')
    with pytest.raises(ValueError, match=f"YAML key '{key}'"):
        g.glossary_outputs(root)


@pytest.mark.parametrize('composition', ['{Ar: 1, H: 2, N: 1, O: 1}', '\n    Ar: 1\n    H: 2\n    N: 1\n    O: 1'])
def test_yaml_composition_labels_are_data_in_both_consumers(tmp_path, composition):
    import glossary_registry as registry
    keys = ['name', 'composition', 'rate-constant', 'A', 'b', 'Ea_R', 'O']
    entries = [dict(kind='key', term=k, meaning='configuration field') for k in keys]
    example = f'- name: test\n  composition: {composition}\n  rate-constant: {{A: 1, b: 0, Ea_R: 10}}\n'
    root = report(tmp_path, entries, f'```yaml\n{example}```\n')
    outputs, uses, _ = g.glossary_outputs(root)
    assert uses == 6
    assert example in outputs[root / 'book/chapters/01-a.qmd']
    _, found = registry.prose_uses(root)
    assert set(found) == {('key', key) for key in keys if key != 'O'}


@pytest.mark.parametrize('key', ['A', 'b', 'Ea_R', 'O'])
def test_yaml_flow_configuration_keys_still_require_definitions(tmp_path, key):
    root = report(tmp_path, [dict(kind='key', term='rate-constant', meaning='rate parameters')],
                  f'```yaml\nrate-constant: {{{key}: 1}}\n```\n')
    with pytest.raises(ValueError, match=f"YAML key '{key}'"):
        g.glossary_outputs(root)
