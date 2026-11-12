/-
The files of docs/format.md as structures, and the shape rule: each file is JSON with its
format, every number parses, and every range has lo <= hi. The deck of rules is in Deck.lean.
-/
import Lean.Data.Json
import Petra.Tape
import Petra.Quantity

namespace Petra
open Lean (Json)

/-- The most findings a verdict holds. The kernel counts the ones after them. -/
def MAX_FINDINGS : Nat := 100

/-- The most bytes the verdict prints of a text it did not write: the item and the reason of
a finding, and the reason of a cell. A longer text is cut. -/
def MAX_TEXT : Nat := 200

/-- The most bytes a name may print in that a cell made from a deck of rules prints whole:
the name of a part, of a load case, of a mechanism, of a field, and the id of a rule. -/
def MAX_NAME : Nat := 64

/-- The most cells the kernel makes from a deck of rules. -/
def MAX_CELLS : Nat := 10000

/-- The most steps the kernel takes to make the cells of one design from a deck of rules and
to write their tapes. A step is one name or one operator of a rule and each thing the
operator reads, each time the rule is written for a part and a load case, or one node of
a tape. Looking at a line of the grid or at a rule for a part is a step and one more for
each part of its condition, and so is each load case looked at for each load a rule reads. -/
def MAX_STEPS : Nat := 10000000

/-- The most steps reading one deck of rules takes (docs/deck.md, "The size of a deck"):
the size of its JSON, and the size of a row again for each time a rule applies it. The
kernel counts them from the file before it reads a row. -/
def MAX_READ : Nat := 1000000

/-- The most bytes the name of the card and the name of the design may print in, for a
design with parts. The label of every input of a tape holds one of them. -/
def MAX_TITLE : Nat := 200

/-- The most bytes the verdict prints of the reasons of the cells it makes from a deck of
rules. Those cells are the parts times the lines of the grid, so their reasons are not held
by the size of the files as the cells of proofs.json are. -/
def MAX_REASONS : Nat := 500000

/-- What a cell says in place of its reason once the reasons before it took `MAX_REASONS`. -/
def UNSAID : String := "past what the verdict prints of reasons"

/-- The bytes the verdict prints for a text, between its quotes. -/
def printed (s : String) : Nat := (Json.str s).compress.utf8ByteSize - 2

/-- The text when it prints in at most `MAX_TEXT` bytes. Otherwise its longest start that
does, and how many characters were left out. -/
def clip (s : String) : String :=
  if printed s ≤ MAX_TEXT then s else
    let kept := (s.foldl (fun (kept, room) c =>
      if room == 0 then (kept, 0) else
        let size := printed (String.singleton c)
        if size ≤ room then (kept.push c, room - size) else (kept, 0)) ("", MAX_TEXT)).1
    kept ++ s!"... ({s.length - kept.length} more characters)"

/-- Refuses a name that a cell would print in more than `MAX_NAME` bytes. -/
def short (what name : String) : Except String Unit :=
  if printed name ≤ MAX_NAME then pure ()
  else throw s!"{what} prints in at most {MAX_NAME} bytes, and this one in {printed name}: {clip name}"

/-- A broken rule: the rule, the file, the item of the file, and what is wrong with it. -/
structure Finding where
  rule : String
  file : String
  item : String
  why : String

/-- The first `MAX_FINDINGS` findings, each with its item and its reason cut to `MAX_TEXT`,
and how many more there were. So what the kernel holds and prints of the findings does not
grow with the files. -/
structure Findings where
  kept : Array Finding := #[]
  more : Nat := 0

def Findings.push (found : Findings) (f : Finding) : Findings :=
  if found.kept.size < MAX_FINDINGS then { found with kept := found.kept.push { f with item := clip f.item, why := clip f.why } }
  else { found with more := found.more + 1 }

def Findings.isEmpty (found : Findings) : Bool := found.kept.isEmpty

structure Input where
  name : String
  dim : String
  range : Iv
  signer : String
  caseName : Option String
  /-- For a load on a part of a deck's type: the part, and which of its type's loads it is. -/
  on : Option String
  field : Option String

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

/-- What a card states of a part exactly, with no range: the name of a key, or a whole number. -/
inductive Said where
  | key (name : String)
  | whole (n : Rat)

/-- One exact statement of the card: the name `PART.FIELD` of what it states, what it says
of it, and who signed it. A design reads it with a given of that name, as it reads a bound. -/
structure Stated where
  name : String
  said : Said
  signer : String

