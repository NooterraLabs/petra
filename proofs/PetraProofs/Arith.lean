/-
The exact interval operations enclose the real operations: if `x` lies in `a` and `y` lies
in `b`, the result of the real operation lies in the kernel's result. Each theorem is about
the kernel's own function in `Petra/Num.lean`, with the cases where it fails.
-/
import PetraProofs.Basic

namespace Petra

/-! ## Real facts the proofs use -/

/-- A product lies between its values at the ends of one factor. -/
theorem mul_between {a b x y : ℝ} (h1 : a ≤ x) (h2 : x ≤ b) :
    min (a * y) (b * y) ≤ x * y ∧ x * y ≤ max (a * y) (b * y) := by
  rcases le_total 0 y with hy | hy
  · exact ⟨(min_le_left _ _).trans (mul_le_mul_of_nonneg_right h1 hy),
      (mul_le_mul_of_nonneg_right h2 hy).trans (le_max_right _ _)⟩
  · exact ⟨(min_le_right _ _).trans (mul_le_mul_of_nonpos_right h2 hy),
      (mul_le_mul_of_nonpos_right h1 hy).trans (le_max_left _ _)⟩

/-- A product lies between the least and the greatest of the four products of the ends. -/
theorem mul_hull {a b c d x y : ℝ} (h1 : a ≤ x) (h2 : x ≤ b) (h3 : c ≤ y) (h4 : y ≤ d) :
    min (min (a * c) (a * d)) (min (b * c) (b * d)) ≤ x * y ∧
      x * y ≤ max (max (a * c) (a * d)) (max (b * c) (b * d)) := by
  obtain ⟨l1, u1⟩ := mul_between (y := y) h1 h2
  obtain ⟨l2, u2⟩ := mul_between (y := a) h3 h4
  obtain ⟨l3, u3⟩ := mul_between (y := b) h3 h4
  rw [mul_comm c a, mul_comm d a, mul_comm y a] at l2 u2
  rw [mul_comm c b, mul_comm d b, mul_comm y b] at l3 u3
  exact ⟨(min_le_min l2 l3).trans l1, u1.trans (max_le_max u2 u3)⟩

theorem inv_between_pos {l h y : ℝ} (hl : 0 < l) (h1 : l ≤ y) (h2 : y ≤ h) :
    1 / h ≤ 1 / y ∧ 1 / y ≤ 1 / l :=
  ⟨one_div_le_one_div_of_le (lt_of_lt_of_le hl h1) h2, one_div_le_one_div_of_le hl h1⟩

theorem inv_between_neg {l h y : ℝ} (hh : h < 0) (h1 : l ≤ y) (h2 : y ≤ h) :
    1 / h ≤ 1 / y ∧ 1 / y ≤ 1 / l := by
  have key := inv_between_pos (l := -h) (h := -l) (y := -y) (by linarith) (by linarith)
    (by linarith)
  simp only [div_neg] at key
  exact ⟨by linarith [key.2], by linarith [key.1]⟩

/-! ## Point, sum, negation, difference, product -/

theorem Iv.pt_sound (q : ℚ) : (Iv.pt q).Holds (q : ℝ) := ⟨le_refl _, le_refl _⟩

theorem Iv.add_sound {a b : Iv} {x y : ℝ} (hx : a.Holds x) (hy : b.Holds y) :
    (a.add b).Holds (x + y) := by
  obtain ⟨h1, h2⟩ := hx
  obtain ⟨h3, h4⟩ := hy
  show ((a.lo + b.lo : ℚ) : ℝ) ≤ x + y ∧ x + y ≤ ((a.hi + b.hi : ℚ) : ℝ)
  push_cast
  exact ⟨by linarith, by linarith⟩

theorem Iv.neg_sound {a : Iv} {x : ℝ} (hx : a.Holds x) : a.neg.Holds (-x) := by
  obtain ⟨h1, h2⟩ := hx
  show ((-a.hi : ℚ) : ℝ) ≤ -x ∧ -x ≤ ((-a.lo : ℚ) : ℝ)
  push_cast
  exact ⟨by linarith, by linarith⟩

theorem Iv.sub_sound {a b : Iv} {x y : ℝ} (hx : a.Holds x) (hy : b.Holds y) :
    (a.sub b).Holds (x - y) := by
  obtain ⟨h1, h2⟩ := hx
  obtain ⟨h3, h4⟩ := hy
  show ((a.lo - b.hi : ℚ) : ℝ) ≤ x - y ∧ x - y ≤ ((a.hi - b.lo : ℚ) : ℝ)
  push_cast
  exact ⟨by linarith, by linarith⟩

