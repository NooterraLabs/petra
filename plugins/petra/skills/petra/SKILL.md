---
name: petra
description: Design, check and repair steel connections to AISC 360-22 (shear tabs, double and single angles, shear tees, end plates, seats, brackets, hangers) and other physical designs with Petra, a checker that backs every verdict with an exact-arithmetic certificate. Use when a user asks to check, size or fix a connection for a load, or when a .petra or .card file is involved.
---

# Petra

Petra checks a design against a card. The card, `NAME.card`, holds what is asked: the loads, the claims and any waivers, each with the name of who signs it. The design, `NAME.petra`, holds the components. Petra answers PASS, FAIL, UNKNOWN or MARGINAL. A small kernel re-checks every PASS and FAIL in exact arithmetic. The steel deck follows AISC 360-22 and works in kips, inches and ksi.

Install it with `pip install petra-lang`. The command is `petra` and the Python import is `petra`. If the `petra` MCP server is connected, call its tools `kinds`, `new` and `check` in place of the commands below. They take the same arguments and return the same text.

## Design a connection

1. Run `petra kinds steel` to see the connection kinds. Run `petra kinds shear_tab` to see every line a kind takes, with its unit and meaning.
2. Run `petra new shear_tab --card > tab.card` and `petra new shear_tab > tab.petra`. They write a card and a complete design that passes it.
3. Edit the card to what the user asked: the load range in the `load` block, signed with the user's name and the source of the numbers. If the user gave a card, use it as it is.
4. Edit the design to the user's job. Set the `beam` and `support` lines, the support's face (`flange` or `web`) and the `basis` (`lrfd` or `asd`).
5. Run `petra check tab.petra`. It reads `tab.card` beside the design, and `--card FILE` names another card. The first line is the status. The `kernel` line says how many of the proofs a second, smaller checker confirmed. The exit code is 0 for PASS, 1 for FAIL, 2 for UNKNOWN, 5 for MARGINAL and 3 for an input error.
6. On a FAIL, apply a move from the `repair` lines, as the next section describes, and check again.
7. Stop at PASS. Tell the user the governing strength check and its utilisation from the `governing` line.

A shape, grade or bolt must be a registry id or a common name for one. `petra registry list W18` lists the W18 shapes. `A325` stands for `bolt_group.120` and `A992` for `steel.A992`. A plate thickness must be a stocked one, and a bolt diameter must be an RCSC size.

## Repair a FAIL

The `repair` lines come right after the `governing` lines:

```
repair     tab/steel.bolts at utilisation 2.02; each move lowers it, the first the most:
  increase  tab.rows (line 15) from 3 to 4: utilisation 1.31; it holds at 5, where the design is FAIL on tab/steel.beam_fit
  increase  tab.bolts diameter (line 14) from 0.75 to 0.875 inch: utilisation 1.79
```

The first line names the governing failed check and its utilisation. Each move changes one number on one line of the design, one step up or down, and never the card, and gives the check's utilisation after that step. The first move lowers the check the most. "It holds at 5" means the check passes with that value, and the rest of the sentence gives the whole design's status there.

- If a move holds and the design passes there, make that edit.
- If the design would then fail another check, make the edit anyway when no move does better, and check again. The repair then targets the named check. In the example, five rows clear the bolts but no longer fit the W16x31's web, so the next repair works on the fit.
- When no number lowers the check, the moves are `swap` moves, which put another angle or tee on the line. The ones that leave the fewest failed checks come first.
- If no move holds, combine moves, or change a part that is not a number: a stronger grade, or `threads excluded`.
- UNKNOWN is not a FAIL. Its `needs` lines say what is missing, such as a load or a line.

## Design a part of a deck's type

`petra kinds` lists each deck after the domains, and `petra kinds lap` prints a type's lines and what the deck's grid asks of it. `petra new lap` prints a design to start from, and `petra new lap --card` its card.

The report has one line for each mechanism the grid asks of a part. A line is proved, refuted, not applicable, waived or open, and the design passes only when none is refuted or open.

- A refuted line names its rule and its clause. Change the design until it is proved.
- An open line means the deck has no rule for that mechanism, or the card gives no load, or a value is outside a table. It is not yours to close. Report UNKNOWN and list the open lines: a waiver belongs to the person who signs the card.
- A line such as `Fy given tab.Fy` reads a value only the card states. If the card lacks it, ask the user for it.

A `lap` of the deck `aisc360-22` has rules for eight mechanisms: the least and the greatest spacing of the holes, their end and side distances, the strength of the bolts and their holes, and the yielding, rupture and block shear of each plate. Four have no rule: `lap.tightening`, `lap.hole_use`, `lap.max_edge_distance` and `lap.ply_flexure`. Those four are open on every lap, so a lap is UNKNOWN until the card waives them, however well it is designed. A bolt of 1 1/8 inch or more, or of a size the tables do not list, leaves more lines open.

## Rules

- The card is the user's. Write into it only the loads and claims the user gave, signed with the user's name and the source of the numbers. Never lower a load, edit a claim, or add a `waive` line to reach PASS. Those belong to the person who signs them.
- A design cannot state a load, a claim, a waiver or a signature, and Petra refuses one that does. A line reads a signed bound the card states with `given NAME`.
- With a PASS, give the user the `card` line. Its hash says which card the design was checked against, so the user can see it is theirs.
- Report PASS only when `petra check` prints PASS. A PASS covers the checks in its table, for the stated loads. The `not checked` lines say what it does not cover.
- Petra checks a design. It does not choose the loads, and it does not replace the engineer who signs the design.

## Use Petra from an MCP client

`petra mcp` serves the tools `check`, `kinds`, `new`, `registry_list` and `docs` over stdio. The `check` tool takes the design as `design`, its text, or as the absolute `path` of a `.petra` file on the server's machine. It takes the card as `card` or `card_path` in the same way, and with `path` alone it reads the `.card` file beside the design. `new` returns a card and a design. `check` returns the text that `petra check` prints, and the JSON as structured content. The server stops a call that runs longer than 120 s and says so. `petra mcp --budget SECONDS` sets another limit.

In Claude Code, `/plugin marketplace add NooterraLabs/petra` and then `/plugin install petra@petra` add the server and this skill. The server runs as `uvx --from petra-lang==0.1.2 petra mcp`, so it needs [uv](https://docs.astral.sh/uv/) and no other install. Clients that read a JSON file take this entry:

```json
{"mcpServers": {"petra": {"command": "uvx", "args": ["--from", "petra-lang==0.1.2", "petra", "mcp"]}}}
```

After `pip install petra-lang`, the command `petra mcp` serves the same tools without uv.

## Use Petra from Python

`petra.check(card, design)` takes the two texts and returns the JSON that `petra check --json` prints, as a dict. On a FAIL, `result["repair"]["moves"]` lists the moves, best first. Each move has `input`, `line`, `from`, `to`, `direction`, `utilisation`, `status` and `clears`.

`petra docs api` prints the Python API and the JSON. `petra docs reference` prints the language.
