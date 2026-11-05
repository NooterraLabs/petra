"""Syntax tree -> Design IR. The parse boundary: every check that makes the IR
trustworthy happens here and nowhere downstream.

Checks here (design level; the language knows no domain):
- every component kind is a key of models.KINDS, so a typo is an input error naming the
  registered kinds;
- component, load, tests, param and claim names are unique; "coverage" is reserved as a
  claim name because the report uses it for the requirements no claim made;
- every load entry, tests record and claim path starts with a declared component; every
  `under` and `from` names a declared load or tests block; a ParamRef names a param;
- every quantity parses to an exact Quantity (units.parse_quantity); every bound outside
  a family carries a signature;
- every waiver mode is a key of models.MODES;
- probability-claim method and event agree (RangeMean with Exceeds, FromTests with
  FailsAt).
All problems in one file are collected and raised together as a LoweringError.

Also checked here, because they are design-level facts rather than domain physics: the
design block names one owner and at most one environment, which must be a key of
registry.environments; a range's ends share a dimension and lo <= hi; a mean shares its
range's dimension and lies inside it; the ambient is a temperature; every signature,
owner and reason is non-empty; a load case gives each (target, field) once; a tests
record has at least one trial and no more failures than trials; a probability lies in
[0, 1] and a confidence strictly between 0 and 1; no declared name is a DECLS keyword.
The probability-claim pairing holds by construction: the parser has one rule per form.

Checks in the owning domain's lowerer (models.base.DomainSpec.kinds), raised as
ComponentError and reported the same way: attribute names and shapes, local name
resolution (nodes, elements, ports), registry references of the right kind (LoLa never
substitutes a default part), unit dimensions per slot, load fields and claim qois.
"""
from __future__ import annotations

from fractions import Fraction
from types import MappingProxyType
from typing import Callable, Iterable

from .. import models
from ..ir import (
    Arg,
    Attr,
    Bound,
    Claim,
    Component,
    Design,
    Exceeds,
    FailsAt,
    Fixed,
    FromTests,
    Input,
    InputKind,
    LoadCase,
    LoadEntry,
    Param,
    ParamRef,
    ProbabilityClaim,
    Punct,
    QoiRef,
    RangeMean,
    Ref,
    Rel,
    Signature,
    Span,
    Tests,
    Text,
    Vec,
    Waiver,
)
from ..kernel import Interval
from ..units import DIMENSIONLESS, TEMPERATURE, Dim, Quantity, UnitError, parse_quantity, require_dim
from ..verdict import COVERAGE_ENTRY
from .lexer import Token
from .parser import DECLS
from .syntax import File, Node


class LoweringError(ValueError):
    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


RESERVED_CLAIMS: frozenset[str] = frozenset({COVERAGE_ENTRY})

_CLAIM_HEADS = ("claim", "prob_exceeds", "prob_fails")

Located = Token | Node


def lower(file: File, registry: object) -> Design:
    return _Lowering(file, registry).design()


