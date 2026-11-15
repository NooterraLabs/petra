# Removing the old path

The old path is the Python checker that stood before the kernel: the models' kinds, their solvers, the registry, and the Python code that checked their certificates. It is to be deleted whole. This page is the list for that: every file of `petra/` with its fate. Nothing is deleted yet.

Since 2026-11-14 the old path decides nothing: `petra check` prints the kernel's verdict, the kernel passes no design without a deck of rules, and a design of an old kind reads UNKNOWN with the reason that its kind has no deck (`tests/test_kernel_decides.py`, `tests/test_no_wrong_pass.py`). What is left to remove is code.

## Counts

Of the 131 files of `petra/`: 103 delete, 13 keep, 15 rewrite.

- **delete**: the file goes whole.
- **keep**: the file stays as it is.
- **rewrite**: the file stays and loses what it does for the old path. The line says what stays.

## The check

```bash
python scripts/old_path.py
```

The script copies `petra/`, removes every file marked delete from the copy, cuts each import of a removed module at module level out of the files that stay, and imports `petra.grid`, `petra.deck`, `petra.rule`, `petra.verify`, `petra.export`, `petra.cli` and `petra.mcp` from the copy. All seven import. It fails if a file of `petra/` is missing from this list or is on it twice.

Importing shows that a module loads. It does not show that its functions run: a function may still read a name that was cut, or import a removed module itself. The script prints both kinds, and they are the work of step 1.2b:

- 25 imports are cut at module level, in 7 files. The ones the seven modules meet: `ComponentError` in `grid.py` and `verify.py`, the three outcome classes of `verdict.py` in `verify.py`, and the checker's names that `petra/kernel/__init__.py` hands on.
- 48 imports inside functions of the files that stay name a removed module: 25 in `cli.py`, 7 in `__init__.py`, 6 in `export.py`, 4 each in `mcp.py` and `pipeline.py`, and one each in `teach.py` and `wellformed.py`.
- 7 of the other 17 modules that stay do not import from the copy. `petra.lang` and its four modules stop on `COVERAGE_ENTRY`, which `lang/lower.py` reads from `verdict.py` while it loads. `petra.teach` stops on the same, through `petra.lang`. `petra.pipeline` stops on `Theorem`. So the language needs more than a cut line before the delete, and until it has it no design can be parsed in the copy.

## What moves before the delete

Read off the script's output, in the order the rewrites need:

1. `ComponentError` leaves `models/base.py` for a file that stays. `grid.py`, `verify.py`, `wellformed.py`, `cli.py` and `bench/kernel_grid.py` take it from there.
2. `check_text`, `Checked` and `INPUT_ERRORS` leave `repair.py` for `pipeline.py`, which is cut down to parse, search and call the kernel. `cli.py`, `mcp.py`, `__init__.py`, `export.py` and `bench/kernel_grid.py` take them from there.
3. `lang/lower.py` loses the models' kinds and with them `models` and `COVERAGE_ENTRY`. `lang/__init__.py` loses the registry, so `parse_design` and `load_design` take no registry.
4. `petra/kernel/__init__.py` hands on only what `interval.py`, `terms.py` and `evaluate.py` define. These three are the Python reader's arithmetic, and they are not a checker.
5. `verify.py` loses `Kernel`, `verify` and `behind`, and `export.py` loses the proofs it wrote from the Python checker's statements.
6. `cli.py`, `mcp.py`, `teach.py` and `__init__.py` lose the commands, tools and names that only the old path served.

## Ways to a status besides petra check

Since step 1.1a no way in gives a pass on the Python checker's word: a design whose kind has no deck of rules reads UNKNOWN with that reason, or FAIL (`tests/test_no_wrong_pass.py`, `tests/test_kernel_decides.py`). The commands and calls below were the ways around `petra check`. Each still goes with the files above.

| Way in | Since step 1.1a | Fate |
|---|---|---|
| `petra.check_file` | Is a check of a file: it returns the kernel's verdict, with the Python checker's report as `report` | `__init__.py`, rewrite |
| `petra envelope` | Prints UNKNOWN with the reason and exits 2, or FAIL and 1. The envelope under it is the Python checker's working | `envelope.py`, delete |
| `petra registry recall` | Prints UNKNOWN for any status of a design or a claim that is not FAIL or UNKNOWN | `recall.py`, delete |
| `petra certify-family` | Unchanged. It stores the Python checker's evidence for a family and exits 0 when every claim is stored. It gives no design a verdict, and `petra check` with that library still reads UNKNOWN | `library/`, delete |
| `petra verify` on certificate files | Unchanged. It exits 0 when the Python checker accepts each file's evidence for the statement written in it, and names no design | `kernel/check.py`, `certs.py`, delete |
| By import: `petra.check_design`, `envelope.envelope`, `library.certify_family`, `recall.recall`, `loop.solve`, the steel package and the gates | Unchanged. Each returns the Python checker's own report or status, which can be a pass. 81 test modules read them, so they change with those tests in step 1.2b | delete, and `pipeline.py` rewrite |

