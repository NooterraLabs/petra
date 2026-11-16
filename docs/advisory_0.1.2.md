# A wrong pass in version 0.1.2

Version 0.1.2 passes a bolted lap that should fail when its design misstates its own surface or its own holes. Version 0.2.0 refuses such a design. If you rely on a pass that 0.1.2 gave a lap, check that the `surface` and the `holes` its design wrote are those of the built joint, or check it again with 0.2.0.

## What was wrong

In 0.1.2 the design of a lap wrote two keys that decide which rules answer for it, and nobody signed either.

| Key | What it picks |
|---|---|
| `surface` | The greatest spacing of the bolts (AISC 360-22 J3.6): 24 thicknesses for painted steel, 14 for unpainted weathering steel |
| `holes` | The end and side distances (Tables J3.4 and J3.5), which grow for an oversize hole |

So one word in the design picked the more generous rule.

The case is in the corpus, run through the released 0.1.2 on 2026-11-15:

| Design | What it is | 0.1.2 | 0.2.0 |
|---|---|---|---|
| `corpus/cases/deck/d21_weathering_over_14t` | Weathering steel with a pitch of 5.5 inch, over the 5.25 inch that 14 thicknesses allow | FAIL | FAIL |
| `corpus/cases/deck/d42_design_writes_its_surface` | The same lap, with `surface protected` written in its design | PASS_WAIVED | refused |

## What 0.2.0 does

Only the card states the two keys, with a signature, as it states a strength:

```
given splice.holes is standard signed "s.engineer@example.org" source "connection drawing, hole schedule"
given splice.surface is weathering signed "s.engineer@example.org" source "connection drawing, coating note"
```

The design reads them:

```
  holes given splice.holes
  surface given splice.surface
```

A design that writes either key itself is refused, and the message says what to write. A deck whose `when` reads a key that a design may state is refused when it is read, so no later deck brings the fault back by that way ([deck.md](deck.md), "The grid").

A card and a design written for 0.1.2 need those four lines to be read by 0.2.0.

## What 0.2.0 does not close

A design still states what its designer chooses: the group of its bolts, and whether their threads are excluded from the shear plane. Both raise the strength that the rules allow. A pass holds for the joint as the card and the design describe it, and nothing checks that the built joint is that one.

## What to do

```bash
pip install -U petra-lang
```

## Reporting a wrong pass

Open an issue with the design and card that reproduce it. A report becomes a case in the corpus.
