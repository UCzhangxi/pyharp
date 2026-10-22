# Derivation specification

Each chapter follows the pinned implementation and states its assumptions. Scientific derivations are pending.

## How to use an entry

Every entry has six parts.

1. **Question**: what the derivation answers, in plain words. Open the section with it.
2. **Start**: definitions and assumptions, each one a code fact (file:line at the pin) or textbook physics.
   State them before the first equation; do not introduce assumptions later.
3. **End**: the formula the code evaluates, with file:line. The derivation must arrive at this formula, in the
   code's variables and sign conventions. Where the derivation and the code differ, say so and point to the
   defect entry; never bend the derivation to match a defect.
4. **Steps**: the intermediate results a reader must see. Show each one as a displayed equation with one
   sentence of reasoning. A step may be merged with its neighbour only if the merge is a single substitution.
5. **Check**: a short numeric test against the built package that confirms the end result. The scripts live
   in `derivation-checks/` next to this file; run one from a scratch directory
   (`export PYHARP_WT=<build tree>; cd $(mktemp -d); python <this dir>/derivation-checks/<script>.py`) and
   quote its `.out` line in the section's Tests layer with the tolerance.
   A derivation without a passing check is not done.
6. **Home and status**: the section file that should hold the derivation and its current coverage:
   PRESENT (all steps a reader needs are written; at most a remark is missing), PARTIAL (named steps are
   missing), MISSING (no derivation).
