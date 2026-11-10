"""Weapons: how a player does with each gun (rounds, duels, force-buys) and where players set up with each weapon
class on every map (matchmaking population, plus pro AWPers).

Needs rounds.py (loadout.parquet, deaths_w.parquet) next to deep.py's output.
"""
import json
import math
import os
from collections import defaultdict

import numpy as np
import pandas as pd

from wily.core import config
from wily.core.i18n import N_, tr, trn
from wily.demos.rounds import PISTOLS, WCLASS

GUNS = set(WCLASS) | PISTOLS
DEFAULT_PISTOLS = {"Glock-18", "USP-S", "P2000"}

WZ = os.path.join(config.OUT, "population", "weapon_zones.json")
WPOP = os.path.join(config.OUT, "population", "weapons.json")
CLASS_FR = {"awp": "AWP", "scout": N_("Scout (SSG 08)"), "rifle": N_("rifles (AK, M4, AUG, SG)"), "rifle_eco": N_("Galil / FAMAS"), "smg": "SMG",
            "shotgun": "shotguns", "heavy": N_("machine guns"), "pistol": N_("pistol only"), "auto": "auto-snipers"}


def _load(mid, name):
    f = os.path.join(config.DEEP, str(mid), name)
    return pd.read_parquet(f) if os.path.exists(f) else None


def _wilson(k, n, z=1.64):
    if not n:
        return None, None
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return round(100 * (c - m) / d), round(100 * (c + m) / d)


def duel_table(mids, steamid=None):
    """Duels won/lost by weapon in hand. steamid=None: every player (population)."""
    won, lost = defaultdict(int), defaultdict(int)
    for mid in mids:
        dw = _load(mid, "deaths_w.parquet")
        if dw is None or not len(dw):
            continue
        dw = dw[(dw.killer != 0) & (dw.killer != dw.victim)]
        if steamid is not None:
            k = dw[dw.killer == steamid]
            v = dw[dw.victim == steamid]
        else:
            k, v = dw, dw
        for w in k.killer_weapon_name.dropna():
            if w in GUNS:
                won[w] += 1
        for w in v.victim_weapon.dropna():
            if w in GUNS:
                lost[w] += 1
    out = {}
    for w in sorted(set(won) | set(lost)):   # 16/10: in one order (a set's changed each run, and the first 12 are kept)
        n = won[w] + lost[w]
        out[w] = {"won": won[w], "lost": lost[w], "n": n, "win": round(100 * won[w] / n) if n else None}
    return out


def round_table(mids, steamid):
    rows = []
    for mid in mids:
        L = _load(mid, "loadout.parquet")
        if L is None or not len(L):
            continue
        x = L[L.steamid == steamid].copy()
        x["match"] = mid
        rows.append(x)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def summarize_rounds(df, key):
    out = []
    for k, g in df.groupby(key):
        n = len(g)
        out.append({"key": k, "rounds": n, "kpr": round(g.kills.mean(), 2), "adr": round(g.damage.mean()),
                    "survival": round(100 * g.died_t.isna().mean()), "win": round(100 * g.won.mean()),
                    "win_ci": _wilson(int(g.won.sum()), n)})
    return sorted(out, key=lambda r: -r["rounds"])


_N = [0.0, 0]


def _n_demos():
    """The base's demos (counted once a minute: a plan build asked 511 times)."""
    import time
    if time.time() - _N[0] > 60:
        from wily.core import ledger
        _N[0], _N[1] = time.time(), sum(1 for f in ledger.match_facts().values() if f.get("loadout"))   # no file checked one by one
    return _N[1]


def population_weapons(rebuild=False):
    """Reference: duel win rate and round stats per weapon, over every matchmaking demo."""
    if os.path.exists(WPOP) and not rebuild:
        cur = json.load(open(WPOP, encoding="utf-8"))
        if cur.get("n_matches", 0) >= 0.85 * _n_demos():   # good until the base grows by 15% (it grows by itself now)
            return cur
    mids = [m for m in os.listdir(config.DEEP) if os.path.exists(os.path.join(config.DEEP, m, "loadout.parquet"))]
    duels = duel_table(mids)
    Ls = [pd.read_parquet(os.path.join(config.DEEP, m, "loadout.parquet")) for m in mids]
    L = pd.concat([x for x in Ls if len(x)], ignore_index=True) if Ls else pd.DataFrame()
    rounds = {}
    if len(L):
        for (w, tb), g in L[L.primary.notna()].groupby(["primary", "team_buy"]):
            if len(g) >= 30:
                rounds.setdefault(w, {})[tb] = {"rounds": len(g), "kpr": round(g.kills.mean(), 2), "adr": round(g.damage.mean()),
                                                 "survival": round(100 * g.died_t.isna().mean()), "win": round(100 * g.won.mean())}
    res = {"duels": {w: v for w, v in duels.items() if v["n"] >= 40}, "rounds": rounds, "n_matches": len(mids)}
    json.dump(res, open(WPOP, "w", encoding="utf-8"), ensure_ascii=False)
    return res


