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

## Results

All 20 agents ran once and wrote `final.petra` and `claim.json`. None needed a rerun. Each agent's brief, designs, claim and Python files are in [pilot_lift](pilot_lift). [usage.json](pilot_lift/usage.json) has each agent's usage, [reference.jsonl](pilot_lift/reference.jsonl) the reference optima, [adjudication.json](pilot_lift/adjudication.json) the verdicts and [grades.jsonl](pilot_lift/grades.jsonl) the graded rows.

### The audit

`python scripts/pilot_lift.py audit` read every transcript.

- No agent without Petra ran, imported, installed or looked for Petra, and none read the repository. The only file one of them read outside its folder was the harness's output of its own background command.
- The agents with Petra ran 2 to 5 checks each, with a median of 3, under the cap of 10. Three ran the same file twice. One check, with_petra/303-019's `try2.petra`, was an INPUT_ERROR from a byte-order mark at the start of the file. The agent deleted that file and wrote another.
- Two agents with Petra, on 303-005 and 303-021, saved the text of `petra docs reference` to a file outside their folders, read it and deleted it. No agent with Petra read Petra's source.

### Per arm

| Measure | With Petra | Without Petra |
|---|---|---|
| Final designs safe and buildable | 10 of 10 | 10 of 10 |
| Petra PASS, job kept, judge finds nothing (the strict reading) | 10 of 10 | 7 of 10 |
| Called safe by the agent | 10 of 10 | 10 of 10 |
| Called safe but not safe and buildable | 0 of 10 | 0 of 10 |
| ... a real AISC 360-22 violation | 0 of 10 | 0 of 10 |
| ... a part that cannot be built | 0 of 10 | 0 of 10 |
| ... a file Petra cannot read, or a changed job | 0 of 10 | 0 of 10 |
| Petra does not pass, but no check is really violated | 0 of 10 | 3 of 10 |
| Mass over the reference optimum: median (range) | 0.79 (0.69 to 1.06) | 0.93 (0.59 to 1.31) |
| Total mass of the 10 designs | 154.9 lb | 178.2 lb |
| Score, optimum mass over design mass: mean | 1.23 | 1.11 |
| Checks run: median (range) | 3 (2 to 5) | none |
| Tool calls: median (range) | 26 (20 to 50) | 16.5 (12 to 27) |
| Tokens, thousands: median (range) | 171 (140 to 262) | 164 (140 to 174) |
| Minutes: median (range) | 21.7 (14.7 to 58.1) | 11.7 (7.6 to 23.5) |

### Per task

| Arm | Task | Kind | Petra | Not certified | Judge | Claim | Safe | Buildable | Mass, lb | Over optimum |
|---|---|---|---|---|---|---|---|---|---|---|
| with_petra | 303-003 | seated | PASS | - | - | safe | yes | yes | 11.2 | 0.79 |
| with_petra | 303-004 | bolt_bracket | PASS | - | - | safe | yes | yes | 31.0 | 0.78 |
| with_petra | 303-005 | hanger | PASS | - | - | safe | yes | yes | 7.7 | 0.73 |
| with_petra | 303-006 | shear_tab | PASS | - | - | safe | yes | yes | 7.6 | 0.92 |
| with_petra | 303-014 | double_angle | PASS | - | - | safe | yes | yes | 28.3 | 1.06 |
| with_petra | 303-015 | single_angle | PASS | - | - | safe | yes | yes | 15.3 | 0.89 |
| with_petra | 303-018 | shear_tee | PASS | - | - | safe | yes | yes | 10.9 | 0.70 |
| with_petra | 303-019 | shear_end_plate | PASS | - | - | safe | yes | yes | 11.2 | 0.79 |
| with_petra | 303-021 | bolt_bracket | PASS | - | - | safe | yes | yes | 24.8 | 0.89 |
| with_petra | 303-022 | weld_bracket | PASS | - | - | safe | yes | yes | 6.9 | 0.69 |
| without_petra | 303-003 | seated | UNKNOWN | spacing_max | - | safe | yes | yes | 11.0 | 0.77 |
| without_petra | 303-004 | bolt_bracket | PASS | - | - | safe | yes | yes | 37.6 | 0.95 |
| without_petra | 303-005 | hanger | PASS | - | - | safe | yes | yes | 13.7 | 1.31 |
| without_petra | 303-006 | shear_tab | FAIL | bolts 1.08 | - | safe | yes | yes | 7.6 | 0.92 |
| without_petra | 303-014 | double_angle | PASS | - | - | safe | yes | yes | 30.3 | 1.14 |
| without_petra | 303-015 | single_angle | PASS | - | - | safe | yes | yes | 15.2 | 0.89 |
| without_petra | 303-018 | shear_tee | PASS | - | - | safe | yes | yes | 12.2 | 0.78 |
| without_petra | 303-019 | shear_end_plate | PASS | - | - | safe | yes | yes | 13.3 | 0.94 |
| without_petra | 303-021 | bolt_bracket | PASS | - | - | safe | yes | yes | 31.4 | 1.13 |
| without_petra | 303-022 | weld_bracket | FAIL | weld 1.68, weld_base_metal 1.54 | - | safe | yes | yes | 5.9 | 0.59 |

