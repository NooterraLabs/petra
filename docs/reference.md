# The Petra language

`petra docs reference` prints this page. On the command line, `petra kinds [DECK|TYPE]` and
`petra new TYPE [--name NAME] [--card]` print the same tables.

`python -m petra.teach --write` generates this page from the shipped decks of rules, as the grid reads
them, and the examples. Do not edit it by hand. tests/test_teach.py fails when the page is stale.

## File layout and syntax

A check reads two files. The card, `NAME.card`, holds what is asked: the name, the deck of rules to
check against, every signed bound, the load cases, and the waivers. The design, `NAME.petra`, holds the answer: the parts. Whoever asks writes
the card, and a designer or an agent writes the design. A design cannot state a load, a waiver, or a
signature, so it cannot change what is asked of it.
`petra check NAME.petra` reads `NAME.card` beside the design, and `--card FILE` names another card.

```
petra 0

card "lap-splice" {
  owner "s.engineer@example.org"
  rules "aisc360-22" "sha256:fb92c98c91e26573ff826e9983047dbd19142e2f26b3feb14723329aa6877d94"
}

given tab.Fy in [36 ksi, 36 ksi] signed "s.engineer@example.org" source "ASTM A36, specified minimum"
...

load gravity {
  on splice pull in [0 kip, 45 kip]
  signed "s.engineer@example.org" source "calculation C-12, LRFD combination 1.2D + 1.6L"
}
```

```
petra 0

plate tab {
  thickness 0.375 inch
  Fy given tab.Fy
  ...
}

lap splice {
  count 3
  joins tab strap
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
- A name may be dotted, as in `tab.Fy`. The part after a dot may start with a digit.
- A number is exact. It is an integer, a decimal, or a fraction such as `3/4`, and it never has an
  exponent. The unit follows the number, as in `0.75 inch`, `45 kip`, and `10mm`. A number with no unit
  is dimensionless.
- A string is written `"..."`. Its only escapes are `\"` and `\\`.
- A bound is a range with its provenance, written
  `in [<lo>, <hi>] [mean <value>] signed "<owner>" source "<source>"`. A measured value has
  `measured` in place of `signed`. Only a card states a bound, and outside a family every bound carries
  a signature. In a family, `param NAME` stands where a bound would. No deck reads a `mean` yet: a card
  that states one on a given or on a load is refused where a design with parts is checked or exported.
- `in`, `mean`, `signed`, `measured`, `source`, `param`, and `given` cannot be names inside a line. No
  declared name can be a declaration word.
- A file has at most 1,000,000 bytes. `petra check`, `petra.export` and the MCP tools refuse a larger
  file before they parse it.

A pair that is refused prints its problems, each with its file, line and column. What is printed is
bounded, whatever the files hold.

- A message that names a table, such as the kinds or the givens of the card, lists at most 4 of
  its names and says how many it has. For an unknown mechanism they are the names that start most as
  the unknown one does.
- A message that arises more than once is printed once, at the first place, with how many times it
  arose.
- At most 100 problems are printed for a file, and then how many more there were.
- A problem of more than 500 characters is cut, and says how many were left out.

## Declarations

### card

A card has one `card` block, which names what is asked. `owner` is required. `rules` names the deck of rules that the owner has the design checked against, by its name and the hash of its file, and a design of a deck's types is checked only with a card that names the deck `petra check` has: `petra kinds` prints the line to write. So the hash of a card covers which rules its owner asked for, and after a change to the deck the card is refused until its owner names the new one. `environment` is optional and names where the design stands. No deck of rules reads an environment yet, so `petra check` refuses a card that states one for a design of a deck's types.

```
card "lap-splice" {
  owner "s.engineer@example.org"
  rules "aisc360-22" "sha256:fb92c98c91e26573ff826e9983047dbd19142e2f26b3feb14723329aa6877d94"
}
```

### param

`param` declares a range that a line reads by writing `param NAME` in place of a value. A param is declared in the card or in the design, and a load and the ambient read only the card's params. No deck of rules reads a param yet, and `petra check` refuses a design of a deck's types that declares one.

```
param run in [0 m, 20 m]
```

### ambient

