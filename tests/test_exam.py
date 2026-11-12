"""The benchmark harness (bench/exam), sat on a toy benchmark with a fake model.

The toy benchmark and the fake model are in tests/exam_toy.py. No test here calls a real
model, fetches a real benchmark or needs a grader's environment: what is tested is the
plumbing. Two arms on the same tasks, the same number of attempts, a report from `petra
check` fed back in the petra arm, the grader's result kept from the model, one record for
each call, the cap on calls, a rerun that goes on where a run stopped, and totals that name
no task.
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from bench.exam import checker, data, model as models, records, run as exam
from bench.exam.adapters import REGISTRY, Grade, code_block, load
from bench.exam.adapters import cadtestbench
from tests.exam_toy import CARD, DESIGN, SECRET, TASKS, TOY, TOY_FEEDBACK, fake

ROOT = Path(__file__).resolve().parents[1]
TOY_FILE = ROOT / "tests" / "exam_toy.py"
GUIDE = checker.GUIDE.read_text(encoding="utf-8").strip()


def scripted(model: str, prompt: str, timeout: float) -> models.Reply:
    return models.Reply(fake(prompt), True, 0.0)


def saying(word: str):
    """The fake model on a prompt with one more word, which tests/exam_toy.py reads."""
    return lambda model, prompt, timeout: models.Reply(fake(f"{prompt} {word}"), True, 0.0)


class Sitting(unittest.TestCase):
    """A run in a folder of its own, outside the repository."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name) / "runs" / "toy.jsonl"
        self.lines: list[str] = []

    def sit(self, adapter=TOY, call=scripted, **settings) -> int:
        settings = exam.Settings(**{"tasks": 4, "model": "fake", **settings})
        return exam.run(adapter, Path(self.tmp.name) / "data" / adapter.name, self.out, settings, call=call, say=self.lines.append)

    def records(self, arm: str | None = None) -> list[dict]:
        return [r for r in records.read(self.out) if arm in (None, r["arm"])]


