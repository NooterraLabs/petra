#!/bin/sh
# format.md says a proofs.json "cannot add a cell, drop one". The cells of one design under two proofs.json files:
# the honest hints prove the range of heat/seismic, so it has a `heat/seismic/where` cell, and the changed hints do not.
cd "$(dirname "$0")"
for d in honest changed; do
  printf "%s: " "$d"
  "${PETRA_VERIFY:?set PETRA_VERIFY to petra-verify}" --card $d/card.json --design $d/design.json --deck $d/deck.json --rules rules.json --run run.json --proofs $d/proofs.json |
    python3 -c 'import json,sys; j=json.load(sys.stdin); print(len(j["cells"]), "cells,", [c["entry"] for c in j["cells"] if c["entry"].endswith("/where")])'
done
