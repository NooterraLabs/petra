"""Safe envelopes (petra/envelope.py) on the gadget domain of test_pipeline.py, and once on a
shipped example through the command line.

The gadget claim F - 1/2 * C <= 0 with C in [20 kN, 25 kN] holds exactly while the load F
stays at or below 10 kN, so an envelope over F must stop within its resolution of 10 kN.
"""
import contextlib
import dataclasses
import io
import json
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

from petra import cli, envelope as envelope_module
from petra.envelope import PROBE_OWNER, EnvelopeError, envelope, find_target, narrow, render, to_json
from petra.ir import InputKind
from petra.models.base import ComponentError
from petra.premises import Tag
from petra.units import DIMENSIONLESS, FORCE, TEMPERATURE, Quantity
from petra.verdict import Pass
from tests.test_pipeline import CAPACITY, REGISTRY, WAIVE_WEAR, GadgetDomain, Solver, gadget, point

ROOT = Path(__file__).resolve().parent.parent
KN = Fraction(1000)
CLAIM = "claim fits: g.utilisation <= 1/2 under push\n"
PUSH = 'load push {\n  on g force in [0 kN, 6 kN]\n  signed "client@example.org" source "brief rev A"\n}\n'


def kn(x) -> Quantity:
    return Quantity(point(Fraction(x) * KN), FORCE)


