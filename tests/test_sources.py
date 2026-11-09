"""Petra's values against the standards they come from (docs/sources).

scripts/source_inventory.py lists every value, equation and rule Petra takes from a
standard. scripts/source_anchors.py bound each one to the text that states it, from a
reading taken with Petra's values hidden. These tests hold the two together:

  - without the documents, the registry must hold each anchor's value, so a changed
    constant fails here until someone reads it again;
  - with the documents (the folder PETRA_SOURCES names, else docs/research/sources), every
    anchor's document, span fingerprint and printed value must still be there. Public CI
    has no documents, and those tests skip.

Each disagreement the second reading found is a test below with its finding in the
docstring. A method question stays an expected failure until someone decides it.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return sys.modules[name]


inv = _script("source_inventory")
vs = _script("verify_sources")
anchoring = _script("source_anchors")

from petra.registry import build_registry  # noqa: E402

KEYS = {"id", "kind", "doc", "doc_sha256", "page", "span", "span_sha256", "printed", "value", "label", "read",
        "cell", "agrees", "finding", "reason"}


class Inventory(unittest.TestCase):
    def test_the_committed_inventory_is_current(self):
        current = inv.OUT.read_text(encoding="utf-8")
        self.assertEqual(current, inv.render(inv.inventory()),
                         "docs/sources/inventory.jsonl is stale: run py -3.11 scripts/source_inventory.py, "
                         "then anchor any new item")


class Anchors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = {i["id"]: i for i in inv.read()}
        cls.anchors = vs.read_anchors()
        cls.registry = build_registry()

    def test_every_item_has_one_anchor(self):
        ids = [a["id"] for a in self.anchors]
        self.assertEqual(len(ids), len(set(ids)), "an item is anchored twice")
        self.assertEqual(sorted(set(self.items) - set(ids)), [], "items without an anchor")
        self.assertEqual(sorted(set(ids) - set(self.items)), [], "anchors for items the inventory no longer has")

    def test_the_registry_holds_what_the_sources_state(self):
        """A value changed in the registry or the code fails here until it is read again."""
        wrong = []
        for a in self.anchors:
            if a.get("value") is None:
                continue
            held = anchoring.petra_value(self.registry, self.items[a["id"]])
            if held != vs.value(a["value"]):
                wrong.append(f"{a['id']}: Petra holds {held}, the source states {a['value']} ({a['doc']} {a['page']})")
        self.assertEqual(wrong, [])

    def test_every_anchored_rule_and_equation_agrees(self):
        """Equations and rules have no single number; the second reading judged each."""
        self.assertEqual([f"{a['id']}: {a.get('finding', '')}" for a in self.anchors if a.get("agrees") is False], [])

    def test_anchors_carry_no_document_text(self):
        """Fingerprints and numbers only: no field holds a span of a standard's prose."""
        for a in self.anchors:
            self.assertLessEqual(set(a), KEYS, a["id"])
            self.assertIn(a["kind"], vs.KINDS, a["id"])
            for field in ("printed", "read", "label", "cell"):
                self.assertLessEqual(len(a.get(field) or ""), 120, f"{a['id']}.{field}")

    def test_every_reading_kind_says_where_or_why(self):
        for a in self.anchors:
            if a["kind"] in ("text", "visual", "cell"):
                self.assertTrue(a["doc_sha256"] and a["span_sha256"] and a["page"], a["id"])
            if a["kind"] == "visual":
                self.assertTrue(a.get("label") and a.get("read"), a["id"])
            if a["kind"] == "absent":
                self.assertTrue(a.get("reason"), a["id"])


class Documents(unittest.TestCase):
    """The documents against the anchors. Skips without them."""

    @classmethod
    def setUpClass(cls):
        cls.folder = vs.sources_dir()
        anchors = vs.read_anchors()
        needed = sorted({a["doc"] for a in anchors if a["kind"] in ("text", "visual", "cell")})
        missing = [d for d in needed if not (cls.folder / d).exists()]
        if missing:
            raise unittest.SkipTest(f"source documents not found in {cls.folder}: {', '.join(missing)}. Set "
                                    f"{vs.ENV} to the folder that holds them to check the anchors; public CI has none")
        try:
            import pypdf  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("pypdf is not installed; the anchors were made with pypdf 5.1.0")
        cls.anchors = anchors

    def test_every_anchor_holds_in_its_document(self):
        failed = vs.verify(self.anchors, self.folder)
        self.assertEqual(failed, {}, "\n".join(f"{k}: {'; '.join(p)}" for k, p in failed.items()))

    def test_chapters_j_and_k_number_what_equations_json_says(self):
        """Its headings and equation labels are AISC 360-22's, page by page."""
        self.assertEqual(vs.equation_problems(vs.read_equations(), self.folder), [])


