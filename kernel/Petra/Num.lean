/-
Exact rationals and closed rational intervals, as petra/kernel/interval.py defines them.

+, -, *, / and integer powers are exact. sqrt, ln, exp, cos and pi round outward to the
grid of dyadic rationals with 96 fractional bits: the lower end is the largest grid point
at or below the value, and the upper end the smallest at or above it. The one exception is
the root of a point that is the square of a fraction, which is that fraction. The mathematics
fixes both ends, so this kernel and the Python one agree on them whatever series each sums.
The cosine of an interval also rests on where the interval lies among the multiples of pi,
which both kernels decide with the same comparisons against the grid's pi (`iCos`).

No definition here is a `partial def` or runs a `while`: each loop is a recursion that Lean
checks to end. So the logic can read every one, and proofs/ proves what each returns
(docs/proved.md).
-/
import Std.Data.TreeMap
import Std.Data.TreeSet

namespace Petra

/-- A pair is ordered by its first member, and then by its second.

Every table of the kernel is kept in the order of its keys, and none by a hash. A file
chooses the keys: its names, its labels and its numbers. A hash of them can be made to send
many keys to one place of a table, where a look then walks them all. A table kept in
order is a balanced tree: neither side of a key holds more than three times the keys of the
other. So a look compares the key with at most five keys for each two bits of the table's
count, and it reads no more of each than the key is long, whatever the file holds. -/
scoped instance [Ord α] [Ord β] : Ord (α × β) := lexOrd

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

/-- The square root of a fraction that is the square of one, or none: the root of its
numerator over the root of its denominator, when that squares back to it. -/
def rootOf (q : Rat) : Option Rat :=
  let r := mkRat (Int.ofNat (isqrt q.num.toNat)) (isqrt q.den)
  if r * r == q then some r else none

/-- The root of an interval rounded outward to the grid. With y = x * 4^PREC, sqrt x * 2^PREC
= sqrt y. floor (sqrt y) is isqrt (floor y), and ceil (sqrt y) is that integer when its
square is y and the next integer otherwise. -/
def gridSqrt (x : Iv) : Iv :=
  let g2 : Rat := qi (GRID * GRID)
  let top := x.hi * g2
  let hiN := isqrt top.floor.toNat
  let loN := isqrt (x.lo * g2).floor.toNat
  let exact := qi (Int.ofNat (hiN * hiN)) == top
  ⟨qd (Int.ofNat loN) GRID, qd (Int.ofNat (if exact then hiN else hiN + 1)) GRID⟩

/-- The root of a point that is the square of a fraction is that fraction, at both ends, and
the root of any other interval is rounded outward to the grid. So sqrt (3^2 + 4^2) is 5 and
not two grid points around it, and a strict inequality at it is decided. Only a point is
taken exactly: an interval with an end at a square still rounds that end to the grid, so that
an interval inside another never has a root that reaches outside the other's. -/
def iSqrt (x : Iv) : Except String Iv :=
  if x.lo < 0 then .error "sqrt over an interval with negative values" else
  match (if x.lo == x.hi then rootOf x.lo else none) with
  | some r => .ok ⟨r, r⟩
  | none => .ok (gridSqrt x)

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

/-- The loop of the series sum_n (-1)^n r^(2n) / (2n)!, where `m` is minus `r` squared.
`[ta, tb]` holds term `n` times `one`, `[a, b]` holds the sum of the terms up to `n` times
`one`, and `fact` is `(2n + 2)!`. The first argument counts the rounds left, so the
recursion ends. It gives the sum, `n` and `fact`. -/
def cosGo (one : Int) (m : Rat) :
    Nat → Int → Int → Int → Int → Nat → Int → Int × Int × Nat × Int
  | 0, _, _, a, b, n, fact => (a, b, n, fact)
  | rounds + 1, ta, tb, a, b, n, fact =>
    if (4 : Int) ^ n * fact ≤ one then
      let t := scale ta tb (m / qi (Int.ofNat ((2 * n + 1) * (2 * n + 2))))
      cosGo one m rounds t.1 t.2 (a + t.1) (b + t.2) (n + 1) (fact * Int.ofNat ((2 * n + 3) * (2 * n + 4)))
    else (a, b, n, fact)

