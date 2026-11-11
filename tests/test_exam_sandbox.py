"""The sandbox of the benchmark harness (bench/exam/sandbox.py), and the harness's refusal to grade without it.

How the sandbox's command line is built is tested anywhere. The gate is tested with the toy benchmark of
tests/exam_toy.py: a run whose grader executes the model's code stops before its first model call when there is no
sandbox, `--no-sandbox` lets it through, and every record says how its grade was made.

The probe runs wherever the grader host has a sandbox, and is skipped elsewhere. It runs one small fixed program
inside and holds what the program could reach to what the sandbox promises. The same program is run outside as
well, to show that it would have seen the difference.

No test here calls a model, fetches a benchmark or runs a real grader.
"""
import ast
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from bench.exam import data, host, records, run as exam, sandbox
from bench.exam.adapters import Adapter, cadtestbench
from tests.exam_toy import TOY, TOY_RUNS
from tests.test_exam import Sitting, saying

BOX = sandbox.Box("/somewhere/bwrap", "0.9.0", covered=("/usr/lib/mounted",))
ARITY = {"--unshare-all": 0, "--die-with-parent": 0, "--new-session": 0, "--clearenv": 0, "--hostname": 1, "--setenv": 2, "--ro-bind": 2,
         "--ro-bind-try": 2, "--symlink": 2, "--tmpfs": 1, "--remount-ro": 1, "--proc": 1, "--dev": 1, "--size": 1, "--chdir": 1}
"""Every option the sandbox may give bwrap, with how many values it takes. A test fails on any other, so an option
that lets something in, such as a writable bind, cannot be added without a test being changed."""

PROBE = r'''
import json, os, re, socket

def attempt(act):
    try:
        return {"ok": True, "got": act()}
    except OSError as exc:
        return {"ok": False, "error": type(exc).__name__, "errno": exc.errno}

def write(folder):
    path = os.path.join(folder, "probe-%d.txt" % os.getpid())
    with open(path, "w") as out:
        out.write("written")
    try:
        return open(path).read()
    finally:
        os.remove(path)

def connect():
    with socket.create_connection((ADDRESS, 80), timeout=5):
        return True

def program(pid):
    try:
        return open("/proc/%d/comm" % pid).read().strip()
    except OSError:
        return "gone since it was listed"

points = sorted({re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), line.split()[4]) for line in open("/proc/self/mountinfo")})
pids = sorted(int(name) for name in os.listdir("/proc") if name.isdigit())
print(json.dumps({
    "canary": attempt(lambda: open(CANARY).read()),
    "home": attempt(lambda: len(os.listdir(HOME))),
    "homes": attempt(lambda: len(os.listdir("/home"))),
    "mnt": attempt(lambda: len(os.listdir("/mnt"))),
    "mnt_c": attempt(lambda: len(os.listdir("/mnt/c"))),
    "connect": attempt(connect),
    "resolve": attempt(lambda: len(socket.getaddrinfo(NAME, 80))),
    "interfaces": sorted(name for _, name in socket.if_nameindex()),
    "work": attempt(lambda: write(".")),
    "writable": [point for point in points if os.path.isdir(point) and attempt(lambda: write(point))["ok"]],
    "outside": {folder: attempt(lambda: write(folder)) for folder in OUTSIDE},
    "covered": {folder: attempt(lambda: len(os.listdir(folder))) for folder in COVERED},
    "shown": attempt(lambda: open(SHOWN + "/fixed.txt").read()),
    "pids": pids, "pid": os.getpid(), "programs": sorted({program(pid) for pid in pids}),
    "env": sorted(os.environ), "cwd": os.getcwd(), "hostname": socket.gethostname(), "root": sorted(os.listdir("/")),
    "etc": sorted(os.listdir("/etc")) if os.path.isdir("/etc") else None,
}))
'''
"""What the probe runs. It tries each thing the sandbox is to stop and says what happened."""
LEFT = r'''
import json, os
left = 0
for name in os.listdir("/proc"):
    try:
        left += name.isdigit() and MARK.encode() in open("/proc/%s/cmdline" % name, "rb").read()
    except OSError:
        pass
print(json.dumps({"left": left}))
'''
"""Run on the host: how many processes there have MARK in their command line."""
ADDRESS = "192.0.2.1"
"""An address kept for documentation (RFC 5737), which is no machine's. With no network, a connection to it fails at once."""


def options(line: list[str]) -> tuple[list[tuple[str, ...]], list[str]]:
    """The options of the bwrap in a command line, each with its values, and the command that follows them."""
    at, found = line.index(BOX.path) + 1, []
    while at < len(line) and line[at].startswith("--"):
        if line[at] not in ARITY:
            raise AssertionError(f"the sandbox gives bwrap {line[at]}, which no test knows")
        found.append(tuple(line[at:at + 1 + ARITY[line[at]]]))
        at += 1 + ARITY[line[at]]
    return found, line[at:]


