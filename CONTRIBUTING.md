# Contributing to Petra

Petra takes issues and pull requests at [NooterraLabs/petra](https://github.com/NooterraLabs/petra). A bug report is most useful with the `.petra` file, the command you ran, and what Petra printed.

## Run the tests

You need Python 3.11 or later with `numpy` and `scipy`. From a clone, install Petra in editable mode and run the suite:

```bash
pip install -e .
python -m unittest discover -s tests -t .
```

Tests that need the full AISC Shapes Database skip unless `PETRA_SHAPES_XLSX` names your copy of the workbook. Never commit the workbook, a standard's PDF, or text copied from a standard. Petra cites clauses and encodes methods. It does not reproduce them.

Some files are generated. Edit the source, then regenerate them:

| File | Regenerate with |
|---|---|
| `docs/reference.md` and `petra/templates.py` | `python -m petra.teach --write` |
| `docs/steel_traceability.md` | `python -m petra.models.steel.trace` |
| `docs/absurd_gap.md`, `docs/canary_recall.md`, `docs/steel_gate.md` | `scripts/absurd_gap.py`, `scripts/canary_recall.py`, `scripts/steel_gate.py` |

Each report in the last row takes 40 minutes or more to regenerate on four cores. The `checks` workflow in `.github/workflows/checks.yml` runs the suite, the absurd-design gap and canary recall on GitHub's runners.

## Releases

A release is a tag `v<version>` whose version matches `pyproject.toml`. Pushing the tag runs `.github/workflows/release.yml`, which builds the wheel and sdist, runs the suite, and publishes both to PyPI through trusted publishing. Links in the README that PyPI shows point into the repository at that tag.

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
