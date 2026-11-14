/-
Exact check of a clearance certificate between two parts with flat and round faces.

The claim: no point of part A is nearer than `clearance` to any point of part B.

A part is a list of solids in one frame, every number an exact rational:

  a block with its faces square to the axes, less round holes that run right through it
  along a coordinate axis
  a solid round bar along a coordinate axis
  a convex solid with flat faces: every point with g . x <= h for each face

The certificate gives hints and witnesses. A hint turns a round face into flat ones on the
safe side: sides for a bar, each of which must hold the whole bar, and for a hole a polygon
that turns left at every corner with every corner inside the hole's circle. So each part
lies inside a union of convex pieces, each a list of faces. A witness for a piece P of A and
a piece Q of B is two lists of weights, none negative. The weighted faces of P add up to
n . x <= a on P. Those of Q must add up to -n . y <= -b on Q. Then every x of P and y of Q
are at least (b - a) / |n| apart, and the check asks b - a >= 0 and
(b - a)^2 >= clearance^2 * |n|^2. Every pair of pieces needs a witness.

This is `check_clearance.py` in Lean. `proofs/` proves what `check` returns.
-/
import Certify.Read

open Lean (Json)

namespace Certify.Clearance

/-- A flat face: the points with gx*x + gy*y + gz*z <= h. -/
structure Face where
  gx : Rat
  gy : Rat
  gz : Rat
  h : Rat

inductive Axis where
  | x | y | z

/-- The face gu*u + gv*v + gt*t <= h, where t runs along the axis and (u, v) across it:
(x, y) for z, (y, z) for x and (z, x) for y. -/
def Axis.face (a : Axis) (gu gv gt h : Rat) : Face :=
  match a with
  | .z => ⟨gu, gv, gt, h⟩
  | .x => ⟨gt, gu, gv, h⟩
  | .y => ⟨gv, gt, gu, h⟩

/-- A round hole that the certificate opens, with the polygon given for it. -/
structure Hole where
  axis : Axis
  cu : Rat
  cv : Rat
  radius : Rat
  polygon : Array (Rat × Rat)

/-- A solid with its hint. A box holds only the holes that the hint opens: a hole with no
polygon is left filled and is not read. -/
inductive Solid where
  | polytope (faces : List Face)
  | cylinder (axis : Axis) (cu cv radius lo hi : Rat) (sides : List (Rat × Rat × Rat))
  | box (lo hi : Rat × Rat × Rat) (holes : List Hole)

structure Witness where
  a : Int
  b : Int
  mu : List (Int × Rat)
  nu : List (Int × Rat)

structure Cert where
  clearance : Rat
  partA : List Solid
  partB : List Solid
  witnesses : List Witness

/-! ## The pieces -/

/-- Corner `i` of a polygon, counted round and round. -/
def corner (P : Array (Rat × Rat)) (i : Nat) : Rat × Rat :=
  P.getD (i % P.size) (0, 0)

/-- The face of the edge from corner `i` to corner `i + 1`, keeping the side to its right.
It tests that corner `i` is inside the hole's circle and that the polygon turns left at
corner `i + 1`. -/
def holeEdge (n : Nat) (hole : Hole) (i : Nat) : Check Face := do
  let p := corner hole.polygon i
  let q := corner hole.polygon (i + 1)
  let w := corner hole.polygon (i + 2)
  need ((p.1 - hole.cu) * (p.1 - hole.cu) + (p.2 - hole.cv) * (p.2 - hole.cv) ≤ hole.radius * hole.radius)
    s!"a corner of a polygon given for a hole of the box {n} is outside the hole"
  need ((q.1 - p.1) * (w.2 - q.2) - (q.2 - p.2) * (w.1 - q.1) > 0)
    s!"a polygon given for a hole of the box {n} is not convex and counter-clockwise"
  .ok (hole.axis.face (-(q.2 - p.2)) (q.1 - p.1) 0 (-(q.2 - p.2) * p.1 + (q.1 - p.1) * p.2))

def holeCut (n : Nat) (hole : Hole) : Check (List Face) := do
  need (hole.radius > 0) s!"a hole of the box {n} has no radius"
  need (hole.polygon.size ≥ 3) s!"a polygon given for a hole of the box {n} has under three corners"
  collect (holeEdge n hole) (List.range hole.polygon.size)

/-- Every way to take one member from each list, the first list turning slowest. -/
def product : List (List α) → List (List α)
  | [] => [[]]
  | l :: ls => l.flatMap fun a => (product ls).map (a :: ·)

def cylinderSide (n : Nat) (axis : Axis) (cu cv radius : Rat) (side : Rat × Rat × Rat) : Check Face := do
  need (side.2.2 ≥ 0 ∧ side.2.2 * side.2.2 ≥ radius * radius * (side.1 * side.1 + side.2.1 * side.2.1))
    s!"a side given for the cylinder {n} cuts into it"
  .ok (axis.face side.1 side.2.1 0 (side.2.2 + side.1 * cu + side.2.1 * cv))

