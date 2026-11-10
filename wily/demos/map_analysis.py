"""Map-level analysis: strong/weak zones per side (all players) and for one player.

Usage: python -m wily.demos.map_analysis <demo.dem> [steamid64] > map.json
"""
import importlib
import json
import math
import re
import sys
from collections import defaultdict

import numpy as np
import pandas as pd

from wily.core import mapdata

ME_DEFAULT = None  # defaults to the Steam account logged in on this PC
TICKRATE = 64
SAMPLE_EVERY = 16
SIDE = {2: "T", 3: "CT"}
PHASES = ((0, 20, "0-20s"), (20, 45, "20-45s"), (45, 999, "45s+"))


def sid(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def humanize(place, mp=None):
    """A place of the game as players call it: the pro / FACEIT callout on that map when there is one (callouts.py),
    else the game's name spaced out ("BackofB" -> "Back of B")."""
    from wily.core import callouts
    c = callouts.name(place, mp)
    if c:
        return c
    s = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[A-Z])(?=[A-Z][a-z])", " ", place)
    s = re.sub(r"\b(Back|Top|Bottom|Side)of\b", r"\1 of", s)
    return s.strip() or "?"


class ZoneMap:
    """Zones from hand-made anchors (zones_<map>.py) or from the game's callouts (last_place_name)."""

    def __init__(self, map_name):
        self.map = map_name
        self.cfg = mapdata.get(map_name)
        try:
            mod = importlib.import_module(f"wily.demos.zones_{map_name.split('_', 1)[1]}")
            self.zones = [(k, n, x, y, self.cfg["levels"][0]["key"]) for k, n, x, y in mod.ZONES]
            self.manual = True
        except ModuleNotFoundError:
            self.zones, self.manual = [], False
        self.anchors = np.array([[z[2], z[3]] for z in self.zones], dtype=float) if self.zones else None

    def learn_places(self, pos):
        """Callout mode: one zone per place name, label at the median position of players seen there."""
        if self.manual:
            return
        seen = pos[pos.place != ""]
        if seen.place.nunique() < 3:
            self._auto_sectors(pos)
            return
        for place, g in seen.groupby("place"):
            if len(g) < 20:
                continue
            level = g.level.value_counts().index[0]
            g = g[g.level == level]
            self.zones.append((place, humanize(place, self.map), float(g.px.median()), float(g.py.median()), level))

    def _auto_sectors(self, pos, k=14, iters=30):
        """No callouts on this map: k-means on where players actually go, sectors numbered north to south."""
        lv = self.cfg["levels"][0]["key"]
        pts = pos[["px", "py"]].to_numpy(float)
        rng = np.random.default_rng(0)
        c = pts[rng.choice(len(pts), k, replace=False)]
        for _ in range(iters):
            lab = ((pts[:, None, :] - c[None]) ** 2).sum(-1).argmin(1)
            c = np.array([pts[lab == i].mean(0) if (lab == i).any() else c[i] for i in range(k)])
        c = c[np.lexsort((c[:, 0], np.round(c[:, 1] / 80)))]
        self.zones = [(f"S{i + 1}", f"Sector {i + 1}", float(x), float(y), lv) for i, (x, y) in enumerate(c)]
        self.anchors = c
        self.manual = True

    def px(self, x, y):
        r = self.cfg
        f = r.get("px_factor", 1.0)
        return (np.asarray(x) - r["pos_x"]) / r["scale"] * f, (r["pos_y"] - np.asarray(y)) / r["scale"] * f

    def zone(self, x, y, place=None):
        if not self.manual:
            return [p if p else "?" for p in place]
        px, py = self.px(x, y)
        pts = np.c_[np.atleast_1d(px), np.atleast_1d(py)]
        idx = ((pts[:, None, :] - self.anchors[None]) ** 2).sum(-1).argmin(1)
        return [self.zones[i][0] for i in idx]

    def name(self, key):
        return next((z[1] for z in self.zones if z[0] == key), humanize(key, self.map))

    def level(self, z):
        return [mapdata.level_of(self.cfg, v) for v in np.atleast_1d(z)]


# the events analyze() reads, in one pass of the demo (onepass.py, 15/10)
EVENTS = {"round_freeze_end": ((), ()), "round_officially_ended": ((), ()),
          "player_death": (("X", "Y", "Z", "team_num", "yaw", "last_place_name"), ())}


