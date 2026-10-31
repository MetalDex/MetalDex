"""Match a shop or auction listing title to a figure in the catalogue.

    from prices.matcher import Matcher
    m = Matcher.from_json("docs/data/figures.json")
    m.match("ドラゴンクエスト メタリックモンスターズギャラリー はぐれメタル ～40周年記念バージョン～ 新品")
    # -> {"status": "ok", "id": "liquid-metal-slime-40th", "cond": "new"}

status is one of:
  ok         exactly one figure, single item
  lot        several different figures, or "set / 3体 / まとめ" wording (left out of prices)
  excluded   not a Metallic Monsters figure on its own (junk, empty box, repaint, other lines)
  uncertain  a figure name plus a variant word we can't place (e.g. "ゴールド" with no anniversary)
  none       no figure name found

The same rules are ported to prices/matcher.js for the browser collectors.
tests/test_matcher.py checks both against tests/match_cases.tsv.
"""
import json
import re
import unicodedata
from pathlib import Path

# Words removed before looking for names (normalised form, longest first).
BOILERPLATE = [
    "めたりっくもんすたーずぎゃらりー", "めたりっくあいてむずぎゃらりー", "めたりっくぎゃらりーもんすたーず",
    "めたりっくもんすたーず", "めたりっくあいてむず", "めたりっくもんすたー", "もんすたーずぎゃらりー",
    "あいてむずぎゃらりー", "あいてむぎゃらりー", "どらごんくえすと", "すくうぇあえにっくす", "すくえあえにっくす",
    "すくうぇあ", "えにっくす", "すくえに", "sqextoys", "sqex", "squareenix", "dragonquest", "metallicmonstersgallery",
    "metallicmonsters", "metallic", "どらくえ", "ふぃぎゅあ", "figure", "めたりっく",
]

# The listing must name the series. Without this, other toys that are just "metallic" (e.g. a metallic-colour
# Hacksaurus from a different line) matched by figure name alone.
SERIES = re.compile(r"めたりっく(もんすたー|あいてむ)|めたりっくぎゃらりー|metallicmonster|metallicitem")

# Not a single Metallic Monsters figure. Checked on the whole title.
EXCLUDE = re.compile(
    r"じゃんく|junk|破損|欠品|部品取り|ぱーつのみ|箱のみ|空箱|外箱のみ|たぐのみ|台座のみ|説明書のみ|"
    r"りぺいんと|repaint|かすたむ|改造|ぎゃらりーhd|hd\d|ちゃぷたー|くりすたるもんすたーず|"
    r"きーほるだー|すとらっぷ|こいん|ぶらいとあーつ|そふび|ぬいぐるみ|一番くじ|がちゃ|ぽーちのみ|写真のみ|ぽすたー|"
    # display stands sold on their own (third-party stands for the Items Gallery swords and shields);
    # a figure listed "with stand" (台座付き / 台座あり) is still a figure
    r"台座(?!付|つき|あり|有|込)"
)

# Several items in one listing (checked on the title after the names are taken out).
LOT = re.compile(
    r"(?<![0-9])(?:[2-9]|[1-9][0-9]+)(?:体|個|種|点|つ|匹|ｺ)|[二三四五六七八九十]体|[二三四五]種|"
    r"せっと|まとめ|ろっと|\blot\b|bundle|など|他|ふるこんぷ|こんぷ|全種"
)

# Variant words that change which figure it is. If one is left over after matching, the result is "uncertain".
LOOSE_VARIANT = re.compile(r"[0-9]+周年|[0-9]+th|ごーるど|gold|金色|金の|きんいろ|ふくびき|ぶらっく|黒|くりあ|ぷらちな|しるばー|ろーずごーるど|あんてぃーく")
ANNIV = re.compile(r"[0-9]+周年|[0-9]+th")
# The Loto equipment comes as two products (sword & shield; armour & helm): a title naming parts of both is a lot.
LOTO_BOTH = re.compile(r"(剣|盾).*(鎧|兜)|(鎧|兜).*(剣|盾)")
GOLDISH = re.compile(r"ごーるど|gold|金色|金の|きんいろ|ろーずごーるど|あんてぃーく")

NEW_WORDS = re.compile(r"未開封|新品|未使用|unopened|brandnew")
USED_WORDS = re.compile(r"中古|開封済|開封品|used|現状品|ゆーずど|難あり")

