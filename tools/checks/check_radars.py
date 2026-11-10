"""The radars' calibration, checked two ways (04/10, the user: "fiabilise les correspondances"):
- against the game's own values (pos_x, pos_y, scale of each map's overview, as MurkyYT extracts them from the game
  files: https://github.com/MurkyYT/cs2-map-icons);
- against the demos: the players' positions of the base, put on the radar with that calibration, must fall on its
  drawn part (a map shifted or scaled wrong puts them on the transparent background). Multi-level maps: each
  position on the image of its level.
Usage: python checks/check_radars.py [--fix]   (--fix: writes the game's exact values where they differ)"""
import glob
import json
import os
import sys
import urllib.request

import numpy as np
import pandas as pd
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from wily.core import config  # noqa: E402

MURKY = "https://raw.githubusercontent.com/MurkyYT/cs2-map-icons/main/data/available.json"


def game_values():
    try:
        req = urllib.request.Request(MURKY, headers={"User-Agent": "wily-coach"})
        return {m: (x.get("radar_info") or {}) for m, x in json.loads(urllib.request.urlopen(req, timeout=30).read())["maps"].items()}
    except Exception as e:
        print("game values unavailable:", e)
        return {}


def positions(mp, n=40000):
    """The players' positions of the base on that map, with their level (samples of the detailed extraction)."""
    out = []
    for d in glob.glob(os.path.join(config.DEEP, "*")):
        try:
            if json.load(open(os.path.join(d, "meta.json"), encoding="utf-8")).get("map") != mp:
                continue
            out.append(pd.read_parquet(os.path.join(d, "samples.parquet"), columns=["X", "Y", "level"]))
        except (OSError, ValueError):
            continue
        if sum(len(x) for x in out) > n * 3:
            break
    if not out:
        return None
    s = pd.concat(out, ignore_index=True)
    return s.sample(min(n, len(s)), random_state=1)


def on_radar(cal, s):
    """Share of the positions on a drawn pixel of their level's radar (within 2 px)."""
    res = {}
    for lv in cal.get("levels", []):
        f = os.path.join(ROOT, "resources", lv["image"])
        if not os.path.exists(f):
            continue
        img = Image.open(f).convert("RGBA")
        k = img.width / 1024
        a = np.array(img)[:, :, 3] > 8
        a = a | np.roll(a, 2, 0) | np.roll(a, -2, 0) | np.roll(a, 2, 1) | np.roll(a, -2, 1)
        g = s[s.level == lv["key"]] if len(cal["levels"]) > 1 and "level" in s else s
        if not len(g):
            continue
        px = ((g.X - cal["pos_x"]) / cal["scale"] * k).round().astype(int).clip(0, img.width - 1)
        py = ((cal["pos_y"] - g.Y) / cal["scale"] * k).round().astype(int).clip(0, img.height - 1)
        res[lv["key"]] = (round(100 * float(a[py.to_numpy(), px.to_numpy()].mean()), 1), len(g))
    return res


def main(fix=False):
    game = game_values()
    bad = 0
    for f in sorted(glob.glob(os.path.join(ROOT, "resources", "maps", "*.json"))):
        mp = os.path.basename(f)[:-5]
        if mp in ("csdm_maps", "overviews"):
            continue
        cal = json.load(open(f, encoding="utf-8"))
        g = game.get(mp) or {}
        diff = {k: (cal.get(k), g[k]) for k in ("pos_x", "pos_y", "scale") if k in g and abs(float(cal.get(k, 0)) - float(g[k])) > 1e-3}
        if diff and fix:
            for k, (_, v) in diff.items():
                cal[k] = float(v)
            json.dump(cal, open(f, "w", encoding="utf-8"), indent=1)
        s = positions(mp)
        on = on_radar(cal, s) if s is not None else {}
        worst = min((v[0] for v in on.values()), default=None)
        bad += worst is not None and worst < 97
        print(f"{mp:14} game {'same' if g and not diff else ('fixed ' if fix else 'differs ') + str(diff) if g else 'no game data'}"
              f" · demos on the radar: {', '.join(f'{k} {v[0]}% of {v[1]}' for k, v in on.items()) or 'no demo'}")
    print("all maps line up" if not bad else f"{bad} map(s) under 97 % on the radar")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main("--fix" in sys.argv) else 0)
