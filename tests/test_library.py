"""The certificate library: family certification, shape matching, Instance offers and the
store on disk. Owner: F.

Hand check of the shipped family box (examples/families/cu_pvc_clipped.lola), from the
heat balance in lola/models/circuit.py, theta = amb + I^2 R20 (1 + alpha (theta - 20)) T,
solved for theta:  theta(I) = (amb + I^2 k (1 - 20 alpha)) / (1 - I^2 k alpha),  k = R20 T.

The hottest corner of the box is the thinnest conductor with the thinnest insulation
and the poorest cooling: A = 2.5 mm2, t = 0.8 mm, h = 5 W/m2K, amb = 40 degC, with
alpha = 0.00393 /K, rho20 = 1/58 ohm mm2/m and the PVC thermal resistivity 5 K m/W.
    d  = sqrt(4 A / pi) = 1.78412 mm,  D = d + 2 t = 3.38412 mm
    T1 = (5 / 2 pi) ln(D / d) = 0.50943 K m/W,  T4 = 1 / (pi D h) = 18.8120 K m/W
    R20 = rho20 / A = 6.89655e-3 ohm/m,  k = R20 (T1 + T4) = 0.133251
    theta(13 A) = 66.65 degC   theta(13.6 A) = 69.43 degC
    theta(13.8 A) = 70.40 degC theta(16 A) = 82.49 degC
so the 70 degC claim holds up to I = 13.72 A and fails at the 16 A the family first
declared. The 3 % drop claim holds over the whole run: at 16 A and 20 m, with the
conductor at 70 degC, 2 L I R20 (1 + 50 alpha) = 5.28 V, under 3 % of 230 V = 6.9 V.
"""
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from lola.kernel import Add, Const, Evidence, Instance, Leaf, Matrix, Neg, RangeHyp, Rejection, Split, Statement, Sym, Theorem, check, decode_statement, statement_hash
from lola.kernel.rules.r1_linear import FeasiblePoints, LinearFeasible
from lola.kernel.rules.r4_enclosure import AllNonpositive, Enclosure
from lola.lang import parse_design
from lola.library import Library, canonical_renaming, certify_family, claim_obligations, family_entry, shape_hash
from lola.pipeline import check_design
from lola.registry import build_registry
from lola.verdict import Discharged, Open
from tests import mutations

ROOT = Path(__file__).resolve().parents[1]
FAMILY = (ROOT / "examples" / "families" / "cu_pvc_clipped.lola").read_text(encoding="utf-8")
CIRCUIT = (ROOT / "examples" / "circuit_pass.lola").read_text(encoding="utf-8")
REGISTRY = build_registry()
DRAW = "param draw       in [0 A, 13 A]"


def family_with_draw(amps: str) -> str:
    assert DRAW in FAMILY, "the shipped family declares its draw as the tests expect"
    return FAMILY.replace(DRAW, f"param draw       in [0 A, {amps} A]")


def circuit_with_draw(amps: str) -> str:
    return CIRCUIT.replace("current in [0 A, 10 A]", f"current in [0 A, {amps} A]")


def claims(text: str) -> dict:
    design = parse_design(text, "test.lola", REGISTRY)
    return {o.requirement.id.rsplit(".", 1)[-1]: o for o in claim_obligations(design, REGISTRY)}


def certify(text: str, root: str):
    return certify_family(parse_design(text, "family.lola", REGISTRY), REGISTRY, Library(root))


def library_outcomes(text: str, library: Library) -> dict:
    report = check_design(parse_design(text, "query.lola", REGISTRY), REGISTRY, (library,))
    return {o.requirement.id.rsplit(".", 1)[-1]: o for o in report.outcomes if isinstance(o, Open)} | {
        o.obligation.requirement.id.rsplit(".", 1)[-1]: o for o in report.outcomes if isinstance(o, Discharged)
    }


