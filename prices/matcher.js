// Browser/Node port of prices/matcher.py. Rules and names come from prices/data/matcher.json
// (written by prices/ingest.py --matcher-data), so only the algorithm lives here.
// Usage: const m = makeMatcher(data); m.match(title, condHint) -> {status, id, cond}
function makeMatcher(D) {
  const R = {};
  for (const k in D.re) R[k] = new RegExp(D.re[k]);
  const tokens = {};
  for (const id in D.tokens) tokens[id] = D.tokens[id].map(p => new RegExp(p));
  const normJp = s => {
    s = s.normalize('NFKC').toLowerCase().replace(/[ァ-ヶ]/g, c => String.fromCharCode(c.charCodeAt(0) - 0x60));
    return s.replace(/[〜～~]/g, '').replace(/[^0-9a-zぁ-ゖー一-龯々()]/g, '');
  };
  const normEn = s => ' ' + s.normalize('NFKC').toLowerCase().replace(/['’]/g, '').replace(/[^0-9a-z]+/g, ' ').trim() + ' ';
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  // Non-overlapping name matches covering as much of the title as possible (see _spans in matcher.py).
  const spans = (text, table, word) => {
    const occ = [];
    for (const [key, ids] of table) {
      const pat = word ? ' ' + key + ' ' : key;
      for (let i = text.indexOf(pat); i !== -1; i = text.indexOf(pat, i + 1)) {
        const a = i + (word ? 1 : 0);
        occ.push([a, a + key.length, ids, key]);
      }
    }
    occ.sort((x, y) => x[1] - y[1] || x[0] - y[0]);
    const n = text.length, best = new Array(n + 1);
    best[0] = [0, 0, []];
    let j = 0;
    for (let i = 1; i <= n; i++) {
      best[i] = best[i - 1];
      while (j < occ.length && occ[j][1] === i) {
        const [a, b] = occ[j], [cov, neg, ch] = best[a];
        const c = [cov + b - a, neg - 1, ch.concat([occ[j]])];
        if (c[0] > best[i][0] || (c[0] === best[i][0] && c[1] > best[i][1])) best[i] = c;
        j++;
      }
    }
    const chosen = best[n][2].slice().sort((x, y) => x[0] - y[0]);
    const taken = new Array(n).fill(false);
    for (const [a, b] of chosen) for (let i = a; i < b; i++) taken[i] = true;
    const rest = [...text].map((c, i) => taken[i] ? ' ' : c).join('');
    return [chosen.map(([, , ids, key]) => [ids, key]), rest];
  };
  const resolve = (ids, title) => {
    let best = null, score = -1;
    for (const id of [...ids].sort()) {
      const t = tokens[id] || [];
      if (t.every(r => r.test(title)) && t.length > score) { best = id; score = t.length; }
    }
    return best;
  };
  function match(title, hint, requireSeries = true) {
    const full = normJp(title);
    const cond = (R.new.test(full) || hint === 'new') ? 'new' : (R.used.test(full) || hint === 'used') ? 'used' : 'unknown';
    if (R.exclude.test(full) || (requireSeries && R.series && !R.series.test(full))) return { status: 'excluded', id: null, cond };
    let t = full;
    for (const b of D.boiler) t = t.split(b).join(' ');
    const [jp, rest] = spans(t, D.jp, false);
    const [en] = spans(normEn(title), D.en, true);
    // the same Japanese name twice means two figures; two different names of one figure don't
    const resolved = jp.map(([c, k]) => [resolve(c, t), k]).concat(en.map(([c]) => [resolve(c, t), false]));
    const seenJp = {};
    const shadowed = new Set(resolved.flatMap(([id]) => D.shadows[id] || []));
    const ids = []; let unresolved = false, nJp = 0;
    for (const [id, isJp] of resolved) {
      if (shadowed.has(id)) continue;
      if (id === null) { unresolved = true; continue; }
      if (isJp) { const k = id + '|' + isJp; seenJp[k] = (seenJp[k] || 0) + 1; nJp = Math.max(nJp, seenJp[k]); }
      if (!ids.includes(id)) ids.push(id);
    }
    if (!ids.length) return { status: unresolved ? 'uncertain' : (R.lot.test(rest) ? 'lot' : 'none'), id: null, cond };
    if (ids.length > 1 || nJp > 1 || R.lot.test(rest)) return { status: 'lot', id: null, ids, cond };
    const id = ids[0], toks = tokens[id] || [];
    if (id.startsWith('item-loto') && R.loto_both && R.loto_both.test(full)) return { status: 'lot', id: null, ids, cond };
    let left = rest;
    for (const tk of toks) left = left.replace(new RegExp(tk.source, 'g'), ' ');
    if (toks.some(tk => R.anniv.test(tk.source))) left = left.replace(new RegExp(R.goldish.source, 'g'), ' ');
    if (R.loose.test(left)) return { status: 'uncertain', id, cond };
    return { status: 'ok', id, cond };
  }
  return { match };
}
if (typeof module !== 'undefined') module.exports = { makeMatcher };
