/-
What `Certify.Clearance.check` proves.

`check_sound`: where the check returns a verdict, every point of every solid of part A is at
least `clearance` from every point of every solid of part B. Points are real, the distance is
the usual one, and the solids are the sets `Solid.points` below: this file is the place to
read what a certificate's part means.
-/
import CertifyProofs.Read
import Certify.Clearance

namespace Certify.Clearance

/-- A point of space. -/
abbrev P3 := ℝ × ℝ × ℝ

/-- The distance between two points. -/
noncomputable def dist3 (x y : P3) : ℝ :=
  Real.sqrt ((x.1 - y.1) ^ 2 + (x.2.1 - y.2.1) ^ 2 + (x.2.2 - y.2.2) ^ 2)

/-- The point is on the inner side of the face. -/
def Face.holds (f : Face) (x : P3) : Prop :=
  (f.gx : ℝ) * x.1 + (f.gy : ℝ) * x.2.1 + (f.gz : ℝ) * x.2.2 ≤ (f.h : ℝ)

/-- The coordinates across an axis, and the one along it. -/
def Axis.u (a : Axis) (x : P3) : ℝ := match a with | .z => x.1 | .x => x.2.1 | .y => x.2.2
def Axis.v (a : Axis) (x : P3) : ℝ := match a with | .z => x.2.1 | .x => x.2.2 | .y => x.1
def Axis.t (a : Axis) (x : P3) : ℝ := match a with | .z => x.2.2 | .x => x.1 | .y => x.2.1

/-- The points of a solid. A box is the block less the open discs of its opened holes, so it
keeps the holes' walls. The sides given for a bar and the polygons given for the holes are
hints: they take no part in what the solid is. -/
def Solid.points : Solid → Set P3
  | .polytope faces => {x | ∀ f ∈ faces, f.holds x}
  | .cylinder axis cu cv radius lo hi _ =>
    {x | (lo : ℝ) ≤ axis.t x ∧ axis.t x ≤ hi ∧
      (axis.u x - cu) ^ 2 + (axis.v x - cv) ^ 2 ≤ (radius : ℝ) ^ 2}
  | .box lo hi holes =>
    {x | ((lo.1 : ℝ) ≤ x.1 ∧ x.1 ≤ hi.1) ∧ ((lo.2.1 : ℝ) ≤ x.2.1 ∧ x.2.1 ≤ hi.2.1) ∧
      ((lo.2.2 : ℝ) ≤ x.2.2 ∧ x.2.2 ≤ hi.2.2) ∧
      ∀ hole ∈ holes, (hole.radius : ℝ) ^ 2 ≤
        (hole.axis.u x - hole.cu) ^ 2 + (hole.axis.v x - hole.cv) ^ 2}

/-- The points of a part: those of any of its solids. -/
def partPoints (solids : List Solid) : Set P3 := {x | ∃ s ∈ solids, x ∈ s.points}

theorem Axis.face_holds (a : Axis) (gu gv gt h : Rat) (x : P3) :
    (a.face gu gv gt h).holds x ↔ (gu : ℝ) * a.u x + gv * a.v x + gt * a.t x ≤ h := by
  cases a <;> simp only [Axis.face, Face.holds, Axis.u, Axis.v, Axis.t] <;>
    constructor <;> intro h <;> linarith

/-! ## A witness -/