class Traceability(unittest.TestCase):
    """docs/steel_traceability.md and docs/steel_connections.md §4 against their sources."""

    @classmethod
    def setUpClass(cls):
        cls.docs = _script("source_docs")

    def test_the_generated_docs_are_current(self):
        connections = self.docs.CONNECTIONS.read_text(encoding="utf-8")
        for path, text in ((self.docs.TRACEABILITY, self.docs.traceability()),
                           (self.docs.CONNECTIONS, self.docs.connections(connections))):
            self.assertEqual(path.read_text(encoding="utf-8"), text,
                             f"{path.relative_to(ROOT)} is stale: run py -3.11 scripts/source_docs.py")

    def test_the_trace_has_every_heading_of_chapters_j_and_k(self):
        """trace.py's provisions are the standard's headings: none missing, none extra. A
        heading the trace does not list is a chapter, a parent of listed parts (J3.11), or a
        part of a listed provision (J2.1a, K3.2)."""
        headings = [h for h, _ in vs.read_equations()["headings"]]
        self.assertEqual([s for s in self.docs.JK if s not in headings], [], "provisions with no heading")
        listed = set(self.docs.JK)
        def parent(h: str) -> bool:
            return any(s.startswith(h + ".") or (s.startswith(h) and s[len(h):].isalpha()) for s in listed)

        extra = [h for h in headings if h not in listed and not parent(h) and not self.docs.resolve(h)]
        self.assertEqual(extra, [], "headings the trace does not list")

    def test_no_excluded_provision_has_values(self):
        """A value whose clause names an excluded provision is data no check reads, or a wrong
        citation."""
        named, _ = self.docs.values_by_provision()
        self.assertEqual({s: [x["id"] for x in named[s]] for s in self.docs.IDS
                          if self.docs.TREATMENT[s] == "excluded" and named[s]}, {})


class Findings(unittest.TestCase):
    """What the second reading found that the first did not: one test per finding."""

    @classmethod
    def setUpClass(cls):
        cls.registry = build_registry()

    def source(self, key: str) -> str:
        fact = self.registry.fact(key)
        return getattr(fact, "source", None) or fact.standard

    def test_the_no_prying_thickness_cites_manual_eq_9_30a(self):
        """fatigue.py and vocab.py cite Manual Eq. 9-20a for tmin = sqrt(4 T b' / (phi p Fu)).
        The Companion (P901 pp. 562, 920) labels that form Eq. 9-30a; 9-20a is the coped
        beam's f = 2(c/d) (P901 p. 612)."""
        ids = {i["id"] for i in inv.read()}
        self.assertNotIn("eq.manual.9-20a", ids)
        self.assertIn("eq.manual.9-30a", ids)
        self.assertNotIn("9-20a", (ROOT / "petra" / "models" / "steel" / "vocab.py").read_text(encoding="utf-8"))

    def test_flexural_yielding_omega_cites_f1a(self):
        """aisc360.j4_5.omega_y cites Section F1(b). Omega_b = 1.67 is in F1(a), beside phi_b
        (A360 p. 120); F1(b) is the rotational restraint at supports."""
        self.assertIn("Section F1(a)", self.source("const.aisc360.j4_5.omega_y"))

    def test_bearing_and_tearout_cite_their_subitems(self):
        """The J3.11a rows cite (1)(i) and (1)(ii). Section J3.11a(1) splits into (a) bearing
        and (b) tearout, each with (i) and (ii) (A360 pp. 211-212)."""
        for key, clause in (("bearing_considered", "J3.11a(1)(a)(i)"), ("bearing_not_considered", "J3.11a(1)(a)(ii)"),
                            ("tearout_considered", "J3.11a(1)(b)(i)"), ("tearout_not_considered", "J3.11a(1)(b)(ii)"),
                            ("bearing_lsl_perpendicular", "J3.11a(2)(a)"),
                            ("tearout_lsl_perpendicular", "J3.11a(2)(b)")):
            self.assertIn(clause, self.source(f"const.aisc360.j3_11a.{key}"), key)

    @unittest.expectedFailure
    def test_group_200_bolts_have_their_own_pretension(self):
        """Method question. checks.py and twin.py take Group 150's pretension for Group 200
        bolts. Table J3.1 (A360 p. 204) gives Group 200 Grade 2 its own column: 90, 113 and
        143 kips at 1, 1-1/8 and 1-1/4 in., and no value at other sizes."""
        for size in ("1", "1_1_8", "1_1_4"):
            self.registry.fact(f"const.bolt_us.{size}.Tm_g200")

    @unittest.expectedFailure
    def test_rcsc_rows_cite_the_edition_aisc_360_22_references(self):
        """Provenance question. Petra cites the RCSC Specification 2025 edition, which is not
        on disk. AISC 360-22 Section A2 (A360 p. 74) references the 2020 edition. Every RCSC
        value Petra holds agrees with AISC 360-22's own statement of it."""
        rcsc = [i["id"] for i in inv.read() if i["edition"] == "RCSC 2025"]
        self.assertEqual(rcsc, [])


if __name__ == "__main__":
    unittest.main()
