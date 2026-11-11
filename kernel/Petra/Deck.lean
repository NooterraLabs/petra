/-
A deck of rules (docs/deck.md, format petra-rules/0): rows, types, the grid and rules, read
as petra/deck.py and petra/grid.py read them, and a rule as a tape for one part.

A rule is kept as a list of steps, each built from earlier ones: its `let` names, the rows
it applies and both sides of its inequalities. A tape for one part under one load case
takes the steps its roots read, in order, and writes each distinct node once.

Reading a deck is bounded before it starts. `steps` counts, from the file alone, the size of
its JSON and the size of a row again for each time a rule applies it, and `readRules`
refuses a deck of more than `MAX_READ`. The reader then does a bounded amount of work for
each value it reads: every name is found through a table, and no table is built for the
names a rule could use but does not. So the time and the memory of reading follow that
count, and with it the bytes of the file.
-/
import Std.Data.HashMap
import Std.Data.HashSet
import Petra.Quantity
import Petra.Files

namespace Petra
open Lean (Json)

/-- One side of a table: the input it reads and its places. A key has a place for each of
its names. A quantity is read at listed values and nowhere else, or in bands, each closed
at its upper end when `upper` and at its lower end when not. Only the last band may have no
upper end. -/
inductive Side where
  | named (input : String) (names : Array String)
  | listed (input : String) (values : Array Rat)
  | banded (input : String) (bands : Array (Rat × Option Rat)) (upper : Bool)

def Side.input : Side → String
  | .named input _ | .listed input _ | .banded input _ _ => input

def Side.places : Side → Nat
  | .named _ names => names.size
  | .listed _ values => values.size
  | .banded _ bands _ => bands.size

/-- Cells by place, `cells[down][across]`, with one column when the table has one side.
None is a cell the standard leaves empty. -/
structure Table where
  down : Side
  across : Option Side
  cells : Array (Array (Option Rat))

/-- What a row takes: a quantity of a dimension, or a key, one of a few names. `known` holds
the names of a key again, to find one without going through the list. -/
inductive Taken where
  | quantity (dim : Dim)
  | key (names : Array String) (known : Std.HashSet String)

/-- An equation keeps its cases as written, each a condition and an expression: a rule that
applies the row reads them again with the row's inputs bound. -/
inductive Body where
  | cases (cases : Array (Option Json × Json))
  | table (table : Table)

structure Row where
  id : String
  dim : Dim
  takes : Array (String × Taken)
  body : Body

/-- What a field of a type is: a quantity, a key, or the parts of a type that it joins, one
for each name in `names`. A load is a quantity. `known` holds the names of a key again. -/
inductive FieldKind where
  | quantity (dim : Dim) (signed whole : Bool) (least : Option Rat)
  | key (names : Array String) (known : Std.HashSet String)
  | parts (kind : String) (names : Array String)

/-- A field of a type. `oneOf` is what the kernel says of a part that gives a key a name
it lacks: the list of its names, made once here and not again for each such part. -/
structure Field where
  name : String
  kind : FieldKind
  oneOf : String := ""

def Field.dim (f : Field) : Option Dim :=
  match f.kind with
  | .quantity dim .. => some dim
  | _ => none

/-- A type. `field` and `load` find a field and a load by name. `called` finds, for each
name a rule may call a joined part by, the type of that part, the field that joins it and
its place among the parts the field joins. -/
structure Kind where
  name : String
  fields : Array Field
  loads : Array Field
  field : Std.HashMap String Field := {}
  load : Std.HashMap String Field := {}
  called : Std.HashMap String (String × String × Nat) := {}
  deriving Inhabited

/-- A condition on what a part is, not on how large. -/
inductive Static where
  | is (field name : String) | loaded (load : String)
  | and (cs : Array Static) | or (cs : Array Static) | not (c : Static)

/-- The key fields a condition on a part reads. -/
def Static.keys : Static → Array String
  | .is field _ => #[field]
  | .loaded _ => #[]
  | .and cs | .or cs => cs.foldl (fun out c => out ++ c.keys) #[]
  | .not c => c.keys

/-- How many parts a condition has: what looking at it for one part costs, in steps. -/
def Static.size : Static → Nat
  | .is _ _ | .loaded _ => 1
  | .and cs | .or cs => cs.foldl (fun n c => n + c.size) 1
  | .not c => 1 + c.size

/-- A line of the grid. `excuse` is none for a line that always asks. Otherwise it holds
the condition under which the mechanism cannot arise, or none when it never arises. -/
structure Ask where
  kind : String
  mechanism : String
  excuse : Option (Option Static)

/-- How a rule gives a side of a table its value: a step, a name of the row's key, or a key
field of the part, or of the part `part` names, through a map from its names to the row's.
No map is the map of each name to itself. -/
inductive Chosen where
  | value (step : Nat)
  | fixed (name : String)
  | field (part : Option String) (field : String) (names : Option (Array (String × String)))

/-- One step of a rule. A `node` is a node of a tape over earlier steps. The others are what
a part gives it: a quantity field of the part or of the part `part` names, a load, a table
at the place the part's values choose, and a row with its inputs bound. A row reads every
input it binds, used or not, as petra/grid.py does. -/
inductive Step where
  | node (node : Node)
  | field (part : Option String) (name : String)
  | load (name : String)
  | table (table : Table) (down : Chosen) (across : Option Chosen)
  | row (binds : Array Nat) (value : Nat)
  deriving Inhabited

def Chosen.reads : Chosen → Array Nat
  | .value step => #[step]
  | _ => #[]

/-- What finding a side's place costs beyond the side's own places: the entries of a map. -/
def Chosen.weight : Chosen → Nat
  | .field _ _ (some names) => names.size
  | _ => 0

def Step.reads : Step → Array Nat
  | .node n => n.reads
  | .field .. | .load _ => #[]
  | .table _ down across => down.reads ++ (across.map Chosen.reads).getD #[]
  | .row binds value => binds.push value

/-- What a step costs to write for one part: itself and each step it reads. A pick renames
every order of its conditions, and a table looks at every cell. -/
def Step.weight : Step → Nat
  | .node (.pick cases) => 1 + cases.size + 2 * orders cases
  | .node n => 1 + n.reads.size
  | .field .. | .load _ => 1
  | .table grid down across =>
    1 + grid.down.places + grid.cells.foldl (fun n line => n + line.size) 0 + down.weight + (across.map Chosen.weight).getD 0
  | .row binds _ => 1 + binds.size