class Arms(Sitting):
    def test_alone_with_no_feedback_is_one_attempt_a_task(self):
        self.assertEqual(self.sit(arms=("alone",)), 0)
        found = self.records()
        self.assertEqual(sorted(r["task"] for r in found), sorted(TASKS))
        self.assertEqual({(r["attempt"], r["final"]) for r in found}, {(1, True)})
        self.assertEqual({r["grade"]["outcome"] for r in found}, {"wrong"}, "the fake model's first answer is one below the range")
        self.assertTrue(all(r["petra"] is None and r["feedback"] is None for r in found))

    def test_alone_with_feedback_retries_and_sees_its_own_reply_and_the_feedback(self):
        self.assertEqual(self.sit(TOY_FEEDBACK, arms=("alone",)), 0)
        first, second = (self.records()[i] for i in (0, 1))
        self.assertEqual((first["attempt"], first["final"], second["attempt"], second["final"]), (1, False, 2, True))
        self.assertEqual(first["feedback"], f"Your number was read as {first['answer']}.")
        self.assertIn("Your previous reply was:\n\n" + first["reply"], second["prompt"])
        self.assertIn(first["feedback"], second["prompt"])
        self.assertIn("Give your final answer", second["prompt"])
        self.assertTrue(second["changed"])
        self.assertEqual((first["grade"]["outcome"], second["grade"]["outcome"]), ("wrong", "pass"))
        self.assertNotIn("Petra", second["prompt"])

    def test_the_attempts_are_the_same_in_both_arms(self):
        self.sit(TOY_FEEDBACK, tasks=1, attempts=3)
        for arm in records.ARMS:
            self.assertEqual([(r["attempt"], r["final"]) for r in self.records(arm)], [(1, False), (2, False), (3, True)], arm)
        self.assertIn("Give your next answer", self.records("alone")[1]["prompt"])
        self.assertIn("You may hand in a design and a card again.", self.records("petra")[1]["prompt"])

    def test_petra_gets_the_guide_and_a_report_on_what_it_hands_in(self):
        self.assertEqual(self.sit(tasks=2, arms=("petra",)), 0)
        first, second = (self.records()[i] for i in (0, 1))
        self.assertIn(GUIDE, first["prompt"])
        # The lap rests a cell on a waiver, so petra check says PASS_WAIVED and exits 6.
        self.assertEqual((first["petra"]["status"], first["petra"]["handed_in"], first["petra"]["exit"]), ("PASS_WAIVED", True, 6))
        self.assertEqual((first["petra"]["design"], first["petra"]["card"]), (DESIGN, CARD))
        self.assertEqual(first["petra"]["text"].splitlines()[0], "lap-splice-waived: PASS_WAIVED")
        self.assertFalse(first["final"])
        self.assertIn("Petra's report on what you handed in:\n\n" + first["petra"]["text"], second["prompt"])
        self.assertIn(first["reply"].strip(), second["prompt"])
        self.assertEqual((second["attempt"], second["final"], second["changed"]), (2, True, True))
        self.assertEqual(second["petra"]["status"], "NONE", "the retry hands nothing in")

    def test_the_blocks_handed_to_petra_are_not_part_of_the_answer(self):
        self.sit(tasks=1, arms=("petra",))
        first = self.records()[0]
        self.assertIn("```petra", first["reply"])
        low = TASKS[first["task"]][1]
        self.assertEqual(first["answer"], str(low - 1), "the last number of the reply outside the two blocks")

    def test_the_alone_arm_is_told_nothing_of_petra(self):
        self.sit(tasks=2, call=saying("NOTHING"))
        self.assertTrue(all("Petra" in r["prompt"] for r in self.records("petra")))
        for record in self.records("alone"):
            self.assertNotIn("Petra", record["prompt"])
            self.assertNotIn("petra", record["prompt"])
            self.assertIsNone(record["petra"])

    def test_petra_with_nothing_handed_in_is_one_attempt_and_is_counted_as_silence(self):
        self.assertEqual(self.sit(tasks=2, arms=("petra",), call=saying("NOTHING")), 0)
        found = self.records()
        self.assertEqual([(r["attempt"], r["final"], r["petra"]["status"]) for r in found], [(1, True, "NONE")] * 2)
        row = records.totals(found)[0]
        self.assertEqual((row["petra"]["replies"], row["petra"]["said_something"], row["petra"]["reports_fed_back"]), (2, 0, 0))

    def test_a_design_petra_refuses_is_a_report_all_the_same(self):
        self.sit(tasks=1, arms=("petra",), call=saying("BROKEN"))
        first, second = self.records()
        self.assertEqual((first["petra"]["status"], first["petra"]["exit"], first["final"]), ("REFUSED", 3, False))
        self.assertIn(first["petra"]["text"], second["prompt"])
        row = records.totals(self.records())[0]
        self.assertEqual((row["petra"]["said_something"], row["petra"]["by_status"]), (1, {"REFUSED": 1, "NONE": 1}))

    def test_both_arms_get_the_same_tasks_and_a_seed_draws_them(self):
        self.sit(tasks=2, call=saying("NOTHING"))
        self.assertEqual(sorted(r["task"] for r in self.records("alone")), sorted(r["task"] for r in self.records("petra")))
        folder = Path(self.tmp.name)
        self.assertEqual(exam.chosen(TOY, folder, 2, 7), exam.chosen(TOY, folder, 2, 7))
        self.assertEqual(len({tuple(exam.chosen(TOY, folder, 2, seed)) for seed in range(20)}) > 1, True)
        self.assertEqual(sorted(exam.chosen(TOY, folder, 99, 1)), sorted(TASKS), "a benchmark with fewer tasks gives them all")

    def test_no_prompt_ever_holds_the_graders_result(self):
        self.sit(TOY_FEEDBACK, attempts=3, call=saying("NOTHING"))
        found = self.records()
        self.assertEqual(len(found), 4 * 2 * 3)
        self.assertTrue(all(r["grade"]["detail"] == {"said": SECRET} for r in found), "every attempt is graded")
        self.assertEqual({r["grade"]["outcome"] for r in found}, {"wrong", "pass"})
        for record in found:
            self.assertNotIn(SECRET, record["prompt"])
            for word in ("pass", "wrong", "no_answer", "grade", "score"):
                self.assertNotIn(word, record["prompt"].replace(GUIDE, "").lower())

    def test_a_reply_with_no_answer_is_graded_as_none(self):
        self.sit(tasks=1, arms=("alone",), call=saying("SILENT"))
        record = self.records()[0]
        self.assertEqual((record["answer"], record["answer_sha256"], record["grade"]["outcome"]), (None, None, "no_answer"))

    def test_a_record_holds_what_was_sent_and_what_came_back(self):
        self.sit(tasks=1, arms=("alone",), seed=5, shakedown=True)
        record = self.records()[0]
        self.assertEqual((record["format"], record["benchmark"], record["arm"], record["seed"], record["model"]),
                         ("petra-exam/0", "toy", "alone", 5, "fake"))
        self.assertEqual(record["prompt"], TOY.prompt(Path("."), record["task"]))
        self.assertEqual(record["prompt_sha256"], data.text_hash(record["prompt"]))
        self.assertEqual(record["reply_sha256"], data.text_hash(record["reply"]))
        self.assertEqual(record["answer_sha256"], data.text_hash(record["answer"]))
        self.assertEqual(record["chars"], {"prompt": len(record["prompt"]), "reply": len(record["reply"])})
        self.assertEqual(sorted(record["seconds"]), ["attempt", "feedback", "grade", "model", "petra"])
        self.assertTrue(record["shakedown"] and record["model_ok"] and record["at"].endswith("+00:00"))


