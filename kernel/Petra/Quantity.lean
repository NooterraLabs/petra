/-
Dimensions, units and the text of a quantity, as petra/units.py and petra/deck.py read them.
A rules deck writes its values with units, and the kernel reads them here: it takes no
conversion from the Python that wrote the file.
-/
import Petra.Num

namespace Petra

/-- A dimension: the exponents of (m, kg, s, A, degC). A square root halves them, so they
are rational. -/
structure Dim where
  m : Rat := 0
  kg : Rat := 0
  s : Rat := 0
  a : Rat := 0
  k : Rat := 0
  deriving BEq, Inhabited

namespace Dim
def zip (f : Rat → Rat → Rat) (x y : Dim) : Dim := ⟨f x.m y.m, f x.kg y.kg, f x.s y.s, f x.a y.a, f x.k y.k⟩
instance : Add Dim := ⟨zip (· + ·)⟩
instance : Sub Dim := ⟨zip (· - ·)⟩
def times (x : Dim) (c : Rat) : Dim := zip (fun e _ => e * c) x x
/-- The five exponents, each as its numerator and its denominator: what a table of
dimensions is keyed by. Two dimensions have one key when their exponents are equal. -/
def key (x : Dim) : Array (Int × Nat) := #[x.m, x.kg, x.s, x.a, x.k].map fun e => (e.num, e.den)
end Dim

def ENERGY : Dim := { m := 2, kg := 1, s := -2 }
def RESISTANCE : Dim := { m := 2, kg := 1, s := -3, a := -2 }

/-- The dimension names a rules deck may write, as `NAMED` in petra/deck.py. A moment is a
force times a length, as energy is. -/
def NAMED : List (String × Dim) := [
  ("dimensionless", {}), ("length", { m := 1 }), ("area", { m := 2 }), ("force", { m := 1, kg := 1, s := -2 }),
  ("stress", { m := -1, kg := 1, s := -2 }), ("mass", { kg := 1 }), ("time", { s := 1 }), ("temperature", { k := 1 }),
  ("energy", ENERGY), ("moment", ENERGY), ("current", { a := 1 }), ("voltage", { m := 2, kg := 1, s := -3, a := -1 }),
  ("power", { m := 2, kg := 1, s := -3 }), ("resistance", RESISTANCE)]

/-- Ten to the eighteenth, which is under 2^63: `digits` reads eighteen digits into a machine
word before it puts them on the number. -/
def PIECE : Nat := 1000000000000000000

/-- The number that the digits `cs` continue. `n` is the number so far without its last
digits, `piece` is those digits and `scale` is ten to their count, so the number so far is
`n * scale + piece`. A piece of eighteen digits is put on `n` with one product and one sum. -/
def digitsGo : List Char → Nat → Nat → Nat → Nat
  | [], n, piece, scale => n * scale + piece
  | c :: cs, n, piece, scale =>
    let piece := 10 * piece + (c.toNat - '0'.toNat)
    let scale := 10 * scale
    if scale == PIECE then digitsGo cs (n * PIECE + piece) 0 1 else digitsGo cs n piece scale

/-- The digits of a natural number. A leading zero is allowed here: a deck writes `0.60`.

The digits are read eighteen at a time, so a long number costs one step on long numbers for
each eighteen digits and not one for each digit. A rule that applies a row reads the row's
numbers again, and a digit at a time took a microsecond a digit. -/
def digits (cs : List Char) : Option Nat :=
  if cs.isEmpty || !cs.all Char.isDigit then none else some (digitsGo cs 0 0 1)

def integer : List Char → Option Int
  | '-' :: cs => (digits cs).map fun n => -Int.ofNat n
  | cs => (digits cs).map Int.ofNat

/-- `force`, `length^3` or `force/length`: names of `NAMED` with whole powers, multiplied or
divided from left to right, as `dimension` in petra/deck.py reads them. -/
def dimension (text : String) : Except String Dim := do
  let term (cs : List Char) : Option Dim := do
    let (name, power) := cs.span (· != '^')
    let unit ← NAMED.lookup (String.ofList name)
    let n ← if (power.drop 1).isEmpty then some 1 else integer (power.drop 1)
    return unit.times (qi n)
  let mut out : Dim := {}
  let mut sign : Rat := 1
  let mut word : List Char := []
  for c in text.toList.filter (· != ' ') ++ ['*'] do
    if c == '*' || c == '/' then
      let some d := term word.reverse | throw s!"{text} is not a dimension"
      out := out + d.times sign
      sign := if c == '*' then 1 else -1
      word := []
    else word := c :: word
  return out

