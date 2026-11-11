"""Design -> verdict. Trusted, and deliberately short: it binds evidence to obligations
and nothing else.

    models       = lower_components(design, registry)          (each kind's lowerer)
    requirements = coverage.generate(design, models) - waivers
    elaborated   = elaborate(design, models, requirements)     (each mode's builder)
    for each obligation: offer evidence from each source in order; kernel.check decides
    entries      = verdict.entries(outcomes, premises, scope)

A claim with a margin is elaborated twice: once as written, and once with its criterion
tightened by the margin (models.base.Criterion.tightened), which gives each claim
obligation a margin obligation built the same way. Unless the claim obligation is
refuted, its margin obligation is offered to the sources too. Every candidate is tried
against the claim first, at every expression it names: a refutation there is a FAIL,
and a proof there proves the claim. A refutation of the margin statement is then a
point within the margin: MARGINAL beside the claim's proof, or an open item's margin
point without one. A proof of it is the margin proved. A claim obligation whose margin
obligation cannot be built beside it is an open item, never a silent PASS.

Every obligation also carries one validity obligation per row of its model
(models.base.ValidityRow). _Close decides each row, memoised by statement hash for the
run, before an outcome is built: a proof of the claim counts only with every row proved
over the box, and a refutation only with every row proved over the box or at its point
(verdict.at_point). A row refuted there makes the claim an open item needing
OutsideValidity; an undecided row adds its own needs.

Every dispatch reads the domain registry (petra/models/__init__.py): a component's kind
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
from dataclasses import dataclass, field
from functools import cached_property
from typing import TYPE_CHECKING, Any, Iterable, Iterator, Mapping, Protocol, Union, get_args

from . import coverage
from . import models as domains
from .ir import Design, Input, InputKind, Param
from .kernel import GOAL_RULE, TAGS, Evidence, Expr, Interval, Matrix, Q, RangeHyp, Refutation, Rejection, Statement, Theorem, TooWeak, check, statement_hash
from .models.base import (
    CertificateRejected,
    CertificateTooWeak,
    ComponentError,
    Elaborated,
    Gap,
    Need,
    NeedsCertificate,
    NoModel,
    NoRuleForQuantity,
    Obligation,
    OutsideValidity,
    RegistryInconsistent,
    Requirement,
)
from .models.contracts import contract_obligations
from .premises import Label, LabelKind, Premise, PremiseBook, ScopeParam, Tag, input_label, label_kind, param_label
from .registry import Constant, Deck, OutsideMakeableSet, Registry, check_deck
from .registry.model import render
from .units import Quantity, interval_text, quantity_text, readable_text, si_unit
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
    WithinMargin,
    assemble,
    at_point,
    describe_need,
    entries,
    has_margin,
    margin_pair_fault,
    open_from_gap,
    render as render_verdict,
    verdict_json,
)

if TYPE_CHECKING:
    from .readout import Finding, Governing, Unchecked


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
    claim, in source order, then the "coverage" entry. `ir` and `registry` are what the
    design was checked from and against, which `findings` reads."""

    design: str
    path: str
    verdict: Verdict
    entries: tuple[ClaimVerdict, ...]
    outcomes: tuple[Outcome, ...]
    warnings: tuple[str, ...]
    ir: Design | None = field(default=None, repr=False, compare=False)
    registry: Registry | None = field(default=None, repr=False, compare=False)

    @cached_property
    def findings(self) -> tuple[Finding, ...]:
        """One petra.readout.Finding per outcome, in order: its outcome, rule, statement
        hash, demand, capacity and utilisation in the design's units, and its point.
        Computed on first use by tooling that reads the verdict and cannot change it."""
        from .readout import findings
        return findings(self)

    @cached_property
    def governing(self) -> Mapping[str, Governing | None]:
        """The governing "strength" check and the governing "detailing" check over all
        the findings (petra.readout.governing), each None when none has a utilisation."""
        from .readout import governing
        return governing(self.findings)

    @cached_property
    def unchecked(self) -> tuple[Unchecked, ...]:
        """Each mode a component's domain declares that no requirement here names on the
        component, with the reason the coverage table gives (petra.readout.unchecked).
        Tooling, computed on first use."""
        from .readout import unchecked
        return unchecked(self)

    def render(self) -> str:
        """The design name and overall status, one status per entry, then
        verdict.render's scope, the governing strength and detailing checks, the
        obligation table with each finding's utilisation, the `excused` and `not checked`
        lines (petra.readout.edge), each counterexample and margin point with its
        finding's numbers, open items and footprint, then any warnings."""
        from .readout import edge, summary

        found = {id(o): f for o, f in zip(self.outcomes, self.findings)}
        status, *rest = render_verdict(self.verdict, self.outcomes, lambda o: found[id(o)].lines(), lambda o: found[id(o)].row(),
                                       tuple(summary(self.governing)), tuple(edge(self.findings, self.unchecked))).split("\n")
        statuses = ", ".join(f"{e.claim} {STATUS[type(e.verdict)]}" for e in self.entries)
        return "\n".join([f"{self.design}: {status}", f"entries    {statuses}", *rest, *(f"warning    {w}" for w in self.warnings)])

    def to_json(self) -> Mapping[str, Any]:
        """{"file": path, "design": name, "status": the overall status, "governing":
        {"strength", "detailing"}: each Governing.to_json or None, "verdicts":
        [verdict.verdict_json(e) and "obligations": the Finding.to_json of each of the
        entry's outcomes, for e in entries], "unchecked": the Unchecked.to_json of each
        mode not demanded}. `petra check --json` prints this, and petra/docs/api.md
        documents every key."""
        found = {id(o): f for o, f in zip(self.outcomes, self.findings)}
        return {
            "file": self.path,
            "design": self.design,
            "status": STATUS[type(self.verdict)],
            "governing": {category: None if g is None else g.to_json() for category, g in self.governing.items()},
            "verdicts": [{**verdict_json(e), "obligations": [found[id(o)].to_json() for o in e.outcomes]} for e in self.entries],
            "unchecked": [u.to_json() for u in self.unchecked],
        }


