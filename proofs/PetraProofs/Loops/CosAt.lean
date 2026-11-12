/-
The kernel's `cosAt` encloses the cosine.

`cosAt` in kernel/Petra/Num.lean takes `y`, the size of `x`, reduces it to `r = y / 2 ^ s`
with `0 ≤ r ≤ 1/2`, sums the series for cos r in fixed point (`cosGo`), puts its remainder
on both sides, and doubles the angle `s` times (`dblGo`) by cos 2y = 2 cos² y - 1, each step
rounded outward. This file proves that it meets `CosAtSpecOf`: the interval it returns holds
cos x, for every rational x.

`cosGo` is a recursion on a count of rounds, `q + 1` of them. `cosGo_stops` proves that the
count never runs out before the loop's own test ends it, so the count changes no result.
-/
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Series
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Basic
import Mathlib.Analysis.SpecificLimits.Basic
import PetraProofs.Spec
import PetraProofs.Loops.OddSeries

namespace Petra.Loops

/-! ## `Int.fdiv`

`OddSeries.lean` proves what `scale` returns for a factor of either sign, and the casts. -/

/-- `Int.fdiv` by a positive number rounds down. -/
private theorem fdiv_floor (m d : ℤ) (hd : 0 < d) :
    ((Int.fdiv m d : ℤ) : ℝ) ≤ (m : ℝ) / (d : ℝ) := by
  rw [Int.fdiv_eq_ediv_of_nonneg _ hd.le]
  have h := Int.ediv_mul_le m (ne_of_gt hd)
  generalize m / d = X at h ⊢
  have hR : (X : ℝ) * (d : ℝ) ≤ (m : ℝ) := by exact_mod_cast h
  have hdR : (0 : ℝ) < (d : ℝ) := by exact_mod_cast hd
  rw [le_div_iff₀ hdR]
  exact hR

/-- Minus `Int.fdiv` of the negation rounds up. -/
private theorem fdiv_ceil (m d : ℤ) (hd : 0 < d) :
    (m : ℝ) / (d : ℝ) ≤ ((-(Int.fdiv (-m) d) : ℤ) : ℝ) := by
  rw [Int.fdiv_eq_ediv_of_nonneg _ hd.le]
  have h := Int.ediv_mul_le (-m) (ne_of_gt hd)
  generalize (-m) / d = X at h ⊢
  have hR : (X : ℝ) * (d : ℝ) ≤ -(m : ℝ) := by exact_mod_cast h
  have hdR : (0 : ℝ) < (d : ℝ) := by exact_mod_cast hd
  rw [div_le_iff₀ hdR]
  push_cast
  linarith

/-! ## The series -/

/-- Term `n` of the series for cos r. -/
private noncomputable def term (r : ℝ) (n : ℕ) : ℝ :=
  (-1) ^ n * r ^ (2 * n) / ((2 * n).factorial : ℝ)

private theorem fact_step (n : ℕ) :
    (2 * (n + 1) + 2).factorial = (2 * n + 2).factorial * ((2 * n + 3) * (2 * n + 4)) := by
  have e : 2 * (n + 1) + 2 = (2 * n + 2) + 1 + 1 := by ring
  rw [e, Nat.factorial_succ, Nat.factorial_succ]
  ring

/-- Term `n + 1` of the series from term `n`. -/
private theorem term_succ (r : ℝ) (n : ℕ) :
    term r n * (-(r * r) / (((2 * n + 1) * (2 * n + 2) : ℕ) : ℝ)) = term r (n + 1) := by
  unfold term
  have e : (2 * (n + 1)).factorial = (2 * n).factorial * ((2 * n + 1) * (2 * n + 2)) := by
    have e2 : 2 * (n + 1) = (2 * n) + 1 + 1 := by ring
    rw [e2, Nat.factorial_succ, Nat.factorial_succ]
    ring
  have h1 : (((2 * n).factorial : ℕ) : ℝ) ≠ 0 := by positivity
  have h2 : ((((2 * n + 1) * (2 * n + 2) : ℕ)) : ℝ) ≠ 0 := by positivity
  have e3 : r ^ (2 * (n + 1)) = r ^ (2 * n) * (r * r) := by
    rw [show 2 * (n + 1) = 2 * n + 2 from by ring, pow_add]
    ring
  rw [e, e3, pow_succ]
  push_cast at h2 ⊢
  field_simp

