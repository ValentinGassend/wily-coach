"""Play-style features for EVERY player of a match, from the deep extraction (duels, positions, grenades).

Usage: python -m wily.demos.style      # all demos with a deep extraction (parallel)
Writes out/style/<match_id>.parquet: one row per player of the match.
"""
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

from wily.core import config
from wily.core import ledger

OUT = os.path.join(config.OUT, "style")
AWP = {"awp", "ssg08"}
RIFLE = {"ak47", "m4a1", "m4a1_silencer", "m4a1_silencer_off", "aug", "sg556", "famas", "galilar", "scar20", "g3sg1"}
SMG = {"mac10", "mp9", "mp7", "mp5sd", "ump45", "p90", "bizon"}
SHOTGUN = {"nova", "xm1014", "mag7", "sawedoff", "m249", "negev"}
PISTOL = {"glock", "hkp2000", "usp_silencer", "usp_silencer_off", "p250", "fiveseven", "tec9", "cz75a", "elite", "revolver"}


def wclass(w):
    w = str(w)
    if w in AWP:
        return "awp"
    if w in RIFLE:
        return "rifle"
    if w in SMG:
        return "smg"
    if w in SHOTGUN:
        return "shotgun"
    if w == "deagle":
        return "deagle"
    if w in PISTOL:
        return "pistol"
    return "other"