theorem combine_sound {P : Array Face} (x : P3) (hx : ∀ f ∈ P, f.holds x) :
    ∀ {ws : List (Int × Rat)} {s : Rat × Rat × Rat × Rat}, combine P ws = .ok s →
      (s.1 : ℝ) * x.1 + (s.2.1 : ℝ) * x.2.1 + (s.2.2.1 : ℝ) * x.2.2 ≤ (s.2.2.2 : ℝ)
  | [], s, h => by
    simp only [combine] at h
    cases h
    simp
  | e :: rest, s, h => by
    simp only [combine, bind_ok, need_ok, decide_eq_true_eq] at h
    obtain ⟨_, hm, h⟩ := h
    generalize hq : (if 0 ≤ e.1 then P[e.1.toNat]? else none) = q at h
    cases q with
    | none => cases h
    | some f =>
      simp only [bind_ok] at h
      obtain ⟨s', hs', h⟩ := h
      cases h
      have ih := combine_sound x hx hs'
      have hf : f ∈ P := by
        split at hq
        · exact Array.mem_of_getElem? hq
        · cases hq
      have hfx := hx f hf
      unfold Face.holds at hfx
      have hm' : (0 : ℝ) ≤ (e.2 : ℝ) := by exact_mod_cast hm
      have := mul_le_mul_of_nonneg_left hfx hm'
      push_cast
      linarith

theorem sqrt_bound {c D : ℝ} (hc : 0 ≤ c) (h : c ^ 2 ≤ D) : c ≤ Real.sqrt D := by
  calc c = Real.sqrt (c ^ 2) := (Real.sqrt_sq hc).symm
    _ ≤ Real.sqrt D := Real.sqrt_le_sqrt h

/-- The arithmetic of a witness: a direction n, a gap along it, and the clearance it shows. -/
theorem apart_core {n1 n2 n3 d1 d2 d3 gap c : ℝ}
    (hdir : 0 < n1 * n1 + n2 * n2 + n3 * n3 ∨ 0 < gap) (hgap0 : 0 ≤ gap)
    (hgap2 : c * c * (n1 * n1 + n2 * n2 + n3 * n3) ≤ gap * gap)
    (hdot : gap ≤ n1 * d1 + n2 * d2 + n3 * d3) :
    c ^ 2 ≤ d1 ^ 2 + d2 ^ 2 + d3 ^ 2 := by
  have key : (n1 * n1 + n2 * n2 + n3 * n3) * (d1 ^ 2 + d2 ^ 2 + d3 ^ 2)
      - (n1 * d1 + n2 * d2 + n3 * d3) * (n1 * d1 + n2 * d2 + n3 * d3)
      = (n1 * d2 - n2 * d1) ^ 2 + (n1 * d3 - n3 * d1) ^ 2 + (n2 * d3 - n3 * d2) ^ 2 := by ring
  have hcs : (n1 * d1 + n2 * d2 + n3 * d3) * (n1 * d1 + n2 * d2 + n3 * d3)
      ≤ (n1 * n1 + n2 * n2 + n3 * n3) * (d1 ^ 2 + d2 ^ 2 + d3 ^ 2) := by
    linarith [sq_nonneg (n1 * d2 - n2 * d1), sq_nonneg (n1 * d3 - n3 * d1), sq_nonneg (n2 * d3 - n3 * d2)]
  have hsq : gap * gap ≤ (n1 * d1 + n2 * d2 + n3 * d3) * (n1 * d1 + n2 * d2 + n3 * d3) :=
    mul_self_le_mul_self hgap0 hdot
  have hnn0 : 0 ≤ n1 * n1 + n2 * n2 + n3 * n3 := by
    linarith [mul_self_nonneg n1, mul_self_nonneg n2, mul_self_nonneg n3]
  have hpos : 0 < n1 * n1 + n2 * n2 + n3 * n3 := by
    rcases hdir with h | h
    · exact h
    · by_contra hneg
      have hz : n1 * n1 + n2 * n2 + n3 * n3 = 0 := le_antisymm (not_lt.mp hneg) hnn0
      rw [hz, zero_mul] at hcs
      have := mul_pos h h
      linarith
  by_contra hlt
  have hlt' := mul_lt_mul_of_pos_left (not_le.mp hlt) hpos
  have e : c * c * (n1 * n1 + n2 * n2 + n3 * n3) = (n1 * n1 + n2 * n2 + n3 * n3) * c ^ 2 := by ring
  linarith