def analyze(path, me):
    from wily.demos import onepass
    p = onepass.Parser(path, EVENTS)
    map_name = p.parse_header()["map_name"]
    zm = ZoneMap(map_name)

    freeze = p.parse_event("round_freeze_end")["tick"].tolist()
    ends = sorted(set(p.parse_event("round_officially_ended")["tick"].tolist()))
    rounds = []
    for i, ft in enumerate(freeze):
        end = min([e for e in ends if e > ft], default=ft + 115 * TICKRATE)
        rounds.append((i + 1, ft, end))

    def round_of(t):
        for n, a, b in rounds:
            if a <= t <= b:
                return n, (t - a) / TICKRATE
        return None, None

    # ---- positions sampled every 0.25s ----
    ticks = [t for _, a, b in rounds for t in range(a, b, SAMPLE_EVERY)]
    pos = p.parse_ticks(["X", "Y", "Z", "team_num", "is_alive", "last_place_name"], ticks=ticks)
    pos = pos[pos.is_alive].copy()
    pos["place"] = pos["last_place_name"].fillna("")
    pos["level"] = zm.level(pos.Z.values)
    pos["px"], pos["py"] = zm.px(pos.X.values, pos.Y.values)
    zm.learn_places(pos)
    pos["steamid"] = pos["steamid"].map(sid)
    pos["side"] = pos.team_num.map(SIDE)
    pos["zone"] = zm.zone(pos.X.values, pos.Y.values, pos.place.values)
    rt = pos["tick"].map(lambda t: round_of(t))
    pos["round"] = [r[0] for r in rt]
    pos["t"] = [r[1] for r in rt]

    # ---- kills with both positions ----
    k = p.parse_event("player_death", player=["X", "Y", "Z", "team_num", "yaw", "last_place_name"])
    k = k[k.attacker_steamid.notna() & (k.attacker_steamid != k.user_steamid)].copy()
    for c in ("attacker_steamid", "user_steamid"):
        k[c] = k[c].map(sid)
    k = k[(k.attacker_steamid != 0) & (k.attacker_team_num != k.user_team_num)]
    rt = k["tick"].map(lambda t: round_of(t))
    k["round"] = [r[0] for r in rt]
    k["t"] = [r[1] for r in rt]
    k = k[k["round"].notna()]
    k["a_zone"] = zm.zone(k.attacker_X.values, k.attacker_Y.values, k.attacker_last_place_name.fillna("").values)
    k["v_zone"] = zm.zone(k.user_X.values, k.user_Y.values, k.user_last_place_name.fillna("").values)
    k["a_level"] = zm.level(k.attacker_Z.values)
    k["v_level"] = zm.level(k.user_Z.values)
    k["a_side"] = k.attacker_team_num.map(SIDE)
    k["v_side"] = k.user_team_num.map(SIDE)
    k = k.sort_values("tick")
    k["opening"] = ~k.duplicated("round")

    # ---- general zone control ----
    general = {}
    for key, name, *_ in zm.zones:
        entry = {"name": name}
        if not ((k.a_zone == key) | (k.v_zone == key)).any() and not (pos.zone == key).any():
            continue
        for side in ("T", "CT"):
            kills = int(((k.a_zone == key) & (k.a_side == side)).sum())
            deaths = int(((k.v_zone == key) & (k.v_side == side)).sum())
            presence = float((pos[(pos.side == side)].zone == key).mean() * 100)
            entry[side] = {"kills_from": kills, "deaths_in": deaths,
                           "kd": round(kills / deaths, 2) if deaths else (float(kills) if kills else None),
                           "presence_pct": round(presence, 1)}
        duels = k[k.v_zone == key]
        entry["duels"] = int(len(duels))
        entry["t_win_pct"] = round(100 * (duels.a_side == "T").mean(), 1) if len(duels) else None
        op = k[k.opening & ((k.v_zone == key) | (k.a_zone == key))]
        entry["opening_duels"] = int(len(op))
        entry["opening_t_win_pct"] = round(100 * (op.a_side == "T").mean(), 1) if len(op) else None
        # when does the fighting happen here
        entry["duel_time_median_s"] = round(float(duels.t.median()), 1) if len(duels) else None
        general[key] = entry

    # ---- me ----
    mine = pos[pos.steamid == me]
    my = {}
    for side in ("T", "CT"):
        ms = mine[mine.side == side]
        rounds_side = sorted(ms["round"].dropna().unique())
        zones = {}
        for key, name, *_ in zm.zones:
            kills = k[(k.attacker_steamid == me) & (k.a_zone == key) & (k.a_side == side)]
            deaths = k[(k.user_steamid == me) & (k.v_zone == key) & (k.v_side == side)]
            pres = float((ms.zone == key).mean() * 100) if len(ms) else 0
            if pres < 1 and not len(kills) and not len(deaths):
                continue
            zones[key] = {"name": name, "presence_pct": round(pres, 1), "kills": int(len(kills)),
                          "deaths": int(len(deaths)), "side_kd_here": general[key][side]["kd"]}
        # where am I at key moments of each round (predictability)
        habits = {}
        for lo, hi, label in PHASES:
            ph = ms[(ms.t >= lo) & (ms.t < hi)]
            per_round = ph.groupby("round").zone.agg(lambda s: s.value_counts().index[0])
            vc = per_round.value_counts()
            habits[label] = [{"zone": zm.name(z), "rounds": int(c), "of": int(len(per_round))} for z, c in vc.head(3).items()]
        my[side] = {"rounds": len(rounds_side), "zones": zones, "habits": habits}

    # ---- my deaths in detail ----
    mydeaths = []
    dk = k[k.user_steamid == me]
    if len(dk):
        snap = p.parse_ticks(["X", "Y", "Z", "yaw", "team_num", "is_alive"], ticks=[int(t) - 1 for t in dk.tick])
        snap["steamid"] = snap["steamid"].map(sid)
        for _, d in dk.iterrows():
            s = snap[snap.tick == int(d.tick) - 1]
            merow = s[s.steamid == me]
            if not len(merow):
                continue
            m = merow.iloc[0]
            mates = s[(s.team_num == m.team_num) & (s.steamid != me) & s.is_alive]
            dist = np.hypot(mates.X - m.X, mates.Y - m.Y)
            nearest = float(dist.min()) if len(dist) else None
            # angle between where I looked and where the killer was
            ang_to_killer = math.degrees(math.atan2(d.attacker_Y - m.Y, d.attacker_X - m.X))
            off = abs((ang_to_killer - m.yaw + 180) % 360 - 180)
            ax, ay = zm.px(d.attacker_X, d.attacker_Y)
            vx, vy = zm.px(m.X, m.Y)
            mydeaths.append({
                "round": int(d["round"]), "side": d.v_side, "t": round(float(d.t), 1),
                "zone": zm.name(d.v_zone), "killer_zone": zm.name(d.a_zone),
                "killer": d.attacker_name, "weapon": d.weapon,
                "nearest_mate_units": round(nearest) if nearest is not None else None,
                "mates_alive": int(len(mates)),
                "view_offset_deg": round(off), "caught_off_angle": off > 45,
                "px": [round(float(vx)), round(float(vy))], "killer_px": [round(float(ax)), round(float(ay))],
                "level": zm.level(m.Z)[0], "killer_level": d.a_level,
            })
    mykills = []
    for _, d in k[k.attacker_steamid == me].iterrows():
        ax, ay = zm.px(d.attacker_X, d.attacker_Y)
        vx, vy = zm.px(d.user_X, d.user_Y)
        mykills.append({"round": int(d["round"]), "side": d.a_side, "t": round(float(d.t), 1),
                        "zone": zm.name(d.a_zone), "victim_zone": zm.name(d.v_zone), "opening": bool(d.opening),
                        "px": [round(float(ax)), round(float(ay))], "victim_px": [round(float(vx)), round(float(vy))],
                        "level": d.a_level, "victim_level": d.v_level})

    # ---- heat grids (radar px, 24px cells) ----
    def heat(df):
        out = {}
        for lv, g in df.groupby("level"):
            cells = defaultdict(int)
            for a, b in zip((g.px // 24).astype(int), (g.py // 24).astype(int)):
                cells[(int(a), int(b))] += 1
            out[lv] = cells
        mx = max((v for c in out.values() for v in c.values()), default=1)
        return {lv: [[a * 24, b * 24, round(v / mx, 3)] for (a, b), v in c.items()] for lv, c in out.items()}

    return {
        "map": map_name, "zone_mode": "manual" if zm.manual else "callouts",
        "radar": {k: v for k, v in zm.cfg.items() if k != "levels"},
        "levels": [{k: v for k, v in lv.items() if k != "image_path"} for lv in zm.cfg["levels"]],
        "zones": [{"key": z[0], "name": z[1], "px": [round(z[2]), round(z[3])], "level": z[4]} for z in zm.zones if z[0] in general],
        "general": general,
        "me": my, "my_deaths": mydeaths, "my_kills": mykills,
        "heat": {"me_T": heat(mine[mine.side == "T"]), "me_CT": heat(mine[mine.side == "CT"]),
                 "all_T": heat(pos[pos.side == "T"]), "all_CT": heat(pos[pos.side == "CT"])},
        "all_kills": [{"a": [round(float(v)) for v in zm.px(r.attacker_X, r.attacker_Y)],
                       "v": [round(float(v)) for v in zm.px(r.user_X, r.user_Y)], "a_level": r.a_level, "v_level": r.v_level,
                       "side": r.a_side, "opening": bool(r.opening)} for _, r in k.iterrows()],
    }


if __name__ == "__main__":
    from wily.core import config
    me = int(sys.argv[2]) if len(sys.argv) > 2 else (ME_DEFAULT or config.logged_in_account()[0])
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(analyze(sys.argv[1], me), ensure_ascii=False, indent=1,
                     default=lambda o: o.item() if hasattr(o, "item") else str(o)))
