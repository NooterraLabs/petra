# What the attacker found

One run of an hour on a Mac with 7 workers, seed 100, at `0420c07`, and the sweep of missing keys. The log line is the last of [log.jsonl](log.jsonl). Each folder named below is in [found](found), and `python3.11 -m bench.attack.repro bench/attack/found/NAME` runs it again and exits 1 while the difference is there. The readers are the kernel at `1e34098`, the Python reader and the clean-room reading, as they stand on `rework`. Nothing here is fixed: each goes to the checker's writer.

| Run | Result |
|---|---|
| Inputs made | 4,556, of which 4,458 reached the comparison (97.9 percent) and 3,849 settled (84.5 percent): PASS 217, FAIL 2,967, UNKNOWN 665, ILL-FORMED 609 |
| Differences | 707, of 36 distinct kinds: 632 of wording between the kernel and the clean-room reading, 13 of wording between the kernel and the grid, 56 in the findings of an ILL-FORMED file and 6 of verdict |
| Crashes and hangs | none, with a limit of 90 seconds for a reader |
| Relations | 906 checked, none broken |
| The sweep | 305 files with one key left out, 40 of which the kernel refuses and the clean-room reading takes |

## False passes

None between readers on a pair of texts the language wrote: in the hour, the 6 differences of verdict were all of files with a key changed (FAIL or UNKNOWN or ILL-FORMED against each other, never PASS). The one kind with a PASS in it came from the sweep of missing keys.

**1. The clean-room reading passes files that the kernel refuses (verdict).** It takes a key that is missing as empty. The kernel refuses the file. For the examples `lap_pass`, `lap_fail` and `lap_unknown`, 40 of the 305 single-key drops split the two:

- `card.json`: `cases`, `claims`, `environment`, `waivers`, and `reason` of a waiver. With `waivers` gone the clean-room reading says UNKNOWN or FAIL, and with the others PASS.
- `design.json`: `params`, `quantities`, and each of `dim`, `entity`, `field`, `line`, `role` and `type` of a quantity.
- `deck.json`: `constants`.

The reading in the kernel is the one to keep: format.md describes each file by its keys, and a PASS about a file that lacks a key the exporter always writes is a PASS about another file. The clean-room reading is wrong, by its own entry E1 in `bench/twin/AMBIGUITIES.md`, where it took the default. No file the exporter writes is affected, since it writes every one of these keys. The pages should say that a key may not be left out.

Reproduce: `bench/attack/found/verdict-40821e911b` (`params`), `verdict-725220d4d2` (`reason` of a waiver), `verdict-d9523be54f` (`quantities`), `verdict-a523cfad8c` (`constants`), `verdict-5d2d30fa90` (`cases`). All of them: `python3.11 -m bench.attack.sweep`. In the run, the forging recipe met it as `verdict-b6218ba805` (`params`, FAIL) and `verdict-32f334a53d` (`waivers`, UNKNOWN).

## Other differences of verdict

**2. A key twice in a file.** The kernel and the Python reader take the last value in `design.json`, `proofs.json`, `deck.json` and `rules.json`, and the clean-room reading refuses the file ("the key appears twice"). `card.json` is refused by both, but only because the design's hash of it no longer fits. Reproduce: `bench/attack/found/verdict-34eb3b1355` (kernel FAIL, clean-room ILL-FORMED, `proofs.json` with `format` twice).

The pages say nothing, so neither reader is wrong. The risk the tenth review named, one hash and two decks, needs a reader that keeps the first value, and none does. The pages should say one thing, and the other reader follow.

## Differences in the findings of an ILL-FORMED file

The two readers give the same verdict and different lists of findings. The pages list "the first 100 broken rules" and say nothing about what follows a shape finding.

**3. After a shape finding the readers go on differently.** The kernel goes on to the rules of Parts with the broken item left out, so a refused part gives a finding `parts.6` for each load of the card on it. The clean-room reading stops at the file's shape finding. In one case the clean-room reading goes on and the kernel stops (`design: null`). Reproduce: `findings-12c7dbcadc` (card number `0/5`: kernel `shape` and `parts.3`, clean-room `shape`), `findings-a9dff89c8f` (design number `1.5`: kernel adds `parts.5` and `parts.6`), `findings-25f2e9a8d2` (the reverse), `findings-0e9f66036c` (deck.json size floor `"1 "`: clean-room adds `types.8`), `findings-938ccc59bf`.

The kernel follows the page more nearly, since a broken item is "left out" and the rest is read. Nobody is wrong: the verdict is the same, and the pages should say how far the rules go after a shape finding.

**4. A given that a refused line leaves unread.** For a design with a refused number (Parts 3) the clean-room reading adds `parts.6` (a given that no part reads) where the kernel does not. Reproduce: `findings-1bc20184c4` (the corpus pair `d05_swapped_given`, one number moved). The page says a line reads the name its given writes, which favours the kernel, but whether a refused line reads is not said.

