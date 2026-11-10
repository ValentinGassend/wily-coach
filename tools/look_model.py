"""Where players look when they see no enemy (29/10, the user: "ce qui joue énormément sur définir les bots comme des
cheaters, comme des humains ou comme l'IA de CS, c'est ... là où ils regardent sans voir des ennemis ... base-toi sur
toutes les analyses de toutes les démos ... en fonction de là où est-ce qu'ils sont et de ce qui se passe sur la carte ...
stuff ... alliés ... ennemis ... points rouges ... bruit qu'ils entendent").

Every 0.25 s of a live round, each living player who sees no enemy (the game's spotting): his place (a 128 u cell, his
side), what he could know then, and where he looked (yaw, pitch). What he could know:
- "dot": an enemy on his radar, spotted by one of his team in the last 2 s, not by him: the nearest one's direction;
- "heard": an enemy he could hear (running within 1100 u, or a shot within 2000 u, in the last 1.5 s): its direction;
- "smoke": a smoke up within 1200 u: its direction;
- "planted": the bomb down, and its direction;
- "none": nothing of that.
A knowledge's direction is kept in 8 sectors of 45 deg. What players do in each (cell, side, knowledge, sector): their
yaw in 36 bins of 10 deg (with the mean pitch of each bin). The plugin's bots look where most players looked there.

Usage: python tools/look_model.py <demo or folder> [...]   ->   out/knowledge/look_model/<map>.json (counts added up)
"""
import glob
import json
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np
from demoparser2 import DemoParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wily.core import config  # noqa: E402

OUT = os.path.join(config.OUT, "knowledge", "look_model")
STEP = 16          # ticks between two samples (0.25 s at 64)
CELL = 128.0
DOT_S, HEAR_S = 2.0, 1.5
RUN_SPEED, STEP_RANGE, SHOT_RANGE, SMOKE_RANGE = 135.0, 1100.0, 2000.0, 1200.0
SMOKE_S = 18.0