def lower_components(design: Design, registry: Registry) -> dict[str, Any]:
    """Component name -> typed model, by models.KINDS[component.kind]'s lowerer. Collects
    every lowerer's problems and raises one ComponentError, which the CLI reports as an
    input error (exit 3)."""
    lowered: dict[str, Any] = {}
    problems: list[str] = []
    for name, component in design.components.items():
        if component.kind not in domains.KINDS:
            problems.append(f"{component.span.path}:{component.span.line}:{component.span.col}: {name}: a {component.kind} is a part of a deck, "
                            "which `petra check` reads and this command does not yet")
            continue
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
    """`margins[i]` is the margin obligation of `elaborated[i]`; None when its
    requirement has no margin; or, for a claim with a margin whose margin obligation
    could not be built beside it, the reason, which _settle turns into an open item."""

    elaborated: tuple[Elaborated, ...]
    margins: tuple[Obligation | str | None, ...]
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
    kept = tuple(e for e in elaborated if e.requirement not in dropped)
    return _Prepared(kept, margin_obligations(design, lowered, kept, registry), waived, warnings)


def obligations_of(design: Design, registry: Registry) -> tuple[Elaborated, ...]:
    """What check_design elaborates the design to, one item per requirement and load
    case, each obligation with its validity rows: for a caller that needs the rows an
    outcome rested on, since an open item carries only its claim's statement."""
    return _prepare(design, registry).elaborated


