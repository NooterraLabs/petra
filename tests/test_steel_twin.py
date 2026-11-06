"""The twin elaborator against the deck (docs/steel_connections.md sections 8 and 9).

petra/models/steel/twin.py evaluates every steel limit state a second time, written from
the method statements in vocab.py and the sources without reading the deck's checks. For
every example design and the variants below, each mode the deck owes is compared: the
twin's governing utilisation against the largest of the deck's values that are not
excused. They agree when the relative difference is at most 1e-6.

A disagreement the sources do not settle in the deck's favour is listed in KNOWN with the
twin's reading. The test fails when a comparison outside KNOWN disagrees, and when a KNOWN
entry has come to agree (the entry is then stale and goes).
"""
from __future__ import annotations

import glob
import os
import unittest

from petra.lang import load_design, parse_design
from petra.models.steel import calc, domain, twin
from petra.registry import build_registry

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOLERANCE = 1e-6

_HEAD = 'petra 0\n\ndesign "steel-twin-{name}" {{\n  owner "s.engineer@example.org"\n}}\n\n'
_SIGN = '  signed "s.engineer@example.org" source "twin variant"\n}}\n'


def _variant(name: str, body: str, loads: str) -> str:
    return _HEAD.format(name=name) + body.strip() + "\n\nload gravity {\n" + loads.rstrip() + "\n" + _SIGN.format()


