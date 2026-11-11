# The Petra language

`petra docs reference` prints this page. On the command line, `petra kinds [DOMAIN|KIND]`,
`petra new KIND [--name NAME] [--card]`, and `petra registry list [PREFIX]` print the same tables.

`python -m petra.teach --write` generates this page from the grammars that the lowerers read, the
registry, and the examples. Do not edit it by hand. tests/test_teach.py fails when the page is stale.

## File layout and syntax

A check reads two files. The card, `NAME.card`, holds what is asked: the name, the environment, every
signed bound, the load cases, the claims, and the waivers. The design, `NAME.petra`, holds the answer:
the components. Whoever asks writes the card, and a designer or an agent writes the design. A design
cannot state a load, a claim, a waiver, or a signature, so it cannot change what is asked of it.
`petra check NAME.petra` reads `NAME.card` beside the design, and `--card FILE` names another card.

```
petra 0

card "steel-shear-tab" {
  owner "s.engineer@example.org"
}

load reaction {
  on st1 shear in [0 kip, 45 kip]
  signed "s.engineer@example.org" source "frame analysis rev 2"
}
```

```
petra 0

shear_tab st1 {
  basis lrfd
  ...
}
```

These rules apply to both files.

- The first line is `petra 0`, the language version.
- The rest of a card holds one `card` block and the `param`, `ambient`, `given`, `load`, `tests`,
  `claim`, and `waive` declarations. The rest of a design holds the components and the `param`
  declarations. Each component, load, tests, param, given, and claim name is declared once.
- Inside a block, each line holds one attribute. A comment runs from `#` to the end of the line.
- A name consists of letters, digits, and `_`, and starts with a letter or `_`. A `-` is never part of a
  name. Write `L4x3-1/2x3/8` as `L4x3_1_2x3_8`, and write `WT5x22.5` as `WT5x22_5`.
- A registry id is dotted, as in `steel.A992`. The part after a dot may start with a digit, as in
  `bolt_group.120`. The registry list at the end of this page gives every id and the common names that
  stand for it.
- A number is exact. It is an integer, a decimal, or a fraction such as `3/4`, and it never has an
  exponent. The unit follows the number, as in `0.75 inch`, `45 kip`, and `10mm`. A number with no unit
  is dimensionless.
- A string is written `"..."`. Its only escapes are `\"` and `\\`.
- A bound is a range with its provenance, written
  `in [<lo>, <hi>] [mean <value>] signed "<owner>" source "<source>"`. A measured value has
  `measured` in place of `signed`. Only a card states a bound, and outside a family every bound carries
  a signature. In a family, `param NAME` stands where a bound would.
- `in`, `mean`, `signed`, `measured`, `source`, `param`, and `given` cannot be names inside a line. No
  declared name can be a declaration word.

## Declarations

### card

A card has one `card` block, which names what is asked. `owner` is required. `environment` is optional and names a registry environment from the registry list at the end of this page.

```
card "warren-footbridge-panel" {
  owner "a.reviewer@example.org"
  environment indoor_dry
}
```

### param

`param` declares a family. The design holds for every value in the param's range. A line names the param by writing `param NAME` in place of a value. A param is declared in the card or in the design. A load and the ambient read only the card's params, and `petra check` refuses a load or an ambient that reads one, because nobody signed it: a family goes to `petra certify-family`.

```
param run in [0 m, 20 m]
```

### ambient

`ambient` declares the ambient temperature range, with a signature.

```
ambient in [10 degC, 40 degC] signed "site.manager@example.org" source "site survey 2026-09"
```

### given

`given` states a signed bound under a name. A component's line in the design reads it by writing `given NAME` where the value goes. The design reads every given the card states. A name may be `PART.FIELD`. A part of a deck's type reads only the given named for it: `Fy given tab.Fy` on the part `tab`.

```
given capacity in [36 kN, 40 kN] measured "qa.lab@example.org" source "proof-load report PL-0917"
```

### component

A component is written `KIND NAME { ... }` in the design, with one attribute per line. The Component kinds section lists every kind and its lines.

```
demand hook {
  capacity given capacity
}
```

### load

A `load` block is one load case. Each entry is `on <target> <field> <bound>`. An entry is signed by its own signature or by the signature on the block's last line. A probability claim reads the `mean` of an entry.

```
load lift {
  on hook force in [0 kN, 40 kN] mean 10 kN
  signed "ops.lead@example.org" source "hoist duty log 2025, 14200 lifts"
}
```

### tests

A `tests` block records proof tests. A tested-failure claim reads it.

```
tests proof {
  on hook trials 300 failures 0 at 36 kN
  signed "qa.lab@example.org" source "batch 2026-09 proof tests, independent lots"
}
```

### claim

A claim takes one of three forms:

- A bound on a quantity, with an optional margin and the load cases it holds under. Without `under`, the claim holds under every load case on the component.
- A range-and-mean probability bound.
- A tested-failure probability bound.

The Component kinds section lists the quantities of each kind. A claim with a margin is MARGINAL when it is proved and a certified point lies within the margin of its bound.

```
claim strength: frame.collapse_factor >= 1.5 under crowd
claim stress:   frame.member(diag_ad).stress <= 235 MPa margin 10 MPa under crowd
claim overload: P(hook.utilisation > 1) <= 3/10 under lift
claim tested:   P(fail hook at 36 kN) <= 1/100 confidence 95 % from proof
```

### waive

`waive` accepts an open coverage demand on a component. Only the card can waive. It names the failure mode, who answers for it, and the reason. The Component kinds section lists the failure modes of each domain. Petra reports a waived demand as waived, never as proved.

```
waive bolt.plate_bearing on bracket by "m.engineer@example.org" reason "bearing checked by test PB-3"
```

## Grammar

The grammar below is EBNF, and `NL` is a line end. Component kinds and their lines are not in the grammar. Each domain declares its own, as the Component kinds section shows.

```
card file   = "petra" INT NL { ( card | param | ambient | given | load | tests | claim | waive ) NL } EOF ;
design file = "petra" INT NL { ( param | component ) NL } EOF ;
card      = "card" STRING "{" NL { ( "owner" STRING | "environment" IDENT ) NL } "}" ;
param     = "param" IDENT "in" range ;
ambient   = "ambient" bound ;
given     = "given" name "in" range [ "mean" qty ] [ signature ] ;
name      = IDENT { "." IDENT } ;              PART.FIELD names the bound on one field of one part
component = KIND IDENT "{" NL { attr NL } "}" ;    KIND: an IDENT not in DECLS
attr      = IDENT { arg } ;
arg       = "given" name | "param" IDENT | qty | tuple | ref | STRING | ":" | "--" | "->" ;
tuple     = "(" qty { "," qty } ")" ;
bound     = "in" range [ "mean" qty ] [ signature ] | "param" IDENT ;
signature = ( "signed" | "measured" ) STRING "source" STRING ;
load      = "load" IDENT "{" NL { "on" path IDENT bound NL } [ signature NL ] "}" ;
tests     = "tests" IDENT "{" NL "on" path "trials" INT "failures" INT "at" qty
            [ signature ] NL [ signature NL ] "}" ;
claim     = "claim" IDENT ":" ( qoi rel qty [ "margin" qty ] [ "under" IDENT { "," IDENT } ]
          | "P" "(" qoi ">" qty ")" "<=" NUMBER "under" IDENT
          | "P" "(" "fail" path "at" qty ")" "<=" NUMBER
            "confidence" qty "from" IDENT ) ;
waive     = "waive" ref "on" path "by" STRING "reason" STRING ;
range     = "[" qty "," qty "]" ;
qty       = NUMBER [ unit ] ;     an IDENT or "%" right after a NUMBER is its unit
unit      = IDENT [ "^" INT ] | "%" ;         inch^4: a unit of length to the power 2, 3 or 4, with no space
qoi       = segment { "." segment } ;          last segment is the quantity name
segment   = IDENT [ "(" IDENT ")" ] ;          member(diag_ad) names element diag_ad
path      = IDENT { "." IDENT } ;
ref       = IDENT { "." IDENT } ;   a local name, a domain keyword, a registry id,
                                    a port (w1.b) or a failure-mode id
rel       = "<=" | ">=" ;
```

## Units

A card and a design accept these unit spellings.

| dimension | spellings |
|---|---|
| dimensionless | `%` |
| length | `m`, `mm`, `um`, `cm`, `km`, `inch`, `ft` |
| area | `mm2`, `m2`, `inch2` |
| force | `N`, `kN`, `MN`, `lbf`, `kip`, `kips` |
| stress | `Pa`, `kPa`, `MPa`, `GPa`, `psi`, `ksi` |
| current | `uA`, `mA`, `A`, `kA` |
| voltage | `V`, `kV` |
| resistance | `ohm`, `mohm`, `kohm`, `Mohm` |
| power | `mW`, `W` |
| energy, torque | `J`, `Nm`, `kip_in`, `kip_ft` |
| time | `s`, `ms` |
| temperature | `degC` |
| mass | `g`, `kg` |
| I2t | `A2s` |

