"""What `petra kinds`, `petra new`, `petra registry list` and `petra docs` print, and
docs/reference.md. Untrusted tooling: it prints the grammars the lowerers read
(DomainSpec.grammars), the registry, the canonical examples and the documents, and decides
no verdict.

    python -m petra.teach            exit 1 when docs/reference.md or petra/templates.py
                                     differs from what this module renders
    python -m petra.teach --write    rewrite both

petra/templates.py copies each kind's canonical example (`example_of`), so `petra new`
works from an installed package, which carries no examples/ directory. For the same reason
`petra docs` renders the reference here, reads the hand-written documents from petra/docs/,
and reads the README from the installed distribution's metadata.
"""
from __future__ import annotations

import argparse
import difflib
import importlib.metadata
import re
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from . import deck as deck_rows
from . import grid, models
from .files import MAX_FILE, MAX_LISTED, MAX_MESSAGE, MAX_PROBLEMS, card_of
from .ir import FromTests, RangeMean
from .lang import parse_design, syntax
from .lang.lexer import Kind, tokenize
from .models.base import CROSS_DOMAIN_MODES, DomainSpec, Field
from .models.steel.lower import SHAPE_GROUP, THREAD_MARKS, tee_parent
from .registry import Constant, ProcessKind, Registry, build_registry, steel_shapes
from .registry.model import fold, hint
from .registry.steel import STOCK_PLATE
from .units import CHARGE, CUSTOMARY, DENSITY, FREQUENCY, SPEED, STIFFNESS, UNITS, dimension_name

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "docs" / "reference.md"
TEMPLATE_MODULE = Path(__file__).with_name("templates.py")

CANONICAL: Mapping[str, str] = {
    "truss": "examples/truss_pass.petra",
    "circuit": "examples/circuit_pass.petra",
    "joint": "examples/bolt_unknown.petra",
    "demand": "examples/hook_uncertain.petra",
    "lap": "examples/deck/lap_pass.petra",
}
"""Kind -> its canonical example, for the kinds whose example predates the rule that a
kind's example is examples/<domain>/<kind>.petra, and for each type of a deck that has one."""

_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class TeachError(ValueError):
    """An unknown domain, kind or registry prefix, or a --name a design cannot take. The
    CLI reports it as an input error."""


def example_of(kind: str) -> str:
    return CANONICAL[kind] if kind in CANONICAL else f"examples/{models.KINDS[kind].name}/{kind}.petra"


def _unknown(name: str, what: str, known: list[str]) -> TeachError:
    close = difflib.get_close_matches(name, known)
    tail = f"did you mean {' or '.join(close)}?" if close else f"one of {', '.join(known)}"
    return TeachError(f"{name!r} is not {what}; {tail}")


# --- petra kinds ------------------------------------------------------------------------


def _select(name: str | None) -> list[tuple[DomainSpec, tuple[str, ...]]]:
    """(domain, the kinds to print) for every domain, one domain, or one kind."""
    if name is None:
        return [(d, tuple(d.kinds)) for d in models.DOMAINS.values()]
    if name in models.DOMAINS:
        return [(models.DOMAINS[name], tuple(models.DOMAINS[name].kinds))]
    if name in models.KINDS:
        return [(models.KINDS[name], (name,))]
    if _decks(name):
        return []
    raise _unknown(name, "a domain, a deck or a component kind", [*models.DOMAINS, *models.KINDS, *(d.name for d in grid.decks()), *grid.kinds()])


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
                form = "<" + " | ".join(f'"{k}"' if " " in k else k for k in f.keys) + ">"
            else:
                form = f"given <name>.{f.name}" if f.signed else "<whole number>" if f.whole else f"<{deck_rows.show(f.dim)}>"
            note = "; the card states it: given <name>." + f.name + " in [<lo>, <hi>] signed ..." if f.signed else ""
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


def _component(domain: DomainSpec, kind: str) -> str:
    """"<truss>" from the target "<truss>.<node>": how the kind's lines name the component."""
    return domain.grammars[kind].target.split(".")[0]


