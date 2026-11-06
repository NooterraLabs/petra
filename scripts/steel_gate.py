"""The steel deck's gate: `python scripts/steel_gate.py [--n 10000] [--seed 1] [--workers 6]
[--faults 3] [--runs 22] [--budget 100] [--no-twin]`.

Generates the connections, checks each with the deck and the twin, seeds the
manufactured faults, runs the breaker, and writes docs/steel_gate.md (the summary, §9
items 4 to 8) and
docs/steel_gate_log.jsonl (every undecided design, disagreement, fault and breaker run).
Untrusted tooling; it never changes a verdict. Exits 1 when an item fails.
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

from lola.models.steel import breaker as B  # noqa: E402
from lola.models.steel import faults as F  # noqa: E402
from lola.models.steel import gate as G  # noqa: E402
from lola.models.steel.generate import generate  # noqa: E402
from lola.registry import build_registry  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="the steel deck's exhaustiveness gate")
    parser.add_argument("--n", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--faults", type=int, default=3, help="passing designs per kind each fault is put into")
    parser.add_argument("--runs", type=int, default=22, help="breaker runs, round-robin over the kinds")
    parser.add_argument("--budget", type=int, default=100, help="deck evaluations per breaker run")
    parser.add_argument("--no-twin", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    args = parser.parse_args(argv)
    with_twin = not args.no_twin
    start = time.time()
    step = 50
    jobs = [(args.seed, i, min(step, args.n - i), with_twin) for i in range(0, args.n, step)]
    rows: list[dict] = []
    with Pool(args.workers) as pool:
        for done, part in enumerate(pool.imap(G.chunk, jobs), 1):
            rows.extend(part)
            if done % 20 == 0:
                print(f"{len(rows)} designs, {time.time() - start:.0f} s", flush=True)
    registry = build_registry()
    caught = list(F.seed_faults(registry, args.faults))
    print(f"faults: {len(caught)}, {time.time() - start:.0f} s", flush=True)
    runs: list[dict] = []
    if with_twin:
        oracle = B.twin_oracle(registry)
        starts = [g for g in generate(args.runs * 4, args.seed + 1000, registry) if g.expected == "PASS" and not g.free
                  and not g.toleranced][:args.runs]
        for g in starts:
            runs.append(B.run(g, registry, oracle, args.budget, args.seed).log())
        print(f"breaker: {len(runs)} runs, {time.time() - start:.0f} s", flush=True)
    summary = G.summarise(rows, args.seed, caught, runs, args.budget)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "steel_gate.md").write_text(G.render(summary), encoding="utf-8", newline="\n")
    (args.out / "steel_gate_log.jsonl").write_text("\n".join(G.log_lines(summary)) + "\n", encoding="utf-8",
                                                     newline="\n")
    print(G.render(summary))
    failed = (summary.undecided or summary.unwitnessed or summary.disagreements or summary.twin_errors
              or not all(c.caught and c.is_named for c in caught) or any(r["false_pass"] for r in runs))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
