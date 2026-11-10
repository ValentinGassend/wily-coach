"""Buys and positions by type of round: pistol, eco, force, full, anti-eco (your team full against an eco).

For every player-round of every matchmaking demo: what was bought (weapon, armour, helmet, grenades, defuse kit),
where the player stood between 15 and 25 s, and what came out of it (round won, damage, kills, survival).
Then, for a player, per map, side and type of round: where to play and what to buy, from his own rounds
(when there are enough) and from the base (same map, same side, same type of round).
"""
import math
import os
from collections import Counter

import pandas as pd

from wily.core import config
from wily.core import ledger
from wily.core.i18n import N_, tr, trn
from wily.demos.map_analysis import humanize

OUT = os.path.join(config.OUT, "population", "buys")
TYPES = ["pistol", "eco", "force", "full", "anti-eco"]
TYPE_FR = {"pistol": N_("Pistol round"), "eco": N_("Eco"), "force": N_("Force-buy"), "full": N_("Full buy"), "anti-eco": N_("Anti-eco")}
ARMOR_FR = {"none": "no kevlar", "kevlar": "kevlar", "helmet": "kevlar + helmet"}
DEFAULT_PISTOLS = {"Glock-18", "USP-S", "P2000"}
# weapons a side cannot buy: holding one means it was picked up (often after winning), not a buy choice
FULL_WEAPONS = {"AK-47", "M4A4", "M4A1-S", "AUG", "SG 553", "AWP", "G3SG1", "SCAR-20"}


def fits(df, rt):
    """Only the buys that belong to this type of round: a player who can afford an AK with armour is not forcing,
    and a Galil in a full-buy round is a downgrade, not a full buy."""
    if rt == "full":
        return df[df.weapon.isin(FULL_WEAPONS)]
    if rt == "force":
        return df[~df.weapon.isin(FULL_WEAPONS)]
    return df


NOT_BUYABLE = {"T": {"M4A4", "M4A1-S", "AUG", "FAMAS", "MP9", "Five-SeveN", "USP-S", "P2000", "MAG-7"},
               "CT": {"AK-47", "SG 553", "Galil AR", "MAC-10", "Tec-9", "Glock-18", "Sawed-Off"}}


def _rtype(team, enemy):
    if team == "pistol":
        return "pistol"
    if team == "full" and enemy == "eco":
        return "anti-eco"
    return team if team in ("eco", "force", "full") else None


def rows_for(ddir):
    d = ddir
    L = pd.read_parquet(os.path.join(d, "loadout.parquet"))
    R = pd.read_parquet(os.path.join(d, "rounds.parquet")).set_index("round")
    if not len(R) or R.T_n.max() < 4 or R.CT_n.max() < 4:  # wingman (2v2): other habits
        return pd.DataFrame()
    S = pd.read_parquet(os.path.join(d, "samples.parquet"), columns=["steamid", "round", "t", "zone"])
    import json
    mp = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8")).get("map")
    S = S[(S.t >= 15) & (S.t <= 25) & (S.zone != "?")]
    setup = S.groupby(["round", "steamid"]).zone.agg(lambda z: z.mode().iloc[0]).to_dict()
    known = "buy_util" in L.columns  # grenades bought, by type (older extractions only have their number)
    rows = []
    for _, x in L.iterrows():
        r = int(x["round"])
        if r not in R.index or x.side not in ("T", "CT"):
            continue
        other = "CT" if x.side == "T" else "T"
        rt = _rtype(R.loc[r].get(f"{x.side}_buy"), R.loc[r].get(f"{other}_buy"))
        if rt is None:
            continue
        util = [u for u in str(x.get("buy_util") or "").split(",") if u] if known else []
        rows.append({"map": mp, "steamid": int(x.steamid), "round": r, "side": x.side, "rtype": rt,
                     "weapon": x.primary if isinstance(x.primary, str) and x.primary else (x.pistol if isinstance(x.pistol, str) else "?"),
                     "wclass": x.wclass, "pistol": x.pistol if isinstance(x.pistol, str) else None,
                     "armor": "helmet" if x.helmet else "kevlar" if (x.armor or 0) > 0 else "none", "util": ",".join(util),
                     "util_n": len(util) if known else int(x.nades or 0), "util_known": known,
                     "defuser": bool(x.defuser), "equip": float(x.equip or 0),
                     "zone": humanize(setup.get((r, int(x.steamid)), ""), mp) if setup.get((r, int(x.steamid))) else None,
                     "kills": int(x.kills), "damage": int(x.damage), "died": bool(pd.notna(x.died_t)), "won": bool(x.won)})
    return pd.DataFrame(rows)


