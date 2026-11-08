# Electronics DC worst-case deck specification

Written 2026-11-07. This is the specification for Petra's second deck. The deck checks small analog and power circuits at DC. Each part's value is an interval built from its tolerance, its temperature coefficient, and the ambient range. Every check either holds at the worst corner of that box or fails with the corner named.

The code is in `petra/models/electronics/`. `board.py` reads a board, `network.py` writes the physics, and `domain.py` states the checks and the coverage rules. The part data are in `petra/registry/electronics.py`.

## 0. The claim

> For every board in its catalogue, Petra checks every rating that each part holds, over each part's tolerance and temperature coefficient and over the signed supply, load, and ambient ranges. A board that takes a part outside its data reads UNKNOWN, never PASS.

The claim covers steady DC only. Transients, ripple, noise, and a part's drift over its life are out of scope (§9).

## 1. Sources

Every registry value is tagged `judged`. Each value was recalled, not checked against the published text, and its source line says so. Checking them is the first open item in §9.

| Source | What the deck takes from it |
|---|---|
| IEC 60063:2015 | The E24 and E96 preferred values, as 120 registry constants |
| IEC 60062:2016 | The tolerance letter codes F (1 %) and J (5 %) |
| IEC 60115-1 | The 20 degC reference temperature of a resistor's tolerance and temperature coefficient |
| IEC 60115-8 | The 70 degC rated ambient and the 55/155/56 climatic category of chip resistors |
| Yageo RC series datasheet | Four chip resistors: 0603 at 1 % and 5 %, 0805 at 1 %, and 1206 at 1 %. Each has a temperature coefficient, a power rating at 70 degC, a limiting element voltage, and a value range |
| TI LM317 datasheet (SLVS044) | A floating adjustable regulator in TO-220 |
| TI LM1117 datasheet (SNOS412) | Fixed 3.3 V and 5.0 V regulators in SOT-223 |
| MIC5205-ADJ datasheet | A grounded adjustable low-dropout regulator in SOT-23-5 |
| A typical 0603 chip LED datasheet | Red and white LEDs, as a forward-voltage fit with a temperature coefficient |
| IEC 60364-5-51:2005 | The ambient classes behind `indoor_dry` (AA5, 5 to 40 degC) and `outdoor_c3` (AA7, -25 to 55 degC) |

## 2. The board

A design declares one `board` per circuit. `petra new board` writes a template, and `docs/reference.md` lists every line.

| Line | Says | Premise tag |
|---|---|---|
| `supply` | A rail fed from outside the board, with its voltage range and the most current it can deliver | `in:`, signed |
| `regulator` | A linear regulator fed from a rail. Its name is its output rail. An adjustable one names its two feedback resistors | `reg:` for the part |
| `resistor` | A chip resistor whose value is in its part's series and range | `reg:` for the part, `dsg:` for the value's decade |
| `divider` | Two resistors in series from a rail to ground | none |
| `led` | A string of LEDs in series with its current-limit resistor | `reg:` for the part, `dsg:` for the count |
| `sink` | A load on a rail. Each load case signs the current it draws | `in:`, signed |

The design's `environment` gives the ambient range, or a signed `ambient` declaration does. A resistor value outside its part's E-series is refused, and the message names the two nearest values.

## 3. How a value becomes an interval

Each part instance has its own variables for where it sits inside each spread. A variable runs over [-1, 1] for a symmetric spread or [0, 1] for a range read from its low end. Two parts of one type therefore vary independently. The full formulas are in the docstring of `network.py`.

- A resistor is `Rn (1 + tol u) (1 + TCR w E)`. `E` is the part's farthest temperature from 20 degC. Its hottest temperature adds its own heating, from a bound on its dissipation times the thermal resistance its derating line implies. That temperature stops at the upper category temperature.
- A fixed regulator's output lies between its stated minimum and maximum. An adjustable one sets its output through its feedback pair, with the reference anywhere in its range and the adjust or feedback pin current anywhere up to its maximum.
- An LED string draws `(V - n (V0 + TC (Tj - T_ref))) / (R + n Rd)`. `V0`, `Rd`, and `TC` each lie between their registry ends, and the junction runs from the ambient up to the ambient plus the LED's heating at its maximum current.
- A rail's current is the sum of what each element on it draws, by Kirchhoff's current law.

## 4. What each class owes

Coverage demands each mode below of every element whose part holds the rating, whether or not a claim names it. Every supply owes `dc.supply_current`.

| Class | Mode | Holds when |
|---|---|---|
| Resistor | `dc.resistor_power` | P <= P70 min(1, (T_upper - Ta) / (T_upper - T_rated)), the IEC 60115-1 derating line |
| Resistor | `dc.resistor_voltage` | The voltage across it <= its limiting element voltage |
| LED | `dc.led_rating` | I <= IF_max min(1, (T_upper - Ta) / (T_upper - T_knee)), the datasheet derating line |
| Regulator | `dc.regulator_headroom` | Vout + V_dropout,max <= Vin |
| Regulator | `dc.regulator_input` | Vin <= Vin,max. For the LM317, Vin - Vout <= its differential limit |
| Regulator | `dc.regulator_current` | I_out <= I_out,max |
| Regulator | `dc.regulator_min_load` | I_out >= I_out,min. Only the LM317 has a minimum load |
| Regulator | `dc.regulator_thermal` | Ta + theta_JA P <= Tj,max |
| Supply | `dc.supply_current` | The current drawn <= the signed capacity |

