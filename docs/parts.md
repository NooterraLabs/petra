# Parts and assemblies

Petra checks physical parts that agents make in code-CAD. A part is a closed triangle mesh with a material and, unless it is bought, a process preset. An assembly places parts, says how each one arrives at its place, and names the screws, gaps and press fits that join them. Each check proves its rule at the worst case of every declared tolerance, refutes it at the point that breaks it, or says what it needs to decide.

The layer lives in `petra/models/parts/` and `petra/registry/parts.py`. The scaffold that came before it is on branch `parts-scaffold`. This page describes branch `parts-core`.

Every number carries a label. **Measured** means run or counted on this branch. **Reported** means a shop, maker or datasheet publishes it on the page named. **Inferred** means reasoned from measured or reported facts. **Guess** means nobody has signed it.

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

claim light: box.mass <= 30 g
```

It is checked the way every design is.

```
petra check examples/parts/assembly.petra
petra check examples/parts/assembly.petra --json
```

The run gives UNKNOWN with 13 obligations, 8 certified and 5 open (measured). The board goes in at the worst corner of both tolerances and rests on the tray. The tray fits the printer, nothing on it spans air, and PETG and polycarbonate keep their shape in an indoor room. The 5 open obligations are print rules with no model yet, and each names the waiver that would close it. `petra new part` and `petra new assembly` print the two examples, and `petra kinds part` prints every line a part takes.

A mesh path is read relative to the design's file. A design given as text must name absolute paths. The sha256 pins the file, so a changed mesh is an input error until the hash is updated.

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

A hole is declared so that rules can read what the mesh cannot say. Its mouth is the point, and it runs along the axis into the part. `clear` lets a screw pass. `tap` and `form` take a screw's thread in metal and in plastic. `insert` takes a heat-set insert from the registry. `press` takes a pin.

## The assembly block

| Line | Says |
|---|---|
| `place <part> at <point> facing <axis> <axis>` | where the part sits, its top and front turned to the two axes; the first place line is the base |
| `insert <part> along <axis> from <length>` | the part arrives moving along the axis over that length; every part but the base has exactly one |
| `fasten <id> <screw> through <part>.<hole> ... into <part>.<hole>` | a screw through clear holes, head side first, into the hole its thread enters |
| `gap <part> <part> [<length>]` | two parts that keep apart by the length beyond their allowances |
| `press <id> <part> into <part>.<hole> diameter <length> interference <length> to <length>` | a pin pressed into a press hole, with its diametral interference range |

Claims bound `mass` on a part, and `mass`, `cg_x`, `cg_y` and `cg_z` on an assembly. Parts take no loads in v0, and lowering refuses a load on them.

## Rules

`rules.RULES` is the one table. Each row names the feature it is demanded on, what failing it means, and the evaluator that decides it. Failure modes, coverage rules and builders derive from the table. A row with no builder is still demanded, and its obligation stays open with a waiver line until a builder exists.

| Rule | Demanded on | Evaluator | Holds when |
|---|---|---|---|
| `fit.insert` | every placed part but the base | geometry | the part travels its insert path clear of every other part by both allowances, rests on something at its place, and lies inside nothing |
| `fit.connected` | every placed part | geometry | the part touches, is fastened to or is pressed into a part placed before it |
| `fit.gap` | each gap line | geometry | the two parts keep the stated gap beyond both allowances |
| `fit.fastener` | each fasten line | geometry | the screw, as a body, reaches its hole clear of every part but the one it threads into |
| `fit.seat` | each fasten line | geometry | a socket head bears on the first part's face, or a countersunk head sits in a declared countersink |
| `fit.grip` | each fasten line | declared | the thread engages enough diameters and does not bottom in a blind hole |
| `fit.press` | each press line | declared | the diametral interference stays in the declared range over both tolerances |
| `fit.hole` | each declared hole | geometry | the mesh holds the hole as declared, and its countersink when one is declared |
| `insert.hole_size` | each insert hole | declared | the hole as made, the declared diameter less its shrink, lies in the insert's catalogue range |
| `insert.depth` | each insert hole | declared | the hole runs at least the insert's length |
| `insert.boss_wall` | each insert hole | geometry | the wall around the insert is at least the catalogue's least wall |
| `part.temperature` | each polymer part | thermal | ambient plus the declared local rise stays at or below the material's heat deflection temperature |
| `print.volume`, `powder.volume`, `sheet.bed` | each made part | geometry | the mesh's extent, grown by its allowance on both sides, fits the machine |
| `print.bridge` | each printed part | geometry | every face printed over air spans at most the preset's bridge between the edges that hold it |
| `sheet.prism` | each sheet part | geometry | the part is a flat profile of the stock's thickness |
| `parts.mass` | a mass claim | mass | the summed mass of parts, screws and inserts meets the claim |
| `parts.cg` | a centre of mass claim | mass | the mass-weighted centre meets the claim along one axis |
| `fit.driver`, `print.min_feature`, `print.thin_wall`, `print.min_hole`, `print.overhang`, `print.support_access`, `powder.min_feature`, `powder.escape`, `sheet.min_web`, `mill.reach`, `mill.min_feature` | as named | none yet | open, with a waiver line |

The table holds 30 rules, 19 with builders and 11 without (measured).

## Fit under tolerance

A fit check that passes on nominal geometry proves little. A 0.25 mm gap passes at nominal and closes when a printed wall comes out 0.5 mm thick. So every fit rule holds at the worst case of the tolerances the design and its presets declare.

- **Allowance.** Each part's true surface lies within its allowance `a` of the mesh, both ways. The allowance is the profile tolerance, from the preset or a signed `tolerance` line, plus a finish's buildup. Against a screw a printed part's allowance also holds half its hole shrink, because printed holes come out small.
- **Order.** Parts go in in place-line order. The base is placed. Every other part arrives along its insert axis from the stated distance.
- **Stops and float.** A part stops on the faces it touches at its place whose triangles lie wholly ahead of its own along the travel. It may then sit anywhere along its axis within its float, `F = max over its stops of (F_stop + a_stop + a_self)`. Across the axis it does not float.
- **Path.** The part is swept from its start to its place and on past it by its float. Every triangle pair but its stops must keep apart by both allowances. When the other part floats along a different axis, that float joins the allowance.
- **Resting and containment.** A part with no stop rests on nothing and fails. A part whose vertex lies inside another part by ray parity fails.
- **Screws.** A screw is a body. Its shank is the circumscribed 32-sided prism of its major diameter, and a socket head adds the circumscribed prism of the head. Its axis is the declared axis of the hole its thread enters, and its head sits at the first hole's mouth. It may overlap only the part it threads into. A tip that runs past the stack into a battery fails `fit.fastener` and names the battery.
- **Seats.** A socket head's bearing ring runs from the hole's radius plus the allowance to the head's radius plus the allowance. The ring must lie on the first part's face, and the head must not pass the hole. A countersunk head needs a declared countersink at least the head's catalogue diameter plus twice the allowance, and `fit.hole` checks that the mesh holds the cone.
- **Grip.** The engaged length is the screw's length past the stack. It must reach `parts.engagement.<role>` diameters, a judged constant per hole role (1.5 for tap and insert, 2 for form, all guesses). In a blind hole it must stay inside the hole's depth.
- **Press fits.** A pressed pair may overlap. The diametral interference at both ends of both tolerances must lie in the declared range, and the pair counts as a stop.
- **Gaps.** A gap line's two parts keep the stated gap plus both allowances apart, swept over their floats when they float along one axis.

Every distance is exact. `exact.py` decides triangle distances, sweeps, parity and coplanar overlap on integers, with every coordinate an exact rational. The statement squares both sides, so a distance `d` against an allowance sum `s` is stated as `s^2 - d^2 <= 0` with `d^2` an exact rational.

## What a verdict means

Each verdict is relative to its premises, and the footprint lists every one.

- **PASS** means the rule holds at every point of the premise box. The box spans the declared tolerances, shrinks, buildups, masses and temperatures. So a fit that passes holds at the tightest corner.
- **FAIL** means the kernel found a point of that box where the rule breaks, and the readout names the point and the triangles. A FAIL under tolerance means the declared tolerances allow the clash, not that every part made will clash.
- **UNKNOWN** means a needed bound is missing, such as a part with no process and no tolerance line, or a rule has no model.

Each rule adds premises of its own.

- `fit.*` reads the mesh as the part, with its surface anywhere within its allowance. A screw is its circumscribed prism, so a PASS holds for the real screw, and a FAIL by less than the circumscription, about 0.5 % of the radius (inferred), is a FAIL of the model. A part does not float sideways. Rotations are the 24 axis turns, so placed coordinates stay exact.
- `fit.hole` bounds the hole from below. A mesh hole larger than declared passes. Insert holes are read as the declared diameter less the shrink row, and the profile tolerance is not applied to them, because insert holes are sized to a printer's measured shrink.
- `print.volume` and its kin read the mesh frame with +z up and the bed at the lowest vertex. A part that fits only when turned fails.
- `print.bridge` treats a face over air as held on an edge where the face across it falls below it, and free where it rises. A face held on every edge and no wider than the bridge's low end passes, because lines laid across its narrower side span at most that side. A face with a point farther than half the bridge from all its edges fails, because every straight line through that point spans more. Any other face, and any face with a free edge, which is an overhang, leaves the rule open.
- `sheet.prism` passes a mesh whose every vertex lies on its two level faces and whose every other face is upright. Faces in two upright planes meet only on upright edges, so every cross-section is the same. A bent part fails, because v0 reads no bend lines.
- `part.temperature` reads the ambient from the design's `ambient` line or its environment class, and the heat deflection temperature at 0.45 MPa (ISO 75-2 method B). Creep under sustained load is not checked.
- `parts.mass` counts a printed part with no `fill` line as solid, which bounds its mass from above only. So a `<=` claim is stated only when it holds that way, and a `>=` claim needs the fill. `parts.cg` weighs each solid part at its exact centroid, a bought or infilled part at its `cg` line, and screws and inserts at the centres of their head and shank cylinders.

## The mesh is a solid

`read_mesh` reads each float32 as its shortest round-trip decimal and scales every coordinate to an integer over one power of ten. It requires every edge to be used by exactly two triangles, once in each direction. An edge shared by four faces, a duplicated face and an open boundary all fail that rule. It refuses two triangles on the same three vertices, because a doubled wall drawn as two opposite triangles passes the edge rule and bounds nothing. Every connected piece must enclose volume, and the whole mesh positive volume. The scaffold's parity rule accepted all of these (audit rows D-152 and D-158).

`exact.surface_problem` finds what the edge rules cannot see, and `lower_part` refuses the mesh with its message. Two triangles that share no vertex and meet mean the surface crosses or touches itself. Two coplanar triangles that overlap and face opposite ways are a wall of zero thickness, or the internal face where two bodies touch. Two neighbours folded onto each other fail too. A piece nested an even number of times must face outward and a piece nested an odd number of times inward, so a void is a void and not a second body.

## Presets

Every row is judged by petra-maintainers and labelled with its source. A design overrides a row with a signed line. `tests/test_parts_table.py` fails when a row's label does not start with reported, inferred or guess.

| Preset | Row | Value | Label |
|---|---|---|---|
| `process.print.fdm_pla_0_4`, `fdm_petg_0_4` | tolerance | 0.5 mm | reported, Hubs FDM design guide |
| | hole_shrink | 0.1 to 0.2 mm | guess |
| | bridge | 5 to 10 mm | reported, two Hubs pages (audit row E-010) |
| | build | 250 x 210 x 220 mm | reported, Prusa MK4 |
| `process.powder.sls_pa12` | tolerance | 0.3 mm | reported, Hubs SLS design guide |
| | hole_shrink | 0 to 0.2 mm | guess |
| | build | 340 x 340 x 600 mm | guess |
| `process.sheet.laser_al_3` | tolerance | 0.127 mm | reported, SendCutSend |
| | thickness | 3 mm | guess |
| | bed | 1200 x 600 mm | guess |
| `process.mill.al6061_3axis` | tolerance | 0.13 mm | reported, Hubs, Protolabs and SendCutSend (audit row E-138) |
| `process.anodize_ii` | buildup | 0.005 to 0.0125 mm | guess |
| `process.powder_coat` | buildup | 0.05 to 0.12 mm | guess |

The scaffold's milling tolerance was 0.05 mm. Shops publish 0.1 to 0.13 mm for standard milling (reported, audit row E-138), so the preset now holds 0.13 mm.

Polymers (PLA, PETG, ABS, ASA, PA12, polycarbonate) carry density, glass transition and heat deflection rows, all guesses from typical datasheets. Screws are ISO 4762 socket heads in M2.5, M3 and M4 and ISO 10642 countersunk heads in M3 and M4, each 6 to 20 mm long. Their head sizes are reported from the standards' tables as maker catalogues print them, and their masses are inferred from steel density and nominal volume. Heat-set inserts in M3 and M4 carry hole range, length, least wall and mass, all guesses from typical catalogues.

## Premises and certificates

The engine measures each geometric fact once per model, in exact rationals. `build.py` states each fact as a design value labelled `dsg:`, beside the registry rows (`reg:`) and the signed bounds (`in:`) it is compared with. The kernel checks the R4 goal over that box. So the kernel checks the arithmetic, and the engine's measures are trusted. Each evaluator is a validated model premise hashed over the module's source, `model:parts.geometry`, `model:parts.declared`, `model:parts.thermal` and `model:parts.mass`.

No kernel rule was added. R4 carries every goal.

## Testing

| Module | What it proves | Tests |
|---|---|---|
| `tests/test_parts_mesh.py` | the reader takes exact coordinates and refuses every non-solid surface | 15 |
| `tests/test_parts_exact.py` | the integer primitives agree with dense sampling, and the surface rules catch crossings, zero-thickness walls and wrong nesting | 14 |
| `tests/test_parts_layer.py` | each modelled rule passes a design worked by hand and fails a one-line mutation of it, end to end through `petra.check` | 31 |
| `tests/test_parts_table.py` | the table, the builders and the registered domain agree, and every preset row is labelled | 6 |

Each FAIL test differs from a passing design in one thing, so it is the rule's own mutation test. `powder.volume` and `sheet.bed` share `print.volume`'s builder and have no test of their own.

No outside checker judges the layer yet. The debt is recorded in `tests/trusted_base.py`. The plan is a clean-room twin of analytic assemblies, such as boxes in boxes with known gaps and pins in polygonal holes of known inscribed radius, with these metamorphic relations.

- An axis turn and a rational shift of a whole assembly leave every verdict unchanged.
- Scaling every length and bound by 2 leaves every verdict unchanged.
- Moving two parts apart never turns a fit PASS into a FAIL.
- Splitting a triangle into coplanar triangles changes nothing.

## Not checked yet

- **Circuit boards.** The scaffold's KiCad reader was deleted. Boards are meshes with a signed tolerance. Connectors, switches, LEDs and mounting holes do not yet create access, actuator, light path or keep-out obligations, and through-hole leads below a board are not keep-outs.
- **Bent sheet.** `sheet.prism` fails a bent part. Flange length, hole-to-bend distance, bend relief and tab-and-slot need bend lines declared on the part, which is a grammar change.
- **Printing.** Least feature, thin wall, least hole, overhang and support access have no model. Bridges are decided only when a face is narrow and held all round or plainly too wide. Warp and elephant's foot are not checked.
- **Milling.** Tool reach and least feature have no model.
- **Fit.** A driver's access to a screw head, washers, sideways float, assembly order beyond place-line order, and cable routing.
- **Strength.** No parts load case is checked, such as a boss splitting under a thread-forming screw or a snap fit's strain.

## Line budget

The kernel gains no line (measured; the branch touches nothing under `petra/kernel/`). The parts modules hold 2,250 trusted code lines, counted with `tests/test_kernel_budget.code_lines` (measured).

| File | Code lines (measured) |
|---|---|
| `petra/models/parts/mesh.py` | 211 |
| `petra/models/parts/space.py` | 40 |
| `petra/models/parts/exact.py` | 385 |
| `petra/models/parts/rules.py` | 86 |
| `petra/models/parts/lower.py` | 431 |
| `petra/models/parts/engine.py` | 456 |
| `petra/models/parts/build.py` | 435 |
| `petra/models/parts/domain.py` | 61 |
| `petra/models/parts/__init__.py` | 2 |
| `petra/registry/parts.py` | 143 |

The whole trusted base holds 15,796 code lines (measured), against 13,530 before the parts work began (measured at 140f742).