class Command(unittest.TestCase):
    """How the command line is built. Nothing is run."""

    def build(self, box=BOX, env=None, seconds=300.0) -> tuple[list[str], list[tuple[str, ...]], list[str]]:
        line = sandbox.command(box, [f"{sandbox.ENV}/bin/python", "-I", "-"], {sandbox.ENV: "/host/venv/x", sandbox.DATA: "/host/data/x"},
                               env or {"EXAM_DATA": sandbox.DATA}, seconds)
        return (line, *options(line))

    def test_the_time_limit_is_kept_outside_the_sandbox_and_bwrap_dies_with_it(self):
        line, found, _ = self.build()
        self.assertEqual(line[:4], ["timeout", "--kill-after=5", "300", BOX.path])
        self.assertIn(("--die-with-parent",), found)
        self.assertEqual(self.build(seconds=0.2)[0][2], "1", "no limit of 0, which `timeout` reads as none")

    def test_every_namespace_is_new_and_the_session_too(self):
        _, found, _ = self.build()
        for option in ("--unshare-all", "--new-session", "--clearenv"):
            self.assertIn((option,), found)
        self.assertIn(("--hostname", "exam"), found)
        self.assertIn(("--proc", "/proc"), found)
        self.assertIn(("--dev", "/dev"), found)

    def test_nothing_of_the_host_is_shown_but_usr_three_system_files_and_what_the_caller_names(self):
        _, found, _ = self.build()
        binds = {option[2]: option[1] for option in found if option[0] in ("--ro-bind", "--ro-bind-try")}
        self.assertEqual(binds, {"/usr": "/usr", **{path: path for path in sandbox.SYSTEM}, sandbox.ENV: "/host/venv/x", sandbox.DATA: "/host/data/x"})
        self.assertEqual(sandbox.SYSTEM, ("/etc/ld.so.cache", "/etc/fonts", "/var/cache/fontconfig"))
        for inside in binds:
            self.assertFalse(inside.startswith(("/mnt", "/home", "/root")), inside)
        self.assertEqual({option[2]: option[1] for option in found if option[0] == "--symlink"},
                         {"/bin": "usr/bin", "/lib": "usr/lib", "/lib64": "usr/lib64", "/sbin": "usr/sbin"})

    def test_a_system_folder_that_is_no_link_is_shown_read_only(self):
        box = sandbox.Box(BOX.path, "0.9.0", links=(("/lib64", "usr/lib64"),), folders=("/bin", "/lib"))
        _, found, _ = self.build(box)
        for folder in ("/bin", "/lib"):
            self.assertIn(("--ro-bind", folder, folder), found)
        self.assertEqual([option for option in found if option[0] == "--symlink"], [("--symlink", "usr/lib64", "/lib64")])

    def test_what_is_mounted_below_a_shown_folder_is_covered_and_cannot_be_written(self):
        _, found, _ = self.build()
        at = found.index(("--tmpfs", "/usr/lib/mounted"))
        self.assertEqual(found[at + 1], ("--remount-ro", "/usr/lib/mounted"))
        self.assertGreater(at, found.index(("--ro-bind", "/usr", "/usr")))

    def test_the_only_places_to_write_are_three_capped_folders_in_memory(self):
        _, found, _ = self.build()
        made = [option[1] for option in found if option[0] == "--tmpfs" and ("--remount-ro", option[1]) not in found]
        self.assertEqual(made, ["/dev/shm", "/tmp", "/work"])
        for size, point in ((sandbox.SHM, "/dev/shm"), (sandbox.TMP, "/tmp"), (sandbox.WORK_BYTES, "/work")):
            self.assertEqual(found[found.index(("--tmpfs", point)) - 1], ("--size", str(size)))
        self.assertEqual(found[-3:], [("--chdir", "/work"), ("--remount-ro", "/dev"), ("--remount-ro", "/")])
        self.assertLess(sandbox.SHM + sandbox.TMP + sandbox.WORK_BYTES, 2 << 30)

    def test_an_older_bwrap_is_given_no_option_it_does_not_know(self):
        _, found, _ = self.build(sandbox.Box(BOX.path, "0.6.1"))
        self.assertNotIn("--size", [option[0] for option in found])
        self.assertEqual([option[1] for option in found if option[0] == "--tmpfs"], ["/dev/shm", "/tmp", "/work"])

    def test_the_environment_is_the_plain_one_and_what_the_caller_adds(self):
        with mock.patch.dict(os.environ, {"SOME_API_KEY": "a-secret-value"}):
            line, found, _ = self.build(env={"EXAM_DATA": sandbox.DATA, "PYTHONUTF8": "1"})
        self.assertEqual({option[1]: option[2] for option in found if option[0] == "--setenv"},
                         {"PATH": "/usr/bin:/bin", "HOME": "/work", "TMPDIR": "/work", "LANG": "C.UTF-8", "EXAM_DATA": "/exam/data", "PYTHONUTF8": "1"})
        self.assertLess(found.index(("--clearenv",)), min(i for i, option in enumerate(found) if option[0] == "--setenv"))
        self.assertNotIn("a-secret-value", " ".join(line))
        self.assertNotIn("SOME_API_KEY", " ".join(line))

    def test_the_command_comes_last_and_is_the_callers(self):
        _, _, tail = self.build()
        self.assertEqual(tail, ["/exam/env/bin/python", "-I", "-"])

    def test_no_path_of_this_machine_is_in_the_command_but_what_the_caller_gave(self):
        line, _, _ = self.build()
        for path in (Path.home(), data.ROOT, data.HOME):
            for spelt in (str(path), path.as_posix()):
                self.assertNotIn(spelt, " ".join(line))

    def test_with_no_sandbox_the_same_command_runs_on_the_folders_themselves(self):
        line = sandbox.bare([f"{sandbox.ENV}/bin/python", "-I", "-"], {sandbox.ENV: "/host/venv/x", sandbox.DATA: "/host/data/x"},
                            {"EXAM_DATA": sandbox.DATA, "PYTHONUTF8": "1"}, 300)
        self.assertEqual(line, ["timeout", "--kill-after=5", "300", "env", "EXAM_DATA=/host/data/x", "PYTHONUTF8=1", "/host/venv/x/bin/python", "-I", "-"])
        self.assertEqual(sandbox.bare(["/exam/environment"], {sandbox.ENV: "/host"}, {}, 1)[-1], "/exam/environment", "only a whole path is swapped")


