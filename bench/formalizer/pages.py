"""Render pages of a standard's PDF as images, so a transcriber sees what is typeset.

    python bench/formalizer/pages.py FILE.pdf FIRST[-LAST] [--dpi N] [--out DIR]

Pages are numbered from 1 as the file counts them, not as they are printed. The images go
to DIR, by default a folder for this file under the system's temporary directory, and the
command prints each path. A standard is licensed: the images are for reading and are not
to be kept, committed or sent anywhere. Needs PyMuPDF (`pip install pymupdf`).
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path


def render(pdf: Path, first: int, last: int, out: Path, dpi: int) -> list[Path]:
    import pymupdf

    out.mkdir(parents=True, exist_ok=True)
    written = []
    with pymupdf.open(pdf) as doc:
        if not 1 <= first <= last <= doc.page_count:
            raise SystemExit(f"{pdf.name} has pages 1 to {doc.page_count}")
        for number in range(first, last + 1):
            page = doc[number - 1]
            scans = page.get_images(full=True)
            if len(scans) == 1 and not page.get_text().strip():
                # A scanned page is one picture. Its own bytes are written as they are: MuPDF
                # renders some of these scans as three strips, and no render adds detail.
                scan = doc.extract_image(scans[0][0])
                path = out / f"p{number:04d}.{scan['ext']}"
                path.write_bytes(scan["image"])
            else:
                path = out / f"p{number:04d}.png"
                page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False).save(path)
            written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("pages", help="one page, or FIRST-LAST")
    parser.add_argument("--dpi", type=int, default=110, help="for a page with a text layer: 110 reads body text, 160 or more a dense table. A scanned page comes at the scan's own size.")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    first, _, last = args.pages.partition("-")
    out = args.out or Path(tempfile.gettempdir()) / "petra-pages" / args.pdf.stem
    for path in render(args.pdf, int(first), int(last or first), out, args.dpi):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
