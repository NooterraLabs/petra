# Registry versions, errata and recall

The registry is the makeable set: the constants, materials, parts, processes and environments a design may name. A registry value is a premise, one of the facts a verdict rests on. When a value turns out wrong, Petra has to say which verdicts rested on it. Each registry entry records where it came from and how it has changed, and `petra registry recall` finds the verdicts a correction touches.

## Entries

A registry entry is a constant, a material, a part, a process or an environment. Each entry has a provenance (`petra/registry/model.py`) with three fields:

- `source` names the document, its edition, and the clause or table, such as `IEC 60228:2004 Table 2, class 2 copper conductor 2.5 mm2`. A material's `standard` is its source. An entry with no source cannot be built.
- `errata` lists each correction, oldest first. An `Erratum` gives the day it landed (`YYYY-MM-DD`), what the entry said before, and what it says now and why.
- `version` is one more than the number of errata. Version 1 is the entry as first entered. The version is computed, so it cannot disagree with the history.

A premise key belongs to one entry. `const.cu.rho20` is its own entry, and `cable.cu_pvc.rho20_max` belongs to `cable.cu_pvc` (`Registry.entry_of`). To correct a value that several entries share, such as one `Stated` reused across sizes, add an erratum to every entry the value reaches.

The deck is the makeable set exported as JSON records, written by `petra registry build` in format `petra-deck/1`. It carries one row per entry under `entries`, with the entry's version, source and errata. `petra registry check` reports four provenance faults as relation `entry.provenance`:

- a row with no source
- a malformed or out-of-order erratum
- a version that is not one more than its errata count
- a record whose entry has no row

## Versions in footprints, not in labels

A footprint is the list of premises a verdict rests on. It names each registry premise by its label, such as `reg:cable.cu_pvc.rho20_max`, and gives the entry's version beside it. The JSON footprint has `"version": 2`. In the text footprint, the source ends with `version 2`.

The label does not carry the version. Labels are the kernel's hypothesis names. Certificates, library keys and statement hashes contain them, and the readout parses them. A version in the label would invalidate every certificate on an erratum that only fixes a citation. An erratum that changes a value already changes the statement through the hypothesis range, so the certificate stops matching without any version in the label.

## Intervals

Values stay points unless the entry's own source states a range or a tolerance. An entry opts in with an erratum that says so. One entry has opted in.

`const.steel.density` is now [7851.8, 8004.8] kg/m3. Its source, EN 1991-1-1:2002 Table A.4, gives steel a unit weight of 77.0 to 78.5 kN/m3, which the registry divides by standard gravity, 9.80665 m/s2. The old point, 7850 kg/m3, lay just below that range. When the range was introduced, no example verdict read steel density, so no verdict changed. The truss's self-weight, added in P1, now reads it, and the FAIL in `examples/truss_fail.petra` takes the heavy end.

`cable.cu_pvc.rho20_max` is also an interval, but it is not a tolerance. It spans the per-size values over the catalogue's sizes, so a family over sizes covers each of them.

A registry value may be a specified limit rather than the physics when the standard guarantees the limit and not the property ([plan](plan.md) section 8, item 7, decided 2026-11-06). The cable fix below takes the specified limit, because the standard caps the resistance a conforming conductor may have.

## The first erratum, cable resistance (2026-11-06)

R20 was `const.cu.rho20 / area`, annealed copper of exactly the nominal area. A class 2 conductor may have more resistance than that, so R20 read low, and so did heating and voltage drop. R20 now reads the maximum resistance at 20 degC that IEC 60228:2004 Table 2 allows for class 2 plain copper.

| size | max ohm/km | old ohm/km | old below max |
|---|---|---|---|
| 1.5 mm2 | 12.1 | 11.494 | 5.0 % |
| 2.5 mm2 | 7.41 | 6.897 | 6.9 % |
| 4 mm2 | 4.61 | 4.310 | 6.5 % |
| 6 mm2 | 3.08 | 2.874 | 6.7 % |
| 10 mm2 | 1.83 | 1.724 | 5.8 % |
| 16 mm2 | 1.15 | 1.078 | 6.3 % |