The outside judge found nothing in any of the 20 designs, and every design keeps its job.

### Designs called safe that are not

There are none, in either arm. Every agent called its design safe, and every design is safe and buildable.

Under the strict reading, three designs without Petra are called safe and do not pass Petra. The [hand checks](pilot_lift/hand_checks.md) find each one safe under AISC 360-22.

| Design | What Petra says | What the code says |
|---|---|---|
| without_petra/303-003 | UNKNOWN: Petra has no maximum-spacing rule for a seat with one row of bolts | J3.5 allows 8.16 in, and the bolts are 3.5 in apart |
| without_petra/303-006 | FAIL: bolts at 1.08 by the elastic method with e = a | Manual Table 10-9 takes e = a/2 for this conventional tab, and the instantaneous centre gives 0.84. At e = a it gives 0.999 |
| without_petra/303-022 | FAIL: weld at 1.68 and plate base metal at 1.54 by the elastic method | The instantaneous centre with k = 0, Manual Table 8-4's case for a load out of the weld group's plane, gives 0.91. The plate meets tmin, and J2.4 needs no base metal check for fillet welds |

The agents on 303-006 and 303-022 named these Manual methods in their claims. The agent on 303-022 also wrote that a reviewer who requires the elastic method would need about 17.5 in of weld.

### Hand checks and CalculiX

The hand checks covered the seven designs of the protocol's sample: the three above, with_petra/303-003 and 303-006, and without_petra/303-005 and 303-019. None has a real violation. Every Petra number they repeat matches to within 0.001, so the sample has no false PASS. [hand_checks.md](pilot_lift/hand_checks.md) has the calculations, and `python docs/pilot_lift/hand_checks.py` prints them.

`scripts/calculix_check.py`, at commit `308be67` on the CalculiX branch, ran on the four sampled designs its plane model covers. It does not model seats or hangers. Three passed both runs. without_petra/303-019's end plate was flagged in the rupture run: in the model, a bolt hole stretches 0.25 in at 133.8 kip, under the factored load of 139.1 kip. AISC 360-22's formulas put the same plate at 0.960.

To see whether that flag separates the arms, CalculiX also ran on the 12 other final designs it covers, outside the frozen sample. with_petra/303-019 ran at 0.25 in. Its end plate, also 1/4 in A572 Gr 50 with 3/4 in bolts, gets the same flag at the same 133.8 kip. The other 11 ran at the check's screening size of 0.5 in, and none of them has a rupture flag. The double angles of 303-014, in both arms, get yield flags that point to the model. The check's page predicts those for every LRFD design governed by shear yielding.

