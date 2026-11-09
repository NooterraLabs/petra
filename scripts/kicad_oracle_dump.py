"""What KiCad's own pcbnew reads from a .kicad_pcb file, in integer nanometres, for
scripts/kicad_oracle.py. Runs inside KiCad's Python, not Petra's:

    flatpak run --filesystem=home --command=python3 org.kicad.KiCad kicad_oracle_dump.py BOARD OUT.json
    python3 kicad_oracle_dump.py BOARD OUT.json      (a distribution's KiCad 7, for k7.json)

Every coordinate is KiCad's board frame, x right and y down, as KiCad holds it after loading.
KiCad's outline polygon and courtyard caches are recorded but are not truth for the oracle:
KiCad shrinks a courtyard cache by a few micrometres, and its polygons place arc points up to
half a micrometre off the arc. The oracle samples the drawn shapes instead.
"""
import json
import sys

import pcbnew


def xy(v):
    return [int(v.x), int(v.y)]


def call(obj, name, *layer_first):
    """obj.name(F_Cu) on KiCad 9+ padstack APIs, else obj.name()."""
    f = getattr(obj, name)
    for args in ((pcbnew.F_Cu,), ()):
        try:
            return f(*args)
        except TypeError:
            continue
    raise TypeError(name)


def chain_points(chain):
    return [xy(chain.CPoint(i)) for i in range(chain.PointCount())]


def chain_arcs(chain):
    """The arcs a chain holds, as KiCad keeps them: start, mid, end and centre."""
    out = []
    try:
        for i in range(chain.ArcCount()):
            a = chain.Arc(i)
            out.append({"start": xy(a.GetP0()), "mid": xy(a.GetArcMid()), "end": xy(a.GetP1()),
                        "center": xy(a.GetCenter()), "radius": float(a.GetRadius())})
    except Exception as err:
        out.append({"error": f"{type(err).__name__}: {err}"})
    return out


def polyset(ps):
    out = []
    for i in range(ps.OutlineCount()):
        out.append({"outline": chain_points(ps.Outline(i)), "arcs": chain_arcs(ps.Outline(i)),
                    "holes": [chain_points(ps.Hole(i, h)) for h in range(ps.HoleCount(i))]})
    return out


FILE_NAMES = {pcbnew.Edge_Cuts: "Edge.Cuts", pcbnew.F_CrtYd: "F.CrtYd", pcbnew.B_CrtYd: "B.CrtYd",
              pcbnew.F_Fab: "F.Fab", pcbnew.B_Fab: "B.Fab", pcbnew.F_Cu: "F.Cu", pcbnew.B_Cu: "B.Cu"}


def layer_name(layer):
    """The layer's name as the file format writes it, whatever the board or KiCad calls it."""
    return FILE_NAMES.get(layer, str(layer))


def shape(s):
    kind = s.ShowShape()
    d = {"kind": kind, "layer": layer_name(s.GetLayer()), "user_layer": s.GetLayerName(), "width": int(s.GetWidth())}
    if kind in ("Line", "Rect", "Arc", "Circle", "Bezier", "Segment", "Rectangle"):
        d["start"], d["end"] = xy(s.GetStart()), xy(s.GetEnd())
    if kind == "Arc":
        d["mid"], d["center"] = xy(s.GetArcMid()), xy(s.GetCenter())
        d["radius"] = float(s.GetRadius())
    if kind == "Circle":
        d["center"], d["radius"] = xy(s.GetCenter()), float(s.GetRadius())
    if kind in ("Rect", "Rectangle"):
        try:
            d["corners"] = [xy(c) for c in s.GetRectCorners()]
        except Exception:
            pass
    if kind in ("Polygon", "Poly"):
        d["poly"] = polyset(s.GetPolyShape())
    bb = s.GetBoundingBox()
    d["bbox"] = [int(bb.GetLeft()), int(bb.GetTop()), int(bb.GetRight()), int(bb.GetBottom())]
    return d


def names(value, prefix):
    return sorted(n for n in dir(pcbnew) if n.startswith(prefix) and getattr(pcbnew, n) == value)


