/-
A square root the logic can read.

The kernel's `isqrt` runs a `while`, so nothing can be proved of it. `Provable.isqrt` below
is the same Newton iteration from the same start, written as a recursion on the current
value, which goes down at every step. It meets `IsqrtSpecOf`.

What was kept the same: the test for zero, the start `2 ^ (Nat.log2 n / 2 + 1)`, the step
`(x + n / x) / 2`, and the rule to stop at the first step that does not go down. So the two
return the same number on every input when run.
-/
import PetraProofs.Trust

namespace Petra.Provable

/-! ## The definitions

These two use core Lean only: no Mathlib name and no Mathlib tactic. They can be moved to
`kernel/Petra/Num.lean` as they stand. -/

/-- Newton's iteration from above: step down while the next value is smaller. -/
def isqrtGo (n x : Nat) : Nat :=
  if _h : (x + n / x) / 2 < x then isqrtGo n ((x + n / x) / 2) else x
termination_by x

/-- floor (sqrt n). -/
def isqrt (n : Nat) : Nat :=
  if n == 0 then 0 else isqrtGo n (2 ^ (Nat.log2 n / 2 + 1))

/-! ## The proofs -/

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

/-- `Provable.isqrt n` is the floor of the square root of `n`. -/
theorem isqrt_spec : IsqrtSpecOf isqrt := by
  intro n
  unfold isqrt
  by_cases h0 : n = 0
  · subst h0
    simp
  · have hne : (n == 0) = false := by simpa using h0
    simp only [hne, Bool.false_eq_true, if_false]
    exact isqrtGo_spec n (Nat.pos_of_ne_zero h0) _ (Nat.pow_pos (by norm_num)) (isqrt_start n)

end Petra.Provable
