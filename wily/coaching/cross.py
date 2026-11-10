"""Cross-match analysis for one player: zones/spots to play or avoid, others' best spots, lineups, duel contexts.

Usage: python -m wily.coaching.cross > out/cross.json   (reads out/deep/<match_id>/)
"""
import json
import os
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

from wily.demos.map_analysis import humanize

ME = None  # set by run()
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # the root
DEEP = os.path.join(HERE, "out", "deep")
CELL = 28  # radar px (~110-160 game units depending on map)


def wr(k, d):
    n = k + d
    return round(100 * k / n) if n else None


def _zone_n(mid):
    """Every player's samples per side and zone (the zones' share of the time spent, summed over the pool)."""
    try:
        S = pd.read_parquet(os.path.join(DEEP, mid, "samples.parquet"), columns=["side", "zone"])
    except Exception:
        return None
    out = {}
    for (side, zone), n in S.groupby(["side", "zone"]).size().items():
        out.setdefault(side, {})[zone] = int(n)
    return out


def _my_zone_n(mid):
    """The player's own samples in the match, per side and zone ({} when they are not in it)."""
    try:
        S = pd.read_parquet(os.path.join(DEEP, mid, "samples.parquet"), columns=["steamid", "side", "zone"])
    except Exception:
        return None
    out = {}
    for (side, zone), n in S[S.steamid == ME].groupby(["side", "zone"]).size().items():
        out.setdefault(side, {})[zone] = int(n)
    return out


def _pool(match_ids=None):
    """(the base's facts, the deep folders' dates, the player's own counts per match, the player's matches asked, the
    maps' pool of matches, the pool's counts per match), the per-match counts kept on disk (ledger.py)."""
    from wily.core import ledger
    dirs = ledger.folders(DEEP)
    facts = {m: (f["map"], f["zone_mode"], f["zones"]) for m, f in ledger.match_facts().items()}
    from wily.app import pipeline
    asked = sorted(m for m in facts if (match_ids is None or m in match_ids) and m in dirs)
    extra = sorted((set(pipeline.player_matches(ME)) & set(facts) & set(dirs)) - set(asked))
    my_n = ledger.per_match(f"cross_me_{ME}", {m: dirs[m] for m in asked + extra}, _my_zone_n)
    mine = {m for m in asked if my_n.get(m)}
    my_maps = {facts[m][0] for m in mine}
    pool = [mid for mid in sorted(facts) if facts[mid][0] in my_maps and (mid in mine or facts[mid][1] == "callouts")]
    zn = ledger.per_match("cross_zone_n", {m: dirs[m] for m in pool}, _zone_n, shared=True)
    return facts, dirs, my_n, mine, pool, zn


