"""Certificate files. Untrusted storage: the kernel re-checks everything it reads.

Envelope (JSON, canonical text on disk):
    {
      "format": "petra-cert/0",
      "kernel": "petra-kernel/0",
      "statement_hash": "sha256:...",
      "statement": <kernel statement JSON>,
      "evidence": <kernel evidence JSON>,
      "producer": {"source": "solver", "petra": "0.1.0"}
    }

The statement is stored so a Lean kernel, or a human, can check the file on its own.
Petra's pipeline never uses the stored statement to decide anything: it re-elaborates the
design and looks files up by the hash of the fresh statement.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .kernel import FORMAT, DecodeError, Evidence, Statement, canonical_text, decode_evidence, decode_statement, encode_evidence, encode_statement, statement_hash

ENVELOPE_FORMAT = "petra-cert/0"
_KEYS = frozenset({"format", "kernel", "statement_hash", "statement", "evidence", "producer"})
_HASH = re.compile(r"sha256:([0-9a-f]{64})")


class CertificateError(ValueError):
    """A certificate file that is malformed, names another kernel format, or whose
    statement does not hash to its statement_hash."""


@dataclass(frozen=True)
class CertificateFile:
    """`statement_hash` must be the hash of `statement`, so a certificate whose statement
    was edited cannot be represented, let alone written."""

    statement_hash: str
    statement: Statement
    evidence: Evidence
    producer: dict

    def __post_init__(self) -> None:
        if statement_hash(self.statement) != self.statement_hash:
            raise CertificateError(f"the statement does not hash to {self.statement_hash}: it was edited or belongs to another file")


def encode_certificate(cert: CertificateFile) -> dict:
    return {
        "format": ENVELOPE_FORMAT,
        "kernel": FORMAT,
        "statement_hash": cert.statement_hash,
        "statement": encode_statement(cert.statement),
        "evidence": encode_evidence(cert.evidence),
        "producer": dict(cert.producer),
    }


def decode_certificate(obj: dict) -> CertificateFile:
    """Strict. Verifies statement_hash equals the hash of the decoded statement, so a
    file whose statement was edited is rejected at read time, before any check."""
    if type(obj) is not dict or set(obj) != _KEYS:
        raise CertificateError(f"a certificate is an object with exactly the keys {sorted(_KEYS)}")
    if obj["format"] != ENVELOPE_FORMAT or obj["kernel"] != FORMAT:
        raise CertificateError(f"format {obj['format']!r} and kernel {obj['kernel']!r} are not {ENVELOPE_FORMAT} and {FORMAT}")
    producer = obj["producer"]
    if type(producer) is not dict or not all(type(k) is str and type(v) is str for k, v in producer.items()):
        raise CertificateError("producer must map strings to strings")
    if type(obj["statement_hash"]) is not str:
        raise CertificateError("statement_hash must be a string")
    try:
        statement, evidence = decode_statement(obj["statement"]), decode_evidence(obj["evidence"])
    except DecodeError as exc:
        raise CertificateError(str(exc)) from None
    return CertificateFile(obj["statement_hash"], statement, evidence, dict(producer))


def load_certificate(path: str | Path) -> CertificateFile:
    """Read and strictly decode one certificate file. A JSON object with a repeated key
    has two readings, so it is refused like any other malformed file."""
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_keys)
    except (UnicodeDecodeError, json.JSONDecodeError, CertificateError) as exc:
        raise CertificateError(f"{path}: {exc}") from None
    try:
        return decode_certificate(obj)
    except CertificateError as exc:
        raise CertificateError(f"{path}: {exc}") from None


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise CertificateError("a JSON object repeats a key")
    return obj


class CertStore:
    """A directory of certificate files named <hash-hex>.json. Both an EvidenceSource and
    an EvidenceSink. Writes go to a temporary file and are renamed into place, so a crash
    leaves either the old file or the new one; writing the same evidence twice is a
    no-op."""

    name = "certs"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        """The stored evidence for this statement hash, or nothing. Raises CertificateError
        for a file that does not decode or that names a different statement."""
        path = self._path(statement_hash)
        if not path.exists():
            return ()
        cert = load_certificate(path)
        if cert.statement_hash != statement_hash:
            raise CertificateError(f"{path} holds a certificate for {cert.statement_hash}, not {statement_hash}")
        return (cert.evidence,)

    def record(self, statement: Statement, statement_hash: str, evidence: Evidence, source: str) -> None:
        from . import __version__  # petra/__init__ imports this module before it is complete

        path = self._path(statement_hash)
        if path.exists():
            try:
                held = load_certificate(path)
            except (CertificateError, OSError):
                held = None
            if held is not None and held.statement == statement and held.evidence == evidence:
                return
        cert = CertificateFile(statement_hash, statement, evidence, {"source": source, "petra": __version__})
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.root, prefix=f".{path.stem}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(canonical_text(encode_certificate(cert)) + "\n")
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def paths(self) -> tuple[Path, ...]:
        """Every certificate file, sorted. Temporary files left by a crashed write end in
        .tmp and are never listed or read."""
        if not self.root.is_dir():
            return ()
        return tuple(sorted(p for p in self.root.glob("*.json") if re.fullmatch(r"[0-9a-f]{64}", p.stem)))

    def _path(self, statement_hash: str) -> Path:
        match = _HASH.fullmatch(statement_hash)
        if match is None:
            raise ValueError(f"{statement_hash!r} is not a sha256 statement hash")
        return self.root / f"{match.group(1)}.json"
