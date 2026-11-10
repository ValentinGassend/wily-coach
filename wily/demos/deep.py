"""Deep per-match extraction for cross-match analysis: duels with context, grenades with outcome, positions.

Usage: python -m wily.demos.deep <demo.dem> <out_dir>
Writes duels.parquet, grenades.parquet, samples.parquet, meta.json
"""
import json
import os
import sys

import numpy as np
import pandas as pd

from wily.core import mapdata
from wily.demos import onepass
from wily.demos.map_analysis import ZoneMap

TICKRATE = 64
SIDE = {2: "T", 3: "CT"}
NADE_EVENTS = {"weapon_smokegrenade": "smokegrenade_detonate", "weapon_flashbang": "flashbang_detonate",
               "weapon_hegrenade": "hegrenade_detonate", "weapon_molotov": "inferno_startburn",
               "weapon_incgrenade": "inferno_startburn"}
NADE_NAME = {"weapon_smokegrenade": "smoke", "weapon_flashbang": "flash", "weapon_hegrenade": "he",
             "weapon_molotov": "molotov", "weapon_incgrenade": "molotov"}
IN_ATTACK, IN_JUMP, IN_DUCK, IN_ATTACK2 = 1, 2, 4, 2048



# a grenades table's columns (read_nades gives them to an empty one)
NADE_COLS = ['tick', 'round', 't', 'type', 'thrower', 'thrower_name', 'side', 'X', 'Y', 'Z', 'pitch', 'yaw', 'px', 'py', 'level', 'zone', 'jump', 'speed', 'crouch', 'walk', 'click', 'land_X', 'land_Y', 'land_Z', 'land_px', 'land_py', 'land_level', 'land_zone', 'flight_s', 'land_tick', 'damage', 'enemies_blind', 'mates_blind', 'blind_total_s', 'kills_after']


def read_nades(path, columns=None):
    """A demo's grenades (only `columns`); a match where nobody threw any (stopped after its first round) has an
    empty table with no columns (the analyses failed on it, 04/10; Mirage's T side lost its key-round spots to it on
    05/10): it gets its columns."""
    import pyarrow.parquet as pq
    if not pq.read_schema(path).names:
        return pd.DataFrame(columns=columns or NADE_COLS)
    return pd.read_parquet(path, columns=columns)