def load(match_ids=None, only=None):
    """Deep data per map: the player's matches, plus every other analyzed demo of the same map
    (reference pool for zone baselines, best spots and lineups) when the map uses game callouts.
    15/10: the pool's positions are no longer loaded (every sample of every match of your maps: 10 GB in memory, and
    a read of the 5,000 matches' meta.json at each sync): your own samples, and each pool match's samples counted per
    side and zone (kept on disk per match), yours taken out: the same shares of the time spent.
    16/10: your own samples counted per side and zone too, kept per match (the first analysis after a restart read
    every one of your matches' positions twice from the hard disk: 148 s). only: those maps (a worker's, run())."""
    from collections import Counter
    from wily.core import ledger
    per_map = defaultdict(lambda: {"duels": [], "nades": [], "my_n": {}, "zone_n": {}, "meta": None, "matches": 0, "pool": 0})
    facts, dirs, my_n, mine, pool, zn = _pool(match_ids)
    if only is not None:
        pool = [mid for mid in pool if facts[mid][0] in only]
    best = {}
    mark = lambda x, mid: x.assign(match=mid)
    for mp in dict.fromkeys(facts[mid][0] for mid in pool):   # each map's duels and grenades, kept as one (ledger.py)
        ms = [mid for mid in pool if facts[mid][0] == mp]
        for name, key in (("duels", "duels"), ("grenades", "nades")):
            items = [(mid, os.path.join(DEEP, mid, f"{name}.parquet"), dirs[mid]) for mid in ms]
            per_map[mp][key] = [ledger.gathered(f"cross_{name}_{mp}", items, prep=mark)]
    for mid in pool:
        mp, _, nz = facts[mid]
        m = per_map[mp]
        others = {sd: Counter(z) for sd, z in (zn.get(mid) or {}).items()}
        for sd, c in (my_n.get(mid) or {}).items():   # the player's own samples: counted, and out of the others' count
            m["my_n"].setdefault(sd, Counter()).update(c)
            for z, n in c.items():
                others.setdefault(sd, Counter())[z] -= int(n)
        for sd, c in others.items():
            m["zone_n"].setdefault(sd, Counter()).update(c)
        m["pool"] += 1
        if mid in mine:
            m["matches"] += 1
        if mp not in best or nz > facts[best[mp]][2]:
            best[mp] = mid
    for mp, m in per_map.items():
        m["meta"] = json.load(open(os.path.join(DEEP, best[mp], "meta.json"), encoding="utf-8"))
        for key in ("duels", "nades"):
            m[key] = pd.concat(m[key], ignore_index=True) if m[key] else pd.DataFrame()
    return per_map


def zone_name(meta, key):
    for z in meta["zones"]:
        if z["key"] == key:
            return z["name"]
    return humanize(key, meta.get("map")) if isinstance(key, str) else str(key)


def my_duels(d):
    """One row per duel I was in, from my point of view."""
    a = d[d.killer == ME].copy()
    a["won"] = True
    b = d[d.victim == ME].copy()
    b["won"] = False
    rows = []
    for won, df, me, op in ((True, a, "killer", "victim"), (False, b, "victim", "killer")):
        for _, r in df.iterrows():
            rows.append({"match": r.match, "round": r["round"], "tick": r.tick, "t": r.t, "won": won,
                         "side": r[f"{me}_side"], "zone": r[f"{me}_zone"], "opp_zone": r[f"{op}_zone"],
                         "px": r[f"{me}_px"], "py": r[f"{me}_py"], "level": r[f"{me}_level"],
                         "opp_px": r[f"{op}_px"], "opp_py": r[f"{op}_py"],
                         "X": r[f"{me}_X"], "Y": r[f"{me}_Y"],
                         "speed": r.get(f"{me}_speed"), "opp_speed": r.get(f"{op}_speed"),
                         "hp": r.get(f"{me}_hp"), "crouch": r.get(f"{me}_crouch"),
                         "mate_dist": r.get(f"{me}_mate_dist"), "mates_alive": r.get(f"{me}_mates_alive"),
                         "opp_mates_alive": r.get(f"{op}_mates_alive"),
                         "me_flashed": r.killer_flashed if me == "killer" else r.victim_flashed,
                         "opp_flashed": r.victim_flashed if me == "killer" else r.killer_flashed,
                         "distance": r.distance, "weapon": r.weapon, "opening": r.opening})
    return pd.DataFrame(rows).sort_values(["match", "tick"]) if rows else pd.DataFrame()


def all_duels_pov(d, exclude_me=True):
    """Every duel from both players' point of view (for 'others' baselines)."""
    rows = []
    for me, op, won in (("killer", "victim", True), ("victim", "killer", False)):
        df = pd.DataFrame({
            "player": d[me], "won": won, "side": d[f"{me}_side"], "zone": d[f"{me}_zone"],
            "px": d[f"{me}_px"], "py": d[f"{me}_py"], "level": d[f"{me}_level"], "t": d.t,
            "speed": d.get(f"{me}_speed"), "opp_speed": d.get(f"{op}_speed"), "crouch": d.get(f"{me}_crouch"),
            "hp": d.get(f"{me}_hp"), "mate_dist": d.get(f"{me}_mate_dist"),
            "mates_alive": d.get(f"{me}_mates_alive"), "opp_mates_alive": d.get(f"{op}_mates_alive"),
            "opp_flashed": d.victim_flashed if me == "killer" else d.killer_flashed,
            "me_flashed": d.killer_flashed if me == "killer" else d.victim_flashed,
            "distance": d.distance, "scoped": d.get(f"{me}_scoped"), "weapon": d.weapon})
        rows.append(df)
    out = pd.concat(rows, ignore_index=True)
    return out[out.player != ME] if exclude_me else out


