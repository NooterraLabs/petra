"""Design -> verdict. Trusted, and deliberately short: it binds evidence to obligations
and nothing else.

    models       = lower_components(design, registry)          (each kind's lowerer)
    requirements = coverage.generate(design, models) - waivers
    elaborated   = elaborate(design, models, requirements)     (each mode's builder)
    for each obligation: offer evidence from each source in order; kernel.check decides
    entries      = verdict.entries(outcomes, premises, scope)

Every dispatch reads the domain registry (lola/models/__init__.py): a component's kind
picks its lowerer, a requirement's mode picks its builder. Nothing here names a domain.

Binding invariant: the statement checked is always the one the elaborator just built
from the design. Sources receive that statement and return evidence only. A stored
certificate whose statement hash differs from the obligation's is never consulted,
which is how a tampered or stale certificate fails to discharge anything.

Sources and sinks are untrusted: an exception from one becomes a report warning and
costs only the evidence it would have offered.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Mapping, Protocol, get_args

from . import coverage
from . import models as domains
from .ir import Design, Input, InputKind, Param
from .kernel import GOAL_RULE, TAGS, Evidence, Expr, Interval, Matrix, Q, RangeHyp, Rejection, Statement, Theorem, TooWeak, check, statement_hash
from .models.base import (
    CertificateRejected,
    CertificateTooWeak,
    ComponentError,
    Elaborated,
    Gap,
    NeedsCertificate,
    NoModel,
    NoRuleForQuantity,
    Obligation,
    RegistryInconsistent,
    Requirement,
)
from .models.contracts import contract_obligations
from .premises import Label, LabelKind, Premise, PremiseBook, ScopeParam, Tag, input_label, label_kind, param_label
from .registry import Constant, Deck, OutsideMakeableSet, Registry, check_deck
from .registry.model import render
from .units import UNITS, Dim, Quantity, format_quantity
from .verdict import (
    STATUS,
    ClaimVerdict,
    Discharged,
    Open,
    Outcome,
    Refuted,
    Scope,
    Verdict,
    Waived,
    assemble,
    describe_need,
    entries,
    open_from_gap,
    render as render_verdict,
    verdict_json,
)


class EvidenceSource(Protocol):
    """Untrusted. Implemented by certs.CertStore, library.Library and solvers.SolverSource.
    May return proof or refutation evidence, several candidates, or none."""

    name: str

    def offer(self, statement: Statement, statement_hash: str) -> Iterable[Evidence]:
        ...


class EvidenceSink(Protocol):
    """Receives evidence the kernel accepted, for example to write a certificate file."""

    def record(self, statement: Statement, statement_hash: str, evidence: Evidence, source: str) -> None:
        ...


@dataclass(frozen=True)
class Report:
    """`verdict` is the conjunction over every entry; `entries` has one ClaimVerdict per
    claim, in source order, then the "coverage" entry."""

    design: str
    path: str
    verdict: Verdict
    entries: tuple[ClaimVerdict, ...]
    outcomes: tuple[Outcome, ...]
    warnings: tuple[str, ...]

    def render(self) -> str:
        """The design name and overall status, one status per entry, then
        verdict.render's scope, obligation table, open items and footprint, then any
        warnings."""
        status, *rest = render_verdict(self.verdict, self.outcomes).split("\n")
        statuses = ", ".join(f"{e.claim} {STATUS[type(e.verdict)]}" for e in self.entries)
        return "\n".join([f"{self.design}: {status}", f"entries    {statuses}", *rest, *(f"warning    {w}" for w in self.warnings)])

    def to_json(self) -> Mapping[str, Any]:
        """{"file": path, "design": name, "status": the overall status, "verdicts":
        [verdict.verdict_json(e) for e in entries]}. `lola check --json` prints this."""
        return {
            "file": self.path,
            "design": self.design,
            "status": STATUS[type(self.verdict)],
            "verdicts": [verdict_json(e) for e in self.entries],
        }


def lower_components(design: Design, registry: Registry) -> dict[str, Any]:
    """Component name -> typed model, by models.KINDS[component.kind]'s lowerer. Collects
    every lowerer's problems and raises one ComponentError, which the CLI reports as an
    input error (exit 3)."""
    lowered: dict[str, Any] = {}
    problems: list[str] = []
    for name, component in design.components.items():
        lower = domains.KINDS[component.kind].kinds[component.kind]
        try:
            lowered[name] = lower(component, design, registry)
        except ComponentError as exc:
            problems.extend(exc.problems)
        except OutsideMakeableSet as exc:
            problems.append(f"{component.span.path}:{component.span.line}:{component.span.col}: {name}: {exc}")
    if problems:
        raise ComponentError(tuple(problems))
    return lowered


def elaborate(design: Design, models: Mapping[str, Any], requirements: tuple[Requirement, ...], registry: Registry) -> tuple[Elaborated, ...]:
    """For each requirement, the domain that owns the subject's component kind: a mode in
    models.UNMODELLED becomes Gap(needs=(NoModel(mode, subject),)); otherwise the
    domain's builder for the mode runs. Then contracts.contract_obligations over every
    component's `ports`. A requirement whose mode no domain builds and that is not
    unmodelled is a bug in a DomainSpec, which models/__init__._index already refuses.

    A builder that states nothing for a requirement would let the requirement vanish
    from the verdict, so it becomes a Gap needing NoRuleForQuantity instead."""
    out: list[Elaborated] = []
    for req in requirements:
        spec = domains.KINDS[design.components[req.subject[0]].kind]
        if req.mode in domains.UNMODELLED:
            out.append(Gap(req, (NoModel(req.mode, req.subject),)))
            continue
        built = spec.builders[req.mode](req, models[req.subject[0]], design, registry)
        out.extend(built or (Gap(req, (NoRuleForQuantity(req.id, f"the {spec.name} elaborator stated no obligation for it"),)),))
    specs: dict = {}
    connections = []
    for name, model in models.items():
        ports = domains.KINDS[design.components[name].kind].ports(model, registry)
        connections.extend(ports.connections)
        for port in ports.specs:
            if specs.setdefault(port.ref, port) != port:
                raise ValueError(f"two port specs name {port.ref}")
    if specs or connections:
        out.extend(contract_obligations(design, tuple(connections), specs, registry))
    return tuple(out)


@dataclass(frozen=True)
class _Prepared:
    elaborated: tuple[Elaborated, ...]
    waived: tuple[tuple[Requirement, Premise], ...]
    warnings: tuple[str, ...]


def _prepare(design: Design, registry: Registry) -> _Prepared:
    """Lower, generate, waive and elaborate. Port contracts exist only after elaboration,
    so waivers are applied to them there."""
    lowered = lower_components(design, registry)
    remaining, waived = coverage.apply_waivers(coverage.generate(design, lowered, registry), design)
    elaborated = elaborate(design, lowered, remaining, registry)
    known = set(remaining)
    late = tuple(dict.fromkeys(e.requirement for e in elaborated if e.requirement not in known))
    _, waived_late = coverage.apply_waivers(late, design)
    dropped = {req for req, _ in waived_late}
    waived += waived_late
    matched = {(req.mode.id, req.subject) for req, _ in waived}
    warnings = tuple(
        f"waiver {w.mode} on {'.'.join(w.subject)} at {w.span.path}:{w.span.line} matches no coverage requirement"
        for w in design.waivers
        if (w.mode, w.subject) not in matched
    )
    return _Prepared(tuple(e for e in elaborated if e.requirement not in dropped), waived, warnings)


def check_design(design: Design, registry: Registry, sources: tuple[EvidenceSource, ...], sink: EvidenceSink | None = None, deck: Deck | None = None, path: str = "") -> Report:
    """Check one design. Deterministic given the same sources. Raises ComponentError for
    an input error, including a design with nothing to check: no requirement at all, or
    every requirement waived, leaves no theorem a verdict could rest on."""
    prepared = _prepare(design, registry)
    if not prepared.elaborated:
        why = "every requirement is waived" if prepared.waived else "it states no claim and coverage demands nothing of it"
        raise ComponentError((f"{design.path}: {design.name}: nothing to check, because {why}; a verdict needs at least one requirement to discharge",),)
    flagged: dict[str, list[RegistryInconsistent]] = {}
    for finding in check_deck(deck) if deck is not None else ():
        flagged.setdefault(finding.entry, []).append(RegistryInconsistent(finding.entry, finding.relation, finding.message))
    warnings = list(prepared.warnings)
    outcomes = tuple(_settle(item, sources, sink, flagged, warnings) for item in prepared.elaborated)
    outcomes += tuple(Waived(req, premise) for req, premise in prepared.waived)
    book = build_premise_book(design, registry, outcomes)
    scope = _scope(design)
    return Report(design.name, path or design.path, assemble(outcomes, book, scope), entries(outcomes, book, scope), outcomes, tuple(warnings))


def _settle(item: Elaborated, sources: tuple[EvidenceSource, ...], sink: EvidenceSink | None, flagged: Mapping[str, list[RegistryInconsistent]], warnings: list[str]) -> Outcome:
    if isinstance(item, Gap):
        return open_from_gap(item)
    statement = item.statement
    digest = statement_hash(statement)
    inconsistent = [need for label in _labels(statement, LabelKind.REGISTRY) for need in flagged.get(_registry_entry(label), ())]
    if inconsistent:
        return Open(item.requirement, tuple(dict.fromkeys(inconsistent)))
    rejected: list[tuple[Rejection, str]] = []
    for source in sources:
        for evidence in _offered(source, statement, digest, item.requirement, warnings):
            result = check(statement, evidence)
            if isinstance(result, Rejection):
                rejected.append((result, source.name))
                continue
            if sink is not None:
                try:
                    sink.record(statement, digest, evidence, source.name)
                except Exception as exc:
                    warnings.append(f"could not record the certificate for {item.requirement.id}: {type(exc).__name__}: {exc}")
            kind = Discharged if isinstance(result, Theorem) else Refuted
            return kind(item, result, source.name)
    if not rejected:
        return Open(item.requirement, (NeedsCertificate(digest, _rule_of(statement), item.describe),))
    needs = tuple((CertificateTooWeak if isinstance(r.fault, TooWeak) else CertificateRejected)(r.statement_hash, r.rule, name, r.reason) for r, name in rejected)
    return Open(item.requirement, needs, tuple(r for r, _ in rejected))


def _offered(source: EvidenceSource, statement: Statement, digest: str, requirement: Requirement, warnings: list[str]) -> Iterator[Evidence]:
    """The source's candidates, with any exception it raises turned into a warning."""
    try:
        yield from source.offer(statement, digest)
    except Exception as exc:
        warnings.append(f"{source.name} failed on {requirement.id}: {type(exc).__name__}: {exc}")


