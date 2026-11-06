"""Steel deck ground truth, M3: the simple shear connections of the Companion to the AISC
Steel Construction Manual, v16.0, Vol. 1 Design Examples (AISC 2023), Part II.A, through
the connection elaborator.

Each example states its inputs as a design and the numbers the Companion prints. A
number is either reproduced to rounding, or bounded: the deck's method is a documented,
more conservative one, and its strength is at most the printed one.

A strength here is the reaction at which a check reaches utilisation 1: the load over the
utilisation. For a check whose demand is the reaction itself that is its available
strength; for the coped section it is phi Mn / e, the Companion's Rn = Mn / e; for a block
of an eccentric group it is what the whole group carries. Moments are compared in kip-in.

Inputs the Companion makes conservative in its tables are stated as the tables take them:
the 1/4 in beam underrun deducted from the beam web's end distance, and Tables 10-1c and
10-10c's top edge distance of 1-1/2 in. Rounding: the Companion sums per-bolt strengths
from tables printed to three figures, and Manual Tables 9-2a and 9-2b tabulate the coped
tee's moduli (with the fillets); those comparisons allow 1 %.

Bounded, not reproduced (the deck's v1.0 methods):
- Eccentric bolt groups: the elastic method against the weakest bolt, where the
  Companion uses the instantaneous-centre coefficient C (or C/n from Table 10-10b).
- Eccentric weld groups on a support (double angle welds B, a single angle's L weld, a
  tee flange): the elastic method on the weld lines alone, returns neglected, where the
  Companion uses the instantaneous-centre tables. A seat's welds are reproduced: Table
  10-6 is the elastic method with the seat bearing on the support.
- The extended plate's tmax: C' by the elastic method, where the Companion takes it from
  Table 7-7.

Neither: II.A-28A's support-side bolts. The Companion reads Table 10-11 at e = 2-1/2 in,
past the actual 1.90 in, and prints 55.0 / 36.5 kips; the elastic group at 1.90 in carries
57.0 / 38.0, so the printed value is not an upper bound and the test leaves it out.

Outside v1.0 or not modelled, so not here: axial force on a shear connection (II.A-1B,
2B, 11B, 17B, 19B; the deck reports the load path UNKNOWN), structural integrity checks
(II.A-1C, 12B, 17C), reinforced copes (II.A-6C, 6D), shared bolts (II.A-9), skewed
connections (II.A-10), splices (II.A-20, 21) and welded beam sides (II.A-3, 5, which
need the C-shaped weld group of M4). II.A-12A's seat strength reads Table 10-5's row
lb = 1-1/8 in where the beam needs only kdes = 1.03 in, and its printed bolt strength is
six bolts' for a four-bolt seat; II.A-13 and II.A-16 carry its seat checks.
"""
import unittest

from tests import steel_examples as ex
from tests.steel_examples import BOLTS


class IIA1A(ex.Example):
    """All-bolted double angle, W36x231 to a W14x90 column flange, 2L5x3-1/2x5/16 x 1'-11-1/2"
    (A572 Gr. 50), eight 3/4 in Group 120-N bolts at 3 in. Ru = 226, Ra = 151 kips."""

    tag, kind, loads = "II.A-1A", "double_angle", ("226", "151")
    body = ("  beam W36x231 grade steel.A992\n  support W14x90 flange grade steel.A992\n"
            "  angles L5x3_1_2x5_16 grade steel.A572_50 outstanding long\n" + BOLTS +
            "  rows 8\n  pitch 3 inch\n  edge_vertical 1.25 inch\n  beam_edge 1.625 inch\n  top 3 inch\n"
            "  beam_gauge 2.125 inch\n  setback 0.5 inch\n  support_side bolted\n  support_gauge 8 inch\n")
    printed = {
        ("shear_yield", "angles:"): ("441", "294"),
        ("shear_rupture", "angles:"): ("302", "201"),
        ("block_shear", "angles: block of 8 row(s) and 1 column(s)"): ("315", "210"),
        ("bolts", "beam side:"): ("282", "187"),
        ("bolts", "support side:"): ("282", "187"),
    }


