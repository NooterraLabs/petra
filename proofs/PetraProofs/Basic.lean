/-
What the proofs share: when an interval holds a real number, and how the kernel's monads
and loops unfold.
-/
import Mathlib.Data.Real.Basic
import Mathlib.Tactic
import Petra.Tape

namespace Petra

/-- The real `x` lies in the interval `a`. The ends of `a` are rationals, read as reals. -/
def Iv.Holds (a : Iv) (x : ℝ) : Prop := (a.lo : ℝ) ≤ x ∧ x ≤ (a.hi : ℝ)

theorem rmin_eq (a b : ℚ) : rmin a b = min a b := by
  unfold rmin
  split_ifs with h
  · exact (min_eq_left h).symm
  · exact (min_eq_right (not_le.mp h).le).symm

theorem rmax_eq (a b : ℚ) : rmax a b = max a b := by
  unfold rmax
  split_ifs with h
  · exact (max_eq_right h).symm
  · exact (max_eq_left (not_le.mp h).le).symm

/-! ## Reading an array at an index -/

theorem getElem!_push_lt {α : Type} [Inhabited α] (a : Array α) (x : α) {i : Nat}
    (h : i < a.size) : (a.push x)[i]! = a[i]! := by
  rw [getElem!_pos (a.push x) i (by simp; omega), getElem!_pos a i h, Array.getElem_push_lt h]

theorem getElem!_push_eq {α : Type} [Inhabited α] (a : Array α) (x : α) :
    (a.push x)[a.size]! = x := by
  rw [getElem!_pos (a.push x) a.size (by simp), Array.getElem_push_eq]

/-! ## The monads `Except` and `M` -/

theorem Except.bind_ok {ε α β : Type} {x : Except ε α} {f : α → Except ε β} {b : β}
    (h : x >>= f = .ok b) : ∃ a, x = .ok a ∧ f a = .ok b := by
  cases x with
  | error e =>
    have h' : (Except.error e : Except ε β) = .ok b := h
    cases h'
  | ok a => exact ⟨a, rfl, h⟩

