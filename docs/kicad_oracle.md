# The board reader against KiCad

`scripts/kicad_oracle.py` reads real KiCad boards with Petra's board reader (docs/boards.md) and compares every number with what KiCad itself reads and exports from the same file. KiCad is the oracle. A pad the reader places, a hole it sizes, or an outline it bounds is checked against KiCad's own reading, its Excellon drill file, its Gerber copper flashes and its Gerber board edge. This page gives the result and the cause of every disagreement.

Every number carries a label. **Measured** means run or read on 2026-11-09 for this page. **Inferred** means reasoned from measured facts. **Recalled** means from memory of KiCad's behaviour, not checked here. The page changes nothing in the reader.

## Outcome

1. **Every placement number agrees with KiCad.** Over the 77 boards the reader reads, 4,794 footprint anchors, angles and faces, 24,777 pads, 6,711 vias and 77 thicknesses agree with KiCad 10's reading, and 2,790 footprints and 13,260 pads with KiCad 7's. The worst pad error is 0.69 nm, inside KiCad's own nanometre rounding (measured). 11,189 holes, 433 slots and 6,711 vias match KiCad's Excellon in place, size and plating, and 23,214 pad centres match KiCad's Gerber flashes (measured).
2. **The outline bounds hold every arc as the file writes it, and KiCad draws some arcs elsewhere.** KiCad computes an arc's centre from its three written points, rounds it, and draws the arc about it. Its centre lies up to 0.063 um from the exact centre of the circle through those points (measured). On 10 boards KiCad's arc, and the Gerber KiCad plots from it, crosses the reader's outer or inner polygon by up to 0.069 um (measured). Swapping each such arc for the circle through its written start, mid and end removes every miss, down to float noise of 0.003 nm (measured). Over the Edge.Cuts arcs of 52 boards, KiCad's drawn ends stray up to 0.088 um from the written ones (measured).
3. **A locked reference is read as the word "locked".** KiCad 6 and 7 write a locked footprint text as `(fp_text reference locked "J1" ...)`, and the reader takes the reference and the value to be `locked` (measured on a real KiCad 6 board and on a board KiCad 7 wrote for this page). The reference then picks no feature mark of its own.
4. **KiCad's own demo boards state two thicknesses.** Four demo files state 1.6002 mm in `(general ...)` and stackups that sum to 1.6 mm or 1.600198 mm. KiCad 10 reports 1.6002 mm for all four, and KiCad 7 for the two it reads (measured). The reader refuses these files, so docs/boards.md's "KiCad keeps the two equal" does not hold, though the refusal is safe.
5. **The reader refuses 40 of 116 real boards, each for a reason docs/boards.md lists.** 12 have Edge.Cuts gaps KiCad closes on its own, 11 hold bezier curves, 11 have footprint Edge.Cuts at angles off the quarter turns, 4 state two thicknesses, 1 has a KiCad 8 footprint with no Value field and 1 is a KiCad 9 demo file shipped with a stray parenthesis (measured). KiCad loads all 40.

## How the oracle was built

KiCad ran on an Ubuntu ARM virtual machine. KiCad 10.0.8 came from Flathub and KiCad 7.0.11 from Ubuntu's own packages, because the KiCad 9 package archive builds no ARM binaries (measured). KiCad 10 reads all four formats Petra reads, KiCad 6 to 9, and KiCad 7 reads the KiCad 6 and 7 ones.

The boards are 116 files in four formats.

| Source | Boards |
| --- | --- |
| KiCad's demo boards, from the Debian and Ubuntu `kicad-demos` packages 6.0.11, 7.0.11, 8.0.8 and 9.0.8 | 55 |
| 15 public hardware repositories on GitHub (Glasgow, HackRF, Cynthion, Bitaxe, Sensor Watch, the MCH2022 badge, the Antmicro Jetson Nano baseboard, LibreSolar BMS C1, Olimex ESP32-C3, Voron hardware, and the Corne, Corney Island, Sweep, Sofle and Lily58 keyboards) | 61 |
| One board KiCad 7 wrote for this page (below) | 1 |

| Format | Read | Refused |
| --- | --- | --- |
| KiCad 6 (20211014) | 18 | 10 |
| KiCad 7 (20221018) | 28 | 16 |
| KiCad 8 (20240108) | 12 | 5 |
| KiCad 9 (20241229) | 19 | 9 |

The boards Petra reads hold 1,398 bottom footprints on 50 boards and 198 footprints at angles off the quarter turns on 19 boards, 174 of them on the bottom. They hold 433 oval drills on 26 boards, 112 pads with a drill offset on 5 boards, 194 arcs in outlines on 21 boards and 8 cutouts on 3 boards (measured).