/-- A dimension as card.json and design.json name one (`dimension_name` in petra/units.py):
a name, or the exponents that are not zero, as in `m^3 s^-1`. -/
def dimNamed (text : String) : Option Dim :=
  let named := NAMED ++ [("I2t", { a := 2, s := 1 }), ("resistance per length", { m := 1, kg := 1, s := -3, a := -2 })]
  match named.lookup text with
  | some d => some d
  | none => (text.splitOn " ").foldlM (init := {}) fun (d : Dim) token => do
    let (base, power) := token.toList.span (· != '^')
    let e := qi (← integer (power.drop 1))
    match String.ofList base with
    | "m" => some { d with m := d.m + e }
    | "kg" => some { d with kg := d.kg + e }
    | "s" => some { d with s := d.s + e }
    | "A" => some { d with a := d.a + e }
    | "degC" => some { d with k := d.k + e }
    | _ => none

def INCH : Rat := mkRat 127 5000
def LB : Rat := mkRat 45359237 100000000
def LBF : Rat := LB * mkRat 980665 100000
def KIP : Rat := 1000 * LBF
def MILE : Rat := 5280 * 12 * INCH

/-- Each unit a deck may write, its factor to SI and its dimension: `UNITS` and `CUSTOMARY`
of petra/units.py. The inch is 25.4 mm, the pound 0.45359237 kg and the pound-force a pound
times 9.80665 m/s2, all by definition. A mile is 5,280 ft, an ounce 1/16 lb, and a knot one
nautical mile, 1,852 m, an hour. A rotation is counted in turns, and a turn is the plain
number 1: `Hz` is one a second and `rpm` one a minute. `mAh` and `Ah` are a current for an
hour. A unit with a `/` in it, as `m/s`, is one spelling of this list and is never worked
out from its halves. -/
def UNITS : List (String × Rat × Dim) :=
  let length : Dim := { m := 1 }
  let area : Dim := { m := 2 }
  let force : Dim := { m := 1, kg := 1, s := -2 }
  let stress : Dim := { m := -1, kg := 1, s := -2 }
  let current : Dim := { a := 1 }
  let voltage : Dim := { m := 2, kg := 1, s := -3, a := -1 }
  let power : Dim := { m := 2, kg := 1, s := -3 }
  let time : Dim := { s := 1 }
  let turns : Dim := { s := -1 }
  let charge : Dim := { s := 1, a := 1 }
  let speed : Dim := { m := 1, s := -1 }
  let density : Dim := { m := -3, kg := 1 }
  [("kW", 1000, power), ("min", 60, time), ("h", 3600, time), ("Hz", 1, turns), ("rpm", mkRat 1 60, turns),
   ("mAh", mkRat 18 5, charge), ("Ah", 3600, charge),
   ("m/s", 1, speed), ("km/h", mkRat 5 18, speed), ("knot", mkRat 463 900, speed), ("mph", MILE / 3600, speed),
   ("kg/m3", 1, density), ("g/cm3", 1000, density), ("N/mm", 1000, { kg := 1, s := -2 }),
   ("lbf_in", LBF * INCH, ENERGY), ("lbf_ft", LBF * 12 * INCH, ENERGY), ("mile", MILE, length),
   ("lb", LB, { kg := 1 }), ("oz", LB / 16, { kg := 1 }),
   ("1", 1, {}), ("%", mkRat 1 100, {}),
   ("m", 1, length), ("mm", mkRat 1 1000, length), ("um", mkRat 1 1000000, length), ("cm", mkRat 1 100, length), ("km", 1000, length),
   ("mm2", mkRat 1 1000000, area), ("m2", 1, area),
   ("N", 1, force), ("kN", 1000, force), ("MN", 1000000, force),
   ("Pa", 1, stress), ("kPa", 1000, stress), ("MPa", 1000000, stress), ("GPa", 1000000000, stress),
   ("uA", mkRat 1 1000000, current), ("mA", mkRat 1 1000, current), ("A", 1, current), ("kA", 1000, current),
   ("V", 1, voltage), ("kV", 1000, voltage),
   ("ohm", 1, RESISTANCE), ("mohm", mkRat 1 1000, RESISTANCE), ("kohm", 1000, RESISTANCE), ("Mohm", 1000000, RESISTANCE),
   ("ohm/km", mkRat 1 1000, { m := 1, kg := 1, s := -3, a := -2 }),
   ("mW", mkRat 1 1000, power), ("W", 1, power), ("J", 1, ENERGY), ("Nm", 1, ENERGY), ("N m", 1, ENERGY),
   ("s", 1, { s := 1 }), ("ms", mkRat 1 1000, { s := 1 }), ("degC", 1, { k := 1 }),
   ("g", mkRat 1 1000, { kg := 1 }), ("kg", 1, { kg := 1 }), ("A2s", 1, { a := 2, s := 1 }),
   ("inch", INCH, length), ("ft", 12 * INCH, length), ("inch2", INCH * INCH, area),
   ("lbf", LBF, force), ("kip", KIP, force), ("kips", KIP, force),
   ("psi", LBF / (INCH * INCH), stress), ("ksi", KIP / (INCH * INCH), stress),
   ("kip_in", KIP * INCH, ENERGY), ("kip_ft", KIP * 12 * INCH, ENERGY)]

