"""The strength limit states each connection kind carries, assembled from the clauses in checks.

Each kind function reads its component's lines and returns the checks against one demand, the
largest magnitude the load ranges give. KINDS maps a kind's name to its function and to the load
field that carries its demand.
"""

import math
from dataclasses import dataclass, field
from fractions import Fraction as F

from twin import checks as ck
from twin.coped import OutOfRange, double_cope_moment, top_cope_moment
from twin.groups import bolt_coefficient, bolt_grid, weld_strength

UNDERRUN = F(1, 4)  # Manual Part 10 beam-length underrun, as the Companion examples apply it
ALLOWANCE = F(1, 16)  # B4.3b, added to a hole's nominal dimension for net areas
SPEC = "AISC 360-22"
MANUAL = "AISC Manual 16th ed."


@dataclass(frozen=True)
class Ply:
    """A connected element at a line of bolts. edge is the distance from the end bolt toward which
    the bolts push this ply to that edge; None where the ply runs on (a support, an uncoped web)."""

    name: str
    t: F
    fu: F
    hole: object
    edge: object = None
    edge_end: str = "bottom"


@dataclass(frozen=True)
class BoltLine:
    label: str
    rows: int
    pitch: F
    per_row: int
    planes: int
    plies: tuple
    coefficient: F = F(1)
    eccentricity_note: str = ""


@dataclass
class Out:
    demand: F
    lrfd: bool
    checks: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    unsupported: list = field(default_factory=list)

    def add(self, name, mode, element, clause, nominal, factor, demand=None, unit="kip", note=""):
        self.checks.append(
            ck.Check(name, mode, element, clause, F(nominal), factor,
                     self.demand if demand is None else demand, unit, note)
        )


# Bolt lines: J3.7 shear, J3.11a bearing and tearout, the J3.7 User Note sum, J3.9 slip


def _ply_nominal(ply, bolts, i, line, deformation):
    lsl = ply.hole.long_slot_across_force
    bear = ck.bearing(bolts.d, ply.t, ply.fu, deformation, lsl)
    at_edge = ply.edge is not None and (
        (ply.edge_end == "bottom" and i == line.rows - 1) or (ply.edge_end == "top" and i == 0)
    )
    if at_edge:
        lc = ply.edge - ply.hole.along / 2
    elif line.rows > 1:
        lc = line.pitch - ply.hole.along
    else:
        return bear
    return min(bear, ck.tearout(lc, ply.t, ply.fu, deformation, lsl))


def bolt_line(out, line, bolts, deformation=True):
    rs = ck.bolt_shear(bolts.fnv, bolts.d, line.planes)
    n = line.rows * line.per_row
    k = line.coefficient
    ecc = f"; {line.eccentricity_note}" if line.eccentricity_note else ""
    out.add(f"bolt shear, {line.label}", "bolts", "bolts", f"{SPEC} J3.7, Eq. J3-1{ecc}",
            k * n * rs, "J3.6")
    effective = F(0)
    per_ply = {ply.name: F(0) for _, ply in line.plies}
    for i in range(line.rows):
        values = [count * _ply_nominal(ply, bolts, i, line, deformation) for count, ply in line.plies]
        effective += line.per_row * min([rs] + values)
        for (_, ply), v in zip(line.plies, values):
            per_ply[ply.name] += line.per_row * v
    eqs = "Eqs. J3-6a and J3-6c" if deformation else "Eqs. J3-6b and J3-6d"
    for name, total in per_ply.items():
        out.add(f"bearing and tearout, {name}, {line.label}", "bearing", name,
                f"{SPEC} J3.11a, {eqs}{ecc}", k * total, "J3.11")
    out.add(f"bolt group effective strength, {line.label}", "bolts", "bolts",
            f"{SPEC} J3.7 User Note with J3.11a{ecc}", k * effective, "J3.6")
    if bolts.joint == "slip_critical":
        mu = F(1, 2) if bolts.surface == "class_b" else F(3, 10)
        kinds = {ply.hole.kind for _, ply in line.plies}
        factor = "slip_lsl" if kinds & {"lsl", "lsl_parallel"} else (
            "slip_ovs" if kinds & {"ovs", "ssl_parallel"} else "slip_std")
        out.add(f"slip, {line.label}", "slip", "bolts", f"{SPEC} J3.9, Eq. J3-4{ecc}",
                k * n * ck.slip(mu, bolts.pretension, line.planes, bolts.fillers), factor)


def eccentric(points, ex):
    c = F(bolt_coefficient(points, float(ex)))
    note = f"{MANUAL} Part 7 instantaneous center, C = {float(c):.4g} at e = {float(ex):.4g} in."
    return c / len(points), note


def column(rows, pitch):
    return bolt_grid(rows, 1, float(pitch), 0.0)


