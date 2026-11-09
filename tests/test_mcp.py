"""`petra mcp`: an MCP client starts the server, writes JSON-RPC requests to its stdin one
per line, and reads one response per request from its stdout (petra/mcp.py).

The server is driven here as a client drives it, through a real process and its pipes,
or through serve() with the pipes replaced by queues where a test must wait for a reply
before it writes the next line.
"""
import json
import queue
import subprocess
import sys
import threading
import unittest
from pathlib import Path

from petra import mcp

ROOT = Path(__file__).resolve().parents[1]
FAILING = ROOT / "tests" / "fixtures" / "readout" / "job5_fail_60k.petra"
SHEAR_TAB = ROOT / "examples" / "steel" / "shear_tab.petra"
MODERN = {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}


def request(rid, method, params=None):
    return {"jsonrpc": "2.0", "id": rid, "method": method, **({"params": params} if params is not None else {})}


def call(rid, tool, **arguments):
    return request(rid, "tools/call", {"name": tool, "arguments": arguments})


def cancel(rid):
    return {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": rid, "reason": "test"}}


class Session(unittest.TestCase):
    """One session: the handshake, the tool list, a call to each tool, and a request the
    client cancels while an earlier check runs."""

    @classmethod
    def setUpClass(cls):
        lines = [
            request(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                      "clientInfo": {"name": "test", "version": "0"}}),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            request(2, "tools/list"),
            call(3, "check", text=FAILING.read_text(encoding="utf-8")),
            call(4, "new", kind="shear_tab", name="tab"),
            call(5, "kinds", name="nonesuché"),
            call(6, "registry_list", prefix="A325"),
            call(7, "docs", name="skill"),
            call(8, "check", path=str(SHEAR_TAB)),
            call(9, "check", text="petra 0\ndesign {\n"),
            request(10, "frobnicate"),
            request(11, "ping"),
            call(12, "check", path=str(SHEAR_TAB)),
            call(13, "kinds"),
            cancel(13),
            request(14, "tools/list", {"_meta": MODERN}),
        ]
        stdin = "\n".join(json.dumps(m) for m in lines) + "\nnot json\n"
        done = subprocess.run([sys.executable, "-m", "petra", "mcp"], input=stdin.encode("utf-8"), cwd=ROOT,
                              capture_output=True, timeout=600)
        cls.code = done.returncode
        cls.stdout = done.stdout
        cls.replies = [json.loads(line) for line in done.stdout.split(b"\n") if line]
        cls.by_id = {r["id"]: r for r in cls.replies}

    def test_it_exits_0_when_stdin_closes_and_answers_every_request_once(self):
        self.assertEqual(self.code, 0)
        self.assertEqual(sorted(r["id"] for r in self.replies if r["id"] is not None), [*range(1, 13), 14],
                         "one reply per request, none for the notifications or the cancelled request")
        self.assertTrue(all(r["jsonrpc"] == "2.0" for r in self.replies))

    def test_stdout_is_ascii_json_one_message_per_line(self):
        self.assertTrue(self.stdout.isascii(), "a non-ASCII character is escaped, so no line separator splits a message")
        self.assertIn("nonesuché", self.by_id[5]["result"]["content"][0]["text"])

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

    def test_a_modern_request_in_the_same_process_gets_a_modern_result(self):
        result = self.by_id[14]["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual([t["name"] for t in result["tools"]], [t["name"] for t in self.by_id[2]["result"]["tools"]])


class Served:
    """serve() on queues: write() hands it a line, reply() waits for its next one."""

    def __init__(self):
        self.lines, self.out = queue.Queue(), queue.Queue()
        self.thread = threading.Thread(target=lambda: mcp.serve(iter(self.lines.get, None), self), daemon=True)
        self.thread.start()

    def send(self, *messages):
        for message in messages:
            self.lines.put(json.dumps(message).encode("utf-8") + b"\n")

    def write(self, data):
        self.out.put(json.loads(data))

    def flush(self):
        pass

    def reply(self, timeout=120):
        return self.out.get(timeout=timeout)

    def close(self):
        self.lines.put(None)
        self.thread.join(timeout=60)
        return self.out.queue


class Cancel(unittest.TestCase):
    def test_a_request_cancelled_while_it_waits_is_never_answered_and_frees_its_id(self):
        served = Served()
        served.send(call(1, "check", path=str(SHEAR_TAB)), call(2, "kinds"), cancel(2), request(3, "ping"))
        self.assertEqual([served.reply()["id"], served.reply()["id"]], [1, 3])
        served.send(request(2, "ping"))
        self.assertEqual(served.reply()["id"], 2)
        self.assertEqual(list(served.close()), [])

    def test_a_cancellation_after_the_reply_does_not_swallow_a_later_request_with_that_id(self):
        served = Served()
        served.send(request(7, "ping"))
        self.assertEqual(served.reply()["id"], 7)
        served.send(cancel(7), cancel("unknown"), request(7, "ping"))
        self.assertEqual(served.reply(), {"jsonrpc": "2.0", "id": 7, "result": {}})
        served.close()


class Handle(unittest.TestCase):
    def test_an_unknown_tool_or_malformed_arguments_are_invalid_params(self):
        for message in (call(1, "frobnicate"), request(2, "tools/call", {"name": "kinds", "arguments": [1]})):
            with self.subTest(message["params"]):
                self.assertEqual(mcp.handle(message)["error"]["code"], mcp.INVALID_PARAMS)

    def test_a_bad_argument_is_a_tool_error_the_model_can_correct(self):
        for message in (call(1, "kinds", flavour="steel"), call(2, "check"), call(3, "check", text=5),
                        call(4, "check", text="x", path="y"), call(5, "new")):
            with self.subTest(message["params"]):
                result = mcp.handle(message)["result"]
                self.assertTrue(result["isError"])
                self.assertTrue(result["content"][0]["text"])

    def test_a_request_id_is_a_string_or_an_integer(self):
        for rid in (None, 1.5, True, [1]):
            with self.subTest(rid):
                self.assertEqual(mcp.handle(request(rid, "ping"))["error"]["code"], mcp.INVALID_REQUEST)
        self.assertEqual(mcp.handle(request("a", "ping"))["result"], {})

    def test_an_unknown_revision_gets_the_newest_legacy_one(self):
        reply = mcp.handle(request(1, "initialize", {"protocolVersion": "1999-01-01"}))
        self.assertEqual(reply["result"]["protocolVersion"], "2025-11-25")

    def test_a_notification_gets_no_reply(self):
        self.assertIsNone(mcp.handle({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}}))