def player(steamid, mids):
    """Everything about the weapons of one player, with the population reference and suggestions."""
    sid = int(steamid)
    mids = [m for m in mids if os.path.exists(os.path.join(config.DEEP, str(m), "loadout.parquet"))]
    if not mids:
        return None
    R = round_table(mids, sid)
    if not len(R):
        return None
    ref = population_weapons()
    duels = duel_table(mids, sid)
    by_w = summarize_rounds(R[R.primary.notna()], "primary")
    by_buy = summarize_rounds(R, "team_buy")
    force = R[(R.team_buy == "force") & R.primary.notna()]
    force_w = summarize_rounds(force, "primary") if len(force) else []
    ct_full = R[(R.side == "CT") & (R.team_buy == "full") & R.primary.isin(["M4A4", "M4A1-S", "AWP", "AUG", "FAMAS"])]
    suggestions = []

    def ref_duel(w):
        d = ref.get("duels", {}).get(w)
        return d["win"] if d else None
    # guns the player loses with, compared to what the base does with the same gun
    for w, d in sorted(duels.items(), key=lambda x: -x[1]["n"]):
        r = ref_duel(w)
        if d["n"] >= 12 and r is not None and d["win"] <= r - 10:
            suggestions.append({"kind": "weapon_weak", "weapon": w, "text": tr("{w}: {p}% of duels won out of {n} (base: {b}%). Try another weapon at the same price for 5 games (experiment '{w}').",
                                                                                w=w, p=d['win'], n=d['n'], b=r), "n": d["n"]})
        elif d["n"] >= 12 and r is not None and d["win"] >= r + 8:
            if w in DEFAULT_PISTOLS:
                suggestions.append({"kind": "pistol_strong", "weapon": w, "text": tr("{w}: {p}% of duels won out of {n} (base: {b}%). Your pistol rounds are a strength: take the opening duels with the pistol.",
                                                                                   w=w, p=d['win'], n=d['n'], b=r), "n": d["n"]})
            else:
                suggestions.append({"kind": "weapon_strong", "weapon": w, "text": tr("{w}: {p}% of duels won out of {n} (base: {b}%). One of your best weapons: buy it when the economy allows.",
                                                                                   w=w, p=d['win'], n=d['n'], b=r), "n": d["n"]})
    for side in ("T", "CT"):
        fs = [x for x in (summarize_rounds(force[force.side == side], "primary") if len(force) else [])
              if x["rounds"] >= 10 and x["key"] not in ("AWP", "AK-47", "M4A4", "M4A1-S", "AUG", "SG 553", "G3SG1", "SCAR-20")]
        if len(fs) >= 2:
            best, worst = max(fs, key=lambda x: x["adr"]), min(fs, key=lambda x: x["adr"])
            if best["key"] != worst["key"] and best["adr"] - worst["adr"] >= 20:
                suggestions.append({"kind": "force", "side": side, "text": tr("On a {side} force-buy, you do {a} damage per round with the {wa} vs {b} with the {wb} ({na} and {nb} rounds). Prefer the {wa} while the gap holds.",
                                                                              side=side, a=best['adr'], wa=best['key'], b=worst['adr'], wb=worst['key'], na=best['rounds'], nb=worst['rounds']),
                                    "n": best["rounds"] + worst["rounds"]})
    m4 = {w: g for w, g in ct_full.groupby("primary")}
    if "M4A4" in m4 and "M4A1-S" in m4 and min(len(m4["M4A4"]), len(m4["M4A1-S"])) >= 15:
        a, b = m4["M4A4"], m4["M4A1-S"]
        better = "M4A4" if a.damage.mean() > b.damage.mean() else "M4A1-S"
        gap = abs(a.damage.mean() - b.damage.mean())
        verdict = tr("Edge to the {w} for you.", w=better) if gap >= 12 else tr("No real difference: take the one you're most comfortable with.")
        suggestions.append({"kind": "m4", "text": tr("On CT full buys, M4A4: {a} damage per round ({na} rounds); M4A1-S: {b} ({nb} rounds).", a=f"{a.damage.mean():.0f}", na=len(a),
                                                     b=f"{b.damage.mean():.0f}", nb=len(b)) + " " + verdict})
    keep = {x["key"] for x in by_w[:12]} | {w for w, _ in sorted(duels.items(), key=lambda x: -x[1]["n"])[:12]}
    return {"by_weapon": by_w[:12], "by_buy": by_buy, "force": force_w, "duels": dict(sorted(((w, d) for w, d in duels.items() if w in keep), key=lambda x: -x[1]["n"])),
            "ref_duels": {w: ref_duel(w) for w in duels}, "ref_rounds": {w: ref.get("rounds", {}).get(w) for w in list(duels)[:12]},
            "suggestions": suggestions, "n_rounds": int(len(R))}


