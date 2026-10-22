#!/usr/bin/env python3
"""Check that every code citation in the report resolves at its sha (STYLE.md 3.1, 9.3, 10.6).

Two citation forms are recognised:

  * the link of STYLE 10.6, a GitHub blob URL pinned to a sha, with an optional line anchor:
        [`arrhenius.cpp:279-306`](https://github.com/chengcli/pyharp/blob/<sha>/src/kinetics/arrhenius.cpp#L279-L306)
  * the reviewers' notation of STYLE 3.1, `path:lines@sha`, optionally prefixed by a repository
    (`snapy:src/eos/x.cpp:42@<sha>`), with several ranges (`x.cpp:3-9, 20-24@<sha>`) or none
    (`docs/x.md@<sha>`, file only). It is allowed in the planning files and the checks, and
    is an error in a `.qmd` file, where STYLE 3.1 allows only the link.
  * a commit of STYLE 3.2, `pyharp@<sha>` (or `snapy@<sha>`, ...): only the sha is checked.
  * a note reference of STYLE 3.2, `docs/<file>@<full sha>` (a file in pyharp's docs/) with no lines: allowed in a `.qmd`
    (editor's ruling 1791657615) at the full 40-character sha only; the sha and the file are checked.

For each citation the checker verifies that
  1. the sha is hexadecimal and long enough: the full 40 characters in a URL (STYLE 10.6), at least
     7 in the notation (STYLE 3.1); a branch or tag name in a URL is an unpinned citation;
  2. the sha names a commit, looked up with `git rev-parse` in the local clones (the repository that
     holds this report, and any `--repo-dir`), then in a blobless cache clone of the cited repository,
     then by fetching the sha itself;
  3. the file exists at that sha, and every cited line is between 1 and the file's last line;
  4. the link text of STYLE 10.6 (`basename:lines`) names the same file and lines as its URL, and a
     repository other than pyharp is named in front of it (`snapy hydro.cpp:49-61`, STYLE 3.1);
  5. the repository is one the report may cite, from the owners it may be cited from (STYLE 3.1):
     pyharp (chengcli/pyharp, UCzhangxi/pyharp), snapy (chengcli/snapy, UCzhangxi/snapy),
     pyharp (chengcli/pyharp), paddle (chengcli/paddle);
  6. in a `.qmd`, a link with a line range names its anchor symbol and the symbol is inside the cited
     lines (STYLE 3.1). The anchor is the `symbol` cell of the link's table row when the table has that
     column (the Code table), else the last inline-code span before the link in its sentence or table
     cell, after any earlier link there (each link names its own): "The rate is `ArrheniusImpl::forward`
     ([`arrhenius.cpp:279-306`](...))". It is found
     in the lines if its identifier (the span without a call's `(...)`), or the last `::` part of it,
     appears there as a whole word.

Every problem is reported as `<file>:<line>: <citation>: <message>`; the exit status is 1 if there is
any, 0 otherwise (2 for a usage error).

    python3 tools/check_citations.py                      # book/, chapters/ and src/ of the report
    python3 tools/check_citations.py book/chapters/06-kinetics.qmd
    python3 tools/check_citations.py --offline            # local clones only, no network
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPORT = Path(__file__).resolve().parent.parent
DEFAULT_DIRS = ("book", "chapters", "src")
SUFFIXES = {".qmd", ".md", ".py", ".yml", ".yaml"}

# The repository this report describes: no prefix in the STYLE 3.1 notation means it, and its links need no name
# in front of the link text.
HOME = "pyharp"

# Repository prefixes of the STYLE 3.1 notation.
PREFIX_REPOS = {
    "pyharp": "chengcli/pyharp",
    "snapy": "chengcli/snapy",
    "pyharp": "chengcli/pyharp",
    "paddle": "chengcli/paddle",
    "pydisort": "zoeyzyhu/pydisort",
}

# STYLE 3.2: a note reference is a file in this directory of the home repository.
NOTE_DIR = "docs/"

# STYLE 3.1: the repositories the report may cite, each from the only owner it may be cited from.
ALLOWED_REPOS = ("chengcli/pyharp", "UCzhangxi/pyharp", "chengcli/snapy", "UCzhangxi/snapy",
                 "chengcli/pyharp", "chengcli/paddle", "happysky19/pyharp", "zoeyzyhu/pydisort")

HEX = re.compile(r"[0-9a-f]+")

# [`text`](url) or [text](url): the link text is checked against the URL when it reads basename:lines.
LINK_TEXT = re.compile(r"\[`?([^\]`]*)`?\]\(\s*$")

BLOB_URL = re.compile(
    r"https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)/blob/"
    r"(?P<ref>[^/\s)#>\"'`\]]+)/(?P<path>[^\s)#>\"'`\]]+)"
    r"(?:#L(?P<l1>\d+)(?:-L(?P<l2>\d+))?)?")

# path:lines@sha or path@sha. The path must contain a slash or end in an extension, so prose is skipped.
NOTATION = re.compile(
    r"(?<![\w/.:@-])(?:(?P<prefix>[a-z][\w-]*):)?"
    r"(?P<path>(?:[\w.-]+/)+[\w.-]+|[\w-]+\.\w+)"
    r"(?::(?P<lines>\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*))?"
    r"@(?P<sha>[0-9a-fA-F]+)\b")

# pyharp@sha, snapy@sha, ...: a commit.
COMMIT = re.compile(r"(?<![\w/.:@-])(?P<prefix>" + "|".join(PREFIX_REPOS) + r")@(?P<sha>[0-9a-fA-F]+)\b")


@dataclass
class Citation:
    file: Path
    line: int
    text: str
    repo: str        # owner/repo
    sha: str
    path: str | None  # None for a commit
    ranges: list[tuple[int, int | None]]
    form: str        # "url", "notation" or "commit"
    link_text: str | None = None
    anchor: str | None = None    # the anchor symbol (STYLE 3.1), for a link in a .qmd


def _git(gitdir: Path, *args: str, binary: bool = False):
    return subprocess.run(["git", "-C", str(gitdir), *args], capture_output=True,
                          text=not binary, timeout=600)


class Resolver:
    """Finds a commit and reads a file at it, in local clones first and then in cache clones."""

    def __init__(self, local: list[Path], cache_dir: Path, offline: bool):
        self.local = local
        self.cache_dir = cache_dir
        self.offline = offline
        self._cache_ready: dict[str, Path | None] = {}
        self._commits: dict[tuple[str, str], tuple[Path | None, str]] = {}
        self._lines: dict[tuple[Path, str, str], int | None] = {}

    def _cache_clone(self, repo: str) -> Path | None:
        if repo in self._cache_ready:
            return self._cache_ready[repo]
        dest = self.cache_dir / repo.replace("/", "__")
        url = f"https://github.com/{repo}.git"
        if (dest / "HEAD").exists():
            p = _git(dest, "fetch", "--quiet", "--filter=blob:none", "origin",
                     "+refs/heads/*:refs/heads/*", "+refs/tags/*:refs/tags/*")
        else:
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                p = subprocess.run(["git", "clone", "--quiet", "--bare", "--filter=blob:none", url, str(dest)],
                                   capture_output=True, text=True, timeout=1800)
            except OSError as e:
                p = subprocess.CompletedProcess([], 1, "", str(e))
        if p.returncode != 0:
            print(f"warning: could not clone or fetch {url}: {p.stderr.strip()}", file=sys.stderr)
        self._cache_ready[repo] = dest if (dest / "HEAD").exists() else None
        return self._cache_ready[repo]

    @staticmethod
    def _rev_parse(gitdir: Path, sha: str) -> tuple[str | None, str]:
        p = _git(gitdir, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{sha}^{{commit}}")
        if p.returncode == 0:
            return p.stdout.strip(), ""
        p = _git(gitdir, "rev-parse", "--disambiguate=" + sha) if len(sha) < 40 else None
        if p is not None and len(p.stdout.split()) > 1:
            return None, f"short sha {sha} is ambiguous; use more characters"
        return None, ""

    def commit(self, repo: str, sha: str) -> tuple[Path | None, str]:
        """Return (gitdir, full sha) or (None, reason)."""
        key = (repo, sha)
        if key in self._commits:
            return self._commits[key]
        result: tuple[Path | None, str] = (None, f"sha {sha} not found in any local clone")
        for gitdir in self.local:
            full, why = self._rev_parse(gitdir, sha)
            if full:
                result = (gitdir, full)
                break
            if why:
                result = (None, why)
                break
        else:
            if not self.offline:
                result = (None, f"sha {sha} not found in {repo} (local clones, cache clone, fetch by sha)")
                cache = self._cache_clone(repo)
                if cache is not None:
                    full, why = self._rev_parse(cache, sha)
                    if not full and not why and len(sha) == 40:
                        # A commit no branch reaches (a force-pushed PR head, a fork's commit) can still be
                        # fetched by its full sha.
                        _git(cache, "fetch", "--quiet", "--filter=blob:none", "origin", sha)
                        full, why = self._rev_parse(cache, sha)
                    if full:
                        result = (cache, full)
                    elif why:
                        result = (None, why)
            else:
                result = (None, f"sha {sha} not found in any local clone (offline)")
        self._commits[key] = result
        return result

    def lines(self, gitdir: Path, sha: str, path: str) -> list[str]:
        """The lines of path at sha (the path is known to be a file there)."""
        data = _git(gitdir, "cat-file", "blob", f"{sha}:{path}", binary=True).stdout
        return data.decode("utf-8", errors="replace").splitlines()

    def line_count(self, gitdir: Path, sha: str, path: str) -> int | None:
        """Number of lines of path at sha, or None if the path is not a file there."""
        key = (gitdir, sha, path)
        if key not in self._lines:
            t = _git(gitdir, "cat-file", "-t", f"{sha}:{path}")
            if t.returncode != 0 or t.stdout.strip() != "blob":
                self._lines[key] = None
            else:
                data = _git(gitdir, "cat-file", "blob", f"{sha}:{path}", binary=True).stdout
                self._lines[key] = data.count(b"\n") + (1 if data and not data.endswith(b"\n") else 0)
        return self._lines[key]


def _ranges(spec: str | None) -> list[tuple[int, int | None]]:
    """'3-9, 20' -> [(3, 9), (20, None)]."""
    out: list[tuple[int, int | None]] = []
    for part in (spec or "").split(","):
        if part.strip():
            a, _, b = part.strip().partition("-")
            out.append((int(a), int(b) if b else None))
    return out


def _fmt(ranges: list[tuple[int, int | None]]) -> str:
    return ", ".join(f"{a}" if b is None else f"{a}-{b}" for a, b in ranges)


# A whole link (text and target), removed before looking for the anchor so link texts are never taken for it.
_LINK = re.compile(r"\[[^\]\n]*\]\([^)\n]*\)")
_SPAN = re.compile(r"`([^`\n]+)`")


def _cells(row: str) -> list[tuple[int, int]]:
    """(start, end) of each cell of a pipe-table row; a | inside backticks or escaped is not a border."""
    borders, tick = [], False
    for i, ch in enumerate(row):
        if ch == "`":
            tick = not tick
        elif ch == "|" and not tick and (i == 0 or row[i - 1] != "\\"):
            borders.append(i)
    return list(zip(borders, borders[1:]))


def find_anchor(lines: list[str], n: int, start: int) -> str | None:
    """The anchor symbol of the link that starts at column `start` of line `n` (0-based), or None."""
    line = lines[n]
    if line.lstrip().startswith("|"):
        top = n
        while top > 0 and lines[top - 1].lstrip().startswith("|"):
            top -= 1
        header = [lines[top][a + 1:b].strip().lower() for a, b in _cells(lines[top])]
        cells = _cells(line)
        if "symbol" in header and header.index("symbol") < len(cells):
            a, b = cells[header.index("symbol")]
            cell = line[a + 1:b].strip()
            spans = _SPAN.findall(cell)
            return (spans[0] if spans else cell) or None
        before = next((line[a + 1:start] for a, b in cells if a < start < b), line[:start])
    else:
        top = n
        while top > 0 and lines[top - 1].strip() and not lines[top - 1].lstrip().startswith(
                ("#", "|", "```", ":::")):
            top -= 1
        before = " ".join(lines[top:n] + [line[:start]])
        before = re.split(r"[.!?]\s+", before)[-1]          # the sentence the link is in
    before = _LINK.split(before)[-1]                         # each link names its own anchor
    spans = _SPAN.findall(before)
    return spans[-1] if spans else None


def anchor_names(anchor: str) -> list[str]:
    """The identifiers an anchor stands for: the span without a call's (...), and its last :: part."""
    name = re.sub(r"\(.*$", "", anchor).strip()
    names = [name] if name else []
    if "::" in name and name.rsplit("::", 1)[1]:
        names.append(name.rsplit("::", 1)[1])
    return names