A unit of length may be raised to the power 2, 3 or 4: the unit, `^` and the power, with no space, as
in `mm^3` and `inch^4`. Its factor is the unit's own factor to that power, exactly, so `1 inch^4` is
(127/5000)^4 m^4. A power is one of `2`, `3` and `4`, written as that one digit: `inch^1`, `inch^5`,
`inch^04` and `inch^3/2` are refused. Only a unit of length takes a power, so `kN^2` and `mm2^2` are
refused. An area has two spellings with one meaning: `mm^2` is `mm2`, `m^2` is `m2` and `inch^2` is
`inch2`. A section modulus is written in a length to the third power and a moment of inertia in a
length to the fourth. Petra prints such a quantity in `mm^3`, `cm^3`, `m^3` and the like, which it
reads back.

## Exit codes of `petra check`

| status | code |
|---|---|
| PASS | 0 |
| FAIL | 1 |
| UNKNOWN | 2 |
| INPUT_ERROR | 3 |
| INTERNAL_ERROR | 4 |
| MARGINAL | 5 |
| BROKEN_PIPE | 141 |

## Component kinds

A component is written `KIND NAME { ... }`, with one line per attribute. A required line appears at
least once. In a form, `<length>` stands for a length, `given NAME`, or `param NAME`. These
cross-domain modes can be waived on any component: `port.contract`, `corrosion.galvanic`.

### Domain truss

Waivable modes: `truss.compliance`, `truss.elastic_stress`, `truss.global_stability`, `truss.member_buckling`, `truss.plastic_collapse`.

#### truss

A `truss` component is written `truss <name> { ... }`. `petra new truss` prints its example, `examples/truss_pass.petra`.

Load entries and claims on a `truss` component take these forms:

- Load entry: `on <truss>.<node> fx|fy in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <truss>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `collapse_factor`, `stability_factor`, `stress`, `compliance`, `buckling_utilisation`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `node` | `<name> at (<x>, <y>) [support pinned\|roller_x\|roller_y]` | required | length |  | a joint at exact coordinates, one line per node, y pointing up (the members' own weight acts in -y); a support fixes x and y (pinned), y only (roller_x) or x only (roller_y) |
| `member` | `<name>: <node> -- <node> [section <id>] [material <id>]` | required |  | `chs.*`, `steel.*` | a pin-ended bar between two nodes, one line per member; its options override the defaults |
| `material` | `<registry material id>` | optional |  | `steel.*` | the material of every member that names none; it needs fy, E and density and the section's material family |
| `section` | `<registry section id>` | optional |  | `chs.*` | the circular hollow section of every member that names none |

### Domain circuit

Waivable modes: `wire.overload_protection`, `wire.short_circuit`, `wire.steady_temperature`, `wire.voltage_drop`.

#### circuit

A `circuit` component is written `circuit <name> { ... }`. `petra new circuit` prints its example, `examples/circuit_pass.petra`.

Load entries and claims on a `circuit` component take these forms:

- Load entry: `on <circuit>.<consumer> current in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <circuit>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `temperature`, `voltage_drop`, `fault_withstand`, `overload_protection`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `supply` | `<name> voltage <voltage> [fault_current given <name>]` | required | voltage, current |  | the source a radial path starts from; without a signed prospective fault current the short-circuit check is UNKNOWN |
| `consumer` | `<name>` | required |  |  | the load at the end of a path; load cases draw current from it |
| `connect` | `<element>.<port> -> <element>.<port>` | required |  |  | joins a downstream port to the next upstream port (supply out, breaker in and out, wire a and b, terminal wire and out, consumer in); every element lies on one path from a supply to a consumer |
| `breaker` | `<name> part <registry breaker id>` | optional |  | `mcb.*` | the protective device of a path, upstream of its wires; at most one per path |
| `wire` | `<name> cable <registry cable id> length <length> install <registry install id> [area <area> insulation <length>]` | optional | length, area | `cable.*`, `install.*` | a cable run; a size id (cable.cu_pvc_2_5) fixes area and insulation, a series id (cable.cu_pvc) takes them as values or params |
| `terminal` | `<name> part <registry terminal id>` | optional |  | `terminal.*` | a terminal a wire lands on; its temperature and current ratings become port contracts |

### Domain bolt

Waivable modes: `bolt.plate_bearing`, `bolt.separation`, `bolt.tension`.

#### joint

A `joint` component is written `joint <name> { ... }`. `petra new joint` prints its example, `examples/bolt_unknown.petra`.

Load entries and claims on a `joint` component take these forms:

- Load entry: `on <joint> force in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <joint>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolt_tension`, `tension_utilisation`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `bolt` | `<registry bolt id> count <n>` | required | count | `bolt.*` | the bolts, exactly one line: a metric bolt (thread, property class, coating) and how many share the load |
| `plate` | `<registry material id> thickness <length> [process <registry process id>]` | required | length | `aluminium.*`, `steel.*`, `stainless.*`, `process.*` | a clamped plate, one line per plate, at least two; a coating, weld or cut process changes its surface or its strength |
| `torque` | `given <name>` | optional | torque |  | the tightening torque; without it the tension check is UNKNOWN |
| `nut_factor` | `given <name>` | optional | dimensionless |  | the nut factor K of the torque-tension relation, positive; without it the tension check is UNKNOWN |
| `load_share` | `given <name>` | optional | dimensionless |  | the joint load factor Phi, the share of the external force the bolts take, within [0, 1]; without it the tension check is UNKNOWN |

### Domain uncertainty

Waivable modes: `uncertain.range_mean`, `uncertain.tested`.

#### demand

A `demand` component is written `demand <name> { ... }`. `petra new demand` prints its example, `examples/hook_uncertain.petra`.

Load entries and claims on a `demand` component take these forms:

- Load entry: `on <demand> force in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: P(<demand>.utilisation > <value>) <= <p> under <load>`
- Claim: `claim <name>: P(fail <demand> at <level>) <= <p> confidence <value> from <tests>`

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `capacity` | `given <name>` | required | force |  | the capacity the demand is compared with, exactly one line: a positive force range with no mean |

### Domain steel

Waivable modes: `steel.beam_fit`, `steel.bearing`, `steel.block_shear`, `steel.bolt_combined`, `steel.bolt_tension`, `steel.bolts`, `steel.bracket_edge`, `steel.clearance`, `steel.compression`, `steel.cope_buckling`, `steel.ductility`, `steel.edge_max`, `steel.edge_min`, `steel.extended_ductility`, `steel.fatigue_bolt_tension`, `steel.fatigue_bolted`, `steel.fatigue_cope`, `steel.fatigue_detail`, `steel.fatigue_weld`, `steel.fatigue_weld_end`, `steel.fillet_size`, `steel.flange_fit`, `steel.flange_local_bending`, `steel.flexural_rupture`, `steel.flexural_yield`, `steel.hole_use`, `steel.j10_stiffeners`, `steel.joint_type`, `steel.load_path`, `steel.panel_zone`, `steel.plate_buckling`, `steel.prying`, `steel.seat_flexure`, `steel.shear_rupture`, `steel.shear_yield`, `steel.slip`, `steel.spacing_max`, `steel.spacing_min`, `steel.tee_ductility`, `steel.tension_rupture`, `steel.tension_yield`, `steel.web_compression_buckling`, `steel.web_crippling`, `steel.web_fit`, `steel.web_local_yielding`, `steel.web_sidesway_buckling`, `steel.weld`, `steel.weld_base_metal`.

#### shear_tab

A `shear_tab` component is written `shear_tab <name> { ... }`. `petra new shear_tab` prints its example, `examples/steel/shear_tab.petra`.

Load entries and claims on a `shear_tab` component take these forms:

- Load entry: `on <conn> shear|axial|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `beam` | `<W shape> grade <steel grade>` | required |  | `W*`, `steel.*` | the supported beam, a W shape from the shape table |
| `support` | `<W shape> flange\|web grade <steel grade>` | required |  | `W*`, `steel.*` | the supporting member and the face the connection meets: a column flange, or a column or girder web |
| `plate` | `<steel grade> thickness <length>` | required | length | `steel.*` | the connecting plate (a shear tab, end plate, seat plate or bracket plate); a fixed thickness is a stocked one |
| `bolts` | `<bolt group> diameter <length> threads included\|excluded [joint snug\|pretensioned\|slip_critical] [surface class_a\|class_b] [fillers none\|one\|two]` | required | length | `bolt_group.*` | the bolts: a Table J3.2 group (A325 is bolt_group.120, A490 bolt_group.150), an RCSC Table 5.2 diameter, threads in or out of the shear planes (AISC's A325-N is threads included, A325-X threads excluded), the installation (snug unless stated), a slip-critical joint's faying surface, and fillers (none unless stated) |
| `rows` | `<n>` | required | count |  | bolt rows, a whole number |
| `pitch` | `<length>` | required | length |  | spacing of bolt rows (s) |
| `edge_vertical` | `<length>` | required | length |  | vertical edge distance of the end rows (Lev) |
| `plate_edge` | `<length>` | required | length |  | horizontal edge distance on the connecting element (Leh) |
| `bolt_line` | `<length>` | required | length |  | distance a to the bolt line (Manual Part 10), from the weld line at the support face; with more than one column, to the column nearest the support |
| `beam_edge` | `<length>` | required | length |  | horizontal edge distance on the beam web, as detailed; strength checks take it less the 1/4 in underrun (Leh, Manual Part 10) |
| `top` | `<length>` | required | length |  | beam's top to the top bolt row |
| `weld` | `<electrode> size <length> [sides 1\|2]` | required | length | `electrode.*` | the fillet weld: electrode, leg size, and fillets at each joint line, which shear_tab, shear_end_plate, weld_bracket, stiffened_seat state |
| `holes` | `<ply> std\|ovs\|ssl\|lsl\|ssl_parallel\|lsl_parallel [<ply> <type> ...]` | optional |  |  | hole types by ply (Table J3.3), plies plate, beam; a ply it does not name has standard holes |
| `cope` | `top\|both depth <length> length <length> [bottom_depth <length>]` | optional | length |  | a cope at the beam's top flange or both flanges: the (top) cope's depth, its length, and with both a bottom depth where it differs; a coped beam states its setback |
| `eccentricity` | `<length>` | optional | length |  | load's distance from the bolt group's or weld's centroid (e) |
| `setback` | `<length>` | optional | length |  | gap from the support face to the beam end, as detailed; a seat's strength checks add the 1/4 in underrun |
| `form` | `conventional\|extended` | optional |  |  | a single plate's configuration (Manual Part 10); conventional unless stated |
| `columns` | `<n>` | optional | count |  | bolt columns; one unless stated |
| `gauge` | `<length>` | optional | length |  | spacing of bolt columns (g) |
| `deformation` | `considered\|not_considered` | optional |  |  | whether deformation at the bolt holes at service load is a design consideration (Section J3.11a); considered unless stated |
| `weathering` | `no\|yes` | optional |  |  | whether the steel is unpainted weathering steel, whose spacing limits are tighter (Section J3.6); no unless stated |

#### double_angle

A `double_angle` component is written `double_angle <name> { ... }`. `petra new double_angle` prints its example, `examples/steel/double_angle.petra`.

Load entries and claims on a `double_angle` component take these forms:

- Load entry: `on <conn> shear|axial|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `beam` | `<W shape> grade <steel grade>` | required |  | `W*`, `steel.*` | the supported beam, a W shape from the shape table |
| `support` | `<W shape> flange\|web grade <steel grade>` | required |  | `W*`, `steel.*` | the supporting member and the face the connection meets: a column flange, or a column or girder web |
| `angles` | `<L shape> grade <steel grade> outstanding long\|short` | required |  | `L*`, `steel.*` | the pair of connection angles; outstanding names the leg on the support |
| `bolts` | `<bolt group> diameter <length> threads included\|excluded [joint snug\|pretensioned\|slip_critical] [surface class_a\|class_b] [fillers none\|one\|two]` | required | length | `bolt_group.*` | the bolts: a Table J3.2 group (A325 is bolt_group.120, A490 bolt_group.150), an RCSC Table 5.2 diameter, threads in or out of the shear planes (AISC's A325-N is threads included, A325-X threads excluded), the installation (snug unless stated), a slip-critical joint's faying surface, and fillers (none unless stated) |
| `rows` | `<n>` | required | count |  | bolt rows, a whole number |
| `pitch` | `<length>` | required | length |  | spacing of bolt rows (s) |
| `edge_vertical` | `<length>` | required | length |  | vertical edge distance of the end rows (Lev) |
| `beam_edge` | `<length>` | required | length |  | horizontal edge distance on the beam web, as detailed; strength checks take it less the 1/4 in underrun (Leh, Manual Part 10) |
| `top` | `<length>` | required | length |  | beam's top to the top bolt row |
| `beam_gauge` | `<length>` | required | length |  | gauge of the bolts through the beam web (g), from the angles' heel, the back of their outstanding legs, to the bolt line in the legs on the beam web; the toe's edge distance is that leg less this gauge |
| `support_side` | `bolted\|welded` | required |  |  | how the angles, tee or seat meet the support: bolted (with support_gauge) or welded (with support_weld) |
| `holes` | `<ply> std\|ovs\|ssl\|lsl\|ssl_parallel\|lsl_parallel [<ply> <type> ...]` | optional |  |  | hole types by ply (Table J3.3), plies angles, beam, support; a ply it does not name has standard holes |
| `support_gauge` | `<length>` | optional | length |  | gauge of the bolts through the support (g), between the two bolt lines, one in each angle's outstanding leg: twice each leg's gauge from its heel, plus the beam web's thickness |
| `support_weld` | `<electrode> size <length> [sides 1\|2]` | optional | length | `electrode.*` | the weld to the support on a welded support side |
| `cope` | `top\|both depth <length> length <length> [bottom_depth <length>]` | optional | length |  | a cope at the beam's top flange or both flanges: the (top) cope's depth, its length, and with both a bottom depth where it differs; a coped beam states its setback |
| `setback` | `<length>` | optional | length |  | gap from the support face to the beam end, as detailed; a seat's strength checks add the 1/4 in underrun |
| `deformation` | `considered\|not_considered` | optional |  |  | whether deformation at the bolt holes at service load is a design consideration (Section J3.11a); considered unless stated |
| `weathering` | `no\|yes` | optional |  |  | whether the steel is unpainted weathering steel, whose spacing limits are tighter (Section J3.6); no unless stated |

#### single_angle

A `single_angle` component is written `single_angle <name> { ... }`. `petra new single_angle` prints its example, `examples/steel/single_angle.petra`.

Load entries and claims on a `single_angle` component take these forms:

- Load entry: `on <conn> shear|axial|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `beam` | `<W shape> grade <steel grade>` | required |  | `W*`, `steel.*` | the supported beam, a W shape from the shape table |
| `support` | `<W shape> flange\|web grade <steel grade>` | required |  | `W*`, `steel.*` | the supporting member and the face the connection meets: a column flange, or a column or girder web |
| `angle` | `<L shape> grade <steel grade> outstanding long\|short` | required |  | `L*`, `steel.*` | the single angle, or a seat's angle; outstanding names the leg on the support, or the seat's leg under the beam |
| `bolts` | `<bolt group> diameter <length> threads included\|excluded [joint snug\|pretensioned\|slip_critical] [surface class_a\|class_b] [fillers none\|one\|two]` | required | length | `bolt_group.*` | the bolts: a Table J3.2 group (A325 is bolt_group.120, A490 bolt_group.150), an RCSC Table 5.2 diameter, threads in or out of the shear planes (AISC's A325-N is threads included, A325-X threads excluded), the installation (snug unless stated), a slip-critical joint's faying surface, and fillers (none unless stated) |
| `rows` | `<n>` | required | count |  | bolt rows, a whole number |
| `pitch` | `<length>` | required | length |  | spacing of bolt rows (s) |
| `edge_vertical` | `<length>` | required | length |  | vertical edge distance of the end rows (Lev) |
| `beam_edge` | `<length>` | required | length |  | horizontal edge distance on the beam web, as detailed; strength checks take it less the 1/4 in underrun (Leh, Manual Part 10) |
| `top` | `<length>` | required | length |  | beam's top to the top bolt row |
| `beam_gauge` | `<length>` | required | length |  | gauge of the bolts through the beam web (g), from the angle's heel, the back of its outstanding leg, to the bolt line in the leg on the beam web; the toe's edge distance is that leg less this gauge |
| `support_side` | `bolted\|welded` | required |  |  | how the angles, tee or seat meet the support: bolted (with support_gauge) or welded (with support_weld) |
| `holes` | `<ply> std\|ovs\|ssl\|lsl\|ssl_parallel\|lsl_parallel [<ply> <type> ...]` | optional |  |  | hole types by ply (Table J3.3), plies angle, beam, support; a ply it does not name has standard holes |
| `support_gauge` | `<length>` | optional | length |  | gauge of the bolts through the support (g), from the angle's heel, at the face of the beam web, to the bolt line in its outstanding leg |
| `support_weld` | `<electrode> size <length> [sides 1\|2]` | optional | length | `electrode.*` | the weld to the support on a welded support side |
| `cope` | `top\|both depth <length> length <length> [bottom_depth <length>]` | optional | length |  | a cope at the beam's top flange or both flanges: the (top) cope's depth, its length, and with both a bottom depth where it differs; a coped beam states its setback |
| `setback` | `<length>` | optional | length |  | gap from the support face to the beam end, as detailed; a seat's strength checks add the 1/4 in underrun |
| `deformation` | `considered\|not_considered` | optional |  |  | whether deformation at the bolt holes at service load is a design consideration (Section J3.11a); considered unless stated |
| `weathering` | `no\|yes` | optional |  |  | whether the steel is unpainted weathering steel, whose spacing limits are tighter (Section J3.6); no unless stated |

#### shear_tee

A `shear_tee` component is written `shear_tee <name> { ... }`. `petra new shear_tee` prints its example, `examples/steel/shear_tee.petra`.

Load entries and claims on a `shear_tee` component take these forms:

- Load entry: `on <conn> shear|axial|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `beam` | `<W shape> grade <steel grade>` | required |  | `W*`, `steel.*` | the supported beam, a W shape from the shape table |
| `support` | `<W shape> flange\|web grade <steel grade>` | required |  | `W*`, `steel.*` | the supporting member and the face the connection meets: a column flange, or a column or girder web |
| `tee` | `<WT shape> grade <steel grade>` | required |  | `WT*`, `steel.*` | the tee, cut from a W shape in the shape table (WT9x25 from W18x50) |
| `bolts` | `<bolt group> diameter <length> threads included\|excluded [joint snug\|pretensioned\|slip_critical] [surface class_a\|class_b] [fillers none\|one\|two]` | required | length | `bolt_group.*` | the bolts: a Table J3.2 group (A325 is bolt_group.120, A490 bolt_group.150), an RCSC Table 5.2 diameter, threads in or out of the shear planes (AISC's A325-N is threads included, A325-X threads excluded), the installation (snug unless stated), a slip-critical joint's faying surface, and fillers (none unless stated) |
| `rows` | `<n>` | required | count |  | bolt rows, a whole number |
| `pitch` | `<length>` | required | length |  | spacing of bolt rows (s) |
| `edge_vertical` | `<length>` | required | length |  | vertical edge distance of the end rows (Lev) |
| `bolt_line` | `<length>` | required | length |  | distance a to the bolt line (Manual Part 10), measured along the stem from the back of the tee flange, at the support face |
| `beam_edge` | `<length>` | required | length |  | horizontal edge distance on the beam web, as detailed; strength checks take it less the 1/4 in underrun (Leh, Manual Part 10) |
| `top` | `<length>` | required | length |  | beam's top to the top bolt row |
| `support_side` | `bolted\|welded` | required |  |  | how the angles, tee or seat meet the support: bolted (with support_gauge) or welded (with support_weld) |
| `holes` | `<ply> std\|ovs\|ssl\|lsl\|ssl_parallel\|lsl_parallel [<ply> <type> ...]` | optional |  |  | hole types by ply (Table J3.3), plies stem, flange, beam, support; a ply it does not name has standard holes |
| `support_gauge` | `<length>` | optional | length |  | gauge of the bolts through the support (g), between the two bolt lines across the tee flange, one each side of the stem |
| `support_weld` | `<electrode> size <length> [sides 1\|2]` | optional | length | `electrode.*` | the weld to the support on a welded support side |
| `cope` | `top\|both depth <length> length <length> [bottom_depth <length>]` | optional | length |  | a cope at the beam's top flange or both flanges: the (top) cope's depth, its length, and with both a bottom depth where it differs; a coped beam states its setback |
| `setback` | `<length>` | optional | length |  | gap from the support face to the beam end, as detailed; a seat's strength checks add the 1/4 in underrun |
| `eccentricity` | `<length>` | optional | length |  | load's distance from the bolt group's or weld's centroid (e) |
| `deformation` | `considered\|not_considered` | optional |  |  | whether deformation at the bolt holes at service load is a design consideration (Section J3.11a); considered unless stated |
| `weathering` | `no\|yes` | optional |  |  | whether the steel is unpainted weathering steel, whose spacing limits are tighter (Section J3.6); no unless stated |

#### shear_end_plate

A `shear_end_plate` component is written `shear_end_plate <name> { ... }`. `petra new shear_end_plate` prints its example, `examples/steel/shear_end_plate.petra`.

Load entries and claims on a `shear_end_plate` component take these forms:

- Load entry: `on <conn> shear|axial|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `beam` | `<W shape> grade <steel grade>` | required |  | `W*`, `steel.*` | the supported beam, a W shape from the shape table |
| `support` | `<W shape> flange\|web grade <steel grade>` | required |  | `W*`, `steel.*` | the supporting member and the face the connection meets: a column flange, or a column or girder web |
| `plate` | `<steel grade> thickness <length>` | required | length | `steel.*` | the connecting plate (a shear tab, end plate, seat plate or bracket plate); a fixed thickness is a stocked one |
| `plate_width` | `<length>` | required | length |  | an end plate's width |
| `bolts` | `<bolt group> diameter <length> threads included\|excluded [joint snug\|pretensioned\|slip_critical] [surface class_a\|class_b] [fillers none\|one\|two]` | required | length | `bolt_group.*` | the bolts: a Table J3.2 group (A325 is bolt_group.120, A490 bolt_group.150), an RCSC Table 5.2 diameter, threads in or out of the shear planes (AISC's A325-N is threads included, A325-X threads excluded), the installation (snug unless stated), a slip-critical joint's faying surface, and fillers (none unless stated) |
| `rows` | `<n>` | required | count |  | bolt rows, a whole number |
| `pitch` | `<length>` | required | length |  | spacing of bolt rows (s) |
| `edge_vertical` | `<length>` | required | length |  | vertical edge distance of the end rows (Lev) |
| `support_gauge` | `<length>` | required | length |  | gauge of the bolts through the support (g), between the two bolt lines across the end plate, one each side of the beam web |
| `weld` | `<electrode> size <length> [sides 1\|2]` | required | length | `electrode.*` | the fillet weld: electrode, leg size, and fillets at each joint line, which shear_tab, shear_end_plate, weld_bracket, stiffened_seat state |
| `holes` | `<ply> std\|ovs\|ssl\|lsl\|ssl_parallel\|lsl_parallel [<ply> <type> ...]` | optional |  |  | hole types by ply (Table J3.3), plies plate, support; a ply it does not name has standard holes |
| `cope` | `top\|both depth <length> length <length> [bottom_depth <length>]` | optional | length |  | a cope at the beam's top flange or both flanges: the (top) cope's depth, its length, and with both a bottom depth where it differs; a coped beam states its setback |
| `setback` | `<length>` | optional | length |  | gap from the support face to the beam end, as detailed; a seat's strength checks add the 1/4 in underrun |
| `deformation` | `considered\|not_considered` | optional |  |  | whether deformation at the bolt holes at service load is a design consideration (Section J3.11a); considered unless stated |
| `weathering` | `no\|yes` | optional |  |  | whether the steel is unpainted weathering steel, whose spacing limits are tighter (Section J3.6); no unless stated |

#### seated

A `seated` component is written `seated <name> { ... }`. `petra new seated` prints its example, `examples/steel/seated.petra`.

Load entries and claims on a `seated` component take these forms:

- Load entry: `on <conn> shear|axial|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `beam` | `<W shape> grade <steel grade>` | required |  | `W*`, `steel.*` | the supported beam, a W shape from the shape table |
| `support` | `<W shape> flange\|web grade <steel grade>` | required |  | `W*`, `steel.*` | the supporting member and the face the connection meets: a column flange, or a column or girder web |
| `angle` | `<L shape> grade <steel grade> outstanding long\|short` | required |  | `L*`, `steel.*` | the single angle, or a seat's angle; outstanding names the leg on the support, or the seat's leg under the beam |
| `seat_length` | `<length>` | required | length |  | a seat angle's length along the beam's width |
| `support_side` | `bolted\|welded` | required |  |  | how the angles, tee or seat meet the support: bolted (with support_gauge) or welded (with support_weld) |
| `top_angle` | `<L shape> grade <steel grade> outstanding long\|short` | required |  | `L*`, `steel.*` | a seat's top angle, which holds the beam's top flange in place |
| `bolts` | `<bolt group> diameter <length> threads included\|excluded [joint snug\|pretensioned\|slip_critical] [surface class_a\|class_b] [fillers none\|one\|two]` | optional | length | `bolt_group.*` | the bolts: a Table J3.2 group (A325 is bolt_group.120, A490 bolt_group.150), an RCSC Table 5.2 diameter, threads in or out of the shear planes (AISC's A325-N is threads included, A325-X threads excluded), the installation (snug unless stated), a slip-critical joint's faying surface, and fillers (none unless stated) |
| `holes` | `<ply> std\|ovs\|ssl\|lsl\|ssl_parallel\|lsl_parallel [<ply> <type> ...]` | optional |  |  | hole types by ply (Table J3.3), plies angle, support; a ply it does not name has standard holes |
| `rows` | `<n>` | optional | count |  | bolt rows, a whole number |
| `pitch` | `<length>` | optional | length |  | spacing of bolt rows (s) |
| `edge_vertical` | `<length>` | optional | length |  | vertical edge distance of the end rows (Lev) |
| `support_gauge` | `<length>` | optional | length |  | gauge of the bolts through the support (g), between the two bolt lines across the seat angle's vertical leg |
| `setback` | `<length>` | optional | length |  | gap from the support face to the beam end, as detailed; a seat's strength checks add the 1/4 in underrun |
| `support_weld` | `<electrode> size <length> [sides 1\|2]` | optional | length | `electrode.*` | the weld to the support on a welded support side |
| `deformation` | `considered\|not_considered` | optional |  |  | whether deformation at the bolt holes at service load is a design consideration (Section J3.11a); considered unless stated |
| `weathering` | `no\|yes` | optional |  |  | whether the steel is unpainted weathering steel, whose spacing limits are tighter (Section J3.6); no unless stated |

#### stiffened_seat

A `stiffened_seat` component is written `stiffened_seat <name> { ... }`. `petra new stiffened_seat` prints its example, `examples/steel/stiffened_seat.petra`.

Load entries and claims on a `stiffened_seat` component take these forms:

- Load entry: `on <conn> shear|axial|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `beam` | `<W shape> grade <steel grade>` | required |  | `W*`, `steel.*` | the supported beam, a W shape from the shape table |
| `support` | `<W shape> flange\|web grade <steel grade>` | required |  | `W*`, `steel.*` | the supporting member and the face the connection meets: a column flange, or a column or girder web |
| `plate` | `<steel grade> thickness <length>` | required | length | `steel.*` | the connecting plate (a shear tab, end plate, seat plate or bracket plate); a fixed thickness is a stocked one |
| `stiffener` | `<steel grade> thickness <length>` | required | length | `steel.*` | a stiffened seat's stiffener plate |
| `stiffener_width` | `<length>` | required | length |  | width of a seat stiffener (W, Manual Table 10-8) |
| `stiffener_length` | `<length>` | required | length |  | length of a seat stiffener and its welds (l) |
| `weld` | `<electrode> size <length> [sides 1\|2]` | required | length | `electrode.*` | the fillet weld: electrode, leg size, and fillets at each joint line, which shear_tab, shear_end_plate, weld_bracket, stiffened_seat state |
| `top_angle` | `<L shape> grade <steel grade> outstanding long\|short` | required |  | `L*`, `steel.*` | a seat's top angle, which holds the beam's top flange in place |
| `setback` | `<length>` | optional | length |  | gap from the support face to the beam end, as detailed; a seat's strength checks add the 1/4 in underrun |

#### flange_force

A `flange_force` component is written `flange_force <name> { ... }`. `petra new flange_force` prints its example, `examples/steel/flange_force.petra`.

Load entries and claims on a `flange_force` component take these forms:

- Load entry: `on <conn> force|panel_shear|axial|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `member` | `<W shape> grade <steel grade>` | required |  | `W*`, `steel.*` | the member the concentrated force acts on |
| `bearing_length` | `<length>` | required | length |  | length of bearing (lb, J10) |
| `location` | `interior\|end` | required |  |  | where the force acts: away from the member's ends, or near one (with distance) |
| `force_kind` | `compressive\|tensile` | required |  |  | the sense of the concentrated force |
| `distance` | `<length>` | optional | length |  | from the member end to a concentrated force (J10) |
| `end_twist` | `restrained\|free` | optional |  |  | whether the member end near the force is framed or otherwise restrained against twisting about its longitudinal axis, or free; a free end needs a pair of full-depth stiffeners (Section J10.7) |
| `pair` | `single\|double` | optional |  |  | one force, or a pair of compressive forces on opposite flanges at one section (Section J10.5); single unless stated |
| `flange_restrained` | `yes\|no` | optional |  |  | whether the loaded flange is restrained against rotation, which web sidesway buckling (Section J10.4) reads |
| `unbraced_length` | `<length>` | optional | length |  | J10.4's laterally unbraced length (Lb) |
| `moment_at_force` | `below_yield\|at_yield` | optional |  |  | whether the member's moment at the force is below or at yield, which sets J10.4's Cr |

#### bolt_bracket

A `bolt_bracket` component is written `bolt_bracket <name> { ... }`. `petra new bolt_bracket` prints its example, `examples/steel/bolt_bracket.petra`.

Load entries and claims on a `bolt_bracket` component take these forms:

- Load entry: `on <conn> shear|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `plate` | `<steel grade> thickness <length>` | required | length | `steel.*` | the connecting plate (a shear tab, end plate, seat plate or bracket plate); a fixed thickness is a stocked one |
| `support` | `<W shape> flange\|web grade <steel grade>` | required |  | `W*`, `steel.*` | the supporting member and the face the connection meets: a column flange, or a column or girder web |
| `bolts` | `<bolt group> diameter <length> threads included\|excluded [joint snug\|pretensioned\|slip_critical] [surface class_a\|class_b] [fillers none\|one\|two]` | required | length | `bolt_group.*` | the bolts: a Table J3.2 group (A325 is bolt_group.120, A490 bolt_group.150), an RCSC Table 5.2 diameter, threads in or out of the shear planes (AISC's A325-N is threads included, A325-X threads excluded), the installation (snug unless stated), a slip-critical joint's faying surface, and fillers (none unless stated) |
| `rows` | `<n>` | required | count |  | bolt rows, a whole number |
| `columns` | `<n>` | required | count |  | bolt columns; one unless stated |
| `pitch` | `<length>` | required | length |  | spacing of bolt rows (s) |
| `gauge` | `<length>` | required | length |  | spacing of bolt columns (g) |
| `eccentricity` | `<length>` | required | length |  | load's distance from the bolt group's or weld's centroid (e) |
| `edge_vertical` | `<length>` | required | length |  | vertical edge distance of the end rows (Lev) |
| `plate_edge` | `<length>` | required | length |  | horizontal edge distance on the connecting element (Leh) |
| `holes` | `<ply> std\|ovs\|ssl\|lsl\|ssl_parallel\|lsl_parallel [<ply> <type> ...]` | optional |  |  | hole types by ply (Table J3.3), plies plate, support; a ply it does not name has standard holes |
| `deformation` | `considered\|not_considered` | optional |  |  | whether deformation at the bolt holes at service load is a design consideration (Section J3.11a); considered unless stated |
| `weathering` | `no\|yes` | optional |  |  | whether the steel is unpainted weathering steel, whose spacing limits are tighter (Section J3.6); no unless stated |
| `free_edge` | `<length>` | optional | length |  | a shaped bracket's free edge, projected (b) |

#### weld_bracket

A `weld_bracket` component is written `weld_bracket <name> { ... }`. `petra new weld_bracket` prints its example, `examples/steel/weld_bracket.petra`.

Load entries and claims on a `weld_bracket` component take these forms:

- Load entry: `on <conn> shear|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `plate` | `<steel grade> thickness <length>` | required | length | `steel.*` | the connecting plate (a shear tab, end plate, seat plate or bracket plate); a fixed thickness is a stocked one |
| `support` | `<W shape> flange\|web grade <steel grade>` | required |  | `W*`, `steel.*` | the supporting member and the face the connection meets: a column flange, or a column or girder web |
| `weld` | `<electrode> size <length> [sides 1\|2]` | required | length | `electrode.*` | the fillet weld: electrode, leg size, and fillets at each joint line, which shear_tab, shear_end_plate, weld_bracket, stiffened_seat state |
| `weld_length` | `<length>` | required | length |  | length of a bracket's weld line (L) |
| `eccentricity` | `<length>` | required | length |  | load's distance from the bolt group's or weld's centroid (e) |
| `weld_return` | `<length>` | optional | length |  | a bracket weld's returns (kl): a C-shaped weld around a plate lapped on the support face |
| `free_edge` | `<length>` | optional | length |  | a shaped bracket's free edge, projected (b) |

#### hanger

A `hanger` component is written `hanger <name> { ... }`. `petra new hanger` prints its example, `examples/steel/hanger.petra`.

Load entries and claims on a `hanger` component take these forms:

- Load entry: `on <conn> tension|shear|cycles in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <conn>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `bolts`, `bolt_tension`, `bolt_combined`, `slip`, `shear_yield`, `shear_rupture`, `block_shear`, `tension_yield`, `tension_rupture`, `flexural_yield`, `flexural_rupture`, `weld`, `weld_base_metal`, `bearing`, `web_local_yielding`, `web_crippling`, `flange_local_bending`, `web_sidesway_buckling`, `web_compression_buckling`, `panel_zone`, `seat_flexure`, `prying`, `spacing_min`, `edge_min`, `spacing_max`, `edge_max`, `fillet_size`, `hole_use`, `joint_type`, `clearance`, `beam_fit`, `flange_fit`, `web_fit`, `compression`, `cope_buckling`, `plate_buckling`, `ductility`, `tee_ductility`, `bracket_edge`, `extended_ductility`, `fatigue_bolted`, `fatigue_bolt_tension`, `fatigue_weld`, `fatigue_weld_end`, `fatigue_cope`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `basis` | `lrfd\|asd` | required |  |  | the design basis: lrfd (factored loads against phi Rn) or asd (service loads against Rn / Omega) |
| `tee` | `<WT shape> grade <steel grade>` | required |  | `WT*`, `steel.*` | the tee, cut from a W shape in the shape table (WT9x25 from W18x50) |
| `support` | `<W shape> flange\|web grade <steel grade>` | required |  | `W*`, `steel.*` | the supporting member and the face the connection meets: a column flange, or a column or girder web |
| `bolts` | `<bolt group> diameter <length> threads included\|excluded [joint snug\|pretensioned\|slip_critical] [surface class_a\|class_b] [fillers none\|one\|two]` | required | length | `bolt_group.*` | the bolts: a Table J3.2 group (A325 is bolt_group.120, A490 bolt_group.150), an RCSC Table 5.2 diameter, threads in or out of the shear planes (AISC's A325-N is threads included, A325-X threads excluded), the installation (snug unless stated), a slip-critical joint's faying surface, and fillers (none unless stated) |
| `rows` | `<n>` | required | count |  | bolt rows, a whole number |
| `pitch` | `<length>` | required | length |  | spacing of bolt rows (s) |
| `tee_gauge` | `<length>` | required | length |  | gauge across a hanger tee's flange (g) |
| `edge_vertical` | `<length>` | required | length |  | vertical edge distance of the end rows (Lev) |
| `holes` | `<ply> std\|ovs\|ssl\|lsl\|ssl_parallel\|lsl_parallel [<ply> <type> ...]` | optional |  |  | hole types by ply (Table J3.3), plies flange, support; a ply it does not name has standard holes |
| `weathering` | `no\|yes` | optional |  |  | whether the steel is unpainted weathering steel, whose spacing limits are tighter (Section J3.6); no unless stated |

### Domain electronics

Waivable modes: `dc.divider_output`, `dc.led_current`, `dc.led_rating`, `dc.rail_voltage`, `dc.regulator_current`, `dc.regulator_headroom`, `dc.regulator_input`, `dc.regulator_min_load`, `dc.regulator_thermal`, `dc.resistor_power`, `dc.resistor_voltage`, `dc.supply_current`.

#### board

A `board` component is written `board <name> { ... }`. `petra new board` prints its example, `examples/electronics/board.petra`.

Load entries and claims on a `board` component take these forms:

- Load entry: `on <board>.<sink> current in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <board>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `voltage`, `output`, `current`, `power_utilisation`, `junction_temperature`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `supply` | `<name> voltage given <name> [capacity given <name>]` | required | voltage, current |  | a rail fed from outside the board, named by the supply; capacity is the most current it can deliver, and without it the supply-current check is UNKNOWN |
| `regulator` | `<name> part <registry regulator id> from <rail> [top <resistor> bottom <resistor>]` | optional |  | `reg.*` | a linear regulator fed from a rail; its name is its output rail; an adjustable one names its feedback resistors, top from the output and bottom to ground |
| `resistor` | `<name> part <registry resistor id> value <resistance> [from <rail>]` | optional | resistance | `res.*` | a chip resistor whose value is in its part's E24 or E96 series; with from, it runs from that rail to ground, and otherwise one divider, LED or regulator names it |
| `divider` | `<name> from <rail> top <resistor> bottom <resistor>` | optional |  |  | two resistors in series from a rail to ground; its output is the node between them |
| `led` | `<name> part <registry led id> from <rail> resistor <resistor> [count <n>]` | optional |  | `led.*` | a string of count LEDs (one by default) in series with its current-limit resistor, from a rail to ground |
| `sink` | `<name> from <rail>` | optional |  |  | a load on a rail; each load case signs the current it draws |

### Domain parts

Waivable modes: `fit.connected`, `fit.driver`, `fit.fastener`, `fit.gap`, `fit.grip`, `fit.hole`, `fit.insert`, `fit.press`, `fit.seat`, `insert.boss_wall`, `insert.depth`, `insert.hole_size`, `mill.min_feature`, `mill.reach`, `part.temperature`, `parts.cg`, `parts.mass`, `powder.escape`, `powder.min_feature`, `powder.volume`, `print.bridge`, `print.min_feature`, `print.min_hole`, `print.overhang`, `print.support_access`, `print.thin_wall`, `print.volume`, `sheet.bed`, `sheet.min_web`, `sheet.prism`.

#### part

A `part` component is written `part <name> { ... }`. `petra new part` prints its example, `examples/parts/part.petra`.

Load entries and claims on a `part` component take these forms:

- Load entry: `on <part>  in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <part>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `mass`, `cg_x`, `cg_y`, `cg_z`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `mesh` | `"<file>" sha256 "<hex>" units <mm\|inch>` | required |  |  | the part's closed surface, an STL or 3MF file, pinned by its hash; coordinates are read exactly |
| `material` | `<registry material id>` | required |  | `polymer.*`, `aluminium.*`, `steel.*`, `stainless.*` | what the part is made of |
| `process` | `<registry process id>` | optional |  | `process.print.*`, `process.powder.*`, `process.sheet.*`, `process.mill.*` | how the part is made: its tolerance, hole shrink and build volume; a bought part names none |
| `finish` | `<registry coating id>` | optional |  | `process.anodize_ii*`, `process.powder_coat*` | a coating whose buildup every fit rule adds to the part's surfaces |
| `tolerance` | `given <name>` | optional | length |  | the profile tolerance, replacing the process preset's |
| `hole_shrink` | `given <name>` | optional | length |  | how much smaller modelled holes come out, diametral |
| `fill` | `given <name>` | optional | dimensionless |  | the part's mass over a solid part's, for printed infill |
| `mass` | `given <name>` | optional | mass |  | a bought part's mass; without it the mass is volume times density |
| `heat` | `given <name>` | optional | temperature |  | how far a local heat source lifts the part above ambient |
| `cg` | `(<x>, <y>, <z>)` | optional | length |  | the centre of mass of a bought or infilled part, in its own frame |
| `hole` | `<id> at (<x>, <y>, <z>) along <top\|bottom\|left\|right\|front\|back> diameter <length> [depth <length>] [clear\|tap\|form\|press\|insert <registry insert id>] [countersink <length>]` | optional | length | `insert.*` | a hole and what it is for; through the part when no depth is given |

#### assembly

A `assembly` component is written `assembly <name> { ... }`. `petra new assembly` prints its example, `examples/parts/assembly.petra`.

Load entries and claims on a `assembly` component take these forms:

- Load entry: `on <assembly>  in [<lo>, <hi>] [mean <value>]`
- Claim: `claim <name>: <assembly>.<qoi> <=|>= <value> [margin <value>] [under <load>, ...]`

In a claim, `<qoi>` is one of `mass`, `cg_x`, `cg_y`, `cg_z`.

| line | form | needed | unit | ids | meaning |
|---|---|---|---|---|---|
| `place` | `<part> at (<x>, <y>, <z>) facing <top\|bottom\|left\|right\|front\|back> <top\|bottom\|left\|right\|front\|back>` | required | length |  | puts a part at a point, its top and front along the two axes; the first is the base |
| `insert` | `<part> along <top\|bottom\|left\|right\|front\|back> from <length>` | optional | length |  | the part arrives at its place moving along the axis over the length; every part but the base has one |
| `fasten` | `<id> <registry screw id> through <part>.<hole> [<part>.<hole> ...] into <part>.<hole>` | optional |  | `screw.*` | a screw through clear holes, head side first, into the hole its thread enters |
| `gap` | `<part> <part> [<length>]` | optional | length |  | two parts that keep apart beyond their tolerances |
| `press` | `<id> <part> into <part>.<hole> diameter <length> interference <length> to <length>` | optional | length |  | a pin part pressed into a press hole, with its diametral interference range |

## Registry

The list below is the output of `petra registry list`. It gives every id a design can name, then the
stocked plate thicknesses. A fixed plate thickness is one of the stocked thicknesses.

The listed shapes are those of the shipped shape table. When `PETRA_SHAPES_XLSX` is set to the AISC
Shapes Database v16.0 workbook, every W and L row in that workbook is an id. A WT is cut from its W,
as WT9x25 is cut from W18x50.

Where a steel connection names a grade, a bolt group, or an electrode, a common name can stand for
the id. A common name matches in any letter case, and `Gr` or `Grade` in it is optional. A common
name is written as one name with `_` between its words, or quoted. For example, `A325` is
`bolt_group.120`, and `A572_50`, `A572_Gr_50`, and `"A572 Gr 50"` are all `steel.A572_50`. A
footprint names the id, not the common name.

AISC's thread suffixes are not part of a name. The `bolts` line states the thread condition instead.
On that line, `-N` is `threads included` and `-X` is `threads excluded`, so A325-N is `bolts bolt_group.120 ... threads included`.

```
steel.S355                  steel: EN 10025-2:2019
aluminium.6061_T6           aluminium: EN 573-3 EN AW-6061, temper T6
copper.cu_etp               copper: IEC 60028:1925
pvc.general_70C             pvc: IEC 60227-1, insulation compound PVC/C
steel.bolt_qt               steel: ISO 898-1:2013, quenched and tempered steel
stainless.A4                stainless: ISO 3506-1:2020, austenitic grade A4
zinc.electroplate           zinc: ISO 2081:2008, electroplated zinc on iron or steel
steel.A992                  steel: ASTM A992 (W shapes); also A992
steel.A36                   steel: ASTM A36 (plates, angles, shapes); also A36
steel.A572_50               steel: ASTM A572 Grade 50 (plates, shapes); also A572 Grade 50
bolt_group.120              bolt: ASTM F3125 Grades A325 and F1852 (Group 120); AISC's -N and -X are `threads included` and `threads excluded`; also A325, F1852
bolt_group.144              bolt: ASTM F3148 Grade 144 (Group 144); AISC's -N and -X are `threads included` and `threads excluded`; also F3148
bolt_group.150              bolt: ASTM F3125 Grades A490 and F2280 (Group 150); AISC's -N and -X are `threads included` and `threads excluded`; also A490, F2280
bolt_group.200              bolt: ASTM F3043 and F3111 (Group 200); AISC's -N and -X are `threads included` and `threads excluded`; also F3043, F3111
bolt_group.A307             bolt: ASTM A307 Grade A; AISC's -N and -X are `threads included` and `threads excluded`; also A307
electrode.E70               electrode: AWS A5.1/A5.5 E70XX; also E70, E70XX
electrode.E80               electrode: AWS A5.1/A5.5 E80XX; also E80, E80XX
res.0603_1pct               resistor: Yageo RC series thick-film chip resistor datasheet: 0603 thick-film chip resistor, 1 % (E96); recalled and not checked against the published text
res.0603_5pct               resistor: Yageo RC series thick-film chip resistor datasheet: 0603 thick-film chip resistor, 5 % (E24); recalled and not checked against the published text
res.0805_1pct               resistor: Yageo RC series thick-film chip resistor datasheet: 0805 thick-film chip resistor, 1 % (E96); recalled and not checked against the published text
res.1206_1pct               resistor: Yageo RC series thick-film chip resistor datasheet: 1206 thick-film chip resistor, 1 % (E96); recalled and not checked against the published text
led.red_0603                led: typical 0603 chip LED datasheet: 0603 red AlInGaP LED; recalled and not checked against the published text
led.white_0603              led: typical 0603 chip LED datasheet: 0603 white InGaN LED; recalled and not checked against the published text
reg.lm317_to220             regulator_floating: TI LM317 datasheet (SLVS044), electrical characteristics: LM317 adjustable regulator, TO-220; recalled and not checked against the published text
reg.ldo1117_3v3_sot223      regulator_fixed: TI LM1117 datasheet (SNOS412), electrical characteristics: 1117 fixed 3.3 V regulator, SOT-223; recalled and not checked against the published text
reg.ldo1117_5v0_sot223      regulator_fixed: TI LM1117 datasheet (SNOS412), electrical characteristics: 1117 fixed 5.0 V regulator, SOT-223; recalled and not checked against the published text
reg.ldo_adj_sot23_5         regulator_grounded: typical 150 mA adjustable low-dropout regulator in SOT-23-5 (MIC5205-ADJ datasheet): adjustable 150 mA low-dropout regulator, SOT-23-5; recalled and not checked against the published text
polymer.pla                 polymer: PLA
polymer.petg                polymer: PETG
polymer.abs                 polymer: ABS
polymer.asa                 polymer: ASA
polymer.pa12                polymer: SLS PA12
polymer.pc                  polymer: polycarbonate
oxide.anodic_aluminium      oxide: anodic aluminium oxide
polymer.powder_coat         polymer: polyester powder coat
brass.insert                brass: CuZn39Pb3 free-cutting brass, EN 12164
chs.48_3x3_2                section: EN 10219-2 CHS 48.3 x 3.2
chs.60_3x3_2                section: EN 10219-2 CHS 60.3 x 3.2
chs.76_1x3_2                section: EN 10219-2 CHS 76.1 x 3.2
chs.88_9x3_2                section: EN 10219-2 CHS 88.9 x 3.2
chs.88_9x4                  section: EN 10219-2 CHS 88.9 x 4
chs.114_3x3_6               section: EN 10219-2 CHS 114.3 x 3.6
cable.cu_pvc                cable: copper conductor, IEC 60228 class 2, PVC insulated, single core
cable.cu_pvc_1_5            cable: 1.5 mm2 copper, PVC insulated (type 60227 IEC 01)
cable.cu_pvc_2_5            cable: 2.5 mm2 copper, PVC insulated (type 60227 IEC 01)
cable.cu_pvc_4              cable: 4 mm2 copper, PVC insulated (type 60227 IEC 01)
cable.cu_pvc_6              cable: 6 mm2 copper, PVC insulated (type 60227 IEC 01)
cable.cu_pvc_10             cable: 10 mm2 copper, PVC insulated (type 60227 IEC 01)
cable.cu_pvc_16             cable: 16 mm2 copper, PVC insulated (type 60227 IEC 01)
mcb.B6                      breaker: IEC 60898-1 type B, 6 A, 6 kA
mcb.B10                     breaker: IEC 60898-1 type B, 10 A, 6 kA
mcb.B16                     breaker: IEC 60898-1 type B, 16 A, 6 kA
mcb.B20                     breaker: IEC 60898-1 type B, 20 A, 6 kA
mcb.B32                     breaker: IEC 60898-1 type B, 32 A, 6 kA
terminal.lever_4mm2_75C     terminal: lever terminal, 0.2 to 4 mm2, 32 A, 75 degC
terminal.screw_16mm2_75C    terminal: screw terminal, 1.5 to 16 mm2, 76 A, 75 degC
bolt.M6_8_8                 bolt: M6x1 property class 8.8
bolt.M6_8_8_zn              bolt: M6x1 property class 8.8, zinc plated
bolt.M6_10_9                bolt: M6x1 property class 10.9
bolt.M6_10_9_zn             bolt: M6x1 property class 10.9, zinc plated
bolt.M6_A4_70               bolt: M6x1 property class A4-70
bolt.M8_8_8                 bolt: M8x1.25 property class 8.8
bolt.M8_8_8_zn              bolt: M8x1.25 property class 8.8, zinc plated
bolt.M8_10_9                bolt: M8x1.25 property class 10.9
bolt.M8_10_9_zn             bolt: M8x1.25 property class 10.9, zinc plated
bolt.M8_A4_70               bolt: M8x1.25 property class A4-70
bolt.M10_8_8                bolt: M10x1.5 property class 8.8
bolt.M10_8_8_zn             bolt: M10x1.5 property class 8.8, zinc plated
bolt.M10_10_9               bolt: M10x1.5 property class 10.9
bolt.M10_10_9_zn            bolt: M10x1.5 property class 10.9, zinc plated
bolt.M10_A4_70              bolt: M10x1.5 property class A4-70
bolt.M12_8_8                bolt: M12x1.75 property class 8.8
bolt.M12_8_8_zn             bolt: M12x1.75 property class 8.8, zinc plated
bolt.M12_10_9               bolt: M12x1.75 property class 10.9
bolt.M12_10_9_zn            bolt: M12x1.75 property class 10.9, zinc plated
bolt.M12_A4_70              bolt: M12x1.75 property class A4-70
bolt.M16_8_8                bolt: M16x2 property class 8.8
bolt.M16_8_8_zn             bolt: M16x2 property class 8.8, zinc plated
bolt.M16_10_9               bolt: M16x2 property class 10.9
bolt.M16_10_9_zn            bolt: M16x2 property class 10.9, zinc plated
bolt.M16_A4_70              bolt: M16x2 property class A4-70
bolt.M20_8_8                bolt: M20x2.5 property class 8.8
bolt.M20_8_8_zn             bolt: M20x2.5 property class 8.8, zinc plated
bolt.M20_10_9               bolt: M20x2.5 property class 10.9
bolt.M20_10_9_zn            bolt: M20x2.5 property class 10.9, zinc plated
bolt.M20_A4_70              bolt: M20x2.5 property class A4-70
bolt.M24_8_8                bolt: M24x3 property class 8.8
bolt.M24_8_8_zn             bolt: M24x3 property class 8.8, zinc plated
bolt.M24_10_9               bolt: M24x3 property class 10.9
bolt.M24_10_9_zn            bolt: M24x3 property class 10.9, zinc plated
bolt.M24_A4_70              bolt: M24x3 property class A4-70
screw.M2_5x6_shcs           screw: M2_5 x 6 ISO 4762 socket head cap screw
screw.M2_5x8_shcs           screw: M2_5 x 8 ISO 4762 socket head cap screw
screw.M2_5x10_shcs          screw: M2_5 x 10 ISO 4762 socket head cap screw
screw.M2_5x12_shcs          screw: M2_5 x 12 ISO 4762 socket head cap screw
screw.M2_5x16_shcs          screw: M2_5 x 16 ISO 4762 socket head cap screw
screw.M2_5x20_shcs          screw: M2_5 x 20 ISO 4762 socket head cap screw
screw.M3x6_shcs             screw: M3 x 6 ISO 4762 socket head cap screw
screw.M3x8_shcs             screw: M3 x 8 ISO 4762 socket head cap screw
screw.M3x10_shcs            screw: M3 x 10 ISO 4762 socket head cap screw
screw.M3x12_shcs            screw: M3 x 12 ISO 4762 socket head cap screw
screw.M3x16_shcs            screw: M3 x 16 ISO 4762 socket head cap screw
screw.M3x20_shcs            screw: M3 x 20 ISO 4762 socket head cap screw
screw.M4x6_shcs             screw: M4 x 6 ISO 4762 socket head cap screw
screw.M4x8_shcs             screw: M4 x 8 ISO 4762 socket head cap screw
screw.M4x10_shcs            screw: M4 x 10 ISO 4762 socket head cap screw
screw.M4x12_shcs            screw: M4 x 12 ISO 4762 socket head cap screw
screw.M4x16_shcs            screw: M4 x 16 ISO 4762 socket head cap screw
screw.M4x20_shcs            screw: M4 x 20 ISO 4762 socket head cap screw
screw.M3x6_csk              screw: M3 x 6 ISO 10642 countersunk screw
screw.M3x8_csk              screw: M3 x 8 ISO 10642 countersunk screw
screw.M3x10_csk             screw: M3 x 10 ISO 10642 countersunk screw
screw.M3x12_csk             screw: M3 x 12 ISO 10642 countersunk screw
screw.M3x16_csk             screw: M3 x 16 ISO 10642 countersunk screw
screw.M3x20_csk             screw: M3 x 20 ISO 10642 countersunk screw
screw.M4x6_csk              screw: M4 x 6 ISO 10642 countersunk screw
screw.M4x8_csk              screw: M4 x 8 ISO 10642 countersunk screw
screw.M4x10_csk             screw: M4 x 10 ISO 10642 countersunk screw
screw.M4x12_csk             screw: M4 x 12 ISO 10642 countersunk screw
screw.M4x16_csk             screw: M4 x 16 ISO 10642 countersunk screw
screw.M4x20_csk             screw: M4 x 20 ISO 10642 countersunk screw
insert.M3x5_7               insert: heat-set brass insert M3, 5.7 mm long
insert.M3x4                 insert: heat-set brass insert M3, 4 mm long
insert.M4x8_1               insert: heat-set brass insert M4, 8.1 mm long
install.clipped_direct      cable installation method
process.zinc_plate          coating, leaves zinc.electroplate exposed
process.mig_weld_6xxx       weld; aluminium fy reduced within 30 mm of the weld for plates 6 mm < t <= 12 mm (EN 1999-1-1 6.1.6.3, not checked)
process.print.fdm_pla_0_4   printing preset (material extrusion)
process.print.fdm_petg_0_4  printing preset (material extrusion)
process.powder.sls_pa12     printing preset (powder-bed fusion)
process.sheet.laser_al_3    sheet cutting preset
process.mill.al6061_3axis   milling preset
process.anodize_ii          coating, leaves oxide.anodic_aluminium exposed
process.powder_coat         coating, leaves polymer.powder_coat exposed
indoor_dry                  environment: corrosivity C1, dry, ambient air temperature from +5 to +40 degC
outdoor_c3                  environment: corrosivity C3, wet, ambient air temperature from -25 to +55 degC
marine_c5                   environment: corrosivity C5, wet, ambient air temperature from -25 to +55 degC
W36x231                     W shape: d 36.5 in, bf 16.5 in, tw 0.76 in, tf 1.26 in
W30x99                      W shape: d 29.7 in, bf 10.5 in, tw 0.52 in, tf 0.67 in
W30x90                      W shape: d 29.5 in, bf 10.4 in, tw 0.47 in, tf 0.61 in
W27x84                      W shape: d 26.7 in, bf 10 in, tw 0.46 in, tf 0.64 in
W24x76                      W shape: d 23.9 in, bf 8.99 in, tw 0.44 in, tf 0.68 in
W24x55                      W shape: d 23.6 in, bf 7.01 in, tw 0.395 in, tf 0.505 in
W21x73                      W shape: d 21.2 in, bf 8.3 in, tw 0.455 in, tf 0.74 in
W21x62                      W shape: d 21 in, bf 8.24 in, tw 0.4 in, tf 0.615 in
W21x57                      W shape: d 21.1 in, bf 6.56 in, tw 0.405 in, tf 0.65 in
W21x50                      W shape: d 20.8 in, bf 6.53 in, tw 0.38 in, tf 0.535 in
W21x44                      W shape: d 20.7 in, bf 6.5 in, tw 0.35 in, tf 0.45 in
W18x50                      W shape: d 18 in, bf 7.5 in, tw 0.355 in, tf 0.57 in
W18x35                      W shape: d 17.7 in, bf 6 in, tw 0.3 in, tf 0.425 in
W16x50                      W shape: d 16.3 in, bf 7.07 in, tw 0.38 in, tf 0.63 in
W16x40                      W shape: d 16 in, bf 7 in, tw 0.305 in, tf 0.505 in
W16x36                      W shape: d 15.9 in, bf 6.99 in, tw 0.295 in, tf 0.43 in
W16x31                      W shape: d 15.9 in, bf 5.53 in, tw 0.275 in, tf 0.44 in
W16x26                      W shape: d 15.7 in, bf 5.5 in, tw 0.25 in, tf 0.345 in
W14x90                      W shape: d 14 in, bf 14.5 in, tw 0.44 in, tf 0.71 in
W14x61                      W shape: d 13.9 in, bf 10 in, tw 0.375 in, tf 0.645 in
W14x53                      W shape: d 13.9 in, bf 8.06 in, tw 0.37 in, tf 0.66 in
W14x38                      W shape: d 14.1 in, bf 6.77 in, tw 0.31 in, tf 0.515 in
W14x22                      W shape: d 13.7 in, bf 5 in, tw 0.23 in, tf 0.335 in
W12x65                      W shape: d 12.1 in, bf 12 in, tw 0.39 in, tf 0.605 in
W12x50                      W shape: d 12.2 in, bf 8.08 in, tw 0.37 in, tf 0.64 in
W12x40                      W shape: d 11.9 in, bf 8.01 in, tw 0.295 in, tf 0.515 in
W12x35                      W shape: d 12.5 in, bf 6.56 in, tw 0.3 in, tf 0.52 in
W12x26                      W shape: d 12.2 in, bf 6.49 in, tw 0.23 in, tf 0.38 in
W10x49                      W shape: d 10 in, bf 10 in, tw 0.34 in, tf 0.56 in
W10x45                      W shape: d 10.1 in, bf 8.02 in, tw 0.35 in, tf 0.62 in
WT18x115_5                  WT shape, cut from W36x231
WT15x49_5                   WT shape, cut from W30x99
WT15x45                     WT shape, cut from W30x90
WT13_5x42                   WT shape, cut from W27x84
WT12x38                     WT shape, cut from W24x76
WT12x27_5                   WT shape, cut from W24x55
WT10_5x36_5                 WT shape, cut from W21x73
WT10_5x31                   WT shape, cut from W21x62
WT10_5x28_5                 WT shape, cut from W21x57
WT10_5x25                   WT shape, cut from W21x50
WT10_5x22                   WT shape, cut from W21x44
WT9x25                      WT shape, cut from W18x50
WT9x17_5                    WT shape, cut from W18x35
WT8x25                      WT shape, cut from W16x50
WT8x20                      WT shape, cut from W16x40
WT8x18                      WT shape, cut from W16x36
WT8x15_5                    WT shape, cut from W16x31
WT8x13                      WT shape, cut from W16x26
WT7x45                      WT shape, cut from W14x90
WT7x30_5                    WT shape, cut from W14x61
WT7x26_5                    WT shape, cut from W14x53
WT7x19                      WT shape, cut from W14x38
WT7x11                      WT shape, cut from W14x22
WT6x32_5                    WT shape, cut from W12x65
WT6x25                      WT shape, cut from W12x50
WT6x20                      WT shape, cut from W12x40
WT6x17_5                    WT shape, cut from W12x35
WT6x13                      WT shape, cut from W12x26
WT5x24_5                    WT shape, cut from W10x49
WT5x22_5                    WT shape, cut from W10x45
L8x4x5_8                    angle: legs 8 in x 4 in, thickness 0.625 in
L7x4x5_8                    angle: legs 7 in x 4 in, thickness 0.625 in
L7x4x1_2                    angle: legs 7 in x 4 in, thickness 0.5 in
L6x4x3_4                    angle: legs 6 in x 4 in, thickness 0.75 in
L6x4x1_2                    angle: legs 6 in x 4 in, thickness 0.5 in
L6x4x3_8                    angle: legs 6 in x 4 in, thickness 0.375 in
L5x3_1_2x3_8                angle: legs 5 in x 3.5 in, thickness 0.375 in
L5x3_1_2x5_16               angle: legs 5 in x 3.5 in, thickness 0.3125 in
L5x3_1_2x1_4                angle: legs 5 in x 3.5 in, thickness 0.25 in
L4x4x1_2                    angle: legs 4 in x 4 in, thickness 0.5 in
L4x4x3_8                    angle: legs 4 in x 4 in, thickness 0.375 in
L4x4x5_16                   angle: legs 4 in x 4 in, thickness 0.3125 in
L4x4x1_4                    angle: legs 4 in x 4 in, thickness 0.25 in
L4x3_1_2x3_8                angle: legs 4 in x 3.5 in, thickness 0.375 in
L4x3_1_2x5_16               angle: legs 4 in x 3.5 in, thickness 0.3125 in
L4x3x3_8                    angle: legs 4 in x 3 in, thickness 0.375 in
shop_deck.plate.t3_16       plate 3/16 in is stocked
shop_deck.plate.t1_4        plate 1/4 in is stocked
shop_deck.plate.t5_16       plate 5/16 in is stocked
shop_deck.plate.t3_8        plate 3/8 in is stocked
shop_deck.plate.t7_16       plate 7/16 in is stocked
shop_deck.plate.t1_2        plate 1/2 in is stocked
shop_deck.plate.t9_16       plate 9/16 in is stocked
shop_deck.plate.t5_8        plate 5/8 in is stocked
shop_deck.plate.t3_4        plate 3/4 in is stocked
shop_deck.plate.t7_8        plate 7/8 in is stocked
shop_deck.plate.t1          plate 1 in is stocked
shop_deck.plate.t1_1_8      plate 1-1/8 in is stocked
shop_deck.plate.t1_1_4      plate 1-1/4 in is stocked
shop_deck.plate.t1_3_8      plate 1-3/8 in is stocked
shop_deck.plate.t1_1_2      plate 1-1/2 in is stocked
shop_deck.plate.t1_3_4      plate 1-3/4 in is stocked
shop_deck.plate.t2          plate 2 in is stocked
shop_deck.plate.t2_1_4      plate 2-1/4 in is stocked
shop_deck.plate.t2_1_2      plate 2-1/2 in is stocked
shop_deck.plate.t2_3_4      plate 2-3/4 in is stocked
shop_deck.plate.t3          plate 3 in is stocked
```
