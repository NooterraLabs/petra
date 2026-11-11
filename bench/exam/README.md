# Sitting public benchmarks

`bench/exam` runs an agent on public benchmarks of hardware and CAD design, twice: alone, and with Petra's reports fed back to it. It exists to measure whether Petra changes what an agent hands in. It measures nothing yet. So far it has been run once, on ten tasks of each of two benchmarks, to show that the plumbing works.

## The rules

A benchmark is a held-out exam: nothing under `petra/`, `kernel/`, `proofs/`, `corpus/` or `examples/` may be written or changed for a benchmark, and no code here knows what a task asks. Whoever writes Petra's rules does not read tasks, answers or the result of a single task, so only totals leave a run, and `python -m bench.exam.summary` is the one command whose output may be pasted anywhere. Benchmark files and run records stay outside the repository and outside any synced folder, under `~/.petra/exam`.

## Run it

```bash
python -m bench.exam.run --benchmark cadtestbench --fetch --tasks 10 --seed 1
python -m bench.exam.summary
```

`--fetch` downloads the benchmark to `~/.petra/exam/data/NAME`, checks every file against the hash the adapter pins, writes `SOURCE.json` there with the URLs, the version and the hashes, and makes the grader's Python environment under `~/.petra/exam/venv/NAME`. It installs nothing into the system Python. The environment variable `PETRA_EXAM_HOME` names another place than `~/.petra/exam`.

| Option | Default | Means |
|---|---|---|
| `--benchmark NAME` | none | `cadtestbench` or `cadsilentfailure`, or `MODULE:NAME` for an adapter that lives elsewhere |
| `--arm` | `both` | `alone`, `petra`, or both on the same tasks |
| `--tasks N` | 10 | How many tasks the seed draws |
| `--seed S` | 1 | Draws the tasks. Both arms of a seed get the same ones. |
| `--model CMD` | `claude-wsl` | A command that reads a prompt on stdin and prints the answer, or a built-in name |
| `--attempts K` | 2 | The most attempts at a task, in either arm |
| `--max-calls N` | 60 | The most model calls one run makes |
| `--call-timeout`, `--grade-timeout`, `--petra-timeout` | 600, 300, 180 | Seconds for one model call, one grading and one `petra check` |
| `--guide FILE` | `petra/docs/skill.md` | What the petra arm is given to read. Repeat it to give more. |
| `--shakedown` | off | Marks the records as a test of the plumbing. The summary then says their numbers mean nothing. |

A run stops at the cap on calls with exit code 2, and after three failed model calls in a row with exit code 1. Run the same command again and it goes on where it stopped: it reads its run file and skips every attempt recorded there. A failed call is recorded and made again.

## The model is a command

The harness sends the prompt on stdin and reads the answer from stdout. Any provider's client can be plugged in as a command line.

- `echo` is no model. The answer is the prompt. It is for tests.
- `claude-wsl` is the Claude Code CLI inside WSL, used as a text function on the model alias `sonnet`: `claude -p --model sonnet --tools '' --max-turns 1 --safe-mode --setting-sources '' --strict-mcp-config --no-session-persistence --disable-slash-commands --system-prompt TEXT`, started in an empty folder under `/tmp`. It has no tools, reads no settings, plugins or instruction files, and keeps no session.

One thing about `claude-wsl` is not in the harness's hands. With a claude.ai login, version 2.1.310 of the CLI attaches the account's email address to every request, and no flag removes it. It also states the working folder, the platform and the date. The folder is the empty one under `/tmp`.

The harness itself puts no path of this machine in a prompt. `petra check` runs in an empty folder on bare file names, and every prompt has the paths of the home folder and the repository taken out before it is sent.

## The two arms

Both arms get the same tasks, the same model command, the same system prompt and the same number of attempts.

**alone.** The agent answers the task. Some benchmarks show an agent something between attempts, such as the measured size of what it made. That is the benchmark's public feedback, and it gives a retry: the agent sees the task again, its own previous reply and the feedback, up to K attempts. Most benchmarks show nothing, and then there is one attempt.

**petra.** The same, and the prompt also holds `petra/docs/skill.md` and five lines that say the agent may hand in a Petra design and its card in two fenced blocks. The harness runs `python -m petra check` on them and feeds the report back with the previous reply, up to the same K. A reply that hands in nothing gets no report. With no report and no feedback from the benchmark there is no retry, as in the alone arm.

