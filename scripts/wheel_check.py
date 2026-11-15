"""Install a built wheel as a stranger would, and see that the kernel inside it gives the verdicts.

    python scripts/wheel_check.py FILE [REQUIREMENT ...] [--platform TAG] [--no-kernel]

FILE is a wheel or an sdist. The script makes a fresh virtual environment in a temporary
directory outside the repository and installs FILE there with pip. Petra needs no other
package. A REQUIREMENT goes to the same pip command, for a run that wants one beside it.
From that directory the script runs `petra check` on examples/deck/lap_pass.petra and on
corpus/cases/old/circuit_pass.petra, and prints the first eight lines of each report.

It exits 1 unless all of these hold:

- the wheel is built for one platform, and for `--platform` when that is given
- the kernel the installed package runs is the file inside the package
- the lap's `kernel` line gives the kernel's verdict and how many proofs it checked
- the lap's `path` line says the kernel worked out every cell from the rules deck, and the
  circuit's that there was nothing to hand the kernel
- the lap says PASS_WAIVED and exits 6, since it rests cells on a waiver, and the circuit
  says UNKNOWN and exits 2, since no deck of rules has a circuit

With `--no-kernel` it asks the opposite, for an sdist or a pure wheel: the package holds no
kernel, and the lap's check gives no verdict: nothing on stdout, the reason on stderr, exit 4.
The circuit reads UNKNOWN as before, since the kernel is not asked about it.

The `wheels` workflow runs this on each platform's wheel, on a runner of that platform.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LAP = ROOT / "examples" / "deck" / "lap_pass.petra"
CIRCUIT = ROOT / "corpus" / "cases" / "old" / "circuit_pass.petra"

# What each design must say, with its exit code. The lap rests five cells on waivers, so it
# passes as PASS_WAIVED. No deck of rules has a circuit, so there is nothing to hand the
# kernel, and the design reads UNKNOWN.
SAYS = {LAP: ("PASS_WAIVED", 6), CIRCUIT: ("UNKNOWN", 2)}
NO_VERDICT = 4

CHECKED = re.compile(r"kernel +petra-verify gives (PASS|FAIL|UNKNOWN): it checked [1-9]\d* of \d+ proofs")
NO_DECK = re.compile(r"path +none: no deck of rules has this design's kinds of part")
FROM_RULES = re.compile(r"path +rules: the kernel worked out every cell from the rules deck")

# A stranger has no kernel named in the environment and no repository on sys.path.
ENV = {k: v for k, v in os.environ.items() if k not in ("PETRA_VERIFY", "PYTHONPATH")}


def run(*argv: str | Path, cwd: Path, code: int = 0, said: list[str] | None = None) -> str:
    """What the command printed. With `said`, what it wrote to stderr is added to it."""
    done = subprocess.run([str(a) for a in argv], cwd=cwd, env=ENV, capture_output=True, text=True, timeout=900)
    if done.returncode != code:
        sys.exit(f"{' '.join(map(str, argv))} exited {done.returncode}, not {code}\n{done.stdout}\n{done.stderr}")
    if said is not None:
        said.append(done.stderr)
    return done.stdout


def faults(file: Path, requirements: list[str], kernel: bool, platform: str | None, where: Path) -> list[str]:
    """What is wrong with the file, installed in a fresh environment at `where`."""
    found = []
    tag = file.name.removesuffix(".whl").split("-")[-1] if file.suffix == ".whl" else None
    if kernel and tag in (None, "any"):
        found.append(f"{file.name} is not a wheel for one platform")
    if platform is not None and tag != platform:
        found.append(f"{file.name} is not for {platform}")
    run(sys.executable, "-m", "venv", where / "venv", cwd=where)
    scripts = where / "venv" / ("Scripts" if os.name == "nt" else "bin")
    python = shutil.which("python", path=str(scripts))
    run(python, "-m", "pip", "install", "--disable-pip-version-check", file, *requirements, cwd=where)
    ran = run(python, "-c", "from petra import verify; print(verify.binary())", cwd=where).strip()
    print(f"kernel in use: {ran}")
    if kernel and ran == "None":
        found.append("the installed package finds no kernel to run")
    elif kernel and not Path(ran).resolve().is_relative_to((where / "venv").resolve()):
        found.append(f"the installed package runs the kernel at {ran}, which is not inside it")
    elif not kernel and ran != "None":
        found.append(f"the installed package runs a kernel, {ran}")
    for design in (LAP, CIRCUIT):
        status, code = SAYS[design]
        if not kernel and design == LAP:
            why: list[str] = []
            printed = run(shutil.which("petra", path=str(scripts)), "check", design, cwd=where, code=NO_VERDICT, said=why)
            print(f"\n$ petra check {design.relative_to(ROOT).as_posix()}\n{why[0].strip()}")
            if printed or "no verdict" not in why[0]:
                found.append(f"{design.name}: with no kernel the check must print nothing and say on stderr that there is no verdict")
            continue
        lines = run(shutil.which("petra", path=str(scripts)), "check", design, cwd=where, code=code).splitlines()
        print("\n".join([f"\n$ petra check {design.relative_to(ROOT).as_posix()}", *lines[:8]]))
        wanted = [CHECKED, FROM_RULES] if design == LAP else [NO_DECK]      # the circuit reads the same with a kernel and without
        found += [f"{design.name}: no line of the report matches {pattern.pattern!r}"
                  for pattern in wanted if not any(pattern.match(line) for line in lines)]
        if not lines[0].endswith(f": {status}"):
            found.append(f"{design.name}: the report does not start with {status}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file", type=Path, help="a wheel or an sdist")
    parser.add_argument("requirements", nargs="*", metavar="REQUIREMENT", help="another requirement for pip to install beside the file")
    parser.add_argument("--platform", help="the platform tag the wheel must carry")
    parser.add_argument("--no-kernel", action="store_true", help="the package must hold no kernel, and give no verdict")
    args = parser.parse_args()
    where = Path(tempfile.mkdtemp(prefix="petra-wheel-")).resolve()
    if where.is_relative_to(ROOT):
        sys.exit(f"the temporary directory {where} is inside the repository")
    try:
        found = faults(args.file.resolve(), args.requirements, not args.no_kernel, args.platform, where)
    finally:
        shutil.rmtree(where, ignore_errors=True)
    print("".join(f"\nFAULT: {fault}" for fault in found) or f"\n{args.file.name}: ok")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
