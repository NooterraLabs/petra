"""What `petra kinds`, `petra new` and `petra docs` print, and docs/reference.md. Untrusted
tooling: it prints the types of the shipped decks as the grid reads them, the canonical
examples and the documents, and decides no verdict.

    python -m petra.teach            exit 1 when docs/reference.md or petra/templates.py
                                     differs from what this module renders
    python -m petra.teach --write    rewrite both

petra/templates.py copies the canonical example of each type that has one (CANONICAL), so
`petra new` works from an installed package, which carries no examples/ directory. For the
same reason `petra docs` renders the reference here, reads the hand-written documents from
petra/docs/, and reads the README from the installed distribution's metadata.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.metadata
import re
import sys
from pathlib import Path
from typing import Callable, Mapping

from . import deck as deck_rows
from . import grid, verify
from .files import MAX_FILE, MAX_LISTED, MAX_MESSAGE, MAX_PROBLEMS, card_of
from .lang import parse_design, syntax
from .lang.lexer import Kind, tokenize
from .units import CHARGE, CUSTOMARY, DENSITY, FREQUENCY, SPEED, STIFFNESS, UNITS, dimension_name

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "reference.md"
TEMPLATE_MODULE = Path(__file__).with_name("templates.py")

CANONICAL: Mapping[str, str] = {
    "lap": "examples/deck/lap_pass.petra",
}
"""A type of a deck -> its canonical example, for each type that has one. `petra new` prints it."""

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class TeachError(ValueError):
    """An unknown deck, type or document, or a --name a design cannot take. The CLI reports
    it as an input error."""


def _unknown(name: str, what: str, known: list[str]) -> TeachError:
    close = difflib.get_close_matches(name, known)
    tail = f"did you mean {' or '.join(close)}?" if close else f"one of {', '.join(known)}"
    return TeachError(f"{name!r} is not {what}; {tail}")


# --- petra kinds ------------------------------------------------------------------------


def _decks(name: str | None) -> list[tuple[grid.Deck, tuple[str, ...]]]:
    """(deck, the types to print) for every deck, one deck, or one type of a deck."""
    return [(d, tuple(d.types) if name in (None, d.name) else (name,)) for d in grid.decks() if name in (None, d.name) or name in d.types]


def _deck_text(deck: grid.Deck, types: tuple[str, ...]) -> str:
    """What a design writes for a part of each type, what a card may put on it, and what
    the grid asks of it, as `petra kinds` prints a kind."""
    lines = [f"deck {deck.name}: {', '.join(deck.types)}", ""]
    for kind in (deck.types[name] for name in types):
        lines.append(f"{kind.name} <name> {{ one line each }}    {kind.what}")
        if kind.name in CANONICAL:
            lines.append(f"  `petra new {kind.name}` prints {CANONICAL[kind.name]}")
        lines += [f"  load entry: on <{kind.name}> {f.name} in [<lo>, <hi>]    {f.what}" for f in kind.loads.values()]
        asks = [a for a in deck.asks if a.type == kind.name]
        if asks:
            lines.append(f"  waive <mechanism> on <{kind.name}> by \"<owner>\" reason \"<reason>\"")
        lines.append("  lines, each once:")
        for f in kind.fields.values():
            if f.type is not None:
                form = " ".join(f"<{f.type}>" for _ in f.names)
            elif f.keys:
                names = "<" + " | ".join(f'"{k}"' if " " in k else k for k in f.keys) + ">"
                form = f"given <name>.{f.name}" if f.signed else names
            else:
                form = f"given <name>.{f.name}" if f.signed else "<whole number>" if f.whole else f"<{deck_rows.show(f.dim)}>"
            states = f"is {names}" if f.keys else "is <whole number>" if f.whole else "in [<lo>, <hi>]"
            note = f"; the card states it: given <name>.{f.name} {states} signed ..." if f.signed else ""
            if f.optional:
                form, note = f"{form} | unstated", note + "; `unstated` where the part's record states none"
            if f.may_be:
                note += f"; may be {f.may_be}" if f.may_be == "zero" else "; may be zero or negative"
            lines += [f"    {f.name} {form}", f"        {f.what}{note}"]
        if kind.needs:
            lines += ["  a part that breaks one of these is no design:", *(f"    {need.why}" for need in kind.needs)]
        if asks:
            lines.append("  the grid asks:")
            for a in asks:
                rules = [r.id for r in deck.rules if (r.type, r.mechanism) == (a.type, a.mechanism)]
                answer = (f"cannot arise{' for some parts' if a.unless else ''}: {a.excused}" if a.excused and not rules
                          else f"rule {', '.join(rules)}" if rules else "no rule yet, so its cell is open until the card waives it")
                lines += [f"    {a.mechanism}    {a.what} ({grid._anchor(a.anchor)})", f"        {answer}"]
        lines.append("")
    return "\n".join(lines)


def kinds_summary() -> str:
    """Each deck with its types, then how to print a type's lines."""
    return "\n".join([*(f"deck {d.name}: {', '.join(d.types)}" for d in grid.decks()), "",
                      "`petra kinds TYPE` prints the lines a part of a type takes, each with its meaning, and what the",
                      "grid asks of it; `petra kinds DECK` prints them for every type of a deck, and `petra kinds --all`",
                      "for every type. `petra new TYPE` prints a complete design to start from, and `--card` its card.", ""])


