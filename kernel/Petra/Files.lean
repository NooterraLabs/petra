/-
The four files of docs/format.md as structures, and the shape rule: each file is JSON with
its format, every number parses, and every range has lo <= hi.
-/
import Lean.Data.Json
import Petra.Tape

namespace Petra
open Lean (Json)

/-- A broken rule: the rule, the file, the item of the file, and what is wrong with it. -/
structure Finding where
  rule : String
  file : String
  item : String
  why : String

structure Input where
  name : String
  dim : String
  range : Iv
  signer : String
  caseName : Option String

structure Claim where
  name : String
  subject : String
  quantity : String
  rel : String
  caseNames : Array String
  dim : String
  bound : Iv

structure Waiver where
  subject : String
  mechanism : String
  signer : String
  reason : String

structure Card where
  name : String
  environment : Option String
  caseNames : Array String
  inputs : Array Input
  claims : Array Claim
  waivers : Array Waiver

structure Quantity where
  kind : String
  entity : String
  line : String
  field : String
  role : String
  dim : String
  range : Iv

structure Param where
  name : String
  dim : String
  range : Iv

structure Design where
  keys : Array String
  name : String
  card : String
  quantities : Array Quantity
  params : Array Param

structure Floor where
  min : Rat
  strict : Bool

structure Constant where
  label : String
  range : Iv

structure Deck where
  size : Floor
  input : Array (String × Floor)
  constants : Array Constant

/-- The state of a cell. The files write `undecided` as "open". -/
inductive State where
  | proved | refuted | notApplicable | waived | undecided
  deriving BEq

def State.name : State → String
  | .proved => "proved"
  | .refuted => "refuted"
  | .notApplicable => "not_applicable"
  | .waived => "waived"
  | .undecided => "open"

def State.all : Array State := #[.proved, .refuted, .notApplicable, .waived, .undecided]

structure Cell where
  subject : String
  mechanism : String
  entry : String
  state : State
  tape : Option Tape
  partition : Option Partition
  point : Option (Array Rat)
  which : Option Nat

def text (j : Json) (key : String) : Except String String :=
  match j.getObjVal? key with
  | .ok (.str s) => pure s
  | _ => throw s!"{key} is not a string"

def number (j : Json) (key : String) : Except String Rat := do
  (parseRat (← text j key)).mapError (s!"{key}: " ++ ·)

def range (j : Json) : Except String Iv := do
  let lo ← number j "lo"
  let hi ← number j "hi"
  if lo ≤ hi then return ⟨lo, hi⟩ else throw "lo is above hi"

def list (j : Json) (key : String) : Except String (Array Json) :=
  match j.getObjVal? key with
  | .ok (.arr a) => pure a
  | _ => throw s!"{key} is not a list"

def texts (j : Json) (key : String) : Except String (Array String) := do
  (← list j key).mapM fun
    | .str s => pure s
    | _ => throw s!"{key} holds a value that is not a string"

/-- The value of a key that an item may leave out. -/
def maybe (j : Json) (key : String) (read : Json → Except String α) : Except String (Option α) :=
  match j.getObjVal? key with
  | .ok v => some <$> (read v).mapError (s!"{key}: " ++ ·)
  | .error _ => pure none

/-- `read` on each element, with the element's place in the message of a failure. -/
def numbered (what : String) (read : Json → Except String α) (a : Array Json) : Except String (Array α) :=
  a.mapIdxM fun i x => (read x).mapError (s!"{what} {i}: " ++ ·)

def readInput (j : Json) : Except String Input := do
  return { name := ← text j "name", dim := ← text j "dim", range := ← range j, signer := ← text j "by",
           caseName := ← maybe j "case" (·.getStr?) }

def readClaim (j : Json) : Except String Claim := do
  let bound ← j.getObjVal? "bound"
  return { name := ← text j "name", subject := ← text j "subject", quantity := ← text j "quantity",
           rel := ← text j "rel", caseNames := ← texts j "cases", dim := ← text bound "dim",
           bound := ← range bound }

