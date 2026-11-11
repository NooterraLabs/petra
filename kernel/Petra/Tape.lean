/-
The tape of docs/format.md: a statement that every root is at most zero for all values of
the inputs in their ranges. A partition proves one and a point refutes one, as `prove` and
`refute` do in petra/kernel/rules/r4_enclosure.py.
-/
import Petra.Num

namespace Petra

/-- The deepest a partition may split, as in r4_enclosure.py. It bounds the walk and not
soundness: any finite split tree covers its box. -/
def MAX_DEPTH : Nat := 64

/-- The largest magnitude a `pow` exponent may have. -/
def MAX_EXPONENT : Nat := 64

/-- The most bits a numerator or a denominator may have, and the largest magnitude `exp`
takes. A tape can square a value at every node, so without this a short tape would not end. -/
def MAX_BITS : Nat := 65536

/-- The most ways a pick may have to order the nodes its conditions compare on one box. -/
def MAX_CHOICES : Nat := 4096

/-- The deepest a condition of a pick may nest, where an order alone is 1 deep. -/
def MAX_COND_DEPTH : Nat := 16

/-- The condition of a case of a pick: an order between two nodes, or conditions joined. -/
inductive Cond where
  | le (i j : Nat) | lt (i j : Nat)
  | and (cs : Array Cond) | or (cs : Array Cond) | not (c : Cond)
  deriving Inhabited, BEq, Hashable

inductive Node where
  | c (x : Rat) | s (k : Nat) | pi
  | add (a : Array Nat) | mul (a : Array Nat) | min (a : Array Nat) | max (a : Array Nat)
  | neg (i : Nat) | abs (i : Nat) | sqrt (i : Nat) | ln (i : Nat) | exp (i : Nat)
  | div (i j : Nat) | pow (i : Nat) (n : Int)
  /-- The value of the first case whose condition holds. A case is its condition and the
  node that is then the pick's value. A case with no condition holds otherwise. -/
  | pick (cases : Array (Option Cond × Nat))
  deriving Inhabited, BEq, Hashable

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
  | .div i j => .div (f i) (f j)
  | .pow i n => .pow (f i) n
  | .pick cases => .pick (cases.map fun (cond, value) => (cond.map (·.map f), f value))

def Node.reads : Node → Array Nat
  | .c _ | .s _ | .pi => #[]
  | .add a | .mul a | .min a | .max a => a
  | .neg i | .abs i | .sqrt i | .ln i | .exp i | .pow i _ => #[i]
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
nodes before it. A pick has its own step, `pick`, which also reads which nodes failed. -/
def Node.enclose (box v : Array Iv) : Node → M Iv
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
  | .ln i => iLn v[i]!
  | .exp i =>
    if v[i]!.lo < -(MAX_BITS : Rat) || v[i]!.hi > (MAX_BITS : Rat) then throw s!"exp of a value beyond {MAX_BITS}"
    else iExp v[i]!
  | .div i j => liftM (m := Except String) (v[i]!.div v[j]!)
  | .pow i n => liftM (m := Except String) (powInt v[i]! n)
  | .pick _ => throw "a pick is not enclosed by this step"

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

/-- The enclosure of every needed node over the box, in tape order, and the failure of each
node that has none. A failure stops nothing here. It matters where a root reads it, through
arithmetic and the cases a pick found. -/
def Tape.eval (t : Tape) (box : Array Iv) (need : Array Bool) : M (Array Iv × Array (Option Failure)) := do
  let mut v : Array Iv := Array.mkEmpty t.nodes.size
  let mut bad : Array (Option Failure) := Array.mkEmpty t.nodes.size
  for (node, i) in t.nodes.zipIdx do
    let mut x : Except Failure Iv := .ok default
    if need[i]! then
      if let .pick cases := node then x := pick v bad i cases
      else if let some f := earliest bad node.reads then x := .error f
      else
        try
          x := .ok (← fits (← node.enclose box v))
        catch why => x := .error ⟨i, why⟩
    match x with
    | .ok y =>
      v := v.push y
      bad := bad.push none
    | .error f =>
      v := v.push default
      bad := bad.push (some f)
  return (v, bad)

/-- The cells of a partition, below before above. A split replaces its cell by the halves at
or below and at or above the cut, whose union is the cell, so the leaves cover the box. -/
def Partition.leaves : Partition → Array Iv → Nat → Except String (Array (Array Iv))
  | .leaf, box, _ => pure #[box]
  | .split k cut below above, box, depth => do
    if depth ≥ MAX_DEPTH then throw s!"the partition is deeper than {MAX_DEPTH}"
    let some r := box[k]? | throw s!"the partition splits input {k}, and the tape has {box.size} inputs"
    unless r.lo < cut && cut < r.hi do throw s!"a split of input {k} is not strictly inside its range"
    let lower ← below.leaves (box.setIfInBounds k ⟨r.lo, cut⟩) (depth + 1)
    let upper ← above.leaves (box.setIfInBounds k ⟨cut, r.hi⟩) (depth + 1)
    return lower ++ upper

/-- The leaves cover the box, and an enclosure contains a root's value at every point of its
leaf. So a root whose upper end is at most zero on every leaf is at most zero on the box.
An enclosure also shows the root is defined there, since a root that reads an undefined
step has none. -/
def Tape.proved (t : Tape) (partition : Partition) : M Unit := do
  t.wellFormed
  let need := t.needed t.roots
  for (cell, n) in (← partition.leaves (t.inputs.map (·.range)) 0).zipIdx do
    try
      let (v, bad) ← t.eval cell need
      if let some f := earliest bad t.roots then throw f.text
      for (root, k) in t.roots.zipIdx do
        if v[root]!.hi > 0 then throw s!"root {k} is above zero"
    catch why => throw s!"leaf {n}: {why}"

/-- The enclosure of a root at a point contains its value there. So a lower end above zero
means the root is above zero at a point of the box, and the statement is false. -/
def Tape.refuted (t : Tape) (point : Array Rat) (which : Nat) : M Unit := do
  t.wellFormed
  let some root := t.roots[which]? | throw s!"the tape has no root {which}"
  unless point.size == t.inputs.size do throw "the point does not hold one value for each input"
  for ((x, input), i) in (point.zip t.inputs).zipIdx do
    unless input.range.has x do throw s!"the point is outside the range of input {i}"
  let (v, bad) ← t.eval (point.map Iv.pt) (t.needed #[root])
  if let some f := bad[root]! then throw f.text
  unless v[root]!.lo > 0 do throw s!"root {which} is not above zero at the point"

end Petra
