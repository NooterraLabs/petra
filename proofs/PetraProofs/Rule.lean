/-
The rule. A partition's leaves cover the box. So when `Tape.proved` returns no failure, every
root has a value at most zero at every point of the box, and when `Tape.refuted` returns
none, the root it names has a value above zero at the point given, which lies in the box.

`Tape.proved` and `Tape.refuted` take the work left and give it back. No theorem here reads
it: a proof that runs out of work returns a failure, and the theorems are about the proofs
that return none.
-/
import PetraProofs.Eval

namespace Petra

/-! ## The leaves of a partition cover the box -/

theorem InBox.set {box : Array Iv} {ρ : Nat → ℝ} {k : Nat} {x : Iv} (h : InBox box ρ)
    (hx : k < box.size → x.Holds (ρ k)) : InBox (box.setIfInBounds k x) ρ := by
  intro j hj
  have hj' : j < box.size := by simpa using hj
  rw [getElem!_setIfInBounds]
  split_ifs with hk
  · obtain ⟨rfl, _⟩ := hk
    exact hx hj'
  · exact h j hj'

/-- The walk over the leaves, for any property `V` of the caches that every step of the tape
keeps. If it returns no failure, every root has a value at most zero at every point of the
box it started from. A split hands the points at or below its cut to one half and the
points at or above it to the other, so every point is in a leaf. This holds for any split:
the walk needs no check of the partition's shape. -/
theorem Tape.walk_sound {t : Tape} {need : Array Bool} {last : Array Nat} {V : Caches → Prop}
    (hwf : t.WF) (hstep : ∀ node ∈ t.nodes, node.StepSound V)
    (hroots : ∀ r ∈ t.roots, r < t.nodes.size → need[r]! = true)
    (hneed : ∀ i (hi : i < t.nodes.size), need[i]! = true →
      ∀ j ∈ t.nodes[i].reads, need[j]! = true) :
    ∀ (p : Partition) (box : Array Iv) (n work : Nat) (c c' : Caches) (n' left : Nat),
      box.size = t.inputs.size → V c →
      t.walk need last p box n work c = .ok ((none, n', left), c') →
      V c' ∧ ∀ ρ, InBox box ρ → ∀ root ∈ t.roots, ∃ x, t.value ρ root = some x ∧ x ≤ 0 := by
  intro p
  induction p with
  | leaf =>
    intro box n work c c' n' left hsize hc h
    unfold Tape.walk at h
    obtain ⟨w, c1, heval, hret⟩ := M.bind_ok h
    dsimp only at hret
    obtain ⟨hr, rfl⟩ := M.pure_ok hret
    obtain ⟨hcv, hev⟩ := Tape.eval_sound hwf hstep hneed hsize hc heval
    refine ⟨hcv, ?_⟩
    have hwhy := congrArg Prod.fst hr
    dsimp only at hwhy
    -- no root has a failure, and no root's upper end is above zero
    cases hearly : earliest w.bad t.roots with
    | some f =>
      rw [hearly] at hwhy
      cases hwhy
    | none =>
      rw [hearly] at hwhy
      dsimp only at hwhy
      by_cases hall : (t.roots.all fun root => decide (w.v[root]!.hi ≤ 0)) = true
      swap
      · rw [if_neg hall] at hwhy
        cases hwhy
      intro ρ hρ root hroot
      have hbad := earliest_none hearly
      have hlt := hwf.roots root hroot
      obtain ⟨x, hx, hxv⟩ := hev ρ hρ root hlt (hroots root hroot hlt) (hbad root hroot)
      have hle : w.v[root]!.hi ≤ 0 :=
        of_decide_eq_true (Array.all_eq_true_iff_forall_mem.mp hall root hroot)
      have hhi : ((w.v[root]!.hi : ℚ) : ℝ) ≤ 0 := by exact_mod_cast hle
      exact ⟨x, hx, hxv.2.trans hhi⟩
  | split k cut below above ihb iha =>
    intro box n work c c' n' left hsize hc h
    unfold Tape.walk at h
    dsimp only at h
    obtain ⟨⟨why, n1, work1⟩, c1, hlow, hrest⟩ := M.bind_ok h
    dsimp only at hrest
    cases why with
    | some reason =>
      dsimp only at hrest
      obtain ⟨hr, -⟩ := M.pure_ok hrest
      cases hr
    | none =>
      dsimp only at hrest
      obtain ⟨hc1, hbelow⟩ := ihb _ n work c c1 n1 work1 (by simpa using hsize) hc hlow
      obtain ⟨hc', habove⟩ := iha _ n1 work1 c1 c' n' left (by simpa using hsize) hc1 hrest
      refine ⟨hc', fun ρ hρ root hroot => ?_⟩
      rcases le_total (ρ k) (cut : ℝ) with hle | hge
      · exact hbelow ρ (hρ.set (fun hk => ⟨(hρ k hk).1, hle⟩)) root hroot
      · exact habove ρ (hρ.set (fun hk => ⟨hge, (hρ k hk).2⟩)) root hroot

/-! ## A proof by partition -/

/-- The rule for a proof, for any property `V` of the caches that every step of the tape
keeps. The two theorems after it are its two readings. -/
theorem Tape.proved_sound_of {t : Tape} {p : Partition} {work left : Nat} {c c' : Caches}
    {V : Caches → Prop} (hstep : ∀ node ∈ t.nodes, node.StepSound V) (hc : V c)
    (h : t.proved p work c = .ok ((none, left), c')) :
    V c' ∧ ∀ ρ, InBox (t.inputs.map (·.range)) ρ →
      ∀ root ∈ t.roots, ∃ x, t.value ρ root = some x ∧ x ≤ 0 := by
  unfold Tape.proved at h
  dsimp only at h
  split_ifs at h with hfee
  · obtain ⟨hr, -⟩ := M.pure_ok h
    cases hr
  cases hwf1 : t.wellFormed with
  | error why =>
    rw [hwf1] at h
    dsimp only at h
    obtain ⟨hr, -⟩ := M.pure_ok h
    cases hr
  | ok u =>
    rw [hwf1] at h
    dsimp only at h
    have hwf := Tape.wellFormed_ok hwf1
    cases hshape : p.shape (t.inputs.map (·.range)) 0 with
    | error why =>
      rw [hshape] at h
      dsimp only at h
      obtain ⟨hr, -⟩ := M.pure_ok h
      cases hr
    | ok u' =>
      rw [hshape] at h
      dsimp only at h
      obtain ⟨⟨why, n, work'⟩, c1, hwalk, hret⟩ := M.bind_ok h
      dsimp only at hret
      obtain ⟨hr, hcc⟩ := M.pure_ok hret
      cases hr
      rw [hcc]
      obtain ⟨-, hn2, hn3⟩ := Tape.needed_spec hwf t.roots
      exact Tape.walk_sound hwf hstep hn2 hn3 p _ 0 _ c c1 n left (by simp) hc hwalk

/-! ## A refutation by a point -/

/-- The rule for a refutation, for any property `V` of the caches that every step of the
tape keeps. -/
theorem Tape.refuted_sound_of {t : Tape} {point : Array ℚ} {which work left : Nat}
    {c c' : Caches} {V : Caches → Prop} (hstep : ∀ node ∈ t.nodes, node.StepSound V) (hc : V c)
    (h : t.refuted point which work c = .ok ((none, left), c')) :
    V c' ∧ ∃ root, t.roots[which]? = some root ∧
      InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) ∧
      ∃ x, t.value (fun k => ((point[k]! : ℚ) : ℝ)) root = some x ∧ 0 < x := by
  unfold Tape.refuted at h
  dsimp only at h
  by_cases hfee : work < t.fee 1 + SPLIT * t.inputs.size
  · rw [if_pos hfee] at h
    obtain ⟨hr, -⟩ := M.pure_ok h
    cases hr
  rw [if_neg hfee] at h
  cases hwf1 : t.wellFormed with
  | error why =>
    rw [hwf1] at h
    dsimp only at h
    obtain ⟨hr, -⟩ := M.pure_ok h
    cases hr
  | ok u =>
    rw [hwf1] at h
    dsimp only at h
    have hwf := Tape.wellFormed_ok hwf1
    cases hroot : t.roots[which]? with
    | none =>
      rw [hroot] at h
      dsimp only at h
      obtain ⟨hr, -⟩ := M.pure_ok h
      cases hr
    | some root =>
      rw [hroot] at h
      dsimp only at h
      by_cases hsz : (point.size != t.inputs.size) = true
      · rw [if_pos hsz] at h
        obtain ⟨hr, -⟩ := M.pure_ok h
        cases hr
      rw [if_neg hsz] at h
      by_cases hout : (!(point.zip t.inputs).all fun p => p.2.range.has p.1) = true
      · rw [if_pos hout] at h
        obtain ⟨hr, -⟩ := M.pure_ok h
        cases hr
      rw [if_neg hout] at h
      have hsz' : point.size = t.inputs.size := by simpa using hsz
      have hall : ((point.zip t.inputs).all fun p => p.2.range.has p.1) = true := by simpa using hout
      obtain ⟨w, c1, heval, h3⟩ := M.bind_ok h
      -- every value of the point lies in its input's range
      have hhas : ∀ i (h1 : i < point.size) (h2 : i < t.inputs.size),
          t.inputs[i].range.has point[i] = true := by
        intro i h1 h2
        have hmem : (point[i], t.inputs[i]) ∈ point.zip t.inputs := by
          rw [Array.mem_iff_getElem]
          exact ⟨i, by simp; omega, by simp⟩
        exact Array.all_eq_true_iff_forall_mem.mp hall _ hmem
      have hbox : InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) := by
        intro k hk
        have hk2 : k < t.inputs.size := by simpa using hk
        have hk1 : k < point.size := by omega
        have hh := hhas k hk1 hk2
        simp only [Iv.has, Bool.and_eq_true, decide_eq_true_eq] at hh
        rw [getElem!_pos _ k hk, Array.getElem_map]
        show ((t.inputs[k].range.lo : ℚ) : ℝ) ≤ ((point[k]! : ℚ) : ℝ) ∧
          ((point[k]! : ℚ) : ℝ) ≤ ((t.inputs[k].range.hi : ℚ) : ℝ)
        rw [getElem!_pos point k hk1]
        exact ⟨by exact_mod_cast hh.1, by exact_mod_cast hh.2⟩
      have hpt : InBox (point.map Iv.pt) (fun k => ((point[k]! : ℚ) : ℝ)) := by
        intro k hk
        have hk1 : k < point.size := by simpa using hk
        rw [getElem!_pos _ k hk, Array.getElem_map]
        show ((point[k] : ℚ) : ℝ) ≤ ((point[k]! : ℚ) : ℝ) ∧
          ((point[k]! : ℚ) : ℝ) ≤ ((point[k] : ℚ) : ℝ)
        rw [getElem!_pos point k hk1]
        exact ⟨le_refl _, le_refl _⟩
      have hrmem : root ∈ t.roots := Array.mem_of_getElem? hroot
      have hrlt := hwf.roots root hrmem
      obtain ⟨-, hn2, hn3⟩ := Tape.needed_spec hwf #[root]
      obtain ⟨hcv, hev⟩ := Tape.eval_sound hwf hstep hn3 (by simpa using hsz') hc heval
      cases hb : w.bad[root]! with
      | some f =>
        rw [hb] at h3
        dsimp only at h3
        obtain ⟨hr, -⟩ := M.pure_ok h3
        cases hr
      | none =>
        rw [hb] at h3
        dsimp only at h3
        split_ifs at h3 with hlo
        swap
        · obtain ⟨hr, -⟩ := M.pure_ok h3
          cases hr
        obtain ⟨-, rfl⟩ := M.pure_ok h3
        obtain ⟨x, hx, hxv⟩ := hev _ hpt root hrlt (hn2 root (by simp) hrlt) hb
        have hlo' : (0 : ℝ) < ((w.v[root]!.lo : ℚ) : ℝ) := by exact_mod_cast hlo
        exact ⟨hcv, root, rfl, hbox, x, hx, lt_of_lt_of_le hlo' hxv.1⟩

/-! ## The theorems

`Tape.proved_sound` and `Tape.refuted_sound` are for any tape. They start from valid caches.
The kernel starts from the empty caches, which are valid (`Caches.valid_empty`), and each
theorem hands valid caches to the next proof. `Tape.proved_sound_exact` and
`Tape.refuted_sound_exact` are for a tape with no `sqrt`, `pi`, `ln` or `exp` node. Such a
tape reads no cache, so they start from any caches.

No theorem here takes a hypothesis about the kernel: each is about `Tape.proved` and
`Tape.refuted` as kernel/Petra/Tape.lean defines them, down to the last loop, with the work
they are given and any work at all. -/

/-- A tape of exact nodes, proved. If `Tape.proved` returns no failure, from any caches and
with any work, then at every point of the box (each input in its range) every root has a
value, and the value is at most zero. -/
theorem Tape.proved_sound_exact {t : Tape} {p : Partition} {work left : Nat} {c c' : Caches}
    (hex : ∀ node ∈ t.nodes, node.Exact) (h : t.proved p work c = .ok ((none, left), c')) :
    ∀ ρ, InBox (t.inputs.map (·.range)) ρ →
      ∀ root ∈ t.roots, ∃ x, t.value ρ root = some x ∧ x ≤ 0 :=
  (Tape.proved_sound_of (V := fun _ => True) (fun node hn => (hex node hn).stepSound)
    True.intro h).2

/-- A tape of exact nodes, refuted. If `Tape.refuted` returns no failure, from any caches and
with any work, the point lies in the box and the root it names has a value there that is
above zero. -/
theorem Tape.refuted_sound_exact {t : Tape} {point : Array ℚ} {which work left : Nat}
    {c c' : Caches} (hex : ∀ node ∈ t.nodes, node.Exact)
    (h : t.refuted point which work c = .ok ((none, left), c')) :
    ∃ root, t.roots[which]? = some root ∧
      InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) ∧
      ∃ x, t.value (fun k => ((point[k]! : ℚ) : ℝ)) root = some x ∧ 0 < x :=
  (Tape.refuted_sound_of (V := fun _ => True) (fun node hn => (hex node hn).stepSound)
    True.intro h).2

/-- Any tape, proved. If `Tape.proved` returns no failure from valid caches, with any work,
then at every point of the box every root has a value, and the value is at most zero. The
caches stay valid. -/
theorem Tape.proved_sound {t : Tape} {p : Partition} {work left : Nat} {c c' : Caches}
    (hc : c.Valid) (h : t.proved p work c = .ok ((none, left), c')) :
    c'.Valid ∧ ∀ ρ, InBox (t.inputs.map (·.range)) ρ →
      ∀ root ∈ t.roots, ∃ x, t.value ρ root = some x ∧ x ≤ 0 :=
  Tape.proved_sound_of (fun node _ => node.stepSound) hc h

/-- Any tape, refuted. If `Tape.refuted` returns no failure from valid caches, with any work,
the point lies in the box and the root it names has a value there that is above zero. The
caches stay valid. -/
theorem Tape.refuted_sound {t : Tape} {point : Array ℚ} {which work left : Nat} {c c' : Caches}
    (hc : c.Valid) (h : t.refuted point which work c = .ok ((none, left), c')) :
    c'.Valid ∧ ∃ root, t.roots[which]? = some root ∧
      InBox (t.inputs.map (·.range)) (fun k => ((point[k]! : ℚ) : ℝ)) ∧
      ∃ x, t.value (fun k => ((point[k]! : ℚ) : ℝ)) root = some x ∧ 0 < x :=
  Tape.refuted_sound_of (fun node _ => node.stepSound) hc h

end Petra
