"""Decks: the makeable set exported as JSON records. Untrusted.

A deck is what a manufacturer or a shop would publish (the PDK analogue): every property
evaluated to an interval, plus the published table values from the standards (IEC 60228
maximum resistances, ISO 898-1 stress areas, the k = 115 of IEC 60364-4-43) recorded
next to them. Verdicts never read a deck for a derivable property; the consistency
checker reads decks to catch corrupted or wrong records, and a third-party deck's Stated
ratings enter a check only after the checker passes them.

Records. A constant "<group>.<name>" is entry "const.<group>", prop "<name>", so the key
"<entry>.<prop>" of every record equals the premise key Registry.expand uses. Published
values attach to the constant group they check. A series entry is a template, not a
makeable thing, so only its sizes appear. A prop never contains a dot.

Provenance grammar, one string per record:
    "derived:<formula over premise keys>"
    "stated:<tag>:<owner>:<source>"     constants and stated properties
    "published:<standard and table>"

Entries. Every registry entry has one row in "entries": its id ("const.<name>" for a
constant), its version as a decimal string, its source and its errata, oldest first, each
{"date", "was", "now"} (model.Provenance). A derived or stated record belongs to the
entry DeckRecord.registry_entry names, and the consistency checker reports a record whose
entry has no row, and a row whose version is not one more than its errata count.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from fractions import Fraction
from functools import cached_property
from typing import Iterator, Mapping

from ..kernel import Interval, enclose, free_syms, parse_q
from ..premises import ALLOWED_TAGS, LabelKind, Tag
from .catalog import build_registry
from .model import Constant, Derived, Erratum, Registry, Stated, render

FORMAT = "petra-deck/1"
_RECORD_KEYS = frozenset({"entry", "prop", "lo", "hi", "unit", "provenance"})
_ENTRY_KEYS = frozenset({"entry", "version", "source", "errata"})
_ERRATUM_KEYS = frozenset({"date", "was", "now"})
_VERSION = re.compile(r"[1-9][0-9]*")
_TAGS = frozenset(t.value for t in ALLOWED_TAGS[LabelKind.REGISTRY])


@dataclass(frozen=True)
class DeckRecord:
    entry: str
    prop: str
    value: Interval
    unit: str
    provenance: str          # "derived:<formula>", "stated:<tag>:<owner>:<source>", "published:<standard table>"

    @property
    def registry_entry(self) -> str:
        """The id of the registry entry the record belongs to: the constant itself for a
        constant record ("const.cu" "rho20" -> "const.cu.rho20"), else its entry."""
        return f"{self.entry}.{self.prop}" if self.entry.startswith("const.") else self.entry


@dataclass(frozen=True)
class DeckEntry:
    """One entry's provenance as a deck carries it. Unchecked on read: check_deck reports
    what is wrong with it."""

    entry: str
    version: int
    source: str
    errata: tuple[Erratum, ...]


@dataclass(frozen=True)
class Deck:
    format: str              # "petra-deck/1"
    records: tuple[DeckRecord, ...]
    entries: tuple[DeckEntry, ...]

    def get(self, entry: str, prop: str) -> DeckRecord | None:
        return self._index.get((entry, prop))

    def entry(self, id: str) -> DeckEntry | None:
        return self._entries.get(id)

    @cached_property
    def _index(self) -> Mapping[tuple[str, str], DeckRecord]:
        return {(r.entry, r.prop): r for r in self.records}

    @cached_property
    def _entries(self) -> Mapping[str, DeckEntry]:
        return {e.entry: e for e in self.entries}


class DeckError(ValueError):
    """A deck file that does not parse. `petra registry check` exits 3 on it."""


PUBLISHED: tuple[tuple[str, str, str, Fraction, str], ...] = (
    *((f"const.iso261.{size}", "As_table", "m2", Fraction(area) / 10**6,
       "ISO 898-1:2013 Table 4, nominal stress area As,nom")
      for size, area in (("M6", "20.1"), ("M8", "36.6"), ("M10", "58.0"), ("M12", "84.3"),
                         ("M16", "157"), ("M20", "245"), ("M24", "353"))),
    ("const.pvc", "k_cu_table", "A s0.5/m2", Fraction(115) * 10**6,
     "IEC 60364-4-43:2008 Table 43A, copper, PVC up to 300 mm2: k = 115 A s0.5/mm2"),
    ("const.cu", "K_table", "A s0.5/m2", Fraction(226) * 10**6,
     "IEC 60949:1988 Table 1, copper: K = 226 A s0.5/mm2"),
)
"""(entry, prop, unit, value, source) values as the standards tabulate them, rounded as
printed. The consistency relations check them against the physics."""


def stated_provenance(tag: Tag, owner: str, source: str) -> str:
    return f"stated:{tag.value}:{owner}:{source}"


def provenance_problem(provenance: str) -> str | None:
    """What is wrong with a record's provenance string, or None."""
    kind, _, rest = provenance.partition(":")
    if kind in ("derived", "published"):
        return None if rest.strip() else f"{kind} record names no {'formula' if kind == 'derived' else 'source'}"
    if kind != "stated":
        return f"unknown provenance kind {kind!r}"
    fields = rest.split(":", 2)
    if len(fields) != 3:
        return "stated record needs tag:owner:source"
    tag, owner, source = fields
    if tag not in _TAGS:
        return f"stated record has tag {tag!r}, not one of {', '.join(sorted(_TAGS))}"
    if not owner.strip():
        return "stated record names no owner"
    if not source.strip():
        return "stated record names no source"
    return None


