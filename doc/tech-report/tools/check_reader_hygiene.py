#!/usr/bin/env python3
"""N3 reader hygiene: source preflight and rendered HTML/PDF text.

python tools/check_reader_hygiene.py --book book
python tools/check_reader_hygiene.py --pdf book/_book/report.pdf
python tools/check_reader_hygiene.py --html book/_book

PDF reports occurrences and affected physical pages separately. Source references
are valid except in literal code; rendered text must contain no raw references.
"""
import argparse
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess

import yaml

PATTERNS = {
    'ISSUES.md': re.compile(r'\bISSUES(?:\.md)?\b'),
    'NOTATION.md': re.compile(r'\bNOTATION(?:\.md)?\b'),
    'STYLE.md': re.compile(r'\bSTYLE(?:\.md)?\b'),
    'flagged to the editor': re.compile(r'\b(?:flagged|flags?|flagging)\s+(?:it\s+)?to\s+the\s+editor\b', re.I),
    'editor tracking': re.compile(r'\b(?:the\s+editor\s+tracks|proposed\s+in\s+the\s+notation\s+issue)\b', re.I),
    'raw @sec-': re.compile(r'@sec-[\w-]*'),
}


def counts(text, rendered=True):
    if not rendered:
        text = re.sub(r'<!--.*?-->', '', text, flags=re.S)
    result = Counter({name: len(p.findall(text)) for name, p in PATTERNS.items()})
    if not rendered:
        # Quarto resolves references in prose, but not in fences or inline code.
        literal = []
        fence = None
        executable = False
        for line in text.splitlines():
            m = re.match(r'^\s*(`{3,}|~{3,})', line)
            if m:
                if fence is None:
                    fence = m.group(1)
                    executable = line[m.end():].lstrip().startswith("{")
                elif m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                    fence = None
                continue
            if fence:
                # echo:false execution cells are not displayed; captions are prose.
                if not executable:
                    literal.append(line)
            else:
                literal.extend(m.group(2) for m in re.finditer(r'(`+)(.*?)\1', line))
        result['raw @sec-'] = len(PATTERNS['raw @sec-'].findall('\n'.join(literal)))
    return result


def sources(book):
    cfg = yaml.safe_load((book / '_quarto.yml').read_text())
    found = set()

    def visit(path):
        path = path.resolve()
        if path in found:
            return
        found.add(path)
        for name in re.findall(r'\{\{<\s*include\s+([^ >]+)\s*>}}', path.read_text()):
            target = path.parent / name
            # Nested generated appendix includes are relative to the chapter root.
            if not target.exists():
                target = book / 'chapters' / name
            visit(target)

    def entries(items):
        for item in items:
            if isinstance(item, str):
                visit(book / item)
            elif isinstance(item, dict):
                if 'file' in item:
                    visit(book / item['file'])
                entries(item.get('chapters', []))
    entries(cfg['book'].get('chapters', []))
    entries(cfg['book'].get('appendices', []))
    return sorted(found)


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag in ('p', 'div', 'tr', 'li', 'br'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--book', type=Path)
    group.add_argument('--pdf', type=Path)
    group.add_argument('--html', type=Path)
    args = ap.parse_args(argv)
    if args.book:
        units = [(str(p), p.read_text()) for p in sources(args.book)]
    elif args.pdf:
        text = subprocess.run(['pdftotext', '-layout', str(args.pdf), '-'], check=True,
                              capture_output=True, text=True).stdout
        units = [(f'page {i}', p) for i, p in enumerate(text.split('\f'), 1) if p.strip()]
    else:
        files = [args.html] if args.html.is_file() else sorted(args.html.rglob('*.html'))
        if not files:
            ap.error('no HTML files found')
        units = []
        for p in files:
            parser = VisibleHTML()
            parser.feed(p.read_text())
            units.append((str(p), ''.join(parser.parts)))
    totals, affected = Counter(), Counter()
    for name, text in units:
        hits = counts(text, rendered=not bool(args.book))
        totals.update(hits)
        affected.update({k: int(v > 0) for k, v in hits.items()})
        if any(hits.values()):
            print(f'{name}: ' + ', '.join(f'{k}={v}' for k, v in hits.items() if v))
    for key in PATTERNS:
        print(f'{key}: {totals[key]} hits; {affected[key]} affected ' +
              ('pages' if args.pdf else 'files'))
    return int(any(totals.values()))


if __name__ == '__main__':
    raise SystemExit(main())
