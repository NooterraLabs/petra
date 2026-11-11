"""The manifest of Petra's trusted base (docs/principles.md T2), read by tests/test_kernel_budget.py.

It holds the kernel core's cap and the trusted total's ceiling, each with its reason, one entry
per certificate rule, and every module under petra/ outside the kernel, trusted or not. It
imports nothing from petra, so the test reads it without loading the kernel.

A rule's entry records its code lines and three items: where the docs state its soundness, the
mutation corpus it must reject, and its check against an outside checker. An item a rule lacks is
a Debt, dated, saying what exists instead.

Each trusted group names the judge or twin that checks it, or a Debt. A judge counts when it
re-derives most of what its modules compute and a test or script compares it with Petra. A judge
of a single condition is named in its group's debt instead.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Limit:
    lines: int
    reason: str


@dataclass(frozen=True)
class Ref:
    """A file or directory in the repository. A non-empty anchor names a markdown heading in a
    .md file, or a top-level class or function in a .py file."""

    path: str
    anchor: str = ""


@dataclass(frozen=True)
class Debt:
    since: date
    what: str


@dataclass(frozen=True)
class Rule:
    id: str
    module: str
    lines: int
    soundness: Ref | Debt
    mutations: tuple[Ref, ...] | Debt
    outside: Ref | Debt


@dataclass(frozen=True)
class Judge:
    code: Ref
    compared_by: tuple[Ref, ...]
    shares: str
    """What the judge shares with Petra (docs/frontier.md §3 rule 2)."""


@dataclass(frozen=True)
class Group:
    name: str
    modules: tuple[str, ...]
    checked_by: Judge | Debt


CORE_CAP = Limit(1000, "Set on 2026-11-08 at 140f742, where the core measured 957 code lines. "
                       "A new rule adds 3 to 5 lines to rules/__init__.py (inferred from its tables), so "
                       "the headroom covers the registry entries of several rules.")

TRUSTED_CEILING = Limit(19196, "Set on 2026-11-08 at 140f742, where the trusted base measured 13,530 "
                               "code lines: core 957, rules 457, outside the kernel 12,116. Raised on "
                               "2026-11-08 on branch parts-core as the parts layer replaces its scaffold: "
                               "classifying the scaffold measured 14,269, and the mesh reader with its "
                               "solid-boundary rules measured 14,461, and the exact evaluator 14,823. "
                               "Registering the parts layer, which deletes the grid, reach, deck and "
                               "KiCad scaffold and adds the fit, fastener, insert, press, temperature, "
                               "extent, flat-sheet and bridge builders with their registry rows, "
                               "measured 15,696. Mass and centre-of-mass claims "
                               "measured 15,796. Raised on branch parts-fix to close the parts-core "
                               "review's false PASSes: holes, threads, presses and seats read from the "
                               "mesh, every screw pair and the last body before its mouth, mass and "
                               "centre-of-mass bounds over the tolerance, and per-piece containment "
                               "measured 16,366. Stops read by flat face rather than by triangle, so "
                               "splitting a face changes no verdict, and a press read with its pairs "
                               "pruned by box, both found by scripts/parts_gate.py, measured 16,404. "
                               "On branch kicad-reader, from parts-core's 15,796, the KiCad board reader "
                               "(its s-expression parser, exact plane geometry with bounding polygons for "
                               "arcs, feature table and reader) measured 16,795, and its exact solids of the "
                               "board and of each part's keep-out, with the checked triangulation, 17,013. "
                               "The fixes after its review on branch kicad-fix, marks from the words of a "
                               "library id and a keep-out room over the courtyard and the Fab layer's "
                               "shapes, measured 17,051, and a name for each solid's mesh that holds what "
                               "defines it 17,058. Both branches merged on branch integration-merge, with "
                               "release 0.1.1's anodic indices and tightening note, hanger-slot's worse-way "
                               "reads and an anodic index for the inserts' brass, measured 17,727. "
                               "On branch rework a design's card became a file of its own: the grammar of "
                               "each file, the `given` declaration and lowering the two trees measured 17,766. "
                               "Refusing a mesh number that is missing, not finite or longer than a coordinate, "
                               "and a design number of more than 100 characters, measured 17,780. "
                               "The micrometre, the unit ISO 286 prints its tolerances in, measured 17,781. "
                               "A given named for the field of the part that reads it, and a refusal in place "
                               "of a crash when a command of the models meets a part of a deck, measured 17,793. "
                               "The grid (petra/grid.py) decides the cells of a design checked against a deck and "
                               "writes each tape from rows that petra/deck.py reads, so both are trusted until the "
                               "kernel reads decks: with them the base measured 19,115. The count takes all of "
                               "deck.py, though the acceptance check in it writes no tape. "
                               "The kernel reads decks since 2026-11-10 (kernel/Petra/Deck.lean): the grid then sends "
                               "it hints and no tapes, and holds a deck's names to letters, digits and _, a grid line "
                               "to a type of the deck and a whole power to 64, as the kernel does. With that the base "
                               "measured 19,115 again. "
                               "Lowering a card with no design, so that an asker can write card.json from their own "
                               "card and compare its hash with the one the kernel prints, and keeping the card's "
                               "givens in the design for the exporter to read, measured 19,122: seven lines in "
                               "petra/lang and petra/ir.py. "
                               "The kernel holds a name that a cell prints whole to 64 bytes, so that its verdict "
                               "stays small. The grid holds the same names to the same 64, counted the same way, so "
                               "that the two refuse the same decks and designs: six lines in petra/grid.py, 19,128. "
                               "A report of a deck's design says which path made it, two lines in grid.py: 19,130. "
                               "A deck is refused for a key it does not know wherever the key stands, and not only at "
                               "the top of a row, a type, a grid line or a rule, and the refusal names the key: 26 lines "
                               "in petra/deck.py and petra/grid.py, 19,156. "
                               "The third hostile review of the kernel found names that two texts could share and "
                               "cells that two rules could share. The kernel now refuses them, and the grid refuses "
                               "the same decks and designs: a text with U+FFFD or half a surrogate pair, a mechanism "
                               "named `unread`, a `where` with no item, two rules of one line whose ids end alike, a "
                               "load case with a / in its name, and an anchor that names something that is no text. "
                               "It also reads a value's digits and blanks as the kernel does, 0 to 9 and space, tab "
                               "and line end, where it took any digit and any blank of Unicode: 13 lines in "
                               "petra/deck.py and petra/grid.py, 19,169. "
                               "The same review found decks under 1 MB that took the kernel a minute or a gigabyte "
                               "to read. The kernel now counts the steps to read a deck from its file, a million at "
                               "most, and holds the name of a card to 200 bytes for a design with parts. The grid "
                               "makes the same count and holds the same name, so that the two refuse the same decks "
                               "and designs: 20 lines in petra/grid.py, 19,189. "
                               "The fourth hostile review of the kernel found two wrong verdicts. A load case that "
                               "put some of the loads a rule reads on a part, and not all, gave the rule no cell under "
                               "it, and a load that no rule reads gave no cell at all. A rule that reads loads now has "
                               "a cell for each load case of the card, open where the case leaves one of its loads "
                               "out, and a load that nothing reads is an open cell, in the kernel and in the grid "
                               "alike: 7 lines in petra/grid.py, 19,196. "
                               "Raise it in the commit that needs more and say why here.")

T2_ADOPTED = date(2026, 11, 8)
"""The day T2 took this form. Every debt found that day carries it."""


def _argued_in_docstring(argument: str) -> Debt:
    return Debt(T2_ADOPTED, f"The module docstring gives the argument ({argument}), and docs/frame.md "
                            "'Certificate rules' gives one line. No doc states the rule's soundness conditions.")


NO_OUTSIDE_CHECKER = Debt(T2_ADOPTED, "No outside checker reads this rule's certificates. T5 names the "
                                      "planned Lean kernel as the second implementation, and this machine "
                                      "has no Lean toolchain (docs/frame.md, Constraints).")

MUTANTS = Ref("tests/test_kernel_mutations.py", "Mutants")

RULES: tuple[Rule, ...] = (
    Rule("R1", "petra/kernel/rules/r1_linear.py", 71,
         _argued_in_docstring("convexity over the vertices of the load box, and Farkas's lemma for the refutation"),
         (MUTANTS, Ref("tests/fixtures/r1_feasible.cert.json"), Ref("tests/fixtures/r1_farkas.cert.json")),
         NO_OUTSIDE_CHECKER),
    Rule("R2", "petra/kernel/rules/r2_definite.py", 68,
         _argued_in_docstring("the Loewner order below the box, and Sylvester's law of inertia for the LDL^T factor"),
         (MUTANTS, Ref("tests/fixtures/r2_ldl.cert.json"), Ref("tests/fixtures/r2_negative_direction.cert.json")),
         NO_OUTSIDE_CHECKER),
    Rule("R3", "petra/kernel/rules/r3_hypercircle.py", 150,
         _argued_in_docstring("the Prager-Synge hypercircle identity, which also proves the MinimizerComponent lemma"),
         (MUTANTS, Ref("tests/fixtures/r3_hypercircle.cert.json"), Ref("tests/fixtures/r3_violation.cert.json"),
          Ref("tests/fixtures/r3_lemma.cert.json"), Ref("tests/fixtures/r3_lemma_witness.cert.json")),
         NO_OUTSIDE_CHECKER),
    Rule("R4", "petra/kernel/rules/r4_enclosure.py", 64,
         _argued_in_docstring("the leaves of a split tree cover the box, and the natural interval extension encloses each leaf"),
         (MUTANTS, Ref("tests/fixtures/r4_enclosure.cert.json"), Ref("tests/fixtures/r4_point_witness.cert.json")),
         NO_OUTSIDE_CHECKER),
    Rule("R5", "petra/kernel/rules/r5_moment.py", 60,
         _argued_in_docstring("moment-problem duality, with domination checked cell by cell"),
         (MUTANTS, Ref("tests/fixtures/r5_moment_dual.cert.json")),
         NO_OUTSIDE_CHECKER),
    Rule("R6", "petra/kernel/rules/r6_scenario.py", 44,
         _argued_in_docstring("the binomial tail summed in exact rationals"),
         Debt(T2_ADOPTED, "tests/fixtures/r6_binomial.cert.json is in the corpus of "
                          "tests/test_kernel_mutations.py, but every operator that applies to it is stopped "
                          "by the codec, the statement hash or dispatch, so no mutant reaches the tail check. "
                          "BinomialTails in tests/test_rules.py and R6Degenerate in "
                          "tests/test_kernel_redteam.py give it false statements by hand."),
         NO_OUTSIDE_CHECKER),
)

TWIN = Ref("twin")
IN_REPO_TWIN = Ref("petra/models/steel/twin.py")

TRUSTED: tuple[Group, ...] = (
    Group("front end",
          ("petra/lang/__init__.py", "petra/lang/lexer.py", "petra/lang/parser.py", "petra/lang/syntax.py",
           "petra/lang/lower.py", "petra/ir.py", "petra/units.py"),
          Debt(T2_ADOPTED, "twin/card.py parses steel cards from the language reference with its own unit "
                           "table, and scripts/twin_check.py compares the results on the steel gate stream. "
                           "No judge parses the other decks' cards.")),
    Group("registry",
          ("petra/registry/__init__.py", "petra/registry/model.py", "petra/registry/constants.py",
           "petra/registry/catalog.py"),
          Debt(T2_ADOPTED, "petra/registry/consistency.py re-derives derivable records from physics "
                           "relations (tests/test_registry_consistency.py), but it is Petra's own code and "
                           "shares registry/model.py. No judge reads the constants from their sources.")),
    Group("domain registry and shared types",
          ("petra/models/__init__.py", "petra/models/base.py"),
          Debt(T2_ADOPTED, "No judge or twin.")),
    Group("truss",
          ("petra/models/truss.py",),
          Debt(T2_ADOPTED, "judges/truss.py re-solves the plastic collapse factor, with and without the "
                           "members' weight, as its own linear program. Elastic forces, stability and member "
                           "buckling have no judge.")),
    Group("circuit",
          ("petra/models/circuit.py",),
          Debt(T2_ADOPTED, "judges/circuit.py checks only that each conductor fits its terminal. Ampacity, "
                           "adiabatic heating, voltage drop and breaker coordination have no judge.")),
    Group("bolt",
          ("petra/models/bolt.py",),
          Debt(T2_ADOPTED, "judges/bolt.py checks only whether a tension claim survives the joint opening.")),
    Group("uncertainty",
          ("petra/models/uncertainty.py",),
          Debt(T2_ADOPTED, "judges/uncertainty.py recomputes the range-and-mean bound only to flag a claim "
                           "that a tested failure below the stated capacity breaks. The scenario bound has no "
                           "judge.")),
    Group("port contracts",
          ("petra/models/contracts.py",),
          Debt(T2_ADOPTED, "No judge or twin.")),
    Group("electronics",
          ("petra/models/electronics/__init__.py", "petra/models/electronics/board.py",
           "petra/models/electronics/network.py", "petra/models/electronics/domain.py",
           "petra/registry/electronics.py"),
          Debt(T2_ADOPTED, "No judge or twin. The deck's gate wants each of its planted faults caught "
                           "(petra/models/electronics/gate.py, docs/electronics_gate.md), which tests the "
                           "deck against known defects, not against a second implementation.")),
    Group("steel strength",
          ("petra/models/steel/__init__.py", "petra/models/steel/lower.py", "petra/models/steel/limits.py",
           "petra/models/steel/checks.py", "petra/models/steel/build.py", "petra/models/steel/path.py",
           "petra/models/steel/domain.py", "petra/mechanics/__init__.py", "petra/mechanics/algebra.py",
           "petra/mechanics/bolt_groups.py", "petra/mechanics/sections.py", "petra/mechanics/stability.py",
           "petra/mechanics/weld_groups.py", "petra/registry/steel.py", "petra/registry/steel_shapes.py"),
          Judge(TWIN, (Ref("scripts/twin_check.py"), Ref("docs/twin_check.md", "The clean-room twin against Petra on the gate stream")),
                "the .petra card format and the model family that wrote both, and no code, registry or "
                "representation (twin/README.md). It does not model stiffened_seat, flange_force, fatigue "
                "or fit beyond J3.5 edge distance.")),
    Group("steel fatigue",
          ("petra/models/steel/fatigue.py",),
          Judge(IN_REPO_TWIN, (Ref("tests/test_steel_twin.py", "TwinAgreesWithTheDeck"),),
                "the deck's lowering (lower.py), its load paths (path.py, cyclic.py), the registry and the "
                "model family")),
    Group("steel fatigue duty and data",
          ("petra/models/steel/cyclic.py", "petra/registry/steel_fatigue.py"),
          Debt(T2_ADOPTED, "The in-repo twin imports cyclic.py and reads these rows from the registry, so "
                           "it shares them. twin/ does not model fatigue.")),
    Group("steel geometry",
          ("petra/models/steel/geometry.py",),
          Judge(Ref("judges/steel.py"), (Ref("tests/test_steel_geometry.py", "JudgeReadings"), Ref("scripts/absurd_gap.py")),
                "petra.ir, the shapes table through petra.registry.steel_shapes, and the model family")),
    Group("steel vocabulary",
          ("petra/models/steel/vocab.py",),
          Debt(T2_ADOPTED, "No judge restates the validity rows or the model premises. The in-repo twin "
                           "reads its method statements from this module.")),
    Group("block shear pilot",
          ("petra/models/steel/blockshear.py",),
          Debt(T2_ADOPTED, "No judge or twin. docs/coped_beam_check.md sets the pilot's bound beside 25 "
                           "published tests, which checks the method, not this builder.")),
    Group("parts",
          ("petra/models/parts/__init__.py", "petra/models/parts/mesh.py", "petra/models/parts/space.py",
           "petra/models/parts/exact.py", "petra/models/parts/rules.py", "petra/models/parts/lower.py",
           "petra/models/parts/engine.py", "petra/models/parts/build.py", "petra/models/parts/domain.py",
           "petra/registry/parts.py"),
          Debt(T2_ADOPTED, "No judge or twin. The engine states its geometric measures as design values, "
                           "so the kernel re-checks the arithmetic over them and not the measures; "
                           "tests/test_parts_exact.py checks the integer primitives against dense sampling, "
                           "which is not a second implementation. scripts/parts_gate.py holds generated "
                           "designs to ten metamorphic relations and checks that planted faults never "
                           "pass, which tests the layer against itself. docs/parts.md 'Testing' plans a "
                           "clean-room twin of analytic assemblies, and it is not written yet.")),
    Group("boards",
          ("petra/models/boards/__init__.py", "petra/models/boards/sexpr.py", "petra/models/boards/plane.py",
           "petra/models/boards/features.py", "petra/models/boards/kicad.py", "petra/models/boards/solid.py"),
          Debt(T2_ADOPTED, "No judge or twin. tests/board_second_reading.py, written by an agent that never saw "
                           "the reader, places every pad of every test board from first principles, and "
                           "SecondReading in tests/test_boards_kicad.py compares the two. It judges pad places "
                           "only, so it is named here and not as the group's judge. The outline, its bounds, "
                           "courtyards, rooms, holes and solids have no second reading.")),
    Group("premises, coverage, verdict and pipeline",
          ("petra/premises.py", "petra/coverage.py", "petra/verdict.py", "petra/pipeline.py"),
          Debt(T2_ADOPTED, "No judge or twin. The absurd-design gap and canary recall score whole verdicts "
                           "against the judges (docs/absurd_gap.md, docs/canary_recall.md), which is not a "
                           "second implementation of these modules.")),
    Group("decks as data",
          ("petra/deck.py", "petra/grid.py"),
          Debt(date(2026, 11, 10), "petra-verify reads the deck's own file and works out every cell and every tape "
                                   "itself (kernel/Petra/Deck.lean, Grid.lean), and `petra check` compares its cells with "
                                   "the grid's one by one: tests/test_grid.py (Kernel), tests/test_kernel_grid.py, and "
                                   "bench/kernel_grid.py on generated designs and damaged decks. So the kernel's verdict "
                                   "no longer rests on these two modules for the cells or the tapes. What is left to "
                                   "them alone is the search for a partition or a point, which can only leave a cell "
                                   "open, and what a report says of a cell beyond its state. The kernel's reader is a "
                                   "port of these modules by one hand, not a reading made without sight of them, so it "
                                   "is named here and not as the group's judge. A row passes the acceptance check of "
                                   "docs/deck.md, which a second transcription backs. A rule has an acceptance check "
                                   "there too (petra/rule.py). The first deck's 15 rules are one of two transcriptions "
                                   "from the pages of the standard: the second gives every sampled part the same "
                                   "answer, and eight worked examples are reproduced (tests/test_deck_rules.py). "
                                   "Nothing second-transcribes a type or a grid line.")),
)

UNTRUSTED: tuple[str, ...] = (
    "petra/__init__.py", "petra/__main__.py", "petra/cli.py", "petra/certs.py", "petra/envelope.py", "petra/export.py", "petra/files.py",
    "petra/loop.py", "petra/mcp.py", "petra/readout.py", "petra/recall.py", "petra/repair.py", "petra/rule.py",
    "petra/teach.py", "petra/templates.py", "petra/verify.py", "petra/wellformed.py",
    "petra/library/__init__.py", "petra/library/family.py", "petra/library/store.py",
    "petra/registry/consistency.py", "petra/registry/deck.py",
    "petra/solvers/__init__.py", "petra/solvers/exact.py", "petra/solvers/r1_linear.py",
    "petra/solvers/r2_definite.py", "petra/solvers/r3_hypercircle.py", "petra/solvers/r4_enclosure.py",
    "petra/solvers/r5_moment.py", "petra/solvers/r6_scenario.py",
    "petra/models/electronics/faults.py", "petra/models/electronics/gate.py",
    "petra/models/electronics/generate.py",
    "petra/models/steel/absent.py", "petra/models/steel/blockshear_solve.py", "petra/models/steel/breaker.py",
    "petra/models/steel/calc.py", "petra/models/steel/faults.py", "petra/models/steel/gate.py",
    "petra/models/steel/generate.py", "petra/models/steel/ic.py", "petra/models/steel/package.py",
    "petra/models/steel/trace.py", "petra/models/steel/twin.py",
)
