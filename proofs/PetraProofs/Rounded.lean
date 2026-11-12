/-
The rounded functions: `iSqrt`, `piIv`, `iLn`, `iExp` and `iCos` return an interval that
holds the true value.

Each theorem is about the kernel's own function, and none takes a hypothesis about it.
Loops/ proves what the four loops return: `isqrt`, `oddSeries`, `expAt` and `cosAt`. What is
proved here is everything around those loops: the rounding to the grid, the scaling of the
square root, Machin's formula, the reduction of ln to atanh, where the cosine falls and
where it rises between the multiples of pi, and the caches.
-/
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Arctan
import Mathlib.Analysis.SpecialFunctions.Log.Basic
import Mathlib.Data.Rat.Floor
import PetraProofs.Spec
import PetraProofs.Arith
import PetraProofs.Loops.Isqrt
import PetraProofs.Loops.OddSeries
import PetraProofs.Loops.ExpAt
import PetraProofs.Loops.CosAt

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

/-- What `grid` returns is the pair of grid points around the enclosure it asked for. -/
private theorem grid_ok {enc : Nat → Iv} {extra : Nat} {lo hi : ℚ} (h : grid enc extra = .ok (lo, hi)) :
    lo = qd ((enc (PREC + extra)).lo * qi GRID).floor GRID ∧
      hi = qd ((enc (PREC + extra)).hi * qi GRID).ceil GRID := by
  unfold grid at h
  dsimp only at h
  split_ifs at h
  exact ⟨(Prod.mk.inj (Except.ok.inj h)).1.symm, (Prod.mk.inj (Except.ok.inj h)).2.symm⟩

/-- If every enclosure `enc p` holds `x`, the pair of grid points that `grid` returns has
`x` between them, whichever enclosure it rounded from. -/
theorem grid_sound {enc : Nat → Iv} {extra : Nat} {x : ℝ} {lo hi : ℚ} (henc : ∀ p, (enc p).Holds x)
    (h : grid enc extra = .ok (lo, hi)) : (lo : ℝ) ≤ x ∧ x ≤ (hi : ℝ) := by
  obtain ⟨rfl, rfl⟩ := grid_ok h
  obtain ⟨h1, h2⟩ := henc (PREC + extra)
  exact ⟨le_trans (Rat.cast_le.2 (grid_lo_le _)) h1, le_trans h2 (Rat.cast_le.2 (grid_le_hi _))⟩

/-! ## The square root

With `G = 2^96`, `gridSqrt` returns `isqrt ⌊lo G²⌋ / G` and `isqrt ⌊hi G²⌋ / G`, the second
plus `1 / G` unless its square is exactly `hi G²`. `iSqrt` returns that, or, for a point
that `rootOf` finds to be the square of a fraction, that fraction at both ends. -/

private theorem gridSqrt_eq (a : Iv) : gridSqrt a =
    ⟨qd (Int.ofNat (isqrt (a.lo * qi (GRID * GRID)).floor.toNat)) GRID,
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

/-- If `isqrt` is the integer square root, the grid's root of an interval with no negative
number holds the square root of every real the interval holds. -/
private theorem gridSqrt_sound {a : Iv} {x : ℝ} (h0 : (0 : ℚ) ≤ a.lo) (ha : a.Holds x) :
    (gridSqrt a).Holds (Real.sqrt x) := by
  obtain ⟨hlo, hhi⟩ := ha
  rw [gridSqrt_eq]
  by_cases hex : (qi (Int.ofNat (isqrt (a.hi * qi (GRID * GRID)).floor.toNat *
      isqrt (a.hi * qi (GRID * GRID)).floor.toNat)) == a.hi * qi (GRID * GRID)) = true
  · rw [if_pos hex]
    refine ⟨sqrt_lower h0 hlo (Loops.isqrt_spec _).1, sqrt_upper hhi ?_⟩
    have heq := beq_iff_eq.mp hex
    exact le_of_eq (heq.symm.trans (qi_ofNat _))
  · rw [if_neg hex]
    refine ⟨sqrt_lower h0 hlo (Loops.isqrt_spec _).1, sqrt_upper hhi ?_⟩
    have hlt := (Loops.isqrt_spec (a.hi * qi (GRID * GRID)).floor.toNat).2
    have h1 : (a.hi * qi (GRID * GRID)).floor <
        (((isqrt (a.hi * qi (GRID * GRID)).floor.toNat + 1) *
          (isqrt (a.hi * qi (GRID * GRID)).floor.toNat + 1) : ℕ) : ℤ) :=
      lt_of_le_of_lt (Int.self_le_toNat _) (by exact_mod_cast hlt)
    have h2 := Rat.floor_lt_iff.mp h1
    exact le_of_lt (by exact_mod_cast h2)

