/-
The rule. A partition's leaves cover the box. So when `Tape.proved` succeeds, every root has
a value at most zero at every point of the box, and when `Tape.refuted` succeeds, the root
it names has a value above zero at the point given, which lies in the box.
-/
import PetraProofs.Eval

namespace Petra

/-! ## The leaves of a partition cover the box -/

theorem InBox.set {box : Array Iv} {ρ : Nat → ℝ} {k : Nat} {x : Iv} (h : InBox box ρ)
    (hx : k < box.size → x.Holds (ρ k)) : InBox (box.setIfInBounds k x) ρ := by
  intro j hj
  have hj' : j < box.size := by simpa using hj
  rw [getElem!_setIfInBounds]
  split_ifs with hk
  · obtain ⟨rfl, _⟩ := hk
    exact hx hj'
  · exact h j hj'

/-- What a split that succeeds has checked, and what it returns. -/
theorem Partition.split_ok {k : Nat} {cut : ℚ} {below above : Partition} {box : Array Iv}
    {depth : Nat} {cells : Array (Array Iv)}
    (h : (Partition.split k cut below above).leaves box depth = .ok cells) :
    ∃ (hk : k < box.size) (lower upper : Array (Array Iv)),
      below.leaves (box.setIfInBounds k ⟨box[k].lo, cut⟩) (depth + 1) = .ok lower ∧
      above.leaves (box.setIfInBounds k ⟨cut, box[k].hi⟩) (depth + 1) = .ok upper ∧
      cells = lower ++ upper := by
  rw [Partition.leaves] at h
  dsimp only at h
  split at h
  · exact (Except.throw_bind_ne_ok h).elim
  rw [pure_bind] at h
  split at h
  swap
  · have h' : (Except.error _ : Except String (Array (Array Iv))) = .ok cells := h
    cases h'
  rename_i r hr
  split at h
  swap
  · exact (Except.throw_bind_ne_ok h).elim
  rw [pure_bind] at h
  obtain ⟨lower, hlow, h⟩ := Except.bind_ok h
  obtain ⟨upper, hup, h⟩ := Except.bind_ok h
  have h' : (Except.ok (lower ++ upper) : Except String (Array (Array Iv))) = .ok cells := h
  cases h'
  obtain ⟨hk, hrk⟩ := Array.getElem?_eq_some_iff.mp hr
  subst hrk
  exact ⟨hk, lower, upper, hlow, hup, rfl⟩

/-- A leaf has one range for each input. -/
theorem Partition.leaves_size : ∀ (p : Partition) (box : Array Iv) (depth : Nat)
    (cells : Array (Array Iv)), p.leaves box depth = .ok cells →
    ∀ cell ∈ cells, cell.size = box.size := by
  intro p
  induction p with
  | leaf =>
    intro box depth cells h cell hcell
    have h' : (Except.ok #[box] : Except String (Array (Array Iv))) = .ok cells := h
    cases h'
    simp only [List.mem_toArray, List.mem_singleton] at hcell
    rw [hcell]
  | split k cut below above ihb iha =>
    intro box depth cells h cell hcell
    obtain ⟨hk, lower, upper, hlow, hup, rfl⟩ := Partition.split_ok h
    rcases Array.mem_append.mp hcell with hmem | hmem
    · rw [ihb _ _ _ hlow cell hmem]
      simp
    · rw [iha _ _ _ hup cell hmem]
      simp

/-- Every point of the box lies in some leaf. -/
theorem Partition.leaves_cover : ∀ (p : Partition) (box : Array Iv) (depth : Nat)
    (cells : Array (Array Iv)) (ρ : Nat → ℝ), p.leaves box depth = .ok cells → InBox box ρ →
    ∃ cell ∈ cells, InBox cell ρ := by
  intro p
  induction p with
  | leaf =>
    intro box depth cells ρ h hρ
    have h' : (Except.ok #[box] : Except String (Array (Array Iv))) = .ok cells := h
    cases h'
    exact ⟨box, by simp, hρ⟩
  | split k cut below above ihb iha =>
    intro box depth cells ρ h hρ
    obtain ⟨hk, lower, upper, hlow, hup, rfl⟩ := Partition.split_ok h
    have hρk := hρ k hk
    rw [getElem!_pos box k hk] at hρk
    rcases le_total (ρ k) (cut : ℝ) with hle | hge
    · obtain ⟨cell, hmem, hin⟩ := ihb _ _ _ ρ hlow (hρ.set (fun _ => ⟨hρk.1, hle⟩))
      exact ⟨cell, Array.mem_append.mpr (Or.inl hmem), hin⟩
    · obtain ⟨cell, hmem, hin⟩ := iha _ _ _ ρ hup (hρ.set (fun _ => ⟨hge, hρk.2⟩))
      exact ⟨cell, Array.mem_append.mpr (Or.inr hmem), hin⟩

