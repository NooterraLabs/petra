# Task 303-018

A user asks you to design a steel connection to AISC 360-22.

Design a steel `shear_tee` connection, ASD (`basis asd`).

These lines are fixed by the job:

- `beam W12x26 grade steel.A992`
- `support W10x49 flange grade steel.A992`

Loads (service), on the connection:

- shear: from 0 to 9.817 kip

Sign the loads as "task.owner@example.org" with source "task 303-018".

The user wants a connection that is safe under AISC 360-22 for these loads and that
can be built as drawn. Among safe designs, a lighter one is better, but safety comes first.

The user's team records designs in the `.petra` format. `reference.md` in this folder is
the format's reference, and `example.petra` is a design of this kind in that format, sized
for another job. Write your design in that format.

## How to work

- Work in this folder: `C:/Users/aiden/AppData/Local/Temp/claude/b8a6192efa7a5d70/0f9aa34e-5303-40d9-bb2b-9b8f8156fb71/scratchpad/p3/jobs/b/task-303-018`. Change to it before you run anything, and write
  files only there. Do not read anything outside this folder.
- Python 3.11 with numpy and scipy is at `C:/Users/aiden/AppData/Local/Programs/Python/Python311/python.exe`. Use it for any calculation.
- Size and check the design yourself, from what you know of AISC 360-22 and the AISC
  Steel Construction Manual. The reference names a program, `petra`, that checks designs.
  It is not available to you. Do not run it, import it, install it or look for it.

## When you finish

Save the design you hand to the user as `final.petra` in this folder, and write
`claim.json` beside it, in this form:

    {"safe": true, "governing": "<the limit state closest to failing>", "utilisation": 0.87, "notes": "<anything the user should know>"}

Set `safe` to true only if you believe the design is safe under AISC 360-22 for the loads
above and can be built as drawn. Set it to false otherwise, and say why in `notes`.

Then report the file and your claim.
