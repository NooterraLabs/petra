"""The grader host: where a benchmark's grader runs. It is this machine on Linux, and WSL on Windows.

A grader executes code a model wrote, and the sandbox that holds it (sandbox.py) is made of Linux namespaces. So on
Windows the harness stays where it is, and only the grading step goes through `wsl.exe`: the grader's environment and
a copy of the benchmark's fetched files live in WSL's own file system, under ~/.petra/exam there, and never under
/mnt. On Linux the host is this machine, the folders are the harness's own, and nothing is copied.

A grader environment is built on the host's /usr/bin/python3, by `uv` when the host has it and by `venv` and `pip`
otherwise. The sandbox shows /usr and no home folder, so an interpreter that lives in a home folder would not start.

A small program the harness needs run on the host is sent to that Python on stdin, so no file of the harness has to
be there. Nothing here knows a benchmark.
"""
from __future__ import annotations

import functools
import io
import json
import os
import re
import subprocess
import tarfile
import threading
from pathlib import Path, PurePosixPath

from bench.exam import data

WSL = os.name == "nt"
PYTHON = "/usr/bin/python3"
"""The host's own Python, which the sandbox can see. Grader environments are built on it."""
SLOW = 300.0
"""Seconds a small command on the host may take. WSL can need most of a minute to start on a busy machine."""
KEEP = 1 << 24
"""The most bytes held of what a command prints, on each of stdout and stderr. A grader runs a model's code, and code
that prints without end must not fill this process's memory."""

_FACTS = r'''
import hashlib, json, os, re, shutil, subprocess
home = os.path.expanduser("~")
exam = EXAM or os.path.join(home, ".petra", "exam")
own = os.path.join(exam, "sandbox", "bubblewrap", "usr", "bin", "bwrap")
bwrap = shutil.which("bwrap") or (own if os.access(own, os.X_OK) else None)
version = digest = pinned = None
if bwrap:
    said = subprocess.run([bwrap, "--version"], capture_output=True, text=True).stdout.split()
    version = said[-1] if said else None
    digest = hashlib.sha256(open(bwrap, "rb").read()).hexdigest()
if bwrap == own:
    try:
        pinned = json.load(open(os.path.join(exam, "sandbox", "SOURCE.json")))["files"][0]["sha256"]
    except (OSError, ValueError, LookupError):
        pinned = ""
roots = ["/bin", "/lib", "/lib32", "/lib64", "/libx32", "/sbin"]
folders = [root for root in roots if os.path.isdir(root) and not os.path.islink(root)]
points = sorted({re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), line.split()[4]) for line in open("/proc/self/mountinfo")})
below = [point for point in points if any(point.startswith(top + "/") for top in ["/usr", *folders])]
at = os.path.join(home, ".local", "bin", "uv")
print(json.dumps({
    "home": home, "exam": exam, "bwrap": bwrap, "version": version, "sha256": digest, "pinned": pinned, "fetched": bwrap == own,
    "links": {root: os.readlink(root) for root in roots if os.path.islink(root)}, "folders": folders,
    "covered": [point for point in below if not any(point.startswith(other + "/") for other in below)],
    "uv": shutil.which("uv") or (at if os.access(at, os.X_OK) else None),
}))
'''
"""Run on the host. It prints the home folder, the exam folder, where bwrap is with its version and hash, which of
the system's top folders are links into /usr, what is mounted below the folders the sandbox shows, and where uv is."""

_HASHES = r'''
import hashlib, json, os
found = {}
for path in PATHS:
    try:
        found[path] = hashlib.sha256(open(os.path.join(FOLDER, path), "rb").read()).hexdigest()
    except OSError:
        found[path] = None
print(json.dumps(found))
'''


class Down(RuntimeError):
    """The host cannot be used or a step on it failed: WSL does not start, it has no Python, or a command there said no."""


