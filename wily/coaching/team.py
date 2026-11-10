"""Team plan: you + 1 to 4 teammates. Crosses every member's data (roles, zones, lineups, weapons, mid-round habits,
matches played together) with the base and the pros to build a game plan:
roles (T, CT, AWP, IGL), map pool, CT setup (who plays where), T executes (who throws what), rotations, calls,
economy, synergies, collective goals and each member's individual work.

Saved in out/teams/<id>.json and copied to the site. Usage: python -m wily.coaching.team <steamid> <steamid> [...]
"""
import datetime as dt
import hashlib
import itertools
import json
import os
from collections import defaultdict

import numpy as np
import pandas as pd

from wily.core import config
from wily.coaching import knowledge as K
from wily.demos.map_analysis import humanize
from wily.core.i18n import N_, num, tr, trn, tr_static

# the zone groups' names (R.group()): English while the plan is built, translated where it is saved
_GROUPS = [N_("A site"), N_("B site"), N_("Mid"), N_("A approach (T side)"), N_("B approach (T side)"), N_("CT side / rotations"), N_("Spawns")]

TEAMS = os.path.join(config.OUT, "teams")
META = os.path.join(config.OUT, "population", "map_meta.json")
PREMIER = ["de_ancient", "de_anubis", "de_cache", "de_dust2", "de_inferno", "de_mirage", "de_nuke"]
ROLE_FR = {"entry": N_("Entry"), "trader": N_("Second / trade"), "support": N_("Support"), "lurker": N_("Lurker"), "awper": N_("AWPer"),
           "flex": N_("Rifler flex"), "anchor": N_("Anchor"), "closer": N_("Closer")}
T_ROLE_DO = {
    "entry": N_("First onto the site, behind the support's flash. Your job: take space and call what you see, even if you die."),
    "trader": N_("Stick to the entry within trade distance (1 to 2 s behind, not on the same line) and avenge them right away."),
    "support": N_("Throw the execute's smokes and flashes, then go in third. Keep a grenade for the post-plant."),
    "lurker": N_("Opposite side of the execute: walk, listen to the rotations and cut them when the team goes in."),
    "awper": N_("Take the first pick on the long angle, then cover the entry or the flank. Never re-peek the same angle."),
    "flex": N_("Backup for the execute or a second lurker depending on the info. Play the end of the round: clutch, post-plant."),
}
CT_SLOT_DO = {
    "anchor": N_("Hold the site: survive 10 s, call how many they are and their grenades, fall back rather than die first."),
    "support": N_("Backup for the most attacked site: delaying utility, then trade the anchor."),
    "mid": N_("Mid control: info early in the round, then a fast rotation to the attacked site."),
    "awp": N_("The long angle that hurts the Ts. One shot, then change position."),
}


# ---------- population references per map ----------
_N = [0.0, 0]


def _n_demos():
    """The base's demos (counted once a minute: a plan build asked 511 times)."""
    import time
    if time.time() - _N[0] > 60:
        from wily.core import ledger
        _N[0], _N[1] = time.time(), sum(1 for f in ledger.match_facts().values() if f.get("rounds"))   # no file checked one by one
    return _N[1]


def map_meta(rebuild=False):
    """Per map: region (A / B / mid) of every zone, and where the Ts plant (share, T win rate, plant time)."""
    if os.path.exists(META) and not rebuild:
        cur = json.load(open(META, encoding="utf-8"))
        if cur.get("_n", 0) >= 0.85 * _n_demos():   # good until the base grows by 15% (it grows by itself now)
            return cur
    from wily.insights import midround
    sites = midround.site_centers()
    out = {"_n": _n_demos()}
    by_map = defaultdict(list)
    for mid in os.listdir(config.DEEP):
        d = os.path.join(config.DEEP, mid)
        try:
            mp = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8"))["map"]
        except Exception:
            continue
        by_map[mp].append(d)
    for mp, dirs in by_map.items():
        entry = {"regions": {}, "plants": {}}
        if mp in sites:
            S = pd.concat([pd.read_parquet(os.path.join(d, "samples.parquet"), columns=["X", "Y", "Z", "zone"]) for d in dirs[:10]], ignore_index=True)
            cen = S.groupby("zone")[["X", "Y", "Z"]].median()
            cA, cB = sites[mp]["A"]["c"], sites[mp]["B"]["c"]
            for z, r in cen.iterrows():
                dA = midround._dist(r.X, r.Y, r.Z, cA)
                dB = midround._dist(r.X, r.Y, r.Z, cB)
                ratio = dA / max(dA + dB, 1)
                entry["regions"][z] = "A" if ratio < 0.4 else "B" if ratio > 0.6 else "mid"
            from wily.demos.map_analysis import ZoneMap
            zm = ZoneMap(mp)
            for L in ("A", "B"):
                x, y = zm.px([sites[mp][L]["c"][0]], [sites[mp][L]["c"][1]])
                entry.setdefault("site_px", {})[L] = [float(x[0]), float(y[0])]
        R = [pd.read_parquet(os.path.join(d, "rounds.parquet")) for d in dirs if os.path.exists(os.path.join(d, "rounds.parquet"))]
        R = pd.concat([r for r in R if len(r)], ignore_index=True) if R else pd.DataFrame()
        if len(R) and "plant_site" in R:
            pl = R[R.plant_site.isin(["A", "B"])]
            for L, g in pl.groupby("plant_site"):
                entry["plants"][L] = {"share": round(100 * len(g) / max(len(pl), 1)), "t_win": round(100 * (g.winner == "T").mean()),
                                      "plant_t": round(float(g.plant_t.median()), 1), "n": int(len(g))}
            entry["rounds"] = int(len(R))
            entry["plant_rate"] = round(100 * len(pl) / len(R))
        out[mp] = entry
    config.write_json(META, out)
    return out


# ---------- members ----------
def _load(p):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def member(sid):
    pdir = config.player_dir(sid)
    adv = _load(os.path.join(pdir, "advice.json"))
    if not adv:
        return None
    cross = _load(os.path.join(pdir, "cross.json")) or {}
    arch = adv.get("archetype") or {}
    scores = {s["role"]: s["score"] for s in arch.get("scores", [])}
    plan = adv.get("plan") or {}
    names = config.settings().get("players", {})
    name = (names.get(str(sid)) or {}).get("name") or (adv.get("leetify") or {}).get("name") or str(sid)
    mdir = os.path.join(pdir, "matches")
    for mid in sorted(os.listdir(mdir)) if os.path.exists(mdir) else []:
        st = _load(os.path.join(mdir, mid, "stats.json"))
        if st and not st.get("error"):
            name = st["player"]["name"]
    return {"steamid": str(sid), "name": name, "adv": adv, "cross": cross, "plan": plan, "arch": arch,
            "scores": {r: scores.get(r, 50) for r in ("entry", "trader", "support", "lurker", "awper", "anchor", "closer")},
            "has_scores": bool(scores), "light": bool(adv.get("light")),
            "maps": {m["map"]: m for m in cross.get("maps", [])}}


