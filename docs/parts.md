# Parts and assemblies

Petra checks physical parts that agents make in code-CAD. A part is a closed triangle mesh with a material and, unless it is bought, a process preset. An assembly places parts, says how each one arrives at its place, and names the screws, gaps and press fits that join them. Each check proves its rule at the worst case of every declared tolerance, refutes it at the point that breaks it, or says what it needs to decide.

The layer lives in `petra/models/parts/` and `petra/registry/parts.py`. The scaffold that came before it is on branch `parts-scaffold`. This page describes branch `parts-fix`, which closes the false PASSes an independent review found on branch `parts-core`.

Every number carries a label. **Measured** means run or counted on this branch. **Reported** means a shop, maker or datasheet publishes it on the page named. **Inferred** means reasoned from measured or reported facts. **Guess** means nobody has signed it, and a value recalled from a standard or a guide that no source on disk confirms is a guess.

## Usage

An agent writes its meshes, then a design beside them. This is `examples/parts/assembly.petra`.

```
part case {
  mesh "case.stl" sha256 "b864...dc5a" units mm
  material polymer.petg
  process process.print.fdm_petg_0_4
}

part board {
  mesh "board.stl" sha256 "5ac8...cd97" units mm
  material polymer.pc
  tolerance in [0.1 mm, 0.1 mm] signed "e.designer@example.org" source "board maker's outline drawing"
  mass in [8 g, 9 g] signed "e.designer@example.org" source "weighed, five boards"
}

assembly box {
  place case at (0 mm, 0 mm, 0 mm) facing top front
  place board at (5 mm, 5 mm, 2 mm) facing top front
  insert board along bottom from 25 mm
}

claim light: box.mass <= 35 g
```

It is checked the way every design is.

```
petra check examples/parts/assembly.petra
petra check examples/parts/assembly.petra --json
```

The run gives UNKNOWN with 13 obligations, 8 certified and 5 open (measured). The board goes in at the worst corner of both tolerances and rests on the tray. The tray fits the printer, nothing on it spans air, and PETG and polycarbonate keep their shape in an indoor room. The mass claim counts the tray as solid with its surface grown by the printer's tolerance, and it holds at 33 g and not at 32.5 g (measured). The 5 open obligations are print rules with no model yet, and each names the waiver that would close it. `petra new part` and `petra new assembly` print the two examples, and `petra kinds part` prints every line a part takes.

A mesh path is read relative to the design's file. A design given as text must name absolute paths. The file is hashed on every read, so a changed mesh is an input error until the hash is updated.

## The part block

| Line | Says |
|---|---|
| `mesh "<file>" sha256 "<hex>" units <mm\|inch>` | the part's closed surface, an STL or 3MF file, read exactly |
| `material <id>` | what it is made of, a registry material |
| `process <id>` | how it is made, a print, powder, sheet or mill preset; a bought part names none |
| `finish <id>` | a coating whose buildup every fit rule adds to the part's surfaces |
| `tolerance <bound>` | a signed profile tolerance that replaces the preset's |
| `hole_shrink <bound>` | a signed diametral undersize of modelled holes that replaces the preset's |
| `fill <bound>` | the part's mass over a solid part's, for printed infill |
| `mass <bound>` | a bought part's signed mass |
| `cg (<x>, <y>, <z>)` | the centre of mass of a bought or infilled part, in its own frame |
| `heat <bound>` | a signed rise above ambient at the part, from a motor, a regulator or a lamp |
| `hole <id> at <point> along <axis> diameter <length> [depth <length>] [clear\|tap\|form\|press\|insert <id>] [countersink <length>]` | a hole and what it is for |

A hole line says where a hole is and what it is for. The rules read its size from the mesh, and only `fit.hole` reads its `depth`. Its mouth is the point, and it runs along the axis into the part. `clear` lets a screw pass. `tap` and `form` take a screw's thread in metal and in plastic. `insert` takes a heat-set insert from the registry. `press` takes a pin.

