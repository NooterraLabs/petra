# The lift pilot: steel connections with and without Petra

This page covers the lift pilot of P3 in the [plan](plan.md). It asks whether agents design safer steel connections with Petra than without it. That is the project's central bet. If the agents without Petra do as well, the bet is wrong, and this page says so.

The protocol below was committed before any agent ran a held-out task. The results come after it.

## Protocol

### Tasks

The tasks are the first 10 tasks of seed 303 whose draft fails, chosen by `agent_tasks` in `scripts/in_the_loop.py`, as P2 chose its agent tasks. A draft is `petra new KIND` with the job written in, so a task whose draft fails needs real sizing. Seed 303 was unused. Seed 101 was P2's development seed and seed 202 its held-out seed, and neither is used here.

| Task | Kind | Basis | Members and eccentricity | Load to |
|---|---|---|---|---|
| 303-003 | seated | ASD | beam W16x26, support W10x49 web | shear 15.843 kip |
| 303-004 | bolt_bracket | ASD | support W12x65 flange, eccentricity 6 in | shear 88.107 kip |
| 303-005 | hanger | ASD | support W16x31 flange | tension 34.745 kip |
| 303-006 | shear_tab | ASD | beam W18x35, support W10x49 web | shear 45.988 kip |
| 303-014 | double_angle | LRFD | beam W24x55, support W14x61 web | shear 142.863 kip |
| 303-015 | single_angle | ASD | beam W24x55, support W14x61 flange | shear 39.449 kip |
| 303-018 | shear_tee | ASD | beam W12x26, support W10x49 flange | shear 9.817 kip |
| 303-019 | shear_end_plate | LRFD | beam W21x44, support W12x65 flange | shear 139.063 kip |
| 303-021 | bolt_bracket | ASD | support W12x40 flange, eccentricity 8 in | shear 39.889 kip |
| 303-022 | weld_bracket | ASD | support W12x40 flange, eccentricity 5 in | shear 48.42 kip |

Each task gives the job only: the kind, the basis, the members, a bracket's eccentricity, and the loads. The design is left blank.

### Agents

Each task goes to two fresh general-purpose agents, one per arm. Both arms run the same model as the agent that ran this pilot (Claude Opus 5.5), at effort xhigh, with no memory of this work. Each agent gets its brief as its whole prompt. The agents run in two waves: tasks 1 to 5 in both arms, then tasks 6 to 10 in both arms. Each agent gets one attempt. An agent that stops before it writes `final.petra`, for a reason outside its work such as an API error, gets one fresh rerun, and the report names it.

`python scripts/pilot_lift.py briefs` writes the briefs. They are in [pilot_lift](pilot_lift), one folder per arm and task. Each agent works in its own folder outside the repository. The folder names do not name the arm, and no brief says that another agent works the same task.

**With Petra.** The brief is P2's brief with two changes. It states the goal both arms share, and it asks for the final files below. The agent runs Petra from a venv that holds only the wheel built from `a91486c` (sha256 `6b824573586e83317d66a774ef44f789b9c1c5f260e1ad33e8bb6585e0224e20`). The brief tells it to read `petra docs skill` first. It has at most 10 checks, as in P2, and every other `petra` command is free.

**Without Petra.** The brief has the same job and the same goal. The folder also holds `reference.md`, a copy of `docs/reference.md`, and `example.petra`, the example design of the task's kind from `examples/steel/`. The agent must write its answer in the same format, so it gets the format's reference. `petra new KIND` prints the same example to the agent with Petra, less one comment line, so both arms start from the same text and the checker is the one difference. The agent uses Python 3.11.9 with numpy 2.4.6 and scipy 1.17.1. Petra is not installed in that Python. The brief tells the agent not to run, import, install or look for Petra, and not to read anything outside its folder. It may use what it knows of AISC 360-22 and the Steel Construction Manual.

**The goal, in both briefs.** The connection is safe under AISC 360-22 for the loads and can be built as drawn. Among safe designs, a lighter one is better, but safety comes first.

**The end, in both arms.** The agent saves `final.petra` and writes `claim.json`, with `safe` (true or false), the governing limit state, its utilisation and notes. `safe` is the agent's own claim that the design is safe under AISC 360-22 for the loads and buildable.

