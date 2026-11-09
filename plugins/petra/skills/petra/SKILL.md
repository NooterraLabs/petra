---
name: petra
description: Design, check and repair steel connections to AISC 360-22 (shear tabs, double and single angles, shear tees, end plates, seats, brackets, hangers) and other physical designs with Petra, a checker that backs every verdict with an exact-arithmetic certificate. Use when a user asks to check, size or fix a connection for a load, or when a .petra file is involved.
---

# Petra

Petra checks a design written in a `.petra` file against the loads and claims written in it. It answers PASS, FAIL, UNKNOWN or MARGINAL. A small kernel re-checks every PASS and FAIL in exact arithmetic. The steel deck follows AISC 360-22 and works in kips, inches and ksi.

Install it with `pip install petra-lang`. The command is `petra` and the Python import is `petra`. If the `petra` MCP server is connected, call its tools `kinds`, `new` and `check` in place of the commands below. They take the same arguments and return the same text.

## Design a connection

1. Run `petra kinds steel` to see the connection kinds. Run `petra kinds shear_tab` to see every line a kind takes, with its unit and meaning.
2. Run `petra new shear_tab > tab.petra`. It writes a complete design that passes.
3. Edit the design to the user's job. Set the `beam` and `support` lines, the support's face (`flange` or `web`), the `basis` (`lrfd` or `asd`) and the load range in the `load` block.
4. Run `petra check tab.petra`. The first line is the status. The exit code is 0 for PASS, 1 for FAIL, 2 for UNKNOWN, 5 for MARGINAL and 3 for an input error.
5. On a FAIL, apply a move from the `repair` lines, as the next section describes, and check again.
6. Stop at PASS. Tell the user the governing strength check and its utilisation from the `governing` line.

A shape, grade or bolt must be a registry id or a common name for one. `petra registry list W18` lists the W18 shapes. `A325` stands for `bolt_group.120` and `A992` for `steel.A992`. A plate thickness must be a stocked one, and a bolt diameter must be an RCSC size.

## Repair a FAIL

The `repair` lines come right after the `governing` lines:

```
repair     tab/steel.bolts at utilisation 2.02; each move lowers it, the first the most:
  increase  tab.rows (line 19) from 3 to 4: utilisation 1.31; it holds at 5, where the design is FAIL on tab/steel.beam_fit
  increase  tab.bolts diameter (line 18) from 0.75 to 0.875 inch: utilisation 1.79
```

The first line names the governing failed check and its utilisation. Each move changes one number on one line of the design, one step up or down, and gives the check's utilisation after that step. The first move lowers the check the most. "It holds at 5" means the check passes with that value, and the rest of the sentence gives the whole design's status there.

- If a move holds and the design passes there, make that edit.
- If the design would then fail another check, make the edit anyway when no move does better, and check again. The repair then targets the named check. In the example, five rows clear the bolts but no longer fit the W16x31's web, so the next repair works on the fit.
- When no number lowers the check, the moves are `swap` moves, which put another angle or tee on the line. The ones that leave the fewest failed checks come first.
- If no move holds, combine moves, or change a part that is not a number: a stronger grade, or `threads excluded`.
- UNKNOWN is not a FAIL. Its `needs` lines say what is missing, such as a load or a line.

## Rules

- Write the loads the user gave, signed with the user's name and the source of the numbers. Never lower a load, edit a claim, or add a `waive` line to reach PASS. Those belong to the person who signs them.
- Report PASS only when `petra check` prints PASS. A PASS covers the checks in its table, for the stated loads. The `not checked` lines say what it does not cover.
- Petra checks a design. It does not choose the loads, and it does not replace the engineer who signs the design.

## Use Petra from an MCP client

`petra mcp` serves the tools `check`, `kinds`, `new`, `registry_list` and `docs` over stdio. The `check` tool takes the design as `text` or as the absolute `path` of a file. It returns the text that `petra check` prints, and the JSON as structured content.

In Claude Code, `/plugin marketplace add NooterraLabs/petra` and then `/plugin install petra@petra` add the server and this skill. The server runs as `uvx --from petra-lang==0.1.2 petra mcp`, so it needs [uv](https://docs.astral.sh/uv/) and no other install. Clients that read a JSON file take this entry:

```json
{"mcpServers": {"petra": {"command": "uvx", "args": ["--from", "petra-lang==0.1.2", "petra", "mcp"]}}}
```

After `pip install petra-lang`, the command `petra mcp` serves the same tools without uv.

## Use Petra from Python

`petra.check(text)` returns the JSON that `petra check --json` prints, as a dict. On a FAIL, `result["repair"]["moves"]` lists the moves, best first. Each move has `input`, `line`, `from`, `to`, `direction`, `utilisation`, `status` and `clears`.

`petra docs api` prints the Python API and the JSON. `petra docs reference` prints the language.