VARIANTS: dict[str, str] = {
    # a coped beam (top flange), three rows, short slots across the force, deformation not considered
    "tab_coped": _variant("tab_coped", """
shear_tab st2 {
  basis lrfd
  beam W16x26 grade steel.A992
  support W14x90 web grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads included
  holes plate ssl
  rows 3
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  bolt_line 3 inch
  beam_edge 1.75 inch
  top 3.5 inch
  setback 0.5 inch
  cope top depth 1.5 inch length 4 inch
  deformation not_considered
  weld electrode.E70 size 0.25 inch sides 2
}""", "  on st2 shear in [0 kip, 30 kip]"),
    # both flanges coped, allowable strength design
    "tab_both_asd": _variant("tab_both_asd", """
shear_tab st3 {
  basis asd
  beam W18x50 grade steel.A992
  support W14x90 web grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads excluded
  rows 4
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  bolt_line 3 inch
  beam_edge 1.75 inch
  top 3 inch
  setback 0.5 inch
  cope both depth 1.5 inch length 5 inch bottom_depth 2 inch
  weld electrode.E70 size 0.25 inch sides 2
}""", "  on st3 shear in [0 kip, 25 kip]"),
    # an extended single plate: two columns, a = 9 in (Companion II.A-19A geometry)
    "tab_extended": _variant("tab_extended", """
shear_tab st4 {
  basis lrfd
  beam W16x26 grade steel.A992
  support W14x90 web grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads included
  form extended
  rows 4
  columns 2
  gauge 3 inch
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  bolt_line 9 inch
  beam_edge 1.75 inch
  top 2.5 inch
  weld electrode.E70 size 0.25 inch sides 2
}""", "  on st4 shear in [0 kip, 30 kip]"),
    # slip-critical bolts in oversized holes in the plate
    "tab_slip": _variant("tab_slip", """
shear_tab st5 {
  basis lrfd
  beam W18x50 grade steel.A992
  support W14x90 flange grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.150 diameter 0.75 inch threads included joint slip_critical surface class_a
  holes plate ovs
  rows 4
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  bolt_line 3 inch
  beam_edge 1.75 inch
  top 3 inch
  weld electrode.E70 size 0.25 inch sides 2
}""", "  on st5 shear in [0 kip, 40 kip]"),
    # double angles welded to the support, beam coped
    "angles_welded": _variant("angles_welded", """
double_angle da2 {
  basis lrfd
  beam W18x50 grade steel.A992
  support W14x90 flange grade steel.A992
  angles L4x3_1_2x5_16 grade steel.A36 outstanding long
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows 3
  pitch 3 inch
  edge_vertical 1.25 inch
  beam_edge 1.75 inch
  top 3 inch
  beam_gauge 2 inch
  cope top depth 2 inch length 4 inch
  setback 0.5 inch
  support_side welded
  support_weld electrode.E70 size 0.25 inch sides 1
}""", "  on da2 shear in [0 kip, 45 kip]"),
    # double angles bolted to a girder web, slip-critical, ASD
    "angles_slip_asd": _variant("angles_slip_asd", """
double_angle da3 {
  basis asd
  beam W16x26 grade steel.A992
  support W18x50 web grade steel.A992
  angles L4x3_1_2x3_8 grade steel.A36 outstanding long
  bolts bolt_group.120 diameter 0.75 inch threads included joint slip_critical surface class_b
  holes beam ssl_parallel
  rows 3
  pitch 3 inch
  edge_vertical 1.25 inch
  beam_edge 1.75 inch
  top 2.5 inch
  beam_gauge 2 inch
  support_side bolted
  support_gauge 5.5 inch
}""", "  on da3 shear in [0 kip, 30 kip]"),
    # long slots across the force in the angles, Group 200 bolts with threads excluded
    "angles_long_slots": _variant("angles_long_slots", """
double_angle da4 {
  basis lrfd
  beam W18x50 grade steel.A992
  support W14x90 flange grade steel.A992
  angles L4x3_1_2x3_8 grade steel.A36 outstanding long
  bolts bolt_group.200 diameter 0.875 inch threads excluded
  holes angles lsl
  rows 4
  pitch 3 inch
  edge_vertical 1.5 inch
  beam_edge 1.75 inch
  top 3 inch
  beam_gauge 2.25 inch
  support_side bolted
  support_gauge 5.5 inch
  deformation not_considered
}""", "  on da4 shear in [0 kip, 90 kip]"),
    # one angle welded to the support
    "angle_welded": _variant("angle_welded", """
single_angle sa2 {
  basis lrfd
  beam W16x26 grade steel.A992
  support W14x90 flange grade steel.A992
  angle L4x4x3_8 grade steel.A36 outstanding long
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows 4
  pitch 3 inch
  edge_vertical 1.25 inch
  beam_edge 1.75 inch
  top 2.5 inch
  beam_gauge 2.5 inch
  support_side welded
  support_weld electrode.E70 size 0.25 inch sides 1
}""", "  on sa2 shear in [0 kip, 20 kip]"),
    # one angle on a coped beam, bolted both sides, slip-critical
    "angle_coped_slip": _variant("angle_coped_slip", """
single_angle sa3 {
  basis lrfd
  beam W18x50 grade steel.A992
  support W14x90 web grade steel.A992
  angle L4x4x3_8 grade steel.A36 outstanding long
  bolts bolt_group.120 diameter 0.75 inch threads included joint slip_critical surface class_a
  rows 4
  pitch 3 inch
  edge_vertical 1.25 inch
  beam_edge 1.75 inch
  top 3 inch
  beam_gauge 2.5 inch
  cope top depth 1.5 inch length 3.5 inch
  setback 0.5 inch
  support_side bolted
  support_gauge 2.5 inch
}""", "  on sa3 shear in [0 kip, 25 kip]"),
    # a tee welded to the support, beam coped at both flanges
    "tee_welded": _variant("tee_welded", """
shear_tee tee2 {
  basis lrfd
  beam W18x50 grade steel.A992
  support W14x90 flange grade steel.A992
  tee WT6x25 grade steel.A992
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows 3
  pitch 3 inch
  edge_vertical 1.25 inch
  bolt_line 3 inch
  beam_edge 1.75 inch
  top 3 inch
  cope both depth 1.5 inch length 4 inch
  setback 0.5 inch
  support_side welded
  support_weld electrode.E70 size 0.25 inch sides 1
}""", "  on tee2 shear in [0 kip, 35 kip]"),
    # a tee bolted to a girder web, three rows, slip-critical
    "tee_web": _variant("tee_web", """
shear_tee tee3 {
  basis lrfd
  beam W16x26 grade steel.A992
  support W18x50 web grade steel.A992
  tee WT6x25 grade steel.A992
  bolts bolt_group.120 diameter 0.75 inch threads included joint slip_critical surface class_b
  rows 3
  pitch 3 inch
  edge_vertical 1.25 inch
  bolt_line 3 inch
  beam_edge 1.75 inch
  top 2.5 inch
  support_side bolted
  support_gauge 5.5 inch
}""", "  on tee3 shear in [0 kip, 30 kip]"),
    # a seat welded to the support
    "seat_welded": _variant("seat_welded", """
seated seat2 {
  basis lrfd
  beam W16x26 grade steel.A992
  support W14x90 flange grade steel.A992
  angle L6x4x3_4 grade steel.A36 outstanding short
  seat_length 8 inch
  setback 0.5 inch
  support_side welded
  support_weld electrode.E70 size 0.3125 inch sides 2
  top_angle L4x4x1_4 grade steel.A36 outstanding long
}""", "  on seat2 shear in [0 kip, 30 kip]"),
    # an end plate on a coped beam, three rows, slip-critical, to a girder web
    "end_plate_coped": _variant("end_plate_coped", """
shear_end_plate ep2 {
  basis lrfd
  beam W16x26 grade steel.A992
  support W18x50 web grade steel.A992
  plate steel.A36 thickness 0.25 inch
  plate_width 7 inch
  bolts bolt_group.120 diameter 0.75 inch threads included joint slip_critical surface class_a
  rows 3
  pitch 3 inch
  edge_vertical 1.25 inch
  support_gauge 4.5 inch
  cope top depth 1.5 inch length 4 inch
  setback 0.25 inch
  weld electrode.E70 size 0.1875 inch sides 2
}""", "  on ep2 shear in [0 kip, 35 kip]"),
    # a shaped bolted bracket (sloped free edge), three rows
    "bolt_bracket_shaped": _variant("bolt_bracket_shaped", """
bolt_bracket bb2 {
  basis lrfd
  plate steel.A36 thickness 0.5 inch
  support W14x90 flange grade steel.A992
  bolts bolt_group.120 diameter 0.875 inch threads included
  rows 3
  columns 2
  pitch 3 inch
  gauge 3 inch
  eccentricity 9 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  free_edge 6 inch
}""", "  on bb2 shear in [0 kip, 25 kip]"),
    # a slip-critical bracket with slots parallel to the force, one filler, weathering steel
    "bolt_bracket_slip": _variant("bolt_bracket_slip", """
bolt_bracket bb3 {
  basis asd
  plate steel.A572_50 thickness 0.625 inch
  support W14x90 flange grade steel.A992
  bolts bolt_group.150 diameter 0.875 inch threads included joint slip_critical surface class_b fillers one
  holes plate ssl_parallel
  rows 5
  columns 2
  pitch 3 inch
  gauge 3.5 inch
  eccentricity 7 inch
  edge_vertical 1.5 inch
  plate_edge 1.75 inch
  weathering yes
}""", "  on bb3 shear in [0 kip, 30 kip]"),
    # a bolted seat with slip-critical bolts and two fillers
    "seat_slip": _variant("seat_slip", """
seated seat3 {
  basis lrfd
  beam W18x50 grade steel.A992
  support W14x90 flange grade steel.A992
  angle L6x4x3_4 grade steel.A36 outstanding short
  seat_length 8 inch
  setback 0.5 inch
  support_side bolted
  bolts bolt_group.120 diameter 0.875 inch threads included joint slip_critical surface class_a fillers two
  rows 2
  pitch 3 inch
  edge_vertical 1.5 inch
  support_gauge 5.5 inch
  top_angle L4x4x1_4 grade steel.A36 outstanding long
}""", "  on seat3 shear in [0 kip, 25 kip]"),
    # a shaped welded bracket square to the support
    "weld_bracket_shaped": _variant("weld_bracket_shaped", """
weld_bracket wb2 {
  basis lrfd
  plate steel.A36 thickness 0.5 inch
  support W14x90 flange grade steel.A992
  weld electrode.E70 size 0.3125 inch sides 2
  weld_length 15 inch
  eccentricity 8 inch
  free_edge 9 inch
}""", "  on wb2 shear in [0 kip, 40 kip]"),
    # a lapped bracket with a C-shaped fillet (returns), sides 1
    "weld_bracket_lapped": _variant("weld_bracket_lapped", """
weld_bracket wb3 {
  basis lrfd
  plate steel.A36 thickness 0.5 inch
  support W14x90 flange grade steel.A992
  weld electrode.E70 size 0.3125 inch sides 1
  weld_length 12 inch
  weld_return 4 inch
  eccentricity 10 inch
  free_edge 6 inch
}""", "  on wb3 shear in [0 kip, 30 kip]"),
    # a hanger in tension and shear on slip-critical Group 150 bolts
    "hanger_shear": _variant("hanger_shear", """
hanger h2 {
  basis lrfd
  tee WT9x25 grade steel.A992
  support W18x50 flange grade steel.A992
  bolts bolt_group.150 diameter 0.75 inch threads included joint slip_critical surface class_a
  rows 3
  pitch 3 inch
  tee_gauge 4 inch
  edge_vertical 1.5 inch
}""", "  on h2 tension in [0 kip, 60 kip]\n  on h2 shear in [0 kip, 20 kip]"),
    # a hanger in tension and shear, bearing-type, ASD
    "hanger_bearing_asd": _variant("hanger_bearing_asd", """
hanger h3 {
  basis asd
  tee WT9x25 grade steel.A992
  support W18x50 flange grade steel.A992
  bolts bolt_group.120 diameter 0.75 inch threads included joint pretensioned
  rows 2
  pitch 3 inch
  tee_gauge 4 inch
  edge_vertical 1.5 inch
}""", "  on h3 tension in [0 kip, 30 kip]\n  on h3 shear in [0 kip, 15 kip]"),
    # J10: a tensile flange force near the member end
    "flange_tensile_end": _variant("flange_tensile_end", """
flange_force ff2 {
  basis lrfd
  member W14x90 grade steel.A992
  bearing_length 6 inch
  location end
  distance 5 inch
  force_kind tensile
}""", "  on ff2 force in [0 kip, 120 kip]"),
    # J10: a pair of compressive forces at the end, with panel shear and axial load
    "flange_double_panel": _variant("flange_double_panel", """
flange_force ff3 {
  basis lrfd
  member W14x90 grade steel.A992
  bearing_length 1 inch
  location end
  distance 4 inch
  force_kind compressive
  pair double
}""", "  on ff3 force in [0 kip, 150 kip]\n  on ff3 panel_shear in [0 kip, 250 kip]\n  on ff3 axial in [0 kip, 700 kip]"),
    # J10: sidesway web buckling with the flange unrestrained, moment at yield
    "flange_sidesway": _variant("flange_sidesway", """
flange_force ff4 {
  basis asd
  member W18x50 grade steel.A992
  bearing_length 4 inch
  location interior
  force_kind compressive
  flange_restrained no
  unbraced_length 60 inch
  moment_at_force at_yield
}""", "  on ff4 force in [0 kip, 40 kip]"),
    # a stiffened seat, ASD
    "stiffened_asd": _variant("stiffened_asd", """
stiffened_seat ss2 {
  basis asd
  beam W18x50 grade steel.A992
  support W14x90 flange grade steel.A992
  plate steel.A36 thickness 0.375 inch
  stiffener steel.A36 thickness 0.375 inch
  stiffener_width 4 inch
  stiffener_length 10 inch
  setback 0.5 inch
  weld electrode.E70 size 0.25 inch sides 2
  top_angle L4x4x1_4 grade steel.A36 outstanding long
}""", "  on ss2 shear in [0 kip, 35 kip]"),
    # a stiffened seat whose welds are past 100 w, so J2.2b(d)'s end-loaded length governs
    "stiffened_long_weld": _variant("stiffened_long_weld", """
stiffened_seat ss3 {
  basis lrfd
  beam W21x44 grade steel.A992
  support W14x90 flange grade steel.A992
  plate steel.A36 thickness 0.375 inch
  stiffener steel.A36 thickness 0.5 inch
  stiffener_width 6 inch
  stiffener_length 24 inch
  setback 0.75 inch
  weld electrode.E70 size 0.1875 inch sides 2
  top_angle L4x4x1_4 grade steel.A36 outstanding long
}""", "  on ss3 shear in [0 kip, 40 kip]"),
    # The variants below reach branches the mutation test (tests/test_steel_mutation.py)
    # found no other design reaching.
    # welds past 300 w (24 in of 1/16 in fillet): J2.2b(d)'s effective length is 180 w
    "stiffened_longest_weld": _variant("stiffened_longest_weld", """
stiffened_seat ss4 {
  basis lrfd
  beam W21x44 grade steel.A992
  support W14x90 flange grade steel.A992
  plate steel.A36 thickness 0.375 inch
  stiffener steel.A36 thickness 0.5 inch
  stiffener_width 6 inch
  stiffener_length 24 inch
  setback 0.75 inch
  weld electrode.E70 size 0.0625 inch sides 2
  top_angle L4x4x1_4 grade steel.A36 outstanding long
}""", "  on ss4 shear in [0 kip, 20 kip]"),
    # a hanger on slip-critical bolts, ASD: its tension reduces the slip resistance (Eq J3-5b)
    "hanger_slip_asd": _variant("hanger_slip_asd", """
hanger h4 {
  basis asd
  tee WT9x25 grade steel.A992
  support W18x50 flange grade steel.A992
  bolts bolt_group.150 diameter 0.75 inch threads included joint slip_critical surface class_a
  rows 3
  pitch 3 inch
  tee_gauge 4 inch
  edge_vertical 1.5 inch
}""", "  on h4 tension in [0 kip, 40 kip]\n  on h4 shear in [0 kip, 12 kip]"),
    # J10.4 applies, r = 1.6, the flange restrained; ASD, with panel shear and axial load
    "flange_sidesway_restrained_asd": _variant("flange_sidesway_restrained_asd", """
flange_force ff5 {
  basis asd
  member W14x90 grade steel.A992
  bearing_length 4 inch
  location interior
  force_kind compressive
  flange_restrained yes
  unbraced_length 240 inch
  moment_at_force below_yield
}""", "  on ff5 force in [0 kip, 60 kip]\n  on ff5 panel_shear in [0 kip, 150 kip]\n  on ff5 axial in [0 kip, 500 kip]"),
    # J10.4 with the flange unrestrained: it applies at r = 1.6 and not at r = 2.6
    "flange_free_applies": _variant("flange_free_applies", """
flange_force ff6 {
  basis lrfd
  member W14x90 grade steel.A992
  bearing_length 4 inch
  location interior
  force_kind compressive
  flange_restrained no
  unbraced_length 240 inch
  moment_at_force below_yield
}""", "  on ff6 force in [0 kip, 60 kip]"),
    "flange_free_excused": _variant("flange_free_excused", """
flange_force ff7 {
  basis lrfd
  member W14x90 grade steel.A992
  bearing_length 4 inch
  location interior
  force_kind compressive
  flange_restrained no
  unbraced_length 144 inch
  moment_at_force below_yield
}""", "  on ff7 force in [0 kip, 60 kip]"),
    # a long double cope on a thin web: F11-4's elastic buckling governs
    "tab_double_cope_slender": _variant("tab_double_cope_slender", """
shear_tab st5 {
  basis lrfd
  beam W18x35 grade steel.A992
  support W14x90 web grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows 3
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  bolt_line 3 inch
  beam_edge 1.75 inch
  top 4 inch
  setback 0.5 inch
  cope both depth 2 inch length 15 inch bottom_depth 2 inch
  weld electrode.E70 size 0.25 inch sides 2
}""", "  on st5 shear in [0 kip, 10 kip]"),
    # a thin shaped bracket with a long free edge: lambda past 1.41, Q = 1.30 / lambda^2
    "bolt_bracket_slender": _variant("bolt_bracket_slender", """
bolt_bracket bb4 {
  basis lrfd
  plate steel.A36 thickness 0.375 inch
  support W14x90 flange grade steel.A992
  bolts bolt_group.120 diameter 0.875 inch threads included
  rows 6
  columns 2
  pitch 3 inch
  gauge 3 inch
  eccentricity 12 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  free_edge 18 inch
}""", "  on bb4 shear in [0 kip, 10 kip]"),
    # a conventional tab whose thickness, not its weld, governs Manual Part 10's ductility rules
    "tab_ductile_plate": _variant("tab_ductile_plate", """
shear_tab st6 {
  basis lrfd
  beam W21x62 grade steel.A992
  support W14x90 web grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows 4
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  bolt_line 3 inch
  beam_edge 1.75 inch
  top 3 inch
  weld electrode.E70 size 0.3125 inch sides 2
}""", "  on st6 shear in [0 kip, 40 kip]"),
    # the same tab with 2 in edges, so the plate's thickness alone governs Manual Part 10's
    # ductility rules, then its weld (a 1/4 in fillet on a 3/8 in plate)
    "tab_ductile_thickness": _variant("tab_ductile_thickness", """
shear_tab st7 {
  basis lrfd
  beam W21x62 grade steel.A992
  support W14x90 web grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows 4
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 2 inch
  bolt_line 3 inch
  beam_edge 2 inch
  top 3 inch
  weld electrode.E70 size 0.3125 inch sides 2
}""", "  on st7 shear in [0 kip, 40 kip]"),
    "tab_ductile_weld": _variant("tab_ductile_weld", """
shear_tab st8 {
  basis lrfd
  beam W21x62 grade steel.A992
  support W14x90 web grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows 4
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 2 inch
  bolt_line 3 inch
  beam_edge 2 inch
  top 3 inch
  weld electrode.E70 size 0.25 inch sides 2
}""", "  on st8 shear in [0 kip, 40 kip]"),
    # a Grade 50 stiffener near its width-to-thickness limit, thicker than the beam web needs
    "stiffened_wide_stiffener": _variant("stiffened_wide_stiffener", """
stiffened_seat ss5 {
  basis lrfd
  beam W18x35 grade steel.A992
  support W14x90 flange grade steel.A992
  plate steel.A36 thickness 0.375 inch
  stiffener steel.A572_50 thickness 0.5 inch
  stiffener_width 6 inch
  stiffener_length 12 inch
  setback 0.5 inch
  weld electrode.E70 size 0.25 inch sides 2
  top_angle L4x4x1_4 grade steel.A36 outstanding long
}""", "  on ss5 shear in [0 kip, 30 kip]"),
    # a hanger in tension and shear, so prying works from F'nt Ab (Companion II.A-1B)
    "hanger_prying_shear": _variant("hanger_prying_shear", """
hanger h9 {
  basis lrfd
  tee WT7x45 grade steel.A992
  support W14x90 flange grade steel.A992
  bolts bolt_group.120 diameter 0.75 inch threads included joint pretensioned
  rows 2
  pitch 3 inch
  tee_gauge 4 inch
  edge_vertical 1.5 inch
}""", "  on h9 tension in [0 kip, 78 kip]\n  on h9 shear in [0 kip, 44 kip]"),
    # declared fillers in a snug shear tab: J5.2(a)'s 0.85 on the bolts' shear strength
    "tab_fillers": _variant("tab_fillers", """
shear_tab st10 {
  basis lrfd
  beam W16x26 grade steel.A992
  support W14x90 web grade steel.A992
  plate steel.A36 thickness 0.375 inch
  bolts bolt_group.120 diameter 0.75 inch threads included fillers one
  rows 3
  pitch 3 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
  bolt_line 3 inch
  beam_edge 1.75 inch
  top 3 inch
  weld electrode.E70 size 0.25 inch sides 2
}""", "  on st10 shear in [0 kip, 40 kip]"),
    # a wide, thin tee flange that prying bends: a > 1.25 b, s/2 > 1.75 b, and Q < 1
    "hanger_thin_flange": _variant("hanger_thin_flange", """
hanger h5 {
  basis lrfd
  tee WT12x27_5 grade steel.A992
  support W14x90 flange grade steel.A992
  bolts bolt_group.120 diameter 0.75 inch threads included joint pretensioned
  rows 2
  pitch 6 inch
  tee_gauge 3 inch
  edge_vertical 1.5 inch
}""", "  on h5 tension in [0 kip, 20 kip]"),
    # a thin rectangular bracket far out: Section F11's elastic buckling (Lb d/t^2 = 4320 past
    # 1.9 E/Fy) governs over yielding, Cb = 1 for the cantilever (F1(c)); the red team's case
    "bracket_rectangular_slender": _variant("bracket_rectangular_slender", """
bolt_bracket bb5 {
  basis lrfd
  plate steel.A36 thickness 0.25 inch
  support W14x90 flange grade steel.A992
  bolts bolt_group.120 diameter 0.75 inch threads included
  rows 6
  columns 2
  pitch 3 inch
  gauge 3 inch
  eccentricity 16.5 inch
  edge_vertical 1.5 inch
  plate_edge 1.5 inch
}""", "  on bb5 shear in [0 kip, 10 kip]"),
    # a rectangular welded bracket square to the support: Eq F11-3 (inelastic), below Mp
    "weld_bracket_rectangular": _variant("weld_bracket_rectangular", """
weld_bracket wb5 {
  basis asd
  plate steel.A36 thickness 0.375 inch
  support W14x90 flange grade steel.A992
  weld electrode.E70 size 0.25 inch sides 2
  weld_length 12 inch
  eccentricity 10 inch
}""", "  on wb5 shear in [0 kip, 8 kip]"),
    # a rectangular lapped bracket: Lb is the arm past the returns, e - kl
    "weld_bracket_rectangular_lapped": _variant("weld_bracket_rectangular_lapped", """
weld_bracket wb6 {
  basis lrfd
  plate steel.A36 thickness 0.375 inch
  support W14x90 flange grade steel.A992
  weld electrode.E70 size 0.25 inch sides 1
  weld_length 10 inch
  weld_return 3 inch
  eccentricity 12 inch
}""", "  on wb6 shear in [0 kip, 10 kip]"),
}