def boxBase (lo hi : Rat × Rat × Rat) : List Face :=
  [⟨-1, 0, 0, -lo.1⟩, ⟨1, 0, 0, hi.1⟩, ⟨0, -1, 0, -lo.2.1⟩, ⟨0, 1, 0, hi.2.1⟩,
   ⟨0, 0, -1, -lo.2.2⟩, ⟨0, 0, 1, hi.2.2⟩]

/-- The convex pieces whose union holds solid `n`. -/
def solidPieces (n : Nat) (s : Solid) : Check (List (List Face)) :=
  match s with
  | .polytope faces => do
    need (faces.length ≥ 1) s!"solid {n} has no face"
    .ok [faces]
  | .cylinder axis cu cv radius lo hi sides => do
    need (radius > 0 ∧ lo < hi) s!"solid {n} is no cylinder"
    let sideFaces ← collect (cylinderSide n axis cu cv radius) sides
    .ok [axis.face 0 0 (-1) (-lo) :: axis.face 0 0 1 hi :: sideFaces]
  | .box lo hi holes => do
    need (lo.1 < hi.1 ∧ lo.2.1 < hi.2.1 ∧ lo.2.2 < hi.2.2) s!"solid {n} is no box"
    let cuts ← collect (holeCut n) holes
    .ok ((product cuts).map (boxBase lo hi ++ ·))

/-- The convex pieces whose union holds a part. Their order is part of the format. -/
def pieces (solids : List Solid) : Check (List (List Face)) := do
  let ps ← collectIdx solidPieces solids 0
  .ok ps.flatten

/-! ## The witnesses -/

/-- The weighted sum of faces of a piece: (n, a) with n . x <= a on the piece. -/
def combine (P : Array Face) : List (Int × Rat) → Check (Rat × Rat × Rat × Rat)
  | [] => .ok (0, 0, 0, 0)
  | e :: rest => do
    need (e.2 ≥ 0) "a weight is negative"
    match (if 0 ≤ e.1 then P[e.1.toNat]? else none) with
    | none => .error "a weight names no face"
    | some f =>
      let s ← combine P rest
      .ok (s.1 + e.2 * f.gx, s.2.1 + e.2 * f.gy, s.2.2.1 + e.2 * f.gz, s.2.2.2 + e.2 * f.h)

/-- What a witness shows: the gap b - a and |n|^2. -/
structure Shown where
  gap : Rat
  nn : Rat

def piece? (A : Array (Array Face)) (i : Int) : Option (Array Face) :=
  if 0 ≤ i then A[i.toNat]? else none

def checkWitness (A B : Array (Array Face)) (c : Rat) (w : Witness) : Check Shown :=
  match piece? A w.a, piece? B w.b with
  | some P, some Q => do
    let s ← combine P w.mu
    let t ← combine Q w.nu
    need (s.1 + t.1 = 0 ∧ s.2.1 + t.2.1 = 0 ∧ s.2.2.1 + t.2.2.1 = 0)
      s!"the two sides of the witness for pieces {w.a} and {w.b} do not face each other"
    let gap := -t.2.2.2 - s.2.2.2
    let nn := s.1 * s.1 + s.2.1 * s.2.1 + s.2.2.1 * s.2.2.1
    need (nn > 0 ∨ gap > 0) s!"the witness for pieces {w.a} and {w.b} has no direction"
    need (gap ≥ 0 ∧ gap * gap ≥ c * c * nn)
      s!"the witness for pieces {w.a} and {w.b} does not show the clearance"
    .ok ⟨gap, nn⟩
  | _, _ => .error "a witness names no piece"

/-- The witness that shows least so far, as (gap^2, |n|^2). It is only printed. -/
def lesser (least : Option (Rat × Rat)) (s : Shown) : Option (Rat × Rat) :=
  if s.nn > 0 then
    match least with
    | none => some (s.gap * s.gap, s.nn)
    | some l => if s.gap * s.gap * l.2 < l.1 * s.nn then some (s.gap * s.gap, s.nn) else some l
  else least

/-- Check each witness in order and mark its pair of pieces as seen. -/
def markAll (A B : Array (Array Face)) (c : Rat) :
    List Witness → Array Bool → Option (Rat × Rat) → Check (Array Bool × Option (Rat × Rat))
  | [], seen, least => .ok (seen, least)
  | w :: ws, seen, least => do
    let s ← checkWitness A B c w
    markAll A B c ws (seen.setIfInBounds (w.a.toNat * B.size + w.b.toNat) true) (lesser least s)

structure Out where
  clearance : Rat
  piecesA : Nat
  piecesB : Nat
  least : Option (Rat × Rat)