class Limits(Sitting):
    def test_a_run_stops_at_the_cap_and_a_rerun_goes_on_where_it_stopped(self):
        self.assertEqual(self.sit(TOY_FEEDBACK, max_calls=5, call=saying("NOTHING")), 2)
        self.assertEqual(len(self.records()), 5)
        self.assertIn("stopped at the cap of 5 model calls", self.lines[-1])
        self.assertEqual(self.sit(TOY_FEEDBACK, max_calls=60, call=saying("NOTHING")), 0)
        found = self.records()
        keys = [(r["task"], r["arm"], r["attempt"]) for r in found]
        self.assertEqual(len(keys), len(set(keys)), "no attempt is made twice")
        self.assertEqual(len(found), 4 * 2 * 2, "four tasks, two arms, two attempts")
        self.assertEqual(sum(r["final"] for r in found), 8)

    def test_a_retry_after_a_rerun_reads_the_reply_the_file_holds(self):
        self.sit(TOY_FEEDBACK, tasks=1, arms=("alone",), max_calls=1)
        self.sit(TOY_FEEDBACK, tasks=1, arms=("alone",))
        first, second = self.records()
        self.assertIn(first["reply"], second["prompt"])
        self.assertTrue(second["changed"])

    def test_a_rerun_of_a_finished_run_calls_no_model(self):
        self.sit(TOY_FEEDBACK, call=saying("NOTHING"))
        before = self.out.read_bytes()

        def never(model, prompt, timeout):
            raise AssertionError("a finished run made a model call")

        self.assertEqual(self.sit(TOY_FEEDBACK, call=never), 0)
        self.assertEqual(self.out.read_bytes(), before)

    def test_another_model_or_a_shakedown_does_not_count_as_done(self):
        self.sit(tasks=1, arms=("alone",))
        self.sit(tasks=1, arms=("alone",), model="other")
        self.sit(tasks=1, arms=("alone",), shakedown=True)
        self.sit(tasks=1, arms=("alone",), shakedown=True)
        self.assertEqual([(r["model"], r["shakedown"]) for r in self.records()], [("fake", False), ("other", False), ("fake", True)])

    def test_three_failed_calls_in_a_row_stop_the_run(self):
        calls = []

        def down(model, prompt, timeout):
            calls.append(prompt)
            return models.Reply("", False, 0.1, "exit code 1: not logged in")

        self.assertEqual(self.sit(call=down), 1)
        self.assertEqual(len(calls), 3)
        found = self.records()
        self.assertEqual([(r["model_ok"], r["model_error"], r["grade"]) for r in found], [(False, "exit code 1: not logged in", None)] * 3)
        self.assertIn("3 model calls in a row failed", self.lines[-1])

    def test_a_failed_call_is_made_again_on_a_rerun(self):
        replies = iter([models.Reply("", False, 0.1, "no answer within 1 s")])
        self.sit(tasks=1, arms=("alone",), call=lambda *a: next(replies))
        self.assertEqual(self.sit(tasks=1, arms=("alone",)), 0)
        self.assertEqual([(r["attempt"], r["model_ok"], r["final"]) for r in self.records()], [(1, False, False), (1, True, True)])
        row = records.totals(self.records())[0]
        self.assertEqual((row["calls"], row["calls_failed"], row["tasks_answered"]), (2, 1, 1))