def claim_forms(domain: DomainSpec, kind: str) -> list[str]:
    """The claim declarations a component of `kind` takes; `<qoi>` is one of domain.qois."""
    c = _component(domain, kind)
    out = []
    if domain.qois:
        out.append(f"claim <name>: {c}.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]")
    if RangeMean in domain.probability:
        out.append(f"claim <name>: P({c}.utilisation > <value>) <= <p> under <load>")
    if FromTests in domain.probability:
        out.append(f"claim <name>: P(fail {c} at <level>) <= <p> confidence <value> from <tests>")
    return out


def load_form(domain: DomainSpec, kind: str) -> str:
    grammar = domain.grammars[kind]
    return f"on {grammar.target} {'|'.join(grammar.loads)} in [<lo>, <hi>] [mean <value>]"


def _modes(domain: DomainSpec) -> list[str]:
    return sorted(m.id for m in domain.modes)


def _facts(field: Field) -> str:
    facts = [field.unit] if field.unit else []
    if field.registry:
        facts.append("ids " + ", ".join(f"{p}*" for p in field.registry))
    return f" [{'; '.join(facts)}]" if facts else ""


def kinds_summary() -> str:
    """Each domain with its kinds, then how to print a kind's lines."""
    lines = [textwrap.fill(f"domain {d.name}: {', '.join(d.kinds)}", width=100, subsequent_indent="  ")
             for d in models.DOMAINS.values()]
    lines += ["", *(f"deck {d.name}: {', '.join(d.types)}" for d in grid.decks())]
    return "\n".join([*lines, "",
                      "`petra kinds KIND` prints the lines a kind takes, each with its meaning; `petra kinds DOMAIN`",
                      "prints them for every kind of a domain, and `petra kinds --all` for every kind.",
                      "`petra new KIND` prints a complete design of KIND to start from.", ""])


def kinds_text(name: str | None) -> str:
    """Every kind of every domain, of one domain, or one kind: its load and claim forms
    and its attribute lines, required then optional, each with its meaning."""
    lines: list[str] = []
    for domain, kinds in _select(name):
        lines += [f"domain {domain.name}: {', '.join(domain.kinds)}",
                  f"  waive <mode> on <path> by \"<owner>\" reason \"<reason>\", <mode> one of "
                  f"{', '.join(_modes(domain))}", ""]
        for kind in kinds:
            grammar = domain.grammars[kind]
            lines += [f"{kind} <name> {{ one line each }}    `petra new {kind}` prints {example_of(kind)}",
                      f"  load entry: {load_form(domain, kind)}"]
            lines += [f"  {form}" for form in claim_forms(domain, kind)]
            if domain.qois:
                lines.append(f"    <qoi>: {', '.join(domain.qois)}")
            for heading, fields in (("required", grammar.required), ("optional", grammar.optional)):
                if fields:
                    lines.append(f"  {heading}:")
                    for f in fields:
                        lines += [f"    {f.name} {f.form}", f"        {f.meaning}{_facts(f)}"]
            lines.append("")
    lines += [_deck_text(deck, types) for deck, types in _decks(name)]
    return "\n".join(lines)


def kinds_json(name: str | None) -> dict:
    def field(f: Field, required: bool) -> dict:
        return {"name": f.name, "required": required, "form": f.form, "unit": f.unit, "registry": list(f.registry),
                "meaning": f.meaning}

    return {"domains": [{
        "domain": domain.name,
        "modes": _modes(domain),
        "kinds": [{
            "kind": kind,
            "example": example_of(kind),
            "load": load_form(domain, kind),
            "load_target": domain.grammars[kind].target,
            "load_fields": list(domain.grammars[kind].loads),
            "claims": claim_forms(domain, kind),
            "qois": list(domain.qois),
            "fields": [field(f, True) for f in domain.grammars[kind].required]
                      + [field(f, False) for f in domain.grammars[kind].optional],
        } for kind in kinds],
    } for domain, kinds in _select(name)]}


# --- petra new --------------------------------------------------------------------------