class IIA2A(ex.Example):
    """Bolted/welded double angle, W36x231 to a W14x90 column flange, 2L4x3-1/2x3/8, eight
    bolts, 5/16 in E70 welds B. Ru = 226, Ra = 151 kips."""

    tag, kind, loads = "II.A-2A", "double_angle", ("226", "151")
    body = ("  beam W36x231 grade steel.A992\n  support W14x90 flange grade steel.A992\n"
            "  angles L4x3_1_2x3_8 grade steel.A572_50 outstanding long\n" + BOLTS +
            "  rows 8\n  pitch 3 inch\n  edge_vertical 1.25 inch\n  beam_edge 1.625 inch\n  top 3 inch\n"
            "  beam_gauge 2.125 inch\n  setback 0.5 inch\n  support_side welded\n"
            "  support_weld electrode.E70 size 0.3125 inch\n")
    printed = {
        ("bolts", "beam side:"): ("286", "190"),
        ("shear_yield", "angles:"): ("528", "352"),
        ("shear_rupture", "angles:"): ("363", "242"),
        ("block_shear", "angles: block of 8 row(s) and 1 column(s)"): ("380", "253"),
    }
    bounded = {("weld", "angles to support:"): ("318", "212")}


class IIA4(ex.Example):
    """All-bolted double angle in a coped beam: W18x50 (top cope 2 in by 4 in) to a W21x62
    girder web, 2L5x3-1/2x1/4 x 0'-8-1/2", three bolts. Ru = 60.0, Ra = 40.0 kips. The beam
    web's end distance is 1-5/8 in less the 1/4 in underrun, as the Companion's block shear."""

    tag, kind, loads = "II.A-4", "double_angle", ("60.0", "40.0")
    body = ("  beam W18x50 grade steel.A992\n  support W21x62 web grade steel.A992\n"
            "  angles L5x3_1_2x1_4 grade steel.A572_50 outstanding long\n" + BOLTS +
            "  rows 3\n  pitch 3 inch\n  edge_vertical 1.25 inch\n  beam_edge 1.375 inch\n  top 3.25 inch\n"
            "  beam_gauge 2.125 inch\n  setback 0.5 inch\n  cope top depth 2 inch length 4 inch\n"
            "  support_side bolted\n  support_gauge 6.25 inch\n")
    printed = {
        ("bolts", "beam side:"): ("73.5", "49.0", 0.01),
        ("bolts", "support side:"): ("96.4", "64.1", 0.01),
        ("cope_buckling", "beam web: flexural yielding and local buckling"): ("374", "249", 0.01),
        ("shear_yield", "beam web:"): ("170", "113"),
        ("block_shear", "beam web: block of 3 row(s) and 1 column(s)"): ("68.6", "45.8"),
        ("shear_rupture", "angles:"): ("85.9", "57.3"),
    }


class IIA8BeamA(ex.Example):
    """All-bolted double angles, beams to a W30x99 girder web: Beam A, W12x40 (top cope 2 in
    by 5 in), 2L5x3-1/2x1/4 x 0'-5-1/2", two bolts, top bolt 2 in below the cope. Ru = 25.0,
    Ra = 16.7 kips. Table 10-1c's block shear takes the top edge as 1-1/2 in and the end
    distance as 1-1/4 in; the second body states those."""

    tag, kind, loads = "II.A-8A", "double_angle", ("25.0", "16.7")
    beam, rows, cope = "W12x40", 2, "  cope top depth 2 inch length 5 inch\n"
    printed_bolts, printed_cope, printed_angles, printed_block = ("50.7", "33.8"), ("104", "68.9"), ("54.8", "36.6"), ("39.2", "26.1")

    def body_with(self, top: str, beam_edge: str) -> str:
        return (f"  beam {self.beam} grade steel.A992\n  support W30x99 web grade steel.A992\n"
                "  angles L5x3_1_2x1_4 grade steel.A572_50 outstanding long\n" + BOLTS +
                f"  rows {self.rows}\n  pitch 3 inch\n  edge_vertical 1.25 inch\n  beam_edge {beam_edge} inch\n"
                f"  top {top} inch\n  beam_gauge 2.125 inch\n  setback 0.5 inch\n" + self.cope +
                "  support_side bolted\n  support_gauge 6.25 inch\n")

    @property
    def body(self):
        return self.body_with("4", "1.625")

    @property
    def printed(self):
        return {
            ("bolts", "beam side:"): (*self.printed_bolts, 0.01),
            ("cope_buckling", "beam web: flexural yielding and local buckling"): (*self.printed_cope, 0.01),
            ("shear_rupture", "angles:"): self.printed_angles,
        }

    def test_block_shear_with_the_tables_edge_distances(self):
        body = self.body_with("3.5", "1.25")
        block = f"beam web: block of {self.rows} row(s) and 1 column(s)"
        for i, basis in enumerate(("lrfd", "asd")):
            self.near(self.strength(basis, "block_shear", block, body), self.printed_block[i], f"{self.tag} {basis}", 0.01)


