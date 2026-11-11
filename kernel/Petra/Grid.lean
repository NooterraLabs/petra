/-
A design against a deck of rules: its parts, and one cell for each answer the grid asks,
as `read_parts`, `cells`, `_answers` and `_unread` in petra/grid.py work them out. The cells
are the kernel's own. proofs.json gives only hints: a partition or a point to try.
-/
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

/-- A quantity is of its field's dimension, more than zero and at least the field's least. -/
def sized (dim : Dim) (least : Option Rat) (its : String) (range : Iv) : Except (String × String) Unit := do
  unless dimNamed its == some dim do throw ("parts.3", s!"is a {its}, which is not the dimension of its field")
  if range.lo ≤ 0 then throw ("parts.3", "is not more than zero")
  if least.any (range.lo < ·) then throw ("parts.3", "is under the least its field may take")

/-- What a line gives its field, or the rule it breaks and why. -/
def slotOf (card : Card) (design : Design) (blocks : Array Block) (part : String) (field : Field) (args : Array Arg) :
    Except (String × String) Slot := do
  match field.kind, args.toList with
  | .parts kind names, args =>
    let named := args.filterMap fun
      | .word word => some word
      | _ => none
    unless named.length == args.length && named.length == names.size && named.eraseDups.length == named.length
        && named.all (fun n => blocks.any fun b => b.name == n && b.kind == kind) do
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
    match (card.inputs.filter (·.name == name)).toList with
    | [input] =>
      if input.caseName.isSome || input.on.isSome || input.field.isSome then throw ("parts.3", s!"{name} is a load of the card")
      sized dim least input.dim input.range
      return .quantity ⟨s!"in:{card.name}.{name}", input.range⟩
    | [] => throw ("parts.3", s!"the card gives no {name}")
    | _ => throw ("parts.3", s!"the card gives {name} twice")
  | .quantity .., _ => throw ("parts.3", "is one number or one given")