def run(argv: list[str], input: str | bytes | None = None, timeout: float | None = SLOW, cwd: str | None = None,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run a command on the host and give back what it printed, as text. Bytes go in and come out untranslated, the
    command gets a plain environment unless one is given, at most KEEP bytes of each stream are held, and what
    wsl.exe itself remarks on stderr is dropped. Raises subprocess.TimeoutExpired past the limit."""
    line = ["wsl.exe", "--cd", cwd or "/", "-e", *argv] if WSL else argv
    sent = input.encode("utf-8") if isinstance(input, str) else input
    process = subprocess.Popen(line, stdin=subprocess.PIPE if sent is not None else subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env or data.plain_env(WSL_UTF8="1"), cwd=None if WSL else cwd)
    printed: dict[str, bytes] = {}
    readers = [threading.Thread(target=_hold, args=(process.stdout, False, printed, "out"), daemon=True),
               threading.Thread(target=_hold, args=(process.stderr, True, printed, "err"), daemon=True)]
    for reader in readers:
        reader.start()
    try:
        if sent is not None:
            try:
                process.stdin.write(sent)
                process.stdin.close()
            except OSError:
                pass      # the command ended before it had read everything
        process.wait(timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        raise
    finally:
        for reader, pipe in zip(readers, (process.stdout, process.stderr)):
            reader.join(15)
            if not reader.is_alive():       # a pipe that something still holds open is given up on, and counts as nothing printed
                pipe.close()
    said = [text for text in printed.get("err", b"").decode("utf-8", "replace").splitlines(keepends=True) if not (WSL and text.startswith("wsl: "))]
    return subprocess.CompletedProcess(argv, process.returncode, printed.get("out", b"").decode("utf-8", "replace"), "".join(said))


def _hold(pipe, last: bool, into: dict[str, bytes], name: str) -> None:
    """Read a pipe to its end and keep at most KEEP bytes of it: the last ones of stderr, where an error is, and the
    first of stdout, where a result is. The rest is read and dropped."""
    chunks: list[bytes] = []
    held = 0
    for chunk in iter(lambda: pipe.read1(1 << 16), b""):
        if last:
            chunks.append(chunk)
            held += len(chunk)
            if held > 2 * KEEP:
                chunks, held = [b"".join(chunks)[-KEEP:]], KEEP
        elif held < KEEP:
            chunks.append(chunk[:KEEP - held])
            held += len(chunks[-1])
    into[name] = b"".join(chunks)[-KEEP:] if last else b"".join(chunks)


def script(program: str, timeout: float = SLOW, **names: object) -> dict:
    """Run a Python program on the host, with the given names set at its top, and read the JSON it prints."""
    head = "".join(f"{name} = {value!r}\n" for name, value in names.items())
    try:
        done = run([PYTHON, "-I", "-"], input=head + program, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Down(f"{'WSL' if WSL else PYTHON} did not start: {exc}") from None
    try:
        return json.loads(done.stdout)
    except ValueError:
        said = (done.stderr.strip() or done.stdout.strip())[-500:]
        raise Down(f"{PYTHON}{' in WSL' if WSL else ''} gave no answer: exit code {done.returncode}: {said}") from None


@functools.lru_cache(maxsize=None)
def facts() -> dict:
    """What the harness needs to know of the host, asked once. Raises Down when the host cannot be used."""
    return script(_FACTS, EXAM=None if WSL else str(data.HOME))


def env(name: str) -> str:
    """The folder of the grader environment of that name, as the host sees it, whether or not it exists yet."""
    return f"{facts()['exam']}/venv/{_plain(name)}"


def where(folder: Path, name: str) -> str:
    """A benchmark's folder as the host sees it: the folder itself on Linux, and its copy in WSL on Windows."""
    return f"{facts()['exam']}/data/{_plain(name)}" if WSL else str(folder.resolve())


def named() -> list[PurePosixPath]:
    """The folders of WSL whose paths name the user, to be taken out of a text before it goes to a model: the exam
    folder, and the home folder unless it is right under the root. Empty on Linux, where the harness's own folders
    are the host's, and when WSL cannot be asked."""
    if not WSL:
        return []
    try:
        exam, home = PurePosixPath(facts()["exam"]), PurePosixPath(facts()["home"])
    except Down:
        return []
    return [exam, *([home] if len(home.parts) >= 3 else [])]


def _plain(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", name) or name in (".", ".."):
        raise ValueError(f"{name!r} cannot name a folder on the host")
    return name


def mirror(folder: Path, name: str) -> None:
    """On Windows, put a benchmark's fetched files and its SOURCE.json into WSL in place of what was there, and check
    the copy against the hashes. On Linux the folder is its own copy."""
    if not WSL:
        return
    packed = io.BytesIO()
    with tarfile.open(fileobj=packed, mode="w") as archive:
        for path in ["SOURCE.json", *[f["path"] for f in data.manifest(folder)["files"]]]:
            content = data.inside(folder, path).read_bytes()
            member = tarfile.TarInfo(path)
            member.size, member.mode = len(content), 0o644
            archive.addfile(member, io.BytesIO(content))
    target = where(folder, name)
    for argv, sent in ((["rm", "-rf", target], None), (["mkdir", "-p", target], None), (["tar", "-xf", "-", "-C", target], packed.getvalue())):
        _must(run(argv, input=sent), f"could not copy the benchmark's files into WSL ({argv[0]})")
    if differ := changed(folder, name):
        raise Down(f"{len(differ)} of the benchmark's files did not reach WSL as they were fetched")


def changed(folder: Path, name: str) -> list[str]:
    """The files of the host's copy that are missing or do not have the hash SOURCE.json records. On Linux there is
    no copy, and data.changed has looked at the folder itself."""
    files = (data.manifest(folder) or {}).get("files", [])
    if not WSL or not files:
        return []
    found = script(_HASHES, FOLDER=where(folder, name), PATHS=[f["path"] for f in files])
    return [f["path"] for f in files if found.get(f["path"]) != f["sha256"]]


def make_env(name: str, packages: list[str]) -> str:
    """Create the grader environment on the host, on its own Python, and install the pinned packages into it with
    their bytecode, which the sandbox could not write later. Nothing is installed into the system Python."""
    target, uv = env(name), facts()["uv"]
    whole = None if WSL else dict(os.environ)      # an install may need the proxy this machine is behind
    made = run(["test", "-x", f"{target}/bin/python"]).returncode == 0
    if uv:
        if not made:
            _must(run([uv, "venv", "--quiet", "--python", PYTHON, target], env=whole), "could not make the grader's environment")
        install = [uv, "pip", "install", "--quiet", "--compile-bytecode", "--python", f"{target}/bin/python", *packages]
    else:
        if not made:
            _must(run([PYTHON, "-m", "venv", target], env=whole), "could not make the grader's environment (the host has no uv, and venv failed)")
        install = [f"{target}/bin/python", "-m", "pip", "install", "--disable-pip-version-check", "--quiet", *packages]
    _must(run(install, timeout=3600, env=whole), "could not install the grader's packages")
    return target


def _must(done: subprocess.CompletedProcess, why: str) -> None:
    if done.returncode != 0:
        raise Down(f"{why}: exit code {done.returncode}: {(done.stderr.strip() or done.stdout.strip())[-500:]}")