structure Card where
  name : String
  environment : Option String
  caseNames : Array String
  inputs : Array Input
  claims : Array Claim
  waivers : Array Waiver
  /-- Which of `tests` and `probability_claims` the card states. A deck of rules reads neither. -/
  stated : Array String
  /-- Which of `tests`, `probability_claims` and `states` the card has as a key, stated or
  empty. Only the card of a design checked against a deck of rules has them. -/
  keyed : Array String
  /-- The keys and the whole numbers the card states: its `states`, or none without the key. -/
  states : Array Stated := #[]

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

/-- One argument of a line of a part: a written number, the name of a bound the card gives,
a bare word or a quoted text. The rules deck says what the line's field makes of it. -/
inductive Arg where
  | number (dim : String) (range : Iv)
  | given (name : String)
  | word (word : String)
  | text (text : String)

structure Line where
  field : String
  args : Array Arg

/-- A part as the design writes it: its name, its type and its lines in order. -/
structure Block where
  name : String
  kind : String
  lines : Array Line

structure Design where
  keys : Array String
  name : String
  card : String
  quantities : Array Quantity
  params : Array Param
  parts : Option (Array Block)

structure Floor where
  min : Rat
  strict : Bool

def Floor.admits (f : Floor) (x : Rat) : Bool := if f.strict then f.min < x else f.min ≤ x

def Floor.broken (f : Floor) (what : String) (x : Rat) : String :=
  let relation := if f.strict then "above" else "at least"
  s!"a {what} is {relation} {f.min}, and this one goes down to {x}"

structure Constant where
  label : String
  range : Iv

structure Deck where
  size : Floor
  /-- The floor of each dimension that has one, found by the dimension's exponents
  (`Dim.key`), with the name deck.json gives it. The table is kept in the order of the
  exponents themselves, which a file writes as whole numbers of any length. -/
  input : Std.TreeMap (Array (Int × Nat)) (String × Floor)
  constants : Array Constant
  /-- Whether deck.json has `rules`, the name and the hash of a deck of rules. The exporter
  writes it for a design checked against one, and the kernel reads only that it is there. -/
  rules : Bool

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

/-- A partition that names each input it splits by its label. -/
inductive Split where
  | leaf
  | split (label : String) (cut : Rat) (below above : Split)

/-- What proofs.json says of a cell the kernel works out from a deck of rules: the state it
claims, and a partition or a point to try. The kernel trusts neither. -/
structure Hint where
  subject : String
  mechanism : String
  entry : String
  state : State
  partition : Option Split
  point : Option (Array (String × Rat))

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
           caseName := ← maybe j "case" (·.getStr?), on := ← maybe j "on" (·.getStr?),
           field := ← maybe j "field" (·.getStr?) }

def readClaim (j : Json) : Except String Claim := do
  let bound ← j.getObjVal? "bound"
  return { name := ← text j "name", subject := ← text j "subject", quantity := ← text j "quantity",
           rel := ← text j "rel", caseNames := ← texts j "cases", dim := ← text bound "dim",
           bound := ← range bound }

/-- An exact statement of the card: `name`, `by`, and one of `key`, the name of a key, and
`whole`, a whole number. It has no other key, and a `whole` that is no whole number is not
read. A statement with no `by` still reads, with an empty signer: naming one is a type rule. -/
def readStated (j : Json) : Except String Stated := do
  for (key, _) in (← j.getObj?).toArray do
    unless ["name", "by", "key", "whole"].contains key do throw s!"a statement has name, by and one of key and whole, and no {key}"
  let name ← text j "name"
  let signer := (text j "by").toOption.getD ""
  match j.getObjVal? "key", j.getObjVal? "whole" with
  | .ok (.str key), .error _ => return { name, said := .key key, signer }
  | .error _, .ok (.str _) =>
    let n ← number j "whole"
    unless n.den == 1 do throw "whole is not a whole number"
    return { name, said := .whole n, signer }
  | _, _ => throw "a statement has one of key, a text, and whole, a whole number as a text"

/-- A waiver with no `by` still reads, with an empty signer: naming one is a type rule. -/
def readWaiver (j : Json) : Except String Waiver := do
  return { subject := ← text j "subject", mechanism := ← text j "mechanism",
           signer := (text j "by").toOption.getD "", reason := ← text j "reason" }

def readQuantity (j : Json) : Except String Quantity := do
  let role ← text j "role"
  unless role == "size" || role == "position" do throw s!"role {role} is not size or position"
  return { kind := ← text j "type", entity := ← text j "entity", line := ← text j "line",
           field := ← text j "field", role, dim := ← text j "dim", range := ← range j }

