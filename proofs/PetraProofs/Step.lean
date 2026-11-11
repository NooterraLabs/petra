/-
One step of a tape. If the enclosure of every node that a node reads holds that node's
value at a point of the box, the enclosure `Node.enclose` returns holds this node's value
there, and the node has a value. A pick has its own step, `pick_sound` in Pick.lean.
-/
import PetraProofs.Arith
import PetraProofs.Rounded

namespace Petra

/-! ## The folds of `add`, `mul`, `min` and `max` -/

theorem add_fold_sound (v : Array Iv) (val : Nat → Option ℝ) :
    ∀ (l : List Nat) (acc : Iv) (s : ℝ) (r : Iv), acc.Holds s →
      (∀ i ∈ l, ∃ x, val i = some x ∧ v[i]!.Holds x) →
      l.foldlM (fun acc i => fits (acc.add v[i]!)) acc = .ok r →
      ∃ xs, l.mapM val = some xs ∧ r.Holds (s + xs.sum) := by
  intro l
  induction l with
  | nil =>
    intro acc s r hacc _ h
    have h' : (Except.ok acc : Except String Iv) = .ok r := h
    cases h'
    exact ⟨[], by simp, by simpa using hacc⟩
  | cons i l ih =>
    intro acc s r hacc hval h
    rw [List.foldlM_cons] at h
    obtain ⟨y, hy, h2⟩ := Except.bind_ok h
    have hyx := fits_ok hy
    subst hyx
    obtain ⟨x, hx, hxv⟩ := hval i (by simp)
    obtain ⟨xs, hxs, hr⟩ := ih _ (s + x) r (Iv.add_sound hacc hxv)
      (fun j hj => hval j (List.mem_cons_of_mem _ hj)) h2
    refine ⟨x :: xs, ?_, ?_⟩
    · rw [List.mapM_cons, hx, hxs]
      rfl
    · rw [List.sum_cons, ← add_assoc]
      exact hr

theorem mul_fold_sound (v : Array Iv) (val : Nat → Option ℝ) :
    ∀ (l : List Nat) (acc : Iv) (s : ℝ) (r : Iv), acc.Holds s →
      (∀ i ∈ l, ∃ x, val i = some x ∧ v[i]!.Holds x) →
      l.foldlM (fun acc i => fits (acc.mul v[i]!)) acc = .ok r →
      ∃ xs, l.mapM val = some xs ∧ r.Holds (s * xs.prod) := by
  intro l
  induction l with
  | nil =>
    intro acc s r hacc _ h
    have h' : (Except.ok acc : Except String Iv) = .ok r := h
    cases h'
    exact ⟨[], by simp, by simpa using hacc⟩
  | cons i l ih =>
    intro acc s r hacc hval h
    rw [List.foldlM_cons] at h
    obtain ⟨y, hy, h2⟩ := Except.bind_ok h
    have hyx := fits_ok hy
    subst hyx
    obtain ⟨x, hx, hxv⟩ := hval i (by simp)
    obtain ⟨xs, hxs, hr⟩ := ih _ (s * x) r (Iv.mul_sound hacc hxv)
      (fun j hj => hval j (List.mem_cons_of_mem _ hj)) h2
    refine ⟨x :: xs, ?_, ?_⟩
    · rw [List.mapM_cons, hx, hxs]
      rfl
    · rw [List.prod_cons, ← mul_assoc]
      exact hr

theorem min_fold_sound (v : Array Iv) (val : Nat → Option ℝ) :
    ∀ (l : List Nat) (acc : Iv) (s : ℝ), acc.Holds s →
      (∀ i ∈ l, ∃ x, val i = some x ∧ v[i]!.Holds x) →
      ∃ xs, l.mapM val = some xs ∧
        (l.foldl (fun acc k => acc.min v[k]!) acc).Holds (xs.foldl Min.min s) := by
  intro l
  induction l with
  | nil =>
    intro acc s hacc _
    exact ⟨[], by simp, hacc⟩
  | cons i l ih =>
    intro acc s hacc hval
    obtain ⟨x, hx, hxv⟩ := hval i (by simp)
    obtain ⟨xs, hxs, hr⟩ := ih (acc.min v[i]!) (Min.min s x) (Iv.min_sound hacc hxv)
      (fun j hj => hval j (List.mem_cons_of_mem _ hj))
    refine ⟨x :: xs, ?_, hr⟩
    rw [List.mapM_cons, hx, hxs]
    rfl

