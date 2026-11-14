# The attacker

A program that attacks the checker with no model. It writes designs, cards and decks from the grammar of [format.md](../../docs/format.md) and [deck.md](../../docs/deck.md), has three readers check each one, and keeps every difference as a small folder that reproduces it with one command. Plan step 3.10.

The three readers are the kernel (`petra-verify`), the Python reader (`petra/grid.py`) and the clean-room reading (`bench/twin/verify.mjs`).

## Run it

```
export PETRA_VERIFY=kernel/.lake/build/bin/petra-verify
python3.11 -m bench.attack.run --seed 1 --budget 3600 --jobs 7
```

No budget means until stopped. SIGINT, SIGTERM or a file named `STOP` in the output folder ends it, and the line is written either way. It needs Python 3.11, Node 22 and a built kernel, and uses no network.

One line is appended to [log.jsonl](log.jsonl) per run: seed, inputs made, the share that reached the comparison, the share that settled, differences, distinct differences, crashes, hangs, relations checked and broken, wall time.

- **Reached** means every reader was asked: the language read the pair and the deck loaded, or a refusal was compared with a refusal.
- **Settled** means the kernel gave PASS, FAIL or UNKNOWN and not ILL-FORMED.

Kept differences go to `OUT/found/KIND-SIG/`. Run one again with

```
python3.11 -m bench.attack.repro bench/attack/found/KIND-SIG
```

`python3.11 -m bench.attack.summary OUT` lists what a run kept, the worst first. [FINDINGS.md](FINDINGS.md) lists what the last run found in the readers as they stand, and [found](found) holds one folder for each kind it names.

## What it makes

| Recipe | Input |
|---|---|
| fresh | A design written from the types of a deck, with a card for its signed fields, loads and waivers. A hill climb moves its numbers toward a design that holds. |
| corpus | A pair of `corpus/cases/deck` or `examples/deck` changed in one to three places |
| hunt | A pair with one number moved to where the Python reader changes its answer: at it, under it, over it, found by halving |
| deck | A deck changed within the grammar, and a design for it |
| hints | The files of a checked design with wrong hints in `proofs.json` |
| json | The same files in another JSON spelling |
| forge | The files with a number, a name, a dimension or a key changed to a value the pages refuse or read in a stated way |
| syntax | One file with its JSON syntax changed |

The decks it starts from are `petra/decks/aisc360.json` and the decks `bench/kernel_grid.py` and `tests/test_grid.py` make up.

## What is compared

Every input goes to the kernel and the third reading, and every pair of texts also to the Python reader. They must give one verdict and the same cells, and the kernel and the third reading the same waivers and completions, the same rules of the same files in their findings, and the same reasons where the pages give a reason its words ([format.md](../../docs/format.md), The verdict). Any other reason is each reader's own, and so is the order of the loads a case leaves out: `held` in [readers.py](readers.py) says which is which. The three comparisons are kept apart: `kernel/twin`, `kernel/grid` and `grid`. A crash, a missing verdict or more than 90 seconds is kept as a crash or a hang.

The reasons of the grid and the kernel are compared for waived cells only, and there by the same rule: `petra check` words its other reasons itself.

## Metamorphic pairs

Each is a property that holds with no oracle. [meta.py](meta.py) gives, for each, the page it rests on, and the ones the pages do not promise are narrowed.

| Relation | Must hold |
|---|---|
| units | A number written in another unit is the same number: the Python reader writes the same files. Its factors are checked against the attacker's own table, [units.py](units.py). |
| rename | A part renamed: the same verdict and cells |
| reorder | Lines, givens, load blocks and waivers in another order: the same verdict and cells |
| load_up | A load raised never turns FAIL into PASS. Held only for a deck whose rules read each load as the whole left side of their inequality. |
| stronger | A plate thicker or stronger never turns PASS into FAIL. Held only for the deck that ships. |
| respell | A deck value written another way, or rules in another order: the same verdict and cells |
| json | A file in another JSON spelling: the same verdict and cells |
| hints | Any hint leaves a proved, refuted or not applicable cell as it was or open, and the cells the same |

## The sweep

`python3.11 -m bench.attack.sweep` leaves out each key of the kernel's files, one at a time, for the three examples that PASS, FAIL and are UNKNOWN, and asks the kernel and the third reading about each. The pages do not say a key may be missing, and the two readers read a missing key differently.

## Planted faults

`python3.11 -m bench.attack.plant FAULT DIR` writes a scratch copy of a reader with one fault and prints the command that runs the attacker against it, stopping at the first difference. The copy is never committed.

## Another machine

The machine needs the repository, a kernel built for it (`cd kernel && lake build`), Node 22 and Python 3.11, and a different `--seed`. Each machine writes its own folder and log line. The Oracle VM is not reachable from the Mac yet, so nothing has run there.