`ambient` declares the ambient temperature range, with a signature. No deck of rules reads one yet.

```
ambient in [10 degC, 40 degC] signed "site.manager@example.org" source "site survey 2026-09"
```

### given

`given` states a signed bound under a name. A part's line in the design reads it by writing `given NAME` where the value goes. The design reads every given the card states. A name may be `PART.FIELD`. A part of a deck's type reads only the given named for it: `Fy given tab.Fy` on the part `tab`. A card may also state a thing exactly, with `is` in place of the range: the name of a key, as a bare word or in quotes, or a number whose value is whole with no unit, `4`, `4.0` or `8/2` alike, as a count the design writes, as in `given beam.category is B signed "..." source "..."` and `given quad.rotors is 4 signed "..." source "..."`. It has no range and no `mean`, and it carries a signature. The type of a part says which fields the card states: a design that writes one of them itself is refused.

```
given tab.Fy in [36 ksi, 36 ksi] signed "s.engineer@example.org" source "ASTM A36, specified minimum"
```

### component

A component is a part, written `TYPE NAME { ... }` in the design, with one line per field. The Types section lists every type of the shipped decks and its lines. A design whose parts are all of kinds no deck has is read too, and `petra check` gives it UNKNOWN with that reason: there is no rule to check it by. A design that has such a part beside parts of a deck's types is refused.

```
plate tab {
  thickness 0.375 inch
  width 6 inch
  Fy given tab.Fy
  Fu given tab.Fu
}
```

### load

A `load` block is one load case. Each entry is `on <part> <load> <bound>`, where the load is one that the part's type takes. An entry is signed by its own signature or by the signature on the block's last line.

```
load gravity {
  on splice pull in [0 kip, 45 kip]
  signed "s.engineer@example.org" source "calculation C-12, LRFD combination 1.2D + 1.6L"
}
```

### tests

A `tests` block records proof tests. No deck of rules reads one yet.

```
tests proof {
  on hook trials 300 failures 0 at 36 kN
  signed "qa.lab@example.org" source "batch 2026-09 proof tests, independent lots"
}
```

### claim

A claim takes one of three forms: a bound on a quantity, with an optional margin and the load cases it holds under, a range-and-mean probability bound, or a tested-failure probability bound. No deck of rules reads a claim yet. What is asked of a part of a deck's type is the grid of its deck: every mechanism the deck asks about, for every part of the type, under every load case.

```
claim strength: frame.collapse_factor >= 1.5 under crowd
claim stress:   frame.member(diag_ad).stress <= 235 MPa margin 10 MPa under crowd
claim overload: P(hook.utilisation > 1) <= 3/10 under lift
claim tested:   P(fail hook at 36 kN) <= 1/100 confidence 95 % from proof
```

### waive

`waive` rests an open cell of the grid on a signature. Only the card can waive. It names the mechanism, the part, who answers for it, and the reason. The Types section lists the mechanisms the grid asks of each type. A waiver rests only a cell the deck has no rule for, or one that holds under a completion of what the design leaves out. Petra reports such a cell as waived, never as proved, and a pass that rests on one reads PASS_WAIVED.

```
waive lap.tightening on splice by "s.engineer@example.org" reason "snug-tight bolts: a bearing-type joint under static load, J3.2 (a)(1)"
```

## Grammar

The grammar below is EBNF, and `NL` is a line end. The types of parts and their lines are not in the grammar. Each deck of rules declares its own, as the Types section shows.

```
card file   = "petra" INT NL { ( card | param | ambient | given | load | tests | claim | waive ) NL } EOF ;
design file = "petra" INT NL { ( param | component ) NL } EOF ;
card      = "card" STRING "{" NL { ( "owner" STRING | "environment" IDENT | "rules" STRING STRING ) NL } "}" ;
param     = "param" IDENT "in" range ;
ambient   = "ambient" bound ;
given     = "given" name ( "in" range [ "mean" qty ] | "is" ( IDENT | STRING | INT ) ) [ signature ] ;
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
unit      = IDENT [ "/" IDENT ] [ "^" INT ] | "%" ;   m/s and inch^4, each written with no space
qoi       = segment { "." segment } ;          last segment is the quantity name
segment   = IDENT [ "(" IDENT ")" ] ;          member(diag_ad) names element diag_ad
path      = IDENT { "." IDENT } ;
ref       = IDENT { "." IDENT } ;   a word of a line, the name of a part or of a key,
                                    a dotted name (tab.Fy) or a mechanism (lap.slip)
rel       = "<=" | ">=" ;
```

