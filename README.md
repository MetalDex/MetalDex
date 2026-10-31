# MetalDex

**The collector's checklist and price guide for the Metallic Monsters Gallery** (メタリックモンスターズギャラリー),
Square Enix's line of die-cast Dragon Quest figures.

**Open it: https://metaldex.github.io/MetalDex/** (works on phones, and offline once loaded)

There has never been one list of every figure. Releases since 2006 are scattered across Japanese news sites, retailer
listings, fan wikis and the official e-STORE, and the shop exclusives and prize figures are easy to miss. MetalDex
collects them into one dataset where every entry cites where it came from, and adds what each figure actually sells for.

**What's in it:**

- **224 entries**: 190 main-line figures, 5 *Battle* figures, 2 *Adventure of Dai* figures and 27 *Metallic Items
  Gallery* pieces, including 58 exclusives (official-shop, e-STORE-only, LOFT, Yahoo! Shopping, game bundles, prizes)
- A photo for every entry, alternate names that are searchable ("Shenron" finds Xenlon), barcodes and retail prices
- **Your collection**: mark what you own and what you want, with price paid, date, notes and your own photo
- **Market prices** from thousands of real completed sales, with the sales behind every price shown
- **Where to buy**, including how to buy from outside Japan

## Use it

**On the web:** open the link above, or `docs/index.html` from a download of this repo. The page is a single file with the data built in, so it also works offline.

- Tap **Mark owned** or ☆ (wishlist) on any figure
- Open a figure to see its barcodes, retail prices and sources, and to record what you paid, when and where you got it, notes, and your own photo
- Browse by type (the default view groups every monster with its variants, like Slimes, King slimes, Killing machines…), or sort by date or name
- Filter by owned / missing / wishlist, by type, by line, or exclusives only, and search in English or Japanese
- Your collection is saved in your browser. Use **Export collection** to back it up or move it to another device, and **Import collection** to load it.

**In Obsidian:** generate one note per figure (with properties for owned, wishlist, price paid, date acquired, where) and an index with progress, wishlist and missing tables:

```bash
python3 obsidian/generate_notes.py --vault "/path/to/your vault"
# bring over what you ticked on the web page:
python3 obsidian/generate_notes.py --vault "/path/to/your vault" --import metaldex-collection-2026-10-06.json
```

Want the photos stored on your own computer, in case a shop removes them? Run `python scripts/cache_images.py`, then `python scripts/build.py`. Local copies go in `docs/img/` (kept out of git) and are used automatically.

Re-running the Obsidian script is safe: catalogue details update, while your own properties and anything under **## My notes** are kept. The index needs the [Dataview](https://github.com/blacksmithgu/obsidian-dataview) plugin.

## Market prices