## What the plan names, and where it is on the list

| Named in step 1.2a | Files |
|---|---|
| The models' kinds | `models/` whole: steel, electronics, boards, parts, truss, circuit, bolt, uncertainty |
| `verdict.py`, `coverage.py`, `premises.py`, `readout.py`, `certs.py`, `recall.py` | delete |
| `ir.py` | rewrite: the language, the grid and the exporter read its classes |
| `lang/lower.py` | rewrite, and `lang/` otherwise stays |
| `models/base.py`, `models/bolt.py` | delete, after `ComponentError` moves |
| `mechanics/` | delete |
| The registry's Python | `registry/` whole, with the 30 rows of the shapes table and their loader |
| The repair search | `repair.py` and `loop.py`, after `check_text` moves |
| The parts layer | `models/parts/`, `registry/parts.py` |
| `pipeline.py` | rewrite: parse, search and call the kernel |
| `_issue_theorem` and its two callers | `kernel/check.py`, delete |
| `petra/kernel/`, the Python checker and its evidence file | `check.py`, `codec.py`, `evidence.py`, `linalg.py` and `rules/` delete. `interval.py`, `terms.py` and `evaluate.py` keep |
| The truss, circuit and network solvers | `models/truss.py`, `models/circuit.py`, `models/electronics/network.py`, delete |
| `solvers/`, `library/` | delete |
| `lang/` | stays: `lexer.py`, `parser.py` and `syntax.py` keep, `__init__.py` and `lower.py` rewrite |
| `export.py` | rewrite |
| `units.py` | keep, until step 1.11 |

## Tests and scripts

The last column of the list names what imports each file by name: test modules without `tests/` and `.py`, then scripts. It reads imports from the source. A test that reaches a file only through another module, or through `petra check` run as a process, is not counted, so the column is a floor. `python scripts/old_path.py --write` writes the column and the next two paragraphs again, and `tests/test_old_path.py` fails when they are stale.

<!-- pins -->
Of the 110 test modules, 84 import a file marked delete. They are replaced by corpus and boundary tests in step 1.2b. 13 more import only files marked rewrite: `test_cosine`, `test_deck_rules`, `test_kernel_attacks`, `test_kernel_attacks2`, `test_kernel_attacks3`, `test_kernel_attacks6`, `test_kernel_attacks8`, `test_kernel_attacks9`, `test_kernel_pages`, `test_mcp`, `test_rules_accept`, `test_tape_pick`, `test_units`. 13 import neither: `test_calculix_check`, `test_deck`, `test_docs`, `test_exam`, `test_exam_sandbox`, `test_interval`, `test_kernel_budget`, `test_old_path`, `test_packaging`, `test_parts_layer`, `test_plugin`, `test_steel_part2`, `test_wheel_tags`.

The scripts outside `petra/` that import a file marked delete: `bench/kernel_grid.py`, `scripts/absurd_gap.py`, `scripts/blockshear_pilot.py`, `scripts/calculix_check.py`, `scripts/canary_recall.py`, `scripts/coped_beam_check.py`, `scripts/electronics_gate.py`, `scripts/kicad_oracle.py`, `scripts/metamorphic.py`, `scripts/parts_gate.py`, `scripts/registry_footprint.py`, `scripts/source_anchors.py`, `scripts/source_docs.py`, `scripts/source_inventory.py`, `scripts/steel_gate.py`, `scripts/steel_package.py`, `scripts/twin_check.py`.
<!-- /pins -->

`bench/kernel_grid.py` is the comparison of the two readers and stays: it takes `ComponentError`, `INPUT_ERRORS` and `build_registry` from files that go, and is rewritten with them. The others drive the old path or read its registry, and go with it. The three `source_*` scripts hold the registry's constants to their sources. A deck's rows need the same, so that work is written again for decks and not kept.

The top-level folder `twin/` is the second reading of the old steel kinds. It imports nothing of `petra/`, and `petra/models/steel/twin.py` and `scripts/twin_check.py` are its side here. It goes with the steel kinds, which ends the clash of its name with `bench/twin/`.

## The list