def _rule_of(statement: Statement) -> str:
    return GOAL_RULE[type(statement.goal)].id


def _labels(statement: Statement, kind: LabelKind) -> tuple[str, ...]:
    return tuple(h.label for h in statement.hyps if isinstance(h, RangeHyp) and label_kind(h.label) is kind)


def _registry_entry(label: str) -> str:
    """"reg:bolt.M12_A4_70.Rp02_min" -> "bolt.M12_A4_70", the deck entry that holds it.
    A constant "reg:const.iso724.d2_coefficient" lives in deck entry "const.iso724"."""
    return label[len("reg:"):].rpartition(".")[0]


def _scope(design: Design) -> Scope:
    return Scope(tuple(_scope_param(design, p) for p in design.params.values()), tuple(design.loads), design.environment)


def _scope_param(design: Design, p: Param) -> ScopeParam:
    return ScopeParam(param_label(design.name, p.name), p.name, p.range.value, _unit(p.range.dim))


# --- The premise book ------------------------------------------------------------------


def build_premise_book(design: Design, registry: Registry, outcomes: tuple[Outcome, ...]) -> PremiseBook:
    """PremiseBook from the registry constants and ratings, the design's signed inputs,
    its params and design values, the model specs of every obligation in `outcomes`, the
    coverage table, and the waiver premise of every Waived outcome. Called once, after
    every outcome is known.

    Every numeric premise carries the range it grants, which verdict assembly checks
    against each hypothesis that names it:
      reg:<entry>.<prop>, reg:const.<name>   Registry.fact, for each label a kernel result uses
      in:<design>.<input>[.mean]             ambient, load entries, and every signed Input a
                                             domain lowered from component attributes
      in:<design>.tests.<name>.trials|.failures   each tests record
      par:<design>.<param>                   a scope parameter, not a premise
    A "dsg:" label is the design itself, which verdict assembly accepts without an entry.
    """
    premises: list[Premise] = [coverage.table_premise()]
    for outcome in outcomes:
        if isinstance(outcome, Waived):
            premises.append(outcome.waiver)
        elif isinstance(outcome, (Discharged, Refuted)):
            premises.append(outcome.obligation.model.premise())
            result = outcome.theorem if isinstance(outcome, Discharged) else outcome.refutation
            premises += [_registry_premise(registry, label) for label in _labels(result.statement, LabelKind.REGISTRY)]
    for inp in _signed_inputs(design, lower_components(design, registry)):
        premises += _input_premises(design, inp)
    for record in design.tests.values():
        statement = f"{record.name} on {'.'.join(record.subject)}: {record.trials} trials, {record.failures} failures at {_quantity_text(record.level)}"
        for field, count in (("trials", record.trials), ("failures", record.failures)):
            label = input_label(design.name, f"tests.{record.name}.{field}")
            premises.append(Premise(label, Tag.MEASURED, record.signature.owner, record.signature.source, statement, Interval(Q(count), Q(count)), "1"))
    params = [_scope_param(design, p) for p in design.params.values()]
    return PremiseBook(premises, params, ())


