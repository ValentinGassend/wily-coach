"""One pass over the base's demos for what needs the demo itself (06/10): the players standing on a teammate (boosts)
and every kill with where both players stood, through a wall or not (wallbangs).

A boost is read from the game's own ground entity (CCSPlayerPawn.m_hGroundEntity: what a player stands on), not
guessed from heights: a ladder, the Nuke vent or players crowding a spawn stack players too, but none of them stand on
a teammate's head. Samples every 8 ticks; a boost is kept as an episode (who, on whom, from when to when, where, where
the top player looked). Kills: player_death with both positions, the attacker's view, the walls it went through.

Cached per demo in out/population/scan/<match>.json (a match is read once). boosts.py and wallbangs.py read them.
Usage: python -m wily.demos.scan [map ...] (all the maps with demos by default, the 150 most recent of each)."""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

from wily.core import config

OUT = os.path.join(config.OUT, "population", "scan")
STEP = 8
PER_MAP = 150
V = 1


def demos(mp, n=PER_MAP):
    from wily.insights import tside
    ds = tside._map_dirs().get(mp, [])
    ds = [os.path.basename(d) for d in ds if config.has_demo(os.path.basename(d))]
    return sorted(ds, key=lambda d: -int(d))[:n]


def path(mid):
    return os.path.join(OUT, f"{mid}.json")


def load(mid):
    try:
        with open(path(mid), encoding="utf-8") as f:
            d = json.load(f)
        return d if d.get("v") == V else None
    except (OSError, ValueError):
        return None


def _r(v, n=1):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v != v else round(v, n)


def scan_demo(mid, src=None):
    """The boosts and the kills of one demo (cached). src: a copy of the demo to read instead (run(): on the SSD)."""
    got = load(mid)
    if got:
        return got
    from demoparser2 import DemoParser
    p = DemoParser(src or config.demo(mid))
    T = p.parse_ticks(["CCSPlayerPawn.m_hGroundEntity", "CCSPlayerController.m_hPlayerPawn", "X", "Y", "Z", "yaw", "pitch", "team_num",
                       "is_alive", "last_place_name", "total_rounds_played", "ducking"], ticks=list(range(0, 700000, STEP)))
    T = T.rename(columns={"CCSPlayerPawn.m_hGroundEntity": "g", "CCSPlayerController.m_hPlayerPawn": "pawn"})
    T["steamid"] = T.steamid.astype(str)
    pawns = set(T.pawn.dropna().astype("int64").unique())
    on = T[T.g.isin(pawns) & T.is_alive.astype(bool)]
    boosts = []
    if len(on):
        own = T[["tick", "pawn", "steamid", "X", "Y", "Z", "team_num", "ducking", "is_alive"]].rename(
            columns={"pawn": "g", "steamid": "base", "X": "bx", "Y": "by", "Z": "bz", "team_num": "bteam", "ducking": "bduck", "is_alive": "balive"})
        M = on.merge(own, on=["tick", "g"])
        M = M[(M.team_num == M.bteam) & (M.steamid != M.base) & M.balive.astype(bool)]   # on a living teammate's head
        for (top, base), g in M.groupby(["steamid", "base"]):
            g = g.sort_values("tick")
            tk = g.tick.to_numpy()
            for part in np.split(np.arange(len(g)), np.where(np.diff(tk) > STEP * 3)[0] + 1):
                e = g.iloc[part]
                P = e[["X", "Y", "Z"]].to_numpy(float)
                B = e[["bx", "by", "bz"]].to_numpy(float)
                pm, bm = np.median(P, axis=0), np.median(B, axis=0)
                yw = np.radians(e.yaw.to_numpy(float))
                boosts.append({"top": str(top), "base": str(base), "team": int(e.team_num.iloc[0]), "round": int(e.total_rounds_played.iloc[0]) + 1,
                               "t0": int(tk[part[0]]), "t1": int(tk[part[-1]]),
                               "pos": [round(float(v), 1) for v in pm], "bpos": [round(float(v), 1) for v in bm],
                               "move": round(float(np.max(np.hypot(B[:, 0] - bm[0], B[:, 1] - bm[1]))), 1),
                               "tmove": round(float(np.max(np.hypot(P[:, 0] - pm[0], P[:, 1] - pm[1]))), 1),
                               "dz": round(float(pm[2] - bm[2]), 1), "bduck": bool(e.bduck.astype(bool).mean() > 0.5),
                               "yaw": round(float(np.degrees(np.arctan2(np.sin(yw).mean(), np.cos(yw).mean()))), 1),
                               "pitch": round(float(e.pitch.median()), 1),
                               "place": str(e.last_place_name.mode().iloc[0]) if e.last_place_name.notna().any() else ""})
    kills = []
    try:
        K = p.parse_event("player_death", player=["X", "Y", "Z", "pitch", "yaw", "team_num", "last_place_name"])
    except Exception:
        K = None
    if isinstance(K, pd.DataFrame) and len(K):
        for r in K.itertuples():
            a, u = getattr(r, "attacker_steamid", None), getattr(r, "user_steamid", None)
            kills.append([int(r.tick), "" if a is None or a != a else str(a), "" if u is None or u != u else str(u), str(getattr(r, "weapon", "") or ""),
                          int(getattr(r, "penetrated", 0) or 0), bool(getattr(r, "headshot", False)),
                          _r(getattr(r, "attacker_X", None)), _r(getattr(r, "attacker_Y", None)), _r(getattr(r, "attacker_Z", None)),
                          _r(getattr(r, "attacker_pitch", None), 2), _r(getattr(r, "attacker_yaw", None), 2),
                          _r(getattr(r, "attacker_team_num", None), 0), str(getattr(r, "attacker_last_place_name", "") or ""),
                          _r(getattr(r, "user_X", None)), _r(getattr(r, "user_Y", None)), _r(getattr(r, "user_Z", None)),
                          _r(getattr(r, "user_team_num", None), 0), str(getattr(r, "user_last_place_name", "") or "")])
    out = {"v": V, "match": mid, "boosts": boosts, "kills": kills,
           "kcols": ["tick", "attacker", "victim", "weapon", "penetrated", "headshot", "ax", "ay", "az", "apitch", "ayaw", "ateam", "aplace",
                     "vx", "vy", "vz", "vteam", "vplace"]}
    os.makedirs(OUT, exist_ok=True)
    tmp = path(mid) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    os.replace(tmp, path(mid))
    return out


