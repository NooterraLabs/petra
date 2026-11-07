"""The absurd-design gap (docs/plan.md P0 item 2): `python scripts/absurd_gap.py [--n 20000]
[--seed 1] [--workers 7] [--out docs]`, or `--seed S --show INDEX` to print one design.

Generates designs across the eleven steel kinds, the circuit and the truss, mutated along
the dimensions that decide whether parts fit: rows, pitch, top, edge distances, gauges,
setback, beam and support swaps, web or flange, copes, angle and tee swaps, conductor size
against terminal, truss span and load scale. Checks each design with Petra and with the
outside judge (judges/), and writes docs/absurd_gap.md and docs/absurd_gap_log.jsonl. The
canaries in judges/canaries run every time. The gap is the designs the judge finds
unbuildable that Petra passes; P1 drives it to zero.

Tooling: deterministic for a seed, since design i draws from its own stream "seed:i".
Steel designs start from the deck's own samplers (petra/models/steel/generate.py) or from
the examples, so their loads are drawn here, not sized by the deck.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from fractions import Fraction
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from judges import CONDITIONS, judge  # noqa: E402
from judges.steel import UNDRAWN  # noqa: E402
from petra.lang import LolaSyntaxError, LoweringError, parse_design  # noqa: E402
from petra.models.base import ComponentError  # noqa: E402
from petra.models.steel import generate as G  # noqa: E402
from petra.pipeline import check_design  # noqa: E402
from petra.registry import build_registry  # noqa: E402
from petra.solvers import SolverSource  # noqa: E402
from petra.verdict import STATUS  # noqa: E402

STEEL = tuple(G.SAMPLERS)
SCHEDULE = (*STEEL, "circuit", "truss", *STEEL, "circuit", "circuit")
"""Design i is of kind SCHEDULE[i % 26]: every steel kind twice, the circuit three times and
the truss once per 26, the first 13 covering every kind."""

CANARIES = ROOT / "judges" / "canaries"
EXAMPLES = ROOT / "examples"
SHAPES = json.loads((ROOT / "petra" / "registry" / "aisc_shapes.json").read_text(encoding="utf-8"))
W_SHAPES = tuple(r["label"].replace("X", "x").replace(".", "_") for r in SHAPES["W"])
ANGLES = tuple(a.replace("X", "x").replace("-", "_").replace("/", "_") for a in SHAPES["L"])
"""Shapes come from the shipped table, so the stream is the same with or without the full
workbook named by PETRA_SHAPES_XLSX."""

LENGTHS = {
    "pitch": ("2.5", "3", "4", "6"),
    "top": ("0.5", "1", "1.5", "2", "3", "4", "6", "10", "16", "24"),
    "edge_vertical": ("1", "1.25", "1.5", "2", "3"),
    "support_gauge": ("2.5", "3.5", "5.5", "7.5", "10", "14"),
    "beam_gauge": ("1.5", "2", "2.5", "3.5"),
    "gauge": ("3", "4", "5.5", "8", "10", "14"),
    "tee_gauge": ("3.5", "4", "5.5", "8", "10", "14"),
    "seat_length": ("4", "6", "8", "12", "16"),
    "setback": ("0.25", "0.5", "1", "2", "4", "6"),
    "bolt_line": ("1.5", "2", "3", "6", "9"),
    "beam_edge": ("1.25", "1.75", "2.5", "4", "6"),
    "plate_width": ("6", "8", "10", "12", "16"),
    "weld_return": ("1", "2", "4", "8", "12"),
    "stiffener_width": ("3", "4", "6", "8"),
    "bearing_length": ("0.5", "4", "10", "24"),
}
COPED = ("shear_tab", "double_angle", "single_angle", "shear_tee", "shear_end_plate")
MUTATIONS = (0, 1, 1, 2, 2, 3)
"""How many mutations a design gets; 0 leaves the sampler's or example's design as drawn, a
control on the judge."""


@dataclass(frozen=True)
class Sample:
    index: int
    kind: str
    origin: str               # "sampler" | "example" | "canary"
    mutations: tuple[str, ...]
    text: str


class Lines:
    """A component block's attribute lines as [key, rest] pairs."""

    def __init__(self, raw: list[str]):
        self.items = [line.strip().split(" ", 1) for line in raw if line.strip()]

    def get(self, key: str) -> str | None:
        return next((rest for k, rest in self.items if k == key), None)

    def set(self, key: str, rest: str) -> None:
        for item in self.items:
            if item[0] == key:
                item[1] = rest
                return
        self.items.append([key, rest])

    def render(self) -> list[str]:
        return [f"  {k} {rest}" for k, rest in self.items]


