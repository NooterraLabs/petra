"""The gym: task generators, the environment's kernel-only reward, the baseline agent.
Owner: Y.

The passing and failing designs come from facts the rest of the suite establishes by
hand. examples/circuit_pass.petra (B10, 2.5 mm2 Cu/PVC clipped direct, 18 m, a 75 degC
lever terminal, 10 A, ambient up to 40 degC, fault level up to 6 kA) passes, and every
bound it checks grows with the draw, the run, the ambient and the fault level, so the
same parts pass any task with at most 10 A over at most 18 m. A B6 breaker on a draw
above 6 A breaks the overload condition I_B <= I_n (IEC 60364-4-43 433.1), so that
design is refuted.
"""
import tempfile
import unittest
from fractions import Fraction
from unittest import mock

from petra.certs import CertificateFile, encode_certificate
from petra.gym import GENERATORS, AgentStats, BaselineAgent, LolaEnv, Submission, run_episodes
from petra.gym.tasks import family_text, fill, generate
from petra.kernel import Evidence, Leaf, Split, encode_evidence
from petra.kernel.rules.r4_enclosure import Enclosure
from petra.lang import parse_design
from petra.library import Library
from petra.models import DOMAINS
from petra.pipeline import check_design
from petra.registry import PartKind, build_registry
from petra.solvers import SolverSource
from petra.verdict import Discharged, Fail, Pass, Unknown

REGISTRY = build_registry()
PASSING = {"cb1.part": "mcb.B10", "w1.cable": "cable.cu_pvc_2_5", "t1.part": "terminal.lever_4mm2_75C"}
OVERLOADED = {"cb1.part": "mcb.B6", "w1.cable": "cable.cu_pvc_2_5", "t1.part": "terminal.lever_4mm2_75C"}


def seed_for(domain: str, fits) -> int:
    return next(seed for seed in range(500) if fits(dict(generate(domain, seed, REGISTRY).given)))


SMALL = seed_for("circuit", lambda g: int(g["current"]) <= 10 and int(g["length"]) <= 18)
OVER_SIX = seed_for("circuit", lambda g: 6 < int(g["current"]) <= 10 and int(g["length"]) <= 18)
LIGHT_BOLT = seed_for("bolt", lambda g: g["torque_hi"] == "50" and int(g["force"]) <= 26 and g["environment"] == "indoor_dry")


class _Collect:
    def __init__(self):
        self.items = []

    def record(self, statement, statement_hash, evidence, source):
        self.items.append((statement_hash, statement, evidence))


def solved_certificates(task, choices) -> tuple[dict, ...]:
    sink = _Collect()
    check_design(parse_design(fill(task, choices), "local.petra", REGISTRY), REGISTRY, (SolverSource(),), sink=sink)
    return tuple(encode_certificate(CertificateFile(h, s, e, {"source": "test"})) for h, s, e in sink.items)


