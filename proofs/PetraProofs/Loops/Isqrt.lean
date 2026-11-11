/-
The kernel's `isqrt` is the floor of the square root.

`isqrt` in kernel/Petra/Num.lean is Newton's iteration from above, written as a recursion on
the current value, which goes down at every step. This file proves that it meets
`IsqrtSpecOf`: `isqrt n * isqrt n ≤ n < (isqrt n + 1) * (isqrt n + 1)`.
-/
import PetraProofs.Spec

namespace Petra.Loops

/-- From a positive value whose square is above `n`, the iteration ends on the floor of the
square root of `n`. -/
theorem isqrtGo_spec (n : Nat) (hn : 0 < n) (x : Nat) (hx : 0 < x)
    (hlt : n < (x + 1) * (x + 1)) :
    isqrtGo n x * isqrtGo n x ≤ n ∧ n < (isqrtGo n x + 1) * (isqrtGo n x + 1) := by
  induction x using Nat.strong_induction_on with
  | _ x ih =>
    rw [isqrtGo]
    by_cases h : (x + n / x) / 2 < x
    · simp only [dif_pos h]
      -- The next value is still at or above the root: the mean of `x` and `n / x`.
      have h2 : n < x * (n / x + 1) := Nat.lt_mul_div_succ n hx
      have key : n < ((x + n / x) / 2 + 1) * ((x + n / x) / 2 + 1) := by
        generalize hq : n / x = q at h2
        generalize hy : (x + q) / 2 = y
        have a2 : x + q + 1 ≤ 2 * (y + 1) := by omega
        have a1 : (n : ℤ) < (x : ℤ) * ((q : ℤ) + 1) := by exact_mod_cast h2
        have a2' : (x : ℤ) + q + 1 ≤ 2 * ((y : ℤ) + 1) := by exact_mod_cast a2
        have a3 : (0 : ℤ) ≤ 2 * ((y : ℤ) + 1) + ((x : ℤ) + q + 1) := by positivity
        have goal : (n : ℤ) < ((y : ℤ) + 1) * ((y : ℤ) + 1) := by
          nlinarith [mul_nonneg (sub_nonneg.2 a2') a3, sq_nonneg ((x : ℤ) - q - 1)]
        exact_mod_cast goal
      have hpos : 0 < (x + n / x) / 2 := by
        rcases Nat.eq_zero_or_pos ((x + n / x) / 2) with h0 | h0
        · rw [h0] at key
          omega
        · exact h0
      exact ih _ h hpos key
    · simp only [dif_neg h]
      have hle : x ≤ n / x := by omega
      exact ⟨(Nat.le_div_iff_mul_le hx).1 hle, hlt⟩

/-- The start is above the root. -/
theorem isqrt_start (n : Nat) :
    n < (2 ^ (Nat.log2 n / 2 + 1) + 1) * (2 ^ (Nat.log2 n / 2 + 1) + 1) := by
  have h1 : n < 2 ^ (Nat.log2 n + 1) := Nat.lt_log2_self
  have h2 : 2 ^ (Nat.log2 n + 1) ≤ 2 ^ (Nat.log2 n / 2 + 1) * 2 ^ (Nat.log2 n / 2 + 1) := by
    rw [← Nat.pow_add]
    exact Nat.pow_le_pow_right (by norm_num) (by omega)
  calc n < 2 ^ (Nat.log2 n + 1) := h1
    _ ≤ 2 ^ (Nat.log2 n / 2 + 1) * 2 ^ (Nat.log2 n / 2 + 1) := h2
    _ ≤ (2 ^ (Nat.log2 n / 2 + 1) + 1) * (2 ^ (Nat.log2 n / 2 + 1) + 1) :=
      Nat.mul_le_mul (Nat.le_succ _) (Nat.le_succ _)

/-- The kernel's `isqrt n` is the floor of the square root of `n`. -/
theorem isqrt_spec : IsqrtSpecOf isqrt := by
  intro n
  unfold isqrt
  by_cases h0 : n = 0
  · subst h0
    simp
  · have hne : (n == 0) = false := by simpa using h0
    simp only [hne, Bool.false_eq_true, if_false]
    exact isqrtGo_spec n (Nat.pos_of_ne_zero h0) _ (Nat.pow_pos (by norm_num)) (isqrt_start n)

end Petra.Loops
