"""Bind each inventory item to the text that states it: `py -3.11 scripts/source_anchors.py --readings DIR`.

Writes docs/sources/anchors.jsonl, one anchor per item of docs/sources/inventory.jsonl, from
a reading of the documents and the documents themselves (scripts/verify_sources.py says
where they are looked for).

A reading is what a reader took from the page with Petra's values hidden: DIR holds
readings_*.jsonl, one object per value read, {task, doc, page, printed, span, kind, label,
read, row, col} or {task, found: false}. `task` is an inventory id, or a table
("table.J3.3") whose `row` and `col` name the cell; `targets` maps a reading to the items it
states. The readings quote the standards, so they stay out of the repository; an anchor
keeps the span's offsets and fingerprint, never its text.

An anchor's kind is:
  text         the span on the page states the value;
  visual       the text layer garbles the value, so the span pins the page by a label and
               `read` gives what the page image shows;
  cell         a cell of the shapes workbook, read here from the workbook itself;
  designation  the item's name states the value (a 7/8 in bolt's diameter);
  absent       no document on disk states it; `reason` says why.

`value` is the number the source states for the item, in the units the inventory prints,
or null where the item is no single number (an equation, a rule). `agrees` is whether Petra
holds what the source states: computed for a number, judged by hand for the rest
(DIFFERS). tests/test_sources.py checks the registry against `value` without the documents,
and verify_sources.py checks the documents against the anchors.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import source_inventory as inv  # noqa: E402
import verify_sources as vs  # noqa: E402
from petra.registry import build_registry  # noqa: E402

OUT = ROOT / "docs" / "sources" / "anchors.jsonl"
DOCS = {"A360": inv.A360, "P901": inv.P901, "P902": inv.P902}
SHEET = "Database v16.0"
F = Fraction


# --- What a reading states -------------------------------------------------------------------

WORDS = {"one": F(1), "two": F(2), "four": F(4), "one-half": F(1, 2)}


def number(printed: str) -> Fraction | None:
    """The one number a printed value states: "1-1/8", "30%", "one", or the coefficient of
    d in "3/4 d"."""
    p = printed.strip()
    if p in WORDS:
        return WORDS[p]
    x = vs.value(p)
    if x is not None:
        return x
    m = re.fullmatch(r"([\d./-]+) ?d", p)
    return vs.value(m.group(1)) if m else None


SIZES = {"1/2": "1_2", "5/8": "5_8", "3/4": "3_4", "7/8": "7_8", "1": "1", "1-1/8": "1_1_8", "1-1/4": "1_1_4",
         "1-3/8": "1_3_8", "1-1/2": "1_1_2"}
DIAMETER = {s: vs.value(s) for s in SIZES}
J32 = {"Fnt": "Fnt", "Fnv threads not excluded (N)": "Fnv_N", "Fnv threads excluded (X)": "Fnv_X"}
J33 = {"standard": "std", "oversize": "ovs", "short-slot width": "ssl_w", "short-slot length": "ssl_l",
       "long-slot width": "lsl_w", "long-slot length": "lsl_l"}
J35 = {"oversized holes": "c2_ovs", "short slots, long axis perpendicular to edge": "c2_ssl"}
J35_ROWS = {"<=7/8": lambda d: d <= F(7, 8), "1": lambda d: d == 1, ">=1-1/8": lambda d: d >= F(9, 8)}
A31 = (("1.3 R >= 1 in", "cat_c"), ("1.3 R >= 3/8", "cat_e_prime"), ("2.1", "cat_b"), ("8.5", "cat_g"))
RECIPROCAL = {"const.aisc_manual.t10_9.eccentricity"}
"""Items the registry holds as the reciprocal of the printed number: e = a/2 is 1/2."""


def _bolt(size: str, prop: str) -> str:
    return f"const.bolt_us.{SIZES[size]}.{prop}"


def targets(r: dict) -> list[tuple[str, Fraction | None]]:
    """(item id, the value the reading states for it) for each item a reading states."""
    task, row, col, printed = r["task"], r.get("row", ""), r.get("col", ""), r.get("printed", "")
    if task == "table.J3.1":
        prop = {"Group 120": "Tm_g120", "Group 144 and Group 150": "Tm_g150"}.get(col)
        return [(_bolt(row, prop), number(printed))] if prop and row in SIZES else []
    if task == "table.J3.2":
        m = re.match(r"(A307|Group (\d+))", row)
        if not m or col not in J32:
            return []
        return [(f"bolt_group.{m.group(2) or 'A307'}.{J32[col]}", number(printed))]
    if task == "table.J3.3":
        prop = J33[col]
        if row in SIZES:
            return [(_bolt(row, prop), number(printed))]
        rule = [(_bolt(s, prop), vs.in_d(printed, d)) for s, d in DIAMETER.items() if d >= F(9, 8)]
        return rule + ([("code.holes_large", None)] if prop == "std" else [])
    if task == "table.J3.4":
        if row in SIZES:
            return [(_bolt(row, "edge_min"), number(printed))]
        if row == "Over 1-1/4":
            rule = [(_bolt(s, "edge_min"), vs.in_d(printed, d)) for s, d in DIAMETER.items() if d > F(5, 4)]
            return rule + [("code.edge_large", number(printed))]
        return []
    if task == "table.J3.5":
        if col == "long slots, long axis perpendicular to edge":
            return [("const.aisc360.j3_5.c2_lsl", number(printed))] if row == "1" else []
        prop = J35.get(col)
        if not prop or row not in J35_ROWS:
            return []
        out = [(_bolt(s, prop), number(printed)) for s, d in DIAMETER.items() if J35_ROWS[row](d)]
        return out + ([("code.c2_rows", None)] if row == "1" and prop == "c2_ovs" else [])
    if task == "table.J2.4":
        k = next(k for k, head in enumerate(("To 1/4", "Over 1/4", "Over 1/2", "Over 3/4")) if row.startswith(head))
        return [(f"const.aisc360.j2_2b.w{k + 1}", number(printed))]
    if task == "table.A-3.1":
        cat = next((c for prefix, c in A31 if row.startswith(prefix)), None)
        prop = "cf" if col.startswith("Constant") else "fth" if col.startswith("Threshold") else None
        return [(f"const.aisc360.app3.{cat}.{prop}", number(printed))] if cat and prop else []
    if task == "const.aisc_manual.p9.tc":
        return [(task, number(printed)), ("eq.manual.9-30a", None)]
    x = number(printed)
    return [(task, 1 / x if task in RECIPROCAL and x else x)]


SPANS: dict[str, tuple[str, int, str, str]] = {
    "const.aisc360.j2_2b.t1": ("A360", 196, "To 1/4 (6) inclusive", "1/4"),
    "const.aisc360.j2_2b.t2": ("A360", 196, "Over 1/4 (6) to 1/2 (13)", "1/2"),
    "const.aisc360.j2_2b.t3": ("A360", 196, "Over 1/2 (13) to 3/4 (19)", "3/4"),
    **{f"const.aisc360.j2_2b.w{k}": ("A360", 196, "1/8 (3)\n3/16 (5)\n1/4 (6)\n5/16 (8)", p)
       for k, p in ((1, "1/8"), (2, "3/16"), (3, "1/4"), (4, "5/16"))},
}
"""Anchors read here rather than by the readers: Table J2.4's row bounds, and its sizes as
the whole column, since a size alone ("1/4 (6)") also matches a row label."""

SHORTER = {
    "code.j10_2_end": {"read": "J10-3 within d of the end, d included; J10-2 beyond"},
    "code.section_stress": {"printed": "elastic analysis, no stress concentration factor"},
}
"""A reader's words cut down to the rule, so no field runs long."""

