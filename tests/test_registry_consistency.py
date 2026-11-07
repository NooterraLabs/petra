"""Physics consistency of decks: the shipped deck is clean, corrupted records are caught
and named by the relation they break. Owner: G."""
import dataclasses
import os
import tempfile
import unittest
from fractions import Fraction

from petra.kernel import Sym
from petra.registry import Deck, Erratum, build_deck, check_deck, read_deck, write_deck
from petra.registry.consistency import RELATIONS, corrupt, flagged_entries

DECK = None
MM2 = Fraction(1, 10**6)


def setUpModule():
    global DECK
    DECK = build_deck()


def broken(deck: Deck, relations=RELATIONS) -> set[tuple[str, str]]:
    return {(f.entry, f.relation) for f in check_deck(deck, relations)}


def finding(deck: Deck, entry: str, relation: str):
    matches = [f for f in check_deck(deck) if (f.entry, f.relation) == (entry, relation)]
    assert len(matches) == 1, f"one {relation} finding on {entry}"
    return matches[0]


def with_provenance(deck: Deck, entry: str, prop: str, provenance: str) -> Deck:
    record = deck.get(entry, prop)
    assert record is not None, f"deck has {entry}.{prop}"
    edited = dataclasses.replace(record, provenance=provenance)
    return dataclasses.replace(deck, records=tuple(edited if r is record else r for r in deck.records))


def without(deck: Deck, entry: str, prop: str) -> Deck:
    assert deck.get(entry, prop) is not None, f"deck has {entry}.{prop}"
    return dataclasses.replace(deck, records=tuple(r for r in deck.records if (r.entry, r.prop) != (entry, prop)))


def applicable(relation) -> list[str]:
    entries = sorted({r.entry for r in DECK.records})
    return [e for e in entries
            if e.startswith(relation.applies_to) and DECK.get(*relation.lhs(DECK, e).name.rsplit(".", 1))]


class ShippedDeck(unittest.TestCase):
    def test_the_shipped_deck_breaks_no_relation(self):
        self.assertEqual(check_deck(DECK), ())

    def test_the_shipped_deck_is_clean_after_a_round_trip_through_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "deck.json")
            write_deck(DECK, path)
            self.assertEqual(check_deck(read_deck(path)), ())

    def test_every_relation_checks_some_entry_of_the_shipped_deck(self):
        for relation in RELATIONS:
            self.assertTrue(applicable(relation), f"{relation.id} applies to no entry")
            for entry in applicable(relation):
                self.assertIsInstance(relation.lhs(DECK, entry), Sym, f"{relation.id}: the left side is one record")

    def test_every_derived_record_is_re_derived(self):
        on_left = {relation.lhs(DECK, e) for relation in RELATIONS for e in applicable(relation)}
        copies = [r for r in DECK.records if r.provenance.startswith("derived:")
                  and Sym(f"{r.entry}.{r.prop}") not in on_left]
        self.assertGreater(len(copies), 100, "sizes copy their series parameters from the constants")
        corrupted = DECK
        for r in copies:
            corrupted = corrupt(corrupted, r.entry, r.prop, Fraction(2))
        messages = [f.message for f in check_deck(corrupted) if f.relation == "record.copy"]
        for r in copies:
            self.assertTrue(any(m.startswith(f"{r.entry}.{r.prop} ") for m in messages),
                            f"a doubled {r.entry}.{r.prop} is caught")


