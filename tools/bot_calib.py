"""How players of your level fight, from your matches' demos (28/10, the user: bots that play "comme un vrai joueur ...
avec un temps de réaction réaliste, sans wallhack, sans vue à travers les smokes ... pas non plus trop nul"): the numbers
the plugin's own bots fight with instead of the game's AI.

For each duel opened (a player's first hit on an enemy, none in the 3 s before): when the game first had the enemy
spotted by him (approximate_spotted_by: no wall, no smoke), his first shot and first hit after it, how far his crosshair
was off the enemy's head then, his speed at the shot (stopped or moving), the distance, the weapon, the hit group, and the
shots he fired till the kill. Every player of your lobbies counted (your level), you apart.

Usage: python tools/bot_calib.py [n_matches]   ->   out/knowledge/bot_calib.json
"""
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd
from demoparser2 import DemoParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wily.core import config  # noqa: E402
from wily.training import replay  # noqa: E402

TICK = 64
WIN = 3 * TICK
NOT_GUNS = {"hegrenade", "inferno", "molotov", "incgrenade", "flashbang", "smokegrenade", "knife", "world", "decoy", "taser"}
OUT = os.path.join(config.OUT, "knowledge", "bot_calib.json")


def sid_(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def off_head(m, e):
    """Degrees between m's view and e's head."""
    pr, yr = math.radians(m[3]), math.radians(m[4])
    v = np.array([math.cos(pr) * math.cos(yr), math.cos(pr) * math.sin(yr), -math.sin(pr)])
    t = np.array([e[0] - m[0], e[1] - m[1], (e[2] + (46 if e[5] else 64)) - (m[2] + (46 if m[5] else 64))])
    n = np.linalg.norm(t)
    return None if n < 1 else math.degrees(math.acos(max(-1.0, min(1.0, float(v @ (t / n))))))


def duels(dem):
    p = DemoParser(dem)
    hurt = p.parse_event("player_hurt", other=["total_rounds_played"])
    for c in ("attacker_steamid", "user_steamid"):
        hurt[c] = hurt[c].map(sid_)
    hurt = hurt[(hurt.attacker_steamid != 0) & (hurt.attacker_steamid != hurt.user_steamid) & ~hurt.weapon.isin(NOT_GUNS)].sort_values("tick")
    fire = p.parse_event("weapon_fire")
    fire["user_steamid"] = fire.user_steamid.map(sid_)
    fire = fire[~fire.weapon.str.replace("weapon_", "", regex=False).isin(NOT_GUNS)]
    fires = {s: np.sort(g.tick.to_numpy()) for s, g in fire.groupby("user_steamid")}
    death = p.parse_event("player_death")
    for c in ("attacker_steamid", "user_steamid"):
        death[c] = death[c].map(sid_)
    kill_at = {(r.attacker_steamid, r.user_steamid, int(r.tick)) for r in death.itertuples()}
    first, last = [], {}
    for r in hurt.itertuples():
        k = (r.attacker_steamid, r.user_steamid)
        if k not in last or r.tick - last[k] > WIN:
            first.append((int(r.tick), r.attacker_steamid, r.user_steamid, r.weapon, int(r.hitgroup) if str(r.hitgroup).isdigit() else str(r.hitgroup)))
        last[k] = r.tick
    if not first:
        return []
    ticks = set()
    for t, *_ in first:
        ticks.update(range(max(t - WIN, 0), t + 1, 2))
    df = p.parse_ticks(["X", "Y", "Z", "pitch", "yaw", "ducking", "approximate_spotted_by"], ticks=sorted(ticks))
    df["steamid"] = df.steamid.map(sid_)
    at, spotted = {}, {}
    for r in df.itertuples():
        at[(r.tick, r.steamid)] = (r.X, r.Y, r.Z, r.pitch, r.yaw, bool(r.ducking))
        sb = r.approximate_spotted_by
        spotted[(r.tick, r.steamid)] = {sid_(x) for x in sb} if isinstance(sb, (list, np.ndarray)) else set()
    kills = sorted(kill_at)
    out = []
    for t, a, v, w, hg in first:
        t0 = max(t - WIN, 0)
        t0 += t0 % 2
        ts = next((k for k in range(t0, t + 1, 2) if a in spotted.get((k, v), ())), None)
        if ts is None:
            continue
        m, e = at.get((ts, a)), at.get((ts, v))
        if not m or not e:
            continue
        fa = fires.get(a, np.array([], dtype=int))
        i = int(np.searchsorted(fa, ts))
        tf = int(fa[i]) if i < len(fa) and fa[i] <= t else None
        # his speed at the shot: where he was 2 ticks before it and at it (the samples every 2 ticks)
        sp = None
        if tf is not None:
            k1 = tf - tf % 2
            p1, p0 = at.get((k1, a)), at.get((k1 - 4, a))
            if p1 and p0:
                sp = math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * TICK / 4
        dk = next((k for (ka, kv, k) in kills if ka == a and kv == v and t <= k <= t + WIN), None)
        shots = int(((fa >= (tf or t)) & (fa <= dk)).sum()) if dk is not None else None
        out.append({"react_shot": None if tf is None else (tf - ts) / TICK, "react_hit": (t - ts) / TICK,
                    "off_deg": off_head(m, e), "speed": sp, "dist": math.dist(m[:3], e[:3]), "weapon": w, "hitgroup": hg,
                    "kill_s": None if dk is None else (dk - ts) / TICK, "shots_to_kill": shots, "attacker": a})
    return out


def q(s, ps=(25, 50, 75, 90)):
    s = pd.Series([x for x in s if x is not None and not (isinstance(x, float) and math.isnan(x))], dtype=float)
    return {f"p{k}": round(float(s.quantile(k / 100)), 3) for k in ps} | {"n": int(len(s))} if len(s) else {"n": 0}


def main(n=15):
    sid = str(config.settings().get("own_steamid") or "")
    rows = []
    for mid, mp in replay._own_matches(sid, n):
        dem = config.demo(mid)
        if not os.path.exists(dem):
            continue
        t0 = time.time()
        try:
            got = duels(dem)
        except Exception as ex:   # a demo the parser refuses: the others still count
            print(mid, mp, "skipped:", ex, flush=True)
            continue
        for g in got:
            g["map"] = mp
        rows += got
        print(f"{mid} {mp}: {len(got)} duels ({time.time() - t0:.0f} s)", flush=True)
    D = pd.DataFrame(rows)
    if D.empty:
        print("no duel")
        return
    D["you"] = D.attacker.astype(str) == sid
    O = D[~D.you]
    band = pd.cut(O.dist, [0, 500, 1000, 1500, 9999], labels=["<500", "500-1000", "1000-1500", ">1500"])
    res = {"made": time.strftime("%Y-%m-%d %H:%M"), "matches": n, "duels": int(len(D)), "players": int(O.attacker.nunique()),
           "others": {"react_shot": q(O.react_shot), "react_hit": q(O.react_hit), "off_deg": q(O.off_deg), "kill_s": q(O.kill_s),
                      "shots_to_kill": q(O.shots_to_kill), "speed_at_shot": q(O.speed),
                      "stopped_share": round(float((O.speed.dropna() < 80).mean()), 3),
                      "head_first_hit": round(float((O.hitgroup.astype(str).isin(["1", "head"])).mean()), 3),
                      "by_dist": {str(b): {"react_hit": q(g.react_hit, (50,)), "head_first_hit": round(float(g.hitgroup.astype(str).isin(["1", "head"]).mean()), 3),
                                           "shots_to_kill": q(g.shots_to_kill, (50,))} for b, g in O.groupby(band, observed=True)}},
           "you": {"react_shot": q(D[D.you].react_shot), "react_hit": q(D[D.you].react_hit), "off_deg": q(D[D.you].off_deg)}}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 15)
