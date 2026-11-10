"""The clean-room twin's done test: `python scripts/twin_check.py [--n 10000] [--seed 1]
[--workers 6] [--full FILE] [--rows FILE]`.

Generates the steel gate's stream as scripts/steel_gate.py does and checks each design with
Petra and with the clean-room twin in twin/, which never imports petra. It compares them per
connection (verdict and governing limit state) and per limit state (outcome and
utilisation), gives every disagreement a cause, writes docs/twin_check_log.jsonl (one compact
row per design) and prints the measured tables of docs/twin_check.md. `--full` also keeps each
design, its card and both full readings. `--rows` reads a log written earlier instead of
running the stream again; given a `--full` log it rewrites the compact one. Untrusted tooling:
it never changes a verdict.

A toleranced design reads one length as `given NAME`, a bound its card gives. Where the twin
refuses such a design, it is also run at each end of that bound, the length stated in the
design and the bound gone from the card, and its worst reading of each check kept (`corners`).
Every count says which reading it uses.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from petra.lang import parse_design  # noqa: E402
from petra.models.steel import calc  # noqa: E402
from petra.models.steel.domain import required  # noqa: E402
from petra.models.steel.fatigue import GENERATORS  # noqa: E402
from petra.models.steel.gate import deck_outcomes  # noqa: E402
from petra.models.steel.generate import generate  # noqa: E402
from petra.pipeline import check_design  # noqa: E402
from petra.registry import build_registry  # noqa: E402
from petra.solvers import SolverSource  # noqa: E402
from petra.verdict import STATUS  # noqa: E402
from twin.card import CardError  # noqa: E402
from twin.run import check_text  # noqa: E402

SLACK = 1e-9
"""Both sides compute exactly; floats carry their ratios here, so 1 + SLACK still reads as 1."""
CLOSE = 0.01
"""Two utilisations of one limit state agree when they differ by at most 1% of the larger."""
GIVEN = re.compile(r"^given (\w+) in \[([0-9.]+) inch, ([0-9.]+) inch\] signed .*\n\n?", re.M)
"""The toleranced length of a gate design, as its card gives it."""


def petra_reading(card: str, text: str, registry) -> dict:
    """Petra's verdict, each required mode's outcome, and each mode's largest utilisation over
    the design's box (calc.values, the numbers the gate's generator scales its loads by)."""
    design = parse_design(card, text, "gate.petra", registry)
    report = check_design(design, registry, (SolverSource(),))
    states, _ = deck_outcomes(report)
    conn = calc.connection(design, "c1", registry)
    modes = {}
    for mode in required(conn, design):
        found = [v for v in calc.values(conn, design, registry, mode, "gate") if not v.excused] if mode in GENERATORS else []
        best = max(found, key=lambda v: v.utilisation, default=None)
        modes[mode] = {"state": states.get(mode, "absent"),
                       "u": None if best is None else best.utilisation,
                       "check": None if best is None else best.what}
    return {"status": STATUS[type(report.verdict)], "modes": modes}


def corners(card: str, text: str) -> list[tuple[str, str]]:
    """The card and the design with the one toleranced length at each end of its interval: the
    card gives the bound no longer, and the line that read it states the length."""
    m = GIVEN.search(card)
    if m is None:
        return []
    name, lo, hi = m.groups()
    line = re.search(rf"^(\s*)(\w+) given {name}$", text, re.M)
    indent, key = line.groups()
    return [(card[:m.start()] + card[m.end():], text[:line.start()] + f"{indent}{key} {x} inch" + text[line.end():])
            for x in (lo, hi)]


def twin_reading(card: str, text: str) -> dict:
    """The twin's status and checks for c1, from the design as written or, when the twin rejects a
    toleranced length, from its worst reading at the interval's two ends."""
    def run(card: str, text: str) -> dict:
        try:
            return check_text(card, text)["components"][0]
        except CardError as e:
            return {"status": "input_error", "reason": f"reader: {e}"}

    raw = run(card, text)
    via = "design"
    if raw["status"] == "input_error" and corners(card, text):
        ends = [run(*c) for c in corners(card, text)]
        if all(e["status"] == "checked" for e in ends):
            via = "corners"
            worst: dict[str, dict] = {}
            for e in ends:
                for c in e["checks"]:
                    if c["name"] not in worst or (c["utilisation"] or 0) > (worst[c["name"]]["utilisation"] or 0):
                        worst[c["name"]] = c
            raw = {**ends[0], "checks": list(worst.values()), "raw_reason": raw["reason"]}
    out = {"status": raw["status"], "via": via, "reason": raw.get("reason") or raw.get("raw_reason")}
    if raw["status"] != "checked":
        return out
    checks = [{"name": c["name"], "mode": c["mode"], "clause": c["clause"], "u": c["utilisation"],
               "available": c["available"], "demand": c["demand"], "unit": c["unit"]} for c in raw["checks"]]
    modes: dict[str, float] = {}
    for c in checks:
        if c["u"] is not None:
            modes[c["mode"]] = max(modes.get(c["mode"], 0.0), c["u"])
    return {**out, "checks": checks, "modes": modes, "unsupported": raw["unsupported"], "notes": raw["notes"]}


