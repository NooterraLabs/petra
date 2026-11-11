/-
The series for atanh and arctan, in a form the logic can read.

The kernel's `oddSeries` runs a `while`, so nothing can be proved of it. `Provable.oddSeries`
below is the same computation, with the loop written as a recursion. It meets
`OddSeriesSpecOf`.

What was kept the same: the fixed point `one = 2 ^ p`, the first term `scale one one x`, the
step `sign * x * x`, the two calls of `scale` in each round, the test
`3 ^ (2 * k + 1) ≤ 2 * one` that keeps the loop going, and the tail
`(9/8) / 3 ^ (2 * k + 1)`. So the two should return the same interval on every input when
run. That is not proved, and cannot be while the kernel's is a `while`. They agreed on every
input tried: docs/proved.md.
-/
import Mathlib.Analysis.SpecialFunctions.Complex.Arctan
import Mathlib.Analysis.SpecialFunctions.Log.Deriv
import Mathlib.Analysis.SpecificLimits.Basic
import PetraProofs.Trust

namespace Petra.Provable

/-! ## The definitions

These two use core Lean and the kernel's own `scale`, `qi` and `qd` only: no Mathlib name
and no Mathlib tactic. They can be moved to `kernel/Petra/Num.lean` as they stand. -/

/-- The loop of the series. `[a, b]` holds term `k` times `one`, and `[lo, hi]` holds the sum
of the terms before it times `one`. It returns the sum and the number of terms summed. The
power of 3 grows at every round, so the loop ends. -/
def oddGo (one : Int) (step : Rat) (a b lo hi : Int) (k : Nat) : Int × Int × Nat :=
  if _h : (3 : Int) ^ (2 * k + 1) ≤ 2 * one then
    let t := scale a b (mkRat 1 (2 * k + 1))
    let n := scale a b step
    oddGo one step n.1 n.2 (lo + t.1) (hi + t.2) (k + 1)
  else (lo, hi, k)
termination_by (2 * one + 1 - (3 : Int) ^ (2 * k + 1)).toNat
decreasing_by
  have h3 : (3 : Int) ^ (2 * (k + 1) + 1) = 3 ^ (2 * k + 1) * 3 * 3 := by
    rw [show 2 * (k + 1) + 1 = (2 * k + 1) + 1 + 1 from by omega, Int.pow_succ, Int.pow_succ]
  have hp : (0 : Int) < 3 ^ (2 * k + 1) := Int.pow_pos (by decide)
  omega

/-- Encloses sum_k sign^k x^(2k+1)/(2k+1) for |x| <= 1/3: atanh x for sign 1 and atan x for
sign -1. The tail after k terms is at most (9/8) 3^-(2k+1). -/
def oddSeries (x : Rat) (sign : Int) (p : Nat) : Iv :=
  let one : Int := (2 : Int) ^ p
  let s := scale one one x
  let r := oddGo one (qi sign * x * x) s.1 s.2 0 0 0
  let tail : Rat := mkRat 9 8 / qi ((3 : Int) ^ (2 * r.2.2 + 1))
  ⟨qd r.1 one - tail, qd r.2.1 one + tail⟩

/-! ## Casts and `scale` -/

theorem qi_cast (n : ℤ) : ((qi n : ℚ) : ℝ) = (n : ℝ) := by
  unfold qi
  rw [Rat.mkRat_eq_div]
  simp

theorem qd_cast (n d : ℤ) (hd : 0 ≤ d) : ((qd n d : ℚ) : ℝ) = (n : ℝ) / (d : ℝ) := by
  unfold qd
  rw [Rat.mkRat_eq_div]
  have h1 : ((d.toNat : ℕ) : ℤ) = d := Int.toNat_of_nonneg hd
  have h2 : ((d.toNat : ℕ) : ℝ) = (d : ℝ) := by exact_mod_cast h1
  push_cast
  rw [h2]

theorem mkRat_one_cast (j : ℕ) : ((mkRat 1 (2 * j + 1) : ℚ) : ℝ) = 1 / (2 * (j : ℝ) + 1) := by
  rw [Rat.mkRat_eq_div]
  push_cast
  rfl