/-- An answer to one line of the grid: `low <= high`, read where every pair of `ranges` is
in order. `fields` and `loads` are what its roots read, through its names and its rows, each
once. `weight` is what its steps cost to write for one part, and `look` what it costs to
see whether the rule is for a part and which loads the part must carry. -/
structure Rule where
  id : String
  kind : String
  mechanism : String
  condition : Option Static
  steps : Array Step
  weight : Nat
  look : Nat
  ranges : Array (Nat × Nat)
  low : Nat
  high : Nat
  fields : Array (Option String × String)
  loads : Array String

/-- What the rule's cells are entered under: its id from after its last `/`. -/
def Rule.entry (rule : Rule) : String := (rule.id.splitOn "/").getLast!

structure Rules where
  name : String
  kinds : Array Kind
  asks : Array Ask
  rules : Array Rule

/-- The steps that `roots` read, directly or through other steps, as `Tape.needed`. -/
def reach (steps : Array Step) (roots : Array Nat) : Array Bool := Id.run do
  let mark (need : Array Bool) (ids : Array Nat) := ids.foldl (fun need i => need.setIfInBounds i true) need
  let mut need := mark (Array.replicate steps.size false) roots
  for k in [0:steps.size] do
    let i := steps.size - 1 - k
    if need[i]! then need := mark need steps[i]!.reads
  return need

-- Reading expressions.

/-- What a name means where an expression is read. In a rule: a field of the part or of a
part it joins. In a row: an input, bound to a step. -/
inductive Meaning where
  | field (dim : Dim) (part : Option String) (name : String)
  | key (names : Array String) (known : Std.HashSet String) (part : Option String) (name : String)
  | bound (dim : Dim) (step : Nat)

inductive Named where
  | pending (body : Json) | busy | done (step : Nat) (dim : Dim)

/-- Where an expression is read. In a row, `bound` holds its inputs, and there is no type:
a row has no loads, no rows and no `let`. In a rule, `kind` is the type the rule is for, and
`kinds` every type by its name. -/
structure Scope where
  bound : Std.HashMap String Meaning := {}
  kind : Option Kind := none
  kinds : Std.HashMap String Kind := {}
  rows : Std.HashMap String Row := {}

def Scope.rule (scope : Scope) : Bool := scope.kind.isSome

/-- What a name means here: an input of the row, a quantity or a key of the type, or
`NAME.FIELD` for a field of a part the type joins. The name is looked up in the tables of
the types, so a type that joins many parts of a type of many fields costs a rule nothing
for the names it does not use. -/
def Scope.find (scope : Scope) (name : String) : Option Meaning :=
  let meaning (f : Field) (part : Option String) : Option Meaning :=
    match f.kind with
    | .quantity dim .. => some (.field dim part f.name)
    | .key names known => some (.key names known part f.name)
    | .parts .. => none
  match scope.bound.get? name with
  | some found => some found
  | none => do
    let kind ← scope.kind
    match kind.field.get? name with
    | some f => meaning f none
    | none =>
      match name.splitOn "." with
      | [part, inner] => do
        let (other, _, _) ← kind.called.get? part
        meaning (← (← scope.kinds.get? other).field.get? inner) (some part)
      | _ => none

structure Draft where
  steps : Array Step := #[]
  lets : Std.HashMap String Named := {}

abbrev Reading := StateT Draft (Except String)

/-- A step more. A value of the file that is read makes at most four steps of a rule: a
power is a root, a power, a one and a quotient. So a rule of a deck within `MAX_READ` never
has four times that many, and the test holds the reader to the count whatever it does. -/
def push (step : Step) : Reading Nat := do
  let place := (← get).steps.size
  if place ≥ 4 * MAX_READ then throw s!"reading a rule takes more than {4 * MAX_READ} steps"
  modify fun d => { d with steps := d.steps.push step }
  return place

def put (node : Node) (dim : Dim) : Reading (Nat × Dim) := do return (← push (.node node), dim)

/-- What a name of `let` stands at, in a rule. The table of the names is looked at and let
go here: a reader that kept hold of it while it read on would have it copied at the next
name it adds. -/
def letOf (scope : Scope) (name : String) : Reading (Option Named) := do
  if scope.rule then return (← get).lets.get? name else return none

def has (j : Json) (key : String) : Bool := (j.getObjVal? key).toOption.isSome

def filled (j : Json) (key : String) : Bool :=
  match j.getObjVal? key with
  | .ok (.str s) => !s.isEmpty
  | _ => false

def members (j : Json) : Except String (Array (String × Json)) := do return (← j.getObj?).toArray

/-- Refuses a key that an object of a deck does not have. A deck holds no key the kernel
does not read: a key it skipped would be a misspelled one, read as if it were left out. The
key is cut to `MAX_TEXT`, as a finding is. -/
def within (j : Json) (allowed : List String) : Except String Unit := do
  for (key, _) in ← members j do
    unless allowed.contains key do throw s!"{clip key} is not a key here: it has {", ".intercalate allowed}"

/-- The first item that is in the list a second time, or none when each is there once. The
table is asked whether it holds the item before the item is put in, and never while: a
table that is still being asked is copied whole when it is added to, and a list of many
names would then cost the square of its length. -/
def twice [BEq α] [Hashable α] (items : Array α) : Option α :=
  (items.foldl (fun (seen, found) x =>
    if found.isSome then (seen, found) else if seen.contains x then (seen, some x) else (seen.insert x, none))
    (({} : Std.HashSet α), (none : Option α))).2

def distinct [BEq α] [Hashable α] (names : Array α) : Bool := (twice names).isNone

/-- The names as a table. -/
def setOf (names : Array String) : Std.HashSet String := names.foldl (·.insert ·) {}

/-- The value of a key that an object of a deck must have. -/
def need (j : Json) (key : String) : Except String Json :=
  match j with
  | .obj members =>
    match members.get? key with
    | some value => pure value
    | none => throw s!"it has no `{key}`"
  | _ => throw "it is not an object"