The grader's result is never shown to the model. Every attempt is graded and recorded, and the last attempt's answer is the one that counts.

Four things to know before reading a comparison:

- On a benchmark with no feedback, the alone arm has one attempt and the petra arm has two whenever it hands in a design. A second look at one's own answer can help with no checker at all. The summary prints first-attempt passes beside final passes for this reason, and a fair comparison needs an arm that retries on an empty report.
- The agent has no tools. The guide tells it to run `petra kinds` and `petra new` to see what a design looks like, and it cannot. So it writes Petra's language from the guide alone. `--guide` can give it more to read.
- The agent may decline. In the shakedown it handed in nothing, every time (see below).
- `petra check` finds the kernel through `PETRA_VERIFY` or in `kernel/.lake/build/bin`. Without one, each report says that the kernel did not run.

## What a report counts as

Every reply of the petra arm is counted once:

| Status | Means |
|---|---|
| PASS, FAIL, UNKNOWN, MARGINAL | Petra read the design and gave that status |
| REFUSED | Petra read it and refused it as an input error |
| DISAGREE | The kernel rejected a proof the Python checker took |
| ERROR | `petra check` crashed or ran past its time limit |
| NONE | The agent handed in no design, so Petra said nothing |

Petra "said something" on the first five. The summary also counts how many reports were fed back and how often the next answer differed from the one before.

## What is recorded and what is not

One JSON line is written for each model call, to `~/.petra/exam/runs/BENCHMARK-seedS-MODEL.jsonl`. A shakedown writes to a file of its own, whose name ends in `-shakedown.jsonl`, so a run that counts never goes on from one that does not. `records.py` lists the fields. A record holds the benchmark and its version, the task id, the arm, the seed, the attempt, the model command, the prompt and the reply in full with their hashes, the answer the grader took, the benchmark's feedback, Petra's report with the design and the card, the grade with what the grader said, lengths in characters, and seconds for the model, Petra, the grader and the whole attempt.

Not recorded: tokens, because a command prints only text. Not kept: the folder the grader worked in. Not built yet: a task is sat once for a seed, so a benchmark that asks for several repetitions of each task needs a repetition number in the record.

The summary prints, for each benchmark, model, seed and arm: tasks answered, calls made and failed, final answers that passed, the mean of the benchmark's own score, outcomes by class, what retries did, Petra's statuses, characters and seconds. The classes are:

| Outcome | Means |
|---|---|
| pass | The answer met the benchmark's pass condition |
| wrong | The answer ran and the grader failed it |
| invalid | The grader could not build or run the answer |
| no_answer | The reply held nothing the grader takes |
| grader_error | The grader itself failed or ran past its time limit |

What a run prints while it works has no task id and no result of a single task.

## Adapters

An adapter knows a benchmark's file format and how its grader is called. It fetches the files, lists the task ids, gives a task's prompt, gives the benchmark's own feedback if it defines any, and grades an answer with the benchmark's own grader. The grader runs in its own environment, started by `adapters/_in_venv.py` with `python -I -X utf8`.

Both graders here execute the model's code. That is how these benchmarks grade. It is not a sandbox: the code runs as the user, held only by the time limit.

- `cadtestbench`: CADTestBench. Four parquet files from Hugging Face and the `cadtestbench` package from the benchmark's repository, each file pinned by hash. A task is one prompt of one of the two partitions. The repository's stored answers of other models are not fetched. One test of the 5,937 imports a package that the grader's stated dependencies do not install, so that test fails for any answer.
- `cadsilentfailure`: cad-silent-failure-bench. One archive of the repository at a pinned commit, from which only the tasks, the grader and the licences are kept. Reference solutions and other models' answers never reach the disk. Its public feedback is the measured properties of the agent's own solid, as in the benchmark's tool-use condition.

To add a benchmark, write a module with an `Adapter` subclass and add it to `REGISTRY` in `adapters/__init__.py`. Read the grader before running it. Write no task id, task text or expected value into the module.

## Tests

`tests/test_exam.py` sits a toy benchmark of four made-up questions with a fake model, both in `tests/exam_toy.py`. It needs no model, no download and no grader environment.

## The shakedown of 2026-11-11