class Model(unittest.TestCase):
    def test_a_command_gets_the_prompt_on_stdin_and_its_output_is_the_reply(self):
        prompt = TOY.prompt(Path("."), "toy-b")
        reply = models.call(f'"{sys.executable}" "{TOY_FILE}"', prompt, 60)
        self.assertEqual((reply.ok, reply.text, reply.error), (True, "8", None))

    def test_echo_is_the_prompt(self):
        self.assertEqual(models.call("echo", "a prompt\nof two lines", 1), models.Reply("a prompt\nof two lines", True, 0.0))

    def test_a_command_that_fails_prints_nothing_or_runs_too_long_is_no_answer(self):
        python = f'"{sys.executable}" -c'
        failed = models.call(f'{python} "import sys; print(1); sys.stderr.write(str(2)); sys.exit(7)"', "x", 60)
        self.assertEqual((failed.ok, failed.error), (False, "exit code 7: 2"))
        silent = models.call(f'{python} "pass"', "x", 60)
        self.assertEqual((silent.ok, silent.text), (False, ""))
        self.assertIn("printed nothing", silent.error)
        slow = models.call(f'{python} "import time; time.sleep(30)"', "x", 1)
        self.assertEqual((slow.ok, slow.error), (False, "no answer within 1 s"))
        self.assertFalse(models.call("no-such-command-anywhere --flag", "x", 5).ok)

    def test_the_default_command_is_a_text_function(self):
        """No tools, one turn, no settings, plugins or servers, no session kept, and a
        folder under /tmp, so the command's own context names no folder of the user's."""
        command = models.PRESETS[models.DEFAULT]
        self.assertEqual(command[:4], ["wsl", "-e", "bash", "-lc"])
        for flag in ("cd /tmp/exam-model", "claude -p", "--model sonnet", "--tools ''", "--max-turns 1", "--safe-mode",
                     "--setting-sources ''", "--strict-mcp-config", "--no-session-persistence", "--system-prompt"):
            self.assertIn(flag, command[4])
        self.assertEqual(models.describe("echo"), "echo (built in)")
        self.assertEqual(models.describe("some command"), "some command")


