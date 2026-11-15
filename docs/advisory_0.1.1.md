# Wrong passes in version 0.1.1

Version 0.1.1 passes designs that should not pass. Version 0.1.2 passes none of them. If you rely on a pass that 0.1.0 or 0.1.1 gave, treat the design as not checked and check it again.

## What was wrong

In 0.1.1 a verdict came from a model written in Python for each kind of part. A model checks what its author thought of, and nothing asks what it left out.

An audit on 2026-11-09 wrote designs that should not pass. Each is in `corpus/cases/audit/` with the reason it should not. Run through the released 0.1.1 on 2026-11-15, 15 of them pass:

| Design | What 0.1.1 does not check |
|---|---|
| `s01_plate_on_thin_web`, `s02_stiffened_seat_on_thin_web` | The web that the connection loads out of its plane |
| `s03_declared_eccentricity` | A stated eccentricity takes the place of the one the geometry gives |
| `s04_edge_distance_tearout` | Tearout along the bolt force |
| `s06_fillet_larger_than_angle_toe`, `s07_fillet_on_seat_angle`, `s07_fillet_on_tee_flange_tip` | The largest fillet weld an edge allows (AISC 360-22 J2.2b) |
| `s09_seat_longer_than_flange` | A seat longer than the flange that bears on it |
| `s10_girder_without_cope` | A beam framed into a girder with no cope stated |
| `s11_slots_too_close` | The clear distance between slots (AISC 360-22 J3.4) |
| `s12_gauge_on_web_fillet` | A hole placed on the web's fillet |
| `s13_end_plate_gauge_clash` | Bolt heads that overlap the web weld |
| `t2_load_through_param` | A load that comes only through a parameter nobody signs |
| `w1_design_waives_its_own_checks` | A design that waives its own bolt and block shear checks |
| `w2_truss_waives_collapse` | A truss that waives collapse, stability and buckling |

The files there are in today's form, a card and a design. Version 0.1.1 reads the two joined in one file, with `card` written as `design`. Version 0.1.0 is older code of the same kind and was not run. Twelve more of the audit's designs use kinds or lines that 0.1.1 does not read, so they say nothing about it.

## What 0.1.2 does

The verdict is the kernel's, and the kernel passes a design only against a deck of rules. One kind of part has a deck today, a bolted lap splice. A design of any older kind reads unknown, with the reason that its kind has no deck. That covers the other steel connections, trusses, wire circuits and bolted joints. A fail of an older kind stays where the kernel itself checked the refutation.

So 0.1.2 answers fewer designs than 0.1.1 did. Of the 15 above, the twelve steel connections read unknown. The other three are refused before any check: a waiver belongs in the card and not in the design, and a load is signed on the card.

## What to do

```bash
pip install -U petra-lang
```

Start the server as `petra mcp`. Started as `python -m petra mcp` from a folder that holds a file named `petra.py`, Python loads that file in Petra's place.

## Reporting a wrong pass

Open an issue with the design and card that reproduce it. A report becomes a case in the corpus.
