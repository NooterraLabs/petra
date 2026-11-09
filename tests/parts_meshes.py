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
