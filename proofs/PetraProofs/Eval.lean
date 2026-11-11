/-
The walk over a tape. `Tape.wellFormed` checks that a node reads only earlier nodes,
`Tape.needed` marks what the roots read, and `Tape.eval` runs one step per marked node. The
theorem here: after `Tape.eval`, the enclosure of every marked node that has no failure holds
that node's value at every point of the box.

A step has a price, and the walk gives up an enclosure after the last node that reads it.
Neither is trusted. A step that cannot pay returns a failure. A node whose enclosure is
given up is marked as failed, so the theorem says nothing of it, whatever `Tape.last` holds.
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

/-- After `k` nodes of the walk there is one entry for each node walked, and the enclosure
of each marked node that has no failure holds its value at every point of the box. A node
whose enclosure was given up has a failure, so this says nothing of it. -/
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

/-- Giving up an enclosure keeps the invariant: the node is marked as failed, so nothing is
said of it any more, and every other entry is as it was. -/
theorem EvalInv.give_up {t : Tape} {box : Array Iv} {need : Array Bool} {k : Nat}
    {bad : Array (Option Failure)} {v : Array Iv} (j : Nat) (y : Iv) (f : Failure)
    (h : EvalInv t box need k bad v) :
    EvalInv t box need k (bad.setIfInBounds j (some f)) (v.setIfInBounds j y) := by
  obtain ⟨h1, h2, h3⟩ := h
  refine ⟨by simp [h1], by simp [h2], ?_⟩
  intro ρ hρ i hi hn hb
  rw [getElem!_setIfInBounds] at hb
  by_cases hji : j = i
  · subst hji
    rw [if_pos ⟨rfl, by omega⟩] at hb
    cases hb
  · rw [if_neg (fun hh => hji hh.1)] at hb
    rw [getElem!_setIfInBounds, if_neg (fun hh => hji hh.1)]
    exact h3 ρ hρ i hi hn hb

/-- `Walk.keep` adds one entry. When it keeps an enclosure, that enclosure is the outcome's. -/
theorem EvalInv.keep {t : Tape} {box : Array Iv} {need : Array Bool} {k : Nat} {w : Walk}
    {x : Except Failure Iv} (h : EvalInv t box need k w.bad w.v)
    (hx : ∀ y, x = .ok y → need[k]! = true → ∀ ρ, InBox box ρ →
      ∃ z, t.value ρ k = some z ∧ y.Holds z) :
    EvalInv t box need (k + 1) (w.keep k x).bad (w.keep k x).v := by
  cases x with
  | error f => exact h.push_err default f
  | ok y =>
    unfold Walk.keep
    dsimp only
    split_ifs
    · exact h.push_err default _
    · exact h.push_ok (hx y rfl)

/-- `Walk.release` keeps the invariant, whatever `last` holds. -/
theorem EvalInv.release {t : Tape} {box : Array Iv} {need : Array Bool} {k : Nat}
    (last : Array Nat) (self : Nat) (ids : Array Nat) (w : Walk)
    (h : EvalInv t box need k w.bad w.v) :
    EvalInv t box need k (w.release last self ids).bad (w.release last self ids).v := by
  unfold Walk.release
  rw [← Array.foldl_toList]
  generalize ids.toList = l
  induction l generalizing w with
  | nil => exact h
  | cons a l ih =>
    rw [List.foldl_cons]
    apply ih
    split_ifs
    · exact h.give_up a default _
    · exact h

/-! ## One step with its price -/

/-- A pick's step with its price returns an enclosure only when `pick` does, and then it is
`pick`'s. -/
theorem pickPriced_ok {v : Array Iv} {bad : Array (Option Failure)} {self : Nat}
    {cases : Array (Option Cond × Nat)} {work : Nat} {y : Iv}
    (h : (pickPriced v bad self cases work).1 = .ok y) : pick v bad self cases = .ok y := by
  unfold pickPriced at h
  cases hw : pickWork v cases work with
  | none =>
    rw [hw] at h
    dsimp only at h
    cases h
  | some cost =>
    rw [hw] at h
    dsimp only at h
    by_cases hlt : work < cost
    · rw [if_pos hlt] at h
      dsimp only at h
      cases h
    · rw [if_neg hlt] at h
      exact h

theorem Except.mapError_ok {ε ε' α : Type} {f : ε → ε'} {x : Except ε α} {y : α}
    (h : x.mapError f = .ok y) : x = .ok y := by
  cases x with
  | error e => simp [Except.mapError] at h
  | ok a => simpa [Except.mapError] using h