DIFFERS: dict[str, str] = {
    "eq.manual.9-20a": "Petra's docstring gives tmin = sqrt(4 T b' / (phi p Fu)) as Manual Eq. 9-20a; the Companion "
                       "labels that form Eq. 9-30a (tc), and 9-20a is the coped beam's f = 2(c/d)",
}
"""Items with no single number whose source reads otherwise than Petra: id -> the finding."""

NOT_STATED = {
    "const.aisc_manual.p7.": "the Companion reads C from Manual Table 7-6 and states no load-deformation curve",
    "const.aisc_manual.p8.": "the Companion reads C from Manual Table 8-4 or 8-8 and states no load-deformation curve",
    "eq.manual.9-10": "no Companion example cites Manual Eq. 9-10",
    "steel.A36.": "neither Companion volume names A36, and AISC 360-22 lists the grade without strengths",
    "const.shop_deck.": "the Companion states no plate thickness increments",
}
"""Why the documents on disk do not state an item a reader looked for and did not find, by id
prefix; otherwise the item's own source says which unread document it cites."""


# --- Anchors ----------------------------------------------------------------------------------

def _readings(folder: Path) -> list[dict]:
    out = []
    for path in sorted(folder.glob("readings_*.jsonl")):
        out += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return out


def petra_value(registry, item: dict) -> Fraction | None:
    """The number Petra holds for an item in source units, or None for an equation or rule."""
    if item["id"].startswith(("eq.", "code.")):
        head = item["value"].split(" ")[0]
        return vs.value(head) if item["unit"] or head == item["value"] else None
    lo, hi = inv.registry_value(registry, item["id"])
    return lo if lo == hi else None