def readArg (j : Json) : Except String Arg := do
  match (← j.getObj?).toArray.toList with
  | [("number", n)] => return .number (← text n "dim") (← range n)
  | [("given", .str name)] => return .given name
  | [("word", .str word)] => return .word word
  | [("text", .str quoted)] => return .text quoted
  | _ => throw "not a number, a given, a word or a text"

def readBlock (j : Json) : Except String Block := do
  let line (l : Json) : Except String Line := do
    return { field := ← text l "field", args := ← numbered "arg" readArg (← list l "args") }
  let name ← text j "name"
  short "the name of a part" name
  return { name, kind := ← text j "type", lines := ← numbered "line" line (← list j "lines") }

def readParam (j : Json) : Except String Param := do
  return { name := ← text j "name", dim := ← text j "dim", range := ← range j }

def readFloor (j : Json) : Except String Floor := do
  match j.getObjVal? "strict" with
  | .ok (.bool strict) => return { min := ← number j "min", strict }
  | _ => throw "strict is not true or false"

def readConstant (j : Json) : Except String Constant := do
  return { label := ← text j "label", range := ← range j }

/-- A condition of a pick that nests at most `depth` deep. -/
def readCond : Nat → Json → Except String Cond
  | 0, _ => throw s!"a condition nests deeper than {MAX_COND_DEPTH}"
  | depth + 1, j => do
    let members (name : String) (a : Array Json) : Except String (Array Cond) :=
      if a.isEmpty then throw s!"{name} of no conditions" else a.mapM (readCond depth)
    match (← j.getArr?).toList with
    | [.str "le", i, k] => return .le (← i.getNat?) (← k.getNat?)
    | [.str "lt", i, k] => return .lt (← i.getNat?) (← k.getNat?)
    | [.str "and", .arr a] => return .and (← members "and" a)
    | [.str "or", .arr a] => return .or (← members "or" a)
    | [.str "not", c] => return .not (← readCond depth c)
    | _ => throw "not a condition of this format"

/-- The cases of a pick: at least one, each a condition and a node, where only the last may
have null for its condition. Their conditions hold at most `MAX_ORDERS` orders between them. -/
def readCases (cases : Array Json) : Except String (Array (Option Cond × Nat)) := do
  if cases.isEmpty then throw "a pick of no cases"
  let found ← cases.mapIdxM fun n case => do
    let [cond, value] := (← case.getArr?).toList | throw "a case of a pick is not a condition and a node"
    if cond.isNull then
      unless n + 1 == cases.size do throw "null is the condition of a case that is not the last"
      return (none, ← value.getNat?)
    return (some (← readCond MAX_COND_DEPTH cond), ← value.getNat?)
  if orders found > MAX_ORDERS then throw s!"the conditions of a pick hold {orders found} orders, over the budget of {MAX_ORDERS}"
  return found

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
  | [.str "cos", i] => return .cos (← i.getNat?)
  | [.str "div", i, k] => return .div (← i.getNat?) (← k.getNat?)
  | [.str "pow", i, n] =>
    let n ← n.getInt?
    if n.natAbs > MAX_EXPONENT then throw s!"a pow exponent of {n} is over the budget of {MAX_EXPONENT}"
    return .pow (← i.getNat?) n
  | [.str "pick", .arr cases] => return .pick (← readCases cases)
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

/-- A partition by labels that nests at most `depth` deep. -/
def readSplit : Nat → Json → Except String Split
  | _, .str "leaf" => pure .leaf
  | 0, _ => throw "a partition nests too deep"
  | depth + 1, j => do
    return .split (← text j "input") (← number j "at")
      (← readSplit depth (← j.getObjVal? "below")) (← readSplit depth (← j.getObjVal? "above"))

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
abbrev Read := ExceptT String (StateM Findings)

/-- The value, or a shape finding that says why there is none. -/
def found (file item : String) (x : Except String α) : StateM Findings (Option α) := do
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
  let stated := #["tests", "probability_claims"].filter fun key => match j.getObjVal? key with
    | .ok (.arr a) => !a.isEmpty
    | .ok _ => true
    | .error _ => false
  let keyed := #["tests", "probability_claims", "states"].filter fun key => (j.getObjVal? key).toOption.isSome
  let states ← if keyed.contains "states" then items "card" j "states" readStated else pure #[]
  return { name := ← text j "name", environment, caseNames := ← texts j "cases",
           inputs := ← items "card" j "inputs" readInput, claims := ← items "card" j "claims" readClaim,
           waivers := ← items "card" j "waivers" readWaiver, stated, keyed, states }