# Required words for figures that share a name with another figure.
TOKENS = {
    "slime-25th": [r"25周年|25th"], "king-slime-25th": [r"25周年|25th"], "liquid-metal-slime-25th": [r"25周年|25th"],
    "liquid-metal-slime-gold-30th": [r"30周年|30th"],
    "slime-35th": [r"35周年|35th"], "king-slime-35th": [r"35周年|35th"], "liquid-metal-slime-35th": [r"35周年|35th"],
    "healslime-35th": [r"35周年|35th"], "slime-knight-35th": [r"35周年|35th"], "item-loto-sword-shield-35th": [r"35周年|35th"],
    "slime-40th": [r"40周年|40th"], "king-slime-40th": [r"40周年|40th"], "liquid-metal-slime-40th": [r"40周年|40th"],
    "dragon-40th": [r"40周年|40th"], "dragonlord-human-40th": [r"40周年|40th"], "dragonlord-40th": [r"40周年|40th"],
    "item-loto-sword-shield-40th": [r"40周年|40th"], "item-loto-armour-helm-40th": [r"40周年|40th"],
    "item-zenithian-sword-shield-40th": [r"40周年|40th"], "item-zenithian-armour-helm-40th": [r"40周年|40th"],
    "slime-loto-blue": [r"ろとぶる|erdrickblue|lotoblue"], "king-slime-loto-blue": [r"ろとぶる|erdrickblue|lotoblue"],
    "estark-blue": [r"ぶるー|青|blue"],
    "malroth-blue": [r"ぶるー|青|blue"], "malroth-green": [r"ぐりーん|緑|green"],
    "liquid-metal-slime-l": [r"はぐれめたるl|lさいず|\(l\)|大きい"], "hagu-lemon-l": [r"はぐれもんl|lさいず|\(l\)"],
    "zoma-cloak": [r"闇の衣|やみのころも|闇のころも|shroud|cloak"],
    "big-eye-critical": [r"つうこん|痛恨|critical|enraged"],
    "slamichi-astron": [r"あすとろん|astron"],
    "slamichi-happy-yellow": [r"しあわせ|幸せ|黄色|いえろー|yellow"],
    "slamichi-yoshinoya": [r"吉野家|よしのや|yoshinoya"],
    "onion-slime": [r"かわ有|かわあり|皮有|皮あり|皮つき|皮付|unpeeled"],
    "onion-slime-peeled": [r"かわ無|かわなし|皮無|皮なし|peeled"],
    "scruffy-dqmsl10": [r"10周年|10th|dqmsl|金の|ごーるど|gold|金色"],
    "drakeslime-dq7r": [r"reimagined|りいまじんど|vii|dq7|ごーるど|gold|金色"],
    "dragonlord-fukubiki-black": [r"ふくびき|ぶらっく|黒|black"],
    "healslime-gold-contest": [r"ごーるど|gold|金色|金の"],
    "slime-gold-dq9-rakuten": [r"楽天|らくてん|rakuten"],
    "slime-gold-dqh2-lawson": [r"ろーそん|lawson|からあげ|ひーろーず"],
    "liquid-metal-slime-gold-tokyo-dome": [r"東京どーむ|tokyodome"],
    "homirot-iv": [r"4世|iv|よんせい"],
    "battle-slime": [r"ばとる|battle"], "battle-liquid-metal-slime": [r"ばとる|battle"],
    "battle-mimic": [r"ばとる|battle"], "battle-killing-machine": [r"ばとる|battle"],
    "battle-great-dragon": [r"ばとる|battle"],
}

# Extra names seen in listings (written as they appear; they are normalised like everything else).
EXTRA_NAMES = {
    "metal-king-slime": ["メタルキングスライム"],
    "lemon-king": ["レモンキングスライム"],
    "killing-machine-2": ["キラーマシンⅡ", "キラーマシーン2"],
    "shenron": ["神竜"],
    "iron-scorpion": ["てつさそり", "鉄のさそり"],
    "orochi": ["ヤマタノオロチ", "八岐大蛇"],
    "dragonlord": ["竜王しんのすがた"],
    "nimzo": ["ミルドラース"],
    "hadlar": ["ハドラー"],
    "ramia": ["ラーミア"],
    "cannibox": ["人食い箱", "人喰い箱"],
    "item-treasure-chest": ["たからばこ"],
    "item-magic-key": ["魔法の鍵", "まほうの鍵"],
    "item-ultimate-key": ["最後の鍵", "さいごの鍵"],
    "item-thiefs-key": ["盗賊の鍵", "とうぞくの鍵"],
    "item-loto-sword-shield": ["ロトの剣", "ロトのつるぎ"],
    "item-loto-sword-shield-35th": ["ロトの剣", "ロトのつるぎ"],
    "item-loto-sword-shield-40th": ["ロトの剣", "ロトのつるぎ"],
    "item-loto-armour-helm": ["ロトの鎧", "ロトのよろい"],
    "item-loto-armour-helm-40th": ["ロトの鎧", "ロトのよろい"],
    "item-zenithian-sword-shield": ["天空の剣"],
    "item-zenithian-sword-shield-40th": ["天空の剣"],
    "item-zenithian-armour-helm": ["天空の鎧"],
    "item-zenithian-armour-helm-40th": ["天空の鎧"],
    "gold-angel-slime": ["ゴールドエンゼルスライム"],
    "metal-angel": ["メタルエンゼルスライム"],
    "item-orbs-red-green": ["レッドオーブ", "グリーンオーブ"],
    "item-orbs-blue-purple": ["ブルーオーブ", "パープルオーブ"],
    "item-orbs-silver-yellow": ["シルバーオーブ", "イエローオーブ"],
    "healslime": ["ホイミン"],
    "evil-priest": ["エビプリ"],
    "pasty-pastry": ["コロネ ホワイト"],
    "hellbaum-roots-set": ["ヘルバオムのねっこ"],
}

