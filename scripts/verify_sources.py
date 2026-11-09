"""Check every anchor against its source document: `py -3.11 scripts/verify_sources.py [--sources DIR]`.

docs/sources/anchors.jsonl binds each inventory item (docs/sources/inventory.jsonl) to the
place in a standard that states it. This script reads the documents from DIR, or from the
folder the PETRA_SOURCES environment variable names, or else from docs/research/sources,
the folder .gitignore keeps out of the repository. For each anchor it checks:

  1. the document's sha256 is the one the anchor names, so the edition is the one read;
  2. the span's sha256: the anchor's [start, end) slice of the page's text, extracted with
     pypdf and normalized by `normalize`, hashes to the anchor's fingerprint, so the words
     are the ones read;
  3. the printed value appears in the span after number normalization (`numbers`): a
     text anchor's value is one of the span's numbers; an equation's label and each of its
     numbers are; a visual anchor, whose equation the text layer drops, needs only its
     label there, and its `read` field records what the page image shows; a workbook cell
     displays the printed value.

The anchors hold fingerprints and numbers, never the documents' text. Exit 1 on any
failure. Needs pypdf (5.1.0 made the anchors; another version may lay text out
differently, and the fingerprints then fail).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata
import zipfile
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
ANCHORS = ROOT / "docs" / "sources" / "anchors.jsonl"
DEFAULT_SOURCES = ROOT / "docs" / "research" / "sources"
ENV = "PETRA_SOURCES"
PYPDF = "5.1.0"

KINDS = ("text", "visual", "cell", "designation", "absent")
"""text: the span states the value. visual: the text layer drops the equation, so the span
pins the page by its label and `read` says what the page image shows. cell: a workbook
cell. designation: the value is fixed by the item's name (a 3/4 in bolt's diameter), no
document needed. absent: the source is not on disk; `reason` says which it is."""


# --- Text and numbers ------------------------------------------------------------------------

DASHES = str.maketrans({"−": "-", "–": "-", "—": "-", "‐": "-", "‑": "-", "⁄": "/",
                        " ": " "})


def normalize(text: str) -> str:
    """NFKC, every dash and minus as "-", the fraction slash as "/", runs of blanks as one
    space, blank lines dropped. Line breaks stay: they are where pypdf ends a printed line."""
    text = unicodedata.normalize("NFKC", text).translate(DASHES)
    return "\n".join(line for line in (" ".join(raw.split()) for raw in text.splitlines()) if line)


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


LABEL = re.compile(r"(?<![\w.])[A-Za-z]+-?\d+(?:[.-]\d+)*[a-z]?")
"""A clause or equation label, or a symbol with a subscript digit: J3-6a, A-3-1, J4.1, tf2.
Its digits are no value."""

NUMBER = re.compile(r"(?<![\d.,/])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?:(?:-| )(\d+)/(\d+)|/(\d+))?(%)?")


def _splits(numerator: str, denominator: int) -> set[Fraction]:
    """"11/8" as pypdf lays out a mixed number: 11/8 or 1 + 1/8. Every split of the
    numerator's digits into a whole part and a proper fraction."""
    out = {Fraction(int(numerator), denominator)}
    for i in range(1, len(numerator)):
        whole, part = int(numerator[:i]), int(numerator[i:])
        if numerator[i] != "0" and part < denominator:
            out.add(whole + Fraction(part, denominator))
    return out


def numbers(text: str, labels: bool = False) -> set[Fraction]:
    """Every value a number in text can be read as, unsigned: 29,000 -> 29000; 0.75; 1-1/8
    -> 9/8; 11/8 -> 11/8 and 1-1/8; 30% -> 30 and 0.3. Labels are skipped unless `labels`,
    which an equation needs: pypdf sets tf squared as "tf2"."""
    text = normalize(text) if labels else LABEL.sub(" ", normalize(text))
    text = re.sub(r"(?<=\d) ?/ ?(?=\d)", "/", text)
    out: set[Fraction] = set()
    for m in NUMBER.finditer(text):
        whole, decimals, mixed_num, mixed_den, den, percent = m.groups()
        base = Fraction(whole.replace(",", "")) + (Fraction(f"0.{decimals}") if decimals else 0)
        if mixed_num is not None:
            values = {base + Fraction(int(mixed_num), int(mixed_den))}
            if m.group(0)[len(whole)] == " ":
                values |= {base, Fraction(int(mixed_num), int(mixed_den))}
        elif den is not None and not decimals:
            values = _splits(whole.replace(",", ""), int(den))
        elif den is not None:
            values = {base / int(den)}
        else:
            values = {base}
        if percent:
            values |= {v / 100 for v in values}
        out |= values
    return out


