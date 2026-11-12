/-
The tape of docs/format.md: a statement that every root is at most zero for all values of
the inputs in their ranges. A partition proves one and a point refutes one, as `prove` and
`refute` do in petra/kernel/rules/r4_enclosure.py.

A proof pays for what it does, in units of work, from what the verdict has left. It pays
for its tape on every leaf before it starts, and each step then pays for the numbers it
handles. A step that cannot pay is not taken, and its node has no value. So the time one
verdict takes is bounded by `MAX_WORK`, whatever the files hold. The kernel walks the
leaves one at a time and gives up each enclosure after the last node that reads it, and it
holds at most `MAX_HELD` words of them at once.
-/
import Petra.Num

namespace Petra

/-- The deepest a partition may split, as in r4_enclosure.py. It bounds the walk and not
soundness: any finite split tree covers its box. -/
def MAX_DEPTH : Nat := 64

/-- The largest magnitude a `pow` exponent may have. -/
def MAX_EXPONENT : Nat := 64

/-- The most bits a numerator or a denominator may have, and the largest magnitude `exp`
and `cos` take. A tape can square a value at every node, so without this a short tape would not end. -/
def MAX_BITS : Nat := 65536

/-- The most ways a pick may have to order the nodes its conditions compare on one box. -/
def MAX_CHOICES : Nat := 4096

/-- The deepest a condition of a pick may nest, where an order alone is 1 deep. -/
def MAX_COND_DEPTH : Nat := 16

/-- The most orders the conditions of one pick may hold between them. -/
def MAX_ORDERS : Nat := 1024

/-- The most work the kernel spends on the proofs of one verdict. A unit is about 0.4
nanoseconds on the desktop the costs below were fitted on, so this is about 8 seconds. -/
def MAX_WORK : Nat := 20000000000

/-- The most 64-bit words of enclosures the kernel holds at once while it walks one leaf:
128 MB. -/
def MAX_HELD : Nat := 16777216

/-- What the kernel says of a proof it does not try because the work left does not pay for
its tape on its leaves. -/
def SPENT : String :=
  s!"this proof would take the kernel past the {MAX_WORK} units of work it spends on one verdict, so it is not tried"

/-- What the kernel says of a step it does not take because the work left does not pay for it. -/
def COSTLY : String :=
  s!"this step would take the kernel past the {MAX_WORK} units of work it spends on one verdict, so it is not taken"

/-- The condition of a case of a pick: an order between two nodes, or conditions joined. -/
inductive Cond where
  | le (i j : Nat) | lt (i j : Nat)
  | and (cs : Array Cond) | or (cs : Array Cond) | not (c : Cond)
  deriving Inhabited, BEq

inductive Node where
  | c (x : Rat) | s (k : Nat) | pi
  | add (a : Array Nat) | mul (a : Array Nat) | min (a : Array Nat) | max (a : Array Nat)
  | neg (i : Nat) | abs (i : Nat) | sqrt (i : Nat) | ln (i : Nat) | exp (i : Nat) | cos (i : Nat)
  | div (i j : Nat) | pow (i : Nat) (n : Int)
  /-- The value of the first case whose condition holds. A case is its condition and the
  node that is then the pick's value. A case with no condition holds otherwise. -/
  | pick (cases : Array (Option Cond × Nat))
  deriving Inhabited, BEq

structure TapeInput where
  label : String
  range : Iv

structure Tape where
  inputs : Array TapeInput
  nodes : Array Node
  roots : Array Nat

inductive Partition where
  | leaf
  | split (input : Nat) (cut : Rat) (below above : Partition)

/-- The two nodes an order compares, the earlier one first. -/
def pair (i j : Nat) : Nat × Nat := if i ≤ j then (i, j) else (j, i)

/-- The pair of every order in a condition. -/
def Cond.pairs : Cond → Array (Nat × Nat)
  | .le i j | .lt i j => #[pair i j]
  | .and cs | .or cs => cs.foldl (fun out c => out ++ c.pairs) #[]
  | .not c => c.pairs

/-- The distinct pairs of nodes that the conditions of a pick compare. -/
def compared (cases : Array (Option Cond × Nat)) : Array (Nat × Nat) :=
  let pairs := cases.flatMap fun (cond, _) => (cond.map Cond.pairs).getD #[]
  pairs.foldl (fun out p => if out.contains p then out else out.push p) #[]

/-- How many orders a condition holds. -/
def Cond.orders : Cond → Nat
  | .le _ _ | .lt _ _ => 1
  | .and cs | .or cs => cs.foldl (fun n c => n + c.orders) 0
  | .not c => c.orders

/-- How many orders the conditions of a pick hold between them. -/
def orders (cases : Array (Option Cond × Nat)) : Nat :=
  cases.foldl (fun n (cond, _) => n + (cond.map Cond.orders).getD 0) 0

