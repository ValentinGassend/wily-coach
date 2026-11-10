"""Per-player metrics for EVERY player of a demo (reference population).

Usage: python -m wily.demos.population            # all cached demos with a deep extraction
       python -m wily.demos.population --reads    # the analyst's reads (clutches, flashes used, untraded deaths) of the
                                       # matches computed before they were measured
Writes out/population/<match_id>.parquet (one row per player of the match).
"""
import math
import os
import sys

import numpy as np
import pandas as pd
from demoparser2 import DemoParser

from wily.core import config
from wily.core import ledger

TICK = 64
GRENADE_INV = {"Flashbang", "High Explosive Grenade", "Smoke Grenade", "Molotov", "Incendiary Grenade", "Decoy Grenade"}
NADE_W = {"weapon_flashbang", "weapon_hegrenade", "weapon_smokegrenade", "weapon_molotov", "weapon_incgrenade", "weapon_decoy"}
RIFLES = {"weapon_ak47", "weapon_m4a1", "weapon_m4a1_silencer", "weapon_aug", "weapon_sg556", "weapon_famas", "weapon_galilar"}
SNIPERS = {"weapon_awp", "weapon_ssg08"}
PISTOLS = {"weapon_glock", "weapon_usp_silencer", "weapon_hkp2000", "weapon_p250", "weapon_fiveseven", "weapon_tec9",
           "weapon_cz75a", "weapon_deagle", "weapon_elite", "weapon_revolver"}
SKILL = ["", "Silver I", "Silver II", "Silver III", "Silver IV", "Silver Elite", "Silver Elite Master", "Gold Nova I",
         "Gold Nova II", "Gold Nova III", "Gold Nova Master", "Master Guardian I", "Master Guardian II",
         "Master Guardian Elite", "Distinguished Master Guardian", "Legendary Eagle", "Legendary Eagle Master",
         "Supreme Master First Class", "Global Elite"]
OUT = os.path.join(config.OUT, "population")
SEEN_S = 1   # an enemy who saw you in the second before a hit counts as seeing you
CLUTCH_COLS = {"clutch_n": 0, "clutch_won": 0, "clutch_multi": 0, "clutch_rounds": "", "clutch_multi_rounds": ""}
READ_COLS = {**CLUTCH_COLS, "flash_blind": 0, "flash_used": 0, "dead_n": 0, "untraded_n": 0}
BLIND_S = 1.5     # a flash that blinds an enemy longer than this is a real flash
TRADE_S = 5       # a teammate kills your killer this soon: traded
IMPACT_S = 3      # your damage this long before your death: not a death without impact