/-- The parts of the design with the card's loads on them, and a finding for each rule of
the group Parts in docs/format.md that the design or the card breaks. -/
def readParts (rules : Rules) (card : Card) (design : Design) : StateM (Array Finding) (Array Part) := do
  let say (rule file item why : String) : StateM (Array Finding) Unit := modify (·.push ⟨rule, file, item, why⟩)
  let blocks := design.parts.getD #[]
  let mut parts : Array Part := #[]
  for (block, n) in blocks.zipIdx do
    if (blocks.extract 0 n).any (·.name == block.name) then say "parts.1" "design" block.name "two parts have this name"
    match rules.kinds.find? (·.name == block.kind) with
    | none => say "parts.1" "design" block.name s!"{block.kind} is not a type of the deck of rules"
    | some kind =>
      let mut slots : Array (String × Slot) := #[]
      for (line, k) in block.lines.zipIdx do
        let item := s!"{block.name}.{line.field}"
        match kind.fields.find? (·.name == line.field) with
        | none => say "parts.2" "design" item s!"is not a field of a {kind.name}"
        | some field =>
          if (block.lines.extract 0 k).any (·.field == line.field) then say "parts.2" "design" item "is given twice"
          else match slotOf card design blocks block.name field line.args with
            | .ok slot => slots := slots.push (line.field, slot)
            | .error (rule, why) => say rule "design" item why
      for field in kind.fields do
        unless block.lines.any (·.field == field.name) do say "parts.2" "design" block.name s!"lacks {field.name}"
      parts := parts.push { name := block.name, kind, slots, loads := #[] }
  for part in parts do
    let joins := parts.foldl (init := 0) fun n other => other.slots.foldl (init := n) fun n slot =>
      match slot.2 with
      | .parts names => n + (names.filter (· == part.name)).size
      | _ => n
    if joins > 1 then say "parts.5" "design" part.name "is joined more than once, and a deck has no rule yet for a part that two others load"
  for input in card.inputs do
    if (card.inputs.filter (·.name == input.name)).size > 1 then say "parts.6" "card" input.name "two inputs have this name"
    match input.caseName, input.on, input.field with
    | none, none, none =>
      let read := blocks.any fun block => block.lines.any fun line => line.args.any fun
        | .given name => name == input.name
        | _ => false
      unless read do say "parts.6" "card" input.name "is no load, and no part reads it"
    | some under, some on, some field =>
      match parts.findIdx? (·.name == on) with
      | none => say "parts.6" "card" input.name s!"a load is put on a part, and {on} is not one"
      | some k =>
        match (parts[k]!.kind.loads.find? (·.name == field)).map (·.kind) with
        | some (FieldKind.quantity dim _ _ least) =>
          if dimNamed input.dim != some dim then say "parts.6" "card" input.name s!"is a {input.dim}, which is not the dimension of {field}"
          else if least.any (input.range.lo < ·) then say "parts.6" "card" input.name s!"is under the least {field} may take"
          else if parts[k]!.loads.any (fun load => load.1 == field && load.2.1 == under) then
            say "parts.6" "card" input.name s!"{under} puts {field} on {on} twice"
          else parts := parts.modify k fun p => { p with loads := p.loads.push (field, under, ⟨s!"in:{card.name}.{input.name}", input.range⟩) }
        | _ => say "parts.6" "card" input.name s!"a {parts[k]!.kind.name} takes no load {field}"
    | _, _, _ => say "parts.6" "card" input.name "a load has its case, the part it is on and its field"
  for w in card.waivers do
    let asked := (parts.find? (·.name == w.subject)).any fun part =>
      rules.asks.any fun ask => ask.kind == part.kind.name && ask.mechanism == w.mechanism
    unless asked do say "parts.7" "card" s!"{w.subject}/{w.mechanism}" "the grid asks no such mechanism of a part of this name"
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

/-- What a tape reads of `part` under a load case. -/
def site (parts : Array Part) (part : Part) (under : Option String) : Site :=
  let slot (called : Option String) (field : String) : Option Slot :=
    match called with
    | none => part.slot field
    | some called => do (← parts.find? (·.name == (← part.joined called))).slot field
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
a deck of rules, it is what the first hint for the cell claims, and `hinted` says there is one. -/
structure Settled where
  cell : Cell
  state : State
  reason : String := ""
  waiver : Option Waiver := none
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

/-- Every cell of the design, in the order petra/grid.py lists them: for each part, each
mechanism the grid asks of its type, and then each field that nothing reads. Also how many
hints name no cell the kernel has. -/
def cells (rules : Rules) (card : Card) (parts : Array Part) (hints : Array Hint) : StateM Caches (Array Settled × Nat) := do
  let hintsFor (subject mechanism entry : String) : Array Hint :=
    hints.filter fun h => h.subject == subject && h.mechanism == mechanism && h.entry == entry
  let cell (subject mechanism entry : String) (state : State) (reason : String := "") (tape : Option Tape := none)
      (waiver : Option Waiver := none) : Settled :=
    let claims := hintsFor subject mechanism entry
    { cell := { subject, mechanism, entry, state := (claims[0]?.map (·.state)).getD .undecided, tape,
                partition := none, point := none, which := none },
      state, reason, waiver, hinted := !claims.isEmpty }
  let mut out : Array Settled := #[]
  let mut ranges : Array (String × String × String) := #[]
  for part in parts do
    for ask in rules.asks.filter (·.kind == part.kind.name) do
      let pending (entry reason : String) : Settled := cell part.name ask.mechanism entry .undecided reason
      if let some waiver := card.waivers.find? fun w => w.subject == part.name && w.mechanism == ask.mechanism then
        out := out.push (cell part.name ask.mechanism "" .waived "" none (some waiver))
      else if ask.excuse.any fun condition => condition.all (·.holds part) then
        out := out.push (cell part.name ask.mechanism "" .notApplicable)
      else
        let answers := rules.rules.filter fun r => r.kind == ask.kind && r.mechanism == ask.mechanism && r.condition.all (·.holds part)
        if answers.isEmpty then
          let other := if rules.rules.any (·.mechanism == ask.mechanism) then " on a part like this one" else ""
          out := out.push (pending "" s!"the deck has no rule for it{other}")
        for rule in answers do
          let tail := (rule.id.splitOn "/").getLast!
          let casesOf (load : String) : Array String := (part.loads.filter (·.1 == load)).map (·.2.1)
          let missing := rule.loads.filter fun load => (casesOf load).isEmpty
          if !missing.isEmpty then
            out := out.push (pending tail s!"the card puts no {" and no ".intercalate missing.toList} on {part.name}, which the rule reads")
            continue
          let unders : Array (Option String) := match rule.loads.toList with
            | [] => #[none]
            | first :: rest => (((casesOf first).filter fun c => rest.all fun load => (casesOf load).contains c).qsort (· < ·)).map some
          if unders.isEmpty then out := out.push (pending tail s!"no load case puts every load the rule reads on {part.name}")
          for under in unders do
            let entry := match under with
              | some under => s!"{tail}/{under}"
              | none => tail
            let here := site parts part under
            if !rule.ranges.isEmpty then
              match rule.tape here rule.ranges with
              | .error why =>
                out := out.push (pending entry why)
                continue
              | .ok tape =>
                ranges := ranges.push (part.name, ask.mechanism, entry ++ "/where")
                let (state, reason) ← byHints tape (hintsFor part.name ask.mechanism (entry ++ "/where")) false
                if state == .proved then out := out.push (cell part.name ask.mechanism (entry ++ "/where") .proved "" (some tape))
                else
                  out := out.push (pending entry s!"the range the rule holds in is not proved: {reason}")
                  continue
            match rule.tape here #[(rule.low, rule.high)] with
            | .error why => out := out.push (pending entry why)
            | .ok tape =>
              let (state, reason) ← byHints tape (hintsFor part.name ask.mechanism entry) true
              out := out.push (cell part.name ask.mechanism entry state reason (some tape))
  let mut read : Array (String × String) := #[]
  for part in parts do
    let conditions := (rules.asks.filter (·.kind == part.kind.name)).filterMap fun ask => ask.excuse.bind id
    let applies := rules.rules.filter fun r => r.kind == part.kind.name && r.condition.all (·.holds part)
    let reads : Array (Option String × String) := (conditions.flatMap Static.keys).map (none, ·) ++ applies.flatMap Rule.fields
    for (called, field) in reads do
      match called with
      | none => read := read.push (part.name, field)
      | some called => if let some other := part.joined called then read := read.push (other, field)
  for part in parts do
    for field in part.kind.fields do
      unless (field.kind matches .parts ..) || read.contains (part.name, field.name) do
        out := out.push (cell part.name "unread" field.name .undecided s!"no rule of the deck reads {part.name}.{field.name}, so nothing checks it")
  let known (h : Hint) : Bool :=
    out.any (fun s => s.cell.subject == h.subject && s.cell.mechanism == h.mechanism && s.cell.entry == h.entry)
      || ranges.contains (h.subject, h.mechanism, h.entry)
  return (out, (hints.filter (!known ·)).size)

end Petra
