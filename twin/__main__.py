"""py -3.11 -m twin CARD.petra [CARD.petra ...] prints one JSON report per card."""

import json
import sys
from pathlib import Path

from twin.card import CardError
from twin.run import check_text


def main(argv):
    if not argv:
        print("usage: py -3.11 -m twin CARD.petra [CARD.petra ...]", file=sys.stderr)
        return 2
    status = 0
    reports = []
    for path in argv:
        try:
            report = check_text(Path(path).read_text(encoding="utf-8"))
        except CardError as err:
            report, status = {"error": str(err)}, 3
        reports.append({"card": path, **report})
    print(json.dumps(reports[0] if len(reports) == 1 else reports, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
