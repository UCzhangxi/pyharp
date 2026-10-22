#!/usr/bin/env python3
"""Move opening prose before glance boxes/local-symbols notes, without reflow.

Usage: fix_glance_order.py [--check] [FILE.qmd ...] (default: the whole book).
Sections end at the next non-template heading. The report's Summary, Derivation,
Numerical method, Code, Tests and Limits subheadings belong to their section.
Only ordinary, top-level Markdown paragraphs count as prose. Code, math,
comments, YAML, divs, tables, lists, images and Quarto shortcodes do not.
A paragraph is moved only when nothing but blank lines separates it from the
closing fence of a box/note; if a table, heading or other block sits between,
the file is left alone and the section is reported as needing a hand-written
opening (a gate failure). Over-length reports count physical content lines,
including blanks, excluding opening/closing fences. Missing prose and length are
advisory, not failures.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass

from fix_glance_boxes import CODE, DIV, targets

TEMPLATE_HEADINGS = {'summary', 'derivation', 'numerical method', 'code', 'tests', 'limits'}
HEADING = re.compile(r'^#{1,6}\s+(.+)')
SPECIAL = re.compile(r'^(?:\s{4}|\t|\s*(?:[-+*]\s|\d+[.)]\s|[>|]|:\s|\{#|!\[|\{\{[<%]|\[\^|\[[^]]+\]:|\\\[|\$\$|---\s*$|\*\*\*\s*$))')
NOTE = re.compile(r'^\s*(?:\*\*)?Local[- ]symbols\b', re.I)
TITLE = re.compile(r'''title\s*=\s*["'](?:At[- ]a[- ]glance|Local[- ]symbols)["']''', re.I)


@dataclass(frozen=True)
class Block:
    start: int
    end: int
    kind: str
    section: str


def blocks(lines: list[str]) -> list[Block]:
    """Conservative block scanner for the report's Markdown (indices are lines)."""
    result = []
    section = '(preamble)'
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        start = i
        h = HEADING.match(lines[i])
        if h:
            if h.group(1).strip().lower() not in TEMPLATE_HEADINGS or not lines[i].startswith('###'):
                section = f'{i + 1}: {h.group(1)}'
            i += 1
            continue
        kind = 'other'
        if s.startswith('<!--'):
            i += 1
            while '-->' not in lines[i - 1] and i < len(lines):
                i += 1
        elif i == 0 and s == '---':
            i += 1
            while i < len(lines) and lines[i].strip() not in ('---', '...'):
                i += 1
            i = min(i + 1, len(lines))
        elif CODE.match(lines[i]):
            fence = CODE.match(lines[i]).group(1)
            i += 1
            while i < len(lines):
                end = lines[i].strip()
                i += 1
                if re.fullmatch(re.escape(fence[0]) + '{' + str(len(fence)) + ',}', end):
                    break
        elif DIV.match(lines[i]):
            kind = 'box' if TITLE.search(lines[i]) else 'other'
            depth, fence = 1, None
            i += 1
            while i < len(lines) and depth:
                c = CODE.match(lines[i])
                d = DIV.match(lines[i])
                if fence:
                    if re.fullmatch(re.escape(fence[0]) + '{' + str(len(fence)) + ',}', lines[i].strip()):
                        fence = None
                elif c:
                    fence = c.group(1)
                elif d:
                    depth += 1 if d.group(2).strip() else -1
                i += 1
        elif s.startswith('$$') or s == r'\[':
            closing = '$$' if s.startswith('$$') else r'\]'
            i += 1
            if not (closing == '$$' and s.count('$$') > 1):
                while i < len(lines):
                    end = lines[i].strip()
                    i += 1
                    if end.startswith(closing):
                        break
        else:
            kind = 'note' if NOTE.match(lines[i]) else ('other' if SPECIAL.match(lines[i]) else 'prose')
            i += 1
            while i < len(lines) and lines[i].strip() and not HEADING.match(lines[i]) and not DIV.match(lines[i]) and not CODE.match(lines[i]):
                i += 1
        result.append(Block(start, i, kind, section))
    return result


def adjacent(lines: list[str], box: Block, prose: Block) -> bool:
    """True when only blank lines separate the box/note's last line from the prose."""
    return all(not line.strip() for line in lines[box.end:prose.start])


def analyze(text: str):
    """Return (moves, no-prose notes/boxes, over-length boxes, needs-hand-written-opening boxes).

    A move is (first box/note, first prose), made only when the prose directly follows a box/note.
    All offsets address original lines.
    """
    lines = text.splitlines(keepends=True)
    parsed = blocks(lines)
    sections = {}
    for block in parsed:
        sections.setdefault(block.section, []).append(block)
    moves, missing, long, blocked = [], [], [], []
    for group in sections.values():
        boxes = [b for b in group if b.kind in ('box', 'note')]
        prose = next((b for b in group if b.kind == 'prose'), None)
        long.extend(b for b in boxes if b.kind == 'box' and b.end - b.start - 2 > 6)
        if boxes and prose is None:
            missing.append(boxes[0])
        elif boxes and boxes[0].start < prose.start:
            before = group[group.index(prose) - 1]
            if before.kind in ('box', 'note') and adjacent(lines, before, prose):
                moves.append((boxes[0], prose))
            else:
                blocked.append(boxes[0])
    return moves, missing, long, blocked


def fix_text(text: str) -> str:
    lines = text.splitlines(keepends=True)
    moves = analyze(text)[0]
    for box, prose in reversed(moves):
        end = prose.end
        while end < len(lines) and not lines[end].strip():
            end += 1
        paragraph = lines[prose.start:end]
        # A final paragraph without a separator needs one at its new position.
        newline = '\r\n' if '\r\n' in text else '\n'
        if paragraph and not paragraph[-1].endswith('\n'):
            paragraph.append(newline)
        if paragraph and paragraph[-1].strip():
            paragraph.append(newline)
        del lines[prose.start:end]
        lines[box.start:box.start] = paragraph
    return ''.join(lines)


def check_text(text: str, label: str) -> int:
    moves, missing, long, blocked = analyze(text)
    for box, _ in moves:
        print(f'{label}:{box.start + 1}: prose required before box/note: {box.section}')
    for box in blocked:
        print(f'{label}:{box.start + 1}: needs a hand-written opening (first prose is not directly after the box): {box.section}')
    for box in missing:
        print(f'{label}:{box.start + 1}: report-only no prose: {box.section}')
    for box in long:
        print(f'{label}:{box.start + 1}: report-only over 6 lines ({box.end - box.start - 2}): {box.section}')
    return len(moves) + len(blocked)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('files', nargs='*')
    args = parser.parse_args(argv)
    count = 0
    for path in targets(args.files):
        text = path.read_bytes().decode('utf-8')
        if args.check:
            count += check_text(text, str(path))
        else:
            moves, _, _, blocked = analyze(text)
            new = fix_text(text)
            if new != text:
                path.write_bytes(new.encode('utf-8'))
            count += len(moves)
            for box in blocked:
                print(f'{path}:{box.start + 1}: needs a hand-written opening, left alone: {box.section}')
    print(f'fix_glance_order: {count} sections ' + ('out of order' if args.check else 'moved'))
    return int(args.check and count > 0)


if __name__ == '__main__':
    raise SystemExit(main())
