/-
Exact rationals and closed rational intervals, as petra/kernel/interval.py defines them.

+, -, *, / and integer powers are exact. sqrt, ln, exp and pi round outward to the grid of
dyadic rationals with 96 fractional bits: the lower end is the largest grid point at or
below the value, and the upper end the smallest at or above it. The mathematics fixes both
ends, so this kernel and the Python one agree on them whatever series each sums.

No definition here is a `partial def` or runs a `while`: each loop is a recursion that Lean
checks to end. So the logic can read every one, and proofs/ proves what each returns
(docs/proved.md).
-/
import Std.Data.HashMap

namespace Petra

structure Iv where
  lo : Rat
  hi : Rat

instance : Inhabited Iv := ⟨⟨0, 0⟩⟩

def PREC : Nat := 96
def GRID : Int := (2 : Int) ^ PREC

@[inline] def qi (n : Int) : Rat := mkRat n 1
@[inline] def qd (n d : Int) : Rat := mkRat n d.toNat
@[inline] def rmin (a b : Rat) : Rat := if a ≤ b then a else b
@[inline] def rmax (a b : Rat) : Rat := if a ≤ b then b else a

namespace Iv
@[inline] def pt (x : Rat) : Iv := ⟨x, x⟩
@[inline] def add (a b : Iv) : Iv := ⟨a.lo + b.lo, a.hi + b.hi⟩
@[inline] def neg (a : Iv) : Iv := ⟨-a.hi, -a.lo⟩
@[inline] def sub (a b : Iv) : Iv := ⟨a.lo - b.hi, a.hi - b.lo⟩
def mul (a b : Iv) : Iv :=
  let p1 := a.lo * b.lo
  let p2 := a.lo * b.hi
  let p3 := a.hi * b.lo
  let p4 := a.hi * b.hi
  ⟨rmin (rmin p1 p2) (rmin p3 p4), rmax (rmax p1 p2) (rmax p3 p4)⟩
def div (a b : Iv) : Except String Iv :=
  if b.lo ≤ 0 ∧ 0 ≤ b.hi then .error "division by an interval that contains 0"
  else .ok (a.mul ⟨1 / b.hi, 1 / b.lo⟩)
def abs (a : Iv) : Iv :=
  if 0 ≤ a.lo then a else if a.hi ≤ 0 then a.neg else ⟨0, rmax (-a.lo) a.hi⟩
@[inline] def min (a b : Iv) : Iv := ⟨rmin a.lo b.lo, rmin a.hi b.hi⟩
@[inline] def max (a b : Iv) : Iv := ⟨rmax a.lo b.lo, rmax a.hi b.hi⟩
@[inline] def has (a : Iv) (x : Rat) : Bool := a.lo ≤ x && x ≤ a.hi
@[inline] def within (a b : Iv) : Bool := b.lo ≤ a.lo && a.hi ≤ b.hi
end Iv

def rpow (x : Rat) : Nat → Rat
  | 0 => 1
  | n + 1 => x * rpow x n

/-- x^n for n >= 0, tight for an even n over an interval that straddles 0. -/
def powInt (a : Iv) (n : Int) : Except String Iv :=
  if n < 0 then .error "negative exponent" else
  let k := n.toNat
  let x := rpow a.lo k
  let y := rpow a.hi k
  if k == 0 || k % 2 == 1 || 0 ≤ a.lo then .ok ⟨x, y⟩
  else if a.hi ≤ 0 then .ok ⟨y, x⟩
  else .ok ⟨0, rmax x y⟩

def bitlen (n : Nat) : Nat := if n == 0 then 0 else Nat.log2 n + 1

/-- Newton's iteration from above: step down while the next value is smaller. The value
goes down at every step, so the recursion ends. -/
def isqrtGo (n x : Nat) : Nat :=
  if _h : (x + n / x) / 2 < x then isqrtGo n ((x + n / x) / 2) else x
termination_by x

/-- floor (sqrt n), by Newton's iteration from above. -/
def isqrt (n : Nat) : Nat :=
  if n == 0 then 0 else isqrtGo n (2 ^ (Nat.log2 n / 2 + 1))

