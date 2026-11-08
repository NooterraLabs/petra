"""The parts deck's data: process presets, polymer materials, screws and washers. Trusted;
each row is a premise with a tag, an owner and a source.

What will be here:
- Process presets, as registry processes "process.<kind>.<id>", each holding exactly the
  rows rules.rows_read(kind) names, every length in metres:
    process.print.fdm_pla_0_4       build, line_width, layer, wall, hole_min, overhang, fit.clearance, tolerance
    process.powder.sls_pa12         build, min_feature, wall, hole_min, escape, fit.clearance, tolerance
    process.sheet.laser_s275_3      thickness, bed, kerf (a beam tool), reach_tolerance, min_web, min_hole, tolerance
    process.sheet.router_cf_3       thickness, bed, tool.<id> rows, reach_tolerance, min_web, min_hole, tolerance
    process.mill.al6061_t6_3axis    tool.<id> rows, special.<id> rows, reach_tolerance, min_feature,
                                    chatter.ratio, setups.budget, tolerance
    process.pcb.fr4_1_6             thickness, outline and drill tolerance, for fit only
  Mold presets follow once a shop signs one; no mold preset ships in v0.
- Polymer and composite materials "polymer.pla", "polymer.pa12", "composite.cf_epoxy",
  with no strength rows until a strength rule reads them.
- Screws "screw.<size>x<length>_<head>_<grade>" and washers "washer.<size>_<form>": head
  diameter and height, bearing ring inner and outer diameter, thread length and minor
  diameter, the driver's tip diameter and the clearance its axis needs above the head.

Every value is a guess from typical datasheets and shop pages, tagged judged and owned by
petra-maintainers, until a maker signs its own preset (a `measured` override, or a preset
of its own). docs/parts.md lists the values and labels each one.
"""
from __future__ import annotations

from typing import Mapping

from .model import Material, Part, Process


def presets() -> Mapping[str, Process]:
    """Every parts process preset by id. Each passes domain.check_presets."""
    raise NotImplementedError


def polymers() -> Mapping[str, Material]:
    raise NotImplementedError


def fasteners() -> Mapping[str, Part]:
    """Screws by id, PartKind.SCREW, with the rows fit.grip, fit.driver and fit.seat read."""
    raise NotImplementedError


def washers() -> Mapping[str, Part]:
    """Washers by id, PartKind.WASHER, with their bearing ring."""
    raise NotImplementedError