def _registry_premise(registry: Registry, label: str) -> Premise:
    key = label[len("reg:"):]
    fact = registry.fact(key)
    if isinstance(fact, Constant):
        return Premise(Label(label), fact.tag, fact.owner, fact.source, fact.statement, fact.value, fact.unit)
    statement = f"{key} {_interval_text(fact.value)} {fact.unit}, {fact.conditions}"
    return Premise(Label(label), fact.tag, fact.owner, fact.standard, statement, fact.value, fact.unit)


_INPUT_TAG = {InputKind.ASSUMED: Tag.ASSUMED, InputKind.MEASURED: Tag.MEASURED}


def _input_premises(design: Design, inp: Input) -> list[Premise]:
    def premise(name: str, q: Quantity, what: str) -> Premise:
        unit = _unit(q.dim)
        text = f"{what} {_quantity_text(q)}"
        return Premise(input_label(design.name, name), _INPUT_TAG[inp.kind], inp.signature.owner, inp.signature.source, text, q.value, unit)

    found = [premise(inp.name, inp.range, f"{inp.name} in")]
    if inp.mean is not None:
        found.append(premise(f"{inp.name}.mean", inp.mean, f"the mean of {inp.name} is"))
    return found


def _signed_inputs(design: Design, lowered: Mapping[str, Any]) -> Iterator[Input]:
    """Every signed Input of the design: its ambient, its load entries, and the ones each
    domain lowered from component attributes into its typed model, found by walking the
    model, so a domain declares its inputs by holding them."""
    roots = [design.ambient, *(e.value for case in design.loads.values() for e in case.entries), *lowered.values()]
    seen: set[int] = set()
    while roots:
        node = roots.pop()
        if id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, Input):
            yield node
        elif dataclasses.is_dataclass(node) and not isinstance(node, type):
            roots += [getattr(node, f.name) for f in dataclasses.fields(node)]
        elif isinstance(node, Mapping):
            roots += list(node.values())
        elif isinstance(node, (tuple, list, set, frozenset)):
            roots += list(node)