private theorem step_cast (m : ℚ) (k : ℕ) :
    ((m / qi (Int.ofNat k) : ℚ) : ℝ) = (m : ℝ) / ((k : ℕ) : ℝ) := by
  rw [Rat.cast_div, qi_cast]
  have e : Int.ofNat k = ((k : ℕ) : ℤ) := rfl
  rw [e, Int.cast_natCast]

/-- What the loop keeps, said of its result: `fact` is `(2n + 2)!`, and the two sums hold
the sum of the terms up to `n` times `one`. -/
private def CosInv (one : ℤ) (r : ℝ) (g : ℤ × ℤ × ℕ × ℤ) : Prop :=
  g.2.2.2 = ((2 * g.2.2.1 + 2).factorial : ℤ) ∧
    (g.1 : ℝ) ≤ (one : ℝ) * ∑ k ∈ Finset.range (g.2.2.1 + 1), term r k ∧
    (one : ℝ) * ∑ k ∈ Finset.range (g.2.2.1 + 1), term r k ≤ (g.2.1 : ℝ)

private theorem cosGo_inv (one : ℤ) (r : ℚ) :
    ∀ (rounds : ℕ) (ta tb a b : ℤ) (n : ℕ) (fact : ℤ),
      fact = ((2 * n + 2).factorial : ℤ) →
      (ta : ℝ) ≤ (one : ℝ) * term (r : ℝ) n →
      (one : ℝ) * term (r : ℝ) n ≤ (tb : ℝ) →
      (a : ℝ) ≤ (one : ℝ) * ∑ k ∈ Finset.range (n + 1), term (r : ℝ) k →
      (one : ℝ) * ∑ k ∈ Finset.range (n + 1), term (r : ℝ) k ≤ (b : ℝ) →
      CosInv one (r : ℝ) (cosGo one (-(r * r)) rounds ta tb a b n fact) := by
  intro rounds
  induction rounds with
  | zero =>
    intro ta tb a b n fact hf _ _ ha hb
    rw [cosGo]
    exact ⟨hf, ha, hb⟩
  | succ rounds ih =>
    intro ta tb a b n fact hf hta htb ha hb
    rw [cosGo]
    by_cases h : (4 : ℤ) ^ n * fact ≤ one
    · simp only [if_pos h]
      obtain ⟨t1, t2⟩ :=
        scale_sound (-(r * r) / qi (Int.ofNat ((2 * n + 1) * (2 * n + 2)))) hta htb
      have hm : ((-(r * r) : ℚ) : ℝ) = -((r : ℝ) * (r : ℝ)) := by push_cast; ring
      rw [step_cast, mul_assoc, hm, term_succ] at t1 t2
      refine ih _ _ _ _ _ _ ?_ t1 t2 ?_ ?_
      · have e : Int.ofNat ((2 * n + 3) * (2 * n + 4)) = (((2 * n + 3) * (2 * n + 4) : ℕ) : ℤ) :=
          rfl
        rw [hf, e, fact_step]
        push_cast
        ring
      · rw [Finset.sum_range_succ, Int.cast_add]
        linarith
      · rw [Finset.sum_range_succ, Int.cast_add]
        linarith
    · simp only [if_neg h]
      exact ⟨hf, ha, hb⟩

