/-
petra-verify --card card.json --design design.json --deck deck.json [--rules rules.json] [--proofs proofs.json]

Prints one JSON object, the verdict of docs/format.md with the state of each cell, and
exits 0 for PASS, 1 for FAIL, 2 for UNKNOWN and 3 for ILL-FORMED. A command line it cannot
read prints the usage and exits 64.
-/
import Petra.Check

open Petra

def str (s : String) : String := (Lean.Json.str s).compress

def object (fields : List (String × String)) : String :=
  "{" ++ ", ".intercalate (fields.map fun (key, value) => s!"{str key}: {value}") ++ "}"

def rows (items : Array String) : String :=
  if items.isEmpty then "[]" else "[\n  " ++ ",\n  ".intercalate items.toList ++ "\n ]"

def render (r : Report) : String :=
  let finding (f : Finding) : String :=
    object [("rule", str f.rule), ("file", str f.file), ("item", str f.item), ("why", str f.why)]
  let waived (s : Settled) : Option String := s.waiver.map fun w =>
    object [("subject", str w.subject), ("mechanism", str w.mechanism), ("by", str w.signer), ("reason", str w.reason)]
  let cell (s : Settled) : String :=
    object ([("subject", str s.cell.subject), ("mechanism", str s.cell.mechanism), ("entry", str s.cell.entry),
             ("claimed", if s.hinted then str s.cell.state.name else "null"), ("state", str s.state.name)]
            ++ if s.reason.isEmpty then [] else [("reason", str s.reason)])
  let count (state : State) : String × String := (state.name, toString (r.cells.filter (·.state == state)).size)
  let fields : List (String × String) := [
    ("verdict", str r.verdict.name),
    ("hashes", object (r.hashes.map fun (file, hash) => (file, hash.elim "null" str))),
    ("findings", rows (r.findings.map finding)),
    ("counts", object (State.all.toList.map count)),
    ("dsg_inputs", toString r.dsgInputs)]
    ++ (r.ignored.map fun n => ("ignored_hints", toString n)).toList ++ [
    ("waived", rows (r.cells.filterMap waived)),
    ("cells", rows (r.cells.map cell))]
  "{" ++ ",\n ".intercalate (fields.map fun (key, value) => s!"{str key}: {value}") ++ "}"

def usage : String :=
  "usage: petra-verify --card card.json --design design.json --deck deck.json [--rules rules.json] [--proofs proofs.json]"

def flags : List String → Option (List (String × String))
  | [] => some []
  | flag :: path :: rest =>
    if ["--card", "--design", "--deck", "--rules", "--proofs"].contains flag then (flags rest).map ((flag, path) :: ·)
    else none
  | _ => none

def slurp (path : String) : IO (Except String ByteArray) := do
  try
    return .ok (← IO.FS.readBinFile path)
  catch e => return .error s!"cannot read the file: {e}"

def refuse : IO UInt32 := do
  IO.eprintln usage
  return 64

def main (args : List String) : IO UInt32 := do
  let some given := flags args | refuse
  let (some card, some design, some deck) := (given.lookup "--card", given.lookup "--design", given.lookup "--deck")
    | refuse
  let report := check (← slurp card) (← slurp design) (← slurp deck) (← (given.lookup "--rules").mapM slurp)
    (← (given.lookup "--proofs").mapM slurp)
  IO.println (render report)
  return report.verdict.exitCode