class Tasks(unittest.TestCase):
    def test_generators_cover_registered_domains_only(self):
        self.assertTrue(set(GENERATORS) <= set(DOMAINS), "every generator names a registered domain")
        self.assertEqual(set(GENERATORS), {"circuit", "bolt"}, "v0 generates circuit and bolt tasks")

    def test_generation_is_deterministic_in_the_seed(self):
        for domain in GENERATORS:
            self.assertEqual(generate(domain, 5, REGISTRY), generate(domain, 5, REGISTRY), f"{domain} seed 5 repeats")
            self.assertGreater(len({generate(domain, s, REGISTRY).template for s in range(10)}), 1, f"{domain} seeds vary the task")

    def test_an_unknown_domain_is_refused(self):
        with self.assertRaises(KeyError):
            generate("hydraulics", 0, REGISTRY)

    def test_every_legal_fill_parses_with_the_owner_claims(self):
        for domain in GENERATORS:
            for seed in range(3):
                task = generate(domain, seed, REGISTRY)
                design = parse_design(fill(task, {h.name: h.choices[-1] for h in task.holes}), "filled.petra", REGISTRY)
                self.assertTrue(design.claims, f"{task.id} keeps its claims")

    def test_choices_are_registry_parts_cheapest_first(self):
        task = generate("circuit", 0, REGISTRY)
        cables = next(h for h in task.holes if h.name == "w1.cable").choices
        areas = [REGISTRY.parts[c].fixes["area"].lo for c in cables]
        self.assertEqual(areas, sorted(areas), "cables run from the smallest area up")
        self.assertEqual(areas[0], Fraction(3, 2_000_000), "1.5 mm2 is the cheapest cable")
        bolts = next(h for h in generate("bolt", 0, REGISTRY).holes if h.name == "j.bolt").choices
        self.assertTrue(all(REGISTRY.parts[b].kind is PartKind.BOLT for b in bolts), "bolt choices are bolts")
        self.assertFalse(any(b.endswith("_zn") for b in bolts), "coated bolts, which lowering refuses, are not offered")

    def test_fill_refuses_choices_outside_the_holes(self):
        task = generate("circuit", 0, REGISTRY)
        for bad in ({**PASSING, "w1.cable": "cable.unobtainium"}, {k: v for k, v in PASSING.items() if k != "t1.part"}, {**PASSING, "extra": "x"}):
            with self.assertRaises(ValueError, msg=f"{bad} is refused"):
                fill(task, bad)

    def test_a_family_text_widens_the_owner_inputs(self):
        task = generate("circuit", SMALL, REGISTRY)
        box = {"draw": (Fraction(0), Fraction(10)), "run": (Fraction(0), Fraction(18)), "amb": (Fraction(5), Fraction(40))}
        design = parse_design(family_text(task, PASSING, box), "family.petra", REGISTRY)
        self.assertTrue(design.is_family, "the widened design is a family")
        self.assertEqual(set(design.params), {"draw", "run", "amb"}, "with one param per widened input")
        with self.assertRaises(ValueError):
            family_text(task, PASSING, {"draw": (Fraction(0), Fraction(10))})


