/-
What the kernel's three loops return, and what a cache must hold.

`isqrt`, `oddSeries` and `expAt` in kernel/Petra/Num.lean each run a loop, written as a
recursion that Lean checks to end. Each statement below says what one of them returns. It
is stated for any function, and Loops/ proves it of the kernel's own.

Nothing here is assumed. Until the kernel's loops were written this way, they ran a `while`
or were a `partial def`, the logic could not read them, and these three statements were
hypotheses of every theorem about `sqrt`, `pi`, `ln` and `exp`.
-/
import Mathlib.Analysis.SpecialFunctions.Trigonometric.Arctan
import PetraProofs.Meaning

namespace Petra

/-- `f n` is the floor of the square root of `n`. -/
def IsqrtSpecOf (f : Nat → Nat) : Prop :=
  ∀ n : Nat, f n * f n ≤ n ∧ n < (f n + 1) * (f n + 1)

/-- For `|x| ≤ 1/3`, `f x 1 p` holds atanh x, written here as `log ((1 + x) / (1 - x)) / 2`,
and `f x (-1) p` holds arctan x. -/
def OddSeriesSpecOf (f : ℚ → Int → Nat → Iv) : Prop :=
  ∀ (x : ℚ) (p : Nat), |x| ≤ 1 / 3 →
    (f x 1 p).Holds (Real.log ((1 + (x : ℝ)) / (1 - (x : ℝ))) / 2) ∧
    (f x (-1) p).Holds (Real.arctan (x : ℝ))

/-- `f x p` holds exp x. -/
def ExpAtSpecOf (f : ℚ → Nat → Iv) : Prop :=
  ∀ (x : ℚ) (p : Nat), (f x p).Holds (Real.exp (x : ℝ))

/-- Every entry of the caches is right: the pair stored for `x` holds ln x, or exp x. The
key of `x` is its numerator and its denominator. -/
def Caches.Valid (c : Caches) : Prop :=
  (∀ (x : ℚ) (v : ℚ × ℚ), c.ln.get? (x.num, x.den) = some v → 0 < x →
    (v.1 : ℝ) ≤ Real.log (x : ℝ) ∧ Real.log (x : ℝ) ≤ (v.2 : ℝ)) ∧
  (∀ (x : ℚ) (v : ℚ × ℚ), c.exp.get? (x.num, x.den) = some v →
    (v.1 : ℝ) ≤ Real.exp (x : ℝ) ∧ Real.exp (x : ℝ) ≤ (v.2 : ℝ))

end Petra