def sid_(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def sector(dx, dy):
    return int(((math.degrees(math.atan2(dy, dx)) + 360.0 + 22.5) % 360.0) // 45.0)


def cell_key(side, x, y, z):
    return f"{side}|{int(x // CELL)}|{int(y // CELL)}|{int(z // 96)}"


def demo_samples(path):
    p = DemoParser(path)
    hdr = p.parse_header()
    mp = hdr.get("map_name") or "?"
    ev = dict(p.parse_events(["round_freeze_end", "round_end", "weapon_fire", "smokegrenade_detonate", "bomb_planted"],
                             player=["X", "Y", "Z"]))
    fe = sorted(int(t) for t in ev.get("round_freeze_end", {"tick": []})["tick"]) if "round_freeze_end" in ev else []
    re_ = sorted(int(t) for t in ev.get("round_end", {"tick": []})["tick"]) if "round_end" in ev else []
    live = []
    for a in fe:
        b = next((r for r in re_ if r > a), None)
        if b:
            live.append((a, b))
    if not live:
        return mp, []
    ticks = sorted({t for a, b in live for t in range(a, b, STEP)})
    df = p.parse_ticks(["X", "Y", "Z", "yaw", "pitch", "team_num", "is_alive", "approximate_spotted_by"], ticks=ticks)
    df["steamid"] = df.steamid.map(sid_)
    by_tick = defaultdict(list)
    for r in df.itertuples():
        if not r.is_alive or r.team_num not in (2, 3):
            continue
        sb = r.approximate_spotted_by
        by_tick[int(r.tick)].append((r.steamid, int(r.team_num), float(r.X), float(r.Y), float(r.Z), float(r.yaw), float(r.pitch),
                                     {sid_(x) for x in sb} if isinstance(sb, (list, np.ndarray)) else set()))
    shots = []
    if "weapon_fire" in ev:
        w = ev["weapon_fire"]
        for r in w.itertuples():
            shots.append((int(r.tick), sid_(r.user_steamid), float(r.user_X), float(r.user_Y)))
    smokes = []
    if "smokegrenade_detonate" in ev:
        for r in ev["smokegrenade_detonate"].itertuples():
            smokes.append((int(r.tick), float(r.x), float(r.y)))
    plants = []
    if "bomb_planted" in ev:
        for r in ev["bomb_planted"].itertuples():
            plants.append((int(r.tick), float(r.user_X), float(r.user_Y)))
    pos = {(t, r[0]): (r[2], r[3], r[4]) for t, rows_ in by_tick.items() for r in rows_}   # each living player's place, each sample
    team_of = {}
    prev = {}
    spotted_at = {}   # enemy steamid -> (tick, x, y, the team that spotted it)
    out = []
    for t in ticks:
        rows = by_tick.get(t, [])
        if not rows:
            continue
        for sid, team, x, y, z, yaw, pitch, sb in rows:
            team_of[sid] = team
        # who is on whose radar now: spotted by any living player of the other team
        for sid, team, x, y, z, yaw, pitch, sb in rows:
            if any(team_of.get(o) not in (None, team) for o in sb):
                spotted_at[sid] = (t, x, y, sb)
        speed = {}
        for sid, team, x, y, z, yaw, pitch, sb in rows:
            if sid in prev:
                pt, px, py = prev[sid]
                speed[sid] = math.hypot(x - px, y - py) * 64.0 / max(1, t - pt)
            prev[sid] = (t, x, y)
        rnd = next(((a, b) for a, b in live if a <= t < b), None)
        for sid, team, x, y, z, yaw, pitch, sb in rows:
            # he sees an enemy now: a fight, not where one looks waiting
            if any(r2[1] != team and sid in r2[7] for r2 in rows):
                continue
            know, dx, dy = "none", 0.0, 0.0
            # an enemy on his radar (spotted by his team, not by him), the nearest
            best = None
            for e, (st, ex, ey, esb) in spotted_at.items():
                # an enemy his team spotted (one of them saw it), he himself not
                if team_of.get(e) in (None, team) or t - st > DOT_S * 64 or sid in esb or not any(team_of.get(o) == team for o in esb):
                    continue
                if not any(row[0] == e for row in rows):
                    continue
                d = math.hypot(ex - x, ey - y)
                if best is None or d < best[0]:
                    best = (d, ex - x, ey - y)
            if best:
                know, dx, dy = "dot", best[1], best[2]
            else:
                heard = None
                for e, te, ex, ey, *_ in rows:
                    if te == team or speed.get(e, 0.0) < RUN_SPEED:
                        continue
                    d = math.hypot(ex - x, ey - y)
                    if d < STEP_RANGE and (heard is None or d < heard[0]):
                        heard = (d, ex - x, ey - y)
                for st, ss, sx, sy in shots:
                    if 0 <= t - st <= HEAR_S * 64 and team_of.get(ss) not in (None, team):
                        d = math.hypot(sx - x, sy - y)
                        if d < SHOT_RANGE and (heard is None or d < heard[0]):
                            heard = (d, sx - x, sy - y)
                if heard:
                    know, dx, dy = "heard", heard[1], heard[2]
                else:
                    pl = next(((px, py) for pt, px, py in plants if rnd and rnd[0] <= pt <= t), None)
                    sm = None
                    for st, sx, sy in smokes:
                        if 0 <= t - st <= SMOKE_S * 64:
                            d = math.hypot(sx - x, sy - y)
                            if d < SMOKE_RANGE and (sm is None or d < sm[0]):
                                sm = (d, sx - x, sy - y)
                    if pl:
                        know, dx, dy = "planted", pl[0] - x, pl[1] - y
                    elif sm:
                        know, dx, dy = "smoke", sm[1], sm[2]
            # 29/10, the user: "te nourrir encore beaucoup plus de ce que font les vrais joueurs ... pour diriger les adversaires,
            # mais aussi les alliés": what he did next, from there in that case. His move over the next second (held: under
            # 35 u; walked: under 140 u; ran), its direction; his way over the next 4 s (a sample each 0.25 s)
            p1 = pos.get((t + 4 * STEP, sid))
            mv = None
            if p1:
                d1 = math.hypot(p1[0] - x, p1[1] - y)
                mv = "h" if d1 < 35.0 else ("w" if d1 < 140.0 else "r") + str(sector(p1[0] - x, p1[1] - y))
            seg = []
            for k in range(1, 17):
                q = pos.get((t + k * STEP, sid))
                if q is None:
                    break
                seg.append((round(q[0]), round(q[1]), round(q[2])))
            mates = sum(1 for r2 in rows if r2[1] == team)
            foes = sum(1 for r2 in rows if r2[1] != team)
            adv = (mates > foes) - (mates < foes)
            phase = 0 if not rnd or t - rnd[0] < 25 * 64 else (1 if t - rnd[0] < 60 * 64 else 2)
            out.append((cell_key("T" if team == 2 else "CT", x, y, z), know, sector(dx, dy) if know != "none" else -1,
                        int(((yaw + 360.0) % 360.0) // 10.0), pitch, mv, adv, phase, seg))
    return mp, out


def add(model, samples):
    for cell, know, sec, ybin, pitch, *_ in samples:
        k = f"{cell}|{know}|{sec}"
        e = model.setdefault(k, {"n": 0, "yaw": [0] * 36, "pitch": [0.0] * 36})
        e["n"] += 1
        e["yaw"][ybin] += 1
        e["pitch"][ybin] += pitch


def export(mp, least=4):
    """The plugin's table for a map: each (cell, side, knowledge, sector) seen `least` times or more -> the yaw most players
    had there (the middle of its 10 deg bin) and their mean pitch in it, with the count. In the training server's coach
    folder (look/<map>.json), read when a drill starts."""
    from wily.training import replay
    fn = os.path.join(OUT, f"{mp}.json")
    if not os.path.exists(fn):
        return 0
    m = json.load(open(fn, encoding="utf-8"))
    tab = {}
    for k, e in m["cells"].items():
        if e["n"] < least:
            continue
        # the four most looked-at bins (a tie: the first, the same each time), each [yaw, pitch, count] (29/10: the bot weighs
        # them with the danger there and what its teammates watch already, Look.cs)
        top = sorted(range(36), key=lambda i: (-e["yaw"][i], i))[:4]
        tab[k] = [e["n"], [[b * 10 + 5 - (360 if b * 10 + 5 > 180 else 0), round(e["pitch"][b] / max(1, e["yaw"][b]), 1), e["yaw"][b]]
                           for b in top if e["yaw"][b] > 0]]
    d = os.path.join(replay.COACH, "look")
    os.makedirs(d, exist_ok=True)
    json.dump({"cell": CELL, "zcell": 96, "v": 2, "keys": tab}, open(os.path.join(d, f"{mp}.json"), "w", encoding="utf-8"))
    return len(tab)


def main(paths):
    files = []
    for a in paths:
        files += sorted(glob.glob(os.path.join(a, "*.dem"))) if os.path.isdir(a) else [a]
    os.makedirs(OUT, exist_ok=True)
    models = {}
    tmp = os.path.join(config.CACHE, "look_tmp")
    os.makedirs(tmp, exist_ok=True)
    for f in files:
        t0 = time.time()
        local, dl = f, ""
        if not os.path.abspath(f).upper().startswith(os.path.abspath(config.HERE).upper()[:2]):
            # 29/10: a demo on Google Drive (G:) read straight by the parser (it maps the file) killed the process ("Windows
            # fatal exception: page error", no traceback): copied to the hard disk first, a real download, then read
            import shutil
            local = os.path.join(tmp, os.path.basename(f))
            try:
                shutil.copyfile(f, local)
            except OSError as e:
                print(os.path.basename(f), "not copied:", e, flush=True)
                continue
            mb = os.path.getsize(local) / 1e6
            dl = f", {mb:.0f} MB in {time.time() - t0:.0f} s ({mb / max(0.1, time.time() - t0):.1f} MB/s)"
        try:
            mp, s = demo_samples(local)
        except Exception as e:   # a demo the parser refuses: the others still count
            print(os.path.basename(f), "skipped:", e, flush=True)
            continue
        finally:
            if local != f:
                try:
                    os.remove(local)
                except OSError:
                    pass
        if mp not in models:
            fn = os.path.join(OUT, f"{mp}.json")
            models[mp] = json.load(open(fn, encoding="utf-8")) if os.path.exists(fn) else {"demos": [], "cells": {}}
        m = models[mp]
        # its name: a demo's file name, or a Drive cache file's place in the cache (29/10: numbers, the same in two folders)
        name = os.path.basename(f) if f.lower().endswith(".dem") else "/".join(os.path.normpath(f).split(os.sep)[-3:])
        if name in m["demos"]:
            print(name, "already in", mp, flush=True)
            continue
        add(m["cells"], s)
        m["demos"].append(name)
        json.dump(m, open(os.path.join(OUT, f"{mp}.json"), "w", encoding="utf-8"))   # saved each demo (29/10: a crash lost 4)
        print(f"{name} {mp}: {len(s)} looks ({time.time() - t0:.0f} s{dl})", flush=True)
    for mp, m in models.items():
        json.dump(m, open(os.path.join(OUT, f"{mp}.json"), "w", encoding="utf-8"))
        kinds = defaultdict(int)
        for k, e in m["cells"].items():
            kinds[k.split("|")[4]] += e["n"]
        print(mp, len(m["demos"]), "demos,", len(m["cells"]), "keys,", dict(kinds), flush=True)
        print(mp, "exported:", export(mp), "keys", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or [os.path.join("E:" + os.sep, "SteamLibrary", "steamapps", "common", "Counter-Strike Global Offensive", "game", "csgo", "replays")])
