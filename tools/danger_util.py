"""Where players get killed from, and what grenades they throw where (29/10, the user: "il ne suffit pas de réfléchir comme
un humain, il faut aussi agir ... là où on regarde, en fonction de là où nos alliés regardent, là où nos alliés sont, là où
les stuff sont tombés, là où les gens se font le plus tuer"). From the matches already read (out/deep/<match>: duels.parquet,
grenades.parquet, meta.json; no demo read again):
- danger: for each 128 u cell and side, the players killed there and the direction their killer stood in (8 sectors): a
  bot there watches those first (Look.cs);
- throws: for each cell, side and moment of the round (before 25 s, 25-60 s, after), the grenades thrown from there by type
  and where they landed (a 256 u cell); the most thrown one kept with one real throw of it (its spot, its view, jumped or not,
  how it was clicked) and what it did on average (damage, enemies blinded, kills after): a bot there throws it (Move.cs).

Usage: python tools/danger_util.py [maps ...]   ->   out/knowledge/danger_util/<map>.json, exported to coach/danger/ and
coach/util/ (the plugin)."""
import json
import math
import os
import sys
import time
from collections import Counter, defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wily.core import config  # noqa: E402

OUT = os.path.join(config.OUT, "knowledge", "danger_util")
CELL, ZC, LAND = 128.0, 96.0, 256.0
DUEL_COLS = ["t", "killer_side", "victim_side", "killer_X", "killer_Y", "victim_X", "victim_Y", "victim_Z"]
NADE_COLS = ["t", "type", "side", "X", "Y", "Z", "pitch", "yaw", "jump", "walk", "crouch", "click", "land_X", "land_Y", "land_Z",
             "flight_s", "damage", "enemies_blind", "kills_after"]


def cell(side, x, y, z):
    return f"{side}|{int(math.floor(x / CELL))}|{int(math.floor(y / CELL))}|{int(math.floor(z / ZC))}"


def sector(dx, dy):
    return int(((math.degrees(math.atan2(dy, dx)) + 360.0 + 22.5) % 360.0) // 45.0)


def phase(t):
    return 0 if t < 25 else (1 if t < 60 else 2)


def side_of(s):
    s = str(s).upper()
    return "T" if s.startswith("T") else "CT"


def main(maps=None):
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    os.makedirs(OUT, exist_ok=True)
    danger = defaultdict(lambda: defaultdict(lambda: [0] * 9))   # map -> cell -> 8 killer sectors + deaths
    throws = defaultdict(lambda: defaultdict(Counter))             # map -> cell|phase -> (type, land cell) -> n
    best = defaultdict(dict)                                       # map -> (cell|phase, type, land) -> a real throw
    effect = defaultdict(lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))
    t0 = time.time()
    mids = sorted(os.listdir(os.path.join(config.OUT, "deep")))
    n = 0
    for mid in mids:
        d = os.path.join(config.OUT, "deep", mid)
        try:
            mp = (json.load(open(os.path.join(d, "meta.json"), encoding="utf-8")).get("map") or "")
        except (OSError, ValueError):
            continue
        if maps and mp not in maps:
            continue
        try:
            D = pd.read_parquet(os.path.join(d, "duels.parquet"), columns=DUEL_COLS)
            for r in D.itertuples(index=False):
                if pd.isna(r.killer_X) or pd.isna(r.victim_X):
                    continue
                e = danger[mp][cell(side_of(r.victim_side), r.victim_X, r.victim_Y, r.victim_Z)]
                e[sector(r.killer_X - r.victim_X, r.killer_Y - r.victim_Y)] += 1
                e[8] += 1
        except (OSError, ValueError, KeyError):
            pass
        try:
            G = pd.read_parquet(os.path.join(d, "grenades.parquet"), columns=NADE_COLS)
            for r in G.itertuples(index=False):
                if pd.isna(r.X) or pd.isna(r.land_X) or r.type not in ("smoke", "flash", "he", "molotov", "incendiary", "smokegrenade",
                                                                          "flashbang", "hegrenade", "incgrenade"):
                    continue
                k = f"{cell(side_of(r.side), r.X, r.Y, r.Z)}|{phase(float(r.t or 0))}"
                lk = f"{int(math.floor(r.land_X / LAND))}|{int(math.floor(r.land_Y / LAND))}"
                throws[mp][k][(r.type, lk)] += 1
                ef = effect[mp][(k, r.type, lk)]
                ef[0] += float(r.damage or 0); ef[1] += float(r.enemies_blind or 0); ef[2] += float(r.kills_after or 0)
                if (k, r.type, lk) not in best[mp]:   # the first real throw of it (the same each run)
                    best[mp][(k, r.type, lk)] = [round(float(r.X), 1), round(float(r.Y), 1), round(float(r.Z), 1), round(float(r.pitch), 2),
                                                 round(float(r.yaw), 2), bool(r.jump), bool(r.walk), bool(r.crouch), str(r.click or ""),
                                                 round(float(r.land_X), 1), round(float(r.land_Y), 1), round(float(r.land_Z), 1),
                                                 round(float(r.flight_s or 0), 2)]   # its flight: the plugin solves its velocity from it
        except (OSError, ValueError, KeyError):
            pass
        n += 1
        if n % 250 == 0:
            print(f"{n} matches read ({time.time() - t0:.0f} s)", flush=True)
    from wily.training import replay
    for mp in sorted(set(danger) | set(throws)):
        dz = {k: v for k, v in danger[mp].items() if v[8] >= 3}
        ut = {}
        for k, c in throws[mp].items():
            (typ, lk), cnt = max(c.items(), key=lambda x: (x[1], x[0]))
            if cnt < 3:
                continue
            ef = effect[mp][(k, typ, lk)]
            z = lambda x: 0.0 if x != x else x   # NaN (nothing measured) as 0: the plugin's JSON reader refuses NaN (30/10)
            ut[k] = {"type": typ, "n": cnt, "share": round(cnt / sum(c.values()), 2), "throw": best[mp][(k, typ, lk)],
                     "damage": z(round(ef[0] / cnt, 1)), "blind": z(round(ef[1] / cnt, 2)), "kills": z(round(ef[2] / cnt, 2))}
        json.dump({"danger": dz, "util": ut}, open(os.path.join(OUT, f"{mp}.json"), "w", encoding="utf-8"))
        for sub, tab in (("danger", dz), ("util", ut)):
            od = os.path.join(replay.COACH, sub)
            os.makedirs(od, exist_ok=True)
            json.dump({"cell": CELL, "zcell": ZC, "keys": tab}, open(os.path.join(od, f"{mp}.json"), "w", encoding="utf-8"))
        print(mp, len(dz), "danger cells,", len(ut), "throw places", flush=True)
    print(f"over: {n} matches in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or None)