theorem tail_cast (K : ℕ) :
    ((mkRat 9 8 / qi ((3 : ℤ) ^ (2 * K + 1)) : ℚ) : ℝ) = 9 / 8 / 3 ^ (2 * K + 1) := by
  rw [Rat.cast_div, qi_cast, Rat.mkRat_eq_div]
  push_cast
  rfl

/-- `Int.fdiv` by a denominator rounds down. -/
theorem fdiv_le (m : ℤ) (c : ℚ) :
    ((Int.fdiv (m * c.num) (Int.ofNat c.den) : ℤ) : ℝ) ≤ (m : ℝ) * (c : ℝ) := by
  have e : Int.ofNat c.den = ((c.den : ℕ) : ℤ) := rfl
  rw [e]
  have hd : (0 : ℤ) < ((c.den : ℕ) : ℤ) := by exact_mod_cast c.den_pos
  rw [Int.fdiv_eq_ediv_of_nonneg _ hd.le]
  have h := Int.ediv_mul_le (m * c.num) (ne_of_gt hd)
  generalize (m * c.num) / ((c.den : ℕ) : ℤ) = X at h ⊢
  have hR : (X : ℝ) * (c.den : ℝ) ≤ (m : ℝ) * (c.num : ℝ) := by exact_mod_cast h
  have hdR : (0 : ℝ) < (c.den : ℝ) := by exact_mod_cast c.den_pos
  rw [Rat.cast_def, ← mul_div_assoc, le_div_iff₀ hdR]
  exact hR

/-- Minus `Int.fdiv` of the negation rounds up. -/
theorem le_neg_fdiv (m : ℤ) (c : ℚ) :
    (m : ℝ) * (c : ℝ) ≤ ((-(Int.fdiv (-(m * c.num)) (Int.ofNat c.den)) : ℤ) : ℝ) := by
  have e : Int.ofNat c.den = ((c.den : ℕ) : ℤ) := rfl
  rw [e]
  have hd : (0 : ℤ) < ((c.den : ℕ) : ℤ) := by exact_mod_cast c.den_pos
  rw [Int.fdiv_eq_ediv_of_nonneg _ hd.le]
  have h := Int.ediv_mul_le (-(m * c.num)) (ne_of_gt hd)
  generalize (-(m * c.num)) / ((c.den : ℕ) : ℤ) = X at h ⊢
  have hR : (X : ℝ) * (c.den : ℝ) ≤ -((m : ℝ) * (c.num : ℝ)) := by exact_mod_cast h
  have hdR : (0 : ℝ) < (c.den : ℝ) := by exact_mod_cast c.den_pos
  rw [Rat.cast_def, ← mul_div_assoc, div_le_iff₀ hdR]
  push_cast
  linarith

theorem scale_of_nonneg {a b : ℤ} {c : ℚ} (hc : 0 ≤ c) :
    scale a b c =
      (Int.fdiv (a * c.num) (Int.ofNat c.den), -Int.fdiv (-(b * c.num)) (Int.ofNat c.den)) := by
  unfold scale
  simp only [if_pos hc]

theorem scale_of_neg {a b : ℤ} {c : ℚ} (hc : ¬ 0 ≤ c) :
    scale a b c =
      (Int.fdiv (b * c.num) (Int.ofNat c.den), -Int.fdiv (-(a * c.num)) (Int.ofNat c.den)) := by
  unfold scale
  simp only [if_neg hc]

/-- `scale a b c` holds `u * c` for every `u` in `[a, b]`. -/
theorem scale_sound {a b : ℤ} {u : ℝ} (c : ℚ) (h1 : (a : ℝ) ≤ u) (h2 : u ≤ (b : ℝ)) :
    ((scale a b c).1 : ℝ) ≤ u * c ∧ u * c ≤ ((scale a b c).2 : ℝ) := by
  by_cases hc : 0 ≤ c
  · rw [scale_of_nonneg hc]
    have hcR : (0 : ℝ) ≤ (c : ℝ) := by exact_mod_cast hc
    exact ⟨(fdiv_le a c).trans (mul_le_mul_of_nonneg_right h1 hcR),
      (mul_le_mul_of_nonneg_right h2 hcR).trans (le_neg_fdiv b c)⟩
  · rw [scale_of_neg hc]
    have hcR : (c : ℝ) ≤ 0 := by exact_mod_cast (not_le.mp hc).le
    exact ⟨(fdiv_le b c).trans (mul_le_mul_of_nonpos_right h2 hcR),
      (mul_le_mul_of_nonpos_right h1 hcR).trans (le_neg_fdiv a c)⟩

