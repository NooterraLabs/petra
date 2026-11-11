/-
The walk over a tape. `Tape.wellFormed` checks that a node reads only earlier nodes,
`Tape.needed` marks what the roots read, and `Tape.eval` runs one step per marked node. The
theorem here: after `Tape.eval`, the enclosure of every marked node that did not fail holds
that node's value at every point of the box.
-/
import PetraProofs.Step
import PetraProofs.Pick

namespace Petra

/-! ## What `wellFormed` checks -/

/-- A node reads only nodes before it, an input node names an input, and a root names a
node. -/
structure Tape.WF (t : Tape) : Prop where
  reads : ∀ i (h : i < t.nodes.size), ∀ j ∈ t.nodes[i].reads, j < i
  input : ∀ i (h : i < t.nodes.size) (k : Nat), t.nodes[i] = .s k → k < t.inputs.size
  roots : ∀ r ∈ t.roots, r < t.nodes.size

theorem Tape.wellFormed_ok {t : Tape} (h : t.wellFormed = .ok ()) : t.WF := by
  unfold Tape.wellFormed at h
  dsimp only at h
  split at h
  · exact (Except.throw_bind_ne_ok h).elim
  rw [pure_bind] at h
  obtain ⟨u, hloop, hroots⟩ := Except.bind_ok h
  have hinv : ∀ i (hi : i < t.nodes.size), i < t.nodes.zipIdx.size →
      (∀ j ∈ t.nodes[i].reads, j < i) ∧ ∀ k', t.nodes[i] = .s k' → k' < t.inputs.size := by
    refine Except.forIn_array_inv _ (fun k (_ : PUnit) => ∀ i (hi : i < t.nodes.size), i < k →
      (∀ j ∈ t.nodes[i].reads, j < i) ∧ ∀ k', t.nodes[i] = .s k' → k' < t.inputs.size)
      t.nodes.zipIdx PUnit.unit u ?_ ?_ hloop
    · intro i _ hlt
      exact absurd hlt (Nat.not_lt_zero i)
    · intro j hj b s hP hf
      have hj' : j < t.nodes.size := by simpa using hj
      simp only [Array.getElem_zipIdx, Nat.zero_add] at hf
      split at hf
      swap
      · exact (Except.throw_bind_ne_ok hf).elim
      rename_i hall
      rw [pure_bind] at hf
      have hreads : ∀ x ∈ t.nodes[j].reads, x < j := fun x hx =>
        of_decide_eq_true (Array.all_eq_true_iff_forall_mem.mp hall x hx)
      have hs : s = .yield PUnit.unit ∧ ∀ k', t.nodes[j] = .s k' → k' < t.inputs.size := by
        split at hf
        · rename_i k' hnode
          split at hf
          · rename_i hk
            have hf' : (Except.ok (ForInStep.yield PUnit.unit) :
                Except String (ForInStep PUnit)) = .ok s := hf
            cases hf'
            refine ⟨rfl, fun k'' hk'' => ?_⟩
            rw [hnode] at hk''
            cases hk''
            exact hk
          · exact (Except.throw_bind_ne_ok hf).elim
        · rename_i hnot
          have hf' : (Except.ok (ForInStep.yield PUnit.unit) :
              Except String (ForInStep PUnit)) = .ok s := hf
          cases hf'
          exact ⟨rfl, fun k'' hk'' => absurd hk'' (hnot k'')⟩
      refine ⟨PUnit.unit, hs.1, ?_⟩
      intro i hi hlt
      rcases Nat.lt_succ_iff_lt_or_eq.mp hlt with hlt | rfl
      · exact hP i hi hlt
      · exact ⟨hreads, hs.2⟩
  refine ⟨fun i hi => (hinv i hi (by simpa using hi)).1,
    fun i hi => (hinv i hi (by simpa using hi)).2, ?_⟩
  split at hroots
  · rename_i hall
    intro r hr
    exact of_decide_eq_true (Array.all_eq_true_iff_forall_mem.mp hall r hr)
  · have h' : (Except.error _ : Except String Unit) = .ok () := hroots
    cases h'