/-- The fold of a sum or a product with its price returns an enclosure only when the fold of
`Node.enclose` does, and then it is that fold's. -/
theorem folded_ok {op : Iv → Iv → Iv} {price : Nat → Nat → Nat} {v : Array Iv} :
    ∀ (l : List Nat) (acc : Iv) (work : Nat) (y : Iv),
      (folded op price v l acc work).1 = .ok y →
      l.foldlM (fun acc i => fits (op acc v[i]!)) acc = .ok y := by
  intro l
  induction l with
  | nil =>
    intro acc work y h
    unfold folded at h
    dsimp only at h
    cases h
    rfl
  | cons i rest ih =>
    intro acc work y h
    unfold folded at h
    dsimp only at h
    by_cases hw : work < price acc.words v[i]!.words
    · rw [if_pos hw] at h
      dsimp only at h
      cases h
    · rw [if_neg hw] at h
      rw [List.foldlM_cons]
      show (fits (op acc v[i]!) >>= fun next =>
        rest.foldlM (fun acc i => fits (op acc v[i]!)) next) = .ok y
      cases hfit : fits (op acc v[i]!) with
      | error why =>
        rw [hfit] at h
        dsimp only at h
        cases h
      | ok next =>
        rw [hfit] at h
        dsimp only at h
        exact ih next _ y h

