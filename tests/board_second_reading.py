"""An independent second reading of pad positions in a KiCad .kicad_pcb file.

Conventions: the board frame is KiCad's screen frame, x to the right and y
down, in millimetres. A footprint at (X, Y, A) places a pad stored at (px, py)
in its own frame at

    x = X + px * cos(A) + py * sin(A)
    y = Y - px * sin(A) + py * cos(A)

so a positive A turns the footprint counter-clockwise as seen on screen.
Bottom-side footprints take the same transform, since KiCad stores their
children already mirrored. A pad's own angle does not move its anchor.
Keys are (reference, pad number); a key seen again gets "#2", "#3", ...
appended to the pad number, in file order.
"""

import math
import re


class _Quoted(str):
    pass


_TOKEN = re.compile(
    r'(\s+)|(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+)|(.)', re.DOTALL
)
_ESCAPE = re.compile(r"\\(.)", re.DOTALL)


def _parse(text):
    root = []
    stack = [root]
    for match in _TOKEN.finditer(text):
        space, opening, closing, quoted, atom, stray = match.groups()
        if space is not None:
            continue
        if opening is not None:
            node = []
            stack[-1].append(node)
            stack.append(node)
        elif closing is not None:
            if len(stack) == 1:
                raise ValueError(f"unmatched ')' at offset {match.start()}")
            stack.pop()
        elif quoted is not None:
            stack[-1].append(_Quoted(_ESCAPE.sub(r"\1", quoted)))
        elif atom is not None:
            stack[-1].append(atom)
        else:
            raise ValueError(f"unterminated string at offset {match.start()}")
    if len(stack) != 1:
        raise ValueError("unclosed '('")
    return root


def _head(node):
    if isinstance(node, list) and node:
        first = node[0]
        if isinstance(first, str) and not isinstance(first, _Quoted):
            return first
    return None


def _children(node, name):
    return [child for child in node[1:] if _head(child) == name]


def _numbers(node):
    values = []
    for item in node[1:]:
        if isinstance(item, str) and not isinstance(item, _Quoted):
            try:
                values.append(float(item))
            except ValueError:
                pass
    return values


def _placement(node):
    ats = _children(node, "at")
    if not ats:
        return 0.0, 0.0, 0.0
    values = _numbers(ats[0])
    x = values[0] if len(values) > 0 else 0.0
    y = values[1] if len(values) > 1 else 0.0
    a = values[2] if len(values) > 2 else 0.0
    return x, y, a


def _cos_sin(degrees):
    quarter = {0.0: (1.0, 0.0), 90.0: (0.0, 1.0), 180.0: (-1.0, 0.0), 270.0: (0.0, -1.0)}
    turned = degrees % 360.0
    if turned in quarter:
        return quarter[turned]
    radians = math.radians(degrees)
    return math.cos(radians), math.sin(radians)


def _reference(footprint):
    for prop in _children(footprint, "property"):
        if len(prop) > 2 and prop[1] == "Reference" and isinstance(prop[2], str):
            return str(prop[2])
    for text in _children(footprint, "fp_text"):
        if len(text) > 2 and text[1] == "reference" and isinstance(text[2], str):
            return str(text[2])
    return ""


def _footprints(forms):
    found = []
    for form in forms:
        head = _head(form)
        if head == "footprint":
            found.append(form)
        elif head == "kicad_pcb":
            found.extend(_children(form, "footprint"))
    return found


def pad_board_positions(text: str) -> dict[tuple[str, str], tuple[float, float]]:
    positions = {}
    seen = {}
    for footprint in _footprints(_parse(text)):
        ref = _reference(footprint)
        fx, fy, fa = _placement(footprint)
        c, s = _cos_sin(fa)
        for pad in _children(footprint, "pad"):
            number = str(pad[1]) if len(pad) > 1 and isinstance(pad[1], str) else ""
            px, py, _ = _placement(pad)
            count = seen.get((ref, number), 0) + 1
            seen[(ref, number)] = count
            key = (ref, number) if count == 1 else (ref, f"{number}#{count}")
            positions[key] = (fx + px * c + py * s, fy - px * s + py * c)
    return positions