def margin_obligations(design: Design, lowered: Mapping[str, Any], elaborated: tuple[Elaborated, ...], registry: Registry) -> tuple[Obligation | str | None, ...]:
    """For each claim requirement with a margin, its builder runs again on the requirement
    with the tightened criterion. Builders are pure and read only rel and bound, so the
    i-th obligation built for the tightened requirement is the margin obligation of the
    i-th obligation built for the claim. A pair counts only when
    verdict.margin_pair_fault accepts it (same model, goal type and hypotheses, so the
    same load case). Anything else gets the reason in place of a margin obligation, so a
    margin is never dropped silently."""
    margins: list[Obligation | str | None] = [None] * len(elaborated)
    positions: dict[Requirement, list[int]] = {}
    for i, item in enumerate(elaborated):
        if has_margin(item.requirement) and isinstance(item, Obligation):
            positions.setdefault(item.requirement, []).append(i)
    for req, where in positions.items():
        spec = domains.KINDS[design.components[req.subject[0]].kind]
        tight = dataclasses.replace(req, criterion=req.criterion.tightened())
        built = tuple(e for e in spec.builders[req.mode](tight, lowered[req.subject[0]], design, registry) or () if isinstance(e, Obligation))
        if len(built) != len(where):
            for i in where:
                margins[i] = f"the builder stated {len(built)} obligations at the tightened bound and {len(where)} for the claim"
            continue
        for i, margin in zip(where, built):
            margins[i] = margin_pair_fault(elaborated[i], margin) or margin
    return tuple(margins)


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
    decided: dict[str, Decision] = {}
    outcomes = tuple(_settle(item, margin, sources, sink, flagged, warnings, decided) for item, margin in zip(prepared.elaborated, prepared.margins))
    outcomes += tuple(Waived(req, premise) for req, premise in prepared.waived)
    book = build_premise_book(design, registry, outcomes)
    scope = _scope(design)
    return Report(design.name, path or design.path, assemble(outcomes, book, scope), entries(outcomes, book, scope), outcomes, tuple(warnings), design, registry)


def _settle(item: Elaborated, margin: Obligation | str | None, sources: tuple[EvidenceSource, ...], sink: EvidenceSink | None, flagged: Mapping[str, list[RegistryInconsistent]], warnings: list[str], decided: dict[str, Decision]) -> Outcome:
    """Settle one obligation: its model's validity rows first, then the claim, whose
    outcome _Close builds with the row proofs. An open claim gains the needs of every row
    not proved, so the report says all that stands between it and a verdict."""
    if isinstance(item, Gap):
        return open_from_gap(item)
    close = _Close(item, sources, sink, flagged, warnings, decided)
    outcome = _settle_claim(item, margin, close, sources, sink, flagged, warnings)
    if isinstance(outcome, Open) and outcome.statement == item.statement:
        named = {n.row for n in outcome.needs if isinstance(n, OutsideValidity)}
        extra = tuple(
            n for v, found in zip(item.validity, close.rows) if not isinstance(found, Theorem) and v.row.id not in named
            for n in _row_needs(v, found)
        )
        if extra:
            return dataclasses.replace(outcome, needs=tuple(dict.fromkeys(outcome.needs + extra)))
    return outcome