| File | Fate | Why | Imported by name from |
|---|---|---|---|
| `petra/__init__.py` | rewrite | `check` stays and calls the kernel only. `check_file` and the table of old names (`check_design`, `CertStore`, `Library`, `Pass` and the rest) go | nothing |
| `petra/__main__.py` | keep | starts the command line |  |
| `petra/certs.py` | delete | the store of certificates the Python checker accepted | old_kinds, test_certs, test_margin, test_pipeline, test_redteam_margins |
| `petra/cli.py` | rewrite | `check`, `docs`, `mcp` and `--version` stay. `explain`, `envelope`, `verify`, `certify-family`, `registry`, `kinds` and `new` go with what they call. `check` loses `--certs`, `--library`, `--no-solve` and `--deck` | test_cli, test_envelope, test_grid, test_kernel_attacks11, test_kernel_attacks12, test_kernel_decides, test_margin, test_no_wrong_pass, test_recall, test_redteam_margins, test_repair, test_steel_package, test_teach, corpus/run.py |
| `petra/coverage.py` | delete | which checks a model's kind owes: the grid of a deck says that now | test_bolt, test_circuit, test_coverage, test_margin, test_pipeline, test_truss, test_uncertainty, test_validity, test_verdict |
| `petra/deck.py` | keep | reads a deck of rows |  |
| `petra/decks/aisc360.json` | keep | the shipped deck |  |
| `petra/decks/core.json` | keep | the floors of core.json, which the kernel holds too |  |
| `petra/docs/api.md` | rewrite | documents the old API and its JSON. Written again for the four verdicts | nothing |
| `petra/docs/skill.md` | rewrite | teaches the models' kinds and a repair to PASS. Written again for designs of a deck | nothing |
| `petra/envelope.py` | delete | bisects the Python checker's verdicts, and exits 0 on its word alone | test_envelope, test_validity |
| `petra/export.py` | rewrite | writes card.json, design.json, deck.json and rules.json for a design of a deck, and `sha256`. `Proofs`, `cells`, `bundle` and the tapes written from the Python checker's statements go | test_deck_features, test_deck_features2, test_export_card, test_grid, test_kernel_attacks, test_kernel_attacks11, test_kernel_attacks2, test_kernel_attacks3, test_kernel_attacks5, test_kernel_decides, test_kernel_grid, test_kernel_limits |
| `petra/files.py` | keep | reads a card and a design as text, and prints nothing a terminal acts on |  |
| `petra/grid.py` | rewrite | the Python reader of a deck's grid. Stays whole, but it takes `ComponentError` from models/base.py, which goes | old_kinds, test_attack, test_cosine, test_deck_features, test_deck_features2, test_deck_rules, test_export_card, test_grid, test_kernel_attacks10, test_kernel_attacks11, test_kernel_attacks12, test_kernel_attacks3, test_kernel_attacks4, test_kernel_attacks5, test_kernel_attacks6, test_kernel_attacks7, test_kernel_attacks8, test_kernel_attacks9, test_kernel_decides, test_kernel_grid, test_kernel_limits, test_kernel_pages, test_lang, test_rules_accept, bench/kernel_grid.py, scripts/registry_footprint.py |
| `petra/ir.py` | rewrite | the parsed card and design. The classes that the language, the grid and the exporter read stay, and the ones only the models' lowering read go | test_contracts, test_coverage, test_envelope, test_lang, test_margin, test_pipeline, test_premises, test_truss, test_uncertainty |
| `petra/kernel/__init__.py` | rewrite | hands on what interval.py, terms.py and evaluate.py define, and nothing of the checker. The folder gets a name that is not the Lean kernel's | mutations, test_blockshear_pilot, test_bolt, test_certs, test_check, test_circuit, test_cli, test_codec, test_contracts, test_cosine, test_coverage, test_deck_rules, test_evaluate, test_export_card, test_kernel_attacks10, test_kernel_attacks4, test_kernel_attacks9, test_kernel_instance, test_kernel_mutations, test_kernel_redteam, test_lang, test_library, test_linalg, test_margin, test_mechanics, test_metamorphic, test_pipeline, test_premises, test_redteam_margins, test_registry, test_registry_consistency, test_rules, test_rules_accept, test_seal, test_solver_registry, test_steel_companion, test_steel_groups, test_steel_limits, test_steel_mutation, test_structure, test_truss, test_uncertainty, test_units, test_validity, test_verdict, bench/kernel_grid.py, scripts/blockshear_pilot.py, scripts/calculix_check.py, scripts/metamorphic.py, scripts/source_inventory.py |
| `petra/kernel/check.py` | delete | the Python checker, with `_issue_theorem` and its two callers, `check` of a statement and of a family instance | mutations, test_blockshear_pilot, test_bolt, test_certs, test_check, test_circuit, test_contracts, test_kernel_instance, test_kernel_mutations, test_kernel_redteam, test_library, test_margin, test_redteam_margins, test_rules, test_seal, test_solver_registry, test_structure, test_truss, test_uncertainty, test_validity, test_verdict, scripts/blockshear_pilot.py |
| `petra/kernel/codec.py` | delete | the certificate format of the Python checker | mutations, test_bolt, test_certs, test_cli, test_codec, test_kernel_instance, test_kernel_mutations, test_kernel_redteam, test_library, test_margin, test_redteam_margins, test_structure, test_truss, test_validity |
| `petra/kernel/evaluate.py` | keep | encloses an expression in exact intervals: deck.py, rule.py and grid.py search with it |  |
| `petra/kernel/evidence.py` | delete | the evidence the Python checker reads | mutations, test_blockshear_pilot, test_certs, test_check, test_circuit, test_cli, test_codec, test_kernel_instance, test_kernel_mutations, test_kernel_redteam, test_library, test_pipeline, test_redteam_margins, test_rules, test_solver_registry, test_structure, test_truss, test_uncertainty, scripts/blockshear_pilot.py |
| `petra/kernel/interval.py` | keep | exact interval arithmetic: units.py, deck.py, grid.py and export.py use it |  |
| `petra/kernel/linalg.py` | delete | exact linear algebra for the checker's rules | test_linalg |
| `petra/kernel/rules/__init__.py` | delete | the Python checker's six rules | test_kernel_instance, test_kernel_mutations, test_solver_registry, test_structure |
| `petra/kernel/rules/base.py` | delete | the Python checker's six rules | test_check, test_kernel_redteam, test_rules, test_structure, test_truss, test_uncertainty, test_verdict |
| `petra/kernel/rules/r1_linear.py` | delete | the Python checker's six rules | mutations, test_blockshear_pilot, test_check, test_codec, test_library, test_rules, test_structure, test_truss |
| `petra/kernel/rules/r2_definite.py` | delete | the Python checker's six rules | mutations, test_codec, test_kernel_redteam, test_rules, test_truss |
| `petra/kernel/rules/r3_hypercircle.py` | delete | the Python checker's six rules | mutations, test_check, test_codec, test_kernel_instance, test_kernel_redteam, test_premises, test_rules, test_solver_registry, test_truss |
| `petra/kernel/rules/r4_enclosure.py` | delete | the Python checker's six rules | mutations, test_certs, test_check, test_circuit, test_cli, test_codec, test_evaluate, test_kernel_instance, test_kernel_redteam, test_library, test_margin, test_pipeline, test_premises, test_readout, test_redteam_margins, test_rules, test_seal, test_solver_registry, test_steel_mutation, test_structure, test_truss, test_verdict, scripts/calculix_check.py |
| `petra/kernel/rules/r5_moment.py` | delete | the Python checker's six rules | mutations, test_check, test_codec, test_kernel_redteam, test_premises, test_rules, test_structure, test_uncertainty |
| `petra/kernel/rules/r6_scenario.py` | delete | the Python checker's six rules | mutations, test_codec, test_kernel_redteam, test_pipeline, test_rules, test_uncertainty |
| `petra/kernel/terms.py` | keep | the nodes of an expression: deck.py, rule.py and grid.py build tapes from them |  |
| `petra/lang/__init__.py` | rewrite | `parse_design` and `load_design` stay, without the registry they take today | old_kinds, steel_examples, test_absurd_judge, test_attack, test_bolt, test_circuit, test_contracts, test_deck_features, test_deck_features2, test_electronics, test_examples, test_export_card, test_grid, test_kernel_attacks10, test_kernel_attacks11, test_kernel_attacks12, test_kernel_attacks4, test_kernel_attacks5, test_kernel_decides, test_kernel_grid, test_kernel_limits, test_lang, test_library, test_margin, test_pipeline, test_readout, test_recall, test_redteam_margins, test_steel_companion, test_steel_connections, test_steel_coverage, test_steel_fatigue, test_steel_gate, test_steel_geometry, test_steel_groups, test_steel_limits, test_steel_mutation, test_steel_package, test_steel_principles, test_steel_properties, test_steel_twin, test_tasks, test_teach, test_truss, test_uncertainty, test_unchecked, test_validity, bench/kernel_grid.py, scripts/absurd_gap.py, scripts/calculix_check.py, scripts/metamorphic.py, scripts/registry_footprint.py, scripts/twin_check.py |
| `petra/lang/lexer.py` | keep | the tokens of a card and a design |  |
| `petra/lang/lower.py` | rewrite | lowers a card and a design of a deck's parts. Everything it does for the models' kinds goes: their grammars, claims, probability claims, tests and modes. It needs `COVERAGE_ENTRY` of verdict.py while it loads | test_deck_features, test_deck_features2, test_export_card, test_lang, test_margin, test_teach, scripts/absurd_gap.py |
| `petra/lang/parser.py` | keep | the syntax tree of a card and a design |  |
| `petra/lang/syntax.py` | keep | the nodes of the syntax tree |  |
| `petra/library/__init__.py` | delete | the library of family certificates | test_library, test_redteam_margins, test_validity |
| `petra/library/family.py` | delete | the library of family certificates | test_library, test_redteam_margins, test_validity |
| `petra/library/store.py` | delete | the library of family certificates | test_library, test_redteam_margins, test_validity |
| `petra/loop.py` | delete | the repair-and-minimise loop over the steel kinds, built on the repair search | test_loop |
| `petra/mcp.py` | rewrite | the server stays with `check` and `docs`. `kinds`, `new` and `registry_list` go with teach.py's part for the models, and the instructions are written again | test_grid, test_kernel_attacks11, test_kernel_attacks12, test_kernel_attacks5, test_kernel_decides, test_mcp, test_no_wrong_pass |
| `petra/mechanics/__init__.py` | delete | the mechanics layer the steel kinds stand on | test_mechanics, test_metamorphic, test_steel_groups, test_steel_limits, scripts/calculix_check.py |
| `petra/mechanics/algebra.py` | delete | the mechanics layer the steel kinds stand on | test_metamorphic, scripts/calculix_check.py |
| `petra/mechanics/bolt_groups.py` | delete | the mechanics layer the steel kinds stand on | nothing |
| `petra/mechanics/sections.py` | delete | the mechanics layer the steel kinds stand on | nothing |
| `petra/mechanics/stability.py` | delete | the mechanics layer the steel kinds stand on | nothing |
| `petra/mechanics/weld_groups.py` | delete | the mechanics layer the steel kinds stand on | nothing |
| `petra/models/__init__.py` | delete | the table of the models' domains and kinds | test_bolt, test_canary_recall, test_circuit, test_contracts, test_coverage, test_domain_registry, test_lang, test_margin, test_parts_table, test_pipeline, test_tasks, test_teach, test_truss, test_uncertainty, test_unchecked, test_validity |
| `petra/models/base.py` | delete | what a model's kind is. `ComponentError`, which grid.py, verify.py, wellformed.py and the command line take from it, moves to a file that stays first | test_bolt, test_circuit, test_contracts, test_coverage, test_domain_registry, test_electronics, test_envelope, test_kernel_decides, test_kernel_limits, test_margin, test_parts_review, test_pipeline, test_premises, test_redteam_margins, test_seal, test_steel_connections, test_steel_coverage, test_steel_limits, test_teach, test_truss, test_uncertainty, test_validity, test_verdict, bench/kernel_grid.py, scripts/absurd_gap.py |
| `petra/models/boards/__init__.py` | delete | the board readers of the electronics kinds | test_boards_kicad, scripts/kicad_oracle.py |
| `petra/models/boards/features.py` | delete | the board readers of the electronics kinds | test_boards_kicad |
| `petra/models/boards/kicad.py` | delete | the board readers of the electronics kinds | test_boards_kicad, scripts/kicad_oracle.py |
| `petra/models/boards/plane.py` | delete | the board readers of the electronics kinds | test_boards_kicad, scripts/kicad_oracle.py |
| `petra/models/boards/sexpr.py` | delete | the board readers of the electronics kinds | test_boards_kicad, scripts/kicad_oracle.py |
| `petra/models/boards/solid.py` | delete | the board readers of the electronics kinds | test_boards_kicad |
| `petra/models/bolt.py` | delete | the bolt kind | test_bolt, test_coverage, test_domain_registry |
| `petra/models/circuit.py` | delete | the circuit kind and its solver | test_circuit, test_contracts, test_coverage, test_teach, test_validity |
| `petra/models/contracts.py` | delete | what a domain's tools owe each other | test_circuit, test_contracts |
| `petra/models/electronics/__init__.py` | delete | the electronics kinds, with the network solver | test_electronics, scripts/electronics_gate.py, scripts/registry_footprint.py |
| `petra/models/electronics/board.py` | delete | the electronics kinds, with the network solver | test_electronics |
| `petra/models/electronics/domain.py` | delete | the electronics kinds, with the network solver | test_electronics |
| `petra/models/electronics/faults.py` | delete | the electronics kinds, with the network solver | test_electronics, scripts/electronics_gate.py |
| `petra/models/electronics/gate.py` | delete | the electronics kinds, with the network solver | test_electronics, scripts/electronics_gate.py |
| `petra/models/electronics/generate.py` | delete | the electronics kinds, with the network solver | test_electronics, scripts/registry_footprint.py |
| `petra/models/electronics/network.py` | delete | the electronics kinds, with the network solver | nothing |
| `petra/models/parts/__init__.py` | delete | the parts layer | test_parts_exact, test_parts_gate, test_parts_review, test_parts_table, scripts/parts_gate.py |
| `petra/models/parts/build.py` | delete | the parts layer | test_parts_table |
| `petra/models/parts/domain.py` | delete | the parts layer | test_parts_table |
| `petra/models/parts/engine.py` | delete | the parts layer | test_parts_gate, test_parts_review, scripts/parts_gate.py |
| `petra/models/parts/exact.py` | delete | the parts layer | test_boards_kicad, test_parts_exact, test_parts_review |
| `petra/models/parts/lower.py` | delete | the parts layer | scripts/parts_gate.py |
| `petra/models/parts/mesh.py` | delete | the parts layer | test_parts_exact, test_parts_mesh, test_parts_review, scripts/parts_gate.py |
| `petra/models/parts/rules.py` | delete | the parts layer | test_parts_table, scripts/parts_gate.py |
| `petra/models/parts/space.py` | delete | the parts layer | test_parts_exact, test_parts_mesh, test_parts_review |
| `petra/models/steel/__init__.py` | delete | the steel kinds | steel_examples, test_blockshear_pilot, test_coped_beam_check, test_mechanics, test_metamorphic, test_readout, test_steel_companion, test_steel_connections, test_steel_coverage, test_steel_fatigue, test_steel_gate, test_steel_geometry, test_steel_groups, test_steel_limits, test_steel_mutation, test_steel_package, test_steel_principles, test_steel_properties, test_steel_trace, test_steel_twin, test_teach, scripts/absurd_gap.py, scripts/blockshear_pilot.py, scripts/calculix_check.py, scripts/coped_beam_check.py, scripts/metamorphic.py, scripts/registry_footprint.py, scripts/source_docs.py, scripts/steel_gate.py, scripts/twin_check.py |
| `petra/models/steel/absent.py` | delete | the steel kinds | nothing |
| `petra/models/steel/blockshear.py` | delete | the steel kinds | test_blockshear_pilot, test_coped_beam_check, scripts/blockshear_pilot.py, scripts/coped_beam_check.py |
| `petra/models/steel/blockshear_solve.py` | delete | the steel kinds | test_blockshear_pilot, scripts/blockshear_pilot.py, scripts/coped_beam_check.py |
| `petra/models/steel/breaker.py` | delete | the steel kinds | test_steel_gate, scripts/canary_recall.py, scripts/steel_gate.py |
| `petra/models/steel/build.py` | delete | the steel kinds | nothing |
| `petra/models/steel/calc.py` | delete | the steel kinds | steel_examples, test_readout, test_steel_companion, test_steel_connections, test_steel_fatigue, test_steel_geometry, test_steel_groups, test_steel_limits, test_steel_mutation, test_steel_package, test_steel_principles, test_steel_properties, test_steel_twin, scripts/calculix_check.py, scripts/metamorphic.py, scripts/twin_check.py |
| `petra/models/steel/checks.py` | delete | the steel kinds | test_metamorphic, test_steel_groups, test_steel_limits, test_steel_mutation, test_steel_properties, scripts/calculix_check.py |
| `petra/models/steel/cyclic.py` | delete | the steel kinds | test_steel_connections, test_steel_fatigue |
| `petra/models/steel/domain.py` | delete | the steel kinds | test_steel_connections, test_steel_coverage, test_steel_fatigue, test_steel_geometry, test_steel_mutation, test_steel_package, test_steel_principles, test_steel_properties, test_steel_twin, scripts/calculix_check.py, scripts/metamorphic.py, scripts/twin_check.py |
| `petra/models/steel/fatigue.py` | delete | the steel kinds | test_metamorphic, test_steel_mutation, test_steel_principles, scripts/metamorphic.py, scripts/twin_check.py |
| `petra/models/steel/faults.py` | delete | the steel kinds | test_steel_gate, scripts/steel_gate.py |
| `petra/models/steel/gate.py` | delete | the steel kinds | test_steel_gate, test_steel_properties, scripts/metamorphic.py, scripts/steel_gate.py, scripts/twin_check.py |
| `petra/models/steel/generate.py` | delete | the steel kinds | test_metamorphic, test_steel_coverage, test_steel_gate, test_steel_geometry, test_steel_package, test_steel_principles, test_steel_properties, scripts/absurd_gap.py, scripts/metamorphic.py, scripts/registry_footprint.py, scripts/steel_gate.py, scripts/twin_check.py |
| `petra/models/steel/geometry.py` | delete | the steel kinds | nothing |
| `petra/models/steel/ic.py` | delete | the steel kinds | test_steel_groups |
| `petra/models/steel/limits.py` | delete | the steel kinds | test_metamorphic, test_steel_companion, test_steel_groups, test_steel_limits, test_steel_principles |
| `petra/models/steel/lower.py` | delete | the steel kinds | test_steel_connections, test_steel_principles, test_steel_properties, test_teach, scripts/metamorphic.py |
| `petra/models/steel/package.py` | delete | the steel kinds | test_steel_package, scripts/steel_package.py |
| `petra/models/steel/path.py` | delete | the steel kinds | test_steel_connections |
| `petra/models/steel/trace.py` | delete | the steel kinds | test_steel_principles, test_steel_trace, scripts/source_docs.py |
| `petra/models/steel/twin.py` | delete | the steel kinds | test_steel_mutation, test_steel_twin |
| `petra/models/steel/vocab.py` | delete | the steel kinds | test_mechanics, test_steel_connections, test_steel_fatigue, test_steel_principles, test_steel_properties, test_steel_trace |
| `petra/models/truss.py` | delete | the truss kind and its solver | test_coverage, test_domain_registry, test_teach, test_truss, test_validity |
| `petra/models/uncertainty.py` | delete | the uncertainty kind | test_domain_registry, test_uncertainty |
| `petra/pipeline.py` | rewrite | cut down to three things: parse the pair, search for the hints of proofs.json, and call the kernel. `check_text` moves here from repair.py. `check_design`, the premise book, the elaboration and `explain` go | old_kinds, test_bolt, test_circuit, test_contracts, test_electronics, test_examples, test_library, test_margin, test_pipeline, test_readout, test_recall, test_redteam_margins, test_steel_connections, test_steel_coverage, test_steel_fatigue, test_steel_gate, test_steel_geometry, test_steel_limits, test_steel_properties, test_teach, test_truss, test_uncertainty, test_unchecked, test_validity, scripts/absurd_gap.py, scripts/metamorphic.py, scripts/registry_footprint.py, scripts/twin_check.py |
| `petra/premises.py` | delete | the premise book of the Python checker's verdicts | test_bolt, test_circuit, test_coverage, test_domain_registry, test_envelope, test_lang, test_margin, test_pipeline, test_premises, test_registry, test_seal, test_steel_data, test_uncertainty, test_verdict |
| `petra/readout.py` | delete | the numbers of a report of the Python checker | test_readout, test_unchecked |
| `petra/recall.py` | delete | which designs rest on a registry entry. Step 1.16 writes the withdrawal list that takes its place | test_kernel_attacks12, test_recall |
| `petra/registry/__init__.py` | delete | the registry's Python | old_kinds, steel_examples, test_absurd_judge, test_attack, test_blockshear_pilot, test_bolt, test_canary_recall, test_circuit, test_contracts, test_coped_beam_check, test_deck_features, test_deck_features2, test_electronics, test_examples, test_export_card, test_grid, test_kernel_attacks10, test_kernel_attacks11, test_kernel_attacks12, test_kernel_attacks4, test_kernel_attacks5, test_kernel_attacks7, test_kernel_grid, test_kernel_limits, test_lang, test_library, test_loop, test_metamorphic, test_parts_table, test_pipeline, test_premises, test_readout, test_recall, test_redteam_margins, test_registry, test_registry_consistency, test_sources, test_steel_companion, test_steel_connections, test_steel_coverage, test_steel_data, test_steel_fatigue, test_steel_gate, test_steel_geometry, test_steel_groups, test_steel_limits, test_steel_mutation, test_steel_package, test_steel_principles, test_steel_properties, test_steel_twin, test_tasks, test_teach, test_truss, test_uncertainty, test_unchecked, test_validity, test_verify, bench/kernel_grid.py, scripts/absurd_gap.py, scripts/blockshear_pilot.py, scripts/canary_recall.py, scripts/coped_beam_check.py, scripts/electronics_gate.py, scripts/metamorphic.py, scripts/registry_footprint.py, scripts/source_anchors.py, scripts/source_inventory.py, scripts/steel_gate.py, scripts/steel_package.py, scripts/twin_check.py |
| `petra/registry/aisc_shapes.json` | delete | the 30 shipped rows of the shapes table, which only the registry reads. A deck that needs shapes takes them from the tag, with the loader | nothing |
| `petra/registry/catalog.py` | delete | the registry's Python | old_kinds, steel_examples, test_absurd_judge, test_attack, test_blockshear_pilot, test_bolt, test_canary_recall, test_circuit, test_contracts, test_coped_beam_check, test_deck_features, test_deck_features2, test_electronics, test_examples, test_export_card, test_grid, test_kernel_attacks10, test_kernel_attacks11, test_kernel_attacks12, test_kernel_attacks4, test_kernel_attacks5, test_kernel_attacks7, test_kernel_grid, test_kernel_limits, test_library, test_loop, test_metamorphic, test_premises, test_readout, test_recall, test_redteam_margins, test_registry, test_sources, test_steel_companion, test_steel_connections, test_steel_coverage, test_steel_data, test_steel_fatigue, test_steel_gate, test_steel_geometry, test_steel_groups, test_steel_limits, test_steel_mutation, test_steel_package, test_steel_principles, test_steel_properties, test_steel_twin, test_tasks, test_teach, test_truss, test_uncertainty, test_unchecked, test_validity, test_verify, bench/kernel_grid.py, scripts/absurd_gap.py, scripts/blockshear_pilot.py, scripts/canary_recall.py, scripts/coped_beam_check.py, scripts/electronics_gate.py, scripts/metamorphic.py, scripts/registry_footprint.py, scripts/source_anchors.py, scripts/source_inventory.py, scripts/steel_gate.py, scripts/steel_package.py, scripts/twin_check.py |
| `petra/registry/consistency.py` | delete | the registry's Python | test_registry_consistency, test_steel_data |
| `petra/registry/constants.py` | delete | the registry's Python | test_registry, test_steel_data, scripts/source_inventory.py |
| `petra/registry/deck.py` | delete | the registry's Python: the old deck of constants, which is not petra/deck.py | test_pipeline, test_registry, test_registry_consistency, test_steel_data |
| `petra/registry/electronics.py` | delete | the registry's Python | test_electronics, test_steel_data |
| `petra/registry/model.py` | delete | the registry's Python | test_bolt, test_lang, test_pipeline, test_premises, test_registry, test_registry_consistency, test_tasks, test_teach, scripts/metamorphic.py, scripts/registry_footprint.py, scripts/source_inventory.py |
| `petra/registry/parts.py` | delete | the registry's Python, for the parts layer | test_parts_table, test_steel_data |
| `petra/registry/steel.py` | delete | the registry's Python | test_metamorphic, test_steel_data, test_steel_mutation, test_steel_principles, test_steel_properties, scripts/calculix_check.py, scripts/metamorphic.py, scripts/source_inventory.py |
| `petra/registry/steel_fatigue.py` | delete | the registry's Python | test_steel_mutation, test_steel_principles, scripts/source_inventory.py |
| `petra/registry/steel_shapes.py` | delete | the loader of the shapes table, for the registry | test_steel_data |
| `petra/repair.py` | delete | the repair search. `check_text`, `Checked` and `INPUT_ERRORS` move to pipeline.py first | test_export_card, test_grid, test_kernel_attacks7, test_kernel_decides, test_no_wrong_pass, test_repair, test_verify, bench/kernel_grid.py |
| `petra/rule.py` | keep | reads a deck's types, grid and rules, and runs an acceptance |  |
| `petra/solvers/__init__.py` | delete | the solvers that write evidence for the Python checker | old_kinds, test_bolt, test_circuit, test_contracts, test_electronics, test_examples, test_kernel_decides, test_margin, test_recall, test_redteam_margins, test_solver_registry, test_steel_connections, test_steel_fatigue, test_steel_gate, test_steel_geometry, test_steel_limits, test_steel_properties, test_truss, test_uncertainty, test_unchecked, test_validity, test_verify, scripts/absurd_gap.py, scripts/metamorphic.py, scripts/registry_footprint.py, scripts/twin_check.py |
| `petra/solvers/exact.py` | delete | the solvers that write evidence for the Python checker | test_solver_registry |
| `petra/solvers/r1_linear.py` | delete | the solvers that write evidence for the Python checker | test_truss |
| `petra/solvers/r2_definite.py` | delete | the solvers that write evidence for the Python checker | test_truss |
| `petra/solvers/r3_hypercircle.py` | delete | the solvers that write evidence for the Python checker | test_truss |
| `petra/solvers/r4_enclosure.py` | delete | the solvers that write evidence for the Python checker | test_bolt, test_circuit, test_contracts, test_solver_registry |
| `petra/solvers/r5_moment.py` | delete | the solvers that write evidence for the Python checker | test_uncertainty |
| `petra/solvers/r6_scenario.py` | delete | the solvers that write evidence for the Python checker | test_uncertainty |
| `petra/teach.py` | rewrite | `docs_text` stays. The kinds, the lines of each, `new` and the registry's list go | test_deck_features, test_teach |
| `petra/templates.py` | delete | the examples `petra new` prints, made from the models' kinds | test_teach |
| `petra/units.py` | keep | stays until step 1.11 moves conversion into the kernel |  |
| `petra/verdict.py` | delete | the Python checker's verdicts and outcomes | old_kinds, test_bolt, test_circuit, test_contracts, test_electronics, test_envelope, test_library, test_margin, test_pipeline, test_readout, test_redteam_margins, test_seal, test_steel_coverage, test_steel_fatigue, test_steel_gate, test_steel_geometry, test_steel_properties, test_truss, test_uncertainty, test_unchecked, test_validity, test_verdict, scripts/absurd_gap.py, scripts/metamorphic.py, scripts/twin_check.py |
| `petra/verify.py` | rewrite | `need`, `run`, `taken`, `ask`, `status`, `refusal` and `differs` stay. `Kernel`, `verify` and `behind`, which hand the kernel the Python checker's proofs, go | test_attack, test_cli, test_cosine, test_deck_features, test_deck_features2, test_export_card, test_grid, test_kernel_attacks, test_kernel_attacks10, test_kernel_attacks11, test_kernel_attacks2, test_kernel_attacks3, test_kernel_attacks4, test_kernel_attacks5, test_kernel_attacks6, test_kernel_attacks7, test_kernel_attacks8, test_kernel_attacks9, test_kernel_decides, test_kernel_grid, test_kernel_limits, test_kernel_pages, test_no_wrong_pass, test_tape_pick, test_verify, bench/kernel_grid.py, bench/work_sweep.py, scripts/steel_package.py |
| `petra/wellformed.py` | rewrite | `findings`, which the grid holds a pair of a deck to, stays. `require`, for the models' kinds, goes | old_kinds |
