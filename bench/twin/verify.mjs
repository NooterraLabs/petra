#!/usr/bin/env node
// verify.mjs: an independent kernel for a design whose parts are of a deck's types.
// Written from format.md and deck.md alone. Exact rational interval arithmetic on BigInt.
//
//   node verify.mjs --card F --design F --deck F --rules F [--proofs F] [--explain]
//
// Prints one JSON object {verdict, findings, counts, ignored_hints, waived, cells} and exits
// 0 PASS, 1 FAIL, 2 UNKNOWN, 3 ILL-FORMED, 64 for a command line it cannot read, and for files
// with no deck of rules whose proofs.json carries a tape, which it does not check. A cell has its
// subject, mechanism, entry, claimed and state, a reason when it is open, waived, not applicable
// or a settled rule that requires, `stated: true` when it is a cell of a rule that requires or a
// cell settled on a tape with no input, and the completion it rests on when it is waived on one. --explain adds the
// steps to read the deck and to make the cells.
//
// Of the limits format.md states, the budget of work (20,000,000,000 units, for the needs, the
// proofs and the walks that ask whether a rule's `where` holds nowhere), the words of enclosures
// held on a leaf and the caches of ln, exp and cos are left out: they are counted in the
// reference kernel's own costs. So is the limit of 100 findings. The steps to make the
// cells (Steps), cos and the completions of item 9 among them, are counted. The kernel does not
// search: the climb of petra check, its budget of nodes and the work it charges its exponentials
// are not here. See AMBIGUITIES.md, I, K, L and M.
//
// With --rules the floors of `domains.input` are the kernel's own copy of core.json's, and a
// deck.json that gives others is a finding (format.md, type rule 8). A completion that a waived
// cell rests on prints each load's value with the unit it is in. See AMBIGUITIES.md, N.
//
// With --rules the size floor of `domains.size` is the kernel's own too (type rule 8). A name is
// counted, and the verdict printed, with an escape of six for each character a terminal acts on
// and does not show. An equation is held to the 1,024 orders of a pick when its row is read,
// whether or not a rule applies it. See AMBIGUITIES.md, O.
//
// A file, an item of one of its lists and a cell have every key format.md gives them, but the
// keys its table of Keys lets them leave out: a key left out, or of the wrong kind, breaks the
// shape rule. An object that holds a key twice is read with the last value. A shape finding is of
// one item, which is left out, or of the whole file, and a card, a design or a deck.json that
// does not read as a whole stops the kernel with the shape findings of all the files; otherwise
// the type rules are applied to what was read, type rule 1 (the design's `card` is the SHA-256 of
// the card's bytes) among them, and then Parts 1 to 8 when the deck of rules reads. A design with
// no parts that comes with a deck of rules is one with no part. With no deck of rules the verdict
// is never PASS, and this kernel gives one only for a list of cells that carries no tape: with a
// tape it exits 64 and prints no verdict. See AMBIGUITIES.md, P.
//
// The `when` of a rule and the `when` of a line's `unless` read only keys that their type marks
// `signed`, of the type itself or of a part it joins, and a deck that names any other key there
// does not read: a finding of the file `rules`. What a rule `requires` may name any key. So a
// `when` holds for a part or it does not: no line is left open for an unstated key of its
// `unless`, a rule answers only when its `when` holds, and no completion makes a rule not answer
// or an `unless` hold. See AMBIGUITIES.md, Q.
//
// A field that a part leaves unstated and that a need names, a need of the part's own type or of
// the type of the part that joins it, is one open cell with mechanism `unread`, in its place among
// the part's fields: the need was not asked (format.md, Parts 9 and Cells 8). An unstated field
// has no other `unread` cell, whatever a completion names. See AMBIGUITIES.md, R.
//
// A line of the grid is excused only with a reason and a ground: the `why` of an `unless` is a
// text with a letter in it, `a` to `z` or `A` to `Z`, and beside it stands exactly one of `when`,
// `least`, `loads` and `with`, each held to deck.md, The grid, when the deck is read. A cell that
// is not applicable has that `why` as its reason, cut once. A line answered `with` other lines is
// one cell for a part, settled after every other cell and every waiver, and no waiver rests it.
// A key is the card's unless its field says `chosen`, a text with a letter in it: a design that
// writes any other key is refused, and no `when` reads a chosen key. Every cell of a rule that
// requires is marked `stated: true`, and so is a cell proved or refuted on a tape whose root reads no input;
// neither is the proved cell a PASS needs. A text past 200 bytes as printed is cut as format.md,
// "A text that is cut", says, and the reasons are held to their three rooms. A `least` excuses
// its line only for a part that has a value for what it names, and the line is open and waivable
// for any other. See AMBIGUITIES.md, S, T and U.

import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

// ============================================================ rationals

const absB = (a) => (a < 0n ? -a : a);
function gcdB(a, b) {
  a = absB(a); b = absB(b);
  while (b) { const t = a % b; a = b; b = t; }
  return a;
}
export function bitlen(a) {
  a = absB(a);
  if (a === 0n) return 0;
  const s = a.toString(16);
  return (s.length - 1) * 4 + (32 - Math.clz32(parseInt(s[0], 16)));
}
export class Q {
  constructor(n, d) { this.n = n; this.d = d; }
  toString() { return this.d === 1n ? this.n.toString() : `${this.n}/${this.d}`; }
}
export function R(n, d = 1n) {
  if (d === 0n) throw new Error('zero denominator');
  if (d < 0n) { n = -n; d = -d; }
  const g = gcdB(n, d);
  if (g > 1n) { n /= g; d /= g; }
  return new Q(n, d);
}
const Q0 = new Q(0n, 1n);
const Q1 = new Q(1n, 1n);
const qadd = (a, b) => (a.d === b.d ? R(a.n + b.n, a.d) : R(a.n * b.d + b.n * a.d, a.d * b.d));
const qsub = (a, b) => R(a.n * b.d - b.n * a.d, a.d * b.d);
const qmul = (a, b) => R(a.n * b.n, a.d * b.d);
const qdiv = (a, b) => R(a.n * b.d, a.d * b.n);
const qneg = (a) => new Q(-a.n, a.d);
const qabs = (a) => (a.n < 0n ? qneg(a) : a);
export const qcmp = (a, b) => {
  const l = a.n * b.d, r = b.n * a.d;
  return l < r ? -1 : l > r ? 1 : 0;
};
const qmin = (a, b) => (qcmp(a, b) <= 0 ? a : b);
const qmax = (a, b) => (qcmp(a, b) >= 0 ? a : b);
const qpow = (a, k) => new Q(a.n ** BigInt(k), a.d ** BigInt(k)); // k >= 0; stays in lowest terms
function floorDiv(a, b) { const q = a / b; return (a % b !== 0n && (a < 0n) !== (b < 0n)) ? q - 1n : q; }
function ceilDiv(a, b) { const q = a / b; return (a % b !== 0n && (a < 0n) === (b < 0n)) ? q + 1n : q; }
function isqrt(n) {
  if (n < 2n) return n;
  let x = 1n << BigInt(Math.ceil(bitlen(n) / 2));
  for (;;) {
    const y = (x + n / x) >> 1n;
    if (y >= x) return x;
    x = y;
  }
}

// ============================================================ numbers

const MAXLEN = 4000;

// A number of card.json, design.json, deck.json or proofs.json: an integer or a fraction in
// lowest terms with a denominator above 1, no leading zero, never -0.
export function parseFileNumber(s) {
  if (typeof s !== 'string' || s.length > MAXLEN) return null;
  let m = /^(-?)(0|[1-9][0-9]*)$/.exec(s);
  if (m) {
    if (m[1] === '-' && m[2] === '0') return null;
    return R(BigInt(m[1] + m[2]));
  }
  m = /^(-?)([1-9][0-9]*)\/([1-9][0-9]*)$/.exec(s);
  if (m) {
    const n = BigInt(m[2]), d = BigInt(m[3]);
    if (d <= 1n || gcdB(n, d) !== 1n) return null;
    return R(m[1] === '-' ? -n : n, d);
  }
  return null;
}

// A number alone of a deck (in an expression or an exponent): digits with an optional sign, then
// a decimal part or a denominator. No comma, no whole number with a fraction, no space.
export function parseNumberAlone(s) {
  if (typeof s !== 'string' || s.length > MAXLEN) return null;
  const m = /^([+-]?)([0-9]+)(?:\.([0-9]+)|\/([0-9]+))?$/.exec(s);
  if (!m) return null;
  let v;
  if (m[3] !== undefined) v = R(BigInt(m[2] + m[3]), 10n ** BigInt(m[3].length));
  else if (m[4] !== undefined) {
    const d = BigInt(m[4]);
    if (d === 0n) return null;
    v = R(BigInt(m[2]), d);
  } else v = R(BigInt(m[2]));
  return m[1] === '-' ? qneg(v) : v;
}
const looksNumeric = (s) => /^[+-]?[0-9]/.test(s);

// ============================================================ dimensions and units

const dvec = (...xs) => xs.map((x) => R(BigInt(x)));
const BASE_DIMS = Object.assign(Object.create(null), {
  dimensionless: dvec(0, 0, 0, 0, 0),
  length: dvec(1, 0, 0, 0, 0),
  area: dvec(2, 0, 0, 0, 0),
  force: dvec(1, 1, -2, 0, 0),
  stress: dvec(-1, 1, -2, 0, 0),
  moment: dvec(2, 1, -2, 0, 0),
  mass: dvec(0, 1, 0, 0, 0),
  time: dvec(0, 0, 1, 0, 0),
  temperature: dvec(0, 0, 0, 0, 1),
  energy: dvec(2, 1, -2, 0, 0),
  current: dvec(0, 0, 0, 1, 0),
  voltage: dvec(2, 1, -3, -1, 0),
  power: dvec(2, 1, -3, 0, 0),
  resistance: dvec(2, 1, -3, -2, 0),
});
const DL = BASE_DIMS.dimensionless;
const dmul = (a, b) => a.map((x, i) => qadd(x, b[i]));
const ddiv = (a, b) => a.map((x, i) => qsub(x, b[i]));
const dpow = (a, q) => a.map((x) => qmul(x, q));
const deq = (a, b) => a.every((x, i) => qcmp(x, b[i]) === 0);
const dstr = (a) => `[${a.map(String).join(',')}]`;

// `length`, `length^3`, `force/length`, `force*length`: left to right, integer powers.
export function parseDim(s) {
  if (typeof s !== 'string' || s.length === 0 || s.length > MAXLEN) return null;
  const toks = s.split(/([*/])/);
  let acc = null;
  for (let i = 0; i < toks.length; i += 2) {
    const f = /^([a-z]+)(?:\^(-?[0-9]+))?$/.exec(toks[i]);
    if (!f || !BASE_DIMS[f[1]]) return null;
    let d = BASE_DIMS[f[1]];
    if (f[2] !== undefined) d = dpow(d, R(BigInt(f[2])));
    acc = i === 0 ? d : toks[i - 1] === '*' ? dmul(acc, d) : ddiv(acc, d);
  }
  return acc;
}

// A dim of card.json, design.json or deck.json (format.md, Numbers): one of sixteen names, or the
// exponents of metre, kilogram, second, ampere and degree Celsius, as in `m^3 s^-1`: each a base,
// `^` and a whole number, one space between two. The bases may stand in any order and more than
// once, their exponents then added; the number may be zero or negative, may have leading zeros and
// has no `+`. The empty text, two spaces together and a space at either end name no dimension.
const FILE_DIMS = Object.assign(Object.create(null), BASE_DIMS, {
  I2t: dvec(0, 0, 1, 2, 0),
  'resistance per length': ddiv(BASE_DIMS.resistance, BASE_DIMS.length),
});
const FILE_BASES = ['m', 'kg', 's', 'A', 'degC'];
export function parseFileDim(s) {
  if (typeof s !== 'string' || s.length > MAXLEN) return null;
  if (FILE_DIMS[s]) return FILE_DIMS[s];
  if (s.length === 0) return null;
  const e = [0n, 0n, 0n, 0n, 0n];
  for (const p of s.split(' ')) {
    const m = /^(m|kg|s|A|degC)\^(-?[0-9]+)$/.exec(p);
    if (!m) return null;
    e[FILE_BASES.indexOf(m[1])] += BigInt(m[2]);
  }
  return e.map((x) => R(x));
}
// Wherever the kernel compares two dimensions it does so by the exponents (format.md, Numbers).
const sameFileDim = (name, dim) => { const d = parseFileDim(name); return d !== null && deq(d, dim); };

const IN = R(127n, 5000n);
const LB = R(45359237n, 100000000n);
const LBF = qmul(LB, R(980665n, 100000n));
const KIP = qmul(LBF, R(1000n));
const FT = qmul(IN, R(12n));
const MILE = qmul(FT, R(5280n));
const PSI = qdiv(LBF, qmul(IN, IN));
const U = (f, dim) => ({ f, dim: typeof dim === 'string' ? parseDim(dim) : dim });
const r10 = (e) => (e >= 0 ? R(10n ** BigInt(e)) : R(1n, 10n ** BigInt(-e)));
// reference.md, Units (pages/units.md), with the factors of its table; and `N m`, which a deck
// reads and a design cannot write (deck.md, Dimensions).
export const UNITS = Object.assign(Object.create(null), {
  '%': U(R(1n, 100n), 'dimensionless'),
  m: U(Q1, 'length'), mm: U(r10(-3), 'length'), um: U(r10(-6), 'length'), cm: U(r10(-2), 'length'),
  km: U(r10(3), 'length'), inch: U(IN, 'length'), ft: U(FT, 'length'), mile: U(MILE, 'length'),
  mm2: U(r10(-6), 'area'), m2: U(Q1, 'area'), inch2: U(qmul(IN, IN), 'area'),
  N: U(Q1, 'force'), kN: U(r10(3), 'force'), MN: U(r10(6), 'force'), lbf: U(LBF, 'force'),
  kip: U(KIP, 'force'), kips: U(KIP, 'force'),
  Pa: U(Q1, 'stress'), kPa: U(r10(3), 'stress'), MPa: U(r10(6), 'stress'), GPa: U(r10(9), 'stress'),
  psi: U(PSI, 'stress'), ksi: U(qmul(PSI, R(1000n)), 'stress'),
  uA: U(r10(-6), 'current'), mA: U(r10(-3), 'current'), A: U(Q1, 'current'), kA: U(r10(3), 'current'),
  V: U(Q1, 'voltage'), kV: U(r10(3), 'voltage'),
  ohm: U(Q1, 'resistance'), mohm: U(r10(-3), 'resistance'), kohm: U(r10(3), 'resistance'),
  Mohm: U(r10(6), 'resistance'),
  'ohm/km': U(r10(-3), 'resistance/length'),
  mW: U(r10(-3), 'power'), W: U(Q1, 'power'), kW: U(r10(3), 'power'),
  J: U(Q1, 'energy'), Nm: U(Q1, 'energy'), 'N m': U(Q1, 'energy'),
  kip_in: U(qmul(KIP, IN), 'energy'), kip_ft: U(qmul(KIP, FT), 'energy'),
  lbf_in: U(qmul(LBF, IN), 'energy'), lbf_ft: U(qmul(LBF, FT), 'energy'),
  s: U(Q1, 'time'), ms: U(r10(-3), 'time'), min: U(R(60n), 'time'), h: U(R(3600n), 'time'),
  degC: U(Q1, 'temperature'),
  g: U(r10(-3), 'mass'), kg: U(Q1, 'mass'), lb: U(LB, 'mass'), oz: U(qdiv(LB, R(16n)), 'mass'),
  A2s: U(Q1, 'current^2*time'),
  Hz: U(Q1, 'dimensionless/time'), rpm: U(R(1n, 60n), 'dimensionless/time'),
  mAh: U(R(18n, 5n), 'current*time'), Ah: U(R(3600n), 'current*time'),
  'm/s': U(Q1, 'length/time'), 'km/h': U(R(5n, 18n), 'length/time'),
  knot: U(R(463n, 900n), 'length/time'), mph: U(R(1397n, 3125n), 'length/time'),
  'kg/m3': U(Q1, 'mass/length^3'), 'g/cm3': U(R(1000n), 'mass/length^3'),
  'N/mm': U(R(1000n), 'force/length'),
});
// deck.md, Dimensions: a unit of length raised to the power 2, 3 or 4, written as that one digit
// right after `^`. No other unit takes a power, and no other power is read.
const LENGTH_UNITS = ['m', 'mm', 'um', 'cm', 'km', 'inch', 'ft', 'mile'];
export function unitOf(s) {
  if (typeof s !== 'string') return null;
  if (UNITS[s]) return UNITS[s];
  const m = /^([a-z]+)\^([234])$/.exec(s);
  if (!m || !LENGTH_UNITS.includes(m[1])) return null;
  const k = Number(m[2]);
  return { f: qpow(UNITS[m[1]].f, k), dim: dpow(BASE_DIMS.length, R(BigInt(k))) };
}
// format.md, The verdict: the unit that a value in Petra's SI is in, printed after the value of
// each load of a completion. "The first unit of factor 1 for the load's dimension, as `N`, `Pa` or
// `m`, or the exponents of the dimension, as `kg^1 s^-2`, when there is none, and `1` for a plain
// number." So a temperature is in `degC`. "First" is taken in the order of the units list
// (pages/units.md), which UNITS keeps; `N m`, which only a deck reads, is not of that list. The
// exponents are written as a `dim` of a file is (format.md, Numbers): the bases m, kg, s, A and
// degC in that order, each that is not zero with `^` and its number, one space between two
// (AMBIGUITIES.md, N4).
export function siUnit(dim) {
  if (deq(dim, DL)) return '1';
  for (const name of Object.keys(UNITS)) {
    if (name === 'N m') continue;
    const u = UNITS[name];
    if (u.f.n === 1n && u.f.d === 1n && deq(u.dim, dim)) return name;
  }
  return FILE_BASES.map((b, i) => (dim[i].n === 0n ? null : `${b}^${dim[i]}`)).filter((x) => x !== null).join(' ');
}

// A value of a deck (deck.md, "A value with its unit"): a number, one space and a unit, or a
// number alone, which is a plain number of no dimension. The number is digits with an optional
// sign and a decimal part or a denominator that is not zero, or a whole number and a fraction
// with exactly one space between them and no sign. A comma is read between thousands, only in the
// digits before a decimal point of a whole number or a decimal; a number with a `/` takes none.
// Spaces, tabs and line ends (LF, CR) around the value are dropped. The space that parts the
// number from its unit is the first space after the number, U+0020; more spaces, tabs and line
// ends may follow it and are dropped. The unit is the rest, read whole (`N m` holds a space).
// Returns {v (SI), dim, hasUnit} or null.
const INTC = '(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)';
const VALUE_RE = new RegExp(
  `^(?:([0-9]+) ([0-9]+)/([0-9]+)|([+-]?)(?:(${INTC})(?:\\.([0-9]+))?|([0-9]+)/([0-9]+)))` +
  '(?: [ \\t\\r\\n]*([\\s\\S]+))?$');
const trimWs = (s) => s.replace(/^[ \t\r\n]+|[ \t\r\n]+$/g, '');
export function parseValue(s) {
  if (typeof s !== 'string' || s.length > MAXLEN) return null;
  const m = VALUE_RE.exec(trimWs(s));
  if (!m) return null;
  const [, mi, mn, md, sign, ip, dec, fn, fd, unit] = m;
  let v;
  if (mi !== undefined) {
    if (BigInt(md) === 0n) return null;
    v = qadd(R(BigInt(mi)), R(BigInt(mn), BigInt(md)));
  } else {
    if (fn !== undefined) {
      if (BigInt(fd) === 0n) return null;
      v = R(BigInt(fn), BigInt(fd));
    } else {
      const ints = ip.replace(/,/g, '');
      v = dec !== undefined ? R(BigInt(ints + dec), 10n ** BigInt(dec.length)) : R(BigInt(ints));
    }
    if (sign === '-') v = qneg(v);
  }
  if (unit === undefined) return { v, dim: DL, hasUnit: false };
  const u = unitOf(unit);
  if (!u) return null;
  return { v: qmul(v, u.f), dim: u.dim, hasUnit: true };
}
// A value that must have the dimension `dim`. A bare `0` is the plain number zero and not the
// zero of every dimension (deck.md): a length that is zero is written `0 mm`.
function quantityOf(s, dim) {
  const q = parseValue(s);
  return q && deq(q.dim, dim) ? q.v : null;
}
// `["q", NUMBER, UNIT]`: its two halves joined with one space and read as one value (H4).
const qValue = (e) => parseValue(`${e[1]} ${e[2]}`);

// ============================================================ JSON

class JsonErr extends Error {}
// format.md, Texts: no text and no key holds U+FFFD, and a reader that keeps half a surrogate
// pair as it is refuses a text with half a pair in it.
function badText(s) {
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c < 0xd800 || (c > 0xdfff && c !== 0xfffd)) continue;
    if (c === 0xfffd || c >= 0xdc00) return true;
    const d = s.charCodeAt(i + 1);
    if (!(d >= 0xdc00 && d <= 0xdfff)) return true;
    i++;
  }
  return false;
}
export function parseJson(text) {
  let i = 0;
  const n = text.length;
  const err = (m) => { throw new JsonErr(`${m} at character ${i}`); };
  const ws = () => {
    while (i < n) {
      const c = text.charCodeAt(i);
      if (c === 32 || c === 9 || c === 10 || c === 13) i++;
      else break;
    }
  };
  const numRe = /-?(?:0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?/y;
  // format.md, Keys: "The value before it is not read: nothing in it is a finding, whatever kind
  // of value it is, and a U+FFFD in it is not seen". So a text or a key with U+FFFD, or with half
  // a surrogate pair, which the kernel "reads as U+FFFD" (Texts), refuses the file only where the
  // file is read. `seen` is the place of the first such text in the value being gone through, or
  // -1, and an object forgets what a value held when the same key comes again.
  let seen = -1;
  function str() {
    i++;
    let out = '';
    let start = i;
    for (;;) {
      if (i >= n) err('unterminated string');
      const c = text.charCodeAt(i);
      if (c === 34) {
        out += text.slice(start, i);
        if (seen < 0 && badText(out)) seen = i;
        i++;
        return out;
      }
      if (c === 92) {
        out += text.slice(start, i);
        const e = text[i + 1];
        i += 2;
        switch (e) {
          case '"': out += '"'; break;
          case '\\': out += '\\'; break;
          case '/': out += '/'; break;
          case 'b': out += '\b'; break;
          case 'f': out += '\f'; break;
          case 'n': out += '\n'; break;
          case 'r': out += '\r'; break;
          case 't': out += '\t'; break;
          case 'u': {
            const h = text.slice(i, i + 4);
            if (!/^[0-9a-fA-F]{4}$/.test(h)) err('bad \\u escape');
            out += String.fromCharCode(parseInt(h, 16));
            i += 4;
            break;
          }
          default: err('bad escape');
        }
        start = i;
        continue;
      }
      if (c < 32) err('control character in a string');
      i++;
    }
  }
  function val(depth) {
    ws();
    if (i >= n) err('unexpected end of text');
    const c = text[i];
    if (c === '{') {
      if (depth + 1 > 128) err('JSON nests more than 128 deep');
      i++;
      const obj = Object.create(null);
      ws();
      if (text[i] === '}') { i++; return obj; }
      // format.md, Keys: "An object that holds one key twice is read with the last value the
      // file gives the key, and the file is not refused for the repeat. The value before it is
      // not read: nothing in it is a finding, whatever kind of value it is, and a U+FFFD in it is
      // not seen. It is still part of the file's bytes, so the limits that are tested on the
      // bytes before the file is read hold for it: the nesting of the file, and the digits of a
      // number outside a string". So the value before the last is gone through as any JSON, with
      // its nesting and its bare numbers held to Limits, and a U+FFFD in it is dropped when its
      // key comes again (AMBIGUITIES.md, P2 and P15). A key is read whatever its value is.
      const before = seen;
      let inKey = -1;
      let inValue = null;
      for (;;) {
        ws();
        if (text[i] !== '"') err('expected a key');
        seen = -1;
        const k = str();
        if (seen >= 0 && inKey < 0) inKey = seen;
        ws();
        if (text[i] !== ':') err('expected :');
        i++;
        seen = -1;
        obj[k] = val(depth + 1);
        if (seen >= 0) (inValue ??= new Map()).set(k, seen);
        else if (inValue) inValue.delete(k);
        ws();
        if (text[i] === ',') { i++; continue; }
        if (text[i] === '}') {
          i++;
          seen = before >= 0 ? before : inKey;
          if (seen < 0 && inValue) for (const at of inValue.values()) { seen = at; break; }
          return obj;
        }
        err('expected , or }');
      }
    }
    if (c === '[') {
      if (depth + 1 > 128) err('JSON nests more than 128 deep');
      i++;
      const arr = [];
      ws();
      if (text[i] === ']') { i++; return arr; }
      for (;;) {
        arr.push(val(depth + 1));
        ws();
        if (text[i] === ',') { i++; continue; }
        if (text[i] === ']') { i++; return arr; }
        err('expected , or ]');
      }
    }
    if (c === '"') return str();
    if (text.startsWith('true', i)) { i += 4; return true; }
    if (text.startsWith('false', i)) { i += 5; return false; }
    if (text.startsWith('null', i)) { i += 4; return null; }
    numRe.lastIndex = i;
    const m = numRe.exec(text);
    if (!m || m.index !== i) err('unexpected character');
    if (m[1] !== undefined || m[2] !== undefined) err('a number outside a string has a fraction or an exponent');
    const digits = m[0].replace('-', '');
    if (digits.length > 32) err('a number outside a string has more than 32 digits');
    i += m[0].length;
    return BigInt(m[0]);
  }
  const v = val(0);
  ws();
  if (i < n) err('text after the JSON value');
  if (seen >= 0) { i = seen; err('a text or a key that is read holds U+FFFD or half a surrogate pair'); }
  return v;
}

const isObj = (x) => x !== null && typeof x === 'object' && !Array.isArray(x);
const isStr = (x) => typeof x === 'string';
const NAME_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
const short = (x) => {
  let s;
  try { s = JSON.stringify(x, (k, v) => (typeof v === 'bigint' ? Number(v) : v)); } catch { s = String(x); }
  if (s === undefined) s = String(x);
  return s.length > 80 ? s.slice(0, 77) + '...' : s;
};

// format.md, Limits: the bytes a name prints in. "A quote, a backslash and a line end print in
// two, and a character that a terminal acts on and does not show prints as an escape of six, `\u`
// and four digits of base 16. A line end is a line feed, U+000A, or a carriage return, U+000D. The
// characters that print in six are the control characters, which are every other character below
// U+0020 and U+007F to U+009F, the line and the paragraph separator, U+2028 and U+2029, and the
// marks that turn the direction of text, U+061C, U+200E, U+200F, U+202A to U+202E and U+2066 to
// U+2069. The tab is one of them. Any other character outside ASCII prints in the bytes of its
// UTF-8, which are two, three or four." The list is taken as it stands (AMBIGUITIES.md, O4).
// The characters from U+007F on that print in six, as ranges of code points. They are written as
// numbers, so that this file holds none of them.
const SIX_FROM_DEL = [[0x7f, 0x9f], [0x61c, 0x61c], [0x200e, 0x200f], [0x2028, 0x2029], [0x202a, 0x202e], [0x2066, 0x2069]];
export function printsInSix(c) {
  if (c === 0x0a || c === 0x0d) return false;
  return c < 0x20 || SIX_FROM_DEL.some(([a, b]) => c >= a && c <= b);
}
const SIX_RE = new RegExp(`[${SIX_FROM_DEL.map(([a, b]) => `${String.fromCharCode(a)}-${String.fromCharCode(b)}`).join('')}]`, 'g');
const sixEscape = (ch) => `${String.fromCharCode(0x5c)}u${ch.charCodeAt(0).toString(16).padStart(4, '0')}`;
export function printedBytes(s) {
  let n = 0;
  for (const ch of s) {
    const c = ch.codePointAt(0);
    if (c === 0x22 || c === 0x5c || c === 0x0a || c === 0x0d) n += 2;
    else if (printsInSix(c)) n += 6;
    else if (c < 0x80) n += 1;
    else if (c < 0x800) n += 2;
    else if (c < 0x10000) n += 3;
    else n += 4;
  }
  return n;
}
// What the kernel prints: its one JSON object, with every text written as the sentences above
// count it. JSON.stringify writes a quote, a backslash and a line end in two, and the other
// characters below U+0020 in six, but for the backspace, the form feed and the tab, which it
// writes in two (`\b`, `\f`, `\t`): those are written as `\u0008`, `\u000c` and `\u0009` here. It
// writes U+007F to U+009F, the two separators and the marks of direction as they are: here each is
// the escape of six. "So nothing a card, a design or a deck holds can move the cursor of a terminal
// that shows the verdict, or write over a line of it." The JSON reads back as the same object.
export function printVerdict(out) {
  return JSON.stringify(out, null, 1)
    .replace(/\\[\s\S]/g, (m) => (m === '\\b' ? '\\u0008' : m === '\\f' ? '\\u000c' : m === '\\t' ? '\\u0009' : m))
    .replace(SIX_RE, sixEscape);
}
const NAME_BYTES = 64;
const LABEL_NAME_BYTES = 200;

// format.md, Limits, "A text that is cut": "A text that prints in at most 200 bytes is printed
// whole. A longer one is cut in this one way." The bytes are those it prints in, character by
// character, a character being one code point. "The kernel takes the characters in order from the
// first and keeps each while its bytes fit in what is left of the 200. It stops at the first
// character that does not fit, and keeps nothing after it, though a later character might fit."
// "After the kept start come the words `... (N more characters)` ... `N` is the number of
// characters left out, the characters of the whole text less those kept ... The word is
// `characters` for one, too." The ending is outside the 200 bytes. "A text is cut once, where it
// is made": the callers say where (AMBIGUITIES.md, S5 and T7).
export const TEXT_BYTES = 200;
export function cutText(s) {
  if (printedBytes(s) <= TEXT_BYTES) return s;
  const chars = [...s];
  let left = TEXT_BYTES, kept = 0;
  for (; kept < chars.length; kept++) {
    const b = printedBytes(chars[kept]);
    if (b > left) break;
    left -= b;
  }
  return `${chars.slice(0, kept).join('')}... (${chars.length - kept} more characters)`;
}
// format.md, Limits, "The room of the reasons": three rooms of 500,000 bytes as printed, for the
// reasons of the refuted cells, of the cells that are not applicable, and of every other cell.
export const REASON_ROOM = 500_000;
export const PAST_ROOM = 'past what the verdict prints of reasons';

// deck.md, "The size of a deck": the steps to read a deck, counted from its JSON alone.
// 1. A number, true, false and null are 1; a text is 2 and 1 more for each 8 code points; a list
//    is 1 more than its items and an object 1 more than its values; a key is not counted.
// 2. Each list ["row", ID, BINDS] (three items, the first the text row, the second a text)
//    inside an item of `rules` counts the size of the first item of `rows` that is an object
//    with that id, and nothing when there is none.
// 3. The steps are the size of the whole file and what rule 2 counts.
export const DECK_STEPS = 1_000_000;
const codePoints = (s) => {
  let n = s.length;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) { const d = s.charCodeAt(i + 1); if (d >= 0xdc00 && d <= 0xdfff) { n--; i++; } }
  }
  return n;
};
function jsonSize(v) {
  if (typeof v === 'string') return 2 + Math.floor(codePoints(v) / 8);
  if (Array.isArray(v)) { let s = 1; for (const x of v) s += jsonSize(x); return s; }
  if (isObj(v)) { let s = 1; for (const k of Object.keys(v)) s += jsonSize(v[k]); return s; }
  return 1;
}
export function deckSteps(D) {
  let total = jsonSize(D);
  if (!isObj(D) || !Array.isArray(D.rules)) return total;
  const rows = Array.isArray(D.rows) ? D.rows : [];
  const firstRow = new Map();
  for (const r of rows) if (isObj(r) && isStr(r.id) && !firstRow.has(r.id)) firstRow.set(r.id, r);
  const sizeOf = new Map();
  const walk = (v) => {
    if (Array.isArray(v)) {
      if (v.length === 3 && v[0] === 'row' && isStr(v[1]) && firstRow.has(v[1])) {
        let s = sizeOf.get(v[1]);
        if (s === undefined) { s = jsonSize(firstRow.get(v[1])); sizeOf.set(v[1], s); }
        total += s;
      }
      for (const x of v) walk(x);
    } else if (isObj(v)) for (const k of Object.keys(v)) walk(v[k]);
  };
  for (const item of D.rules) walk(item);
  return total;
}

