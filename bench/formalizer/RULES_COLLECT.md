# Collecting worked examples for a task's mechanisms

You are given a task and a published source of worked examples, such as a standard's own design examples. You find the worked examples of each mechanism the task asks about and write each as data. The acceptance check then asks the rules that two transcribers wrote to reproduce your numbers.

## What you are given

- The task, a JSON file. It holds the types, with the fields and loads of each kind of part, and the mechanisms, each with the clause that raises it.
- The manual: `docs/deck.md`, "A type" and "A worked example of a mechanism".
- The source, and where in it to look. Read it in place. `python bench/formalizer/pages.py FILE.pdf FIRST-LAST` renders pages as images under the system's temporary folder.

## What you must not see

- A rule written for this task, by a transcriber or in a deck of `petra/decks`. An example that was fitted to a rule checks nothing.
- The output of the acceptance check. Do not run it.

## The source is licensed

Take numbers and where they are printed. Do not copy its prose, keep its pages, commit them or send them anywhere.

## What an example is

A part of one of the task's types, as the source has it, and one number that the source prints for one mechanism of that part.

```json
{"anchor": "the source, its example and its page, as printed",
 "given": {"a.thickness": "3/8 inch", "a.Fy": "36 ksi"},
 "loads": {"pull": "45 kip"},
 "side": "right",
 "gives": "72.9 kip"}
```

| Key | Holds |
|---|---|
| `anchor` | The source, the number of the example and the page, as printed |
| `given` | Each field of the part that the source states, by the task's name for it: a field of the type by its name, a field of a joined part as `a.thickness` |
| `loads` | Each load on the part that the source states, by the task's name for it |
| `side` | Which number this is: `left` for what the part must carry or must have, `right` for what it can carry or may have, `ratio` for the first over the second |
| `gives` | The number as printed, with its unit and every digit printed. The check takes how near a rule must come from the digits. |
| `within` | Another bound, such as `"1 %"`, only where the print warrants it. Say why in your notes. |

## Which examples to take

1. The part is one the type can be. Read the type's `what`. If the type is one line of bolts in single shear, a joint with two lines or in double shear is no example of it, however near. Leave it out.
2. The number is for the mechanism as a whole, for this part. A mechanism may take in several limit states. If the task asks about the strength of the bolts with bearing and tearout at their holes, the source's shear strength of one bolt is no example of it. The strength of the joint that the source ends with is.
3. Where the source prints the number for each of two parts, as for each plate, take the one that governs: the least of what the parts can carry, or the greatest of what they must have. Say in the anchor which part it was.
4. The method is the task's. A load that the task calls a required strength by one method has no examples by another.
5. The edition of the source goes with the edition of the standard. Say both.

## What to write, and what not

- Write a value as the source prints it, with its unit: `3/8 inch`, `36 ksi`. A key is one of the names the type lists for it.
- Give every field of the part that the source states, also those you think the mechanism does not need. A rule that wrongly reads a field is caught by an example that gives it.
- Do not give a field the source does not state. Do not take it from the task's ranges, from a table the example does not cite, or from your own judgement. A rule that reads a field you left out will not reproduce the example, and that is a finding about the rule or about the example, for a person to settle.
- Leave a load out if the source prints none. A side that reads no load is still checked.
- Do not work the number out again, and do not correct the source. If you think the source is wrong, write what it prints and say so in your notes.
- One printed number is one example. Two numbers for one part, such as its left side and its ratio, are two examples.

Examples that differ are worth more than examples that repeat. Look for the other names of each key, for a part where another term governs, and for a part on each side of a limit the clause sets.

## What you hand in

One JSON file.

```json
{"source": "the source and its edition, and the edition of the standard it goes with",
 "examples": {"MECHANISM": []},
 "left_out": [{"anchor": "...", "why": "two lines of bolts"}],
 "notes": "anything a reader of the examples should know"}
```

List under `left_out` each worked example you looked at and did not take, and why. A mechanism with no example has an empty list, and your notes say that the source has none.
