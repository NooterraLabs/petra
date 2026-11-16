---
name: petra
description: Design and check bolted lap joints of steel plates to AISC 360-22 with Petra, a checker whose verdict comes from a small kernel that reads a deck of rules and works out every check in exact arithmetic. Use when a user asks to check or size a bolted lap splice for a load, or when a .petra or .card file is involved.
---

# Petra

Petra checks a design against a card and a deck of rules. The card, `NAME.card`, holds what is asked: the loads, the signed bounds and any waivers, each with the name of who signs it. The design, `NAME.petra`, holds the parts. Petra answers PASS, PASS_WAIVED, FAIL or UNKNOWN. The answer is the verdict of a small kernel, which reads the deck and works out every check itself in exact arithmetic.

The kernel passes a design only against a deck of rules. One deck ships today, `aisc360-22`, with two types of part: a `plate` and a `lap`, a bolted lap joint of two plates. It follows AISC 360-22 and works in kips, inches and ksi. A design whose parts are all of other kinds reads UNKNOWN, with the reason that no deck has its kind, and one that mixes the two is refused.

Install it with `pip install petra-lang`. The command is `petra` and the Python import is `petra`. If the `petra` MCP server is connected, call its tools `kinds`, `new` and `check` in place of the commands below. They take the same arguments and return the same text.

## Design a lap joint

1. Run `petra kinds lap` to see every line a lap takes, with its unit and meaning, and what the deck's grid asks of it.
2. Run `petra new lap --card > lap.card` and `petra new lap > lap.petra`. They write a card and a complete design to start from.
3. Put the user's loads and material bounds into the card, signed with the user's name and the source of the numbers. Edit the design's lines to fit.
4. Run `petra check lap.petra`. Read the first line for the verdict, and then the cells.

The card that `petra new` prints signs no waiver, so the pair reads UNKNOWN with six lines open. The example it is from passes on waivers that its own engineer signed, and nobody has signed yours.

## Read the report

The report has one line for each mechanism the grid asks of a part. A line is proved, refuted, not applicable, waived or open. The design passes only when none is refuted or open.

- A proved line names its rule and its clause. The number before it is the left side of the rule over the right, at its worst: 0.84 means 84% of the limit is used.
- A refuted line names its rule and its clause, with the two sides of the rule. Change the design until it is proved.
- An open line means the deck has no rule for that mechanism, or the card gives no load, or a value is outside a table, or a rule could not be decided. It is not yours to close. Report UNKNOWN and list the open lines.
- A waived line rests on a signature. The status is then PASS_WAIVED and not PASS: the design passes what the deck could check, and the `waived` lines name each waiver and who signed it. Report PASS_WAIVED with those lines.
- A line such as `Fy given tab.Fy` reads a value only the card states. If the card lacks it, ask the user for it.

A `lap` has rules for eight mechanisms: the least and the greatest spacing of the holes, their end and side distances, the strength of the bolts and their holes, and the yielding, rupture and block shear of each plate. Five have no rule: `lap.tightening`, `lap.hole_use`, `lap.max_edge_distance`, `lap.partial_block_shear` and `lap.ply_flexure`. Those five are open on every lap, so a lap is UNKNOWN until the card waives them, however well it is designed. A bolt of a size the tables do not list leaves more lines open.

## Rules

- The card is the user's. Write into it only the loads and bounds the user gave, signed with the user's name and the source of the numbers. Never lower a load or add a `waive` line to reach PASS. Those belong to the person who signs them.
- A design cannot state a load, a waiver or a signature, and Petra refuses one that does. A line reads a signed bound the card states with `given NAME`.
- With a PASS, give the user the `card` line. Its hash says which card the design was checked against, so the user can see it is theirs.
- Report PASS only when `petra check` prints PASS. A PASS covers the cells in its table, for the stated loads. It says nothing of what the deck does not ask about.
- Petra checks a design. It does not choose the loads, and it does not replace the engineer who signs the design.

## Use Petra from an MCP client

`petra mcp` serves the tools `check`, `kinds`, `new` and `docs` over stdio. The `check` tool takes the design as `design`, its text, or as the absolute `path` of a `.petra` file on the server's machine. It takes the card as `card` or `card_path` in the same way, and with `path` alone it reads the `.card` file beside the design. `new` returns a card and a design. `check` returns the text that `petra check` prints, and the JSON as structured content. The server stops a call that runs longer than 120 s and says so. `petra mcp --budget SECONDS` sets another limit.

In Claude Code, `/plugin marketplace add NooterraLabs/petra` and then `/plugin install petra@petra` add the server and this skill. The server runs as `uvx --from petra-lang==0.3.0 petra mcp`, so it needs [uv](https://docs.astral.sh/uv/) and no other install. Clients that read a JSON file take this entry:

```json
{"mcpServers": {"petra": {"command": "uvx", "args": ["--from", "petra-lang==0.3.0", "petra", "mcp"]}}}
```

After `pip install petra-lang`, the command `petra mcp` serves the same tools without uv.

## Use Petra from Python

`petra.check(card, design)` takes the two texts and returns the JSON that `petra check --json` prints, as a dict. `result["status"]` is the verdict, and `result["cells"]` lists every cell with its `subject`, `mechanism`, `state`, `rule` and `ratio`.

`petra docs api` prints the Python API and the JSON. `petra docs reference` prints the language.
