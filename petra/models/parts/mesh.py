"""A part's mesh: STL or 3MF bytes to exact coordinates. Trusted; the boundary for mesh files.

The part is the solid the mesh bounds. `read_mesh` accepts a mesh only when it is the
oriented boundary of a solid: every edge is used by exactly two triangles, once in each
direction, so the surface is closed, two-manifold and consistently oriented. That one
rule refuses an edge shared by four faces (two bodies meeting along an edge), a
duplicated face, and an open boundary. Two triangles on the same three vertices are
refused too, because a doubled wall drawn as a pair of opposite triangles passes the edge
rule and bounds nothing. Every connected piece must enclose volume, and the whole mesh
must enclose positive volume, so an inside-out file and a closed zero-thickness sheet are
refused. Lowering (lower.py) adds the checks that need geometry: no triangles cross, no
two triangles of the mesh lie on each other facing opposite ways (a zero-thickness wall
or an internal face), and each piece's orientation agrees with its nesting.

Coordinates are exact. A float32 in a binary STL is read as the shortest decimal that
round-trips to it (numpy's `format_float_positional` with `unique=True`), so a CAD export
of 25.1 mm reads as 251/10 mm, the same rational a design line `25.1 mm` gives, and two
parts drawn to touch do touch. ASCII STL and 3MF decimals are read as written. Every
coordinate is then an integer over one power of ten, `Mesh.scale`.
"""
from __future__ import annotations

import hashlib
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from io import BytesIO
from pathlib import Path

import numpy as np

from ...kernel import Q
from ..base import ComponentError

Point = tuple[Q, Q, Q]
"""Exact coordinates in millimetres. Statements convert to metres at their boundary (build.py)."""

LIMIT = 2 ** 60
"""Every integer coordinate Petra stores in int64 stays below this, so a sum or difference of
two never wraps (exact.make_body)."""


class Unit(Enum):
    """The unit a mesh file's numbers are in. STL carries none, so the design names it."""

    MM = "mm"
    INCH = "inch"


_TO_MM = {Unit.MM: Fraction(1), Unit.INCH: Fraction(127, 5)}
_3MF_UNITS = {"millimeter": Unit.MM, "inch": Unit.INCH}


class MeshError(ComponentError):
    """A mesh file Petra refuses. The message names the file, the rule broken and the
    first offending edge, triangle or coordinate."""

    def __init__(self, path: Path | str, problem: str) -> None:
        super().__init__((f"{path}: {problem}",))


@dataclass(frozen=True, eq=False)
class Mesh:
    """The oriented boundary of a solid with exact coordinates. Only `read_mesh` builds one."""

    path: str
    sha256: str
    scale: int                 # coordinates are integers in units of 1/scale mm; a power of ten
    vertices: np.ndarray       # (n, 3) int64, read-only; equal points merged
    triangles: np.ndarray      # (m, 3) int64 indices into vertices, read-only, counter-clockwise seen from outside

    def point(self, index: int) -> Point:
        """Vertex `index` in millimetres, exact."""
        return tuple(Fraction(int(c), self.scale) for c in self.vertices[index])

    def bounds(self) -> tuple[Point, Point]:
        """The closed axis-aligned box of the vertices, low corner then high corner."""
        lo, hi = self.vertices.min(axis=0), self.vertices.max(axis=0)
        return tuple(Fraction(int(c), self.scale) for c in lo), tuple(Fraction(int(c), self.scale) for c in hi)

    def volume(self) -> Fraction:
        """The enclosed volume, mm^3, exact."""
        return Fraction(sum(_dets(self)), 6 * self.scale ** 3)

    def centroid(self) -> Point:
        """The centroid of the enclosed volume, mm, exact: each tetrahedron from the origin
        to a triangle weighs its signed volume and has its centroid at a quarter of the
        triangle's vertex sum."""
        dets = _dets(self)
        total = sum(dets)
        tri = self.vertices[self.triangles].astype(object)
        sums = tri.sum(axis=1)
        return tuple(Fraction(sum(d * int(s[k]) for d, s in zip(dets, sums)), 4 * total * self.scale) for k in range(3))


def _dets(mesh: Mesh) -> list[int]:
    """Six times each triangle's signed tetrahedron volume from the origin, in scale^3 units."""
    t = mesh.vertices[mesh.triangles].astype(object)
    a, b, c = t[:, 0], t[:, 1], t[:, 2]
    cross = np.stack((b[:, 1] * c[:, 2] - b[:, 2] * c[:, 1],
                      b[:, 2] * c[:, 0] - b[:, 0] * c[:, 2],
                      b[:, 0] * c[:, 1] - b[:, 1] * c[:, 0]), axis=1)
    return [int(v) for v in (a * cross).sum(axis=1)]