def new_text(kind: str, name: str | None, registry: Registry) -> tuple[str, str]:
    """The canonical example of `kind` as (its card, its design), the component renamed to
    `name` in both when given. The pair is lowered before it is returned, so a name the
    design cannot take is an error (LolaSyntaxError or LoweringError), never a broken file."""
    from .templates import TEMPLATES

    if kind not in TEMPLATES:
        if kind in grid.kinds():
            raise TeachError(f"a {kind} is written with the part that joins it; `petra kinds {kind}` lists its lines")
        raise _unknown(kind, "a component kind", list(TEMPLATES))
    source, component, card, text = TEMPLATES[kind]
    if name is not None:
        if not _NAME.fullmatch(name):
            raise TeachError(f"--name {name!r} is not a name: letters, digits and _, starting with a letter or _")
        card, text = rename(card, component, name), rename(text, component, name)
    first, _, rest = text.partition("\n")
    out = f"{first}\n# From {source}. `petra kinds {kind}` lists every line a {kind} takes.\n{rest}"
    parse_design(card, out, f"<petra new {kind}>", registry)
    return card, out


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
    """petra/templates.py: each kind's canonical example, the name of its component of
    that kind, its card's text and its design's."""
    registry = build_registry()
    lines = ['"""Generated by `python -m petra.teach --write` from the examples it names; do not edit.',
             "`petra new KIND` prints from TEMPLATES[KIND]: (the example, the name of its KIND component,",
             'the text of its card, the text of its design). tests/test_teach.py fails when this file is stale."""',
             "",
             "TEMPLATES: dict[str, tuple[str, str, str, str]] = {"]
    for kind in (*models.KINDS, *(k for k in grid.kinds() if k in CANONICAL)):
        source = example_of(kind)
        card, text = (ROOT / card_of(source)).read_text(encoding="utf-8"), (ROOT / source).read_text(encoding="utf-8")
        design = parse_design(card, text, source, registry)
        named = [c.name for c in design.components.values() if c.kind == kind]
        if len(named) != 1:
            raise ValueError(f"{source} has {len(named)} {kind} components; a canonical example has one")
        lines += [f"    {kind!r}: (", f"        {source!r},", f"        {named[0]!r},"]
        for body in (card, text):
            lines += ["        (", *(f"            {line!r}" for line in body.splitlines(keepends=True)), "        ),"]
        lines.append("    ),")
    lines.append("}")
    return "\n".join(lines) + "\n"


# --- petra registry list ----------------------------------------------------------------


@dataclass(frozen=True)
class Listed:
    id: str
    what: str
    names: tuple[str, ...]   # the common names that resolve to it


_INCH = CUSTOMARY["inch"][0]

_PROCESSES: Mapping[ProcessKind, str] = {
    ProcessKind.INSTALL: "cable installation method",
    ProcessKind.COATING: "coating",
    ProcessKind.WELD: "weld",
    ProcessKind.CUT: "cut",
    ProcessKind.PRINT: "printing preset (material extrusion)",
    ProcessKind.POWDER: "printing preset (powder-bed fusion)",
    ProcessKind.SHEET: "sheet cutting preset",
    ProcessKind.MILL: "milling preset",
    ProcessKind.MOLD: "molding preset",
}


def _inches(c: Constant) -> str:
    return f"{float(c.value.lo / _INCH):g} in"


def tee_of(w: str) -> str | None:
    """W18x50 -> WT9x25: the tee cut from a W, which steel.lower.tee_parent reads back."""
    depth, _, weight = w[1:].partition("x")
    try:
        halves = [float(part.replace("_", ".")) / 2 for part in (depth, weight)]
    except ValueError:
        return None
    text = [str(int(h)) if h == int(h) else str(h).replace(".", "_") for h in halves]
    tee = f"WT{text[0]}x{text[1]}"
    return tee if tee_parent(tee) == w else None