## The assembly block

| Line | Says |
|---|---|
| `place <part> at <point> facing <axis> <axis>` | where the part sits, its top and front turned to the two axes; the first place line is the base |
| `insert <part> along <axis> from <length>` | the part arrives moving along the axis over that length; every part but the base has exactly one |
| `fasten <id> <screw> through <part>.<hole> ... into <part>.<hole>` | a screw through clear holes, head side first, into the hole its thread enters |
| `gap <part> <part> [<length>]` | two parts that keep apart by the length beyond their allowances |
| `press <id> <part> into <part>.<hole> diameter <length> interference <length> to <length>` | a pin pressed into a press hole, with its diametral interference range |

A press line's `diameter` stays in the grammar, and no rule reads it, because `fit.press` reads the pin from its mesh.

Claims bound `mass` on a part, and `mass`, `cg_x`, `cg_y` and `cg_z` on an assembly. Parts take no loads in v0, and lowering refuses a load on them.

## Rules

`rules.RULES` is the one table. Each row names the feature it is demanded on, what failing it means, and the evaluator that decides it. Failure modes, coverage rules and builders derive from the table. A row with no builder is still demanded, and its obligation stays open with a waiver line until a builder exists.

| Rule | Demanded on | Evaluator | Holds when |
|---|---|---|---|
| `fit.insert` | every placed part but the base | geometry | the part travels its insert path clear of every other part by both allowances, rests on something at its place, and no piece of it lies inside another part |
| `fit.connected` | every placed part | geometry | the part touches, is fastened to or is pressed into a part placed before it |
| `fit.gap` | each gap line | geometry | the two parts keep the stated gap beyond both allowances |
| `fit.fastener` | each fasten line | geometry | the screw, as a body, reaches its hole clear of every part, enters the part it threads into only past that hole's mouth, and meets no other screw |
| `fit.seat` | each fasten line | geometry | a socket head covers the first hole and bears on the first part's face, or a countersunk head fits the countersink the mesh holds |
| `fit.grip` | each fasten line | geometry | the thread engages enough diameters in a hole or insert that takes it, and does not bottom in a blind hole |
| `fit.press` | each press line | geometry | the pin sits in its hole, and the interference read from both meshes stays in the declared range over both tolerances |
| `fit.hole` | each declared hole | geometry | the mesh holds the hole as declared, and its countersink when one is declared |
| `insert.hole_size` | each insert hole | geometry | the hole read from the mesh, with its allowance and shrink, lies in the insert's catalogue range |
| `insert.depth` | each insert hole | geometry | the hole's axis runs at least the insert's length and the allowance before it meets material |
| `insert.boss_wall` | each insert hole | geometry | the wall around the hole is at least the catalogue's least wall over the insert's length |
| `part.temperature` | each polymer part | thermal | ambient plus the declared local rise stays at or below the material's heat deflection temperature |
| `print.volume`, `powder.volume`, `sheet.bed` | each made part | geometry | the mesh's extent, grown by its allowance on both sides, fits the machine |
| `print.bridge` | each printed part | geometry | every face printed over air spans at most the preset's bridge between the edges that hold it |
| `sheet.prism` | each sheet part | geometry | the part is a flat profile of the stock's thickness |
| `parts.mass` | a mass claim | mass | the summed mass of parts, screws and inserts over the tolerance meets the claim |
| `parts.cg` | a centre of mass claim | mass | the mass-weighted centre over the tolerance and the floats meets the claim along one axis |
| `fit.driver`, `print.min_feature`, `print.thin_wall`, `print.min_hole`, `print.overhang`, `print.support_access`, `powder.min_feature`, `powder.escape`, `sheet.min_web`, `mill.reach`, `mill.min_feature` | as named | none yet | open, with a waiver line |

The table holds 30 rules, 19 with builders and 11 without (measured).

