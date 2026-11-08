"""An MCP server over Petra's Python API, on stdio, with the standard library only.

    petra mcp                  (or python -m petra.mcp)

The client starts the server and writes JSON-RPC 2.0 messages to its stdin, one per line;
the server writes one response per request to stdout, one per line, and nothing else
(the stdio transport of the Model Context Protocol). The server answers initialize,
ping, tools/list and tools/call, and takes notifications without answering. It offers
five tools, each a call petra's own commands make:

    check           repair.check_text: the text `petra check` prints, and the JSON as
                    structured content
    kinds           teach.kinds_summary, or teach.kinds_text for a domain or a kind
    new             teach.new_text: a complete design of a kind to edit
    registry_list   teach.registry_text: the registry ids a design can name
    docs            teach.docs_text: the skill, the API, the language reference

A tool that cannot do what it was asked (an unknown kind, a design that does not lower)
answers with isError true and the reason, so the model reads it. A bug in a tool answers
with a JSON-RPC internal error, and the server keeps serving. Untrusted: it only calls
the API, so a bug here costs a reply, never a verdict.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any, BinaryIO, Callable, Mapping

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
"""The protocol revisions the server speaks, newest first. It answers initialize with the
client's revision when it is one of these, else with the newest."""

INSTRUCTIONS = """Petra checks a physical design against the claims and loads written in it, and answers \
PASS, FAIL, UNKNOWN or MARGINAL with a certificate. Its main deck is steel connections to AISC 360-22, \
in kips and inches. To design one: call `kinds` to see what Petra can check, `new` with a kind for a \
complete design to edit, then `check` with the edited text. On a FAIL, the check's repair names the \
input that lowers the governing check most, the way to move it, and a value at which that check holds. \
Change design lines only: the loads and claims belong to their signer. Report PASS only when `check` \
returns PASS. The `docs` tool with name `skill` prints the full guide."""


class ToolError(Exception):
    """A tool could not do what it was asked: the reply says why, with isError true."""


class RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603

Result = tuple[str, Any]
"""What a tool returns: the text the model reads, and structured content or None."""


def _string(args: Mapping[str, Any], key: str, required: bool = False) -> str | None:
    value = args.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise RpcError(INVALID_PARAMS, f"argument {key!r} must be a string")
    return value


def _check(args: Mapping[str, Any]) -> Result:
    from . import build_registry
    from .repair import check_text
    from .solvers import SolverSource

    text, path = _string(args, "text"), _string(args, "path")
    if (text is None) == (path is None):
        raise RpcError(INVALID_PARAMS, "give the design as `text` or as a file `path`, not both")
    if path is not None:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise ToolError(f"cannot read {path}: {exc}") from None
    checked = check_text(text, path or "<text>", build_registry(), (SolverSource(),))
    if checked.report is None:
        raise ToolError(checked.text())
    return checked.text(), checked.to_json()


def _taught(call: Callable[[], str]) -> str:
    from .repair import INPUT_ERRORS
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
    from . import build_registry
    from .teach import new_text

    kind, name = _string(args, "kind", required=True), _string(args, "name")
    return _taught(lambda: new_text(kind, name, build_registry())), None


def _registry_list(args: Mapping[str, Any]) -> Result:
    from . import build_registry
    from .teach import registry_text

    prefix = _string(args, "prefix")
    registry = build_registry()
    return _taught(lambda: registry_text(registry, prefix, registry.constants)), None


def _docs(args: Mapping[str, Any]) -> Result:
    from .teach import docs_text

    name = _string(args, "name")
    return _taught(lambda: docs_text(name)), None


def _schema(properties: Mapping[str, str], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"type": "object", "properties": {k: {"type": "string", "description": v} for k, v in properties.items()},
            "required": list(required), "additionalProperties": False}


