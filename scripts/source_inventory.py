"""What Petra encodes from a standard: `py -3.11 scripts/source_inventory.py [--check]`.

Writes docs/sources/inventory.jsonl, one item per line, sorted by id. An item is one of:

  - a registry value (petra/registry): every Constant, and every Stated property of a
    material, part, process or environment. Its id is the key of its premise label, so
    "const.aisc360.j4_1.phi" or "bolt_group.120.Fnt";
  - an equation of the steel deck's limit states, by its number in the standard, from the
    docstrings of petra/models/steel/limits.py and fatigue.py, which cite each equation they
    encode ("Eq J3-1", "Manual Eqs 9-14, 9-19 and 9-20"). Its id is "eq.<edition>.<label>";
  - a rule the code encodes in its structure rather than in a registry row, listed by hand
    in HAND below, with id "code.<name>".

Each item gives its module and symbol, its value in the units its source prints (inches,
kips and ksi for the AISC and RCSC texts), its clause and edition as Petra cites them, its
origin (standard, designation, datasheet or petra), its tag, and the document on disk that
holds its source, if any. A registry value's clause and edition are read from its source
text; the parse is in `cite`. Deterministic: the same registry gives the same file.

--check exits 1 when the committed file differs from what the registry gives.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import asdict, dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from petra.kernel import Interval  # noqa: E402
from petra.registry import build_registry  # noqa: E402
from petra.registry import constants as base_rows  # noqa: E402
from petra.registry import steel as steel_rows  # noqa: E402
from petra.registry import steel_fatigue as fatigue_rows  # noqa: E402
from petra.registry.model import Constant, Registry, Stated  # noqa: E402
from petra.units import CUSTOMARY  # noqa: E402

OUT = ROOT / "docs" / "sources" / "inventory.jsonl"

A360 = "A360-22W-ewr.pdf"
P901 = "P901-23W.pdf"
P902 = "P902-23W.pdf"
SHAPES = "SHAPE160.xlsx"
BTH = "asme-bth-1-2023-en_compress.pdf"
DOCUMENTS = (A360, P901, P902, SHAPES, BTH)
"""The source documents on disk (docs/sources/README.md says where), by file name."""

INCH = CUSTOMARY["inch"][0]
KIP = CUSTOMARY["kip"][0]
KSI = CUSTOMARY["ksi"][0]
LB_PER_FT = Fraction(45359237, 10**8) / (12 * INCH)

CUSTOMARY_UNITS = {"m": (INCH, "in"), "m2": (INCH ** 2, "in2"), "Pa": (KSI, "ksi"), "N": (KIP, "kips"),
                   "1/m": (1 / INCH, "1/in"), "kg/m": (LB_PER_FT, "lb/ft"), "1": (Fraction(1), "1")}
"""A registry unit -> (its size in the source's customary unit, that unit's name)."""


@dataclass(frozen=True)
class Item:
    id: str
    module: str
    symbol: str
    kind: str           # factor | constant | limit | table_row | equation
    value: str          # exact, in `unit`; an equation's form for an equation
    unit: str
    clause: str
    edition: str
    origin: str         # standard | designation | datasheet | petra
    tag: str            # sanctioned | judged; "" for an equation or a rule of the code
    document: str | None


# --- Citations -------------------------------------------------------------------------------

EDITIONS = (
    (r"AISC 360-22", "AISC 360-22"),
    (r"RCSC 2025", "RCSC 2025"),
    (r"AISC Steel Construction Manual, 16th ed\.", "AISC Manual 16th ed."),
    (r"AISC Shapes Database v16\.0", "AISC Shapes Database v16.0"),
    (r"ASTM A6/A6M", "ASTM A6/A6M"),
    (r"ASTM [A-F]\d+(?: Grade \w+)?", None),
    (r"ASME B[\d.]+", None),
    (r"AWS A5\.1/A5\.5", "AWS A5.1/A5.5"),
    (r"(?:IEC|EN|ISO) \d[\d-]*(?::\d{4})?", None),
    (r"WGS 84", "WGS 84"),
    (r"MIL-STD-889", "MIL-STD-889"),
)
"""(pattern, edition name or None for the matched text), tried in order on a source."""

REF = re.compile(
    r"(?:Commentary )?Sections? [A-Z]?\d+(?:\.\d+)*[a-z]?(?:\([a-z0-9]+\))*(?:-[A-Z]?\d+(?:\.\d+)*(?:\([a-z0-9]+\))*)?"
    r"|Table [A-Z]?-?\d+(?:[.-]\d+)*[a-z]?"
    r"|Eqs?\. [A-Z]?-?\d+(?:-\d+)*[a-z]?(?:(?:, | and | to )[A-Z]?-?\d+(?:-\d+)+[a-z]?)*"
    r"|Appendix \d+|Parts? \d+(?:, \d+)*(?: and \d+)?|Figure \d+-\d+|Symbols list|User Note|Annex [A-Z]+"
    r"|Examples? [A-Z]+\.[A-Z\d.-]+")
"""A clause reference inside a source text."""

BARE = re.compile(r"(?<![\w.-])\d+(?:\.\d+){1,3}(?:\(\d+\))?(?![\w.])")
"""A bare clause number, as EN, IEC and ISO sources write them: "3.2.6(1)", "433.1"."""

ALSO = re.compile(r"\(= (AISC 360-22) ([^)]*)\)")
"""An RCSC row's equivalent in AISC 360-22, which is on disk: "(= AISC 360-22 Table J3.2)"."""


