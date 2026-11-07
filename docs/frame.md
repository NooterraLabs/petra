# Petra v0 frame

Petra checks claims about physical designs. A verdict is a theorem relative to explicit premises, the facts it assumes, in the way a Lean proof is relative to its axioms. Untrusted solvers produce certificates, the evidence that a claim holds or fails. A small trusted kernel checks those certificates with exact rational arithmetic and never trusts a floating-point number.

Every agent that proposes an architecture for Petra, and every implementer, starts from this file. It defines the concepts, the first physics domains, what done means, and the constraints.

## Concepts

### Premises and the footprint

Every fact a verdict depends on is a premise. Each premise has one of these tags:

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

### Claims

A requirement owner states a claim: a quantity of interest, a relation, a bound, and a scope. The owner also signs the input bounds, such as loads and ambient conditions. The checker never invents an input bound. A missing bound becomes an UNKNOWN obligation.

### Verdicts

Each kind of verdict carries different data:

- `PASS` carries the scope it holds over (parameter box, load cases, environment class) and the footprint.
- `FAIL` carries a counterexample certificate and the footprint.
- `UNKNOWN` carries its open obligations and what each one needs. An obligation is one check the design owes. It stays open until a certificate or a named waiver discharges it.

It must be impossible to construct a PASS without a scope and a footprint.

### The makeable set

Designs may reference only the entries of four registries:

| Registry | Entries |
|---|---|
| Materials | Real alloys and polymers by designation, with the properties their spec guarantees (minimums and ranges) |
| Parts | Catalogue parts with ratings. Each rating stores its value, its test conditions, the standard it was tested to, and its owner. |
| Processes | Shape limits, tolerances, and how the process changes material properties. Welding, for example, lowers strength near the weld. |
| Environments | Named classes such as ambient temperature ranges and corrosivity |

Where it can, Petra computes a registry entry from physics plus constants instead of storing a number. A bolt's stress area, for example, comes from the thread geometry. A wire's resistance per metre is its standard's maximum resistance, kept as a resistivity over the cross-section. The consistency checker re-derives every derivable number and flags records that disagree.

Every entry names its source (document, edition, clause or table) and lists its errata, the corrections made to it since. An entry's version is one more than its errata count, and a footprint names the version of each registry premise. `petra registry recall ID` lists the designs whose verdicts rest on an entry, as [Registry versions, errata and recall](registry.md) describes.

Anything outside the makeable set needs its own evidence or gets UNKNOWN.

### Certificate rules

The kernel knows six rules, R1 to R6. Each rule checks one kind of certificate against equations that the kernel builds itself from the design. A solver never supplies the matrices or the model equations.

| Rule | Checks | Used for |
|---|---|---|
| R1 linear feasibility and duality | a static field that satisfies equilibrium exactly and stays inside capacity gives a lower bound on collapse load. A mechanism gives an upper bound | plastic collapse PASS, mechanism FAIL |
| R2 positive definiteness by exact LDLᵀ | if K + λG is positive definite, verified by exact LDLᵀ and Sylvester's law of inertia, there is no instability below λ | global buckling |
| R3 hypercircle (Prager and Synge) | a statically admissible field and a kinematically admissible field bracket the true compliance and bound the force error | elastic stiffness and stress |
| R4 interval enclosure over boxes | an expression's range over a box, with a branch-and-bound partition into cells | closed-form checks and family certificates |
| R5 moment-problem duality | a function that dominates the failure indicator gives a bound on failure probability from range and mean information alone | uncertainty without assumed distributions |
| R6 scenario bound | an exact binomial tail inequality | probability claims from sampled tests |

All six rules compute with rational intervals, which have rigorous bounds for square root and natural log.

### Composition

Components expose ports that carry interval quantities: current, temperature, force, voltage, conductor area. Each port has an assume-guarantee contract. At a connection, Petra checks the contracts on both ends by interval inclusion. For example, a terminal rated to 75 °C caps the temperature a wire may reach at that port, and the conductor range of the terminal's clamp bounds the area of the wire it holds.