/-- The condition with each node it compares renamed. -/
def Cond.map (f : Nat → Nat) : Cond → Cond
  | .le i j => .le (f i) (f j)
  | .lt i j => .lt (f i) (f j)
  | .and cs => .and (cs.map (·.map f))
  | .or cs => .or (cs.map (·.map f))
  | .not c => .not (c.map f)

/-- The node with each node it reads renamed. An input and a constant read none. -/
def Node.map (f : Nat → Nat) : Node → Node
  | .c x => .c x
  | .s k => .s k
  | .pi => .pi
  | .add a => .add (a.map f)
  | .mul a => .mul (a.map f)
  | .min a => .min (a.map f)
  | .max a => .max (a.map f)
  | .neg i => .neg (f i)
  | .abs i => .abs (f i)
  | .sqrt i => .sqrt (f i)
  | .ln i => .ln (f i)
  | .exp i => .exp (f i)
  | .cos i => .cos (f i)
  | .div i j => .div (f i) (f j)
  | .pow i n => .pow (f i) n
  | .pick cases => .pick (cases.map fun (cond, value) => (cond.map (·.map f), f value))

def Node.reads : Node → Array Nat
  | .c _ | .s _ | .pi => #[]
  | .add a | .mul a | .min a | .max a => a
  | .neg i | .abs i | .sqrt i | .ln i | .exp i | .cos i | .pow i _ => #[i]
  | .div i j => #[i, j]
  | .pick cases => (compared cases).flatMap (fun (a, b) => #[a, b]) ++ cases.map (·.2)

/-- A tape has a root, a node reads only nodes before it, an input node names an input, and
a root names a node. -/
def Tape.wellFormed (t : Tape) : Except String Unit := do
  if t.roots.isEmpty then throw "the tape has no root"
  for (node, i) in t.nodes.zipIdx do
    unless node.reads.all (· < i) do throw s!"node {i} reads a node that is not before it"
    if let .s k := node then
      unless k < t.inputs.size do throw s!"node {i} reads input {k}, and the tape has {t.inputs.size} inputs"
  unless t.roots.all (· < t.nodes.size) do throw "a root is not a node of the tape"

/-- The nodes that `roots` read, directly or through other nodes. A node reads only earlier
nodes, so one pass from the last node finds them. The kernel evaluates these and no others,
as `enclose` in petra/kernel/evaluate.py evaluates only what an expression holds. -/
def Tape.needed (t : Tape) (roots : Array Nat) : Array Bool := Id.run do
  let mark (need : Array Bool) (ids : Array Nat) := ids.foldl (fun need i => need.setIfInBounds i true) need
  let mut need := mark (Array.replicate t.nodes.size false) roots
  for k in [0:t.nodes.size] do
    let i := t.nodes.size - 1 - k
    if need[i]! then need := mark need t.nodes[i]!.reads
  return need

def fits (x : Iv) : Except String Iv :=
  if [x.lo, x.hi].all (fun q => bitlen q.num.natAbs ≤ MAX_BITS && bitlen q.den ≤ MAX_BITS) then .ok x
  else .error s!"a value has more than {MAX_BITS} bits"

/-- One step of the interval rule: the enclosure of a node from the enclosures `v` of the
nodes before it. `sqrt`, `ln`, `exp`, `cos` and pi round to the grid, `ln`, `exp` and `cos`
from an enclosure with `extra` bits more than the grid has. A pick has its own step, `pick`, which
also reads which nodes failed. -/
def Node.enclose (box v : Array Iv) (extra : Nat) : Node → M Iv
  | .c x => pure (Iv.pt x)
  | .s k => pure box[k]!
  | .pi => liftM (m := Except String) piIv
  | .add a => liftM (m := Except String) (a.foldlM (fun acc i => fits (acc.add v[i]!)) (Iv.pt 0))
  | .mul a => liftM (m := Except String) (a.foldlM (fun acc i => fits (acc.mul v[i]!)) (Iv.pt 1))
  | .min a => match a.toList with
    | [] => throw "min of no nodes"
    | i :: rest => pure (rest.foldl (fun acc k => acc.min v[k]!) v[i]!)
  | .max a => match a.toList with
    | [] => throw "max of no nodes"
    | i :: rest => pure (rest.foldl (fun acc k => acc.max v[k]!) v[i]!)
  | .neg i => pure v[i]!.neg
  | .abs i => pure v[i]!.abs
  | .sqrt i => liftM (m := Except String) (iSqrt v[i]!)
  | .ln i => iLn v[i]! extra
  | .exp i =>
    if v[i]!.lo < -(MAX_BITS : Rat) || v[i]!.hi > (MAX_BITS : Rat) then throw s!"exp of a value beyond {MAX_BITS}"
    else iExp v[i]! extra
  | .cos i =>
    if v[i]!.lo < -(MAX_BITS : Rat) || v[i]!.hi > (MAX_BITS : Rat) then throw s!"cos of a value beyond {MAX_BITS}"
    else iCos v[i]! extra
  | .div i j => liftM (m := Except String) (v[i]!.div v[j]!)
  | .pow i n => liftM (m := Except String) (powInt v[i]! n)
  | .pick _ => throw "a pick is not enclosed by this step"

-- What a step costs.
--
-- Each formula below is an estimate of the time its step takes, in units of work, from the
-- bits of the numbers the step reads. A unit is a little under half a nanosecond on the
-- desktop the formulas were fitted on, whatever the step and however long its numbers:
-- bench/work_sweep.py measures that, and docs/format.md, "Work", holds its table. No theorem
-- reads the formulas: a wrong estimate moves the time a verdict takes and nothing else.
--
-- Three things shape them. A number under 32 bits is kept in a machine word and a longer
-- one on the heap, and a step on heap numbers takes several times as long whatever their
-- length, so each formula has a floor that rises between a few bits and 32. A fraction is
-- kept in lowest terms, so a sum and a product each take greatest common divisors, which
-- cost more than the products do. And the library multiplies and divides long numbers
-- faster than the schoolbook, so the cost of two `n`-bit numbers grows about as `n` to the
-- power one and a half, and not as its square.

/-- The 64-bit words of a number: of its numerator and its denominator together. -/
def ratWords (q : Rat) : Nat := (bitlen q.num.natAbs + bitlen q.den) / 64 + 1

/-- The 64-bit words of an enclosure: of both its ends. The walk counts what it holds in
these (`MAX_HELD`). -/
def Iv.words (x : Iv) : Nat := ratWords x.lo + ratWords x.hi

/-- The bits of the longer of a number's numerator and denominator. -/
def ratBits (q : Rat) : Nat := Nat.max (bitlen q.num.natAbs) (bitlen q.den)

/-- The bits of the longest of the four numbers of an enclosure. A step is charged as if
all four were that long. -/
def Iv.bits (x : Iv) : Nat := Nat.max (ratBits x.lo) (ratBits x.hi)

/-- How far `n` is from `lo` towards `hi`: nothing at `lo` and under, and `hi - lo` from `hi` on. -/
def ramp (n lo hi : Nat) : Nat := Nat.min n hi - Nat.min n lo

/-- `n` to the power one and a half. -/
def pow32 (n : Nat) : Nat := n * isqrt n

/-- One term of a sum, when the longest number of the sum so far has `p` bits and the
longest of the term `w`: a greatest common divisor of the two denominators, and three
products. -/
def addWork (p w : Nat) : Nat :=
  let floor := 4000 + 875 * ramp (Nat.max p w) 16 32
  if p + w < 64 then floor else floor + (p + w) * 11 / 10 + pow32 (isqrt (p * w))

/-- One factor of a product: four products of fractions, each with two greatest common
divisors, and then the four are compared with each other, which multiplies them across. -/
def mulWork (p w : Nat) : Nat :=
  let floor := 12000 + 1500 * ramp (Nat.max p w) 8 32
  if p + w < 64 then floor else floor + pow32 (p + w) * 26 / 100 + pow32 (isqrt (p * w)) * 27 / 10

/-- A quotient: a product by the two ends of the divisor turned over. -/
def divWork (p w : Nat) : Nat := mulWork p w + (if w < 32 then 6000 else 14000 + w / 2)

/-- One comparison of two enclosures, as `min`, `max` and a pick make: two comparisons of
fractions, each of which multiplies across. -/
def orderWork (p w : Nat) : Nat :=
  let floor := 550 + 1625 * ramp (Nat.max p w) 12 20
  if p + w < 64 then floor else floor + pow32 (p + w) / 30

/-- A step that copies its number or hands it on: a negation, an absolute value, an input
and a constant. `small` is its cost on numbers under 32 bits, and `heap` on longer ones. -/
def copyWork (small heap per n : Nat) : Nat := if n < 32 then small else heap + n / per

/-- A least or a greatest of the nodes `a`: the first is handed on, and each after it is
compared with the one kept so far, which is as long as the longest before it. -/
def leastWork (v : Array Iv) (a : Array Nat) : Nat :=
  match a.toList with
  | [] => 0
  | first :: rest =>
    (rest.foldl (fun (cost, p) i =>
      let w := v[i]!.bits
      (cost + orderWork p w, Nat.max p w)) (copyWork 800 3000 16 v[first]!.bits, v[first]!.bits)).1

/-- The square root of an enclosure: Newton's iteration on the whole part of each end times
`GRID` squared, which has the bits the end's numerator has more than its denominator and
192 more, and costs their square. -/
def sqrtWork (x : Iv) : Nat :=
  let whole (q : Rat) : Nat := bitlen q.num.natAbs + 256 - bitlen q.den
  62000 + 4 * x.bits + (whole x.lo * whole x.lo + whole x.hi * whole x.hi) / 900

/-- The logarithm of one end `x` from an enclosure of `PREC + extra` bits. The series is of
`(m - 1) / (m + 1)` for `x` scaled to `m` between a half and two, a number as long as
the longer of the numerator and the denominator of `x`, whatever `x` is near: reducing it
takes greatest common divisors, and each term of the series, of which there are as many as
bits, multiplies that many bits by it. The kernel keeps ln 2 for the first enclosure and
sums it again for the others. -/
def lnWork (extra : Nat) (x : Rat) : Nat :=
  let p := PREC + extra
  let n := ratBits x
  (if extra == 32 then (if n < 32 then 5000 else 7000) else 17000) * p + p * n * 4 / 5 + pow32 n * 3 / 5

/-- The exponential of one end `x` from an enclosure of `PREC + extra` bits. `expPos` works
with `q` bits, which grow with the size of `x`, sums about `2 q / log2 q` terms of that
length, and then squares. -/
def expWork (extra : Nat) (x : Rat) : Nat :=
  let c := (if x < 0 then -x else x).ceil.toNat
  let s := bitlen c + 1
  let q := PREC + extra + 2 * s + 2 * c
  let wide := q / 64 + 1
  let terms := Nat.max 32 (2 * q / bitlen q)
  let w := ratWords x
  (terms * (10000 + 54 * wide + 20 * w + wide * w / 3) + (s + 16) * wide * wide / 4) * 17 / 10

/-- The cosine of one end `x` from an enclosure of `PREC + extra` bits. `cosAt` works with
`q` bits, which grow with the size of `x`. It squares the end, which takes greatest common
divisors of its `n` bits, sums about `q / (log2 q + 1)` terms, each a product of `q` bits
by the square and a quotient by it, and then doubles the angle `s` times, each a square of
`q` bits. -/
def cosWork (extra : Nat) (x : Rat) : Nat :=
  let c := (if x < 0 then -x else x).ceil.toNat
  let s := bitlen c + 1
  let q := PREC + extra + 2 * s + 8
  let wide := q / 64 + 1
  let terms := q / (bitlen q + 1)
  let n := ratBits x
  let w := n / 64 + 1
  110000 + 1000 * w + pow32 n + terms * (25000 + 400 * w + 20 * wide * w) + s * (11000 + 30 * wide * wide)

/-- Placing the two ends of an enclosure among the multiples of pi: for each end a quotient
by an end of pi, its whole part, and a comparison with that many times an end of pi. -/
def placeWork (x : Iv) : Nat := 15000 + 3 * x.bits

/-- A whole power `k` of an enclosure whose longest number has `n` bits: `k` products for
each end, the `j`-th by a number `j` times as long. Each takes greatest common divisors
of `n` bits, and from the third on a division of the longer number by the shorter. -/
def powWork (k n : Nat) : Nat :=
  let each := if n * k < 32 then 4700 else if n < 32 then 14500 else 31000
  k * (each + n / 2) + (k - 1) * (pow32 n * 31 / 20) + ((k - 1) * (k - 2) / 2) * (n * n / 300 + 4 * n)

/-- An `ln`, an `exp` or a `cos` of an end the caches hold: a look at them. A cache is kept in the
order of its ends, so a look compares the end with at most 25 of the 1,024 a cache holds,
and with 10 or 11 as a rule, and each comparison reads no more than the end has bits. -/
def cachedWork (x : Rat) : Nat := 1500 + ratBits x / 8

/-- The work of the step `Node.enclose` for a node other than a pick, a sum and a product,
which pay as they go (`pickPriced`, `folded`). An `ln`, an `exp` or a `cos` of an end the
caches hold costs a look at them, and the step may copy a cache's table of `MAX_CACHED`
entries. A `cos` also pays for placing its enclosure among the multiples of pi, and of two
ends of one size it computes one. -/
def Node.work (box v : Array Iv) (extra : Nat) (caches : Caches) : Node → Nat
  | .c x => copyWork 800 8000 8 (ratBits x)
  | .s k => copyWork 700 4000 12 box[k]!.bits
  | .pi => 2800
  | .add _ | .mul _ => 500
  | .min a | .max a => 500 + leastWork v a
  | .neg i | .abs i => copyWork 1100 7000 3 v[i]!.bits
  | .sqrt i => sqrtWork v[i]!
  | .ln i =>
    let x := v[i]!
    let one (x : Rat) : Nat :=
      if x == 1 || caches.ln.contains (x.num, x.den) then cachedWork x else lnWork extra x
    25000 + one x.lo + (if x.lo == x.hi then cachedWork x.hi else one x.hi)
  | .exp i =>
    let x := v[i]!
    if x.lo < -(MAX_BITS : Rat) || x.hi > (MAX_BITS : Rat) then 3000 else
    let one (x : Rat) : Nat :=
      if x == 0 || caches.exp.contains (x.num, x.den) then cachedWork x else expWork extra x
    25000 + one x.lo + (if x.lo == x.hi then cachedWork x.hi else one x.hi)
  | .cos i =>
    let x := v[i]!
    if x.lo < -(MAX_BITS : Rat) || x.hi > (MAX_BITS : Rat) then 3000 else
    let one (x : Rat) : Nat :=
      let y := if x < 0 then -x else x
      if x == 0 || caches.cos.contains (y.num, y.den) then cachedWork x else cosWork extra x
    25000 + placeWork x + one x.lo + (if x.lo == x.hi || x.lo == -x.hi then cachedWork x.hi else one x.hi)
  | .div i j => divWork v[i]!.bits v[j]!.bits
  | .pow i n => 2800 + v[i]!.bits / 8 + powWork n.natAbs v[i]!.bits
  | .pick _ => 500

/-- How many distinct pairs the conditions of a pick compare: the size of `compared`, counted
through a table kept in order and so without the comparisons `compared` makes. -/
def pairsOf (cases : Array (Option Cond × Nat)) : Nat :=
  (cases.foldl (fun seen (cond, _) => ((cond.map Cond.pairs).getD #[]).foldl (·.insert ·) seen)
    ({} : Std.TreeSet (Nat × Nat))).size

/-- What a tape costs to read once, whatever its numbers: each node and each node it reads.
A pick finds the distinct pairs among its orders by comparing each order with the pairs
found before it, so it reads its orders times its pairs. -/
def Node.size : Node → Nat
  | .c _ | .s _ | .pi => 200
  | .add a | .mul a | .min a | .max a => 200 + 40 * a.size
  | .neg _ | .abs _ | .sqrt _ | .ln _ | .exp _ | .cos _ | .pow _ _ => 240
  | .div _ _ => 280
  | .pick cases => 200 + 40 * cases.size + 20 * orders cases * (pairsOf cases + 1)

def Tape.size (t : Tape) : Nat := t.nodes.foldl (fun n node => n + node.size) 0

/-- What one split of a partition costs beyond its tape: the cut is compared with both ends
of a range, and each is a number of the files, at most `MAX_NUMBER_CHARS` long. -/
def SPLIT : Nat := 20000

/-- What a proof pays before its first step, for a tape of this size with this many inputs
on this many leaves: for reading the tape three times, to check it and to mark what the
roots read and where each node is last read, and once more for each leaf, with the split
that made the leaf and a copy of the box. -/
def feeOf (size inputs leaves : Nat) : Nat := size * (3 + leaves) + leaves * (SPLIT + 8 * inputs)

/-- What a proof of the tape pays before its first step. Finding the size reads the tape, so
a caller that asks for the fee of one tape many times keeps the size and asks `feeOf`. -/
def Tape.fee (t : Tape) (leaves : Nat) : Nat := feeOf t.size t.inputs.size leaves

/-- The leaves of a partition. -/
def Partition.count : Partition → Nat
  | .leaf => 1
  | .split _ _ below above => below.count + above.count

/-- Why a node has no enclosure on a box: the node where the evaluation failed, and what
failed there. A node that reads a failed node has the same failure, so a reason names the
node where the failure began. -/
structure Failure where
  node : Nat
  why : String

def Failure.text (f : Failure) : String := s!"node {f.node}: {f.why}"

/-- The failure that began earliest in the tape among those of the nodes `ids`, or none when
every one of them has an enclosure. -/
def earliest (bad : Array (Option Failure)) (ids : Array Nat) : Option Failure :=
  ids.foldl (fun found i => match found, bad[i]! with
    | some f, some g => if g.node < f.node then some g else some f
    | none, g => g
    | f, none => f) none

/-- The orders of the first node of a pair against the second that their enclosures leave
possible: below, equal or above. At every point of the box the two values lie in their
enclosures, so their order there is one of these. A node against itself is equal. -/
def outcomes (v : Array Iv) (p : Nat × Nat) : Array Ordering :=
  let x := v[p.1]!
  let y := v[p.2]!
  if p.1 == p.2 then #[Ordering.eq] else
    (if x.lo < y.hi then #[Ordering.lt] else #[])
      ++ (if x.lo ≤ y.hi && y.lo ≤ x.hi then #[Ordering.eq] else #[])
      ++ (if x.hi > y.lo then #[Ordering.gt] else #[])

/-- Way `n` of taking one outcome for each pair: the digits of `n`, where a pair with `k`
outcomes is a digit to the base `k`. The numbers below the product of the bases give every
way once. -/
def way (options : Array (Array Ordering)) (n : Nat) : Array Ordering :=
  (options.foldl (fun (taken, n) os => (taken.push os[n % os.size]!, n / os.size)) (#[], n)).1

/-- The order of node `i` against node `j` when `taken` holds one outcome for each of
`pairs`. Every order a condition asks for is of a pair in `pairs`: `compared` collects them
from the same conditions. -/
def order (pairs : Array (Nat × Nat)) (taken : Array Ordering) (i j : Nat) : Ordering :=
  match pairs.idxOf? (pair i j) with
  | some k => if i ≤ j then taken[k]! else taken[k]!.swap
  | none => .eq

/-- Whether a condition is true when `rel i j` is the order of node `i` against node `j`. -/
def Cond.holds (rel : Nat → Nat → Ordering) : Cond → Bool
  | .le i j => rel i j != .gt
  | .lt i j => rel i j == .lt
  | .and cs => cs.foldl (fun so c => so && c.holds rel) true
  | .or cs => cs.foldl (fun so c => so || c.holds rel) false
  | .not c => !c.holds rel

/-- The enclosure of pick `self` over a box: the hull of the values of the cases that can be
the first to hold there.

The kernel does not know the order of two compared nodes at each point of the box. So it
takes every order their enclosures leave possible, and every way of taking one for each
pair. In one way every order is true or false, so every condition is, and one case is the
first to hold. At a point of the box the true order of each pair is one that the enclosures
leave possible, so the case that is first there is among the cases found, and its value
there lies in the enclosure of its node. So the hull of those enclosures contains the pick's
value at every point. Taking the pairs as independent adds ways that no point has. A way
adds a case to the hull or fails the pick, and it never drops the true case.

A pick fails when a node it compares has failed, when a case it found has, when some way
leaves no case that holds, and when there are more than `MAX_CHOICES` ways. A case it did
not find may have failed: no point of the box takes its value. -/
def pick (v : Array Iv) (bad : Array (Option Failure)) (self : Nat) (cases : Array (Option Cond × Nat)) :
    Except Failure Iv := do
  let pairs := compared cases
  if let some f := earliest bad (pairs.flatMap fun (a, b) => #[a, b]) then throw f
  let options := pairs.map (outcomes v)
  let ways := options.foldl (fun n os => if n > MAX_CHOICES then n else n * os.size) 1
  if ways > MAX_CHOICES then
    throw ⟨self, s!"a pick with more than {MAX_CHOICES} ways to order what it compares"⟩
  let mut found : Array Nat := #[]
  for n in [0:ways] do
    let rel := order pairs (way options n)
    match cases.find? (fun (cond, _) => cond.all (·.holds rel)) with
    | some (_, value) => unless found.contains value do found := found.push value
    | none => throw ⟨self, "no case of the pick holds somewhere in the box"⟩
  if let some f := earliest bad found then throw f
  match found.toList with
  | [] => throw ⟨self, "no case of the pick holds somewhere in the box"⟩
  | first :: rest => return rest.foldl (fun hull k => ⟨rmin hull.lo v[k]!.lo, rmax hull.hi v[k]!.hi⟩) v[first]!

/-- The work of a pick's step: the orders its enclosures leave possible for each pair, then
every way of taking one for each pair, in which each order of each condition is looked up
among the pairs, and the hull of the cases found, of which there is at most one for each
way. None when the work left does not pay for looking at the pairs. -/
def pickWork (v : Array Iv) (cases : Array (Option Cond × Nat)) (work : Nat) : Option Nat :=
  let pairs := compared cases
  let look := pairs.foldl (fun n p => n + 2 * orderWork v[p.1]!.bits v[p.2]!.bits) 0
  if work < look then none else
    let ways := (pairs.map (outcomes v)).foldl (fun n os => if n > MAX_CHOICES then n else n * os.size) 1
    let each := 200 + 20 * pairs.size + 30 * cases.size + orders cases * (150 + 6 * pairs.size)
    let long := cases.foldl (fun n (_, k) => Nat.max n v[k]!.bits) 1
    let hull := Nat.min ways cases.size * orderWork long long
    some (look + (if ways > MAX_CHOICES then 0 else ways * each + hull))

/-- A pick's step with its price: the step when the work left pays for it, and then what is
left. -/
def pickPriced (v : Array Iv) (bad : Array (Option Failure)) (self : Nat) (cases : Array (Option Cond × Nat))
    (work : Nat) : Except Failure Iv × Nat :=
  match pickWork v cases work with
  | none => (.error ⟨self, COSTLY⟩, work)
  | some cost => if work < cost then (.error ⟨self, COSTLY⟩, work) else (pick v bad self cases, work - cost)

/-- The step of a node other than a pick, with its price. A step that rounds to the grid
does it from the first enclosure of `extras` that separates its value from the grid, and
pays for each one it asks for before it asks. Gives the enclosure, or why the node has
none, and the work left. -/
def Node.tries (box v : Array Iv) (self : Nat) (node : Node) : List Nat → Nat → M (Except Failure Iv × Nat)
  | [], work => pure (.error ⟨self, UNSEPARATED⟩, work)
  | extra :: rest, work => do
    let cost := node.work box v extra (← get)
    if work < cost then pure (.error ⟨self, COSTLY⟩, work)
    else
      tryCatch (do
        let y ← fits (← node.enclose box v extra)
        pure (.ok y, work - cost))
        fun why =>
          if why == UNSEPARATED then node.tries box v self rest (work - cost)
          else pure (.error ⟨self, why⟩, work - cost)

/-- The step of a sum or a product with its price: `Node.enclose` folds `op` over the nodes
and holds each sum so far to `fits`, and this is that fold with each term paid for before it
is taken, by the bits of the sum so far and the bits of the term. So a sum of many
terms costs what its numbers come to, and not what they could. Gives the enclosure, or why
there is none, and the work left. -/
def folded (op : Iv → Iv → Iv) (price : Nat → Nat → Nat) (v : Array Iv) : List Nat → Iv → Nat → Except String Iv × Nat
  | [], acc, work => (.ok acc, work)
  | i :: rest, acc, work =>
    let cost := price acc.bits v[i]!.bits
    if work < cost then (.error COSTLY, work) else
      match fits (op acc v[i]!) with
      | .error why => (.error why, work - cost)
      | .ok next => folded op price v rest next (work - cost)

/-- One step of a tape with its price. A node that reads a failed node has that failure and
costs nothing. -/
def Node.priced (box v : Array Iv) (bad : Array (Option Failure)) (self : Nat) (node : Node) (work : Nat) :
    M (Except Failure Iv × Nat) :=
  match node with
  | .pick cases => pure (pickPriced v bad self cases work)
  | node =>
    match earliest bad node.reads with
    | some f => pure (.error f, work)
    | none =>
      let named (r : Except String Iv × Nat) : Except Failure Iv × Nat := (r.1.mapError (⟨self, ·⟩), r.2)
      match node with
      | .add a => pure (named (folded Iv.add addWork v a.toList (Iv.pt 0) work))
      | .mul a => pure (named (folded Iv.mul mulWork v a.toList (Iv.pt 1) work))
      | node => node.tries box v self EXTRAS work

/-- The walk over one box so far: the enclosure of each node walked and the failure of each
that has none, the words of the enclosures it holds, and the work left. -/
structure Walk where
  v : Array Iv
  bad : Array (Option Failure)
  held : Nat
  work : Nat

/-- Why a node has no enclosure once the last node that reads it is walked. -/
def GONE : String := "its enclosure was given up after the last node that reads it"

def HELD : String := s!"the tape holds more than {MAX_HELD} words of enclosures at once"

/-- The walk with the outcome of node `self` added. An enclosure that would take the walk
past `MAX_HELD` words is not kept, and the node has none. -/
def Walk.keep (w : Walk) (self : Nat) : Except Failure Iv → Walk
  | .ok y =>
    if w.held + y.words > MAX_HELD then { w with v := w.v.push default, bad := w.bad.push (some ⟨self, HELD⟩) }
    else { w with v := w.v.push y, bad := w.bad.push none, held := w.held + y.words }
  | .error f => { w with v := w.v.push default, bad := w.bad.push (some f) }

/-- The walk with the enclosures given up that node `self` read last. `last[k]` is the last
node that reads node `k`. A node given up is marked as failed, so a node that read it
afterwards would fail and not read `[0, 0]`: what is given up never reaches a root. -/
def Walk.release (w : Walk) (last : Array Nat) (self : Nat) (ids : Array Nat) : Walk :=
  ids.foldl (fun w k =>
    if last[k]! == self && w.bad[k]!.isNone then
      let held := w.held - w.v[k]!.words
      { w with v := w.v.setIfInBounds k default, bad := w.bad.setIfInBounds k (some ⟨k, GONE⟩), held }
    else w) w

/-- For each node, the last needed node that reads it. A root is never given up: it is read
after the last node. -/
def Tape.last (t : Tape) (roots : Array Nat) (need : Array Bool) : Array Nat := Id.run do
  let mut last := Array.replicate t.nodes.size 0
  for (node, i) in t.nodes.zipIdx do
    if need[i]! then last := node.reads.foldl (fun last k => last.setIfInBounds k i) last
  return roots.foldl (fun last r => last.setIfInBounds r t.nodes.size) last

/-- One node of the walk: its step when a root reads it, and then the enclosures it read
last are given up. A node no root reads has no step. -/
def Tape.visit (box : Array Iv) (need : Array Bool) (last : Array Nat) (node : Node) (i : Nat) (w : Walk) : M Walk :=
  if need[i]! then do
    let (x, work) ← node.priced box w.v w.bad i w.work
    pure (({ w with work }.keep i x).release last i node.reads)
  else pure { w with v := w.v.push default, bad := w.bad.push none }

/-- The walk over the box, in tape order: the enclosure of every needed node that is still
held, the failure of each node that has none, and the work left. A failure stops nothing
here. It matters where a root reads it, through arithmetic and the cases a pick found. -/
def Tape.eval (t : Tape) (box : Array Iv) (need : Array Bool) (last : Array Nat) (work : Nat) : M Walk := do
  let mut w : Walk := { v := Array.mkEmpty t.nodes.size, bad := Array.mkEmpty t.nodes.size, held := 0, work }
  for (node, i) in t.nodes.zipIdx do
    w ← Tape.visit box need last node i w
  return w

/-- What is wrong with a partition of the box, or nothing: it is at most `MAX_DEPTH` deep,
and each split is of an input of the tape, strictly inside the range the input has there. -/
def Partition.shape : Partition → Array Iv → Nat → Except String Unit
  | .leaf, _, _ => pure ()
  | .split k cut below above, box, depth => do
    if depth ≥ MAX_DEPTH then throw s!"the partition is deeper than {MAX_DEPTH}"
    let some r := box[k]? | throw s!"the partition splits input {k}, and the tape has {box.size} inputs"
    unless r.lo < cut && cut < r.hi do throw s!"a split of input {k} is not strictly inside its range"
    below.shape (box.setIfInBounds k ⟨r.lo, cut⟩) (depth + 1)
    above.shape (box.setIfInBounds k ⟨cut, r.hi⟩) (depth + 1)

/-- The walk over the leaves of a partition, below before above, one leaf at a time. `n` is
how many leaves are walked already. Gives why the first leaf that fails does, or nothing
when every root has an upper end of at most zero on every leaf, with the leaves walked and
the work left.

A split replaces its box by the halves at or below and at or above the cut, whose union is
the box, so the leaves cover the box. An enclosure contains a root's value at every point of
its leaf. So a root whose upper end is at most zero on every leaf is at most zero on the
box. An enclosure also shows the root is defined there, since a root that reads an undefined
step has none. -/
def Tape.walk (t : Tape) (need : Array Bool) (last : Array Nat) :
    Partition → Array Iv → Nat → Nat → M (Option String × Nat × Nat)
  | .leaf, box, n, work => do
    let w ← t.eval box need last work
    let why : Option String :=
      match earliest w.bad t.roots with
      | some f => some f.text
      | none =>
        if t.roots.all (fun root => decide (w.v[root]!.hi ≤ 0)) then none
        else some s!"root {(t.roots.findIdx? fun root => w.v[root]!.hi > 0).getD 0} is above zero"
    pure (why.map (s!"leaf {n}: " ++ ·), n + 1, w.work)
  | .split k cut below above, box, n, work => do
    let r := box[k]!
    let (why, n, work) ← t.walk need last below (box.setIfInBounds k ⟨r.lo, cut⟩) n work
    match why with
    | some why => pure (some why, n, work)
    | none => t.walk need last above (box.setIfInBounds k ⟨cut, r.hi⟩) n work

/-- A proof by a partition. Gives nothing when every root is at most zero on the box, or why
the proof fails, and the work left. A proof pays `Tape.fee` first, and one that cannot is
not tried. -/
def Tape.proved (t : Tape) (partition : Partition) (work : Nat) : M (Option String × Nat) :=
  let fee := t.fee partition.count
  if work < fee then pure (some SPENT, work) else
  match t.wellFormed with
  | .error why => pure (some why, work - fee)
  | .ok () =>
    let box := t.inputs.map (·.range)
    match partition.shape box 0 with
    | .error why => pure (some why, work - fee)
    | .ok () => do
      let need := t.needed t.roots
      let (why, _, work) ← t.walk need (t.last t.roots need) partition box 0 (work - fee)
      pure (why, work)

/-- A refutation by a point. Gives nothing when root `which` is above zero at the point,
which lies in the box, or why the refutation fails, and the work left. The enclosure of a
root at a point contains its value there. So a lower end above zero means the root is above
zero at a point of the box, and the statement is false. -/
def Tape.refuted (t : Tape) (point : Array Rat) (which : Nat) (work : Nat) : M (Option String × Nat) :=
  let fee := t.fee 1 + SPLIT * t.inputs.size
  if work < fee then pure (some SPENT, work) else
  match t.wellFormed with
  | .error why => pure (some why, work - fee)
  | .ok () =>
    match t.roots[which]? with
    | none => pure (some s!"the tape has no root {which}", work - fee)
    | some root =>
      if point.size != t.inputs.size then pure (some "the point does not hold one value for each input", work - fee)
      else if !(point.zip t.inputs).all (fun p => p.2.range.has p.1) then
        pure (some s!"the point is outside the range of input {((point.zip t.inputs).findIdx? fun p => !p.2.range.has p.1).getD 0}", work - fee)
      else do
        let need := t.needed #[root]
        let w ← t.eval (point.map Iv.pt) need (t.last #[root] need) (work - fee)
        match w.bad[root]! with
        | some f => pure (some f.text, w.work)
        | none =>
          if w.v[root]!.lo > 0 then pure (none, w.work)
          else pure (some s!"root {which} is not above zero at the point", w.work)

end Petra
