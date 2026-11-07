# Petra v0 frame

Petra checks claims about physical designs. A verdict is a theorem relative to explicit premises, in the way a Lean proof is relative to its axioms. Untrusted solvers produce certificates. A small trusted kernel checks those certificates with exact rational arithmetic and never trusts a floating-point number.

This file is the shared grounding for every design runner and implementer. It states what done means, the concepts, the first physics domains and the constraints.

## Definition of done

Each item is a check someone can run.

1. `python -m unittest discover -s tests` passes on Python 3.11 with the standard library plus numpy and scipy.
2. `python -m petra check examples/<name>.petra` prints a PASS, a FAIL and an UNKNOWN verdict across the example designs. Each verdict prints its premise footprint.
3. `petra/kernel` imports only the standard library and uses exact rationals and rational intervals. A mutation suite tampers with every certificate type, and the kernel rejects every tampered certificate.
4. Every certificate rule below runs end to end from a `.petra` file through an untrusted solver to the kernel.
5. Registries (the makeable set) are computed from physics plus a short list of constants, not typed in as tables. A consistency checker built on physics relations catches deliberately corrupted records.
6. A coverage generator turns a design into obligations. An obligation with no certificate and no named waiver makes the verdict UNKNOWN and names what is missing.
7. Family certification proves a parametric family over a whole parameter box once. Later queries inside the box reuse the stored certificate. A benchmark compares the cost of reuse with recomputation, and explains the number.
8. A gym-style environment generates tasks, takes a design plus certificates from an agent, and returns a reward computed only by the kernel. A baseline agent solves generated tasks, and its successful family certificates land in the library.

## Concepts

### Premises and the footprint

Every fact a verdict depends on is a premise with one tag:

| Tag | Meaning |
|---|---|
| `proved` | follows from the kernel's definitions and arithmetic |
| `certified` | a certificate the kernel checked in this run |
| `sanctioned` | a value fixed by a named standard or spec, such as a property-class minimum |
| `measured` | a test result with provenance |
| `validated_model` | a model form accepted within a stated validity range, such as small-strain linear elasticity |
| `assumed` | asserted by a named owner, such as the requirement owner's load range |
| `judged` | an engineering judgement by a named person |

The footprint of a verdict is the set of non-`proved` premises it used, like Lean's `#print axioms`. Every premise carries its owner and source.

### Verdicts

- `PASS` carries the scope it holds over (parameter box, load cases, environment class) and the footprint.
- `FAIL` carries a counterexample certificate and the footprint.
- `UNKNOWN` carries the list of open obligations and what each one needs.

A PASS without a scope and footprint must be impossible to construct.

### Claims

A requirement owner states a claim: a quantity of interest, a relation, a bound, and a scope. The owner also signs the input bounds (loads, ambient conditions). The checker never invents an input bound. A missing bound becomes an UNKNOWN obligation.

### The makeable set

Designs may only reference entries in four registries:

- **Materials.** Real alloys and polymers by designation, with the properties their spec guarantees (minimums and ranges).
- **Parts.** Catalogue parts with ratings. Each rating stores its value, its test conditions, the standard it was tested to, and its owner.
- **Processes.** Shape limits, tolerances, and how the process changes material properties (welding lowers strength near the weld).
- **Environments.** Named classes such as ambient temperature ranges and corrosivity.

Where possible a registry entry is computed from physics plus constants rather than stored as a number. For example, a bolt's stress area comes from the thread geometry, and a wire's resistance per metre is its standard's maximum resistance, kept as a resistivity over the cross-section. The consistency checker re-derives every derivable number and flags records that disagree.

Every entry names its source (document, edition, clause or table) and lists its errata. Its version is one more than its errata count, and a footprint names the version of each registry premise. `petra registry recall ID` lists the designs whose verdicts rest on an entry ([registry.md](registry.md)).

Anything outside the makeable set needs its own evidence or gets UNKNOWN.

### Certificate rules

The kernel knows a small set of rules. Each rule checks one certificate kind against equations the kernel builds itself from the design. A solver never supplies the matrices or the model equations.

| Rule | Checks | Used for |
|---|---|---|
| R1 linear feasibility and duality | a static field that satisfies equilibrium exactly and stays inside capacity gives a lower bound on collapse load. A mechanism gives an upper bound | plastic collapse PASS, mechanism FAIL |
| R2 positive definiteness by exact LDLᵀ | if K + λG is positive definite, verified by exact LDLᵀ and Sylvester's law of inertia, there is no instability below λ | global buckling |
| R3 hypercircle (Prager–Synge) | a statically admissible field and a kinematically admissible field bracket the true compliance and bound the force error | elastic stiffness and stress |
| R4 interval enclosure over boxes | an expression's range over a box, with a branch-and-bound partition into cells | closed-form checks and family certificates |
| R5 moment-problem duality | a function that dominates the failure indicator gives a bound on failure probability from range and mean information alone | uncertainty without assumed distributions |
| R6 scenario bound | an exact binomial tail inequality | probability claims from sampled tests |

Underneath all rules sit rational intervals with rigorous bounds for square root and natural log.

### Composition

Components expose ports that carry interval quantities: current, temperature, force, voltage. A connection checks the assume–guarantee contracts on both ends by interval inclusion. For example, a terminal rated to 75 °C caps the temperature a wire may reach at that port.

### Coverage

A rule table maps (materials × environment × energy domains × connections) to obligations. Examples are "two dissimilar metals in a wet environment need a galvanic corrosion check" and "a compression member needs a buckling check". Each obligation is discharged by a certificate or a named waiver. Otherwise the verdict is UNKNOWN.

### Family certification and the library

A family is a model plus a parameter box. Certifying it once stores a certificate keyed by a content hash of the model definition and the box. A query inside the box reuses the stored certificate after a cheap containment check.

### The training loop

A gym-style environment generates tasks from parametric requirements. An agent returns a design plus certificates. The reward comes only from the kernel's verdict. Successful family certificates go into the library.

## First physics domains

1. **Pin-jointed 2D trusses.** Elastic response (R3), plastic collapse (R1), global stability (R2), member flexural buckling to EN 1993-1-1 (R4).
2. **Electrical wire circuits.** Ampacity from a steady heat balance, short-circuit adiabatic heating (the k factor), voltage drop, and terminal and breaker coordination through port contracts. A family certificate over wire sizes and ambient temperatures (R4).
3. **Bolts.** Metric thread stress area computed from geometry, property-class minimum strengths as sanctioned premises, and a tension check (R4).
4. **Uncertain loads.** Load known only by range and mean (R5), and a probability claim from sampled tests (R6).

## Constraints

- Windows 10, Python 3.11.9, with numpy 2.4, scipy 1.17, sympy 1.14 and mpmath 1.3 installed. No pytest, so tests use `unittest`. No Lean toolchain. No network installs.
- `petra/kernel` uses only the standard library (`fractions`, `math`, `dataclasses`, `hashlib`, `json`).
- Keep the trusted kernel small, under about 1,500 lines. Everything outside the kernel is untrusted and may use numpy and scipy.
- Certificates serialise to JSON in a language-neutral format, so a Lean kernel can check the same files later.

## Out of scope for v0

These are next. The interfaces must admit each one as one new certificate rule plus one model definition.

- continuum finite elements with equilibrated stress reconstruction;
- the certified reduced basis method;
- certified neural surrogates;
- a Lean kernel.