class IIA8BeamB(IIA8BeamA):
    """Beam B, W21x50 (top cope 2 in by 5 in), 2L5x3-1/2x1/4 x 1'-2-1/2", five bolts.
    Ru = 110, Ra = 73.3 kips."""

    tag, loads = "II.A-8B", ("110", "73.3")
    beam, rows = "W21x50", 5
    printed_bolts, printed_cope, printed_angles, printed_block = ("158", "105"), ("383", "254"), ("148", "98.7"), ("121", "80.8")


# --- Copes ---------------------------------------------------------------------------------------

END_PLATE_HOST = ("  support W14x90 flange grade steel.A992\n  plate steel.A572_50 thickness 0.25 inch\n"
                  "  plate_width 6 inch\n" + BOLTS + "  rows 3\n  pitch 3 inch\n  edge_vertical 1.25 inch\n"
                  "  support_gauge 3.5 inch\n  weld electrode.E70 size 0.1875 inch sides 2\n  setback 0.5 inch\n")
"""A welded shear connection to host a cope: the Companion's II.A-6 and 7 give none."""


class IIA6A(ex.Example):
    """A W21x62 coped at the top flange, dc = 8 in, c = 9 in, setback 1/2 in (e = 9.50 in).
    Flexural yielding and local web buckling of the coped section."""

    tag, kind, loads = "II.A-6A", "shear_end_plate", ("135", "90.0")
    body = "  beam W21x62 grade steel.A992\n  cope top depth 8 inch length 9 inch\n" + END_PLATE_HOST
    printed = {("cope_buckling", "beam web: flexural yielding and local buckling"): ("116", "77.2", 0.01)}


class IIA6B(IIA6A):
    """Solution B: a W21x73 with the same cope."""

    tag = "II.A-6B"
    body = "  beam W21x73 grade steel.A992\n  cope top depth 8 inch length 9 inch\n" + END_PLATE_HOST
    printed = {("cope_buckling", "beam web: flexural yielding and local buckling"): ("150", "100", 0.01)}


class IIA7(ex.Example):
    """A W16x40 coped at both flanges, dct = 3-1/2 in, dcb = 2 in, c = 9-1/2 in, setback
    1/2 in (e = 10.0 in): Section F11 with Cb by Manual Eq 9-21, Mn = Mp = 421 kip-in."""

    tag, kind, loads = "II.A-7", "shear_end_plate", ("37.9", "25.2")
    body = ("  beam W16x40 grade steel.A992\n  cope both depth 3.5 inch length 9.5 inch bottom_depth 2 inch\n"
            + END_PLATE_HOST)
    printed = {("cope_buckling", "beam web: lateral-torsional buckling of the doubly coped web, Lb d/t^2 <="): ("37.9", "25.2")}


# --- Shear end plate -------------------------------------------------------------------------------

class IIA11A(ex.Example):
    """Shear end plate, W18x50 (top cope 2 in by 4 in) to a W21x62 girder web, PL1/4x6x0'-8-1/2"
    (A572 Gr. 50), six bolts, 3/16 in E70 fillets both sides of the web. Ru = 60.0, Ra =
    40.0 kips. The plate's shear rupture is Table 10-4a's (unrounded Anv); Part B rounds Anv
    to 2.94 in^2 and prints 86.3 / 57.5."""

    tag, kind, loads = "II.A-11A", "shear_end_plate", ("60.0", "40.0")
    body = ("  beam W18x50 grade steel.A992\n  support W21x62 web grade steel.A992\n"
            "  plate steel.A572_50 thickness 0.25 inch\n  plate_width 6 inch\n" + BOLTS +
            "  rows 3\n  pitch 3 inch\n  edge_vertical 1.25 inch\n  support_gauge 3.5 inch\n"
            "  weld electrode.E70 size 0.1875 inch sides 2\n  cope top depth 2 inch length 4 inch\n")
    printed = {
        ("shear_yield", "end plate:"): ("128", "85.3"),
        ("shear_rupture", "end plate:"): ("85.9", "57.3"),
        ("block_shear", "end plate: block of 3 row(s) and 1 column(s)"): ("93.8", "62.5"),
        ("bolts", "support side:"): ("96.4", "64.1", 0.01),
        ("weld", "end plate to beam web:"): ("67.9", "45.3"),
    }


