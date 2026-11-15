"""A steel connection's calculation package: `python scripts/steel_package.py DESIGN.petra OUT_DIR`.

Checks the design against DESIGN.card beside it and writes OUT_DIR/design.card,
OUT_DIR/design.petra, OUT_DIR/report.md and OUT_DIR/certs/ (petra/models/steel/package.py),
then re-checks the package as `petra verify` and `petra check --certs --no-solve` would.
Prints the Python checker's status of the design and of the re-check, and exits 0 when the
package re-checks, 1 otherwise. Neither status is a verdict: a steel connection of the
models' kinds has no deck of rules, so where that checker refutes nothing the status reads
UNKNOWN, with the reason, and never PASS. `petra check` on the package gives the kernel's
verdict. Untrusted tooling; it never changes a verdict.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from petra.files import read_pair  # noqa: E402
from petra.models.steel.package import recheck, write_package  # noqa: E402
from petra.registry import build_registry  # noqa: E402
from petra.verify import held, no_deck  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="a steel connection's calculation package")
    parser.add_argument("design", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    registry = build_registry()
    pkg = write_package(*read_pair(args.design), args.out, registry)
    again = recheck(pkg, registry)
    print(f"{args.out}: {held(pkg.status)}; {again.certificates} certificates, {len(again.rejected)} rejected, "
          f"{len(again.missing)} missing; re-checked from the certificates alone: {held(again.status)}")
    if held(pkg.status) == "UNKNOWN":
        print(f"reason     {no_deck(pkg.kinds)}")
    return 0 if again.holds(pkg.status) else 1


if __name__ == "__main__":
    sys.exit(main())
