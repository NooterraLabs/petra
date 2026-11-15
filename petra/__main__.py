"""`python -m petra`. Python puts the working directory first on the path of a module run with
-m, so a file there named like a module Petra loads later, a `fractions.py` or a `numpy`, would
be loaded in its place. The package itself is found by then, and its own modules are found
through it, so the working directory comes off the path here, before the command line is read.

This cannot help when the working directory holds a file named petra.py or a folder named
petra: Python loads that in the package's place before any line of Petra runs. Start the
server as `petra mcp`, which looks in no working directory."""
import os
import sys

_HERE = os.getcwd()
_OWN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:] = [p for p in sys.path if (p and os.path.abspath(p) != _HERE) or os.path.abspath(p or _HERE) == _OWN]

from .cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
