/-
A design against a deck of rules: its parts, and one cell for each answer the grid asks,
as `read_parts`, `cells`, `_answers` and `_unread` in petra/grid.py work them out. The cells
are the kernel's own. proofs.json gives only hints: a partition or a point to try.

Everything here that is found by name is found through a table kept in the order of its
keys, so the work grows with the files and not with their product, whatever names a file
holds. Where a part meets the deck, the work is the product of the two, and it is counted
in steps before it is done: a design past `MAX_CELLS` cells or `MAX_STEPS` steps is refused
there.
-/
import Petra.Deck

namespace Petra

/-- What a part has for one field: a quantity as a tape reads it, the name of a key, or the
names of the parts it joins. -/
inductive Slot where
  | quantity (input : TapeInput)
  | key (name : String)
  | parts (names : Array String)

/-- A part of a deck's type, with what it has for each field by the field's name. -/
structure Part where
  name : String
  kind : Kind
  slots : Std.TreeMap String Slot
  deriving Inhabited

def Part.slot (part : Part) (field : String) : Option Slot := part.slots.get? field

/-- The name of the part that `part` joins under the name a rule calls it by. -/
def Part.joined (part : Part) (called : String) : Option String := do
  let (_, field, k) ← part.kind.called.get? called
  let .parts joined ← part.slot field | none
  joined[k]?

/-- The loads the card puts on the parts. `on` finds the card's input by the part, the load
and the load case. `put` holds, for a part, each load the card puts on it with the case
that does, in the order of the loads' names and then of the cases'. `carried` holds each
part with each load that some case puts on it. `cases` holds the load cases of the card,
each once, in the order of their names: the names its `cases` lists and the case of each
of its loads. -/
structure Loads where
  on : Std.TreeMap (String × String × String) TapeInput := {}
  put : Std.TreeMap String (Array (String × String)) := {}
  carried : Std.TreeSet (String × String) := {}
  cases : Array String := #[]

/-- The items under each key, in their order. -/
def grouped [Ord κ] (items : Array α) (key : α → κ) : Std.TreeMap κ (Array α) :=
  items.foldl (init := {}) fun table x => table.alter (key x) fun
    | some found => some (found.push x)
    | none => some #[x]

/-- The first item under each key. -/
def firsts [Ord κ] (items : Array α) (key : α → κ) : Std.TreeMap κ α :=
  items.foldl (init := {}) fun table x => table.insertIfNew (key x) x

/-- A quantity is of its field's dimension, more than zero and at least the field's least. -/
def sized (dim : Dim) (least : Option Rat) (its : String) (range : Iv) : Except (String × String) Unit := do
  unless dimNamed its == some dim do throw ("parts.3", s!"is a {its}, which is not the dimension of its field")
  if range.lo ≤ 0 then throw ("parts.3", "is not more than zero")
  if least.any (range.lo < ·) then throw ("parts.3", "is under the least its field may take")

