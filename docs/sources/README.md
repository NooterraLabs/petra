# sources

These files tie each value Petra takes from a standard to the page that states it. A wrong value then fails a test.

## files

- `inventory.jsonl` lists every constant, table row, equation, limit and resistance factor Petra encodes from a standard, with its module, symbol, value, clause and edition. `scripts/source_inventory.py` writes it from the registry, the steel limit-state docstrings and a short list of rules the code holds in its structure.
- `anchors.jsonl` gives each item an anchor: the document's sha256, the page, the [start, end) offsets and sha256 of the text span that states it, and the value as printed. It holds fingerprints and numbers, never the documents' text.
- `equations.json` lists the headings and equation numbers of AISC 360-22 Chapters J and K, each with its page. `scripts/source_docs.py` counts Petra's coverage of the chapters against it.

An anchor's kind is one of:

- `text`: the span states the value.
- `visual`: the PDF's text layer garbles the value, so the span pins the page by a label and `read` gives what the page image shows.
- `cell`: a cell of the shapes workbook.
- `designation`: the item's name states the value, as a 7/8 in. bolt's diameter.
- `absent`: no document on disk states it, and `reason` says why.

## documents

The documents are not in the repository. `scripts/verify_sources.py` reads them from the folder named by `PETRA_SOURCES`, or else from `docs/research/sources`, which `.gitignore` keeps out:

- `A360-22W-ewr.pdf`, AISC 360-22
- `P901-23W.pdf` and `P902-23W.pdf`, the AISC v16.0 Companion, volumes 1 and 2
- `SHAPE160.xlsx`, the AISC Shapes Database v16.0

Text is extracted with pypdf 5.1.0. Another version may lay text out differently, and the span fingerprints then fail.

## checks

`py -3.11 -m unittest tests.test_sources` runs every check.

- Without the documents, the registry must hold each anchor's value, and the inventory must match the code.
- With the documents, every anchor's document hash, span fingerprint and printed value must still hold, and `equations.json` must hold the headings and equation numbers AISC 360-22 prints. These tests skip when the documents are absent, as in public CI.
- `docs/steel_traceability.md` and the provision table in `docs/steel_connections.md` must be what `scripts/source_docs.py` writes from the inventory, the anchors and `petra/models/steel/trace.py`.

`py -3.11 scripts/verify_sources.py` runs the document checks alone.

## a new value

1. Run `py -3.11 scripts/source_inventory.py`.
2. Read the new value from the document with Petra's value hidden.
3. Add the reading to the readings folder and run `py -3.11 scripts/source_anchors.py --readings DIR`.
4. Run `py -3.11 scripts/source_docs.py`.

The readings quote the standards, so they stay outside the repository.
