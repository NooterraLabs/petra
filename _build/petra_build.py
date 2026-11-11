"""Petra's build backend: the PEP 517 wheel and sdist hooks and the PEP 660 editable hook,
standard library only. pyproject.toml names it with `requires = []`, so pip builds Petra
with no build packages and no network, under build isolation too.

The [project] table gives the core metadata (version 2.4), and a key this module does not
write is an error, never a silent omission. [tool.petra-build] `include` lists, as globs
from the project root, every file the wheel ships. The sdist holds those files and the
build inputs, so a wheel built from it ships the same files. Both archives carry fixed
timestamps, so one tree always builds the same bytes.

[tool.petra-build] `kernel` names the file that `lake build` makes of the Lean kernel. A
tree that holds it builds a wheel for one platform, which carries the binary as
petra/bin/petra-verify (.exe on Windows), where petra/verify.py looks for it. The wheel's
platform tag is read from the binary itself (`platform_tag`), so it promises what the
binary needs and no less. A tree without the binary builds the pure wheel, and so does an
sdist, which never holds it: a report from that wheel says that no kernel ran.
"""
from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
import locale
import os
import re
import stat
import struct
import tarfile
import zipfile
from pathlib import Path
from typing import Any, NamedTuple

try:
    import tomllib
except ModuleNotFoundError as exc:
    raise RuntimeError("Petra needs Python 3.11 or later") from exc

ROOT = Path(__file__).resolve().parent.parent

WRITTEN = frozenset({"name", "version", "description", "readme", "requires-python", "license", "license-files", "dependencies", "urls", "scripts"})
"""The [project] keys the metadata carries."""

ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
"""The earliest time a zip entry can carry."""


def _pyproject() -> tuple[dict[str, Any], dict[str, Any]]:
    """The [project] table, checked, and the [tool.petra-build] table."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    unwritten = sorted(set(project) - WRITTEN)
    if unwritten:
        raise ValueError(f"petra_build does not write the [project] keys {unwritten}")
    if not project["readme"].endswith(".md"):
        raise ValueError("petra_build writes the readme as text/markdown, so it must be a .md file")
    return project, data["tool"]["petra-build"]


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


BIN = "petra/bin"
"""Where a platform wheel carries the kernel. petra/verify.py looks for it there."""

GLIBC = frozenset({"libc.so.6", "libm.so.6", "libdl.so.2", "libpthread.so.0", "librt.so.1",
                   "ld-linux-x86-64.so.2", "ld-linux-aarch64.so.1"})
"""The shared libraries glibc itself provides. PEP 600 lets a manylinux wheel link against
them, and a few others that the kernel does not use."""

ELF_MACHINES = {62: ("x86_64", 5), 183: ("aarch64", 17)}
"""An ELF machine number's name in a tag, and the oldest glibc 2.x an installer looks for on it."""

MACHO_MACHINES = {0x01000007: "x86_64", 0x0100000C: "arm64"}

MACHO_DYLIB = frozenset({0x0C, 0x18, 0x1F, 0x20, 0x23})
"""The Mach-O load commands that name a library to load, without the bit that marks a
command the loader must know."""

WINDOWS = frozenset({"advapi32.dll", "bcrypt.dll", "dbghelp.dll", "icu.dll", "iphlpapi.dll", "kernel32.dll", "ole32.dll",
                     "shell32.dll", "ucrtbase.dll", "user32.dll", "userenv.dll", "ws2_32.dll"})
"""DLLs that Windows 10 version 1903 and every later Windows carry. icu.dll came with that
version, and the rest are older. A wheel's tag names no version of Windows, so on Windows
petra/verify.py starts the kernel once before it relies on it."""


class Kernel(NamedTuple):
    """The kernel of a platform wheel: its path in the wheel, its bytes, and the platform
    tag the bytes call for."""

    path: str
    data: bytes
    platform: str


def _text(data: bytes, at: int) -> str:
    """The NUL-terminated name at an offset."""
    return data[at:data.index(b"\0", at)].decode("ascii")