## Fit under tolerance

A fit check that passes on nominal geometry proves little. A 0.25 mm gap passes at nominal and closes when a printed wall comes out 0.5 mm thick. So every fit rule holds at the worst case of the tolerances the design and its presets declare.

- **Allowance.** Each part's true surface lies within its allowance `a` of the mesh, both ways. The allowance is the profile tolerance plus a finish's buildup. The tolerance comes from a signed `tolerance` line, or else from the preset. A print or powder preset's tolerance is the larger of its floor and its rate times the part's span, the diagonal of the mesh's box. Against a screw a printed part's allowance also holds half its hole shrink, because printed holes come out small.
- **Order and start.** Parts go in in place-line order. The base is placed. Every other part arrives along its insert axis from the stated distance, or from farther back if it must start there to lie wholly behind every part placed before it. So no part starts inside another.
- **Stops and float.** A part stops on the faces it touches at its place that lie wholly ahead of its own along the travel. A face is a flat region of triangles joined edge to edge and facing one way, so splitting a face into more triangles changes no stop. The part may then sit anywhere along its axis within its float, `F = max over its stops of (F_stop + a_stop + a_self)`. Across the axis it does not float.
- **Path.** The part is swept from its start to its place and on past it by its float. Every triangle pair but its stops must keep apart by both allowances. When the other part floats along a different axis, that float joins the allowance.
- **Resting and containment.** A part with no stop rests on nothing and fails. Each edge-joined piece of each part is probed for lying inside the other part, so a part of two pieces fails when either piece lies inside.
- **Screws.** A screw is a body. Its shank is the circumscribed 32-sided prism of its major diameter at its greatest length, and a socket head adds the circumscribed prism of the head at its greatest diameter. A countersunk head is the same prism, not a cone, reaching a head's height below the deepest it sinks, so a countersink that fits the cone closely fails `fit.fastener`, a FAIL of the model. Its axis is the declared axis of the hole its thread enters, and that hole may sit off its declared place by its part's allowance, so every clearance the screw keeps grows by that shift. Its head sits at the first hole's mouth, or lower where the mesh's countersink lets it sink. Its reach holds only while the head is held there. A socket head at its least diameter must overhang the first hole at its widest just below the mouth, grown by the allowance and the shift, and a countersunk head must stop in the countersink the mesh has. A countersunk head in a hole with no countersink declared sits on the mouth and is held like a socket head. A head that can pass its hole fails `fit.fastener`, and `fit.grip` in a blind hole, since nothing bounds how far the screw reaches. The screw arrives from beyond every part. It may enter the part it threads into only past that hole's mouth, so a screw that must cut material to reach its hole fails. It meets no other screw, on its path or in its place, and the other screw is taken where its head holds it, which that screw's own `fit.fastener` checks. A tip that runs past the stack into a battery fails `fit.fastener` and names the battery.
- **Seats.** The first hole is read from the mesh just below its mouth, grown by the allowance on both sides and by the shift of the hole the thread enters. A socket head at its least catalogue diameter must cover that hole at its widest, and its bearing ring must lie on the first part's face. A countersunk head at its greatest diameter must fit the countersink at its narrowest, so it sits at or below the surface, and the countersink in the mesh must narrow enough to stop it.
- **Grip.** The engaged length is the least length of thread past the stack, with the head at its seat. It must reach `parts.engagement.<role>` diameters, a judged constant per hole role (1.5 for tap and insert, 2 for form, all guesses). A tap or form hole is read from the mesh over that length. As made, its widest diameter plus twice the allowance must stay inside the thread's basic pitch diameter, taken as `d - 0.65 P`, and solid material must reach past the crest by the allowance. ISO 724 gives the pitch diameter as `d - 0.6495 P` as recalled (guess), and 0.65 rounds it up so the rule errs safe. An insert must take the screw's thread size, and its length must reach 1.5 diameters. In a blind hole the tip, at the screw's greatest length with the head held at its seat, must stop short of the floor the hole's axis meets.
- **Press fits.** A pressed pair may overlap. The hole is read over the whole length the pin crosses the part from the hole's mouth. The pin must sit in its hole, which means the hole's axis meets no material over that length, the pin holds the axis, and the hole's wall there lies inside the pin. So a pin driven past a blind hole's floor fails, and so does a hole that steps wider partway along the pin, since only a uniform press is modelled. The least interference is twice the least distance from the hole's wall to the pin's side faces, and the most is twice the pin's greatest radius less the hole's least. Each moves by twice both allowances and by the hole's shrink, and both must lie in the declared range. The pair counts as a stop.
- **Gaps.** A gap line's two parts keep the stated gap plus both allowances apart, swept over their floats when they float along one axis. A gap line between parts that touch always fails.

