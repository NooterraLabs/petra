# Task 202-029

A user asks you to design a steel connection with Petra, a design checker. Petra is
installed. Run it as:

    C:/Users/aiden/AppData/Local/Temp/claude/b8a6192efa7a5d70/0f9aa34e-5303-40d9-bb2b-9b8f8156fb71/scratchpad/venv/Scripts/petra.exe

Design a steel `hanger` connection, LRFD (`basis lrfd`).

These lines are fixed by the job:

- `support W18x35 flange grade steel.A992`

Loads (factored), on the connection:

- tension: from 0 to 42.043 kip

Sign the loads as "task.owner@example.org" with source "task 202-029".

## How to work

- Work in this folder: `C:/Users/aiden/AppData/Local/Temp/claude/b8a6192efa7a5d70/0f9aa34e-5303-40d9-bb2b-9b8f8156fb71/scratchpad/agents/task-202-029`. Change to it before you run anything, and write
  files only there. Use only what the `petra` command prints, its `--help` and its
  documents. Do not read Petra's source files or anything outside this folder.
- Save each design you want checked as `try1.petra`, `try2.petra`, and so on, in this
  folder, and check it with `petra check tryN.petra` (with or without `--json`). Each
  such run is one check, and you have at most 10.
- Other `petra` commands, such as `--help`, `docs`, `kinds`, `new` and `registry list`,
  are not checks. Use them as often as you like.
- Do not call Petra from a script or from Python, and do not check any other file.
- Stop at the first PASS, or after 10 checks.

When you stop, report the number of checks you ran, the status of each, and the file
that passed, if one did.
