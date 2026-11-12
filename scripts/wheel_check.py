"""Install a built wheel as a stranger would, and see that the kernel inside it checks verdicts.

    python scripts/wheel_check.py FILE [REQUIREMENT ...] [--platform TAG] [--no-kernel]

FILE is a wheel or an sdist. The script makes a fresh virtual environment in a temporary
directory outside the repository and installs FILE there with pip, which fetches numpy and
scipy from the package index. A REQUIREMENT, such as numpy==2.4.6, goes to the same pip
command and pins what it fetches. From that directory the script runs `petra check` on
examples/deck/lap_pass.petra and on examples/circuit_pass.petra, and prints the first eight
lines of each report.

It exits 1 unless all of these hold:

- the wheel is built for one platform, and for `--platform` when that is given
- the kernel the installed package runs is the file inside the package
- each report's `kernel` line says how many proofs petra-verify checked
- the lap's `path` line says the kernel worked out every cell from the rules deck
- the lap says PASS_WAIVED and exits 6, since it rests cells on a waiver, and the circuit
  says PASS and exits 0

With `--no-kernel` it asks the opposite, for an sdist or a pure wheel: the package holds no
kernel, and each report says that none ran.

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
CIRCUIT = ROOT / "examples" / "circuit_pass.petra"

# What each design must say, with its exit code. The lap rests four cells on a waiver, so it
# passes as PASS_WAIVED.
SAYS = {LAP: ("PASS_WAIVED", 6), CIRCUIT: ("PASS", 0)}

CHECKED = re.compile(r"kernel +petra-verify checked [1-9]\d* of \d+ proofs")
NOT_RUN = re.compile(r"kernel +not run: ")
FROM_RULES = re.compile(r"path +rules: the kernel worked out every cell from the rules deck")

# A stranger has no kernel named in the environment and no repository on sys.path.
ENV = {k: v for k, v in os.environ.items() if k not in ("PETRA_VERIFY", "PETRA_SHAPES_XLSX", "PYTHONPATH")}


def run(*argv: str | Path, cwd: Path, code: int = 0) -> str:
    done = subprocess.run([str(a) for a in argv], cwd=cwd, env=ENV, capture_output=True, text=True, timeout=900)
    if done.returncode != code:
        sys.exit(f"{' '.join(map(str, argv))} exited {done.returncode}\n{done.stdout}\n{done.stderr}")
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
        lines = run(shutil.which("petra", path=str(scripts)), "check", design, cwd=where, code=code).splitlines()
        print("\n".join([f"\n$ petra check {design.relative_to(ROOT).as_posix()}", *lines[:8]]))
        wanted = [CHECKED if kernel else NOT_RUN, *([FROM_RULES] if kernel and design == LAP else [])]
        found += [f"{design.name}: no line of the report matches {pattern.pattern!r}"
                  for pattern in wanted if not any(pattern.match(line) for line in lines)]
        if not lines[0].endswith(f": {status}"):
            found.append(f"{design.name}: the report does not start with {status}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("file", type=Path, help="a wheel or an sdist")
    parser.add_argument("requirements", nargs="*", metavar="REQUIREMENT", help="a pin for pip, such as numpy==2.4.6")
    parser.add_argument("--platform", help="the platform tag the wheel must carry")
    parser.add_argument("--no-kernel", action="store_true", help="the package must hold no kernel, and say that none ran")
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
