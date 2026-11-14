/-
Reading a certificate. Every number is exact: a JSON whole number, or a string "p" or "p/q"
of decimal digits with an optional sign. A JSON number with a decimal point or an exponent
left over is refused, since it names a binary fraction that the file does not show.
-/
import Lean.Data.Json

open Lean (Json)

namespace Certify

/-- A reason to refuse a file, as the checker prints it after "REFUSED: ". -/
abbrev Check := Except String

def need (ok : Bool) (why : String) : Check Unit :=
  if ok then .ok () else .error why

/-- A file that cannot be read as the format is refused with this reason. -/
def notInFormat (why : String) : Check α :=
  .error s!"the file is not in the format ({why})"

def digits : List Char → Option Nat
  | [] => none
  | cs => cs.foldlM (fun n c => if c.isDigit then some (10 * n + (c.toNat - 48)) else none) 0

def ratOfChars (cs : List Char) : Option Rat :=
  let (neg, body) : Bool × List Char :=
    match cs with
    | '-' :: r => (true, r)
    | '+' :: r => (false, r)
    | r => (false, r)
  let (p, q) := body.span (· != '/')
  match q with
  | [] => (digits p).map fun n => if neg then -(n : Rat) else (n : Rat)
  | _ :: d => do
    let n ← digits p
    let d ← digits d
    if d = 0 then none else some (mkRat (if neg then -(n : Int) else (n : Int)) d)

def num (j : Json) : Check Rat :=
  match j with
  | .num n =>
    if n.exponent = 0 then .ok (n.mantissa : Rat)
    else notInFormat "a number with a decimal point is not exact; write it as \"p/q\""
  | .str s =>
    match ratOfChars s.toList with
    | some q => .ok q
    | none => notInFormat s!"'{s}' is not a number"
  | _ => notInFormat "a number is needed"

def int (j : Json) : Check Int :=
  match j with
  | .num n => if n.exponent = 0 then .ok n.mantissa else notInFormat "a whole number is needed"
  | _ => notInFormat "a whole number is needed"

def field (j : Json) (key : String) : Check Json :=
  match j with
  | .obj _ =>
    match j.getObjVal? key with
    | .ok v => .ok v
    | .error _ => notInFormat s!"no '{key}'"
  | _ => notInFormat s!"an object with '{key}' is needed"

def field? (j : Json) (key : String) : Option Json :=
  match j.getObjVal? key with
  | .ok v => some v
  | .error _ => none

def list (j : Json) : Check (List Json) :=
  match j with
  | .arr a => .ok a.toList
  | _ => notInFormat "a list is needed"

def text (j : Json) : Check String :=
  match j with
  | .str s => .ok s
  | _ => notInFormat "a string is needed"

def keys (j : Json) : Check (List String) :=
  match j with
  | .obj kv => .ok (kv.foldl (fun acc k _ => k :: acc) []).reverse
  | _ => notInFormat "an object is needed"

def pair (j : Json) : Check (Rat × Rat) := do
  match ← list j with
  | [a, b] => return (← num a, ← num b)
  | _ => notInFormat "a pair of numbers is needed"

def triple (j : Json) : Check (Rat × Rat × Rat) := do
  match ← list j with
  | [a, b, c] => return (← num a, ← num b, ← num c)
  | _ => notInFormat "three numbers are needed"

/-- Run `f` on each member in order, stopping at the first refusal. -/
def collect (f : α → Check β) : List α → Check (List β)
  | [] => .ok []
  | a :: as => do
    let b ← f a
    let bs ← collect f as
    .ok (b :: bs)

/-- The same, with each member's place in the list. -/
def collectIdx (f : Nat → α → Check β) : List α → Nat → Check (List β)
  | [], _ => .ok []
  | a :: as, n => do
    let b ← f n a
    let bs ← collectIdx f as (n + 1)
    .ok (b :: bs)

/-- Every member passes `f`, tried in order. -/
def each (f : Nat → α → Check Unit) : List α → Nat → Check Unit
  | [], _ => .ok ()
  | a :: as, n => do
    f n a
    each f as (n + 1)

/-- A fraction as Python prints one: "p/q", or "p" when q is 1. -/
def fraction (q : Rat) : String :=
  if q.den = 1 then toString q.num else s!"{q.num}/{q.den}"

/-- A fraction rounded to six decimal places, half to even, as "%.6f" prints its exact value. -/
def decimal6 (q : Rat) : String :=
  let a : Rat := if q < 0 then -q else q
  let scaled := a * 1000000
  let fl : Nat := (scaled.num / scaled.den).toNat
  let rem : Rat := scaled - (fl : Rat)
  let n : Nat :=
    if rem > 1/2 then fl + 1 else if rem < 1/2 then fl else (if fl % 2 = 0 then fl else fl + 1)
  let frac := toString (n % 1000000)
  let pad := String.ofList (List.replicate (6 - frac.length) '0')
  (if q < 0 then "-" else "") ++ s!"{n / 1000000}.{pad}{frac}"

end Certify
