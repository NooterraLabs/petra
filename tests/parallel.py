"""Run the test suite in parallel: one process for each test module, several at a time on
this machine, and more on other machines over ssh.

    python tests/parallel.py [-j N] [--fast] [--local] [--hosts FILE] [--shard K/N] [--record] [NAME ...]

With no NAME it runs every tests/test_*.py. The longest modules start first, by the times
in tests/durations.tsv, which `--record` rewrites from this run.

`--fast` leaves out every module that took over SLOW seconds when last recorded, and says
which. It is for the loop of editing and checking. The whole suite still runs before a
commit, and CI runs it on every push.

A hosts file adds machines, one a line, and the default is ~/.petra/test-hosts:

    USER@HOST slots=4 python=PATH [lake=PATH] [skip=MODULE,MODULE]

Before the run each host gets the working tree, tracked and untracked alike, as a tar
stream over ssh into ~/petra-tests/NAME, and builds the kernel there when `lake` names
one. Then every free slot, here or there, takes the longest module left, so a slow machine
takes fewer. A host that cannot be reached or prepared is left out, and the run goes on.

`--shard K/N` runs the K-th of N shares of the modules, split so the shares take about the
same time. CI runs one share in each job.

Exits 0 when every module passed. A module that failed is printed whole at the end.

Measured on a 4-core desktop, 82 modules and 1,740 tests: 32 minutes one after another,
12 with 4 at a time and 12 with 8, and 8 with a second 4-core machine. `--fast` took under
5 minutes on the desktop alone and under 2 with the second machine. Two threads of one
core do the work of about one, so the default is half the logical processors. The longest
module takes 8 minutes while others run beside it, and no split by module goes under the
longest. Running a long module class by class was tried and made it slower: its classes
share what the module builds once.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tarfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DURATIONS = ROOT / "tests" / "durations.tsv"
HOSTS = Path.home() / ".petra" / "test-hosts"
SLOW = 60.0
"""`--fast` leaves out a module that took longer than this, in seconds."""
UNKNOWN = 5.0
"""The time assumed for a module that has no recorded one."""
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]


@dataclass(frozen=True)
class Host:
    address: str
    slots: int
    python: str
    lake: str | None
    skip: frozenset[str]

    @property
    def folder(self) -> str:
        return f"petra-tests/{ROOT.name}"


@dataclass
class Result:
    unit: str
    where: str
    seconds: float
    code: int
    output: str
    tests: int = 0
    counts: dict[str, int] = field(default_factory=dict)


def recorded() -> dict[str, float]:
    if not DURATIONS.is_file():
        return {}
    lines = (line.split("\t") for line in DURATIONS.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#"))
    return {name: float(seconds) for name, seconds in lines}


def hosts(path: Path) -> list[Host]:
    found = []
    for line in path.read_text(encoding="utf-8").splitlines() if path.is_file() else []:
        words = line.split("#")[0].split()
        if not words:
            continue
        options = dict(word.split("=", 1) for word in words[1:])
        found.append(Host(words[0], int(options.get("slots", 1)), options.get("python", "python3"), options.get("lake"),
                          frozenset(filter(None, options.get("skip", "").split(",")))))
    return found


def shares(units: list[str], known: dict[str, float], n: int) -> list[list[str]]:
    """N lists of modules that take about the same time: the longest module first, each to
    the share that is lightest so far."""
    out: list[list[str]] = [[] for _ in range(n)]
    load = [0.0] * n
    for unit in sorted(units, key=lambda u: (-known.get(u, UNKNOWN), u)):
        k = load.index(min(load))
        out[k].append(unit)
        load[k] += known.get(unit, UNKNOWN)
    return out


def summary(output: str) -> tuple[int, dict[str, int]]:
    """How many tests a module ran, and the counts on unittest's last line."""
    ran = re.search(r"^Ran (\d+) tests? in", output, re.M)
    last = re.search(r"^(?:OK|FAILED)(?: \((.*)\))?\s*\Z", output.strip(), re.M)
    counts = dict(part.split("=") for part in last[1].split(", ")) if last and last[1] else {}
    return (int(ran[1]) if ran else 0), {name: int(n) for name, n in counts.items()}


