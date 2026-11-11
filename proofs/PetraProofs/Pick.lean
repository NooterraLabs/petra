/-
The pick node. When `pick` returns an enclosure, the pick has a value at the point, and the
enclosure holds it. The argument is the one in the comment on `pick` in
kernel/Petra/Tape.lean: the true order of every compared pair is one the enclosures allow,
so one of the ways the kernel tries is the true one, and in that way the first case that
holds is the case that is first at the point.
-/
import PetraProofs.Meaning

namespace Petra

/-! ## The order of two reals -/

/-- The order of `x` against `y`. -/
noncomputable def ordR (x y : ℝ) : Ordering :=
  if x < y then .lt else if x = y then .eq else .gt

theorem ordR_self (x : ℝ) : ordR x x = .eq := by
  unfold ordR
  rw [if_neg (lt_irrefl x), if_pos rfl]

theorem ordR_swap (x y : ℝ) : (ordR x y).swap = ordR y x := by
  unfold ordR
  rcases lt_trichotomy x y with h | h | h
  · rw [if_pos h, if_neg h.not_gt, if_neg h.ne']; rfl
  · subst h; rw [if_neg (lt_irrefl x), if_pos rfl]; rfl
  · rw [if_neg h.not_gt, if_neg h.ne', if_pos h]; rfl

theorem decide_le_eq (x y : ℝ) : decide (x ≤ y) = (ordR x y != .gt) := by
  unfold ordR
  rcases lt_trichotomy x y with h | h | h
  · rw [if_pos h, decide_eq_true h.le]; rfl
  · subst h; rw [if_neg (lt_irrefl x), if_pos rfl, decide_eq_true le_rfl]; rfl
  · rw [if_neg h.not_gt, if_neg h.ne', decide_eq_false (not_le.mpr h)]; rfl

theorem decide_lt_eq (x y : ℝ) : decide (x < y) = (ordR x y == .lt) := by
  unfold ordR
  rcases lt_trichotomy x y with h | h | h
  · rw [if_pos h, decide_eq_true h]; rfl
  · subst h; rw [if_neg (lt_irrefl x), if_pos rfl, decide_eq_false (lt_irrefl x)]; rfl
  · rw [if_neg h.not_gt, if_neg h.ne', decide_eq_false h.not_gt]; rfl

/-! ## Small facts about lists and arrays -/

theorem find?_congr' {α : Type} {p q : α → Bool} (l : List α) (h : ∀ a ∈ l, p a = q a) :
    l.find? p = l.find? q := by
  induction l with
  | nil => rfl
  | cons a l ih =>
    have ha : p a = q a := h a (by simp)
    have ih' := ih (fun b hb => h b (by simp [hb]))
    simp only [List.find?_cons, ha, ih']

theorem idxOf?_spec {α : Type} [BEq α] [LawfulBEq α] {xs : Array α} {a : α} (h : a ∈ xs) :
    ∃ k, ∃ hk : k < xs.size, xs.idxOf? a = some k ∧ xs[k] = a := by
  rw [Array.idxOf?_eq_map_finIdxOf?_val]
  cases hf : xs.finIdxOf? a with
  | none => exact absurd h (Array.finIdxOf?_eq_none_iff.mp hf)
  | some i => exact ⟨i.val, i.isLt, rfl, (Array.finIdxOf?_eq_some_iff.mp hf).1⟩

/-- A fold that appends holds what each member appends. -/
theorem mem_foldl_append {α β : Type} (g : α → Array β) {F : Array β → α → Array β}
    (hF : ∀ out a, F out a = out ++ g a) (p : β) :
    ∀ (l : List α) (init : Array β), (p ∈ init ∨ ∃ a ∈ l, p ∈ g a) → p ∈ l.foldl F init := by
  intro l
  induction l with
  | nil =>
    intro init h
    rcases h with h | ⟨a, ha, _⟩
    · exact h
    · simp at ha
  | cons a l ih =>
    intro init h
    rw [List.foldl_cons]
    apply ih
    rw [hF]
    rcases h with h | ⟨b, hb, hp⟩
    · exact Or.inl (Array.mem_append.mpr (Or.inl h))
    · rcases List.mem_cons.mp hb with rfl | hb
      · exact Or.inl (Array.mem_append.mpr (Or.inr hp))
      · exact Or.inr ⟨b, hb, hp⟩

/-- A fold that keeps the first copy of each member keeps every member. -/
theorem mem_dedupe {α : Type} [BEq α] [LawfulBEq α] {F : Array α → α → Array α}
    (hF : ∀ out q, F out q = if out.contains q then out else out.push q) (p : α) :
    ∀ (l : List α) (out : Array α), (p ∈ out ∨ p ∈ l) → p ∈ l.foldl F out := by
  intro l
  induction l with
  | nil =>
    intro out h
    rcases h with h | h
    · exact h
    · simp at h
  | cons q l ih =>
    intro out h
    rw [List.foldl_cons]
    apply ih
    rw [hF]
    rcases h with h | h
    · left
      split_ifs
      · exact h
      · exact Array.mem_push.mpr (Or.inl h)
    · rcases List.mem_cons.mp h with rfl | h
      · left
        split_ifs with hc
        · exact Array.mem_of_contains_eq_true hc
        · exact Array.mem_push.mpr (Or.inr rfl)
      · exact Or.inr h

/-! ## `earliest` -/

/-- With no earliest failure, no listed node has failed. -/
theorem earliest_none {bad : Array (Option Failure)} {ids : Array Nat}
    (h : earliest bad ids = none) : ∀ i ∈ ids, bad[i]! = none := by
  have key : ∀ G : Option Failure → Nat → Option Failure,
      (∀ found i, G found i = none → found = none ∧ bad[i]! = none) →
      ids.foldl G none = none → ∀ i ∈ ids, bad[i]! = none := by
    intro G hG hfold
    rw [← Array.foldl_toList] at hfold
    have aux : ∀ (l : List Nat) (found : Option Failure), l.foldl G found = none →
        found = none ∧ ∀ i ∈ l, bad[i]! = none := by
      intro l
      induction l with
      | nil => intro found h; exact ⟨h, by simp⟩
      | cons a l ih =>
        intro found h
        rw [List.foldl_cons] at h
        obtain ⟨h1, h2⟩ := ih _ h
        obtain ⟨h3, h4⟩ := hG _ _ h1
        refine ⟨h3, ?_⟩
        intro i hi
        rcases List.mem_cons.mp hi with rfl | hi
        · exact h4
        · exact h2 i hi
    intro i hi
    exact (aux _ _ hfold).2 i (Array.mem_toList_iff.mpr hi)
  refine key _ ?_ h
  intro found i hG
  split at hG
  · split at hG <;> cases hG
  · exact ⟨rfl, hG⟩
  · rename_i hb
    exact ⟨hG, hb⟩

/-! ## The pairs a condition compares -/

theorem mem_pairs_and {cs : Array Cond} {c : Cond} {p : Nat × Nat} (hc : c ∈ cs)
    (hp : p ∈ c.pairs) : p ∈ (Cond.and cs).pairs := by
  rw [Cond.pairs, ← Array.foldl_toList]
  exact mem_foldl_append Cond.pairs (fun _ _ => rfl) p cs.toList #[]
    (Or.inr ⟨c, Array.mem_toList_iff.mpr hc, hp⟩)

theorem mem_pairs_or {cs : Array Cond} {c : Cond} {p : Nat × Nat} (hc : c ∈ cs)
    (hp : p ∈ c.pairs) : p ∈ (Cond.or cs).pairs := by
  rw [Cond.pairs, ← Array.foldl_toList]
  exact mem_foldl_append Cond.pairs (fun _ _ => rfl) p cs.toList #[]
    (Or.inr ⟨c, Array.mem_toList_iff.mpr hc, hp⟩)

/-- Every pair of a condition of a case is among the pairs the pick compares. -/
theorem mem_compared {cases : Array (Option Cond × Nat)} {c : Cond} {value : Nat}
    {p : Nat × Nat} (hcase : (some c, value) ∈ cases) (hp : p ∈ c.pairs) :
    p ∈ compared cases := by
  unfold compared
  dsimp only
  rw [← Array.foldl_toList]
  refine mem_dedupe (fun _ _ => rfl) p _ #[] (Or.inr ?_)
  exact Array.mem_toList_iff.mpr (Array.mem_flatMap.mpr ⟨(some c, value), hcase, hp⟩)

theorem mem_reads_of_compared {cases : Array (Option Cond × Nat)} {p : Nat × Nat}
    (hp : p ∈ compared cases) :
    p.1 ∈ (Node.pick cases).reads ∧ p.2 ∈ (Node.pick cases).reads := by
  have h1 : ∀ i, i = p.1 ∨ i = p.2 → i ∈ (Node.pick cases).reads := by
    intro i hi
    rw [Node.reads]
    refine Array.mem_append.mpr (Or.inl (Array.mem_flatMap.mpr ⟨p, hp, ?_⟩))
    obtain ⟨a, b⟩ := p
    rcases hi with rfl | rfl <;> simp
  exact ⟨h1 _ (Or.inl rfl), h1 _ (Or.inr rfl)⟩

theorem mem_reads_of_case {cases : Array (Option Cond × Nat)} {c : Option Cond} {value : Nat}
    (h : (c, value) ∈ cases) : value ∈ (Node.pick cases).reads := by
  rw [Node.reads]
  exact Array.mem_append.mpr (Or.inr (Array.mem_map.mpr ⟨(c, value), h, rfl⟩))

/-! ## The ways of ordering -/

/-- Once the count of ways is over the limit, it stays where it is. -/
theorem ways_stuck {g : Nat → Array Ordering → Nat}
    (hg : ∀ n os, g n os = if n > MAX_CHOICES then n else n * os.size) :
    ∀ (opts : List (Array Ordering)) (acc : Nat), acc > MAX_CHOICES → opts.foldl g acc = acc := by
  intro opts
  induction opts with
  | nil => intro acc _; rfl
  | cons os opts ih =>
    intro acc h
    rw [List.foldl_cons, hg, if_pos h]
    exact ih acc h

/-- A count of ways within the limit is the product of the numbers of outcomes. -/
theorem ways_eq_prod {g : Nat → Array Ordering → Nat}
    (hg : ∀ n os, g n os = if n > MAX_CHOICES then n else n * os.size) :
    ∀ (opts : List (Array Ordering)) (acc : Nat), opts.foldl g acc ≤ MAX_CHOICES →
      opts.foldl g acc = acc * (opts.map Array.size).prod := by
  intro opts
  induction opts with
  | nil => intro acc _; simp
  | cons os opts ih =>
    intro acc h
    rw [List.foldl_cons] at h ⊢
    by_cases hacc : acc > MAX_CHOICES
    · rw [hg, if_pos hacc, ways_stuck hg opts acc hacc] at h
      omega
    · rw [hg, if_neg hacc] at h ⊢
      rw [ih _ h, List.map_cons, List.prod_cons, Nat.mul_assoc]

/-- Every choice of one outcome for each pair is the way of some number below the product. -/
theorem way_exists {f : Array Ordering × Nat → Array Ordering → Array Ordering × Nat}
    (hf : ∀ taken n os, f (taken, n) os = (taken.push os[n % os.size]!, n / os.size)) :
    ∀ (choice : List Ordering) (opts : List (Array Ordering)),
      List.Forall₂ (fun o os => o ∈ os) choice opts →
      ∃ n, n < (opts.map Array.size).prod ∧
        ∀ taken : Array Ordering, (opts.foldl f (taken, n)).1 = taken ++ choice.toArray := by
  intro choice opts h
  induction h with
  | nil => exact ⟨0, by simp, fun taken => by simp⟩
  | @cons o os choice opts hmem _ ih =>
    obtain ⟨n', hn', hw⟩ := ih
    obtain ⟨d, hd, hod⟩ := Array.getElem_of_mem hmem
    have hpos : 0 < os.size := by omega
    refine ⟨d + os.size * n', ?_, ?_⟩
    · rw [List.map_cons, List.prod_cons]
      calc d + os.size * n' < os.size + os.size * n' := by omega
        _ = os.size * (n' + 1) := by ring
        _ ≤ os.size * (opts.map Array.size).prod := Nat.mul_le_mul_left _ hn'
    · intro taken
      have e1 : (d + os.size * n') % os.size = d := by
        rw [Nat.add_mul_mod_self_left, Nat.mod_eq_of_lt hd]
      have e2 : (d + os.size * n') / os.size = n' := by
        rw [Nat.add_mul_div_left _ _ hpos, Nat.div_eq_of_lt hd, Nat.zero_add]
      rw [List.foldl_cons, hf, e1, e2, getElem!_pos os d hd, hod, hw]
      apply Array.ext'
      simp

theorem way_eq_choice (options : Array (Array Ordering)) (choice : List Ordering)
    (h : List.Forall₂ (fun o os => o ∈ os) choice options.toList) :
    ∃ n, n < (options.toList.map Array.size).prod ∧ way options n = choice.toArray := by
  have key : ∀ f : Array Ordering × Nat → Array Ordering → Array Ordering × Nat,
      (∀ taken n os, f (taken, n) os = (taken.push os[n % os.size]!, n / os.size)) →
      ∃ n, n < (options.toList.map Array.size).prod ∧
        (options.foldl f (#[], n)).1 = choice.toArray := by
    intro f hf
    obtain ⟨n, hn, hw⟩ := way_exists hf choice options.toList h
    refine ⟨n, hn, ?_⟩
    rw [← Array.foldl_toList, hw]
    simp
  exact key _ (fun _ _ _ => rfl)

/-- The true order of two nodes is one their enclosures allow. -/
theorem ordR_mem_outcomes {v : Array Iv} {p : Nat × Nat} {x y : ℝ} (hx : v[p.1]!.Holds x)
    (hy : v[p.2]!.Holds y) (heq : p.1 = p.2 → x = y) : ordR x y ∈ outcomes v p := by
  unfold outcomes
  dsimp only
  split
  · rename_i hpp
    have hxy := heq (by simpa using hpp)
    subst hxy
    rw [ordR_self]
    simp
  · rcases lt_trichotomy x y with hlt | hxy | hgt
    · have h1 : v[p.1]!.lo < v[p.2]!.hi := by
        exact_mod_cast lt_of_le_of_lt hx.1 (lt_of_lt_of_le hlt hy.2)
      have ho : ordR x y = .lt := by unfold ordR; rw [if_pos hlt]
      rw [ho, if_pos h1]
      simp
    · subst hxy
      have h1 : v[p.1]!.lo ≤ v[p.2]!.hi := by exact_mod_cast le_trans hx.1 hy.2
      have h2 : v[p.2]!.lo ≤ v[p.1]!.hi := by exact_mod_cast le_trans hy.1 hx.2
      rw [ordR_self]
      simp [h1, h2]
    · have h1 : v[p.1]!.hi > v[p.2]!.lo := by
        exact_mod_cast lt_of_le_of_lt hy.1 (lt_of_lt_of_le hgt hx.2)
      have ho : ordR x y = .gt := by unfold ordR; rw [if_neg hgt.not_gt, if_neg hgt.ne']
      rw [ho, if_pos h1]
      simp

/-- When `taken` holds the true order of each compared pair, `order` gives the true order of
node `i` against node `j`, whichever of the two is the earlier. -/
theorem order_true {pairs : Array (Nat × Nat)} {taken : Array Ordering} {xs : Nat → ℝ}
    (htaken : ∀ k (hk : k < pairs.size), taken[k]! = ordR (xs pairs[k].1) (xs pairs[k].2))
    {i j : Nat} (hmem : pair i j ∈ pairs) : order pairs taken i j = ordR (xs i) (xs j) := by
  obtain ⟨k, hk, hidx, hpk⟩ := idxOf?_spec hmem
  unfold order
  rw [hidx]
  dsimp only
  rw [htaken k hk, hpk]
  unfold pair
  split_ifs with hij
  · rfl
  · exact ordR_swap _ _

/-! ## Conditions -/

theorem foldl_agree {F : Option Bool → Cond → Option Bool} {G : Bool → Cond → Bool}
    {op : Bool → Bool → Bool} {truth : Cond → Option Bool} {holds : Cond → Bool}
    (hF : ∀ a c b, truth c = some b → F (some a) c = some (op a b))
    (hG : ∀ a c, G a c = op a (holds c)) :
    ∀ (l : List Cond) (a : Bool), (∀ c ∈ l, truth c = some (holds c)) →
      l.foldl F (some a) = some (l.foldl G a) := by
  intro l
  induction l with
  | nil => intro a _; rfl
  | cons c l ih =>
    intro a h
    rw [List.foldl_cons, List.foldl_cons, hF a c _ (h c (by simp)), hG]
    exact ih _ (fun c' hc' => h c' (by simp [hc']))

/-- When `rel` is the true order of every pair a condition compares, the kernel's reading
of the condition is its truth at the point. -/
theorem holds_eq_truth (rel : Nat → Nat → Ordering) (val : Nat → Option ℝ) (xs : Nat → ℝ) :
    ∀ c : Cond, (∀ i j, pair i j ∈ c.pairs →
        val i = some (xs i) ∧ val j = some (xs j) ∧ rel i j = ordR (xs i) (xs j)) →
      c.truth val = some (c.holds rel)
  | .le i j, h => by
    obtain ⟨hi, hj, hr⟩ := h i j (by rw [Cond.pairs]; simp)
    rw [Cond.truth, Cond.holds, hi, hj, hr, ← decide_le_eq]
  | .lt i j, h => by
    obtain ⟨hi, hj, hr⟩ := h i j (by rw [Cond.pairs]; simp)
    rw [Cond.truth, Cond.holds, hi, hj, hr, ← decide_lt_eq]
  | .and cs, h => by
    have ih : ∀ c ∈ cs.toList, c.truth val = some (c.holds rel) := fun c hc =>
      holds_eq_truth rel val xs c
        (fun i j hp => h i j (mem_pairs_and (Array.mem_toList_iff.mp hc) hp))
    rw [Cond.truth, Cond.holds, ← Array.foldl_toList, ← Array.foldl_toList]
    exact foldl_agree (op := fun a b => a && b) (fun a c b hb => by simp only [hb])
      (fun a c => rfl) cs.toList true ih
  | .or cs, h => by
    have ih : ∀ c ∈ cs.toList, c.truth val = some (c.holds rel) := fun c hc =>
      holds_eq_truth rel val xs c
        (fun i j hp => h i j (mem_pairs_or (Array.mem_toList_iff.mp hc) hp))
    rw [Cond.truth, Cond.holds, ← Array.foldl_toList, ← Array.foldl_toList]
    exact foldl_agree (op := fun a b => a || b) (fun a c b hb => by simp only [hb])
      (fun a c => rfl) cs.toList false ih
  | .not c, h => by
    have ih := holds_eq_truth rel val xs c (fun i j hp => h i j (by rw [Cond.pairs]; exact hp))
    rw [Cond.truth, Cond.holds, ih]
    rfl
termination_by c => sizeOf c
decreasing_by
  all_goals simp_wf
  · have := Array.sizeOf_lt_of_mem (Array.mem_toList_iff.mp hc)
    omega
  · have := Array.sizeOf_lt_of_mem (Array.mem_toList_iff.mp hc)
    omega

/-! ## The hull -/

/-- The hull of the found enclosures holds its first enclosure and every later one. -/
theorem hull_fold (v : Array Iv) {H : Iv → Nat → Iv}
    (hH : ∀ hull k, H hull k = ⟨rmin hull.lo v[k]!.lo, rmax hull.hi v[k]!.hi⟩) :
    ∀ (rest : List Nat) (init : Iv),
      ((rest.foldl H init).lo ≤ init.lo ∧ init.hi ≤ (rest.foldl H init).hi) ∧
      ∀ k ∈ rest, (rest.foldl H init).lo ≤ v[k]!.lo ∧ v[k]!.hi ≤ (rest.foldl H init).hi := by
  intro rest
  induction rest with
  | nil => intro init; exact ⟨⟨le_refl _, le_refl _⟩, by simp⟩
  | cons k rest ih =>
    intro init
    rw [List.foldl_cons]
    obtain ⟨⟨h1, h2⟩, h3⟩ := ih (H init k)
    have e1 : (H init k).lo = min init.lo v[k]!.lo := by rw [hH, rmin_eq]
    have e2 : (H init k).hi = max init.hi v[k]!.hi := by rw [hH, rmax_eq]
    rw [e1] at h1
    rw [e2] at h2
    refine ⟨⟨h1.trans (min_le_left _ _), (le_max_left _ _).trans h2⟩, ?_⟩
    intro k' hk'
    rcases List.mem_cons.mp hk' with rfl | hk'
    · exact ⟨h1.trans (min_le_right _ _), (le_max_right _ _).trans h2⟩
    · exact h3 k' hk'

theorem Iv.Holds.wider {a r : Iv} {x : ℝ} (h : a.Holds x) (hlo : r.lo ≤ a.lo) (hhi : a.hi ≤ r.hi) :
    r.Holds x :=
  ⟨le_trans (by exact_mod_cast hlo) h.1, le_trans h.2 (by exact_mod_cast hhi)⟩

/-! ## What a pick that returns has checked -/

theorem Except.throw_bind_ne_ok {ε α β : Type} {e : ε} {f : α → Except ε β} {b : β}
    (h : (throw e >>= f) = .ok b) : False := by
  have h' : (Except.error e : Except ε β) = .ok b := h
  cases h'

/-- A pick that returns `r` found no failure among the nodes it compares, tried every way,
found in each way a first case that holds, found no failure among those cases, and returns
a range that holds the enclosure of each of them. -/
theorem pick_ok {v : Array Iv} {bad : Array (Option Failure)} {self : Nat}
    {cases : Array (Option Cond × Nat)} {r : Iv} (h : pick v bad self cases = .ok r) :
    (∀ p ∈ compared cases, bad[p.1]! = none ∧ bad[p.2]! = none) ∧
    ∃ found : Array Nat,
      (∀ n, n < (((compared cases).map (outcomes v)).toList.map Array.size).prod →
        ∃ c value, cases.find? (fun case => case.1.all (fun c =>
            c.holds (order (compared cases) (way ((compared cases).map (outcomes v)) n))))
          = some (c, value) ∧ value ∈ found) ∧
      (∀ k ∈ found, bad[k]! = none) ∧
      (∀ k ∈ found, r.lo ≤ v[k]!.lo ∧ v[k]!.hi ≤ r.hi) := by
  unfold pick at h
  dsimp only at h
  split at h
  · exact (Except.throw_bind_ne_ok h).elim
  rename_i hE1
  rw [pure_bind] at h
  split at h
  · exact (Except.throw_bind_ne_ok h).elim
  rename_i hways
  rw [pure_bind] at h
  obtain ⟨found, hloop, h⟩ := Except.bind_ok h
  split at h
  · exact (Except.throw_bind_ne_ok h).elim
  rename_i hE2
  rw [pure_bind] at h
  have hE1' : earliest bad (Array.flatMap (fun x => #[x.1, x.2]) (compared cases)) = none :=
    Option.eq_none_iff_forall_ne_some.mpr (fun f hf => hE1 f hf)
  have hE2' : earliest bad found = none :=
    Option.eq_none_iff_forall_ne_some.mpr (fun f hf => hE2 f hf)
  refine ⟨?_, found, ?_, earliest_none hE2', ?_⟩
  · -- no compared node has failed
    intro p hp
    have hnone := earliest_none hE1'
    exact ⟨hnone p.1 (Array.mem_flatMap.mpr ⟨p, hp, by simp⟩),
      hnone p.2 (Array.mem_flatMap.mpr ⟨p, hp, by simp⟩)⟩
  · -- every way has its first case in `found`
    have hprod := ways_eq_prod (g := fun n os => if n > MAX_CHOICES then n else n * os.size)
      (fun _ _ => rfl) (Array.map (outcomes v) (compared cases)).toList 1
      (by rw [Array.foldl_toList]; exact Nat.le_of_not_gt hways)
    rw [Array.foldl_toList, Nat.one_mul] at hprod
    have hinv : ∀ n, n < Array.foldl (fun n os => if n > MAX_CHOICES then n else n * os.size) 1
          (Array.map (outcomes v) (compared cases)) →
        ∃ c value, cases.find? (fun case => case.1.all (fun c =>
            c.holds (order (compared cases) (way ((compared cases).map (outcomes v)) n))))
          = some (c, value) ∧ value ∈ found := by
      refine Except.forIn_range_inv _ (fun k (found : Array Nat) => ∀ n, n < k →
        ∃ c value, cases.find? (fun case => case.1.all (fun c =>
            c.holds (order (compared cases) (way ((compared cases).map (outcomes v)) n))))
          = some (c, value) ∧ value ∈ found) _ #[] found ?_ ?_ hloop
      · intro n hn
        omega
      · intro j _ b s hP hf
        split at hf
        · rename_i c value heq
          split at hf
          · rename_i hcont
            have hf' : (Except.ok (ForInStep.yield b) :
                Except Failure (ForInStep (Array Nat))) = .ok s := hf
            cases hf'
            refine ⟨b, rfl, ?_⟩
            intro n hn
            rcases Nat.lt_succ_iff_lt_or_eq.mp hn with hn | rfl
            · exact hP n hn
            · exact ⟨c, value, heq, Array.mem_of_contains_eq_true hcont⟩
          · have hf' : (Except.ok (ForInStep.yield (b.push value)) :
                Except Failure (ForInStep (Array Nat))) = .ok s := hf
            cases hf'
            refine ⟨b.push value, rfl, ?_⟩
            intro n hn
            rcases Nat.lt_succ_iff_lt_or_eq.mp hn with hn | rfl
            · obtain ⟨c', value', h1, h2⟩ := hP n hn
              exact ⟨c', value', h1, Array.mem_push.mpr (Or.inl h2)⟩
            · exact ⟨c, value, heq, Array.mem_push.mpr (Or.inr rfl)⟩
        · exact (Except.throw_bind_ne_ok hf).elim
    intro n hn
    exact hinv n (lt_of_lt_of_eq hn hprod.symm)
  · -- the range returned holds the enclosure of every found case
    split at h
    · have h' : (Except.error _ : Except Failure Iv) = .ok r := h
      cases h'
    · rename_i first rest hfound
      have h' : (Except.ok _ : Except Failure Iv) = .ok r := h
      injection h' with hr
      subst hr
      obtain ⟨⟨h1, h2⟩, h3⟩ := hull_fold v (fun _ _ => rfl) rest v[first]!
      intro k hk
      have hk' : k ∈ first :: rest := by
        rw [← hfound]
        exact Array.mem_toList_iff.mpr hk
      rcases List.mem_cons.mp hk' with rfl | hk'
      · exact ⟨h1, h2⟩
      · exact h3 k hk'

/-! ## The pick node -/

/-- The pick node. `val i` is the value of node `i` at a point, and every node the pick
reads that has not failed has a value there, which its enclosure holds. If `pick` returns a
range, the pick has a value at the point, and the range holds it. -/
theorem pick_sound {v : Array Iv} {bad : Array (Option Failure)} {self : Nat}
    {cases : Array (Option Cond × Nat)} {val : Nat → Option ℝ} {r : Iv}
    (hval : ∀ i ∈ (Node.pick cases).reads, bad[i]! = none → ∃ x, val i = some x ∧ v[i]!.Holds x)
    (h : pick v bad self cases = .ok r) :
    ∃ x, pickValue val cases.toList = some x ∧ r.Holds x := by
  obtain ⟨hcmp, found, hways, hbad, hhull⟩ := pick_ok h
  -- the value of each node at the point, where it has one
  let xs : Nat → ℝ := fun i => (val i).getD 0
  have hnode : ∀ i ∈ (Node.pick cases).reads, bad[i]! = none →
      val i = some (xs i) ∧ v[i]!.Holds (xs i) := by
    intro i hi hb
    obtain ⟨x, hx, hh⟩ := hval i hi hb
    have hxs : xs i = x := by
      show (val i).getD 0 = x
      rw [hx]
      rfl
    rw [hxs]
    exact ⟨hx, hh⟩
  have hpair : ∀ p ∈ compared cases,
      (val p.1 = some (xs p.1) ∧ v[p.1]!.Holds (xs p.1)) ∧
      (val p.2 = some (xs p.2) ∧ v[p.2]!.Holds (xs p.2)) := by
    intro p hp
    obtain ⟨m1, m2⟩ := mem_reads_of_compared hp
    obtain ⟨b1, b2⟩ := hcmp p hp
    exact ⟨hnode _ m1 b1, hnode _ m2 b2⟩
  -- the true order of every compared pair is a way the kernel tried
  have hforall : List.Forall₂ (fun o os => o ∈ os)
      ((compared cases).toList.map fun p => ordR (xs p.1) (xs p.2))
      ((compared cases).map (outcomes v)).toList := by
    rw [Array.toList_map]
    refine List.forall₂_map_left_iff.2 (List.forall₂_map_right_iff.2 (List.forall₂_same.2 ?_))
    intro p hp
    obtain ⟨⟨_, h1⟩, ⟨_, h2⟩⟩ := hpair p (Array.mem_toList_iff.mp hp)
    exact ordR_mem_outcomes h1 h2 (fun e => by rw [e])
  obtain ⟨n, hn, hway⟩ := way_eq_choice _ _ hforall
  obtain ⟨c, value, hfind, hmem⟩ := hways n hn
  rw [hway] at hfind
  -- in that way, `order` is the true order
  have hrel : ∀ i j, pair i j ∈ compared cases →
      val i = some (xs i) ∧ val j = some (xs j) ∧
      order (compared cases)
        ((compared cases).toList.map fun p => ordR (xs p.1) (xs p.2)).toArray i j
        = ordR (xs i) (xs j) := by
    intro i j hp
    obtain ⟨⟨v1, _⟩, ⟨v2, _⟩⟩ := hpair _ hp
    have hord := order_true (xs := xs)
      (taken := ((compared cases).toList.map fun p => ordR (xs p.1) (xs p.2)).toArray) (by
        intro k hk
        rw [getElem!_pos _ k (by simpa using hk)]
        simp) hp
    refine ⟨?_, ?_, hord⟩
    · unfold pair at v1 v2
      split_ifs at v1 v2 with hij
      · exact v1
      · exact v2
    · unfold pair at v1 v2
      split_ifs at v1 v2 with hij
      · exact v2
      · exact v1
  generalize hrel_def : order (compared cases)
    ((compared cases).toList.map fun p => ordR (xs p.1) (xs p.2)).toArray = rel at hfind hrel
  -- so the kernel reads every condition as it is at the point
  have hcase : ∀ case ∈ cases.toList,
      caseTruth val case.1 = some (case.1.all (fun c => c.holds rel)) := by
    rintro ⟨cond, value'⟩ hm
    cases cond with
    | none => rfl
    | some c' =>
      exact holds_eq_truth rel val xs c'
        (fun i j hp => hrel i j (mem_compared (Array.mem_toList_iff.mp hm) hp))
  have hall : cases.toList.all (fun case => (caseTruth val case.1).isSome) = true := by
    rw [List.all_eq_true]
    intro case hc
    rw [hcase case hc]
    rfl
  have hfind' : cases.toList.find? (fun case => caseTruth val case.1 == some true)
      = some (c, value) := by
    rw [← Array.find?_toList] at hfind
    rw [← hfind]
    apply find?_congr'
    intro case hc
    beta_reduce
    rw [hcase case hc]
    generalize Option.all (fun c => Cond.holds rel c) case.1 = b
    cases b <;> rfl
  have hpv : pickValue val cases.toList = val value := by
    unfold pickValue
    rw [if_pos hall, hfind']
  -- and the first case that holds at the point is one the kernel found
  have hcv : (c, value) ∈ cases := Array.mem_of_find?_eq_some hfind
  obtain ⟨hv, hh⟩ := hnode value (mem_reads_of_case hcv) (hbad value hmem)
  obtain ⟨hlo, hhi⟩ := hhull value hmem
  exact ⟨xs value, by rw [hpv, hv], hh.wider hlo hhi⟩

end Petra
