"""An MCP server over Petra's Python API, on stdio, with the standard library only.

    petra mcp [--budget SECONDS]

The client starts the server and writes JSON-RPC 2.0 messages to its stdin, one per line;
the server writes one response per request to stdout, one per line, and nothing else
(the stdio transport of the Model Context Protocol). It offers four tools, each a call
petra's own commands make:

    check           pipeline.check_text: the text `petra check` prints, and the JSON as
                    structured content. The verdict of a design of a deck is the
                    kernel's: with none to run, or one whose answer cannot be taken,
                    the tool answers with isError true and `no verdict`
    kinds           teach.kinds_summary, or teach.kinds_text for a deck or a type of one
    new             teach.new_text: a card and a complete design of a type to edit
    docs            teach.docs_text: the skill, the API, the language reference

The server speaks both eras of the protocol. A request whose params._meta names a
protocol version is served on its own, as revision 2026-07-28 has it: the result carries
resultType, the server's identity in _meta, and for a list the caching hints. A client of
an earlier revision opens with initialize, and gets results without those fields.
server/discover answers only a modern request, and initialize is always legacy.

A tool that cannot do what it was asked (an argument of the wrong type, an unknown type,
a pair that is refused) answers with isError true and the reason, so the model
reads it and can try again. An unknown tool, a malformed request or a bug in a tool
answers with a JSON-RPC error, and the server keeps serving. A thread reads stdin ahead
of the requests being answered, so that notifications/cancelled reaches a request still
in the queue, which is then never answered, or one in progress, which is stopped.

Tool calls run in a second process, the worker. A call that is cancelled, or that runs past
the budget, ends with that process, and the server starts another. The server itself never
imports the language or the grid.

The `path` and `card_path` of a check come from a model, so they read a .petra and a
.card file on this machine and nothing else, and they give the same answer for a file that
is missing, unreadable or of another kind.
Untrusted: it only calls the API, so a bug here costs a reply, never a verdict.
"""
from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, BinaryIO, Callable, Iterable, Mapping

