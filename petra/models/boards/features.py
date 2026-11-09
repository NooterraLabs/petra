"""Which footprints are mounting holes, connectors, switches, LEDs and test points, and what
the enclosure deck must still be told about each. Trusted.

A footprint is marked by every row of `RULES` it matches: the letters of its reference before
the first digit, a word of its library id (the library's nickname and the footprint's name),
or a pad's test-point property. A row reads only those facts from the file. A board file
holds no part height, no mating direction and no light path, so `premises` names each as a
missing premise the enclosure deck demands as a signed line.

A mark adds premises from any row, and takes the height and lead protrusion away only when
the library id says the footprint is a mounting hole and nothing else. The letter H also
names standoffs that stand off the board. A footprint with pads that no row marks carries
the access premise, so a part these rows miss is never silently left out.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Feature(Enum):
    MOUNTING_HOLE = "mounting hole"
    CONNECTOR = "connector"
    SWITCH = "switch"
    LED = "LED"
    TEST_POINT = "test point"


@dataclass(frozen=True)
class Rule:
    """A footprint has `feature` when its `field` matches `pattern`. A reference matches when
    its letters equal the pattern, a library id when one of the pattern's words or phrases,
    split by "|", stands among its words (`words`), and a pad when one of its pads carries
    the property."""

    feature: Feature
    field: str
    pattern: str
    source: str


_LIBRARIES = "reported, the KiCad footprint libraries listed at kicad.github.io/footprints"
_NAMES = "measured, the library ids of the footprints on the boards of docs/kicad_oracle.md"

RULES: tuple[Rule, ...] = (
    Rule(Feature.MOUNTING_HOLE, "library", "mounting hole", _LIBRARIES),
    Rule(Feature.MOUNTING_HOLE, "reference", "H", "recalled, the reference of KiCad's MountingHole symbol"),
    Rule(Feature.MOUNTING_HOLE, "reference", "MH", "recalled, common usage"),
    Rule(Feature.CONNECTOR, "library", "connector|terminal block", _LIBRARIES),
    Rule(Feature.CONNECTOR, "library", "connectors|conn|connect|usb|header|pin socket|jack|jst|molex|hirose|idc|fpc|"
                                       "ffc|dsub|trrs|hdmi|rj", _NAMES),
    Rule(Feature.CONNECTOR, "reference", "J", "recalled, IEEE 315 class letter for a jack"),
    Rule(Feature.CONNECTOR, "reference", "P", "recalled, IEEE 315 class letter for a plug"),
    Rule(Feature.CONNECTOR, "reference", "CN", "recalled, common usage"),
    Rule(Feature.SWITCH, "library", "button|switch", _LIBRARIES),
    Rule(Feature.SWITCH, "library", "sw|buttons|tactile|tact|spdt|spst", _NAMES),
    Rule(Feature.SWITCH, "reference", "SW", "recalled, the reference of KiCad's switch symbols"),
    Rule(Feature.SWITCH, "reference", "S", "recalled, IEEE 315 class letter for a switch"),
    Rule(Feature.LED, "library", "led", _LIBRARIES),
    Rule(Feature.LED, "library", "leds", _NAMES),
    Rule(Feature.LED, "reference", "LED", "recalled, common usage"),
    Rule(Feature.LED, "reference", "DS", "recalled, IEEE 315 class letter for an indicator lamp"),
    Rule(Feature.TEST_POINT, "library", "test point", _LIBRARIES),
    Rule(Feature.TEST_POINT, "library", "testpoint", _NAMES),
    Rule(Feature.TEST_POINT, "reference", "TP", "recalled, the reference of KiCad's test point symbols"),
    Rule(Feature.TEST_POINT, "pad", "pad_prop_testpoint", "reported, dev-docs.kicad.org, footprint pad properties"),
)


def words(library: str) -> str:
    """A library id's runs of letters, split where a small letter meets a capital, in lower
    case: "kbd:ResetSW" gives "kbd reset sw" and "OLIMEX_LEDs-FP:LED_0603" "olimex leds fp led"."""
    return " ".join(re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", library).lower()))


def classify(reference: str, library: str, pad_properties: frozenset[str]) -> tuple[Rule, ...]:
    """The rows of RULES a footprint matches."""
    letters = re.match(r"[A-Za-z]*", reference).group(0).upper()
    named = words(library)
    return tuple(r for r in RULES if (r.field == "reference" and letters == r.pattern)
                 or (r.field == "library" and re.search(rf"\b(?:{r.pattern})\b", named))
                 or (r.field == "pad" and r.pattern in pad_properties))


def mounting(marks: tuple[Rule, ...]) -> bool:
    """Whether the library id says the footprint is a mounting hole, and no row marks it as
    anything else. Its drilled pads are then mounting holes, and it has no body or leads."""
    return {m.feature for m in marks} == {Feature.MOUNTING_HOLE} and any(m.field == "library" for m in marks)


@dataclass(frozen=True)
class Premise:
    """A fact the enclosure deck needs and the board file does not hold."""

    name: str
    what: str


HEIGHT = Premise("height", "how far the part's body stands above the board face it sits on")
ACCESS = Premise("access", "whether light, a hand, a plug or a probe must reach the part through the enclosure; "
                           "no row of RULES marks it")
PROTRUSION = Premise("lead protrusion", "how far its leads and pegs stand beyond the opposite face once fitted")

DEMANDED: dict[Feature, tuple[Premise, ...]] = {
    Feature.MOUNTING_HOLE: (Premise("fastener", "the screw, standoff or rivet that passes through the hole"),),
    Feature.CONNECTOR: (Premise("mating direction", "the direction a mating plug or cable arrives from, and the room it needs"),),
    Feature.SWITCH: (Premise("actuator", "the direction the actuator is pressed or slid from, and its travel"),),
    Feature.LED: (Premise("light path", "the direction the light leaves the part, and what must stay clear for it"),),
    Feature.TEST_POINT: (Premise("probe access", "the direction a probe reaches the test point from"),),
}

THICKNESS = Premise("thickness as made", "the range the made board's thickness falls in, mm; a thickness the file "
                                         "states is the drawn one, and a board maker makes it within a tolerance")
EDGE = Premise("edge tolerance", "how far the board maker's cut edge may stray from the drawn outline")
HOLES = Premise("hole size as made", "how far each drilled hole, plated or not, may differ from its drill size")


def premises(marks: tuple[Rule, ...], has_pads: bool, has_holes: bool) -> tuple[Premise, ...]:
    """The premises a footprint leaves to the enclosure deck. Every footprint with pads that
    is not a mounting hole has a body of unknown height. A footprint with drilled pads may
    stand beyond the far face. A footprint with pads and no mark may need a way in."""
    features = {m.feature for m in marks}
    out = [HEIGHT] if has_pads and not mounting(marks) else []
    if has_holes and not mounting(marks):
        out.append(PROTRUSION)
    for feature in Feature:
        if feature in features:
            out += DEMANDED[feature]
    return tuple(out) + ((ACCESS,) if has_pads and not features else ())
