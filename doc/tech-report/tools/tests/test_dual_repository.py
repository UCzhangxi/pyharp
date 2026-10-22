"""Both report pins resolve symbols; wrong repository, symbol, and pins fail."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import code_anchors as anchors
import check_citations as citations
import ratchet_gate as ratchet

@pytest.mark.parametrize('repository,path,symbol', [
    ('pyharp', 'src/radiation/radiation_band.cpp', 'RadiationBandImpl::forward'),
    ('pydisort', 'src/disort.cpp', 'DisortImpl::forward'),
])
def test_real_pinned_symbols_resolve(repository, path, symbol):
    repo, sha = anchors.read_pins()[repository]
    snapshot = anchors.Snapshot.of(repo, sha)
    cite = anchors.parse_args(f'{path} {symbol} repo={repository}')
    lo, hi = snapshot.resolve(cite)
    assert hi >= lo > 0
    assert symbol in '\n'.join(snapshot.lines(path, lo, hi))
    with pytest.raises(anchors.Unresolved, match='no symbol'):
        snapshot.resolve(anchors.Cite(path, 'MissingSymbol', None, repository))


def test_repository_is_part_of_shortcode_identity():
    a = anchors.parse_args('src/disort.cpp repo=pyharp')
    b = anchors.parse_args('src/disort.cpp repo=pydisort')
    assert a.key != b.key
    with pytest.raises(anchors.Unresolved, match='unknown repository'):
        anchors.parse_args('src/disort.cpp repo=unknown')
    snap = anchors.Snapshot.of(*anchors.read_pins()['pyharp'])
    with pytest.raises(anchors.Unresolved, match='no file'):
        snap.resolve(a)


def test_real_dual_table_urls_and_failure(tmp_path, monkeypatch):
    page = tmp_path / 'citations.qmd'
    page.write_text('{{< code src/radiation/radiation_band.cpp RadiationBandImpl::forward >}}\n'
                    '{{< code src/disort.cpp DisortImpl::forward repo=pydisort >}}\n')
    table = tmp_path / 'table.json'
    monkeypatch.setattr(anchors, 'TABLE', table)
    args = SimpleNamespace(paths=[page], no_write=False)
    assert anchors.cmd_check(args) == 0
    rows = json.loads(table.read_text())['citations']
    for alias, (repo, sha) in anchors.read_pins().items():
        row = next(v for k, v in rows.items() if k.startswith(alias + '|'))
        assert f'https://github.com/{repo}/blob/{sha}/' in row['url']
        assert '#L' in row['url']
    page.write_text(page.read_text() + '{{< code missing.cpp repo=pydisort >}}\n')
    assert anchors.cmd_check(args) == 1


def test_pydisort_is_checked_by_the_ratchet():
    pins = ratchet.pins(ratchet.ROOT)
    assert pins['pydisort'] == anchors.read_pins()['pydisort'][1]
    assert not ratchet.offpin_hits('pydisort@' + pins['pydisort'], pins)
    assert ratchet.offpin_hits('pydisort@' + '1' * 40, pins)


def test_both_repository_notations_are_recognized(tmp_path):
    page = tmp_path / 'planning.md'
    pins = anchors.read_pins()
    page.write_text('\n'.join(f'{alias}:src/missing.cpp:1@{sha}' for alias, (_, sha) in pins.items()))
    found = citations.find_citations(page)
    assert {c.repo for c in found} == {repo for repo, _ in pins.values()}
    resolver = citations.Resolver([anchors.find_commit(repo, sha) for repo, sha in pins.values()], tmp_path / 'cache', True)
    assert all(any('does not exist' in p for p in citations.check(c, resolver)) for c in found)