/-- A fraction that `rootOf` gives is at least zero, and its square is the fraction it was
given. -/
private theorem rootOf_sound {q r : ℚ} (h : rootOf q = some r) : 0 ≤ r ∧ r * r = q := by
  unfold rootOf at h
  dsimp only at h
  split_ifs at h with hsq
  · obtain rfl := Option.some.inj h
    refine ⟨?_, beq_iff_eq.mp hsq⟩
    rw [Rat.mkRat_eq_div]
    have hn0 : (0 : ℤ) ≤ Int.ofNat (isqrt q.num.toNat) := Int.natCast_nonneg _
    have hn : (0 : ℚ) ≤ ((Int.ofNat (isqrt q.num.toNat) : ℤ) : ℚ) := by exact_mod_cast hn0
    exact div_nonneg hn (Nat.cast_nonneg _)

/-- If `isqrt` is the integer square root, `iSqrt` succeeds only on an interval with no
negative number, and its result holds the square root of every real the interval holds. -/
theorem iSqrt_sound {a r : Iv} {x : ℝ} (ha : a.Holds x)
    (h : iSqrt a = .ok r) : 0 ≤ x ∧ r.Holds (Real.sqrt x) := by
  unfold iSqrt at h
  by_cases hneg : a.lo < 0
  · rw [if_pos hneg] at h
    cases h
  rw [if_neg hneg] at h
  have h0 : (0 : ℚ) ≤ a.lo := not_lt.mp hneg
  have hx0 : (0 : ℝ) ≤ x := le_trans (by exact_mod_cast h0) ha.1
  refine ⟨hx0, ?_⟩
  split at h
  · rename_i q hq
    cases h
    by_cases hpt : (a.lo == a.hi) = true
    · rw [if_pos hpt] at hq
      obtain ⟨hq0, hqq⟩ := rootOf_sound hq
      have hlh : a.lo = a.hi := beq_iff_eq.mp hpt
      have hx : x = ((a.lo : ℚ) : ℝ) := le_antisymm (by rw [hlh]; exact ha.2) ha.1
      have hs : Real.sqrt x = ((q : ℚ) : ℝ) := by
        rw [hx, ← hqq]
        push_cast
        exact Real.sqrt_mul_self (by exact_mod_cast hq0)
      exact ⟨le_of_eq hs.symm, le_of_eq hs⟩
    · rw [if_neg hpt] at hq
      cases hq
  · cases h
    exact gridSqrt_sound h0 ha

/-! ## Pi

`piAt` is Machin's formula, 16 arctan (1/5) - 4 arctan (1/239), on two runs of `oddSeries`. -/

private theorem piAt_sound (p : ℕ) : (piAt p).Holds Real.pi := by
  have h5 : |(mkRat 1 5 : ℚ)| ≤ 1 / 3 := by
    rw [Rat.mkRat_eq_div, abs_le]
    constructor <;> norm_num
  have h239 : |(mkRat 1 239 : ℚ)| ≤ 1 / 3 := by
    rw [Rat.mkRat_eq_div, abs_le]
    constructor <;> norm_num
  have a5 := (Loops.oddSeries_spec _ p h5).2
  have a239 := (Loops.oddSeries_spec _ p h239).2
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
theorem piIv_sound {r : Iv} (h : piIv = .ok r) : r.Holds Real.pi := by
  unfold piIv at h
  cases hg : grid piAt 32 with
  | error e =>
    rw [hg] at h
    cases h
  | ok v =>
    rw [hg] at h
    obtain ⟨lo, hi⟩ := v
    have h' : (Except.ok ⟨lo, hi⟩ : Except String Iv) = .ok r := h
    cases h'
    exact grid_sound (piAt_sound) hg

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