class Checker(unittest.TestCase):
    def test_a_reply_is_split_into_the_answer_the_design_and_the_card(self):
        reply = "An answer.\n```python\nx = 1\n```\n```petra\nA\n```\ntext\n``` card \nB\n```\n```petra\nsecond\n```\nend\n"
        self.assertEqual(checker.split(reply), ("An answer.\n```python\nx = 1\n```\ntext\nend\n", "A\n", "B\n"))
        self.assertEqual(checker.split("no blocks"), ("no blocks", None, None))

    def test_nothing_handed_in_is_no_report(self):
        self.assertEqual(checker.check(None, None, 5).status, "NONE")
        alone = checker.check(None, CARD, 5)
        self.assertEqual((alone.status, alone.handed_in), ("NONE", False))
        self.assertIn("with no design", alone.text)

    def test_the_statuses_are_the_ones_petra_prints(self):
        for name, status, code in (("lap_fail", "FAIL", 1), ("lap_unknown", "UNKNOWN", 2)):
            design, card = ((ROOT / "examples" / "deck" / f"{name}.{kind}").read_text(encoding="utf-8") for kind in ("petra", "card"))
            report = checker.check(design, card, 120)
            self.assertEqual((report.status, report.exit), (status, code), name)
            self.assertTrue(report.text.splitlines()[0].endswith(f": {status}"))

    def test_a_report_holds_no_path_of_this_machine(self):
        report = checker.check(DESIGN, None, 120)
        self.assertEqual((report.status, report.exit), ("REFUSED", 3), "a design with no card is an input error")
        for path in (Path.home(), ROOT, Path(tempfile.gettempdir())):
            for spelt in (str(path), path.as_posix()):
                self.assertNotIn(spelt.lower(), report.text.lower())
        self.assertIn("design.card", report.text)

    def test_a_crash_is_not_taken_for_a_verdict(self):
        """Petra's exit code 4 is any internal error, and a crash of the interpreter exits 1."""
        trace = "Traceback (most recent call last):\n  ...\n"
        for code, printed, status in ((1, trace + "KeyError: 'x'\n", "ERROR"), (4, trace + "ModuleNotFoundError: No module named 'x'\n", "ERROR"),
                                      (4, trace + "petra.verify.Disagreement: design.petra: petra-verify gives FAIL\n", "DISAGREE"),
                                      (3, "usage: petra check\n", "ERROR"), (3, "petra: design.petra:1:1: expected the header\n", "REFUSED"),
                                      (0, "lap: FAIL\n", "ERROR"), (2, "lap: UNKNOWN\nneeds ...\n", "UNKNOWN"), (77, "", "ERROR")):
            with mock.patch.object(checker.subprocess, "run", return_value=subprocess.CompletedProcess([], code, "", printed)):
                self.assertEqual(checker.check(DESIGN, CARD, 5).status, status, (code, printed))
        with mock.patch.object(checker.subprocess, "run", side_effect=subprocess.TimeoutExpired("petra", 5)):
            self.assertEqual(checker.check(DESIGN, CARD, 5).status, "ERROR")
        self.assertNotIn("ERROR", checker.SAID)
        self.assertNotIn("DISAGREE", checker.SAID)

    def test_paths_are_taken_out_however_they_are_spelt(self):
        folder = Path.home() / "a-made-up-folder"
        text = f"at {folder}\\x.py and {folder.as_posix()}/y.py and {str(folder).replace(chr(92), chr(92) * 2)} and {str(folder).upper()}"
        self.assertEqual(checker.scrub(text, folder), "at .\\x.py and ./y.py and . and .")
        self.assertEqual(checker.scrub(f"in {ROOT.as_posix()}/petra/cli.py"), "in ./petra/cli.py")


