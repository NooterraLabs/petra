"""py -3.11 -m twin DESIGN.petra [DESIGN.petra ...] prints one JSON report per design, each
read against the card beside it, DESIGN.card."""

import json
import sys
from pathlib import Path

from twin.card import CardError
from twin.run import check_text


def main(argv):
    if not argv:
        print("usage: py -3.11 -m twin DESIGN.petra [DESIGN.petra ...]", file=sys.stderr)
        return 2
    status = 0
    reports = []
    for path in argv:
        card = Path(path).with_suffix(".card")
        try:
            report = check_text(card.read_text(encoding="utf-8"), Path(path).read_text(encoding="utf-8"))
        except CardError as err:
            report, status = {"error": str(err)}, 3
        reports.append({"design": path, **report})
    print(json.dumps(reports[0] if len(reports) == 1 else reports, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
