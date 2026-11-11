/-
The rounded functions: `iSqrt`, `piIv`, `iLn` and `iExp` return an interval that holds the
true value.

Each theorem is about the kernel's own function. Each takes as a hypothesis the statement
of Trust.lean about the loop that function runs, since the logic cannot see into a `while`
or a `partial def`. What is proved here is everything around those loops: the rounding to
the grid, the scaling of the square root, Machin's formula, the reduction of ln to atanh,
and the caches.
-/
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Arctan
import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Data.Rat.Floor
import PetraProofs.Trust
import PetraProofs.Arith

namespace Petra

/-! ## Rationals the kernel builds -/

private theorem qi_eq (n : ℤ) : qi n = (n : ℚ) := by
  unfold qi
  rw [Rat.mkRat_eq_div]
  simp

private theorem qd_eq (n d : ℤ) (hd : 0 ≤ d) : qd n d = (n : ℚ) / (d : ℚ) := by
  unfold qd
  rw [Rat.mkRat_eq_div]
  have h : ((d.toNat : ℕ) : ℤ) = d := Int.toNat_of_nonneg hd
  have h' : ((d.toNat : ℕ) : ℚ) = (d : ℚ) := by exact_mod_cast congrArg (fun z : ℤ => (z : ℚ)) h
  rw [h']

private theorem qi_ofNat (n : ℕ) : qi (Int.ofNat n) = (n : ℚ) := by
  rw [qi_eq]
  exact Int.cast_natCast n

private theorem GRID_pos : 0 < GRID := by
  unfold GRID
  positivity

private theorem GRIDq_pos : (0 : ℚ) < (GRID : ℚ) := by exact_mod_cast GRID_pos

/-! ## The grid -/

private theorem grid_lo_le (a : ℚ) : qd (a * qi GRID).floor GRID ≤ a := by
  rw [qd_eq _ _ GRID_pos.le, qi_eq, div_le_iff₀ GRIDq_pos]
  exact Rat.floor_le _

private theorem grid_le_hi (a : ℚ) : a ≤ qd (a * qi GRID).ceil GRID := by
  rw [qd_eq _ _ GRID_pos.le, qi_eq, le_div_iff₀ GRIDq_pos]
  exact Rat.le_ceil

/-- What `grid` returns is the pair of grid points around one of the enclosures it asked
for. -/
private theorem grid_ok {enc : Nat → Iv} {lo hi : ℚ} (h : grid enc = .ok (lo, hi)) :
    ∃ p, lo = qd ((enc p).lo * qi GRID).floor GRID ∧ hi = qd ((enc p).hi * qi GRID).ceil GRID := by
  unfold grid at h
  simp only [List.forIn_cons, List.forIn_nil] at h
  -- Four tests, so sixteen cases. In each, the loop returns the pair of the first test that
  -- passed. When none passed it returns the error, and `split_ifs` closes that case.
  split_ifs at h <;>
    first
    | exact ⟨PREC + 32, (Prod.mk.inj (Except.ok.inj h)).1.symm, (Prod.mk.inj (Except.ok.inj h)).2.symm⟩
    | exact ⟨PREC + 128, (Prod.mk.inj (Except.ok.inj h)).1.symm, (Prod.mk.inj (Except.ok.inj h)).2.symm⟩
    | exact ⟨PREC + 512, (Prod.mk.inj (Except.ok.inj h)).1.symm, (Prod.mk.inj (Except.ok.inj h)).2.symm⟩
    | exact ⟨PREC + 2048, (Prod.mk.inj (Except.ok.inj h)).1.symm, (Prod.mk.inj (Except.ok.inj h)).2.symm⟩

/-- If every enclosure `enc p` holds `x`, the pair of grid points that `grid` returns has
`x` between them. -/
theorem grid_sound {enc : Nat → Iv} {x : ℝ} {lo hi : ℚ} (henc : ∀ p, (enc p).Holds x)
    (h : grid enc = .ok (lo, hi)) : (lo : ℝ) ≤ x ∧ x ≤ (hi : ℝ) := by
  obtain ⟨p, rfl, rfl⟩ := grid_ok h
  obtain ⟨h1, h2⟩ := henc p
  exact ⟨le_trans (Rat.cast_le.2 (grid_lo_le _)) h1, le_trans h2 (Rat.cast_le.2 (grid_le_hi _))⟩

/-! ## The square root

With `G = 2^96`, `iSqrt` returns `isqrt ⌊lo G²⌋ / G` and `isqrt ⌊hi G²⌋ / G`, the second
plus `1 / G` unless its square is exactly `hi G²`. -/

private theorem iSqrt_eq (a : Iv) : iSqrt a =
    if a.lo < 0 then .error "sqrt over an interval with negative values" else
    .ok ⟨qd (Int.ofNat (isqrt (a.lo * qi (GRID * GRID)).floor.toNat)) GRID,
      qd (Int.ofNat (if (qi (Int.ofNat (isqrt (a.hi * qi (GRID * GRID)).floor.toNat *
            isqrt (a.hi * qi (GRID * GRID)).floor.toNat)) == a.hi * qi (GRID * GRID)) = true
          then isqrt (a.hi * qi (GRID * GRID)).floor.toNat
          else isqrt (a.hi * qi (GRID * GRID)).floor.toNat + 1)) GRID⟩ := rfl

private theorem qd_nat_cast (n : ℕ) :
    ((qd (Int.ofNat n) GRID : ℚ) : ℝ) = (n : ℝ) / (GRID : ℝ) := by
  rw [qd_eq _ _ GRID_pos.le]
  have e : ((Int.ofNat n : ℤ) : ℚ) = (n : ℚ) := Int.cast_natCast n
  rw [e]
  push_cast
  rfl

private theorem GRIDr_pos : (0 : ℝ) < (GRID : ℝ) := by exact_mod_cast GRID_pos

/-- A natural number whose square is at most `⌊q G²⌋` is, over `G`, at most the square root
of any real at or above `q`. -/
private theorem sqrt_lower {q : ℚ} {x : ℝ} {n : ℕ} (hq : 0 ≤ q) (hqx : (q : ℝ) ≤ x)
    (hn : n * n ≤ (q * qi (GRID * GRID)).floor.toNat) :
    ((qd (Int.ofNat n) GRID : ℚ) : ℝ) ≤ Real.sqrt x := by
  have hfl : (0 : ℤ) ≤ (q * qi (GRID * GRID)).floor := by
    rw [Rat.le_floor_iff, qi_eq]
    have := GRIDq_pos
    push_cast
    positivity
  have h1 : ((n * n : ℕ) : ℤ) ≤ (q * qi (GRID * GRID)).floor := by
    calc ((n * n : ℕ) : ℤ) ≤ (((q * qi (GRID * GRID)).floor.toNat : ℕ) : ℤ) := by exact_mod_cast hn
      _ = (q * qi (GRID * GRID)).floor := Int.toNat_of_nonneg hfl
  have h2 : (((n * n : ℕ) : ℤ) : ℚ) ≤ q * qi (GRID * GRID) :=
    le_trans (by exact_mod_cast h1) (Rat.floor_le _)
  rw [qi_eq] at h2
  have h3 : (n : ℝ) * (n : ℝ) ≤ (q : ℝ) * ((GRID : ℝ) * (GRID : ℝ)) := by exact_mod_cast h2
  have hG := GRIDr_pos
  have key : ((n : ℝ) / (GRID : ℝ)) ^ 2 ≤ x := by
    rw [div_pow, div_le_iff₀ (by positivity)]
    have h4 : (q : ℝ) * ((GRID : ℝ) * (GRID : ℝ)) ≤ x * ((GRID : ℝ) * (GRID : ℝ)) :=
      mul_le_mul_of_nonneg_right hqx (by positivity)
    nlinarith
  rw [qd_nat_cast]
  calc (n : ℝ) / (GRID : ℝ) = Real.sqrt (((n : ℝ) / (GRID : ℝ)) ^ 2) :=
        (Real.sqrt_sq (by positivity)).symm
    _ ≤ Real.sqrt x := Real.sqrt_le_sqrt key

/-- A natural number whose square is at least `q G²` is, over `G`, at least the square root
of any real at or below `q`. -/
private theorem sqrt_upper {q : ℚ} {x : ℝ} {n : ℕ} (hxq : x ≤ (q : ℝ))
    (hn : q * qi (GRID * GRID) ≤ ((n * n : ℕ) : ℚ)) :
    Real.sqrt x ≤ ((qd (Int.ofNat n) GRID : ℚ) : ℝ) := by
  rw [qi_eq] at hn
  have h3 : (q : ℝ) * ((GRID : ℝ) * (GRID : ℝ)) ≤ (n : ℝ) * (n : ℝ) := by exact_mod_cast hn
  have hG := GRIDr_pos
  have key : x ≤ ((n : ℝ) / (GRID : ℝ)) ^ 2 := by
    rw [div_pow, le_div_iff₀ (by positivity)]
    have h4 : x * ((GRID : ℝ) * (GRID : ℝ)) ≤ (q : ℝ) * ((GRID : ℝ) * (GRID : ℝ)) :=
      mul_le_mul_of_nonneg_right hxq (by positivity)
    nlinarith
  rw [qd_nat_cast]
  calc Real.sqrt x ≤ Real.sqrt (((n : ℝ) / (GRID : ℝ)) ^ 2) := Real.sqrt_le_sqrt key
    _ = (n : ℝ) / (GRID : ℝ) := Real.sqrt_sq (by positivity)

/-- If `isqrt` is the integer square root, `iSqrt` succeeds only on an interval with no
negative number, and its result holds the square root of every real the interval holds. -/
theorem iSqrt_sound (hs : IsqrtSpec) {a r : Iv} {x : ℝ} (ha : a.Holds x)
    (h : iSqrt a = .ok r) : 0 ≤ x ∧ r.Holds (Real.sqrt x) := by
  obtain ⟨hlo, hhi⟩ := ha
  rw [iSqrt_eq] at h
  by_cases hneg : a.lo < 0
  · rw [if_pos hneg] at h
    cases h
  rw [if_neg hneg] at h
  have h0 : (0 : ℚ) ≤ a.lo := not_lt.mp hneg
  have hx0 : (0 : ℝ) ≤ x := le_trans (by exact_mod_cast h0) hlo
  refine ⟨hx0, ?_⟩
  by_cases hex : (qi (Int.ofNat (isqrt (a.hi * qi (GRID * GRID)).floor.toNat *
      isqrt (a.hi * qi (GRID * GRID)).floor.toNat)) == a.hi * qi (GRID * GRID)) = true
  · rw [if_pos hex] at h
    cases h
    refine ⟨sqrt_lower h0 hlo (hs _).1, sqrt_upper hhi ?_⟩
    have heq := beq_iff_eq.mp hex
    exact le_of_eq (heq.symm.trans (qi_ofNat _))
  · rw [if_neg hex] at h
    cases h
    refine ⟨sqrt_lower h0 hlo (hs _).1, sqrt_upper hhi ?_⟩
    have hlt := (hs (a.hi * qi (GRID * GRID)).floor.toNat).2
    have h1 : (a.hi * qi (GRID * GRID)).floor <
        (((isqrt (a.hi * qi (GRID * GRID)).floor.toNat + 1) *
          (isqrt (a.hi * qi (GRID * GRID)).floor.toNat + 1) : ℕ) : ℤ) :=
      lt_of_le_of_lt (Int.self_le_toNat _) (by exact_mod_cast hlt)
    have h2 := Rat.floor_lt_iff.mp h1
    exact le_of_lt (by exact_mod_cast h2)

/-! ## Pi

`piAt` is Machin's formula, 16 arctan (1/5) - 4 arctan (1/239), on two runs of `oddSeries`. -/

private theorem piAt_sound (hs : OddSeriesSpec) (p : ℕ) : (piAt p).Holds Real.pi := by
  have h5 : |(mkRat 1 5 : ℚ)| ≤ 1 / 3 := by
    rw [Rat.mkRat_eq_div, abs_le]
    constructor <;> norm_num
  have h239 : |(mkRat 1 239 : ℚ)| ≤ 1 / 3 := by
    rw [Rat.mkRat_eq_div, abs_le]
    constructor <;> norm_num
  have a5 := (hs _ p h5).2
  have a239 := (hs _ p h239).2
  have e5 : ((mkRat 1 5 : ℚ) : ℝ) = 5⁻¹ := by
    rw [Rat.mkRat_eq_div]
    norm_num
  have e239 : ((mkRat 1 239 : ℚ) : ℝ) = 239⁻¹ := by
    rw [Rat.mkRat_eq_div]
    norm_num
  rw [e5] at a5
  rw [e239] at a239
  have hm := Iv.sub_sound (Iv.mul_sound (Iv.pt_sound 16) a5) (Iv.mul_sound (Iv.pt_sound 4) a239)
  have hpi : Real.pi = ((16 : ℚ) : ℝ) * Real.arctan 5⁻¹ - ((4 : ℚ) : ℝ) * Real.arctan 239⁻¹ := by
    have := Real.four_mul_arctan_inv_5_sub_arctan_inv_239
    push_cast
    linarith
  rw [hpi]
  exact hm

/-- If `oddSeries` holds the sums it is written to hold, the interval `piIv` returns holds
pi. -/
theorem piIv_sound (hs : OddSeriesSpec) {r : Iv} (h : piIv = .ok r) : r.Holds Real.pi := by
  unfold piIv at h
  cases hg : grid piAt with
  | error e =>
    rw [hg] at h
    cases h
  | ok v =>
    rw [hg] at h
    obtain ⟨lo, hi⟩ := v
    have h' : (Except.ok ⟨lo, hi⟩ : Except String Iv) = .ok r := h
    cases h'
    exact grid_sound (piAt_sound hs) hg

/-! ## ln

`lnAt x` writes `x = m 2^e` with `m` in (1/2, 2), and returns `2 atanh z + e ln 2` with
`z = (m - 1) / (m + 1)`. -/

private theorem bitlen_of_ne_zero {n : ℕ} (h : n ≠ 0) : bitlen n = Nat.log2 n + 1 := by
  unfold bitlen
  simp [h]

/-- The exponent `e` that `lnAt` takes. -/
private def lnE (x : ℚ) : ℤ := Int.ofNat (bitlen x.num.natAbs) - Int.ofNat (bitlen x.den)

/-- The mantissa `m` that `lnAt` takes. -/
private def lnM (x : ℚ) : ℚ :=
  if 0 ≤ lnE x then x / qi ((2 : Int) ^ (lnE x).toNat) else x * qi ((2 : Int) ^ (-(lnE x)).toNat)

private theorem lnAt_eq (x : ℚ) (p : ℕ) : lnAt x p =
    ((Iv.pt 2).mul (oddSeries ((lnM x - 1) / (lnM x + 1)) 1 p)).add
      ((Iv.pt (qi (lnE x))).mul (if p == 128 then ln2_128 else ln2At p)) := rfl

private theorem lnM_eq_zpow (x : ℚ) : lnM x = x / (2 : ℚ) ^ (lnE x) := by
  unfold lnM
  split_ifs with h
  · rw [qi_eq]
    push_cast
    congr 1
    conv_rhs => rw [← Int.toNat_of_nonneg h]
    exact (zpow_natCast 2 _).symm
  · have h' : 0 ≤ -(lnE x) := by omega
    rw [qi_eq, div_eq_mul_inv, ← zpow_neg]
    push_cast
    congr 1
    conv_rhs => rw [← Int.toNat_of_nonneg h']
    exact (zpow_natCast 2 _).symm

private theorem ratio_bounds {N D PA PB : ℚ} (pa : 0 < PA) (pb : 0 < PB) (a1 : PA ≤ N)
    (a2 : N < 2 * PA) (b1 : PB ≤ D) (b2 : D < 2 * PB) :
    1 / 2 < N / D / (PA / PB) ∧ N / D / (PA / PB) < 2 := by
  have dpos : 0 < D := lt_of_lt_of_le pb b1
  have e : N / D / (PA / PB) = N * PB / (D * PA) := by
    field_simp
  rw [e]
  constructor
  · rw [lt_div_iff₀ (by positivity)]
    nlinarith [mul_lt_mul_of_pos_right b2 pa, mul_le_mul_of_nonneg_left a1 pb.le]
  · rw [div_lt_iff₀ (by positivity)]
    nlinarith [mul_lt_mul_of_pos_right a2 pb, mul_le_mul_of_nonneg_right b1 pa.le]

private theorem lnM_bounds {x : ℚ} (hx : 0 < x) : 1 / 2 < lnM x ∧ lnM x < 2 := by
  have hnum : 0 < x.num := Rat.num_pos.mpr hx
  have hn0 : x.num.natAbs ≠ 0 := by omega
  have hd0 : x.den ≠ 0 := x.den_nz
  have hA1 := Nat.log2_self_le hn0
  have hA2 := @Nat.lt_log2_self x.num.natAbs
  have hB1 := Nat.log2_self_le hd0
  have hB2 := @Nat.lt_log2_self x.den
  have hE : lnE x = (x.num.natAbs.log2 : ℤ) - (x.den.log2 : ℤ) := by
    unfold lnE
    rw [bitlen_of_ne_zero hn0, bitlen_of_ne_zero hd0]
    show ((x.num.natAbs.log2 + 1 : ℕ) : ℤ) - ((x.den.log2 + 1 : ℕ) : ℤ) = _
    omega
  have hxeq : (x.num.natAbs : ℚ) / (x.den : ℚ) = x := by
    have h1 : ((x.num.natAbs : ℕ) : ℤ) = x.num := Int.natAbs_of_nonneg hnum.le
    have h2 : ((x.num.natAbs : ℕ) : ℚ) = (x.num : ℚ) := by
      rw [← h1]
      exact (Int.cast_natCast _).symm
    rw [h2]
    exact Rat.num_div_den x
  have a1 : (2 : ℚ) ^ x.num.natAbs.log2 ≤ (x.num.natAbs : ℚ) := by exact_mod_cast hA1
  have a2 : (x.num.natAbs : ℚ) < 2 * (2 : ℚ) ^ x.num.natAbs.log2 := by
    have : (x.num.natAbs : ℚ) < (2 : ℚ) ^ (x.num.natAbs.log2 + 1) := by exact_mod_cast hA2
    rwa [pow_succ, mul_comm] at this
  have b1 : (2 : ℚ) ^ x.den.log2 ≤ (x.den : ℚ) := by exact_mod_cast hB1
  have b2 : (x.den : ℚ) < 2 * (2 : ℚ) ^ x.den.log2 := by
    have : (x.den : ℚ) < (2 : ℚ) ^ (x.den.log2 + 1) := by exact_mod_cast hB2
    rwa [pow_succ, mul_comm] at this
  have key := ratio_bounds (by positivity) (by positivity) a1 a2 b1 b2
  rw [hxeq] at key
  rw [lnM_eq_zpow, hE, zpow_sub₀ (by norm_num : (2 : ℚ) ≠ 0), zpow_natCast, zpow_natCast]
  exact key

private theorem ln2At_sound (hs : OddSeriesSpec) (p : ℕ) : (ln2At p).Holds (Real.log 2) := by
  have h3 : |(mkRat 1 3 : ℚ)| ≤ 1 / 3 := by
    rw [Rat.mkRat_eq_div, abs_le]
    constructor <;> norm_num
  have a := (hs _ p h3).1
  have e : Real.log ((1 + ((mkRat 1 3 : ℚ) : ℝ)) / (1 - ((mkRat 1 3 : ℚ) : ℝ))) = Real.log 2 := by
    congr 1
    rw [Rat.mkRat_eq_div]
    norm_num
  rw [e] at a
  have hm := Iv.mul_sound (Iv.pt_sound 2) a
  have e2 : ((2 : ℚ) : ℝ) * (Real.log 2 / 2) = Real.log 2 := by
    push_cast
    ring
  rw [e2] at hm
  exact hm

private theorem lnAt_sound (hs : OddSeriesSpec) {x : ℚ} (hx : 0 < x) (p : ℕ) :
    (lnAt x p).Holds (Real.log (x : ℝ)) := by
  obtain ⟨hm1, hm2⟩ := lnM_bounds hx
  have hmpos : (0 : ℚ) < lnM x := by linarith
  have hz : |(lnM x - 1) / (lnM x + 1)| ≤ 1 / 3 := by
    have hpos : (0 : ℚ) < lnM x + 1 := by linarith
    rw [abs_le]
    constructor
    · rw [le_div_iff₀ hpos]
      linarith
    · rw [div_le_iff₀ hpos]
      linarith
  have hser := (hs _ p hz).1
  have hmr : (0 : ℝ) < (lnM x : ℝ) := by exact_mod_cast hmpos
  have hlogm : Real.log ((1 + (((lnM x - 1) / (lnM x + 1) : ℚ) : ℝ)) /
      (1 - (((lnM x - 1) / (lnM x + 1) : ℚ) : ℝ))) = Real.log (lnM x : ℝ) := by
    congr 1
    push_cast
    have hp : ((lnM x : ℝ) + 1) ≠ 0 := by linarith
    have e1 : 1 + ((lnM x : ℝ) - 1) / ((lnM x : ℝ) + 1) = 2 * (lnM x : ℝ) / ((lnM x : ℝ) + 1) := by
      field_simp
      ring
    have e2 : 1 - ((lnM x : ℝ) - 1) / ((lnM x : ℝ) + 1) = 2 / ((lnM x : ℝ) + 1) := by
      field_simp
      ring
    rw [e1, e2]
    field_simp
  rw [hlogm] at hser
  have hl2 : (if p == 128 then ln2_128 else ln2At p).Holds (Real.log 2) := by
    split_ifs
    · exact ln2At_sound hs 128
    · exact ln2At_sound hs p
  have hsum := Iv.add_sound (Iv.mul_sound (Iv.pt_sound 2) hser) (Iv.mul_sound (Iv.pt_sound (qi (lnE x))) hl2)
  have hxm : (x : ℝ) = (lnM x : ℝ) * (2 : ℝ) ^ (lnE x) := by
    have h2 : ((2 : ℚ) ^ (lnE x)) ≠ 0 := zpow_ne_zero _ (by norm_num)
    have : x = lnM x * (2 : ℚ) ^ (lnE x) := by
      rw [lnM_eq_zpow, div_mul_cancel₀ _ h2]
    calc (x : ℝ) = ((lnM x * (2 : ℚ) ^ (lnE x) : ℚ) : ℝ) := congrArg (fun q : ℚ => (q : ℝ)) this
      _ = (lnM x : ℝ) * (2 : ℝ) ^ (lnE x) := by
        rw [Rat.cast_mul, Rat.cast_zpow]
        norm_num
  have hlog : Real.log (x : ℝ) =
      ((2 : ℚ) : ℝ) * (Real.log (lnM x : ℝ) / 2) + ((qi (lnE x) : ℚ) : ℝ) * Real.log 2 := by
    rw [qi_eq]
    conv_lhs => rw [hxm]
    rw [Real.log_mul (ne_of_gt hmr) (zpow_ne_zero _ (by norm_num)), Real.log_zpow]
    push_cast
    ring
  rw [lnAt_eq, hlog]
  exact hsum

/-! ## The caches

`lnPoint` and `expPoint` keep what they computed, under the numerator and the denominator
of the argument. A cache is valid when every entry is right, and each call keeps it so. -/

/-- The empty caches, which the kernel starts from, are valid. -/
theorem Caches.valid_empty : ({} : Caches).Valid := by
  constructor
  · intro x v h _
    have h' : (∅ : Cache).get? (x.num, x.den) = some v := h
    rw [Std.HashMap.get?_eq_getElem?, Std.HashMap.getElem?_empty] at h'
    cases h'
  · intro x v h
    have h' : (∅ : Cache).get? (x.num, x.den) = some v := h
    rw [Std.HashMap.get?_eq_getElem?, Std.HashMap.getElem?_empty] at h'
    cases h'

private theorem get_ok {c s c' : Caches} (h : (get : M Caches) c = .ok (s, c')) :
    s = c ∧ c' = c := by
  have h' : (Except.ok (c, c) : Except String (Caches × Caches)) = .ok (s, c') := h
  cases h'
  exact ⟨rfl, rfl⟩