class FamilyBox(unittest.TestCase):
    def test_shipped_box_certifies_both_claims(self):
        with tempfile.TemporaryDirectory() as root:
            result = certify(FAMILY, root)
            self.assertEqual(result.skipped, (), "the hand check puts the hottest corner of the 13 A box at 66.65 degC")
            self.assertEqual(len(result.stored), 2, "hot and drop each store one entry")

    def test_the_16_A_box_is_refuted_on_temperature_only(self):
        with tempfile.TemporaryDirectory() as root:
            result = certify(family_with_draw("16"), root)
            self.assertEqual(len(result.skipped), 1, "only the hot claim fails at 16 A (82.49 degC by hand)")
            self.assertIn("claim.hot", result.skipped[0], "the skipped claim is hot")
            self.assertIn("refuted", result.skipped[0], "the solver refutes it rather than giving up")
            self.assertEqual(len(result.stored), 1, "the drop claim (5.28 V of 6.9 V by hand) is still stored")

    def test_the_box_edge_sits_where_the_hand_check_puts_it(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(certify(family_with_draw("13.6"), root).skipped, (), "69.43 degC at 13.6 A is within 70 degC")
        with tempfile.TemporaryDirectory() as root:
            skipped = certify(family_with_draw("13.8"), root).skipped
            self.assertTrue(any("claim.hot" in s and "refuted" in s for s in skipped), "70.40 degC at 13.8 A is refuted")

    def test_certifying_twice_stores_nothing_new(self):
        with tempfile.TemporaryDirectory() as root:
            certify(FAMILY, root)
            files = sorted(p.relative_to(root) for p in Path(root).rglob("*") if p.is_file())
            certify(FAMILY, root)
            again = sorted(p.relative_to(root) for p in Path(root).rglob("*") if p.is_file())
            self.assertEqual(files, again, "the second certification leaves the same files")
            self.assertEqual(Library(root).stats()["families"], 2, "two families after two runs")

    def test_a_concrete_design_is_not_a_family(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                certify(CIRCUIT, root)


class ShapeMatching(unittest.TestCase):
    def test_a_concrete_claim_has_its_family_claims_shape(self):
        family, concrete = claims(FAMILY), claims(CIRCUIT)
        for name in ("hot", "drop"):
            self.assertEqual(shape_hash(family[name].statement), shape_hash(concrete[name].statement), f"{name} shapes match across symbol names")

    def test_different_claims_have_different_shapes(self):
        concrete = claims(CIRCUIT)
        self.assertNotEqual(shape_hash(concrete["hot"].statement), shape_hash(concrete["drop"].statement), "temperature and drop differ in shape")

    def test_ranges_and_labels_do_not_change_the_shape_but_constants_do(self):
        def statement(name: str, hi: int, limit: int, label: str) -> Statement:
            return Statement((RangeHyp(name, Fraction(0), Fraction(hi), label),), AllNonpositive((Add((Sym(name), Neg(Const(Fraction(limit))))),)))

        base = statement("x", 10, 12, "a")
        self.assertEqual(shape_hash(base), shape_hash(statement("load", 3, 12, "b")), "a renamed, narrowed symbol keeps the shape")
        self.assertNotEqual(shape_hash(base), shape_hash(statement("x", 10, 11, "a")), "a different constant changes the shape")

    def test_canonical_renaming_is_consistent(self):
        family, concrete = claims(FAMILY)["hot"].statement, claims(CIRCUIT)["hot"].statement
        self.assertEqual(sorted(canonical_renaming(family).values()), sorted(canonical_renaming(concrete).values()), "both use the same canonical names")
        self.assertEqual(len(set(canonical_renaming(family).values())), len(family.hyps), "every hypothesis gets its own canonical name")


class Lookup(unittest.TestCase):
    def test_a_query_inside_the_box_reuses_the_family(self):
        with tempfile.TemporaryDirectory() as root:
            certify(FAMILY, root)
            library = Library(root)
            outcomes = library_outcomes(CIRCUIT, library)
            for name in ("hot", "drop"):
                self.assertIsInstance(outcomes[name], Discharged, f"{name} is proved from the library")
                self.assertEqual(outcomes[name].source, "library", f"{name} evidence came from the library")
            self.assertEqual(library.stats()["hits"], 2, "one hit per claim")

    def test_a_query_outside_the_box_is_not_offered(self):
        with tempfile.TemporaryDirectory() as root:
            certify(FAMILY, root)
            library = Library(root)
            outcomes = library_outcomes(circuit_with_draw("14"), library)
            self.assertIsInstance(outcomes["hot"], Open, "14 A lies outside the 13 A box")
            self.assertGreaterEqual(library.stats()["misses"], 1, "the lookup missed")
            self.assertIsNone(library.lookup(claims(circuit_with_draw("14"))["hot"].statement), "lookup finds no containing family")

    def test_a_false_family_planted_in_the_library_never_passes(self):
        planted = claims(family_with_draw("16"))["hot"]
        with tempfile.TemporaryDirectory() as root:
            library = Library(root)
            library.add(family_entry(planted.statement, Evidence(Enclosure(Leaf())), ("planted",)))
            outcomes = library_outcomes(circuit_with_draw("15"), library)
            self.assertIsInstance(outcomes["hot"], Open, "the kernel rejects the planted evidence, so 15 A stays open")
            self.assertTrue(outcomes["hot"].rejections, "the rejection is recorded")


def bound(name: str, lo: int, hi: int) -> Statement:
    """name - 10 <= 0 over [lo, hi]: true exactly when hi <= 10."""
    return Statement((RangeHyp(name, Fraction(lo), Fraction(hi), "load"),), AllNonpositive((Add((Sym(name), Neg(Const(Fraction(10))))),)))


class Offers(unittest.TestCase):
    PARTITION = Split("x", Fraction(5), Leaf(), Split("x", Fraction(8), Leaf(), Leaf()))

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.library = Library(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def offer(self, statement: Statement) -> tuple:
        return tuple(self.library.offer(statement, statement_hash(statement)))

    def test_an_offer_is_an_instance_under_the_canonical_renaming(self):
        certify(FAMILY, self.dir.name)
        query = claims(CIRCUIT)["hot"].statement
        (evidence,) = self.offer(query)
        self.assertIsInstance(evidence.body, Instance, "the library offers an Instance")
        entry = self.library.lookup(query)
        self.assertEqual((evidence.body.statement, evidence.body.evidence), (entry.statement, entry.evidence), "of the family lookup finds")
        family_names, query_names = canonical_renaming(entry.statement), canonical_renaming(query)
        self.assertEqual({family_names[f]: query_names[q] for f, q in evidence.body.renaming}, {c: c for c in family_names.values()},
                         "each family symbol goes to the query symbol with the same canonical name")
        result = check(query, evidence)
        self.assertIsInstance(result, Theorem, getattr(result, "reason", ""))
        self.assertEqual(result.statement_hash, statement_hash(query), "the theorem is about the query")

    def test_an_instance_proves_a_query_inside_the_box(self):
        self.library.add(family_entry(bound("x", 0, 10), Evidence(Enclosure(self.PARTITION)), ("model",)))
        (evidence,) = self.offer(bound("y", 2, 7))
        self.assertEqual(evidence.body.renaming, (("x", "y"),), "x is renamed to y")
        self.assertIsInstance(check(bound("y", 2, 7), evidence), Theorem, "y - 10 <= 0 holds on y in [2, 7]")

    def test_nothing_is_offered_outside_the_box_and_a_forced_instance_is_rejected(self):
        family = bound("x", 0, 10)
        self.library.add(family_entry(family, Evidence(Enclosure(self.PARTITION)), ("model",)))
        self.assertEqual(self.offer(bound("y", 2, 12)), (), "[2, 12] is not inside [0, 10]")
        forced = Evidence(Instance(family, Evidence(Enclosure(self.PARTITION)), (("x", "y"),)))
        self.assertIsInstance(check(bound("y", 2, 12), forced), Rejection, "y - 10 <= 0 fails at y = 12, so no Instance proves it")

    def test_the_family_with_the_fewest_leaves_is_offered(self):
        self.library.add(family_entry(bound("x", 0, 10), Evidence(Enclosure(self.PARTITION)), ("model",)))
        self.library.add(family_entry(bound("x", 0, 9), Evidence(Enclosure(Leaf())), ("model",)))
        (evidence,) = self.offer(bound("y", 2, 7))
        self.assertEqual(evidence.body.evidence, Evidence(Enclosure(Leaf())), "the one-leaf family over [0, 9] is cheaper to check than the three-leaf one")
        self.assertIsInstance(check(bound("y", 2, 7), evidence), Theorem, "and it proves the query")

    def test_a_renaming_that_reorders_symbols_needs_no_new_evidence(self):
        def statement(p: str, s: str, p_box: tuple[int, int], s_box: tuple[int, int]) -> Statement:
            hyps = sorted((RangeHyp(p, Fraction(p_box[0]), Fraction(p_box[1]), "p"), RangeHyp(s, Fraction(s_box[0]), Fraction(s_box[1]), "s")), key=lambda h: h.sym)
            goal = LinearFeasible(Matrix(1, 1, ((0, 0, Fraction(1)),)), (Add((Sym(p), Sym(s))),), (Const(Fraction(0)),), (Const(Fraction(20)),))
            return Statement(tuple(hyps), goal)

        family = statement("p", "s", (0, 10), (0, 4))
        family_points = Evidence(FeasiblePoints(((Fraction(0),), (Fraction(10),), (Fraction(4),), (Fraction(14),))))
        self.assertIsInstance(check(family, family_points), Theorem, "x = p + s at the family vertices (p, s) = (0,0), (10,0), (0,4), (10,4)")
        query = statement("b", "a", (2, 6), (1, 3))
        self.assertIsInstance(check(query, family_points), Rejection, "the family's own points do not fit the query's vertices")
        self.library.add(family_entry(family, family_points, ("model",)))
        (evidence,) = self.offer(query)
        self.assertEqual(evidence.body.renaming, (("p", "b"), ("s", "a")), "p goes to b and s to a, which sort the other way")
        self.assertIsInstance(check(query, evidence), Theorem, "the Instance proves the query with the family's points unchanged")

    def test_a_bound_random_variable_is_renamed_with_the_hypotheses(self):
        fix = mutations.BY_NAME["r5_instance"]
        family = fix.evidence.body
        self.library.add(family_entry(family.statement, family.evidence, ("model",)))
        (evidence,) = self.offer(fix.statement)
        self.assertEqual(evidence.body.renaming, (("C", "cap"), ("Hi", "hi"), ("Lo", "lo"), ("M", "mean"), ("x", "load")),
                         "the goal's random variable x is renamed along with the hypotheses")
        self.assertIsInstance(check(fix.statement, evidence), Theorem, "the threshold [37, 40] lies inside the family's [36, 40]")


class Store(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)
        certify(FAMILY, self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def files(self) -> list[Path]:
        return sorted(p for p in self.root.rglob("*") if p.is_file())

    def test_files_are_named_by_shape_and_family_key(self):
        entries = Library(self.root).entries()
        self.assertEqual(len(entries), 2, "two entries")
        expected = sorted(self.root / e.shape_hash.removeprefix("sha256:") / f"{e.family_key.removeprefix('sha256:')}.json" for e in entries)
        self.assertEqual(self.files(), expected, "one file per entry, at <shape>/<key>.json, and no temporary left behind")

    def test_files_are_canonical_utf8_with_lf(self):
        for path in self.files():
            data = path.read_bytes()
            self.assertNotIn(b"\r", data, f"{path.name} has LF line endings")
            self.assertFalse(data.startswith(b"\xef\xbb\xbf"), f"{path.name} has no byte order mark")
            obj = json.loads(data.decode("utf-8"))
            self.assertEqual(data.decode("utf-8"), json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n", f"{path.name} is canonical text")

    def test_a_misnamed_file_is_never_used(self):
        path = self.files()[0]
        path.rename(path.with_name("0" * 64 + ".json"))
        library = Library(self.root)
        self.assertEqual(library.stats()["unreadable"], 1, "the renamed file is counted as unreadable")
        self.assertEqual(library.stats()["families"], 1, "only the untouched entry is used")

    def test_a_file_with_an_edited_box_is_never_used(self):
        for path in self.files():
            obj = json.loads(path.read_text(encoding="utf-8"))
            hyp = next(h for h in obj["statement"]["hyps"] if h["t"] == "range_hyp" and h["lo"] != h["hi"])
            hyp["hi"] = hyp["lo"]
            obj["statement_hash"] = statement_hash(decode_statement(obj["statement"]))
            path.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
        library = Library(self.root)
        self.assertEqual(library.stats()["families"], 0, "a consistent envelope with an edited box no longer hashes to its file name")
        self.assertIsInstance(library_outcomes(CIRCUIT, library)["hot"], Open, "nothing is offered from an edited file")

    def test_a_corrupt_file_is_counted_not_fatal(self):
        self.files()[0].write_text("{not json", encoding="utf-8")
        stats = Library(self.root).stats()
        self.assertEqual((stats["families"], stats["unreadable"]), (1, 1), "one readable family, one unreadable file")


if __name__ == "__main__":
    unittest.main()
