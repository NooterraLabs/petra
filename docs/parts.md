# Parts and assemblies

This page designs Petra's move from steel connections to physical parts that agents make. A part is a closed triangle mesh with a material and a process. An assembly places parts and circuit boards and says how they go together. Petra checks that the parts fit, that each can be made by its process, and says what it could not decide.

The scaffold is on branch `parts-scaffold` under `petra/models/parts/` and `petra/registry/parts.py`. It has types, signatures and contracts, and every unwritten body raises `NotImplementedError`. It declares no `DOMAIN`, so nothing it holds reaches a verdict yet.

Every number carries a label. **Measured** means run or counted while writing this page, or measured by one of the two design sketches on this machine. **Inferred** means reasoned from measured facts. **Guess** means a guess.

## Problem

Agents can now write meshes and board files. This design targets the mistakes that stop a part from being made or put together. A board does not slide into its case. A screw is too short for the stack it clamps. A USB plug hits the wall below its opening. A wall is thinner than two printed lines. An inside corner is sharper than any cutter can reach. Steel connections taught Petra to check strength against a code. Parts need it to check geometry against a process.

Four constraints make the shape non-obvious.

- **The kernel is frozen.** It holds 1,414 of its 1,500 budgeted code lines (measured with `tests/test_kernel_budget.py`). Rules R1 to R6 bound expressions over boxes of hypotheses. None quantifies over points of space.
- **Statements take exact rationals only (T3).** An STL mesh holds float32 coordinates. A voxel test in floats cannot sit in the trusted path.
- **Every premise number is a labelled `RangeHyp` (decision 2), and the statement is a pure function of the design (decision 1).** So a solver setting cannot quietly become a premise, and a premise cannot hide inside a solver.
- **A grid can never prove touching contact.** A board resting on its standoffs touches them. Any cell that meets the contact face is unsure, so a grid-only fit check answers UNKNOWN on every seated part. Fit needs an exact evaluator.

## Usage

An agent writes three blocks beside its mesh and board files. Every number in this design is a guess. Every number in the verdict below is an illustration.

```
petra 0

design "sensor-box" {
  owner "e.designer@example.org"
}

pcb main {
  file "main.kicad_pcb" sha256 "41ab...e2"
  process process.pcb.fr4_1_6
  height J1 in [3.2 mm, 3.3 mm] signed "e.designer@example.org" source "USB-C receptacle drawing"
  height others in [0 mm, 2.5 mm] signed "e.designer@example.org" source "every other part is SMD under 2.5 mm"
}

part case {
  mesh "case.stl" sha256 "9f2c...07" units mm
  material polymer.pla
  process process.print.fdm_pla_0_4
  build top
  hole b1 at (4 mm, 4 mm, 6 mm) along bottom diameter 2.2 mm depth 5 mm form
  hole c1 at (2 mm, 2 mm, 20 mm) along bottom diameter 2.2 mm depth 8 mm form
}

part lid {
  mesh "lid.stl" sha256 "c3d1...9a" units mm
  material polymer.pla
  process process.print.fdm_pla_0_4
  build bottom
  hole l1 at (2 mm, 2 mm, 2 mm) along bottom diameter 2.8 mm clear
  seat s1 at (2 mm, 2 mm, 2 mm) facing top ring screw.m2_5x8_pan_a2
}

assembly unit {
  place case at (0 mm, 0 mm, 0 mm) facing top front
  place main at (2 mm, 2 mm, 6 mm) facing top front
  place lid at (0 mm, 0 mm, 20 mm) facing top front
  insert main along bottom from 14 mm
  fasten f1 screw.m2_5x5_pan_a2 through main.H1 into case.b1
  fasten f2 screw.m2_5x8_pan_a2 through lid.l1 into case.c1
  access usb box (9 mm, 3.4 mm) at (30 mm, 0 mm, 8 mm) along back
  gap main lid
}
```

The parser already takes every line of it (measured by parsing this text with `petra.lang.parser.parse`). No language grammar changes. Each kind's lines are a `Grammar` in `lower.py`, so `petra kinds part`, `petra new` and `docs/reference.md` print them from one place.

The agent checks it the way it checks steel.

```
petra check sensor-box.petra
petra check sensor-box.petra --json
```

The MCP `check` tool is unchanged. Given `path`, mesh and board files resolve against the design's directory. Given `text`, they must be absolute paths.

