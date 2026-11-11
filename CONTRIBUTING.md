# Contributing to Petra

Petra takes issues and pull requests at [NooterraLabs/petra](https://github.com/NooterraLabs/petra). A bug report is most useful with the card and the design, the command you ran, and what Petra printed.

## Run the tests

You need Python 3.11 or later with `numpy` and `scipy`. From a clone, install Petra in editable mode and run the suite:

```bash
pip install -e .
python tests/parallel.py
```

`tests/parallel.py` runs one process for each test module, several at a time. On a 4-core desktop the suite took 12 minutes this way and 32 one after another. `python -m unittest discover -s tests -t .` still runs it the plain way.

| Command | Runs |
|---|---|
| `python tests/parallel.py --fast` | Every module that took a minute or less when last recorded: nine tests in ten, in under 5 minutes on that desktop |
| `python tests/parallel.py tests.test_grid tests.test_deck` | The modules you name |
| `python tests/parallel.py --record` | The suite, and rewrites `tests/durations.tsv`, which orders the modules longest first |

To spread a run over more machines, list them in `~/.petra/test-hosts`, one a line: `USER@HOST slots=4 python=PATH lake=PATH`. Each gets the working tree over ssh before the run, and every free slot takes the longest module left. With a second 4-core machine the suite took 8 minutes, and `--fast` under 2. The head of `tests/parallel.py` describes the file.

Run the whole suite before you open a pull request. The `checks` workflow runs it on every push, as six jobs side by side, with the corpus beside them.

Tests that need the full AISC Shapes Database skip unless `PETRA_SHAPES_XLSX` names your copy of the workbook. Never commit the workbook, a standard's PDF, or text copied from a standard. Petra cites clauses and encodes methods. It does not reproduce them.

Some files are generated. Edit the source, then regenerate them:

| File | Regenerate with |
|---|---|
| `docs/reference.md` and `petra/templates.py` | `python -m petra.teach --write` |
| `docs/steel_traceability.md` and the provision table in `docs/steel_connections.md` | `scripts/source_docs.py` |
| `docs/absurd_gap.md`, `docs/canary_recall.md`, `docs/metamorphic.md`, `docs/steel_gate.md` | `scripts/absurd_gap.py`, `scripts/canary_recall.py`, `scripts/metamorphic.py`, `scripts/steel_gate.py` |
| `docs/electronics_gate.md` | `scripts/electronics_gate.py`, about 7 minutes on six workers |

Each report in the third row takes 40 minutes or more to regenerate on four cores. The `checks` workflow in `.github/workflows/checks.yml` runs the suite, the absurd-design gap, canary recall and the metamorphic relations on GitHub's runners.

## Releases

A release is a tag `v<version>` whose version matches `pyproject.toml`. Pushing the tag runs `.github/workflows/release.yml`, which builds the sdist and one wheel for each of five platforms, runs the suite, and publishes the six files to PyPI through trusted publishing. Links in the README that PyPI shows point into the repository at that tag.

Each wheel carries the Lean kernel for its platform, so Petra installed from PyPI has the kernel check its verdicts. `.github/workflows/wheels.yml` builds each wheel on a runner of its platform, installs it in a fresh environment and has it check two designs. The `checks` workflow runs the same jobs on every push and keeps the wheels as artifacts. [kernel/README.md](kernel/README.md#in-a-wheel) lists the platforms, what each wheel asks of a machine, and how to build one yourself. The sdist carries no kernel.

## Changes to the kernel

Every verdict trusts `petra/kernel/`, so a change there needs the maintainer's approval before it merges. The kernel imports only the Python standard library, and a test enforces this.

## Sign off every commit

Petra takes contributions under the [Developer Certificate of Origin 1.1](https://developercertificate.org/) (DCO), not a contributor licence agreement. Your sign-off certifies that you wrote the change, or have the right to submit it under the project's licence. `git commit -s` adds the line:

```text
Signed-off-by: Your Name <you@example.com>
```

Use your real name. A pull request with an unsigned commit does not merge.

## Your contribution's licence

Code is Apache-2.0 ([LICENSE](LICENSE)). Documentation in `docs/` is CC BY 4.0 ([docs/LICENSE.md](docs/LICENSE.md)). You keep the copyright in your work. Petra asks for no rights beyond those licences, so the project holds no more rights to your contribution than anyone else.

## The licence pledge

Nooterra will not move Petra to a source-available licence, or to any licence the Open Source Initiative has not approved. Terraform, Redis and Elasticsearch each changed licence after people came to rely on them, and each was forked. Even if the pledge were broken, every version released under Apache-2.0 would stay available under Apache-2.0. [docs/open_source.md](docs/open_source.md) gives the sources.

## The name

[TRADEMARK.md](TRADEMARK.md) says how anyone may use the Petra name, and what "Petra-checked" means.
