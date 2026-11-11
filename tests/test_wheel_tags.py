"""A wheel's platform tag promises what the kernel inside it needs, and no less.

The build backend reads the tag from the kernel's own headers (`platform_tag` in
_build/petra_build.py). tests/test_packaging.py holds it to the kernel built on this
machine. The tests here cover what no one machine shows: each hands the reader the headers
of an ELF, Mach-O or PE executable, made here with no code behind them, and asks for the
tag, or for the refusal where no tag would be true.

The last class holds scripts/macos_target.py, which finds the macOS version to link the
kernel for, to archives made the same way.
"""
import importlib.util
import struct
import tempfile
import unittest
from pathlib import Path

from tests.test_packaging import backend

ROOT = Path(__file__).resolve().parents[1]
X86_64, AARCH64 = 62, 183
INTEL, ARM = 0x01000007, 0x0100000C
LIBSYSTEM = "/usr/lib/libSystem.B.dylib"
ADDRESS = 0x10000
"""Where the ELF file is loaded, so that an address is not its file offset."""


def elf(machine: int, needs: dict[str, list[str]], dynamic: bool = True, bits: int = 2) -> bytes:
    """An ELF executable that loads each library of `needs` and asks it for the symbol
    versions listed."""
    strings = b"\0"

    def name(text: str) -> int:
        nonlocal strings
        strings += text.encode("ascii") + b"\0"
        return len(strings) - len(text) - 1

    versioned = [(library, versions) for library, versions in needs.items() if versions]
    needed = b"".join(struct.pack("<qQ", 1, name(library)) for library in needs)
    verneed = b""
    for n, (library, versions) in enumerate(versioned):
        last = n == len(versioned) - 1
        verneed += struct.pack("<HHIII", 1, len(versions), name(library), 16, 0 if last else 16 + 16 * len(versions))
        for m, version in enumerate(versions):
            verneed += struct.pack("<IHHII", 0, 0, m + 2, name(version), 0 if m == len(versions) - 1 else 16)
    at_dynamic = 64 + 2 * 56
    at_strings = at_dynamic + len(needed) + 4 * 16
    at_verneed = at_strings + len(strings)
    table = needed + struct.pack("<qQqQqQqQ", 5, ADDRESS + at_strings, 0x6FFFFFFE, ADDRESS + at_verneed, 0x6FFFFFFF, len(versioned), 0, 0)
    body = table + strings + verneed
    header = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF" + bytes([bits, 1, 1]), 3, machine, 1, 0, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    load = struct.pack("<IIQQQQQQ", 1, 5, 0, ADDRESS, ADDRESS, at_dynamic + len(body), at_dynamic + len(body), 0x1000)
    segment = struct.pack("<IIQQQQQQ", 2 if dynamic else 4, 6, at_dynamic, ADDRESS + at_dynamic, ADDRESS + at_dynamic, len(table), len(table), 8)
    return header + load + segment + body


def macho(machine: int, version: tuple[int, int, int] | None, libraries: tuple[str, ...] = (LIBSYSTEM,), signed: bool = True,
          platform: int = 1, old_command: bool = False) -> bytes:
    """A Mach-O executable linked for a macOS version, which loads the libraries."""
    commands = []
    if version is not None:
        packed = version[0] << 16 | version[1] << 8 | version[2]
        commands.append(struct.pack("<IIII", 0x24, 16, packed, packed) if old_command else struct.pack("<IIIIII", 0x32, 24, platform, packed, packed, 0))
    for n, library in enumerate(libraries):
        text = library.encode("ascii") + b"\0"
        text += b"\0" * (-len(text) % 8)
        # the second library is loaded weakly, by the command with the must-know bit set
        commands.append(struct.pack("<IIIIII", 0x80000018 if n == 1 else 0x0C, 24 + len(text), 24, 0, 0, 0) + text)
    if signed:
        commands.append(struct.pack("<IIII", 0x1D, 16, 0, 0))
    body = b"".join(commands)
    return struct.pack("<IIIIIIII", 0xFEEDFACF, machine, 3, 2, len(commands), len(body), 0, 0) + body


def pe(dlls: tuple[str, ...], machine: int = 0x8664, delayed: int = 0) -> bytes:
    """A PE32+ executable that imports the DLLs."""
    address, offset = 0x1000, 0x200
    names, at = b"", 20 * (len(dlls) + 1)
    table = b""
    for dll in dlls:
        table += struct.pack("<IIIII", 0, 0, 0, address + at + len(names), 0)
        names += dll.encode("ascii") + b"\0"
    section = table + bytes(20) + names
    optional = bytearray(240)
    struct.pack_into("<H", optional, 0, 0x20B)
    struct.pack_into("<II", optional, 112 + 8, address, len(table) + 20)
    struct.pack_into("<II", optional, 112 + 13 * 8, delayed, 0)
    head = b"MZ" + bytes(0x3A) + struct.pack("<I", 0x40) + b"PE\0\0" + struct.pack("<HHIIIHH", machine, 1, 0, 0, 0, 240, 0x22)
    head += bytes(optional) + struct.pack("<8sIIII16s", b".idata", len(section), address, len(section), offset, bytes(16))
    return head + bytes(offset - len(head)) + section