class _Close:
    """Builds an obligation's Discharged, Refuted or WithinMargin outcome with the proofs
    of its model's validity rows, each decided once over the box, or else the Open item
    that takes its place:

    - Proved, or proved and within its margin: kept when every row is proved over the
      box.
    - Refuted at a point: kept when every row is proved over the box or at that point
      (verdict.at_point). A counterexample where the model does not hold is none.
    - Otherwise open: a row refuted is OutsideValidity at the row's counterexample, or
      at the claim's for a refuted claim; a row undecided needs what would decide it. A
      claim proved within its margin keeps its point as the open item's margin point.

    A margin point without the claim's proof (an open item's) needs no row proofs."""

    def __init__(self, item: Obligation, sources: tuple[EvidenceSource, ...], sink: EvidenceSink | None, flagged: Mapping[str, list[RegistryInconsistent]], warnings: list[str], decided: dict[str, Decision]) -> None:
        self.item = item
        self._args = (sources, sink, flagged, warnings, decided)
        self.rows = tuple(_decide(v, *self._args) for v in item.validity)

    def __call__(self, kind: type, *fields: Any) -> Outcome:
        item = self.item
        if not item.validity or (kind is WithinMargin and fields[3] is None):
            return kind(item, *fields)
        if kind is Refuted:
            proofs: list[Theorem] = []
            for v, found in zip(item.validity, self.rows):
                if not isinstance(found, Theorem):
                    there = dataclasses.replace(v, statement=at_point(v.statement, fields[0]), describe=f"{v.describe}, at the counterexample")
                    found = _decide(there, *self._args)
                    if not isinstance(found, Theorem):
                        return Open(item.requirement, _row_needs(there, found, v.statement), statement=item.statement)
                proofs.append(found)
            return Refuted(item, *fields, validity=tuple(proofs))
        if all(isinstance(found, Theorem) for found in self.rows):
            return kind(item, *fields, validity=self.rows)
        needs = tuple(n for v, found in zip(item.validity, self.rows) if not isinstance(found, Theorem) for n in _row_needs(v, found))
        near = WithinMargin(item, *fields[:3]) if kind is WithinMargin else None
        return Open(item.requirement, needs, statement=item.statement, near=near)


Decision = Union[Theorem, Refutation, tuple[Need, ...]]
"""What the sources and the kernel made of one statement: a proof, a refutation, or what
would decide it."""


def _decide(item: Obligation, sources: tuple[EvidenceSource, ...], sink: EvidenceSink | None, flagged: Mapping[str, list[RegistryInconsistent]], warnings: list[str], decided: dict[str, Decision]) -> Decision:
    """A validity obligation's decision, once per statement per check: the obligations
    of one load case share their rows' statements."""
    digest = statement_hash(item.statement)
    if digest not in decided:
        inconsistent = [need for label in _labels(item.statement, LabelKind.REGISTRY) for need in flagged.get(_registry_entry(label), ())]
        if inconsistent:
            decided[digest] = tuple(dict.fromkeys(inconsistent))
        else:
            rejected: list[tuple[Rejection, str]] = []
            found = _first_accepted(item, sources, sink, rejected, warnings)
            decided[digest] = found[0] if found is not None else _unsettled(item, digest, rejected)
    return decided[digest]


def _row_needs(row: Obligation, found: Decision, wide: Statement | None = None) -> tuple[Need, ...]:
    """OutsideValidity for a refuted row, at the inputs its point varies over `wide`, the
    row over the whole box (by default the refuted statement itself; for a row narrowed to
    a counterexample, the row before narrowing, so the need names that point); else the
    needs."""
    if not isinstance(found, Refutation):
        return found
    ranges = {h.sym: h for h in (wide or found.statement).hyps if isinstance(h, RangeHyp)}
    point = tuple((sym, str(value)) for sym, value in found.point if sym in ranges and ranges[sym].lo != ranges[sym].hi)
    return (OutsideValidity(row.model.id, row.row.id, row.row.text, found.statement_hash, point),)


def _unsettled(item: Obligation, digest: str, rejected: list[tuple[Rejection, str]]) -> tuple[Need, ...]:
    if not rejected:
        return (NeedsCertificate(digest, _rule_of(item.statement), item.describe),)
    return tuple((CertificateTooWeak if isinstance(r.fault, TooWeak) else CertificateRejected)(r.statement_hash, r.rule, name, r.reason) for r, name in rejected)