class Corruptions(unittest.TestCase):
    def test_each_relation_catches_its_own_record_doubled(self):
        for relation in RELATIONS:
            entry = applicable(relation)[0]
            prop = relation.lhs(DECK, entry).name.rsplit(".", 1)[1]
            self.assertIn((entry, relation.id), broken(corrupt(DECK, entry, prop, Fraction(2)), (relation,)),
                          f"{relation.id} catches a doubled {entry}.{prop}")

    def test_a_wrong_stress_area_is_caught(self):
        corrupted = corrupt(DECK, "bolt.M12_A4_70", "As", Fraction(3, 2))
        self.assertEqual(broken(corrupted), {("bolt.M12_A4_70", "bolt.stress_area")})
        found = finding(corrupted, "bolt.M12_A4_70", "bolt.stress_area")
        self.assertIn("bolt.M12_A4_70.As", found.message)
        self.assertGreater(found.lhs.lo, Fraction("126.3") * MM2, "1.5 * 84.267 mm2")
        self.assertGreater(found.rhs.lo, Fraction("84.26") * MM2, "ISO 724 stress area of M12 is 84.267 mm2")
        self.assertLess(found.rhs.hi, Fraction("84.28") * MM2)

    def test_a_wrong_stress_area_also_breaks_the_proof_load_that_uses_it(self):
        self.assertEqual(broken(corrupt(DECK, "bolt.M12_8_8", "As", Fraction(9, 10))),
                         {("bolt.M12_8_8", "bolt.stress_area"), ("bolt.M12_8_8", "bolt.proof_load")})

    def test_a_wrong_published_stress_area_is_caught(self):
        self.assertEqual(broken(corrupt(DECK, "const.iso261.M12", "As_table", Fraction(10))),
                         {("const.iso261.M12", "thread.stress_area_table")})

    def test_a_wrong_resistance_per_metre_is_caught(self):
        corrupted = corrupt(DECK, "cable.cu_pvc_2_5", "R20", Fraction(2))
        self.assertEqual(broken(corrupted), {("cable.cu_pvc_2_5", "cable.resistance")})
        self.assertIn("cable.cu_pvc_2_5.R20", finding(corrupted, "cable.cu_pvc_2_5", "cable.resistance").message)

    def test_a_resistance_inside_the_iec_60228_allowance_passes(self):
        self.assertEqual(broken(corrupt(DECK, "cable.cu_pvc_2_5", "R20", Fraction(109, 100))), set())

    def test_a_resistance_outside_the_iec_60228_allowance_is_caught(self):
        for factor in (Fraction(111, 100), Fraction(99, 100)):
            self.assertEqual(broken(corrupt(DECK, "cable.cu_pvc_2_5", "R20", factor)),
                             {("cable.cu_pvc_2_5", "cable.resistance")}, f"R20 times {factor}")

    def test_a_wrong_published_maximum_resistance_is_caught(self):
        self.assertEqual(broken(corrupt(DECK, "const.iec60228.2_5", "R20_max_table", Fraction(1, 2))),
                         {("const.iec60228.2_5", "conductor.resistance_table")})

    def test_unit_slips_by_a_factor_of_1000_are_caught(self):
        cases = (
            ("bolt.M16_8_8", "d", Fraction(1000), {"bolt.stress_area", "record.copy"}),
            ("cable.cu_pvc_4", "R20", Fraction(1000), {"cable.resistance"}),
            ("bolt.M20_10_9", "Fp", Fraction(1, 1000), {"bolt.proof_load"}),
            ("steel.S355", "density", Fraction(1, 1000), {"record.copy"}),
            ("const.cu", "rho20", Fraction(1000), {"copper.adiabatic_constant"}),
        )
        for entry, prop, factor, relations in cases:
            found = {relation for e, relation in broken(corrupt(DECK, entry, prop, factor)) if e == entry}
            self.assertEqual(found, relations, f"{entry}.{prop} times {factor}")

    def test_a_copied_constant_that_disagrees_with_its_constant_is_caught(self):
        corrupted = corrupt(DECK, "cable.cu_pvc_2_5", "alpha", Fraction(2))
        self.assertEqual(broken(corrupted), {("cable.cu_pvc_2_5", "record.copy")})
        self.assertIn("const.cu.alpha20", finding(corrupted, "cable.cu_pvc_2_5", "record.copy").message)

    def test_a_wrong_temperature_coefficient_is_caught(self):
        self.assertEqual({r for e, r in broken(corrupt(DECK, "const.cu", "alpha20", Fraction(11, 10))) if e == "const.cu"},
                         {"copper.temperature_coefficient"})

    def test_a_wrong_k_factor_is_caught(self):
        self.assertEqual(broken(corrupt(DECK, "const.pvc", "k_cu_table", Fraction(103, 100))),
                         {("const.pvc", "insulation.k_factor_table")})
        self.assertEqual(broken(corrupt(DECK, "const.pvc", "k_cu_table", Fraction(1005, 1000))), set(),
                         "115.6 against the derived 114.8 is inside the 1 % tolerance")

    def test_a_corrupted_imported_deck_is_caught(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "deck.json")
            write_deck(corrupt(DECK, "chs.60_3x3_2", "A", Fraction(1000)), path)
            self.assertEqual(broken(read_deck(path)), {("chs.60_3x3_2", "section.area")})


class Provenance(unittest.TestCase):
    def test_a_record_without_a_source_is_caught(self):
        corrupted = with_provenance(DECK, "bolt.M12_A4_70", "Rp02_min", "stated:sanctioned:ISO:")
        self.assertEqual(broken(corrupted), {("bolt.M12_A4_70", "record.provenance")})
        message = finding(corrupted, "bolt.M12_A4_70", "record.provenance").message
        self.assertIn("Rp02_min", message)
        self.assertIn("source", message)

    def test_malformed_provenance_is_caught(self):
        for provenance in ("published: ", "derived:", "stated:sanctioned::ISO 3506-1", "stated:assumed:ISO:ISO 3506-1",
                           "stated:sanctioned", "typed in", ""):
            self.assertEqual(broken(with_provenance(DECK, "bolt.M12_A4_70", "Rp02_min", provenance)),
                             {("bolt.M12_A4_70", "record.provenance")}, repr(provenance))

    def test_well_formed_provenance_of_every_kind_passes(self):
        for provenance in ("stated:judged:petra-maintainers:recalled", "published:ISO 3506-1:2020 Table 6",
                           "stated:measured:Acme Fasteners:test report 17"):
            self.assertEqual(broken(with_provenance(DECK, "bolt.M12_A4_70", "Rp02_min", provenance)), set(),
                             repr(provenance))