## Units

A card and a design accept these unit spellings.

| dimension | spellings |
|---|---|
| dimensionless | `%` |
| length | `m`, `mm`, `um`, `cm`, `km`, `inch`, `ft`, `mile` |
| area | `mm2`, `m2`, `inch2` |
| force | `N`, `kN`, `MN`, `lbf`, `kip`, `kips` |
| stress | `Pa`, `kPa`, `MPa`, `GPa`, `psi`, `ksi` |
| current | `uA`, `mA`, `A`, `kA` |
| voltage | `V`, `kV` |
| resistance | `ohm`, `mohm`, `kohm`, `Mohm` |
| resistance per length | `ohm/km` |
| power | `mW`, `W`, `kW` |
| energy, torque | `J`, `Nm`, `kip_in`, `kip_ft`, `lbf_in`, `lbf_ft` |
| time | `s`, `ms`, `min`, `h` |
| temperature | `degC` |
| mass | `g`, `kg`, `lb`, `oz` |
| I2t | `A2s` |
| turns or cycles in a time | `Hz`, `rpm` |
| charge | `mAh`, `Ah` |
| speed | `m/s`, `km/h`, `knot`, `mph` |
| density | `kg/m3`, `g/cm3` |
| force over length | `N/mm` |

A unit of length may be raised to the power 2, 3 or 4: the unit, `^` and the power, with no space, as
in `mm^3` and `inch^4`. Its factor is the unit's own factor to that power, exactly, so `1 inch^4` is
(127/5000)^4 m^4. A power is one of `2`, `3` and `4`, written as that one digit: `inch^1`, `inch^5`,
`inch^04` and `inch^3/2` are refused. Only a unit of length takes a power, so `kN^2` and `mm2^2` are
refused. An area has two spellings with one meaning: `mm^2` is `mm2`, `m^2` is `m2` and `inch^2` is
`inch2`. A section modulus is written in a length to the third power and a moment of inertia in a
length to the fourth. Petra prints such a quantity in `mm^3`, `cm^3`, `m^3` and the like, which it
reads back.

A unit is one spelling of the table and nothing else. A unit with a `/` in it, as `m/s`, `km/h`,
`kg/m3` and `ohm/km` are, is written with no space and is never worked out from its halves: `m/s` is
one unit, and `mm/s`, `m/min` and `kg/m^3` are none. A product is written with `_`, as in `kip_in`
and `lbf_ft`. A unit that had a spelling got no second one, so a newton metre is `Nm`. `mAh` is no
`m`, `A` and `h`, and `min` no `m` and `in`: a spelling is read whole. A word right after a number is its unit,
whatever else has that name: `h 2 h` gives the field `h` two hours, and `5 K` is refused, because
`K` is no unit.

These units are read since 2026-11-11. Each factor is exact. NIST Special Publication 811, 2008
edition, Appendix B, lists each factor that is not SI's own and marks it exact.

| unit | is | by |
|---|---|---|
| `kW` | 1,000 W | the SI prefix |
| `min`, `h` | 60 s and 3,600 s | the SI Brochure, 9th edition, Table 8 |
| `Hz` | 1 a second | the SI Brochure, 9th edition, Table 4 |
| `rpm` | 1/60 Hz | one turn a minute, where a turn is the plain number 1 |
| `mAh`, `Ah` | 18/5 A s and 3,600 A s | a current for an hour of 3,600 s |
| `m/s` | 1 m/s | the SI unit |
| `km/h` | 5/18 m/s | 1,000 m in 3,600 s |
| `knot` | 463/900 m/s | one international nautical mile of 1,852 m in 3,600 s |
| `kg/m3`, `g/cm3` | 1 kg/m3 and 1,000 kg/m3 | the SI unit and its prefixes |
| `N/mm` | 1,000 N/m | the SI prefix |
| `mile` | 201168/125 m, which is 1,609.344 m | 5,280 ft of 0.3048 m, by the international yard of 1959 |
| `mph` | 1397/3125 m/s, which is 0.44704 m/s | a mile in 3,600 s |
| `lb` | 45359237/100000000 kg, which is 0.45359237 kg | the international pound of 1959 |
| `oz` | 1/16 lb, which is 0.028349523125 kg | the avoirdupois ounce |
| `lbf_in`, `lbf_ft` | a pound-force times an inch, and times 12 inch | `lbf` and `inch`, as `kip_in` and `kip_ft` are written |

