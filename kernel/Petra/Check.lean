/-
The rules of docs/format.md in its order, and the verdict.
-/
import Petra.Grid
import Petra.Sha256

namespace Petra

/-- What the type of a part says with `may_be` of one of its fields, or of one of its loads
when `load`: `positive` when it says nothing, and for a part or a field that the deck of
rules does not have. `kinds` holds the types of the deck by name and `typed` the type of
each part of the design by the part's name. Each look goes through two tables, so asking
it of every quantity and of every input costs the design and the card, and not their
product with the deck. -/
def signOf (kinds : Std.TreeMap String Kind) (typed : Std.TreeMap String String) (part field : String) (load : Bool) : Sign :=
  let found : Option Sign := do
    let kind ← kinds.get? (← typed.get? part)
    let f ← if load then kind.load.get? field else kind.field.get? field
    return f.sign
  found.getD .positive

/-- The part and the field that a given names, `PART.FIELD`: what stands before its last dot
and what stands after it. The name of a field holds no dot. -/
def givenOf (name : String) : String × String :=
  match (name.splitOn ".").reverse with
  | field :: rest => (".".intercalate rest.reverse, field)
  | [] => (name, "")

/-- The type rules, 1 to 5. Rules 6 and 7 are in `rules` and `marks`: they read the command line.

`sign` is what the deck of rules says with `may_be` of a field or of a load of a part
(`signOf`). A number that a design writes for a field that may be zero or negative is not
held to the floor of a size: Parts 3 holds it to its field's own. An input for a field or
a load that may be negative is not held to a floor of its dimension that is at zero or
above, and is still held to one under zero, as the floor of a temperature is. -/
def types (cardHash : String) (card : Card) (design : Design) (deck : Deck)
    (sign : String → String → Bool → Sign := fun _ _ _ => .positive) : StateM Findings Unit := do
  let say (rule file item why : String) : StateM Findings Unit := modify (·.push ⟨rule, file, item, why⟩)
  if design.card != cardHash then
    say "types.1" "design" "card" s!"is not the hash of the card file, {cardHash}"
  for key in design.keys do
    unless ["format", "name", "card", "quantities", "params", "parts"].contains key do
      say "types.2" "design" key "a design has no such key"
  for q in design.quantities do
    if q.role == "size" && !deck.size.admits q.range.lo && sign q.entity q.line false == .positive then
      say "types.3" "design" s!"{q.entity}.{q.line}.{q.field}" (deck.size.broken "size" q.range.lo)
  for i in card.inputs do
    match dimNamed i.dim with
    | none => say "types.4" "card" i.name s!"{i.dim} is not a dimension"
    | some dim =>
      if let some (name, floor) := deck.input.get? dim.key then
        if !floor.admits i.range.lo then
          let its := match i.on, i.field with
            | some part, some field => sign part field true
            | _, _ => let (part, field) := givenOf i.name; sign part field false
          unless its == .negative && floor.min ≥ 0 do say "types.4" "card" i.name (floor.broken name i.range.lo)
    if i.signer.isEmpty then say "types.5" "card" i.name "the input names no by"
  for s in card.states do
    if s.signer.isEmpty then say "types.5" "card" s.name "the statement names no by"
  for w in card.waivers do
    if w.signer.isEmpty then
      say "types.5" "card" s!"{w.subject}/{w.mechanism}" "the waiver names no by"

/-- Type rule 7. What only the files of a design checked against a deck of rules have: an
input of the card that puts a load on a part, the keys `tests` and `probability_claims` of
the card, and `rules` in deck.json. Each is a finding when the design has no parts or
`--rules` names no deck. Without this a card that was issued for a deck of rules would be
checked with the cells that proofs.json lists, which the kernel takes as they come. -/
def marks (card : Card) (design : Design) (deck : Deck) (deckOfRules : Bool) : StateM Findings Unit := do
  let lacks := " and ".intercalate ((if design.parts.isNone then ["the design has no parts"] else [])
    ++ (if deckOfRules then [] else ["--rules names none"]))
  if lacks.isEmpty then return
  let say (file item what : String) : StateM Findings Unit :=
    modify (·.push ⟨"types.7", file, item, s!"{what}, which only a design checked against a deck of rules has, and {lacks}"⟩)
  for i in card.inputs do
    if i.on.isSome || i.field.isSome then say "card" i.name "is a load on a part"
  for key in card.keyed do say "card" key "is a key of the card"
  if deck.rules then say "deck" "rules" "names a deck of rules"