def _unit(dim: Dim) -> str:
    """The SI spelling of a dimension, or its base-unit exponents when units.UNITS has no
    unit of factor 1 for it."""
    named = next((u for u, (factor, d) in UNITS.items() if factor == 1 and d == dim), None)
    if named is not None:
        return named
    return " ".join(f"{base}^{e}" for base, e in zip(("m", "kg", "s", "A", "degC"), (dim.m, dim.kg, dim.s, dim.A, dim.degC)) if e)


def _quantity_text(q: Quantity) -> str:
    unit = _unit(q.dim)
    return format_quantity(q, unit) if unit in UNITS else f"{_interval_text(q.value)} {unit}"


def _interval_text(value: Interval) -> str:
    return str(value.lo) if value.lo == value.hi else f"[{value.lo}, {value.hi}]"


# --- explain ------------------------------------------------------------------------------


def explain(design: Design, registry: Registry) -> str:
    """Elaborate without checking and pretty-print each statement in mathematical notation
    with every hypothesis label, so a reviewer can audit the trusted front end and the
    elaborators against the source file. `lola explain FILE` prints this.

    Goals print generically, field by field, with expressions in infix, so a new rule's
    goal prints without a change here."""
    prepared = _prepare(design, registry)
    obligations = sum(isinstance(e, Obligation) for e in prepared.elaborated)
    lines = [
        f"design {design.name} ({design.path})",
        f"{obligations} statements, {len(prepared.elaborated) - obligations} gaps, {len(prepared.waived)} waived",
    ]
    for item in prepared.elaborated:
        lines.append("")
        if isinstance(item, Gap):
            lines.append(f"gap {item.requirement.id}")
            lines += [f"  needs  {describe_need(n)}" for n in item.needs]
            continue
        statement = item.statement
        lines += [
            f"obligation {item.requirement.id}",
            f"  means  {item.describe}",
            f"  model  {item.model.premise().label}  {item.model.form}",
            f"  rule   {_rule_of(statement)}  {statement_hash(statement)}",
            "  for all",
        ]
        width = max((len(h.sym) for h in statement.hyps), default=0)
        for h in statement.hyps:
            if isinstance(h, RangeHyp):
                lines.append(f"    {h.sym:<{width}}  in {_interval_text(Interval(h.lo, h.hi))}   {h.label}")
            else:
                lines.append(f"    {h.sym:<{width}}  := the quantity below (its range is proved by a lemma in the evidence)")
                lines += _term_lines("definition", h.definition, 3)
        lines += _term_lines("goal", statement.goal, 1)
    for req, premise in prepared.waived:
        lines += ["", f"waived {req.id}", f"  by     {premise.owner}: {premise.statement}"]
    lines += [f"warning {w}" for w in prepared.warnings]
    return "\n".join(lines)


