"""Which registry values Petra's checks read: `py -3.11 scripts/registry_footprint.py [--check]`.

Checks a corpus of designs with the solvers and records, for every registry key that some
verdict's footprint names ("reg:<key>"), the first design whose verdict rests on it. The
corpus, in order:

  - every design under examples/;
  - the first STEEL designs of the steel gate's stream (petra/models/steel/generate.py),
    cyclic designs among them, and the first ELECTRONICS of the electronics stream;
  - generated tasks (bench/tasks.py) for GYM_SEEDS seeds of each domain, each hole filled in
    turn with each of its choices and the other holes with their first;
  - each steel example, and each design of the steel stream, again in the other design basis.

Writes docs/sources/footprint.json. tests/test_sources.py holds every registry key to be
live or listed in UNUSED with what reads it and why no check does, and fails when a listed
key is live. A key is live when the footprint names it, or when it is a row of a CATALOGUES
table or an environment, and the footprint names the same property of another row: a
design that names the row reads it the same way. --check exits 1 when the committed file
differs from what the corpus gives; it took 17 minutes on four busy cores (measured).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bench import tasks  # noqa: E402
from petra.files import read_pair  # noqa: E402
from petra.lang import load_design, parse_design  # noqa: E402
from petra.models.electronics import generate as electronics  # noqa: E402
from petra.models.steel import generate as steel  # noqa: E402
from petra.pipeline import check_design  # noqa: E402
from petra.registry import build_registry, catalog  # noqa: E402
from petra.registry.model import Registry, Stated  # noqa: E402
from petra.solvers import SolverSource  # noqa: E402

OUT = ROOT / "docs" / "sources" / "footprint.json"
STEEL = (110, 1)
ELECTRONICS = (60, 7)
"""(designs, seed) of each generated stream."""
GYM_SEEDS = 16

CATALOGUES = (
    "bolt.", "bolt_group.", "cable.", "electrode.", "insert.", "led.", "mcb.", "polymer.", "process.mill.",
    "process.powder.", "process.print.", "process.sheet.", "reg.", "res.", "screw.", "steel.", "terminal.",
    "const.aisc_shapes_v16.", "const.bolt_us.", "const.en10219_2.", "const.iec60063.E24.", "const.iec60063.E96.",
    "const.iec60227_3.", "const.iec60228.", "const.iso261.", "const.shop_deck.plate.",
)
"""Tables whose rows a check reads by the row a design names: "const.bolt_us.7_8.std" is
one size's standard hole, read the way every size's is."""

ENVIRONMENTS = frozenset(catalog.environments())
"""The environment ids, whose rows a check reads by the one a design names."""


class Unused(NamedTuple):
    reader: str
    """The file that reads the value, or "" when nothing does."""
    needle: str
    """Text the reader holds where it reads the value. The test fails when it goes."""
    why: str


_CONSISTENCY = "petra/registry/consistency.py"
_STEEL_REGISTRY = "petra/registry/steel.py"
_CHECKS = "petra/models/steel/checks.py"
_FATIGUE = "petra/models/steel/fatigue.py"
_PARTS = "petra/models/parts/build.py"
_PARTS_ENGINE = "petra/models/parts/engine.py"
_NO_SCREW = "fit.fastener and the thread's engagement read it; no corpus design has a screw"
_NO_INSERT = "fit.insert reads it; no corpus design has a heat-set insert"
_NO_FINISH = "a finish's rows; no corpus design names a finish"
_NO_POWDER = "a powder bed's rows; no corpus design is sintered"
_NO_SHEET = "a sheet cutter's rows; no corpus design is cut from sheet"
_GALVANIC = Unused("petra/coverage.py", '.get("anodic_index")',
                   "coverage reads it to decide whether a contact pair is a galvanic mode; no check reads it")

UNUSED: dict[str, Unused] = {
    # Read outside the checks: lowering, coverage or a size's fixed parameters record no premise.
    "const.shop_deck.plate.*": Unused("petra/models/steel/lower.py", "_stocked(",
                                      "lowering rejects a fixed plate thickness the shop does not stock"),
    "res.*.r_min": Unused("petra/models/electronics/board.py", '"r_min"',
                          "lowering rejects a resistance outside the series range"),
    "res.*.r_max": Unused("petra/models/electronics/board.py", '"r_max"',
                          "lowering rejects a resistance outside the series range"),
    "res.*.steps": Unused("petra/models/electronics/board.py", '"steps"',
                          "lowering rejects a resistance that is not a value of the series' E series"),
    "const.iec60228.*.area": Unused("petra/models/circuit.py", "part.fixes",
                                    "a cable size fixes its area as a design value, so a check's premise is the size"),
    "const.iec60227_3.*.insulation": Unused("petra/models/circuit.py", "part.fixes",
                                            "a cable size fixes its insulation as a design value, so a check's "
                                            "premise is the size"),
    "aluminium.6061_T6.anodic_index": _GALVANIC,
    "bolt_group.*.anodic_index": _GALVANIC,
    "brass.insert.anodic_index": _GALVANIC,
    "copper.cu_etp.anodic_index": _GALVANIC,
    "electrode.*.anodic_index": _GALVANIC,
    "stainless.A4.anodic_index": _GALVANIC,
    "steel.*.anodic_index": _GALVANIC,
    "zinc.electroplate.anodic_index": _GALVANIC,
    # Read only by the registry's consistency relations (tests/test_registry_consistency.py).
    "bolt.*.Rm_min": Unused(_CONSISTENCY, '"bolt.yield_order"',
                            "the joint checks take Sp, or Rp02_min where the class states no Sp"),
    "const.iso898_1.8_8.yield_ratio": Unused(_CONSISTENCY, '"bolt.class_ratio"',
                                             "sets the class_yield_ratio that bolt.class_ratio holds against "
                                             "Rp02_min / Rm_min; no check reads the ratio"),
    "const.iso898_1.10_9.yield_ratio": Unused(_CONSISTENCY, '"bolt.class_ratio"',
                                              "sets the class_yield_ratio that bolt.class_ratio holds against "
                                              "Rp02_min / Rm_min; no check reads the ratio"),
    "const.iec60898_1.nontrip_factor": Unused(_CONSISTENCY, '"breaker.conventional_non_tripping"',
                                              "sets the breaker's I_nt, which no check reads"),
    "bolt_group.*.fu": Unused(_STEEL_REGISTRY, '"bolt_group.tensile_ratio"',
                              "the relations hold Fnt, Fnv and Tm against it; the checks read Fnt and Fnv"),
    "const.aisc_shapes_v16.*.w": Unused(_STEEL_REGISTRY, '"shape.weight"',
                                        "shape.weight holds it against density times A; no check takes a "
                                        "member's self-weight from it"),
    "const.steel.nu": Unused(_CONSISTENCY, '"material.shear_modulus"',
                             "sets the shear modulus G, which no check reads; the cope's buckling takes "
                             "aisc360.nu"),
    "const.aluminium.E": Unused(_CONSISTENCY, '"material.shear_modulus"',
                                "the bolted joint reads no property of its plates, and the truss takes steel"),
    "const.aluminium.nu": Unused(_CONSISTENCY, '"material.shear_modulus"',
                                 "the bolted joint reads no property of its plates, and the truss takes steel"),
    "aluminium.6061_T6.fy": Unused(_CONSISTENCY, '"material.yield_order"',
                                   "the bolted joint reads no property of its plates, and the truss takes steel"),
    "aluminium.6061_T6.fu": Unused(_CONSISTENCY, '"material.yield_order"',
                                   "the bolted joint reads no property of its plates, and the truss takes steel"),
    # Read by nothing.
    "polymer.*.tg": Unused("", "", "part.temperature takes the heat deflection temperature, and no rule reads a glass "
                                   "transition"),
    "const.aluminium.density": Unused("", "", "the bolted joint reads no property of its plates, and the truss "
                                              "takes steel"),
    # Read by a check on a branch no corpus design reaches.
    "const.aisc360.j3_5.c2_lsl": Unused(_CHECKS, '"aisc360.j3_5.c2_lsl"',
                                        "the edge distance of a long-slotted hole; no corpus design has one at an "
                                        "edge"),
    "const.bolt_us.*.c2_ovs": Unused(_CHECKS, '.c2_ovs"',
                                     "the edge distance of an oversized hole; no corpus design has one at an edge"),
    "const.rcsc2025.s5_4.hf_two": Unused(_CHECKS, '"rcsc2025.s5_4.hf_',
                                         "the slip factor for two or more fillers; no corpus design has two"),
    "const.rcsc2025.s5_4.phi_lsl": Unused(_CHECKS, '"_lsl"',
                                          "slip resistance with long slots; no slip-critical corpus design has them"),
    "const.rcsc2025.s5_4.omega_lsl": Unused(_CHECKS, '"_lsl"',
                                            "slip resistance with long slots; no slip-critical corpus design has them"),
    "const.aisc360.j10_5.omega": Unused(_CHECKS, '"aisc360.j10_5"',
                                        "web compression buckling in ASD; no ASD verdict of the corpus rests on it, "
                                        "since a FAIL rests on its failing check alone"),
    "const.aisc360.j3_10.ksc_asd": Unused(_CHECKS, '"aisc360.j3_10.ksc_asd"',
                                          "slip resistance with a tension in ASD; no ASD verdict of the corpus rests "
                                          "on a slip-critical joint in tension"),
    "const.aisc360.app3.a3_7_thread": Unused(_FATIGUE, '"a3_7_thread"',
                                             "fatigue of bolts in tension; no cyclic corpus design loads its bolts "
                                             "in tension"),
    "const.aisc360.app3.s3_4_share": Unused(_FATIGUE, '"s3_4_share"',
                                            "fatigue of bolts in tension; no cyclic corpus design loads its bolts "
                                            "in tension"),
    "const.aisc360.app3.cat_g.cf": Unused(_FATIGUE, '"cat_{category}.cf"',
                                          "category G is bolts in tension; no cyclic corpus design loads its bolts "
                                          "in tension"),
    "const.aisc360.app3.cat_g.fth": Unused(_FATIGUE, '"cat_{category}.fth"',
                                           "category G is bolts in tension; no cyclic corpus design loads its "
                                           "bolts in tension"),
    "const.bolt_us.*.tpi": Unused(_FATIGUE, '.tpi"',
                                  "fatigue of bolts in tension; no cyclic corpus design loads its bolts in tension. "
                                  "bolt.pretension_g120 and _g150 in petra/registry/steel.py read it too"),
    # The parts deck's rows, read on branches the two parts examples, a printed tray and a
    # board dropped into it, do not reach.
    "const.parts.engagement.form": Unused(_PARTS, 'sb.constant(f"parts.engagement.{last.role}")',
                                          "a screw's least engagement in a formed hole; no corpus design has a screw"),
    "const.parts.engagement.tap": Unused(_PARTS, 'sb.constant(f"parts.engagement.{last.role}")',
                                         "a screw's least engagement in a tapped hole; no corpus design has a screw"),
    "const.parts.engagement.insert": Unused(_PARTS, 'sb.constant("parts.engagement.insert")',
                                            "a screw's least engagement in an insert; no corpus design has one"),
    "screw.*.d": Unused(_PARTS, 'sb.registry(f.screw, "d")', _NO_SCREW),
    "screw.*.thread_d": Unused(_PARTS, 'sb.registry(f.screw, "thread_d")', _NO_SCREW),
    "screw.*.pitch": Unused(_PARTS, 'sb.registry(f.screw, "pitch")', _NO_SCREW),
    "screw.*.head_d": Unused(_PARTS, 'sb.registry(f.screw, "head_d")', _NO_SCREW),
    "screw.*.mass": Unused(_PARTS, 'sb.registry(f.screw, "mass")', _NO_SCREW),
    "screw.*.head_h": Unused(_PARTS_ENGINE, 'props["head_h"]',
                             "the engine places the head by it and no check premises it; no corpus design has a screw"),
    "screw.*.length": Unused(_PARTS_ENGINE, 'props["length"]',
                             "the engine places the tip by it and no check premises it; no corpus design has a screw"),
    "screw.*.csk_angle": Unused(_PARTS_ENGINE, '"csk_angle" in props',
                                "its presence marks a countersunk head, and no check reads the angle"),
    "insert.*.thread_d": Unused(_PARTS, 'sb.registry(last.insert, "thread_d")', _NO_INSERT),
    "insert.*.hole_min": Unused(_PARTS, 'sb.registry(hole.insert, "hole_min")', _NO_INSERT),
    "insert.*.hole_max": Unused(_PARTS, 'sb.registry(hole.insert, "hole_max")', _NO_INSERT),
    "insert.*.length": Unused(_PARTS, 'sb.registry(hole.insert, "length")', _NO_INSERT),
    "insert.*.wall_min": Unused(_PARTS, 'sb.registry(hole.insert, "wall_min")', _NO_INSERT),
    "insert.*.mass": Unused(_PARTS, 'sb.registry(h.insert, "mass")', _NO_INSERT),
    "process.anodize_ii.buildup": Unused(_PARTS, 'sb.registry(part.finish, "buildup")', _NO_FINISH),
    "process.anodize_ii.density": Unused(_PARTS, 'sb.registry(part.finish, "density")', _NO_FINISH),
    "process.powder_coat.buildup": Unused(_PARTS, 'sb.registry(part.finish, "buildup")', _NO_FINISH),
    "process.powder_coat.density": Unused(_PARTS, 'sb.registry(part.finish, "density")', _NO_FINISH),
    "process.mill.*.tolerance": Unused(_PARTS, 'sb.registry(part.preset, "tolerance")',
                                       "a milled part's profile tolerance; no corpus design is milled"),
    "process.powder.*.build_x": Unused(_PARTS, "sb.registry(part.preset, row)", _NO_POWDER),
    "process.powder.*.build_y": Unused(_PARTS, "sb.registry(part.preset, row)", _NO_POWDER),
    "process.powder.*.build_z": Unused(_PARTS, "sb.registry(part.preset, row)", _NO_POWDER),
    "process.powder.*.hole_shrink": Unused(_PARTS, 'sb.registry(part.preset, "hole_shrink")', _NO_POWDER),
    "process.powder.*.tolerance": Unused(_PARTS, 'sb.registry(part.preset, "tolerance")', _NO_POWDER),
    "process.powder.*.tolerance_rate": Unused(_PARTS, 'sb.registry(part.preset, "tolerance_rate")', _NO_POWDER),
    "process.print.*.bridge": Unused(_PARTS, 'sb.registry(part.preset, "bridge")',
                                     "print.bridge reads it for a face over air; the corpus's printed tray has none"),
    "process.print.*.hole_shrink": Unused(_PARTS, 'sb.registry(part.preset, "hole_shrink")',
                                          "a printed hole's shrink; no corpus design prints a modelled hole"),
    "process.sheet.*.bed_x": Unused(_PARTS, "sb.registry(part.preset, row)", _NO_SHEET),
    "process.sheet.*.bed_y": Unused(_PARTS, "sb.registry(part.preset, row)", _NO_SHEET),
    "process.sheet.*.thickness": Unused(_PARTS, 'sb.registry(part.preset, "thickness")', _NO_SHEET),
    "process.sheet.*.tolerance": Unused(_PARTS, 'sb.registry(part.preset, "tolerance")', _NO_SHEET),
}
"""A registry key, or a family as family() writes it, -> what reads it and why no check
does. Every entry is a finding: a value no check rests on, or a branch no corpus design
reaches."""


def keys(registry: Registry) -> list[str]:
    """Every registry key: each constant, and each stated property of an entry, whether in its
    props or a field of its own (an environment's ambient)."""
    out = [f"const.{name}" for name in registry.constants]
    for table in (registry.materials, registry.parts, registry.processes, registry.environments):
        for eid, entry in table.items():
            fields = {f.name: getattr(entry, f.name) for f in dataclasses.fields(entry)}
            props = {**fields, **getattr(entry, "props", {})}
            out += [f"{eid}.{prop}" for prop, v in props.items() if isinstance(v, Stated)]
    return sorted(set(out))


def family(key: str) -> str:
    """The key with its catalogue row left out ("const.bolt_us.*.std"), or the key itself.
    The environments are one table too: "marine_c5.ambient" is in "<environment>.ambient"."""
    head, dot, prop = key.partition(".")
    if head in ENVIRONMENTS:
        return f"<environment>{dot}{prop}"
    for table in CATALOGUES:
        if key.startswith(table):
            _, dot, prop = key[len(table):].partition(".")
            return f"{table}*{dot}{prop}"
    return key


def live(every: list[str], read: dict[str, str]) -> set[str]:
    """The keys the footprint names, and the catalogue rows whose property it names."""
    families = {family(k) for k in read}
    return {k for k in every if k in read or family(k) in families}


def unused(key: str) -> Unused | None:
    """Why no check reads key, if UNUSED lists it or its family."""
    return UNUSED.get(key) or UNUSED.get(family(key))


def read_by(design, name: str, registry: Registry) -> set[str]:
    """The registry keys the verdicts of one design rest on; `design` is a path, read with
    the card beside it, or the texts (card, design)."""
    if isinstance(design, Path):
        lowered = load_design(design, registry)
    else:
        lowered = parse_design(*design, f"{name}.petra", registry)
    body = check_design(lowered, registry, (SolverSource(),), path=f"{name}.petra").to_json()
    return {p["label"][len("reg:"):] for v in body["verdicts"] for p in v["footprint"] if p["label"].startswith("reg:")}


def gym(registry: Registry):
    for domain in sorted(tasks.GENERATORS):
        for seed in range(GYM_SEEDS):
            task = tasks.generate(domain, seed, registry)
            first = {h.name: h.choices[0] for h in task.holes}
            done = set()
            for hole in task.holes:
                for choice in hole.choices:
                    pick = {**first, hole.name: choice}
                    if tuple(sorted(pick.items())) not in done:
                        done.add(tuple(sorted(pick.items())))
                        yield f"{task.id} {hole.name}={choice}", (task.card, tasks.fill(task, pick))


def corpus(registry: Registry):
    """(name, design path or the texts (card, design)) of every corpus design, in order."""
    for path in sorted(ROOT.glob("examples/**/*.petra")):
        yield path.relative_to(ROOT).as_posix(), path
    for g in steel.generate(*STEEL, registry):
        yield g.name, (g.card, g.text)
    for g in electronics.generate(*ELECTRONICS, registry):
        yield g.name, electronics.render(g)
    yield from tail(registry)


def other_basis(text: str) -> str:
    """A steel design checked by ASD instead of LRFD, or by LRFD instead of ASD."""
    return text.replace("basis lrfd", "basis asd") if "basis lrfd" in text else text.replace("basis asd", "basis lrfd")


def tail(registry: Registry):
    """The corpus after the generated streams: the gym tasks, then the steel examples and the
    steel stream in the other design basis."""
    yield from gym(registry)
    for path in sorted(ROOT.glob("examples/steel/*.petra")):
        card, text = read_pair(path)
        yield f"{path.relative_to(ROOT).as_posix()} in the other basis", (card, other_basis(text))
    for g in steel.generate(*STEEL, registry):
        yield f"{g.name} in the other basis", (g.card, other_basis(g.text))


def footprint(registry: Registry, log=None, designs=None) -> dict:
    read: dict[str, str] = {}
    count = 0
    for name, design in designs if designs is not None else corpus(registry):
        count += 1
        for key in sorted(read_by(design, name, registry)):
            read.setdefault(key, name)
        if log:
            log(f"{count:4d} {name}: {len(read)} keys read")
    return {"corpus": {"designs": count, "steel": {"designs": STEEL[0], "seed": STEEL[1]},
                       "electronics": {"designs": ELECTRONICS[0], "seed": ELECTRONICS[1]},
                       "gym seeds": GYM_SEEDS},
            "read": dict(sorted(read.items()))}


def render(found: dict) -> str:
    return json.dumps(found, indent=1) + "\n"


def read(path: Path = OUT) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the committed file is stale")
    args = parser.parse_args(argv)
    registry = build_registry()
    text = render(footprint(registry, log=lambda line: print(line, flush=True)))
    if args.check:
        stale = OUT.read_text(encoding="utf-8") != text
        print(f"{OUT.relative_to(ROOT)} is {'stale' if stale else 'current'}")
        return 1 if stale else 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    every = keys(build_registry())
    found = json.loads(text)["read"]
    print(f"wrote {OUT.relative_to(ROOT)}: {len(found)} of {len(every)} registry keys read, "
          f"{len(live(every, found))} live")
    return 0


if __name__ == "__main__":
    sys.exit(main())
