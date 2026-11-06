"""Rolled shapes for the steel deck: the AISC Shapes Database table and its importer.

The table lives in aisc_shapes.json beside this module, so a verdict never depends on a
file outside the repository. Each W row becomes constants "aisc_shapes_v16.<key>.<prop>"
(d, bf, tf, tw, kdes, A) carrying the table's tag, owner and source; the source names the
database file and its sha256 when the table came from it. Each W and L designation also
gives constants of its own, tagged sanctioned because the designation is the value: a
W18x50's nominal weight 50 lb/ft, an L4x3-1/2x3/8's legs and thickness.

    python -m lola.registry.steel_shapes import FILE.xlsx [--out PATH]

reads the published workbook (Excel 2007+ format, read with zipfile and ElementTree, no
other package), keeps every W and L row, and rewrites the table with the file's sha256
and tag sanctioned. Until a maintainer runs it on the published file, the shipped table is
a transcription tagged judged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from dataclasses import dataclass
from fractions import Fraction
from typing import Iterator, Mapping
from xml.etree import ElementTree

from ..kernel import Interval
from ..premises import Tag
from ..units import CUSTOMARY
from .model import Constant

TABLE = os.path.join(os.path.dirname(__file__), "aisc_shapes.json")
FORMAT = "lola-shapes/0"
GROUP = "aisc_shapes_v16"
W_PROPS: tuple[str, ...] = ("d", "bf", "tf", "tw", "kdes", "A")
"""The W-shape columns a connection check reads, by their Shapes Database header names."""

_INCH = CUSTOMARY["inch"][0]
_LB_PER_FT = Fraction(45359237, 10**8) / (12 * _INCH)
_LABEL = re.compile(r"(W|L)[0-9][0-9X./-]*")


@dataclass(frozen=True)
class ShapeTable:
    file: str | None
    sha256: str | None
    tag: Tag
    owner: str
    source: str
    w: tuple[Mapping[str, str], ...]     # label, then each of W_PROPS as decimal text in inch or inch2
    angles: tuple[str, ...]              # designations "L4X3-1/2X3/8"


def key(label: str) -> str:
    """"W18X50" -> "W18x50", "L4X3-1/2X3/8" -> "L4x3_1_2x3_8": an id segment."""
    return label.replace("X", "x").replace("-", "_").replace("/", "_").replace(".", "_")


def load(path: str = TABLE) -> ShapeTable:
    with open(path, encoding="utf-8") as f:
        body = json.load(f)
    if body.get("format") != FORMAT:
        raise ValueError(f"{path}: format {body.get('format')!r} is not {FORMAT}")
    return ShapeTable(body["file"], body["sha256"], Tag(body["tag"]), body["owner"], body["source"],
                      tuple(body["W"]), tuple(body["L"]))


def _mixed(text: str) -> Fraction:
    """"3-1/2" -> 7/2, "3/8" -> 3/8, "4" -> 4: a designation's dimension in inches."""
    whole, _, frac = text.partition("-")
    return Fraction(whole) + (Fraction(frac) if frac else 0)


def angle_legs(label: str) -> tuple[Fraction, Fraction, Fraction]:
    """(long leg, short leg, thickness) in inches from "L4X3-1/2X3/8"."""
    parts = label[1:].split("X")
    if len(parts) != 3:
        raise ValueError(f"{label} is not an angle designation L<leg>X<leg>X<thickness>")
    long, short, t = (_mixed(p) for p in parts)
    return long, short, t


def weight(label: str) -> Fraction:
    """Nominal weight in lb/ft from "W18X50"."""
    return Fraction(label.split("X")[1])


