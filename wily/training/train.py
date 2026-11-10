"""The training session: one Play, the whole block in the time you chose, on the training server (replay.py).

Three blocks per map, in this order: aim on the map, stuff, situations.
- Aim: your real duel spots. You stand where you fought in your matches, and the bots appear one by one where your
  enemies were in those duels (they hold the spot and shoot back). The zones where you died most come first.
- Stuff: the lineups your plan recommends for the zones you play. A new one is guided (exact spot and aim, how to
  throw); once you landed it, only the spot and how; then only the spot.
- Situations: your replays (lost 1v1/1v2, opening deaths not traded…).
Everything comes back by Leitner boxes: a miss comes back at the next session, a success later and later; the rest of
each block is drawn at random among the important ones. Each drill scores points (streaks multiply them): XP, levels.

Maps: one map, a random one (weighted by what you play), or a mix of up to 3 (one changelevel per map)."""
import copy
import json
import math
import os
import random
import re
import threading
import time
from collections import Counter

import numpy as np
import pandas as pd

from wily.core import config
from wily.training import crossfire
from wily.training import momentum
from wily.training import execs
from wily.core import i18n   # i18n.tr: train.py's own tr is a rifle
from wily.training import replay

STATE_F = os.path.join(config.OUT, "train_progress.json")
SITES_F = os.path.join(config.OUT, "train_sites.json")
SESS = os.path.join(replay.COACH, "sessions")
# share of the time of each block: defending a site (CT), the push routes with their prefires (T), the stuff, the
# situations (04/10: "a CT training, then a T one: the push routes"); a warm-up (5 min) is the first two only
SPLIT = {"defend": 0.17, "push": 0.17, "aim": 0.34, "nade": 0.2, "situation": 0.46, "wallbang": 0.12}   # before 06/10 (kept for the old sessions' files)
# the warm-up (06/10, the user: "tout l'entraînement sur le même serveur comme avant, le bouton warmup pour tout lancer:
# de l'aim, de la défense de bomb site, du chemin de prefire, du stuff, du wallbang"): one session in that order, each
# part's share of the time by the session's length (5 min: the hands only)
ORDER = ["aim", "defend", "push", "nade", "wallbang", "situation", "momentum"]   # momentum: a focus block only (14/10)


def splits(minutes):
    if minutes <= 5:
        return {"aim": 0.4, "defend": 0.3, "push": 0.3}
    if minutes <= 10:
        return {"aim": 0.2, "defend": 0.15, "push": 0.15, "nade": 0.2, "wallbang": 0.1, "situation": 0.2}
    if minutes <= 20:
        return {"aim": 0.15, "defend": 0.15, "push": 0.15, "nade": 0.15, "wallbang": 0.1, "situation": 0.3}
    return {"aim": 0.12, "defend": 0.15, "push": 0.15, "nade": 0.15, "wallbang": 0.12, "situation": 0.31}
WARMUP = {"defend": 0.5, "push": 0.5, "aim": 1.0}
# 07/10, the user: "si je change le temps ça change les timing de toutes les parties, certains temps enlèvent ou ajoutent
# des trucs": the aim first (2 to 5 min), then each map's parts in that order while their least useful time fits (a
# defense of 100 s, a prefire of 75 s...), the time left shared by weight; a map without room for both is left out
PART_MIN = {"defend": 100, "push": 75, "nade": 80, "situation": 90, "wallbang": 60}
PART_W = {"defend": 0.2, "push": 0.2, "nade": 0.2, "situation": 0.3, "wallbang": 0.1}
PART_ORDER = ["defend", "push", "nade", "situation", "wallbang"]   # how parts come in as the time grows
MAP_MIN = 175   # a map keeps a defense and a prefire at least, or it is left out


def aim_seconds(minutes):
    if minutes <= 5:   # 07/10, the user: "sur 5 min pas d'aim et 1 map max"
        return 0
    return int(min(300, max(120, minutes * 60 * 0.15)))


def parts_for(minutes, chosen, has=lambda mp, k: True, first=None):
    """-> (the aim's seconds, [(map, [(kind, seconds), ...]), ...]) in the session's order. has(map, kind): whether that
    part has something there (no defense on a hostage map); first(map): the kind to put first (your weak side there)."""
    total = int(minutes * 60)
    aim = aim_seconds(minutes)
    left = max(0, total - aim)
    keep = list(chosen)[:1] if minutes <= 5 else list(chosen)
    while len(keep) > 1 and left / len(keep) < MAP_MIN:   # too short for every map: the first ones
        keep.pop()
    out = []
    for mp in keep:
        budget = left / len(keep)
        kinds = [k for k in PART_ORDER if has(mp, k)]
        f = first(mp) if first else None
        if f in kinds:
            kinds.remove(f)
            kinds.insert(0, f)
        took, used = [], 0
        for k in kinds:
            if used + PART_MIN[k] > budget:
                break
            took.append(k)
            used += PART_MIN[k]
        if not took and kinds:   # less than any part: the first one anyway
            took = [kinds[0]]
            used = PART_MIN[kinds[0]]
        w = sum(PART_W[k] for k in took) or 1.0
        extra = max(0.0, budget - used)
        secs = {k: PART_MIN[k] + extra * PART_W[k] / w for k in took}
        out.append((mp, [(k, int(secs[k])) for k in ORDER if k in secs]))
    return aim, out
WARMUP_MIN = 5
# Prepare's focus block (13/10, the user: "pouvoir jouer intensivement certains blocs, 10 min de stuff only, 10 min de
# défense de bombsite only"): one module for the whole time, on one map
# 14/10, Momentum (rework_entrainement.md, section 9: "a dedicated movement training mode"): moving on the real maps,
# a focus block of its own, not in the full session until the training level shares its time out
# the parts put aside for this release (28/10, the user: "cette partie-là, on peut la mettre de côté pour la prochaine
# release, la cacher à tous les utilisateurs": Momentum, till his own jumps are recorded): out of the modules offered and of
# the sessions; COACH_SHOW_HIDDEN=1 (a lab of his) brings them back
HIDDEN = () if os.environ.get("COACH_SHOW_HIDDEN") else ("momentum",)
FOCUS = tuple(k for k in ("crossfire", "defend", "push", "nade", "wallbang", "situation", "momentum") if k not in HIDDEN)
FOCUS_REPEAT = 3   # a focus block plays each drill three times at most
EST = {"defend": 110, "push": 75, "aim": 85, "nade": 40, "situation": 45, "wallbang": 60, "momentum": 65}   # seconds a drill takes, about (with a retry)
RIFLE = {2: "weapon_ak47", 3: "weapon_m4a1"}
PRIMARY = {"AK-47": "ak47", "M4A4": "m4a1", "M4A1-S": "m4a1_silencer", "AWP": "awp", "Galil AR": "galilar",
           "FAMAS": "famas", "SG 553": "sg556", "AUG": "aug", "SSG 08": "ssg08", "MP9": "mp9", "MAC-10": "mac10"}
NADE_ITEM = {"smoke": "weapon_smokegrenade", "flash": "weapon_flashbang", "he": "weapon_hegrenade",
             "molotov": {2: "weapon_molotov", 3: "weapon_incgrenade"}}


# ---------------------------------------------------------------- progress (XP, Leitner boxes)

def progress():
    try:
        p = json.load(open(STATE_F, encoding="utf-8"))
    except (OSError, ValueError):
        p = {}
    p.setdefault("xp", 0)
    p.setdefault("sessions", [])
    p.setdefault("items", {})
    p.setdefault("read", 0)
    return p


def _save(p):
    json.dump(p, open(STATE_F, "w", encoding="utf-8"), ensure_ascii=False)


def level(xp):
    """Level n needs 300 * n * (n - 1) / 2 XP: 300 to reach level 2, 900 to level 3, 1800 to level 4…"""
    n = int((1 + math.sqrt(1 + 8 * xp / 300)) / 2)
    lo, hi = 300 * n * (n - 1) // 2, 300 * (n + 1) * n // 2
    return {"level": n, "xp": xp, "from": lo, "to": hi}


def ingest():
    """The plugin's results since last time: points, boxes of the items, finished sessions."""
    p = progress()
    try:
        lines = open(os.path.join(replay.COACH, "results.jsonl"), encoding="utf-8").read().splitlines()
    except OSError:
        return p
    n = len(p["sessions"])
    for ln in lines[p["read"]:]:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if not r.get("session"):
            continue
        if r.get("end"):
            s = next((x for x in p["sessions"] if x["id"] == r["session"]), None)
            if s is not None:
                s.update(done=True, points=r.get("points", 0), ok=r.get("ok", 0), drills=r.get("drills", 0))
            continue
        p["xp"] += int(r.get("points") or 0)
        it = p["items"].setdefault(r["drill"], {"box": 0, "next": 0, "n": 0, "ok": 0})
        it["n"] += 1
        if r.get("ok"):
            it["ok"] += 1
            it["box"] = min(3, it["box"] + 1)
            it["next"] = n - 1 + 2 ** it["box"]   # 2, 4, 8 sessions later (n: sessions so far, this one included)
        else:
            it["box"] = 0
            it["next"] = n   # the next session
        it["last"] = r.get("outcome")
        if r.get("pops") and r.get("target"):   # a lineup: where your throws popped (07/10)
            it["pops"] = (it.get("pops") or [])[-8:] + [list(map(float, q[:2])) for q in r["pops"]]
            it["target"] = [float(v) for v in r["target"][:2]]
    p["read"] = len(lines)
    _save(p)
    return p


def _pick(cands, n, items, nsess, key=lambda c: c["id"], weight=lambda c: 1.0):
    """Due items first (the ones missed come back), then new or not yet due ones at random, weighted by importance."""
    due = [c for c in cands if key(c) in items and items[key(c)]["next"] <= nsess]
    due.sort(key=lambda c: (items[key(c)]["box"], items[key(c)]["next"]))
    rest = [c for c in cands if c not in due]
    out = due[:n]
    if len(out) < n and rest:
        w = np.array([max(0.05, weight(c)) * (2.0 if key(c) not in items else 1.0) for c in rest], dtype=float)
        k = min(n - len(out), len(rest))
        idx = np.random.choice(len(rest), size=k, replace=False, p=w / w.sum())
        out += [rest[i] for i in idx]
    return out


# ---------------------------------------------------------------- the drills of a map

_MY = {}


def _my_matches(sid, mp=None):
    """Your matches with a demo: [(match, map)]. Their maps from the ledger of the base's matches, the list kept while
    your matches folder is the same, a minute at most (22/10: Prepare's first answer opened your 124 meta.json four
    times a map on the hard disk)."""
    md = os.path.join(config.player_dir(sid), "matches")
    try:
        names = tuple(sorted(os.listdir(md))) if os.path.isdir(md) else ()
    except OSError:
        names = ()
    hit = _MY.get(str(sid))
    if not hit or hit[1] != names or time.time() - hit[0] > 60:
        try:
            from wily.core import ledger
            facts = ledger.match_facts()
        except Exception:
            facts = {}
        allm = []
        for mid in names:
            deep = os.path.join(config.OUT, "deep", mid)
            m = (facts.get(mid) or {}).get("map")
            if not m:
                try:
                    m = json.load(open(os.path.join(deep, "meta.json"), encoding="utf-8"))["map"]
                except (OSError, ValueError, KeyError):
                    continue
            if os.path.exists(os.path.join(deep, "duels.parquet")):
                allm.append((mid, m))
        hit = _MY[str(sid)] = (time.time(), names, allm)
    return [x for x in hit[2] if mp is None or x[1] == mp]


def maps(sid):
    """Your maps with their number of matches (with demo)."""
    c = {}
    for _, m in _my_matches(sid):
        c[m] = c.get(m, 0) + 1
    return dict(sorted(c.items(), key=lambda x: -x[1]))