Each benchmark was run once: 10 tasks, both arms, seed 1, K = 2, the model `claude-wsl`, no kernel. The run shows that the plumbing works. Its numbers mean nothing and compare nothing: ten tasks, one sample of the model for each, and a petra arm in which Petra never spoke.

| | cadtestbench | cadsilentfailure |
|---|---|---|
| Model calls, and how many failed | 20, 0 | 40, 0 |
| Attempts a task | 1 in both arms | 2 in both arms, from the benchmark's own feedback |
| alone: final answers that passed | 8 of 10 | 10 of 10 |
| petra: final answers that passed | 7 of 10 | 10 of 10 |
| Outcomes other than pass | wrong: 2 alone, 3 petra | none |
| Retries that changed the answer | no retries | 2 of 10 alone, 3 of 10 petra |
| Replies on which Petra said something | 0 of 10 | 0 of 20 |
| Characters sent, alone and petra | 7,340 and 90,110 | 31,723 and 197,511 |
| Wall time | 4 min 26 s | 6 min 5 s |

Nothing broke: no model call failed, no grader failed, and no answer was unreadable.

In no reply of the petra arm did the agent hand in a design. So `petra check` never ran on a benchmark task, and the two arms differ only by the 8,000 characters of guide in the prompt.

To see the loop run with the real model, a made-up task about a bolted lap splice, which is from no benchmark, was put to it four times in the petra arm. Three times it handed in nothing, with the guide alone, with what `petra kinds` and `petra new` print added, and with a note added that the harness runs the checker. Each time it gave the same reason: the guide says a lap is UNKNOWN until the card waives four mechanisms, and that waivers are not the agent's to write. The fourth time the task itself demanded the hand-in. Then the loop ran: a design and a card came in, `petra check` gave UNKNOWN, the report went back, and a second answer came.

## Which benchmarks can be sat

Checked on 2026-11-11 from each benchmark's own repository, dataset page or paper page. "Ran here" means the grader was run on this PC: Windows 10, Python 3.11, no GPU, WSL Ubuntu with KiCad 9.0.9 and ngspice 42, and no Docker, OpenSCAD, FreeCAD, Blender, Gmsh or CalculiX. Everything else in that column is a reading of the stated requirements and was not tried. Tasks are described for the whole benchmark only.

The order is by four things: tasks public, grader deterministic, runs here for free, and in the category, which is an agent designing a physical part, structure, mechanism or board against requirements. It is not an order of where Petra would do well. The last column is about Petra as it is today: a checker of designs written in its own language against a card of loads and limits, with one deck of rules for bolted steel lap joints and older built-in kinds for steel connections, trusses, wire circuits, one bolted joint, DC ratings of a small parts catalogue, and meshes of printed parts.

### Can be sat here now

