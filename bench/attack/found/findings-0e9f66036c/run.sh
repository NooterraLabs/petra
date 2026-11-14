#!/bin/sh
# The kernel and the third reading on the files of this folder, then all three readers through the attacker.
cd "$(dirname "$0")"
ROOT=${PETRA_ROOT:-$(git rev-parse --show-toplevel)}
"${PETRA_VERIFY:?set PETRA_VERIFY to petra-verify}" --card card.json --design design.json --deck deck.json --proofs proofs.json --rules rules.json
node "$ROOT/bench/twin/verify.mjs" --card card.json --design design.json --deck deck.json --proofs proofs.json --rules rules.json
(cd "$ROOT" && python3.11 -m bench.attack.repro "$OLDPWD")
