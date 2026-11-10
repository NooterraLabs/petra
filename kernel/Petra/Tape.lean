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

inductive Node where
  | c (x : Rat) | s (k : Nat) | pi
  | add (a : Array Nat) | mul (a : Array Nat) | min (a : Array Nat) | max (a : Array Nat)
  | neg (i : Nat) | abs (i : Nat) | sqrt (i : Nat) | ln (i : Nat) | exp (i : Nat)
  | div (i j : Nat) | pow (i : Nat) (n : Int)
  deriving Inhabited

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

def Node.reads : Node → Array Nat
  | .c _ | .s _ | .pi => #[]
  | .add a | .mul a | .min a | .max a => a
  | .neg i | .abs i | .sqrt i | .ln i | .exp i | .pow i _ => #[i]
  | .div i j => #[i, j]

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
nodes before it. -/
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

/-- The enclosure of every needed node over the box, in tape order. -/
def Tape.eval (t : Tape) (box : Array Iv) (need : Array Bool) : M (Array Iv) := do
  let mut v : Array Iv := Array.mkEmpty t.nodes.size
  for (node, i) in t.nodes.zipIdx do
    if need[i]! then
      try
        v := v.push (← fits (← node.enclose box v))
      catch why => throw s!"node {i}: {why}"
    else
      v := v.push default
  return v

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
An enclosure also shows the root is defined there, since an undefined step fails. -/
def Tape.proved (t : Tape) (partition : Partition) : M Unit := do
  t.wellFormed
  let need := t.needed t.roots
  for (cell, n) in (← partition.leaves (t.inputs.map (·.range)) 0).zipIdx do
    try
      let v ← t.eval cell need
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
  let v ← t.eval (point.map Iv.pt) (t.needed #[root])
  unless v[root]!.lo > 0 do throw s!"root {which} is not above zero at the point"

end Petra
