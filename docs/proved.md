# What is proved about the kernel

`proofs/` is a second Lake package. It depends on Mathlib and on `kernel/` by path. Every theorem in it is about the kernel's own definitions in `kernel/Petra/Num.lean` and `kernel/Petra/Tape.lean`, not about copies of them. Nothing in `kernel/` depends on it, and the kernel still builds with the toolchain alone.

## The result

A tape states that every root is at most zero for all values of the inputs in their ranges ([format.md](format.md)).

- If `Tape.proved` succeeds from valid caches, then at every point of the box every root has a value, and the value is at most zero. This is `Tape.proved_sound`.
- If `Tape.refuted` succeeds from valid caches, the point lies in the box and the root it names has a value above zero there. This is `Tape.refuted_sound`.

Both hold for any tape, with `sqrt`, `pi`, `ln` and `exp` nodes or without. Neither takes a hypothesis about the kernel, and no proof uses `sorry` or an axiom beyond Lean's standard three.

A box is one range for each input. A point of the box is one real number for each input, inside its range. A cache is valid when every pair it stores for a number holds that number's logarithm, or its exponential. The kernel starts from the empty caches, which are valid, and each theorem also says that the caches stay valid.

## What a tape means

The theorems need the real value of a node at a point. `proofs/PetraProofs/Meaning.lean` defines it, in 85 lines, and it is the one file to read against the section "Tapes" of [format.md](format.md). A theorem is only as good as this definition.

`Tape.value t ρ i` is the value of node `i` when input `k` has the value `ρ k`. It is `some x` or `none`. It is `none` when the node:

- divides by zero, takes the square root of a negative number, or takes the logarithm of a number that is not positive
- raises zero to a negative power
- is a `min` or a `max` of no nodes
- names an input the tape does not have
- reads a node that has no value, or a node that is not before it
- is a `pick` where a condition compares a node that has no value, or where no case holds, or where the node of the first case that holds has no value

So "the root has a value" in a theorem says that none of these happens on the way to the root. A case of a `pick` with no condition holds wherever it sits in the list, as it does in the kernel.

## The theorems

"`a` holds `x`" means that the real `x` lies between the ends of the interval `a`, with the rational ends read as reals. In Lean it is `a.Holds x`.

### The exact operations

In `proofs/PetraProofs/Arith.lean`. In each, `a` holds `x` and `b` holds `y`.

| Theorem | Says |
|---|---|
| `Iv.add_sound` | `a.add b` holds `x + y`. |
| `Iv.neg_sound` | `a.neg` holds `-x`. |
| `Iv.sub_sound` | `a.sub b` holds `x - y`. |
| `Iv.mul_sound` | `a.mul b` holds `x * y`. |
| `Iv.abs_sound` | `a.abs` holds the absolute value of `x`. |
| `Iv.min_sound`, `Iv.max_sound` | `a.min b` holds the lesser of `x` and `y`, and `a.max b` the greater. |
| `Iv.div_sound` | If `a.div b` returns `r`, then `y` is not zero and `r` holds `x / y`. `Iv.div` fails when `b` holds zero. |
| `powInt_sound` | If `powInt a n` returns `r`, then `n` is at least zero and `r` holds `x ^ n`. `powInt` fails for a negative `n`. |
| `fits_ok` | `fits` returns its interval unchanged, or fails. So the bit budget never moves an enclosure. |

### The three loops

In `proofs/PetraProofs/Loops/`. The kernel has three loops under its rounded functions. Each theorem is about the kernel's own function.

| Theorem | Says |
|---|---|
| `Loops.isqrt_spec` | `isqrt n` is the floor of the square root of `n`. |
| `Loops.oddSeries_spec` | For `x` between -1/3 and 1/3, `oddSeries x 1 p` holds atanh `x` and `oddSeries x (-1) p` holds arctan `x`. |
| `Loops.expAt_spec` | `expAt x p` holds exp `x`. |
| `Loops.expGo_stops` | The count of rounds given to the loop of `expAt` never runs out before the loop's own test ends it. |

`proofs/PetraProofs/Spec.lean` holds the three statements, each written for any function.

### The rounded functions

In `proofs/PetraProofs/Rounded.lean`.

| Theorem | Says |
|---|---|
| `grid_sound` | If every enclosure `enc p` holds `x`, the two grid points that `grid enc` returns have `x` between them. |
| `iSqrt_sound` | If `iSqrt a` returns `r`, then `x` is at least zero and `r` holds the square root of `x`. |
| `piIv_sound` | If `piIv` returns `r`, then `r` holds pi. |
| `iLn_sound` | If `iLn a` returns `r`, then `x` is above zero, `r` holds ln `x`, and the caches stay valid. |
| `iExp_sound` | If `iExp a` returns `r`, then `r` holds exp `x`, and the caches stay valid. |
| `iLn_valid`, `iExp_valid` | `iLn` and `iExp` keep the caches valid on any interval, also one that holds no number. |
| `Caches.valid_empty` | The empty caches, which the kernel starts from, are valid. |