/-! ## What `needed` marks -/

theorem getElem!_setIfInBounds {α : Type} [Inhabited α] (a : Array α) (i j : Nat) (x : α) :
    (a.setIfInBounds i x)[j]! = if i = j ∧ j < a.size then x else a[j]! := by
  by_cases hj : j < a.size
  · rw [getElem!_pos (a.setIfInBounds i x) j (by simpa using hj), getElem!_pos a j hj]
    by_cases hij : i = j
    · subst hij
      simp [hj]
    · rw [if_neg (fun h => hij h.1)]
      exact Array.getElem_setIfInBounds_ne hj hij
  · rw [getElem!_neg (a.setIfInBounds i x) j (by simpa using hj), getElem!_neg a j hj]
    simp [hj]

/-- Marking keeps the size, and marks an index when it was marked or is listed. -/
theorem mark_spec : ∀ (ids : List Nat) (need : Array Bool),
    (ids.foldl (fun need i => need.setIfInBounds i true) need).size = need.size ∧
    ∀ j, (ids.foldl (fun need i => need.setIfInBounds i true) need)[j]! = true ↔
      (need[j]! = true ∨ (j ∈ ids ∧ j < need.size)) := by
  intro ids
  induction ids with
  | nil =>
    intro need
    simp
  | cons i ids ih =>
    intro need
    obtain ⟨h1, h2⟩ := ih (need.setIfInBounds i true)
    rw [List.foldl_cons]
    refine ⟨by rw [h1]; simp, fun j => ?_⟩
    rw [h2 j, getElem!_setIfInBounds]
    simp only [Array.size_setIfInBounds, List.mem_cons]
    by_cases hij : i = j
    · subst hij
      by_cases hj : i < need.size <;> simp [hj]
    · have hji : j ≠ i := fun h => hij h.symm
      simp [hij, hji]

