"""Lanes and plays of the T side.

How each bomb site is entered (its main, through mid, the other entrances), learned from where the Ts of every push
stood a few seconds before the site was taken; then the play of each round: a rush, a split (two lanes at once),
one lane, or no attack. Feeds the CT side of the in-game radar: the odds of each entrance and play, and when each
lane is usually pushed (to block it with a grenade at the right time).
"""
import collections
import json
import math
import os
import re

import numpy as np
import pandas as pd

from wily.core import config
from wily.insights import midround

GEO = os.path.join(config.OUT, "population", "tside_geo.json")
SKIP = {"TSpawn", "CTSpawn"}
MIDNAME = re.compile(r"mid|connector|catwalk|jungle|walkway|window", re.I)
BEFORE = 6.0      # where each T of the push stood 6 s before the site was taken
JOIN = 40.0       # approach zones less than 40° apart around the site: the same lane
MIN_SHARE = 0.03  # an approach zone used in less than 3 % of the takes does not make a lane
STACKED = 1200.0  # sites closer than this on the radar plane are stacked (Nuke): no "toward the other site"
STEP, T_MAX = 5, 100


def _maps_demos():
    from wily.core import ledger
    facts = ledger.match_facts()   # 15/10: not the 5,000 meta.json read again
    by = {}
    for mid in os.listdir(config.DEEP):
        f = facts.get(mid) or {}
        if f.get("map") and f.get("samples"):
            by.setdefault(f["map"], []).append(mid)
    return by


_GEO = {}


def geo(rebuild=False):
    """Per map: where each zone is (world and radar), the T spawn, the site centers, and the radar transform
    (so the app can put your live position on the radar). 16/10: kept while its 12 matches per map stay the same (the
    number of matches of the base before: built again at each new match), and in memory for 30 s (99 calls a plan,
    each reading the base's folder)."""
    import time
    try:
        mt = os.path.getmtime(GEO)
    except OSError:
        mt = None
    hit = _GEO.get("v")
    if not rebuild and hit and hit[0] == mt and time.monotonic() - hit[1] < 30:
        return hit[2]
    by = _maps_demos()
    try:   # v2: callouts (callouts.py); v3: what it's made of, the site centers and each map's 12 first matches
        sites = os.path.getmtime(midround.SITES)
    except OSError:
        sites = None
    n = f"v3-{sites}-" + ";".join(f"{mp}:{','.join(sorted(v)[:12])}" for mp, v in sorted(by.items()))
    if os.path.exists(GEO) and not rebuild:
        try:
            cur = json.load(open(GEO, encoding="utf-8"))
            if cur.get("_n") == n or config.role() == "client":   # a player's copy: the full base's, not its own few demos' (05/10)
                _GEO["v"] = (mt, time.monotonic(), cur)
                return cur
        except (OSError, ValueError):
            pass
    from wily.demos.map_analysis import ZoneMap, humanize
    sites = midround.site_centers()
    out = {"_n": n}
    for mp, mids in by.items():
        try:
            zm = ZoneMap(mp)
        except Exception:
            continue
        acc, sp = [], []
        for mid in sorted(mids)[:12]:
            s = pd.read_parquet(os.path.join(config.DEEP, mid, "samples.parquet"), columns=["zone", "X", "Y", "Z", "side", "t", "health"])
            s = s[s.health > 0]
            acc.append(s[["zone", "X", "Y", "Z"]])
            sp.append(s[(s.side == "T") & (s.t <= 1.0)][["X", "Y"]])
        s = pd.concat(acc)
        zones = {}
        for z, g in s.groupby("zone"):
            if len(g) < 20 or z in ("?", ""):
                continue
            x, y, zz = (float(g[c].median()) for c in ("X", "Y", "Z"))
            px, py = zm.px(x, y)
            zones[z] = {"c": [round(x), round(y), round(zz)], "px": [round(float(px)), round(float(py))],
                        "level": zm.level(zz)[0], "name": humanize(z, mp)}
        spw = pd.concat(sp)
        st = {}
        for L, v in (sites.get(mp) or {}).items():
            px, py = zm.px(v["c"][0], v["c"][1])
            st[L] = {"c": [round(c) for c in v["c"]], "px": [round(float(px)), round(float(py))], "level": zm.level(v["c"][2])[0]}
        cfg = zm.cfg
        out[mp] = {"zones": zones, "spawn": [round(float(spw.X.median())), round(float(spw.Y.median()))] if len(spw) else None,
                   "sites": st,
                   "radar": {"pos_x": cfg["pos_x"], "pos_y": cfg["pos_y"], "scale": cfg["scale"], "f": cfg.get("px_factor", 1.0),
                             "levels": [{k: lv[k] for k in ("key", "z_min", "z_max") if k in lv} for lv in cfg["levels"]]}}
    tmp = GEO + f".{os.getpid()}.tmp"
    json.dump(out, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, GEO)
    return out