PROTOCOL_VERSIONS = ("2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
"""The protocol revisions the server speaks, newest first. The first is modern; initialize
answers with the client's revision when it is one of the rest, else with the newest of
them."""

LEGACY = PROTOCOL_VERSIONS[1:]

VERSION, CLIENT_CAPABILITIES, SERVER_INFO = (f"io.modelcontextprotocol/{key}" for key in
                                             ("protocolVersion", "clientCapabilities", "serverInfo"))

CACHEABLE = {"tools/list": 3_600_000, "server/discover": 3_600_000}
"""The modern results that carry caching hints, with ttlMs: the tools never change while
the server runs, and a new version of Petra starts a new server."""

INSTRUCTIONS = """Petra checks a physical design against a deck of rules, under the loads and bounds its card states. The \
answer is the verdict of its kernel: PASS, FAIL or UNKNOWN, or PASS_WAIVED for a design that passes with a \
cell resting on a waiver. The kernel passes only a design whose parts are of the types of a deck of rules. A \
design whose parts are all of other kinds reads UNKNOWN, with the reason that no deck has its kind, and one \
that mixes the two is refused. Never report such a design as passing. With no kernel to run, `check` of a \
design of a deck answers with an error and no verdict. \
The shipped deck is bolted lap joints of steel plates to AISC 360-22, in kips and inches. To design one: call \
`kinds` to see the types and their lines, `new` with a type for a card and a complete design to edit, then \
`check` with the edited text. The report lists every cell of the grid: proved, refuted with the two sides of \
the rule, open where the deck has no rule yet, or waived. \
Change design lines only: the loads, the bounds and the waivers belong to their signer. Report PASS only when \
`check` returns PASS, and PASS_WAIVED as a pass that rests on the waivers it lists. The `docs` tool with name \
`skill` prints the full guide."""


class ToolError(Exception):
    """A tool could not do what it was asked: the reply says why, with isError true."""


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
UNSUPPORTED_PROTOCOL_VERSION = -32022

Result = tuple[str, Any]
"""What a tool returns: the text the model reads, and structured content or None."""


def _string(args: Mapping[str, Any], key: str, required: bool = False) -> str | None:
    value = args.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ToolError(f"argument {key!r} must be a string")
    return value


def _check(args: Mapping[str, Any]) -> Result:
    from . import verify
    from .files import acts, card_of, shown
    from .pipeline import check_text

    text, path = _string(args, "design"), _string(args, "path")
    card, card_path = _string(args, "card"), _string(args, "card_path")
    for name, value in (("path", path), ("card_path", card_path)):
        if value is not None and acts(value):      # the report prints the paths, and keeps its own line feeds
            raise ToolError(f"`{name}` holds a character that a terminal acts on, or a line end")
    if text is None and path is None:
        raise ToolError("give the design as `design`, its text, or as the absolute `path` of a .petra file")
    if text is not None and path is not None:
        raise ToolError("give the design as `design`, its text, or as a file `path`, not both")
    if card is not None and card_path is not None:
        raise ToolError("give the card as `card`, its text, or as a file `card_path`, not both")
    if card is None and card_path is None and path is None:
        raise ToolError("give the card the design answers as `card`, its text, or as the absolute `card_path` of a .card file")
    if path is not None:
        text = _file_at(path, "path", ".petra")
    if card is None:
        card_path = card_path or card_of(path)
        card = _file_at(card_path, "card_path", ".card")
    try:
        checked = check_text(card, text, path or "<design>", card_path=card_path or "<card>")
    except verify.NoVerdict as exc:      # no kernel ran, or its answer cannot be taken: nothing else gives a verdict
        raise ToolError(shown(f"no verdict: {exc}")) from None
    # The text is what a client shows a person, so it goes out as `petra check` prints it: no character a terminal acts on.
    if checked.error is not None:
        raise ToolError(shown(checked.text()))
    return shown(checked.text()), checked.to_json()


def _file_at(path: str, argument: str, suffix: str) -> str:
    """The text of the file at `path`, which has `suffix`. A network path is refused
    before anything touches it, because opening one sends the user's credentials to the
    host it names."""
    from .files import read_text
    from .lang import LolaSyntaxError

    try:
        if path.startswith(("\\\\", "//")):
            raise OSError
        real = Path(path).resolve(strict=True)
        if real.suffix != suffix or not real.is_file():
            raise OSError
        return read_text(real)
    except LolaSyntaxError as exc:      # a file over the size a card or a design may have, or one that is no text
        raise ToolError(str(exc)) from None
    except (OSError, ValueError):
        raise ToolError(f"cannot read {path}: `{argument}` takes a {suffix} file on this machine. "
                        "Give its text instead.") from None


def _taught(call: Callable[[], str]) -> str:
    from .pipeline import INPUT_ERRORS
    from .teach import TeachError

    try:
        return call()
    except (TeachError, *INPUT_ERRORS) as exc:
        raise ToolError(str(exc)) from None


def _kinds(args: Mapping[str, Any]) -> Result:
    from .teach import kinds_summary, kinds_text

    name = _string(args, "name")
    return _taught(lambda: kinds_summary() if name is None else kinds_text(name)), None


def _new(args: Mapping[str, Any]) -> Result:
    from .teach import new_text

    kind, name = _string(args, "kind", required=True), _string(args, "name")
    card, design = _taught(lambda: new_text(kind, name))
    return f"The card, {kind}.card:\n\n{card}\nThe design, {kind}.petra:\n\n{design}", {"card": card, "design": design}


def _docs(args: Mapping[str, Any]) -> Result:
    from .teach import docs_text

    name = _string(args, "name")
    return _taught(lambda: docs_text(name)), None


def _schema(properties: Mapping[str, str], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": {k: {"type": "string", "description": v} for k, v in properties.items()},
            "required": list(required), "additionalProperties": False}


TOOLS: Mapping[str, tuple[str, dict[str, Any], Callable[[Mapping[str, Any]], Result]]] = {
    "check": ("Check a design against the card it answers and return the kernel's verdict: PASS, FAIL or UNKNOWN, "
              "or PASS_WAIVED when it passes and a cell rests on a waiver, with every cell of the deck's grid: its "
              "part, its mechanism, its state and, for a rule that was worked out, how much of the limit is used. The "
              "card holds what was asked: the loads, the signed bounds and the waivers. The design holds the parts "
              "and cannot change the card. A design none of whose parts is of a deck's type reads UNKNOWN. The "
              "structured content is the JSON `petra check --json` prints.",
              _schema({"design": "the design, the full text of a .petra file",
                       "path": "the absolute path of a .petra file to read instead of `design`",
                       "card": "the card, the full text of a .card file",
                       "card_path": "the absolute path of a .card file to read instead of `card`; "
                                    "with `path` and no card, the .card file beside the design"}),
              _check),
    "kinds": ("List the decks of rules Petra checks against and the types of part each has. With a deck (aisc360-22) or "
              "a type (lap), print each type's lines with their units and meanings, the loads a card may put on a "
              "part of it, and the mechanisms the grid asks of it, each with its rule or as open.",
              _schema({"name": "a deck or a type of one; leave out to list them all"}), _kinds),
    "new": ("Return a card and a complete design of one type to edit into the pair you need. The card signs no "
            "waiver, so the pair reads UNKNOWN until the lines its deck has no rule for are waived by their signer.",
            _schema({"kind": "the type of part, such as lap", "name": "the part's name"},
                    ("kind",)), _new),
    "docs": ("Print a document that ships with Petra: skill (how to design and check with Petra), api (the Python API "
             "and the JSON), reference (the language), readme. Leave out name to list them.",
             _schema({"name": "skill, api, reference or readme"}), _docs),
}


def _call(params: Mapping[str, Any]) -> dict[str, Any]:
    name, args = params.get("name"), params.get("arguments") or {}
    if name not in TOOLS:
        raise RpcError(INVALID_PARAMS, f"unknown tool {name!r}; the tools are {', '.join(TOOLS)}")
    if not isinstance(args, dict):
        raise RpcError(INVALID_PARAMS, "arguments must be an object")
    try:
        unknown = sorted(set(args) - set(TOOLS[name][1]["properties"]))
        if unknown:
            raise ToolError(f"{name} takes no argument {', '.join(unknown)}; it takes {', '.join(TOOLS[name][1]['properties'])}")
        text, structured = TOOLS[name][2](args)
    except ToolError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    out: dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": False}
    if structured is not None:
        out["structuredContent"] = structured
    return out


def _server_info() -> dict[str, str]:
    from . import __version__

    return {"name": "petra", "version": __version__}


CAPABILITIES = {"tools": {}}


def _initialize(params: Mapping[str, Any]) -> dict[str, Any]:
    asked = params.get("protocolVersion")
    return {"protocolVersion": asked if asked in LEGACY else LEGACY[0], "capabilities": CAPABILITIES,
            "serverInfo": _server_info(), "instructions": INSTRUCTIONS}


def _discover(params: Mapping[str, Any]) -> dict[str, Any]:
    return {"supportedVersions": list(PROTOCOL_VERSIONS), "capabilities": CAPABILITIES, "instructions": INSTRUCTIONS}


METHODS: Mapping[str, Callable[[Mapping[str, Any]], Any]] = {
    "initialize": _initialize,
    "server/discover": _discover,
    "ping": lambda params: {},
    "tools/list": lambda params: {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (d, s, _) in TOOLS.items()]},
    "tools/call": _call,
}