**Audit.** After the runs, each agent's folder and transcript are searched. For an agent without Petra, any `petra` command, `import petra`, package install, or read of a path in the repository excludes its design from the arm's numbers. That task then gets one fresh rerun, and the report gives both. For an agent with Petra, the transcript gives the number of `petra check` runs, and any read of Petra's source is reported.

### Grading

`python scripts/pilot_lift.py grade docs/pilot_lift --reference docs/pilot_lift/reference.jsonl --adjudication docs/pilot_lift/adjudication.json --usage docs/pilot_lift/usage.json` grades both arms. It trusts nothing an agent says. Each `final.petra` gets:

1. **Petra's verdict at `a91486c`.** This branch changes no file under `petra/`.
2. **The job check**, `petra.loop.Task.faithful`. The design must hold one component of the task's kind, keep the basis, members and eccentricity, carry each load from 0 to at least the job's top, and waive nothing.
3. **The outside judge** in `judges/`, for buildability.
4. **An adjudication of every check Petra does not certify.** Petra is stricter than the code in a few documented places. So for each such check, a hand calculation to AISC 360-22, and the Manual method the code relies on, decides it at the design's written values. The verdict is `real` when the code check fails. It is `conservative` when the code check holds and Petra fails it by a stricter reading:
   - the four fit readings of [steel_connections.md](steel_connections.md) §5a;
   - the elastic method for eccentric bolt and weld groups, where the instantaneous-centre method gives more (§7 there);
   - J10.8 and J10.9 not credited, and a stiffened seat's weld group taken without its return (§6 there);
   - the worst point of a tolerance box where the code reads the nominal value, such as the 1/4 in underrun that Petra takes off `beam_edge` and adds to `setback`, which the Manual recommends and the code does not require.

   A difference not on this list is recorded with its reason. A Manual check that meets a requirement of AISC 360-22, such as rotation capacity under B3.4a, is `real` when the design breaks the Manual's limit and shows the requirement no other way. Fit and wrench-clearance checks count for buildability. The rest count for safety. `docs/pilot_lift/adjudication.json` holds each verdict and its reason, and `docs/pilot_lift/hand_checks.md` holds the calculations.
5. **A hand check of the governing limit state on a sample.** The sample is every design an agent called safe that Petra does not pass, plus two passing designs per arm drawn with `random.Random(303)`. A hand check that finds a real violation in a design Petra passes is entered as `real` and reported as a false PASS.
6. **CalculiX.** If `scripts/calculix_check.py` exists on a branch when grading starts, it checks the sample. If not, CalculiX is recorded as open.

A design is **safe** when Petra can read it, it keeps the job, and no check is adjudicated a real strength or detailing violation. It is **buildable** when the judge finds nothing and no fit check is adjudicated real. A file Petra cannot read is neither. If the intended design behind such a file is plain, a fix of the syntax alone is graded too and reported apart. The **strict** reading counts only a Petra PASS that keeps the job and that the judge clears.

The **reference optimum** is the design that `petra.loop.solve` keeps for the task, with a budget of 10 checks and the judge reading every design it keeps. If the loop reaches no PASS, the minimiser starts from the generator's design. `python scripts/pilot_lift.py reference` writes it.

### Measures, per arm

- The share of final designs that are safe and buildable.
- The share the agent called safe that are not safe and buildable. This is the key number. The report gives every such case and its cause.
- The mass of each safe design over the reference optimum's, and P3's score: the optimum's mass over the design's, or 0 for a design that is not safe and buildable.
- The checks run, from the transcript, for the agents with Petra. The tool calls, tokens and minutes each agent's usage report gives, for both arms.

Ten tasks per arm is a pilot. The report gives counts and claims no significance.

### What the result means, fixed in advance

- The bet holds on this pilot if the agents with Petra call fewer unsafe or unbuildable designs safe than the agents without it, and produce at least as many safe and buildable designs.
- The bet is wrong on this pilot if the agents without Petra do as well on both counts.
- Any other result is mixed, and the report says which way each count went.