# Variant figures that use another figure's name as their base (name_ja doesn't contain it cleanly).
BASE_OVERRIDE = {
    "slime-gold-dq9-rakuten": ["スライム"],
    "slime-gold-dqh2-lawson": ["スライム"],
    "liquid-metal-slime-gold-tokyo-dome": ["はぐれメタル"],
    "liquid-metal-slime-gold-30th": ["はぐれメタル"],
    "healslime-gold-contest": ["ホイミスライム"],
    "dragonlord-fukubiki-black": ["竜王"],
    "slamichi-yoshinoya": ["スラミチ"],
    "slamichi-happy-yellow": ["スラミチ"],
    "scruffy-dqmsl10": ["ワルぼう"],
    "drakeslime-dq7r": ["ドラゴスライム"],
    "onion-slime": ["たまねぎスライム"],
    "onion-slime-peeled": ["たまねぎスライム"],
    "liquid-metal-slime-l": ["はぐれメタル"],
    "hagu-lemon-l": ["はぐレモン"],
    "big-eye-critical": ["おおめだま"],
    "slamichi-astron": ["スラミチ"],
}

# When both are found, the second is part of the first's name in listings (e.g. "ミミック（宝箱）").
SHADOWS = {"mimic": ["item-treasure-chest"], "cannibox": ["item-treasure-chest"], "battle-mimic": ["item-treasure-chest"]}

KATA = {c: c - 0x60 for c in range(0x30A1, 0x30F7)}