// ============================================================ transcendentals

const GRID_BITS = 96n;
const GRID = 1n << GRID_BITS;
const gq = (k) => R(k, GRID);

// sqrt of q >= 0 on the grid: [floor(2^96 sqrt q), ceil(2^96 sqrt q)] / 2^96.
export function sqrtEnc(q) {
  if (q.n === 0n) return [Q0, Q0];
  const num = q.n << (2n * GRID_BITS);
  const s = isqrt(num / q.d);
  const exact = s * s * q.d === num;
  return [gq(s), gq(exact ? s : s + 1n)];
}

function snap(lo, hi, p) {
  // lo, hi: fixed point with p fractional bits; outward to the 2^-96 grid
  const sh = p - GRID_BITS;
  return [lo >> sh, -((-hi) >> sh)];
}

let piCache = null;
function atanInvFixed(k, p) {
  // atan(1/k) * 2^p as [value, error bound in ulps]
  const one = 1n << p;
  let sum = 0n, j = 0n, pw = k, terms = 0n;
  for (;;) {
    const t = one / ((2n * j + 1n) * pw);
    if (t === 0n) break;
    sum += j % 2n === 0n ? t : -t;
    j++; pw *= k * k; terms++;
  }
  return [sum, terms + 2n];
}
export function piEnc() {
  if (piCache) return piCache;
  for (let p = 192n; ; p *= 2n) {
    const [a5, e5] = atanInvFixed(5n, p);
    const [a239, e239] = atanInvFixed(239n, p);
    const lo = 16n * (a5 - e5) - 4n * (a239 + e239);
    const hi = 16n * (a5 + e5) - 4n * (a239 - e239);
    const [glo, ghi] = snap(lo, hi, p);
    if (ghi - glo <= 1n) { piCache = [gq(glo), gq(ghi)]; return piCache; }
  }
}

// e^x on the grid, |x| <= 65536.
export function expEnc(x) {
  if (x.n === 0n) return [Q1, Q1];
  const neg = x.n < 0n;
  const a = neg ? qneg(x) : x;
  const af = Number(floorDiv(a.n * 1024n, a.d)) / 1024;
  const k = BigInt(bitlen(a.n / a.d) + 8);
  for (let guard = 64; ; guard *= 2) {
    const vBits = neg ? 0 : Math.ceil(af * 1.4426950408889634) + 2;
    const p = BigInt(96 + guard + vBits + 16) + k;
    const one = 1n << p;
    const sh = p - k;
    const yLo = (a.n << sh) / a.d;
    const yHi = ceilDiv(a.n << sh, a.d);
    let s = one, t = one;
    for (let j = 1n; ; j++) {
      t = (t * yLo) / (j * one);
      if (t === 0n) break;
      s += t;
    }
    let lo = s;
    s = one; t = one;
    for (let j = 1n; ; j++) {
      t = ceilDiv(t * yHi, j * one);
      s += t;
      if (t <= 1n) { s += 1n; break; }
    }
    let hi = s;
    for (let i = 0n; i < k; i++) {
      lo = (lo * lo) >> p;
      hi = ceilDiv(hi * hi, one);
    }
    if (neg) {
      const one2 = one * one;
      const nlo = one2 / hi, nhi = ceilDiv(one2, lo);
      lo = nlo; hi = nhi;
    }
    const [glo, ghi] = snap(lo, hi, p);
    if (ghi - glo <= 1n || guard > 4096) return [gq(glo), gq(ghi)];
  }
}

// atanh(z) * 2^p for z = zn/zd in [0, 1/3], as [lo, hi].
function atanhFixed(zn, zd, p) {
  if (zn === 0n) return [0n, 0n];
  const one = 1n << p;
  const zLo = (zn << p) / zd, zHi = ceilDiv(zn << p, zd);
  let S = 0n, P = zLo;
  const z2Lo = (zLo * zLo) >> p;
  for (let j = 0n; P > 0n; j++) {
    S += P / (2n * j + 1n);
    P = (P * z2Lo) >> p;
  }
  const lo = S;
  S = 0n; P = zHi;
  const z2Hi = ceilDiv(zHi * zHi, one);
  for (let j = 0n; ; j++) {
    S += ceilDiv(P, 2n * j + 1n);
    P = ceilDiv(P * z2Hi, one);
    if (P <= 2n) { S += 2n * P + 2n; break; }
  }
  return [lo, S];
}
const ln2Cache = new Map();
function ln2Fixed(p) {
  let v = ln2Cache.get(p);
  if (!v) {
    const [a, b] = atanhFixed(1n, 3n, p);
    v = [2n * a, 2n * b];
    ln2Cache.set(p, v);
  }
  return v;
}
// ln x on the grid, x > 0.
export function lnEnc(x) {
  if (x.n === x.d) return [Q0, Q0];
  let e = bitlen(x.n) - bitlen(x.d);
  let mn, md;
  for (;;) {
    if (e >= 0) { mn = x.n; md = x.d << BigInt(e); } else { mn = x.n << BigInt(-e); md = x.d; }
    if (3n * mn >= 4n * md) e++;
    else if (3n * mn < 2n * md) e--;
    else break;
  }
  const zn = mn - md, zd = mn + md;
  const zneg = zn < 0n;
  const za = zneg ? -zn : zn;
  const E = BigInt(e);
  for (let guard = 64; ; guard *= 2) {
    const p = BigInt(96 + guard + 8 + bitlen(absB(E)));
    const [alo, ahi] = atanhFixed(za, zd, p);
    const [l2lo, l2hi] = ln2Fixed(p);
    let lo = E >= 0n ? E * l2lo : E * l2hi;
    let hi = E >= 0n ? E * l2hi : E * l2lo;
    if (zneg) { lo -= 2n * ahi; hi -= 2n * alo; } else { lo += 2n * alo; hi += 2n * ahi; }
    const [glo, ghi] = snap(lo, hi, p);
    if (ghi - glo <= 1n || guard > 4096) return [gq(glo), gq(ghi)];
  }
}

// format.md, Tapes, "The square root of an enclosure": a point that is the square of a fraction
// has that fraction for its root. The whole roots of the numerator and of the denominator,
// rounded down, and their quotient when its square is the point. Null for any other point.
export function sqrtExact(q) {
  if (q.n < 0n) return null;
  const rn = isqrt(q.n), rd = isqrt(q.d);
  return rn * rn === q.n && rd * rd === q.d ? new Q(rn, rd) : null;
}

// cos x * 2^P as [lo, hi], an enclosure for a fraction x with |x| <= 65536. As format.md says the
// reference does it: the angle is halved s times, the series of the cosine is summed with its
// remainder, and the angle is doubled s times again by cos 2y = 2 cos^2 y - 1.
function cosFixed(x, P) {
  const a = absB(x.n), d = x.d;
  let s = 0n;
  while ((a << 1n) > (d << s)) s++; // |x| / 2^s <= 1/2
  const one = 1n << P;
  // z = (x / 2^s)^2, at most 1/4, held between two points of the fixed grid.
  const zNum = a * a, zDen = (d * d) << (2n * s);
  const zLo = (zNum << P) / zDen, zHi = ceilDiv(zNum << P, zDen);
  // The sum of (-1)^k z^k / (2k)!. Each term is rounded down from the one before, so it is at
  // most 2 below its true value, and the first term that rounds to 0 bounds the remainder by 2.
  const series = (Z) => {
    let T = one, S = one, k = 0n;
    for (;;) {
      k++;
      T = (T * Z) / (one * (2n * k - 1n) * (2n * k));
      if (T === 0n) break;
      S += k % 2n === 1n ? -T : T;
    }
    return [S, 2n * k + 2n];
  };
  // cos of the root of z falls as z rises on [0, 1/4].
  const [sH, eH] = series(zHi), [sL, eL] = series(zLo);
  let lo = sH - eH, hi = sL + eL;
  const clamp = () => { if (lo < -one) lo = -one; if (hi > one) hi = one; };
  clamp();
  for (let i = 0n; i < s; i++) {
    let qlo, qhi;
    if (lo >= 0n) { qlo = lo * lo; qhi = hi * hi; } else if (hi <= 0n) { qlo = hi * hi; qhi = lo * lo; } else { qlo = 0n; qhi = lo * lo > hi * hi ? lo * lo : hi * hi; }
    lo = 2n * (qlo >> P) - one;
    hi = 2n * ceilDiv(qhi, one) - one;
    clamp();
  }
  return [lo, hi];
}

// format.md, Tapes, "The cosine of an enclosure": the grid points at or under and at or over the
// cosine of one end, or null when it has none. The cosine of 0 is 1. The cosine of any other
// fraction lies strictly between two neighbouring grid points, and those are its enclosure; one
// that is closer to a grid point other than 1 and -1 than 2^-2144 has no value. The enclosure is
// asked for at 128, 224 and 608 bits, and last at 2,160, under the finest width of 2^-2144.
const COS_LEVELS = [128n, 224n, 608n, 2160n];
const COS_FINEST = 2144n;
const cosCache = new Map();
function cosEnd(x) {
  if (x.n === 0n) return [Q1, Q1];
  const key = `${absB(x.n)}/${x.d}`; // the cosine of an end is the cosine of its negative
  if (cosCache.has(key)) return cosCache.get(key);
  let res = null;
  const top = 1n << GRID_BITS; // the grid index of 1
  for (const T of COS_LEVELS) {
    const final = T === COS_LEVELS[COS_LEVELS.length - 1];
    let P = T + 64n, A, B;
    for (;;) {
      [A, B] = cosFixed(x, P);
      if (B - A <= (1n << (P - T))) break;
      P += 64n;
    }
    const G = 1n << (P - GRID_BITS);
    // The grid points other than 1 and -1 that the enclosure holds, or at the last level that lie
    // within 2^-2144 of it.
    const slack = final ? 1n << (P - COS_FINEST) : 0n;
    const gFirst = ceilDiv(A - slack, G), gLast = floorDiv(B + slack, G);
    let held = gLast - gFirst + 1n;
    if (held > 0n) {
      if (gFirst <= top && top <= gLast) held--;
      if (gFirst <= -top && -top <= gLast) held--;
    }
    if (held <= 0n) { const g = floorDiv(A, G); res = [gq(g), gq(g + 1n)]; break; }
    if (final) break;
  }
  if (cosCache.size >= 4096) cosCache.clear();
  cosCache.set(key, res);
  return res;
}
const QM1 = new Q(-1n, 1n);
const ANGLE_LIMIT = R(65536n);
// The enclosure of the cosine of an angle [lo, hi], or null when it has none: when it reaches
// below -65,536 or above 65,536, or the cosine of an end has none. The enclosure is placed among
// the multiples of pi with the kernel's pi: i is the greatest whole number with i pi at or under
// lo, and j the least with hi at or under j pi, each tested with the end of pi that makes the test
// harder (AMBIGUITIES.md, K2). The cosines of both ends are taken in every case (K1).
export function cosEnc(v) {
  const [lo, hi] = v;
  if (qcmp(lo, qneg(ANGLE_LIMIT)) < 0 || qcmp(hi, ANGLE_LIMIT) > 0) return null;
  const [pL, pH] = piEnc();
  const i = lo.n >= 0n ? floorDiv(lo.n * pH.d, lo.d * pH.n) : floorDiv(lo.n * pL.d, lo.d * pL.n);
  const j = hi.n > 0n ? ceilDiv(hi.n * pL.d, hi.d * pL.n) : ceilDiv(hi.n * pH.d, hi.d * pH.n);
  const cLo = cosEnd(lo);
  const cHi = qcmp(lo, hi) === 0 ? cLo : cosEnd(hi);
  if (!cLo || !cHi) return null;
  const even = i % 2n === 0n;
  if (j <= i + 1n) return even ? [cHi[0], cLo[1]] : [cLo[0], cHi[1]];
  if (j === i + 2n) return even ? [QM1, qmax(cLo[1], cHi[1])] : [qmin(cLo[0], cHi[0]), Q1];
  return [QM1, Q1];
}

// ============================================================ interval evaluation of a tape

const BITS_LIMIT = 65536;
const tooBig = (q) => bitlen(q.n) > BITS_LIMIT || bitlen(q.d) > BITS_LIMIT;
const EXP_LIMIT = R(65536n);

function imul(a, b) {
  const p = [qmul(a[0], b[0]), qmul(a[0], b[1]), qmul(a[1], b[0]), qmul(a[1], b[1])];
  return [p.reduce(qmin), p.reduce(qmax)];
}
function ipow(a, k) {
  if (k === 0) return [Q1, Q1];
  const lb = Math.max(bitlen(a[0].n), bitlen(a[0].d), bitlen(a[1].n), bitlen(a[1].d));
  if ((lb - 1) * k + 1 > BITS_LIMIT) return null;
  const pl = qpow(a[0], k), ph = qpow(a[1], k);
  if (k % 2 === 1) return [pl, ph];
  if (a[0].n >= 0n) return [pl, ph];
  if (a[1].n <= 0n) return [ph, pl];
  return [Q0, qmax(pl, ph)];
}
function idiv(a, b) {
  if (b[0].n <= 0n && b[1].n >= 0n) return null;
  return imul(a, [qdiv(Q1, b[1]), qdiv(Q1, b[0])]);
}

// Tape: nodes as in format.md; constants are kept as Q beside their node.
export class Tape {
  constructor() {
    this.nodes = [];
    this.keys = new Map();
    this.cq = new Map();
    this.inputs = [];
    this.labels = new Map();
    this.roots = [];
  }
  add(node) {
    const k = JSON.stringify(node);
    let i = this.keys.get(k);
    if (i === undefined) {
      if (this.onNode) this.onNode();
      i = this.nodes.length;
      this.nodes.push(node);
      this.keys.set(k, i);
    }
    return i;
  }
  c(q) {
    const i = this.add(['c', q.toString()]);
    this.cq.set(i, q);
    return i;
  }
  input(label, lo, hi) {
    let k = this.labels.get(label);
    if (k === undefined) {
      k = this.inputs.length;
      this.inputs.push({ label, lo, hi });
      this.labels.set(label, k);
    }
    return this.add(['s', k]);
  }
}

const MAX_WAYS = 4096;

// The enclosure of node i, a node other than a pick, on a box, or null when it has none there.
// get(j) is the enclosure of node j, or null.
function nodeEnc(tape, i, nd, box, get) {
  let r = null;
  switch (nd[0]) {
    case 'c': {
      const q = tape.cq.get(i) ?? parseFileNumber(nd[1]);
      r = [q, q];
      break;
    }
    case 's': r = box[nd[1]]; break;
    case 'pi': r = piEnc(); break;
    case 'add': {
      // format.md, Limits: a value with more than 65,536 bits in its numerator or its denominator
      // has none, and "that holds for every node of a tape, and for each sum and each product so
      // far of a node that adds or multiplies many, at a point as over a box". So each sum so far
      // is held to the bits, as each product so far is below, and not the last alone.
      let lo = Q0, hi = Q0, ok = true;
      for (const j of nd[1]) {
        const v = get(j);
        if (!v) { ok = false; break; }
        lo = qadd(lo, v[0]); hi = qadd(hi, v[1]);
        if (tooBig(lo) || tooBig(hi)) { ok = false; break; }
      }
      r = ok ? [lo, hi] : null;
      break;
    }
    case 'mul': {
      let acc = [Q1, Q1];
      for (const j of nd[1]) {
        const v = get(j);
        if (!v) { acc = null; break; }
        acc = imul(acc, v);
        if (tooBig(acc[0]) || tooBig(acc[1])) { acc = null; break; }
      }
      r = acc;
      break;
    }
    case 'min': case 'max': {
      let acc = null, ok = true;
      for (const j of nd[1]) {
        const v = get(j);
        if (!v) { ok = false; break; }
        if (!acc) acc = v;
        else if (nd[0] === 'min') acc = [qmin(acc[0], v[0]), qmin(acc[1], v[1])];
        else acc = [qmax(acc[0], v[0]), qmax(acc[1], v[1])];
      }
      r = ok ? acc : null;
      break;
    }
    case 'neg': { const v = get(nd[1]); r = v ? [qneg(v[1]), qneg(v[0])] : null; break; }
    case 'abs': {
      const v = get(nd[1]);
      if (!v) break;
      if (v[0].n >= 0n) r = v;
      else if (v[1].n <= 0n) r = [qneg(v[1]), qneg(v[0])];
      else r = [Q0, qmax(qneg(v[0]), v[1])];
      break;
    }
    case 'sqrt': {
      const v = get(nd[1]);
      if (!v || v[0].n < 0n) break;
      // format.md, Tapes: the root of a point that is the square of a fraction is that fraction,
      // and only a point is taken so.
      if (qcmp(v[0], v[1]) === 0) {
        const e = sqrtExact(v[0]);
        if (e) { r = [e, e]; break; }
      }
      r = [sqrtEnc(v[0])[0], sqrtEnc(v[1])[1]];
      break;
    }
    case 'ln': {
      const v = get(nd[1]);
      if (!v || v[0].n <= 0n) break;
      r = [lnEnc(v[0])[0], lnEnc(v[1])[1]];
      break;
    }
    case 'exp': {
      const v = get(nd[1]);
      if (!v || qcmp(qabs(v[0]), EXP_LIMIT) > 0 || qcmp(qabs(v[1]), EXP_LIMIT) > 0) break;
      if (v[1].n > 0n && Number(v[1].n / v[1].d) * 1.4427 > BITS_LIMIT) break;
      r = [expEnc(v[0])[0], expEnc(v[1])[1]];
      break;
    }
    case 'cos': {
      const v = get(nd[1]);
      if (!v) break;
      r = cosEnc(v);
      break;
    }
    case 'div': {
      const a = get(nd[1]);
      if (!a) break;
      const b = get(nd[2]);
      if (!b) break;
      r = idiv(a, b);
      break;
    }
    case 'pow': {
      const v = get(nd[1]);
      if (!v) break;
      const k = nd[2];
      if (k >= 0) r = ipow(v, k);
      else {
        const p = ipow(v, -k);
        r = p ? idiv([Q1, Q1], p) : null;
      }
      break;
    }
    default: r = null;
  }
  if (r && (tooBig(r[0]) || tooBig(r[1]))) r = null;
  return r;
}

// Returns ev(i) -> [lo, hi] or null (no value on the box), memoized and lazy.
export function evaluator(tape, box) {
  const memo = new Array(tape.nodes.length);
  const ev = (i) => {
    const m = memo[i];
    if (m !== undefined) return m;
    const nd = tape.nodes[i];
    let r = nd[0] === 'pick' ? evalPick(nd[1], ev) : nodeEnc(tape, i, nd, box, ev);
    if (r && (tooBig(r[0]) || tooBig(r[1]))) r = null;
    memo[i] = r;
    return r;
  };
  return ev;
}

// The nodes that the conditions of a pick compare, and its pairs, each pair once.
function pickPairs(cases) {
  const pairs = new Map();
  const compared = new Set();
  const walk = (c) => {
    if (c === null) return;
    if (c[0] === 'le' || c[0] === 'lt') {
      compared.add(c[1]); compared.add(c[2]);
      if (c[1] !== c[2]) {
        const a = Math.min(c[1], c[2]), b = Math.max(c[1], c[2]);
        pairs.set(`${a},${b}`, [a, b]);
      }
    } else if (c[0] === 'not') walk(c[1]);
    else for (const x of c[1]) walk(x);
  };
  for (const [c] of cases) walk(c);
  return { compared, plist: [...pairs.values()] };
}

// Each way of taking one order for each pair that the enclosures leave possible, as the index of
// the first case that holds in it, or -1 where none holds; null with more than 4,096 ways.
function pickWays(cases, plist, enc) {
  const pidx = new Map(plist.map(([a, b], k) => [`${a},${b}`, k]));
  const opts = plist.map(([a, b]) => {
    const A = enc(a), B = enc(b);
    const o = [];
    if (qcmp(A[0], B[1]) < 0) o.push(-1);
    if (qcmp(A[0], B[1]) <= 0 && qcmp(B[0], A[1]) <= 0) o.push(0);
    if (qcmp(A[1], B[0]) > 0) o.push(1);
    return o;
  });
  let ways = 1;
  for (const o of opts) { ways *= o.length; if (ways > MAX_WAYS) return null; }
  const choice = new Array(plist.length).fill(0);
  const rel = (x, y) => {
    if (x === y) return 0;
    if (x < y) { const k = pidx.get(`${x},${y}`); return opts[k][choice[k]]; }
    return -rel(y, x);
  };
  const holds = (c) => {
    if (c === null) return true;
    switch (c[0]) {
      case 'le': return rel(c[1], c[2]) <= 0;
      case 'lt': return rel(c[1], c[2]) < 0;
      case 'and': return c[1].every(holds);
      case 'or': return c[1].some(holds);
      case 'not': return !holds(c[1]);
      default: return false;
    }
  };
  const firsts = [];
  for (let w = 0; w < ways; w++) {
    let x = w;
    for (let k = 0; k < plist.length; k++) { choice[k] = x % opts[k].length; x = Math.floor(x / opts[k].length); }
    let f = -1;
    for (let ci = 0; ci < cases.length; ci++) if (holds(cases[ci][0])) { f = ci; break; }
    firsts.push(f);
  }
  return firsts;
}

function evalPick(cases, ev) {
  const { compared, plist } = pickPairs(cases);
  for (const k of compared) if (!ev(k)) return null;
  const firsts = pickWays(cases, plist, ev);
  if (!firsts || firsts.includes(-1)) return null;
  let lo = null, hi = null;
  for (const f of [...new Set(firsts)].sort((a, b) => a - b)) {
    const v = ev(cases[f][1]);
    if (!v) return null;
    lo = lo === null ? v[0] : qmin(lo, v[0]);
    hi = hi === null ? v[1] : qmax(hi, v[1]);
  }
  return [lo, hi];
}

// format.md, The rules, item 5: on a line the card waives, a rule whose `where` is not proved asks
// whether the `where` holds nowhere in the box: whether a root of its tape has an enclosure over
// the whole box, walked as a proof walks one leaf, whose lower end is above zero. A root with no
// value at some point is not above zero there. Returns the index of the first such root, or -1.
// (The walk of item 6, which asked whether a root had no value anywhere, rests nothing now.)
const fullBox = (tape) => tape.inputs.map((inp) => [inp.lo, inp.hi]);
export function holdsNowhere(tape) {
  const ev = evaluator(tape, fullBox(tape));
  return tape.roots.findIndex((r) => { const v = ev(r); return !!v && v[0].n > 0n; });
}

// format.md, Cells 6: "The root of this tape reads an input when it reads the input's node,
// directly or through the nodes it reads: the nodes of a sum, a product or any other arithmetic,
// the nodes that a pick compares, and the node of each case of a pick. A tape may hold an input
// that its root does not read, as the quantity bound to an input of a row that the row does not
// use." The exponent of a `pow` is a number of the node and no node.
export function rootReadsInput(tape, root) {
  const seen = new Set();
  const stack = [root];
  const cond = (c0) => {
    const cs = [c0];
    while (cs.length) {
      const c = cs.pop();
      if (c === null) continue;
      if (c[0] === 'le' || c[0] === 'lt') stack.push(c[1], c[2]);
      else if (c[0] === 'not') cs.push(c[1]);
      else for (const x of c[1]) cs.push(x);
    }
  };
  while (stack.length) {
    const i = stack.pop();
    if (seen.has(i)) continue;
    seen.add(i);
    const nd = tape.nodes[i];
    switch (nd[0]) {
      case 's': return true;
      case 'c': case 'pi': break;
      case 'add': case 'mul': case 'min': case 'max': for (const j of nd[1]) stack.push(j); break;
      case 'div': stack.push(nd[1], nd[2]); break;
      case 'pick': for (const [c, n] of nd[1]) { cond(c); stack.push(n); } break;
      default: stack.push(nd[1]); // neg, abs, sqrt, ln, exp, cos, and the base of a pow
    }
  }
  return false;
}

const MAX_PARTITION_DEPTH = 64;

// True when the partition proves every root of the tape (each upper end at most zero).
export function proves(tape, partition) {
  if (tape.roots.length === 0) return false;
  const rec = (box, P, depth) => {
    if (P === 'leaf') {
      const ev = evaluator(tape, box);
      for (const r of tape.roots) {
        const v = ev(r);
        if (!v || v[1].n > 0n) return false;
      }
      return true;
    }
    if (!isObj(P) || !isStr(P.input) || !isStr(P.at)) return false;
    if (depth + 1 > MAX_PARTITION_DEPTH) return false;
    const k = tape.labels.get(P.input);
    if (k === undefined) return false;
    const x = parseFileNumber(P.at);
    if (!x) return false;
    const [lo, hi] = box[k];
    if (!(qcmp(lo, x) < 0 && qcmp(x, hi) < 0)) return false;
    const below = box.slice(), above = box.slice();
    below[k] = [lo, x];
    above[k] = [x, hi];
    return rec(below, P.below, depth + 1) && rec(above, P.above, depth + 1);
  };
  return rec(tape.inputs.map((inp) => [inp.lo, inp.hi]), partition, 0);
}

// True when the point has a value for every input, inside its range, and the root's lower end
// is above zero there.
export function refutes(tape, point) {
  if (!isObj(point) || tape.roots.length !== 1) return false;
  const box = [];
  for (const inp of tape.inputs) {
    if (!Object.hasOwn(point, inp.label)) return false;
    const x = parseFileNumber(point[inp.label]);
    if (!x) return false;
    if (qcmp(x, inp.lo) < 0 || qcmp(x, inp.hi) > 0) return false;
    box.push([x, x]);
  }
  const v = evaluator(tape, box)(tape.roots[0]);
  return !!v && v[0].n > 0n;
}

// ============================================================ the deck of rules

class DeckErr extends Error {}
const DE = (m) => new DeckErr(m);
class CannotWrite extends Error {}
// A limit of format.md, Limits, passed while the cells are made.
class LimitErr extends Error {}
export const CELL_STEPS = 10_000_000;
export const CELL_LIMIT = 10_000;
export const MAX_ORDERS = 1024;
// format.md, The rules, item 9: the kernel tries the combinations of names of the unstated keys
// of an incomplete cell while there are at most 4,096 of them.
export const COMPLETION_COMBOS = 4096;

const MAX_EXPR_DEPTH = 1024;