def contexts(mine, others):
    """Win rate of duels under different conditions, me vs the other players."""
    def split(df, name, masks):
        res = []
        for label, fn in masks:
            s = df[fn(df)]
            res.append({"label": label, "n": int(len(s)), "win": round(100 * s.won.mean()) if len(s) else None})
        return {"name": name, "rows": res}

    specs = [
        ("Teammate support", [("teammate within 600 u", lambda x: x.mate_dist < 600),
                                     ("alone (teammate beyond 1,200 u or none)", lambda x: (x.mate_dist > 1200) | x.mate_dist.isna())]),
        ("Movement at the start of the duel", [("still, you hold the angle (< 40 u/s)", lambda x: x.speed < 40),
                                        ("moving, you peek (> 110 u/s)", lambda x: x.speed > 110)]),
        ("Enemy movement", [("the enemy peeks at you (> 110 u/s)", lambda x: x.opp_speed > 110),
                                       ("the enemy is still (< 40 u/s)", lambda x: x.opp_speed < 40)]),
        ("Flashes", [("enemy flashed by your team", lambda x: x.opp_flashed == True),
                    ("you flashed", lambda x: x.me_flashed == True),
                    ("nobody flashed", lambda x: (x.opp_flashed == False) & (x.me_flashed == False))]),
        ("Balance of power", [("with a man advantage", lambda x: x.mates_alive > x.opp_mates_alive),
                              ("even", lambda x: x.mates_alive == x.opp_mates_alive),
                              ("outnumbered", lambda x: x.mates_alive < x.opp_mates_alive)]),
        ("Moment of the round", [("0-20 s", lambda x: x.t <= 20), ("20-45 s", lambda x: (x.t > 20) & (x.t <= 45)),
                             ("after 45 s", lambda x: x.t > 45)]),
        ("Distance", [("short (< 10 m)", lambda x: x.distance < 10), ("medium (10-20 m)", lambda x: (x.distance >= 10) & (x.distance < 20)),
                      ("long (> 20 m)", lambda x: x.distance >= 20)]),
        ("Health at the start of the duel", [("more than 80 HP", lambda x: x.hp > 80), ("less than 50 HP", lambda x: x.hp < 50)]),
        ("Stance", [("crouched", lambda x: x.crouch == True), ("standing", lambda x: x.crouch == False)]),
    ]
    out = []
    for name, masks in specs:
        a, b = split(mine, name, masks), split(others, name, masks)
        for ra, rb in zip(a["rows"], b["rows"]):
            ra["others_win"], ra["others_n"] = rb["win"], rb["n"]
        out.append(a)
    return out


def repeek(mine):
    """After one of my kills, what happens in my next duel within 8 s depending on whether I moved."""
    res = {"stayed": [0, 0], "moved": [0, 0]}
    for _, g in mine.groupby(["match", "round"]):
        g = g.sort_values("tick").reset_index(drop=True)
        for i in range(len(g) - 1):
            a, b = g.iloc[i], g.iloc[i + 1]
            if not a.won or b.tick - a.tick > 8 * 64:
                continue
            moved = np.hypot(b.X - a.X, b.Y - a.Y)
            key = "stayed" if moved < 150 else "moved"
            res[key][0 if b.won else 1] += 1
    return {k: {"won": v[0], "lost": v[1], "win": wr(*v)} for k, v in res.items()}


