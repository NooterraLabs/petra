"""`petra registry recall`: which verdicts rest on a registry entry, read from their
footprints, tried on the first erratum (cable R20, 2026-11-06). Owner: G."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from petra.cli import EXIT_CODES, main
from petra.lang import load_design
from petra.pipeline import check_design
from petra.recall import RecallError, covered, recall, to_json
from petra.registry import build_registry
from petra.solvers import SolverSource

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
CIRCUIT = EXAMPLES / "circuit_pass.petra"
REGISTRY = build_registry()
SERIES = "reg:cable.cu_pvc.rho20_max"


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


def report_json(path: Path) -> dict:
    return check_design(load_design(path, REGISTRY), REGISTRY, (SolverSource(),), path=path.as_posix()).to_json()


class Footprints(unittest.TestCase):
    def test_every_registry_premise_names_the_version_of_its_entry_and_no_other_premise_has_one(self):
        body = report_json(CIRCUIT)
        premises = [p for v in body["verdicts"] for p in v["footprint"]]
        self.assertIn({"tag": "judged", "label": SERIES, "owner": "petra-maintainers", "version": 2,
                       "source": REGISTRY.fact("cable.cu_pvc.rho20_max").standard}, premises)
        for p in premises:
            key = p["label"][len("reg:"):]
            if p["label"].startswith("reg:"):
                self.assertEqual(p["version"], REGISTRY.entry_of(key).provenance.version, p["label"])
            else:
                self.assertNotIn("version", p)

    def test_the_text_footprint_names_a_corrected_entry_s_version(self):
        code, out, _ = run("check", str(CIRCUIT))
        self.assertEqual(code, 0)
        (line,) = [line for line in out.splitlines() if f" {SERIES} " in line]
        self.assertTrue(line.endswith("; version 2)"), line)


class TheR20Erratum(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.found = recall(REGISTRY, "cable.cu_pvc", [EXAMPLES])

    def test_recall_finds_exactly_the_examples_whose_verdicts_read_the_cable_series(self):
        self.assertEqual([(d.file, d.design, d.status) for d in self.found.designs], [
            (CIRCUIT.as_posix(), "workshop-lighting-radial", "PASS"),
            ((EXAMPLES / "families" / "cu_pvc_clipped.petra").as_posix(), "family-cu-pvc-clipped-direct", "UNKNOWN"),
        ])
        self.assertEqual(self.found.checked, len(list(EXAMPLES.rglob("*.petra"))))
        self.assertEqual(self.found.errors, ())

    def test_each_claim_names_the_premise_and_the_version_it_was_checked_at(self):
        circuit = self.found.designs[0]
        self.assertEqual([(v.claim, v.status) for v in circuit.verdicts], [("hot", "PASS"), ("drop", "PASS"), ("coverage", "PASS")])
        for v in circuit.verdicts:
            self.assertEqual([(r.label, r.version, r.current, r.stale) for r in v.premises], [(SERIES, 2, 2, False)])

    def test_the_header_gives_the_entry_its_version_source_and_erratum(self):
        ((entry, provenance),) = self.found.entries
        self.assertEqual((entry, provenance.version), ("cable.cu_pvc", 2))
        self.assertIn("rho20 / area", provenance.errata[0].was)

    def test_recall_is_per_claim(self):
        """Copper's resistivity no longer sets R20, but the adiabatic k of the short-circuit
        check still reads it, so only the coverage verdict rests on it."""
        found = recall(REGISTRY, "const.cu.rho20", [CIRCUIT])
        ((design,),) = (found.designs,)
        self.assertEqual([v.claim for v in design.verdicts], ["coverage"])

    def test_a_canary_and_a_fixture_are_found_when_named(self):
        canary = ROOT / "judges" / "canaries" / "circuit_16mm2_in_4mm2_terminal.petra"
        fixture = ROOT / "tests" / "fixtures" / "readout" / "cable_30m_protected.petra"
        found = recall(REGISTRY, "cable.cu_pvc", [canary, fixture])
        self.assertEqual([(d.file, d.status) for d in found.designs], [(canary.as_posix(), "PASS"), (fixture.as_posix(), "FAIL")])


class SavedReports(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.body = report_json(CIRCUIT)

    def tearDown(self):
        self.dir.cleanup()

    def saved(self, name: str, edit) -> Path:
        for v in self.body["verdicts"]:
            for p in v["footprint"]:
                if p["label"] == SERIES:
                    edit(p)
        path = Path(self.dir.name) / name
        path.write_text(json.dumps(self.body), encoding="utf-8")
        return path

    def test_a_report_checked_before_the_erratum_is_marked_stale(self):
        path = self.saved("before.json", lambda p: p.update(version=1))
        (design,) = recall(REGISTRY, "cable.cu_pvc", [path]).designs
        self.assertTrue(all(r.stale and (r.version, r.current) == (1, 2) for v in design.verdicts for r in v.premises))
        code, out, _ = run("registry", "recall", "cable.cu_pvc", str(path))
        self.assertEqual(code, 0)
        self.assertIn(f"{SERIES} (version 1, now 2: checked before an erratum)", out)

    def test_a_report_saved_before_versions_says_so(self):
        path = self.saved("unversioned.json", lambda p: p.pop("version"))
        (design,) = recall(REGISTRY, "cable.cu_pvc", [path]).designs
        self.assertEqual({(r.version, r.current) for v in design.verdicts for r in v.premises}, {(None, 2)})

    def test_a_json_file_that_is_not_a_report_is_an_error_and_the_rest_still_print(self):
        bad = Path(self.dir.name) / "cert.json"
        bad.write_text(json.dumps({"statement": {}}), encoding="utf-8")
        code, out, _ = run("registry", "recall", "cable.cu_pvc", str(bad), str(CIRCUIT), str(Path(self.dir.name) / "missing.petra"))
        self.assertEqual(code, EXIT_CODES["INPUT_ERROR"])
        self.assertIn(f"PASS      {CIRCUIT.as_posix()}  workshop-lighting-radial", out)
        self.assertIn("not a `petra check --json` report", out)
        self.assertTrue(out.rstrip().endswith("1 of 1 designs rest on cable.cu_pvc"), out)


class Ids(unittest.TestCase):
    def test_an_id_is_an_entry_a_premise_key_a_common_name_or_a_prefix(self):
        self.assertEqual([e for e, _ in covered(REGISTRY, "cable.cu_pvc")], ["cable.cu_pvc"])
        self.assertEqual([e for e, _ in covered(REGISTRY, "cable.cu_pvc.rho20_max")], ["cable.cu_pvc"])
        self.assertEqual([e for e, _ in covered(REGISTRY, "const.cu.rho20")], ["const.cu.rho20"])
        self.assertEqual(sorted(e for e, _ in covered(REGISTRY, "const.iec60228.2_5")), ["const.iec60228.2_5.area"])
        self.assertEqual(recall(REGISTRY, "A325", [CIRCUIT]).id, REGISTRY.canonical("A325"))

    def test_an_unknown_id_is_an_input_error_with_suggestions(self):
        with self.assertRaisesRegex(RecallError, "cable.cu_pvx is not a registry entry, premise key or id prefix"):
            recall(REGISTRY, "cable.cu_pvx", [CIRCUIT])
        code, out, err = run("registry", "recall", "cable.cu_pvx", str(CIRCUIT))
        self.assertEqual((code, out), (EXIT_CODES["INPUT_ERROR"], ""))
        self.assertIn("cable.cu_pvc", err)

    def test_with_no_files_recall_reads_examples_in_the_working_directory(self):
        def run_in(directory, *argv):
            here = os.getcwd()
            os.chdir(directory)
            try:
                return run(*argv)
            finally:
                os.chdir(here)

        code, out, _ = run_in(ROOT, "registry", "recall", "cable.cu_pvc", "--json")
        self.assertEqual(code, 0)
        body = json.loads(out)
        self.assertEqual(set(body), {"id", "entries", "designs", "checked", "errors"})
        self.assertEqual([d["file"] for d in body["designs"]],
                         ["examples/circuit_pass.petra", "examples/families/cu_pvc_clipped.petra"])
        self.assertEqual(body["designs"][0]["verdicts"][0]["premises"],
                         [{"label": SERIES, "version": 2, "current": 2, "stale": False}])
        with tempfile.TemporaryDirectory() as empty:
            code, _, err = run_in(empty, "registry", "recall", "cable.cu_pvc")
        self.assertEqual(code, EXIT_CODES["INPUT_ERROR"])
        self.assertIn("no examples/ directory here", err)

    def test_to_json_round_trips_through_json(self):
        found = recall(REGISTRY, "cable.cu_pvc", [CIRCUIT])
        self.assertEqual(json.loads(json.dumps(to_json(found))), to_json(found))


if __name__ == "__main__":
    unittest.main()