### One step of a tape

In `proofs/PetraProofs/Step.lean`.

| Theorem | Says |
|---|---|
| `Node.enclose_sound` | Take a point of the box. If the enclosure of every node that this node reads holds that node's value at the point, and `Node.enclose` returns `r` from valid caches, then this node has a value at the point and `r` holds it. |
| `Node.enclose_valid` | A step keeps the caches valid. |
| `Node.enclose_exact` | The step of a node other than `sqrt`, `pi`, `ln` and `exp` does not read the caches and does not change them. |

### The pick node

In `proofs/PetraProofs/Pick.lean`.

| Theorem | Says |
|---|---|
| `pick_sound` | Take a point of the box. If the enclosure of every node the pick reads that has not failed holds that node's value at the point, and `pick` returns `r`, then the pick has a value at the point and `r` holds it. |
| `pick_ok` | A `pick` that returns found no failure among the nodes it compares, tried every way of ordering them, found in each way a first case that holds, and found no failure among those cases. |
| `way_eq_choice` | Every choice of one allowed order for each pair is one of the ways the kernel tries. |
| `holds_eq_truth` | When the orders are the true ones at a point, `Cond.holds` gives a condition its truth value at that point. |

### The walk and the rule

In `proofs/PetraProofs/Eval.lean` and `proofs/PetraProofs/Rule.lean`.

| Theorem | Says |
|---|---|
| `Tape.wellFormed_ok` | A tape that `Tape.wellFormed` accepts has nodes that read only earlier nodes, input nodes that name an input, and roots that name a node. |
| `Tape.needed_spec` | `Tape.needed` marks every root, and with a marked node every node it reads. |
| `Tape.eval_sound` | After `Tape.eval`, the enclosure of every marked node that did not fail holds that node's value at every point of the box. |
| `Partition.leaves_cover` | Every point of the box lies in some leaf of the partition. |
| `Tape.proved_sound` | For any tape, from valid caches: if `Tape.proved` succeeds, every root has a value at most zero at every point of the box, and the caches stay valid. |
| `Tape.refuted_sound` | For any tape, from valid caches: if `Tape.refuted` succeeds, the point lies in the box and the root it names has a value above zero there, and the caches stay valid. |
| `Tape.proved_sound_exact`, `Tape.refuted_sound_exact` | The same two for a tape with no `sqrt`, `pi`, `ln` or `exp` node, from any caches. Such a tape reads no cache. |

## How the loops came to be proved

Until 2026-11-11 the kernel's `isqrt` and `oddSeries` ran a `while`, and `expAt` was a `partial def` that ran one. Lean compiles `while` to `Lean.Loop.forIn`, which is itself a `partial def`, and the logic sees a `partial def` as a constant with no equation. So no theorem could say what any of the three returned, and every theorem about `sqrt`, `pi`, `ln` and `exp` took a statement about its loop as a hypothesis.

The three are now written as recursions that Lean checks to end. Each is the same computation: the same start, the same steps, the same test to stop and the same tail.

| Function | Its loop | Why it ends |
|---|---|---|
| `isqrt` | `isqrtGo`, Newton's iteration from above | The value goes down at every step. |
| `oddSeries` | `oddGo`, the terms of the series | The power of 3 it tests grows at every round. |
| `expAt` | `expGo`, the terms of the series, and `sqGo`, the squarings | Each counts down: `expGo` from `q + 1` rounds, which `Loops.expGo_stops` proves it never uses up, and `sqGo` from the number of squarings. |

The change moved no result that was looked at:

- The old and the new functions returned the same value on 21,801 integers for `isqrt`, 1,232 inputs for `oddSeries` and 500 for `expAt`, run side by side.
- The kernel built before the change and the kernel built after it printed the same bytes, and exited with the same code, on every bundle the corpus exports: 244 runs, of which 26 read a deck of rules.
- Those 244 runs took 21.5 s before and 20.4 s after. Nine tapes made of `sqrt`, `ln`, `exp` and `pi` nodes alone took 1.75 s before and 1.83 s after, with the same bytes printed.

That the old and the new agree on every input cannot be proved, for the reason above, and does not need to be: the theorems are about the functions the kernel has now.

## What is not proved

- Anything in `Petra/Check.lean`, `Petra/Files.lean`, `Petra/Deck.lean`, `Petra/Grid.lean`, `Petra/Quantity.lean`, `Petra/Sha256.lean` and `Main.lean`: reading the files, the test on the labels and ranges of a tape's inputs, writing a tape from a rule of a deck, the list of cells, the hash, and the verdict. The theorems start at a tape, a partition and a point.
- That the program computes what the definitions say. The theorems are about the definitions as the logic reads them. Lean's compiler and its runtime, with their arithmetic on large numbers, arrays and hash maps, turn the definitions into the program, and they are trusted. `proofs/check_axioms.py` holds the two kernel files to no attribute that would give a definition other code to run.
- That the kernel and the Python kernel give the same ends.
- That a tape's formula is the one a standard states. [format.md](format.md) lists this among what the kernel does not check.

