"""Round context of a demo, next to deep.py's output (same round numbering):
  rounds.parquet    winner, end reason, bomb plant (site, time, planter), defuse, team economy per round
  loadout.parquet   per player and round: primary weapon, equipment value, money, round stats (kills, damage, survival)
  steps.parquet     running footsteps (audible), with the distance to the nearest enemy and teammate
  deaths_w.parquet  weapon in hand of the victim at each death (duels.parquet only has the killer's)

Usage: python -m wily.demos.rounds <demo.dem> <out_dir>
"""
import os
import sys

import numpy as np
import pandas as pd

TICKRATE = 64
SIDE = {2: "T", 3: "CT"}
WCLASS = {
    "AWP": "awp", "SSG 08": "scout", "G3SG1": "auto", "SCAR-20": "auto",
    "AK-47": "rifle", "M4A4": "rifle", "M4A1-S": "rifle", "AUG": "rifle", "SG 553": "rifle",
    "Galil AR": "rifle_eco", "FAMAS": "rifle_eco",
    "MAC-10": "smg", "MP9": "smg", "MP7": "smg", "MP5-SD": "smg", "UMP-45": "smg", "P90": "smg", "PP-Bizon": "smg",
    "Nova": "shotgun", "XM1014": "shotgun", "MAG-7": "shotgun", "Sawed-Off": "shotgun", "M249": "heavy", "Negev": "heavy",
}
PISTOLS = {"Glock-18", "USP-S", "P2000", "P250", "Five-SeveN", "Tec-9", "CZ75-Auto", "Desert Eagle", "Dual Berettas", "R8 Revolver"}
NADES = {"High Explosive Grenade", "Smoke Grenade", "Flashbang", "Molotov", "Incendiary Grenade", "Decoy Grenade"}
NADE_SHORT = {"Flashbang": "flash", "Smoke Grenade": "smoke", "High Explosive Grenade": "HE", "Molotov": "molotov",
              "Incendiary Grenade": "molotov", "Decoy Grenade": "decoy"}