/-- The rounds do not run out: when `fact` is positive and the rounds left are more than
`q - n`, the loop ends because its test fails. So `q + 1` rounds from `n = 0` give what a
loop with no count gives. -/
theorem cosGo_stops (q : ℕ) (m : ℚ) :
    ∀ (rounds : ℕ) (ta tb a b : ℤ) (n : ℕ) (fact : ℤ), 1 ≤ fact → q + 1 ≤ rounds + n →
      ¬ ((4 : ℤ) ^ (cosGo ((2 : ℤ) ^ q) m rounds ta tb a b n fact).2.2.1 *
        (cosGo ((2 : ℤ) ^ q) m rounds ta tb a b n fact).2.2.2 ≤ (2 : ℤ) ^ q) := by
  intro rounds
  induction rounds with
  | zero =>
    intro ta tb a b n fact hf hn
    rw [cosGo]
    have h1 : (2 : ℤ) ^ q < 2 ^ n := pow_lt_pow_right₀ (by norm_num) (by omega)
    have h2 : (2 : ℤ) ^ n ≤ 4 ^ n := pow_le_pow_left₀ (by norm_num) (by norm_num) n
    have h3 : (0 : ℤ) < 4 ^ n := by positivity
    show ¬ ((4 : ℤ) ^ n * fact ≤ 2 ^ q)
    nlinarith
  | succ rounds ih =>
    intro ta tb a b n fact hf hn
    rw [cosGo]
    by_cases h : (4 : ℤ) ^ n * fact ≤ 2 ^ q
    · simp only [if_pos h]
      refine ih _ _ _ _ _ _ ?_ (by omega)
      have e : Int.ofNat ((2 * n + 3) * (2 * n + 4)) = (((2 * n + 3) * (2 * n + 4) : ℕ) : ℤ) :=
        rfl
      rw [e]
      have : (1 : ℤ) ≤ (((2 * n + 3) * (2 * n + 4) : ℕ) : ℤ) := by
        exact_mod_cast Nat.succ_le_of_lt (Nat.mul_pos (by omega) (by omega))
      nlinarith
    · simp only [if_neg h]
      exact h

/-- The size of a term. -/
private theorem abs_term (r : ℝ) (k : ℕ) :
    |term r k| = (r ^ 2) ^ k / ((2 * k).factorial : ℝ) := by
  unfold term
  rw [abs_div, abs_mul, abs_pow, abs_neg, abs_one, one_pow, one_mul, pow_mul, abs_pow,
    abs_of_nonneg (sq_nonneg r), Nat.abs_cast]