## What the proofs found in the kernel

No case was found where an operation returns an interval that fails to hold the true value. The proofs go through for the kernel as it is. These points came up on the way. None is a fault.

- `Node.enclose` reads an input as `box[k]!`. For a `k` past the end of the box this is `[0, 0]` and not a failure. `Tape.wellFormed` refuses such a tape first, and `Tape.proved` and `Tape.refuted` keep one range for each input, so the case does not arise. `Node.enclose_sound` states the condition.
- `Tape.eval` gives a node that no root reads the enclosure `[0, 0]` and no failure. This is right only because `Tape.needed` marks every node a marked node reads, which in turn needs a node to read only earlier nodes. `Tape.needed_spec` proves it from `Tape.wellFormed`.
- `iLn` calls `lnPoint` on the upper end without a test that it is above zero. For an interval with its ends the wrong way round, the cache gains an entry under a key that is not positive. No number lies in such an interval, and nothing reads the entry as a logarithm.
- In `compared`, the removal of duplicate pairs is not needed for the result to be right. In `order`, the branch `none => .eq` is never reached for a condition of the same pick.
- `grid` tests `hi - lo ≤ 1`. The test makes the result tight. It plays no part in whether the result holds the value.

## The axioms

`python proofs/check_axioms.py` builds the proofs and prints the axioms each main theorem rests on. `propext`, `Classical.choice` and `Quot.sound` are Lean's standard three. No other axiom appears, and `sorryAx` does not appear. The script fails when either does, when a source file holds `sorry`, and when the lines below are not the ones it prints.

```
'Petra.Iv.add_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.neg_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.sub_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.mul_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.abs_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.min_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.max_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.div_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.powInt_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.fits_ok' depends on axioms: [propext]
'Petra.Loops.isqrt_spec' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Loops.oddSeries_spec' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Loops.expAt_spec' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Loops.expGo_stops' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.grid_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.iSqrt_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.piIv_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.iLn_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.iExp_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.iLn_valid' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.iExp_valid' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Caches.valid_empty' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Node.enclose_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Node.enclose_valid' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.pick_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.wellFormed_ok' depends on axioms: [propext, Quot.sound]
'Petra.Tape.needed_spec' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.eval_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Partition.leaves_cover' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.proved_sound_exact' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.refuted_sound_exact' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.proved_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.refuted_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
```

## Rebuild

The build needs [elan](https://github.com/leanprover/elan), Python and about 8 GB of disk, nearly all of it Mathlib's prebuilt files.

```bash
cd proofs
lake exe cache get
python check_axioms.py
```

The first command fetches Mathlib's prebuilt files, so that nothing of Mathlib compiles from source. The second builds the two kernel files the proofs read and the proof files, checks the axioms, and prints them. The build takes about 50 seconds on four ARM cores. The job `proofs` of `.github/workflows/checks.yml` runs the same two commands on every push.

| Pinned | To |
|---|---|
| Toolchain | `leanprover/lean4:v4.30.0-rc2`, the one `kernel/lean-toolchain` names |
| Mathlib | The tag `v4.30.0-rc2`, commit `5450b53e5ddc75d46418fabb605edbf36bd0beb6`, in `proofs/lake-manifest.json` |

On Linux for aarch64, the build of this toolchain that the build machine has ships `bin/leantar` as an x86-64 program, so `lake exe cache get` downloads the files and cannot unpack them. The same version of `leantar`, 0.1.19, built for aarch64 from the [leangz releases](https://github.com/digama0/leangz/releases), unpacks them. The cache tool finds `leantar` by asking `lean --print-prefix`, so a `lean` first on the `PATH` that answers that one question with another folder, and passes every other call on, points it at the working copy. On x86-64 the two commands above are enough.

## Layout

| File | Holds |
|---|---|
| `PetraProofs/Basic.lean` | When an interval holds a real, and how the kernel's monads and loops unfold |
| `PetraProofs/Meaning.lean` | The real value of a node at a point |
| `PetraProofs/Spec.lean` | What each of the three loops returns, as a statement, and when a cache is valid |
| `PetraProofs/Arith.lean` | The exact operations |
| `PetraProofs/Loops/` | The kernel's `isqrt`, `oddSeries` and `expAt` meet their statements |
| `PetraProofs/Rounded.lean` | `grid`, `iSqrt`, `piIv`, `iLn`, `iExp` and the caches |
| `PetraProofs/Step.lean` | One step of a tape |
| `PetraProofs/Pick.lean` | The pick node |
| `PetraProofs/Eval.lean` | `wellFormed`, `needed` and `eval` |
| `PetraProofs/Rule.lean` | Partitions, `proved` and `refuted` |
| `PetraProofs/Axioms.lean` | The `#print axioms` lines |
| `check_axioms.py` | The build, the check of the axioms, and the check of the sources |
