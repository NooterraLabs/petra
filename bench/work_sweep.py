"""What a unit of the kernel's work costs in time, for each step and each length of number.

    python bench/work_sweep.py [--kernel PATH] [--bits N,N,...] [--seconds S] [--only STEP,...]

A proof pays for its steps in units of work, and a verdict has 20,000,000,000 of them
(docs/format.md, "Work"). The count bounds the time only if a unit costs about the same time
whatever the step and however long its numbers. This measures that on the machine it runs on.

For each step and each length it writes a tape whose roots are many copies of the step over
enclosures whose four numbers each have that many bits, with no pattern in them: a fraction
in lowest terms keeps a greatest common divisor away, and those cost the most. It has the
kernel walk the tape on enough leaves to take `--seconds` of processor time, and divides the
processor nanoseconds by the `work` the verdict prints. Beside them it runs the yardstick: the
chain of 4,000 small products of tests/test_kernel_limits.py, whose numbers fit a machine word.

Prints one line for each step with the nanoseconds a unit at each length, and exits 1 when
the most of them is over three times the yardstick's. The time is the processor's and not
the clock's, less what the kernel takes to start and to read the files, so a busy machine
moves the numbers less than it moves the clock, and it moves the yardstick with them.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.setrecursionlimit(100_000)
sys.set_int_max_str_digits(0)

from petra import verify  # noqa: E402
from tests.test_kernel_attacks2 import measured  # noqa: E402
from tests.test_kernel_limits import old_path  # noqa: E402

BITS = (64, 250, 1000, 4000, 16000, 64000)
LIMIT = 3.0
"""How many times the yardstick's nanoseconds a unit the most of the sweep may be."""
CHUNK = 12_000
"""A number of a file is at most 4,000 characters, so a longer one is put together on the tape from pieces of this many bits."""
HELD = 64_000_000
"""The bits of the copies a tape may keep at once: the kernel holds 128 MB of enclosures, an
enclosure of `b`-bit numbers is four of them, and a power is up to eight times as long."""


def num(x: Fraction) -> str:
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def halves(lo: int, hi: int):
    """A partition of input 0 over [lo, hi] into leaves of length 1."""
    if hi - lo == 1:
        return "leaf"
    mid = (lo + hi) // 2
    return {"input": 0, "at": str(mid), "below": halves(lo, mid), "above": halves(mid, hi)}


class Tape:
    def __init__(self, seed: int) -> None:
        self.rnd = random.Random(seed)
        self.nodes: list[list] = [["s", 0]]

    def add(self, *node) -> int:
        self.nodes.append(list(node))
        return len(self.nodes) - 1

    def odd(self, bits: int) -> int:
        return self.rnd.getrandbits(bits) | (1 << (bits - 1)) | 1

    def whole(self, n: int) -> int:
        """The node of a whole number, put together from pieces when it is long."""
        if n.bit_length() <= CHUNK:
            return self.add("c", str(n))
        high = self.whole(n >> CHUNK)
        shifted = self.add("mul", [high, self.add("c", str(1 << CHUNK))])
        return self.add("add", [shifted, self.add("c", str(n & ((1 << CHUNK) - 1)))])

    def dense(self, bits: int) -> int:
        """The node of a fraction between a half and two whose numerator and denominator have `bits` bits."""
        x = Fraction(self.odd(bits), self.odd(bits))
        if x.numerator.bit_length() + x.denominator.bit_length() <= CHUNK:
            return self.add("c", num(x))
        return self.add("div", self.whole(x.numerator), self.whole(x.denominator))

    def wide(self, bits: int) -> int:
        """An enclosure with two different ends of `bits` bits: a fraction plus the input, which a leaf holds to a range of length 1."""
        return self.add("add", [self.dense(bits), 0])


def step(kind: str, t: Tape, bits: int):
    """The operands of the step, made once, and a function that adds one copy of the step over them."""
    if kind in ("add", "mul", "min", "max"):
        a, b = t.wide(bits), t.wide(bits)
        return [a, b], lambda: t.add(kind, [a, b])
    if kind == "div":
        a, b = t.wide(bits), t.wide(bits)
        return [a, b], lambda: t.add("div", a, b)
    if kind in ("neg", "abs", "sqrt", "ln"):
        a = t.wide(bits)
        return [a], lambda: t.add(kind, a)
    if kind == "exp":
        a = t.add("add", [t.dense(bits), t.add("mul", [0, t.add("c", "1/1048576")])])
        return [a], lambda: t.add("exp", a)
    if kind.startswith("pow"):
        a = t.wide(bits)
        return [a], lambda: t.add("pow", a, int(kind[3:]))
    if kind == "pick":
        a, b = t.wide(bits), t.wide(bits)
        return [a, b], lambda: t.add("pick", [[["le", a, b], a], [None, b]])
    if kind == "c":
        x = Fraction(t.odd(min(bits, 6000)), t.odd(min(bits, 6000)))
        return [], lambda: t.add("c", num(x))
    if kind == "pi":
        return [], lambda: t.add("pi")
    raise SystemExit(f"{kind} is not a step")


STEPS = ("c", "pi", "neg", "abs", "add", "mul", "div", "min", "max", "pick", "sqrt", "pow2", "pow3", "pow8", "ln", "exp")


