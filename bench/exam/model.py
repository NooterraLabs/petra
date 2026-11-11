"""The model is a command: a prompt goes in on stdin and the answer comes back on stdout.

`--model` takes one of the names below or any command line. A command line is run as it
is written, with no shell, so a provider's own client can be plugged in later.

    echo         No model. The answer is the prompt, word for word. For tests.
    claude-wsl   The Claude Code CLI inside WSL, as a text function: no tools, one turn, no
                 settings, no session kept, started in an empty folder under /tmp.

A call fails when the command exits with another code than 0, prints nothing, or runs past
the time limit. The harness records a failed call and does not take it for an answer.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass

SYSTEM = "You answer one engineering design task. You have no tools and one reply. Give the answer in the form the task asks for."
"""The system prompt of the built-in commands. Both arms get the same one."""

_CLAUDE = ("mkdir -p /tmp/exam-model && cd /tmp/exam-model && claude -p --model {model} --tools '' --max-turns 1 "
           "--safe-mode --setting-sources '' --strict-mcp-config --no-session-persistence --disable-slash-commands "
           "--system-prompt " + shlex.quote(SYSTEM))

PRESETS: dict[str, list[str]] = {
    "claude-wsl": ["wsl", "-e", "bash", "-lc", _CLAUDE.format(model="sonnet")],
}
DEFAULT = "claude-wsl"


@dataclass(frozen=True)
class Reply:
    text: str
    ok: bool
    seconds: float
    error: str | None = None


def command(model: str) -> list[str] | str | None:
    """What runs for a model: None for the built-in echo, the argument list of a named
    command, or the command line as written."""
    if model == "echo":
        return None
    return PRESETS.get(model, model)


def describe(model: str) -> str:
    """The command as one line, for the record."""
    run = command(model)
    return "echo (built in)" if run is None else run if isinstance(run, str) else subprocess.list2cmdline(run)


def call(model: str, prompt: str, timeout: float) -> Reply:
    run = command(model)
    began = time.monotonic()
    if run is None:
        return Reply(prompt, True, 0.0)
    if isinstance(run, str) and os.name != "nt":
        run = shlex.split(run)
    try:
        done = subprocess.run(run, input=prompt, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return Reply("", False, time.monotonic() - began, f"no answer within {timeout:.0f} s")
    except OSError as exc:
        return Reply("", False, time.monotonic() - began, f"the command did not start: {exc}")
    seconds = time.monotonic() - began
    if done.returncode != 0:
        said = (done.stderr.strip() or done.stdout.strip())[-2000:]
        return Reply(done.stdout, False, seconds, f"exit code {done.returncode}: {said}")
    if not done.stdout.strip():
        return Reply("", False, seconds, f"the command printed nothing: {done.stderr.strip()[-2000:]}")
    return Reply(done.stdout, True, seconds)