def find_citations(path: Path) -> list[Citation]:
    """Every citation in one file, with its 1-based line number."""
    out: list[Citation] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    for n, line in enumerate(lines, 1):
        url_spans = []
        for m in BLOB_URL.finditer(line):
            url_spans.append(m.span())
            text = LINK_TEXT.search(line[:m.start()])
            ranges = [(int(m["l1"]), int(m["l2"]) if m["l2"] else None)] if m["l1"] else []
            anchor = None
            if path.suffix == ".qmd" and ranges:
                start = line.rfind("[", 0, text.start() + 1) if text else m.start()
                anchor = find_anchor(lines, n - 1, max(start, 0))
            out.append(Citation(path, n, m.group(0), f"{m['owner']}/{m['repo']}", m["ref"], m["path"],
                                ranges, "url", text.group(1) if text else None, anchor))
        for m in NOTATION.finditer(line):
            if any(a <= m.start() < b for a, b in url_spans):
                continue
            prefix = m["prefix"]
            repo = PREFIX_REPOS.get(prefix or HOME, f"<unknown repository prefix '{prefix}'>")
            out.append(Citation(path, n, m.group(0), repo, m["sha"], m["path"], _ranges(m["lines"]),
                                "notation"))
        for m in COMMIT.finditer(line):
            if not any(a <= m.start() < b for a, b in url_spans):
                out.append(Citation(path, n, m.group(0), PREFIX_REPOS[m["prefix"]], m["sha"], None, [],
                                    "commit"))
    return out


