#!/bin/sh
# Rebuild every control with the scripts under controls/ and compare the Lean checker with
# the Python one on each file. The records go to results/.
#
#     sh run_controls.sh [WORK_DIR]
#
# Needs the Lean checker built (lake build) and Python 3.10 or later. It makes a virtual
# environment in WORK_DIR with numpy and scipy, which the generator uses.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
WORK=${1:-$(mktemp -d)}
mkdir -p "$WORK"
[ -x "$WORK/venv/bin/python" ] || { python3 -m venv "$WORK/venv" && "$WORK/venv/bin/pip" install -q numpy scipy; }
PY="$WORK/venv/bin/python"

# the scripts expect the generator and the checker beside them
C="$WORK/clearance"
mkdir -p "$C/neg" "$C/certs" "$C/probes" "$C/forms"
cp "$HERE"/controls/clearance/*.py "$HERE/reference/check_clearance.py" "$C/"
(cd "$C" && "$PY" run_cases.py > run_cases.log && "$PY" neg_controls.py > neg_controls.log && "$PY" cheat_controls.py > cheat_controls.log && "$PY" probe_checker.py > probe_checker.log) || true

# the sample and every control: the two checkers must give the same verdict on each
python3 "$HERE/compare.py" "$HERE/samples/c1_pin_in_bore_32.json" "$C/certs" "$C/neg" "$C/probes" --json "$HERE/results/clearance_compare.json" --strip "$WORK"

# loose ways of writing a number: here the two may differ, with Lean the stricter
"$PY" "$C/form_probes.py" "$HERE/samples/c1_pin_in_bore_32.json" "$C/forms"
python3 "$HERE/compare.py" "$C/forms" --json "$HERE/results/forms_clearance.json" --strip "$WORK" || true