def readDesign (j : Json) : Read Design := do
  let parts ← if (j.getObjVal? "parts").toOption.isSome then some <$> items "design" j "parts" readBlock else pure none
  return { keys := (← j.getObj?).keysArray, name := ← text j "name", card := ← text j "card",
           quantities := ← items "design" j "quantities" readQuantity,
           params := ← items "design" j "params" readParam, parts }

/-- Of two floors of one dimension, whether the first admits less: it is the higher, or of
two at one height the strict one. A value the tighter one admits, the other admits too. -/
def Floor.tighter (f g : Floor) : Bool := g.min < f.min || (f.min == g.min && f.strict && !g.strict)

/-- `about` in `domains.input` is prose, as petra/decks/core.json writes it, and not a
dimension. Every other key names a dimension, and its floor is kept by the dimension's
exponents: `m^1` and `length` are one dimension with one floor, the tighter of the two. So
type rule 4 finds the floor of an input however the card spells its dimension, and tests
an input against one floor, whatever the file holds. -/
def readDeck (j : Json) : Read Deck := do
  let domains ← j.getObjVal? "domains"
  let mut input : Std.TreeMap (Array (Int × Nat)) (String × Floor) := {}
  for (name, x) in (← (← domains.getObjVal? "input").getObj?).toArray do
    if name != "about" then
      let floor : Except String (Dim × Floor) := do
        let some dim := dimNamed name | throw "is not a dimension"
        return (dim, ← readFloor x)
      if let some (dim, floor) ← found "deck" s!"domains.input.{name}" floor then
        unless (input.get? dim.key).any fun held => !floor.tighter held.2 do
          input := input.insert dim.key (name, floor)
  return { size := ← readFloor (← domains.getObjVal? "size"), input,
           constants := ← items "deck" j "constants" readConstant, rules := (j.getObjVal? "rules").toOption.isSome }

def readProofs (j : Json) : Read (Array Cell) := items "proofs" j "cells" readCell

/-- The deepest a file's JSON may nest. A partition of depth `MAX_DEPTH` fits. -/
def MAX_NESTING : Nat := 128

/-- A hint has a state of the list. Its partition names inputs by label, and its point gives
a value to each label. A tape in it is not read. -/
def readHint (j : Json) : Except String Hint := do
  let name ← text j "state"
  let some state := State.all.find? (·.name == name) | throw s!"state {name} is not a state of this format"
  let value (x : String × Json) : Except String (String × Rat) := do return (x.1, ← parseRat (← x.2.getStr?))
  return { subject := ← text j "subject", mechanism := ← text j "mechanism", entry := ← text j "entry", state,
           partition := ← maybe j "partition" (readSplit MAX_NESTING),
           point := ← maybe j "point" (fun p => do (← p.getObj?).toArray.mapM value) }

def readHints (j : Json) : Read (Array Hint) := items "proofs" j "cells" readHint

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

/-- U+FFFD, the replacement character. -/
def REPLACEMENT : Char := Char.ofNat 0xFFFD

/-- Whether a text of the file, or a key of one of its objects, holds U+FFFD. The JSON reader
gives that character for an escape of half a surrogate pair, so once a file is read, a name
written with the escape of one half, with the escape of the other half, or with U+FFFD
itself is one text, and a waiver for one name would rest a cell of another. A file that
holds it is refused whole. A pair of escapes that is one character reads as that
character. The file nests at most `MAX_NESTING` deep. -/
partial def replaced : Json → Bool
  | .str s => s.contains REPLACEMENT
  | .arr items => items.any replaced
  | .obj members => members.toArray.any fun (key, value) => key.contains REPLACEMENT || replaced value
  | _ => false

/-- A file as its structure, or none with a finding when it is not JSON with its format. -/
def load (file format : String) (content : Except String ByteArray) (read : Json → Read α) :
    StateM Findings (Option α) := do
  let whole : Read α := do
    let bytes ← content
    bounded bytes
    let some source := String.fromUTF8? bytes | throw "not UTF-8"
    let j ← (Json.parse source).mapError ("not JSON: " ++ ·)
    if replaced j then
      throw "a text or a key holds U+FFFD, the replacement character, which an escape of half a surrogate pair also reads as"
    unless (text j "format").toOption == some format do throw s!"format is not {format}"
    read j
  found file "" (← whole.run)

end Petra