class Totals(Sitting):
    def test_the_totals_count_what_happened(self):
        self.sit(TOY_FEEDBACK, tasks=2, shakedown=True)
        alone, petra = records.totals(self.records())
        for row in (alone, petra):
            self.assertEqual((row["tasks_answered"], row["tasks_unfinished"], row["calls"], row["calls_failed"]), (2, 0, 4, 0))
            self.assertEqual((row["passed"], row["mean_score"], row["outcomes"]), (2, 1.0, {"pass": 2}))
            self.assertEqual((row["passed_on_first_attempt"], row["tasks_with_a_retry"], row["retries"]), (0, 2, 2))
            self.assertEqual((row["retries_that_changed_the_answer"], row["retries_fail_to_pass"], row["retries_pass_to_fail"]), (2, 2, 0))
            self.assertEqual(row["prompt_chars"], sum(len(r["prompt"]) for r in self.records(row["arm"])))
        self.assertNotIn("petra", alone)
        self.assertEqual(petra["petra"]["by_status"], {"PASS_WAIVED": 2, "NONE": 2}, "the waived lap's exit 6, as above")
        self.assertEqual((petra["petra"]["replies"], petra["petra"]["said_something"]), (4, 2))
        self.assertEqual((petra["petra"]["reports_fed_back"], petra["petra"]["next_answer_changed_after_a_report"]), (2, 2))

    def test_a_wrong_answer_that_stays_wrong_is_counted_as_wrong(self):
        self.sit(tasks=3, arms=("alone",))
        row = records.totals(self.records())[0]
        self.assertEqual((row["passed"], row["mean_score"], row["outcomes"], row["retries"]), (0, 0.0, {"wrong": 3}, 0))

    def test_an_unfinished_task_is_not_counted_as_answered(self):
        self.sit(TOY_FEEDBACK, tasks=2, arms=("alone",), max_calls=3)
        row = records.totals(self.records())[0]
        self.assertEqual((row["tasks_answered"], row["tasks_unfinished"], row["passed"]), (1, 1, 1))

    def test_the_totals_and_what_a_run_prints_name_no_task_and_quote_none(self):
        self.sit(TOY_FEEDBACK, shakedown=True, call=saying("NOTHING"))
        found = self.records()
        printed = "\n".join([records.show(records.totals(found)), json.dumps(records.totals(found)), *self.lines])
        for record in found:
            for held in (record["task"], record["prompt"], record["reply"], record["feedback"], SECRET):
                if held and len(held) > 8:      # a reply of the fake model can be one number, and totals have numbers
                    self.assertNotIn(held, printed)
        for text, _, _ in TASKS.values():
            self.assertNotIn(text, printed)
        self.assertEqual(len(self.lines), 16 + 1, "a line for each call and one at the end")
        self.assertNotRegex("\n".join(self.lines), r"pass|wrong|PASS|REFUSED|NONE", "no line gives the result of one task")

    def test_a_shakedown_says_that_its_numbers_mean_nothing(self):
        self.sit(tasks=1, arms=("alone",), shakedown=True)
        self.assertIn(records.NOTE, records.show(records.totals(self.records())))
        self.assertIn("mean nothing", records.NOTE)
        self.sit(tasks=1, arms=("alone",), seed=2)
        self.assertEqual(records.show(records.totals([r for r in self.records() if r["seed"] == 2])).count(records.NOTE), 0)
        self.assertEqual(records.show([]), "no records")


class CommandLine(unittest.TestCase):
    def run_module(self, module: str, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", module, *arguments], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", stdin=subprocess.DEVNULL, timeout=300)

    def test_a_run_and_its_summary_from_the_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            where = ["--runs", str(Path(tmp) / "runs")]
            done = self.run_module("bench.exam.run", "--benchmark", "tests.exam_toy:TOY", "--arm", "alone", "--tasks", "3", "--seed", "4",
                                   "--model", "echo", "--fetch", "--shakedown", "--data", str(Path(tmp) / "data"), *where)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn("fetched toy: 4 tasks", done.stdout)
            self.assertIn("every chosen task has its final answer", done.stdout)
            self.assertIn("toy, model echo, seed 4", done.stdout)
            self.assertIn(records.NOTE, done.stdout)
            self.assertEqual([p.name for p in (Path(tmp) / "runs").iterdir()], ["toy-seed4-echo-shakedown.jsonl"])
            summary = self.run_module("bench.exam.summary", *where)
            self.assertEqual(summary.returncode, 0, summary.stderr)
            self.assertIn("alone  tasks answered 3, unfinished 0; calls 3, of which failed 0", summary.stdout)
            self.assertIn("final answers: passed 3 of 3", summary.stdout, "the echo of a toy prompt ends in the top of its range")
            as_json = json.loads(self.run_module("bench.exam.summary", "--json", *where).stdout)
            self.assertEqual((as_json[0]["benchmark"], as_json[0]["passed"]), ("toy", 3))
            for name in TASKS:
                self.assertNotIn(name, done.stdout + summary.stdout)

    def test_a_folder_inside_the_repository_or_a_synced_one_is_refused(self):
        done = self.run_module("bench.exam.run", "--benchmark", "tests.exam_toy:TOY", "--model", "echo", "--runs", str(ROOT / "bench" / "runs"))
        self.assertEqual(done.returncode, 2)
        self.assertIn("inside the repository", done.stderr)
        self.assertFalse((ROOT / "bench" / "runs").exists())
        self.assertEqual(data.refused(ROOT), "inside the repository")
        self.assertEqual(data.refused(Path(tempfile.gettempdir()) / "OneDrive - Someone" / "runs"), "inside a synced folder")
        self.assertIsNone(data.refused(Path(tempfile.gettempdir()) / "runs"))

    def test_a_command_line_as_the_model_gets_a_file_name_of_its_own(self):
        runs = Path("runs")
        self.assertEqual(exam.run_file(runs, "toy", 1, "claude-wsl").name, "toy-seed1-claude-wsl.jsonl")
        self.assertEqual(exam.run_file(runs, "toy", 1, "claude-wsl", shakedown=True).name, "toy-seed1-claude-wsl-shakedown.jsonl")
        name = exam.run_file(runs, "toy", 1, "some command --with flags").name
        self.assertRegex(name, r"^toy-seed1-command-[0-9a-f]{10}\.jsonl$")