def cells(df, xcol="px", ycol="py"):
    return list(zip((df[xcol] // CELL).astype(int), (df[ycol] // CELL).astype(int), df["level"]))


def _contenders(t, grp, typ, zones_of_interest, top):
    """The landing cells that can be among the top ones, in the groups' order (16/10: the full reading of each of the
    thousands of cells, for 4 kept, took a minute per plan). Each cell's score computed for all at once, the same as
    lineups() computes it one cell at a time; the cells kept: those not left out and scoring at least the top-th best
    (less a margin far above any rounding): the others can't be in the top, lineups() reads the rest as before."""
    if not len(t):
        return []
    n = grp.size()
    rel = (t.zone.isin(zones_of_interest) | t.land_zone.isin(zones_of_interest)).groupby(t["lcell"]).any()
    if typ == "flash":
        sc = t.enemies_blind.fillna(0) * 2 + t.kills_after.fillna(0) * 3 - t.mates_blind.fillna(0) * 2
        ok = (sc > 0).groupby(t["lcell"]).any()
        value = sc.groupby(t["lcell"]).mean() + 0.3 * n
    elif typ in ("he", "molotov"):
        dmg = t.damage.fillna(0)
        ok = ~((dmg.groupby(t["lcell"]).sum() <= 0) & (n < 3))
        value = dmg.groupby(t["lcell"]).mean() / 20 + n
    else:
        ok = n >= 2
        value = n + t.thrower.groupby(t["lcell"]).nunique()
    key = (value + rel.astype(int) * 5)[ok]
    if len(key) <= top:
        return list(key.index)
    floor = key.nlargest(top).iloc[-1] - 1e-6 * max(1.0, abs(float(key.max())))
    return list(key.index[key >= floor])


def lineups(nades, side, zones_of_interest, meta, top=4):
    """Best grenades of each type that land in / are thrown from the zones this player uses."""
    out = []
    g = nades[(nades.side == side) & nades.land_px.notna()].copy()
    if not len(g):
        return out
    g["lcell"] = list(zip((g.land_px // 36).astype(int), (g.land_py // 36).astype(int), g.land_level))
    for typ in ("smoke", "flash", "molotov", "he"):
        t = g[g.type == typ]
        groups = []
        grp = t.groupby("lcell")
        for cell in _contenders(t, grp, typ, zones_of_interest, top):
            c = grp.get_group(cell)
            rel = c.zone.isin(zones_of_interest).any() or c.land_zone.isin(zones_of_interest).any()
            if typ == "flash":
                c = c.assign(score=c.enemies_blind.fillna(0) * 2 + c.kills_after.fillna(0) * 3 - c.mates_blind.fillna(0) * 2)
                eff = c[c.score > 0]
                if not len(eff):
                    continue
                best = eff.sort_values("score", ascending=False).iloc[0]
                metric = {"uses": int(len(c)), "enemies_blind_avg": round(float(c.enemies_blind.mean()), 1),
                          "mates_blind_avg": round(float(c.mates_blind.mean()), 1), "kills_after": int(c.kills_after.sum())}
                value = float(c.score.mean()) + 0.3 * len(c)
            elif typ in ("he", "molotov"):
                if c.damage.fillna(0).sum() <= 0 and len(c) < 3:
                    continue
                c = c.assign(repro=(c.speed < 20) | c.jump)
                best = c.sort_values(["damage", "repro"], ascending=False).iloc[0]
                metric = {"uses": int(len(c)), "damage_avg": round(float(c.damage.fillna(0).mean())),
                          "damage_best": int(best.damage or 0)}
                value = float(c.damage.fillna(0).mean()) / 20 + len(c)
            else:  # smoke: popular landing spot = standard smoke; pick the most common throw spot
                if len(c) < 2:
                    continue
                tc = c.assign(tcell=list(zip((c.px // 20).astype(int), (c.py // 20).astype(int))),
                              repro=(c.speed < 20) | c.jump)
                pool = tc[tc.repro] if tc.repro.any() else tc
                top_throw = pool.tcell.value_counts().index[0]
                best = pool[pool.tcell == top_throw].iloc[0]
                metric = {"uses": int(len(c)), "players": int(c.thrower.nunique())}
                value = len(c) + c.thrower.nunique()
            groups.append((value + (5 if rel else 0), rel, best, metric))
        groups.sort(key=lambda x: -x[0])
        for value, rel, b, metric in groups[:top]:
            how = []
            if b.jump:
                how.append("jumpthrow")
            if b.speed > 150:
                how.append("running")
            elif b.walk or 20 < b.speed <= 150:
                how.append("walking")
            if b.crouch:
                how.append("crouching")
            out.append({
                "type": typ, "side": side, "relevant": bool(rel), **metric,
                "from_zone": zone_name(meta, b.zone), "to_zone": zone_name(meta, b.land_zone) if b.land_zone else None,
                "from_px": [round(b.px), round(b.py)], "to_px": [round(b.land_px), round(b.land_py)],
                "level": b.level, "land_level": b.land_level,
                "t": b.t, "click": b.click, "how": " + ".join(how) or "standing still", "by": b.thrower_name,
                "setpos": f"setpos {b.X:.1f} {b.Y:.1f} {b.Z:.1f}; setang {b.pitch:.2f} {b.yaw:.2f} 0",
                "flight_s": b.get("flight_s"),
            })
    return out


def per_map(name, m, mine=None, others=None):
    d, n, meta = m["duels"], m["nades"], m["meta"]
    mine = my_duels(d) if mine is None else mine
    others = all_duels_pov(d) if others is None else others
    res = {"map": name, "matches": m["matches"], "pool": m["pool"], "levels": meta["levels"], "zone_mode": meta["zone_mode"],
           "zones_meta": meta["zones"], "sides": {}}
    for side in ("T", "CT"):
        my_c = {z: n for z, n in (m.get("my_n") or {}).get(side, {}).items() if n > 0}
        if not my_c:
            continue
        md = mine[mine.side == side] if len(mine) else mine
        od = others[others.side == side]
        # each zone's rows once (16/10: the whole side's duels compared to each zone in turn, a third of the run)
        od_z = dict(tuple(od.groupby("zone")))
        md_z = dict(tuple(md.groupby("zone"))) if len(md) else {}
        no_od, no_md = od.iloc[0:0], (md.iloc[0:0] if len(md) else md)
        tot_me = sum(my_c.values())
        pres = pd.Series({z: n / tot_me for z, n in my_c.items()}, dtype=float)
        first_contact = {}
        for z, g in od_z.items():
            first_contact[z] = round(float(g.t.quantile(0.25)), 1)
        zones = []
        # in the zones' order (16/10: a set's, that changed from one run to the next for zones of equal presence)
        for z in sorted(set(pres.index) | set(md.zone if len(md) else []), key=str):
            if z in ("?", None):
                continue
            mz = md_z.get(z, no_md) if len(md) else md
            k, dd = (int(mz.won.sum()), int((~mz.won).sum())) if len(mz) else (0, 0)
            oz = od_z.get(z, no_od)
            ok, odd = int(oz.won.sum()), int((~oz.won).sum())
            p = float(pres.get(z, 0) * 100)
            me_wr, oth_wr = wr(k, dd), wr(ok, odd)
            verdict = None
            if k + dd >= 4 and me_wr >= 60 and (oth_wr is None or me_wr >= oth_wr + 5):
                verdict = "exploit"
            elif k + dd >= 4 and (me_wr <= 35 or (oth_wr is not None and me_wr <= oth_wr - 20)):
                verdict = "avoid"
            elif k + dd >= 3 and k == 0:
                verdict = "avoid"
            if p < 3 and k + dd < 3:
                continue
            killers = mz[~mz.won].opp_zone.value_counts().head(2) if len(mine) else pd.Series(dtype=int)
            zones.append({"key": z, "name": zone_name(meta, z), "presence": round(p, 1), "k": k, "d": dd, "win": me_wr,
                          "others_k": ok, "others_d": odd, "others_win": oth_wr, "verdict": verdict,
                          "early_contact_s": first_contact.get(z),
                          "killed_from": [{"zone": zone_name(meta, kz), "n": int(c)} for kz, c in killers.items()],
                          "my_speed_med": round(float(mz.speed.median())) if len(mz) and mz.speed.notna().any() else None,
                          "others_speed_med": round(float(oz.speed.median())) if len(oz) and oz.speed.notna().any() else None})
        zones.sort(key=lambda z: -z["presence"])
        # whole-pool view of the side: which zones pay off for everybody, and how much time players spend there
        zc = {z: n for z, n in (m.get("zone_n") or {}).get(side, {}).items() if n > 0}   # the others' samples per zone
        tot = sum(zc.values())
        side_pres = pd.Series({z: n / tot for z, n in zc.items()}, dtype=float) if tot else pd.Series(dtype=float)
        pool_zones = []
        for z, g in od_z.items():
            if z in ("?", None):
                continue
            k, dd = int(g.won.sum()), int((~g.won).sum())
            if k + dd < 8:
                continue
            pool_zones.append({"key": z, "name": zone_name(meta, z), "k": k, "d": dd, "win": wr(k, dd),
                               "others_presence": round(float(side_pres.get(z, 0) * 100), 1),
                               "my_presence": round(float(pres.get(z, 0) * 100), 1),
                               "hold_pct": round(100 * float((g.speed < 40).mean())) if g.speed.notna().any() else None,
                               "t_med": round(float(g.t.median()))})
        pool_zones.sort(key=lambda z: -(z["win"] or 0))
        # my micro spots
        spots = []
        if len(md):
            md = md.assign(cell=cells(md))
            for c, g in md.groupby("cell"):
                if len(g) < 2:
                    continue
                spots.append({"px": [round(float(g.px.mean())), round(float(g.py.mean()))], "level": c[2],
                              "k": int(g.won.sum()), "d": int((~g.won).sum()), "zone": zone_name(meta, g.zone.mode()[0])})
        # others' best spots, in zones I use
        my_zones = {z["key"] for z in zones if z["presence"] >= 4}
        od2 = od[od.zone.isin(my_zones)].assign(cell=lambda x: cells(x))
        best = []
        for c, g in od2.groupby("cell"):
            k, dd = int(g.won.sum()), int((~g.won).sum())
            if k + dd >= 5 and k / (k + dd) >= 0.65:
                best.append({"px": [round(float(g.px.mean())), round(float(g.py.mean()))], "level": c[2], "k": k, "d": dd,
                             "win": wr(k, dd), "zone": zone_name(meta, g.zone.mode()[0]),
                             "hold_pct": round(100 * float((g.speed < 40).mean())), "crouch_pct": round(100 * float((g.crouch == True).mean())),
                             "scoped_pct": round(100 * float((g.scoped == True).mean())), "t_med": round(float(g.t.median())),
                             "players": int(g.player.nunique())})
        best.sort(key=lambda b: (-(b["k"] - b["d"]), -b["win"]))
        # my deaths spots with killers (for the radar)
        deaths = [{"px": [round(r.px), round(r.py)], "opp_px": [round(r.opp_px), round(r.opp_py)], "level": r.level, "won": bool(r.won),
                   "zone": zone_name(meta, r.zone)} for _, r in (md.dropna(subset=["px", "py", "opp_px", "opp_py"]).iterrows() if len(md) else [])]
        interest = my_zones | {z["key"] for z in zones if z["verdict"] == "avoid"}
        res["sides"][side] = {"zones": zones, "pool_zones": pool_zones, "spots": spots, "best_spots": best[:8], "duels": deaths,
                              "lineups": lineups(n, side, interest, meta) if len(n) else []}
    return res


# The maps in worker processes (16/10, the user: "encore beaucoup beaucoup trop long": one map after the other on one
# core of 24, 9 to 15 s). A worker reads its map's tables itself (a map's are hundreds of MB: never sent between
# processes) and sends back its result and, for contexts() and repeek(), its counts, added up here: the same numbers.
CTX_SPECS = None


def _ctx_specs():
    return [
        ("Teammate support", [("teammate within 600 u", lambda x: x.mate_dist < 600),
                              ("alone (teammate beyond 1,200 u or none)", lambda x: (x.mate_dist > 1200) | x.mate_dist.isna())]),
        ("Movement at the start of the duel", [("still, you hold the angle (< 40 u/s)", lambda x: x.speed < 40),
                                               ("moving, you peek (> 110 u/s)", lambda x: x.speed > 110)]),
        ("Enemy movement", [("the enemy peeks at you (> 110 u/s)", lambda x: x.opp_speed > 110),
                            ("the enemy is still (< 40 u/s)", lambda x: x.opp_speed < 40)]),
        ("Flashes", [("enemy flashed by your team", lambda x: x.opp_flashed == True),
                     ("you flashed", lambda x: x.me_flashed == True),
                     ("nobody flashed", lambda x: (x.opp_flashed == False) & (x.me_flashed == False))]),
        ("Balance of power", [("with a man advantage", lambda x: x.mates_alive > x.opp_mates_alive),
                              ("even", lambda x: x.mates_alive == x.opp_mates_alive),
                              ("outnumbered", lambda x: x.mates_alive < x.opp_mates_alive)]),
        ("Moment of the round", [("0-20 s", lambda x: x.t <= 20), ("20-45 s", lambda x: (x.t > 20) & (x.t <= 45)),
                                 ("after 45 s", lambda x: x.t > 45)]),
        ("Distance", [("short (< 10 m)", lambda x: x.distance < 10), ("medium (10-20 m)", lambda x: (x.distance >= 10) & (x.distance < 20)),
                      ("long (> 20 m)", lambda x: x.distance >= 20)]),
        ("Health at the start of the duel", [("more than 80 HP", lambda x: x.hp > 80), ("less than 50 HP", lambda x: x.hp < 50)]),
        ("Stance", [("crouched", lambda x: x.crouch == True), ("standing", lambda x: x.crouch == False)]),
    ]


def _ctx_counts(df):
    """[[(duels, won) per row] per spec] of contexts()'s table."""
    if not len(df):
        return [[(0, 0) for _ in masks] for _, masks in _ctx_specs()]
    return [[(int(len(s)), int(s.won.sum())) for s in (df[fn(df)] for _, fn in masks)] for _, masks in _ctx_specs()]


def _repeek_counts(mine):
    res = {"stayed": [0, 0], "moved": [0, 0]}
    if not len(mine):
        return res
    for _, g in mine.groupby(["match", "round"]):
        g = g.sort_values("tick").reset_index(drop=True)
        for i in range(len(g) - 1):
            a, b = g.iloc[i], g.iloc[i + 1]
            if not a.won or b.tick - a.tick > 8 * 64:
                continue
            moved = np.hypot(b.X - a.X, b.Y - a.Y)
            res["stayed" if moved < 150 else "moved"][0 if b.won else 1] += 1
    return res


def _map_part(me, match_ids, mp):
    """One map of run(), in a worker: its result, and its counts for contexts(), repeek() and the totals."""
    global ME
    ME = int(me)
    m = load(match_ids, only={mp}).get(mp)
    if m is None:
        return None
    mine, others = my_duels(m["duels"]), all_duels_pov(m["duels"])
    return {"map": per_map(mp, m, mine, others), "ctx": (_ctx_counts(mine), _ctx_counts(others)), "repeek": _repeek_counts(mine),
            "tot": (int(len(mine)), int(mine.won.sum()) if len(mine) else 0, int(len(others)), int(others.won.sum()) if len(others) else 0)}


def _won_pct(won, n):
    """round(100 * won rate) as a pandas mean gives it (a numpy number, the same value)."""
    return round(100 * np.float64(won / n))


def run_parallel(me, match_ids=None, during=None, workers=6, ex=None):
    """run() with each map in a worker process; during(), here, while they run. The same result. ex: worker processes
    to use (pipeline.pool()), else its own."""
    global ME
    ME = int(me)
    from concurrent.futures import ProcessPoolExecutor
    from wily.core import config
    facts, _, _, mine, pool, _ = _pool(match_ids)   # the per-match counts brought up to date here, read by the workers
    order = list(dict.fromkeys(facts[mid][0] for mid in pool))
    played = {mp: sum(1 for mid in pool if facts[mid][0] == mp and mid in mine) for mp in order}
    order = sorted(order, key=lambda mp: -played[mp])   # the maps as run() orders them
    own = ex is None
    if own:
        ex = ProcessPoolExecutor(max(1, min(workers, len(order))), initializer=config.low_priority)
    try:
        futs = [ex.submit(_map_part, me, match_ids, mp) for mp in order]
        if during:
            during()
        parts = [f.result() for f in futs]
    finally:
        if own:
            ex.shutdown()
    parts = [p for p in parts if p]
    out = {"maps": [p["map"] for p in parts], "contexts": None, "repeek": None}
    specs = _ctx_specs()
    add = lambda k: [[tuple(sum(p["ctx"][k][i][j][x] for p in parts) for x in (0, 1)) for j in range(len(masks))]
                     for i, (_, masks) in enumerate(specs)]
    a, b = add(0), add(1)
    out["contexts"] = [{"name": name, "rows": [{"label": label, "n": a[i][j][0], "win": _won_pct(a[i][j][1], a[i][j][0]) if a[i][j][0] else None,
                                                "others_win": _won_pct(b[i][j][1], b[i][j][0]) if b[i][j][0] else None, "others_n": b[i][j][0]}
                                               for j, (label, _) in enumerate(masks)]}
                       for i, (name, masks) in enumerate(specs)]
    rp = {k: [sum(p["repeek"][k][x] for p in parts) for x in (0, 1)] for k in ("stayed", "moved")}
    out["repeek"] = {k: {"won": v[0], "lost": v[1], "win": wr(*v)} for k, v in rp.items()}
    n_me, w_me, n_ot, w_ot = (sum(p["tot"][x] for p in parts) for x in range(4))
    out["totals"] = {"my_duels": n_me, "my_win": _won_pct(w_me, n_me), "others_duels": n_ot, "others_win": _won_pct(w_ot, n_ot)}
    return out


def run(me, match_ids=None):
    global ME
    ME = int(me)
    pm = load(match_ids)
    out = {"maps": [], "contexts": None, "repeek": None}
    all_mine, all_others = [], []
    for name, m in sorted(pm.items(), key=lambda x: -x[1]["matches"]):
        mine, others = my_duels(m["duels"]), all_duels_pov(m["duels"])   # once per map (16/10: twice)
        out["maps"].append(per_map(name, m, mine, others))
        all_mine.append(mine)
        all_others.append(others)
    mine = pd.concat(all_mine, ignore_index=True)
    others = pd.concat(all_others, ignore_index=True)
    out["contexts"] = contexts(mine, others)
    out["repeek"] = repeek(mine)
    out["totals"] = {"my_duels": int(len(mine)), "my_win": round(100 * float(mine.won.mean())), "others_duels": int(len(others)),
                     "others_win": round(100 * float(others.won.mean()))}
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    from wily.core import config
    res = run(int(sys.argv[1]) if len(sys.argv) > 1 else config.logged_in_account()[0])
    print(json.dumps(res, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