# --- Seats -------------------------------------------------------------------------------------------

class IIA13(ex.Example):
    """Welded unstiffened seat, W21x62 on a W14x61 column flange, L8x4x5/8 x 0'-8" (A572
    Gr. 50), 5/16 in E70 welds, setback 3/4 in with the underrun. Ru = 54.8, Ra = 36.5 kips.
    The welds are Table 10-6's to its digits. Its seat row is lb = 1-1/8 in; the beam needs
    kdes = 1.12 in, so the seat's flexure moves by 1/2 %."""

    tag, kind, loads = "II.A-13", "seated", ("54.8", "36.5")
    body = ("  beam W21x62 grade steel.A992\n  support W14x61 flange grade steel.A992\n"
            "  angle L8x4x5_8 grade steel.A572_50 outstanding short\n  seat_length 8 inch\n  setback 0.75 inch\n"
            "  support_side welded\n  support_weld electrode.E70 size 0.3125 inch\n"
            "  top_angle L4x4x1_4 grade steel.A572_50 outstanding long\n")
    printed = {
        ("weld", "seat to support:"): ("66.7", "44.5"),
        ("seat_flexure", "seat angle:"): ("113", "74.9", 0.01),
    }


class IIA16(ex.Example):
    """Offset welded seat, W14x38 on a W12x65 column flange, L7x4x5/8 x 0'-6", 5/16 in E70
    welds. The Companion designs the seat for twice the heavier weld's share, 51.4 / 34.2
    kips, from Table 10-6: the seat's shear yielding governs it."""

    tag, kind, loads = "II.A-16", "seated", ("51.4", "34.2")
    body = ("  beam W14x38 grade steel.A992\n  support W12x65 flange grade steel.A992\n"
            "  angle L7x4x5_8 grade steel.A572_50 outstanding short\n  seat_length 6 inch\n  setback 0.75 inch\n"
            "  support_side welded\n  support_weld electrode.E70 size 0.3125 inch\n"
            "  top_angle L4x4x1_4 grade steel.A572_50 outstanding long\n")
    printed = {
        ("weld", "seat to support:"): ("53.4", "35.6"),
        ("shear_yield", "seat angle:"): ("113", "75.0"),
    }


# --- Single plates -------------------------------------------------------------------------------------

SHEAR_TAB = ("  plate steel.A572_50 thickness 0.25 inch\n" + BOLTS + "  rows 4\n  pitch 3 inch\n  edge_vertical 1.25 inch\n"
             "  plate_edge 1.5 inch\n  bolt_line 3 inch\n  weld electrode.E70 size 0.1875 inch sides 2\n  setback 0.5 inch\n"
             "  eccentricity 1.5 inch\n")
"""The conventional single plate of II.A-17A and 18, e = a/2 by Manual Table 10-9."""


class IIA17A(ex.Example):
    """Conventional single plate, W16x50 to a W14x90 column flange, PL1/4x4-1/2x0'-11-1/2"
    (A572 Gr. 50), four bolts, a = 3 in. Ru = 49.6, Ra = 33.0 kips."""

    tag, kind, loads = "II.A-17A", "shear_tab", ("49.6", "33.0")
    body = ("  beam W16x50 grade steel.A992\n  support W14x90 flange grade steel.A992\n" + SHEAR_TAB +
            "  beam_edge 2.5 inch\n  top 3 inch\n")
    printed = {
        ("shear_yield", "plate:"): ("86.4", "57.6"),
        ("shear_rupture", "plate:"): ("58.5", "39.0"),
        ("block_shear", "plate: block of 4 row(s) and 1 column(s)"): ("65.3", "43.6"),
    }
    bounded = {("bolts", "beam side:"): ("58.5", "38.9")}


class IIA18(ex.Example):
    """Conventional single plate, W18x35 (top cope 2 in by 4 in) to a W21x62 girder web,
    the plate of II.A-17A. Ru = 39.8, Ra = 26.5 kips. The beam web's block shear is Table
    10-10c's: top edge 1-1/2 in, end distance 2-1/4 in less the table's 1/4 in underrun."""

    tag, kind, loads = "II.A-18", "shear_tab", ("39.8", "26.5")
    body = ("  beam W18x35 grade steel.A992\n  support W21x62 web grade steel.A992\n" + SHEAR_TAB +
            "  beam_edge 2 inch\n  top 3.5 inch\n  cope top depth 2 inch length 4 inch\n")
    printed = {
        ("block_shear", "beam web: block of 4 row(s) and 1 column(s)"): ("88.2", "58.7"),
        ("shear_rupture", "plate:"): ("58.5", "39.0"),
    }
    bounded = {("bolts", "beam side:"): ("58.5", "38.9")}


