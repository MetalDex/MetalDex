# Price tracker

Collects what Metallic Monsters Gallery figures actually sell for, what's for sale right now and where, and builds
the **Market** view in the tracker: a guide price per figure, 30-day change, weekly price charts, risers and fallers,
a gallery-wide index, the cheapest listings with links, and your collection's value.

## What's collected

| Source | What | How |
|---|---|---|
| Yahoo! Auctions | completed sales (last 180 days on the first run) and buy-it-now listings | script or browser |
| Mercari | sold items and current listings (prices shown in US$ outside Japan, converted to yen) | browser only |
| Square Enix e-STORE, Hobby Search, Sootang | new figures in stock or on pre-order | script or browser |
| eBay | not yet: sold searches need a signed-in eBay account and show a bot check | — |
| AmiAmi, Suruga-ya, Mandarake | not yet: Cloudflare bot checks | — |

Second-hand listings must name the series ("メタリックモンスターズ(ギャラリー)" / "メタリックアイテムズ" or the English
equivalent); a figure name plus "metallic" isn't enough, because other toy lines make metallic-colour versions of the
same monsters. Listings are matched to figures by name (`prices/matcher.py`, with a JavaScript copy in `prices/matcher.js`).
Lots and sets, junk/parts, repaints, other product lines (Monsters Gallery HD, keychains…) and listings with an
unplaceable variant word ("gold" with no anniversary) are left out. Barcodes (JAN) are used where a shop shows them.
`python3 prices/tests/test_matcher.py` checks both matchers against real titles in `tests/match_cases.tsv`.

