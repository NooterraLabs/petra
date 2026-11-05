"""LoLa's trusted kernel. Mathematics only; standard library only.

The kernel knows rationals, intervals, expressions, exact matrices, and six certificate
rules over them. It does not know what a truss, a wire or a bolt is. Every physical
meaning arrives from an elaborator in lola/models, which is trusted separately and is
named in every footprint as a validated_model premise.

Public surface. Code outside lola/kernel imports this package and the registered rule
modules (lola.kernel.rules.r1_linear and so on), which define each rule's goal, evidence
and lemma types. Every other kernel module is internal, and tests/test_structure.py
fails if outside code imports one:

    check(statement, evidence) -> Theorem | Refutation | Rejection
    is_issued(result)                  True only for a result check returned
    Instance                           proof evidence for any goal: a family theorem's instance
    forget_families()                  empty check's memo of the family theorems Instances use
    RULES and the tables derived from it, and the Goal and evidence aliases
    term constructors (terms.py) and shared evidence pieces (evidence.py)
    encode_*/decode_*/statement_hash   the JSON contract a Lean kernel will share
    enclose(expr, box)                 interval evaluation, for solvers and the deck checker
"""
from __future__ import annotations

from .check import CheckResult, Refutation, Rejection, Theorem, check, forget_families, is_issued
from .codec import (
    FORMAT,
    TAGS,
    DecodeError,
    canonical_text,
    decode_evidence,
    decode_statement,
    encode_evidence,
    encode_statement,
    evidence_hash,
    statement_hash,
)
from .evaluate import Box, NotAffine, affine_coefficients, enclose, free_syms
from .evidence import DefinedRange, Evidence, Instance, Leaf, Partition, Point, Split, Vector
from .interval import Interval, KernelArithmeticError, Q, i_ln, i_pi, i_sqrt, parse_q
from .rules import (
    GOAL_RULE,
    LEMMAS,
    MODULE_OF,
    PROOF_RULE,
    REFUTATION_RULE,
    RULES,
    Fault,
    Goal,
    Invalid,
    Lemma,
    LemmaEvidence,
    ProofEvidence,
    QuantityDef,
    RefutationEvidence,
    RuleSpec,
    TooWeak,
)
from .terms import (
    Abs,
    Add,
    Const,
    DefinedHyp,
    Div,
    Exp,
    Expr,
    Hyp,
    Ln,
    Matrix,
    Max,
    Min,
    Mul,
    Neg,
    Pi,
    PowInt,
    RangeHyp,
    Sqrt,
    Statement,
    Sym,
)

KERNEL_LINE_BUDGET = 1500
"""tests/test_kernel_budget.py counts non-blank, non-comment, non-docstring lines under
lola/kernel and fails above this number."""