/-- What the ranges signed under one name ask between them. A range contains every one of
them when it contains `hull`, the least range that holds them all, and a point lies in
every one when it lies in `core`, what they have in common, which may hold no number. So a
name the card gives many times costs an input of a tape one test, and not one for each. -/
structure Bounds where
  hull : Iv
  core : Iv

def Bounds.of (ranges : Array Iv) : Option Bounds :=
  ranges[0]?.map fun first => ranges.foldl (init := ⟨first, first⟩) fun b r =>
    ⟨⟨rmin b.hull.lo r.lo, rmax b.hull.hi r.hi⟩, ⟨rmax b.core.lo r.lo, rmin b.core.hi r.hi⟩⟩

/-- What the card and the deck sign, found by name: what the ranges of the card's inputs of
each name ask, the label every one of them starts with, what the ranges of the deck's
constants of each label ask, and the first waiver of each subject and mechanism with its
place in the card's list. So the tests on a cell cost what the cell holds, and not that
times the card. -/
structure Signed where
  lead : String
  inputs : Std.TreeMap String Bounds
  constants : Std.TreeMap String Bounds
  waivers : Std.TreeMap (String × String) (Waiver × Nat)

def Signed.of (card : Card) (deck : Deck) : Signed :=
  { lead := s!"in:{card.name}.",
    inputs := (grouped card.inputs (·.name)).filterMap fun _ found => Bounds.of (found.map (·.range)),
    constants := (grouped deck.constants (·.label)).filterMap fun _ found => Bounds.of (found.map (·.range)),
    waivers := firsts card.waivers.zipIdx fun w => (w.1.subject, w.1.mechanism) }

/-- What the card or the deck signs for a tape's input: the ranges of the card's inputs
named `INPUT` for the label `in:CARD.INPUT`, and of the deck's constants of a `reg:` label.
A `dsg:` input has no signed range: the kernel does not tie it to the design yet. -/
def Signed.ranges (signed : Signed) (label : String) : Except String (Option Bounds) :=
  let among (ranges : Option Bounds) (file : String) : Except String (Option Bounds) :=
    match ranges with
    | some ranges => pure (some ranges)
    | none => throw s!"the {file} has no {label}"
  if label.startsWith "in:" then
    among (if label.startsWith signed.lead then signed.inputs.get? (String.ofList (label.toList.drop signed.lead.length)) else none) "card"
  else if label.startsWith "reg:" then among (signed.constants.get? label) "deck"
  else if label.startsWith "dsg:" then pure none
  else throw s!"input {label} is not labelled in:, reg: or dsg:"

/-- The test on labels: every `in:` input is the card's, every `reg:` input is the deck's,
and the tape's range contains theirs. Gives what is signed for each input. -/
def premises (signed : Signed) (tape : Tape) : Except String (Array (Option Bounds)) :=
  tape.inputs.mapM fun input => do
    let ranges ← signed.ranges input.label
    unless ranges.all (·.hull.within input.range) do
      throw s!"the tape's range for {input.label} does not contain the signed one"
    return ranges

