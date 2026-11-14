# Clearance certificates

A clearance certificate is a JSON file that claims two parts are at least a stated distance apart and carries the evidence for it. `check-clearance` is a small Lean program that tests the evidence in exact rational arithmetic and prints `PROVED` or `REFUSED`. The program that writes a certificate is not trusted.

## What a certificate holds

- Two parts, A and B. A part is a list of solids in one frame: a block with its faces square to the axes less round holes that run through it, a round bar along an axis, or a convex solid with flat faces.
- The clearance it claims.
- Hints that turn each round face into flat ones on the safe side: sides for a bar, a polygon for a hole. The checker tests every hint, so each part lies inside a union of convex pieces.
- A witness for every pair of pieces, one of A and one of B: weights on their faces that add up to a plane between the two.

The format is `clearance-cert/0`. The docstring of `reference/check_clearance.py` describes it in full. `samples/c1_pin_in_bore_32.json` is a pin in the bore of a block.

## What is proved

`Certify.Clearance.check_sound`, in `proofs/CertifyProofs/ClearanceSound.lean`: if `check cert` returns a verdict, then every point of part A is at least `cert.clearance` from every point of part B.

Points are triples of real numbers and the distance is the usual one. `Solid.points` in `proofs/CertifyProofs/Clearance.lean` says which points a solid has, and is the one definition to read against the format. The proof has no `sorry` and rests on Lean's three standard axioms only: `propext`, `Classical.choice` and `Quot.sound`. `results/axioms.txt` is the output of the command below.

## What is assumed

- The reading of the JSON. The theorem is about the certificate that `parse` returns. That `parse` reads a file as the format says is tested, not proved.
- That the solids describe the real parts.
- Tolerances. The certificate is about the sizes written in it.
- Deflection under load, and thermal growth.
- Lean's kernel, its compiler and runtime, and Mathlib's real numbers.

A hole given no polygon is left filled and its fields are not read. The theorem is then about a part with more material, which is the safe side.

## What is tested

`check-clearance` is `reference/check_clearance.py` written again in Lean. `run_controls.sh` rebuilds the controls and runs both checkers on every file.

| Set | Files | Proved by Python | Proved by Lean | Verdicts that differ |
|---|---|---|---|---|
| the sample, 56 case certificates, 11 probes, and 322 controls: spoiled files, claims too large, lying hints, and harmless changes that must still pass | 390 | 111 | 111 | 0 |
| a good certificate with one number written loosely | 8 | 6 | 1 | 5 |

In the first set the first line of the two outputs is the same on every file too. In the second set the five that differ all go one way, Python accepts and Lean refuses: a number with a decimal point, an index written as a string or with a decimal point, and a block with a fourth coordinate. The records are `results/clearance_compare.json` and `results/forms_clearance.json`.

## Run it

```sh
cd certify
lake build
.lake/build/bin/check-clearance samples/c1_pin_in_bore_32.json
```

The checker needs the Lean toolchain alone, the same one as `kernel/`. It exits with 0 for `PROVED` and 1 for `REFUSED`.

```sh
cd proofs
lake build
lake env lean Axioms.lean
```

`proofs/` is a second package. It depends on Mathlib, which the first build fetches, and on the checker by path.

```sh
sh run_controls.sh
```

This needs Python 3 with `venv`. It installs numpy and scipy for the generator into a working folder.

## Status

The checker runs on its own. It is not yet wired into `petra check`. A stress checker is in work.
