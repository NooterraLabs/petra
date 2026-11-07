"""`petra mcp`: an MCP client starts the server, writes JSON-RPC requests to its stdin one
per line, and reads one response per request from its stdout (petra/mcp.py).

The server is driven here as a client drives it, through a real process and its pipes.
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

from petra import mcp

ROOT = Path(__file__).resolve().parents[1]
FAILING = ROOT / "tests" / "fixtures" / "readout" / "job5_fail_60k.petra"


def request(rid, method, params=None):
    return {"jsonrpc": "2.0", "id": rid, "method": method, **({"params": params} if params is not None else {})}


def call(rid, tool, **arguments):
    return request(rid, "tools/call", {"name": tool, "arguments": arguments})


class Session(unittest.TestCase):
    """One session: the handshake, the tool list, and a call to each tool."""

    @classmethod
    def setUpClass(cls):
        lines = [
            request(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "test", "version": "0"}}),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            request(2, "tools/list"),
            call(3, "check", text=FAILING.read_text(encoding="utf-8")),
            call(4, "new", kind="shear_tab", name="tab"),
            call(5, "kinds", name="nonesuch"),
            call(6, "registry_list", prefix="A325"),
            call(7, "docs", name="skill"),
            call(8, "check", path=str(ROOT / "examples" / "steel" / "shear_tab.petra")),
            call(9, "check", text="petra 0\ndesign {\n"),
            request(10, "frobnicate"),
            request(11, "ping"),
        ]
        stdin = "\n".join(json.dumps(m) for m in lines) + "\nnot json\n"
        done = subprocess.run([sys.executable, "-m", "petra", "mcp"], input=stdin.encode("utf-8"), cwd=ROOT,
                              capture_output=True, timeout=600)
        cls.code = done.returncode
        cls.replies = [json.loads(line) for line in done.stdout.decode("utf-8").splitlines()]
        cls.by_id = {r["id"]: r for r in cls.replies}

    def test_it_exits_0_when_stdin_closes_and_answers_every_request_once(self):
        self.assertEqual(self.code, 0)
        self.assertEqual(sorted(r["id"] for r in self.replies if r["id"] is not None), list(range(1, 12)),
                         "one reply per request, none for the notification")
        self.assertTrue(all(r["jsonrpc"] == "2.0" for r in self.replies))

    def test_initialize_echoes_a_known_revision_and_offers_tools(self):
        result = self.by_id[1]["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "petra")

    def test_the_tools_cover_check_kinds_new_registry_list_and_docs(self):
        tools = {t["name"]: t for t in self.by_id[2]["result"]["tools"]}
        self.assertEqual(set(tools), {"check", "kinds", "new", "registry_list", "docs"})
        self.assertEqual(tools["new"]["inputSchema"]["required"], ["kind"])

    def test_check_returns_the_report_text_and_the_json_with_its_repair(self):
        result = self.by_id[3]["result"]
        self.assertFalse(result["isError"])
        text = result["content"][0]["text"]
        self.assertTrue(text.startswith("job5-shear-tab-60k: FAIL"))
        self.assertIn("increase  tab.rows (line 19) from 3 to 4", text)
        self.assertEqual(result["structuredContent"]["status"], "FAIL")
        self.assertEqual(result["structuredContent"]["repair"]["moves"][0]["input"], "tab.rows")

    def test_check_reads_a_path(self):
        self.assertEqual(self.by_id[8]["result"]["structuredContent"]["status"], "PASS")

    def test_a_design_that_does_not_lower_is_a_tool_error_the_model_reads(self):
        result = self.by_id[9]["result"]
        self.assertTrue(result["isError"])
        self.assertIn("INPUT_ERROR", result["content"][0]["text"])

    def test_new_prints_a_design_that_checks(self):
        text = self.by_id[4]["result"]["content"][0]["text"]
        self.assertIn("shear_tab tab {", text)

    def test_an_unknown_kind_is_a_tool_error_that_suggests(self):
        result = self.by_id[5]["result"]
        self.assertTrue(result["isError"])
        self.assertIn("nonesuch", result["content"][0]["text"])

    def test_registry_list_and_docs(self):
        self.assertIn("bolt_group.120", self.by_id[6]["result"]["content"][0]["text"])
        self.assertEqual(self.by_id[7]["result"]["content"][0]["text"],
                         (ROOT / "petra" / "docs" / "skill.md").read_text(encoding="utf-8"))

    def test_protocol_errors(self):
        self.assertEqual(self.by_id[10]["error"]["code"], mcp.METHOD_NOT_FOUND)
        self.assertEqual(self.by_id[11]["result"], {})
        (parse,) = [r for r in self.replies if r["id"] is None]
        self.assertEqual(parse["error"]["code"], mcp.PARSE_ERROR)


class Findable(unittest.TestCase):
    def test_the_skill_is_a_skill_md_with_a_name_and_a_description(self):
        text = (ROOT / "petra" / "docs" / "skill.md").read_text(encoding="utf-8")
        head, _, body = text.removeprefix("---\n").partition("\n---\n")
        fields = dict(line.split(": ", 1) for line in head.splitlines())
        self.assertEqual(set(fields), {"name", "description"})
        self.assertEqual(fields["name"], "petra")
        self.assertIn("petra check", body)

    def test_petra_help_names_the_skill_and_the_server(self):
        done = subprocess.run([sys.executable, "-m", "petra", "--help"], cwd=ROOT, capture_output=True, text=True, timeout=300)
        self.assertIn("`petra docs skill`", done.stdout)
        self.assertIn("`petra mcp`", done.stdout)
        self.assertIn("mcp", done.stdout.split("options:")[0], "mcp is listed with the subcommands")


class Handle(unittest.TestCase):
    def test_an_unknown_tool_or_argument_is_invalid_params(self):
        for message in (call(1, "frobnicate"), call(2, "kinds", flavour="steel"), call(3, "check")):
            with self.subTest(message["params"]):
                self.assertEqual(mcp.handle(message)["error"]["code"], mcp.INVALID_PARAMS)

    def test_an_unknown_revision_gets_the_newest(self):
        reply = mcp.handle(request(1, "initialize", {"protocolVersion": "1999-01-01"}))
        self.assertEqual(reply["result"]["protocolVersion"], mcp.PROTOCOL_VERSIONS[0])

    def test_a_notification_gets_no_reply(self):
        self.assertIsNone(mcp.handle({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}}))


if __name__ == "__main__":
    unittest.main()