class IIA19A(ex.Example):
    """Extended single plate, W16x36 to a W14x90 column web, PL1/2x12x1'-1-1/4" (A572 Gr. 50),
    two lines of four bolts at 3 in, a = 9 in to the first line, 5/16 in E70 fillets both
    sides. Ru = 36.0, Ra = 24.0 kips. Flexural rupture: Znet = 12.75 in^3; the Companion
    reads 12.8 from Table 15-2."""

    tag, kind, loads = "II.A-19A", "shear_tab", ("36.0", "24.0")
    body = ("  beam W16x36 grade steel.A992\n  support W14x90 web grade steel.A992\n"
            "  plate steel.A572_50 thickness 0.5 inch\n" + BOLTS + "  rows 4\n  columns 2\n  gauge 3 inch\n"
            "  pitch 3 inch\n  edge_vertical 1.5 inch\n  plate_edge 1.25 inch\n  bolt_line 9 inch\n  beam_edge 1.5 inch\n"
            "  top 3 inch\n  weld electrode.E70 size 0.3125 inch sides 2\n  form extended\n")
    moments = ("flexural_yield", "flexural_rupture", "plate_buckling")
    printed = {
        ("shear_yield", "plate:"): ("180", "120"),
        ("shear_rupture", "plate:"): ("125", "83.0"),
        ("block_shear", "plate: block of 4 row(s) and 2 column(s)"): ("145", "96.5"),
        ("flexural_yield", "plate: flexural yielding"): ("810", "539"),
        ("plate_buckling", "plate: lateral-torsional buckling, Lb d/t^2 <="): ("810", "539"),
        ("flexural_rupture", "plate:"): ("624", "416", 0.01),
    }
    bounded = {("bolts", "beam side:"): ("41.7", "27.7")}

    def test_shear_and_flexure_interaction(self):
        for basis, printed in (("lrfd", "0.200"), ("asd", "0.201")):
            found, _ = self.values(basis, "flexural_yield")
            check = next(v for v in found if v.what.startswith("plate: shear and flexural yielding interaction"))
            self.published(check.utilisation ** 2, printed, f"{basis} Eq 10-8")

    def test_tmax_is_bounded_by_the_tables(self):
        for basis in ("lrfd", "asd"):
            found, _ = self.values(basis, "extended_ductility")
            check = next(v for v in found if v.what.startswith("plate: no thicker than tmax"))
            self.assertLessEqual(check.available, 0.575)
            self.assertGreaterEqual(check.available, 0.5)


# --- Single angles -------------------------------------------------------------------------------------

class IIA28A(ex.Example):
    """All-bolted single angle, W18x35 (top cope 2 in by 4 in, setback 3/4 in) to a W21x62
    girder web, L4x3x3/8 x 0'-11-1/2" (A572 Gr. 50), the 3 in leg on the girder at a
    1-3/4 in gage, four bolts each leg. Ru = 39.8, Ra = 26.5 kips. Beam web block shear with
    lev = leh = 1-1/2 in (the underrun taken), as the Companion has it."""

    tag, kind, loads = "II.A-28A", "single_angle", ("39.8", "26.5")
    body = ("  beam W18x35 grade steel.A992\n  support W21x62 web grade steel.A992\n"
            "  angle L4x3x3_8 grade steel.A572_50 outstanding short\n" + BOLTS +
            "  rows 4\n  pitch 3 inch\n  edge_vertical 1.25 inch\n  beam_edge 1.5 inch\n  top 3.5 inch\n"
            "  beam_gauge 2.5 inch\n  setback 0.75 inch\n  cope top depth 2 inch length 4 inch\n"
            "  support_side bolted\n  support_gauge 1.75 inch\n")
    moments = ("flexural_yield", "flexural_rupture", "cope_buckling")
    printed = {
        ("shear_yield", "angle:"): ("129", "86.0"),
        ("shear_rupture", "angle:"): ("87.8", "58.5"),
        ("block_shear", "angle outstanding: block of 4 row(s) and 1 column(s)"): ("93.6", "62.4"),
        ("flexural_yield", "angle outstanding:"): ("558", "371"),
        ("flexural_rupture", "angle outstanding:"): ("413", "275"),
        ("cope_buckling", "beam web: flexural yielding and local buckling"): ("1,140", "760", 0.01),
        ("shear_yield", "beam web:"): ("141", "94.0"),
        ("block_shear", "beam web: block of 4 row(s) and 1 column(s)"): ("80.9", "53.9"),
    }
    # The support side's printed 55.0 / 36.5 reads Table 10-11 at e = 2-1/2 in, more than the
    # actual 1.90 in, so it bounds nothing; the deck's elastic group at 1.90 in gives 57.0 / 38.0.
    bounded = {("bolts", "beam side:"): ("68.5", "45.6")}