# Settled, and no longer listed: the twin's first readings disagreed with the deck in nine
# places. The Companion settled four for the twin and the deck was fixed (Znet's odd-row
# term, II.A-17B and 19A; a welded beam web's shear plane d less the copes, II.A-5; a single
# angle's weld eccentricity leg + tw/2, II.A-29; a tee's flange-tip welds as Table 10-2
# welds B at bf/2, II.A-31). It settled two for the deck, whose method statements were then
# completed and the twin re-read from them (seat flexure at the middle of the required
# bearing, Table 10-5 and II.A-12A; the Manual's seat-weld form, Table 10-6 and II.A-16).
# Two statements promised what the deck does not do, and were narrowed: joint_type also
# named the slip-critical hole rule, which is hole_use's (J3.3), and flange_local_bending
# named J10.1's narrow-load exemption, which needs a width across the flange the grammar
# does not declare (the deck checks it always, the conservative reading).
KNOWN: dict[tuple[str, str, str], str] = {}
"""(design, connection, mode) -> the twin's reading where it disagrees with the deck."""


def _designs(registry):
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "examples", "steel", "*.petra"))):
        out.append((os.path.basename(path)[:-5], load_design(path, registry)))
    for name, text in VARIANTS.items():
        out.append((name, parse_design(text, f"<twin:{name}>", registry)))
    return out


