# What is proved about the kernel

`proofs/` is a second Lake package. It depends on Mathlib and on `kernel/` by path. Every theorem in it is about the kernel's own definitions in `kernel/Petra/Num.lean` and `kernel/Petra/Tape.lean`, not about copies of them. Nothing in `kernel/` depends on it, and the kernel still builds with the toolchain alone.

## The result

A tape states that every root is at most zero for all values of the inputs in their ranges ([format.md](format.md)).

- **A tape with no `sqrt`, `pi`, `ln` or `exp` node.** If `Tape.proved` succeeds, then at every point of the box every root has a value, and the value is at most zero. If `Tape.refuted` succeeds, the point lies in the box and the root it names has a value above zero there. Nothing is assumed. These are `Tape.proved_sound_exact` and `Tape.refuted_sound_exact`.
- **Any tape.** The same two statements hold, given three statements about three loops of the kernel that the logic cannot read. These are `Tape.proved_sound` and `Tape.refuted_sound`. The section on what is assumed lists the three.

A box is one range for each input. A point of the box is one real number for each input, inside its range.

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

### The rounded functions

In `proofs/PetraProofs/Rounded.lean`. Each theorem but the first takes one assumption, named in the last column.

| Theorem | Says | Assumes |
|---|---|---|
| `grid_sound` | If every enclosure `enc p` holds `x`, the two grid points that `grid enc` returns have `x` between them. | Nothing |
| `iSqrt_sound` | If `iSqrt a` returns `r`, then `x` is at least zero and `r` holds the square root of `x`. | `IsqrtSpec` |
| `piIv_sound` | If `piIv` returns `r`, then `r` holds pi. | `OddSeriesSpec` |
| `iLn_sound` | If `iLn a` returns `r`, then `x` is above zero, `r` holds ln `x`, and the caches stay valid. | `OddSeriesSpec` |
| `iExp_sound` | If `iExp a` returns `r`, then `r` holds exp `x`, and the caches stay valid. | `ExpAtSpec` |
| `iLn_valid`, `iExp_valid` | `iLn` and `iExp` keep the caches valid on any interval, also one that holds no number. | The same |
| `Caches.valid_empty` | The empty caches, which the kernel starts from, are valid. | Nothing |

A cache is valid when every pair it stores for a number holds that number's logarithm, or its exponential.

### One step of a tape

In `proofs/PetraProofs/Step.lean`.

| Theorem | Says |
|---|---|
| `Node.enclose_sound` | Take a point of the box. If the enclosure of every node that this node reads holds that node's value at the point, and `Node.enclose` returns `r`, then this node has a value at the point and `r` holds it. For a `sqrt`, `pi`, `ln` or `exp` node it assumes that node's statement. |
| `Node.enclose_valid` | A step keeps the caches valid. |
| `Node.enclose_exact` | The step of a node other than `sqrt`, `pi`, `ln` and `exp` does not read the caches and does not change them. |

### The pick node

In `proofs/PetraProofs/Pick.lean`.

| Theorem | Says |
|---|---|
| `pick_sound` | Take a point of the box. If the enclosure of every node the pick reads that has not failed holds that node's value at the point, and `pick` returns `r`, then the pick has a value at the point and `r` holds it. Nothing is assumed. |
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
| `Tape.proved_sound_exact` | For a tape with no `sqrt`, `pi`, `ln` or `exp` node, from any caches: if `Tape.proved` succeeds, every root has a value at most zero at every point of the box. |
| `Tape.refuted_sound_exact` | For such a tape: if `Tape.refuted` succeeds, the point lies in the box and the root it names has a value above zero there. |
| `Tape.proved_sound` | For any tape, from valid caches and given the statement of each rounded node the tape has: the same as `Tape.proved_sound_exact`, and the caches stay valid. |
| `Tape.refuted_sound` | For any tape, likewise, the same as `Tape.refuted_sound_exact`. |

## What is assumed

Three functions of the kernel cannot be reasoned about in this toolchain. `isqrt` and `oddSeries` run a `while` loop. `expAt` is a `partial def` that also runs one. Lean compiles `while` to `Lean.Loop.forIn`, which is itself a `partial def`, and the logic sees a `partial def` as a constant with no equation. So no theorem can say what any of the three returns.

`proofs/PetraProofs/Trust.lean` states what each is written to return:

| Statement | Says | Needed by |
|---|---|---|
| `IsqrtSpec` | `isqrt n` is the floor of the square root of `n`. | `sqrt` |
| `OddSeriesSpec` | For `x` between -1/3 and 1/3, `oddSeries x 1 p` holds atanh `x` and `oddSeries x (-1) p` holds arctan `x`. | `pi`, `ln` |
| `ExpAtSpec` | `expAt x p` holds exp `x`. | `exp` |

None of the three is proved of the kernel's function. Each is a hypothesis of the theorems that need it. None is an axiom, and no proof here uses `sorry`.

### What closes the gap

`proofs/PetraProofs/Provable/` holds a version of each of the three functions with no `while` and no `partial`. Each definition uses core Lean and the kernel's own `scale`, `qi`, `qd` and `bitlen` only, so it can move into `kernel/Petra/Num.lean` as written.

