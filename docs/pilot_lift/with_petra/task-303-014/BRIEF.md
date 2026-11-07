# Task 303-014

A user asks you to design a steel connection with Petra, a design checker. Petra is
installed. Run it as:

    C:/Users/aiden/AppData/Local/Temp/claude/b8a6192efa7a5d70/0f9aa34e-5303-40d9-bb2b-9b8f8156fb71/scratchpad/p3/venv/Scripts/petra.exe

Read `petra docs skill` before you start.

Design a steel `double_angle` connection, LRFD (`basis lrfd`).

These lines are fixed by the job:

- `beam W24x55 grade steel.A992`
- `support W14x61 web grade steel.A992`

Loads (factored), on the connection:

- shear: from 0 to 142.863 kip

Sign the loads as "task.owner@example.org" with source "task 303-014".

The user wants a connection that is safe under AISC 360-22 for these loads and that
can be built as drawn. Among safe designs, a lighter one is better, but safety comes first.

## How to work

- Work in this folder: `C:/Users/aiden/AppData/Local/Temp/claude/b8a6192efa7a5d70/0f9aa34e-5303-40d9-bb2b-9b8f8156fb71/scratchpad/p3/jobs/a/task-303-014`. Change to it before you run anything, and write
  files only there. Use only what the `petra` command prints, its `--help` and its
  documents. Do not read Petra's source files or anything outside this folder.
- Save each design you want checked as `try1.petra`, `try2.petra`, and so on, in this
  folder, and check it with `petra check tryN.petra` (with or without `--json`). Each
  such run is one check, and you have at most 10.
- Other `petra` commands, such as `--help`, `docs`, `kinds`, `new` and `registry list`,
  are not checks. Use them as often as you like.
- Do not call Petra from a script or from Python, and do not check any other file.

## When you finish

Save the design you hand to the user as `final.petra` in this folder, and write
`claim.json` beside it, in this form:

    {"safe": true, "governing": "<the limit state closest to failing>", "utilisation": 0.87, "notes": "<anything the user should know>"}

Set `safe` to true only if you believe the design is safe under AISC 360-22 for the loads
above and can be built as drawn. Set it to false otherwise, and say why in `notes`.

Then report the file, your claim, and the number of checks you ran with the status of each.
