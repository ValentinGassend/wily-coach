"""Deep dive for one player (needs his demos in cache/): true reaction time & crosshair placement from visibility data,
who-saw-who-first on deaths, 2D round replays, grenade audit vs pros, zone duels vs pros.

Usage: python -m wily.demos.deepdive [steamid]
Writes out/players/<sid>/deepdive.json and out/players/<sid>/replays/<match>.json
"""
import json
import math
import os
import sys

import numpy as np
import pandas as pd
from demoparser2 import DemoParser

from wily.core import config
from wily.core import mapdata
from wily.demos.map_analysis import humanize

TICK = 64
WIN = 3 * TICK  # look back 3 s before the first damage


def sid_(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def view_angle(m, e):
    """Angle between m's view and e's head (deg)."""
    pr, yr = math.radians(m["pitch"]), math.radians(m["yaw"])
    v = np.array([math.cos(pr) * math.cos(yr), math.cos(pr) * math.sin(yr), -math.sin(pr)])
    t = np.array([e["X"] - m["X"], e["Y"] - m["Y"], (e["Z"] + (46 if e["ducking"] else 64)) - (m["Z"] + (46 if m["ducking"] else 64))])
    n = np.linalg.norm(t)
    return None if n < 1 else math.degrees(math.acos(max(-1, min(1, float(v @ (t / n))))))


def engagements(dem):
    """For every player: reaction time / crosshair error on engagements they opened fire in, and first-sight on deaths."""
    p = DemoParser(dem)
    hurt = p.parse_event("player_hurt")
    for c in ("attacker_steamid", "user_steamid"):
        hurt[c] = hurt[c].map(sid_)
    hurt = hurt[(hurt.attacker_steamid != 0) & (hurt.attacker_steamid != hurt.user_steamid)]
    hurt = hurt[~hurt.weapon.isin(["hegrenade", "inferno", "molotov", "incgrenade", "flashbang", "smokegrenade", "knife", "world"])]
    hurt = hurt.sort_values("tick")
    # first hit of each (attacker, victim) engagement (a new engagement after 3 s without hits)
    first, last = [], {}
    for r in hurt.itertuples():
        k = (r.attacker_steamid, r.user_steamid)
        if k not in last or r.tick - last[k] > WIN:
            first.append((int(r.tick), r.attacker_steamid, r.user_steamid))
        last[k] = r.tick
    deaths = p.parse_event("player_death")
    for c in ("attacker_steamid", "user_steamid"):
        deaths[c] = deaths[c].map(sid_)
    deaths = deaths[(deaths.attacker_steamid != 0) & (deaths.attacker_steamid != deaths.user_steamid)]
    ticks = set()
    for t, a, v in first:
        ticks.update(range(max(t - WIN, 0), t + 1, 2))
    for t in deaths.tick:
        ticks.update(range(max(int(t) - WIN, 0), int(t) + 1, 2))
    if not ticks:
        return pd.DataFrame(), pd.DataFrame()
    df = p.parse_ticks(["X", "Y", "Z", "pitch", "yaw", "ducking", "approximate_spotted_by", "is_alive"], ticks=sorted(ticks))
    df["steamid"] = df["steamid"].map(sid_)
    spotted = {}  # (tick, target) -> set of observers
    rows = {}
    for r in df.itertuples():
        spotted[(r.tick, r.steamid)] = {sid_(x) for x in (r.approximate_spotted_by if isinstance(r.approximate_spotted_by, (list, np.ndarray)) else [])}
        rows[(r.tick, r.steamid)] = {"X": r.X, "Y": r.Y, "Z": r.Z, "pitch": r.pitch, "yaw": r.yaw, "ducking": bool(r.ducking)}

    def first_seen(observer, target, t_end):
        for t in range(max(t_end - WIN, 0) + (t_end - WIN) % 2 if t_end >= WIN else 0, t_end + 1, 2):
            if observer in spotted.get((t, target), ()):
                return t
        return None
    eng = []
    for t, a, v in first:
        ts = first_seen(a, v, t)
        if ts is None:
            continue
        m, e = rows.get((ts, a)), rows.get((ts, v))
        ang = view_angle(m, e) if m and e else None
        eng.append({"attacker": a, "victim": v, "tick": t, "reaction_s": (t - ts) / TICK, "preaim_deg": ang})
    dth = []
    for r in deaths.itertuples():
        t = int(r.tick)
        me_seen = first_seen(r.attacker_steamid, r.user_steamid, t)   # killer saw victim
        i_saw = first_seen(r.user_steamid, r.attacker_steamid, t)     # victim saw killer
        dth.append({"victim": r.user_steamid, "killer": r.attacker_steamid, "tick": t,
                    "surprised": i_saw is None or (me_seen is not None and me_seen < i_saw - 8),
                    "never_saw": i_saw is None})
    return pd.DataFrame(eng), pd.DataFrame(dth)


def replay(mid):
    """Compact 2D replay: per round, frames every 0.5 s with every player's radar position."""
    d = os.path.join(config.DEEP, mid)
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    sm = pd.read_parquet(os.path.join(d, "samples.parquet"))
    duels = pd.read_parquet(os.path.join(d, "duels.parquet"))
    nades = pd.read_parquet(os.path.join(d, "grenades.parquet"))
    players = sm.drop_duplicates("steamid")[["steamid", "name"]]
    pidx = {s: i for i, s in enumerate(players.steamid)}
    rounds = []
    for rn, g in sm.groupby("round"):
        frames = []
        for t, f in g.groupby("t"):
            frames.append([round(float(t), 1), [[pidx[s], round(float(x)), round(float(y)), 0 if side == "T" else 1, lv]
                                               for s, x, y, side, lv in zip(f.steamid, f.px, f.py, f.side, f.level)]])
        k = duels[duels["round"] == rn]
        n = nades[nades["round"] == rn] if len(nades) else nades
        rounds.append({"n": int(rn), "frames": frames,
                       "kills": [[round(float(r.t), 1), pidx.get(r.killer, -1), pidx.get(r.victim, -1), round(r.victim_px), round(r.victim_py), r.weapon]
                                 for r in k.itertuples()],
                       "nades": [[round(float(r.t + (r.flight_s or 0)), 1), r.type, round(r.land_px), round(r.land_py), pidx.get(r.thrower, -1)]
                                 for r in n.itertuples() if r.land_px == r.land_px] if len(n) else []})
    return {"map": meta["map"], "levels": meta["levels"], "players": [{"steamid": str(s), "name": nm} for s, nm in players.itertuples(index=False)],
            "rounds": rounds}


def ensure_replay(sid, mid):
    """A match's 2D replay for a player's page, built from the match's detailed extraction when it is missing (0.3 s,
    no demo needed): the replays were only made by run(), last run on 10/01, so every later match had none (04/10)."""
    mid = str(mid)
    dst = os.path.join(config.player_dir(sid), "replays", f"{mid}.json")
    if os.path.exists(dst):
        return dst
    if not os.path.exists(os.path.join(config.DEEP, mid, "samples.parquet")):
        return None
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    config.write_json(dst, replay(mid), ensure_ascii=False, separators=(",", ":"))
    return dst


def grenade_audit(steamid, my_matches):
    """My grenades vs pro grenades on the same maps: what I throw, and what pros throw from my zones that I never do."""
    from wily.base import proref
    pro_dir = os.path.join(config.OUT, "deep_pro")
    mine, pro = [], []
    maps = set()
    for mid in my_matches:
        d = os.path.join(config.DEEP, mid)
        meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
        g = pd.read_parquet(os.path.join(d, "grenades.parquet"))
        g = g[g.thrower == steamid].assign(map=meta["map"])
        mine.append(g)
        maps.add(meta["map"])
    mine = pd.concat(mine, ignore_index=True) if mine else pd.DataFrame()
    my_zone_time = {}  # map -> side -> zones holding >= 5 % of my time
    for mid in my_matches:
        d = os.path.join(config.DEEP, mid)
        meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
        smp = pd.read_parquet(os.path.join(d, "samples.parquet"), columns=["steamid", "side", "zone"])
        smp = smp[smp.steamid == steamid]
        for side, g in smp.groupby("side"):
            share = g.zone.value_counts(normalize=True)
            my_zone_time.setdefault(meta["map"], {}).setdefault(side, set()).update(share[share >= 0.05].index)
    for pid in os.listdir(pro_dir) if os.path.exists(pro_dir) else []:
        mp = os.path.join(pro_dir, pid, "meta.json")
        if not os.path.exists(mp):
            continue
        meta = json.load(open(mp, encoding="utf-8"))
        if meta["map"] in maps:
            g = pd.read_parquet(os.path.join(pro_dir, pid, "grenades.parquet")).assign(map=meta["map"])
            pro.append(g)
    pro = pd.concat(pro, ignore_index=True) if pro else pd.DataFrame()
    out = {}
    for m in maps:
        me = mine[(mine["map"] == m) & mine.land_px.notna()] if len(mine) else mine
        pr = pro[(pro["map"] == m) & pro.land_px.notna()] if len(pro) else pro
        cell = lambda df: list(zip((df.land_px // 40).astype(int), (df.land_py // 40).astype(int), df["type"]))
        mine_cells = set(cell(me)) if len(me) else set()
        res = {"mine": [], "missing": []}
        # my grenades grouped by landing spot, with how often pros use the same spot
        if len(me):
            me = me.assign(cell=cell(me))
            pro_cells = pd.Series(cell(pr)).value_counts() if len(pr) else pd.Series(dtype=int)
            for c, g in me.groupby("cell"):
                b = g.iloc[0]
                res["mine"].append({"type": b["type"], "from": humanize(str(b.zone), m), "to": humanize(str(b.land_zone), m) if b.land_zone else None,
                                    "count": int(len(g)), "pro_uses": int(pro_cells.get(c, 0)),
                                    "enemies_blind": float(g.enemies_blind.fillna(0).mean()) if "enemies_blind" in g and b["type"] == "flash" else None,
                                    "mates_blind": float(g.mates_blind.fillna(0).mean()) if "mates_blind" in g and b["type"] == "flash" else None,
                                    "damage": float(g.damage.fillna(0).mean()) if "damage" in g and b["type"] in ("he", "molotov") else None})
            res["mine"].sort(key=lambda x: -x["count"])
        # pro grenades thrown, on my side, from zones where I spend time, landing where I never throw
        if len(pr):
            pr = pr.assign(cell=cell(pr))
            mz = my_zone_time.get(m, {})
            keep = pr.apply(lambda r: r["zone"] in mz.get(r["side"], set()), axis=1)
            cand = pr[keep & ~pr.cell.isin(mine_cells)]
            for c, g in cand.groupby("cell"):
                if len(g) < 3:
                    continue
                rep = g[(g.speed < 20) | g.jump]
                b = (rep if len(rep) else g).iloc[0]
                how = " + ".join(x for x, ok in (("jumpthrow", b.jump), ("running", b.speed > 150), ("crouching", b.crouch)) if ok) or "standing still"
                res["missing"].append({"type": b["type"], "from": humanize(str(b.zone), m), "to": humanize(str(b.land_zone), m) if b.land_zone else None,
                                       "pro_uses": int(len(g)), "side": b.side, "t": round(float(g.t.median())), "how": how,
                                       "by": str(b.thrower_name), "setpos": f"setpos {b.X:.1f} {b.Y:.1f} {b.Z:.1f}; setang {b.pitch:.2f} {b.yaw:.2f} 0",
                                       "from_px": [round(b.px), round(b.py)], "to_px": [round(b.land_px), round(b.land_py)], "level": b.level})
            res["missing"].sort(key=lambda x: -x["pro_uses"])
            res["missing"] = res["missing"][:10]
        out[m] = res
    return out


def zones_vs_pros(steamid, my_matches):
    """Duels won per zone: me vs pros in the same zone and side."""
    pro_dir = os.path.join(config.OUT, "deep_pro")
    mine, pro = [], []
    maps = {}
    for mid in my_matches:
        d = os.path.join(config.DEEP, mid)
        meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
        if meta.get("zone_mode") != "callouts":
            continue
        du = pd.read_parquet(os.path.join(d, "duels.parquet")).assign(map=meta["map"])
        mine.append(du[(du.killer == steamid) | (du.victim == steamid)])
        maps[meta["map"]] = True
    for pid in os.listdir(pro_dir) if os.path.exists(pro_dir) else []:
        mp = os.path.join(pro_dir, pid, "meta.json")
        if os.path.exists(mp):
            meta = json.load(open(mp, encoding="utf-8"))
            if meta["map"] in maps:
                pro.append(pd.read_parquet(os.path.join(pro_dir, pid, "duels.parquet")).assign(map=meta["map"]))
    if not mine or not pro:
        return {}
    mine, pro = pd.concat(mine), pd.concat(pro)

    def pov(df, who=None):
        a = df if who is None else df[df.killer == who]
        b = df if who is None else df[df.victim == who]
        return pd.concat([pd.DataFrame({"map": a["map"], "side": a.killer_side, "zone": a.killer_zone, "won": True, "speed": a.killer_speed}),
                          pd.DataFrame({"map": b["map"], "side": b.victim_side, "zone": b.victim_zone, "won": False, "speed": b.victim_speed})])
    me, pr = pov(mine, steamid), pov(pro)
    out = []
    for (m, side, z), g in me.groupby(["map", "side", "zone"]):
        if len(g) < 3 or z == "?":
            continue
        pg = pr[(pr["map"] == m) & (pr.side == side) & (pr.zone == z)]
        if len(pg) < 10:
            continue
        out.append({"map": m, "side": side, "zone": humanize(z, m), "my_duels": int(len(g)), "my_win": round(100 * g.won.mean()),
                    "pro_duels": int(len(pg)), "pro_win": round(100 * pg.won.mean()),
                    "my_hold": round(100 * (g.speed < 40).mean()), "pro_hold": round(100 * (pg.speed < 40).mean())})
    return sorted(out, key=lambda x: -x["my_duels"])


def run(steamid):
    steamid = int(steamid)
    pdir = config.player_dir(steamid)
    my_matches = [m for m in os.listdir(os.path.join(pdir, "matches")) if config.has_demo(m)
                  and os.path.exists(os.path.join(config.DEEP, m, "meta.json"))]
    E, Dd = [], []
    os.makedirs(os.path.join(pdir, "replays"), exist_ok=True)
    for mid in my_matches:
        print(f"[{mid}] visibility and replay", flush=True)
        e, d = engagements(config.demo(mid))
        E.append(e.assign(match=mid))
        Dd.append(d.assign(match=mid))
        json.dump(replay(mid), open(os.path.join(pdir, "replays", f"{mid}.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    E, Dd = pd.concat(E, ignore_index=True), pd.concat(Dd, ignore_index=True)
    me_e, oth_e = E[E.attacker == steamid], E[E.attacker != steamid]
    me_d, oth_d = Dd[Dd.victim == steamid], Dd[Dd.victim != steamid]
    # per-player medians of the other players of the same matches = reference distribution
    ref_rt = oth_e.groupby("attacker").reaction_s.median()
    ref_pa = oth_e.groupby("attacker").preaim_deg.median()
    ref_sp = oth_d.groupby("victim").surprised.mean()
    pct_better = lambda ref, v, lower=True: round(float(((ref > v) if lower else (ref < v)).mean() * 100)) if len(ref) and v == v else None
    rt, pa, sp = float(me_e.reaction_s.median()), float(me_e.preaim_deg.median()), float(me_d.surprised.mean()) if len(me_d) else None
    fast = me_e[me_e.reaction_s <= 0.35]
    res = {
        "engagements": int(len(me_e)), "deaths": int(len(me_d)),
        "reaction": {"you": round(rt, 3), "median_others": round(float(ref_rt.median()), 3), "better_than_pct": pct_better(ref_rt, rt),
                     "share_under_350ms": round(100 * len(fast) / max(len(me_e), 1))},
        "preaim": {"you": round(pa, 1), "median_others": round(float(ref_pa.median()), 1), "better_than_pct": pct_better(ref_pa, pa)},
        "surprised": {"you": round(100 * sp) if sp is not None else None, "median_others": round(100 * float(ref_sp.median())),
                      "better_than_pct": pct_better(ref_sp, sp) if sp is not None else None,
                      "never_saw": int(me_d.never_saw.sum()) if len(me_d) else 0},
        "n_ref_players": int(ref_rt.index.nunique()),
        "matches": my_matches,
        "grenades": grenade_audit(steamid, my_matches),
        "zones_vs_pros": zones_vs_pros(steamid, my_matches),
    }
    json.dump(res, open(os.path.join(pdir, "deepdive.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    return res


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    r = run(sys.argv[1] if len(sys.argv) > 1 else config.settings().get("own_steamid"))
    print(json.dumps({k: r[k] for k in ("engagements", "deaths", "reaction", "preaim", "surprised", "n_ref_players")}, ensure_ascii=False, indent=1))
    print(json.dumps(r["zones_vs_pros"][:8], ensure_ascii=False))
    for m, g in r["grenades"].items():
        print(m, "mine", [(x["type"], x["from"], x["to"], x["count"], x["pro_uses"]) for x in g["mine"][:5]])
        print(m, "missing", [(x["type"], x["from"], x["to"], x["pro_uses"], x["by"]) for x in g["missing"][:5]])
