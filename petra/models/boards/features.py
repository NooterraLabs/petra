"""Which footprints are mounting holes, connectors, switches, LEDs and test points, and what
the enclosure deck must still be told about each. Trusted.

A footprint is marked by every row of `RULES` it matches: the letters of its reference before
the first digit, the nickname of its library (the part of its library id before the colon),
or a pad's test-point property. A row reads only those facts from the file. A board file
holds no part height, no mating direction and no light path, so `premises` names each as a
missing premise the enclosure deck demands as a signed line.
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
    its letters equal the pattern, a library when its nickname starts with it, and a pad when
    one of its pads carries the property."""

    feature: Feature
    field: str
    pattern: str
    source: str


_LIBRARIES = "reported, the KiCad footprint libraries listed at kicad.github.io/footprints"

RULES: tuple[Rule, ...] = (
    Rule(Feature.MOUNTING_HOLE, "library", "MountingHole", _LIBRARIES),
    Rule(Feature.MOUNTING_HOLE, "reference", "H", "recalled, the reference of KiCad's MountingHole symbol"),
    Rule(Feature.MOUNTING_HOLE, "reference", "MH", "recalled, common usage"),
    Rule(Feature.CONNECTOR, "library", "Connector", _LIBRARIES),
    Rule(Feature.CONNECTOR, "library", "TerminalBlock", _LIBRARIES),
    Rule(Feature.CONNECTOR, "reference", "J", "recalled, IEEE 315 class letter for a jack"),
    Rule(Feature.CONNECTOR, "reference", "P", "recalled, IEEE 315 class letter for a plug"),
    Rule(Feature.CONNECTOR, "reference", "CN", "recalled, common usage"),
    Rule(Feature.SWITCH, "library", "Button_Switch", _LIBRARIES),
    Rule(Feature.SWITCH, "reference", "SW", "recalled, the reference of KiCad's switch symbols"),
    Rule(Feature.SWITCH, "reference", "S", "recalled, IEEE 315 class letter for a switch"),
    Rule(Feature.LED, "library", "LED_", _LIBRARIES),
    Rule(Feature.LED, "reference", "LED", "recalled, common usage"),
    Rule(Feature.LED, "reference", "DS", "recalled, IEEE 315 class letter for an indicator lamp"),
    Rule(Feature.TEST_POINT, "library", "TestPoint", _LIBRARIES),
    Rule(Feature.TEST_POINT, "reference", "TP", "recalled, the reference of KiCad's test point symbols"),
    Rule(Feature.TEST_POINT, "pad", "pad_prop_testpoint", "reported, dev-docs.kicad.org, footprint pad properties"),
)


def classify(reference: str, library: str, pad_properties: frozenset[str]) -> tuple[Rule, ...]:
    """The rows of RULES a footprint matches."""
    letters = re.match(r"[A-Za-z]*", reference).group(0).upper()
    nickname = library.split(":", 1)[0]
    return tuple(r for r in RULES if (r.field == "reference" and letters == r.pattern)
                 or (r.field == "library" and nickname.startswith(r.pattern))
                 or (r.field == "pad" and r.pattern in pad_properties))


@dataclass(frozen=True)
class Premise:
    """A fact the enclosure deck needs and the board file does not hold."""

    name: str
    what: str


HEIGHT = Premise("height", "how far the part's body stands above the board face it sits on")
PROTRUSION = Premise("lead protrusion", "how far its leads and pegs stand beyond the opposite face once fitted")

DEMANDED: dict[Feature, tuple[Premise, ...]] = {
    Feature.MOUNTING_HOLE: (Premise("fastener", "the screw, standoff or rivet that passes through the hole"),),
    Feature.CONNECTOR: (Premise("mating direction", "the direction a mating plug or cable arrives from, and the room it needs"),),
    Feature.SWITCH: (Premise("actuator", "the direction the actuator is pressed or slid from, and its travel"),),
    Feature.LED: (Premise("light path", "the direction the light leaves the part, and what must stay clear for it"),),
    Feature.TEST_POINT: (Premise("probe access", "the direction a probe reaches the test point from"),),
}

THICKNESS = Premise("thickness", "the board's thickness, which the file does not state")
EDGE = Premise("edge tolerance", "how far the board maker's cut edge may stray from the drawn outline")
HOLES = Premise("hole size as made", "how far each drilled hole, plated or not, may differ from its drill size")


def premises(marks: tuple[Rule, ...], has_pads: bool, has_holes: bool) -> tuple[Premise, ...]:
    """The premises a footprint leaves to the enclosure deck. Every footprint with pads that
    is not a mounting hole has a body of unknown height. A footprint with drilled pads may
    stand beyond the far face."""
    features = {m.feature for m in marks}
    out = []
    if has_pads and Feature.MOUNTING_HOLE not in features:
        out.append(HEIGHT)
    if has_holes and Feature.MOUNTING_HOLE not in features:
        out.append(PROTRUSION)
    for feature in Feature:
        if feature in features:
            out += DEMANDED[feature]
    return tuple(out)