/-- With y = x * 4^PREC, sqrt x * 2^PREC = sqrt y. floor (sqrt y) is isqrt (floor y), and
ceil (sqrt y) is that integer when its square is y and the next integer otherwise. -/
def iSqrt (x : Iv) : Except String Iv :=
  if x.lo < 0 then .error "sqrt over an interval with negative values" else
  let g2 : Rat := qi (GRID * GRID)
  let top := x.hi * g2
  let hiN := isqrt top.floor.toNat
  let loN := isqrt (x.lo * g2).floor.toNat
  let exact := qi (Int.ofNat (hiN * hiN)) == top
  .ok ⟨qd (Int.ofNat loN) GRID, qd (Int.ofNat (if exact then hiN else hiN + 1)) GRID⟩

/-- [a, b] * c rounded outward to integers. -/
def scale (a b : Int) (c : Rat) : Int × Int :=
  let lo := if 0 ≤ c then a else b
  let hi := if 0 ≤ c then b else a
  let n := c.num
  let d : Int := Int.ofNat c.den
  (Int.fdiv (lo * n) d, - Int.fdiv (-(hi * n)) d)

/-- The loop of the series. `[a, b]` holds term `k` times `one`, and `[lo, hi]` holds the sum
of the terms before it times `one`. It gives the sum and the number of terms summed. The
power of 3 grows at every round, so the recursion ends. -/
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

def ln2At (p : Nat) : Iv := (Iv.pt 2).mul (oddSeries (mkRat 1 3) 1 p)

def ln2_128 : Iv := ln2At 128

/-- ln x = 2 atanh z + e ln 2, where x = m 2^e with m in (1/2, 2) and z = (m - 1)/(m + 1). -/
def lnAt (x : Rat) (p : Nat) : Iv :=
  let e : Int := Int.ofNat (bitlen x.num.natAbs) - Int.ofNat (bitlen x.den)
  let m : Rat := if 0 ≤ e then x / qi ((2 : Int) ^ e.toNat) else x * qi ((2 : Int) ^ (-e).toNat)
  let z := (m - 1) / (m + 1)
  let l2 := if p == 128 then ln2_128 else ln2At p
  ((Iv.pt 2).mul (oddSeries z 1 p)).add ((Iv.pt (qi e)).mul l2)

/-- The loop of the series sum_n r^n / n!. `[ta, tb]` holds term `n` times `one`, `[a, b]`
holds the sum of the terms up to `n` times `one`, and `fact` is `(n + 1)!`. The first
argument counts the rounds left, so the recursion ends. It gives the sum, `n` and `fact`. -/
def expGo (one : Int) (r : Rat) :
    Nat → Int → Int → Int → Int → Nat → Int → Int × Int × Nat × Int
  | 0, _, _, a, b, n, fact => (a, b, n, fact)
  | rounds + 1, ta, tb, a, b, n, fact =>
    if (2 : Int) ^ n * fact ≤ one then
      let t := scale ta tb (r / qi (Int.ofNat (n + 1)))
      expGo one r rounds t.1 t.2 (a + t.1) (b + t.2) (n + 1) (fact * Int.ofNat (n + 1 + 1))
    else (a, b, n, fact)

/-- `j` squarings of `[a, b] / one`, each rounded outward. -/
def sqGo (one : Int) : Nat → Int → Int → Int × Int
  | 0, a, b => (a, b)
  | j + 1, a, b => sqGo one j (Int.fdiv (a * a) one) (- Int.fdiv (-(b * b)) one)

/-- An enclosure of `exp (r * 2 ^ s)` times `2 ^ q`, for `0 <= r <= 1/2`: the series for
`exp r`, its remainder, and `s` squarings. The loop is given `q + 1` rounds and its own
test ends it sooner: `2 ^ n <= 2 ^ n * fact <= 2 ^ q` needs `n <= q`. -/
def expInt (r : Rat) (s q : Nat) : Int × Int :=
  let one : Int := (2 : Int) ^ q
  let g := expGo one r (q + 1) one one one one 0 1
  sqGo one s g.1 (g.2.1 + (- Int.fdiv (-one) ((2 : Int) ^ g.2.2.1 * g.2.2.2)))

/-- exp x for x >= 0: exp(r)^(2^s) with r = x / 2^s < 1/2. The working precision q grows
with s and x, since each squaring doubles the relative error. -/
def expPos (x : Rat) (p : Nat) : Iv :=
  let c := x.ceil.toNat
  let s := bitlen c + 1
  let q := p + 2 * s + 2 * c
  let one : Int := (2 : Int) ^ q
  let e := expInt (x / qi ((2 : Int) ^ s)) s q
  ⟨qd e.1 one, qd e.2 one⟩