def listing(registry: Registry, shapes: Mapping[str, Constant]) -> list[Listed]:
    """Every id a design names, with one line on what it is: materials, parts, processes,
    environments, then the shapes in `shapes` (W, the WT cut from each, L) and the
    stocked plate thicknesses."""
    names: dict[str, list[str]] = {}
    for common, mid in registry.names.items():
        names.setdefault(mid, []).append(common)
    out = []
    for m in registry.materials.values():
        what = f"{m.family}: {m.standard}"
        if m.family == "bolt":
            what += "; AISC's -N and -X are `threads included` and `threads excluded`"
        out.append(Listed(m.id, what, tuple(names.get(m.id, ()))))
    out += [Listed(p.id, f"{p.kind.value}: {p.designation}", ()) for p in registry.parts.values()]
    for p in registry.processes.values():
        what = _PROCESSES[p.kind] + (f", leaves {p.surface} exposed" if p.surface else "")
        what += "".join(f"; {e.material_family} {e.prop} reduced {e.zone}" for e in p.effects)
        out.append(Listed(p.id, what, ()))
    out += [Listed(e.id, f"environment: corrosivity {e.corrosivity.value}, {'wet' if e.wet else 'dry'}, "
                         f"{e.ambient.conditions}", ()) for e in registry.environments.values()]
    rows: dict[str, dict[str, Constant]] = {}
    for key, c in shapes.items():
        group, _, rest = key.partition(".")
        shape, _, prop = rest.partition(".")
        if group == SHAPE_GROUP:
            rows.setdefault(shape, {})[prop] = c
    w = [s for s in rows if s.startswith("W") and "bf" in rows[s]]
    out += [Listed(s, f"W shape: d {_inches(rows[s]['d'])}, bf {_inches(rows[s]['bf'])}, tw {_inches(rows[s]['tw'])}, "
                      f"tf {_inches(rows[s]['tf'])}", ()) for s in w]
    out += [Listed(tee, f"WT shape, cut from {s}", ()) for s in w if (tee := tee_of(s))]
    out += [Listed(s, f"angle: legs {_inches(rows[s]['d'])} x {_inches(rows[s]['b'])}, thickness "
                      f"{_inches(rows[s]['t'])}", ()) for s in rows if s.startswith("L") and "t" in rows[s]]
    out += [Listed(k, c.statement, ()) for k, c in registry.constants.items() if k.startswith(STOCK_PLATE)]
    return out


def registry_text(registry: Registry, prefix: str | None, shapes: Mapping[str, Constant]) -> str:
    """One line per id starting with `prefix` (any case) or with a common name that does."""
    entries = listing(registry, shapes)
    if prefix is not None:
        entries = [e for e in entries if e.id.lower().startswith(prefix.lower())
                   or any(fold(n).startswith(fold(prefix)) for n in e.names)]
        if not entries:
            ids = [e.id for e in listing(registry, shapes)]
            raise TeachError(f"no registry id starts with {prefix}{hint(registry.suggest(prefix, ids))}")
    width = max(len(e.id) for e in entries)
    return "".join(f"{e.id:<{width}}  {e.what}{'; also ' + ', '.join(e.names) if e.names else ''}\n" for e in entries)


# --- docs/reference.md --------------------------------------------------------------------