/-- The cell rules, 1 to 5. A refuting point must also lie in the signed ranges and give
one value to each label: a point outside what the card signs, or one that sets an input to
two values at once, says nothing about the design. `left` is the work the proofs before this
one left of `MAX_WORK`, and the result holds what this one leaves. A proof that cannot pay
for its tape is not tried, a step that cannot pay is not taken, and either way the cell is
open. The caches keep what a proof that holds computed. -/
def settle (signed : Signed) (cell : Cell) (left : Nat) : StateM Caches (Settled × Nat) := do
  let undecided (reason : String) (left : Nat) : Settled × Nat := ({ cell, state := .undecided, reason := clip reason }, left)
  let test (ready : Except String (Nat → M (Option String × Nat))) : StateM Caches (Settled × Nat) := do
    match ready with
    | .error reason => return undecided reason left
    | .ok proof =>
      match (proof left).run (← get) with
      | .ok ((none, left), caches) =>
        set caches
        return ({ cell, state := cell.state }, left)
      | .ok ((some reason, left), _) => return undecided reason left
      | .error reason => return undecided reason left
  match cell.state, cell.tape with
  | .proved, some tape => test do
    let _ ← premises signed tape
    let some partition := cell.partition | throw "a proved cell with a tape has no partition"
    return tape.proved partition
  | .refuted, some tape => test do
    let ranges ← premises signed tape
    let some point := cell.point | throw "a refuted cell with a tape has no point"
    let some which := cell.which | throw "a refuted cell with a tape has no which"
    return fun left => do
      let (why, left) ← tape.refuted point which left
      if why.isSome then return (why, left)
      if let some i := (point.zip ranges).findIdx? fun (x, among) => !among.all (·.core.has x) then
        return (some s!"the point is outside the signed range of input {i}", left)
      let (_, twice) := (tape.inputs.zip point).foldl (init := (({} : Std.TreeMap String Rat), false)) fun (seen, twice) (input, x) =>
        match seen.get? input.label with
        | some y => (seen, twice || x != y)
        | none => (seen.insert input.label x, twice)
      return (if twice then some "the point gives two values to one label" else none, left)
  | .proved, none | .refuted, none =>
    return undecided "the kernel has no rule yet for a proof with no tape" left
  | .waived, _ =>
    match signed.waivers.get? (cell.subject, cell.mechanism) with
    | some (w, k) => return ({ cell, state := .waived, waiver := some (k, w) }, left)
    | none => return undecided "the card lists no waiver with this subject and mechanism" left
  | state, _ => return ({ cell, state }, left)

inductive Verdict where
  | pass | fail | unknown | illFormed

def Verdict.name : Verdict → String
  | .pass => "PASS"
  | .fail => "FAIL"
  | .unknown => "UNKNOWN"
  | .illFormed => "ILL-FORMED"

def Verdict.exitCode : Verdict → UInt32
  | .pass => 0
  | .fail => 1
  | .unknown => 2
  | .illFormed => 3

structure Report where
  verdict : Verdict
  hashes : List (String × Option String)
  findings : Findings
  cells : Array Settled
  /-- Where the cells came from: `rules` when `--rules` named a deck and the kernel made them
  from it, and `proofs` when it took the list that proofs.json holds. -/
  cellsFrom : String
  /-- With a deck of rules: how many hints of proofs.json name no cell the kernel has. -/
  ignored : Option Nat
  /-- How many distinct `dsg:` inputs the settled proofs read. With a deck of rules they are
  the numbers the design's parts write. Without one the kernel takes their ranges as the
  tape states them. -/
  dsgInputs : Nat
  /-- The work the proofs took, of `MAX_WORK`. -/
  work : Nat

/-- The distinct `dsg:` inputs that the tapes of the proved and the refuted cells read. -/
def dsgInputs (cells : Array Settled) : Nat :=
  let labels : Std.TreeSet String := cells.foldl (init := {}) fun seen s =>
    match s.state, s.cell.tape with
    | .proved, some tape | .refuted, some tape =>
      tape.inputs.foldl (fun seen i => if i.label.startsWith "dsg:" then seen.insert i.label else seen) seen
    | _, _ => seen
  labels.size

/-- The cells, and for cells made from a deck of rules what `Made` adds to them. -/
structure Found where
  cells : Array Settled := #[]
  ignored : Option Nat := none
  dsgInputs : Nat := 0
  work : Nat := 0

