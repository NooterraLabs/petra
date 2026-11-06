"""Family reuse benchmark: `python scripts/bench_family.py [--queries N] [--seed S] [--family NAME]`.

Runs every family in petra.bench.family.FAMILIES (the cu_pvc cable family, then the
Warren truss family), or only the one named. Each is certified once, then seeded query
designs inside its box are timed along two paths, reuse (the library lookup, which gives
an Instance of the family, and the kernel check) and recompute (solver, kernel check).
Prints one block per family, each petra.bench.family.render(result): one line per path,
the "reuse" line first, the first query on a cold family memo, the split of each path's
time, then the predicted and measured ratios. Untrusted measurement code; it never
changes a verdict.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from petra.bench import family  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    """--queries overrides every family's default query count. Prints the blocks and
    returns 0."""
    names = [f.name for f in family.FAMILIES]
    parser = argparse.ArgumentParser(description="family reuse versus recomputation")
    parser.add_argument("--queries", type=int, default=None, help="queries per family (default: "
                        + ", ".join(f"{f.name} {f.queries}" for f in family.FAMILIES) + ")")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--family", choices=names, action="append", help="run only this family (repeatable)")
    args = parser.parse_args(argv)
    chosen = [f for f in family.FAMILIES if args.family is None or f.name in args.family]
    print("\n\n".join(family.render(family.run(f, args.queries, args.seed)) for f in chosen))
    return 0


if __name__ == "__main__":
    sys.exit(main())
