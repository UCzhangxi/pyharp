# Author checklist

Run this before opening a chapter PR. Everything here is cheap; the render is the only slow step, and CI runs
it anyway. Rules are in STYLE.md — this is the operational list, not a second rulebook. How a PR is opened and
merged: CONTRIBUTING.md.

## 1. Gates to run

All from `doc/tech-report`. Each command is the whole check; none needs an argument you have to invent.

| # | command | must say |
|---|---|---|
| 1 | `python3 tools/code_anchors.py check` | `0 unresolved`. Needs Universal Ctags 6.2.1 (`CTAGS=<binary>` if it is not on `PATH`) and a clone holding the pin (`PYHARP_REPO`), else it fetches one into `~/.cache/pyharp-report`. |
| 2 | `python3 tools/check_citations.py` | **no new problems**. Compare the count against the base, not against zero. |
| 3 | `python3 tools/gen_derivation_index.py` | writes, and leaves `git status` clean |
| 4 | `python3 tools/gen_notation_index.py` | writes, and leaves `git status` clean |
| 5 | `python3 tools/gen_test_index.py --check` | `is current` |
| 6 | `python3 tools/book_chapters.py` | lists the chapters that exist, and leaves `git status` clean |
| 7 | `find book -name '*.qmd' \| sort \| xargs python3 tools/check_math_spans.py` | exit 0 |
| 8 | `python3 tools/check_table_cells.py book/` | `clean` |
| 9 | `python3 tools/check_glance_boxes.py` | exit 0 (`python3 tools/fix_glance_boxes.py` inserts the missing blank lines) |
| 10 | `python3 -m pytest tools/tests -q` | all pass |
| 11 | `python3 tools/ratchet_gate.py check` | exit 0; a count that fell needs `python3 tools/ratchet_gate.py update` in the same PR, and a rise fails |
| 12 | `python3 tools/render_gate.py book/` | its `✗` lines are **the same as the base's**, not absent |

**Compare 2, 11 and 12 against the base commit, not against perfection.** Run them on the base in a scratch
worktree first and keep both outputs. A gate that was already red is not yours to fix in a content PR; a gate
that goes red *under your change* is.

Generators (3, 4, 5, 6) must be no-ops. If one rewrites a file, commit what it wrote — never hand-edit a
generated file.

Quarto is not installed on every machine. Where it is missing, `render_gate.py` runs the source gates and then
stops at the render itself; say so in the PR body and let CI (the `tech-report` workflow) be the render's word.

## 1b. Citations and the pin

- **Every code citation must resolve at the pin `code_pin.yml` names** — that is gate 1, and `0 unresolved` is
  the only passing result. A citation that resolves at some other sha is not a citation; the pin is the one the
  tools read, never one copied into prose.
- **Where a cited symbol's name or spelling changed at the pin** — renamed, moved to another file, split —
  **rewrite the citation to the symbol the code now has, keep the pin, and flag it in the PR body**: one line
  per citation giving the old symbol, the new symbol, and whether the claim beside it changed. Never drop the
  pin and never delete the citation to make the gate pass.

  > **PROVISIONAL.** This clause is written as the working rule but the editor has not ruled on it. Follow it,
  > and expect it to be replaced. It is marked provisional in STYLE.md 3.1 as well.

- `python3 tools/code_anchors.py bump <sha>` is the only way the pin moves, and only the editor runs it.
- Both pyharp and pydisort have full pins in `code_pin.yml`. Select the repository with `repo=pyharp` or `repo=pydisort`; raw links are checked against their named repository and commit.

## 1c. Notation and the book map

- **Write against NOTATION.md, not against a symbol you pick locally.** It is the shared register; a chapter
  that invents its own spelling for a symbol NOTATION.md already carries is a review failure.
- **Raise map questions to the editor rather than settling them in a chapter PR**: a notation conflict between
  two chapters, a symbol with two meanings, which chapter is a mechanism's home, or a definition that belongs
  somewhere other than where it sits. Those are the editor's to draft and the project owner's to rule on.
