from check import run

cands = {
    "B: L4x4x1/4, 5 x 3/4 A325-N, gb 2.25 gs 2.25": dict(
        db=0.75, grade="A325", thr="N", n=5, s=3.0, Lev=1.75, t=0.25, leg_beam=4.0,
        leg_sup=4.0, beam_gauge=2.25, support_gauge=2.25, beam_edge=1.75, top=3.5),
    "B2: L4x4x1/4, 5 x 3/4 A325-N, gb 2.25 gs 2.0": dict(
        db=0.75, grade="A325", thr="N", n=5, s=3.0, Lev=1.75, t=0.25, leg_beam=4.0,
        leg_sup=4.0, beam_gauge=2.25, support_gauge=2.0, beam_edge=1.75, top=3.5),
    "A: L4x4x5/16, 4 x 7/8 A325-N, gb 2.25 gs 2.0": dict(
        db=0.875, grade="A325", thr="N", n=4, s=3.0, Lev=1.75, t=0.3125, leg_beam=4.0,
        leg_sup=4.0, beam_gauge=2.25, support_gauge=2.0, beam_edge=1.75, top=3.5),
}
for k, c in cands.items():
    print("=" * 70)
    print(k)
    run(c)