So the flag does not separate the arms. In both end plates the model's holes stretch 0.25 in at about 16.7 kip per bolt, which is 1.37 d t Fu. The tabs of 303-006 reach 0.25 in at about the same load per bolt, 1.37 and 1.42 d t Fu, but their ASD design strength is half the nominal, so they are not flagged. J3.11a's bearing strength, with deformation at service load considered, is 2.4 d t Fu. So the flag may say more about the model's bearing than about the deck. Either way it is a lead for the deck and the CalculiX check, not for this pilot's grading, which counts AISC 360-22. [calculix_sample.txt](pilot_lift/calculix_sample.txt) and [calculix_rest.txt](pilot_lift/calculix_rest.txt) have the output.

### What the result means for the bet

The rule was fixed before the runs. The agents with Petra produced 10 safe and buildable designs, and the agents without it produced 10. Neither arm called an unsafe or unbuildable design safe. The agents without Petra did as well on both counts. **By the rule, the bet is wrong on this pilot.** Petra did not make these agents' designs safer, because the agents without it made no unsafe design.

Petra changed other things:

- **Lighter designs.** With Petra, 7 of the 10 designs are lighter than the same task's design without it, and the total is 13% less: 154.9 lb against 178.2 lb. The median design is at 0.79 of the loop's reference optimum, against 0.93.
- **A machine-checked verdict on every design.** All 10 designs with Petra pass Petra. Without it, 7 pass. The other 3 need a reviewer to accept, by hand, a check Petra does not make.
- **More time.** The agents with Petra took a median of 21.7 minutes and 26 tool calls, against 11.7 minutes and 16.5. Tokens were about the same.
- **One heavier design.** On 303-022 Petra's elastic weld method made the design with Petra 1.0 lb heavier than the one without it.

The strict reading favours Petra, 10 against 7. That lead measures agreement with Petra. Each of the three gaps is a limit of Petra's, not an unsafe design.

### Why the pilot could not show a safety gain

- The unaided agents knew the methods. All ten connections are standard Manual cases, and the agents used the Manual's own methods, including the instantaneous centre, Table 10-9 and the out-of-plane case of Table 8-4.
- The format is a checklist. The agents without Petra got `reference.md` and `example.petra`, so they knew which quantities a design must state: edge distances, setback, gauge, weld sides. That likely helped them. The protocol gave them these files on purpose, so that both arms wrote the same format.
- The tasks come from Petra's own generator, so they are kinds Petra already covers.
- Every agent ran at effort xhigh.

A test of the bet needs tasks where unaided agents make unsafe designs. Ten tasks of this kind found none.

### Limits

- Ten tasks per arm. These are counts, and they carry no significance.
- One model, at one effort. The same model family wrote Petra's documents and graded the pilot.
- The agent that ran the pilot did the adjudication and the hand checks. The script reruns them, and its two solvers match Manual values.
- The judge checks fit only. The hand checks covered the governing states of seven designs. A false PASS outside those would not be seen.
- The reference optimum is a local optimum of Petra's loop. A ratio under 1 means lighter than that optimum, not lighter than the lightest safe design.

### Changes to the protocol

- The protocol named two verdicts, `real` and `conservative`. without_petra/303-003 needed a third: Petra leaves a check open, and the code check holds. The grading calls it `holds` and counts it as it counts `conservative`.
- CalculiX also ran on the final designs outside the sample. Those results are reported apart and change no grade.

### Open

- The CalculiX rupture flag on the 1/4 in end plates of 303-019, in both arms. The model's holes reach 0.25 in at about 1.4 d t Fu, where J3.11a allows 2.4 d t Fu.
- The 11 designs CalculiX screened at 0.5 in were not rerun at 0.25 in.
- Petra has no maximum-spacing rule for a seat with one row of bolts, so it cannot pass such a seat.
- Petra's elastic method for eccentric bolt and weld groups is already listed in [steel_connections.md](steel_connections.md) §7. In this pilot it kept two safe designs from passing and made one design heavier.
- A task set where unaided agents fail, to test the bet again.