/-! ## A proof by partition -/

/-- The rule for a proof, for any property `V` of the caches that every step of the tape
keeps. The two theorems after it are its two readings. -/
theorem Tape.proved_sound_of {t : Tape} {p : Partition} {c c' : Caches} {V : Caches → Prop}
    (hstep : ∀ node ∈ t.nodes, node.StepSound V) (hc : V c)
    (h : t.proved p c = .ok ((), c')) :
    V c' ∧ ∀ ρ, InBox (t.inputs.map (·.range)) ρ →
      ∀ root ∈ t.roots, ∃ x, t.value ρ root = some x ∧ x ≤ 0 := by
  unfold Tape.proved at h
  dsimp only at h
  obtain ⟨u1, c1, hwf0, h1⟩ := M.bind_ok h
  obtain ⟨hwf1, hc1⟩ := M.lift_ok hwf0
  rw [hc1] at h1
  have hwf := Tape.wellFormed_ok hwf1
  obtain ⟨cells, c2, hleaves0, h2⟩ := M.bind_ok h1
  obtain ⟨hleaves, hc2⟩ := M.lift_ok hleaves0
  rw [hc2] at h2
  obtain ⟨u2, c3, hloop, hret⟩ := M.bind_ok h2
  have hc3 : c' = c3 := (M.pure_ok hret).2
  rw [hc3]
  obtain ⟨-, hn2, hn3⟩ := Tape.needed_spec hwf t.roots
  have hsizes := Partition.leaves_size p _ 0 cells hleaves
  have hinv : V c3 ∧ ∀ j (hj : j < cells.size), j < cells.zipIdx.size → ∀ ρ,
      InBox cells[j] ρ → ∀ root ∈ t.roots, ∃ x, t.value ρ root = some x ∧ x ≤ 0 := by
    refine M.forIn_array_inv _ (fun k (_ : PUnit) c0 => V c0 ∧
      ∀ j (hj : j < cells.size), j < k → ∀ ρ, InBox cells[j] ρ →
        ∀ root ∈ t.roots, ∃ x, t.value ρ root = some x ∧ x ≤ 0)
      cells.zipIdx PUnit.unit u2 c c3 ?_ ?_ hloop
    · exact ⟨hc, fun j _ hlt => absurd hlt (Nat.not_lt_zero j)⟩
    · intro j hj b cj s cj' hP hf
      have hj' : j < cells.size := by simpa using hj
      obtain ⟨hcv, hprev⟩ := hP
      simp only [Array.getElem_zipIdx, Nat.zero_add] at hf
      obtain ⟨u, c4, htc, hy⟩ := M.bind_ok hf
      obtain ⟨hs, hc4⟩ := M.pure_ok (a := ForInStep.yield PUnit.unit) hy
      rcases M.tryCatch_ok htc with hok | ⟨e, -, hh⟩
      swap
      · exact (M.throw_not_ok hh).elim
      obtain ⟨⟨v, bad⟩, c5, heval, hrest⟩ := M.bind_ok hok
      dsimp only at hrest
      have hsize : cells[j].size = t.inputs.size := by
        rw [hsizes cells[j] (Array.mem_of_getElem (h := hj') rfl)]
        simp
      obtain ⟨hcv', hev⟩ := Tape.eval_sound hwf hstep hn3 hsize hcv heval
      cases hearly : earliest bad t.roots with
      | some f =>
        rw [hearly] at hrest
        obtain ⟨_, _, hthrow, -⟩ := M.bind_ok hrest
        exact (M.throw_not_ok hthrow).elim
      | none =>
        rw [hearly] at hrest
        simp only [pure_bind] at hrest
        obtain ⟨u', c6, hroots, hret'⟩ := M.bind_ok hrest
        have hc6 : c4 = c6 := (M.pure_ok hret').2
        -- no root's upper end is above zero
        have hrinv : c6 = c5 ∧ ∀ i (hi : i < t.roots.size), i < t.roots.zipIdx.size →
            ¬ (v[t.roots[i]]!.hi > 0) := by
          refine M.forIn_array_inv _ (fun k (_ : PUnit) c0 => c0 = c5 ∧
            ∀ i (hi : i < t.roots.size), i < k → ¬ (v[t.roots[i]]!.hi > 0))
            t.roots.zipIdx PUnit.unit u' c5 c6 ?_ ?_ hroots
          · exact ⟨rfl, fun i _ hlt => absurd hlt (Nat.not_lt_zero i)⟩
          · intro i hi b' ci s' ci' hP' hf'
            have hi' : i < t.roots.size := by simpa using hi
            obtain ⟨hci, hprev'⟩ := hP'
            simp only [Array.getElem_zipIdx, Nat.zero_add] at hf'
            by_cases hpos : v[t.roots[i]]!.hi > 0
            · rw [if_pos hpos] at hf'
              obtain ⟨_, _, hthrow, -⟩ := M.bind_ok hf'
              exact (M.throw_not_ok hthrow).elim
            · rw [if_neg hpos] at hf'
              obtain ⟨hs', hci'⟩ := M.pure_ok (a := ForInStep.yield PUnit.unit) hf'
              refine ⟨PUnit.unit, hs', by rw [hci', hci], ?_⟩
              intro i' hi'' hlt
              rcases Nat.lt_succ_iff_lt_or_eq.mp hlt with hlt | rfl
              · exact hprev' i' hi'' hlt
              · exact hpos
        obtain ⟨hc65, hroots'⟩ := hrinv
        refine ⟨PUnit.unit, hs, by rw [hc4, hc6, hc65]; exact hcv', ?_⟩
        intro j' hj'' hlt ρ hρ root hroot
        rcases Nat.lt_succ_iff_lt_or_eq.mp hlt with hlt | rfl
        · exact hprev j' hj'' hlt ρ hρ root hroot
        · have hbad := earliest_none hearly
          have hlt' := hwf.roots root hroot
          obtain ⟨x, hx, hxv⟩ := hev ρ hρ root hlt' (hn2 root hroot hlt') (hbad root hroot)
          obtain ⟨i, hi, hri⟩ := Array.mem_iff_getElem.mp hroot
          have hhi : ((v[root]!.hi : ℚ) : ℝ) ≤ 0 := by
            rw [← hri]
            exact_mod_cast not_lt.mp (hroots' i hi (by simpa using hi))
          exact ⟨x, hx, hxv.2.trans hhi⟩
  obtain ⟨hcv, hall⟩ := hinv
  refine ⟨hcv, fun ρ hρ root hroot => ?_⟩
  obtain ⟨cell, hmem, hin⟩ := Partition.leaves_cover p _ 0 cells ρ hleaves hρ
  obtain ⟨j, hj, hcj⟩ := Array.mem_iff_getElem.mp hmem
  rw [← hcj] at hin
  exact hall j hj (by simpa using hj) ρ hin root hroot

/-! ## A refutation by a point -/

/-- The rule for a refutation, for any property `V` of the caches that every step of the
tape keeps. -/
theorem Tape.refuted_sound_of {t : Tape} {point : Array ℚ} {which : Nat} {c c' : Caches}
    {V : Caches → Prop} (hstep : ∀ node ∈ t.nodes, node.StepSound V) (hc : V c)
    (h : t.refuted point which c = .ok ((), c')) :
    V c' ∧ ∃ root, t.roots[which]? = some root ∧
      InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) ∧
      ∃ x, t.value (fun k => ((point[k]! : ℚ) : ℝ)) root = some x ∧ 0 < x := by
  unfold Tape.refuted at h
  dsimp only at h
  obtain ⟨u1, c1, hwf0, h1⟩ := M.bind_ok h
  obtain ⟨hwf1, hc1⟩ := M.lift_ok hwf0
  rw [hc1] at h1
  have hwf := Tape.wellFormed_ok hwf1
  cases hroot : t.roots[which]? with
  | none =>
    rw [hroot] at h1
    exact (M.throw_not_ok h1).elim
  | some root =>
    rw [hroot] at h1
    dsimp only at h1
    by_cases hsz : (point.size == t.inputs.size) = true
    swap
    · rw [if_neg hsz] at h1
      obtain ⟨_, _, hthrow, -⟩ := M.bind_ok h1
      exact (M.throw_not_ok hthrow).elim
    rw [if_pos hsz] at h1
    simp only [pure_bind] at h1
    have hsz' : point.size = t.inputs.size := by simpa using hsz
    obtain ⟨u2, c2, hloop, h2⟩ := M.bind_ok h1
    obtain ⟨⟨v, bad⟩, c3, heval, h3⟩ := M.bind_ok h2
    dsimp only at h3
    -- every value of the point lies in its input's range
    have hpoint : c2 = c ∧ ∀ i (h1 : i < point.size) (h2 : i < t.inputs.size),
        i < (point.zip t.inputs).zipIdx.size → t.inputs[i].range.has point[i] = true := by
      refine M.forIn_array_inv _ (fun k (_ : PUnit) c0 => c0 = c ∧
        ∀ i (h1 : i < point.size) (h2 : i < t.inputs.size), i < k →
          t.inputs[i].range.has point[i] = true)
        (point.zip t.inputs).zipIdx PUnit.unit u2 c c2 ?_ ?_ hloop
      · exact ⟨rfl, fun i _ _ hlt => absurd hlt (Nat.not_lt_zero i)⟩
      · intro i hi b ci s ci' hP hf
        obtain ⟨hci, hprev⟩ := hP
        have hi2 : i < point.size ∧ i < t.inputs.size := by
          have hi' := hi
          simp only [Array.size_zipIdx, Array.size_zip] at hi'
          omega
        obtain ⟨hip, hit⟩ := hi2
        simp only [Array.getElem_zipIdx, Array.getElem_zip, Nat.zero_add] at hf
        by_cases hhas : t.inputs[i].range.has point[i] = true
        · rw [if_pos hhas] at hf
          obtain ⟨hs, hci'⟩ := M.pure_ok (a := ForInStep.yield PUnit.unit) hf
          refine ⟨PUnit.unit, hs, by rw [hci', hci], ?_⟩
          intro i' h1 h2 hlt
          rcases Nat.lt_succ_iff_lt_or_eq.mp hlt with hlt | rfl
          · exact hprev i' h1 h2 hlt
          · exact hhas
        · rw [if_neg hhas] at hf
          obtain ⟨_, _, hthrow, -⟩ := M.bind_ok hf
          exact (M.throw_not_ok hthrow).elim
    obtain ⟨hc2, hhas⟩ := hpoint
    rw [hc2] at heval
    have hbox : InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) := by
      intro k hk
      have hk2 : k < t.inputs.size := by simpa using hk
      have hk1 : k < point.size := by omega
      have hh := hhas k hk1 hk2 (by simp; omega)
      simp only [Iv.has, Bool.and_eq_true, decide_eq_true_eq] at hh
      rw [getElem!_pos _ k hk, Array.getElem_map]
      show ((t.inputs[k].range.lo : ℚ) : ℝ) ≤ ((point[k]! : ℚ) : ℝ) ∧
        ((point[k]! : ℚ) : ℝ) ≤ ((t.inputs[k].range.hi : ℚ) : ℝ)
      rw [getElem!_pos point k hk1]
      exact ⟨by exact_mod_cast hh.1, by exact_mod_cast hh.2⟩
    have hpt : InBox (point.map Iv.pt) (fun k => ((point[k]! : ℚ) : ℝ)) := by
      intro k hk
      have hk1 : k < point.size := by simpa using hk
      rw [getElem!_pos _ k hk, Array.getElem_map]
      show ((point[k] : ℚ) : ℝ) ≤ ((point[k]! : ℚ) : ℝ) ∧
        ((point[k]! : ℚ) : ℝ) ≤ ((point[k] : ℚ) : ℝ)
      rw [getElem!_pos point k hk1]
      exact ⟨le_refl _, le_refl _⟩
    have hrmem : root ∈ t.roots := Array.mem_of_getElem? hroot
    have hrlt := hwf.roots root hrmem
    obtain ⟨-, hn2, hn3⟩ := Tape.needed_spec hwf #[root]
    obtain ⟨hcv, hev⟩ := Tape.eval_sound hwf hstep hn3 (by simpa using hsz') hc heval
    cases hb : bad[root]! with
    | some f =>
      rw [hb] at h3
      obtain ⟨_, _, hthrow, -⟩ := M.bind_ok h3
      exact (M.throw_not_ok hthrow).elim
    | none =>
      rw [hb] at h3
      dsimp only at h3
      by_cases hlo : v[root]!.lo > 0
      swap
      · rw [if_neg hlo] at h3
        exact (M.throw_not_ok h3).elim
      rw [if_pos hlo] at h3
      have hc3 : c' = c3 := (M.pure_ok h3).2
      rw [hc3]
      obtain ⟨x, hx, hxv⟩ := hev _ hpt root hrlt (hn2 root (by simp) hrlt) hb
      have hlo' : (0 : ℝ) < ((v[root]!.lo : ℚ) : ℝ) := by exact_mod_cast hlo
      exact ⟨hcv, root, rfl, hbox, x, hx, lt_of_lt_of_le hlo' hxv.1⟩

/-! ## The theorems

`Tape.proved_sound_exact` and `Tape.refuted_sound_exact` assume nothing: they are for a tape
with no `sqrt`, `pi`, `ln` or `exp` node, from any caches. `Tape.proved_sound` and
`Tape.refuted_sound` are for any tape. They assume, for each rounded node the tape has, the
statement in Trust.lean about the loop that node runs, and they start from valid caches. The
kernel starts from the empty caches, which are valid (`Caches.valid_empty`), and each
theorem hands valid caches to the next proof. -/

/-- A tape of exact nodes, proved. If `Tape.proved` succeeds, from any caches, then at every
point of the box (each input in its range) every root has a value, and the value is at most
zero. Nothing is assumed. -/
theorem Tape.proved_sound_exact {t : Tape} {p : Partition} {c c' : Caches}
    (hex : ∀ node ∈ t.nodes, node.Exact) (h : t.proved p c = .ok ((), c')) :
    ∀ ρ, InBox (t.inputs.map (·.range)) ρ →
      ∀ root ∈ t.roots, ∃ x, t.value ρ root = some x ∧ x ≤ 0 :=
  (Tape.proved_sound_of (V := fun _ => True) (fun node hn => (hex node hn).stepSound)
    True.intro h).2

/-- A tape of exact nodes, refuted. If `Tape.refuted` succeeds, from any caches, the point
lies in the box and the root it names has a value there that is above zero. Nothing is
assumed. -/
theorem Tape.refuted_sound_exact {t : Tape} {point : Array ℚ} {which : Nat} {c c' : Caches}
    (hex : ∀ node ∈ t.nodes, node.Exact) (h : t.refuted point which c = .ok ((), c')) :
    ∃ root, t.roots[which]? = some root ∧
      InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) ∧
      ∃ x, t.value (fun k => ((point[k]! : ℚ) : ℝ)) root = some x ∧ 0 < x :=
  (Tape.refuted_sound_of (V := fun _ => True) (fun node hn => (hex node hn).stepSound)
    True.intro h).2

/-- Any tape, proved. If `Tape.proved` succeeds from valid caches, then at every point of the
box every root has a value, and the value is at most zero. The caches stay valid.
`htrust` is the assumption of each rounded node the tape has. -/
theorem Tape.proved_sound {t : Tape} {p : Partition} {c c' : Caches}
    (htrust : ∀ node ∈ t.nodes, node.Trusted) (hc : c.Valid)
    (h : t.proved p c = .ok ((), c')) :
    c'.Valid ∧ ∀ ρ, InBox (t.inputs.map (·.range)) ρ →
      ∀ root ∈ t.roots, ∃ x, t.value ρ root = some x ∧ x ≤ 0 :=
  Tape.proved_sound_of (fun node hn => (htrust node hn).stepSound) hc h

/-- Any tape, refuted. If `Tape.refuted` succeeds from valid caches, the point lies in the
box and the root it names has a value there that is above zero. The caches stay valid.
`htrust` is the assumption of each rounded node the tape has. -/
theorem Tape.refuted_sound {t : Tape} {point : Array ℚ} {which : Nat} {c c' : Caches}
    (htrust : ∀ node ∈ t.nodes, node.Trusted) (hc : c.Valid)
    (h : t.refuted point which c = .ok ((), c')) :
    c'.Valid ∧ ∃ root, t.roots[which]? = some root ∧
      InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) ∧
      ∃ x, t.value (fun k => ((point[k]! : ℚ) : ℝ)) root = some x ∧ 0 < x :=
  Tape.refuted_sound_of (fun node hn => (htrust node hn).stepSound) hc h

/-- The three assumptions together give every node's. -/
theorem Node.trusted_of_specs (h1 : IsqrtSpec) (h2 : OddSeriesSpec) (h3 : ExpAtSpec)
    (node : Node) : node.Trusted := by
  cases node <;> first | exact True.intro | exact h1 | exact h2 | exact h3

end Petra