def main(path, out):
    board = pcbnew.LoadBoard(path)
    ds = board.GetDesignSettings()
    result = {"file": path, "kicad": pcbnew.Version(), "thickness": int(ds.GetBoardThickness()),
              "copper_layers": board.GetCopperLayerCount()}
    try:
        stack = board.GetStackupOrDefault()
        result["stackup_thickness"] = int(stack.BuildBoardThicknessFromStackup())
        result["stackup_layers"] = int(stack.GetCount())
        result["has_stackup_in_file"] = bool(ds.m_HasStackup) if hasattr(ds, "m_HasStackup") else None
    except Exception as exc:
        result["stackup_error"] = repr(exc)
    edge = pcbnew.Edge_Cuts
    result["edge_shapes"] = [shape(d) for d in board.GetDrawings()
                             if isinstance(d, pcbnew.PCB_SHAPE) and d.GetLayer() == edge]
    outline = pcbnew.SHAPE_POLY_SET()
    ok = None
    for args in ((outline, False), (outline,), (outline, None, False, False)):
        try:
            ok = board.GetBoardPolygonOutlines(*args)
            break
        except TypeError:
            continue
    result["outline_ok"] = bool(ok)
    result["outline"] = polyset(outline)
    fps = []
    for fp in board.GetFootprints():
        try:
            fp.BuildCourtyardCaches()
        except Exception:
            pass
        f = {"ref": fp.GetReference(), "value": fp.GetValue(), "fpid": fp.GetFPIDAsString(),
             "layer": layer_name(fp.GetLayer()), "flipped": bool(fp.IsFlipped()), "at": xy(fp.GetPosition()),
             "angle": float(fp.GetOrientationDegrees()), "attrs": int(fp.GetAttributes())}
        try:
            f["descr"], f["tags"] = fp.GetLibDescription(), fp.GetKeywords()
        except Exception:
            f["descr"], f["tags"] = "", ""
        cy = {}
        for name, layer in (("F", pcbnew.F_CrtYd), ("B", pcbnew.B_CrtYd)):
            try:
                cy[name] = polyset(fp.GetCourtyard(layer))
            except Exception as exc:
                cy[name] = str(exc)
        f["courtyard"] = cy
        f["graphics"] = [shape(g) for g in fp.GraphicalItems()
                         if isinstance(g, pcbnew.PCB_SHAPE) and layer_name(g.GetLayer()) in
                         ("Edge.Cuts", "F.CrtYd", "B.CrtYd", "F.Fab", "B.Fab")]
        pads = []
        for p in fp.Pads():
            pad = {"number": p.GetNumber(), "attr": int(p.GetAttribute()),
                   "attr_names": names(p.GetAttribute(), "PAD_ATTRIB"),
                   "at": xy(p.GetPosition()), "angle": float(p.GetOrientationDegrees()),
                   "drill": xy(p.GetDrillSize()), "drill_shape": int(p.GetDrillShape()),
                   "drill_shape_names": names(p.GetDrillShape(), "PAD_DRILL_SHAPE"),
                   "offset": xy(call(p, "GetOffset")), "shape_pos": xy(call(p, "ShapePos")),
                   "size": xy(call(p, "GetSize")),
                   "fp_rel": xy(p.GetFPRelativePosition() if hasattr(p, "GetFPRelativePosition") else p.GetPos0())}
            try:
                pad["fp_rel_angle"] = float(p.GetFPRelativeOrientation().AsDegrees())
            except Exception:
                pass
            bb = p.GetBoundingBox()
            pad["bbox"] = [int(bb.GetLeft()), int(bb.GetTop()), int(bb.GetRight()), int(bb.GetBottom())]
            pads.append(pad)
        f["pads"] = pads
        fps.append(f)
    result["footprints"] = fps
    vias = []
    for t in board.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            v = pcbnew.Cast_to_PCB_VIA(t) if hasattr(pcbnew, "Cast_to_PCB_VIA") else t
            vias.append({"at": xy(v.GetPosition()), "drill": int(v.GetDrillValue()),
                         "type": int(v.GetViaType()), "type_names": names(v.GetViaType(), "VIATYPE")})
    result["vias"] = vias
    with open(out, "w") as fh:
        json.dump(result, fh)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
