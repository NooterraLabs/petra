"""What the attacker makes next: a recipe is chosen, and gives drafts to judge.

A `Draft` is one input: a text pair with its deck, or files. A draft may name a relation to an
earlier draft of the same step (`relation`), which the runner checks once both are judged.
"""
from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from . import bind, deckinfo, decks, files as F, gen, meta, readers, spec as S
from .spec import Spec

ROOT = Path(__file__).resolve().parents[2]
RECIPES = {"fresh": 22, "corpus": 22, "hunt": 14, "deck": 18, "hints": 8, "json": 4, "forge": 7, "syntax": 2, "bind": 10}
"""How often each recipe is chosen, in parts of 107."""


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
    extra: dict = field(default_factory=dict)   # what a relation check needs: the rename, the direction of a load, what the binding expects
    run: str | None = bind.AUTO             # the run the deck is read with: AUTO for its honest one (bind.run_for), None for none

    def texts(self) -> tuple[str, str]:
        """The pair, with a card that names the deck it is checked against unless its spec names another or none."""
        return self.spec.texts(bind.pin(self.deck_text)) if self.spec else ("", "")


BINDING = ("card_hash", "card_none", "card_name", "run_other", "run_none", "gate", "run_text", "run_keys", "changed", "changed_stale_run",
           "changed_rebound", "two_decks", "name_escape", "crlf", "deck_json", "card_json", "card_json")