def _elf_tag(data: bytes) -> str:
    """manylinux_2_Y, where 2.Y is the newest glibc whose symbols the loader will ask for,
    when the binary needs glibc's libraries and nothing else. Otherwise linux_<machine>,
    which promises only the machine that built it, and which PyPI does not take."""
    if data[4:6] != b"\x02\x01" or struct.unpack_from("<H", data, 18)[0] not in ELF_MACHINES:
        raise ValueError("the kernel is an ELF file, but not a 64-bit one for x86-64 or aarch64")
    machine, oldest = ELF_MACHINES[struct.unpack_from("<H", data, 18)[0]]
    (headers,), (size, count) = struct.unpack_from("<Q", data, 32), struct.unpack_from("<HH", data, 54)
    # each program header's type, flags, file offset, address, physical address and size in the file
    segments = [struct.unpack_from("<IIQQQQ", data, headers + n * size) for n in range(count)]
    dynamic = next((offset for kind, _, offset, *_ in segments if kind == 2), None)
    if dynamic is None:
        return f"linux_{machine}"

    def at(address: int) -> int:
        """The file offset of an address in a loaded segment."""
        return next(offset + address - start for kind, _, offset, start, _, length in segments
                    if kind == 1 and start <= address < start + length)

    entries = []
    while not entries or entries[-1][0]:
        entries.append(struct.unpack_from("<qQ", data, dynamic + 16 * len(entries)))
    table = dict(entries)
    names = at(table[5])
    libraries = {_text(data, names + value) for tag, value in entries if tag == 1}
    # the table of version needs, one entry for each library that is asked for versions
    versions, need = [], at(table[0x6FFFFFFE]) if table.get(0x6FFFFFFF) else 0
    for _ in range(table.get(0x6FFFFFFF, 0)):
        _, wanted, _, first, following = struct.unpack_from("<HHIII", data, need)
        item = need + first
        for _ in range(wanted):
            _, _, _, name, after = struct.unpack_from("<IHHII", data, item)
            versions.append(_text(data, names + name))
            item += after
        need += following
    glibc = [re.fullmatch(r"GLIBC_2\.(\d+)(?:\.\d+)?", version) for version in versions]
    if not libraries <= GLIBC or not all(glibc):
        return f"linux_{machine}"
    return f"manylinux_2_{max([oldest, *(int(found[1]) for found in glibc)])}_{machine}"


def _macho_tag(data: bytes) -> str:
    """macosx_X_Y for the macOS version the binary says it was linked for. It may load
    only libraries that macOS carries, and on arm64 it must be signed, because macOS runs
    no unsigned arm64 code."""
    machine, _, _, count = struct.unpack_from("<IIII", data, 4)
    if machine not in MACHO_MACHINES:
        raise ValueError("the kernel is a Mach-O file, but not for x86-64 or arm64")
    at, minimum, libraries, signed = 32, None, [], False
    for _ in range(count):
        command, size = struct.unpack_from("<II", data, at)
        if command == 0x32:
            platform, minimum = struct.unpack_from("<II", data, at + 8)
            if platform != 1:
                raise ValueError("the kernel is a Mach-O file for a platform other than macOS")
        elif command == 0x24:
            (minimum,) = struct.unpack_from("<I", data, at + 8)
        elif command & 0x7FFFFFFF in MACHO_DYLIB:
            libraries.append(_text(data, at + struct.unpack_from("<I", data, at + 8)[0]))
        signed |= command == 0x1D
        at += size
    foreign = sorted(name for name in libraries if not name.startswith(("/usr/lib/", "/System/Library/")))
    if foreign:
        raise ValueError(f"the kernel loads {', '.join(foreign)}, which macOS does not carry")
    if minimum is None:
        raise ValueError("the kernel does not say which macOS it was linked for")
    if MACHO_MACHINES[machine] == "arm64" and not signed:
        raise ValueError("the kernel is not signed, and macOS runs no unsigned arm64 code: `codesign --sign - FILE` signs it")
    major, minor, patch = minimum >> 16, minimum >> 8 & 0xFF, minimum & 0xFF
    # From macOS 11 an installer looks for whole versions only: 11_0, 12_0 and so on.
    major, minor = (major + bool(minor or patch), 0) if major >= 11 else (major, minor + bool(patch))
    return f"macosx_{major}_{minor}_{MACHO_MACHINES[machine]}"


