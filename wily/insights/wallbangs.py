"""The wallbangs of each map (06/10, the user: "en plus des lineups de stuff, sur les entraînements un peu longs (30
minutes), tu me fasses practice des lineups de wallbang").

The demos keep every kill through a wall (player_death's "penetrated"): who shot from where, aiming where, and where the
victim stood. Kills from the same spot (60 units, same height) onto the same place through the same wall (the aim within
12 degrees) are one wallbang, the most killing first: where to stand, where to aim (the most common aim), where the
enemies stand behind it, with which weapon. The training's long sessions put you there with bots behind the wall.
Reads the demos of the base (150 a map at most, the most recent), kept in out/population/wallbangs.json.
Usage: python -m wily.insights.wallbangs [map ...]"""
import json
import os
import sys
import time
from collections import Counter

import numpy as np
import pandas as pd

from wily.core import config

OUT = os.path.join(config.OUT, "population", "wallbangs.json")
PER_MAP = 150
STAND_R, STAND_Z, AIM_DEG, MIN_KILLS = 60.0, 40.0, 12.0, 4
SIDE = {2: "T", 3: "CT"}


def _demos(mp):
    from wily.demos import scan
    from wily.insights import tside
    done = [d for d in scan.demos(mp, 100000) if scan.load(d)]   # every demo scan.py has read
    if len(done) >= PER_MAP:
        return done
    ds = tside._map_dirs().get(mp, [])
    ds = [d for d in ds if config.has_demo(os.path.basename(d))]
    return sorted(ds, key=lambda d: -int(os.path.basename(d)))[:PER_MAP]


def _kills(mid):
    from wily.demos import scan
    k = scan.kills(mid)   # scan.py's pass already read this demo (06/10): no second read of 200 MB
    if k is not None:
        k = k[(k.ateam != k.vteam) & k.ax.notna() & k.vx.notna()]
        return pd.DataFrame({"weapon": k.weapon, "penetrated": k.penetrated, "attacker_X": k.ax, "attacker_Y": k.ay, "attacker_Z": k.az,
                             "attacker_pitch": k.apitch, "attacker_yaw": k.ayaw, "attacker_team_num": k.ateam,
                             "attacker_last_place_name": k.aplace, "user_X": k.vx, "user_Y": k.vy, "user_Z": k.vz,
                             "user_last_place_name": k.vplace, "match": mid})
    from demoparser2 import DemoParser
    p = DemoParser(config.demo(mid))
    k = p.parse_event("player_death", player=["X", "Y", "Z", "pitch", "yaw", "team_num", "last_place_name"])
    if not isinstance(k, pd.DataFrame) or not len(k) or "penetrated" not in k:
        return pd.DataFrame()
    # every kill between enemies: the ones through a wall make the wallbangs, the others say whether the victims stand in
    # plain sight of that spot too (then it is no real wallbang)
    k = k[(k.attacker_team_num != k.user_team_num) & k.attacker_X.notna() & k.user_X.notna()]
    return k[["weapon", "penetrated", "attacker_X", "attacker_Y", "attacker_Z", "attacker_pitch", "attacker_yaw", "attacker_team_num",
              "attacker_last_place_name", "user_X", "user_Y", "user_Z", "user_last_place_name"]].assign(match=mid)


