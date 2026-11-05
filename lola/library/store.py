"""The certificate library. Untrusted: it stores evidence; the kernel re-checks every
reuse against the query's own statement.

Keys:
  shape hash   sha256 of the canonical statement with every RangeHyp range and label
               erased and symbols renamed by order of first occurrence. Two statements
               with the same shape differ only in their boxes.
  family key   sha256 of (model ids with source hashes, canonical statement including
               ranges). This is "content hash of the model definition and the box".

Layout on disk:  <root>/<shape-hex>/<family-hex>.json   (certs.CertificateFile envelope
plus a "models" list). Writes are atomic renames; storing the same family twice is a
no-op.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from ..kernel import Evidence, Interval, Statement


@dataclass(frozen=True)
class FamilyEntry:
    family_key: str
    shape_hash: str
    statement: Statement
    evidence: Evidence
    models: tuple[str, ...]
    box: tuple[tuple[str, Interval], ...]     # canonical symbol -> range


def shape_hash(statement: Statement) -> str:
    raise NotImplementedError


def canonical_renaming(statement: Statement) -> dict[str, str]:
    """Original symbol -> canonical symbol ("v0", "v1", ...) by order of first occurrence
    in the canonical JSON of the goal."""
    raise NotImplementedError


class Library:
    """EvidenceSource and store. `offer` finds a family whose box contains the query's box
    (after canonical renaming) and returns transported evidence."""

    name = "library"

    def __init__(self, root: str | Path) -> None:
        raise NotImplementedError

    def add(self, entry: FamilyEntry) -> None:
        raise NotImplementedError

    def lookup(self, statement: Statement) -> FamilyEntry | None:
        """Containment check: same shape hash, every query RangeHyp range inside the
        family's range for the same canonical symbol. Picks the smallest containing box
        (fewest leaves to re-check)."""
        raise NotImplementedError

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        raise NotImplementedError

    def stats(self) -> dict:
        """hits, misses, families, total leaves: for the benchmark and the gym logs."""
        raise NotImplementedError