def _pct(m, key, where="bench"):
    """Percentile of a metric (advice bench or mid-round bench); 50 when unknown."""
    if where == "bench":
        b = ((m["adv"].get("bench") or {}).get("metrics") or {}).get(key) or {}
    else:
        b = (((m["plan"].get("mid") or {}).get("bench") or {}).get("metrics") or {}).get(key) or {}
    return b.get("percentile")


# ---------- roles ----------
def t_fit(m, role):
    s = m["scores"]
    if role == "lurker":
        return s["lurker"] + 0.2 * s["closer"]
    if role == "flex":
        return 0.5 * s["closer"] + 0.3 * s["trader"] + 0.2 * s["anchor"]
    return s[role]


def assign(members, slots, fit):
    """Best injective assignment members -> slots (brute force, at most 5! cases). -> {member index: slot index}"""
    n, k = len(members), len(slots)
    best, best_v = {}, -1e9
    if n <= k:
        for perm in itertools.permutations(range(k), n):
            v = sum(fit(members[i], slots[perm[i]]) for i in range(n))
            if v > best_v:
                best, best_v = {i: perm[i] for i in range(n)}, v
    else:  # more members than slots: the best-suited members take them
        for perm in itertools.permutations(range(n), k):
            v = sum(fit(members[perm[j]], slots[j]) for j in range(k))
            if v > best_v:
                best, best_v = {perm[j]: j for j in range(k)}, v
    return best


def t_roles(M):
    awp_ok = max(m["scores"]["awper"] for m in M) >= 55 or any(
        (((m["plan"].get("weapons") or {}).get("duels") or {}).get("AWP") or {}).get("n", 0) >= 15 for m in M)
    roles = ["entry", "trader", "support", "lurker", "awper" if awp_ok else "flex"]
    # with fewer than 5, each member gets the role he fits best without overlap; random players take the rest
    a = assign(M, roles, lambda m, r: t_fit(m, r))
    out = {M[i]["steamid"]: roles[j] for i, j in a.items()}
    return out, [r for r in roles if r not in out.values()], awp_ok


def igl(M):
    res = []
    for m in M:
        vals, why = [], []
        for key, where, label in (("adv_conv", "mid", N_("converts advantages")), ("adv_throw", "mid", N_("rarely throws the advantage")),
                                  ("isolated", "mid", N_("rarely dies isolated")), ("traded_pct", "bench", N_("plays as a team (deaths traded)"))):
            p = _pct(m, key, where)
            if p is not None:
                vals.append(p)
                if p >= 65:
                    why.append(label)
        role = m["arch"].get("role")
        bonus = 8 if role in ("support", "anchor", "closer", "lurker") else -8 if role in ("entry", "awper") else 0
        art = {"support": N_("Support"), "anchor": N_("Anchor"), "closer": N_("Closer"), "lurker": N_("Lurker")}.get(role)
        hours = ((m["plan"].get("level") or {}).get("hours")) or 0
        exp = min(hours / 500, 8)
        score = (sum(vals) / len(vals) if vals else 50) + bonus + exp
        if bonus > 0:
            why.append(tr("{role} profile: often in the back, sees the round unfold", role=tr(art)))
        if hours >= 1500:
            why.append(tr("{n} h played", n=num(hours)))
        res.append({"steamid": m["steamid"], "name": m["name"], "score": round(score), "why": why})
    res.sort(key=lambda x: -x["score"])
    return res


# ---------- maps ----------
def map_pool(M, meta):
    maps = set(PREMIER)
    for m in M:
        maps |= set(m["maps"]) | set((m["adv"].get("maps") or {}).keys())
    maps = {mp for mp in maps if mp.startswith("de_")}   # hostage maps (cs_*): no sites, no plan
    rows = []
    for mp in maps:
        per, w, t, known = [], 0, 0, 0
        for m in M:
            rec = (m["adv"].get("maps") or {}).get(mp) or {}
            rw = sum((rec.get(s) or {}).get("record", [0, 0])[0] for s in ("T", "CT"))
            rt = sum((rec.get(s) or {}).get("record", [0, 0])[1] for s in ("T", "CT"))
            n = (m["maps"].get(mp) or {}).get("matches", 0)
            if rt:
                known += 1
            w, t = w + rw, t + rt
            per.append({"steamid": m["steamid"], "name": m["name"], "matches": n, "rounds": rt, "win": round(100 * rw / rt) if rt else None})
        comfort = (w + 0.5 * 24) / (t + 24) * 100  # rounds won, pulled toward 50 % with few rounds
        rows.append({"map": mp, "premier": mp in PREMIER, "members_with_data": known, "rounds": t,
                     "round_win": round(100 * w / t) if t else None, "comfort": round(comfort, 1), "per_member": per,
                     "plants": (meta.get(mp) or {}).get("plants")})
    rows.sort(key=lambda r: (-(r["members_with_data"] > 0), -r["comfort"], -r["rounds"]))
    prem = [r for r in rows if r["premier"]]
    picks = [r["map"] for r in prem if r["members_with_data"]][:2]
    work = [r["map"] for r in prem if r["map"] not in picks][:2]
    return rows, picks, work


# ---------- per-map plan ----------
def _zone_perf(m, mp, side, key):
    for z in ((m["maps"].get(mp) or {}).get("sides", {}).get(side, {}) or {}).get("zones", []):
        if z["key"] == key:
            return z
    return None


def _shrunk(z, prior=0.5, k=6):
    if not z:
        return prior
    return (z["k"] + prior * k) / (z["k"] + z["d"] + k)


def _ref_map(M, mp):
    """Pool data of a map (identical for every member who played it): zones meta, spots, pool zones, lineups."""
    ref = None
    for m in M:
        x = m["maps"].get(mp)
        if x and (ref is None or x.get("pool", 0) > ref.get("pool", 0)):
            ref = x
    return ref


def _kd(k, d):
    """'7-2' below 10 duels (a percentage would say too much), '64% (18-10)' above."""
    k, d = int(k or 0), int(d or 0)
    return f"{k}-{d}" if k + d < 10 else f"{round(100 * k / (k + d))}% ({k}-{d})"


def _candidates(ref, side):
    """Positions of a side: the base's kill spots with enough duels, completed by the base's zones (zone centre)."""
    spots = [dict(s) for s in ref["sides"].get(side, {}).get("best_spots", [])
             if s.get("zone") and (s.get("k", 0) + s.get("d", 0) >= 6 or s.get("players", 0) >= 4)]
    have = {s["zone"] for s in spots}
    meta_px = {z["name"]: z for z in ref.get("zones_meta", [])}
    for z in ref["sides"].get(side, {}).get("pool_zones", []):
        zm = meta_px.get(z["name"])
        if zm and z["name"] not in have and z["k"] + z["d"] >= 8 and "spawn" not in z["key"].lower():
            spots.append({"px": zm["px"], "level": zm.get("level"), "zone": z["name"], "k": z["k"], "d": z["d"], "win": z.get("win"),
                          "hold_pct": z.get("hold_pct"), "scoped_pct": None, "t_med": z.get("t_med"), "players": max(1, round((z["k"] + z["d"]) / 4))})
            have.add(z["name"])
    for s in spots:
        s["score"] = (s.get("k", 0) + 3) / (s.get("k", 0) + s.get("d", 0) + 6) * min(s.get("k", 0) + s.get("d", 0) + 4, 30)
    return spots


