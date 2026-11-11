/-
Runs the kernel's three loops beside the versions of `PetraProofs/Provable/` and prints, for
each, how many inputs were tried and whether every result was the same. This is a test and
not a proof: the logic cannot read the kernel's loops. Run it with

  lake env lean Compare.lean

after `lake build`. Each line should end in `true`.
-/
import PetraProofs.Provable.Isqrt
import PetraProofs.Provable.OddSeries
import PetraProofs.Provable.ExpAt

open Petra

def sameIv (a b : Iv) : Bool := a.lo == b.lo && a.hi == b.hi

/-- The integers 0 to 5000, and 600 large ones around powers of two and squares. -/
def sqrtInputs : List Nat :=
  List.range 5001 ++ (List.range 100).flatMap (fun k =>
    [2 ^ (k + 60) - 1, 2 ^ (k + 60), 2 ^ (k + 60) + 1, (3 ^ (k + 20)) * (3 ^ (k + 20)),
     (3 ^ (k + 20)) * (3 ^ (k + 20)) - 1, 10 ^ (k + 30) + 7])

#eval ("isqrt", sqrtInputs.length, sqrtInputs.all fun n => isqrt n == Provable.isqrt n)

def oddInputs : List (Rat × Int × Nat) :=
  [mkRat 1 3, mkRat (-1) 3, mkRat 1 5, mkRat 1 239, 0, mkRat 1 7, mkRat (-2) 9, mkRat 33 100,
   mkRat 1 1000000, mkRat (-17) 91].flatMap (fun x =>
    [(1 : Int), -1].flatMap (fun s => [0, 1, 8, 96, 128, 224, 608].map (fun p => (x, s, p))))

#eval ("oddSeries", oddInputs.length,
  oddInputs.all fun (x, s, p) => sameIv (oddSeries x s p) (Provable.oddSeries x s p))

def expInputs : List (Rat × Nat) :=
  [0, 1, -1, mkRat 1 2, mkRat (-1) 2, mkRat 1 1000, mkRat 7 3, mkRat (-22) 7, 10, -10, 37,
   mkRat 123456789 1000000, mkRat (-99) 2, mkRat 1 3].flatMap (fun x =>
    [0, 8, 128, 224].map (fun p => (x, p)))

#eval ("expAt", expInputs.length,
  expInputs.all fun (x, p) => sameIv (expAt x p) (Provable.expAt x p))
