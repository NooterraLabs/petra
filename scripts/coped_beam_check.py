"""Published coped-beam block shear tests against AISC 360-22 Eq. J4-5 and P8's plane-stress
lower bound (docs/coped_beam_check.md). Untrusted tooling: it reads the extracted numbers in
docs/coped_beam_tests.json and changes no verdict.

    python scripts/coped_beam_check.py solve [--only ID ...]
        J4.3 and the 1999 LRFD rule for every specimen, and P8's lower bound in bearing and
        confined contact for every specimen P8's mesh holds. Writes
        docs/coped_beam_check_log.jsonl, or updates the named specimens' lines with --only.
    python scripts/coped_beam_check.py report
        The tables docs/coped_beam_check.md quotes, from the data file and the log.

J4.3 is Eq. J4-5 at the measured Fy, Fu and dimensions, with no resistance factor, on the
block the tests tore out: the shear plane down the inner line from the cope edge to the
bottom bolt, the tension plane from there to the beam end. Holes take B4.3b's 1/16 in
allowance. Ubs is 1 for one line and the registry's nonuniform value for two (Commentary
Fig. C-J4.2). The log also keeps the steel deck's value, the least over the blocks of the
first k rows and first j lines with every bolt taking an equal share, which is never higher.

The lower bound is P8's statement and solver, unchanged (petra/models/steel/blockshear.py,
blockshear_solve.py), on P8's mesh and margin (scripts/blockshear_pilot.py). A small
registry view hands it the specimen's measured Fy, Fu and hole. P8's plate is a full
rectangular group of round holes, so specimens with a missing bolt, slotted holes or a
bottom cope get no bound.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
import time
from dataclasses import dataclass
from fractions import Fraction as Q
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scipy import stats  # noqa: E402

from petra.models.steel import blockshear as B  # noqa: E402
from petra.models.steel import blockshear_solve as S  # noqa: E402
from petra.registry import build_registry  # noqa: E402
from petra.units import CUSTOMARY  # noqa: E402

DATA = ROOT / "docs" / "coped_beam_tests.json"
LOG = ROOT / "docs" / "coped_beam_check_log.jsonl"


def _pilot():
    spec = importlib.util.spec_from_file_location("blockshear_pilot", ROOT / "scripts" / "blockshear_pilot.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PILOT = _pilot()
INCH = B.INCH
KSI = CUSTOMARY["ksi"][0]
KIP = CUSTOMARY["kip"][0]
UNITS = {
    "SI": dict(length=Q(1, 1000), stress=Q(10**6), force=Q(1000)),
    "US": dict(length=INCH, stress=KSI, force=KIP),
}
"""Each data row's units, to metres, pascals and newtons, exactly."""


def exact(value) -> Q:
    return Q(str(value))


@dataclass(frozen=True)
class Specimen:
    """One test, lengths in metres, stresses in pascals, the load in newtons, all exact.
    `holes` holds (line, row) for every hole, line 1 nearest the beam end and row 1 below
    the cope; every hole holds a bolt. `slot` is a horizontal slot's length, else None."""

    id: str
    source: str
    lines: int
    rows: int
    pitches: tuple[Q, ...]
    gauge: Q
    lev: Q
    leh: Q
    hole: Q
    slot: Q | None
    bolt: Q
    t: Q
    fy: Q
    fu: Q
    load: Q
    holes: frozenset
    block_shear: bool
    mode: str
    bottom_cope: bool

    @property
    def rectangular(self) -> bool:
        return self.holes == frozenset((j, r) for j in range(1, self.lines + 1) for r in range(1, self.rows + 1))

    @property
    def meshable(self) -> bool:
        """P8's plate holds it: a full rectangular group of round holes, one free end edge."""
        return self.rectangular and self.slot is None and not self.bottom_cope


def specimen(row: dict) -> Specimen:
    u = UNITS[row["units"]]
    length = lambda v: exact(v) * u["length"]  # noqa: E731
    rows = len(row["pitches"]) + 1
    lines = row["lines"]
    holes = row.get("holes") or [list(range(1, rows + 1))] * lines
    return Specimen(
        row["id"], row["source"], lines, rows, tuple(length(p) for p in row["pitches"]),
        length(row["gauge"]) if row["gauge"] is not None else Q(0), length(row["lev"]), length(row["leh"]),
        length(row["hole"]), length(row["slot"]) if row.get("slot") else None, length(row["bolt"]),
        length(row["t"]), exact(row["fy"]) * u["stress"], exact(row["fu"]) * u["stress"],
        exact(row["load"]) * u["force"], frozenset((j + 1, r) for j, line in enumerate(holes) for r in line),
        row["block_shear"], row["mode"], "bottom_cope" in row)


