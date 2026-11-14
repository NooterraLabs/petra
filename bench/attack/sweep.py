"""`python3.11 -m bench.attack.sweep [--out DIR]`: leave out each key of the kernel's files, one at a time.

For three designs of the examples (one each that PASS, FAIL and are UNKNOWN) it takes card.json,
design.json, deck.json and proofs.json, and for each key that an object of the file has, at each place the
file has such an object, writes the file without it. The kernel and the third reading are
asked about each. The pages say what a file has, and not that a key may be missing, so the two
may read a missing key two ways. The sweep keeps each difference as the runner does and prints
what each reader says, by the key.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

from . import files as F, found, maker, readers

ROOT = Path(__file__).resolve().parents[2]


def objects(node, path=()):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from objects(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from objects(v, path + (i,))


def drops(obj):
    """(path, key, changed) for the first object at each place of the file's shape and each key it has."""
    seen = set()
    for path, o in objects(obj):
        shape = tuple("*" if isinstance(p, int) else p for p in path)
        for key in list(o):
            if (shape, key) in seen:
                continue
            seen.add((shape, key))
            changed = copy.deepcopy(obj)
            target = changed
            for p in path:
                target = target[p]
            del target[key]
            yield path, key, changed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=ROOT / "bench" / "attack" / "runs" / "sweep")
    args = ap.parse_args(argv)
    readers.Config.kernel = os.environ.get("PETRA_VERIFY")
    deck_text = (ROOT / "petra" / "decks" / "aisc360.json").read_text(encoding="utf-8")
    pairs: dict[tuple, list[str]] = {}
    for name in ("lap_pass", "lap_fail", "lap_unknown"):
        card = (ROOT / "examples" / "deck" / f"{name}.card").read_text(encoding="utf-8")
        design = (ROOT / "examples" / "deck" / f"{name}.petra").read_text(encoding="utf-8")
        base = readers.bundle_of(card, design, deck_text)
        for fname in ("card", "design", "deck", "proofs"):
            for path, key, changed in drops(json.loads(base[fname])):
                files = F.rebind({**base, fname: json.dumps(changed, indent=1, sort_keys=True)})
                j = readers.judge_files({**files, "rules": deck_text})
                where = f"{fname}.{'.'.join(str(p) for p in path if not isinstance(p, int))}{'.' if path else ''}{key}".replace("..", ".")
                pairs.setdefault((j.verdict.get("kernel"), j.verdict.get("twin")), []).append(f"{name}: {where}")
                for diff in j.diffs:
                    d = maker.Draft("sweep", None, "aisc360", deck_text, files=files, notes=[f"{where} left out of {name}"])
                    d.shipped = True
                    found.keep(args.out, d, j, readers.Diff(diff.kind, diff.where, diff.detail, key=f"sweep|{fname}|{key}|{diff.key}"))
    for (k, t), items in sorted(pairs.items(), key=lambda kv: str(kv[0])):
        print(f"kernel {k}, twin {t}: {len(items)}" + (f"  e.g. {items[0]}" if k != t else ""))
        if k != t:
            for item in items:
                print("    ", item)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