def analyze_map(mp, log=print):
    from wily.core import mapdata
    from wily.demos.map_analysis import humanize
    t0 = time.time()
    ds = _demos(mp)
    K = []
    for d in ds:
        try:
            k = _kills(os.path.basename(d))
        except Exception as e:
            log(f"{mp} {os.path.basename(d)}: unreadable ({e})")
            continue
        if len(k):
            K.append(k)
    if not K:
        return None
    K = pd.concat(K, ignore_index=True)
    K = K[~K.weapon.isin(["hegrenade", "inferno", "molotov", "incgrenade", "world", "knife", "knife_t"])]
    D = K[K.penetrated.fillna(0) == 0]   # the kills in plain sight
    K = K[K.penetrated.fillna(0) > 0]
    cfg = mapdata.get(mp)
    f = cfg.get("px_factor", 1.0)
    px = lambda X, Y: [round((X - cfg["pos_x"]) / cfg["scale"] * f), round((cfg["pos_y"] - Y) / cfg["scale"] * f)]
    cl = []   # [x, y, z, yaw, [rows]]
    wide = len(ds) < 60   # few demos (Overpass: 29): a wider spot and aim, or nothing groups
    sr, ad = (STAND_R * 1.8, AIM_DEG * 1.7) if wide else (STAND_R, AIM_DEG)
    for i, b in zip(K.index, K.itertuples()):
        for c in cl:
            dy = abs(((c[3] - b.attacker_yaw) + 180) % 360 - 180)
            if abs(c[0] - b.attacker_X) < sr and abs(c[1] - b.attacker_Y) < sr and abs(c[2] - b.attacker_Z) < STAND_Z and dy < ad:
                c[4].append(i)
                n = len(c[4])
                c[0] += (b.attacker_X - c[0]) / n
                c[1] += (b.attacker_Y - c[1]) / n
                break
        else:
            cl.append([b.attacker_X, b.attacker_Y, b.attacker_Z, b.attacker_yaw, [i]])
    out = []
    small = len(ds) < 60   # few demos (Overpass: 29): 3 kills from 2 matches make a wallbang
    for c in cl:
        x = K.loc[c[4]]
        if len(x) < (3 if small else MIN_KILLS) or x.match.nunique() < (2 if small else 3):
            continue
        P, Y = x.attacker_pitch.to_numpy(float), x.attacker_yaw.to_numpy(float)
        dyy = np.abs(((Y[:, None] - Y[None, :]) + 180) % 360 - 180)
        b = x.iloc[int(np.argmax(((np.abs(P[:, None] - P[None, :]) < 3) & (dyy < 3)).sum(1)))]
        vic, seen = [], []
        for vx, vy, vz in zip(x.user_X, x.user_Y, x.user_Z):
            if all(np.hypot(vx - a, vy - b_) > 90 for a, b_, _ in seen):
                seen.append((vx, vy, vz))
            if len(seen) >= 4:
                break
        # a real wallbang: from that spot, the ones standing there are mostly killed through the wall, not in plain sight
        # (06/10, the user: "c'est un travers porte, c'est nul", "juste dans un coin d'une caisse", "je suis en face du
        # mec, c'est pas un wallbang du tout")
        sx, sy, sz = float(x.attacker_X.median()), float(x.attacker_Y.median()), float(b.attacker_Z)
        VX, VY = x.user_X.to_numpy(float), x.user_Y.to_numpy(float)
        yw = np.radians(x.attacker_yaw.to_numpy(float))
        my = float(np.degrees(np.arctan2(np.sin(yw).mean(), np.cos(yw).mean())))
        # the same line of fire only (aim within 12 degrees): the kills in plain sight from there, onto them
        d0 = D[(np.abs(D.attacker_X - sx) < sr) & (np.abs(D.attacker_Y - sy) < sr) & (np.abs(D.attacker_Z - sz) < STAND_Z)
               & (np.abs(((D.attacker_yaw - my) + 180) % 360 - 180) < ad)]
        direct = int(sum(np.hypot(VX - vx, VY - vy).min() < 100 for vx, vy in zip(d0.user_X, d0.user_Y))) if len(d0) else 0
        wall = len(x) / (len(x) + direct)
        if wall < 0.75:   # 09/10, Nuke's B Site at 57%: "c'est juste un tir à travers la petite barrière jaune" (seen through)
            continue
        side = Counter(x.attacker_team_num.map(SIDE)).most_common(1)[0][0]
        wc = Counter(x.weapon)
        fz = Counter(x.attacker_last_place_name.dropna()).most_common(1)
        tz = Counter(x.user_last_place_name.dropna()).most_common(1)
        out.append({"side": side, "from": humanize(fz[0][0], mp) if fz else "?", "to": humanize(tz[0][0], mp) if tz else "?",
                    "from_key": fz[0][0] if fz else None, "to_key": tz[0][0] if tz else None,
                    "pos": [round(float(x.attacker_X.median()), 1), round(float(x.attacker_Y.median()), 1), round(float(b.attacker_Z), 1)],
                    "ang": [round(float(b.attacker_pitch), 2), round(float(b.attacker_yaw), 2)],
                    "setpos": f"setpos {x.attacker_X.median():.1f} {x.attacker_Y.median():.1f} {b.attacker_Z:.1f}; setang {b.attacker_pitch:.2f} {b.attacker_yaw:.2f} 0",
                    "victims": [[round(float(a), 1), round(float(b_), 1), round(float(z), 1)] for a, b_, z in seen],
                    "px": px(float(x.attacker_X.median()), float(x.attacker_Y.median())),
                    "to_px": px(float(x.user_X.median()), float(x.user_Y.median())), "level": mapdata.level_of(cfg, float(b.attacker_Z)),
                    "n": int(len(x)), "matches": int(x.match.nunique()), "weapons": {w: round(100 * n / len(x)) for w, n in wc.most_common(3)},
                    "wall": round(wall, 2)})
    out.sort(key=lambda o: -o["n"] * o["wall"])
    log(f"{mp}: {len(out)} wallbangs from {len(K)} kills through walls in {len(ds)} demos ({time.time() - t0:.0f} s)")
    return out[:24]


def run(maps=None, log=print):
    from wily.insights import tside
    try:
        cur = json.load(open(OUT, encoding="utf-8"))
    except (OSError, ValueError):
        cur = {}
    todo = maps or sorted(m for m, ds in tside._map_dirs().items() if len(ds) >= 20 and m.startswith("de_"))
    res = {"time": time.strftime("%Y-%m-%d"), "maps": dict(cur.get("maps") or {})}
    for mp in todo:
        try:
            r = analyze_map(mp, log)
        except Exception as e:
            log(f"{mp}: wallbangs unavailable ({e})")
            r = None
        if r is not None:   # none found is an answer too: the old ones (weak ones included) go
            res["maps"][mp] = r
            config.write_json(OUT, res)   # map by map: a long run keeps what it found
    return res


def load(mp=None):
    try:
        d = json.load(open(OUT, encoding="utf-8")).get("maps") or {}
    except (OSError, ValueError):
        d = {}
    return d.get(mp) or [] if mp else d


if __name__ == "__main__":
    config.low_priority()
    run(sys.argv[1:] or None)
