# Circuit boards

An agent that designs an enclosure starts from a KiCad board file. Petra reads that file straight into one typed record of exact facts, so every later enclosure check starts from the board the designer drew. A misread board, such as a bottom footprint mirrored twice or a wrong thickness, would make every later verdict wrong. So the reader reads each number exactly, refuses what it cannot read exactly, and is tested against a second reading written apart from it.

The reader lives in `petra/models/boards/`. The enclosure deck will wire it into the parts layer (docs/parts.md). This page describes branch `kicad-reader`.

Every number carries a label. **Measured** means run or counted on this branch. **Reported** means a source publishes it on the page named. **Inferred** means reasoned from measured or reported facts. **Guess** means nobody has checked it. A convention known from KiCad's behaviour and its files, with no page read here that states it, is marked **recalled**. Constants the code chooses, such as the 0.01 mm default tolerance, are choices and not claims, so they carry no label.

## Usage

```python
from petra.models.boards import Errs, board_solid, keepout, read_board

board = read_board("controller.kicad_pcb")
board.thickness                       # Thickness(value=Fraction(8, 5), source='setup.stackup'), or None
for footprint in board.footprints:
    footprint.reference, footprint.side, footprint.features, footprint.missing
board.leads()                         # every plated through-hole pad, with its footprint
over = board_solid(board, Errs.OVER)  # a Prism whose mesh holds the drawn board
room = keepout(board, board.footprints[0], 0, 12, Errs.OVER)  # 12 mm is a premise, not a fact
```

## What is read

Board files of KiCad 6, 7, 8 and 9. Each version below is the last of its development cycle in `pcbnew/pcb_io/kicad_sexpr/pcb_io_kicad_sexpr.h` on KiCad's 9.0 branch (reported), and so the one its release series writes (inferred).

| version | KiCad | reference and value |
|---|---|---|
| 20211014 | 6 | `(fp_text reference "J1" ...)`, or `(fp_text reference locked "J1" ...)` for a locked text |
| 20221018 | 7 | `(fp_text reference "J1" ...)`, or `(fp_text reference locked "J1" ...)` for a locked text |
| 20240108 | 8 | `(property "Reference" "J1" ...)`, since version 20230620, "PCB Fields" (reported, same header) |
| 20241229 | 9 | `(property "Reference" "J1" ...)` |

KiCad 6 and 7 write a locked text's `locked` before the text. The reader skips that bare word, so the locked J1 of KiCad 7's rewrite of the pic_programmer demo and the locked U1 of Sofle v2 read as J1 and U1 (measured, docs/kicad_oracle.md). A quoted `"locked"` is a text like any other.

Every length is an exact rational in millimetres, read from the file's decimals, so 2.54 is 127/50. The record holds these.

- **Outline.** The Edge.Cuts loops, one boundary and its cutouts. Lines, arcs and circles are kept exact. Board items (`gr_line`, `gr_arc`, `gr_circle`, `gr_rect`, `gr_poly` with arc entries) and footprint items on Edge.Cuts both count.
- **Thickness.** The sum of the stackup's layer thicknesses, labelled `setup.stackup`, else `(general (thickness ...))`, labelled `general.thickness`. A file that states neither gets no thickness, never a default.
- **Footprints.** Reference, value, library id, face, anchor and angle, `attr` words, pads, a courtyard for each face, the feature marks and the missing premises.
- **Pads.** Number, kind, whether plated, shape, place in the footprint, angle, size, drill, the copper's offset from the hole, and the place on the board. The kinds are SMD, connect, through-hole, NPTH and mounting hole. A drilled pad of a footprint marked as a mounting hole is a mounting hole, plated or not.
- **Through-hole leads.** `Board.leads()` lists each plated through-hole pad outside a mounting hole, with its board place and drill.
- **Vias.** Place, drill, and whether the via passes through the board.

## The record

