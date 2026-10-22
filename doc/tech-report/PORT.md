# Skeleton provenance and handoff

Home thread: C0C2D3PCW20:1792626016.512429.

Infrastructure source: UCzhangxi/kintera, branch tech-report,
head 68fea828ca5c6a0cffd22ca7a103c2bbcc960b34,
parent b327613d6d521fa236cb31f845df8fc4162e76c9.

Target: UCzhangxi/pyharp, branch tech-report,
base f34506f9d14ee7b1f2e1222775baa5093ae6967f,
parent 4b8172df1a17e871dae9886debc949858ff28ab6.
The target base equals the chengcli/pyharp source pin and peeled v2.7.8.

Publication repository: happysky19/pyharp.
Publication branch: tianhao/pyharp-report-skeleton.
The maintainer opens the upstream pull request; this work creates none upstream.

The source pin for zoeyzyhu/pydisort v1.7.1 is
8af15242a265a60ea6fb51c29d48e6688a63ab67.

## Port boundaries

STYLE rules, rendering/gate logic, generic generators and tests are retained.
Repository selectors, code links, package names, chapter inventory, source/test
mapping and bibliography are adapted. Contributor assignment files and output
columns are omitted. Scientific authors and named methods are retained.
The existing package-style allowance and derivation-summary column allowance
are retained from the source baseline; no new allowances were added.
The initial ratchet has 16 uncited chapter/appendix headings because these are
stubs. These are orphan-section counts, not unresolved links. Future chapter
prose must reduce that baseline. Unresolved rendered references fail the gate.

## Pending inputs and tooling limitation

The authoritative defect register was not found in the fetched source or shared
artifacts. DEFECTS.md reserves P1–P9 and D1 as CANDIDATE without inventing titles.

The test index captures 14 registered tests using CTest in the configured
build's tests directory. The imported refresh command runs CTest at the build
root, where this pyharp configuration lists zero tests. The current fixture was
made from the actual subdirectory output with the existing reducer. Refresh
subdirectory support is pending an issue-first change: the publication fork has
Issues disabled, and GitHub rejected issue creation. Registration is not test
execution; no numerical solver checks are claimed here.

The inherited TeX theme uses the older KOMA-Script `\ifstr` command. Local
rendering uses KOMA-Script 3.49.2, where it is available; newer KOMA-Script can
require a compatibility update. Package auto-install is disabled. Fork CI and
upstream PR CI are separate evidence; a local build is not PR acceptance.