def sid(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def buy_type(value, n, pistol_round):
    """Team equipment value -> eco / force / full (per living player, at the end of the buy period)."""
    if pistol_round:
        return "pistol"
    per = value / max(n, 1)
    return "eco" if per < 1500 else "force" if per < 3700 else "full"


# the events extract() reads, in one pass of the demo (onepass.py, 15/10)
EVENTS = {"round_freeze_end": ((), ()), "round_officially_ended": ((), ()), "round_end": ((), ()),
          "bomb_planted": (("X", "Y", "last_place_name"), ()), "bomb_defused": ((), ()), "bomb_exploded": ((), ()),
          "player_hurt": (("team_num",), ()), "player_death": (("team_num", "active_weapon_name", "last_place_name"), ()),
          "player_footstep": ((), ())}


def extract(path, out):
    from wily.demos import onepass
    p = onepass.Parser(path, EVENTS)
    freeze = p.parse_event("round_freeze_end")["tick"].tolist()
    ends = sorted(set(p.parse_event("round_officially_ended")["tick"].tolist()))
    rounds = []
    for i, ft in enumerate(freeze):
        end = min([e for e in ends if e > ft], default=ft + 115 * TICKRATE)
        rounds.append((i + 1, ft, end))
    r_start = np.array([a for _, a, _ in rounds])
    r_end = np.array([b for _, _, b in rounds])

    def rnd(t):
        idx = np.where((r_start <= t) & (t <= r_end))[0]
        return (int(idx[0]) + 1, (t - r_start[idx[0]]) / TICKRATE) if len(idx) else (None, None)

    def ev(name, **kw):
        try:
            e = p.parse_event(name, **kw)
            return e if isinstance(e, pd.DataFrame) else pd.DataFrame()
        except Exception:
            return pd.DataFrame()

    re_ = ev("round_end")
    plant = ev("bomb_planted", player=["X", "Y", "last_place_name"])
    defuse = ev("bomb_defused")
    boom = ev("bomb_exploded")

    # site letter: the place name of the planter ("BombsiteA"), else the nearest named site of this demo
    def site_of(row):
        pl = str(row.get("user_last_place_name") or "")
        if pl.lower().startswith("bombsite"):
            return pl[-1].upper()
        return None
    if len(plant):
        plant["site_l"] = [site_of(r) for _, r in plant.iterrows()]
        known = plant[plant.site_l.notna()].groupby("site")["site_l"].agg(lambda s: s.mode().iloc[0]).to_dict()
        plant["site_l"] = [s if s else known.get(i) for s, i in zip(plant.site_l, plant.site)]

    # economy: two looks per round (start of round, end of the buy period); keep the later living snapshot
    looks = sorted({t for _, a, _ in rounds for t in (a + 2 * TICKRATE, a + 18 * TICKRATE)})
    lo = p.parse_ticks(["inventory", "balance", "current_equip_value", "armor_value", "has_helmet", "has_defuser", "team_num", "is_alive"],
                       ticks=looks)
    lo["steamid"] = lo["steamid"].map(sid)
    lo = lo[lo.team_num.isin([2, 3])]
    lo["round"] = [rnd(t)[0] for t in lo.tick]
    lo = lo[lo["round"].notna()]
    first = lo.sort_values("tick").drop_duplicates(["round", "steamid"], keep="first").set_index(["round", "steamid"])
    alive = lo[lo.is_alive].sort_values("tick").drop_duplicates(["round", "steamid"], keep="last").set_index(["round", "steamid"])

    # round stats from damage and deaths
    hurt = ev("player_hurt", player=["team_num"])
    if len(hurt):
        for c in ("attacker_steamid", "user_steamid"):
            hurt[c] = hurt[c].map(sid)
        hurt = hurt[(hurt.attacker_steamid != 0) & (hurt.attacker_team_num != hurt.user_team_num)]
        hurt["round"] = [rnd(t)[0] for t in hurt.tick]
        dmg = hurt.groupby(["round", "attacker_steamid"]).dmg_health.sum()
    else:
        dmg = pd.Series(dtype=float)
    death = ev("player_death", player=["team_num", "active_weapon_name", "last_place_name"])
    for c in ("attacker_steamid", "user_steamid", "assister_steamid"):
        if c in death:
            death[c] = death[c].map(sid)
    death["round"] = [rnd(t)[0] for t in death.tick]
    death["t"] = [rnd(t)[1] for t in death.tick]
    death = death[death["round"].notna()]
    enemy_kill = death[(death.attacker_steamid != 0) & (death.attacker_steamid != death.user_steamid)
                       & (death.attacker_team_num != death.user_team_num)]
    kills = enemy_kill.groupby(["round", "attacker_steamid"]).size()
    died = death.groupby(["round", "user_steamid"]).t.min()

    n_players = first.reset_index().steamid.nunique() if len(first) else 10
    half = 8 if n_players <= 4 else 12  # Wingman: MR8, 5v5: MR12
    rows_r, rows_l = [], []
    for r, ft, end in rounds:
        rec = {"round": r, "start_tick": int(ft), "end_tick": int(end), "winner": None, "reason": None, "end_t": None}
        e = re_[(re_.tick >= ft) & (re_.tick <= end)] if len(re_) else re_
        if len(e):
            x = e.iloc[0]
            rec.update({"winner": x.winner if x.winner in ("T", "CT") else None, "reason": str(x.reason), "end_t": round((x.tick - ft) / TICKRATE, 1)})
        pl = plant[(plant.tick >= ft) & (plant.tick <= end)] if len(plant) else plant
        if len(pl):
            x = pl.iloc[0]
            rec.update({"plant_tick": int(x.tick), "plant_t": round((x.tick - ft) / TICKRATE, 1), "plant_site": x.site_l,
                        "planter": sid(x.user_steamid), "plant_X": float(x.user_X), "plant_Y": float(x.user_Y),
                        "plant_place": x.user_last_place_name})
        df = defuse[(defuse.tick >= ft) & (defuse.tick <= end)] if len(defuse) else defuse
        rec["defused"] = bool(len(df))
        bx = boom[(boom.tick >= ft) & (boom.tick <= end)] if len(boom) else boom
        rec["exploded"] = bool(len(bx))
        pistol = r in (1, half + 1)
        for team, side in ((2, "T"), (3, "CT")):
            snap = [alive.loc[(r, s)] for (rr, s) in alive.index if rr == r] if len(alive) else []
            vals = [x for x in snap if x.team_num == team]
            val = float(sum(x.current_equip_value for x in vals))
            rec[f"{side}_equip"] = val
            rec[f"{side}_n"] = len(vals)
            rec[f"{side}_buy"] = buy_type(val, len(vals), pistol)
        rows_r.append(rec)
        # per player
        for (rr, s), x in first.iterrows():
            if rr != r:
                continue
            a = alive.loc[(r, s)] if (r, s) in alive.index else x
            inv = list(a.inventory) if isinstance(a.inventory, (list, np.ndarray)) else []
            inv0 = list(x.inventory) if isinstance(x.inventory, (list, np.ndarray)) else []  # 2 s in: what was bought, before any throw
            prim = next((w for w in inv if w in WCLASS), None)
            pist = next((w for w in inv if w in PISTOLS), None)
            rows_l.append({
                "round": r, "steamid": s, "name": x["name"], "side": SIDE.get(int(x.team_num)),
                "primary": prim, "wclass": WCLASS.get(prim, "pistol"), "pistol": pist,
                "nades": int(sum(1 for w in inv if w in NADES)), "util": ",".join(sorted(NADE_SHORT[w] for w in inv if w in NADE_SHORT)),
                "buy_util": ",".join(sorted(NADE_SHORT[w] for w in inv0 if w in NADE_SHORT)),
                "armor": int(a.armor_value or 0), "helmet": bool(a.has_helmet),
                "defuser": bool(a.has_defuser), "equip": float(a.current_equip_value or 0), "money_start": int(x.balance or 0),
                "kills": int(kills.get((r, s), 0)), "damage": int(min(dmg.get((r, s), 0), 500)),
                "died_t": None if (r, s) not in died.index else round(float(died.loc[(r, s)]), 1),
            })
    R = pd.DataFrame(rows_r)
    L = pd.DataFrame(rows_l)
    if len(L) and len(R):
        win = R.set_index("round").winner
        L["won"] = [win.get(r) == sd for r, sd in zip(L["round"], L.side)]
        L["team_buy"] = [R.set_index("round").get(f"{sd}_buy", pd.Series()).get(r) if sd else None for r, sd in zip(L["round"], L.side)]
    R.to_parquet(os.path.join(out, "rounds.parquet"))
    L.to_parquet(os.path.join(out, "loadout.parquet"))

    # victim weapon at death
    dw = death[["tick", "round", "t", "user_steamid", "user_active_weapon_name", "attacker_steamid", "attacker_active_weapon_name", "weapon"]].rename(
        columns={"user_steamid": "victim", "user_active_weapon_name": "victim_weapon", "attacker_steamid": "killer",
                 "attacker_active_weapon_name": "killer_weapon_name"})
    dw.to_parquet(os.path.join(out, "deaths_w.parquet"))

    # audible footsteps: distance to the nearest living enemy / teammate at that moment
    fs = ev("player_footstep")
    if len(fs):
        fs["user_steamid"] = fs["user_steamid"].map(sid)
        fs["round"] = [rnd(t)[0] for t in fs.tick]
        fs = fs[fs["round"].notna()]
    if len(fs):
        pos = p.parse_ticks(["X", "Y", "Z", "team_num", "is_alive", "last_place_name"], ticks=sorted(set(fs.tick.astype(int))))
        pos["steamid"] = pos["steamid"].map(sid)
        pos = pos[pos.is_alive & pos.team_num.isin([2, 3])]
        g = {t: d for t, d in pos.groupby("tick")}
        rows = []
        for _, f in fs.iterrows():
            d = g.get(int(f.tick))
            if d is None:
                continue
            me = d[d.steamid == f.user_steamid]
            if not len(me):
                continue
            me = me.iloc[0]
            dist = np.sqrt((d.X - me.X) ** 2 + (d.Y - me.Y) ** 2 + ((d.Z - me.Z) * 1.0) ** 2)
            en = dist[(d.team_num != me.team_num)]
            mt = dist[(d.team_num == me.team_num) & (d.steamid != me.steamid)]
            rows.append({"tick": int(f.tick), "round": int(f["round"]), "t": round(rnd(int(f.tick))[1], 1), "steamid": int(f.user_steamid),
                         "side": SIDE.get(int(me.team_num)), "place": me.last_place_name,
                         "enemy_dist": float(en.min()) if len(en) else None, "mate_dist": float(mt.min()) if len(mt) else None,
                         "enemies_alive": int(len(en)), "mates_alive": int(len(mt))})
        pd.DataFrame(rows).to_parquet(os.path.join(out, "steps.parquet"))
    else:
        pd.DataFrame(columns=["tick", "round", "t", "steamid", "side", "place", "enemy_dist", "mate_dist", "enemies_alive", "mates_alive"]).to_parquet(
            os.path.join(out, "steps.parquet"))
    from wily.core import ledger
    ledger.touch(out)   # its files replaced in place: the steps after it see it (ledger.py)
    return len(R), len(L)


def done(out):
    if not all(os.path.exists(os.path.join(out, f)) for f in ("rounds.parquet", "loadout.parquet", "steps.parquet", "deaths_w.parquet")):
        return False
    import pyarrow.parquet as pq
    return "buy_util" in pq.read_schema(os.path.join(out, "loadout.parquet")).names  # grenades bought (types), added later


def _low_priority():
    """Worker processes run below normal priority: the game keeps the CPU when both run."""
    try:
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x00004000)
    except Exception:
        pass