def sid(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


# the events extract() reads, in one pass of the demo (onepass.py, 15/10)
EVENTS = {"round_freeze_end": ((), ()), "round_officially_ended": ((), ()),
          "player_death": (("X", "Y", "Z", "team_num", "last_place_name", "health"), ()),
          "player_hurt": ((), ()), "player_blind": ((), ()),
          "weapon_fire": (("X", "Y", "Z", "pitch", "yaw", "velocity_X", "velocity_Y", "velocity_Z", "is_airborne", "ducking",
                           "is_walking", "team_num", "last_place_name"), ()),
          **{ev: ((), ()) for ev in set(NADE_EVENTS.values())}}


def extract(path, out):
    os.makedirs(out, exist_ok=True)
    p = onepass.Parser(path, EVENTS)
    map_name = p.parse_header()["map_name"]
    zm = ZoneMap(map_name)
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

    # ---------- position samples (all players, every 0.5 s) ----------
    ticks = [t for _, a, b in rounds for t in range(a, b, 32)]
    sm = p.parse_ticks(["X", "Y", "Z", "team_num", "is_alive", "last_place_name", "health"], ticks=ticks)
    sm = sm[sm.is_alive].copy()
    sm["steamid"] = sm["steamid"].map(sid)
    sm["place"] = sm["last_place_name"].fillna("")
    sm["level"] = zm.level(sm.Z.values)
    sm["px"], sm["py"] = zm.px(sm.X.values, sm.Y.values)
    zm.learn_places(sm)
    sm["zone"] = zm.zone(sm.X.values, sm.Y.values, sm.place.values)
    rr = [rnd(t) for t in sm["tick"]]
    sm["round"] = [r[0] for r in rr]
    sm["t"] = [r[1] for r in rr]
    sm["side"] = sm.team_num.map(SIDE)
    sm[["tick", "steamid", "name", "side", "round", "t", "X", "Y", "Z", "px", "py", "level", "zone", "health"]].to_parquet(
        os.path.join(out, "samples.parquet"))

    # ---------- duels ----------
    k = p.parse_event("player_death", player=["X", "Y", "Z", "team_num", "last_place_name", "health"])
    for c in ("attacker_steamid", "user_steamid", "assister_steamid"):
        k[c] = k[c].map(sid)
    k = k[(k.attacker_steamid != 0) & (k.attacker_steamid != k.user_steamid) & (k.attacker_team_num != k.user_team_num)].copy()
    rr = [rnd(t) for t in k["tick"]]
    k["round"] = [r[0] for r in rr]
    k["t"] = [r[1] for r in rr]
    k = k[k["round"].notna()].sort_values("tick").reset_index(drop=True)

    hurt = p.parse_event("player_hurt")
    for c in ("attacker_steamid", "user_steamid"):
        hurt[c] = hurt[c].map(sid)
    blind = p.parse_event("player_blind")
    if not isinstance(blind, pd.DataFrame) or not len(blind):  # some tournament demos do not record it
        blind = pd.DataFrame(columns=["tick", "attacker_steamid", "user_steamid", "blind_duration"])
    for c in ("attacker_steamid", "user_steamid"):
        blind[c] = blind[c].map(sid)

    # duel start = first damage exchanged between the two within 5 s before the kill
    starts = []
    for _, d in k.iterrows():
        a, v = d.attacker_steamid, d.user_steamid
        h = hurt[(hurt.tick <= d.tick) & (hurt.tick >= d.tick - 5 * TICKRATE) &
                 (((hurt.attacker_steamid == a) & (hurt.user_steamid == v)) |
                  ((hurt.attacker_steamid == v) & (hurt.user_steamid == a)))]
        starts.append(int(h.tick.min()) if len(h) else int(d.tick))
    k["duel_start"] = starts
    probe = sorted({max(t - 4, 0) for t in starts} | {max(t - 12, 0) for t in starts} | {int(t) - 1 for t in k.tick})
    snap = p.parse_ticks(["X", "Y", "Z", "team_num", "is_alive", "health", "ducking", "is_scoped"], ticks=probe)
    snap["steamid"] = snap["steamid"].map(sid)
    snap = snap.set_index(["tick", "steamid"]).sort_index()

    def at(t, s):
        try:
            v = snap.loc[(t, s)]
            return v.iloc[0] if isinstance(v, pd.DataFrame) else v
        except KeyError:
            return None

    rows = []
    for _, d in k.iterrows():
        a, v, ts = d.attacker_steamid, d.user_steamid, int(d.duel_start)
        rec = {"tick": int(d.tick), "round": int(d["round"]), "t": round(float(d.t), 1),
               "killer": a, "victim": v, "killer_name": d.attacker_name, "victim_name": d.user_name,
               "killer_side": SIDE.get(d.attacker_team_num), "victim_side": SIDE.get(d.user_team_num),
               "weapon": d.weapon, "headshot": bool(d.headshot), "distance": float(d.distance) if pd.notna(d.distance) else None,
               "duel_len_s": round((d.tick - ts) / TICKRATE, 2)}
        for role, s, prefix in (("killer", a, "attacker"), ("victim", v, "user")):
            x, y, z = d[f"{prefix}_X"], d[f"{prefix}_Y"], d[f"{prefix}_Z"]
            px, py = zm.px(x, y)
            rec[f"{role}_X"], rec[f"{role}_Y"], rec[f"{role}_Z"] = float(x), float(y), float(z)
            rec[f"{role}_px"], rec[f"{role}_py"] = float(px), float(py)
            rec[f"{role}_level"] = zm.level(z)[0]
            place = d.get(f"{prefix}_last_place_name") or ""
            rec[f"{role}_zone"] = zm.zone([x], [y], [place])[0]
            s1, s0 = at(max(ts - 4, 0), s), at(max(ts - 12, 0), s)
            if s1 is not None and s0 is not None:
                rec[f"{role}_speed"] = float(np.hypot(s1.X - s0.X, s1.Y - s0.Y) / (8 / TICKRATE))
                rec[f"{role}_hp"] = int(s1.health)
                rec[f"{role}_crouch"] = bool(s1.ducking)
                rec[f"{role}_scoped"] = bool(s1.is_scoped)
            # support: nearest living teammate at the kill
            me_row = at(int(d.tick) - 1, s)
            if me_row is not None:
                tk = snap.xs(int(d.tick) - 1, level="tick")
                mates = tk[(tk.team_num == me_row.team_num) & tk.is_alive & (tk.index != s)]
                dist = np.hypot(mates.X - me_row.X, mates.Y - me_row.Y)
                rec[f"{role}_mate_dist"] = float(dist.min()) if len(dist) else None
                rec[f"{role}_mates_alive"] = int(len(mates))
        # was the victim blinded by the killer's team just before
        fl = blind[(blind.user_steamid == v) & (blind.tick <= d.tick) & (blind.tick >= d.tick - int(2.5 * TICKRATE)) &
                   (blind.blind_duration >= 0.7)]
        rec["victim_flashed"] = bool(len(fl[fl.attacker_steamid != v]))
        fl2 = blind[(blind.user_steamid == a) & (blind.tick <= d.tick) & (blind.tick >= d.tick - int(2.5 * TICKRATE)) &
                    (blind.blind_duration >= 0.7)]
        rec["killer_flashed"] = bool(len(fl2))
        # traded: victim's side kills the killer within 5 s
        rec["traded"] = bool(((k.user_steamid == a) & (k.tick > d.tick) & (k.tick <= d.tick + 5 * TICKRATE)).any())
        rows.append(rec)
    duels = pd.DataFrame(rows)
    duels["opening"] = ~duels.duplicated("round")
    duels.to_parquet(os.path.join(out, "duels.parquet"))

    # ---------- grenades ----------
    wf = p.parse_event("weapon_fire", player=["X", "Y", "Z", "pitch", "yaw", "velocity_X", "velocity_Y", "velocity_Z",
                                                "is_airborne", "ducking", "is_walking", "team_num", "last_place_name"])
    wf = wf[wf.weapon.isin(NADE_EVENTS)].copy()
    wf["user_steamid"] = wf["user_steamid"].map(sid)
    # which mouse button was held just before release
    try:
        bt = p.parse_ticks(["buttons"], ticks=sorted({max(int(t) - 3, 0) for t in wf.tick}))
        bt["steamid"] = bt["steamid"].map(sid)
        bt = bt.set_index(["tick", "steamid"])["buttons"]
    except Exception:  # not recorded in every demo version
        bt = pd.Series(dtype=float)
    det = {}
    for ev in set(NADE_EVENTS.values()):
        e = p.parse_event(ev)
        if not isinstance(e, pd.DataFrame) or not len(e):
            e = pd.DataFrame(columns=["tick", "user_steamid", "x", "y", "z"])
        e["user_steamid"] = e["user_steamid"].map(sid)
        det[ev] = e.sort_values("tick")
    used = set()
    grows = []
    for _, g in wf.sort_values("tick").iterrows():
        ev = NADE_EVENTS[g.weapon]
        e = det[ev]
        cand = e[(e.user_steamid == g.user_steamid) & (e.tick > g.tick) & (e.tick <= g.tick + 15 * TICKRATE)]
        cand = cand[~cand.index.map(lambda i: (ev, i) in used)]
        land = cand.iloc[0] if len(cand) else None
        if land is not None:
            used.add((ev, land.name))
        r, t = rnd(int(g.tick))
        if r is None:
            continue
        try:
            b = int(bt.loc[(max(int(g.tick) - 3, 0), g.user_steamid)])
        except (KeyError, TypeError, ValueError, pd.errors.IndexingError):
            b = None
        side = SIDE.get(g.user_team_num)
        px, py = zm.px(g.user_X, g.user_Y)
        rec = {"tick": int(g.tick), "round": r, "t": round(t, 1), "type": NADE_NAME[g.weapon],
               "thrower": g.user_steamid, "thrower_name": g.user_name, "side": side,
               "X": float(g.user_X), "Y": float(g.user_Y), "Z": float(g.user_Z),
               "pitch": float(g.user_pitch), "yaw": float(g.user_yaw),
               "px": float(px), "py": float(py), "level": zm.level(g.user_Z)[0],
               "zone": zm.zone([g.user_X], [g.user_Y], [g.user_last_place_name or ""])[0],
               "jump": bool(g.user_is_airborne) or abs(float(g.user_velocity_Z)) > 1,
               "speed": float(np.hypot(g.user_velocity_X, g.user_velocity_Y)), "crouch": bool(g.user_ducking),
               "walk": bool(g.user_is_walking),
               "click": None if b is None else ("right" if (b & IN_ATTACK2 and not b & IN_ATTACK) else
                                                ("middle" if (b & IN_ATTACK2 and b & IN_ATTACK) else "left"))}
        if land is not None:
            lx, ly = zm.px(land.x, land.y)
            rec.update({"land_X": float(land.x), "land_Y": float(land.y), "land_Z": float(land.z), "land_px": float(lx), "land_py": float(ly),
                        "land_level": zm.level(land.z)[0], "land_zone": zm.zone([land.x], [land.y], [""])[0] if zm.manual else None,
                        "flight_s": round((land.tick - g.tick) / TICKRATE, 2), "land_tick": int(land.tick)})
            lt = int(land.tick)
            if rec["type"] == "flash":
                bl = blind[(blind.attacker_steamid == g.user_steamid) & (blind.tick >= lt - 2) & (blind.tick <= lt + 4)]
                team_of = sm.drop_duplicates("steamid").set_index("steamid")["side"]
                bl = bl.assign(vside=bl.user_steamid.map(team_of))
                rec["enemies_blind"] = int(((bl.vside != side) & (bl.blind_duration >= 1.5)).sum())
                rec["mates_blind"] = int(((bl.vside == side) & (bl.user_steamid != g.user_steamid) & (bl.blind_duration >= 1.0)).sum())
                rec["blind_total_s"] = round(float(bl[bl.vside != side].blind_duration.sum()), 1)
                fk = duels[(duels.tick > lt) & (duels.tick <= lt + 3 * TICKRATE) & (duels.killer_side == side) & duels.victim_flashed]
                rec["kills_after"] = int(len(fk))
            elif rec["type"] in ("he", "molotov"):
                w = ["hegrenade"] if rec["type"] == "he" else ["inferno", "molotov", "incgrenade"]
                span = 2 if rec["type"] == "he" else 8 * TICKRATE
                hh = hurt[(hurt.attacker_steamid == g.user_steamid) & hurt.weapon.isin(w) & (hurt.tick >= lt - 2) & (hurt.tick <= lt + span)]
                team_of = sm.drop_duplicates("steamid").set_index("steamid")["side"]
                rec["damage"] = int(hh[hh.user_steamid.map(team_of) != side].dmg_health.sum())
        grows.append(rec)
    nades = pd.DataFrame(grows)
    if len(nades) and not zm.manual and "land_X" in nades:
        # callout maps: landing zone = most common place of players near the landing point
        pl = sm[sm.zone != "?"][["X", "Y", "Z", "zone"]].to_numpy()
        coords = pl[:, :3].astype(float)

        def near_zone(x, y, z):
            if pd.isna(x):
                return None
            dd = (coords[:, 0] - x) ** 2 + (coords[:, 1] - y) ** 2 + ((coords[:, 2] - z) * 2) ** 2
            return pl[dd.argmin(), 3]
        nades["land_zone"] = [near_zone(x, y, z) for x, y, z in zip(nades.land_X, nades.land_Y, nades.land_Z)]
    if not len(nades.columns):   # nobody threw a grenade (a match stopped after a round): the table keeps its columns
        nades = pd.DataFrame(columns=NADE_COLS)
    nades.to_parquet(os.path.join(out, "grenades.parquet"))

    meta = {"map": map_name, "rounds": len(rounds),
            "zones": [{"key": z[0], "name": z[1], "px": [z[2], z[3]], "level": z[4]} for z in zm.zones],
            "zone_mode": "manual" if zm.manual else "callouts",
            "levels": [{kk: vv for kk, vv in lv.items() if kk != "image_path"} for lv in zm.cfg["levels"]]}
    json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False)
    from wily.core import ledger
    ledger.touch(out)   # extracted again in place: the steps after it see it (ledger.py)
    return len(duels), len(nades)


if __name__ == "__main__":
    print(extract(sys.argv[1], sys.argv[2]))