Every distance is exact. `exact.py` decides triangle distances, sweeps, parity and coplanar overlap on Python integers, with every coordinate an exact rational. A coordinate, pad or sweep that reaches 2^60 units of the common denominator is refused with an input error, so the int64 arrays that hold boxes never wrap. The statement squares both sides, so a distance `d` against an allowance sum `s` is stated as `s^2 - d^2 <= 0` with `d^2` an exact rational.

## What a verdict means

Each verdict is relative to its premises, and the footprint lists every one.

- **PASS** means the rule holds at every point of the premise box. The box spans the declared tolerances, shrinks, buildups, masses and temperatures, and the material a tolerance or a coat can add to or take from a part. So a fit that passes holds at the tightest corner, and a mass that passes holds for the heaviest part the tolerances allow.
- **FAIL** means the kernel found a point of that box where the rule breaks, and the readout names the point and the triangles. A FAIL under tolerance means the declared tolerances allow the clash, not that every part made will clash.
- **UNKNOWN** means a needed bound is missing, such as a part with no process and no tolerance line, or a rule has no model.

Each rule adds premises of its own.

- `fit.*` reads the mesh as the part, with its surface anywhere within its allowance. That holds for holes, threads, presses, seats and insert holes too, and no rule but `fit.hole` takes a declared diameter as the hole's size. A screw is its circumscribed prism at its greatest size, so a PASS holds for the real screw, and a FAIL by less than the circumscription, about 0.5 % of the radius (inferred), is a FAIL of the model. A part does not float sideways. Rotations are the 24 axis turns, so placed coordinates stay exact.
- A hole in a mesh is a polygon whose sides lie inside its corners by `r (1 - cos(pi / n))`, 0.48 % of the radius for 32 sides (inferred). A polygon drawn with its corners on the declared radius fails `fit.hole` at any tolerance below that. Draw the polygon around the circle, or declare its inscribed diameter.
- `fit.hole` bounds the hole from below, so a mesh hole larger than declared passes it. The rules that need more of a hole than that bound, `fit.grip`, `fit.seat`, `fit.press` and the insert rules, read it from the mesh themselves.
- `print.volume` and its kin read the mesh frame with +z up and the bed at the lowest vertex. A part that fits only when turned fails.
- `print.bridge` treats a face over air as held on an edge where the face across it falls below it, and free where it rises. A face held on every edge and no wider than the bridge's low end passes, because lines laid across its narrower side span at most that side. A face with a point farther than half the bridge from all its edges fails, because every straight line through that point spans more. Any other face, and any face with a free edge, which is an overhang, leaves the rule open.
- `sheet.prism` passes a mesh whose every vertex lies on its two level faces and whose every other face is upright. Faces in two upright planes meet only on upright edges, so every cross-section is the same. A bent part fails, because v0 reads no bend lines.
- `part.temperature` reads the ambient from the design's `ambient` line or its environment class, and the heat deflection temperature at 0.45 MPa (ISO 75-2 method B). Creep under sustained load is not checked.
- `parts.mass` moves each part's volume by the shell within its allowance of its surface. Every point of that shell lies within `a` of a face, of an edge where the surface bends, or of a vertex on such an edge, so the shell holds at most `area a + 4 ridge a^2 + 5 corners a^3` (inferred, since pi < 4 and 4 pi / 3 < 5). A coat weighs at most its density times twice that shell. A printed part with no `fill` line counts as solid, which bounds its mass from above only. So a `<=` claim is stated only when it holds that way, and a `>=` claim needs the fill.
- `parts.cg` weighs each solid part at its exact centroid, moved along its insert axis by its float. Material the shell adds beyond the claim's plane, or takes away before it, moves the moment by at most the shell's mass times the part's farthest reach past the plane. A bought or infilled part sits at its `cg` line. Screws and inserts sit anywhere along their length on their axes, off them by the hole's shift.

