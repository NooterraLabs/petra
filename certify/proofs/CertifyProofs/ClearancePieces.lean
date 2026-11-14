/-
The pieces hold the solids: every point of a solid lies in one of the convex pieces that
`solidPieces` makes for it. This is where the hints are shown to be on the safe side.
-/
import CertifyProofs.Clearance

namespace Certify.Clearance

/-- A point lies in a piece: it is on the inner side of every face. -/
def inPiece (P : List Face) (x : P3) : Prop := ∀ f ∈ P, f.holds x

/-! ## A bar lies inside each of its sides -/

theorem side_core {gu gv du dv R h : ℝ} (hh : 0 ≤ h)
    (hs : R * R * (gu * gu + gv * gv) ≤ h * h) (hin : du ^ 2 + dv ^ 2 ≤ R ^ 2) :
    gu * du + gv * dv ≤ h := by
  by_contra hlt
  have h1 : h * h < (gu * du + gv * dv) * (gu * du + gv * dv) :=
    mul_self_lt_mul_self hh (not_le.mp hlt)
  have hg : 0 ≤ gu * gu + gv * gv := by linarith [mul_self_nonneg gu, mul_self_nonneg gv]
  have h2 := mul_le_mul_of_nonneg_left hin hg
  have key : (gu * gu + gv * gv) * (du ^ 2 + dv ^ 2)
      - (gu * du + gv * dv) * (gu * du + gv * dv) = (gu * dv - gv * du) ^ 2 := by ring
  have e : (gu * gu + gv * gv) * R ^ 2 = R * R * (gu * gu + gv * gv) := by ring
  linarith [sq_nonneg (gu * dv - gv * du)]

theorem cylinderSide_holds {n : Nat} {axis : Axis} {cu cv radius : Rat} {side : Rat × Rat × Rat}
    {f : Face} (h : cylinderSide n axis cu cv radius side = .ok f) (x : P3)
    (hin : (axis.u x - cu) ^ 2 + (axis.v x - cv) ^ 2 ≤ (radius : ℝ) ^ 2) : f.holds x := by
  simp only [cylinderSide, bind_ok, need_ok, decide_eq_true_eq] at h
  obtain ⟨_, ⟨h0, hs⟩, h⟩ := h
  cases h
  rw [Axis.face_holds]
  have h0' : (0 : ℝ) ≤ (side.2.2 : ℝ) := by exact_mod_cast h0
  have hs' : (radius : ℝ) * radius * ((side.1 : ℝ) * side.1 + (side.2.1 : ℝ) * side.2.1) ≤
      (side.2.2 : ℝ) * side.2.2 := by exact_mod_cast hs
  have := side_core h0' hs' hin
  push_cast
  linarith

/-! ## A block less a hole lies inside the pieces cut by the hole's polygon -/