def assess(g, registry) -> dict:
    t0 = time.perf_counter()
    petra = petra_reading(g.card, g.text, registry)
    t1 = time.perf_counter()
    twin = twin_reading(g.card, g.text)
    t2 = time.perf_counter()
    return {"name": g.name, "kind": g.kind, "expected": g.expected, "free": g.free, "toleranced": g.toleranced,
            "cyclic": g.cycles is not None, "card": g.card, "text": g.text, "petra": petra, "twin": twin,
            "seconds": {"petra": t1 - t0, "twin": t2 - t1}}


def chunk(args: tuple[int, int, int]) -> list[dict]:
    seed, start, count = args
    registry = build_registry()
    rows = []
    t = time.perf_counter()
    for g in generate(count, seed, registry, start):
        row = assess(g, registry)
        row["seconds"]["generate"] = time.perf_counter() - t - row["seconds"]["petra"] - row["seconds"]["twin"]
        rows.append(row)
        t = time.perf_counter()
    return rows


FOLD = {"bearing": "bolts"}
"""The twin reports each ply's bearing and tearout apart from its bolt group; Petra's bolts
mode holds the group to the least of shear, bearing and tearout per bolt, so they meet there."""
RENAMED = {"normal and flexural interaction, section B-B": "bracket_edge", "shear yielding, section B-B": "bracket_edge"}
"""Twin checks Petra files under another mode: a shaped bracket's free edge is bracket_edge."""


def twin_modes(twin: dict) -> dict[str, tuple[float, str]]:
    """The twin's largest utilisation per limit state, in Petra's mode names, with its check."""
    out: dict[str, tuple[float, str]] = {}
    for c in twin["checks"]:
        if c["u"] is None:
            continue
        mode = RENAMED.get(c["name"], FOLD.get(c["mode"], c["mode"]))
        if mode not in out or c["u"] > out[mode][0]:
            out[mode] = (c["u"], c["name"])
    return out


def fails(u: float) -> bool:
    return u > 1 + SLACK


def compare(row: dict) -> dict:
    """One design: each verdict, and per limit state both sides carry, the outcome of the pair."""
    petra, twin = row["petra"], row["twin"]
    out = {"name": row["name"], "kind": row["kind"], "petra": petra["status"], "via": twin["via"],
           "free": row["free"], "toleranced": row["toleranced"], "cyclic": row["cyclic"]}
    if twin["status"] != "checked":
        return {**out, "twin": twin["status"], "reason": twin["reason"]}
    tm = twin_modes(twin)
    if not tm:
        return {**out, "twin": "unsupported", "reason": "; ".join(twin["unsupported"]) or "no checks"}
    pm = {m: v for m, v in petra["modes"].items() if v["u"] is not None or v["state"] != "pass"}
    shared = sorted(set(tm) & {m for m, v in pm.items() if v["u"] is not None})
    modes = []
    for m in shared:
        state, pu, (tu, check) = pm[m]["state"], pm[m]["u"], tm[m]
        if fails(tu) and state == "pass":
            outcome = "twin_fail"
        elif not fails(tu) and state != "pass":
            outcome = "petra_fail"
        elif abs(pu - tu) <= CLOSE * max(abs(pu), abs(tu)):
            outcome = "agree"
        else:
            outcome = "apart"
        modes.append({"mode": m, "state": state, "petra_u": pu, "twin_u": tu, "twin_check": check,
                      "petra_check": pm[m]["check"], "outcome": outcome})
    twin_verdict = "FAIL" if any(fails(u) for u, _ in tm.values()) else "PASS"
    petra_gov = max(shared, key=lambda m: pm[m]["u"], default=None)
    twin_gov = max(tm, key=lambda m: tm[m][0], default=None)
    return {**out, "twin": twin_verdict, "modes": modes,
            "petra_only_failed": sorted(m for m, v in pm.items() if m not in tm and v["state"] != "pass"),
            "twin_only": sorted(set(tm) - set(pm)),
            "governing": {"petra": petra_gov, "twin": twin_gov,
                          "petra_u": None if petra_gov is None else pm[petra_gov]["u"],
                          "twin_u": None if twin_gov is None else tm[twin_gov][0]},
            "unsupported": twin["unsupported"]}


