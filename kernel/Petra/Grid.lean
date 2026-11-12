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
  /-- The part leaves the field unstated, which its type lets it. It has no value and no
  default: whatever reads it has no answer for the part. `quantity` says that the field is a
  quantity and not a key. -/
  | unstated (quantity : Bool)

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
that does, in the order of the loads' names and then of the cases'. `cases` holds the load
cases of the card, each once, in the order of their names: the names its `cases` lists and
the case of each of its loads. -/
structure Loads where
  on : Std.TreeMap (String × String × String) TapeInput := {}
  put : Std.TreeMap String (Array (String × String)) := {}
  cases : Array String := #[]

/-- The items under each key, in their order. -/
def grouped [Ord κ] (items : Array α) (key : α → κ) : Std.TreeMap κ (Array α) :=
  items.foldl (init := {}) fun table x => table.alter (key x) fun
    | some found => some (found.push x)
    | none => some #[x]

/-- The first item under each key. -/
def firsts [Ord κ] (items : Array α) (key : α → κ) : Std.TreeMap κ α :=
  items.foldl (init := {}) fun table x => table.insertIfNew (key x) x

/-- The floors that deck.json gives the dimensions, by the exponents of each (`Deck.input`). -/
abbrev Floors := Std.TreeMap (Array (Int × Nat)) (String × Floor)

/-- The floors of petra/decks/core.json, `domains.input`: zero for each dimension it lists, and
absolute zero, -273.15 degC, for a temperature. A design checked against a deck of rules is
held to these and not to the ones its deck.json gives: they decide whether a number of a part,
a bound of the card or a completion may be had, and no hash a reader checks covers deck.json
(type rule 8). -/
def CORE_FLOORS : Floors :=
  [("current", (0 : Rat)), ("voltage", 0), ("length", 0), ("area", 0), ("mass", 0), ("energy", 0),
   ("power", 0), ("time", 0), ("resistance", 0), ("dimensionless", 0), ("temperature", -5463 / 20)].foldl
    (init := {}) fun table (name, min) => match dimNamed name with
      | some dim => table.insert dim.key (name, { min, strict := false })
      | none => table

/-- Why the deck of rules is refused for a `least` under a floor of `floors`, if it is: the
first field or load, by type and then fields before loads, whose `least` is under the floor of
its dimension, where that floor holds for it as type rule 4 holds a load of the card. A floor
under zero holds always, and one at zero or above unless the quantity may be negative. A
completion of a load left out, and the search for one, go down to the `least`, where no card
may put the load. -/
def underFloor (rules : Rules) (floors : Floors) : Option String := Id.run do
  for kind in rules.kinds do
    for f in kind.fields ++ kind.loads do
      if let .quantity dim _ _ (some least) := f.kind then
        if let some (name, floor) := floors.get? dim.key then
          if (f.sign != .negative || floor.min < 0) && least < floor.min then
            return some s!"field {f.name}: its least, {least} in SI units, is under {floor.min}, the floor of a {name}, and no card states a value under it"
  return none

/-- A quantity is of its field's dimension and at least the field's least. It is more than
zero, unless its field says with `may_be` that it may be zero, and is then at least zero,
or that it may be negative, and then has no floor by its sign. -/
def sized (dim : Dim) (sign : Sign) (least : Option Rat) (its : String) (range : Iv) : Except (String × String) Unit := do
  unless dimNamed its == some dim do throw ("parts.3", s!"is a {its}, which is not the dimension of its field")
  match sign with
  | .positive => if range.lo ≤ 0 then throw ("parts.3", "is not more than zero")
  | .zero => if range.lo < 0 then throw ("parts.3", "is under zero, and its field may be zero and not under it")
  | .negative => pure ()
  if least.any (range.lo < ·) then throw ("parts.3", "is under the least its field may take")