private theorem modify_ok {f : Caches → Caches} {c c' : Caches} {u : PUnit}
    (h : (modify f : M PUnit) c = .ok (u, c')) : c' = f c := by
  have h' : (Except.ok (PUnit.unit, f c) : Except String (PUnit × Caches)) = .ok (u, c') := h
  cases h'
  rfl

private theorem key_eq {q x : ℚ} (h : ((q.num, q.den) == (x.num, x.den)) = true) : q = x := by
  have h' := beq_iff_eq.mp h
  exact Rat.ext (congrArg Prod.fst h') (congrArg Prod.snd h')

/-- The three ways `lnPoint` returns: the argument is 1, the cache has it, or `grid` computes
it and the cache gains it. -/
private theorem lnPoint_cases {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    (h : lnPoint q c = .ok (v, c')) :
    (q = 1 ∧ v = (0, 0) ∧ c' = c) ∨
    (c.ln.get? (q.num, q.den) = some v ∧ c' = c) ∨
    (grid (lnAt q) = .ok v ∧ c' = { c with ln := c.ln.insert (q.num, q.den) v }) := by
  unfold lnPoint at h
  dsimp only at h
  by_cases h1 : (q == 1) = true
  · rw [if_pos h1] at h
    obtain ⟨hv, hc'⟩ := M.pure_ok h
    exact Or.inl ⟨beq_iff_eq.mp h1, hv, hc'⟩
  · rw [if_neg h1] at h
    obtain ⟨u, c1, h2, h3⟩ := M.bind_ok h
    rw [(M.pure_ok h2).2] at h3
    obtain ⟨s, c2, h4, h5⟩ := M.bind_ok h3
    obtain ⟨hs1, hs2⟩ := get_ok h4
    rw [hs1, hs2] at h5
    cases hget : c.ln.get? (q.num, q.den) with
    | some w =>
      rw [hget] at h5
      obtain ⟨hv, hc'⟩ := M.pure_ok h5
      exact Or.inr (Or.inl ⟨by rw [hv], hc'⟩)
    | none =>
      rw [hget] at h5
      obtain ⟨w, c3, h6, h7⟩ := M.bind_ok h5
      obtain ⟨hg, hc3⟩ := M.lift_ok h6
      rw [hc3] at h7
      obtain ⟨u', c4, h8, h9⟩ := M.bind_ok h7
      rw [modify_ok h8] at h9
      obtain ⟨hv, hc'⟩ := M.pure_ok h9
      subst hv
      exact Or.inr (Or.inr ⟨hg, hc'⟩)

private theorem lnPoint_sound (hs : OddSeriesSpec) {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    (hc : c.Valid) (hq : 0 < q) (h : lnPoint q c = .ok (v, c')) :
    c'.Valid ∧ (v.1 : ℝ) ≤ Real.log (q : ℝ) ∧ Real.log (q : ℝ) ≤ (v.2 : ℝ) := by
  rcases lnPoint_cases h with ⟨rfl, rfl, rfl⟩ | ⟨hget, rfl⟩ | ⟨hg, rfl⟩
  · refine ⟨hc, ?_, ?_⟩ <;> simp
  · exact ⟨hc, hc.1 q v hget hq⟩
  · have hb := grid_sound (lnAt_sound hs hq) hg
    refine ⟨⟨fun x w hget hx => ?_, hc.2⟩, hb⟩
    have hget' : (c.ln.insert (q.num, q.den) v).get? (x.num, x.den) = some w := hget
    rw [Std.HashMap.get?_insert] at hget'
    by_cases hk : ((q.num, q.den) == (x.num, x.den)) = true
    · rw [if_pos hk] at hget'
      cases hget'
      rw [← key_eq hk]
      exact hb
    · rw [if_neg hk] at hget'
      exact hc.1 x w hget' hx

/-- `lnPoint` keeps the caches valid, whatever its argument: an entry under a key that is
not positive is never read as a logarithm. -/
private theorem lnPoint_valid (hs : OddSeriesSpec) {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    (hc : c.Valid) (h : lnPoint q c = .ok (v, c')) : c'.Valid := by
  rcases lnPoint_cases h with ⟨-, -, rfl⟩ | ⟨-, rfl⟩ | ⟨hg, rfl⟩
  · exact hc
  · exact hc
  · refine ⟨fun x w hget hx => ?_, hc.2⟩
    have hget' : (c.ln.insert (q.num, q.den) v).get? (x.num, x.den) = some w := hget
    rw [Std.HashMap.get?_insert] at hget'
    by_cases hk : ((q.num, q.den) == (x.num, x.den)) = true
    · rw [if_pos hk] at hget'
      cases hget'
      have hqx := key_eq hk
      subst hqx
      exact grid_sound (lnAt_sound hs hx) hg
    · rw [if_neg hk] at hget'
      exact hc.1 x w hget' hx

/-- `iLn` keeps the caches valid, on any interval. -/
theorem iLn_valid (hs : OddSeriesSpec) {a r : Iv} {c c' : Caches} (hc : c.Valid)
    (h : iLn a c = .ok (r, c')) : c'.Valid := by
  unfold iLn at h
  dsimp only at h
  by_cases hneg : a.lo ≤ 0
  · rw [if_pos hneg] at h
    obtain ⟨u, c1, h1, -⟩ := M.bind_ok h
    exact (M.throw_not_ok h1).elim
  · rw [if_neg hneg] at h
    obtain ⟨u, c1, h1, h2⟩ := M.bind_ok h
    rw [(M.pure_ok h1).2] at h2
    obtain ⟨va, c2, h3, h4⟩ := M.bind_ok h2
    obtain ⟨vb, c3, h5, h6⟩ := M.bind_ok h4
    obtain ⟨-, hc'⟩ := M.pure_ok h6
    rw [hc']
    exact lnPoint_valid hs (lnPoint_valid hs hc h3) h5

/-- If `oddSeries` holds the sums it is written to hold, `iLn` succeeds only on an interval
of positive numbers, its result holds the logarithm of every real the interval holds, and
it keeps the caches valid. -/
theorem iLn_sound (hs : OddSeriesSpec) {a r : Iv} {x : ℝ} {c c' : Caches} (hc : c.Valid)
    (ha : a.Holds x) (h : iLn a c = .ok (r, c')) : c'.Valid ∧ 0 < x ∧ r.Holds (Real.log x) := by
  obtain ⟨hlo, hhi⟩ := ha
  unfold iLn at h
  dsimp only at h
  by_cases hneg : a.lo ≤ 0
  · rw [if_pos hneg] at h
    obtain ⟨u, c1, h1, -⟩ := M.bind_ok h
    exact (M.throw_not_ok h1).elim
  · rw [if_neg hneg] at h
    have hlo0 : (0 : ℚ) < a.lo := not_le.mp hneg
    have hlor : (0 : ℝ) < (a.lo : ℝ) := by exact_mod_cast hlo0
    have hx : 0 < x := lt_of_lt_of_le hlor hlo
    have hhir : (0 : ℝ) < (a.hi : ℝ) := lt_of_lt_of_le hx hhi
    have hhi0 : (0 : ℚ) < a.hi := by exact_mod_cast hhir
    obtain ⟨u, c1, h1, h2⟩ := M.bind_ok h
    rw [(M.pure_ok h1).2] at h2
    obtain ⟨va, c2, h3, h4⟩ := M.bind_ok h2
    obtain ⟨vb, c3, h5, h6⟩ := M.bind_ok h4
    obtain ⟨hr, hc'⟩ := M.pure_ok h6
    obtain ⟨hc2, hla, -⟩ := lnPoint_sound hs hc hlo0 h3
    obtain ⟨hc3, -, hlb⟩ := lnPoint_sound hs hc2 hhi0 h5
    rw [hr, hc']
    exact ⟨hc3, hx, le_trans hla ((Real.log_le_log_iff hlor hx).2 hlo),
      le_trans ((Real.log_le_log_iff hx hhir).2 hhi) hlb⟩

/-! ## exp -/

private theorem expPoint_cases {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    (h : expPoint q c = .ok (v, c')) :
    (q = 0 ∧ v = (1, 1) ∧ c' = c) ∨
    (c.exp.get? (q.num, q.den) = some v ∧ c' = c) ∨
    (grid (expAt q) = .ok v ∧ c' = { c with exp := c.exp.insert (q.num, q.den) v }) := by
  unfold expPoint at h
  dsimp only at h
  by_cases h1 : (q == 0) = true
  · rw [if_pos h1] at h
    obtain ⟨hv, hc'⟩ := M.pure_ok h
    exact Or.inl ⟨beq_iff_eq.mp h1, hv, hc'⟩
  · rw [if_neg h1] at h
    obtain ⟨u, c1, h2, h3⟩ := M.bind_ok h
    rw [(M.pure_ok h2).2] at h3
    obtain ⟨s, c2, h4, h5⟩ := M.bind_ok h3
    obtain ⟨hs1, hs2⟩ := get_ok h4
    rw [hs1, hs2] at h5
    cases hget : c.exp.get? (q.num, q.den) with
    | some w =>
      rw [hget] at h5
      obtain ⟨hv, hc'⟩ := M.pure_ok h5
      exact Or.inr (Or.inl ⟨by rw [hv], hc'⟩)
    | none =>
      rw [hget] at h5
      obtain ⟨w, c3, h6, h7⟩ := M.bind_ok h5
      obtain ⟨hg, hc3⟩ := M.lift_ok h6
      rw [hc3] at h7
      obtain ⟨u', c4, h8, h9⟩ := M.bind_ok h7
      rw [modify_ok h8] at h9
      obtain ⟨hv, hc'⟩ := M.pure_ok h9
      subst hv
      exact Or.inr (Or.inr ⟨hg, hc'⟩)

private theorem expPoint_sound (hs : ExpAtSpec) {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    (hc : c.Valid) (h : expPoint q c = .ok (v, c')) :
    c'.Valid ∧ (v.1 : ℝ) ≤ Real.exp (q : ℝ) ∧ Real.exp (q : ℝ) ≤ (v.2 : ℝ) := by
  rcases expPoint_cases h with ⟨rfl, rfl, rfl⟩ | ⟨hget, rfl⟩ | ⟨hg, rfl⟩
  · refine ⟨hc, ?_, ?_⟩ <;> simp
  · exact ⟨hc, hc.2 q v hget⟩
  · have hb := grid_sound (hs q) hg
    refine ⟨⟨hc.1, fun x w hget => ?_⟩, hb⟩
    have hget' : (c.exp.insert (q.num, q.den) v).get? (x.num, x.den) = some w := hget
    rw [Std.HashMap.get?_insert] at hget'
    by_cases hk : ((q.num, q.den) == (x.num, x.den)) = true
    · rw [if_pos hk] at hget'
      cases hget'
      rw [← key_eq hk]
      exact hb
    · rw [if_neg hk] at hget'
      exact hc.2 x w hget'

/-- If `expAt` holds exp, the result of `iExp` holds the exponential of every real the
interval holds, and `iExp` keeps the caches valid. -/
theorem iExp_sound (hs : ExpAtSpec) {a r : Iv} {x : ℝ} {c c' : Caches} (hc : c.Valid)
    (ha : a.Holds x) (h : iExp a c = .ok (r, c')) : c'.Valid ∧ r.Holds (Real.exp x) := by
  obtain ⟨hlo, hhi⟩ := ha
  unfold iExp at h
  obtain ⟨va, c2, h3, h4⟩ := M.bind_ok h
  obtain ⟨vb, c3, h5, h6⟩ := M.bind_ok h4
  obtain ⟨hr, hc'⟩ := M.pure_ok h6
  obtain ⟨hc2, hla, -⟩ := expPoint_sound hs hc h3
  obtain ⟨hc3, -, hlb⟩ := expPoint_sound hs hc2 h5
  rw [hr, hc']
  exact ⟨hc3, le_trans hla (Real.exp_le_exp.2 hlo), le_trans (Real.exp_le_exp.2 hhi) hlb⟩

/-- `iExp` keeps the caches valid, on any interval. -/
theorem iExp_valid (hs : ExpAtSpec) {a r : Iv} {c c' : Caches} (hc : c.Valid)
    (h : iExp a c = .ok (r, c')) : c'.Valid := by
  unfold iExp at h
  obtain ⟨va, c2, h3, h4⟩ := M.bind_ok h
  obtain ⟨vb, c3, h5, h6⟩ := M.bind_ok h4
  obtain ⟨-, hc'⟩ := M.pure_ok h6
  rw [hc']
  exact (expPoint_sound hs (expPoint_sound hs hc h3).1 h5).1

end Petra