class Entry(unittest.TestCase):
    """`sandbox.run`, the one way a grader is started, with the host mocked."""

    def test_it_refuses_when_there_is_no_sandbox_and_starts_nothing(self):
        with mock.patch.object(sandbox, "look", return_value=(None, "a made-up reason")), mock.patch.object(host, "run") as started:
            with self.assertRaisesRegex(sandbox.Missing, "a made-up reason"):
                sandbox.run(["true"], {}, {}, 5)
            with self.assertRaises(sandbox.Missing):
                sandbox.how(executes=True)
        started.assert_not_called()

    def test_it_runs_in_the_sandbox_it_found_and_outside_only_when_told(self):
        done = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(sandbox, "look", return_value=(BOX, "")), mock.patch.object(host, "run", return_value=done) as started:
            sandbox.run(["true"], {}, {}, 5, input="in")
            self.assertEqual(started.call_args.args[0], sandbox.command(BOX, ["true"], {}, {}, 5))
            self.assertEqual(started.call_args.kwargs, {"input": "in", "timeout": 35})
            sandbox.run(["true"], {}, {}, 5, sandboxed=False)
            self.assertEqual(started.call_args.args[0], ["timeout", "--kill-after=5", "5", "env", "true"])

    def test_how_a_grade_is_made_is_one_of_three_things(self):
        with mock.patch.object(sandbox, "look", return_value=(BOX, "")):
            self.assertEqual(sandbox.how(executes=True), "bwrap 0.9.0")
            self.assertEqual(sandbox.how(executes=True, sandboxed=False), "none")
        with mock.patch.object(sandbox, "look", side_effect=AssertionError("a grader that executes nothing asked for a sandbox")):
            self.assertEqual(sandbox.how(executes=False), "not needed")
            self.assertEqual(sandbox.how(executes=False, sandboxed=False), "not needed")

    def test_a_bwrap_counts_only_when_a_command_ran_in_it_and_it_is_as_it_was_fetched(self):
        known = {"home": "/h", "exam": "/h/exam", "bwrap": "/h/exam/sandbox/bubblewrap/usr/bin/bwrap", "version": "0.9.0", "sha256": "aa", "pinned": "aa",
                 "fetched": True, "links": {"/bin": "usr/bin"}, "folders": [], "covered": [], "uv": None}

        def look(facts, code=0, said=""):
            sandbox.look.cache_clear()
            self.addCleanup(sandbox.look.cache_clear)
            ran = subprocess.CompletedProcess([], code, "", said)
            with mock.patch.object(host, "facts", return_value=facts), mock.patch.object(host, "run", return_value=ran) as started:
                return (*sandbox.look(), started.call_count)

        box, why, calls = look(known)
        self.assertEqual((box, why, calls), (sandbox.Box(known["bwrap"], "0.9.0", (("/bin", "usr/bin"),)), "", 1))
        box, why, calls = look(known, 1, "bwrap: setting up uid map: Permission denied")
        self.assertEqual((box, calls), (None, 1))
        self.assertIn("Permission denied", why)
        box, why, calls = look({**known, "sha256": "bb"})
        self.assertEqual((box, calls), (None, 0), "a bwrap that changed since it was fetched is not run")
        box, why, calls = look({**known, "bwrap": None})
        self.assertEqual((box, calls), (None, 0))
        self.assertIn("bwrap is not on the path", why)
        sandbox.look.cache_clear()
        with mock.patch.object(host, "facts", side_effect=host.Down("WSL did not start")):
            self.assertEqual(sandbox.look(), (None, "WSL did not start"))

    def test_only_so_much_of_what_a_command_prints_is_held(self):
        printed = bytes(range(256)) * 40
        for keep in (1, 100, 5000, len(printed), len(printed) + 1):
            with mock.patch.object(host, "KEEP", keep):
                into: dict[str, bytes] = {}
                host._hold(io.BytesIO(printed), False, into, "out")
                host._hold(io.BytesIO(printed), True, into, "err")
            self.assertEqual((into["out"], into["err"]), (printed[:keep], printed[-keep:]), keep)
        self.assertLessEqual(host.KEEP, 1 << 26)

    def test_a_command_here_gets_bytes_in_and_gives_text_back(self):
        """`host.run` on this machine's own Python, which is the host's only on Linux: the pipes are the same."""
        program = "import sys; data = sys.stdin.buffer.read(); sys.stdout.buffer.write(data + data); sys.stderr.write('said'); sys.exit(3)"
        with mock.patch.object(host, "WSL", False):
            done = host.run([sys.executable, "-c", program], input=b"a\r\nb\n\xc3\xa9")
            self.assertEqual((done.returncode, done.stdout, done.stderr), (3, "a\r\nb\néa\r\nb\né", "said"))
            self.assertEqual(host.run([sys.executable, "-c", program], input="é\n").stdout, "é\né\n", "text goes in as UTF-8, with its line ends as they are")
            with self.assertRaises(subprocess.TimeoutExpired):
                host.run([sys.executable, "-c", "import time; time.sleep(60)"], timeout=1)
            with mock.patch.object(host, "KEEP", 1000):
                loud = host.run([sys.executable, "-c", "import sys; sys.stdout.write('o' * 300000); sys.stderr.write('e' * 300000 + 'end')"])
            self.assertEqual((loud.stdout, loud.stderr), ("o" * 1000, "e" * 997 + "end"))

    def test_an_adapter_that_says_nothing_is_taken_to_execute_the_models_code(self):
        self.assertTrue(Adapter.executes and Adapter.sandboxed)
        self.assertTrue(cadtestbench.ADAPTER.executes)
        self.assertFalse(TOY.executes)
        self.assertTrue(TOY_RUNS.executes)