The maximum values in this table were written from memory, not checked against the published text, because the standard is not among `docs/research/sources`. Each value is tagged `judged` and owned by petra-maintainers, and its source says so. Verify each value against IEC 60228:2004 Table 2 before you rely on it.

Each size holds `rho20_max`, the maximum times the nominal area, and R20 is `rho20_max / area`. The series `cable.cu_pvc` holds the span of `rho20_max` over the sizes, [18.15, 18.525] ohm mm2/km. A concrete wire and a family therefore keep the same statement shape, and the library still reuses family certificates. The series and all six sizes carry the erratum and are at version 2. Two deck relations check the new values. `cable.resistance` checks `R20 == rho20_max / area`, and `cable.resistance_allowance` checks that `rho20_max` lies within 10 % above annealed copper's resistivity.

The circuit model reads a wire's properties through its series, so it checks every size at the top of the span, 2.5 mm2's 18.525 ohm mm2/km. That value is exact for 2.5 mm2 and up to 2 % conservative for the other sizes.

No example or fixture changed status.

| design | before | after |
|---|---|---|
| `examples/circuit_pass.petra` | PASS, 55.17 degC, drop 2.97 V | PASS, 56.36 degC, drop 3.19 V |
| `examples/families/cu_pvc_clipped.petra` | UNKNOWN (coverage), hot certified | UNKNOWN (coverage), hot certified |
| `judges/canaries/circuit_16mm2_in_4mm2_terminal.petra` | PASS, 41.17 degC | PASS, 41.26 degC |
| `tests/fixtures/readout/cable_30m_protected.petra` | FAIL, 100.1 degC, drop 9.90 V | FAIL, 106.8 degC, drop 10.64 V |

The family's 13 A box still certifies, but its edge moved from 13.72 A to 13.23 A. The `circuit_pass` ambient envelope now ends at 51.95 degC instead of 53.13 degC.

## Recall

`petra registry recall ID [FILE ...]` lists the designs whose verdicts rest on an entry. ID is an entry, a premise key, a common name or an id prefix such as `const.iec60228`. Each FILE is one of these:

- a `.petra` design, which recall checks now
- a saved `petra check --json` report
- a directory, which recall searches for `.petra` files

With no FILE, recall reads `examples/`.

```text
$ petra registry recall cable.cu_pvc examples judges/canaries tests/fixtures/readout
entry     cable.cu_pvc  version 2  (IEC 60228:2004 class 2 copper conductors; IEC 60227-3:1993 type 60227 IEC 01 PVC insulation)
  erratum 2026-11-06  was R20 = const.cu.rho20 / area, annealed copper of exactly the nominal area
                      now R20 = rho20_max / area with rho20_max in [18.15, 18.525] ohm mm2/km, the span of IEC 60228 Table 2 maximum resistance times nominal area over the catalogue's sizes
PASS      examples/circuit_pass.petra  workshop-lighting-radial
  hot       PASS     reg:cable.cu_pvc.rho20_max (version 2)
  drop      PASS     reg:cable.cu_pvc.rho20_max (version 2)
  coverage  PASS     reg:cable.cu_pvc.rho20_max (version 2)
...
FAIL      tests/fixtures/readout/cable_30m_protected.petra  job3-cable-2-5-30m
  hot       FAIL     reg:cable.cu_pvc.rho20_max (version 2)
  ...
4 of 34 designs rest on cable.cu_pvc
```

Recall marks a saved report that names an older version with `(version 1, now 2: checked before an erratum)`. With `--json`, recall prints the same data as `{"id", "entries", "designs", "checked", "errors"}`. The exit code is 0 when recall read every file. It is 3 when a file could not be read, or when the ID is unknown.

Recall reads footprints only. It finds a design when a verdict depends on the entry's values, not when the design only names the entry. A size such as `cable.cu_pvc_2_5` is not in today's footprints, because the circuit model reads its values through `cable.cu_pvc`, so recall the series. A derived property reaches a footprint through the constants and stated values it is computed from, so recall those.