/-- `j` doublings of the angle. `[a, b] / one` holds cos y, and cos 2y = 2 cos² y - 1. So
each round squares the enclosure, rounded outward: the square is at least `low`, which is
zero when the enclosure holds zero, and at most `high`. A cosine is at most 1, so the
upper end is kept at `one`. The lower end is at least minus `one` as it comes, since
`low` is not negative. -/
def dblGo (one : Int) : Nat → Int → Int → Int × Int
  | 0, a, b => (a, b)
  | j + 1, a, b =>
    let low := if 0 ≤ a then a * a else if b ≤ 0 then b * b else 0
    let high := if a * a ≤ b * b then b * b else a * a
    let hi := 2 * (- Int.fdiv (-high) one) - one
    dblGo one j (2 * Int.fdiv low one - one) (if hi ≤ one then hi else one)

/-- An enclosure of `cos (r * 2 ^ s)` times `2 ^ q`, for `r` between -1/2 and 1/2: the
series for `cos r`, its remainder, and `s` doublings of the angle. After the term `n` the
rest of the series is at most `1 / (4 ^ n * (2n + 2)!)` in size, whatever its sign. The
loop is given `q + 1` rounds and its own test ends it sooner: `4 ^ n <= 2 ^ q` needs
`2 n <= q`. -/
def cosInt (r : Rat) (s q : Nat) : Int × Int :=
  let one : Int := (2 : Int) ^ q
  let g := cosGo one (-(r * r)) (q + 1) one one one one 0 2
  let rest := - Int.fdiv (-one) ((4 : Int) ^ g.2.2.1 * g.2.2.2)
  dblGo one s (g.1 - rest) (g.2.1 + rest)

/-- cos x, for any x. The cosine is even, so it is that of `y`, the size of `x`, and
cos y = cos (2^s r) with r = y / 2^s < 1/2. Each doubling takes the error times four at
most, so the working precision q grows by two bits with each, and eight bits more pay for
the rounding of the terms of the series. -/
def cosAt (x : Rat) (p : Nat) : Iv :=
  let y := if x < 0 then -x else x
  let s := bitlen y.ceil.toNat + 1
  let q := p + 2 * s + 8
  let one : Int := (2 : Int) ^ q
  let e := cosInt (y / qi ((2 : Int) ^ s)) s q
  ⟨qd e.1 one, qd e.2 one⟩

/-- Machin's formula: pi = 16 atan(1/5) - 4 atan(1/239). -/
def piAt (p : Nat) : Iv :=
  ((Iv.pt 16).mul (oddSeries (mkRat 1 5) (-1) p)).sub ((Iv.pt 4).mul (oddSeries (mkRat 1 239) (-1) p))

/-- What `grid` says of an enclosure that has a grid point inside it. -/
def UNSEPARATED : String := "no enclosure separated the value from the rounding grid"

/-- How many bits more than the grid an enclosure has, in the order the kernel tries them.
`Tape.lean` asks for the next only when `grid` could not round from the one before, and
pays for each as it asks. -/
def EXTRAS : List Nat := [32, 128, 512, 2048]

/-- The grid points just below and just above the real that `enc p` encloses, read from the
enclosure with `extra` bits more than the grid. Every caller passes an irrational value, so
a fine enough enclosure separates it from the grid, and every enclosure that does gives the
same two points. -/
def grid (enc : Nat → Iv) (extra : Nat) : Except String (Rat × Rat) :=
  let e := enc (PREC + extra)
  let lo := (e.lo * qi GRID).floor
  let hi := (e.hi * qi GRID).ceil
  if hi - lo ≤ 1 then .ok (qd lo GRID, qd hi GRID) else .error UNSEPARATED

/-- Pi on the grid. The first enclosure separates it. -/
def piIv : Except String Iv := (grid piAt 32).map fun (lo, hi) => ⟨lo, hi⟩

/-- The ends a step has rounded, each under its numerator and its denominator, in the order
of the numerators and then of the denominators. A look compares the end it asks for with at
most 25 of the 1,024 ends a full cache holds, and with 10 or 11 of them as a rule. Each
comparison reads the two numbers from their top down to where they differ, so it costs no
more than the end has bits. -/
abbrev Cache := Std.TreeMap (Int × Nat) (Rat × Rat) lexOrd.compare

structure Caches where
  ln : Cache := {}
  exp : Cache := {}
  cos : Cache := {}

abbrev M := StateT Caches (Except String)

/-- The most entries a cache holds, which bounds what the caches hold and how many ends a
look compares. -/
def MAX_CACHED : Nat := 1024

