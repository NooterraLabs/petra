/-
What the small loops of `Certify/Read.lean` return, for the proofs that follow.
-/
import Mathlib.Tactic
import Mathlib.Data.Real.Basic
import Mathlib.Data.Real.Sqrt
import Certify.Read

namespace Certify

theorem need_ok {b : Bool} {why : String} {u : Unit} : need b why = .ok u ↔ b = true := by
  unfold need; split <;> simp_all

theorem bind_ok {α β : Type} {x : Check α} {f : α → Check β} {b : β} :
    (x >>= f) = .ok b ↔ ∃ a, x = .ok a ∧ f a = .ok b := by
  cases x <;> simp [bind, Except.bind]

theorem collect_mem_in {α β : Type} {f : α → Check β} :
    ∀ {l : List α} {r : List β}, collect f l = .ok r → ∀ a ∈ l, ∃ b ∈ r, f a = .ok b
  | [], _, _, a, ha => by cases ha
  | a0 :: as, r, h, a, ha => by
    simp only [collect, bind_ok] at h
    obtain ⟨b, hb, bs, hbs, h⟩ := h
    cases h
    rcases List.mem_cons.mp ha with rfl | ha
    · exact ⟨b, by simp, hb⟩
    · obtain ⟨b', hb', hf⟩ := collect_mem_in hbs a ha
      exact ⟨b', by simp [hb'], hf⟩

theorem collect_mem_out {α β : Type} {f : α → Check β} :
    ∀ {l : List α} {r : List β}, collect f l = .ok r → ∀ b ∈ r, ∃ a ∈ l, f a = .ok b
  | [], r, h, b, hb => by
    simp only [collect] at h
    cases h
    cases hb
  | a0 :: as, r, h, b, hb => by
    simp only [collect, bind_ok] at h
    obtain ⟨b0, hb0, bs, hbs, h⟩ := h
    cases h
    rcases List.mem_cons.mp hb with rfl | hb
    · exact ⟨a0, by simp, hb0⟩
    · obtain ⟨a, ha, hf⟩ := collect_mem_out hbs b hb
      exact ⟨a, by simp [ha], hf⟩

theorem collectIdx_mem_in {α β : Type} {f : Nat → α → Check β} :
    ∀ {l : List α} {n : Nat} {r : List β}, collectIdx f l n = .ok r →
      ∀ a ∈ l, ∃ k, ∃ b ∈ r, f k a = .ok b
  | [], _, _, _, a, ha => by cases ha
  | a0 :: as, n, r, h, a, ha => by
    simp only [collectIdx, bind_ok] at h
    obtain ⟨b, hb, bs, hbs, h⟩ := h
    cases h
    rcases List.mem_cons.mp ha with rfl | ha
    · exact ⟨n, b, by simp, hb⟩
    · obtain ⟨k, b', hb', hf⟩ := collectIdx_mem_in hbs a ha
      exact ⟨k, b', by simp [hb'], hf⟩

/-- Where `each` passes, every member passed, each at its own place. -/
theorem each_ok {α : Type} {f : Nat → α → Check Unit} :
    ∀ {l : List α} {n : Nat}, each f l n = .ok () →
      ∀ (k : Nat) (hk : k < l.length), f (n + k) l[k] = .ok ()
  | [], _, _, k, hk => by cases hk
  | a :: as, n, h, k, hk => by
    simp only [each, bind_ok] at h
    obtain ⟨_, ha, h⟩ := h
    cases k with
    | zero => simpa using ha
    | succ k =>
      have := each_ok h k (by simpa using hk)
      simpa [Nat.add_assoc, Nat.add_comm 1 k] using this

end Certify