/-- At the corner q furthest along x - c, between the corners p before it and w after it:
a point x strictly left of both edges, and no nearer the centre than R, cannot be. -/
theorem corner_core {p1 p2 q1 q2 w1 w2 x1 x2 c1 c2 R : ℝ}
    (ht : 0 < (q1 - p1) * (w2 - q2) - (q2 - p2) * (w1 - q1))
    (hl0 : 0 < (q1 - p1) * (x2 - p2) - (q2 - p2) * (x1 - p1))
    (hl1 : 0 < (w1 - q1) * (x2 - q2) - (w2 - q2) * (x1 - q1))
    (hm0 : (x1 - c1) * p1 + (x2 - c2) * p2 ≤ (x1 - c1) * q1 + (x2 - c2) * q2)
    (hm1 : (x1 - c1) * w1 + (x2 - c2) * w2 ≤ (x1 - c1) * q1 + (x2 - c2) * q2)
    (hq : (q1 - c1) * (q1 - c1) + (q2 - c2) * (q2 - c2) ≤ R * R)
    (hge : R ^ 2 ≤ (x1 - c1) ^ 2 + (x2 - c2) ^ 2) : False := by
  -- x - q is a mix of p - q and w - q with weights above zero, so it points back from q
  have hU : 0 < (q1 - p1) * (x2 - q2) - (q2 - p2) * (x1 - q1) := by
    have e : (q1 - p1) * (x2 - p2) - (q2 - p2) * (x1 - p1)
        = (q1 - p1) * (x2 - q2) - (q2 - p2) * (x1 - q1) := by ring
    linarith
  have hA : ((q1 - p1) * (w2 - q2) - (q2 - p2) * (w1 - q1))
        * ((x1 - c1) * (x1 - q1) + (x2 - c2) * (x2 - q2))
      = ((q1 - p1) * (x2 - q2) - (q2 - p2) * (x1 - q1))
          * ((x1 - c1) * (w1 - q1) + (x2 - c2) * (w2 - q2))
        - ((w1 - q1) * (x2 - q2) - (w2 - q2) * (x1 - q1))
          * ((x1 - c1) * (q1 - p1) + (x2 - c2) * (q2 - p2)) := by ring
  have t1 : ((q1 - p1) * (x2 - q2) - (q2 - p2) * (x1 - q1))
      * ((x1 - c1) * (w1 - q1) + (x2 - c2) * (w2 - q2)) ≤ 0 :=
    mul_nonpos_of_nonneg_of_nonpos hU.le (by linarith)
  have t2 : 0 ≤ ((w1 - q1) * (x2 - q2) - (w2 - q2) * (x1 - q1))
      * ((x1 - c1) * (q1 - p1) + (x2 - c2) * (q2 - p2)) :=
    mul_nonneg hl1.le (by linarith)
  have hdz : (x1 - c1) * (x1 - q1) + (x2 - c2) * (x2 - q2) ≤ 0 := by
    by_contra hpos
    have := mul_pos ht (not_le.mp hpos)
    linarith
  -- so x is q itself
  have e1 : (x1 - q1) * (x1 - q1) + (x2 - q2) * (x2 - q2)
      = 2 * ((x1 - c1) * (x1 - q1) + (x2 - c2) * (x2 - q2))
        - ((x1 - c1) ^ 2 + (x2 - c2) ^ 2) + ((q1 - c1) * (q1 - c1) + (q2 - c2) * (q2 - c2)) := by ring
  have e2 : R ^ 2 = R * R := by ring
  have hz : (x1 - q1) * (x1 - q1) + (x2 - q2) * (x2 - q2) ≤ 0 := by linarith
  have hz1 : x1 - q1 = 0 :=
    mul_self_eq_zero.mp (le_antisymm (by linarith [mul_self_nonneg (x2 - q2)]) (mul_self_nonneg _))
  have hz2 : x2 - q2 = 0 :=
    mul_self_eq_zero.mp (le_antisymm (by linarith [mul_self_nonneg (x1 - q1)]) (mul_self_nonneg _))
  rw [hz1, hz2] at hU
  simp at hU

/-- A polygon that turns left at every corner, with every corner in the closed disc: a point
strictly left of every edge is strictly inside the disc. `C` gives the corners round and round. -/
theorem polygon_core (N : ℕ) (hN : 0 < N) (C : ℕ → ℝ × ℝ) (hper : ∀ i, C (i + N) = C i)
    (c : ℝ × ℝ) (R : ℝ)
    (hin : ∀ i, ((C i).1 - c.1) * ((C i).1 - c.1) + ((C i).2 - c.2) * ((C i).2 - c.2) ≤ R * R)
    (hturn : ∀ i, 0 < ((C (i + 1)).1 - (C i).1) * ((C (i + 2)).2 - (C (i + 1)).2)
      - ((C (i + 1)).2 - (C i).2) * ((C (i + 2)).1 - (C (i + 1)).1))
    (x : ℝ × ℝ)
    (hleft : ∀ i, 0 < ((C (i + 1)).1 - (C i).1) * (x.2 - (C i).2)
      - ((C (i + 1)).2 - (C i).2) * (x.1 - (C i).1)) :
    (x.1 - c.1) ^ 2 + (x.2 - c.2) ^ 2 < R ^ 2 := by
  by_contra hge
  have hge := not_lt.mp hge
  obtain ⟨j, -, hj⟩ := Finset.exists_max_image (Finset.range N)
    (fun i => (x.1 - c.1) * (C i).1 + (x.2 - c.2) * (C i).2) ⟨0, Finset.mem_range.mpr hN⟩
  have hmul : ∀ k i, C (i + N * k) = C i := by
    intro k
    induction k with
    | zero => intro i; simp
    | succ k ih =>
      intro i
      have : i + N * (k + 1) = (i + N * k) + N := by ring
      rw [this, hper, ih]
  have hmod : ∀ i, C (i % N) = C i := by
    intro i
    have := hmul (i / N) (i % N)
    rw [Nat.mod_add_div] at this
    exact this.symm
  have hmax : ∀ i, (x.1 - c.1) * (C i).1 + (x.2 - c.2) * (C i).2
      ≤ (x.1 - c.1) * (C j).1 + (x.2 - c.2) * (C j).2 := by
    intro i
    have := hj (i % N) (Finset.mem_range.mpr (Nat.mod_lt _ hN))
    simpa [hmod] using this
  obtain ⟨i0, hi0⟩ : ∃ i0, i0 + 1 = j + N := ⟨j + N - 1, by omega⟩
  have e1 : C (i0 + 1) = C j := by rw [hi0, hper]
  have e2 : C (i0 + 2) = C (j + 1) := by
    have : i0 + 2 = (j + 1) + N := by omega
    rw [this, hper]
  have ht := hturn i0
  have hl0 := hleft i0
  rw [e1, e2] at ht
  rw [e1] at hl0
  exact corner_core ht hl0 (hleft j) (hmax i0) (hmax (j + 1)) (hin j) hge