/-- The cache with one entry more. A full cache starts again from the new entry: the ends of
the leaf before, which the next leaf reads again, are the entries that were added last. -/
def cached (cache : Cache) (key : Int × Nat) (v : Rat × Rat) : Cache :=
  (if cache.size < MAX_CACHED then cache else {}).insert key v

def lnPoint (x : Rat) (extra : Nat) : M (Rat × Rat) := do
  if x == 1 then return (0, 0)
  let key := (x.num, x.den)
  match (← get).ln.get? key with
  | some v => return v
  | none =>
    let v ← liftM (m := Except String) (grid (lnAt x) extra)
    modify fun c => { c with ln := cached c.ln key v }
    return v

def expPoint (x : Rat) (extra : Nat) : M (Rat × Rat) := do
  if x == 0 then return (1, 1)
  let key := (x.num, x.den)
  match (← get).exp.get? key with
  | some v => return v
  | none =>
    let v ← liftM (m := Except String) (grid (expAt x) extra)
    modify fun c => { c with exp := cached c.exp key v }
    return v

def iLn (x : Iv) (extra : Nat) : M Iv := do
  if x.lo ≤ 0 then throw "ln over an interval with non-positive values"
  return ⟨(← lnPoint x.lo extra).1, (← lnPoint x.hi extra).2⟩

def iExp (x : Iv) (extra : Nat) : M Iv := do
  return ⟨(← expPoint x.lo extra).1, (← expPoint x.hi extra).2⟩

/-- The grid points around cos x. cos 0 is 1, a point of the grid, and the cosine of any
other rational is irrational. The cosine is even, so the cache keeps an end under its
size, and an end and its negative are one entry. -/
def cosPoint (x : Rat) (extra : Nat) : M (Rat × Rat) := do
  if x == 0 then return (1, 1)
  let y := if x < 0 then -x else x
  let key := (y.num, y.den)
  match (← get).cos.get? key with
  | some v => return v
  | none =>
    let v ← liftM (m := Except String) (grid (cosAt y) extra)
    modify fun c => { c with cos := cached c.cos key v }
    return v

/-- What `iCos` says when the two tests of its multiples of pi do not hold. They hold for
every enclosure of pi whose ends are above zero. -/
def UNPLACED : String := "cos over an interval that the enclosure of pi does not place between two of its multiples"

/-- The cosine of an enclosure, for any enclosure.

Between `k` pi and `k + 1` pi the cosine falls when `k` is even and rises when `k` is odd,
and at `k` pi it is 1 or -1. The enclosure `pi` of pi places the interval: `i` is a whole
number with `i` pi at or under the lower end, and `j` one with the upper end at or under
`j` pi. Each is found by a division by an end of `pi`, and then tested: `i` times the end
of `pi` that makes the product greater is at least `i` pi, and `j` times the end that
makes it less is at most `j` pi. So what follows rests on the two tests and not on how
`i` and `j` were found.

- `j <= i + 1`: the interval lies between `i` pi and `i + 1` pi, where the cosine goes one
  way. Its enclosure is from the grid points around the cosines of the two ends.
- `j = i + 2`: `i + 1` pi may lie in the interval, and the cosine turns there, at -1 for
  an even `i` and at 1 for an odd one. That is one end of the enclosure, and the other is
  the greater, or the lesser, of the grid points of the two ends.
- `j > i + 2`: the enclosure is from -1 to 1.

An end that `pi` does not place on one side of a multiple of pi, since the multiple's
enclosure holds it, counts as on both: `j` is then `i + 2`, and the enclosure reaches to
1 or to -1. The cosine of such an end is closer to that than the grid is fine. -/
def iCos (x : Iv) (extra : Nat) : M Iv := do
  let pi ← liftM (m := Except String) piIv
  let i := (x.lo / (if 0 ≤ x.lo then pi.hi else pi.lo)).floor
  let j := (x.hi / (if 0 < x.hi then pi.lo else pi.hi)).ceil
  if qi i * (if 0 ≤ i then pi.hi else pi.lo) ≤ x.lo ∧ x.hi ≤ qi j * (if 0 ≤ j then pi.lo else pi.hi) then
    if i + 2 < j then return ⟨-1, 1⟩
    else do
      let a ← cosPoint x.lo extra
      let b ← cosPoint x.hi extra
      if j ≤ i + 1 then return (if i % 2 = 0 then ⟨b.1, a.2⟩ else ⟨a.1, b.2⟩)
      else return (if i % 2 = 0 then ⟨-1, rmax a.2 b.2⟩ else ⟨rmin a.1 b.1, 1⟩)
  else throw UNPLACED

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