class Linux(unittest.TestCase):
    tag = staticmethod(backend().platform_tag)

    def test_the_tag_names_the_newest_glibc_any_library_is_asked_for(self):
        needs = {"libc.so.6": ["GLIBC_2.2.5", "GLIBC_2.17", "GLIBC_2.3.4", "GLIBC_2.14"], "ld-linux-x86-64.so.2": ["GLIBC_2.3"],
                 "libpthread.so.0": ["GLIBC_2.2.5", "GLIBC_2.3.3"], "libdl.so.2": ["GLIBC_2.2.5"], "librt.so.1": [], "libm.so.6": ["GLIBC_2.2.5"]}
        self.assertEqual(self.tag(elf(X86_64, needs)), "manylinux_2_17_x86_64")
        self.assertEqual(self.tag(elf(X86_64, {"libc.so.6": ["GLIBC_2.2.5"], "libm.so.6": ["GLIBC_2.34", "GLIBC_2.29"]})), "manylinux_2_34_x86_64")
        self.assertEqual(self.tag(elf(AARCH64, {"libc.so.6": ["GLIBC_2.17"], "libpthread.so.0": ["GLIBC_2.17"]})), "manylinux_2_17_aarch64")

    def test_it_names_no_glibc_older_than_installers_look_for(self):
        self.assertEqual(self.tag(elf(X86_64, {"libc.so.6": ["GLIBC_2.2.5"]})), "manylinux_2_5_x86_64")
        self.assertEqual(self.tag(elf(AARCH64, {"libc.so.6": []})), "manylinux_2_17_aarch64")

    def test_a_library_outside_glibc_leaves_only_this_machines_tag(self):
        for library in ("libstdc++.so.6", "libgmp.so.10", "libleanshared.so"):
            with self.subTest(library):
                self.assertEqual(self.tag(elf(X86_64, {"libc.so.6": ["GLIBC_2.17"], library: []})), "linux_x86_64")

    def test_a_version_that_is_no_glibc_release_leaves_only_this_machines_tag(self):
        for version in ("GLIBC_ABI_DT_RELR", "GLIBC_PRIVATE", "GLIBC_3.0", "GCC_3.0"):
            with self.subTest(version):
                self.assertEqual(self.tag(elf(AARCH64, {"libc.so.6": ["GLIBC_2.17", version]})), "linux_aarch64")

    def test_a_file_with_no_dynamic_segment_gets_only_this_machines_tag(self):
        self.assertEqual(self.tag(elf(X86_64, {"libc.so.6": ["GLIBC_2.17"]}, dynamic=False)), "linux_x86_64")

    def test_another_machine_or_a_32_bit_file_is_refused(self):
        for binary in (elf(40, {"libc.so.6": ["GLIBC_2.17"]}), elf(X86_64, {"libc.so.6": ["GLIBC_2.17"]}, bits=1)):
            with self.assertRaisesRegex(ValueError, "64-bit one for x86-64 or aarch64"):
                self.tag(binary)


class MacOS(unittest.TestCase):
    tag = staticmethod(backend().platform_tag)

    def test_the_tag_names_the_macos_the_file_was_linked_for(self):
        self.assertEqual(self.tag(macho(ARM, (15, 0, 0), (LIBSYSTEM, "/usr/lib/libc++.1.dylib"))), "macosx_15_0_arm64")
        self.assertEqual(self.tag(macho(ARM, (11, 0, 0))), "macosx_11_0_arm64")
        self.assertEqual(self.tag(macho(INTEL, (10, 15, 0), signed=False)), "macosx_10_15_x86_64")
        self.assertEqual(self.tag(macho(INTEL, (10, 12, 0), signed=False, old_command=True)), "macosx_10_12_x86_64")

    def test_a_version_between_two_tags_takes_the_later_one(self):
        """An installer on macOS 11 or later looks for 11_0, 12_0 and so on, so 15.2 is
        promised only from the next whole version."""
        self.assertEqual(self.tag(macho(ARM, (15, 2, 0))), "macosx_16_0_arm64")
        self.assertEqual(self.tag(macho(ARM, (11, 0, 1))), "macosx_12_0_arm64")
        self.assertEqual(self.tag(macho(INTEL, (10, 15, 4), signed=False)), "macosx_10_16_x86_64")

    def test_a_library_that_macos_does_not_carry_is_refused_by_name(self):
        with self.assertRaisesRegex(ValueError, "@rpath/libleanshared.dylib, which macOS does not carry"):
            self.tag(macho(ARM, (15, 0, 0), (LIBSYSTEM, "@rpath/libleanshared.dylib")))
        with self.assertRaisesRegex(ValueError, "/opt/homebrew/opt/gmp/lib/libgmp.10.dylib"):
            self.tag(macho(ARM, (15, 0, 0), ("/opt/homebrew/opt/gmp/lib/libgmp.10.dylib",)))

    def test_an_unsigned_arm64_file_is_refused_and_an_unsigned_x86_64_one_is_not(self):
        with self.assertRaisesRegex(ValueError, "not signed"):
            self.tag(macho(ARM, (15, 0, 0), signed=False))
        self.assertEqual(self.tag(macho(INTEL, (15, 0, 0), signed=False)), "macosx_15_0_x86_64")

    def test_a_file_that_names_no_macos_version_is_refused(self):
        with self.assertRaisesRegex(ValueError, "does not say which macOS"):
            self.tag(macho(ARM, None))
        with self.assertRaisesRegex(ValueError, "a platform other than macOS"):
            self.tag(macho(ARM, (15, 0, 0), platform=2))
        with self.assertRaisesRegex(ValueError, "not for x86-64 or arm64"):
            self.tag(macho(7, (10, 15, 0)))