def _span(folder: Path, doc: str, page: int, text: str) -> dict:
    path = folder / doc
    page_text = vs.page_text(path, page)
    start = page_text.find(text)
    if start < 0:
        raise ValueError(f"{doc} page {page}: the span is not on the page: {text[:60]!r}")
    return {"doc": doc, "doc_sha256": vs.sha256(path), "page": page, "span": [start, start + len(text)],
            "span_sha256": vs.fingerprint(text)}


def _fmt(x: Fraction | None) -> str | None:
    return None if x is None else inv.exact(x)


def from_reading(folder: Path, item: dict, r: dict, stated: Fraction | None) -> dict:
    """An anchor from a reading. An equation anchored by a constant's reading prints the
    equation the reader recorded, not the constant."""
    printed = r.get("read") if item["id"].startswith("eq.") and r["task"] != item["id"] else None
    a = {"id": item["id"], "kind": r["kind"], **_span(folder, DOCS[r["doc"]], r["page"], vs.normalize(r["span"])),
         "printed": printed or r["printed"], "value": _fmt(stated)}
    if r["kind"] == "visual":
        a["label"], a["read"] = r["label"], r["read"]
    if r.get("row") or r.get("col"):
        row = r.get("row", "").split(",")[0] if r["task"] == "table.A-3.1" else r.get("row", "")
        a["cell"] = f"{row} / {r.get('col', '')}"
    a.update(SHORTER.get(item["id"], {}))
    return a


def shape_cell(folder: Path, item: dict) -> dict:
    """A W shape's dimension as the shapes workbook gives it: the row whose AISC_Manual_Label
    is the shape, the first column headed by the dimension's name."""
    path = folder / inv.SHAPES
    cells = vs._sheet(path, SHEET)
    shape, prop = item["id"].split(".")[2:4]
    label = shape.upper()
    header = {}
    for ref, text in cells.items():
        m = re.fullmatch(r"([A-Z]+)1", ref)
        if m and text not in header:
            header[text] = m.group(1)
    rows = [re.sub(r"[A-Z]+", "", ref) for ref, text in cells.items() if ref.startswith("C") and text == label]
    if len(rows) != 1:
        raise ValueError(f"{label} is on {len(rows)} rows of {inv.SHAPES}")
    where = f"{SHEET}!{header[prop]}{rows[0]}"
    text = vs.cell_text(path, where)
    printed = vs.cell_number(text)
    return {"id": item["id"], "kind": "cell", "doc": inv.SHAPES, "doc_sha256": vs.sha256(path), "page": where,
            "span": None, "span_sha256": vs.fingerprint(vs.normalize(text)), "printed": printed,
            "value": _fmt(vs.value(printed))}


