"""Circuit boards read from KiCad files. Trusted. docs/boards.md is the design.

`kicad.read_board` reads a .kicad_pcb file of KiCad 6, 7, 8 or 9 into one `Board` record of
exact facts from the file, `features` marks the footprints a later rule needs and names what
the file cannot say, and `solid` builds the board and each part's keep-out as exact meshes
for the parts layer.
"""
from .features import Feature, Premise
from .kicad import Board, Footprint, Pad, PadKind, Side, parse_board, read_board
from .sexpr import BoardError
from .solid import Errs, Prism, board_solid, keepout

__all__ = ["Board", "BoardError", "Errs", "Feature", "Footprint", "Pad", "PadKind", "Premise", "Prism", "Side",
           "board_solid", "keepout", "parse_board", "read_board"]
