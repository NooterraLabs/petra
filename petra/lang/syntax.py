"""Untyped syntax tree for the two files of a design, close to the grammar. Internal to
petra.lang.

A card (NAME.card) is what the asker owns: the name, the environment, every signed bound,
the load cases, the claims and the waivers. A design (NAME.petra) is what the designer
owns: the components and the params of a family. A design signs nothing and waives
nothing; it reads a bound the card states with `given NAME`.

Grammar (EBNF; NL is a NEWLINE token). The parser in parser.py follows it rule for rule.
The grammar knows no component kind and no attribute name: those belong to the domain
that registers the kind (petra/models), so adding a domain never edits this file.

    card file   = "petra" INT NL { ( card | param | ambient | given | load | tests | claim | waive ) NL } EOF ;
    design file = "petra" INT NL { ( param | component ) NL } EOF ;
    card      = "card" STRING "{" NL { ( "owner" STRING | "environment" IDENT ) NL } "}" ;
    param     = "param" IDENT "in" range ;
    ambient   = "ambient" bound ;
    given     = "given" IDENT "in" range [ "mean" qty ] [ signature ] ;
    component = KIND IDENT "{" NL { attr NL } "}" ;    KIND: an IDENT not in DECLS
    attr      = IDENT { arg } ;
    arg       = "given" IDENT | "param" IDENT | qty | tuple | ref | STRING | ":" | "--" | "->" ;
    tuple     = "(" qty { "," qty } ")" ;
    bound     = "in" range [ "mean" qty ] [ signature ] | "param" IDENT ;
    signature = ( "signed" | "measured" ) STRING "source" STRING ;
    load      = "load" IDENT "{" NL { "on" path IDENT bound NL } [ signature NL ] "}" ;
    tests     = "tests" IDENT "{" NL "on" path "trials" INT "failures" INT "at" qty
                [ signature ] NL [ signature NL ] "}" ;
    claim     = "claim" IDENT ":" ( qoi rel qty [ "margin" qty ] [ "under" IDENT { "," IDENT } ]
              | "P" "(" qoi ">" qty ")" "<=" NUMBER "under" IDENT
              | "P" "(" "fail" path "at" qty ")" "<=" NUMBER
                "confidence" qty "from" IDENT ) ;
    waive     = "waive" ref "on" path "by" STRING "reason" STRING ;
    range     = "[" qty "," qty "]" ;
    qty       = NUMBER [ unit ] ;     an IDENT or "%" right after a NUMBER is its unit
    qoi       = segment { "." segment } ;          last segment is the quantity name
    segment   = IDENT [ "(" IDENT ")" ] ;          member(diag_ad) names element diag_ad
    path      = IDENT { "." IDENT } ;
    ref       = IDENT { "." IDENT } ;   a local name, a domain keyword, a registry id,
                                        a port (w1.b) or a failure-mode id
    rel       = "<=" | ">=" ;

Every given, load entry and tests record carries a signature, its own or its block's. The
names "in", "mean", "signed", "measured", "source", "param" and "given" cannot be refs in an
attribute line.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Node:
    """Generic syntax node: a keyword-tagged list of children with a source position.
    Lowering pattern-matches on `head`."""

    head: str
    args: tuple = ()
    props: dict = field(default_factory=dict)
    line: int = 0
    col: int = 0


@dataclass(frozen=True)
class File:
    path: str
    version: int
    decls: tuple[Node, ...]