def parse(paths):
    """'zone@t>zone@t>†@t;...' -> one list of (zone, time it was entered) per T."""
    out = []
    for tp in str(paths or "").split(";"):
        seq = []
        for e in tp.split(">"):
            z, _, t = e.rpartition("@")
            if z:
                try:
                    seq.append((z, float(t)))
                except ValueError:
                    pass
        if seq:
            out.append(seq)
    return out


def members(paths, site, ht, trail=False):
    """Where each T of the push stood BEFORE s before the site was taken: the ones who got in within 6 s of the take,
    and the ones killed on the way in the 10 s before (where they died). With trail: also the zones each one went
    through in the last 8 s (tells the zones that are one route, like Long A then A Ramp)."""
    tag = f"Bombsite{site}"
    out, trails = [], []
    for seq in parse(paths):
        way = []   # the zones before the i-th (16/10: kept as it goes, not rebuilt from the start at each step)
        for i, (z, t) in enumerate(seq):
            if z == "†":
                if ht - 10 <= t < ht and way:
                    out.append(way[-1])
                    trails.append({z2 for z2, t2 in seq[:i] if t2 >= t - 8 and z2 not in SKIP and not z2.startswith("Bombsite")} | {way[-1]})
                break
            if z == tag and ht - 1 <= t <= ht + 6:
                before = [z2 for z2, t2 in seq[:i] if t2 <= ht - BEFORE and z2 not in SKIP and not z2.startswith("Bombsite")]
                if before or way:
                    out.append((before or way)[-1])
                    last = [j for j, (z2, t2) in enumerate(seq[:i]) if t2 <= t - 8]
                    j0 = last[-1] if last else 0
                    trails.append({z2 for z2, _ in seq[j0:i] if z2 not in SKIP and not z2.startswith("Bombsite")})
                break
            if z not in SKIP and not z.startswith("Bombsite"):
                way.append(z)
    return (out, trails) if trail else out


