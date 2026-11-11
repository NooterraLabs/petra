/-
The kernel's `expAt` encloses the exponential.

`expAt` in kernel/Petra/Num.lean reduces `x` to `r = x / 2 ^ s` with `0 ≤ r ≤ 1/2`, sums the
series for exp r in fixed point (`expGo`), adds its remainder, and squares `s` times
(`sqGo`), each step rounded outward. For `x < 0` it returns `1 / exp (-x)`. This file proves
that it meets `ExpAtSpecOf`: the interval it returns holds exp x.

`expGo` is a recursion on a count of rounds, `q + 1` of them. `expGo_stops` proves that the
count never runs out before the loop's own test ends it, so the count changes no result.
-/
import Mathlib.Analysis.Complex.Exponential
import Mathlib.Analysis.SpecialFunctions.Exp
import PetraProofs.Spec

namespace Petra.Loops

/-! ## Casts, `Int.fdiv` and `scale`

`OddSeries.lean` proves the same facts about `scale`. They are repeated here, as private
theorems, so that each file checks alone. -/

private theorem qi_eq (n : ℤ) : qi n = (n : ℚ) := by
  unfold qi
  rw [Rat.mkRat_eq_div]
  simp

private theorem qd_cast (n d : ℤ) (hd : 0 ≤ d) : ((qd n d : ℚ) : ℝ) = (n : ℝ) / (d : ℝ) := by
  unfold qd
  rw [Rat.mkRat_eq_div]
  have h1 : ((d.toNat : ℕ) : ℤ) = d := Int.toNat_of_nonneg hd
  have h2 : ((d.toNat : ℕ) : ℝ) = (d : ℝ) := by exact_mod_cast h1
  push_cast
  rw [h2]

/-- `Int.fdiv` by a positive number rounds down. -/
private theorem fdiv_cast_le (m d : ℤ) (hd : 0 < d) :
    ((Int.fdiv m d : ℤ) : ℝ) ≤ (m : ℝ) / (d : ℝ) := by
  rw [Int.fdiv_eq_ediv_of_nonneg _ hd.le]
  have h := Int.ediv_mul_le m (ne_of_gt hd)
  generalize m / d = X at h ⊢
  have hR : (X : ℝ) * (d : ℝ) ≤ (m : ℝ) := by exact_mod_cast h
  have hdR : (0 : ℝ) < (d : ℝ) := by exact_mod_cast hd
  rw [le_div_iff₀ hdR]
  exact hR

/-- Minus `Int.fdiv` of the negation rounds up. -/
private theorem le_neg_fdiv_cast (m d : ℤ) (hd : 0 < d) :
    (m : ℝ) / (d : ℝ) ≤ ((-(Int.fdiv (-m) d) : ℤ) : ℝ) := by
  rw [Int.fdiv_eq_ediv_of_nonneg _ hd.le]
  have h := Int.ediv_mul_le (-m) (ne_of_gt hd)
  generalize (-m) / d = X at h ⊢
  have hR : (X : ℝ) * (d : ℝ) ≤ -(m : ℝ) := by exact_mod_cast h
  have hdR : (0 : ℝ) < (d : ℝ) := by exact_mod_cast hd
  rw [div_le_iff₀ hdR]
  push_cast
  linarith

private theorem den_pos' (c : ℚ) : (0 : ℤ) < Int.ofNat c.den := by
  have e : Int.ofNat c.den = ((c.den : ℕ) : ℤ) := rfl
  rw [e]
  exact_mod_cast c.den_pos

private theorem mul_cast_eq (m : ℤ) (c : ℚ) :
    ((m * c.num : ℤ) : ℝ) / ((Int.ofNat c.den : ℤ) : ℝ) = (m : ℝ) * (c : ℝ) := by
  have e : Int.ofNat c.den = ((c.den : ℕ) : ℤ) := rfl
  rw [e, Rat.cast_def]
  push_cast
  ring