def build_deck(registry: Registry | None = None) -> Deck:
    """Evaluate every property with an interval enclosure and add the published records.
    With no registry, the shipped one."""
    registry = registry if registry is not None else build_registry()
    records = [_constant_record(c) for c in registry.constants.values()]
    for entry_id, props in _entries(registry):
        records += [_property_record(registry, entry_id, prop) for prop in props]
    for process in registry.processes.values():
        for effect in process.effects:
            records.append(_value_record(process.id, f"effect_{effect.material_family}_{effect.prop}", effect.factor))
    for env in registry.environments.values():
        records.append(_value_record(env.id, "ambient", env.ambient))
    groups = {r.entry for r in records if r.entry.startswith("const.")}
    records += [DeckRecord(entry, prop, Interval(value, value), unit, f"published:{source}")
                for entry, prop, unit, value, source in PUBLISHED if entry in groups]
    entries = (DeckEntry(id, e.provenance.version, e.provenance.source, e.provenance.errata) for id, e in registry.entries())
    return Deck(FORMAT, tuple(sorted(records, key=lambda r: (r.entry, r.prop))), tuple(sorted(entries, key=lambda e: e.entry)))


def write_deck(deck: Deck, path: str) -> None:
    body = {"format": deck.format, "records": [
        {"entry": r.entry, "prop": r.prop, "lo": str(r.value.lo), "hi": str(r.value.hi), "unit": r.unit,
         "provenance": r.provenance}
        for r in deck.records
    ], "entries": [
        {"entry": e.entry, "version": str(e.version), "source": e.source,
         "errata": [{"date": x.date, "was": x.was, "now": x.now} for x in e.errata]}
        for e in deck.entries
    ]}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(body, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def read_deck(path: str) -> Deck:
    """Strict parse; rationals in kernel canonical form. Raises DeckError."""
    try:
        with open(path, encoding="utf-8") as f:
            body = json.loads(f.read(), parse_float=_no_number, parse_int=_no_number, parse_constant=_no_number)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, DeckError) as exc:
        raise DeckError(f"{path}: {exc}") from None
    if not isinstance(body, dict) or set(body) != {"format", "records", "entries"}:
        raise DeckError(f"{path}: a deck is an object with exactly the keys format, records and entries")
    if body["format"] != FORMAT:
        raise DeckError(f"{path}: format {body['format']!r} is not {FORMAT}")
    if not isinstance(body["records"], list) or not isinstance(body["entries"], list):
        raise DeckError(f"{path}: records and entries must be lists")
    records, seen = [], set()
    for i, raw in enumerate(body["records"]):
        record = _parse_record(raw, f"{path}: record {i}")
        if (record.entry, record.prop) in seen:
            raise DeckError(f"{path}: record {i}: {record.entry}.{record.prop} appears twice")
        seen.add((record.entry, record.prop))
        records.append(record)
    entries: dict[str, DeckEntry] = {}
    for i, raw in enumerate(body["entries"]):
        entry = _parse_entry(raw, f"{path}: entry {i}")
        if entry.entry in entries:
            raise DeckError(f"{path}: entry {i}: {entry.entry} appears twice")
        entries[entry.entry] = entry
    return Deck(FORMAT, tuple(records), tuple(entries.values()))