**5. A card with a key twice.** `findings-c06d8dc629`: the kernel says the design's hash of the card does not fit (`types.1`) and the clean-room reading says the card is not JSON. A consequence of 2.

## Differences of wording

Reasons of open and waived cells. The pages give the text of some (`open but for the waiver: `, `the range the rule holds in is not proved: `, the unstated field) and none of these. The kernel and the third reading are held to the same text where the pages give it, and these differ where they do not.

**6. A cell nothing reads.** Kernel and grid: `no rule of the deck reads cell.maker, so nothing checks it`. Clean-room: `no rule and no line of the grid reads it`, and for a load `no rule reads this load`. 584 of the inputs. Reproduce: `reason-2a8ca1ed97` (a field), `reason-e431d18a93` (a load). The pages give no text for it. The clean-room reading is the one that differs from the other two.

**7. The reason the hints left.** Kernel: `the partition splits in:x, which the tape does not read`, `the point is outside the range of input 0`, `leaf 0: root 0 is above zero`, `a split of input 1 is not strictly inside its range`. Clean-room: `no partition of proofs.json proves it and no point refutes it` for each. Reproduce: `reason-84d4e2a115`, `reason-28fec7b209`, `reason-e9e45ec3b3`. The page says only "the reason the hints left".

**8. The loads a case leaves out, in a waived cell.** The grid lists them in the order of the type's loads (`no push and no twist`) and the kernel and the clean-room reading in another (`no twist and no push`). Reproduce: `reason-501a6d7a63`. The page says "the first four" and not in what order. The grid is the odd one of the three.

## Documentation

**9. A hint can add or drop a cell.** format.md says a `proofs.json` "cannot add a cell, drop one, or change what a cell says". The cell of a range, `heat/seismic/where`, is there only when a hint proves the range, so a hint does add and drop it. The attacker's first property for hints said the cells stay, and the kernel broke it. The page is wrong in that sentence, or `/where` cells are not cells there. Reproduce: `sh bench/attack/found/doc-hints-and-where-cells/run.sh`, which prints 16 cells and then 15.

## Not found

- No difference in a verdict or in the cells between the kernel, the Python reader and the clean-room reading on a pair of texts the language wrote, in the 4,458 inputs that reached the comparison, 545 of them against a deck changed within the grammar.
- No refusal that one reader made and another did not, in the hour. An earlier run found one, and it was the difference the pages state: the kernel reads the names of `let` in any order and the grid in the order of the file (format.md, rules.json).
- No crash, hang or traceback in any reader, and no output the attacker could not read.
- No relation broken: units (the Python reader's files do not change when a number is written in another unit, and each value equals the attacker's own table), rename, reorder, a load raised (held for the shipped deck), a plate thicker or stronger, a deck value written another way, a file in another JSON spelling, and wrong hints that leave a proved cell proved.

## What became of each finding

The twelfth review ruled on each of the nine, after an hour of its own on the tree of phase 1 (seed 12, the log line of 2026-11-14T23:51 in [log.jsonl](log.jsonl)): 5,682 inputs, 5,568 of them at the comparison, 891 differences of 43 kinds, no difference of verdict or of cells between the kernel and the Python reader, no relation broken. That hour added two: the clean-room reading stopped with no verdict on a card whose name is no text, and it read `"tests": null` as a finding of shape where the kernel says Parts 8.

| Finding | Ruling |
|---|---|
| 1. A key left out | The clean-room reading is fixed. format.md has a section "Keys" that lists every key a file may leave out, and `tests/test_kernel_attacks12.py` holds the kernel to it. |
| 2. A key written twice | format.md says the last value is read, and the reading follows. Whether a repeated key should be refused is still open, in step 1.12 of the plan. |
| 3. After a shape finding | format.md says how far the rules go, under "After a broken rule", and the reading follows. |
| 4. A given that a refused line names | It counts as read. format.md says so. |
| 5. A card with a key twice | It follows from 2: the hash is of the bytes. |
| 6. The reason of a cell nothing reads | format.md gives the words, and the reading follows. |
| 7, 8. The reason the hints left, and the order of the loads a case leaves out | Each reader's own words. format.md says which reasons it holds, and [readers.py](readers.py) compares those (`held`). |
| 9. A hint adds or drops the cell of a range | The page was wrong, and is corrected. |
| The reading stops with no verdict | Fixed in the reading. |
| `"tests": null` | format.md says the two keys are held to no kind, and the reading follows. |

After the rulings a run of 15 minutes (seed 121, 4 workers) made 903 inputs, 891 of them at the comparison, and kept no difference of any kind. The sweep of missing keys gives the kernel and the clean-room reading the same answer on all 305 files.

## What the attacker is not yet

It does not run the kernel against another kernel, only against the two readings. Its designs for the decks other than the first are written from their fields and not from their rules, so the made-up decks of the benches get fewer passes (5 percent of inputs PASS overall). It does not change a deck's types or its grid beyond dropping a line, and it makes no byte-level changes to the JSON.