/-- What a line gives its field, or the rule it breaks and why. `typed` holds each part of
the design by its name and its type, `inputs` the card's inputs of each name, and `card` and
`design` the two names as the labels of a tape hold them. -/
def slotOf (card design : String) (typed : Std.TreeSet (String × String))
    (inputs : Std.TreeMap String (Array Input)) (part : String) (field : Field) (args : Array Arg) :
    Except (String × String) Slot := do
  match field.kind, args.toList with
  | .parts kind names, args =>
    let named := args.filterMap fun
      | .word word => some word
      | _ => none
    unless named.length == args.length && named.length == names.size && distinct named.toArray
        && named.all (fun n => typed.contains (n, kind)) do
      throw ("parts.5", s!"names {names.size} different {kind} parts of this design")
    return .parts named.toArray
  | .key _ known, [.word name] | .key _ known, [.text name] =>
    unless known.contains name do throw ("parts.4", field.oneOf)
    return .key name
  | .key .., _ => throw ("parts.4", "takes one name")
  | .quantity dim signed whole least, [.number its range] =>
    if signed then throw ("parts.3", "is for the card to state: the design reads it with a given")
    sized dim least its range
    if whole && (range.lo != range.hi || range.lo.den != 1) then throw ("parts.3", "is a count: one whole number")
    return .quantity ⟨s!"dsg:{design}.{part}.{field.name}", range⟩
  | .quantity dim _ whole least, [.given name] =>
    if whole then throw ("parts.3", "is a count, which the design writes as a whole number")
    unless name == s!"{part}.{field.name}" do
      throw ("parts.3", s!"reads the given {name}, and a part reads only the bound the card gives for it, {part}.{field.name}")
    match (inputs.getD name #[]).toList with
    | [input] =>
      if input.caseName.isSome || input.on.isSome || input.field.isSome then throw ("parts.3", s!"{name} is a load of the card")
      sized dim least input.dim input.range
      return .quantity ⟨s!"in:{card}.{name}", input.range⟩
    | [] => throw ("parts.3", s!"the card gives no {name}")
    | _ => throw ("parts.3", s!"the card gives {name} twice")
  | .quantity .., _ => throw ("parts.3", "is one number or one given")

/-- The parts of the design with the card's loads on them, and a finding for each rule of
the group Parts in docs/format.md that the design or the card breaks. -/
def readParts (rules : Rules) (card : Card) (design : Design) : StateM Findings (Array Part × Loads) := do
  let say (rule file item why : String) : StateM Findings Unit := modify (·.push ⟨rule, file, item, why⟩)
  -- The label of every input of a tape holds the name of the card or of the design, so a
  -- long name would be held once for each number of the design. A name past `MAX_TITLE` is
  -- a finding, and no label is made from it.
  let title (file name : String) : StateM Findings String := do
    if printed name ≤ MAX_TITLE then return name
    say "shape" file "name" s!"the name of the {file} prints in at most {MAX_TITLE} bytes for a design with parts, and this one in {printed name}"
    return ""
  let cardName ← title "card" card.name
  let designName ← title "design" design.name
  let blocks := design.parts.getD #[]
  let typed : Std.TreeSet (String × String) := blocks.foldl (fun seen b => seen.insert (b.name, b.kind)) {}
  let inputsNamed := grouped card.inputs (·.name)
  let kinds := firsts rules.kinds (·.name)
  let mut parts : Array Part := #[]
  let mut names : Std.TreeSet String := {}
  for block in blocks do
    if names.contains block.name then say "parts.1" "design" block.name "two parts have this name"
    names := names.insert block.name
    match kinds.get? block.kind with
    | none => say "parts.1" "design" block.name s!"{block.kind} is not a type of the deck of rules"
    | some kind =>
      let mut slots : Std.TreeMap String Slot := {}
      let mut given : Std.TreeSet String := {}
      let mut known := 0
      for line in block.lines do
        let item := s!"{block.name}.{line.field}"
        match kind.field.get? line.field with
        | none => say "parts.2" "design" item s!"is not a field of a {kind.name}"
        | some field =>
          if given.contains line.field then say "parts.2" "design" item "is given twice"
          else
            known := known + 1
            match slotOf cardName designName typed inputsNamed block.name field line.args with
            | .ok slot => slots := slots.insert line.field slot
            | .error (rule, why) => say rule "design" item why
        given := given.insert line.field
      -- A finding for each field the part lacks. Once the findings are full they are only
      -- counted, and the fields a part lacks are its type's less the ones it gives: a design
      -- of many empty parts of a type of many fields is counted and not gone through.
      if (← get).kept.size < MAX_FINDINGS then
        for field in kind.fields do
          unless given.contains field.name do say "parts.2" "design" block.name s!"lacks {field.name}"
      else modify fun found => { found with more := found.more + (kind.fields.size - known) }
      parts := parts.push { name := block.name, kind, slots }
  let joins : Std.TreeMap String Nat := parts.foldl (init := {}) fun table part => part.slots.foldl (init := table) fun table _ slot =>
    match slot with
    | .parts names => names.foldl (fun table name => table.insert name (table.getD name 0 + 1)) table
    | _ => table
  for part in parts do
    if joins.getD part.name 0 > 1 then say "parts.5" "design" part.name "is joined more than once, and a deck has no rule yet for a part that two others load"
  let read : Std.TreeSet String := blocks.foldl (init := {}) fun read block => block.lines.foldl (init := read) fun read line =>
    line.args.foldl (init := read) fun read arg => match arg with
      | .given name => read.insert name
      | _ => read
  let place : Std.TreeMap String Part := firsts parts (·.name)
  let mut on : Std.TreeMap (String × String × String) TapeInput := {}
  -- A name of the card's `cases` is the name of a load case, whether a load has it or not,
  -- and a cell prints it. The case of a load is held to its limits below, where the load is
  -- read, and a case that no load has is held to them here.
  let ofLoads := setOf (card.inputs.filterMap (·.caseName))
  for under in card.caseNames do
    unless ofLoads.contains under do
      if let .error why := short "the name of a load case" under then say "shape" "card" "cases" why
      else if under.contains '/' then say "shape" "card" "cases" "the name of a load case holds no /: an entry is a rule and a case with a / between them"
  for input in card.inputs do
    if (inputsNamed.getD input.name #[]).size > 1 then say "parts.6" "card" input.name "two inputs have this name"
    match input.caseName, input.on, input.field with
    | none, none, none =>
      unless read.contains input.name do say "parts.6" "card" input.name "is no load, and no part reads it"
    | some under, some part, some field =>
      match place.get? part with
      | none => say "parts.6" "card" input.name s!"a load is put on a part, and {part} is not one"
      | some its =>
        match (its.kind.load.get? field).map (·.kind) with
        | some (FieldKind.quantity dim _ _ least) =>
          if dimNamed input.dim != some dim then say "parts.6" "card" input.name s!"is a {input.dim}, which is not the dimension of {field}"
          else if least.any (input.range.lo < ·) then say "parts.6" "card" input.name s!"is under the least {field} may take"
          else if on.contains (part, field, under) then say "parts.6" "card" input.name s!"{under} puts {field} on {part} twice"
          else if let .error why := short "the name of a load case" under then say "shape" "card" input.name why
          else if under.contains '/' then say "shape" "card" input.name "the name of a load case holds no /: an entry is a rule and a case with a / between them"
          else on := on.insert (part, field, under) ⟨s!"in:{cardName}.{input.name}", input.range⟩
        | _ => say "parts.6" "card" input.name s!"a {its.kind.name} takes no load {field}"
    | _, _, _ => say "parts.6" "card" input.name "a load has its case, the part it is on and its field"
  let asked : Std.TreeSet (String × String) := rules.asks.foldl (fun asked ask => asked.insert (ask.kind, ask.mechanism)) {}
  for w in card.waivers do
    unless (place.get? w.subject).any fun part => asked.contains (part.kind.name, w.mechanism) do
      say "parts.7" "card" s!"{w.subject}/{w.mechanism}" "the grid asks no such mechanism of a part of this name"
  unless card.claims.isEmpty do say "parts.8" "card" "claims" "a deck of rules does not read a claim yet"
  for key in card.stated do say "parts.8" "card" key "a deck of rules does not read these yet"
  unless design.params.isEmpty do say "parts.8" "design" "params" "a deck of rules does not read a param yet"
  -- `on` is kept in the order of the part, then the load, then the case. So going through
  -- it gives each part its loads in the order of their names, and each load its cases in
  -- the order of theirs, whatever order the card lists them in.
  let put : Std.TreeMap String (Array (String × String)) := on.foldl (init := {}) fun table (part, load, under) _ =>
    table.alter part fun
      | some found => some (found.push (load, under))
      | none => some #[(load, under)]
  let carried : Std.TreeSet (String × String) := on.foldl (init := {}) fun found (part, load, _) _ => found.insert (part, load)
  let cases : Std.TreeSet String := on.foldl (init := setOf card.caseNames) fun found (_, _, under) _ => found.insert under
  return (parts, { on, put, carried, cases := cases.toArray })

/-- The parts that `part` joins, each under the name a rule calls it by. A condition finds a
joined part here, among the names of one part's type, and not among every part of the
design. A part gives one word for each of these names, so the table is no larger than the
part's own lines. -/
def Part.fellows (named : Std.TreeMap String Part) (part : Part) : Std.TreeMap String Part :=
  part.kind.called.foldl (init := {}) fun found called (_, field, k) =>
    match part.slot field with
    | some (.parts joined) =>
      match joined[k]? >>= named.get? with
      | some other => found.insert called other
      | none => found
    | _ => found

/-- Whether a condition holds for a part. An `is` reads a key of the part, or of the one
part it joins under a name, which `fellows` holds. A key that is not there holds no name. -/
def Static.holds (loads : Loads) (part : Part) (fellows : Std.TreeMap String Part) : Static → Bool
  | .is called field name =>
    let owner := match called with
      | none => some part
      | some called => fellows.get? called
    match owner.bind (·.slot field) with
    | some (.key mine) => mine == name
    | _ => false
  | .loaded load => loads.carried.contains (part.name, load)
  | .and cs => cs.foldl (fun so c => so && c.holds loads part fellows) true
  | .or cs => cs.foldl (fun so c => so || c.holds loads part fellows) false
  | .not c => !c.holds loads part fellows

/-- What a tape reads of `part` under a load case. `named` finds a part by its name. -/
def site (named : Std.TreeMap String Part) (loads : Loads) (part : Part) (under : Option String) : Site :=
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
    load := fun name => do loads.on.get? (part.name, name, ← under) }

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

/-- The partition with each label as the tape's input of that label. `place` finds the
first input of a label. It is made when the partition first splits, so a partition of one
leaf, which names no input, costs no table. -/
def Split.partition (place : Thunk (Std.TreeMap String Nat)) : Split → Except String Partition
  | .leaf => pure .leaf
  | .split label cut below above => do
    let some k := place.get.get? label | throw s!"the partition splits {label}, which the tape does not read"
    return .split k cut (← below.partition place) (← above.partition place)

/-- The state the hints settle a tape on: proved by the first partition that proves every
root, or refuted by the first point that refutes root 0 when `refutable`, and open with the
first reason otherwise. The tape is the kernel's, with the ranges the card and the design
give, so a point is inside them or refutes nothing. `left` is the work the proofs before
this one left of `MAX_WORK`, and the result holds what this one leaves. A try pays for
itself as it goes, and one that cannot pay its fee is not made.

The size of the tape is found once, and each hint is held to its fee from that. A hint
then costs its own length to look at, however long the tape is: only a try that pays reads
the tape. -/
def byHints (tape : Tape) (hints : Array Hint) (refutable : Bool) (left : Nat) : StateM Caches (State × String × Nat) := do
  if hints.isEmpty then return (.undecided, "proofs.json has no partition and no point for it", left)
  let place : Thunk (Std.TreeMap String Nat) := Thunk.mk fun _ =>
    tape.inputs.zipIdx.foldl (fun table (input, k) => if table.contains input.label then table else table.insert input.label k) {}
  let size := tape.size
  let fee (leaves : Nat) : Nat := feeOf size tape.inputs.size leaves
  let mut reason := ""
  let mut left := left
  for hint in hints do
    let mut tries : Array (State × Nat × (Nat → M (Option String × Nat))) := #[]
    if let some split := hint.partition then
      match split.partition place with
      | .ok partition => tries := tries.push (.proved, fee partition.count, tape.proved partition)
      | .error why => if reason.isEmpty then reason := why
    if let (some point, true) := (hint.point, refutable) then
      tries := tries.push (.refuted, fee 1, fun left =>
        let given : Std.TreeMap String Rat := point.foldl (fun table (label, x) => table.insert label x) {}
        match tape.inputs.mapM fun input => given.get? input.label with
        | some values =>
          if left < fee 1 + SPLIT * tape.inputs.size then pure (some SPENT, left) else tape.refuted values 0 left
        | none =>
          let lacks := (tape.inputs.find? fun input => !given.contains input.label).map (·.label)
          pure (some s!"the point has no value for {lacks.getD ""}", left))
    for (state, least, proof) in tries do
      if left < least then
        if reason.isEmpty then reason := SPENT
      else
        match (proof left).run (← get) with
        | .ok ((none, after), caches) =>
          set caches
          return (state, "", after)
        | .ok ((some why, after), _) =>
          left := after
          if reason.isEmpty then reason := why
        | .error why => if reason.isEmpty then reason := why
  return (.undecided, if reason.isEmpty then "proofs.json has no partition and no point for it" else reason, left)

/-- What `cells` gives: every cell, how many hints name no cell the kernel has, and how many
distinct `dsg:` inputs the tapes of the proved and the refuted cells read. -/
structure Made where
  cells : Array Settled
  ignored : Nat
  dsgInputs : Nat
  /-- The work the proofs took, of `MAX_WORK`. -/
  work : Nat

/-- The cells with their reasons held to `MAX_REASONS` bytes between them: a reason that
would go past it is replaced by `UNSAID`. -/
def said (cells : Array Settled) : Array Settled :=
  (cells.foldl (fun (out, room) s =>
    if s.reason.isEmpty then (out.push s, room)
    else if printed s.reason ≤ room then (out.push s, room - printed s.reason)
    else (out.push { s with reason := UNSAID }, 0)) (#[], MAX_REASONS)).1

/-- Every cell of the design, in the order petra/grid.py lists them: for each part, each
mechanism the grid asks of its type, and then for each part each field and each load that
nothing reads. An error when there are more than `MAX_CELLS` of them, or when making them
takes more than `MAX_STEPS` steps: the kernel stops there and settles none.

A rule that reads loads answers once for each load case of the card. Under a case that does
not put every load the rule reads on the part, its cell is open: a load the card does not
state is not taken as zero.

A step is counted before the work it stands for. A line of the grid for a part is a step
and one for each part of its `unless`. A rule of the line is a step, one for each part of
its `when` and one for each load it reads. For a rule that answers and reads loads, each
load case of the card is a step for each load the rule reads. Writing a tape is the weight
of its rule, and a tape is a step for each node. Then every rule of a part's type is looked
at once more for what it reads of the part: its look, and a step for each field it reads. -/
def cells (rules : Rules) (card : Card) (parts : Array Part) (loads : Loads) (hints : Array Hint) : StateM Caches (Except String Made) := do
  let over := s!"the deck of rules asks more than {MAX_CELLS} cells of this design, and the kernel makes no more"
  let long := s!"writing the tapes of this design from the deck of rules takes more than {MAX_STEPS} steps, and the kernel takes no more"
  let hinted := grouped hints fun h => (h.subject, h.mechanism, h.entry)
  let hintsFor (subject mechanism entry : String) : Array Hint := hinted.getD (subject, mechanism, entry) #[]
  let waivers := firsts card.waivers.zipIdx fun w => (w.1.subject, w.1.mechanism)
  let asksOf := grouped rules.asks (·.kind)
  let rulesOf := grouped rules.rules fun r => (r.kind, r.mechanism)
  let lookOf : Std.TreeMap (String × String) Nat := rulesOf.map fun _ line => line.foldl (fun n r => n + r.look) 0
  let named := firsts parts (·.name)
  let fellowsOf := parts.map (·.fellows named)
  let answered : Std.TreeSet String := rules.rules.foldl (fun found r => found.insert r.mechanism) {}
  let cell (subject mechanism entry : String) (state : State) (reason : String := "") (waiver : Option (Nat × Waiver) := none) : Settled :=
    let claims := hintsFor subject mechanism entry
    { cell := { subject, mechanism, entry, state := (claims[0]?.map (·.state)).getD .undecided, tape := none,
                partition := none, point := none, which := none },
      state, reason := clip reason, waiver, hinted := !claims.isEmpty }
  let dsgOf (tape : Tape) (seen : Std.TreeSet String) : Std.TreeSet String :=
    tape.inputs.foldl (fun seen i => if i.label.startsWith "dsg:" then seen.insert i.label else seen) seen
  -- The loads of a list, for a reason: the first four by name, and how many more.
  let listed (names : Array String) : String :=
    " and no ".intercalate (names.toList.take 4) ++ (if names.size > 4 then s!" and {names.size - 4} more" else "")
  let mut out : Array Settled := #[]
  let mut ranges : Std.TreeSet (String × String × String) := {}
  let mut dsg : Std.TreeSet String := {}
  let mut steps := 0
  let mut left := MAX_WORK
  for (part, fellows) in parts.zip fellowsOf do
    for ask in asksOf.getD part.kind.name #[] do
      if out.size > MAX_CELLS then return .error over
      steps := steps + 1 + ((ask.excuse.bind id).map Static.size).getD 0 + lookOf.getD (ask.kind, ask.mechanism) 0
      if steps > MAX_STEPS then return .error long
      let pending (entry reason : String) : Settled := cell part.name ask.mechanism entry .undecided reason
      if let some (waiver, k) := waivers.get? (part.name, ask.mechanism) then
        out := out.push (cell part.name ask.mechanism "" .waived "" (some (k, waiver)))
      else if ask.excuse.any fun condition => condition.all (·.holds loads part fellows) then
        out := out.push (cell part.name ask.mechanism "" .notApplicable)
      else
        let answers := (rulesOf.getD (ask.kind, ask.mechanism) #[]).filter fun r => r.condition.all (·.holds loads part fellows)
        if answers.isEmpty then
          let other := if answered.contains ask.mechanism then " on a part like this one" else ""
          out := out.push (pending "" s!"the deck has no rule for it{other}")
        for rule in answers do
          let tail := rule.entry
          -- A rule that requires has one cell, with no tape and no hint: proved when its
          -- condition over keys holds for the part, and refuted when it does not, with each
          -- key it names and the name the part has for it.
          if let some required := rule.requires then
            if out.size > MAX_CELLS then return .error over
            if required.holds loads part fellows then out := out.push (cell part.name ask.mechanism tail .proved)
            else
              let has := (once required.keys).map fun (called, field) =>
                let owner := match called with
                  | none => some part
                  | some called => fellows.get? called
                let name := match owner.bind (·.slot field) with
                  | some (.key mine) => mine
                  | _ => "nothing"
                s!"{(called.map (· ++ ".")).getD ""}{field} is {name}"
              out := out.push (cell part.name ask.mechanism tail .refuted
                s!"the part is not what the rule requires: {", ".intercalate has.toList}")
            continue
          let mut unders : Array (Option String) := #[none]
          if !rule.loads.isEmpty then
            -- A card with no load case at all puts none of the rule's loads on the part.
            if loads.cases.isEmpty then
              out := out.push (pending tail s!"the card puts no {listed rule.loads} on {part.name}, which the rule reads")
              continue
            -- One cell for each load case of the card, in the order of their names. Each case
            -- is looked up for each load the rule reads, which is what is counted.
            steps := steps + loads.cases.size * rule.loads.size
            if steps > MAX_STEPS then return .error long
            unders := loads.cases.map some
          for under in unders do
            if out.size > MAX_CELLS then return .error over
            let entry := match under with
              | some under => s!"{tail}/{under}"
              | none => tail
            -- A case that does not put every load the rule reads on the part leaves the cell
            -- open. No load is taken as zero: a card that means none states a load of zero.
            if let some c := under then
              let missing := rule.loads.filter fun load => !loads.on.contains (part.name, load, c)
              if !missing.isEmpty then
                out := out.push (pending entry s!"case {c} puts no {listed missing} on {part.name}, which the rule reads")
                continue
            steps := steps + rule.weight * (if rule.ranges.isEmpty then 1 else 2)
            if steps > MAX_STEPS then return .error long
            let here := site named loads part under
            if !rule.ranges.isEmpty then
              match rule.tape here rule.ranges with
              | .error why =>
                out := out.push (pending entry why)
                continue
              | .ok tape =>
                steps := steps + tape.nodes.size
                ranges := ranges.insert (part.name, ask.mechanism, entry ++ "/where")
                let (state, reason, after) ← byHints tape (hintsFor part.name ask.mechanism (entry ++ "/where")) false left
                left := after
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
              let (state, reason, after) ← byHints tape (hintsFor part.name ask.mechanism entry) true left
              left := after
              out := out.push (cell part.name ask.mechanism entry state reason)
              if state == .proved || state == .refuted then dsg := dsgOf tape dsg
  -- What a rule or a line of the grid reads of each part. Every rule of a part's type is
  -- looked at here, whatever the card waives, so the look is counted again. The look of a
  -- rule holds a step for each load it reads. A load is read by an expression of a rule
  -- that applies to the part it is on. A `loaded` in a `when` or an `unless` asks whether
  -- the load is there and reads nothing of it, so it is no reader.
  let rulesOfKind := grouped rules.rules (·.kind)
  let readOf : Std.TreeMap String Nat := rulesOfKind.map fun _ line => line.foldl (fun n r => n + r.look + r.fields.size) 0
  let mut read : Std.TreeSet (String × String) := {}
  let mut readLoads : Std.TreeSet (String × String) := {}
  for (part, fellows) in parts.zip fellowsOf do
    steps := steps + 1 + readOf.getD part.kind.name 0
    if steps > MAX_STEPS then return .error long
    for ask in asksOf.getD part.kind.name #[] do
      for (called, field) in ((ask.excuse.bind id).map Static.keys).getD #[] do
        match called with
        | none => read := read.insert (part.name, field)
        | some called => if let some other := fellows.get? called then read := read.insert (other.name, field)
    for rule in rulesOfKind.getD part.kind.name #[] do
      if rule.condition.all (·.holds loads part fellows) then
        for load in rule.loads do readLoads := readLoads.insert (part.name, load)
        for (called, field) in rule.fields do
          match called with
          | none => read := read.insert (part.name, field)
          | some called => if let some other := part.joined called then read := read.insert (other, field)
  for part in parts do
    for field in part.kind.fields do
      if out.size > MAX_CELLS then return .error over
      unless (field.kind matches .parts ..) || read.contains (part.name, field.name) do
        out := out.push (cell part.name UNREAD field.name .undecided s!"no rule of the deck reads {part.name}.{field.name}, so nothing checks it")
    -- A load that nothing reads, once for each case that puts it on the part. Its entry is
    -- `LOAD/CASE`, which no field's entry is: the name of a field holds no `/`.
    for (load, under) in loads.put.getD part.name #[] do
      if out.size > MAX_CELLS then return .error over
      unless readLoads.contains (part.name, load) do
        out := out.push (cell part.name UNREAD s!"{load}/{under}" .undecided
          s!"no rule of the deck reads the load {load} that case {under} puts on {part.name}, so nothing checks it")
  if out.size > MAX_CELLS then return .error over
  -- No two cells have one key: `readRules` and `readParts` refuse what could make two, and
  -- this holds the list to it whatever they let through.
  unless distinct (out.map fun s => (s.cell.subject, s.cell.mechanism, s.cell.entry)) do
    return .error "two cells of this design would have one subject, mechanism and entry, and the kernel prints no key twice"
  let made := out.foldl (fun made s => made.insert (s.cell.subject, s.cell.mechanism, s.cell.entry)) ranges
  return .ok { cells := said out, ignored := (hints.filter fun h => !made.contains (h.subject, h.mechanism, h.entry)).size,
               dsgInputs := dsg.size, work := MAX_WORK - left }

end Petra
