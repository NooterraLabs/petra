/-
A strict inequality. A rule of a deck that states `lt` asks that one side is under the other,
and not only at most it. The kernel writes it with the nodes it has: the root of the rule's
tape is a pick that is -1 where node `i` is under node `j`, and 1 elsewhere (`Rule.tape` in
kernel/Petra/Deck.lean). So the two rules of a tape decide it as they stand.

- `Tape.proved` shows the root at most zero at every point of the box. The root is -1 or 1,
  so it is -1 there, and node `i` is under node `j` at every point.
- `Tape.refuted` shows the root above zero at the point. So it is 1 there, and node `i` is
  not under node `j` at the point.

Both follow from `Tape.proved_sound` and `Tape.refuted_sound` and from what a pick means
(Meaning.lean). Nothing of the kernel is changed for them. They are about any tape whose
root has this shape. That `Rule.tape` gives the root this shape is read from its three
lines, and is not proved here: Deck.lean is outside what the proofs read.
-/
import PetraProofs.Rule

namespace Petra

/-- The value of a constant node. -/
theorem Tape.value_const {t : Tape} {ρ : Nat → ℝ} {k : Nat} {q : ℚ} (h : t.nodes[k]? = some (.c q)) :
    t.value ρ k = some (q : ℝ) := by
  obtain ⟨hk, hnode⟩ := Array.getElem?_eq_some_iff.mp h
  rw [Tape.value_eq hk, hnode]
  rfl

/-- What a strict root is worth. Where it has a value, node `i` and node `j` have values
too, and the root is -1 when the first is under the second and 1 when it is not. -/
theorem Tape.strict_value {t : Tape} {ρ : Nat → ℝ} {root i j m p : Nat} {x : ℝ}
    (hroot : t.nodes[root]? = some (.pick #[(some (.lt i j), m), (none, p)]))
    (hm : t.nodes[m]? = some (.c (-1))) (hp : t.nodes[p]? = some (.c 1))
    (hx : t.value ρ root = some x) :
    ∃ a b, t.value ρ i = some a ∧ t.value ρ j = some b ∧ ((a < b ∧ x = -1) ∨ (b ≤ a ∧ x = 1)) := by
  obtain ⟨hlt, hnode⟩ := Array.getElem?_eq_some_iff.mp hroot
  rw [Tape.value_eq hlt, hnode] at hx
  -- what a node before the root is worth, as the root reads it
  have before : ∀ (k : Nat) (y : ℝ),
      (if _h : k < root then t.value ρ k else none) = some y → t.value ρ k = some y := by
    intro k y hk
    by_cases hlt' : k < root
    · rw [dif_pos hlt'] at hk
      exact hk
    · rw [dif_neg hlt'] at hk
      cases hk
  generalize hval : (fun k => if _h : k < root then t.value ρ k else none) = val at hx
  have before' : ∀ (k : Nat) (y : ℝ), val k = some y → t.value ρ k = some y := by
    intro k y hk
    rw [← hval] at hk
    exact before k y hk
  have hx' : pickValue val [(some (.lt i j), m), (none, p)] = some x := hx
  unfold pickValue at hx'
  cases hvi : val i with
  | none =>
    simp [caseTruth, Cond.truth, hvi] at hx'
  | some a =>
    cases hvj : val j with
    | none =>
      simp [caseTruth, Cond.truth, hvi, hvj] at hx'
    | some b =>
      refine ⟨a, b, before' i a hvi, before' j b hvj, ?_⟩
      by_cases hab : a < b
      · left
        simp [caseTruth, Cond.truth, hvi, hvj, hab] at hx'
        have hmv := before' m x hx'
        rw [Tape.value_const hm] at hmv
        have hxe : ((-1 : ℚ) : ℝ) = x := Option.some.inj hmv
        refine ⟨hab, ?_⟩
        rw [← hxe]
        norm_num
      · right
        simp [caseTruth, Cond.truth, hvi, hvj, hab] at hx'
        have hpv := before' p x hx'
        rw [Tape.value_const hp] at hpv
        have hxe : ((1 : ℚ) : ℝ) = x := Option.some.inj hpv
        refine ⟨not_lt.mp hab, ?_⟩
        rw [← hxe]
        norm_num

/-- A strict root, proved. If `Tape.proved` returns no failure from valid caches, with any
work, and a root of the tape is the strict root of node `i` against node `j`, then at every
point of the box both nodes have values and the first is under the second. -/
theorem Tape.proved_strict {t : Tape} {part : Partition} {work left : Nat} {c c' : Caches}
    {root i j m p : Nat} (hc : c.Valid) (h : t.proved part work c = .ok ((none, left), c'))
    (hmem : root ∈ t.roots)
    (hroot : t.nodes[root]? = some (.pick #[(some (.lt i j), m), (none, p)]))
    (hm : t.nodes[m]? = some (.c (-1))) (hp : t.nodes[p]? = some (.c 1)) :
    ∀ ρ, InBox (t.inputs.map (·.range)) ρ →
      ∃ a b, t.value ρ i = some a ∧ t.value ρ j = some b ∧ a < b := by
  intro ρ hρ
  obtain ⟨x, hx, hle⟩ := (Tape.proved_sound hc h).2 ρ hρ root hmem
  obtain ⟨a, b, ha, hb, hcase⟩ := Tape.strict_value hroot hm hp hx
  rcases hcase with ⟨hab, -⟩ | ⟨-, hx1⟩
  · exact ⟨a, b, ha, hb, hab⟩
  · exfalso
    rw [hx1] at hle
    linarith

/-- A strict root, refuted. If `Tape.refuted` returns no failure from valid caches, with any
work, and the root it names is the strict root of node `i` against node `j`, then the point
lies in the box, both nodes have values there, and the first is not under the second: the
second is at most the first. -/
theorem Tape.refuted_strict {t : Tape} {point : Array ℚ} {which work left : Nat} {c c' : Caches}
    {i j m p : Nat} (hc : c.Valid) (h : t.refuted point which work c = .ok ((none, left), c'))
    (hroot : ∀ root, t.roots[which]? = some root →
      t.nodes[root]? = some (.pick #[(some (.lt i j), m), (none, p)]))
    (hm : t.nodes[m]? = some (.c (-1))) (hp : t.nodes[p]? = some (.c 1)) :
    InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) ∧
      ∃ a b, t.value (fun k => ((point[k]! : ℚ) : ℝ)) i = some a ∧
        t.value (fun k => ((point[k]! : ℚ) : ℝ)) j = some b ∧ b ≤ a := by
  obtain ⟨-, root, hr, hbox, x, hx, hpos⟩ := Tape.refuted_sound hc h
  obtain ⟨a, b, ha, hb, hcase⟩ := Tape.strict_value (hroot root hr) hm hp hx
  refine ⟨hbox, a, b, ha, hb, ?_⟩
  rcases hcase with ⟨-, hx1⟩ | ⟨hba, -⟩
  · exfalso
    rw [hx1] at hpos
    linarith
  · exact hba

end Petra
