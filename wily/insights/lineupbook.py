"""Lineup books made by players for a map (where to stand, where to aim, the throw, with their pictures), read from
their public GitHub repository and kept in out/lineups/<map>.json (not versioned: the book stays its author's; the page
shows it with their name and a link, its pictures loaded from GitHub).

BOOKS lists the known books. Usage: python -m wily.insights.lineupbook  (downloads them again)"""
import json
import os
import re
import sys
import time
import urllib.request

from wily.core import config

BOOKS = {
    "de_fachwerk": {"repo": "gronnmann/de-fachwerk-smokes", "branch": "master", "file": "main.typ", "author": "gronnmann"},
}
DIR = os.path.join(config.OUT, "lineups")
MAX_AGE = 7 * 86400
KIND = {"smokes": "smoke", "smoke": "smoke", "flash": "flash", "flashes": "flash", "molly": "molotov", "mollies": "molotov", "molotov": "molotov",
        "he": "he"}


def _anchor(*parts):
    return "--".join(re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-") for p in parts if p)


def parse(text, book):
    """The lineups of a Typst book: #lineup("From -> Target Kind", kind:, throw:, position: [..], aim: [..], *-image:)
    under '= Site', '== Side', '=== Kind' headings."""
    raw_base = f"https://raw.githubusercontent.com/{book['repo']}/{book['branch']}/"
    page = f"https://github.com/{book['repo']}"
    h, items, cur = {1: None, 2: None, 3: None}, [], None
    for ln in text.splitlines():
        m = re.match(r"^(=+)\s+(.+)$", ln)
        if m and cur is None:
            lv = min(len(m.group(1)), 3)
            h[lv] = m.group(2).strip()
            for k in range(lv + 1, 4):
                h[k] = None
            continue
        if ln.startswith("#lineup("):
            cur = {"raw": ""}
            continue
        if cur is None:
            continue
        if ln.strip() != ")":
            cur["raw"] += ln + "\n"
            continue
        r = cur["raw"]
        cur = None
        t = re.search(r'^\s*"([^"]+)"', r, re.M)
        if not t:
            continue
        title = re.sub(r"\s+", " ", t.group(1)).strip()
        g = lambda k: (re.search(k + r':\s*"([^"]+)"', r) or [None, None])[1]
        b = lambda k: (re.search(k + r":\s*\[(.*?)\]\s*,?\s*$", r, re.M) or [None, None])[1]
        kind = KIND.get((g("kind") or h[3] or "smoke").lower().split()[0], "smoke")
        site = (h[1] or "").replace(" Site", "").strip() or None
        side = "CT" if "CT" in (h[2] or "") else "T" if (h[2] or "").startswith("T") else None
        frm, arrow, to = title.partition("->")
        if not arrow:   # "Long Flash": no from -> to
            frm, to = None, title
        to = re.sub(r"\s*(super\s+)?(smoke|flash|molly|molotov)\s*$", "", to.strip(), flags=re.I) or to.strip()
        img = lambda k: raw_base + g(k) if g(k) else None
        items.append({"title": title, "site": site, "side": side, "type": kind, "from": (frm or "").strip() or None, "to": to or None,
                      "throw": g("throw") if g("throw") and g("throw") != "Throw" else None,
                      "position": b("position"), "aim": b("aim"), "landing": b("landing"),
                      "img_position": img("position-image"), "img_aim": img("aim-image"), "img_aim2": img("aim-image-2"),
                      "img_landing": img("landing-image"),
                      "link": f"{page}#{_anchor(h[1], h[2], h[3])}"})
    return items


def fetch(mp, force=False):
    book = BOOKS.get(mp)
    if not book:
        return None
    os.makedirs(DIR, exist_ok=True)
    f = os.path.join(DIR, f"{mp}.json")
    if not force and os.path.exists(f) and time.time() - os.path.getmtime(f) < MAX_AGE:
        return json.load(open(f, encoding="utf-8"))
    try:
        url = f"https://raw.githubusercontent.com/{book['repo']}/{book['branch']}/{book['file']}"
        text = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "wily-coach"}), timeout=20).read().decode("utf-8")
        res = {"map": mp, "author": book["author"], "repo": f"https://github.com/{book['repo']}", "time": time.strftime("%Y-%m-%d"),
               "lineups": parse(text, book)}
        json.dump(res, open(f, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return res
    except Exception as e:
        print(f"lineup book {mp}: {e}")
        return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else None


def all_books():
    return {mp: b for mp in BOOKS if (b := fetch(mp))}


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for mp in BOOKS:
        b = fetch(mp, force=True)
        print(mp, len((b or {}).get("lineups", [])), "lineups")
        for x in (b or {}).get("lineups", []):
            print("  ", x["site"], x["side"], x["type"], x["throw"] or "", "|", x["from"], "->", x["to"])
