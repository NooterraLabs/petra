# Petra

Petra checks a physical design against the claims written in it. A design is a short `.petra` file that describes a steel connection, a truss, a wire circuit or a bolted joint. Petra answers pass, fail, marginal or unknown, and backs every pass and fail with a certificate that a small kernel re-checks in exact arithmetic.

Petra checks the loads a design states. It does not choose them, and it does not replace the engineer who signs the design.

## Install

```bash
pip install petra-lang
```

In Claude Code, `/plugin marketplace add NooterraLabs/petra` and then `/plugin install petra@petra` give your agent Petra's tools and its skill.

## Use

```bash
petra new shear_tab > tab.petra
petra check tab.petra
```

`petra new` prints an example design to edit. `petra check` prints the verdict, the check that governs it, and every check behind it. `petra kinds` lists what Petra can check, and `petra docs` lists the documents that ship with it.

## Learn more

- [Language reference](docs/reference.md)
- [Using Petra from Python](petra/docs/api.md)
- [Petra in a coding agent's loop](docs/in_the_loop.md)
- [How the checker works](docs/design.md)
- [Steel connections](docs/steel_connections.md)
- [Roadmap and test results](docs/plan.md)

## License

Code is under Apache-2.0 and docs are under Creative Commons Attribution 4.0. To send a change, read [contributing](CONTRIBUTING.md).

<!-- mcp-name: io.github.NooterraLabs/petra -->