def run_all(log=print):
    """The matches whose buys are missing or older than their loadout (the ones found up to date before are not
    opened again: ledger.py, 15/10)."""
    os.makedirs(OUT, exist_ok=True)
    led = ledger.Ledger("buys", version="buy_util")
    have = ledger.names(OUT)
    n = 0
    for mid, stamp in ledger.folders(config.DEEP).items():
        if mid in have and led.settled(mid, stamp):
            continue
        d = os.path.join(config.DEEP, mid)
        f = os.path.join(OUT, f"{mid}.parquet")
        lo = os.path.join(d, "loadout.parquet")
        if not os.path.exists(lo) or not os.path.exists(os.path.join(d, "rounds.parquet")):
            continue
        if mid in have and os.path.getmtime(f) >= os.path.getmtime(lo):
            led.mark(mid, stamp)
            continue
        import pyarrow.parquet as pq
        if mid in have and "buy_util" not in pq.read_schema(lo).names:
            continue
        try:
            rows_for(d).to_parquet(f)
            led.mark(mid, stamp)
            n += 1
        except Exception as e:
            log(f"[{mid}] buys: {e}")
    led.save()
    return n


def load():
    """Every match's buys as one (kept consolidated: only the new matches' files are read, ledger.py)."""
    return ledger.stacked(OUT, "buys", skip_empty=True)


def kit(row):
    """Readable buy, grouped the way the choice is made for this type of round."""
    rt, w, a, un = row["rtype"], row["weapon"], row["armor"], row["util_n"]
    util = [u for u in (row["util"] or "").split(",") if u and u != "decoy"]   # a $50 decoy is not a buy decision
    ut = ", ".join(f"{k}{f' ×{v}' if v > 1 else ''}" for k, v in Counter(util).most_common())
    if rt == "eco":   # the armor of an eco is often kept from the round before: the choice is the weapon
        return " + ".join(p for p in (w if w != "?" else "default pistol", ut or None) if p)
    if rt == "pistol":
        parts = [w if w != "?" else "default pistol", ARMOR_FR[a] if a != "none" else None, ut or None]
        return " + ".join(p for p in parts if p)
    if rt == "force":
        return f"{w} + {ARMOR_FR[a]}"
    if rt == "anti-eco":
        return w
    return f"{w} + {'3+ grenades' if un >= 3 else '1-2 grenades' if un else 'no grenade'}"