def read_mesh(path: Path, sha256: str, unit: Unit) -> Mesh:
    """Read a binary or ASCII STL (sniffed) or a 3MF (a zip with one object, its build
    transform applied exactly from the decimal text). Check the sha256 of the file bytes,
    convert to millimetres exactly (an inch is 127/5 mm), merge equal vertices, and require
    the boundary of a solid as the module docstring states. The bytes are read and hashed
    on every call, and only the parse of bytes that match is memoised, so a file changed on
    disk is refused under its old hash. Raises MeshError."""
    path, sha256 = str(path), sha256.lower()
    try:
        data = Path(path).read_bytes()
    except OSError as exc:
        raise MeshError(path, f"cannot be read: {exc.strerror or exc}") from None
    found = hashlib.sha256(data).hexdigest()
    if found != sha256:
        raise MeshError(path, f"sha256 is {found}, not {sha256} as the design says")
    key = (path, sha256, unit)
    if key not in _PARSED:
        if len(_PARSED) >= 64:
            _PARSED.pop(next(iter(_PARSED)))
        _PARSED[key] = _decode(path, sha256, unit, data)
    return _PARSED[key]


_PARSED: dict[tuple[str, str, Unit], Mesh] = {}


def _decode(path: str, sha256: str, unit: Unit, data: bytes) -> Mesh:
    if data[:4] == b"PK\x03\x04":
        coords, faces = _three_mf(path, data, unit)
    elif _is_binary_stl(data):
        coords, faces = _binary_stl(path, data)
    else:
        coords, faces = _ascii_stl(path, data)
    return _solid(path, sha256, coords, faces, _TO_MM[unit])


def _is_binary_stl(data: bytes) -> bool:
    if len(data) < 84:
        return False
    count = int.from_bytes(data[80:84], "little")
    return len(data) == 84 + 50 * count