**Links:** for current buy-it-now listings the tracker shows the cheapest price seen on the last check and links to a
live search, since they sell or end any time. For completed sales, the 3 newest of each figure link to their listing
page, but only after `prices/check_links.py` (run by every update) has opened the page and found it still there; a
page is re-checked after a week and a gone one is replaced by the next-newest sale. Yahoo listing ids starting with
"z" are Yahoo! Flea Market items (`paypayfleamarket.yahoo.co.jp/item/<id>`), the rest Yahoo! Auctions
(`auctions.yahoo.co.jp/jp/auction/<id>`). Yahoo refuses quick page loads, so the checker goes slowly (60 pages per run). Shop product pages (e-STORE, Hobby
Search, Sootang) are linked. e-STORE stock is read from each product page (the list page doesn't mark sold-out items);
if the store refuses ("too much traffic"), the stock is recorded as unknown and not shown as in stock.

**Checking the numbers:** every sale keeps the seller's listing title. Each figure's window in the tracker lists the
sales of the last 90 days behind its guide price (outliers greyed out), each with a **Wrong figure?** link that opens
a pre-filled GitHub issue (`.github/ISSUE_TEMPLATE/wrong-match.yml`). A confirmed report becomes a line in
`data/corrections.csv` (`python3 prices/correct.py <listing id> <right figure id | exclude> "why" --by "#issue"`),
which `aggregate.py` applies on every run, so the fix sticks through later updates. Matching is also spot-checked:
`python3 prices/audit.py sample` draws 200 random sales into `data/audits/<date>.csv`; once every row has a verdict,
the tracker shows the result (October 2026: 199 of 200 right; the one miss was fixed in the matcher).

**Guide price** = median sale over the last 30 days (90 days when a figure had fewer than 5 recent sales), after
dropping sales below a third or above three times the figure's usual price. Buy-it-now listings below 40% of the
guide price are hidden as probably not the figure.

## Data files (`prices/data/`)

- `sales.csv`: every completed sale (source, listing id, figure, date, price, yen price, condition, listing title).
  Never duplicated. A few of the earliest sales have no title.
- `corrections.csv`: confirmed wrong matches (listing → right figure, or `exclude`), applied by `aggregate.py`.
- `audits/`: spot-checks of the matching (`prices/audit.py`).
- `links.json`: which recent sales' listing pages were found working (`prices/check_links.py`), and when.
- `listings/YYYY-MM-DD.csv`: what was for sale that day; `.counts.csv` has the number of listings per figure.
- `fx.csv`: the US$→¥ rate used for each run (Mercari prices).
- `rates.json`: yen → USD/EUR/GBP/KRW/CNY rates for the tracker's currency menu (`python3 prices/update_rates.py`).
  The page also fetches fresh rates itself when opened online.
- `matcher.json`: names and rules for the browser matcher (`python3 prices/ingest.py --matcher-data`).
- `raw/` and `logs/`: what each collector returned and a log of each run; kept on the maintainer's computer, not in
  the repo.

## Running it

**One click** (any computer with Python 3.9+, no extra packages, no browser needed):

- Windows: double-click `update-prices.bat` in the repo's top folder.
- Mac: double-click `update-prices.command`. Linux: `./update-prices.command`.

It runs `prices/update.py`, which updates exchange rates, collects Yahoo! Auctions (sold + buy-now), the Square Enix
e-STORE and Sootang (`prices/collect.py`), adds them to the history, rebuilds the tracker and the
Obsidian notes (when the repo sits inside the vault), writes a log to `prices/data/logs/update-<date>.txt` (not committed), and
commits. Add `--push` to also push (the published site updates from that), `--no-commit` to skip the commit.
It takes a few minutes because it waits between pages.

Safety: a source that fails, or returns less than half as many listings as its last run (a block or a half-loaded
site), is left out of that update, so a bad run can't wipe out good data; `--force` overrides the size check.
A failed collection is saved as `<source>-<date>.failed.json` (not committed) and never overwrites a good file.

Only the maintainer needs to run it: everyone else gets the new prices from the published site.

**Run it weekly by itself (Windows Task Scheduler)**, in a Command Prompt (change the path to yours):

```
schtasks /Create /TN "MetalDex price update" /SC WEEKLY /D SUN /ST 11:00 /TR "\"C:\path\to\metal-gallery-tracker\update-prices.bat\" --auto"
```

(`--auto` stops it waiting for Enter at the end.) Mac/Linux: a cron line such as
`0 11 * * 0 /path/to/metal-gallery-tracker/update-prices.command --auto`.

**Step by step** (what the one-click script does):

```bash
python3 prices/collect.py                       # Yahoo sold + listings, e-STORE, Sootang
python3 prices/ingest.py prices/data/raw/*-$(date +%F).json
python3 prices/aggregate.py && python3 scripts/build.py
```

**Browser** (needed for Mercari; also works for everything else). In a tab on the site:

1. First time on that site: paste `prices/collectors/install.min.js` into the console (it saves the collectors in
   the site's local storage). Later: paste `prices/collectors/load.js`.
2. `__mmgRun('yahoo-sold', {since: '2026-10-21'})`, `__mmgRun('yahoo-ask')`, `__mmgRun('mercari-sold', {pages: 10})`
   (on `https://jp.mercari.com/search?keyword=メタリックモンスターズ&status=sold_out&sort=created_time&order=desc`),
   `__mmgRun('mercari-ask', {pages: 10})` (same search with `status=on_sale`), `__mmgRun('estore')`,
   `__mmgRun('hobbysearch')`, `__mmgRun('sootang')`.
3. When `__mmgStatus().done` is true, copy `__mmgPack()` into a `.pack` file and run
   `python3 prices/ingest.py --usdjpy <rate> file.pack`.

After changing the catalogue or the matcher: `python3 prices/ingest.py --matcher-data && python3 prices/collectors/make_bundle.py`.

Mercari and Hobby Search are only collected by the browser route: Mercari builds its pages in the browser, and
Hobby Search answers scripts with a Cloudflare "Just a moment" bot check, which we don't try to get around
(`check-sites.bat` / `python3 prices/collect.py --diagnose` shows what each site answers a script). A weekly browser run
collects all sources (including Mercari) and commits the results; the one-click script covers everything else.