def _adiff(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


class Geo:
    def __init__(self, G, mp):
        self.m = G.get(mp) or {}

    def theta(self, site, z):
        c = (self.m.get("zones", {}).get(z) or {}).get("c")
        s = (self.m.get("sites", {}).get(site) or {}).get("c")
        if not c or not s:
            return None
        return math.degrees(math.atan2(c[1] - s[1], c[0] - s[0])) % 360

    def dist(self, site, z):
        c = (self.m.get("zones", {}).get(z) or {}).get("c")
        s = (self.m.get("sites", {}).get(site) or {}).get("c")
        return math.hypot(c[0] - s[0], c[1] - s[1]) if c and s else None

    def toward_other(self, site):
        s, o = (self.m.get("sites", {}).get(x, {}).get("c") for x in (site, "B" if site == "A" else "A"))
        if not s or not o or math.hypot(o[0] - s[0], o[1] - s[1]) < STACKED:
            return None
        return math.degrees(math.atan2(o[1] - s[1], o[0] - s[0])) % 360


def learn(df, G):
    """Lanes of every site: approach zones grouped by direction around the site. The main lane is the one rushes
    use; a lane is 'mid' when it goes through mid (its name) or faces the other site."""
    from wily.demos.map_analysis import humanize
    appr, appr_rush, mem = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter), {}
    trails = collections.defaultdict(list)
    ent = df[df.entered & df.site.isin(["A", "B"]) & df.hit_t.notna()] if "t_paths" in df else df.iloc[0:0]
    for idx, mp, site, ht, paths, dyn in zip(ent.index, ent["map"], ent.site, ent.hit_t, ent.t_paths, ent.dyn):
        ms, tr = members(paths, site, float(ht), trail=True)
        mem[idx] = ms
        trails[(mp, site)] += tr
        for z in set(ms):
            appr[(mp, site)][z] += 1
            if dyn == "rush":
                appr_rush[(mp, site)][z] += 1
    lanes = {}
    for (mp, site), cnt in appr.items():
        g = Geo(G, mp)
        tot = sum(cnt.values())
        todo = [(z, n, g.theta(site, z)) for z, n in cnt.most_common() if n / tot >= MIN_SHARE]
        ls = []
        for z, n, th in todo:
            if th is None:
                continue
            best = min(ls, key=lambda L: _adiff(L["theta"], th)) if ls else None
            if best and _adiff(best["theta"], th) <= JOIN:
                best["zones"].append(z)
                best["n"] += n
            else:
                ls.append({"theta": th, "zones": [z], "n": n})
        if not ls:
            continue
        # two lanes are one route when the Ts of the push often go through both in their last 8 s
        merged = True
        while merged and len(ls) > 1:
            merged = False
            for i in range(len(ls)):
                for j in range(i + 1, len(ls)):
                    zi, zj = ls[i]["zones"][0], ls[j]["zones"][0]   # their main zones only: a stray zone joins nothing
                    both = sum(1 for t in trails[(mp, site)] if zi in t and zj in t)
                    if both >= 0.25 * min(cnt[zi], cnt[zj]):
                        keep, drop = (i, j) if ls[i]["n"] >= ls[j]["n"] else (j, i)
                        ls[keep]["zones"] += ls[drop]["zones"]
                        ls[keep]["n"] += ls[drop]["n"]
                        ls.pop(drop)
                        merged = True
                        break
                if merged:
                    break
        for L in ls:
            L["zones"].sort(key=lambda z: -cnt[z])
            L["core"] = [z for z in L["zones"] if cnt[z] >= 0.15 * L["n"]] or L["zones"][:1]   # its real zones, without strays
            L["rush"] = sum(appr_rush[(mp, site)][z] for z in L["zones"])
        ls.sort(key=lambda L: (-L["rush"], -L["n"]))
        other = g.toward_other(site)
        zinfo = G.get(mp, {}).get("zones", {})
        for i, L in enumerate(ls):
            top = L["zones"][0]
            L["main"] = i == 0
            L["mid"] = bool(MIDNAME.search(top)) or (not L["main"] and other is not None and _adiff(L["theta"], other) <= 45)
            # named after its most used zone, and the next one when it is used almost as much (Palace / T Ramp)
            second = L["zones"][1] if len(L["zones"]) > 1 and cnt[L["zones"][1]] >= 0.4 * cnt[top] else None
            c1, c2 = (zinfo.get(top) or {}).get("c"), (zinfo.get(second) or {}).get("c") if second else None
            if second and (not c1 or not c2 or math.hypot(c1[0] - c2[0], c1[1] - c2[1]) > 1300):
                second = None   # two zones far apart: the name of the first one says where the lane is
            L["name"] = humanize(top, mp) + (f" / {humanize(second, mp)}" if second else "")
            L["px"], L["level"] = (zinfo.get(top) or {}).get("px"), (zinfo.get(top) or {}).get("level")
            L["theta"] = round(L["theta"])
        lanes.setdefault(mp, {})[site] = ls
    return lanes, mem


def lane_of(lanes, g, site, z):
    ls = lanes or []
    for i, L in enumerate(ls):
        if z in L["zones"]:
            return i
    th = g.theta(site, z)
    if th is None or not ls:
        return None
    d = g.dist(site, z)
    i = min(range(len(ls)), key=lambda k: _adiff(ls[k]["theta"], th))
    return i if _adiff(ls[i]["theta"], th) <= 60 and (d is None or d <= 3000) else None


