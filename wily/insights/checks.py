"""The angles you leave unchecked (06/10, the user during a bot match: "mets des bots aux endroits qui sont joués et que
je ne check jamais dans mes démos: cette position est souvent jouée et je la check très peu").

For each map: the CT spots the base plays most around the sites (train.site_data: each with the places it was fought
from, so the places it is seen from). In your demos as T, every round you stand in sight of a spot (within 150 u of a
place it is seen from, same floor) for half a second or more, does your crosshair go to it (within 12 degrees of the
line from your eyes to its head height)? A spot you stand in sight of in many rounds and look at in few is an angle you
leave unchecked: the training puts its prefire bots there first (train.practice_drills).

Your view: your demos, every 4 ticks. Cached in out/players/<you>/checks.json, made again when you have new demos.
Usage: python -m wily.insights.checks <steamid> [map ...]"""
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

from wily.core import config

STEP = 4
NEAR, DZ, AIM_YAW, AIM_PITCH, MIN_ROUNDS = 150.0, 110.0, 12.0, 15.0, 4


def _file(sid):
    return os.path.join(config.player_dir(sid), "checks.json")


def _my_views(sid, mid):
    """Your position and view in one demo, as T and alive: [round, x, y, z, yaw, pitch] every 4 ticks."""
    from demoparser2 import DemoParser
    p = DemoParser(config.demo(mid))
    T = p.parse_ticks(["X", "Y", "Z", "yaw", "pitch", "is_alive", "team_num", "total_rounds_played"], ticks=list(range(0, 700000, STEP)))
    T = T[(T.steamid.astype(str) == str(sid)) & T.is_alive.astype(bool) & (T.team_num == 2)]
    return T.assign(round=T.total_rounds_played + 1)[["round", "X", "Y", "Z", "yaw", "pitch"]].to_numpy(float)


def analyze_map(sid, mp, log=print):
    from wily.training import train
    S = train.site_data(mp)
    holds = []
    for z, s in (S.get("sites") or {}).items():
        for h in train._site_holds(s):
            if len(h.get("seen") or []) >= 4:
                holds.append(dict(h, site=train.replay_zone(z, mp)))
    if not holds:
        return []
    mids = [m for m, mp_ in train._my_matches(str(sid), mp) if config.has_demo(m)]
    stat = [{"in": set(), "look": set()} for _ in holds]
    t0 = time.time()
    for mid in mids:
        try:
            V = _my_views(sid, mid)
        except Exception as e:
            log(f"{mid}: unreadable ({e})")
            continue
        if not len(V):
            continue
        for i, h in enumerate(holds):
            Q = np.array(h["seen"], float).reshape(-1, 3)
            d = np.hypot(V[:, None, 1] - Q[None, :, 0], V[:, None, 2] - Q[None, :, 1]).min(1)
            dz = np.abs(V[:, None, 3] - Q[None, :, 2]).min(1)
            insight = (d < NEAR) & (dz < DZ)
            if not insight.any():
                continue
            W = V[insight]
            hx, hy, hz = h["pos"][0], h["pos"][1], h["pos"][2] + 56   # its head
            yaw = np.degrees(np.arctan2(hy - W[:, 2], hx - W[:, 1]))
            pitch = -np.degrees(np.arctan2(hz - (W[:, 3] + 64), np.hypot(hx - W[:, 1], hy - W[:, 2])))
            look = (np.abs(((W[:, 4] - yaw) + 180) % 360 - 180) < AIM_YAW) & (np.abs(W[:, 5] - pitch) < AIM_PITCH)
            for r in np.unique(W[:, 0]):
                m = W[:, 0] == r
                if m.sum() * STEP / 64 >= 0.5:   # half a second in its sight, that round
                    stat[i]["in"].add((mid, int(r)))
                    if look[m].any():
                        stat[i]["look"].add((mid, int(r)))
    out = []
    for h, st in zip(holds, stat):
        n_in, n_look = len(st["in"]), len(st["look"])
        if n_in >= MIN_ROUNDS:
            out.append({"pos": h["pos"], "zone": h.get("zone"), "site": h["site"], "played": h["n"], "rounds_in_sight": n_in,
                        "checked": round(100 * n_look / n_in)})
    out.sort(key=lambda x: (x["checked"], -x["played"]))
    log(f"{mp}: {len(out)} angles you stood in sight of ({len(mids)} demos, {time.time() - t0:.0f} s)")
    return out


def run(sid, maps=None, log=print):
    from wily.training import train
    f = _file(sid)
    try:
        cur = json.load(open(f, encoding="utf-8"))
    except (OSError, ValueError):
        cur = {}
    todo = maps or [m for m in train.maps(sid) if m.startswith("de_")]
    for mp in todo:
        try:
            cur[mp] = {"t": time.time(), "n": len(train._my_matches(str(sid), mp)), "angles": analyze_map(sid, mp, log)}
        except Exception as e:
            log(f"{mp}: checks unavailable ({e})")
        config.write_json(f, cur)
    return cur


def unchecked(sid, mp, at_most=40):
    """The angles of a map you check in at most 40% of the rounds you stand in sight of them, the most played first."""
    try:
        d = (json.load(open(_file(sid), encoding="utf-8")).get(mp) or {}).get("angles") or []
    except (OSError, ValueError):
        return []
    return sorted([a for a in d if a["checked"] <= at_most], key=lambda a: -a["played"])


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2:] or None)