For each board, `scripts/kicad_oracle_dump.py` ran inside KiCad's Python and wrote KiCad's reading in integer nanometres. `kicad-cli` wrote the Excellon drill files (decimal, absolute origin, slots as G85), Gerber X2 for the copper and Edge.Cuts layers with pad attributes, and the placement file.

Truth is what KiCad computes and exports, with two exceptions. KiCad's courtyard caches are shrunk by about 5 um, and its polygons place arc points up to 0.5 um off the arc (measured). The oracle samples the drawn courtyard and Edge.Cuts shapes instead. KiCad rounds every point to the nanometre, so placement checks allow 1 nm beyond the reader's own stated error, and outline and courtyard checks allow 2 nm.

### The constructed board

No real board here holds an arc inside a polygon or a drill offset on the bottom face, and only one holds a locked reference. `construct.py`, kept with the oracle data, makes KiCad 7 write all three into the pic_programmer demo. It turns one capacitor by 33.3 degrees and flips it to the bottom with KiCad's own Flip, and turns another by 147.5 degrees on top. It gives every through-hole pad of both a drill offset and one of them an oval drill, and locks the texts of connector J1. KiCad's Python cannot build an arc inside a polygon, so an Edge.Cuts polygon with an arc goes in as text and KiCad reads the file and writes it again. Every coordinate in the file is KiCad's.

## Checks

From `python scripts/kicad_oracle.py ORACLE_DIR` over all 117 boards, of which the reader reads 77 (measured). The full log is docs/kicad_oracle_log.jsonl.

| Check | Compared | Disagree | Worst |
| --- | --- | --- | --- |
| Excellon holes the reader lacks | 74 | 0 | 0 |
| committed Excellon holes the reader lacks | 15 | 2 | 0 |
| committed hole in Excellon | 74 | 74 | 0 |
| committed hole place vs Excellon | 863 | 0 | 0.00154 |
| committed hole plating vs Excellon | 863 | 4 | 0 |
| committed hole size vs Excellon | 863 | 0 | 0.00086 |
| committed slot vs Excellon | 10 | 0 | 0 |
| committed via in Excellon | 176 | 176 | 0 |
| committed via place vs Excellon | 873 | 0 | 0.00177 |
| courtyard bracketed | 4,128 | 0 | 9.66e-07 |
| courtyard read | 9,588 | 16 | 0 |
| courtyard within deviation | 4,128 | 0 | 5.63e-07 |
| hole place vs Excellon | 11,189 | 0 | 0.000707 |
| hole plating vs Excellon | 11,189 | 0 | 0 |
| hole size vs Excellon | 11,189 | 0 | 0.0004 |
| k10 footprint anchor | 4,794 | 0 | 0 |
| k10 footprint angle | 4,794 | 0 | 0 |
| k10 footprint order | 2 | 2 | 0 |
| k10 footprint side | 4,794 | 0 | 0 |
| k10 pad angle (absolute) | 24,777 | 0 | 0 |
| k10 pad copper | 24,777 | 0 | 6.87e-07 |
| k10 pad drill | 11,154 | 0 | 0 |
| k10 pad kind | 24,777 | 0 | 0 |
| k10 pad offset | 24,777 | 0 | 0 |
| k10 pad place (hole centre) | 24,777 | 0 | 6.85e-07 |
| k10 thickness | 77 | 0 | 0 |
| k10 via | 6,711 | 0 | 0 |
| k7 footprint anchor | 2,790 | 0 | 0 |
| k7 footprint angle | 2,790 | 0 | 0 |
| k7 footprint order | 2 | 2 | 0 |
| k7 footprint side | 2,790 | 0 | 0 |
| k7 pad angle (absolute) | 13,260 | 0 | 0 |
| k7 pad copper | 13,260 | 0 | 6.87e-07 |
| k7 pad drill | 5,830 | 0 | 0 |
| k7 pad kind | 13,260 | 0 | 0 |
| k7 pad offset | 13,260 | 0 | 0 |
| k7 pad place (hole centre) | 13,260 | 0 | 6.85e-07 |
| k7 thickness | 46 | 0 | 0 |
| k7 via | 3,361 | 0 | 0 |
| outline (Edge.Cuts Gerber) bracketed | 77 | 10 | 6.89e-05 |
| outline (Edge.Cuts Gerber) within deviation | 77 | 1 | 1.64e-05 |
| outline (KiCad Edge.Cuts shapes) bracketed | 77 | 10 | 6.89e-05 |
| outline (KiCad Edge.Cuts shapes) within deviation | 77 | 1 | 1.84e-05 |
| outline (KiCad shapes, written arcs) bracketed | 77 | 0 | 2.25e-09 |
| outline (KiCad shapes, written arcs) within deviation | 77 | 0 | 5.86e-14 |
| outline loop count | 77 | 0 | 0 |
| pad copper vs Gerber flash | 23,214 | 0 | 6.87e-07 |
| pos side | 4,365 | 0 | 0 |
| slot vs Excellon | 433 | 0 | 0.0007 |
| via place vs Excellon | 6,711 | 0 | 0.000707 |