private theorem ln2At_sound (p : ℕ) : (ln2At p).Holds (Real.log 2) := by
  have h3 : |(mkRat 1 3 : ℚ)| ≤ 1 / 3 := by
    rw [Rat.mkRat_eq_div, abs_le]
    constructor <;> norm_num
  have a := (Loops.oddSeries_spec _ p h3).1
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

private theorem lnAt_sound {x : ℚ} (hx : 0 < x) (p : ℕ) :
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
  have hser := (Loops.oddSeries_spec _ p hz).1
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
    · exact ln2At_sound 128
    · exact ln2At_sound p
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
of the argument. A cache is valid when every entry is right, and each call keeps it so.

A cache is a table kept in the order of its keys: by the numerator, and then by the
denominator. The two facts below are what the table's own theorems ask of that order. It
is an order, and two keys that it puts in one place are one key. -/

private instance keyOrder : Std.TransCmp (lexOrd : Ord (Int × Nat)).compare :=
  letI : Ord (Int × Nat) := lexOrd
  (inferInstance : Std.TransOrd (Int × Nat))

private theorem key_eq {q x : ℚ} (h : (lexOrd : Ord (Int × Nat)).compare (q.num, q.den) (x.num, x.den) = .eq) : q = x := by
  letI : Ord (Int × Nat) := lexOrd
  have h' : (q.num, q.den) = (x.num, x.den) := Std.LawfulEqOrd.eq_of_compare h
  exact Rat.ext (congrArg Prod.fst h') (congrArg Prod.snd h')

private theorem empty_get? {k : Int × Nat} {v : ℚ × ℚ} (h : (∅ : Cache).get? k = some v) : False := by
  rw [Std.TreeMap.get?_eq_getElem?, Std.TreeMap.getElem?_emptyc] at h
  cases h

/-- The empty caches, which the kernel starts from, are valid. -/
theorem Caches.valid_empty : ({} : Caches).Valid := by
  refine ⟨?_, ?_, ?_⟩
  · intro x v h _
    exact (empty_get? h).elim
  · intro x v h
    exact (empty_get? h).elim
  · intro x v h
    exact (empty_get? h).elim

