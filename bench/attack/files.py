"""Changes to the files the kernel reads, which no language wrote.

The kernel reads `card.json`, `design.json`, `deck.json`, `rules.json` and `proofs.json`
(docs/format.md). Here the files of a design the Python reader checked are changed one way
the pages describe, so the kernel and the third reading are asked about files that the
exporter would never write. Three families:

  hints     `proofs.json` holds only hints for a design with parts: a partition, a point, a
            completion. The pages say it can leave a cell open that a better search would
            settle and can do nothing else (format.md, "Cells from a deck of rules"). So any
            hint, however wrong, must leave every cell as it was or open.
  respell   the same files in another JSON spelling: whitespace, the order of keys, an escape
            for a letter, a dimension written by its exponents. Nothing in format.md lets a
            verdict depend on these.
  forge     a number, a name, a dimension or a key changed to a value the pages refuse or
            read in a stated way, so that the readers' refusals are compared.
"""
from __future__ import annotations

import copy
import hashlib
import json
import random
import re
from fractions import Fraction
from typing import Any, Callable

from . import units

NUMBER = re.compile(r"-?\d+(?:/\d+)?")


def sha(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def dump(obj: Any, rng: random.Random | None = None) -> str:
    """A JSON text of the object, in one of the spellings of whitespace."""
    if rng is None:
        return json.dumps(obj, indent=1, sort_keys=True)
    return json.dumps(obj, indent=rng.choice([None, 0, 1, 2, "\t"]), separators=rng.choice([(",", ":"), (", ", ": "), None]), sort_keys=rng.random() < 0.5, ensure_ascii=rng.random() < 0.5)


def rebind(files: dict[str, str], rng: random.Random | None = None) -> dict[str, str]:
    """The design names the hash of the card it answers, as an honest exporter writes it."""
    out = dict(files)
    try:
        d = json.loads(out["design"])
        d["card"] = sha(out["card"])
        out["design"] = dump(d, rng) if rng else json.dumps(d, indent=1, sort_keys=True)
    except (KeyError, ValueError):
        pass
    return out


def _walk(node: Any, path: tuple = ()) -> list[tuple[Any, Any, tuple]]:
    """(container, key, path) for every value of a JSON tree that is not a container."""
    out = []
    if isinstance(node, dict):
        for k, v in node.items():
            out += _walk(v, path + (k,)) if isinstance(v, (dict, list)) else [(node, k, path + (k,))]
    elif isinstance(node, list):
        for i, v in enumerate(node):
            out += _walk(v, path + (i,)) if isinstance(v, (dict, list)) else [(node, i, path + (i,))]
    return out


def _numbers(obj: Any) -> list[tuple[Any, Any, tuple]]:
    return [(c, k, p) for c, k, p in _walk(obj) if isinstance(c[k], str) and NUMBER.fullmatch(c[k])]


def equal_dim(rng: random.Random, dim: str) -> str | None:
    """Another spelling of the dimension a file names, by exponents (format.md, Numbers)."""
    d = units.dim_of(dim) if not re.search(r"[0-9]", dim) or " " not in dim else None
    if d is None:
        m = re.findall(r"(m|kg|s|A|degC)\^(-?\d+)", dim)
        if not m:
            return None
        acc = {k: 0 for k in ("m", "kg", "s", "A", "degC")}
        for b, e in m:
            acc[b] += int(e)
        d = tuple(acc[k] for k in ("m", "kg", "s", "A", "degC"))
    if d == units.NONE:
        return rng.choice(["dimensionless", "m^0", "m^1 m^-1", "kg^2 kg^-2"])
    parts: list[tuple[str, int]] = []
    for base, e in zip(("m", "kg", "s", "A", "degC"), d):
        if e:
            parts.append((base, e))
            if rng.random() < 0.4 and abs(e) > 1:           # a base may stand more than once: the exponents add
                parts[-1] = (base, e - 1)
                parts.append((base, 1))
            if rng.random() < 0.2:
                parts.append((base, 0))
    rng.shuffle(parts)
    return " ".join(f"{b}^{'0' * rng.choice([0, 0, 1])}{e}" if e >= 0 else f"{b}^{e}" for b, e in parts)


# --- respelling (relations): the verdict must not change

def respell(rng: random.Random, files: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    out, notes = dict(files), []
    which = rng.sample(["card", "design", "proofs"], k=rng.randint(1, 3))
    for name in which:
        try:
            obj = json.loads(out[name])
        except (KeyError, ValueError):
            continue
        if name != "proofs" and rng.random() < 0.6:
            for c, k, p in _walk(obj):
                if k == "dim" and isinstance(c[k], str) and rng.random() < 0.5:
                    alt = equal_dim(rng, c[k])
                    if alt:
                        c[k] = alt
                        notes.append(f"{name}: a dim written {alt}")
        if rng.random() < 0.5:
            def shuffle(n):
                if isinstance(n, dict):
                    items = [(k, shuffle(v)) for k, v in n.items()]
                    rng.shuffle(items)
                    return dict(items)
                if isinstance(n, list):
                    return [shuffle(v) for v in n]
                return n
            obj = shuffle(obj)
            notes.append(f"{name}: keys in another order")
        text = dump(obj, rng)
        if rng.random() < 0.3:                                  # a letter written as an escape
            text = re.sub(r'"(format|name|subject|mechanism)"', lambda m: '"' + "".join(f"\\u{ord(c):04x}" if rng.random() < 0.5 else c for c in m.group(1)) + '"', text)
            notes.append(f"{name}: a key written with escapes")
        out[name] = text
        notes.append(f"{name}: whitespace")
    return rebind(out, rng) if "card" in which or "design" in which else out, notes


# --- hints

def _labels(proofs: dict) -> list[str]:
    found: set[str] = set()
    for c in proofs.get("cells", []):
        found.update((c.get("point") or {}).keys())

        def walk(p):
            if isinstance(p, dict):
                found.add(p.get("input", ""))
                walk(p.get("below"))
                walk(p.get("above"))
        walk(c.get("partition"))
    found.discard("")
    return sorted(found)


def _rand_number(rng: random.Random) -> str:
    n = rng.choice(["0", "1", "-1", "1/2", "-1/3", "7", "1000000", "-1000000000000", "3/8", "127/5000", str(rng.randrange(1, 10 ** rng.choice([2, 6, 20, 80]))), f"{rng.randrange(1, 99)}/{rng.randrange(2, 99)}"])
    return str(Fraction(n))


def _partition(rng: random.Random, labels: list[str], depth: int) -> Any:
    if depth <= 0 or not labels or rng.random() < 0.35:
        return "leaf"
    return {"input": rng.choice(labels), "at": _rand_number(rng), "below": _partition(rng, labels, depth - 1), "above": _partition(rng, labels, depth - 1)}


def hints(rng: random.Random, files: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """proofs.json with hints that are wrong in ways the pages name: a split that is not inside the input's range, a point outside the ranges, a partition 70 deep, a completion for a load or a key that the part does not have, a hint for a cell that is not there, a state that no cell has."""
    try:
        proofs = json.loads(files["proofs"])
    except (KeyError, ValueError):
        return files, []
    p = copy.deepcopy(proofs)
    cells = p.get("cells", [])
    labels = _labels(p) or ["in:attack.lap.pull"]
    notes: list[str] = []
    for _ in range(rng.choice([1, 2, 3, 6])):
        if not cells:
            break
        c = rng.choice(cells)
        k = rng.choice(["split", "point", "deep", "completion", "state", "ghost", "dup", "drop", "scramble_point", "huge", "why"])
        if k == "split":
            c["state"] = "proved"
            c["partition"] = _partition(rng, labels, rng.choice([1, 2, 5]))
            c.pop("point", None)
        elif k == "point":
            c["state"] = "refuted"
            c["point"] = {l: _rand_number(rng) for l in labels}
            c.pop("partition", None)
        elif k == "deep":
            part: Any = "leaf"
            for _ in range(rng.choice([63, 64, 65, 80])):
                part = {"input": rng.choice(labels), "at": _rand_number(rng), "below": part, "above": "leaf"}
            c["state"], c["partition"] = "proved", part
        elif k == "completion":
            c["completion"] = {"keys": [["lap", "holes", "oversize"], ["nobody", "x", "y"]][:rng.randint(0, 2)], "loads": [["lap", "pull", rng.choice(["gravity", "wind", ""]), _rand_number(rng)]][:rng.randint(0, 1)]}
        elif k == "state":
            c["state"] = rng.choice(["proved", "refuted", "waived", "open", "not_applicable", "bogus"])
        elif k == "ghost":
            cells.append({"subject": rng.choice(["ghost", c.get("subject", "x")]), "mechanism": c.get("mechanism", "m"), "entry": rng.choice(["", "x", c.get("entry", "") + "/where"]), "state": "proved", "partition": "leaf"})
        elif k == "dup":
            cells.append(copy.deepcopy(c))
        elif k == "drop" and len(cells) > 1:
            cells.remove(c)
        elif k == "scramble_point" and c.get("point"):
            ks = list(c["point"])
            c["point"][rng.choice(ks)] = rng.choice(["1/0", "-0", "01", "", "x", "1e3", "3.5"])
        elif k == "huge":
            c["point"] = {l: str(10 ** rng.choice([300, 1300, 4001])) for l in labels}
            c["state"] = "refuted"
        elif k == "why":
            c["why"] = rng.choice(["", "x" * 5000, "‮", "\x1b[2J"])
        notes.append(f"a hint: {k}")
    return {**files, "proofs": dump(p, rng)}, notes


def sound(honest: list[tuple], got: list[tuple]) -> str | None:
    """What a hint may not do, as format.md says it: the same cells in the same order, and a cell that was proved, refuted or not applicable is that or open.

    A cell that was open or waived may now be settled by a better hint, so it is not held. Returns what was broken, or None."""
    honest = [c for c in honest if not c[2].endswith("/where")]       # a `/where` cell is there when a hint proves the range, so a hint may add it or take it away
    got = [c for c in got if not c[2].endswith("/where")]
    if [c[:3] for c in honest] != [c[:3] for c in got]:
        return f"the cells are not the same: {len(honest)} before and {len(got)} after"
    for a, b in zip(honest, got):
        if a[3] in ("proved", "refuted", "not_applicable") and b[3] not in (a[3], "open"):
            return f"{a[0]}/{a[1]}/{a[2]} was {a[3]} and is {b[3]} under other hints"
    return None


# --- forging: values the pages refuse or read in a stated way

def forge(rng: random.Random, files: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    out, notes = dict(files), []
    name = rng.choice(["card", "design", "design", "card", "deck"])
    try:
        obj = json.loads(out[name])
    except (KeyError, ValueError):
        return files, []
    nums = _numbers(obj)
    texts = [(c, k, p) for c, k, p in _walk(obj) if isinstance(c[k], str) and not NUMBER.fullmatch(c[k]) and k in ("name", "subject", "mechanism", "by", "field", "type", "entity", "line", "reason", "key")]
    ops: list[Callable] = []
    if nums:
        ops += [lambda: ("number", nums)] * 3
    if texts:
        ops += [lambda: ("text", texts)] * 2
    ops += [lambda: ("shape", None)] * 2
    kind, pool = rng.choice(ops)()
    if kind == "number":
        c, k, p = rng.choice(pool)
        old = c[k]
        c[k] = rng.choice(["-0", "00", "01", "1/0", "2/4", "+1", "1.5", "1e3", "", " 1", "1 ", "٣", "１", "9" * 4001, "9" * 4000, "1/" + "9" * 3999, "-1/2", "0/5", "1/1", str(Fraction(old) * 2) if re.fullmatch(r"-?\d+(/\d+)?", old) else "1"])
        notes.append(f"{name}: number {old[:20]} made {c[k][:20]!r}")
    elif kind == "text":
        c, k, p = rng.choice(pool)
        old = c[k]
        c[k] = rng.choice(["�", "a\ud800", "a\udfff", "😀", "x" * 64, "x" * 65, "x" * 200, "x" * 201, "", old + " ", " " + old, old.upper(), "a\nb", "a\u0000b", "a‮b", "a/b", "é", "é", old + "​", "where"])
        notes.append(f"{name}: text {old[:20]!r} made {c[k][:20]!r}")
    else:
        if isinstance(obj, dict):
            what = rng.choice(["unknown_key", "drop_key", "null", "type", "format"])
            if what == "unknown_key":
                obj["zzz"] = 1
            elif what == "drop_key" and obj:
                obj.pop(rng.choice(list(obj)))
            elif what == "null" and obj:
                obj[rng.choice(list(obj))] = None
            elif what == "type" and obj:
                obj[rng.choice(list(obj))] = rng.choice([1, True, [], {}, "x"])
            elif what == "format":
                obj["format"] = rng.choice(["petra-card/1", "", "petra-rules/0", None])
            notes.append(f"{name}: {what}")
    out[name] = dump(obj, rng)
    return rebind(out, rng) if name in ("card",) else out, notes


def syntax(rng: random.Random, files: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """The text of one file changed in its JSON syntax: a byte-order mark, a trailing comma, a key twice, a number where a string goes, nesting past 128."""
    name = rng.choice(["card", "design", "proofs"])
    if name not in files:
        return files, []
    text = files[name]
    k = rng.choice(["bom", "trailing", "dup", "nest", "bare", "tail", "comment", "single", "nan"])
    if k == "bom":
        text = "﻿" + text
    elif k == "trailing":
        i = text.rfind("}")
        text = text[:i].rstrip() + "," + text[i:]
    elif k == "dup":
        text = text.replace("{", '{"format": "x",', 1) if rng.random() < 0.5 else re.sub(r'"format": "([^"]*)"', r'"format": "\1", "format": "\1"', text, count=1)
    elif k == "nest":
        n = rng.choice([127, 128, 129, 200])
        text = text[:-1].rstrip() + ', "z": ' + "[" * n + "]" * n + "}" if text.rstrip().endswith("}") else text
    elif k == "bare":
        text = re.sub(r'"(lo|hi)": "(-?\d+)"', r'"\1": \2', text, count=1)
    elif k == "tail":
        text += "\n{}"
    elif k == "comment":
        text = "// x\n" + text
    elif k == "single":
        text = text.replace('"', "'", 2)
    elif k == "nan":
        text = re.sub(r'"(lo|hi)": "-?\d+(?:/\d+)?"', r'"\1": NaN', text, count=1)
    return {**files, name: text}, [f"{name}: JSON syntax {k}"]
