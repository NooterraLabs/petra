# The first run of rules from the page

Two transcribers each wrote the rules for every line of a lap's grid from the pages of ANSI/AISC 360-22, on 2026-11-11. They were two different models, and neither saw the other's rules or the rules of the shipped deck. A third agent collected worked examples from the AISC Design Examples v16.0 without seeing any rule.

| File | Holds |
|---|---|
| `rules_task2.json` | The task: the types, the rows (the deck's and the 14 of `a3.json`), and the 15 mechanisms |
| `rules2_a.json`, `rules2_b.json` | The two transcriptions as handed in |
| `rules2_examples.json` | The 8 worked examples as collected |

```bash
python -m petra.rule bench/formalizer/rules_task2.json bench/formalizer/rules2_a.json --second bench/formalizer/rules2_b.json --examples bench/formalizer/rules2_examples.json
```

## Result

| Mechanism | The two transcriptions | Worked examples |
|---|---|---|
| Minimum spacing | Agree at 132 sampled parts | 1 reproduced |
| End distance, standard and oversize holes | Agree at 128 | 2 reproduced |
| Side distance | Agree at 128 | none found |
| Strength of the bolts and their holes | Agree at 140 | 2 reproduced |
| Yielding of each plate | Agree at 128 | 1 reproduced |
| Rupture of each plate through a hole | Agree at 128 | 1 reproduced |
| Block shear of each plate | Agree at 128 | 1 reproduced |
| Tension with shear, slip, a plate in shear, a plate in compression | Both say it cannot arise | |
| Maximum spacing and edge distance | Differ | none found |
| Use of the hole type | One says it cannot arise for standard holes and leaves the rest out, the other leaves it all out | |
| Tightening, bending of the plates | Both left out | |

So seven lines have rules that two readers of the page agree on, six of them with a printed number behind them. The shipped deck has rules for three.

## What the run showed

- The one disagreement came from the task. It defines the side distance as the least over both plates, and Section J3.6 limits the greatest, for each plate. One transcriber wrote the rule from the least and the other refused to, saying why. The line needs splitting, and the edge half needs a field the lap lacks.
- Both transcribers met the same limit of the rule format: a rule cannot choose between a table and its last line, which is a formula, by the size of the bolt. So bolts of 1 1/8 inch and over are left open on four lines. A row with cases for the hole diameter would mend it.
- Both left out the same things for the same reasons: note a of Table J3.4, which permits a lesser edge distance on conditions that are not quantities, and the pair of equations for a joint where deformation of the hole is not a design consideration, for which the lap has no key.
- The source has no lap of two plates worked whole. Every example is a part of another connection: one line of bolts, or one plate. The three for a plate give that plate's fields alone, so they test the rules of one plate, as `petra/rule.py` now does for an example of one of several like parts.
- All eight examples use a 3/4 inch Group 120 bolt with threads included, in 50 ksi steel. None tells another size, group or grade apart.

## What it does not show

Each transcriber saw one rule of the shipped deck in the manual, and a sample report that names two more by their equations. Their four agreements that a mechanism cannot arise match the manual's count. The rules have not been put in the deck, and the shipped deck's four rules have not been compared with these.
