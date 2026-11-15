# Petra

Petra checks a physical design against what was asked of it. A card is a short file that states the loads and the claims, each with who signs it. A design is a short `.petra` file that describes the parts, and it cannot change the card. Petra answers pass, fail or unknown. The answer is the verdict of a small kernel, which reads a deck of rules and works out every check itself in exact arithmetic.

The kernel passes a design only against a deck of rules. One kind of part has a deck today, a bolted lap splice. A design of the older kinds, which are the other steel connections, trusses, wire circuits and bolted joints, reads unknown until its kind has one.

Petra checks the loads a card states. It does not choose them, and it does not replace the engineer who signs the design.

## Install

```bash
pip install petra-lang
```

In Claude Code with [uv](https://docs.astral.sh/uv/) installed, `/plugin marketplace add NooterraLabs/petra` and then `/plugin install petra@petra` give your agent Petra's tools and its skill.

## Use

```bash
petra new lap --card > lap.card
petra new lap > lap.petra
petra check lap.petra
```

`petra new` prints an example design to edit, and with `--card` a card for it. `petra check` prints the verdict and every check behind it. The deck proves eight of the lap's checks and has no rule yet for five more, and the card signs no waiver, so the verdict is unknown, with those five lines open, and the exit code is 2. A waiver is for the person who answers for a line to sign: with all five signed the verdict is a waived pass, and the exit code is 6. `petra kinds` lists what Petra can check, and `petra docs` lists the documents that ship with it.

## Learn more

- [Language reference](docs/reference.md)
- [Using Petra from Python](petra/docs/api.md)
- [Petra in a coding agent's loop](docs/in_the_loop.md)
- [How the checker works](docs/design.md)
- [Steel connections](docs/steel_connections.md)
- [Electronics worst case](docs/electronics_dc.md)
- [Roadmap and test results](docs/plan.md)

## License

Code is under Apache-2.0 and docs are under Creative Commons Attribution 4.0. To send a change, read [contributing](CONTRIBUTING.md).

<!-- mcp-name: io.github.NooterraLabs/petra -->
