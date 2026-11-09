"""The certificate library. Untrusted: it stores family theorems' evidence and offers a
query an Instance of the family whose box contains it. The kernel checks the family once
per process and, for every query, that the query is the family statement renamed with a
narrower box.

Keys:
  shape hash   sha256 of the canonical statement with every RangeHyp range and label
               erased and symbols renamed by order of first occurrence. Two statements
               with the same shape differ only in their boxes.
  family key   sha256 of (model ids with source hashes, canonical statement including
               ranges). This is "content hash of the model definition and the box".

Layout on disk:  <root>/<shape-hex>/<family-hex>.json   (certs.CertificateFile envelope
plus a "models" list). Writes are atomic renames; storing the same family twice is a
no-op. A file whose name does not match its content, or that does not decode, is never
used: it is foreign or corrupt, and it is counted in stats()["unreadable"].
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from .. import __version__
from ..certs import CertificateFile, decode_certificate, encode_certificate
from ..kernel import Evidence, Instance, Interval, Leaf, RangeHyp, Split, Statement, canonical_text, encode_statement, statement_hash

_HEX = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class FamilyEntry:
    family_key: str
    shape_hash: str
    statement: Statement
    evidence: Evidence
    models: tuple[str, ...]
    box: tuple[tuple[str, Interval], ...]     # canonical symbol -> range


def family_entry(statement: Statement, evidence: Evidence, models: Iterable[str]) -> FamilyEntry:
    """The entry for evidence the kernel accepted for `statement`, keyed by the models
    the statement rests on."""
    models = tuple(sorted(set(models)))
    shape, renaming = _canonical(statement)
    box = tuple(sorted((renaming[h.sym], Interval(h.lo, h.hi)) for h in statement.hyps if isinstance(h, RangeHyp)))
    key = _digest({"models": list(models), "statement": encode_statement(statement)})
    return FamilyEntry(key, shape, statement, evidence, models, box)


def shape_hash(statement: Statement) -> str:
    return _canonical(statement)[0]


def canonical_renaming(statement: Statement) -> dict[str, str]:
    """Original symbol -> canonical symbol ("v0", "v1", ...) by order of first occurrence
    in the canonical JSON of the goal. A DefinedHyp's definition is read right after the
    goal names its symbol, so the symbols only a definition uses are canonical too."""
    return _canonical(statement)[1]


def _canonical(statement: Statement) -> tuple[str, dict[str, str]]:
    """(shape hash, canonical renaming) from one encoding of the statement. A name gets
    its canonical name when first visited, so one walk both orders and renames."""
    obj = encode_statement(statement)
    names: dict[str, str] = {}
    order: list[str] = []

    def visit(name: str) -> str:
        if name not in names:
            names[name] = f"v{len(names)}"
            order.append(name)
        return names[name]

    goal = _map_syms(obj["goal"], visit)
    definitions = {h["sym"]: h["definition"] for h in obj["hyps"] if h["t"] == "defined_hyp"}
    renamed: dict[str, Any] = {}
    seen = 0
    while seen < len(order):
        if order[seen] in definitions:
            renamed[order[seen]] = _map_syms(definitions[order[seen]], visit)
        seen += 1
    for sym in sorted(h.sym for h in statement.hyps):
        visit(sym)
    hyps = sorted([names[h["sym"]], renamed.get(h["sym"])] for h in obj["hyps"])
    return _digest({"goal": goal, "hyps": hyps}), names


def _map_syms(node: Any, fn: Callable[[str], str]) -> Any:
    """The JSON term with every symbol name replaced by fn(name), visiting names in the
    order canonical text lists them (keys sorted). A symbol is a "sym" node's name or a
    string "sym" field (a bound random variable)."""
    if isinstance(node, list):
        return [_map_syms(x, fn) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key in sorted(node):
        value = node[key]
        is_name = (key == "name" and node.get("t") == "sym") or (key == "sym" and isinstance(value, str))
        out[key] = fn(value) if is_name else _map_syms(value, fn)
    return out


def _digest(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_text(obj).encode("ascii")).hexdigest()


def leaf_count(term: object) -> int:
    """Leaves over every partition in a piece of evidence: the cells a kernel check
    walks. Evidence without a partition has none."""
    if isinstance(term, Leaf):
        return 1
    if isinstance(term, Split):
        return leaf_count(term.left) + leaf_count(term.right)
    if isinstance(term, tuple):
        return sum(leaf_count(t) for t in term if not isinstance(t, (int, str)))
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        return sum(leaf_count(getattr(term, f.name)) for f in dataclasses.fields(term))
    return 0


@dataclass(frozen=True)
class _Held:
    entry: FamilyEntry
    renaming: dict[str, str]
    leaves: int


class Library:
    """EvidenceSource and store. `offer` finds a family whose box contains the query's box
    (after canonical renaming) and returns an Instance of it under that renaming."""

    name = "library"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._held: dict[Path, tuple[tuple[int, int], _Held | None]] = {}
        self._hits = 0
        self._misses = 0

    def add(self, entry: FamilyEntry) -> None:
        path = self._path(entry.shape_hash, entry.family_key)
        held = self._read(path) if path.exists() else None
        if held is not None and held.entry == entry:
            return
        cert = CertificateFile(statement_hash(entry.statement), entry.statement, entry.evidence, {"source": "library", "petra": __version__})
        text = canonical_text({**encode_certificate(cert), "models": list(entry.models)}) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def lookup(self, statement: Statement) -> FamilyEntry | None:
        """Containment check: same shape hash, every query RangeHyp range inside the
        family's range for the same canonical symbol. Picks the family whose evidence has
        the fewest leaves, the cheapest for the kernel to check the one time a process
        needs it."""
        found = self._match(statement)
        return None if found is None else found[0]

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        """An Instance of the lookup's family, renaming each family symbol to the query
        symbol with the same canonical name."""
        found = self._match(statement)
        if found is None:
            self._misses += 1
            return ()
        self._hits += 1
        entry, renaming = found
        return (Evidence(Instance(entry.statement, entry.evidence, tuple(sorted(renaming.items())))),)

    def entries(self) -> tuple[FamilyEntry, ...]:
        """Every readable entry, sorted by family key."""
        held = (self._read(p, s) for d in self._dirs() for p, s in self._files(d))
        return tuple(sorted((h.entry for h in held if h is not None), key=lambda e: e.family_key))

    def stats(self) -> dict:
        """hits, misses, families, total leaves: for the benchmark and the gym logs."""
        files = [f for d in self._dirs() for f in self._files(d)]
        held = [h for h in (self._read(p, s) for p, s in files) if h is not None]
        return {
            "hits": self._hits,
            "misses": self._misses,
            "families": len(held),
            "leaves": sum(leaf_count(h.entry.evidence) for h in held),
            "unreadable": len(files) - len(held),
        }

    def _match(self, statement: Statement) -> tuple[FamilyEntry, dict[str, str]] | None:
        """The containing family whose evidence has the fewest leaves, and the renaming
        from its symbols, bound ones included, to the query's."""
        shape, mine = _canonical(statement)
        canonical_box = {mine[h.sym]: Interval(h.lo, h.hi) for h in statement.hyps if isinstance(h, RangeHyp)}
        back = {c: s for s, c in mine.items()}
        best = None
        for path, stamp in self._files(self.root / shape.removeprefix("sha256:")):
            held = self._read(path, stamp)
            if held is None or not _contains(dict(held.entry.box), canonical_box):
                continue
            if best is None or (held.leaves, held.entry.family_key) < best[0]:
                best = ((held.leaves, held.entry.family_key), held)
        if best is None:
            return None
        held = best[1]
        return held.entry, {f: back[c] for f, c in held.renaming.items()}

    def _read(self, path: Path, stamp: tuple[int, int] | None = None) -> _Held | None:
        """The entry at `path`, parsed again only when its modification time or size
        changed. A stale cache costs at worst a failed re-check, never a false PASS."""
        if stamp is None:
            try:
                stamp = _stamp(path.stat())
            except OSError:
                return None
        cached = self._held.get(path)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        held = _load(path)
        self._held[path] = (stamp, held)
        return held

    def _dirs(self) -> list[Path]:
        try:
            with os.scandir(self.root) as found:
                return sorted(Path(d.path) for d in found if d.is_dir() and _HEX.fullmatch(d.name))
        except OSError:
            return []

    @staticmethod
    def _files(directory: Path) -> list[tuple[Path, tuple[int, int]]]:
        """(path, stamp) for each entry file; scandir carries the stat, so a lookup costs
        one directory read rather than a stat per file."""
        try:
            with os.scandir(directory) as found:
                return sorted((Path(f.path), _stamp(f.stat())) for f in found
                              if f.name.endswith(".json") and _HEX.fullmatch(f.name[:-5]) and f.is_file())
        except OSError:
            return []

    def _path(self, shape: str, key: str) -> Path:
        return self.root / shape.removeprefix("sha256:") / f"{key.removeprefix('sha256:')}.json"


def _stamp(st: os.stat_result) -> tuple[int, int]:
    return st.st_mtime_ns, st.st_size


def _contains(family: dict[str, Interval], query: dict[str, Interval]) -> bool:
    return family.keys() == query.keys() and all(family[c].lo <= q.lo and q.hi <= family[c].hi for c, q in query.items())


def _load(path: Path) -> _Held | None:
    """The entry a library file holds, or None when the file is malformed or sits under
    a name its content does not hash to."""
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        models = obj.pop("models")
        if not (isinstance(models, list) and all(isinstance(m, str) for m in models)):
            return None
        cert = decode_certificate(obj)
        entry = family_entry(cert.statement, cert.evidence, models)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    if path.stem != entry.family_key.removeprefix("sha256:") or path.parent.name != entry.shape_hash.removeprefix("sha256:"):
        return None
    return _Held(entry, canonical_renaming(entry.statement), leaf_count(entry.evidence))