TOOLS: Mapping[str, tuple[str, dict[str, Any], Callable[[Mapping[str, Any]], Result]]] = {
    "check": ("Check a .petra design and return its verdict: PASS, FAIL, UNKNOWN or MARGINAL, the governing checks "
              "with demand, capacity and utilisation, and every obligation. On a FAIL, the repair lists the moves that "
              "lower the governing check, best first: one number on a component's line, which way, and a value at "
              "which the check holds. The structured content is the JSON `petra check --json` prints.",
              _schema({"text": "the design, the full text of a .petra file", "path": "a .petra file to read instead of text"}),
              _check),
    "kinds": ("List the component kinds Petra can check. With a domain (steel) or a kind (shear_tab), print each "
              "kind's lines, required and optional, with units, registry ids and meanings.",
              _schema({"name": "a domain or a component kind; leave out to list them all"}), _kinds),
    "new": ("Return a complete design of one kind, which passes, to edit into the design you need.",
            _schema({"kind": "the component kind, such as shear_tab or double_angle", "name": "the component's name"},
                    ("kind",)), _new),
    "registry_list": ("List the registry ids a design can name: shapes, grades, bolt groups, electrodes, stocked plates, "
                      "with the common names that stand for them (A325 is bolt_group.120).",
                      _schema({"prefix": "only ids and common names that start with this, such as W18 or steel."}),
                      _registry_list),
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
    unknown = sorted(set(args) - set(TOOLS[name][1]["properties"]))
    if unknown:
        raise RpcError(INVALID_PARAMS, f"{name} takes no argument {', '.join(unknown)}")
    try:
        text, structured = TOOLS[name][2](args)
    except ToolError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    out: dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": False}
    if structured is not None:
        out["structuredContent"] = structured
    return out


def _initialize(params: Mapping[str, Any]) -> dict[str, Any]:
    from . import __version__

    asked = params.get("protocolVersion")
    return {"protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "petra", "version": __version__},
            "instructions": INSTRUCTIONS}


METHODS: Mapping[str, Callable[[Mapping[str, Any]], Any]] = {
    "initialize": _initialize,
    "ping": lambda params: {},
    "tools/list": lambda params: {"tools": [{"name": n, "description": d, "inputSchema": s} for n, (d, s, _) in TOOLS.items()]},
    "tools/call": _call,
}


def handle(message: Any) -> dict[str, Any] | None:
    """The response to one JSON-RPC message, or None for a notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        if isinstance(message, dict) and "method" not in message and ("result" in message or "error" in message):
            return None
        return _error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST, "not a JSON-RPC 2.0 request")
    if "id" not in message:
        return None
    rid, method, params = message["id"], message["method"], message.get("params") or {}
    if method not in METHODS:
        return _error(rid, METHOD_NOT_FOUND, f"unknown method {method!r}")
    if not isinstance(params, dict):
        return _error(rid, INVALID_PARAMS, "params must be an object")
    try:
        return {"jsonrpc": "2.0", "id": rid, "result": METHODS[method](params)}
    except RpcError as exc:
        return _error(rid, exc.code, str(exc))
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        return _error(rid, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")


def _error(rid: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def serve(stdin: BinaryIO, stdout: BinaryIO) -> int:
    """Answer each line of `stdin` until it closes. A line holds one message, or a batch
    as a JSON array, which gets an array of the responses."""
    for raw in stdin:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            reply: Any = _error(None, PARSE_ERROR, f"not JSON: {exc}")
        else:
            if isinstance(message, list):
                reply = [r for r in map(handle, message) if r is not None] or None
            else:
                reply = handle(message)
        if reply is not None:
            stdout.write(json.dumps(reply, ensure_ascii=False).encode("utf-8") + b"\n")
            stdout.flush()
    return 0


def main() -> int:
    """Serve on the process's stdin and stdout. Anything else that prints goes to stderr,
    so that stdout carries only the protocol."""
    out = sys.stdout.buffer
    sys.stdout = sys.stderr
    return serve(sys.stdin.buffer, out)


if __name__ == "__main__":
    sys.exit(main())