def sid(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def _clutches(p, hurt, deaths, samples, rounds):
    """Every player's 1v2+ clutches: the moment they are the last one alive of their team with 2 enemies or more
    left. Per player: how many, how many won, and in how many they took damage while 2 enemies or more saw them
    (the demo's approximate_spotted_by over the second before each hit: it updates in steps), with the rounds. hurt, deaths: the demo's events (steamids as
    ints); samples: the side of each player per round; rounds: rounds.parquet."""
    sides = {int(n): dict(zip(g.steamid.astype("int64"), g.side))
             for n, g in samples.drop_duplicates(["round", "steamid"]).groupby("round")}
    deaths = deaths.sort_values("tick")
    found = []   # (player, round, start tick, end tick, enemies left, won)
    for _, R in rounds.iterrows():
        n = int(R["round"])
        pl = {s: sd for s, sd in sides.get(n, {}).items() if s and sd in ("T", "CT")}
        alive = {"T": {s for s, sd in pl.items() if sd == "T"}, "CT": {s for s, sd in pl.items() if sd == "CT"}}
        t_end = int(R.end_tick) if pd.notna(R.end_tick) else int(deaths.tick.max() if len(deaths) else 0)
        rd = deaths[(deaths.tick >= R.start_tick) & (deaths.tick <= t_end)]
        done = set()
        for v, t in zip(rd.user_steamid, rd.tick):
            sd = pl.get(v)
            if sd is None or v not in alive[sd]:
                continue
            alive[sd].discard(v)
            other = "CT" if sd == "T" else "T"
            if sd not in done and len(alive[sd]) == 1 and len(alive[other]) >= 2:
                done.add(sd)
                me = next(iter(alive[sd]))
                mine = rd[(rd.user_steamid == me) & (rd.tick > t)]
                end = int(mine.tick.iloc[0]) if len(mine) else t_end
                found.append((me, n, int(t), end, set(alive[other]), R.winner == sd))
    hits = {}
    for me, n, t0, t1, foes, _ in found:
        h = hurt[(hurt.user_steamid == me) & (hurt.tick > t0) & (hurt.tick <= t1) & hurt.attacker_steamid.isin(foes)]
        hits[(me, n)] = sorted(set(int(x) for x in h.tick))
    ticks = sorted({t - d for v in hits.values() for t in v for d in range(0, SEEN_S * TICK + 1, 8)})
    seen = {}
    if ticks:
        sp = p.parse_ticks(["approximate_spotted_by"], ticks=ticks)
        for t, s_, by in zip(sp.tick, sp.steamid, sp.approximate_spotted_by):
            seen[(int(t), sid(s_))] = {sid(x) for x in (by if isinstance(by, (list, np.ndarray)) else [])}
    out = {}
    for me, n, t0, t1, foes, won in found:
        o = out.setdefault(me, {k: (v if not isinstance(v, str) else []) for k, v in CLUTCH_COLS.items()})
        o["clutch_n"] += 1
        o["clutch_won"] += int(won)
        o["clutch_rounds"].append(n)
        dead = deaths[deaths.user_steamid.isin(foes) & (deaths.tick > t0)]
        for t in hits[(me, n)]:
            left = foes - set(dead[dead.tick < t].user_steamid)
            saw = set().union(*(seen.get((t - d, me), set()) for d in range(0, SEEN_S * TICK + 1, 8)))
            if len(saw & left) >= 2:
                o["clutch_multi"] += 1
                o["clutch_multi_rounds"].append(n)
                break
    for o in out.values():
        o["clutch_rounds"] = ",".join(map(str, o["clutch_rounds"]))
        o["clutch_multi_rounds"] = ",".join(map(str, o["clutch_multi_rounds"]))
    return out


def _flashes_trades(p, hurt, deaths, samples, rounds):
    """Every player's flashes that their team uses (enemies blinded over 1.5 s, and the ones the team hits while
    blind) and deaths without impact (no trade within 5 s, no damage of theirs in the 3 s before): the same reads as
    pro_analyst, for the whole base."""
    sides = {int(n): dict(zip(g.steamid.astype("int64"), g.side))
             for n, g in samples.drop_duplicates(["round", "steamid"]).groupby("round")}
    starts = rounds.sort_values("start_tick")
    st_t, st_n = starts.start_tick.to_numpy(), starts["round"].to_numpy()

    def round_of(t):
        i = int(np.searchsorted(st_t, t, side="right")) - 1
        return int(st_n[i]) if i >= 0 else None

    out = {}

    def add(s, k, v=1):
        o = out.setdefault(s, {"flash_blind": 0, "flash_used": 0, "dead_n": 0, "untraded_n": 0})
        o[k] += v
    try:
        blind = p.parse_event("player_blind")
    except Exception:
        blind = pd.DataFrame()
    if len(blind):
        for c in ("attacker_steamid", "user_steamid"):
            blind[c] = blind[c].map(sid)
        for a, u, t, dur in zip(blind.attacker_steamid, blind.user_steamid, blind.tick, blind.blind_duration):
            if not dur or dur <= BLIND_S:
                continue
            sd = sides.get(round_of(t), {})
            sa, su = sd.get(a), sd.get(u)
            if not sa or not su or sa == su:
                continue
            add(a, "flash_blind")
            team = [s for s, x in sd.items() if x == sa]
            hit = hurt[(hurt.user_steamid == u) & (hurt.tick >= t) & (hurt.tick <= t + dur * TICK) & hurt.attacker_steamid.isin(team)]
            if len(hit):
                add(a, "flash_used")
    for v, k, t in zip(deaths.user_steamid, deaths.attacker_steamid, deaths.tick):
        sd = sides.get(round_of(t), {})
        sv, sk = sd.get(v), sd.get(k)
        if not sv or not sk or sv == sk:
            continue
        add(v, "dead_n")
        mates = [s for s, x in sd.items() if x == sv]
        traded = ((deaths.user_steamid == k) & (deaths.tick > t) & (deaths.tick <= t + TRADE_S * TICK)
                  & deaths.attacker_steamid.isin(mates)).any()
        foes = [s for s, x in sd.items() if x == sk]
        impact = ((hurt.attacker_steamid == v) & (hurt.tick <= t) & (hurt.tick >= t - IMPACT_S * TICK)
                  & hurt.user_steamid.isin(foes)).any()
        if not traded and not impact:
            add(v, "untraded_n")
    return out


def _read_cols(mid, p, hurt, deaths, samples):
    """The analyst's reads of every player of a match of the base (its rounds from the detailed extraction): the 1v2+
    clutches, the flashes used, the deaths without impact. {} without the rounds."""
    f = os.path.join(config.DEEP, mid, "rounds.parquet")
    if not os.path.exists(f):
        return {}
    rounds = pd.read_parquet(f)
    out = _clutches(p, hurt, deaths, samples, rounds)
    for s, o in _flashes_trades(p, hurt, deaths, samples, rounds).items():
        out.setdefault(s, {}).update(o)
    return out


def add_reads(mid):
    """The analyst's reads for a match of the base computed before they existed: True when added."""
    f = os.path.join(OUT, f"{mid}.parquet")
    df = pd.read_parquet(f)
    if "untraded_n" in df.columns:
        return False
    p = DemoParser(config.demo(mid))
    hurt = p.parse_event("player_hurt")
    deaths = p.parse_event("player_death")
    for d in (hurt, deaths):
        for c in ("attacker_steamid", "user_steamid"):
            d[c] = d[c].map(sid)
    samples = pd.read_parquet(os.path.join(config.DEEP, mid, "samples.parquet"), columns=["steamid", "side", "round"])
    cl = _read_cols(mid, p, hurt, deaths, samples)
    for k, v in READ_COLS.items():
        df[k] = [cl.get(int(x), {}).get(k, v) for x in df.steamid]
    df.to_parquet(f)
    return True


# the events extract() reads, in one pass of the demo (onepass.py, 15/10)
EVENTS = {"round_freeze_end": ((), ()), "rank_update": ((), ()), "player_hurt": ((), ()), "player_death": ((), ()),
          "weapon_fire": (("velocity_X", "velocity_Y"), ()), "player_blind": ((), ())}


def extract(mid):
    dem = config.demo(mid)
    ddir = os.path.join(config.DEEP, mid)
    duels = pd.read_parquet(os.path.join(ddir, "duels.parquet"))
    nades = __import__("wily.demos.deep", fromlist=["deep"]).read_nades(os.path.join(ddir, "grenades.parquet"))
    samples = pd.read_parquet(os.path.join(ddir, "samples.parquet"), columns=["steamid", "name", "side", "round"])
    from wily.demos import onepass
    p = onepass.Parser(dem, EVENTS)
    hdr = p.parse_header()
    freeze = p.parse_event("round_freeze_end")["tick"].tolist()
    n_rounds = len(freeze)
    players = samples.drop_duplicates("steamid")[["steamid", "name"]]
    players = players[players.steamid != 0]

    # ranks
    rank = {}
    try:
        ru = p.parse_event("rank_update")
        ru["user_steamid"] = ru["user_steamid"].map(sid)
        for _, r in ru.iterrows():
            rank[r.user_steamid] = (int(r.rank_type_id), int(r.rank_old or 0), int(r.rank_new or 0))
    except Exception:
        pass

    # damage (capped to remaining health)
    hurt = p.parse_event("player_hurt")
    for c in ("attacker_steamid", "user_steamid"):
        hurt[c] = hurt[c].map(sid)
    hurt = hurt.sort_values("tick")
    team_at = p.parse_ticks(["team_num"], ticks=[freeze[0] + 1, freeze[-1] + 1] if freeze else [0])
    team_at["steamid"] = team_at["steamid"].map(sid)
    hp, real = {}, []
    rid = np.searchsorted(np.array(freeze), hurt.tick.values, side="right")
    for (r_, v, d, h) in zip(rid, hurt.user_steamid, hurt.dmg_health, hurt.health):
        before = hp.get((r_, v), 100)
        real.append(min(int(d), before))
        hp[(r_, v)] = max(int(h), 0)
    hurt["real"] = real
    hurt["weapon_full"] = "weapon_" + hurt.weapon.astype(str)
    deaths = p.parse_event("player_death")
    for c in ("attacker_steamid", "user_steamid", "assister_steamid"):
        deaths[c] = deaths[c].map(sid)
    enemy_hurt = hurt[hurt.attacker_steamid != hurt.user_steamid]
    reads = _read_cols(mid, p, hurt, deaths, samples)

    # grenades still in inventory at death
    dticks = sorted({max(int(t) - 2, 0) for t in deaths.tick})
    inv = p.parse_ticks(["inventory"], ticks=dticks) if dticks else pd.DataFrame(columns=["tick", "steamid", "inventory"])
    inv["steamid"] = inv["steamid"].map(sid)
    inv = inv.set_index(["tick", "steamid"])["inventory"]
    unused = {}
    for _, d in deaths.iterrows():
        try:
            items = inv.loc[(max(int(d.tick) - 2, 0), d.user_steamid)]
            unused[d.user_steamid] = unused.get(d.user_steamid, 0) + sum(1 for x in items if x in GRENADE_INV)
        except (KeyError, TypeError):
            pass

    # economy at freeze end: money left vs poorest teammate
    eco = p.parse_ticks(["balance", "current_equip_value", "round_start_equip_value", "team_num", "inventory"], ticks=freeze)
    eco["steamid"] = eco["steamid"].map(sid)
    drops, bought = {}, {}
    for t, g in eco.groupby("tick"):
        g = g.assign(start=g.balance + g.current_equip_value - g.round_start_equip_value.fillna(0))
        for team, tg in g.groupby("team_num"):
            poorest = tg.start.min()
            for _, r in tg.iterrows():
                if r.balance >= 3000 and poorest < 2500:
                    drops[r.steamid] = drops.get(r.steamid, 0) + 1
        for _, r in g.iterrows():
            bought[r.steamid] = bought.get(r.steamid, 0) + sum(1 for x in (r.inventory if isinstance(r.inventory, (list, np.ndarray)) else []) if x in GRENADE_INV)

    # shooting: moving shots, spray
    wf = p.parse_event("weapon_fire", player=["velocity_X", "velocity_Y"])
    wf["user_steamid"] = wf["user_steamid"].map(sid)
    wf["speed"] = np.hypot(wf.user_velocity_X, wf.user_velocity_Y)
    shoot = {}
    hit_ticks = hurt.groupby("attacker_steamid").tick.apply(set).to_dict()
    for s, g in wf.groupby("user_steamid"):
        pis, rif = g[g.weapon.isin(PISTOLS)], g[g.weapon.isin(RIFLES)]
        rs = rif.sort_values("tick")
        idx, last, i = [], -999, 0
        for t in rs.tick:
            i = i + 1 if t - last <= 10 else 1
            idx.append(i)
            last = t
        hits = hit_ticks.get(s, set())
        rs = rs.assign(b=idx, hit=[any((t + k) in hits for k in range(3)) for t in rs.tick])
        shoot[s] = {"pistol_shots": len(pis), "pistol_moving": float((pis.speed > 85).mean() * 100) if len(pis) else None,
                    "rifle_shots": len(rif), "rifle_moving": float((rif.speed > 75).mean() * 100) if len(rif) else None,
                    "b1_hit": float(rs[rs.b == 1].hit.mean() * 100) if (rs.b == 1).sum() else None,
                    "b9_hit": float(rs[rs.b >= 9].hit.mean() * 100) if (rs.b >= 9).sum() else None,
                    "b9_shots": int((rs.b >= 9).sum()), "b1_shots": int((rs.b == 1).sum())}

    # crosshair placement: angle to the head ~125 ms before the first shot of each engagement
    eng = enemy_hurt[~enemy_hurt.weapon.isin(["hegrenade", "inferno", "molotov", "incgrenade", "flashbang", "smokegrenade", "knife"])]
    fires = wf[~wf.weapon.isin(NADE_W)][["tick", "user_steamid"]].sort_values("tick")
    samples_x, last_hit = [], {}
    fire_by = {s: g.tick.values for s, g in fires.groupby("user_steamid")}
    for a, v, t in zip(eng.attacker_steamid, eng.user_steamid, eng.tick):
        k = (a, v)
        if k in last_hit and t - last_hit[k] < 3 * TICK:
            last_hit[k] = t
            continue
        last_hit[k] = t
        ft = fire_by.get(a)
        if ft is None:
            continue
        w = ft[(ft <= t) & (ft >= t - TICK)]
        if len(w):
            samples_x.append((int(w.min()) - 8, a, v))
    xh = {}
    if samples_x:
        pos = p.parse_ticks(["X", "Y", "Z", "pitch", "yaw", "ducking"], ticks=sorted({t for t, _, _ in samples_x}))
        pos["steamid"] = pos["steamid"].map(sid)
        pos = pos.set_index(["tick", "steamid"])
        for t, a, v in samples_x:
            try:
                m, e = pos.loc[(t, a)], pos.loc[(t, v)]
            except KeyError:
                continue
            ex, ey, ez = m.X, m.Y, m.Z + (46 if m.ducking else 64)
            tx, ty, tz = e.X, e.Y, e.Z + (46 if e.ducking else 64)
            pr, yr = math.radians(m.pitch), math.radians(m.yaw)
            view = np.array([math.cos(pr) * math.cos(yr), math.cos(pr) * math.sin(yr), -math.sin(pr)])
            to = np.array([tx - ex, ty - ey, tz - ez])
            n = np.linalg.norm(to)
            if n < 1:
                continue
            xh.setdefault(a, []).append(math.degrees(math.acos(max(-1, min(1, float(view @ (to / n)))))))

    rows = []
    for _, pl in players.iterrows():
        s = pl.steamid
        k_ = duels[duels.killer == s]
        d_ = duels[duels.victim == s]
        a_ = deaths[(deaths.assister_steamid == s)]
        side_rounds = samples[samples.steamid == s].drop_duplicates("round").side.value_counts().to_dict()
        pov = pd.concat([pd.DataFrame({"won": True, "speed": k_.killer_speed, "hp": k_.killer_hp, "dist": k_.distance,
                                       "oppfl": k_.victim_flashed, "mates": k_.killer_mates_alive, "opp": k_.victim_mates_alive}),
                         pd.DataFrame({"won": False, "speed": d_.victim_speed, "hp": d_.victim_hp, "dist": d_.distance,
                                       "oppfl": d_.killer_flashed, "mates": d_.victim_mates_alive, "opp": d_.killer_mates_alive})])
        wr = lambda m: (float(pov[m].won.mean() * 100), int(m.sum())) if m.sum() else (None, 0)
        hold, n_hold = wr(pov.speed < 40)
        peek, n_peek = wr(pov.speed > 110)
        low, n_low = wr(pov.hp < 50)
        far, n_far = wr(pov.dist >= 20)
        close, n_close = wr(pov.dist < 10)
        my_n = nades[nades.thrower == s]
        fl = my_n[my_n.type == "flash"]
        rt = rank.get(s, (None, None, None))
        kills, dths = len(k_), len(d_)
        sh = shoot.get(s, {})
        xs = xh.get(s, [])
        rows.append({
            "match": mid, "map": hdr.get("map_name"), "steamid": str(s), "name": pl["name"], "rounds": n_rounds,
            "rank_type": rt[0], "rank": rt[2] or rt[1] or None,
            "kills": kills, "deaths": dths, "assists": len(a_),
            "adr": float(enemy_hurt[enemy_hurt.attacker_steamid == s].real.sum() / max(n_rounds, 1)),
            "hs_pct": float(k_.headshot.mean() * 100) if kills else None,
            "traded_pct": float(d_.traded.mean() * 100) if dths else None,
            "open_won": int(k_.opening.sum()), "open_lost": int(d_.opening.sum()),
            "nades_unused": unused.get(s, 0), "nades_owned": bought.get(s, 0),
            "flashes": int(len(fl)), "flash_enemies": int(fl.enemies_blind.fillna(0).sum()) if len(fl) else 0,
            "flash_mates": int(fl.mates_blind.fillna(0).sum()) if len(fl) else 0,
            "util_dmg": float(my_n.damage.fillna(0).sum()) if "damage" in my_n else 0.0,
            "drops_missed": drops.get(s, 0),
            "early_deaths": int((d_.t <= 20).sum()), "last_alive_deaths": int((d_.victim_mates_alive == 0).sum()),
            "hold_win": hold, "n_hold": n_hold, "peek_win": peek, "n_peek": n_peek,
            "lowhp_win": low, "n_lowhp": n_low, "far_win": far, "n_far": n_far, "close_win": close, "n_close": n_close,
            "flash_duels": int(pov.oppfl.fillna(False).astype(bool).sum()), "duels": int(len(pov)),
            "xhair": float(np.median(xs)) if len(xs) >= 5 else None, "n_xhair": len(xs),
            **sh, **{k: reads.get(int(s), {}).get(k, v) for k, v in READ_COLS.items()},
        })
    df = pd.DataFrame(rows)
    os.makedirs(OUT, exist_ok=True)
    df.to_parquet(os.path.join(OUT, f"{mid}.parquet"))
    return df


def run_all(force=False):
    done = 0
    have = set() if force else ledger.names(OUT)   # 15/10: one read of each folder, not file checks per match
    dems = ledger.names(config.CACHE, ".dem")
    for mid in sorted(os.listdir(config.DEEP)):
        if mid in have or mid not in dems:
            continue
        if not os.path.exists(os.path.join(config.DEEP, mid, "meta.json")):
            continue
        try:
            extract(mid)
            done += 1
            print(f"[{mid}] population OK", flush=True)
        except Exception as e:
            print(f"[{mid}] population ERROR {e}", flush=True)
    return done


def load():
    """Every match's population as one (kept consolidated: only the new matches' files are read, ledger.py)."""
    return ledger.stacked(OUT, "population", only=lambda f: f[:-8].isdigit())   # not nades.parquet, tside_all.parquet


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--reads" in sys.argv:
        for f in sorted(os.listdir(OUT)):
            if f.endswith(".parquet") and os.path.exists(os.path.join(config.CACHE, f[:-8] + ".dem")):
                try:
                    print(f[:-8], "added" if add_reads(f[:-8]) else "already", flush=True)
                except Exception as e:
                    print(f[:-8], "ERROR", e, flush=True)
        sys.exit()
    run_all("--force" in sys.argv)
    df = load()
    print(len(df), "player-match rows,", df.steamid.nunique() if len(df) else 0, "players")