function checkKeys(o, allowed, required, what) {
  if (!isObj(o)) throw DE(`${what} is not an object`);
  for (const k of Object.keys(o)) if (!allowed.includes(k)) throw DE(`${what} has the unknown key ${JSON.stringify(k)}`);
  for (const k of required) if (!Object.hasOwn(o, k)) throw DE(`${what} has no ${k}`);
}
function optText(o, k, what) {
  if (Object.hasOwn(o, k) && !isStr(o[k])) throw DE(`${what}.${k} is not a text`);
}
function checkAnchor(a, what) {
  if (a === undefined) throw DE(`${what} has no anchor`);
  checkKeys(a, ['standard', 'clause', 'equation', 'table', 'page'], [], `${what}.anchor`);
  for (const k of Object.keys(a)) if (!isStr(a[k])) throw DE(`${what}.anchor.${k} is not a text`);
  if (!a.standard || !a.clause) throw DE(`${what}.anchor lacks its standard or its clause`);
}
function checkName(s, what) {
  if (!isStr(s) || !NAME_RE.test(s)) throw DE(`${what} ${short(s)} is not a name of letters, digits and _`);
}
// format.md, The deck of rules: the name of a field, a load, a joined part or a `let` is letters,
// digits and `_`. Another name, of a type or of an input of a row, is a JSON string (format.md,
// rules.json; AMBIGUITIES.md, D4).
function nameText(s, what) {
  if (!isStr(s) || s.length === 0) throw DE(`${what} ${short(s)} is not a name`);
}
// A text the deck must have: `what` of a type, a line; `why` of an item of where.
function needText(o, k, what) {
  if (!Object.hasOwn(o, k)) throw DE(`${what} has no ${k}`);
  if (!isStr(o[k])) throw DE(`${what}.${k} is not a text`);
}
// A text the deck must have and that is not empty: `what` of a field, a load; `says`; `why` of a jump.
function needFullText(o, k, what) {
  needText(o, k, what);
  if (o[k].length === 0) throw DE(`${what}.${k} is the empty text`);
}
// deck.md, The grid, "The reason": "`why` is a text that holds at least one letter, `a` to `z` or
// `A` to `Z`. An `unless` with no `why`, with a `why` that is no text, or with one that holds none
// of those 52 letters, as `""`, `" "`, `"..."` and `"0"`, is refused, and the message is the same
// for all three: `grid MECHANISM: unless: it says why, in a text with a letter in it`." The same
// test holds the `chosen` of a key (deck.md, A key the designer chooses). A letter with an accent,
// or of another alphabet, is none of the 52 (AMBIGUITIES.md, S1).
const LETTER_RE = /[A-Za-z]/;
const hasLetter = (x) => isStr(x) && LETTER_RE.test(x);
function needReason(o, k, what) {
  if (!Object.hasOwn(o, k) || !hasLetter(o[k])) throw DE(`${what}: it says ${k}, in a text with a letter in it`);
}
// format.md, Limits: in a deck of rules the name of a field, a load, a joined part and a let,
// the name of a mechanism and the id of a rule print in at most 64 bytes.
function checkNameBytes(s, what) {
  if (printedBytes(s) > NAME_BYTES) throw DE(`${what} ${short(s)} prints in more than 64 bytes`);
}

// The dimension and the nesting depth of an expression, in a scope that resolves names.
function checkExpr(e, sc) {
  const res = checkExpr0(e, sc);
  if (res.depth > MAX_EXPR_DEPTH) throw DE('an expression nests more than 1,024 deep');
  return res;
}
function checkExpr0(e, sc) {
  if (isStr(e)) {
    if (e.length > MAXLEN) throw DE('a number or a name is longer than 4,000 characters');
    if (e === 'pi') return { dim: DL, depth: 1 };
    if (looksNumeric(e)) {
      if (!parseNumberAlone(e)) throw DE(`${short(e)} is not a number`);
      return { dim: DL, depth: 1 };
    }
    return sc.name(e);
  }
  if (!Array.isArray(e) || e.length === 0 || !isStr(e[0])) throw DE(`${short(e)} is not an expression`);
  const op = e[0];
  const args = e.slice(1);
  const one = () => { if (args.length !== 1) throw DE(`${op} takes one argument`); return checkExpr(args[0], sc); };
  switch (op) {
    case 'q': {
      if (args.length !== 2 || !isStr(args[0]) || !isStr(args[1])) throw DE(`${short(e)} is not a constant with a unit`);
      const v = qValue(e);
      if (!v) throw DE(`${short(e)} is not a value with its unit`);
      return { dim: v.dim, depth: 2 };
    }
    case 'add': case 'mul': case 'min': case 'max': {
      if (args.length < 1) throw DE(`${op} has no argument`);
      const rs = args.map((a) => checkExpr(a, sc));
      let dim;
      if (op === 'mul') dim = rs.reduce((d, r) => dmul(d, r.dim), DL);
      else {
        dim = rs[0].dim;
        for (const r of rs) if (!deq(r.dim, dim)) throw DE(`the arguments of ${op} are of different dimensions`);
      }
      let depth = 0;
      for (const r of rs) if (r.depth > depth) depth = r.depth;
      return { dim, depth: 1 + depth };
    }
    case 'sub': case 'div': {
      if (args.length !== 2) throw DE(`${op} takes two arguments`);
      const a = checkExpr(args[0], sc), b = checkExpr(args[1], sc);
      if (op === 'sub' && !deq(a.dim, b.dim)) throw DE('the two sides of sub are of different dimensions');
      return { dim: op === 'sub' ? a.dim : ddiv(a.dim, b.dim), depth: 1 + Math.max(a.depth, b.depth) };
    }
    case 'neg': case 'abs': { const a = one(); return { dim: a.dim, depth: 1 + a.depth }; }
    case 'sqrt': { const a = one(); return { dim: dpow(a.dim, R(1n, 2n)), depth: 1 + a.depth }; }
    // deck.md, Expressions: the argument of exp, ln and cos is a plain number, and so is the
    // value. A deck that takes the cosine of a length is refused.
    case 'exp': case 'ln': case 'cos': {
      const a = one();
      if (!deq(a.dim, DL)) throw DE(`the argument of ${op} is not a plain number`);
      return { dim: DL, depth: 1 + a.depth };
    }
    case 'pow': {
      if (args.length !== 2) throw DE('pow takes two arguments');
      const b = checkExpr(args[0], sc);
      const x = args[1];
      if (isStr(x) && looksNumeric(x)) {
        const n = parseNumberAlone(x);
        if (!n) throw DE(`${short(x)} is not a number`);
        if (qmul(n, R(2n)).d === 1n) {
          if (qcmp(qabs(n), R(64n)) > 0) throw DE('a whole or a half power has an exponent above 64 in magnitude');
          return { dim: dpow(b.dim, n), depth: 1 + Math.max(b.depth, 1) };
        }
        if (!deq(b.dim, DL)) throw DE('the base of a power that is neither whole nor half is not a plain number');
        return { dim: DL, depth: 1 + Math.max(b.depth, 1) };
      }
      const xe = checkExpr(x, sc);
      if (!deq(b.dim, DL) || !deq(xe.dim, DL)) throw DE('a power with an exponent that varies needs a plain number for both');
      return { dim: DL, depth: 1 + Math.max(b.depth, xe.depth) };
    }
    case 'load':
      if (!sc.load) throw DE('a row reads no load');
      return sc.load(args);
    case 'row':
      if (!sc.row) throw DE('a row applies no row');
      return sc.row(args);
    case 'case':
      if (!sc.case) throw DE('a case is read in a rule and in no row');
      return sc.case(args);
    default:
      throw DE(`${short(op)} is not an operator`);
  }
}

function checkRowCond(c, sc) {
  if (!Array.isArray(c) || c.length === 0 || !isStr(c[0])) throw DE(`${short(c)} is not a condition`);
  const args = c.slice(1);
  switch (c[0]) {
    case 'le': case 'lt': case 'ge': case 'gt': {
      if (args.length !== 2) throw DE(`${c[0]} takes two expressions`);
      const a = checkExpr(args[0], sc), b = checkExpr(args[1], sc);
      if (!deq(a.dim, b.dim)) throw DE(`the two sides of ${c[0]} are of different dimensions`);
      return 1 + Math.max(a.depth, b.depth);
    }
    case 'and': case 'or': {
      if (args.length < 1) throw DE(`${c[0]} has no member`);
      let depth = 0;
      for (const x of args) { const d = checkRowCond(x, sc); if (d > depth) depth = d; }
      return 1 + depth;
    }
    case 'not':
      if (args.length !== 1) throw DE('not takes one condition');
      return 1 + checkRowCond(args[0], sc);
    default:
      throw DE(`${short(c[0])} is not a condition`);
  }
}

function loadSide(s, row, which) {
  checkKeys(s, ['by', 'bands', 'closed', 'at'], ['by'], `table.${which}`);
  if (!isStr(s.by) || !row.inputs.has(s.by)) throw DE(`table.${which}.by names no input of the row`);
  const inp = row.inputs.get(s.by);
  if (inp.kind === 'k') {
    if (Object.hasOwn(s, 'bands') || Object.hasOwn(s, 'at') || Object.hasOwn(s, 'closed')) throw DE(`table.${which} reads a key and has bands or values`);
    return { by: s.by, kind: 'key', names: inp.names, count: inp.names.length };
  }
  const hasB = Object.hasOwn(s, 'bands'), hasA = Object.hasOwn(s, 'at');
  if (hasB === hasA) throw DE(`table.${which} reads a quantity and needs one of bands and at`);
  if (hasB) {
    if (!Array.isArray(s.bands) || s.bands.length === 0) throw DE(`table.${which}.bands is not a list of bands`);
    let closed = 'upper';
    if (Object.hasOwn(s, 'closed')) {
      if (s.closed !== 'upper' && s.closed !== 'lower') throw DE(`table.${which}.closed is neither upper nor lower`);
      closed = s.closed;
    }
    const bands = s.bands.map((b, i) => {
      if (!Array.isArray(b) || b.length !== 2) throw DE(`band ${i + 1} is not a pair`);
      const lo = quantityOf(b[0], inp.dim);
      if (!lo) throw DE(`band ${i + 1} has a lower end ${short(b[0])} that is not a ${dstr(inp.dim)} quantity`);
      let hi = null;
      if (b[1] === null) {
        if (i !== s.bands.length - 1) throw DE(`band ${i + 1} has no upper end and is not the last`);
      } else {
        hi = quantityOf(b[1], inp.dim);
        if (!hi) throw DE(`band ${i + 1} has an upper end ${short(b[1])} that is not a ${dstr(inp.dim)} quantity`);
      }
      return [lo, hi];
    });
    bands.forEach(([lo, hi], i) => {
      if (hi && qcmp(lo, hi) >= 0) throw DE(`band ${i + 1} has its lower end at or above its upper end`);
      if (i > 0 && qcmp(bands[i - 1][1], lo) > 0) throw DE(`band ${i + 1} starts before band ${i} ends`);
    });
    return { by: s.by, kind: 'bands', bands, closed, count: bands.length };
  }
  if (Object.hasOwn(s, 'closed')) throw DE(`table.${which} has closed and no bands`);
  if (!Array.isArray(s.at) || s.at.length === 0) throw DE(`table.${which}.at is not a list of values`);
  const at = s.at.map((v, i) => {
    const q = quantityOf(v, inp.dim);
    if (!q) throw DE(`value ${i + 1} of table.${which}.at, ${short(v)}, is not a quantity of the input's dimension`);
    return q;
  });
  at.forEach((v, i) => { if (i > 0 && qcmp(at[i - 1], v) >= 0) throw DE(`value ${i + 1} of table.${which}.at is not above the one before it`); });
  return { by: s.by, kind: 'at', at, count: at.length };
}

function loadTable(t, row) {
  // deck.md, "A table that gives a name": such a table has `down`, `cells` and perhaps `across`,
  // and no `unit`, `rises` or `falls`.
  if (row.gives.names) checkKeys(t, ['down', 'across', 'cells'], ['down', 'cells'], 'table');
  else checkKeys(t, ['down', 'across', 'cells', 'unit', 'rises', 'falls'], ['down', 'cells'], 'table');
  let unit = null;
  if (Object.hasOwn(t, 'unit')) {
    if (!isStr(t.unit) || !unitOf(t.unit)) throw DE(`table.unit ${short(t.unit)} is not a unit`);
    unit = unitOf(t.unit);
  }
  for (const k of ['rises', 'falls']) {
    if (Object.hasOwn(t, k) && (!Array.isArray(t[k]) || !t[k].every(isStr))) throw DE(`table.${k} is not a list of names`);
  }
  const down = loadSide(t.down, row, 'down');
  const across = Object.hasOwn(t, 'across') ? loadSide(t.across, row, 'across') : null;
  // deck.md: each text of rises and falls is the `by` of a side of this table, a name may stand
  // twice in a list, and no name is in both lists.
  const sides = new Set([down.by, ...(across ? [across.by] : [])]);
  for (const k of ['rises', 'falls']) {
    for (const nm of t[k] ?? []) if (!sides.has(nm)) throw DE(`table.${k} names ${short(nm)}, which is the by of no side of this table`);
  }
  if (t.rises && t.falls && t.rises.some((nm) => t.falls.includes(nm))) throw DE('a name is in both rises and falls');
  // deck.md, `unit`: spaces, tabs and line ends around a cell are dropped first. A cell that then
  // holds a space is read as stating its own unit, and any other cell is read in the table's unit.
  // A table that gives a name has names for cells: one of `one_of`, as a text, or null.
  const cell = (c, where) => {
    if (c === null) return null;
    if (row.gives.names) {
      if (!isStr(c) || !row.gives.names.includes(c)) throw DE(`cell ${where} ${short(c)} is not a name of gives.one_of`);
      return c;
    }
    if (!isStr(c)) throw DE(`cell ${where} ${short(c)} is not a value`);
    const ct = trimWs(c);
    let q = parseValue(ct);
    if (q && unit && !ct.includes(' ')) q = { v: qmul(q.v, unit.f), dim: unit.dim, hasUnit: true };
    if (!q) throw DE(`cell ${where} ${short(c)} is not a value`);
    if (!deq(q.dim, row.gives.dim)) throw DE(`cell ${where} is not of the row's dimension`);
    return q.v;
  };
  if (!Array.isArray(t.cells) || t.cells.length !== down.count) throw DE(`table.cells does not have one line for each of the ${down.count} places of down`);
  const cells = t.cells.map((line, i) => {
    if (!across) return cell(line, `${i + 1}`);
    if (!Array.isArray(line) || line.length !== across.count) throw DE(`line ${i + 1} of table.cells does not have one cell for each of the ${across.count} places across`);
    return line.map((c, j) => cell(c, `${i + 1},${j + 1}`));
  });
  if (row.gives.names) {
    // deck.md: every name of `one_of` is the name of at least one cell, and the refusal names the
    // row and the name.
    const held = new Set(across ? cells.flat() : cells);
    for (const nm of row.gives.names) if (!held.has(nm)) throw DE(`no cell of ${row.id} holds ${short(nm)}, which one_of lists`);
  }
  return { down, across, cells };
}

// The cells of a table that gives a name that hold a name, in the order of its lines and, within
// a line, of its cells (format.md, "How the kernel writes a table").
function nameCells(row) {
  const T = row.table, out = [];
  for (let i = 0; i < T.down.count; i++) {
    if (!T.across) { if (T.cells[i] !== null) out.push({ i, j: null, name: T.cells[i] }); continue; }
    for (let j = 0; j < T.across.count; j++) if (T.cells[i][j] !== null) out.push({ i, j, name: T.cells[i][j] });
  }
  return out;
}
// The orders of a place of a side: two for a band with two ends or a listed value, one for a
// last band with no upper end.
const placeOrders = (side, i) => (side.kind === 'bands' && side.bands[i][1] === null ? 1 : 2);
// The orders of a cell of a table that gives a name: the orders of both its places.
const nameCellOrders = (row, c) => placeOrders(row.table.down, c.i) + (row.table.across ? placeOrders(row.table.across, c.j) : 0);

function loadRow(r, rowsSoFar) {
  checkKeys(r, ['id', 'anchor', 'gives', 'takes', 'is', 'cases', 'table', 'jumps'], ['id', 'gives', 'takes'], 'the row');
  if (!isStr(r.id) || r.id.length === 0) throw DE('the row has no id');
  if (rowsSoFar.has(r.id)) throw DE(`two rows have the id ${r.id}`);
  checkAnchor(r.anchor, 'the row');
  // deck.md: `gives` has `name` and `dim`, or for a table that gives a name `one_of` in place of
  // `dim`: a list of texts that is not empty, each once. Never both.
  checkKeys(r.gives, ['name', 'dim', 'one_of', 'what'], ['name'], 'gives');
  if (!isStr(r.gives.name)) throw DE('gives.name is not a text');
  optText(r.gives, 'what', 'gives');
  if (Object.hasOwn(r.gives, 'dim') === Object.hasOwn(r.gives, 'one_of')) throw DE('gives has not exactly one of dim and one_of');
  let gdim = null, gnames = null;
  if (Object.hasOwn(r.gives, 'dim')) {
    gdim = parseDim(r.gives.dim);
    if (!gdim) throw DE(`gives.dim ${short(r.gives.dim)} is not a dimension`);
  } else {
    const o = r.gives.one_of;
    if (!Array.isArray(o) || o.length === 0 || !o.every(isStr) || new Set(o).size !== o.length) throw DE('gives.one_of is not a list of distinct names');
    gnames = o.slice();
  }
  const row = { id: r.id, gives: { name: r.gives.name, dim: gdim, names: gnames }, inputs: new Map(), kind: null };
  if (!Array.isArray(r.takes)) throw DE('takes is not a list');
  for (const t of r.takes) {
    if (!isObj(t)) throw DE('an input is not an object');
    if (Object.hasOwn(t, 'one_of')) {
      checkKeys(t, ['name', 'one_of', 'what'], ['name', 'one_of'], 'a key input');
      nameText(t.name, 'the input');
      optText(t, 'what', 'the input');
      if (!Array.isArray(t.one_of) || t.one_of.length === 0 || !t.one_of.every(isStr) || new Set(t.one_of).size !== t.one_of.length) throw DE(`the key ${t.name} has no list of distinct names`);
      if (row.inputs.has(t.name)) throw DE(`the row takes ${t.name} twice`);
      row.inputs.set(t.name, { kind: 'k', names: t.one_of.slice() });
    } else {
      // deck.md: every quantity a row takes has a range, each end with its unit.
      checkKeys(t, ['name', 'dim', 'what', 'range'], ['name', 'dim', 'range'], 'an input');
      nameText(t.name, 'the input');
      if (t.name === 'pi') throw DE('an input is named pi');
      optText(t, 'what', 'the input');
      const dim = parseDim(t.dim);
      if (!dim) throw DE(`the input ${t.name} has the dimension ${short(t.dim)}, which is not one`);
      if (!Array.isArray(t.range) || t.range.length !== 2) throw DE(`the range of ${t.name} is not two values`);
      const lo = quantityOf(t.range[0], dim), hi = quantityOf(t.range[1], dim);
      if (!lo || !hi) throw DE(`the range of ${t.name} is not two values of its dimension`);
      if (qcmp(lo, hi) > 0) throw DE(`the range of ${t.name} has its lower value second`);
      if (row.inputs.has(t.name)) throw DE(`the row takes ${t.name} twice`);
      row.inputs.set(t.name, { kind: 'q', dim });
    }
  }
  const kinds = ['is', 'cases', 'table'].filter((k) => Object.hasOwn(r, k));
  if (kinds.length !== 1) throw DE('the row has not exactly one of is, cases and table');
  row.kind = kinds[0];
  // deck.md: a row that gives a name is a table, and takes quantities and no key.
  if (gnames) {
    if (row.kind !== 'table') throw DE(`the row gives a name with ${row.kind}, and only a table gives a name`);
    for (const [nm, inp] of row.inputs) if (inp.kind === 'k') throw DE(`the row gives a name and takes the key ${nm}`);
  }
  const sc = {
    name: (nm) => {
      const inp = row.inputs.get(nm);
      if (!inp) throw DE(`${short(nm)} is not an input of the row`);
      if (inp.kind !== 'q') throw DE(`the key ${nm} is read outside a table`);
      return { dim: inp.dim, depth: 1 };
    },
  };
  if (row.kind !== 'table') {
    for (const inp of row.inputs.values()) if (inp.kind === 'k') throw DE('a row that is not a table takes a key');
  }
  if (row.kind === 'is') {
    const res = checkExpr(r.is, sc);
    if (!deq(res.dim, gdim)) throw DE('the expression does not give the row\'s dimension');
    row.is = r.is;
  } else if (row.kind === 'cases') {
    if (!Array.isArray(r.cases) || r.cases.length === 0) throw DE('cases is not a list of cases');
    row.cases = r.cases.map((cs, i) => {
      checkKeys(cs, ['when', 'is'], ['is'], `case ${i + 1}`);
      if (!Object.hasOwn(cs, 'when') && i !== r.cases.length - 1) throw DE(`case ${i + 1} has no when and is not the last`);
      if (Object.hasOwn(cs, 'when')) {
        if (checkRowCond(cs.when, sc) > MAX_EXPR_DEPTH) throw DE('a condition nests more than 1,024 deep');
      }
      const res = checkExpr(cs.is, sc);
      if (!deq(res.dim, gdim)) throw DE(`case ${i + 1} does not give the row's dimension`);
      return { when: Object.hasOwn(cs, 'when') ? cs.when : undefined, is: cs.is };
    });
  } else {
    row.table = loadTable(r.table, row);
  }
  if (Object.hasOwn(r, 'jumps')) {
    if (!Array.isArray(r.jumps)) throw DE('jumps is not a list');
    // deck.md, A row: "A jump has `cases` and `why`. `cases` is a list of whole numbers, each one
    // of the row's cases counted from 1, in which exactly two different numbers stand".
    const nCases = row.kind === 'cases' ? BigInt(row.cases.length) : 0n;
    for (const j of r.jumps) {
      checkKeys(j, ['cases', 'why'], ['cases'], 'a jump');
      if (!Array.isArray(j.cases) || !j.cases.every((x) => typeof x === 'bigint')) throw DE('a jump has no list of case numbers');
      for (const x of j.cases) if (x < 1n || x > nCases) throw DE(`a jump names case ${x}, and the row has ${nCases === 0n ? 'no cases' : `cases 1 to ${nCases}`}`);
      const distinct = new Set(j.cases.map(String)).size;
      if (distinct !== 2) throw DE(`a jump names ${distinct} different cases, and it names exactly two`);
      needFullText(j, 'why', 'a jump');
    }
  }
  // The orders of the pick a row with cases is written as: every comparison of its conditions.
  row.orders = 0;
  if (row.kind === 'cases') for (const cs of row.cases) if (cs.when !== undefined) row.orders += condOrders(cs.when);
  // format.md, How the kernel writes a table: "An equation is held to it whether or not a rule
  // applies it: the kernel writes every equation once when it reads its row." So an equation whose
  // conditions hold more than 1,024 orders refuses its row, and the deck with it, here and not
  // where a rule applies it. One case that holds otherwise, standing first, is no pick and has no
  // order. A table is still counted where a rule applies it (AMBIGUITIES.md, O3).
  if (row.orders > MAX_ORDERS) throw DE(`the cases of the equation hold ${row.orders} orders, more than 1,024 for one pick, whether or not a rule applies it`);
  return row;
}
function condOrders(c) {
  if (c[0] === 'and' || c[0] === 'or' || c[0] === 'not') {
    let n = 0;
    for (let i = 1; i < c.length; i++) n += condOrders(c[i]);
    return n;
  }
  return 1;
}

// Depth of a row's expression when each input stands for an expression of the given depth.
function exprDepth(e, leaf) {
  if (isStr(e)) return e === 'pi' || looksNumeric(e) ? 1 : leaf(e);
  if (e[0] === 'q') return 2;
  let m = 1;
  for (let i = 1; i < e.length; i++) {
    const a = e[i];
    m = Math.max(m, isStr(a) && e[0] === 'pow' && i === 2 && looksNumeric(a) ? 1 : exprDepth(a, leaf));
  }
  return 1 + m;
}
function condDepth(c, leaf) {
  if (c[0] === 'and' || c[0] === 'or' || c[0] === 'not') {
    let m = 0;
    for (let i = 1; i < c.length; i++) m = Math.max(m, condDepth(c[i], leaf));
    return 1 + m;
  }
  return 1 + Math.max(exprDepth(c[1], leaf), exprDepth(c[2], leaf));
}
function rowDepth(row, bd) {
  const leaf = (nm) => bd.get(nm) ?? 1;
  if (row.kind === 'is') return exprDepth(row.is, leaf);
  if (row.kind === 'cases') {
    let m = 1;
    for (const cs of row.cases) {
      m = Math.max(m, exprDepth(cs.is, leaf));
      if (cs.when !== undefined) m = Math.max(m, condDepth(cs.when, leaf));
    }
    return 1 + m;
  }
  let m = 1;
  for (const s of [row.table.down, row.table.across]) if (s) m = Math.max(m, 1 + leaf(s.by));
  return 1 + m;
}

function loadType(t, seenTypes) {
  // deck.md: a type has `type`, `what`, a text that may be empty, and `fields`, and may have
  // `loads` and `needs`.
  checkKeys(t, ['type', 'what', 'fields', 'loads', 'needs'], ['type', 'what', 'fields'], 'the type');
  nameText(t.type, 'the type');
  if (seenTypes.has(t.type)) throw DE(`two types are named ${t.type}`);
  needText(t, 'what', 'the type');
  const T = { name: t.type, fields: [], fieldMap: new Map(), loads: new Map(), joins: [], asMap: new Map(), needs: [], needsJ: undefined };
  if (!Array.isArray(t.fields)) throw DE('fields is not a list');
  const flag = (f, k) => {
    if (Object.hasOwn(f, k) && typeof f[k] !== 'boolean') throw DE(`${k} of ${f.name} is not true or false`);
    return f[k] === true;
  };
  for (const f of t.fields) {
    // deck.md: a field has `name`, `what`, a text that is not empty, and one of dim, one_of and
    // type. A quantity may have optional, signed, whole, least and may_be; a key optional, signed
    // and chosen and no other of them; a field that joins parts `as` and none of them.
    checkKeys(f, ['name', 'what', 'dim', 'one_of', 'type', 'as', 'signed', 'chosen', 'whole', 'least', 'optional', 'may_be'], ['name', 'what'], 'a field');
    checkName(f.name, 'the field');
    checkNameBytes(f.name, 'the field');
    needFullText(f, 'what', `the field ${f.name}`);
    if (T.fieldMap.has(f.name)) throw DE(`two fields are named ${f.name}`);
    const kinds = ['dim', 'one_of', 'type'].filter((k) => Object.hasOwn(f, k));
    if (kinds.length !== 1) throw DE(`the field ${f.name} has not exactly one of dim, one_of and type`);
    let F;
    // deck.md, A deck: "So is a key where it does not belong: ... `chosen` on a field that is no
    // key", whatever it holds.
    if (kinds[0] !== 'one_of' && Object.hasOwn(f, 'chosen')) throw DE(`the field ${f.name} has chosen, and it is no key: chosen stands on a key and on no other field`);
    if (kinds[0] === 'dim') {
      if (Object.hasOwn(f, 'as')) throw DE(`the quantity ${f.name} has as`);
      const dim = parseDim(f.dim);
      if (!dim) throw DE(`the field ${f.name} has the dimension ${short(f.dim)}, which is not one`);
      const signed = flag(f, 'signed'), whole = flag(f, 'whole'), optional = flag(f, 'optional');
      if (optional && signed) throw DE(`the field ${f.name} is both optional and signed`);
      // deck.md, A type: "A count is a plain number, so its `dim` is `dimensionless`, and a `whole`
      // field of any other dimension is refused." Compared by the exponents, as every dimension is.
      if (whole && !deq(dim, DL)) throw DE(`the field ${f.name} is whole, and a count is dimensionless, not ${short(f.dim)}`);
      let mayBe = null;
      if (Object.hasOwn(f, 'may_be')) {
        if (f.may_be !== 'zero' && f.may_be !== 'negative') throw DE(`may_be of ${f.name} is ${short(f.may_be)}, and it is "zero" or "negative"`);
        mayBe = f.may_be;
      }
      let least = null;
      if (Object.hasOwn(f, 'least')) {
        least = quantityOf(f.least, dim);
        if (!least) throw DE(`least of ${f.name} is not a quantity of its dimension`);
        // deck.md, "A quantity at or under zero": a `least` beside `may_be: zero` is refused, and
        // beside `may_be: negative` one at zero or above is.
        if (mayBe === 'zero') throw DE(`${f.name} says may_be zero and has a least: the floor is zero`);
        if (mayBe === 'negative' && least.n >= 0n) throw DE(`${f.name} says may_be negative and has a least at zero or above`);
      }
      F = { name: f.name, kind: 'q', dimName: f.dim, dim, signed, whole, least, optional, mayBe };
    } else if (kinds[0] === 'one_of') {
      for (const k of ['whole', 'least', 'may_be', 'as']) if (Object.hasOwn(f, k)) throw DE(`the key ${f.name} has ${k}`);
      if (!Array.isArray(f.one_of) || f.one_of.length === 0 || !f.one_of.every(isStr) || new Set(f.one_of).size !== f.one_of.length) throw DE(`the key ${f.name} has no list of distinct names`);
      // deck.md, A key the designer chooses: "A key is the card's or the designer's: one of the
      // two, and not both. A key with no `chosen` is the card's, with `"signed": true` or with no
      // `signed` at all. A key with `chosen` is the designer's, and `"signed": false` beside it
      // says the same again. A deck is refused for a key that has `"signed": false` and no
      // `chosen`, for a key that has `chosen` beside `"signed": true`, and for a key whose `chosen`
      // is no text or holds none of those 52 letters, as `""`, `"1 2 3."`, `5` and `null`. The
      // refusal names the field, and says the same for each of the three." A `chosen` that is
      // there is one, `null` too: an `unless` of `null` is read as none, and that is said of the
      // `unless` alone (AMBIGUITIES.md, T1).
      const saysSigned = Object.hasOwn(f, 'signed');
      const signedFlag = flag(f, 'signed'), optional = flag(f, 'optional');
      const chosen = Object.hasOwn(f, 'chosen');
      const KEY_OWNER = `field ${f.name}: a key is the card's, which \`signed\` may say, or the designer's, which \`chosen\` says with why, in words: one of the two, and not both`;
      if (chosen && !hasLetter(f.chosen)) throw DE(KEY_OWNER);
      if (chosen && signedFlag) throw DE(KEY_OWNER);
      if (!chosen && saysSigned && !signedFlag) throw DE(KEY_OWNER);
      // "A key is signed unless it says `chosen`, so an optional key says `chosen`", and "A field
      // is not both `optional` and `signed`".
      const signed = !chosen;
      if (optional && signed) throw DE(`the field ${f.name} is both optional and signed: a key with no chosen is signed, so an optional key says chosen`);
      // deck.md: a key that is optional has no name `unstated`.
      if (optional && f.one_of.includes('unstated')) throw DE(`the optional key ${f.name} has the name unstated`);
      F = { name: f.name, kind: 'k', names: f.one_of.slice(), signed, optional, chosen };
    } else {
      for (const k of ['signed', 'chosen', 'whole', 'least', 'optional', 'may_be']) if (Object.hasOwn(f, k)) throw DE(`the field ${f.name} that joins parts has ${k}`);
      if (!isStr(f.type)) throw DE(`the field ${f.name} names no type`);
      // deck.md, The grid: a field with no `as` joins one part, under the field's own name.
      let as = [f.name];
      if (Object.hasOwn(f, 'as')) {
        if (!Array.isArray(f.as) || f.as.length === 0) throw DE(`as of ${f.name} is not a list of names`);
        as = f.as;
      }
      for (const a of as) {
        checkName(a, 'a joined part');
        checkNameBytes(a, 'a joined part');
        if (T.asMap.has(a)) throw DE(`two joined parts are called ${a}`);
        T.asMap.set(a, { field: f.name, type: f.type });
      }
      F = { name: f.name, kind: 'j', type: f.type, as: as.slice() };
      T.joins.push(F);
    }
    T.fields.push(F);
    T.fieldMap.set(f.name, F);
  }
  if (Object.hasOwn(t, 'loads')) {
    if (!Array.isArray(t.loads)) throw DE('loads is not a list');
    for (const l of t.loads) {
      // deck.md: a load has a name, a dim, `what` it is, a text that is not empty, a least, and
      // `may_be`, which on a load is "negative" or left out.
      checkKeys(l, ['name', 'dim', 'what', 'least', 'may_be'], ['name', 'dim', 'what'], 'a load');
      checkName(l.name, 'the load');
      checkNameBytes(l.name, 'the load');
      needFullText(l, 'what', `the load ${l.name}`);
      if (T.loads.has(l.name)) throw DE(`two loads are named ${l.name}`);
      const dim = parseDim(l.dim);
      if (!dim) throw DE(`the load ${l.name} has the dimension ${short(l.dim)}, which is not one`);
      let mayBe = null;
      if (Object.hasOwn(l, 'may_be')) {
        if (l.may_be !== 'negative') throw DE(`may_be of the load ${l.name} is ${short(l.may_be)}, and on a load it is "negative"`);
        mayBe = 'negative';
      }
      let least = null;
      if (Object.hasOwn(l, 'least')) {
        least = quantityOf(l.least, dim);
        if (!least) throw DE(`least of the load ${l.name} is not a quantity of its dimension`);
      }
      T.loads.set(l.name, { name: l.name, dimName: l.dim, dim, least, mayBe });
    }
  }
  if (Object.hasOwn(t, 'needs')) {
    // deck.md, "What a type needs": a list with at least one item. Its items are read once every
    // type is known (checkNeeds), since a need may name a field of a part the type joins.
    if (!Array.isArray(t.needs) || t.needs.length === 0) throw DE('needs is not a list with at least one item');
    T.needsJ = t.needs;
  }
  return T;
}

