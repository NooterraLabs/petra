"""Mesh files for the parts tests: boxes and shapes whose geometry is known exactly.

Every writer takes triangles as vertex triples in millimetres (exact decimals as text or
Fractions) and returns the path and the sha256 of what it wrote."""
from __future__ import annotations

import hashlib
import struct
import zipfile
from fractions import Fraction
from pathlib import Path

Tri = tuple[tuple, tuple, tuple]


def box(lo, hi) -> list[Tri]:
    """The closed box [lo, hi], each face two triangles with outward normals."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    p = {
        0: (x0, y0, z0), 1: (x1, y0, z0), 2: (x1, y1, z0), 3: (x0, y1, z0),
        4: (x0, y0, z1), 5: (x1, y0, z1), 6: (x1, y1, z1), 7: (x0, y1, z1),
    }
    quads = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))
    out = []
    for a, b, c, d in quads:
        out.append((p[a], p[b], p[c]))
        out.append((p[a], p[c], p[d]))
    return out


def flipped(tris: list[Tri]) -> list[Tri]:
    return [(a, c, b) for a, b, c in tris]


def _text(v) -> str:
    """Coordinates are written as given: ints or decimal strings."""
    return str(v)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ascii_stl(path: Path, tris: list[Tri]) -> tuple[Path, str]:
    lines = ["solid test"]
    for t in tris:
        lines.append("  facet normal 0 0 0")
        lines.append("    outer loop")
        for v in t:
            lines.append("      vertex " + " ".join(_text(c) for c in v))
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append("endsolid test")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path, _sha(path)


def binary_stl(path: Path, tris: list[Tri]) -> tuple[Path, str]:
    body = bytearray(b"solid binary header that is not ascii".ljust(80, b" "))
    body += struct.pack("<I", len(tris))
    for t in tris:
        body += struct.pack("<3f", 0, 0, 0)
        for v in t:
            body += struct.pack("<3f", *(float(Fraction(str(c))) for c in v))
        body += struct.pack("<H", 0)
    path.write_bytes(bytes(body))
    return path, _sha(path)


def three_mf(path: Path, tris: list[Tri], transform: str | None = None, unit: str = "millimeter") -> tuple[Path, str]:
    index: dict[tuple, int] = {}
    faces = []
    for t in tris:
        faces.append(tuple(index.setdefault(tuple(_text(c) for c in v), len(index)) for v in t))
    vertices = "".join(f'<vertex x="{x}" y="{y}" z="{z}"/>' for x, y, z in index)
    triangles = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in faces)
    item = f'<item objectid="1"{f" transform={chr(34)}{transform}{chr(34)}" if transform else ""}/>'
    model = (f'<?xml version="1.0" encoding="UTF-8"?><model unit="{unit}" '
             f'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>'
             f'<object id="1" type="model"><mesh><vertices>{vertices}</vertices><triangles>{triangles}</triangles>'
             f'</mesh></object></resources><build>{item}</build></model>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("3D/3dmodel.model", model)
    return path, _sha(path)


def tray(lo, hi, wall, floor) -> list[Tri]:
    """An open-top box: the outer box [lo, hi] less the pocket `wall` in from each side and
    `floor` up from the bottom, open at the top. Coordinates as Fractions."""
    (x0, y0, z0), (x1, y1, z1) = [tuple(Fraction(str(c)) for c in p) for p in (lo, hi)]
    w, f = Fraction(str(wall)), Fraction(str(floor))
    o = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    i = [(x0 + w, y0 + w), (x1 - w, y0 + w), (x1 - w, y1 - w), (x0 + w, y1 - w)]
    out = [((*o[0], z0), (*o[2], z0), (*o[1], z0)), ((*o[0], z0), (*o[3], z0), (*o[2], z0))]
    for k in range(4):
        a, b = o[k], o[(k + 1) % 4]
        out += [((*a, z0), (*b, z0), (*b, z1)), ((*a, z0), (*b, z1), (*a, z1))]
        p, q = i[k], i[(k + 1) % 4]
        out += [((*a, z1), (*b, z1), (*q, z1)), ((*a, z1), (*q, z1), (*p, z1))]
        out += [((*p, z1), (*q, z1), (*q, z0 + f)), ((*p, z1), (*q, z0 + f), (*p, z0 + f))]
    out += [((*i[0], z0 + f), (*i[1], z0 + f), (*i[2], z0 + f)), ((*i[0], z0 + f), (*i[2], z0 + f), (*i[3], z0 + f))]
    return out


def _ngon(centre, r, n):
    import math
    cx, cy = (Fraction(str(c)) for c in centre)
    return [(cx + Fraction(f"{float(r) * math.cos((k + 0.5) * 2 * math.pi / n):.4f}"),
             cy + Fraction(f"{float(r) * math.sin((k + 0.5) * 2 * math.pi / n):.4f}")) for k in range(n)]


def prism(ring, z0, z1) -> list[Tri]:
    """A solid prism along z over a counter-clockwise polygon that is star-shaped from its
    first corner, so a fan from that corner covers it."""
    ring = [(Fraction(str(x)), Fraction(str(y))) for x, y in ring]
    z0, z1, n = Fraction(str(z0)), Fraction(str(z1)), len(ring)
    out = [((*ring[0], z1), (*ring[k], z1), (*ring[k + 1], z1)) for k in range(1, n - 1)]
    out += [((*ring[0], z0), (*ring[k + 1], z0), (*ring[k], z0)) for k in range(1, n - 1)]
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        out += [((*a, z0), (*b, z0), (*b, z1)), ((*a, z0), (*b, z1), (*a, z1))]
    return out


def pin(centre, r, z0, z1, n=32) -> list[Tri]:
    """A solid n-gon prism along z, corners at radius r."""
    return prism(_ngon(centre, r, n), z0, z1)


def upright(ring, width) -> list[Tri]:
    """A prism along y over a polygon drawn in the xz plane, counter-clockwise as x and z
    run. It is drawn in the xy plane and turned up by swapping y and z, a reflection, so
    each triangle's order is reversed to keep it facing out."""
    return flipped([tuple((x, z, y) for x, y, z in tri) for tri in prism(ring, 0, width)])