class Envelopes(GadgetDomain):
    BODY = (gadget(CAPACITY), PUSH, CLAIM, WAIVE_WEAR)

    def run_envelope(self, *body, name="push.g.force", lo=kn(0), hi=kn(30), **kwargs):
        return envelope(self.design(*(body or self.BODY)), REGISTRY, name, lo, hi, (Solver(),), **kwargs)

    def test_the_envelope_stops_within_its_resolution_of_the_true_limit(self):
        env = self.run_envelope(resolution=kn(Fraction(1, 2)))
        lo, hi = env.safe
        self.assertEqual(lo, 0)
        self.assertTrue(10 * KN - KN / 2 <= hi <= 10 * KN, hi)
        self.assertTrue(10 * KN < env.above.limit <= hi + KN / 2, env.above.limit)
        self.assertEqual(env.above.blocker.status, "FAIL")
        self.assertIsNone(env.below.blocker, "the low side passes to the end of the probe range")
        self.assertEqual(env.anchor, 3 * KN, "the middle of the stated range [0, 6] kN")

    def test_the_whole_envelope_is_one_pass_assumed_by_the_probe_not_the_owner(self):
        env = self.run_envelope(resolution=kn(1))
        self.assertEqual((env.confirm.lo, env.confirm.hi), env.safe)
        report = env.confirm.report
        self.assertIsInstance(report.verdict, Pass, report.render())
        premise = next(p for p in report.verdict.footprint.premises if p.label == "in:rig.push.g.force")
        self.assertEqual((premise.owner, premise.tag, premise.range.lo, premise.range.hi), (PROBE_OWNER, Tag.ASSUMED, *env.safe))

    def test_every_proved_probe_lies_inside_the_envelope_and_every_other_reaches_past_it(self):
        env = self.run_envelope(resolution=kn(1))
        lo, hi = env.safe
        for p in env.probes:
            with self.subTest(probe=(p.lo, p.hi)):
                if p.status == "PASS":
                    self.assertTrue(lo <= p.lo and p.hi <= hi)
                else:
                    self.assertTrue(p.hi > hi or p.lo < lo)

    def test_a_failing_anchor_has_no_envelope(self):
        env = self.run_envelope(at=kn(12))
        self.assertIsNone(env.safe)
        self.assertEqual(env.start.status, "FAIL")
        self.assertEqual(env.start.at, 12 * KN)
        self.assertIn("envelope   none", render(env))

    def test_a_failing_middle_re_anchors_at_the_low_end(self):
        # The load is stated up to 30 kN, so its middle, 15 kN, is past the 10 kN the
        # gadget carries; the envelope still exists from the low end.
        env = self.run_envelope(gadget(CAPACITY), PUSH.replace("6 kN", "30 kN"), CLAIM, WAIVE_WEAR, resolution=kn(1))
        first = env.probes[0]
        self.assertEqual((first.lo, first.hi, first.status), (15 * KN, 15 * KN, "FAIL"))
        self.assertEqual((env.anchor, env.start.status), (0, "PASS"))
        lo, hi = env.safe
        self.assertEqual(lo, 0)
        self.assertTrue(9 * KN <= hi <= 10 * KN, hi)
        self.assertTrue(any("anchored at the low end" in n for n in env.notes), env.notes)
        self.assertIn("anchored at the low end", render(env))
        self.assertLessEqual(len(env.probes), envelope_module.DEFAULT_MAX_PROBES)

    def test_a_given_anchor_is_never_moved(self):
        env = self.run_envelope(gadget(CAPACITY), PUSH.replace("6 kN", "30 kN"), CLAIM, WAIVE_WEAR, at=kn(15))
        self.assertIsNone(env.safe)
        self.assertEqual((env.anchor, len(env.probes)), (15 * KN, 1))

    def test_when_the_low_end_fails_too_both_are_named(self):
        body = (gadget(CAPACITY), PUSH.replace("[0 kN, 6 kN]", "[20 kN, 30 kN]"), CLAIM, WAIVE_WEAR)
        env = self.run_envelope(*body, lo=kn(20), hi=kn(30))
        self.assertIsNone(env.safe)
        self.assertEqual(env.anchor, 25 * KN)
        self.assertTrue(any("at the low end of the probe range, 20000 N, it is FAIL too" in n for n in env.notes), env.notes)

    def test_reports_print_in_the_unit_of_the_request(self):
        env = self.run_envelope(resolution=kn(1), unit="kN")
        text = render(env)
        self.assertIn("stated [0, 6] kN; probed [0, 30] kN from 3 kN, resolution 1 kN", text)
        self.assertNotRegex(text, r"\d N\b")
        self.assertEqual(to_json(env)["probe"], ["0", "30000"], "the JSON stays exact SI")
        with self.assertRaises(EnvelopeError):
            self.run_envelope(unit="degC")

    def test_a_param_is_probed_by_its_scope_parameter(self):
        body = (gadget("  capacity param cap\n"), "param cap in [20 kN, 25 kN]\n", PUSH.replace("6 kN", "9 kN"), CLAIM, WAIVE_WEAR)
        env = self.run_envelope(*body, name="cap", lo=kn(10), hi=kn(40), resolution=kn(1))
        lo, hi = env.safe
        self.assertEqual(hi, 40 * KN)
        self.assertTrue(18 * KN <= lo <= 18 * KN + KN, lo)
        self.assertEqual(env.target.label, "par:rig.cap")

    def test_obligations_that_do_not_depend_on_the_input_are_set_aside(self):
        other = 'load pull {\n  on h force in [0 kN, 5 kN]\n  signed "client@example.org" source "brief rev A"\n}\n'
        waive_h = 'waive gadget.wear on h by "o@example.org" reason "no sliding contact"\n'
        env = self.run_envelope(gadget(CAPACITY), gadget(CAPACITY, name="h"), PUSH, other, CLAIM, WAIVE_WEAR, waive_h, resolution=kn(2))
        self.assertEqual((env.elsewhere, env.elsewhere_open), ("PASS", ()))
        self.assertIn("do not depend on push.g.force are PASS", render(env))

    def test_a_probe_the_design_refuses_is_invalid_and_stops_the_envelope(self):
        real = envelope_module.check_design

        def refusing(design, registry, sources, **kwargs):
            force = design.loads["push"].entries[0].value.range.value
            if force.hi > 8 * KN:
                raise ComponentError(("g: the rig cannot apply more than 8 kN",))
            return real(design, registry, sources, **kwargs)

        with mock.patch.object(envelope_module, "check_design", refusing):
            env = self.run_envelope(resolution=kn(1))
        self.assertLessEqual(env.safe[1], 8 * KN)
        self.assertEqual(env.above.blocker.status, "INVALID")
        self.assertIn("cannot apply", env.above.blocker.why)

    def test_requests_that_cannot_be_answered_are_refused(self):
        cases = (
            dict(name="nothing"),
            dict(lo=Quantity(point(0), TEMPERATURE)),
            dict(lo=kn(5), hi=kn(5)),
            dict(at=kn(50)),
            dict(resolution=Quantity(point(1), DIMENSIONLESS)),
        )
        for kwargs in cases:
            with self.subTest(**{k: str(v) for k, v in kwargs.items()}), self.assertRaises(EnvelopeError):
                self.run_envelope(**kwargs)

    def test_an_input_with_a_mean_is_refused(self):
        mean = PUSH.replace("[0 kN, 6 kN]", "[0 kN, 6 kN] mean 4 kN")
        with self.assertRaises(EnvelopeError) as ctx:
            self.run_envelope(gadget(CAPACITY), mean, CLAIM, WAIVE_WEAR)
        self.assertIn("mean", str(ctx.exception))

    def test_narrowing_replaces_one_bound_and_signs_it_as_a_probe(self):
        design = self.design(*self.BODY)
        target = find_target(design, REGISTRY, "g.capacity")
        narrowed = narrow(design, target, 21 * KN, 22 * KN)
        (attr,) = [a for a in narrowed.components["g"].attrs if a.key == "capacity"]
        (bound,) = attr.args
        self.assertEqual((bound.range.value.lo, bound.range.value.hi, bound.kind, bound.signature.owner), (21 * KN, 22 * KN, InputKind.ASSUMED, PROBE_OWNER))
        self.assertEqual(narrowed.loads, design.loads)

    def test_the_probe_limit_stops_the_search_and_says_so(self):
        env = self.run_envelope(resolution=kn(Fraction(1, 10**6)), max_probes=6)
        self.assertLessEqual(len(env.probes), 6)
        self.assertTrue(env.above.capped)
        self.assertEqual((env.confirm.lo, env.confirm.hi), env.safe, "the confirming check still runs")
        self.assertTrue(any("stopped at the limit of 6 checks" in n for n in env.notes), env.notes)
        self.assertIn("stopped at the probe limit", render(env))
        self.assertTrue(to_json(env)["above"]["capped"])

    def test_a_resolution_finer_than_the_range_over_2_to_the_20_is_raised(self):
        env = self.run_envelope(resolution=kn(Fraction(1, 10**30)))
        self.assertEqual(env.resolution, 30 * KN / 2**20)
        self.assertTrue(any(n.startswith("resolution raised") for n in env.notes), env.notes)
        self.assertLessEqual(len(env.probes), envelope_module.DEFAULT_MAX_PROBES)

    def test_fewer_than_four_probes_is_refused(self):
        with self.assertRaises(EnvelopeError):
            self.run_envelope(max_probes=3)

    def test_a_confirming_check_that_does_not_pass_is_named(self):
        env = self.run_envelope(resolution=kn(1))
        failing = dataclasses.replace(env.confirm, status="UNKNOWN")
        self.assertIn("the check over the whole interval is UNKNOWN", render(dataclasses.replace(env, confirm=failing)))

    def test_json_holds_exact_rationals(self):
        found = to_json(self.run_envelope(resolution=kn(1)))
        self.assertEqual((found["label"], found["unit"], found["probe"]), ("in:rig.push.g.force", "N", ["0", "30000"]))
        self.assertEqual(found["safe"][0], "0")
        self.assertEqual(found["above"]["status"], "FAIL")
        self.assertEqual(found["probes"][0], {"range": ["3000", "3000"], "status": "PASS"})