private theorem fdiv_le (m : ℤ) (c : ℚ) :
    ((Int.fdiv (m * c.num) (Int.ofNat c.den) : ℤ) : ℝ) ≤ (m : ℝ) * (c : ℝ) := by
  rw [← mul_cast_eq]
  exact fdiv_cast_le _ _ (den_pos' c)

private theorem le_neg_fdiv (m : ℤ) (c : ℚ) :
    (m : ℝ) * (c : ℝ) ≤ ((-(Int.fdiv (-(m * c.num)) (Int.ofNat c.den)) : ℤ) : ℝ) := by
  rw [← mul_cast_eq]
  exact le_neg_fdiv_cast _ _ (den_pos' c)

private theorem scale_of_nonneg {a b : ℤ} {c : ℚ} (hc : 0 ≤ c) :
    scale a b c =
      (Int.fdiv (a * c.num) (Int.ofNat c.den), -Int.fdiv (-(b * c.num)) (Int.ofNat c.den)) := by
  unfold scale
  simp only [if_pos hc]

/-- For `c ≥ 0`, `scale a b c` holds `u * c` for every `u` in `[a, b]`. -/
private theorem scale_sound {a b : ℤ} {u : ℝ} {c : ℚ} (hc : 0 ≤ c) (h1 : (a : ℝ) ≤ u)
    (h2 : u ≤ (b : ℝ)) :
    ((scale a b c).1 : ℝ) ≤ u * c ∧ u * c ≤ ((scale a b c).2 : ℝ) := by
  rw [scale_of_nonneg hc]
  have hcR : (0 : ℝ) ≤ (c : ℝ) := by exact_mod_cast hc
  exact ⟨(fdiv_le a c).trans (mul_le_mul_of_nonneg_right h1 hcR),
    (mul_le_mul_of_nonneg_right h2 hcR).trans (le_neg_fdiv b c)⟩

private theorem scale_fst_nonneg {a b : ℤ} {c : ℚ} (ha : 0 ≤ a) (hc : 0 ≤ c) :
    0 ≤ (scale a b c).1 := by
  rw [scale_of_nonneg hc]
  show 0 ≤ Int.fdiv (a * c.num) (Int.ofNat c.den)
  rw [Int.fdiv_eq_ediv_of_nonneg _ (den_pos' c).le]
  exact Int.ediv_nonneg (Int.mul_nonneg ha (Rat.num_nonneg.2 hc)) (den_pos' c).le

/-! ## The series -/

private theorem step_nonneg {r : ℚ} (hr0 : 0 ≤ r) (n : ℕ) : 0 ≤ r / qi (Int.ofNat (n + 1)) := by
  rw [qi_eq]
  have e : Int.ofNat (n + 1) = ((n + 1 : ℕ) : ℤ) := rfl
  rw [e]
  exact div_nonneg hr0 (by positivity)

private theorem step_cast (r : ℚ) (n : ℕ) :
    ((r / qi (Int.ofNat (n + 1)) : ℚ) : ℝ) = (r : ℝ) / ((n : ℝ) + 1) := by
  rw [qi_eq]
  have e : Int.ofNat (n + 1) = ((n + 1 : ℕ) : ℤ) := rfl
  rw [e]
  push_cast
  rfl

/-- Term `n + 1` of the series from term `n`. -/
private theorem term_succ (r : ℝ) (n : ℕ) :
    r ^ n / (n.factorial : ℝ) * (r / ((n : ℝ) + 1)) = r ^ (n + 1) / ((n + 1).factorial : ℝ) := by
  have h1 : ((n.factorial : ℕ) : ℝ) ≠ 0 := by positivity
  have h2 : ((n : ℝ) + 1) ≠ 0 := by positivity
  rw [Nat.factorial_succ, pow_succ]
  push_cast
  field_simp

/-- What the loop keeps, said of its result: `fact` is `(n + 1)!`, the lower sum is at
least `one`, and the two sums hold the sum of the terms up to `n` times `one`. -/
private def ExpInv (one : ℤ) (r : ℚ) (g : ℤ × ℤ × ℕ × ℤ) : Prop :=
  g.2.2.2 = ((g.2.2.1 + 1).factorial : ℤ) ∧ one ≤ g.1 ∧
    (g.1 : ℝ) ≤ (one : ℝ) * ∑ m ∈ Finset.range (g.2.2.1 + 1), (r : ℝ) ^ m / (m.factorial : ℝ) ∧
    (one : ℝ) * ∑ m ∈ Finset.range (g.2.2.1 + 1), (r : ℝ) ^ m / (m.factorial : ℝ) ≤ (g.2.1 : ℝ)

private theorem expGo_inv (one : ℤ) (r : ℚ) (hr0 : 0 ≤ r) :
    ∀ (rounds : ℕ) (ta tb a b : ℤ) (n : ℕ) (fact : ℤ),
      fact = ((n + 1).factorial : ℤ) → 0 ≤ ta →
      (ta : ℝ) ≤ (one : ℝ) * ((r : ℝ) ^ n / (n.factorial : ℝ)) →
      (one : ℝ) * ((r : ℝ) ^ n / (n.factorial : ℝ)) ≤ (tb : ℝ) →
      one ≤ a →
      (a : ℝ) ≤ (one : ℝ) * ∑ m ∈ Finset.range (n + 1), (r : ℝ) ^ m / (m.factorial : ℝ) →
      (one : ℝ) * ∑ m ∈ Finset.range (n + 1), (r : ℝ) ^ m / (m.factorial : ℝ) ≤ (b : ℝ) →
      ExpInv one r (expGo one r rounds ta tb a b n fact) := by
  intro rounds
  induction rounds with
  | zero =>
    intro ta tb a b n fact hf _ _ _ ha ha2 hb2
    unfold ExpInv
    rw [expGo]
    exact ⟨hf, ha, ha2, hb2⟩
  | succ rounds ih =>
    intro ta tb a b n fact hf hta hta2 htb2 ha ha2 hb2
    rw [expGo]
    by_cases h : (2 : ℤ) ^ n * fact ≤ one
    · simp only [if_pos h]
      have hc := step_nonneg hr0 n
      obtain ⟨t1, t2⟩ := scale_sound hc hta2 htb2
      rw [step_cast, mul_assoc, term_succ] at t1 t2
      have t0 := scale_fst_nonneg (b := tb) hta hc
      refine ih _ _ _ _ _ _ ?_ t0 t1 t2 ?_ ?_ ?_
      · have e : Int.ofNat (n + 1 + 1) = ((n + 1 + 1 : ℕ) : ℤ) := rfl
        rw [hf, e, Nat.factorial_succ (n + 1)]
        push_cast
        ring
      · omega
      · rw [Finset.sum_range_succ, mul_add]
        push_cast
        linarith
      · rw [Finset.sum_range_succ, mul_add]
        push_cast
        linarith
    · simp only [if_neg h]
      unfold ExpInv
      exact ⟨hf, ha, ha2, hb2⟩

/-- The rounds do not run out: when `fact` is positive and the rounds left are more than
`q - n`, the loop ends because its test fails. So `q + 1` rounds from `n = 0` give what a
loop with no count gives. -/
theorem expGo_stops (q : ℕ) (r : ℚ) :
    ∀ (rounds : ℕ) (ta tb a b : ℤ) (n : ℕ) (fact : ℤ), 1 ≤ fact → q + 1 ≤ rounds + n →
      ¬ ((2 : ℤ) ^ (expGo ((2 : ℤ) ^ q) r rounds ta tb a b n fact).2.2.1 *
        (expGo ((2 : ℤ) ^ q) r rounds ta tb a b n fact).2.2.2 ≤ (2 : ℤ) ^ q) := by
  intro rounds
  induction rounds with
  | zero =>
    intro ta tb a b n fact hf hn
    rw [expGo]
    have h1 : (2 : ℤ) ^ q < 2 ^ n := pow_lt_pow_right₀ (by norm_num) (by omega)
    have h2 : (0 : ℤ) < 2 ^ n := by positivity
    show ¬ ((2 : ℤ) ^ n * fact ≤ 2 ^ q)
    nlinarith
  | succ rounds ih =>
    intro ta tb a b n fact hf hn
    rw [expGo]
    by_cases h : (2 : ℤ) ^ n * fact ≤ 2 ^ q
    · simp only [if_pos h]
      refine ih _ _ _ _ _ _ ?_ (by omega)
      have e : Int.ofNat (n + 1 + 1) = ((n + 1 + 1 : ℕ) : ℤ) := rfl
      rw [e]
      have : (1 : ℤ) ≤ ((n + 1 + 1 : ℕ) : ℤ) := by exact_mod_cast Nat.succ_pos (n + 1)
      nlinarith
    · simp only [if_neg h]
      exact h

/-- The remainder of the series: for `0 ≤ r ≤ 1/2`, exp r is at most the sum of the terms
up to `n` plus `1 / (2^n (n + 1)!)`. -/
private theorem exp_le_sum_add (r : ℝ) (hr0 : 0 ≤ r) (hr : r ≤ 1 / 2) (n : ℕ) :
    Real.exp r ≤ ∑ m ∈ Finset.range (n + 1), r ^ m / (m.factorial : ℝ) +
      1 / (2 ^ n * ((n + 1).factorial : ℝ)) := by
  have h := Real.exp_bound' hr0 (by linarith) (Nat.succ_pos n)
  refine h.trans (add_le_add le_rfl ?_)
  have hF : (0 : ℝ) < ((n + 1).factorial : ℝ) := by positivity
  have hN : (1 : ℝ) ≤ ((n + 1 : ℕ) : ℝ) := by exact_mod_cast Nat.succ_pos n
  have h2 : (2 : ℝ) ^ n * r ^ (n + 1) ≤ 1 / 2 := by
    calc (2 : ℝ) ^ n * r ^ (n + 1) ≤ 2 ^ n * (1 / 2) ^ (n + 1) := by gcongr
      _ = 1 / 2 := by
        rw [pow_succ, one_div_pow]
        field_simp
  rw [div_le_div_iff₀ (by positivity) (by positivity), one_mul]
  calc r ^ (n + 1) * (((n + 1 : ℕ) : ℝ) + 1) * (2 ^ n * ((n + 1).factorial : ℝ))
      = (2 ^ n * r ^ (n + 1)) * ((((n + 1 : ℕ) : ℝ) + 1) * ((n + 1).factorial : ℝ)) := by ring
    _ ≤ 1 / 2 * ((((n + 1 : ℕ) : ℝ) + 1) * ((n + 1).factorial : ℝ)) := by gcongr
    _ ≤ ((n + 1).factorial : ℝ) * ((n + 1 : ℕ) : ℝ) := by
      nlinarith [mul_nonneg hF.le (sub_nonneg.2 hN)]

/-! ## The squarings -/

private theorem sqGo_inv (one : ℤ) (hone : 0 < one) :
    ∀ (j : ℕ) (a b : ℤ) (Y : ℝ), 0 ≤ Y → one ≤ a → (a : ℝ) ≤ (one : ℝ) * Y →
      (one : ℝ) * Y ≤ (b : ℝ) →
      one ≤ (sqGo one j a b).1 ∧ ((sqGo one j a b).1 : ℝ) ≤ (one : ℝ) * Y ^ (2 ^ j) ∧
        (one : ℝ) * Y ^ (2 ^ j) ≤ ((sqGo one j a b).2 : ℝ) := by
  have hOR : (0 : ℝ) < (one : ℝ) := by exact_mod_cast hone
  intro j
  induction j with
  | zero =>
    intro a b Y _ ha ha2 hb2
    rw [sqGo]
    simpa using ⟨ha, ha2, hb2⟩
  | succ j ih =>
    intro a b Y hY ha ha2 hb2
    rw [sqGo]
    have e : Y ^ (2 ^ (j + 1)) = (Y ^ 2) ^ (2 ^ j) := by rw [← pow_mul, ← pow_succ']
    rw [e]
    have haR : (0 : ℝ) ≤ (a : ℝ) := by exact_mod_cast hone.le.trans ha
    have hOY : (0 : ℝ) ≤ (one : ℝ) * Y := mul_nonneg hOR.le hY
    refine ih _ _ (Y ^ 2) (by positivity) ?_ ?_ ?_
    · rw [Int.fdiv_eq_ediv_of_nonneg _ hone.le]
      exact Int.le_ediv_of_mul_le hone (Int.mul_le_mul ha ha hone.le (hone.le.trans ha))
    · refine (fdiv_cast_le _ _ hone).trans ?_
      rw [div_le_iff₀ hOR]
      push_cast
      nlinarith
    · refine le_trans ?_ (le_neg_fdiv_cast _ _ hone)
      rw [le_div_iff₀ hOR]
      push_cast
      nlinarith

/-! ## The enclosure -/

/-- For `0 ≤ r ≤ 1/2` and `x = 2^s r`, `expInt r s q` holds `2^q exp x`, and its lower end
is at least `2^q`. -/
private theorem expInt_spec (x : ℝ) (r : ℚ) (s q : ℕ) (hr0 : 0 ≤ r) (hr : (r : ℝ) ≤ 1 / 2)
    (hx : x = ((2 ^ s : ℕ) : ℝ) * (r : ℝ)) :
    (2 : ℤ) ^ q ≤ (expInt r s q).1 ∧
      ((expInt r s q).1 : ℝ) ≤ (((2 : ℤ) ^ q : ℤ) : ℝ) * Real.exp x ∧
      (((2 : ℤ) ^ q : ℤ) : ℝ) * Real.exp x ≤ ((expInt r s q).2 : ℝ) := by
  have hone : (0 : ℤ) < (2 : ℤ) ^ q := by positivity
  unfold expInt
  simp only []
  generalize (2 : ℤ) ^ q = one at hone ⊢
  have hOR : (0 : ℝ) < (one : ℝ) := by exact_mod_cast hone
  have hr0R : (0 : ℝ) ≤ (r : ℝ) := by exact_mod_cast hr0
  have inv := expGo_inv one r hr0 (q + 1) one one one one 0 1 (by simp) hone.le (by simp)
    (by simp) le_rfl (by simp) (by simp)
  generalize expGo one r (q + 1) one one one one 0 1 = g at inv ⊢
  obtain ⟨hf, ha, ha2, hb2⟩ := inv
  have hD : (0 : ℤ) < 2 ^ g.2.2.1 * g.2.2.2 := by
    rw [hf]
    positivity
  have hrem := le_neg_fdiv_cast one (2 ^ g.2.2.1 * g.2.2.2) hD
  have hexp := exp_le_sum_add (r : ℝ) hr0R hr g.2.2.1
  have hlow := Real.sum_le_exp_of_nonneg hr0R (g.2.2.1 + 1)
  have ha3 : (g.1 : ℝ) ≤ (one : ℝ) * Real.exp (r : ℝ) :=
    ha2.trans (mul_le_mul_of_nonneg_left hlow hOR.le)
  have hb3 : (one : ℝ) * Real.exp (r : ℝ) ≤
      ((g.2.1 + -Int.fdiv (-one) (2 ^ g.2.2.1 * g.2.2.2) : ℤ) : ℝ) := by
    have e : (one : ℝ) / ((2 ^ g.2.2.1 * g.2.2.2 : ℤ) : ℝ) =
        (one : ℝ) * (1 / (2 ^ g.2.2.1 * (((g.2.2.1 + 1).factorial : ℕ) : ℝ))) := by
      rw [hf]
      push_cast
      ring
    rw [e] at hrem
    have h1 := mul_le_mul_of_nonneg_left hexp hOR.le
    rw [mul_add] at h1
    rw [Int.cast_add]
    linarith
  have sq := sqGo_inv one hone s g.1 _ (Real.exp (r : ℝ)) (Real.exp_pos _).le ha ha3 hb3
  have hxe : Real.exp x = Real.exp (r : ℝ) ^ (2 ^ s) := by
    rw [hx, Real.exp_nat_mul]
  rw [hxe]
  exact sq

private theorem lt_two_pow_bitlen (c : ℕ) : c < 2 ^ bitlen c := by
  unfold bitlen
  by_cases h : c = 0
  · subst h
    simp
  · have hne : (c == 0) = false := by simpa using h
    simp only [hne, Bool.false_eq_true, if_false]
    exact Nat.lt_log2_self

/-- The enclosure for `x ≥ 0`, and its lower end is positive. -/
theorem expPos_holds (x : ℚ) (hx : 0 ≤ x) (p : ℕ) :
    (expPos x p).Holds (Real.exp (x : ℝ)) ∧ (0 : ℝ) < ((expPos x p).lo : ℝ) := by
  -- The reduced argument is at most 1/2.
  have h1 : x ≤ ((x.ceil : ℤ) : ℚ) := Rat.ceil_le_iff.1 le_rfl
  have h2 : x.ceil ≤ ((x.ceil.toNat : ℕ) : ℤ) := Int.self_le_toNat _
  have h1R : (x : ℝ) ≤ ((x.ceil : ℤ) : ℝ) := by exact_mod_cast h1
  have h2R : ((x.ceil : ℤ) : ℝ) ≤ ((x.ceil.toNat : ℕ) : ℝ) := by exact_mod_cast h2
  have h3 : ((x.ceil.toNat : ℕ) : ℝ) < (2 : ℝ) ^ bitlen x.ceil.toNat := by
    exact_mod_cast lt_two_pow_bitlen x.ceil.toNat
  have hxR : (0 : ℝ) ≤ (x : ℝ) := by exact_mod_cast hx
  have hq : qi ((2 : ℤ) ^ (bitlen x.ceil.toNat + 1)) = (2 : ℚ) ^ (bitlen x.ceil.toNat + 1) := by
    rw [qi_eq]
    push_cast
    rfl
  have hr0 : 0 ≤ x / qi ((2 : ℤ) ^ (bitlen x.ceil.toNat + 1)) := by
    rw [hq]
    exact div_nonneg hx (by positivity)
  have hrR : ((x / qi ((2 : ℤ) ^ (bitlen x.ceil.toNat + 1)) : ℚ) : ℝ) =
      (x : ℝ) / (2 : ℝ) ^ (bitlen x.ceil.toNat + 1) := by
    rw [hq]
    push_cast
    rfl
  have hr : ((x / qi ((2 : ℤ) ^ (bitlen x.ceil.toNat + 1)) : ℚ) : ℝ) ≤ 1 / 2 := by
    rw [hrR, div_le_iff₀ (by positivity), pow_succ]
    linarith
  have hxe : (x : ℝ) = ((2 ^ (bitlen x.ceil.toNat + 1) : ℕ) : ℝ) *
      ((x / qi ((2 : ℤ) ^ (bitlen x.ceil.toNat + 1)) : ℚ) : ℝ) := by
    rw [hrR]
    push_cast
    field_simp
  obtain ⟨e1, e2, e3⟩ := expInt_spec (x : ℝ) _ (bitlen x.ceil.toNat + 1)
    (p + 2 * (bitlen x.ceil.toNat + 1) + 2 * x.ceil.toNat) hr0 hr hxe
  have hone : (0 : ℤ) < (2 : ℤ) ^ (p + 2 * (bitlen x.ceil.toNat + 1) + 2 * x.ceil.toNat) := by
    positivity
  have hOR : (0 : ℝ) <
      (((2 : ℤ) ^ (p + 2 * (bitlen x.ceil.toNat + 1) + 2 * x.ceil.toNat) : ℤ) : ℝ) := by
    exact_mod_cast hone
  have e1R : (((2 : ℤ) ^ (p + 2 * (bitlen x.ceil.toNat + 1) + 2 * x.ceil.toNat) : ℤ) : ℝ) ≤
      ((expInt (x / qi ((2 : ℤ) ^ (bitlen x.ceil.toNat + 1))) (bitlen x.ceil.toNat + 1)
        (p + 2 * (bitlen x.ceil.toNat + 1) + 2 * x.ceil.toNat)).1 : ℝ) := by
    exact_mod_cast e1
  refine ⟨⟨?_, ?_⟩, ?_⟩
  · show ((qd _ _ : ℚ) : ℝ) ≤ _
    rw [qd_cast _ _ hone.le, div_le_iff₀ hOR]
    linarith
  · show _ ≤ ((qd _ _ : ℚ) : ℝ)
    rw [qd_cast _ _ hone.le, le_div_iff₀ hOR]
    linarith
  · show (0 : ℝ) < ((qd _ _ : ℚ) : ℝ)
    rw [qd_cast _ _ hone.le]
    exact div_pos (lt_of_lt_of_le hOR e1R) hOR

/-- The kernel's `expAt x p` holds exp x. -/
theorem expAt_spec : ExpAtSpecOf expAt := by
  intro x p
  unfold expAt
  by_cases h : x < 0
  · rw [if_pos h]
    obtain ⟨⟨h1, h2⟩, h3⟩ := expPos_holds (-x) (by linarith) p
    show ((1 / (expPos (-x) p).hi : ℚ) : ℝ) ≤ Real.exp (x : ℝ) ∧
      Real.exp (x : ℝ) ≤ ((1 / (expPos (-x) p).lo : ℚ) : ℝ)
    rw [Rat.cast_neg, Real.exp_neg] at h1 h2
    have hpos := Real.exp_pos (x : ℝ)
    have hhi : (0 : ℝ) < ((expPos (-x) p).hi : ℝ) := lt_of_lt_of_le (inv_pos.2 hpos) h2
    push_cast
    constructor
    · rw [div_le_iff₀ hhi]
      have := mul_le_mul_of_nonneg_left h2 hpos.le
      rwa [mul_inv_cancel₀ hpos.ne'] at this
    · rw [le_div_iff₀ h3]
      have := mul_le_mul_of_nonneg_left h1 hpos.le
      rwa [mul_inv_cancel₀ hpos.ne'] at this
  · rw [if_neg h]
    exact (expPos_holds x (not_lt.mp h) p).1

end Petra.Loops
