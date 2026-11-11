/-
A design against a deck of rules: its parts, and one cell for each answer the grid asks,
as `read_parts`, `cells`, `_answers` and `_unread` in petra/grid.py work them out. The cells
are the kernel's own. proofs.json gives only hints: a partition or a point to try.

Everything here that is found by name is found through a table, so the work grows with the
files and not with their product.
-/
import Std.Data.HashMap
import Std.Data.HashSet
import Petra.Deck

namespace Petra

/-- What a part has for one field: a quantity as a tape reads it, the name of a key, or the
names of the parts it joins. -/
inductive Slot where
  | quantity (input : TapeInput)
  | key (name : String)
  | parts (names : Array String)

/-- A part of a deck's type. A load is the load's name, the load case and the card's input. -/
structure Part where
  name : String
  kind : Kind
  slots : Array (String × Slot)
  loads : Array (String × String × TapeInput)
  deriving Inhabited

def Part.slot (part : Part) (field : String) : Option Slot := (part.slots.find? (·.1 == field)).map (·.2)

/-- The name of the part that `part` joins under the name a rule calls it by. -/
def Part.joined (part : Part) (called : String) : Option String := do
  let field ← part.kind.fields.find? fun f => match f.kind with
    | .parts _ names => names.contains called
    | _ => false
  let .parts _ names := field.kind | none
  let .parts joined ← part.slot field.name | none
  joined[← names.findIdx? (· == called)]?

/-- The items under each key, in their order. -/
def grouped [BEq κ] [Hashable κ] (items : Array α) (key : α → κ) : Std.HashMap κ (Array α) :=
  items.foldl (init := {}) fun table x => table.alter (key x) fun
    | some found => some (found.push x)
    | none => some #[x]

/-- The first item under each key. -/
def firsts [BEq κ] [Hashable κ] (items : Array α) (key : α → κ) : Std.HashMap κ α :=
  items.foldl (init := {}) fun table x => if table.contains (key x) then table else table.insert (key x) x

/-- A quantity is of its field's dimension, more than zero and at least the field's least. -/
def sized (dim : Dim) (least : Option Rat) (its : String) (range : Iv) : Except (String × String) Unit := do
  unless dimNamed its == some dim do throw ("parts.3", s!"is a {its}, which is not the dimension of its field")
  if range.lo ≤ 0 then throw ("parts.3", "is not more than zero")
  if least.any (range.lo < ·) then throw ("parts.3", "is under the least its field may take")

