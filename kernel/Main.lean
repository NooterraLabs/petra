/-
petra-verify --card card.json --design design.json --deck deck.json [--rules rules.json] [--proofs proofs.json]

Prints one JSON object, the verdict of docs/format.md with the state of each cell, and
exits 0 for PASS, 1 for FAIL, 2 for UNKNOWN and 3 for ILL-FORMED. `cells_from` says whether
the cells are the kernel's own, made from the deck of rules, or the list of proofs.json. A command line it cannot
read prints the usage and exits 64.
-/
import Petra.Check

open Petra

/-- A text as the verdict prints it: no character that a terminal acts on is printed raw
(`Petra.quote`). -/
def str (s : String) : String := quote s

def object (fields : List (String × String)) : String :=
  "{" ++ ", ".intercalate (fields.map fun (key, value) => s!"{str key}: {value}") ++ "}"

def rows (items : Array String) : String :=
  if items.isEmpty then "[]" else "[\n  " ++ ",\n  ".intercalate items.toList ++ "\n ]"

def render (r : Report) : String :=
  let finding (f : Finding) : String :=
    object [("rule", str f.rule), ("file", str f.file), ("item", str f.item), ("why", str f.why)]
  let waived (w : Waiver) : String :=
    object [("subject", str w.subject), ("mechanism", str w.mechanism), ("by", str w.signer), ("reason", str w.reason)]
  -- Each waiver once, in the order the cells first rest on it: many cells may rest on one.
  let waivers : Array Waiver := ((r.cells.filterMap (·.waiver)).foldl (fun (seen, out) (k, w) =>
    if seen.contains k then (seen, out) else (seen.insert k, out.push w)) (({} : Std.TreeSet Nat), #[])).2
  -- What a waived cell was completed with, as proofs.json writes a completion, with the unit
  -- of each load's value after it: degC for a temperature, and no kelvin. The waiver's signer
  -- answers for what is left out being so.
  let inline (items : Array String) : String := "[" ++ ", ".intercalate items.toList ++ "]"
  let completion (c : Completion) : String :=
    object [("keys", inline (c.keys.map fun (p, f, n) => inline #[str p, str f, str n])),
            ("loads", inline (c.loads.map fun (p, l, u, x) => inline #[str p, str l, str u, str (toString x), str (r.units.getD (p, l) "")]))]
  let cell (s : Settled) : String :=
    object ([("subject", str s.cell.subject), ("mechanism", str s.cell.mechanism), ("entry", str s.cell.entry),
             ("claimed", if s.hinted then str s.cell.state.name else "null"), ("state", str s.state.name)]
            ++ (if s.reason.isEmpty then [] else [("reason", str s.reason)])
            ++ match s.state, s.completion with
              | .waived, some c => [("completion", completion c)]
              | _, _ => [])
  let count (state : State) : String × String := (state.name, toString (r.cells.filter (·.state == state)).size)
  let fields : List (String × String) := [
    ("verdict", str r.verdict.name),
    ("hashes", object (r.hashes.map fun (file, hash) => (file, hash.elim "null" str))),
    ("cells_from", str r.cellsFrom),
    ("findings", rows (r.findings.kept.map finding)),
    ("more_findings", toString r.findings.more),
    ("counts", object (State.all.toList.map count)),
    ("dsg_inputs", toString r.dsgInputs),
    ("work", toString r.work)]
    ++ (r.ignored.map fun n => ("ignored_hints", toString n)).toList ++ [
    ("waived", rows (waivers.map waived)),
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