class Adapters(unittest.TestCase):
    def test_every_adapter_of_the_registry_loads_under_its_name(self):
        for name in REGISTRY:
            adapter = load(name)
            self.assertEqual(adapter.name, name)
            self.assertTrue(adapter.about)
        self.assertIs(load("tests.exam_toy:TOY"), TOY)
        with self.assertRaises(KeyError):
            load("no-such-benchmark")

    def test_the_default_folders_are_outside_the_repository(self):
        for folder in (data.DATA, data.RUNS):
            self.assertNotIn(ROOT, folder.resolve().parents)
        self.assertEqual(data.DATA.parent, data.HOME)

    def test_the_code_of_a_reply_is_its_last_python_block(self):
        self.assertEqual(code_block("```python\na = 1\n```\nor better\n```py\nb = 2\n```\n"), "b = 2\n")
        self.assertEqual(code_block("```\nbare = 1\n```"), "bare = 1\n")
        self.assertEqual(code_block("```text\nnotes\n```\n```python\nc = 3\n```\n```\nbare\n```"), "c = 3\n")
        self.assertIsNone(code_block("no code"))
        self.assertIsNone(code_block("```json\n{}\n```"))
        self.assertIsNone(code_block("```python\n\n```"))

    def test_a_grade_has_one_of_the_outcomes(self):
        self.assertTrue(Grade("pass", 1.0).passed)
        self.assertFalse(Grade("wrong", 0.5).passed)
        self.assertEqual(Grade("invalid", 0.0, {"a": 1}).to_dict(), {"outcome": "invalid", "score": 0.0, "detail": {"a": 1}, "seconds": 0.0, "passed": False})
        with self.assertRaises(ValueError):
            Grade("fine", 1.0)

    def test_a_cadtestbench_result_is_read_as_the_benchmarks_own_aggregate_reads_it(self):
        def result(**summary) -> dict:
            tests = [{"id": 1, "category": "made_up", "status": "fail", "message": "m"}, {"id": 2, "category": "made_up", "status": "pass"}]
            return {"metrics": {"cadtest": {"metadata": {"summary": {"total_cadtests": 2, "passed": 1, "model_compile_error": False,
                                                                     "evaluation_error": None, **summary}, "cadtests": tests}}}}

        wrong = cadtestbench.read(result())
        self.assertEqual((wrong.outcome, wrong.score, wrong.detail["failed"]), ("wrong", 0.5, [{"id": 1, "category": "made_up", "message": "m"}]))
        self.assertEqual(cadtestbench.read(result(passed=2)).outcome, "pass")
        self.assertEqual(cadtestbench.read(result(passed=0, total_cadtests=0)).outcome, "wrong", "a task with no test is not passed")
        self.assertEqual(cadtestbench.read(result(passed=0, model_compile_error=True)).outcome, "invalid")
        self.assertEqual(cadtestbench.read(result(passed=0, evaluation_error="cadtests_load_error")).outcome, "grader_error")
        self.assertEqual(cadtestbench.read({"error_message": "boom", "metrics": None}).outcome, "grader_error")

    def test_a_fetched_file_is_held_to_its_pinned_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.txt"
            source.write_bytes(b"made up\n")
            folder, digest = Path(tmp) / "bench", data.sha256(b"made up\n")
            manifest = data.fetch(folder, [data.Source(source.as_uri(), "a/file.txt", digest)], {"at": "v1"})
            self.assertEqual((folder / "a" / "file.txt").read_bytes(), b"made up\n")
            self.assertEqual(manifest, {"version": {"at": "v1"}, "files": [{"path": "a/file.txt", "url": source.as_uri(), "sha256": digest}]})
            self.assertEqual(data.manifest(folder), manifest)
            source.unlink()
            self.assertEqual(data.fetch(folder, [data.Source(source.as_uri(), "a/file.txt", digest)], {"at": "v1"}), manifest,
                             "a file that is there with its hash is not fetched again")
            source.write_bytes(b"changed\n")
            with self.assertRaisesRegex(ValueError, "the adapter pins"):
                data.fetch(folder, [data.Source(source.as_uri(), "b.txt", digest)], {})
            with self.assertRaisesRegex(ValueError, "not inside"):
                data.fetch(folder, [data.Source(source.as_uri(), "../outside.txt")], {})
            self.assertFalse((Path(tmp) / "outside.txt").exists())

    def test_a_run_refuses_files_that_are_not_as_they_were_fetched(self):
        """A grader runs a model's code beside the benchmark's files, so a run checks them first."""
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.txt"
            source.write_bytes(b"one\n")
            folder = Path(tmp) / "bench"
            data.fetch(folder, [data.Source(source.as_uri(), "tasks/a.txt")], {})
            self.assertEqual(data.changed(folder), [])
            (folder / "tasks" / "a.txt").write_bytes(b"two\n")
            self.assertEqual(data.changed(folder), ["tasks/a.txt"])
            with self.assertRaisesRegex(SystemExit, "not as they were fetched"):
                exam.run(TOY, folder, Path(tmp) / "runs" / "x.jsonl", exam.Settings(model="fake"), call=scripted, say=lambda line: None)
            self.assertFalse((Path(tmp) / "runs").exists())
            (folder / "tasks" / "a.txt").unlink()
            self.assertEqual(data.changed(folder), ["tasks/a.txt"])
            self.assertEqual(data.changed(Path(tmp) / "never-fetched"), [])

    def test_a_grader_gets_none_of_the_environment_but_what_a_program_needs(self):
        with mock.patch.dict(os.environ, {"SOME_API_KEY": "a secret", "PATH": os.environ.get("PATH", "")}):
            env = data.plain_env(EXTRA="1")
        self.assertNotIn("SOME_API_KEY", env)
        self.assertEqual(env["EXTRA"], "1")
        self.assertIn("PATH", env)
        self.assertTrue(set(env) <= {*data.KEPT, "EXTRA"})

    def test_an_archive_leaves_on_disk_only_what_the_patterns_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            packed = io.BytesIO()
            with zipfile.ZipFile(packed, "w") as archive:
                for name, text in (("top/tasks/one.json", "{}"), ("top/tasks/answers/one.py", "x"), ("top/grader/g.py", "y"), ("top/data/big.jsonl", "z")):
                    archive.writestr(name, text)
            source = Path(tmp) / "repo.zip"
            source.write_bytes(packed.getvalue())
            folder = Path(tmp) / "bench"
            manifest = data.fetch_archive(folder, source.as_uri(), ["tasks/*.json", "grader/*.py"], {"at": "c1"})
            self.assertEqual(sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()),
                             ["SOURCE.json", "grader/g.py", "tasks/one.json"])
            self.assertEqual(manifest["archive_sha256"], data.sha256(packed.getvalue()))
            source.unlink()
            again = data.fetch_archive(folder, source.as_uri(), ["tasks/*.json", "grader/*.py"], {"at": "c1"}, manifest["digest"])
            self.assertEqual(again["files"], manifest["files"], "kept files with the pinned digest are not fetched again")
            source.write_bytes(packed.getvalue())
            with self.assertRaisesRegex(ValueError, "the adapter pins"):
                data.fetch_archive(Path(tmp) / "other", source.as_uri(), ["tasks/*.json"], {}, manifest["digest"])


if __name__ == "__main__":
    unittest.main()