def extract(mid, deep_dir=None, out_dir=None):
    d = os.path.join(deep_dir or config.DEEP, mid)
    duels = pd.read_parquet(os.path.join(d, "duels.parquet"))
    nades = __import__("wily.demos.deep", fromlist=["deep"]).read_nades(os.path.join(d, "grenades.parquet"))
    sm = pd.read_parquet(os.path.join(d, "samples.parquet"))
    import json
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
    sm = sm[sm.steamid != 0]
    rounds = int(sm["round"].max()) if len(sm) else 0

    # isolation: distance to the nearest living teammate, mid-round (15-60 s)
    mid_sm = sm[(sm.t >= 15) & (sm.t <= 60)][["tick", "steamid", "side", "X", "Y"]]
    iso = {}
    for (tick, side), g in mid_sm.groupby(["tick", "side"]):
        if len(g) < 2:
            continue
        xy = g[["X", "Y"]].to_numpy()
        dist = np.hypot(xy[:, None, 0] - xy[None, :, 0], xy[:, None, 1] - xy[None, :, 1])
        np.fill_diagonal(dist, np.inf)
        for s, v in zip(g.steamid, dist.min(1)):
            iso.setdefault((s, side), []).append(v)

    # trades: my kill on someone who killed a teammate of mine in the previous 5 s
    duels = duels.sort_values("tick")
    trade_k, trade_dt = {}, {}
    for r in duels.itertuples():
        prev = duels[(duels.killer == r.victim) & (duels.victim_side == r.killer_side) & (duels.tick < r.tick) & (duels.tick >= r.tick - 320)]
        if len(prev):
            trade_k[r.killer] = trade_k.get(r.killer, 0) + 1
            trade_dt.setdefault(r.killer, []).append((r.tick - prev.tick.max()) / 64)

    site_zones = {z["key"] for z in meta.get("zones", []) if "bombsite" in z["key"].lower() or z["key"].lower() in ("asite", "bsite")}
    rows = []
    for s, name in sm.drop_duplicates("steamid")[["steamid", "name"]].itertuples(index=False):
        k = duels[duels.killer == s]
        dd = duels[duels.victim == s]
        pov_speed = pd.concat([k.killer_speed, dd.victim_speed]).dropna()
        pov_scoped = pd.concat([k.killer_scoped, dd.victim_scoped]).dropna()
        pov_t = pd.concat([k[["round", "t"]], dd[["round", "t"]]])
        first_t = pov_t.groupby("round").t.min() if len(pov_t) else pd.Series(dtype=float)
        ms = sm[sm.steamid == s]
        t_rounds = ms[ms.side == "T"]["round"].nunique()
        ct_rounds = ms[ms.side == "CT"]["round"].nunique()
        ct = ms[(ms.side == "CT") & (ms.t >= 10)]
        zc = ct.zone.value_counts(normalize=True) if len(ct) else pd.Series(dtype=float)
        n = nades[nades.thrower == s]
        cls = k.weapon.map(wclass).value_counts().to_dict()
        wk = k.weapon.value_counts().head(3).to_dict()
        rows.append({
            "match": mid, "map": meta["map"], "steamid": str(s), "name": name, "rounds": rounds,
            "t_rounds": t_rounds, "ct_rounds": ct_rounds, "kills": len(k), "deaths": len(dd),
            "duels": len(k) + len(dd),
            "open_att": int(k.opening.sum() + dd.opening.sum()),
            "open_att_T": int(k[k.killer_side == "T"].opening.sum() + dd[dd.victim_side == "T"].opening.sum()),
            "open_won": int(k.opening.sum()),
            "trade_kills": trade_k.get(s, 0), "trade_time": float(np.median(trade_dt[s])) if s in trade_dt else None,
            "traded_deaths": int(dd.traded.sum()),
            "iso_T": float(np.median(iso[(s, "T")])) if (s, "T") in iso else None,
            "iso_CT": float(np.median(iso[(s, "CT")])) if (s, "CT") in iso else None,
            "speed_duel": float(pov_speed.median()) if len(pov_speed) else None,
            "move_share": float((pov_speed > 110).mean()) if len(pov_speed) else None,
            "hold_share": float((pov_speed < 40).mean()) if len(pov_speed) else None,
            "scoped_share": float(pov_scoped.astype(bool).mean()) if len(pov_scoped) else None,
            "first_duel_t": float(first_t.median()) if len(first_t) else None,
            "late_kills": int((k.t > 60).sum()), "early_kills": int((k.t <= 20).sum()),
            "duel_len_won": float(k.duel_len_s.median()) if len(k) else None,
            "hs_kills": int(k.headshot.sum()),
            "flashes": int((n.type == "flash").sum()), "smokes": int((n.type == "smoke").sum()),
            "molotovs": int((n.type == "molotov").sum()), "hes": int((n.type == "he").sum()),
            "flash_enemies": float(n[n.type == "flash"].enemies_blind.fillna(0).sum()) if "enemies_blind" in n else 0.0,
            "util_dmg": float(n.damage.fillna(0).sum()) if "damage" in n else 0.0,
            "ct_site_share": float(zc[[z for z in zc.index if z in site_zones]].sum()) if len(zc) and site_zones else None,
            "ct_top_zone_share": float(zc.iloc[0]) if len(zc) else None,
            "k_awp": cls.get("awp", 0), "k_rifle": cls.get("rifle", 0), "k_smg": cls.get("smg", 0),
            "k_shotgun": cls.get("shotgun", 0), "k_pistol": cls.get("pistol", 0), "k_deagle": cls.get("deagle", 0),
            "top_weapons": ";".join(f"{w}:{c}" for w, c in wk.items()),
        })
    df = pd.DataFrame(rows)
    os.makedirs(out_dir or OUT, exist_ok=True)
    df.to_parquet(os.path.join(out_dir or OUT, f"{mid}.parquet"))
    return len(df)


def run_all(workers=12, force=False):
    have = set() if force else ledger.names(OUT)   # 15/10: one read of the folder, not a file check per match
    todo = [m for m in os.listdir(config.DEEP) if m not in have and os.path.exists(os.path.join(config.DEEP, m, "meta.json"))]
    if not todo:
        return 0
    if len(todo) == 1 or workers == 1:
        for m in todo:
            extract(m)
        return len(todo)
    with ProcessPoolExecutor(workers) as ex:
        for f in as_completed([ex.submit(extract, m) for m in todo]):
            try:
                f.result()
            except Exception as e:
                print("style ERROR", e, flush=True)
    return len(todo)


def load():
    """Every match's styles as one (kept consolidated: only the new matches' files are read, ledger.py)."""
    return ledger.stacked(OUT, "style")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    n = run_all(force="--force" in sys.argv)
    df = load()
    print(n, "matches processed;", len(df), "fiches,", df.steamid.nunique() if len(df) else 0, "players")