# Elements, J4


def shear_element(out, label, grade, t, length, n_holes, hole, planes=1):
    out.add(f"shear yielding, {label}", "shear_yield", label, f"{SPEC} J4.2(a), Eq. J4-3",
            planes * ck.shear_yield(grade.fy, length * t), "J4.2a")
    anv = (length - n_holes * (hole.along + ALLOWANCE)) * t
    out.add(f"shear rupture, {label}", "shear_rupture", label, f"{SPEC} J4.2(b), Eq. J4-4",
            planes * ck.shear_rupture(grade.fu, anv), "J4.2b")


def block_shear(out, label, grade, t, lev, pitch, leh, rows, hole, blocks=1):
    """One or more blocks along a single bolt column, torn toward the edge the bolts push: shear
    from that edge through the k-th bolt, tension from there out to the edge across the force,
    Ubs = 1. J4.3 holds on every path, so besides the whole column (k = rows) the twin checks the
    block through the k rows nearest the edge with the least strength per row, against those
    rows' equal share k / rows of the demand."""
    clause = f"{SPEC} J4.3, Eq. J4-5, Ubs = 1"
    ant = (leh - (hole.across + ALLOWANCE) / 2) * t

    def strength(k):
        agv = (lev + (k - 1) * pitch) * t
        anv = agv - (k - F(1, 2)) * (hole.along + ALLOWANCE) * t
        return blocks * ck.block_shear(grade.fy, grade.fu, agv, anv, ant)

    out.add(f"block shear, {label}", "block_shear", label, clause, strength(rows), "J4.3")
    if rows > 1:
        k = min(range(1, rows), key=lambda k: strength(k) / k)
        out.add(f"block shear, {label}, partial path", "block_shear", label,
                f"{clause}, through the {k} of {rows} rows nearest the edge", strength(k), "J4.3",
                out.demand * k / rows, note=f"demand is the share of {k} of {rows} rows")


def flexure_element(out, label, grade, t, depth, hole, offsets, moment):
    out.add(f"flexural yielding, {label}", "flexural_yield", label,
            f"{MANUAL} Part 9, Mn = Fy Z with Z = t d^2 / 4 (F11 with yielding governing)",
            grade.fy * ck.plastic_modulus(t, depth), "flexure", moment, "kip-in")
    znet = ck.net_plastic_modulus(t, depth, hole.along + ALLOWANCE, offsets)
    out.add(f"flexural rupture, {label}", "flexural_rupture", label, f"{MANUAL} Eq. 9-8, Mn = Fu Znet",
            grade.fu * znet, "flexural_rupture", moment, "kip-in")


def hole_offsets(rows, pitch):
    mid = F(rows - 1, 2) * pitch
    return [i * pitch - mid for i in range(rows)]


# Shared readers


def element_length(rows, pitch, lev):
    return 2 * lev + (rows - 1) * pitch


def support_ply(lines):
    shape, face, grade = lines.support()
    t = shape.tf if face == "flange" else shape.tw
    return shape, face, grade, t


def beam_web_ply(lines, beam, grade, hole):
    """The bolts push the beam web up. Uncoped, the web runs on into the flange; with a top
    cope the edge is the cope's horizontal cut."""
    cope = lines.cope()
    edge = None
    if cope is not None:
        edge = lines.length("top") - cope.depth
    return Ply("beam web", beam.tw, grade.fu, hole, edge, "top")


def cope_checks(out, lines, beam, grade, rows=None, pitch=None, hole=None):
    """Limit states of a coped beam end. rows, pitch and hole describe the bolts in the web; None
    means the connection is welded to the web."""
    cope = lines.cope()
    if cope is None:
        return
    hc = beam.d - cope.depth - cope.bottom_depth
    label = "beam web, coped section"
    setback = lines.optional_length("setback")
    if setback is None:
        out.unsupported.append("coped flexure: no setback on the card, so e = c + setback is unknown")
    else:
        e = cope.length + setback
        try:
            if cope.flanges == "top":
                mn, how = top_cope_moment(beam, grade.fy, cope.depth, cope.length)
                clause = f"{MANUAL} Part 9, Eqs. 9-9 and 9-14 to 9-20a; {how}"
            else:
                mn, how = double_cope_moment(beam, grade.fy, cope.depth, cope.bottom_depth, cope.length)
                clause = f"{SPEC} {how}, Lb = c and d = hc; Cb by {MANUAL} Eq. 9-21"
            out.add("coped section flexure", "cope_buckling", label, clause, mn / e, "flexure",
                    note=f"Rn = Mn / e (Manual Eq. 9-9) with e = c + setback = {float(e):.4g} in.")
        except OutOfRange as err:
            out.unsupported.append(f"coped flexure: {err}")
    out.add("shear yielding, coped section", "shear_yield", label, f"{SPEC} J4.2(a), Eq. J4-3 on hc tw",
            ck.shear_yield(grade.fy, hc * beam.tw), "J4.2a")
    if rows is None:
        out.add("shear rupture, coped section", "shear_rupture", label,
                f"{SPEC} J4.2(b), Eq. J4-4 on hc tw, welded so no holes (Example II.A-6)",
                ck.shear_rupture(grade.fu, hc * beam.tw), "J4.2b")
        return
    if cope.flanges == "both":
        anv = (hc - rows * (hole.along + ALLOWANCE)) * beam.tw
        out.add("shear rupture, coped section", "shear_rupture", label,
                f"{SPEC} J4.2(b), Eq. J4-4 on hc tw less the holes",
                ck.shear_rupture(grade.fu, anv), "J4.2b")
    else:
        out.notes.append("top cope only: web shear rupture does not apply, block shear covers it (Example II.A-4)")
    lev = lines.length("top") - cope.depth
    leh = lines.optional_length("beam_edge")
    if leh is None:
        out.unsupported.append("coped web block shear: no beam_edge on the card")
        return
    block_shear(out, "beam web", grade, beam.tw, lev, pitch, leh - UNDERRUN, rows, hole)