def designation(item: dict) -> dict:
    """The value an item's name states: a bolt's diameter, a bolt group's tensile strength,
    a W shape's weight per foot, an angle's legs and thickness."""
    key = item["id"]
    parts = key.split(".")
    stated = None
    if key.startswith("const.bolt_us.") and parts[-1] == "d":
        stated = vs.value(parts[2].replace("_", "/", 1) if parts[2].count("_") == 1 else
                          parts[2].replace("_", "-", 1).replace("_", "/"))
    elif key.startswith("bolt_group.") and parts[-1] == "fu":
        stated = F(parts[1])
    elif key.startswith("const.aisc_shapes_v16.W") and parts[-1] == "w":
        stated = F(parts[2].split("x")[1])
    elif key.startswith("const.aisc_shapes_v16.L"):
        legs = [vs.value(p.replace("_", "-", 1).replace("_", "/") if p.count("_") == 2 else p.replace("_", "/"))
                for p in parts[2][1:].split("x")]
        stated = dict(zip("dbt", legs))[parts[-1]]
    elif key.startswith("const.en10219_2."):
        stated = dict(zip("Dt", (F(p.replace("_", ".")) / 1000 for p in parts[2].split("x"))))[parts[-1]]
    elif key.startswith("const.iso261.M") and parts[-1] == "d":
        stated = F(parts[2][1:]) / 1000
    elif key.startswith("electrode.E"):
        stated = F(parts[1][1:])
    name = item["clause"].removeprefix("bolt designation ").removeprefix("angle designation ")
    return {"id": key, "kind": "designation", "printed": name, "value": _fmt(stated),
            "reason": "the name states it"}


def absent(item: dict, looked: bool) -> dict:
    if item["origin"] == "petra":
        reason = "Petra's own value; no standard states it"
    elif item["origin"] == "datasheet":
        reason = "a manufacturer's datasheet, not on disk"
    elif looked:
        reason = next((why for prefix, why in NOT_STATED.items() if item["id"].startswith(prefix)),
                      f"not stated in the documents on disk; Petra cites {item['edition']} {item['clause']}")
    else:
        reason = f"{item['edition']} is not on disk"
    return {"id": item["id"], "kind": "absent", "reason": reason}


def anchors(readings: list[dict], folder: Path) -> list[dict]:
    registry = build_registry()
    items = inv.read()
    stated: dict[str, list[tuple[dict, Fraction | None]]] = {}
    looked: set[str] = set()
    for r in readings:
        if r.get("found") is False:
            looked.add(r["task"])
            continue
        for key, x in targets(r):
            stated.setdefault(key, []).append((r, x))
    out = []
    for item in items:
        key = item["id"]
        held = None if item["origin"] == "designation" else petra_value(registry, item)
        if key in SPANS:
            doc, page, text, printed = SPANS[key]
            a = {"id": key, "kind": "text", **_span(folder, DOCS[doc], page, text), "printed": printed,
                 "value": _fmt(vs.value(printed))}
        elif item["origin"] == "designation":
            a = designation(item)
        elif item["edition"] == "AISC Shapes Database v16.0":
            a = shape_cell(folder, item)
        elif key in stated:
            pairs = stated[key]
            r, x = next(((r, x) for r, x in pairs if held is not None and x == held), pairs[0])
            a = from_reading(folder, item, r, x)
        else:
            a = absent(item, key in looked or key.startswith("const.shop_deck."))
        if a["kind"] != "absent":
            if item["origin"] == "designation":
                held = petra_value(registry, item)
            if held is None and key.startswith(("eq.", "code.")):
                a["value"] = None
            x = vs.value(a["value"]) if a.get("value") else None
            a["agrees"] = (x == held) if x is not None and held is not None else key not in DIFFERS
            if key in DIFFERS:
                a["finding"] = DIFFERS[key]
        out.append(a)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--readings", required=True, help="folder of readings_*.jsonl")
    parser.add_argument("--sources", help=f"folder holding the documents (default ${vs.ENV})")
    args = parser.parse_args(argv)
    folder = vs.sources_dir(args.sources)
    out = anchors(_readings(Path(args.readings)), folder)
    OUT.write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in out), encoding="utf-8", newline="\n")
    kinds: dict[str, int] = {}
    for a in out:
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)}: {len(out)} anchors, {kinds}; "
          f"{sum(1 for a in out if a.get('agrees') is False)} disagree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
