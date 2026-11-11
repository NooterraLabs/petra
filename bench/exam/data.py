"""Where benchmark files and run records live, and how a benchmark file is fetched.

Everything is under ~/.petra/exam, which is outside the repository and outside any synced
folder. A fetched file is held to a pinned SHA-256 when the adapter states one, and the
folder keeps SOURCE.json: each file's URL, its hash, and the version it was taken at.
A grader's environment is made where the grader runs, which host.py knows.

A request carries nothing of this machine: the user agent is a fixed word, and a URL holds
only what the adapter pins.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
HOME = Path(os.environ.get("PETRA_EXAM_HOME") or Path.home() / ".petra" / "exam")
"""Benchmark files and run records, and on Linux the grader environments and a fetched
sandbox too (host.py says where those are on Windows). PETRA_EXAM_HOME names another place."""
DATA = HOME / "data"
RUNS = HOME / "runs"
AGENT = "benchmark-harness"
LIMIT = 200 * 1024 * 1024
"""The largest file a fetch takes, in bytes."""


@dataclass(frozen=True)
class Source:
    """One file of a benchmark: where it is, where it goes under the benchmark's folder,
    and the hash it must have. A hash of None is taken on trust and recorded."""

    url: str
    path: str
    sha256: str | None = None


def refused(folder: Path) -> str | None:
    """Why a folder may not hold benchmark files or records, or None when it may: it is
    inside the repository, or inside a folder that a sync client copies elsewhere."""
    where = folder.resolve()
    if where == ROOT or ROOT in where.parents:
        return "inside the repository"
    if any(part.lower().startswith(("onedrive", "dropbox", "google drive", "icloud")) for part in where.parts):
        return "inside a synced folder"
    return None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_hash(text: str) -> str:
    return "sha256:" + sha256(text.encode("utf-8"))


def inside(folder: Path, relative: str) -> Path:
    """The path of a file under a folder, refused when it would land outside it."""
    target = (folder / relative).resolve()
    if folder.resolve() not in target.parents:
        raise ValueError(f"{relative} is not inside {folder}")
    return target


def fetch(folder: Path, sources: list[Source], version: dict[str, str]) -> dict:
    """Bring every source into the folder and write SOURCE.json. A file that is there with
    its pinned hash is not fetched again. Raises when a hash differs from the pin."""
    folder.mkdir(parents=True, exist_ok=True)
    files = []
    for source in sources:
        target = inside(folder, source.path)
        if source.sha256 and target.is_file() and sha256(target.read_bytes()) == source.sha256:
            files.append({"path": source.path, "url": source.url, "sha256": source.sha256})
            continue
        request = urllib.request.Request(source.url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(request, timeout=120) as reply:
            data = reply.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise ValueError(f"{source.url} is larger than {LIMIT} bytes")
        found = sha256(data)
        if source.sha256 and found != source.sha256:
            raise ValueError(f"{source.url} has hash {found}, and the adapter pins {source.sha256}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files.append({"path": source.path, "url": source.url, "sha256": found})
    manifest = {"version": version, "files": files}
    (folder / "SOURCE.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8", newline="\n")
    return manifest


def fetch_archive(folder: Path, url: str, keep: list[str], version: dict[str, str], digest: str | None = None) -> dict:
    """Bring the members of a zip archive that match one of the `keep` patterns into the
    folder, without the archive's top folder, and write SOURCE.json. The archive itself is
    not kept, so what the patterns leave out never reaches the disk. `digest` pins the
    kept files together: the hash of their sorted "PATH HASH" lines. Nothing is executed."""
    import fnmatch
    import io
    import zipfile

    folder.mkdir(parents=True, exist_ok=True)
    known = manifest(folder)
    if digest and known and known.get("digest") == digest and all(
            (folder / f["path"]).is_file() and sha256((folder / f["path"]).read_bytes()) == f["sha256"] for f in known["files"]):
        known["version"] = version
        (folder / "SOURCE.json").write_text(json.dumps(known, indent=1) + "\n", encoding="utf-8", newline="\n")
        return known
    request = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=300) as reply:
        data = reply.read(LIMIT + 1)
    if len(data) > LIMIT:
        raise ValueError(f"{url} is larger than {LIMIT} bytes")
    kept: list[tuple[Path, bytes]] = []
    files = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in sorted(archive.infolist(), key=lambda m: m.filename):
            path = member.filename.split("/", 1)[1] if "/" in member.filename else ""
            if member.is_dir() or not any(fnmatch.fnmatchcase(path, pattern) for pattern in keep):
                continue
            if member.file_size > LIMIT:
                raise ValueError(f"{path} in {url} is larger than {LIMIT} bytes")
            kept.append((inside(folder, path), archive.read(member)))
            files.append({"path": path, "sha256": sha256(kept[-1][1])})
    found = sha256("".join(f"{f['path']} {f['sha256']}\n" for f in files).encode("utf-8"))
    if digest and found != digest:
        raise ValueError(f"the files kept from {url} have digest {found}, and the adapter pins {digest}")
    for target, content in kept:      # nothing is written before the digest holds
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    out = {"version": version, "archive": url, "archive_sha256": sha256(data), "digest": found, "files": files}
    (folder / "SOURCE.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
    return out


def manifest(folder: Path) -> dict | None:
    path = folder / "SOURCE.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def changed(folder: Path) -> list[str]:
    """The fetched files that are missing or no longer have the hash SOURCE.json records.
    A grader runs a model's code beside these files, so a run checks them before it starts."""
    found = manifest(folder)
    return [f["path"] for f in (found or {}).get("files", [])
            if not (folder / f["path"]).is_file() or sha256((folder / f["path"]).read_bytes()) != f["sha256"]]


KEPT = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "HOMEDRIVE",
        "HOMEPATH", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "LANG", "LC_ALL")


def plain_env(**more: str) -> dict[str, str]:
    """The environment of a command that leads to a grader: what a program needs to start,
    and `more`. A grader runs code a model wrote, and a key or a token in this process's
    environment is none of that code's business. In the sandbox the grader gets less
    still (sandbox.PLAIN)."""
    return {**{name: os.environ[name] for name in KEPT if name in os.environ}, **more}
