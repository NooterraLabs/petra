/-
The rules of docs/format.md in its order, and the verdict.
-/
import Std.Data.HashSet
import Petra.Files
import Petra.Sha256

namespace Petra

def Floor.admits (f : Floor) (x : Rat) : Bool := if f.strict then f.min < x else f.min ≤ x

def Floor.broken (f : Floor) (what : String) (x : Rat) : String :=
  let relation := if f.strict then "above" else "at least"
  s!"a {what} is {relation} {f.min}, and this one goes down to {x}"

/-- The type rules, 1 to 5. -/
def types (cardHash : String) (card : Card) (design : Design) (deck : Deck) : Array Finding := Id.run do
  let mut out : Array Finding := #[]
  if design.card != cardHash then
    out := out.push ⟨"types.1", "design", "card", s!"is not the hash of the card file, {cardHash}"⟩
  for key in design.keys do
    unless ["format", "name", "card", "quantities", "params"].contains key do
      out := out.push ⟨"types.2", "design", key, "a design has no such key"⟩
  for q in design.quantities do
    if q.role == "size" && !deck.size.admits q.range.lo then
      out := out.push ⟨"types.3", "design", s!"{q.entity}.{q.line}.{q.field}", deck.size.broken "size" q.range.lo⟩
  for i in card.inputs do
    for (dim, floor) in deck.input do
      if dim == i.dim && !floor.admits i.range.lo then
        out := out.push ⟨"types.4", "card", i.name, floor.broken dim i.range.lo⟩
  for w in card.waivers do
    if w.signer.isEmpty then
      out := out.push ⟨"types.5", "card", s!"{w.subject}/{w.mechanism}", "the waiver names no by"⟩
  return out

/-- What the card or the deck signs for a tape's input. A `dsg:` input has no signed range:
the kernel does not tie it to the design yet. -/
def signed (card : Card) (deck : Deck) (label : String) : Except String (Array Iv) :=
  let among (ranges : Array Iv) (file : String) : Except String (Array Iv) :=
    if ranges.isEmpty then throw s!"the {file} has no {label}" else pure ranges
  if label.startsWith "in:" then
    among ((card.inputs.filter fun i => s!"in:{card.name}.{i.name}" == label).map (·.range)) "card"
  else if label.startsWith "reg:" then
    among ((deck.constants.filter (·.label == label)).map (·.range)) "deck"
  else if label.startsWith "dsg:" then pure #[]
  else throw s!"input {label} is not labelled in:, reg: or dsg:"

/-- The test on labels: every `in:` input is the card's, every `reg:` input is the deck's,
and the tape's range contains theirs. Gives the signed ranges of each input. -/
def premises (card : Card) (deck : Deck) (tape : Tape) : Except String (Array (Array Iv)) :=
  tape.inputs.mapM fun input => do
    let ranges ← signed card deck input.label
    unless ranges.all (·.within input.range) do
      throw s!"the tape's range for {input.label} does not contain the signed one"
    return ranges

/-- A cell, the state the kernel settles on, and the test that failed when that is not the
state the file claims. -/
structure Settled where
  cell : Cell
  state : State
  reason : String := ""
  waiver : Option Waiver := none

/-- The cell rules, 1 to 5. A refuting point must also lie in the signed ranges and give
one value to each label: a point outside what the card signs, or one that sets an input to
two values at once, says nothing about the design. -/
def settle (card : Card) (deck : Deck) (cell : Cell) : StateM Caches Settled := do
  let test (proof : M Unit) : StateM Caches Settled := do
    match proof.run (← get) with
    | .ok (_, caches) =>
      set caches
      return { cell, state := cell.state }
    | .error reason => return { cell, state := .undecided, reason }
  match cell.state, cell.tape with
  | .proved, some tape => test do
    let _ ← premises card deck tape
    let some partition := cell.partition | throw "a proved cell with a tape has no partition"
    tape.proved partition
  | .refuted, some tape => test do
    let ranges ← premises card deck tape
    let some point := cell.point | throw "a refuted cell with a tape has no point"
    let some which := cell.which | throw "a refuted cell with a tape has no which"
    tape.refuted point which
    for ((x, among), i) in (point.zip ranges).zipIdx do
      unless among.all (·.has x) do throw s!"the point is outside the signed range of input {i}"
    let valued := (tape.inputs.map (·.label)).zip point
    unless valued.all (fun (l, x) => valued.all fun (m, y) => l != m || x == y) do
      throw "the point gives two values to one label"
  | .proved, none | .refuted, none =>
    return { cell, state := .undecided, reason := "the kernel has no rule yet for a proof with no tape" }
  | .waived, _ =>
    match card.waivers.find? fun w => w.subject == cell.subject && w.mechanism == cell.mechanism with
    | some waiver => return { cell, state := .waived, waiver }
    | none => return { cell, state := .undecided, reason := "the card lists no waiver with this subject and mechanism" }
  | state, _ => return { cell, state }

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
  findings : Array Finding
  cells : Array Settled

/-- The `dsg:` inputs the settled proofs read. The kernel takes their ranges as stated. -/
def Report.dsgInputs (r : Report) : Nat :=
  let labels : Std.HashSet String := r.cells.foldl (init := {}) fun seen s =>
    match s.state, s.cell.tape with
    | .proved, some tape | .refuted, some tape =>
      tape.inputs.foldl (fun seen i => if i.label.startsWith "dsg:" then seen.insert i.label else seen) seen
    | _, _ => seen
  labels.size

/-- Shape, then types, then the cells. A broken rule of the first two groups is a finding,
and with a finding the kernel settles no cell. -/
def rules (cardHash : String) (card design deck : Except String ByteArray)
    (proofs : Option (Except String ByteArray)) : StateM (Array Finding) (Array Settled) := do
  let card? ← load "card" "petra-card/0" card readCard
  let design? ← load "design" "petra-design/0" design readDesign
  let deck? ← load "deck" "petra-deck/0" deck readDeck
  let cells? ← match proofs with
    | some bytes => load "proofs" "petra-proofs/0" bytes readProofs
    | none => pure none
  let (some card, some design, some deck) := (card?, design?, deck?) | return #[]
  modify (· ++ types cardHash card design deck)
  if !(← get).isEmpty then return #[]
  return Id.run (((cells?.getD #[]).mapM (settle card deck)).run' {})

/-- ILL-FORMED with a finding, FAIL with a refuted cell, PASS when every cell is proved,
waived or not applicable and one is proved, and UNKNOWN otherwise: with an open cell, or
with nothing proved. -/
def check (card design deck : Except String ByteArray) (proofs : Option (Except String ByteArray)) : Report :=
  let hash (bytes : Except String ByteArray) : Option String := bytes.toOption.map fun b => "sha256:" ++ sha256 b
  let (cells, findings) := Id.run ((rules ((hash card).getD "") card design deck proofs).run #[])
  let has (state : State) : Bool := cells.any (·.state == state)
  let verdict :=
    if !findings.isEmpty then .illFormed
    else if has .refuted then .fail
    else if has .undecided || !has .proved then .unknown
    else .pass
  { verdict, hashes := [("card", hash card), ("design", hash design), ("deck", hash deck)], findings, cells }

end Petra