class Environment(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.library = Library(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def env(self, seed: int) -> tuple[LolaEnv, object]:
        env = LolaEnv("circuit", seed, self.library, REGISTRY)
        return env, env.reset()

    def test_kernel_checked_certificates_earn_a_pass(self):
        env, task = self.env(SMALL)
        reward, report = env.step(Submission(PASSING, solved_certificates(task, PASSING)))
        self.assertEqual(reward, 1.0, "a design the kernel proves earns 1")
        self.assertIsInstance(report.verdict, Pass, "the report is a PASS")

    def test_no_certificates_leave_the_design_unknown(self):
        env, _ = self.env(SMALL)
        reward, report = env.step(Submission(PASSING, ()))
        self.assertEqual(reward, 0.0, "without evidence the environment proves nothing itself")
        self.assertIsInstance(report.verdict, Unknown, "the report is UNKNOWN")

    def test_step_never_runs_a_solver(self):
        env, task = self.env(SMALL)
        certificates = solved_certificates(task, PASSING)
        with mock.patch.object(SolverSource, "offer", side_effect=AssertionError("a solver ran")) as offer:
            reward, report = env.step(Submission(PASSING, certificates))
        offer.assert_not_called()
        self.assertEqual(reward, 1.0, "the certificates alone earn the pass")
        self.assertEqual(report.warnings, (), "no source raised")

    def test_a_refuted_design_costs_one(self):
        env, task = self.env(OVER_SIX)
        reward, report = env.step(Submission(OVERLOADED, solved_certificates(task, OVERLOADED)))
        self.assertEqual(reward, -1.0, "a B6 on a draw above 6 A is refuted")
        self.assertIsInstance(report.verdict, Fail, "the report is a FAIL")

    def test_a_withheld_refutation_is_unknown_not_pass(self):
        env, _ = self.env(OVER_SIX)
        reward, _ = env.step(Submission(OVERLOADED, ()))
        self.assertEqual(reward, 0.0, "withholding the refutation cannot earn more than 0")

    def test_an_edited_statement_is_ignored_with_a_warning(self):
        env, task = self.env(SMALL)
        certificates = list(solved_certificates(task, PASSING))
        edited = dict(certificates[0], statement={**certificates[0]["statement"], "hyps": []})
        reward, report = env.step(Submission(PASSING, (edited, *certificates[1:])))
        self.assertEqual(reward, 0.0, "the remaining certificates do not cover the design")
        self.assertTrue(any("ignored" in w for w in report.warnings), "the report says the certificate was ignored")

    def test_evidence_that_does_not_check_is_rejected(self):
        env, task = self.env(SMALL)
        certificates = solved_certificates(task, PASSING)
        forged = []
        for cert in certificates:
            sym = next(h["sym"] for h in cert["statement"]["hyps"] if h["t"] == "range_hyp")
            forged.append(dict(cert, evidence=encode_evidence(Evidence(Enclosure(Split(sym, Fraction(10**9), Leaf(), Leaf()))))))
        reward, report = env.step(Submission(PASSING, tuple(forged)))
        self.assertEqual(reward, 0.0, "a split outside every cell proves nothing")
        self.assertNotIsInstance(report.verdict, Pass, "the report is not a PASS")

    def test_illegal_choices_and_early_steps_are_refused(self):
        env = LolaEnv("circuit", SMALL, self.library, REGISTRY)
        with self.assertRaises(RuntimeError):
            env.step(Submission(PASSING, ()))
        env.reset()
        with self.assertRaises(ValueError):
            env.step(Submission({**PASSING, "cb1.part": "mcb.B99"}, ()))
        with self.assertRaises(KeyError):
            LolaEnv("hydraulics", 0, self.library, REGISTRY)


class Agent(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.library = Library(self.dir.name)
        self.agent = BaselineAgent(self.library, REGISTRY)

    def tearDown(self):
        self.dir.cleanup()

    def episode(self, domain: str, seed: int):
        env = LolaEnv(domain, seed, self.library, REGISTRY)
        task = env.reset()
        submission = self.agent.act(task)
        reward, report = env.step(submission)
        self.agent.learn(task, submission, reward)
        return reward, report

    def test_the_agent_solves_a_task_and_stores_families(self):
        reward, _ = self.episode("circuit", SMALL)
        self.assertEqual(reward, 1.0, "the environment confirms the agent's pass")
        stats = self.agent.stats()
        self.assertEqual((stats.tasks, stats.passed), (1, 1), "one task, one pass")
        self.assertGreaterEqual(stats.families_added, 1, "the solved design is widened into the library")

    def test_a_repeated_task_is_answered_from_the_library(self):
        self.episode("circuit", SMALL)
        reward, report = self.episode("circuit", SMALL)
        self.assertEqual(reward, 1.0, "the second attempt still passes")
        reused = [o for o in report.outcomes if isinstance(o, Discharged) and o.source == "library"]
        self.assertGreaterEqual(len(reused), 2, "the environment takes both claims from the library, not the submission")
        self.assertGreaterEqual(self.agent.stats().library_hits, 2, "the agent counts the reuse")

    def test_the_agent_solves_a_bolt_task(self):
        """With torque in [40, 50] Nm and a force up to 26 kN, two M12 A4-70 bolts keep
        the joint closed, as coverage's separation check demands, since the plates' share
        per bolt, 0.9 x 13 kN = 11.7 kN, stays under the least preload 40 / (0.22 x 12 mm)
        = 15.15 kN, and each carries F_V + Phi F / n = 50 / (0.16 x 12 mm) + 0.25 x 13 kN
        = 29.29 kN, within 0.9 x 450 MPa x 84.3 mm2 = 34.14 kN, so a pass exists among the
        agent's candidates. One bolt opens the joint past 16.8 kN."""
        reward, _ = self.episode("bolt", LIGHT_BOLT)
        self.assertEqual(reward, 1.0, "the environment confirms a bolt pass")
        self.assertEqual(self.agent.stats().families_added, 1,
                         "the tension claim is stored as one family; a family stores claims, not coverage checks")

    def test_a_reward_below_one_teaches_nothing(self):
        task = generate("circuit", SMALL, REGISTRY)
        self.agent.learn(task, Submission(PASSING, ()), 0.0)
        stats = self.agent.stats()
        self.assertEqual((stats.tasks, stats.passed, stats.families_added), (1, 0, 0), "an UNKNOWN adds no family")
        self.assertEqual(self.library.stats()["families"], 0, "the library is untouched")

    def test_stats_render_the_summary_line(self):
        self.assertEqual(AgentStats(20, 17, 5, 9).render(), "solved 17/20 episodes (library hits 5, families added 9)", "the petra gym summary line")

    def test_run_episodes_counts_every_episode(self):
        stats = run_episodes(("circuit",), 1, SMALL, None)
        self.assertEqual((stats.tasks, stats.passed), (1, 1), "the small circuit task passes")
        with self.assertRaises(ValueError):
            run_episodes((), 1, 0, None)


if __name__ == "__main__":
    unittest.main()