def bundle(kind: str, bits: int, copies: int, leaves: int) -> dict[str, str]:
    """A tape of `copies` of the step. Each copy is under a root, and so is each operand:
    with no copy the tape still makes the operands, and that run is what is taken off."""
    t = Tape(bits * 131 + len(kind))
    operands, make = step(kind, t, bits)
    roots = [t.add("neg", t.add("abs", node)) for node in [t.add("c", "0"), *operands]]
    for _ in range(copies):
        roots.append(t.add("neg", t.add("abs", make())))
    tape = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": str(leaves)}], "nodes": t.nodes, "roots": roots}
    return old_path([{"subject": "s", "mechanism": "m", "entry": "e", "state": "proved", "tape": tape, "partition": halves(0, leaves)}], [])


def yardstick(leaves: int) -> dict[str, str]:
    nodes = [["c", "3/8"], ["c", "8/3"], ["s", 0]]
    for k in range(4000):
        nodes.append(["mul", [len(nodes) - 1, k % 2]])
    nodes += [["c", "-1000000"], ["add", [len(nodes) - 1, len(nodes)]]]
    tape = {"inputs": [{"label": "dsg:x", "lo": "0", "hi": str(leaves)}], "nodes": nodes, "roots": [len(nodes) - 1]}
    return old_path([{"subject": "s", "mechanism": "m", "entry": "e", "state": "proved", "tape": tape, "partition": halves(0, leaves)}], [])


def rate(make, seconds: float, start: float, bare: bool = False, most: int = 4096) -> tuple[float, int, float]:
    """The nanoseconds a unit of the copies in the bundles `make(copies, leaves)`, their work
    and their processor seconds, from the run that took at least `seconds`. The same tape
    with no copy is run on the same leaves and taken off, so what is left is the step's own
    and not the making of its operands. So first enough copies, `most` at most, that their
    work is no less than the operands': a cheap step on long numbers would be lost in the
    making of them otherwise. Then more leaves, and more copies when the proof stops on its
    first leaf, as it does when a step has no value. With `bare` the tape has no operands,
    and what the kernel takes to start is taken off."""
    copies, leaves = 16, 1
    if not bare:
        none = measured(make(0, 1), timeout=900)[0]["work"]
        while copies < most and measured(make(copies, 1), timeout=900)[0]["work"] < 2 * none:
            copies = min(most, copies * 4)
    while True:
        said, cpu, _ = measured(make(copies, leaves), timeout=900)
        took, work = max(cpu - start, 0.0), said["work"]
        stopped = said["cells"][0]["state"] != "proved"
        grow = 4 if took < seconds / 8 else 2
        if took < seconds and work < 19_000_000_000:
            if stopped and copies < most:
                copies = min(most, copies * grow)
                continue
            if not stopped and leaves < 4096:
                leaves *= grow
                continue
        if not bare:
            less, cpu0, _ = measured(make(0, leaves), timeout=900)
            took, work = max(cpu - cpu0, 0.0), work - less["work"]
        return (took * 1e9 / work if work > 0 else float("nan")), work, took


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--kernel", help="the kernel to measure; default the one `petra check` would run")
    parser.add_argument("--bits", default=",".join(map(str, BITS)), help="the lengths of the numbers, in bits")
    parser.add_argument("--seconds", type=float, default=0.6, help="the processor seconds each measurement takes at least")
    parser.add_argument("--only", help="the steps to measure, of " + ", ".join(STEPS))
    args = parser.parse_args()
    if args.kernel:
        os.environ["PETRA_VERIFY"] = args.kernel
    if verify.binary() is None:
        print("no petra-verify is built here and --kernel names none", file=sys.stderr)
        return 2
    bits = [int(b) for b in args.bits.split(",")]
    kinds = args.only.split(",") if args.only else list(STEPS)
    start = min(measured(old_path([], []))[1] for _ in range(3))
    print(f"the kernel starts and reads an empty design in {start:.2f} processor seconds, which is taken off each run")
    yard, work, took = rate(lambda copies, leaves: yardstick(leaves), max(args.seconds, 1.0), start, bare=True)
    print(f"yardstick: {yard:.2f} ns a unit ({work:,} units in {took:.2f} s)")
    print(f"{'step':6}" + "".join(f"{b:>9,}" for b in bits) + "   most")
    worst, where = 0.0, ""
    for kind in kinds:
        cells = []
        for b in bits:
            if kind == "pi" and b != bits[0]:
                cells.append(None)
                continue
            found, _, _ = rate(lambda copies, leaves, b=b: bundle(kind, b, copies, leaves), args.seconds, start, most=min(4096, HELD // b))
            cells.append(found)
            if found > worst:
                worst, where = found, f"{kind} at {b:,} bits"
        most = max(c for c in cells if c is not None)
        print(f"{kind:6}" + "".join(f"{'':>9}" if c is None else f"{c:9.2f}" for c in cells) + f"{most:7.2f}", flush=True)
    again, _, _ = rate(lambda copies, leaves: yardstick(leaves), max(args.seconds, 1.0), start, bare=True)
    yard = min(yard, again)
    print(f"yardstick again: {again:.2f} ns a unit")
    print(f"the most is {worst:.2f} ns a unit, {where}: {worst / yard:.1f} times the yardstick's {yard:.2f}, and the limit is {LIMIT:g} times")
    return 0 if worst <= LIMIT * yard else 1


if __name__ == "__main__":
    sys.exit(main())
