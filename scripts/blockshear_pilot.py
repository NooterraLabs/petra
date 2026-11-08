"""The block shear pilot (docs/plan.md §6 P8, docs/blockshear_pilot.md):
`python scripts/blockshear_pilot.py [--contact bearing|confined] [--all] [--log FILE]`, or
`python scripts/blockshear_pilot.py --point ROWS COLS S G LEV LEH [--grade G] [--flow fy|fu FACTOR]`
for the kernel's verdict on one plate.

Sweeps the box below in order. At each geometry one linear program gives the plate's
lower-bound limit load per unit flow stress, so every grade's load factor follows from it.
At the first point where J4.3's force exceeds the lower bound at Fy, the kernel checks a
Farkas refutation, the run prints the premise J4.3 rests on there, and the kernel proves
the bound at the smallest flow stress on LADDER that carries J4.3's force. Points before
it are proved by the kernel at Fy. With --all the sweep goes on, without certificates,
and prints every point. Untrusted tooling: every verdict it prints is the kernel's.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from fractions import Fraction as Q
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from petra.kernel import Evidence, Refutation, Theorem, check  # noqa: E402
from petra.models.steel import blockshear as B  # noqa: E402
from petra.models.steel import blockshear_solve as S  # noqa: E402
from petra.registry import build_registry  # noqa: E402

IN = B.INCH
KSI = 6894757.293168361
"""Pa per ksi, for printing only."""

BOX = {
    "grade": ("A36", "A992", "A572_50"),
    "cols": (1, 2),
    "rows": (2, 4),
    "pitch": (Q(9, 4), Q(3)),
    "gauge": (Q(9, 4), Q(3)),
    "lev": (Q(5, 4), Q(2)),
    "leh": (Q(5, 4), Q(2)),
}
"""The box, lengths in inches: 3/4 in bolts in standard holes, every combination. Gauge
varies only with two columns. Thickness drops out: the statement is per unit thickness."""

BOLT = "bolt_us.3_4"
MARGIN = Q(2)
DISC = B.Discretization(rings=1, cell=Q(1), box=Q(3, 4))
LADDER = (Q(1), Q(6, 5), Q(7, 5), Q(8, 5), Q(9, 5), Q(2), Q(5, 2), Q(3))
"""Flow stresses, as multiples of Fu, at which the run tries to prove J4.3's force."""
PROOF_MARGIN = 1.001
"""A load factor the program must clear before the run rounds its field into a proof."""


def geometries():
    for cols in BOX["cols"]:
        for rows in BOX["rows"]:
            for pitch in BOX["pitch"]:
                for gauge in (BOX["gauge"] if cols > 1 else BOX["gauge"][:1]):
                    for lev in BOX["lev"]:
                        for leh in BOX["leh"]:
                            yield dict(rows=rows, cols=cols, pitch=pitch, gauge=gauge, lev=lev, leh=leh)


def plate(geometry: dict, grade: str) -> B.Plate:
    g = geometry
    return B.Plate(g["rows"], g["cols"], g["pitch"] * IN, g["gauge"] * IN, g["lev"] * IN, g["leh"] * IN, MARGIN * IN, grade, BOLT)


def describe(geometry: dict, grade: str) -> str:
    g = geometry
    gauge = f" g {float(g['gauge']):g}" if g["cols"] > 1 else ""
    return (f"{grade:7s} {g['rows']}x{g['cols']} s {float(g['pitch']):g}{gauge} Lev {float(g['lev']):g} "
            f"Leh {float(g['leh']):g}")


def unit_bound(geometry: dict, registry, contact: str) -> float:
    """The lower-bound load per unit flow stress (inches), from one Airy program."""
    pilot = B.statement(plate(geometry, BOX["grade"][1]), registry, DISC, B.Flow("fy", Q(1)), contact)
    bound = S.airy_program(pilot, S.airy(pilot))
    return bound.factor * float(pilot.claim.force) / float(pilot.claim.fy)


def verdict(result) -> str:
    if isinstance(result, (Theorem, Refutation)):
        return f"{type(result).__name__} {result.rule}, footprint {sorted(result.labels)}"
    return f"Rejection: {result.reason}"


def prove(p: B.Plate, registry, flow: B.Flow, contact: str, margin: float = PROOF_MARGIN):
    pilot = B.statement(p, registry, DISC, flow, contact)
    field = S.airy(pilot)
    bound = S.airy_program(pilot, field)
    if bound.factor < margin:
        return bound.factor, None
    points = S.feasible_points(pilot, field, bound.z)
    return bound.factor, (None if points is None else check(pilot.statement, Evidence(points)))


def refute(p: B.Plate, registry, contact: str, flow: B.Flow = B.Flow("fy", Q(1))):
    pilot = B.statement(p, registry, DISC, flow, contact)
    bound = S.statement_program(pilot)
    return bound.factor, check(pilot.statement, Evidence(S.farkas_ray(pilot, bound.y)))


def one_point(args, registry) -> int:
    """--point: the kernel's verdict on one plate at one flow stress. It tries a proof when
    the Airy program clears J4.3's force at all, and a refutation otherwise."""
    rows, cols, pitch, gauge, lev, leh = args.point
    geometry = dict(rows=int(rows), cols=int(cols), pitch=Q(pitch), gauge=Q(gauge), lev=Q(lev), leh=Q(leh))
    p = plate(geometry, args.grade)
    flow = B.Flow(args.flow[0], Q(args.flow[1]))
    lam, result = prove(p, registry, flow, args.contact, margin=1)
    if result is None and lam < 1:
        lam, result = refute(p, registry, args.contact, flow)
    shown = verdict(result) if result is not None else "no proof: the rounded field left the yield surface"
    print(f"{describe(geometry, args.grade)}, flow stress {flow.factor} {flow.prop}, contact {args.contact}: "
          f"program {lam:.4f}, kernel: {shown}", flush=True)
    return 0