def _settle_claim(item: Obligation, margin: Obligation | str | None, close: _Close, sources: tuple[EvidenceSource, ...], sink: EvidenceSink | None, flagged: Mapping[str, list[RegistryInconsistent]], warnings: list[str]) -> Outcome:
    statement = item.statement
    digest = statement_hash(statement)
    inconsistent = [need for label in _labels(statement, LabelKind.REGISTRY) for need in flagged.get(_registry_entry(label), ())]
    if inconsistent:
        return Open(item.requirement, tuple(dict.fromkeys(inconsistent)), statement=statement)
    rejected: list[tuple[Rejection, str]] = []
    found = _first_accepted(item, sources, sink, rejected, warnings)
    if found is not None and isinstance(found[0], Refutation):
        return close(Refuted, *found)
    near = None
    if isinstance(margin, str):
        warnings.append(f"{item.requirement.id}: its margin was not checked, because {margin}")
        return Open(item.requirement, (NoRuleForQuantity(item.requirement.id, f"its margin statement was not checked, because {margin}"),), statement=statement)
    if margin is not None:
        settled = _at_margin(item, margin, found, close, sources, sink, warnings)
        if not (isinstance(settled, WithinMargin) and settled.theorem is None):
            if settled is not None:
                return settled
        else:
            near = settled
    elif found is not None:
        return close(Discharged, *found)
    return Open(item.requirement, _unsettled(item, digest, rejected), tuple(r for r, _ in rejected), statement, near)


def _first_accepted(item: Obligation, sources: tuple[EvidenceSource, ...], sink: EvidenceSink | None, rejected: list[tuple[Rejection, str]], warnings: list[str]) -> tuple[Theorem | Refutation, str] | None:
    """The first result, with its source's name, that the kernel accepts for the
    obligation's statement from the evidence the sources offer in order. Each rejection
    is appended to `rejected`."""
    statement, digest = item.statement, statement_hash(item.statement)
    for source in sources:
        for evidence in _offered(source, statement, digest, item.requirement, warnings):
            result = check(statement, evidence)
            if isinstance(result, Rejection):
                rejected.append((result, source.name))
                continue
            _record(sink, statement, digest, evidence, source.name, item.requirement, warnings)
            return result, source.name
    return None


def _at_margin(item: Obligation, margin: Obligation, proved: tuple[Theorem, str] | None, close: _Close, sources: tuple[EvidenceSource, ...], sink: EvidenceSink | None, warnings: list[str]) -> Outcome | None:
    """Offer the margin statement to the sources and settle the claim obligation with
    what they return. Each candidate is tried against the claim first, at every
    expression it can name (_against_claim): a refutation there is a FAIL, and a proof
    there proves a claim nothing else proved. Then against the margin statement: a
    refutation is a point within the margin, and a proof is the margin proved.

    Returns Refuted; a WithinMargin, carrying the claim's theorem when the claim is
    proved (MARGINAL) and none when it is not (the open item's margin point); a
    Discharged carrying the margin obligation, with the margin statement's theorem when
    it was proved and without when no point within the margin was found (undecided); or
    None when the claim is unproved and no point within the margin was found."""
    statement, digest = margin.statement, statement_hash(margin.statement)
    claim, claim_digest = item.statement, statement_hash(item.statement)
    margin_theorem = None
    for source in sources:
        for evidence in _offered(source, statement, digest, margin.requirement, warnings):
            result, used = _against_claim(claim, evidence)
            if isinstance(result, Refutation):
                _record(sink, claim, claim_digest, used, source.name, item.requirement, warnings)
                return close(Refuted, result, source.name)
            if isinstance(result, Theorem) and proved is None:
                _record(sink, claim, claim_digest, used, source.name, item.requirement, warnings)
                proved = (result, source.name)
            result = check(statement, evidence)
            if isinstance(result, Refutation):
                _record(sink, statement, digest, evidence, source.name, margin.requirement, warnings)
                return close(WithinMargin, margin, result, source.name, None if proved is None else proved[0])
            if isinstance(result, Theorem) and margin_theorem is None:
                _record(sink, statement, digest, evidence, source.name, margin.requirement, warnings)
                margin_theorem = result
            if proved is not None and margin_theorem is not None:
                return close(Discharged, *proved, margin, margin_theorem)
    return None if proved is None else close(Discharged, *proved, margin, margin_theorem)