/-- Each item once, in the order of its first place. -/
def once [BEq α] [Hashable α] (items : Array α) : Array α :=
  (items.foldl (fun (seen, out) x => if seen.contains x then (seen, out) else (seen.insert x, out.push x))
    (({} : Std.HashSet α), #[])).2

/-- A name a deck gives a field, a load, a joined part or a `let`: letters, digits and `_`,
not starting with a digit, and at most `MAX_NAME` of them. So `a.Fy` is always a field of a
joined part and a name is never a number. -/
def identifier (name : String) : Except String Unit :=
  match name.toList with
  | c :: rest =>
    if (c.isAlpha || c == '_') && rest.all (fun c => c.isAlphanum || c == '_') then short "a name" name
    else throw s!"{clip name} is not a name: write letters, digits and _"
  | [] => throw "a name is empty"

/-- How a rule binds a key that a row takes: to a key field whose names are all names of the
row's key, to `["key", NAME]`, or to `["by", FIELD, {its name: the row's name}]`. A field
with more names than the row's key has one the key lacks, so the names of a field are
gone through only when they are no more than the key's, which the row holds. -/
def chosen (scope : Scope) (known : Std.HashSet String) (j : Json) : Except String Chosen := do
  let keyField (name : String) : Except String (Array String × Option String × String) :=
    match scope.find name with
    | some (.key names _ part field) => pure (names, part, field)
    | _ => throw s!"{clip name} is not a key field"
  let how := "a key is bound to a key field, to [\"key\", NAME] or to [\"by\", FIELD, {...}]"
  match j with
  | .str name =>
    let (names, part, field) ← keyField name
    unless names.size ≤ known.size && names.all known.contains do throw s!"{name} has names the row lacks"
    return .field part field none
  | .arr items =>
    if items.size > 3 then throw how
    match items.toList with
    | [.str "key", .str name] =>
      unless known.contains name do throw s!"{clip name} is not a name of the row's key"
      return .fixed name
    | [.str "by", .str name, map] =>
      let (names, part, field) ← keyField name
      let pairs ← (← members map).mapM fun (mine, its) => do return (mine, ← its.getStr?)
      let given := setOf (pairs.map (·.1))
      unless pairs.size == names.size && names.all given.contains && pairs.all (fun p => known.contains p.2) do
        throw s!"`by` gives one of the row's names for each name of {name}"
      return .field part field (some pairs)
    | _ => throw how
  | _ => throw how

mutual

/-- An expression of docs/deck.md as a step and its dimension, as `_Reader.expr` and
`_Binder.expr` read one. A name of `let` is read where it is first used, and a row where it
is applied, so `fuel` bounds the nesting through both. -/
def expr (scope : Scope) : Nat → Json → Reading (Nat × Dim)
  | 0, _ => throw "an expression nests too deep"
  | fuel + 1, .str name => do
    if name == "pi" then return (← put .pi {})
    match scope.find name with
    | some (.field dim part field) => return (← push (.field part field), dim)
    | some (.bound dim step) => return (step, dim)
    | some (.key ..) => throw s!"{name} is a key, and only a table reads a key"
    | none =>
      match ← letOf scope name with
      | some (.done step dim) => return (step, dim)
      | some .busy => throw s!"`let` defines {name} by itself"
      | some (.pending body) =>
        modify fun d => { d with lets := d.lets.insert name .busy }
        let (step, dim) ← expr scope fuel body
        modify fun d => { d with lets := d.lets.insert name (.done step dim) }
        return (step, dim)
      | none =>
        match if name.length ≤ MAX_NUMBER_CHARS then decimal name.toList else none with
        | some x => put (.c x) {}
        | none => throw s!"{String.ofList (name.toList.take 40)} is not a number, and nothing here has that name"
  | fuel + 1, .arr items => do
    let plain (what : String) (dim : Dim) : Reading Unit :=
      unless dim == {} do throw s!"{what} must be a plain number"
    let some (Json.str op) := items[0]? | throw "an expression starts with the name of its operator"
    match op, (items.toList.drop 1) with
    | "q", [.str x, .str unit] =>
      let (value, dim) ← amount (x ++ " " ++ unit)
      put (.c value) dim
    | "pow", [base, exponent] =>
      let (x, dim) ← expr scope fuel base
      let number ← match exponent with
        | .str written =>
          -- The names of `let` are asked for here and not kept from before the base was read:
          -- a table that is held twice is copied when the base adds a name to it.
          if written == "pi" || (scope.find written).isSome || (← letOf scope written).isSome then pure none
          else match if written.length ≤ MAX_NUMBER_CHARS then decimal written.toList else none with
            | some n => pure (some n)
            | none => throw s!"{String.ofList (written.toList.take 40)} is not a number, and nothing here has that name"
        | _ => pure none
      match number with
      | some n =>
        if n.den ≤ 2 then
          if n.num.natAbs > MAX_EXPONENT then throw s!"a power of {n} is over the budget of {MAX_EXPONENT}"
          let root ← if n.den == 1 then pure x else push (.node (.sqrt x))
          let raised ← push (.node (.pow root (Int.ofNat n.num.natAbs)))
          if n > 0 then return (raised, dim.times n)
          put (.div (← push (.node (.c 1))) raised) (dim.times n)
        else
          plain s!"the base of the power {n}" dim
          let product ← push (.node (.mul #[← push (.node (.c n)), ← push (.node (.ln x))]))
          put (.exp product) {}
      | none =>
        let (y, exponentDim) ← expr scope fuel exponent
        plain "an exponent" exponentDim
        plain "the base of a power with an exponent that varies" dim
        let product ← push (.node (.mul #[y, ← push (.node (.ln x))]))
        put (.exp product) {}
    | "load", [.str name] =>
      let some kind := scope.kind | throw "a row reads no load"
      match (kind.load.get? name).bind Field.dim with
      | some dim => return (← push (.load name), dim)
      | none => throw s!"the type takes no load {clip name}"
    | "row", [.str id, binds] =>
      unless scope.rule do throw "a row applies no row"
      let some row := scope.rows.get? id | throw s!"{clip id} is not a row of the deck"
      -- Each input is bound once: as many names as the row takes, and each of them given.
      let written ← members binds
      let given : Std.HashMap String Json := written.foldl (fun table (name, value) => table.insert name value) {}
      unless written.size == row.takes.size && row.takes.all (fun t => given.contains t.1) do
        throw s!"{id} takes {", ".intercalate (row.takes.map (·.1)).toList}, and the rule binds {", ".intercalate (written.map (·.1)).toList}"
      let mut names : Std.HashMap String Meaning := {}
      let mut bound : Array Nat := #[]
      let mut keys : Std.HashMap String Chosen := {}
      for (name, taken) in row.takes do
        let some value := given.get? name | throw s!"{id}: {name} is not bound"
        match taken with
        | .quantity dim =>
          let (step, its) ← expr scope fuel value
          unless its == dim do throw s!"{id}: the rule binds {name} to another dimension than the row takes"
          names := names.insert name (.bound dim step)
          bound := bound.push step
        | .key _ known => keys := keys.insert name (← chosen scope known value)
      let value ← match row.body with
        | .cases written => cases { bound := names } row.dim fuel written
        | .table table =>
          let pick (side : Side) : Reading Chosen :=
            match keys.get? side.input, names.get? side.input with
            | some key, _ => pure key
            | none, some (.bound _ step) => pure (.value step)
            | _, _ => throw s!"{id}: {side.input} is not bound"
          push (.table table (← pick table.down) (← table.across.mapM pick))
      return (← push (.row bound value), row.dim)
    | _, args =>
      let parts ← args.mapM (expr scope fuel)
      let ids := (parts.map (·.1)).toArray
      let dims := parts.map (·.2)
      let same : Reading Dim :=
        match dims with
        | d :: rest => if rest.all (· == d) then pure d else throw s!"{clip op} of different dimensions"
        | [] => throw s!"{clip op} of nothing"
      match op, ids.toList, dims with
      | "add", _ :: _, _ => put (.add ids) (← same)
      | "min", _ :: _, _ => put (.min ids) (← same)
      | "max", _ :: _, _ => put (.max ids) (← same)
      | "sub", [a, b], _ => put (.add #[a, ← push (.node (.neg b))]) (← same)
      | "mul", _ :: _, _ => put (.mul ids) (dims.foldl (· + ·) {})
      | "div", [a, b], [da, db] => put (.div a b) (da - db)
      | "neg", [a], [d] => put (.neg a) d
      | "abs", [a], [d] => put (.abs a) d
      | "sqrt", [a], [d] => put (.sqrt a) (d.times (mkRat 1 2))
      | "exp", [a], [d] => do plain "the argument of exp" d; put (.exp a) {}
      | "ln", [a], [d] => do plain "the argument of ln" d; put (.ln a) {}
      | _, _, _ => throw s!"{clip op} with {args.length} arguments is not in the language"
  | _ + 1, _ => throw "an expression is a number, a name or [operator, ...]"

/-- A condition of a case: an order between two expressions of one dimension, or conditions
joined. `ge` and `gt` are `le` and `lt` the other way round. -/
def cond (scope : Scope) : Nat → Json → Reading Cond
  | 0, _ => throw "a condition nests too deep"
  | fuel + 1, j => do
    let order (flip strict : Bool) (a b : Json) : Reading Cond := do
      let (x, dx) ← expr scope fuel a
      let (y, dy) ← expr scope fuel b
      unless dx == dy do throw "a condition compares two dimensions"
      let (x, y) := if flip then (y, x) else (x, y)
      return if strict then .lt x y else .le x y
    match (← j.getArr?).toList with
    | [.str "le", a, b] => order false false a b
    | [.str "lt", a, b] => order false true a b
    | [.str "ge", a, b] => order true false a b
    | [.str "gt", a, b] => order true true a b
    | .str "and" :: c :: rest => return .and (← (c :: rest).toArray.mapM (cond scope fuel))
    | .str "or" :: c :: rest => return .or (← (c :: rest).toArray.mapM (cond scope fuel))
    | [.str "not", c] => return .not (← cond scope fuel c)
    | _ => throw "not a condition: write le, lt, ge, gt, and, or, not"

/-- The value of an equation: the first case whose condition holds, each of dimension `dim`.
One case that holds otherwise is its value. No case at all is a pick of none, which has no
value. -/
def cases (scope : Scope) (dim : Dim) : Nat → Array (Option Json × Json) → Reading Nat
  | 0, _ => throw "an expression nests too deep"
  | fuel + 1, written => do
    let mut found : Array (Option Cond × Nat) := #[]
    for (condition, value) in written do
      let condition ← condition.mapM (cond scope fuel)
      let (step, its) ← expr scope fuel value
      unless its == dim do throw s!"case {found.size + 1} gives another dimension than the row"
      found := found.push (condition, step)
    match found[0]? with
    | some (none, step) => return step
    | _ => push (.node (.pick found))

end

/-- A condition on a part: `["is", FIELD, NAME]` on a key field of the type itself,
`["loaded", LOAD]`, and `and`, `or`, `not` of these. -/
def static (scope : Scope) : Nat → Json → Except String Static
  | 0, _ => throw "a condition nests too deep"
  | fuel + 1, j => do
    match (← j.getArr?).toList with
    | [.str "is", .str field, .str name] =>
      match scope.find field with
      | some (.key _ known none _) =>
        unless known.contains name do throw s!"{clip name} is not a name of {field}"
        return .is field name
      | _ => throw s!"{clip field} is not a key field of the type"
    | [.str "loaded", .str load] =>
      unless scope.kind.any (·.load.contains load) do throw s!"the type takes no load {clip load}"
      return .loaded load
    | .str "and" :: c :: rest => return .and (← (c :: rest).toArray.mapM (static scope fuel))
    | .str "or" :: c :: rest => return .or (← (c :: rest).toArray.mapM (static scope fuel))
    | [.str "not", c] => return .not (← static scope fuel c)
    | _ => throw "not a condition on a part: write is, loaded, and, or, not"

/-- The deepest an expression may nest, counted through the names of `let` it reads and the
rows it applies. A file nests at most `MAX_NESTING` deep, so a row or a rule alone is within
it, and a chain of names that each read the next is cut here. -/
def MAX_EXPRESSION : Nat := 1024

-- Reading a deck.

/-- An anchor names its standard and its clause, and may name an equation, a table and a
page. Each is a text. -/
def anchored (j : Json) : Except String Unit := do
  let anchor ← need j "anchor"
  (within anchor ["standard", "clause", "equation", "table", "page"]).mapError ("anchor: " ++ ·)
  unless filled anchor "standard" && filled anchor "clause" do throw "the anchor lacks its standard or its clause"
  for key in ["equation", "table", "page"] do
    if has anchor key && (text anchor key).toOption.isNone then throw s!"the anchor's {key} is not a text"

/-- A list a key may leave out. -/
def listed (j : Json) (key : String) : Except String (Array Json) := if has j key then list j key else pure #[]

def readTable (j : Json) (takes : Array (String × Taken)) (gives : Dim) : Except String Table := do
  within j ["down", "across", "cells", "unit", "rises", "falls"]
  let side (a : Json) : Except String Side := do
    let input ← text a "by"
    match takes.find? (·.1 == input) with
    | none => throw s!"the table reads {clip input}, which the row does not take"
    | some (_, .key names _) =>
      within a ["by"]
      return .named input names
    | some (_, .quantity dim) =>
      within a (if has a "bands" then ["by", "bands", "closed"] else ["by", "at"])
      if has a "bands" == has a "at" then throw s!"the side that reads {input} has `bands` or `at`"
      let upper ← match a.getObjVal? "closed" with
        | .error _ | .ok (.str "upper") => pure true
        | .ok (.str "lower") => pure false
        | _ => throw "`closed` is upper or lower"
      let value (x : Json) : Except String Rat := do
        let (v, its) ← amount (← x.getStr?)
        unless its == dim do throw s!"the side that reads {input} has a value of another dimension"
        return v
      if has a "at" then
        let values ← (← list a "at").mapM value
        unless (values.zip (values.extract 1 values.size)).all (fun (x, y) => x < y) do
          throw s!"the values {input} is read at are in order, each once"
        return .listed input values
      let bands ← (← list a "bands").mapM fun band => do
        let ends ← band.getArr?
        if ends.size != 2 then throw "a band is a pair"
        match ends.toList with
        | [lo, .null] => return (← value lo, none)
        | [lo, hi] => return (← value lo, some (← value hi))
        | _ => throw "a band is a pair"
      for ((lo, hi), n) in bands.zipIdx do
        let inOrder := match hi, bands[n + 1]? with
          | none, next => next.isNone
          | some hi, some (next, _) => lo < hi && hi ≤ next
          | some hi, none => lo < hi
        unless inOrder do
          throw s!"the bands of {input} are pairs, the lower end first, in order and none over another; only the last may have no upper end"
      return .banded input bands upper
  let down ← side (← need j "down")
  let across ← (j.getObjVal? "across").toOption.mapM side
  let sides := #[down.input] ++ (across.map (·.input)).toArray
  unless sides.size == takes.size && takes.all (fun t => sides.contains t.1) do
    throw "each input of a table is read by one of its sides, and by one only"
  let unit ← match j.getObjVal? "unit" with
    | .ok (.str unit) => pure (some unit)
    | .ok .null | .error _ => pure none
    | _ => throw "unit is not text"
  let cell (x : Json) : Except String (Option Rat) := do
    if x.isNull then return none
    let written := strip (← x.getStr?).toList
    let whole := match unit with
      | some unit => if written.contains ' ' then written else written ++ ' ' :: unit.toList
      | none => written
    let (v, its) ← amount (String.ofList whole)
    unless its == gives do throw "a cell is of another dimension than the row gives"
    return some v
  let lines ← (← list j "cells").mapM fun line =>
    if across.isSome then do (← line.getArr?).mapM cell else do return #[← cell line]
  unless lines.size == down.places && lines.all (·.size == (across.map Side.places).getD 1) do
    throw "the cells are one line for each place down, with one cell for each place across"
  let rises ← (← listed j "rises").mapM (·.getStr?)
  let falls ← (← listed j "falls").mapM (·.getStr?)
  -- A table has at most two sides, so each list is gone through at most twice.
  unless (rises ++ falls).all sides.contains && !sides.any (fun s => rises.contains s && falls.contains s) do
    throw "`rises` and `falls` name sides of the table, and no side is in both"
  return { down, across, cells := lines }

def readRow (j : Json) : Except String Row := do
  let id ← text j "id"
  let row : Except String Row := do
    within j ["id", "anchor", "gives", "takes", "is", "cases", "jumps", "table"]
    unless (["is", "cases", "table"].filter (has j)).length == 1 do throw "a row has one of `is`, `cases` and `table`"
    anchored j
    let gives ← need j "gives"
    (within gives ["name", "dim", "what"]).mapError ("gives: " ++ ·)
    let _ ← text gives "name"
    let dim ← dimension (← text gives "dim")
    let mut takes : Array (String × Taken) := #[]
    let mut seen : Std.HashSet String := {}
    for t in ← list j "takes" do
      let name ← text t "name"
      if seen.contains name then throw s!"{clip name} is taken twice"
      seen := seen.insert name
      if has t "one_of" then
        let names ← texts t "one_of"
        if names.isEmpty || !distinct names || has t "dim" || has t "range" then
          throw s!"{clip name} is a key: it has `one_of`, a list of different names, and no `dim` or `range`"
        (within t ["name", "what", "one_of"]).mapError (s!"{clip name}: " ++ ·)
        takes := takes.push (name, .key names (setOf names))
      else
        (within t ["name", "what", "dim", "range"]).mapError (s!"{clip name}: " ++ ·)
        let its ← dimension (← text t "dim")
        match ← (← texts t "range").toList.mapM amount with
        | [(lo, loDim), (hi, hiDim)] =>
          unless loDim == its && hiDim == its && lo ≤ hi do throw s!"the range of {clip name} is two values of its dimension, the lower first"
        | _ => throw s!"the range of {clip name} is two values"
        takes := takes.push (name, .quantity its)
    if has j "table" then
      if has j "jumps" then throw "a table has no jumps: it steps at every band"
      return { id, dim, takes, body := .table (← readTable (← need j "table") takes dim) }
    if takes.any (fun t => t.2 matches .key ..) then throw "an equation takes no key: only a table reads one"
    let written ← if has j "cases" then list j "cases" else do pure #[Json.mkObj [("is", ← need j "is")]]
    let mut found : Array (Option Json × Json) := #[]
    for (entry, n) in written.zipIdx do
      within entry ["when", "is"]
      let condition := (entry.getObjVal? "when").toOption
      if condition.isNone && n + 1 != written.size then throw "only the last case may leave `when` out"
      found := found.push (condition, ← need entry "is")
    -- Read the cases once with each input as a step of its own, for their names and dimensions.
    let mut names : Std.HashMap String Meaning := {}
    for ((name, taken), n) in takes.zipIdx do
      if let .quantity its := taken then names := names.insert name (.bound its n)
    let _ ← (cases { bound := names } dim MAX_EXPRESSION found).run { steps := takes.map fun t => .field none t.1 }
    for jump in ← listed j "jumps" do
      (within jump ["cases", "why"]).mapError ("a jump: " ++ ·)
      -- The different numbers of the list, up to three of them: a jump names two.
      let ends := (← (← list jump "cases").mapM (·.getNat?)).foldl
        (fun (seen : Array Nat) n => if seen.size > 2 || seen.contains n then seen else seen.push n) #[]
      unless ends.size == 2 && ends.all (fun n => 1 ≤ n && n ≤ found.size) && filled jump "why" do
        throw "a jump names two of the row's cases by number, from 1, and says why"
    return { id, dim, takes, body := .cases found }
  row.mapError (s!"row {clip id}: " ++ ·)

def readField (load : Bool) (j : Json) : Except String Field := do
  let name ← text j "name"
  let field : Except String Field := do
    within j (if load then ["name", "what", "dim", "least"] else ["name", "what", "dim", "least", "one_of", "type", "as", "signed", "whole"])
    unless (["dim", "one_of", "type"].filter (has j)).length == 1 && filled j "what" do
      throw "it has `what` and one of `dim`, `one_of` and `type`"
    identifier name
    if has j "one_of" then
      within j ["name", "what", "one_of"]
      let names ← texts j "one_of"
      if names.isEmpty || !distinct names then throw "`one_of` is a list of different names"
      return { name, kind := .key names (setOf names), oneOf := s!"is one of: {", ".intercalate names.toList}" }
    if has j "type" then
      within j ["name", "what", "type", "as"]
      let names ← if has j "as" then texts j "as" else pure #[name]
      if names.isEmpty || !distinct names then throw "`as` names each part once"
      names.forM identifier
      return { name, kind := .parts (← text j "type") names }
    within j ["name", "what", "dim", "least", "signed", "whole"]
    let dim ← dimension (← text j "dim")
    let least ← if has j "least" then do
        let (x, its) ← amount (← text j "least")
        unless its == dim do throw "its least value is of another dimension"
        pure (some x)
      else pure none
    let flag (key : String) : Except String Bool :=
      match j.getObjVal? key with
      | .error _ => pure false
      | .ok (.bool b) => pure b
      | _ => throw s!"{key} is true or false"
    let whole ← flag "whole"
    if whole && dim != {} then throw "a count is a plain number"
    return { name, kind := .quantity dim (← flag "signed") whole least }
  field.mapError (s!"field {clip name}: " ++ ·)

def readKind (j : Json) : Except String Kind := do
  let name ← text j "type"
  let kind : Except String Kind := do
    within j ["type", "what", "fields", "loads"]
    let _ ← (text j "what").mapError fun _ => "it has `what`, a text"
    let fields ← (← list j "fields").mapM (readField false)
    let loads ← (← listed j "loads").mapM (readField true)
    let joined := fields.flatMap fun f => match f.kind with
      | .parts _ names => names
      | _ => #[]
    unless distinct (fields.map (·.name)) && distinct (loads.map (·.name)) && distinct joined do
      throw "two fields, two loads or two joined parts have one name"
    let called : Std.HashMap String (String × String × Nat) := fields.foldl (init := {}) fun table f =>
      match f.kind with
      | .parts other names => names.zipIdx.foldl (fun table (part, k) => table.insert part (other, f.name, k)) table
      | _ => table
    return { name, fields, loads, called,
             field := fields.foldl (fun table f => table.insert f.name f) {},
             load := loads.foldl (fun table f => table.insert f.name f) {} }
  kind.mapError (s!"type {clip name}: " ++ ·)

/-- The mechanism of the cell the kernel makes for a field that nothing reads. No line of
the grid has this name, so no cell of a rule has the key of such a cell. -/
def UNREAD : String := "unread"

def readAsk (kinds : Std.HashMap String Kind) (rows : Std.HashMap String Row) (j : Json) : Except String Ask := do
  let mechanism ← text j "mechanism"
  let ask : Except String Ask := do
    short "the name of a mechanism" mechanism
    within j ["type", "mechanism", "what", "anchor", "unless"]
    if mechanism == UNREAD then throw s!"no mechanism is named {UNREAD}: the cell of a field that nothing reads has that name"
    anchored j
    let _ ← (text j "what").mapError fun _ => "it has `what`, a text"
    let name ← text j "type"
    let some kind := kinds.get? name | throw s!"{clip name} is not a type of the deck"
    let excuse ← match j.getObjVal? "unless" with
      | .error _ | .ok .null => pure none
      | .ok said => do
        (within said ["why", "when"]).mapError ("unless: " ++ ·)
        let _ ← text said "why"
        pure (some (← (said.getObjVal? "when").toOption.mapM (static { kind := some kind, kinds, rows } MAX_EXPRESSION)))
    return { kind := name, mechanism, excuse }
  ask.mapError (s!"grid {clip mechanism}: " ++ ·)

def readRule (kinds : Std.HashMap String Kind) (rows : Std.HashMap String Row) (asks : Std.HashMap (String × String) Ask) (j : Json) :
    Except String Rule := do
  let id ← text j "id"
  let rule : Except String Rule := do
    short "the id of a rule" id
    within j ["id", "type", "mechanism", "anchor", "says", "when", "let", "where", "le"]
    anchored j
    unless filled j "says" do throw "a rule says what it states"
    let name ← text j "type"
    let mechanism ← text j "mechanism"
    let some kind := kinds.get? name | throw s!"{clip name} is not a type of the deck"
    match (asks.get? (name, mechanism)).map (·.excuse) with
    | none => throw s!"the grid does not ask {clip mechanism} of {name}"
    | some (some none) => throw s!"the grid says {mechanism} never arises for {name}"
    | _ => pure ()
    let scope : Scope := { kind := some kind, kinds, rows }
    let lets ← if has j "let" then members (← need j "let") else pure #[]
    for (name, _) in lets do
      identifier name
      if name == "pi" || (scope.find name).isSome then throw s!"`let` names {name}, which has a meaning already"
    let pair (sides : Json) (what : String) : Reading (Nat × Nat) := do
      let ends ← sides.getArr?
      if ends.size != 2 then throw s!"{what} has two sides"
      let [low, high] := ends.toList | throw s!"{what} has two sides"
      let (x, dx) ← expr scope MAX_EXPRESSION low
      let (y, dy) ← expr scope MAX_EXPRESSION high
      unless dx == dy do throw s!"{what} compares two dimensions"
      return (x, y)
    let read : Reading ((Nat × Nat) × Array (Nat × Nat)) := do
      let main ← pair (← need j "le") "`le`"
      let written ← listed j "where"
      if has j "where" && written.isEmpty then
        throw "`where` has at least one item: a rule that holds everywhere leaves it out"
      let ranges ← written.mapM fun range => do
        (within range ["le", "why"]).mapError ("where: " ++ ·)
        let _ ← text range "why"
        pair (← need range "le") "`where`"
      for (name, _) in lets do
        let _ ← expr scope MAX_EXPRESSION (.str name)
      return (main, ranges)
    let (((low, high), ranges), draft) ← read.run { lets := Std.HashMap.ofList (lets.map fun (name, body) => (name, Named.pending body)).toList }
    let condition ← (j.getObjVal? "when").toOption.mapM (static scope MAX_EXPRESSION)
    let need := reach draft.steps (#[low, high] ++ ranges.flatMap fun (a, b) => #[a, b])
    let used := ((draft.steps.zip need).filter (·.2)).map (·.1)
    let fields := used.flatMap fun
      | .field part name => #[(part, name)]
      | .table _ down across => #[some down, across].filterMap fun
        | some (.field part name _) => some (part, name)
        | _ => none
      | _ => #[]
    let loads := once (used.filterMap fun
      | .load name => some name
      | _ => none)
    return { id, kind := name, mechanism, condition, steps := draft.steps,
             weight := draft.steps.foldl (fun n step => n + step.weight) 0,
             look := 1 + (condition.map Static.size).getD 0 + loads.size, ranges, low, high,
             fields := once (fields ++ ((condition.map Static.keys).getD #[]).map (none, ·)), loads }
  rule.mapError (s!"rule {clip id}: " ++ ·)

/-- How many characters of a text are one step to read. -/
def TEXT_STEP : Nat := 8

/-- The size of a text: two, and one more for each `TEXT_STEP` characters. A rule that
applies a row reads the row's texts again. A text that is a number becomes a step of the
rule each time, which the kernel keeps, so it counts as two where a list counts as one. And
a text that is a number or a name is gone through character by character each time. -/
def textSize (s : String) : Nat := 2 + s.length / TEXT_STEP

/-- The size of a JSON value: one for a number, a flag and null, `textSize` for a text, and
for a list or an object one more than the sizes of what it holds. A key is not counted. A
file nests at most `MAX_NESTING` deep. -/
partial def valueSize (j : Json) : Nat :=
  match j with
  | .arr items => items.foldl (fun n item => n + valueSize item) 1
  | .obj members => members.toArray.foldl (fun n (_, value) => n + valueSize value) 1
  | .str s => textSize s
  | _ => 1

/-- The sizes of the rows that the lists `["row", ID, ...]` inside a value name, one for
each such list: what reading the rows again costs a rule that applies them. -/
partial def applied (rows : Std.HashMap String Nat) (j : Json) : Nat :=
  match j with
  | .arr items =>
    let own := if items.size == 3 then
        match items[0]!, items[1]! with
        | .str "row", .str id => rows.getD id 0
        | _, _ => 0
      else 0
    items.foldl (fun n item => n + applied rows item) own
  | .obj members => members.toArray.foldl (fun n (_, value) => n + applied rows value) 0
  | _ => 0

/-- The steps reading a deck takes (docs/deck.md, "The size of a deck"): the size of the
whole file, and for each list `["row", ID, ...]` anywhere inside an item of `rules`, the
size of the first row of the deck whose `id` is `ID`. A rule reads a row again each time it
applies it, and everything else once. The count is of the file as it stands, read or not:
`petra/grid.py` makes the same count, so the two refuse the same decks. -/
def readingSteps (j : Json) : Nat :=
  let rows : Std.HashMap String Nat := ((list j "rows").toOption.getD #[]).foldl (init := {}) fun table row =>
    match text row "id" with
    | .ok id => if table.contains id then table else table.insert id (valueSize row)
    | .error _ => table
  ((list j "rules").toOption.getD #[]).foldl (fun n rule => n + applied rows rule) (valueSize j)

/-- A deck of rules from its file, as `read_deck` in petra/grid.py. -/
def readRules (j : Json) : Except String Rules := do
  within j ["format", "name", "about", "rows", "types", "grid", "rules"]
  let count := readingSteps j
  if count > MAX_READ then
    throw s!"reading this deck takes {count} steps, over the budget of {MAX_READ}: a value of the file is one step, a text two or more, and a rule that applies a row takes the row's steps again"
  let name ← text j "name"
  let found ← (← list j "rows").mapM readRow
  unless distinct (found.map (·.id)) do throw "two rows have one id"
  let rows := Std.HashMap.ofList (found.map fun r => (r.id, r)).toList
  let read ← (← list j "types").mapM readKind
  unless distinct (read.map (·.name)) do throw "two types have one name"
  let kinds : Std.HashMap String Kind := read.foldl (fun table kind => table.insert kind.name kind) {}
  for kind in read do
    for f in kind.fields do
      if let .parts other _ := f.kind then
        match kinds.get? other with
        | some its =>
          unless its.called.isEmpty do
            throw s!"{kind.name}.{f.name}: it names parts of {other}, whose own fields name parts"
        | none => throw s!"{kind.name}.{f.name}: {clip other} is not a type of the deck"
  let asks ← (← list j "grid").mapM (readAsk kinds rows)
  unless distinct (asks.map fun a => (a.kind, a.mechanism)) do throw "the grid asks one mechanism of one type twice"
  let asked : Std.HashMap (String × String) Ask := asks.foldl (fun table a => table.insert (a.kind, a.mechanism) a) {}
  let rules ← (← list j "rules").mapM (readRule kinds rows asked)
  unless distinct (rules.map (·.id)) do throw "two rules have one id"
  if let some (kind, mechanism, entry) := twice (rules.map fun r => (r.kind, r.mechanism, r.entry)) then
    throw s!"two rules answer {mechanism} of {kind} with ids that end in {entry} after the last /, so their cells would have one entry"
  return { name, kinds := read, asks, rules }

-- A rule as a tape.

/-- What a tape reads of one part under one load case: a quantity field and a key field of
the part, or of the part that `part` names, and a load. -/
structure Site where
  quantity : Option String → String → Option TapeInput
  key : Option String → String → Option String
  load : String → Option TapeInput

/-- A tape being written. `seen` finds a node that is there already, so one quantity is one
node, and a pick that compares it twice orders it once. `labelled` finds an input by its
label. -/
structure Writing where
  inputs : Array TapeInput := #[]
  nodes : Array Node := #[]
  seen : Std.HashMap Node Nat := {}
  labelled : Std.HashMap String Nat := {}

abbrev Write := StateT Writing (Except String)

/-- The place of a node, written once. The tape is taken and given back in one step, so
adding a node does not copy the nodes before it. -/
def node (n : Node) : Write Nat := modifyGet fun w =>
  match w.seen.get? n with
  | some i => (i, w)
  | none =>
    let i := w.nodes.size
    (i, { w with nodes := w.nodes.push n, seen := w.seen.insert n i })

def input (i : TapeInput) : Write Nat := do
  let k ← modifyGet fun w =>
    match w.labelled.get? i.label with
    | some k => (k, w)
    | none =>
      let k := w.inputs.size
      (k, { w with inputs := w.inputs.push i, labelled := w.labelled.insert i.label k })
  node (.s k)

/-- The first case that holds, or none when there is no case. One case that holds otherwise
is its value. A pick holds at most `MAX_ORDERS` orders, as one that a file carries. -/
def pickOf (cases : Array (Option Cond × Nat)) : Write (Option Nat) :=
  match cases[0]? with
  | none => pure none
  | some (none, value) => pure (some value)
  | some _ =>
    let count := orders cases
    if count > MAX_ORDERS then
      throw s!"an equation or a table compares {count} orders here, over the budget of {MAX_ORDERS} for one pick"
    else some <$> node (.pick cases)

/-- The places of one side that the part can be at, each with the condition that it is
there: one place for a key, every listed value, every band. -/
def places (site : Site) (side : Side) (how : Chosen) (ids : Array Nat) : Write (Array (Nat × Option Cond)) := do
  let key (names : Array String) (name : String) : Write (Array (Nat × Option Cond)) :=
    match names.findIdx? (· == name) with
    | some i => pure #[(i, none)]
    | none => throw s!"{name} is not a name of {side.input}"
  match side, how with
  | .named _ names, .fixed name => key names name
  | .named _ names, .field part field map =>
    let some mine := site.key part field | throw s!"the part has no key {field}"
    match map with
    | none => key names mine
    | some pairs =>
      let some (_, its) := pairs.find? (·.1 == mine) | throw s!"{mine} has no name in {side.input}"
      key names its
  | .listed _ values, .value step =>
    values.mapIdxM fun n v => do
      let c ← node (.c v)
      return (n, some (.and #[.le ids[step]! c, .le c ids[step]!]))
  | .banded _ bands upper, .value step =>
    bands.mapIdxM fun n (lo, hi) => do
      let x := ids[step]!
      let l ← node (.c lo)
      let above : Cond := if upper then .lt l x else .le l x
      match hi with
      | none => return (n, some above)
      | some hi =>
        let h ← node (.c hi)
        return (n, some (.and #[above, if upper then .le x h else .lt x h]))
  | _, _ => throw s!"{side.input} is read by a value of the wrong kind"

/-- The value of a table for the part, or none where it gives nothing: a pick over the
places down, each a pick over the places across, with the empty cells left out. -/
def tableOf (site : Site) (table : Table) (down : Chosen) (across : Option Chosen) (ids : Array Nat) : Write (Option Nat) := do
  let columns ← match table.across, across with
    | some side, some how => places site side how ids
    | none, none => pure #[(0, none)]
    | _, _ => throw "a table's sides and what it is read by differ"
  let mut lines : Array (Option Cond × Nat) := #[]
  for (i, condition) in ← places site table.down down ids do
    let there ← columns.filterMapM fun (k, c) => do
      match (table.cells[i]!)[k]! with
      | some x => return some (c, ← node (.c x))
      | none => return none
    if let some line ← pickOf there then lines := lines.push (condition, line)
  pickOf lines

/-- The tape of a rule for one part: for each pair of `pairs` a root, the first less the
second. An error is a reason the rule has no value for the part. -/
def Rule.tape (rule : Rule) (site : Site) (pairs : Array (Nat × Nat)) : Except String Tape := do
  let need := reach rule.steps (pairs.flatMap fun (a, b) => #[a, b])
  let write : Write (Array Nat) := do
    let mut ids : Array Nat := Array.replicate rule.steps.size 0
    for (step, i) in rule.steps.zipIdx do
      if need[i]! then
        let id ← match step with
          | .node (.pick cases) => do
            let some id ← pickOf (cases.map fun (c, v) => (c.map (·.map (ids[·]!)), ids[v]!)) | throw "an equation has no case"
            pure id
          | .node n => node (n.map (ids[·]!))
          | .field part name => do
            let some value := site.quantity part name | throw s!"the part has no {name}"
            input value
          | .load name => do
            let some value := site.load name | throw s!"the part has no load {name}"
            input value
          | .table table down across => do
            let some id ← tableOf site table down across ids | throw "a table gives nothing here"
            pure id
          | .row _ value => pure ids[value]!
        ids := ids.set! i id
    pairs.mapM fun (low, high) => do node (.add #[ids[low]!, ← node (.neg ids[high]!)])
  let (roots, written) ← write.run {}
  return { inputs := written.inputs, nodes := written.nodes, roots }

end Petra