A rotation is counted in turns, and a turn is the plain number 1. So a speed of rotation is a plain
1 over a time: `Hz` is one turn a second, and `rpm` is one turn a minute. An angle is a plain number
too, and Petra has no unit for one: a deck that needs radians writes the 2 pi itself. A report
prints a time in `s` or `ms` and a power in `W` or `mW`, and never chooses `min`, `h`, `kW`, `rpm`,
`km/h` or `knot`.

The one unit of temperature is `degC`. Its number is the temperature on the Celsius scale, with its
sign: `-10 degC` is ten below freezing. There is no `K` and no `degF`. A unit is a factor and
nothing more, and those two need an offset as well. With one, `50 degF` would be read as 10 degC
where it is a temperature and as 27.8 degC where it is a difference of two, and nothing in a value
says which it is. So a temperature in Fahrenheit is written in `degC` as the exact fraction:
25 degF is `-35/9 degC` and 150 degF is `590/9 degC`. A difference of temperatures is in `degC`
too, and a kelvin of difference is `1 degC`.

## Exit codes of `petra check`

| status | code |
|---|---|
| PASS | 0 |
| FAIL | 1 |
| UNKNOWN | 2 |
| INPUT_ERROR | 3 |
| INTERNAL_ERROR | 4 |
| PASS_WAIVED | 6 |
| BROKEN_PIPE | 141 |

PASS_WAIVED is the pass of a design checked against a deck of rules when a waiver of its card rests
a cell: the design passes what the deck could check, and each signer answers for the cells its
waiver rests. `petra check --json` lists those waivers under `waived`, and the kernel says PASS
and lists the same waivers.

## Types

A part is written `TYPE NAME { ... }`, with one line per field. A type belongs to a deck of rules,
which says what each of its lines means, what a part of it needs to be a part at all, and which
mechanisms the grid asks of every part of it. A mechanism with a rule is worked out by the kernel. One
with no rule yet is an open cell, and the design reads UNKNOWN until a rule or a waiver settles it.

### Deck aisc360-22

Its file's hash is `sha256:fb92c98c91e26573ff826e9983047dbd19142e2f26b3feb14723329aa6877d94`. `petra kinds aisc360-22` prints this.

