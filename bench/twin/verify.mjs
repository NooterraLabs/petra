#!/usr/bin/env node
// verify.mjs: an independent kernel for a design whose parts are of a deck's types.
// Written from format.md and deck.md alone. Exact rational interval arithmetic on BigInt.
//
//   node verify.mjs --card F --design F --deck F --rules F [--proofs F] [--explain]
//
// Prints one JSON object {verdict, findings, cells} and exits 0 PASS, 1 FAIL, 2 UNKNOWN,
// 3 ILL-FORMED, 64 for a command line it cannot read. --explain adds a reason to each cell,
// the counts and the number of ignored hints.

import { readFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

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

// A number alone of a deck: digits with an optional sign, then a decimal part or a denominator.
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
// A file names a dimension, and two names are one dimension when their exponents are equal (moment and energy).
const sameDim = (name, dim) => { const d = parseDim(name); return d !== null && deq(d, dim); };
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

const IN = R(127n, 5000n);
const LBF = qmul(R(45359237n, 100000000n), R(980665n, 100000n));
const KIP = qmul(LBF, R(1000n));
const FT = qmul(IN, R(12n));
const PSI = qdiv(LBF, qmul(IN, IN));
const U = (f, dim) => ({ f, dim: BASE_DIMS[dim] });
const r10 = (e) => (e >= 0 ? R(10n ** BigInt(e)) : R(1n, 10n ** BigInt(-e)));
export const UNITS = Object.assign(Object.create(null), {
  '%': U(R(1n, 100n), 'dimensionless'),
  m: U(Q1, 'length'), mm: U(r10(-3), 'length'), um: U(r10(-6), 'length'), cm: U(r10(-2), 'length'),
  km: U(r10(3), 'length'), inch: U(IN, 'length'), ft: U(FT, 'length'),
  mm2: U(r10(-6), 'area'), m2: U(Q1, 'area'), inch2: U(qmul(IN, IN), 'area'),
  N: U(Q1, 'force'), kN: U(r10(3), 'force'), MN: U(r10(6), 'force'), lbf: U(LBF, 'force'),
  kip: U(KIP, 'force'), kips: U(KIP, 'force'),
  Pa: U(Q1, 'stress'), kPa: U(r10(3), 'stress'), MPa: U(r10(6), 'stress'), GPa: U(r10(9), 'stress'),
  psi: U(PSI, 'stress'), ksi: U(qmul(PSI, R(1000n)), 'stress'),
  uA: U(r10(-6), 'current'), mA: U(r10(-3), 'current'), A: U(Q1, 'current'), kA: U(r10(3), 'current'),
  V: U(Q1, 'voltage'), kV: U(r10(3), 'voltage'),
  ohm: U(Q1, 'resistance'), mohm: U(r10(-3), 'resistance'), kohm: U(r10(3), 'resistance'),
  Mohm: U(r10(6), 'resistance'),
  mW: U(r10(-3), 'power'), W: U(Q1, 'power'),
  J: U(Q1, 'energy'), Nm: U(Q1, 'energy'), kip_in: U(qmul(KIP, IN), 'energy'), kip_ft: U(qmul(KIP, FT), 'energy'),
  s: U(Q1, 'time'), ms: U(r10(-3), 'time'),
  degC: U(Q1, 'temperature'),
  g: U(r10(-3), 'mass'), kg: U(Q1, 'mass'),
  A2s: { f: Q1, dim: dmul(dmul(BASE_DIMS.current, BASE_DIMS.current), BASE_DIMS.time) },
});

// A quantity of a deck: `0.75 inch`, `3/4 inch`, `1 1/8 inch`, `29,000 ksi`, or a number alone.
// Returns {v (SI), dim, hasUnit} or null.
export function parseQuantity(s) {
  if (typeof s !== 'string' || s.length > MAXLEN) return null;
  const m = /^([+-]?)([0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.([0-9]+)|\/([0-9]+)| ([0-9]+)\/([0-9]+))?(?: ?([A-Za-z%][A-Za-z0-9_]*))?$/.exec(s);
  if (!m) return null;
  const [, sign, ip, dec, den, mn, md, unit] = m;
  const hasComma = ip.includes(',');
  const ints = ip.replace(/,/g, '');
  let v;
  if (dec !== undefined) v = R(BigInt(ints + dec), 10n ** BigInt(dec.length));
  else if (den !== undefined) {
    if (BigInt(den) === 0n) return null;
    v = R(BigInt(ints), BigInt(den));
  } else if (mn !== undefined) {
    if (BigInt(md) === 0n || unit === undefined) return null;
    v = qadd(R(BigInt(ints)), R(BigInt(mn), BigInt(md)));
  } else v = R(BigInt(ints));
  if (sign === '-') v = qneg(v);
  if (unit === undefined) {
    if (hasComma) return null;
    return { v, dim: DL, hasUnit: false };
  }
  const u = UNITS[unit];
  if (!u) return null;
  return { v: qmul(v, u.f), dim: u.dim, hasUnit: true };
}
// A quantity that must have the dimension `dim`; a bare zero is the zero of any dimension.
function quantityOf(s, dim) {
  const q = parseQuantity(s);
  if (!q) return null;
  if (deq(q.dim, dim)) return q.v;
  if (!q.hasUnit && q.v.n === 0n) return q.v;
  return null;
}

// ============================================================ JSON

class JsonErr extends Error {}
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
  function str() {
    i++;
    let out = '';
    let start = i;
    for (;;) {
      if (i >= n) err('unterminated string');
      const c = text.charCodeAt(i);
      if (c === 34) { out += text.slice(start, i); i++; return out; }
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
      for (;;) {
        ws();
        if (text[i] !== '"') err('expected a key');
        const k = str();
        ws();
        if (text[i] !== ':') err('expected :');
        i++;
        const v = val(depth + 1);
        if (Object.hasOwn(obj, k)) err(`the key ${JSON.stringify(k)} appears twice`);
        obj[k] = v;
        ws();
        if (text[i] === ',') { i++; continue; }
        if (text[i] === '}') { i++; return obj; }
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

// Returns ev(i) -> [lo, hi] or null (no value on the box), memoized and lazy.
export function evaluator(tape, box) {
  const memo = new Array(tape.nodes.length);
  const ev = (i) => {
    const m = memo[i];
    if (m !== undefined) return m;
    const nd = tape.nodes[i];
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
        let lo = Q0, hi = Q0, ok = true;
        for (const j of nd[1]) {
          const v = ev(j);
          if (!v) { ok = false; break; }
          lo = qadd(lo, v[0]); hi = qadd(hi, v[1]);
        }
        r = ok ? [lo, hi] : null;
        break;
      }
      case 'mul': {
        let acc = [Q1, Q1];
        for (const j of nd[1]) {
          const v = ev(j);
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
          const v = ev(j);
          if (!v) { ok = false; break; }
          if (!acc) acc = v;
          else if (nd[0] === 'min') acc = [qmin(acc[0], v[0]), qmin(acc[1], v[1])];
          else acc = [qmax(acc[0], v[0]), qmax(acc[1], v[1])];
        }
        r = ok ? acc : null;
        break;
      }
      case 'neg': { const v = ev(nd[1]); r = v ? [qneg(v[1]), qneg(v[0])] : null; break; }
      case 'abs': {
        const v = ev(nd[1]);
        if (!v) break;
        if (v[0].n >= 0n) r = v;
        else if (v[1].n <= 0n) r = [qneg(v[1]), qneg(v[0])];
        else r = [Q0, qmax(qneg(v[0]), v[1])];
        break;
      }
      case 'sqrt': {
        const v = ev(nd[1]);
        if (!v || v[0].n < 0n) break;
        r = [sqrtEnc(v[0])[0], sqrtEnc(v[1])[1]];
        break;
      }
      case 'ln': {
        const v = ev(nd[1]);
        if (!v || v[0].n <= 0n) break;
        r = [lnEnc(v[0])[0], lnEnc(v[1])[1]];
        break;
      }
      case 'exp': {
        const v = ev(nd[1]);
        if (!v || qcmp(qabs(v[0]), EXP_LIMIT) > 0 || qcmp(qabs(v[1]), EXP_LIMIT) > 0) break;
        if (v[1].n > 0n && Number(v[1].n / v[1].d) * 1.4427 > BITS_LIMIT) break;
        r = [expEnc(v[0])[0], expEnc(v[1])[1]];
        break;
      }
      case 'div': {
        const a = ev(nd[1]);
        if (!a) break;
        const b = ev(nd[2]);
        if (!b) break;
        r = idiv(a, b);
        break;
      }
      case 'pow': {
        const v = ev(nd[1]);
        if (!v) break;
        const k = nd[2];
        if (k >= 0) r = ipow(v, k);
        else {
          const p = ipow(v, -k);
          r = p ? idiv([Q1, Q1], p) : null;
        }
        break;
      }
      case 'pick': r = evalPick(nd[1], ev); break;
      default: r = null;
    }
    if (r && (tooBig(r[0]) || tooBig(r[1]))) r = null;
    memo[i] = r;
    return r;
  };
  return ev;
}

function evalPick(cases, ev) {
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
  for (const k of compared) if (!ev(k)) return null;
  const plist = [...pairs.values()];
  const pidx = new Map(plist.map(([a, b], k) => [`${a},${b}`, k]));
  const opts = plist.map(([a, b]) => {
    const A = ev(a), B = ev(b);
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
  const firsts = new Set();
  for (let w = 0; w < ways; w++) {
    let x = w;
    for (let k = 0; k < plist.length; k++) { choice[k] = x % opts[k].length; x = Math.floor(x / opts[k].length); }
    let f = -1;
    for (let ci = 0; ci < cases.length; ci++) if (holds(cases[ci][0])) { f = ci; break; }
    if (f < 0) return null;
    firsts.add(f);
  }
  let lo = null, hi = null;
  for (const f of [...firsts].sort((a, b) => a - b)) {
    const v = ev(cases[f][1]);
    if (!v) return null;
    lo = lo === null ? v[0] : qmin(lo, v[0]);
    hi = hi === null ? v[1] : qmax(hi, v[1]);
  }
  return [lo, hi];
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
  if (a === undefined) return;
  checkKeys(a, ['standard', 'clause', 'equation', 'table', 'page'], [], `${what}.anchor`);
  for (const k of Object.keys(a)) if (!isStr(a[k])) throw DE(`${what}.anchor.${k} is not a text`);
}
function checkName(s, what) {
  if (!isStr(s) || !NAME_RE.test(s)) throw DE(`${what} ${short(s)} is not a name of letters, digits and _`);
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
      if (!parseNumberAlone(args[0])) throw DE(`${short(args[0])} is not a number`);
      const u = UNITS[args[1]];
      if (!u) throw DE(`${short(args[1])} is not a unit`);
      return { dim: u.dim, depth: 2 };
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
      return { dim, depth: 1 + Math.max(...rs.map((r) => r.depth)) };
    }
    case 'sub': case 'div': {
      if (args.length !== 2) throw DE(`${op} takes two arguments`);
      const a = checkExpr(args[0], sc), b = checkExpr(args[1], sc);
      if (op === 'sub' && !deq(a.dim, b.dim)) throw DE('the two sides of sub are of different dimensions');
      return { dim: op === 'sub' ? a.dim : ddiv(a.dim, b.dim), depth: 1 + Math.max(a.depth, b.depth) };
    }
    case 'neg': case 'abs': { const a = one(); return { dim: a.dim, depth: 1 + a.depth }; }
    case 'sqrt': { const a = one(); return { dim: dpow(a.dim, R(1n, 2n)), depth: 1 + a.depth }; }
    case 'exp': case 'ln': {
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
    case 'and': case 'or':
      if (args.length < 1) throw DE(`${c[0]} has no member`);
      return 1 + Math.max(...args.map((x) => checkRowCond(x, sc)));
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
    return { by: s.by, kind: 'bands', bands, closed, count: bands.length };
  }
  if (Object.hasOwn(s, 'closed')) throw DE(`table.${which} has closed and no bands`);
  if (!Array.isArray(s.at) || s.at.length === 0) throw DE(`table.${which}.at is not a list of values`);
  const at = s.at.map((v, i) => {
    const q = quantityOf(v, inp.dim);
    if (!q) throw DE(`value ${i + 1} of table.${which}.at, ${short(v)}, is not a quantity of the input's dimension`);
    return q;
  });
  return { by: s.by, kind: 'at', at, count: at.length };
}

function loadTable(t, row) {
  checkKeys(t, ['down', 'across', 'cells', 'unit', 'rises', 'falls'], ['down', 'cells'], 'table');
  let unit = null;
  if (Object.hasOwn(t, 'unit')) {
    if (!isStr(t.unit) || !UNITS[t.unit]) throw DE(`table.unit ${short(t.unit)} is not a unit`);
    unit = UNITS[t.unit];
  }
  for (const k of ['rises', 'falls']) {
    if (Object.hasOwn(t, k) && (!Array.isArray(t[k]) || !t[k].every(isStr))) throw DE(`table.${k} is not a list of names`);
  }
  const down = loadSide(t.down, row, 'down');
  const across = Object.hasOwn(t, 'across') ? loadSide(t.across, row, 'across') : null;
  const cell = (c, where) => {
    if (c === null) return null;
    const q = parseQuantity(c);
    if (!q) throw DE(`cell ${where} ${short(c)} is not a value`);
    let v = q.v, dim = q.dim;
    if (!q.hasUnit && unit) { v = qmul(v, unit.f); dim = unit.dim; }
    if (!deq(dim, row.gives.dim) && !(q.v.n === 0n && !q.hasUnit)) throw DE(`cell ${where} is not of the row's dimension`);
    return v;
  };
  if (!Array.isArray(t.cells) || t.cells.length !== down.count) throw DE(`table.cells does not have one line for each of the ${down.count} places of down`);
  const cells = t.cells.map((line, i) => {
    if (!across) return cell(line, `${i + 1}`);
    if (!Array.isArray(line) || line.length !== across.count) throw DE(`line ${i + 1} of table.cells does not have one cell for each of the ${across.count} places across`);
    return line.map((c, j) => cell(c, `${i + 1},${j + 1}`));
  });
  return { down, across, cells };
}

function loadRow(r, rowsSoFar) {
  checkKeys(r, ['id', 'anchor', 'gives', 'takes', 'is', 'cases', 'table', 'jumps'], ['id', 'gives', 'takes'], 'the row');
  if (!isStr(r.id) || r.id.length === 0) throw DE('the row has no id');
  if (rowsSoFar.has(r.id)) throw DE(`two rows have the id ${r.id}`);
  checkAnchor(r.anchor, 'the row');
  checkKeys(r.gives, ['name', 'dim', 'what'], ['name', 'dim'], 'gives');
  if (!isStr(r.gives.name)) throw DE('gives.name is not a text');
  optText(r.gives, 'what', 'gives');
  const gdim = parseDim(r.gives.dim);
  if (!gdim) throw DE(`gives.dim ${short(r.gives.dim)} is not a dimension`);
  const row = { id: r.id, gives: { name: r.gives.name, dim: gdim }, inputs: new Map(), kind: null };
  if (!Array.isArray(r.takes)) throw DE('takes is not a list');
  for (const t of r.takes) {
    if (!isObj(t)) throw DE('an input is not an object');
    if (Object.hasOwn(t, 'one_of')) {
      checkKeys(t, ['name', 'one_of', 'what'], ['name', 'one_of'], 'a key input');
      checkName(t.name, 'the input');
      optText(t, 'what', 'the input');
      if (!Array.isArray(t.one_of) || t.one_of.length === 0 || !t.one_of.every(isStr) || new Set(t.one_of).size !== t.one_of.length) throw DE(`the key ${t.name} has no list of distinct names`);
      if (row.inputs.has(t.name)) throw DE(`the row takes ${t.name} twice`);
      row.inputs.set(t.name, { kind: 'k', names: t.one_of.slice() });
    } else {
      checkKeys(t, ['name', 'dim', 'what', 'range'], ['name', 'dim'], 'an input');
      checkName(t.name, 'the input');
      if (t.name === 'pi') throw DE('an input is named pi');
      optText(t, 'what', 'the input');
      const dim = parseDim(t.dim);
      if (!dim) throw DE(`the input ${t.name} has the dimension ${short(t.dim)}, which is not one`);
      if (Object.hasOwn(t, 'range')) {
        if (!Array.isArray(t.range) || t.range.length !== 2) throw DE(`the range of ${t.name} is not two values`);
        const lo = quantityOf(t.range[0], dim), hi = quantityOf(t.range[1], dim);
        if (!lo || !hi) throw DE(`the range of ${t.name} is not two quantities of its dimension`);
        if (qcmp(lo, hi) > 0) throw DE(`the range of ${t.name} has its lower value second`);
      }
      if (row.inputs.has(t.name)) throw DE(`the row takes ${t.name} twice`);
      row.inputs.set(t.name, { kind: 'q', dim });
    }
  }
  const kinds = ['is', 'cases', 'table'].filter((k) => Object.hasOwn(r, k));
  if (kinds.length !== 1) throw DE('the row has not exactly one of is, cases and table');
  row.kind = kinds[0];
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
    for (const j of r.jumps) {
      checkKeys(j, ['cases', 'why'], ['cases'], 'a jump');
      if (!Array.isArray(j.cases) || !j.cases.every((x) => typeof x === 'bigint')) throw DE('a jump has no list of case numbers');
      optText(j, 'why', 'a jump');
    }
  }
  return row;
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
  if (c[0] === 'and' || c[0] === 'or' || c[0] === 'not') return 1 + Math.max(...c.slice(1).map((x) => condDepth(x, leaf)));
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
  checkKeys(t, ['type', 'what', 'fields', 'loads'], ['type', 'fields'], 'the type');
  checkName(t.type, 'the type');
  if (seenTypes.has(t.type)) throw DE(`two types are named ${t.type}`);
  optText(t, 'what', 'the type');
  const T = { name: t.type, fields: [], fieldMap: new Map(), loads: new Map(), joins: [], asMap: new Map() };
  if (!Array.isArray(t.fields)) throw DE('fields is not a list');
  for (const f of t.fields) {
    checkKeys(f, ['name', 'what', 'dim', 'one_of', 'type', 'as', 'signed', 'whole', 'least'], ['name'], 'a field');
    checkName(f.name, 'the field');
    optText(f, 'what', `the field ${f.name}`);
    if (T.fieldMap.has(f.name)) throw DE(`two fields are named ${f.name}`);
    const kinds = ['dim', 'one_of', 'type'].filter((k) => Object.hasOwn(f, k));
    if (kinds.length !== 1) throw DE(`the field ${f.name} has not exactly one of dim, one_of and type`);
    let F;
    if (kinds[0] === 'dim') {
      if (Object.hasOwn(f, 'as')) throw DE(`the quantity ${f.name} has as`);
      const dim = parseDim(f.dim);
      if (!dim) throw DE(`the field ${f.name} has the dimension ${short(f.dim)}, which is not one`);
      for (const k of ['signed', 'whole']) if (Object.hasOwn(f, k) && typeof f[k] !== 'boolean') throw DE(`${k} of ${f.name} is not true or false`);
      let least = null;
      if (Object.hasOwn(f, 'least')) {
        least = quantityOf(f.least, dim);
        if (!least) throw DE(`least of ${f.name} is not a quantity of its dimension`);
      }
      F = { name: f.name, kind: 'q', dimName: f.dim, dim, signed: f.signed === true, whole: f.whole === true, least };
    } else if (kinds[0] === 'one_of') {
      for (const k of ['signed', 'whole', 'least', 'as']) if (Object.hasOwn(f, k)) throw DE(`the key ${f.name} has ${k}`);
      if (!Array.isArray(f.one_of) || f.one_of.length === 0 || !f.one_of.every(isStr) || new Set(f.one_of).size !== f.one_of.length) throw DE(`the key ${f.name} has no list of distinct names`);
      F = { name: f.name, kind: 'k', names: f.one_of.slice() };
    } else {
      for (const k of ['signed', 'whole', 'least']) if (Object.hasOwn(f, k)) throw DE(`the field ${f.name} that joins parts has ${k}`);
      if (!isStr(f.type)) throw DE(`the field ${f.name} names no type`);
      if (!Array.isArray(f.as) || f.as.length === 0) throw DE(`the field ${f.name} has no as`);
      for (const a of f.as) {
        checkName(a, 'a joined part');
        if (T.asMap.has(a)) throw DE(`two joined parts are called ${a}`);
        T.asMap.set(a, { field: f.name, type: f.type });
      }
      F = { name: f.name, kind: 'j', type: f.type, as: f.as.slice() };
      T.joins.push(F);
    }
    T.fields.push(F);
    T.fieldMap.set(f.name, F);
  }
  if (Object.hasOwn(t, 'loads')) {
    if (!Array.isArray(t.loads)) throw DE('loads is not a list');
    for (const l of t.loads) {
      checkKeys(l, ['name', 'dim', 'what', 'least'], ['name', 'dim'], 'a load');
      checkName(l.name, 'the load');
      optText(l, 'what', `the load ${l.name}`);
      if (T.loads.has(l.name)) throw DE(`two loads are named ${l.name}`);
      const dim = parseDim(l.dim);
      if (!dim) throw DE(`the load ${l.name} has the dimension ${short(l.dim)}, which is not one`);
      let least = null;
      if (Object.hasOwn(l, 'least')) {
        least = quantityOf(l.least, dim);
        if (!least) throw DE(`least of the load ${l.name} is not a quantity of its dimension`);
      }
      T.loads.set(l.name, { name: l.name, dimName: l.dim, dim, least });
    }
  }
  return T;
}

// A key field of a type, by FIELD or AS.FIELD: {names, own|joined}.
function keyField(s, T, types) {
  if (!isStr(s)) return null;
  const f = T.fieldMap.get(s);
  if (f) return f.kind === 'k' ? { names: f.names, own: s } : null;
  const dot = s.indexOf('.');
  if (dot <= 0) return null;
  const j = T.asMap.get(s.slice(0, dot));
  if (!j) return null;
  const f2 = types.get(j.type)?.fieldMap.get(s.slice(dot + 1));
  return f2 && f2.kind === 'k' ? { names: f2.names, joined: s } : null;
}

function addRead(reads, kf) {
  if (kf.own) reads.own.add(kf.own);
  else reads.joined.add(kf.joined);
}

// A condition on a part: is, loaded, and, or, not.
function checkPartCond(c, T, types, reads) {
  if (!Array.isArray(c) || c.length === 0 || !isStr(c[0])) throw DE(`${short(c)} is not a condition on a part`);
  switch (c[0]) {
    case 'is': {
      if (c.length !== 3) throw DE('is takes a field and a name');
      const kf = keyField(c[1], T, types);
      if (!kf) throw DE(`${short(c[1])} is not a key field of ${T.name}`);
      if (!isStr(c[2]) || !kf.names.includes(c[2])) throw DE(`${short(c[2])} is not a name of ${c[1]}`);
      addRead(reads, kf);
      return;
    }
    case 'loaded':
      if (c.length !== 2 || !isStr(c[1]) || !T.loads.has(c[1])) throw DE(`${short(c[1])} is not a load of ${T.name}`);
      return;
    case 'and': case 'or':
      if (c.length < 2) throw DE(`${c[0]} has no member`);
      for (const x of c.slice(1)) checkPartCond(x, T, types, reads);
      return;
    case 'not':
      if (c.length !== 2) throw DE('not takes one condition');
      checkPartCond(c[1], T, types, reads);
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
  checkKeys(r, ['id', 'type', 'mechanism', 'anchor', 'says', 'le', 'let', 'where', 'when'], ['id', 'type', 'mechanism', 'le'], 'the rule');
  if (!isStr(r.id) || r.id.length === 0) throw DE('the rule has no id');
  checkAnchor(r.anchor, 'the rule');
  optText(r, 'says', 'the rule');
  const T = deck.types.get(r.type);
  if (!T) throw DE(`the rule's type ${short(r.type)} is not a type of the deck`);
  const line = deck.grid.find((g) => g.type === r.type && g.mechanism === r.mechanism);
  if (!line) throw DE(`the rule answers ${short(r.mechanism)}, which is no line of the grid for ${r.type}`);
  if (line.unless && line.unless.when === undefined) throw DE(`the rule answers ${r.mechanism}, which cannot arise`);
  const lets = Object.hasOwn(r, 'let') ? r.let : Object.create(null);
  if (!isObj(lets)) throw DE('let is not an object');
  for (const k of Object.keys(lets)) {
    checkName(k, 'the let name');
    if (T.fieldMap.has(k)) throw DE(`the let name ${k} is a field's name`);
  }
  const letMemo = new Map();
  const letBusy = new Set();
  const scopeFor = (reads) => ({
    name: (e) => {
      if (Object.hasOwn(lets, e)) {
        const info = letInfo(e);
        mergeReads(reads, info.reads);
        return { dim: info.dim, depth: 1 + info.depth };
      }
      const f = T.fieldMap.get(e);
      if (f) {
        if (f.kind !== 'q') throw DE(`${e} is not a quantity field of ${T.name}`);
        reads.own.add(e);
        return { dim: f.dim, depth: 1 };
      }
      const dot = e.indexOf('.');
      if (dot > 0) {
        const j = T.asMap.get(e.slice(0, dot));
        const f2 = j && deck.types.get(j.type)?.fieldMap.get(e.slice(dot + 1));
        if (f2 && f2.kind === 'q') { reads.joined.add(e); return { dim: f2.dim, depth: 1 }; }
      }
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
          checkKeyBinding(v, inp, nm, row, reads);
          bd.set(nm, 1);
        }
      }
      const depth = 1 + rowDepth(row, bd);
      if (depth > MAX_EXPR_DEPTH) throw DE('an expression nests more than 1,024 deep');
      return { dim: row.gives.dim, depth };
    },
  });
  const checkKeyBinding = (v, inp, nm, row, reads) => {
    if (isStr(v)) {
      const kf = keyField(v, T, deck.types);
      if (!kf) throw DE(`the key ${nm} of ${row.id} is bound to ${short(v)}, which is not a key field`);
      if (!kf.names.every((x) => inp.names.includes(x))) throw DE(`the key field ${v} has a name that the key ${nm} of ${row.id} has not`);
      addRead(reads, kf);
      return;
    }
    if (Array.isArray(v) && v[0] === 'key') {
      if (v.length !== 2 || !isStr(v[1]) || !inp.names.includes(v[1])) throw DE(`${short(v)} is not a name of the key ${nm} of ${row.id}`);
      return;
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
      addRead(reads, kf);
      return;
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
  if (!Array.isArray(r.le) || r.le.length !== 2) throw DE('le is not two expressions');
  const a = checkExpr(r.le[0], sc), b = checkExpr(r.le[1], sc);
  if (!deq(a.dim, b.dim)) throw DE('the two sides of le are of different dimensions');
  let where;
  if (Object.hasOwn(r, 'where')) {
    if (!Array.isArray(r.where)) throw DE('where is not a list');
    where = r.where.map((w, i) => {
      checkKeys(w, ['le', 'why'], ['le'], `where ${i + 1}`);
      optText(w, 'why', `where ${i + 1}`);
      if (!Array.isArray(w.le) || w.le.length !== 2) throw DE(`where ${i + 1} is not two expressions`);
      const x = checkExpr(w.le[0], sc), y = checkExpr(w.le[1], sc);
      if (!deq(x.dim, y.dim)) throw DE(`the two sides of where ${i + 1} are of different dimensions`);
      return w.le;
    });
  }
  let when;
  if (Object.hasOwn(r, 'when')) {
    checkPartCond(r.when, T, deck.types, ruleReads);
    when = r.when;
  }
  const slash = r.id.lastIndexOf('/');
  return {
    id: r.id, tail: slash >= 0 ? r.id.slice(slash + 1) : r.id, type: r.type, mechanism: r.mechanism,
    le: r.le, lets, where, when, reads: ruleReads,
  };
}

export function loadDeck(D, find) {
  const F = (item, why) => find('rules', item, why);
  const errs0 = [];
  const top = (fn, item) => {
    try { return fn(); } catch (e) { if (e instanceof DeckErr) { F(item, e.message); errs0.push(1); return undefined; } throw e; }
  };
  top(() => {
    checkKeys(D, ['format', 'name', 'about', 'rows', 'types', 'grid', 'rules'], ['format', 'rows', 'types', 'grid', 'rules'], 'the deck');
    optText(D, 'name', 'the deck');
    optText(D, 'about', 'the deck');
    for (const k of ['rows', 'types', 'grid', 'rules']) if (!Array.isArray(D[k])) throw DE(`${k} is not a list`);
  }, '');
  if (errs0.length) return null;
  const deck = { rows: new Map(), types: new Map(), grid: [], rules: [] };
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
  const mechs = new Set();
  D.grid.forEach((g, i) => {
    const item = `grid[${i}]${isObj(g) && isStr(g.mechanism) ? ' ' + g.mechanism : ''}`;
    const line = top(() => {
      checkKeys(g, ['type', 'mechanism', 'what', 'anchor', 'unless'], ['type', 'mechanism'], 'the line');
      const T = deck.types.get(g.type);
      if (!T) throw DE(`the line's type ${short(g.type)} is not a type of the deck`);
      if (!isStr(g.mechanism) || g.mechanism.length === 0) throw DE('the line names no mechanism');
      if (mechs.has(g.mechanism)) throw DE(`two lines are named ${g.mechanism}`);
      optText(g, 'what', 'the line');
      checkAnchor(g.anchor, 'the line');
      let unless;
      if (Object.hasOwn(g, 'unless')) {
        checkKeys(g.unless, ['why', 'when'], [], 'unless');
        optText(g.unless, 'why', 'unless');
        const reads = newReads();
        if (Object.hasOwn(g.unless, 'when')) checkPartCond(g.unless.when, T, deck.types, reads);
        unless = { when: g.unless.when, why: g.unless.why, reads };
      }
      return { type: g.type, mechanism: g.mechanism, unless };
    }, item);
    if (line) { deck.grid.push(line); mechs.add(line.mechanism); }
  });
  const ids = new Set();
  D.rules.forEach((r, i) => {
    const item = `rules[${i}]${isObj(r) && isStr(r.id) ? ' ' + r.id : ''}`;
    const rule = top(() => {
      const x = loadRule(r, deck);
      if (ids.has(x.id)) throw DE(`two rules have the id ${x.id}`);
      return x;
    }, item);
    if (rule) { deck.rules.push(rule); ids.add(rule.id); }
  });
  return errs0.length ? null : deck;
}

// ============================================================ the kernel

const STATES = ['proved', 'refuted', 'not_applicable', 'waived', 'open'];
const nameCmp = (a, b) => {
  const x = [...a].map((c) => c.codePointAt(0)), y = [...b].map((c) => c.codePointAt(0));
  for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] - y[i];
  return x.length - y.length;
};

export function verifyTexts(texts, opts = {}) {
  const findings = [];
  const find = (file, item, why) => findings.push({ file, item, why });
  const ill = () => ({ out: { verdict: 'ILL-FORMED', findings, cells: [] }, code: 3 });

  // ---------------------------------------------------------------- shape
  const docs = {};
  const formats = { card: 'petra-card/0', design: 'petra-design/0', deck: 'petra-deck/0', rules: 'petra-rules/0', proofs: 'petra-proofs/0' };
  for (const k of Object.keys(formats)) {
    if (texts[k] === undefined) continue;
    if (texts[k] === null) { find(k, '', 'the file cannot be read'); continue; }
    try {
      docs[k] = parseJson(texts[k]);
    } catch (e) {
      if (e instanceof JsonErr) { find(k, '', `not JSON the kernel reads: ${e.message}`); continue; }
      throw e;
    }
    if (!isObj(docs[k]) || docs[k].format !== formats[k]) { find(k, 'format', `format is not ${formats[k]}`); delete docs[k]; }
  }
  if (findings.length) return ill();
  const { card: cardJ, design: designJ, deck: deckJ, rules: rulesJ, proofs: proofsJ } = docs;

  const num = (file, item, v) => {
    const q = parseFileNumber(v);
    if (!q) find(file, item, `${short(v)} is not a number`);
    return q;
  };
  const range = (file, item, o) => {
    const lo = num(file, `${item}.lo`, o.lo), hi = num(file, `${item}.hi`, o.hi);
    if (lo && hi && qcmp(lo, hi) > 0) { find(file, item, 'lo is above hi'); return null; }
    return lo && hi ? [lo, hi] : null;
  };
  const list = (file, o, k, required) => {
    if (!Object.hasOwn(o, k)) { if (required) find(file, k, `has no ${k}`); return []; }
    if (!Array.isArray(o[k])) { find(file, k, `${k} is not a list`); return []; }
    return o[k];
  };

  // card
  if (!isStr(cardJ.name)) find('card', 'name', 'the card has no name');
  const inputs = [];
  list('card', cardJ, 'inputs', false).forEach((x, i) => {
    const item = `inputs[${i}]${isObj(x) && isStr(x.name) ? ' ' + x.name : ''}`;
    if (!isObj(x)) { find('card', item, 'not an object'); return; }
    if (!isStr(x.name)) find('card', item, 'the input has no name');
    if (!isStr(x.dim)) find('card', item, 'the input has no dim');
    for (const k of ['case', 'on', 'field']) if (Object.hasOwn(x, k) && !isStr(x[k])) find('card', item, `${k} is not a text`);
    const rg = range('card', item, x);
    inputs.push({ item, name: x.name, dim: x.dim, lo: rg?.[0], hi: rg?.[1], by: x.by, case: x.case, on: x.on, field: x.field });
  });
  const waivers = [];
  list('card', cardJ, 'waivers', false).forEach((w, i) => {
    const item = `waivers[${i}]`;
    if (!isObj(w) || !isStr(w.subject) || !isStr(w.mechanism)) { find('card', item, 'a waiver has no subject or mechanism'); return; }
    waivers.push({ item, subject: w.subject, mechanism: w.mechanism, by: w.by });
  });
  const claims = list('card', cardJ, 'claims', false);
  const tests = list('card', cardJ, 'tests', false);
  const pclaims = list('card', cardJ, 'probability_claims', false);

  // design
  if (!isStr(designJ.name)) find('design', 'name', 'the design has no name');
  if (!isStr(designJ.card)) find('design', 'card', 'the design names no card');
  const quantities = [];
  list('design', designJ, 'quantities', false).forEach((x, i) => {
    const item = `quantities[${i}]`;
    if (!isObj(x)) { find('design', item, 'not an object'); return; }
    const rg = range('design', item, x);
    quantities.push({ item, role: x.role, lo: rg?.[0] });
  });
  const params = list('design', designJ, 'params', false);
  params.forEach((x, i) => { if (isObj(x)) range('design', `params[${i}]`, x); });
  const hasParts = Object.hasOwn(designJ, 'parts');
  const partsJ = hasParts ? list('design', designJ, 'parts', true) : [];
  partsJ.forEach((p, i) => {
    if (!isObj(p) || !Array.isArray(p.lines)) return;
    p.lines.forEach((l, j) => {
      if (!isObj(l) || !Array.isArray(l.args)) return;
      l.args.forEach((a, k) => {
        if (isObj(a) && isObj(a.number)) range('design', `parts[${i}].lines[${j}].args[${k}].number`, a.number);
      });
    });
  });

  // deck.json
  let sizeDomain = null;
  const inputDomains = new Map();
  if (!isObj(deckJ.domains) || !isObj(deckJ.domains.size) || !isObj(deckJ.domains.input)) find('deck', 'domains', 'the deck has no domains.size and domains.input');
  else {
    const s = deckJ.domains.size;
    const m = num('deck', 'domains.size.min', s.min);
    if (typeof s.strict !== 'boolean') find('deck', 'domains.size.strict', 'strict is not true or false');
    sizeDomain = m ? { min: m, strict: s.strict === true } : null;
    for (const k of Object.keys(deckJ.domains.input)) {
      const d = deckJ.domains.input[k];
      if (!isObj(d)) continue; // `about` and other texts
      const dm = num('deck', `domains.input.${k}.min`, d.min);
      if (typeof d.strict !== 'boolean') find('deck', `domains.input.${k}.strict`, 'strict is not true or false');
      if (dm) inputDomains.set(k, { min: dm, strict: d.strict === true });
    }
  }
  list('deck', deckJ, 'constants', false).forEach((c, i) => { if (isObj(c)) range('deck', `constants[${i}]`, c); else find('deck', `constants[${i}]`, 'not an object'); });

  // proofs.json
  const hints = new Map();
  const hintKey = (s, m, e) => `${s}\u0000${m}\u0000${e}`;
  if (proofsJ) {
    list('proofs', proofsJ, 'cells', true).forEach((c, i) => {
      const item = `cells[${i}]`;
      if (!isObj(c) || !isStr(c.subject) || !isStr(c.mechanism) || !isStr(c.entry) || !isStr(c.state)) { find('proofs', item, 'a cell lacks its subject, mechanism, entry or state'); return; }
      if (!STATES.includes(c.state)) { find('proofs', item, `${short(c.state)} is not a state`); return; }
      let bad = false;
      const walk = (P, d) => {
        if (!isObj(P) || d > 200) return;
        if (Object.hasOwn(P, 'at') && !parseFileNumber(P.at)) { find('proofs', item, `the partition splits at ${short(P.at)}, which is not a number`); bad = true; }
        walk(P.below, d + 1);
        walk(P.above, d + 1);
      };
      if (Object.hasOwn(c, 'partition')) walk(c.partition, 0);
      if (isObj(c.point)) for (const k of Object.keys(c.point)) if (!parseFileNumber(c.point[k])) { find('proofs', item, `the point gives ${k} the value ${short(c.point[k])}, which is not a number`); bad = true; }
      if (bad) return;
      const key = hintKey(c.subject, c.mechanism, c.entry);
      if (!hints.has(key)) hints.set(key, []);
      hints.get(key).push(c);
    });
  }
  if (findings.length) return ill();

  // ---------------------------------------------------------------- types
  const allowedDesignKeys = ['format', 'name', 'card', 'quantities', 'params', 'parts'];
  for (const k of Object.keys(designJ)) if (!allowedDesignKeys.includes(k)) find('design', k, `the design has the key ${k}`);
  for (const q of quantities) {
    if (q.role === 'size' && q.lo && sizeDomain) {
      const c = qcmp(q.lo, sizeDomain.min);
      if (c < 0 || (c === 0 && sizeDomain.strict)) find('design', q.item, `a size is ${q.lo}, at or below the least a size may take`);
    }
  }
  for (const x of inputs) {
    const d = isStr(x.dim) ? inputDomains.get(x.dim) : undefined;
    if (d && x.lo) {
      const c = qcmp(x.lo, d.min);
      if (c < 0 || (c === 0 && d.strict)) find('card', x.item, `lo is ${x.lo}, below the floor of ${x.dim}`);
    }
    if (!isStr(x.by) || x.by.length === 0) find('card', x.item, 'the input names no by: nobody signed it');
  }
  for (const w of waivers) if (!isStr(w.by) || w.by.length === 0) find('card', w.item, 'the waiver names no by');
  if (!hasParts) return { out: null, code: 64, message: 'a design with no parts is outside what this kernel reads' };
  if (!rulesJ) find('design', 'parts', 'a design with parts comes with --rules');
  if (findings.length) return ill();

  // ---------------------------------------------------------------- the deck of rules
  const deck = loadDeck(rulesJ, find);
  if (!deck || findings.length) return ill();

  // ---------------------------------------------------------------- parts
  const DN = designJ.name, CN = cardJ.name;
  const inputByName = new Map();
  for (const x of inputs) {
    if (inputByName.has(x.name)) find('card', x.item, `two inputs are named ${x.name}`);
    else inputByName.set(x.name, x);
    const n = ['case', 'on', 'field'].filter((k) => x[k] !== undefined).length;
    x.isLoad = n === 3;
    x.isGiven = n === 0;
    if (!x.isLoad && !x.isGiven) find('card', x.item, 'the input has some but not all of case, on and field');
  }
  const parts = [];
  const partByName = new Map();
  const givensRead = new Set();
  partsJ.forEach((p, pi) => {
    const item = `parts[${pi}]${isObj(p) && isStr(p.name) ? ' ' + p.name : ''}`;
    const PF = (why) => find('design', item, why);
    if (!isObj(p) || !isStr(p.name) || !isStr(p.type) || !Array.isArray(p.lines)) { PF('a part has no name, type or lines'); return; }
    if (partByName.has(p.name)) { PF(`two parts are named ${p.name}`); return; }
    const T = deck.types.get(p.type);
    if (!T) { PF(`${p.type} is not a type of the deck`); return; }
    const part = { name: p.name, type: T, values: new Map(), joinWords: new Map(), joins: new Map(), item };
    partByName.set(p.name, part);
    parts.push(part);
    const seen = new Set();
    p.lines.forEach((l, li) => {
      const LF = (why) => PF(`line ${li + 1}: ${why}`);
      if (!isObj(l) || !isStr(l.field) || !Array.isArray(l.args)) { LF('the line has no field or args'); return; }
      const f = T.fieldMap.get(l.field);
      if (!f) { LF(`${l.field} is not a field of ${T.name}`); return; }
      if (seen.has(l.field)) { LF(`the part gives ${l.field} twice`); return; }
      seen.add(l.field);
      const args = l.args;
      const argKind = (a) => (isObj(a) && Object.keys(a).length === 1 ? Object.keys(a)[0] : null);
      if (f.kind === 'q') {
        if (args.length !== 1) { LF(`${f.name} takes one number or one given`); return; }
        const a = args[0], k = argKind(a);
        let lo, hi, label;
        if (k === 'number' && isObj(a.number)) {
          if (f.signed) { LF(`${f.name} is signed: only the card states it`); return; }
          if (!sameDim(a.number.dim, f.dim)) { LF(`${f.name} is of ${f.dimName}, and the number is of ${short(a.number.dim)}`); return; }
          lo = parseFileNumber(a.number.lo); hi = parseFileNumber(a.number.hi);
          if (!lo || !hi) return; // reported under shape
          if (f.whole && (qcmp(lo, hi) !== 0 || lo.d !== 1n)) { LF(`${f.name} is a whole number`); return; }
          label = `dsg:${DN}.${p.name}.${f.name}`;
        } else if (k === 'given' && isStr(a.given)) {
          if (f.whole) { LF(`${f.name} is a whole number that the design writes`); return; }
          if (a.given !== `${p.name}.${f.name}`) { LF(`the given for ${f.name} is named ${a.given}, not ${p.name}.${f.name}`); return; }
          const x = inputByName.get(a.given);
          if (!x) { LF(`the card has no input ${a.given}`); return; }
          if (!x.isGiven) { LF(`the input ${a.given} is a load`); return; }
          if (!sameDim(x.dim, f.dim)) { LF(`${f.name} is of ${f.dimName}, and the card's ${a.given} is of ${short(x.dim)}`); return; }
          givensRead.add(a.given);
          lo = x.lo; hi = x.hi;
          if (!lo || !hi) return;
          label = `in:${CN}.${x.name}`;
        } else { LF(`${f.name} takes one number or one given, not ${short(a)}`); return; }
        if (lo.n <= 0n) { LF(`${f.name} is ${lo}, not more than zero`); return; }
        if (f.least && qcmp(lo, f.least) < 0) { LF(`${f.name} is ${lo}, below its least ${f.least}`); return; }
        part.values.set(f.name, { kind: 'q', label, lo, hi });
      } else if (f.kind === 'k') {
        if (args.length !== 1) { LF(`${f.name} takes one word or one text`); return; }
        const a = args[0], k = argKind(a);
        const v = k === 'word' ? a.word : k === 'text' ? a.text : undefined;
        if (!isStr(v)) { LF(`${f.name} takes one word or one text, not ${short(a)}`); return; }
        if (!f.names.includes(v)) { LF(`${short(v)} is not one of the names of ${f.name}`); return; }
        part.values.set(f.name, { kind: 'k', value: v });
      } else {
        if (args.length !== f.as.length) { LF(`${f.name} takes ${f.as.length} words`); return; }
        const words = [];
        for (const a of args) {
          if (argKind(a) !== 'word' || !isStr(a.word)) { LF(`${f.name} takes words that name parts, not ${short(a)}`); return; }
          words.push(a.word);
        }
        part.joinWords.set(f.name, words);
      }
    });
    for (const f of T.fields) if (!seen.has(f.name)) PF(`the part has no line for ${f.name}`);
  });
  const joinedBy = new Map();
  for (const part of parts) {
    for (const f of part.type.joins) {
      const words = part.joinWords.get(f.name);
      if (!words) continue;
      if (new Set(words).size !== words.length) { find('design', part.item, `${f.name} names one part twice`); continue; }
      words.forEach((w, i) => {
        const q = partByName.get(w);
        if (!q) { find('design', part.item, `${f.name} names ${w}, which is no part`); return; }
        if (q.type.name !== f.type) { find('design', part.item, `${f.name} names ${w}, which is not a ${f.type}`); return; }
        if (joinedBy.has(w)) { find('design', part.item, `${w} is joined more than once`); return; }
        joinedBy.set(w, part.name);
        part.joins.set(f.as[i], q);
      });
    }
  }
  const loadKeys = new Set();
  for (const x of inputs) {
    if (x.isLoad) {
      const part = partByName.get(x.on);
      if (!part) { find('card', x.item, `the load is on ${short(x.on)}, which is no part`); continue; }
      const L = part.type.loads.get(x.field);
      if (!L) { find('card', x.item, `${short(x.field)} is not a load of ${part.type.name}`); continue; }
      if (!sameDim(x.dim, L.dim)) { find('card', x.item, `the load ${L.name} is of ${L.dimName}, and the input is of ${short(x.dim)}`); continue; }
      if (L.least && x.lo && qcmp(x.lo, L.least) < 0) find('card', x.item, `the load is below its least ${L.least}`);
      const k = `${x.case}\u0000${x.on}\u0000${x.field}`;
      if (loadKeys.has(k)) find('card', x.item, `the case ${x.case} puts ${x.field} on ${x.on} twice`);
      loadKeys.add(k);
    } else if (x.isGiven && isStr(x.name) && !givensRead.has(x.name)) {
      find('card', x.item, `no part reads the given ${x.name}`);
    }
  }
  for (const w of waivers) {
    const part = partByName.get(w.subject);
    if (!part) { find('card', w.item, `the waiver names ${w.subject}, which is no part`); continue; }
    if (!deck.grid.some((g) => g.type === part.type.name && g.mechanism === w.mechanism)) find('card', w.item, `the grid asks no ${w.mechanism} of a ${part.type.name}`);
  }
  if (claims.length) find('card', 'claims', 'a card for a deck of rules has no claim');
  if (tests.length) find('card', 'tests', 'a card for a deck of rules has no tests record');
  if (pclaims.length) find('card', 'probability_claims', 'a card for a deck of rules has no probability claim');
  if (params.length) find('design', 'params', 'a design of a deck\'s types has no param');
  if (findings.length) return ill();

  // ---------------------------------------------------------------- cells
  const loadInputs = inputs.filter((x) => x.isLoad);
  const loadInput = (cs, partName, field) => loadInputs.find((x) => x.case === cs && x.on === partName && x.field === field);
  const keyValue = (part, ref) => {
    const dot = ref.indexOf('.');
    if (dot < 0 || part.type.fieldMap.has(ref)) return part.values.get(ref).value;
    return part.joins.get(ref.slice(0, dot)).values.get(ref.slice(dot + 1)).value;
  };
  const partCond = (c, part) => {
    switch (c[0]) {
      case 'is': return keyValue(part, c[1]) === c[2];
      case 'loaded': return loadInputs.some((x) => x.on === part.name && x.field === c[1]);
      case 'and': return c.slice(1).every((x) => partCond(x, part));
      case 'or': return c.slice(1).some((x) => partCond(x, part));
      case 'not': return !partCond(c[1], part);
    }
    return false;
  };

  // A tape from a rule for a part (and a case), with the roots of le or of where.
  const writeTape = (rule, part, cs, which) => {
    const t = new Tape();
    const letNodes = new Map();
    const quantityNode = (name) => {
      let v;
      if (part.type.fieldMap.has(name)) v = part.values.get(name);
      else {
        const dot = name.indexOf('.');
        v = part.joins.get(name.slice(0, dot)).values.get(name.slice(dot + 1));
      }
      return t.input(v.label, v.lo, v.hi);
    };
    const op = (e, sub) => {
      switch (e[0]) {
        case 'add': case 'mul': case 'min': case 'max': return t.add([e[0], e.slice(1).map(sub)]);
        case 'sub': { const a = sub(e[1]), b = sub(e[2]); return t.add(['add', [a, t.add(['neg', b])]]); }
        case 'div': { const a = sub(e[1]), b = sub(e[2]); return t.add(['div', a, b]); }
        case 'neg': case 'abs': case 'sqrt': case 'exp': case 'ln': return t.add([e[0], sub(e[1])]);
        case 'pow': {
          const b = sub(e[1]);
          const x = e[2];
          if (isStr(x) && looksNumeric(x)) {
            const n = parseNumberAlone(x);
            const twice = qmul(n, R(2n));
            if (twice.d === 1n) {
              const neg = n.n < 0n;
              const tw = neg ? -twice.n : twice.n;
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
      if (e[0] === 'q') return t.c(qmul(parseNumberAlone(e[1]), UNITS[e[2]].f));
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
    const resolveKey = (b) => {
      if (isStr(b)) return keyValue(part, b);
      if (b[0] === 'key') return b[1];
      const v = keyValue(part, b[1]);
      if (!Object.hasOwn(b[2], v)) throw new CannotWrite(`the table has no line for ${b[1]} ${v}`);
      return b[2][v];
    };
    const placeCond = (side, i, x) => {
      if (side.kind === 'at') { const v = t.c(side.at[i]); return ['and', [['le', x, v], ['le', v, x]]]; }
      const [lo, hi] = side.bands[i];
      const L = t.c(lo);
      if (side.closed === 'upper') { const c1 = ['lt', L, x]; return hi === null ? c1 : ['and', [c1, ['le', x, t.c(hi)]]]; }
      const c1 = ['le', L, x];
      return hi === null ? c1 : ['and', [c1, ['lt', x, t.c(hi)]]];
    };
    const table = (row, qin, key) => {
      const T = row.table;
      const sel = (side) => (side.kind === 'key' ? { fixed: side.names.indexOf(key(side.by)) } : { side, x: qin(side.by) });
      const d = sel(T.down);
      const a = T.across ? sel(T.across) : null;
      const cellNode = (i, j) => {
        const v = a ? T.cells[i][j] : T.cells[i];
        return v === null ? null : t.c(v);
      };
      const pickOver = (s, at) => {
        const cases = [];
        for (let i = 0; i < s.side.count; i++) {
          const node = at(i);
          if (node !== null) cases.push([placeCond(s.side, i, s.x), node]);
        }
        return cases.length ? t.add(['pick', cases]) : null;
      };
      let node;
      if (!a) node = d.fixed !== undefined ? cellNode(d.fixed) : pickOver(d, (i) => cellNode(i));
      else if (d.fixed !== undefined && a.fixed !== undefined) node = cellNode(d.fixed, a.fixed);
      else if (d.fixed !== undefined) node = pickOver(a, (j) => cellNode(d.fixed, j));
      else if (a.fixed !== undefined) node = pickOver(d, (i) => cellNode(i, a.fixed));
      else node = pickOver(d, (i) => pickOver(a, (j) => cellNode(i, j)));
      if (node === null) throw new CannotWrite(`every cell ${row.id} could read is empty`);
      return node;
    };
    const applyRow = (row, binding) => {
      const cache = new Map();
      const qin = (nm) => {
        let i = cache.get(nm);
        if (i === undefined) { i = expr(binding[nm]); cache.set(nm, i); }
        return i;
      };
      const key = (nm) => resolveKey(binding[nm]);
      if (row.kind === 'is') return rowExpr(row.is, qin);
      if (row.kind === 'cases') {
        const cases = row.cases.map((cs2) => {
          const c = cs2.when === undefined ? null : rowCond(cs2.when, qin);
          return [c, rowExpr(cs2.is, qin)];
        });
        return t.add(['pick', cases]);
      }
      return table(row, qin, key);
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
        case 'q': return t.c(qmul(parseNumberAlone(e[1]), UNITS[e[2]].f));
        case 'load': {
          const x = loadInput(cs, part.name, e[1]);
          return t.input(`in:${CN}.${x.name}`, x.lo, x.hi);
        }
        case 'row': return applyRow(deck.rows.get(e[1]), e[2]);
      }
      return op(e, expr);
    };
    const root = (pair) => { const l = expr(pair[0]), r = expr(pair[1]); return t.add(['add', [l, t.add(['neg', r])]]); };
    if (which === 'le') t.roots.push(root(rule.le));
    else for (const w of rule.where) t.roots.push(root(w));
    return t;
  };

  const usedHints = new Set();
  const cells = [];
  const unread = [];
  const push = (subject, mechanism, entry, state, reason) => cells.push({ subject, mechanism, entry, state, reason });
  const hintsFor = (s, m, e) => {
    const k = hintKey(s, m, e);
    usedHints.add(k);
    return hints.get(k) || [];
  };
  const tryWrite = (rule, part, cs, which) => {
    try { return { tape: writeTape(rule, part, cs, which) }; } catch (e) { if (e instanceof CannotWrite) return { why: e.message }; throw e; }
  };

  const ruleCells = (rule, part, line) => {
    const loads = [...rule.reads.loads];
    let caseList = [null];
    if (loads.length) {
      const mine = loadInputs.filter((x) => x.on === part.name);
      const missing = loads.find((l) => !mine.some((x) => x.field === l));
      if (missing) { push(part.name, line.mechanism, rule.tail, 'open', `the card puts no ${missing} on ${part.name}, which the rule reads`); return; }
      const names = [...new Set(mine.map((x) => x.case))].filter((c) => loads.every((l) => mine.some((x) => x.case === c && x.field === l)));
      if (!names.length) { push(part.name, line.mechanism, rule.tail, 'open', 'no case puts every load the rule reads on the part'); return; }
      caseList = names.sort(nameCmp);
    }
    for (const cs of caseList) {
      const entry = cs === null ? rule.tail : `${rule.tail}/${cs}`;
      if (rule.where !== undefined) {
        const w = tryWrite(rule, part, cs, 'where');
        let ok = false;
        const hs = hintsFor(part.name, line.mechanism, `${entry}/where`);
        if (w.tape) for (const h of hs) if (Object.hasOwn(h, 'partition') && proves(w.tape, h.partition)) { ok = true; break; }
        if (!ok) { push(part.name, line.mechanism, entry, 'open', w.tape ? 'the rule\'s range (where) is not proved' : `the range cannot be written: ${w.why}`); continue; }
        push(part.name, line.mechanism, `${entry}/where`, 'proved', 'a partition proves the range');
      }
      const w = tryWrite(rule, part, cs, 'le');
      if (!w.tape) { push(part.name, line.mechanism, entry, 'open', `the tape cannot be written: ${w.why}`); continue; }
      let state = null;
      for (const h of hintsFor(part.name, line.mechanism, entry)) {
        if (Object.hasOwn(h, 'partition') && proves(w.tape, h.partition)) { state = 'proved'; break; }
        if (Object.hasOwn(h, 'point') && refutes(w.tape, h.point)) { state = 'refuted'; break; }
      }
      if (state) push(part.name, line.mechanism, entry, state, state === 'proved' ? 'a partition proves it' : 'a point refutes it');
      else push(part.name, line.mechanism, entry, 'open', 'no hint proves or refutes it');
    }
  };

  // reads, for the unread cells
  const readSets = new Map(parts.map((p) => [p.name, new Set()]));
  const markReads = (part, reads) => {
    for (const f of reads.own) readSets.get(part.name).add(f);
    for (const jf of reads.joined) {
      const dot = jf.indexOf('.');
      const q = part.joins.get(jf.slice(0, dot));
      if (q) readSets.get(q.name).add(jf.slice(dot + 1));
    }
  };
  for (const part of parts) {
    for (const rule of deck.rules) if (rule.type === part.type.name && (rule.when === undefined || partCond(rule.when, part))) markReads(part, rule.reads);
    for (const g of deck.grid) if (g.type === part.type.name && g.unless) markReads(part, g.unless.reads);
  }

  for (const part of parts) {
    for (const line of deck.grid) {
      if (line.type !== part.type.name) continue;
      if (waivers.some((w) => w.subject === part.name && w.mechanism === line.mechanism)) {
        hintsFor(part.name, line.mechanism, '');
        push(part.name, line.mechanism, '', 'waived', 'the card waives it');
        continue;
      }
      if (line.unless && (line.unless.when === undefined || partCond(line.unless.when, part))) {
        hintsFor(part.name, line.mechanism, '');
        push(part.name, line.mechanism, '', 'not_applicable', line.unless.why ?? 'the grid says it cannot arise');
        continue;
      }
      const rules = deck.rules.filter((r) => r.type === part.type.name && r.mechanism === line.mechanism && (r.when === undefined || partCond(r.when, part)));
      if (!rules.length) {
        hintsFor(part.name, line.mechanism, '');
        push(part.name, line.mechanism, '', 'open', 'the deck has no rule for it that holds for the part');
        continue;
      }
      for (const rule of rules) ruleCells(rule, part, line);
    }
    for (const f of part.type.fields) {
      if (f.kind === 'j') continue;
      if (!readSets.get(part.name).has(f.name)) unread.push([part.name, f.name]);
    }
  }
  // Values that nothing reads come after every other cell, part by part (docs/deck.md).
  for (const [name, fieldName] of unread) {
    hintsFor(name, 'unread', fieldName);
    push(name, 'unread', fieldName, 'open', 'no rule and no line of the grid reads it');
  }

  const counts = Object.fromEntries(STATES.map((s) => [s, cells.filter((c) => c.state === s).length]));
  let verdict, code;
  if (counts.refuted) { verdict = 'FAIL'; code = 1; }
  else if (counts.open || !counts.proved) { verdict = 'UNKNOWN'; code = 2; }
  else { verdict = 'PASS'; code = 0; }
  let ignored = 0;
  for (const [k, hs] of hints) if (!usedHints.has(k)) ignored += hs.length;
  const out = {
    verdict,
    findings: [],
    cells: cells.map((c) => (opts.explain ? { ...c } : { subject: c.subject, mechanism: c.mechanism, entry: c.entry, state: c.state })),
  };
  if (opts.explain) { out.counts = counts; out.ignored_hints = ignored; }
  return { out, code };
}

// ============================================================ command line

const USAGE = 'usage: node verify.mjs --card FILE --design FILE --deck FILE --rules FILE [--proofs FILE] [--explain]';

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
  process.stdout.write(JSON.stringify(res.out, null, 1) + '\n');
  process.exitCode = res.code;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try { main(); } catch (e) { process.stderr.write(`internal error: ${e && e.stack ? e.stack : e}\n`); process.exit(70); }
}