/-! ## The loop -/

/-- The loop keeps what its comment says. `U k` is term `k` times `one`, before the division
by `2 * k + 1`. When `[a, b]` holds `U k` and `[lo, hi]` holds the sum of the first `k`
terms, the result holds the sum of as many terms as the loop went on to sum. -/
theorem oddGo_inv (one : ℤ) (step : ℚ) (U : ℕ → ℝ) (hU : ∀ k, U (k + 1) = U k * (step : ℝ)) :
    ∀ (a b lo hi : ℤ) (k : ℕ), (a : ℝ) ≤ U k → U k ≤ (b : ℝ) →
      (lo : ℝ) ≤ ∑ j ∈ Finset.range k, U j * ((mkRat 1 (2 * j + 1) : ℚ) : ℝ) →
      ∑ j ∈ Finset.range k, U j * ((mkRat 1 (2 * j + 1) : ℚ) : ℝ) ≤ (hi : ℝ) →
      ((oddGo one step a b lo hi k).1 : ℝ) ≤
          ∑ j ∈ Finset.range (oddGo one step a b lo hi k).2.2,
            U j * ((mkRat 1 (2 * j + 1) : ℚ) : ℝ) ∧
        ∑ j ∈ Finset.range (oddGo one step a b lo hi k).2.2,
            U j * ((mkRat 1 (2 * j + 1) : ℚ) : ℝ) ≤
          ((oddGo one step a b lo hi k).2.1 : ℝ) := by
  intro a b lo hi k
  generalize hm : (2 * one + 1 - (3 : ℤ) ^ (2 * k + 1)).toNat = m
  induction m using Nat.strong_induction_on generalizing a b lo hi k with
  | _ m ih =>
    intro ha hb hlo hhi
    rw [oddGo]
    by_cases h : (3 : ℤ) ^ (2 * k + 1) ≤ 2 * one
    · simp only [dif_pos h]
      obtain ⟨t1, t2⟩ := scale_sound (mkRat 1 (2 * k + 1)) ha hb
      obtain ⟨n1, n2⟩ := scale_sound step ha hb
      refine ih _ ?_ _ _ _ _ (k + 1) rfl ?_ ?_ ?_ ?_
      · have h3 : (3 : ℤ) ^ (2 * (k + 1) + 1) = 3 ^ (2 * k + 1) * 3 * 3 := by
          rw [show 2 * (k + 1) + 1 = (2 * k + 1) + 1 + 1 from by omega, pow_succ, pow_succ]
        have hp : (0 : ℤ) < 3 ^ (2 * k + 1) := by positivity
        rw [h3]
        omega
      · rw [hU]
        exact n1
      · rw [hU]
        exact n2
      · rw [Finset.sum_range_succ]
        push_cast
        linarith
      · rw [Finset.sum_range_succ]
        push_cast
        linarith
    · simp only [dif_neg h]
      exact ⟨hlo, hhi⟩

/-! ## The tail -/