PRINTED = re.compile(r"(\d+(?:,\d{3})*)(?:\.(\d+))?(?:-(\d+)/(\d+)|/(\d+))?(%)?")


def value(printed: str) -> Fraction | None:
    """The one number a printed value states, read as written: "1-1/8" is 9/8 and "11/8"
    is 11/8 (a reader writes a mixed number with its hyphen), "30%" is 0.3, "29,000" is
    29000. None for anything else (an equation, a formula in d)."""
    m = PRINTED.fullmatch(printed.strip())
    if not m:
        return None
    whole, decimals, mixed_num, mixed_den, den, percent = m.groups()
    x = Fraction(whole.replace(",", "")) + (Fraction(f"0.{decimals}") if decimals else 0)
    if mixed_num is not None:
        x += Fraction(int(mixed_num), int(mixed_den))
    elif den is not None:
        x /= int(den)
    return x / 100 if percent else x


def stated(printed: str) -> list[Fraction | None]:
    """The numbers a printed value states: its one number, or each number of a formula or an
    equation ("1-1/4 d", "Rn = 1.2 lc t Fu <= 2.4 d t Fu")."""
    one = value(printed)
    if one is not None:
        return [one]
    return [value(t) for t in re.findall(r"\d[\d.,]*(?:-\d+/\d+|/\d+)?%?", printed)]


def missing(printed: str, span: str) -> list[str]:
    """The numbers of printed that the span does not state; [] when the span states them all.
    One number is looked for among the span's values with labels skipped; a formula's
    numbers among all of them."""
    found = numbers(span, labels=value(printed) is None)
    return [str(x) for x in stated(printed) if x is None or x not in found]


def in_d(printed: str, d: Fraction) -> Fraction | None:
    """A table formula in the bolt diameter d at d: "d + 1/8", "1-1/4 d", "1.25d", "2.5d"."""
    text = printed.replace(" ", "")
    m = re.fullmatch(r"\(?d\+([\d./-]+)\)?", text)
    if m and value(m.group(1)) is not None:
        return d + value(m.group(1))
    m = re.fullmatch(r"([\d./-]+)(?:×|x|\*)?d", text)
    if m and value(m.group(1)) is not None:
        return value(m.group(1)) * d
    return None


# --- Documents ---------------------------------------------------------------------------------

def sources_dir(given: str | None = None) -> Path:
    return Path(given or os.environ.get(ENV) or DEFAULT_SOURCES)


@lru_cache(maxsize=None)
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


@lru_cache(maxsize=None)
def _reader(path: Path):
    import pypdf
    return pypdf.PdfReader(str(path))


@lru_cache(maxsize=None)
def page_text(path: Path, page: int) -> str:
    """The normalized text of a 1-based page."""
    return normalize(_reader(path).pages[page - 1].extract_text() or "")


XLSX = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


@lru_cache(maxsize=None)
def _workbook(path: Path) -> tuple[dict[str, str], list[str]]:
    """(sheet name -> part path, shared strings) of an xlsx file."""
    with zipfile.ZipFile(path) as book:
        rels = ElementTree.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        target = {r.get("Id"): r.get("Target") for r in rels}
        root = ElementTree.fromstring(book.read("xl/workbook.xml"))
        rid = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        sheets = {s.get("name"): "xl/" + target[s.get(rid)].lstrip("/").removeprefix("xl/")
                  for s in root.iter(f"{XLSX}sheet")}
        strings = []
        if "xl/sharedStrings.xml" in book.namelist():
            for si in ElementTree.fromstring(book.read("xl/sharedStrings.xml")).iter(f"{XLSX}si"):
                strings.append("".join(t.text or "" for t in si.iter(f"{XLSX}t")))
    return sheets, strings


