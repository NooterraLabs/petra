"""Family reuse benchmark: `python scripts/bench_family.py [--queries N] [--seed S]`.

Certifies examples/families/cu_pvc_clipped.lola once, then times N seeded query designs
inside its box along two paths, reuse (library lookup, transport, kernel check) and
recompute (solver, kernel check). Prints lola.bench.family.render(result): one line per
path, the "reuse" line first, then the predicted and measured ratios. Untrusted
measurement code; it never changes a verdict.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lola.bench import family  # noqa: E402

FAMILY = ROOT / "examples" / "families" / "cu_pvc_clipped.lola"


def main(argv: list[str] | None = None) -> int:
    """Parse --queries (default 200) and --seed (default 0), run family.run on FAMILY,
    print family.render(result), and return 0."""
    parser = argparse.ArgumentParser(description="family reuse versus recomputation")
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    print(family.render(family.run(str(FAMILY), args.queries, args.seed)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
