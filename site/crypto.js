/* Hand-written Argon2id (RFC 9106) and Fernet. No dependencies, no network.
   Everything runs on this page; a demo, not a replacement for a real library. */
(function (root) {
  'use strict';
  /* ---------- BLAKE2b (BigInt: used rarely, only at the start and the end) ---------- */
  const IV = [0x6a09e667f3bcc908n, 0xbb67ae8584caa73bn, 0x3c6ef372fe94f82bn, 0xa54ff53a5f1d36f1n,
    0x510e527fade682d1n, 0x9b05688c2b3e6c1fn, 0x1f83d9abfb41bd6bn, 0x5be0cd19137e2179n];
  const SIGMA = ['0123456789abcdef', 'ea489fd61c02b753', 'b8c052fdae367194', '7931dcbe265a40f8', '905724afe1bc683d',
    '2c6a0b834d75fe19', 'c51fed4a0763928b', 'db7ec13950f4862a', '6fe9b308c2d714a5', 'a2847615fb9e3cd0']
    .map(s => [...s].map(c => parseInt(c, 16)));
  const M64 = (1n << 64n) - 1n;
  const rr = (x, n) => ((x >> n) | (x << (64n - n))) & M64;
  function blake2b(outLen, input) {
    const h = IV.slice();
    h[0] ^= 0x01010000n ^ BigInt(outLen);
    let off = 0, t = 0n;
    do {
      const last = off + 128 >= input.length;
      const b = new Uint8Array(128);
      b.set(input.subarray(off, Math.min(off + 128, input.length)));
      t += BigInt(last ? input.length - off : 128);
      const m = [];
      for (let i = 0; i < 16; i++) {
        let w = 0n;
        for (let j = 7; j >= 0; j--) w = (w << 8n) | BigInt(b[i * 8 + j]);
        m.push(w);
      }
      const v = h.concat(IV);
      v[12] ^= t;
      if (last) v[14] ^= M64;
      const g = (a, c, e, d, x, y) => {
        v[a] = (v[a] + v[c] + x) & M64; v[d] = rr(v[d] ^ v[a], 32n);
        v[e] = (v[e] + v[d]) & M64; v[c] = rr(v[c] ^ v[e], 24n);
        v[a] = (v[a] + v[c] + y) & M64; v[d] = rr(v[d] ^ v[a], 16n);
        v[e] = (v[e] + v[d]) & M64; v[c] = rr(v[c] ^ v[e], 63n);
      };
      for (let r = 0; r < 12; r++) {
        const s = SIGMA[r % 10];
        g(0, 4, 8, 12, m[s[0]], m[s[1]]); g(1, 5, 9, 13, m[s[2]], m[s[3]]);
        g(2, 6, 10, 14, m[s[4]], m[s[5]]); g(3, 7, 11, 15, m[s[6]], m[s[7]]);
        g(0, 5, 10, 15, m[s[8]], m[s[9]]); g(1, 6, 11, 12, m[s[10]], m[s[11]]);
        g(2, 7, 8, 13, m[s[12]], m[s[13]]); g(3, 4, 9, 14, m[s[14]], m[s[15]]);
      }
      for (let i = 0; i < 8; i++) h[i] ^= v[i] ^ v[i + 8];
      off += 128;
    } while (off < input.length);
    const out = new Uint8Array(outLen);
    for (let i = 0; i < outLen; i++) out[i] = Number((h[i >> 3] >> BigInt(8 * (i & 7))) & 255n);
    return out;
  }
  const le32 = n => new Uint8Array([n & 255, (n >>> 8) & 255, (n >>> 16) & 255, (n >>> 24) & 255]);
  function cat(...a) {
    const out = new Uint8Array(a.reduce((s, x) => s + x.length, 0));
    let o = 0;
    for (const x of a) { out.set(x, o); o += x.length; }
    return out;
  }
  function hPrime(T, X) {
    const inp = cat(le32(T), X);
    if (T <= 64) return blake2b(T, inp);
    const out = new Uint8Array(T), r = Math.ceil(T / 32) - 2;
    let v = blake2b(64, inp);
    out.set(v.subarray(0, 32), 0);
    for (let i = 1; i < r; i++) { v = blake2b(64, v); out.set(v.subarray(0, 32), i * 32); }
    out.set(blake2b(T - 32 * r, v), 32 * r);
    return out;
  }

  /* ---------- Argon2 compression: 64-bit words as pairs of 32-bit ones ---------- */
  const R = new Uint32Array(256), Q = new Uint32Array(256);
  function fm(x, y) { // x = x + y + 2 * lo(x) * lo(y)
    const a = R[x], b = R[y];
    const al = a & 0xffff, ah = a >>> 16, bl = b & 0xffff, bh = b >>> 16;
    const t = al * bl, m1 = ah * bl + Math.floor(t / 65536), m2 = al * bh + (m1 % 65536);
    const phi = ah * bh + Math.floor(m1 / 65536) + Math.floor(m2 / 65536);
    const plo = Math.imul(a, b) >>> 0;
    const lo = a + b + ((plo << 1) >>> 0);
    R[x + 1] = R[x + 1] + R[y + 1] + (phi * 2 + (plo >>> 31)) + Math.floor(lo / 4294967296);
    R[x] = lo;
  }
  function gb(a, b, c, d) {
    let l, h;
    fm(a, b);
    l = R[d] ^ R[a]; h = R[d + 1] ^ R[a + 1]; R[d] = h; R[d + 1] = l;                    // >>> 32
    fm(c, d);
    l = R[b] ^ R[c]; h = R[b + 1] ^ R[c + 1]; R[b] = (l >>> 24) | (h << 8); R[b + 1] = (h >>> 24) | (l << 8);
    fm(a, b);
    l = R[d] ^ R[a]; h = R[d + 1] ^ R[a + 1]; R[d] = (l >>> 16) | (h << 16); R[d + 1] = (h >>> 16) | (l << 16);
    fm(c, d);
    l = R[b] ^ R[c]; h = R[b + 1] ^ R[c + 1]; R[b] = (l << 1) | (h >>> 31); R[b + 1] = (h << 1) | (l >>> 31);
  }
  function P(i0, i1, i2, i3, i4, i5, i6, i7, i8, i9, ia, ib, ic, id, ie, if_) {
    gb(i0, i4, i8, ic); gb(i1, i5, i9, id); gb(i2, i6, ia, ie); gb(i3, i7, ib, if_);
    gb(i0, i5, ia, if_); gb(i1, i6, ib, ic); gb(i2, i7, i8, id); gb(i3, i4, i9, ie);
  }
  function fill(X, xo, Y, yo, Z, zo, withXor) {
    for (let i = 0; i < 256; i++) { R[i] = X[xo + i] ^ Y[yo + i]; Q[i] = R[i]; }
    if (withXor) for (let i = 0; i < 256; i++) Q[i] ^= Z[zo + i];
    for (let i = 0; i < 8; i++) {
      const o = i * 32;
      P(o, o + 2, o + 4, o + 6, o + 8, o + 10, o + 12, o + 14, o + 16, o + 18, o + 20, o + 22, o + 24, o + 26, o + 28, o + 30);
    }
    for (let i = 0; i < 8; i++) {
      const o = i * 4;
      P(o, o + 2, o + 32, o + 34, o + 64, o + 66, o + 96, o + 98, o + 128, o + 130, o + 160, o + 162, o + 192, o + 194, o + 224, o + 226);
    }
    for (let i = 0; i < 256; i++) Z[zo + i] = Q[i] ^ R[i];
  }

  /* ---------- Argon2id. With lanes = 1 it can also record what happened to each block ---------- */
  function argon2id(o) {
    const pw = o.password, salt = o.salt, t = o.t, p = o.p || 1, tagLen = o.len || 32;
    const secret = o.secret || new Uint8Array(0), ad = o.ad || new Uint8Array(0);
    const mp = 4 * p * Math.floor(o.m / (4 * p)), q = mp / p, seg = q / 4;
    const H0 = blake2b(64, cat(le32(p), le32(tagLen), le32(o.m), le32(t), le32(0x13), le32(2),
      le32(pw.length), pw, le32(salt.length), salt, le32(secret.length), secret, le32(ad.length), ad));
    const B = new Uint32Array(256 * mp);
    const trace = o.trace ? { q, t, refs: new Uint16Array(q * t).fill(65535), shade: new Uint8Array(q * t) } : null;
    const shade = (pass, idx, off) => { if (trace) trace.shade[pass * q + idx] = B[off] & 255; };
    for (let l = 0; l < p; l++) for (let j = 0; j < 2; j++) {
      const b = hPrime(1024, cat(H0, le32(j), le32(l))), off = (l * q + j) * 256;
      const dv = new DataView(b.buffer);
      for (let i = 0; i < 256; i++) B[off + i] = dv.getUint32(i * 4, true);
      shade(0, j, off);
    }
    const zero = new Uint32Array(256), input = new Uint32Array(256), addr = new Uint32Array(256);
    const nextAddr = () => {
      input[12]++;
      fill(zero, 0, input, 0, addr, 0, false);
      fill(zero, 0, addr, 0, addr, 0, false);
    };
    for (let pass = 0; pass < t; pass++) for (let s = 0; s < 4; s++) for (let l = 0; l < p; l++) {
      const independent = pass === 0 && s < 2;
      if (independent) {
        input.fill(0);
        input[0] = pass; input[2] = l; input[4] = s; input[6] = mp; input[8] = t; input[10] = 2;
      }
      let start = 0;
      if (pass === 0 && s === 0) { start = 2; if (independent) nextAddr(); }
      for (let i = start; i < seg; i++) {
        const idx = s * seg + i, cur = (l * q + idx) * 256;
        const prev = (l * q + (idx === 0 ? q - 1 : idx - 1)) * 256;
        let j1, j2;
        if (independent) {
          if (i % 128 === 0) nextAddr();
          j1 = addr[(i % 128) * 2]; j2 = addr[(i % 128) * 2 + 1];
        } else { j1 = B[prev]; j2 = B[prev + 1]; }
        let rl = j2 % p;
        if (pass === 0 && s === 0) rl = l;
        const same = rl === l;
        let area;
        if (pass === 0) area = s === 0 ? i - 1 : same ? s * seg + i - 1 : s * seg - (i === 0 ? 1 : 0);
        else area = same ? q - seg + i - 1 : q - seg - (i === 0 ? 1 : 0);
        // relative position: area - 1 - (area * (j1^2 >> 32) >> 32)
        const jl = j1 & 0xffff, jh = j1 >>> 16;
        const m0 = jl * jl, m1 = 2 * jl * jh + Math.floor(m0 / 65536);
        const x = jh * jh + Math.floor(m1 / 65536);   // hi32(j1 * j1)
        const al = area & 0xffff, ah = area >>> 16, xl = x & 0xffff, xh = Math.floor(x / 65536);
        const n0 = al * xl, n1 = ah * xl + Math.floor(n0 / 65536), n2 = al * xh + (n1 % 65536);
        const y = ah * xh + Math.floor(n1 / 65536) + Math.floor(n2 / 65536);
        const z = area - 1 - y;
        const begin = pass === 0 ? 0 : (s === 3 ? 0 : (s + 1) * seg);
        const ref = (begin + z) % q;
        fill(B, prev, B, (rl * q + ref) * 256, B, cur, pass > 0);
        if (trace) { trace.refs[pass * q + idx] = ref; shade(pass, idx, cur); }
      }
    }
    const C = new Uint32Array(256);
    for (let l = 0; l < p; l++) { const off = (l * q + q - 1) * 256; for (let i = 0; i < 256; i++) C[i] ^= B[off + i]; }
    const cb = new Uint8Array(1024), cv = new DataView(cb.buffer);
    for (let i = 0; i < 256; i++) cv.setUint32(i * 4, C[i], true);
    const tag = hPrime(tagLen, cb);
    return trace ? { tag, trace } : { tag };
  }

  /* ---------- Fernet (spec: github.com/fernet/spec) through the browser's own WebCrypto ---------- */
  const subtle = () => (root.crypto && root.crypto.subtle) || null;
  const b64u = b => {
    let s = '';
    for (const x of b) s += String.fromCharCode(x);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_');
  };
  const unb64u = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0));
  const hmacKey = k => subtle().importKey('raw', k, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign', 'verify']);
  const aesKey = k => subtle().importKey('raw', k, 'AES-CBC', false, ['encrypt', 'decrypt']);
  async function fernetEncrypt(key, plain, ts) {
    const iv = root.crypto.getRandomValues(new Uint8Array(16));
    const ct = new Uint8Array(await subtle().encrypt({ name: 'AES-CBC', iv }, await aesKey(key.subarray(16, 32)), plain));
    const head = new Uint8Array(9);
    head[0] = 0x80;
    new DataView(head.buffer).setUint32(5, ts, false);
    const body = cat(head, iv, ct);
    const mac = new Uint8Array(await subtle().sign('HMAC', await hmacKey(key.subarray(0, 16)), body));
    return cat(body, mac);
  }
  async function fernetDecrypt(key, tok) { // null means the signature did not match
    const body = tok.subarray(0, tok.length - 32), mac = tok.subarray(tok.length - 32);
    if (!await subtle().verify('HMAC', await hmacKey(key.subarray(0, 16)), mac, body)) return null;
    return new Uint8Array(await subtle().decrypt({ name: 'AES-CBC', iv: tok.subarray(9, 25) },
      await aesKey(key.subarray(16, 32)), tok.subarray(25, tok.length - 32)));
  }
  root.WKCrypto = { blake2b, argon2id, fernetEncrypt, fernetDecrypt, b64u, unb64u, hasSubtle: () => !!subtle() };
})(globalThis);