/-- The powers a unit of length may be raised to, each as it is written. One power has one
spelling: `inch^4`, and not `inch^04` or `inch^+4`. -/
def UNIT_POWERS : List (String × Nat) := [("2", 2), ("3", 3), ("4", 4)]

/-- A unit as a value writes it (`_unit` in petra/units.py): a spelling of `UNITS`, or a unit
of length, `^` and 2, 3 or 4, as in `mm^3` and `inch^4`. The factor is the unit's own factor
to that power, exactly, and the dimension is a length to that power. So `mm^2` is `mm2` and
`inch^2` is `inch2`. Only a unit of length takes a power: a section's area, modulus and
moment of inertia are lengths to a power, and a power of a unit that is itself a product or
a quotient, as `ohm/km` and `kip_in` are, could be read two ways. -/
def unitOf (unit : String) : Except String (Rat × Dim) :=
  match unit.splitOn "^" with
  | [name] =>
    match UNITS.lookup name with
    | some found => pure found
    | none => throw s!"{unit} is not a unit"
  | [name, power] =>
    match UNITS.lookup name, UNIT_POWERS.lookup power with
    | some (factor, dim), some n =>
      if dim == ({ m := 1 } : Dim) then pure (rpow factor n, dim.times (qi (Int.ofNat n)))
      else throw s!"{unit} is not a unit: only a unit of length takes a power"
    | none, _ => throw s!"{unit} is not a unit"
    | some _, none => throw s!"{unit} is not a unit: the power of a unit is 2, 3 or 4, as in inch^4"
  | _ => throw s!"{unit} is not a unit"

/-- A number as petra/units.py reads one: digits with an optional sign, and then a decimal
part or a denominator that is not zero. No exponent, no space and no other digit. -/
def decimal (text : List Char) : Option Rat := do
  let (negative, body) := match text with
    | '-' :: rest => (true, rest)
    | '+' :: rest => (false, rest)
    | rest => (false, rest)
  let (whole, rest) := body.span Char.isDigit
  let n ← digits whole
  let x : Rat ← match rest with
    | [] => some (qi n)
    | '.' :: part => (digits part).map fun f => qi n + mkRat f (10 ^ part.length)
    | '/' :: part => (digits part).bind fun d => if d == 0 then none else some (mkRat n d)
    | _ => none
  return if negative then -x else x

def strip (cs : List Char) : List Char := ((cs.dropWhile Char.isWhitespace).reverse.dropWhile Char.isWhitespace).reverse

/-- A number with commas between its thousands, as in 29,000, with the commas taken out.
None when a comma stands anywhere else. -/
def thousands (number : List Char) : Option (List Char) := do
  let (sign, body) := match number with
    | '-' :: rest => (['-'], rest)
    | '+' :: rest => (['+'], rest)
    | rest => ([], rest)
  let (whole, part) := body.span (· != '.')
  let groups := (String.ofList whole).splitOn ","
  let first ← groups.head?
  guard (groups.length > 1 && 1 ≤ first.length && first.length ≤ 3 && first.toList.all Char.isDigit)
  guard ((groups.drop 1).all fun g => g.length == 3 && g.toList.all Char.isDigit)
  guard (part.isEmpty || (digits (part.drop 1)).isSome)
  return sign ++ whole.filter (· != ',') ++ part

/-- `0.75 inch` as an exact SI value and its dimension, as `quantity` in petra/deck.py reads
it. A number alone has no dimension. A whole number and a fraction, `1 1/8 inch`, is their
sum. A comma is read only between thousands. -/
def amount (text : String) : Except String (Rat × Dim) := do
  if text.length > MAX_NUMBER_CHARS then throw s!"a quantity of {text.length} characters is over the budget of {MAX_NUMBER_CHARS}"
  let bad : Except String (Rat × Dim) := throw s!"{text} is not a quantity"
  let (head, tail) := (strip text.toList).span (· != ' ')
  let mixed : Option (List Char × List Char) := do
    let whole ← digits head
    let (top, rest) := (tail.drop 1).span Char.isDigit
    let t ← digits top
    let (bottom, unit) := (rest.drop 1).span Char.isDigit
    let b ← digits bottom
    guard (rest.head? == some '/' && b != 0 && (unit.isEmpty || unit.head? == some ' '))
    return ((toString (whole * b + t) ++ "/" ++ toString b).toList, unit)
  let (number, unit) := mixed.getD (head, tail)
  let some number := if number.contains ',' then thousands number else some number | bad
  let some x := decimal number | bad
  let unit := String.ofList (strip (unit.drop 1))
  let (factor, dim) ← (unitOf (if unit.isEmpty then "1" else unit)).mapError (s!"{text}: " ++ ·)
  return (x * factor, dim)

end Petra