def _found(name: str | None) -> list[tuple[grid.Deck, tuple[str, ...]]]:
    found = _decks(name)
    if not found:
        raise _unknown(name, "a deck or a type of one", [*(d.name for d in grid.decks()), *grid.kinds()])
    return found


def kinds_text(name: str | None) -> str:
    """Every type of every deck, of one deck, or one type: what a design writes for a part
    of it, what a card may put on it, and what the grid asks of it."""
    return "\n".join(_deck_text(deck, types) for deck, types in _found(name))


def kinds_json(name: str | None) -> dict:
    """What `kinds_text` prints, as data: each deck with its hash, and each type with its
    fields, its loads, what it needs of a part and what the grid asks of one."""
    def field(f: grid.Field) -> dict:
        return {"name": f.name, "what": f.what, "dimension": None if f.dim is None else deck_rows.show(f.dim), "keys": list(f.keys),
                "type": f.type, "names": list(f.names), "signed": f.signed, "whole": f.whole, "optional": f.optional, "may_be": f.may_be}

    return {"decks": [{
        "deck": deck.name,
        "hash": deck.hash,
        "types": [{
            "type": kind.name,
            "what": kind.what,
            "example": CANONICAL.get(kind.name),
            "fields": [field(f) for f in kind.fields.values()],
            "loads": [field(f) for f in kind.loads.values()],
            "needs": [need.why for need in kind.needs],
            "asks": [{"mechanism": a.mechanism, "what": a.what, "anchor": grid._anchor(a.anchor), "excused": a.excused,
                      "rules": [r.id for r in deck.rules if (r.type, r.mechanism) == (a.type, a.mechanism)]}
                     for a in deck.asks if a.type == kind.name],
        } for kind in (deck.types[t] for t in types)],
    } for deck, types in _found(name)]}


# --- petra new --------------------------------------------------------------------------


def new_text(kind: str, name: str | None) -> tuple[str, str]:
    """The canonical example of `kind` as (its card, its design), the component renamed to
    `name` in both when given. The pair is lowered before it is returned, so a name the
    design cannot take is an error (LolaSyntaxError or LoweringError), never a broken file."""
    from .templates import TEMPLATES

    if kind not in TEMPLATES:
        if kind in grid.kinds():
            raise TeachError(f"a {kind} is written with the part that joins it; `petra kinds {kind}` lists its lines")
        raise _unknown(kind, "a type of a deck that has an example", list(TEMPLATES))
    source, component, card, text = TEMPLATES[kind]
    if name is not None:
        if not _NAME.fullmatch(name):
            raise TeachError(f"--name {name!r} is not a name: letters, digits and _, starting with a letter or _")
        card, text = rename(card, component, name), rename(text, component, name)
    first, _, rest = text.partition("\n")
    out = f"{first}\n# From {source}. `petra kinds {kind}` lists every line a {kind} takes.\n{rest}"
    card = unsigned(card)
    parse_design(card, out, f"<petra new {kind}>")
    return card, out


UNSIGNED = ("# The example this card is from waives each line that its deck has no rule for, signed by its\n"
            "# engineer. This card signs none: those lines are open, and the check reads UNKNOWN until the\n"
            "# person who answers for a line writes its `waive` and signs it. That is never the one who\n"
            "# draws the design.\n")