/-- A witness that passes shows its two pieces at least `c` apart. -/
theorem checkWitness_sound {A B : Array (Array Face)} {c : Rat} {w : Witness} {s : Shown}
    (hc : 0 ≤ c) (h : checkWitness A B c w = .ok s) :
    ∃ P Q, piece? A w.a = some P ∧ piece? B w.b = some Q ∧
      ∀ x y : P3, (∀ f ∈ P, f.holds x) → (∀ f ∈ Q, f.holds y) → (c : ℝ) ≤ dist3 x y := by
  unfold checkWitness at h
  generalize hP : piece? A w.a = oP at h
  generalize hQ : piece? B w.b = oQ at h
  cases oP with
  | none => simp at h
  | some P =>
  cases oQ with
  | none => simp at h
  | some Q =>
  refine ⟨P, Q, rfl, rfl, ?_⟩
  simp only [bind_ok, need_ok, decide_eq_true_eq] at h
  obtain ⟨s1, hs1, t1, ht1, _, hface, _, hdir, _, hgap, _⟩ := h
  intro x y hx hy
  have hn := combine_sound x hx hs1
  have hm := combine_sound y hy ht1
  obtain ⟨h1, h2, h3⟩ := hface
  have e1 : (s1.1 : ℝ) + (t1.1 : ℝ) = 0 := by exact_mod_cast h1
  have e2 : (s1.2.1 : ℝ) + (t1.2.1 : ℝ) = 0 := by exact_mod_cast h2
  have e3 : (s1.2.2.1 : ℝ) + (t1.2.2.1 : ℝ) = 0 := by exact_mod_cast h3
  have f1 : (t1.1 : ℝ) = -(s1.1 : ℝ) := by linarith
  have f2 : (t1.2.1 : ℝ) = -(s1.2.1 : ℝ) := by linarith
  have f3 : (t1.2.2.1 : ℝ) = -(s1.2.2.1 : ℝ) := by linarith
  rw [f1, f2, f3] at hm
  have hdir' : 0 < (s1.1 : ℝ) * s1.1 + (s1.2.1 : ℝ) * s1.2.1 + (s1.2.2.1 : ℝ) * s1.2.2.1 ∨
      0 < -(t1.2.2.2 : ℝ) - (s1.2.2.2 : ℝ) := by
    rcases hdir with h | h
    · left; exact_mod_cast h
    · right; exact_mod_cast h
  have hgap0 : 0 ≤ -(t1.2.2.2 : ℝ) - (s1.2.2.2 : ℝ) := by exact_mod_cast hgap.1
  have hgap2 : (c : ℝ) * c * ((s1.1 : ℝ) * s1.1 + (s1.2.1 : ℝ) * s1.2.1 + (s1.2.2.1 : ℝ) * s1.2.2.1) ≤
      (-(t1.2.2.2 : ℝ) - (s1.2.2.2 : ℝ)) * (-(t1.2.2.2 : ℝ) - (s1.2.2.2 : ℝ)) := by
    exact_mod_cast hgap.2
  have hdot : -(t1.2.2.2 : ℝ) - (s1.2.2.2 : ℝ) ≤
      (s1.1 : ℝ) * (y.1 - x.1) + (s1.2.1 : ℝ) * (y.2.1 - x.2.1) + (s1.2.2.1 : ℝ) * (y.2.2 - x.2.2) := by
    linarith
  have hD := apart_core hdir' hgap0 hgap2 hdot
  unfold dist3
  apply sqrt_bound (by exact_mod_cast hc)
  have e : (x.1 - y.1) ^ 2 + (x.2.1 - y.2.1) ^ 2 + (x.2.2 - y.2.2) ^ 2 =
      (y.1 - x.1) ^ 2 + (y.2.1 - x.2.1) ^ 2 + (y.2.2 - x.2.2) ^ 2 := by ring
  rw [e]; exact hD

end Certify.Clearance