theorem max_fold_sound (v : Array Iv) (val : Nat → Option ℝ) :
    ∀ (l : List Nat) (acc : Iv) (s : ℝ), acc.Holds s →
      (∀ i ∈ l, ∃ x, val i = some x ∧ v[i]!.Holds x) →
      ∃ xs, l.mapM val = some xs ∧
        (l.foldl (fun acc k => acc.max v[k]!) acc).Holds (xs.foldl Max.max s) := by
  intro l
  induction l with
  | nil =>
    intro acc s hacc _
    exact ⟨[], by simp, hacc⟩
  | cons i l ih =>
    intro acc s hacc hval
    obtain ⟨x, hx, hxv⟩ := hval i (by simp)
    obtain ⟨xs, hxs, hr⟩ := ih (acc.max v[i]!) (Max.max s x) (Iv.max_sound hacc hxv)
      (fun j hj => hval j (List.mem_cons_of_mem _ hj))
    refine ⟨x :: xs, ?_, hr⟩
    rw [List.mapM_cons, hx, hxs]
    rfl

/-! ## The step -/

/-- One step of the interval rule is sound. `box` is the box and `ρ` a point in it. `v`
holds the enclosures of the earlier nodes and `val` their values at `ρ`. If the enclosure
of every node this node reads holds that node's value, and the step returns `r`, then this
node has a value at `ρ` and `r` holds it. The caches stay right.