"""What a template's card says where the example's waivers stood."""


def unsigned(card: str) -> str:
    """The card of a template with no waiver. An example signs the waivers of its own engineer,
    and a card to start from must sign nothing in anyone's name: with the example's waivers
    in it, a design drawn against it passed on signatures nobody gave
    (tests/test_kernel_attacks12.py)."""
    lines = card.splitlines(keepends=True)
    at = [n for n, line in enumerate(lines) if line.lstrip().startswith("waive ")]
    if not at:
        return card
    kept = [line for n, line in enumerate(lines) if n not in at]
    return "".join(kept[:at[0]]) + UNSIGNED + "".join(kept[at[0]:])


def rename(text: str, old: str, new: str) -> str:
    """Every name token `old` that is not the part after a dot becomes `new`; strings and
    comments are untouched."""
    starts = [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]
    at = []
    tokens = tokenize(text, "<template>")
    for before, tok in zip((None, *tokens), tokens):
        if tok.kind is Kind.IDENT and tok.text == old and not (before is not None and before.text == "."):
            at.append(starts[tok.line - 1] + tok.col - 1)
    for i in reversed(at):
        text = text[:i] + new + text[i + len(old):]
    return text


def render_templates() -> str:
    """petra/templates.py: the canonical example of each type that has one, the name of its
    component of that type, its card's text and its design's."""
    lines = ['"""Generated by `python -m petra.teach --write` from the examples it names; do not edit.',
             "`petra new KIND` prints from TEMPLATES[KIND]: (the example, the name of its KIND component,",
             'the text of its card, the text of its design). tests/test_teach.py fails when this file is stale."""',
             "",
             "TEMPLATES: dict[str, tuple[str, str, str, str]] = {"]
    for kind in (k for k in grid.kinds() if k in CANONICAL):
        source = CANONICAL[kind]
        card, text = (ROOT / card_of(source)).read_text(encoding="utf-8"), (ROOT / source).read_text(encoding="utf-8")
        design = parse_design(card, text, source)
        named = [c.name for c in design.components.values() if c.kind == kind]
        if len(named) != 1:
            raise ValueError(f"{source} has {len(named)} {kind} components; a canonical example has one")
        lines += [f"    {kind!r}: (", f"        {source!r},", f"        {named[0]!r},"]
        for body in (card, text):
            lines += ["        (", *(f"            {line!r}" for line in body.splitlines(keepends=True)), "        ),"]
        lines.append("    ),")
    lines.append("}")
    return "\n".join(lines) + "\n"


# --- docs/reference.md --------------------------------------------------------------------

