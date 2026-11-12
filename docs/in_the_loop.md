# Petra in a coding agent's loop

This page shows how to call Petra from an agent or a script.

- `petra.check(card, design)` returns plain data, and a FAIL names the inputs of the design that would move it most.
- `petra mcp` serves Petra's tools to an MCP client, and `petra docs skill` prints a SKILL.md for coding agents.

## Check from Python

```python
import petra

result = petra.check(open("tab.card").read(), open("tab.petra").read())
result["status"]            # "PASS", "PASS_WAIVED", "FAIL", "UNKNOWN", "MARGINAL" or "INPUT_ERROR"
result["repair"]["moves"]   # on a FAIL: the inputs to change, best first
```

PASS_WAIVED is the pass of a design of a deck's type when a waiver of the card rests one of its cells. It passes what the deck could check, `result["waived"]` lists each waiver with who signed it, and `petra check` exits 6 for it.

The result is the same JSON that `petra check --json` prints. On a FAIL, the `repair` key holds the moves. A move changes one number in the design, such as `tab.rows` or `tab.plate thickness`, by one step up or down. No move changes the card. Petra re-checks each step and sorts the moves by the utilisation of the governing check after the step, lowest first. For the top three moves it also searches further in the same direction for a value at which the governing check holds, and reports that value and the design's status there. When no number lowers the check, the moves swap an angle or tee for another shape of its family instead. `petra check` prints the same moves as text under the governing check. The [Python API](../petra/docs/api.md#repair) gives the exact shape.

A move is a suggestion from a search, not a verdict. Only a check of the edited design says whether it passes.

## Use from an MCP client

`petra mcp` runs a Model Context Protocol server on stdin and stdout. It uses only the Python standard library. Its tools are `check`, `kinds`, `new`, `registry_list` and `docs`. `check` returns the text that `petra check` prints, and the data of `petra.check` as structured content. It takes the design as `design` or `path` and the card as `card` or `card_path`. A path reads a `.petra` or a `.card` file on the server's machine and nothing else, and with `path` alone the card is the `.card` file beside the design. Tool calls run in a second process, so the server can stop a call that the client cancels or that runs past 120 s. `petra mcp --budget SECONDS` sets another limit. The server speaks protocol revision 2026-07-28, in which each request names its revision, and answers `initialize` for clients of 2025-11-25 back to 2024-11-05.

`petra docs skill` prints a SKILL.md for coding agents. It says how to start from `petra new`, how to read a FAIL and its moves, and what an agent must never change to reach a PASS. That is the card: the loads, the claims and the waivers.

### Claude Code

This repository is a Claude Code plugin marketplace. In Claude Code, run

```
/plugin marketplace add NooterraLabs/petra
/plugin install petra@petra
```

The plugin adds the server and the skill. It starts the server with

```bash
uvx --from petra-lang==0.1.2 petra mcp
```

so it needs [uv](https://docs.astral.sh/uv/) and no other install. On the first start uv fetches Petra, numpy and scipy into its cache, and later starts reuse them. The pin holds the server at the release whose skill the plugin carries, and each release moves it.

Claude Code waits 30 s for a server to start (reported in its docs). The server answers the handshake before it imports Petra's language, models and solvers, and the first tool call that needs them imports them. Under full load on an 8-thread PC it answered in a median 2.9 s, where importing them first took 25.8 s (measured). The first start through uv also downloads the packages. If `/mcp` shows `petra` failed on its first start, set `MCP_TIMEOUT=120000` in the environment and start Claude Code again.

The plugin runs uvx rather than a `petra` already on the PATH, because then the plugin is the only step. `petra mcp` from the PATH needs `pip install petra-lang` first, into a Python the client can find, and it serves whichever version is installed there, which may not match the skill. Without uv, take that route by hand:

```bash
pip install petra-lang
claude mcp add petra -- petra mcp
```

With uv and without the plugin, `claude mcp add petra -- uvx --from petra-lang==0.1.2 petra mcp` adds the server alone.

### Cursor

Cursor reads `.cursor/mcp.json` in a project, or `~/.cursor/mcp.json` for every project:

```json
{"mcpServers": {"petra": {"type": "stdio", "command": "uvx", "args": ["--from", "petra-lang==0.1.2", "petra", "mcp"]}}}
```

### Codex

```bash
codex mcp add petra -- uvx --from petra-lang==0.1.2 petra mcp
```

Or put the server in `~/.codex/config.toml`:

```toml
[mcp_servers.petra]
command = "uvx"
args = ["--from", "petra-lang==0.1.2", "petra", "mcp"]
startup_timeout_sec = 60
```

Codex waits 10 s for a server to start unless `startup_timeout_sec` says otherwise (reported in Codex's docs). Petra's server answered its handshake in 0.14 s on a quiet Windows PC, once its files were compiled (measured). A first start through uv also downloads the packages, so the entry allows a minute.

### The MCP registry

`server.json` is Petra's entry for the official MCP registry, named `io.github.NooterraLabs/petra`. It points at `petra-lang` on PyPI, run by uvx with the argument `mcp`. The package installs a `petra-lang` command for that, the same as `petra`. The registry takes the entry only if the package's README holds the line `mcp-name: io.github.NooterraLabs/petra`, which README.md carries in a comment.

### Publish a release to agents

Each step needs the maintainer, and they go in this order.

1. Release 0.1.2 to PyPI. Push the commit that numbers it 0.1.2 to main, and push the tag `v0.1.2` with it. The release workflow publishes the package. The plugin and the registry entry both pin `petra-lang==0.1.2`, and the plugin's server cannot start until PyPI has that version.
2. On a machine with uv, check the release with `uvx --from petra-lang==0.1.2 petra kinds`.
3. The plugin has nothing to publish. Once main holds `.claude-plugin/marketplace.json`, `/plugin marketplace add NooterraLabs/petra` reads it. Check it with `/plugin install petra@petra`, then `/mcp`, which lists `petra` as connected.
4. Install `mcp-publisher` as the registry's [quickstart](https://modelcontextprotocol.io/registry/quickstart) says. From the repository root, run

   ```bash
   mcp-publisher login github
   mcp-publisher publish
   ```

   The GitHub account must be an owner of the NooterraLabs organization. The registry grants an organization's namespace to its owners only, spelled as GitHub spells the organization, and compares names case for case (read in the registry's source). That is why the name is `io.github.NooterraLabs/petra` and not lower case.
5. Check the entry with `curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.NooterraLabs/petra"`.

For a later release, change the version in pyproject.toml first. `tests/test_plugin.py` then fails until `plugins/petra/.mcp.json`, `plugin.json`, `server.json`, the skill and this page name the new version. Publish the registry entry again once PyPI has the release.