## The mesh is a solid

`read_mesh` reads ASCII decimals as written and each float32 as its shortest round-trip decimal, and scales every coordinate to an integer over one power of ten, at most 10^13. A coordinate whose integer reaches 2^60 is refused. It requires every edge to be used by exactly two triangles, once in each direction. An edge shared by four faces, a duplicated face and an open boundary all fail that rule. It refuses two triangles on the same three vertices, because a doubled wall drawn as two opposite triangles passes the edge rule and bounds nothing. Every piece must enclose volume, and the whole mesh positive volume. A piece is a set of triangles joined through shared edges, so two shells that touch at one vertex are two pieces. The scaffold's parity rule accepted all of these (audit rows D-152 and D-158).

`exact.surface_problem` finds what the edge rules cannot see, and `lower_part` refuses the mesh with its message. Two triangles that meet anywhere but at the vertex or the edge they share mean the surface crosses or touches itself, so two triangles that share one vertex are tested too. Two coplanar triangles that overlap and face opposite ways are a wall of zero thickness, or the internal face where two bodies touch. Two neighbours folded onto each other fail too. Each piece is probed for its nesting at the centroid of one of its triangles. A piece nested an even number of times must face outward and a piece nested an odd number of times inward, so a void is a void and not a second body.

## Presets

Every row is judged by petra-maintainers and labelled with its source. A design overrides a row with a signed line. `tests/test_parts_table.py` fails when a row's label does not start with reported, inferred or guess.

| Preset | Row | Value | Label |
|---|---|---|---|
| `process.print.fdm_pla_0_4`, `fdm_petg_0_4` | tolerance | 0.5 mm, or 0.5 % of the span when larger | guess, recalled from the Hubs FDM design guide |
| | hole_shrink | 0.1 to 0.2 mm | guess |
| | bridge | 5 to 10 mm | reported, two Hubs pages (audit row E-010) |
| | build | 250 x 210 x 220 mm | reported, Prusa MK4 |
| `process.powder.sls_pa12` | tolerance | 0.3 mm, or 0.3 % of the span when larger | guess, recalled from the Hubs SLS design guide |
| | hole_shrink | 0 to 0.2 mm | guess |
| | build | 340 x 340 x 600 mm | guess |
| `process.sheet.laser_al_3` | tolerance | 0.127 mm | reported, SendCutSend |
| | thickness | 3 mm | guess |
| | bed | 1200 x 600 mm | guess |
| `process.mill.al6061_3axis` | tolerance | 0.13 mm | reported, Hubs, Protolabs and SendCutSend (audit row E-138) |
| `process.anodize_ii` | buildup | 0.005 to 0.0125 mm | guess |
| `process.powder_coat` | buildup | 0.05 to 0.12 mm | guess |

The scaffold's milling tolerance was 0.05 mm. Shops publish 0.1 to 0.13 mm for standard milling (reported, audit row E-138), so the preset now holds 0.13 mm. A part whose span puts the rate past the floor is held to the rate, so a 245 mm bar printed in PETG is held to 1.23 mm each side (inferred).