// deck.md, "What a type needs". A need has `le` or `lt`, never both, and `why`, a text that is not
// empty. A side is a quantity field of the type, `AS.FIELD` of a part it joins, a number, a `q`,
// add, mul, sub, neg, or div by a field that is more than zero or a constant that is not zero. A
// need names at least one field and each field once over both sides; both sides have one dimension.
function checkNeeds(T, types) {
  T.needs = T.needsJ.map((n, k) => {
    const what = `need ${k + 1}`;
    checkKeys(n, ['le', 'lt', 'why'], ['why'], what);
    needFullText(n, 'why', what);
    if (Object.hasOwn(n, 'le') === Object.hasOwn(n, 'lt')) throw DE(`${what} has not exactly one of le and lt`);
    const op = Object.hasOwn(n, 'le') ? 'le' : 'lt';
    const sides = n[op];
    if (!Array.isArray(sides) || sides.length !== 2) throw DE(`${what}: ${op} is not two sides`);
    const named = [];
    const field = (s) => {
      const f = T.fieldMap.get(s);
      if (f) return f.kind === 'q' ? { f, ref: s } : null;
      const dot = s.indexOf('.');
      if (dot <= 0) return null;
      const j = T.asMap.get(s.slice(0, dot));
      const f2 = j && types.get(j.type)?.fieldMap.get(s.slice(dot + 1));
      return f2 && f2.kind === 'q' ? { f: f2, ref: s } : null;
    };
    const side = (e) => {
      if (isStr(e)) {
        if (looksNumeric(e)) {
          const v = parseNumberAlone(e);
          if (!v) throw DE(`${what}: ${short(e)} is not a number`);
          return { dim: DL };
        }
        const fd = field(e);
        if (!fd) throw DE(`${what}: ${short(e)} is no quantity field of ${T.name} or of a part it joins`);
        named.push(e);
        return { dim: fd.f.dim };
      }
      if (!Array.isArray(e) || e.length === 0 || !isStr(e[0])) throw DE(`${what}: ${short(e)} is not a side of a need`);
      const args = e.slice(1);
      switch (e[0]) {
        case 'q': {
          if (args.length !== 2 || !isStr(args[0]) || !isStr(args[1])) throw DE(`${what}: ${short(e)} is not a constant with a unit`);
          const v = qValue(e);
          if (!v) throw DE(`${what}: ${short(e)} is not a value with its unit`);
          return { dim: v.dim };
        }
        case 'add': case 'mul': {
          if (args.length < 1) throw DE(`${what}: ${e[0]} has no argument`);
          const rs = args.map(side);
          if (e[0] === 'mul') return { dim: rs.reduce((d, r) => dmul(d, r.dim), DL) };
          for (const r of rs) if (!deq(r.dim, rs[0].dim)) throw DE(`${what}: the terms of add are of different dimensions`);
          return { dim: rs[0].dim };
        }
        case 'sub': {
          if (args.length !== 2) throw DE(`${what}: sub takes two arguments`);
          const a = side(args[0]), b = side(args[1]);
          if (!deq(a.dim, b.dim)) throw DE(`${what}: the two sides of sub are of different dimensions`);
          return { dim: a.dim };
        }
        case 'neg':
          if (args.length !== 1) throw DE(`${what}: neg takes one argument`);
          return side(args[0]);
        case 'div': {
          if (args.length !== 2) throw DE(`${what}: div takes two arguments`);
          const a = side(args[0]);
          const d = args[1];
          let bd;
          if (isStr(d) && !looksNumeric(d)) {
            const fd = field(d);
            if (!fd) throw DE(`${what}: ${short(d)} is no quantity field of ${T.name} or of a part it joins`);
            if (fd.f.mayBe) throw DE(`${what} divides by ${d}, which may be zero`);
            named.push(d);
            bd = fd.f.dim;
          } else if (isStr(d) || (Array.isArray(d) && d[0] === 'q')) {
            const v = isStr(d) ? parseNumberAlone(d) : (d.length === 3 && isStr(d[1]) && isStr(d[2]) ? qValue(d) : null);
            if (!v) throw DE(`${what}: ${short(d)} is not a number or a constant`);
            const q = isStr(d) ? v : v.v;
            if (q.n === 0n) throw DE(`${what} divides by zero`);
            bd = isStr(d) ? DL : v.dim;
          } else throw DE(`${what} divides by ${short(d)}, which is neither a field nor a constant`);
          return { dim: ddiv(a.dim, bd) };
        }
        default:
          throw DE(`${what}: ${short(e[0])} is not in a need: a need has no root, logarithm, exponential, cosine, power, least, greatest, absolute value, pi, load, row, case or key`);
      }
    };
    const L = side(sides[0]), Rr = side(sides[1]);
    if (!deq(L.dim, Rr.dim)) throw DE(`${what}: the two sides are of different dimensions`);
    if (!named.length) throw DE(`${what} names no field`);
    if (new Set(named).size !== named.length) throw DE(`${what} names a field more than once`);
    return { op, sides, why: n.why, fields: named };
  });
}

// A key field of a type, by FIELD or AS.FIELD: {names, signed, own|joined}.
function keyField(s, T, types) {
  if (!isStr(s)) return null;
  const f = T.fieldMap.get(s);
  if (f) return f.kind === 'k' ? { names: f.names, signed: f.signed, own: s } : null;
  const dot = s.indexOf('.');
  if (dot <= 0) return null;
  const j = T.asMap.get(s.slice(0, dot));
  if (!j) return null;
  const f2 = types.get(j.type)?.fieldMap.get(s.slice(dot + 1));
  return f2 && f2.kind === 'k' ? { names: f2.names, signed: f2.signed, joined: s } : null;
}

function addRead(reads, kf) {
  if (kf.own) reads.own.add(kf.own);
  else reads.joined.add(kf.joined);
}

// A condition on a part (deck.md, The grid): `["is", FIELD, NAME]` on a key of the type or
// `PART.FIELD` of a part it joins, and `and`, `or` and `not` of these. `loaded` is gone and is
// refused wherever it stands, whatever follows the word.
//
// `whenOf` is given for the `when` of a rule and the `when` of a line's `unless`, as the words
// that say whose it is, and left out for what a rule `requires`. deck.md, The grid: "A `when`
// reads only keys that the card states: keys that do not say `chosen` ... So each `is` of a
// `when` names a key that only the card states ..., of the type itself or of a part it joins, and
// a deck that names a chosen key there is refused when it is read." and "What a rule `requires`
// is the check itself, and it may name any key, the card's or a chosen one" (AMBIGUITIES.md, Q1
// to Q3). A key's `signed` here is that it does not say `chosen` (loadType). The words of the
// refusal are the page's: "its `when` reads surface, which the design may state: a `when` reads
// only a key the card signs".
function checkPartCond(c, T, types, reads, whenOf) {
  if (!Array.isArray(c) || c.length === 0 || !isStr(c[0])) throw DE(`${short(c)} is not a condition on a part`);
  switch (c[0]) {
    case 'is': {
      if (c.length !== 3) throw DE('is takes a field and a name');
      const kf = keyField(c[1], T, types);
      if (!kf) throw DE(`${short(c[1])} is not a key field of ${T.name} or of a part it joins`);
      if (whenOf !== undefined && !kf.signed) throw DE(`${whenOf} reads ${c[1]}, which the design may state: a \`when\` reads only a key the card signs`);
      if (!isStr(c[2]) || !kf.names.includes(c[2])) throw DE(`${short(c[2])} is not a name of ${c[1]}`);
      addRead(reads, kf);
      return;
    }
    case 'loaded':
      throw DE('loaded is no condition: a condition is over keys, which are the same under every load case');
    case 'and': case 'or':
      if (c.length < 2) throw DE(`${c[0]} has no member`);
      for (const x of c.slice(1)) checkPartCond(x, T, types, reads, whenOf);
      return;
    case 'not':
      if (c.length !== 2) throw DE('not takes one condition');
      checkPartCond(c[1], T, types, reads, whenOf);
      return;
    default:
      throw DE(`${short(c[0])} is not a condition on a part`);
  }
}

const newReads = () => ({ own: new Set(), joined: new Set(), loads: new Set() });
function mergeReads(into, from) {
  for (const k of ['own', 'joined', 'loads']) for (const x of from[k]) into[k].add(x);
}

function loadRule(r, deck) {
  // deck.md, A rule: `says` is a text that is not empty; a rule has one of `le`, `lt` and
  // `requires`, and a rule with `requires` has no `let` and no `where`.
  checkKeys(r, ['id', 'type', 'mechanism', 'anchor', 'says', 'le', 'lt', 'requires', 'let', 'where', 'when'], ['id', 'type', 'mechanism', 'says'], 'the rule');
  if (!isStr(r.id) || r.id.length === 0) throw DE('the rule has no id');
  checkNameBytes(r.id, 'the id');
  checkAnchor(r.anchor, 'the rule');
  needFullText(r, 'says', 'the rule');
  const forms = ['le', 'lt', 'requires'].filter((k) => Object.hasOwn(r, k));
  if (forms.length !== 1) throw DE('a rule has one of le, an inequality, lt, a strict one, and requires, a condition over keys');
  const form = forms[0];
  if (form === 'requires') for (const k of ['let', 'where']) if (Object.hasOwn(r, k)) throw DE(`a rule with requires has no ${k}`);
  const T = deck.types.get(r.type);
  if (!T) throw DE(`the rule's type ${short(r.type)} is not a type of the deck`);
  const line = isStr(r.mechanism) ? deck.lineOf.get(`${r.type}\u0000${r.mechanism}`) : undefined;
  if (!line) throw DE(`the rule answers ${short(r.mechanism)}, which is no line of the grid for ${r.type}`);
  // deck.md, The grid: "No rule answers a line whose ground is `least`, `loads` or `with`, and a
  // deck with such a rule is refused, in the same words by both readers. The first refusal is for
  // a ground of `least` or of `loads`, and the second for `with`: `rule ID: the grid excuses
  // MECHANISM by what TYPE declares, and no rule answers such a line`, `rule ID: the grid says
  // MECHANISM is answered with other lines for TYPE`." A line with a `when` has rules.
  if (line.unless && line.unless.ground === 'with') throw DE(`the grid says ${r.mechanism} is answered with other lines for ${r.type}`);
  if (line.unless && line.unless.ground !== 'when') throw DE(`the grid excuses ${r.mechanism} by what ${r.type} declares, and no rule answers such a line`);
  const lets = Object.hasOwn(r, 'let') ? r.let : Object.create(null);
  if (!isObj(lets)) throw DE('let is not an object');
  for (const k of Object.keys(lets)) {
    checkName(k, 'the let name');
    checkNameBytes(k, 'the let name');
    if (T.fieldMap.has(k)) throw DE(`the let name ${k} is a field's name`);
  }
  const letMemo = new Map();
  const letBusy = new Set();
  // deck.md, The size of a deck: a rule that could write a pick of more than 1,024 orders for some
  // part is refused when the deck is read, and the deck with it. Every expression of the rule is
  // counted, each name of `let` among them (AMBIGUITIES.md, L2).
  const tooManyOrders = (n, what) => {
    if (n > MAX_ORDERS) throw DE(`the rule could write a pick of ${n} orders, more than 1,024: ${what}`);
  };
  const fieldOf = (e) => {
    const f = T.fieldMap.get(e);
    if (f) return f.kind === 'q' ? { f, own: e } : null;
    const dot = e.indexOf('.');
    if (dot <= 0) return null;
    const j = T.asMap.get(e.slice(0, dot));
    const f2 = j && deck.types.get(j.type)?.fieldMap.get(e.slice(dot + 1));
    return f2 && f2.kind === 'q' ? { f: f2, joined: e } : null;
  };
  // A row that gives a name, applied: each quantity it takes bound to an expression of its
  // dimension. It gives a name and no quantity.
  const nameRowApp = (v, reads) => {
    if (!Array.isArray(v) || v[0] !== 'row' || v.length !== 3 || !isStr(v[1]) || !isObj(v[2])) throw DE(`${short(v)} is not a row applied`);
    const row = deck.rows.get(v[1]);
    if (!row) throw DE(`${short(v[1])} is not a row of the deck`);
    if (!row.gives.names) throw DE(`the row ${row.id} gives a quantity and no name`);
    const b = v[2];
    for (const k of Object.keys(b)) if (!row.inputs.has(k)) throw DE(`the row ${row.id} has no input ${k}`);
    let depth = 0;
    for (const [nm, inp] of row.inputs) {
      if (!Object.hasOwn(b, nm)) throw DE(`the input ${nm} of ${row.id} is not bound`);
      const res = checkExpr(b[nm], scopeFor(reads));
      if (!deq(res.dim, inp.dim)) throw DE(`the input ${nm} of ${row.id} is bound to an expression of another dimension`);
      if (res.depth > depth) depth = res.depth;
    }
    return { row, depth: 2 + depth };
  };
  const scopeFor = (reads) => ({
    name: (e) => {
      if (Object.hasOwn(lets, e)) {
        const info = letInfo(e);
        mergeReads(reads, info.reads);
        return { dim: info.dim, depth: 1 + info.depth };
      }
      const fd = fieldOf(e);
      if (fd) { addRead(reads, fd); return { dim: fd.f.dim, depth: 1 }; }
      throw DE(`${short(e)} names no quantity field, field of a joined part or let`);
    },
    load: (args) => {
      if (args.length !== 1 || !isStr(args[0]) || !T.loads.has(args[0])) throw DE(`${short(args[0])} is not a load of ${T.name}`);
      reads.loads.add(args[0]);
      return { dim: T.loads.get(args[0]).dim, depth: 2 };
    },
    row: (args) => {
      if (args.length !== 2 || !isStr(args[0]) || !isObj(args[1])) throw DE('row takes an id and a binding of its inputs');
      const row = deck.rows.get(args[0]);
      if (!row) throw DE(`${short(args[0])} is not a row of the deck`);
      // deck.md, "A table that gives a name": a name is no quantity.
      if (row.gives.names) throw DE(`the row ${row.id} gives a name, which is no quantity`);
      const b = args[1];
      for (const k of Object.keys(b)) if (!row.inputs.has(k)) throw DE(`the row ${row.id} has no input ${k}`);
      const bd = new Map();
      for (const [nm, inp] of row.inputs) {
        if (!Object.hasOwn(b, nm)) throw DE(`the input ${nm} of ${row.id} is not bound`);
        const v = b[nm];
        if (inp.kind === 'q') {
          const res = checkExpr(v, scopeFor(reads));
          if (!deq(res.dim, inp.dim)) throw DE(`the input ${nm} of ${row.id} is bound to an expression of another dimension`);
          bd.set(nm, res.depth);
        } else {
          bd.set(nm, checkKeyBinding(v, inp, nm, row, reads));
        }
      }
      const depth = 1 + rowDepth(row, bd);
      if (depth > MAX_EXPR_DEPTH) throw DE('an expression nests more than 1,024 deep');
      // format.md, How the kernel writes a table: the orders of every pick the rule could write
      // for any part, counted when the deck is read. An equation with cases is one pick (one case
      // that holds otherwise, standing first, is none), and it is held to the orders when its row
      // is read, whether or not a rule applies it (loadRow). A table is the pick over its places
      // down and the pick of each line over its places across, every place counted, empty cells
      // too: a place of a quantity side has the orders of its band or listed value, a place of a
      // side whose key a row names those of that row's cell, and a side read by a key none.
      if (row.kind === 'table') {
        const sideOrders = (side) => {
          if (side.kind !== 'key') { let n = 0; for (let i = 0; i < side.count; i++) n += placeOrders(side, i); return n; }
          const v = b[side.by];
          if (!Array.isArray(v) || v[0] !== 'row') return 0;
          const N = deck.rows.get(v[1]);
          return nameCells(N).reduce((n, c) => n + nameCellOrders(N, c), 0);
        };
        tooManyOrders(sideOrders(row.table.down), `the places down of ${row.id}`);
        if (row.table.across) tooManyOrders(sideOrders(row.table.across), `the places across of ${row.id}`);
      }
      return { dim: row.gives.dim, depth };
    },
    // deck.md, A rule: `["case", ["row", ID, {...}], {NAME: ...}]`, a row that gives a name and
    // an expression for each name of its `one_of` and no other, all of one dimension.
    case: (args) => {
      if (args.length !== 2) throw DE('case takes a row that gives a name and a map of its names');
      const app = nameRowApp(args[0], reads);
      // A `case` is one pick, with one case for each cell of its row that holds a name.
      tooManyOrders(nameCells(app.row).reduce((n, c) => n + nameCellOrders(app.row, c), 0), `a case over ${app.row.id}`);
      const m = args[1];
      if (!isObj(m)) throw DE('the map of case is not an object');
      for (const k of Object.keys(m)) if (!app.row.gives.names.includes(k)) throw DE(`${short(k)} is not a name that ${app.row.id} gives`);
      let dim = null, depth = app.depth;
      for (const nm of app.row.gives.names) {
        if (!Object.hasOwn(m, nm)) throw DE(`the case has no expression for ${short(nm)}, which ${app.row.id} gives`);
        const res = checkExpr(m[nm], scopeFor(reads));
        if (dim && !deq(dim, res.dim)) throw DE('the expressions of a case are of different dimensions');
        dim = res.dim;
        if (res.depth > depth) depth = res.depth;
      }
      if (1 + depth > MAX_EXPR_DEPTH) throw DE('an expression nests more than 1,024 deep');
      return { dim, depth: 1 + depth };
    },
  });
  // deck.md, A rule: a key that a row takes is bound to a key field whose names are all names of
  // the row's key, to `["key", NAME]`, to `["by", FIELD, MAP]`, or to a row that gives a name,
  // every name of whose `one_of` is a name of the key. Returns the depth of the binding.
  const checkKeyBinding = (v, inp, nm, row, reads) => {
    if (isStr(v)) {
      const kf = keyField(v, T, deck.types);
      if (!kf) throw DE(`the key ${nm} of ${row.id} is bound to ${short(v)}, which is not a key field`);
      if (!kf.names.every((x) => inp.names.includes(x))) throw DE(`the key field ${v} has a name that the key ${nm} of ${row.id} has not`);
      addRead(reads, kf);
      return 1;
    }
    if (Array.isArray(v) && v[0] === 'key') {
      if (v.length !== 2 || !isStr(v[1]) || !inp.names.includes(v[1])) throw DE(`${short(v)} is not a name of the key ${nm} of ${row.id}`);
      return 1;
    }
    if (Array.isArray(v) && v[0] === 'by') {
      if (v.length !== 3) throw DE('by takes a field and a map');
      const kf = keyField(v[1], T, deck.types);
      if (!kf) throw DE(`${short(v[1])} is not a key field of ${T.name}`);
      if (!isObj(v[2])) throw DE('the map of by is not an object');
      for (const k of Object.keys(v[2])) {
        if (!kf.names.includes(k)) throw DE(`${short(k)} is not a name of ${v[1]}`);
        if (!isStr(v[2][k]) || !inp.names.includes(v[2][k])) throw DE(`${short(v[2][k])} is not a name of the key ${nm} of ${row.id}`);
      }
      // deck.md: the map of a `by` has one entry for each name of the field.
      for (const k of kf.names) if (!Object.hasOwn(v[2], k)) throw DE(`the map of by leaves out the name ${short(k)} of ${v[1]}`);
      addRead(reads, kf);
      return 1;
    }
    if (Array.isArray(v) && v[0] === 'row') {
      const app = nameRowApp(v, reads);
      for (const x of app.row.gives.names) if (!inp.names.includes(x)) throw DE(`${app.row.id} gives ${short(x)}, which is no name of the key ${nm} of ${row.id}`);
      return app.depth;
    }
    throw DE(`the key ${nm} of ${row.id} is bound to ${short(v)}`);
  };
  const letInfo = (nm) => {
    const m = letMemo.get(nm);
    if (m) return m;
    if (letBusy.has(nm)) throw DE(`the let name ${nm} reads itself`);
    letBusy.add(nm);
    const reads = newReads();
    const res = checkExpr(lets[nm], scopeFor(reads));
    if (1 + res.depth > MAX_EXPR_DEPTH) throw DE('an expression nests more than 1,024 deep');
    letBusy.delete(nm);
    const info = { dim: res.dim, depth: res.depth, reads };
    letMemo.set(nm, info);
    return info;
  };
  const ruleReads = newReads();
  const sc = scopeFor(ruleReads);
  for (const k of Object.keys(lets)) letInfo(k); // every let must hold together
  let sides;
  if (form !== 'requires') {
    sides = r[form];
    if (!Array.isArray(sides) || sides.length !== 2) throw DE(`${form} is not two expressions`);
    const a = checkExpr(sides[0], sc), b = checkExpr(sides[1], sc);
    if (!deq(a.dim, b.dim)) throw DE(`the two sides of ${form} are of different dimensions`);
  }
  // deck.md: a `where` is a list with at least one item; each item has `le` and `why`, a text that
  // may be empty, and no `lt`.
  let where, whereWhy;
  if (Object.hasOwn(r, 'where')) {
    if (!Array.isArray(r.where)) throw DE('where is not a list');
    if (r.where.length === 0) throw DE('where is there and has no item');
    // The tape that refutes the rule inside its `where` has a pick of one order for each item.
    tooManyOrders(r.where.length, 'the items of its where');
    whereWhy = r.where.map((w) => (isObj(w) ? w.why : undefined));
    where = r.where.map((w, i) => {
      checkKeys(w, ['le', 'why'], ['le', 'why'], `where ${i + 1}`);
      needText(w, 'why', `where ${i + 1}`);
      if (!Array.isArray(w.le) || w.le.length !== 2) throw DE(`where ${i + 1} is not two expressions`);
      const x = checkExpr(w.le[0], sc), y = checkExpr(w.le[1], sc);
      if (!deq(x.dim, y.dim)) throw DE(`the two sides of where ${i + 1} are of different dimensions`);
      return w.le;
    });
  }
  let when, requires;
  if (Object.hasOwn(r, 'when')) {
    // deck.md, A rule: `when` is "A condition on the part, as in the grid: on its own keys and on
    // the keys of the parts it joins, each of them `signed`."
    checkPartCond(r.when, T, deck.types, ruleReads, 'its `when`');
    when = r.when;
  }
  if (form === 'requires') {
    // deck.md, A rule that requires: "on a key of the part or of a part it joins, signed or not".
    checkPartCond(r.requires, T, deck.types, ruleReads);
    requires = r.requires;
  }
  if (form !== 'requires') checkMayBe({ sides, where, lets }, deck, T, fieldOf);
  const slash = r.id.lastIndexOf('/');
  // For the steps of the cells (format.md, Steps): the weight of the rule, the size of its
  // `when` and of its `requires`, the loads it reads and the fields it reads.
  let weight = 0;
  if (form !== 'requires') {
    const W = (e) => stepWeight(e, deck, false);
    for (const k of Object.keys(lets)) weight += W(lets[k]);
    weight += W(sides[0]) + W(sides[1]);
    if (where) for (const w of where) weight += W(w[0]) + W(w[1]);
  }
  return {
    id: r.id, tail: slash >= 0 ? r.id.slice(slash + 1) : r.id, type: r.type, mechanism: r.mechanism,
    form, sides, lets, where, whereWhy, when, requires, reads: ruleReads,
    whenKeys: condKeys(when), requiresKeys: condKeys(requires),
    weight, whenSize: condSize(when), requiresSize: condSize(requires),
    fieldsRead: ruleReads.own.size + ruleReads.joined.size,
  };
}

// format.md, rules.json, "A rule with no value where a field says it may be", and deck.md, "A
// quantity at or under zero". Once a rule's nodes are written, a `div` whose divisor stands for a
// field or a load that says `may_be`, a `sqrt` of one that says `"may_be": "negative"`, and an `ln`
// of either are refused. A node stands for a field when it is the field's input, a `pow` other
// than the 0th of a node that stands for it, or a `sqrt` of one; an even `pow` of a field that may
// be under zero stands for one that may be zero. A name of `let` and an input of a row are the
// node they are bound to. No other node stands for a field. The nodes are those the sides and the
// `where` read, as writeTape writes them, so a name of `let` that neither reads is not looked into
// (AMBIGUITIES.md, K4). A stand is null or {name, kind}, kind being "zero" or "negative".
function checkMayBe(rule, deck, T, fieldOf) {
  const refuse = (what, s) => {
    const may = s.kind === 'zero' ? 'may be zero' : 'may be under zero';
    throw DE(`the rule ${what} ${s.name}, which ${may}: at such a value the rule says nothing, so a part there could not be checked`);
  };
  const root = (s) => { if (s && s.kind === 'negative') refuse('takes the root of', s); return s; };
  const logOf = (s) => { if (s) refuse('takes the logarithm of', s); };
  const divBy = (s) => { if (s) refuse('divides by', s); };
  const powOf = (s, k) => (s && k % 2n === 0n && s.kind === 'negative' ? { name: s.name, kind: 'zero' } : s);
  const cond = (c, name) => {
    if (c[0] === 'and' || c[0] === 'or' || c[0] === 'not') { for (let i = 1; i < c.length; i++) cond(c[i], name); return; }
    walk(c[1], name); walk(c[2], name);
  };
  // A row that gives a name, applied: the quantities it binds are written for its conditions.
  const nameRow = (N, b, name) => { for (const [nm] of N.inputs) walk(b[nm], name); };
  const rowApp = (row, b, name) => {
    const memo = new Map();
    const qin = (nm) => { if (!memo.has(nm)) memo.set(nm, walk(b[nm], name)); return memo.get(nm); };
    if (row.kind === 'is') return walk(row.is, qin);
    if (row.kind === 'cases') {
      const vals = row.cases.map((cs) => { if (cs.when !== undefined) cond(cs.when, qin); return walk(cs.is, qin); });
      // One case that holds otherwise, standing first, is its own node and no pick.
      return row.cases[0].when === undefined ? vals[0] : null;
    }
    for (const side of [row.table.down, row.table.across]) {
      if (!side) continue;
      if (side.kind !== 'key') qin(side.by);
      else if (Array.isArray(b[side.by]) && b[side.by][0] === 'row') nameRow(deck.rows.get(b[side.by][1]), b[side.by][2], name);
    }
    return null;
  };
  const walk = (e, name) => {
    if (isStr(e)) return e === 'pi' || looksNumeric(e) ? null : name(e);
    const W = (a) => walk(a, name);
    switch (e[0]) {
      case 'q': return null;
      case 'load': { const L = T.loads.get(e[1]); return L.mayBe ? { name: `the load ${e[1]}`, kind: L.mayBe } : null; }
      case 'add': case 'mul': case 'min': case 'max': for (let i = 1; i < e.length; i++) W(e[i]); return null;
      case 'sub': W(e[1]); W(e[2]); return null;
      case 'neg': case 'abs': case 'exp': case 'cos': W(e[1]); return null;
      case 'sqrt': return root(W(e[1]));
      case 'ln': logOf(W(e[1])); return null;
      case 'div': W(e[1]); divBy(W(e[2])); return null;
      case 'pow': {
        const b = W(e[1]);
        const x = e[2];
        if (isStr(x) && looksNumeric(x)) {
          const n = parseNumberAlone(x);
          const twice = qmul(n, R(2n));
          if (twice.d === 1n) {
            // As writeTape writes it: a whole power is a pow, a half power a pow of a sqrt, and a
            // power of 0 or below 1 over the power.
            const tw = absB(twice.n);
            const node = tw % 2n === 0n ? (tw === 0n ? null : powOf(b, tw / 2n)) : powOf(root(b), tw);
            if (n.n <= 0n) { divBy(node); return null; }
            return node;
          }
          logOf(b); // any other power is exp of the exponent times ln
          return null;
        }
        W(x);
        logOf(b);
        return null;
      }
      case 'row': return rowApp(deck.rows.get(e[1]), e[2], name);
      case 'case': {
        nameRow(deck.rows.get(e[1][1]), e[1][2], name);
        for (const k of Object.keys(e[2])) W(e[2][k]);
        return null;
      }
    }
    throw new Error(`unexpected operator ${e[0]}`);
  };
  const letMemo = new Map();
  const ruleName = (nm) => {
    if (Object.hasOwn(rule.lets, nm)) {
      if (!letMemo.has(nm)) letMemo.set(nm, walk(rule.lets[nm], ruleName));
      return letMemo.get(nm);
    }
    const fd = fieldOf(nm);
    return fd.f.mayBe ? { name: nm, kind: fd.f.mayBe } : null;
  };
  walk(rule.sides[0], ruleName);
  walk(rule.sides[1], ruleName);
  if (rule.where) for (const w of rule.where) { walk(w[0], ruleName); walk(w[1], ruleName); }
}