def base_maps(min_matches=20):
    """The bomb maps the base covers (its site data comes with the app), the most played first: one you have no demo of
    trains on the base's own spots, ways and lineups (09/10, his warm-up: "trainer les maps sur lesquelles je n'ai pas
    forcément de démo téléchargée, puisque j'ai le dataset des matchs"). Its situations need your demos: none there."""
    try:
        C = json.load(open(SITES_F, encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {mp: int(v.get("n") or 0) for mp, v in C.items()
           if isinstance(v, dict) and v.get("sites") and int(v.get("n") or 0) >= min_matches}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _angle(a, b):
    d = np.asarray(b, float) - np.asarray(a, float)
    yaw = math.degrees(math.atan2(d[1], d[0]))
    pitch = -math.degrees(math.atan2(d[2], math.hypot(d[0], d[1])))
    return [round(pitch, 1), round(yaw, 1)]


def aim_drills(sid, mp):
    """Your duel spots on this map: you where you fought, the enemies where they were (one drill per zone and side)."""
    sid = str(sid)
    rows = []
    for mid, _ in _my_matches(sid, mp):
        deep = os.path.join(config.OUT, "deep", mid)
        D = pd.read_parquet(os.path.join(deep, "duels.parquet"))
        D["killer"], D["victim"] = D.killer.astype(str), D.victim.astype(str)
        L = pd.read_parquet(os.path.join(deep, "loadout.parquet"), columns=["round", "steamid", "primary"])
        L = L[L.steamid.astype(str) == sid].set_index("round").primary
        for _, d in D[(D.killer == sid) | (D.victim == sid)].iterrows():
            me = "killer" if d.killer == sid else "victim"
            en = "victim" if me == "killer" else "killer"
            if d[f"{me}_side"] == d[f"{en}_side"]:
                continue
            rows.append({"side": d[f"{me}_side"], "zone": d[f"{me}_zone"], "died": me == "victim", "weapon": L.get(d["round"]),
                         "me": (float(d[f"{me}_X"]), float(d[f"{me}_Y"]), float(d[f"{me}_Z"])),
                         "en": (float(d[f"{en}_X"]), float(d[f"{en}_Y"]), float(d[f"{en}_Z"])),
                         "en_zone": d[f"{en}_zone"]})
    if not rows:
        return []
    R = pd.DataFrame(rows)
    out = []
    for (side, zone), g in R.groupby(["side", "zone"]):
        if len(g) < 3 or not isinstance(zone, str) or zone in ("?", ""):
            continue
        # your most frequent spot in the zone, and only the duels you took from there: their enemies were in sight
        P = np.array(g.me.tolist())
        near = None
        for rad in (220, 350):
            d2 = np.sqrt(((P[:, None, :2] - P[None, :, :2]) ** 2).sum(-1))
            close = (d2 <= rad) & (np.abs(P[:, None, 2] - P[None, :, 2]) < 100)
            k = int(np.argmax(close.sum(1) * 10 + g.died.to_numpy()))
            near = g[close[k]]
            mine = P[k]
            enemies, seen = [], []
            E = list(zip(near.en, near.en_zone))
            random.shuffle(E)
            for e, ez in E:   # distinct spots (150 u apart), not too far, 5 at most
                if all(math.dist(e, s_) > 150 for s_ in seen) and 150 < math.dist(e, mine) < 1800:
                    seen.append(e)
                    enemies.append({"pos": [round(v, 1) for v in e], "zone": replay_zone(ez, mp)})
                if len(enemies) >= 5:
                    break
            if len(enemies) >= 2:
                break
        if len(enemies) < 2:
            continue
        team = 2 if side == "T" else 3
        w = g.weapon.dropna()
        wp = PRIMARY.get(w.mode().iloc[0]) if len(w) else None
        died = int(near.died.sum())
        out.append({"id": f"aim:{mp}:{side}:{zone}", "kind": "aim", "map": mp, "title": f"{replay_zone(zone, mp)} ({side})",
                    "tip": i18n.tr("{n} enemies, one by one, where they were when you fought here", n=len(enemies)) + (" · " + i18n.tr("you died here {n}×", n=died) if died else ""),
                    "team": team, "me": {"pos": [round(float(v), 1) for v in mine], "ang": _angle(mine, enemies[0]["pos"])},
                    "weapons": ["weapon_knife", f"weapon_{wp}" if wp else RIFLE[team]],
                    "bot_weapons": ["weapon_knife", RIFLE[5 - team]],
                    "bots": [{"pos": e["pos"], "ang": _angle(e["pos"], mine), "zone": e["zone"]} for e in enemies],
                    "weight": 1 + 2 * died + len(near)})
    return out


# ---------------------------------------------------------------- the aim block on an aim range (06/10)

# 07/10: not aim_map any more. Its file (maps/aim_map.vpk, 2023, like fy_pool_day.vpk) is the only one of the game's maps
# without Valve's signature: the game refuses it from a server ("Signature failed for ...aim_map.vpk", then back to the
# menu at SIGNONSTATE_PRESPAWN; 06/10 19:57 and 07/10 11:31). Pool Day (Arms Race, signed): 16 enabled spawns a side on
# one level, 600-1,300 u across the pool, a duel's distance; the plugin drops a spot of theirs you can't see
AIM_FALLBACK = "ar_pool_day"


def aim_map():
    """07/10, the user: "j'irai récupérer une nouvelle carte d'aim ... je te donnerai le lien Steam": Aim Botz (Steam
    Workshop 3070244462) when the game has it (the player subscribed), else Pool Day."""
    return "aim_botz" if replay.client_workshop(replay.WORKSHOP["aim_botz"]) else AIM_FALLBACK


AIM_MAP = AIM_FALLBACK   # the fallback; the session asks aim_map()


def _my_guns(sid):
    """The guns you play (your demos): your T rifle, your CT rifle, your pistol (the default one unless you play another
    one a lot)."""
    t, ct, pist = Counter(), Counter(), Counter()
    for mid, _ in _my_matches(str(sid)):
        try:
            L = pd.read_parquet(os.path.join(config.OUT, "deep", mid, "loadout.parquet"), columns=["steamid", "side", "primary", "pistol"])
        except Exception:
            continue
        L = L[L.steamid.astype(str) == str(sid)]
        t.update(L[L.side == "T"].primary.dropna())
        ct.update(L[L.side == "CT"].primary.dropna())
        pist.update(L.pistol.dropna())
    rifle = lambda c, names, dflt: next((n for n, _ in c.most_common() if n in names and replay._item(n)), dflt)
    tr = rifle(t, ("AK-47", "Galil AR", "SG 553"), "AK-47")
    cr = rifle(ct, ("M4A1-S", "M4A4", "FAMAS", "AUG"), "M4A1-S")
    n = sum(pist.values()) or 1
    pi = next((p for p, k in pist.most_common() if p not in ("Glock-18", "USP-S", "P2000") and k >= 0.15 * n and replay._item(p)), "USP-S")
    return tr, cr, pi


def aim_range_drills(sid, secs):
    """The aim block (06/10, the user: "fais le travail d'aim sur une map d'aim, une map d'entraînement d'aim, et
    ensuite lance les maps que j'ai choisies"; the duel spots on the maps spawned in front of him or behind him and
    prefired him): on an aim range (AIM_MAP), targets across the map in front of you: still ones to flick to, strafing
    ones, then duels that shoot back only after a player's reaction time; your guns. As many as the block's time holds."""
    tr, cr, pi = _my_guns(sid)
    w = lambda n: replay._item(n) or "weapon_ak47"
    mp = aim_map()
    team = 3 if mp == "aim_botz" else 2   # Aim Botz: you on its CT spawn in the middle, the targets on its T spawns
    menu = [
        # 09/10, his warm-up: "j'aimerais bien avoir plus de bots pour l'aim": twice as many targets out at once
        {"variant": "flick", "gun": tr, "secs": 60, "count": 6, "goal": 30,
         "tip": i18n.tr("still targets across the map: flick to the head, one bullet · they don't shoot")},
        {"variant": "strafe", "gun": cr, "secs": 50, "count": 4, "goal": 16,
         "tip": i18n.tr("strafing targets: stop, then shoot (counter-strafe) · they don't shoot")},
        {"variant": "duel", "gun": tr, "secs": 60, "count": 3, "goal": 14,
         "tip": i18n.tr("duels: they shoot back once they've seen you a player's reaction time · you respawn")},
        {"variant": "flick", "gun": pi, "secs": 45, "count": 5, "goal": 18,
         "tip": i18n.tr("pistol: still targets, head only · they don't shoot")},
    ]
    out, used, k = [], 0, 0
    while used < secs - 20 and k < max(8, secs // 50):   # a focus block: as many as its time holds
        m = menu[k % len(menu)]
        k += 1
        name = {"flick": "FLICKS", "strafe": "STRAFE", "duel": "DUELS"}[m["variant"]]
        out.append({"id": f"range:{m['variant']}:{m['gun']}", "kind": "aim", "mode": "range", "variant": m["variant"], "map": mp,
                    "title": f"{name} · {m['gun']}", "tip": m["tip"], "team": team,
                    "weapons": ["weapon_knife", w(m["gun"])] if m["gun"] == pi else ["weapon_knife", "weapon_glock", w(m["gun"])],
                    "bot_weapons": ["weapon_knife", RIFLE[3]], "seconds": m["secs"], "count": m["count"], "goal": m["goal"],
                    "clock": m["secs"]})
        used += m["secs"] + 12
    return out


# a prefire's angles by the bots' level (06/10, the user: "en expert les bots vraiment partout, en normal le maximum
# mais un peu moins, en simple vraiment beaucoup moins: les positions les plus fortes, les plus jouées")
PREFIRE_N = {0: 4, 1: 7, 2: 9, 3: 10}
# its CTs that react as the base's do (23/10, the user: "quelques CT qui réagissent comme ceux de la base"): none at Easy,
# then one, two, three of them, never the first one met (it would teach nothing), drawn anew each time
PREFIRE_REACT = {0: 0, 1: 1, 2: 2, 3: 3}


def _by_level(d, difficulty):
    b = d["bots"][:PREFIRE_N.get(int(difficulty), 9)]   # the most played first
    m = min((x.get("at", 0) for x in b), default=0)
    d["bots"] = [dict(x, at=round(x.get("at", 0) - m, 1)) for x in b]
    later = [x for x in d["bots"] if x.get("seq", 0) >= 1]
    for x in random.sample(later, min(len(later), PREFIRE_REACT.get(int(difficulty), 2))):
        x["react"] = True
    return d


# ---------------------------------------------------------------- aim like on practice servers

def _cells(P, cell=110):
    """Positions grouped by cells of 110 u (and height): (count, median position) the busiest first."""
    if not len(P):
        return []
    P = np.asarray(P, float)
    key = np.stack([np.floor(P[:, 0] / cell), np.floor(P[:, 1] / cell), np.floor(P[:, 2] / 90)], 1)
    _, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    out = []
    for k in range(len(cnt)):
        C = P[inv.ravel() == k]
        med = np.median(C, axis=0)
        out.append((int(cnt[k]), C[int(np.argmin(np.linalg.norm(C - med, axis=1)))]))   # a real position, not a blend
    return sorted(out, key=lambda x: -x[0])


def _spread(cands, n, gap=160, keep=lambda p: True):
    out = []
    for c, p in cands:
        if keep(p) and all(math.dist(p, q) > gap for _, q in out):
            out.append((c, p))
        if len(out) >= n:
            break
    return out


def _hold_t(CP, tm, p):
    """When the CTs fight from that spot (median time in the round): the peek timing."""
    near = np.hypot(CP[:, 0] - p[0], CP[:, 1] - p[1]) < 110
    return round(float(np.median(tm[near] if near.any() else tm)), 1)


def site_data(mp):
    """From every demo of the map (the whole base, not only yours): for each bomb site, the spots CTs hold it from (the
    duels of the first 75 s of a round, CT within 1500 u of the site) and where the Ts come from (entrance zones, with
    their spots). Each spot keeps where the Ts it fought stood ("seen", 40 at most: the two saw each other, so a way
    that passes there is in its sight, 06/10) and how often its CTs fought crouched. Cached per map, rebuilt when the
    base grows."""
    try:
        cache = json.load(open(SITES_F, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    dirs = _map_dirs(mp)
    # computed again when the map has a quarter more matches (the base grows by itself: not at every Play)
    if mp in cache and cache[mp].get("v") == 6 and cache[mp].get("n", 0) >= 0.8 * len(dirs):
        return cache[mp]
    # never the base's spots replaced by a count from far fewer demos (07/10: a player's app holds the base's sites but
    # not its demos; an older version's sites, rebuilt there from the player's own few matches, came out empty)
    if mp in cache and cache[mp].get("sites") and (config.role() == "client" or len(dirs) < 0.5 * cache[mp].get("n", 0)):
        return cache[mp]
    cols = ["t", "killer_side", "victim_side", "killer_zone", "victim_zone", "killer_crouch", "victim_crouch",
            "killer_X", "killer_Y", "killer_Z", "victim_X", "victim_Y", "victim_Z"]
    parts = []
    for d in dirs:
        try:
            D = pd.read_parquet(os.path.join(config.OUT, "deep", d, "duels.parquet"), columns=cols)
        except Exception:
            continue
        D = D[(D.t <= 75) & (((D.killer_side == "CT") & (D.victim_side == "T")) | ((D.killer_side == "T") & (D.victim_side == "CT")))]
        if not len(D):
            continue
        ck = (D.killer_side == "CT").to_numpy()
        col = lambda a, ct: np.where(ck == ct, D[f"killer_{a}"].to_numpy(), D[f"victim_{a}"].to_numpy())
        parts.append(pd.DataFrame({"time": D.t.to_numpy(float),
                                   "ctx": col("X", True), "cty": col("Y", True), "ctz": col("Z", True), "ct_zone": col("zone", True),
                                   "ct_crouch": col("crouch", True), "tx": col("X", False), "ty": col("Y", False), "tz": col("Z", False),
                                   "t_zone": col("zone", False)}))
    R = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    sites = {}
    if len(R):
        R = R.dropna(subset=["ctx", "cty", "ctz", "tx", "ty", "tz"])
        CA = R[["ctx", "cty", "ctz"]].to_numpy(float)
        rng = np.random.default_rng(0)
        for z in sorted({z for z in R.ct_zone.dropna().unique() if "Bombsite" in str(z)}):
            S = R[R.ct_zone == z]
            if len(S) < 25:
                continue
            cen = np.median(S[["ctx", "cty", "ctz"]].to_numpy(float), axis=0)
            near = R[(np.linalg.norm(CA - cen, axis=1) < 1500) & (np.abs(CA[:, 2] - cen[2]) < 300)]   # its own floor (Nuke: A is above B)
            ents = []
            for tz, g in near.groupby("t_zone"):   # where the Ts were when they fought the site's CTs
                if not isinstance(tz, str) or tz == z or len(g) < 12:
                    continue
                T = g[["tx", "ty", "tz"]].to_numpy(float)
                dist = float(np.median(np.linalg.norm(T - cen, axis=1)))
                if dist < 500:
                    continue
                CP = g[["ctx", "cty", "ctz"]].to_numpy(float)
                holds = _spread(_cells(CP), 12)   # the CT spots facing that entrance
                tm = g.time.to_numpy()
                spawn = _spread(_cells(T), 3, gap=200, keep=lambda p: math.dist(p, cen) > 700)
                if len(holds) < 4 or not spawn:
                    continue
                tcen = np.median(T, axis=0)
                cr = g.ct_crouch.eq(True).to_numpy()
                hs = []
                for c, p in holds:
                    m = (np.hypot(CP[:, 0] - p[0], CP[:, 1] - p[1]) < 110) & (np.abs(CP[:, 2] - p[2]) < 90)
                    Tm = T[m]
                    if len(Tm) > 40:
                        Tm = Tm[rng.choice(len(Tm), 40, replace=False)]
                    hs.append({"pos": [round(float(v), 1) for v in p], "ang": _angle(p, tcen), "n": c, "t": _hold_t(CP, tm, p),
                               "zone": _hold_zone(CP, g.ct_zone.to_numpy(), p, mp), "seen": [[round(float(v)) for v in q] for q in Tm],
                               "crouch": round(float(cr[m].mean()), 2) if m.any() else 0.0})
                ents.append({"zone": tz, "n": int(len(g)), "dist": round(dist),
                             "start": [round(float(v), 1) for v in _spread(_cells(T), 1)[0][1]], "holds": hs,
                             "spawns": [[round(float(v), 1) for v in p] for _, p in spawn]})
            ents.sort(key=lambda e: -e["n"])
            spot = _spread(_cells(S[["ctx", "cty", "ctz"]].to_numpy(float)), 1)[0][1]   # the CTs' favourite spot on the site
            sites[z] = {"center": [round(float(v), 1) for v in cen], "defend": [round(float(v), 1) for v in spot], "entrances": ents[:4]}
    cache[mp] = {"n": len(dirs), "v": 6, "sites": sites}
    json.dump(cache, open(SITES_F, "w", encoding="utf-8"))
    return cache[mp]


_PLANTS = {}


def _plant_spot(mp, letter, S):
    """Where the base's Ts plant on a site, its busiest 48 u cell: on the plant zone itself, a spot players stand on
    (09/10, his Inferno defense: "fais-moi spawn là où on peut planter, là je spawn juste à côté du bombsite"; the
    CTs' favourite spot of the site can be next to it). Its height: where the base's players stood there, on the site's
    floor (Nuke's A is above B). None without enough plants."""
    key = (mp, letter)
    if key not in _PLANTS:
        pts = []
        for d in _map_dirs(mp)[-400:]:
            try:
                R = pd.read_parquet(os.path.join(config.OUT, "deep", d, "rounds.parquet"), columns=["plant_site", "plant_X", "plant_Y"])
            except Exception:
                continue
            R = R[(R.plant_site == letter) & R.plant_X.notna() & R.plant_Y.notna()]
            pts += R[["plant_X", "plant_Y"]].values.tolist()
        _PLANTS[key] = np.array(pts, float).reshape(-1, 2)
    P = _PLANTS[key]
    if len(P) < 20 or not S.get("center"):
        return None
    cx, cy = (P[:, 0] // 48).astype(int), (P[:, 1] // 48).astype(int)
    (bx, by), _ = Counter(zip(cx, cy)).most_common(1)[0]
    x, y = np.median(P[(cx == bx) & (cy == by)], axis=0)
    Z = _zone_samples(mp)
    zs = Z.Z.to_numpy(float)[(np.hypot(Z.X.to_numpy(float) - x, Z.Y.to_numpy(float) - y) < 48) & (np.abs(Z.Z.to_numpy(float) - S["center"][2]) < 160)]
    z = float(np.median(zs)) if len(zs) >= 5 else float(S["center"][2])
    return [round(float(x), 1), round(float(y), 1), round(z + 2, 1)]


def _site_holds(S):
    """A site's CT spots from all its entrances, the ones 160 u apart merged (their counts and their foes summed), the
    most held first."""
    out = []
    for h in sorted((h for e in S["entrances"] for h in e["holds"]), key=lambda h: -h["n"]):
        same = next((q for q in out if math.dist(h["pos"], q["pos"]) <= 160), None)
        if same:
            same["n"] += h["n"]
            same["seen"] = same["seen"] + list(h.get("seen") or [])
            continue
        out.append(dict(h, seen=list(h.get("seen") or [])))
    return out


def _sees(h, P, r=160.0, dz=110.0):
    """How many of a CT spot's foes stood on that way (its points within r, same floor): the duels prove the two saw
    each other, so the way passes in the spot's sight. 0: never seen fighting from there."""
    Q = np.array(h.get("seen") or [], float).reshape(-1, 3)
    W = np.asarray(P, float)[:, :3]
    if not len(Q) or not len(W):
        return 0
    W = W[::3] if len(W) > 90 else W
    m = (np.hypot(Q[:, None, 0] - W[None, :, 0], Q[:, None, 1] - W[None, :, 1]) < r) & (np.abs(Q[:, None, 2] - W[None, :, 2]) < dz)
    return int(m.any(1).sum())


def _first_seen(h, P, r=160.0, dz=110.0):
    """The first frame of a way in a CT spot's sight (one of its foes' spots), -1: never."""
    Q = np.array(h.get("seen") or [], float).reshape(-1, 3)
    W = np.asarray(P, float)[:, :3]
    if not len(Q) or not len(W):
        return -1
    m = ((np.hypot(W[:, None, 0] - Q[None, :, 0], W[:, None, 1] - Q[None, :, 1]) < r) & (np.abs(W[:, None, 2] - Q[None, :, 2]) < dz)).any(1)
    return int(np.argmax(m)) if m.any() else -1


def _seen_before_site(h, path, site, r=300.0, grace=96):
    """A post's attacker in the post's sight before it has stood 3 s on the bombsite (03/11, round 20, Fachwerk's A AWP:
    8 kills, no death, 2 waves of 6 lost, the site taken 10 s in by attackers the post never saw; the plugin's rule: 4 s on
    the site's box unseen takes it): its first frame in the post's sight (_first_seen) comes before its grace-th frame
    within r of the plant zone (32 frames a second)."""
    P = np.asarray(path, float).reshape(-1, 5)
    k = _first_seen(h, P)
    if k < 0:
        return False
    if site is None:
        return True
    near = (np.hypot(P[:k, 0] - site[0], P[:k, 1] - site[1]) < r) & (np.abs(P[:k, 2] - site[2]) < 160)
    return int(near.sum()) < grace


def _hold_zone(CP, zones, p, mp):
    """A hold's place name: the most common zone of the CTs who fought from there (Backsite, Heaven…)."""
    near = np.hypot(CP[:, 0] - p[0], CP[:, 1] - p[1]) < 110
    z = pd.Series(zones[near] if near.any() else zones).dropna()
    return replay_zone(z.mode().iloc[0], mp) if len(z) else None


ZONES_F = os.path.join(config.OUT, "train_zones.json")
THIN = 30   # fewer of a map's matches here: a player's PC (its own matches), not the base's
_ZS = {}


def _zone_samples(mp, max_matches=60):
    """Where the base's players stood on a map (its last 60 matches, alive): x, y, z and their place's name. Kept 10 min
    in memory, one map at a time: the base's package makes every post's outline at once (08/10)."""
    hit = _ZS.get(mp)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    parts = []
    for d in _map_dirs(mp)[-max_matches:]:
        try:
            S = pd.read_parquet(os.path.join(config.OUT, "deep", d, "samples.parquet"), columns=["X", "Y", "Z", "zone", "health"])
        except Exception:
            continue
        S = S[(S.health > 0) & S.zone.notna()]
        if len(S):
            zs = {z: replay_zone(z, mp) for z in S.zone.unique()}
            parts.append(pd.DataFrame({"X": S.X.to_numpy(np.float32), "Y": S.Y.to_numpy(np.float32), "Z": S.Z.to_numpy(np.float32),
                                       "name": S.zone.map(zs).astype(str).to_numpy()}))
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame({"X": [], "Y": [], "Z": [], "name": []})
    df["name"] = df["name"].astype("category")
    _ZS.clear()
    _ZS[mp] = (time.time(), df)
    return df


WALLS_D = os.path.join(config.OUT, "train_walls")
_GRID = {}


def _occupancy(mp):
    """Where the base's players stood on that map, as cells of 8 u (x, y) and 16 u (z): made once from its samples
    (_zone_samples: 60 matches read from the hard disk, a minute cold), kept in out/train_walls, made again when the
    map has a quarter more matches (20/10: Prepare's site takes waited 213 s, every spot reading them again)."""
    if mp in _GRID:
        return _GRID[mp]
    os.makedirs(WALLS_D, exist_ok=True)
    f, meta = os.path.join(WALLS_D, f"{mp}.npy"), os.path.join(WALLS_D, f"{mp}.json")
    n = len(_map_dirs(mp))
    G = None
    try:
        if (config.read_json(meta, {}) or {}).get("n", 0) >= 0.8 * n:
            G = np.load(f)
    except (OSError, ValueError):
        G = None
    if G is None:
        S = _zone_samples(mp)
        G = np.unique(np.stack([np.round(S.X.to_numpy() / 8), np.round(S.Y.to_numpy() / 8), np.round(S.Z.to_numpy() / 16)], 1).astype(np.int32), axis=0)
        np.save(f, G)
        config.write_json(meta, {"n": n, "cells": int(len(G))})
    _GRID[mp] = G
    return G


def spot_walls(mp, p, r=40.0, dz=40.0):
    """Whether a stuff spot is one you find again (19/10, his 21:19 video: "on retient un stuff en identifiant une zone
    depuis laquelle l'envoyer ... un angle, le long d'un mur", "en plein milieu de l'allée ce ne sont pas des endroits
    dans lesquels on peut envoyer un stuff"; 20/10, a flash from an open square: "cette flash est envoyée de nulle
    part"): where the base's players stood around it, in 16 directions; one nobody stood in between 8 and r u is a wall.
    -> {dirs: 16 bools (east first, counterclockwise), walls: the blocked ones, ok: a wall along it (3 in a row), n}"""
    G = _occupancy(mp)
    X, Y, Z = G[:, 0] * 8.0, G[:, 1] * 8.0, G[:, 2] * 16.0
    m = (np.abs(X - p[0]) < r) & (np.abs(Y - p[1]) < r) & (np.abs(Z - p[2]) < dz)
    dx, dy = X[m] - p[0], Y[m] - p[1]
    d = np.hypot(dx, dy)
    k = ((np.degrees(np.arctan2(dy, dx)) % 360) // 22.5).astype(int)[(d > 8) & (d < r)]
    dirs = [not bool((k == i).any()) for i in range(16)]
    run = max((sum(1 for j in range(16) if all(dirs[(i + t) % 16] for t in range(j + 1))) for i in range(16)), default=0)
    return {"dirs": dirs, "walls": sum(dirs), "ok": run >= 3 and sum(dirs) < 16, "n": int(m.sum())}


TAKES_F = os.path.join(config.OUT, "train_takes.json")


def take_spots(mp, site):
    """Where the CTs are when the Ts take a site (20/10, his video: "croiser les endroits où je t'envoie des grenades avec
    les positions fortes que tu as dans les datas ... trouver les endroits où sont les joueurs défensifs et quand les
    joueurs sont offensifs, créer un premier contact sur les bombes sites"): in each round of the base whose duels reach
    the site (a T in its zone or 500 u of its centre), the CTs of its duels from 2 s before that first contact to 12 s
    after, 900 u of the centre and on its floor; merged 110 u apart, the most met first. -> [{pos, n, first, crouch,
    zone}]. Cached per map, made again with a quarter more matches."""
    cache = config.read_json(TAKES_F, {}) or {}
    dirs = _map_dirs(mp)
    key = f"{mp}|{site}"
    if key in cache and cache[key].get("n", 0) >= 0.8 * len(dirs):
        return cache[key]["spots"]
    S = (site_data(mp).get("sites") or {}).get(f"Bombsite{site}")
    if not S or not S.get("center"):
        return []
    c, zone = S["center"], f"Bombsite{site}"
    cols = ["round", "t", "killer_side", "victim_side", "killer_zone", "victim_zone", "killer_X", "killer_Y", "killer_Z",
            "victim_X", "victim_Y", "victim_Z", "killer_crouch", "victim_crouch"]
    pts = []
    for d in dirs:
        try:
            D = pd.read_parquet(os.path.join(config.OUT, "deep", d, "duels.parquet"), columns=cols)
        except Exception:
            continue
        for _, g in D.groupby("round"):
            g = g.sort_values("t")
            tk = g.killer_side.to_numpy() == "T"
            tx = np.where(tk, g.killer_X, g.victim_X)
            ty = np.where(tk, g.killer_Y, g.victim_Y)
            tz = np.where(tk, g.killer_zone, g.victim_zone)
            on = (tz == zone) | (np.hypot(tx - c[0], ty - c[1]) < 500)
            if not on.any():
                continue
            t1 = g.t.to_numpy()[on.argmax()]
            w = g[(g.t >= t1 - 2) & (g.t <= t1 + 12)]
            ck = w.killer_side.to_numpy() == "CT"
            for x, y, z, cr, zn, t in zip(np.where(ck, w.killer_X, w.victim_X), np.where(ck, w.killer_Y, w.victim_Y),
                                          np.where(ck, w.killer_Z, w.victim_Z), np.where(ck, w.killer_crouch, w.victim_crouch),
                                          np.where(ck, w.killer_zone, w.victim_zone), w.t):
                if math.dist((x, y), c[:2]) <= 900 and abs(z - c[2]) < 250:
                    pts.append(((float(x), float(y), float(z)), bool(cr), str(zn), t == t1))
    cl = []
    for p, cr, zn, first in pts:
        for q in cl:
            if math.dist(q["c"][:2], p[:2]) < 110 and abs(q["c"][2] - p[2]) < 60:
                q["s"] = [a + b for a, b in zip(q["s"], p)]
                q["n"] += 1
                q["crouch"] += cr
                q["first"] += first
                q["zones"][zn] = q["zones"].get(zn, 0) + 1
                q["c"] = [v / q["n"] for v in q["s"]]
                break
        else:
            cl.append({"c": list(p), "s": list(p), "n": 1, "crouch": int(cr), "first": int(first), "zones": {zn: 1}})
    cl.sort(key=lambda q: -q["n"])
    spots = [{"pos": [round(float(v), 1) for v in q["c"]], "n": int(q["n"]), "first": int(q["first"]), "crouch": int(q["crouch"]),
              "zone": max(q["zones"], key=q["zones"].get)} for q in cl if q["n"] >= 5]
    cache[key] = {"n": len(dirs), "spots": spots}
    try:
        config.write_json(TAKES_F, cache)
    except OSError:
        pass
    return spots


def start_near(mp, p, yaw=0.0, prefer=None, lo=150.0, hi=260.0):
    """Where a step-by-step stuff drill puts you (20/10, his video: "je ne dois pas apparaître déjà au bon endroit, je dois
    me déplacer, je dois être juste à proximité"): a place the base's players stood on, 150 to 260 u from the spot, same
    floor, from which you walk to it in a straight line (players stood all along it); the nearest to where you come from
    (the last grenade's spot), else behind you as you throw. None: no such place."""
    G = _occupancy(mp)
    X, Y, Z = G[:, 0] * 8.0, G[:, 1] * 8.0, G[:, 2] * 16.0
    near = (np.abs(X - p[0]) < hi + 16) & (np.abs(Y - p[1]) < hi + 16) & (np.abs(Z - p[2]) < 48)
    X, Y, Z = X[near], Y[near], Z[near]
    if not len(X):
        return None
    d = np.hypot(X - p[0], Y - p[1])
    cand = np.flatnonzero((d >= lo) & (d <= hi) & (np.abs(Z - p[2]) < 24))
    if not len(cand):
        return None
    cells = set(zip(np.round(X / 8).astype(int), np.round(Y / 8).astype(int)))

    def walkable(i):
        n = int(d[i] // 8)
        miss = 0
        for k in range(1, n):
            x = p[0] + (X[i] - p[0]) * k / n
            y = p[1] + (Y[i] - p[1]) * k / n
            cx, cy = round(x / 8), round(y / 8)
            if not any((cx + a, cy + b) in cells for a in (-1, 0, 1) for b in (-1, 0, 1)):
                miss += 1
                if miss > 1:
                    return False
        return True

    if prefer is not None and math.dist(prefer[:2], p[:2]) > lo:
        score = np.hypot(X[cand] - prefer[0], Y[cand] - prefer[1])
    else:   # behind you as you throw
        back = math.radians(yaw + 180.0)
        h = np.arctan2(Y[cand] - p[1], X[cand] - p[0])
        score = np.abs(np.angle(np.exp(1j * (h - back))))
    from wily.training import navmesh
    for j in np.argsort(score)[:400]:
        i = int(cand[j])
        if walkable(i):
            q = [round(float(X[i]), 1), round(float(Y[i]), 1), round(float(p[2] if abs(Z[i] - p[2]) < 16 else Z[i]) + 8.0, 1)]
            # in the open, 16 u from any wall or prop (22/10, his test video: "je spawn en endroits où je suis bloqué": a
            # place players stood by an IBC tank put him inside it)
            if navmesh.on_mesh(mp, q) is False or (navmesh.walls(mp, q, r=16.0) or []):
                continue
            return q
    return None


def zone_outline(mp, name, near, cell=32.0, max_matches=60, R=1600.0, ZR=170.0, hold=650.0):
    """The ground outline of the place a defense's post is in (06/10, the user: "une zone plus grande que juste un cercle,
    adapte-toi à la morphologie de la map: si c'est Garage, prends tout le Garage"): where the base's players stood in
    that place (same name, same floor), 650 u around the post at most (Nuke's Outside is the whole yard), the piece
    around the post with its small holes filled, its border walked around and simplified (20 u). Cached per post; the
    base's package ships them all (zones_for_base), a player's PC uses the nearest one of the same place."""
    if not name or not near:
        return []
    key = f"{mp}|{name}|{round(near[0])}|{round(near[1])}|{round(near[2])}"
    try:
        cache = json.load(open(ZONES_F, encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if key in cache:
        return cache[key]
    if len(_map_dirs(mp)) < THIN:
        # 08/10, his warm-up on the installed app: with its own 8 matches Nuke's Tunnels came out 32 x 96 u ("c'est vraiment
        # un pixel"), Ramp 128 x 160: the base's outline of that place nearest to it (same floor, 900 u)
        best = None
        for k, v in cache.items():
            parts = k.split("|")
            if len(parts) != 5 or parts[0] != mp or parts[1] != name or not v:
                continue
            x, y, z = (float(c) for c in parts[2:])
            d = math.hypot(x - near[0], y - near[1])
            if abs(z - near[2]) < ZR and d < 900 and (best is None or d < best[0]):
                best = (d, v)
        if best:
            return best[1]
    from collections import deque
    S = _zone_samples(mp, max_matches)
    S = S[(S.name == name) & (np.hypot(S.X - near[0], S.Y - near[1]) < R) & ((S.Z - near[2]).abs() < ZR)]
    P = S[["X", "Y", "Z"]].to_numpy(float)
    out = []
    if len(P) >= 30:
        cnt = Counter(zip(np.floor(P[:, 0] / cell).astype(int), np.floor(P[:, 1] / cell).astype(int)))
        occ = {c for c, n in cnt.items() if n >= 2 and math.hypot((c[0] + .5) * cell - near[0], (c[1] + .5) * cell - near[1]) < hold}
        if occ:
            start = min(occ, key=lambda c: ((c[0] + .5) * cell - near[0]) ** 2 + ((c[1] + .5) * cell - near[1]) ** 2)
            comp, q = {start}, deque([start])
            while q:
                x, y = q.popleft()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    n = (x + dx, y + dy)
                    if n in occ and n not in comp:
                        comp.add(n)
                        q.append(n)
            for _ in range(2):   # a box in the middle: its cells filled
                xs, ys = [c[0] for c in comp], [c[1] for c in comp]
                comp |= {(x, y) for x in range(min(xs) - 1, max(xs) + 2) for y in range(min(ys) - 1, max(ys) + 2)
                         if (x, y) not in comp and sum((x + dx, y + dy) in comp for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) >= 3}
            edges = {}
            for (x, y) in comp:
                for (dx, dy), (a, b) in (((0, -1), ((x, y), (x + 1, y))), ((1, 0), ((x + 1, y), (x + 1, y + 1))),
                                          ((0, 1), ((x + 1, y + 1), (x, y + 1))), ((-1, 0), ((x, y + 1), (x, y)))):
                    if (x + dx, y + dy) not in comp:
                        edges.setdefault(a, []).append(b)
            loops = []
            while edges:
                a = next(iter(edges))
                loop = [a]
                while a in edges:
                    nx = edges[a].pop()
                    if not edges[a]:
                        del edges[a]
                    if nx == loop[0]:
                        break
                    loop.append(nx)
                    a = nx
                loops.append(loop)
            L = np.array(max(loops, key=len), float) * cell
            L = L[_rdp(np.c_[L, np.zeros(len(L))], 20.0)]
            for x, y in L:
                d = np.hypot(P[:, 0] - x, P[:, 1] - y)
                out.append([round(float(x), 1), round(float(y), 1), round(float(np.median(P[np.argsort(d)[:25], 2])), 1)])
    cache[key] = out
    config.write_json(ZONES_F, cache)
    return out


def zones_for_base(log=print):
    """Every post's outline (each site's holds) and each place's around its 3 busiest spots (900 u apart: a situation's
    zone on a player's PC takes the nearest), made here where the base's matches are, shipped with the base (08/10)."""
    try:
        sites = json.load(open(SITES_F, encoding="utf-8"))
    except (OSError, ValueError):
        sites = {}
    for mp in sorted(sites):
        t0, n = time.time(), 0
        for S in (sites[mp].get("sites") or {}).values():
            for h in _site_holds(S):
                if h.get("zone") and h.get("pos"):
                    zone_outline(mp, h["zone"], h["pos"])
                    n += 1
        df = _zone_samples(mp)
        for name, g in df.groupby("name", observed=True):
            if str(name) in ("", "nan", "?", "None") or len(g) < 200:
                continue
            cx, cy = np.floor(g.X.to_numpy() / 64).astype(np.int64), np.floor(g.Y.to_numpy() / 64).astype(np.int64)
            cells = pd.Series(cx * 100000 + cy).value_counts()
            picked = []
            for c in cells.index[:300]:
                x, y = int(c // 100000), int(c % 100000)
                if y > 50000:   # negative y: the key wrapped
                    x, y = x + 1, y - 100000
                p = ((x + .5) * 64, (y + .5) * 64)
                if all(math.dist(p, q[:2]) >= 900 for q in picked):
                    zz = float(np.median(g.Z.to_numpy()[(cx == x) & (cy == y)]))
                    picked.append((p[0], p[1], zz))
                if len(picked) >= 3:
                    break
            for p in picked:
                zone_outline(mp, str(name), list(p))
                n += 1
        log(f"zones {mp}: {n} outlines ({time.time() - t0:.0f} s)")
    _ZS.clear()


def _timings(holds):
    """When each angle peeks, from the real timings (the earliest at once, the others after it, compressed by half,
    within 30 s): the bots show up like the players do, at recurring moments."""
    ts = [h.get("t") for h in holds]
    if not ts or any(t is None for t in ts):
        return [0.0] * len(holds)
    t0 = min(ts)
    return [round(min(30.0, (t - t0) * 0.5), 1) for t in ts]


ENTRY_D = os.path.join(config.OUT, "train_entries")


def _hit_nades(p, ticks):
    """The grenades thrown in the windows of a demo's hits: (tick, thrower, the plugin's nade: type, first position and
    speed), like replay._nades (a thrower dead in the replay throws nothing)."""
    try:
        g = p.parse_grenades()
    except Exception:
        return []
    lo, hi = min(ticks), max(ticks)
    g = g[g.grenade_type.isin(list(replay.NADES)) & g.x.notna() & (g.tick >= lo) & (g.tick <= hi)].sort_values("tick")
    out = []
    for (_, sid_, typ), e in g.groupby(["grenade_entity_id", "steamid", "grenade_type"]):
        t = e.tick.to_numpy()
        cuts = [0] + [i for i in range(1, len(t)) if t[i] - t[i - 1] > 2] + [len(t)]
        for a, b in zip(cuts, cuts[1:]):
            r = e.iloc[a:b]
            if len(r) < 2:
                continue
            dt = (int(r.tick.iloc[1]) - int(r.tick.iloc[0])) / 64
            v = [(float(r[c].iloc[1]) - float(r[c].iloc[0])) / dt for c in ("x", "y", "z")]
            v[2] += 0.5 * 320 * dt
            out.append((int(r.tick.iloc[0]), str(sid_), {"type": replay.NADES[typ], "inc": False, "life": int(r.tick.iloc[-1]) - int(r.tick.iloc[0]),
                                                          "p": [round(float(r[c].iloc[0]), 1) for c in ("x", "y", "z")], "v": [round(x, 1) for x in v]}))
    return out


def entries(mp, demos=24):
    """Real hits on each site, from the base's demos: for every plant, the planter and the Ts entering with him, their
    path in the 14 s before the plant (positions every 2 ticks), the ones that came from outside (700 u away or more)
    and ended on the site; with the moment a CT first saw each one (spot: its frame, -1: never) and the grenades it
    threw on the way (f: their frame). The attackers of a defense walk them, throw them, then fight on their own once
    they see you. Cached per map."""
    os.makedirs(ENTRY_D, exist_ok=True)
    cf = os.path.join(ENTRY_D, f"{mp}.json")
    try:
        c = json.load(open(cf, encoding="utf-8"))
        if c.get("v") == 5:
            return c
    except (OSError, ValueError):
        pass
    return replay.in_worker(_entries, mp, demos)   # the demos parsed out of the app's process (08/10)


def _entries(mp, demos=24):
    from demoparser2 import DemoParser
    from wily.insights import nades
    os.makedirs(ENTRY_D, exist_ok=True)
    cf = os.path.join(ENTRY_D, f"{mp}.json")
    dirs = []
    for d in sorted(os.listdir(os.path.join(config.OUT, "deep")), reverse=True):
        try:
            if json.load(open(os.path.join(config.OUT, "deep", d, "meta.json"), encoding="utf-8")).get("map") == mp                     and config.has_demo(d):
                dirs.append(d)
        except (OSError, ValueError):
            continue
    out = {"v": 5, "A": [], "B": []}
    for d in dirs[:demos]:
        try:
            R = pd.read_parquet(os.path.join(config.OUT, "deep", d, "rounds.parquet"))
            R = R[R.plant_site.isin(["A", "B"]) & R.plant_tick.notna()]
            if not len(R):
                continue
            want = sorted({t for pt in R.plant_tick for t in range(int(pt) - 14 * 64, int(pt) + 1, 2)})
            dp = DemoParser(config.demo(d))
            T = dp.parse_ticks(["X", "Y", "Z", "yaw", "pitch", "is_alive", "team_num", "last_place_name", "spotted"], ticks=want)
            thrown = _hit_nades(dp, want)
        except Exception as e:
            print("entries", d, e, flush=True)
            continue
        for _, r in R.iterrows():
            pt, site = int(r.plant_tick), r.plant_site
            w = T[(T.tick >= pt - 14 * 64) & (T.tick <= pt) & (T.team_num == 2)]
            pl = w[w.steamid == r.planter].sort_values("tick")
            pz = float(pl.Z.iloc[-1]) if len(pl) else None   # the floor of the plant (Nuke: a T on A when B is planted is not on B)
            for sid_, g in w.groupby("steamid"):
                g = g.sort_values("tick")
                if len(g) < 200 or not bool(g.is_alive.iloc[-1]):
                    continue
                P = g[["X", "Y", "Z"]].to_numpy(float)
                dist = np.hypot(P[:, 0] - r.plant_X, P[:, 1] - r.plant_Y)
                if dist[-1] > 450 or dist[0] < 700 or (pz is not None and abs(P[-1, 2] - pz) > 200):
                    continue
                k0 = int(np.argmax(dist <= 1500)) if (dist <= 1500).any() else 0   # from where it gets close
                if len(g) - k0 < 40:
                    continue
                path, zones = [], []
                for x, y, z, yw, pi in zip(g.X, g.Y, g.Z, g.yaw, g.pitch):
                    path += [round(float(x), 1), round(float(y), 1), round(float(z), 1), round(float(yw), 1), round(float(pi), 1)]
                for pl in g.last_place_name.fillna(""):   # the places it crosses, in order
                    nm = nades.humanize(pl, mp) if pl else None
                    if nm and (not zones or zones[-1] != nm):
                        zones.append(nm)
                pl = g.last_place_name.fillna("").iloc[k0]
                seen = g.spotted.astype(object).eq(True).to_numpy() if "spotted" in g else np.zeros(len(g), bool)
                t0_ = int(g.tick.iloc[0])
                own = [{"f": (tk - t0_) // 2, **nd} for tk, by, nd in thrown if by == str(sid_) and t0_ <= tk <= int(g.tick.iloc[-1])]
                out[site].append({"zone": nades.humanize(pl, mp) or "?", "path": path, "k0": k0, "zones": zones,
                                  "from": round(float(dist[0])), "spot": int(np.argmax(seen)) if seen.any() else -1, "nades": own})
    json.dump(out, open(cf, "w", encoding="utf-8"), separators=(",", ":"))
    return out


def _opening(z, w=13):
    """The height without the jumps: a morphological opening over ±w samples (positions every 2 ticks: ±0.4 s). A
    jump's arc, shorter than the window, goes; a ramp or a box you stay on keeps its height."""
    from numpy.lib.stride_tricks import sliding_window_view
    e = sliding_window_view(np.pad(z, w, mode="edge"), 2 * w + 1).min(axis=1)
    return sliding_window_view(np.pad(e, w, mode="edge"), 2 * w + 1).max(axis=1)


def _jumps(z):
    """How many jumps a way has (its height 25 u over the ground, again and again)."""
    up = (np.asarray(z, float) - _opening(np.asarray(z, float))) > 25
    return int(np.sum(up[1:] & ~up[:-1]) + (1 if len(up) and up[0] else 0))


def _no_returns(P, r=90.0):
    """A walked way without its loops and its returns (07/10, the user: "le chemin qui fait des allers-retours,
    useless"): from each point, on to the last later point back within r of it (same floor) when the way went away
    meanwhile (1.5 r), so a trip there and back is cut out. 09/10 (his prefire video: "le path au sol... ne suit pas
    exactement la map"): without that condition every point jumped to the one 90 u ahead, a way of 449 points kept 27,
    and the line's smoothing, made for a point every 2 ticks, flattened its heights (Control's ramp drawn 218 u low)."""
    Q = np.asarray(P, float)
    if len(Q) < 3:
        return Q
    out, i, n = [0], 0, len(Q)
    while i < n - 1:
        R = Q[i + 1:]
        d = np.hypot(R[:, 0] - Q[i, 0], R[:, 1] - Q[i, 1])
        back = np.where((d < r) & (np.abs(R[:, 2] - Q[i, 2]) < 60))[0]
        j = int(back[-1]) if len(back) else -1
        i = i + 1 + j if j > 0 and d[:j].max() > 1.5 * r else i + 1
        out.append(i)
    return Q[out]


def _detour(P):
    """How much longer than the straight way a walked way is (1: straight)."""
    Q = np.asarray(P, float)[:, :2]
    if len(Q) < 2:
        return 1.0
    walk = float(np.linalg.norm(np.diff(Q, axis=0), axis=1).sum())
    return walk / max(1.0, float(np.linalg.norm(Q[-1] - Q[0])))


def _rdp(Q, eps):
    """The points that keep the way's shape within eps (Ramer-Douglas-Peucker)."""
    keep, stack = {0, len(Q) - 1}, [(0, len(Q) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        seg, pts = Q[b] - Q[a], Q[a + 1:b] - Q[a]
        n = float(np.linalg.norm(seg))
        d = np.linalg.norm(np.cross(pts, seg / n), axis=1) if n > 1e-6 else np.linalg.norm(pts, axis=1)
        k = int(np.argmax(d))
        if d[k] > eps:
            keep.add(a + 1 + k)
            stack += [(a, a + 1 + k), (a + 1 + k, b)]
    return sorted(keep)


# the maps' water: (x min, x max, y min, y max, -, the height the line goes up to there): Anubis's canals, where the
# players' feet are at -189 and the walkways at -152
WATER = {"de_anubis": [(-420, 1270, 20, 890, -200, -158)]}


def _ground_line(P, mp=None):
    """The way drawn on the ground: the jumps flattened, the strafes straightened, 60 segments at most (03/10: the
    line hung in the air and zigzagged where the real player jumped on the boxes)."""
    Q = np.array(P[:, :3], float)
    Q[:, 2] = _opening(Q[:, 2])
    if len(Q) > 20:   # the strafes and quick peeks smoothed out (±0.125 s): the way, not the steps (04/10: "the zigzag is bad");
        k = 4         # ±0.25 s cut the corners through the walls (09/10, his video: "le path dessiné au sol ne suit pas exactement la map")
        pad = np.pad(Q[:, :2], ((k, k), (0, 0)), mode="edge")
        sm = np.stack([np.convolve(pad[:, j], np.ones(2 * k + 1) / (2 * k + 1), mode="valid") for j in range(2)], 1)
        sm[0], sm[-1] = Q[0, :2], Q[-1, :2]
        Q[:, :2] = sm
    for x0, x1, y0, y1, zmin, surf in WATER.get(mp, ()):   # in the water: on its surface, not under it (06/10, Anubis)
        w = (Q[:, 0] > x0) & (Q[:, 0] < x1) & (Q[:, 1] > y0) & (Q[:, 1] < y1) & (Q[:, 2] < surf)
        Q[w, 2] = surf
    eps, keep = 16.0, _rdp(Q, 16.0)   # 06/10: closer to the way walked (48 u cut the corners; 24 still did, 09/10)
    while len(keep) > 81:
        eps *= 1.5
        keep = _rdp(Q, eps)
    return [[round(float(v), 1) for v in Q[i]] for i in keep]


_DUEL_POS = {}


def _duel_spots(mp):
    """Where the map's players stood in duels (killers and victims, all the base's demos of it): (n, 3), cached."""
    if mp not in _DUEL_POS:
        parts = []
        for d in _map_dirs(mp):
            try:
                D = pd.read_parquet(os.path.join(config.OUT, "deep", d, "duels.parquet"),
                                    columns=["killer_X", "killer_Y", "killer_Z", "victim_X", "victim_Y", "victim_Z"])
            except Exception:
                continue
            parts += [D[["killer_X", "killer_Y", "killer_Z"]].to_numpy(float), D[["victim_X", "victim_Y", "victim_Z"]].to_numpy(float)]
        _DUEL_POS[mp] = np.concatenate(parts) if parts else np.zeros((0, 3))
    return _DUEL_POS[mp]


def real_boost(mp, b):
    """A boost only a boost reaches (07/10, the user on Overpass's Walkway: "on peut avoir accès sans boost"): its top
    spot is not where the base's players fight on their own, more than its boosts' own kills and deaths would put them."""
    Q = _duel_spots(mp)
    if not len(Q):
        return True
    top, base = np.asarray(b["pos"], float), np.asarray(b["base"], float)
    near = np.hypot(Q[:, 0] - top[0], Q[:, 1] - top[1]) < 80
    up = int((near & (np.abs(Q[:, 2] - top[2]) < 20)).sum())   # fights at the top's height around it
    down = int((near & (np.abs(Q[:, 2] - base[2]) < 20)).sum())   # and on the floor below
    # a floor of its own (as many fights up there as below, beyond the boosters' own): Walkway 7 up / 5 below; a real
    # boost: Inferno's B site 19 up / 479 below
    return not (up > b.get("kills", 0) + b.get("deaths", 0) + 3 and up > 0.2 * down)


def boost_top(b):
    """Where the top player of a boost goes (13/10, a tester: "22 boost didn't work"): right on the teammate's head, its
    height 54 u crouched or 72 u standing (the demo's 63 u on Anubis put you 9 u into a standing mate, pushed off), at
    most 8 u off its axis (15 u in some demos: on the edge of a 32 u wide head). -> (pos, crouched mate)."""
    base, top = b["base"], b["pos"]
    duck = b.get("dz", 72) < 63
    dx, dy = top[0] - base[0], top[1] - base[1]
    r = math.hypot(dx, dy)
    k = min(1.0, 8.0 / r) if r > 0 else 0.0
    return [round(base[0] + dx * k, 1), round(base[1] + dy * k, 1), round(base[2] + (54 if duck else 72) + 0.5, 1)], duck


def _prefire_boost(mp, S, P, line):
    """A CT boost of the base near this site whose top player killed Ts on this way: [top, base] as prefire holds (fs:
    the way's first point near one of its victims), or None."""
    try:
        from wily.insights import boosts
        B = [b for b in boosts.load(mp) if b.get("side") == "CT" and b.get("victims") and b.get("kills", 0) >= 2
             and math.dist(b["pos"][:2], S["defend"][:2]) < 1500 and real_boost(mp, b)]
    except Exception:
        return None
    W = np.asarray(P, float)
    for b in sorted(B, key=lambda b: -b["kills"]):
        V = np.array(b["victims"], float).reshape(-1, 3)
        near = (np.hypot(W[:, None, 0] - V[None, :, 0], W[:, None, 1] - V[None, :, 1]) < 200) & (np.abs(W[:, None, 2] - V[None, :, 2]) < 110)
        if not near.any():
            continue
        fs = int(np.argmax(near.any(1)))
        w = W[fs]
        li = int(np.argmin([math.dist(w[:2], q[:2]) for q in line])) if line else 0
        (top, duck), base = boost_top(b), list(b["base"])
        ang = _angle([top[0], top[1], top[2] + 64], [w[0], w[1], w[2] + 56])
        return [{"pos": top, "ang": ang, "zone": f"{b['place']} (boost)", "n": b["kills"], "fs": fs, "li": li, "unc": False, "t": float(b.get("t_med") or 60)},
                {"pos": base, "ang": [0, ang[1]], "zone": f"{b['place']} (boost, below)", "crouch": 1.0 if duck else 0.0,
                 "n": b["kills"], "fs": fs, "li": li, "unc": False, "t": float(b.get("t_med") or 60)}]
    return None


# the posts a defense's weapon is played on (23/10, the user: "une arme qui colle au poste : MAG-7 sur un coin proche, AWP
# sur une longue ligne"): how far its foes stood from it, the median of its duels (u); a rifle and a pistol anywhere
KIT_REACH = {"close": (0.0, 750.0), "awp": (1100.0, 1e9)}
# a shotgun's post a close corner itself (24/10, the real-client battery: MAG-7 posts with their foes at 669 to 728 u, Nuke's
# Vending, Cache's Checkers, Mirage's B site, lost 1 kill for 6 deaths; an SMG holds those)
SHOTGUNS, SHOTGUN_REACH = ("MAG-7", "XM1014", "Nova", "Sawed-Off"), 450.0
# a shotgun's post only where a corner of its zone sees the attackers' ways within this (03/11, round 19: passed at 307 u
# and under, Nuke's A and B; failed every time from 345 u, five maps; round 20 with 310: Overpass's Construction (301 u)
# and Mirage's A (291 and 303 u) 1 wave of 6, 5 deaths each, Nuke's 275 u had held 5 of 6): tools/close_check.py,
# resources/close_checked.json
CLOSE_CAP = 280.0


def _close_ok(mp, post):
    """A shotgun's post as tools/close_check.py found it: True when its corners keep the ways within CLOSE_CAP, or when
    it was never checked (offered till it is)."""
    rec = (config.read_json(os.path.join(config.HERE, "resources", "close_checked.json"), {}) or {}).get(
        f"{mp}|{round(post['pos'][0])}|{round(post['pos'][1])}|{round(post['pos'][2])}")
    return rec is None or (rec.get("reach") is not None and rec["reach"] <= CLOSE_CAP)


def _defend_format(kit, difficulty):
    """A defense's attackers at a time and its frags asked, at your level (23/10, the user: "au niveau Facile, la Défense
    du site A de Dust2 est déjà très dure en solo. Le niveau devrait dépendre du format (solo contre 3) autant que des
    bots"): one at Easy, two at Normal, the weapon's own at Hard, one more at Expert; the frags asked in proportion."""
    base = int(kit["alive"])
    alive = min(base + 1, {0: 1, 1: 2, 2: base}.get(int(difficulty), base + 1))
    return alive, max(3, round(kit["goal"] * (0.6 + 0.4 * alive / base)))


def practice_drills(sid, mp, difficulty=2):
    """Prefire (you T from an entrance, bots on every angle the CTs really hold, they don't shoot: clear them fast) and
    defense (you CT on the site, attackers keep coming from the real entrances for 90 s: as many frags as you can)."""
    out = []
    try:   # the angles you rarely check in your demos (checks.py, 06/10): a prefire's bots go there first
        from wily.insights import checks
        unc = checks.unchecked(sid, mp)
    except Exception:
        unc = []
    for z, S in (site_data(mp).get("sites") or {}).items():
        site = replay_zone(z, mp)
        pick = []
        for e in S["entrances"]:   # the entrances right on the site, not two next to each other
            if e["dist"] < 1700 and all(math.dist(e["start"], p["start"]) > 900 for p in pick):
                pick.append(e)
        letter = z.replace("Bombsite", "")[:1]
        hits = [t for t in (entries(mp).get(letter) or []) if t.get("from", 0) >= 1300 and len(t.get("zones") or []) >= 2
                and not any("CT" in zn for zn in t["zones"])   # an attack, not a late rotation through the CTs' side
                and replay_zone("Bombsite" + ("B" if letter == "A" else "A"), mp) not in t["zones"]]   # nor a drop from the other site (Nuke)
        for e in pick[:3]:   # the push routes: one per entrance on the site
            frm = replay_zone(e["zone"], mp)
            # a real hit through that entrance, from far: its way is the route (start, places, the line drawn in the game)
            way = sorted([t for t in hits if frm in (t.get("zones") or [])], key=lambda t: -t.get("from", 0))[:6]
            if way:   # one of the ones from furthest, with the fewest jumps (boxes: a line hard to follow), the most direct
                jumps = {id(t): _jumps(np.array(t["path"], float).reshape(-1, 5)[:, 2]) for t in way}
                way = [t for t in way if jumps[id(t)] == min(jumps.values())]
                det = {id(t): _detour(_no_returns(np.array(t["path"], float).reshape(-1, 5)[:, :3])) for t in way}
                way = [t for t in way if det[id(t)] <= 1.25 * min(det.values())]
            hit = random.choice(way) if way else None
            if not hit:
                continue
            P = _no_returns(np.array(hit["path"], float).reshape(-1, 5)[:, :3]) if hit else None
            start = [round(float(v), 1) for v in P[0]] if hit else e["start"]
            # the CT angles seen from that very way (06/10, the user: "le dernier, je le croise jamais... je veux juste
            # qu'il soit visible depuis le chemin que je prends"): the base's duels put Ts on this way fighting a CT on
            # that spot (they saw each other); the most fought from it first (the strongest, the most played: the
            # session keeps more or fewer by its level), none right at your start, 10 at most (a team holds 10 bots)
            keep = []
            for h in _site_holds(S):
                h["vis"] = _sees(h, P)
                if h["vis"] >= 2 and math.dist(h["pos"][:2], start[:2]) > 600:
                    keep.append(h)
            for h in keep:
                h["unc"] = any(math.dist(h["pos"][:2], a["pos"][:2]) < 120 and abs(h["pos"][2] - a["pos"][2]) < 90 for a in unc)
            keep = sorted(keep, key=lambda h: (-h["unc"], -h["vis"], -h["n"]))[:10]
            if len(keep) < 4:
                continue
            for h in keep:   # each one turned to where it saw the Ts of this way
                Q = np.array(h["seen"], float).reshape(-1, 3)
                near = Q[np.hypot(Q[:, 0, None] - P[None, ::3, 0], Q[:, 1, None] - P[None, ::3, 1]).min(1) < 160]
                if len(near):
                    eye = 46 if h.get("crouch", 0) >= 0.35 else 64
                    h["ang"] = _angle([h["pos"][0], h["pos"][1], h["pos"][2] + eye], np.median(near, axis=0) + [0, 0, 56])
            route = hit["zones"] if hit else [frm, site]
            first = min(keep, key=lambda h: math.dist(h["pos"], start))
            line = _ground_line(P, mp) if hit else []   # the way drawn on the ground
            ats = dict(zip(map(id, keep), _timings(keep)))
            for h in keep:
                fs = _first_seen(h, P)
                h["fs"] = fs if fs >= 0 else len(P)
                w = P[min(h["fs"], len(P) - 1)]
                h["li"] = int(np.argmin([math.dist(w[:2], q[:2]) for q in line])) if line else 0
            keep = sorted(keep, key=lambda h: (h["fs"], ats[id(h)]))
            # now and then a CT boost of the base on that way (07/10: "il peut y avoir des positions de boost, pas souvent
            # certes"): the two of them, the top one where the base's boosters stood and killed Ts on this way
            boost = _prefire_boost(mp, S, P, line) if random.random() < 0.35 else None
            if boost:
                keep = keep[:10 - len(boost)]
                at = max([ats[id(h)] for h in keep] or [0.0]) * 0.6
                for h in boost:
                    ats[id(h)] = at
                keep = sorted(keep + boost, key=lambda h: (h["fs"], ats[id(h)]))
            out.append({"id": f"prefire:{mp}:{z}:{e['zone']}", "kind": "aim", "mode": "prefire", "map": mp,
                        "title": i18n.tr("PREFIRE {site} via {way}", site=site, way=frm), "team": 2, "route": route, "line": line,
                        "tip": i18n.tr("follow the gold line: {route} · the angles CTs hold there, at their real timings", route=' → '.join(route))
                               + (" · " + i18n.tr("{n} you rarely check in your matches", n=sum(h['unc'] for h in keep)) if any(h["unc"] for h in keep) else "")
                               + " · " + i18n.tr("they don't move, they don't shoot"),
                        "me": {"pos": start, "ang": _angle(start, line[1] if len(line) > 1 else first["pos"])},
                        "weapons": ["weapon_knife", RIFLE[2]], "bot_weapons": ["weapon_knife", RIFLE[3]],
                        "bots": [{"pos": h["pos"], "ang": h["ang"], "zone": h.get("zone") or site, "at": ats[id(h)], "duck": h.get("crouch", 0) >= 0.35,
                                  "seq": i, "li": h["li"]} for i, h in enumerate(keep)],
                        # the round's clock as when these angles get fought (06/10: "le vrai temps in-game, pas 58 minutes")
                        "clock": round(max(15.0, 115 - max(0.0, min(h["t"] for h in keep) - 8)), 1),
                        "seconds": 90, "weight": 2 + min(1.0, e["n"] / 400)})
        spawns = [{"pos": p, "ang": _angle(p, S["defend"]), "zone": replay_zone(e["zone"], mp)} for e in S["entrances"] for p in e["spawns"]]
        letter = z.replace("Bombsite", "")[:1]
        hits = (entries(mp).get(letter) or []) if letter in ("A", "B") else []
        other = replay_zone("Bombsite" + ("B" if letter == "A" else "A"), mp)
        hits = [t for t in hits if not any("CT" in zn for zn in t.get("zones") or []) and other not in (t.get("zones") or [])]   # attacks
        # the spots to hold, one after the other, before playing free (04/10: "a specific work on positions: backsite,
        # then that one, then free"): the most held of the site, each its own place, and only one the real hits come
        # into sight of (06/10: "les bots n'attaquent pas le mid, je peux rester à rien faire"); each post gets its own
        # attackers, real hits that walk into its sight from out of it
        site_pt = _plant_spot(mp, letter, S) or S["defend"]   # the plant zone (the plugin's "site taken" is on its box)
        cands = []   # the posts that could be held, 4 at most, each with its own attackers and how far its foes stood
        for h in _site_holds(S):
            if not h.get("zone") or any(h["zone"] == q[0]["zone"] or math.dist(h["pos"], q[0]["pos"]) <= 300 for q in cands):
                continue
            mine = [t for t in hits if _sees(h, np.array(t["path"], float).reshape(-1, 5), r=180) >= 2]
            poly = zone_outline(mp, h["zone"], h["pos"])
            tr = _defense_tracks(mine, h["pos"], n=10, foes=h, mp=mp, poly=poly) if len(mine) >= 3 else []
            # the post sees them before they hold the site (03/11): no wave lost to attackers it could never see
            tr = [t for t in tr if _seen_before_site(h, t["path"], site_pt)]
            if len(tr) < 3:   # too few walk into its sight from out of it
                continue
            Q = np.array(h["seen"], float).reshape(-1, 3)   # turned to where its foes stood
            ang = _angle([h["pos"][0], h["pos"][1], h["pos"][2] + 64], np.median(Q, axis=0) + [0, 0, 56]) if len(Q) else h["ang"]
            reach = float(np.median(np.hypot(Q[:, 0] - h["pos"][0], Q[:, 1] - h["pos"][1]))) if len(Q) else 900.0
            cands.append(({"pos": h["pos"], "ang": ang, "zone": _post_name(mp, h, letter), "poly": poly, "t": h.get("t")}, tr, reach))
            if len(cands) >= 4:
                break
        free_tr = [dict(t, post=-1) for t in _defense_tracks(hits, S["defend"], n=12, mp=mp)]   # then free: any of them
        if len(spawns) < 2 and not cands and not free_tr:
            continue
        site_at = site_pt   # free: you back on the plant zone itself
        for kit in _defense_kits(sid):
            lo, hi = KIT_REACH.get(kit["cls"], (0.0, 1e9))
            if kit["name"] in SHOTGUNS:
                hi = min(hi, SHOTGUN_REACH)
            fit = [c for c in cands if lo <= c[2] <= hi and (kit["name"] not in SHOTGUNS or _close_ok(mp, c[0]))][:2]
            if kit["cls"] in KIT_REACH and not fit:   # no post of this site fits that weapon: not played here
                continue
            posts = [c[0] for c in fit]
            # a shotgun plays its close corners only (24/10, the real-client battery on Ancient: its post at 419 u, then half
            # the drill free on the site, its long duels lost 4 kills for 7 deaths): no free phase
            free = kit["name"] not in SHOTGUNS
            tracks = [dict(t, post=k) for k, c in enumerate(fit) for t in c[1]] + (free_tr if free else [])
            if len(spawns) < 2 and not tracks:
                continue
            ways = Counter(t["zone"] for t in tracks)
            froms = ", ".join(f"{w} {round(100 * n / len(tracks))}%" for w, n in ways.most_common(4)) if tracks else \
                ", ".join(dict.fromkeys(replay_zone(e["zone"], mp) for e in S["entrances"]))
            hold_t = [p["t"] for p in posts if p.get("t") is not None]
            alive, goal = _defend_format(kit, difficulty)
            out.append({"id": f"defend:{mp}:{z}:{kit['cls']}", "kind": "aim", "mode": "defend", "map": mp,
                        "title": i18n.tr("DEFEND {site} · {kit}", site=site, kit=kit['name']), "team": 3,
                        "tip": i18n.tr("{s} s · {n} at a time, the ways real hits come: {ways} · {goal} frags · you respawn", s=kit['seconds'], n=alive, ways=froms, goal=goal),
                        # a shotgun's drill (no free phase) starts on its post itself (24/10: from the site its first
                        # attackers saw him in the countdown, went their own way and never came to the post)
                        "me": {"pos": posts[0]["pos"], "ang": posts[0]["ang"]} if not free and posts else
                              {"pos": site_at, "ang": _angle(site_at, spawns[0]["pos"] if spawns else tracks[0]["path"][:3])},
                        "weapons": kit["weapons"], "bot_weapons": kit["bot_weapons"], "armor": 100, "helmet": kit["helmet"],
                        "bots": spawns, "tracks": tracks, "seconds": kit["seconds"], "alive": alive, "goal": goal,
                        "posts": posts, "free": free, "weight": kit["weight"], "reach": [round(c[2]) for c in fit], "plant_at": site_at,
                        "clock": round(max(20.0, 115 - max(0.0, min(hold_t) - 6)), 1) if hold_t else 0})
    return out


# a post's name as players call it where the game's places say otherwise (06/10, the user on Overpass: "cette zone elle
# s'appelle Toilettes, pas Lower Park"): (map, x, y, radius, callout)
POST_NAMES = [("de_overpass", -2238.6, -603.1, 260, "Toilets")]


def _post_name(mp, h, letter=""):
    for m, x, y, r, nm in POST_NAMES:
        if m == mp and math.hypot(h["pos"][0] - x, h["pos"][1] - y) < r:
            return nm
    if letter and h["zone"] in ("Short", "Long", "Ramp", "Main", "Lobby"):   # "Short" of the A site: "Short A"
        return f"{h['zone']} {letter}"
    return h["zone"]


# a walk-on this many times the straight line, and this much longer, is a way round the map, not a way in (10/11, round
# 26, Overpass's B Connector post: three of its four attackers cut 640 u from it, by the B site, walked on 7,400 u round
# the whole map, the mesh's way never climbing a step over 18 u; 36 s before they came near, then from the top of the
# stairs behind it, 120 u over it; elsewhere a post's attackers come within 500 u in 2 to 16 s)
DETOUR = (2.5, 1200.0)


def _toward(mp, path, spot, short=32.0, speed=215.0, poly=None):
    """A cut real hit walked on to the zone it attacks (27/10, the user: "les défenses de zone sont supposées rester dans
    les zones ... le problème est le comportement des adversaires qui ne se dirigent pas vers la zone": their ways ended
    by it, the bots then put away far off or left to the game's own roaming): from its last frame the mesh's way to the
    spot, `short` u short of it, at a rifle's walk (32 frames a second, as the demo's), turned the way it goes (16:58, Nuke:
    stopped 150 u short, the defender hidden in its zone, 18 waves taken off unseen: into the zone, to the post itself).
    -> the path's frames with the walk added (as they were when there is no way); None when the mesh's way there goes
    round the map (DETOUR): that hit attacks another place, it is left out."""
    from wily.training import navmesh
    if not mp or len(path) < 10:
        return path
    last = path[-5:-2]
    out = list(path)
    d0 = math.dist(last[:2], spot[:2])
    if d0 > short + 40:
        W = navmesh.route(mp, last, spot)
        if len(W) < 2:
            return path
        way = sum(math.dist(a[:2], b[:2]) for a, b in zip(W, W[1:]))
        if way > DETOUR[0] * d0 and way > d0 + DETOUR[1]:
            return None
        out += _walk(W, speed, short)
    # then it clears the zone (27/10 19:00, Vertigo B: at the post, the defender hidden in his zone, left to the game it
    # walked off, 12 waves taken off unseen)
    if poly and math.dist(out[-5:-3], spot[:2]) <= 150:
        out += _zone_sweep(mp, out[-5:-2], poly, spot)
    return out


def _walk(W, speed, short=0.0):
    """Frames along a mesh way (32 a second), turned the way it goes, `short` u short of its end."""
    L = [0.0]
    for a, b in zip(W, W[1:]):
        L.append(L[-1] + math.dist(a[:2], b[:2]))
    stop = L[-1] - short
    out, s, k, step = [], speed / 32.0, 0, speed / 32.0
    while s < stop:
        while k + 1 < len(W) and L[k + 1] < s:
            k += 1
        if k + 1 >= len(W):
            break
        a, b = W[k], W[k + 1]
        f = (s - L[k]) / max(1e-6, L[k + 1] - L[k])
        x, y, z = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f
        out += [round(x, 1), round(y, 1), round(z, 1), round(math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), 1), 0.0]
        s += step
    return out


def _in_zone(poly, x, y):
    inside, n = False, len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i][:2], poly[(i + 1) % n][:2]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _zone_sweep(mp, at, poly, spot, legs=3, speed=150.0, most=12.0, reach=420.0):
    """An attacker come to the post clears the zone you hold (27/10, the user: "les adversaires ... ne se dirigent pas
    vers la zone"; a zone defense is played moving inside it, the attackers looking for you there): from where its way
    ended, at a walk, by `legs` of the zone's spots each the farthest from the ones it went by (its corners), on the
    post's floor, `reach` u of the post at most (21:58, Nuke's Tunnels: a long corridor's far end, 1390 u from you), `most`
    s at most; the plugin gives it to the game only when it sees you or is on you.
    -> its frames ([] when the zone has no spot on the mesh)."""
    from wily.training import navmesh
    xs, ys = [q[0] for q in poly], [q[1] for q in poly]
    grid = []
    for x in np.arange(min(xs), max(xs) + 1, 48.0):
        for y in np.arange(min(ys), max(ys) + 1, 48.0):
            if _in_zone(poly, x, y):
                q = navmesh.nearest(mp, [float(x), float(y), spot[2]], r=24.0, dz=48.0)
                if q and abs(q[2] - spot[2]) < 48 and math.dist(q[:2], spot[:2]) <= reach:
                    grid.append(q)
    if len(grid) < 2:
        return []
    out, cur, went = [], list(at), [list(at)]
    for _ in range(legs):
        nxt = max(grid, key=lambda q: min(math.dist(q[:2], p[:2]) for p in went) + random.uniform(0, 60))
        if math.dist(nxt[:2], cur[:2]) < 96:
            break
        W = navmesh.route(mp, cur, nxt)
        if len(W) < 2:
            continue
        out += _walk(W, speed)
        went.append(nxt)
        cur = nxt
        if len(out) >= most * 32 * 5:
            return out[:int(most * 32) * 5]
    return out


def _defense_tracks(hits, spot, n=24, foes=None, mp=None, poly=None):
    """A defense's attackers: real hits on the site in their real proportions (the ways attackers really take: few by
    mid when few go by mid, 04/10), each one from 2 s before a CT first saw it in its match, so it walks in out of sight
    instead of appearing in front of you ("the spawn kill problem"), never closer than 700 u; with its grenades. For a
    post (foes: its CT spot): from 3 s before it comes into that spot's sight, 900 u away at least (06/10: "ils sont trop
    proches de moi"). A post's attacker comes AT it (09/10, his video: "il faut que les bots se dirigent vers la zone que je
    défends", "si je ne les tue pas quand ils passent devant moi, après ils ne sont plus là"): a way that only passes by
    (never within 650 u of the spot) is left out, and the walk ends 1 s after its closest point, where the bot then fights
    on its own; and it starts out of sight (one in the spot's sight in its first 1.5 s appeared in front of you: "ils me
    spawnent littéralement dessus")."""
    cut = []
    for t in hits:
        P = np.array(t["path"], float).reshape(-1, 5)
        d = np.hypot(P[:, 0] - spot[0], P[:, 1] - spot[1])
        sp = _first_seen(foes, P, r=180) if foes else t.get("spot", -1)
        far = 900 if foes else 700
        if 0 <= sp < 32 and d[0] < 1200:   # seen from its very first second, close: it would appear in your sight
            continue
        end = len(P)
        if foes:
            if sp < 48:   # in the post's sight from the start (or never): it would pop up in front of you
                continue
            d3 = np.linalg.norm(P[:, :3] - np.asarray(spot, float)[:3], axis=1)
            near = sp + int(np.argmin(d3[sp:]))
            if d3[near] > 650:   # it only passes by, far
                continue
            end = min(len(P), near + 32)
        k = max(0, sp - (72 if foes else 64)) if sp >= 0 else 0
        while k > 0 and d[k] < far:
            k -= 1
        if d[k] < far or end - k < 40:
            continue
        # on the ground at its start: one cut in the middle of a jump put its bot in the air, in the stairs' ceiling the
        # player cleared crouched (17/10, the self-test: Inferno's Apps, a bot caught there at each start)
        air = P[:, 2] - _opening(P[:, 2]) > 6
        steep = np.r_[np.abs(np.diff(P[:, 2])) > 2.5, False]   # a takeoff or a stair: its next frames climb or drop
        while k < end - 40 and (air[k] or steep[k:k + 3].any()):
            k += 1
        way = _toward(mp, t["path"][5 * k:5 * end], spot, poly=poly)
        if way is None:   # its way to the spot round the map (10/11): it attacks somewhere else
            continue
        cut.append({"zone": t["zone"], "path": way,
                    "nades": [dict(nd, f=nd["f"] - k) for nd in t.get("nades") or [] if k <= nd["f"] < end]})
    by = {}
    for t in cut:
        by.setdefault(t["zone"], []).append(t)
    pick = []
    for w, ts in by.items():   # each way its share of the n
        pick += random.sample(ts, min(len(ts), max(1, round(n * len(ts) / len(cut)))))
    random.shuffle(pick)
    return pick[:n]


KIT_CLASS = {"rifle": ("M4A4", "M4A1-S", "AK-47", "FAMAS", "Galil AR", "AUG", "SG 553"),
             "close": ("MAG-7", "XM1014", "Nova", "Sawed-Off", "MP9", "MAC-10", "MP7", "MP5-SD", "UMP-45", "P90", "PP-Bizon"),
             "awp": ("AWP", "SSG 08")}


def _defense_kits(sid):
    """The weapons of your site defenses: the ones you play as CT (your demos), one defense each: your rifle, your
    close-range weapon and the AWP when you play them, your pistol (04/10: "other weapons than the M4, ones I do play:
    the pistol, closer range, the sniper"). Longer with the rifle, and more at a time; fewer for the AWP and the pistol."""
    prim, pist, n = Counter(), Counter(), 0
    for mid, _ in _my_matches(str(sid)):
        try:
            L = pd.read_parquet(os.path.join(config.OUT, "deep", mid, "loadout.parquet"), columns=["steamid", "side", "primary", "pistol"])
        except Exception:
            continue
        L = L[(L.steamid.astype(str) == str(sid)) & (L.side == "CT")]
        n += len(L)
        prim.update(L.primary.dropna())
        pist.update(L.pistol.dropna())
    pistol = next((p for p, _ in pist.most_common() if replay._item(p)), "USP-S")
    side_arm = replay._item(pistol) or "weapon_usp_silencer"
    kits = []
    for cls, names in KIT_CLASS.items():
        best = max((x for x in names if prim[x] and replay._item(x)), key=lambda x: prim[x], default=None)
        if cls == "rifle" and not best:
            best = "M4A4"
        if not best or (cls != "rifle" and sum(prim[x] for x in names) < max(5, 0.05 * n)):
            continue
        kits.append({"cls": cls, "name": best, "weapons": ["weapon_knife", side_arm, replay._item(best)], "helmet": True,
                     "bot_weapons": ["weapon_knife", "weapon_glock", RIFLE[2]], "seconds": {"rifle": 180}.get(cls, 150),   # 04/11, his order: more time, all 6 waves
                     "alive": 4 if cls == "rifle" else 3, "goal": {"rifle": 10, "close": 8, "awp": 7}[cls], "weight": 4 if cls == "rifle" else 3})
    kits.append({"cls": "pistol", "name": pistol, "weapons": ["weapon_knife", side_arm], "helmet": False,
                 "bot_weapons": ["weapon_knife", "weapon_glock"], "seconds": 135, "alive": 3, "goal": 6, "weight": 3})
    return kits


def replay_zone(z, mp=None):
    from wily.insights import nades
    return nades.humanize(z, mp) or str(z)


def _world(mp, px, py):
    from wily.core import mapdata
    r = mapdata.get(mp)
    f = r.get("px_factor", 1.0)
    return [round(px / f * r["scale"] + r["pos_x"], 1), round(r["pos_y"] - py / f * r["scale"], 1)]


_LANDS = {}


_RAW = {}


def _findable_spot(mp, typ, side, frm, land, r=150.0):
    """The same lineup thrown by the base from a spot you find again (20/10, his video on a flash from an open square:
    "cette flash est envoyée de nulle part"; 19/10: "un angle, le long d'un mur"): of the base's throws of that kind and
    side from that zone, standing still (or a jumpthrow from standing), that landed within r u of it (a flash: wherever it
    popped above), the spot most of them stood on that has a wall by it (spot_walls): one of its throws, its aim and its
    technique. None: no such throw."""
    if mp not in _RAW:
        try:
            N = pd.read_parquet(os.path.join(config.OUT, "population", "nades.parquet"), filters=[("map", "==", mp)],
                                columns=["type", "side", "zone", "X", "Y", "Z", "pitch", "yaw", "jump", "crouch", "speed", "land_X", "land_Y", "land_Z"])
        except Exception:
            N = None
        if N is not None:   # its words as categories: compared 600 times a map (22/10: 10 s of Dust2's Prepare on them)
            for c in ("type", "side", "zone"):
                N[c] = N[c].astype("category")
        _RAW[mp] = N   # each map's kept (20/10: one at a time, Prepare asking two maps read the table again and again)
    N = _RAW[mp]
    if N is None or not land:
        return None
    n = N[(N.type == typ) & (N.side == side) & (N.zone == frm) & (N.speed < 30) & N.land_X.notna()]
    n = n[np.hypot(n.land_X - land[0], n.land_Y - land[1]) < r]
    if typ != "flash" and len(land) >= 3:
        n = n[(n.land_Z - land[2]).abs() < 120]
    best = None
    for _, g in n.groupby([(n.X / 24).round(), (n.Y / 24).round()]):
        if len(g) < 2:
            continue
        c = [float(g.X.median()), float(g.Y.median()), float(g.Z.median())]
        if (best is None or len(g) > best[0]) and spot_walls(mp, c)["ok"]:
            best = (len(g), g, c)
    if not best:
        return None
    g, c = best[1], best[2]
    t = g.iloc[int(np.argmin(np.hypot(g.X.to_numpy() - c[0], g.Y.to_numpy() - c[1])))]
    how = "jumpthrow" if bool(t.jump) else "crouching" if bool(t.crouch) else "standing still"
    return [round(float(t.X), 1), round(float(t.Y), 1), round(float(t.Z), 1)], [round(float(t.pitch), 2), round(float(t.yaw), 2)], how


def _land(mp, typ, pos, ang=None):
    """Where that very throw landed (the one whose spot and aim the drill gives), not the middle of its group: a
    bouncing molotov of the group can land 300 u from it (03/10). With its height when the demo it comes from is here
    (its detonation point): x, y, z; else x, y. Matched on its aim too (17/10: the guided bot's misses, 70 throws of
    the base from Anubis' Canal spot, each its own way: their middle was nobody's landing)."""
    if mp not in _LANDS:
        f = os.path.join(config.OUT, "population", "nades.parquet")
        cols = ["map", "match", "round", "type", "X", "Y", "land_px", "land_py"]
        try:
            N = None
            for more in (["pitch", "yaw", "land_X", "land_Y", "land_Z"], ["land_X", "land_Y", "land_Z"], []):
                try:   # a player's copy: each throw's landing came with the base, its demo stays on the coach's PC (05/10)
                    N = pd.read_parquet(f, columns=cols + more, filters=[("map", "==", mp)])
                    break
                except Exception:
                    continue
            N = N[N["map"] == mp].copy()
            N["type"] = N["type"].astype("category")   # compared for each lineup (22/10: 4 s of Dust2's Prepare)
            _LANDS[mp] = N
        except Exception:
            _LANDS[mp] = None
    N = _LANDS[mp]
    if N is None or not len(N):
        return None
    m = N[(N.type == typ) & ((N.X - pos[0]).abs() < 1) & ((N.Y - pos[1]).abs() < 1)]
    if not len(m):
        return None
    if ang is not None and "pitch" in m:
        aim = m[((m.pitch - ang[0]).abs() < 0.5) & (((m.yaw - ang[1] + 180) % 360 - 180).abs() < 0.5)]
        if len(aim):
            m = aim
    if "land_X" in m and m.land_X.notna().any():
        q = m[m.land_X.notna() & m.land_Z.notna()][["land_X", "land_Y", "land_Z"]].to_numpy(float)[:5]
        if len(q):
            return [round(float(v), 1) for v in np.median(q, axis=0)]
    pts = []
    for mid, rnd in zip(m["match"].astype(str), m["round"]):   # the same throw in its demo: x, y and z
        try:
            G = pd.read_parquet(os.path.join(config.OUT, "deep", mid, "grenades.parquet"),
                                columns=["round", "type", "X", "Y", "land_X", "land_Y", "land_Z"])
        except Exception:
            continue
        g = G[(G["round"] == rnd) & (G.type == typ) & ((G.X - pos[0]).abs() < 1) & ((G.Y - pos[1]).abs() < 1)].dropna()
        pts += g[["land_X", "land_Y", "land_Z"]].values.tolist()
        if len(pts) >= 5:
            break
    if pts:
        return [round(float(v), 1) for v in np.median(np.array(pts, float), axis=0)]
    return _world(mp, float(m.land_px.median()), float(m.land_py.median()))


SPOTS_F = os.path.join(config.OUT, "train_spots.json")


_MAPDIRS = {}


def _map_dirs(mp):
    """The base's matches on a map. Kept 10 min in memory (06/10: a map's stuff drills asked 19 times, reading the
    2,900 matches' meta.json each time: 54,000 files, 14 s before the warm-up could start), from the ledger of the base's
    matches (22/10, his test video: Prepare's first answer after the app started, 35 s, refreshed, "j'ai souvent une
    erreur comme ça qui pète": 5,101 meta.json opened on the hard disk; the ledger reads only the new ones). A folder
    still being written (.<id>.tmp) is no match yet."""
    hit = _MAPDIRS.get(mp)
    if hit and time.time() - hit[0] < 600:
        return hit[1]
    try:
        from wily.core import ledger
        facts = ledger.match_facts()
    except Exception as e:
        print("map dirs: no ledger", e, flush=True)
        facts = None
    if facts is not None:
        dirs = sorted(m for m, f in facts.items() if not m.startswith(".") and (f or {}).get("map") == mp)
        _MAPDIRS[mp] = (time.time(), dirs)
        return dirs
    dirs = []
    try:
        names = sorted(os.listdir(os.path.join(config.OUT, "deep")))
    except FileNotFoundError:   # a fresh install before its first analysis (08/10, the installer's test): no match yet
        names = []
    for d in names:
        try:
            with open(os.path.join(config.OUT, "deep", d, "meta.json"), encoding="utf-8") as fh:
                if json.load(fh).get("map") == mp:
                    dirs.append(d)
        except (OSError, ValueError):
            continue
    _MAPDIRS[mp] = (time.time(), dirs)
    return dirs


_SPOTS_MEM = {"mt": None, "c": {}}


def _spots(mp):
    """Where each side really stands on the map: the duels of every demo (killers and victims), 64 u cells with their
    mean position and how often. Cached per map, computed again after a quarter more matches."""
    try:   # the file read again only when it changed (19 reads of 1 MB per map's stuff before)
        mt = os.path.getmtime(SPOTS_F)
        if _SPOTS_MEM["mt"] != mt:
            with open(SPOTS_F, encoding="utf-8") as fh:
                _SPOTS_MEM.update(mt=mt, c=json.load(fh))
        cache = _SPOTS_MEM["c"]
    except (OSError, ValueError):
        cache = {}
    dirs = _map_dirs(mp)
    c = cache.get(mp)
    if c and c.get("n", 0) >= 0.8 * len(dirs):
        return c
    cells = {}
    for d in dirs:
        try:
            D = pd.read_parquet(os.path.join(config.OUT, "deep", d, "duels.parquet"),
                                columns=["killer_side", "victim_side", "killer_X", "killer_Y", "killer_Z", "victim_X", "victim_Y", "victim_Z"])
        except Exception:
            continue
        for who in ("killer", "victim"):
            for sd, x, y, z in zip(D[f"{who}_side"], D[f"{who}_X"], D[f"{who}_Y"], D[f"{who}_Z"]):
                if sd in ("T", "CT") and x == x and y == y and z == z:
                    k = (sd, int(x // 64), int(y // 64), int(z // 64))
                    a = cells.setdefault(k, [0, 0.0, 0.0, 0.0])
                    a[0] += 1
                    a[1] += x
                    a[2] += y
                    a[3] += z
    out = {"n": len(dirs), "T": [], "CT": []}
    for (sd, *_), (n, sx, sy, sz) in sorted(cells.items(), key=lambda kv: -kv[1][0]):
        if len(out[sd]) < 4000:
            out[sd].append([round(sx / n, 1), round(sy / n, 1), round(sz / n, 1), n])
    cache[mp] = out
    with open(SPOTS_F, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, separators=(",", ":"))
    return out


VICTIMS_CHECKED = os.path.join(config.HERE, "resources", "victims_checked.json")
_VCHK = {"t": 0, "v": {}}


def victim_key(mp, typ, me, land):
    return f"{mp}|{typ}|{round(me[0])}|{round(me[1])}|{round(land[0])}|{round(land[1])}"


def _victims_checked(mp, typ, me, land, vs):
    """The victims the guided bot found taking it (19/10, tools/victim_check.py: "vérifie bien avec tes bots que la POV de
    la personne qui subit la flash subit vraiment la flash"): one it measured untouched left out; none left when it
    measured them all untouched (no "from their side" rather than a wrong one)."""
    if time.time() - _VCHK["t"] > 60:
        _VCHK.update(t=time.time(), v=config.read_json(VICTIMS_CHECKED, {}) or {})
    rec = _VCHK["v"].get(victim_key(mp, typ, me, land))
    if not rec:
        return vs
    def miss(v):
        return any(not c.get("hit") and math.dist(c["pos"][:2], v["pos"][:2]) < 24 for c in rec.get("victims") or [])
    return [v for v in vs if not miss(v)]


def _thrower_sees(mp, typ, me, land):
    """A flash whose thrower sees it pop (19/10, his video: "je flash un endroit que je vois en ligne directe, donc si il y
    a quelqu'un qui pique un peu plus tard, je me fais tuer"): tools/victim_check.py's guide blinded by it on the spot it
    is thrown from, turned to where it pops."""
    if typ != "flash":
        return False
    if time.time() - _VCHK["t"] > 60:
        _VCHK.update(t=time.time(), v=config.read_json(VICTIMS_CHECKED, {}) or {})
    rec = _VCHK["v"].get(victim_key(mp, typ, me, land)) or {}
    return bool((rec.get("thrower") or {}).get("seen"))


def zone_raw(mp, p):
    """The demos' own place name where p is: the base's Ts' samples around it (64 u, else 128, else 256: a corner they
    seldom stand in; its floor), the most common. None: no T ever near."""
    E = _early(mp)
    X, Y, Z = E.X.to_numpy(), E.Y.to_numpy(), E.Z.to_numpy()
    for r in (64, 128, 256):
        m = (np.abs(X - p[0]) < r) & (np.abs(Y - p[1]) < r) & (np.abs(Z - p[2]) < 80)
        z = E.zone[m].astype(str)
        z = z[z != "?"]
        if len(z) >= 5:
            return z.mode().iloc[0]
    return None


_WAYS = {}


def way_zones(mp, zone, site):
    """One way in to a site (22/10, the user on Dust2's exec A from Long: "la flash que tu envoies, elle part de short A,
    pas de longue A ... je peux pas mettre les deux smokes longue A et le flash short A"): the zones the base's Ts go
    through from that zone to the site (half of them at least) and the zone they come from into it (4 in 10 at least).
    Dust2's Long Doors: Long, A Ramp, Outside Long; not Short Stairs (2 in 100)."""
    k = (mp, zone, site)
    if k in _WAYS:
        return _WAYS[k]
    E = _early(mp).sort_values(["d", "round", "sid", "t"])
    z = E.zone.astype(str).to_numpy()
    key = (E.d.to_numpy().astype(np.int64) * 100000 + E["round"].to_numpy().astype(np.int64) * 100) * 1000 + E.sid.cat.codes.to_numpy()
    cuts = np.r_[0, np.nonzero(np.diff(key))[0] + 1, len(key)]
    seen, before, n = Counter(), Counter(), 0
    for a, b in zip(cuts[:-1], cuts[1:]):
        t = z[a:b]
        hit, end = np.nonzero(t == zone)[0], np.nonzero(t == site)[0]
        if len(hit) and len(end) and hit[0] < end[-1]:
            n += 1
            seen.update(set(t[hit[0]:end[-1] + 1]))
            prev = [x for x in t[:hit[0]] if x not in ("?", zone)]
            if prev:
                before[prev[-1]] += 1
    out = {zone, site} | {x for x, c in seen.items() if n and c >= 0.5 * n} | {x for x, c in before.items() if n and c >= 0.4 * n}
    _WAYS[k] = out
    return out


FIRE_R = 150.0   # a molotov's fire on the floor, about


def molotov_blocks(mp, land, t_pop, foe="T", secs=7.0):
    """The share of the base's Ts on their way by a molotov's fire (500 u of it, its floor) while it burns that go
    through it, not round it: a fire they walk round blocks nothing (22/10, the user on Dust2's A defense: "les
    terroristes qui pushent long peuvent contourner la molotov pour se rapprocher du car ... ma molotov ne sert à rien à
    part m'exposer stuff en main pendant un timing"; 58 % of the Ts there went round it). -> (share, tracks) or (None, 0)."""
    if foe != "T" or not land or len(land) < 3:
        return None, 0
    E = _early(mp)
    W = E[(E.t >= t_pop) & (E.t <= t_pop + secs)]
    d = np.hypot(W.X.to_numpy() - land[0], W.Y.to_numpy() - land[1])
    W = W[(d < 500) & (np.abs(W.Z.to_numpy() - land[2]) < 120)]
    if not len(W):
        return None, 0
    W = W.assign(dd=np.hypot(W.X.to_numpy() - land[0], W.Y.to_numpy() - land[1]))
    m = W.groupby(["d", "round", "sid"], observed=True).dd.min()
    m = m[m < 400]
    if len(m) < 20:
        return None, int(len(m))
    return round(float((m < FIRE_R).mean()), 2), int(len(m))


def _standable(mp, vs):
    """Each victim where a player stands (22/10, his test video: "la personne qui cible le stuff est à moitié dans le
    mur"): one off the map's mesh (the base's player in the air, on a prop's edge, against a wall) put on the nearest
    floor a player stands on, 48 u of it at most; none there: left out. A map without a mesh: as they are."""
    from wily.training import navmesh
    out = []
    for v in vs:
        p = v.get("pos")
        on = navmesh.on_mesh(mp, p) if p and len(p) >= 3 else None
        if on is None or on:
            out.append(v)
            continue
        q = navmesh.nearest(mp, p)
        if q:
            out.append(dict(v, pos=q))
    return out


def _victims(mp, team, typ, land, me, side=None, t_med=None, checked=True, see=None, avoid=None):
    """The enemies a grenade is for (_victims_raw), each where a player stands (_standable); avoid: the places its own
    exec already holds (exec_avoid)."""
    v = _standable(mp, _victims_raw(mp, team, typ, land, me, side, t_med, checked, see, avoid))
    # checked again where they now stand (24/10, the checks: Ancient's Alley molotov, its victim moved by _standable onto
    # the very spot the guided bot had measured untouched); an entry drill has no landing
    return _victims_checked(mp, typ, me, land, v) if checked and v and land else v


def _victims_raw(mp, team, typ, land, me, side=None, t_med=None, checked=True, see=None, avoid=None):
    """The enemies a grenade is for, where the base's players really were when the same lineup landed (06/10, the user:
    "la personne qui subit le stuff doit être là où quelqu'un a pris des dégâts avec cette grenade": a Squeaky flash is
    for the Ts in Squeaky, not for a CT outside): the throws from that spot onto that place in the demos, the enemies in
    its reach at that moment (an HE 350 u, a molotov 220 u, a flash 650 u, a smoke 900 u, same floor), their most
    frequent spots, turned to it. Without such throws: the most held enemy spots in its reach (a smoke or a flash: the
    ones beyond it from where you throw); a molotov: in its fire, turned to where it came from."""
    if not land or len(land) < 3:
        return []
    if see and typ == "smoke":   # a defense's smoke: the view onto its defender's post it cuts (21/10); a take's: onto its entry
        # (or onto its own way in and the site's, both sides of it: 22/10, Dust2's Short smoke from Long, a list of views)
        v = []
        for s in (see if isinstance(see[0], (list, tuple)) else [see]):
            v += [o for o in _defense_smoke_victims(mp, land, s, "T" if team == 3 else "CT") if all(math.dist(o["pos"], q["pos"]) >= 150 for q in v)]
        return _victims_checked(mp, typ, me, land, v) if checked else v
    key = (f"{'v12' if typ == 'flash' and team == 2 else 'v10'}|{mp}|{typ}|{team}|{round(me[0])}|{round(me[1])}|{round(land[0])}|{round(land[1])}"   # v10: a defender's flash; v12: a take's (holds, nearer its pop)
           + (f"|{round(float(t_med))}" if t_med else "")   # for the Ts on their way then (22/10)
           + "".join(f"|{t[0][0]}{round(q[0])},{round(q[1])}" for t, q in [(a[0], a[1]) for a in avoid or []] if typ == "flash"))
    try:
        VC = json.load(open(VICTIMS_F, encoding="utf-8"))
    except (OSError, ValueError):
        VC = {}
    hit = VC.get(key)
    if hit and time.time() - hit.get("t", 0) < 7 * 86400:   # a week: the base changes slowly
        return _victims_checked(mp, typ, me, land, hit["v"]) if checked else hit["v"]
    v = _victims_of(mp, team, typ, land, me, t_med, avoid)
    VC[key] = {"t": time.time(), "v": v}
    try:
        config.write_json(VICTIMS_F, VC)
    except OSError:
        pass
    return _victims_checked(mp, typ, me, land, v) if checked else v


def _defense_smoke_victims(mp, land, see, foe="T"):
    """A site defense's smoke (21/10, resources/defenses.json: "cuts Heaven's view onto the site"): the Ts whose view of
    the defender's post it is for, not the ones beyond it from where it is thrown (the guided bot found none of those
    cut: they look at the site past it). The base's T duel spots met 8 times at least, 900 u of it at most (a smoke's
    reach) on its floor, whose sight of the post passes through it (144 u of its middle, its radius), the most met first, 2 at most,
    150 u apart; each turned to the post, "see" the post's eyes: the guided bot checks the smoke really cuts that line.
    A take's smoke (foe "CT", 21/10, Dust2's cross smoke: thrown from Long Doors, nobody could see its thrower anyway):
    the CTs whose view of where its entry crosses it cuts."""
    eye = [see[0], see[1], see[2] + 64]
    out = []
    for x, y, z, n in sorted(_spots(mp).get(foe) or [], key=lambda h: -h[3]):
        if n < 8 or math.hypot(x - land[0], y - land[1]) > 900 or abs(z - land[2]) > 100:   # its floor
            continue
        dx, dy = eye[0] - x, eye[1] - y
        t = max(0.0, min(1.0, ((land[0] - x) * dx + (land[1] - y) * dy) / ((dx * dx + dy * dy) or 1.0)))
        if math.hypot(x + t * dx - land[0], y + t * dy - land[1]) > 144 or any(math.dist([x, y, z], o["pos"]) < 150 for o in out):
            continue
        out.append({"pos": [round(x, 1), round(y, 1), round(z, 1)], "ang": _angle([x, y, z + 64], eye), "see": eye})
        if len(out) >= 2:
            break
    return out


VICTIMS_F = os.path.join(config.OUT, "train_victims.json")


def _real_line(mp, side, p, heads=()):
    """The line a player on that spot holds (07/10, the user: "quand je subis la flash, je regarde une ligne qui existe
    vraiment ... une ligne que tu connais déjà parce qu'il y a la data des pre-fires"): where the players there were
    heading; a CT on a spot the base's CTs fight from: where their foes stood (the prefires' data), else the entrance
    nearest it; a T: the site nearest it. None: unknown."""
    ys = [y for q, y in heads if math.dist(q[:2], p[:2]) < 120]
    if ys:
        a = np.radians(ys)
        return [0.0, round(float(np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean()))), 1)]
    sites = list((site_data(mp).get("sites") or {}).values())
    eye = [p[0], p[1], p[2] + 64]
    if side == "CT":
        best = None
        for S in sites:
            for h in _site_holds(S):
                d = math.dist(h["pos"][:2], p[:2])
                if d < 300 and abs(h["pos"][2] - p[2]) < 90 and (h.get("seen") or []) and (best is None or d < best[0]):
                    best = (d, h)
        if best:
            Q = np.array(best[1]["seen"], float).reshape(-1, 3)
            return _angle(eye, list(np.median(Q, axis=0) + [0, 0, 56]))
        ent = [e["start"] for S in sites for e in S.get("entrances") or [] if e.get("start")]
        ent = [q for q in ent if math.dist(q[:2], p[:2]) < 2500]
        if ent:
            q = min(ent, key=lambda q: math.dist(q[:2], p[:2]))
            return [0.0, round(math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])), 1)]
        return None
    tg = [S["defend"] for S in sites if S.get("defend") and math.dist(S["defend"][:2], p[:2]) < 3000]
    if tg:
        q = min(tg, key=lambda q: math.dist(q[:2], p[:2]))
        return [0.0, round(math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])), 1)]
    return None


def _rotating(mp, land, foe):
    """One of theirs on his way in where a smoke lands (20/10, his video: "il faudrait que la personne qui subisse le
    stuff soit un peu en amont de cette smoke, comme si c'était un joueur qui rotate du A vers le B, et qui arriverait au
    niveau du spawn CT"): the base's way of their side (Momentum's ways: a spawn or the other site to this one) passing
    nearest it (400 u at most), 300 u before it, turned to it; "see": what it keeps him from seeing, that way 300 u on
    past it (the way's end short of that: 300 u on past it the way he looks)."""
    best = None
    for w in (momentum.load(mp, build=False) or {}).get("routes") or []:
        if w.get("side") != foe or len(w.get("line") or []) < 2:
            continue
        L = np.asarray([p[:3] for p in w["line"]], float)
        d = np.hypot(L[:, 0] - land[0], L[:, 1] - land[1])
        i = int(d.argmin())
        if d[i] < 400 and (best is None or d[i] < best[0]):
            best = (float(d[i]), L, i)
    if not best:
        return None
    _, L, i = best
    acc, j = 0.0, i
    while j > 0 and acc < 300:
        acc += float(np.hypot(L[j, 0] - L[j - 1, 0], L[j, 1] - L[j - 1, 1]))
        j -= 1
    p = L[j]
    acc, k = 0.0, i
    while k < len(L) - 1 and acc < 300:
        acc += float(np.hypot(L[k + 1, 0] - L[k, 0], L[k + 1, 1] - L[k, 1]))
        k += 1
    if acc >= 150:
        see = L[k]
    else:
        u = np.asarray(land[:2], float) - p[:2]
        u = u / max(1.0, float(np.hypot(*u)))
        see = np.array([land[0] + 300 * u[0], land[1] + 300 * u[1], land[2]], float)
    return {"pos": [round(float(v), 1) for v in p], "ang": [0.0, round(math.degrees(math.atan2(land[1] - p[1], land[0] - p[0])), 1)],
            "see": [round(float(v), 1) for v in see]}


AIM_TOL_F = os.path.join(config.HERE, "resources", "aim_tolerance.json")
_AT = {"t": 0.0, "v": {}}


def aim_key(mp, typ, pos, ang):
    """A lineup's key in resources/aim_tolerance.json: its map, kind, spot and aim."""
    return f"{mp}|{typ}|{round(pos[0])}|{round(pos[1])}|{round(pos[2])}|{round(float(ang[0]), 1)}|{round(float(ang[1]), 1)}"


def aim_tol(d):
    """The yellow circle a lineup's throw allows, degrees (23/10, the user: "le rond de visée de 0,9° est trop large pour
    les lancers sensibles au rebond", tools/aim_tolerance.py: how far its landing moves for a tenth of a degree); 0 when
    not measured (the plugin's 0.9)."""
    if time.time() - _AT["t"] > 60:
        _AT.update(t=time.time(), v=config.read_json(AIM_TOL_F, {}) or {})
    me = d.get("me") or {}
    if not d.get("map") or not d.get("type") or len(me.get("pos") or []) < 3 or len(me.get("ang") or []) < 2:
        return 0.0
    rec = _AT["v"].get(aim_key(d["map"], d["type"], me["pos"], me["ang"]))
    return float(rec["tol"]) if rec and rec.get("tol") else 0.0


WEAPON_COLS = ["killer_side", "killer_X", "killer_Y", "killer_Z", "victim_X", "victim_Y", "weapon"]
_WEAPONS = {}


def duel_weapons(mp):
    """The map's kills with the killer's spot and weapon (one copy kept, ledger.gathered): which guns a spot is played
    with (23/10, the user: "varier les armes selon le spot (AWP sur les longues lignes ...)")."""
    if mp not in _WEAPONS:
        from wily.core import ledger
        stamps = ledger.folders(config.DEEP)
        items = [(d, os.path.join(config.DEEP, d, "duels.parquet"), stamps.get(d)) for d in _map_dirs(mp)]
        try:
            D = ledger.gathered(f"duel_weapons_{mp}", items, prep=lambda x, k: x.reindex(columns=WEAPON_COLS))
        except Exception as e:
            print("duel weapons", mp, e, flush=True)
            D = pd.DataFrame(columns=WEAPON_COLS)
        _WEAPONS[mp] = D.reindex(columns=WEAPON_COLS).dropna(subset=WEAPON_COLS[1:4])
    return _WEAPONS[mp]


def awp_share(mp, pos, side, r=120.0):
    """The share of a spot's kills made with an AWP by its own side (killers within r, same floor), and how many."""
    D = duel_weapons(mp)
    m = (D.killer_side.to_numpy() == side) & (np.hypot(D.killer_X.to_numpy() - pos[0], D.killer_Y.to_numpy() - pos[1]) < r) \
        & (np.abs(D.killer_Z.to_numpy() - pos[2]) < 90)
    n = int(m.sum())
    return (float((D.weapon.to_numpy()[m] == "awp").mean()) if n else 0.0), n


APPROACH_F = os.path.join(config.OUT, "train_approach.json")


def approach(mp, me, secs=7.0, r=64.0):
    """The base's Ts' way up to a spot (23/10, the user: "montrer, pendant la vue du ciel, ton personnage qui avance sur le
    chemin des T de la base jusqu'à son départ"): of their tracks that come within r of it on its floor, the one whose
    last `secs` before it start nearest all of theirs (the most usual way in), a point every half second, the oldest
    first; [] when none walked there. Kept in out/train_approach.json."""
    key = f"{mp}|{round(me[0])}|{round(me[1])}|{round(me[2])}"
    book = config.read_json(APPROACH_F, {}) or {}
    if key in book:
        return book[key]
    E = _early(mp)
    box = (np.abs(E.X.to_numpy() - me[0]) < 2200) & (np.abs(E.Y.to_numpy() - me[1]) < 2200)
    W = E[box]
    X, Y, Z, T = W.X.to_numpy(float), W.Y.to_numpy(float), W.Z.to_numpy(float), W.t.to_numpy(float)
    K = W.d.to_numpy().astype(np.int64) * 100000 + W["round"].to_numpy().astype(np.int64) * 100 + W.sid.cat.codes.to_numpy().astype(np.int64) % 100
    near = (np.hypot(X - me[0], Y - me[1]) < r) & (np.abs(Z - me[2]) < 80)
    out = []
    firsts = {}
    for k, t in zip(K[near], T[near]):
        if k not in firsts or t < firsts[k]:
            firsts[k] = t
    ways = []
    for k, t in list(firsts.items())[:300]:
        m = (K == k) & (T >= t - secs) & (T <= t)
        o = np.argsort(T[m])
        P = np.c_[X[m][o], Y[m][o], Z[m][o]]
        if len(P) >= max(4, int(secs * 2) - 2) and np.hypot(*(P[-1, :2] - P[0, :2])) >= 300:
            ways.append(P)
    if ways:
        S = np.array([w[0] for w in ways])
        med = np.median(S, axis=0)
        best = min(ways, key=lambda w: math.dist(w[0][:2], med[:2]))
        out = [[round(float(v), 1) for v in p] for p in best[:-1]]
    book[key] = out
    config.write_json(APPROACH_F, book)
    return out


HOLD_COLS = ["t", "killer_side", "victim_side", "killer_X", "killer_Y", "killer_Z", "victim_X", "victim_Y", "victim_Z", "killer_speed"]
_HOLDS = {}


def _duel_sides(mp):
    """The map's duels with their sides, the round's clock and the killer's speed (one copy kept, ledger.gathered: only
    the new or changed matches read)."""
    if mp not in _HOLDS:
        from wily.core import ledger
        stamps = ledger.folders(config.DEEP)
        items = [(d, os.path.join(config.DEEP, d, "duels.parquet"), stamps.get(d)) for d in _map_dirs(mp)]
        try:
            D = ledger.gathered(f"duel_sides_{mp}", items, prep=lambda x, k: x.reindex(columns=HOLD_COLS))
        except Exception as e:
            print("duel sides", mp, e, flush=True)
            D = pd.DataFrame(columns=HOLD_COLS)
        _HOLDS[mp] = D.reindex(columns=HOLD_COLS).dropna(subset=HOLD_COLS[3:9])
    return _HOLDS[mp]


def exec_avoid(d, drills):
    """The places its own exec already holds (22/10 eve, the user on Fachwerk's exec A flash 5: "si la personne est là,
    elle subit déjà la molotov"): the smokes' and fires' landings of the drills of its clip, itself aside."""
    def group(x):   # its clip, or its id less its rank (an exec's step drills lose their clip: execs.sequence)
        return x.get("clip") or (str(x.get("id") or "").rsplit(":", 1)[0] if str(x.get("id") or "").count(":") >= 2 else None)
    g = group(d)
    if not g:
        return []
    return [(o["type"], o["target"]) for o in drills if o is not d and group(o) == g
            and o.get("type") in ("smoke", "molotov") and o.get("target")]


def _take_flash_holds(mp, land, me, n=2, avoid=None):
    """A take's flash is for the CTs who hold the line its Ts come through by it (22/10 eve, the user on Fachwerk's exec
    A: "ce qu'on cible avec la flash, c'est quelqu'un qui va tenir la ligne portail et qui va donc se faire flash, ce qui
    permettra à l'allié de faire le kill ... des positions assez fortes, des positions qui permettent aux ennemis de faire
    des kills aussi en temps normal ... et des positions où les ennemis peuvent avoir aussi des covers assez rapides"; its
    first flash: "quelqu'un qui attend une personne qui décale juste avant le jump que tu fais pour aller sur le site A",
    not the one at Long's end): the base's CT kills in the round's first minute of Ts within 300 u under its pop, the CTs'
    spots (64 u) with two of them at least, not up the Ts' own way (its zones; the site's own kept), not running (median
    150 u/s at most), a wall of the mesh within 64 u (a cover at hand), the most kills there, then overall less half its
    deaths, 150 u apart; each turned to where its Ts died. [] when the base has none."""
    from wily.training import navmesh
    D = _duel_sides(mp)
    if not len(D):
        return []
    lx, ly = land[0], land[1]
    D = D[D.t <= 60]
    K = D[(D.killer_side == "CT") & (D.victim_side == "T") & (np.hypot(D.victim_X - lx, D.victim_Y - ly) < 300)]
    if len(K) < 2:
        return []
    sc = [(n_, S["center"]) for n_, S in (site_data(mp).get("sites") or {}).items() if S.get("center")]
    site = min(sc, key=lambda x: math.dist(x[1][:2], [lx, ly]))[0] if sc else None
    z0 = zone_raw(mp, me)
    way = (way_zones(mp, z0, site) - {site}) if z0 and site else set()
    N = navmesh.load(mp)
    S = N["segs"] if N else np.zeros((0, 6))

    def cover(p):
        k = np.abs(S[:, 4] - p[2]) < 60
        if not k.any():
            return 1e9
        A, B = S[k][:, 0:2], S[k][:, 2:4]
        d = B - A
        t = np.clip(((p[0] - A[:, 0]) * d[:, 0] + (p[1] - A[:, 1]) * d[:, 1]) / np.maximum((d * d).sum(1), 1e-9), 0, 1)
        return float(np.hypot(A[:, 0] + t * d[:, 0] - p[0], A[:, 1] + t * d[:, 1] - p[1]).min())
    K = K.assign(cx=(K.killer_X // 64).astype(int), cy=(K.killer_Y // 64).astype(int), cz=(K.killer_Z // 64).astype(int))
    rows = []
    for _, g in K.groupby(["cx", "cy", "cz"]):
        if len(g) < 2 or float(g.killer_speed.median()) > 150:
            continue
        p = [float(g.killer_X.mean()), float(g.killer_Y.mean()), float(g.killer_Z.mean())]
        if zone_raw(mp, p) in way or cover(p) > 64:
            continue
        # not in its exec's own fire or smoke: that one is gone already (or sees nothing)
        if any((t == "molotov" and math.hypot(p[0] - q[0], p[1] - q[1]) < 230 and abs(p[2] - (q[2] if len(q) > 2 else p[2])) < 120)
               or (t == "smoke" and math.hypot(p[0] - q[0], p[1] - q[1]) < 200) for t, q in avoid or []):
            continue
        near = lambda X, Y, Z: (np.hypot(X - p[0], Y - p[1]) < 48) & (np.abs(Z - p[2]) < 60)
        kills = int((near(D.killer_X, D.killer_Y, D.killer_Z) & (D.killer_side == "CT")).sum())
        deaths = int((near(D.victim_X, D.victim_Y, D.victim_Z) & (D.victim_side == "CT")).sum())
        line = [float(g.victim_X.median()), float(g.victim_Y.median()), float(g.victim_Z.median())]
        rows.append((len(g), kills - 0.5 * deaths, p, line))
    out = []
    # the strongest first (his "des positions qui permettent aux ennemis de faire des kills aussi en temps normal"): its
    # kills less half its deaths, then its kills on that line; a second one only half as strong at least (his "un endroit
    # où tu peux te trouver quand t'es en train de rota" came second)
    rows.sort(key=lambda r: (-r[1], -r[0]))
    for nk, sc_, p, line in rows:
        if out and sc_ < 0.5 * rows[0][1]:
            break
        # a little nearer its pop, turned a little to it (22/10 eve, the user on flash 4: "légèrement déplacer la personne
        # ... pour que la personne prenne la flash de façon un peu plus longtemps"): its spot within 48 u of the hold's
        # middle nearest the pop (a wall still within 64 u), its view up to 15 degrees to the pop when it pops within 40
        best = None
        for r in (0, 24, 48):
            for k in range(8 if r else 1):
                a = 2 * math.pi * k / 8
                q = navmesh.nearest(mp, [p[0] + r * math.cos(a), p[1] + r * math.sin(a), p[2]], r=24.0 if r else 40.0)
                if q and cover(q) <= 64 and (best is None or math.dist(q, land) < math.dist(best, land)):
                    best = q
        q = [round(float(v), 1) for v in (best or p)]
        if all(math.dist(q, o["pos"]) >= 150 for o in out):
            ang = _angle([q[0], q[1], q[2] + 64], [line[0], line[1], line[2] + 64])
            to_pop = math.degrees(math.atan2(land[1] - q[1], land[0] - q[0]))
            dyaw = (to_pop - ang[1] + 540) % 360 - 180
            if abs(dyaw) < 40:
                ang = [ang[0], round(ang[1] + max(-15.0, min(15.0, dyaw)), 1)]
            out.append({"pos": q, "ang": ang})
        if len(out) >= n:
            break
    return out


def _victims_of(mp, team, typ, land, me, t_med=None, avoid=None):
    lx, ly, lz = land[:3]
    reach = {"he": 350, "molotov": 220, "flash": 650, "smoke": 900}.get(typ, 500)
    foe = "CT" if team == 2 else "T"
    # where their players defend, the most held first (20/10, his video: "mets-moi des spots où les joueurs défendent",
    # "je suis dans le mur", "tu peux mettre la personne qui subit la flash plus loin derrière, il n'y a personne qui va
    # regarder là en étant contact au mur", "il faut que le joueur soit derrière la charrette"): a molotov's in its fire,
    # behind what it lands by (farther from you than its fire); a flash's under it, in front of it from you; a smoke's
    # beyond it; an HE's around it. The base's players hurt by it there only when no held spot fits
    look = [lx, ly, lz + (0 if typ == "flash" else 40)]
    dl = math.hypot(lx - me[0], ly - me[1]) or 1.0
    ax, ay = (lx - me[0]) / dl, (ly - me[1]) / dl
    # a defender's flash: the Ts still on their way in, 250 u farther from the site than it pops at least (22/10, his
    # test video on Dust2's A: "si tu mets la personne ciblée au car, c'est déjà trop tard, faut que la personne ciblée
    # soit dans la longue")
    sc = [S["center"] for S in (site_data(mp).get("sites") or {}).values() if S.get("center")]
    sc = min(sc, key=lambda c: math.dist(c[:2], [lx, ly])) if sc else None
    on_way = typ == "flash" and foe == "T" and sc is not None and math.dist(sc[:2], [lx, ly]) <= 900
    def fits(x, y, z):
        d, ahead = math.hypot(x - lx, y - ly), (x - lx) * ax + (y - ly) * ay
        if typ == "molotov":   # its fire falls down what it lands on: the floor below too
            return d <= 200 and -110 < z - lz < 40
        if typ == "flash":
            if on_way and math.dist(sc[:2], [x, y]) < math.dist(sc[:2], [lx, ly]) + 250:
                return False
            return d <= reach and -450 < z - lz < 100 and ahead >= -150
        if typ == "smoke":
            return d <= reach and abs(z - lz) < 200 and ahead >= 0.5 * d
        return d <= reach and abs(z - lz) < 90
    if on_way and t_med:   # the base's Ts where they are when it pops (thrown at its usual moment): on their way in
        try:
            E = _early(mp)
            t_pop = float(t_med) + 1.5
            W = E[(E.t >= t_pop - 1.0) & (E.t <= t_pop + 1.0)]
            W = W[(np.hypot(W.X - lx, W.Y - ly) < reach) & ((W.Z - lz) > -450) & ((W.Z - lz) < 100)]
            out = []
            for (cx, cy), g in sorted(W.groupby([(W.X / 64).round(), (W.Y / 64).round()], observed=True), key=lambda kv: -len(kv[1])):
                if len(g) < 20:
                    break
                p = [round(float(g.X.median()), 1), round(float(g.Y.median()), 1), round(float(g.Z.median()), 1)]
                if fits(*p) and all(math.dist(p, o["pos"]) > 200 for o in out):
                    out.append({"pos": p, "ang": _angle([p[0], p[1], p[2] + 64], look)})
                if len(out) >= 2:
                    break
            if out:
                return out
        except Exception as e:
            print("victims on their way", mp, e, flush=True)
    held = [h for h in _spots(mp)[foe] if fits(*h[:3])]
    if typ == "molotov":   # behind it first
        held.sort(key=lambda h: (math.hypot(h[0] - me[0], h[1] - me[1]) < dl - 16, -h[3]))
    out = []
    if typ == "smoke":   # first one of theirs on his way in, rotating
        r = _rotating(mp, land, foe)
        if r:
            out.append(r)
    if typ == "flash" and foe == "CT":   # a take's flash: the CTs holding the line its Ts come through by it (22/10 eve)
        hv = _take_flash_holds(mp, land, me, avoid=avoid)
        if hv:
            return hv
    if typ == "flash" and foe == "CT":   # a site's flash: its defenders when the Ts take it first (20/10, his video: "cette
        # flash elle n'est pas faite pour la personne qui l'a [subie], elle est faite pour la personne qui est sur le site
        # A"): the base's CT spots of its takes in its reach (take_spots), the site's own place first, the most met first
        for site, S in (site_data(mp).get("sites") or {}).items():
            if not S.get("center") or math.dist(S["center"][:2], [lx, ly]) > 900:
                continue
            ts = [t for t in take_spots(mp, site[-1]) if fits(*t["pos"])]
            own = f"Bombsite{site[-1]}"
            for t in sorted(ts, key=lambda t: (t["zone"] != own, -t["n"])):
                if all(math.dist(t["pos"], o["pos"]) > 200 for o in out):
                    out.append({"pos": t["pos"], "ang": _real_line(mp, foe, t["pos"]) or _angle([t["pos"][0], t["pos"][1], t["pos"][2] + 64], look)})
                if len(out) >= 2:
                    return out
    for x, y, z, n in held:
        if all(math.dist([x, y, z], o["pos"]) > 200 for o in out):
            out.append({"pos": [x, y, z], "ang": _real_line(mp, foe, [x, y, z]) or _angle([x, y, z + 64], look)})
        if len(out) >= 2:
            return out
    if out:
        return out
    _land(mp, typ, me)   # the base's throws of the map, loaded
    N, hits, heads = _LANDS.get(mp), [], []
    if N is not None and len(N):
        m = N[(N.type == typ) & ((N.X - me[0]).abs() < 24) & ((N.Y - me[1]).abs() < 24)]
        for mid, rnd in list(dict.fromkeys(zip(m["match"].astype(str), m["round"])))[:10]:
            try:
                G = pd.read_parquet(os.path.join(config.OUT, "deep", mid, "grenades.parquet"),
                                    columns=["round", "type", "X", "Y", "t", "flight_s", "land_X", "land_Y", "land_Z", "enemies_blind", "damage"])
                Sm = pd.read_parquet(os.path.join(config.OUT, "deep", mid, "samples.parquet"), columns=["round", "t", "side", "steamid", "X", "Y", "Z", "health"])
            except Exception:
                continue
            g = G[(G["round"] == rnd) & (G.type == typ) & ((G.X - me[0]).abs() < 24) & ((G.Y - me[1]).abs() < 24)
                  & (np.hypot(G.land_X - lx, G.land_Y - ly) < 160)]
            lo, hi = {"flash": (-260, 60), "he": (-150, 90), "molotov": (-90, 90)}.get(typ, (-160, 160))   # its floor (Nuke: A over B)
            for r in g.itertuples():
                if typ == "flash" and not (r.enemies_blind == r.enemies_blind and r.enemies_blind > 0):
                    continue   # that time it blinded nobody
                if typ in ("he", "molotov") and not (r.damage == r.damage and r.damage > 0):
                    continue   # that time it hurt nobody
                tl = float(r.t) + (float(r.flight_s) if r.flight_s == r.flight_s else 1.5)
                q = Sm[(Sm["round"] == rnd) & ((Sm.t - tl).abs() <= 0.5) & (Sm.side == foe) & (Sm.health > 0)]
                q0 = Sm[(Sm["round"] == rnd) & ((Sm.t - (tl - 0.8)).abs() <= 0.4) & (Sm.side == foe)]
                before = dict(zip(q0.steamid.astype(str), zip(q0.X, q0.Y)))
                near = sorted((math.hypot(x - lx, y - ly) + 2 * abs(z - lz), (x, y, z), before.get(str(s)))
                              for x, y, z, s in zip(q.X, q.Y, q.Z, q.steamid) if math.hypot(x - lx, y - ly) <= reach and lo <= z - lz <= hi)
                if typ == "molotov":   # 20/10, his video: "il faut juste que la personne qui subisse ce stuff soit derrière la
                    # charrette": the one behind what it lands by (farther from you than its fire) first
                    dl = math.hypot(lx - me[0], ly - me[1])
                    near.sort(key=lambda t: (math.hypot(t[1][0] - me[0], t[1][1] - me[1]) < dl - 16, t[0]))
                for _, p, b in near[:2]:   # the closest: the ones it was for; where they were heading (their line)
                    hits.append(p)
                    if b and math.hypot(p[0] - b[0], p[1] - b[1]) > 40:
                        heads.append((p, math.degrees(math.atan2(p[1] - b[1], p[0] - b[0]))))
    look = [lx, ly, lz + (0 if typ == "flash" else 40)]
    out = []
    if len(hits) >= 2:
        for n, p in _cells(np.array(hits, float), cell=64):
            if all(math.dist(p, o["pos"]) > 200 for o in out):
                pp = [round(float(v), 1) for v in p]
                out.append({"pos": pp, "ang": _real_line(mp, foe, pp, heads) or _angle([pp[0], pp[1], pp[2] + 64], look)})
            if len(out) >= 2:
                break
        return out
    if typ == "molotov":   # in its fire, on its far side (behind what it flushes), turned to where it came from
        dx, dy = me[0] - lx, me[1] - ly
        d = math.hypot(dx, dy) or 1.0
        p = [round(lx - 32 * dx / d, 1), round(ly - 32 * dy / d, 1), round(lz, 1)]
        return [{"pos": p, "ang": _angle([p[0], p[1], p[2] + 64], [me[0], me[1], me[2] + 64])}]
    lo_z, hi_z = (-450, 100) if typ == "flash" else (-200, 200)   # a flash pops in the air: the ones under it
    ax, ay = lx - me[0], ly - me[1]
    an = math.hypot(ax, ay) or 1.0
    cone = {"smoke": 0.5, "flash": 0.0}.get(typ)

    def beyond(x, y):
        if cone is None:
            return True
        bx, by = x - lx, y - ly
        return (ax * bx + ay * by) / (an * (math.hypot(bx, by) or 1.0)) >= cone
    for x, y, z, n in _spots(mp)["CT" if team == 2 else "T"]:   # the most held first
        if math.hypot(x - lx, y - ly) <= reach and lo_z < z - lz < hi_z and beyond(x, y) and all(math.dist([x, y, z], o["pos"]) > 250 for o in out):
            out.append({"pos": [x, y, z], "ang": _real_line(mp, foe, [x, y, z]) or _angle([x, y, z + 64], look)})
            if len(out) >= 2:
                break
    return out


def _my_setup(sid, mp):
    """Where you stand on each side of this map 15 to 30 s into your rounds (your demos: the spot you play, not where the
    round takes you: on Fachwerk you hold Apps, you end up on A), and the zones your enemies come from when you fight
    from those spots. -> ({side: Counter(zone)}, {side: Counter(enemy zone)})."""
    setup, faced = {"CT": Counter(), "T": Counter()}, {"CT": Counter(), "T": Counter()}
    duels = []
    for mid, _ in _my_matches(str(sid), mp):
        deep = os.path.join(config.OUT, "deep", mid)
        try:
            S = pd.read_parquet(os.path.join(deep, "samples.parquet"), columns=["steamid", "side", "round", "t", "zone"])
            D = pd.read_parquet(os.path.join(deep, "duels.parquet"), columns=["killer", "victim", "killer_side", "victim_side", "killer_zone", "victim_zone"])
        except Exception:
            continue
        S = S[(S.steamid.astype(str) == str(sid)) & (S.t >= 15) & (S.t <= 30)]
        for (_, side), g in S.groupby(["round", "side"]):
            z = g.zone.dropna().mode()
            if side in setup and len(z):
                setup[side][z.iloc[0]] += 1
        for who, en in (("killer", "victim"), ("victim", "killer")):
            d = D[D[who].astype(str) == str(sid)]
            duels += list(zip(d[f"{who}_side"], d[f"{who}_zone"], d[f"{en}_zone"]))
    for side, mz, ez in duels:
        if side in faced and mz in dict(setup[side].most_common(3)) and isinstance(ez, str):
            faced[side][ez] += 1
    return setup, faced


# from a spot, standing still when you click; a run-throw (W pressed as you release, a bind's way) leaves from it too
# (09/10: his "running molly" to Banana was told "standing still")
REPEATABLE = ("standing still", "jumpthrow", "crouching", "jumpthrow + crouching", "run-throw (W)", "W + jumpthrow",
              "run-throw (moving forward)", "forward + jumpthrow")


# 17/10, the user: "fais des tests bot guidés pour les stuff en respectant les consignes affichées pour voir si tout
# fonctionne": each lineup thrown on the training server by a bot as its words say (tools/train_selftest.py --guided),
# the ones it missed thrown every other way (tools/lineup_check.py). resources/lineups_checked.json keeps what came out:
# the way that lands (its words corrected) or none (the lineup left out). Matched on its spot and aim too: the lineup
# your demos make between the same places may be another one
CHECKED = os.path.join(config.HERE, "resources", "lineups_checked.json")
_CHK = None


def _checked(did, pos, ang):
    """The check of that lineup ({ok, how, click, ...}), or None when it was never thrown by the guided bot."""
    global _CHK
    if _CHK is None:
        _CHK = {}
        for x in (config.read_json(CHECKED, {}) or {}).get("lineups") or []:
            _CHK.setdefault(x["id"], []).append(x)
    for x in _CHK.get(did) or []:
        if all(abs(a - b) <= 16 for a, b in zip(x["pos"], pos)) and all(abs((a - b + 180) % 360 - 180) <= 1 for a, b in zip(x["ang"], ang)):
            return x
    return None


def _lands_for_you(it):
    """False when your throws of a lineup keep popping together far from its spot (07/10, the smoke to Sniper's Nest:
    three throws 600 u away, 70 u apart: the lineup is not what the demos say, not your hand)."""
    P = np.array((it or {}).get("pops") or [], float).reshape(-1, 2)
    tg = (it or {}).get("target")
    if len(P) < 2 or not tg:
        return True
    c = np.median(P, axis=0)
    together = float(np.median(np.linalg.norm(P - c, axis=1))) < 120
    return not (together and math.dist(c, tg[:2]) > 400)


_DUEL_PAIRS = {}


DUEL_COLS = ["killer_X", "killer_Y", "killer_Z", "victim_X", "victim_Y", "victim_Z"]


def _duel_pairs(mp):
    """The map's duels: (killer xyz, victim xyz), cached; read from one copy of the map's duels kept as one (22/10, his
    test video: Prepare's first answer after the app started read Dust2's 987 duels.parquet one by one on the hard disk;
    ledger.gathered takes in only the new or changed matches)."""
    if mp not in _DUEL_PAIRS:
        from wily.core import ledger
        stamps = ledger.folders(config.DEEP)
        items = [(d, os.path.join(config.DEEP, d, "duels.parquet"), stamps.get(d)) for d in _map_dirs(mp)]
        try:
            D = ledger.gathered(f"duel_pairs_{mp}", items, prep=lambda x, k: x.reindex(columns=DUEL_COLS))
        except Exception as e:
            print("duel pairs", mp, e, flush=True)
            D = pd.DataFrame(columns=DUEL_COLS)
        D = D.reindex(columns=DUEL_COLS).dropna()
        _DUEL_PAIRS[mp] = (D[DUEL_COLS[:3]].to_numpy(float), D[DUEL_COLS[3:]].to_numpy(float))
    return _DUEL_PAIRS[mp]


def _exposed(mp, spot, land, r=450, dz=220):
    """How many duels of the base had one player at a throw's spot and the other where it lands (r, dz around it): they
    see each other (07/10, the user: "je suis sur une ligne où la personne qui subit mon stuff peut me voir")."""
    K, V = _duel_pairs(mp)
    if not len(K):
        return 0
    def near(A, p, r, dz):
        return (np.hypot(A[:, 0] - p[0], A[:, 1] - p[1]) < r) & (np.abs(A[:, 2] - p[2]) < dz)
    return int((near(K, spot, 120, 90) & near(V, land, r, dz)).sum() + (near(V, spot, 120, 90) & near(K, land, r, dz)).sum())


def _works(typ, x, side):
    """A lineup that does something in the base's matches (09/10, his stuff drills: "il n'y a pas vraiment de joueurs qui
    jouent dans cette zone", "cette grenade ne sert à rien, la personne ne l'a pas subie"): a flash that blinds an enemy
    a quarter of the time, an HE that hurts someone 22% of the time for 6+ damage a throw, a molotov that burns someone
    8% of the time (a CT's early one, against a rush, is kept: it closes the way in time); a smoke always."""
    if typ == "flash":
        return (x.get("blind") or 0) >= 25
    if typ == "he":
        return (x.get("hit") or 0) >= 22 and (x.get("dmg") or 0) >= 6
    if typ == "molotov":
        early = side == "CT" and (x.get("usual") == "debut" or (x.get("t_med") or 99) <= 25)
        return early or (x.get("hit") or 0) >= 8
    return True


CLICK = {"left": "left click", "gauche": "left click", "right": "right click", "droit": "right click",
         "middle": "left + right click", "milieu": "left + right click", "both": "left + right click"}


_ND, _ND_LOCK, _ND_BUSY = {}, {}, set()


def _nd_stamp():
    """What the map's lineups are made from that can change any minute: your setups (!setup), the defenses and takes
    Wily found, the guided bot's checks (their files' times)."""
    from wily.training import setups
    fs = [setups._file()] + [os.path.join(config.HERE, "resources", f) for f in ("defenses.json", "takes.json", "victims_checked.json", "lineups_checked.json")]
    return tuple(os.path.getmtime(f) if os.path.exists(f) else 0.0 for f in fs)


def nade_drills(sid, mp):
    """The map's lineups (_nade_drills), the same ones for 5 min (20/10: Prepare's plan, its tiles and its site takes
    each made them again, at once): made once while the others wait for it, a copy each time (its callers change theirs).
    Older than 5 min: served as they are and made again behind (21/10: the first Prepare after 5 min waited 30 to 60 s
    for its site takes); made again at once when one of their files changed (a setup saved, a defense found)."""
    k = (str(sid), mp)
    stamp = _nd_stamp()
    with _ND_LOCK.setdefault(k, threading.Lock()):
        hit = _ND.get(k)
        if not hit or hit[2] != stamp:
            hit = _ND[k] = (time.time(), _nade_drills(sid, mp), stamp)
        elif time.time() - hit[0] > 300 and k not in _ND_BUSY:
            _ND_BUSY.add(k)
            threading.Thread(target=_nd_refresh, args=(k, sid, mp, stamp), daemon=True).start()
    return copy.deepcopy(hit[1])


def _nd_refresh(k, sid, mp, stamp):
    try:
        v = _nade_drills(sid, mp)
        with _ND_LOCK.setdefault(k, threading.Lock()):
            _ND[k] = (time.time(), v, stamp)
    except Exception as e:
        print("nade_drills", mp, e, flush=True)
    finally:
        _ND_BUSY.discard(k)


def prewarm(sid, n=3):
    """Prepare's answers made ahead for your most played maps (20/10, the user: "essaye d'accélérer la préparation des
    entraînements": the first one after the app started waited 15 to 30 s): each module's drills, the site takes, the
    Momentum parts. A match first: nothing then."""
    for mp in list(maps(sid))[:n]:
        if config.in_match():
            return
        try:
            module_counts(sid, mp)
            execs.offer(sid, mp)
            momentum_offer(sid, mp)
        except Exception as e:
            print("prewarm", mp, e, flush=True)


def _nade_drills(sid, mp):
    """The lineups for where you play: thrown from the spots you hold 15-30 s into your rounds, or landing where your
    enemies come from when you hold them (04/10: "I'm an Apps player, I don't play long: this smoke changes nothing for
    me"). Only throws you can repeat from a spot: standing, crouching or a jumpthrow (04/10: "you say running jump: it
    goes way too far": a running throw starts somewhere the demos don't tell)."""
    from wily.insights import nades
    S = (nades.summary().get("maps") or {}).get(mp) or {}
    setup, faced = _my_setup(sid, mp)
    based = set()
    for side, M in S.items():   # no match of yours on this map (09/10): the spots the base throws from most, onto its busiest places
        if isinstance(M, dict) and not setup.get(side):
            based.add(side)
            fk, tk = Counter(), Counter()
            for T in (M.get("types") or {}).values():
                for x in T.get("groups") or []:
                    fk[x["from_key"]] += int(x.get("n") or 0)
                    tk[x["to_key"]] += int(x.get("n") or 0)
            setup[side], faced[side] = fk, tk
    out, E = [], None
    for side, M in S.items():
        if not isinstance(M, dict) or not setup.get(side):
            continue
        team = 2 if side == "T" else 3
        su, fa = setup[side], faced[side]
        top, n_su = dict(su.most_common(3)), sum(su.values())
        hot, n_fa = dict(fa.most_common(5)), sum(fa.values()) or 1
        cands, died_ok = [], {}
        for typ, T in (M.get("types") or {}).items():
            gs = T.get("groups") or []
            dd = [g["died"] for g in gs if g.get("died") is not None]
            died_cap = max(15.0, 2.0 * float(np.median(dd))) if dd else None   # the base: median 6%, 90% of the lineups under 15%
            for x in gs:
                if (x.get("how") or "standing still") not in REPEATABLE or not _works(typ, x, side):
                    continue
                if died_cap is not None and x.get("died") is not None and x["died"] >= died_cap:
                    continue   # its thrower dies after it far more often than the others: thrown where they see you
                died_ok[id(x)] = died_cap is not None and x.get("died") is not None
                rel = top.get(x["from_key"], 0) / n_su + 0.5 * hot.get(x["to_key"], 0) / n_fa
                if rel > 0:
                    cands.append((rel * (0.5 + float(x.get("score") or 0)), rel, typ, x))
        items = (progress().get("items") or {})
        n0 = len(out)
        for w, rel, typ, x in sorted(cands, key=lambda c: -c[0]):   # the 16 best kept once the bad ones are out (19/10)
            if len(out) - n0 >= 16:
                break
            sp = (x.get("setpos") or "").replace(";", " ").split()
            try:
                pos = [float(v) for v in sp[1:4]]
                ang = [float(sp[5]), float(sp[6])]
            except (IndexError, ValueError):
                continue
            did = f"nade:{mp}:{side}:{typ}:{x['from_key']}>{x['to_key']}"
            if not _lands_for_you(items.get(did)):
                continue
            alt_how = None
            if not spot_walls(mp, pos)["ok"]:   # no wall, no corner to find its spot by: the base's same lineup from one, else none
                l0 = _land(mp, typ, pos, ang) or (_world(mp, *x["to_px"]) if x.get("to_px") else None)
                alt = _findable_spot(mp, typ, side, x["from_key"], l0) if l0 else None
                if not alt:
                    continue
                pos, ang, alt_how = alt
            chk = _checked(did, pos, ang)
            if chk and not chk.get("ok"):
                continue   # the guided bot found no way of throwing it that lands
            land0 = _land(mp, typ, pos, ang) or _world(mp, *x["to_px"]) if x.get("to_px") else None
            l3 = (land0 if len(land0) >= 3 else [land0[0], land0[1], pos[2]]) if land0 and len(land0) >= 2 else None
            if l3 and typ != "flash" and _exposed(mp, pos, l3, 150, 120) >= 10:
                continue   # 19/10, his 17/10 video: "j'envoie le stuff à un endroit que je vois déjà ... si quelqu'un a déjà la
                # ligne je suis mort": the base's duels between this spot and the very place it lands (150 u around it: the
                # 450 u below took in half the map; Fachwerk's smoke to A site 13, the molotov he liked on Long A 4)
            if l3 and not died_ok.get(id(x)) and _exposed(mp, pos, l3) >= 3:
                continue   # 07/10: "je suis visible de là où j'envoie la grenade ... tu peux me faire tuer alors que je suis en train de stuff"
            if typ != "flash" and (x["from_key"] == x["to_key"] or (land0 and len(land0) >= 2 and math.hypot(land0[0] - pos[0], land0[1] - pos[1]) < 500)):
                continue   # 10/10, a Molotov → T Main from T Main's exit: "je suis vraiment au contact de la zone que je dois molo ... ça sert à rien d'envoyer ce stuff"
            item =NADE_ITEM[typ][team] if typ == "molotov" else NADE_ITEM.get(typ)
            if not item or not x.get("to_px"):
                continue
            name = {"smoke": i18n.tr("Smoke"), "flash": i18n.tr("Flash"), "he": "HE", "molotov": i18n.tr("Molotov")}[typ]
            land = _land(mp, typ, pos, ang) or _world(mp, *x["to_px"])
            if _thrower_sees(mp, typ, pos, land):
                continue
            mine = x["from_key"] in top
            if side in based:   # the base's spots, not yours
                why = i18n.tr("from {zone}, a spot the base throws it from", zone=x['from']) if mine else i18n.tr("onto {zone}, where they come from", zone=x['to'])
            else:
                why = i18n.tr("from {zone}, your spot", zone=x['from']) if mine else i18n.tr("onto {zone}, where they come at you from your spot", zone=x['to'])
            out.append({"id": did, "kind": "nade", "map": mp,
                        "title": f"{name} → {x['to']}", "tip": f"{why} · {x.get('timer') or ''}".strip(" ·"),
                        "team": team, "type": typ, "item": item, "how": (chk or {}).get("how") or alt_how or config.key_free(x.get("how")) or "standing still",
                        # 09/10, his HE to Mini, told "left click": "c'est pas que du left click, c'est du left et right
                        # click". The demos hold the buttons for almost no throw (CS2's don't record them: 154 of 1,028,672
                        # in the base): the click only when it is known, never a "left click" by default
                        "click": (chk or {}).get("click") or CLICK.get(x.get("click") or "", ""),
                        "me": {"pos": pos, "ang": ang}, "target": land, "victims": [], "_vic": [side, x.get("t_med")],
                        "clock": round(max(10.0, 115 - float(x.get("t_med") or 0) + 3), 1) if x.get("t_med") else 0,
                        "weight": 1 + 10 * w})
            # a CT's early smoke or molotov: thrown against a real rush, in its timing (06/10, the user: "quand c'est une
            # smoke de timing j'aimerais bien avoir la smoke dans le timing")
            if RUSH_ON and side == "CT" and typ in ("smoke", "molotov") and (x.get("usual") == "debut" or (x.get("t_med") or 99) <= 25):
                try:
                    if E is None:
                        E = _early(mp)
                    R = _rush(mp, land, float(x.get("flight_s") or 2.5), max(0.0, float(x.get("t_med") or 10) - 3), E)
                except Exception as e:
                    print("rush", mp, x.get("to"), e, flush=True)
                    R = None
                if R and not _rush_hits(typ, land, R["tracks"]):
                    R = None   # its fire or its cloud above or below the way they run (21/10, Dust2: a molotov 137 u above Top Mid's rushers, a smoke on the tunnel's roof)
                if R:
                    at = max(0.0, 115 - R["at"])
                    out[-1].update(tracks=R["tracks"], step=RUSH_STEP, clock=R["clock"], rush_at=R["at"], weight=out[-1]["weight"] * 1.5,
                                   title=i18n.tr("ANTI-RUSH {nade} → {zone}", nade=name, zone=x['to']),
                                   tip=f"{why} · " + i18n.tr("a real rush gets there at {t}: up before it", t=f"{int(at // 60)}:{int(at % 60):02d}"))
    return out


# 22/10, his test video (16:19): "sincèrement, pour l'instant fais disparaître toutes les parties anti-rush, il n'y a pas
# vraiment de plus-value ... si je ne te dis pas l'inverse, fais disparaître les parties anti-rush": no anti-rush drill
RUSH_ON = False
RUSH_HIT = {"molotov": (150.0, 48.0), "smoke": (144.0, 110.0)}   # its fire's reach on their floor; its cloud's radius and height


def _rush_hits(typ, land, tracks):
    """One of the rushers runs through what it does: a molotov's fire on the floor they run on, a smoke's cloud around the
    way they come (21/10, Dust2's anti-rush: the base's place is where it landed, not always where they pass)."""
    if not land or len(land) < 3 or typ not in RUSH_HIT:
        return True
    r, dz = RUSH_HIT[typ]
    for tr in tracks:
        P = np.asarray(tr.get("path") or [], float).reshape(-1, 5)
        near = P[np.hypot(P[:, 0] - land[0], P[:, 1] - land[1]) <= r]
        if len(near) and float(np.abs(near[:, 2] - land[2]).min()) <= dz:
            return True
    return False


EARLY_D = os.path.join(config.OUT, "train_early")
RUSH_R, RUSH_DZ, RUSH_STEP, RUSH_LEAD = 240.0, 140.0, 32, 7.0   # the spot reached: 240 u, same floor; samples every 0.5 s
STEP_Z = 18.0   # CS2's step height: a sample higher than both its neighbours by more is a jump


def _early(mp, demos=250):
    """The Ts' positions in the first 40 s of the base's rounds on a map (the demos' samples, every 0.5 s): when a rush is
    where. Cached per map (out/train_early), made again when the base has a quarter more matches."""
    os.makedirs(EARLY_D, exist_ok=True)
    f, meta = os.path.join(EARLY_D, f"{mp}.parquet"), os.path.join(EARLY_D, f"{mp}.json")
    dirs = _map_dirs(mp)[-demos:]
    try:
        with open(meta, encoding="utf-8") as fh:
            if json.load(fh).get("n", 0) >= 0.8 * len(dirs):
                return pd.read_parquet(f)
    except (OSError, ValueError):
        pass
    parts = []
    for i, d in enumerate(dirs):
        try:
            S = pd.read_parquet(os.path.join(config.OUT, "deep", d, "samples.parquet"), columns=["steamid", "side", "round", "t", "X", "Y", "Z", "zone"])
        except Exception:
            continue
        S = S[(S.side == "T") & (S.t <= 40)]
        if len(S):
            parts.append(pd.DataFrame({"d": np.int16(i), "round": S["round"].astype(np.int16), "sid": S.steamid.astype(str),
                                       "t": S.t.astype(np.float32), "X": S.X.astype(np.float32), "Y": S.Y.astype(np.float32),
                                       "Z": S.Z.astype(np.float32), "zone": S.zone.astype(str)}))
    E = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["d", "round", "sid", "t", "X", "Y", "Z", "zone"])
    E["sid"] = E.sid.astype("category")
    E["zone"] = E.zone.astype("category")
    E.to_parquet(f)
    with open(meta, "w", encoding="utf-8") as fh:
        json.dump({"n": len(dirs), "rows": len(E)}, fh)
    return E


def _rush(mp, land, flight, ready=0.0, E=None, q=(0.0, 0.2), after=4.0):
    """A real rush through a grenade's spot (06/10, the user on a CT smoke: "une smoke anti rush: j'aimerais avoir la
    situation du mec qui rush et qui se prend cette smoke, pour avoir la smoke dans le timing"): of the base's Ts who
    reach that spot in the first 40 s after a CT can have it up there (ready: when the CTs usually get to the throw, plus
    the flight), the fastest fifth are the rushes; their round with the most Ts through it within 4 s gives the runners.
    GO when the CT gets to the spot, or 7 s before the last moment to throw when the rush is slower.
    q: the share of them by how fast they got there (a site defense, 21/10: the typical takes, 0.4 to 0.6: the fastest
    fifth asked one defender for four grenades from four corners in two seconds). after: how long each one's way goes on
    past the spot (a defense: on to the site, its later grenades on their way).
    -> {"tracks": [{zone, path, arrive}], "clock": the clock at GO, "at": the round's time the first one gets there}"""
    if not land or len(land) < 3:
        return None
    E = _early(mp) if E is None else E
    if not len(E):
        return None
    m = (np.hypot(E.X.to_numpy() - land[0], E.Y.to_numpy() - land[1]) < RUSH_R) & (np.abs(E.Z.to_numpy() - land[2]) < RUSH_DZ)
    A = E[m].groupby(["d", "round", "sid"], observed=True).t.min().reset_index()
    A = A[A.t >= max(6.0, ready + flight + 2.5)]   # a rush the grenade can stop: drawn (it comes at GO), thrown, up (not a T whose spawn is next to it)
    if len(A) < 10:
        return None
    fast = A[(A.t >= A.t.quantile(q[0])) & (A.t <= A.t.quantile(q[1]))]
    cands = []
    for (d, r), g in fast.groupby(["d", "round"]):
        g = g.sort_values("t")
        k = int((g.t <= g.t.iloc[0] + 4).sum())
        cands.append((k, float(g.t.iloc[0]), d, r, g[g.t <= g.t.iloc[0] + 4]))
    cands.sort(key=lambda c: (-c[0], c[1]))
    # the round with the most Ts through it within 4 s whose runners a bot can replay all of (22/10: its jumpers left out,
    # Dust2's CT A hold went from 6 Ts to 2): the next one when a round loses some, the fullest found at most 30 rounds in
    best = None
    for k, t_arr, d, r, who in cands[:30]:
        t_go = max(0.0, round(max(ready, t_arr - flight - RUSH_LEAD) * 2) / 2)
        tracks = _rush_tracks(mp, E, d, r, who, t_go, after)
        if best is None or len(tracks) > len(best[2]):
            best = (t_arr, t_go, tracks)
        if len(tracks) >= min(k, 4):
            break
    if not best or not best[2]:
        return None
    t_arr, t_go, tracks = best
    return {"tracks": tracks[:4], "clock": round(115 - t_go, 1), "at": round(t_arr, 1)}


def _rush_tracks(mp, E, d, r, who, t_go, after):
    """The ways of a round's runners from GO to after their spot, each one a bot can walk (no gap, no jump)."""
    tracks = []
    for sid_, ta in zip(who.sid, who.t):
        g = E[(E.d == d) & (E["round"] == r) & (E.sid == sid_) & (E.t >= t_go - 0.01) & (E.t <= ta + after)].sort_values("t")
        if len(g) < 4 or abs(float(g.t.iloc[0]) - t_go) > 0.01 or (np.diff(g.t.to_numpy()) > 0.51).any():
            continue   # a gap in its samples: not walked
        P = g[["X", "Y", "Z"]].to_numpy(float)
        if len(P) > 2 and float((P[1:-1, 2] - np.maximum(P[:-2, 2], P[2:, 2])).max()) > STEP_Z:
            continue   # a jump on its way (a bot can't jump: 22/10, Dust2's anti-rush, a rusher put back on his way where he jumped)
        path, yaw = [], 0.0
        for i in range(len(P)):
            if i + 1 < len(P) and math.hypot(P[i + 1][0] - P[i][0], P[i + 1][1] - P[i][1]) > 4:
                yaw = math.degrees(math.atan2(P[i + 1][1] - P[i][1], P[i + 1][0] - P[i][0]))   # facing the way it runs
            path += [round(P[i][0], 1), round(P[i][1], 1), round(P[i][2], 1), round(yaw, 1), 0.0]
        z0 = str(g.zone.iloc[0])
        tracks.append({"zone": replay_zone(z0, mp) if z0 and z0 != "nan" else "rush", "path": path, "arrive": round(float(ta) - t_go, 1)})
    return tracks


def clip_drills(sid, mp):
    """The lineups of the clips you sent (clips.py, 07/10: "Essaye de récupérer ces stuffs"): a clip's grenades one after
    the other from its exact spot, at the clip's moment of the round. Weighed well above the base's: you asked for them."""
    from wily.insights import clips
    out = []
    for c in clips.load(mp):
        team = 2 if c["side"] == "T" else 3
        n = len(c["throws"])
        for i, x in enumerate(c["throws"]):
            typ = x["type"]
            item = NADE_ITEM[typ][team] if typ == "molotov" else NADE_ITEM.get(typ)
            if not item or not x.get("pos") or not x.get("land"):
                continue
            chk = _checked(f"clip:{c['id']}:{i}", x["pos"], x["ang"])
            if chk and not chk.get("ok"):
                continue   # the guided bot found no way of throwing it that lands
            name = {"smoke": i18n.tr("Smoke"), "flash": i18n.tr("Flash"), "he": "HE", "molotov": i18n.tr("Molotov")}[typ]
            seen = i18n.tr("{n} throws in the base, {p} by pros", n=x['uses'], p=x['pro_uses']) if x.get("uses") else i18n.tr("not in the base yet")
            out.append({"id": f"clip:{c['id']}:{i}", "kind": "nade", "map": mp, "clip": c["id"], "step": i,
                        "title": f"{name} → {x['to']}" + (f" ({i + 1}/{n})" if n > 1 else ""),
                        "tip": f"{i18n.tr(c['title'])} · " + i18n.tr("@{handle}'s clip", handle=c['handle']) + f" · {seen}",
                        "team": team, "type": typ, "item": item, "how": (chk or {}).get("how") or config.key_free(x.get("how")) or "standing still",
                        "click": (chk or {}).get("click") or x.get("click") or "left click",
                        "me": {"pos": x["pos"], "ang": x["ang"]}, "target": x["land"], "victims": [], "_vic": [c["side"], x.get("t")],
                        "clock": round(max(10.0, 115 - float(x["t"]) + 3), 1) if x.get("t") is not None else 0,
                        "weight": 25})
    from wily.training import setups
    try:   # your own setups, saved on the training server with !keep and !setup (19/10): like a clip, whole and in order
        out += setups.drills(mp)
    except Exception as e:
        print("setups", mp, e, flush=True)
    return out


def _setups_of(mp, drills):
    """The base's lineups that go together as setups (setups.compose, 19/10): tagged so a block comes whole."""
    from wily.training import setups
    try:
        return setups.compose(mp, drills)
    except Exception as e:
        print("setups", mp, e, flush=True)
        return drills


def _whole_clips(picked, cands):
    """A clip's grenades go together, in its order: one of them picked brings the others (ZywOo's smoke without its
    molotov and flash is not his execute)."""
    out, done = [], set()
    for d in picked:
        cl = d.get("clip")
        if not cl:
            out.append(d)
        elif cl not in done:
            done.add(cl)
            out += sorted([c for c in cands if c.get("clip") == cl], key=lambda c: c.get("step", 0))
    return out


# ---------------------------------------------------------------- where you struggle lately (06/10)

KIND_EN = {"exec": i18n.N_("executes"), "rush": i18n.N_("rushes"), "hit": i18n.N_("hits")}
_STRUG = {"t": 0, "sid": None, "v": []}


def struggles(sid, n=20):
    """Where you lose rounds lately (06/10, the user: "la game d'Overpass entre le 4 et le 5 où on s'est pris des execs B
    en CT: si tu vois des situations comme ça où je galère, priorise-les en entraînement"): your last matches' rounds by
    map, side, site and how the Ts came (an execute: three Ts or more on the site after 0:30; a rush: before), the
    recent ones weighing more (a week old: half). A situation counts when you lost most of its rounds, twice at least.
    -> [{map, side, site, kind, lost, n, score, rounds: [[mid, round], ...], last}] the worst first"""
    from wily.insights import tside
    sid = str(sid)
    if _STRUG["sid"] == sid and time.time() - _STRUG["t"] < 600:
        return _STRUG["v"]
    try:
        reg = json.load(open(os.path.join(config.CACHE, "matches.json"), encoding="utf-8"))
    except (OSError, ValueError):
        reg = {}
    acc = {}
    for mid, mp in replay._own_matches(sid, n):
        f = os.path.join(tside.OUT, mid + ".parquet")
        lf = os.path.join(config.OUT, "deep", mid, "loadout.parquet")
        if not mp or not os.path.exists(f) or not os.path.exists(lf):
            continue
        try:
            R = pd.read_parquet(f, columns=["round", "site", "hit_t", "n_exec", "T_won"])
            L = pd.read_parquet(lf, columns=["round", "steamid", "side"])
        except Exception:
            continue
        me = L[L.steamid.astype(str) == sid].set_index("round").side
        when = (reg.get(mid) or {}).get("time")
        try:
            t = time.mktime(time.strptime(when[:16], "%Y-%m-%dT%H:%M")) if when else None
        except ValueError:
            t = None
        w = 0.5 ** (max(0.0, time.time() - t) / 86400 / 7) if t else 0.5
        for r in R.itertuples():
            side = me.get(r.round)
            if side not in ("T", "CT") or r.site not in ("A", "B") or r.hit_t != r.hit_t:
                continue
            kind = "rush" if r.hit_t < 30 else "exec" if (r.n_exec or 0) >= 3 else "hit"
            lost = bool(r.T_won) if side == "CT" else not bool(r.T_won)
            e = acc.setdefault((mp, side, r.site, kind), {"lost": 0, "n": 0, "w": 0.0, "rounds": [], "last": 0})
            e["n"] += 1
            if lost:
                e["lost"] += 1
                e["w"] += w
                e["rounds"].append([mid, int(r.round)])
                e["last"] = max(e["last"], t or 0)
    out = []
    for (mp, side, site, kind), e in acc.items():
        if e["lost"] >= 2 and e["lost"] / e["n"] >= 0.55:
            out.append({"map": mp, "side": side, "site": site, "kind": kind, "lost": e["lost"], "n": e["n"],
                        "score": round(e["w"] * e["lost"] / e["n"], 3), "rounds": e["rounds"],
                        "last": i18n.day_month(e["last"]) if e["last"] else None,
                        "text": i18n.tr("{side} on {site}: {a} of {b} rounds lost to {kind}", side=side, site=site, a=e['lost'], b=e['n'], kind=i18n.tr(KIND_EN[kind])) if side == "CT"
                                else i18n.tr("T on {site}: {a} of {b} {kind} lost", site=site, a=e['lost'], b=e['n'], kind=i18n.tr(KIND_EN[kind]))})
    out.sort(key=lambda x: -x["score"])
    _STRUG.update(t=time.time(), sid=sid, v=out)
    return out


def _boost(S, mp, side, site):
    """How much a drill on that map, side and site is pushed (1: not at all, up to 4): your recent struggles there."""
    top = max((x["score"] for x in S), default=0) or 1
    sc = sum(x["score"] for x in S if x["map"] == mp and x["side"] == side and x["site"] == site)
    return 1 + 3 * min(1.0, sc / top)


# ---------------------------------------------------------------- wallbangs (06/10: "practice des lineups de wallbang" in long sessions)

WB_WEAPON = {"ak47": "weapon_ak47", "m4a1_silencer": "weapon_m4a1_silencer", "m4a1": "weapon_m4a1", "awp": "weapon_awp", "ssg08": "weapon_ssg08",
             "deagle": "weapon_deagle", "galilar": "weapon_galilar", "famas": "weapon_famas", "aug": "weapon_aug", "sg556": "weapon_sg556"}


def wallbang_drills(sid, mp):
    """The map's wallbangs (wallbangs.py: the base's kills through walls from one spot onto one place): you on the
    spot, the bots where the victims stood behind the wall, the weapon most of those kills were made with."""
    # 30/10, his review: "les wallbangs, ça va être comme les momentum ... on va les désactiver pour l'instant, et puis je
    # les rentrerai à la main plus tard": none offered (the boosts stay), COACH_SHOW_HIDDEN=1 brings them back
    if not os.environ.get("COACH_SHOW_HIDDEN"):
        return []
    from wily.insights import wallbangs
    out = []
    for w in wallbangs.load(mp)[:10]:
        ws = w.get("weapons") or {}
        if ws and max(ws.values()) < 50:   # 07/10, Mid → Kaffee "c'est nul comme wallbang": 3 kills by an AK, a Negev and a shotgun, sprays
            continue
        team = 2 if w["side"] == "T" else 3
        wp = next((WB_WEAPON[k] for k in (w.get("weapons") or {}) if k in WB_WEAPON), RIFLE[team])
        name = {v: k for k, v in WB_WEAPON.items()}.get(wp, "rifle").replace("_silencer", "-S").upper()
        vic = [v for v in w.get("victims") or []][:3]
        if not vic:
            continue
        out.append({"id": f"wallbang:{mp}:{w['side']}:{w.get('from_key')}>{w.get('to_key')}", "kind": "aim", "map": mp,
                    "title": i18n.tr("WALLBANG {from} → {to}", **{"from": w['from']}, to=w['to']) + f" ({w['side']}{', ' + i18n.tr('AWP line') if wp in ('weapon_awp', 'weapon_ssg08') else ''})",
                    "tip": i18n.tr("through the wall with the {weapon}: {n} kills from here in my base, {p}% through the wall · they stand still behind it, they don't shoot · a few bullets where they stand",
                                   weapon=name, n=w['n'], p=round(100 * w.get('wall', 1))),
                    "team": team, "me": {"pos": w["pos"], "ang": _angle(w["pos"], vic[0])}, "weapons": ["weapon_knife", wp],
                    "bot_weapons": ["weapon_knife", RIFLE[5 - team]],
                    "bots": [{"pos": v, "ang": _angle(v, w["pos"]), "zone": replay_zone(w.get("to_key") or "", mp)} for v in vic],
                    "weight": 1 + w["n"] / 5})
    return out


def _on_floor(mp, p):
    """A target's feet on the floor under or over it (26/10, Mirage's Short boost: its target 6 u under the mesh's floor,
    gone from its very start, never in sight): the mesh's height there when it is within 18 u."""
    try:
        from wily.training import navmesh
        q = navmesh.nearest(mp, p)
    except Exception:
        q = None
    if q and math.hypot(q[0] - p[0], q[1] - p[1]) < 4 and abs(q[2] - p[2]) <= 18:
        return [p[0], p[1], round(float(q[2]), 1)]
    return p


def boost_drills(sid, mp, raw=False):
    """The map's boosts that kill (boosts.py, 06/10, the user: "sur Nuke il y a très peu de wallbangs, par contre il y a
    des boosts, et ça c'est intéressant", "des moves de boost pour être au-dessus des smokes"): you on the teammate's
    head where the base's players stood (a bot below, crouched when they boosted on a crouched one), still targets where
    the players killed from up there stood; the ones that killed most first."""
    from wily.insights import boosts
    out = []
    for b in boosts.load(mp):
        if b["kills"] < 2 or not b.get("victims") or not real_boost(mp, b):
            continue
        team = 2 if b["side"] == "T" else 3
        (top, duck), base = boost_top(b), b["base"]
        wp = next((WB_WEAPON[k] for k in (b.get("weapons") or {}) if k in WB_WEAPON), RIFLE[team])
        out.append({"id": f"boost:{mp}:{b['side']}:{round(top[0])}:{round(top[1])}", "kind": "aim", "map": mp,
                    "title": i18n.tr("BOOST {place}", place=b['place']) + f" ({b['side']})",
                    "tip": i18n.tr("on a teammate's head: {n}× in my base, {k} kills from up there for {d} deaths · they stand still where those players stood", n=b['n'], k=b['kills'], d=b['deaths']),
                    "team": team, "me": {"pos": top, "ang": [b.get("pitch") or 0, b.get("yaw") or 0]},
                    "mate": {"pos": base, "ang": [0, b.get("yaw") or 0], "zone": "your boost", "duck": duck},
                    "weapons": ["weapon_knife", wp], "bot_weapons": ["weapon_knife", RIFLE[5 - team]],
                    "bots": [{"pos": _on_floor(mp, v), "ang": _angle(v, top), "zone": b["victim_places"][0] if b.get("victim_places") else b["place"]} for v in b["victims"][:3]],
                    "clock": round(max(10.0, 115 - float(b["t_med"]) + 3), 1) if b.get("t_med") is not None else 0,
                    "weight": 1 + b["kills"] / 3})
    # one boost a spot (22/10 report and 24/10 real test, Dust2's Top Mid: three of the base's boosts on the same top, three
    # drills of one id that met in its checks): the one that killed most
    seen, one = set(), []
    for d in sorted(out, key=lambda d: -d["weight"]):
        if d["id"] not in seen:
            seen.add(d["id"])
            one.append(d)
    return one if raw else [d for d in (_boost_seen(mp, d) for d in one) if d]


def _boost_seen(mp, d):
    """A boost as tools/boost_check.py found it on the server (24/10, the real test of Mirage's Short boost: up on the
    crouched teammate, a wall 45 u in front of the eyes, neither target in sight): its targets you see from up there, on
    the teammate that shows the most (a standing one 18 u higher), none: no boost. Not checked yet: as it is."""
    key = f"{mp}|{round(d['me']['pos'][0])}|{round(d['me']['pos'][1])}|{round(d['me']['pos'][2])}"
    # a boost no try ever got a kill from, taken off by hand with why (03/11, his rule: no forced content; kept apart from
    # boost_check's book, which a new check writes over)
    if key in (config.read_json(os.path.join(config.HERE, "resources", "boost_withdrawn.json"), {}) or {}):
        return None
    rec = (config.read_json(os.path.join(config.HERE, "resources", "boost_checked.json"), {}) or {}).get(key)
    if not rec or len(rec.get("crouched") or []) != len(d["bots"]):
        return d
    # 27/10 it took a standing one whenever it showed as many (the plugin's on-ground flag: up on a crouched teammate you were
    # off the ground for the game, every shot with the air's spread, AWP shots 100-200 u off at 1134 u on Anubis's B Main;
    # on a standing one, Mirage's Short, within 16 u at 973 u)
    # 28/10: the base's own way when it shows any (lab 5: that on-ground flag was the plugin's placement, dropped on the
    # teammate while it crouched under you; put on it once crouched you are on the ground. Raised 18 u onto a standing one,
    # Dust2's Top Mid boost had your head in the arch over it, stuck there at every height)
    own = "crouched" if d["mate"].get("duck") else "standing"
    other = "standing" if own == "crouched" else "crouched"
    way = own if sum(rec.get(own) or []) else other
    bots = [b for b, ok in zip(d["bots"], rec[way]) if ok]
    if not bots:
        return None
    if way == "standing" and d["mate"].get("duck"):
        top = d["me"]["pos"]
        d = dict(d, me=dict(d["me"], pos=[top[0], top[1], round(top[2] + 18.0, 1)]), mate=dict(d["mate"], duck=False))
    elif way == "crouched" and not d["mate"].get("duck"):   # the base's on a standing one: 18 u lower on a crouched one (03/11)
        top = d["me"]["pos"]
        d = dict(d, me=dict(d["me"], pos=[top[0], top[1], round(top[2] - 18.0, 1)]), mate=dict(d["mate"], duck=True))
    return dict(d, bots=bots)


def situation_drills(sid, mp, all_sc=None):
    return [{"id": s["id"], "kind": "situation", "map": s["map"], "title": f"R{s['round']} · " + (
                i18n.tr("1v{n} clutch", n=s['vs']) if s["kind"] == "clutch" else i18n.tr("death")) + (f" · {replay_zone(s['zone'], mp)}" if s.get("zone") else ""),
             "tip": (i18n.tr("you died to {who} ({weapon})", who=s['by'], weapon=s.get('weapon')) if s.get("by") else i18n.tr("you lost it")) +
                    ("" if s["kind"] == "clutch" else (" · " + i18n.tr("first death") if s.get("opening") else "") + ("" if s.get("traded") else " · " + i18n.tr("not traded"))),
             "mid": s["mid"], "round": s["round"], "sk": s["kind"], "t": s["t"], "weight": s["score"]}
            for s in (all_sc if all_sc is not None else replay.scenarios(sid, n=40)) if s["map"] == mp
            # a clutch whose bomb leaves no time to make it, one where nobody came twice: not offered (02/11, his rules)
            and (s["kind"] != "clutch" or replay.clutch_time_ok(s["id"])) and s["id"] not in _withdrawn_now()]


_WD = {"at": 0.0, "ids": set()}


def _withdrawn_now():
    """replay.passive_withdrawn(), read again each 30 s at most (a session's build asks it for every situation)."""
    import time as _t
    if _t.time() - _WD["at"] > 30:
        _WD["ids"], _WD["at"] = replay.passive_withdrawn(), _t.time()
    return _WD["ids"]


# ---------------------------------------------------------------- the session

# your weapon for the session (20/10, the user: "il faudrait pouvoir choisir son arme (ak, m4a4, m4a1s, usp, glock,
# deagle, awp)"): Prepare's choice; none: the ones you play in your matches (_my_guns)
WEAPONS = {"ak47": "weapon_ak47", "m4a4": "weapon_m4a1", "m4a1s": "weapon_m4a1_silencer", "awp": "weapon_awp",
           "deagle": "weapon_deagle", "usp": "weapon_usp_silencer", "glock": "weapon_glock"}
PISTOLS = {"weapon_deagle", "weapon_usp_silencer", "weapon_glock", "weapon_hkp2000", "weapon_p250", "weapon_fiveseven", "weapon_tec9",
           "weapon_cz75a", "weapon_elite", "weapon_revolver"}
NADES = {"weapon_smokegrenade", "weapon_flashbang", "weapon_hegrenade", "weapon_molotov", "weapon_incgrenade", "weapon_decoy"}
ARMED = ("aim", "crossfire", "defend", "push", "momentum")   # the blocks fought with your gun (Stuff: grenades; Situations:
# your round's own loadout; Wallbang: the gun that goes through that wall)


def _swap(ws, w):
    """A drill's weapons with yours: a rifle or the AWP in the main one's place (a pistol round stays one), a pistol
    alone in place of both; the order kept (the last one is the one in your hands)."""
    main = lambda x: x not in PISTOLS and x != "weapon_knife" and x not in NADES
    if w in PISTOLS:
        out, put = [], False
        for x in ws:
            if x in PISTOLS or main(x):
                if not put:
                    out.append(w)
                    put = True
            else:
                out.append(x)
        return out
    return [w if main(x) else x for x in ws] if any(main(x) for x in ws) else ws


def _arm(blocks, key):
    w = WEAPONS.get(key)
    if not w:
        return
    for b in blocks:
        if b["kind"] in ARMED:
            for d in b["drills"]:
                if d.get("weapons"):
                    d["weapons"] = _swap(d["weapons"], w)


def build(sid, minutes=20, where="random", difficulty=2, focus=None, record=True, tag=None, exec_key=None, pick=None, weapon=None, seed=None, only=None,
          every=False):
    """The plan of a session: blocks of each map, drills picked (due first, then at random by importance), the
    situations' scenario files built. Written to the server's coach/sessions folder. focus: one module of FOCUS for
    the whole time, on the first map (a focus block), its drills again until the time is full. exec_key: a Stuff focus
    block's site take or defense instead of a time (19/10, execs.py): its lineups one by one, then all of them at once."""
    sid = str(sid)
    if seed is not None:   # 29/10, the tests' fixed set (his rule: 90 % on 3 runs of the same): the same picks each time
        random.seed(int(seed))
        np.random.seed(int(seed) % (2 ** 32))
    p = ingest()
    nsess = len(p["sessions"])
    mine = maps(sid)
    base = base_maps()
    if not mine and not any(m in base for m in str(where).split(",")):
        raise ValueError("no match with a demo yet")
    names = list(mine)
    try:
        S = struggles(sid)
    except Exception as e:
        print("struggles:", e, flush=True)
        S = []
    top = max((x["score"] for x in S), default=0) or 1
    hard = {m: min(1.0, sum(x["score"] for x in S if x["map"] == m) / top) for m in names}   # your struggles: their maps come up more
    picked_maps = [m for m in str(where).split(",") if m in mine or m in base]   # Prepare's maps (one to three), yours or the base's
    if picked_maps:
        chosen = picked_maps[:3]
    elif where == "mix":
        k = 1 if minutes < 15 else 2 if minutes < 30 else 3
        w = np.array([mine[m] * (1 + 2 * hard[m]) for m in names], float)
        chosen = list(np.random.choice(names, size=min(k, len(names)), replace=False, p=w / w.sum()))
    else:
        w = np.array([mine[m] * (1 + 2 * hard[m]) for m in names], float)
        chosen = [str(np.random.choice(names, p=w / w.sum()))]
    focus = focus if focus in FOCUS else None
    sc_all = replay.scenarios(sid, n=40)   # your situations to play again: their maps only get a situations part
    sit = {x["map"] for x in sc_all}
    warm = minutes <= WARMUP_MIN and not focus   # a quick warm-up before a game: no aim, one map (07/10), its defense, prefire and stuff
    first = lambda mp: next(("defend" if x["side"] == "CT" else "push" for x in S if x["map"] == mp), None)   # your weak side there first
    if focus:   # a focus block: that module only, on the first map
        chosen = chosen[:1]
        if not _has(chosen[0], focus, mine, sit):
            raise ValueError(i18n.tr("nothing of this module on this map yet"))
        aim_s, parts = (int(minutes * 60), []) if focus == "crossfire" else (0, [(chosen[0], [(focus, int(minutes * 60))])])
    else:
        aim_s, parts = parts_for(minutes, chosen, lambda mp, k: _has(mp, k, mine, sit), first)   # the preview's rule: what it shows is what you get
    plan_of = dict(parts)
    cf_from = list(chosen) if focus == "crossfire" else [mp for mp, _ in parts]   # Crossfire's map: the session's first with its data
    chosen = [mp for mp, _ in parts]   # a short warm-up keeps the first maps only
    all_sc = sc_all if any(k == "situation" for ps in plan_of.values() for k, _ in ps) else []
    blocks, todo = [], []
    if aim_s:   # the aim first, for all the maps' share (06/10); none in 5 min
        # 13/10, Crossfire replaces the aim map: real duels on the first map of the session that has them (it goes
        # first: no map change between the two); the aim map stays for a session whose maps have none yet
        cf_map = next((m for m in cf_from if (crossfire.load(m, build=False) or {}).get("spots")), None)
        cfd = crossfire.drills(sid, cf_map, aim_s, _my_guns(sid), RIFLE, p["items"], nsess) if cf_map else []
        if cfd:
            chosen = [cf_map] + [m for m in chosen if m != cf_map]
            blocks.append({"map": cf_map, "kind": "crossfire", "seconds": aim_s, "drills": cfd})
        else:
            blocks.append({"map": aim_map(), "kind": "aim", "seconds": aim_s, "drills": aim_range_drills(sid, aim_s)})
    for mp in chosen:
        secs_of = dict(plan_of.get(mp) or [])
        pr = practice_drills(sid, mp, difficulty) if {"defend", "push"} & set(secs_of) else []   # a focus block of another module: not built
        fns = {"defend": lambda s_, m_: [d for d in pr if d.get("mode") == "defend"],
               "push": lambda s_, m_: [d for d in pr if d.get("mode") == "prefire"], "nade": lambda s_, m_: _setups_of(m_, nade_drills(s_, m_)) + clip_drills(s_, m_),
               "wallbang": lambda s_, m_: wallbang_drills(s_, m_) + boost_drills(s_, m_), "situation": lambda s_, m_: situation_drills(s_, m_, all_sc),
               "momentum": lambda s_, m_: []}
        if not pr:   # no site's drills (a hostage map): the situations take the defense's and the prefire's time
            secs_of["situation"] = secs_of.get("situation", 0) + secs_of.pop("defend", 0) + secs_of.pop("push", 0)
        kinds = [(k, fns[k]) for k in ORDER if secs_of.get(k)]
        bad = {(m_, r_) for x in S if x["map"] == mp for m_, r_ in x["rounds"]}   # the rounds you struggled in
        spare = 0.0   # a part with nothing to train on this map gives its time to the next ones
        for kind, fn in kinds:
            secs = secs_of[kind] + spare
            if kind == "momentum":   # its own picks: the level's order, each variant's drills in a row, as many as its time holds
                mpick = pick if pick in momentum.PICKS else None   # 20/10: or a choice of Prepare's, each drill once
                md = momentum.drills(sid, mp, secs, _my_guns(sid), RIFLE, p["items"], nsess, pick=mpick)
                if md:
                    blocks.append({"map": mp, "kind": kind, "seconds": int(sum(d["seconds"] for d in md) * 1.5) if mpick else int(secs), "drills": md})
                spare = 0.0 if md else secs
                continue
            cands = fn(sid, mp)
            if only is not None:   # the recette (29/10): those drills, each once, none drawn
                cands = [c for c in cands if c.get("id") in only]
            ex = kind == "nade" and exec_key in execs.KEYS
            if ex:   # 19/10, his video: "à la place d'avoir 10 minutes, ici j'aurai exec A"
                cands, secs = execs.sequence(sid, mp, exec_key)   # the lineups as they are (not the composed setups' titles)
            if not cands:
                spare = secs
                continue
            spare = 0.0
            for c in cands:   # your struggles first: the defense of that site, its pushes, the rounds you lost there
                site = None
                if c.get("mode") in ("defend", "prefire"):
                    site = next((s_ for s_ in ("A", "B") if f"Bombsite{s_}" in c["id"] or f":{s_} " in c.get("title", "") or c.get("title", "").endswith(f" {s_}")), None)
                    if site is None:
                        site = next((s_ for s_ in ("A", "B") if f"DEFEND {s_}" in c.get("title", "") or f"PUSH {s_}" in c.get("title", "")), None)
                if site:
                    b = _boost(S, mp, "CT" if c.get("mode") == "defend" else "T", site)
                    if b > 1.05:
                        c["weight"] = c.get("weight", 1.0) * b
                        why = next((x for x in S if x["map"] == mp and x["site"] == site and x["side"] == ("CT" if c.get("mode") == "defend" else "T")), None)
                        if why:
                            c["tip"] = f"{c.get('tip', '')} · " + i18n.tr("priority: {why} lately", why=why['text'])
                            c["tip"] = c["tip"].strip(" ·")
                if kind == "situation" and (str(c.get("mid")), int(c.get("round") or 0)) in bad:
                    c["weight"] = c.get("weight", 1.0) * 3
            n = max(1, int(secs / EST[kind]) + 1)
            # every: the measure (29/10, his rule: a block validated only with every drill of its panel tested, 3 runs >= 90 %):
            # all of them, each once, its time as long as they need
            picked = list(cands) if ex or only is not None or every else _pick(cands, n, p["items"], nsess, weight=lambda c: c.get("weight", 1.0))
            if every:
                secs = max(secs, len(picked) * EST.get(kind, 60) * 2.6)   # a failed one is played again at once (29/10: the 6th never came)
            if kind == "nade" and not ex:
                picked = _whole_clips(picked, cands)
            drills = []
            for d in picked:
                if kind == "nade":   # guided, then the spot and how, then the spot only
                    d["level"] = min(2, (p["items"].get(d["id"]) or {}).get("box", 0))
                    for x in [d] + list(d.get("members") or []):   # its circle the throw's own, when measured (23/10)
                        tol = aim_tol(x)
                        if tol:
                            x["aim_tol"] = tol
                    side_, t_med = d.pop("_vic", [None, None])
                    try:   # a rush's runners are the ones it is for: no victims to show after
                        d["victims"] = [] if d.get("tracks") or d.get("mode") == "exec" else _victims(mp, d["team"], d["type"], d.get("target"), d["me"]["pos"], side_, t_med, see=d.pop("_see", None), avoid=exec_avoid(d, picked))
                    except Exception as e:
                        print("victims", d["id"], e, flush=True)
                if kind == "push":
                    _by_level(d, difficulty)
                if kind == "situation":   # its file is built below (the plugin waits for it if it comes to it first)
                    d["scenario"] = d["id"]
                    todo.append(d)
                d.pop("weight", None)
                drills.append(d)
            if focus and drills and not ex and only is None and not every:   # a focus block: its drills again until its time is full, each once before any twice,
                k0 = len(drills)   # three times at most (one wallbang 24 times is no training: the block is shorter)
                while len(drills) * EST[kind] < secs * 1.2 and len(drills) < k0 * FOCUS_REPEAT:
                    drills.append(copy.deepcopy(drills[len(drills) % k0]))
            if drills:
                blocks.append({"map": mp, "kind": kind, "seconds": int(secs), "drills": drills})
    if not blocks:
        raise ValueError(i18n.tr("nothing of this module on this map yet") if focus else "nothing to train on these maps yet")
    chosen = chosen or list(dict.fromkeys(b["map"] for b in blocks))   # a focus Crossfire on the aim map
    sid_ = f"{tag}_{time.strftime('%Y%m%d_%H%M%S')}" if tag else time.strftime("s%Y%m%d_%H%M%S")   # tag: a self-test's
    sess = {"id": sid_, "minutes": minutes, "where": where, "maps": chosen, "difficulty": int(difficulty),
            "level": level(p["xp"]), "warmup": warm, "focus": focus, "blocks": blocks}
    if exec_key:
        sess["exec"] = exec_key
    if seed is not None:   # the plugin's own draws too (waves, ways, rushers)
        sess["seed"] = int(seed)
    if weapon in WEAPONS:   # your weapon in every block fought with one
        _arm(blocks, weapon)
        sess["weapon"] = weapon
    os.makedirs(SESS, exist_ok=True)
    replay.write_ui()   # the server's words in the app's language, read with the session (13/10)
    first = [d for d in blocks[0]["drills"] if blocks[0]["kind"] == "situation"][:1]
    for d in first:   # a session that starts with a situation: that one now
        _scenario(sid, d)
    json.dump(sess, open(os.path.join(SESS, f"{sid_}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    rest = [d for d in todo if d not in first]
    if rest:   # the others while you play the first blocks (demo parsing: about 2 s each), one after the other: two
        import threading   # demos parsed at once crashed a player's app in polars (08/10, replay.PARSE)
        threading.Thread(target=lambda: [_scenario(sid, d) for d in rest], daemon=True).start()
    if record:   # not a self-test's (tools/train_selftest.py): those never join your progress
        p["sessions"].append({"id": sid_, "t": time.time(), "minutes": minutes, "maps": chosen, "done": False, "difficulty": int(difficulty),
                              "focus": focus})
        _save(p)
    return sess


def _sit_maps(sid):
    """The maps of your situations to play again (your recent matches': a map you played long ago has none)."""
    try:
        return {x["map"] for x in replay.scenarios(str(sid), n=40)} if str(sid).isdigit() else set()
    except Exception as e:
        print("situations:", e, flush=True)
        return set()


def _why_not(mp, k, mine, sit=None):
    """Why that part has nothing on that map (None: it has): a hostage map has no site, a map of the base only no
    situation (they are your demos'), nor one without a recent match of yours (sit: _sit_maps), a map without a
    wallbang or a boost that kills none of those, nor Momentum one without the base's ways and jumps."""
    if k in ("defend", "push") and mp.startswith("cs_"):
        return i18n.tr("no bombsite on this map")
    if k == "situation" and mp != "random" and mp not in mine:
        return i18n.tr("needs your own matches on this map")
    if k == "situation" and mp != "random" and sit is not None and mp not in sit:
        return i18n.tr("none found on this map yet")
    if k == "momentum" and mp != "random" and not momentum.has(mp):   # its ways and jumps come with the base
        return i18n.tr("none found on this map yet")
    if k == "wallbang" and mp != "random":
        from wily.insights import boosts
        from wily.insights import wallbangs
        if not (wallbangs.load(mp) or any(x["kills"] >= 2 and real_boost(mp, x) for x in boosts.load(mp))):
            return i18n.tr("none found on this map yet")
    return None


def _has(mp, k, mine, sit=None):
    return _why_not(mp, k, mine, sit) is None


def modules(sid, mp):
    """Prepare's focus block on that map: each module, whether it has something there (and why not); Crossfire without
    its data there runs on the aim map."""
    sid = str(sid)
    mine = maps(sid) if sid.isdigit() else {}
    cf = mp != "random" and bool((crossfire.load(mp, build=False) or {}).get("spots"))
    sit = _sit_maps(sid)
    out = []
    for k in FOCUS:
        why = None if k == "crossfire" else _why_not(mp, k, mine, sit)
        out.append({"kind": k, "ok": why is None, "why": why,
                    "note": None if k != "crossfire" or cf else i18n.tr("on the aim map: no real duels of this map yet")})
    return out


COUNTS_F = os.path.join(config.OUT, "train_counts.json")
_COUNTS_LOCK = threading.Lock()


def momentum_offer(sid, mp):
    """Prepare's Momentum choices on that map (momentum.offer)."""
    return momentum.offer(sid, mp, _my_guns(sid), RIFLE)


def module_counts(sid, mp):
    """How many drills each module has on that map (Prepare's focus tiles), None where it can't be told; Crossfire's:
    its spots there (0: it runs on the aim map). The defense's, the prefire's, the stuff's and the wallbang's are kept a
    day on the disk (a map's first count builds its drills: 10 s to a minute while the PC works); Crossfire's and the
    situations' are read each time (a second), and Momentum's (its ways, jumps, stops and silent walks there)."""
    sid = str(sid)
    mine = maps(sid) if sid.isdigit() else {}

    def n(fn):
        try:
            return fn()
        except Exception as e:
            print("module count", mp, e, flush=True)
            return None
    key = f"{sid}:{mp}"
    with _COUNTS_LOCK:   # one count at a time: two tiles' requests never build the same drills twice
        disk = config.read_json(COUNTS_F, {}) or {}
        hit = disk.get(key)
        if not hit or time.time() - hit.get("t", 0) > 86400:
            pr = n(lambda: practice_drills(sid, mp) if _has(mp, "defend", mine) else []) or []
            hit = {"t": time.time(), "n": {"defend": sum(d.get("mode") == "defend" for d in pr), "push": sum(d.get("mode") == "prefire" for d in pr),
                                           "nade": n(lambda: len({d["id"] for d in nade_drills(sid, mp) + clip_drills(sid, mp)})),
                                           "wallbang": n(lambda: len(wallbang_drills(sid, mp) + boost_drills(sid, mp)))}}
            disk[key] = hit
            try:
                config.write_json(COUNTS_F, disk)
            except OSError as e:
                print("module counts:", e, flush=True)
    return {"crossfire": len((crossfire.load(mp, build=False) or {}).get("spots") or []), **hit["n"],
            "situation": n(lambda: len(situation_drills(sid, mp, replay.scenarios(sid, n=40))) if mp in mine else 0),
            "momentum": 0 if "momentum" in HIDDEN else n(lambda: momentum.count(mp))}


def preview(sid, minutes=20, where="random", focus=None):
    """What a warm-up will be, before it's built (Prepare shows it under its button): each part's minutes, map by map;
    a part without data on a map (no wallbang found there yet) gives its time to the next one. focus: a focus block,
    that module only on the first map ([] when it has nothing there)."""
    sid = str(sid)
    mine = maps(sid) if sid.isdigit() else {}
    base = base_maps()
    chosen = [m for m in str(where).split(",") if m in mine or m in base][:3] or [where if where in mine else "random"]
    sit = _sit_maps(sid)
    if focus in FOCUS:
        mp = chosen[0]
        if focus == "crossfire":
            cf = mp != "random" and (crossfire.load(mp, build=False) or {}).get("spots")
            return [{"map": mp if cf else aim_map(), "kind": "crossfire" if cf else "aim", "seconds": int(minutes * 60)}]
        return [{"map": mp, "kind": focus, "seconds": int(minutes * 60)}] if _has(mp, focus, mine, sit) else []
    has = lambda mp, k: _has(mp, k, mine, sit)   # noqa: E731
    try:
        S = struggles(sid) if sid.isdigit() else []
    except Exception:
        S = []
    first = lambda mp: next(("defend" if x["side"] == "CT" else "push" for x in S if x["map"] == mp), None)
    aim, parts = parts_for(minutes, chosen, has, first)
    out = []
    if aim:   # the aim first: Crossfire on the first map that has it (13/10), it then comes first; else the aim map (06/10)
        cf_map = next((mp for mp, _ in parts if mp != "random" and (crossfire.load(mp, build=False) or {}).get("spots")), None)
        if cf_map:
            parts = sorted(parts, key=lambda p: p[0] != cf_map)
        out.append({"map": cf_map or aim_map(), "kind": "crossfire" if cf_map else "aim", "seconds": aim})
    for mp, ps in parts:
        out += [{"map": mp, "kind": k, "seconds": secs} for k, secs in ps]
    return out


def _scenario(sid, d):
    try:
        replay.build(sid, d["mid"], d["round"], d["sk"], d.get("t"))
    except Exception as e:
        print("situation", d["id"], repr(e), flush=True)


def suggest(sid, p=None):
    """What the page preselects (04/10: "the bots' level from my level in training", "a 5 min warm-up when I know my
    stuff or I just played"): the bots' level from your last two sessions (85 % of the drills or more: one up; half or
    less: one down; else the same), the warm-up when your last match ended under two hours ago or you master most of
    your lineups."""
    p = p or progress()
    done = [x for x in p["sessions"] if x.get("done") and x.get("drills")][-2:]
    last = next((x for x in reversed(p["sessions"]) if x.get("difficulty") is not None), None)
    d = int(last["difficulty"]) if last else None
    if d is None and done:   # sessions before 04/10: the level is in their file
        try:
            with open(os.path.join(SESS, f"{done[-1]['id']}.json"), encoding="utf-8") as fh:
                d = int(json.load(fh).get("difficulty", 2))
        except (OSError, ValueError):
            d = None
    rate = sum(x.get("ok", 0) for x in done) / max(1, sum(x.get("drills", 0) for x in done)) if done else None
    diff, why = (2 if d is None else d), i18n.tr("your last level")
    if d is not None and rate is not None and rate >= 0.85 and d < 3:
        diff, why = d + 1, i18n.tr("{p} % of your last drills ✔: one level up", p=round(100 * rate))
    elif d is not None and rate is not None and rate <= 0.5 and d > 0:
        diff, why = d - 1, i18n.tr("{p} % of your last drills ✔: one level down", p=round(100 * rate))
    warm, wwhy = False, ""
    try:   # your last match: the match list (start + length), you among its players
        acc = int(sid) - 76561197960265728
        with open(os.path.join(config.CACHE, "matches.json"), encoding="utf-8") as fh:
            reg = json.load(fh)
        ends = [time.mktime(time.strptime(m["time"][:16], "%Y-%m-%dT%H:%M")) + (m.get("duration_s") or 2400)
                for m in reg.values() if acc in (m.get("accounts") or []) and m.get("time")]
        if ends and time.time() - max(ends) < 2 * 3600:
            warm, wwhy = True, i18n.tr("you played a match less than two hours ago")
    except (OSError, ValueError, TypeError, KeyError):
        pass
    nade = [v for k, v in p["items"].items() if k.startswith("nade:")]
    if not warm and len(nade) >= 8 and sum(v["box"] >= 2 for v in nade) >= 0.7 * len(nade):
        warm, wwhy = True, i18n.tr("you master most of your lineups")
    return {"diff": diff, "why": why, "warmup": warm, "warm_why": wwhy}


def summary(sid=None):
    """For the page: level, XP, last sessions, what comes back next time, what to preselect."""
    p = ingest()
    nsess = len(p["sessions"])
    due = [k for k, v in p["items"].items() if v["next"] <= nsess]
    kinds = {}
    for k in due:
        kinds[k.split(":")[0] if ":" in k else "situation"] = kinds.get(k.split(":")[0] if ":" in k else "situation", 0) + 1
    stars = {k: v["box"] for k, v in p["items"].items()}
    return {**level(p["xp"]), "sessions": p["sessions"][-5:], "due": kinds, "mastered": sum(1 for v in stars.values() if v >= 3),
            "items": len(stars), "suggest": suggest(sid, p) if sid and str(sid).isdigit() else None, "last": last_session(p)}


def last_session(p=None):
    """The last session's recap for Prepare (13/10, a focus block's "bilan": what worked, its measures, what comes back
    next time): each drill's last try (its title from the session's file), the missed ones that come back."""
    p = p or progress()
    if not p["sessions"]:
        return None
    s = p["sessions"][-1]
    titles = {}
    try:
        for b in json.load(open(os.path.join(SESS, f"{s['id']}.json"), encoding="utf-8"))["blocks"]:
            for d in b["drills"]:
                titles[d["id"]] = (d.get("title") or d["id"], b["kind"])
    except (OSError, ValueError, KeyError):
        pass
    last = {}
    try:
        with open(os.path.join(replay.COACH, "results.jsonl"), encoding="utf-8") as f:
            for ln in f:
                if s["id"] not in ln:
                    continue
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if r.get("session") == s["id"] and r.get("drill"):
                    last[r["drill"]] = r
    except OSError:
        pass
    drills = [{"title": titles.get(k, (k, ""))[0], "kind": titles.get(k, ("", r.get("kind") or ""))[1], "ok": bool(r.get("ok")),
               "outcome": r.get("outcome") or "", "detail": r.get("detail") or ""} for k, r in last.items()]
    again = sum(1 for k, r in last.items() if not r.get("ok") and r.get("outcome") != "skipped")
    return {"id": s["id"], "t": s.get("t"), "minutes": s.get("minutes"), "maps": s.get("maps") or [], "focus": s.get("focus"),
            "done": bool(s.get("done")), "points": s.get("points") if s.get("done") else sum(int(r.get("points") or 0) for r in last.values()),
            "ok": sum(1 for d in drills if d["ok"]), "n": len(drills), "drills": drills, "again": again}


def _game_running():
    """The game runs (the training server is a cs2.exe too: the one started with -dedicated)."""
    import subprocess
    if os.name != "nt":   # Linux: the game's process and its command line through psutil
        import psutil
        return any(config.is_cs2(p.info.get("name")) and "-dedicated" not in " ".join(p.info.get("cmdline") or [])
                   for p in psutil.process_iter(["name", "cmdline"]))
    ps = "Get-CimInstance Win32_Process -Filter \"name='cs2.exe'\" | ForEach-Object { $_.CommandLine }"
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, creationflags=replay.NO_WINDOW)
    return any(ln.strip() and "-dedicated" not in ln for ln in r.stdout.splitlines())


def _console():
    from wily.live import chatcalls
    f = chatcalls.console_file()
    return f if f and os.path.exists(f) else None


def _menu_since(start_size):
    """The game's main menu is up since the launch, its background map loaded (its console log is written again at
    each launch): a connect given before that is cut while the map loads (LOOPSHUTDOWN, seen on 03/10)."""
    f = _console()
    if not f:
        return False
    size = os.path.getsize(f)
    with open(f, "rb") as fh:
        fh.seek(0 if size < start_size else start_size)
        t = fh.read()
    return b"-> CSGO_GAME_UI_STATE_MAINMENU" in t and b"Connected to 'loopback" in t


def _connected_since(start_size):
    """The game reached the training server since that point of its console log: it is loading the map now."""
    f = _console()
    if not f:
        return False
    size = os.path.getsize(f)
    with open(f, "rb") as fh:
        fh.seek(0 if size < start_size else start_size)
        t = fh.read()
    return f"Connected to '127.0.0.1:{replay.PORT}'".encode() in t


def _refused_since(start_size):
    """The game gave up loading the server's map since that point of its console log: why, in a few words (07/10: the
    game refused aim_map's unsigned file and went back to its menu, the server only saw a disconnect by the user)."""
    f = _console()
    if not f:
        return None
    size = os.path.getsize(f)
    with open(f, "rb") as fh:
        fh.seek(0 if size < start_size else start_size)
        t = fh.read().decode("utf-8", "replace")
    ms = list(re.finditer(r"Disconnection during connection phase\. Sign-on state: \d+ \((\w+)\)\. Disconnect reason: (\w+)", t))
    if not ms:
        return None
    m = ms[-1]   # the last one: a map change's cut before it is no refusal (below)
    if m.group(2) in ("NETWORK_DISCONNECT_LOOPSHUTDOWN", "NETWORK_DISCONNECT_DISCONNECT_BY_USER"):
        # the server changed its map while the game came in (17/10, the user restarting a session: said in red in
        # Prepare while CS2 loaded the new map and got in), or you left it yourself (19/10, his reconnection: "c'est
        # bizarre comme erreur"): the game follows it or you come back, the wait goes on
        return None
    # a map file the game refused: the server's map's own (maps\, a Workshop map's folder), not one of the Workshop
    # items you are subscribed to (19/10: six "failed" in every console, harmless, and made it a refusal)
    ids = set(replay.WORKSHOP.values())
    sig = next((g for g in re.findall(r"Signature failed for ([^\r\n]*?\.vpk)", t)
                if re.search(r"[\\/]maps[\\/]|^maps[\\/]", g) or any(w in g for w in ids)), None)
    if sig:
        return i18n.tr("CS2 refused the map file {file} (not signed by Valve) and went back to its menu", file=re.split(r"[\\/]", sig)[-1])
    return i18n.tr("CS2 left the server while loading the map ({what} at {when})", what=m.group(2), when=m.group(1))


_LAUNCH = {}


def _open(url):
    """A steam:// link through the system: Windows' file association, xdg-open on Linux."""
    if os.name == "nt":
        os.startfile(url)
    else:
        import subprocess
        subprocess.Popen(["xdg-open", url], start_new_session=True)


def _launch_game():
    """CS2 started, not connected yet: its menu comes up while the session is built (06/10: the build took 4 minutes
    on a busy disk and the game only started after it)."""
    f = _console()
    _LAUNCH.update(start=os.path.getsize(f) if f else 0, t=time.time())
    _open("steam://run/730")


def _wait_menu(start):
    for _ in range(180):
        if _menu_since(start):
            break
        time.sleep(1)
    time.sleep(8)   # the menu settles


def _connect():
    """The game sent to the server. A connect given while CS2 starts is lost (it runs before the menu is ready): a
    closed game is started first, the connect waits for its menu. First the game's own connect (Steam passes it to the
    running game), then Steam's: Steam's opens its "game info" window, whose check of the local server fails ("the app
    ID given by the server is invalid", 06/10) while its "Join" button works. Once the game has reached the server it is
    loading the map: no other connect then, it would cut the load. A map the game refuses (07/10: aim_map's unsigned file,
    the 06/10 19:57 drop was that too) is said in Prepare (replay.JOIN) instead of waiting."""
    urls = [f"steam://rungame/730/76561202255233023/+connect%20127.0.0.1:{replay.PORT}", f"steam://connect/127.0.0.1:{replay.PORT}"]
    recent = _LAUNCH and time.time() - _LAUNCH.get("t", 0) < 240
    if not _game_running() and not (recent and time.time() - _LAUNCH["t"] < 60):
        _launch_game()
        _wait_menu(_LAUNCH["start"])
    elif recent and not _menu_since(_LAUNCH["start"]):
        _wait_menu(_LAUNCH["start"])   # started a moment ago (play()): its menu first
    f = _console()
    replay.JOIN.clear()
    replay.JOIN.update(state="joining", t=time.time())
    for url in urls:
        start = os.path.getsize(f) if f else 0
        _open(url)
        t0, wait, loading = time.time(), (30 if url.startswith("steam://rungame") else 60), False
        while time.time() - t0 < wait:
            time.sleep(1)
            h = replay.heartbeat()
            if h and h.get("humans"):
                time.sleep(10)   # still there 10 s later: in game (a connect cut while loading drops you before)
                h = replay.heartbeat()
                if h and h.get("humans"):
                    replay.JOIN.update(state="in", t=time.time())
                    return True
            if not loading and _connected_since(start):
                loading, wait = True, time.time() - t0 + 150   # on the server, the map loading: wait for it, nothing else
                replay.JOIN.update(state="loading", t=time.time())
            why = _refused_since(start) if loading else None
            if why:   # Prepare says it (Rejoin would only do the same again)
                replay.JOIN.update(state="refused", why=why, t=time.time())
                print("training join:", why, flush=True)
                return False
        if loading:
            replay.JOIN.update(state="failed", why=i18n.tr("CS2 reached the server but did not get into the game"), t=time.time())
            return False   # it got to the server but not in the game: no second connect (Prepare's Rejoin is there)
    replay.JOIN.update(state="failed", why=i18n.tr("CS2 did not reach the training server"), t=time.time())
    return False


def _quiet_start(mp):
    try:
        replay.start(mp)
    except Exception as e:   # play() starts it again and says why
        print("training server early start:", e, flush=True)


RECETTE_F = os.path.join(config.OUT, "realtest", "recette.json")   # tools/recette.py: the drills the latest tests failed


def recette_build(sid, difficulty=2, seed=None):
    """The recette (28/10, the user: "des séances de labo ... uniquement à moi ... une session intensive de tous les éléments
    qui posent problème"): every drill the latest tests failed (tools/recette.py's list), map by map, each once, none
    drawn. A Stuff site take or defense comes whole (its lineups, then all of them at once)."""
    groups = {}
    for x in config.read_json(RECETTE_F, []) or []:
        groups.setdefault((x["map"], x["focus"], x.get("exec")), set()).add(x["id"])
    blocks = []
    for (mp, kind, ex), ids in groups.items():
        if kind not in FOCUS:
            continue
        try:
            sub = build(sid, minutes=max(5, min(90, len(ids) * EST.get(kind, 60) // 60 + 1)), where=mp, difficulty=difficulty, focus=kind,
                        record=False, tag="recette_part", exec_key=ex if kind == "nade" else None, seed=seed, only=None if ex else ids)
        except ValueError as e:
            print("recette", mp, kind, ex, e, flush=True)
            continue
        blocks += sub["blocks"]
    if not blocks:
        raise ValueError("nothing failed in the latest tests")
    maps_ = list(dict.fromkeys(b["map"] for b in blocks))
    blocks.sort(key=lambda b: maps_.index(b["map"]))   # one map change per map
    sid_ = time.strftime("recette_%Y%m%d_%H%M%S")
    sess = {"id": sid_, "minutes": max(1, sum(b["seconds"] for b in blocks) // 60), "where": ",".join(maps_), "maps": maps_,
            "difficulty": int(difficulty), "level": level(ingest()["xp"]), "warmup": False, "focus": "recette", "blocks": blocks}
    if seed is not None:
        sess["seed"] = int(seed)
    os.makedirs(SESS, exist_ok=True)
    json.dump(sess, open(os.path.join(SESS, f"{sid_}.json"), "w", encoding="utf-8"), ensure_ascii=False)
    return sess


def play_recette(sid, difficulty=2, seed=None):
    """The recette played as one Play: built, the server on its first map, the plugin told, the game sent to it."""
    import threading
    if not replay.claim("the recette"):
        raise RuntimeError(f"{replay.busy()} is starting on the training server: wait for it")
    try:
        if not _game_running():
            _launch_game()
        sess = recette_build(sid, difficulty, seed)
        replay.start(sess["blocks"][0]["map"])
        replay.rcon(f"css_session {sess['id']}")
        threading.Thread(target=_connect, daemon=True).start()
        return {"session": {k: sess[k] for k in ("id", "minutes", "maps")},
                "blocks": [{"map": b["map"], "kind": b["kind"], "seconds": b["seconds"], "n": len(b["drills"])} for b in sess["blocks"]],
                **replay.status()}
    finally:
        replay.release()


def play(sid, minutes=20, where="random", difficulty=2, focus=None, exec_key=None, weapon=None, seed=None, every=False):
    """exec_key: a focus block's choice instead of its time (a Stuff block's site take, a Momentum block's part)."""
    """One Play: the session built, the server on its first map, the plugin told, and the game sent to the server
    (started first if it is closed). You only follow what the game shows."""
    import ctypes
    if not replay.claim("a warm-up"):
        raise RuntimeError(f"{replay.busy()} is starting on the training server: wait for it")
    try:
        # the build reads the hard disk a while: below the server and the game (the request's thread only)
        ctypes.windll.kernel32.SetThreadPriority(ctypes.windll.kernel32.GetCurrentThread(), -1)
    except Exception:
        pass
    try:
        return _play(sid, minutes, where, difficulty, focus, exec_key, weapon, seed, every)
    finally:
        try:
            ctypes.windll.kernel32.SetThreadPriority(ctypes.windll.kernel32.GetCurrentThread(), 0)
        except Exception:
            pass
        replay.release()


def _play(sid, minutes, where, difficulty, focus=None, exec_key=None, weapon=None, seed=None, every=False):
    import threading
    named = [m for m in str(where).split(",") if m in maps(sid) or m in base_maps()]
    if focus in FOCUS:   # a focus block: one map
        named = named[:1]
    cf = next((m for m in named if (crossfire.load(m, build=False) or {}).get("spots")), None)   # Crossfire's map (13/10)
    if focus in FOCUS and focus != "crossfire":
        first = next(iter(named), None)
    else:   # 5 min: no aim, straight to the map
        first = (cf or aim_map()) if focus == "crossfire" or aim_seconds(minutes) else next(iter(named), None)
    if not _game_running():   # CS2 comes up while the session is built (its menu is needed before a connect)
        _launch_game()
    pre = threading.Thread(target=lambda: _quiet_start(first), daemon=True) if first else None
    if pre:   # the server starts while the session is built (06/10: a minute and a half before anything happened)
        pre.start()
    sess = build(sid, minutes, where, difficulty, focus, exec_key=exec_key if focus == "nade" else None,
                 pick=exec_key if focus == "momentum" else None, weapon=weapon, seed=seed, every=every)
    if pre:
        pre.join(timeout=150)   # never an RCON before its map runs: the server would then refuse 127.0.0.1
    replay.start(sess["blocks"][0]["map"])
    replay.rcon(f"css_session {sess['id']}")
    threading.Thread(target=_connect, daemon=True).start()
    return {"session": {k: sess[k] for k in ("id", "minutes", "maps")},
            "blocks": [{"map": b["map"], "kind": b["kind"], "seconds": b["seconds"], "n": len(b["drills"])} for b in sess["blocks"]],
            **replay.status()}