_MAX_WHICH = 256
"""The most expressions or bounds _against_claim tries a point witness at."""


def _against_claim(claim: Statement, evidence: Evidence) -> tuple[Theorem | Refutation | Rejection, Evidence]:
    """The kernel's result for `evidence` against the claim, with the evidence used. When
    it neither proves nor refutes, and its body names one expression or bound of the goal
    by an integer `which` (a point witness), the same body is tried naming each other one,
    from -1 up, until the kernel answers that there is no such index: a margin witness
    shows the margin statement fails at a point through one expression, and the claim may
    fail at that point through another. The first refutation found is returned.
    Untrusted search: every candidate is checked by the kernel."""
    first = check(claim, evidence)
    body = evidence.body
    if isinstance(first, (Theorem, Refutation)) or not dataclasses.is_dataclass(body) or type(getattr(body, "which", None)) is not int:
        return first, evidence
    for k in range(-1, _MAX_WHICH):
        if k == body.which:
            continue
        candidate = dataclasses.replace(evidence, body=dataclasses.replace(body, which=k))
        result = check(claim, candidate)
        if isinstance(result, Refutation):
            return result, candidate
        if k >= 0 and isinstance(result, Rejection) and not isinstance(result.fault, TooWeak):
            break
    return first, evidence


def _record(sink: EvidenceSink | None, statement: Statement, digest: str, evidence: Evidence, source: str, requirement: Requirement, warnings: list[str]) -> None:
    if sink is None:
        return
    try:
        sink.record(statement, digest, evidence, source)
    except Exception as exc:
        warnings.append(f"could not record the certificate for {requirement.id}: {type(exc).__name__}: {exc}")


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
    return ScopeParam(param_label(design.name, p.name), p.name, p.range.value, si_unit(p.range.dim))


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
        elif isinstance(outcome, (Discharged, Refuted, WithinMargin)):
            premises.append(outcome.obligation.model.premise())
            result = outcome.theorem if isinstance(outcome, Discharged) else outcome.refutation
            for statement in (result.statement, *(v.statement for v in outcome.obligation.validity)):
                premises += [_registry_premise(registry, label) for label in _labels(statement, LabelKind.REGISTRY)]
            if isinstance(outcome, WithinMargin) and outcome.theorem is not None:
                premises += [_registry_premise(registry, label) for label in _labels(outcome.theorem.statement, LabelKind.REGISTRY)]
        elif isinstance(outcome, Open) and outcome.near is not None:
            premises.append(outcome.near.margin.model.premise())
            premises += [_registry_premise(registry, label) for label in _labels(outcome.near.refutation.statement, LabelKind.REGISTRY)]
    for inp in signed_inputs(design, lower_components(design, registry)):
        premises += _input_premises(design, inp)
    for record in design.tests.values():
        statement = f"{record.name} on {'.'.join(record.subject)}: {record.trials} trials, {record.failures} failures at {quantity_text(record.level)}"
        for field, count in (("trials", record.trials), ("failures", record.failures)):
            label = input_label(design.name, f"tests.{record.name}.{field}")
            premises.append(Premise(label, Tag.MEASURED, record.signature.owner, record.signature.source, statement, Interval(Q(count), Q(count)), "1"))
    params = [_scope_param(design, p) for p in design.params.values()]
    return PremiseBook(premises, params, ())


def _registry_premise(registry: Registry, label: str) -> Premise:
    key = label[len("reg:"):]
    fact = registry.fact(key)
    version = registry.entry_of(key).provenance.version
    if isinstance(fact, Constant):
        return Premise(Label(label), fact.tag, fact.owner, fact.source, fact.statement, fact.value, fact.unit, version)
    statement = f"{key} {interval_text(fact.value)} {fact.unit}, {fact.conditions}"
    return Premise(Label(label), fact.tag, fact.owner, fact.standard, statement, fact.value, fact.unit, version)