The **Market** button switches the tracker to a price table: a guide price for every figure (median of recent
completed sales on Yahoo! Auctions and Mercari), the 30-day change, sales volume, the cheapest listing right now
(shop listings link to the shop), risers and fallers, a gallery-wide price index, and a weekly price chart in each figure's window.
The status window shows what your collection is worth. Prices can be shown in yen, US dollars, euros, pounds,
Korean won or Chinese yuan (European Central Bank rates, refreshed when the page is opened online). Prices are collected weekly. To update them yourself, double-click `update-prices.bat` (Windows) or
`update-prices.command` (Mac); it needs [Python 3](https://www.python.org/downloads/) and nothing else. Details in
[prices/README.md](prices/README.md).

## Buying from outside Japan

Yahoo! Auctions, Yahoo! Flea Market, Mercari and the Square Enix e-STORE only deliver inside Japan. The tracker's
**How to buy from abroad** guide (footer, or any figure's "Where to buy") explains proxy services, which one suits which
site, fees as published in 2026, Mercari's Global app (US, Taiwan, Hong Kong) and a few Japanese listing words. Every
figure also has "Search on Buyee" links for Yahoo! Auctions, Yahoo! Flea Market and Mercari. No affiliate links.

## How the data is organised

| File | One row per | Notes |
|---|---|---|
| `data/figures.csv` | figure design (what you own) | Variants with a different paint or sculpt (Loto Blue, 25th/35th/40th Anniversary, Blue Version…) are separate entries |
| `data/groups.py` | type group | Display order and grouping (e.g. all Slime variants together); every id must appear exactly once |
| `data/releases.csv` | retail SKU / barcode | Re-runs of the same design get new barcodes and go here, not in figures.csv |

`python3 scripts/build.py` validates both files (unique IDs, valid dates, EAN-13 checksums on every barcode, a source on every entry) and writes `docs/data/figures.json` and `docs/index.html`. No dependencies beyond Python 3.

Fields in `figures.csv`:

- `line`: `mmg` (main line), `battle`, `dai`, `items`
- `exclusive`: blank for general release, or `official-shop` (ARTNIA / SQUARE ENIX GARDEN / e-STORE / events), `estore`, `yahoo`, `loft`, `bundle` (packed with a game edition), `prize` (lottery/campaign prize, never sold), `event`, `limited` (limited, channel not yet confirmed)
- `first_release`: `YYYY`, `YYYY-MM` or `YYYY-MM-DD`
- `wiki`: Dragon Quest Wiki page title (the English name comes from here)
- `aka`: `;`-separated alternate names, searchable in the tracker
- `hs_id`: Hobby Search item number, used for the product photo
- `image_url`: explicit photo URL (overrides `hs_id`), mostly Square Enix e-STORE product images
- `sources`: `;`-separated list of URLs or the keys `dqwiki`, `hobbysearch`, `amiami`, `sootang`, `estore`

## Sources

- [Metal Dracky's collection list & guide](https://metalfigurecollector.com/dragon-quest-metallic-monsters-gallery/): full monster list, prize-only figures, and paint variations between runs
- [Dragon Quest Wiki](https://dragon-quest.org/): English monster and item names
- [Square Enix e-STORE](https://store.jp.square-enix.com/estore/e/edragonquest-figure/): current and re-ordered products, including official-shop exclusives
- [集まれ！ドラクエ設定wiki](https://dqwiki.wicurio.com/): fan wiki list of releases from 2006 to mid-2022 (original series numbers 1–16, event exclusives)
- [Hobby Search](https://www.1999.co.jp/): barcodes, retail prices, sizes, release months
- [AmiAmi](https://slist.amiami.jp/top/search/list?s_seriestitle_id=4547) and [Sootang](https://www.sootang.jp/collections/series_metalic-monsters-garelly): barcodes and recent releases
- Release announcements from [dragonquest.jp](https://www.dragonquest.jp/), [4Gamer](https://www.4gamer.net/), [Inside Games](https://www.inside-games.jp/) and others, linked on each entry

## Known gaps (help wanted)

- Release dates for the first six figures (2006–2007) and for a few figures marked "Not yet verified"
- Exact sales channel for event-era limited releases (Killer Armour, Premium Slime, Blood Hand, Mecha Burn, Sky Dragon, Atlas, Arm Lion, Boss Troll, Baramos Evil)
- Barcodes for most official-shop exclusives and the 2006–2013 originals
- English names follow the [Dragon Quest Wiki](https://dragon-quest.org/) (current official localisations, e.g. Xenlon, Hunter mech, Gem slime). A handful with no official English name (Slamichi, Homirot IV, Aurora Under…) are romanised or translated

Know something? [Open an issue](https://github.com/metaldex/MetalDex/issues/new/choose) with the **New figure or release** or
**Fix a figure** form; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Photo credits

Photos are hot-linked from where they were published and are not stored in this repository:

- **Official product photos** © ARMOR PROJECT/BIRD STUDIO/SQUARE ENIX, shown from the Square Enix e-STORE and from
  Hobby Search (1999.co.jp), which uses Square Enix's own press photos (they carry Square Enix's copyright line)
- **Metal Dracky** ([collection list & guide](https://metalfigurecollector.com/dragon-quest-metallic-monsters-gallery/)): photos of prize-only figures, used with permission. Thank you!
- one Rakuten shop photo (Premium Slime) until a better one is found
- photos contributed by collectors, credited by name on each figure

Each figure's window in the tracker shows who its photo belongs to. If you own one of these photos and would like it
removed or credited differently, open an issue and it will be changed promptly.

**Contribute a photo:** use the **Photo submission** issue form (see [CONTRIBUTING.md](CONTRIBUTING.md#photos)). Clear photos of a single figure on a plain
background are the most useful, especially for figures that only have a shop photo.

## Legal

Unofficial fan project, not affiliated with or endorsed by Square Enix. Dragon Quest © ARMOR PROJECT / BIRD STUDIO / SQUARE ENIX. Photos remain the property of their owners (see Photo credits). Code is MIT-licensed; the dataset (`data/`) is CC BY 4.0.