theorem holeEdge_ok {n : Nat} {hole : Hole} {i : Nat} {f : Face} (h : holeEdge n hole i = .ok f) :
    ((corner hole.polygon i).1 - hole.cu) * ((corner hole.polygon i).1 - hole.cu)
        + ((corner hole.polygon i).2 - hole.cv) * ((corner hole.polygon i).2 - hole.cv)
        ≤ hole.radius * hole.radius ∧
    ((corner hole.polygon (i + 1)).1 - (corner hole.polygon i).1)
        * ((corner hole.polygon (i + 2)).2 - (corner hole.polygon (i + 1)).2)
      - ((corner hole.polygon (i + 1)).2 - (corner hole.polygon i).2)
        * ((corner hole.polygon (i + 2)).1 - (corner hole.polygon (i + 1)).1) > 0 ∧
    f = hole.axis.face (-((corner hole.polygon (i + 1)).2 - (corner hole.polygon i).2))
      ((corner hole.polygon (i + 1)).1 - (corner hole.polygon i).1) 0
      (-((corner hole.polygon (i + 1)).2 - (corner hole.polygon i).2) * (corner hole.polygon i).1
        + ((corner hole.polygon (i + 1)).1 - (corner hole.polygon i).1) * (corner hole.polygon i).2) := by
  simp only [holeEdge, bind_ok, need_ok, decide_eq_true_eq] at h
  obtain ⟨_, h1, _, h2, h3⟩ := h
  cases h3
  exact ⟨h1, h2, rfl⟩

/-- A point of the block that is not inside the hole lies on the kept side of some edge of
the hole's polygon. -/
theorem holeCut_covers {n : Nat} {hole : Hole} {faces : List Face}
    (h : holeCut n hole = .ok faces) (x : P3)
    (hx : (hole.radius : ℝ) ^ 2 ≤ (hole.axis.u x - hole.cu) ^ 2 + (hole.axis.v x - hole.cv) ^ 2) :
    ∃ f ∈ faces, f.holds x := by
  simp only [holeCut, bind_ok, need_ok, decide_eq_true_eq] at h
  obtain ⟨_, _, _, hN, hcol⟩ := h
  by_contra hno
  have hno : ∀ f ∈ faces, ¬ f.holds x := fun f hf hfx => hno ⟨f, hf, hfx⟩
  have hN0 : 0 < hole.polygon.size := by omega
  have hc : ∀ i k, corner hole.polygon (i % hole.polygon.size + k) = corner hole.polygon (i + k) := by
    intro i k
    simp [corner, Nat.mod_add_mod]
  have hfacts : ∀ i : ℕ,
      (((corner hole.polygon i).1 : ℝ) - hole.cu) * (((corner hole.polygon i).1 : ℝ) - hole.cu)
        + (((corner hole.polygon i).2 : ℝ) - hole.cv) * (((corner hole.polygon i).2 : ℝ) - hole.cv)
        ≤ (hole.radius : ℝ) * hole.radius ∧
      0 < (((corner hole.polygon (i + 1)).1 : ℝ) - (corner hole.polygon i).1)
          * (((corner hole.polygon (i + 2)).2 : ℝ) - (corner hole.polygon (i + 1)).2)
        - (((corner hole.polygon (i + 1)).2 : ℝ) - (corner hole.polygon i).2)
          * (((corner hole.polygon (i + 2)).1 : ℝ) - (corner hole.polygon (i + 1)).1) ∧
      0 < (((corner hole.polygon (i + 1)).1 : ℝ) - (corner hole.polygon i).1)
          * (hole.axis.v x - (corner hole.polygon i).2)
        - (((corner hole.polygon (i + 1)).2 : ℝ) - (corner hole.polygon i).2)
          * (hole.axis.u x - (corner hole.polygon i).1) := by
    intro i
    obtain ⟨f, hf, he⟩ := collect_mem_in hcol (i % hole.polygon.size)
      (List.mem_range.mpr (Nat.mod_lt _ hN0))
    obtain ⟨h1, h2, h3⟩ := holeEdge_ok he
    have hnh := hno f hf
    rw [h3, Axis.face_holds] at hnh
    have c0 := hc i 0
    simp only [Nat.add_zero] at c0
    rw [hc i 1, hc i 2, c0] at h2
    rw [c0] at h1
    rw [hc i 1, c0] at hnh
    refine ⟨by exact_mod_cast h1, by exact_mod_cast h2, ?_⟩
    have hnh := not_le.mp hnh
    push_cast at hnh
    linarith
  have := polygon_core hole.polygon.size hN0
    (fun i => (((corner hole.polygon i).1 : ℝ), ((corner hole.polygon i).2 : ℝ)))
    (fun i => by simp [corner]) ((hole.cu : ℝ), (hole.cv : ℝ)) (hole.radius : ℝ)
    (fun i => (hfacts i).1) (fun i => (hfacts i).2.1) (hole.axis.u x, hole.axis.v x)
    (fun i => (hfacts i).2.2)
  exact absurd this (not_lt.mpr hx)