```
Board        path, sha256, version, kicad, outline, thickness | None, footprints, vias, missing
Outline      boundary: Loop, cutouts: (Loop, ...)
Loop         items: (Segment | Arc | Circle, ...), closed, simple, region on its left
Segment      start, end
Arc          start, mid, end              three points as the file writes them
Circle       center, through
Bounds       inner, outer: polygons, deviation
Thickness    value, source                "setup.stackup" or "general.thickness"
Footprint    reference, value, library, side, placement (at, angle), attributes,
             pads, courtyards (top, bottom), marks, missing
Pad          number, kind, plated, shape, local, angle, size, drill | None, offset, at: Spot, properties
Drill        width, height, oval
Spot         point, error                 the true point lies within error of point
Courtyard    face, loops (footprint frame, exact), board: (Bounds, ...), room: Bounds
NoCourtyard  face, reason                 "absent", or what is wrong with the drawn one
Via          at, drill, through
Prism        mesh, errs, low, high, deviation
```

## Frames and turns

KiCad's board frame has x to the right and y down, in millimetres (recalled). A footprint at (X, Y) turned by A degrees puts a child stored at (x, y) at

    X + x cos A + y sin A,    Y - x sin A + y cos A

so a positive angle turns the part counter-clockwise on screen (recalled). A pad's angle in the file is its orientation on the board, with the footprint's angle already in it (recalled). When KiCad flips a footprint to the bottom face it mirrors the children and stores them as they then lie, so one transform places children on either face (recalled). Mirroring a bottom footprint again is the mistake the tests watch for most closely.

A turn by a multiple of 90 degrees is exact. Any other angle takes its cosine and sine from thirty terms of their series with pi bounded to 1e-40, rounded to 24 decimals, and the error is carried. A point placed at such an angle is rounded to a 1e-9 mm grid and kept as a `Spot` with a bound on its error. The largest pad error on the test boards is 8.5e-10 mm (measured).

The solids use a mesh frame with x as the board's x, y as minus the board's y, and z out of the top face. The frame is right-handed, and the board fills 0 <= z <= thickness.

## The outline

Lines and arcs join where their ends are equal exactly, and each end must meet exactly one other. A loop must not cross or touch itself, two loops must not meet, one loop must hold all the others, and no cutout may lie inside another.

A mesh cannot hold an arc, so `plane.bounds` gives each loop an inner polygon inside its region and an outer polygon holding it, with corners on a decimal grid. Each arc is cut into bends of at most a quarter turn at rational points, the start turned by 90 degrees about the rational centre. A bend turning with the loop bulges out of the region, so the inner polygon takes a chord path inside the circle and the outer one a tangent path outside it. A bend turning against the loop, as in a notch, takes the other two. Floats propose the corners, and exact checks accept them or refuse them. The default tolerance is 0.01 mm, a mesh-size choice and not a fact about any board.

### Why the bounds are sound

A chord path's corners lie strictly inside the circle and turn one way about the centre inside the bend's wedge. So each ray from the centre through the wedge meets the path once and the arc once, and the path with the arc bounds a lune with winding number 0 or 1 at every point. A tangent path's corners lie outside the circle, its edges miss the closed disc but at the bend's ends, and it turns the same way, so it bounds a lune the same way.

Every lune lies on the region's side of its bend. The inner polygon's boundary is the loop less each lune's boundary, so its winding number at a point is the loop's less the number of lunes holding the point. Outside the region that is 0 or below. The code checks that the polygon is simple and positively oriented, so its winding number is 0 or 1 everywhere, and every point outside the region has winding number 0 with respect to it. The inner polygon lies in the region. The outer polygon's winding number is the loop's plus the lunes', so it is at least 1 at every point of the region, and the outer polygon holds the region.

The deviation bounds how far each polygon strays from its arc. A chord path keeps between the radius r and the least distance n from the centre to the path, so it strays at most r - n, which the code bounds above by (r^2 - n^2) / (lower root of r^2 + lower root of n^2). A tangent path keeps between r and its farthest corner f, at most (f^2 - r^2) / (2 lower root of r^2). Each point of either path meets the arc along its ray from the centre, and each point of the arc meets the path along the same ray.

### Turned courtyards

A courtyard's bounds are turned with the decimal cosine c and sine s. If c and s are each within e of the true values, a point at local (x, y) lands within e (|x| + |y|) of its true place, because the error matrix is a scaled rotation. The outer polygon is then grown by more than that reach and the inner one shrunk. Exact checks confirm that each grown polygon is simple, holds the turned one, and keeps every edge further than the reach from the turned one's edges. A point of the true image lies within the reach of a point of the turned polygon, which lies further than the reach from the grown boundary, so it lies inside it. The same holds inward for the shrunk polygon.

### Rooms

