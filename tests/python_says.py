"""What the Python checker says of a design, for the tests of the old path.

`petra check` exits with the kernel's verdict, and the kernel has no deck of rules for the
models' kinds, so its exit code no longer tells a design the Python checker passes from one
it leaves open. The tests of the Python checker read its own status instead, from the
`python` line of a report or the `python` key of its JSON. That status decides nothing
(tests/test_kernel_decides.py), and these tests go with the old path.
"""
import json
import re

LINE = re.compile(r"^python     the Python checker says (\w+), which decides nothing", re.M)


def python_says(out: str) -> str:
    """The Python checker's status in what `petra check` printed, as text or as JSON."""
    found = LINE.search(out)
    return found[1] if found else json.loads(out)["python"]
