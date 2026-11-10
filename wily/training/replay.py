"""Training on a local server: situations of your own demos played again. The bots follow exactly the recorded paths of
the nine other players (where they went, where they looked), they shoot back on their own when they see you, and you
take your own spot again (actor) or watch it all (spectator: a bot plays your spot too).

- scenarios(sid): the situations worth playing again: your deaths that lost the round or were not traded, the clutches
  you lost, from your last matches with a demo in cache.
- build(sid, mid, rnd, kind): one scenario from the demo (positions of the ten players every 2 ticks, their loadouts,
  who killed whom) written to the server's coach/scenarios folder.
- start(map) / stop() / status(): the server (a separate copy made by tools/make_server.py), hidden, 127.0.0.1 only; the
  plugin CoachReplay (plugin/CoachReplay) plays the scenario and appends each try to coach/results.jsonl.
Nothing here touches the game: the server is its own copy, and the game joins it like any community server."""
import json
import math
import os
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time

import numpy as np
import pandas as pd

from wily.core import config
from wily.core import i18n

SERVER = config.cs2server_dir()   # COACH_CS2SERVER, the settings, or next to the game (any PC)
EXE = os.path.join(SERVER, "game", "bin", *(("linuxsteamrt64", "cs2") if config.LINUX else ("win64", "cs2.exe")))
LINUX_LOG = os.path.join(config.OUT, "train_server.log")   # Linux: the server's own output (its first runs: what to fix)
EXPERIMENTAL = i18n.N_("The training server is experimental on Linux: turn it on in Settings (Training server on Linux), then try again. Review and Live work without it.")   # said with i18n.tr where it is raised
CSGO = os.path.join(SERVER, "game", "csgo")
COACH = os.path.join(CSGO, "coach")   # scenarios/, results.jsonl, live.json (the plugin's heartbeat)
SCEN = os.path.join(COACH, "scenarios")
# 23/10, the user: "lancer en parallèle le jeu et les tests ... pendant que Ancient, Vertigo ... se font analyser": a second
# server beside the first (COACH_CS2SERVER its folder, COACH_CS2PORT its port), its own state; the app's is 27015
PORT = int(os.environ.get("COACH_CS2PORT") or 27015)
STATE_F = os.path.join(config.OUT, "train.json" if PORT == 27015 else f"train_{PORT}.json")
STEP = 2   # one position every 2 ticks (32 a second); the plugin interpolates
BEFORE, AFTER, CLUTCH = 7, 6, 35   # seconds of a death situation before and after it; length of a clutch
NO_WINDOW = config.NO_WINDOW   # CREATE_NO_WINDOW on Windows, 0 elsewhere (Linux: no creationflags)

ITEMS = {"AK-47": "ak47", "M4A4": "m4a1", "M4A1-S": "m4a1_silencer", "AWP": "awp", "SSG 08": "ssg08", "AUG": "aug",
         "SG 553": "sg556", "FAMAS": "famas", "Galil AR": "galilar", "G3SG1": "g3sg1", "SCAR-20": "scar20",
         "MAC-10": "mac10", "MP9": "mp9", "MP7": "mp7", "MP5-SD": "mp5sd", "UMP-45": "ump45", "P90": "p90",
         "PP-Bizon": "bizon", "Nova": "nova", "XM1014": "xm1014", "MAG-7": "mag7", "Sawed-Off": "sawedoff",
         "M249": "m249", "Negev": "negev", "Glock-18": "glock", "USP-S": "usp_silencer", "P2000": "hkp2000",
         "P250": "p250", "Five-SeveN": "fiveseven", "Tec-9": "tec9", "CZ75-Auto": "cz75a", "Desert Eagle": "deagle",
         "R8 Revolver": "revolver", "Dual Berettas": "elite", "Zeus x27": "taser", "High Explosive Grenade": "hegrenade",
         "Flashbang": "flashbang", "Smoke Grenade": "smokegrenade", "Molotov": "molotov",
         "Incendiary Grenade": "incgrenade", "Decoy Grenade": "decoy", "C4 Explosive": "c4"}


def _item(name):
    if not name:
        return None
    if name in ITEMS:
        return "weapon_" + ITEMS[name]
    low = str(name).lower()
    if "knife" in low or "bayonet" in low or "karambit" in low or "dagger" in low:
        return "weapon_knife"
    return None


# ---------------------------------------------------------------- the situations

# a player's history (05/10, the beta): the demos of the base's matches stay on the coach's PC (200-300 MB each), their
# situations come built from them (tools/make_beta.py), one folder per match
PREBUILT = os.path.join(config.OUT, "scenarios")


def _has_demo(mid):
    return config.has_demo(mid)


def clutch_time_ok(sc_id):
    """A clutch with the bomb down for you to defuse, with the time it takes (02/11 17:20, the user: "garde les clutchs qui ont
    plus de marges temporelles en prenant en compte le temps de defuse si j'ai un kit ou pas plus le temps d'aller tuer les
    joueurs en prenant en compte le temps de déplacement"; round 16: 7 of them lost to the bomb): the bomb's time at its
    start (or till its plant, then 40 s) against your way to it on the mesh at 220 u/s, its defuse (5 s with a kit, 10
    without) and 5 s for each of them still up once you are alone, 5 s more. -> False when it cannot be made; True otherwise, or when its
    scenario is not built yet."""
    f = os.path.join(SCEN, f"{sc_id}.json")
    if not os.path.exists(f):
        try:
            mid, rest = str(sc_id).split("_r", 1)
            rnd, k = rest.split("_", 1)
            f = _prebuilt(mid, rnd, "clutch" if k.startswith("c") else "death") or ""
        except ValueError:
            return True
    try:
        sc = json.load(open(f, encoding="utf-8"))
    except (OSError, ValueError):
        return True
    b = sc.get("bomb") or {}
    me = next((p for p in sc.get("players") or [] if p.get("me")), None)
    if not b.get("pos") or not me or me.get("team") != 3 or len(me.get("path") or []) < 3:
        return True
    fps = float(sc.get("rate") or 64) / float(sc.get("step") or 2)
    avail = float(b.get("f") or 0) / fps + float(b.get("left") or 40.0)
    start = list(me["path"][:3])
    dist = None
    try:
        from wily.training import navmesh
        r = navmesh.route(sc.get("map"), start, list(b["pos"]))
        if r:
            dist = sum(math.dist(r[i][:2], r[i + 1][:2]) for i in range(len(r) - 1))
    except Exception:
        dist = None
    if dist is None:
        dist = 1.3 * math.dist(start[:2], b["pos"][:2])
    # the ones still up once you are alone (your last teammate down): 5 s each to find and kill, 5 s more of margin (his
    # "plus de marges temporelles"; at 3 s and 2 s Fachwerk's R24 passed, 26.6 s for 22.9, lost twice to the bomb)
    # (a death frame of -1: alive to the end)
    mates = [p.get("death") for p in sc.get("players") or [] if p.get("team") == me.get("team") and not p.get("me")]
    alone = max(mates) if mates and all(isinstance(d, (int, float)) and d > 0 for d in mates) else 0
    foes = sum(1 for p in sc.get("players") or []
               if p.get("team") not in (None, me.get("team")) and (p.get("death") is None or p.get("death") < 0 or p.get("death") > alone))
    need = dist / 220.0 + (5.0 if me.get("kit") else 10.0) + 5.0 * foes + 5.0
    return avail >= need


PASSIVE_SINCE = 1793637000   # 02/11 17:30: the bots come and duel you from then (CoachReplay.cs); older ones not counted