A courtyard is the area a footprint's author keeps clear for the part, and it does not always hold the part. KiCad's StickHub demo draws the body of a JST SH connector 1.295 mm past its courtyard on the F.Fab layer, and a capacitor laid over the board's edge 11.5 mm past it. Over the boards of docs/kicad_oracle.md, 37 of 4,057 footprints draw a Fab body more than 0.01 mm outside the courtyard (measured, docs/kicad_oracle.md's boards).

So a part's room on a face is the convex hull of the face's courtyard and of every line, arc, circle, rectangle and polygon the footprint draws on the face's Fab layer, F.Fab for the top and B.Fab for the bottom. The hull is one convex region that holds both. A concave courtyard grows to its hull, which an OVER keep-out may do. Text on the Fab layer is not a shape and is not read. A shape on the Fab layer that the reader cannot read makes the courtyard on that face a `NoCourtyard`.

`plane.enclose` bounds the hull. Its inner polygon is the hull of the inner polygons' corners and of points on the Fab shapes: segment ends and the ends of each arc's quarter-turn bends, all exact. Each lies in the true hull, so the inner polygon does. Its outer polygon is the hull of the outer polygons' corners, of segment ends, and of each bend's ends with its tangent path. A bend lies between its chord and its tangent path along every ray from its centre through its wedge, so the outer polygon holds every bend and the true hull. The three regions are convex and nested. Let d be the furthest any corner of the outer polygon lies from the inner one. Then every point of the outer boundary lies within d of the inner polygon and so of the true boundary, and every point of the true boundary lies within d of the inner polygon's boundary, and the same holds outward along each supporting line. d is the room's deviation. `plane.moved` turns the room onto the board as it turns a courtyard.

### Holes

A round hole of radius r whose centre is known within e has an inner convex polygon with every corner nearer than r - e to its centre, and an outer convex polygon whose every edge line lies further than r + e from it. An oval drill is a slot, the set of points within r of a segment, along the pad's x axis when it is wider than tall and along its y axis otherwise, turned by the pad's angle. The same two tests apply to the segment, because the points within a distance of a segment make a convex set.

## Solids

`board_solid(board, errs)` builds the board as an exact mesh for the parts layer. `Errs.OVER` holds the drawn board, so it takes the outer polygon of the boundary less the inner polygons of the cutouts and holes. `Errs.UNDER` lies inside it, so it takes the inner polygon of the boundary less the outer polygons of the cutouts and holes. An UNDER solid cuts every hole, vias included. An OVER solid may leave holes uncut and still hold the board. It cuts no blind or micro via, since such a via ends inside the board. Both solids bound the drawn board, not the board as made. How far the made board strays is a premise (below).

`keepout(board, footprint, low, high, errs)` sweeps the room on the footprint's face (above, "Rooms") from `low` to `high` mm out from that face, or from the face named, and returns one prism. A part's height is a premise, so the caller gives both heights.

Each face is cut into triangles by joining every hole to the boundary with a bridge and clipping ears. The cut is not trusted. An exact check confirms that every triangle turns positively, that no edge is used twice in one direction, and that the edges left after opposite pairs cancel are exactly the region's boundary edges, each in its own direction. The triangles then form a 2-chain whose boundary is the region's boundary, so at each point their count equals the region's winding number, 1 inside and 0 outside. Positive triangles cannot cancel one another, so they cover each point of the region once and no point outside it. The mesh then passes the parts layer's own check of a solid's boundary (`petra/models/parts/mesh.py`), in which every edge has exactly one face in each direction.

## What is refused

Each refusal is a `BoardError` naming the file and, where it can, the line.

