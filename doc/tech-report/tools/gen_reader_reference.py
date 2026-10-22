#!/usr/bin/env python3
"""Attach first-use glossary notes from tools/reader-glossary.json to the chapters.

Each chapter gets a footnote at the first prose use of a registered acronym, YAML key or
symbol, in include order. Symbol meanings are resolved against NOTATION.md (Appendix A).
A scaffold with an empty registry is valid: there is nothing to attach yet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REPORT = Path(__file__).resolve().parent.parent
# A glossary source is a blob link at a full 40-character sha (STYLE 10.6) in one of the
# allowed repositories, so a moving branch can never change what a definition points at.
_SOURCE = re.compile(r'https://github\.com/chengcli/(?:pyharp|snapy|pyharp|paddle)/blob/[0-9a-f]{40}/[^\s#]+#L\d+(?:-L\d+)?')

_GLOSS_NOTES = re.compile(r'\n<!-- reader glossary notes -->\n.*?<!-- end reader glossary notes -->\n?', re.S)
_GLOSS_KEYS = re.compile(r'^<!-- reader glossary keys -->.*\n', re.M)
_GLOSS_REF = re.compile(r'\[\^rg-[a-f0-9]{12}\]')


def yaml_keys(source):
    """Yield configuration fields, excluding the element-to-count composition map.

    Compose nodes instead of loading values so YAML's scalar coercion cannot
    change key spelling. Traversal handles block/flow maps and list items alike.
    """
    import yaml

    def walk(node, ancestors=frozenset()):
        if id(node) in ancestors:  # recursive aliases are not additional fields
            return
        ancestors = ancestors | {id(node)}
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                if isinstance(key, yaml.ScalarNode):
                    yield key.value
                    if key.value != 'composition':
                        yield from walk(value, ancestors)
        elif isinstance(node, yaml.SequenceNode):
            for value in node.value:
                yield from walk(value, ancestors)

    try:
        for document in yaml.compose_all(source):
            yield from walk(document)
    except yaml.YAMLError as exc:
        raise ValueError(f'invalid YAML example: {exc}') from exc


def glossary_entries(report):
    """One inventory; symbol meanings are resolved against Appendix A's source."""
    import gen_notation_index as notation
    data = json.loads((report / 'tools/reader-glossary.json').read_text())
    if data.get('version') != 1 or not isinstance(data.get('entries'), list):
        raise ValueError('glossary needs version 1 and an entries list')
    rows = {(s['num'], row['symbol']): row for s in notation.parse(
        (report / 'NOTATION.md').read_text())[1] for row in s['rows'] if 'symbol' in row}
    entries, seen = [], set()
    for item in data['entries']:
        if item.get('kind') == 'concept':  # named concepts: registry and glossary only, no first-use notes
            continue
        kind, term = item['kind'], item['term']
        if kind not in ('acronym', 'key', 'symbol') or not isinstance(term, str) or not term.strip():
            raise ValueError(f'invalid glossary entry: {item!r}')
        identity = (kind, term)
        if identity in seen:
            raise ValueError(f'duplicate glossary entry: {identity}')
        seen.add(identity)
        if kind == 'symbol':
            row = rows.get((item.get('notation_group'), term))
            if row is None:
                raise ValueError(f'glossary symbol is absent from Appendix A: {term}')
            meaning = notation._refs(row['meaning'])
            key = notation.symbol_key(term)
        else:
            meaning, key = item.get('meaning', ''), term
        if not isinstance(meaning, str) or not meaning.strip():
            raise ValueError(f'glossary has no definition for {kind} {term}')
        # Inline code can name a C++ local or an output field, not only a YAML key.
        # Explicit file-local senses keep first-use annotations tied to their context.
        local = item.get('meaning_by_file', {})
        if not isinstance(local, dict) or any(
                not isinstance(value, str) or not value.strip()
                or not (report / 'book' / path).is_file()
                for path, value in local.items()):
            raise ValueError(f'invalid local glossary meanings for {term}')
        source = item.get('source')
        notation_only = item.get('notation_only', False)
        if source is not None and (notation_only or not isinstance(source, str) or not _SOURCE.fullmatch(source)):
            raise ValueError(f'invalid pinned glossary source for {term}')
        if not isinstance(notation_only, bool):
            raise ValueError(f'invalid notation-only marker for {term}')
        suffix = ('; [source](' + source + ')') if source else (
            '; notation only; see @sec-appa' if notation_only else '')
        meaning += suffix
        local = {path: value + suffix for path, value in local.items()}
        entries.append(dict(kind=kind, term=term, key=key, meaning=meaning,
                            meaning_by_file=local))
    return entries