_EXPR_TYPES = get_args(Expr)
_TAG_OF = {cls: tag for tag, cls in TAGS.items()}


def _term_lines(name: str, value: object, depth: int) -> list[str]:
    pad = "  " * depth
    if isinstance(value, _EXPR_TYPES):
        return [f"{pad}{name}  {render(value)}"]
    if isinstance(value, Matrix):
        rows: dict[int, list[str]] = {}
        for i, j, v in value.entries:
            rows.setdefault(i, []).append(f"[{j}] {v}")
        return [f"{pad}{name}  {value.rows}x{value.cols} matrix, rows not shown are zero", *(f"{pad}  row {i}: {', '.join(r)}" for i, r in rows.items())]
    if isinstance(value, tuple):
        if not value:
            return [f"{pad}{name}  ()"]
        return [f"{pad}{name}", *(line for i, v in enumerate(value) for line in _term_lines(f"[{i}]", v, depth + 1))]
    if dataclasses.is_dataclass(value):
        head = f"{pad}{name}  {_TAG_OF.get(type(value), type(value).__name__)}"
        return [head, *(line for f in dataclasses.fields(value) for line in _term_lines(f.name, getattr(value, f.name), depth + 1))]
    return [f"{pad}{name}  {value}"]


__all__ = ["ComponentError", "EvidenceSink", "EvidenceSource", "Report", "build_premise_book", "check_design", "elaborate", "explain", "lower_components"]