```
sensor-box: FAIL
entries    coverage FAIL
checked    38 obligations, 33 certified, 1 refuted, 0 waived, 4 open
governing  fit  unit.usb/fit.access: the plug enters case 0.35 mm below the opening's lower edge
  unit.case.main/fit.overlap     coverage fit.overlap    R4  proved    exact     sha256:1e07..  validity 1 proved  no crossing, 4 seated contacts
  unit.main.J1/fit.keepout       coverage fit.keepout    R4  proved    exact     sha256:8c3a..  validity 1 proved  0.42 mm clear
  unit.usb/fit.access            coverage fit.access     R4  refuted   exact     sha256:5be1..  validity 1 proved  plug edge 3 crosses case face 18204
  unit.f2/fit.grip               coverage fit.grip       R4  proved    declared  sha256:77d0..  engagement 5.2 mm, needs 4.5 mm
  case/print.thin_wall           coverage print          R4  proved    grid      sha256:c90f..  validity 2 proved  thinnest wall 1.05 to 1.22 mm
  case/print.min_hole            coverage print          --  open      grid      unresolved at 0.0625 mm cells, 12 unsure cells beside hole b1
cost       case/print.overhang  support area 412 to 455 mm2 (no budget stated)
footprint  57 premises
  design           dsg:sensor-box.case.mesh   case.stl sha256:9f2c...07, 41,288 triangles, read exactly
  assumed          in:sensor-box.main.height.J1   main.J1 height in [3.2, 3.3] mm   (e.designer@example.org; USB-C receptacle drawing)
  assumed          in:sensor-box.main.height.others   main height of every other footprint in [0, 2.5] mm   (e.designer@example.org; ...)
  judged           reg:process.print.fdm_pla_0_4.fit.clearance   [0.2, 0.3] mm   (petra-maintainers; typical FDM shop practice; version 1)
  validated_model  model:parts.exact@<hash>   exact rational geometry of closed triangle meshes at one placement; valid when ...
  validated_model  model:parts.grid@<hash>    three-valued cell grid over the part; valid when ...
```

The JSON keeps today's keys and adds two. An obligation gets `witness`. The report gets `costs`.

```json
{"requirement": "unit.usb/fit.access/coverage.fit.access", "outcome": "refuted", "rule": "R4",
 "describe": "a 9 x 3.4 mm plug travels along back to (30, 0, 8) mm without entering a body",
 "witness": {"crossing": {"edge": [["usb", 3], ["usb", 7]], "face": ["case", 18204], "at": ["30.1", "-0.4", "4.65"]}},
 "needs": []}
```

## Shape

### Organizing structures

- **Three component kinds.** `part` is a mesh, a material and an optional process. `pcb` is a KiCad file and a fit preset. `assembly` places parts and boards and declares fasteners, insert paths, access paths, gaps, guards and openings. A part without a process is checked for fit only, and the readout says so.
- **One table.** `rules.RULES` holds every fit and fabrication check, 38 rows (measured). Each row names the feature it applies to, what failing means, the measure it reads, the query that measure needs, and the preset row it is held to. Failure modes, coverage rules, builders and the rows each preset must hold all derive from it (per `principle-model-the-domain`). A new check is a new row.
- **Three evaluators.** EXACT answers questions about one placement in exact rational arithmetic. DECLARED answers questions about declared features alone, such as hole sizes and screw lengths, and the statement is the whole check. GRID answers questions about every placement on a three-valued cell grid.
- **One query.** `space.Sweep` asks whether a mover can travel along an axis into its place without entering the obstacles, and how much sideways room it keeps. The engine picks the evaluator from the mover's placement, so no caller chooses one.

### Data shapes

| Type | Module | What it holds |
|---|---|---|
| `Mesh` | `mesh.py` | integer vertices over one power-of-ten scale, triangles, path and sha256 |
| `Board` | `kicad.py` | outline and cutout loops of segments and exact arcs, drills, courtyard keep-outs with heights |
| `Turn`, `Placement`, `Solid` | `space.py` | the 24 axis rotations, an exact offset, a mesh where an assembly puts it |
| `Profile`, `Placed`, `Everywhere` | `space.py` | a body of revolution as bands of semi-infinite cylinders, at one point or at every point |
| `Sweep` | `space.py` | mover, direction, travel, obstacles, sideways clearance |
| `Bracket`, `Overlap` | `space.py` | the answers. A Bracket is a measure's low and high ends and its witness. An Overlap is a crossing, a contained vertex, or proof of none |
| `CellGrid` | `grid.py` | cell states IN, OUT and ON, the owner of each cell, the stock mask, the parent grid |
| `Rule`, `QuerySpec` | `rules.py` | one row of the table |
| `Deck`, `Row`, `Tool`, `Override` | `deck.py` | one preset's rows with the design's overrides merged, each row keeping its premise label |
| `PartDesign`, `PcbDesign`, `Assembly` | `lower.py` | the typed models, with `Hole`, `Seat`, `Place`, `Fasten`, `Insert`, `Access`, `Apart`, `Guard`, `Opening` |
| `Run`, `Cost`, `GridBudget` | `engine.py` | every answer for one model, the cost lines, the solver budget |
| `UnresolvedGeometry` | `build.py` | the new gap need for an undecided geometric rule |