// The keys a condition names, in the order it names them and each once.
function condKeys(c, out = []) {
  if (c === undefined) return out;
  if (c[0] === 'is') { if (!out.includes(c[1])) out.push(c[1]); return out; }
  for (let i = 1; i < c.length; i++) condKeys(c[i], out);
  return out;
}

// format.md, Steps: the size of a condition is 1 for an `is`, 1 more than the sizes of its
// members for an `and` and an `or`, and 1 more than its member for a `not`. None is 0.
function condSize(c) {
  if (c === undefined) return 0;
  if (c[0] === 'and' || c[0] === 'or' || c[0] === 'not') {
    let n = 1;
    for (let i = 1; i < c.length; i++) n += condSize(c[i]);
    return n;
  }
  return 1;
}

// format.md, Steps, the table of steps and their weights. A number, `pi`, a `q`, a field, a load
// and each later mention weigh 1 (a name of `let` too, AMBIGUITIES.md, J3); inside the body of a
// row, the name of an input is no step. What the page leaves open is taken as AMBIGUITIES.md, H8
// and J3 say. The expression has been checked.
function stepWeight(e, deck, inBody) {
  const W = (x) => stepWeight(x, deck, inBody);
  if (isStr(e)) return inBody && e !== 'pi' && !looksNumeric(e) ? 0 : 1;
  const op = e[0];
  switch (op) {
    case 'q': case 'load': return 1;
    case 'add': case 'mul': case 'min': case 'max': {
      let s = e.length;
      for (let i = 1; i < e.length; i++) s += W(e[i]);
      return s;
    }
    case 'neg': case 'abs': case 'sqrt': case 'exp': case 'ln': case 'cos': return 2 + W(e[1]);
    case 'div': return 3 + W(e[1]) + W(e[2]);
    case 'sub': return 5 + W(e[1]) + W(e[2]);
    case 'pow': {
      const x = e[2];
      if (isStr(x) && looksNumeric(x)) {
        const n = parseNumberAlone(x);
        const twice = qmul(n, R(2n));
        if (twice.d !== 1n) return 8 + W(e[1]); // a constant, a logarithm, a product, an exponential
        const half = twice.n % 2n !== 0n;
        // a whole power above 0 is one step of 2; of 0 or below a power, a one and a quotient
        // (2, 1, 3); a half power is a root of 2 first and then the whole power of twice it.
        const whole = (k) => (k > 0n ? 2 : 6);
        return (half ? 2 + whole(twice.n) : whole(n.n)) + W(e[1]);
      }
      return 7 + W(e[1]) + W(x); // a logarithm, a product, an exponential
    }
    case 'row': return rowAppWeight(deck.rows.get(e[1]), e[2], deck);
    case 'case': {
      const N = deck.rows.get(e[1][1]);
      let s = nameRowWeight(N, e[1][2], deck);
      const nm = e[2];
      for (const k of Object.keys(nm)) s += W(nm[k]);
      const cells = nameCells(N);
      let orders = 0;
      for (const c of cells) orders += nameCellOrders(N, c);
      return s + 1 + cells.length + 2 * orders;
    }
  }
  throw new Error(`unexpected operator ${op}`);
}
// A row that gives a quantity, applied: the steps of each quantity it binds, the steps of its
// body, and one step of weight 1 and 1 for each quantity it binds. A key that is bound is no step,
// but a row that gives the name it is bound to is applied, with its own steps.
function rowAppWeight(row, b, deck) {
  let s = 0, nq = 0, byEntries = 0;
  const named = { down: 0, across: 0 };
  for (const [nm, inp] of row.inputs) {
    if (inp.kind === 'q') { s += stepWeight(b[nm], deck, false); nq++; continue; }
    const v = b[nm];
    if (Array.isArray(v) && v[0] === 'by') byEntries += Object.keys(v[2]).length;
    if (Array.isArray(v) && v[0] === 'row') {
      const N = deck.rows.get(v[1]);
      s += nameRowWeight(N, v[2], deck);
      const n = nameCells(N).length;
      if (row.table.down.by === nm) named.down = n;
      if (row.table.across && row.table.across.by === nm) named.across = n;
    }
  }
  return s + 1 + nq + rowBodyWeight(row, byEntries, named);
}
// A row that gives a name, applied: the steps of each quantity it binds, and one step of weight 1
// for each end of a band and each listed value of its sides.
function nameRowWeight(N, b, deck) {
  let s = 0;
  for (const [nm] of N.inputs) s += stepWeight(b[nm], deck, false);
  for (const side of [N.table.down, N.table.across]) {
    if (!side) continue;
    if (side.kind === 'at') s += side.count;
    else for (const [, hi] of side.bands) s += hi === null ? 1 : 2;
  }
  return s;
}
function rowBodyWeight(row, byEntries, named) {
  const W = (x) => stepWeight(x, null, true); // a row reads no row and no load
  if (row.kind === 'is') return W(row.is);
  if (row.kind === 'cases') {
    const condW = (c) => {
      if (c[0] === 'and' || c[0] === 'or' || c[0] === 'not') { let s = 0; for (let i = 1; i < c.length; i++) s += condW(c[i]); return s; }
      return W(c[1]) + W(c[2]);
    };
    let s = 0;
    for (const cs of row.cases) s += W(cs.is) + (cs.when === undefined ? 0 : condW(cs.when));
    // One case that holds otherwise is no pick.
    if (row.cases.length === 1 && row.cases[0].when === undefined) return s;
    return s + 1 + row.cases.length + 2 * row.orders;
  }
  // A table weighs 1, 1 for each place down, 1 for each cell and 1 for each entry of a `by` that
  // reads it. A table with a key that a row names goes through the product of the places it goes
  // through down and across in place of its cells, and 1 more for each cell of that row that holds
  // a name (AMBIGUITIES.md, J4).
  const T = row.table;
  const pd = named.down || T.down.count;
  const pa = T.across ? named.across || T.across.count : 1;
  return 1 + T.down.count + pd * pa + named.down + named.across + byEntries;
}

// deck.md, "A rule that requires": the reader tries each `requires`, in the order of the deck,
// at every combination of the names of the keys that it and its `when` name, while a rule has at
// most 4,096 combinations and the cost of the rules tried, combinations times the sizes of the
// `requires` and the `when`, is at most 1,000,000. A rule past either is read untried.
const REQ_COMBOS = 4096;
const REQ_COST = 1_000_000;
function tryRequires(deck) {
  let spent = 0;
  for (const rule of deck.rules) {
    if (rule.form !== 'requires') continue;
    const T = deck.types.get(rule.type);
    const keys = condKeys(rule.when, condKeys(rule.requires).slice());
    const names = keys.map((k) => keyField(k, T, deck.types).names);
    let combos = 1;
    for (const n of names) { combos *= n.length; if (combos > REQ_COMBOS) break; }
    if (combos > REQ_COMBOS) continue;
    const cost = combos * (rule.requiresSize + rule.whenSize);
    if (spent + cost > REQ_COST) continue;
    spent += cost;
    const at = new Array(keys.length).fill(0);
    const val = new Map();
    const holds = (c) => {
      switch (c[0]) {
        case 'is': return val.get(c[1]) === c[2];
        case 'and': return c.slice(1).every(holds);
        case 'or': return c.slice(1).some(holds);
        case 'not': return !holds(c[1]);
      }
      return false;
    };
    let answers = 0, met = 0;
    for (let n = 0; n < combos; n++) {
      let x = n;
      for (let i = 0; i < keys.length; i++) { at[i] = x % names[i].length; x = Math.floor(x / names[i].length); val.set(keys[i], names[i][at[i]]); }
      if (rule.when !== undefined && !holds(rule.when)) continue;
      answers++;
      if (holds(rule.requires)) met++;
    }
    if (answers === 0) throw DE(`the rule ${rule.id} answers no part: its when holds for no combination of its keys`);
    if (met === answers) throw DE(`the rule ${rule.id} requires what no part can break: it holds at every combination at which the rule answers`);
    if (met === 0) throw DE(`the rule ${rule.id} requires what no part can meet: it holds at no combination at which the rule answers`);
  }
}

const GROUNDS = ['when', 'least', 'loads', 'with'];
export function loadDeck(D, find) {
  // format.md, After a broken rule: a deck of rules "reads whole or not at all", and the item of
  // a finding of the whole file is the empty text. Where in the deck it is goes in the reason.
  const F = (item, why) => find('rules', '', item ? `${item}: ${why}` : why);
  const errs0 = [];
  const top = (fn, item) => {
    try { return fn(); } catch (e) { if (e instanceof DeckErr) { F(item, e.message); errs0.push(1); return undefined; } throw e; }
  };
  top(() => {
    // deck.md, A deck: "A deck has every key of this table but `about`, which it may leave out:
    // a deck with no `name` is refused."
    checkKeys(D, ['format', 'name', 'about', 'rows', 'types', 'grid', 'rules'], ['format', 'name', 'rows', 'types', 'grid', 'rules'], 'the deck');
    needText(D, 'name', 'the deck');
    optText(D, 'about', 'the deck');
    for (const k of ['rows', 'types', 'grid', 'rules']) if (!Array.isArray(D[k])) throw DE(`${k} is not a list`);
  }, '');
  if (errs0.length) return null;
  const deck = { rows: new Map(), types: new Map(), grid: [], rules: [], lineOf: new Map() };
  D.rows.forEach((r, i) => {
    const item = `rows[${i}]${isObj(r) && isStr(r.id) ? ' ' + r.id : ''}`;
    const row = top(() => loadRow(r, deck.rows), item);
    if (row) deck.rows.set(row.id, row);
  });
  D.types.forEach((t, i) => {
    const item = `types[${i}]${isObj(t) && isStr(t.type) ? ' ' + t.type : ''}`;
    const T = top(() => loadType(t, deck.types), item);
    if (T) deck.types.set(T.name, T);
  });
  for (const T of deck.types.values()) {
    for (const j of T.joins) if (!deck.types.has(j.type)) top(() => { throw DE(`the field ${j.name} joins parts of ${short(j.type)}, which is not a type`); }, `types ${T.name}`);
  }
  if (errs0.length) return null;
  for (const T of deck.types.values()) if (T.needsJ !== undefined) top(() => checkNeeds(T, deck.types), `types ${T.name} needs`);
  const mechs = new Set();
  D.grid.forEach((g, i) => {
    const item = `grid[${i}]${isObj(g) && isStr(g.mechanism) ? ' ' + g.mechanism : ''}`;
    const line = top(() => {
      // deck.md: a line has `type`, `mechanism`, `anchor` and `what`, a text that may be empty.
      checkKeys(g, ['type', 'mechanism', 'what', 'anchor', 'unless'], ['type', 'mechanism', 'what'], 'the line');
      const T = deck.types.get(g.type);
      if (!T) throw DE(`the line's type ${short(g.type)} is not a type of the deck`);
      if (!isStr(g.mechanism) || g.mechanism.length === 0) throw DE('the line names no mechanism');
      checkNameBytes(g.mechanism, 'the mechanism');
      // deck.md: no mechanism is named `unread`, the name of the cells for the fields nothing reads.
      if (g.mechanism === 'unread') throw DE('a line of the grid is named unread');
      if (mechs.has(g.mechanism)) throw DE(`two lines are named ${g.mechanism}`);
      needText(g, 'what', 'the line');
      checkAnchor(g.anchor, 'the line');
      // deck.md, The grid: "An `unless` has `why` and exactly one of the four grounds, and no
      // other key. One with no ground, or with two, is refused"; "A line whose `unless` is `null`
      // is read as a line with none." The key that the page does not give is refused first, then
      // the `why`, then the count of the grounds, then the ground itself: a line has one finding,
      // of the first of these that it breaks (AMBIGUITIES.md, T1 and T2).
      let unless;
      if (Object.hasOwn(g, 'unless') && g.unless !== null) {
        const u = g.unless;
        checkKeys(u, ['why', ...GROUNDS], [], 'unless');
        needReason(u, 'why', 'unless');
        const grounds = GROUNDS.filter((k) => Object.hasOwn(u, k));
        if (grounds.length !== 1) throw DE('unless: it has one ground: `when` over keys the card states, `least` of the type, `loads` of the type, or `with` other lines');
        const ground = grounds[0];
        const reads = newReads();
        // format.md, Cells 2: the reason of a cell that is not applicable "is the `why` of the
        // `unless`, as the deck writes it, cut once, when the deck is read".
        unless = { ground, why: cutText(u.why), reads };
        if (ground === 'when') {
          // deck.md, The grid: the `when` of an `unless` reads only keys that the card states.
          checkPartCond(u.when, T, deck.types, reads, 'the `when` of its `unless`');
          unless.when = u.when;
        } else if (ground === 'least') {
          // deck.md, The grid, `least`: "A list of exactly two texts. `NAME` is a load of the
          // line's type, or else a field of it, and it is a quantity that has a `least` in the
          // type. `VALUE` is a value with its unit ..., of the dimension of `NAME`, and it is at
          // most the `least` that the type gives `NAME`." The tests are made in the order the
          // page lists the refusals, and the words after `unless: ` are the page's.
          // "A deck is refused when its `least` is no list of exactly two texts ... A `least`
          // that is no list, or that holds an item that is no text, is refused in the first of
          // these words, by both readers."
          const l = u.least;
          if (!Array.isArray(l) || l.length !== 2 || !l.every(isStr)) throw DE('unless: `least` is a load or a quantity of the type and a value: [NAME, VALUE]');
          const [nm, val] = l;
          const ofLoad = T.loads.has(nm);
          const q = T.loads.get(nm) ?? T.fieldMap.get(nm);
          if (!q) throw DE(`unless: ${nm} is no load and no field of ${T.name}`);
          // A key and a field that joins parts have no `least`; neither has a quantity or a load
          // that the type gives none.
          if (!q.least) throw DE(`unless: ${nm} has no \`least\` in ${T.name}`);
          const pv = parseValue(val);
          // "A `VALUE` that is a text and no value with a unit is refused by each reader in its
          // own words, after `grid MECHANISM: unless: least: `."
          if (!pv) throw DE(`unless: least: ${short(val)} is no value with its unit`);
          if (!deq(pv.dim, q.dim)) throw DE(`unless: the value of \`least\` is of another dimension than ${nm}`);
          const v = pv.v;
          if (qcmp(v, q.least) > 0) throw DE(`unless: ${T.name} does not say that ${nm} is at least ${trimWs(val)}`);
          unless.least = { name: nm, ofLoad };
        } else if (ground === 'loads') {
          // deck.md, The grid, `loads`: "A list of texts: every load of the line's type, each
          // once, and no other name. For a type that takes no load it is the empty list."
          const l = u.loads;
          // "Anything else is refused in the same words by both readers, a `loads` that is no
          // list of texts among them".
          if (!Array.isArray(l) || !l.every(isStr) || l.length !== T.loads.size || new Set(l).size !== l.length || !l.every((x) => T.loads.has(x))) throw DE(`unless: \`loads\` names each load of ${T.name} once and no other`);
        } else {
          // deck.md, The grid, `with`: "A list of at least one text, each once: the mechanisms of
          // other lines that the grid asks of the same type. A line does not name itself, and it
          // names no line that is itself answered `with` others". The lines it names "may stand
          // before it in the grid or after it", so they are looked up once the grid has read.
          const l = u.with;
          // "A `with` that is no list of texts is refused in the first of these words, by both
          // readers."
          if (!Array.isArray(l) || !l.every(isStr) || l.length === 0 || new Set(l).size !== l.length || l.includes(g.mechanism)) throw DE('unless: `with` names other lines of the grid, each once');
          unless.with = l.slice();
        }
      }
      return { type: g.type, mechanism: g.mechanism, unless, unlessSize: unless ? condSize(unless.when) : 0 };
    }, item);
    if (line) { deck.grid.push({ ...line, item }); mechs.add(line.mechanism); deck.lineOf.set(`${line.type}\u0000${line.mechanism}`, deck.grid[deck.grid.length - 1]); }
  });
  if (errs0.length) return null;
  // The lines that a `with` names, once every line has read: each is a line that the grid asks of
  // the same type, and none is itself answered with other lines, "so the answer is one step away".
  for (const line of deck.grid) {
    if (line.unless?.ground !== 'with') continue;
    top(() => {
      for (const m of line.unless.with) {
        const other = deck.lineOf.get(`${line.type}\u0000${m}`);
        if (!other) throw DE(`unless: it is answered with ${m}, which the grid does not ask of ${line.type}`);
        if (other.unless?.ground === 'with') throw DE(`unless: it is answered with ${m}, which is itself answered with other lines`);
      }
    }, line.item);
  }
  if (errs0.length) return null;
  const ids = new Set();
  const tails = new Set();
  D.rules.forEach((r, i) => {
    const item = `rules[${i}]${isObj(r) && isStr(r.id) ? ' ' + r.id : ''}`;
    const rule = top(() => {
      const x = loadRule(r, deck);
      if (ids.has(x.id)) throw DE(`two rules have the id ${x.id}`);
      // deck.md: two rules for one type and one mechanism have ids that differ after their last `/`.
      if (tails.has(`${x.type}\u0000${x.mechanism}\u0000${x.tail}`)) throw DE(`two rules for ${x.mechanism} have ids that end in ${short(x.tail)} after their last /`);
      return x;
    }, item);
    if (rule) { deck.rules.push(rule); ids.add(rule.id); tails.add(`${rule.type}\u0000${rule.mechanism}\u0000${rule.tail}`); }
  });
  if (errs0.length) return null;
  top(() => tryRequires(deck), 'rules');
  return errs0.length ? null : deck;
}

// ============================================================ the kernel

const STATES = ['proved', 'refuted', 'not_applicable', 'waived', 'open'];
// format.md, type rule 8, and deck.json: "For a design checked against a deck of rules the kernel
// holds its own copy of the size floor of `domains.size` and of the floors of `domains.input`, and
// a deck.json that gives others is a finding". These are the floors of decks/core.json,
// as type rule 8 lists them: "zero for a current, a voltage, a length, an area, a mass, an energy,
// a power, a time, a resistance and a dimensionless number, and -5463/20, absolute zero in degC,
// for a temperature, none strict". Eleven lines, kept by the exponents of the dimension.
export const CORE_INPUT_FLOORS = [
  ['current', '0'], ['voltage', '0'], ['length', '0'], ['area', '0'], ['mass', '0'], ['energy', '0'],
  ['power', '0'], ['time', '0'], ['resistance', '0'], ['dimensionless', '0'], ['temperature', '-5463/20'],
];
const coreInputFloors = () => new Map(CORE_INPUT_FLOORS.map(([name, min]) => [dstr(FILE_DIMS[name]), { min: parseFileNumber(min), strict: false, name }]));
// The twelfth line of that table (format.md, type rule 8): "`domains.size` of deck.json has the
// `min` and the `strict` that core.json gives it too: zero, and strict."
export const CORE_SIZE_FLOOR = { min: '0', strict: true };
// format.md, Cells 4, and deck.md, A rule that requires: the reason of a proved cell of a rule
// that requires.
const STATED_REASON = 'what the rule requires is stated: nothing is worked out';
// format.md, Cells 6: the reason of a proved cell whose tape has no input.
const NO_INPUT_REASON = 'the inequality reads no quantity of the part or of the card: nothing of the design is worked out';
const CASE_WHERE ='a load case is not named where: an entry that ends in /where is the range of a rule';
const nameCmp = (a, b) => {
  const x = [...a].map((c) => c.codePointAt(0)), y = [...b].map((c) => c.codePointAt(0));
  for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] - y[i];
  return x.length - y.length;
};