/-- A waiver with no `by` still reads, with an empty signer: naming one is a type rule. -/
def readWaiver (j : Json) : Except String Waiver := do
  return { subject := ← text j "subject", mechanism := ← text j "mechanism",
           signer := (text j "by").toOption.getD "", reason := ← text j "reason" }

def readQuantity (j : Json) : Except String Quantity := do
  let role ← text j "role"
  unless role == "size" || role == "position" do throw s!"role {role} is not size or position"
  return { kind := ← text j "type", entity := ← text j "entity", line := ← text j "line",
           field := ← text j "field", role, dim := ← text j "dim", range := ← range j }

def readParam (j : Json) : Except String Param := do
  return { name := ← text j "name", dim := ← text j "dim", range := ← range j }

def readFloor (j : Json) : Except String Floor := do
  match j.getObjVal? "strict" with
  | .ok (.bool strict) => return { min := ← number j "min", strict }
  | _ => throw "strict is not true or false"

def readConstant (j : Json) : Except String Constant := do
  return { label := ← text j "label", range := ← range j }

def readNode (j : Json) : Except String Node := do
  let ids (a : Array Json) : Except String (Array Nat) := a.mapM (·.getNat?)
  match (← j.getArr?).toList with
  | [.str "c", .str x] => return .c (← parseRat x)
  | [.str "s", k] => return .s (← k.getNat?)
  | [.str "pi"] => return .pi
  | [.str "add", .arr a] => return .add (← ids a)
  | [.str "mul", .arr a] => return .mul (← ids a)
  | [.str "min", .arr a] => return .min (← ids a)
  | [.str "max", .arr a] => return .max (← ids a)
  | [.str "neg", i] => return .neg (← i.getNat?)
  | [.str "abs", i] => return .abs (← i.getNat?)
  | [.str "sqrt", i] => return .sqrt (← i.getNat?)
  | [.str "ln", i] => return .ln (← i.getNat?)
  | [.str "exp", i] => return .exp (← i.getNat?)
  | [.str "div", i, k] => return .div (← i.getNat?) (← k.getNat?)
  | [.str "pow", i, n] =>
    let n ← n.getInt?
    if n.natAbs > MAX_EXPONENT then throw s!"a pow exponent of {n} is over the budget of {MAX_EXPONENT}"
    return .pow (← i.getNat?) n
  | _ => throw "not a node of this format"

def readTape (j : Json) : Except String Tape := do
  let input (i : Json) : Except String TapeInput := do return { label := ← text i "label", range := ← range i }
  return { inputs := ← numbered "input" input (← list j "inputs"),
           nodes := ← numbered "node" readNode (← list j "nodes"),
           roots := ← numbered "root" (·.getNat?) (← list j "roots") }

partial def readPartition : Json → Except String Partition
  | .str "leaf" => pure .leaf
  | j => do
    return .split (← (← j.getObjVal? "input").getNat?) (← number j "at")
      (← readPartition (← j.getObjVal? "below")) (← readPartition (← j.getObjVal? "above"))

def readCell (j : Json) : Except String Cell := do
  let name ← text j "state"
  let some state := State.all.find? (·.name == name) | throw s!"state {name} is not a state of this format"
  if state == .notApplicable || state == .undecided then
    let _ ← text j "why"
  let value (x : Json) : Except String Rat := do parseRat (← x.getStr?)
  return { subject := ← text j "subject", mechanism := ← text j "mechanism", entry := ← text j "entry", state,
           tape := ← maybe j "tape" readTape, partition := ← maybe j "partition" readPartition,
           point := ← maybe j "point" (fun p => do numbered "value" value (← p.getArr?)),
           which := ← maybe j "which" (·.getNat?) }

/-- Reads a file and keeps the shape findings. A failure of the whole file is the error. -/
abbrev Read := ExceptT String (StateM (Array Finding))