OUTCOMES = ("agree", "apart", "twin_fail", "petra_fail")
"""A limit state both sides carry: same side of 1 and within CLOSE; same side but further
apart; the twin fails it and Petra holds it; the twin holds it and Petra fails it."""


# --- Why they disagree ---------------------------------------------------------------------
#
# Each limit state on opposite sides of 1 (twin_fail, petra_fail) gets one cause below. The
# rules read the design, its card and both readings; each cause was settled by the hand checks
# that docs/twin_check.md lists. A disagreement no rule claims is "unclassified".

PETRA_UNSAFE, PETRA_SAFE = "Petra error, unsafe", "Petra error, conservative"
TWIN_UNSAFE, TWIN_SAFE = "twin error, unsafe", "twin error, conservative"
COVERAGE, AMBIGUITY = "coverage", "ambiguity"

CAUSES = {
    "tearout-direction": (PETRA_UNSAFE, "bracket bolt pushed toward the plate's back edge, whose tearout Petra never checks"),
    "weld-arm": (PETRA_UNSAFE, "weld bracket eccentricity read from the weld line, where the reference says the centroid"),
    "partial-block": (TWIN_UNSAFE, "block shear through fewer rows than the group, which the twin does not check"),
    "prying-shear": (TWIN_UNSAFE, "hanger prying under shear, which the twin computes from Fnt instead of F'nt"),
    "uncoped-web-rupture": (PETRA_SAFE, "uncoped beam web checked for shear rupture of its net section"),
    "eccentric-method": (PETRA_SAFE, "eccentric bolt or weld group by Petra's elastic method against the twin's IC"),
    "bracket-least-edge": (TWIN_SAFE, "every bracket bolt given II.A-22's least edge distance"),
    "slot-in-tearout": (TWIN_SAFE, "a bracket's parallel slot length taken into the back edge's clear distance"),
    "web-end-bolt": (TWIN_SAFE, "a continuous web's end bolt taken as an interior bolt"),
    "hanger-slot": (AMBIGUITY, "a slot in a hanger flange, whose orientation the design does not fix"),
    "filler-thickness": (AMBIGUITY, "fillers declared without a thickness"),
    "impossible-layout": (COVERAGE, "a bolt line off its angle leg, which only Petra's geometry modes see"),
    "petra-only": (COVERAGE, "a limit state Petra checks and the twin does not"),
    "unclassified": ("unclassified", "no rule claims it"),
}

FU = {"steel.A36": 58.0, "steel.A572_50": 65.0, "steel.A992": 65.0}
"""Fu in ksi of the plate grades the gate draws (ASTM A36, A572 Gr. 50, A992)."""
FNV = {("bolt_group.120", "included"): 54.0, ("bolt_group.120", "excluded"): 68.0,
       ("bolt_group.150", "included"): 68.0, ("bolt_group.150", "excluded"): 84.0}
"""Fnv in ksi, Table J3.2."""
ROUND_HOLE = {"std": {0.75: 13 / 16, 0.875: 15 / 16, 1.0: 9 / 8}, "ovs": {0.75: 15 / 16, 0.875: 17 / 16, 1.0: 5 / 4}}
"""Hole diameters in inches, Table J3.3."""


def _number(text: str, key: str) -> float:
    return float(re.search(rf"^\s*{key} ([0-9.]+)", text, re.M).group(1))