SNIPPETS: tuple[tuple[str, str, str], ...] = (
    ("card", "A card has one `card` block, which names what is asked. `owner` is required. `environment` is "
     "optional and names where the design stands. No deck of rules reads an environment yet, so `petra check` "
     "refuses a card that states one for a design of a deck's types.",
     'card "lap-splice" {\n  owner "s.engineer@example.org"\n}'),
    ("param", "`param` declares a range that a line reads by writing `param NAME` in place of a value. A param is "
     "declared in the card or in the design, and a load and the ambient read only the card's params. No deck of "
     "rules reads a param yet, and `petra check` refuses a pair that declares one.",
     "param run in [0 m, 20 m]"),
    ("ambient", "`ambient` declares the ambient temperature range, with a signature. No deck of rules reads one yet.",
     'ambient in [10 degC, 40 degC] signed "site.manager@example.org" source "site survey 2026-09"'),
    ("given", "`given` states a signed bound under a name. A part's line in the design reads it by writing "
     "`given NAME` where the value goes. The design reads every given the card states. A name may be `PART.FIELD`. "
     "A part of a deck's type reads only the given named for it: `Fy given tab.Fy` on the part `tab`. "
     "A card may also state a thing exactly, with `is` in place of the range: the name of a key, as a bare word "
     "or in quotes, or a number whose value is whole with no unit, `4`, `4.0` or `8/2` alike, as a count the design "
     "writes, as in `given beam.category is B signed \"...\" source \"...\"` "
     "and `given quad.rotors is 4 signed \"...\" source \"...\"`. It has no range and no `mean`, and it carries a "
     "signature. The type of a part says which fields the card states: a design that writes one of them itself "
     "is refused.",
     'given tab.Fy in [36 ksi, 36 ksi] signed "s.engineer@example.org" source "ASTM A36, specified minimum"'),
    ("component", "A component is a part, written `TYPE NAME { ... }` in the design, with one line per field. The "
     "Types section lists every type of the shipped decks and its lines. A design with a part of a kind no deck "
     "has is read too, and `petra check` gives it UNKNOWN with that reason: there is no rule to check it by.",
     "plate tab {\n  thickness 0.375 inch\n  width 6 inch\n  Fy given tab.Fy\n  Fu given tab.Fu\n}"),
    ("load", "A `load` block is one load case. Each entry is `on <part> <load> <bound>`, where the load is one "
     "that the part's type takes. An entry is signed by its own signature or by the signature on the block's "
     "last line.",
     'load gravity {\n  on splice pull in [0 kip, 45 kip]\n'
     '  signed "s.engineer@example.org" source "calculation C-12, LRFD combination 1.2D + 1.6L"\n}'),
    ("tests", "A `tests` block records proof tests. No deck of rules reads one yet.",
     'tests proof {\n  on hook trials 300 failures 0 at 36 kN\n'
     '  signed "qa.lab@example.org" source "batch 2026-09 proof tests, independent lots"\n}'),
    ("claim", "A claim takes one of three forms: a bound on a quantity, with an optional margin and the load "
     "cases it holds under, a range-and-mean probability bound, or a tested-failure probability bound. No deck "
     "of rules reads a claim yet. What is asked of a part of a deck's type is the grid of its deck: every "
     "mechanism the deck asks about, for every part of the type, under every load case.",
     "claim strength: frame.collapse_factor >= 1.5 under crowd\n"
     "claim stress:   frame.member(diag_ad).stress <= 235 MPa margin 10 MPa under crowd\n"
     "claim overload: P(hook.utilisation > 1) <= 3/10 under lift\n"
     "claim tested:   P(fail hook at 36 kN) <= 1/100 confidence 95 % from proof"),
    ("waive", "`waive` rests an open cell of the grid on a signature. Only the card can waive. It names the "
     "mechanism, the part, who answers for it, and the reason. The Types section lists the mechanisms the grid "
     "asks of each type. A waiver rests only a cell the deck has no rule for, or one that holds under a "
     "completion of what the design leaves out. Petra reports such a cell as waived, never as proved, and a "
     "pass that rests on one reads PASS_WAIVED.",
     'waive lap.tightening on splice by "s.engineer@example.org" reason "snug-tight bolts: a bearing-type joint under static load, J3.2 (a)(1)"'),
)
"""(declaration, what it says, an example). Every declaration but `param` and `component` is
the card's. tests/test_teach.py parses the examples."""


def _grammar() -> str:
    """The EBNF block of lang/syntax.py's docstring."""
    lines = syntax.__doc__.splitlines()
    start = next(i for i, line in enumerate(lines) if line.lstrip().startswith("card file "))
    end = next(i for i in range(start, len(lines)) if not lines[i].strip())
    return "\n".join(line[4:] for line in lines[start:end])


def _units() -> list[str]:
    """`| dimension | spellings |` rows: every unit a .petra file can write."""
    by_dim: dict[str, list[str]] = {}
    for table in (UNITS, CUSTOMARY):
        for spelling, (_, dim) in table.items():
            if all(map(_NAME.fullmatch, spelling.split("/", 1))) or spelling == "%":
                name = _DIMENSIONS.get(dim) or dimension_name(dim)
                by_dim.setdefault("energy, torque" if name == "energy" else name, []).append(f"`{spelling}`")
    return [f"| {dim} | {', '.join(spellings)} |" for dim, spellings in by_dim.items()]


_DIMENSIONS = {FREQUENCY: "turns or cycles in a time", CHARGE: "charge", SPEED: "speed", DENSITY: "density", STIFFNESS: "force over length"}
"""What the units table calls a dimension that has no name of its own in a file."""

