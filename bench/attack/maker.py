"""What the attacker makes next: a recipe is chosen, and gives drafts to judge.

A `Draft` is one input: a text pair with its deck, or files. A draft may name a relation to an
earlier draft of the same step (`relation`), which the runner checks once both are judged.
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from . import deckinfo, decks, files as F, gen, meta, readers, spec as S
from .spec import Spec

ROOT = Path(__file__).resolve().parents[2]
RECIPES = {"fresh": 22, "corpus": 22, "hunt": 14, "deck": 18, "hints": 8, "json": 4, "forge": 7, "syntax": 2}
"""How often each recipe is chosen, in parts of 97."""


@dataclass
class Draft:
    recipe: str
    spec: Spec | None = None
    deck_name: str = "aisc360"
    deck_text: str = ""
    base_text: str | None = None            # a deck that loads, to read the design with when deck_text does not
    files: dict[str, str] | None = None     # for a draft that no language wrote
    notes: list[str] = field(default_factory=list)
    relation: tuple[str, int] | None = None     # (name, index of the draft in the step that this one is related to)
    shipped: bool = True                    # the deck is a file of petra/decks as it stands
    extra: dict = field(default_factory=dict)   # what a relation check needs: the rename, the direction of a load

    def texts(self) -> tuple[str, str]:
        return self.spec.texts() if self.spec else ("", "")


class Maker:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.seeds = deckinfo.seeds()
        self.infos = {n: deckinfo.read(d) for n, d in self.seeds.items()}
        self.text = {"aisc360": (ROOT / "petra" / "decks" / "aisc360.json").read_text(encoding="utf-8")}
        for n, d in self.seeds.items():
            self.text.setdefault(n, json.dumps(d, indent=1))
        self.corpus = gen.corpus_specs()
        gen.learn_anchors(self.corpus)
        self.probes: dict[str, object] = {}
        self.monotone = {n: meta.load_monotone(d) for n, d in self.seeds.items()}
        self.hung: Draft | None = None

    # --- choosing

    def pick_deck(self) -> str:
        names = list(self.seeds)
        return "aisc360" if self.rng.random() < 0.55 or len(names) == 1 else self.rng.choice([n for n in names if n != "aisc360"])

    def probe(self, text: str):
        if text not in self.probes:
            self.probes[text] = gen.probe_factory(text)
        return self.probes[text]

    def language(self, name: str | None = None, text: str | None = None, info=None) -> Draft:
        """A text pair for a deck: a fresh design, or a changed pair of the corpus when the deck is the one the corpus is written for."""
        name = name or self.pick_deck()
        info = info or self.infos[name]
        text = text or self.text[name]
        if name == "aisc360" and self.corpus and self.rng.random() < 0.5:
            where, base = self.rng.choice(self.corpus)
            s = gen.mutate_corpus(self.rng, info, base)
            s.notes.insert(0, f"from {where}")
            recipe = "corpus"
        else:
            s = gen.fresh(self.rng, info)
            recipe = "fresh"
            if self.rng.random() < 0.45:
                try:
                    s = gen.climb(self.rng, s, self.probe(text))
                except Exception:       # noqa: BLE001 a design the reader cannot read is left as it was
                    pass
        d = Draft(recipe, s, name, text, shipped=name == "aisc360" and text == self.text["aisc360"])
        if self.rng.random() < 0.07:
            d.notes.append("damaged: " + gen.damage(self.rng, info, s))
        d.notes = s.notes + d.notes
        return d

    def next(self) -> list[Draft]:
        recipe = self.rng.choices(list(RECIPES), list(RECIPES.values()))[0]
        return getattr(self, "make_" + recipe)()

    # --- the recipes

    def make_fresh(self) -> list[Draft]:
        return [self.language()]

    make_corpus = make_fresh

    def make_hunt(self) -> list[Draft]:
        name = "aisc360" if self.rng.random() < 0.8 else self.pick_deck()
        d = self.language(name)
        try:
            found = gen.hunt(self.rng, self.infos[name], d.spec, self.probe(self.text[name]))
        except Exception:       # noqa: BLE001 a probe that cannot read the design is no hunt
            found = []
        out = []
        for s, label in found[:8]:
            h = Draft("hunt", s, name, self.text[name], notes=[*d.notes, *s.notes], shipped=d.shipped)
            out.append(h)
        return out or [d]

    def make_deck(self) -> list[Draft]:
        name = "aisc360" if self.rng.random() < 0.6 else self.pick_deck()
        base = self.seeds[name]
        for attempt in range(8):
            mutated, notes, kind = decks.mutate(self.rng, base)
            text = json.dumps(mutated, indent=self.rng.choice([1, 2]))      # the order of keys is kept: the grid reads the names of `let` in it
            loads = True
            try:
                readers.read_deck(text)
            except Exception:       # noqa: BLE001
                loads = False
            if loads or (attempt == 7) or self.rng.random() < 0.08:
                break
        try:
            info = deckinfo.read(mutated)
        except Exception:       # noqa: BLE001
            info = self.infos[name]
        if not info.types:
            info = self.infos[name]
        d = self.language(name, text, info)
        d.recipe, d.shipped, d.base_text = "deck", False, self.text[name]
        d.notes = [f"deck: {n}" for n in notes] + d.notes
        out = [d]
        if kind == "relation" and loads and notes:
            ref = Draft("deck", d.spec.copy() if d.spec else None, name, self.text[name], notes=["the same design against the deck as it ships"], shipped=name == "aisc360")
            out = [ref, d]
            d.relation = ("respell", 0)
        return out

    def _bundle(self, recipe: str) -> Draft | None:
        d = self.language()
        if not d.spec or any(n.startswith("damaged") for n in d.notes):
            return None
        card, design = d.texts()
        try:
            files = readers.bundle_of(card, design, d.deck_text)
        except readers.Timeout:
            self.hung = d
            return None
        if not files:
            return None
        d.files = files
        return d

    def make_hints(self) -> list[Draft]:
        d = self._bundle("hints")
        if not d:
            return [self.language()]
        honest = Draft("hints", None, d.deck_name, d.deck_text, files=d.files, notes=[*d.notes, "the honest files"], shipped=d.shipped)
        changed, notes = F.hints(self.rng, d.files)
        c = Draft("hints", None, d.deck_name, d.deck_text, files=changed, notes=[*d.notes, *notes], relation=("hints", 0), shipped=d.shipped)
        return [honest, c]

    def make_json(self) -> list[Draft]:
        d = self._bundle("json")
        if not d:
            return [self.language()]
        honest = Draft("json", None, d.deck_name, d.deck_text, files=d.files, notes=[*d.notes, "the honest files"], shipped=d.shipped)
        changed, notes = F.respell(self.rng, d.files)
        c = Draft("json", None, d.deck_name, d.deck_text, files=changed, notes=[*d.notes, *notes], relation=("json", 0), shipped=d.shipped)
        return [honest, c]

    def make_forge(self) -> list[Draft]:
        d = self._bundle("forge")
        if not d:
            return [self.language()]
        changed, notes = F.forge(self.rng, d.files)
        return [Draft("forge", None, d.deck_name, d.deck_text, files=changed, notes=[*d.notes, *notes], shipped=d.shipped)]

    def make_syntax(self) -> list[Draft]:
        d = self._bundle("syntax")
        if not d:
            return [self.language()]
        changed, notes = F.syntax(self.rng, d.files)
        return [Draft("syntax", None, d.deck_name, d.deck_text, files=changed, notes=[*d.notes, *notes], shipped=d.shipped)]

    # --- relations of a judged draft

    def derive(self, d: Draft) -> list[Draft]:
        """A draft related to a text pair that was judged: its twin under a relation the pages promise, or one the deck allows."""
        if d.spec is None or d.files is not None:
            return []
        info = self.infos.get(d.deck_name)
        options = ["units", "units_si", "rename", "reorder"]
        if d.deck_name in self.monotone and d.shipped and self.monotone[d.deck_name]:
            options += ["load_up", "load_down"] * 2
        if d.deck_name == "aisc360" and d.shipped:
            options += ["stronger"] * 2
        what = self.rng.choice(options)
        s = d.spec
        extra: dict = {}
        if what == "units":
            c = meta.other_units(self.rng, s)
        elif what == "units_si":
            c = meta.to_si(s)
        elif what == "rename":
            c, extra["rename"] = meta.renamed(self.rng, s)
        elif what == "reorder":
            c = meta.shuffled(self.rng, s)
        elif what in ("load_up", "load_down"):
            f = Fraction(self.rng.choice([101, 110, 150, 200, 400]), 100)
            c = meta.scaled_loads(s, f if what == "load_up" else 1 / f)
            extra["up"] = what == "load_up"
        else:
            c = meta.stronger(self.rng, s)
        if c is None:
            return []
        child = Draft("relation:" + what, c, d.deck_name, d.deck_text, d.base_text, notes=[*d.notes, f"the {what} relation"], relation=(what, 0), shipped=d.shipped, extra=extra)
        return [child]
