/-
`check_sound`: a clearance certificate that the checker accepts is true of the solids it names.
-/
import CertifyProofs.ClearancePieces

namespace Certify.Clearance

theorem pair_unique {n a b a' b' : Nat} (hb : b < n) (hb' : b' < n)
    (h : a * n + b = a' * n + b') : a = a' ∧ b = b' := by
  have ha : a = a' := by
    rcases Nat.lt_trichotomy a a' with hlt | heq | hgt
    · have : (a + 1) * n ≤ a' * n := Nat.mul_le_mul_right n hlt
      rw [Nat.add_mul] at this
      omega
    · exact heq
    · have : (a' + 1) * n ≤ a * n := Nat.mul_le_mul_right n hgt
      rw [Nat.add_mul] at this
      omega
  subst ha
  exact ⟨rfl, by omega⟩

theorem piece?_some {A : Array (Array Face)} {i : Int} {P : Array Face} (h : piece? A i = some P) :
    ∃ hi : i.toNat < A.size, A[i.toNat] = P := by
  unfold piece? at h
  split at h
  · exact Array.getElem?_eq_some_iff.mp h
  · cases h

/-- A pair of pieces that ends up marked was marked at the start, or has a witness that passed. -/
theorem markAll_sound {A B : Array (Array Face)} {c : Rat} :
    ∀ {ws : List Witness} {seen : Array Bool} {least : Option (Rat × Rat)}
      {r : Array Bool × Option (Rat × Rat)},
      markAll A B c ws seen least = .ok r → ∀ k, r.1.getD k false = true →
        seen.getD k false = true ∨
        ∃ w ∈ ws, (∃ s, checkWitness A B c w = .ok s) ∧ w.a.toNat * B.size + w.b.toNat = k
  | [], seen, least, r, h, k, hk => by
    simp only [markAll] at h
    cases h
    exact Or.inl hk
  | w :: ws, seen, least, r, h, k, hk => by
    simp only [markAll, bind_ok] at h
    obtain ⟨s, hs, h⟩ := h
    rcases markAll_sound h k hk with h1 | ⟨w', hw', hok, hidx⟩
    · by_cases hkk : w.a.toNat * B.size + w.b.toNat = k
      · exact Or.inr ⟨w, by simp, ⟨s, hs⟩, hkk⟩
      · left
        simpa [Array.getD_eq_getD_getElem?, Array.getElem?_setIfInBounds, hkk] using h1
    · exact Or.inr ⟨w', by simp [hw'], hok, hidx⟩

/-- Where the check returns a verdict, every point of part A is at least `clearance` from
every point of part B. -/
theorem check_sound {cert : Cert} {out : Out} (h : check cert = .ok out) :
    ∀ x ∈ partPoints cert.partA, ∀ y ∈ partPoints cert.partB,
      (cert.clearance : ℝ) ≤ dist3 x y := by
  simp only [check, bind_ok, need_ok, decide_eq_true_eq] at h
  obtain ⟨_, hc, la, hla, lb, hlb, r, hr, h⟩ := h
  intro x hx y hy
  obtain ⟨P, hP, hPx⟩ := pieces_covers hla x hx
  obtain ⟨Q, hQ, hQy⟩ := pieces_covers hlb y hy
  obtain ⟨i, hi, rfl⟩ := List.getElem_of_mem hP
  obtain ⟨j, hj, rfl⟩ := List.getElem_of_mem hQ
  have hAs : (la.map List.toArray).toArray.size = la.length := by simp
  have hBs : (lb.map List.toArray).toArray.size = lb.length := by simp
  -- every pair is marked
  have hall : ∀ k < (la.map List.toArray).toArray.size * (lb.map List.toArray).toArray.size,
      r.1.getD k false = true := by
    intro k hk
    split at h
    · rename_i hnil
      have := List.filter_eq_nil_iff.mp hnil k (List.mem_range.mpr hk)
      simpa using this
    · cases h
  have hk : i * (lb.map List.toArray).toArray.size + j
      < (la.map List.toArray).toArray.size * (lb.map List.toArray).toArray.size := by
    rw [hAs, hBs]
    have : (i + 1) * lb.length ≤ la.length * lb.length := Nat.mul_le_mul_right _ hi
    rw [Nat.add_mul] at this
    omega
  rcases markAll_sound hr _ (hall _ hk) with h0 | ⟨w, _, ⟨s, hs⟩, hidx⟩
  · exfalso
    simp only [Array.getD_eq_getD_getElem?, Array.getElem?_replicate] at h0
    split at h0 <;> simp at h0
  · obtain ⟨P', Q', hP', hQ', hdist⟩ := checkWitness_sound hc hs
    obtain ⟨hia, hPa⟩ := piece?_some hP'
    obtain ⟨hib, hQb⟩ := piece?_some hQ'
    obtain ⟨ea, eb⟩ := pair_unique hib (by rw [hBs]; exact hj) hidx
    apply hdist x y
    · intro f hf
      have : f ∈ la[i] := by
        have e : P' = la[i].toArray := by rw [← hPa]; simp [ea]
        rw [e] at hf
        simpa using hf
      exact hPx f this
    · intro f hf
      have : f ∈ lb[j] := by
        have e : Q' = lb[j].toArray := by rw [← hQb]; simp [eb]
        rw [e] at hf
        simpa using hf
      exact hQy f this

end Certify.Clearance