class Helper(unittest.TestCase):
    """The program a grader's Python is sent, and how a request reaches it."""

    def sent(self, request: dict, sandboxed: bool = True) -> mock.Mock:
        known = {"home": "/h", "exam": "/h/exam"}
        done = subprocess.CompletedProcess([], 0, "{}", "")
        with mock.patch.object(host, "facts", return_value=known), mock.patch.object(sandbox, "run", return_value=done) as started:
            cadtestbench.in_venv("made-up", Path(tempfile.gettempdir()) / "made-up", "cadtestbench", request, 7, sandboxed)
        return started

    def test_a_grader_is_started_through_the_sandbox_with_its_environment_and_the_files_to_read(self):
        call = self.sent({})
        self.assertEqual(call.call_args.args[0], ["/exam/env/bin/python", "-I", "-X", "utf8", "-"])
        there = "/h/exam/data/made-up" if host.WSL else str((Path(tempfile.gettempdir()) / "made-up").resolve())
        self.assertEqual(call.call_args.args[1], {"/exam/env": "/h/exam/venv/made-up", "/exam/data": there})
        self.assertEqual(call.call_args.args[2]["EXAM_DATA"], "/exam/data")
        self.assertEqual((call.call_args.args[3], call.call_args.kwargs["sandboxed"]), (7, True))
        self.assertFalse(self.sent({}, sandboxed=False).call_args.kwargs["sandboxed"])

    def test_the_request_goes_in_with_the_helper_and_comes_out_as_it_was(self):
        request = {"partition": "p", "sample": "s", "answer": "x = '''a\"b'''\nprint(\"\\\\n\")\n# café ✓\nsys.exit(main('other', 0))\n"}
        program = self.sent(request).call_args.kwargs["input"]
        helper = cadtestbench.HELPER.read_text(encoding="utf-8")
        self.assertTrue(program.startswith(helper))
        added = program[len(helper):].strip().splitlines()
        self.assertEqual(len(added), 1, "one line is added, whatever the answer holds")
        call = ast.parse(added[0]).body[0].value.args[0]
        self.assertEqual((call.func.id, call.args[0].value), ("main", "cadtestbench"))
        self.assertEqual(json.loads(call.args[1].args[0].value), request)

    def test_standard_output_is_kept_for_the_result(self):
        """Run here, by this Python, with a mode made up for the test."""
        mode = ("MODES['made_up'] = lambda word: [print('printed by a grader'), os.system('echo printed by a child'), "
                "{'word': word, 'empty': os.listdir('.') == [], 'home': os.path.samefile(os.environ['HOME'], '.')}][2]")
        program = cadtestbench.HELPER.read_text(encoding="utf-8") + f"\n{mode}\nsys.exit(main('made_up', json.loads({json.dumps({'word': 'café'})!r})))\n"
        done = subprocess.run([sys.executable, "-I", "-X", "utf8", "-"], input=program.encode("utf-8"), capture_output=True, timeout=120)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), {"word": "café", "empty": True, "home": True})
        self.assertIn(b"printed by a grader", done.stderr)
        self.assertIn(b"printed by a child", done.stderr)

    def test_a_folder_on_the_host_is_named_by_plain_words_only(self):
        with mock.patch.object(host, "facts", return_value={"home": "/h", "exam": "/h/exam"}):
            self.assertEqual(host.env("cadtestbench"), "/h/exam/venv/cadtestbench")
            for name in ("../up", "a b", "a/b", "", ".."):
                with self.assertRaises(ValueError):
                    host.env(name)