def _instantaneous_centre(pts: list[tuple[float, float]], e: float) -> tuple[float, list[float]]:
    """Manual Part 7's IC for a vertical load e right of the centroid of a group symmetric about
    its horizontal centroid line: the centre x0 < 0 on that line, and each bolt's R / Rult."""
    def terms(x0: float) -> tuple[list[float], list[float]]:
        rs = [((x - x0) ** 2 + y * y) ** 0.5 for x, y in pts]
        return rs, [(1 - 2.718281828459045 ** (-10 * 0.34 * r / max(rs))) ** 0.55 for r in rs]

    def balance(x0: float) -> float:
        rs, f = terms(x0)
        return sum(fi * r for fi, r in zip(f, rs)) - (e - x0) * sum(fi * (x - x0) / r for fi, r, (x, _) in zip(f, rs, pts))

    lo, hi = -1e4, -1e-9
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if balance(mid) > 0 else (mid, hi)
    return lo, terms(lo)[1]


def bracket_tearout(card: str, text: str) -> float | None:
    """A bolt bracket's worst bolt by the IC method, each bolt's tearout clear distance taken
    along its own force (J3.11a) to the plate's back, top or bottom edge or the next hole; the
    plate runs on toward the load. Round holes only; None for a slotted plate."""
    if corners(card, text):
        found = [bracket_tearout(*corner) for corner in corners(card, text)]
        return None if None in found else max(found)
    m = re.search(r"^\s*holes .*\bplate (\w+)", text, re.M)
    kind = m.group(1) if m else "std"
    if kind not in ROUND_HOLE:
        return None
    grade, t = re.search(r"^\s*plate (steel\.\w+) thickness ([0-9.]+)", text, re.M).groups()
    group, d, threads = re.search(r"bolts (bolt_group\.\d+) diameter ([0-9.]+) inch threads (\w+)", text).groups()
    t, d, fu = float(t), float(d), FU[grade]
    half = ROUND_HOLE[kind][d] / 2
    phi = 0.75 if "basis lrfd" in text else 0.5
    kb, kt = (3.0, 1.5) if "deformation not_considered" in text else (2.4, 1.2)
    rows, cols = int(_number(text, "rows")), int(_number(text, "columns"))
    s, g, e = _number(text, "pitch"), _number(text, "gauge"), _number(text, "eccentricity")
    lev, leh = _number(text, "edge_vertical"), _number(text, "plate_edge")
    load = float(re.search(r"shear in \[0 kip, ([0-9.]+) kip\]", card).group(1))
    pts = [(j * g - (cols - 1) * g / 2, (rows - 1) * s / 2 - i * s) for i in range(rows) for j in range(cols)]
    back, top, bottom = -(cols - 1) * g / 2 - leh, (rows - 1) * s / 2 + lev, -(rows - 1) * s / 2 - lev
    x0, share = _instantaneous_centre(pts, e)
    c = sum(f * (x - x0) / ((x - x0) ** 2 + y * y) ** 0.5 for f, (x, y) in zip(share, pts))
    shear = FNV[(group, threads)] * 3.141592653589793 * d * d / 4
    worst = 0.0
    for f, (x, y) in zip(share, pts):
        r = ((x - x0) ** 2 + y * y) ** 0.5
        ux, uy = -y / r, (x - x0) / r
        reach = [(x - back) / -ux] if ux < 0 else []
        reach += [(top - y) / uy] if uy > 0 else [(y - bottom) / -uy] if uy < 0 else []
        lc = min(reach) - half if reach else float("inf")
        for qx, qy in pts:
            along = (qx - x) * ux + (qy - y) * uy
            if along > 0 and abs((qy - y) * ux - (qx - x) * uy) < 2 * half:
                lc = min(lc, along - 2 * half)
        rn = phi * min(shear, kb * d * t * fu, kt * lc * t * fu)
        worst = max(worst, load * f / c / rn)
    return worst


