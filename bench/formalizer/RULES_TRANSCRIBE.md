# Writing the rules for a task

You are given a task and a standard. You write the rules that answer the task's mechanisms. Someone else writes them too, from the same task and the same standard. A machine compares the two, part by part, and admits a mechanism only where they agree. That works only if neither of you has seen the other's rules.

## What you are given

- The task, a JSON file. It holds the types, with the fields and loads of each kind of part, the rows you may use, and the mechanisms to answer, each with the clause that raises it.
- The manual: `docs/deck.md`. Read "A row" for the language of expressions, "A deck" for a type, the grid and a rule, and "A transcription" for what you hand in.
- The standard, and the pages to read. Read it in place. `python bench/formalizer/pages.py FILE.pdf FIRST-LAST` renders pages as images under the system's temporary folder, so that you see what is typeset.

## What you must not see

- Another transcription of this task, here or anywhere else.
- The rules of a deck in `petra/decks` for the same types. A deck's rows and types are yours to read, and its rules are not.
- A worked example. Do not look for one to check a rule against.

The manual shows a rule of the first deck as its example. If your task is that deck's, say in your notes what you saw of it.

## The standard is licensed

Do not copy its prose, keep its pages, commit them or send them anywhere. A rule's `says`, the `why` of a range and the `why` of an `unless` are your own words. An anchor names the clause, the equation and the table, and quotes nothing.

## What you hand in

One JSON file.

```json
{"transcriber": "who or what wrote this",
 "source": "the edition, and the pages read",
 "rules": [],
 "unless": [{"mechanism": "...", "why": "..."}],
 "left_out": [{"mechanism": "...", "why": "..."}]}
```

Every mechanism of the task is in one of the three lists, or in two when you answer part of it. Do one of three things with each.

- Write its rule, or its rules.
- Say that it cannot arise, under `unless`, and why. Add `when` if it cannot arise for some parts only.
- Leave it out, under `left_out`, and say what stopped you.

## Writing a rule

1. Read the mechanism's clause, and every clause it sends you to.
2. Use the task's names. A field is its name. A field of a joined part is `a.thickness`, by the name the type gives the part in `as`. A load is `["load", "pull"]`.
3. Use the task's rows. What the standard gives as an equation or a table, a rule reads as `["row", ID, {...}]`, with each input bound. Do not write a row's formula again in a rule.
4. Write in the rule what the clause leaves to the reader: an area from a width and a thickness, a clear distance from a spacing and a hole. A factor that the clause fixes for the inequality, such as a resistance factor, is a number in the rule.
5. Write the inequality as the clause states it. What the part must carry or must have goes on the left, and what it can carry or may have on the right. A load is at most a strength. A least distance is at most the part's distance. Do not move a term to the other side: write `a <= b`, and not `a - b <= 0`. The left side over the right is the ratio a report prints.
6. Give the rule a `when` if it holds only for parts with some key, or only for parts that carry some load.
7. Give the rule a `where` for each condition of the clause that compares quantities and that the rule does not take care of itself. If the clause changes a value past some length and your rule does not, the rule holds up to that length, and says so. Outside its `where` a rule says nothing, and a design there stays open. Do not leave a condition out because parts seldom meet it.
8. Write `says` in your own words: the inequality, as a sentence.

One requirement of the clause is one rule. Where a clause asks the same of each of two parts, a rule for each and one rule with their `min` are both right, and the check counts them the same.

## What a transcriber gets wrong

- A safe shortcut. If the clause sums a strength over the bolts, sum it. The count times the weakest bolt is safe and is another rule, and the check will tell the two apart.
- The other part. `a.thickness` with `b.Fu` is seldom what a clause means.
- The neighbouring symbol: `Fy` for `Fu`, a gross area for a net one, a hole's diameter for a bolt's.
- The column of a table. Say which column each name of a key reads, with `["by", FIELD, {...}]` where the type's names and the table's differ.
- The task's ranges. They are where the check samples parts. They are not limits of the standard, and no rule reads them.
- Another edition. Where your memory of the standard and the page differ, the page is right. Say which edition you read.

## What to leave out, and say

- A mechanism whose clause needs a field the type does not have. Name the field.
- A mechanism whose clause needs an equation or a table that the task has no row for. Name it.
- A requirement that is not an inequality between quantities, such as a ban on one name of a key, or a choice that depends on what the part is for. Do not write a made-up inequality in its place.
- A condition that is neither a comparison of quantities nor a key of the type, such as an approval. Say which rule it would have changed.
- Part of a mechanism. Answer the parts you can with a `when`, and list the mechanism under `left_out` with what is missing.

Say that a mechanism cannot arise only when what the type is rules it out. That it seldom governs is no reason.

## Before you hand in

```bash
python -m petra.rule TASK.json YOURS.json
```

This runs the parts of the check that need no second transcription. Mend what `units` refuses. If `reach`, `direction`, `alike` or `reads` finds something, read the clause again. Do not change a rule to make a part pass: write what the clause says, and put what you could not settle in your notes.
