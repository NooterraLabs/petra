"""Makeable-set registry: lookups, derivations, provenance and deck files. Owner: G."""
import dataclasses
import json
import os
import tempfile
import unittest
from fractions import Fraction

from lola.kernel import Add, Const, Div, Interval, Mul, Neg, Pi, PowInt, Sym
from lola.premises import Tag
from lola.registry import (
    Constant,
    Corrosivity,
    DeckError,
    Derived,
    OutsideMakeableSet,
    Part,
    PartKind,
    Registry,
    Stated,
    build_deck,
    build_registry,
    read_deck,
    write_deck,
)
from lola.registry.constants import CONSTANTS, STATED

REGISTRY = build_registry()
DECK = None
MM2 = Fraction(1, 10**6)


def setUpModule():
    global DECK
    DECK = build_deck(REGISTRY)


def value(entry: str, prop: str) -> Interval:
    record = DECK.get(entry, prop)
    assert record is not None, f"deck has {entry}.{prop}"
    return record.value


def point(text: str, scale: Fraction = Fraction(1)) -> Interval:
    return Interval(Fraction(text) * scale, Fraction(text) * scale)


class Lookups(unittest.TestCase):
    def test_the_ids_the_example_designs_use_are_in_the_makeable_set(self):
        self.assertEqual(REGISTRY.material("steel.S355").standard, "EN 10025-2:2019")
        self.assertEqual(REGISTRY.material("aluminium.6061_T6").family, "aluminium")
        for pid, kind in (
            ("chs.60_3x3_2", PartKind.SECTION),
            ("chs.76_1x3_2", PartKind.SECTION),
            ("cable.cu_pvc_2_5", PartKind.CABLE),
            ("cable.cu_pvc", PartKind.CABLE),
            ("mcb.B16", PartKind.BREAKER),
            ("terminal.lever_4mm2_75C", PartKind.TERMINAL),
            ("bolt.M12_A4_70", PartKind.BOLT),
            ("bolt.M12_8_8_zn", PartKind.BOLT),
        ):
            self.assertEqual(REGISTRY.part(pid, kind).id, pid)
        self.assertEqual(REGISTRY.process("install.clipped_direct").id, "install.clipped_direct")
        marine = REGISTRY.environment("marine_c5")
        self.assertIs(marine.corrosivity, Corrosivity.C5)
        self.assertTrue(marine.wet, "a marine C5 environment is wet")
        self.assertFalse(REGISTRY.environment("indoor_dry").wet, "indoor_dry is dry")

    def test_ids_outside_the_makeable_set_are_refused(self):
        for lookup in (
            lambda: REGISTRY.material("steel.S999"),
            lambda: REGISTRY.part("bolt.M13_8_8", PartKind.BOLT),
            lambda: REGISTRY.process("install.buried"),
            lambda: REGISTRY.environment("lunar"),
            lambda: REGISTRY.property("steel.S355", "toughness"),
            lambda: REGISTRY.property("steel.S999", "fy"),
        ):
            with self.assertRaises(OutsideMakeableSet):
                lookup()

    def test_a_part_of_the_wrong_kind_is_refused(self):
        with self.assertRaisesRegex(OutsideMakeableSet, "breaker"):
            REGISTRY.part("mcb.B16", PartKind.CABLE)

    def test_building_the_registry_is_pure(self):
        self.assertEqual(build_registry(), REGISTRY)

    def test_every_entry_id_is_unique_across_kinds(self):
        ids = [*REGISTRY.materials, *REGISTRY.parts, *REGISTRY.processes, *REGISTRY.environments]
        self.assertEqual(len(ids), len(set(ids)))
        for table in (REGISTRY.materials, REGISTRY.parts, REGISTRY.processes, REGISTRY.environments):
            for key, entry in table.items():
                self.assertEqual(key, entry.id)