_FACTORS = [
    ("`kW`", "1,000 W", "the SI prefix"),
    ("`min`, `h`", "60 s and 3,600 s", "the SI Brochure, 9th edition, Table 8"),
    ("`Hz`", "1 a second", "the SI Brochure, 9th edition, Table 4"),
    ("`rpm`", "1/60 Hz", "one turn a minute, where a turn is the plain number 1"),
    ("`mAh`, `Ah`", "18/5 A s and 3,600 A s", "a current for an hour of 3,600 s"),
    ("`m/s`", "1 m/s", "the SI unit"),
    ("`km/h`", "5/18 m/s", "1,000 m in 3,600 s"),
    ("`knot`", "463/900 m/s", "one international nautical mile of 1,852 m in 3,600 s"),
    ("`kg/m3`, `g/cm3`", "1 kg/m3 and 1,000 kg/m3", "the SI unit and its prefixes"),
    ("`N/mm`", "1,000 N/m", "the SI prefix"),
    ("`mile`", "201168/125 m, which is 1,609.344 m", "5,280 ft of 0.3048 m, by the international yard of 1959"),
    ("`mph`", "1397/3125 m/s, which is 0.44704 m/s", "a mile in 3,600 s"),
    ("`lb`", "45359237/100000000 kg, which is 0.45359237 kg", "the international pound of 1959"),
    ("`oz`", "1/16 lb, which is 0.028349523125 kg", "the avoirdupois ounce"),
    ("`lbf_in`, `lbf_ft`", "a pound-force times an inch, and times 12 inch", "`lbf` and `inch`, as `kip_in` and `kip_ft` are written"),
]
"""The units read since 2026-11-11, each with its exact factor and where the factor comes from."""


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def _types_markdown() -> list[str]:
    out = []
    for deck in grid.decks():
        out += [f"### Deck {deck.name}", "", f"Its file's hash is `{deck.hash}`. `petra kinds {deck.name}` prints this.", "",
                "```", _deck_text(deck, tuple(deck.types)).rstrip("\n"), "```", ""]
    return out


