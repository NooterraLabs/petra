"""`python3.11 -m bench.attack.repro DIR`: run a kept difference again. See found.py."""
import sys

from .found import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