def _example_lines(kind: str) -> list[str]:
    lines = (EXAMPLES / "steel" / f"{kind}.petra").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(f"{kind} ") and line.rstrip().endswith("{"))
    block = lines[start + 1:lines.index("}", start)]
    return [line for line in block if line.strip() and not line.strip().startswith("basis")]


def _mutate(kind: str, lines: Lines, rng: random.Random) -> str | None:
    ops = [k for k in LENGTHS if lines.get(k) is not None]
    ops += [k for k in ("rows", "beam", "support", "angle", "angles", "tee") if lines.get(k) is not None]
    ops += ["face"] if lines.get("support") is not None and kind != "hanger" else []
    ops += ["columns"] if kind == "bolt_bracket" else []
    ops += ["cope"] if kind in COPED else []
    op = rng.choice(ops)
    if op in LENGTHS:
        value = rng.choice(LENGTHS[op])
        lines.set(op, f"{value} inch")
        return f"{op}={value}"
    if op == "rows":
        n = rng.randint(2, 12)
        lines.set("rows", str(n))
        return f"rows={n}"
    if op == "columns":
        n = rng.choice((1, 2, 3, 4))
        lines.set("columns", str(n))
        return f"columns={n}"
    if op == "beam":
        shape = rng.choice(W_SHAPES)
        lines.set("beam", f"{shape} {lines.get('beam').split(' ', 1)[1]}")
        return f"beam={shape}"
    if op in ("support", "face"):
        shape, face, rest = lines.get("support").split(" ", 2)
        if op == "support":
            shape = rng.choice(W_SHAPES)
        if op == "face" or kind != "hanger" and rng.random() < 0.5:
            face = "web" if face == "flange" else "flange"
        lines.set("support", f"{shape} {face} {rest}")
        return f"support={shape} {face}"
    if op in ("angle", "angles"):
        _, rest = lines.get(op).split(" ", 1)
        shape = rng.choice(ANGLES)
        if rng.random() < 0.5:
            rest = rest.replace("outstanding long", "outstanding @").replace("outstanding short", "outstanding long")
            rest = rest.replace("outstanding @", "outstanding short")
        lines.set(op, f"{shape} {rest}")
        return f"{op}={shape} {rest.rsplit(' ', 1)[1]}"
    if op == "tee":
        parent = rng.choice([w for w in W_SHAPES if int(w[1:].split("x")[0]) % 2 == 0])
        depth, weight = parent[1:].split("x")
        half = Fraction(weight.replace("_", ".")) / 2
        tee = f"WT{int(depth) // 2}x{half.numerator if half.denominator == 1 else str(float(half)).replace('.', '_')}"
        lines.set("tee", f"{tee} {lines.get('tee').split(' ', 1)[1]}")
        return f"tee={tee}"
    depth, length = rng.choice(("1", "2", "4")), rng.choice(("3", "4", "6", "9"))
    both = rng.random() < 0.3
    lines.set("cope", f"{'both' if both else 'top'} depth {depth} inch length {length} inch")
    if kind != "shear_end_plate" and lines.get("setback") is None:
        lines.set("setback", "0.5 inch")
    return f"cope={'both' if both else 'top'} {depth}x{length}"


def _steel(index: int, kind: str, rng: random.Random, registry) -> Sample:
    secondary: tuple = ()
    if rng.random() < 0.75:
        s = G._Sampler(rng, registry)
        G.SAMPLERS[kind](s)
        lines, origin, secondary = Lines(s.lines), "sampler", tuple(s.secondary)
    else:
        lines, origin = Lines(_example_lines(kind)), "example"
    labels = tuple(_mutate(kind, lines, rng) for _ in range(rng.choice(MUTATIONS)))
    top = 200 if kind == "flange_force" else 40
    load = G._load(math.exp(rng.uniform(0, math.log(top))))
    basis = rng.choice(("lrfd", "asd"))
    text = G.source(f"absurd-{index:05d}", kind, basis, lines.render(), load, secondary)
    return Sample(index, kind, origin, labels, text)