_INPUT_TAG = {InputKind.ASSUMED: Tag.ASSUMED, InputKind.MEASURED: Tag.MEASURED}


def _input_premises(design: Design, inp: Input) -> list[Premise]:
    def premise(name: str, q: Quantity, what: str) -> Premise:
        unit = si_unit(q.dim)
        text = f"{what} {quantity_text(q)}"
        return Premise(input_label(design.name, name), _INPUT_TAG[inp.kind], inp.signature.owner, inp.signature.source, text, q.value, unit)

    found = [premise(inp.name, inp.range, f"{inp.name} in")]
    if inp.mean is not None:
        found.append(premise(f"{inp.name}.mean", inp.mean, f"the mean of {inp.name} is"))
    return found


def signed_inputs(design: Design, lowered: Mapping[str, Any]) -> Iterator[Input]:
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


# --- explain ------------------------------------------------------------------------------


def explain(design: Design, registry: Registry) -> str:
    """Elaborate without checking and pretty-print each statement in mathematical notation
    with every hypothesis label, so a reviewer can audit the trusted front end and the
    elaborators against the source file. `petra explain FILE` prints this.

    Goals print generically, field by field, with expressions in infix, so a new rule's
    goal prints without a change here."""
    prepared = _prepare(design, registry)
    obligations = sum(isinstance(e, Obligation) for e in prepared.elaborated)
    lines = [
        f"design {design.name} ({design.path})",
        f"{obligations} statements, {len(prepared.elaborated) - obligations} gaps, {len(prepared.waived)} waived",
    ]
    for item, margin in zip(prepared.elaborated, prepared.margins):
        lines.append("")
        if isinstance(item, Gap):
            lines.append(f"gap {item.requirement.id}")
            lines += [f"  needs  {describe_need(n)}" for n in item.needs]
            continue
        lines += _statement_lines(f"obligation {item.requirement.id}", item)
        for v in item.validity:
            lines += _statement_lines(f"  validity {v.row.id}: {v.row.text}", v, "  ")
        if isinstance(margin, Obligation):
            moved = readable_text(margin.requirement.criterion.bound)
            lines += _statement_lines(f"  margin obligation, the bound moved to {moved}", margin, "  ")
        elif margin is not None:
            lines.append(f"  margin not checked: {margin}")
    for req, premise in prepared.waived:
        lines += ["", f"waived {req.id}", f"  by     {premise.owner}: {premise.statement}"]
    lines += [f"warning {w}" for w in prepared.warnings]
    return "\n".join(lines)


def _statement_lines(head: str, item: Obligation, pad: str = "") -> list[str]:
    statement = item.statement
    lines = [
        head,
        f"{pad}  means  {item.describe}",
        f"{pad}  model  {item.model.premise().label}  {item.model.form}",
        f"{pad}  rule   {_rule_of(statement)}  {statement_hash(statement)}",
        f"{pad}  for all",
    ]
    width = max((len(h.sym) for h in statement.hyps), default=0)
    for h in statement.hyps:
        if isinstance(h, RangeHyp):
            lines.append(f"{pad}    {h.sym:<{width}}  in {interval_text(Interval(h.lo, h.hi))}   {h.label}")
        else:
            lines.append(f"{pad}    {h.sym:<{width}}  := the quantity below (its range is proved by a lemma in the evidence)")
            lines += [pad + line for line in _term_lines("definition", h.definition, 3)]
    return lines + [pad + line for line in _term_lines("goal", statement.goal, 1)]


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


__all__ = ["ComponentError", "EvidenceSink", "EvidenceSource", "Report", "build_premise_book", "check_design", "elaborate", "explain", "lower_components", "margin_obligations", "signed_inputs"]