theorem Iv.mul_sound {a b : Iv} {x y : ℝ} (hx : a.Holds x) (hy : b.Holds y) :
    (a.mul b).Holds (x * y) := by
  obtain ⟨h1, h2⟩ := hx
  obtain ⟨h3, h4⟩ := hy
  show ((rmin (rmin (a.lo * b.lo) (a.lo * b.hi)) (rmin (a.hi * b.lo) (a.hi * b.hi)) : ℚ) : ℝ)
      ≤ x * y ∧
    x * y ≤
      ((rmax (rmax (a.lo * b.lo) (a.lo * b.hi)) (rmax (a.hi * b.lo) (a.hi * b.hi)) : ℚ) : ℝ)
  simp only [rmin_eq, rmax_eq, Rat.cast_min, Rat.cast_max, Rat.cast_mul]
  exact mul_hull h1 h2 h3 h4

/-! ## Absolute value, least, greatest -/

theorem Iv.abs_sound {a : Iv} {x : ℝ} (hx : a.Holds x) : a.abs.Holds |x| := by
  obtain ⟨h1, h2⟩ := hx
  unfold Iv.abs
  split_ifs with h0 h3
  · have h0' : (0 : ℝ) ≤ (a.lo : ℝ) := by exact_mod_cast h0
    rw [abs_of_nonneg (h0'.trans h1)]
    exact ⟨h1, h2⟩
  · have h3' : (a.hi : ℝ) ≤ 0 := by exact_mod_cast h3
    rw [abs_of_nonpos (h2.trans h3')]
    exact Iv.neg_sound ⟨h1, h2⟩
  · show ((0 : ℚ) : ℝ) ≤ |x| ∧ |x| ≤ ((rmax (-a.lo) a.hi : ℚ) : ℝ)
    rw [rmax_eq]
    push_cast
    exact ⟨abs_nonneg x,
      abs_le'.2 ⟨h2.trans (le_max_right _ _), (neg_le_neg h1).trans (le_max_left _ _)⟩⟩

theorem Iv.min_sound {a b : Iv} {x y : ℝ} (hx : a.Holds x) (hy : b.Holds y) :
    (a.min b).Holds (Min.min x y) := by
  obtain ⟨h1, h2⟩ := hx
  obtain ⟨h3, h4⟩ := hy
  show ((rmin a.lo b.lo : ℚ) : ℝ) ≤ Min.min x y ∧ Min.min x y ≤ ((rmin a.hi b.hi : ℚ) : ℝ)
  rw [rmin_eq, rmin_eq, Rat.cast_min, Rat.cast_min]
  exact ⟨min_le_min h1 h3, min_le_min h2 h4⟩

theorem Iv.max_sound {a b : Iv} {x y : ℝ} (hx : a.Holds x) (hy : b.Holds y) :
    (a.max b).Holds (Max.max x y) := by
  obtain ⟨h1, h2⟩ := hx
  obtain ⟨h3, h4⟩ := hy
  show ((rmax a.lo b.lo : ℚ) : ℝ) ≤ Max.max x y ∧ Max.max x y ≤ ((rmax a.hi b.hi : ℚ) : ℝ)
  rw [rmax_eq, rmax_eq, Rat.cast_max, Rat.cast_max]
  exact ⟨max_le_max h1 h3, max_le_max h2 h4⟩

/-! ## Quotient

`Iv.div` fails when the divisor's interval holds zero. When it succeeds, the divisor is not
zero and the quotient lies in the result. -/

theorem Iv.div_sound {a b r : Iv} {x y : ℝ} (hx : a.Holds x) (hy : b.Holds y)
    (h : a.div b = .ok r) : y ≠ 0 ∧ r.Holds (x / y) := by
  obtain ⟨h3, h4⟩ := hy
  unfold Iv.div at h
  split_ifs at h with hz
  have hr : a.mul ⟨1 / b.hi, 1 / b.lo⟩ = r := by cases h; rfl
  subst hr
  have hz' : (0 : ℝ) < (b.lo : ℝ) ∨ (b.hi : ℝ) < 0 := by
    by_contra hcon
    simp only [not_or, not_lt] at hcon
    exact hz ⟨by exact_mod_cast hcon.1, by exact_mod_cast hcon.2⟩
  have hinv : (⟨1 / b.hi, 1 / b.lo⟩ : Iv).Holds (1 / y) := by
    show ((1 / b.hi : ℚ) : ℝ) ≤ 1 / y ∧ 1 / y ≤ ((1 / b.lo : ℚ) : ℝ)
    push_cast
    rcases hz' with hpos | hneg
    · exact inv_between_pos hpos h3 h4
    · exact inv_between_neg hneg h3 h4
  have hy0 : y ≠ 0 := by
    rcases hz' with hpos | hneg
    · exact ne_of_gt (lt_of_lt_of_le hpos h3)
    · exact ne_of_lt (lt_of_le_of_lt h4 hneg)
  refine ⟨hy0, ?_⟩
  have key := Iv.mul_sound hx hinv
  rwa [mul_one_div] at key

/-! ## Integer power

`powInt` fails for a negative exponent. For `n ≥ 0` the power `x ^ n` lies in the result. -/

theorem rpow_cast (x : ℚ) (k : ℕ) : ((rpow x k : ℚ) : ℝ) = (x : ℝ) ^ k := by
  induction k with
  | zero => simp [rpow]
  | succ n ih => rw [rpow, Rat.cast_mul, ih, pow_succ, mul_comm]

theorem powInt_eq (a : Iv) (n : ℤ) : powInt a n =
    if n < 0 then .error "negative exponent" else
    if (n.toNat == 0 || n.toNat % 2 == 1 || decide (0 ≤ a.lo)) = true then
      .ok ⟨rpow a.lo n.toNat, rpow a.hi n.toNat⟩
    else if a.hi ≤ 0 then .ok ⟨rpow a.hi n.toNat, rpow a.lo n.toNat⟩
    else .ok ⟨0, rmax (rpow a.lo n.toNat) (rpow a.hi n.toNat)⟩ := rfl

theorem powInt_sound {a r : Iv} {x : ℝ} {n : ℤ} (hx : a.Holds x) (h : powInt a n = .ok r) :
    0 ≤ n ∧ r.Holds (x ^ n.toNat) := by
  obtain ⟨h1, h2⟩ := hx
  rw [powInt_eq] at h
  split_ifs at h with hn hk hhi
  · -- the exponent is 0 or odd, or the interval is at or above 0: the power goes up with x
    refine ⟨not_lt.mp hn, ?_⟩
    cases h
    show ((rpow a.lo n.toNat : ℚ) : ℝ) ≤ x ^ n.toNat ∧ x ^ n.toNat ≤ ((rpow a.hi n.toNat : ℚ) : ℝ)
    rw [rpow_cast, rpow_cast]
    simp only [Bool.or_eq_true, beq_iff_eq, decide_eq_true_eq] at hk
    rcases hk with (hk0 | hodd) | hlo
    · rw [hk0]
      simp
    · have ho : Odd n.toNat := Nat.odd_iff.mpr hodd
      exact ⟨ho.strictMono_pow.monotone h1, ho.strictMono_pow.monotone h2⟩
    · have hlo' : (0 : ℝ) ≤ (a.lo : ℝ) := by exact_mod_cast hlo
      exact ⟨pow_le_pow_left₀ hlo' h1 _, pow_le_pow_left₀ (hlo'.trans h1) h2 _⟩
  · -- an even exponent over an interval at or below 0: the power goes down with x
    refine ⟨not_lt.mp hn, ?_⟩
    cases h
    simp only [Bool.or_eq_true, beq_iff_eq, decide_eq_true_eq, not_or] at hk
    have he : Even n.toNat := Nat.even_iff.mpr (by omega)
    have hhi' : (a.hi : ℝ) ≤ 0 := by exact_mod_cast hhi
    show ((rpow a.hi n.toNat : ℚ) : ℝ) ≤ x ^ n.toNat ∧ x ^ n.toNat ≤ ((rpow a.lo n.toNat : ℚ) : ℝ)
    rw [rpow_cast, rpow_cast, ← he.neg_pow x, ← he.neg_pow (a.hi : ℝ), ← he.neg_pow (a.lo : ℝ)]
    exact ⟨pow_le_pow_left₀ (by linarith) (by linarith) _,
      pow_le_pow_left₀ (by linarith) (by linarith) _⟩
  · -- an even exponent over an interval that straddles 0
    refine ⟨not_lt.mp hn, ?_⟩
    cases h
    simp only [Bool.or_eq_true, beq_iff_eq, decide_eq_true_eq, not_or] at hk
    have he : Even n.toNat := Nat.even_iff.mpr (by omega)
    show ((0 : ℚ) : ℝ) ≤ x ^ n.toNat ∧
      x ^ n.toNat ≤ ((rmax (rpow a.lo n.toNat) (rpow a.hi n.toNat) : ℚ) : ℝ)
    rw [rmax_eq, Rat.cast_max, rpow_cast, rpow_cast, Rat.cast_zero]
    refine ⟨he.pow_nonneg x, ?_⟩
    rcases le_total 0 x with hx0 | hx0
    · exact (pow_le_pow_left₀ hx0 h2 _).trans (le_max_right _ _)
    · calc x ^ n.toNat = (-x) ^ n.toNat := (he.neg_pow x).symm
        _ ≤ (-(a.lo : ℝ)) ^ n.toNat := pow_le_pow_left₀ (by linarith) (by linarith) _
        _ = (a.lo : ℝ) ^ n.toNat := he.neg_pow _
        _ ≤ _ := le_max_left _ _

/-! ## The bit budget

`fits` returns its interval unchanged or fails, so it never widens or moves an enclosure. -/

theorem fits_ok {x y : Iv} (h : fits x = .ok y) : y = x := by
  unfold fits at h
  split_ifs at h
  cases h
  rfl

end Petra