def run_here(unit: str) -> tuple[int, str]:
    done = subprocess.run([sys.executable, "-m", "unittest", unit], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", stdin=subprocess.DEVNULL)
    return done.returncode, done.stdout + done.stderr


def run_there(host: Host, unit: str) -> tuple[int, str]:
    done = subprocess.run([*SSH, host.address, f"cd {host.folder} && {host.python} -m unittest {unit}"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL)
    return done.returncode, done.stdout + done.stderr


def prepare(host: Host) -> str | None:
    """Send the tree to the host and build the kernel there. Gives why it failed, or None.
    The build folder of the kernel is kept from the run before, so the build is short."""
    listed = subprocess.run(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True)
    names = [n for n in listed.stdout.decode("utf-8").split("\0") if n and (ROOT / n).is_file()]
    folder = host.folder
    receive = (f"rm -rf {folder}.new && mkdir -p {folder}.new && tar -xzf - -C {folder}.new && "
               f"if [ -d {folder}/kernel/.lake ]; then mv {folder}/kernel/.lake {folder}.new/kernel/.lake; fi && "
               f"rm -rf {folder} && mv {folder}.new {folder}")
    if host.lake:
        receive += f" && cd {folder}/kernel && {host.lake} build"
    ssh = subprocess.Popen([*SSH, host.address, receive], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        with tarfile.open(fileobj=ssh.stdin, mode="w|gz") as tar:
            for name in names:
                tar.add(ROOT / name, arcname=name, recursive=False)
        ssh.stdin.close()
    except OSError:
        pass      # ssh has gone, and what it printed says why
    said = ssh.stdout.read().decode("utf-8", "replace")
    return None if ssh.wait() == 0 else (said.strip().splitlines() or ["ssh failed"])[-1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("names", nargs="*", metavar="NAME", help="test modules, as unittest names them: tests.test_grid")
    parser.add_argument("-j", "--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2), help="modules at a time on this machine")
    parser.add_argument("--fast", action="store_true", help=f"leave out the modules that took over {SLOW:.0f} s when last recorded")
    parser.add_argument("--hosts", type=Path, default=HOSTS, help=f"other machines to run on; default {HOSTS}")
    parser.add_argument("--local", action="store_true", help="run on this machine only")
    parser.add_argument("--shard", metavar="K/N", help="run the K-th of N shares")
    parser.add_argument("--record", action="store_true", help=f"write this run's times to {DURATIONS.relative_to(ROOT).as_posix()}")
    args = parser.parse_args()
    known = recorded()
    todo = args.names or sorted(f"tests.{p.stem}" for p in (ROOT / "tests").glob("test_*.py"))
    left_out = sorted(u for u in todo if args.fast and known.get(u, 0) > SLOW)
    todo = [u for u in todo if u not in left_out]
    if args.shard:
        k, n = (int(x) for x in args.shard.split("/"))
        todo = shares(todo, known, n)[k - 1]
    todo.sort(key=lambda u: (-known.get(u, UNKNOWN), u))
    started = time.monotonic()

    ready: list[Host] = []
    others = [] if args.local or args.shard else hosts(args.hosts)
    if others:
        failed: dict[str, str] = {}

        def send(host: Host) -> None:
            try:
                why = prepare(host)
            except Exception as exc:      # a host that cannot be prepared is left out, whatever went wrong
                why = f"{type(exc).__name__}: {exc}"
            (ready.append(host) if why is None else failed.__setitem__(host.address, why))

        senders = [threading.Thread(target=send, args=(h,)) for h in others]
        for t in senders:
            t.start()
        for t in senders:
            t.join()
        for address, why in failed.items():
            print(f"left out {address}: {why}", flush=True)
        print(f"sent the tree to {', '.join(h.address for h in ready) or 'no host'} in {time.monotonic() - started:.0f} s", flush=True)

    lock = threading.Lock()
    results: list[Result] = []
    total = len(todo)

    def take(skip: frozenset[str]) -> str | None:
        with lock:
            for n, unit in enumerate(todo):
                if unit not in skip:
                    return todo.pop(n)
        return None

    def work(where: str, run, skip: frozenset[str] = frozenset()) -> None:
        while (unit := take(skip)) is not None:
            began = time.monotonic()
            code, output = run(unit)
            if where != "here" and code == 255:      # ssh's own failure: the module goes back for another slot
                with lock:
                    todo.insert(0, unit)
                print(f"lost {where}: {(output.strip().splitlines() or ['ssh failed'])[-1]}", flush=True)
                return
            tests, counts = summary(output)
            result = Result(unit, where, time.monotonic() - began, code, output, tests, counts)
            with lock:
                results.append(result)
                print(f"[{len(results):>3}/{total}] {'ok  ' if code == 0 else 'FAIL'} {result.seconds:6.1f} s  {unit}  ({tests} tests, {where})", flush=True)

    workers = [threading.Thread(target=work, args=("here", run_here)) for _ in range(max(1, args.jobs))]
    workers += [threading.Thread(target=work, args=(h.address, lambda unit, h=h: run_there(h, unit), h.skip)) for h in ready for _ in range(h.slots)]
    for t in workers:
        t.start()
    for t in workers:
        t.join()

    bad = [r for r in results if r.code != 0]
    for r in bad:
        print(f"\n{'=' * 70}\n{r.unit} on {r.where}\n{r.output.rstrip()}", flush=True)
    counts: dict[str, int] = {}
    for r in results:
        for name, n in r.counts.items():
            counts[name] = counts.get(name, 0) + n
    wall, spent = time.monotonic() - started, sum(r.seconds for r in results)
    detail = ", ".join(f"{name}={n}" for name, n in sorted(counts.items()))
    print(f"\nRan {sum(r.tests for r in results)} tests in {len(results)} modules in {wall:.0f} s ({spent:.0f} s of work)")
    if left_out:
        print(f"left out as slow, {sum(known[u] for u in left_out):.0f} s of work: {', '.join(u.removeprefix('tests.') for u in left_out)}")
    if todo:
        print(f"NOT RUN, no slot would take them: {', '.join(todo)}")
    print(("OK" if not bad and not todo else f"FAILED ({len(bad)} modules)") + (f" ({detail})" if detail else ""))
    if args.record:
        times = {**known, **{r.unit: r.seconds for r in results}}
        DURATIONS.write_text("# Seconds each test module took on the run that last recorded it (python tests/parallel.py --record).\n"
                             + "".join(f"{name}\t{seconds:.1f}\n" for name, seconds in sorted(times.items())), encoding="utf-8", newline="\n")
    return 0 if not bad and not todo else 1


if __name__ == "__main__":
    sys.exit(main())
