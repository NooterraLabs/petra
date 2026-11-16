"""The manifest of what Petra's Python counts and holds to a ceiling (docs/principles.md T2), read
by tests/test_kernel_budget.py.

The verdict of a check is the kernel's, petra-verify, written in Lean under kernel/. Nothing in
petra/ is trusted for a pass: a bug there costs an input error, an UNKNOWN or a difference from
the kernel. Two parts of it still stand between what a person wrote and what the kernel reads or
what a report says, so they are counted and each names what checks it, or a dated Debt:

- the arithmetic of the Python reader (petra/kernel), which the grid's own cells rest on;
- the front end, which turns the text of a card and a design into the files the kernel reads;
- the decks as data, the Python reader of a deck's rows and grid.

It imports nothing from petra, so the test reads it without loading the package.

Until 2026-11-15 this file also held one entry for each certificate rule of the Python checker
and the trust class of the models, the registry and the solvers. They went with the old path
(plan step 1.2c), and the tag `old-path` holds them.
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


CORE_CAP = Limit(331, "Set on 2026-11-15 at the deletion of the old path (plan step 1.2c), where the arithmetic of the "
                       "Python reader measured 331 code lines: interval.py, terms.py and evaluate.py, and the "
                       "package's own file. Before that day the cap was 1,023 and covered the Python checker's "
                       "core too: its check, its codec, its evidence and its linear algebra, which are gone.")

TRUSTED_CEILING = Limit(4076, "Set on 2026-11-15 at the deletion of the old path (plan step 1.2c), where what is counted "
                                "measured 3,871 code lines: the arithmetic 331, and outside it the front end and the decks "
                                "as data, 3,540. Before that day the ceiling was 20,119, of which the models, the "
                                "registry, the premises and the Python checker's rules were the most: all are gone. "
                                "Raised the same day for what the thirteenth review found in the exporter: a usage error "
                                "exits 3 and not 2, which is kept for a design no deck has, and a run that cannot write "
                                "one of its files takes back the ones it wrote. 11 lines in petra/export.py: 3,882. "
                                "Raised on 2026-11-15 for plan step 1.6: the Python reader refuses a deck whose rule's "
                                "`when`, or whose line's `unless`, reads a key the card does not sign, as the kernel "
                                "does. 16 lines in petra/grid.py and 2 in the deck, where the holes and the surface of a "
                                "lap are signed: 3,900. "
                                "Raised the same day for what the fourteenth review found: a field left unstated that a "
                                "need names has an open cell, so that no part passes by leaving out what its type needs, "
                                "and a deck nested deeper than the kernel reads is refused before it is read, where it "
                                "ended in a RecursionError. 33 lines in petra/grid.py: 3,933. "
                                "And for its second round: the reader has room for a chain of names as long as the "
                                "kernel reads, which ended it at 246, and a file of the decks' folder is held to the "
                                "depth before it is read. 18 lines in petra/grid.py: 3,951. "
                                "Raised on 2026-11-16 for the rest of plan step 1.6: a line of the grid is excused only "
                                "with a reason that is not empty, and the cell of a rule with `requires`, which works "
                                "nothing out, is marked and is not the proved cell a PASS needs. And the mean of a "
                                "given or of a load on a deck's card is refused, where it was dropped with nothing "
                                "said. 8 lines in petra/grid.py: 3,959. "
                                "Raised the same day for the last part of step 1.6, the owner's rulings 1 and 2, and for "
                                "what the fifteenth review found. A key is the card's unless the deck says `chosen` and "
                                "why. An `unless` has one ground that the reader checks: a `when`, a `least` or the "
                                "`loads` the type declares, or `with` other lines, whose cell is settled after every "
                                "other. The cell of a rule that reads no quantity is marked as one of stated keys. A "
                                "deck's reason is cut once, as the kernel cuts it, and prints on one line. The guard on "
                                "the kernel's answer knows a stated cell, and the exporter refuses a mean on every way "
                                "in. 93 lines, most of them in petra/grid.py: 4,052. "
                                "And for what the sixteenth review found: the least of a load or of a quantity excuses a "
                                "line for a part that has a value for it and leaves it open for any other, a tape none "
                                "of whose roots reads an input is one that reads nothing, and a name and an anchor of a "
                                "deck print on the line of their own cell. 24 lines in petra/grid.py: 4,076. "
                                "Raise it in the commit that needs more and say why here.")

T2_ADOPTED = date(2026, 11, 8)
"""The day T2 took this form. Every debt found that day carries it."""


TRUSTED: tuple[Group, ...] = (
    Group("front end",
          ("petra/lang/__init__.py", "petra/lang/lexer.py", "petra/lang/parser.py", "petra/lang/syntax.py",
           "petra/lang/lower.py", "petra/ir.py", "petra/units.py", "petra/export.py"),
          Debt(date(2026, 11, 15), "No second reading of the language. The kernel and the clean-room reading under "
                                   "bench/twin both start from the JSON files this group writes, so a card or a design "
                                   "that it turns into the wrong files is checked as those files. The report names the "
                                   "card and the design by the hash of their text, and the kernel prints the hash of "
                                   "each file it read, which ties a verdict to the files and not to this group's reading "
                                   "of the text. The second parser there was, twin/card.py, read the steel kinds' cards "
                                   "and went with them on this date.")),
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
    "petra/__init__.py", "petra/__main__.py", "petra/cli.py", "petra/files.py", "petra/mcp.py", "petra/pipeline.py", "petra/rule.py",
    "petra/teach.py", "petra/templates.py", "petra/verify.py", "petra/wellformed.py",
)
"""Each of these calls the front end, the reader or the kernel, or words what they gave. A bug in one costs a refusal, a reply or a
line of a report, and none of them writes a file the kernel reads."""
