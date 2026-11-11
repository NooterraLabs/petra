# petra-verify

The checker that decides a verdict. It reads four JSON files, and a fifth for a design checked against a deck of rules, and trusts none of them. [docs/format.md](../docs/format.md) describes the files, the rules and the verdict.

## Build

The build needs the Lean toolchain that `lean-toolchain` names, and nothing else. With [elan](https://github.com/leanprover/elan) installed, run this in `kernel/`:

```bash
lake build
```

The binary is `.lake/build/bin/petra-verify`, or `petra-verify.exe` on Windows.

## Run

```bash
python -m petra.export examples/circuit_pass.petra --out out
kernel/.lake/build/bin/petra-verify --card out/card.json --design out/design.json --deck out/deck.json --proofs out/proofs.json
```

The second command prints the verdict as JSON and exits 0 for PASS, 1 for FAIL, 2 for UNKNOWN and 3 for ILL-FORMED.

For a design whose parts are of a deck of rules, such as `examples/deck/lap_pass.petra`, the export also writes `rules.json`, the deck's own file, and the kernel takes it as `--rules out/rules.json`. It then works out every cell from the deck itself.

The verdict says which of the two it did, in `cells_from`, and prints the hash of each file it read. A PASS is about a deck of rules only when `hashes.rules` is the hash of the deck the reader trusts, and about the asker's card only when `hashes.card` is the asker's. [docs/format.md](../docs/format.md) says how to check both, under "Reading a verdict" and "The asker's card".

## With petra check

`petra check` runs the kernel on its own report when it finds one. It looks for the file the environment variable `PETRA_VERIFY` names, then for the kernel inside the installed package, then for `.lake/build/bin/petra-verify` here. Its `kernel` line says how many of the proofs behind the status the kernel checked, and `python corpus/run.py --kernel BINARY` gives the kernel's own verdict on every corpus design.

## In a wheel

A wheel from PyPI carries the kernel as `petra/bin/petra-verify`, so `pip install petra-lang` needs no Lean toolchain. The sdist carries no kernel. Petra installed from the sdist says on the `kernel` line of each report that no kernel ran.

The build backend, `_build/petra_build.py`, puts the kernel in a wheel when the tree holds one. After `lake build` here, these two commands, run in the repository's root, build a wheel for your platform and try it in a fresh environment:

```bash
pip wheel --no-deps -w dist .
python scripts/wheel_check.py dist/*.whl
```

The backend reads the wheel's platform tag from the binary, so the tag asks for what the binary needs. The `wheels` workflow builds one wheel on a runner of each platform and holds it to the tag in this table:

| Platform | Tag | The kernel needs |
|---|---|---|
| Linux x86-64 | `manylinux_2_17_x86_64` | glibc 2.17 or later |
| Linux aarch64 | `manylinux_2_17_aarch64` | glibc 2.17 or later |
| macOS arm64 | `macosx_15_0_arm64` | macOS 15 or later |
| macOS x86-64 | `macosx_15_0_x86_64` | macOS 15 or later |
| Windows x86-64 | `win_amd64` | Windows 10 version 1903 or later |

On any other machine pip takes the sdist, and no kernel runs. The Linux and Windows rows were measured on kernels built for them. The macOS rows are read from the files of the Lean toolchain for macOS, and no macOS wheel had been built when this was written.

Lean's runtime, GMP, libuv and, outside macOS, the C++ library are linked into the binary. What it loads when it starts is part of the system:

- **Linux.** Lake links against the glibc that the Lean toolchain carries, not the build machine's. The kernel loads `libc`, `libm`, `libdl`, `libpthread` and `librt`, and asks for no symbol newer than `GLIBC_2.17`. `auditwheel show` names the same tag.
- **macOS.** The kernel loads `libSystem` and the system's `libc++`. The linker writes into the binary the macOS version it is told, whatever the linked objects say. Lean 4.30.0-rc2 compiles its own libraries for macOS 11.0, but the `libgmp.a` it ships is compiled for macOS 15.0, and its `libuv.a` for 15.0 on arm64 and 14.0 on x86-64. So `scripts/macos_target.py` finds the newest version any object in the toolchain's static libraries was compiled for, and the workflow links the kernel for that one.
- **Windows.** The kernel imports only DLLs that Windows carries. One of them, `icu.dll`, came with Windows 10 version 1903. A wheel's tag names no version of Windows, so on Windows `petra check` starts the kernel once before it relies on it. Where the kernel cannot start, `petra check` warns and the report says that no kernel ran.

A new Lean toolchain can change what the kernel needs. The workflow then fails on the row whose tag no longer matches, until that row and this table are changed.

A wheel is a little over 30 MB, and the kernel in it is 100 to 120 MB unpacked. Most of that is Lean's own library, which comes in with `Lean.Data.Json`. Importing only the JSON parser and printer does not make it smaller.

## Layout

| File | Holds |
|---|---|
| `Petra/Num.lean` | Exact rationals, intervals, and `sqrt`, `ln`, `exp` and pi rounded outward |
| `Petra/Tape.lean` | The interval rule: a partition proves a tape, a point refutes one, and each step pays for its work |
| `Petra/Sha256.lean` | The hash of a file's bytes |
| `Petra/Files.lean` | The files as structures |
| `Petra/Quantity.lean` | Dimensions, the unit table, and the text of a quantity |
| `Petra/Deck.lean` | A deck of rules, and a rule as a tape for one part |
| `Petra/Grid.lean` | The parts of a design, and the cells the grid asks of them |
| `Petra/Check.lean` | The rules in order, and the verdict |
| `Main.lean` | The command line and the printed JSON |

## What is proved

The interval rule is proved, for `Petra/Num.lean` and `Petra/Tape.lean` as they stand: a tape that `Tape.proved` accepts has every root at most zero at every point of its box, and a point that `Tape.refuted` accepts has its root above zero. Both hold whatever work the proof is given: a proof that runs out of work is not accepted. The proofs are in `../proofs`, a second package that depends on Mathlib, and [docs/proved.md](../docs/proved.md) lists them. Nothing in this folder depends on that package.

For the logic to read them, no definition in those two files is a `partial def` or runs a `while`: each loop is a recursion that Lean checks to end.

The other files are not proved: reading the files, the deck of rules, the cells and the verdict. The arithmetic gives the same interval ends as `petra/kernel/interval.py` on every root tried. The Windows build and a Linux build on aarch64 print the same verdict on 115 exported corpus designs. `python bench/kernel_grid.py` compares the cells the kernel makes from a deck of rules with the ones `petra/grid.py` makes, on generated designs and on damaged decks.