- A file that is not UTF-8, an unclosed string, a stray or missing parenthesis, or more than one top-level list.
- A file whose top list is not `kicad_pcb`, and any version but the four above, nightly builds included.
- A number with an exponent or anything but a plain decimal. KiCad writes none (reported, dev-docs.kicad.org, s-expression format, "Syntax").
- No outline; an open outline; three or more ends meeting at a point; a loop that crosses or touches itself; two loops that meet; loops of which none holds all the others; a cutout inside a cutout.
- A bezier curve on Edge.Cuts, an arc whose three points lie on one line, a circle of radius 0, a line of length 0, a rectangle with no area.
- Edge.Cuts items in a footprint turned by an angle that is not a multiple of 90 degrees, since their board coordinates are not rational.
- An arc that comes within 0.0001 mm of another edge, or two edges that meet at a zero angle, since no polygon can bound them. How often real outlines do this is not measured.
- A footprint off F.Cu and B.Cu, a reference or value not written the way its version writes it or written with no text, a pad type outside smd, connect, thru_hole and np_thru_hole, a drilled pad with no drill, a pad with no size, and a via with no drill.
- A stackup whose layers sum to a thickness other than the one in `(general ...)`. KiCad does not keep the two equal. Four of its own demo boards state 1.6002 mm in `(general ...)` and stackups that sum to 1.6 mm or 1.600198 mm, and KiCad 10 reports 1.6002 mm for all four (measured, docs/kicad_oracle.md). Neither number says which thickness the board is made to, so the reader refuses the file and names both.

A courtyard Petra cannot read, or a Fab shape on its face, is not refused. The courtyard becomes `NoCourtyard` with the reason, and a keep-out on that face raises `BoardError`. A solid whose hole bounds meet each other or the edge's bounds is refused, as a hole cut by the board's edge is.

## What the file cannot tell the enclosure deck

A board file holds no part height, no mating direction and no light path. `features.py` names each fact it lacks as a `Premise`, and the enclosure deck must demand each as a signed line. The marks come from the reference's letters, the words of the library id and a pad's test-point property. The words are the runs of letters in the library's nickname and the footprint's name, split where a small letter meets a capital, so `kbd:ResetSW` gives kbd, reset and sw. The table and its sources are `features.RULES`. The words of KiCad's own library names are reported from kicad.github.io/footprints. The other words are measured, read off the library ids on the boards of docs/kicad_oracle.md. Reference letters are recalled from IEEE 315 class letters, KiCad's symbol defaults and common use.

| feature | marked by | premise demanded |
|---|---|---|
| mounting hole | library words mounting hole, reference H, MH | fastener |
| connector | library words connector, connectors, terminal block, conn, connect, usb, header, pin socket, jack, jst, molex, hirose, idc, fpc, ffc, dsub, trrs, hdmi, rj, reference J, P, CN | mating direction and room |
| switch | library words button, buttons, switch, sw, tactile, tact, spdt, spst, reference SW, S | actuator direction and travel |
| LED | library words led, leds, reference LED, DS | light path |
| test point | library words test point, testpoint, reference TP, pad property `pad_prop_testpoint` | probe access |

Any mark adds its premise. Only the library id makes a footprint a mounting hole, and only when no other row marks it. Its drilled pads are then mounting holes, and it lacks no height. The letter H alone does not, since a standoff such as KiCad's `Mounting_Wuerth` parts stands 5 mm off the board under the same H (inferred from the H5mm in its name). A footprint with pads that no row marks lacks its **access**, whether light, a hand, a plug or a probe must reach it, so a part the rows miss still reaches the deck as a premise.

On the boards of docs/kicad_oracle.md, the footprints whose library id or value names an LED, a switch or a connector, by patterns written apart from `RULES`, numbered 244, 227 and 471 when the rows read only library nicknames, and 139, 22 and 93 of them lacked that mark (measured). With the library words they number 247, 227 and 479, and 0, 0 and 40 lack the mark (measured). The counts grew because footprints with a locked reference now read their reference and match KiCad's list (inferred). Of the 40, 39 are LEDs, test points and packages the audit's own patterns catch by mistake, such as `Duo_LED` and `VQFN`, and one is a terminal block with reference TB, which carries the access premise (measured).

Every footprint with pads that is not a mounting hole also lacks its **height** above its face, and one with drilled pads lacks its **lead protrusion** beyond the far face. Every board lacks its **thickness as made**, a range, its **edge tolerance**, the board maker's cut against the drawn outline, and, when it has holes, the **hole size as made**. A thickness the file states is the drawn one, so a slot sized to a stated 1.6 mm passes on the file alone and may not take a board made thicker. Board makers commonly quote 10% either way (recalled). Petra keeps no such figure, so the deck gives the range whether or not the file states a thickness, and builds the OVER solid at its top and the UNDER solid at its bottom with `board_solid(..., thickness=...)`.

Petra keeps no table of typical package heights. Every height is a premise.