/-- What the walk needs of the step of a node other than a pick, whichever enclosure it
rounds from: it keeps the property `V` of the caches, and an enclosure it returns holds the
node's value. Running out of work, or of enclosures to try, returns no enclosure. -/
theorem Node.tries_sound {node : Node} {box v : Array Iv} {self : Nat} {V : Caches → Prop}
    (hstep : node.StepSound V) :
    ∀ (extras : List Nat) (work : Nat) (c c' : Caches) (r : Except Failure Iv × Nat),
      V c → node.tries box v self extras work c = .ok (r, c') →
      V c' ∧ ∀ y, r.1 = .ok y → ∀ (ρ : Nat → ℝ) (val : Nat → Option ℝ), InBox box ρ →
        (∀ k, node = .s k → k < box.size) →
        (∀ i ∈ node.reads, ∃ x, val i = some x ∧ v[i]!.Holds x) →
        ∃ x, node.value box.size ρ val = some x ∧ y.Holds x := by
  intro extras
  induction extras with
  | nil =>
    intro work c c' r hc h
    unfold Node.tries at h
    obtain ⟨rfl, rfl⟩ := M.pure_ok h
    exact ⟨hc, fun y hy => by cases hy⟩
  | cons extra rest ih =>
    intro work c c' r hc h
    unfold Node.tries at h
    obtain ⟨s, c1, hget, h1⟩ := M.bind_ok h
    obtain ⟨rfl, rfl⟩ := M.get_ok hget
    dsimp only at h1
    split_ifs at h1 with hw
    · obtain ⟨rfl, rfl⟩ := M.pure_ok h1
      exact ⟨hc, fun y hy => by cases hy⟩
    · rcases M.tryCatch_ok h1 with hok | ⟨e, -, hh⟩
      · obtain ⟨a, c3, henc, hok2⟩ := M.bind_ok hok
        obtain ⟨y, c4, hfit, hok3⟩ := M.bind_ok hok2
        obtain ⟨hfit', rfl⟩ := M.lift_ok hfit
        have hya := fits_ok hfit'
        subst hya
        obtain ⟨rfl, rfl⟩ := M.pure_ok hok3
        obtain ⟨hV, hsound⟩ := hstep _ _ _ _ _ _ hc henc
        refine ⟨hV, fun y' hy' ρ val hρ hs hval => ?_⟩
        cases hy'
        exact hsound ρ val hρ hs hval
      · split_ifs at hh
        · exact ih _ _ _ _ hc hh
        · obtain ⟨rfl, rfl⟩ := M.pure_ok hh
          exact ⟨hc, fun y hy => by cases hy⟩

/-- One node of the walk keeps the invariant, and the property `V` of the caches. -/
theorem Tape.visit_sound {t : Tape} {box : Array Iv} {need : Array Bool} {last : Array Nat}
    {V : Caches → Prop} (hwf : t.WF)
    (hneed : ∀ i (hi : i < t.nodes.size), need[i]! = true →
      ∀ j ∈ t.nodes[i].reads, need[j]! = true)
    (hsize : box.size = t.inputs.size) {j : Nat} (hj : j < t.nodes.size)
    (hstep : t.nodes[j].StepSound V) {w w' : Walk} {c c' : Caches} (hc : V c)
    (hE : EvalInv t box need j w.bad w.v)
    (h : Tape.visit box need last t.nodes[j] j w c = .ok (w', c')) :
    V c' ∧ EvalInv t box need (j + 1) w'.bad w'.v := by
  -- the enclosure of every node this node reads, if it has no failure, holds that node's value
  have hreads : need[j]! = true → ∀ ρ, InBox box ρ → ∀ i ∈ t.nodes[j].reads,
      w.bad[i]! = none → ∃ x, (fun i => if _h : i < j then t.value ρ i else none) i = some x ∧
        w.v[i]!.Holds x := by
    intro hn ρ hρ i hi hb
    have hlt := hwf.reads j hj i hi
    obtain ⟨x, hx, hxv⟩ := hE.2.2 ρ hρ i hlt (hneed j hj hn i hi) hb
    refine ⟨x, ?_, hxv⟩
    show (if _h : i < j then t.value ρ i else none) = some x
    rw [dif_pos hlt]
    exact hx
  have hin : ∀ k, t.nodes[j] = .s k → k < box.size := fun k hk => by
    rw [hsize]
    exact hwf.input j hj k hk
  have hval : ∀ ρ, t.value ρ j = t.nodes[j].value t.inputs.size ρ
      (fun i => if _h : i < j then t.value ρ i else none) := fun ρ => Tape.value_eq hj
  generalize t.nodes[j] = node at h hreads hstep hin hval
  unfold Tape.visit at h
  by_cases hn : need[j]! = true
  · rw [if_pos hn] at h
    obtain ⟨⟨x, work⟩, c1, hp, hrest⟩ := M.bind_ok h
    dsimp only at hrest
    -- what the priced step gives: `V` of the caches, and an enclosure that holds the value
    have key : V c1 ∧ ∀ y, x = .ok y → ∀ ρ, InBox box ρ →
        ∃ z, t.value ρ j = some z ∧ y.Holds z := by
      cases node with
      | pick cases =>
        unfold Node.priced at hp
        dsimp only at hp
        obtain ⟨hr, rfl⟩ := M.pure_ok hp
        refine ⟨hc, fun y hy ρ hρ => ?_⟩
        have hpick : pick w.v w.bad j cases = .ok y := by
          apply pickPriced_ok (work := w.work)
          rw [← hr]
          exact hy
        rw [hval ρ]
        exact pick_sound (fun i hi hb => hreads hn ρ hρ i hi hb) hpick
      | add a =>
        unfold Node.priced at hp
        dsimp only at hp
        generalize hearly : earliest w.bad _ = early at hp
        cases early with
        | some f =>
          obtain ⟨hr, rfl⟩ := M.pure_ok hp
          refine ⟨hc, fun y hy => ?_⟩
          cases hr
          cases hy
        | none =>
          obtain ⟨hr, hcc⟩ := M.pure_ok hp
          refine ⟨by rw [hcc]; exact hc, fun y hy ρ hρ => ?_⟩
          -- the sum paid for term by term is the sum of `Node.enclose`
          have hfold : a.foldlM (fun acc i => fits (acc.add w.v[i]!)) (Iv.pt 0) = .ok y := by
            rw [← Array.foldlM_toList]
            apply folded_ok (op := Iv.add) (price := addWork) _ _ w.work
            apply Except.mapError_ok (f := fun why => (⟨j, why⟩ : Failure))
            rw [← hy]
            exact (congrArg Prod.fst hr).symm
          have henc : (Node.add a).enclose box w.v 0 c = .ok (y, c) := by
            show (liftM (m := Except String)
              (a.foldlM (fun acc i => fits (acc.add w.v[i]!)) (Iv.pt 0)) : M Iv) c = .ok (y, c)
            rw [hfold]
            rfl
          obtain ⟨-, hsound⟩ := hstep _ _ _ _ _ _ hc henc
          have hbad := earliest_none hearly
          obtain ⟨z, hz, hzv⟩ := hsound ρ _ hρ hin
            (fun i hi => hreads hn ρ hρ i hi (hbad i hi))
          rw [hsize] at hz
          exact ⟨z, by rw [hval ρ]; exact hz, hzv⟩
      | mul a =>
        unfold Node.priced at hp
        dsimp only at hp
        generalize hearly : earliest w.bad _ = early at hp
        cases early with
        | some f =>
          obtain ⟨hr, rfl⟩ := M.pure_ok hp
          refine ⟨hc, fun y hy => ?_⟩
          cases hr
          cases hy
        | none =>
          obtain ⟨hr, hcc⟩ := M.pure_ok hp
          refine ⟨by rw [hcc]; exact hc, fun y hy ρ hρ => ?_⟩
          have hfold : a.foldlM (fun acc i => fits (acc.mul w.v[i]!)) (Iv.pt 1) = .ok y := by
            rw [← Array.foldlM_toList]
            apply folded_ok (op := Iv.mul) (price := mulWork) _ _ w.work
            apply Except.mapError_ok (f := fun why => (⟨j, why⟩ : Failure))
            rw [← hy]
            exact (congrArg Prod.fst hr).symm
          have henc : (Node.mul a).enclose box w.v 0 c = .ok (y, c) := by
            show (liftM (m := Except String)
              (a.foldlM (fun acc i => fits (acc.mul w.v[i]!)) (Iv.pt 1)) : M Iv) c = .ok (y, c)
            rw [hfold]
            rfl
          obtain ⟨-, hsound⟩ := hstep _ _ _ _ _ _ hc henc
          have hbad := earliest_none hearly
          obtain ⟨z, hz, hzv⟩ := hsound ρ _ hρ hin
            (fun i hi => hreads hn ρ hρ i hi (hbad i hi))
          rw [hsize] at hz
          exact ⟨z, by rw [hval ρ]; exact hz, hzv⟩
      | _ =>
        unfold Node.priced at hp
        dsimp only at hp
        generalize hearly : earliest w.bad _ = early at hp
        cases early with
        | some f =>
          obtain ⟨hr, rfl⟩ := M.pure_ok hp
          refine ⟨hc, fun y hy => ?_⟩
          cases hr
          cases hy
        | none =>
          obtain ⟨hV, hsound⟩ := Node.tries_sound hstep _ _ _ _ _ hc hp
          refine ⟨hV, fun y hy ρ hρ => ?_⟩
          have hbad := earliest_none hearly
          obtain ⟨z, hz, hzv⟩ := hsound y hy ρ _ hρ hin
            (fun i hi => hreads hn ρ hρ i hi (hbad i hi))
          rw [hsize] at hz
          exact ⟨z, by rw [hval ρ]; exact hz, hzv⟩
    obtain ⟨hw', hc'⟩ := M.pure_ok hrest
    rw [hw', hc']
    refine ⟨key.1, EvalInv.release _ _ _ _ (EvalInv.keep (w := { w with work := work }) hE ?_)⟩
    intro y hy _ ρ hρ
    exact key.2 y hy ρ hρ
  · -- a node no root reads: no step runs
    rw [if_neg hn] at h
    obtain ⟨rfl, rfl⟩ := M.pure_ok h
    exact ⟨hc, hE.push_ok (fun hn' => absurd hn' hn)⟩

/-- After `Tape.eval`, the enclosure of every marked node that has no failure holds that
node's value at every point of the box. `V` is a property of the caches that every step of
the tape keeps: see `Node.StepSound`. The work left and the words held play no part. -/
theorem Tape.eval_sound {t : Tape} {box : Array Iv} {need : Array Bool} {last : Array Nat}
    {work : Nat} {c c' : Caches} {w : Walk} {V : Caches → Prop}
    (hwf : t.WF) (hstep : ∀ node ∈ t.nodes, node.StepSound V)
    (hneed : ∀ i (hi : i < t.nodes.size), need[i]! = true →
      ∀ j ∈ t.nodes[i].reads, need[j]! = true)
    (hsize : box.size = t.inputs.size) (hc : V c)
    (h : t.eval box need last work c = .ok (w, c')) :
    V c' ∧ ∀ ρ, InBox box ρ → ∀ i, i < t.nodes.size → need[i]! = true → w.bad[i]! = none →
      ∃ x, t.value ρ i = some x ∧ w.v[i]!.Holds x := by
  unfold Tape.eval at h
  dsimp only at h
  obtain ⟨r, c1, hloop, hret⟩ := M.bind_ok h
  have hinv : V c1 ∧ EvalInv t box need t.nodes.zipIdx.size r.bad r.v := by
    refine M.forIn_array_inv _
      (fun k (r : Walk) c => V c ∧ EvalInv t box need k r.bad r.v) t.nodes.zipIdx _ r c c1 ?_ ?_ hloop
    · exact ⟨hc, by simp [EvalInv]⟩
    · intro j hj b c s c' hP hf
      have hj' : j < t.nodes.size := by simpa using hj
      obtain ⟨hcv, hE⟩ := hP
      simp only [Array.getElem_zipIdx, Nat.zero_add] at hf
      obtain ⟨b', c2, hv, hy⟩ := M.bind_ok hf
      obtain ⟨rfl, rfl⟩ := M.pure_ok (a := ForInStep.yield b') hy
      obtain ⟨hV, hE'⟩ := Tape.visit_sound hwf hneed hsize hj'
        (hstep t.nodes[j] (Array.mem_of_getElem (h := hj') rfl)) hcv hE hv
      exact ⟨_, rfl, hV, hE'⟩
  obtain ⟨hrv, hrc⟩ := M.pure_ok hret
  subst hrv
  subst hrc
  obtain ⟨hcv, -, -, hE⟩ := hinv
  exact ⟨hcv, fun ρ hρ i hi => hE ρ hρ i (by simpa using hi)⟩

end Petra