class EntryProvenance(unittest.TestCase):
    def edited(self, id: str, **changes) -> Deck:
        entry = DECK.entry(id)
        assert entry is not None, f"deck has entry {id}"
        return dataclasses.replace(DECK, entries=tuple(dataclasses.replace(e, **changes) if e is entry else e
                                                       for e in DECK.entries))

    def test_an_entry_without_a_source_is_caught_on_the_entry_the_pipeline_flags(self):
        self.assertEqual(broken(self.edited("bolt.M12_A4_70", source=" ")), {("bolt.M12_A4_70", "entry.provenance")})
        self.assertEqual(broken(self.edited("const.cu.rho20", source="")), {("const.cu", "entry.provenance")})

    def test_a_version_that_does_not_count_the_errata_is_caught(self):
        fix = Erratum("2026-11-06", "it said 1", "it says 2")
        self.assertEqual(broken(self.edited("steel.S355", version=2)), {("steel.S355", "entry.provenance")})
        self.assertEqual(broken(self.edited("steel.S355", version=2, errata=(fix,))), set())
        self.assertIn("version 1 with 1 errata", finding(self.edited("steel.S355", errata=(fix,)), "steel.S355",
                                                          "entry.provenance").message)

    def test_a_malformed_erratum_is_caught(self):
        for erratum in (Erratum("6 Nov 2026", "a", "b"), Erratum("2026-11-06", "a", " ")):
            self.assertEqual(broken(self.edited("steel.S355", version=2, errata=(erratum,))),
                             {("steel.S355", "entry.provenance")}, repr(erratum))

    def test_a_record_whose_entry_has_no_row_is_caught_once_per_entry(self):
        reduced = dataclasses.replace(DECK, entries=tuple(e for e in DECK.entries if e.entry not in ("chs.60_3x3_2", "const.cu.qc")))
        self.assertEqual(broken(reduced), {("chs.60_3x3_2", "entry.provenance"), ("const.cu", "entry.provenance")})
        self.assertIn("no entry row gives chs.60_3x3_2's source and version",
                      finding(reduced, "chs.60_3x3_2", "entry.provenance").message)


class MissingAndUndefined(unittest.TestCase):
    def test_a_record_a_relation_needs_but_the_deck_lacks_is_caught(self):
        reduced = without(DECK, "bolt.M12_A4_70", "d")
        self.assertEqual(broken(reduced), {("bolt.M12_A4_70", "bolt.stress_area")})
        self.assertIn("no record bolt.M12_A4_70.d", finding(reduced, "bolt.M12_A4_70", "bolt.stress_area").message)

    def test_a_copy_whose_constant_the_deck_lacks_is_caught(self):
        reduced = without(DECK, "const.install.clipped_direct", "h")
        self.assertEqual(broken(reduced), {("install.clipped_direct", "record.copy")})

    def test_a_deck_that_omits_a_derived_property_breaks_nothing(self):
        self.assertEqual(broken(without(DECK, "bolt.M12_A4_70", "As")), set())

    def test_an_undefined_operation_is_a_finding(self):
        corrupted = corrupt(DECK, "cable.cu_pvc_2_5", "area", Fraction(0))
        self.assertTrue(finding(corrupted, "cable.cu_pvc_2_5", "cable.resistance").message.startswith("cannot evaluate"))

    def test_corrupting_a_record_the_deck_lacks_is_refused(self):
        with self.assertRaises(KeyError):
            corrupt(DECK, "bolt.M12_A4_70", "Fp", Fraction(2))


class Reporting(unittest.TestCase):
    def test_findings_are_sorted_and_repeatable(self):
        corrupted = corrupt(corrupt(DECK, "mcb.B16", "I_t", Fraction(2)), "chs.60_3x3_2", "I", Fraction(2))
        first = check_deck(corrupted)
        self.assertEqual(first, check_deck(corrupted))
        self.assertEqual(list(first), sorted(first, key=lambda f: (f.entry, f.relation, f.message)))
        self.assertEqual(flagged_entries(first), {"chs.60_3x3_2", "mcb.B16"})
        self.assertEqual({(f.entry, f.relation) for f in first},
                         {("chs.60_3x3_2", "section.second_moment"), ("mcb.B16", "breaker.conventional_tripping")})


if __name__ == "__main__":
    unittest.main()