def cite(source: str) -> tuple[str, str]:
    """(edition, clause) of a registry source text: the edition named first, and the clause
    references between it and the first colon or semicolon."""
    own = ALSO.sub("", source)
    if "datasheet" in own:
        return own[:own.index("datasheet") + len("datasheet")].strip(), ""
    found = [(m.start(), m.end(), name or m.group(0)) for pattern, name in EDITIONS
             for m in [re.search(pattern, own)] if m]
    if not found:
        return "", ""
    start, end, edition = min(found, key=lambda f: (f[0], -f[1]))
    head = re.sub(r"\(AISC 360-16[^)]*\)", "", re.split(r"[:;]", own[end:], maxsplit=1)[0])
    refs = REF.findall(head) or (BARE.findall(head) if not edition.startswith(("AISC", "RCSC")) else [])
    seen: list[str] = []
    for r in refs:
        if r not in seen:
            seen.append(r)
    clause = ", ".join(seen) if seen else head.strip(" ,.()")[:80]
    row = re.search(r", row (\S+), column (\w+)", own)
    if edition == "AISC Shapes Database v16.0" and row:
        clause = f"row {row.group(1)}, column {row.group(2)}"
    also = ALSO.search(source)
    if also:
        clause += f" (= {also.group(1)} {also.group(2)})"
    return edition, clause


def origin(name: str, source: str) -> str:
    if name.startswith(("petra.", "rcsc2025.joint_level.")) or "Petra's encoding" in source \
            or "judged by petra-maintainers" in source or "not taken from a standard" in source:
        return "petra"
    if "datasheet" in source:
        return "datasheet"
    if "(the designation)" in source or "designation" in source.split(":")[0]:
        return "designation"
    return "standard"


def document(edition: str, source: str) -> str | None:
    """The document on disk that holds a registry value's source, if one does."""
    if edition == "AISC Shapes Database v16.0":
        return SHAPES
    if "P901-23W.pdf" in source or "Companion" in source:
        return P901
    if edition == "AISC 360-22" or ALSO.search(source):
        return A360
    return None


# --- Values ----------------------------------------------------------------------------------

