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

`petra check` runs the kernel on its own report when it finds one. It looks for the file the environment variable `PETRA_VERIFY` names, then for `.lake/build/bin/petra-verify` here. Its `kernel` line says how many of the proofs behind the status the kernel checked, and `python corpus/run.py --kernel BINARY` gives the kernel's own verdict on every corpus design.

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