CIRCUIT = """petra 0

design "absurd-{index:05d}" {{
  owner "gate@petra.dev"
  environment indoor_dry
}}

ambient in [10 degC, 40 degC] signed "gate@petra.dev" source "absurd gap generator"

circuit lighting {{
  supply mains voltage 230 V fault_current in [0 kA, 6 kA] signed "gate@petra.dev" source "absurd gap generator"
  breaker cb1 part {breaker}
  wire w1 cable {cable} length {length} m install install.clipped_direct
  terminal t1 part {terminal}
  consumer lamps

  connect mains.out -> cb1.in
  connect cb1.out -> w1.a
  connect w1.b -> t1.wire
  connect t1.out -> lamps.in
}}

load lamp_draw {{
  on lighting.lamps current in [0 A, {current} A]
  signed "gate@petra.dev" source "absurd gap generator"
}}

claim hot:  lighting.w1.temperature <= 70 degC under lamp_draw
claim drop: lighting.w1.voltage_drop <= 3 % under lamp_draw
"""


def _circuit(index: int, rng: random.Random, registry) -> Sample:
    parts = sorted(registry.parts)
    choices = {
        "cable": [p for p in parts if p.startswith("cable.cu_pvc_")],
        "terminal": [p for p in parts if p.startswith("terminal.")],
        "breaker": [p for p in parts if p.startswith("mcb.")],
        "length": ["5", "10", "18", "30", "60"],
        "current": ["2", "6", "10", "16", "25"],
    }
    fields = {"cable": "cable.cu_pvc_2_5", "terminal": "terminal.lever_4mm2_75C", "breaker": "mcb.B10", "length": "18",
              "current": "10"}
    labels = []
    for field in rng.sample(sorted(choices), rng.choice(MUTATIONS)):
        fields[field] = rng.choice(choices[field])
        labels.append(f"{field}={fields[field]}")
    return Sample(index, "circuit", "example", tuple(labels), CIRCUIT.format(index=index, **fields))


TRUSS = """petra 0

design "absurd-{index:05d}" {{
  owner "gate@petra.dev"
  environment indoor_dry
}}

truss frame {{
  material steel.S355
  section {section}

  node A at (0 m, 0 m) support pinned
  node B at ({b} m, 0 m)
  node C at ({c} m, 0 m) support roller_x
  node D at ({d} m, {h} m)
  node E at ({e} m, {h} m)

  member bottom_ab: A -- B
  member bottom_bc: B -- C
  member top_de:    D -- E section {top}
  member diag_ad:   A -- D
  member diag_db:   D -- B
  member diag_be:   B -- E
  member diag_ec:   E -- C
}}

load crowd {{
  on frame.D fy in [{lo} N, {hi} N]
  on frame.E fy in [{lo} N, {hi} N]
  signed "gate@petra.dev" source "absurd gap generator"
}}

claim strength:   frame.collapse_factor >= 1.5 under crowd
claim stability:  frame.stability_factor >= 3 under crowd
claim stress:     frame.member(diag_ad).stress <= 235 MPa under crowd
"""


def _decimal(x: Fraction) -> str:
    return f"{float(x):.10g}" if x.denominator != 1 else str(x.numerator)


def _truss(index: int, rng: random.Random, registry) -> Sample:
    """The two-panel Warren truss of examples/truss_pass.petra, its span scaled and its loads
    scaled, sections swapped. Scaled coordinates stay exact (halves of whole metres)."""
    sections = sorted(p for p in registry.parts if p.startswith("chs."))
    fields = {"span": 1, "load": Fraction(1), "section": "chs.60_3x3_2", "top": "chs.76_1x3_2"}
    choices = {"span": (1, 2, 5, 10, 20, 50, 100, 200),
               "load": tuple(Fraction(1, 10**k) for k in range(6)),
               "section": sections, "top": sections}
    labels = []
    for field in rng.sample(sorted(choices), rng.choice(MUTATIONS)):
        fields[field] = rng.choice(choices[field])
        labels.append(f"{field}={fields[field] if field != 'load' else _decimal(fields[field])}")
    k, f = fields["span"], fields["load"]
    text = TRUSS.format(index=index, section=fields["section"], top=fields["top"],
                        b=_decimal(Fraction(3 * k)), c=_decimal(Fraction(6 * k)), d=_decimal(Fraction(3 * k, 2)),
                        e=_decimal(Fraction(9 * k, 2)), h=_decimal(Fraction(2 * k)),
                        lo=_decimal(-24000 * f), hi=_decimal(-16000 * f))
    return Sample(index, "truss", "example", tuple(labels), text)


