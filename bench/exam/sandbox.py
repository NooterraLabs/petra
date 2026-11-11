"""The sandbox a grader runs in: Linux namespaces, set up by bubblewrap (bwrap) on the grader host (host.py).

Some benchmarks grade by executing code a model wrote. `run` is the one way the harness starts such a grader, and it
refuses when the host has no sandbox, unless the caller says the run was told to grade without one. Inside, the code has:

    network       none: a new network namespace, whose only interface is a loopback that is down
    files         the host's /usr, read-only, with the links into it (/bin, /lib and the like) and the few paths of
                  SYSTEM, and the folders the caller names, read-only, at paths that name nobody (/exam/env,
                  /exam/data). No home folder, no /mnt, nothing else of /etc, and an empty folder over anything
                  mounted below /usr
    to write in   /work, /tmp and /dev/shm: three new file systems in memory, capped at WORK_BYTES, TMP and SHM bytes
                  where bwrap is 0.8 or later, and gone when the grader ends. Nothing it writes outlasts it
    processes     a process namespace of its own, with its own /proc and a /dev of the few standard devices
    environment   PLAIN and what the caller adds, and no variable of the harness or of the host
    time          the caller's limit, kept by `timeout` on the host: bwrap dies with it, and the namespace with bwrap

It is not a virtual machine. The code still talks to the host's kernel, so a fault in the kernel is a way out, and no
system call is filtered. It can use every processor and all the memory until the time limit. It can read what the
kernel shows any process: the processor, the memory, the kernel's version, and the host paths of the folders mounted
for it, which hold the user's name. And the grader shares the sandbox with the code it grades, so that code can still
reach its own grade.

`--fetch` gets bwrap from the distribution's own archive when the host has none on its path: `apt-get download` and
`dpkg-deb -x`, with no root. It lands in the host's exam folder under sandbox/, beside a SOURCE.json with the URL, the
package, the version and the hashes. bwrap is counted as a sandbox only after one command has run in it.
"""
from __future__ import annotations

import functools
import re
import subprocess
from dataclasses import dataclass
from typing import Callable

from bench.exam import host

ENV = "/exam/env"
"""Where a grader's environment is shown in the sandbox."""
DATA = "/exam/data"
"""Where a benchmark's fetched files are shown in the sandbox."""
WORK = "/work"
"""The folder a grader starts in, which is also its home and its temporary folder."""
PLAIN = {"PATH": "/usr/bin:/bin", "HOME": WORK, "TMPDIR": WORK, "LANG": "C.UTF-8"}
"""The environment inside, before what the caller adds."""
SYSTEM = ("/etc/ld.so.cache", "/etc/fonts", "/var/cache/fontconfig")
"""What is shown of the host outside /usr, where the host has it: the loader's list of libraries, and the system's
font settings with their cache, so that a CAD kernel that sets text finds the fonts it finds outside."""
WORK_BYTES, TMP, SHM = 1 << 30, 1 << 28, 1 << 26
"""The most that /work, /tmp and /dev/shm hold. They are memory, so the caps are what keeps a grader from filling it with files."""
NONE = "none"
"""A record's `sandbox` when its grade was made outside one."""
NOT_NEEDED = "not needed"
"""A record's `sandbox` when the grader executes nothing the model wrote."""
REFUSAL = """the grader of this benchmark executes code the model wrote, and there is no sandbox to hold it: {why}.
Run once with --fetch to set one up. It needs Linux, or WSL on Windows, with user namespaces, and it gets bwrap from the distribution's archive when none is installed.
--no-sandbox grades without one. The model's code then runs as the user, with the user's files and the network in reach."""