def _modern(meta: Any) -> bool:
    """Whether a request is modern: its _meta names a protocol version, which must be one
    the server speaks, beside the client's capabilities."""
    if not isinstance(meta, dict) or VERSION not in meta:
        return False
    if meta[VERSION] not in PROTOCOL_VERSIONS:
        raise RpcError(UNSUPPORTED_PROTOCOL_VERSION, "Unsupported protocol version",
                       {"supported": list(PROTOCOL_VERSIONS), "requested": meta[VERSION]})
    if not isinstance(meta.get(CLIENT_CAPABILITIES), dict):
        raise RpcError(INVALID_PARAMS, f"_meta must carry {CLIENT_CAPABILITIES} beside {VERSION}")
    return True


def _request_id(message: Any) -> str | int | None:
    """The id of a request that a client can cancel, or None."""
    if isinstance(message, dict) and isinstance(message.get("method"), str):
        rid = message.get("id")
        if isinstance(rid, (str, int)) and not isinstance(rid, bool):
            return rid
    return None


def handle(message: Any, call: Callable[[Mapping[str, Any]], dict[str, Any]] = _call) -> dict[str, Any] | None:
    """The response to one JSON-RPC message, or None for a notification. `call` runs a
    tools/call: here, or in the worker."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        if isinstance(message, dict) and "method" not in message and ("result" in message or "error" in message):
            return None
        return _error(_request_id(message), INVALID_REQUEST, "not a JSON-RPC 2.0 request")
    if "id" not in message:
        return None
    rid = _request_id(message)
    if rid is None:
        return _error(None, INVALID_REQUEST, "a request id is a string or an integer")
    method, params = message["method"], message.get("params") or {}
    if not isinstance(params, dict):
        return _error(rid, INVALID_PARAMS, "params must be an object")
    try:
        modern = method != "initialize" and _modern(params.get("_meta"))
        if method == "server/discover" and not modern:
            raise RpcError(INVALID_PARAMS, f"server/discover takes _meta with {VERSION} and {CLIENT_CAPABILITIES}")
        if method not in METHODS:
            raise RpcError(METHOD_NOT_FOUND, f"unknown method {method!r}")
        result = call(params) if method == "tools/call" else METHODS[method](params)
    except RpcError as exc:
        return _error(rid, exc.code, str(exc), exc.data)
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        return _error(rid, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
    if modern:
        result = {"resultType": "complete", **result, "_meta": {SERVER_INFO: _server_info()}}
        if method in CACHEABLE:
            result |= {"ttlMs": CACHEABLE[method], "cacheScope": "public"}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _error(rid: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": error}


BUDGET_S = 120.0
"""How long a tool call may run before the server stops it. The slowest shipped example
checks in about 10 s on a busy desktop, and the slowest design in corpus/ that finishes
takes 28 s."""


def _tool_error(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": True}


class Worker:
    """The process that runs tool calls, so that a call can be stopped by ending it.

    It also keeps numpy out of the server. On Windows a library that loads while another
    thread waits on stdin can block until the client writes again. numpy's did, and the
    first tool call got no answer."""

    COMMAND = (sys.executable, "-P", "-c",
               "import os, sys; here, own = os.getcwd(), os.path.abspath(sys.argv[1]); "
               "kept = [p for p in sys.path if p and (os.path.abspath(p) != here or os.path.abspath(p) == own)]; "
               "sys.path[:] = kept if own in map(os.path.abspath, kept) else [own] + kept; "
               "from petra.cli import main; sys.exit(main(['mcp', '--worker']))",
               str(Path(__file__).resolve().parent.parent))
    """The worker is this package: the folder that holds it goes first on the worker's path, and
    the working directory comes off it. `python -m petra` would put the working directory
    first, and a file named petra.py in the folder a client starts the server in would then be
    the worker, and answer every check as it liked (tests/test_kernel_attacks12.py). `-P` stops
    Python adding the working directory itself, and the command takes out every entry that is
    the working directory by another road: an empty entry of PYTHONPATH is one. The folder that
    holds the package stays where it is on the path, working directory or not, and goes first
    only when it is not there at all, as in a source tree with no install. For an install it is
    site-packages, which must not come before the standard library."""

    def __init__(self, budget: float = BUDGET_S) -> None:
        self.budget = budget
        self._start()

    def _start(self) -> None:
        # On POSIX the worker leads a group of its own, so that stopping it stops the kernel it started with it.
        self.process = subprocess.Popen(self.COMMAND, stdin=subprocess.PIPE, stdout=subprocess.PIPE, start_new_session=hasattr(os, "killpg"))
        self.replies: queue.Queue[bytes] = queue.Queue()
        self.reader = threading.Thread(target=self._read, args=(self.process, self.replies), name="petra-mcp-worker", daemon=True)
        self.reader.start()

    @staticmethod
    def _read(process: subprocess.Popen, replies: queue.Queue[bytes]) -> None:
        for line in process.stdout:
            replies.put(line)
        replies.put(b"")

    def stop(self) -> None:
        if hasattr(os, "killpg"):
            try:
                os.killpg(self.process.pid, signal.SIGKILL)      # the worker and every process it started, a kernel among them
            except (ProcessLookupError, PermissionError):
                pass      # it has ended already
        self.process.kill()
        self.process.wait()
        self.reader.join()
        for pipe in (self.process.stdin, self.process.stdout):
            try:
                pipe.close()
            except OSError:
                pass  # a line the worker never read is still in the pipe's buffer

    def call(self, params: Mapping[str, Any], cancelled: Callable[[], bool]) -> dict[str, Any]:
        """The result of one tools/call. Once `cancelled()` is true the call is stopped,
        and what this returns is not sent."""
        try:
            self.process.stdin.write(json.dumps(params).encode("ascii") + b"\n")
            self.process.stdin.flush()
        except OSError:
            pass  # the worker has ended, and its last line says so below
        deadline = time.monotonic() + self.budget
        while True:
            try:
                line = self.replies.get(timeout=0.05)
            except queue.Empty:
                if not cancelled() and time.monotonic() < deadline:
                    continue
                why = f"stopped after {self.budget:g} s with no verdict. `petra mcp --budget SECONDS` sets the limit."
            else:
                if line:
                    reply = json.loads(line)
                    if "error" in reply:
                        raise RpcError(*reply["error"])
                    return reply["result"]
                why = "the checker ended before it answered. Its error is on the server's stderr."
            self.stop()
            self._start()
            return _tool_error(why)


def work(stdin: Iterable[bytes], stdout: BinaryIO) -> int:
    """The worker: answer each line of `stdin`, the params of one tools/call, with a line
    that holds its result or its JSON-RPC error. What a tool call imports is imported
    first, while the client is still shaking hands with the server."""
    from . import pipeline, teach  # noqa: F401

    for raw in stdin:
        try:
            reply: dict[str, Any] = {"result": _call(json.loads(raw))}
        except RpcError as exc:
            reply = {"error": [exc.code, str(exc), exc.data]}
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            reply = {"error": [INTERNAL_ERROR, f"{type(exc).__name__}: {exc}", None]}
        stdout.write(json.dumps(reply).encode("ascii") + b"\n")
        stdout.flush()
    return 0


def serve(stdin: Iterable[bytes], stdout: BinaryIO, worker: Worker | None = None) -> int:
    """Answer each line of `stdin` until it closes. A line holds one message, or a batch
    as a JSON array, which gets an array of the responses. A reader thread takes each
    notifications/cancelled as it arrives; this thread answers the rest in order. Tool
    calls run in `worker`, or in this process when there is none."""
    inbox: queue.Queue[Any] = queue.Queue()
    closed = object()
    lock = threading.Lock()
    pending: set[str | int] = set()
    cancelled: set[str | int] = set()

    def read() -> None:
        try:
            for raw in stdin:
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except (ValueError, RecursionError) as exc:
                    inbox.put(_error(None, PARSE_ERROR, f"not JSON: {exc}"))
                    continue
                if isinstance(message, dict) and message.get("method") == "notifications/cancelled":
                    target = (message.get("params") or {}).get("requestId")
                    with lock:
                        if target in pending:
                            cancelled.add(target)
                    continue
                rid = _request_id(message)
                if rid is not None:
                    with lock:
                        pending.add(rid)
                inbox.put((rid, message))
        finally:
            inbox.put(closed)

    threading.Thread(target=read, name="petra-mcp-stdin", daemon=True).start()
    while (item := inbox.get()) is not closed:
        if not isinstance(item, tuple):
            reply = item
        else:
            rid, message = item
            def is_cancelled(rid: Any = rid) -> bool:
                with lock:
                    return rid in cancelled

            run = _call if worker is None else lambda params: worker.call(params, is_cancelled)
            if isinstance(message, list):
                reply = [r for r in (handle(m, run) for m in message) if r is not None] or None
            else:
                reply = None if is_cancelled() else handle(message, run)
            with lock:
                if rid in cancelled:
                    reply = None
                cancelled.discard(rid)
                pending.discard(rid)
        if reply is not None:
            stdout.write(json.dumps(reply).encode("ascii") + b"\n")
            stdout.flush()
    if worker is not None:
        worker.stop()
    return 0


def main(budget: float = BUDGET_S, worker: bool = False) -> int:
    """Serve on the process's stdin and stdout, or be the worker of a server. Anything else
    that prints goes to stderr, so that stdout carries only the protocol. The server starts
    its worker before the thread that reads stdin."""
    out = sys.stdout.buffer
    sys.stdout = sys.stderr
    if worker:
        _watch(os.getppid())
        return work(sys.stdin.buffer, out)
    return serve(sys.stdin.buffer, out, Worker(budget))


def _watch(server: int) -> None:
    """Have this worker stop itself, and everything it started, once the server that started it
    is gone. The worker leads a group of its own (`Worker._start`), so a signal that ends the
    server does not reach it, and a check it is in the middle of does not see its input
    close: without this, a server stopped with Ctrl-C left its worker and a kernel running."""
    def watch() -> None:
        while os.getppid() == server:
            time.sleep(0.5)
        if hasattr(os, "killpg") and os.getpgid(0) == os.getpid():
            os.killpg(os.getpid(), signal.SIGKILL)
        os._exit(1)

    threading.Thread(target=watch, name="petra-mcp-server-watch", daemon=True).start()


if __name__ == "__main__":
    sys.exit(main())