Three modes come from claims only, because no part rating bounds them.

| Mode | Claims |
|---|---|
| `dc.rail_voltage` | A supply or regulator output from above or below. This covers the supply range and a feedback network's output |
| `dc.divider_output` | A divider's output from above or below, such as a window an ADC input must stay inside |
| `dc.led_current` | An LED string's current from above or below |

A claim on `power_utilisation` bounds a resistor's power as a fraction of its derated rating. A claim on `junction_temperature` bounds a regulator's junction below its maximum.

`domain.RATINGS` maps each mode to the rating properties it reads. A part that holds any of them owes the mode. `domain.PROPERTIES` sorts every property of every part as a rating, a validity limit, a spread, or a parameter, and `tests/test_electronics.py` fails on a property with no role. The readout lists each mode a board does not owe and says why. A claim-only mode says that only a claim demands it. `dc.regulator_min_load` on a board with no LM317 says that no regulator there states a minimum load.

## 5. Validity: UNKNOWN, never PASS

Validity rows hold the limits past which a part's data say nothing while the part still works ([design.md](design.md), decision 12). The deck has two rows.

- `dc.cold` holds when the ambient is at or above the lowest temperature of every part a statement reads.
- `dc.led_range` holds when every LED a statement reads carries a current inside its forward-voltage fit, from 1 mA up to its maximum current.

A limit past which the part has failed is a mode of its own, not a row. A regulator in dropout fails `dc.regulator_headroom`, so the design fails whatever else holds.

The LED rating check alone skips the top of the fit. Where the fitted current passes the top, the true current does too, because the forward voltage only rises with current. The top is the LED's maximum current, so the failure stands.

A missing input is a gap, not a guess. A design with no ambient, a supply with no capacity, or a sink with no signed current leaves each check that reads it UNKNOWN, and the open item names the input.

## 6. Examples

| File | Verdict | Why |
|---|---|---|
| `examples/electronics/board.petra` | PASS | A sensor board: an LDO, an LED, and an ADC divider whose output window holds at 99 % of its bound |
| `examples/electronics/adjustable.petra` | PASS | An LM317 feeding an adjustable LDO, with both rails claimed |
| `examples/electronics/led_fail.petra` | FAIL | At its worst corner, a 150 ohm 5 % resistor drives a red LED to 25.9 mA against a derated 18.75 mA at 40 degC |
| `examples/electronics/regulator_fail.petra` | FAIL | A 5 V LDO fed from 5 V has no headroom, and a 3.3 V LDO from 12 V reaches 216 degC |
| `examples/electronics/cold_unknown.petra` | UNKNOWN | The LM317's data start at 0 degC, and an outdoor site reaches -25 degC |

Each example re-checks from its certificates alone. `petra check FILE --certs DIR` writes them, and `petra verify DIR/*.json` checks each one with the kernel.

## 7. The gate

`python scripts/electronics_gate.py` generates boards, checks each one, plants faults, and writes [electronics_gate.md](electronics_gate.md). The generator draws six kinds of board at random: a divider, an LED string, a fixed regulator, each adjustable style, and a chain of a regulator, an LED, and a divider. Each claim's bound sits 2 % to 8 % from the deck's own extreme of the quantity, on the passing or the failing side as the generator aims it.

Measured on 2026-11-07, stream seed 1:

| Gate item | Result |
|---|---|
| Decidedness | 1200 of 1200 boards PASS or FAIL. None is UNKNOWN |
| Claims on target | 2200 of 2200 claims land on the side their margin aimed at |
| Makeability | 661 of 661 FAILs carry a witness point |
| Certificates | 120 of 120 sampled boards re-check from their certificates alone, and the kernel accepts every certificate |
| Planted faults | 98 of 98 caught as FAIL, and each one names its mode |

Twelve kinds of planted fault go into boards that pass, one for each mode in §4. Examples are an LED resistor sized for 1.5 times the LED's maximum current, an LDO fed half its dropout above its output, and a divider's 1 % resistors swapped for 5 % ones under a window the 1 % parts meet.

The gate does not show that the registry values match the published datasheets. It also draws only boards inside the deck's validity, by a float estimate of each LED's least current.

## 8. What the kernel needs

Every check is a closed-form inequality over a box, which R4 proves or refutes. The deck needs no new kernel rule.

## 9. Open items

1. Check every `judged` value against its published source, and retag the ones that match.
2. Read atopile designs. The reader waits for atopile, which is not installed here.
3. Write a twin elaborator and a breaker for this deck, as the steel deck has.
4. Add canaries for the absurd-gap judge and mutation tests of the builders.
5. Model a resistor's drift over its life. The registry does not hold load-life or damp-heat stability yet.
6. Model dropout as a function of current. The deck uses each regulator's full-load maximum everywhere, which is conservative.
7. Add more classes: parallel LED strings, resistor networks, Zener references, and transistor switches.