class Derivations(unittest.TestCase):
    def test_resistance_per_metre_is_resistivity_over_area(self):
        self.assertEqual(REGISTRY.expand("cable.cu_pvc_2_5", "R20"),
                         Div(Sym("const.cu.rho20"), Sym("const.iec60228.2_5.area")))

    def test_a_size_inherits_its_series_derivations(self):
        self.assertIs(REGISTRY.property("cable.cu_pvc_2_5", "R20"), REGISTRY.property("cable.cu_pvc", "R20"))
        self.assertEqual(REGISTRY.expand("cable.cu_pvc_2_5", "area"), Sym("const.iec60228.2_5.area"))

    def test_stress_area_is_iso_724_geometry_in_the_shape_of_the_design_certificate(self):
        d, p = Sym("const.iso261.M12.d"), Sym("const.iso261.M12.pitch")
        c2, c3 = Sym("const.iso724.d2_coefficient"), Sym("const.iso724.d3_coefficient")
        expected = Mul((Div(Pi(), Const(Fraction(4))), PowInt(Div(Add((
            Add((d, Neg(Mul((c2, p))))),
            Add((d, Neg(Mul((c3, p))))),
        )), Const(Fraction(2))), 2)))
        self.assertEqual(REGISTRY.expand("bolt.M12_A4_70", "As"), expected)
        for key, text in (
            ("const.iso261.M12.d", "3/250"),
            ("const.iso261.M12.pitch", "7/4000"),
            ("const.iso724.d2_coefficient", "649519/1000000"),
            ("const.iso724.d3_coefficient", "1226869/1000000"),
            ("bolt.M12_A4_70.Rp02_min", "450000000"),
        ):
            self.assertEqual(REGISTRY.fact(key).value, point(text), key)

    def test_a_stated_property_is_its_own_premise_key(self):
        self.assertEqual(REGISTRY.expand("bolt.M12_A4_70", "Rp02_min"), Sym("bolt.M12_A4_70.Rp02_min"))
        self.assertEqual(REGISTRY.expand("steel.S355", "E"), Sym("const.steel.E"))

    def test_proof_load_is_stated_proof_stress_times_derived_area(self):
        self.assertEqual(REGISTRY.expand("bolt.M12_8_8", "Fp"),
                         Mul((Sym("bolt.M12_8_8.Sp"), REGISTRY.expand("bolt.M12_8_8", "As"))))

    def test_a_family_supplies_the_parameters_its_series_leaves_open(self):
        area = Sym("par:area")
        self.assertEqual(REGISTRY.expand("cable.cu_pvc", "R20", {"area": area}), Div(Sym("const.cu.rho20"), area))
        with self.assertRaisesRegex(OutsideMakeableSet, "area"):
            REGISTRY.expand("cable.cu_pvc", "R20")

    def test_every_property_expands_to_premises_the_registry_resolves(self):
        templates = {p.series for p in REGISTRY.parts.values() if p.series}
        checked = 0
        for table in (REGISTRY.materials, REGISTRY.parts, REGISTRY.processes):
            for entry in table.values():
                if entry.id in templates:
                    continue
                inherited = REGISTRY.parts[entry.series].props if getattr(entry, "series", None) else {}
                for prop in {*entry.props, *inherited}:
                    for name in _syms(REGISTRY.expand(entry.id, prop)):
                        fact = REGISTRY.fact(name)
                        self.assertIsInstance(fact, (Constant, Stated), f"{entry.id}.{prop} -> {name}")
                    checked += 1
        self.assertGreater(checked, 300)

    def test_a_size_fixes_the_values_of_the_constants_it_names(self):
        sizes = [p for p in REGISTRY.parts.values() if p.series is not None]
        self.assertTrue(sizes, "the catalogue has size entries")
        for part in sizes:
            self.assertTrue(part.fixes, part.id)
            for param, fixed in part.fixes.items():
                self.assertEqual(REGISTRY.fact(REGISTRY.expand(part.id, param).name).value, fixed, f"{part.id}.{param}")

    def test_broken_derivations_are_refused(self):
        def registry(props):
            part = Part("x.part", PartKind.SECTION, "test part", "steel.S355", props)
            return Registry(CONSTANTS, {}, {"x.part": part}, {}, {})

        cyclic = registry({"a": Derived(Sym("self.b"), "1"), "b": Derived(Sym("self.a"), "1")})
        with self.assertRaisesRegex(ValueError, "cycle"):
            cyclic.expand("x.part", "a")
        with self.assertRaisesRegex(OutsideMakeableSet, "unknown constant"):
            registry({"a": Derived(Sym("const.unobtainium.E"), "Pa")}).expand("x.part", "a")
        with self.assertRaisesRegex(ValueError, "neither"):
            registry({"a": Derived(Sym("E"), "Pa")}).expand("x.part", "a")
        self.assertEqual(registry({"a": Derived(Sym("const.steel.E"), "Pa")}).expand("x.part", "a"), Sym("const.steel.E"))

    def test_fact_resolves_only_premise_keys(self):
        self.assertEqual(REGISTRY.fact("indoor_dry.ambient").value, Interval(Fraction(5), Fraction(40)))
        for key in ("cable.cu_pvc_2_5.R20", "const.unobtainium", "steel.S355.toughness", "nowhere.ambient"):
            with self.assertRaises(OutsideMakeableSet, msg=key):
                REGISTRY.fact(key)