export function verifyTexts(texts, opts = {}) {
  const findings = [];
  // A finding of the shape rules, or of a deck that does not hold together, has the rule `shape`.
  // format.md, A text that is cut: "the item and the reason of a finding when the finding is kept".
  const find = (file, item, why, rule = 'shape') => { findings.push({ rule, file, item: isStr(item) ? cutText(item) : item, why: isStr(why) ? cutText(why) : why }); };
  const zeroCounts = () => Object.fromEntries(STATES.map((s) => [s, 0]));
  const ill = () => ({ out: { verdict: 'ILL-FORMED', findings, counts: zeroCounts(), waived: [], cells: [] }, code: 3 });
  const has = (o, k) => Object.hasOwn(o, k);

  // ---------------------------------------------------------------- shape
  // format.md, After a broken rule: "The kernel reads every file it is given and lists the shape
  // findings of each. A shape finding is of one item or of the whole file. An item is an item of
  // `inputs`, `claims`, `waivers`, `states`, `quantities`, `params`, `parts`, `constants` or
  // `cells`, or a key of `domains.input`: it is left out, and the rest of its file is read. ...
  // Anything else that does not read is of the whole file, and the finding's item is the empty
  // text: a file that is not JSON or has not its `format`, a key of the file itself that is
  // missing or holds a value of the wrong kind, `domains.size`, and a deck of rules, which reads
  // whole or not at all." `whole` holds the files that do not read as a whole.
  const whole = new Set();
  const W = (file, why) => { whole.add(file); find(file, '', why); };
  const docs = {};
  const formats = { card: 'petra-card/0', design: 'petra-design/0', deck: 'petra-deck/0', rules: 'petra-rules/0', proofs: 'petra-proofs/0' };
  for (const k of ['card', 'design', 'deck']) if (texts[k] === undefined) W(k, 'no file is given');
  for (const k of Object.keys(formats)) {
    if (texts[k] === undefined) continue;
    if (texts[k] === null) { W(k, 'the file cannot be read'); continue; }
    try {
      docs[k] = parseJson(texts[k]);
    } catch (e) {
      if (e instanceof JsonErr) { W(k, `not JSON the kernel reads: ${e.message}`); continue; }
      throw e;
    }
    if (!isObj(docs[k]) || docs[k].format !== formats[k]) { W(k, `format is not ${formats[k]}`); delete docs[k]; }
  }
  const { card: cardJ, design: designJ, deck: deckJ, rules: rulesJ, proofs: proofsJ } = docs;
  // `--rules` names a deck when the command line has it, whether or not its file reads.
  const rulesGiven = texts.rules !== undefined;

  // format.md, Keys: "A file, an item of one of its lists and a cell have every key this page
  // gives them. One that leaves a key out breaks the shape rule, as one that gives the key a value
  // of the wrong kind does." Each of the readers below gives the first thing that does not read,
  // in words, or null.
  const noText = (o, keys) => { const k = keys.find((x) => !isStr(o[x])); return k === undefined ? null : `${k} is not a text`; };
  // A range: `lo` and `hi`, each a number of the file (format.md, Numbers), with lo <= hi.
  const noRange = (o) => {
    for (const k of ['lo', 'hi']) if (!parseFileNumber(o[k])) return `${k} is ${short(o[k])}, which is not a number`;
    return qcmp(parseFileNumber(o.lo), parseFileNumber(o.hi)) > 0 ? 'lo is above hi' : null;
  };
  // The items of a list of a file. A list that is missing or is no list is of the whole file. An
  // item that reads is kept, as what `read` gives for it; one that does not is a shape finding
  // with the words `read` gives, and is left out.
  const items = (file, o, k, read) => {
    if (!Array.isArray(o[k])) { W(file, `${k} is not a list`); return []; }
    const out = [];
    o[k].forEach((x, i) => {
      const item = `${k}[${i}]`;
      const r = isObj(x) ? read(x, item) : 'not an object';
      if (isStr(r)) find(file, item, r);
      else out.push(r);
    });
    return out;
  };

  // card.json. format.md, Keys: it may leave out `states`, `tests` and `probability_claims`, and
  // no other key. `name` is a text, `environment` "a registry id, or null", `cases` the names of
  // the load cases. `tests` and `probability_claims` are held to no kind: "any value but the empty
  // list is a card that has one, and the finding is of Parts 8 and not of shape."
  let inputs = [], waivers = [], claims = [], states = [], cardCases = [];
  if (cardJ) {
    if (!isStr(cardJ.name)) W('card', 'name is not a text');
    if (!has(cardJ, 'environment') || (cardJ.environment !== null && !isStr(cardJ.environment))) W('card', 'environment is not a text or null');
    // A name of `cases` that is no text is no item of the lists above: it is of the whole file.
    if (!Array.isArray(cardJ.cases)) W('card', 'cases is not a list');
    else if (!cardJ.cases.every(isStr)) W('card', 'cases holds a name that is not a text');
    else cardCases = cardJ.cases;
    // An input: `name`, `dim`, `lo`, `hi` and `by`. It may leave out `case`, `on` and `field`.
    inputs = items('card', cardJ, 'inputs', (x, item) => {
      const e = noText(x, ['name', 'dim']) ?? noRange(x) ?? noText(x, ['by']);
      if (e) return e;
      for (const k of ['case', 'on', 'field']) if (has(x, k) && !isStr(x[k])) return `${k} is not a text`;
      return { item: `${item} ${x.name}`, name: x.name, dim: x.dim, lo: parseFileNumber(x.lo), hi: parseFileNumber(x.hi), by: x.by, case: x.case, on: x.on, field: x.field };
    });
    // A claim: `name`, `subject`, `quantity`, `rel`, `cases`, `bound`. The page gives the kind of
    // none of them, so a claim that has the six keys reads (AMBIGUITIES.md, P5).
    claims = items('card', cardJ, 'claims', (c) => {
      const k = ['name', 'subject', 'quantity', 'rel', 'cases', 'bound'].find((x) => !has(c, x));
      return k === undefined ? c : `a claim has no ${k}`;
    });
    // A waiver: `subject`, `mechanism`, `reason`, and `by`, which it may leave out: "It then
    // names nobody, which type rule 5 refuses."
    waivers = items('card', cardJ, 'waivers', (w, item) => {
      const e = noText(w, ['subject', 'mechanism', 'reason']);
      if (e) return e;
      if (has(w, 'by') && !isStr(w.by)) return 'by is not a text';
      return { item, subject: w.subject, mechanism: w.mechanism, by: w.by, reason: w.reason };
    });
    // format.md, card.json: an item of `states` has `name`, `by`, and exactly one of `key`, a
    // text, and `whole`, a whole number written as every number of the file is, and no other key.
    // "An item that breaks this is a shape finding and is left out." It may leave out `by`, as a
    // waiver may (Keys).
    if (has(cardJ, 'states')) states = items('card', cardJ, 'states', (s, item) => {
      const extra = Object.keys(s).find((k) => !['name', 'by', 'key', 'whole'].includes(k));
      if (extra !== undefined) return `an item of states has the key ${short(extra)}`;
      if (!isStr(s.name)) return 'name is not a text';
      if (has(s, 'by') && !isStr(s.by)) return 'by is not a text';
      if (has(s, 'key') === has(s, 'whole')) return 'an item of states has exactly one of key and whole';
      if (has(s, 'key')) return isStr(s.key) ? { item: `${item} ${s.name}`, name: s.name, by: s.by, key: s.key } : 'key is not a text';
      const w = parseFileNumber(s.whole);
      return w && w.d === 1n ? { item: `${item} ${s.name}`, name: s.name, by: s.by, whole: w } : `whole is ${short(s.whole)}, which is not a whole number`;
    });
  }

  // design.json. It may leave out `parts`, and no other key. A part is one item, "so a part with
  // one line that does not read is left out whole". Its name is within 64 bytes as printed,
  // "whether or not `--rules` names a deck". A line has its `field` and its `args`, and an
  // argument is one of four things: a number with its `dim`, `lo` and `hi`, a given, a word or a
  // text. Anything else, as the `{"other": KIND}` of the exporter, does not read.
  const readPart = (p, item) => {
    if (!isStr(p.name)) return 'name is not a text';
    const bytes = printedBytes(p.name);
    if (bytes > NAME_BYTES) return `the name of a part prints in at most ${NAME_BYTES} bytes, and this one in ${bytes}`;
    if (!isStr(p.type)) return 'type is not a text';
    if (!Array.isArray(p.lines)) return 'lines is not a list';
    const lines = [];
    for (let j = 0; j < p.lines.length; j++) {
      const l = p.lines[j], at = `line ${j + 1}`;
      if (!isObj(l)) return `${at} is not an object`;
      if (!isStr(l.field)) return `${at}: field is not a text`;
      if (!Array.isArray(l.args)) return `${at}: args is not a list`;
      const args = [];
      for (let k = 0; k < l.args.length; k++) {
        const a = l.args[k], aat = `${at}, argument ${k + 1}`;
        const kind = isObj(a) && Object.keys(a).length === 1 ? Object.keys(a)[0] : null;
        if (kind === 'number') {
          if (!isObj(a.number)) return `${aat}: the number is not an object`;
          const e = noText(a.number, ['dim']) ?? noRange(a.number);
          if (e) return `${aat}: ${e}`;
          args.push({ kind, dim: a.number.dim, lo: parseFileNumber(a.number.lo), hi: parseFileNumber(a.number.hi) });
        } else if (kind === 'given' || kind === 'word' || kind === 'text') {
          if (!isStr(a[kind])) return `${aat}: ${kind} is not a text`;
          args.push({ kind, value: a[kind] });
        } else return `${aat} is not a number, a given, a word or a text`;
      }
      lines.push({ field: l.field, args });
    }
    return { item: `${item} ${p.name}`, name: p.name, type: p.type, lines };
  };
  let quantities = [], params = [], partsR = [];
  const hasParts = !!designJ && has(designJ, 'parts');
  if (designJ) {
    if (!isStr(designJ.name)) W('design', 'name is not a text');
    if (!isStr(designJ.card)) W('design', 'card is not a text');
    // A quantity: `type`, `entity`, `line`, `field`, `role`, `dim`, `lo`, `hi`. A param: `name`,
    // `dim`, `lo`, `hi`.
    quantities = items('design', designJ, 'quantities', (x, item) => noText(x, ['type', 'entity', 'line', 'field', 'role', 'dim']) ?? noRange(x)
      ?? { item, role: x.role, lo: parseFileNumber(x.lo), entity: x.entity, line: x.line });
    params = items('design', designJ, 'params', (x) => noText(x, ['name', 'dim']) ?? noRange(x) ?? x);
    if (hasParts) partsR = items('design', designJ, 'parts', readPart);
  }

  // deck.json. It may leave out `rules`, and `about` wherever it stands. `domains.size` has `min`,
  // a number, and `strict`, true or false, and one that does not read is of the whole file. A key
  // of `domains.input` is an item: it names a dimension and has `min` and `strict`, and one that
  // does not read is left out, so its dimension has no floor of it. `about` is prose. Two keys of
  // one dimension give it one floor: the higher, and the strict one when both are at one height.
  // Floors are kept by the exponents. A constant has `label`, `lo` and `hi`.
  let sizeDomain = null;
  let inputDomains = new Map();
  if (deckJ) {
    const dom = deckJ.domains;
    if (!isObj(dom)) W('deck', 'domains is not an object');
    else {
      const s = dom.size;
      if (!isObj(s)) W('deck', 'domains.size is not an object');
      else if (!parseFileNumber(s.min)) W('deck', `domains.size: min is ${short(s.min)}, which is not a number`);
      else if (typeof s.strict !== 'boolean') W('deck', 'domains.size: strict is not true or false');
      else sizeDomain = { min: parseFileNumber(s.min), strict: s.strict };
      if (!isObj(dom.input)) W('deck', 'domains.input is not an object');
      else {
        for (const k of Object.keys(dom.input)) {
          if (k === 'about') continue;
          const item = `domains.input.${k}`;
          const dim = parseFileDim(k);
          if (!dim) { find('deck', item, `${short(k)} names no dimension`); continue; }
          const d = dom.input[k];
          if (!isObj(d)) { find('deck', item, 'the floor is not an object'); continue; }
          const dm = parseFileNumber(d.min);
          if (!dm) { find('deck', item, `min is ${short(d.min)}, which is not a number`); continue; }
          if (typeof d.strict !== 'boolean') { find('deck', item, 'strict is not true or false'); continue; }
          const key = dstr(dim), was = inputDomains.get(key);
          const c = was ? qcmp(dm, was.min) : 1;
          if (c > 0) inputDomains.set(key, { min: dm, strict: d.strict, name: k });
          else if (c === 0 && d.strict) was.strict = true;
        }
      }
    }
    items('deck', deckJ, 'constants', (c) => noText(c, ['label']) ?? noRange(c) ?? c);
  }
  // format.md, type rule 8: "With `--rules`, `domains.input` of deck.json gives each dimension the
  // floor that `petra/decks/core.json` gives it, and no other dimension a floor ... A floor is
  // compared by the exponents of its dimension, its `min` and its `strict`, so `m^1` and `length`
  // are one key. A deck.json that differs is a finding, and the kernel goes on with core.json's
  // floors in its place." The floors that deck.json gives are compared as it gives them once two
  // keys of one dimension are one floor (AMBIGUITIES.md, N2), and from here on `inputDomains` is
  // the kernel's own copy: type rule 4, the deck of rules, Parts 3 and the completions are held to
  // it. The finding is made with the type rules, below. Without `--rules` the floors are
  // deck.json's, as before.
  let floorsDiffer = null;
  if (rulesGiven) {
    const core = coreInputFloors();
    for (const [key, c] of core) {
      const d = inputDomains.get(key);
      if (!d) floorsDiffer = `it gives a ${c.name} no floor, and core.json gives it ${c.min}`;
      else if (qcmp(d.min, c.min) !== 0) floorsDiffer = `it gives a ${c.name} the floor ${d.min}, and core.json gives it ${c.min}`;
      else if (d.strict !== c.strict) floorsDiffer = `it gives a ${c.name} a strict floor, and no floor of core.json is strict`;
      if (floorsDiffer) break;
    }
    if (!floorsDiffer) for (const [key, d] of inputDomains) if (!core.has(key)) { floorsDiffer = `it gives the floor ${d.min} to ${short(d.name)}, a dimension that core.json gives none`; break; }
    inputDomains = core;
  }
  // format.md, type rule 8: "With `--rules`, `domains.size` of deck.json has the `min` and the
  // `strict` that core.json gives it too: zero, and strict. A deck.json that gives another is a
  // finding of its own, at `domains.size`, and the kernel goes on with core.json's size floor. So
  // with `--rules` every floor this document names, in type rules 3 and 4, in the deck of rules, in
  // Parts 3 and in a completion, is core.json's." The `min` and the `strict` alone are compared: an
  // `about` beside them is prose. A `domains.size` that does not read is of the whole file, and the
  // kernel stops before the type rules (After a broken rule). From here on `sizeDomain` is the
  // kernel's own with --rules, and type rule 3 is held to it. Without `--rules` it is deck.json's.
  let sizeDiffers = null;
  if (rulesGiven) {
    const core = { min: parseFileNumber(CORE_SIZE_FLOOR.min), strict: CORE_SIZE_FLOOR.strict };
    if (sizeDomain && qcmp(sizeDomain.min, core.min) !== 0) sizeDiffers = `it gives a size the floor ${sizeDomain.min}, and core.json gives it ${core.min}`;
    else if (sizeDomain && sizeDomain.strict !== core.strict) sizeDiffers = 'it gives a size a floor that is not strict, and the size floor of core.json is strict';
    sizeDomain = core;
  }

  // proofs.json. format.md, Keys: a cell has `subject`, `mechanism`, `entry` and `state`, and may
  // leave out `tape`, `partition`, `point`, `which`, `rule` and `completion`. "Without `--rules`,
  // a `not_applicable` or `open` cell has `why`. With `--rules` a cell is a hint, and `why` may be
  // left out of any." "A proofs.json that breaks a shape
  // rule in any hint, as a number written `01` or a hint with no `state`, is refused whole like
  // any file, and the verdict is ILL-FORMED with no cell." With `--rules` a cell is a hint, and
  // the kernel reads three more of its keys: `partition`, which is the text `leaf` or an object,
  // `point`, an object, and `completion`, an object whose `keys` and `loads` are lists. One that
  // gives such a key a value of another kind breaks the shape rule (Keys), and so does a number
  // that does not parse: the `at` of a split, a value of a point, the value of a load of four
  // items of a completion. Any other fault of their form settles nothing, or does not fit, and
  // breaks no shape rule (AMBIGUITIES.md, P6). The kernel does not read the `why`, the `rule`,
  // the `tape` or the `which` of a hint, and holds them to no kind.
  const hints = new Map();
  const hintKey = (s, m, e) => `${s}\u0000${m}\u0000${e}`;
  if (proofsJ) {
    items('proofs', proofsJ, 'cells', (c) => {
      const e = noText(c, ['subject', 'mechanism', 'entry', 'state']);
      if (e) return e;
      if (!STATES.includes(c.state)) return `${short(c.state)} is not a state`;
      if (!rulesGiven) {
        // "Without `--rules` a cell is what the kernel checks", whatever the design is: the page
        // asked the `why` of a design with no parts only, until it was changed with P15.
        if ((c.state === 'not_applicable' || c.state === 'open') && !isStr(c.why)) return `a cell that is ${c.state} says why, and why is not a text`;
        return c;
      }
      if (has(c, 'partition')) {
        if (!isStr(c.partition) && !isObj(c.partition)) return 'partition is not the text leaf or an object';
        let bad = null;
        const walk = (P) => {
          if (!isObj(P) || bad) return;
          if (has(P, 'at') && !parseFileNumber(P.at)) { bad = `the partition splits at ${short(P.at)}, which is not a number`; return; }
          walk(P.below);
          walk(P.above);
        };
        walk(c.partition);
        if (bad) return bad;
      }
      if (has(c, 'point')) {
        if (!isObj(c.point)) return 'point is not an object';
        for (const k of Object.keys(c.point)) if (!parseFileNumber(c.point[k])) return `the point gives ${short(k)} the value ${short(c.point[k])}, which is not a number`;
      }
      if (has(c, 'completion')) {
        const cp = c.completion;
        if (!isObj(cp)) return 'completion is not an object';
        for (const k of ['keys', 'loads']) if (has(cp, k) && !Array.isArray(cp[k])) return `completion: ${k} is not a list`;
        // A completion gives each load "a number in a string, as in a point" (item 9).
        for (const l of cp.loads ?? []) if (Array.isArray(l) && l.length === 4 && isStr(l[3]) && !parseFileNumber(l[3])) return `the completion gives ${short(l[1])} the value ${short(l[3])}, which is not a number`;
      }
      const key = hintKey(c.subject, c.mechanism, c.entry);
      if (!hints.has(key)) hints.set(key, []);
      hints.get(key).push(c);
      return c;
    });
  }

  // ---------------------------------------------------------------- the deck of rules
  // Read here, before the type rules, because type rules 3 and 4 ask which fields of the deck's
  // types say `may_be`. Its findings are those of the deck of rules: of the file `rules`, with the
  // empty item, since a deck reads whole or not at all. deck.md, "The size of a deck": a deck that
  // takes more than 1,000,000 steps to read is refused before a row is read.
  let deck = null, deckStepCount = 0;
  if (rulesJ) {
    deckStepCount = deckSteps(rulesJ);
    if (deckStepCount > DECK_STEPS) find('rules', '', `reading the deck takes ${deckStepCount} steps, more than 1,000,000`);
    else deck = loadDeck(rulesJ, find);
  }
  // format.md, The deck of rules: once the deck has read, no `least` of a field or a load is under
  // the floor its dimension has in `domains.input` of core.json (type rule 8: `inputDomains` is
  // the kernel's own copy with --rules), where that floor holds for it as type rule 4
  // holds an input: a floor under zero always, and one at zero or above unless the field or load
  // says `may_be: negative`. A deck that breaks it is refused as one that does not read is. "Under"
  // is taken strictly, whether or not the floor is strict (AMBIGUITIES.md, M1).
  if (deck) {
    let under = false;
    for (const T of deck.types.values()) {
      const fls = [...T.fields.filter((f) => f.kind === 'q').map((f) => ['field', f]), ...[...T.loads.values()].map((l) => ['load', l])];
      for (const [what, f] of fls) {
        if (!f.least) continue;
        const fl = inputDomains.get(dstr(f.dim));
        if (!fl || (f.mayBe === 'negative' && fl.min.n >= 0n)) continue;
        if (qcmp(f.least, fl.min) < 0) {
          find('rules', '', `${what} ${f.name}: its least, ${f.least} in SI units, is under ${fl.min}, the floor of a ${fl.name}, and no card states a value under it`);
          under = true;
        }
      }
    }
    if (under) deck = null;
  }
  // Shape: with --rules the names of the card and of the design print in at most 200 bytes,
  // "tested when the deck that `--rules` names holds together". A name past the limit is a text
  // that reads: the finding is at `name`, leaves nothing out and stops nothing (AMBIGUITIES.md, P7).
  const nameLimit = (file, item, s, limit, what) => {
    if (isStr(s) && printedBytes(s) > limit) { find(file, item, `${what} prints in at most ${limit} bytes, and this one in ${printedBytes(s)}`); return false; }
    return true;
  };
  // format.md, After a broken rule: "When card.json, design.json or deck.json does not read as a
  // whole, the kernel stops there, with the shape findings of all the files. Otherwise it applies
  // the type rules to what it read".
  if (whole.has('card') || whole.has('design') || whole.has('deck')) return ill();
  // The two names are tested past the stop: "They are found where the parts are read, with the
  // rules of Parts, and those go on", as the name of a load case is. Nothing stops between here
  // and Parts 1 to 8 when the deck of rules reads (AMBIGUITIES.md, P16).
  if (deck) {
    nameLimit('card', 'name', cardJ.name, LABEL_NAME_BYTES, 'the name of the card');
    nameLimit('design', 'name', designJ.name, LABEL_NAME_BYTES, 'the name of the design');
  }

  // The type of the first part of a name (type rules 3 and 4), when the deck holds together: "The
  // part is the first of that name in `parts`", of the parts that read (AMBIGUITIES.md, P11).
  const firstOfName = new Map();
  for (const p of partsR) if (!firstOfName.has(p.name)) firstOfName.set(p.name, p);
  const firstPartType = (name) => {
    if (!deck) return null;
    const p = firstOfName.get(name);
    return p ? deck.types.get(p.type) ?? null : null;
  };

  // ---------------------------------------------------------------- types
  // Type rule 1: "The design's `card` is the SHA-256 of the card file's bytes", written
  // `sha256:HEX` (format.md, design.json). The file read as JSON, so it is UTF-8 with no byte
  // order mark, and its text gives its bytes back.
  const cardHash = `sha256:${createHash('sha256').update(texts.card, 'utf8').digest('hex')}`;
  if (designJ.card !== cardHash) find('design', 'card', `is not the hash of the card file, ${cardHash}`, 'types.1');
  const allowedDesignKeys = ['format', 'name', 'card', 'quantities', 'params', 'parts'];
  for (const k of Object.keys(designJ)) if (!allowedDesignKeys.includes(k)) find('design', k, `the design has the key ${short(k)}`, 'types.2');
  // Type rule 8: "Rule 8 is applied before rules 3 and 4, which read the floors it settles, so its
  // findings are printed before theirs." With --rules, a deck.json whose `domains.input` is not the
  // floors of core.json is a finding. The kernel went on with core.json's floors in its place,
  // above: type rule 4, the `least`s of the deck of rules, Parts 3 and the completions are all
  // held to them. And a deck.json whose `domains.size` is not core.json's size floor is "a finding
  // of its own, at `domains.size`".
  if (rulesGiven && floorsDiffer) find('deck', 'domains.input', `with --rules the floors are those of core.json, which the kernel holds itself, and deck.json gives others: ${floorsDiffer}`, 'types.8');
  if (rulesGiven && sizeDiffers) find('deck', 'domains.size', `with --rules the size floor is that of core.json, which the kernel holds itself, and deck.json gives another: ${sizeDiffers}`, 'types.8');
  // Type rule 3, but for a quantity of a field that says `may_be`, which Parts 3 holds to the
  // field's own floor. With --rules the size floor is core.json's (type rule 8), whatever
  // deck.json gives.
  for (const q of quantities) {
    if (q.role === 'size') {
      const T = firstPartType(q.entity);
      const f = T ? T.fieldMap.get(q.line) : null;
      if (f && f.kind === 'q' && f.mayBe) continue;
      const c = qcmp(q.lo, sizeDomain.min);
      if (c < 0 || (c === 0 && sizeDomain.strict)) find('design', q.item, `a size is ${q.lo}, at or below the least a size may take`, 'types.3');
    }
  }
  // Type rule 4: every input's dim names a dimension, and its floor is found by the exponents. An
  // input for a field or a load that says `may_be: negative` is not held to a floor at zero or
  // above, and is held to one under zero.
  for (const x of inputs) {
    x.dimVec = parseFileDim(x.dim);
    if (!x.dimVec) { find('card', x.item, `${short(x.dim)} names no dimension`, 'types.4'); continue; }
    const d = inputDomains.get(dstr(x.dimVec));
    if (!d) continue;
    let negative = false;
    if (x.on !== undefined || x.field !== undefined || x.case !== undefined) {
      const T = x.on !== undefined ? firstPartType(x.on) : null;
      negative = !!(T && x.field !== undefined && T.loads.get(x.field)?.mayBe === 'negative');
    } else {
      const dot = x.name.lastIndexOf('.');
      const T = dot > 0 ? firstPartType(x.name.slice(0, dot)) : null;
      const f = T ? T.fieldMap.get(x.name.slice(dot + 1)) : null;
      negative = !!(f && f.kind === 'q' && f.mayBe === 'negative');
    }
    if (negative && d.min.n >= 0n) continue;
    const c = qcmp(x.lo, d.min);
    if (c < 0 || (c === 0 && d.strict)) find('card', x.item, `lo is ${x.lo}, below the floor of ${d.name}`, 'types.4');
  }
  // Type rule 5: every input, every waiver and every item of `states` names a `by` that is not
  // the empty text. A waiver or an item of `states` with no `by` "names nobody, which type rule 5
  // refuses" (Keys); an input with none did not read.
  for (const x of inputs) if (x.by.length === 0) find('card', x.item, 'the input names no by: nobody signed it', 'types.5');
  for (const w of waivers) if (w.by === undefined || w.by.length === 0) find('card', w.item, 'the waiver names no by', 'types.5');
  for (const s of states) if (s.by === undefined || s.by.length === 0) find('card', s.item, 'the statement names no by', 'types.5');
  // Types 6 and 7: parts come with --rules, and the marks of a file for a deck of rules come
  // with parts and --rules: an input with `on` or `field`, `tests`, `probability_claims` or
  // `states` in the card, `rules` in deck.json.
  if (hasParts && !rulesGiven) find('design', 'parts', 'a design with parts comes with --rules', 'types.6');
  if (!hasParts || !rulesGiven) {
    const why = !hasParts ? 'is a mark of a design checked against a deck of rules, and the design has no parts' : 'is a mark of a design checked against a deck of rules, and --rules names no deck';
    for (const x of inputs) if (x.on !== undefined || x.field !== undefined) find('card', x.item, `an input with on or field ${why}`, 'types.7');
    for (const k of ['tests', 'probability_claims', 'states']) if (has(cardJ, k)) find('card', k, `the key ${k} ${why}`, 'types.7');
    if (has(deckJ, 'rules')) find('deck', 'rules', `the key rules ${why}`, 'types.7');
  }

  // format.md, After a broken rule: "and then, when `--rules` names a deck of rules that reads,
  // Parts 1 to 8, whatever it has found by then. ... With a deck of rules that does not read, no
  // rule of Parts is applied."
  if (!rulesGiven) {
    if (findings.length) return ill();
    // `--rules` names no deck and no rule is broken (so the design has no parts: type rule 6).
    // format.md, The verdict: "Without `--rules` the cells are the list of proofs.json, which the
    // kernel takes as it comes. It checks the tape of each ... So nothing the kernel checks there
    // makes a PASS, and the verdict of such files is UNKNOWN at best." This kernel checks no tape
    // that a file carries (AMBIGUITIES.md, C8), so a list with a tape in it gets no verdict here.
    // A list with none is settled by Cells 3 to 5 alone: "`proved` or `refuted` with no tape is
    // open", "`waived` holds only when the card lists a waiver with the same `subject` and
    // `mechanism`. Otherwise it is open", and "`not_applicable` is taken as stated". No cell of it
    // is refuted, so its verdict is UNKNOWN (AMBIGUITIES.md, P10).
    const listed = proofsJ ? proofsJ.cells : [];
    if (listed.some((c) => has(c, 'tape'))) return { out: null, code: 64, message: 'files with no deck of rules whose cells carry a tape are outside what this kernel reads: it gives them no verdict' };
    const counts = zeroCounts();
    const rested = [];
    const cells = listed.map((c) => {
      const o = { subject: c.subject, mechanism: c.mechanism, entry: c.entry, claimed: c.state, state: 'open' };
      if (c.state === 'not_applicable') o.state = 'not_applicable';
      else if (c.state === 'waived') {
        const w = waivers.find((x) => x.subject === c.subject && x.mechanism === c.mechanism);
        if (w) { o.state = 'waived'; if (!rested.includes(w)) rested.push(w); }
        else o.reason = 'the card lists no waiver with this subject and mechanism';
      } else if (c.state === 'open') { /* format.md, The verdict: "An `open` cell of the file has none either" */ }
      else o.reason = `the cell is written ${c.state} and carries no tape: the kernel has no rule for its proof yet`;
      if (o.state === 'waived') o.reason = 'the card waives it';
      counts[o.state]++;
      return o;
    });
    return {
      out: { verdict: 'UNKNOWN', findings: [], counts, waived: rested.map((w) => ({ subject: w.subject, mechanism: w.mechanism, by: w.by, reason: w.reason })), cells },
      code: 2,
    };
  }
  if (!deck) return ill();

  // ---------------------------------------------------------------- parts
  // "So a design that has no `parts` is one with no part: each given of the card is then one that
  // no part reads, and each waiver names no part."
  const DN = designJ.name, CN = cardJ.name;
  const inputByName = new Map();
  for (const x of inputs) {
    if (inputByName.has(x.name)) find('card', x.item, `two inputs are named ${x.name}`, 'parts.6');
    else inputByName.set(x.name, x);
    const n = ['case', 'on', 'field'].filter((k) => x[k] !== undefined).length;
    x.isLoad = n === 3;
    x.isGiven = n === 0;
    if (!x.isLoad && !x.isGiven) find('card', x.item, 'the input has some but not all of case, on and field', 'parts.6');
  }
  // Parts 6: every item of `states` has a name of its own, among the items and among the inputs.
  const stateByName = new Map();
  for (const s of states) {
    if (stateByName.has(s.name)) find('card', s.item, `${s.name} is stated twice`, 'parts.6');
    else if (inputByName.has(s.name)) find('card', s.item, `${s.name} is stated and bounded: a statement and a bound do not share a name`, 'parts.6');
    else stateByName.set(s.name, s);
  }
  // format.md, After a broken rule: "A rule of Parts counts a given as read when a line of a part
  // has it as an argument, whether or not the line or the part breaks a rule of Parts. ... A part
  // that a shape finding left out reads nothing". And Parts 6: "A line reads the name its given
  // writes, so a statement is read when some line of some part has a given of its name."
  const givensNamed = new Set();
  for (const p of partsR) for (const l of p.lines) for (const a of l.args) if (a.kind === 'given') givensNamed.add(a.value);
  // "A part whose type the deck does not have (Parts 1) is no part that a load is put on, that a
  // waiver names or that another part joins. A part that breaks any other rule is still one." Of
  // two parts of one name the first is the part of that name, as in type rule 3, and the lines of
  // both are held to Parts 2 to 5 (AMBIGUITIES.md, P8).
  const parts = [];
  const partByName = new Map();
  for (const p of partsR) {
    const PF = (why, rule) => find('design', p.item, why, rule);
    const T = deck.types.get(p.type);
    if (!T) { PF(`${short(p.type)} is not a type of the deck`, 'parts.1'); continue; }
    const part = { name: p.name, type: T, values: new Map(), joinWords: new Map(), joins: new Map(), item: p.item };
    if (partByName.has(p.name)) PF(`two parts are named ${p.name}`, 'parts.1');
    else partByName.set(p.name, part);
    parts.push(part);
    const seen = new Set();
    p.lines.forEach((l, li) => {
      const LF = (why, rule = 'parts.3') => PF(`line ${li + 1}: ${why}`, rule);
      const f = T.fieldMap.get(l.field);
      if (!f) { LF(`${short(l.field)} is not a field of ${T.name}`, 'parts.2'); return; }
      if (seen.has(l.field)) { LF(`the part gives ${l.field} twice`, 'parts.2'); return; }
      seen.add(l.field);
      const args = l.args;
      const a = args.length === 1 ? args[0] : null;
      const given = a && a.kind === 'given' ? a.value : null;
      if (f.kind === 'q') {
        if (!a) { LF(`${f.name} takes one number or one given`); return; }
        // deck.md, "A field that a record may leave unstated": the one word `unstated`.
        if (a.kind === 'word' && a.value === 'unstated') {
          if (!f.optional) { LF(`${f.name} is not optional, and a part states it: unstated is refused`); return; }
          part.values.set(f.name, { kind: 'q', unstated: true });
          return;
        }
        let lo, hi, label, written = false;
        if (a.kind === 'number') {
          if (f.signed) { LF(`${f.name} is signed: it is for the card to state, and the design reads it with given`); return; }
          if (!sameFileDim(a.dim, f.dim)) { LF(`${f.name} is of ${f.dimName}, and the number is of ${short(a.dim)}`); return; }
          lo = a.lo; hi = a.hi;
          if (f.whole && (qcmp(lo, hi) !== 0 || lo.d !== 1n)) { LF(`${f.name} is a count: one whole number`); return; }
          label = `dsg:${DN}.${p.name}.${f.name}`;
          written = true;
        } else if (given !== null) {
          if (given !== `${p.name}.${f.name}`) { LF(`reads the given ${given}, and a part reads only what the card states for it, ${p.name}.${f.name}`); return; }
          if (f.whole) {
            // Parts 3: a count is stated by the card with `whole`; an input of its name is no count.
            if (inputByName.has(given)) { LF(`${given} is a count, which the card states exactly, and the card gives it a range`); return; }
            const st = stateByName.get(given);
            if (!st) { LF(`the card states no ${given}`); return; }
            if (st.whole === undefined) { LF(`the card states ${given} as a name, and it is a count`); return; }
            lo = hi = st.whole;
            label = `in:${CN}.${given}`;
          } else {
            const x = inputByName.get(given);
            if (!x) { LF(stateByName.has(given) ? `the card states ${given} exactly, and it is a quantity that is no count` : `the card has no input ${given}`); return; }
            if (!x.isGiven) { LF(`the input ${given} is a load`); return; }
            if (!sameFileDim(x.dim, f.dim)) { LF(`${f.name} is of ${f.dimName}, and the card's ${given} is of ${short(x.dim)}`); return; }
            lo = x.lo; hi = x.hi;
            label = `in:${CN}.${x.name}`;
          }
        } else { LF(`${f.name} takes one number or one given, not a ${a.kind}`); return; }
        // Parts 3: more than zero, at least zero with may_be zero, no floor by its sign with
        // may_be negative; a number the design writes for such a field is held to the floor its
        // dimension has in domains.input of core.json (type rule 8) when that floor is under
        // zero. And at least its least.
        if (!f.mayBe && lo.n <= 0n) { LF(`${f.name} is ${lo}, not more than zero`); return; }
        if (f.mayBe === 'zero' && lo.n < 0n) { LF(`${f.name} is ${lo}, under zero`); return; }
        if (f.mayBe === 'negative' && written) {
          const fl = inputDomains.get(dstr(f.dim));
          if (fl && fl.min.n < 0n) {
            const c = qcmp(lo, fl.min);
            if (c < 0 || (c === 0 && fl.strict)) { LF(`${f.name} is ${lo}, below the floor of ${fl.name}`); return; }
          }
        }
        if (f.least && qcmp(lo, f.least) < 0) { LF(`${f.name} is ${lo}, below its least ${f.least}`); return; }
        part.values.set(f.name, { kind: 'q', label, lo, hi });
      } else if (f.kind === 'k') {
        if (!a) { LF(`${f.name} takes one word, one text or one given`, 'parts.4'); return; }
        if (a.kind === 'word' && a.value === 'unstated' && f.optional) { part.values.set(f.name, { kind: 'k', unstated: true }); return; }
        if (given !== null) {
          // Parts 4: a given of a key is an item of `states` with `key`.
          if (given !== `${p.name}.${f.name}`) { LF(`reads the given ${given}, and a part reads only what the card states for it, ${p.name}.${f.name}`, 'parts.4'); return; }
          if (inputByName.has(given)) { LF(`the card gives ${given} a range, and a key is stated exactly`, 'parts.4'); return; }
          const st = stateByName.get(given);
          if (!st) { LF(`the card states no ${given}`, 'parts.4'); return; }
          if (st.key === undefined) { LF(`the card states ${given} as a count, and it is a key`, 'parts.4'); return; }
          if (!f.names.includes(st.key)) { LF(`the card states ${short(st.key)} for ${given}, which is not one of the names of ${f.name}`, 'parts.4'); return; }
          part.values.set(f.name, { kind: 'k', value: st.key });
          return;
        }
        // Parts 4: "a key that does not say `chosen` is a given, whether or not its field says
        // `signed`, and a word or a text for it is a finding. A key that says `chosen` is a word,
        // a text or a given."
        if (f.signed) { LF(`${f.name} is for the card to state: its field does not say chosen, and the design reads it with given`, 'parts.4'); return; }
        if (a.kind !== 'word' && a.kind !== 'text') { LF(`${f.name} takes one word, one text or one given, not a number`, 'parts.4'); return; }
        if (!f.names.includes(a.value)) { LF(`${short(a.value)} is not one of the names of ${f.name}`, 'parts.4'); return; }
        part.values.set(f.name, { kind: 'k', value: a.value });
      } else {
        if (args.length !== f.as.length) { LF(`${f.name} takes ${f.as.length} words`, 'parts.5'); return; }
        const words = [];
        for (const b of args) {
          if (b.kind !== 'word') { LF(`${f.name} takes words that name parts, not a ${b.kind}`, 'parts.5'); return; }
          words.push(b.value);
        }
        part.joinWords.set(f.name, words);
      }
    });
    for (const f of T.fields) if (!seen.has(f.name)) PF(`the part has no line for ${f.name}`, 'parts.2');
  }
  const joinedBy = new Map();
  for (const part of parts) {
    for (const f of part.type.joins) {
      const words = part.joinWords.get(f.name);
      if (!words) continue;
      if (new Set(words).size !== words.length) { find('design', part.item, `${f.name} names one part twice`, 'parts.5'); continue; }
      words.forEach((w, i) => {
        const q = partByName.get(w);
        if (!q) { find('design', part.item, `${f.name} names ${w}, which is no part`, 'parts.5'); return; }
        if (q.type.name !== f.type) { find('design', part.item, `${f.name} names ${w}, which is not a ${f.type}`, 'parts.5'); return; }
        if (joinedBy.has(w)) { find('design', part.item, `${w} is joined more than once`, 'parts.5'); return; }
        joinedBy.set(w, part.name);
        part.joins.set(f.as[i], q);
      });
    }
  }
  // Parts 6. A load is tested in this order and stops at the first that fails: its part, its
  // field, its dimension, its least, that no case puts it on the part twice, and then the name of
  // its case (64 bytes, no `/`, and not `where`). A load that fails is no load of the card. A
  // given is one that a part reads (`givensNamed`, above).
  const loadKeys = new Set();
  const loads = [];
  for (const x of inputs) {
    if (x.isLoad) {
      const part = partByName.get(x.on);
      if (!part) { find('card', x.item, `the load is on ${short(x.on)}, which is no part`, 'parts.6'); continue; }
      const L = part.type.loads.get(x.field);
      if (!L) { find('card', x.item, `${short(x.field)} is not a load of ${part.type.name}`, 'parts.6'); continue; }
      if (!sameFileDim(x.dim, L.dim)) { find('card', x.item, `the load ${L.name} is of ${L.dimName}, and the input is of ${short(x.dim)}`, 'parts.6'); continue; }
      if (L.least && qcmp(x.lo, L.least) < 0) { find('card', x.item, `the load is below its least ${L.least}`, 'parts.6'); continue; }
      const k = `${x.case}\u0000${x.on}\u0000${x.field}`;
      if (loadKeys.has(k)) { find('card', x.item, `the case ${x.case} puts ${x.field} on ${x.on} twice`, 'parts.6'); continue; }
      loadKeys.add(k);
      if (!nameLimit('card', x.item, x.case, NAME_BYTES, `the name of the case ${short(x.case)}`)) continue;
      if (x.case.includes('/')) { find('card', x.item, `the name of the case ${short(x.case)} holds a /`); continue; }
      // Parts 6: a case is not named `where`, since an entry that ends in `/where` is a range.
      if (x.case === 'where') { find('card', x.item, CASE_WHERE); continue; }
      loads.push(x);
    } else if (x.isGiven && !givensNamed.has(x.name)) {
      find('card', x.item, `no part reads the given ${x.name}`, 'parts.6');
    }
  }
  for (const s of states) if (stateByName.get(s.name) === s && !givensNamed.has(s.name)) find('card', s.item, `${s.name} is stated, and no part reads it`, 'parts.6');
  // A name in `cases` that no load has is a load case too, held to the same limit.
  const loadCaseNames = new Set(loads.map((x) => x.case));
  for (const c of cardCases) {
    if (loadCaseNames.has(c)) continue;
    if (!nameLimit('card', 'cases', c, NAME_BYTES, `the name of the case ${short(c)}`)) continue;
    if (c.includes('/')) find('card', 'cases', `the name of the case ${short(c)} holds a /`);
    else if (c === 'where') find('card', 'cases', CASE_WHERE);
  }
  for (const w of waivers) {
    const part = partByName.get(w.subject);
    if (!part) { find('card', w.item, `the waiver names ${w.subject}, which is no part`, 'parts.7'); continue; }
    if (!deck.lineOf.has(`${part.type.name}\u0000${w.mechanism}`)) find('card', w.item, `the grid asks no ${w.mechanism} of a ${part.type.name}`, 'parts.7');
  }
  // Parts 8: no claim, tests record, probability claim or environment, and no param. format.md,
  // card.json: the kernel "holds neither key to a list: any value but the empty list is a card
  // that has one, and the finding is of Parts 8 and not of shape."
  const hasOne = (k) => has(cardJ, k) && !(Array.isArray(cardJ[k]) && cardJ[k].length === 0);
  if (claims.length) find('card', 'claims', 'a card for a deck of rules has no claim', 'parts.8');
  if (hasOne('tests')) find('card', 'tests', 'a card for a deck of rules has no tests record', 'parts.8');
  if (hasOne('probability_claims')) find('card', 'probability_claims', 'a card for a deck of rules has no probability claim', 'parts.8');
  if (cardJ.environment !== null) find('card', 'environment', 'a deck of rules does not read an environment yet', 'parts.8');
  if (params.length) find('design', 'params', 'a design of a deck\'s types has no param', 'parts.8');
  if (findings.length) return ill();

  // A field of a part by the name a rule or a need writes: FIELD, or AS.FIELD of a joined part.
  const resolve = (part, ref) => {
    const dot = ref.indexOf('.');
    if (dot < 0) return { part, field: ref };
    return { part: part.joins.get(ref.slice(0, dot)), field: ref.slice(dot + 1) };
  };
  const valueOf = (part, ref) => { const r = resolve(part, ref); return r.part.values.get(r.field); };
  const isUnstated = (part, ref) => valueOf(part, ref)?.unstated === true;
  const unstatedName = (part, ref) => { const r = resolve(part, ref); return `${r.part.name}.${r.field}`; };
  const partHasUnstated = (part) => [part, ...part.joins.values()].some((q) => [...q.values.values()].some((v) => v.unstated));
  for (const part of parts) part.hasUnstated = partHasUnstated(part);

  // ---------------------------------------------------------------- Parts 9: the needs
  // format.md, Parts 9: each part keeps each need of its type, decided with exact fractions over
  // the ranges of its fields. A need that names an unstated field is not asked: "it is no
  // finding, and the kernel goes on to the next need. Each such field then has an open cell, so
  // the design does not pass" (the cell is made with the `unread` cells, below). A value of more
  // than 65,536 bits leaves the need undecided, which is a finding too.
  class NeedTooBig extends Error {}
  const big = (q) => { if (tooBig(q)) throw new NeedTooBig(); return q; };
  const needRange = (e, part) => {
    if (isStr(e)) {
      if (looksNumeric(e)) { const v = parseNumberAlone(e); return [v, v]; }
      const v = valueOf(part, e);
      return [v.lo, v.hi];
    }
    const args = e.slice(1);
    switch (e[0]) {
      case 'q': { const v = qValue(e).v; return [v, v]; }
      case 'add': {
        let lo = Q0, hi = Q0;
        for (const a of args) { const r = needRange(a, part); lo = big(qadd(lo, r[0])); hi = big(qadd(hi, r[1])); }
        return [lo, hi];
      }
      case 'mul': {
        let acc = [Q1, Q1];
        for (const a of args) { acc = imul(acc, needRange(a, part)); big(acc[0]); big(acc[1]); }
        return acc;
      }
      case 'neg': { const r = needRange(args[0], part); return [qneg(r[1]), qneg(r[0])]; }
      case 'sub': {
        const a = needRange(args[0], part), b = needRange(args[1], part);
        return [big(qsub(a[0], b[1])), big(qsub(a[1], b[0]))];
      }
      case 'div': {
        const a = needRange(args[0], part), b = needRange(args[1], part);
        const r = imul(a, [qdiv(Q1, b[1]), qdiv(Q1, b[0])]);
        big(r[0]); big(r[1]);
        return r;
      }
    }
    throw new Error(`unexpected operator in a need: ${e[0]}`);
  };
  for (const part of parts) {
    part.type.needs.forEach((need, k) => {
      if (need.fields.some((ref) => isUnstated(part, ref))) return;
      let L, Rg;
      try { L = needRange(need.sides[0], part); Rg = needRange(need.sides[1], part); } catch (e) {
        if (!(e instanceof NeedTooBig)) throw e;
        find('design', part.name, `need ${k + 1} of a ${part.type.name} is not decided: a value has more than 65536 bits`, 'parts.9');
        return;
      }
      const c = qcmp(L[1], Rg[0]);
      if (need.op === 'le' ? c <= 0 : c < 0) return;
      find('design', part.name, `breaks need ${k + 1} of a ${part.type.name}: its left side, up to ${L[1]}, is not ${need.op === 'le' ? 'at most' : 'under'} its right side, down to ${Rg[0]}, in SI units: ${need.why}`, 'parts.9');
    });
  }
  if (findings.length) return ill();

  // ---------------------------------------------------------------- cells
  // format.md, Limits and Steps: at most 10,000 cells and 10,000,000 steps to make them and write
  // their tapes. The count is tested after each charge of Steps items 1, 2, 3 and 5; the nodes of
  // a tape (item 4) are added with no test of their own.
  let steps = 0;
  const charge = (n) => {
    steps += n;
    if (steps > CELL_STEPS) throw new LimitErr('making the cells and writing their tapes takes more than 10,000,000 steps');
  };
  // The load cases of the card: the names its `cases` lists and the `case` of each of its loads,
  // each once, in order by code point.
  const loadCases = [...new Set([...cardCases, ...loads.map((x) => x.case)])].sort(nameCmp);
  // The loads on each part, by field and then by case; the lines and the rules, by type.
  const loadsOn = new Map();
  for (const x of loads) {
    if (!loadsOn.has(x.on)) loadsOn.set(x.on, new Map());
    const m = loadsOn.get(x.on);
    if (!m.has(x.field)) m.set(x.field, new Map());
    m.get(x.field).set(x.case, x);
  }
  const loadInput = (cs, partName, field) => loadsOn.get(partName).get(field).get(cs);
  const putsLoad = (cs, partName, field) => loadsOn.get(partName)?.get(field)?.has(cs) ?? false;
  const waiverOf = new Map();
  for (const w of waivers) { const k = `${w.subject}\u0000${w.mechanism}`; if (!waiverOf.has(k)) waiverOf.set(k, w); }
  const linesOf = new Map(), rulesOfType = new Map(), rulesOfLine = new Map();
  const addTo = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };
  for (const g of deck.grid) addTo(linesOf, g.type, g);
  for (const r of deck.rules) { addTo(rulesOfType, r.type, r); addTo(rulesOfLine, `${r.type}\u0000${r.mechanism}`, r); }
  // The name a part has for a key, by the name a rule writes. Under a completion (format.md, The
  // rules, item 9) an unstated key has the name the completion gives it.
  const keyValue = (part, ref, comp) => {
    const r = resolve(part, ref);
    const v = r.part.values.get(r.field);
    if (v.unstated) return comp ? comp.keys.get(`${r.part.name}\u0000${r.field}`) : undefined;
    return v.value;
  };
  const partCond = (c, part, comp) => {
    switch (c[0]) {
      case 'is': return keyValue(part, c[1], comp) === c[2];
      case 'and': return c.slice(1).every((x) => partCond(x, part, comp));
      case 'or': return c.slice(1).some((x) => partCond(x, part, comp));
      case 'not': return !partCond(c[1], part, comp);
    }
    return false;
  };
  // format.md, Cells 3: "A rule answers for a part when its `when` holds for the part, and a rule
  // with no `when` answers for every part of its type." Cells 2: "A signed field is not optional,
  // so no key that a `when` reads is unstated, and a `when` holds for a part or it does
  // not." So the `when` of a rule and of an `unless` is decided on the part as it is, with no
  // completion: the deck reader has refused a `when` that names a key that is not signed.
  const answers = (rule, part) => rule.when === undefined || partCond(rule.when, part);

  // A tape from a rule for a part (and a case), with the root of le or lt, or the roots of where.
  // `comp`, a completion, names each unstated key the rule reads and gives each load the case
  // leaves out, as an input of one value labelled `put:CASE.PART.LOAD` (item 9).
  const writeTape = (rule, part, cs, which, comp = null) => {
    const t = new Tape();
    const letNodes = new Map();
    const quantityNode = (name) => {
      const v = valueOf(part, name);
      return t.input(v.label, v.lo, v.hi);
    };
    const op = (e, sub) => {
      switch (e[0]) {
        case 'add': case 'mul': case 'min': case 'max': return t.add([e[0], e.slice(1).map(sub)]);
        case 'sub': { const a = sub(e[1]), b = sub(e[2]); return t.add(['add', [a, t.add(['neg', b])]]); }
        case 'div': { const a = sub(e[1]), b = sub(e[2]); return t.add(['div', a, b]); }
        case 'neg': case 'abs': case 'sqrt': case 'exp': case 'ln': case 'cos': return t.add([e[0], sub(e[1])]);
        case 'pow': {
          const b = sub(e[1]);
          const x = e[2];
          if (isStr(x) && looksNumeric(x)) {
            const n = parseNumberAlone(x);
            const twice = qmul(n, R(2n));
            if (twice.d === 1n) {
              // A whole power of 0 or below is 1 over the power, as a negative one is.
              const neg = n.n <= 0n;
              const tw = twice.n < 0n ? -twice.n : twice.n;
              const node = tw % 2n === 0n ? t.add(['pow', b, Number(tw / 2n)]) : t.add(['pow', t.add(['sqrt', b]), Number(tw)]);
              return neg ? t.add(['div', t.c(Q1), node]) : node;
            }
            return t.add(['exp', t.add(['mul', [t.c(n), t.add(['ln', b])]])]);
          }
          const xe = sub(x);
          return t.add(['exp', t.add(['mul', [xe, t.add(['ln', b])]])]);
        }
      }
      throw new Error(`unexpected operator ${e[0]}`);
    };
    const rowExpr = (e, qin) => {
      if (isStr(e)) {
        if (e === 'pi') return t.add(['pi']);
        if (looksNumeric(e)) return t.c(parseNumberAlone(e));
        return qin(e);
      }
      if (e[0] === 'q') return t.c(qValue(e).v);
      return op(e, (a) => rowExpr(a, qin));
    };
    const rowCond = (c, qin) => {
      const x = (a) => rowExpr(a, qin);
      switch (c[0]) {
        case 'le': return ['le', x(c[1]), x(c[2])];
        case 'lt': return ['lt', x(c[1]), x(c[2])];
        case 'ge': { const a = x(c[1]), b = x(c[2]); return ['le', b, a]; }
        case 'gt': { const a = x(c[1]), b = x(c[2]); return ['lt', b, a]; }
        case 'and': case 'or': return [c[0], c.slice(1).map((y) => rowCond(y, qin))];
        case 'not': return ['not', rowCond(c[1], qin)];
      }
      throw new Error(`unexpected condition ${c[0]}`);
    };
    // The name of a key side read by a key field, a fixed name or a `by`. The map of a `by` is
    // total and a completion names every unstated key, so the guard does not arise.
    const resolveKey = (b) => {
      if (isStr(b)) return keyValue(part, b, comp);
      if (b[0] === 'key') return b[1];
      const v = keyValue(part, b[1], comp);
      if (!Object.hasOwn(b[2], v)) throw new CannotWrite(`the table has no line for ${b[1]} ${v}`);
      return b[2][v];
    };
    // format.md, "How the kernel writes a table": the condition of a place of a side.
    const placeCond = (side, i, x) => {
      if (side.kind === 'at') { const v = t.c(side.at[i]); return ['and', [['le', x, v], ['le', v, x]]]; }
      const [lo, hi] = side.bands[i];
      const L = t.c(lo);
      if (side.closed === 'upper') { const c1 = ['lt', L, x]; return hi === null ? c1 : ['and', [c1, ['le', x, t.c(hi)]]]; }
      const c1 = ['le', L, x];
      return hi === null ? c1 : ['and', [c1, ['lt', x, t.c(hi)]]];
    };
    // No pick is over 1,024 orders: a deck that could write one does not load (loadRule).
    // The inputs of a row that gives a name, each written once from the expression bound to it.
    const nameRowInputs = (binds) => {
      const cache = new Map();
      return (nm) => {
        let i = cache.get(nm);
        if (i === undefined) { i = expr(binds[nm]); cache.set(nm, i); }
        return i;
      };
    };
    // The condition of a cell of a row that gives a name: the condition of its place on the row's
    // own side, or `and` of the two for a row with two sides.
    const nameCellCond = (N, c, nq) => {
      const down = placeCond(N.table.down, c.i, nq(N.table.down.by));
      if (!N.table.across) return down;
      return ['and', [down, placeCond(N.table.across, c.j, nq(N.table.across.by))]];
    };
    // The places of a side of a table, each with a condition written when used.
    const sidePlaces = (side, binding, qin) => {
      if (side.kind === 'key') {
        const b = binding[side.by];
        if (Array.isArray(b) && b[0] === 'row') {
          const N = deck.rows.get(b[1]);
          const nq = nameRowInputs(b[2]);
          return nameCells(N).map((c) => ({ idx: side.names.indexOf(c.name), cond: () => nameCellCond(N, c, nq) }));
        }
        return [{ idx: side.names.indexOf(resolveKey(b)), cond: null }];
      }
      let x;
      const xn = () => (x === undefined ? (x = qin(side.by)) : x);
      return [...Array(side.count).keys()].map((i) => ({ idx: i, cond: () => placeCond(side, i, xn()) }));
    };
    const table = (row, binding, qin) => {
      const T = row.table;
      const D = sidePlaces(T.down, binding, qin);
      const A = T.across ? sidePlaces(T.across, binding, qin) : [{ idx: null, cond: null }];
      const cellAt = (i, j) => (T.across ? T.cells[i][j] : T.cells[i]);
      const lines = [];
      for (const dp of D) {
        const cs = A.filter((ap) => cellAt(dp.idx, ap.idx) !== null);
        if (cs.length) lines.push({ dp, cs });
      }
      // format.md, How the kernel writes a table: with no line at all, the table is a pick of no
      // case, which has no value anywhere, and the tape is still written.
      if (!lines.length) return t.add(['pick', []]);
      const lineNodes = lines.map((l) => {
        const cases = l.cs.map((ap) => [ap.cond ? ap.cond() : null, t.c(cellAt(l.dp.idx, ap.idx))]);
        return cases[0][0] === null ? cases[0][1] : t.add(['pick', cases]);
      });
      const cases = lines.map((l, k) => [l.dp.cond ? l.dp.cond() : null, lineNodes[k]]);
      return cases[0][0] === null ? cases[0][1] : t.add(['pick', cases]);
    };
    const applyRow = (row, binding) => {
      const cache = new Map();
      const qin = (nm) => {
        let i = cache.get(nm);
        if (i === undefined) { i = expr(binding[nm]); cache.set(nm, i); }
        return i;
      };
      if (row.kind === 'is') return rowExpr(row.is, qin);
      if (row.kind === 'cases') {
        const cases = row.cases.map((cs2) => {
          const c = cs2.when === undefined ? null : rowCond(cs2.when, qin);
          return [c, rowExpr(cs2.is, qin)];
        });
        // One case that holds otherwise, standing first, is its own node and no pick.
        return cases[0][0] === null ? cases[0][1] : t.add(['pick', cases]);
      }
      return table(row, binding, qin);
    };
    const expr = (e) => {
      if (isStr(e)) {
        if (e === 'pi') return t.add(['pi']);
        if (looksNumeric(e)) return t.c(parseNumberAlone(e));
        if (Object.hasOwn(rule.lets, e)) {
          let i = letNodes.get(e);
          if (i === undefined) { i = expr(rule.lets[e]); letNodes.set(e, i); }
          return i;
        }
        return quantityNode(e);
      }
      switch (e[0]) {
        case 'q': return t.c(qValue(e).v);
        case 'load': {
          if (cs !== null && putsLoad(cs, part.name, e[1])) {
            const x = loadInput(cs, part.name, e[1]);
            return t.input(`in:${CN}.${x.name}`, x.lo, x.hi);
          }
          // Item 9: under a completion the card puts the load on its part in its case.
          const v = comp.loads.get(e[1]);
          return t.input(`put:${cs ?? ''}.${part.name}.${e[1]}`, v, v);
        }
        case 'row': return applyRow(deck.rows.get(e[1]), e[2]);
        case 'case': {
          // format.md: a `case` is one pick, for each cell of its row that holds a name, the
          // condition of the cell and the node of the expression of its name. Every expression
          // is written.
          const N = deck.rows.get(e[1][1]);
          const cells = nameCells(N);
          const nq = nameRowInputs(e[1][2]);
          const node = new Map();
          for (const nm of N.gives.names) node.set(nm, expr(e[2][nm]));
          return t.add(['pick', cells.map((c) => [nameCellCond(N, c, nq), node.get(c.name)])]);
        }
      }
      return op(e, expr);
    };
    // 'where': one root for each item of `where`. 'whole' (item 9, a witness of a rule with
    // `where`): those roots and after them the rule's root of item 6, so that a partition that
    // proves every root proves the range and the rule over the whole box.
    if (which === 'where' || which === 'whole') {
      for (const w of rule.where) { const l = expr(w[0]), r = expr(w[1]); t.roots.push(t.add(['add', [l, t.add(['neg', r])]])); }
      if (which === 'where') return t;
    }
    let root;
    if (rule.form === 'le') {
      const l = expr(rule.sides[0]), r = expr(rule.sides[1]);
      root = t.add(['add', [l, t.add(['neg', r])]]);
    } else {
      // format.md, Cells 6: for `lt` the root is the pick [[lt L R] -1] [null 1].
      const l = expr(rule.sides[0]), r = expr(rule.sides[1]);
      const M = t.c(R(-1n)), P = t.c(Q1);
      root = t.add(['pick', [[['lt', l, r], M], [null, P]]]);
    }
    if (which === 'within') {
      // format.md, Cells 5: the rule's tape inside its range, whose root is a pick: the rule's
      // root where every item of `where` holds, and -1 where one does not.
      const conds = rule.where.map((w) => ['le', expr(w[0]), expr(w[1])]);
      root = t.add(['pick', [[conds.length === 1 ? conds[0] : ['and', conds], root], [null, t.c(R(-1n))]]]);
    }
    t.roots.push(root);
    return t;
  };

  const usedHints = new Set();
  const cells = [];
  const cellKeys = new Set();
  const usedWaivers = [];
  // The cells of the lines that are answered `with` other lines, to be settled last (Cells 2).
  const withCells = [];
  const push = (c) => {
    if (cells.length >= CELL_LIMIT) throw new LimitErr('the design has more than 10,000 cells');
    const k = hintKey(c.subject, c.mechanism, c.entry);
    cellKeys.add(k);
    usedHints.add(k);
    c.claimed = hints.get(k)?.[0]?.state ?? null;
    cells.push(c);
  };
  const hintsFor = (s, m, e) => hints.get(hintKey(s, m, e)) || [];
  const tryWrite = (rule, part, cs, which, comp = null) => {
    try {
      const tape = writeTape(rule, part, cs, which, comp);
      steps += tape.nodes.length; // Steps item 4, tested at the next charge
      return { tape };
    } catch (e) { if (e instanceof CannotWrite) return { why: e.message }; throw e; }
  };
  // What the hints left of a cell that none of them settles.
  const hintsLeft = (tried) => (tried.length ? 'no partition of proofs.json proves it and no point refutes it' : 'proofs.json has no partition and no point for it');

  // ---- completions (format.md, The rules, items 1 and 9)
  // The unstated keys of a list of names a rule writes, each key of a part once, in the order of
  // the list: {key: "PART\0FIELD", names}.
  const unstatedKeys = (part, refs) => {
    const out = [];
    for (const ref of refs) {
      if (!isUnstated(part, ref)) continue;
      const r = resolve(part, ref);
      const key = `${r.part.name}\u0000${r.field}`;
      if (!out.some((x) => x.key === key)) out.push({ key, names: r.part.type.fieldMap.get(r.field).names });
    }
    return out;
  };
  // How many keys and loads a hint's completion names, for the steps.
  const compSize = (c) => (isObj(c) ? (Array.isArray(c.keys) ? c.keys.length : 0) + (Array.isArray(c.loads) ? c.loads.length : 0) : 0);
  // A completion fits a cell when it names each unstated key once, with a name its field lists,
  // and gives each load the case leaves out once, on the part and in the cell's case, with a value
  // at or above the load's least, or at or above zero for a load with no least that is not
  // "may_be": "negative", and that the floor of its dimension admits where the floor holds for
  // the load, as type rule 4 holds a load of the card (AMBIGUITIES.md, L9): that floor is
  // core.json's (type rule 8). It names nothing else. Returns {keys, loads, loadKeys, src} or
  // null; `src` is what a waived cell resting on it prints (format.md, The verdict): the hint's
  // completion "with one item more for each load", `[PART, LOAD, CASE, VALUE, UNIT]`, where UNIT
  // is the unit of Petra's SI for the dimension the deck gives the load (siUnit).
  const fitComp = (c, part, cs, ukeys, missing) => {
    if (!isObj(c) || Object.keys(c).some((k) => k !== 'keys' && k !== 'loads')) return null;
    const kl = Object.hasOwn(c, 'keys') ? c.keys : [], ll = Object.hasOwn(c, 'loads') ? c.loads : [];
    if (!Array.isArray(kl) || !Array.isArray(ll) || kl.length !== ukeys.length || ll.length !== missing.length) return null;
    const comp = { keys: new Map(), loads: new Map(), loadKeys: new Map(), loadList: [], src: { keys: kl, loads: [] } };
    for (const k of kl) {
      if (!Array.isArray(k) || k.length !== 3 || !k.every(isStr)) return null;
      const key = `${k[0]}\u0000${k[1]}`;
      const u = ukeys.find((x) => x.key === key);
      if (!u || comp.keys.has(key) || !u.names.includes(k[2])) return null;
      comp.keys.set(key, k[2]);
    }
    for (const l of ll) {
      if (!Array.isArray(l) || l.length !== 4 || !l.every(isStr)) return null;
      const v = parseFileNumber(l[3]);
      if (!v || l[0] !== part.name || l[2] !== (cs ?? '') || !missing.includes(l[1]) || comp.loads.has(l[1])) return null;
      const L = part.type.loads.get(l[1]);
      if (L.least ? qcmp(v, L.least) < 0 : L.mayBe !== 'negative' && v.n < 0n) return null;
      const fl = inputDomains.get(dstr(L.dim));
      if (fl && !(L.mayBe === 'negative' && fl.min.n >= 0n)) {
        const c2 = qcmp(v, fl.min);
        if (c2 < 0 || (c2 === 0 && fl.strict)) return null;
      }
      comp.loads.set(l[1], v);
      comp.loadKeys.set(`${l[0]}\u0000${l[1]}\u0000${l[2]}`, v);
      comp.loadList.push({ part: l[0], load: l[1], cs: l[2] });
      comp.src.loads.push([l[0], l[1], l[2], l[3], siUnit(L.dim)]);
    }
    return comp;
  };
  // The completions of the cells that waivers rest agree, across the design (item 1).
  // `restedPuts`: for each part, each load a rested completion gives and the cases it gives it in,
  // for the reads of item 8.
  const restedKeys = new Map(), restedLoads = new Map(), restedPuts = new Map();
  const agrees = (comp) => {
    for (const [k, nm] of comp.keys) if (restedKeys.has(k) && restedKeys.get(k) !== nm) return false;
    for (const [k, v] of comp.loadKeys) if (restedLoads.has(k) && qcmp(restedLoads.get(k), v) !== 0) return false;
    return true;
  };
  const recordRested = (comp) => {
    for (const [k, nm] of comp.keys) restedKeys.set(k, nm);
    for (const [k, v] of comp.loadKeys) restedLoads.set(k, v);
    for (const p of comp.loadList) {
      if (!restedPuts.has(p.part)) restedPuts.set(p.part, new Map());
      const m = restedPuts.get(p.part);
      if (!m.has(p.load)) m.set(p.load, new Set());
      m.get(p.load).add(p.cs);
    }
  };
  // Item 4: the reason of a refuted rule with requires names each key it names, in order and each
  // once, with the name the part has for it, or `unstated`, while they fit: "the first key always,
  // and a later one while the keys so far, `, ` and that key are at most 144 bytes of UTF-8". The
  // bytes are now those of UTF-8 and not those a text prints in, and "A reason whose first key
  // alone takes it past 200 bytes as printed is cut as any reason is" (the cell cuts it).
  const utf8Bytes = (t) => Buffer.byteLength(t, 'utf8');
  const requiresReason = (rule, part) => {
    const head = 'the part is not what the rule requires: ';
    let named = '';
    const ks = rule.requiresKeys;
    for (let i = 0; i < ks.length; i++) {
      const v = keyValue(part, ks[i]);
      const piece = `${ks[i]} is ${v === undefined ? 'unstated' : [...String(v)].slice(0, 200).join('')}`;
      if (i > 0 && utf8Bytes(named) + 2 + utf8Bytes(piece) > 144) { named += ` and ${ks.length - i} more`; break; }
      named += (i > 0 ? ', ' : '') + piece;
    }
    return head + named;
  };
  // "no pull", "no twist and no push": the first four loads a case leaves out, and how many more.
  const noLoads = (ls) => {
    const shown = ls.slice(0, 4).map((l) => `no ${l}`);
    if (ls.length > 4) return `${shown.join(', ')} and ${ls.length - 4} more`;
    return shown.length > 1 ? `${shown.slice(0, -1).join(', ')} and ${shown[shown.length - 1]}` : shown[0];
  };

  // The cells of one rule that answers for a part, into `out`. An open cell carries `rest`: what a
  // waiver of the line may rest it on (format.md, Cells 1). 'norule' and 'where' rest it as it is,
  // a completion rests it while it agrees with those rested before, and null not at all. On a line
  // the card waives (`waived`) the kernel asks item 5's question and looks for item 9's witness.
  const ruleCells = (rule, part, line, out, waived) => {
    // "A text is cut once, where it is made: a reason when its cell is made" (format.md, A text
    // that is cut). `requires` marks every cell of a rule with `requires`, and `noInput` a cell
    // that item 6 proves or refutes on a tape whose root reads no input: both print `"stated": true`.
    const cell = (entry, state, reason, rest = null, noInput = false) => out.push({ subject: part.name, mechanism: line.mechanism, entry, state, reason: reason === undefined ? undefined : cutText(reason), rest, requires: rule.form === 'requires', noInput });
    // Item 9: an incomplete cell, of a rule that reads unstated keys (ukeys) and no unstated
    // quantity, or whose case leaves out loads the rule reads (missing). It looks only at the
    // hints that have a completion.
    const incomplete = (entry, cs, missing, ukeys, why) => {
      const hs = hintsFor(part.name, line.mechanism, entry).filter((h) => Object.hasOwn(h, 'completion'));
      const stepOf = 1 + rule.whenSize + rule.requiresSize;
      // A tape written under a completion takes the weight, twice with `where`, and its nodes,
      // which are steps of item 9's charge and so tested at once. `which` is 'within' (the second
      // tape of item 5) to refute a rule with `where`, 'whole' (its range and the rule) or 'where'
      // (its range alone) for a witness of one, and 'le' for a rule with none.
      const tapeUnder = (comp, which) => {
        charge(rule.where !== undefined ? 2 * rule.weight : rule.weight);
        const w = tryWrite(rule, part, cs, which, comp);
        charge(0);
        return w;
      };
      // Refuted when the case leaves out no load and the rule fails under every combination of
      // names of the unstated keys: the names of each key in the order its field lists them, the
      // first key's fastest, while there are at most 4,096, stopping at the first that does not.
      // Each combination is a step, with the sizes of `when` and `requires` and one for each key
      // it names. For a rule with an inequality each hint of the cell is looked at once, before the
      // first combination, and the points of those whose completion fits and gives no load are
      // kept by the names they give the keys, in the file's order (AMBIGUITIES.md, L3 and L8).
      if (!missing.length && ukeys.length) {
        let combos = 1;
        for (const k of ukeys) { combos *= k.names.length; if (combos > COMPLETION_COMBOS) break; }
        let all = combos <= COMPLETION_COMBOS;
        const namesKey = (keys) => ukeys.map((u) => keys.get(u.key)).join('\u0000');
        const points = new Map();
        if (all && rule.form !== 'requires') {
          for (const h of hs) {
            charge(stepOf + compSize(h.completion));
            const hc = fitComp(h.completion, part, cs, ukeys, missing);
            if (!hc || hc.loads.size || !Object.hasOwn(h, 'point')) continue;
            const k = namesKey(hc.keys);
            if (!points.has(k)) points.set(k, []);
            points.get(k).push({ comp: hc, point: h.point });
          }
        }
        for (let n = 0; all && n < combos; n++) {
          const comp = { keys: new Map(), loads: new Map(), loadKeys: new Map() };
          let x = n;
          for (const k of ukeys) { comp.keys.set(k.key, k.names[x % k.names.length]); x = Math.floor(x / k.names.length); }
          charge(stepOf + ukeys.length);
          // Item 9: "under each, the rule answers for the part": it does, since no completion
          // names a key of its `when` ("No completion changes which rules answer for a part").
          if (rule.form === 'requires') { if (partCond(rule.requires, part, comp)) all = false; continue; }
          let fails = false;
          for (const p of points.get(namesKey(comp.keys)) ?? []) {
            const w = tapeUnder(p.comp, rule.where !== undefined ? 'within' : 'le');
            if (w.tape && refutes(w.tape, p.point)) { fails = true; break; }
          }
          if (!fails) all = false;
        }
        if (all) { cell(entry, 'refuted', rule.form === 'requires' ? requiresReason(rule, part) : undefined); return; }
      }
      // Otherwise, on a line the card waives, the first hint that is a witness, the hints looked
      // at again in the file's order. Item 9: "A hint is a witness when its completion fits the
      // cell and, under it, its `requires` holds, or the hint's partition proves the rule's tape
      // written under it." For a rule with `where` that tape is the range and the rule over the
      // whole box, and a hint with no partition is a witness when the `where` holds nowhere in
      // the box (item 5's question). The hint's point is not tried. A completion under which the
      // rule does not answer is no witness any more: there is none ("No completion changes which
      // rules answer for a part or which lines arise").
      if (waived) {
        for (const h of hs) {
          charge(stepOf + compSize(h.completion));
          const comp = fitComp(h.completion, part, cs, ukeys, missing);
          if (!comp) continue;
          let witness;
          if (rule.form === 'requires') witness = partCond(rule.requires, part, comp);
          else if (Object.hasOwn(h, 'partition')) {
            const w = tapeUnder(comp, rule.where !== undefined ? 'whole' : 'le');
            witness = !!w.tape && proves(w.tape, h.partition);
          } else if (rule.where !== undefined) {
            const w = tapeUnder(comp, 'where');
            witness = !!w.tape && holdsNowhere(w.tape) >= 0;
          } else witness = false;
          if (witness) { cell(entry, 'open', why, comp); return; }
        }
      }
      cell(entry, 'open', why);
    };

    // Cells 3 and Steps item 2: a rule that reads a field the part leaves unstated. An unstated
    // quantity gives only open cells, which no waiver rests; unstated keys alone make each of the
    // rule's cells incomplete. The field is one of its sides, its `where`, a row or a `case` it
    // applies, or its `requires`: "The keys of a `when` are never unstated (item 2)". The reason
    // names the first "in this order: the fields that the steps of the rule read, in the order of
    // the steps; or for a rule with `requires`, the keys of its `requires`": for an inequality
    // this reader's own order, the part's fields before those of the parts it joins, and for a
    // rule with `requires` the order in which it names them (AMBIGUITIES.md, L3 and Q6).
    let ukeys = [], uwhy = null;
    if (part.hasUnstated) {
      charge(rule.fieldsRead);
      const refs = (rule.form === 'requires' ? rule.requiresKeys : [...rule.reads.own, ...rule.reads.joined]).filter((ref) => isUnstated(part, ref));
      if (refs.length) {
        uwhy = `${unstatedName(part, refs[0])} is unstated: its maker states none, and the rule reads it`;
        if (refs.some((ref) => valueOf(part, ref).kind === 'q')) {
          if (rule.form === 'requires' || rule.reads.loads.size === 0 || loadCases.length === 0) cell(rule.tail, 'open', uwhy);
          else {
            charge(loadCases.length);
            for (const cs of loadCases) cell(`${rule.tail}/${cs}`, 'open', uwhy);
          }
          return;
        }
        ukeys = unstatedKeys(part, refs);
      }
    }
    // Cells 4: a rule with `requires` gives one cell, proved when the condition holds for the part,
    // and settled by item 9 for a part that leaves a key it reads unstated. "The cell is marked
    // `"stated": true`, and it is not the proved cell a PASS needs (The verdict). A proved cell has
    // the `reason` `what the rule requires is stated: nothing is worked out`." The mark is put on
    // where the cells are printed, on each cell of such a rule that is proved or refuted, however
    // it came to be refuted (AMBIGUITIES.md, S3).
    if (rule.form === 'requires') {
      if (ukeys.length) incomplete(rule.tail, null, [], ukeys, uwhy);
      else if (partCond(rule.requires, part)) cell(rule.tail, 'proved', STATED_REASON);
      else cell(rule.tail, 'refuted', requiresReason(rule, part));
      return;
    }
    const settle = (cs) => {
      // Steps item 3: the weight of the rule, twice for a rule with `where`.
      charge(rule.where !== undefined ? 2 * rule.weight : rule.weight);
      const entry = cs === null ? rule.tail : `${rule.tail}/${cs}`;
      const hs = hintsFor(part.name, line.mechanism, entry);
      if (rule.where !== undefined) {
        // Cells 7: a tape that cannot be written leaves the cell open, and no waiver rests it.
        const w = tryWrite(rule, part, cs, 'where');
        if (!w.tape) { cell(entry, 'open', `the range cannot be written: ${w.why}`); return; }
        const wh = hintsFor(part.name, line.mechanism, `${entry}/where`).filter((h) => Object.hasOwn(h, 'partition'));
        if (!wh.some((h) => proves(w.tape, h.partition))) {
          // Cells 5: no `/where` cell. Inside its range a point may still refute the rule: the
          // points of the hints with the cell's entry, and none of their partitions, are tried on
          // the rule's tape inside its range, which Steps counts in place of the rule's own.
          const wi = tryWrite(rule, part, cs, 'within');
          if (!wi.tape) { cell(entry, 'open', `the tape cannot be written: ${wi.why}`); return; }
          const hp = hs.filter((h) => Object.hasOwn(h, 'point'));
          if (hp.some((h) => refutes(wi.tape, h.point))) { cell(entry, 'refuted'); return; }
          // On a waived line: the cell is waivable when a root of the range's tape has an
          // enclosure over the whole box whose lower end is above zero.
          const k = waived ? holdsNowhere(w.tape) : -1;
          if (k >= 0) cell(entry, 'open', `the rule holds only where ${rule.whereWhy[k]}, and that holds nowhere in the ranges for ${part.name}`, 'where');
          else cell(entry, 'open', `the range the rule holds in is not proved: ${hintsLeft([...wh, ...hp])}`);
          return;
        }
        cell(`${entry}/where`, 'proved');
      }
      const w = tryWrite(rule, part, cs, 'le');
      if (!w.tape) { cell(entry, 'open', `the tape cannot be written: ${w.why}`); return; }
      let state = null;
      for (const h of hs) {
        if (Object.hasOwn(h, 'partition') && proves(w.tape, h.partition)) { state = 'proved'; break; }
        if (Object.hasOwn(h, 'point') && refutes(w.tape, h.point)) { state = 'refuted'; break; }
      }
      // Cells 6: an open cell stays open on a line the card waives, whether its root is left
      // undecided or has no value at some points of the box or at all of them.
      // Cells 6: "A cell that this item proves or refutes on a tape whose root reads no input is
      // marked `"stated": true` ... Its inequality reads no quantity of the part and none of the
      // card ... A proved one has the `reason` `the inequality reads no quantity of the part or of
      // the card: nothing of the design is worked out` ... A refuted one has no reason ... This
      // tape holds no root of the `where`, so a rule whose `where` reads a quantity and whose two
      // sides are numbers has a marked cell, beside the `/where` cell of item 5." The mark goes by
      // what the root reads and not by what the tape holds (AMBIGUITIES.md, T5 and U3).
      const noInput = !rootReadsInput(w.tape, w.tape.roots[0]);
      if (state) cell(entry, state, noInput && state === 'proved' ? NO_INPUT_REASON : undefined, null, noInput);
      else cell(entry, 'open', hintsLeft(hs.filter((h) => Object.hasOwn(h, 'partition') || Object.hasOwn(h, 'point'))));
    };
    const ls = [...rule.reads.loads];
    if (!ls.length) {
      if (ukeys.length) incomplete(rule.tail, null, [], ukeys, uwhy);
      else settle(null);
      return;
    }
    // Cells 4: a card with no load case gives one cell with no case, every load it reads left
    // out; its completion gives each load in the case named by the empty text.
    if (!loadCases.length) {
      incomplete(rule.tail, '', ls, ukeys, uwhy ?? `the card puts ${noLoads(ls)} on ${part.name}, which the rule reads`);
      return;
    }
    // Steps item 2: every load case of the card times every load the rule reads.
    charge(loadCases.length * ls.length);
    for (const cs of loadCases) {
      const missing = ls.filter((l) => !putsLoad(cs, part.name, l));
      if (missing.length || ukeys.length) incomplete(`${rule.tail}/${cs}`, cs, missing, ukeys, uwhy ?? `case ${cs} puts ${noLoads(missing)} on ${part.name}, which the rule reads`);
      else settle(cs);
    }
  };

  // Reads, for the unread cells (Cells 8): by a rule that applies to the part (it answers, waived
  // or not and whether or not its line's unless holds), by a rule that applies to the part that
  // joins it, and by an unless of the lines of its type. A load is read by an expression of a rule
  // of its own part's type that applies. They are worked out under the completions of the cells
  // the waivers rest, after the last of them is rested: each key one of them names has that name,
  // and each load one gives is on its part in its case. Which rules apply does not turn on them:
  // "A rule applies to a part when it is for the part's type and it answers for the part: its
  // `when` holds (item 3)", and no completion names a key of a `when`. So the completions bear
  // only on which loads left out are on a part here, and each of those is read by the rule whose
  // cell was rested (AMBIGUITIES.md, Q5 and R2).
  const readSets = new Map(parts.map((p) => [p.name, new Set()]));
  const loadReads = new Map(parts.map((p) => [p.name, new Set()]));
  const markReads = (part, reads) => {
    for (const f of reads.own) readSets.get(part.name).add(f);
    for (const jf of reads.joined) {
      const dot = jf.indexOf('.');
      const q = part.joins.get(jf.slice(0, dot));
      if (q) readSets.get(q.name).add(jf.slice(dot + 1));
    }
  };
  // format.md, Cells 8: "A field that the part leaves unstated has no `unread` cell, read or
  // not, unless a need names it: a need of the part's own type that names the field, or a need of
  // the type of the part that joins it, which names it `PART.FIELD`." `PART` is the name that the
  // joining field's `as` gives the part, as a need writes a field of a joined part (deck.md, What
  // a type needs), so the need of a part that joins two names the field of the one it names and
  // not of the other (AMBIGUITIES.md, R1).
  const joinerOf = new Map();
  for (const j of parts) for (const [as, q] of j.joins) joinerOf.set(q.name, { part: j, as });
  const needNames = (part, field) => {
    if (part.type.needs.some((n) => n.fields.includes(field))) return true;
    const j = joinerOf.get(part.name);
    return !!j && j.part.type.needs.some((n) => n.fields.includes(`${j.as}.${field}`));
  };
  // format.md, Steps, An unstated field: "For such a part, after every cell: one step for each
  // field that a need of the part's type names, as often as the need names it." Such a part is
  // one "that leaves a field unstated, or that joins a part that does" (AMBIGUITIES.md, R3).
  const needsCharge = (part) => part.type.needs.reduce((n, need) => n + need.fields.length, 0);
  const workOutReads = () => {
    for (const part of parts) {
      for (const rule of rulesOfType.get(part.type.name) ?? []) {
        if (!answers(rule, part)) continue;
        markReads(part, rule.reads);
        for (const l of rule.reads.loads) loadReads.get(part.name).add(l);
      }
      for (const g of linesOf.get(part.type.name) ?? []) if (g.unless) markReads(part, g.unless.reads);
    }
  };
  const ruleCharge = (r) => (r.form === 'requires' ? 1 + r.whenSize + r.requiresSize : 1 + r.whenSize + r.reads.loads.size);

  try {
    for (const part of parts) {
      for (const line of linesOf.get(part.type.name) ?? []) {
        const lineRules = rulesOfLine.get(`${part.type.name}\u0000${line.mechanism}`) ?? [];
        // Steps item 1: the line and every rule of the line, in one charge, whatever the waivers.
        charge(1 + line.unlessSize + lineRules.reduce((n, r) => n + ruleCharge(r), 0));
        const w = waiverOf.get(`${part.name}\u0000${line.mechanism}`);
        const out = [];
        // The cells of items 2 and 3 that no rule gives, with an empty entry. The `why` of a deck
        // was cut when the deck was read, "and it is not cut again"; any other reason is cut here,
        // where its cell is made.
        const lineCell = (state, reason, rest = null) => out.push({ subject: part.name, mechanism: line.mechanism, entry: '', state, reason: state === 'not_applicable' ? reason : cutText(reason), rest });
        // Cells 2: "A line with an `unless` does not ask of a part where the ground of the
        // `unless` holds." `when`: one `not_applicable` cell for a part that the condition holds
        // for, and item 3 for any other; no key of a `when` is unstated, so it holds or it does
        // not. `least`: part by part, below. `loads`: "the ground was checked when the deck was
        // read, and it holds for every part of the type." `with`: "one cell for each part, in the line's place in
        // the order of the cells, and its state is settled last". "Each of these cells has an
        // empty `entry`."
        const u = line.unless;
        if (u && u.ground === 'with') {
          // Steps item 1: "its charge is 1, and it is tested. Then one step is added for each
          // line that its `with` names, with no test."
          steps += u.with.length;
          // Cells 1: "A line that is answered with other lines (item 2) is no line that a waiver
          // rests ... whether or not the card waives it". So the cell goes by the waiver's loop
          // below untouched: it is not open yet, and it is settled after the last part.
          const c = { subject: part.name, mechanism: line.mechanism, entry: '', state: null, reason: undefined, rest: null, answeredWith: u };
          withCells.push(c);
          push(c);
          continue;
        }
        if (u && u.ground === 'least') {
          // Cells 2, `least`: "It excuses the line for a part that has a value for `NAME`, and for
          // no other part. Where `NAME` is a load, a part has a value when the card has at least
          // one load case and every load case of the card puts `NAME` on the part. Where `NAME` is
          // a quantity, a part has a value unless it leaves the quantity unstated (Parts 2). For a
          // part that has a value the line is one `not_applicable` cell. For any other part it is
          // one `open` cell, which is waivable (item 1) as the cell of a line with no rule is. Its
          // `reason` is `the least of NAME would excuse it, and the card does not put NAME on PART
          // in every load case, or has none` for a load, and `the least of NAME would excuse it,
          // and PART leaves NAME unstated` for a quantity."
          // The loads are those of the card: "a load that a completion gives is no load that the
          // card puts on the part" (item 9). Steps item 1: "in a charge of its own with the limit
          // tested after it, it takes one step for each load case of the card where the `least` is
          // of a load, and one step where it is of a quantity, for every part of the type, excused
          // or not."
          const nm = u.least.name;
          charge(u.least.ofLoad ? loadCases.length : 1);
          const hasValue = u.least.ofLoad
            ? loadCases.length > 0 && loadCases.every((cs) => putsLoad(cs, part.name, nm))
            : part.values.get(nm)?.unstated !== true;
          if (hasValue) lineCell('not_applicable', u.why);
          else lineCell('open', u.least.ofLoad
            ? `the least of ${nm} would excuse it, and the card does not put ${nm} on ${part.name} in every load case, or has none`
            : `the least of ${nm} would excuse it, and ${part.name} leaves ${nm} unstated`, 'norule');
        } else if (u && (u.ground !== 'when' || partCond(u.when, part))) lineCell('not_applicable', u.why);
        else {
          const rules = lineRules.filter((r) => answers(r, part));
          if (!rules.length) lineCell('open', lineRules.length ? 'the deck has no rule for it on a part like this one' : 'the deck has no rule for it', 'norule');
          else for (const rule of rules) ruleCells(rule, part, line, out, !!w);
        }
        // Cells 1: a waiver rests each open cell of its line that is waivable: the line has no rule
        // for the part, the rule's `where` holds nowhere in the box, or a hint's completion makes
        // the rule hold and agrees with the completions of the cells rested before it. Every other
        // open cell of the line stays open, and says so. Cells 1 names no completion of a line's
        // `unless` any more: "when the rule reads an unstated key, or the case leaves out a load
        // the rule reads, and a hint names a completion of what is left out under which the rule
        // holds (item 9)" (AMBIGUITIES.md, Q4).
        for (const c of out) {
          if (w && c.state === 'open') {
            let rests = c.rest === 'norule' || c.rest === 'where';
            if (!rests && c.rest && agrees(c.rest)) { recordRested(c.rest); rests = true; c.completion = c.rest.src; }
            // Cells 1: "The kernel cuts a reason twice here ... It cuts the reason of the open
            // cell when it makes the cell, before any word is put in front. It then puts the words
            // in front and cuts the whole." and "The reason that starts `the waiver does not rest
            // this cell: ` is made and cut the same way."
            if (rests) {
              c.state = 'waived';
              c.reason = cutText(`open but for the waiver: ${c.reason ?? ''}`);
              if (!usedWaivers.includes(w)) usedWaivers.push(w);
            } else c.reason = cutText(`the waiver does not rest this cell: ${c.reason ?? ''}`);
          }
          push(c);
        }
      }
    }
    // Values that nothing reads come after every other cell, part by part: a part's fields in the
    // order of its type's fields, and then its loads in the order of their names and of their
    // cases' names. A field the part leaves unstated has none, unless a need names it: it is then
    // one open cell with the field as its entry, "in its place among the part's fields", and the
    // reason the page gives it. A load a rested completion gives is on its part in its case; a
    // key one names is still a field the part leaves unstated (AMBIGUITIES.md, R2).
    // format.md, Cells 8, gives the words of their reasons: "The reason of the first is `no rule
    // of the deck reads PART.FIELD, so nothing checks it`, and of the second `no rule of the deck
    // reads the load LOAD that case CASE puts on PART, so nothing checks it`, with `the card` in
    // place of `case CASE` when the card has no load case."
    // Cells 2, `with`: the state of a line that is answered with other lines "is settled last:
    // after every other cell of the lines of the grid is made for every part (items 2 to 7 and
    // 9), and after every waiver has rested what it rests (item 1). The cell is `not_applicable`
    // when every cell that the named lines have for the same part is `proved`, `waived` or
    // `not_applicable`: a cell entered `RULE/where` counts, and so does a cell marked `stated`.
    // Otherwise the cell is `open`, and its `reason` is `it is answered with LINE, which is not
    // settled for PART` ... `LINE` is the first line, in the order `with` lists them, that has a
    // cell for the part that is `open` or `refuted`." A line that a `with` names is never itself
    // answered with others, so every cell looked at here has its state. The cells are in their
    // places already; the cells named `unread` come after and are no cells of a line.
    if (withCells.length) {
      const unsettled = new Set();
      for (const c of cells) if (c.state === 'open' || c.state === 'refuted') unsettled.add(`${c.subject}\u0000${c.mechanism}`);
      for (const c of withCells) {
        const first = c.answeredWith.with.find((m) => unsettled.has(`${c.subject}\u0000${m}`));
        if (first === undefined) { c.state = 'not_applicable'; c.reason = c.answeredWith.why; }
        else { c.state = 'open'; c.reason = cutText(`it is answered with ${first}, which is not settled for ${c.subject}`); }
      }
    }
    for (const part of parts) if (part.hasUnstated) charge(needsCharge(part));
    workOutReads();
    for (const part of parts) {
      for (const f of part.type.fields) {
        if (f.kind === 'j') continue;
        if (part.values.get(f.name)?.unstated) {
          if (needNames(part, f.name)) push({ subject: part.name, mechanism: 'unread', entry: f.name, state: 'open', reason: cutText(`${part.name}.${f.name} is unstated: its maker states none, and a need names it`) });
          continue;
        }
        if (!readSets.get(part.name).has(f.name)) push({ subject: part.name, mechanism: 'unread', entry: f.name, state: 'open', reason: cutText(`no rule of the deck reads ${part.name}.${f.name}, so nothing checks it`) });
      }
      const mine = new Map();
      for (const [l, m] of loadsOn.get(part.name) ?? []) mine.set(l, new Set(m.keys()));
      for (const [l, s] of restedPuts.get(part.name) ?? []) {
        if (!mine.has(l)) mine.set(l, new Set());
        for (const cs of s) mine.get(l).add(cs);
      }
      for (const l of [...mine.keys()].sort(nameCmp)) {
        if (loadReads.get(part.name).has(l)) continue;
        for (const cs of [...mine.get(l)].sort(nameCmp)) {
          push({ subject: part.name, mechanism: 'unread', entry: `${l}/${cs}`, state: 'open', reason: cutText(`no rule of the deck reads the load ${l} that ${loadCases.length ? `case ${cs}` : 'the card'} puts on ${part.name}, so nothing checks it`) });
        }
      }
    }
    // Steps item 5: what a rule reads. For each part 1, and for each rule of its type what item 1
    // charges for it and one for each field it reads.
    for (const part of parts) {
      let n = 1;
      for (const r of rulesOfType.get(part.type.name) ?? []) n += ruleCharge(r) + r.fieldsRead;
      charge(n);
    }
    // The finished list holds no key twice (format.md, Cells).
    if (cellKeys.size !== cells.length) throw new LimitErr('two cells have one subject, mechanism and entry');
  } catch (e) {
    if (!(e instanceof LimitErr)) throw e;
    find('design', 'parts', e.message, 'limits');
    return ill();
  }

  const counts = zeroCounts();
  for (const c of cells) counts[c.state]++;
  // format.md, The verdict: a cell whose entry ends in `/where` proves a rule's range and not the
  // rule, and is not the one proved cell that a PASS needs. "Nor is the cell of a rule with
  // `requires`, which the kernel marks `"stated": true` ... A design whose only proved cells are of
  // ranges or of stated keys is UNKNOWN." So a PASS needs a cell that is proved by working
  // something out: the proved cell of a rule with an inequality.
  // Now, format.md, The verdict: "A cell is worked out when all three of these hold, and by
  // nothing else: its state is `proved`, it is not marked `"stated": true`, and its entry does not
  // end in `/where`. The words of a reason and of a rule decide nothing here." A cell is marked
  // when it is of a rule with `requires`, whatever its state, or when item 6 proved or refuted it
  // on a tape with no input.
  const isStated = (c) => c.requires === true || c.noInput === true;
  const provedRule = cells.some((c) => c.state === 'proved' && !isStated(c) && !c.entry.endsWith('/where'));
  // format.md, The verdict: "With `--rules` a cell has a reason when it is open, waived or not
  // applicable, when it is a refuted cell of a rule with `requires`, and when it is a proved cell
  // marked `stated`. Any other proved or refuted cell has none."
  const hasReason = (c) => c.state === 'open' || c.state === 'waived' || c.state === 'not_applicable'
    || (c.state === 'refuted' && c.requires === true) || (c.state === 'proved' && isStated(c));
  // format.md, The room of the reasons: three rooms of 500,000 bytes, "one for each of three kinds
  // of cell": the cells that are refuted, the cells that are not applicable, and "Every other
  // cell: open, waived and proved". "The kernel goes through the finished cells in their
  // order, after the last cell is made, with the three rooms full. A cell with no reason takes
  // nothing. A cell with a reason takes the bytes its reason prints in, as cut, from the room of
  // its kind, when they fit in what is left of that room. The first reason that does not fit is
  // replaced by `past what the verdict prints of reasons`, and so is every later reason of that
  // kind, whatever its length: that room is then at nothing. The words that replace a reason are
  // not counted against either room."
  const room = { refuted: REASON_ROOM, na: REASON_ROOM, other: REASON_ROOM };
  const shut = { refuted: false, na: false, other: false };
  const printedReason = new Map();
  for (const c of cells) {
    if (!hasReason(c)) continue;
    const kind = c.state === 'refuted' ? 'refuted' : c.state === 'not_applicable' ? 'na' : 'other';
    const text = c.reason ?? '';
    const b = printedBytes(text);
    if (!shut[kind] && b <= room[kind]) { room[kind] -= b; printedReason.set(c, text); }
    else { shut[kind] = true; room[kind] = 0; printedReason.set(c, PAST_ROOM); }
  }
  let verdict, code;
  if (counts.refuted) { verdict = 'FAIL'; code = 1; }
  else if (counts.open || !provedRule) { verdict = 'UNKNOWN'; code = 2; }
  else { verdict = 'PASS'; code = 0; }
  let ignored = 0;
  for (const [k, hs] of hints) if (!usedHints.has(k)) ignored += hs.length;
  const out = {
    verdict,
    findings: [],
    counts,
    ignored_hints: ignored,
    waived: usedWaivers.map((w) => ({ subject: w.subject, mechanism: w.mechanism, by: w.by, reason: w.reason })),
    cells: cells.map((c) => {
      const o = { subject: c.subject, mechanism: c.mechanism, entry: c.entry, claimed: c.claimed, state: c.state };
      // format.md, The verdict: "A cell that is marked `stated` has `"stated": true` (items 4 and
      // 6): every cell of a rule with `requires`, and a cell that a tape with no input proves or
      // refutes. No other cell has the key, and it is never `false`." The reason of a cell that is
      // not applicable is the `why` of its line's `unless`, cut once, when the deck was read.
      if (isStated(c)) o.stated = true;
      if (printedReason.has(c)) o.reason = printedReason.get(c);
      // format.md, The verdict: a waived cell that rests on a completion has it, as its hint in
      // proofs.json writes it, with both lists (AMBIGUITIES.md, M4) and with the unit of each
      // load's value after the value.
      if (c.state === 'waived' && c.completion) o.completion = JSON.parse(JSON.stringify(c.completion));
      return o;
    }),
  };
  if (opts.explain) { out.deck_steps = deckStepCount; out.steps = steps; }
  return { out, code };
}