class CommandLine(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["envelope", str(ROOT / "examples" / "circuit_pass.petra"), *args])
        return code, out.getvalue()

    def test_the_ambient_envelope_of_the_lighting_radial(self):
        code, out = self.run_cli("--input", "ambient", "--from", "-20 degC", "--to", "100degC", "--json")
        self.assertEqual(code, 0)
        found = json.loads(out)
        lo, hi = (Fraction(x) for x in found["safe"])
        self.assertEqual(lo, -20)
        self.assertTrue(40 <= hi < Fraction(found["above"]["limit"]) <= 100, found["above"])
        self.assertEqual(found["above"]["status"], "FAIL")
        self.assertIn("claim.hot", found["above"]["why"])
        self.assertEqual(found["confirmed"], "PASS")

    def test_an_unknown_input_or_a_wrong_unit_is_an_input_error(self):
        self.assertEqual(self.run_cli("--input", "nothing", "--from", "0", "--to", "1")[0], 3)
        self.assertEqual(self.run_cli("--input", "ambient", "--from", "0 A", "--to", "1 A")[0], 3)
        self.assertEqual(self.run_cli("--input", "ambient", "--from", "zero", "--to", "1 degC")[0], 3)

    def test_a_negative_quantity_may_carry_its_unit_attached(self):
        code, out = self.run_cli("--input", "ambient", "--from", "-20degC", "--to", "100degC", "--json")
        self.assertEqual(code, 0, out)
        self.assertEqual(json.loads(out)["probe"], ["-20", "100"])

    def test_a_steel_envelope_reads_in_kips_from_the_low_end(self):
        out = io.StringIO()
        fixture = ROOT / "tests" / "fixtures" / "readout" / "job5_fail_60k.petra"
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.main(["envelope", str(fixture), "--input", "reaction.tab.shear", "--from", "0 kip", "--to", "60 kip", "--max-probes", "4"])
        text = out.getvalue()
        self.assertEqual(code, 0, text)
        self.assertIn("at reaction.tab.shear = 30 kip, the middle, the design is FAIL", text)
        self.assertIn("stated [0, 60] kip; probed [0, 60] kip from 0 kip", text)
        self.assertNotRegex(text, r"\d N\b")

    def test_a_failing_anchor_exits_with_its_status(self):
        code, out = self.run_cli("--input", "ambient", "--from", "-20 degC", "--to", "100 degC", "--at", "90 degC")
        self.assertEqual(code, 1)
        self.assertIn("envelope   none", out)


if __name__ == "__main__":
    unittest.main()