def passive_withdrawn():
    """The situations that end with nobody killed twice of their last three plays since the bots come for you (02/11 17:20,
    the user: "fait en sorte que les bots viennent jouer des duels contre moi ou alors enlève cette drill"): their ids."""
    last = {}
    try:
        with open(os.path.join(COACH, "results.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                if '"situation"' not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("kind") == "situation" and (r.get("t") or 0) >= PASSIVE_SINCE:
                    last.setdefault(r.get("drill"), []).append(r.get("outcome"))
    except OSError:
        return set()
    return {d for d, o in last.items() if sum(1 for x in o[-3:] if x == "passive") >= 2}


def _prebuilt(mid, rnd, kind):
    f = os.path.join(PREBUILT, str(mid), f"{mid}_r{int(rnd)}_{kind[0]}.json")
    return f if os.path.exists(f) else None


_OWN = {}


def _own_matches(sid, n=15):
    """Your last matches with their demo: [(match, map)]. Kept while your matches folder is the same, a minute at most
    (22/10: a session's build read your 124 stats.json twice, on the hard disk)."""
    md = os.path.join(config.player_dir(sid), "matches")
    try:
        names = tuple(sorted(os.listdir(md))) if os.path.isdir(md) else ()
    except OSError:
        names = ()
    hit = _OWN.get(str(sid))
    if not hit or hit[1] != names or time.time() - hit[0] > 60:
        out = []
        for mid in names:
            deep = os.path.join(config.OUT, "deep", mid)
            if (_has_demo(mid) or os.path.isdir(os.path.join(PREBUILT, mid))) and os.path.exists(os.path.join(deep, "duels.parquet")):
                try:
                    st = json.load(open(os.path.join(md, mid, "stats.json"), encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                out.append((mid, st.get("map")))
        hit = _OWN[str(sid)] = (time.time(), names, sorted(out, key=lambda x: int(x[0]), reverse=True))
    return list(hit[2][:n])


# 29/10, the user: "élimine des situations qui n'ont rien à foutre là. Des duels longue distance alors que je suis au fusil à
# pompe ... c'est littéralement des mauvais placements de base ... j'ai rien à faire là avec cette arme là": a death at a range
# your weapon can't fight at is no duel to play again (a shotgun past 13 m, an SMG past 30 m: the duels' distance is in m);
# kept apart for the coaching (where you stood with what)
SHOTGUNS = {"Nova", "XM1014", "MAG-7", "Sawed-Off"}
SMGS = {"MP9", "MAC-10", "MP7", "MP5-SD", "UMP-45", "P90", "PP-Bizon"}


def misplaced(weapon, dist_m):
    """Your weapon could not fight there: a shotgun past 13 m, an SMG past 30 m."""
    try:
        d = float(dist_m)
    except (TypeError, ValueError):
        return False
    return (weapon in SHOTGUNS and d > 13) or (weapon in SMGS and d > 30)


def scenarios(sid, n=15):
    """The situations worth playing again, the worst first: the 1v1 and 1v2 you lost, your opening deaths not traded in a
    lost round, then the rest (1v3, deaths with one of the three)."""
    sid = str(sid)
    out, odd = [], []
    try:
        lost = set(json.load(open(LOST_F, encoding="utf-8")))
    except (OSError, ValueError):
        lost = set()
    for mid, mp in _own_matches(sid, n):
        deep = os.path.join(config.OUT, "deep", mid)
        D = pd.read_parquet(os.path.join(deep, "duels.parquet"))
        L = pd.read_parquet(os.path.join(deep, "loadout.parquet"), columns=["round", "steamid", "side", "won", "primary", "pistol"])
        L["steamid"] = L.steamid.astype(str)
        me = L[L.steamid == sid].set_index("round")
        D["killer"], D["victim"] = D.killer.astype(str), D.victim.astype(str)
        for _, d in D[D.victim == sid].iterrows():
            r = int(d["round"])
            mine = (me.primary.get(r) or me.pistol.get(r)) if r in me.index else None
            if misplaced(mine, d.get("distance")):
                odd.append({"mid": mid, "map": mp, "round": r, "t": round(float(d.t), 1), "zone": d.victim_zone, "weapon": mine,
                            "distance_m": round(float(d.distance), 1), "by": d.killer_name, "their": d.weapon})
                continue
            won = bool(me.won.get(r)) if r in me.index else None
            score = (2 if won is False else 0) + (1 if not d.get("traded") else 0) + (1 if d.get("opening") else 0)
            out.append({"id": f"{mid}_r{r}_d", "mid": mid, "map": mp, "round": r, "kind": "death", "t": round(float(d.t), 1),
                        "side": d.victim_side, "zone": d.victim_zone, "by": d.killer_name, "weapon": d.weapon,
                        "mine": (me.primary.get(r) or me.pistol.get(r)) if r in me.index else None,
                        "opening": bool(d.get("opening")), "traded": bool(d.get("traded")), "won": won, "score": score})
        # clutches: the last teammate falls while you are alive, enemies left
        for r, R in D.groupby("round"):
            if r not in me.index:
                continue
            side = me.side.get(r)
            mates = set(L[(L["round"] == r) & (L.side == side) & (L.steamid != sid)].steamid)
            dead = R.sort_values("tick")
            gone = dead[dead.victim.isin(mates)]
            if len(mates) < 1 or len(gone.victim.unique()) < len(mates):
                continue
            last = gone.iloc[-1]
            mine = dead[dead.victim == sid]
            if len(mine) and mine.tick.iloc[0] < last.tick:
                continue
            n_en = int(((L["round"] == r) & (L.side != side)).sum()) or 5   # the enemy team as it was (one may have left)
            foes = n_en - int(((dead.victim_side != side) & (dead.tick <= last.tick)).sum())
            if not 1 <= foes <= 3 or bool(me.won.get(r)):   # 1v4, 1v5: nothing much to learn
                continue
            out.append({"id": f"{mid}_r{int(r)}_c", "mid": mid, "map": mp, "round": int(r), "kind": "clutch",
                        "t": round(float(last.t), 1), "side": side, "zone": last.victim_zone, "vs": foes,
                        "mine": me.primary.get(r) or me.pistol.get(r), "won": False, "score": {1: 5, 2: 4}.get(foes, 3)})
    if odd:   # the deaths with the wrong weapon for the range: for the coaching, not to replay
        try:
            config.write_json(os.path.join(config.player_dir(sid), "misplaced.json"), odd)
        except OSError:
            pass
    # a match without its demo (the player's history): only the situations built on the coach's PC
    out = [s for s in out if (_has_demo(s["mid"]) or _prebuilt(s["mid"], s["round"], s["kind"])) and s["id"] not in lost]
    return sorted(out, key=lambda s: (-s["score"], -int(s["mid"]), s["round"]))


# ---------------------------------------------------------------- one scenario from the demo

# 08/10: a player's app went down with an access violation in polars' runtime (demoparser2 uses it), the session's
# situations parsed in three threads while a second session's were starting. The demos the app parses itself (the
# situations, the defense's entries) now go to ONE worker process, one at a time: a crash there costs a situation,
# never the app (the analysis' own workers already work this way: cs2coach).
PARSE = threading.RLock()
_POOL = {"ex": None}


def in_worker(fn, *args):
    """fn(*args) in the app's demo worker (a process of its own, one job at a time); straight here when this already is
    a worker. A crash of the worker: started again once, then RuntimeError."""
    import multiprocessing
    if multiprocessing.current_process().name != "MainProcess":
        return fn(*args)
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool
    with PARSE:
        for attempt in (1, 2):
            if _POOL["ex"] is None:
                _POOL["ex"] = ProcessPoolExecutor(1, initializer=config.low_priority)
            try:
                return _POOL["ex"].submit(fn, *args).result()
            except BrokenProcessPool:
                _POOL["ex"] = None
                print(f"demo worker crashed ({getattr(fn, '__name__', fn)}{args[:3]})" + (", trying once more" if attempt == 1 else ""), flush=True)
        raise RuntimeError("the demo parser crashed on this demo")


def build(sid, mid, rnd, kind="death", t=None):
    return in_worker(_build, sid, mid, rnd, kind, t)


def _build(sid, mid, rnd, kind="death", t=None):
    from demoparser2 import DemoParser
    sid, mid, rnd = str(sid), str(mid), int(rnd)
    pre = None if _has_demo(mid) else _prebuilt(mid, rnd, kind)
    if pre:   # a match of the player's history: built on the coach's PC
        sc = json.load(open(pre, encoding="utf-8"))
        os.makedirs(SCEN, exist_ok=True)
        shutil.copyfile(pre, os.path.join(SCEN, f"{sc['id']}.json"))
        return sc
    deep = os.path.join(config.OUT, "deep", mid)
    R = pd.read_parquet(os.path.join(deep, "rounds.parquet")).set_index("round")
    D = pd.read_parquet(os.path.join(deep, "duels.parquet"))
    D["killer"], D["victim"] = D.killer.astype(str), D.victim.astype(str)
    mp = json.load(open(os.path.join(deep, "meta.json"), encoding="utf-8"))["map"]
    t0, t_end = int(R.start_tick[rnd]), int(R.end_tick[rnd])
    Dr = D[D["round"] == rnd].sort_values("tick")
    if kind == "clutch":   # t: when the last teammate fell (from scenarios())
        if t is None:
            t = next(s for s in scenarios(sid, n=60) if s["mid"] == mid and s["round"] == rnd and s["kind"] == "clutch")["t"]
        key = int(Dr[Dr.t <= t + 0.05].tick.iloc[-1])
        start, end = max(t0, key - 64), min(t_end, key + CLUTCH * 64)
    else:
        key = int(Dr[Dr.victim == sid].tick.iloc[0])
        start, end = max(t0, key - BEFORE * 64), min(t_end, key + AFTER * 64)
    p = DemoParser(config.demo(mid))
    # start when no enemy is close: the latest moment 5 to 20 s before (a clutch: 1 to 12 s before it starts), with all of
    # them 1,100 u away (06/10, a clutch started face to face with its enemy: "je viens d'ici à la base, je ne peux pas
    # me retrouver face à face")
    if True:
        try:
            early = max(t0 + 2 * 64, key - (12 if kind == "clutch" else 20) * 64)
            Q = p.parse_ticks(["X", "Y", "team_num", "is_alive"], ticks=list(range(early, key - (1 if kind == "clutch" else 5) * 64 + 1, 32)))
            Q["steamid"] = Q.steamid.astype(str)
            mine = Q[Q.steamid == sid].set_index("tick")
            myteam = int(mine.team_num.iloc[0]) if len(mine) else 0
            for tk in sorted(Q.tick.unique(), reverse=True):
                if tk not in mine.index:
                    continue
                me_ = mine.loc[tk]
                en = Q[(Q.tick == tk) & (Q.team_num != myteam) & Q.team_num.isin([2, 3]) & Q.is_alive]
                if not len(en) or float(np.hypot(en.X - me_.X, en.Y - me_.Y).min()) >= 1100:
                    start = int(tk)
                    break
        except Exception as e:
            print("start", mid, rnd, e, flush=True)
    # a bit more of the round before it (07/10, the user: "commencer la situation un peu plus tôt, un peu avant la
    # situation", "un peu plus de recul sur le round")
    start = max(t0 + 16, start - (3 if kind == "clutch" else 4) * 64)
    if start - t0 < 12 * 64:   # very early in the round: from the spawn (06/10: "fais-moi partir quasiment du spawn")
        start = t0 + 16
    ticks = list(range(start, end + 1, STEP))
    T = p.parse_ticks(["X", "Y", "Z", "yaw", "pitch", "is_alive", "team_num", "ducking", "last_place_name"], ticks=ticks)
    T["steamid"] = T.steamid.astype(str)
    S = p.parse_ticks(["team_num", "inventory", "active_weapon_name", "health", "armor_value", "has_helmet", "has_defuser", "is_alive"],
                      ticks=[start])
    S["steamid"] = S.steamid.astype(str)
    players = []
    team_of = {str(r.steamid): int(r.team_num) for r in S.itertuples() if r.team_num in (2, 3)}
    # who killed whom in the window, from the demo's own deaths (04/10: a bot you killed in the match with a kill the
    # duels table did not keep died on its own in the replay, though you did not kill it this time)
    try:
        K = p.parse_event("player_death")
        K = K[(K.tick >= start) & (K.tick <= end)]
        killer_of, weapon_of = {}, {}
        for u, a_, w_ in zip(K.user_steamid, K.attacker_steamid, K.weapon):
            u, a_ = str(u), ("" if a_ is None or a_ != a_ else str(a_))
            killer_of.setdefault(u, "" if a_ in ("", "0", u) else a_)   # yourself or the world: ""
            weapon_of.setdefault(u, str(w_ or ""))
    except Exception as e:
        print("deaths", mid, rnd, e, flush=True)
        killer_of, weapon_of = {}, {}
    for _, s in S.iterrows():
        if s.team_num not in (2, 3) or not s.is_alive:
            continue
        g = T[T.steamid == s.steamid].sort_values("tick")
        alive = g.is_alive.to_numpy()
        death = next((i for i in range(len(alive)) if not alive[i]), -1)
        k = g if death < 0 else g.iloc[:death]
        # the round's end tick can be the next round's start: everyone back on a spawn, thousands of units in one step
        # (17/10, the self-test: 41 of 2,258 ways ended so, their bots put back across the map): cut there
        jump = np.nonzero(np.hypot(np.diff(k.X.to_numpy(float)), np.diff(k.Y.to_numpy(float))) > 200)[0]
        if len(jump):
            k = k.iloc[:int(jump[0]) + 1]
            death = death if 0 <= death < len(k) else -1
        path = []
        for x, y, z, yw, pt in zip(k.X, k.Y, k.Z, k.yaw, k.pitch):
            path += [round(float(x), 1), round(float(y), 1), round(float(z), 1), round(float(yw), 1), round(float(pt), 1)]
        duck = [int(i) for i, v in enumerate(k.ducking.fillna(False)) if v]
        died = Dr[(Dr.victim == s.steamid) & (Dr.tick >= start) & (Dr.tick <= end)]
        kl = killer_of.get(s.steamid, str(died.killer.iloc[0]) if len(died) else "")
        if kl and team_of.get(kl) == int(s.team_num):   # a teammate's spray in the match (04/10, Nuke R16): not here
            death, kl = -1, ""
        weapons = [w for w in (_item(i) for i in (s.inventory or [])) if w]
        places = []   # your route in the match: where you went, when (the screen shows the next one)
        if s.steamid == sid and "last_place_name" in k:
            from wily.insights import nades
            names = [nades.humanize(pl, mp) if pl else None for pl in k.last_place_name.fillna("")]
            runs = []   # (first frame, name, frames): a place crossed in less than half a second is left out
            for i, nm in enumerate(names):
                if runs and runs[-1][1] == nm:
                    runs[-1][2] += 1
                else:
                    runs.append([i, nm, 1])
            for i, nm, n in runs:
                if nm and n >= 16 and (not places or places[-1][1] != nm):
                    places.append([i, nm])
        from wily.insights import nades
        at = nades.humanize(k.last_place_name.fillna("").iloc[0], mp) if len(k) and "last_place_name" in k else None
        players.append({"sid": s.steamid, "name": str(s["name"])[:31], "team": int(s.team_num), "me": s.steamid == sid, "places": places, "at": at,
                        "hp": int(s.health), "armor": int(s.armor_value), "helmet": bool(s.has_helmet),
                        "kit": bool(s.get("has_defuser")) and int(s.team_num) == 3,
                        "weapons": weapons, "active": _item(s.active_weapon_name), "path": path, "duck": duck,
                        "death": death, "killer": kl, "kw": weapon_of.get(s.steamid, "") if kl else ""})
    me = next((q for q in players if q["me"]), None)
    if not me:
        raise ValueError("you are not alive at the start of this situation")
    teams = {q["sid"]: q["team"] for q in players}
    zone = (Dr[Dr.victim == sid].victim_zone.iloc[0] if kind == "death" and len(Dr[Dr.victim == sid]) else "")
    from wily.insights import nades
    md = Dr[Dr.victim == sid]
    danger = ""
    if kind == "death" and len(md):   # who got you, from where, with what
        k0 = md.iloc[0]
        danger = i18n.tr("{who} got you from {zone} ({weapon})", who=k0.killer_name, zone=nades.humanize(k0.killer_zone, mp) or '?', weapon=k0.weapon)
    bomb, plant = _bomb(p, R, rnd, t0, t_end, start, end, me)
    goal = i18n.tr("win the round (a kill at least)") if kind == "clutch" else i18n.tr("a kill, or get traded (no kill: no point)")
    if bomb and bomb["f"] == 0 and kind == "clutch":   # after the plant the bomb decides the round
        goal = i18n.tr("win the round: defuse it") if me["team"] == 3 else i18n.tr("win the round: the bomb blows up, or they all die")
    try:   # your way in the match, drawn on the ground like the prefire's (04/10: "give me the route on the ground")
        from wily.training import train
        line = train._ground_line(np.array(me["path"], float).reshape(-1, 5), mp) if len(me["path"]) >= 10 else []
    except Exception as e:
        print("line", mid, rnd, e, flush=True)
        line = []
    # 07/10, the user: "plutôt que de mettre le chemin exact dans les situations, une zone dans laquelle la situation se
    # passe pour que j'aie la possibilité de la jouer différemment", and for a retake "la route jusqu'à où elle est":
    # the place where it happens drawn on the ground (the bomb's site once planted, else where you died or where the
    # clutch was), the gold line only up to it
    zone_name, zone_at, zone_poly = "", None, []
    try:
        from wily.training import train
        P = np.array(me["path"], float).reshape(-1, 5)
        if bomb and (bomb["f"] == 0 or kind == "clutch"):
            zone_at = bomb["pos"]
            zone_name = "B Site" if bomb.get("site") == 1 else "A Site"
            zone_name = train.replay_zone("Bombsite" + zone_name[0], mp) or zone_name
        elif kind == "death" and len(md):
            k0 = md.iloc[0]
            zone_at = [float(k0.victim_X), float(k0.victim_Y), float(k0.victim_Z)]
            zone_name = train.replay_zone(k0.victim_zone, mp) or ""
        elif len(P):
            kf = min(len(P) - 1, max(0, (key - start) // STEP))
            zone_at = [float(v) for v in P[kf, :3]]
            pl = T[(T.steamid == sid)].sort_values("tick").last_place_name.fillna("")
            zone_name = train.replay_zone(pl.iloc[min(kf, len(pl) - 1)], mp) if len(pl) else ""
        if zone_at:
            zone_poly = train.zone_outline(mp, zone_name, zone_at) if zone_name else []
            inside = None
            if len(zone_poly) >= 3:
                inside = [i for i, q in enumerate(line) if _in_poly(q[:2], zone_poly)]
            else:
                inside = [i for i, q in enumerate(line) if math.dist(q[:2], zone_at[:2]) < 300]
            line = line[:inside[0] + 1] if inside else line
            if len(line) < 2:
                line = []
    except Exception as e:
        print("zone", mid, rnd, e, flush=True)
    # a defuse you can't make (07/10: "quand je n'ai pas de kit, c'est injouable: soit j'avais un kit dans la démo et
    # c'est jouable, soit la situation est perdue d'avance, autant pas me la faire jouer"): 10 s to defuse without a kit
    lost = ""
    if me["team"] == 3 and bomb and bomb["f"] == 0 and not me.get("kit"):
        foes = sum(1 for q in players if q["team"] != me["team"])
        if bomb["left"] < 12 + 4 * foes:
            lost = i18n.tr("no kit (10 s to defuse), {s} s left, {n} to kill first: lost in advance", s=f"{bomb['left']:.0f}", n=foes)
            try:
                L = json.load(open(LOST_F, encoding="utf-8"))
            except (OSError, ValueError):
                L = []
            sid_ = f"{mid}_r{rnd}_{kind[0]}"
            if sid_ not in L:
                config.write_json(LOST_F, L + [sid_])
    # who died before the window, where, when (06/10: "il me faut du contexte: savoir où mes alliés meurent pour savoir
    # où sont les ennemis"), and where everyone went before it (the doors they opened, the vents they broke)
    dead, trail = [], []
    for r in Dr[(Dr.tick >= t0) & (Dr.tick < start)].itertuples():
        if r.victim_side in ("T", "CT") and r.victim_X == r.victim_X:
            dead.append({"pos": [round(float(r.victim_X), 1), round(float(r.victim_Y), 1), round(float(r.victim_Z), 1)],
                         "team": 2 if r.victim_side == "T" else 3, "at": nades.humanize(r.victim_zone, mp) or "",
                         "clock": nades._timer(float(r.t))})
    try:
        if start - t0 > 64:
            B = p.parse_ticks(["X", "Y", "Z", "is_alive"], ticks=list(range(t0, start, 32)))
            B = B[B.is_alive.astype(bool)]
            seen_ = set()
            for x, y, z in zip(B.X, B.Y, B.Z):
                k = (int(x // 48), int(y // 48), int(z // 64))
                if k not in seen_:
                    seen_.add(k)
                    trail.append([round(float(x)), round(float(y)), round(float(z))])
    except Exception as e:
        print("trail", mid, rnd, e, flush=True)
    sc = {"id": f"{mid}_r{rnd}_{kind[0]}", "map": mp, "match": mid, "round": rnd, "kind": kind, "rate": 64, "step": STEP,
          "start_tick": start, "key": (key - start) // STEP, "team": me["team"], "zone": zone,
          "title": f"{mp.replace('de_', '').replace('cs_', '').title()} R{rnd} · {'clutch' if kind == 'clutch' else 'death'}"
                   f"{' · ' + zone if zone else ''}", "players": players, "nades": _nades(p, start, end, teams),
          "danger": danger, "goal": goal, "bomb": bomb, "plant": plant, "line": line,
          "clock": round(max(0.0, ROUND_S - (start - t0) / 64), 1), "dead": dead, "trail": trail,
          "zone_name": zone_name, "zone_at": zone_at, "zone_poly": zone_poly, "lost": lost}
    os.makedirs(SCEN, exist_ok=True)
    f = os.path.join(SCEN, f"{sc['id']}.json")
    json.dump(sc, open(f, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return sc


C4_TIMER = 40   # mp_c4timer (competitive)
LOST_F = os.path.join(config.OUT, "train_lost.json")   # situations lost in advance (no kit, no time): never proposed again
ROUND_S = 115   # a round's time after the freeze time (Premier, competitive: 1:55)


def _bomb(p, R, rnd, t0, t_end, start, end, me):
    """The round's bomb for the situation: planted before it starts (ticking from the first second with the time it had
    left), during it (by its planter at that moment, if he is still alive in the replay; yours: you plant it), or not in
    the window. -> (the bomb for the plugin or None, the line said on screen)."""
    try:
        ev = p.parse_event("bomb_planted", player=["X", "Y", "Z", "last_place_name"])
    except Exception:
        ev = None
    rows = ev[(ev.tick >= t0) & (ev.tick <= t_end)] if ev is not None and len(ev) else []
    if not len(rows):
        return None, i18n.tr("not planted: no plant in this round")
    b = rows.iloc[0]
    tick, by = int(b.tick), str(b.user_steamid)
    site = R.plant_site.get(rnd) if "plant_site" in R.columns else None
    if site not in ("A", "B"):
        site = "B" if str(b.get("user_last_place_name") or "").endswith("B") else "A"
    if tick > end:
        return None, i18n.tr("not planted yet (in the match: {site}, {s} s after this starts)", site=site, s=round((tick - start) / 64))
    left = C4_TIMER - max(0, start - tick) / 64
    bomb = {"f": max(0, (tick - start) // STEP), "pos": [round(float(b[f"user_{c}"]), 1) for c in "XYZ"],
            "site": 0 if site == "A" else 1, "left": round(left, 1), "by": by}
    if tick <= start:
        return bomb, i18n.tr("planted at {site} · {s} s left", site=site, s=f"{left:.0f}") + " · " + (i18n.tr("defuse it") if me["team"] == 3 else i18n.tr("keep it ticking"))
    secs = round((tick - start) / 64)
    if by == me["sid"]:
        return bomb, i18n.tr("you have the bomb: in the match you planted {site} {s} s in", site=site, s=secs)
    return bomb, i18n.tr("not planted yet: in the match they plant {site} {s} s in", site=site, s=secs)


NADES = {"CSmokeGrenadeProjectile": "smoke", "CFlashbangProjectile": "flash", "CHEGrenadeProjectile": "he",
         "CMolotovProjectile": "molotov", "CDecoyProjectile": "decoy"}


def _nades(p, start, end, teams):
    """The grenades thrown in the window: frame, type, thrower, first position and speed (the server flies them again
    from there; a thrower dead in the replay throws nothing)."""
    try:
        g = p.parse_grenades()
    except Exception:
        return []
    g = g[g.grenade_type.isin(list(NADES)) & g.x.notna() & (g.tick >= start) & (g.tick <= end)].sort_values("tick")
    out = []
    for (_, sid, typ), e in g.groupby(["grenade_entity_id", "steamid", "grenade_type"]):
        t = e.tick.to_numpy()
        cuts = [0] + [i for i in range(1, len(t)) if t[i] - t[i - 1] > 2] + [len(t)]   # an entity id is reused by later throws
        for a, b in zip(cuts, cuts[1:]):
            r = e.iloc[a:b]
            if len(r) < 2 or int(r.tick.iloc[0]) <= start:   # already flying when the situation starts
                continue
            dt = (int(r.tick.iloc[1]) - int(r.tick.iloc[0])) / 64
            v = [(float(r[c].iloc[1]) - float(r[c].iloc[0])) / dt for c in ("x", "y", "z")]
            v[2] += 0.5 * 320 * dt   # gravity over that first step (0.4 x 800)
            sid = str(sid)
            out.append({"f": (int(r.tick.iloc[0]) - start) // STEP, "type": NADES[typ], "by": sid,
                        "life": int(r.tick.iloc[-1]) - int(r.tick.iloc[0]),   # ticks until it pops (a smoke: until it fades)
                        "inc": NADES[typ] == "molotov" and teams.get(sid) == 3,
                        "p": [round(float(r[c].iloc[0]), 1) for c in ("x", "y", "z")], "v": [round(x, 1) for x in v]})
    return sorted(out, key=lambda n: n["f"])


# ---------------------------------------------------------------- the server

def _state():
    try:
        return json.load(open(STATE_F, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(s):
    # a state read before the RCON password was made never drops it (08/10: a player's first server got a password the
    # next save erased; the app then made another one and the server refused it)
    cur = _state()
    if cur.get("rcon") and not s.get("rcon"):
        s = dict(s, rcon=cur["rcon"])
    json.dump(s, open(STATE_F, "w", encoding="utf-8"))


def _password():
    s = _state()
    if not s.get("rcon"):
        s["rcon"] = secrets.token_hex(8)   # our own server's password, not a user credential: local and random
        _save_state(s)
    return s["rcon"]


def rcon(cmd, timeout=3.0, wait=0.6):
    """A console command on the training server -> its answer. wait: how long its answer is read for (the protocol says
    nothing of its end: the read runs out). 30/10: 0.66 s each; a command whose answer nobody reads (the plugin's file
    asks: css_dbglosfile) passes wait=0.02."""
    s = socket.create_connection(("127.0.0.1", PORT), timeout=timeout)

    def send(i, t, body):
        b = struct.pack("<ii", i, t) + body.encode("utf-8") + b"\x00\x00"
        s.sendall(struct.pack("<i", len(b)) + b)

    def exact(n):
        d = b""
        while len(d) < n:
            c = s.recv(n - len(d))
            if not c:
                raise ConnectionError("rcon closed")
            d += c
        return d

    def recv():
        n = struct.unpack("<i", exact(4))[0]
        d = exact(n)
        i, t = struct.unpack("<ii", d[:8])
        return i, t, d[8:-2].decode("utf-8", "replace")

    try:
        send(1, 3, _password())
        while True:
            i, t, _ = recv()
            if t == 2:
                if i == -1:
                    raise PermissionError("rcon password refused")
                break
        send(2, 2, cmd)
        out = []
        s.settimeout(wait)
        try:
            while True:
                out.append(recv()[2])
        except (socket.timeout, ConnectionError):
            pass
        return "".join(out)
    finally:
        s.close()


def _pid_alive(pid):
    if not pid:
        return False
    if os.name != "nt":
        import psutil
        try:
            return config.is_cs2(psutil.Process(int(pid)).name())
        except (psutil.Error, ValueError):
            return False
    # errors replaced: tasklist writes in the console's code page ("Aucune tâche ..."), which a UTF-8 Python (python -X utf8)
    # cannot decode: its output came back None and the start of a server that was up failed (23/10)
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW)
    return "cs2.exe" in (r.stdout or "")


def installed():
    return os.path.exists(EXE) and os.path.isdir(os.path.join(CSGO, "addons", "counterstrikesharp", "plugins", "CoachReplay"))


def heartbeat():
    """The plugin's heartbeat: who is on the server, what is playing (None when the server is down)."""
    try:
        h = json.load(open(os.path.join(COACH, "live.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return h if time.time() - (h.get("t") or 0) < 8 else None


def _beat_age():
    """Seconds since the plugin's last heartbeat (None: never)."""
    try:
        return time.time() - (json.load(open(os.path.join(COACH, "live.json"), encoding="utf-8")).get("t") or 0)
    except (OSError, ValueError):
        return None


def _dead(s):
    """A server that runs without its plugin beating for a minute: no map (a load that failed, 08/10: Aim Botz reloaded
    itself by name and the server was left with nothing), or the plugin gone. Nothing there can be asked anything."""
    if not _pid_alive(s.get("pid")) or time.time() - (s.get("started") or 0) < 120:
        return False
    age = _beat_age()
    return age is None or age > 60


def on_server():
    """You are on the training server right now (the coach's GSI treats it as practice)."""
    h = heartbeat()
    return bool(h and h.get("humans"))


def status():
    s = _state()
    up = _pid_alive(s.get("pid"))
    h = heartbeat() if up else None
    h = h or {}
    return {"installed": installed(), "install": dict(INSTALL), "path": SERVER, "running": up, "dead": up and not h and _dead(s),
            "busy": busy(), "map": (h.get("map") or s.get("map")) if up else None,
            "humans": h.get("humans", 0), "scenario": h.get("scenario"), "state": h.get("state"),
            "session": {k: h.get(k) for k in ("session", "block", "drill", "points", "ok", "done", "streak", "left")} if h.get("session") else None,
            "connect": f"connect 127.0.0.1:{PORT}", "join": dict(JOIN)}


def steps_live(fresh=2.0):
    """A step-by-step drill's four toggles as the plugin wrote them (coach/steps_live.json, 16 times a second; 23/10, the
    user: "afficher les 4 indicateurs du pas à pas aussi dans la page Live"); {} when none is being played now."""
    f = os.path.join(COACH, "steps_live.json")
    try:
        if time.time() - os.path.getmtime(f) > fresh:
            return {}
        with open(f, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _update():
    """After a CS2 update the server copy still links the old files (the game would refuse it): linked again first."""
    sys.path.insert(0, os.path.join(config.HERE, "plugin"))
    import make_server
    if not make_server.current():
        make_server.main()
    make_server.plugin()   # a newer build of the coach's plugin (an update of the app)


INSTALL = {"running": False, "log": None, "error": None}
JOIN = {}   # the game's last way to the server (train._connect): joining, loading, in, refused or failed, and why
# 07/10: Aim Botz (the user's pick, Steam Workshop) for the aim block: the server loads it by its id. The game mounts the
# player's own subscribed copy (a Workshop addon needs no Valve signature, unlike aim_map's old file)
WORKSHOP = {"aim_botz": "3070244462"}
WORKSHOP_BASE = "ar_pool_day"   # the map the server starts on before loading a Workshop one
# what its own config sets, undone before another map (the plugin does the same when a session moves on)
AFTER_WORKSHOP = ["game_type 0", "game_mode 1", "sv_cheats 0", "sv_infinite_ammo 0", "bot_all_weapons", "bot_join_team any",
                  "mp_humanteam any", "mp_respawn_on_death_ct 0", "mp_respawn_on_death_t 0", "weapon_auto_cleanup_time 0",
                  "weapon_max_before_cleanup 0", "mp_free_armor 0", "mp_buy_anywhere 0", "bot_quota 0", "bot_kick"]


def client_workshop(wid):
    """The player's subscribed copy of a Workshop item (its folder in the game's library), or None."""
    try:
        lib = os.path.dirname(os.path.dirname(config.cs2_dir()))   # ...\steamapps
        d = os.path.join(lib, "workshop", "content", "730", str(wid))
        return d if os.path.isdir(d) and any(f.endswith("_dir.vpk") or f.endswith(".vpk") for f in os.listdir(d)) else None
    except Exception:
        return None


def _seed_workshop(wid):
    """The server's copy of a Workshop item from the player's (no download): its files and its line in the server's
    workshop manifest. Without the player's copy the server downloads it itself at host_workshop_map."""
    src = client_workshop(wid)
    if not src:
        return False
    root = os.path.dirname(os.path.dirname(os.path.dirname(CSGO)))   # E:\CS2Server (game\csgo -> root)
    dst = os.path.join(root, "steamapps", "workshop", "content", "730", str(wid))
    os.makedirs(dst, exist_ok=True)
    for f in os.listdir(src):
        a, b = os.path.join(src, f), os.path.join(dst, f)
        if os.path.isfile(a) and (not os.path.exists(b) or os.path.getsize(b) != os.path.getsize(a)):
            shutil.copy2(a, b)   # a copy, not a link: the server's updates never touch the player's files
    acf = os.path.join(root, "steamapps", "workshop", "appworkshop_730.acf")
    item = {"size": "0", "timeupdated": "0", "manifest": "0"}
    try:
        t = open(os.path.join(os.path.dirname(os.path.dirname(src)), "..", "appworkshop_730.acf"), encoding="utf-8", errors="replace").read()
        import re
        m = re.search(r'"%s"\s*\{([^}]*)\}' % wid, t)
        if m:
            for k in item:
                v = re.search(r'"%s"\s*"([^"]*)"' % k, m.group(1))
                if v:
                    item[k] = v.group(1)
    except OSError:
        pass
    if not os.path.exists(acf) or f'"{wid}"' not in open(acf, encoding="utf-8", errors="replace").read():
        open(acf, "w", encoding="utf-8").write(
            '"AppWorkshop"\n{\n\t"appid"\t\t"730"\n\t"SizeOnDisk"\t\t"%s"\n\t"NeedsUpdate"\t\t"0"\n\t"NeedsDownload"\t\t"0"\n'
            '\t"TimeLastUpdated"\t\t"0"\n\t"TimeLastAppRan"\t\t"0"\n\t"LastBuildID"\t\t"0"\n'
            '\t"WorkshopItemsInstalled"\n\t{\n\t\t"%s"\n\t\t{\n\t\t\t"size"\t\t"%s"\n\t\t\t"timeupdated"\t\t"%s"\n\t\t\t"manifest"\t\t"%s"\n\t\t}\n\t}\n'
            '\t"WorkshopItemDetails"\n\t{\n\t\t"%s"\n\t\t{\n\t\t\t"manifest"\t\t"%s"\n\t\t\t"timeupdated"\t\t"%s"\n\t\t\t"timetouched"\t\t"0"\n'
            '\t\t\t"latest_timeupdated"\t\t"%s"\n\t\t\t"latest_manifest"\t\t"%s"\n\t\t}\n\t}\n}\n'
            % (item["size"], wid, item["size"], item["timeupdated"], item["manifest"], wid, item["manifest"], item["timeupdated"], item["timeupdated"], item["manifest"]))
    return True


def install():
    """The training server made on this PC from the app (05/10, the beta: a player without plugin/make_server.py at
    hand): CS2's files linked next to the game (no copy, a few minutes), Metamod, CounterStrikeSharp and the plugin."""
    if not config.linux_training():
        raise RuntimeError(i18n.tr(EXPERIMENTAL))
    if INSTALL["running"]:
        return status()

    def run():
        try:
            sys.path.insert(0, os.path.join(config.HERE, "plugin"))
            import make_server
            make_server.main(log=lambda m: INSTALL.update(log=m))
        except Exception as e:
            INSTALL["error"] = str(e) or type(e).__name__
        finally:
            INSTALL["running"] = False
    INSTALL.update(running=True, error=None, log="Starting…")
    threading.Thread(target=run, daemon=True).start()
    return status()


# one thing at a time on the training server (06/10 19:52: while a warm-up was built, the three photo buttons sent the
# server to Nuke, Anubis and Overpass in one second and sent the game twice more): a warm-up, a photo session or a
# situation claims the server while it starts; another one is refused meanwhile
_BUSY = {"what": None, "t": 0.0}
_BUSY_LOCK = threading.Lock()


def claim(what, ttl=600):
    """True: the server is yours for that start (release() after it); False: another start runs (busy() says which)."""
    with _BUSY_LOCK:
        if _BUSY["what"] and time.time() - _BUSY["t"] < ttl:
            return False
        _BUSY.update(what=what, t=time.time())
        return True


def release():
    with _BUSY_LOCK:
        _BUSY.update(what=None, t=0.0)


def busy():
    return _BUSY["what"] if _BUSY["what"] and time.time() - _BUSY["t"] < 600 else None


def _steamclient_linux():
    """A dedicated server on Linux loads Steam's client library from ~/.steam/sdk64 (the usual setup of a CS2 server):
    linked there from the Steam install when missing. -> what is missing, or None."""
    want = os.path.join(os.path.expanduser("~"), ".steam", "sdk64", "steamclient.so")
    if os.path.exists(want):
        return None
    for src in (os.path.join(config.steam_path(), "linux64", "steamclient.so"),
                os.path.join(SERVER, "game", "bin", "linuxsteamrt64", "steamclient.so")):
        if os.path.exists(src):
            os.makedirs(os.path.dirname(want), exist_ok=True)
            try:
                os.symlink(src, want)
            except FileExistsError:
                pass
            return None
    return "steamclient.so was not found in Steam's folder (linux64): start Steam once, then try again"


def _launch_linux(args):
    """The server in the background on Linux, through the game's own launcher script (cs2.sh sets its libraries) when
    there is one; its output in out/train_server.log; a session of its own (it outlives a page reload, not the app)."""
    miss = _steamclient_linux()
    if miss:
        raise RuntimeError(miss)
    sh = os.path.join(SERVER, "game", "cs2.sh")
    # the script itself, not "sh" it: it is written for bash ([[ ... ]] to spot -dedicated) and /bin/sh is not bash on
    # every distribution (Debian and Ubuntu: dash), where it would not see -dedicated and refuse to start outside Steam
    cmd = ([sh] + args[1:]) if os.access(sh, os.X_OK) else args
    env = dict(os.environ)
    lib = os.path.dirname(EXE)
    env["LD_LIBRARY_PATH"] = lib + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    log = open(LINUX_LOG, "a", encoding="utf-8")
    log.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} {' '.join(c for c in cmd if not c.startswith(_password()))}\n")
    log.flush()
    return subprocess.Popen(cmd, cwd=lib, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True, close_fds=True)


def _linux_pid(pr, secs=30):
    """The server's own pid, not its launcher's: cs2.sh waits on the server (it restarts it when it asks for it), so
    Popen holds a shell, and everything here knows the server by its name ("cs2"). -> the server of that session once
    it is up, else the shell's pid (a launch straight to the binary, or one that went nowhere)."""
    import psutil
    for _ in range(int(secs * 10)):
        try:
            p = psutil.Process(pr.pid)
            for c in [p] + p.children(recursive=True):   # itself first: without cs2.sh Popen already holds the server
                if config.is_cs2(c.name()):
                    return c.pid
        except psutil.Error:
            break
        if pr.poll() is not None:
            break
        time.sleep(0.1)
    return pr.pid


def _kill_port_servers():
    """A dedicated server of this training server's own folder still on its port, whatever its RCON password, stopped
    before another starts (31/10, the battery: the server's state had another password than the one still running, it was
    not taken over, a second one started on 27015, both half alive, sessions with no drill). Never the player's own game
    (no -dedicated), never another folder's server."""
    try:
        import psutil
    except ImportError:
        return
    exe = os.path.normcase(os.path.abspath(EXE))
    for p in psutil.process_iter(["name", "cmdline", "exe"]):
        try:
            cmd = p.info.get("cmdline") or []
            if not cmd or "-dedicated" not in cmd:
                continue
            if os.path.normcase(os.path.abspath(cmd[0])) != exe:
                continue
            port = cmd[cmd.index("-port") + 1] if "-port" in cmd and cmd.index("-port") + 1 < len(cmd) else "27015"
            if str(port) != str(PORT):
                continue
            print(f"training server: an old one still on port {PORT} (pid {p.pid}), stopped first", flush=True)
            p.kill()
            p.wait(10)
        except (psutil.Error, ValueError):
            continue


def _running_pid():
    """A training server of this app's own already up on this PC, whose pid it does not have: the app was restarted, or
    an older one left it behind (before 13/10 its pid was its launcher's on Linux, so stop() never reached it). Taken
    over instead of starting a second one on the same port, which would only crash. Known as ours by the RCON password
    this app gave it (random, kept in its state): a CS2 server of the player's own on that port is never taken over,
    so never stopped by start() either. Not by its folder: on Linux the training server's files are links to the
    game's, the process's executable is the game's own. -> its pid, or None."""
    try:
        import psutil
    except ImportError:
        return None
    pw = _state().get("rcon")
    if not pw:   # no password given yet: no server of ours ever started
        return None
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            cmd = p.info.get("cmdline") or []
            if config.is_cs2(p.info.get("name")) and "-dedicated" in cmd and str(PORT) in cmd and pw in cmd:
                return p.pid
        except psutil.Error:
            continue
    return None


def _above_normal(pid):
    """The server above the app's own work: a build reading the hard disk made it run at half speed (06/10 19:53: frames
    of 20-30 ms, 0.2 ms of them its own). Its console's host (conhost.exe) high: 08/10, his warm-up dropped him seven
    times ("Too many queued messages"); on a loaded PC the server's console writes waited 0.6-0.8 s on a starved conhost,
    frames that long (all 24 cores busy: 17 such frames a minute with conhost normal, none with it high, the server's own
    priority changing nothing). Linux: left as it is (a higher priority needs root)."""
    if config.LINUX:
        return
    try:
        import psutil
        p = psutil.Process(pid)
        if p.nice() != psutil.ABOVE_NORMAL_PRIORITY_CLASS:
            p.nice(psutil.ABOVE_NORMAL_PRIORITY_CLASS)
        config.full_speed(pid)   # hidden, Windows 11 would run it slow and ignore its timer (16/10)
        for c in p.children(recursive=True):
            if c.name().lower() == "conhost.exe" and c.nice() != psutil.HIGH_PRIORITY_CLASS:
                c.nice(psutil.HIGH_PRIORITY_CLASS)
    except Exception as e:
        print("server priority:", e, flush=True)


def _hide_console(pid):
    """The server's console window out of sight. CREATE_NEW_CONSOLE with SW_HIDE no longer hides it (07/10, his warm-up
    video: the server's log over the desktop at each start, where it can take the focus from the game): its window,
    owned by the server's conhost child, is hidden once it shows. Returns how many were hidden. Linux: no window."""
    if config.LINUX:
        return 1
    try:
        import ctypes
        from ctypes import wintypes
        import psutil
        u = ctypes.windll.user32
        pids = {pid} | {c.pid for c in psutil.Process(pid).children(recursive=True)}
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(h, _):
            owner = wintypes.DWORD()
            u.GetWindowThreadProcessId(h, ctypes.byref(owner))
            if owner.value in pids and u.IsWindowVisible(h):
                cls = ctypes.create_unicode_buffer(64)
                u.GetClassNameW(h, cls, 64)
                if cls.value == "ConsoleWindowClass":
                    found.append(h)
            return True
        u.EnumWindows(each, 0)
        for h in found:
            u.ShowWindow(h, 0)   # SW_HIDE
        return len(found)
    except Exception as e:
        print("server console:", e, flush=True)
        return 0


def _in_poly(p, poly):
    """Point in polygon (ray casting) on x, y."""
    x, y, inside, n = float(p[0]), float(p[1]), False, len(poly)
    for i in range(n):
        x1, y1 = float(poly[i][0]), float(poly[i][1])
        x2, y2 = float(poly[(i + 1) % n][0]), float(poly[(i + 1) % n][1])
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def control(**kw):
    """The plugin's control file (coach/control.json, 08/10): "rcon": this app's password, set by the plugin on the
    running server; "quit": the server stops itself (no password, no rights needed: a server run as administrator, or
    one whose password was lost, still obeys)."""
    try:
        json.dump(kw, open(os.path.join(COACH, "control.json"), "w", encoding="utf-8"))
    except OSError as e:
        print("training server control:", e, flush=True)


def write_ui(lang=None):
    """The training server's words in the app's language (13/10): coach/ui.json, read by the plugin when a session or a
    situation starts (i18n.plugin_catalog). Written only when it changes: the plugin reads it again on a new date."""
    try:
        data = json.dumps(i18n.plugin_catalog(lang), ensure_ascii=False, separators=(",", ":"))
        f = os.path.join(COACH, "ui.json")
        try:
            if open(f, encoding="utf-8").read() == data:
                return
        except OSError:
            pass
        os.makedirs(COACH, exist_ok=True)
        with open(f + ".tmp", "w", encoding="utf-8") as o:
            o.write(data)
        os.replace(f + ".tmp", f)
    except (OSError, ValueError) as e:
        print("training server language:", e, flush=True)


def _gone(pid, secs):
    for _ in range(int(secs * 2)):
        if not _pid_alive(pid):
            return True
        time.sleep(0.5)
    return not _pid_alive(pid)


def _force_stop(pid):
    """A server this app can't talk to: asked to stop through the plugin, else killed; RuntimeError when neither works.
    A plugin that doesn't beat can't read the request: killed at once."""
    age = _beat_age()
    control(rcon=_password(), quit=int(time.time()))
    if age is not None and age < 10 and _gone(pid, 15):
        return
    if config.LINUX:
        import signal
        try:
            os.killpg(os.getpgid(int(pid)), signal.SIGKILL)   # its session: cs2.sh and the server
        except (OSError, ValueError):
            try:
                os.kill(int(pid), signal.SIGKILL)
            except (OSError, ValueError):
                pass
    else:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=NO_WINDOW)
    if not _gone(pid, 5):
        raise RuntimeError("The training server doesn't answer and can't be stopped: end 'Counter-Strike 2' (the server, "
                           "not your game) " + ("with your system monitor, or log out" if config.LINUX
                                                else "in the Task Manager, or restart Windows") + ", then try again")


def _answers():
    """True when this app can still talk to its server (the right password, 127.0.0.1 not refused)."""
    try:
        rcon("echo wily", timeout=5.0)
        return True
    except PermissionError:
        return False
    except OSError:   # refused after failed logins: the server says nothing
        return False


# touched while the server loads a map (17/10: three starts past 120 s while the demo copies to Drive read the same
# disk): tools/archive_demos.py waits meanwhile
LOADING = os.path.join(config.OUT, "training_loading" if PORT == 27015 else f"training_loading_{PORT}")


def start(mp):
    """The server on this map (started hidden, or its map changed); back when it answers."""
    try:
        with open(LOADING, "w", encoding="utf-8") as f:
            f.write(mp)
    except OSError:
        pass
    try:
        return _start(mp)
    finally:
        try:
            os.remove(LOADING)
        except OSError:
            pass


def _start(mp):
    if not config.linux_training():
        raise RuntimeError(i18n.tr(EXPERIMENTAL))
    if not installed():
        raise RuntimeError("The training server is not installed yet: install it from the Prepare page")
    pw = _password()   # made and saved before the state is read (08/10)
    s = _state()
    h0 = heartbeat() or {}
    if not _pid_alive(s.get("pid")):
        found = _running_pid()   # one of ours already up: taken over (a second one on the same port would only crash)
        if found:
            print(f"training server: already up (pid {found}), taken over", flush=True)
            s.update(pid=found, map=h0.get("map") or s.get("map"), started=s.get("started") or time.time())
            _save_state(s)
    if _dead(s):
        print(f"training server: no heartbeat for {_beat_age() or 0:.0f} s (no map?), started again", flush=True)
        _force_stop(s["pid"])
        s.pop("pid", None)
        _save_state(s)
    elif _pid_alive(s.get("pid")) and not h0.get("humans") and not _answers():   # nobody on it, and it won't listen: again
        print("training server: it refuses this app's RCON, started again", flush=True)
        _force_stop(s["pid"])
        s.pop("pid", None)
        _save_state(s)
    wid = WORKSHOP.get(mp)
    if wid:
        _seed_workshop(wid)
    if _pid_alive(s.get("pid")):
        _above_normal(s["pid"])   # a server an older app started: its console's host high too (08/10)
        if s.get("map") != mp:
            if s.get("map") in WORKSHOP and not wid:
                for c in AFTER_WORKSHOP:
                    rcon(c)
            rcon(f"host_workshop_map {wid}" if wid else f"changelevel {mp}")
            s["map"] = mp
            _save_state(s)
            time.sleep(8)
            if wid:
                _wait_map(mp)
        return status()
    _update()
    _kill_port_servers()   # never a second one on its port
    log = os.path.join(CSGO, "addons", "metamod", "console.log")   # -condebug's, written again at each start: the last
    try:                                                          # run's kept (23/10: a server gone with no dump, its
        shutil.copy2(log, log[:-4] + ".prev.log")                 # words lost to the next start)
    except OSError:
        pass
    args = [EXE, "-dedicated", "-usercon", "-ip", "127.0.0.1", "-port", str(PORT), "-condebug", "-nohltv",
            "+sv_lan", "1", "+rcon_password", _password(), "+game_type", "0", "+game_mode", "1",
            "+map", WORKSHOP_BASE if wid else mp]   # a Workshop map only once the server runs: given at launch it is ignored (07/10)
    if config.LINUX:
        pr = _launch_linux(args)
        pid = _linux_pid(pr)   # the server behind cs2.sh: the pid this app keeps, and the one it can recognise later
    else:
        si = subprocess.STARTUPINFO()   # its own console, hidden: without one the server logs a console error every frame
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0   # SW_HIDE: never shown, never takes the focus
        pr = subprocess.Popen(args, cwd=os.path.dirname(EXE), creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=si)
        pid = pr.pid
    _above_normal(pid)
    for _ in range(20):   # its console comes up within a second or two
        if _hide_console(pid):
            break
        time.sleep(0.1)
    s.update(pid=pid, map=mp, started=time.time())
    _save_state(s)
    control(rcon=pw)   # the plugin sets it too: the server and this app always agree on it
    # rcon only once the map runs (the plugin's heartbeat): an early try counts as a failed login and the server then
    # refuses 127.0.0.1
    for _ in range(120):
        time.sleep(1)
        _hide_console(pid)   # shown again while the server starts: hidden again
        _above_normal(pid)   # its console's host comes up meanwhile: high
        if pr.poll() is not None:   # before the heartbeat: a server that stopped is not the one beating
            raise RuntimeError("the training server stopped while starting"
                               + (f" (what it said: {LINUX_LOG})" if config.LINUX else ""))
        h = heartbeat()
        if h and (h.get("t") or 0) > s["started"]:
            if wid:   # up on the base map: now the Workshop one
                rcon(f"host_workshop_map {wid}")
                _wait_map(mp)
            return status()
    raise RuntimeError("the training server did not start in 120 s")


def _wait_map(mp, secs=90):
    """The plugin's heartbeat on that map (a Workshop map loads in 20-30 s)."""
    t0 = time.time()
    while time.time() - t0 < secs:
        time.sleep(1)
        h = heartbeat() or {}
        if h.get("map") == mp and (h.get("t") or 0) > t0:
            return True
    print("training server: still not on", mp, "after", secs, "s", flush=True)
    return False


def stop():
    s = _state()
    pid = s.get("pid")
    if _pid_alive(pid):
        dead = _dead(s)   # no map: nothing answers there, killed at once
        if not dead:
            try:
                rcon("quit")
            except OSError:   # PermissionError too: a server that won't listen is asked through the plugin (08/10)
                pass
        if dead or not _gone(pid, 5):
            try:
                _force_stop(pid)
            except RuntimeError as e:
                print("training server:", e, flush=True)
    s.pop("pid", None)
    _save_state(s)
    return status()


def keep():
    """Used with nobody on it (tools/train_selftest.py plays its sessions alone): the idle stop below waits. 17/10: it
    stopped the self-test's server every 20 minutes, in the middle of a drill or of a map change (76 crash dumps since
    03/10, all its quit: CounterStrikeSharp's exit after the engine's)."""
    s = _state()
    s["seen"] = time.time()
    _save_state(s)


def idle_check(after=20 * 60):
    """Stops the server when nobody has been on it for 20 minutes (it holds about 1 GB of memory)."""
    s = _state()
    if not s.get("pid") or not _pid_alive(s.get("pid")):
        return
    h = heartbeat()
    now = time.time()
    if h and h.get("humans"):
        s["seen"] = now
        _save_state(s)
    elif now - max(s.get("seen") or 0, s.get("started") or 0) > after:
        stop()


def play(sid, mid, rnd, kind="death", mode="actor", diff=2):
    """Build the scenario, the server on its map, and tell the plugin: it starts as soon as you are in (or now)."""
    sc = build(sid, mid, rnd, kind)
    write_ui()
    start(sc["map"])
    rcon(f"css_replay {sc['id']} {mode} {max(0, min(3, int(diff)))}")
    return {**status(), "scenario": {k: sc[k] for k in ("id", "title", "map", "round", "kind")}}


def results():
    """Every try, per scenario: tries, wins, last outcome."""
    out = {}
    try:
        lines = open(os.path.join(COACH, "results.jsonl"), encoding="utf-8").read().splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        e = out.setdefault(r.get("id"), {"tries": 0, "won": 0, "survived": 0, "last": None, "kills": 0, "watched": 0})
        if r.get("mode") == "spec":   # watched: a bot played your spot
            e["watched"] += 1
            continue
        e["tries"] += 1
        e["won"] += r.get("outcome") in ("won", "traded", "kill")   # a kill or a trade: a success (04/10)
        e["survived"] += r.get("outcome") == "survived" and (r.get("kills") or 0) >= 1
        e["kills"] += r.get("kills") or 0
        e["last"] = r.get("outcome")
    return out