// ============================================================ command line

const USAGE = 'usage: node verify.mjs --card FILE --design FILE --deck FILE [--rules FILE] [--proofs FILE] [--explain]';

function readText(path) {
  let buf;
  try { buf = readFileSync(path); } catch { return null; }
  if (buf.length >= 3 && buf[0] === 0xef && buf[1] === 0xbb && buf[2] === 0xbf) return '\u0000BOM';
  try { return new TextDecoder('utf-8', { fatal: true }).decode(buf); } catch { return '\u0000UTF8'; }
}

export function run(argv) {
  const flags = { '--card': 'card', '--design': 'design', '--deck': 'deck', '--rules': 'rules', '--proofs': 'proofs' };
  const paths = {};
  let explain = false;
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--explain') { explain = true; continue; }
    const k = flags[a];
    if (!k || paths[k] !== undefined || i + 1 >= argv.length) return { usage: true };
    paths[k] = argv[++i];
  }
  if (!paths.card || !paths.design || !paths.deck) return { usage: true };
  const texts = {};
  for (const k of Object.keys(paths)) texts[k] = readText(paths[k]);
  const bad = {};
  for (const k of Object.keys(texts)) {
    if (texts[k] === '\u0000BOM') { bad[k] = 'the file begins with a byte order mark'; texts[k] = null; }
    else if (texts[k] === '\u0000UTF8') { bad[k] = 'the file is not UTF-8'; texts[k] = null; }
  }
  const res = verifyTexts(texts, { explain });
  if (res.out && res.out.verdict === 'ILL-FORMED') {
    for (const f of res.out.findings) if (bad[f.file] && f.why === 'the file cannot be read') f.why = bad[f.file];
  }
  return res;
}

function main() {
  const res = run(process.argv.slice(2));
  if (res.usage) { process.stderr.write(USAGE + '\n'); process.exit(64); }
  if (res.code === 64) { process.stderr.write((res.message || USAGE) + '\n'); process.exit(64); }
  process.stdout.write(printVerdict(res.out) + '\n');
  process.exitCode = res.code;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try { main(); } catch (e) { process.stderr.write(`internal error: ${e && e.stack ? e.stack : e}\n`); process.exit(70); }
}