class Windows(unittest.TestCase):
    tag = staticmethod(backend().platform_tag)

    def test_a_file_that_imports_only_what_windows_carries_is_win_amd64(self):
        self.assertEqual(self.tag(pe(("ucrtbase.dll", "KERNEL32.dll", "icu.dll", "WS2_32.dll", "IPHLPAPI.DLL"))), "win_amd64")
        self.assertEqual(self.tag(pe(())), "win_amd64")

    def test_a_dll_off_the_list_is_refused_by_name(self):
        with self.assertRaisesRegex(ValueError, r"imports libc\+\+\.dll, libleanshared\.dll,"):
            self.tag(pe(("KERNEL32.dll", "libleanshared.dll", "libc++.dll")))

    def test_another_machine_or_delayed_imports_are_refused(self):
        with self.assertRaisesRegex(ValueError, "64-bit one for x86-64"):
            self.tag(pe(("KERNEL32.dll",), machine=0xAA64))
        with self.assertRaisesRegex(ValueError, "delay-loaded"):
            self.tag(pe(("KERNEL32.dll",), delayed=0x1000))

    def test_a_file_of_no_known_kind_is_refused(self):
        with self.assertRaisesRegex(ValueError, "not an ELF, Mach-O or PE executable"):
            self.tag(b"#!/bin/sh\nexit 64\n")


def archive(*members: tuple[str, bytes]) -> bytes:
    """An `ar` archive of the BSD kind. A name over 16 bytes goes at the head of its body."""
    out = b"!<arch>\n"
    for name, body in members:
        long = name.encode("ascii") + b"\0" * (-len(name) % 4) if len(name) > 16 else b""
        size = len(long) + len(body)
        label = f"#1/{len(long)}" if long else name
        out += f"{label:<16}{0:<12}{0:<6}{0:<6}{'100644':<8}{size:<10}`\n".encode("ascii") + long + body + b"\n" * (size & 1)
    return out


def target(libraries: dict[str, bytes]) -> str:
    spec = importlib.util.spec_from_file_location("macos_target", ROOT / "scripts" / "macos_target.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as prefix:
        for path, data in libraries.items():
            Path(prefix, path).parent.mkdir(parents=True, exist_ok=True)
            Path(prefix, path).write_bytes(data)
        return module.target(Path(prefix))


class MacTarget(unittest.TestCase):
    def test_it_is_the_newest_macos_any_object_of_any_library_was_compiled_for(self):
        lean = archive(("__.SYMDEF SORTED", b"\0" * 9), ("Init.o", macho(ARM, (11, 0, 0))), ("a_long_member_name.c.o", macho(ARM, (11, 0, 0))))
        gmp = archive(("__.SYMDEF", b"\0" * 8), ("add_n.o", macho(ARM, (15, 0, 0))), ("old.o", macho(ARM, (10, 12, 0), old_command=True)))
        self.assertEqual(target({"lib/lean/libInit.a": lean}), "11.0")
        self.assertEqual(target({"lib/lean/libInit.a": lean, "lib/libgmp.a": gmp}), "15.0")
        self.assertEqual(target({"lib/libuv.a": archive(("uv.o", macho(INTEL, (14, 5, 1)))), "lib/libgmp.a": gmp}), "15.0")
        self.assertEqual(target({"lib/libuv.a": archive(("uv.o", macho(INTEL, (15, 4, 1)))), "lib/libgmp.a": gmp}), "15.4.1")

    def test_a_toolchain_with_no_object_compiled_for_macos_is_refused(self):
        for libraries in ({}, {"lib/libgmp.a": archive(("add_n.o", elf(X86_64, {})))}):
            with self.assertRaisesRegex(ValueError, "no static library"):
                target(libraries)


if __name__ == "__main__":
    unittest.main()