/-- Shape, then types, then the deck of rules and the parts when `--rules` names a deck,
then the cells. A broken rule of a group before the cells is a finding, and with a finding
the kernel settles no cell. With a deck of rules the cells are the ones the kernel works out
from it, and proofs.json holds hints. Without one the cells are the ones proofs.json lists. -/
def rules (cardHash : String) (card design deck : Except String ByteArray)
    (deckOfRules proofs : Option (Except String ByteArray)) : StateM Findings Found := do
  let card? ← load "card" "petra-card/0" card readCard
  let design? ← load "design" "petra-design/0" design readDesign
  let deck? ← load "deck" "petra-deck/0" deck readDeck
  let rules? ← match deckOfRules with
    | some bytes => load "rules" "petra-rules/0" bytes fun j => do return ← readRules j
    | none => pure none
  let cells? ← match proofs, deckOfRules with
    | some bytes, none => load "proofs" "petra-proofs/0" bytes readProofs
    | _, _ => pure none
  let hints? ← match proofs, deckOfRules with
    | some bytes, some _ => load "proofs" "petra-proofs/0" bytes readHints
    | _, _ => pure none
  let (some card, some design, some deck) := (card?, design?, deck?) | return {}
  -- What the deck of rules says with `may_be` of the fields and the loads of the design's parts.
  let sign : String → String → Bool → Sign := match rules?, design.parts with
    | some rules, some blocks =>
      signOf (firsts rules.kinds (·.name)) (blocks.foldl (fun table b => table.insertIfNew b.name b.kind) {})
    | _, _ => fun _ _ _ => .positive
  types cardHash card design deck sign
  if design.parts.isSome && deckOfRules.isNone then
    modify (·.push ⟨"types.6", "design", "parts", "a design with parts is checked against a deck of rules, and --rules names none"⟩)
  marks card design deck deckOfRules.isSome
  let (parts, loads) ← match rules? with
    | some rules => readParts rules card design deck.input
    | none => pure (#[], {})
  -- What the types need of their fields is asked last, of a design that breaks no rule
  -- before it, and what deciding it takes comes off the work of the verdict.
  let left ← if (← get).isEmpty then needs parts else pure MAX_WORK
  if !(← get).isEmpty then return {}
  let some rules := rules? |
    let signed := Signed.of card deck
    let settled : StateM Caches (Array Settled × Nat) := (cells?.getD #[]).foldlM (init := (#[], MAX_WORK)) fun (out, left) cell => do
      let (found, left) ← settle signed cell left
      return (out.push found, left)
    let (cells, left) := Id.run (settled.run' {})
    return { cells, dsgInputs := dsgInputs cells, work := MAX_WORK - left }
  match Id.run ((cells rules card parts loads (hints?.getD #[]) left).run' {}) with
  | .ok made => return { cells := made.cells, ignored := some made.ignored, dsgInputs := made.dsgInputs, work := made.work }
  | .error why =>
    modify (·.push ⟨"limits", "design", "parts", why⟩)
    return {}

/-- ILL-FORMED with a finding, FAIL with a refuted cell, PASS when every cell is proved,
waived or not applicable and one is proved, and UNKNOWN otherwise: with an open cell, or
with nothing proved. -/
def check (card design deck : Except String ByteArray) (deckOfRules proofs : Option (Except String ByteArray)) : Report :=
  let hash (bytes : Except String ByteArray) : Option String := bytes.toOption.map fun b => "sha256:" ++ sha256 b
  let (found, findings) := Id.run ((rules ((hash card).getD "") card design deck deckOfRules proofs).run {})
  let cells := found.cells
  let has (state : State) : Bool := cells.any (·.state == state)
  let verdict :=
    if !findings.isEmpty then .illFormed
    else if has .refuted then .fail
    else if has .undecided || !has .proved then .unknown
    else .pass
  let hashes := [("card", hash card), ("design", hash design), ("deck", hash deck), ("rules", deckOfRules.bind hash)]
  { verdict, hashes, findings, cells, cellsFrom := if deckOfRules.isSome then "rules" else "proofs",
    ignored := found.ignored, dsgInputs := found.dsgInputs, work := found.work }

end Petra