The worst column is the largest error among the items compared, in mm. The `committed` rows compare the drill files each repository ships, explained below.

## Each disagreement and its cause

**Outline arcs, 10 boards.** The nearest true point to each miss lies on an arc. At (91.580005, 52.989918) on the Corney Island backplate, KiCad holds the arc's centre at (91.5801, 53.49) with radius 0.500082 mm. The circle through the written points has its centre at (91.580052, 53.490021) and radius 0.500034 mm, so KiCad's arc ends 0.069 um past the line it should meet (measured). KiCad's Gerber agrees with KiCad's arc. Read against the written circles, every board is bracketed (measured). On Sofle v2 an arc too small for the default tolerance gets bounds at 0.0001 mm, and KiCad's arc strays 0.018 um past their stated deviation, while the written circles stay within it (measured). The reader is right about the file, and the board maker cuts KiCad's arc. The gap is over 1,000 times smaller than the 0.1 mm a board maker's cut strays (recalled), which the reader already demands as the edge tolerance premise.

**Footprint order, one real board and the constructed one.** These are the locked references, U1 on the Sofle v2 board and J1 on the constructed one. The comparison matches footprints by file order and reference, so the pads of these two are not compared.

**Courtyards the reader cannot read, 16.** KiCad builds a courtyard where the reader finds an open end or a loop inside another (measured). The reader marks these NoCourtyard, and a keep-out on that face raises. That is a refusal, not a wrong answer.

**Repository drill files, 4 boards.** Glasgow revC3 and Bitaxe Ultra write slots as routed paths (M15), which the oracle does not read, and Glasgow ships one file for plated and unplated holes. Olimex ESP32-C3 Rev C and Rev D ship drill files from another origin. The KiCad 10 exports of the same boards agree with the reader (measured).

## The six readings

docs/boards.md lists six readings of the format docs that it could not settle.

| Reading | Verdict |
| --- | --- |
| y points down and a positive angle turns counter-clockwise on screen | Holds. 4,794 anchors and angles and 24,777 pads agree with KiCad, 198 footprints among them at angles off the quarter turns (measured). |
| A pad's angle is absolute, not relative to its footprint | Holds. 24,777 pad angles agree with KiCad 10 and 13,260 with KiCad 7 (measured). |
| A bottom footprint's children are stored already mirrored | Holds. The pads and courtyards of 1,398 bottom footprints agree with KiCad, 174 of them at angles off the quarter turns (measured). |
| A drill offset moves the copper and not the hole | Holds. 112 offset pads on 5 boards, 2 of them on a footprint flipped to the bottom at 33.3 degrees, put the hole on the pad's anchor in KiCad's reading and its Excellon, and the copper at the offset in KiCad's reading and its Gerber (measured). |
| An `(arc ...)` inside `(pts ...)` is an arc | Holds on the one board that has one. KiCad 7 wrote it back as written, and the reader's bounds hold KiCad's arc and its Gerber (measured). |
| `(general (thickness ...))` and the stackup agree | The reader's refusal is safe, and the docs' claim that KiCad keeps the two equal is false. KiCad's own demos differ by up to 0.2 um, and KiCad reports the general value (measured). |

## Limits

The oracle compares the reader with KiCad. It does not judge whether a courtyard holds its part, whether `features.RULES` names a part rightly, or which premises the reader demands.

KiCad 8 and 9 did not run, so KiCad 10 stands in for them. It read every KiCad 8 and 9 file here (measured). The real boards lean to keyboards and open hardware, and only 2 of them have cutouts. One constructed board carries the arc in a polygon and the bottom-face drill offset. Gerber flashes cover only the pads KiCad flashes, not custom shapes it fills as regions.

## Reproduce

The oracle data is not in the repository. On a machine with KiCad 10, for each board:

```
python3 scripts/kicad_oracle_dump.py BOARD k10.json      # inside KiCad's Python
kicad-cli pcb export drill -o drill/ --format excellon --drill-origin absolute \
  --excellon-zeros-format decimal --excellon-oval-format alternate -u mm --excellon-separate-th BOARD
kicad-cli pcb export gerbers -o gerber/ -l Edge.Cuts,F.Cu,B.Cu --no-protel-ext BOARD
kicad-cli pcb export pos -o pos.csv --format csv --units mm --side both BOARD
```

Then, with Petra's Python:

```
python scripts/kicad_oracle.py ORACLE_DIR --out OUT
```