/-- When term `j` is at most `(1/3) (1/9)^j` in size, the sum differs from the sum of its
first `K` terms by at most `(9/8) / 3^(2K+1)`. -/
theorem tail_bound (g : ℕ → ℝ) (S : ℝ) (hS : HasSum g S)
    (hg : ∀ j, |g j| ≤ 1 / 3 * (1 / 9) ^ j) (K : ℕ) :
    |S - ∑ j ∈ Finset.range K, g j| ≤ 9 / 8 / 3 ^ (2 * K + 1) := by
  have h1 : HasSum (fun j => g (j + K)) (S - ∑ j ∈ Finset.range K, g j) :=
    (hasSum_nat_add_iff' K).2 hS
  have h2 : HasSum (fun j : ℕ => 1 / 3 * (1 / 9) ^ K * (1 / 9 : ℝ) ^ j)
      (1 / 3 * (1 / 9) ^ K * (1 - 1 / 9)⁻¹) :=
    (hasSum_geometric_of_lt_one (by norm_num) (by norm_num)).mul_left _
  have h3 := tsum_of_norm_bounded h2 (fun j => by
    rw [Real.norm_eq_abs]
    calc |g (j + K)| ≤ 1 / 3 * (1 / 9) ^ (j + K) := hg _
      _ = 1 / 3 * (1 / 9) ^ K * (1 / 9) ^ j := by rw [pow_add]; ring)
  rw [h1.tsum_eq, Real.norm_eq_abs] at h3
  have e : (3 : ℝ) ^ (2 * K + 1) = 9 ^ K * 3 := by
    rw [pow_succ, pow_mul]
    norm_num
  have hpos : (0 : ℝ) < 9 ^ K := by positivity
  calc |S - ∑ j ∈ Finset.range K, g j| ≤ 1 / 3 * (1 / 9) ^ K * (1 - 1 / 9)⁻¹ := h3
    _ = 9 / 8 / 3 ^ (2 * K + 1) := by
      rw [e, one_div_pow]
      field_simp
      norm_num

/-! ## The series -/

/-- The enclosure holds the sum of any series whose term `j` is
`(sign * x * x)^j * x / (2 * j + 1)`, for `|x| ≤ 1/3` and `|sign| ≤ 1`. -/
theorem oddCore_holds (one : ℤ) (hpos : 0 < one) (x : ℚ) (σ : ℤ) (g : ℕ → ℝ) (S : ℝ)
    (hx : |(x : ℝ)| ≤ 1 / 3) (hσ : |(σ : ℝ)| ≤ 1)
    (hg : ∀ j : ℕ, g j = ((σ : ℝ) * x * x) ^ j * x / (2 * (j : ℝ) + 1))
    (hS : HasSum g S) :
    ((qd (oddGo one (qi σ * x * x) (scale one one x).1 (scale one one x).2 0 0 0).1 one -
        mkRat 9 8 / qi ((3 : ℤ) ^
          (2 * (oddGo one (qi σ * x * x) (scale one one x).1 (scale one one x).2 0 0 0).2.2 + 1)) :
        ℚ) : ℝ) ≤ S ∧
    S ≤ ((qd (oddGo one (qi σ * x * x) (scale one one x).1 (scale one one x).2 0 0 0).2.1 one +
        mkRat 9 8 / qi ((3 : ℤ) ^
          (2 * (oddGo one (qi σ * x * x) (scale one one x).1 (scale one one x).2 0 0 0).2.2 + 1)) :
        ℚ) : ℝ) := by
  have hposR : (0 : ℝ) < (one : ℝ) := by exact_mod_cast hpos
  have hstepR : ((qi σ * x * x : ℚ) : ℝ) = (σ : ℝ) * x * x := by
    rw [Rat.cast_mul, Rat.cast_mul, qi_cast]
  have hU : ∀ k : ℕ, (one : ℝ) * x * ((qi σ * x * x : ℚ) : ℝ) ^ (k + 1) =
      (one : ℝ) * x * ((qi σ * x * x : ℚ) : ℝ) ^ k * ((qi σ * x * x : ℚ) : ℝ) := fun k => by
    rw [pow_succ]
    ring
  have hW : ∀ j : ℕ, (one : ℝ) * x * ((qi σ * x * x : ℚ) : ℝ) ^ j *
      ((mkRat 1 (2 * j + 1) : ℚ) : ℝ) = (one : ℝ) * g j := fun j => by
    rw [hg, mkRat_one_cast, hstepR]
    ring
  obtain ⟨s1, s2⟩ := scale_sound (a := one) (b := one) (u := (one : ℝ)) x le_rfl le_rfl
  have inv := oddGo_inv one (qi σ * x * x)
    (fun k => (one : ℝ) * x * ((qi σ * x * x : ℚ) : ℝ) ^ k) hU
    (scale one one x).1 (scale one one x).2 0 0 0
    (by simpa using s1) (by simpa using s2) (by simp) (by simp)
  generalize oddGo one (qi σ * x * x) (scale one one x).1 (scale one one x).2 0 0 0 = r at inv ⊢
  obtain ⟨i1, i2⟩ := inv
  simp only [hW, ← Finset.mul_sum] at i1 i2
  -- The size of a term.
  have hq : |(σ : ℝ) * x * x| ≤ 1 / 9 := by
    rw [abs_mul, abs_mul]
    calc |(σ : ℝ)| * |(x : ℝ)| * |(x : ℝ)| ≤ 1 * (1 / 3) * (1 / 3) := by gcongr
      _ = 1 / 9 := by norm_num
  have hterm : ∀ j, |g j| ≤ 1 / 3 * (1 / 9) ^ j := fun j => by
    have hden : (1 : ℝ) ≤ |2 * (j : ℝ) + 1| := by
      rw [abs_of_nonneg (by positivity)]
      have : (0 : ℝ) ≤ (j : ℝ) := Nat.cast_nonneg j
      linarith
    rw [hg, abs_div, abs_mul, abs_pow]
    calc |(σ : ℝ) * x * x| ^ j * |(x : ℝ)| / |2 * (j : ℝ) + 1|
        ≤ |(σ : ℝ) * x * x| ^ j * |(x : ℝ)| / 1 :=
          div_le_div_of_nonneg_left (by positivity) one_pos hden
      _ ≤ (1 / 9) ^ j * (1 / 3) := by
          rw [div_one]
          exact mul_le_mul (pow_le_pow_left₀ (abs_nonneg _) hq j) hx (abs_nonneg _) (by positivity)
      _ = 1 / 3 * (1 / 9) ^ j := by ring
  have tb := abs_le.1 (tail_bound g S hS hterm r.2.2)
  have l1 : (r.1 : ℝ) / (one : ℝ) ≤ ∑ j ∈ Finset.range r.2.2, g j := by
    rw [div_le_iff₀ hposR]
    linarith
  have l2 : ∑ j ∈ Finset.range r.2.2, g j ≤ (r.2.1 : ℝ) / (one : ℝ) := by
    rw [le_div_iff₀ hposR]
    linarith
  constructor
  · rw [Rat.cast_sub, tail_cast, qd_cast _ _ hpos.le]
    linarith [tb.1]
  · rw [Rat.cast_add, tail_cast, qd_cast _ _ hpos.le]
    linarith [tb.2]

theorem oddSeries_holds (x : ℚ) (σ : ℤ) (p : ℕ) (g : ℕ → ℝ) (S : ℝ)
    (hx : |(x : ℝ)| ≤ 1 / 3) (hσ : |(σ : ℝ)| ≤ 1)
    (hg : ∀ j : ℕ, g j = ((σ : ℝ) * x * x) ^ j * x / (2 * (j : ℝ) + 1))
    (hS : HasSum g S) : (oddSeries x σ p).Holds S :=
  oddCore_holds ((2 : ℤ) ^ p) (by positivity) x σ g S hx hσ hg hS

/-- `Provable.oddSeries x 1 p` holds atanh x and `Provable.oddSeries x (-1) p` holds
arctan x, for `|x| ≤ 1/3`. -/
theorem oddSeries_spec : OddSeriesSpecOf oddSeries := by
  intro x p hx
  have hxR : |(x : ℝ)| ≤ 1 / 3 := by
    have h := (Rat.cast_le (K := ℝ)).2 hx
    rw [Rat.cast_abs] at h
    push_cast at h
    exact h
  have hx1 : |(x : ℝ)| < 1 := by linarith
  constructor
  · have h0 := (Real.hasSum_log_sub_log_of_abs_lt_one hx1).mul_left (1 / 2)
    have hS : (1 / 2 : ℝ) * (Real.log (1 + x) - Real.log (1 - x)) =
        Real.log ((1 + (x : ℝ)) / (1 - x)) / 2 := by
      have hb := abs_lt.1 hx1
      rw [Real.log_div (by linarith) (by linarith)]
      ring
    rw [hS] at h0
    refine oddSeries_holds x 1 p _ _ hxR (by norm_num) (fun j => ?_) h0
    have hne : (2 * (j : ℝ) + 1) ≠ 0 := by positivity
    push_cast
    field_simp
    ring
  · have h0 := Real.hasSum_arctan (x := (x : ℝ)) (by rw [Real.norm_eq_abs]; exact hx1)
    refine oddSeries_holds x (-1) p _ _ hxR (by norm_num) (fun j => ?_) h0
    push_cast
    ring

end Petra.Provable