### Data flow

```
.petra  ──parse──▶ Component ──lower_part / lower_pcb / lower_assembly──▶ PartDesign, PcbDesign, Assembly
                                   │ read_mesh, read_board (hash-pinned, memoised)
                                   ▼
                    deck(registry, preset, overrides) ──▶ Deck
                                   ▼
            engine(model, decks) ──ask(Sweep)──▶ exact.clearance        (one placement)
                                   │             reach.reach on a grid   (every placement)
                                   │             exact.overlap, gap, seat, slopes, prism, extent
                                   ▼
                    Run: answers by (rule, subject), costs
                                   ▼
            build(requirement, model) ──▶ Obligation (R4 main goal + validity lemmas) or Gap
                                   ▼
                    kernel check ──▶ verdict, readout, footprint
```

### Invariants and where they live

- **Coordinates stay exact.** `read_mesh` reads each float32 as its shortest round-trip decimal, which has at most 9 significant digits (inferred from float32's 24-bit significand), and scales all of them to integers over one power of ten. Placements turn only by the 24 axis rotations and move by exact offsets. So every placed coordinate is an exact rational, and two faces the author made coplanar stay coplanar.
- **A mesh is the oriented boundary of a solid.** `read_mesh` requires every edge to be used by exactly two triangles, once in each direction. An edge shared by four faces, a duplicated face and an open boundary all fail that rule. It refuses two triangles on the same three vertices, because a doubled wall drawn as two opposite triangles passes the edge rule and bounds nothing. Every connected piece must enclose volume, and the whole mesh positive volume. The scaffold's parity rule accepted all of these (audit rows D-152 and D-158). `exact.surface_problem` finds what the edge rules cannot see, and `lower_part` refuses the mesh with its message. Two triangles that share no vertex and meet mean the surface crosses or touches itself. Two coplanar triangles that overlap and face opposite ways are a wall of zero thickness, or the internal face where two bodies touch. Two neighbours folded onto each other fail too. A piece nested an even number of times must face outward and a piece nested an odd number of times inward, so a void is a void and not a second body.
- **Profiles are monotone.** `Profile.__post_init__` refuses band depths that do not rise and radii that fall, so every profile is a union of semi-infinite cylinders and a height field decides where it fits. This is implemented in the scaffold.
- **A Bracket's ends are ordered.** `Bracket.__post_init__` refuses lo above hi. Implemented.
- **Rule ids are unique.** `rules.py` raises at import on a repeated id. Implemented.
- **Only `deck()` merges presets and overrides,** and only `lower_part` builds an `Override`, after checking the preset holds the row and the bound has its unit (per `principle-type-system-discipline`).
- **Every preset holds exactly the rows its kind's rules read.** `domain.check_presets` compares each preset with `rules.rows_read(kind)` and the registry's consistency check reports the difference at load.
- **An impossible rule cannot be waived.** `lower_part` refuses the waiver.
- **The grid's cell side is never a premise.** `engine.BUDGET` holds it in code, and `engine.py`'s source is hashed into the grid model.

### Interface depth

The caller's surface is the three block kinds and the verdict. It hides the mesh reader, the board reader, both evaluators, the refinement loop and the witness lemmas. Inside the package, `engine.engine` is the one entry point to geometry, every sweep goes through `engine.ask`, and `build.build` is the one builder for all 38 modes (measured). The surface stays this small because every per-rule difference is a row of data, not a function.

## The fit layer

Fit comes first in the build order. Every fit question below except one is exact on rational mesh coordinates with R4 alone.

| Question | Rule | Evaluator | What the kernel checks | What stays trusted |
|---|---|---|---|---|
| Do two placed bodies overlap? | `fit.overlap` | exact | for FAIL, the crossing lemma, four signed volumes over the five vertices of an edge and a face (R4); for PASS, each seated contact as a coplanar, opposite-facing pair (R4) | broad-phase completeness, containment by parity, the zero count of crossings |
| Does a component, its courtyard raised to its height, hit a body? | `fit.keepout` | exact | as overlap, with the height a signed `RangeHyp` | the board reader |
| Do two bodies keep a clearance apart? | `fit.gap` | exact | the least squared distance against the squared clearance row. FAIL adds the near lemma, one squared distance from the two features' vertices | the closest-pair search |
| Does a board travel its insertion path? | `fit.insert`, `fit.insert_clearance` | exact | the least sideways squared clearance against the row | the cross-section sweep |
| Does a plug reach its connector? | `fit.access` | exact | as insert | as insert |
| Does a pin of the hole's size, less the tolerance, pass the hole? | `fit.hole` | exact | as insert, with the pin radius from the declared diameter | as insert |
| Does the screw head or washer bear on the face? | `fit.seat` | exact | the ring's widest point off the face union | the face-union containment |
| Do hole patterns align across parts? | `fit.align` | declared | the squared offset of hole centres against the room the holes leave, over the tolerances | lowering |
| Is the screw long enough and not too long? | `fit.grip` | declared | thread engagement and bottoming lengths through the stack | lowering |
| Does a driver reach the screw head? | `fit.driver` | exact | sideways clearance of the driver's profile | the sweep |
| Does a declared opening pass the guard's ball? | `fit.opening` | declared | the opening's width at its widest tolerance against the sphere | lowering |
| Does any ball of the guard's size reach the hazard? | `fit.passage` | grid | the stencil and extreme lemmas | cell classification and the bottleneck search |

The insert sweep is exact because a polyhedron swept along an axis is a polyhedron, and its cross-sections change only at the finitely many levels of vertices. The sideways clearance is a 2D distance between rational polygons at those levels (inferred). A seat is not a clash. The sweep measures clearance between open cross-sections at common levels, so faces that meet head on at the end of the travel are a seat.

`fit.passage` needs the grid because "no ball anywhere reaches the hazard" quantifies over every placement of the ball. A guard made of declared bars, slots and holes uses `fit.opening` instead and stays exact.

## One query for fit and reach

`Sweep(mover, along, travel, obstacles, clearance)` serves both. The mover's placement picks the evaluator.

| Mover | Placement | Evaluator | Used by |
|---|---|---|---|
| a board, a lid, a plug body | `Solid` | exact | `fit.insert`, `fit.access` |
| a pin, a screw driver | `Placed` at a `Point` | exact | `fit.hole`, `fit.driver` |
| a cutter, a router bit, a laser's beam | `Placed` `Everywhere` | grid | `mill.reach`, `sheet.corner` |
| a ray along the pull | `Placed` `Everywhere`, radius 0 | grid | `mold.undercut`, `mold.side_actions` |

The twin tests the seam. For one placement computed both ways, the exact answer must lie inside the grid's Bracket (metamorphic relation MR3 below).

## Process rows

Printing and flat cutting come before 3-axis milling, and molding comes last. Each preset holds exactly the rows its kind's rules read. Every value in these tables is a guess from typical shop pages and datasheets, judged by petra-maintainers until a maker signs its own preset or overrides a row with `measured`.

**Material extrusion, `process.print.fdm_pla_0_4`.**

| Row | Value (guess) | Worse end | Read by |
|---|---|---|---|
| `build` | 220 x 220 x 250 mm | low | `print.volume` |
| `line_width` | 0.40 to 0.45 mm | high | `print.min_feature`, as a disk one line wide and one layer thick |
| `layer` | 0.2 mm | high | the disk's height |
| `wall` | 0.8 mm | high | `print.thin_wall` (worse) |
| `hole_min` | 1.0 mm | high | `print.min_hole` |
| `overhang` | slope ratio 1, 45 degrees from vertical | low | `print.overhang` (costlier, support area) |
| `fit.clearance` | 0.2 to 0.3 mm | high | `fit.gap`, `fit.insert_clearance` |
| `tolerance` | 0.2 mm | high | `fit.align`, `fit.hole`, `fit.opening` |

**Powder-bed fusion, `process.powder.sls_pa12`.**

| Row | Value (guess) | Worse end | Read by |
|---|---|---|---|
| `build` | 300 x 300 x 300 mm | low | `powder.volume` |
| `min_feature` | 0.8 mm | high | `powder.min_feature`, as a ball |
| `wall` | 1.0 mm | high | `powder.thin_wall` (worse) |
| `hole_min` | 1.5 mm | high | `powder.min_hole` |
| `escape` | 3.5 mm | high | `powder.escape`, a ball from every closed void to outside |
| `fit.clearance` | 0.3 mm | high | fit rules |
| `tolerance` | 0.3 mm | high | fit rules |

**Profiles cut from sheet, `process.sheet.laser_s275_3` and `process.sheet.router_cf_3`.** `sheet.prism` first checks the part is an extrusion of the stock thickness along its declared normal, exactly. The corner rule is then the reach question in the sheet's plane.

| Row | Laser, 3 mm S275 (guess) | Router, 3 mm carbon fibre (guess) | Read by |
|---|---|---|---|
| `thickness` | 2.85 to 3.15 mm | 2.9 to 3.1 mm | `sheet.prism` |
| `bed` | 3000 x 1500 mm | 600 x 400 mm | `sheet.bed` |
| tool | beam of radius 0.10 to 0.15 mm, half the kerf | `tool.t3`, flat, radius 1.5875 mm, reach 12 mm | `sheet.corner` |
| `reach_tolerance` | 0.05 mm | 0.05 mm | `sheet.corner` |
| `min_web` | 3 mm | 2 mm | `sheet.min_web` |
| `min_hole` | 3 mm | 3.2 mm | `sheet.min_hole` |
| `tolerance` | 0.1 mm | 0.1 mm | fit rules |

**3-axis milling, `process.mill.al6061_t6_3axis`.** The rows are sketch B's.

| Row | Value (guess) | Read by |
|---|---|---|
| `tool.t1` to `tool.t4` | flat end mills of radius 0.5, 1.5, 4 and 6 mm, reaching 3, 9, 24 and 36 mm below the holder | `mill.reach` |
| `reach_tolerance` | 0.5 mm | `mill.reach`, `mill.special_tools` |
| `min_feature` | 0.8 mm | `mill.min_feature` |
| `chatter.ratio` | 8, free height over thickness | `mill.chatter` (worse) |
| `setups.budget` | 2 | `mill.setups` (costlier) |
| `tolerance` | 0.05 mm | fit rules |

**Boards, `process.pcb.fr4_1_6`.** Thickness 1.44 to 1.76 mm, outline tolerance 0.2 mm, drill tolerance 0.08 mm (all guesses). It is read by fit rules only.

**Molding** has rules in the table (`mold.undercut`, `mold.draft`, `mold.side_actions`, `mold.min_wall`, `mold.sink`) and no preset in v0. A mold shop's signed preset comes first.

Consequences follow the synthesis. An **impossible** rule fails the design and refuses a waiver at lowering. A **worse** rule fails it, and its owner may waive it with a signature and a reason. A **costlier** rule always prints a cost line and fails only against a budget the design or the preset states. Coverage demands a costlier rule only where such a budget exists.

## The circuit board reader

`kicad.py` reads `.kicad_pcb` files from KiCad 6 on with the standard library only. It accepts file version 20211014 or newer, KiCad 6's version as recalled and not yet checked against KiCad's source (guess). The format is S-expressions, so the parser is small, about 60 lines (guess). It reads four things.

- The outline. Edge.Cuts lines, arcs, circles, rectangles and polygons, chained into closed loops. The outermost loop is the outline and the rest are cutouts. A loop that does not close is refused.
- The thickness, from `(general (thickness ...))`.
- The holes. Every pad with a drill, plated or not, and every mounting hole. A fasten line names a board hole by its footprint reference, such as `main.H1`.
- The keep-outs. Each footprint's courtyard on F.CrtYd or B.CrtYd, with its side.

KiCad's y axis points down the screen, so the reader flips it to point up. A footprint turned by a multiple of 90 degrees is placed exactly. Any other angle is placed by a rational rotation within 2^-30 rad of it, and every affected edge moves by that bound toward the harder fit. Keep-outs grow and drills shrink. At 1,000 mm from the origin that bound is about 1e-6 mm (inferred).

Component heights are a stated premise. The pcb block's signed `height <ref>` line comes first. Then a footprint's `Height` property, read as a design value when the board's author set one. Then the signed `height others` line. A footprint with none of these leaves `fit.keepout` a Gap needing `NeedsInputBound`. A footprint with no courtyard keeps an empty keep-out, and its keep-out check is a Gap until a waiver names it. Petra never invents a height.

The reader is trusted, pinned by the design's sha256, and runs at check time. The board feeds the enclosure deck. Its outline, holes and keep-outs become a placed `Solid` the case's fit rules check against.

## Certificates

Every verdict has three layers, as in sketch B. The kernel checks the inequality and the geometric lemmas. A trusted evaluator, a validated_model premise hashed over its source, vouches for what the lemmas do not state. Premises carry the rest.

| Evaluator | PASS | FAIL | UNKNOWN |
|---|---|---|---|
| exact | the measure's exact value against the bound row, R4 Enclosure. Seated contacts restated as R4 lemmas | the same goal refuted, beside a witness lemma that restates the crossing or the near pair from its vertex coordinates, R4 PointWitness | a contact the contact rule does not classify, such as edge on edge across a face. Gap needing `UnresolvedGeometry` |
| declared | the inequality over declared sizes and signed tolerances, R4 Enclosure | the same refuted at a point of the tolerance box | none beyond a missing signed bound |
| grid | the Bracket's hi end against the bound, beside the stencil and extreme lemmas | the Bracket's lo end refuted, beside the obstruction lemma for the witness cell | the Bracket straddles the bound at the solver's floor. Gap needing `UnresolvedGeometry`, naming the unsure cells |

A straddling Bracket states nothing. Refuting its hi end would not refute the design, so the builder returns a Gap. Squares keep every goal rational. A distance d against a bound c is stated as d^2 - c^2, with d^2 an exact sum of squares.

**What stays a premise.**

- The mesh is the part. Its hash and its exact coordinates are design values. A tessellated cylinder is a polygon, and the check is about the polygon.
- The board file is the board. Component heights are signed or read from the file.
- Preset rows are judged, or overridden with an owner and a reason.
- Each evaluator is a validated_model premise, `model:parts.exact`, `model:parts.declared` or `model:parts.grid`. Each hashes every module it trusts, as `electronics/domain.py` already does for its three.
- The grid's cell side is not a premise. A sound grid at any side gives the same PASS and FAIL and differs only in how often it says UNKNOWN. Because `engine.BUDGET` sits in hashed source, the statement stays a pure function of the design.

**No new kernel rule.** R4 carries every goal and lemma. Sketch A proposed R7, a cover-residual lemma. A PASS names a finite cover of tool poses, and a FAIL names a point of stock with a finite proof that no allowed pose cuts it. R7 would put reach under kernel check. It would cost about 465 lines (guess, sketch A) and take the kernel to about 1,880 of 1,500 (inferred, sketch A). It is rejected for now. Sketch B considered a cell-counting rule and rejected it too, because it would still trust the cell classification. Lemma variables, such as a tool centre's offset in the obstruction lemma, are labelled `dsg:` like the electronics domain's normalised spreads.

## Mistake classes

Each class below names the Petra checks that catch it and the mistakes no check catches yet.

| Class | Caught by | Not caught yet |
|---|---|---|
| Intent | claims; `fit.hole` and `fit.seat` test declared features against the mesh, so a hole declared but not modelled fails; `fit.access` for every declared connector | a part that is valid and does the wrong job; a button not over its switch unless declared as access; a missing vent; the wrong board revision behind a correct hash |
| Geometric validity | lowering refuses a hash mismatch, an open or non-manifold surface, a self-crossing surface, a hole or seat outside the mesh, a turn whose axes are parallel, a board outline that does not close | chord error, where a coarse tessellation makes holes and bosses smaller than their CAD model; the check is right about the mesh and the mesh is wrong about the intent |
| Fit and interface | `fit.overlap`, `fit.keepout`, `fit.gap`, `fit.insert`, `fit.insert_clearance`, `fit.access`, `fit.hole`, `fit.seat`, `fit.align`, `fit.grip`, `fit.driver` | assembly order, since every sweep runs against every other placed body, so an order-dependent design is refused (a false FAIL, never a false PASS); cable routing; snap-fit engagement |
| Fabrication | `print.*`, `powder.*`, `sheet.*`, `mill.*`, `mold.*`, 25 rules (measured) | warp and shrink, bridging, support removal access, fixturing and clamps, tool deflection, feeds and heat |
| Strength and stiffness | the truss, bolt and steel connection domains for their own kinds | every parts load case in v0, such as boss splitting under a thread-forming screw, snap-fit strain, wall deflection, interlayer weakness of prints, creep of PLA |
| Code compliance | steel's AISC 360 checks; electronics ratings; `fit.passage` and `fit.opening` against a signed probe sphere | creepage and clearance between conductors and the case (IEC 62368-1), flammability ratings (UL 94), water ingress, jointed test fingers |
| Unstated premises | a missing height or courtyard is a Gap; a part without a process prints "fit only"; preset rows, overrides and models sit in the footprint; a grid UNKNOWN names its unsure cells | thermal expansion between PLA and FR4 (about 0.11 mm more growth for PLA over 100 mm and 20 K, inferred from expansion coefficients of 68e-6 and 14e-6 per K, both guesses); humidity swell of PA12; a board populated differently from its file |

## Line budget

The kernel gains no line (measured; the branch touches nothing under `petra/kernel/`).

The scaffold adds 739 trusted code lines (measured with `tests/test_kernel_budget.code_lines`). The test adds 30 untrusted ones (measured).

| File | Scaffold code lines (measured) | Lines the implementation adds (guess) |
|---|---|---|
| `petra/models/parts/mesh.py` | 25 | 150 |
| `petra/models/parts/space.py` | 105 | 40 |
| `petra/models/parts/kicad.py` | 61 | 330 |
| `petra/models/parts/exact.py` | 23 | 600 |
| `petra/models/parts/grid.py` | 23 | 300 |
| `petra/models/parts/reach.py` | 34 | 650 |
| `petra/models/parts/rules.py` | 150 | 20 |
| `petra/models/parts/deck.py` | 41 | 60 |
| `petra/models/parts/lower.py` | 166 | 400 |
| `petra/models/parts/engine.py` | 31 | 220 |
| `petra/models/parts/build.py` | 33 | 450 |
| `petra/models/parts/domain.py` | 28 | 160 |
| `petra/registry/parts.py` | 11 | 300 |
| `petra/registry/model.py` | 8 | 0 |
| shared modules (base, verdict, readout, templates, catalog, teach, models) | 0 | 130 |
| **total** | **739** | **3,810** |

So the implemented domain holds about 4,550 trusted code lines (inferred from the measured scaffold and the guessed additions). For scale, the electronics domain holds 1,533 code lines and the steel models 8,272 with their twin and generators (both measured).

## Testing

A clean-room twin and metamorphic relations judge the evaluators, as they judge the steel deck.

**The twin** generates assemblies whose answers are analytic. Boxes nest in boxes with known gaps. Round pins pass polygonal holes whose inscribed radius is known. Boards slide into slots of known width. Plates carry pockets with known corner radii and walls of known thickness. For each it computes the true answer in closed form.

**The metamorphic relations.**

- MR1. An axis rotation and a rational translation of a whole assembly leave every verdict unchanged.
- MR2. Scaling every length and every bound by 2 leaves every verdict unchanged.
- MR3. For one placement computed both ways, the exact answer lies inside the grid's Bracket.
- MR4. Refining the grid never turns PASS into FAIL or FAIL into PASS.
- MR5. Moving two bodies apart never turns a fit PASS into a FAIL.
- MR6. Splitting a triangle into coplanar triangles changes nothing.
- MR7. Shrinking a tool's radius never turns a reach PASS into a FAIL.

**Done test for step 1, exact fit.** The sensor box above and 200 generated assemblies (guess) give zero wrong PASS and zero wrong FAIL against the twin, every relation holds on all of them, and UNKNOWN stays under 5 percent of fit obligations (guess).

## Cost

| Step | Cost | Label |
|---|---|---|
| exact point-to-face squared distance, scaled integers | 4.3 µs | measured by sketch A |
| the same in Python Fractions | 107.9 µs | measured by sketch A |
| exact triangle-to-triangle test, about 15 sub-distances | about 75 µs | inferred |
| one pair of 40,000-triangle bodies with 10,000 candidate pairs near contact | about 0.75 s | inferred from a guessed candidate count |
| grid reach on a 155,200-triangle mesh at 0.25 mm cells | 21.1 s | measured by sketch B |
| the same at 0.125 mm cells | 32.6 s | measured by sketch B |
| reading a 2 MB board file | under 1 s | guess |
| checking the sensor box | under a minute | guess |

Scaled integers, not Fractions, set the exact evaluator's cost, which is why `Mesh` stores integer vertices over one scale. The exact predicates run on Python integers. The grid's separating-axis test runs on int64 while every product stays below 2^62, and on Python integers otherwise.

## Build order

The order follows what each step needs.

1. **Exact fit.** `mesh`, `space`, `exact`, `kicad`, `deck`, `lower` for all three kinds, `build` for the exact and declared evaluators, the fit rows, registration with fit rules only. Done when the step 1 test above passes.
2. **Printing and flat cutting.** `grid`, `reach.thickness`, `reach.passage`, the exact `slopes`, `prism` and `extent`, the print, powder and sheet presets. The sheet corner rule is the first reach question, in the sheet's plane. Done when generated prints and profiles with analytic walls, holes and corners pass the twin.
3. **3-axis milling.** `reach.reach` with tool decks, `directions_needed`, `ratio`, the mill preset. Done when sketch B's bracket gives its stated verdicts and the twin's pockets pass.
4. **Molding.** Pull reach and draft, once a shop signs a preset.

## Module map

| File | Status | Change |
|---|---|---|
| `petra/models/parts/*.py` | new, scaffold | the twelve modules above |
| `petra/registry/parts.py` | new, scaffold | presets, polymers, screws, washers |
| `petra/registry/model.py` | changed | `PartKind` gains SCREW and WASHER; `ProcessKind` gains PRINT, POWDER, SHEET, MILL, MOLD and PCB |
| `tests/test_parts_scaffold.py` | new | the scaffold loads; the package declares no DOMAIN; the rule table holds together |
| `petra/registry/catalog.py` | step 1 | merges the parts deck |
| `petra/teach.py` | step 1 | `_PROCESSES` entries for the new process kinds |
| `petra/models/__init__.py` | step 1 | registers the parts DOMAIN |
| `petra/models/base.py` | step 1 | `UnresolvedGeometry` joins `GapNeed` |
| `petra/verdict.py` | step 1 | one match case for `UnresolvedGeometry` |
| `petra/readout.py` | step 1 | witness lines and cost lines; `tests/test_readout.py` gains the two keys |
| `petra/templates.py` | step 1 | `petra new part`, `pcb` and `assembly` |
| `tests/test_structure.py` | step 1 | a fence so `petra/models/parts` imports only the standard library, numpy and petra |
| `petra/pipeline.py` | none | `Design.path` already gives lowering the design's directory (read in `petra/ir.py`) |

## Red-flag screen

- **Shallow module.** `deck.py` is one function over three types. It stays, because it is the one place rows and overrides merge.
- **Information leakage.** The integer scale and the int64 layout are known to `mesh`, `exact` and `grid` only. KiCad's format is known to `kicad` only.
- **Temporal decomposition.** None. Lowering, engine and build split by data, and each runs once per model through a memo.
- **Pass-through method.** `engine.ask` adds the dispatch and does not merely forward.
- **Split ownership.** The registry owns preset rows, lowering owns overrides, and `RULES` owns checks. Nothing else writes them.
- **Two ways to do one task.** Exact clearance and grid reach answer one query, and the mover's placement picks between them. A duplicate `exact.pin` was cut while sketching. PASS on a Bracket's hi end and FAIL on its lo end are the two certified directions of one measure, kept from sketch B.
- **Importable internals.** The modules are importable, as in every Petra domain. The step 1 fence guards imports.
- **Hand-synced list.** Every table derives from `RULES`. The test's module list is compared with the files on disk, so it cannot drift silently.

## Synthesis decision

Sketch B is the base. It keeps the three-valued grid, R4 alone, no kernel rule and no language change, and its certificate story carries over whole. From sketch A this design takes exact rational coordinates and exact witnesses, and builds a new exact evaluator from them. That evaluator is the fit layer, which neither sketch had and which goes first. Sketch A's kernel rule R7 is rejected for now. The synthesis grafts four further changes. The grid's resolution is a solver budget, not a premise. A costlier rule is always a cost line and fails only against a stated budget. A worse rule fails and may be waived by signature, and an impossible one refuses waivers. Thin features are found by opening with a ball, or with a disk for printed lines.

## Tradeoffs accepted

- We accept an exact evaluator that trusts its broad phase and its parity count, in exchange for fit checks that can PASS a seated part. A grid cannot.
- We accept that a grid rule near its bound answers UNKNOWN, in exchange for no resolution premise in any footprint.
- We accept axis-aligned placements only in assemblies, in exchange for exact placed coordinates. KiCad's other rotations are handled inside the reader with a stated bound.
- We accept that every sweep runs against every other placed body, in exchange for not modelling assembly order. An order-dependent design is a false FAIL, never a false PASS.
- We accept judged preset values that are guesses, in exchange for a check an agent can run today. Each sits in the footprint with its label.
- We accept no strength rules for parts in v0, in exchange for shipping fit and fabrication first.

## Alternatives considered

- **Sketch A's R7 cover-residual lemma in the kernel.** It would put reach itself under kernel check, with a pose cover for PASS and an infeasibility proof for FAIL. It costs about 465 kernel lines (guess, sketch A) and breaks the 1,500-line budget. Fit, which goes first, does not need it, and B's grid serves reach with R4 alone.
- **A grid-only fit layer.** One evaluator is smaller, but it cannot prove touching contact, so every seated board would be UNKNOWN. It exposes resolution to the caller as the only way out.
- **A separate fit engine beside the reach engine.** Two queries for one question, two dispatch paths, two sets of tests. One `Sweep` with dispatch by placement hides that choice.
- **Converting meshes and boards to Petra files at import time.** It moves the trusted reader out of the check, but the converted file is then a second artefact to pin and keep in sync. Reading at check time behind a hash keeps one.

## Open questions

Each has a default the implementation follows until the maintainer answers.

1. Should parts get a kernel rule, R7 or a geometry rule? **Default no.** Revisit if the grid's UNKNOWN rate on real parts stays above 10 percent at the floor (guess threshold).
2. Should lemma variables get their own `var:` label namespace, about 10 trusted lines (guess)? **Default no.** They use `dsg:`.
3. Should a worse rule FAIL with a signed waiver, or report MARGINAL through decision 10? **Default FAIL, waivable.**
4. Should the MCP `check` tool take a base directory for relative file paths? **Default no.** Text designs name absolute paths.
5. Should Petra ship code tables for guard probe sizes, such as IEC 60529's? **Default no** until licensing of code tables is decided. The owner signs the sphere.
6. Should directions beyond the six axes come in, for 5-axis milling, angled pulls and turned placements? **Default later.**
7. Should float32 meshes be read as shortest decimals, exactly, rather than snapped to a dyadic grid? **Default shortest decimals,** so no snap premise exists.
8. Should KiCad files be read at check time? **Default yes,** trusted and hash-pinned.
9. Who signs presets? **Default petra-maintainers, judged.** A maker's preset or `measured` overrides upgrade them.
10. What height does a component get when the board file has none? **Default none.** A signed line is required, or the keep-out check is a Gap.
11. Should the grid's floor be a CLI solver flag? **Default no.** It stays in `engine.py` so statements stay pure functions of the design.

## Next implementation step

Write `mesh.read_mesh` with the shortest-decimal reader, and test it on binary and ASCII STL files whose coordinates are known exactly.