Polymers (PLA, PETG, ABS, ASA, PA12, polycarbonate) carry density, glass transition and heat deflection rows, all guesses from typical datasheets. Screws are ISO 4762 socket heads in M2.5, M3 and M4 and ISO 10642 countersunk heads in M3 and M4, each 6 to 20 mm long. Their greatest head diameters and head heights are reported from the standards' tables as maker catalogues print them. Their least head diameters, their length limits and their coarse pitches are recalled, not read from a source on disk (guess), and rounded so the rules that read them err safe. Their masses are inferred from steel density and their volume over the length range. Heat-set inserts in M3 and M4 carry hole range, length, least wall and mass, all guesses from typical catalogues.

## Premises and certificates

The engine measures each geometric fact once per model, in exact rationals. `build.py` states each fact as a design value labelled `dsg:`, beside the registry rows (`reg:`) and the signed bounds (`in:`) it is compared with. The kernel checks the R4 goal over that box. So the kernel checks the arithmetic, and the engine's measures are trusted. Each evaluator is a validated model premise hashed over the module's source, `model:parts.geometry`, `model:parts.thermal` and `model:parts.mass`.

No kernel rule was added. R4 carries every goal.

## Testing

| Module | What it proves | Tests |
|---|---|---|
| `tests/test_parts_mesh.py` | the reader takes exact coordinates and refuses every non-solid surface | 15 |
| `tests/test_parts_exact.py` | the integer primitives agree with dense sampling, and the surface rules catch crossings, zero-thickness walls and wrong nesting | 14 |
| `tests/test_parts_layer.py` | each modelled rule passes a design worked by hand and fails a one-line mutation of it, end to end through `petra.check` | 32 |
| `tests/test_parts_review.py` | each false PASS the review of `parts-core` found, and four more found since by reading the fixed rules, now fails, refuses or stays open | 34 |
| `tests/test_parts_table.py` | the table, the builders and the registered domain agree, and every preset row is labelled | 6 |
| `tests/test_parts_gate.py` | one generated design of each family keeps its verdicts under four relations and catches its plants, and two faults patched in are caught | 5 |

Each FAIL test differs from a passing design in one thing, so it is the rule's own mutation test. `powder.volume` and `sheet.bed` share `print.volume`'s builder and have no test of their own.

`scripts/parts_gate.py` is the layer's generated gate. It makes designs in five families, a lid screwed to a base, a board dropped into a tray, a peg pressed into a block, a heat-set insert in a printed part, and a milled block with mass claims. Each design is sized to pass with room, and the gate asks two things of it.

- **Relations.** Every obligation keeps its outcome when the design turns 90 or 180 degrees about z, when each mesh frame moves and its placement moves back, when the assembly moves, when flat edges are split at their midpoints, when the triangles are reordered, when each triangle starts at its next corner, when coordinates are written with six decimals, when the first part's frame moves 10^5 mm with one corner 1e-13 mm out, and when every length doubles. The frame move puts a coordinate at 1.0e18 units against the 2^60 limit of 1.15e18 (inferred), and a refusal there is allowed and counted. Doubling applies only where every bound is signed or scales with length, the press family and a bare milled block, whose mill tolerance the variant signs at twice 0.13 mm and whose unmodelled mill rules it leaves out. Screws, inserts and print presets are catalogue or absolute values, so their families are not doubled. Turning by 90 degrees leaves out the build-volume rules, whose machine axes do not turn with the part.
- **Plants.** A mutation that breaks the design never comes back PASS. The plants move a part into another, thin a wall past what its rule needs, swap a screw for the next size, open a press hole past its pin, shrink or shorten an insert's hole, grow a board into the tray's allowance, nest a void or an outward shell in a solid block, and move a broken design's first frame as far as the frame relation does.

