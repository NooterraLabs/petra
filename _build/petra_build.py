"""Petra's build backend: the PEP 517 wheel and sdist hooks and the PEP 660 editable hook,
standard library only. pyproject.toml names it with `requires = []`, so pip builds Petra
with no build packages and no network, under build isolation too.

The [project] table gives the core metadata (version 2.4), and a key this module does not
write is an error, never a silent omission. [tool.petra-build] `include` lists, as globs
from the project root, every file the wheel ships. The sdist holds those files and the
build inputs, so a wheel built from it ships the same files. Both archives carry fixed
timestamps, so one tree always builds the same bytes.
"""
from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import locale
import re
import tarfile
import zipfile
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError as exc:
    raise RuntimeError("Petra needs Python 3.11 or later") from exc

ROOT = Path(__file__).resolve().parent.parent

WRITTEN = frozenset({"name", "version", "description", "readme", "requires-python", "license", "license-files", "dependencies", "urls", "scripts"})
"""The [project] keys the metadata carries."""

ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
"""The earliest time a zip entry can carry."""


def _pyproject() -> tuple[dict[str, Any], list[str]]:
    """The [project] table and the include globs, checked."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    unwritten = sorted(set(project) - WRITTEN)
    if unwritten:
        raise ValueError(f"petra_build does not write the [project] keys {unwritten}")
    if not project["readme"].endswith(".md"):
        raise ValueError("petra_build writes the readme as text/markdown, so it must be a .md file")
    return project, data["tool"]["petra-build"]["include"]


def _dist(project: dict[str, Any]) -> str:
    """The distribution name as archive file names spell it."""
    return re.sub(r"[-_.]+", "_", project["name"]).lower()


def _shipped(include: list[str]) -> list[str]:
    """The project-relative paths the wheel ships, sorted. A glob that matches no file is
    an error, so a moved data file cannot drop out of the wheel unnoticed."""
    paths: set[str] = set()
    for pattern in include:
        found = {p.relative_to(ROOT).as_posix() for p in ROOT.glob(pattern)
                 if p.is_file() and "__pycache__" not in p.relative_to(ROOT).parts}
        if not found:
            raise ValueError(f"[tool.petra-build] include glob {pattern!r} matches no file")
        paths |= found
    return sorted(paths)


RELATIVE_LINK = re.compile(r"\]\((?!https?://|#|mailto:)([^)\s]+)\)")


def description(project: dict[str, Any]) -> str:
    """The readme as PyPI and an installed `petra docs readme` show it. Neither has the
    repository beside it, so each relative link points into the repository at the release
    tag `v<version>`."""
    base = f"{project['urls']['Source']}/blob/v{project['version']}/"
    readme = (ROOT / project["readme"]).read_text(encoding="utf-8")
    return RELATIVE_LINK.sub(lambda m: f"]({base}{m.group(1)})", readme)


def _metadata(project: dict[str, Any]) -> bytes:
    fields = [
        ("Metadata-Version", "2.4"),
        ("Name", project["name"]),
        ("Version", project["version"]),
        ("Summary", project["description"]),
        ("Requires-Python", project["requires-python"]),
        ("License-Expression", project["license"]),
        *(("License-File", f) for f in project["license-files"]),
        *(("Requires-Dist", d) for d in project["dependencies"]),
        *(("Project-URL", f"{label}, {url}") for label, url in project["urls"].items()),
        ("Description-Content-Type", "text/markdown"),
    ]
    return ("".join(f"{k}: {v}\n" for k, v in fields) + "\n" + description(project)).encode("utf-8")


def _wheel(directory: str, project: dict[str, Any], payload: list[tuple[str, bytes]]) -> str:
    """Write the wheel of `payload` plus its .dist-info and return its file name."""
    name, version = _dist(project), project["version"]
    info = f"{name}-{version}.dist-info"
    scripts = "".join(f"{k} = {v}\n" for k, v in project["scripts"].items())
    files = [
        *payload,
        (f"{info}/METADATA", _metadata(project)),
        (f"{info}/WHEEL", b"Wheel-Version: 1.0\nGenerator: petra_build\nRoot-Is-Purelib: true\nTag: py3-none-any\n"),
        (f"{info}/entry_points.txt", f"[console_scripts]\n{scripts}".encode("utf-8")),
        *((f"{info}/licenses/{f}", (ROOT / f).read_bytes()) for f in project["license-files"]),
    ]
    record = io.StringIO()
    rows = csv.writer(record, lineterminator="\n")
    for path, data in files:
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
        rows.writerow([path, f"sha256={digest}", len(data)])
    rows.writerow([f"{info}/RECORD", "", ""])
    files.append((f"{info}/RECORD", record.getvalue().encode("utf-8")))
    filename = f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(Path(directory) / filename, "w") as archive:
        for path, data in files:
            entry = zipfile.ZipInfo(path, ZIP_EPOCH)
            entry.external_attr = 0o644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    return filename


def build_wheel(wheel_directory: str, config_settings: dict | None = None, metadata_directory: str | None = None) -> str:
    project, include = _pyproject()
    return _wheel(wheel_directory, project, [(p, (ROOT / p).read_bytes()) for p in _shipped(include)])


def build_editable(wheel_directory: str, config_settings: dict | None = None, metadata_directory: str | None = None) -> str:
    """A wheel whose .pth file puts this source tree on sys.path, so edits take effect
    without reinstalling."""
    project, _ = _pyproject()
    # Python 3.11 reads .pth files in the locale encoding; 3.13 tries UTF-8 first, then that.
    line = f"{ROOT}\n".encode(locale.getpreferredencoding(False))
    return _wheel(wheel_directory, project, [(f"_{_dist(project)}_editable.pth", line)])


def build_sdist(sdist_directory: str, config_settings: dict | None = None) -> str:
    project, include = _pyproject()
    base = f"{_dist(project)}-{project['version']}"
    inputs = {"pyproject.toml", Path(__file__).resolve().relative_to(ROOT).as_posix(), project["readme"], *project["license-files"]}
    files = [("PKG-INFO", _metadata(project)), *((p, (ROOT / p).read_bytes()) for p in sorted(inputs | set(_shipped(include))))]
    filename = f"{base}.tar.gz"
    with open(Path(sdist_directory) / filename, "wb") as raw, \
            gzip.GzipFile(filename=filename, fileobj=raw, mode="wb", mtime=0) as gz, \
            tarfile.open(fileobj=gz, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path, data in files:
            entry = tarfile.TarInfo(f"{base}/{path}")
            entry.size, entry.mode = len(data), 0o644
            tar.addfile(entry, io.BytesIO(data))
    return filename


def get_requires_for_build_wheel(config_settings: dict | None = None) -> list[str]:
    return []


def get_requires_for_build_sdist(config_settings: dict | None = None) -> list[str]:
    return []


def get_requires_for_build_editable(config_settings: dict | None = None) -> list[str]:
    return []
