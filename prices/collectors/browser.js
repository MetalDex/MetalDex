// Price collectors that run inside a browser tab (paste into the console).
//
// 1. Open the source site in a tab (start URLs are in prices/README.md).
// 2. First time on a site: paste prices/collectors/install.js (made by make_bundle.py; it saves itself in the
//    site's localStorage). Later runs: paste prices/collectors/load.js instead.
// 3. __mmgRun('yahoo-sold', {since: '2026-10-21'}) starts a collector in the background.
//    Mercari: open the search page first (prices/README.md); __mmgRun('mercari-sold', {pages: 10}) clicks through pages.
// 4. Poll __mmgStatus() until done, then read __mmgChunk(0), __mmgChunk(1), ... (15,000 characters each),
//    join the text into a .json file and run: python3 prices/ingest.py --usdjpy <rate> <file.json> ...
//
// Every collector returns {src, run, records, unmatched, stats}. A record is
//   [kind, listing_id, figure_id, price, currency, date, cond, extra]
// kind: "sold" (completed sale), "ask" (second-hand buy-it-now listing), "retail" (shop, new)
// date: sale date (YYYY-MM-DD) for sold, "" otherwise. extra: bids / stock status / match note.
(function () {
  const W = window;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const day = d => new Date(d).toISOString().slice(0, 10);
  const getText = async url => { const r = await fetch(url, { credentials: 'include' }); if (!r.ok) throw new Error(url + ' -> ' + r.status); return r.text(); };
  const parseHTML = h => new DOMParser().parseFromString(h, 'text/html');
  const yen = s => { const m = String(s).replace(/[,，\s]/g, '').match(/([0-9]+(?:\.[0-9]+)?)/); return m ? Number(m[1]) : null; };

  W.__mmgInstall = function (data) {
    try { localStorage.setItem('mmgMatcher', JSON.stringify(data)); } catch (e) {}
    W.__mmgMatcherData = data;
    return 'matcher installed: ' + data.jp.length + ' names';
  };
  function matcher() {
    let d = W.__mmgMatcherData;
    if (!d) { try { d = JSON.parse(localStorage.getItem('mmgMatcher') || 'null'); } catch (e) {} }
    if (!d) throw new Error('call __mmgInstall(matcherData) first');
    W.__mmgMatcherData = d;
    return makeMatcher(d);
  }

  function collector(src) {
    const M = matcher(), out = { src, run: day(Date.now()), records: [], unmatched: [], stats: { seen: 0, ok: 0, lot: 0, excluded: 0, uncertain: 0, none: 0 }, done: false, error: null };
    out.add = (kind, id, title, price, cur, date, condHint, extra, jan) => {
      out.stats.seen++;
      let r = null;
      if (jan && W.__mmgMatcherData && W.__mmgMatcherData.jan && W.__mmgMatcherData.jan[jan]) r = { status: 'ok', id: W.__mmgMatcherData.jan[jan], cond: 'new' };
      if (!r) r = M.match(title, condHint, kind !== 'retail'); // shop pages are already this series
      out.stats[r.status]++;
      if (r.status === 'ok') out.records.push([kind, String(id), r.id, price, cur, date || '', r.cond, extra == null ? '' : extra, String(title || '').replace(/\s+/g, ' ').slice(0, 120)]);
      else if ((r.status === 'none' || r.status === 'uncertain') && out.unmatched.length < 60) out.unmatched.push([r.status, String(id), title.slice(0, 90), price]);
    };
    return out;
  }

  // ---------- Yahoo! Auctions (auctions.yahoo.co.jp) ----------
  function yahooItems(html) {
    const m = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
    if (!m) throw new Error('Yahoo page has no __NEXT_DATA__ (layout changed or bot check)');
    const l = JSON.parse(m[1]).props.pageProps.initialState.search.items.listing;
    return { items: l.items || [], total: l.totalResultsAvailable };
  }
  const ycond = c => /NEW/.test(c || '') ? 'new' : (c ? 'used' : '');
  async function yahooSold(out, o) {
    const since = o.since || '2000-01-01', seen = new Set();
    for (const q of o.queries || ['メタリックモンスターズ', 'メタリックアイテムズ']) {
      for (let b = 1; b <= 15000; b += 100) {
        const { items } = yahooItems(await getText('https://auctions.yahoo.co.jp/closedsearch/closedsearch?p=' + encodeURIComponent(q) + '&n=100&b=' + b));
        if (!items.length) break;
        let older = 0;
        for (const it of items) {
          const d = day(it.endTime);
          if (d < since) { older++; continue; }
          if (seen.has(it.auctionId)) continue;
          seen.add(it.auctionId);
          out.add('sold', it.auctionId, it.title, it.price, 'JPY', d, ycond(it.itemCondition), it.bidCount);
        }
        if (older === items.length) break;
        await sleep(o.delay || 1500);
      }
    }
  }
  async function yahooAsk(out, o) {
    const seen = new Set();
    for (const q of o.queries || ['メタリックモンスターズ', 'メタリックアイテムズ']) {
      for (let b = 1; b <= (o.max || 3000); b += 100) {
        const { items } = yahooItems(await getText('https://auctions.yahoo.co.jp/search/search?p=' + encodeURIComponent(q) + '&n=100&b=' + b));
        if (!items.length) break;
        for (const it of items) {
          const p = it.buyNowPrice || (it.isFixedPrice ? it.price : null);
          if (!p || seen.has(it.auctionId)) continue; // auctions without a buy-it-now price aren't asks
          seen.add(it.auctionId);
          out.add('ask', it.auctionId, it.title, p, 'JPY', '', ycond(it.itemCondition), it.isFleamarketItem ? 'flea' : 'auction');
        }
        await sleep(o.delay || 1500);
      }
    }
  }

  // ---------- Mercari (jp.mercari.com) ----------
  // Mercari builds its pages in the browser, so this reads the page that is open.
  // Navigate page by page (…&page_token=v1:N) and call __mmgRun('mercari-sold'|'mercari-ask') on each; results add up.
  async function mercariPage(out, kind) {
    for (let i = 0; i < 20 && !document.querySelector('li[data-testid="item-cell"]'); i++) await sleep(500);
    const cells = [...document.querySelectorAll('li[data-testid="item-cell"]')];
    for (const li of cells) {
      const a = li.querySelector('a[href*="/item/"], a[href*="/shops/product/"]');
      const img = li.querySelector('img');
      const pr = li.querySelector('[data-testid="item-tile-price"]');
      if (!a || !img || !pr) continue;
      const id = a.getAttribute('href').split('/').pop();
      const title = (img.getAttribute('alt') || '').replace(/のサムネイル.*$/, '');
      const txt = pr.textContent;
      const cur = /US\$|\$/.test(txt) ? 'USD' : 'JPY';
      out.add(kind, id, title, yen(txt), cur, '', '', a.getAttribute('href').includes('/shops/') ? 'shop' : '');
    }
    const next = [...document.querySelectorAll('a')].find(x => x.textContent.trim() === '次へ');
    out.next = next ? next.href : null;
    out.stats.cells = (out.stats.cells || 0) + cells.length;
  }

  // Reads up to o.pages pages by clicking "次へ" (next) inside the page, so no new page loads are needed.
  async function mercariCrawl(out, kind, o) {
    for (let p = 0; p < (o.pages || 10); p++) {
      await mercariPage(out, kind);
      const next = [...document.querySelectorAll('a')].find(x => x.textContent.trim() === '次へ');
      if (!next) break;
      const first = document.querySelector('li[data-testid="item-cell"] a')?.getAttribute('href');
      next.click();
      for (let i = 0; i < 40; i++) {
        await sleep(500);
        const now = document.querySelector('li[data-testid="item-cell"] a')?.getAttribute('href');
        if (now && now !== first) break;
      }
      await sleep(o.delay || 1500);
    }
  }

  // ---------- Hobby Search (www.1999.co.jp) ----------
  async function hobbysearch(out, o) {
    const base = 'https://www.1999.co.jp/search?typ1_c=111&target=ItemSeries&searchkey=' + encodeURIComponent('ドラゴンクエスト メタリックモンスターズギャラリー');
    for (let p = 1; p <= 10; p++) {
      const doc = parseHTML(await getText(base + '&spage=' + p));
      const cards = [...doc.querySelectorAll('.c-card')];
      if (!cards.length) break;
      for (const c of cards) {
        const code = c.querySelector('[itemcode]')?.getAttribute('itemcode');
        const t = c.innerText || c.textContent;
        const title = (c.querySelector('a[title]')?.getAttribute('title')) || t.replace(/\s+/g, ' ');
        const price = yen(c.querySelector('.c-card__price-element')?.textContent);
        const stock = /在庫なし|品切|販売終了/.test(t) ? 'out' : /予約/.test(t) ? 'pre' : 'in';
        if (code && price) out.add('retail', code, title, price, 'JPY', '', 'new', stock);
      }
      await sleep(o.delay || 1500);
    }
  }

  // ---------- Square Enix e-STORE (store.jp.square-enix.com) ----------
  async function estore(out, o) {
    const seen = new Set();
    for (let p = 1; p <= 20; p++) {
      const url = 'https://store.jp.square-enix.com/estore/e/edragonquest-figure' + (p > 1 ? '_p' + p : '') + '/';
      const doc = parseHTML(await getText(url));
      const cards = [...doc.querySelectorAll('dl.block-thumbnail-t--goods')];
      const first = cards[0]?.querySelector('a[href*="/g/g"]')?.getAttribute('href');
      if (!cards.length || seen.has(first)) break; // past the last page the store repeats it
      seen.add(first);
      for (const c of cards) {
        const a = c.querySelector('a[href*="/g/g"]');
        const title = a?.getAttribute('title') || '';
        if (!/メタリック/.test(title)) continue;
        const code = (a.getAttribute('href').match(/\/g\/g([^/]+)/) || [])[1];
        const icons = [...c.querySelectorAll('.block-icon span')].map(s => s.textContent.trim()).join(' ');
        const txt = c.textContent;
        const stock = /在庫切れ|品切|売り切れ|SOLD|受付終了|販売終了/.test(txt + icons) ? 'out' : /予約/.test(icons) ? 'pre' : 'in';
        let st = stock;
        // the list page doesn't show sold-out items; the product page's stock box does
        if (st !== 'pre') {
          try {
            const pd = parseHTML(await getText('/estore/g/g' + code + '/'));
            const box = (pd.querySelector('.block-goods-stock')?.textContent || '').replace(/\s+/g, '').split('※')[0]; // status first; the notes after ※ can mention 予約
            st = /品切|在庫切|販売終了|受付終了/.test(box) ? 'out' : /予約/.test(box) ? 'pre' : /在庫あり/.test(box) ? 'in' : 'unknown';
          } catch (e) { st = 'unknown'; } // the store answers "too much traffic" (403) when asked too fast
          await sleep(o.delay || 3000);
        }
        out.add('retail', code, title, yen(c.querySelector('.price')?.textContent), 'JPY', '', 'new', st);
      }
      await sleep(o.delay || 1500);
    }
  }

  // ---------- Sootang (www.sootang.jp, Shopify) ----------
  async function sootang(out, o) {
    for (let p = 1; p <= 5; p++) {
      const j = JSON.parse(await getText('https://www.sootang.jp/collections/series_metalic-monsters-garelly/products.json?limit=250&page=' + p));
      if (!j.products.length) break;
      for (const pr of j.products) {
        for (const v of pr.variants) {
          const jan = /^[0-9]{13}$/.test(v.sku || '') ? v.sku : (/^[0-9]{13}$/.test(pr.handle) ? pr.handle : '');
          out.add('retail', pr.handle, pr.title, Number(v.price), 'JPY', '', 'new', v.available ? 'in' : 'out', jan);
        }
      }
      await sleep(o.delay || 1000);
    }
  }

  const RUN = {
    'yahoo-sold': yahooSold, 'yahoo-ask': yahooAsk, hobbysearch, estore, sootang,
    'mercari-sold': (out, o) => mercariCrawl(out, 'sold', o), 'mercari-ask': (out, o) => mercariCrawl(out, 'ask', o),
  };

  // Start a collector in the background. For Mercari, call again on each page with {append: true}.
  W.__mmgRun = function (src, o = {}) {
    if (!RUN[src]) throw new Error('unknown source ' + src + '; one of ' + Object.keys(RUN).join(', '));
    const out = (o.append && W.__mmgOut && W.__mmgOut.src === src) ? W.__mmgOut : collector(src);
    out.done = false; out.error = null; W.__mmgOut = out;
    RUN[src](out, o).then(() => { out.done = true; }, e => { out.error = String(e && e.message || e); out.done = true; });
    return 'started ' + src;
  };
  W.__mmgStatus = () => { const o = W.__mmgOut; return o ? { src: o.src, done: o.done, error: o.error, records: o.records.length, stats: o.stats, next: o.next || null } : null; };
  // Compact text form for moving results through a chat-sized pipe (read by prices/ingest.py):
  //   #mmgpack2 <src> <run> / #stats {...} / #u <status> <price> <title>
  //   O <figure> day:price[c] ...  sales older than idDays, without listing ids (day = days before the run;
  //                                 c: n new, x unknown, nothing = used)
  //   R kind,id,figure,price,currency,date,cond,extra   everything else
  // Listing ids are only needed for recent sales (so an overlapping next run doesn't count them twice) and for
  // listings (to link to them), so older sales drop them to keep the text small.
  W.__mmgPack = function (idDays = 21) {
    const o = W.__mmgOut, cc = c => c === 'new' ? 'n' : c === 'used' ? '' : 'x';
    const base = Date.parse(o.run), cutoff = new Date(base - idDays * 864e5).toISOString().slice(0, 10);
    const old = {}, rows = [], perFig = {};
    // second-hand listings: keep the 3 cheapest per figure and send the total count separately
    for (const r of o.records) if (r[0] === 'ask') (perFig[r[2]] = perFig[r[2]] || []).push(r);
    const keep = new Set(Object.values(perFig).flatMap(a => a.sort((x, y) => x[3] - y[3]).slice(0, 3)));
    for (const r of o.records) {
      const [kind, id, f, price, cur, date, cond, extra, title] = r;
      if (kind === 'ask' && !keep.has(r)) continue;
      if (kind === 'sold' && date && date < cutoff) {
        (old[f] = old[f] || []).push(Math.round((base - Date.parse(date)) / 864e5) + ':' + price + cc(cond));
      } else rows.push('R ' + [kind, id, f, price, cur === 'JPY' ? '' : cur, date, cc(cond), String(extra).replace(/,/g, ' ')].join(',') + (title ? '\t' + title : ''));
    }
    const lines = ['#mmgpack2 ' + o.src + ' ' + o.run, '#stats ' + JSON.stringify(o.stats)];
    if (o.error) lines.push('#error ' + o.error);
    if (Object.keys(perFig).length) lines.push('#counts ' + Object.entries(perFig).map(([f, a]) => f + ':' + a.length).join(' '));
    for (const u of o.unmatched) lines.push('#u ' + u[0] + ' ' + u[3] + ' ' + String(u[2]).replace(/\s+/g, ' '));
    for (const f in old) lines.push('O ' + f + ' ' + old[f].join(' '));
    return lines.concat(rows).join('\n');
  };
  // Read the packed text in pieces: __mmgPackChunk(0), __mmgPackChunk(1), ... plus a SHA-1 to check the copy.
  W.__mmgPackChunk = async function (i, size = 15000) {
    if (i === 0 || !W.__mmgPacked) W.__mmgPacked = W.__mmgPack();
    const t = W.__mmgPacked;
    const sha = [...new Uint8Array(await crypto.subtle.digest('SHA-1', new TextEncoder().encode(t)))].map(x => x.toString(16).padStart(2, '0')).join('').slice(0, 12);
    return { i, of: Math.ceil(t.length / size), sha1: sha, text: t.slice(i * size, (i + 1) * size) };
  };
  W.__mmgChunk = function (i, size = 15000) {
    const o = W.__mmgOut;
    const s = JSON.stringify({ src: o.src, run: o.run, stats: o.stats, error: o.error, records: o.records, unmatched: o.unmatched });
    return { i, of: Math.ceil(s.length / size), text: s.slice(i * size, (i + 1) * size) };
  };
})();