# ---------- where to play with each weapon ----------
def weapon_zones(rebuild=False):
    """Per map, side and weapon class: where players stand at 15-25 s (setup) and how their duels go in each zone."""
    if os.path.exists(WZ) and not rebuild:
        cur = json.load(open(WZ, encoding="utf-8"))
        if cur.get("_n", 0) >= 0.85 * _n_demos():   # good until the base grows by 15% (it grows by itself now)
            return cur
    acc = defaultdict(lambda: defaultdict(lambda: {"n": 0, "k": 0, "d": 0, "won": 0}))
    duel_acc = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for mid in os.listdir(config.DEEP):
        d = os.path.join(config.DEEP, mid)
        if not os.path.exists(os.path.join(d, "loadout.parquet")):
            continue
        try:
            meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))
        except Exception:
            continue
        mp = meta.get("map")
        L = pd.read_parquet(os.path.join(d, "loadout.parquet"))
        if not len(L):
            continue
        S = pd.read_parquet(os.path.join(d, "samples.parquet"), columns=["steamid", "round", "t", "zone", "side"])
        S = S[(S.t >= 15) & (S.t <= 25)]
        setup = S.groupby(["round", "steamid"]).zone.agg(lambda z: z.mode().iloc[0])
        D = pd.read_parquet(os.path.join(d, "duels.parquet"))
        wc = {(int(r), int(s)): w for r, s, w in zip(L["round"], L.steamid, L.wclass)}
        for _, x in L.iterrows():
            z = setup.get((x["round"], x.steamid))
            if z is None or not x.side:
                continue
            a = acc[(mp, x.side, x.wclass)][z]
            a["n"] += 1
            a["k"] += int(x.kills)
            a["d"] += int(pd.notna(x.died_t))
            a["won"] += int(bool(x.won))
        for _, k in D.iterrows():
            kw, vw = wc.get((int(k["round"]), int(k.killer))), wc.get((int(k["round"]), int(k.victim)))
            if kw and k.killer_side:
                duel_acc[(mp, k.killer_side, kw)][k.killer_zone][0] += 1
            if vw and k.victim_side:
                duel_acc[(mp, k.victim_side, vw)][k.victim_zone][1] += 1
    # pro AWPers: players who got an AWP kill in the round
    pro_awp = defaultdict(lambda: defaultdict(int))
    dp = os.path.join(config.OUT, "deep_pro")
    for mid in os.listdir(dp) if os.path.exists(dp) else []:
        d = os.path.join(dp, mid)
        try:
            mp = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8")).get("map")
            D = pd.read_parquet(os.path.join(d, "duels.parquet"))
            S = pd.read_parquet(os.path.join(d, "samples.parquet"), columns=["steamid", "round", "t", "zone", "side"])
        except Exception:
            continue
        awp = D[D.weapon == "awp"][["round", "killer", "killer_side"]].drop_duplicates(["round", "killer"])
        S = S[(S.t >= 15) & (S.t <= 25)]
        setup = S.groupby(["round", "steamid"]).zone.agg(lambda z: z.mode().iloc[0])
        for _, x in awp.iterrows():
            z = setup.get((x["round"], x.killer))
            if z is not None and x.killer_side:
                pro_awp[(mp, x.killer_side)][z] += 1
    out = {}
    for (mp, side, wc), zones in acc.items():
        tot = sum(v["n"] for v in zones.values())
        if tot < 25:
            continue
        du = duel_acc.get((mp, side, wc), {})
        rows = []
        for z, v in sorted(zones.items(), key=lambda kv: -kv[1]["n"]):
            if v["n"] < 5:
                continue
            k, dd = du.get(z, [0, 0])
            rows.append({"zone": z, "share": round(100 * v["n"] / tot), "rounds": v["n"], "kpr": round(v["k"] / v["n"], 2),
                         "death": round(100 * v["d"] / v["n"]), "round_win": round(100 * v["won"] / v["n"]),
                         "duel_win": round(100 * k / (k + dd)) if k + dd >= 8 else None, "duels": k + dd})
        out.setdefault(mp, {}).setdefault(side, {})[wc] = {"rounds": tot, "zones": rows[:8]}
    for (mp, side), zones in pro_awp.items():
        tot = sum(zones.values())
        if tot >= 10:
            out.setdefault(mp, {}).setdefault(side, {})["pro_awp"] = {"rounds": tot, "zones": [{"zone": z, "share": round(100 * n / tot), "rounds": n}
                                                                                               for z, n in sorted(zones.items(), key=lambda kv: -kv[1])[:6]]}
    out["_n"] = _n_demos()
    json.dump(out, open(WZ, "w", encoding="utf-8"), ensure_ascii=False)
    return out


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    from wily.app import pipeline
    sid = int(sys.argv[1]) if len(sys.argv) > 1 else config.logged_in_account()[0]
    print(json.dumps(player(sid, pipeline.player_matches(sid)), ensure_ascii=False, indent=1)[:5000])
