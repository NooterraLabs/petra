/-
The axioms each main theorem rests on. `lake build PetraProofs.Axioms` prints them, and
docs/proved.md holds the output. `propext`, `Classical.choice` and `Quot.sound` are Lean's
standard three. Any other name here is a finding.
-/
import PetraProofs.Rule
import PetraProofs.Provable.Isqrt
import PetraProofs.Provable.OddSeries
import PetraProofs.Provable.ExpAt

-- the exact interval operations
#print axioms Petra.Iv.add_sound
#print axioms Petra.Iv.neg_sound
#print axioms Petra.Iv.mul_sound
#print axioms Petra.Iv.abs_sound
#print axioms Petra.Iv.min_sound
#print axioms Petra.Iv.max_sound
#print axioms Petra.Iv.div_sound
#print axioms Petra.powInt_sound
#print axioms Petra.fits_ok
-- the rounded functions, each from its stated assumption
#print axioms Petra.grid_sound
#print axioms Petra.iSqrt_sound
#print axioms Petra.piIv_sound
#print axioms Petra.iLn_sound
#print axioms Petra.iExp_sound
-- one step, and the pick
#print axioms Petra.Node.enclose_sound
#print axioms Petra.pick_sound
-- the walk and the rule
#print axioms Petra.Tape.eval_sound
#print axioms Petra.Partition.leaves_cover
#print axioms Petra.Tape.proved_sound_exact
#print axioms Petra.Tape.refuted_sound_exact
#print axioms Petra.Tape.proved_sound
#print axioms Petra.Tape.refuted_sound
-- the versions without `while` meet the assumptions
#print axioms Petra.Provable.isqrt_spec
#print axioms Petra.Provable.oddSeries_spec
#print axioms Petra.Provable.expAt_spec
