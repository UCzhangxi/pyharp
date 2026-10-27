# Sourced by the chNN_run.sh scripts: keep a copy of the committed outputs before they are regenerated in place, then
# compare the two with tools/compare_outputs.py, which normalises version, host, timing and date lines, and masks the
# host-dependent measurements declared in host-dependent.json, and nothing else (its docstring lists the rules). The
# run script exits with the comparison's status: 0 REPRODUCED, 1 not.
#   snapshot_outputs FILE...            FILE relative to the directory of the run script ($D), or to $CMP_ROOT when
#                                       the run script sets it (the report directory, for figure data in src/)
#   compare_outputs CHAPTER [OPTION...] compares the files given to snapshot_outputs; options go to the tool
snapshot_outputs() {
  CMP_FILES=("$@"); CMP_EXPECTED=$(mktemp -d)
  local f
  for f in "$@"; do
    mkdir -p "$CMP_EXPECTED/$(dirname "$f")"
    [ -f "${CMP_ROOT:-$D}/$f" ] && cp "${CMP_ROOT:-$D}/$f" "$CMP_EXPECTED/$f"
  done
  return 0
}
compare_outputs() {
  local chapter=$1 rc hd=(); shift
  [ -f "$D/host-dependent.json" ] && hd=(--host-dependent "$D/host-dependent.json")
  echo
  python3 "$D/../tools/compare_outputs.py" "${hd[@]}" "$@" "$chapter" "$CMP_EXPECTED" "${CMP_ROOT:-$D}" \
    "${CMP_FILES[@]}"; rc=$?
  rm -rf "$CMP_EXPECTED"
  return $rc
}
