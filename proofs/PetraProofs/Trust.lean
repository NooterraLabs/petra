/-
What is assumed, and what a cache must hold.

Three functions of the kernel cannot be reasoned about in this toolchain. `isqrt` and
`oddSeries` run a `while` loop, and `expAt` is a `partial def` that also runs one. Lean
compiles `while` to `Lean.Loop.forIn`, a `partial def`, and the logic sees a `partial def`
as a constant with no equation. So no theorem can say what any of the three returns.

Each statement below says what one of them is written to return. None is proved of the
kernel's function. A theorem that needs one takes it as a hypothesis, by name, and never as
an axiom. Each is stated for any function, so that a function written without `while` can
be shown to meet it.
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

/-- Assumed: the kernel's `isqrt` runs a `while`. -/
def IsqrtSpec : Prop := IsqrtSpecOf isqrt

/-- Assumed: the kernel's `oddSeries` runs a `while`. -/
def OddSeriesSpec : Prop := OddSeriesSpecOf oddSeries

/-- Assumed: the kernel's `expAt` is a `partial def`. -/
def ExpAtSpec : Prop := ExpAtSpecOf expAt

/-- What a node's step assumes: nothing for arithmetic and `pick`, and for a rounded
function the statement about the loop it runs. -/
def Node.Trusted : Node → Prop
  | .sqrt _ => IsqrtSpec
  | .pi => OddSeriesSpec
  | .ln _ => OddSeriesSpec
  | .exp _ => ExpAtSpec
  | _ => True

/-- Every entry of the caches is right: the pair stored for `x` holds ln x, or exp x. The
key of `x` is its numerator and its denominator. -/
def Caches.Valid (c : Caches) : Prop :=
  (∀ (x : ℚ) (v : ℚ × ℚ), c.ln.get? (x.num, x.den) = some v → 0 < x →
    (v.1 : ℝ) ≤ Real.log (x : ℝ) ∧ Real.log (x : ℝ) ≤ (v.2 : ℝ)) ∧
  (∀ (x : ℚ) (v : ℚ × ℚ), c.exp.get? (x.num, x.den) = some v →
    (v.1 : ℝ) ≤ Real.exp (x : ℝ) ∧ Real.exp (x : ℝ) ≤ (v.2 : ℝ))

end Petra