def norm_jp(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().translate(KATA)
    s = re.sub(r"[〜～~]", "", s)
    return re.sub(r"[^0-9a-zぁ-ゖー一-龯々()]", "", s)


def norm_en(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower().replace("'", "").replace("’", "")
    return " " + re.sub(r"[^0-9a-z]+", " ", s).strip() + " "


def strip_variant(name_ja: str) -> str:
    s = re.sub(r"[～〜<＜（(].*$", "", name_ja)
    s = re.sub(r"^バトル\s*", "", s)
    s = re.sub(r"\s+L$", "", s)
    return s.strip()


class Matcher:
    def __init__(self, figures):
        self.figs = {f["id"]: f for f in figures}
        self.tokens = {fid: [re.compile(t) for t in ts] for fid, ts in TOKENS.items()}
        jp, en = {}, {}
        for f in figures:
            fid = f["id"]
            bases = BASE_OVERRIDE.get(fid) or [strip_variant(f["name_ja"])]
            for b in bases + EXTRA_NAMES.get(fid, []):
                k = norm_jp(b)
                if len(k) >= 2:
                    jp.setdefault(k, set()).add(fid)
            for b in [f.get("name_en", "")] + list(f.get("aka") or []):
                b = re.sub(r"\s*\(.*?\)", "", b)
                k = norm_en(b).strip()
                if len(k) >= 4 and k not in ("slime", "dragon", "dracky"):
                    en.setdefault(k, set()).add(fid)
        self.jp = sorted(jp.items(), key=lambda kv: -len(kv[0]))
        self.en = sorted(en.items(), key=lambda kv: -len(kv[0]))
        self.boiler = sorted({norm_jp(b) if not b.isascii() else b for b in BOILERPLATE}, key=len, reverse=True)

    @classmethod
    def from_json(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8"))["figures"])

    def _spans(self, text, table, word=False):
        """Non-overlapping name matches covering as much of the title as possible: list of (start, end, ids).

        Titles lose their punctuation in normalising, so names can run into each other: in
        "マリンスライム＆スライムつむり" the letters also spell ライムスライム across the join. Choosing the set of
        matches that covers the most text (then the fewest, i.e. longest, names) reads it as Seaslime + Shell slime.
        """
        occ = []
        for key, ids in table:
            pat = re.escape(" " + key + " ") if word else re.escape(key)
            for m in re.finditer("(?=" + pat + ")", text):
                a = m.start() + (1 if word else 0)
                occ.append((a, a + len(key), ids))
        occ.sort(key=lambda o: (o[1], o[0]))
        # best[i]: (covered chars, -number of names, chosen) using occurrences that end at or before position i
        best = [(0, 0, ())] * (len(text) + 1)
        j = 0
        for i in range(1, len(text) + 1):
            best[i] = best[i - 1]
            while j < len(occ) and occ[j][1] == i:
                a, b, ids = occ[j]
                cov, neg, ch = best[a]
                cand = (cov + b - a, neg - 1, ch + ((a, b, ids),))
                if cand[:2] > best[i][:2]:
                    best[i] = cand
                j += 1
        found = sorted(best[len(text)][2])
        taken = [False] * len(text)
        for a, b, _ in found:
            for i in range(a, b):
                taken[i] = True
        rest = "".join(" " if taken[i] else c for i, c in enumerate(text))
        return found, rest

    def _resolve(self, ids, title):
        """Pick the figure among same-name candidates whose variant words are present (most specific wins)."""
        best, score = None, -1
        for fid in sorted(ids):
            toks = self.tokens.get(fid, [])
            if all(t.search(title) for t in toks) and len(toks) > score:
                best, score = fid, len(toks)
        return best

    def match(self, title: str, condition_hint: str = "", require_series: bool = True) -> dict:
        """require_series=False for shop listings whose titles we already know are this series (e-STORE, Hobby Search…)."""
        full = norm_jp(title)
        cond = "new" if NEW_WORDS.search(full) or condition_hint == "new" else (
            "used" if USED_WORDS.search(full) or condition_hint == "used" else "unknown")
        if EXCLUDE.search(full) or (require_series and not SERIES.search(full)):
            return {"status": "excluded", "id": None, "cond": cond}
        t = full
        for b in self.boiler:
            t = t.replace(b, " ")
        spans, rest = self._spans(t, self.jp)
        en_spans, _ = self._spans(norm_en(title), self.en, word=True)
        ids, unresolved, n_jp = [], False, 0
        # is_jp carries the matched text: the same Japanese name twice ("スライム スライム") means two figures,
        # two different names of one figure ("まほうのかぎ / 魔法の鍵") don't
        resolved = [(self._resolve(c, t), t[s:e]) for s, e, c in spans] + [(self._resolve(c, t), False) for _, _, c in en_spans]
        seen_jp = {}
        shadowed = {x for fid, _ in resolved for x in SHADOWS.get(fid, [])}
        for fid, is_jp in resolved:
            if fid in shadowed:
                continue
            if fid is None:
                unresolved = True
                continue
            if is_jp:
                seen_jp[(fid, is_jp)] = seen_jp.get((fid, is_jp), 0) + 1
                n_jp = max(n_jp, seen_jp[(fid, is_jp)])
            if fid not in ids:
                ids.append(fid)
        if not ids:
            # "35周年記念 5体セット": several figures, none named
            status = "uncertain" if unresolved else ("lot" if LOT.search(rest) else "none")
            return {"status": status, "id": None, "cond": cond}
        if len(ids) > 1 or n_jp > 1 or LOT.search(rest):
            return {"status": "lot", "id": None, "ids": ids, "cond": cond}
        fid = ids[0]
        if fid.startswith("item-loto") and LOTO_BOTH.search(full):
            return {"status": "lot", "id": None, "ids": ids, "cond": cond}
        toks = self.tokens.get(fid, [])
        left = rest
        for tk in toks:
            left = tk.sub(" ", left)
        if any(ANNIV.search(tk.pattern) for tk in toks):
            left = GOLDISH.sub(" ", left)
        if LOOSE_VARIANT.search(left):
            return {"status": "uncertain", "id": fid, "cond": cond}
        return {"status": "ok", "id": fid, "cond": cond}


def export(m: "Matcher") -> dict:
    """Everything the JS port needs, so names and rules live in one place (this file)."""
    return {
        "jp": [[k, sorted(v)] for k, v in m.jp],
        "en": [[k, sorted(v)] for k, v in m.en],
        "boiler": m.boiler,
        "tokens": TOKENS,
        "shadows": SHADOWS,
        "jan": {r["jan"]: f["id"] for f in m.figs.values() for r in f.get("releases", [])},
        "re": {"series": SERIES.pattern, "exclude": EXCLUDE.pattern, "lot": LOT.pattern, "loose": LOOSE_VARIANT.pattern, "anniv": ANNIV.pattern, "loto_both": LOTO_BOTH.pattern,
               "goldish": GOLDISH.pattern, "new": NEW_WORDS.pattern, "used": USED_WORDS.pattern},
    }