def _one(args):
    dem, out = args
    try:
        return os.path.basename(out), extract(dem, out)
    except Exception as e:
        return os.path.basename(out), f"ERROR {e}"


def run_all(cache, deep_dir, workers=3, log=print):
    """Every cached demo whose deep extraction exists but has no round context yet (the ones found complete before
    are not opened again: ledger.py, 15/10)."""
    from concurrent.futures import ProcessPoolExecutor
    from wily.core import ledger
    led = ledger.Ledger(f"rounds_{os.path.basename(deep_dir)}", version="buy_util")
    dirs = ledger.folders(deep_dir)
    todo = []
    for f in os.listdir(cache):
        if f.endswith(".dem"):
            mid = f[:-4]
            if mid not in dirs or led.settled(mid, dirs[mid]):
                continue
            out = os.path.join(deep_dir, mid)
            if not os.path.exists(os.path.join(out, "meta.json")):
                continue
            if done(out):
                led.mark(mid, dirs[mid])
            else:
                todo.append((os.path.join(cache, f), out))
    led.save()
    if not todo:
        return 0
    log(f"Round context: {len(todo)} demo(s)…")
    with ProcessPoolExecutor(min(workers, len(todo)), initializer=_low_priority) as ex:
        for i, (mid, res) in enumerate(ex.map(_one, todo), 1):
            if i % 10 == 0 or isinstance(res, str):
                log(f"  {i}/{len(todo)} {mid} {res if isinstance(res, str) else ''}")
    return len(todo)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 2:
        print(extract(sys.argv[1], sys.argv[2]))
    else:
        from wily.core import config
        print(run_all(config.CACHE, config.DEEP))
