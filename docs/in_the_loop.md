# Petra in a coding agent's loop

This page covers P2 of the [plan](plan.md). P2 puts Petra inside the loop of a coding agent or a search: write a design, check it, repair it until it passes, then make it lighter without losing a certified margin. It has three parts:

- `petra.check(text)` returns plain data, and a FAIL names the inputs that would move it most.
- `petra mcp` serves Petra's tools to an MCP client, and `petra docs skill` prints a SKILL.md for coding agents.
- `petra/loop.py` runs the repair-and-minimise loop on steel connections.

The last section says how P2 is measured. Its numbers were fixed before the held-out measurement ran.

## Check from Python

```python
import petra

result = petra.check(open("tab.petra").read())
result["status"]            # "PASS", "FAIL", "UNKNOWN", "MARGINAL" or "INPUT_ERROR"
result["repair"]["moves"]   # on a FAIL: the inputs to change, best first
```

The result is the same JSON that `petra check --json` prints. On a FAIL, the `repair` key holds the moves. A move changes one number in the design, such as `tab.rows` or `tab.plate thickness`, by one step up or down. Petra re-checks each step and sorts the moves by the utilisation of the governing check after the step, lowest first. For the top three moves it also searches further in the same direction for a value at which the governing check holds, and reports that value and the design's status there. When no number lowers the check, the moves swap an angle or tee for another shape of its family instead. `petra check` prints the same moves as text under the governing check. The [Python API](../petra/docs/api.md#repair) gives the exact shape.

A move is a suggestion from a search, not a verdict. Only a check of the edited design says whether it passes.

## Use from an MCP client

`petra mcp` runs a Model Context Protocol server on stdin and stdout. It uses only the Python standard library. Its tools are `check`, `kinds`, `new`, `registry_list` and `docs`. `check` returns the text that `petra check` prints, and the data of `petra.check` as structured content. The server speaks protocol revision 2026-07-28, in which each request names its revision, and answers `initialize` for clients of 2025-11-25 back to 2024-11-05.

`petra docs skill` prints a SKILL.md for coding agents. It says how to start from `petra new`, how to read a FAIL and its moves, and what an agent must never change to reach a PASS. Those are the loads, the claims and the waivers.

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

## The repair-and-minimise loop

`petra/loop.py` runs on tasks. A task is a job a user would give: a connection kind, the design basis, the members, a bracket's eccentricity, and the loads. The loop never changes those, even when a repair move offers it.

1. **Draft.** Start from `petra new KIND` and write the task's lines and loads into it.
2. **Repair.** Check the draft. On a FAIL, take a move from the repair, as an agent reading the output would: a move whose clearing value passes, else the clearing move that leaves the fewest failed checks, else the best one-step move. Repeat until PASS, or until 10 checks are spent.
3. **Minimise.** From the PASS, step each number on the component's lines toward less mass, and double the step while the design still passes. Swap each angle or tee for a lighter shape that passes. Repeat until no edit is lighter and passes.

The loop keeps a design only when Petra returns PASS for it. So every margin it keeps is certified by the kernel. A MARGINAL design is not kept.

The outside judge in `judges/` reads every design the loop keeps. The judge computes the geometry on its own, so it can catch a design that Petra passes but that does not fit. The minimiser looks for the edge of the passing region, so it is the strongest breaker the project has. The [CalculiX spot check](calculix_check.md) models each kept optimum's governing element with finite elements and compares its capacity with Petra's.

The mass is an estimate. Plates and stiffeners count as rectangles, angles and tees as their section over the connection's length, and each bolt as its shank over a 2 in grip with a head and a nut. It ranks the designs of one task against each other. It is not a bill of materials.

To run the loop:

```bash
python scripts/in_the_loop.py loop --seed 202 --n 100 --workers 4 --log loop.jsonl
```

## How P2 is measured

P2 is done when two things hold:

- On held-out steel tasks, a fresh agent reaches PASS within 10 checks on at least 80% of tasks.
- No design the loop keeps fails the geometry model or the CalculiX spot check.

These numbers were frozen in the commit that added this page, before any held-out run. They live in `scripts/in_the_loop.py` as `CHECKS = 10` and `SHARE = 4/5`.

**Tasks.** Tasks come from the steel deck's design generator, `petra/models/steel/generate.py`. A design it draws becomes a task when it is one of the ten connection kinds, the deck passes it at the drawn load, it is outside the sample that needs no detailer, and it has no toleranced line. The task keeps the design's kind, basis, members, eccentricity and loads, and drops the rest. The generator's design stays as the reference, which shows that the job can be done. `flange_force` is not a task kind, because it has no part to size.