/-! ## Every solid lies inside its pieces -/

theorem product_covers {x : P3} : ∀ {cuts : List (List Face)},
    (∀ cut ∈ cuts, ∃ f ∈ cut, f.holds x) → ∃ choice ∈ product cuts, ∀ f ∈ choice, f.holds x
  | [], _ => ⟨[], by simp [product], by simp⟩
  | l :: ls, h => by
    obtain ⟨f, hf, hfx⟩ := h l (by simp)
    obtain ⟨ch, hch, hall⟩ := product_covers (cuts := ls) (fun cut hc => h cut (by simp [hc]))
    refine ⟨f :: ch, ?_, ?_⟩
    · simp only [product, List.mem_flatMap, List.mem_map]
      exact ⟨f, hf, ch, hch, rfl⟩
    · intro g hg
      rcases List.mem_cons.mp hg with rfl | hg
      · exact hfx
      · exact hall g hg

theorem solidPieces_covers {n : Nat} {s : Solid} {ps : List (List Face)}
    (h : solidPieces n s = .ok ps) : ∀ x ∈ s.points, ∃ P ∈ ps, inPiece P x := by
  intro x hx
  cases s with
  | polytope faces =>
    simp only [solidPieces, bind_ok, need_ok] at h
    obtain ⟨_, _, h⟩ := h
    cases h
    exact ⟨faces, by simp, hx⟩
  | cylinder axis cu cv radius lo hi sides =>
    simp only [solidPieces, bind_ok, need_ok] at h
    obtain ⟨_, _, sideFaces, hs, h⟩ := h
    cases h
    obtain ⟨hlo, hhi, hin⟩ := hx
    refine ⟨axis.face 0 0 (-1) (-lo) :: axis.face 0 0 1 hi :: sideFaces, by simp, ?_⟩
    intro f hf
    simp only [List.mem_cons] at hf
    rcases hf with rfl | rfl | hf
    · rw [Axis.face_holds]; push_cast; linarith
    · rw [Axis.face_holds]; push_cast; linarith
    · obtain ⟨side, _, hside⟩ := collect_mem_out hs f hf
      exact cylinderSide_holds hside x hin
  | box lo hi holes =>
    simp only [solidPieces, bind_ok, need_ok] at h
    obtain ⟨_, _, cuts, hcuts, h⟩ := h
    cases h
    obtain ⟨hx1, hx2, hx3, hholes⟩ := hx
    have hall : ∀ cut ∈ cuts, ∃ f ∈ cut, f.holds x := by
      intro cut hcut
      obtain ⟨hole, hh, hc⟩ := collect_mem_out hcuts cut hcut
      exact holeCut_covers hc x (hholes hole hh)
    obtain ⟨choice, hch, hcx⟩ := product_covers hall
    refine ⟨boxBase lo hi ++ choice, List.mem_map.mpr ⟨choice, hch, rfl⟩, ?_⟩
    intro f hf
    rcases List.mem_append.mp hf with hf | hf
    · simp only [boxBase, List.mem_cons, List.mem_nil_iff, or_false] at hf
      rcases hf with rfl | rfl | rfl | rfl | rfl | rfl <;> simp only [Face.holds] <;>
        push_cast <;> linarith
    · exact hcx f hf

/-- Every point of a part lies in one of the part's pieces. -/
theorem pieces_covers {solids : List Solid} {ps : List (List Face)} (h : pieces solids = .ok ps) :
    ∀ x ∈ partPoints solids, ∃ P ∈ ps, inPiece P x := by
  simp only [pieces, bind_ok] at h
  obtain ⟨pss, hpss, h⟩ := h
  cases h
  rintro x ⟨s, hs, hx⟩
  obtain ⟨k, p, hp, hk⟩ := collectIdx_mem_in hpss s hs
  obtain ⟨P, hP, hPx⟩ := solidPieces_covers hk x hx
  exact ⟨P, List.mem_flatten.mpr ⟨p, hp, hP⟩, hPx⟩

end Certify.Clearance