def bracket(leg, rise, t, width) -> list[Tri]:
    """An L bracket bent from sheet t thick: a leg along x, a rise along z, width along y."""
    return upright([(0, 0), (leg, 0), (leg, t), (t, t), (t, rise), (0, rise)], width)


def plate(lo, hi, centre, r, n=32, sink=None) -> list[Tri]:
    """The block [lo, hi] with a through hole along z: a regular n-gon, corners at radius r
    about `centre` (x, y), rounded to 4 decimals so shared corners stay equal. With `sink`,
    a 90 degree countersink of that corner radius opens the hole at the top."""
    (x0, y0, z0), (x1, y1, z1) = [tuple(Fraction(str(c)) for c in p) for p in (lo, hi)]
    ring = _ngon(centre, r, n)
    mouth = _ngon(centre, sink, n) if sink is not None else ring
    zs = z1 - (Fraction(str(sink)) - Fraction(str(r))) if sink is not None else z1
    corners = [(x1, y1), (x0, y1), (x0, y0), (x1, y0)]
    top2 = []
    bottom2 = []
    for q in range(4):
        c, d = corners[q], corners[(q + 1) % 4]
        for face, loop in ((top2, mouth), (bottom2, ring)):
            arc = loop[q * n // 4:(q + 1) * n // 4]
            face += [(c, arc[k], arc[k + 1]) for k in range(len(arc) - 1)]
            nxt = loop[((q + 1) * n // 4) % n]
            face += [(c, arc[-1], nxt), (c, nxt, d)]

    def up(t, z, sign):
        a, b, c = t
        cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
        t3 = ((*a, z), (*b, z), (*c, z))
        return t3 if (cross > 0) == (sign > 0) else (t3[0], t3[2], t3[1])

    out = [up(t, z1, 1) for t in top2] + [up(t, z0, -1) for t in bottom2]
    outer = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    for k in range(4):
        a, b = outer[k], outer[(k + 1) % 4]
        out += [((*a, z0), (*b, z0), (*b, z1)), ((*a, z0), (*b, z1), (*a, z1))]
    for k in range(n):
        a, b = ring[k], ring[(k + 1) % n]
        out += [((*a, z0), (*a, zs), (*b, zs)), ((*a, z0), (*b, zs), (*b, z0))]
        if sink is not None:
            p, q = mouth[k], mouth[(k + 1) % n]
            out += [((*a, zs), (*p, z1), (*q, z1)), ((*a, zs), (*q, z1), (*b, zs))]
    return out


def write(tmp, name, tris) -> tuple[str, str]:
    """An ASCII STL of exact decimals in `tmp`; returns its absolute path and sha256."""
    path, sha = ascii_stl(Path(tmp) / f"{name}.stl", [tuple(tuple(_decimal(c) for c in v) for v in t) for t in tris])
    return str(path.resolve()).replace("\\", "/"), sha


def _decimal(c) -> str:
    q = Fraction(str(c)) if not isinstance(c, Fraction) else c
    text = f"{float(q):.10f}".rstrip("0").rstrip(".")
    if Fraction(text) != q:
        raise ValueError(f"{q} is not a short decimal")
    return text
