"""Premises and the footprint. Trusted, outside the kernel.

The kernel only sees opaque labels on RangeHyps. This module gives each label its
meaning: a tag, an owner, a source, and (for numeric premises) the range the premise
asserts. A footprint is computed from kernel results, never written by hand:

    footprint(verdict) = premises named by the labels of the theorems it used
                       + the validated_model premise of every elaborator involved
                       + the coverage-table premise
                       + every waiver premise

Labels are namespaced strings so a reader can tell them apart in JSON:
    "reg:<entry>.<property>"      registry constant or rating        (sanctioned, measured)
    "in:<design>.<load>.<field>"  signed input bound                 (assumed)
    "par:<design>.<param>"        family or scope parameter          (scope, not a premise)
    "dsg:<design>.<path>"         a value the designer drew          (the design itself)
    "model:<id>@<src-hash>"       elaborator                         (validated_model)
    "cov:<table-hash>"            coverage rule table                (judged)
    "waive:<design>.<mode>.<subject>"                                (judged)
    "cert:<statement-hash>"       kernel-checked certificate         (certified)
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping, NewType, Union

from .kernel import Interval

Label = NewType("Label", str)


def registry_label(entry: str, prop: str) -> Label:
    return Label(f"reg:{entry}.{prop}")


def constant_label(name: str) -> Label:
    return Label(f"reg:const.{name}")


def input_label(design: str, name: str) -> Label:
    return Label(f"in:{design}.{name}")


def param_label(design: str, name: str) -> Label:
    return Label(f"par:{design}.{name}")


def design_label(design: str, name: str) -> Label:
    return Label(f"dsg:{design}.{name}")


class Tag(Enum):
    PROVED = "proved"
    CERTIFIED = "certified"
    SANCTIONED = "sanctioned"
    MEASURED = "measured"
    VALIDATED_MODEL = "validated_model"
    ASSUMED = "assumed"
    JUDGED = "judged"


class LabelKind(Enum):
    REGISTRY = "reg"
    INPUT = "in"
    PARAM = "par"
    DESIGN = "dsg"
    MODEL = "model"
    COVERAGE = "cov"
    WAIVER = "waive"
    CERT = "cert"


ALLOWED_TAGS: Mapping[LabelKind, frozenset[Tag]] = {
    LabelKind.REGISTRY: frozenset({Tag.SANCTIONED, Tag.MEASURED, Tag.JUDGED}),
    LabelKind.INPUT: frozenset({Tag.ASSUMED, Tag.MEASURED}),
    LabelKind.MODEL: frozenset({Tag.VALIDATED_MODEL}),
    LabelKind.COVERAGE: frozenset({Tag.JUDGED}),
    LabelKind.WAIVER: frozenset({Tag.JUDGED}),
    LabelKind.CERT: frozenset({Tag.CERTIFIED}),
}
"""A premise whose tag is not allowed for its label kind fails to construct, so an input
bound can never be tagged sanctioned and a model can never be tagged assumed."""


def label_kind(label: str) -> LabelKind:
    """Parse the namespace prefix. Raises ValueError for an unknown prefix or an empty
    name after it."""
    prefix, sep, name = label.partition(":")
    if not sep or not name:
        raise ValueError(f"label {label!r} has no namespace prefix")
    return LabelKind(prefix)


@dataclass(frozen=True)
class Premise:
    """One non-proved fact. `range` is set for numeric premises and must lie inside the
    range of every RangeHyp that carries this label (checked by `PremiseBook.resolve`), so
    a theorem covers every value the premise admits. Tag PROVED is never a Premise: proved facts are the kernel's own and stay out of the
    footprint. `version` is set on a registry premise only: the version of the registry entry
    the value came from (registry.model.Provenance), which the label does not carry."""

    label: Label
    tag: Tag
    owner: str
    source: str
    statement: str
    range: Interval | None = None
    unit: str | None = None
    version: int | None = None

    def __post_init__(self) -> None:
        if self.tag is Tag.PROVED:
            raise ValueError(f"{self.label}: a proved fact is the kernel's own and is never a premise")
        allowed = ALLOWED_TAGS.get(label_kind(self.label), frozenset())
        if self.tag not in allowed:
            raise ValueError(f"{self.label}: tag {self.tag.value} does not fit its label namespace")
        if not self.owner or not self.source:
            raise ValueError(f"{self.label}: a premise needs an owner and a source")
        if self.version is not None and (label_kind(self.label) is not LabelKind.REGISTRY or self.version < 1):
            raise ValueError(f"{self.label}: only a registry premise has a version, and a version is at least 1")


@dataclass(frozen=True)
class ScopeParam:
    """A family or scope parameter: a quantity the PASS holds over, not a fact assumed."""

    label: Label
    name: str
    range: Interval
    unit: str

    def __post_init__(self) -> None:
        if label_kind(self.label) is not LabelKind.PARAM:
            raise ValueError(f"{self.label}: a scope parameter label starts with par:")


@dataclass(frozen=True)
class DesignValue:
    """A value the designer drew (a length, a node coordinate, a chosen size). It is what
    the verdict is about, so it is neither a premise nor a scope parameter. It is a
    hypothesis only so concrete statements and family statements share one shape."""

    label: Label
    value: Interval
    unit: str

    def __post_init__(self) -> None:
        if label_kind(self.label) is not LabelKind.DESIGN:
            raise ValueError(f"{self.label}: a design value label starts with dsg:")


@dataclass(frozen=True)
class Footprint:
    """Non-empty, sorted by label. Every Petra verdict rests on at least one elaborator and
    the coverage table, so an empty footprint is a construction error."""

    premises: tuple[Premise, ...]

    def __post_init__(self) -> None:
        if not self.premises:
            raise ValueError("a footprint is never empty")
        if not all(isinstance(p, Premise) for p in self.premises):
            raise TypeError("a footprint holds only Premise values")
        labels = [p.label for p in self.premises]
        if labels != sorted(set(labels)):
            raise ValueError("footprint premises must be sorted by label, with no label twice")

    @property
    def labels(self) -> frozenset[str]:
        return frozenset(p.label for p in self.premises)

    def by_tag(self) -> Mapping[Tag, tuple[Premise, ...]]:
        """Non-empty groups in Tag order, each sorted by label."""
        groups = {tag: tuple(p for p in self.premises if p.tag is tag) for tag in Tag}
        return {tag: group for tag, group in groups.items() if group}


Entry = Union[Premise, ScopeParam, DesignValue]


class PremiseBook:
    """Label -> Premise or ScopeParam for one design check. Built once by the pipeline from
    the registry, the design's signed inputs, the elaborators used, the coverage table and
    the waivers. Read-only afterwards. The same entry may be given twice; two different
    entries for one label are refused."""

    def __init__(self, premises: Iterable[Premise], params: Iterable[ScopeParam], design_values: Iterable[DesignValue]) -> None:
        entries: dict[str, Entry] = {}
        for entry in (*premises, *params, *design_values):
            if not isinstance(entry, (Premise, ScopeParam, DesignValue)):
                raise TypeError(f"{entry!r} is not a premise, scope parameter or design value")
            if entries.setdefault(entry.label, entry) != entry:
                raise ValueError(f"{entry.label} names two different entries")
        self._entries: Mapping[str, Entry] = MappingProxyType(entries)

    def resolve(self, label: str, hyp_range: Interval) -> Premise | ScopeParam | DesignValue:
        """Return the entry for a RangeHyp label. Raises UnresolvedLabel if missing, and
        RangeMismatch if a premise's range is not a subset of the hyp range (a statement
        that assumes a wider range than the premise grants is fine; a narrower one would
        assume more than the premise says). A premise with no range cannot back a
        RangeHyp, so it is a RangeMismatch too."""
        entry = self._entries.get(label)
        if entry is None:
            raise UnresolvedLabel(label)
        granted = entry.value if isinstance(entry, DesignValue) else entry.range
        if granted is None:
            raise RangeMismatch(f"{label} grants no range, so it cannot back a hypothesis")
        if not (hyp_range.lo <= granted.lo and granted.hi <= hyp_range.hi):
            raise RangeMismatch(
                f"{label} grants [{granted.lo}, {granted.hi}] but the statement assumes only [{hyp_range.lo}, {hyp_range.hi}]"
            )
        return entry

    def footprint(self, labels: Iterable[str]) -> Footprint:
        """The premises named by `labels`. Scope parameters and design values are not
        premises, so their labels are skipped. Raises UnresolvedLabel for a missing one."""
        premises = []
        for label in set(labels):
            if label_kind(label) in (LabelKind.PARAM, LabelKind.DESIGN):
                continue
            entry = self._entries.get(label)
            if entry is None:
                raise UnresolvedLabel(label)
            premises.append(entry)
        return Footprint(tuple(sorted(premises, key=lambda p: p.label)))


class UnresolvedLabel(LookupError):
    pass


class RangeMismatch(ValueError):
    pass