def classify(df, lanes, G, mem=None):
    """The play of every round: rushA/B, splitA/B (two lanes at once, 3+ Ts), A0/A1/B0... (one lane), none;
    and the lanes each attack used."""
    mem = mem or {}
    play, used = [], []
    # 16/10: the columns read as lists, not row by row through pandas (97,845 rows)
    col = lambda c: df[c].tolist() if c in df else [None] * len(df)
    has_paths = "t_paths" in df
    rows = zip(df.index, df["map"].tolist(), df.site.tolist(), col("entered"), col("hit_t"), col("t_paths"), col("stop_t"),
               col("t_events"), col("dyn"))
    for idx, mp, site, entered, hit_t, t_paths, stop_t, t_events, dyn in rows:
        if site not in ("A", "B"):
            play.append("none")
            used.append("")
            continue
        g = Geo(G, mp)
        L = (lanes.get(mp) or {}).get(site) or []
        if entered and hit_t == hit_t:
            zs = mem.get(idx)
            if zs is None and has_paths:
                zs = members(t_paths, site, float(hit_t))
            ls = [lane_of(L, g, site, z) for z in (zs or [])]
        else:   # stopped before the site: the zones of the fights of that push
            st = stop_t
            evs = [e.rpartition("@") for e in str(t_events or "").split(";") if "@" in e]
            ls = [lane_of(L, g, site, z) for z, _, t in evs if st == st and st is not None and st <= float(t) <= st + 10]
        ls = [x for x in ls if x is not None]
        distinct = sorted(set(ls))
        if dyn == "rush":
            p = f"rush{site}"
        elif len(distinct) >= 2 and len(ls) >= 3:
            p = f"split{site}"
        else:
            p = f"{site}{distinct[0] if distinct else 0}"
        play.append(p)
        used.append(",".join(str(x) for x in distinct))
    df["play"], df["play_lanes"] = play, used
    return df


def name(p, lanes_mp, used):
    """'Rush B through Upper Tunnel', 'Split A: Long A + Extended A', 'B through B Doors (mid)', 'No real attack'."""
    if p == "none":
        return "No real attack"
    site = p[-1] if p.startswith(("rush", "split")) else p[0]
    L = (lanes_mp or {}).get(site) or []
    idx = [i for i in used if 0 <= i < len(L)]
    lab = lambda i: L[i]["name"] + (" (mid)" if L[i]["mid"] and "mid" not in L[i]["name"].lower() else "")
    if p.startswith("rush"):
        return f"Rush {site}" + (f" through {lab(idx[0])}" if idx else "")
    if p.startswith("split"):
        return f"Split {site}" + (f": {L[idx[0]]['name']} + {L[idx[1]]['name']}" if len(idx) >= 2 else "")
    i = int(p[1:]) if p[1:].isdigit() else 0
    return f"{site} through {lab(i)}" if i < len(L) else f"{site} attack"


def _pct(x):
    return int(round(100 * x)) if x == x else None