def _pe_tag(data: bytes) -> str:
    """win_amd64, for a binary that imports only DLLs on the WINDOWS list."""
    (header,) = struct.unpack_from("<I", data, 0x3C)
    machine, count, _, _, _, optional = struct.unpack_from("<HHIIIH", data, header + 4)
    start = header + 24
    if data[header:header + 4] != b"PE\0\0" or machine != 0x8664 or struct.unpack_from("<H", data, start)[0] != 0x20B:
        raise ValueError("the kernel is a Windows file, but not a 64-bit one for x86-64")
    (imports,), (delayed,) = struct.unpack_from("<I", data, start + 112 + 8), struct.unpack_from("<I", data, start + 112 + 13 * 8)
    if delayed:
        raise ValueError("the kernel has delay-loaded imports, which petra_build does not read")
    # each section's size in memory, address, size in the file and file offset
    sections = [struct.unpack_from("<IIII", data, start + optional + 40 * n + 8) for n in range(count)]

    def at(address: int) -> int:
        """The file offset of an address in a section."""
        return next(offset + address - begin for size, begin, kept, offset in sections if begin <= address < begin + max(size, kept))

    names, entry = [], at(imports)
    while struct.unpack_from("<I", data, entry + 12)[0]:
        names.append(_text(data, at(struct.unpack_from("<I", data, entry + 12)[0])).lower())
        entry += 20
    foreign = sorted(set(names) - WINDOWS)
    if foreign:
        raise ValueError(f"the kernel imports {', '.join(foreign)}, and the list of DLLs that Windows carries (WINDOWS) does not hold it")
    return "win_amd64"


def platform_tag(binary: bytes) -> str:
    """The wheel platform tag that promises what an executable needs to run, read from its
    own headers. Raises ValueError for an executable whose needs no tag can state."""
    if binary[:4] == b"\x7fELF":
        return _elf_tag(binary)
    if binary[:4] == b"\xcf\xfa\xed\xfe":
        return _macho_tag(binary)
    if binary[:2] == b"MZ":
        return _pe_tag(binary)
    raise ValueError("the kernel is not an ELF, Mach-O or PE executable")


def _kernel(built: str) -> Kernel | None:
    """The kernel that `lake build` left at `built` in this tree, .exe on Windows, or None
    when the tree holds none."""
    source = ROOT / (built + (".exe" if os.name == "nt" else ""))
    if not source.is_file():
        return None
    data = source.read_bytes()
    return Kernel(f"{BIN}/{source.name}", data, platform_tag(data))


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


def _wheel(directory: str, project: dict[str, Any], payload: list[tuple[str, bytes]], kernel: Kernel | None = None) -> str:
    """Write the wheel of `payload` plus its .dist-info and return its file name. With a
    kernel the wheel is of the kernel's platform and carries it as an executable file."""
    name, version = _dist(project), project["version"]
    info = f"{name}-{version}.dist-info"
    scripts = "".join(f"{k} = {v}\n" for k, v in project["scripts"].items())
    tag = f"py3-none-{kernel.platform if kernel else 'any'}"
    files = [
        *payload,
        *([kernel[:2]] if kernel else []),
        (f"{info}/METADATA", _metadata(project)),
        (f"{info}/WHEEL", f"Wheel-Version: 1.0\nGenerator: petra_build\nRoot-Is-Purelib: {'false' if kernel else 'true'}\nTag: {tag}\n".encode("ascii")),
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
    filename = f"{name}-{version}-{tag}.whl"
    with zipfile.ZipFile(Path(directory) / filename, "w") as archive:
        for path, data in files:
            entry = zipfile.ZipInfo(path, ZIP_EPOCH)
            # pip makes a file executable only when its entry is a regular file with an execute bit
            entry.external_attr = ((stat.S_IFREG | 0o755) if kernel and path == kernel.path else 0o644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    return filename


def build_wheel(wheel_directory: str, config_settings: dict | None = None, metadata_directory: str | None = None) -> str:
    project, tool = _pyproject()
    return _wheel(wheel_directory, project, [(p, (ROOT / p).read_bytes()) for p in _shipped(tool["include"])], _kernel(tool["kernel"]))


def build_editable(wheel_directory: str, config_settings: dict | None = None, metadata_directory: str | None = None) -> str:
    """A wheel whose .pth file puts this source tree on sys.path, so edits take effect
    without reinstalling."""
    project, _ = _pyproject()
    # Python 3.11 reads .pth files in the locale encoding; 3.13 tries UTF-8 first, then that.
    line = f"{ROOT}\n".encode(locale.getpreferredencoding(False))
    return _wheel(wheel_directory, project, [(f"_{_dist(project)}_editable.pth", line)])


def build_sdist(sdist_directory: str, config_settings: dict | None = None) -> str:
    project, tool = _pyproject()
    base = f"{_dist(project)}-{project['version']}"
    inputs = {"pyproject.toml", Path(__file__).resolve().relative_to(ROOT).as_posix(), project["readme"], *project["license-files"]}
    files = [("PKG-INFO", _metadata(project)), *((p, (ROOT / p).read_bytes()) for p in sorted(inputs | set(_shipped(tool["include"]))))]
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