@lru_cache(maxsize=None)
def _sheet(path: Path, sheet: str) -> dict[str, str]:
    """cell reference -> its text, every cell of one sheet."""
    sheets, strings = _workbook(path)
    with zipfile.ZipFile(path) as book:
        root = ElementTree.fromstring(book.read(sheets[sheet]))
    cells = {}
    for c in root.iter(f"{XLSX}c"):
        v = c.find(f"{XLSX}v")
        if v is None or v.text is None:
            inline = c.find(f"{XLSX}is")
            cells[c.get("r")] = "".join(t.text or "" for t in inline.iter(f"{XLSX}t")) if inline is not None else ""
        else:
            cells[c.get("r")] = strings[int(v.text)] if c.get("t") == "s" else v.text
    return cells


def cell_text(path: Path, where: str) -> str:
    """The text of a cell "<sheet>!<ref>", as the workbook stores it."""
    sheet, _, ref = where.rpartition("!")
    return _sheet(path, sheet).get(ref, "")


def cell_number(text: str) -> str:
    """A numeric cell as the workbook displays it: the shortest decimal that is the same
    double ("0.35499999999999998" is 0.355). Other text as it is."""
    try:
        return repr(float(text)).removesuffix(".0")
    except ValueError:
        return text


# --- Checks --------------------------------------------------------------------------------------

def read_anchors(path: Path = ANCHORS) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def span_text(anchor: dict, folder: Path) -> str:
    if anchor["kind"] == "cell":
        return normalize(cell_text(folder / anchor["doc"], anchor["page"]))
    start, end = anchor["span"]
    return page_text(folder / anchor["doc"], anchor["page"])[start:end]


def problems(anchor: dict, folder: Path) -> list[str]:
    """What fails for one anchor against the documents in folder; [] when it holds."""
    if anchor["kind"] in ("designation", "absent"):
        return []
    path = folder / anchor["doc"]
    if not path.exists():
        return [f"{anchor['doc']} is not in {folder}"]
    if sha256(path) != anchor["doc_sha256"]:
        return [f"{anchor['doc']} has sha256 {sha256(path)}, not the anchored {anchor['doc_sha256']}"]
    span = span_text(anchor, folder)
    if fingerprint(span) != anchor["span_sha256"]:
        return [f"page {anchor['page']} span {anchor.get('span')} no longer has the anchored fingerprint"]
    printed = anchor["printed"]
    if anchor["kind"] == "cell":
        return [] if cell_number(span) == printed else [f"cell {anchor['page']} reads {span!r}, not {printed!r}"]
    out = []
    if anchor.get("label") and normalize(anchor["label"]) not in span:
        out.append(f"label {anchor['label']} is not in the span")
    if anchor["kind"] == "visual":
        return out
    absent = missing(printed, span)
    if absent:
        out.append(f"printed {printed!r}: {', '.join(absent)} not among the span's numbers")
    return out


def verify(anchors: list[dict], folder: Path) -> dict[str, list[str]]:
    """anchor id -> its problems, for every anchor that has one."""
    return {a["id"]: p for a in anchors for p in [problems(a, folder)] if p}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sources", help=f"folder holding the documents (default ${ENV}, else {DEFAULT_SOURCES})")
    args = parser.parse_args(argv)
    folder = sources_dir(args.sources)
    anchors = read_anchors()
    failed = verify(anchors, folder)
    for key, found in failed.items():
        for p in found:
            print(f"{key}: {p}")
    kinds = {k: sum(1 for a in anchors if a["kind"] == k) for k in KINDS}
    print(f"{len(anchors)} anchors ({', '.join(f'{n} {k}' for k, n in kinds.items())}); "
          f"{len(failed)} fail against {folder}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