def render_reference() -> str:
    from .cli import EXIT_CODES

    lines = [
        "# The Petra language",
        "",
        "`petra docs reference` prints this page. On the command line, `petra kinds [DECK|TYPE]` and",
        "`petra new TYPE [--name NAME] [--card]` print the same tables.",
        "",
        "`python -m petra.teach --write` generates this page from the shipped decks of rules, as the grid reads",
        "them, and the examples. Do not edit it by hand. tests/test_teach.py fails when the page is stale.",
        "",
        "## File layout and syntax",
        "",
        "A check reads two files. The card, `NAME.card`, holds what is asked: the name, every signed bound, the",
        "load cases, and the waivers. The design, `NAME.petra`, holds the answer: the parts. Whoever asks writes",
        "the card, and a designer or an agent writes the design. A design cannot state a load, a waiver, or a",
        "signature, so it cannot change what is asked of it.",
        "`petra check NAME.petra` reads `NAME.card` beside the design, and `--card FILE` names another card.",
        "",
        "```",
        "petra 0",
        "",
        'card "lap-splice" {',
        '  owner "s.engineer@example.org"',
        "}",
        "",
        'given tab.Fy in [36 ksi, 36 ksi] signed "s.engineer@example.org" source "ASTM A36, specified minimum"',
        "...",
        "",
        "load gravity {",
        "  on splice pull in [0 kip, 45 kip]",
        '  signed "s.engineer@example.org" source "calculation C-12, LRFD combination 1.2D + 1.6L"',
        "}",
        "```",
        "",
        "```",
        "petra 0",
        "",
        "plate tab {",
        "  thickness 0.375 inch",
        "  Fy given tab.Fy",
        "  ...",
        "}",
        "",
        "lap splice {",
        "  count 3",
        "  joins tab strap",
        "  ...",
        "}",
        "```",
        "",
        "These rules apply to both files.",
        "",
        "- The first line is `petra 0`, the language version.",
        "- The rest of a card holds one `card` block and the `param`, `ambient`, `given`, `load`, `tests`,",
        "  `claim`, and `waive` declarations. The rest of a design holds the components and the `param`",
        "  declarations. Each component, load, tests, param, given, and claim name is declared once.",
        "- Inside a block, each line holds one attribute. A comment runs from `#` to the end of the line.",
        "- A name consists of letters, digits, and `_`, and starts with a letter or `_`. A `-` is never part of a",
        "  name. Write `L4x3-1/2x3/8` as `L4x3_1_2x3_8`, and write `WT5x22.5` as `WT5x22_5`.",
        "- A name may be dotted, as in `tab.Fy`. The part after a dot may start with a digit.",
        "- A number is exact. It is an integer, a decimal, or a fraction such as `3/4`, and it never has an",
        "  exponent. The unit follows the number, as in `0.75 inch`, `45 kip`, and `10mm`. A number with no unit",
        "  is dimensionless.",
        '- A string is written `"..."`. Its only escapes are `\\"` and `\\\\`.',
        "- A bound is a range with its provenance, written",
        "  `in [<lo>, <hi>] [mean <value>] signed \"<owner>\" source \"<source>\"`. A measured value has",
        "  `measured` in place of `signed`. Only a card states a bound, and outside a family every bound carries",
        "  a signature. In a family, `param NAME` stands where a bound would.",
        "- `in`, `mean`, `signed`, `measured`, `source`, `param`, and `given` cannot be names inside a line. No",
        "  declared name can be a declaration word.",
        f"- A file has at most {MAX_FILE:,} bytes. `petra check`, `petra.export` and the MCP tools refuse a larger",
        "  file before they parse it.",
        "",
        "A pair that is refused prints its problems, each with its file, line and column. What is printed is",
        "bounded, whatever the files hold.",
        "",
        f"- A message that names a table, such as the kinds or the givens of the card, lists at most {MAX_LISTED} of",
        "  its names and says how many it has. For an unknown mechanism they are the names that start most as",
        "  the unknown one does.",
        "- A message that arises more than once is printed once, at the first place, with how many times it",
        "  arose.",
        f"- At most {MAX_PROBLEMS} problems are printed for a file, and then how many more there were.",
        f"- A problem of more than {MAX_MESSAGE} characters is cut, and says how many were left out.",
        "",
        "## Declarations",
        "",
    ]
    for decl, what, example in SNIPPETS:
        lines += [f"### {decl}", "", what, "", "```", example, "```", ""]
    lines += ["## Grammar", "", "The grammar below is EBNF, and `NL` is a line end. The types of parts and their lines "
              "are not in the grammar. Each deck of rules declares its own, as the Types section shows.",
              "", "```", _grammar(), "```", "",
              "## Units", "", "A card and a design accept these unit spellings.", "",
              "| dimension | spellings |", "|---|---|", *_units(), "",
              "A unit of length may be raised to the power 2, 3 or 4: the unit, `^` and the power, with no space, as",
              "in `mm^3` and `inch^4`. Its factor is the unit's own factor to that power, exactly, so `1 inch^4` is",
              "(127/5000)^4 m^4. A power is one of `2`, `3` and `4`, written as that one digit: `inch^1`, `inch^5`,",
              "`inch^04` and `inch^3/2` are refused. Only a unit of length takes a power, so `kN^2` and `mm2^2` are",
              "refused. An area has two spellings with one meaning: `mm^2` is `mm2`, `m^2` is `m2` and `inch^2` is",
              "`inch2`. A section modulus is written in a length to the third power and a moment of inertia in a",
              "length to the fourth. Petra prints such a quantity in `mm^3`, `cm^3`, `m^3` and the like, which it",
              "reads back.", "",
              "A unit is one spelling of the table and nothing else. A unit with a `/` in it, as `m/s`, `km/h`,",
              "`kg/m3` and `ohm/km` are, is written with no space and is never worked out from its halves: `m/s` is",
              "one unit, and `mm/s`, `m/min` and `kg/m^3` are none. A product is written with `_`, as in `kip_in`",
              "and `lbf_ft`. A unit that had a spelling got no second one, so a newton metre is `Nm`. `mAh` is no",
              "`m`, `A` and `h`, and `min` no `m` and `in`: a spelling is read whole. A word right after a number is its unit,",
              "whatever else has that name: `h 2 h` gives the field `h` two hours, and `5 K` is refused, because",
              "`K` is no unit.", "",
              "These units are read since 2026-11-11. Each factor is exact. NIST Special Publication 811, 2008",
              "edition, Appendix B, lists each factor that is not SI's own and marks it exact.", "",
              "| unit | is | by |", "|---|---|---|", *(f"| {unit} | {factor} | {source} |" for unit, factor, source in _FACTORS), "",
              "A rotation is counted in turns, and a turn is the plain number 1. So a speed of rotation is a plain",
              "1 over a time: `Hz` is one turn a second, and `rpm` is one turn a minute. An angle is a plain number",
              "too, and Petra has no unit for one: a deck that needs radians writes the 2 pi itself. A report",
              "prints a time in `s` or `ms` and a power in `W` or `mW`, and never chooses `min`, `h`, `kW`, `rpm`,",
              "`km/h` or `knot`.", "",
              "The one unit of temperature is `degC`. Its number is the temperature on the Celsius scale, with its",
              "sign: `-10 degC` is ten below freezing. There is no `K` and no `degF`. A unit is a factor and",
              "nothing more, and those two need an offset as well. With one, `50 degF` would be read as 10 degC",
              "where it is a temperature and as 27.8 degC where it is a difference of two, and nothing in a value",
              "says which it is. So a temperature in Fahrenheit is written in `degC` as the exact fraction:",
              "25 degF is `-35/9 degC` and 150 degF is `590/9 degC`. A difference of temperatures is in `degC`",
              "too, and a kelvin of difference is `1 degC`.", "",
              "## Exit codes of `petra check`", "", "| status | code |", "|---|---|",
              *(f"| {status} | {code} |" for status, code in EXIT_CODES.items()), "",
              "PASS_WAIVED is the pass of a design checked against a deck of rules when a waiver of its card rests",
              "a cell: the design passes what the deck could check, and each signer answers for the cells its",
              "waiver rests. `petra check --json` lists those waivers under `waived`, and the kernel says PASS",
              "and lists the same waivers.", "",
              "## Types", "",
              "A part is written `TYPE NAME { ... }`, with one line per field. A type belongs to a deck of rules,",
              "which says what each of its lines means, what a part of it needs to be a part at all, and which",
              "mechanisms the grid asks of every part of it. A mechanism with a rule is worked out by the kernel. One",
              "with no rule yet is an open cell, and the design reads UNKNOWN until a rule or a waiver settles it.", "",
              *_types_markdown()]
    return "\n".join(lines)