def cause_of(row: dict, mode: dict) -> str:
    """The cause of one limit state on opposite sides of 1 (module comment above)."""
    kind, text, name, outcome = row["kind"], row["text"], mode["mode"], mode["outcome"]
    rows_m = re.search(r"^\s*rows (\d+)", text, re.M)
    if name == "block_shear" and outcome == "petra_fail":
        if mode["petra_u"] == float("inf"):
            return "impossible-layout"
        k = re.search(r"block of (\d+) row", mode["petra_check"] or "")
        if k and rows_m and int(k.group(1)) < int(rows_m.group(1)):
            return "partial-block"
    if name == "shear_rupture" and outcome == "petra_fail" and kind == "double_angle" \
            and (mode["petra_check"] or "").startswith("beam web") and "\n  cope " not in text:
        return "uncoped-web-rupture"
    if name in ("bolts", "slip", "weld") and outcome == "petra_fail":
        if kind == "double_angle":
            return "filler-thickness" if re.search(r"fillers (one|two)", text) else "unclassified"
        if kind in ("shear_tab", "shear_tee", "single_angle", "bolt_bracket", "weld_bracket"):
            return "eccentric-method"
    if kind == "bolt_bracket" and name == "bolts" and outcome == "twin_fail":
        u = bracket_tearout(row["card"], text)
        if u is None:
            return "slot-in-tearout"
        return "tearout-direction" if fails(u) else "bracket-least-edge"
    if kind == "weld_bracket" and name == "bracket_edge" and outcome == "twin_fail" and "weld_return" in text:
        return "weld-arm"
    if kind == "hanger" and name == "prying":
        if outcome == "petra_fail" and "shear in" in row["card"]:
            return "prying-shear"
        if re.search(r"^\s*holes .*\b(ssl|lsl)\b(?!_)", text, re.M):
            return "hanger-slot"
    if kind in ("double_angle", "shear_end_plate") and name == "bolts" and outcome == "twin_fail":
        return "web-end-bolt"
    return "unclassified"


def compact(row: dict) -> dict:
    """One design's line of the committed log: both verdicts, each shared limit state, and the
    cause of every disagreement. The design and its card are left out; the seed regenerates them."""
    c = compare(row)
    out = {k: c[k] for k in ("name", "kind", "petra", "twin", "via", "free", "toleranced", "cyclic")}
    out["expected"] = row["expected"]
    out["seconds"] = {k: round(v, 4) for k, v in row["seconds"].items()}
    if c["twin"] not in ("PASS", "FAIL"):
        return {**out, "reason": c["reason"]}

    def r4(u: float) -> float | str:
        return "inf" if u == float("inf") else round(u, 4)

    disagree = [m for m in c["modes"] if m["outcome"] in ("twin_fail", "petra_fail")]
    causes = {m["mode"]: cause_of(row, m) for m in disagree}
    out["modes"] = [[m["mode"], m["outcome"], r4(m["petra_u"]), r4(m["twin_u"])] + ([causes[m["mode"]]] if m["mode"] in causes else [])
                    for m in c["modes"]]
    out["petra_only_failed"], out["twin_only"] = c["petra_only_failed"], c["twin_only"]
    out["governing"] = [c["governing"]["petra"], c["governing"]["twin"]]
    if c["petra"] != c["twin"]:
        side = "petra_fail" if c["petra"] == "FAIL" else "twin_fail"
        found = [causes[m["mode"]] for m in disagree if m["outcome"] == side]
        if side == "petra_fail" and c["petra_only_failed"]:
            found.append("petra-only")
        out["verdict_causes"] = sorted(set(found)) or ["unclassified"]
    return out


# --- The tables of docs/twin_check.md -----------------------------------------------------

KINDS = ("shear_tab", "double_angle", "shear_end_plate", "single_angle", "shear_tee", "seated",
         "bolt_bracket", "weld_bracket", "hanger", "stiffened_seat", "flange_force")


def table(head: list[str], body: list[list]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(str(x) for x in r) + " |" for r in body]


