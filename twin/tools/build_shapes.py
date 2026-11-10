"""Write twin/shapes.json from the AISC shapes database, read in place.

Usage: py -3.11 -m twin.tools.build_shapes PATH_TO_SHAPE160.xlsx

The workbook is parsed with the standard library (zipfile and ElementTree). Only W, WT and L
rows are kept, and only the dimensions the twin's checks read. Values are stored as the
shortest decimal string that round-trips the workbook's double.
"""

import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
FIELDS = {
    "W": ["A", "d", "bf", "tw", "tf", "kdes", "kdet", "k1", "Sx", "Zx", "T"],
    "WT": ["A", "d", "bf", "tw", "tf", "kdes", "y"],
    "L": ["A", "b", "d", "t", "kdes", "x", "y"],
}
OUT = Path(__file__).resolve().parent.parent / "shapes.json"


def design_name(label):
    """AISC label to a design's spelling: L4X3-1/2X3/8 is L4x3_1_2x3_8, WT5X22.5 is WT5x22_5."""
    return re.sub(r"[-/.]", "_", label.replace("X", "x"))


def rows(path):
    with zipfile.ZipFile(path) as z:
        strings = [
            "".join(t.text or "" for t in si.iter(NS + "t"))
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).iter(NS + "si")
        ]
        sheet = ET.fromstring(z.read("xl/worksheets/sheet2.xml"))
    for row in sheet.iter(NS + "row"):
        cells = {}
        for c in row.iter(NS + "c"):
            v = c.find(NS + "v")
            if v is not None:
                col = re.match(r"[A-Z]+", c.get("r")).group(0)
                cells[col] = strings[int(v.text)] if c.get("t") == "s" else v.text
        yield cells


def number(text):
    return repr(float(text))


def build(path):
    it = rows(path)
    header = next(it)
    imperial = {}
    for col, name in header.items():
        imperial.setdefault(name, col)
    shapes = {}
    for cells in it:
        kind = cells.get("A")
        if kind not in FIELDS:
            continue
        name = design_name(cells[imperial["AISC_Manual_Label"]])
        if name in shapes:
            raise SystemExit(f"duplicate name {name}")
        entry = {}
        for field in FIELDS[kind]:
            raw = cells.get(imperial[field])
            if raw not in (None, "–", "-"):
                entry[field] = number(raw)
        shapes[name] = entry
    return shapes


def main():
    shapes = build(sys.argv[1])
    lines = [f"{json.dumps(name)}: {json.dumps(shapes[name], sort_keys=True)}" for name in sorted(shapes)]
    OUT.write_text("{\n" + ",\n".join(lines) + "\n}\n", encoding="utf-8")
    print(f"wrote {len(shapes)} shapes to {OUT}")


if __name__ == "__main__":
    main()