def _entries(registry: Registry) -> Iterator[tuple[str, list[str]]]:
    """(entry id, its props including inherited ones) for every makeable entry."""
    templates = {p.series for p in registry.parts.values() if p.series is not None}
    for m in registry.materials.values():
        yield m.id, list(m.props)
    for p in registry.parts.values():
        if p.id not in templates:
            inherited = registry.parts[p.series].props if p.series is not None else {}
            yield p.id, list(dict.fromkeys([*p.props, *inherited]))
    for process in registry.processes.values():
        yield process.id, list(process.props)


def _constant_record(c: Constant) -> DeckRecord:
    group, _, name = c.name.rpartition(".")
    return DeckRecord(f"const.{group}", name, c.value, c.unit, stated_provenance(c.tag, c.owner, c.source))


def _property_record(registry: Registry, entry_id: str, prop: str) -> DeckRecord:
    found = registry.property(entry_id, prop)
    if isinstance(found, Stated):
        return _value_record(entry_id, prop, found)
    expr = registry.expand(entry_id, prop)
    box = {key: registry.fact(key).value for key in free_syms(expr)}
    return DeckRecord(entry_id, prop, enclose(expr, box), found.unit, f"derived:{render(expr)}")


def _value_record(entry_id: str, prop: str, value: Stated | Derived) -> DeckRecord:
    if isinstance(value, Derived):
        raise TypeError(f"{entry_id}.{prop}: only stated values are exported without a registry")
    return DeckRecord(entry_id, prop, value.value, value.unit, stated_provenance(value.tag, value.owner, value.standard))


def _no_number(text: str) -> object:
    raise DeckError(f"JSON number {text} where a deck needs a rational string")


def _parse_q(text: object, where: str) -> Fraction:
    try:
        return parse_q(text)
    except ValueError:
        raise DeckError(f"{where}: {text!r} is not a canonical rational (\"n\" or reduced \"p/q\")") from None


def _parse_record(raw: object, where: str) -> DeckRecord:
    if not isinstance(raw, dict) or set(raw) != _RECORD_KEYS:
        raise DeckError(f"{where}: a record has exactly the keys {', '.join(sorted(_RECORD_KEYS))}")
    for key in ("entry", "prop", "unit", "provenance"):
        if not isinstance(raw[key], str):
            raise DeckError(f"{where}: {key} must be a string")
    if not raw["entry"] or not raw["prop"] or "." in raw["prop"]:
        raise DeckError(f"{where}: entry and prop must be non-empty and prop must not contain a dot")
    lo, hi = _parse_q(raw["lo"], where), _parse_q(raw["hi"], where)
    if lo > hi:
        raise DeckError(f"{where}: lo {raw['lo']} is above hi {raw['hi']}")
    return DeckRecord(raw["entry"], raw["prop"], Interval(lo, hi), raw["unit"], raw["provenance"])


def _parse_entry(raw: object, where: str) -> DeckEntry:
    if not isinstance(raw, dict) or set(raw) != _ENTRY_KEYS:
        raise DeckError(f"{where}: an entry has exactly the keys {', '.join(sorted(_ENTRY_KEYS))}")
    if not all(isinstance(raw[key], str) for key in ("entry", "version", "source")) or not raw["entry"]:
        raise DeckError(f"{where}: entry, version and source must be strings, and entry non-empty")
    if not _VERSION.fullmatch(raw["version"]):
        raise DeckError(f"{where}: version {raw['version']!r} is not a positive integer without leading zeros")
    if not isinstance(raw["errata"], list):
        raise DeckError(f"{where}: errata must be a list")
    errata = []
    for e in raw["errata"]:
        if not isinstance(e, dict) or set(e) != _ERRATUM_KEYS or not all(isinstance(v, str) for v in e.values()):
            raise DeckError(f"{where}: an erratum has exactly the string keys {', '.join(sorted(_ERRATUM_KEYS))}")
        errata.append(Erratum(e["date"], e["was"], e["now"]))
    return DeckEntry(raw["entry"], int(raw["version"]), raw["source"], tuple(errata))