On 300 designs from seed 1 at 2ff27e4, the gate ran 3,749 s on five workers beside the full suite, and no relation broke, no plant passed and no design crashed (measured). 290 bases pass. The other 10 are countersunk stacks that the layer's own conservative models fail, 7 by `fit.fastener`, which takes the head as a prism, and 3 by `fit.hole`, whose countersink cone, shrunk by the allowance, the drawn polygon does not hold (measured). The relations held in 2,610 checks, 90 of them doublings (measured). 60 frame moves were refused at the limit (measured). They are the stack family's (inferred, from the 13 stack designs checked and the counts), whose moved coordinates reach past 2^60. All 980 plants were caught, 170 of them as input errors when the push plant met the same limit (measured).

Built and run on this branch, the gate found two faults in the layer. Splitting a face's edges broke `fit.insert` on an enclosure, because stops were read triangle by triangle, and stops are now read by face. One press design took 645 s, 219 s of it in one check, and the check now prunes its triangle pairs by box and takes 12.9 s (measured). The gate checks whole designs, so it could not see the four obligations found by reading the fixed rules, each in a design another rule already failed. A screw reach was trusted with the head free to pass its hole, in three ways, and a press was read only to the hole's declared depth.

No second implementation judges the layer yet. The gate tests the layer against itself, and the debt is recorded in `tests/trusted_base.py`. The plan is a clean-room twin of analytic assemblies, such as boxes in boxes with known gaps and pins in polygonal holes of known inscribed radius. One relation from the first plan is not in the gate yet. Moving two parts apart should never turn a fit PASS into a FAIL.

## Not checked yet

- **Circuit boards.** The scaffold's KiCad reader was deleted. Boards are meshes with a signed tolerance. Connectors, switches, LEDs and mounting holes do not yet create access, actuator, light path or keep-out obligations, and through-hole leads below a board are not keep-outs.
- **Bent sheet.** `sheet.prism` fails a bent part. Flange length, hole-to-bend distance, bend relief and tab-and-slot need bend lines declared on the part, which is a grammar change.
- **Printing.** Least feature, thin wall, least hole, overhang and support access have no model. Bridges are decided only when a face is narrow and held all round or plainly too wide. Warp and elephant's foot are not checked.
- **Milling.** Tool reach and least feature have no model.
- **Threads.** No rule sets a least size for a tap or form hole, so a hole too small for its tap or for a thread-forming screw passes `fit.grip`.
- **Fit.** A driver's access to a screw head, washers, assembly order beyond place-line order, and cable routing. A part does not float sideways, so two boards in one pocket can pass a gap line across their travel that a sideways slide would close (review L5). A part resting on a slope or a cone has no flat face to stop on, so it rests on nothing and fails (review FF5).
- **Mesh reading.** A binary STL's float32 is read as its shortest decimal, which can sit up to half a unit in its last place from the float (review L6). A coordinate that needs more than 13 decimals, as float32 noise written to an ASCII file can, is refused (review FF3).
- **Strength.** No parts load case is checked, such as a boss splitting under a thread-forming screw or a snap fit's strain.

## Line budget

The kernel gains no line (measured; the branch touches nothing under `petra/kernel/`). The parts modules hold 2,877 trusted code lines, counted with `tests/test_kernel_budget.code_lines` (measured), against 2,250 on `parts-core` (measured).

| File | Code lines (measured) |
|---|---|
| `petra/models/parts/mesh.py` | 222 |
| `petra/models/parts/space.py` | 40 |
| `petra/models/parts/exact.py` | 419 |
| `petra/models/parts/rules.py` | 95 |
| `petra/models/parts/lower.py` | 431 |
| `petra/models/parts/engine.py` | 829 |
| `petra/models/parts/build.py` | 616 |
| `petra/models/parts/domain.py` | 61 |
| `petra/models/parts/__init__.py` | 2 |
| `petra/registry/parts.py` | 162 |

The whole trusted base holds 16,423 code lines (measured), against 13,530 before the parts work began (measured at 140f742).