private theorem modify_ok {f : Caches → Caches} {c c' : Caches} {u : PUnit}
    (h : (modify f : M PUnit) c = .ok (u, c')) : c' = f c := by
  have h' : (Except.ok (PUnit.unit, f c) : Except String (PUnit × Caches)) = .ok (u, c') := h
  cases h'
  rfl

/-- An entry of a cache that gained one is the new entry or an entry it had before: a full
cache starts again from the new entry, and loses entries but gains no other. -/
private theorem cached_get? {cache : Cache} {q x : ℚ} {v w : ℚ × ℚ}
    (h : (cached cache (q.num, q.den) v).get? (x.num, x.den) = some w) :
    (q = x ∧ w = v) ∨ cache.get? (x.num, x.den) = some w := by
  unfold cached at h
  rw [Std.TreeMap.get?_eq_getElem?, Std.TreeMap.getElem?_insert] at h
  by_cases hk : (lexOrd : Ord (Int × Nat)).compare (q.num, q.den) (x.num, x.den) = .eq
  · rw [if_pos hk] at h
    cases h
    exact Or.inl ⟨key_eq hk, rfl⟩
  · rw [if_neg hk] at h
    split_ifs at h
    · exact Or.inr h
    · exact (empty_get? h).elim

/-- The three ways `lnPoint` returns: the argument is 1, the cache has it, or `grid` computes
it and the cache gains it. -/
private theorem lnPoint_cases {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    {extra : Nat} (h : lnPoint q extra c = .ok (v, c')) :
    (q = 1 ∧ v = (0, 0) ∧ c' = c) ∨
    (c.ln.get? (q.num, q.den) = some v ∧ c' = c) ∨
    (grid (lnAt q) extra = .ok v ∧ c' = { c with ln := cached c.ln (q.num, q.den) v }) := by
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
    obtain ⟨hs1, hs2⟩ := M.get_ok h4
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

private theorem lnPoint_sound {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    (hc : c.Valid) (hq : 0 < q) {extra : Nat} (h : lnPoint q extra c = .ok (v, c')) :
    c'.Valid ∧ (v.1 : ℝ) ≤ Real.log (q : ℝ) ∧ Real.log (q : ℝ) ≤ (v.2 : ℝ) := by
  rcases lnPoint_cases h with ⟨rfl, rfl, rfl⟩ | ⟨hget, rfl⟩ | ⟨hg, rfl⟩
  · refine ⟨hc, ?_, ?_⟩ <;> simp
  · exact ⟨hc, hc.1 q v hget hq⟩
  · have hb := grid_sound (lnAt_sound hq) hg
    refine ⟨⟨fun x w hget hx => ?_, hc.2⟩, hb⟩
    obtain hnew | hold := cached_get? hget
    · rw [← hnew.1, hnew.2]
      exact hb
    · exact hc.1 x w hold hx

/-- `lnPoint` keeps the caches valid, whatever its argument: an entry under a key that is
not positive is never read as a logarithm. -/
private theorem lnPoint_valid {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    (hc : c.Valid) {extra : Nat} (h : lnPoint q extra c = .ok (v, c')) : c'.Valid := by
  rcases lnPoint_cases h with ⟨-, -, rfl⟩ | ⟨-, rfl⟩ | ⟨hg, rfl⟩
  · exact hc
  · exact hc
  · refine ⟨fun x w hget hx => ?_, hc.2⟩
    obtain hnew | hold := cached_get? hget
    · obtain ⟨hqx, hvw⟩ := hnew
      subst hqx
      rw [hvw]
      exact grid_sound (lnAt_sound hx) hg
    · exact hc.1 x w hold hx

/-- `iLn` keeps the caches valid, on any interval. -/
theorem iLn_valid {a r : Iv} {c c' : Caches} (hc : c.Valid)
    {extra : Nat} (h : iLn a extra c = .ok (r, c')) : c'.Valid := by
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
    exact lnPoint_valid (lnPoint_valid hc h3) h5

/-- If `oddSeries` holds the sums it is written to hold, `iLn` succeeds only on an interval
of positive numbers, its result holds the logarithm of every real the interval holds, and
it keeps the caches valid. -/
theorem iLn_sound {a r : Iv} {x : ℝ} {c c' : Caches} (hc : c.Valid)
    (ha : a.Holds x) {extra : Nat} (h : iLn a extra c = .ok (r, c')) : c'.Valid ∧ 0 < x ∧ r.Holds (Real.log x) := by
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
    obtain ⟨hc2, hla, -⟩ := lnPoint_sound hc hlo0 h3
    obtain ⟨hc3, -, hlb⟩ := lnPoint_sound hc2 hhi0 h5
    rw [hr, hc']
    exact ⟨hc3, hx, le_trans hla ((Real.log_le_log_iff hlor hx).2 hlo),
      le_trans ((Real.log_le_log_iff hx hhir).2 hhi) hlb⟩

/-! ## exp -/

private theorem expPoint_cases {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    {extra : Nat} (h : expPoint q extra c = .ok (v, c')) :
    (q = 0 ∧ v = (1, 1) ∧ c' = c) ∨
    (c.exp.get? (q.num, q.den) = some v ∧ c' = c) ∨
    (grid (expAt q) extra = .ok v ∧ c' = { c with exp := cached c.exp (q.num, q.den) v }) := by
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
    obtain ⟨hs1, hs2⟩ := M.get_ok h4
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

private theorem expPoint_sound {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    (hc : c.Valid) {extra : Nat} (h : expPoint q extra c = .ok (v, c')) :
    c'.Valid ∧ (v.1 : ℝ) ≤ Real.exp (q : ℝ) ∧ Real.exp (q : ℝ) ≤ (v.2 : ℝ) := by
  rcases expPoint_cases h with ⟨rfl, rfl, rfl⟩ | ⟨hget, rfl⟩ | ⟨hg, rfl⟩
  · refine ⟨hc, ?_, ?_⟩ <;> simp
  · exact ⟨hc, hc.2.1 q v hget⟩
  · have hb := grid_sound (Loops.expAt_spec q) hg
    refine ⟨⟨hc.1, fun x w hget => ?_, hc.2.2⟩, hb⟩
    obtain hnew | hold := cached_get? hget
    · rw [← hnew.1, hnew.2]
      exact hb
    · exact hc.2.1 x w hold

/-- If `expAt` holds exp, the result of `iExp` holds the exponential of every real the
interval holds, and `iExp` keeps the caches valid. -/
theorem iExp_sound {a r : Iv} {x : ℝ} {c c' : Caches} (hc : c.Valid)
    (ha : a.Holds x) {extra : Nat} (h : iExp a extra c = .ok (r, c')) : c'.Valid ∧ r.Holds (Real.exp x) := by
  obtain ⟨hlo, hhi⟩ := ha
  unfold iExp at h
  obtain ⟨va, c2, h3, h4⟩ := M.bind_ok h
  obtain ⟨vb, c3, h5, h6⟩ := M.bind_ok h4
  obtain ⟨hr, hc'⟩ := M.pure_ok h6
  obtain ⟨hc2, hla, -⟩ := expPoint_sound hc h3
  obtain ⟨hc3, -, hlb⟩ := expPoint_sound hc2 h5
  rw [hr, hc']
  exact ⟨hc3, le_trans hla (Real.exp_le_exp.2 hlo), le_trans (Real.exp_le_exp.2 hhi) hlb⟩

/-- `iExp` keeps the caches valid, on any interval. -/
theorem iExp_valid {a r : Iv} {c c' : Caches} (hc : c.Valid)
    {extra : Nat} (h : iExp a extra c = .ok (r, c')) : c'.Valid := by
  unfold iExp at h
  obtain ⟨va, c2, h3, h4⟩ := M.bind_ok h
  obtain ⟨vb, c3, h5, h6⟩ := M.bind_ok h4
  obtain ⟨-, hc'⟩ := M.pure_ok h6
  rw [hc']
  exact (expPoint_sound (expPoint_sound hc h3).1 h5).1

/-! ## cos

`cosPoint` keeps what it computed under the size of its argument: the cosine is even.
`iCos` places an interval among the multiples of pi with the enclosure `piIv` of pi, and
reads the cosine off the grid points of the two ends, by where the cosine falls and where
it rises. -/

private theorem cosPoint_cases {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    {extra : Nat} (h : cosPoint q extra c = .ok (v, c')) :
    (q = 0 ∧ v = (1, 1) ∧ c' = c) ∨
    (c.cos.get? ((if q < 0 then -q else q).num, (if q < 0 then -q else q).den) = some v ∧
      c' = c) ∨
    (grid (cosAt (if q < 0 then -q else q)) extra = .ok v ∧
      c' = { c with
        cos := cached c.cos ((if q < 0 then -q else q).num, (if q < 0 then -q else q).den) v }) := by
  unfold cosPoint at h
  dsimp only at h
  by_cases h1 : (q == 0) = true
  · rw [if_pos h1] at h
    obtain ⟨hv, hc'⟩ := M.pure_ok h
    exact Or.inl ⟨beq_iff_eq.mp h1, hv, hc'⟩
  · rw [if_neg h1] at h
    obtain ⟨u, c1, h2, h3⟩ := M.bind_ok h
    rw [(M.pure_ok h2).2] at h3
    obtain ⟨s, c2, h4, h5⟩ := M.bind_ok h3
    obtain ⟨hs1, hs2⟩ := M.get_ok h4
    rw [hs1, hs2] at h5
    cases hget : c.cos.get? ((if q < 0 then -q else q).num, (if q < 0 then -q else q).den) with
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

/-- The cosine of the size of a number is the number's cosine. -/
private theorem cos_size (q : ℚ) :
    Real.cos (((if q < 0 then -q else q : ℚ)) : ℝ) = Real.cos (q : ℝ) := by
  split_ifs
  · push_cast
    exact Real.cos_neg _
  · rfl

/-- `cosPoint` returns two numbers with cos q between them, for any rational `q`, and keeps
the caches valid. -/
private theorem cosPoint_sound {q : ℚ} {c c' : Caches} {v : ℚ × ℚ}
    (hc : c.Valid) {extra : Nat} (h : cosPoint q extra c = .ok (v, c')) :
    c'.Valid ∧ (v.1 : ℝ) ≤ Real.cos (q : ℝ) ∧ Real.cos (q : ℝ) ≤ (v.2 : ℝ) := by
  rcases cosPoint_cases h with ⟨rfl, rfl, rfl⟩ | ⟨hget, rfl⟩ | ⟨hg, rfl⟩
  · refine ⟨hc, ?_, ?_⟩ <;> simp
  · have hb := hc.2.2 _ v hget
    rw [cos_size] at hb
    exact ⟨hc, hb⟩
  · have hb := grid_sound (Loops.cosAt_spec _) hg
    refine ⟨⟨hc.1, hc.2.1, fun x w hget => ?_⟩, by rw [cos_size] at hb; exact hb⟩
    obtain hnew | hold := cached_get? hget
    · rw [← hnew.1, hnew.2]
      exact hb
    · exact hc.2.2 x w hold

/-- Between `k` pi and `k + 1` pi the cosine falls when `k` is even and rises when `k` is
odd. -/
private theorem cos_between {k : ℤ} {u v : ℝ} (hu : (k : ℝ) * Real.pi ≤ u) (huv : u ≤ v)
    (hv : v ≤ ((k : ℝ) + 1) * Real.pi) :
    (k % 2 = 0 → Real.cos v ≤ Real.cos u) ∧ (¬ k % 2 = 0 → Real.cos u ≤ Real.cos v) := by
  have e : ∀ t : ℝ, Real.cos t = (-1) ^ k * Real.cos (t - k * Real.pi) := by
    intro t
    have h := Real.cos_add_int_mul_pi (t - k * Real.pi) k
    rw [sub_add_cancel] at h
    exact h
  have hmono : Real.cos (v - k * Real.pi) ≤ Real.cos (u - k * Real.pi) :=
    Real.cos_le_cos_of_nonneg_of_le_pi (by linarith) (by linarith) (by linarith)
  constructor
  · intro hk
    have h1 : (-1 : ℝ) ^ k = 1 := Even.neg_one_zpow (Int.even_iff.mpr hk)
    rw [e u, e v, h1]
    linarith
  · intro hk
    have h1 : (-1 : ℝ) ^ k = -1 := Odd.neg_one_zpow (Int.odd_iff.mpr (by omega))
    rw [e u, e v, h1]
    linarith

/-- The result of `iCos` holds the cosine of every real the interval holds, whatever the
interval, and `iCos` keeps the caches valid. -/
theorem iCos_sound {a r : Iv} {x : ℝ} {c c' : Caches} (hc : c.Valid)
    (ha : a.Holds x) {extra : Nat} (h : iCos a extra c = .ok (r, c')) :
    c'.Valid ∧ r.Holds (Real.cos x) := by
  obtain ⟨hlo, hhi⟩ := ha
  unfold iCos at h
  obtain ⟨pi, c1, hpi, h1⟩ := M.bind_ok h
  obtain ⟨hpiv, rfl⟩ := M.lift_ok hpi
  have hpiH := piIv_sound hpiv
  dsimp only at h1
  generalize (a.lo / (if 0 ≤ a.lo then pi.hi else pi.lo)).floor = i at h1
  generalize (a.hi / (if 0 < a.hi then pi.lo else pi.hi)).ceil = j at h1
  by_cases hplaced : qi i * (if 0 ≤ i then pi.hi else pi.lo) ≤ a.lo ∧
      a.hi ≤ qi j * (if 0 ≤ j then pi.lo else pi.hi)
  swap
  · rw [if_neg hplaced] at h1
    exact (M.throw_not_ok h1).elim
  rw [if_pos hplaced] at h1
  by_cases hwide : i + 2 < j
  · -- more than two multiples of pi apart: from -1 to 1
    rw [if_pos hwide] at h1
    obtain ⟨rfl, rfl⟩ := M.pure_ok h1
    refine ⟨hc, ?_, ?_⟩
    · show ((-1 : ℚ) : ℝ) ≤ Real.cos x
      push_cast
      exact Real.neg_one_le_cos x
    · show Real.cos x ≤ ((1 : ℚ) : ℝ)
      push_cast
      exact Real.cos_le_one x
  rw [if_neg hwide] at h1
  obtain ⟨va, c2, h3, h4⟩ := M.bind_ok h1
  obtain ⟨vb, c3, h5, h6⟩ := M.bind_ok h4
  obtain ⟨hc2, hla, hua⟩ := cosPoint_sound hc h3
  obtain ⟨hc3, hlb, hub⟩ := cosPoint_sound hc2 h5
  -- `i` pi is at or under the lower end, and the upper end at or under `j` pi
  have ei : ((qi i : ℚ) : ℝ) = (i : ℝ) := by
    rw [qi_eq]
    exact Rat.cast_intCast i
  have ej : ((qi j : ℚ) : ℝ) = (j : ℝ) := by
    rw [qi_eq]
    exact Rat.cast_intCast j
  have hilo : (i : ℝ) * Real.pi ≤ (a.lo : ℝ) := by
    have h1 : ((qi i * (if 0 ≤ i then pi.hi else pi.lo) : ℚ) : ℝ) ≤ (a.lo : ℝ) := by
      exact_mod_cast hplaced.1
    refine le_trans ?_ h1
    rw [Rat.cast_mul, ei]
    split_ifs with h0
    · exact mul_le_mul_of_nonneg_left hpiH.2 (by exact_mod_cast h0)
    · exact mul_le_mul_of_nonpos_left hpiH.1 (by exact_mod_cast (not_le.mp h0).le)
  have hjhi : (a.hi : ℝ) ≤ (j : ℝ) * Real.pi := by
    have h1 : (a.hi : ℝ) ≤ ((qi j * (if 0 ≤ j then pi.lo else pi.hi) : ℚ) : ℝ) := by
      exact_mod_cast hplaced.2
    refine le_trans h1 ?_
    rw [Rat.cast_mul, ej]
    split_ifs with h0
    · exact mul_le_mul_of_nonneg_left hpiH.1 (by exact_mod_cast h0)
    · exact mul_le_mul_of_nonpos_left hpiH.2 (by exact_mod_cast (not_le.mp h0).le)
  have hpos := Real.pi_pos
  by_cases hone : j ≤ i + 1
  · -- between `i` pi and `i + 1` pi the cosine goes one way
    rw [if_pos hone] at h6
    obtain ⟨rfl, rfl⟩ := M.pure_ok h6
    have hj1 : (j : ℝ) ≤ (i : ℝ) + 1 := by exact_mod_cast hone
    have htop : (a.hi : ℝ) ≤ ((i : ℝ) + 1) * Real.pi :=
      le_trans hjhi (mul_le_mul_of_nonneg_right hj1 hpos.le)
    obtain ⟨d1, u1⟩ := cos_between hilo hlo (le_trans hhi htop)
    obtain ⟨d2, u2⟩ := cos_between (le_trans hilo hlo) hhi htop
    refine ⟨hc3, ?_⟩
    by_cases heven : i % 2 = 0
    · rw [if_pos heven]
      exact ⟨le_trans hlb (d2 heven), le_trans (d1 heven) hua⟩
    · rw [if_neg heven]
      exact ⟨le_trans hla (u1 heven), le_trans (u2 heven) hub⟩
  · -- `i + 1` pi may lie in the interval, and the cosine turns there
    rw [if_neg hone] at h6
    obtain ⟨rfl, rfl⟩ := M.pure_ok h6
    have hj2 : j = i + 2 := by omega
    have htop : (a.hi : ℝ) ≤ (((i + 1 : ℤ) : ℝ) + 1) * Real.pi := by
      rw [hj2] at hjhi
      push_cast at hjhi ⊢
      linarith
    refine ⟨hc3, ?_⟩
    by_cases heven : i % 2 = 0
    · rw [if_pos heven]
      have hodd : ¬ (i + 1) % 2 = 0 := by omega
      refine ⟨?_, ?_⟩
      · show ((-1 : ℚ) : ℝ) ≤ Real.cos x
        push_cast
        exact Real.neg_one_le_cos x
      · show Real.cos x ≤ ((rmax va.2 vb.2 : ℚ) : ℝ)
        rw [rmax_eq, Rat.cast_max]
        rcases le_total x (((i : ℝ) + 1) * Real.pi) with hx | hx
        · exact le_trans ((cos_between hilo hlo hx).1 heven) (le_trans hua (le_max_left _ _))
        · have hx' : ((i + 1 : ℤ) : ℝ) * Real.pi ≤ x := by
            push_cast
            exact hx
          exact le_trans ((cos_between hx' hhi htop).2 hodd) (le_trans hub (le_max_right _ _))
    · rw [if_neg heven]
      have hev : (i + 1) % 2 = 0 := by omega
      refine ⟨?_, ?_⟩
      · show ((rmin va.1 vb.1 : ℚ) : ℝ) ≤ Real.cos x
        rw [rmin_eq, Rat.cast_min]
        rcases le_total x (((i : ℝ) + 1) * Real.pi) with hx | hx
        · exact le_trans (le_trans (min_le_left _ _) hla) ((cos_between hilo hlo hx).2 heven)
        · have hx' : ((i + 1 : ℤ) : ℝ) * Real.pi ≤ x := by
            push_cast
            exact hx
          exact le_trans (le_trans (min_le_right _ _) hlb) ((cos_between hx' hhi htop).1 hev)
      · show Real.cos x ≤ ((1 : ℚ) : ℝ)
        push_cast
        exact Real.cos_le_one x

/-- `iCos` keeps the caches valid, on any interval, also one that holds no number. -/
theorem iCos_valid {a r : Iv} {c c' : Caches} (hc : c.Valid)
    {extra : Nat} (h : iCos a extra c = .ok (r, c')) : c'.Valid := by
  unfold iCos at h
  obtain ⟨pi, c1, hpi, h1⟩ := M.bind_ok h
  obtain ⟨-, rfl⟩ := M.lift_ok hpi
  dsimp only at h1
  generalize (a.lo / (if 0 ≤ a.lo then pi.hi else pi.lo)).floor = i at h1
  generalize (a.hi / (if 0 < a.hi then pi.lo else pi.hi)).ceil = j at h1
  by_cases hplaced : qi i * (if 0 ≤ i then pi.hi else pi.lo) ≤ a.lo ∧
      a.hi ≤ qi j * (if 0 ≤ j then pi.lo else pi.hi)
  swap
  · rw [if_neg hplaced] at h1
    exact (M.throw_not_ok h1).elim
  rw [if_pos hplaced] at h1
  by_cases hwide : i + 2 < j
  · rw [if_pos hwide] at h1
    obtain ⟨-, rfl⟩ := M.pure_ok h1
    exact hc
  rw [if_neg hwide] at h1
  obtain ⟨va, c2, h3, h4⟩ := M.bind_ok h1
  obtain ⟨vb, c3, h5, h6⟩ := M.bind_ok h4
  have hc3 := (cosPoint_sound (cosPoint_sound hc h3).1 h5).1
  by_cases hone : j ≤ i + 1
  · rw [if_pos hone] at h6
    obtain ⟨-, rfl⟩ := M.pure_ok h6
    exact hc3
  · rw [if_neg hone] at h6
    obtain ⟨-, rfl⟩ := M.pure_ok h6
    exact hc3

end Petra