def kills(mid):
    """A scanned demo's kills as a table (None when it is not scanned)."""
    d = load(mid)
    if not d:
        return None
    return pd.DataFrame(d["kills"], columns=d["kcols"]).assign(match=mid)


def _one(mid, low=True, src=None):
    if low:   # the CPU the game doesn't use (a run while he plays); his go (06/10, "je ne joue pas"): full speed
        config.low_priority()
    t = time.time()
    try:
        d = scan_demo(mid, src)
        return mid, len(d["boosts"]), len(d["kills"]), round(time.time() - t, 1), None
    except Exception as e:
        return mid, 0, 0, round(time.time() - t, 1), str(e)[:200]
    finally:
        if src and os.path.dirname(src) == TMP:
            try:
                os.remove(src)
            except OSError:
                pass


TMP = os.path.join(os.environ.get("TEMP") or os.path.expanduser("~"), "wily_scan")   # on the SSD (C:) here


def run(maps=None, workers=3, per_map=PER_MAP, low=True, log=print):
    """The maps' demos not scanned yet. The demos sit on a hard disk (06/10: 200 MB each; 10 parsers reading them at once
    made the disk seek all the time: 17 demos a minute, 1.3 cores busy of 24): one thread copies them one after the
    other (one sequential read, the disk's best) to the SSD, the workers parse the copies and delete them; a few copies
    ahead at most."""
    import queue
    import shutil
    import threading
    from wily.insights import tside
    from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
    os.makedirs(TMP, exist_ok=True)
    for f in os.listdir(TMP):   # copies left by a stopped run
        try:
            os.remove(os.path.join(TMP, f))
        except OSError:
            pass
    todo_maps = maps or [m for m, ds in sorted(tside._map_dirs().items(), key=lambda kv: -len(kv[1])) if len(ds) >= 10]
    with ProcessPoolExecutor(workers) as ex:
        for mp in todo_maps:
            ds = [d for d in demos(mp, per_map) if not load(d)]
            t0, tot = time.time(), {"b": 0, "k": 0, "bad": 0}
            q = queue.Queue(maxsize=4)

            def copier():
                for mid in ds:
                    src, dst = config.demo(mid), os.path.join(TMP, mid + ".dem")
                    try:
                        shutil.copyfile(src, dst)
                    except OSError:
                        dst = src   # no room on the SSD: read it where it is
                    q.put((mid, dst))
                q.put(None)
            threading.Thread(target=copier, daemon=True).start()

            def take(fs):
                for f in fs:
                    mid, b, k, s_, err = f.result()
                    tot["b"] += b
                    tot["k"] += k
                    tot["bad"] += bool(err)
            pending = set()
            while True:
                item = q.get()
                if item is None:
                    break
                pending.add(ex.submit(_one, item[0], low, item[1]))
                while len(pending) >= workers + 2:
                    done_, pending = wait(pending, return_when=FIRST_COMPLETED)
                    take(done_)
            take(pending)
            log(f"{mp}: {len(demos(mp, per_map))} demos scanned ({len(ds)} new: {tot['b']} boost episodes, {tot['k']} kills, {tot['bad']} unreadable) in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    # python -m wily.demos.scan [map ...] [--all] [--fast]: --all every demo of a map (not the 150 most recent), --fast normal priority
    # and 10 workers (nobody playing)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fast = "--fast" in sys.argv
    if not fast:
        config.low_priority()
    run(args or None, workers=10 if fast else 3, per_map=100000 if "--all" in sys.argv else PER_MAP, low=not fast)