def sample(seed: int, index: int, registry) -> Sample:
    rng = random.Random(f"{seed}:{index}")
    kind = SCHEDULE[index % len(SCHEDULE)]
    if kind == "circuit":
        return _circuit(index, rng, registry)
    if kind == "truss":
        return _truss(index, rng, registry)
    return _steel(index, kind, rng, registry)


def assess(s: Sample, registry) -> dict:
    """Petra's verdict and the judge's findings for one design."""
    start = time.perf_counter()
    status, note, violations, undecided = "PASS", None, [], []
    try:
        design = parse_design(s.text, f"{s.kind}.petra", registry)
    except (LolaSyntaxError, LoweringError) as e:
        design, status, note = None, "REJECTED", str(e).splitlines()[0][:200]
    if design is not None:
        found = judge(design, registry)
        violations = [[v.id, v.reason] for v in found.violations]
        undecided = list(found.undecided)
        try:
            status = STATUS[type(check_design(design, registry, (SolverSource(),)).verdict)]
        except ComponentError as e:
            status, note = "REJECTED", e.problems[0][:200]
    return {**asdict(s), "mutations": list(s.mutations), "status": status, "note": note, "violations": violations,
            "undecided": undecided, "seconds": time.perf_counter() - start}


_REGISTRY = None


def _init() -> None:
    global _REGISTRY
    _REGISTRY = build_registry()


def chunk(job: tuple[int, int, int]) -> list[dict]:
    seed, start, count = job
    return [assess(sample(seed, i, _REGISTRY), _REGISTRY) for i in range(start, start + count)]


def run(seed: int, n: int, workers: int, step: int = 26) -> list[dict]:
    jobs = [(seed, i, min(step, n - i)) for i in range(0, n, step)]
    if workers <= 1:
        _init()
        return [row for job in jobs for row in chunk(job)]
    rows: list[dict] = []
    started = time.time()
    with Pool(workers, initializer=_init) as pool:
        for done, part in enumerate(pool.imap(chunk, jobs), 1):
            rows.extend(part)
            if done % 40 == 0:
                print(f"{len(rows)} designs, {time.time() - started:.0f} s", flush=True)
    return rows


def canaries(registry) -> list[dict]:
    out = []
    for i, path in enumerate(sorted(CANARIES.glob("*.petra"))):
        text = path.read_text(encoding="utf-8")
        condition = next(line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("# violates:"))
        design = parse_design(text, path.name, registry)
        kind = next(iter(design.components.values())).kind
        row = assess(Sample(-1 - i, kind, "canary", (), text), registry)
        out.append({**row, "name": path.stem, "condition": condition})
    return out


# --- The report ----------------------------------------------------------------------------------


def _summary(rows: list[dict]):
    kinds = list(dict.fromkeys(SCHEDULE))
    per_kind = {k: Counter() for k in kinds}
    cells: dict[tuple[str, str], dict] = {}
    for row in rows:
        c = per_kind[row["kind"]]
        c["generated"] += 1
        c[row["status"]] += 1
        ids = sorted({v[0] for v in row["violations"]})
        if ids:
            c["judged"] += 1
            c["gap"] += row["status"] == "PASS"
        if not row["mutations"] and ids:
            c["control_judged"] += 1
            c["control_gap"] += row["status"] == "PASS"
        if not row["mutations"]:
            c["control"] += 1
        for cid in ids:
            cell = cells.setdefault((row["kind"], cid), {"judged": 0, "pass": 0, "example": None, "first": None})
            cell["judged"] += 1
            cell["first"] = cell["first"] or row
            if row["status"] == "PASS":
                cell["pass"] += 1
                cell["example"] = cell["example"] or row
    return kinds, per_kind, cells


def refound(canary: dict, rows: list[dict]) -> bool:
    return any(r["kind"] == canary["kind"] and r["status"] == "PASS" and any(v[0] == canary["condition"] for v in r["violations"])
               for r in rows)