/-- The remainder of the series: for `|r| ≤ 1/2`, cos r differs from the sum of the terms
up to `n` by at most `1 / (4^n (2n + 2)!)`. Term `j` is at most `(1/4)^j / (2j)!` in size,
so the terms after `n` are under a geometric series. -/
private theorem cos_tail (r : ℝ) (hr : |r| ≤ 1 / 2) (n : ℕ) :
    |Real.cos r - ∑ k ∈ Finset.range (n + 1), term r k| ≤
      1 / (4 ^ n * ((2 * n + 2).factorial : ℝ)) := by
  have hS : HasSum (term r) (Real.cos r) := Real.hasSum_cos r
  have h1 : HasSum (fun j => term r (j + (n + 1)))
      (Real.cos r - ∑ k ∈ Finset.range (n + 1), term r k) :=
    (hasSum_nat_add_iff' (n + 1)).2 hS
  have h2 : HasSum
      (fun j : ℕ => (1 / 4 : ℝ) ^ (n + 1) / ((2 * n + 2).factorial : ℝ) * (1 / 4 : ℝ) ^ j)
      ((1 / 4 : ℝ) ^ (n + 1) / ((2 * n + 2).factorial : ℝ) * (1 - 1 / 4)⁻¹) :=
    (hasSum_geometric_of_lt_one (by norm_num) (by norm_num)).mul_left _
  have hr2 : r ^ 2 ≤ 1 / 4 := by
    have hb := abs_le.1 hr
    nlinarith [hb.1, hb.2]
  have hbound : ∀ j : ℕ, ‖term r (j + (n + 1))‖ ≤
      (1 / 4 : ℝ) ^ (n + 1) / ((2 * n + 2).factorial : ℝ) * (1 / 4 : ℝ) ^ j := by
    intro j
    have hden : ((2 * n + 2).factorial : ℝ) ≤ ((2 * (j + (n + 1))).factorial : ℝ) := by
      exact_mod_cast Nat.factorial_le (by omega)
    have hnum : (r ^ 2) ^ (j + (n + 1)) ≤ (1 / 4 : ℝ) ^ (j + (n + 1)) :=
      pow_le_pow_left₀ (sq_nonneg r) hr2 _
    rw [Real.norm_eq_abs, abs_term]
    calc (r ^ 2) ^ (j + (n + 1)) / ((2 * (j + (n + 1))).factorial : ℝ)
        ≤ (1 / 4 : ℝ) ^ (j + (n + 1)) / ((2 * n + 2).factorial : ℝ) :=
          div_le_div₀ (by positivity) hnum (by positivity) hden
      _ = (1 / 4 : ℝ) ^ (n + 1) / ((2 * n + 2).factorial : ℝ) * (1 / 4 : ℝ) ^ j := by
          rw [pow_add]
          ring
  have h3 := tsum_of_norm_bounded h2 hbound
  rw [h1.tsum_eq, Real.norm_eq_abs] at h3
  have hF : (0 : ℝ) < ((2 * n + 2).factorial : ℝ) := by positivity
  have h4 : (0 : ℝ) < 4 ^ n := by positivity
  calc |Real.cos r - ∑ k ∈ Finset.range (n + 1), term r k|
      ≤ (1 / 4 : ℝ) ^ (n + 1) / ((2 * n + 2).factorial : ℝ) * (1 - 1 / 4)⁻¹ := h3
    _ = 1 / 3 * (1 / (4 ^ n * ((2 * n + 2).factorial : ℝ))) := by
        rw [pow_succ, one_div_pow]
        field_simp
        norm_num
    _ ≤ 1 / (4 ^ n * ((2 * n + 2).factorial : ℝ)) := by
        have : (0 : ℝ) ≤ 1 / (4 ^ n * ((2 * n + 2).factorial : ℝ)) := by positivity
        linarith

/-! ## The doublings -/

/-- `dblGo` keeps an enclosure of `one * cos y` an enclosure through `j` doublings of the
angle. -/
private theorem dblGo_inv (one : ℤ) (hone : 0 < one) :
    ∀ (j : ℕ) (a b : ℤ) (y : ℝ), (a : ℝ) ≤ (one : ℝ) * Real.cos y →
      (one : ℝ) * Real.cos y ≤ (b : ℝ) →
      ((dblGo one j a b).1 : ℝ) ≤ (one : ℝ) * Real.cos (2 ^ j * y) ∧
        (one : ℝ) * Real.cos (2 ^ j * y) ≤ ((dblGo one j a b).2 : ℝ) := by
  have hOR : (0 : ℝ) < (one : ℝ) := by exact_mod_cast hone
  have hne : (one : ℝ) ≠ 0 := hOR.ne'
  intro j
  induction j with
  | zero =>
    intro a b y ha hb
    rw [dblGo]
    simpa using ⟨ha, hb⟩
  | succ j ih =>
    intro a b y ha hb
    rw [dblGo]
    have e : (2 : ℝ) ^ (j + 1) * y = 2 ^ j * (2 * y) := by
      rw [pow_succ]
      ring
    rw [e]
    -- the square of `one * cos y` lies between `low` and `high`
    have hlow : (((if 0 ≤ a then a * a else if b ≤ 0 then b * b else 0 : ℤ)) : ℝ) ≤
        (one : ℝ) * Real.cos y * ((one : ℝ) * Real.cos y) := by
      split_ifs with h0 h1
      · have h0' : (0 : ℝ) ≤ (a : ℝ) := by exact_mod_cast h0
        push_cast
        nlinarith
      · have h1' : (b : ℝ) ≤ 0 := by exact_mod_cast h1
        push_cast
        nlinarith
      · push_cast
        exact mul_self_nonneg _
    have hhigh : (one : ℝ) * Real.cos y * ((one : ℝ) * Real.cos y) ≤
        (((if a * a ≤ b * b then b * b else a * a : ℤ)) : ℝ) := by
      have hmax : (one : ℝ) * Real.cos y * ((one : ℝ) * Real.cos y) ≤
          max ((a : ℝ) * a) ((b : ℝ) * b) := by
        rcases le_total 0 ((one : ℝ) * Real.cos y) with h | h
        · exact le_max_of_le_right (by nlinarith)
        · exact le_max_of_le_left (by nlinarith)
      split_ifs with h
      · have h' : (a : ℝ) * a ≤ (b : ℝ) * b := by exact_mod_cast h
        rw [max_eq_right h'] at hmax
        push_cast
        exact hmax
      · have h' : (b : ℝ) * b ≤ (a : ℝ) * a := by exact_mod_cast (not_le.mp h).le
        rw [max_eq_left h'] at hmax
        push_cast
        exact hmax
    generalize (if 0 ≤ a then a * a else if b ≤ 0 then b * b else 0 : ℤ) = low at hlow ⊢
    generalize (if a * a ≤ b * b then b * b else a * a : ℤ) = high at hhigh ⊢
    have hcos : (one : ℝ) * Real.cos (2 * y) =
        2 * ((one : ℝ) * Real.cos y * ((one : ℝ) * Real.cos y) / (one : ℝ)) - (one : ℝ) := by
      rw [Real.cos_two_mul]
      field_simp
    refine ih _ _ (2 * y) ?_ ?_
    · have hf := fdiv_floor low one hone
      have hd : (low : ℝ) / (one : ℝ) ≤
          (one : ℝ) * Real.cos y * ((one : ℝ) * Real.cos y) / (one : ℝ) :=
        div_le_div_of_nonneg_right hlow hOR.le
      rw [hcos]
      push_cast
      linarith
    · split_ifs with hclamp
      · have hf := fdiv_ceil high one hone
        have hd : (one : ℝ) * Real.cos y * ((one : ℝ) * Real.cos y) / (one : ℝ) ≤
            (high : ℝ) / (one : ℝ) :=
          div_le_div_of_nonneg_right hhigh hOR.le
        rw [hcos]
        push_cast at hf ⊢
        linarith
      · exact mul_le_of_le_one_right hOR.le (Real.cos_le_one _)

/-! ## The enclosure -/

/-- For `|r| ≤ 1/2` and `y = 2^s r`, `cosInt r s q` holds `2^q cos y`. -/
private theorem cosInt_spec (y : ℝ) (r : ℚ) (s q : ℕ) (hr : |(r : ℝ)| ≤ 1 / 2)
    (hy : y = 2 ^ s * (r : ℝ)) :
    ((cosInt r s q).1 : ℝ) ≤ (((2 : ℤ) ^ q : ℤ) : ℝ) * Real.cos y ∧
      (((2 : ℤ) ^ q : ℤ) : ℝ) * Real.cos y ≤ ((cosInt r s q).2 : ℝ) := by
  have hone : (0 : ℤ) < (2 : ℤ) ^ q := by positivity
  unfold cosInt
  simp only []
  generalize (2 : ℤ) ^ q = one at hone ⊢
  have hOR : (0 : ℝ) < (one : ℝ) := by exact_mod_cast hone
  have inv := cosGo_inv one r (q + 1) one one one one 0 2 (by simp [Nat.factorial])
    (by simp [term]) (by simp [term]) (by simp [term]) (by simp [term])
  generalize cosGo one (-(r * r)) (q + 1) one one one one 0 2 = g at inv ⊢
  obtain ⟨hf, ha, hb⟩ := inv
  have hD : (0 : ℤ) < 4 ^ g.2.2.1 * g.2.2.2 := by
    rw [hf]
    positivity
  have hrest := fdiv_ceil one (4 ^ g.2.2.1 * g.2.2.2) hD
  have e : (one : ℝ) / ((4 ^ g.2.2.1 * g.2.2.2 : ℤ) : ℝ) =
      (one : ℝ) * (1 / (4 ^ g.2.2.1 * (((2 * g.2.2.1 + 2).factorial : ℕ) : ℝ))) := by
    rw [hf]
    push_cast
    ring
  rw [e] at hrest
  obtain ⟨t1, t2⟩ := abs_le.1 (cos_tail (r : ℝ) hr g.2.2.1)
  have t1' := mul_le_mul_of_nonneg_left t1 hOR.le
  have t2' := mul_le_mul_of_nonneg_left t2 hOR.le
  rw [hy]
  refine dblGo_inv one hone s _ _ (r : ℝ) ?_ ?_
  · rw [Int.cast_sub]
    nlinarith
  · rw [Int.cast_add]
    nlinarith

/-- Two whole numbers around `one * v`, each over `one`, are an interval that holds `v`. -/
private theorem holds_qd {a b one : ℤ} {v : ℝ} (hone : 0 < one) (h1 : (a : ℝ) ≤ (one : ℝ) * v)
    (h2 : (one : ℝ) * v ≤ (b : ℝ)) : (⟨qd a one, qd b one⟩ : Iv).Holds v := by
  have hOR : (0 : ℝ) < (one : ℝ) := by exact_mod_cast hone
  constructor
  · show ((qd a one : ℚ) : ℝ) ≤ v
    rw [qd_cast _ _ hone.le, div_le_iff₀ hOR]
    linarith
  · show v ≤ ((qd b one : ℚ) : ℝ)
    rw [qd_cast _ _ hone.le, le_div_iff₀ hOR]
    linarith

private theorem bitlen_bound (c : ℕ) : c < 2 ^ bitlen c := by
  unfold bitlen
  by_cases h : c = 0
  · subst h
    simp
  · have hne : (c == 0) = false := by simpa using h
    simp only [hne, Bool.false_eq_true, if_false]
    exact Nat.lt_log2_self

/-- The kernel's `cosAt x p` holds cos x. -/
theorem cosAt_spec : CosAtSpecOf cosAt := by
  intro x p
  unfold cosAt
  simp only []
  -- the cosine is even, so it is that of the size of `x`
  have hcos : Real.cos (x : ℝ) = Real.cos (((if x < 0 then -x else x : ℚ)) : ℝ) := by
    split_ifs
    · push_cast
      exact (Real.cos_neg _).symm
    · rfl
  have hy0 : (0 : ℚ) ≤ (if x < 0 then -x else x) := by
    split_ifs with h
    · linarith
    · exact not_lt.mp h
  rw [hcos]
  generalize (if x < 0 then -x else x : ℚ) = y at hy0 ⊢
  -- the reduced argument is at most 1/2
  have h1 : y ≤ ((y.ceil : ℤ) : ℚ) := Rat.ceil_le_iff.1 le_rfl
  have h2 : y.ceil ≤ ((y.ceil.toNat : ℕ) : ℤ) := Int.self_le_toNat _
  have h1R : (y : ℝ) ≤ ((y.ceil : ℤ) : ℝ) := by exact_mod_cast h1
  have h2R : ((y.ceil : ℤ) : ℝ) ≤ ((y.ceil.toNat : ℕ) : ℝ) := by exact_mod_cast h2
  have h3 : ((y.ceil.toNat : ℕ) : ℝ) < (2 : ℝ) ^ bitlen y.ceil.toNat := by
    exact_mod_cast bitlen_bound y.ceil.toNat
  have hyR : (0 : ℝ) ≤ (y : ℝ) := by exact_mod_cast hy0
  have hrR : ((y / qi ((2 : ℤ) ^ (bitlen y.ceil.toNat + 1)) : ℚ) : ℝ) =
      (y : ℝ) / (2 : ℝ) ^ (bitlen y.ceil.toNat + 1) := by
    rw [Rat.cast_div, qi_cast]
    push_cast
    rfl
  have hr : |((y / qi ((2 : ℤ) ^ (bitlen y.ceil.toNat + 1)) : ℚ) : ℝ)| ≤ 1 / 2 := by
    rw [hrR, abs_of_nonneg (by positivity), div_le_iff₀ (by positivity), pow_succ]
    linarith
  have hye : (y : ℝ) = 2 ^ (bitlen y.ceil.toNat + 1) *
      ((y / qi ((2 : ℤ) ^ (bitlen y.ceil.toNat + 1)) : ℚ) : ℝ) := by
    rw [hrR]
    field_simp
  obtain ⟨e1, e2⟩ := cosInt_spec (y : ℝ) _ (bitlen y.ceil.toNat + 1)
    (p + 2 * (bitlen y.ceil.toNat + 1) + 8) hr hye
  exact holds_qd (by positivity) e1 e2

end Petra.Loops