- **The generated notation index records first textual *use*, not first *definition*.** Appendix A comes from
  `tools/gen_notation_index.py`, whose column is headed **"first used"**: the first scheme, in book order,
  whose maths contains the symbol, matched exactly. It is a search result, not a definition audit — the
  passage it names may use a symbol that chapter never defines, and a row with no match shows `—`. So **that
  column is not authoritative for where a symbol is defined**. Before relying on it, open the section it names
  and confirm the symbol is defined there. If it is not, tell the editor rather than quietly adding a
  definition to make the row true.

## 1d. Evidence, re-pin and ownership (STYLE.md 11)

- **Every number you publish comes from a check output at the `code_pin.yml` pin, cited inline, and every
  claim names its test.** No test yet? Mark it **missing evidence** — do not let it stand on your word.
- **A quoted number is held against its stated tolerance, not against one host's digits.** Where a test
  byte-compares a check's `stdout` with its committed `.out`, that stays legal — but when such a test fails only
  in a round-off digit, the stale thing is the fixture, not the claim. Never hand-write a byte comparison of
  rendered prose, tables or figures (STYLE.md 11.1).
- **A pending Tests layer is a to-do you own, not a finished section.** If one is in your chapter, produce the
  test or retract the claim.
- **When the pin moves**, re-read the **union** of claims whose check output changed *and* the changed-symbol
  diff for claims with no test. The symbol diff is the floor, not a substitute (STYLE.md 11.2).
- **You own one chapter and you edit only that chapter.** Contributor assignments are coordinated outside this repository. The integrator never edits chapter text; generated appendix output is regenerated by its
  generator, never hand-edited by you.
- **A contradiction with another chapter goes to the editor** — you do not fix it in their file, and you do
  not quietly change yours to match. Ask the owner first where the text is theirs (STYLE.md 11.4,
  PROVISIONAL).
- **You are the burn-down owner for your chapter**: its history lines, off-pin shas, pending Tests layers and
  missing-evidence marks are yours to clear as you rewrite.

## 2. What goes in the PR body

- **Pins**: the base sha you branched from and the code pin, each with the command that read it
  (`git ls-remote`, `code_pin.yml`) and the UTC time.
- **One line per row or claim you touched**: what it was, what it is now, and why — or `kept`, with what you
  checked at the pin.
- **Citations whose symbol changed at the pin**: old symbol, new symbol, and whether the claim changed
  (section 1b, provisional). A reviewer reads this list first; an empty list is stated, not omitted.
- **Gate table, before and after**, with the numbers — not "gates pass".
- **Anything you deliberately did not do**, with its count. "I left 12 of these and here is where" is a
  finding; silence is a trap for the next author.
- No AI attribution line, and no `Co-Authored-By` trailer.

## 3. What the text may not contain

- A hand-written line number, in a link to a pinned repository or in `path:lines@sha` form (STYLE.md 3.1).
- A sha restating the pin. Read it from `code_pin.yml`.
- Change history: "since `#NNN`", "main after ...", "checked at `<sha>`", or a PR number in prose
  (STYLE.md 3.2). Provenance goes in the PROVENANCE block, a `[source: ...]` or `[sha: ...]` footnote, or a
  markdown `[^label]:` footnote definition — all three are legal and a PR number may appear in any of them.
- A sha in body prose. A sha belongs only in `code_pin.yml`, a PROVENANCE block or a provenance footnote
  (STYLE.md 3.1). A link for a repository with no code pin carries its sha in the URL, which is the link form,
  not prose.
- A measured number without its command and the versions behind it (STYLE.md 4).
- Anything that is not pyharp code at the pin or published literature: no unpublished notes, no private
  material (CONTRIBUTING.md).

## 4. What to ask the editor instead of deciding

Raise it in the PR body or as an issue on UCzhangxi/pyharp; do not settle these inside a chapter PR.

- **A new symbol** that NOTATION.md has no entry for — propose it, use it locally, and flag it.
- **A symbol that clashes** with a reserved letter, or that two chapters use differently.
- **A section that belongs in another chapter**, or a scheme that needs splitting or merging.
- **A cross-chapter claim** you cannot verify from your own chapter's code.
- **A pin move**, always. Authors never move the pin.
- **A gate that is red on the base.** Report the count; do not sweep it in a content PR.