An input node must name an input of the box: `Node.enclose` reads `box[k]!`, which is
`[0, 0]` and no failure for a `k` past the end. `Tape.wellFormed` refuses such a tape before
any step runs. -/
theorem Node.enclose_sound {node : Node} {box v : Array Iv} {ρ : Nat → ℝ}
    {val : Nat → Option ℝ} {c c' : Caches} {r : Iv}
    (htrust : node.Trusted) (hbox : InBox box ρ)
    (hs : ∀ k, node = .s k → k < box.size)
    (hval : ∀ i ∈ node.reads, ∃ x, val i = some x ∧ v[i]!.Holds x)
    (hc : c.Valid)
    (h : node.enclose box v c = .ok (r, c')) :
    c'.Valid ∧ ∃ x, node.value box.size ρ val = some x ∧ r.Holds x := by
  cases node with
  | c q =>
    obtain ⟨rfl, rfl⟩ := M.pure_ok (a := Iv.pt q) h
    exact ⟨hc, (q : ℝ), rfl, Iv.pt_sound q⟩
  | s k =>
    obtain ⟨rfl, rfl⟩ := M.pure_ok (a := box[k]!) h
    have hk := hs k rfl
    refine ⟨hc, ρ k, ?_, hbox k hk⟩
    show (if k < box.size then some (ρ k) else none) = some (ρ k)
    rw [if_pos hk]
  | pi =>
    obtain ⟨hpi, rfl⟩ := M.lift_ok (e := piIv) h
    exact ⟨hc, Real.pi, rfl, piIv_sound htrust hpi⟩
  | add a =>
    obtain ⟨hf, rfl⟩ :=
      M.lift_ok (e := a.foldlM (fun acc i => fits (acc.add v[i]!)) (Iv.pt 0)) h
    rw [← Array.foldlM_toList] at hf
    obtain ⟨xs, hxs, hr⟩ := add_fold_sound v val a.toList (Iv.pt 0) 0 r
      (by simpa using Iv.pt_sound 0) (fun i hi => hval i (Array.mem_toList_iff.mp hi)) hf
    refine ⟨hc, xs.sum, ?_, by simpa using hr⟩
    show (a.toList.mapM val).map List.sum = some xs.sum
    rw [hxs]
    rfl
  | mul a =>
    obtain ⟨hf, rfl⟩ :=
      M.lift_ok (e := a.foldlM (fun acc i => fits (acc.mul v[i]!)) (Iv.pt 1)) h
    rw [← Array.foldlM_toList] at hf
    obtain ⟨xs, hxs, hr⟩ := mul_fold_sound v val a.toList (Iv.pt 1) 1 r
      (by simpa using Iv.pt_sound 1) (fun i hi => hval i (Array.mem_toList_iff.mp hi)) hf
    refine ⟨hc, xs.prod, ?_, by simpa using hr⟩
    show (a.toList.mapM val).map List.prod = some xs.prod
    rw [hxs]
    rfl
  | min a =>
    have h' : (match a.toList with
      | [] => (throw "min of no nodes" : M Iv)
      | i :: rest => pure (rest.foldl (fun acc k => acc.min v[k]!) v[i]!)) c = .ok (r, c') := h
    cases hl : a.toList with
    | nil =>
      rw [hl] at h'
      exact (M.throw_not_ok h').elim
    | cons i rest =>
      rw [hl] at h'
      obtain ⟨rfl, rfl⟩ := M.pure_ok h'
      have hmem : ∀ j ∈ i :: rest, ∃ x, val j = some x ∧ v[j]!.Holds x := fun j hj =>
        hval j (Array.mem_toList_iff.mp (show j ∈ a.toList by rw [hl]; exact hj))
      obtain ⟨x, hx, hxv⟩ := hmem i (by simp)
      obtain ⟨xs, hxs, hr⟩ := min_fold_sound v val rest v[i]! x hxv
        (fun j hj => hmem j (List.mem_cons_of_mem _ hj))
      refine ⟨hc, xs.foldl Min.min x, ?_, hr⟩
      show (a.toList.mapM val).bind _ = _
      rw [hl, List.mapM_cons, hx, hxs]
      rfl
  | max a =>
    have h' : (match a.toList with
      | [] => (throw "max of no nodes" : M Iv)
      | i :: rest => pure (rest.foldl (fun acc k => acc.max v[k]!) v[i]!)) c = .ok (r, c') := h
    cases hl : a.toList with
    | nil =>
      rw [hl] at h'
      exact (M.throw_not_ok h').elim
    | cons i rest =>
      rw [hl] at h'
      obtain ⟨rfl, rfl⟩ := M.pure_ok h'
      have hmem : ∀ j ∈ i :: rest, ∃ x, val j = some x ∧ v[j]!.Holds x := fun j hj =>
        hval j (Array.mem_toList_iff.mp (show j ∈ a.toList by rw [hl]; exact hj))
      obtain ⟨x, hx, hxv⟩ := hmem i (by simp)
      obtain ⟨xs, hxs, hr⟩ := max_fold_sound v val rest v[i]! x hxv
        (fun j hj => hmem j (List.mem_cons_of_mem _ hj))
      refine ⟨hc, xs.foldl Max.max x, ?_, hr⟩
      show (a.toList.mapM val).bind _ = _
      rw [hl, List.mapM_cons, hx, hxs]
      rfl
  | neg i =>
    obtain ⟨rfl, rfl⟩ := M.pure_ok (a := v[i]!.neg) h
    obtain ⟨x, hx, hxv⟩ := hval i (by simp [Node.reads])
    refine ⟨hc, -x, ?_, Iv.neg_sound hxv⟩
    show (val i).map (fun x => -x) = some (-x)
    rw [hx]
    rfl
  | abs i =>
    obtain ⟨rfl, rfl⟩ := M.pure_ok (a := v[i]!.abs) h
    obtain ⟨x, hx, hxv⟩ := hval i (by simp [Node.reads])
    refine ⟨hc, |x|, ?_, Iv.abs_sound hxv⟩
    show (val i).map (fun x => |x|) = some |x|
    rw [hx]
    rfl
  | sqrt i =>
    obtain ⟨hq, rfl⟩ := M.lift_ok (e := iSqrt v[i]!) h
    obtain ⟨x, hx, hxv⟩ := hval i (by simp [Node.reads])
    obtain ⟨hx0, hr⟩ := iSqrt_sound htrust hxv hq
    refine ⟨hc, Real.sqrt x, ?_, hr⟩
    show (val i).bind (fun x => if 0 ≤ x then some (Real.sqrt x) else none) = some (Real.sqrt x)
    rw [hx]
    show (if 0 ≤ x then some (Real.sqrt x) else none) = some (Real.sqrt x)
    rw [if_pos hx0]
  | ln i =>
    obtain ⟨x, hx, hxv⟩ := hval i (by simp [Node.reads])
    have h' : iLn v[i]! c = .ok (r, c') := h
    obtain ⟨hc', hpos, hr⟩ := iLn_sound htrust hc hxv h'
    refine ⟨hc', Real.log x, ?_, hr⟩
    show (val i).bind (fun x => if 0 < x then some (Real.log x) else none) = some (Real.log x)
    rw [hx]
    show (if 0 < x then some (Real.log x) else none) = some (Real.log x)
    rw [if_pos hpos]
  | exp i =>
    obtain ⟨x, hx, hxv⟩ := hval i (by simp [Node.reads])
    simp only [Node.enclose] at h
    split at h
    · exact (M.throw_not_ok h).elim
    · obtain ⟨hc', hr⟩ := iExp_sound htrust hc hxv h
      refine ⟨hc', Real.exp x, ?_, hr⟩
      show (val i).map Real.exp = some (Real.exp x)
      rw [hx]
      rfl
  | div i j =>
    obtain ⟨hq, rfl⟩ := M.lift_ok (e := v[i]!.div v[j]!) h
    obtain ⟨x, hx, hxv⟩ := hval i (by simp [Node.reads])
    obtain ⟨y, hy, hyv⟩ := hval j (by simp [Node.reads])
    obtain ⟨hy0, hr⟩ := Iv.div_sound hxv hyv hq
    refine ⟨hc, x / y, ?_, hr⟩
    show (val i).bind (fun x => (val j).bind fun y => if y = 0 then none else some (x / y))
      = some (x / y)
    rw [hx, hy]
    show (if y = 0 then none else some (x / y)) = some (x / y)
    rw [if_neg hy0]
  | pow i n =>
    obtain ⟨hq, rfl⟩ := M.lift_ok (e := powInt v[i]! n) h
    obtain ⟨x, hx, hxv⟩ := hval i (by simp [Node.reads])
    obtain ⟨hn, hr⟩ := powInt_sound hxv hq
    have hpow : x ^ n = x ^ n.toNat := by
      conv_lhs => rw [← Int.toNat_of_nonneg hn]
      exact zpow_natCast x n.toNat
    refine ⟨hc, x ^ n, ?_, by rw [hpow]; exact hr⟩
    show (val i).bind (fun x => if 0 ≤ n ∨ x ≠ 0 then some (x ^ n) else none) = some (x ^ n)
    rw [hx]
    show (if 0 ≤ n ∨ x ≠ 0 then some (x ^ n) else none) = some (x ^ n)
    rw [if_pos (Or.inl hn)]
  | pick cases =>
    exact (M.throw_not_ok (s := "a pick is not enclosed by this step") h).elim

/-- A step keeps the caches right, with or without a point in the box. -/
theorem Node.enclose_valid {node : Node} {box v : Array Iv} {c c' : Caches} {r : Iv}
    (htrust : node.Trusted) (hc : c.Valid) (h : node.enclose box v c = .ok (r, c')) :
    c'.Valid := by
  cases node with
  | c q =>
    obtain ⟨-, rfl⟩ := M.pure_ok (a := Iv.pt q) h
    exact hc
  | s k =>
    obtain ⟨-, rfl⟩ := M.pure_ok (a := box[k]!) h
    exact hc
  | pi =>
    obtain ⟨-, rfl⟩ := M.lift_ok (e := piIv) h
    exact hc
  | add a =>
    obtain ⟨-, rfl⟩ :=
      M.lift_ok (e := a.foldlM (fun acc i => fits (acc.add v[i]!)) (Iv.pt 0)) h
    exact hc
  | mul a =>
    obtain ⟨-, rfl⟩ :=
      M.lift_ok (e := a.foldlM (fun acc i => fits (acc.mul v[i]!)) (Iv.pt 1)) h
    exact hc
  | min a =>
    have h' : (match a.toList with
      | [] => (throw "min of no nodes" : M Iv)
      | i :: rest => pure (rest.foldl (fun acc k => acc.min v[k]!) v[i]!)) c = .ok (r, c') := h
    cases hl : a.toList with
    | nil =>
      rw [hl] at h'
      exact (M.throw_not_ok h').elim
    | cons i rest =>
      rw [hl] at h'
      obtain ⟨-, rfl⟩ := M.pure_ok h'
      exact hc
  | max a =>
    have h' : (match a.toList with
      | [] => (throw "max of no nodes" : M Iv)
      | i :: rest => pure (rest.foldl (fun acc k => acc.max v[k]!) v[i]!)) c = .ok (r, c') := h
    cases hl : a.toList with
    | nil =>
      rw [hl] at h'
      exact (M.throw_not_ok h').elim
    | cons i rest =>
      rw [hl] at h'
      obtain ⟨-, rfl⟩ := M.pure_ok h'
      exact hc
  | neg i =>
    obtain ⟨-, rfl⟩ := M.pure_ok (a := v[i]!.neg) h
    exact hc
  | abs i =>
    obtain ⟨-, rfl⟩ := M.pure_ok (a := v[i]!.abs) h
    exact hc
  | sqrt i =>
    obtain ⟨-, rfl⟩ := M.lift_ok (e := iSqrt v[i]!) h
    exact hc
  | ln i =>
    have h' : iLn v[i]! c = .ok (r, c') := h
    exact iLn_valid htrust hc h'
  | exp i =>
    simp only [Node.enclose] at h
    split at h
    · exact (M.throw_not_ok h).elim
    · exact iExp_valid htrust hc h
  | div i j =>
    obtain ⟨-, rfl⟩ := M.lift_ok (e := v[i]!.div v[j]!) h
    exact hc
  | pow i n =>
    obtain ⟨-, rfl⟩ := M.lift_ok (e := powInt v[i]! n) h
    exact hc
  | pick cases =>
    exact (M.throw_not_ok (s := "a pick is not enclosed by this step") h).elim

end Petra
