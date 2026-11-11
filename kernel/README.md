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

## With petra check

`petra check` runs the kernel on its own report when it finds one. It looks for the file the environment variable `PETRA_VERIFY` names, then for `.lake/build/bin/petra-verify` here. Its `kernel` line says how many of the proofs behind the status the kernel checked, and `python corpus/run.py --kernel BINARY` gives the kernel's own verdict on every corpus design.

## Layout

| File | Holds |
|---|---|
| `Petra/Num.lean` | Exact rationals, intervals, and `sqrt`, `ln`, `exp` and pi rounded outward |
| `Petra/Tape.lean` | The interval rule: a partition proves a tape, a point refutes one |
| `Petra/Sha256.lean` | The hash of a file's bytes |
| `Petra/Files.lean` | The files as structures |
| `Petra/Quantity.lean` | Dimensions, the unit table, and the text of a quantity |
| `Petra/Deck.lean` | A deck of rules, and a rule as a tape for one part |
| `Petra/Grid.lean` | The parts of a design, and the cells the grid asks of them |
| `Petra/Check.lean` | The rules in order, and the verdict |
| `Main.lean` | The command line and the printed JSON |

Nothing here is proved yet. The arithmetic gives the same interval ends as `petra/kernel/interval.py` on every root tried. The Windows build and a Linux build on aarch64 print the same verdict on 115 exported corpus designs. `python bench/kernel_grid.py` compares the cells the kernel makes from a deck of rules with the ones `petra/grid.py` makes, on generated designs and on damaged decks.