def _wilson_low(k, n, z=1.28):
    if not n:
        return 0
    p = k / n
    d = 1 + z * z / n
    return (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d


def _table(df, key, min_n, by="win"):
    """Options ranked by rounds won (lower bound of the win rate), or by damage for eco rounds (mostly lost anyway)."""
    if not len(df):
        return []
    g = df.groupby(key).agg(n=("won", "size"), won=("won", "sum"), adr=("damage", "mean"), kpr=("kills", "mean"), died=("died", "mean"))
    g = g[g.n >= min_n]
    out = []
    for k, x in g.iterrows():
        if not k:
            continue
        score = _wilson_low(x.won, x.n) if by == "win" else (x.adr * x.n + 70 * 8) / (x.n + 8)
        out.append({"key": k, "n": int(x.n), "win": round(100 * x.won / x.n), "adr": round(x.adr), "kpr": round(x.kpr, 2),
                    "survival": round(100 * (1 - x.died)), "score": score})
    return sorted(out, key=lambda r: -r["score"])


def advise(sid, maps):
    """Per map, side and type of round: where to play and what to buy (you, then the base)."""
    B = load()
    if not len(B):
        return None
    B["kit"] = B.apply(kit, axis=1)
    if "util_known" in B:
        B.loc[B.rtype.isin(["pistol", "eco"]) & ~B.util_known.fillna(False).astype(bool), "kit"] = None
    me = B[B.steamid == int(sid)]
    res = {"types": {}, "maps": {}}
    for rt in TYPES:  # all maps together: what works for you on each type of round
        m = me[me.rtype == rt]
        b = B[B.rtype == rt]
        res["types"][rt] = {"label": TYPE_FR[rt], "rounds": int(len(m)), "win": round(100 * m.won.mean()) if len(m) else None,
                            "adr": round(m.damage.mean()) if len(m) else None, "base_win": round(100 * b.won.mean()) if len(b) else None,
                            "my_kits": _table(fits(m, rt), "kit", 2)[:4], "base_kits": _table(fits(b, rt), "kit", 40)[:4]}
    for mp in maps:
        for side in ("T", "CT"):
            for rt in TYPES:
                b = B[(B["map"] == mp) & (B.side == side) & (B.rtype == rt)]
                m = me[(me["map"] == mp) & (me.side == side) & (me.rtype == rt)]
                if len(b) < 20 and len(m) < 2:
                    continue
                by = "adr" if rt == "eco" else "win"
                # where to play: not the spawn, and for T not the bomb site itself (being there at 15-25 s is a result, not a choice)
                ok_zone = lambda z: bool(z) and "spawn" not in z.lower() and not (side == "T" and z.lower().startswith("bombsite"))
                buyable = lambda df: df[~df.weapon.isin(NOT_BUYABLE[side])]
                kn = 20 if rt in ("force", "full") else 12
                bz, bk = _table(b[b.zone.map(ok_zone)], "zone", 12, by), _table(fits(buyable(b), rt), "kit", kn, by)
                mz, mk = _table(m[m.zone.map(ok_zone)], "zone", 2, by), _table(fits(buyable(m), rt), "kit", 2, by)
                base_win = round(100 * b.won.mean()) if len(b) else None
                # recommendation: your own zone/buy when it has worked at least as well as the base, else the base's best
                base_adr = b.damage.mean() if len(b) else None
                better = (lambda x: x["win"] >= base_win) if by == "win" else (lambda x: base_adr is not None and x["adr"] >= base_adr)
                rz = next((z for z in mz if z["n"] >= 3 and base_win is not None and better(z)), None)
                rk = next((k for k in mk if k["n"] >= 3 and base_win is not None and better(k)), None)
                res["maps"].setdefault(mp, {}).setdefault(side, {})[rt] = {
                    "label": TYPE_FR[rt], "n_base": int(len(b)), "n_me": int(len(m)), "base_win": base_win, "by": by,
                    "my_win": round(100 * m.won.mean()) if len(m) else None,
                    "zone": {"name": (rz or (bz[0] if bz else {})).get("key"), "from": "you" if rz else "base",
                             **{k: v for k, v in (rz or (bz[0] if bz else {})).items() if k in ("n", "win", "adr")}} if (rz or bz) else None,
                    "kit": {"name": (rk or (bk[0] if bk else {})).get("key"), "from": "you" if rk else "base",
                            **{k: v for k, v in (rk or (bk[0] if bk else {})).items() if k in ("n", "win", "adr")}} if (rk or bk) else None,
                    "base_zones": bz[:4], "base_kits": bk[:4], "my_zones": mz[:3], "my_kits": mk[:3],
                    "avoid_zone": (bz[-1] if len(bz) >= 4 and bz[-1]["win"] <= (base_win or 50) - 8 else None)}
    return res


# ---------- adapted to the player's profile ----------
ROLE_FR = {"entry": N_("entry"), "trader": N_("second / trade"), "support": N_("support"), "lurker": N_("lurker"), "awper": N_("AWPer"),
           "anchor": N_("anchor"), "closer": N_("closer")}


def peers(sid, arch):
    """Players of the base with the same profile: main and second role of the player's archetype."""
    from wily.coaching import archetype
    _, _, ref, _, _ = archetype.reference()
    roles = [r for r in ((arch or {}).get("role"), ((arch or {}).get("second") or {}).get("role")) if r]
    if not roles and str(sid) in ref.index:
        roles = [ref.loc[str(sid), "role"]]
    ids = {int(i) for i, r in ref.role.items() if r in roles and int(i) != int(sid)}
    return ids, roles


def _blend(b, p, m, key, by, bonus=None, need=(12, 8, 3)):
    """Every option scored from your rounds, pulled toward players of your profile, themselves pulled toward the base.
    With few rounds of your own, your profile decides; with many, your own results do. An option needs enough rounds
    somewhere (need = base, profile, you) to be proposed at all."""
    if not len(b) and not len(m):
        return []
    def agg(df):   # 16/10: size and sums straight (the named aggregation's overhead, 957 times a plan): the same numbers
        if not len(df):
            return pd.DataFrame(columns=["n", "w", "dmg"])
        g = df.groupby(key)
        return pd.DataFrame({"n": g.size(), "w": g["won"].sum(), "dmg": g["damage"].sum()})
    B, P, M = agg(b), agg(p), agg(m)
    p0 = b.won.mean() if len(b) else 0.5
    a0 = b.damage.mean() if len(b) else 80.0
    out = []
    # each table read once (16/10: three row lookups per option and per table, thousands a plan)
    rows = lambda T: {k: (int(n), float(w), float(d)) for k, n, w, d in zip(T.index, T.n, T.w, T.dmg)}
    Bd, Pd, Md = rows(B), rows(P), rows(M)
    for k in sorted(set(B.index) | set(P.index) | set(M.index), key=str):   # 16/10: equal scores in one order (a set's changed each run)
        if not k:
            continue
        nb, wb, db = Bd.get(k, (0, 0.0, 0.0))
        np_, wp, dp = Pd.get(k, (0, 0.0, 0.0))
        nm, wm, dm = Md.get(k, (0, 0.0, 0.0))
        if nb < need[0] and np_ < need[1] and nm < need[2]:
            continue
        if by == "win":
            s_b = (wb + p0 * 20) / (nb + 20)
            s_p = (wp + s_b * 30) / (np_ + 30)
            s_m = (wm + s_p * 10) / (nm + 10)
        else:  # eco rounds: damage, the round is usually lost anyway
            s_b = (db + a0 * 20) / (nb + 20)
            s_p = (dp + s_b * 30) / (np_ + 30)
            s_m = ((dm + s_p * 10) / (nm + 10)) / 200
        why = []
        if nm:
            why.append(trn(int(wm), "you: {n} round won out of {m}", "you: {n} rounds won out of {m}", m=nm) if by == "win" else tr("you: {d} damage per round over {m}", d=f"{dm / nm:.0f}", m=nm))
        if np_ >= 5:
            why.append(tr("players of your profile: {p}% over {n}", p=f"{100 * wp / np_:.0f}", n=np_) if by == "win" else tr("players of your profile: {d} damage over {n}", d=f"{dp / np_:.0f}", n=np_))
        if nb >= 8:
            why.append(tr("base: {p}% over {n}", p=f"{100 * wb / nb:.0f}", n=nb) if by == "win" else tr("base: {d} damage over {n}", d=f"{db / nb:.0f}", n=nb))
        score = s_m
        if bonus:
            add, reason = bonus(k)
            if add:
                score += add
                why.append(reason)
        out.append({"key": k, "score": round(float(100 * score), 1), "n_me": nm, "n_peer": np_, "n_base": nb,
                    "me_win": round(100 * wm / nm) if nm else None, "peer_win": round(100 * wp / np_) if np_ else None,
                    "base_win": round(100 * wb / nb) if nb else None, "why": why})
    return sorted(out, key=lambda r: -r["score"])


# Not buying is not a buy. Over the whole base a full buy without grenades wins less (53 % vs 57 %) and a force buy
# without kevlar too (30 % vs 41 %): when one tops a small cell it is noise, so it is never recommended.
NON_BUYS = {"full": "no grenade", "force": "no kevlar"}


def _real_buys(kits, rt):
    bad = NON_BUYS.get(rt)
    kits = [k for k in kits if not bad or bad not in k["key"]]
    if rt == "anti-eco":   # against an eco the AWP is the weapon you lose for nothing (the buy card says no AWP)
        kits = [k for k in kits if not k["key"].startswith("AWP")]
    if rt == "pistol":   # over the whole base, kevlar wins more pistol rounds (T 54 % vs 47 %, CT 51 % vs 48 %): first
        kits = [k for k in kits if "kevlar" in k["key"]] + [k for k in kits if "kevlar" not in k["key"]]
    # one AWP per team: when it comes first, say so and keep the best rifle right behind it
    if kits and kits[0]["key"].startswith("AWP"):
        kits[0] = dict(kits[0], why=kits[0]["why"] + [tr("if the AWP is free on your team")])
        alt = next((i for i, k in enumerate(kits) if not k["key"].startswith("AWP")), None)
        if alt and alt > 1:
            kits.insert(1, kits.pop(alt))
    return kits


def adapted(sid, maps, arch=None, zone_duels=None, weapons_info=None):
    """Where to play and what to buy on each type of round, for YOU: your rounds, players of your profile, your duels
    in each zone and with each weapon."""
    Bf = load()
    if not len(Bf):
        return None
    # each buy's label, once per combination (7,000 for the base's million rows: 0.5 s instead of 10 to 35, 15/10)
    cols = ["rtype", "weapon", "armor", "util_n", "util"]
    u = Bf[cols].drop_duplicates()
    Bf["kit"] = Bf[cols].merge(u.assign(kit=u.apply(kit, axis=1)), on=cols, how="left")["kit"].to_numpy()
    if "util_known" in Bf:
        Bf.loc[Bf.rtype.isin(["pistol", "eco"]) & ~Bf.util_known.fillna(False).astype(bool), "kit"] = None
    ids, roles = peers(sid, arch)
    me = Bf[Bf.steamid == int(sid)]
    Pf = Bf[Bf.steamid.isin(ids)]
    zd = zone_duels or {}
    duels = ((weapons_info or {}).get("duels") or {})
    ref = ((weapons_info or {}).get("ref_duels") or {})

    def weapon_bonus(k):
        w = str(k).split(" + ")[0]
        d, r = duels.get(w), ref.get(w)
        if not d or r is None or d.get("n", 0) < 10:
            return 0, None
        edge = float(max(-0.06, min(0.06, (d["win"] - r) / 100 * 0.3)))
        return edge, tr("your {w}: {p}% of duels won (base {b}%)", w=w, p=d['win'], b=r)
    res = {"profile": [tr(ROLE_FR.get(r, r)) for r in roles], "n_peers": len(ids), "types": {}, "maps": {}}
    for rt in TYPES:
        by = "adr" if rt == "eco" else "win"
        b, p, m = (fits(x[x.rtype == rt], rt) for x in (Bf, Pf, me))
        kits = _real_buys(_blend(b, p, m, "kit", by, weapon_bonus, need=(40, 15, 5)), rt)
        sides = {}
        for side in ("T", "CT"):
            sb = lambda x: fits(x[(x.side == side) & ~x.weapon.isin(NOT_BUYABLE[side])], rt)
            ks = _real_buys(_blend(sb(b), sb(p), sb(m), "kit", by, weapon_bonus, need=(40, 15, 5)), rt)
            if ks:
                sides[side] = {"kits": ks[:3]}
        res["types"][rt] = {"label": TYPE_FR[rt], "rounds": int(len(me[me.rtype == rt])),
                            "win": round(100 * me[me.rtype == rt].won.mean()) if len(me[me.rtype == rt]) else None,
                            "peer_win": round(100 * Pf[Pf.rtype == rt].won.mean()) if len(Pf[Pf.rtype == rt]) else None,
                            "kits": kits[:3], "sides": sides}
    # the rows split once by map, side and type of round, each zone judged once (16/10: 160 selections of the million
    # rows, every row's zone checked one at a time: 30 s a plan); the same rows, in the same order
    split = lambda x: {k: g for k, g in x.groupby(["map", "side", "rtype"], sort=False)}
    SB, SP, SM = split(Bf), split(Pf), split(me)
    for mp in maps:
        for side in ("T", "CT"):
            ok_zone = lambda z: bool(z) and "spawn" not in z.lower() and not (side == "T" and z.lower().startswith("bombsite"))
            zoned = lambda x: x[x.zone.isin([z for z in pd.unique(x.zone) if ok_zone(z)])]
            duel_z = zd.get((mp, side), {})

            def zone_bonus(z):
                kd = duel_z.get(z)
                if not kd or kd[0] + kd[1] < 4:
                    return 0, None
                k, d = kd
                # your own duels in the zone weigh in clearly: a 4-8 spot is not the one to send you to, whatever the base
                return float(0.75 * ((k + 3) / (k + d + 6) - 0.5)), tr("your duels here (all rounds): {k}-{d}", k=k, d=d)
            for rt in TYPES:
                by = "adr" if rt == "eco" else "win"
                b, p, m = (S.get((mp, side, rt), x.iloc[:0]) for S, x in ((SB, Bf), (SP, Pf), (SM, me)))
                if len(b) < 20 and len(m) < 2:
                    continue
                buy = lambda x: fits(x[~x.weapon.isin(NOT_BUYABLE[side])], rt)
                zones = _blend(zoned(b), zoned(p), zoned(m), "zone", by, zone_bonus, need=(15, 8, 3))
                kits = _real_buys(_blend(buy(b), buy(p), buy(m), "kit", by, weapon_bonus, need=(15, 10, 3)), rt)
                res["maps"].setdefault(mp, {}).setdefault(side, {})[rt] = {
                    "label": TYPE_FR[rt], "by": by, "n_base": int(len(b)), "n_peer": int(len(p)), "n_me": int(len(m)),
                    "base_win": round(100 * b.won.mean()) if len(b) else None, "peer_win": round(100 * p.won.mean()) if len(p) else None,
                    "my_win": round(100 * m.won.mean()) if len(m) else None,
                    "zone": zones[0] if zones else None, "zones": zones[1:3], "kit": kits[0] if kits else None, "kits": kits[1:3],
                    "avoid": next((z for z in reversed(zones) if (z["n_base"] + z["n_peer"]) >= 15 and z["score"] < (100 * b.won.mean() if len(b) else 50) - 8), None) if by == "win" else None}
    return res


if __name__ == "__main__":
    import json
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(run_all(), "matches")
    r = advise(int(sys.argv[1]) if len(sys.argv) > 1 else config.logged_in_account()[0], ["de_nuke", "de_anubis"])
    print(json.dumps(r["types"], ensure_ascii=False, indent=1)[:3000])
    print(json.dumps(r["maps"].get("de_nuke", {}).get("CT", {}).get("pistol"), ensure_ascii=False, indent=1))