_FETCH = r'''
import glob, hashlib, json, os, shutil, subprocess, sys, tempfile

def stop(why):
    print(json.dumps({"error": why}))
    sys.exit(0)

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

with tempfile.TemporaryDirectory() as work:
    try:
        listed = subprocess.run(["apt-get", "download", "--print-uris", "bubblewrap"], cwd=work, capture_output=True, text=True).stdout.split()
        got = subprocess.run(["apt-get", "download", "bubblewrap"], cwd=work, capture_output=True, text=True)
    except OSError:
        stop("this system has no apt-get to fetch bubblewrap with, so install it with the system's own package manager")
    debs = glob.glob(os.path.join(work, "bubblewrap_*.deb"))
    if got.returncode != 0 or len(debs) != 1:
        stop("apt-get download bubblewrap failed: " + (got.stderr or got.stdout).strip()[-300:])
    into = os.path.join(TARGET, "bubblewrap")
    shutil.rmtree(into, ignore_errors=True)
    os.makedirs(TARGET, exist_ok=True)
    unpacked = subprocess.run(["dpkg-deb", "-x", debs[0], into], capture_output=True, text=True)
    binary = os.path.join(into, "usr", "bin", "bwrap")
    if unpacked.returncode != 0 or not os.path.isfile(binary):
        stop("dpkg-deb could not unpack bubblewrap: " + unpacked.stderr.strip()[-300:])
    said = subprocess.run([binary, "--version"], capture_output=True, text=True).stdout.strip()
    manifest = {"version": {"package": os.path.basename(debs[0]), "bwrap": said, "listed": listed[-1] if listed else ""},
                "archive": listed[0].strip("'") if listed else "", "archive_sha256": sha(debs[0]),
                "files": [{"path": "bubblewrap/usr/bin/bwrap", "sha256": sha(binary)}]}
    with open(os.path.join(TARGET, "SOURCE.json"), "w", encoding="utf-8", newline="\n") as out:
        out.write(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(manifest))
'''
"""Run on the host. It downloads the bubblewrap package, which apt-get holds to the hash in its signed index, unpacks
it into TARGET with no root, and writes SOURCE.json there: the URL, the package, the version and the hashes."""


class Missing(RuntimeError):
    """A grader that executes the model's code was about to run, and the host has no sandbox."""


@dataclass(frozen=True)
class Box:
    """A bwrap on the host, with what the host's layout asks of the command line: which top folders are links into
    /usr, which are folders of their own, and what is mounted below them and has to be covered."""

    path: str
    version: str
    links: tuple[tuple[str, str], ...] = (("/bin", "usr/bin"), ("/lib", "usr/lib"), ("/lib64", "usr/lib64"), ("/sbin", "usr/sbin"))
    folders: tuple[str, ...] = ()
    covered: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        return f"bwrap {self.version}"


def command(box: Box, argv: list[str], readonly: dict[str, str], env: dict[str, str], seconds: float) -> list[str]:
    """The command line that runs `argv` in the sandbox for at most `seconds`. `readonly` maps a path inside to the
    host folder shown there, and `env` is added to PLAIN. Nothing else of the host but /usr gets in."""
    capped = tuple(int(part) for part in re.findall(r"\d+", box.version)[:2]) >= (0, 8)      # bwrap learnt --size in 0.8
    line = ["timeout", "--kill-after=5", str(max(1, round(seconds))), box.path,
            "--unshare-all", "--die-with-parent", "--new-session", "--hostname", "exam", "--clearenv"]
    for name, value in {**PLAIN, **env}.items():
        line += ["--setenv", name, value]
    line += ["--ro-bind", "/usr", "/usr"]
    for name, target in box.links:
        line += ["--symlink", target, name]
    for name in box.folders:
        line += ["--ro-bind", name, name]
    for point in box.covered:
        line += ["--tmpfs", point, "--remount-ro", point]
    for path in SYSTEM:
        line += ["--ro-bind-try", path, path]
    for inside, outside in readonly.items():
        line += ["--ro-bind", outside, inside]
    line += ["--proc", "/proc", "--dev", "/dev"]
    for size, point in ((SHM, "/dev/shm"), (TMP, "/tmp"), (WORK_BYTES, WORK)):
        line += [*(["--size", str(size)] if capped else []), "--tmpfs", point]
    return [*line, "--chdir", WORK, "--remount-ro", "/dev", "--remount-ro", "/", *argv]      # /dev and / are memory too, and have no cap