SNIPPETS: tuple[tuple[str, str, str], ...] = (
    ("card", "A card has one `card` block, which names what is asked. `owner` is required. `environment` is "
     "optional and names a registry environment from the registry list at the end of this page. No deck of "
     "rules reads an environment yet. So the card of a design with a part of a deck's type, such as a `lap`, "
     "states none, and `petra check` refuses one that does.",
     'card "warren-footbridge-panel" {\n  owner "a.reviewer@example.org"\n  environment indoor_dry\n}'),
    ("param", "`param` declares a family. The design holds for every value in the param's range. A line names the "
     "param by writing `param NAME` in place of a value. A param is declared in the card or in the design. A "
     "load and the ambient read only the card's params, and `petra check` refuses a load or an ambient that "
     "reads one, because nobody signed it: a family goes to `petra certify-family`.",
     "param run in [0 m, 20 m]"),
    ("ambient", "`ambient` declares the ambient temperature range, with a signature.",
     'ambient in [10 degC, 40 degC] signed "site.manager@example.org" source "site survey 2026-09"'),
    ("given", "`given` states a signed bound under a name. A component's line in the design reads it by writing "
     "`given NAME` where the value goes. The design reads every given the card states. A name may be `PART.FIELD`. "
     "A part of a deck's type reads only the given named for it: `Fy given tab.Fy` on the part `tab`.",
     'given capacity in [36 kN, 40 kN] measured "qa.lab@example.org" source "proof-load report PL-0917"'),
    ("component", "A component is written `KIND NAME { ... }` in the design, with one attribute per line. The "
     "Component kinds section lists every kind and its lines.",
     "demand hook {\n  capacity given capacity\n}"),
    ("load", "A `load` block is one load case. Each entry is `on <target> <field> <bound>`. An entry is signed by "
     "its own signature or by the signature on the block's last line. A probability claim reads the `mean` of "
     "an entry.",
     'load lift {\n  on hook force in [0 kN, 40 kN] mean 10 kN\n'
     '  signed "ops.lead@example.org" source "hoist duty log 2025, 14200 lifts"\n}'),
    ("tests", "A `tests` block records proof tests. A tested-failure claim reads it.",
     'tests proof {\n  on hook trials 300 failures 0 at 36 kN\n'
     '  signed "qa.lab@example.org" source "batch 2026-09 proof tests, independent lots"\n}'),
    ("claim", "A claim takes one of three forms:\n\n"
     "- A bound on a quantity, with an optional margin and the load cases it holds under. Without `under`, the "
     "claim holds under every load case on the component.\n"
     "- A range-and-mean probability bound.\n"
     "- A tested-failure probability bound.\n\n"
     "The Component kinds section lists the quantities of each kind. A claim with a margin is MARGINAL when it "
     "is proved and a certified point lies within the margin of its bound.",
     "claim strength: frame.collapse_factor >= 1.5 under crowd\n"
     "claim stress:   frame.member(diag_ad).stress <= 235 MPa margin 10 MPa under crowd\n"
     "claim overload: P(hook.utilisation > 1) <= 3/10 under lift\n"
     "claim tested:   P(fail hook at 36 kN) <= 1/100 confidence 95 % from proof"),
    ("waive", "`waive` accepts an open coverage demand on a component. Only the card can waive. It names the "
     "failure mode, who answers for it, and the reason. The Component kinds section lists the failure modes of each domain. Petra reports "
     "a waived demand as waived, never as proved.",
     'waive bolt.plate_bearing on bracket by "m.engineer@example.org" reason "bearing checked by test PB-3"'),
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


def _kinds_markdown() -> list[str]:
    out = []
    for domain in models.DOMAINS.values():
        out += [f"### Domain {domain.name}", "",
                f"Waivable modes: {', '.join(f'`{m}`' for m in _modes(domain))}.", ""]
        for kind in domain.kinds:
            grammar = domain.grammars[kind]
            out += [f"#### {kind}", "",
                    f"A `{kind}` component is written `{kind} <name> {{ ... }}`. `petra new {kind}` prints its "
                    f"example, `{example_of(kind)}`.", "",
                    f"Load entries and claims on a `{kind}` component take these forms:", "",
                    f"- Load entry: `{load_form(domain, kind)}`"]
            out += [f"- Claim: `{form}`" for form in claim_forms(domain, kind)]
            if domain.qois:
                out += ["", f"In a claim, `<qoi>` is one of {', '.join(f'`{q}`' for q in domain.qois)}."]
            out += ["", "| line | form | needed | unit | ids | meaning |", "|---|---|---|---|---|---|"]
            for required, fields in ((True, grammar.required), (False, grammar.optional)):
                for f in fields:
                    ids = ", ".join(f"`{p}*`" for p in f.registry)
                    out.append(f"| `{f.name}` | `{_cell(f.form)}` | {'required' if required else 'optional'} | "
                               f"{f.unit} | {ids} | {_cell(f.meaning)} |")
            out.append("")
    return out


def render_reference() -> str:
    from .cli import EXIT_CODES

    registry = build_registry()
    shapes = steel_shapes.constants(steel_shapes.shipped())
    marks = " and ".join(f"`-{mark}` is `threads {threads}`" for mark, threads in THREAD_MARKS.items())
    lines = [
        "# The Petra language",
        "",
        "`petra docs reference` prints this page. On the command line, `petra kinds [DOMAIN|KIND]`,",
        "`petra new KIND [--name NAME] [--card]`, and `petra registry list [PREFIX]` print the same tables.",
        "",
        "`python -m petra.teach --write` generates this page from the grammars that the lowerers read, the",
        "registry, and the examples. Do not edit it by hand. tests/test_teach.py fails when the page is stale.",
        "",
        "## File layout and syntax",
        "",
        "A check reads two files. The card, `NAME.card`, holds what is asked: the name, the environment, every",
        "signed bound, the load cases, the claims, and the waivers. The design, `NAME.petra`, holds the answer:",
        "the components. Whoever asks writes the card, and a designer or an agent writes the design. A design",
        "cannot state a load, a claim, a waiver, or a signature, so it cannot change what is asked of it.",
        "`petra check NAME.petra` reads `NAME.card` beside the design, and `--card FILE` names another card.",
        "",
        "```",
        "petra 0",
        "",
        'card "steel-shear-tab" {',
        '  owner "s.engineer@example.org"',
        "}",
        "",
        "load reaction {",
        "  on st1 shear in [0 kip, 45 kip]",
        '  signed "s.engineer@example.org" source "frame analysis rev 2"',
        "}",
        "```",
        "",
        "```",
        "petra 0",
        "",
        "shear_tab st1 {",
        "  basis lrfd",
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
        "- A registry id is dotted, as in `steel.A992`. The part after a dot may start with a digit, as in",
        "  `bolt_group.120`. The registry list at the end of this page gives every id and the common names that",
        "  stand for it.",
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
        "  its names and says how many it has. For an unknown kind or mode they are the names that start most",
        "  as the unknown one does.",
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
    lines += ["## Grammar", "", "The grammar below is EBNF, and `NL` is a line end. Component kinds and their lines "
              "are not in the grammar. Each domain declares its own, as the Component kinds section shows.",
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
              "## Component kinds", "",
              "A component is written `KIND NAME { ... }`, with one line per attribute. A required line appears at",
              "least once. In a form, `<length>` stands for a length, `given NAME`, or `param NAME`. These",
              "cross-domain modes can be waived on any component: "
              f"{', '.join(f'`{m.id}`' for m in CROSS_DOMAIN_MODES)}.", "",
              *_kinds_markdown(),
              "## Registry", "",
              "The list below is the output of `petra registry list`. It gives every id a design can name, then the",
              "stocked plate thicknesses. A fixed plate thickness is one of the stocked thicknesses.", "",
              "The listed shapes are those of the shipped shape table. When `PETRA_SHAPES_XLSX` is set to the AISC",
              "Shapes Database v16.0 workbook, every W and L row in that workbook is an id. A WT is cut from its W,",
              "as WT9x25 is cut from W18x50.", "",
              "Where a steel connection names a grade, a bolt group, or an electrode, a common name can stand for",
              "the id. A common name matches in any letter case, and `Gr` or `Grade` in it is optional. A common",
              "name is written as one name with `_` between its words, or quoted. For example, `A325` is",
              '`bolt_group.120`, and `A572_50`, `A572_Gr_50`, and `"A572 Gr 50"` are all `steel.A572_50`. A',
              "footprint names the id, not the common name.", "",
              "AISC's thread suffixes are not part of a name. The `bolts` line states the thread condition instead.",
              f"On that line, {marks}, so A325-N is `bolts bolt_group.120 ... threads included`.", "",
              "```", registry_text(registry, None, shapes).rstrip("\n"), "```", ""]
    return "\n".join(lines)


# --- petra docs ---------------------------------------------------------------------------

DOCS_DIR = Path(__file__).with_name("docs")


def readme() -> str:
    """README.md of the source tree petra runs from (a clone or an editable install), else
    the copy the installed distribution carries as its description."""
    if (ROOT / "pyproject.toml").is_file() and (ROOT / "README.md").is_file():
        return (ROOT / "README.md").read_text(encoding="utf-8")
    return importlib.metadata.metadata("petra-lang").get_payload()


DOCS: Mapping[str, tuple[str, Callable[[], str]]] = {
    "readme": ("installing Petra and a quickstart", readme),
    "reference": ("the .petra language: syntax, units, every kind's lines and every registry id", render_reference),
    "api": ("the Python API, and the JSON that `petra check --json` prints",
            lambda: (DOCS_DIR / "api.md").read_text(encoding="utf-8")),
    "skill": ("how a coding agent designs, checks and repairs with Petra, and the MCP server; a SKILL.md",
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