# Kinds


def shear_tab(lines, out, demands):
    beam, beam_grade = lines.member("beam")
    _, face, sup_grade, t_sup = support_ply(lines)
    grade, tp = lines.plate("plate")
    bolts = lines.bolts()
    n, s = lines.count("rows"), lines.length("pitch")
    lev, leh = lines.length("edge_vertical"), lines.length("plate_edge")
    a = lines.length("bolt_line")
    weld = lines.weld("weld")
    deformation = lines.word("deformation", "considered") == "considered"
    if lines.word("form", "conventional") != "conventional" or lines.count("columns", 1) != 1:
        out.unsupported.append("extended or multi-column single plates are not modeled")
        return
    holes = lines.holes(bolts.d, ["plate", "beam"])
    length = element_length(n, s, lev)
    e = lines.optional_length("eccentricity")
    e = a / 2 if e is None else e
    k, note = eccentric(column(n, s), e)
    out.notes.append("bolt group eccentricity e = a/2 for the conventional configuration "
                     "(Manual Table 10-9 as Example II.A-17A applies it)")
    plate = Ply("plate", tp, grade.fu, holes["plate"], lev, "bottom")
    web = beam_web_ply(lines, beam, beam_grade, holes["beam"])
    bolt_line(out, BoltLine("beam side", n, s, 1, 1, ((1, plate), (1, web)), k, note), bolts, deformation)
    shear_element(out, "plate", grade, tp, length, n, holes["plate"])
    block_shear(out, "plate", grade, tp, lev, s, leh, n, holes["plate"])
    out.add("fillet weld, plate to support", "weld", "weld", f"{SPEC} J2.4, Eq. J2-4, kds = 1.0",
            weld.sides * ck.fillet_weld(weld.fexx, weld.w, length), "J2.4")
    out.add(f"support {face} shear rupture at the weld", "weld_base_metal", f"support {face}",
            f"{SPEC} J4.2(b), Eq. J4-4 on one plane per fillet (Manual Eq. 9-6 form)",
            weld.sides * ck.shear_rupture(sup_grade.fu, t_sup * length), "J4.2b")
    cope_checks(out, lines, beam, beam_grade, n, s, holes["beam"])


def _angle_legs(shape, outstanding):
    """Returns (leg on the beam web, outstanding leg)."""
    if outstanding == "long":
        return shape.short_leg, shape.long_leg
    return shape.long_leg, shape.short_leg


def double_angle(lines, out, demands):
    beam, beam_grade = lines.member("beam")
    _, face, sup_grade, t_sup = support_ply(lines)
    shape, grade, outstanding = lines.angle("angles")
    bolts = lines.bolts()
    n, s, lev = lines.count("rows"), lines.length("pitch"), lines.length("edge_vertical")
    deformation = lines.word("deformation", "considered") == "considered"
    holes = lines.holes(bolts.d, ["angles", "beam", "support"])
    t = shape.t
    length = element_length(n, s, lev)
    beam_leg, out_leg = _angle_legs(shape, outstanding)
    beam_gauge = lines.length("beam_gauge")
    angle_beam = Ply("angles", t, grade.fu, holes["angles"], lev, "bottom")
    web = beam_web_ply(lines, beam, beam_grade, holes["beam"])
    bolt_line(out, BoltLine("beam side", n, s, 1, 2, ((2, angle_beam), (1, web))), bolts, deformation)
    shear_element(out, "angles", grade, t, length, n, holes["angles"], planes=2)
    block_shear(out, "angles, beam leg", grade, t, lev, s, beam_leg - beam_gauge, n,
                holes["angles"], blocks=2)
    side = lines.word("support_side")
    if side == "bolted":
        g_out = (lines.length("support_gauge") - beam.tw) / 2
        angle_sup = Ply("angles", t, grade.fu, holes["angles"], lev, "top")
        sup = Ply(f"support {face}", t_sup, sup_grade.fu, holes["support"])
        bolt_line(out, BoltLine("support side", n, s, 2, 1, ((1, angle_sup), (1, sup))), bolts, deformation)
        block_shear(out, "angles, outstanding leg", grade, t, lev, s, out_leg - g_out, n,
                    holes["angles"], blocks=2)
    else:
        out.unsupported.append("welded support side: the eccentric angle-to-support weld is not modeled")
    cope_checks(out, lines, beam, beam_grade, n, s, holes["beam"])


