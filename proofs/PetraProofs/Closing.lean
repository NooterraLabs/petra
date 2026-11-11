/-
What is left, as three equations.

The theorems for a tape with `sqrt`, `pi`, `ln` or `exp` assume a statement about each of
the kernel's loops `isqrt`, `oddSeries` and `expAt`. `Provable/` holds a version of each loop
with no `while`, proved to meet that statement. So the assumptions hold as soon as the
kernel's three functions are those versions. Each equation below is then true by `rfl`.
-/
import PetraProofs.Rule
import PetraProofs.Provable.Isqrt
import PetraProofs.Provable.OddSeries
import PetraProofs.Provable.ExpAt

namespace Petra

/-- If the kernel's three loops are the versions of `Provable/`, every node's assumption
holds. -/
theorem Node.trusted_of_swap (h1 : isqrt = Provable.isqrt)
    (h2 : oddSeries = Provable.oddSeries) (h3 : expAt = Provable.expAt) (node : Node) :
    node.Trusted := by
  refine Node.trusted_of_specs ?_ ?_ ?_ node
  · unfold IsqrtSpec
    rw [h1]
    exact Provable.isqrt_spec
  · unfold OddSeriesSpec
    rw [h2]
    exact Provable.oddSeries_spec
  · unfold ExpAtSpec
    rw [h3]
    exact Provable.expAt_spec

/-- Any tape, proved, with the three loops swapped. -/
theorem Tape.proved_sound_of_swap {t : Tape} {p : Partition} {c c' : Caches}
    (h1 : isqrt = Provable.isqrt) (h2 : oddSeries = Provable.oddSeries)
    (h3 : expAt = Provable.expAt) (hc : c.Valid) (h : t.proved p c = .ok ((), c')) :
    c'.Valid ∧ ∀ ρ, InBox (t.inputs.map (·.range)) ρ →
      ∀ root ∈ t.roots, ∃ x, t.value ρ root = some x ∧ x ≤ 0 :=
  Tape.proved_sound (fun node _ => Node.trusted_of_swap h1 h2 h3 node) hc h

/-- Any tape, refuted, with the three loops swapped. -/
theorem Tape.refuted_sound_of_swap {t : Tape} {point : Array ℚ} {which : Nat} {c c' : Caches}
    (h1 : isqrt = Provable.isqrt) (h2 : oddSeries = Provable.oddSeries)
    (h3 : expAt = Provable.expAt) (hc : c.Valid) (h : t.refuted point which c = .ok ((), c')) :
    c'.Valid ∧ ∃ root, t.roots[which]? = some root ∧
      InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) ∧
      ∃ x, t.value (fun k => ((point[k]! : ℚ) : ℝ)) root = some x ∧ 0 < x :=
  Tape.refuted_sound (fun node _ => Node.trusted_of_swap h1 h2 h3 node) hc h

end Petra
