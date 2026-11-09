"""Circuit boards read from KiCad files. Trusted. docs/boards.md is the design.

`kicad.read_board` reads a .kicad_pcb file of KiCad 6, 7, 8 or 9 into one `Board` record of
exact facts from the file, and `features` marks the footprints a later rule needs and names what
the file cannot say.
"""
from .features import Feature, Premise
from .kicad import Board, Footprint, Pad, PadKind, Side, parse_board, read_board
from .sexpr import BoardError

__all__ = ["Board", "BoardError", "Feature", "Footprint", "Pad", "PadKind", "Premise", "Side", "parse_board",
           "read_board"]
