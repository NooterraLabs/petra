# The old path

The old path was the checker Petra had before the kernel. It was written in Python: models of trusses, wire circuits, bolted joints, uncertain loads, printed parts, circuit boards and steel connections, solvers that searched for evidence, a registry of constants, and a Python program that checked the evidence. It decided verdicts on its own word.

It was deleted on 2026-11-15. The tag `old-path` holds the tree as it stood just before.

## Why it went

An audit found designs that it passed and should not have ([advisory_0.1.1.md](advisory_0.1.1.md)). Its rules were code, written once, and nothing outside the code said which checks a design owed. A deck of rules is data: it lists every mechanism a part must answer for, a small kernel works each one out, and a mechanism with no rule is an open cell.

Version 0.1.2 first took away the old path's power to pass a design. This step removed the code.

## What went

- 103 of the 131 files under `petra/`: the models, the mechanics layer, the registry, the solvers, the library of family certificates, the Python checker with its six certificate rules, and the repair search.
- The commands `explain`, `envelope`, `verify`, `certify-family` and `registry`, and the server's `registry_list` tool.
- The folder `twin/`, a second reading of the old steel models.
- The tests, scripts and public pages that described them.
- The two packages the solvers needed. Petra now installs with the standard library alone.

## What stays

- The language, the exporter, the Python reader of a deck, and the shell around the kernel.
- `petra/kernel/`, which holds the Python reader's exact arithmetic and no checker. The kernel is `petra-verify`, under `kernel/`.
- The commands `check`, `kinds`, `new`, `docs` and `mcp`.

## What it costs

A design of an old kind reads UNKNOWN, with the reason that no deck has its kind. That holds for a design the old path failed, too: with no rule to work out, the kernel has no cell to refute.

The designs that were the old path's examples are kept as cases under `corpus/cases/old/`. Where the old path decided one rightly, its line in `corpus/expected.tsv` says what the right answer is. A deck that brings a kind back has to give each of them that answer.

## Bringing a rule back

A rule returns as a row and a rule of a deck, through the acceptance check of [deck.md](deck.md). The tag holds the old code to read it from. Nothing is copied back as code that decides.