def shear_end_plate(lines, out, demands):
    beam, beam_grade = lines.member("beam")
    _, face, sup_grade, t_sup = support_ply(lines)
    grade, tp = lines.plate("plate")
    width = lines.length("plate_width")
    bolts = lines.bolts()
    n, s, lev = lines.count("rows"), lines.length("pitch"), lines.length("edge_vertical")
    gauge = lines.length("support_gauge")
    weld = lines.weld("weld")
    deformation = lines.word("deformation", "considered") == "considered"
    holes = lines.holes(bolts.d, ["plate", "support"])
    length = element_length(n, s, lev)
    plate = Ply("plate", tp, grade.fu, holes["plate"], lev, "top")
    sup = Ply(f"support {face}", t_sup, sup_grade.fu, holes["support"])
    bolt_line(out, BoltLine("support side", n, s, 2, 1, ((1, plate), (1, sup))), bolts, deformation)
    shear_element(out, "plate", grade, tp, length, n, holes["plate"], planes=2)
    block_shear(out, "plate", grade, tp, lev, s, (width - gauge) / 2, n, holes["plate"], blocks=2)
    lw = length - 2 * weld.w
    out.add("fillet weld, plate to beam web", "weld", "weld",
            f"{SPEC} J2.4, Eq. J2-4, kds = 1.0, length less twice the weld size",
            weld.sides * ck.fillet_weld(weld.fexx, weld.w, lw), "J2.4")
    out.add("beam web shear yielding at the weld", "weld_base_metal", "beam web",
            f"{SPEC} J4.2(a), Eq. J4-3 over the weld length", ck.shear_yield(beam_grade.fy, beam.tw * lw), "J4.2a")
    out.add("beam web shear rupture at the weld", "weld_base_metal", "beam web",
            f"{SPEC} J4.2(b), Eq. J4-4 over the weld length (Manual Table 10-4c minimum web)",
            ck.shear_rupture(beam_grade.fu, beam.tw * lw), "J4.2b")
    cope_checks(out, lines, beam, beam_grade)


def single_angle(lines, out, demands):
    beam, beam_grade = lines.member("beam")
    _, face, sup_grade, t_sup = support_ply(lines)
    shape, grade, outstanding = lines.angle("angle")
    bolts = lines.bolts()
    n, s, lev = lines.count("rows"), lines.length("pitch"), lines.length("edge_vertical")
    deformation = lines.word("deformation", "considered") == "considered"
    holes = lines.holes(bolts.d, ["angle", "beam", "support"])
    t = shape.t
    length = element_length(n, s, lev)
    beam_leg, sup_leg = _angle_legs(shape, outstanding)
    beam_gauge = lines.length("beam_gauge")
    if beam_gauge <= 3:
        k_b, note_b = F(1), "beam-leg eccentricity of 3 in. or less neglected (Manual Fig. 10-15, Example II.A-28A)"
    else:
        k_b, note_b = eccentric(column(n, s), beam_gauge)
    angle_beam = Ply("angle", t, grade.fu, holes["angle"], lev, "bottom")
    web = beam_web_ply(lines, beam, beam_grade, holes["beam"])
    bolt_line(out, BoltLine("beam leg", n, s, 1, 1, ((1, angle_beam), (1, web)), k_b, note_b), bolts, deformation)
    shear_element(out, "angle", grade, t, length, n, holes["angle"])
    block_shear(out, "angle, beam leg", grade, t, lev, s, beam_leg - beam_gauge, n, holes["angle"])
    side = lines.word("support_side")
    if side == "bolted":
        g_sup = lines.length("support_gauge")
        e = g_sup + beam.tw / 2
        k_s, note_s = eccentric(column(n, s), e)
        angle_sup = Ply("angle", t, grade.fu, holes["angle"], lev, "top")
        sup = Ply(f"support {face}", t_sup, sup_grade.fu, holes["support"])
        bolt_line(out, BoltLine("support leg", n, s, 1, 1, ((1, angle_sup), (1, sup)), k_s, note_s), bolts, deformation)
        block_shear(out, "angle, support leg", grade, t, lev, s, sup_leg - g_sup, n, holes["angle"])
        flexure_element(out, "angle, support leg", grade, t, length, holes["angle"],
                        hole_offsets(n, s), out.demand * e)
    else:
        out.unsupported.append("welded support side: the eccentric angle-to-support weld is not modeled")
    cope_checks(out, lines, beam, beam_grade, n, s, holes["beam"])


