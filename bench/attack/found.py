"""A difference kept as a small folder that reproduces it with one command, and that command.

    python3.11 -m bench.attack.repro DIR

reads the folder and runs the same readers on the same input, prints what each said and the
differences, and exits 1 when there is one. The folder holds the input (`design.petra` and
`design.card` for a pair the language reads, the kernel's files otherwise), `case.json` with
what was done to make it, and `run.sh` that asks the kernel and the third reading by hand.
A relation keeps the input it was taken from in `base/`.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from . import bind, meta, readers
from .readers import Diff, Judged

ROOT = Path(__file__).resolve().parents[2]
DECKS = ROOT / "petra" / "decks"


def _write(folder: Path, draft, judged: Judged) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    if draft.spec is not None:
        card, design = draft.texts()
        (folder / "design.card").write_text(card, encoding="utf-8", newline="\n")
        (folder / "design.petra").write_text(design, encoding="utf-8", newline="\n")
    files = draft.files or judged.files
    for name, body in (files or {}).items():
        if name == "rules" and draft.shipped:
            continue
        (folder / f"{name}.json").write_bytes(body.encode("utf-8", "surrogatepass"))
    if not draft.shipped:
        (folder / "rules.json").write_bytes(draft.deck_text.encode("utf-8", "surrogatepass"))
    if isinstance(draft.run, str) and draft.run != bind.AUTO and "run" not in (files or {}):
        (folder / "run.json").write_bytes(draft.run.encode("utf-8", "surrogatepass"))


def keep(out: Path, draft, judged: Judged, diff: Diff, base=None, base_judged: Judged | None = None, seed: int = 0) -> bool:
    """Write the folder for a difference, once. Returns True when it is new, and counts it when it is not."""
    folder = out / "found" / f"{diff.kind}-{diff.sig()}"
    try:
        folder.mkdir(parents=True)
    except FileExistsError:
        meta_file = folder / "case.json"
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            data["count"] = data.get("count", 1) + 1
            meta_file.write_text(json.dumps(data, indent=1), encoding="utf-8")
        except (OSError, ValueError):
            pass
        return False
    _write(folder, draft, judged)
    if base is not None and base_judged is not None:
        _write(folder / "base", base, base_judged)
        (folder / "base" / "case.json").write_text(json.dumps({"language": base.spec is not None, "deck": base.deck_name if base.shipped else None, "kind": "base", "where": "", "recipe": base.recipe, "notes": base.notes[:6], **({"run": "none"} if base.run is None else {})}), encoding="utf-8")
    case = {"sig": diff.sig(), "kind": diff.kind, "where": diff.where, "detail": diff.detail, "recipe": draft.recipe, "notes": draft.notes[:12], "deck": draft.deck_name if draft.shipped else None,
            "relation": draft.relation[0] if draft.relation else None, "extra": {k: v for k, v in draft.extra.items()}, "verdicts": judged.verdict, "seed": seed, "count": 1,
            "language": draft.spec is not None, **({"run": "none"} if draft.run is None else {})}
    (folder / "case.json").write_text(json.dumps(case, indent=1, ensure_ascii=True), encoding="utf-8")
    write_run_sh(folder, draft.deck_name if draft.shipped else None)
    return True


def write_run_sh(folder: Path, shipped: str | None) -> None:
    """The script that asks the kernel and the third reading by hand, then all the readers through the attacker."""
    rules = f'"$ROOT/petra/decks/{shipped}.json"' if shipped else "rules.json"
    names = [n for n in ("card", "design", "deck") if (folder / f"{n}.json").exists()]
    args = " ".join(f"--{n} {n}.json" for n in names) + f" --rules {rules}"
    args += "".join(f" --{n} {n}.json" for n in ("run", "proofs") if (folder / f"{n}.json").exists())
    (folder / "run.sh").write_text(
        "#!/bin/sh\n# The kernel and the third reading on the files of this folder, then the readers through the attacker.\n"
        'cd "$(dirname "$0")"\nROOT=${PETRA_ROOT:-$(git rev-parse --show-toplevel)}\n'
        f'"${{PETRA_VERIFY:?set PETRA_VERIFY to petra-verify}}" {args}\nnode "$ROOT/bench/twin/verify.mjs" {args}\n'
        '(cd "$ROOT" && python3.11 -m bench.attack.repro "$OLDPWD")\n', encoding="utf-8")


def _text(path: Path) -> str:
    return path.read_bytes().decode("utf-8", "surrogatepass")


def load(folder: Path):
    """The pieces of a kept folder: the case, the pair or the files, the deck's text and the run it is read with
    (the folder's run.json, bind.AUTO for the honest run of a folder that keeps none, or None for a case kept with none)."""
    case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    deck_text = _text(folder / "rules.json") if (folder / "rules.json").exists() else (DECKS / f"{case['deck'] or 'aisc360'}.json").read_text(encoding="utf-8")
    run = _text(folder / "run.json") if (folder / "run.json").exists() else None if case.get("run") == "none" else bind.AUTO
    pair = None
    files = None
    if (folder / "design.petra").exists():
        pair = ((folder / "design.card").read_text(encoding="utf-8"), (folder / "design.petra").read_text(encoding="utf-8"))
    names = [n for n in ("card", "design", "deck", "run", "proofs") if (folder / f"{n}.json").exists()]
    if names:
        files = {n: _text(folder / f"{n}.json") for n in names}
        files["rules"] = deck_text
    return case, pair, files, deck_text, run


def judge_folder(folder: Path) -> tuple[dict, Judged]:
    case, pair, files, deck_text, run = load(folder)
    if case.get("language") and pair:
        base_text = None if case["deck"] else (DECKS / "aisc360.json").read_text(encoding="utf-8")
        j = readers.judge(pair[0], pair[1], deck_text, base_text, cli=True, run=run)
    else:
        j = readers.judge_files(files or {})
    return case, j


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="run a kept difference again")
    ap.add_argument("folder", nargs="?", default=".")
    ap.add_argument("--twin", default=None, help="the third reading, such as bench/twin/verify.mjs; default readers.Config.twin")
    args = ap.parse_args(argv)
    folder = Path(args.folder).resolve()
    if os.environ.get("PETRA_VERIFY"):
        readers.Config.kernel = os.environ["PETRA_VERIFY"]
    if args.twin:
        readers.Config.twin = args.twin
    case, j = judge_folder(folder)
    print(f"{folder.name}: {case['kind']} at {case['where']}, found by the {case['recipe']} recipe")
    print("  made as:", "; ".join(case.get("notes", [])[:6]) or "-")
    print("  kept:", case.get("detail", "")[:300])
    print("  verdicts then:", ", ".join(f"{k} {v}" for k, v in case.get("verdicts", {}).items()) or "-")
    print("  verdicts:", ", ".join(f"{k} {v}" for k, v in j.verdict.items()) or j.outcome)
    if j.findings:
        print("  the kernel's findings:", sorted({(f.get("file"), f.get("rule")) for f in j.findings})[:8])
    if not readers.Config.twin:
        print("  the third reading is not asked (readers.Config.twin): a difference with it cannot show here")
    diffs = list(j.diffs) + bind.expected(case.get("extra") or {}, j)
    if case.get("relation") and (folder / "base").exists():
        bcase, bj = judge_folder(folder / "base")
        print("  base verdicts:", ", ".join(f"{k} {v}" for k, v in bj.verdict.items()))
        rel = case["relation"]
        if rel in ("units", "units_si"):
            diffs += [Diff("bundle", "grid", f"{n} differs between the two spellings") for n in ("card", "design") if (bj.files or {}).get(n) != (j.files or {}).get(n)]
        elif rel == "rename":
            diffs += meta.same(bj, j, "rename", case["extra"].get("rename"))
        elif rel in ("reorder", "json", "respell"):
            diffs += meta.same(bj, j, rel, ordered=False)
        elif rel == "bind_same":
            diffs += meta.same(bj, j, "bind")
        elif rel in ("load_up", "load_down"):
            diffs += meta.load_check(bj, j, case["extra"].get("up", True))
        elif rel == "stronger":
            diffs += meta.stronger_check(bj, j)
        elif rel == "hints":
            diffs += meta.hints_check(bj, j)
    for d in diffs:
        print(f"  {d.kind} ({d.where}): {d.detail[:400]}")
    print(f"  {len(diffs)} difference(s)" if diffs else "  no difference: this does not reproduce")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