theorem M.bind_ok {α β : Type} {x : M α} {f : α → M β} {c c' : Caches} {b : β}
    (h : (x >>= f) c = .ok (b, c')) : ∃ a c₁, x c = .ok (a, c₁) ∧ f a c₁ = .ok (b, c') := by
  have e : (x >>= f) c = (x c >>= fun p => f p.1 p.2) := rfl
  rw [e] at h
  obtain ⟨⟨a, c₁⟩, h1, h2⟩ := Except.bind_ok h
  exact ⟨a, c₁, h1, h2⟩

theorem M.pure_ok {α : Type} {a b : α} {c c' : Caches}
    (h : (pure a : M α) c = .ok (b, c')) : b = a ∧ c' = c := by
  have h' : (Except.ok (a, c) : Except String (α × Caches)) = .ok (b, c') := h
  cases h'
  exact ⟨rfl, rfl⟩

theorem M.lift_ok {α : Type} {e : Except String α} {c c' : Caches} {b : α}
    (h : (liftM (m := Except String) e : M α) c = .ok (b, c')) : e = .ok b ∧ c' = c := by
  cases e with
  | error s =>
    have h' : (Except.error s : Except String (α × Caches)) = .ok (b, c') := h
    cases h'
  | ok a =>
    have h' : (Except.ok (a, c) : Except String (α × Caches)) = .ok (b, c') := h
    cases h'
    exact ⟨rfl, rfl⟩

theorem M.throw_not_ok {α : Type} {s : String} {c c' : Caches} {b : α}
    (h : (throw s : M α) c = .ok (b, c')) : False := by
  have h' : (Except.error s : Except String (α × Caches)) = .ok (b, c') := h
  cases h'

theorem M.tryCatch_ok {α : Type} {x : M α} {handle : String → M α} {c c' : Caches} {b : α}
    (h : (tryCatch x handle) c = .ok (b, c')) :
    x c = .ok (b, c') ∨ ∃ e, x c = .error e ∧ handle e c = .ok (b, c') := by
  have e : (tryCatch x handle) c = Except.tryCatch (x c) (fun e => handle e c) := rfl
  rw [e] at h
  cases hx : x c with
  | ok r => rw [hx] at h; exact Or.inl h
  | error s => rw [hx] at h; exact Or.inr ⟨s, rfl, h⟩

/-! ## Loops

Each loop of the kernel either goes on to its next round or throws. So a property that
holds before the loop, and that every round keeps, holds after it. `P k` is the property
after `k` rounds. -/

theorem M.forIn_list_inv {α β : Type} (f : α → β → M (ForInStep β))
    (P : Nat → β → Caches → Prop) :
    ∀ (l : List α) (k : Nat) (b : β) (c : Caches) (r : β) (c' : Caches), P k b c →
      (∀ (j : Nat) (hj : j < l.length) (b : β) (c : Caches) (s : ForInStep β) (c' : Caches),
        P (k + j) b c → f l[j] b c = .ok (s, c') → ∃ b', s = .yield b' ∧ P (k + j + 1) b' c') →
      forIn l b f c = .ok (r, c') → P (k + l.length) r c' := by
  intro l
  induction l with
  | nil =>
    intro k b c r c' h0 _ h
    rw [List.forIn_nil] at h
    obtain ⟨rfl, rfl⟩ := M.pure_ok h
    simpa using h0
  | cons a l ih =>
    intro k b c r c' h0 hstep h
    rw [List.forIn_cons] at h
    obtain ⟨s, c₁, h1, h2⟩ := M.bind_ok h
    obtain ⟨b', rfl, hP⟩ := hstep 0 (Nat.succ_pos _) b c s c₁ h0 h1
    have := ih (k + 1) b' c₁ r c' hP (fun j hj b c s c' hp hf => by
      have e1 : k + 1 + j = k + (j + 1) := by omega
      have e2 : k + 1 + j + 1 = k + (j + 1) + 1 := by omega
      rw [e1] at hp
      rw [e2]
      exact hstep (j + 1) (Nat.succ_lt_succ hj) b c s c' hp hf) h2
    have e : k + 1 + l.length = k + (a :: l).length := by simp; omega
    rw [← e]
    exact this

theorem M.forIn_array_inv {α β : Type} (f : α → β → M (ForInStep β))
    (P : Nat → β → Caches → Prop) (xs : Array α) (b r : β) (c c' : Caches) (h0 : P 0 b c)
    (hstep : ∀ (j : Nat) (hj : j < xs.size) (b : β) (c : Caches) (s : ForInStep β)
      (c' : Caches), P j b c → f xs[j] b c = .ok (s, c') → ∃ b', s = .yield b' ∧ P (j + 1) b' c')
    (h : forIn xs b f c = .ok (r, c')) : P xs.size r c' := by
  rw [← Array.forIn_toList] at h
  have := M.forIn_list_inv f P xs.toList 0 b c r c' h0 (fun j hj b c s c' hp hf => by
    simp only [Nat.zero_add] at hp ⊢
    exact hstep j (by simpa using hj) b c s c' hp (by simpa using hf)) h
  simpa using this

theorem Except.forIn_list_inv {ε α β : Type} (f : α → β → Except ε (ForInStep β))
    (P : Nat → β → Prop) :
    ∀ (l : List α) (k : Nat) (b r : β), P k b →
      (∀ (j : Nat) (hj : j < l.length) (b : β) (s : ForInStep β),
        P (k + j) b → f l[j] b = .ok s → ∃ b', s = .yield b' ∧ P (k + j + 1) b') →
      forIn l b f = .ok r → P (k + l.length) r := by
  intro l
  induction l with
  | nil =>
    intro k b r h0 _ h
    rw [List.forIn_nil] at h
    have h' : (Except.ok b : Except ε β) = .ok r := h
    cases h'
    simpa using h0
  | cons a l ih =>
    intro k b r h0 hstep h
    rw [List.forIn_cons] at h
    obtain ⟨s, h1, h2⟩ := Except.bind_ok h
    obtain ⟨b', rfl, hP⟩ := hstep 0 (Nat.succ_pos _) b s h0 h1
    have := ih (k + 1) b' r hP (fun j hj b s hp hf => by
      have e1 : k + 1 + j = k + (j + 1) := by omega
      have e2 : k + 1 + j + 1 = k + (j + 1) + 1 := by omega
      rw [e1] at hp
      rw [e2]
      exact hstep (j + 1) (Nat.succ_lt_succ hj) b s hp hf) h2
    have e : k + 1 + l.length = k + (a :: l).length := by simp; omega
    rw [← e]
    exact this

theorem Except.forIn_array_inv {ε α β : Type} (f : α → β → Except ε (ForInStep β))
    (P : Nat → β → Prop) (xs : Array α) (b r : β) (h0 : P 0 b)
    (hstep : ∀ (j : Nat) (hj : j < xs.size) (b : β) (s : ForInStep β),
      P j b → f xs[j] b = .ok s → ∃ b', s = .yield b' ∧ P (j + 1) b')
    (h : forIn xs b f = .ok r) : P xs.size r := by
  rw [← Array.forIn_toList] at h
  have := Except.forIn_list_inv f P xs.toList 0 b r h0 (fun j hj b s hp hf => by
    simp only [Nat.zero_add] at hp ⊢
    exact hstep j (by simpa using hj) b s hp (by simpa using hf)) h
  simpa using this

/-- A loop over `[0:n]` in `Except`. -/
theorem Except.forIn_range_inv {ε β : Type} (f : Nat → β → Except ε (ForInStep β))
    (P : Nat → β → Prop) (n : Nat) (b r : β) (h0 : P 0 b)
    (hstep : ∀ (j : Nat), j < n → ∀ (b : β) (s : ForInStep β),
      P j b → f j b = .ok s → ∃ b', s = .yield b' ∧ P (j + 1) b')
    (h : forIn [0:n] b f = .ok r) : P n r := by
  rw [Std.Legacy.Range.forIn_eq_forIn_range'] at h
  have hsize : ([0:n] : Std.Legacy.Range).size = n := by simp [Std.Legacy.Range.size]
  rw [hsize] at h
  have := Except.forIn_list_inv f P (List.range' 0 n) 0 b r h0 (fun j hj b s hp hf => by
    simp only [Nat.zero_add] at hp ⊢
    have hj' : j < n := by simpa using hj
    exact hstep j hj' b s hp (by simpa using hf)) h
  simpa using this

theorem Id.forIn_list_inv {α β : Type} (f : α → β → Id (ForInStep β)) (P : Nat → β → Prop) :
    ∀ (l : List α) (k : Nat) (b : β), P k b →
      (∀ (j : Nat) (hj : j < l.length) (b : β),
        P (k + j) b → ∃ b', f l[j] b = pure (.yield b') ∧ P (k + j + 1) b') →
      P (k + l.length) (Id.run (forIn l b f)) := by
  intro l
  induction l with
  | nil =>
    intro k b h0 _
    simpa using h0
  | cons a l ih =>
    intro k b h0 hstep
    obtain ⟨b', hb, hP⟩ := hstep 0 (Nat.succ_pos _) b h0
    have hb' : f a b = pure (.yield b') := hb
    rw [List.forIn_cons, hb', pure_bind]
    have := ih (k + 1) b' hP (fun j hj b hp => by
      have e1 : k + 1 + j = k + (j + 1) := by omega
      have e2 : k + 1 + j + 1 = k + (j + 1) + 1 := by omega
      rw [e1] at hp
      rw [e2]
      exact hstep (j + 1) (Nat.succ_lt_succ hj) b hp)
    have e : k + 1 + l.length = k + (a :: l).length := by simp; omega
    rw [← e]
    exact this

/-- A loop over `[0:n]` in `Id`. -/
theorem Id.forIn_range_inv {β : Type} (f : Nat → β → Id (ForInStep β)) (P : Nat → β → Prop)
    (n : Nat) (b : β) (h0 : P 0 b)
    (hstep : ∀ (j : Nat), j < n → ∀ (b : β), P j b → ∃ b', f j b = pure (.yield b') ∧ P (j + 1) b') :
    P n (Id.run (forIn [0:n] b f)) := by
  rw [Std.Legacy.Range.forIn_eq_forIn_range']
  have hsize : ([0:n] : Std.Legacy.Range).size = n := by simp [Std.Legacy.Range.size]
  rw [hsize]
  have := Id.forIn_list_inv f P (List.range' 0 n) 0 b h0 (fun j hj b hp => by
    simp only [Nat.zero_add] at hp ⊢
    have hj' : j < n := by simpa using hj
    obtain ⟨b', h1, h2⟩ := hstep j hj' b hp
    exact ⟨b', by simpa using h1, h2⟩)
  simpa using this

end Petra