def is_note_reference(c: Citation) -> bool:
    """A note reference of STYLE 3.2, `docs/<file>@<sha>`: a file in the home repository's NOTE_DIR, no lines, no
    repository prefix. The editor's ruling (1791657615): in a .qmd it is exempt from the code-citation form of STYLE
    3.1, but only at the full 40-character sha; the sha and the file are still checked."""
    return (c.form == "notation" and c.path is not None and c.path.startswith(NOTE_DIR)
            and not c.ranges and c.repo == PREFIX_REPOS[HOME] and not c.text.startswith(HOME + ":"))


def check(c: Citation, resolver: Resolver) -> list[str]:
    """The problems of one citation, as messages without the location."""
    sha = c.sha
    if c.repo.startswith("<"):
        return [c.repo[1:-1]]
    if c.form == "notation" and c.file.suffix == ".qmd":
        if not is_note_reference(c):
            return ["STYLE 3.1: path:line@sha never appears in a .qmd file; use the link of STYLE 10.6"]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            return [f"a note reference needs the full 40-character sha, not '{sha}' (STYLE 3.2; no short shas)"]
    if c.repo.lower() not in {r.lower() for r in ALLOWED_REPOS}:
        return [f"{c.repo} is not a repository the report may cite; STYLE 3.1 allows "
                f"{', '.join(ALLOWED_REPOS)} (a fork's commit is cited from the repository it lives on)"]
    if not HEX.fullmatch(sha):
        if c.form == "url":
            return [f"URL is not pinned: '{sha}' is not a sha (STYLE 10.6 requires the full 40-character sha)"]
        return [f"'{sha}' is not a hexadecimal sha"]
    if c.form == "url" and len(sha) != 40:
        return [f"sha {sha} has {len(sha)} characters; a URL needs the full 40-character sha (STYLE 10.6)"]
    if len(sha) < 7 or len(sha) > 40:
        return [f"sha {sha} has {len(sha)} characters; use 7 to 40 (STYLE 3.1)"]

    errors = []
    for a, b in c.ranges:
        if a < 1:
            errors.append(f"line {a} does not exist; lines start at 1")
        if b is not None and b < a:
            errors.append(f"line range {a}-{b} is reversed")
    text = re.fullmatch(r"(?:(?P<repo>[\w.-]+) )?(?P<name>[\w./-]+):(?P<lines>\d+(?:-\d+)?)", c.link_text or "")
    if c.form == "url" and text:
        name, lines = text["name"], text["lines"]
        repo = c.repo.split("/")[1]
        if repo != HOME and text["repo"] != repo:
            errors.append(f"link text must start with the repository name: '{repo} {name}:{lines}' (STYLE 3.1)")
        elif repo == HOME and text["repo"] not in (None, HOME):
            errors.append(f"link text names repository '{text['repo']}' but the URL is {c.repo}")
        if not ("/" + c.path).endswith("/" + name):
            errors.append(f"link text names '{name}' but the URL points at '{c.path}'")
        if not c.ranges:
            errors.append(f"link text cites lines {lines} but the URL has no #L anchor")
        elif lines != _fmt(c.ranges):
            want = _fmt(c.ranges).replace("-", "-L")
            errors.append(f"link text cites lines {lines} but the URL anchor is #L{want}")

    if c.form == "url" and c.file.suffix == ".qmd" and c.ranges and not c.anchor:
        errors.append("names no anchor symbol: put the function, type or variable the lines contain in "
                      "backticks before the link, or in the Code table's symbol column (STYLE 3.1)")

    gitdir, full = resolver.commit(c.repo, sha)
    if gitdir is None:
        return errors + [full]
    if c.path is None:
        return errors
    n = resolver.line_count(gitdir, full, c.path)
    if n is None:
        hint = "" if "/" in c.path else "; give the path from the repository root, not the basename"
        return errors + [f"file {c.path} does not exist at {sha}{hint}"]
    last = max((b if b is not None else a for a, b in c.ranges), default=0)
    if last > n:
        errors.append(f"line {last} is past the end of {c.path} at {sha} ({n} lines)")
    elif c.anchor and c.ranges and not errors:
        text = resolver.lines(gitdir, full, c.path)
        cited = "\n".join(l for a, b in c.ranges for l in text[a - 1:(b or a)])
        if not any(re.search(r"(?<![\w])" + re.escape(x) + r"(?![\w])", cited) for x in anchor_names(c.anchor)):
            errors.append(f"anchor symbol `{c.anchor}` is not in lines {_fmt(c.ranges)} of {c.path} at {sha} "
                          "(STYLE 3.1: the range must contain the anchor)")
    return errors