def load_data(path: Path = DATA) -> tuple[dict, list[Specimen]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data, [specimen(row) for row in data["specimens"]]


# --- J4.3 -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Constants:
    shear: Q
    allowance: Q
    ubs_nonuniform: Q


def constants(registry) -> Constants:
    return Constants(*(B.constant(registry, name) for name in
                       ("aisc360.j4_3.shear", "aisc360.b4_3b.hole_allowance", "aisc360.j4_3.ubs_nonuniform")))


@dataclass(frozen=True)
class Block:
    """J4.3 for the block of the first k rows and the first j lines, in newtons for the
    specimen's thickness. `force` is the connection load at which this block reaches Rn
    when every bolt takes an equal share."""

    k: int
    j: int
    agv: Q
    anv: Q
    ant: Q
    ubs: Q
    rupture: Q
    yield_: Q
    force: Q

    @property
    def branch(self) -> str:
        return "rupture" if self.rupture <= self.yield_ else "yield"


def blocks(sp: Specimen, c: Constants) -> list[Block]:
    """Every block whose corner is a hole: the shear plane runs down line j from the cope edge
    to row k, the tension plane from there to the beam end."""
    shear_hole = sp.hole + c.allowance
    tension_hole = (sp.slot or sp.hole) + c.allowance
    found = []
    for k in range(1, sp.rows + 1):
        for j in range(1, sp.lines + 1):
            if (j, k) not in sp.holes:
                continue
            agv = sp.lev + sum(sp.pitches[:k - 1], Q(0))
            above = sum(1 for r in range(1, k) if (j, r) in sp.holes)
            anv = agv - (above + Q(1, 2)) * shear_hole
            crossed = sum(1 for i in range(1, j) if (i, k) in sp.holes)
            ant = sp.leh + (j - 1) * sp.gauge - (crossed + Q(1, 2)) * tension_hole
            ubs = Q(1) if j == 1 else c.ubs_nonuniform
            rupture = (c.shear * sp.fu * anv + ubs * sp.fu * ant) * sp.t
            yield_ = (c.shear * sp.fy * agv + ubs * sp.fu * ant) * sp.t
            share = Q(len(sp.holes), sum(1 for (i, r) in sp.holes if i <= j and r <= k))
            found.append(Block(k, j, agv * sp.t, anv * sp.t, ant * sp.t, ubs, rupture, yield_, min(rupture, yield_) * share))
    return found


def j4_3(sp: Specimen, c: Constants) -> tuple[Block, Block]:
    """The governing block and the whole-group block (all rows, all lines)."""
    found = blocks(sp, c)
    governing = min(found, key=lambda b: (b.force, b.k, b.j))
    whole = next(b for b in found if (b.k, b.j) == (sp.rows, sp.lines))
    return governing, whole


def lrfd1999(sp: Specimen, c: Constants) -> Q:
    """The 1999 LRFD rule Kulak and Grondin (2001) reviewed, on the whole-group block, with no
    Ubs: if Fu Ant >= 0.6 Fu Anv, 0.6 Fy Agv + Fu Ant, else 0.6 Fu Anv + Fy Agt, at most
    0.6 Fu Anv + Fu Ant. Used only to compare this extraction with their published means."""
    _, whole = j4_3(sp, c)
    tension = whole.ant * sp.fu
    shear = c.shear * whole.anv * sp.fu
    agt = (sp.leh + (sp.lines - 1) * sp.gauge) * sp.t
    rn = c.shear * sp.fy * whole.agv + tension if tension >= shear else shear + sp.fy * agt
    return min(rn, shear + tension)


# --- P8's lower bound -----------------------------------------------------------------------


def _fixed(value: Q) -> SimpleNamespace:
    return SimpleNamespace(value=SimpleNamespace(lo=value, hi=value))


class Measured:
    """The registry as P8's model reads it, with the grade "specimen" at the measured Fy and
    Fu and the bolt "specimen" in the measured hole."""

    def __init__(self, registry, sp: Specimen):
        self.constants = {**registry.constants, "specimen.std": _fixed(sp.hole), "specimen.d": _fixed(sp.bolt)}
        self._steel = {"fy": sp.fy, "fu": sp.fu}

    def property(self, entry: str, prop: str) -> SimpleNamespace:
        if entry != "steel.specimen":
            raise KeyError(entry)
        return _fixed(self._steel[prop])


def plate(sp: Specimen) -> B.Plate:
    """P8's plate. As-built pitches differ by a fraction of a millimetre, so the plate takes
    their mean, which keeps the whole block's gross shear length."""
    pitch = sum(sp.pitches, Q(0)) / len(sp.pitches)
    return B.Plate(sp.rows, sp.lines, pitch, sp.gauge, sp.lev, sp.leh, PILOT.MARGIN * INCH, "specimen", "specimen")


def unit_bound(sp: Specimen, registry, contact: str) -> tuple[float, B.Claim]:
    """P8's lower-bound load per unit flow stress and unit thickness (inches), and P8's own
    J4.3 claim for the plate, from one Airy program."""
    view = Measured(registry, sp)
    pilot = B.statement(plate(sp), view, PILOT.DISC, B.Flow("fy", Q(1)), contact)
    bound = S.airy_program(pilot, S.airy(pilot))
    return bound.factor * float(pilot.claim.force) / float(pilot.claim.fy), pilot.claim


def newtons_of_unit(unit: float, sp: Specimen, flow: Q) -> float:
    """A unit bound (inches) as newtons at flow stress `flow` for the specimen's thickness."""
    return unit * float(INCH) * float(sp.t) * float(flow)


# --- solve and report -----------------------------------------------------------------------


def solve_one(sp: Specimen, registry, c: Constants) -> dict:
    governing, whole = j4_3(sp, c)
    row = dict(
        id=sp.id, source=sp.source, block_shear=sp.block_shear, lines=sp.lines, rows=sp.rows,
        ubs=str(whole.ubs), test_kN=round(float(sp.load) / 1000, 2),
        j43_kN=round(float(whole.force) / 1000, 2), j43_branch=whole.branch,
        deck_kN=round(float(governing.force) / 1000, 2), deck_block=[governing.k, governing.j],
        lrfd1999_kN=round(float(lrfd1999(sp, c)) / 1000, 2),
    )
    if not sp.meshable:
        row["bound"] = None
        return row
    row["bound"] = {}
    for contact in B.CONTACTS:
        start = time.time()
        unit, claim = unit_bound(sp, registry, contact)
        row["bound"][contact] = dict(unit_in=round(unit, 5), at_fy_kN=round(newtons_of_unit(unit, sp, sp.fy) / 1000, 2),
                                     seconds=round(time.time() - start, 1))
        row["p8_claim_kN"] = round(float(claim.force) * float(INCH) * float(sp.t) / 1000, 2)
    return row


def solve(args) -> int:
    registry = build_registry()
    c = constants(registry)
    _, specimens = load_data()
    chosen = [sp for sp in specimens if not args.only or sp.id in args.only]
    kept = {}
    if args.only and LOG.exists():
        kept = {json.loads(line)["id"]: line for line in LOG.read_text(encoding="utf-8").splitlines()}
    for sp in chosen:
        row = solve_one(sp, registry, c)
        kept[sp.id] = json.dumps(row)
        print(json.dumps(row), flush=True)
    order = [sp.id for sp in specimens if sp.id in kept]
    LOG.write_text("".join(kept[i] + "\n" for i in order), encoding="utf-8")
    return 0


def _r(x: float, places: int = 2) -> str:
    return f"{x:.{places}f}"


def summary(ratios: list[float]) -> dict:
    """Count below 1.0, its one-sided 95 percent Clopper-Pearson upper bound as a fraction,
    and the mean with its one-sided 95 percent t lower bound."""
    n = len(ratios)
    below = sum(1 for r in ratios if r < 1)
    upper = 1.0 if below == n else float(stats.beta.ppf(0.95, below + 1, n - below))
    mean = sum(ratios) / n
    sd = math.sqrt(sum((r - mean) ** 2 for r in ratios) / (n - 1)) if n > 1 else float("nan")
    low = mean - float(stats.t.ppf(0.95, n - 1)) * sd / math.sqrt(n) if n > 1 else float("nan")
    return dict(n=n, below=below, upper=upper, mean=mean, cov=sd / mean, low=low, min=min(ratios))


def report(args) -> int:
    data, specimens = load_data()
    by_id = {sp.id: sp for sp in specimens}
    rows = {json.loads(line)["id"]: json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines()}
    raw = {r["id"]: r for r in data["specimens"]}
    failed = [sp for sp in specimens if sp.block_shear]
    other = [sp for sp in specimens if not sp.block_shear]

    def ratio(sp: Specimen, key: str = "j43_kN") -> float:
        return rows[sp.id]["test_kN"] / rows[sp.id][key]

    print("### Specimens\n")
    print("| Specimen | Source | Lines x rows | t (mm) | Fy (MPa) | Fu (MPa) | Lev (mm) | Leh (mm) | s (mm) | g (mm) | Hole (mm) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for sp in specimens:
        mm = lambda v: _r(float(v) * 1000, 1)  # noqa: E731
        pitch = "/".join(mm(p) for p in sp.pitches)
        bolts = f"{sp.lines} x {sp.rows}" + ("" if sp.rectangular else f", {len(sp.holes)} bolts")
        hole = mm(sp.hole) + (f" x {mm(sp.slot)} slot" if sp.slot else "") + ("" if raw[sp.id]["hole_measured"] else " (std)")
        print(f"| {sp.id} | {sp.source} | {bolts} | {_r(float(sp.t) * 1000)} | {_r(float(sp.fy) / 1e6, 0)} | "
              f"{_r(float(sp.fu) / 1e6, 0)} | {mm(sp.lev)} | {mm(sp.leh)} | {pitch} | {mm(sp.gauge) if sp.lines > 1 else ''} | {hole} |")

    print("\n### Copes and failures\n")
    print("| Specimen | Bolt (mm) | Cope, length x depth (mm) | End rotation (deg) | Block shear | Failure reported |")
    print("|---|---|---|---|---|---|")
    for sp in specimens:
        r = raw[sp.id]
        mm = lambda v: "not given" if v is None else _r(float(exact(v) * UNITS[r["units"]]["length"]) * 1000, 1)  # noqa: E731
        cope = f"{mm(r['cope_length'])} x {mm(r['cope_depth'])}" + (", top and bottom" if sp.bottom_cope else "")
        print(f"| {sp.id} | {mm(r['bolt'])} | {cope} | {'not given' if r['rotation_deg'] is None else r['rotation_deg']} | {'yes' if sp.block_shear else 'no'} | {r['mode']} |")

    print("\n### Block shear failures\n")
    print("| Specimen | Ubs | Test (kN) | J4.3 (kN) | Test / J4.3 | Bound at Fy (kN) | Test / bound | J4.3 / bound | Test / confined bound |")
    print("|---|---|---|---|---|---|---|---|---|")
    for sp in failed:
        row = rows[sp.id]
        bound = row["bound"]
        if bound:
            lb, conf = bound["bearing"]["at_fy_kN"], bound["confined"]["at_fy_kN"]
            tail = f"{_r(lb, 1)} | {_r(row['test_kN'] / lb)} | {_r(row['j43_kN'] / lb)} | {_r(row['test_kN'] / conf)}"
        else:
            tail = "not meshed | | | "
        print(f"| {sp.id} | {row['ubs']} | {_r(row['test_kN'], 1)} | {_r(row['j43_kN'], 1)} | {_r(ratio(sp), 3)} | {tail} |")

    print("\n### Other failures\n")
    print("| Specimen | Test (kN) | J4.3 (kN) | Test / J4.3 | Bound at Fy (kN) | Failure |")
    print("|---|---|---|---|---|---|")
    for sp in other:
        row = rows[sp.id]
        lb = _r(row["bound"]["bearing"]["at_fy_kN"], 1) if row["bound"] else "not meshed"
        print(f"| {sp.id} | {_r(row['test_kN'], 1)} | {_r(row['j43_kN'], 1)} | {_r(ratio(sp), 3)} | {lb} | {raw[sp.id]['mode']} |")

    print("\n### Test over J4.3\n")
    print("| Group | Specimens | Below 1.0 | 95% upper bound on the share below 1.0 | Mean | CoV | 95% lower bound on the mean | Least |")
    print("|---|---|---|---|---|---|---|---|")
    groups = [("one line, Ubs = 1", [sp for sp in failed if sp.lines == 1]),
              ("two lines, Ubs = 0.5", [sp for sp in failed if sp.lines == 2]),
              ("all", failed)]
    for name, group in groups:
        s = summary([ratio(sp) for sp in group])
        print(f"| {name} | {s['n']} | {s['below']} | {_r(s['upper'])} | {_r(s['mean'])} | {_r(s['cov'])} | {_r(s['low'])} | {_r(s['min'], 3)} |")

    print("\n### Test over J4.3 under other readings, and over the 1999 rule\n")
    print("| Rule | One line, below 1.0 | One line, mean | Two lines, below 1.0 | Two lines, mean | All, below 1.0 | All, mean |")
    print("|---|---|---|---|---|---|---|")
    c = constants(build_registry())
    bare = Constants(c.shear, Q(0), c.ubs_nonuniform)
    readings = [("J4.3, whole block, B4.3b allowance (the tables above)", lambda sp: j4_3(sp, c)[1].force),
                ("J4.3, whole block, no allowance", lambda sp: j4_3(sp, bare)[1].force),
                ("J4.3, the deck's least block, B4.3b allowance", lambda sp: j4_3(sp, c)[0].force),
                ("the 1999 LRFD rule, no Ubs, whole block", lambda sp: lrfd1999(sp, c))]
    for name, force in readings:
        cells = []
        for group in ([sp for sp in failed if sp.lines == 1], [sp for sp in failed if sp.lines == 2], failed):
            values = [float(sp.load / force(sp)) for sp in group]
            cells += [f"{sum(1 for v in values if v < 1)} of {len(values)}", _r(sum(values) / len(values))]
        print(f"| {name} | {' | '.join(cells)} |")

    print("\n### Test over P8's bound\n")
    print("| Group | Specimens | Test / bound | J4.3 / bound | Test / confined bound | Test / bound at Fu |")
    print("|---|---|---|---|---|---|")
    for name, group in groups:
        meshed = [sp for sp in group if rows[sp.id]["bound"]]
        bearing = lambda sp: rows[sp.id]["bound"]["bearing"]["at_fy_kN"]  # noqa: E731
        columns = [[rows[sp.id]["test_kN"] / bearing(sp) for sp in meshed],
                   [rows[sp.id]["j43_kN"] / bearing(sp) for sp in meshed],
                   [rows[sp.id]["test_kN"] / rows[sp.id]["bound"]["confined"]["at_fy_kN"] for sp in meshed],
                   [rows[sp.id]["test_kN"] / (bearing(sp) * float(sp.fu / sp.fy)) for sp in meshed]]
        spans = " | ".join(f"{_r(min(v))} to {_r(max(v))}" for v in columns)
        print(f"| {name} | {len(meshed)} | {spans} |")

    print("\n### Extraction check against published means of the 1999 LRFD rule\n")
    print("| Family | Specimens here | Mean here | Published | Where |")
    print("|---|---|---|---|---|")
    for check in data["checks"]["lrfd1999_mean_test_over_predicted"]:
        group = [sp for sp in specimens if sp.source == check["family"] and (sp.block_shear or check["family"] == "SER244")]
        here = [ratio(sp, "lrfd1999_kN") for sp in group]
        spread = f", CoV {check['cov']}" if "cov" in check else (f", sd {check['sd']}" if "sd" in check else "")
        print(f"| {check['family']} | {len(group)} | {_r(sum(here) / len(here))} | {check['n']} test{'s' if check['n'] != 1 else ''}, mean {check['mean']}{spread} | {check['where']} |")

    print("\n### Ricles and Yura, J4.3 here and on the IDEA page\n")
    print("| Specimen | J4.3 here (kip) | IDEA P_AISC (kip) |")
    print("|---|---|---|")
    for sid, theirs in data["checks"]["idea_aisc_kip"]["values"].items():
        print(f"| {sid} | {_r(rows[sid]['j43_kN'] * 1000 / float(KIP), 1)} | {theirs} |")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="coped-beam block shear tests against J4.3 and P8's lower bound")
    sub = parser.add_subparsers(dest="command", required=True)
    p_solve = sub.add_parser("solve", help="compute every specimen and write the log")
    p_solve.add_argument("--only", nargs="+", help="specimen ids to recompute; the rest of the log is kept")
    sub.add_parser("report", help="print the doc's tables from the data file and the log")
    args = parser.parse_args(argv)
    return {"solve": solve, "report": report}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
