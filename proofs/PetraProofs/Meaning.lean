/-
What a tape means: the real value of each node at a point, an assignment of a real number
to each input. This file is the statement the proofs are about, so it is the one to read
against docs/format.md, section "Tapes": the table of nodes and the paragraph on `pick`.

A value is an `Option ℝ`. `none` says the node has no value at the point: it divides by
zero, takes the square root of a negative number or the logarithm of a number that is not
positive, reads an input the tape does not have, reads a node that has no value, or is a
pick with no case that holds.
-/
import Mathlib.Data.Real.Sqrt
import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Analysis.SpecialFunctions.Exp
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Basic
import PetraProofs.Basic

namespace Petra

/-- Whether a condition holds, when `val i` is the value of node `i`. It is `none` when a
node that the condition compares has no value. -/
noncomputable def Cond.truth (val : Nat → Option ℝ) : Cond → Option Bool
  | .le i j => match val i, val j with
    | some x, some y => some (decide (x ≤ y))
    | _, _ => none
  | .lt i j => match val i, val j with
    | some x, some y => some (decide (x < y))
    | _, _ => none
  | .and cs => cs.foldl (fun so c => match so, c.truth val with
    | some a, some b => some (a && b)
    | _, _ => none) (some true)
  | .or cs => cs.foldl (fun so c => match so, c.truth val with
    | some a, some b => some (a || b)
    | _, _ => none) (some false)
  | .not c => (c.truth val).map (!·)

/-- Whether a case of a pick holds. A case with no condition holds. -/
noncomputable def caseTruth (val : Nat → Option ℝ) : Option Cond → Option Bool
  | none => some true
  | some c => c.truth val

/-- The value of a pick: the value of the node of the first case whose condition holds. It
has one only when every condition of the pick has a truth value. -/
noncomputable def pickValue (val : Nat → Option ℝ) (cases : List (Option Cond × Nat)) : Option ℝ :=
  if cases.all (fun case => (caseTruth val case.1).isSome) then
    match cases.find? (fun case => caseTruth val case.1 == some true) with
    | some (_, i) => val i
    | none => none
  else none

/-- The value of a node, when the tape has `inputs` inputs, `ρ k` is the value of input `k`
and `val i` is the value of node `i`. -/
noncomputable def Node.value (inputs : Nat) (ρ : Nat → ℝ) (val : Nat → Option ℝ) : Node → Option ℝ
  | .c x => some (x : ℝ)
  | .s k => if k < inputs then some (ρ k) else none
  | .pi => some Real.pi
  | .add a => (a.toList.mapM val).map List.sum
  | .mul a => (a.toList.mapM val).map List.prod
  | .min a => (a.toList.mapM val).bind fun xs => match xs with
    | [] => none
    | x :: rest => some (rest.foldl Min.min x)
  | .max a => (a.toList.mapM val).bind fun xs => match xs with
    | [] => none
    | x :: rest => some (rest.foldl Max.max x)
  | .neg i => (val i).map fun x => -x
  | .abs i => (val i).map fun x => |x|
  | .sqrt i => (val i).bind fun x => if 0 ≤ x then some (Real.sqrt x) else none
  | .ln i => (val i).bind fun x => if 0 < x then some (Real.log x) else none
  | .exp i => (val i).map Real.exp
  | .cos i => (val i).map Real.cos
  | .div i j => (val i).bind fun x => (val j).bind fun y => if y = 0 then none else some (x / y)
  | .pow i n => (val i).bind fun x => if 0 ≤ n ∨ x ≠ 0 then some (x ^ n) else none
  | .pick cases => pickValue val cases.toList

/-- The value of node `i` of a tape at the point `ρ`. A node reads only the nodes before
it: a node that names itself or a later node reads `none` there. -/
noncomputable def Tape.value (t : Tape) (ρ : Nat → ℝ) (i : Nat) : Option ℝ :=
  if h : i < t.nodes.size then
    t.nodes[i].value t.inputs.size ρ (fun j => if _h : j < i then t.value ρ j else none)
  else none
termination_by i

/-- The point `ρ` lies in the box: each input's value lies in that input's range. -/
def InBox (box : Array Iv) (ρ : Nat → ℝ) : Prop :=
  ∀ k, k < box.size → box[k]!.Holds (ρ k)

end Petra