/-- The value, or a shape finding that says why there is none. -/
def found (file item : String) (x : Except String α) : StateM (Array Finding) (Option α) := do
  match x with
  | .ok y => return some y
  | .error why =>
    modify (·.push { rule := "shape", file, item, why })
    return none

/-- The items of a list that read. An item that does not is a finding and is left out, so
one bad item does not hide the next. -/
def items (file : String) (j : Json) (key : String) (read : Json → Except String α) : Read (Array α) := do
  let mut out := #[]
  for (x, i) in (← list j key).zipIdx do
    if let some y ← found file s!"{key}[{i}]" (read x) then out := out.push y
  return out

def readCard (j : Json) : Read Card := do
  let environment ← match j.getObjVal? "environment" with
    | .ok (.str s) => pure (some s)
    | .ok .null => pure none
    | _ => throw "environment is not a string or null"
  return { name := ← text j "name", environment, caseNames := ← texts j "cases",
           inputs := ← items "card" j "inputs" readInput, claims := ← items "card" j "claims" readClaim,
           waivers := ← items "card" j "waivers" readWaiver }

def readDesign (j : Json) : Read Design := do
  return { keys := (← j.getObj?).keysArray, name := ← text j "name", card := ← text j "card",
           quantities := ← items "design" j "quantities" readQuantity,
           params := ← items "design" j "params" readParam }

/-- `about` in `domains.input` is prose, as petra/decks/core.json writes it, and not a dimension. -/
def readDeck (j : Json) : Read Deck := do
  let domains ← j.getObjVal? "domains"
  let mut input := #[]
  for (dim, x) in (← (← domains.getObjVal? "input").getObj?).toArray do
    if dim != "about" then
      if let some floor ← found "deck" s!"domains.input.{dim}" (readFloor x) then input := input.push (dim, floor)
  return { size := ← readFloor (← domains.getObjVal? "size"), input,
           constants := ← items "deck" j "constants" readConstant }

def readProofs (j : Json) : Read (Array Cell) := items "proofs" j "cells" readCell

/-- The deepest a file's JSON may nest. A partition of depth `MAX_DEPTH` fits. -/
def MAX_NESTING : Nat := 128

/-- The most digits a number outside a string may have. -/
def MAX_DIGITS : Nat := 32

/-- Refuses what the JSON reader would spend unbounded stack or time on: nesting deeper than
`MAX_NESTING`, a number of more than `MAX_DIGITS` digits, and a number with a fraction or an
exponent, which the reader expands in full. The format writes none of these: its rationals
are strings. -/
def bounded (bytes : ByteArray) : Except String Unit := do
  let mut depth := 0
  let mut digits := 0
  let mut quoted := false
  let mut escaped := false
  for b in bytes do
    let c := Char.ofNat b.toNat
    if quoted then
      if escaped then escaped := false
      else if c == '\\' then escaped := true
      else if c == '"' then quoted := false
    else
      if c == '.' || (digits > 0 && (c == 'e' || c == 'E')) then
        throw "a number outside a string has a fraction or an exponent"
      digits := if c.isDigit then digits + 1 else 0
      if digits > MAX_DIGITS then throw s!"a number outside a string has more than {MAX_DIGITS} digits"
      if c == '"' then quoted := true
      else if c == '[' || c == '{' then
        depth := depth + 1
        if depth > MAX_NESTING then throw s!"nested deeper than {MAX_NESTING}"
      else if c == ']' || c == '}' then depth := depth - 1

/-- A file as its structure, or none with a finding when it is not JSON with its format. -/
def load (file format : String) (content : Except String ByteArray) (read : Json → Read α) :
    StateM (Array Finding) (Option α) := do
  let whole : Read α := do
    let bytes ← content
    bounded bytes
    let some source := String.fromUTF8? bytes | throw "not UTF-8"
    let j ← (Json.parse source).mapError ("not JSON: " ++ ·)
    unless (text j "format").toOption == some format do throw s!"format is not {format}"
    read j
  found file "" (← whole.run)

end Petra