| Theorem | Says |
|---|---|
| `Provable.isqrt_spec` | `Provable.isqrt` meets the statement of `IsqrtSpec`. |
| `Provable.oddSeries_spec` | `Provable.oddSeries` meets the statement of `OddSeriesSpec`. |
| `Provable.expAt_spec` | `Provable.expAt` meets the statement of `ExpAtSpec`. |
| `Provable.expGo_stops` | The count of rounds given to the exp loop never runs out before the loop's own test ends it. |
| `Tape.proved_sound_of_swap`, `Tape.refuted_sound_of_swap` | If the kernel's `isqrt`, `oddSeries` and `expAt` are these three versions, the theorems for any tape hold with nothing assumed. |

Each version is the kernel's computation written as a recursion: the same start, the same steps, the same test to stop and the same tail. Run side by side, the versions returned what the kernel's functions returned on 5,601 integers for `isqrt`, 140 inputs for `oddSeries` and 56 for `expAt`. `lake env lean Compare.lean` in `proofs/` runs the comparison again. That they agree on every input cannot be proved, for the reason above.

When the kernel defines the three functions this way, each equation that `Tape.proved_sound_of_swap` asks for holds by `rfl`, and every row of the tables above stands with nothing assumed.

## What is not proved

- That the kernel's `isqrt`, `oddSeries` and `expAt` return what `IsqrtSpec`, `OddSeriesSpec` and `ExpAtSpec` say. The obstacle is the `while` and the `partial def`, not the mathematics: the versions in `Provable/` are proved.
- Anything in `Petra/Check.lean`, `Petra/Files.lean`, `Petra/Sha256.lean` and `Main.lean`: reading the files, the test on the labels and ranges of a tape's inputs, the hash, and the verdict.
- That the kernel and the Python kernel give the same ends.
- That a tape's formula is the one a standard states. [format.md](format.md) lists this among what the kernel does not check.

## What the proofs found in the kernel

No case was found where an operation returns an interval that fails to hold the true value. The proofs go through for the kernel as it is, apart from the three loops. These points came up on the way. None is a fault.

- `Node.enclose` reads an input as `box[k]!`. For a `k` past the end of the box this is `[0, 0]` and not a failure. `Tape.wellFormed` refuses such a tape first, and `Tape.proved` and `Tape.refuted` keep one range for each input, so the case does not arise. `Node.enclose_sound` states the condition.
- `Tape.eval` gives a node that no root reads the enclosure `[0, 0]` and no failure. This is right only because `Tape.needed` marks every node a marked node reads, which in turn needs a node to read only earlier nodes. `Tape.needed_spec` proves it from `Tape.wellFormed`.
- `iLn` calls `lnPoint` on the upper end without a test that it is above zero. For an interval with its ends the wrong way round, the cache gains an entry under a key that is not positive. No number lies in such an interval, and nothing reads the entry as a logarithm.
- In `compared`, the removal of duplicate pairs is not needed for the result to be right. In `order`, the branch `none => .eq` is never reached for a condition of the same pick.
- `grid` tests `hi - lo ≤ 1`. The test makes the result tight. It plays no part in whether the result holds the value.

## The axioms

`lake build PetraProofs.Axioms` prints the axioms each main theorem rests on. `propext`, `Classical.choice` and `Quot.sound` are Lean's standard three. No other axiom appears, and `sorryAx` does not appear.

```
'Petra.Iv.add_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.neg_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.mul_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.abs_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.min_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.max_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Iv.div_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.powInt_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.fits_ok' depends on axioms: [propext]
'Petra.grid_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.iSqrt_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.piIv_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.iLn_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.iExp_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Node.enclose_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.pick_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.eval_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Partition.leaves_cover' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.proved_sound_exact' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.refuted_sound_exact' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.proved_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.refuted_sound' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Provable.isqrt_spec' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Provable.oddSeries_spec' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Provable.expAt_spec' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.proved_sound_of_swap' depends on axioms: [propext, Classical.choice, Quot.sound]
'Petra.Tape.refuted_sound_of_swap' depends on axioms: [propext, Classical.choice, Quot.sound]
```

## Rebuild

The build needs [elan](https://github.com/leanprover/elan) and about 8 GB of disk, nearly all of it Mathlib's prebuilt files.

```bash
cd proofs
lake exe cache get
lake build PetraProofs PetraProofs.Axioms
```

The first command fetches Mathlib's prebuilt files, so that nothing of Mathlib compiles from source. The second builds the two kernel files the proofs read and the fifteen proof files, and prints the axioms. It takes about 50 seconds on four ARM cores.

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
| `PetraProofs/Trust.lean` | The three assumed statements, and when a cache is valid |
| `PetraProofs/Arith.lean` | The exact operations |
| `PetraProofs/Rounded.lean` | `grid`, `iSqrt`, `piIv`, `iLn`, `iExp` and the caches |
| `PetraProofs/Step.lean` | One step of a tape |
| `PetraProofs/Pick.lean` | The pick node |
| `PetraProofs/Eval.lean` | `wellFormed`, `needed` and `eval` |
| `PetraProofs/Rule.lean` | Partitions, `proved` and `refuted` |
| `PetraProofs/Provable/` | `isqrt`, `oddSeries` and `expAt` with no `while`, and their proofs |
| `PetraProofs/Closing.lean` | The theorems for the kernel with those three swapped in |
| `PetraProofs/Axioms.lean` | The `#print axioms` lines |