class HandCalculations(unittest.TestCase):
    def test_wire_resistance_per_metre(self):
        self.assertEqual(value("cable.cu_pvc_2_5", "R20"), point("1/145"), "1 / (58e6 S/m * 2.5e-6 m2)")
        self.assertEqual(value("cable.cu_pvc_16", "R20"), point("1/928"), "1 / (58e6 S/m * 16e-6 m2)")

    def test_short_circuit_k_factor_for_copper_in_pvc(self):
        k = value("cable.cu_pvc_2_5", "k")
        self.assertGreater(k.lo, Fraction("114.7e6"),
                           "sqrt(3.45e6 * 254.5 * 58e6) = 225.67 A s0.5/mm2, times sqrt(ln(394.5 / 304.5)) = 114.84")
        self.assertLess(k.hi, Fraction("114.9e6"))

    def test_bolt_stress_area_and_proof_load(self):
        area = value("bolt.M12_8_8", "As")
        self.assertGreater(area.lo, Fraction("84.26") * MM2, "(pi/4) (10.863342 + 9.852979)^2 / 4 = 84.267 mm2")
        self.assertLess(area.hi, Fraction("84.28") * MM2)
        proof = value("bolt.M12_8_8", "Fp")
        self.assertGreater(proof.lo, Fraction("48870"), "580 MPa * 84.267 mm2 = 48875 N")
        self.assertLess(proof.hi, Fraction("48880"))
        self.assertIsNone(DECK.get("bolt.M12_A4_70", "Fp"), "ISO 3506-1 class 70 defines no proof stress")

    def test_circular_hollow_section(self):
        area, second = value("chs.60_3x3_2", "A"), value("chs.60_3x3_2", "I")
        self.assertGreater(area.lo, Fraction("574.0") * MM2, "(pi/4)(60.3^2 - 53.9^2) = 574.03 mm2")
        self.assertLess(area.hi, Fraction("574.1") * MM2)
        self.assertGreater(second.lo, Fraction("23.46e-8"), "(pi/64)(60.3^4 - 53.9^4) = 23.468 cm4")
        self.assertLess(second.hi, Fraction("23.48e-8"))

    def test_shear_modulus_spans_the_elastic_modulus_range(self):
        self.assertEqual(value("steel.S355", "G"),
                         Interval(Fraction(2000, 26) * 10**9, Fraction(2100, 26) * 10**9), "[200, 210] GPa / (2 * 1.3)")

    def test_breaker_conventional_currents(self):
        self.assertEqual(value("mcb.B16", "I_t"), point("23.2"), "1.45 * 16 A")
        self.assertEqual(value("mcb.B16", "I_nt"), point("18.08"), "1.13 * 16 A")


class Provenance(unittest.TestCase):
    def test_every_constant_and_stated_value_names_its_tag_owner_and_source(self):
        values = [(c.name, c.tag, c.owner, c.source) for c in CONSTANTS.values()]
        values += [(key, s.tag, s.owner, s.standard) for key, s in STATED.items()]
        for name, tag, owner, source in values:
            self.assertIn(tag, {Tag.SANCTIONED, Tag.MEASURED, Tag.JUDGED}, name)
            self.assertTrue(owner and source, name)
            if tag is Tag.JUDGED:
                self.assertEqual(owner, "lola-maintainers", f"{name}: a judged value is the maintainers' judgement")
                self.assertRegex(source, "recalled|judged", f"{name}: a judged source says why it is not sanctioned")
            else:
                self.assertNotEqual(owner, "lola-maintainers", f"{name}: a sanctioned value is owned by its standards body")

    def test_the_footprint_premises_of_the_design_resolve(self):
        steel_e = REGISTRY.fact("const.steel.E")
        self.assertEqual(steel_e.value, Interval(Fraction(200 * 10**9), Fraction(210 * 10**9)))
        self.assertIs(steel_e.tag, Tag.SANCTIONED)
        self.assertIn("EN 1993-1-1", steel_e.source)
        fy = REGISTRY.fact("steel.S355.fy")
        self.assertEqual(fy.value, point("355e6"))
        self.assertEqual(fy.standard, "EN 10025-2:2019 Table 7")

    def test_a_value_without_provenance_or_with_a_non_registry_tag_cannot_be_built(self):
        iv = point("1")
        Constant("x", iv, "1", Tag.SANCTIONED, "ISO", "ISO 1", "a fact")
        Stated(iv, "1", Tag.JUDGED, "lola-maintainers", "judged", "conditions")
        for build in (
            lambda: Constant("x", iv, "1", Tag.SANCTIONED, "ISO", "", "no source"),
            lambda: Constant("x", iv, "1", Tag.SANCTIONED, " ", "ISO 1", "no owner"),
            lambda: Constant("x", iv, "1", Tag.PROVED, "ISO", "ISO 1", "proved is the kernel's"),
            lambda: Constant("x", iv, "1", Tag.ASSUMED, "ISO", "ISO 1", "an owner's input, not a registry value"),
            lambda: Stated(iv, "1", Tag.SANCTIONED, "ISO", "", "no standard"),
            lambda: Stated(iv, "1", Tag.CERTIFIED, "ISO", "ISO 1", "certified is a kernel result"),
        ):
            with self.assertRaises(ValueError):
                build()