/-- What a line gives its field, or the rule it breaks and why. `typed` holds each part of
the design by its name and its type, `inputs` the card's inputs of each name, and `card` and
`design` the two names as the labels of a tape hold them. -/
def slotOf (card design : String) (typed : Std.TreeSet (String × String))
    (inputs : Std.TreeMap String (Array Input)) (states : Std.TreeMap String (Array Stated)) (floors : Floors)
    (part : String) (field : Field) (args : Array Arg) :
    Except (String × String) Slot := do
  -- What the card states exactly under the name a line reads with a given: a part reads only
  -- what the card states for it and for the field, once. `rule` is the rule the field's kind
  -- breaks when there is none.
  let stated (rule name : String) : Except (String × String) Said := do
    unless name == s!"{part}.{field.name}" do
      throw (rule, s!"reads the given {name}, and a part reads only what the card states for it, {part}.{field.name}")
    match (states.getD name #[]).toList with
    | [found] => pure found.said
    | [] =>
      if inputs.contains name then
        throw (rule, s!"{name} is a bound of the card, and a key or a count is stated exactly: `given {name} is ...`")
      throw (rule, s!"the card states no {name}")
    | _ => throw (rule, s!"the card states {name} twice")
  -- The one word `unstated` leaves an `optional` field unstated. On any other field it is
  -- what it would be there: a name of a key that has that name, and nothing a quantity takes.
  if let (#[.word word], false) := (args, field.kind matches .parts ..) then
    if word == UNSTATED then
      if field.optional then return .unstated (field.kind matches .quantity ..)
      unless field.kind matches .key .. do
        throw ("parts.3", "is left unstated, and its field is not `optional`: it must be stated")
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
    if field.signed then throw ("parts.4", "is for the card to state: the design reads it with a given")
    unless known.contains name do throw ("parts.4", field.oneOf)
    return .key name
  | .key _ known, [.given name] =>
    -- A key that the card states: the name is the card's, and it is one of the key's names.
    match ← stated "parts.4" name with
    | .key said =>
      unless known.contains said do throw ("parts.4", field.oneOf)
      return .key said
    | .whole _ => throw ("parts.4", s!"the card states a whole number for {name}, and it is a key")
  | .key .., _ => throw ("parts.4", "takes one name, or one given")
  | .quantity dim signed whole least, [.number its range] =>
    if signed then throw ("parts.3", "is for the card to state: the design reads it with a given")
    sized dim field.sign least its range
    -- A number that may be negative is still held to a floor of its dimension that is under
    -- zero, as an input of the card is (type rule 4): no temperature is under absolute zero.
    if field.sign == .negative then
      if let some (name, floor) := floors.get? dim.key then
        if floor.min < 0 && !floor.admits range.lo then throw ("parts.3", floor.broken name range.lo)
    if whole && (range.lo != range.hi || range.lo.den != 1) then throw ("parts.3", "is a count: one whole number")
    return .quantity ⟨s!"dsg:{design}.{part}.{field.name}", range⟩
  | .quantity dim _ true least, [.given name] =>
    -- A count that the card states: one whole number, exact, held to the floor of its field.
    match ← stated "parts.3" name with
    | .whole n =>
      sized dim field.sign least "dimensionless" (Iv.pt n)
      return .quantity ⟨s!"in:{card}.{name}", Iv.pt n⟩
    | .key _ => throw ("parts.3", s!"the card states a name for {name}, and it is a count")
  | .quantity dim _ false least, [.given name] =>
    unless name == s!"{part}.{field.name}" do
      throw ("parts.3", s!"reads the given {name}, and a part reads only the bound the card gives for it, {part}.{field.name}")
    if states.contains name && !inputs.contains name then
      throw ("parts.3", s!"{name} is stated exactly by the card, and a quantity that is no count reads a bound: `given {name} in [...]`")
    match (inputs.getD name #[]).toList with
    | [input] =>
      if input.caseName.isSome || input.on.isSome || input.field.isSome then throw ("parts.3", s!"{name} is a load of the card")
      sized dim field.sign least input.dim input.range
      return .quantity ⟨s!"in:{card}.{name}", input.range⟩
    | [] => throw ("parts.3", s!"the card gives no {name}")
    | _ => throw ("parts.3", s!"the card gives {name} twice")
  | .quantity .., _ => throw ("parts.3", "is one number or one given")

/-- The parts of the design with the card's loads on them, and a finding for each rule of
the group Parts in docs/format.md that the design or the card breaks. -/
def readParts (rules : Rules) (card : Card) (design : Design) (floors : Floors := {}) : StateM Findings (Array Part × Loads) := do
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
  let statesNamed := grouped card.states (·.name)
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
            match slotOf cardName designName typed inputsNamed statesNamed floors block.name field line.args with
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
  -- A case is not named `where` either: the entry of its cells would end in `/where`, which
  -- marks the cell that proves a rule's range, and their proofs would not count.
  let WHERE := "a load case is not named where: an entry that ends in /where is the range of a rule"
  let ofLoads := setOf (card.inputs.filterMap (·.caseName))
  for under in card.caseNames do
    unless ofLoads.contains under do
      if let .error why := short "the name of a load case" under then say "shape" "card" "cases" why
      else if under.contains '/' then say "shape" "card" "cases" "the name of a load case holds no /: an entry is a rule and a case with a / between them"
      else if under == "where" then say "shape" "card" "cases" WHERE
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
          else if under == "where" then say "shape" "card" input.name WHERE
          else on := on.insert (part, field, under) ⟨s!"in:{cardName}.{input.name}", input.range⟩
        | _ => say "parts.6" "card" input.name s!"a {its.kind.name} takes no load {field}"
    | _, _, _ => say "parts.6" "card" input.name "a load has its case, the part it is on and its field"
  -- What the card states exactly is read by a part, as a given is, and has a name of its own
  -- among the statements and the inputs: a name in both could be read as either.
  for s in card.states do
    if (statesNamed.getD s.name #[]).size > 1 then say "parts.6" "card" s.name "two statements have this name"
    if inputsNamed.contains s.name then say "parts.6" "card" s.name "is the name of a statement and of an input: each has a name of its own"
    unless read.contains s.name do say "parts.6" "card" s.name "is stated, and no part reads it"
  let asked : Std.TreeSet (String × String) := rules.asks.foldl (fun asked ask => asked.insert (ask.kind, ask.mechanism)) {}
  for w in card.waivers do
    unless (place.get? w.subject).any fun part => asked.contains (part.kind.name, w.mechanism) do
      say "parts.7" "card" s!"{w.subject}/{w.mechanism}" "the grid asks no such mechanism of a part of this name"
  -- An environment that the card states would be read by no cell, and a verdict would look
  -- as if it held there: a lap in a marine atmosphere passed as it does indoors. It is
  -- refused, as an ambient is, until a deck reads one.
  if card.environment.isSome then say "parts.8" "card" "environment" "a deck of rules does not read an environment yet"
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
  let cases : Std.TreeSet String := on.foldl (init := setOf card.caseNames) fun found (_, _, under) _ => found.insert under
  return (parts, { on, put, cases := cases.toArray })

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

/-- The first of these fields that the part, or the part it joins under a name, leaves
unstated: `PART.FIELD`, with the name of the part that has the field. -/
def Part.lacks (part : Part) (fellows : Std.TreeMap String Part) (fields : Array (Option String × String)) : Option String :=
  fields.findSome? fun (called, field) =>
    let owner := match called with
      | none => some part
      | some called => fellows.get? called
    owner.bind fun owner => match owner.slot field with
      | some (.unstated _) => some s!"{owner.name}.{field}"
      | _ => none

/-- Whether one of these fields that the part, or a part it joins, leaves unstated is a
quantity. No hint names a value for a quantity, so the rule's cells stay open and no waiver
rests them. A key left unstated takes one of finitely many names, and a hint may name one. -/
def Part.lacksQuantity (part : Part) (fellows : Std.TreeMap String Part) (fields : Array (Option String × String)) : Bool :=
  fields.any fun (called, field) =>
    let owner := match called with
      | none => some part
      | some called => fellows.get? called
    match owner.bind (·.slot field) with
    | some (.unstated quantity) => quantity
    | _ => false

/-- A key that a rule reads and that a part leaves unstated: the part that has it, the field,
and the names the key may take, in the order of its `one_of` and again as a table. -/
structure Unsaid where
  owner : String
  field : String
  names : Array String
  known : Std.TreeSet String

/-- The keys of these fields that the part, or a part it joins, leaves unstated, each once,
in the order of the fields. -/
def Part.unsaid (part : Part) (fellows : Std.TreeMap String Part) (fields : Array (Option String × String)) : Array Unsaid :=
  fields.foldl (init := #[]) fun out (called, field) =>
    let owner := match called with
      | none => some part
      | some called => fellows.get? called
    match owner with
    | none => out
    | some owner =>
      match owner.slot field, (owner.kind.field.get? field).map (·.kind) with
      | some (.unstated false), some (FieldKind.key names known) =>
        if out.any fun u => u.owner == owner.name && u.field == field then out else out.push ⟨owner.name, field, names, known⟩
      | _, _ => out

/-- The parts with the keys of a completion named, and the card's loads with its loads put on
the parts. A completed load is an input of one value, labelled `put:CASE.PART.LOAD`. -/
def Completion.onto (c : Completion) (named : Std.TreeMap String Part) (loads : Loads) : Std.TreeMap String Part × Loads :=
  let named := c.keys.foldl (init := named) fun named (owner, field, name) =>
    named.modify owner fun p => { p with slots := p.slots.insert field (.key name) }
  let on := c.loads.foldl (init := loads.on) fun on (part, load, under, x) =>
    on.insert (part, load, under) ⟨s!"put:{under}.{part}.{load}", Iv.pt x⟩
  (named, { loads with on })

/-- Whether a completion gives each key of `unsaid` one of its names, and each load of
`missing` under the case `under` one value its field allows, each once and nothing else. A
load's value is at least the load's `least`; with none, at least zero, unless the load may be
negative. It is held to the floor of its dimension in `floors` as a load of the card is (type
rule 4): a floor under zero always, and one at zero or above unless the load may be negative.
So no completion puts a temperature under absolute zero. -/
def Completion.fits (c : Completion) (part : Part) (unsaid : Array Unsaid) (missing : Array String) (under : String) (floors : Floors) : Bool :=
  let allowed (load : String) (x : Rat) : Bool :=
    match part.kind.load.get? load with
    | some f => match f.kind with
      | .quantity dim _ _ least => least.all (· ≤ x) && (least.isSome || f.sign == .negative || 0 ≤ x)
          && (floors.get? dim.key).all fun (_, floor) => (f.sign == .negative && 0 ≤ floor.min) || floor.admits x
      | _ => false
    | none => false
  c.keys.size == unsaid.size && c.loads.size == missing.size
    && distinct (c.keys.map fun (owner, field, _) => (owner, field))
    && distinct (c.loads.map fun (_, load, _, _) => load)
    && c.keys.all (fun (owner, field, name) => unsaid.any fun u => u.owner == owner && u.field == field && u.known.contains name)
    && c.loads.all (fun (p, load, u, x) => p == part.name && u == under && missing.contains load && allowed load x)

/-- The names of the parts that leave a field unstated. -/
def bareOf (parts : Array Part) : Std.TreeSet String :=
  parts.foldl (init := {}) fun bare part =>
    if part.slots.foldl (fun so _ slot => so || slot matches .unstated _) false then bare.insert part.name else bare

/-- Whether the part leaves a field unstated or joins a part that does. Only for such a part
does the kernel look for what reads an unstated field, so a design that states every field
is checked in the steps it took before a field could be left unstated. -/
def Part.touched (part : Part) (bare : Std.TreeSet String) (fellows : Std.TreeMap String Part) : Bool :=
  bare.contains part.name || fellows.foldl (fun so _ other => so || bare.contains other.name) false

/-- What the reason of a waived cell starts with. What follows is the reason the cell had
while it was open. -/
def WAIVED : String := "open but for the waiver: "

/-- What the reason of an open cell of a waived line starts with, when the waiver does not
rest it: the deck has a rule for the part, and nothing shows that the rule holds. -/
def UNRESTED : String := "the waiver does not rest this cell: "

/-- What a cell says when its rule, or the `unless` of its line, reads a field that the part
leaves unstated. -/
def UNSTATED_WHY (field reader : String) : String := s!"{field} is unstated: its maker states none, and {reader} reads it"

/-- Whether a condition holds for a part. An `is` reads a key of the part, or of the one
part it joins under a name, which `fellows` holds. A key that is not there holds no name.
The answer rests on the keys of the design alone, so it is the same under every load case
of the card, and no case can switch a rule or a line off for another. -/
def Static.holds (part : Part) (fellows : Std.TreeMap String Part) : Static → Bool
  | .is called field name =>
    let owner := match called with
      | none => some part
      | some called => fellows.get? called
    match owner.bind (·.slot field) with
    | some (.key mine) => mine == name
    | _ => false
  | .and cs => cs.foldl (fun so c => so && c.holds part fellows) true
  | .or cs => cs.foldl (fun so c => so || c.holds part fellows) false
  | .not c => !c.holds part fellows

/-- The bytes that the reason of a refuted requirement has for its keys: what a reason prints,
less its first words, `the part is not what the rule requires: `, and the count of the keys
it does not name, ` and 999999 more`. -/
def REQUIRED_ROOM : Nat := MAX_TEXT - 56

/-- Why a part is not what a rule requires: each key the rule names and the name the part
has for it, or `unstated`, while they fit in what a reason prints beside its first words and
the count of the rest, and the rest are counted: a condition may name thousands, for
thousands of parts. The first key is always named, and a name of a key may be long, so the
reason holds its first characters. -/
def Part.refusal (part : Part) (fellows : Std.TreeMap String Part) (rule : Rule) : String := Id.run do
  let mut has := ""
  let mut said := 0
  for (called, field) in rule.asked do
    let owner := match called with
      | none => some part
      | some called => fellows.get? called
    let name := match owner.bind (·.slot field) with
      | some (.key mine) => toString (mine.take MAX_TEXT)
      | some (.unstated _) => UNSTATED
      | _ => "nothing"
    let one := s!"{(called.map (· ++ ".")).getD ""}{field} is {name}"
    if said > 0 && has.utf8ByteSize + 2 + one.utf8ByteSize > REQUIRED_ROOM then break
    has := has ++ (if said == 0 then "" else ", ") ++ one
    said := said + 1
  let more := if said < rule.asked.size then s!" and {rule.asked.size - said} more" else ""
  return s!"the part is not what the rule requires: {has}{more}"

/-- A computation that pays for each step, in units of work, from what is left, before it
takes the step. What is left is kept when the computation fails. -/
abbrev Paying := ExceptT String (StateM Nat)

/-- What the kernel says when the needs of a design would take it past its work. -/
def NEEDS_SPENT : String :=
  s!"deciding what the types need of this design would take the kernel past the {MAX_WORK} units of work it spends on one verdict"

def pay (cost : Nat) : Paying Unit := do
  let left ← get
  if left < cost then throw NEEDS_SPENT
  set (left - cost)

def paid (found : Except String α) : Paying α :=
  match found with
  | .ok x => pure x
  | .error why => throw why

/-- The range of an expression of a need over the ranges that `value` gives its fields, by
the four operations on the ends. The expression reads each field once, so this is the
range of its values and no wider. Each step pays what the same step of a tape pays
(`addWork`, `mulWork`, `divWork` in Tape.lean), and a number is held to `MAX_BITS`. -/
def Exact.range (value : Option String → String → Option Iv) : Nat → Exact → Paying Iv
  | 0, _ => throw "a need nests too deep"
  | _ + 1, .c x => do
    pay (copyWork 800 8000 8 (ratBits x))
    return Iv.pt x
  | _ + 1, .field part name => do
    let some x := value part name | throw s!"the part has no quantity {name}"
    pay (copyWork 700 4000 12 x.bits)
    return x
  | fuel + 1, .add terms => terms.foldlM (init := Iv.pt 0) fun sum term => do
    let x ← term.range value fuel
    pay (addWork sum.bits x.bits)
    paid (fits (sum.add x))
  | fuel + 1, .mul factors => factors.foldlM (init := Iv.pt 1) fun product factor => do
    let x ← factor.range value fuel
    pay (mulWork product.bits x.bits)
    paid (fits (product.mul x))
  | fuel + 1, .neg x => do
    let v ← x.range value fuel
    pay (copyWork 1100 7000 3 v.bits)
    return v.neg
  | fuel + 1, .div x y => do
    let a ← x.range value fuel
    let b ← y.range value fuel
    pay (divWork a.bits b.bits)
    paid (a.div b >>= fits)

/-- A finding for each need of its type that a part breaks (docs/format.md, Parts 9), and
the work that is left of `MAX_WORK` for the proofs. A need holds when the most its left
side reaches is at most the least its right side reaches, or under it for `lt`: for every
value the card and the design allow, and not only at one. The kernel decides it with exact
fractions and no hint. It is asked of a design that breaks no rule before it, so every
field is there and every quantity is more than zero. -/
def needs (parts : Array Part) : StateM Findings Nat := do
  let named := firsts parts (·.name)
  let bare := bareOf parts
  let mut left := MAX_WORK
  for part in parts do
    if part.kind.needs.isEmpty then continue
    let fellows := part.fellows named
    let touched := part.touched bare fellows
    let value (called : Option String) (field : String) : Option Iv :=
      let owner := match called with
        | none => some part
        | some called => fellows.get? called
      match owner.bind (·.slot field) with
      | some (.quantity input) => some input.range
      | _ => none
    for (need, k) in part.kind.needs.zipIdx do
      -- A need that names a field the part leaves unstated is not decided, and does not
      -- refuse the part: there is nothing to compare. Looking for such a field costs what
      -- reading each field of the need costs, and only a part that leaves a field unstated,
      -- or joins one that does, is looked at.
      if touched then
        let fields := need.low.fields ++ need.high.fields
        let look := 700 * fields.size
        if left < look then
          modify (·.push ⟨"limits", "design", part.name, NEEDS_SPENT⟩)
          return 0
        left := left - look
        if (part.lacks fellows fields).isSome then continue
      let sides : Paying (Iv × Iv) := do
        let low ← need.low.range value MAX_EXPRESSION
        let high ← need.high.range value MAX_EXPRESSION
        pay (orderWork low.bits high.bits)
        return (low, high)
      let (found, after) := Id.run (sides.run.run left)
      left := after
      match found with
      | .ok (low, high) =>
        unless (if need.strict then low.hi < high.lo else low.hi ≤ high.lo) do
          -- Once the findings are full a finding is only counted, and its text is not made:
          -- a design of many parts that each break a need costs no more than its needs.
          if (← get).kept.size ≥ MAX_FINDINGS then
            modify (·.push ⟨"parts.9", "design", part.name, ""⟩)
          else
            -- A number is printed whole when it is short. A long one would be cut from the
            -- finding, and takes long to write out.
            let shown (x : Rat) : String := if ratBits x ≤ 256 then toString x else s!"a number of {ratBits x} bits"
            let most := if low.lo == low.hi then shown low.hi else s!"up to {shown low.hi}"
            let least := if high.lo == high.hi then shown high.lo else s!"down to {shown high.lo}"
            modify (·.push ⟨"parts.9", "design", part.name,
              s!"breaks need {k + 1} of a {part.kind.name}: its left side, {most}, is not {if need.strict then "under" else "at most"} its right side, {least}, in SI units: {need.why}"⟩)
      | .error why =>
        if why == NEEDS_SPENT then
          modify (·.push ⟨"limits", "design", part.name, why⟩)
          return 0
        if (← get).kept.size ≥ MAX_FINDINGS then
          modify (·.push ⟨"parts.9", "design", part.name, ""⟩)
        else
          modify (·.push ⟨"parts.9", "design", part.name, s!"need {k + 1} of a {part.kind.name} is not decided: {why}"⟩)
  return left

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
  /-- Whether a waiver of the cell's line may rest the cell while it is open. The deck has no
  rule for the part: the line has no rule for it, or the rule's `where` holds nowhere in the
  ranges. Or the part leaves keys unstated, or a load case leaves out loads, and a hint names
  a completion of them under which the rule holds (`incomplete`). -/
  waivable : Bool := false
  /-- That completion. A waiver rests the cell only if it names no key and no load otherwise
  than a completion of a cell the card's waivers rest before it. -/
  completion : Option Completion := none

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

/-- What an incomplete cell is: refuted, or open with the completion of the first hint that
is a witness, if one is. -/
inductive Incomplete where
  | refuted
  | pending (completion : Option Completion)

/-- The cell of a rule for a part that leaves the keys of `unsaid` unstated, or under a load
case that leaves out the loads of `missing`. `under` is the case, or empty for a card with no
load case. Only the hints that name a completion are looked at.

The cell is refuted when no load is left out and, under each combination of the names of the
keys, the rule answers for the part and fails: its `requires` does not hold, or a hint names
that combination and a point that refutes the rule's tape written under it. The kernel goes
through the combinations itself, while there are at most `MAX_TRIED`, and stops at the first
that does not refute.

On a line the card waives, the cell is otherwise open with the completion of the first hint
that is a witness: one that `fits` the cell, under which the rule does not answer for the
part, or its `requires` holds, or the hint's partition proves the rule's tape written under
it. A waiver may rest the cell then, and only then (`cells`).

The tape a point refutes, for a rule with a `where`, is the one whose root is the rule's
inside the `where` and -1 outside it: a point refutes it only inside the `where`. A witness
meets what a complete cell must. The tape its partition proves has a root for each item of
the `where` before the rule's, so it proves the `where` and the rule over the whole box, as
the `/where` cell and the rule's cell are proved. A hint with no partition is a witness for a
rule with a `where` when, under its completion, the `where` holds nowhere in the box, as a
complete cell is rested. Each combination and each hint looked at is a step, and one for each
part of the rule's `when` and `requires`, a combination one for each key, and a hint one for
each key and load it names. Each hint is looked at once to refute, before the combinations,
and once more to find a witness. Each tape written
is the weight of the rule, twice with a `where`, and a step for each node. None when that
would come to more than `room` steps. Otherwise the cell, the steps it took, the work left
and `dsg` with the `dsg:` inputs of the tapes that refute it. -/
def incomplete (rule : Rule) (named : Std.TreeMap String Part) (loads : Loads) (part : Part) (unsaid : Array Unsaid)
    (missing : Array String) (under : String) (hints : Array Hint) (waived : Bool) (room left : Nat) (dsg : Std.TreeSet String) (floors : Floors) :
    StateM Caches (Option (Incomplete × Nat × Nat × Std.TreeSet String)) := do
  let looks := 1 + (rule.condition.map Static.size).getD 0 + (rule.requires.map Static.size).getD 0
  let weight := rule.weight * (if rule.ranges.isEmpty then 1 else 2)
  let hints := hints.filter (·.completion.isSome)
  -- The part and its fellows under a completion, and what the rule's tape reads there.
  let complete (c : Completion) : Part × Std.TreeMap String Part × Site :=
    let (named', loads') := c.onto named loads
    let part' := named'.getD part.name part
    (part', part'.fellows named', site named' loads' part' (some under))
  let write (here : Site) : Except String Tape := rule.tape here #[(rule.low, rule.high)] rule.strict rule.ranges
  let proving (here : Site) : Except String Tape := rule.tape here #[(rule.low, rule.high)] rule.strict (first := rule.ranges)
  let mut spent := 0
  let mut left := left
  let combinations := unsaid.foldl (fun n u => if n > MAX_TRIED then n else n * u.names.size) 1
  if missing.isEmpty && combinations ≤ MAX_TRIED then
    let mut broken := true
    let mut read := dsg
    -- The points of the hints, by the keys of their completions in order, so that a
    -- combination finds its own in one look however many hints the cell has. Each hint is
    -- looked at once here and charged as a hint is, and one whose completion gives a load or
    -- names the keys otherwise than one combination does is found by none.
    let ordered (keys : Array (String × String × String)) := keys.qsort (fun a b => compare a b == .lt)
    let mut pointed : Std.TreeMap (Array (String × String × String)) (Array Hint) := {}
    if rule.requires.isNone then
      for h in hints do
        let some c := h.completion | continue
        spent := spent + looks + c.keys.size + c.loads.size
        if spent > room then return none
        if h.point.isNone || !c.loads.isEmpty then continue
        let point := { h with partition := none }
        pointed := pointed.alter (ordered c.keys) fun
          | some found => some (found.push point)
          | none => some #[point]
    for n in [0:combinations] do
      spent := spent + looks + unsaid.size
      if spent > room then return none
      let keys := (unsaid.foldl (fun (out, n) u => (out.push (u.owner, u.field, u.names[n % u.names.size]!), n / u.names.size)) (#[], n)).1
      let c : Completion := { keys }
      let (part', fellows', here) := complete c
      unless rule.condition.all (·.holds part' fellows') do
        broken := false
        break
      if let some required := rule.requires then
        if required.holds part' fellows' then
          broken := false
          break
        continue
      let points := pointed.getD (ordered keys) #[]
      if points.isEmpty then
        broken := false
        break
      spent := spent + weight
      if spent > room then return none
      let .ok tape := write here | broken := false; break
      spent := spent + tape.nodes.size
      if spent > room then return none
      let (state, _, after) ← byHints tape points true left
      left := after
      unless state == .refuted do
        broken := false
        break
      read := tape.inputs.foldl (fun seen i => if i.label.startsWith "dsg:" then seen.insert i.label else seen) read
    if broken then return some (.refuted, spent, left, read)
  if !waived then return some (.pending none, spent, left, dsg)
  for h in hints do
    let some c := h.completion | continue
    spent := spent + looks + c.keys.size + c.loads.size
    if spent > room then return none
    unless c.fits part unsaid missing under floors do continue
    let (part', fellows', here) := complete c
    unless rule.condition.all (·.holds part' fellows') do return some (.pending (some c), spent, left, dsg)
    if let some required := rule.requires then
      if required.holds part' fellows' then return some (.pending (some c), spent, left, dsg)
      continue
    if h.partition.isNone && rule.ranges.isEmpty then continue
    spent := spent + weight
    if spent > room then return none
    if h.partition.isSome then
      let .ok tape := proving here | continue
      spent := spent + tape.nodes.size
      if spent > room then return none
      let (state, _, after) ← byHints tape #[{ h with point := none }] false left
      left := after
      if state == .proved then return some (.pending (some c), spent, left, dsg)
    else
      -- A `where` that holds nowhere in the box under the completion: the rule says nothing of
      -- the part so completed. The walk comes off the work, and the caches stay as they were.
      let .ok tape := rule.tape here rule.ranges | continue
      spent := spent + tape.nodes.size
      if spent > room then return none
      if let .ok ((found, after), _) := (tape.above left).run (← get) then
        left := after
        if found.isSome then return some (.pending (some c), spent, left, dsg)
  return some (.pending none, spent, left, dsg)

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
not put every load the rule reads on the part, its cell is incomplete (`incomplete`): a load
the card does not state is not taken as zero.

A step is counted before the work it stands for. A line of the grid for a part is a step
and one for each part of its `unless`. A rule of the line is a step, one for each part of
its `when` and one for each load it reads. For a rule that answers and reads loads, each
load case of the card is a step for each load the rule reads. Writing a tape is the weight
of its rule, and a tape is a step for each node. An incomplete cell counts as `incomplete`
says, and so does a hint for a line whose `unless` reads an unstated key. Then every rule of
a part's type is looked at once more for what it reads of the part: its look, and a step for
each field it reads.

`floors` are those of core.json (type rule 8), which hold a completion's loads as they hold
the card's. -/
def cells (rules : Rules) (card : Card) (parts : Array Part) (loads : Loads) (hints : Array Hint) (budget : Nat := MAX_WORK)
    (floors : Floors := {}) : StateM Caches (Except String Made) := do
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
  let bare := bareOf parts
  let touchedOf := (parts.zip fellowsOf).map fun (part, fellows) => part.touched bare fellows
  let answered : Std.TreeSet String := rules.rules.foldl (fun found r => found.insert r.mechanism) {}
  let cell (subject mechanism entry : String) (state : State) (reason : String := "") (waiver : Option (Nat × Waiver) := none) : Settled :=
    let claims := hintsFor subject mechanism entry
    { cell := { subject, mechanism, entry, state := (claims[0]?.map (·.state)).getD .undecided, tape := none,
                partition := none, point := none, which := none },
      state, reason := clip reason, waiver, hinted := !claims.isEmpty }
  let dsgOf (tape : Tape) (seen : Std.TreeSet String) : Std.TreeSet String :=
    tape.inputs.foldl (fun seen i => if i.label.startsWith "dsg:" then seen.insert i.label else seen) seen
  -- The item of a rule's `where` that holds nowhere in the box, if one does (`Tape.above` on
  -- the tape of the `where`): a waiver may then rest the rule's cell. It is asked only on a
  -- line the card waives, and what it takes comes off the work. The caches stay as they were.
  let nowhere (tape : Tape) (asked : Bool) (left : Nat) : StateM Caches (Option Nat × Nat) := do
    if !asked then return (none, left)
    match (tape.above left).run (← get) with
    | .ok ((found, after), _) => return (found, after)
    | .error _ => return (none, left)
  -- The loads of a list, for a reason: the first four by name, and how many more.
  let listed (names : Array String) : String :=
    " and no ".intercalate (names.toList.take 4) ++ (if names.size > 4 then s!" and {names.size - 4} more" else "")
  let mut out : Array Settled := #[]
  let mut ranges : Std.TreeSet (String × String × String) := {}
  let mut dsg : Std.TreeSet String := {}
  let mut steps := 0
  let mut left := budget
  let mut fixedKeys : Std.TreeMap (String × String) String := {}
  let mut fixedLoads : Std.TreeMap (String × String × String) Rat := {}
  for ((part, fellows), touched) in (parts.zip fellowsOf).zip touchedOf do
    -- A condition that names a key the part leaves unstated is not decided: nothing says
    -- whether it holds. The part is looked at for one only when it leaves a field unstated
    -- or joins a part that does.
    let lacks (fields : Array (Option String × String)) : Option String := if touched then part.lacks fellows fields else none
    for ask in asksOf.getD part.kind.name #[] do
      if out.size > MAX_CELLS then return .error over
      steps := steps + 1 + ((ask.excuse.bind id).map Static.size).getD 0 + lookOf.getD (ask.kind, ask.mechanism) 0
      if steps > MAX_STEPS then return .error long
      let pending (entry reason : String) (waivable : Bool) : Settled :=
        { cell part.name ask.mechanism entry .undecided reason with waivable }
      let waived := waivers.contains (part.name, ask.mechanism)
      -- The cells of the line are made as if the card waived nothing, but for the hints of
      -- completions, which are looked at only where it waives the line on the part. There,
      -- those of them that are open and waivable are rested once they are all made.
      let first := out.size
      if let some field := lacks (((ask.excuse.bind id).map Static.keys).getD #[]) then
        -- The `unless` of the line reads a key that is unstated, so nothing says whether the
        -- mechanism can arise for the part. The line is open, and no rule of it is run. On a
        -- line the card waives, a waiver may rest it under the completion of the first hint
        -- that names a name for each such key and under which the `unless` holds. Each hint
        -- is a step, and one for each key and load it names.
        let unsaid := part.unsaid fellows (((ask.excuse.bind id).map Static.keys).getD #[])
        let mut found : Option Completion := none
        if waived then
          for h in hintsFor part.name ask.mechanism "" do
            let some c := h.completion | continue
            steps := steps + 1 + ((ask.excuse.bind id).map Static.size).getD 0 + c.keys.size + c.loads.size
            if steps > MAX_STEPS then return .error long
            unless c.fits part unsaid #[] "" floors do continue
            let named' := (c.onto named loads).1
            let part' := named'.getD part.name part
            if ask.excuse.any fun condition => condition.all (·.holds part' (part'.fellows named')) then
              found := some c
              break
        out := out.push { pending "" (UNSTATED_WHY field "the `unless` of the line") found.isSome with completion := found }
      else if ask.excuse.any fun condition => condition.all (·.holds part fellows) then
        out := out.push (cell part.name ask.mechanism "" .notApplicable)
      else
        -- A rule answers when its `when` holds, and also when its `when` names a key that
        -- is unstated: nothing says that it does not apply, and its cells are then open.
        let answers := (rulesOf.getD (ask.kind, ask.mechanism) #[]).filter fun r =>
          (lacks ((r.condition.map Static.keys).getD #[])).isSome || r.condition.all (·.holds part fellows)
        if answers.isEmpty then
          let other := if answered.contains ask.mechanism then " on a part like this one" else ""
          out := out.push (pending "" s!"the deck has no rule for it{other}" true)
        for rule in answers do
          let tail := rule.entry
          -- A rule that reads a field the part leaves unstated has no answer of its own: it
          -- reads the field in a side, in its `where`, in its `when` or in its `requires`.
          -- Looking is a step for each field the rule reads. With a quantity left unstated
          -- each cell the rule would give is open, and no waiver rests it. With keys alone
          -- left unstated the cells are incomplete (`incomplete`).
          let mut unsaid : Array Unsaid := #[]
          let mut unstated := ""
          if touched then
            steps := steps + rule.fields.size
            if steps > MAX_STEPS then return .error long
            if let some field := part.lacks fellows rule.fields then
              unstated := UNSTATED_WHY field "the rule"
              if part.lacksQuantity fellows rule.fields then
                if rule.requires.isSome || rule.loads.isEmpty || loads.cases.isEmpty then
                  if out.size > MAX_CELLS then return .error over
                  out := out.push (pending tail unstated false)
                else
                  steps := steps + loads.cases.size
                  if steps > MAX_STEPS then return .error long
                  for under in loads.cases do
                    if out.size > MAX_CELLS then return .error over
                    out := out.push (pending s!"{tail}/{under}" unstated false)
                continue
              unsaid := part.unsaid fellows rule.fields
          -- One cell for each load case of the card, in the order of their names, for a rule
          -- that reads loads. Each case is looked up for each load the rule reads, which is
          -- what is counted. A card with no load case has one cell for such a rule, with every
          -- load it reads left out.
          let mut unders : Array (Option String) := #[none]
          if !rule.loads.isEmpty && !loads.cases.isEmpty then
            steps := steps + loads.cases.size * rule.loads.size
            if steps > MAX_STEPS then return .error long
            unders := loads.cases.map some
          for under in unders do
            if out.size > MAX_CELLS then return .error over
            let entry := match under with
              | some under => s!"{tail}/{under}"
              | none => tail
            -- A case that does not put every load the rule reads on the part leaves the cell
            -- incomplete. No load is taken as zero: a card that means none states a load of
            -- zero.
            let missing := match under with
              | some c => rule.loads.filter fun load => !loads.on.contains (part.name, load, c)
              | none => rule.loads
            if !unsaid.isEmpty || !missing.isEmpty then
              let why := if !unsaid.isEmpty then unstated else match under with
                | some c => s!"case {c} puts no {listed missing} on {part.name}, which the rule reads"
                | none => s!"the card puts no {listed missing} on {part.name}, which the rule reads"
              let some (found, spent, after, read) ← incomplete rule named loads part unsaid missing (under.getD "")
                  (hintsFor part.name ask.mechanism entry) waived (MAX_STEPS - steps) left dsg floors
                | return .error long
              steps := steps + spent
              left := after
              match found with
              | .refuted =>
                let why := if rule.requires.isSome then part.refusal fellows rule else ""
                out := out.push (cell part.name ask.mechanism entry .refuted why)
                dsg := read
              | .pending completion => out := out.push { pending entry why completion.isSome with completion }
              continue
            -- A rule that requires has one cell, with no tape and no hint: proved when its
            -- condition over keys holds for the part, and refuted when it does not, with each
            -- key it names and the name the part has for it.
            if let some required := rule.requires then
              if required.holds part fellows then out := out.push (cell part.name ask.mechanism tail .proved)
              else out := out.push (cell part.name ask.mechanism tail .refuted (part.refusal fellows rule))
              continue
            steps := steps + rule.weight * (if rule.ranges.isEmpty then 1 else 2)
            if steps > MAX_STEPS then return .error long
            let here := site named loads part under
            -- A tape that cannot be written leaves the cell open, and a waiver does not rest
            -- it: the deck must cover the part.
            if !rule.ranges.isEmpty then
              match rule.tape here rule.ranges with
              | .error why =>
                out := out.push (pending entry why false)
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
                  -- A point inside the range where the rule fails refutes it, as the tape whose
                  -- root is the rule's inside the `where` and -1 outside it shows there. Only
                  -- the points of the cell's hints are tried: a partition of that tape proves
                  -- nothing of a part that may be outside the range.
                  if let .ok inside := rule.tape here #[(rule.low, rule.high)] rule.strict rule.ranges then
                    steps := steps + inside.nodes.size
                    let points := (hintsFor part.name ask.mechanism entry).map ({ · with partition := none })
                    let (state, _, after) ← byHints inside points true left
                    left := after
                    if state == .refuted then
                      out := out.push (cell part.name ask.mechanism entry .refuted)
                      dsg := dsgOf inside dsg
                      continue
                  -- A range that holds nowhere in the box is a part the deck has no rule for,
                  -- and a waiver rests the cell. One that may hold somewhere does not.
                  let (outside, after) ← nowhere tape waived left
                  left := after
                  match outside with
                  | some k => out := out.push (pending entry s!"the rule holds only where {rule.whys[k]!}, and that holds nowhere in the ranges for {part.name}" true)
                  | none => out := out.push (pending entry s!"the range the rule holds in is not proved: {reason}" false)
                  continue
            match rule.tape here #[(rule.low, rule.high)] rule.strict with
            | .error why => out := out.push (pending entry why false)
            | .ok tape =>
              steps := steps + tape.nodes.size
              let (state, reason, after) ← byHints tape (hintsFor part.name ask.mechanism entry) true left
              left := after
              -- An open cell stays open under a waiver, whether its inequality is left
              -- undecided or a table has no value for the part: the deck must cover the part.
              out := out.push (cell part.name ask.mechanism entry state reason)
              if state == .proved || state == .refuted then dsg := dsgOf tape dsg
      -- A waiver rests a cell that would be open and that the deck has no rule for, or that a
      -- completion makes hold, and no other. A cell of the line that its rule proved is
      -- proved, and the waiver was not needed for it. One that its rule refuted is refuted:
      -- no waiver hides a refutation. One that the grid says cannot arise stays so. One whose
      -- rule is left undecided, or has no value for the part, stays open, and its reason says
      -- that the waiver does not rest it. The reason of a waived cell says what was open.
      --
      -- The completions of the cells rested hold together: each key of a part has one name
      -- and each load of a case one value, over the whole design. A cell whose completion
      -- names a key or a load otherwise than one rested before it is not rested.
      if let some (waiver, k) := waivers.get? (part.name, ask.mechanism) then
        for i in [first:out.size] do
          let some s := out[i]? | continue
          if s.state != .undecided then continue
          let agrees := s.completion.all fun c =>
            c.keys.all (fun (owner, field, name) => (fixedKeys.get? (owner, field)).all (· == name))
              && c.loads.all (fun (p, load, u, x) => (fixedLoads.get? (p, load, u)).all (· == x))
          if s.waivable && agrees then
            if let some c := s.completion then
              fixedKeys := c.keys.foldl (fun fixed (owner, field, name) => fixed.insert (owner, field) name) fixedKeys
              fixedLoads := c.loads.foldl (fun fixed (p, load, u, x) => fixed.insert (p, load, u) x) fixedLoads
            out := out.set! i { s with state := .waived, reason := clip (WAIVED ++ s.reason), waiver := some (k, waiver) }
          else out := out.set! i { s with reason := clip (UNRESTED ++ s.reason) }
  -- What a rule or a line of the grid reads of each part. Every rule of a part's type is
  -- looked at here, whatever the card waives, so the look is counted again. The look of a
  -- rule holds a step for each load it reads. A load is read by an expression of a rule
  -- that applies to the part it is on, and by nothing else.
  --
  -- It is worked out under the completions of the cells the waivers rest: a key they name
  -- has that name, and a load they give is on its part in its case. So a design that leaves
  -- out what the waiver answers for reads what the design that states it reads, and a rule
  -- that does not answer under the completion reads nothing.
  let named : Std.TreeMap String Part := fixedKeys.foldl (init := named) fun named (owner, field) name =>
    named.modify owner fun p => { p with slots := p.slots.insert field (.key name) }
  let parts := parts.map fun p => named.getD p.name p
  let fellowsOf := parts.map (·.fellows named)
  let put : Std.TreeMap String (Array (String × String)) :=
    ((fixedLoads.foldl (fun on key _ => on.insert key) (loads.on.foldl (fun on key _ => on.insert key) ({} : Std.TreeSet (String × String × String))))).foldl
      (init := {}) fun table (part, load, under) => table.alter part fun
        | some found => some (found.push (load, under))
        | none => some #[(load, under)]
  let rulesOfKind := grouped rules.rules (·.kind)
  let readOf : Std.TreeMap String Nat := rulesOfKind.map fun _ line => line.foldl (fun n r => n + r.look + r.fields.size) 0
  let mut read : Std.TreeSet (String × String) := {}
  let mut readLoads : Std.TreeSet (String × String) := {}
  for ((part, fellows), touched) in (parts.zip fellowsOf).zip touchedOf do
    steps := steps + 1 + readOf.getD part.kind.name 0
    if steps > MAX_STEPS then return .error long
    for ask in asksOf.getD part.kind.name #[] do
      for (called, field) in ((ask.excuse.bind id).map Static.keys).getD #[] do
        match called with
        | none => read := read.insert (part.name, field)
        | some called => if let some other := fellows.get? called then read := read.insert (other.name, field)
    for rule in rulesOfKind.getD part.kind.name #[] do
      -- A rule applies as it answers: where its `when` holds, and where its `when` names a
      -- key that the part leaves unstated.
      if (touched && (part.lacks fellows ((rule.condition.map Static.keys).getD #[])).isSome) || rule.condition.all (·.holds part fellows) then
        for load in rule.loads do readLoads := readLoads.insert (part.name, load)
        for (called, field) in rule.fields do
          match called with
          | none => read := read.insert (part.name, field)
          | some called => if let some other := part.joined called then read := read.insert (other, field)
  for part in parts do
    for field in part.kind.fields do
      if out.size > MAX_CELLS then return .error over
      -- A field left unstated has no value that something could fail to check, and no cell.
      unless (field.kind matches .parts ..) || read.contains (part.name, field.name) || (part.slot field.name matches some (.unstated _)) do
        out := out.push (cell part.name UNREAD field.name .undecided s!"no rule of the deck reads {part.name}.{field.name}, so nothing checks it")
    -- A load that nothing reads, once for each case that puts it on the part. Its entry is
    -- `LOAD/CASE`, which no field's entry is: the name of a field holds no `/`.
    for (load, under) in put.getD part.name #[] do
      if out.size > MAX_CELLS then return .error over
      unless readLoads.contains (part.name, load) do
        out := out.push (cell part.name UNREAD s!"{load}/{under}" .undecided
          s!"no rule of the deck reads the load {load} that {if under.isEmpty then "the card" else s!"case {under}"} puts on {part.name}, so nothing checks it")
  if out.size > MAX_CELLS then return .error over
  -- No two cells have one key: `readRules` and `readParts` refuse what could make two, and
  -- this holds the list to it whatever they let through.
  unless distinct (out.map fun s => (s.cell.subject, s.cell.mechanism, s.cell.entry)) do
    return .error "two cells of this design would have one subject, mechanism and entry, and the kernel prints no key twice"
  let made := out.foldl (fun made s => made.insert (s.cell.subject, s.cell.mechanism, s.cell.entry)) ranges
  return .ok { cells := said out, ignored := (hints.filter fun h => !made.contains (h.subject, h.mechanism, h.entry)).size,
               dsgInputs := dsg.size, work := MAX_WORK - left }

end Petra