def glossary_outputs(report):
    """Attach a footnote at the first prose use in each chapter, in include order.

    Code, headings, attributes and provenance comments are not prose uses. YAML
    keys are recognised when named in inline code; executable examples stay intact.
    """
    import gen_notation_index as notation
    import gen_topic_index as topics
    entries = glossary_entries(report)
    lookup = {(e['kind'], e['key']): e for e in entries if e['key']}
    token = re.compile(r'\{\{<.*?>\}\}|`[^`\n]+`|(?<!\$)\$[^$\n]+\$(?!\$)|\b[A-Z][A-Z0-9]{1,6}\b')
    seen, outputs, uses = {}, {}, 0
    for path in topics.book_order(report / 'book'):
        rel = path.relative_to(report / 'book').as_posix()
        m = re.match(r'chapters/(\d\d)-', rel)
        if not m:
            continue
        chapter = m[1]
        used = seen.setdefault(chapter, set())
        text = _GLOSS_REF.sub('', _GLOSS_KEYS.sub('', _GLOSS_NOTES.sub('', path.read_text())))
        notes = []
        fence = comment = display = generated = False
        lines = []

        def replace(match):
            nonlocal uses
            word = match[0]
            if word.startswith('{{<'):
                return word
            if word.startswith('`'):
                identity = ('key', word[1:-1])
            elif word.startswith('$'):
                identity = ('symbol', notation._norm(word[1:-1]))
            else:
                identity = ('acronym', word)
            entry = lookup.get(identity)
            if entry is None or identity in used:
                return word
            used.add(identity)
            ident = hashlib.sha256((chapter + ':' + repr(identity)).encode()).hexdigest()[:12]
            note = f'rg-{ident}'
            notes.append(f'[^' + note + ']: ' + entry['term'] + ' — ' + entry['meaning_by_file'].get(rel, entry['meaning']))
            uses += 1
            return word + '[^' + note + ']'

        input_lines = text.splitlines(keepends=True)
        for line_index, line in enumerate(input_lines):
            stripped = line.lstrip()
            if '<!-- generated reader-reference:' in line:
                generated = True
            if generated:
                lines.append(line)
                if '<!-- end reader-reference:' in line:
                    generated = False
                continue
            if '<!--' in line:
                comment = True
            if comment:
                lines.append(line)
                if '-->' in line:
                    comment = False
                continue
            if stripped.startswith('```'):
                if not fence and stripped.strip() in ('```yaml', '```yml'):
                    keys = []
                    fragment = []
                    for future in input_lines[line_index + 1:]:
                        if future.lstrip().startswith('```'):
                            break
                        fragment.append(future)
                    for key in yaml_keys(''.join(fragment)):
                        identity = ('key', key)
                        if identity not in lookup:
                            raise ValueError(f'{rel}: YAML key {key!r} has no glossary definition')
                        if identity not in used:
                            keys.append(token.sub(replace, '`' + key + '`'))
                    if keys:
                        lines.append('<!-- reader glossary keys -->Keys in this fragment: ' + ', '.join(keys) + '.\n')
                fence = not fence
                lines.append(line)
                continue
            if not fence and stripped.startswith('$$'):
                if line.count('$$') % 2:
                    display = not display
                lines.append(line)
                continue
            if fence or display or stripped.startswith('#'):
                lines.append(line)
            else:
                lines.append(token.sub(replace, line))
        output = ''.join(lines).rstrip() + '\n'
        if notes:
            output += '\n<!-- reader glossary notes -->\n' + '\n\n'.join(notes) + '\n<!-- end reader glossary notes -->\n'
        outputs[path] = output
    return outputs, uses, len(entries)


def check_glossary(report, check=True):
    try:
        outputs, uses, entries = glossary_outputs(report)
        bad = 0
        for path, expected in outputs.items():
            if path.read_text() != expected:
                if check:
                    print(f'{path.relative_to(report)}: first-use glossary notes are stale')
                    bad += 1
                else:
                    path.write_text(expected)
        print(f'N4 glossary: {bad} problem(s); {entries} entries; {uses} chapter-first prose uses')
        return bad
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'N4 glossary: invalid input: {exc}')
        return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report', type=Path, default=REPORT)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args(argv)
    return int(bool(check_glossary(args.report.resolve(), args.check)))


if __name__ == '__main__':
    raise SystemExit(main())