class Modern(unittest.TestCase):
    """Revision 2026-07-28: no handshake; each request names its version in _meta."""

    def test_discover_names_the_versions_the_tools_and_the_server(self):
        result = mcp.handle(request("d", "server/discover", {"_meta": MODERN}))["result"]
        self.assertEqual(result["resultType"], "complete")
        self.assertEqual(result["supportedVersions"][:2], ["2026-07-28", "2025-11-25"])
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["_meta"]["io.modelcontextprotocol/serverInfo"]["name"], "petra")
        self.assertGreaterEqual(result["ttlMs"], 0)
        self.assertIn(result["cacheScope"], ("public", "private"))

    def test_a_tool_list_carries_caching_hints_and_a_call_carries_its_result_type(self):
        listed = mcp.handle(request(1, "tools/list", {"_meta": MODERN}))["result"]
        self.assertEqual((listed["resultType"], listed["cacheScope"]), ("complete", "public"))
        self.assertGreaterEqual(listed["ttlMs"], 0)
        called = mcp.handle(request(2, "tools/call", {"name": "docs", "arguments": {}, "_meta": MODERN}))["result"]
        self.assertEqual(called["resultType"], "complete")
        self.assertNotIn("ttlMs", called)
        self.assertFalse(called["isError"])

    def test_an_unsupported_version_lists_the_supported_ones(self):
        meta = {**MODERN, "io.modelcontextprotocol/protocolVersion": "1900-01-01"}
        error = mcp.handle(request(1, "tools/list", {"_meta": meta}))["error"]
        self.assertEqual(error["code"], -32022)
        self.assertEqual(error["data"], {"supported": list(mcp.PROTOCOL_VERSIONS), "requested": "1900-01-01"})

    def test_a_modern_request_without_the_client_capabilities_is_invalid_params(self):
        meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}
        self.assertEqual(mcp.handle(request(1, "tools/list", {"_meta": meta}))["error"]["code"], mcp.INVALID_PARAMS)

    def test_a_legacy_probe_of_discover_gets_an_error_so_the_client_falls_back_to_initialize(self):
        self.assertEqual(mcp.handle(request(1, "server/discover"))["error"]["code"], mcp.INVALID_PARAMS)

    def test_a_legacy_request_gets_no_modern_fields(self):
        result = mcp.handle(request(1, "tools/list"))["result"]
        self.assertEqual(set(result), {"tools"})


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


if __name__ == "__main__":
    unittest.main()
