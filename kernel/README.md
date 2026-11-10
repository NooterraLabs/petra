# petra-verify

The checker that decides a verdict. It reads four JSON files and trusts none of them. [docs/format.md](../docs/format.md) describes the files, the rules and the verdict.

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

## With petra check

`petra check` runs the kernel on its own report when it finds one. It looks for the file the environment variable `PETRA_VERIFY` names, then for `.lake/build/bin/petra-verify` here. Its `kernel` line says how many of the proofs behind the status the kernel checked, and `python corpus/run.py --kernel BINARY` gives the kernel's own verdict on every corpus design.

## Layout

| File | Holds |
|---|---|
| `Petra/Num.lean` | Exact rationals, intervals, and `sqrt`, `ln`, `exp` and pi rounded outward |
| `Petra/Tape.lean` | The interval rule: a partition proves a tape, a point refutes one |
| `Petra/Sha256.lean` | The hash of a file's bytes |
| `Petra/Files.lean` | The four files as structures |
| `Petra/Check.lean` | The rules in order, and the verdict |
| `Main.lean` | The command line and the printed JSON |

Nothing here is proved yet. The arithmetic gives the same interval ends as `petra/kernel/interval.py` on every root tried. The Windows build and a Linux build on aarch64 print the same verdict on 115 exported corpus designs.