def summary(g, lanes_mp, contact_zones=None, k=10):
    """Per map: the lanes, the odds of each play (all rounds and by kind of round), how the lanes are used by each
    play, and what the CT side sees for each play (when the site is taken, where the first duel is)."""
    if not lanes_mp or "play" not in g:
        return None
    plays = [p for p in g.play.value_counts().index if isinstance(p, str)]
    allp = g.play.value_counts(normalize=True)
    prior = {"all": {p: round(float(allp.get(p, 0.0)), 4) for p in plays}}
    for c, x in g[g.ctx.notna()].groupby("ctx"):
        vc = x.play.value_counts()
        prior[c] = {p: round(float((vc.get(p, 0) + k * allp.get(p, 0.0)) / (len(x) + k)), 4) for p in plays}
    # lanes each play uses (a split or a rush can use several)
    use = {}
    for p, x in g.groupby("play"):
        if p == "none":
            continue
        cnt = collections.Counter(int(i) for s in x.play_lanes for i in str(s).split(",") if i != "")
        use[p] = {str(i): round(n / len(x), 3) for i, n in cnt.items()}
        if not use[p] and p[-1:].isdigit():
            use[p] = {p[-1]: 1.0}
    # when the site gets taken (or the attack stopped), per play: chance nothing happened yet at t
    ts = list(range(0, T_MAX + 1, STEP))
    surv = {}
    commit = np.where(g.entered.to_numpy(dtype=bool), pd.to_numeric(g.hit_t, errors="coerce"), pd.to_numeric(g.stop_t, errors="coerce"))
    endt = pd.to_numeric(g.end_t, errors="coerce").fillna(115).to_numpy(dtype=float)
    for p in plays:
        sel = (g.play == p).to_numpy()
        if sel.sum() < 5:
            continue
        c = endt[sel] if p == "none" else np.where(np.isnan(commit[sel]), 115.0, commit[sel])
        surv[p] = [round(float((c > t).mean()) + 1e-3, 4) for t in ts]
    # first duel of the round, per play (pulled toward the play's site when a play has few rounds)
    contact = {}
    if contact_zones:
        f = g[g.first_zone.notna()]
        zs = list(contact_zones)
        for p in plays:
            x = f[f.play == p]
            site = "none" if p == "none" else p[-1] if p.startswith(("rush", "split")) else p[0]
            base = f[(f.site == ("-" if site == "none" else site))]
            if len(base) < 10:
                continue
            vb = base.first_zone.where(base.first_zone.isin(zs), "other").value_counts(normalize=True)
            vx = x.first_zone.where(x.first_zone.isin(zs), "other").value_counts()
            n = len(x)
            contact[p] = {z: round(float((vx.get(z, 0) + 8 * vb.get(z, 0.0) + 0.5) / (n + 8 + 0.5 * (len(zs) + 1))), 4) for z in zs + ["other"]}
    # names shown to the player: from the lanes each play uses most
    label = {p: name(p, lanes_mp, [int(i) for i, _ in sorted(use.get(p, {}).items(), key=lambda kv: -kv[1])]) for p in plays}
    n = len(g)
    from wily.demos.map_analysis import humanize
    mp = g["map"].iloc[0] if len(g) else None
    share = {}   # how often each lane is used when this site is attacked
    for site in ("A", "B"):
        x = g[g.play.str.endswith(site) | g.play.str.startswith(site)] if len(g) else g
        for i in range(len((lanes_mp or {}).get(site) or [])):
            share[(site, i)] = _pct(x.play_lanes.map(lambda u: str(i) in str(u).split(",")).mean()) if len(x) else None
    return {"lanes": {s: [{k: L[k] for k in ("name", "px", "level", "main", "mid", "theta")} | {"share": share.get((s, i)), "zones": [humanize(z, mp) for z in L.get("core") or L["zones"]]}
                          for i, L in enumerate(ls)] for s, ls in lanes_mp.items()},
            "prior": prior, "use": use, "surv": {"t": ts, **surv}, "contact": contact, "label": label,
            "n": {p: int((g.play == p).sum()) for p in plays}, "rounds": int(n),
            # how the Ts fare with each play (T rounds won), overall and by kind of round: what to run as T
            "win": {p: _pct(g[g.play == p].T_won.astype(bool).mean()) for p in plays if (g.play == p).sum() >= 5},
            "win_ctx": {c: {p: [int(len(y)), _pct(y.T_won.astype(bool).mean())] for p, y in x.groupby("play") if len(y) >= 5}
                        for c, x in g[g.ctx.notna()].groupby("ctx")}}


def radar(G, mp):
    """What the app needs to draw on the radar of this map: site centers and the transform for a live position."""
    m = G.get(mp) or {}
    return {"sites": m.get("sites"), "radar": m.get("radar"),
            "zones": {v["name"]: {"px": v["px"], "level": v["level"]} for v in (m.get("zones") or {}).values()}}