### Coverage

Coverage decides which obligations a design owes. A rule table maps (materials × environment × energy domains × connections) to obligations. For example, "two dissimilar metals in a wet environment need a galvanic corrosion check", and "a compression member needs a buckling check".

A certificate or a named waiver discharges each obligation. A waiver is a `waive` line in the design that accepts one open obligation and names who answers for it. If an obligation has neither, the verdict is UNKNOWN.

### Family certification and the library

A family is a model plus a parameter box. Certifying a family once stores its certificate in the library, keyed by a content hash of the model definition and the box. A query inside the box reuses the stored certificate after a cheap containment check.

### The training loop

A gym-style environment generates tasks from parametric requirements. An agent returns a design plus certificates. The reward comes only from the kernel's verdict. Successful family certificates go into the library.

## First physics domains

| Domain | Checks |
|---|---|
| Pin-jointed 2D trusses | Elastic response (R4 over R3 force lemmas), plastic collapse of a statically determinate truss (R1), global stability (R2), and member flexural buckling to EN 1993-1-1 (R4). Every load case carries the members' own weight. |
| Electrical wire circuits | Ampacity from a steady heat balance, short-circuit adiabatic heating (the k factor), voltage drop, and terminal and breaker coordination through port contracts, including a conductor that fits its terminal's clamp. A family certificate over wire sizes and ambient temperatures (R4). |
| Bolts | Metric thread stress area computed from geometry, property-class minimum strengths as sanctioned premises, and a tension check (R4). |
| Uncertain loads | Load known only by range and mean (R5), and a probability claim from sampled tests (R6). |

## Definition of done

Each item is a check you can run.

1. `python -m unittest discover -s tests` passes on Python 3.11 with the standard library plus numpy and scipy.
2. `python -m petra check examples/<name>.petra` prints a PASS, a FAIL and an UNKNOWN verdict across the example designs. Each verdict prints its premise footprint.
3. `petra/kernel` imports only the standard library and uses exact rationals and rational intervals. A mutation suite tampers with every certificate type, and the kernel rejects every tampered certificate.
4. Every certificate rule, R1 to R6, runs end to end from a `.petra` file through an untrusted solver to the kernel.
5. Registries, the makeable set, are computed from physics plus a short list of constants, not typed in as tables. A constant may be a limit that a standard specifies, such as IEC 60228's maximum conductor resistance, when the standard guarantees the limit and not the physical property. A consistency checker built on physics relations catches records that were corrupted on purpose.
6. A coverage generator turns a design into obligations. An obligation with no certificate and no named waiver makes the verdict UNKNOWN and names what is missing.
7. Family certification proves a parametric family over a whole parameter box once. Later queries inside the box reuse the stored certificate. A benchmark compares the cost of reuse with recomputation and explains the number.
8. A gym-style environment generates tasks, takes a design plus certificates from an agent, and returns a reward that only the kernel computes. A baseline agent solves generated tasks, and its successful family certificates go into the library.

## Constraints

- The machine runs Windows 10 and Python 3.11.9, with numpy 2.4, scipy 1.17, sympy 1.14 and mpmath 1.3 installed. It has no pytest, so tests use `unittest`. It has no Lean toolchain, and nothing may be installed from the network.
- `petra/kernel` uses only the standard library (`fractions`, `math`, `dataclasses`, `hashlib`, `json`).
- The trusted kernel stays small, under about 1,500 lines. Everything outside the kernel is untrusted and may use numpy and scipy.
- Certificates serialise to JSON in a language-neutral format, so a Lean kernel can check the same files later.

## Out of scope for v0

These come next. The interfaces must admit each one as one new certificate rule plus one model definition.

- continuum finite elements with equilibrated stress reconstruction
- the certified reduced basis method
- certified neural surrogates
- a Lean kernel