class DeckFiles(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "deck.json")

    def tearDown(self):
        self.dir.cleanup()

    def write_body(self, body) -> str:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(body, f)
        return self.path

    def good_record(self, **changes):
        record = {"entry": "chs.60_3x3_2", "prop": "A", "lo": "1/2", "hi": "3/4", "unit": "m2", "provenance": "derived:x"}
        record.update(changes)
        return record

    def test_a_written_deck_reads_back_identical_with_lf_line_endings(self):
        write_deck(DECK, self.path)
        self.assertEqual(read_deck(self.path), DECK)
        with open(self.path, "rb") as f:
            self.assertNotIn(b"\r\n", f.read())

    def test_the_shipped_deck_has_one_record_per_key_and_no_series_templates(self):
        keys = [(r.entry, r.prop) for r in DECK.records]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all("." not in prop for _, prop in keys))
        self.assertFalse(any(entry == "cable.cu_pvc" for entry, _ in keys), "a series is a template, not a part")
        self.assertIsNone(DECK.get("cable.cu_pvc_2_5", "toughness"))

    def test_a_valid_minimal_deck_parses(self):
        deck = read_deck(self.write_body({"format": "lola-deck/0", "records": [self.good_record()]}))
        self.assertEqual(deck.get("chs.60_3x3_2", "A").value, Interval(Fraction(1, 2), Fraction(3, 4)))

    def test_malformed_decks_are_refused(self):
        cases = {
            "float": {"format": "lola-deck/0", "records": [self.good_record(lo=0.5)]},
            "decimal string": {"format": "lola-deck/0", "records": [self.good_record(lo="0.5")]},
            "unreduced": {"format": "lola-deck/0", "records": [self.good_record(lo="2/4")]},
            "unit denominator": {"format": "lola-deck/0", "records": [self.good_record(lo="1/1")]},
            "negative zero": {"format": "lola-deck/0", "records": [self.good_record(lo="-0")]},
            "lo above hi": {"format": "lola-deck/0", "records": [self.good_record(lo="1", hi="0")]},
            "dotted prop": {"format": "lola-deck/0", "records": [self.good_record(prop="A.x")]},
            "extra key": {"format": "lola-deck/0", "records": [self.good_record(note="x")]},
            "duplicate": {"format": "lola-deck/0", "records": [self.good_record(), self.good_record()]},
            "wrong format": {"format": "lola-deck/1", "records": []},
            "extra top-level key": {"format": "lola-deck/0", "records": [], "x": 1},
            "not an object": [],
        }
        for name, body in cases.items():
            with self.assertRaises(DeckError, msg=name):
                read_deck(self.write_body(body))
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        with self.assertRaises(DeckError):
            read_deck(self.path)
        with self.assertRaises(DeckError):
            read_deck(os.path.join(self.dir.name, "missing.json"))

    def test_build_deck_defaults_to_the_shipped_registry(self):
        self.assertEqual(build_deck(), DECK)


def _syms(expr) -> set[str]:
    if isinstance(expr, Sym):
        return {expr.name}
    found = set()
    for f in dataclasses.fields(expr):
        child = getattr(expr, f.name)
        for c in child if isinstance(child, tuple) else (child,):
            if dataclasses.is_dataclass(c):
                found |= _syms(c)
    return found


if __name__ == "__main__":
    unittest.main()
