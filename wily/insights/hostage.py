"""Hostage maps (cs_*): the roles of the bomb maps are reversed. The CTs attack (they go and get a hostage and bring
it back), the Ts defend. From the matches of the base, per map:

- the CTs' ways out of their spawn in the first 40 s (the zones walked, cut at the death), the most taken first, each
  drawn as the walk of one real player (the medoid), with the CTs' rounds won when one takes it and when they reach
  its end (game clock on the page);
- where the Ts hold 20 to 40 s in (share of their time), and the spots they kill CTs from in the first minute: the
  zones the CT attacker checks.

The ways are kept in the order of the map, not of their use (10/10, the user: numpad 1, 2, 3 = left, middle, right as
seen from the CT spawn toward the hostages, the same keys every day), each with a short name (its last zone no other way
takes: "Side Hall", "Back Way").

The carries (10/10): the demos record a hostage rescued (who, when) but not its pick-up. The carrier walks to the hostage
and back, so the pick-up is the point of his walk farthest from where he rescued it: from there, his way back, how long
it took, and the zones the ways back cross (where the Ts cut them). Only the carries that ended in a rescue are seen.

A map shows up with 40 rounds or more. Usage: python -m wily.insights.hostage  (prints the summary)"""
import json
import os
import sys

import numpy as np
import pandas as pd

from wily.core import config

ROUTE_MAX_T = 40.0
MIN_ROUNDS = 40
OUT = os.path.join(config.OUT, "hostage.json")


def _humanize(z, mp):
    from wily.demos.map_analysis import humanize
    return humanize(z, mp) if isinstance(z, str) and z else None


def _resample(pts, k=60):
    xy = np.array([[p[0], p[1]] for p in pts])
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
    if d[-1] <= 0:
        return None
    s = np.linspace(0, d[-1], k)
    idx = np.clip(np.searchsorted(d, s), 0, len(pts) - 1)
    return np.c_[np.interp(s, d, xy[:, 0]), np.interp(s, d, xy[:, 1])], [pts[i][2] for i in idx], [pts[i][3] for i in idx]


def _rescues(d):
    """The hostages rescued in a match: [{"round", "t", "steamid"}], read once from its demo (kept beside its tables)."""
    f = os.path.join(d, "hostages.json")
    if os.path.exists(f):
        try:
            return json.load(open(f, encoding="utf-8"))
        except (OSError, ValueError):
            pass
    dem = config.demo(os.path.basename(d))
    fr = os.path.join(d, "rounds.parquet")
    if not (os.path.exists(dem) and os.path.exists(fr)):
        return []
    from demoparser2 import DemoParser
    R = pd.read_parquet(fr, columns=["round", "start_tick", "end_tick"])
    try:
        e = DemoParser(dem).parse_event("hostage_rescued")
    except Exception:
        e = pd.DataFrame()
    if not isinstance(e, pd.DataFrame):   # no rescue in the match: an empty list
        e = pd.DataFrame()
    out = []
    for tick, s in zip(e.get("tick", []), e.get("user_steamid", [])):
        r = R[(R.start_tick <= tick) & (tick <= R.end_tick + 64)]
        if len(r):
            out.append({"round": int(r["round"].iloc[0]), "t": round((tick - int(r.start_tick.iloc[0])) / 64, 1), "steamid": str(s)})
    json.dump(out, open(f, "w", encoding="utf-8"))
    return out


def _carry(S, rs, mp):
    """One rescue's carry from the carrier's walk: picked up at the point farthest from where he rescued it."""
    x = S[(S["round"] == rs["round"]) & (S.steamid.astype(str) == rs["steamid"]) & (S.t <= rs["t"] + 0.5)].sort_values("t")
    if len(x) < 10:
        return None
    end = np.array([x.px.iloc[-1], x.py.iloc[-1]])
    dist = np.hypot(x.px.values - end[0], x.py.values - end[1])
    i = int(np.argmax(dist))
    if dist[i] < 60:
        return None
    c = x.iloc[i:]
    zs, zt = [], {}
    for z, t in zip(c.zone, c.t):
        zh = _humanize(z, mp)
        if zh and (not zs or zs[-1] != zh):
            zs.append(zh)
            zt.setdefault(zh, float(t - c.t.iloc[0]))
    return {"from": _humanize(x.zone.iloc[i], mp), "to": zs[-1] if zs else None, "zones": zs, "zt": zt, "s": float(c.t.iloc[-1] - c.t.iloc[0]),
            "t0": float(c.t.iloc[0]), "pts": [(float(a), float(b), lv, float(t)) for a, b, lv, t in zip(c.px, c.py, c.level, c.t)]}


def _order(routes):
    """The ways from left to right as seen from the CT spawn toward the hostages (radar: y down), keys 1, 2, 3, and
    each one's short name: its last zone no other way takes."""
    if not routes:
        return routes
    st = np.mean([r["pts"][0][:2] for r in routes], axis=0)
    ends = np.array([r["pts"][-1][:2] for r in routes])
    h = ends.mean(axis=0) - st
    side = [h[0] * (e[1] - st[1]) - h[1] * (e[0] - st[0]) for e in ends]   # < 0: left of the heading
    routes = [r for _, r in sorted(zip(side, routes), key=lambda q: q[0])]
    for k, r in enumerate(routes, 1):
        own = [z for z in r["zones"] if not any(z in o["zones"] for o in routes if o is not r)]
        r.update(key=k, name=(own or r["zones"])[-1])
    return routes


