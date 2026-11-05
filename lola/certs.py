"""Certificate files. Untrusted storage: the kernel re-checks everything it reads.

Envelope (JSON, canonical text on disk):
    {
      "format": "lola-cert/0",
      "kernel": "lola-kernel/0",
      "statement_hash": "sha256:...",
      "statement": <kernel statement JSON>,
      "evidence": <kernel evidence JSON>,
      "producer": {"source": "solver:linear", "lola": "0.1.0"}
    }

The statement is stored so a Lean kernel, or a human, can check the file on its own.
LoLa's pipeline never uses the stored statement to decide anything: it re-elaborates the
design and looks files up by the hash of the fresh statement.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .kernel import Evidence, Statement

ENVELOPE_FORMAT = "lola-cert/0"


@dataclass(frozen=True)
class CertificateFile:
    statement_hash: str
    statement: Statement
    evidence: Evidence
    producer: dict


def encode_certificate(cert: CertificateFile) -> dict:
    raise NotImplementedError


def decode_certificate(obj: dict) -> CertificateFile:
    """Strict. Verifies statement_hash equals the hash of the decoded statement, so a
    file whose statement was edited is rejected at read time, before any check."""
    raise NotImplementedError


class CertStore:
    """A directory of certificate files named <hash-hex>.json. Both an EvidenceSource and
    an EvidenceSink. Writes go to a temporary file and are renamed into place, so a crash
    leaves either the old file or the new one; writing the same evidence twice is a
    no-op."""

    name = "certs"

    def __init__(self, root: str | Path) -> None:
        raise NotImplementedError

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        raise NotImplementedError

    def record(self, statement: Statement, statement_hash: str, evidence: Evidence, source: str) -> None:
        raise NotImplementedError

    def paths(self) -> tuple[Path, ...]:
        raise NotImplementedError