class Gate(Sitting):
    """A run and the sandbox, with the toy benchmark. Whether the host has a sandbox is made up for each test."""

    def host(self, box: sandbox.Box | None):
        found = (box, "" if box else "a made-up reason")
        return mock.patch.multiple(host, named=mock.Mock(return_value=[])), mock.patch.object(sandbox, "look", return_value=found)

    def sit(self, *arguments, box: sandbox.Box | None = None, **settings) -> int:
        named, look = self.host(box)
        with named, look:
            return super().sit(*arguments, **settings)

    def test_a_run_stops_before_any_model_call_when_its_grader_would_run_with_no_sandbox(self):
        calls = []
        with self.assertRaises(SystemExit) as stop:
            self.sit(TOY_RUNS, call=lambda *a: calls.append(a))
        said = str(stop.exception)
        self.assertEqual(calls, [])
        self.assertFalse(self.out.exists())
        self.assertIn("a made-up reason", said)
        self.assertIn("Run once with --fetch to set one up", said)
        self.assertIn("--no-sandbox grades without one", said)
        self.assertEqual(said, sandbox.REFUSAL.format(why="a made-up reason"))

    def test_no_sandbox_is_allowed_when_asked_for_and_every_record_and_the_summary_say_so(self):
        self.assertEqual(self.sit(TOY_RUNS, sandbox=False, call=saying("NOTHING")), 0)
        found = self.records()
        self.assertEqual(len(found), 8, "four tasks, two arms, one attempt")
        self.assertEqual({r["sandbox"] for r in found}, {"none"})
        rows = records.totals(found)
        self.assertEqual([(row["grades"], row["grades_with_no_sandbox"]) for row in rows], [(4, 4), (4, 4)])
        self.assertIn("  " + records.BARE.format(n=8, of=8), records.show(rows).splitlines())
        self.assertIn("no sandbox", records.BARE)

    def test_no_sandbox_means_none_even_where_there_is_one(self):
        self.assertEqual(self.sit(TOY_RUNS, tasks=1, arms=("alone",), sandbox=False, box=BOX), 0)
        self.assertEqual([r["sandbox"] for r in self.records()], ["none"])
        self.assertFalse(TOY_RUNS.sandboxed)
        self.sit(TOY_RUNS, tasks=1, arms=("alone",), seed=2, box=BOX)
        self.assertTrue(TOY_RUNS.sandboxed, "the next run is in the sandbox again")

    def test_with_a_sandbox_every_record_says_which_and_the_summary_says_nothing(self):
        self.assertEqual(self.sit(TOY_RUNS, box=BOX, call=saying("NOTHING")), 0)
        found = self.records()
        self.assertEqual({r["sandbox"] for r in found}, {"bwrap 0.9.0"})
        self.assertEqual(sum(row["grades_with_no_sandbox"] for row in records.totals(found)), 0)
        self.assertNotIn("sandbox", records.show(records.totals(found)))

    def test_a_grader_that_executes_nothing_needs_none(self):
        with mock.patch.object(sandbox, "look", side_effect=AssertionError("the toy grader asked for a sandbox")), \
                mock.patch.object(host, "facts", side_effect=AssertionError("the toy grader asked for the host")):
            self.assertEqual(Sitting.sit(self, TOY, call=saying("NOTHING")), 0)
        found = self.records()
        self.assertEqual({r["sandbox"] for r in found}, {"not needed"})
        self.assertNotIn("sandbox", records.show(records.totals(found)))

    def test_a_run_that_mixes_them_says_how_many_grades_had_none(self):
        self.sit(TOY_RUNS, tasks=1, arms=("alone",), sandbox=False)
        self.sit(TOY_RUNS, tasks=2, arms=("alone",), box=BOX)
        rows = records.totals(self.records())
        self.assertEqual([(row["grades"], row["grades_with_no_sandbox"]) for row in rows], [(2, 1)])
        self.assertIn(records.BARE.format(n=1, of=2), records.show(rows))

    def test_a_record_from_before_the_sandbox_counts_as_graded_with_none(self):
        self.sit(TOY_RUNS, tasks=2, arms=("alone",), box=BOX)
        old = [{name: value for name, value in record.items() if name != "sandbox"} for record in self.records()]
        self.assertEqual(records.totals(old)[0]["grades_with_no_sandbox"], 2)

    def test_a_failed_call_is_no_grade_made_with_no_sandbox(self):
        from bench.exam import model as models
        self.sit(TOY_RUNS, tasks=1, arms=("alone",), sandbox=False, call=lambda *a: models.Reply("", False, 0.1, "exit code 1"))
        row = records.totals(self.records())[0]
        self.assertEqual((row["calls_failed"], row["grades"], row["grades_with_no_sandbox"]), (1, 0, 0))

    def test_the_folders_of_the_host_are_taken_out_of_what_goes_back_to_the_model(self):
        from pathlib import PurePosixPath

        class Telling(type(TOY_RUNS)):
            name = "toytelling"

            def feedback(self, folder, task, answer, timeout):
                return "File /home/somebody/.petra/exam/venv/x/lib/a.py and /home/somebody/notes"

        hidden = [PurePosixPath("/home/somebody/.petra/exam"), PurePosixPath("/home/somebody")]
        with mock.patch.object(host, "named", return_value=hidden), mock.patch.object(sandbox, "look", return_value=(BOX, "")):
            Sitting.sit(self, Telling(), tasks=1, arms=("alone",))
        first, second = self.records()
        self.assertEqual(first["feedback"], "File ./venv/x/lib/a.py and ./notes")
        self.assertNotIn("somebody", second["prompt"])

    def run_main(self, *arguments: str, box: sandbox.Box | None = None) -> tuple[int | str, str]:
        tmp = Path(self.tmp.name)
        printed = io.StringIO()
        named, look = self.host(box)
        with named, look, contextlib.redirect_stdout(printed):
            try:
                code = exam.main(["--benchmark", "tests.exam_toy:TOY_RUNS", "--model", "echo", "--tasks", "2", "--arm", "alone",
                                  "--data", str(tmp / "data"), "--runs", str(tmp / "runs"), *arguments])
            except SystemExit as stop:
                code = stop.code
        return code, printed.getvalue()

    def test_the_command_line_refuses_and_its_flag_lets_it_through(self):
        code, printed = self.run_main()
        self.assertEqual(code, sandbox.REFUSAL.format(why="a made-up reason"), "a message as the exit code is printed and exits 1")
        self.assertFalse((Path(self.tmp.name) / "runs").exists())
        code, printed = self.run_main("--no-sandbox")
        self.assertEqual(code, 0, printed)
        self.assertIn(records.BARE.format(n=2, of=2), printed)
        self.assertEqual({r["sandbox"] for r in records.read(Path(self.tmp.name) / "runs" / "toyruns-seed1-echo.jsonl")}, {"none"})
        code, printed = self.run_main("--seed", "2", box=BOX)
        self.assertEqual(code, 0, printed)
        self.assertNotIn("no sandbox", printed.split("toyruns, model echo, seed 2")[1])