| Benchmark | Tasks public | Grader public | Runs on this PC | In and out | Where Petra could say anything today |
|---|---|---|---|---|---|
| 1. [CADTestBench](https://github.com/dimitrismallis/CADTestBench) | Hugging Face dataset, 200 parts with two prompts each, 400 in all. MIT. No gate. | In the repository. Deterministic: 5,937 executable tests on the solid. Needs CadQuery. | Ran here, natively, about 4 s an answer. | A text requirement in, a CadQuery script out. One shot. No feedback defined. | Nothing yet. A task states the shape and sizes of one part. Petra has no check of a solid against stated sizes, and a task states no load, material or process. |
| 2. [cad-silent-failure-bench](https://github.com/rodriguescarson/cad-silent-failure-bench) | In the repository, 13 tasks with 122 checks. CC BY 4.0, code MIT. No gate. | In the repository. Deterministic: kernel measurements held to tolerance bands. Needs build123d. | Ran here, natively, 7 to 15 s an answer. | A text specification in, build123d code out. One shot, or a loop in which the agent sees the measured properties of its own solid. | Nothing yet, for the same reason. |

### Could be sat with more setup

| Benchmark | Tasks public | Grader public | Runs on this PC | In and out | Where Petra could say anything today |
|---|---|---|---|---|---|
| 3. [CADClamp](https://github.com/ChristianNHill/cadclamp) | In the repository, 47 prompts, with 20 older and 10 extra. Code Apache-2.0, prompts CDLA-Permissive-2.0. | Deterministic geometry and printability checks on an STL. Its own runs use Docker sandboxes. | Not tried. Scoring an STL should run natively. The sandbox needs Docker. | Text in, a CAD program in one of seven languages out. One shot. | Nothing through text. Petra's parts kind has rules for a print process, but it reads a mesh file with a material and a process, which a task does not give. |
| 4. [CadEval](https://github.com/wgpatrick/cadeval) | In the repository, 25 tasks. No licence file. | Deterministic: OpenSCAD render, then mesh measures against reference meshes. | Not tried. Needs OpenSCAD. | Text in, OpenSCAD out. One shot. | Nothing yet. |
| 5. [PCBSchemaGen](https://github.com/HZou9/PCBSchemaGen_v2) | Hugging Face and the repository, 227 tasks in two suites. Tasks MIT. | In the repository under PolyForm Noncommercial. Deterministic: SKiDL run, KiCad ERC, rule layers. Linux. | Not tried. WSL has KiCad 9. The noncommercial licence of the grader needs the owner's decision first. | A text task in, SKiDL Python out. One shot, or a loop with the verifier's feedback. | Nothing yet. Petra has no check of a schematic or a netlist. |
| 6. [EngDesign](https://github.com/AGI4Engineering/EngDesign), open subset | In the repository, 101 tasks, of which 67 or 53 need no paid tool (the README and the project page differ). MIT. | A script for each task: simulation and numeric checks with partial credit. Docker. | Not tried. Needs Docker. | A text prompt in, design parameters or code out. One shot, or rounds with scores fed back. | Not known without reading tasks. Nine domains, and by one outside count 13 of 101 tasks are physical engineering. |
| 7. [Certified feasibility margins](https://github.com/nbbllxx0/Certified-feasibility-margins) | In the repository, generated item sets. A hold-out of 76 items is not released. Code MIT, data CC BY 4.0. | Deterministic parser and grader with two reference solvers. NumPy, SciPy, SymPy. Python 3.12 is stated. | Not tried. | A text problem in, accept or reject with numbers out. One shot. It judges a given design and designs none. | Nothing yet. The items are beams and disks at their limit loads, and Petra has no model of either. |
| 8. [CAD-bench](https://github.com/CAD-bench/cad-bench) | In the repository, 17 tasks. Seven functional tasks are withheld. MIT. | Deterministic geometry checks, and rigid-body simulation in Blender. Harbor and Docker. | Not tried. Needs Docker. | An instruction in, a Build123D file out. An agent in a sandbox. | Nothing yet. |
| 9. [Parametric CAD Bench V3](https://cadbench.ai) | On the Harbor hub, 100 tasks. Apache-2.0. Whether the hub wants a login was not verified. | [freecad-validator](https://github.com/gNucleus-AI/freecad-validator), deterministic, FreeCAD 1.1. Tasks run under Harbor and Docker. | Not tried. Needs Docker and FreeCAD. | Text or a drawing in, a FreeCAD file out. An agent with a shell, one attempt. | Nothing yet. |
| 10. [EDA Bench](https://github.com/EDA-bench/eda-bench) | In the repository, 35 tasks. No licence for the benchmark as a whole. | Deterministic: connectivity, ERC, DRC, ngspice. Harbor and Docker. | Not tried. Needs Docker. | An instruction and a tool container in, a routed KiCad project out. An agent with tools. | Nothing yet. Petra reads a KiCad board's geometry and checks DC ratings of parts in its own catalogue, and neither is what is graded. |
| 11. [StructBench](https://github.com/rapidcad/structbench) | In the repository, 75 load cases by the README and 30 by the datacard. No licence file. | Deterministic: design space, load path, a safety factor from Gmsh and CalculiX, mass. The script imports modules the file listing does not show. | Not tried. Needs Gmsh and CalculiX. | A load case in, a CadQuery part out. | Nothing yet. This is the nearest in kind: a part held to loads. Petra has no deck for a free-form part under load. |
| 12. [PCBWorld-Bench](https://github.com/LGAI-Research/PCBWorld) | Boards are fetched from a third-party repository by a script. Code BSD-3, engine GPLv3. | Deterministic: KiCad's own DRC and connectivity. Linux, Python 3.12, an engine build. | Not tried. | A placed board in, a routed board out, through tool calls. Many turns with DRC feedback. | Nothing yet. |
| 13. [BenchCAD 1.0](https://github.com/BenchCAD/BenchCAD-main) | Hugging Face, 17,900 image-to-code items and two smaller sets. CC BY 4.0. | Deterministic: volume overlap with a reference solid. | Not tried. The input is images, which a text command cannot take. | Four views of a part in, a CadQuery program out. | Nothing. The score is likeness to a reference shape. |
| 14. [LMBuild](https://github.com/Lumos-Jiateng/LMBuild) | Hugging Face, 200 core tasks in 12 GB. CC BY-NC-SA 4.0. | Twelve metrics. Nine run on a CPU, three need model judges on a GPU. | Not tried. | An object's name and a photo in, an assembled structure out, through tool calls. | Nothing yet. |
| 15. [RLE-Bench](https://github.com/RLE-Bench/RLE-Bench) | In the repository. Two of nine task families are mechanical design. MIT. | Simulation. Docker, Linux, Python 3.12. | Not tried. Needs Docker. | Not verified. | Not known. |

### In reach but outside the category

These publish tasks and a deterministic grader. They are chip design, simulation setup or question answering, and none asks for a physical part, structure, mechanism or board. Petra can say nothing on any of them today.

| Benchmark | What it is | What the grader needs |
|---|---|---|
| [AnalogPortBench](https://github.com/saeidrajabii/AnalogPortBench) | 54 analog circuit porting tasks, MIT | ngspice and the SKY130 models, in WSL |
| [AnalogCoder](https://github.com/laiyao1/AnalogCoder) and AnalogCoder-Pro | 24 analog circuit tasks, and more in Pro | ngspice and PySpice |
| [VerilogEval v2](https://github.com/NVlabs/verilog-eval), [ChipVerilog](https://github.com/HKUSTGZ-MICS-LYU/ChipVerilog), [RealBench](https://github.com/IPRC-DIP/RealBench), [CVDP](https://github.com/NVlabs/cvdp_benchmark) | RTL from a specification | Icarus Verilog, Verilator or Yosys. CVDP needs Docker, and 280 of its 749 rows need a paid simulator. |
| [ICLayout-Bench](https://github.com/lizhangmai/ICLayout-Bench) | 92 public chip layout tasks | Docker and open PDKs |
| [FoamBench](https://github.com/NREL-Theseus/cfdllmbench) | 126 CFD case setups | OpenFOAM 10 |
| [DesignQA](https://github.com/anniedoris/design_qa), [PCB-Bench](https://github.com/digailab/PCB-Bench), PE Civil Bench | Questions with reference answers | Python. PE Civil Bench ships no scorer. |

### Cannot be sat

| Why | Benchmarks |
|---|---|
| Gated: a login, a form or an agreement | BenchCAD 2.0 and 2.1 Core, PLE (and 56 of its 85 tasks are hidden), Text2CAD, MARB's answer key |
| Tasks or grader not released, or held out by design | CADEngBench, RealCADBench, FunCADBench (the harness is out, the tasks are not), Text2CAD-Bench (references withheld), HWE-Bench, EEBench, PCBBench, PCB Gym, PCBInnoBench, Long-Horizon Analog Design Bench, SAFTAC, Build-A-Chip-Bench, RWE-bench, MBEval, Physics-in-the-Loop, RoboForge, FrontierCAD, PartBench, PolyBridgeBench, CADGenBench, the beam study of arXiv 2507.02938 |
| Needs a paid tool | FEABench (COMSOL), RTLLM (Synopsys VCS), the commercial rows of CVDP, the formal check of RealBench |
| Judged by a model or by people, or no grader at all | MUSE, neuralCAD-Edit, CADBench of BlenderLLM, Query2CAD, CADPrompt, pcba-bench, 14 of PLE's 29 open tasks |
| Needs hardware or far more machine than this PC | Embedded Arena (physical boards), CADWorld (a Linux host with KVM and 35 GB), EngiWorld (98 GB of virtual machines), 3DCodeBench (268 GB, and a GPU for most scores) |
| Not a benchmark of tasks, or tied to its own system | CAD-Recode, StructureClaw-Bench, the closed-loop compliance study of arXiv 2608.07978, the KiCad set of Cua-Bench (not found) |

No public benchmark was found that asks for a steel connection or a bolted joint and grades it against AISC 360, Eurocode 3 or an ASME code.