/-- exp x: `expPos x` for x >= 0, and 1 / exp(-x) for x < 0. -/
def expAt (x : Rat) (p : Nat) : Iv :=
  if x < 0 then
    let e := expPos (-x) p
    ⟨1 / e.hi, 1 / e.lo⟩
  else expPos x p

/-- Machin's formula: pi = 16 atan(1/5) - 4 atan(1/239). -/
def piAt (p : Nat) : Iv :=
  ((Iv.pt 16).mul (oddSeries (mkRat 1 5) (-1) p)).sub ((Iv.pt 4).mul (oddSeries (mkRat 1 239) (-1) p))

/-- The grid points just below and just above the real that `enc p` encloses. Every caller
passes an irrational value, so a fine enough enclosure separates it from the grid. -/
def grid (enc : Nat → Iv) : Except String (Rat × Rat) := Id.run do
  for extra in [32, 128, 512, 2048] do
    let e := enc (PREC + extra)
    let lo := (e.lo * qi GRID).floor
    let hi := (e.hi * qi GRID).ceil
    if hi - lo ≤ 1 then return .ok (qd lo GRID, qd hi GRID)
  return .error "no enclosure separated the value from the rounding grid"

def piIv : Except String Iv := (grid piAt).map fun (lo, hi) => ⟨lo, hi⟩

abbrev Cache := Std.HashMap (Int × Nat) (Rat × Rat)

structure Caches where
  ln : Cache := {}
  exp : Cache := {}

abbrev M := StateT Caches (Except String)

def lnPoint (x : Rat) : M (Rat × Rat) := do
  if x == 1 then return (0, 0)
  let key := (x.num, x.den)
  match (← get).ln.get? key with
  | some v => return v
  | none =>
    let v ← liftM (m := Except String) (grid (lnAt x))
    modify fun c => { c with ln := c.ln.insert key v }
    return v

def expPoint (x : Rat) : M (Rat × Rat) := do
  if x == 0 then return (1, 1)
  let key := (x.num, x.den)
  match (← get).exp.get? key with
  | some v => return v
  | none =>
    let v ← liftM (m := Except String) (grid (expAt x))
    modify fun c => { c with exp := c.exp.insert key v }
    return v

def iLn (x : Iv) : M Iv := do
  if x.lo ≤ 0 then throw "ln over an interval with non-positive values"
  return ⟨(← lnPoint x.lo).1, (← lnPoint x.hi).2⟩

def iExp (x : Iv) : M Iv := do
  return ⟨(← expPoint x.lo).1, (← expPoint x.hi).2⟩

/-- The longest string the kernel reads as a number. -/
def MAX_NUMBER_CHARS : Nat := 4000

/-- The digits of a natural number, with no leading zero. -/
def natural (digits : List Char) : Option Nat :=
  if digits.isEmpty || !digits.all Char.isDigit || (digits.length > 1 && digits.head? == some '0') then none
  else some (digits.foldl (fun n c => 10 * n + (c.toNat - '0'.toNat)) 0)

/-- A rational in the one spelling petra/kernel/interval.py's `parse_q` takes: "n", or "p/q"
in lowest terms with q > 1. One rational has one spelling, so a hash of a file is a hash of
its numbers. -/
def parseRat (text : String) : Except String Rat := do
  if text.length > MAX_NUMBER_CHARS then
    throw s!"a number of {text.length} characters is over the budget of {MAX_NUMBER_CHARS}"
  let (negative, body) := match text.toList with
    | '-' :: rest => (true, rest)
    | chars => (false, chars)
  let (top, rest) := body.span (· != '/')
  let value : Option Rat := do
    let n ← natural top
    let signed : Int := if negative then -Int.ofNat n else Int.ofNat n
    match rest with
    | [] => if negative && n == 0 then none else some (qi signed)
    | _ :: bottom =>
      let d ← natural bottom
      if d ≤ 1 || n.gcd d != 1 then none else some (mkRat signed d)
  match value with
  | some x => return x
  | none => throw s!"not a canonical rational: {String.ofList (text.toList.take 40)}"

end Petra