def _binary_stl(path: str, data: bytes) -> tuple[list[Fraction], np.ndarray]:
    count = int.from_bytes(data[80:84], "little")
    record = np.dtype([("normal", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    floats = np.frombuffer(data, dtype=record, count=count, offset=84)["v"].reshape(-1)
    if not np.all(np.isfinite(floats)):
        raise MeshError(path, "holds a coordinate that is not a finite number")
    unique, inverse = np.unique(floats, return_inverse=True)
    exact = [Fraction(np.format_float_positional(np.float32(v), unique=True, trim="-")) for v in unique]
    coords = [exact[i] for i in inverse]
    return coords, np.arange(len(coords) // 3, dtype=np.int64).reshape(-1, 3)


_NUMBER = r"([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
_VERTEX = re.compile(rf"vertex\s+{_NUMBER}\s+{_NUMBER}\s+{_NUMBER}")


def _ascii_stl(path: str, data: bytes) -> tuple[list[Fraction], np.ndarray]:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        raise MeshError(path, "is neither a binary STL of consistent length nor ASCII text") from None
    if not text.lstrip().startswith("solid"):
        raise MeshError(path, "is neither a binary STL, an ASCII STL nor a 3MF")
    coords = [Fraction(n) for match in _VERTEX.finditer(text) for n in match.groups()]
    if len(coords) % 9 or text.count("facet normal") * 9 != len(coords):
        raise MeshError(path, "holds a facet that does not have exactly three vertices")
    return coords, np.arange(len(coords) // 3, dtype=np.int64).reshape(-1, 3)


def _three_mf(path: str, data: bytes, unit: Unit) -> tuple[list[Fraction], np.ndarray]:
    try:
        with zipfile.ZipFile(BytesIO(data)) as z:
            root = ET.fromstring(z.read("3D/3dmodel.model"))
    except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise MeshError(path, f"is not a readable 3MF: {exc}") from None
    ns = {"m": root.tag[1:].split("}")[0]} if root.tag.startswith("{") else {"m": ""}
    q = (lambda tag: f"m:{tag}") if ns["m"] else (lambda tag: tag)
    stated = _3MF_UNITS.get(root.get("unit", "millimeter"))
    if stated is not unit:
        raise MeshError(path, f"is in {root.get('unit', 'millimeter')} and the design reads it in {unit.value}")
    objects = root.findall(f"{q('resources')}/{q('object')}", ns)
    items = root.findall(f"{q('build')}/{q('item')}", ns)
    if len(objects) != 1 or len(items) != 1 or objects[0].find(q("mesh"), ns) is None:
        raise MeshError(path, "a 3MF holds exactly one mesh object, built once")
    mesh = objects[0].find(q("mesh"), ns)
    vertices = [tuple(Fraction(v.get(k)) for k in "xyz") for v in mesh.find(q("vertices"), ns)]
    faces = np.array([[int(t.get(k)) for k in ("v1", "v2", "v3")] for t in mesh.find(q("triangles"), ns)], dtype=np.int64)
    m = [Fraction(x) for x in items[0].get("transform", "1 0 0 0 1 0 0 0 1 0 0 0").split()]
    if len(m) != 12:
        raise MeshError(path, "a build transform has twelve numbers")
    placed = [tuple(x * m[k] + y * m[3 + k] + z * m[6 + k] + m[9 + k] for k in range(3)) for x, y, z in vertices]
    det = m[0] * (m[4] * m[8] - m[5] * m[7]) - m[1] * (m[3] * m[8] - m[5] * m[6]) + m[2] * (m[3] * m[7] - m[4] * m[6])
    if det <= 0:
        raise MeshError(path, "the build transform mirrors or flattens the object")
    if faces.size and (faces.min() < 0 or faces.max() >= len(placed)):
        raise MeshError(path, "a triangle names a vertex the object does not hold")
    coords = [c for v in placed for c in v]
    return coords, faces


def _solid(path: str, sha256: str, coords: list[Fraction], faces: np.ndarray, to_mm: Fraction) -> Mesh:
    if not len(faces):
        raise MeshError(path, "holds no triangles")
    mm = [c * to_mm for c in coords]
    scale = 1
    for d in {c.denominator for c in mm}:
        while scale % d:
            if scale > 10 ** 12:
                raise MeshError(path, f"a coordinate with denominator {d} is not a decimal Petra can hold exactly")
            scale *= 10
    ints = [int(c * scale) for c in mm]
    if any(abs(i) >= LIMIT for i in ints):
        raise MeshError(path, "a coordinate is too large at the file's precision")
    raw = np.array(ints, dtype=np.int64).reshape(-1, 3)
    vertices, inverse = np.unique(raw, axis=0, return_inverse=True)
    triangles = inverse.reshape(-1)[faces]
    _check_surface(path, vertices, triangles)
    vertices.setflags(write=False)
    triangles = np.ascontiguousarray(triangles, dtype=np.int64)
    triangles.setflags(write=False)
    mesh = Mesh(path, sha256, scale, vertices, triangles)
    _check_volumes(path, mesh)
    return mesh


def _check_surface(path: str, vertices: np.ndarray, triangles: np.ndarray) -> None:
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    collapsed = np.flatnonzero((a == b) | (b == c) | (c == a))
    if collapsed.size:
        raise MeshError(path, f"triangle {collapsed[0]} has no area: two of its corners are one point")
    p = vertices.astype(object)
    u, v = p[b] - p[a], p[c] - p[a]
    cross = np.stack((u[:, 1] * v[:, 2] - u[:, 2] * v[:, 1], u[:, 2] * v[:, 0] - u[:, 0] * v[:, 2],
                      u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0]), axis=1)
    flat = np.flatnonzero((cross == 0).all(axis=1))
    if flat.size:
        raise MeshError(path, f"triangle {flat[0]} has no area: its corners lie on one line")
    n = len(vertices)
    heads = np.concatenate((a, b, c))
    tails = np.concatenate((b, c, a))
    codes = heads * n + tails
    order = np.argsort(codes, kind="stable")
    same = np.flatnonzero(codes[order][1:] == codes[order][:-1])
    if same.size:
        first, second = order[same[0]] % len(triangles), order[same[0] + 1] % len(triangles)
        raise MeshError(path, f"triangles {first} and {second} use edge {_edge(vertices, heads[order[same[0]]], tails[order[same[0]]])} "
                              "in the same direction: they disagree in orientation, or the edge has more than two faces")
    lonely = np.flatnonzero(~np.isin(tails * n + heads, codes))
    if lonely.size:
        k = lonely[0]
        raise MeshError(path, f"edge {_edge(vertices, heads[k], tails[k])} has one face only (triangle {k % len(triangles)}): "
                              "the surface is open")
    keys = np.sort(triangles, axis=1)
    _, first, counts = np.unique(keys, axis=0, return_index=True, return_counts=True)
    doubled = np.flatnonzero(counts > 1)
    if doubled.size:
        k = first[doubled[0]]
        twin = next(j for j in range(len(keys)) if j != k and (keys[j] == keys[k]).all())
        raise MeshError(path, f"triangles {k} and {twin} lie on the same three vertices: a doubled wall bounds no material")


def _check_volumes(path: str, mesh: Mesh) -> None:
    """Every connected piece encloses volume, and the whole mesh positive volume."""
    dets = _dets(mesh)
    pieces = _pieces(len(mesh.vertices), mesh.triangles)
    totals: dict[int, int] = {}
    for k, piece in enumerate(pieces):
        totals[piece] = totals.get(piece, 0) + dets[k]
    for piece, total in totals.items():
        if total == 0:
            k = pieces.index(piece)
            raise MeshError(path, f"the closed piece holding triangle {k} encloses no volume: it is a sheet with no thickness")
    if sum(totals.values()) < 0:
        raise MeshError(path, "is inside out: its triangles face inward, so it encloses negative volume")


def _pieces(n: int, triangles: np.ndarray) -> list[int]:
    """The connected piece of each triangle, as the root vertex of its union-find class."""
    parent = list(range(n))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b, c in triangles.tolist():
        ra, rb, rc = root(a), root(b), root(c)
        parent[rb] = ra
        parent[root(rc)] = ra
    return [root(t[0]) for t in triangles.tolist()]


def _edge(vertices: np.ndarray, a: int, b: int) -> str:
    return f"{tuple(int(x) for x in vertices[a])}-{tuple(int(x) for x in vertices[b])} (units of the file's scale)"


def pieces(mesh: Mesh) -> list[int]:
    """The connected piece of each triangle of `mesh` (lower.py checks each piece's
    orientation against its nesting)."""
    return _pieces(len(mesh.vertices), mesh.triangles)