def bare(argv: list[str], readonly: dict[str, str], env: dict[str, str], seconds: float) -> list[str]:
    """The command line that runs `argv` on the host with no sandbox: the same limit and variables, and each path of
    the sandbox swapped for the folder it stands for."""
    def outside(text: str) -> str:
        for inside, folder in readonly.items():
            if text == inside or text.startswith(inside + "/"):
                return folder + text[len(inside):]
        return text

    return ["timeout", "--kill-after=5", str(max(1, round(seconds))), "env", *[f"{name}={outside(value)}" for name, value in env.items()],
            *[outside(part) for part in argv]]


@functools.lru_cache(maxsize=None)
def look() -> tuple[Box | None, str]:
    """The host's sandbox, or None and why there is none. bwrap counts only when it is as it was fetched and one
    command has run in it."""
    try:
        known = host.facts()
    except host.Down as down:
        return None, str(down)
    if not known["bwrap"]:
        return None, f"bwrap is not on the path{' of WSL' if host.WSL else ''}, and none was fetched"
    if known["fetched"] and known["sha256"] != known["pinned"]:
        return None, "the bwrap that was fetched no longer has the hash recorded for it"
    box = Box(known["bwrap"], known["version"] or "of no known version", tuple(sorted(known["links"].items())), tuple(known["folders"]),
              tuple(known["covered"]))
    try:
        tried = host.run(command(box, ["true"], {}, {}, 60))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"bwrap did not start: {exc}"
    if tried.returncode != 0:
        return None, f"bwrap is there and no command runs in it: {tried.stderr.strip()[-300:] or f'exit code {tried.returncode}'}"
    return box, ""


def find() -> Box | None:
    return look()[0]


def how(executes: bool, sandboxed: bool = True) -> str:
    """How a run's grades are made, for its records: in which sandbox, in none, or with no need of one. Raises
    Missing when the grader executes the model's code, the run was not told to do without, and there is no sandbox."""
    if not executes:
        return NOT_NEEDED
    if not sandboxed:
        return NONE
    box, why = look()
    if box is None:
        raise Missing(REFUSAL.format(why=why))
    return box.label


def run(argv: list[str], readonly: dict[str, str], env: dict[str, str], timeout: float, input: str | bytes | None = None,
        sandboxed: bool = True) -> subprocess.CompletedProcess:
    """Run a command on the host in the sandbox, with the paths of `readonly` shown to it and `input` on its stdin.
    Exit code 124 means it ran past the limit. `sandboxed=False` runs it with no sandbox, and is for a run that was
    told to. Raises Missing when a sandbox is wanted and there is none."""
    if sandboxed:
        box, why = look()
        if box is None:
            raise Missing(REFUSAL.format(why=why))
        line = command(box, argv, readonly, env, timeout)
    else:
        line = bare(argv, readonly, env, timeout)
    return host.run(line, input=input, timeout=timeout + 30)


def fetch(say: Callable[[str], None] = print) -> Box:
    """Make sure the host has a sandbox, and fetch bwrap from the distribution's archive when it has none on its path
    or its fetched one has changed. Raises Missing when there is still none."""
    forget()
    box, why = look()
    if box is None:
        try:
            known = host.facts()
            if not known["bwrap"] or (known["fetched"] and known["sha256"] != known["pinned"]):
                got = host.script(_FETCH, TARGET=f"{known['exam']}/sandbox")
                if got.get("error"):
                    raise Missing(f"no sandbox could be set up: {got['error']}")
                say(f"fetched {got['version']['package']} from {got['archive']}")
        except host.Down as down:
            raise Missing(f"no sandbox could be set up: {down}") from None
        forget()
        box, why = look()
    if box is None:
        raise Missing(f"no sandbox could be set up: {why}")
    say(f"the sandbox is {box.label}")
    return box


def forget() -> None:
    """Drop what was learnt of the host, so that the next look asks it again."""
    look.cache_clear()
    host.facts.cache_clear()
