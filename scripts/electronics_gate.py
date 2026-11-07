"""The electronics deck's gate: `python scripts/electronics_gate.py [--n 1200] [--seed 1]
[--workers 6] [--faults 3] [--every 10]`.

Generates the boards, checks each with the deck, re-checks the certificates of every
`--every`-th one, plants the faults, and writes docs/electronics_gate.md. Untrusted
tooling; it never changes a verdict. Exits 1 when an item fails.
"""
from __future__ import annotations

import argparse
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from petra.models.electronics import faults as F  # noqa: E402
from petra.models.electronics import gate as G  # noqa: E402
from petra.registry import build_registry  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="the electronics deck's gate")
    parser.add_argument("--n", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--faults", type=int, default=3, help="passing designs per kind each fault is put into")
    parser.add_argument("--every", type=int, default=10, help="re-check the certificates of every n-th design; 0 for none")
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    args = parser.parse_args(argv)
    start = time.time()
    step = 25
    jobs = [(args.seed, i, min(step, args.n - i), args.every) for i in range(0, args.n, step)]
    rows: list[dict] = []
    with Pool(args.workers) as pool:
        for done, part in enumerate(pool.imap(G.chunk, jobs), 1):
            rows.extend(part)
            if done % 10 == 0:
                print(f"{len(rows)} designs, {time.time() - start:.0f} s", flush=True)
    caught = list(F.seed_faults(build_registry(), args.faults))
    print(f"faults: {len(caught)}, {time.time() - start:.0f} s", flush=True)
    summary = G.summarise(rows, args.seed, caught)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "electronics_gate.md").write_text(G.render(summary), encoding="utf-8", newline="\n")
    print(G.render(summary))
    return 1 if G.failed(summary) else 0


if __name__ == "__main__":
    sys.exit(main())