The reader skips copper, tracks, zones, solder mask, silkscreen, 3D models, board material, castellations, flex regions and text, and refuses footprints outside F.Cu and B.Cu.

## Readings of the KiCad docs that are not settled

The developer docs (dev-docs.kicad.org, "S-Expression Format" and "Board File Format") give the tokens but leave these open. Each is recalled from KiCad's behaviour and files, and each is a place a misreading would hide.

- **Which way y and angles run.** The docs state neither. The reader takes y down and positive angles counter-clockwise on screen.
- **Pad angles.** The docs say a pad's `at` holds its "orientation angle" and not whether the footprint's angle is in it. The reader takes it as the pad's orientation on the board, with the footprint's angle in it.
- **Bottom footprints.** The docs do not say whether a bottom footprint's children are stored mirrored. The reader takes them as stored mirrored.
- **Drill offset.** The docs call `(offset x y)` in a drill the "drill offset from the pad center". The reader follows KiCad's pad model, in which the hole sits at the pad's place and the offset moves the copper (recalled). If the docs' words are literal, a pad with an offset has its hole in the wrong place. No test board here can decide it.
- **Thickness.** The docs do not relate `(general (thickness ...))` to the stackup. KiCad's own demo boards differ in the two by up to 0.2 um (measured, docs/kicad_oracle.md). The reader refuses a file where they differ.
- **Arcs in polygons.** The docs describe `pts` as `xy` points only. The reader also reads `(arc (start ...) (mid ...) (end ...))` entries, as KiCad 7 and later write in polygons (recalled).

## Testing

`python -m unittest tests.test_boards_kicad` runs 41 tests in about 20 s on a busy desktop (measured). Every board is written in the test file by hand, and no third-party board is copied.

- Each version header reads, the four versions give one record, and six other versions and a missing one are refused.
- Arcs stay exact, with their bounds on the named sides, for convex corners and for a concave notch. On 164 exact points of the rounded corners, and on 41 points against each path of one bend alone, no point strays further than the stated deviation and some stray further than half of it. A round board and KiCad's six-decimal arc mids read.
- Cutouts, footprint Edge.Cuts and outline items in any order and direction.
- The probe part at 0, 90, 37.5 and 270 degrees against positions worked by hand, and on the bottom face as KiCad stores it, mirrored.
- A through-hole connector with an oval drill, plated and unplated mounting holes, NPTH pegs, a drill offset, vias, missing and broken courtyards, a missing stackup, and no thickness.
- Twenty-eight malformed files and two unreadable ones, each refused with its message.
- **Metamorphic.** Turning the whole file by 90, 180 or 270 degrees and moving it by a decimal shift moves the outline, every footprint's anchor and angle, every pad and via, and each quarter-turn courtyard by exactly that motion, and every pad at 37.5 degrees by exactly that motion too. The 37.5 degree courtyard still holds its true corners after the motion. Flipping any footprint to the other face mirrors its pads, and flipping it twice gives back the same record.
- **Second reading.** `tests/board_second_reading.py` was written by a separate agent that never saw the reader. It places each pad from first principles in floats. On 16 boards every pad agrees with the reader within the reader's error plus 1e-9 mm (measured).
- **Solids.** A polygon board with a cutout is exact, at 1888 mm^3 for both OVER and UNDER. Round boards and the rich test board bracket their true volumes within bounds on pi. The parts layer's own surface check (`exact.surface_problem`) finds no defect in the five meshes it is run on.

Planting one mistake at a time in the reader, the tests caught 16 of 16 (measured). The mistakes were a rotation the other way, quarter turns the other way, bottom footprints mirrored again, bottom angles negated again, pad angles read as relative to the footprint, a default thickness, the stackup ignored, footprint Edge.Cuts left in the footprint's frame, loops allowed to meet, concave arcs bounded like convex ones, decimals read through floats, OVER and UNDER voids swapped, a slot along the wrong axis, no y flip in the mesh frame, and the chord and the tangent deviations each understated by a factor of 4. The two deviation mistakes survived until the dense arc checks were added.

## Line budget

The kernel gains no line, and no file under `petra/models/parts/` changes (measured). The board modules hold 1,217 trusted code lines, counted with `tests/test_kernel_budget.code_lines` (measured). `tests/trusted_base.py` records them as the group "boards", with the second reading named in its debt because it judges pad places only.
