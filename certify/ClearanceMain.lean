import Certify.Clearance

open Certify Certify.Clearance

/-- The whole part of a square root, by halving. -/
def isqrt (n : Nat) : Nat := Id.run do
  let mut lo := 0
  let mut hi := n + 1
  for _ in [0 : n.log2 + 2] do
    if hi - lo ≤ 1 then break
    let mid := (lo + hi) / 2
    if mid * mid ≤ n then lo := mid else hi := mid
  return lo

/-- The square root of a fraction, cut to six decimal places. It is only printed. -/
def root6 (q : Rat) : String :=
  let n := isqrt (q.num.toNat * 1000000000000 / q.den)
  let frac := toString (n % 1000000)
  s!"{n / 1000000}.{String.ofList (List.replicate (6 - frac.length) '0')}{frac}"

def main (args : List String) : IO UInt32 := do
  match args with
  | [path] =>
    let began ← IO.monoMsNow
    let verdict ← (do
      let text ← IO.FS.readFile path
      match Lean.Json.parse text with
      | .error e => pure (notInFormat s!"JSON: {e}")
      | .ok j => pure (parse j >>= check) : IO (Check Out)).catchExceptions
        fun e => pure (notInFormat s!"{e}")
    match verdict with
    | .error why =>
      IO.println s!"REFUSED: {why}"
      return 1
    | .ok out =>
      let shown := match out.least with
        | none => "none, every piece pair has an empty piece"
        | some l => root6 (l.1 / l.2)
      IO.println s!"PROVED: the parts are at least {fraction out.clearance} = {decimal6 out.clearance} apart"
      IO.println s!"  {out.piecesA} pieces of A against {out.piecesB} of B, {out.piecesA * out.piecesB} pairs, the least distance shown {shown}"
      IO.println s!"  checked in {(← IO.monoMsNow) - began} ms"
      return 0
  | _ =>
    IO.eprintln "usage: check-clearance CERT.json"
    return 2