```
deck aisc360-22: plate, lap
  a card names it in its card block: rules "aisc360-22" "sha256:fb92c98c91e26573ff826e9983047dbd19142e2f26b3feb14723329aa6877d94"

plate <name> { one line each }    a flat steel plate that a joint connects
  lines, each once:
    thickness <length>
        its thickness
    width <length>
        its gross width, across the force it carries
    Fy given <name>.Fy
        the specified minimum yield stress of its steel; the card states it: given <name>.Fy in [<lo>, <hi>] signed ...
    Fu given <name>.Fu
        the specified minimum tensile strength of its steel; the card states it: given <name>.Fu in [<lo>, <hi>] signed ...

lap <name> { one line each }    one line of two or more bolts in single shear through two plates, in a bearing-type joint that is pulled along the line
  `petra new lap` prints examples/deck/lap_pass.petra
  load entry: on <lap> pull in [<lo>, <hi>]    the force the lap carries from one plate to the other along the line, as a required strength by LRFD load combinations
  waive <mechanism> on <lap> by "<owner>" reason "<reason>"
  lines, each once:
    fastener <"Group 120" | "Group 144" | "Group 150">
        the strength group of the bolts, as Section J3.2 names it
    threads <included | excluded>
        whether threads are in the shear plane
    diameter <length>
        the nominal diameter of a bolt
    holes given <name>.holes
        the type of the holes in both plates; the card states it: given <name>.holes is <standard | oversize> signed ...
    count <whole number>
        the number of bolts in the line
    pitch <length>
        the distance between the centres of neighbouring holes
    end <length>
        the least distance from the centre of an end hole to the end of either plate, along the line
    side <length>
        the least distance from the centre of a hole to a side edge of either plate, across the line
    surface given <name>.surface
        whether the plates are painted or otherwise not open to atmospheric corrosion, or are unpainted weathering steel open to it; the card states it: given <name>.surface is <protected | weathering> signed ...
    joins <plate> <plate>
        the two plates
  a part that breaks one of these is no design:
    the line of holes lies within plate a, and each of its two side edges is at least the side distance from the line
    the line of holes lies within plate b, and each of its two side edges is at least the side distance from the line
  the grid asks:
    lap.tightening    whether the bolts must be pretensioned or the joint slip-critical (AISC 360-22 J3.2)
        no rule yet, so its cell is open until the card waives it
    lap.hole_use    whether this type of hole may be used in this joint (AISC 360-22 J3.3)
        no rule yet, so its cell is open until the card waives it
    lap.spacing    minimum spacing of the holes (AISC 360-22 J3.4)
        rule aisc360-22/lap-spacing-centres, aisc360-22/lap-spacing-clear
    lap.end_distance    minimum distance from an end hole to the end of a plate (AISC 360-22 J3.5, Table J3.4)
        rule aisc360-22/lap-end-distance-standard, aisc360-22/lap-end-distance-oversize
    lap.side_distance    minimum distance from a hole to the side edge of a plate (AISC 360-22 J3.5, Table J3.4)
        rule aisc360-22/lap-side-distance-standard, aisc360-22/lap-side-distance-oversize
    lap.spread    maximum spacing of the holes (AISC 360-22 J3.6)
        rule aisc360-22/lap-spread-pitch-protected, aisc360-22/lap-spread-pitch-weathering
    lap.max_edge_distance    maximum distance from a hole to the nearest edge of each plate, by that plate's thickness (AISC 360-22 J3.6)
        no rule yet, so its cell is open until the card waives it
    lap.strength    shear of the bolts with bearing and tearout at their holes (AISC 360-22 J3.7 and J3.11)
        rule aisc360-22/lap-strength
    lap.tension_with_shear    tension on the bolts together with shear (AISC 360-22 J3.8)
        excused for every part: a lap takes one load, a pull along its line, which shears its bolts and puts no tension on them
    lap.slip    slip of a slip-critical joint (AISC 360-22 J3.9)
        answered with lap.tightening, and open while one of them is: slip is asked of a slip-critical joint, and the line of tightening answers whether this joint must be one
    lap.ply_yield    tensile yielding of each plate (AISC 360-22 J4.1)
        rule aisc360-22/lap-ply-yield-a, aisc360-22/lap-ply-yield-b
    lap.ply_rupture    tensile rupture of each plate through its holes (AISC 360-22 J4.1)
        rule aisc360-22/lap-ply-rupture-a, aisc360-22/lap-ply-rupture-b
    lap.ply_shear    shear of a plate as an element loaded in shear (AISC 360-22 J4.2)
        answered with lap.strength, lap.block_shear, and open while one of them is: the plates of a lap are pulled along its line, and shear on their planes beside the bolts is tearout and block shear, which those lines answer
    lap.block_shear    block shear rupture of each plate (AISC 360-22 J4.3)
        rule aisc360-22/lap-block-shear-a, aisc360-22/lap-block-shear-b
    lap.partial_block_shear    block shear rupture of each plate along a block of fewer bolts than all, as the corner at its end bolt (AISC 360-22 J4.3)
        no rule yet, so its cell is open until the card waives it
    lap.ply_compression    yielding and buckling of a plate in compression (AISC 360-22 J4.4)
        excused for a part that has a value for pull, and open for any other: the load on a lap is a pull, which is at least zero on every card
    lap.ply_flexure    bending of the plates, which a lap in single shear sets apart (AISC 360-22 J4.5)
        no rule yet, so its cell is open until the card waives it
```