def exact(x: Fraction) -> str:
    """A rational as the shortest exact text: a terminating decimal, else p/q."""
    x = Fraction(x)
    d = x.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d != 1:
        return f"{x.numerator}/{x.denominator}"
    with localcontext() as ctx:
        ctx.prec = 60
        text = format(Decimal(x.numerator) / Decimal(x.denominator), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def customary(edition: str) -> bool:
    return edition.startswith(("AISC", "RCSC", "ASTM", "ASME", "AWS"))


def inches(x: Fraction) -> str:
    """A length in inches as the AISC tables print it: 1-1/8 for 9/8, 13/16, and 0.209 where
    the denominator is no power of two up to 64."""
    if x.denominator > 64 or x.denominator & (x.denominator - 1) or x < 0:
        return exact(x)
    whole, part = divmod(x, 1)
    if part == 0:
        return str(whole)
    return f"{part.numerator}/{part.denominator}" if whole == 0 else f"{whole}-{part.numerator}/{part.denominator}"


def in_source_units(value: Interval, unit: str, edition: str) -> tuple[str, str]:
    """(value text, unit) as the source prints it: customary for AISC, RCSC, ASTM, ASME and
    AWS, the registry's SI otherwise."""
    scale, name = CUSTOMARY_UNITS.get(unit, (Fraction(1), unit)) if customary(edition) else (Fraction(1), unit)
    show = inches if name == "in" else exact
    lo, hi = Fraction(value.lo) / scale, Fraction(value.hi) / scale
    return (show(lo) if lo == hi else f"[{show(lo)}, {show(hi)}]"), name


def registry_value(registry: Registry, key: str) -> tuple[Fraction, Fraction]:
    """The (lo, hi) of a registry item in its source's units: what tests compare."""
    fact = registry.fact(key)
    source = fact.source if isinstance(fact, Constant) else fact.standard
    edition, _ = cite(source)
    scale = CUSTOMARY_UNITS.get(fact.unit, (Fraction(1), fact.unit))[0] if customary(edition) else Fraction(1)
    return Fraction(fact.value.lo) / scale, Fraction(fact.value.hi) / scale


# --- Where each registry value is written -------------------------------------------------------

def _names(rows) -> set[str]:
    return {row[0] for row in rows}


FACTOR_NAMES = _names(steel_rows.FACTORS)
COEFFICIENT_NAMES = _names(steel_rows.COEFFICIENTS)
FATIGUE_NAMES = _names(fatigue_rows.FATIGUE)
BOLT_SYMBOLS = {"d": "BOLT_SIZES", "std": "HOLES", "ovs": "HOLES", "ssl_w": "HOLES", "ssl_l": "HOLES", "lsl_w": "HOLES",
                "lsl_l": "HOLES", "edge_min": "EDGE_MIN", "c2_ovs": "C2_INCREMENT", "c2_ssl": "C2_INCREMENT",
                "Tm_g120": "PRETENSION", "Tm_g150": "PRETENSION", "tpi": "THREADS_PER_INCH", "nut_F": "_bolt_constants"}


def _tabulated(size: str, table) -> bool:
    return any(steel_rows.size_id(s) == size for s in table)


def place(key: str) -> tuple[str, str]:
    """(module, symbol) where a registry value is written."""
    if key.startswith("const."):
        name = key[len("const."):]
        if name in FACTOR_NAMES:
            return "petra/registry/steel.py", "FACTORS"
        if name in COEFFICIENT_NAMES:
            return "petra/registry/steel.py", "_weld_ic_rows" if name.startswith("aisc_manual.p8.") else "COEFFICIENTS"
        if name in FATIGUE_NAMES:
            return "petra/registry/steel_fatigue.py", "FATIGUE"
        if name.startswith("bolt_us."):
            prop = name.rsplit(".", 1)[1]
            size = name.split(".")[1]
            symbol = BOLT_SYMBOLS[prop]
            if symbol == "HOLES" and not _tabulated(size, steel_rows.HOLES):
                symbol = "holes_for"
            if symbol == "EDGE_MIN" and not _tabulated(size, steel_rows.EDGE_MIN):
                symbol = "_bolt_constants"
            return "petra/registry/steel.py", symbol
        if name.startswith(steel_rows.STOCK_PLATE):
            return "petra/registry/steel.py", "STOCK_PLATES"
        if name.startswith("aisc_shapes_v16."):
            return "petra/registry/aisc_shapes.json", "steel_shapes.constants"
        if name in base_rows.CONSTANTS:
            return "petra/registry/constants.py", "_constants"
        return "petra/registry/electronics.py", "electronics_constants"
    entry = key.rpartition(".")[0]
    if entry.startswith("bolt_group."):
        return "petra/registry/steel.py", "BOLT_GROUPS"
    if entry in {f"steel.{g}" for g in steel_rows.GRADES}:
        return "petra/registry/steel.py", "GRADES"
    if entry.startswith("electrode."):
        return "petra/registry/steel.py", "ELECTRODES"
    if entry.startswith(("res.", "led.", "reg.")):
        return "petra/registry/electronics.py", "electronics_materials"
    return "petra/registry/constants.py", "STATED"


MANUAL_TABLE = "AISC Manual 16th ed. Table 2-4"

LIMIT = re.compile(r"(min|max|limit|ratio|cap|pitch|edge|cycles|offset|allowance|length|depth|rows|clip|underrun|"
                   r"exemption|end_distance|floor|plies|_t\d?$|^t\d$|share|peak|a_min|k_max)")


def kind(key: str, fact: Constant | Stated) -> str:
    name = key.removeprefix("const.")
    short = name.rsplit(".", 1)[-1]
    if isinstance(fact, Stated) or name.startswith(("bolt_us.", "aisc_shapes_v16.", "aisc360.app3.cat_", "iso261.",
                                                    "iec60228.", "iec60227_3.", "en10219_2.", "iec60063.",
                                                    steel_rows.STOCK_PLATE)) \
            or re.fullmatch(r"aisc360\.j2_2b\.[tw]\d", name):
        return "table_row"
    if re.search(r"(^|_)(phi|omega)(_|$)", short):
        return "factor"
    if LIMIT.search(short):
        return "limit"
    return "constant"


def registry_items(registry: Registry) -> list[Item]:
    out = []
    keys = [f"const.{name}" for name in registry.constants]
    for table in (registry.materials, registry.parts, registry.processes, registry.environments):
        for eid, entry in table.items():
            keys += [f"{eid}.{prop}" for prop, v in getattr(entry, "props", {}).items() if isinstance(v, Stated)]
    for key in sorted(set(keys)):
        fact = registry.fact(key)
        source = fact.source if isinstance(fact, Constant) else fact.standard
        if key.endswith(".anodic_index"):
            source = source.rpartition("; ")[2]
        edition, clause = cite(source)
        if key.rpartition(".")[0] in {f"steel.{g}" for g in steel_rows.GRADES} and key.endswith((".fy", ".fu")):
            clause = f"specified minimum {key.rsplit('.', 1)[1].capitalize()}, as {MANUAL_TABLE} lists it"
        value, unit = in_source_units(fact.value, fact.unit, edition)
        module, symbol = place(key)
        out.append(Item(key, module, symbol, kind(key, fact), value, unit, clause, edition, origin(key, source),
                        fact.tag.value, document(edition, source)))
    return out


# --- Equations -------------------------------------------------------------------------------

EQUATION_MODULES = ("petra/models/steel/limits.py", "petra/models/steel/fatigue.py")
LABEL = r"(?:[A-Z]-\d+-\d+|[A-Z]\d+-\d+[a-z]?(?:/[a-z])?|\d+-\d+[a-z]?(?:/[a-z])?)"
CITED = re.compile(rf"(360-16 |Manual )?Eqs?\.? ({LABEL}(?:(?:, | and | to ){LABEL})*)")
MENTIONED = {("fillet_line", "J2-5"), ("fillet_line", "J2-6"), ("prying_available", "J3-3")}
"""(function, label) pairs a docstring names without encoding: fillet_line takes kds = 1 and
says the directional increase and the group rule are not taken; prying_available points at
the combined-stress equations its bolt strength comes from."""


def _span(first: str, last: str) -> list[str]:
    """"15-13", "15-15" -> 15-13, 15-14, 15-15."""
    head, _, a = first.rpartition("-")
    b = last.rpartition("-")[2]
    if a.isdigit() and b.isdigit() and last.startswith(head + "-"):
        return [f"{head}-{n}" for n in range(int(a), int(b) + 1)]
    return [first, last]


def labels(docstring: str) -> list[tuple[str, str]]:
    """(edition, label) of each equation a docstring cites: "Eq J3-3a/b" gives J3-3a and
    J3-3b, "Eqs 15-13 to 15-15" the three; a label without a letter is the Manual's, and one
    after "360-16" is the earlier edition's, which no item takes."""
    out = []
    for m in CITED.finditer(" ".join(docstring.split())):
        if m.group(1) == "360-16 ":
            continue
        parts = re.split(r"(, | and | to )", m.group(2))
        names: list[str] = []
        for i in range(0, len(parts), 2):
            if i >= 2 and parts[i - 1] == " to ":
                names[-1:] = _span(names[-1], parts[i])
            else:
                names.append(parts[i])
        for label in names:
            stem, _, alt = label.partition("/")
            for one in [stem] + ([stem[:-1] + alt] if alt else []):
                manual = m.group(1) == "Manual " or re.fullmatch(r"\d+-\d+[a-z]?", one) is not None
                out.append(("AISC Manual 16th ed." if manual else "AISC 360-22", one))
    return out


def equation_items() -> list[Item]:
    found: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
    for module in EQUATION_MODULES:
        tree = ast.parse((ROOT / module).read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            doc = ast.get_docstring(node) or ""
            summary = " ".join(doc.split("\n\n")[0].split())
            for edition, label in labels(doc):
                if (node.name, label) not in MENTIONED:
                    found.setdefault((edition, label), []).append((module, node.name, summary))
    out = []
    for (edition, label), where in sorted(found.items()):
        prefix = "aisc360" if edition == "AISC 360-22" else "manual"
        summary = where[0][2]
        out.append(Item(f"eq.{prefix}.{label}", ", ".join(sorted({m for m, _, _ in where})),
                        ", ".join(sorted({f for _, f, _ in where})), "equation",
                        summary if len(summary) <= 300 else summary[:297] + "...", "", f"Eq. {label}", edition,
                        "standard", "", A360 if edition == "AISC 360-22" else P901))
    return out


# --- Rules in the code's structure ---------------------------------------------------------------

HAND: tuple[Item, ...] = (
    Item("code.bolt_area", "petra/models/steel/limits.py", "bolt_area", "equation", "Ab = pi d^2 / 4", "",
         "Table J3.2 (Ab, the nominal unthreaded body area)", "AISC 360-22", "standard", "", A360),
    Item("code.fillet_throat", "petra/mechanics/weld_groups.py", "fillet_throat", "equation", "w / sqrt 2", "",
         "Section J2.2a (effective throat of an equal-leg fillet)", "AISC 360-22", "standard", "", A360),
    Item("code.kds_one", "petra/models/steel/limits.py", "fillet_line", "constant", "1", "1",
         "Section J2.4(a) (kds = 1.0; the directional increase of Eq. J2-5 not taken)", "AISC 360-22", "standard", "",
         A360),
    Item("code.holes_large", "petra/registry/steel.py", "holes_for", "table_row",
         "d + 1/8, d + 5/16, (d + 1/8) x (d + 3/8), (d + 1/8) x 2.5d", "in",
         "Table J3.3, bolt diameter 1-1/8 in and over", "AISC 360-22", "standard", "", A360),
    Item("code.edge_large", "petra/registry/steel.py", "_bolt_constants", "table_row", "1.25 d", "in",
         "Table J3.4, bolt diameter over 1-1/4 in", "AISC 360-22", "standard", "", A360),
    Item("code.c2_rows", "petra/registry/steel.py", "_bolt_constants", "table_row",
         "up to 7/8 in; 1 in; 1-1/8 in and over", "in", "Table J3.5, the nominal diameter rows", "AISC 360-22",
         "standard", "", A360),
    Item("code.ubs_uniform", "petra/models/steel/checks.py", "gen_block_shear", "constant", "1", "1",
         "Section J4.3 (Ubs = 1 where the tension stress is uniform)", "AISC 360-22", "standard", "", A360),
    Item("code.ksc_lrfd", "petra/models/steel/limits.py", "slip_ksc", "constant", "1", "1",
         "Section J3.10, Eq. J3-5a (no factor on Tu in LRFD)", "AISC 360-22", "standard", "", A360),
    Item("code.panel_alpha_lrfd", "petra/models/steel/checks.py", "gen_panel_zone", "constant", "1.0", "1",
         "Section J10.6 (alpha = 1.0 in LRFD)", "AISC 360-22", "standard", "", A360),
    Item("code.j10_1_end_half", "petra/models/steel/checks.py", "gen_flange_local_bending", "limit", "1/2", "1",
         "Section J10.1 (the strength halved within 10 tf of the member end)", "AISC 360-22", "standard", "", A360),
    Item("code.j10_2_end", "petra/models/steel/checks.py", "gen_web_local_yielding", "limit", "d", "",
         "Section J10.2 (Eq. J10-3 within d of the member end)", "AISC 360-22", "standard", "", A360),
    Item("code.j10_3_end", "petra/models/steel/checks.py", "gen_web_crippling", "limit", "d/2", "",
         "Section J10.3 (Eqs. J10-5a and J10-5b within d/2 of the member end)", "AISC 360-22", "standard", "", A360),
    Item("code.j10_5_end_half", "petra/models/steel/checks.py", "gen_web_compression_buckling", "limit", "1/2", "1",
         "Section J10.5 (the strength halved within d/2 of the member end)", "AISC 360-22", "standard", "", A360),
    Item("code.panel_zone_threshold", "petra/models/steel/limits.py", "panel_zone", "limit", "0.4", "1",
         "Section J10.6, Eqs. J10-9 and J10-10 (alpha Pr <= 0.4 Py, the crossing of min(1, 1.4 - alpha Pr / Py))",
         "AISC 360-22", "standard", "", A360),
    Item("code.section_stress", "petra/models/steel/fatigue.py", "section_stress", "equation", "M / S + 3 V / (2 t d)", "",
         "Appendix 3, Section 3.2 (elastic stress, no stress concentration factor)", "AISC 360-22", "standard", "", A360),
    Item("code.tm_definition", "petra/registry/steel.py", "_pretension", "equation", "Tm = 0.70 Fu As", "",
         "Section 5.4 commentary (Tm is 70 % of the bolt's minimum tensile strength; = AISC 360-22 Table J3.1 notes)",
         "RCSC 2025", "standard", "", A360),
)
"""Rules the code writes in its structure, with 0, 1 and 2 only (tests/test_steel_principles.py),
or in a formula over a registry row: each with the clause it encodes."""


def inventory() -> list[Item]:
    items = [*registry_items(build_registry()), *equation_items(), *HAND]
    ids = [i.id for i in items]
    if len(ids) != len(set(ids)):
        raise RuntimeError("an inventory id appears twice")
    return sorted(items, key=lambda i: i.id)


def render(items: list[Item]) -> str:
    return "".join(json.dumps(asdict(i), ensure_ascii=False) + "\n" for i in items)


def read(path: Path = OUT) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="exit 1 when the committed inventory is stale")
    args = parser.parse_args(argv)
    text = render(inventory())
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print(f"{OUT.relative_to(ROOT)} is stale; run py -3.11 scripts/source_inventory.py")
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    counts: dict[str, int] = {}
    for item in json.loads("[" + ",".join(text.splitlines()) + "]"):
        counts[item["origin"]] = counts.get(item["origin"], 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)}: {text.count(chr(10))} items, by origin {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