class _Lowering:
    """One pass over one file. Names are indexed before anything is lowered, so a
    declaration that fails to lower does not also make every reference to it fail."""

    def __init__(self, file: File, registry: object) -> None:
        self.file = file
        self.path = file.path
        self.registry = registry
        self.problems: list[tuple[int, int, str]] = []

    def problem(self, at: Located, message: str) -> None:
        self.problems.append((at.line, at.col, message))

    def span(self, at: Located) -> Span:
        return Span(self.path, at.line, at.col)

    # --- the design -------------------------------------------------------------

    def design(self) -> Design:
        decls = self.file.decls
        by_head = {head: [d for d in decls if d.head == head] for head in {d.head for d in decls}}
        self.params_by_name = self.index(by_head.get("param", ()), "param", lambda n: n.args[0])
        self.components_by_name = self.index(by_head.get("component", ()), "component", lambda n: n.args[1])
        self.loads_by_name = self.index(by_head.get("load", ()), "load case", lambda n: n.args[0])
        self.tests_by_name = self.index(by_head.get("tests", ()), "tests block", lambda n: n.args[0])
        claim_nodes = [d for d in decls if d.head in _CLAIM_HEADS]
        self.index(claim_nodes, "claim", lambda n: n.args[0])
        for node in claim_nodes:
            if node.args[0].text in RESERVED_CLAIMS:
                self.problem(node.args[0], f"claim name '{node.args[0].text}' is reserved for the report entry of requirements no claim made")

        name, owner, environment = self.header(by_head.get("design", ()))
        params = self.lowered(self.params_by_name, self.param)
        ambient = self.ambient(by_head.get("ambient", ()), params)
        components = self.lowered(self.components_by_name, self.component)
        loads = self.lowered(self.loads_by_name, self.load)
        tests = self.lowered(self.tests_by_name, self.tests)
        claims = tuple(self.claim(n) for n in claim_nodes if n.head == "claim")
        probability_claims = tuple(self.probability_claim(n) for n in claim_nodes if n.head != "claim")
        waivers = tuple(self.waiver(n) for n in by_head.get("waive", ()))

        if self.problems:
            raise LoweringError(tuple(f"{self.path}:{line}:{col}: {message}" for line, col, message in sorted(self.problems)))
        return Design(
            name=name,
            owner=owner,
            path=self.path,
            environment=environment,
            ambient=ambient,
            components=MappingProxyType(components),
            loads=MappingProxyType(loads),
            claims=claims,
            probability_claims=probability_claims,
            tests=MappingProxyType(tests),
            waivers=waivers,
            params=MappingProxyType(params),
        )

    def index(self, nodes: Iterable[Node], what: str, name_of: Callable[[Node], Token]) -> dict[str, Node]:
        table: dict[str, Node] = {}
        for node in nodes:
            tok = name_of(node)
            if tok.text in DECLS:
                self.problem(tok, f"{what} name '{tok.text}' is a design-level keyword")
            elif tok.text in table:
                self.problem(tok, f"{what} '{tok.text}' is declared twice (first at line {name_of(table[tok.text]).line})")
            else:
                table[tok.text] = node
        return table

    @staticmethod
    def lowered(table: dict[str, Node], lower_one: Callable[[Node], object]) -> dict:
        out = {}
        for name, node in table.items():
            value = lower_one(node)
            if value is not None:
                out[name] = value
        return out

    def header(self, nodes: list[Node]) -> tuple[str, str, str | None]:
        if not nodes:
            self.problems.append((1, 1, 'no design block: add design "<name>" { owner "<who>" }'))
            return "", "", None
        for extra in nodes[1:]:
            self.problem(extra, "a file declares one design; this is a second design block")
        name_tok, items = nodes[0].args
        self.nonempty(name_tok, "the design name")
        owners = [i for i in items if i.head == "owner"]
        envs = [i for i in items if i.head == "environment"]
        if not owners:
            self.problem(nodes[0], f"design '{name_tok.text}' names no owner")
        for extra in owners[1:] + envs[1:]:
            self.problem(extra, f"the design's {extra.head} is given twice")
        owner = owners[0].args[0].text if owners else ""
        if owners:
            self.nonempty(owners[0].args[0], "the design owner")
        environment = envs[0].args[0].text if envs else None
        known = self.registry.environments
        if environment is not None and environment not in known:
            self.problem(envs[0].args[0], f"unknown environment '{environment}'; the registry holds: {', '.join(sorted(known))}")
        return name_tok.text, owner, environment

    def nonempty(self, tok: Token, what: str) -> bool:
        if tok.text.strip():
            return True
        self.problem(tok, f"{what} is empty")
        return False

    # --- quantities, ranges and signed bounds ------------------------------------

    def qty(self, node: Node) -> Quantity | None:
        number, unit = node.args
        try:
            return parse_quantity(number.text, unit.text if unit is not None else None)
        except UnitError as e:
            self.problem(unit or number, str(e))
            return None

    def dimensioned(self, q: Quantity | None, dim: Dim, what: str, at: Located) -> Quantity | None:
        if q is None:
            return None
        try:
            return require_dim(q, dim, what)
        except UnitError as e:
            self.problem(at, str(e))
            return None

    def range(self, node: Node) -> Quantity | None:
        lo_node, hi_node = node.args
        lo, hi = self.qty(lo_node), self.qty(hi_node)
        if lo is None or hi is None:
            return None
        if self.dimensioned(hi, lo.dim, "the range's upper end has the wrong dimension", hi_node) is None:
            return None
        if lo.value.lo > hi.value.lo:
            self.problem(node, f"malformed range: the lower end {lo_node.args[0].text} is above the upper end {hi_node.args[0].text}")
            return None
        return Quantity(Interval(lo.value.lo, hi.value.lo), lo.dim)

    def signature(self, node: Node) -> tuple[Signature, InputKind] | None:
        kind, owner, source = node.args
        owner_ok = self.nonempty(owner, "the signer")
        source_ok = self.nonempty(source, "the signature's source")
        if not (owner_ok and source_ok):
            return None
        return Signature(owner.text, source.text), InputKind.MEASURED if kind.text == "measured" else InputKind.ASSUMED

    def signed_range(self, node: Node, fallback: Node | None, what: str):
        """(range, signature, kind, span, mean) for a `bound` node, or None after
        recording every problem. The bound's own signature wins over `fallback`, the
        enclosing block's."""
        rng = self.range(node.args[0])
        sig_node = node.props["sig"] or fallback
        signed = None
        if sig_node is None:
            self.problem(node, f"{what}: input bound without a signature; add 'signed \"<owner>\" source \"<where>\"' (LoLa never invents an input bound)")
        else:
            signed = self.signature(sig_node)
        mean = None
        mean_node = node.props["mean"]
        if mean_node is not None:
            mean = self.qty(mean_node)
            if mean is not None and rng is not None:
                mean = self.dimensioned(mean, rng.dim, f"{what}: the mean has the wrong dimension", mean_node)
                if mean is not None and not rng.value.lo <= mean.value.lo <= rng.value.hi:
                    self.problem(mean_node, f"{what}: the mean lies outside its range")
                    mean = None
            if mean is None:
                return None
        if rng is None or signed is None:
            return None
        return rng, signed[0], signed[1], self.span(node), mean

    def paramref(self, node: Node) -> ParamRef | None:
        name = node.args[0]
        if name.text not in self.params_by_name:
            self.problem(name, f"unknown param '{name.text}'")
            return None
        return ParamRef(name.text)

    def input_or_param(self, node: Node, fallback: Node | None, name: str) -> Input | ParamRef | None:
        if node.head == "paramref":
            return self.paramref(node)
        parts = self.signed_range(node, fallback, name)
        if parts is None:
            return None
        rng, signature, kind, span, mean = parts
        return Input(name, rng, signature, kind, span, mean)

    # --- declarations ------------------------------------------------------------

    def param(self, node: Node) -> Param | None:
        name, rng = node.args
        q = self.range(rng)
        return None if q is None else Param(name.text, q, self.span(node))

    def ambient(self, nodes: list[Node], params: dict[str, Param]) -> Input | ParamRef | None:
        for extra in nodes[1:]:
            self.problem(extra, "the ambient is declared twice")
        if not nodes:
            return None
        bound = nodes[0].args[0]
        value = self.input_or_param(bound, None, "ambient")
        if isinstance(value, Input):
            self.dimensioned(value.range, TEMPERATURE, "ambient", bound)
        elif isinstance(value, ParamRef) and value.name in params:
            self.dimensioned(params[value.name].range, TEMPERATURE, f"ambient (param {value.name})", bound)
        return value

    def component(self, node: Node) -> Component:
        kind, name, attrs = node.args
        if kind.text not in models.KINDS:
            self.problem(kind, f"unknown component kind '{kind.text}'; registered kinds: {', '.join(sorted(models.KINDS))}")
        lowered = []
        for attr in attrs:
            key, args = attr.args
            what = f"{name.text}.{key.text}"
            typed = (self.arg(a, what) for a in args)
            lowered.append(Attr(key.text, tuple(a for a in typed if a is not None), self.span(attr)))
        return Component(kind.text, name.text, tuple(lowered), self.span(node))

    def arg(self, node: Node, what: str) -> Arg | None:
        match node.head:
            case "qty":
                q = self.qty(node)
                return None if q is None else Fixed(q)
            case "bound":
                parts = self.signed_range(node, None, what)
                if parts is None:
                    return None
                rng, signature, kind, span, mean = parts
                return Bound(rng, signature, kind, span, mean)
            case "paramref":
                return self.paramref(node)
            case "tuple":
                items = [self.qty(q) for q in node.args]
                return None if None in items else Vec(tuple(items))
            case "ref":
                return Ref(tuple(t.text for t in node.args))
            case "text":
                return Text(node.args[0].text)
            case "punct":
                return Punct(node.args[0].text)
        raise AssertionError(f"parser produced an unknown argument node {node.head!r}")

    def rooted(self, path: tuple[str, ...], at: Located, what: str) -> None:
        if not path:
            self.problem(at, f"{what}: the path must start with a declared component, as in frame.collapse_factor")
        elif path[0] not in self.components_by_name:
            self.problem(at, f"{what}: '{path[0]}' is not a declared component")

    def load(self, node: Node) -> LoadCase:
        name, entries, sig = node.args
        lowered, seen = [], set()
        for entry in entries:
            target, field, value = entry.args
            path = tuple(t.text for t in target.args)
            self.rooted(path, target, f"load {name.text}")
            if (path, field.text) in seen:
                self.problem(entry, f"load {name.text}: {'.'.join(path)} {field.text} is given twice")
            seen.add((path, field.text))
            v = self.input_or_param(value, sig, f"{name.text}.{'.'.join(path)}.{field.text}")
            if v is not None:
                lowered.append(LoadEntry(path, field.text, v))
        return LoadCase(name.text, tuple(lowered), self.span(node))

    def tests(self, node: Node) -> Tests | None:
        name, subject, trials, failures, level_node, sig, block_sig = node.args
        path = tuple(t.text for t in subject.args)
        self.rooted(path, subject, f"tests {name.text}")
        if trials < 1:
            self.problem(node, f"tests {name.text}: needs at least one trial")
        if failures > trials:
            self.problem(node, f"tests {name.text}: {failures} failures exceed {trials} trials")
        if sig is not None and block_sig is not None:
            self.problem(block_sig, f"tests {name.text} is signed twice")
        sig_node = sig or block_sig
        signed = None
        if sig_node is None:
            self.problem(node, f"tests {name.text} has no signature; add 'measured \"<owner>\" source \"<where>\"'")
        else:
            signed = self.signature(sig_node)
        level = self.qty(level_node)
        if signed is None or level is None:
            return None
        return Tests(name.text, path, trials, failures, level, signed[0], self.span(node))

    def claim(self, node: Node) -> Claim:
        name, qoi_node, rel, bound_node, margin_node, under = node.args
        qoi = self.qoi(qoi_node, f"claim {name.text}")
        bound = self.qty(bound_node)
        margin = None if margin_node is None else self.margin(margin_node, bound, f"claim {name.text}")
        for load in under:
            self.declared_load(load, f"claim {name.text}")
        return Claim(name.text, qoi, Rel(rel.text), bound, tuple(t.text for t in under), None, self.span(node), margin)

    def margin(self, node: Node, bound: Quantity | None, what: str) -> Quantity | None:
        """A positive quantity in the bound's dimension. Temperatures are degC with no
        offset, so a margin in degC is a difference, as it should be."""
        q = self.qty(node)
        if q is None or bound is None:
            return None
        if bound.dim == DIMENSIONLESS and q.dim != DIMENSIONLESS:
            number, unit = node.args
            self.problem(node, f"{what}: the margin must have the bound's dimension, but the bound is a plain number and the margin is {number.text} {unit.text}; if the quantity has a unit, the bound needs a unit too")
            return None
        if self.dimensioned(q, bound.dim, f"{what}: the margin must have the bound's dimension", node) is None:
            return None
        if q.value.lo <= 0:
            self.problem(node, f"{what}: a margin must be positive, got {node.args[0].text}")
            return None
        return q

    def probability_claim(self, node: Node) -> ProbabilityClaim:
        name = node.args[0]
        what = f"claim {name.text}"
        if node.head == "prob_exceeds":
            _, qoi_node, threshold_node, p_tok, load = node.args
            qoi, threshold = self.qoi(qoi_node, what), self.qty(threshold_node)
            self.declared_load(load, what)
            event, method = Exceeds(qoi, threshold, load.text), RangeMean()
        else:
            _, subject, level_node, p_tok, confidence_node, tests = node.args
            path = tuple(t.text for t in subject.args)
            self.rooted(path, subject, what)
            if tests.text not in self.tests_by_name:
                self.problem(tests, f"{what}: unknown tests block '{tests.text}'")
            event, method = FailsAt(path, self.qty(level_node)), FromTests(tests.text, self.confidence(confidence_node, what))
        return ProbabilityClaim(name.text, event, self.probability(p_tok, what), method, self.span(node))

    def qoi(self, node: Node, what: str) -> QoiRef:
        path_toks, name = node.args
        path = tuple(t.text for t in path_toks)
        self.rooted(path, node, what)
        return QoiRef(path, name.text)

    def declared_load(self, tok: Token, what: str) -> None:
        if tok.text not in self.loads_by_name:
            self.problem(tok, f"{what}: unknown load case '{tok.text}'")

    def probability(self, tok: Token, what: str) -> Fraction | None:
        p = self.qty(Node("qty", (tok, None), {}, tok.line, tok.col))
        if p is not None and not 0 <= p.value.lo <= 1:
            self.problem(tok, f"{what}: a probability lies in [0, 1], not {tok.text}")
            return None
        return None if p is None else p.value.lo

    def confidence(self, node: Node, what: str) -> Fraction | None:
        c = self.dimensioned(self.qty(node), DIMENSIONLESS, f"{what}: confidence", node)
        if c is not None and not 0 < c.value.lo < 1:
            self.problem(node, f"{what}: a confidence lies strictly between 0 and 100 %")
            return None
        return None if c is None else c.value.lo

    def waiver(self, node: Node) -> Waiver:
        mode, subject, owner, reason = node.args
        mode_id = ".".join(t.text for t in mode.args)
        if mode_id not in models.MODES:
            self.problem(mode, f"unknown failure mode '{mode_id}'; known modes: {', '.join(sorted(models.MODES))}")
        self.nonempty(owner, "the waiver's owner")
        self.nonempty(reason, "the waiver's reason")
        return Waiver(mode_id, tuple(t.text for t in subject.args), owner.text, reason.text, self.span(node))