def render(rows: list[dict]) -> list[str]:
    out = [f"{len(rows)} designs.", ""]
    status = Counter(r["twin"] if r["twin"] not in ("PASS", "FAIL") else "checked" for r in rows)
    reasons = Counter((r["kind"], r["reason"]) for r in rows if r["twin"] not in ("PASS", "FAIL"))
    out += table(["twin status", "designs"], [[k, v] for k, v in sorted(status.items())]) + [""]
    out += table(["kind", "twin status", "reason", "designs"], [[k, "unsupported", why[:90], n] for (k, why), n in sorted(reasons.items())]) + [""]
    out += [f"Read at the two ends of a toleranced length: {sum(r['via'] == 'corners' for r in rows)} designs.", ""]

    checked = [r for r in rows if r["twin"] in ("PASS", "FAIL")]
    pairs = Counter((r["kind"], r["petra"], r["twin"]) for r in checked)
    body = [[k] + [pairs[(k, p, t)] for p, t in (("PASS", "PASS"), ("FAIL", "FAIL"), ("FAIL", "PASS"), ("PASS", "FAIL"))]
            for k in KINDS if any(r["kind"] == k for r in checked)]
    body.append(["all"] + [sum(x[i] for x in body) for i in range(1, 5)])
    out += table(["kind", "both PASS", "both FAIL", "Petra FAIL, twin PASS", "Petra PASS, twin FAIL"], body) + [""]

    gov = Counter((r["kind"], r["governing"][0] == r["governing"][1]) for r in checked)
    out += table(["kind", "same governing limit state", "another"], [[k, gov[(k, True)], gov[(k, False)]] for k in KINDS if gov[(k, True)] + gov[(k, False)]]) + [""]

    states = Counter((r["kind"], m[0], m[1]) for r in checked for m in r["modes"])
    body = [[k, m] + [states[(k, m, o)] for o in OUTCOMES] for k, m in sorted({(k, m) for k, m, _ in states}, key=lambda x: (KINDS.index(x[0]), x[1]))]
    out += table(["kind", "limit state", "agree", "apart", "twin fails, Petra holds", "Petra fails, twin holds"], body) + [""]

    by_cause: dict[str, Counter] = defaultdict(Counter)
    examples: dict[str, list[str]] = defaultdict(list)
    for r in checked:
        for m in r["modes"]:
            if len(m) > 4:
                by_cause[m[4]][m[1]] += 1
                if len(examples[m[4]]) < 3 and r["name"] not in examples[m[4]]:
                    examples[m[4]].append(r["name"])
        for cause in r.get("verdict_causes", []):
            by_cause[cause]["verdict"] += 1
            if len(examples[cause]) < 3 and r["name"] not in examples[cause]:
                examples[cause].append(r["name"])
    body = [[CAUSES[k][0], f"`{k}`", CAUSES[k][1], v["twin_fail"], v["petra_fail"], v["verdict"], ", ".join(examples[k])]
            for k, v in sorted(by_cause.items(), key=lambda kv: (list(CAUSES).index(kv[0])))]
    out += table(["class", "cause", "what differs", "twin fails, Petra holds", "Petra fails, twin holds", "verdicts it splits", "examples"], body) + [""]

    only = Counter((r["kind"], m) for r in checked for m in r["petra_only_failed"])
    solo = Counter(m for r in checked if r.get("verdict_causes") == ["petra-only"] for m in r["petra_only_failed"])
    by_mode = Counter(m for (_, m) in only.elements())
    out += table(["Petra-only failed mode", "designs", "of which the verdict's only cause"],
                 [[m, n, solo[m]] for m, n in by_mode.most_common()]) + [""]
    twin_only = Counter((r["kind"], m) for r in checked for m in r["twin_only"])
    out += table(["kind", "twin-only limit state", "designs"], [[k, m, n] for (k, m), n in sorted(twin_only.items())]) + [""]

    secs = {k: sum(r["seconds"][k] for r in rows) / len(rows) for k in ("generate", "petra", "twin")}
    out += [f"Mean seconds per design: generate {secs['generate']:.3f}, Petra {secs['petra']:.3f}, twin {secs['twin']:.4f}."]
    unclassified = sum(v for k, c in by_cause.items() if k == "unclassified" for v in c.values())
    out += [f"Unclassified disagreements: {unclassified}."]
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="the clean-room twin against Petra on the steel gate stream")
    parser.add_argument("--n", type=int, default=10000)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--rows", type=Path, help="a log this script wrote, compact or --full; print its tables without running")
    parser.add_argument("--log", type=Path, default=ROOT / "docs" / "twin_check_log.jsonl")
    parser.add_argument("--full", type=Path, help="also write each design, its card and both readings here")
    args = parser.parse_args(argv)
    if args.rows:
        rows = [json.loads(line) for line in args.rows.read_text(encoding="utf-8").splitlines() if line.strip()]
        if rows and "text" in rows[0]:
            rows = [compact(r) for r in rows]
            args.log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
    else:
        start = time.time()
        step = 25
        jobs = [(args.seed, i, min(step, args.start + args.n - i)) for i in range(args.start, args.start + args.n, step)]
        full = []
        with Pool(args.workers) as pool:
            for done, part in enumerate(pool.imap(chunk, jobs), 1):
                full.extend(part)
                if done % 20 == 0:
                    print(f"{len(full)} designs, {time.time() - start:.0f} s", flush=True)
        print(f"wall {time.time() - start:.0f} s with {args.workers} workers", flush=True)
        if args.full:
            args.full.write_text("".join(json.dumps(r) + "\n" for r in full), encoding="utf-8", newline="\n")
        rows = [compact(r) for r in full]
        args.log.parent.mkdir(parents=True, exist_ok=True)
        args.log.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
    print("\n".join(render(rows)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