class IIA29(ex.Example):
    """Bolted/welded single angle, W16x50 to a W14x90 column flange, L4x3x3/8 x 0'-11-1/2",
    the 4 in leg bolted to the beam web (bolt line 2-3/4 in from the column), the 3 in leg
    welded with 3/16 in E70 fillets. Ru = 54.0, Ra = 36.0 kips."""

    tag, kind, loads = "II.A-29", "single_angle", ("54.0", "36.0")
    body = ("  beam W16x50 grade steel.A992\n  support W14x90 flange grade steel.A992\n"
            "  angle L4x3x3_8 grade steel.A572_50 outstanding short\n" + BOLTS +
            "  rows 4\n  pitch 3 inch\n  edge_vertical 1.25 inch\n  beam_edge 2.25 inch\n  top 3 inch\n"
            "  beam_gauge 2.75 inch\n  setback 0.5 inch\n  support_side welded\n"
            "  support_weld electrode.E70 size 0.1875 inch\n")
    printed = {
        ("shear_yield", "angle:"): ("129", "86.0"),
        ("shear_rupture", "angle:"): ("87.8", "58.5"),
        ("block_shear", "angle: block of 4 row(s) and 1 column(s)"): ("93.8", "62.5"),
    }
    bounded = {("bolts", "beam side:"): ("71.6", "47.6"), ("weld", "angle to support:"): ("56.7", "37.8")}


# --- Tees ----------------------------------------------------------------------------------------------

TEE = ("  beam W16x50 grade steel.A992\n  support W14x90 flange grade steel.A992\n  tee WT5x22_5 grade steel.A992\n"
       + BOLTS + "  rows 4\n  pitch 3 inch\n  edge_vertical 1.25 inch\n  bolt_line 3.8 inch\n  beam_edge 3.3 inch\n"
       "  top 3 inch\n  setback 0.5 inch\n")
TEE_STEM = {
    ("flexural_yield", "tee stem:"): ("521", "346"),
    ("flexural_rupture", "tee stem:"): ("386", "257"),
    ("shear_yield", "tee stem:"): ("121", "80.7"),
    ("shear_rupture", "tee stem:"): ("81.8", "54.5"),
    ("block_shear", "tee stem: block of 4 row(s) and 1 column(s)"): ("87.4", "58.2"),
}


class IIA30(ex.Example):
    """All-bolted tee, W16x50 to a W14x90 column flange, WT5x22.5 x 0'-11-1/2" (A992), four
    bolts through the stem at a = 3.80 in, eight through the flange at a 5-1/2 in gage.
    Ru = 36.0, Ra = 24.0 kips."""

    tag, kind, loads = "II.A-30", "shear_tee", ("36.0", "24.0")
    body = TEE + "  support_side bolted\n  support_gauge 5.5 inch\n"
    moments = ("flexural_yield", "flexural_rupture")
    printed = {**TEE_STEM, ("bolts", "support side:"): ("143", "95.2")}
    bounded = {("bolts", "beam side:"): ("43.5", "28.9")}


class IIA31(IIA30):
    """Bolted/welded tee: II.A-30's tee, its flange welded to the column flange with 1/4 in
    E70 fillets along both tips."""

    tag = "II.A-31"
    body = TEE + "  support_side welded\n  support_weld electrode.E70 size 0.25 inch\n"
    printed = TEE_STEM
    bounded = {("bolts", "beam side:"): ("43.5", "28.9"), ("weld", "tee flange to support:"): ("99.7", "66.5")}



if __name__ == "__main__":
    unittest.main()