def map_summary(mp, dirs, cell=24):
    ways, holds, danger, n_rounds, ct_won, rescued = {}, {}, {}, 0, 0, 0
    carries = []
    for d in dirs:
        fs, fr, fd = (os.path.join(d, x) for x in ("samples.parquet", "rounds.parquet", "duels.parquet"))
        if not (os.path.exists(fs) and os.path.exists(fr)):
            continue
        mid = os.path.basename(d)
        R = pd.read_parquet(fr)
        won = {int(r): w == "CT" for r, w in zip(R["round"], R.winner)}
        n_rounds += len(R)
        ct_won += sum(won.values())
        rescued += int((R.reason.astype(str) == "hostage_rescued").sum())
        S = pd.read_parquet(fs, columns=["steamid", "side", "round", "t", "px", "py", "level", "zone", "health"])
        S = S[S.px.notna()].sort_values("t")
        for rs in _rescues(d):
            c = _carry(S, rs, mp)
            if c:
                carries.append(c)
        for (rnd, sid), x in S[(S.side == "CT") & (S.t <= ROUTE_MAX_T)].groupby(["round", "steamid"]):
            zs, pts = [], []
            for z, t, px_, py_, lv, hp in zip(x.zone, x.t, x.px, x.py, x.level, x.health):
                if hp is not None and hp <= 0:
                    break
                pts.append((float(px_), float(py_), lv, float(t)))
                zh = _humanize(z, mp)
                if zh and "spawn" not in zh.lower() and (not zs or zs[-1][0] != zh):
                    if zh in [q[0] for q in zs]:
                        zs = zs[:[q[0] for q in zs].index(zh) + 1]
                    else:
                        zs.append((zh, float(t)))
            zs = zs[:4]
            if len(zs) < 2 or len(pts) < 6:
                continue
            key = tuple(q[0] for q in zs)
            e = ways.setdefault(key, {"r": 0, "w": 0, "tr": [], "t_end": []})
            e["r"] += 1
            e["w"] += int(won.get(int(rnd), False))
            e["t_end"].append(zs[-1][1])
            if len(e["tr"]) < 80:
                e["tr"].append(pts)
        T = S[(S.side == "T") & (S.health > 0) & (S.t >= 20) & (S.t <= 40)]
        for (lv, cx, cy), x in T.groupby(["level", (T.px // cell).astype(int), (T.py // cell).astype(int)]):
            h = holds.setdefault((lv, cx, cy), {"n": 0, "z": {}})
            h["n"] += len(x)
            for z in x.zone.dropna():
                h["z"][z] = h["z"].get(z, 0) + 1
        if os.path.exists(fd):
            D = pd.read_parquet(fd, columns=["t", "killer_side", "victim_side", "killer_px", "killer_py", "killer_level", "killer_zone"])
            D = D[(D.killer_side == "T") & (D.victim_side == "CT") & (D.t <= 60) & D.killer_px.notna()]
            for (lv, cx, cy), x in D.groupby(["killer_level", (D.killer_px // cell).astype(int), (D.killer_py // cell).astype(int)]):
                k = danger.setdefault((lv, cx, cy), {"n": 0, "z": {}})
                k["n"] += len(x)
                for z in x.killer_zone.dropna():
                    k["z"][z] = k["z"].get(z, 0) + 1
    if n_rounds < MIN_ROUNDS:
        return None
    base = ct_won / n_rounds
    routes = []
    for key, e in sorted(ways.items(), key=lambda kv: -kv[1]["r"])[:3]:
        if e["r"] < 8:
            continue
        rs = [r for r in (_resample(t) for t in e["tr"]) if r is not None]
        if not rs:
            continue
        A = np.array([r[0] for r in rs])
        med = int(np.argmin([np.mean(np.hypot(*(A - a).transpose(2, 0, 1))) for a in A]))
        xy, lv, ts = rs[med]
        routes.append({"zones": list(key), "n": e["r"], "won": round(100 * (e["w"] + 10 * base) / (e["r"] + 10)),
                       "t_end": round(float(np.median(e["t_end"])), 1),
                       "pts": [[round(float(x_), 1), round(float(y_), 1), l_, round(float(t_), 1)] for (x_, y_), l_, t_ in zip(xy, lv, ts)]})
    tot = sum(h["n"] for h in holds.values()) or 1
    hold = [{"px": [round((cx + .5) * cell), round((cy + .5) * cell)], "level": lv, "share": round(100 * h["n"] / tot, 1),
             "zone": _humanize(max(h["z"], key=h["z"].get), mp) if h["z"] else None}
            for (lv, cx, cy), h in sorted(holds.items(), key=lambda kv: -kv[1]["n"])[:8]]
    dk = sum(k["n"] for k in danger.values()) or 1
    dang = [{"px": [round((cx + .5) * cell), round((cy + .5) * cell)], "level": lv, "kills": k["n"], "share": round(100 * k["n"] / dk, 1),
             "zone": _humanize(max(k["z"], key=k["z"].get), mp) if k["z"] else None}
            for (lv, cx, cy), k in sorted(danger.items(), key=lambda kv: -kv[1]["n"])[:6] if k["n"] >= 3]
    return {"n_rounds": n_rounds, "n_matches": len(dirs), "ct_won": round(100 * base), "rescued": round(100 * rescued / n_rounds),
            "routes": _order(routes), "holds": hold, "danger": dang, "carry": _carries(carries), "geo": _geo(mp)}


def _geo(mp):
    """The radar's transform (a live position on the map: the carrier's spot when he presses numpad 7 / 9)."""
    try:
        from wily.insights import lanes as LN
        return LN.radar(LN.geo(), mp)
    except Exception:
        return None


def _carries(cs):
    """Per spot where hostages were picked up: the way back most like the others (the medoid), its time, where it ends;
    and the zones the ways back cross the most (neither the spot nor the rescue): where the Ts cut them, and how long
    after the pick-up the carrier gets there."""
    by = {}
    for c in cs:
        if c["from"]:
            by.setdefault(c["from"], []).append(c)
    spots = []
    for z, L in sorted(by.items(), key=lambda kv: -len(kv[1])):
        if len(L) < 3:
            continue
        rs = [(c, r) for c, r in ((c, _resample(c["pts"], 40)) for c in L) if r is not None]
        if not rs:
            continue
        A = np.array([r[0] for _, r in rs])
        med = int(np.argmin([np.mean(np.hypot(*(A - a).transpose(2, 0, 1))) for a in A]))
        c0, (xy, lv, ts) = rs[med]
        cut = {}
        for c in L:
            seen = set()
            for q in c["zones"][1:-1]:
                if q not in seen and q != z:
                    seen.add(q)
                    cut.setdefault(q, []).append(c)
        cuts = []
        for q, cl in sorted(cut.items(), key=lambda kv: -len(kv[1]))[:2]:
            if len(cl) < max(2, 0.4 * len(L)):
                continue
            cuts.append({"zone": q, "share": round(100 * len(cl) / len(L)), "after": round(float(np.median([c["zt"][q] for c in cl])), 1)})
        spots.append({"zone": z, "n": len(L), "s": round(float(np.median([c["s"] for c in L])), 1),
                      "t0": round(float(np.median([c["t0"] for c in L])), 1),
                      "to": max(sorted(set(c["to"] for c in L if c["to"]), key=str), key=[c["to"] for c in L].count, default=None),
                      "cut": cuts, "pts": [[round(float(x_), 1), round(float(y_), 1), l_, round(float(t_) - ts[0], 1)] for (x_, y_), l_, t_ in zip(xy, lv, ts)]})
    return spots


_NAMES = {}


def way_names(mp):
    """{1: "Back Way", 2: "Main Hall", 3: "Side Hall"} from the saved summary (no new computation: read 10 times a
    second by the keys' files)."""
    try:
        mt = os.path.getmtime(OUT)
    except OSError:
        return {}
    c = _NAMES.get(mp)
    if c and c[0] == mt:
        return c[1]
    try:
        m = (json.load(open(OUT, encoding="utf-8")).get("maps") or {}).get(mp) or {}
        names = {int(r["key"]): r["name"] for r in m.get("routes") or [] if r.get("key") and r.get("name")}
    except (OSError, ValueError, KeyError, TypeError):
        names = {}
    _NAMES[mp] = (mt, names)
    return names


def summary(force=False):
    """Every hostage map of the base; cached until a match is added."""
    from wily.insights import tside
    dirs = {m: d for m, d in tside._map_dirs().items() if m.startswith("cs_")}
    sig = sorted(os.path.basename(x) for d in dirs.values() for x in d)
    if not force and os.path.exists(OUT):
        try:
            c = json.load(open(OUT, encoding="utf-8"))
            if c.get("sig") == sig or config.role() == "client":   # a player's copy: the full base's, not its own few demos' (05/10)
                return c["maps"]
        except (OSError, ValueError):
            pass
    out = {}
    for mp, d in dirs.items():
        try:
            s = map_summary(mp, d)
        except Exception as e:
            print(f"{mp}: hostage summary unavailable ({e})")
            s = None
        if s:
            out[mp] = s
    json.dump({"sig": sig, "maps": out}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    config.low_priority()
    for mp, s in summary(force=True).items():
        print(mp, s["n_rounds"], "rounds, CT won", s["ct_won"], "%, rescued", s["rescued"], "%")
        for r in s["routes"]:
            print("   route", " > ".join(r["zones"]), r["n"], "walks, won", r["won"], "%, end at", r["t_end"], "s")
        print("   T holds:", [(h["zone"], h["share"]) for h in s["holds"][:5]])
        print("   T kill spots:", [(h["zone"], h["kills"]) for h in s["danger"][:5]])