def shear_tee(lines, out, demands):
    beam, beam_grade = lines.member("beam")
    _, face, sup_grade, t_sup = support_ply(lines)
    tee, grade = lines.tee()
    bolts = lines.bolts()
    n, s, lev = lines.count("rows"), lines.length("pitch"), lines.length("edge_vertical")
    a = lines.length("bolt_line")
    deformation = lines.word("deformation", "considered") == "considered"
    holes = lines.holes(bolts.d, ["stem", "flange", "beam", "support"])
    length = element_length(n, s, lev)
    e = lines.optional_length("eccentricity")
    e = a if e is None else e
    k, note = eccentric(column(n, s), e)
    stem = Ply("tee stem", tee.tw, grade.fu, holes["stem"], lev, "bottom")
    web = beam_web_ply(lines, beam, beam_grade, holes["beam"])
    bolt_line(out, BoltLine("stem", n, s, 1, 1, ((1, stem), (1, web)), k, note), bolts, deformation)
    flexure_element(out, "tee stem", grade, tee.tw, length, holes["stem"], hole_offsets(n, s), out.demand * a)
    shear_element(out, "tee stem", grade, tee.tw, length, n, holes["stem"])
    block_shear(out, "tee stem", grade, tee.tw, lev, s, tee.d - a, n, holes["stem"])
    side = lines.word("support_side")
    if side == "bolted":
        gauge = lines.length("support_gauge")
        flange = Ply("tee flange", tee.tf, grade.fu, holes["flange"], lev, "top")
        sup = Ply(f"support {face}", t_sup, sup_grade.fu, holes["support"])
        bolt_line(out, BoltLine("flange", n, s, 2, 1, ((1, flange), (1, sup))), bolts, deformation)
        shear_element(out, "tee flange", grade, tee.tf, length, n, holes["flange"], planes=2)
        block_shear(out, "tee flange", grade, tee.tf, lev, s, (tee.bf - gauge) / 2, n,
                    holes["flange"], blocks=2)
    else:
        out.unsupported.append("welded support side: the tee-flange-to-support weld is not modeled")
    cope_checks(out, lines, beam, beam_grade, n, s, holes["beam"])


def seated(lines, out, demands):
    beam, beam_grade = lines.member("beam")
    _, face, sup_grade, t_sup = support_ply(lines)
    shape, grade, outstanding = lines.angle("angle")
    seat = lines.length("seat_length")
    setback = lines.length("setback", F(1, 2)) + UNDERRUN
    t = shape.t
    out_leg = shape.long_leg if outstanding == "long" else shape.short_leg
    lb = out_leg - setback
    d, tw, tf, k = beam.d, beam.tw, beam.tf, beam.kdes
    fy = beam_grade.fy
    out.add("beam web local yielding", "web_local_yielding", "beam web",
            f"{SPEC} J10.2, Eq. J10-3, lb = seat leg less setback and 1/4 in. underrun",
            ck.web_local_yielding(fy, tw, k, lb, d), "J10.2")
    eq = "J10-5a" if lb / d <= F(1, 5) else "J10-5b"
    out.add("beam web local crippling", "web_crippling", "beam web", f"{SPEC} J10.3, Eq. {eq}",
            ck.web_crippling(fy, tw, tf, lb, d), "J10.3")
    out.add("seat outstanding leg shear yielding", "shear_yield", "seat angle",
            f"{SPEC} J4.2(a), Eq. J4-3 on the outstanding leg (Manual Part 10 seat checks)",
            ck.shear_yield(grade.fy, seat * t), "J4.2a")
    lb_req = _required_bearing(out, beam, fy)
    arm = setback + lb_req / 2 - (t + F(3, 8))
    out.add("seat outstanding leg flexural yielding", "seat_flexure", "seat angle",
            f"{MANUAL} Part 10 seat flexure, Mn = Fy L t^2 / 4 at t + 3/8 in. from the angle's back",
            grade.fy * seat * t * t / 4, "flexure", out.demand * max(arm, F(0)), "kip-in",
            note=f"reaction at setback + lb/2 with lb = {float(lb_req):.4g} in. required by J10.2 and J10.3, at least kdes")
    side = lines.word("support_side")
    if side == "bolted" and lines.has("bolts"):
        bolts = lines.bolts()
        holes = lines.holes(bolts.d, ["angle", "support"])
        rows = lines.count("rows")
        pitch = lines.length("pitch", F(3))
        leg = Ply("seat angle", t, grade.fu, holes["angle"])
        sup = Ply(f"support {face}", t_sup, sup_grade.fu, holes["support"])
        bolt_line(out, BoltLine("seat to support", rows, pitch, 2, 1, ((1, leg), (1, sup))), bolts,
                  lines.word("deformation", "considered") == "considered")
    else:
        out.unsupported.append("welded seat: the seat-to-support weld is not modeled")
    out.notes.append("top angle: a stability detail, carries no strength check")


