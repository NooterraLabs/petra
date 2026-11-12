/-
A rule's `where`. Outside the range of its `where` a rule says nothing, so a cell whose
`where` is not proved over the box is not proved. A point inside the range where the rule
fails refutes it there. The kernel writes that with the nodes it has: the root of the tape is
a pick that is the rule's own root where every pair of the `where` is in order, and -1
elsewhere (`Rule.tape` with `within`, in kernel/Petra/Deck.lean). The kernel only refutes
with such a tape.

`Tape.refuted` shows that root above zero at the point. So it is not -1 there: every pair of
the `where` has values in order at the point, and the rule's own root is above zero.

This follows from `Tape.refuted_sound` and from what a pick means (Meaning.lean), as
Strict.lean does for `lt`. It is about any tape whose root has this shape. That `Rule.tape`
gives the root this shape is read from its lines, and is not proved here: Deck.lean is
outside what the proofs read.
-/
import PetraProofs.Strict

namespace Petra

/-- A fold that is true only where what it held so far is true and the next condition is
true, true at the end: what it started with is true, and so is every condition. -/
private theorem foldl_true {val : Nat → Option ℝ} {f : Option Bool → Cond → Option Bool}
    (hf : ∀ so c, f so c = some true → so = some true ∧ c.truth val = some true) :
    ∀ (l : List Cond) (so : Option Bool), l.foldl f so = some true →
      so = some true ∧ ∀ c ∈ l, c.truth val = some true
  | [], so, h => ⟨h, fun c hc => by simp at hc⟩
  | c :: l, so, h => by
    rw [List.foldl_cons] at h
    obtain ⟨h1, h2⟩ := foldl_true hf l (f so c) h
    obtain ⟨h3, h4⟩ := hf so c h1
    refine ⟨h3, fun d hd => ?_⟩
    rcases List.mem_cons.mp hd with rfl | hd
    · exact h4
    · exact h2 d hd

/-- An `and` of `le` conditions that is true: both nodes of each pair have values, and the
first is at most the second. -/
private theorem and_le_true {val : Nat → Option ℝ} {gate : Array (Nat × Nat)}
    (h : Cond.truth val (.and (gate.map fun p => .le p.1 p.2)) = some true) :
    ∀ p ∈ gate.toList, ∃ a b, val p.1 = some a ∧ val p.2 = some b ∧ a ≤ b := by
  intro p hp
  rw [Cond.truth, ← Array.foldl_toList] at h
  refine (fun hall => ?_) ((foldl_true (val := val) ?_ _ _ h).2 (.le p.1 p.2) ?_)
  · rw [Cond.truth] at hall
    split at hall
    · rename_i a b ha hb
      simp at hall
      exact ⟨a, b, ha, hb, hall⟩
    · cases hall
  · intro so c hfc
    split at hfc
    · simp_all
    · cases hfc
  · rw [Array.toList_map]
    exact List.mem_map.mpr ⟨p, hp, rfl⟩

/-- What a root under a `where` is worth. Where it is above zero, both nodes of each pair of
the `where` have values and the first is at most the second, and the rule's own root `r` has
the same value. -/
theorem Tape.within_value {t : Tape} {ρ : Nat → ℝ} {root r m : Nat} {gate : Array (Nat × Nat)} {x : ℝ}
    (hroot : t.nodes[root]? = some (.pick #[(some (.and (gate.map fun p => .le p.1 p.2)), r), (none, m)]))
    (hm : t.nodes[m]? = some (.c (-1))) (hx : t.value ρ root = some x) (hpos : 0 < x) :
    (∀ p ∈ gate.toList, ∃ a b, t.value ρ p.1 = some a ∧ t.value ρ p.2 = some b ∧ a ≤ b) ∧
      t.value ρ r = some x := by
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
  have hx' : pickValue val [(some (.and (gate.map fun p => .le p.1 p.2)), r), (none, m)] = some x := hx
  unfold pickValue at hx'
  cases hg : Cond.truth val (.and (gate.map fun p => .le p.1 p.2)) with
  | none => simp [caseTruth, hg] at hx'
  | some g =>
    cases g with
    | false =>
      simp [caseTruth, hg] at hx'
      have hmv := before' m x hx'
      rw [Tape.value_const hm] at hmv
      have hxe : ((-1 : ℚ) : ℝ) = x := Option.some.inj hmv
      rw [← hxe] at hpos
      norm_num at hpos
    | true =>
      simp [caseTruth, hg] at hx'
      refine ⟨fun p hp => ?_, before' r x hx'⟩
      obtain ⟨a, b, ha, hb, hab⟩ := and_le_true hg p hp
      exact ⟨a, b, before' _ _ ha, before' _ _ hb, hab⟩

/-- A root under a `where`, refuted. If `Tape.refuted` returns no failure from valid caches,
with any work, and the root it names is the root `r` under the `where` of `gate`, then the
point lies in the box, both nodes of each pair of the `where` have values there and the first
is at most the second, and the root `r` is above zero there. -/
theorem Tape.refuted_within {t : Tape} {point : Array ℚ} {which work left : Nat} {c c' : Caches}
    {gate : Array (Nat × Nat)} {r m : Nat} (hc : c.Valid) (h : t.refuted point which work c = .ok ((none, left), c'))
    (hroot : ∀ root, t.roots[which]? = some root →
      t.nodes[root]? = some (.pick #[(some (.and (gate.map fun p => .le p.1 p.2)), r), (none, m)]))
    (hm : t.nodes[m]? = some (.c (-1))) :
    InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) ∧
      (∀ p ∈ gate.toList, ∃ a b, t.value (fun k => ((point[k]! : ℚ) : ℝ)) p.1 = some a ∧
        t.value (fun k => ((point[k]! : ℚ) : ℝ)) p.2 = some b ∧ a ≤ b) ∧
      ∃ y, t.value (fun k => ((point[k]! : ℚ) : ℝ)) r = some y ∧ 0 < y := by
  obtain ⟨-, root, hr, hbox, x, hx, hpos⟩ := Tape.refuted_sound hc h
  obtain ⟨hgate, hrx⟩ := Tape.within_value (hroot root hr) hm hx hpos
  exact ⟨hbox, hgate, x, hrx, hpos⟩

end Petra