class Probe(unittest.TestCase):
    """One fixed program, run in the sandbox of this machine's grader host and beside it. Skipped where there is none."""

    @classmethod
    def setUpClass(cls):
        sandbox.forget()
        cls.box, why = sandbox.look()
        if cls.box is None:
            raise unittest.SkipTest(f"no sandbox here: {why.splitlines()[0][:200]}")
        cls.known = host.facts()
        cls.token = f"canary-{os.getpid()}"
        cls.canary = f"{cls.known['home']}/.petra-exam-{cls.token}"
        cls.shown = host.run(["mktemp", "-d"]).stdout.strip()
        cls.addClassCleanup(host.run, ["rm", "-rf", cls.canary, cls.shown])
        for path, text in ((cls.canary, cls.token), (f"{cls.shown}/fixed.txt", "fixed")):
            assert host.run(["tee", path], input=text).returncode == 0, path
        names = {"CANARY": cls.canary, "HOME": cls.known["home"], "ADDRESS": ADDRESS, "NAME": "example.com", "SHOWN": sandbox.DATA,
                 "OUTSIDE": ["/", "/usr", "/usr/bin", "/etc", "/dev", "/proc", sandbox.DATA, *cls.box.covered], "COVERED": list(cls.box.covered)}
        program = "".join(f"{name} = {value!r}\n" for name, value in names.items()) + PROBE
        with mock.patch.dict(os.environ, {"SOME_API_KEY": "a-secret-value"}):
            cls.inside = cls.ask(program, sandboxed=True)
            cls.beside = cls.ask(program.replace(f"SHOWN = {sandbox.DATA!r}", f"SHOWN = {cls.shown!r}"), sandboxed=False)

    @classmethod
    def ask(cls, program: str, sandboxed: bool) -> dict:
        done = sandbox.run([host.PYTHON, "-I", "-"], {sandbox.DATA: cls.shown}, {"ADDED": "by the caller"}, 120, input=program, sandboxed=sandboxed)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    def test_it_cannot_read_a_file_in_the_home_folder(self):
        self.assertEqual((self.inside["canary"]["ok"], self.inside["canary"]["error"]), (False, "FileNotFoundError"))
        self.assertEqual((self.inside["home"]["ok"], self.inside["homes"]["ok"]), (False, False), "there is no home folder at all")
        self.assertEqual(self.beside["canary"], {"ok": True, "got": self.token}, "the same program reads it outside the sandbox")

    def test_it_cannot_list_the_windows_drives(self):
        self.assertEqual((self.inside["mnt_c"]["ok"], self.inside["mnt_c"]["error"]), (False, "FileNotFoundError"))
        self.assertFalse(self.inside["mnt"]["ok"], "there is no /mnt")
        if host.WSL:
            self.assertTrue(self.beside["mnt_c"]["ok"], "outside the sandbox, WSL shows drive C")

    def test_it_cannot_open_a_connection_out(self):
        self.assertEqual(self.inside["connect"], {"ok": False, "error": "OSError", "errno": 101},
                         "Linux's ENETUNREACH: there is no network to send on, which is not a refusal or a timeout")
        self.assertEqual(self.inside["interfaces"], ["lo"])
        self.assertGreater(len(self.beside["interfaces"]), 1, "outside the sandbox there is an interface to send on")

    def test_it_cannot_resolve_a_host_name(self):
        self.assertEqual((self.inside["resolve"]["ok"], self.inside["resolve"]["error"]), (False, "gaierror"))

    def test_it_cannot_write_outside_its_work_folder(self):
        for folder, tried in self.inside["outside"].items():
            self.assertFalse(tried["ok"], folder)
        self.assertEqual(self.inside["writable"], ["/dev/shm", "/tmp", "/work"], "of all that is mounted, only the three folders in memory")
        self.assertEqual(self.inside["shown"], {"ok": True, "got": "fixed"}, "what the caller shows it can be read")
        self.assertEqual(host.run(["ls", self.shown]).stdout.split(), ["fixed.txt"])

    def test_it_can_write_in_its_work_folder(self):
        self.assertEqual(self.inside["work"], {"ok": True, "got": "written"})
        self.assertEqual(self.inside["cwd"], "/work")

    def test_it_cannot_see_another_process(self):
        self.assertEqual(self.inside["pids"], [1, 2])
        self.assertEqual(self.inside["pid"], 2)
        self.assertEqual(self.inside["programs"], ["bwrap", "python3"])
        self.assertGreater(len(self.beside["pids"]), 2, "outside the sandbox the same program sees the others")

    def test_it_has_no_environment_but_the_plain_one(self):
        self.assertEqual(set(self.inside["env"]) - {"PWD", "LC_CTYPE"}, {*sandbox.PLAIN, "ADDED"})
        self.assertEqual(self.inside["hostname"], "exam")

    def test_it_sees_the_system_and_nothing_else(self):
        self.assertLessEqual(set(self.inside["root"]), {"bin", "dev", "etc", "exam", "lib", "lib32", "lib64", "libx32", "proc", "sbin", "tmp", "usr", "var", "work"})
        self.assertLessEqual(set(self.inside["etc"]), {"ld.so.cache", "fonts"})
        for folder, listed in self.inside["covered"].items():
            self.assertEqual(listed, {"ok": True, "got": 0}, f"{folder} is mounted below /usr on the host, and is empty inside")

    def test_a_grader_that_runs_past_its_limit_is_stopped_and_leaves_no_process(self):
        mark = f"asleep-{self.token}"
        began = time.monotonic()
        done = sandbox.run([host.PYTHON, "-I", "-c", f"import time; time.sleep(600)  # {mark}"], {}, {}, 2)
        self.assertEqual(done.returncode, 124)
        self.assertLess(time.monotonic() - began, 60)
        for _ in range(20):      # the namespace is torn down just after `timeout` has gone
            left = host.script(LEFT, MARK=mark)["left"]
            if not left:
                break
            time.sleep(0.5)
        self.assertEqual(left, 0, "nothing that ran in the sandbox is still running")
        self.assertGreaterEqual(host.script(LEFT, MARK="python3")["left"], 1, "the same look finds a process that is there: its own")

    def test_a_grader_that_prints_a_great_deal_fills_no_memory_here(self):
        program = "import sys\nfor stream in (sys.stdout, sys.stderr):\n    for _ in range(40):\n        stream.write('x' * (1 << 20))\nsys.stderr.write('the end')\n"
        done = sandbox.run([host.PYTHON, "-I", "-"], {}, {}, 120, input=program)
        self.assertEqual((done.returncode, len(done.stdout), len(done.stderr)), (0, host.KEEP, host.KEEP))
        self.assertTrue(done.stderr.endswith("the end"))

    def test_its_folders_hold_no_more_than_their_caps(self):
        """Each folder's size is read, and only the smallest is filled, so that the test takes little memory itself."""
        if "--size" not in sandbox.command(self.box, ["true"], {}, {}, 1):
            self.skipTest(f"{self.box.label} cannot cap a folder in memory")
        program = ("import json, os\nsizes = {folder: os.statvfs(folder).f_blocks * os.statvfs(folder).f_frsize for folder in ('/dev/shm', '/tmp', '/work')}\n"
                   "try:\n    with open('/dev/shm/big', 'wb') as out:\n        for _ in range(CAP // (1 << 20) + 8):\n            out.write(bytes(1 << 20))\n"
                   "    filled = 'no cap'\nexcept OSError as exc:\n    filled = [exc.errno, os.path.getsize('/dev/shm/big') <= CAP]\n"
                   "print(json.dumps({'sizes': sizes, 'filled': filled}))\n")
        found = json.loads(sandbox.run([host.PYTHON, "-I", "-"], {}, {}, 120, input=f"CAP = {sandbox.SHM}\n" + program).stdout)
        self.assertEqual(found["sizes"], {"/dev/shm": sandbox.SHM, "/tmp": sandbox.TMP, "/work": sandbox.WORK_BYTES})
        self.assertEqual(found["filled"], [28, True], "Linux's ENOSPC, at the cap")

    @unittest.skipUnless(host.WSL, "only Windows keeps a copy of a benchmark's files, in WSL")
    def test_a_benchmarks_files_reach_wsl_as_fetched_and_a_changed_copy_is_seen(self):
        name = f"made-up-{self.token}"
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.txt"
            source.write_bytes(b"made up\r\nand not text: \x00\xff\n")
            folder = Path(tmp) / name
            data.fetch(folder, [data.Source(source.as_uri(), "tasks/a.txt"), data.Source(source.as_uri(), "grader/deep/b.py")], {"at": "v1"})
            self.addCleanup(host.run, ["rm", "-rf", host.where(folder, name)])
            host.mirror(folder, name)
            self.assertEqual(host.changed(folder, name), [])
            self.assertEqual(host.where(folder, name), f"{self.known['exam']}/data/{name}")
            self.assertEqual(host.run(["tee", f"{host.where(folder, name)}/tasks/a.txt"], input="changed").returncode, 0)
            self.assertEqual(host.changed(folder, name), ["tasks/a.txt"])
            with mock.patch.object(sandbox, "look", return_value=(BOX, "")), self.assertRaisesRegex(SystemExit, "missing from WSL or not as they were fetched"):
                exam.ready(type("MadeUp", (Adapter,), {"name": name})(), folder)
            host.mirror(folder, name)
            self.assertEqual(host.changed(folder, name), [], "a second copy takes the place of the first")


if __name__ == "__main__":
    unittest.main()