def premise(p: B.Plate, registry, claim: B.Claim, unit: float, contact: str) -> list[str]:
    """What J4.3's force needs at this point that the statement does not give."""
    mesh = B.build_mesh(p, registry, DISC)
    n = p.rows * p.cols
    force = float(claim.force)
    lines = []
    b = claim.governing
    terms = ("0.6 Fu Anv + Ubs Fu Ant" if claim.branch == "rupture" else "0.6 Fy Agv + Ubs Fu Ant")
    lines.append(f"J4.3 block of {b.k} row(s) and {b.j} column(s) governs, branch {claim.branch} ({terms}), "
                 f"Ubs {b.ubs}: {force / KSI:.1f} kip per inch of thickness")
    cap = n * 2 / 3 ** 0.5 * float(claim.fy) * float(mesh.width)
    if contact == "bearing":
        lines.append(f"plane-stress bearing cap n (2/sqrt 3) Fy w = {cap / KSI:.1f} kip/in "
                     f"({'below' if cap < force else 'above'} J4.3's force)")
    required = force / unit
    lines.append(f"flow stress J4.3 needs from this mesh: {required / KSI:.1f} ksi = "
                 f"{required / float(claim.fy):.2f} Fy = {required / float(claim.fu):.2f} Fu")
    if contact == "bearing" and cap < force:
        lines.append("premise: each bolt bears on the plate above 2/sqrt 3 Fy over the hole's width, past "
                     "plane stress at Fy; J4.3 rests on J3.11's confined bearing (2.4 d t Fu) and strain hardening")
    elif required > float(claim.fu):
        lines.append("premise: a flow stress above Fu; J4.3 rests on more than strain hardening to Fu")
    else:
        lines.append("premise: strain hardening to the flow stress above, at or below Fu")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="the block shear pilot")
    parser.add_argument("--contact", choices=B.CONTACTS, default="bearing")
    parser.add_argument("--all", action="store_true", help="sweep the whole box, without certificates past the first counterexample")
    parser.add_argument("--log", type=Path, help="write one JSON line per point")
    parser.add_argument("--point", nargs=6, metavar=("ROWS", "COLS", "S", "G", "LEV", "LEH"),
                        help="check one plate instead of sweeping the box, lengths in inches as fractions")
    parser.add_argument("--grade", default="A36", help="the grade for --point")
    parser.add_argument("--flow", nargs=2, metavar=("PROP", "FACTOR"), default=("fy", "1"),
                        help="the flow stress for --point: fy or fu, times a fraction")
    args = parser.parse_args(argv)
    registry = build_registry()
    if args.point:
        return one_point(args, registry)
    print(f"box: {', '.join(f'{k} {[str(v) for v in vals]}' for k, vals in BOX.items())}; bolts {BOLT}, "
          f"standard holes, margin {MARGIN} in, contact {args.contact}", flush=True)
    print(f"model premise: model:{B.MODEL.id}@{B.MODEL.source_hash}", flush=True)
    log = args.log.open("w", encoding="utf-8") if args.log else None
    found = False
    for geometry in geometries():
        start = time.time()
        unit = unit_bound(geometry, registry, args.contact)
        for grade in BOX["grade"]:
            p = plate(geometry, grade)
            claim = B.j4_3(p, registry)
            j311 = B.bearing(p, registry)
            factor = float(claim.fy) * unit / float(claim.force)
            row = dict(point=describe(geometry, grade), factor=round(factor, 4), j43_kip_per_in=round(float(claim.force) / KSI, 2),
                       block=[claim.governing.k, claim.governing.j], branch=claim.branch,
                       j43_governs=claim.force <= j311, need_fu=round(float(claim.force) / unit / float(claim.fu), 3))
            line = (f"{row['point']}: LB/J4.3 at Fy {factor:.3f}, J4.3 {row['j43_kip_per_in']:.1f} kip/in "
                    f"block {claim.governing.k}x{claim.governing.j} {claim.branch}, "
                    f"{'J4.3 governs J3.11' if row['j43_governs'] else 'J3.11 governs'}, needs {row['need_fu']:.2f} Fu "
                    f"({time.time() - start:.0f} s)")
            if not found:
                if factor >= 1:
                    lam, result = prove(p, registry, B.Flow("fy", Q(1)), args.contact)
                    line += f"\n  kernel at Fy: {verdict(result) if result is not None else f'no proof (program {lam:.4f})'}"
                else:
                    found = True
                    lam, result = refute(p, registry, args.contact)
                    line += (f"\n  FIRST COUNTEREXAMPLE in the box: J4.3 exceeds the lower bound at Fy "
                             f"(statement program {lam:.4f})\n  kernel at Fy: {verdict(result)}")
                    for text in premise(p, registry, claim, unit, args.contact):
                        line += f"\n  {text}"
                    need = float(claim.force) / unit / float(claim.fu)
                    for c in LADDER:
                        if float(c) > need * PROOF_MARGIN:
                            lam, result = prove(p, registry, B.Flow("fu", c), args.contact)
                            shown = verdict(result) if result is not None else f"no proof (program {lam:.4f})"
                            line += f"\n  kernel at flow stress {c} Fu: {shown}"
                            break
                    else:
                        line += f"\n  no flow stress on the ladder up to {LADDER[-1]} Fu carries J4.3's force"
            print(line, flush=True)
            if log:
                log.write(json.dumps(row) + "\n")
                log.flush()
            if found and not args.all:
                return 0
    if not found:
        print("the kernel proved J4.3's force at most the lower bound at every point of the box (a grid of points)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