def _required_bearing(out, beam, fy):
    """Bearing length the demand needs under J10.2 and J10.3 at a beam end, at least kdes."""
    phi_y, om_y = ck.FACTORS["J10.2"]
    phi_c, om_c = ck.FACTORS["J10.3"]
    nominal_y = out.demand / phi_y if out.lrfd else out.demand * om_y
    nominal_c = out.demand / phi_c if out.lrfd else out.demand * om_c
    lb_y = nominal_y / (fy * beam.tw) - F(5, 2) * beam.kdes
    base = F(2, 5) * beam.tw**2 * ck.sqrt(ck.E * fy * beam.tf / beam.tw)
    slender = ck.sqrt((beam.tw / beam.tf) ** 3)
    lb_c = (nominal_c / base - 1) * beam.d / (3 * slender)
    if lb_c / beam.d > F(1, 5):
        lb_c = ((nominal_c / base - 1) / slender + F(1, 5)) * beam.d / 4
    return max(beam.kdes, lb_y, lb_c)


def bolt_bracket(lines, out, demands):
    grade, tp = lines.plate("plate")
    _, face, sup_grade, t_sup = support_ply(lines)
    bolts = lines.bolts()
    n, m = lines.count("rows"), lines.count("columns")
    s, g = lines.length("pitch"), lines.length("gauge")
    ex = lines.length("eccentricity")
    lev, leh = lines.length("edge_vertical"), lines.length("plate_edge")
    deformation = lines.word("deformation", "considered") == "considered"
    holes = lines.holes(bolts.d, ["plate", "support"])
    depth = element_length(n, s, lev)
    pts = bolt_grid(n, m, float(s), float(g))
    c = F(bolt_coefficient(pts, float(ex)))
    note = f"{MANUAL} Part 7 instantaneous center, C = {float(c):.4g} at ex = {float(ex):.4g} in."
    edge = min(lev, leh)
    clear = [edge - holes["plate"].along / 2]
    if n > 1:
        clear.append(s - holes["plate"].along)
    if m > 1:
        clear.append(g - holes["plate"].across)
    lc = min(clear)
    rs = ck.bolt_shear(bolts.fnv, bolts.d)
    rp = min(ck.bearing(bolts.d, tp, grade.fu, deformation), ck.tearout(lc, tp, grade.fu, deformation))
    spacing = ([s - holes["support"].along] if n > 1 else []) + ([g - holes["support"].across] if m > 1 else [])
    rsup = ck.bearing(bolts.d, t_sup, sup_grade.fu, deformation)
    if spacing:
        rsup = min(rsup, ck.tearout(min(spacing), t_sup, sup_grade.fu, deformation))
    out.add("bolt shear", "bolts", "bolts", f"{SPEC} J3.7, Eq. J3-1; {note}", c * rs, "J3.6")
    out.add("bearing and tearout, plate", "bearing", "plate",
            f"{SPEC} J3.11a at the least clear distance for every bolt (Example II.A-22); {note}", c * rp, "J3.11")
    out.add(f"bearing and tearout, support {face}", "bearing", f"support {face}", f"{SPEC} J3.11a; {note}",
            c * rsup, "J3.11")
    out.add("bolt group effective strength", "bolts", "bolts", f"{SPEC} J3.7 User Note with J3.11a; {note}",
            c * min(rs, rp, rsup), "J3.6")
    e_aa = ex - F(m - 1, 2) * g
    moment = out.demand * e_aa
    out.add("flexural yielding, section A-A", "flexural_yield", "plate", f"{MANUAL} Eqs. 15-1 and 15-2",
            grade.fy * ck.plastic_modulus(tp, depth), "flexure", moment, "kip-in")
    znet = ck.net_plastic_modulus(tp, depth, holes["plate"].along + ALLOWANCE, hole_offsets(n, s))
    out.add("flexural rupture, section A-A", "flexural_rupture", "plate", f"{MANUAL} Eq. 15-3",
            grade.fu * znet, "flexural_rupture", moment, "kip-in")
    shear_element(out, "plate, section A-A", grade, tp, depth, n, holes["plate"])
    free_edge(out, lines, grade, tp, depth, e_aa)