The loop and the skill were built on seed 101. The held-out tasks come from seed 202, and nothing was tuned on them.

**The loop run.** The loop runs on the first 100 tasks of seed 202. A task counts as reached when the loop's first PASS comes within 10 checks. This run measures the repair moves, not an agent.

**The agent run.** The agent tasks are the first 10 tasks of seed 202 whose draft fails, so that `petra new` with the job written in is not enough. Each task goes to one fresh agent with no memory of this work. `python scripts/in_the_loop.py briefs DIR --petra PATH` writes the brief. The agent may use every `petra` command and document, but not Petra's source. It saves each design it wants checked as `try1.petra`, `try2.petra` and so on, and each `petra check` of one of them counts as a check. `python scripts/in_the_loop.py score DIR` then re-checks the tries in order. A task counts as reached when a try within the first 10 passes, keeps the job, and draws no violation from the judge. The bar is 8 of 10.

**Geometry.** The judge reads every design the loop keeps in the loop run, and the first passing try of each agent. The bar is no violation.

**CalculiX.** The spot check against CalculiX is open. CalculiX is not installed where this ran, so no design has been checked against it yet.

## Results

**Development, seed 101.** These runs came before the freeze, and their misses were used to fix the loop. On 30 tasks, the loop reached PASS within 10 checks on all 30 (measured). 19 drafts passed at the first check. The 11 that needed a repair took a median of 2 checks and at most 5. The judge read the 218 designs the loop kept and found no violation. One pilot agent, on task 101-005, passed at its first check.

**Held out, seed 202.** All numbers below are measured, on the code of the freeze commit. Both bars are met.

| Measure | Result | Bar |
|---|---|---|
| Fresh agents that reached a faithful PASS within 10 checks | 10 of 10 | 8 of 10 |
| Loop tasks that reached PASS within 10 checks | 97 of 100 | none set |
| Judge violations in the designs the loop kept (644) and the agents' passing tries (10) | 0 | 0 |
| Loop optima that change the job | 0 | 0 |
| CalculiX spot checks | none run | open |

The loop run took 4 workers on a 4-core ARM machine. A task took a median of 3.3 s and at most 48 s. The log, one JSON line per task with the first PASS and the optimum, is [in_the_loop_log.jsonl](in_the_loop_log.jsonl).

- 60 drafts passed at the first check. The 37 that needed a repair took a median of 2 checks and at most 4.
- The minimiser checked 3983 designs and kept 547. The optimum's estimated mass over the first PASS's had a median of 0.66 and a range of 0.22 to 1.00.
- The loop missed 3 tasks. On 202-013 and 202-100, double angles into a W10x49's web, the outstanding legs are wider than the web's flat. The fix is the word `outstanding short`, which is neither a number nor a shape, so the repair offers no move. On 202-020, a single angle at 130 kip, one-number moves went back and forth between rows, pitch and edge distance. The agent on the same task changed the bolt diameter, the threads and the rows together.

The agents' briefs and tries are in [in_the_loop_agents](in_the_loop_agents). `python scripts/in_the_loop.py score docs/in_the_loop_agents` re-scores them.

| Task | Kind | Checks | Statuses |
|---|---|---|---|
| 202-001 | shear_tab | 1 | PASS |
| 202-009 | stiffened_seat | 1 | PASS |
| 202-013 | double_angle | 1 | PASS |
| 202-018 | hanger | 1 | PASS |
| 202-020 | single_angle | 2 | FAIL, PASS |
| 202-024 | hanger | 1 | PASS |
| 202-029 | hanger | 2 | FAIL, PASS |
| 202-032 | shear_tee | 1 | PASS |
| 202-040 | bolt_bracket | 1 | PASS |
| 202-041 | weld_bracket | 1 | PASS |

Read these numbers with four limits:

- The agents did not start from the failing draft. Each read `petra docs`, `petra new` and the reference, then sized its own design. So 8 of 10 passed at the first check, and only 2 used a repair. Both of those took Petra's first move and passed at the next check. The run shows that an agent can design with Petra's documents. It says little about repair.
- The agents were general-purpose subagents of the same model that wrote the skill and the docs, with no memory of this work. A different model may do worse.
- The agent on 202-032 ran `petra explain` four times on two versions of its design before its one check. `explain` evaluates the design, but the brief did not count it as a check. Counting each run as a check gives 5 checks, which still reaches the bar.
- Ten tasks is a small sample. One more miss would leave 9 of 10, and three more would fall below the bar.