# --- petra docs ---------------------------------------------------------------------------

DOCS_DIR = Path(__file__).with_name("docs")


def readme() -> str:
    """README.md of the source tree petra runs from (a clone or an editable install), else
    the copy the installed distribution carries as its description."""
    if verify.source_tree(ROOT) and (ROOT / "README.md").is_file():
        return (ROOT / "README.md").read_text(encoding="utf-8")
    return importlib.metadata.metadata("petra-lang").get_payload()


DOCS: Mapping[str, tuple[str, Callable[[], str]]] = {
    "readme": ("installing Petra and a quickstart", readme),
    "reference": ("the .petra language: syntax, units, and the lines of every type of the shipped decks", render_reference),
    "api": ("the Python API, and the JSON that `petra check --json` prints",
            lambda: (DOCS_DIR / "api.md").read_text(encoding="utf-8")),
    "skill": ("how a coding agent designs and checks with Petra, and the MCP server; a SKILL.md",
              lambda: (DOCS_DIR / "skill.md").read_text(encoding="utf-8")),
}
"""`petra docs NAME` -> (what the document is, its text)."""


def docs_text(name: str | None) -> str:
    """The document `name`, or with None one line per document."""
    if name is None:
        width = max(map(len, DOCS))
        return "".join(f"{n:<{width}}  {what}\n" for n, (what, _) in DOCS.items()) + "`petra docs NAME` prints one.\n"
    if name not in DOCS:
        raise _unknown(name, "a document", list(DOCS))
    return DOCS[name][1]()


# --- main --------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m petra.teach", description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="rewrite docs/reference.md and petra/templates.py")
    args = parser.parse_args(argv)
    stale = []
    for path, render in ((TEMPLATE_MODULE, render_templates), (REFERENCE, render_reference)):
        text = render()
        if args.write:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {path.relative_to(ROOT)}")
        elif not path.exists() or path.read_text(encoding="utf-8") != text:
            stale.append(str(path.relative_to(ROOT)))
    for path in stale:
        print(f"{path} is stale: run python -m petra.teach --write")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