def compare(registry):
    """Every (design, conn, mode) -> (twin u, deck u), over all designs and cases."""
    rows: dict[tuple[str, str, str], tuple[float, float]] = {}
    for label, design in _designs(registry):
        for name in design.components:
            conn = calc.connection(design, name, registry)
            owed = [m for m in domain.required(conn, design) if m not in twin.UNCHECKED]
            for case in design.loads:
                mine = twin.utilisations(conn, design, registry, case)
                for mode in owed:
                    deck = max((v.utilisation for v in calc.values(conn, design, registry, mode, case)
                                if not v.excused), default=0.0)
                    key = (label, name, mode)
                    t = mine.get(mode, float("nan"))
                    old = rows.get(key)
                    rows[key] = (t, deck) if old is None or _differs(t, deck) else old
    return rows


def _differs(t: float, d: float) -> bool:
    if t == d:
        return False
    if t != t or d != d:
        return True
    return abs(t - d) > TOLERANCE * max(abs(t), abs(d))


class TwinAgreesWithTheDeck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = build_registry()
        cls.rows = compare(cls.registry)

    def test_the_twin_owes_what_the_deck_owes(self):
        for label, design in _designs(self.registry):
            for name in design.components:
                conn = calc.connection(design, name, self.registry)
                with self.subTest(design=label, conn=name):
                    self.assertEqual(set(twin.modes_owed(conn, design)), set(domain.required(conn, design)))

    def test_every_comparison_outside_known_agrees(self):
        for key, (t, d) in sorted(self.rows.items()):
            if key in KNOWN:
                continue
            with self.subTest(design=key[0], conn=key[1], mode=key[2]):
                self.assertFalse(_differs(t, d), f"twin {t!r} deck {d!r}")

    def test_every_known_disagreement_still_disagrees(self):
        for key in KNOWN:
            with self.subTest(design=key[0], conn=key[1], mode=key[2]):
                self.assertIn(key, self.rows)
                t, d = self.rows[key]
                self.assertTrue(_differs(t, d), f"twin and deck now agree at {t!r}; drop the KNOWN entry")

    def test_every_kind_is_compared(self):
        kinds = {calc.connection(d, n, self.registry).kind for _, d in _designs(self.registry) for n in d.components}
        self.assertEqual(kinds, set(twin.KINDS))


if __name__ == "__main__":
    unittest.main()