def check (cert : Cert) : Check Out := do
  need (cert.clearance ≥ 0) "the clearance is negative"
  let la ← pieces cert.partA
  let lb ← pieces cert.partB
  let A := (la.map List.toArray).toArray
  let B := (lb.map List.toArray).toArray
  let r ← markAll A B cert.clearance cert.witnesses (Array.replicate (A.size * B.size) false) none
  let missing := (List.range (A.size * B.size)).filter fun k => !(r.1.getD k false)
  match missing with
  | [] => .ok ⟨cert.clearance, A.size, B.size, r.2⟩
  | k :: _ =>
    .error s!"{missing.length} pairs of pieces have no witness, the first [({k / B.size}, {k % B.size})]"

/-! ## Reading the file -/

def parseAxis (j : Json) : Check Axis :=
  match j with
  | .str "x" => .ok .x
  | .str "y" => .ok .y
  | .str "z" => .ok .z
  | _ => notInFormat "an axis is x, y or z"

def pyList (ks : List String) : String :=
  "[" ++ ", ".intercalate (ks.map fun k => s!"'{k}'") ++ "]"

def unknown (j : Json) (allowed : List String) : Check (List String) := do
  .ok ((← keys j).filter fun k => !allowed.contains k)

def parseFace (j : Json) : Check Face := do
  match ← list j with
  | [a, b, c, h] => .ok ⟨← num a, ← num b, ← num c, ← num h⟩
  | _ => notInFormat "a face is four numbers"

def parseHole (n : Nat) (e : Json × Json) : Check (Option Hole) :=
  match e.2 with
  | .null => .ok none
  | polygon => do
    let extra ← unknown e.1 ["axis", "centre", "radius"]
    need extra.isEmpty s!"a hole of the box {n} has a key this format does not know: {pyList extra}"
    let axis ← parseAxis (← field e.1 "axis")
    let radius ← num (← field e.1 "radius")
    let c ← pair (← field e.1 "centre")
    let P ← collect pair (← list polygon)
    .ok (some ⟨axis, c.1, c.2, radius, P.toArray⟩)

def parseSolid (n : Nat) (e : Json × Json) : Check Solid := do
  let solid := e.1
  let hint := match e.2 with
    | .null => Json.mkObj []
    | h => h
  let kind ← field solid "kind"
  let allowed ← match kind with
    | .str "polytope" => pure ["kind", "halfspaces"]
    | .str "cylinder" => pure ["kind", "axis", "centre", "radius", "lo", "hi"]
    | .str "box" => pure ["kind", "lo", "hi", "holes"]
    | _ => .error s!"solid {n} is of no known kind"
  let extra ← unknown solid allowed
  need extra.isEmpty s!"solid {n} has a key this format does not know: {pyList extra}"
  let hintExtra ← unknown hint ["sides", "holes"]
  need hintExtra.isEmpty s!"the hint for solid {n} has a key this format does not know"
  match kind with
  | .str "polytope" =>
    .ok (.polytope (← collect parseFace (← list (← field solid "halfspaces"))))
  | .str "cylinder" =>
    let axis ← parseAxis (← field solid "axis")
    let radius ← num (← field solid "radius")
    let c ← pair (← field solid "centre")
    let lo ← num (← field solid "lo")
    let hi ← num (← field solid "hi")
    let sides ← match field? hint "sides" with
      | none => pure []
      | some s => do collect triple (← list s)
    .ok (.cylinder axis c.1 c.2 radius lo hi sides)
  | _ =>
    let lo ← triple (← field solid "lo")
    let hi ← triple (← field solid "hi")
    let holes ← match field? solid "holes" with
      | none => pure []
      | some h => list h
    let given ← match field? hint "holes" with
      | none => pure (holes.map fun _ => Json.null)
      | some g => list g
    need (given.length = holes.length) s!"one polygon, or null, for each hole of the box {n} is needed"
    let opened ← collect (parseHole n) (holes.zip given)
    .ok (.box lo hi (opened.filterMap id))

def parsePart (solids hints : Json) : Check (List Solid) := do
  let ss ← list solids
  let hs ← list hints
  need (hs.length = ss.length) "one hint, or null, for each solid is needed"
  collectIdx parseSolid (ss.zip hs) 0

def parseWeights (j : Json) : Check (List (Int × Rat)) := do
  collect (fun e => do
    match ← list e with
    | [i, m] => .ok (← int i, ← num m)
    | _ => notInFormat "a weight is a face and a number") (← list j)

def parseWitness (j : Json) : Check Witness := do
  .ok ⟨← int (← field j "a"), ← int (← field j "b"), ← parseWeights (← field j "mu"),
    ← parseWeights (← field j "nu")⟩

def parse (j : Json) : Check Cert := do
  match j with
  | .obj _ => pure ()
  | _ => notInFormat "an object is needed"
  match field? j "format" with
  | some (.str "clearance-cert/0") => pure ()
  | _ => .error "not a clearance-cert/0 file"
  let c ← num (← field j "clearance")
  let parts ← field j "parts"
  let hints ← field j "hints"
  let A ← parsePart (← field parts "A") (← field hints "A")
  let B ← parsePart (← field parts "B") (← field hints "B")
  let ws ← collect parseWitness (← list (← field j "witnesses"))
  .ok ⟨c, A, B, ws⟩

end Certify.Clearance