def free_edge(out, lines, grade, t, a, e):
    """Section B-B of a shaped bracket with a sloped free edge (Manual Part 15, Eqs. 15-6 to 15-18)."""
    b = lines.optional_length("free_edge")
    if b is None:
        return
    theta = math.atan2(float(b), float(a))
    a1 = F(float(a) / math.cos(theta))
    b1 = F(float(a) * math.sin(theta))
    sin, cos = F(math.sin(theta)), F(math.cos(theta))
    out.add("shear yielding, section B-B", "shear_yield", "plate, section B-B", f"{MANUAL} Eqs. 15-6 and 15-7",
            F(3, 5) * grade.fy * t * b1, "J4.2a", out.demand * sin)
    lam = (b1 / t) * ck.sqrt(grade.fy) / (5 * ck.sqrt(475 + 1120 * (b1 / a1) ** 2))
    if lam <= F(7, 10):
        q = F(1)
    elif lam <= F(141, 100):
        q = F(134, 100) - F(486, 1000) * lam
    else:
        q = F(13, 10) / lam**2
    fcr = q * grade.fy
    phi, omega = ck.FACTORS["flexure"]
    nr, mr = out.demand * cos, out.demand * e - out.demand * cos * b1 / 2
    nc = fcr * t * b1 * (phi if out.lrfd else 1 / omega)
    mc = fcr * t * b1 * b1 / 4 * (phi if out.lrfd else 1 / omega)
    out.add("normal and flexural interaction, section B-B", "plate_buckling", "plate, section B-B",
            f"{MANUAL} Eqs. 15-8 to 15-18, Nr/Nc + Mr/Mc with Fcr = Q Fy, Q = {float(q):.3g}",
            F(1), "ratio", nr / nc + max(mr, F(0)) / mc, "ratio")


def weld_bracket(lines, out, demands):
    grade, tp = lines.plate("plate")
    weld = lines.weld("weld")
    length = lines.length("weld_length")
    e = lines.length("eccentricity")
    kl = lines.optional_length("weld_return")
    if kl is not None:
        segments = [((0.0, 0.0), (0.0, -float(length))), ((0.0, 0.0), (float(kl), 0.0)),
                    ((0.0, -float(length)), (float(kl), -float(length)))]
        rn = F(weld_strength(segments, float(e), float(weld.w), float(weld.fexx)))
        xbar = kl * kl / (2 * kl + length)
        out.add("fillet weld group", "weld", "weld",
                f"{SPEC} J2.4 with {MANUAL} Part 8 instantaneous center, C-shaped weld lapped on the support",
                weld.sides * rn, "J2.4")
        e_aa = e + xbar - kl
    else:
        throat_strength = F(3, 5) * weld.fexx * weld.w * F(math.sqrt(2)) / 2
        ratio = ck.sqrt(1 + (6 * e / length) ** 2)
        out.add("fillet weld lines, load normal to the faying surface", "weld", "weld",
                f"{SPEC} J2.4, kds = 1.0, elastic resultant of direct shear and bending on the weld lines",
                weld.sides * throat_strength * length / ratio, "J2.4")
        e_aa = e
    out.add("flexural yielding, section A-A", "flexural_yield", "plate", f"{MANUAL} Eqs. 15-1 and 15-2",
            grade.fy * ck.plastic_modulus(tp, length), "flexure", out.demand * e_aa, "kip-in")
    out.add("shear yielding, section A-A", "shear_yield", "plate", f"{SPEC} J4.2(a), Eq. J4-3",
            ck.shear_yield(grade.fy, length * tp), "J4.2a")
    out.add("shear rupture, section A-A", "shear_rupture", "plate", f"{SPEC} J4.2(b), Eq. J4-4, no holes",
            ck.shear_rupture(grade.fu, length * tp), "J4.2b")
    free_edge(out, lines, grade, tp, length, e_aa)


