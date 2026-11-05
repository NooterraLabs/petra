"""The certificate envelope and CertStore. Owner: I.

A certificate is untrusted storage. These tests check that a file can only be read back
for the statement it was written for, and that writes are atomic and idempotent.
"""
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

from lola import __version__
from lola.certs import CertificateError, CertificateFile, CertStore, decode_certificate, encode_certificate, load_certificate
from lola.kernel import Add, Const, Evidence, Leaf, Neg, RangeHyp, Split, Statement, Sym, Theorem, check, statement_hash
from lola.kernel.rules.r4_enclosure import AllNonpositive, Enclosure

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "bolt_tension.cert.json"


def statement(hi: int = 1) -> Statement:
    """x in [0, hi] proves x - 2 <= 0 for hi <= 2."""
    return Statement((RangeHyp("x", Fraction(0), Fraction(hi), "in:t.x"),), AllNonpositive((Add((Sym("x"), Neg(Const(Fraction(2))))),)))


LEAF = Evidence(Enclosure(Leaf()))
SPLIT = Evidence(Enclosure(Split("x", Fraction(1, 2), Leaf(), Leaf())))


def certificate(s: Statement = statement(), evidence: Evidence = LEAF) -> CertificateFile:
    return CertificateFile(statement_hash(s), s, evidence, {"source": "solver", "lola": __version__})


class Envelope(unittest.TestCase):
    def test_a_certificate_round_trips_through_json(self):
        cert = certificate()
        back = decode_certificate(json.loads(json.dumps(encode_certificate(cert))))
        self.assertEqual(back, cert)
        self.assertIsInstance(check(back.statement, back.evidence), Theorem)

    def test_a_certificate_whose_statement_was_edited_is_refused_at_read_time(self):
        obj = encode_certificate(certificate())
        obj["statement"]["hyps"][0]["hi"] = "3"
        with self.assertRaises(CertificateError):
            decode_certificate(obj)

    def test_a_statement_that_does_not_hash_to_its_name_cannot_be_represented(self):
        with self.assertRaises(CertificateError):
            CertificateFile(statement_hash(statement(2)), statement(1), LEAF, {})

    def test_every_malformed_envelope_is_refused(self):
        good = encode_certificate(certificate())
        cases = {
            "another envelope format": dict(good, format="lola-cert/1"),
            "another kernel format": dict(good, kernel="lola-kernel/1"),
            "an extra key": dict(good, note="hi"),
            "a missing key": {k: v for k, v in good.items() if k != "producer"},
            "a non-string producer value": dict(good, producer={"source": 1}),
            "a non-string hash": dict(good, statement_hash=7),
            "a float where a rational belongs": dict(good, statement=json.loads(json.dumps(good["statement"]).replace('"hi": "1"', '"hi": 1.0'))),
            "not an object": [good],
        }
        for name, obj in cases.items():
            with self.subTest(name), self.assertRaises(CertificateError):
                decode_certificate(obj)

    def test_a_file_that_repeats_a_key_is_refused(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "c.json"
            text = json.dumps(encode_certificate(certificate()))
            path.write_text(text[:-1] + ', "format": "lola-cert/0"}', encoding="utf-8")
            with self.assertRaises(CertificateError):
                load_certificate(path)

    def test_the_shipped_example_decodes_and_a_one_byte_edit_does_not(self):
        cert = load_certificate(EXAMPLE)
        self.assertEqual(cert.statement_hash, statement_hash(cert.statement))
        text = EXAMPLE.read_text(encoding="utf-8")
        hi = cert.statement.hyps[0].hi
        edited = text.replace(f'"hi": "{hi}"', f'"hi": "{hi + 1}"', 1)
        self.assertEqual(sum(x != y for x, y in zip(edited, text)), 1)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "edited.json"
            path.write_text(edited, encoding="utf-8")
            with self.assertRaises(CertificateError):
                load_certificate(path)


class Store(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.store = CertStore(self.root)
        self.s = statement()
        self.digest = statement_hash(self.s)

    def files(self):
        return sorted(p.name for p in self.root.iterdir())

    def test_recorded_evidence_is_offered_back_for_its_statement_only(self):
        self.store.record(self.s, self.digest, LEAF, "solver")
        self.assertEqual(tuple(self.store.offer(self.s, self.digest)), (LEAF,))
        other = statement(2)
        self.assertEqual(tuple(self.store.offer(other, statement_hash(other))), ())
        (path,) = self.store.paths()
        self.assertEqual(path.name, self.digest.removeprefix("sha256:") + ".json")
        self.assertEqual(load_certificate(path).producer, {"source": "solver", "lola": __version__})

    def test_the_file_on_disk_is_canonical_utf8_with_lf(self):
        self.store.record(self.s, self.digest, LEAF, "solver")
        raw = self.store.paths()[0].read_bytes()
        self.assertTrue(raw.endswith(b"}\n"))
        self.assertNotIn(b"\r", raw)
        self.assertNotIn(b": ", raw)

    def test_recording_the_same_evidence_twice_changes_nothing(self):
        self.store.record(self.s, self.digest, LEAF, "solver")
        path = self.store.paths()[0]
        before, stamp = path.read_bytes(), path.stat().st_mtime_ns
        self.store.record(self.s, self.digest, LEAF, "library")
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), (before, stamp))
        self.assertEqual(self.files(), [path.name])

    def test_recording_other_evidence_replaces_the_file(self):
        self.store.record(self.s, self.digest, LEAF, "solver")
        self.store.record(self.s, self.digest, SPLIT, "solver")
        self.assertEqual(tuple(self.store.offer(self.s, self.digest)), (SPLIT,))
        self.assertEqual(len(self.files()), 1)

    def test_a_crash_mid_write_leaves_the_old_file_and_no_temporary(self):
        self.store.record(self.s, self.digest, LEAF, "solver")
        with mock.patch("lola.certs.os.replace", side_effect=OSError("power cut")), self.assertRaises(OSError):
            self.store.record(self.s, self.digest, SPLIT, "solver")
        self.assertEqual(tuple(self.store.offer(self.s, self.digest)), (LEAF,))
        self.assertEqual(len(self.files()), 1)

    def test_a_leftover_temporary_file_is_never_listed(self):
        self.store.record(self.s, self.digest, LEAF, "solver")
        (self.root / f".{self.digest.removeprefix('sha256:')}.abc.tmp").write_text("{", encoding="utf-8")
        (self.root / "notes.json").write_text("{}", encoding="utf-8")
        self.assertEqual(len(self.store.paths()), 1)

    def test_a_store_creates_its_directory_on_first_write(self):
        nested = CertStore(self.root / "a" / "b")
        self.assertEqual(nested.paths(), ())
        nested.record(self.s, self.digest, LEAF, "solver")
        self.assertEqual(len(nested.paths()), 1)

    def test_a_file_under_the_wrong_name_is_an_error_not_evidence(self):
        other = statement(2)
        self.store.record(other, statement_hash(other), LEAF, "solver")
        (self.store.paths()[0]).rename(self.root / (self.digest.removeprefix("sha256:") + ".json"))
        with self.assertRaises(CertificateError):
            tuple(self.store.offer(self.s, self.digest))

    def test_a_name_that_is_not_a_statement_hash_is_refused(self):
        for bad in ("sha256:../../etc", "md5:" + "0" * 32, self.digest.upper()):
            with self.subTest(bad), self.assertRaises(ValueError):
                self.store.offer(self.s, bad)


if __name__ == "__main__":
    unittest.main()
