"""Canary recall (docs/plan.md P1 items 4 and 7): `python scripts/canary_recall.py [--seed 2]
[--budget 600] [--workers 7] [--hole KIND:MODE[+MODE...][@CONDITION] ...] [--out docs]`.

Would the absurd-design search see a hole in Petra? The harness plants holes without
editing petra/: it runs Petra, then takes every outcome of the hole's modes as discharged,
the verdict of a deck that lacks those checks (absurd_gap.holed_status). A design exposes
the hole when the holed Petra passes it, the outside judge rejects it for a condition the
hole guards, and the hole is what let it through: Petra itself does not pass it, or the
hole has no modes because today's Petra already lacks the check. Recall per kind and
domain is holes exposed over holes planted, within a fixed budget for each search:

  1. the absurd-gap generator draws BUDGET designs of the hole's kind from the stream of
     `scripts/absurd_gap.py --seeds SEED` (one Petra run per design serves every hole of
     the kind);
  2. on each steel hole the generator missed, the steel breaker climbs for BUDGET Petra
     evaluations: the moves and acceptance rule of petra/models/steel/breaker.py, with the
     holed deck as the deck and the judge as the oracle (utilisation 2 on each condition it
     raises). breaker.run checks the unholed deck, so the climb is restated here.

The holes, unless --hole names others:

  - one per canary in judges/canaries, guarding the canary's condition: the modes that keep
    today's Petra from passing that canary. A canary Petra passes gives a hole with no
    modes, already open, which the search exposes by re-finding a PASS of its kind and
    condition. Once P1 makes the canary fail, the modes that refuse it become its hole, so
    the harness needs no new list. A canary Petra's lowering rejects has no outcome to
    discharge, so it plants no hole; the report names it.
  - one per mode Petra checks on the kind's generated designs, guarding any condition: the
    strength and detailing modes the judge is silent on, found only when a design the judge
    rejects for some condition passes everything but that mode.

Writes docs/canary_recall.md and docs/canary_recall_log.jsonl. Tooling: deterministic for
a seed and budget.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for path in (ROOT, ROOT / "scripts"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import absurd_gap as A  # noqa: E402
from petra.models.steel.breaker import _move  # noqa: E402
from petra.registry import build_registry  # noqa: E402

KINDS = tuple(dict.fromkeys(A.SCHEDULE))
MOVE_TRIES = 20
"""Draws per evaluation before a climb gives up: a design none of whose lines the breaker
moves would otherwise loop for ever."""


@dataclass(frozen=True)
class Hole:
    name: str
    kind: str
    modes: frozenset[str]
    target: frozenset[str] | None     # the conditions that expose it; None: any the judge raises
    origin: str                       # "canary" | "mode" | "given"


def exposes(row: dict, hole: Hole) -> bool:
    ids = {v[0] for v in row["violations"]}
    judged = bool(ids) if hole.target is None else bool(ids & hole.target)
    return judged and A.holed_status(row, hole.modes) == "PASS" and (not hole.modes or row["status"] != "PASS")


def parse_hole(text: str) -> Hole:
    """"hanger:steel.edge_min+steel.clearance@steel.support_side.flange_width"."""
    kind, rest = text.split(":", 1)
    modes, _, target = rest.partition("@")
    if kind not in KINDS:
        raise argparse.ArgumentTypeError(f"{kind} is not a kind the generator draws: {', '.join(KINDS)}")
    return Hole(text, kind, frozenset(m for m in modes.split("+") if m), frozenset({target}) if target else None, "given")


def canary_holes(canary_rows: list[dict]) -> list[Hole]:
    return [Hole(c["name"], c["kind"], frozenset(c["refused"]), frozenset({c["condition"]}), "canary")
            for c in canary_rows if c["status"] != "REJECTED"]


def mode_holes(rows: dict[str, list[dict]]) -> list[Hole]:
    return [Hole(f"{kind}/{mode}", kind, frozenset({mode}), None, "mode")
            for kind in KINDS for mode in sorted({m for r in rows.get(kind, []) for m in r["checked"]})]


# --- The searches ---------------------------------------------------------------------------------


def indices(kind: str, budget: int) -> list[int]:
    """The first `budget` positions of the absurd-gap stream that draw `kind`."""
    period = [i for i, k in enumerate(A.SCHEDULE) if k == kind]
    return [cycle * len(A.SCHEDULE) + i for cycle in range(budget // len(period) + 1) for i in period][:budget]


def _design(job: tuple[int, int]) -> dict:
    seed, index = job
    return {**A.assess(A.sample(seed, index, A._REGISTRY), A._REGISTRY), "seed": seed}


def _score(row: dict, hole: Hole) -> float:
    """The judge as the breaker's oracle: utilisation 2 on each condition it raises that the
    hole guards, so the climb keeps a design the judge rejects."""
    ids = {v[0] for v in row["violations"]}
    return 2.0 if (ids if hole.target is None else ids & hole.target) else 0.0


def climb(hole: Hole, starts: list[dict], budget: int, seed: int) -> dict:
    """The breaker's climb on the holed deck from each start in turn, sharing `budget` Petra
    evaluations; stops at the first design that exposes the hole."""
    spent = 0
    for n, start in enumerate(starts):
        share = (budget - spent) // (len(starts) - n)
        rng = random.Random(f"recall:{seed}:{hole.name}:{start['index']}")
        text, best, used, tries = start["text"], _score(start, hole), 0, 0
        while used < share and tries < MOVE_TRIES * share:
            tries += 1
            moved = _move(text, rng)
            if moved is None or moved == text:
                continue
            used += 1
            row = A.assess(A.Sample(start["index"], hole.kind, "breaker", (), moved), A._REGISTRY)
            if exposes(row, hole):
                return {"found_by": "breaker", "after": spent + used, "start": start["index"], "status": row["status"],
                        "conditions": sorted({v[0] for v in row["violations"]}), "text": moved,
                        "hash": hashlib.sha256(moved.encode()).hexdigest()[:16]}
            if A.holed_status(row, hole.modes) == "PASS" and _score(row, hole) >= best:
                text, best = moved, _score(row, hole)
        spent += used
    return {"found_by": None, "after": spent}


def _climb(job: tuple[Hole, list[dict], int, int]) -> dict:
    return climb(*job)


def breaker_starts(hole: Hole, rows: list[dict], most: int = 4) -> list[dict]:
    """Up to `most` generated designs the holed deck passes: those the judge rejects for a
    guarded condition first, then for any, then the rest."""
    passing = [r for r in rows if A.holed_status(r, hole.modes) == "PASS"]
    rank = lambda r: (-_score(r, hole), not r["violations"], r["index"])
    return sorted(passing, key=rank)[:most]


def recall(seed: int, budget: int, workers: int, kinds: tuple[str, ...] = KINDS,
           given: tuple[Hole, ...] = ()) -> tuple[list[dict], dict]:
    """(one result per hole, timings and counts)."""
    started = time.time()
    jobs = [(seed, i) for kind in kinds for i in indices(kind, budget)]
    registry = build_registry()
    if workers <= 1:
        A._init()
        designs = [_design(job) for job in jobs]
    else:
        with Pool(workers, initializer=A._init) as pool:
            designs = pool.map(_design, jobs, chunksize=8)
    rows: dict[str, list[dict]] = defaultdict(list)
    for row in designs:
        rows[row["kind"]].append(row)
    canary_rows = [] if given else A.canaries(registry)
    holes = list(given) or [h for h in (*canary_holes(canary_rows), *mode_holes(rows)) if h.kind in kinds]
    generated = time.time()
    results = []
    for hole in holes:
        first = next(((n, r) for n, r in enumerate(rows[hole.kind], 1) if exposes(r, hole)), None)
        result = {"found_by": None, "after": len(rows[hole.kind])}
        if first is not None:
            n, r = first
            result = {"found_by": "generator", "after": n, "index": r["index"], "status": r["status"],
                      "conditions": sorted({v[0] for v in r["violations"]})}
        results.append(result)
    missed = [(i, h) for i, (h, r) in enumerate(zip(holes, results)) if r["found_by"] is None and h.kind in A.STEEL]
    climbs = [(h, breaker_starts(h, rows[h.kind]), budget, seed) for _, h in missed]
    if workers <= 1:
        climbed = [_climb(job) for job in climbs]
    else:
        with Pool(workers, initializer=A._init) as pool:
            climbed = pool.map(_climb, climbs, chunksize=1)
    for (i, hole), result in zip(missed, climbed):
        results[i] = {**result, "generator_after": results[i]["after"]}
    out = [{"hole": h.name, "kind": h.kind, "origin": h.origin, "modes": sorted(h.modes),
            "target": sorted(h.target) if h.target is not None else None, **r} for h, r in zip(holes, results)]
    stats = {"designs": len(designs), "generator_s": generated - started, "breaker_s": time.time() - generated,
             "climbs": len(climbs), "evaluations": sum(r["after"] for r in climbed),
             "canaries": {c["name"]: c["status"] for c in canary_rows}}
    return out, stats


# --- The report -----------------------------------------------------------------------------------


def _found(r: dict) -> str:
    if r["found_by"] == "generator":
        return f"generator, design {r['index']} ({r['after']} drawn)"
    if r["found_by"] == "breaker":
        return f"breaker from design {r['start']}, {r['after']} evaluations (`{r['hash']}`)"
    return "no"


def _codes(items) -> str:
    return ", ".join(f"`{x}`" for x in items) or "none"


def render(results: list[dict], stats: dict, args, wall: float, provenance: dict[str, str]) -> str:
    by_kind = defaultdict(lambda: defaultdict(list))
    for r in results:
        by_kind[r["kind"]][r["origin"]].append(r)
    out = [
        "# Canary recall",
        "",
        f"Generated by `python scripts/canary_recall.py --seed {args.seed} --budget {args.budget} --workers {args.workers}`"
        f"{''.join(f' --hole {h.name}' for h in args.hole)}, in {wall / 60:.1f} minutes of wall time. Do not edit by hand; "
        "re-run the script.",
        "",
        "| Measured | Last commit touching it |",
        "|---|---|",
        f"| Petra, `petra/` | {provenance['petra']} |",
        f"| The generator: `{'`, `'.join(A.GENERATOR)}` | {provenance['generator']} |",
        f"| This harness, `scripts/canary_recall.py` | {provenance['harness']} |",
        "",
        "A **hole** is a set of Petra's modes taken as discharged, the verdict of a deck that lacks those checks. A design "
        "**exposes** it when the holed Petra passes it, the judge rejects it for a condition the hole guards, and Petra "
        "itself does not pass it (or the hole has no modes, because today's Petra already lacks the check). **Recall** is "
        "holes exposed over holes planted, per kind and domain, with the generator drawing "
        f"{args.budget} designs of each kind from seed {args.seed}'s stream and the steel breaker climbing "
        f"{args.budget} Petra evaluations on each steel hole the generator missed. `scripts/canary_recall.py` says how "
        "the holes are chosen.",
        "",
        "## Recall per kind and domain",
        "",
        "**Canary holes** guard a canary's condition with the modes that refuse that canary today; P1's predicate reads "
        "this column. **Mode holes** take out one mode Petra checks on the kind and count a find under any condition the "
        "judge raises: the judge has no condition of its own for these modes, so a find needs a design it rejects for "
        "another reason that passes everything but the mode.",
        "",
        "| Kind | Canary holes | Exposed | Recall | Mode holes | Exposed | Recall |",
        "|---|---|---|---|---|---|---|",
    ]
    totals = defaultdict(int)
    for kind in KINDS:
        if kind not in by_kind:
            continue
        cells = []
        for origin in ("canary", "mode"):
            mine = by_kind[kind][origin] + (by_kind[kind]["given"] if origin == "canary" else [])
            hit = sum(r["found_by"] is not None for r in mine)
            totals[origin] += len(mine)
            totals[origin + "_hit"] += hit
            cells += [str(len(mine)), str(hit), f"{100 * hit / len(mine):.0f}%" if mine else "n/a"]
        out.append(f"| {kind} | {' | '.join(cells)} |")
    share = lambda o: f"{100 * totals[o + '_hit'] / totals[o]:.0f}%" if totals[o] else "n/a"
    out += [f"| **all** | {totals['canary']} | {totals['canary_hit']} | **{share('canary')}** | {totals['mode']} | "
            f"{totals['mode_hit']} | {share('mode')} |", ""]
    out += ["## Canary holes", "",
            "| Canary | Kind | Condition | Petra today | Hole: modes discharged | Exposed by |", "|---|---|---|---|---|---|"]
    for r in results:
        if r["origin"] == "mode":
            continue
        target = _codes(r["target"]) if r["target"] is not None else "any"
        today = stats["canaries"].get(r["hole"], "")
        modes = _codes(r["modes"]) if r["modes"] else "none (already open)"
        out.append(f"| `{r['hole']}` | {r['kind']} | {target} | {today} | {modes} | {_found(r)} |")
    rejected = sorted(name for name, status in stats["canaries"].items() if status == "REJECTED")
    out += ["", f"Canaries Petra's lowering rejects, which leave no outcome to discharge and so plant no hole: "
                f"{_codes(rejected)}."]
    out += ["", "## Mode holes", "", "| Kind | Exposed | Not exposed |", "|---|---|---|"]
    for kind in KINDS:
        mine = by_kind[kind]["mode"] if kind in by_kind else []
        if not mine:
            continue
        hit = [r["modes"][0] for r in mine if r["found_by"] is not None]
        miss = [r["modes"][0] for r in mine if r["found_by"] is None]
        out.append(f"| {kind} | {_codes(hit)} | {_codes(miss)} |")
    out += ["", "## Cost", "",
            f"{stats['designs']} generated designs in {stats['generator_s'] / 60:.1f} minutes; {stats['climbs']} breaker "
            f"climbs, {stats['evaluations']} Petra evaluations, in {stats['breaker_s'] / 60:.1f} minutes. Every hole, and the "
            "text of every design the breaker found, is in `docs/canary_recall_log.jsonl`; `python scripts/absurd_gap.py "
            f"--seeds {args.seed} --show INDEX` prints a generated one.", ""]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="measure canary recall with holes planted in Petra")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--budget", type=int, default=600, help="designs per kind, and breaker evaluations per hole")
    parser.add_argument("--workers", type=int, default=7)
    parser.add_argument("--hole", type=parse_hole, action="append", default=[],
                        help="KIND:MODE[+MODE...][@CONDITION], in place of the default holes; repeatable")
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    args = parser.parse_args(argv)
    started = time.time()
    results, stats = recall(args.seed, args.budget, args.workers, given=tuple(args.hole))
    wall = time.time() - started
    provenance = {"petra": A.commit(("petra",)), "generator": A.commit(A.GENERATOR),
                  "harness": A.commit(("scripts/canary_recall.py",))}
    args.out.mkdir(parents=True, exist_ok=True)
    report = render(results, stats, args, wall, provenance)
    (args.out / "canary_recall.md").write_text(report, encoding="utf-8", newline="\n")
    lines = [json.dumps(r, sort_keys=True) for r in results]
    (args.out / "canary_recall_log.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(report.split("## Canary holes", 1)[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