def constants(table: ShapeTable | None = None) -> dict[str, Constant]:
    table = table or load()
    out: list[Constant] = []
    for row in table.w:
        label, k = row["label"], key(row["label"])
        where = f"{table.source}, row {label}"
        for prop in W_PROPS:
            unit = "m2" if prop == "A" else "m"
            scale = _INCH**2 if prop == "A" else _INCH
            text = row[prop]
            out.append(Constant(f"{GROUP}.{k}.{prop}", _point(Fraction(text) * scale), unit, table.tag, table.owner,
                                f"{where}, column {prop} = {text} {'in2' if prop == 'A' else 'in'}",
                                f"{label} has {prop} = {text} {'in2' if prop == 'A' else 'in'}"))
        w = weight(label)
        out.append(Constant(f"{GROUP}.{k}.w", _point(w * _LB_PER_FT), "kg/m", Tag.SANCTIONED, "ASTM",
                            f"ASTM A6/A6M W-shape designation {label}: nominal weight {w} lb/ft (the designation)",
                            f"{label} weighs {w} lb/ft nominally"))
    for label in table.angles:
        k = key(label)
        legs = dict(zip(("d", "b", "t"), angle_legs(label)))
        for prop, value in legs.items():
            what = {"d": "long leg", "b": "short leg", "t": "thickness"}[prop]
            out.append(Constant(f"{GROUP}.{k}.{prop}", _point(value * _INCH), "m", Tag.SANCTIONED, "ASTM",
                                f"ASTM A6/A6M angle designation {label}: {what} {value} in (the designation)",
                                f"{label} has {what} {value} in"))
    found = {c.name: c for c in out}
    if len(found) != len(out):
        raise ValueError("a shape is listed twice")
    return found


def _point(x: Fraction) -> Interval:
    return Interval(x, x)


# --- Importer for the published workbook ------------------------------------------------

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _shared_strings(book: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in book.namelist():
        return []
    root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(f"{_NS}t")) for si in root.iter(f"{_NS}si")]


def _column(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def _rows(book: zipfile.ZipFile, sheet: str, strings: list[str]) -> Iterator[dict[int, str]]:
    root = ElementTree.fromstring(book.read(sheet))
    for row in root.iter(f"{_NS}row"):
        cells: dict[int, str] = {}
        for c in row.iter(f"{_NS}c"):
            kind = c.get("t")
            if kind == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(f"{_NS}t"))
            else:
                v = c.find(f"{_NS}v")
                if v is None or v.text is None:
                    continue
                text = strings[int(v.text)] if kind == "s" else v.text
            cells[_column(c.get("r", ""))] = text.strip()
        yield cells


def _decimal(text: str) -> str | None:
    """The shortest decimal text of a numeric cell, or None for a blank or a dash."""
    try:
        x = float(text)
    except ValueError:
        return None
    return repr(x) if x > 0 else None


def import_workbook(path: str) -> dict:
    """The table body for aisc_shapes.json from the published workbook: every W row with
    all of W_PROPS numeric, and every L designation, with the file's sha256."""
    digest = sha256(path)
    with zipfile.ZipFile(path) as book:
        strings = _shared_strings(book)
        sheets = sorted(n for n in book.namelist() if n.startswith("xl/worksheets/") and n.endswith(".xml"))
        for sheet in sheets:
            rows = _rows(book, sheet, strings)
            header = next(rows, {})
            names = {text: col for col, text in header.items()}
            if "AISC_Manual_Label" in names and "Type" in names and all(p in names for p in W_PROPS):
                break
        else:
            raise ValueError(f"{path}: no worksheet has the headers AISC_Manual_Label, Type and {', '.join(W_PROPS)}")
        w, angles = [], []
        for cells in rows:
            label, kind = cells.get(names["AISC_Manual_Label"], ""), cells.get(names["Type"], "")
            if kind == "W" and _LABEL.fullmatch(label):
                values = {p: _decimal(cells.get(names[p], "")) for p in W_PROPS}
                if all(values.values()):
                    w.append({"label": label, **values})
            elif kind == "L" and _LABEL.fullmatch(label):
                angles.append(label)
    name = os.path.basename(path)
    return {
        "format": FORMAT,
        "file": name,
        "sha256": digest,
        "tag": Tag.SANCTIONED.value,
        "owner": "AISC",
        "source": f"AISC Shapes Database v16.0 ({name}, sha256 {digest})",
        "units": {p: "inch2" if p == "A" else "inch" for p in W_PROPS},
        "W": w,
        "L": angles,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m lola.registry.steel_shapes")
    sub = parser.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("import", help="rewrite the shape table from the published workbook")
    imp.add_argument("file")
    imp.add_argument("--out", default=TABLE)
    args = parser.parse_args(argv)
    body = import_workbook(args.file)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(body, indent=1, ensure_ascii=False) + "\n")
    print(f"{len(body['W'])} W rows and {len(body['L'])} angles from {args.file} (sha256 {body['sha256']}) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
