// Delade hjälpfunktioner för Secret Santa-sidorna.
// Länkarna innehåller vem man fått, men förvrängt med en slumpad nyckel
// så att det inte går att läsa namnet i själva länktexten.
// Allt ligger efter "#" i adressen och skickas därför aldrig till servern.
(function (global) {
  'use strict';

  function b64urlEncode(bytes) {
    let s = '';
    for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }

  function b64urlDecode(str) {
    str = str.replace(/-/g, '+').replace(/_/g, '/');
    while (str.length % 4) str += '=';
    const s = atob(str);
    const out = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) out[i] = s.charCodeAt(i);
    return out;
  }

  function scramble(data, key) {
    const out = new Uint8Array(data.length);
    let x = 0;
    for (let i = 0; i < key.length; i++) x = (x * 31 + key[i]) >>> 0;
    for (let i = 0; i < data.length; i++) {
      // enkel pseudo-slumpström (xorshift) seedad med nyckeln
      x ^= x << 13; x >>>= 0;
      x ^= x >>> 17;
      x ^= x << 5; x >>>= 0;
      out[i] = data[i] ^ key[i % key.length] ^ (x & 255);
    }
    return out;
  }

  function encode(obj) {
    const data = new TextEncoder().encode(JSON.stringify(obj));
    const key = new Uint8Array(12);
    crypto.getRandomValues(key);
    const body = scramble(data, key);
    const all = new Uint8Array(key.length + body.length);
    all.set(key, 0);
    all.set(body, key.length);
    return 'v1.' + b64urlEncode(all);
  }

  function decode(token) {
    if (!token || token.slice(0, 3) !== 'v1.') throw new Error('bad token');
    const all = b64urlDecode(token.slice(3));
    const key = all.slice(0, 12);
    const data = scramble(all.slice(12), key);
    return JSON.parse(new TextDecoder().decode(data));
  }

  function randInt(n) {
    const a = new Uint32Array(1);
    crypto.getRandomValues(a);
    return a[0] % n;
  }

  function shuffle(arr) {
    const a = arr.slice();
    for (let i = a.length - 1; i > 0; i--) {
      const j = randInt(i + 1);
      [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
  }

  // people: [{name, group}] -> Map giverIndex -> recipientIndex, eller null
  function draw(people, noMutual) {
    const n = people.length;
    for (let attempt = 0; attempt < 20000; attempt++) {
      const order = shuffle([...Array(n).keys()]);
      const taken = new Array(n).fill(false);
      const result = new Array(n).fill(-1);
      let ok = true;
      for (const g of order) {
        const options = [];
        for (let r = 0; r < n; r++) {
          if (taken[r] || r === g) continue;
          if (people[r].group === people[g].group) continue;
          if (noMutual && result[r] === g) continue;
          options.push(r);
        }
        if (!options.length) { ok = false; break; }
        const r = options[randInt(options.length)];
        result[g] = r;
        taken[r] = true;
      }
      if (ok) return result;
    }
    return null;
  }

  global.Santa = { encode, decode, draw, shuffle };
})(window);