def hanger(lines, out, demands):
    tee, grade = lines.tee()
    sup, face, sup_grade, _ = support_ply(lines)
    bolts = lines.bolts()
    n, s = lines.count("rows"), lines.length("pitch")
    g, lev = lines.length("tee_gauge"), lines.length("edge_vertical")
    holes = lines.holes(bolts.d, ["flange", "support"])
    length = element_length(n, s, lev)
    nb = 2 * n
    rn = ck.bolt_tension(bolts.fnt, bolts.d)
    out.add("bolt tension", "bolt_tension", "bolts", f"{SPEC} J3.7, Eq. J3-1 with Fnt", nb * rn, "J3.6")
    for label, t, fu, bf, tw, hole in (
        ("tee flange", tee.tf, grade.fu, tee.bf, tee.tw, holes["flange"]),
        (f"support {face}", sup.tf if face == "flange" else sup.tw, sup_grade.fu, sup.bf, sup.tw, holes["support"]),
    ):
        q_sum, detail = _prying(out, bolts, rn, n, s, lev, g, t, fu, bf, tw, hole)
        out.add(f"bolt tension with prying, {label}", "prying", label,
                f"{MANUAL} Part 9 prying, Eqs. 9-23 to 9-40; {detail}", 2 * q_sum * rn, "J3.6")
    shear = demands.get("shear", F(0))
    out.add("tee stem tensile yielding", "tension_yield", "tee stem", f"{SPEC} J4.1(a), Eq. J4-1 over the tee length",
            ck.tension_yield(grade.fy, length * tee.tw), "J4.1a")
    shear_element(out, "tee flange", grade, tee.tf, length, n, holes["flange"], planes=2)
    if shear:
        rs = ck.bolt_shear(bolts.fnv, bolts.d)
        out.add("bolt shear", "bolts", "bolts", f"{SPEC} J3.7, Eq. J3-1", nb * rs, "J3.6", shear)
        phi, omega = ck.FACTORS["J3.6"]
        frv = shear / (nb * ck.bolt_area(bolts.d))
        reduction = (bolts.fnt / (phi * bolts.fnv)) if out.lrfd else (omega * bolts.fnt / bolts.fnv)
        fnt1 = min(F(13, 10) * bolts.fnt - reduction * frv, bolts.fnt)
        out.add("bolt tension with shear", "bolt_combined", "bolts", f"{SPEC} J3.8, Eqs. J3-2 and J3-3",
                nb * fnt1 * ck.bolt_area(bolts.d), "J3.6")
    if bolts.joint == "slip_critical":
        out.unsupported.append("slip-critical hanger: J3.10's tension reduction of slip is not modeled")


def prying(tc_bolt, b1, a1, p, hole_across, t, fu, lrfd):
    """Manual Part 9 prying for one bolt and its tributary length p: Eqs. 9-28 to 9-30 give tc,
    alpha' and Q. tc_bolt is the bolt's available tension. Returns (tc, alpha', Q)."""
    phi_b, omega_b = ck.FACTORS["flexure"]
    delta = 1 - hole_across / p
    rho = b1 / a1
    factor = 1 / phi_b if lrfd else omega_b
    tc = ck.sqrt(4 * tc_bolt * b1 * factor / (p * fu))
    alpha = (1 / (delta * (1 + rho))) * ((tc / t) ** 2 - 1)
    if alpha < 0:
        q = F(1)
    elif alpha <= 1:
        q = (t / tc) ** 2 * (1 + delta * alpha)
    else:
        q = (t / tc) ** 2 * (1 + delta)
    return tc, alpha, q


def prying_geometry(d, g, tw, bf):
    """b' and a' of Manual Eqs. 9-23 and 9-24 for a bolt gauge g across a flange of width bf."""
    b = (g - tw) / 2
    a = (bf - g) / 2
    return b, b - d / 2, min(a + d / 2, F(5, 4) * b + d / 2)


def tributary(rows, s, lev, b):
    """Tributary length per bolt of each row (Manual Fig. 9-4 as Example II.D-1 applies it)."""
    end = min(lev, F(7, 4) * b)
    if rows == 1:
        return [2 * end]
    side = min(s / 2, F(7, 4) * b)
    return [end + side if i in (0, rows - 1) else 2 * side for i in range(rows)]


def _prying(out, bolts, rn, rows, s, lev, g, t, fu, bf, tw, hole):
    """Sum over rows of Q for one line of bolts, with the basis's phi or Omega."""
    phi, omega = ck.FACTORS["J3.6"]
    tc_bolt = rn * phi if out.lrfd else rn / omega
    b, b1, a1 = prying_geometry(bolts.d, g, tw, bf)
    q_sum = sum(prying(tc_bolt, b1, a1, p, hole.across, t, fu, out.lrfd)[2] for p in tributary(rows, s, lev, b))
    return q_sum, f"b' = {float(b1):.4g} in., a' = {float(a1):.4g} in., Q summed over {rows} rows = {float(q_sum):.4g}"


KINDS = {
    "shear_tab": (shear_tab, "shear"),
    "double_angle": (double_angle, "shear"),
    "shear_end_plate": (shear_end_plate, "shear"),
    "single_angle": (single_angle, "shear"),
    "shear_tee": (shear_tee, "shear"),
    "seated": (seated, "shear"),
    "bolt_bracket": (bolt_bracket, "shear"),
    "weld_bracket": (weld_bracket, "shear"),
    "hanger": (hanger, "tension"),
}