/-- `needed` marks every root, and with a marked node every node it reads. -/
theorem Tape.needed_spec {t : Tape} (hwf : t.WF) (roots : Array Nat) :
    (t.needed roots).size = t.nodes.size ∧
    (∀ r ∈ roots, r < t.nodes.size → (t.needed roots)[r]! = true) ∧
    (∀ i (hi : i < t.nodes.size), (t.needed roots)[i]! = true →
      ∀ j ∈ t.nodes[i].reads, (t.needed roots)[j]! = true) := by
  let P : Nat → Array Bool → Prop := fun k need =>
    need.size = t.nodes.size ∧
    (∀ r ∈ roots, r < t.nodes.size → need[r]! = true) ∧
    (∀ i (hi : i < t.nodes.size), t.nodes.size - k ≤ i → need[i]! = true →
      ∀ j ∈ t.nodes[i].reads, need[j]! = true)
  have key : P t.nodes.size (t.needed roots) := by
    unfold Tape.needed
    dsimp only
    rw [bind_pure]
    refine Id.forIn_range_inv _ P _ _ ?_ ?_
    · -- before the loop: the roots are marked
      obtain ⟨m1, m2⟩ := mark_spec roots.toList (Array.replicate t.nodes.size false)
      rw [Array.foldl_toList] at m1 m2
      refine ⟨by rw [m1]; simp, fun r hr hlt => ?_, fun i hi hle => by omega⟩
      exact (m2 r).mpr (Or.inr ⟨Array.mem_toList_iff.mpr hr, by simpa using hlt⟩)
    · -- one round: node `size - 1 - k`, after every later node
      intro k hk need hP
      obtain ⟨hsz, hroots, hclos⟩ := hP
      have hi : t.nodes.size - 1 - k < t.nodes.size := by omega
      have e : t.nodes[t.nodes.size - 1 - k]! = t.nodes[t.nodes.size - 1 - k] :=
        getElem!_pos t.nodes _ hi
      by_cases hn : need[t.nodes.size - 1 - k]! = true
      · obtain ⟨m1, m2⟩ := mark_spec t.nodes[t.nodes.size - 1 - k]!.reads.toList need
        rw [Array.foldl_toList] at m1 m2
        refine ⟨Array.foldl (fun need i => need.setIfInBounds i true) need
            t.nodes[t.nodes.size - 1 - k]!.reads, by rw [if_pos hn]; rfl, by rw [m1]; exact hsz,
          fun r hr hlt => (m2 r).mpr (Or.inl (hroots r hr hlt)), ?_⟩
        intro i' hi' hle hmark j hj
        rcases Nat.eq_or_lt_of_le (show t.nodes.size - 1 - k ≤ i' by omega) with heq | hlt
        · subst heq
          refine (m2 j).mpr (Or.inr ⟨Array.mem_toList_iff.mpr (by rw [e]; exact hj), ?_⟩)
          rw [hsz]
          exact lt_trans (hwf.reads _ hi j hj) hi
        · have hold : need[i']! = true := by
            rcases (m2 i').mp hmark with h | ⟨h, _⟩
            · exact h
            · rw [e] at h
              have := hwf.reads _ hi i' (Array.mem_toList_iff.mp h)
              omega
          exact (m2 j).mpr (Or.inl (hclos i' hi' (by omega) hold j hj))
      · refine ⟨need, by rw [if_neg hn]; rfl, hsz, hroots, ?_⟩
        intro i' hi' hle hmark j hj
        rcases Nat.eq_or_lt_of_le (show t.nodes.size - 1 - k ≤ i' by omega) with heq | hlt
        · subst heq
          exact absurd hmark hn
        · exact hclos i' hi' (by omega) hmark j hj
  obtain ⟨h1, h2, h3⟩ := key
  exact ⟨h1, h2, fun i hi => h3 i hi (by omega)⟩

/-! ## The walk -/

theorem Tape.value_eq {t : Tape} {ρ : Nat → ℝ} {i : Nat} (hi : i < t.nodes.size) :
    t.value ρ i =
      t.nodes[i].value t.inputs.size ρ (fun j => if _h : j < i then t.value ρ j else none) := by
  rw [Tape.value, dif_pos hi]

/-- After `k` rounds of `Tape.eval` there is one entry for each node walked, and the
enclosure of each marked node that did not fail holds its value at every point of the box. -/
def EvalInv (t : Tape) (box : Array Iv) (need : Array Bool) (k : Nat)
    (bad : Array (Option Failure)) (v : Array Iv) : Prop :=
  v.size = k ∧ bad.size = k ∧
  ∀ ρ, InBox box ρ → ∀ i, i < k → need[i]! = true → bad[i]! = none →
    ∃ x, t.value ρ i = some x ∧ v[i]!.Holds x

theorem EvalInv.push_ok {t : Tape} {box : Array Iv} {need : Array Bool} {k : Nat}
    {bad : Array (Option Failure)} {v : Array Iv} {y : Iv} (h : EvalInv t box need k bad v)
    (hy : need[k]! = true → ∀ ρ, InBox box ρ → ∃ x, t.value ρ k = some x ∧ y.Holds x) :
    EvalInv t box need (k + 1) (bad.push none) (v.push y) := by
  obtain ⟨h1, h2, h3⟩ := h
  subst h1
  refine ⟨by simp, by simp [h2], ?_⟩
  intro ρ hρ i hi hn hb
  rcases Nat.lt_succ_iff_lt_or_eq.mp hi with hlt | rfl
  · rw [getElem!_push_lt bad none (by omega)] at hb
    rw [getElem!_push_lt v y hlt]
    exact h3 ρ hρ i hlt hn hb
  · rw [getElem!_push_eq]
    exact hy hn ρ hρ

theorem EvalInv.push_err {t : Tape} {box : Array Iv} {need : Array Bool} {k : Nat}
    {bad : Array (Option Failure)} {v : Array Iv} (y : Iv) (f : Failure)
    (h : EvalInv t box need k bad v) :
    EvalInv t box need (k + 1) (bad.push (some f)) (v.push y) := by
  obtain ⟨h1, h2, h3⟩ := h
  subst h1
  refine ⟨by simp, by simp [h2], ?_⟩
  intro ρ hρ i hi hn hb
  rcases Nat.lt_succ_iff_lt_or_eq.mp hi with hlt | rfl
  · rw [getElem!_push_lt bad (some f) (by omega)] at hb
    rw [getElem!_push_lt v y hlt]
    exact h3 ρ hρ i hlt hn hb
  · rw [← h2, getElem!_push_eq] at hb
    cases hb

theorem Tape.eval_sound {t : Tape} {box : Array Iv} {need : Array Bool} {c c' : Caches}
    {v : Array Iv} {bad : Array (Option Failure)}
    (hwf : t.WF) (htrust : ∀ node ∈ t.nodes, node.Trusted)
    (hneed : ∀ i (hi : i < t.nodes.size), need[i]! = true →
      ∀ j ∈ t.nodes[i].reads, need[j]! = true)
    (hsize : box.size = t.inputs.size) (hc : c.Valid)
    (h : t.eval box need c = .ok ((v, bad), c')) :
    c'.Valid ∧ ∀ ρ, InBox box ρ → ∀ i, i < t.nodes.size → need[i]! = true → bad[i]! = none →
      ∃ x, t.value ρ i = some x ∧ v[i]!.Holds x := by
  unfold Tape.eval at h
  dsimp only at h
  obtain ⟨r, c1, hloop, hret⟩ := M.bind_ok h
  have hinv : c1.Valid ∧ EvalInv t box need t.nodes.zipIdx.size r.1 r.2 := by
    refine M.forIn_array_inv _
      (fun k (r : MProd (Array (Option Failure)) (Array Iv)) c =>
        c.Valid ∧ EvalInv t box need k r.1 r.2) t.nodes.zipIdx _ r c c1 ?_ ?_ hloop
    · exact ⟨hc, by simp [EvalInv]⟩
    · intro j hj b c s c' hP hf
      have hj' : j < t.nodes.size := by simpa using hj
      obtain ⟨hcv, hE⟩ := hP
      simp only [Array.getElem_zipIdx, Nat.zero_add] at hf
      -- the enclosure of every node this node reads holds that node's value
      have hreads : need[j]! = true → ∀ ρ, InBox box ρ → ∀ i ∈ t.nodes[j].reads,
          b.fst[i]! = none → ∃ x, (fun i => if _h : i < j then t.value ρ i else none) i = some x ∧
            b.snd[i]!.Holds x := by
        intro hn ρ hρ i hi hb
        have hlt := hwf.reads j hj' i hi
        obtain ⟨x, hx, hxv⟩ := hE.2.2 ρ hρ i hlt (hneed j hj' hn i hi) hb
        refine ⟨x, ?_, hxv⟩
        show (if _h : i < j then t.value ρ i else none) = some x
        rw [dif_pos hlt]
        exact hx
      have htr := htrust t.nodes[j] (Array.mem_of_getElem (h := hj') rfl)
      have hin : ∀ k, t.nodes[j] = .s k → k < box.size := fun k hk => by
        rw [hsize]
        exact hwf.input j hj' k hk
      have hval : ∀ ρ, t.value ρ j = t.nodes[j].value t.inputs.size ρ
          (fun i => if _h : i < j then t.value ρ i else none) := fun ρ => Tape.value_eq hj'
      generalize t.nodes[j] = node at hf hreads htr hin hval
      by_cases hn : need[j]! = true
      · rw [if_pos hn] at hf
        cases node with
        | pick cases =>
          dsimp only at hf
          rw [pure_bind] at hf
          cases hpick : pick b.snd b.fst j cases with
          | ok y =>
            rw [hpick] at hf
            obtain ⟨rfl, rfl⟩ := M.pure_ok
              (a := ForInStep.yield (MProd.mk (b.fst.push none) (b.snd.push y))) hf
            refine ⟨_, rfl, hcv, hE.push_ok (fun _ ρ hρ => ?_)⟩
            rw [hval ρ]
            exact pick_sound (fun i hi hb => hreads hn ρ hρ i hi hb) hpick
          | error f =>
            rw [hpick] at hf
            obtain ⟨rfl, rfl⟩ := M.pure_ok
              (a := ForInStep.yield (MProd.mk (b.fst.push (some f)) (b.snd.push default))) hf
            exact ⟨_, rfl, hcv, hE.push_err default f⟩
        | _ =>
          dsimp only at hf
          generalize hearly : earliest b.fst _ = early at hf
          cases early with
          | some f =>
            -- a node it reads has failed
            obtain ⟨rfl, rfl⟩ := M.pure_ok
              (a := ForInStep.yield (MProd.mk (b.fst.push (some f)) (b.snd.push default))) hf
            exact ⟨_, rfl, hcv, hE.push_err default f⟩
          | none =>
            -- the step of the interval rule
            obtain ⟨r1, c2, htc, hrest⟩ := M.bind_ok hf
            rw [pure_bind] at hrest
            rcases M.tryCatch_ok htc with hok | ⟨e, -, hh⟩
            · obtain ⟨a, c3, henc, hok2⟩ := M.bind_ok hok
              obtain ⟨y, c4, hfit, hok3⟩ := M.bind_ok hok2
              obtain ⟨hfit', rfl⟩ := M.lift_ok hfit
              have hya := fits_ok hfit'
              subst hya
              obtain ⟨rfl, rfl⟩ := M.pure_ok
                (a := (MProd.mk PUnit.unit (Except.ok y) : MProd PUnit (Except Failure Iv))) hok3
              obtain ⟨rfl, rfl⟩ := M.pure_ok
                (a := ForInStep.yield (MProd.mk (b.fst.push none) (b.snd.push y))) hrest
              refine ⟨_, rfl, Node.enclose_valid htr hcv henc, hE.push_ok (fun _ ρ hρ => ?_)⟩
              have hbad := earliest_none hearly
              obtain ⟨-, x, hx, hxv⟩ := Node.enclose_sound htr hρ hin
                (fun i hi => hreads hn ρ hρ i hi (hbad i hi)) hcv henc
              rw [hsize] at hx
              exact ⟨x, by rw [hval ρ]; exact hx, hxv⟩
            · obtain ⟨rfl, rfl⟩ := M.pure_ok
                (a := (MProd.mk PUnit.unit (Except.error ⟨j, e⟩) :
                  MProd PUnit (Except Failure Iv))) hh
              obtain ⟨rfl, rfl⟩ := M.pure_ok
                (a := ForInStep.yield (MProd.mk (b.fst.push (some ⟨j, e⟩)) (b.snd.push default)))
                hrest
              exact ⟨_, rfl, hcv, hE.push_err default _⟩
      · -- a node no root reads: no step runs
        rw [if_neg hn] at hf
        obtain ⟨rfl, rfl⟩ := M.pure_ok
          (a := ForInStep.yield (MProd.mk (b.fst.push none) (b.snd.push default))) hf
        exact ⟨_, rfl, hcv, hE.push_ok (fun hn' => absurd hn' hn)⟩
  obtain ⟨hrv, hrc⟩ := M.pure_ok (a := (r.snd, r.fst)) hret
  cases hrv
  subst hrc
  obtain ⟨hcv, -, -, hE⟩ := hinv
  exact ⟨hcv, fun ρ hρ i hi => hE ρ hρ i (by simpa using hi)⟩

end Petra