"""The sub-recipes of the binding recipe. Each says what it expects in Draft.extra["bind"] (bind.expected)."""


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
            if s.rules == bind.pin(self.text["aisc360"]):
                s.rules = S.DECK        # its owner names the deck it is checked against; a case that names another or none keeps it
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

    # --- the binding by hash (bind.py): the sub-recipes are BINDING, and README.md says what each must hold

    def make_bind(self) -> list[Draft]:
        kind = self.rng.choice(BINDING)
        out = getattr(self, "bind_" + kind)()
        for d in out:
            d.recipe = d.recipe if d.recipe.startswith("bind:") else "bind:" + kind
        return out

    def _plain(self, name: str | None = None) -> Draft:
        """A text pair with no damage, for a recipe whose one fault is of the binding."""
        for _ in range(4):
            d = self.language(name)
            if not any(n.startswith("damaged") for n in d.notes):
                break
        return d

    def _other_text(self, text: str) -> str:
        """The file of another deck than the one whose file is `text`."""
        others = [t for t in self.text.values() if t != text]
        return self.rng.choice(others) if others else text + "\n"

    def _as(self, d: Draft, what: str, expect: str, rules: list[str] | None = None, **more) -> Draft:
        d.extra["bind"] = {"what": what, "expect": expect, "rules": rules or [], **more}
        d.notes.append(f"binding: {what}")
        return d

    def _child(self, d: Draft, **change) -> Draft:
        c = Draft(d.recipe, d.spec.copy() if d.spec else None, d.deck_name, d.deck_text, d.base_text, files=dict(d.files) if d.files else None,
                  notes=list(d.notes), shipped=d.shipped, extra=dict(d.extra), run=d.run)
        for k, v in change.items():
            setattr(c, k, v)
        return c

    def bind_card_hash(self) -> list[Draft]:
        d = self._plain()
        name, right = bind.pin(d.deck_text)
        hexes = right.split(":", 1)[1]
        i = self.rng.randrange(len(hexes))
        flip = hexes[:i] + ("0" if hexes[i] != "0" else "1") + hexes[i + 1:]
        what, other = self.rng.choice([("the hash of another deck", bind.deck_hash(self._other_text(d.deck_text))),
                                       ("one hex digit changed", "sha256:" + flip), ("a hash of zeros", "sha256:" + "0" * 64),
                                       ("an empty hash", ""), ("the hash with no prefix", hexes), ("the hash in upper-case hex", "sha256:" + hexes.upper()),
                                       ("the prefix in capitals", "SHA256:" + hexes), ("the hash with a space before it", " " + right),
                                       ("the hash of the file with CR LF line ends", bind.sha(d.deck_text.replace("\n", "\r\n")))])
        d.spec.rules = (name, other)
        return [self._as(d, f"the card names {what}", "refuse", ["types.9"])]

    def bind_card_none(self) -> list[Draft]:
        d = self._plain()
        d.spec.rules = None
        return [self._as(d, "the card names no deck", "refuse", ["types.9"])]

    def bind_card_name(self) -> list[Draft]:
        d = self._plain()
        name, right = bind.pin(d.deck_text)
        other_name = bind.name_of(self._other_text(d.deck_text))
        what, wrong = self.rng.choice([("the name in capitals", name.upper() if name.upper() != name else name + "X"), ("the name with a space after it", name + " "),
                                       ("an empty name", ""), ("the name of another deck", other_name if other_name != name else name + "-2"),
                                       ("the name with a zero-width space", name + "\u200b"), ("the name cut short", name[:-1])])
        d.spec.rules = (wrong, right)
        return [self._as(d, f"the card names {what} and the right hash", "refuse", ["types.9"])]

    def bind_run_other(self) -> list[Draft]:
        d = self._plain()
        what, run = self.rng.choice([("the run of another deck", bind.made_up_run(self._other_text(d.deck_text))),
                                     ("the run of the deck with one more line end", bind.made_up_run(d.deck_text + "\n")),
                                     ("the shipped run with a deck that is not the one it admitted", bind.shipped_run(self.text["aisc360"]) if d.deck_text != self.text["aisc360"] else bind.made_up_run(self._other_text(d.deck_text)))])
        d.run = run
        return [self._as(d, f"the deck is read with {what}", "refuse", ["types.11"])]

    def bind_run_none(self) -> list[Draft]:
        d = self._plain()
        d.run = None
        return [self._as(d, "the deck is read with no run", "refuse", ["types.11"])]

    def bind_gate(self) -> list[Draft]:
        d = self._plain()
        if self.rng.random() < 0.3:      # one letter, a to z, is enough: the same verdict as the honest run
            gate = self.rng.choice(["a", "1a", " Z ", "--x--", "日本 a"])
            c = self._child(d, run=bind.made_up_run(d.deck_text, gate=gate), relation=("bind_same", 0))
            return [d, self._as(c, f"a gate with a letter, {gate!r}", "read")]
        gate = self.rng.choice(["", "123", "--", " ", "é", "日本語", "ÅÄÖ", "Αβγ", "1.2", "\t", "\ufffd", 7, None, [], {"a": "b"}, True])
        d.run = bind.made_up_run(d.deck_text, gate=gate)
        return [self._as(d, f"a gate with no letter a to z, {gate!r}", "refuse", ["types.11", "run:shape"])]

    def bind_run_text(self) -> list[Draft]:
        d = self._plain()
        honest = bind.run_for(d.deck_text)
        body = json.loads(honest)
        what, run, expect = self.rng.choice([
            ("an empty run", "", "refuse"), ("a run that is not JSON", "not json", "refuse"), ("a run that is a list", "[]", "refuse"),
            ("a run that is an empty object", "{}", "refuse"), ("a run that is null", "null", "refuse"),
            ("a run with a byte-order mark", "\ufeff" + honest, "refuse"), ("a run with a trailing comma", honest.rstrip().rstrip("}") + ",}", "refuse"),
            ("a run with a second value after it", honest + "{}", "refuse"),
            ("a run of another format", json.dumps({**body, "format": "petra-run/1"}), "refuse"),
            ("a run with no format", json.dumps({k: v for k, v in body.items() if k != "format"}), "refuse"),
            ("a run with no deck", json.dumps({k: v for k, v in body.items() if k != "deck"}), "refuse"),
            ("a run with no gate", json.dumps({k: v for k, v in body.items() if k != "gate"}), "refuse"),
            ("a run whose deck is a number", json.dumps({**body, "deck": 5}), "refuse"),
            ("a run whose deck is null", json.dumps({**body, "deck": None}), "refuse"),
            ("a run whose deck holds U+FFFD", json.dumps({**body, "deck": body["deck"] + "\ufffd"}), "refuse"),
            ("a run whose gate holds half a surrogate pair", json.dumps({**body, "gate": "a\ud800"}), "refuse"),
            ("a run whose deck is in upper-case hex", json.dumps({**body, "deck": "sha256:" + body["deck"].split(":", 1)[1].upper()}), "refuse"),
            ("a run nested 200 deep", json.dumps({**body, "zzz": "@"}).replace('"@"', "[" * 200 + "]" * 200), "agree"),
            ("a run with a number of 400 digits", json.dumps({**body, "seed": "@"}).replace('"@"', "9" * 400), "agree"),
            ("a run with a number of 5000 digits", json.dumps({**body, "seed": "@"}).replace('"@"', "9" * 5000), "agree"),
            ("a run with a number in an exponent", json.dumps({**body, "seed": "@"}).replace('"@"', "1e400"), "agree")])
        d.run = run
        return [self._as(d, what, expect, ["run:shape", "types.11"] if expect == "refuse" else [])]

    def bind_run_keys(self) -> list[Draft]:
        d = self._plain()
        honest = bind.run_for(d.deck_text)
        body = json.loads(honest)
        right, wrong = body["deck"], bind.deck_hash(self._other_text(d.deck_text))
        pick = self.rng.random()
        if pick < 0.25:          # a key twice: the last value is read (format.md, "Keys")
            last_right = self.rng.random() < 0.5
            first, last = (wrong, right) if last_right else (right, wrong)
            run = '{"deck": "%s", "format": "%s", "gate": "%s", "deck": "%s"}' % (first, bind.RUN, body["gate"], last)
            d.run = run
            if last_right:
                c = self._child(d, relation=("bind_same", 0))
                d.run = bind.AUTO
                return [d, self._as(c, "the run names the deck twice, the right hash last", "read")]
            return [self._as(d, "the run names the deck twice, another hash last", "refuse", ["types.11"])]
        more = self.rng.choice([{"seed": 3}, {"lines": [{"mechanism": "x", "state": "refused", "checks": []}]}, {"whole": {"reads": {"outcome": "fail"}}},
                                {"zzz": None}, {"Deck": wrong}, {"GATE": ""}, {"inputs": {"rules": wrong}}, {"changed": "x" * 3000},
                                {"stray": ["everything"], "lines": []}, {"deck_": wrong, "gate ": ""}])
        c = self._child(d, run=bind.text({**body, **more}), relation=("bind_same", 0))
        return [d, self._as(c, f"a run with keys no reader reads, {sorted(more)}", "read")]

    def _edited(self, text: str) -> tuple[str, str, bool]:
        """The deck's file changed after the bundle was made: one byte, or a limit raised. True when what it says is the same."""
        k = self.rng.choice(["space", "line_end", "digit", "limit", "limit"])
        if k == "space":
            i = text.index("{") + 1
            return text[:i] + " " + text[i:], "one space added", True
        if k == "line_end":
            return text + "\n", "one line end added", True
        if k == "digit":
            spots = [m.start() for m in re.finditer(r"(?<=[0-9.])[1-8](?=[0-9 \"])", text)]
            if spots:
                i = self.rng.choice(spots)
                return text[:i] + str(int(text[i]) + 1) + text[i + 1:], "one digit raised", False
        body = json.loads(text)
        items = decks.value_leaves(body)
        if not items:
            return text + " ", "one space added", True
        parent, key, path = self.rng.choice(items)
        n, unit = decks._value(parent, key)
        decks._set_value(parent, key, n * 10 if n else Fraction(1), unit, self.rng)
        return json.dumps(body, indent=1), f"a limit raised ten times, {'.'.join(map(str, path[-3:]))}", False

    def bind_changed(self) -> list[Draft]:
        """The deck's file changed after the bundle was made, with the card, deck.json and the run still naming the deck as it was."""
        d = self._plain()
        old = d.deck_text
        new, what, _ = self._edited(old)
        d.spec.rules, d.run, d.deck_text, d.base_text, d.shipped = bind.pin(old), bind.run_for(old), new, old, False
        return [self._as(d, f"the rules changed after the bundle was made ({what}), nothing rebound", "refuse", ["types.9", "types.10", "types.11"])]

    def bind_changed_stale_run(self) -> list[Draft]:
        """The deck's file changed after its run: the card names the deck as it is, and the run is the old one."""
        d = self._plain()
        old = d.deck_text
        new, what, _ = self._edited(old)
        d.run, d.deck_text, d.base_text, d.shipped = bind.run_for(old), new, old, False
        return [self._as(d, f"the rules changed after their run ({what}), the card rebound and the run not", "refuse", ["types.11"])]

    def bind_changed_rebound(self) -> list[Draft]:
        """The deck's file changed, and every file bound to it again, as an honest exporter would: a deck like any other."""
        d = self._plain()
        old = d.deck_text
        new, what, same = self._edited(old)
        c = self._child(d, deck_text=new, base_text=old, shipped=False)
        if same:
            c.relation = ("bind_same", 0)
            return [d, self._as(c, f"the rules changed ({what}) and every file rebound", "read")]
        return [self._as(c, f"the rules changed ({what}) and every file rebound", "read")]

    def bind_two_decks(self) -> list[Draft]:
        """The same card under two decks: it names one, and is checked against the other, which says the same in other bytes."""
        d = self._plain()
        a = d.deck_text
        body = json.loads(a)
        decks.op_respell(self.rng, body)
        b = json.dumps(body, indent=self.rng.choice([1, 2]))
        if b == a:
            b = a + "\n"
        named, read = (a, b) if self.rng.random() < 0.5 else (b, a)
        d.spec.rules = bind.pin(named)
        other = self._child(d, deck_text=read, base_text=a, shipped=read == self.text["aisc360"] and d.shipped)
        d.deck_text, d.base_text, d.shipped = named, a, named == self.text["aisc360"] and d.shipped
        return [self._as(d, "the card under the deck it names", "read"), self._as(other, "the same card under another deck", "refuse", ["types.9"])]

    def bind_name_escape(self) -> list[Draft]:
        """A deck whose name a card's text escapes, bound honestly: the name changes nothing but the binding."""
        d = self._plain()
        body = json.loads(d.deck_text)
        name = self.rng.choice(['a"b', "back\\slash", "café", "x" * 300, " lead", "a\u202eb", "\\\"", "日本"])
        plain = self._child(d, deck_text=json.dumps({**body, "name": "plain"}, indent=1), base_text=d.deck_text, shipped=False)
        c = self._child(d, deck_text=json.dumps({**body, "name": name}, indent=1), base_text=d.deck_text, shipped=False, relation=("bind_same", 0))
        return [plain, self._as(c, f"a deck named {name[:20]!r}, bound honestly", "read")]

    def bind_crlf(self) -> list[Draft]:
        """The deck's file with CR LF line ends, bound as Petra binds it: by the hash of the file with LF line ends (docs/deck.md)."""
        d = self._plain()
        c = self._child(d, deck_text=d.deck_text.replace("\n", "\r\n"), base_text=d.deck_text, shipped=False)
        return [self._as(c, "the deck's file with CR LF line ends, the card and the run naming its hash with LF", "agree")]

    def bind_deck_json(self) -> list[Draft]:
        d = self._bundle("bind")
        if not d:
            return [self._plain()]
        deck = json.loads(d.files["deck"])
        name, right = bind.pin(d.deck_text)
        what, held = self.rng.choice([("another hash", {"name": name, "hash": bind.deck_hash(self._other_text(d.deck_text))}), ("another name", {"name": name + "-x", "hash": right}),
                                      ("no rules", "drop"), ("a name that is a number", {"name": 1, "hash": right}), ("no hash", {"name": name}),
                                      ("the hash in upper-case hex", {"name": name, "hash": right.upper()}), ("rules that is a text", "x"), ("rules that is null", None)])
        if held == "drop":
            deck.pop("rules", None)
        else:
            deck["rules"] = held
        files = {**d.files, "deck": F.dump(deck, self.rng)}
        return [self._as(Draft("bind:deck_json", None, d.deck_name, d.deck_text, files=files, notes=list(d.notes), shipped=d.shipped), f"deck.json names {what}", "refuse", ["types.10"])]

    def bind_card_json(self) -> list[Draft]:
        """card.json with its owner, or a source or a kind of an input or a statement, left out or of the wrong kind, and the same fault in the card's text."""
        d = self._bundle("bind")
        if not d:
            return [self._plain()]
        card = json.loads(d.files["card"])
        items = [("input", i) for i in card.get("inputs", [])] + [("statement", s) for s in card.get("states", [])]
        options = ["owner"] + (["source", "kind"] if items else [])
        key = self.rng.choice(options)
        if key == "owner":
            what, value = self.rng.choice([("left out", "drop"), ("empty", ""), ("a number", 5), ("null", None), ("another owner", "someone.else@example.org")])
            holder, where = card, "the card's owner"
        else:
            kind, holder = self.rng.choice(items)
            where = f"the {key} of {kind} {holder.get('name')}"
            what, value = self.rng.choice([("left out", "drop"), ("empty", ""), ("a number", 1), ("null", None)] +
                                          ([("estimated", "estimated"), ("Signed", "Signed"), ("measured", "measured")] if key == "kind" else [("another source", "a drawing")]))
        if value == "drop":
            holder.pop(key, None)
        else:
            holder[key] = value
        good = value in ("measured", "a drawing", "someone.else@example.org")
        files = F.rebind({**d.files, "card": F.dump(card, self.rng)}, self.rng)
        f = Draft("bind:card_json", None, d.deck_name, d.deck_text, files=files, notes=list(d.notes), shipped=d.shipped)
        if good:
            honest = Draft("bind:card_json", None, d.deck_name, d.deck_text, files=d.files, notes=[*d.notes, "the honest files"], shipped=d.shipped)
            f.relation = ("bind_same", 0)
            return [honest, self._as(f, f"{where} is {what}", "read")]
        out = [self._as(f, f"{where} is {what}", "refuse", ["types.5"])]
        if key == "owner" and value in ("drop", ""):        # the same fault in the card's text, which the language refuses
            t = self._child(d, files=None)
            t.spec.owner = ""
            t.recipe = "bind:card_json"
            out.append(self._as(t, "the card's owner is empty in its text", "refuse"))
        return out

    # --- relations of a judged draft

    def derive(self, d: Draft) -> list[Draft]:
        """A draft related to a text pair that was judged: its twin under a relation the pages promise, or one the deck allows."""
        if d.spec is None or d.files is not None or d.extra.get("bind"):        # a draft of the binding is about its binding, which a twin would not keep
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
        child = Draft("relation:" + what, c, d.deck_name, d.deck_text, d.base_text, notes=[*d.notes, f"the {what} relation"], relation=(what, 0), shipped=d.shipped, extra=extra, run=d.run)
        return [child]