def _reason(row: dict, cid: str) -> str:
    return next(v[1] for v in row["violations"] if v[0] == cid)


def render(rows: list[dict], canary_rows: list[dict], args, wall: float, commit: str) -> str:
    kinds, per_kind, cells = _summary(rows)
    total = Counter()
    for c in per_kind.values():
        total.update(c)
    seconds = defaultdict(float)
    for row in rows:
        seconds[row["kind"]] += row["seconds"]
    out = [
        "# The absurd-design gap",
        "",
        f"Generated by `python scripts/absurd_gap.py --n {args.n} --seed {args.seed} --workers {args.workers}` at commit "
        f"`{commit}`, in {wall / 60:.1f} minutes of wall time. Do not edit by hand; re-run the script.",
        "",
        "Each design is a sample from the steel deck's own samplers (`petra/models/steel/generate.py`) or an example, "
        "mutated 0 to 3 times along the dimensions that decide whether parts fit, with its load drawn log-uniform "
        "(1 to 40 kip, 1 to 200 kip for flange_force), so most strength checks pass and fit is what is tested. Petra checks "
        "it (`check_design`, the solvers as evidence), and the outside judge in `judges/` reads it. **Judged** means the "
        "judge finds at least one violated condition. **Gap** means judged and Petra PASS: a design Petra certifies that "
        "cannot be built as drawn, or is unsafe for a reason Petra's models never name. P1 drives the gap to zero "
        "(docs/plan.md §6).",
        "",
        "## Per kind",
        "",
        "| Kind | Generated | Rejected by lowering | Petra PASS | Judged | Gap (judged and PASS) | Gap share of PASS | "
        "Controls judged (gap) | Mean check s |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for k in kinds:
        c = per_kind[k]
        share = f"{100 * c['gap'] / c['PASS']:.0f}%" if c["PASS"] else "n/a"
        out.append(f"| {k} | {c['generated']} | {c['REJECTED']} | {c['PASS']} | {c['judged']} | {c['gap']} | {share} | "
                   f"{c['control_judged']} of {c['control']} ({c['control_gap']}) | "
                   f"{seconds[k] / max(1, c['generated']):.2f} |")
    share = f"{100 * total['gap'] / total['PASS']:.0f}%" if total["PASS"] else "n/a"
    out.append(f"| **all** | {total['generated']} | {total['REJECTED']} | {total['PASS']} | {total['judged']} | "
               f"**{total['gap']}** | {share} | {total['control_judged']} of {total['control']} ({total['control_gap']}) | |")
    statuses = Counter(r["status"] for r in rows)
    out += ["", "Statuses over all designs: " + ", ".join(f"{s} {n}" for s, n in sorted(statuses.items())) + ".",
            "**Controls** are designs with no mutation: the sampler's or example's design as drawn. A judged control is "
            "either a false alarm or a gap in the sampler's own rules; the examples below say which.", ""]
    out += ["## Per kind and condition", "",
            "Every condition the judge can raise on the kind, including those it never raised in this run.", "",
            "| Kind | Condition | Judged | Gap (PASS among judged) | Example |", "|---|---|---|---|---|"]
    for k in kinds:
        for cid, cond in CONDITIONS.items():
            if k not in cond.kinds:
                continue
            cell = cells.get((k, cid), {"judged": 0, "pass": 0, "example": None, "first": None})
            row = cell["example"] or cell["first"]
            example = f"[#{row['index']}](#design-{row['index']})" if cell["example"] else (f"#{row['index']} (`--show {row['index']}`)" if row else "")
            out.append(f"| {k} | `{cid}` | {cell['judged']} | {cell['pass']} | {example} |")
        if not any(k in cond.kinds for cond in CONDITIONS.values()):
            out.append(f"| {k} | none | | | {UNDRAWN.get(k, '')} |")
    out += ["", "## Canaries", "",
            "Each file in `judges/canaries` is a false PASS found by hand on 2026-11-06, run in every run. **Re-found** means "
            "the generator produced a design of the same kind, with the same condition, that Petra passes.", "",
            "| Canary | Condition | Petra | Judge names it | Re-found |", "|---|---|---|---|---|"]
    found = 0
    for c in canary_rows:
        names = any(v[0] == c["condition"] for v in c["violations"])
        again = refound(c, rows)
        found += again
        out.append(f"| `{c['name']}` | `{c['condition']}` | {c['status']} | {'yes' if names else 'no'} | {'yes' if again else 'no'} |")
    out += ["", f"Canary recall: the generator re-found {found} of {len(canary_rows)}.", ""]
    undecided = Counter()
    for row in rows:
        for note in row["undecided"]:
            undecided[(row["kind"], note.split(":", 1)[-1].strip().split(",")[0][:80])] += 1
    out += ["## What the judge did not decide", "",
            "Per design, the notes the judge left (counted by kind and the start of the note):", ""]
    out += [f"- {k}: {what} ({n})" for (k, what), n in sorted(undecided.items())] or ["- none"]
    out += ["", "By construction, for every design:", ""]
    out += [f"- {k}: {why}." for k, why in UNDRAWN.items()]
    out += [
        "- Every support is read as a column. Under a girder reading, a beam framing to the web would also need its depth "
        "to fit between the girder's flanges or a cope; the grammar does not say which, so that condition is not judged.",
        "- Bolt holes are taken as standard (Table J3.3), the smallest the grammar allows, and fits are physical "
        "(a hole wholly on the part), not Table J3.4's minimum edge distances, which Petra checks where it names them.",
        "- `steel.beam_side.fillet` and `steel.support_side.web_fillet` flag a part that clears the flanges but sits on "
        "the web-to-flange fillets, inside kdes (the shapes table's detailing value). A fabricator can clip such a "
        "corner, so these are counted apart from parts that hit solid steel or leave the member.",
        "- Where the lines leave a position open, the judge takes the most favourable one: a symmetric pair of bolt "
        "lines is centred on the column, a one-sided group (a single angle, a bracket's columns) goes wherever it fits, "
        "and a beam end and its cope reach as far out as the lines allow.",
        "- Wrench clearance, weld access and bolt length are not judged; Petra names clearance for some plies.",
        "- The truss judge cannot decide out-of-plane bracing, which the truss model assumes and never states.",
        "- The circuit judge reads the terminal's conductor range from the registry, whose rows are tagged judged.",
        "",
        "## Examples, one per gap cell",
        "",
    ]
    for (k, cid), cell in sorted(cells.items(), key=lambda kv: (kinds.index(kv[0][0]), kv[0][1])):
        row = cell["example"]
        if row is None:
            continue
        out += [f"### Design {row['index']}", "", f"{k}, `{cid}`: {_reason(row, cid)}. Mutations: "
                f"{', '.join(row['mutations']) or 'none'}. Origin: {row['origin']}.", "", "```", row["text"].rstrip(), "```", ""]
    return "\n".join(out) + "\n"


def log_lines(rows: list[dict], canary_rows: list[dict]) -> list[str]:
    """Every canary with its text, and every generated design the judge flags or leaves
    undecided or Petra rejects, without its text: `--show INDEX` regenerates any design from
    the seed. Per-design times are left out, so a seed's log is the same on every run."""
    out = []
    for row in canary_rows + rows:
        if row["origin"] != "canary" and not (row["violations"] or row["undecided"] or row["status"] in ("REJECTED", "ERROR")):
            continue
        keep = {k: v for k, v in row.items() if k not in ("seconds", "text")}
        if row["origin"] == "canary":
            keep["text"] = row["text"]
        out.append(json.dumps(keep, sort_keys=True))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="measure the absurd-design gap")
    parser.add_argument("--n", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--workers", type=int, default=7)
    parser.add_argument("--out", type=Path, default=ROOT / "docs")
    parser.add_argument("--show", type=int, metavar="INDEX", help="print design INDEX of the seed and stop")
    args = parser.parse_args(argv)
    if args.show is not None:
        print(sample(args.seed, args.show, build_registry()).text)
        return 0
    started = time.time()
    rows = run(args.seed, args.n, args.workers)
    canary_rows = canaries(build_registry())
    wall = time.time() - started
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    args.out.mkdir(parents=True, exist_ok=True)
    report = render(rows, canary_rows, args, wall, commit)
    (args.out / "absurd_gap.md").write_text(report, encoding="utf-8", newline="\n")
    (args.out / "absurd_gap_log.jsonl").write_text("\n".join(log_lines(rows, canary_rows)) + "\n", encoding="utf-8", newline="\n")
    print(report.split("## Examples", 1)[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
