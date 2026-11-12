/-
The axioms each main theorem rests on. `lake build PetraProofs.Axioms` prints them, and
docs/proved.md holds the output. `propext`, `Classical.choice` and `Quot.sound` are Lean's
standard three. Any other name here is a finding, and `sorryAx` is an unfinished proof.
proofs/check_axioms.py reads the output and fails on either.
-/
import PetraProofs.Strict

-- the exact interval operations
#print axioms Petra.Iv.add_sound
#print axioms Petra.Iv.neg_sound
#print axioms Petra.Iv.sub_sound
#print axioms Petra.Iv.mul_sound
#print axioms Petra.Iv.abs_sound
#print axioms Petra.Iv.min_sound
#print axioms Petra.Iv.max_sound
#print axioms Petra.Iv.div_sound
#print axioms Petra.powInt_sound
#print axioms Petra.fits_ok
-- the kernel's four loops
#print axioms Petra.Loops.isqrt_spec
#print axioms Petra.Loops.oddSeries_spec
#print axioms Petra.Loops.expAt_spec
#print axioms Petra.Loops.expGo_stops
#print axioms Petra.Loops.cosAt_spec
#print axioms Petra.Loops.cosGo_stops
-- the rounded functions
#print axioms Petra.grid_sound
#print axioms Petra.iSqrt_sound
#print axioms Petra.piIv_sound
#print axioms Petra.iLn_sound
#print axioms Petra.iExp_sound
#print axioms Petra.iCos_sound
#print axioms Petra.iLn_valid
#print axioms Petra.iExp_valid
#print axioms Petra.iCos_valid
#print axioms Petra.Caches.valid_empty
-- one step, and the pick
#print axioms Petra.Node.enclose_sound
#print axioms Petra.Node.enclose_valid
#print axioms Petra.pick_sound
-- one step with its price
#print axioms Petra.pickPriced_ok
#print axioms Petra.folded_ok
#print axioms Petra.Node.tries_sound
-- the walk and the rule
#print axioms Petra.Tape.wellFormed_ok
#print axioms Petra.Tape.needed_spec
#print axioms Petra.Tape.eval_sound
#print axioms Petra.Tape.walk_sound
#print axioms Petra.Tape.proved_sound_exact
#print axioms Petra.Tape.refuted_sound_exact
#print axioms Petra.Tape.proved_sound
#print axioms Petra.Tape.refuted_sound
-- a strict inequality, as a root that is a pick
#print axioms Petra.Tape.strict_value
#print axioms Petra.Tape.proved_strict
#print axioms Petra.Tape.refuted_strict