/-- What a line gives its field, or the rule it breaks and why. `blocks` holds the blocks of
each name and `inputs` the card's inputs of each name. -/
def slotOf (card : Card) (design : Design) (blocks : Std.HashMap String (Array Block))
    (inputs : Std.HashMap String (Array Input)) (part : String) (field : Field) (args : Array Arg) :
    Except (String × String) Slot := do
  match field.kind, args.toList with
  | .parts kind names, args =>
    let named := args.filterMap fun
      | .word word => some word
      | _ => none
    unless named.length == args.length && named.length == names.size && distinct named.toArray
        && named.all (fun n => (blocks.getD n #[]).any (·.kind == kind)) do
      throw ("parts.5", s!"names {names.size} different {kind} parts of this design")
    return .parts named.toArray
  | .key names, [.word name] | .key names, [.text name] =>
    unless names.contains name do throw ("parts.4", s!"is one of: {", ".intercalate names.toList}")
    return .key name
  | .key .., _ => throw ("parts.4", "takes one name")
  | .quantity dim signed whole least, [.number its range] =>
    if signed then throw ("parts.3", "is for the card to state: the design reads it with a given")
    sized dim least its range
    if whole && (range.lo != range.hi || range.lo.den != 1) then throw ("parts.3", "is a count: one whole number")
    return .quantity ⟨s!"dsg:{design.name}.{part}.{field.name}", range⟩
  | .quantity dim _ whole least, [.given name] =>
    if whole then throw ("parts.3", "is a count, which the design writes as a whole number")
    unless name == s!"{part}.{field.name}" do
      throw ("parts.3", s!"reads the given {name}, and a part reads only the bound the card gives for it, {part}.{field.name}")
    match (inputs.getD name #[]).toList with
    | [input] =>
      if input.caseName.isSome || input.on.isSome || input.field.isSome then throw ("parts.3", s!"{name} is a load of the card")
      sized dim least input.dim input.range
      return .quantity ⟨s!"in:{card.name}.{name}", input.range⟩
    | [] => throw ("parts.3", s!"the card gives no {name}")
    | _ => throw ("parts.3", s!"the card gives {name} twice")
  | .quantity .., _ => throw ("parts.3", "is one number or one given")

/-- The parts of the design with the card's loads on them, and a finding for each rule of
the group Parts in docs/format.md that the design or the card breaks. -/
def readParts (rules : Rules) (card : Card) (design : Design) : StateM Findings (Array Part) := do
  let say (rule file item why : String) : StateM Findings Unit := modify (·.push ⟨rule, file, item, why⟩)
  let blocks := design.parts.getD #[]
  let blocksNamed := grouped blocks (·.name)
  let inputsNamed := grouped card.inputs (·.name)
  let kinds := firsts rules.kinds (·.name)
  let fieldsOf : Std.HashMap String (Std.HashMap String Field) :=
    rules.kinds.foldl (fun table kind => table.insert kind.name (firsts kind.fields (·.name))) {}
  let mut parts : Array Part := #[]
  let mut names : Std.HashSet String := {}
  for block in blocks do
    if names.contains block.name then say "parts.1" "design" block.name "two parts have this name"
    names := names.insert block.name
    match kinds.get? block.kind with
    | none => say "parts.1" "design" block.name s!"{block.kind} is not a type of the deck of rules"
    | some kind =>
      let fields := fieldsOf.getD kind.name {}
      let mut slots : Array (String × Slot) := #[]
      let mut given : Std.HashSet String := {}
      for line in block.lines do
        let item := s!"{block.name}.{line.field}"
        match fields.get? line.field with
        | none => say "parts.2" "design" item s!"is not a field of a {kind.name}"
        | some field =>
          if given.contains line.field then say "parts.2" "design" item "is given twice"
          else match slotOf card design blocksNamed inputsNamed block.name field line.args with
            | .ok slot => slots := slots.push (line.field, slot)
            | .error (rule, why) => say rule "design" item why
        given := given.insert line.field
      for field in kind.fields do
        unless given.contains field.name do say "parts.2" "design" block.name s!"lacks {field.name}"
      parts := parts.push { name := block.name, kind, slots, loads := #[] }
  let joins : Std.HashMap String Nat := parts.foldl (init := {}) fun table part => part.slots.foldl (init := table) fun table slot =>
    match slot.2 with
    | .parts names => names.foldl (fun table name => table.insert name (table.getD name 0 + 1)) table
    | _ => table
  for part in parts do
    if joins.getD part.name 0 > 1 then say "parts.5" "design" part.name "is joined more than once, and a deck has no rule yet for a part that two others load"
  let read : Std.HashSet String := blocks.foldl (init := {}) fun read block => block.lines.foldl (init := read) fun read line =>
    line.args.foldl (init := read) fun read arg => match arg with
      | .given name => read.insert name
      | _ => read
  let place : Std.HashMap String Nat := (firsts parts.zipIdx (·.1.name)).map fun _ found => found.2
  let mut put : Std.HashSet (Nat × String × String) := {}
  for input in card.inputs do
    if (inputsNamed.getD input.name #[]).size > 1 then say "parts.6" "card" input.name "two inputs have this name"
    match input.caseName, input.on, input.field with
    | none, none, none =>
      unless read.contains input.name do say "parts.6" "card" input.name "is no load, and no part reads it"
    | some under, some on, some field =>
      match place.get? on with
      | none => say "parts.6" "card" input.name s!"a load is put on a part, and {on} is not one"
      | some k =>
        match (parts[k]!.kind.loads.find? (·.name == field)).map (·.kind) with
        | some (FieldKind.quantity dim _ _ least) =>
          if dimNamed input.dim != some dim then say "parts.6" "card" input.name s!"is a {input.dim}, which is not the dimension of {field}"
          else if least.any (input.range.lo < ·) then say "parts.6" "card" input.name s!"is under the least {field} may take"
          else if put.contains (k, field, under) then say "parts.6" "card" input.name s!"{under} puts {field} on {on} twice"
          else if let .error why := short "the name of a load case" under then say "shape" "card" input.name why
          else
            put := put.insert (k, field, under)
            parts := parts.modify k fun p => { p with loads := p.loads.push (field, under, ⟨s!"in:{card.name}.{input.name}", input.range⟩) }
        | _ => say "parts.6" "card" input.name s!"a {parts[k]!.kind.name} takes no load {field}"
    | _, _, _ => say "parts.6" "card" input.name "a load has its case, the part it is on and its field"
  let asked : Std.HashSet (String × String) := rules.asks.foldl (fun asked ask => asked.insert (ask.kind, ask.mechanism)) {}
  for w in card.waivers do
    unless (place.get? w.subject).any fun k => asked.contains (parts[k]!.kind.name, w.mechanism) do
      say "parts.7" "card" s!"{w.subject}/{w.mechanism}" "the grid asks no such mechanism of a part of this name"
  unless card.claims.isEmpty do say "parts.8" "card" "claims" "a deck of rules does not read a claim yet"
  for key in card.stated do say "parts.8" "card" key "a deck of rules does not read these yet"
  unless design.params.isEmpty do say "parts.8" "design" "params" "a deck of rules does not read a param yet"
  return parts

def Static.holds (part : Part) : Static → Bool
  | .is field name => match part.slot field with
    | some (.key mine) => mine == name
    | _ => false
  | .loaded load => part.loads.any (·.1 == load)
  | .and cs => cs.foldl (fun so c => so && c.holds part) true
  | .or cs => cs.foldl (fun so c => so || c.holds part) false
  | .not c => !c.holds part

/-- What a tape reads of `part` under a load case. `named` finds a part by its name. -/
def site (named : Std.HashMap String Part) (part : Part) (under : Option String) : Site :=
  let slot (called : Option String) (field : String) : Option Slot :=
    match called with
    | none => part.slot field
    | some called => do (← named.get? (← part.joined called)).slot field
  { quantity := fun called field => match slot called field with
      | some (.quantity input) => some input
      | _ => none
    key := fun called field => match slot called field with
      | some (.key name) => some name
      | _ => none
    load := fun name => do
      let under ← under
      (part.loads.find? fun load => load.1 == name && load.2.1 == under).map (·.2.2) }

/-- A cell, the state the kernel settles on, and why when that is open. For a cell read
from proofs.json, `cell.state` is what the file claims. For a cell the kernel works out from
a deck of rules, it is what the first hint for the cell claims, and `hinted` says there is
one. Such a cell does not keep its tape: the kernel writes one for each part and each rule,
and holds one at a time. -/
structure Settled where
  cell : Cell
  state : State
  reason : String := ""
  /-- The waiver a waived cell rests on, with its place in the card's list. -/
  waiver : Option (Nat × Waiver) := none
  hinted : Bool := true

/-- The partition with each label as the tape's input of that label. -/
def Split.partition (labels : Array String) : Split → Except String Partition
  | .leaf => pure .leaf
  | .split label cut below above => do
    let some k := labels.findIdx? (· == label) | throw s!"the partition splits {label}, which the tape does not read"
    return .split k cut (← below.partition labels) (← above.partition labels)

/-- The state the hints settle a tape on: proved by the first partition that proves every
root, or refuted by the first point that refutes root 0 when `refutable`, and open with the
first reason otherwise. The tape is the kernel's, with the ranges the card and the design
give, so a point is inside them or refutes nothing. -/
def byHints (tape : Tape) (hints : Array Hint) (refutable : Bool) : StateM Caches (State × String) := do
  let labels := tape.inputs.map (·.label)
  let mut reason := ""
  for hint in hints do
    let mut tries : Array (State × M Unit) := #[]
    if let some split := hint.partition then
      tries := tries.push (.proved, do tape.proved (← split.partition labels))
    if let (some point, true) := (hint.point, refutable) then
      tries := tries.push (.refuted, do
        let values ← tape.inputs.mapM fun input => match point.find? (·.1 == input.label) with
          | some (_, x) => pure x
          | none => throw s!"the point has no value for {input.label}"
        tape.refuted values 0)
    for (state, proof) in tries do
      match proof.run (← get) with
      | .ok (_, caches) =>
        set caches
        return (state, "")
      | .error why => if reason.isEmpty then reason := why
  return (.undecided, if reason.isEmpty then "proofs.json has no partition and no point for it" else reason)

/-- What `cells` gives: every cell, how many hints name no cell the kernel has, and how many
distinct `dsg:` inputs the tapes of the proved and the refuted cells read. -/
structure Made where
  cells : Array Settled
  ignored : Nat
  dsgInputs : Nat

/-- Every cell of the design, in the order petra/grid.py lists them: for each part, each
mechanism the grid asks of its type, and then each field that nothing reads. An error when
there are more than `MAX_CELLS` of them, or when writing their tapes takes more than
`MAX_STEPS` steps: the kernel stops there and settles none. -/
def cells (rules : Rules) (card : Card) (parts : Array Part) (hints : Array Hint) : StateM Caches (Except String Made) := do
  let over := s!"the deck of rules asks more than {MAX_CELLS} cells of this design, and the kernel makes no more"
  let long := s!"writing the tapes of this design from the deck of rules takes more than {MAX_STEPS} steps, and the kernel takes no more"
  let hinted := grouped hints fun h => (h.subject, h.mechanism, h.entry)
  let hintsFor (subject mechanism entry : String) : Array Hint := hinted.getD (subject, mechanism, entry) #[]
  let waivers := firsts card.waivers.zipIdx fun w => (w.1.subject, w.1.mechanism)
  let asksOf := grouped rules.asks (·.kind)
  let rulesOf := grouped rules.rules (·.kind)
  let named := firsts parts (·.name)
  let cell (subject mechanism entry : String) (state : State) (reason : String := "") (waiver : Option (Nat × Waiver) := none) : Settled :=
    let claims := hintsFor subject mechanism entry
    { cell := { subject, mechanism, entry, state := (claims[0]?.map (·.state)).getD .undecided, tape := none,
                partition := none, point := none, which := none },
      state, reason := clip reason, waiver, hinted := !claims.isEmpty }
  let dsgOf (tape : Tape) (seen : Std.HashSet String) : Std.HashSet String :=
    tape.inputs.foldl (fun seen i => if i.label.startsWith "dsg:" then seen.insert i.label else seen) seen
  let mut out : Array Settled := #[]
  let mut ranges : Std.HashSet (String × String × String) := {}
  let mut dsg : Std.HashSet String := {}
  let mut steps := 0
  for part in parts do
    for ask in asksOf.getD part.kind.name #[] do
      if out.size > MAX_CELLS then return .error over
      let pending (entry reason : String) : Settled := cell part.name ask.mechanism entry .undecided reason
      if let some (waiver, k) := waivers.get? (part.name, ask.mechanism) then
        out := out.push (cell part.name ask.mechanism "" .waived "" (some (k, waiver)))
      else if ask.excuse.any fun condition => condition.all (·.holds part) then
        out := out.push (cell part.name ask.mechanism "" .notApplicable)
      else
        let answers := (rulesOf.getD ask.kind #[]).filter fun r => r.mechanism == ask.mechanism && r.condition.all (·.holds part)
        if answers.isEmpty then
          let other := if rules.rules.any (·.mechanism == ask.mechanism) then " on a part like this one" else ""
          out := out.push (pending "" s!"the deck has no rule for it{other}")
        for rule in answers do
          let tail := (rule.id.splitOn "/").getLast!
          let casesOf (load : String) : Array String := (part.loads.filter (·.1 == load)).map (·.2.1)
          let missing := rule.loads.filter fun load => (casesOf load).isEmpty
          if !missing.isEmpty then
            let rest := if missing.size > 4 then s!" and {missing.size - 4} more" else ""
            out := out.push (pending tail s!"the card puts no {" and no ".intercalate (missing.toList.take 4)}{rest} on {part.name}, which the rule reads")
            continue
          let unders : Array (Option String) := match rule.loads.toList with
            | [] => #[none]
            | first :: rest => (((casesOf first).filter fun c => rest.all fun load => (casesOf load).contains c).qsort (· < ·)).map some
          if unders.isEmpty then out := out.push (pending tail s!"no load case puts every load the rule reads on {part.name}")
          for under in unders do
            if out.size > MAX_CELLS then return .error over
            steps := steps + rule.steps.size * (if rule.ranges.isEmpty then 1 else 2)
            if steps > MAX_STEPS then return .error long
            let entry := match under with
              | some under => s!"{tail}/{under}"
              | none => tail
            let here := site named part under
            if !rule.ranges.isEmpty then
              match rule.tape here rule.ranges with
              | .error why =>
                out := out.push (pending entry why)
                continue
              | .ok tape =>
                steps := steps + tape.nodes.size
                ranges := ranges.insert (part.name, ask.mechanism, entry ++ "/where")
                let (state, reason) ← byHints tape (hintsFor part.name ask.mechanism (entry ++ "/where")) false
                if state == .proved then
                  out := out.push (cell part.name ask.mechanism (entry ++ "/where") .proved)
                  dsg := dsgOf tape dsg
                else
                  out := out.push (pending entry s!"the range the rule holds in is not proved: {reason}")
                  continue
            match rule.tape here #[(rule.low, rule.high)] with
            | .error why => out := out.push (pending entry why)
            | .ok tape =>
              steps := steps + tape.nodes.size
              let (state, reason) ← byHints tape (hintsFor part.name ask.mechanism entry) true
              out := out.push (cell part.name ask.mechanism entry state reason)
              if state == .proved || state == .refuted then dsg := dsgOf tape dsg
  let mut read : Std.HashSet (String × String) := {}
  for part in parts do
    for ask in asksOf.getD part.kind.name #[] do
      for field in ((ask.excuse.bind id).map Static.keys).getD #[] do read := read.insert (part.name, field)
    for rule in rulesOf.getD part.kind.name #[] do
      if rule.condition.all (·.holds part) then
        for (called, field) in rule.fields do
          match called with
          | none => read := read.insert (part.name, field)
          | some called => if let some other := part.joined called then read := read.insert (other, field)
  for part in parts do
    for field in part.kind.fields do
      if out.size > MAX_CELLS then return .error over
      unless (field.kind matches .parts ..) || read.contains (part.name, field.name) do
        out := out.push (cell part.name "unread" field.name .undecided s!"no rule of the deck reads {part.name}.{field.name}, so nothing checks it")
  if out.size > MAX_CELLS then return .error over
  let made := out.foldl (fun made s => made.insert (s.cell.subject, s.cell.mechanism, s.cell.entry)) ranges
  return .ok { cells := out, ignored := (hints.filter fun h => !made.contains (h.subject, h.mechanism, h.entry)).size, dsgInputs := dsg.size }

end Petra
