"""Which verdicts rest on a registry entry: `petra registry recall ID [FILES...]`.

A verdict's footprint names every registry value it rests on as "reg:<key>" with the
version of the entry the value came from (registry.model.Provenance). Recall checks each
design, or reads a saved `petra check --json` report, and keeps the verdicts whose
footprint names a key of the recalled entry. It reads footprints only, so it finds a
design exactly when its verdict depends on the entry's values; a design that names the
entry but whose checks never read its values is not listed.

ID is a registry entry ("cable.cu_pvc", "const.cu.rho20"), a premise key
("cable.cu_pvc.rho20_max"), a common name a design may use ("A325"), or a prefix of entry
ids ending at a dot ("const.iec60228" for every IEC 60228 constant). A key matches when it
equals ID or starts with ID and a dot.

A report saved before an entry gained an erratum names the older version, and recall
marks the premise stale: that verdict was reached on the value the erratum replaced.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .lang import LolaSyntaxError, LoweringError, load_design
from .models.base import ComponentError
from . import grid
from .pipeline import check_design
from .registry import OutsideMakeableSet, Provenance, Registry
from .solvers import SolverSource


class RecallError(ValueError):
    """An ID that names no registry entry, key or prefix, or no FILES and no examples/."""


@dataclass(frozen=True)
class Rested:
    """One premise of a verdict that the recalled entry supplies."""

    label: str                 # "reg:cable.cu_pvc.rho20_max"
    version: int | None        # the version the verdict was reached on; None in a report saved before versions
    current: int | None        # the entry's version now; None when the registry no longer holds the key

    @property
    def stale(self) -> bool:
        return self.current is not None and self.version != self.current


@dataclass(frozen=True)
class RecalledVerdict:
    claim: str
    status: str
    premises: tuple[Rested, ...]


@dataclass(frozen=True)
class RecalledDesign:
    file: str
    design: str
    status: str
    verdicts: tuple[RecalledVerdict, ...]


@dataclass(frozen=True)
class Recall:
    id: str
    entries: tuple[tuple[str, Provenance], ...]   # the registry entries ID covers, by id
    designs: tuple[RecalledDesign, ...]           # those whose verdicts rest on ID, in file order
    checked: int                                  # designs and reports read
    errors: tuple[tuple[str, str], ...]           # (file, why it could not be read)


def recall(registry: Registry, id: str, paths: Iterable[str | Path] = ()) -> Recall:
    """Recall ID over `paths`: .petra files are checked with the solvers, each against the
    .card file beside it, .json files are read as saved reports, and directories are
    searched for .petra files. With no paths, examples/ in the working directory."""
    id = registry.canonical(id)
    entries = covered(registry, id)
    files = _files(paths)
    designs, errors = [], []
    for path in files:
        try:
            body = _report(registry, path)
        except (LolaSyntaxError, LoweringError, ComponentError, OSError, UnicodeDecodeError, ValueError) as exc:
            errors.append((path.as_posix(), str(exc)))
            continue
        found = _rests(registry, id, body)
        if found.verdicts:
            designs.append(RecalledDesign(path.as_posix(), found.design, found.status, found.verdicts))
    return Recall(id, entries, tuple(designs), len(files) - len(errors), tuple(errors))


def covered(registry: Registry, id: str) -> tuple[tuple[str, Provenance], ...]:
    """(entry id, provenance) for every entry ID covers: the entry ID names, the entry of
    the key ID names, or every entry under the prefix ID. Raises RecallError for none."""
    ids = [entry_id for entry_id, _ in registry.entries()]
    if id in ids:
        chosen = [id]
    else:
        try:
            registry.fact(id)
            chosen = [_entry_id(registry, id)]
        except OutsideMakeableSet:
            chosen = [entry_id for entry_id in ids if entry_id.startswith(id + ".")]
    if not chosen:
        raise RecallError(registry.unknown(id, "entry, premise key or id prefix", ids))
    return tuple((entry_id, registry.entry(entry_id).provenance) for entry_id in chosen)


def to_json(found: Recall) -> Mapping[str, Any]:
    """{"id", "entries": [{"entry", "version", "source", "errata": [{"date", "was",
    "now"}]}], "designs": [{"file", "design", "status", "verdicts": [{"claim", "status",
    "premises": [{"label", "version", "current", "stale"}]}]}], "checked", "errors":
    [{"file", "error"}]}."""
    return {
        "id": found.id,
        "entries": [{"entry": entry_id, "version": p.version, "source": p.source,
                     "errata": [{"date": e.date, "was": e.was, "now": e.now} for e in p.errata]}
                    for entry_id, p in found.entries],
        "designs": [{"file": d.file, "design": d.design, "status": d.status,
                     "verdicts": [{"claim": v.claim, "status": v.status,
                                   "premises": [{"label": r.label, "version": r.version, "current": r.current,
                                                 "stale": r.stale} for r in v.premises]}
                                  for v in d.verdicts]}
                    for d in found.designs],
        "checked": found.checked,
        "errors": [{"file": f, "error": e} for f, e in found.errors],
    }


_LISTED = 20


def render(found: Recall) -> str:
    lines = []
    for entry_id, p in found.entries[:_LISTED]:
        lines.append(f"entry     {entry_id}  version {p.version}  ({p.source})")
        for e in p.errata:
            lines.append(f"  erratum {e.date}  was {e.was}")
            lines.append(f"{'':22}now {e.now}")
    if len(found.entries) > _LISTED:
        lines.append(f"entry     and {len(found.entries) - _LISTED} more under {found.id} (--json lists each)")
    for d in found.designs:
        lines.append(f"{d.status:<9} {d.file}  {d.design}")
        width = max(len(v.claim) for v in d.verdicts)
        for v in d.verdicts:
            lines.append(f"  {v.claim:<{width}}  {v.status:<8} {', '.join(_rested_text(r) for r in v.premises)}")
    lines += [f"error     {f}: {e}" for f, e in found.errors]
    lines.append(f"{len(found.designs)} of {found.checked} designs rest on {found.id}")
    return "\n".join(lines)


def _rested_text(r: Rested) -> str:
    if r.current is None:
        return f"{r.label} (version {r.version}; the registry no longer holds it)"
    if r.version is None:
        return f"{r.label} (version not recorded; now {r.current})"
    if r.stale:
        return f"{r.label} (version {r.version}, now {r.current}: checked before an erratum)"
    return f"{r.label} (version {r.version})"


@dataclass(frozen=True)
class _Found:
    design: str
    status: str
    verdicts: tuple[RecalledVerdict, ...]


def _rests(registry: Registry, id: str, body: Mapping[str, Any]) -> _Found:
    verdicts = []
    for v in body["verdicts"]:
        rested = tuple(Rested(p["label"], p.get("version"), _current(registry, p["label"][len("reg:"):]))
                       for p in v["footprint"] if _matches(p["label"], id))
        if rested:
            verdicts.append(RecalledVerdict(v["claim"], v["status"], rested))
    return _Found(body["design"], body["status"], tuple(verdicts))


def _matches(label: str, id: str) -> bool:
    if not label.startswith("reg:"):
        return False
    key = label[len("reg:"):]
    return key == id or key.startswith(id + ".")


def _current(registry: Registry, key: str) -> int | None:
    try:
        registry.fact(key)
        return registry.entry_of(key).provenance.version
    except OutsideMakeableSet:
        return None


def _entry_id(registry: Registry, key: str) -> str:
    return key if key.startswith("const.") else key.rpartition(".")[0]


def _files(paths: Iterable[str | Path]) -> list[Path]:
    given = [Path(p) for p in paths]
    if not given:
        if not Path("examples").is_dir():
            raise RecallError("no FILES given and no examples/ directory here")
        given = [Path("examples")]
    files: list[Path] = []
    for path in given:
        files += sorted(path.rglob("*.petra")) if path.is_dir() else [path]
    return list(dict.fromkeys(files))


def _report(registry: Registry, path: Path) -> Mapping[str, Any]:
    """The `petra check --json` body of a .petra file (checked now, against the card beside
    it) or of a saved report."""
    if path.suffix != ".json":
        design = load_design(path, registry)
        if grid.owner(design) is not None:
            return {"design": design.name, "status": "UNKNOWN", "verdicts": []}      # a deck's design reads no registry entry
        report = check_design(design, registry, (SolverSource(),), path=path.as_posix())
        return report.to_json()
    body = json.loads(path.read_text(encoding="utf-8"))
    if not (isinstance(body, dict) and isinstance(body.get("design"), str) and isinstance(body.get("status"), str)
            and isinstance(body.get("verdicts"), list)
            and all(isinstance(v, dict) and isinstance(v.get("claim"), str) and isinstance(v.get("status"), str)
                    and isinstance(v.get("footprint"), list)
                    and all(isinstance(p, dict) and isinstance(p.get("label"), str) for p in v["footprint"])
                    for v in body["verdicts"])):
        raise ValueError("not a `petra check --json` report")
    return body
