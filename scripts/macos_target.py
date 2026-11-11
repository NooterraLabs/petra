"""Print the oldest macOS that a kernel linked with a Lean toolchain can promise to run on.

    python scripts/macos_target.py PREFIX

PREFIX is the toolchain's folder, as `lean --print-prefix` gives it. Lake links the kernel
statically from the libraries in PREFIX/lib and PREFIX/lib/lean, and every object in them
says which macOS it was compiled for. This prints the newest of those versions, in the
form MACOSX_DEPLOYMENT_TARGET takes.

The linker writes the version it is told into the kernel, whatever the objects say, and
petra_build reads the wheel's tag from the kernel. So the `wheels` workflow tells the
linker this version, and the tag then asks for no older macOS than any object inside the
kernel does.

Lean 4.30.0-rc2 compiles its own libraries for macOS 11.0. Its libgmp.a is compiled for
15.0, and its libuv.a for 15.0 on arm64 and 14.0 on x86-64. So this prints 15.0 for both.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Iterator

MACHO = b"\xcf\xfa\xed\xfe"
"""How a 64-bit little-endian Mach-O file starts."""


def members(archive: bytes) -> Iterator[int]:
    """The offset of each member's body in an `ar` archive of the BSD kind, which may put
    a member's name at the head of its body."""
    if archive[:8] != b"!<arch>\n":
        raise ValueError("not an ar archive")
    at = 8
    while at < len(archive):
        name, size = archive[at:at + 16].decode("ascii").strip(), int(archive[at + 48:at + 58])
        yield at + 60 + (int(name[3:]) if name.startswith("#1/") else 0)
        at += 60 + size + (size & 1)


def compiled_for(data: bytes, start: int) -> tuple[int, int, int] | None:
    """The macOS version the Mach-O object at `start` says it was compiled for, or None
    for a member that is no such object or says none."""
    if data[start:start + 4] != MACHO:
        return None
    (count,), at = struct.unpack_from("<I", data, start + 16), start + 32
    for _ in range(count):
        command, size = struct.unpack_from("<II", data, at)
        # LC_BUILD_VERSION holds the platform and then the version, LC_VERSION_MIN_MACOSX the version
        if command in (0x32, 0x24):
            (version,) = struct.unpack_from("<I", data, at + (12 if command == 0x32 else 8))
            return version >> 16, version >> 8 & 0xFF, version & 0xFF
        at += size
    return None


def target(prefix: Path) -> str:
    libraries = sorted([*prefix.glob("lib/*.a"), *prefix.glob("lib/lean/*.a")])
    versions = [version for library in libraries for data in [library.read_bytes()]
                for start in members(data) if (version := compiled_for(data, start)) is not None]
    if not versions:
        raise ValueError(f"no static library under {prefix} holds an object compiled for macOS")
    newest = max(versions)
    return ".".join(map(str, newest if newest[2] else newest[:2]))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__.split("\n\n")[1].strip())
    try:
        print(target(Path(sys.argv[1])))
    except ValueError as error:
        sys.exit(f"macos_target: {error}")