def collect(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for p in paths:
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.suffix in SUFFIXES and f.is_file()
                            and "_book" not in f.parts and "_freeze" not in f.parts)
        elif p.is_file():
            files.append(p)
        else:
            raise FileNotFoundError(p)
    return files


def _local_clones(extra: list[Path]) -> list[Path]:
    clones = list(extra)
    top = subprocess.run(["git", "-C", str(REPORT), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True)
    if top.returncode == 0:
        clones.append(Path(top.stdout.strip()))
    return clones


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="*", type=Path,
                    help="files or directories to scan (default: book/, chapters/, src/ of the report)")
    ap.add_argument("--repo-dir", action="append", type=Path, default=[],
                    help="another local clone to look shas up in (repeatable)")
    ap.add_argument("--cache-dir", type=Path,
                    default=Path(os.environ.get("CHECK_CITATIONS_CACHE",
                                                Path.home() / ".cache" / "pyharp-report-citations")),
                    help="where cache clones of cited repositories live")
    ap.add_argument("--offline", action="store_true", help="never clone or fetch")
    ap.add_argument("--list", action="store_true", help="print every citation found, with its status")
    args = ap.parse_args(argv)

    paths = args.paths or [REPORT / d for d in DEFAULT_DIRS if (REPORT / d).is_dir()]
    try:
        files = collect(paths)
    except FileNotFoundError as e:
        print(f"error: no such file or directory: {e}", file=sys.stderr)
        return 2

    resolver = Resolver(_local_clones(args.repo_dir), args.cache_dir, args.offline)
    n_cite = n_bad = 0
    for f in files:
        for c in find_citations(f):
            n_cite += 1
            problems = check(c, resolver)
            where = f"{os.path.relpath(c.file)}:{c.line}"
            for msg in problems:
                print(f"{where}: {c.text}: {msg}")
            if problems:
                n_bad += 1
            elif args.list:
                print(f"{where}: {c.text}: ok")
    print(f"check_citations: {n_cite} citations in {len(files)} files, {n_bad} with problems",
          file=sys.stderr)
    return 1 if n_bad else 0


if __name__ == "__main__":
    sys.exit(main())
