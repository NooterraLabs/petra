"""The coped-beam test check (scripts/coped_beam_check.py, docs/coped_beam_check.md).

Offline: nothing here runs a linear program. The doc's tables come from the committed log.
"""
from __future__ import annotations

import contextlib
import dataclasses
import importlib.util
import io
import sys
import unittest
from pathlib import Path

from petra.models.steel import blockshear as B
from petra.registry import build_registry

ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location("coped_beam_check", ROOT / "scripts" / "coped_beam_check.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["coped_beam_check"] = module
    spec.loader.exec_module(module)
    return module


cb = _load()
REGISTRY = build_registry()
CONSTANTS = cb.constants(REGISTRY)
DATA, SPECIMENS = cb.load_data()


class J43(unittest.TestCase):
    def test_every_block_agrees_with_the_deck_on_every_meshed_specimen(self):
        meshed = [sp for sp in SPECIMENS if sp.meshable]
        self.assertGreaterEqual(len(meshed), 18)
        for sp in meshed:
            plate = cb.plate(sp)
            even = dataclasses.replace(sp, pitches=(plate.pitch,) * len(sp.pitches))
            mine = {(b.k, b.j): b for b in cb.blocks(even, CONSTANTS)}
            claim = B.j4_3(plate, cb.Measured(REGISTRY, sp))
            self.assertEqual(set(mine), {(b.k, b.j) for b in claim.blocks}, sp.id)
            scale = B.INCH * sp.t
            for theirs in claim.blocks:
                ours = mine[(theirs.k, theirs.j)]
                self.assertEqual((theirs.agv * scale, theirs.anv * scale, theirs.ant * scale, theirs.ubs),
                                 (ours.agv, ours.anv, ours.ant, ours.ubs), f"{sp.id} block {theirs.k}x{theirs.j}")
                self.assertEqual(theirs.group * scale, ours.force, f"{sp.id} block {theirs.k}x{theirs.j}")
            self.assertEqual(cb.j4_3(even, CONSTANTS)[1], cb.j4_3(sp, CONSTANTS)[1], f"{sp.id}: the mean pitch moved the whole block")

    def test_the_deck_value_is_never_above_the_whole_block(self):
        for sp in SPECIMENS:
            governing, whole = cb.j4_3(sp, CONSTANTS)
            self.assertLessEqual(governing.force, whole.force, sp.id)

    def test_ricles_and_yura_round_holes_reproduce_the_published_aisc_values(self):
        published = DATA["checks"]["idea_aisc_kip"]["values"]
        checked = 0
        for sp in SPECIMENS:
            if sp.id in published and sp.slot is None:
                _, whole = cb.j4_3(sp, CONSTANTS)
                self.assertAlmostEqual(float(whole.force / cb.KIP), published[sp.id], delta=0.06, msg=sp.id)
                checked += 1
        self.assertEqual(checked, 6)

    def test_a_slotted_tension_plane_loses_the_slot_length(self):
        slotted = next(sp for sp in SPECIMENS if sp.slot is not None)
        round_ = dataclasses.replace(slotted, slot=None)
        _, a = cb.j4_3(slotted, CONSTANTS)
        _, b = cb.j4_3(round_, CONSTANTS)
        self.assertEqual(b.ant - a.ant, slotted.t * (slotted.slot - slotted.hole) * 3 / 2)
        self.assertEqual(a.agv, b.agv)


class Doc(unittest.TestCase):
    def test_the_doc_quotes_the_report(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cb.main(["report"])
        doc = (ROOT / "docs" / "coped_beam_check.md").read_text(encoding="utf-8")
        missing = [line for line in out.getvalue().splitlines() if line.startswith("|") and line not in doc]
        self.assertEqual(missing, [], "docs/coped_beam_check.md drifted from `coped_beam_check.py report`")


if __name__ == "__main__":
    unittest.main()