# ---------- the base's plays on a map (lanes.py): what the CTs face, what the Ts can run ----------
_TDF = (None, None)


def _tdf():
    """The T-side rounds of the base, kept while the data doesn't change (the server lives for days: new demos
    must show up in the next plan)."""
    global _TDF
    from wily.insights import tside
    st = tside._stamp()
    if _TDF[0] != st:
        _TDF = (st, tside.load())
    return _TDF[1]


def _tside_maps(maps):
    try:
        from wily.insights import tside
        return (tside.tendencies(list(maps)) or {}).get("maps") or {}
    except Exception as e:  # the plan stays usable without it
        print("plays unavailable:", e)
        return {}


def _play_site(p):
    return None if p == "none" else p[-1] if p.startswith(("rush", "split")) else p[0]


def _d(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


class Regions:
    """Where a zone is: on a site, on the way the Ts take toward a site (the lanes), mid, or spawn side.
    Lanes first (learned from the Ts' paths), then the radar distance to the two sites."""

    def __init__(self, TS, ref, meta_regions):
        P, G = TS.get("plays") or {}, TS.get("geo") or {}
        self.sites = {L: ((G.get("sites") or {}).get(L) or {}).get("px") for L in ("A", "B")}
        self.lane_site, self.mid = defaultdict(set), set()
        for L, ls in (P.get("lanes") or {}).items():
            for ln in ls:
                for z in ln.get("zones", []):
                    self.lane_site[z].add(L)
                    if ln.get("mid"):
                        self.mid.add(z)
        self.px = {z["name"]: z.get("px") for z in ref.get("zones_meta", [])}
        self.lvl = {z["name"]: z.get("level") for z in ref.get("zones_meta", [])}
        sl = {L: ((G.get("sites") or {}).get(L) or {}).get("level") for L in ("A", "B")}
        # sites one above the other (Nuke): the radar distance means nothing, the level decides
        self.stacked = sl if sl["A"] and sl["B"] and sl["A"] != sl["B"] else None
        self.key = {z["name"]: z["key"] for z in ref.get("zones_meta", [])}
        self.old = meta_regions or {}
        sp = {n: p for n, p in self.px.items() if p and "spawn" in n.lower()}
        self.ct_spawn = next((p for n, p in sp.items() if n.lower().startswith("ct")), None)
        self.t_spawn = next((p for n, p in sp.items() if n.lower().startswith("t ")), None)

    def of(self, name, px=None):
        px = px or self.px.get(name)
        A, B = self.sites["A"], self.sites["B"]
        if not (A and B and px):
            return self.old.get(self.key.get(name, name), "mid")
        k = self.key.get(name, "")
        if k in ("BombsiteA", "BombsiteB"):
            return k[-1]
        dA, dB = _d(px, A), _d(px, B)
        lv = self.lvl.get(name)
        if self.stacked:
            on = [L for L in ("A", "B") if self.stacked[L] == lv]
            if on and _d(px, self.sites[on[0]]) <= 55:
                return on[0]
        elif min(dA, dB) <= max(0.12 * _d(A, B), 45):
            return "A" if dA < dB else "B"
        if name in self.mid:
            return "mid"
        if len(self.lane_site.get(name, ())) == 1:
            return next(iter(self.lane_site[name]))
        if self.stacked and lv:
            return next((L for L in ("A", "B") if self.stacked[L] == lv), "mid")
        r = dA / max(dA + dB, 1)
        return "A" if r < 0.42 else "B" if r > 0.58 else "mid"

    def group(self, name):
        """Vocabulary group: 'A site', 'A approach (T side)', 'Mid', 'CT side', 'T side'."""
        px = self.px.get(name)
        if "spawn" in name.lower():
            return "Spawns"
        reg = self.of(name, px)
        A, B = self.sites["A"], self.sites["B"]
        near = 55 if self.stacked else max(0.12 * _d(A, B), 45) if A and B else 0
        if self.key.get(name) in ("BombsiteA", "BombsiteB") or (reg in ("A", "B") and px and self.sites[reg] and _d(px, self.sites[reg]) <= near
                                                                  and (not self.stacked or self.lvl.get(name) == self.stacked[reg])):
            return f"{reg} site"
        t_side = name in self.lane_site or name.startswith("T ") or (px and self.ct_spawn and self.t_spawn and _d(px, self.t_spawn) < _d(px, self.ct_spawn))
        if reg in ("A", "B") and t_side:
            return f"{reg} approach (T side)"
        if not t_side and name not in self.mid:
            return "CT side / rotations"
        return f"{reg} site" if reg in ("A", "B") else "Mid"


def team_rounds(M, mp, matches):
    """The tside rows of this map, each tagged with the team's side that round ('T', 'CT' or None)."""
    df = _tdf()
    g = df[df["map"] == mp].copy() if len(df) else df
    if not len(g):
        return g
    first = {r["id"]: r.get("side1") for r in matches if r.get("map") == mp}
    g["team"] = [None if str(m) not in first else ("T" if (t == "a") == (first[str(m)] == "T") else "CT")
                 for m, t in zip(g["match"].astype(str), g.t_team)]
    return g


def threats(TS, g):
    """CT reading of a map: how often each site and each lane is attacked (all rounds of the base), how often it is a
    rush, and every play with how the Ts fare and how the team fared against it."""
    P = TS.get("plays") or {}
    prior, use, lanes = (P.get("prior") or {}).get("all") or {}, P.get("use") or {}, P.get("lanes") or {}
    if not prior or not lanes:
        return None
    att = 1 - prior.get("none", 0)
    sites = {}
    for L in ("A", "B"):
        ps = {p: v for p, v in prior.items() if _play_site(p) == L}
        tot = sum(ps.values())
        rush = sum(v for p, v in ps.items() if p.startswith("rush"))
        ls = []
        for i, ln in enumerate(lanes.get(L) or []):
            odds = sum(v * (use.get(p) or {}).get(str(i), 0) for p, v in ps.items())
            r = sum(v * (use.get(p) or {}).get(str(i), 0) for p, v in ps.items() if p.startswith("rush"))
            ls.append({"i": i, "key": f"{L}{i}", "name": ln["name"], "px": ln["px"], "level": ln.get("level"), "mid": ln.get("mid"),
                       "main": ln.get("main"), "zones": ln.get("zones"), "odds": round(100 * odds / max(att, 1e-6)),
                       "rush": round(100 * r / max(odds, 1e-6)) if odds else 0, "share": ln.get("share")})
        sites[L] = {"odds": round(100 * tot / max(att, 1e-6)), "rush": round(100 * rush / max(tot, 1e-6)) if tot else 0, "lanes": ls}
    plays = []
    for p, v in sorted(prior.items(), key=lambda kv: -kv[1]):
        x = g[g.play == p] if len(g) else g
        n = int(len(x))
        if p == "none" or n < 5:
            continue
        hit = pd.to_numeric(x[x.entered.astype(bool)].hit_t, errors="coerce").dropna() if n else []
        tT = x[x.team == "T"] if "team" in x else x.iloc[0:0]
        tC = x[x.team == "CT"] if "team" in x else x.iloc[0:0]
        plays.append({"key": p, "label": (P.get("label") or {}).get(p, p), "site": _play_site(p), "odds": round(100 * v),
                      "n": n, "t_win": round(100 * x.T_won.astype(bool).mean()), "hit_t": round(float(np.median(hit))) if len(hit) >= 3 else None,
                      "lanes": [int(i) for i, u in sorted((use.get(p) or {}).items(), key=lambda kv: -kv[1]) if u >= 0.25],
                      "team_t": {"n": int(len(tT)), "won": int(tT.T_won.astype(bool).sum())},
                      "team_ct": {"n": int(len(tC)), "won": int((~tC.T_won.astype(bool)).sum())}})
    heavy = "A" if sites["A"]["odds"] >= sites["B"]["odds"] else "B"
    return {"sites": sites, "plays": plays, "heavy": heavy, "rounds": P.get("rounds"),
            "t_avg": round(100 * g.T_won.astype(bool).mean()) if len(g) else None,
            "rush_s": None, "geo_sites": {L: ((TS.get("geo") or {}).get("sites") or {}).get(L) for L in ("A", "B")}}


def _member_spots(m, mp, side, R):
    """A member's spots on a side, with their region: the zones they play, duels won, multi-kill rounds."""
    out = []
    for s in ((m["plan"].get("spots") or {}).get(mp) or {}).get(side) or []:
        out.append(dict(s, region=R.of(s["name"], s.get("px"))))
    return out


def _strength(s):
    """How good a member's own spot is: duels won (shrunk toward 50%) plus the multi-kill rounds made from it."""
    if not s:
        return 0.5
    return (s.get("k") or 0) / max((s.get("k") or 0) + (s.get("d") or 0) + 6, 1) + 3 / max((s.get("k") or 0) + (s.get("d") or 0) + 6, 1) \
        + 0.04 * min(s.get("multi2") or 0, 4) + 0.04 * min(s.get("multi3") or 0, 2)


def _lane_nades(M, mp, key, member_sid):
    """The grenades that close a T entrance (nades.lane_picks): the slot's own player's when known, else the best of the base."""
    order = [m for m in M if m["steamid"] == member_sid] + [m for m in M if m["steamid"] != member_sid]
    for m in order:
        picks = ((((m["plan"].get("nades") or {}).get("maps") or {}).get(mp) or {}).get("CT") or {}).get("lanes") or {}
        if picks.get(key):
            res = []
            for typ in ("molotov", "smoke", "he", "flash"):
                x = picks[key].get(typ)
                if x:
                    res.append({"type": typ, "role": x.get("role"), "from": x.get("from"), "to": x.get("to"), "timer": x.get("timer"),
                                "t": x.get("t_med"), "setpos": x.get("setpos"), "how": config.key_free(x.get("how")), "from_px": x.get("from_px"),
                                "to_px": x.get("to_px"), "level": x.get("level"), "n": x.get("n"),
                                "yours": bool(x.get("yours") and m["steamid"] == member_sid)})
            return res[:3]
    return []


CT_LABEL = {"anchor": N_("{site} anchor"), "support": N_("{site} support"), "mid": N_("Mid / rotation"), "awp": "AWP"}


def ct_setup(M, mp, ref, R, TH, size):
    """Five CT positions, each facing a T lane, ordered by how often that lane is attacked; members take the ones they
    fit (profile, their own spots on that site, multi-kills), extra players the rest."""
    spots = _candidates(ref, "CT")
    for s in spots:
        s["region"] = R.of(s["zone"], s.get("px"))
    heavy = TH["heavy"] if TH else "A"
    light = "B" if heavy == "A" else "A"
    lanes = {L: (TH["sites"][L]["lanes"] if TH else []) for L in ("A", "B")}
    mid_lanes = [ln for L in ("A", "B") for ln in lanes[L] if ln.get("mid")]

    def best(region, used, pred=lambda s: True):
        c = [s for s in spots if s["region"] == region and s["zone"] not in used and pred(s)]
        return max(c, key=lambda s: s["score"]) if c else None

    plan = [("anchor", heavy), ("anchor", light), ("support", heavy), ("awp", None), ("mid", "mid")]
    slots, used = [], set()
    for kind, region in plan:
        if kind == "awp":
            c = [x for x in spots if x["zone"] not in used and (x.get("scoped_pct") or 0) >= 25]
            s = max(c, key=lambda x: (x.get("scoped_pct") or 0) * x["score"]) if c else None
        else:
            s = best(region, used)
        if s is None and kind == "mid":   # no CT spot in the middle: a second player on the light site
            kind, region, s = "support", light, best(light, used)
        if s is None:
            s = best(heavy, used) or best(light, used) or best("mid", used)
        if s is None:
            continue
        used.add(s["zone"])
        site = region if kind in ("anchor", "support") and region in ("A", "B") else s["region"]
        # the T lane in front of the position: the anchor faces the site's most attacked lane, the support the next one
        # not faced yet, the mid player a mid lane, the AWP the nearest
        cand = mid_lanes if kind == "mid" and mid_lanes else lanes.get(site if site in ("A", "B") else heavy) or []
        faced = {(sl.get("lane") or {}).get("key") for sl in slots}
        if kind in ("anchor", "support") and cand:
            lane = max(cand, key=lambda ln: (ln["key"] not in faced, ln["odds"]))
        else:
            lane = min(cand, key=lambda ln: _d(ln["px"], s["px"])) if cand and s.get("px") else None
        slots.append({"kind": kind, "site": site, "zone": s["zone"], "px": s["px"], "level": s.get("level"),
                      "base": _kd(s.get("k"), s.get("d")) if s.get("k") is not None else None, "base_win": s.get("win"),
                      "hold_pct": s.get("hold_pct"), "t_med": s.get("t_med"),
                      "lane": {k: lane[k] for k in ("key", "name", "odds", "rush", "px", "level")} if lane else None})
    MS = {m["steamid"]: _member_spots(m, mp, "CT", R) for m in M}

    def fit(m, slot):
        s = m["scores"]
        role = {"anchor": s["anchor"] + 0.4 * s["closer"], "mid": 0.5 * s["entry"] + 0.5 * s["trader"], "awp": s["awper"] * 1.2,
                "support": s["support"] + 0.2 * s["anchor"]}[slot["kind"]] / 100
        mine = [x for x in MS[m["steamid"]] if x["region"] == slot["site"]]
        own = max((_strength(x) for x in mine), default=0.45)
        pres = min(sum(x.get("presence") or 0 for x in mine) / 25, 1) * 0.15
        return 0.5 * role + 0.5 * own + pres
    a = assign(M, slots, fit) if slots else {}
    for i, j in a.items():
        m, sl = M[i], slots[j]
        sl["member"], sl["name"] = m["steamid"], m["name"]
        mine = sorted([x for x in MS[m["steamid"]] if x["region"] == sl["site"]], key=lambda x: -_strength(x))
        top = mine[0] if mine else None
        why = []
        # the member's own strong spot on that site replaces the base's when it is clearly theirs
        taken = {x["zone"] for x in slots if x is not sl}
        mine = [x for x in mine if x["name"] not in taken]
        top = mine[0] if mine else None
        if top and ((top.get("multi2") or 0) >= 2 or ((top.get("k") or 0) + (top.get("d") or 0) >= 6 and _strength(top) >= 0.55)):
            if top["name"] != sl["zone"]:
                sl["base_zone"] = sl["zone"] + (f" ({sl['base']} in duels)" if sl.get("base") else "")
                sl["base"] = None
            sl.update(zone=top["name"], px=top["px"], level=top.get("level") or sl["level"], yours=True)
            why.append(tr("your spot: {kd} in duels", kd=_kd(top.get('k'), top.get('d'))))
            if top.get("multi2"):
                why.append(trn(top['multi2'], "{n} multi-kill round", "{n} multi-kill rounds") + (", " + tr("best {n} kills", n=top['best']) if (top.get("best") or 0) >= 3 else ""))
        else:
            z = _zone_perf(m, mp, "CT", R.key.get(sl["zone"], sl["zone"]))
            if z and z["k"] + z["d"] >= 4:
                why.append(tr("{kd} there", kd=_kd(z['k'], z['d'])))
            elif z and (z.get("presence") or 0) >= 5:
                why.append(tr("plays there {p}% of the time", p=f"{z['presence']:.0f}"))
        if sl["kind"] == "awp" and m["scores"]["awper"] >= 55:
            why.append(tr("AWPer profile"))
        if sl["kind"] == "anchor" and m["scores"]["anchor"] >= 60:
            why.append(tr("anchor profile"))
        sl["why"] = why
    extra = 0
    for sl in slots:
        sl.setdefault("why", [])
        if not sl.get("member"):
            extra += 1
            sl["extra"] = extra   # 'Extra player 1': who to tell, in the order of the list
        sl["do"] = CT_SLOT_DO[sl["kind"]]
        sl["label"] = CT_LABEL[sl["kind"]].format(site=sl["site"])
        sl["nades"] = _lane_nades(M, mp, sl["lane"]["key"], sl.get("member")) if sl.get("lane") else []
    # the most attacked lanes first: the order a smaller team fills
    slots.sort(key=lambda sl: (not sl.get("member"), -((sl.get("lane") or {}).get("odds") or 0)))
    seen = set()
    for sl in slots:
        k = (sl.get("lane") or {}).get("key")
        if k in seen:
            sl["nades"], sl["nades_with"] = [], next(x.get("name") or f"extra player {x.get('extra')}" for x in slots if (x.get("lane") or {}).get("key") == k)
        seen.add(k)
    return slots, heavy


def rotations(mp, slots, TS=None, R=None):
    from wily.insights import midround
    refs = midround.route_refs().get(mp, {})
    rot = (TS or {}).get("rotations") or {}
    out = []
    for sl in slots:
        if not sl.get("member"):   # anchors too: once the bomb is down on the other site, everyone retakes
            continue
        for L in ("A", "B"):
            if sl["site"] == L:
                continue
            r = refs.get(L, {})
            best = None
            for who in ("pro", "base"):
                rs = [x for x in (r.get(who) or {}).get("routes", []) if x.get("travel") is not None and x["travel"] >= 3 and x["n"] >= (5 if who == "pro" else 8)]
                if rs:
                    avg = ((r.get(who) or {}).get("timing") or {}).get("died_way") or 25
                    best = min(rs, key=lambda x: ((x["died"] * x["n"] + avg * 5) / (x["n"] + 5), x["travel"]))
                    best = dict(best, who=who)
                    break
            if not best:   # the base's rotations toward that site, from that very zone
                starts = [z for z in (rot.get(L) or {}) if z == sl["zone"]] or [z for z in (rot.get(L) or {}) if R and R.of(z) == sl["site"]]
                rs = [dict(x, start=z) for z in starts for x in rot[L][z].get("routes", []) if x["n"] >= 3 and (x.get("travel") or 0) >= 3]
                if rs:
                    best = dict(min(rs, key=lambda x: (x["died"], x["travel"])), who="zone")
                    best["route"] = " > ".join(([best["start"]] if best["start"] != best["route"][0] else []) + best["route"])
                    best["humanized"] = True
            if best:
                rt = best["route"].split(" > ")
                out.append({"member": sl["member"], "name": sl["name"], "to": L, "route": " → ".join(z if best.get("humanized") else humanize(z, mp) for z in rt),
                            "travel": best["travel"], "died": best["died"], "n": best["n"], "who": best["who"]})
    return out


def _lineups(M, mp, ref):
    """T lineups of the base on this map, and the ones each member already threw."""
    lus = [l for l in ref["sides"].get("T", {}).get("lineups", []) if l.get("to_zone")]
    mine = defaultdict(set)
    for m in M:
        for l in (((m["maps"].get(mp) or {}).get("sides", {}).get("T") or {}).get("lineups", [])):
            if l.get("by") == m["name"]:
                mine[m["steamid"]].add((l["type"], l["from_zone"], l["to_zone"]))
    return lus, mine


def t_plays(M, mp, ref, R, TH, troles, missing):
    """The plays to run as T: the base's best execute, split and rush on this map (T rounds won, pulled toward the
    average with few rounds, plus the team's own record), each with who goes through which lane and who throws what."""
    if not TH:
        return []
    lanes = {L: TH["sites"][L]["lanes"] for L in ("A", "B")}
    site_px = {L: (TH["geo_sites"].get(L) or {}).get("px") for L in ("A", "B")}
    avg = np.mean([p["t_win"] for p in TH["plays"]]) if TH["plays"] else 45

    def score(p):
        b = (p["t_win"] / 100 * p["n"] + avg / 100 * 15) / (p["n"] + 15)
        t = p["team_t"]
        return b + 0.5 * ((t["won"] + b * 6) / (t["n"] + 6) - b)
    pick = []
    for kind in ("exec", "split", "rush"):
        c = [p for p in TH["plays"] if p["n"] >= 8 and (p["key"].startswith(kind) if kind != "exec" else p["key"][1:].isdigit())]
        if c:
            b = max(c, key=score)
            tt = b["team_t"]
            if kind == "exec" or b["t_win"] >= avg or (tt["n"] >= 3 and tt["won"] / tt["n"] >= 0.5 and b["t_win"] >= avg - 5):
                pick.append(b)
    # everyone in a slot: members with their role, extra players with the roles left
    who = [(sid, r) for sid, r in troles.items()] + [(None, r) for r in missing]
    names = {m["steamid"]: m["name"] for m in M}
    lus, mine = _lineups(M, mp, ref)
    out = []
    for p in pick:
        L, ls = p["site"], lanes[p["site"]]
        used = [i for i in p["lanes"] if i < len(ls)] or ([next((i for i, x in enumerate(ls) if x.get("main")), 0)] if ls else [])
        main = used[0] if used else None
        second = used[1] if len(used) > 1 else None
        other = lanes["B" if L == "A" else "A"]
        lurk = next((ln for ln in other if ln.get("main")), other[0] if other else None)
        rows, extra = [], 0
        for sid, role in sorted(who, key=lambda x: ["entry", "trader", "support", "awper", "flex", "lurker"].index(x[1])):
            lane = main
            if p["key"].startswith("split") and second is not None and role in ("support", "lurker", "flex"):
                lane = second
            do = T_ROLE_DO[role]
            if role == "lurker" and not p["key"].startswith(("rush", "split")) and lurk:
                ln = {"name": lurk["name"], "px": lurk["px"], "level": lurk.get("level"), "lurk": True}
                do = tr("Show yourself through {zone} early to pull a CT, then cut the rotation when the team goes in.", zone=lurk['name'])
            elif role == "lurker" and p["key"].startswith("rush"):
                ln = {k: ls[lane][k] for k in ("name", "px", "level")} if lane is not None else None
                do = tr("Last of the rush: watch the flank behind the pack, then hold the bomb's way in.")
            else:
                ln = {k: ls[lane][k] for k in ("name", "px", "level")} if lane is not None else None
                if p["key"].startswith("split") and lane == second and role != "lurker":
                    do = tr("Second lane: arrive at the same time as the pack, from {zone}.", zone=ls[second]['name'])
            if not sid:
                extra += 1
            rows.append({"member": sid, "name": names.get(sid) or tr("Extra player {n}", n=extra), "extra": not sid, "role": role,
                         "role_name": ROLE_FR[role], "lane": ln, "do": do})
        # grenades: lineups landing on the site, thrown from the lanes the play uses (a rush keeps flashes and one molotov)
        c0 = site_px.get(L)
        lane_z = {i: set(ls[i]["zones"]) for i in used}
        near = [l for l in lus if c0 and l.get("to_px") and _d(l["to_px"], c0) <= 190 and (not R.stacked or R.of(l["to_zone"]) == L)]
        if len(near) < 3:
            near = [l for l in lus if R.of(l["to_zone"]) == L] or near
        want = (("flash", 2), ("molotov", 1)) if p["key"].startswith("rush") else (("smoke", 3), ("flash", 2), ("molotov", 1))
        items, load = [], defaultdict(int)
        in_lane = lambda l: next((i for i, z in lane_z.items() if l["from_zone"] in z), None)
        for typ, k in want:
            seen = set()
            pool = sorted([x for x in near if x["type"] == typ],
                          key=lambda l: (in_lane(l) is None, -((l.get("enemies_blind_avg") or 0) * 10 if typ == "flash" else (l.get("damage_avg") or 0) if typ == "molotov" else 0) - l["uses"] / 50))
            for l in pool:
                if l["to_zone"] in seen:
                    continue
                seen.add(l["to_zone"])
                li = in_lane(l)
                # thrower: someone in the lane it is thrown from, who already threw it, else by role (support first)
                pref = {"smoke": ["support", "flex", "trader", "awper", "entry"], "flash": ["trader", "support", "entry", "flex", "awper"],
                        "molotov": ["support", "entry", "trader", "flex", "awper"]}[typ]
                cand = [r for r in rows if r["role"] != "lurker" or p["key"].startswith("split")]
                thr = next((r for r in cand if r["member"] and (typ, l["from_zone"], l["to_zone"]) in mine[r["member"]]), None)
                if not thr:
                    for role in pref:
                        thr = next((r for r in cand if r["role"] == role and load[r["name"]] < 2), None)
                        if thr:
                            break
                if thr:
                    load[thr["name"]] += 1
                items.append({"type": typ, "from": l["from_zone"], "to": l["to_zone"], "setpos": l.get("setpos"), "t": l.get("t"), "how": config.key_free(l.get("how")),
                              "uses": l["uses"], "from_px": l.get("from_px"), "to_px": l.get("to_px"), "level": l.get("level"),
                              "lane": ls[li]["name"] if li is not None else None, "member": (thr or {}).get("member"),
                              "name": (thr or {}).get("name", "a teammate"),
                              "known": bool(thr and thr["member"] and (typ, l["from_zone"], l["to_zone"]) in mine[thr["member"]])})
                if len(seen) >= k:
                    break
        tt = p["team_t"]
        out.append({**{k: p[k] for k in ("key", "label", "site", "n", "t_win", "hit_t", "odds")}, "team_t": tt,
                    "kind": "rush" if p["key"].startswith("rush") else "split" if p["key"].startswith("split") else "exec",
                    "lanes": [{k: ls[i][k] for k in ("name", "px", "level", "zones")} for i in used], "site_px": c0,
                    "roles": rows, "nades": items})
    return out


def vocabulary(ref, R):
    groups = defaultdict(list)
    for z in ref.get("zones_meta", []):
        groups[R.group(z["name"])].append(z["name"])
    order = ["A site", "A approach (T side)", "Mid", "B approach (T side)", "B site", "CT side / rotations", "Spawns"]
    return [{"title": k, "zones": sorted(groups[k])} for k in order if groups.get(k)]


# ---------- together ----------
def synergy(M):
    """Matches played together (same team) and trades between each pair."""
    ids = [int(m["steamid"]) for m in M]
    pairs = {}
    for mid in os.listdir(config.DEEP):
        f = os.path.join(config.DEEP, mid, "samples.parquet")
        if not os.path.exists(f):
            continue
        s = pd.read_parquet(f, columns=["steamid", "side", "round"])
        present = [i for i in ids if i in set(s.steamid)]
        if len(present) < 2:
            continue
        r1 = s[s["round"] == s["round"].min()].drop_duplicates("steamid").set_index("steamid")["side"]
        D = pd.read_parquet(os.path.join(config.DEEP, mid, "duels.parquet"))
        R = os.path.join(config.DEEP, mid, "rounds.parquet")
        for a, b in itertools.combinations(sorted(present), 2):
            if r1.get(a) != r1.get(b):
                continue
            key = f"{a}-{b}"
            p = pairs.setdefault(key, {"a": str(a), "b": str(b), "matches": 0, "trades_ab": 0, "trades_ba": 0, "rounds": 0, "rounds_won": 0})
            p["matches"] += 1
            for x, y, k in ((a, b, "trades_ab"), (b, a, "trades_ba")):  # x avenges y
                for _, d in D[D.victim == y].iterrows():
                    if ((D.killer == x) & (D.victim == d.killer) & (D.tick > d.tick) & (D.tick <= d.tick + 5 * 64)).any():
                        p[k] += 1
            if os.path.exists(R):
                rr = pd.read_parquet(R)
                L = pd.read_parquet(os.path.join(config.DEEP, mid, "loadout.parquet"))
                la = L[L.steamid == a][["round", "side"]]
                w = rr.set_index("round").winner
                p["rounds"] += int(len(la))
                p["rounds_won"] += int(sum(w.get(r) == sd for r, sd in zip(la["round"], la.side)))
    names = {m["steamid"]: m["name"] for m in M}
    out = []
    for p in pairs.values():
        p["name_a"], p["name_b"] = names[p["a"]], names[p["b"]]
        p["round_win"] = round(100 * p["rounds_won"] / p["rounds"]) if p["rounds"] else None
        out.append(p)
    return sorted(out, key=lambda p: -p["matches"])


def collective(M):
    """Team averages of the percentiles that decide team rounds: the three weakest become collective goals."""
    checks = [("traded_pct", "bench", N_("Play in pairs (trades)"), N_("Entry + trader always together, 1-2 s apart. In Team Deathmatch or on a retake server: no duel without a teammate in range.")),
              ("flash_duels_pct", "bench", N_("Flash for the others"), N_("Every execute starts with a flash thrown for the entry. Call 'flash' before throwing it.")),
              ("nades_unused_24", "bench", N_("Empty the grenades"), N_("Team 40-second rule: at 1:15 on the clock as T, all grenades are gone.")),
              ("adv_conv", "mid", N_("Convert advantages"), N_("At 5v4: regroup on a site, crossfires, no more solo duels.")),
              ("isolated", "mid", N_("Spacing"), N_("Nobody dies alone: everyone must be tradable within 2 s.")),
              ("rt_solo", "mid", N_("Grouped retakes"), N_("Bomb planted: regroup and go in together on the same flash.")),
              ("rot_died", "mid", N_("Safe rotations"), N_("A single voice calls the rotation, on solid info, and we rotate through the covered route."))]
    res = []
    for key, where, title, do in checks:
        vals = [(_pct(m, key, where), m["name"]) for m in M]
        known = [(v, n) for v, n in vals if v is not None]
        if not known:
            continue
        avg = sum(v for v, _ in known) / len(known)
        res.append({"key": key, "title": title, "avg_percentile": round(avg), "do": do,
                    "members": [{"name": n, "percentile": round(v)} for v, n in known]})
    res.sort(key=lambda r: r["avg_percentile"])
    return res


def individual(M, troles, ct_by_member):
    out = []
    for m in M:
        rules = (m["adv"].get("rules") or [])[:2]
        weak = [w for w in ((m["plan"].get("mid") or {}).get("weak") or []) if w.get("id") != "note"][:1]
        warm = ((m["plan"].get("training") or {}).get("warmup") or [])[:1]
        out.append({"steamid": m["steamid"], "name": m["name"], "t_role": ROLE_FR.get(troles.get(m["steamid"]), None),
                    "ct_role": ct_by_member.get(m["steamid"]),
                    "archetype": m["arch"].get("name"),
                    "priorities": [r.get("short") or r.get("title") for r in rules] + [w.get("fix") for w in weak if w.get("fix")],
                    "drill": warm[0]["map"] + ": " + warm[0]["text"] if warm else None})
    return out


FULL_BUY = {"AWP", "AK-47", "M4A4", "M4A1-S", "AUG", "SG 553", "G3SG1", "SCAR-20"}


def economy(M, troles, awp_ok):
    rows = []
    awper = next((sid for sid, r in troles.items() if r == "awper"), None)
    for m in M:
        W = m["plan"].get("weapons") or {}
        force = [x for x in W.get("force", []) if x["rounds"] >= 8 and x["key"] not in FULL_BUY]
        force.sort(key=lambda x: -((x.get("win") or 0) * x["rounds"] + 40 * 10) / (x["rounds"] + 10) - x["adr"] / 20)
        pistol = [s for s in W.get("suggestions", []) if s["kind"] == "pistol_strong"]
        rows.append({"steamid": m["steamid"], "name": m["name"], "force": force[0]["key"] if force else None,
                     "force_adr": force[0]["adr"] if force else None, "force_win": force[0].get("win") if force else None,
                     "force_n": force[0]["rounds"] if force else None, "pistol": bool(pistol),
                     "awp": m["steamid"] == awper})
    order = ([awper] if awper else []) + [sid for sid, r in sorted(troles.items(), key=lambda x: ["entry", "trader", "support", "flex", "lurker", "awper"].index(x[1])) if sid != awper]
    names = {m["steamid"]: m["name"] for m in M}
    return {"awp": names.get(awper) if awper else None, "awp_ok": awp_ok, "members": rows,
            "drop_order": [names[s] for s in order], "pistol_openers": [r["name"] for r in rows if r["pistol"]],
            "rules": [tr("We buy together: full, force or eco, called before buy time."),
                      tr("The richest drops first, in this order: {names} (the AWP first).", names=", ".join(names[s] for s in order)) if awper
                      else tr("The richest drops first, in this order: {names}.", names=", ".join(names[s] for s in order)),
                      tr("Force only if everyone's money plus the loss bonus still pays a full buy next round ($3,700 as T, $3,900 as CT).")],
            "src": K.src("sw_economy", "h2k_economy")}


def team_matches(M):
    ids = {int(m["steamid"]) for m in M}
    rows = []
    for mid in os.listdir(config.DEEP):
        f = os.path.join(config.DEEP, mid, "samples.parquet")
        if not os.path.exists(f):
            continue
        s = pd.read_parquet(f, columns=["steamid", "side", "round"])
        r1 = s[s["round"] == s["round"].min()].drop_duplicates("steamid").set_index("steamid")["side"]
        here = [i for i in ids if i in r1.index]
        if len(here) < 2:
            continue
        sides = {r1[i] for i in here}
        if len(sides) != 1:
            continue
        st = None
        for i in here:
            st = _load(os.path.join(config.player_dir(i), "matches", mid, "stats.json"))
            if st:
                break
        meta = _load(os.path.join(config.DEEP, mid, "meta.json")) or {}
        rows.append({"id": mid, "map": meta.get("map"), "members": len(here), "side1": next(iter(sides)), "time": (st or {}).get("match", {}).get("time"),
                     "result": (st or {}).get("result"), "score": (st or {}).get("final_score")})
    rows.sort(key=lambda r: r["time"] or "", reverse=True)
    return rows


# ---------- build ----------
def team_id(ids):
    return hashlib.sha1("-".join(sorted(str(i) for i in ids)).encode()).hexdigest()[:10]


def build(ids, owner=None):
    ids = list(dict.fromkeys(str(int(i)) for i in ids))
    if not 2 <= len(ids) <= 5:
        raise ValueError("A team has 2 to 5 players (you + 1 to 4 teammates).")
    M = [member(i) for i in ids]
    missing = [ids[i] for i, m in enumerate(M) if m is None]
    if missing:
        raise ValueError("These players are not analyzed yet: " + ", ".join(missing) + ". Run their analysis first from the search bar.")
    meta = map_meta()
    troles, missing_roles, awp_ok = t_roles(M)
    pool, picks, work = map_pool(M, meta)
    maps_plan = {}
    ct_by_member = {}
    matches = team_matches(M)
    # plans for the maps the members have data on: Premier ones first, then the others they play (40 rounds or more)
    rows = sorted([r for r in pool if r["members_with_data"] and (r["premier"] or r["rounds"] >= 40)],
                  key=lambda r: (not r["premier"], -r["rounds"]))[:12]
    TSM = _tside_maps([r["map"] for r in rows])
    for row in rows:
        mp = row["map"]
        ref = _ref_map(M, mp)
        if not ref:
            continue
        TS = TSM.get(mp) or {}
        R = Regions(TS, ref, (meta.get(mp) or {}).get("regions"))
        TH = threats(TS, team_rounds(M, mp, matches))
        slots, heavy = ct_setup(M, mp, ref, R, TH, len(M))
        plays = t_plays(M, mp, ref, R, TH, troles, missing_roles)
        for sl in slots:
            if sl.get("member"):
                ct_by_member.setdefault(sl["member"], {})[mp] = f"{sl['label']} ({sl['zone']})"
        maps_plan[mp] = {"map": mp, "ct": slots, "heavy_site": heavy, "rotations": rotations(mp, slots, TS, R), "threats": TH,
                         "t_plays": plays, "vocab": vocabulary(ref, R), "plants": (meta.get(mp) or {}).get("plants") or {},
                         "levels": ref.get("levels"), "site_px": {L: (TH or {}).get("geo_sites", {}).get(L, {}).get("px") for L in ("A", "B")} if TH else (meta.get(mp) or {}).get("site_px"),
                         "videos": K.src(*K.MAP_VIDEOS.get(mp, []))}
    ct_summary = {sid: " · ".join(f"{mp[3:].capitalize()}: {lab}" for mp, lab in d.items()) for sid, d in ct_by_member.items()}
    plan = {"id": team_id(ids), "created": dt.datetime.now().isoformat(timespec="minutes"), "owner": str(owner or ids[0]),
            "members": [{"steamid": m["steamid"], "name": m["name"], "archetype": m["arch"].get("name"), "icon": m["arch"].get("icon"),
                         "light": m["light"], "has_scores": m["has_scores"], "scores": m["scores"],
                         "level": (m["plan"].get("level") or {}).get("name"), "t_role": troles.get(m["steamid"]),
                         "t_role_name": ROLE_FR.get(troles.get(m["steamid"])), "t_do": T_ROLE_DO.get(troles.get(m["steamid"]))} for m in M],
            "size": len(M), "missing_roles": [ROLE_FR[r] for r in missing_roles], "awp_ok": awp_ok,
            "igl": igl(M), "maps": pool, "picks": picks, "to_work": work, "plans": maps_plan,
            "economy": economy(M, troles, awp_ok), "synergy": synergy(M), "collective": collective(M)[:3],
            "individual": individual(M, troles, ct_summary), "matches": matches[:20], "n_matches": len(matches),
            "playbook": [{**{k: v for k, v in p.items() if k != "src"}, "src": K.src(*p["src"])} for p in K.PLAYBOOK
                         if set(p["tags"]) & {"rotation", "retake", "advantage", "postplant"}],
            "party": {k: {"title": v["title"], "items": v["items"], "src": K.src(*v["src"])} for k, v in K.PARTY.items()}}
    plan["party_key"] = {2: "duo", 3: "trio", 4: "quatuor", 5: "five"}[len(M)]
    config.write_json(os.path.join(TEAMS, f"{plan['id']}.json"), tr_static(json.loads(json.dumps(plan, default=str))))   # its fixed sentences in the player's language
    return plan


_NONE = object()


def suggestions(sid, limit=8):
    """Likely teammates of a player: partners seen in their team, then players met most often."""
    sid = int(sid)
    cnt, names = defaultdict(int), {}
    from wily.app import pipeline
    from wily.coaching import context
    his = set(pipeline.player_matches(sid))   # 15/10: his matches only (every match's positions were read)
    dg = context.digest(sid, his)   # 16/10: the first round's players of each match kept (context.digest)
    for mid in os.listdir(config.DEEP):
        if mid not in his or mid not in dg:
            continue
        r1 = dg[mid]["first"]   # their in-game name too: a teammate not analyzed here is shown by name (05/10, the beta)
        mine = next((sd for p, sd, _ in r1 if p == sid), _NONE)
        if mine is _NONE:
            continue
        for p, sd, nm in r1:
            if p != sid and sd == mine and p:
                cnt[p] += 1
                if nm:
                    names[p] = nm
    # 16/10: only the players who can be in the top (met at least as often as the limit-th one): the others were each
    # given a name and a profile check for nothing (every player ever met, one file check each)
    floor = sorted(cnt.values(), reverse=True)[limit - 1] if len(cnt) >= limit else 0
    rows = [{"steamid": str(p), "name": config.display_name(p, names.get(p)), "together": n,
             "analyzed": os.path.exists(os.path.join(config.player_dir(p), "advice.json"))} for p, n in cnt.items() if n >= floor]
    rows.sort(key=lambda r: (-r["together"], not r["analyzed"]))
    return rows[:limit]


def index():
    out = []
    for f in sorted(os.listdir(TEAMS)) if os.path.exists(TEAMS) else []:
        if f.endswith(".json") and f != "index.json":
            t = _load(os.path.join(TEAMS, f))
            out.append({"id": t["id"], "created": t["created"], "members": [{"steamid": m["steamid"], "name": m["name"]} for m in t["members"]]})
    return sorted(out, key=lambda t: t["created"], reverse=True)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    p = build(sys.argv[1:])
    print(json.dumps({k: p[k] for k in ("id", "members", "picks", "to_work", "igl", "missing_roles")}, ensure_ascii=False, indent=1)[:4000])


def mates_regions(sid, limit=6):
    """Your frequent teammates who have a profile, and where each one plays as CT on each map (share of their time on
    the A side, the B side, mid). Dead, you watch one of them: a fight at their spot tells where the Ts are."""
    meta = map_meta()
    out = {}
    for s in suggestions(sid, limit=limit):
        if not s.get("analyzed") or (s.get("together") or 0) < 2:   # a teammate met once won't be watched again
            continue
        f = os.path.join(config.player_dir(s["steamid"]), "cross.json")
        if not os.path.exists(f):
            continue
        try:
            cross = json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        maps = {}
        for m in cross.get("maps", []):
            regs = (meta.get(m.get("map")) or {}).get("regions") or {}
            W = {}
            for z in (((m.get("sides") or {}).get("CT") or {}).get("zones") or []):
                if "spawn" in str(z.get("key", "")).lower() or not z.get("presence"):
                    continue
                r = regs.get(z.get("key")) or "mid"
                W[r] = W.get(r, 0) + z["presence"]
            tot = sum(W.values())
            if tot >= 20:
                maps[m["map"]] = {k: round(v / tot, 2) for k, v in W.items()}
        if maps:
            out[str(s["steamid"])] = {"name": s.get("name"), "maps": maps}
    return out
