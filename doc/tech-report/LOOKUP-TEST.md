# Lookup test: grading method

The lookup test measures whether a reader who has never seen the book can find the answer to a question through
the book's own routes (table of contents, topic index, task map, glossary), and whether the section the route
leads to answers it.

## Inputs

- **Book**: the rendered PDF of branch `tech-report` of UCzhangxi/pyharp at one named commit, taken from the CI
  render of that commit (the PDF artifact of the `tech-report` workflow). Grade on that PDF, not on the sources.
- **Questions**: a held-out question bank, written by someone who never saw the book. Each question has a FIXED
  route and an expected topic, for example "How do I <task> in pyharp?" with route "task map".

## Rules for the grader (read first)

- Grade in a fresh sandbox: a new grader with no memory files, no prior conversation, no clone of pyharp or of
  the report sources. Its only inputs are the PDF, this file and the question bank.
- The grader plays a first-year PhD student in planetary atmospheres: knows the physics, has never used pyharp,
  never saw the book. It may not use anything it knows about pyharp beyond what the PDF says.
- Whoever runs the test only sets up the sandbox, passes it the PDF, this file and its questions, and publishes
  its table unedited. Do not correct or soften its grades.
- State with the results how the sandbox was made (tool or command) and that it had no memory.

## Per question

1. Use ONLY the question's fixed route to find a destination: TOC = the printed table of contents; topic index =
   the topic index appendix (Appendix D); task map = the "How do I ...?" appendix (Appendix E); glossary = the
   glossary appendix (Appendix F). No full-text search, no memory of where something is written. Record the entry
   used (verbatim) and where it sends you (section number and title), or "no entry".
2. Read that section and grade it:
   - FULL: answers the question as asked.
   - PARTIAL: right place, but the answer is incomplete or needs another section.
   - WRONG-PLACE: the route lands somewhere that does not answer it.
   - NO-ENTRY: the route has no entry for it.
   - NOT-PROVIDED-STATED: the route says the book does not cover it, with a reason.
3. Then one full-text search (`pdftotext` and `grep`): is it answered elsewhere in the book? This separates a
   route failure (answered elsewhere) from a content gap (answered nowhere).

## Output

One markdown table, one row per question:

| id | route | entry used (verbatim) | destination | grade | page | evidence (<= 2 quoted lines) | elsewhere? |
|---|---|---|---|---|---|---|---|

Publish it as a markdown file with the line "grades <first id>-<last id> done". Evidence and page are required on
every row; a row without them counts as not graded.

## Where the results go

A question's grade is the evidence for its status in the task map: `lookup_grade` in `tools/task-map.yaml`, and
the curated reader-task list `tools/reader-tasks.md`, from which `tools/gen_reader_tasks.py` generates the task
map appendix. A route failure is fixed in the route (an index or task-map entry, a label); a content gap is fixed
in the chapter or stated as "not provided" with its reason. A pointer alone is not evidence that a task is
answered.
