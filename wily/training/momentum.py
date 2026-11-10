"""Momentum: moving on the real maps (rework_entrainement.md, section 9; the user: "Momentum: a dedicated movement
training mode built to improve your map mobility, pathing, and jump precision using real map assets"). A module of its
own (a focus block), four drills, all from the base's real rounds:
- route: a real way run against the clock, a T or CT spawn to a site or a CT rotation from one site to the other. Its
  checkpoints on the ground in order (the gold line too, until you ran it once), your time at each one against the
  base's pace, at the end against the base's runs of that way (their median), its fastest runs (their 10th percentile)
  and the pros';
- jump: a jump the base's players really make onto something (a box, a ledge, a window), from its takeoff to where they
  land; the training server checks you land on top;
- stop: counter-strafing (the level's first fundamental): run left and right, STOP comes at full speed; measured, the
  time from your speed's drop to an accurate stop, and whether you went the other way after;
- silent: the last stretch of a real way into a site, walked (Shift) in the time given: a footstep heard is a miss.
The movement useful in a match only: no bunny hop, no surf (the document's proposal, 14/10).

Built on the coach's PC from the base (shipped with it, like the entries and Crossfire): out/train_momentum/<map>.json
- routes: every player's run from his spawn to the first site he entered, each CT's from one site to the other, running
  all the way (150 u/s or more each half second but one), from the matches' samples (every 0.5 s); grouped by their
  start, their site and the first three places they cross; the two most run ways of each start and site, 8 runs at
  least. A way's line is its most typical run read again from its demo (every 2 ticks, on the ground);
- jumps: from the demos (the game's player_jump), the jumps whose player landed 32 to 72 u higher on solid ground (not on
  a teammate: that is a boost), grouped by their takeoff and their landing; 6 jumps of 4 matches at least, outside the
  spawns; the kills its jumpers made from up there in the next 15 s.

Usage: python -m wily.training.momentum [map ...] (every bomb map of the base by default)."""
import json
import math
import os
import sys
import time
from collections import Counter

import numpy as np
import pandas as pd

from wily.core import config
from wily.core import i18n
from wily.training import crossfire

MO_D = os.path.join(config.OUT, "train_momentum")
V = 1
MATCHES = 400   # the base's matches read per map for the ways (their samples)
DEMOS = 120   # demos parsed per map for the jumps
RUN = 75.0   # u in half a second: running (150 u/s; a knife 250, a rifle 215, a walk 130)
MIN_RUNS = 8   # runs of a way at least
CP_EVERY = 450.0   # u between two checkpoints
CP_R, END_R = 120.0, 140.0   # how near a checkpoint counts, the way's end (Momentum.cs: the same)
SILENT_LEN = 750.0   # the silent walk's stretch, before the site
CLIMB = (32.0, 72.0)   # a jump onto something: higher than a step (18 u), lower than a boost
SITE = {"BombsiteA": "A", "BombsiteB": "B"}
HOW = {"jump": i18n.N_("jump"), "run": i18n.N_("running jump"), "duck": i18n.N_("crouch-jump"), "run+duck": i18n.N_("running crouch-jump")}


def path(mp):
    return os.path.join(MO_D, f"{mp}.json")


def load(mp, build=True):
    """The map's momentum data (cached); {} where it can't be built (a player's copy without it, no demo)."""
    try:
        with open(path(mp), encoding="utf-8") as f:
            c = json.load(f)
        if c.get("v") == V:
            return c
    except (OSError, ValueError):
        pass
    if not build or config.role() == "client":
        return {}
    from wily.training import replay
    return replay.in_worker(_build, mp)


# ---------------------------------------------------------------- the ways

def _bearing(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _route(zones, mp, limit=3):
    """The places a run crosses, in order, flickers dropped (A B A -> A): its way's name."""
    from wily.insights import nades
    out = []
    for z in zones:
        n = nades.humanize(z, mp) if isinstance(z, str) and z else None
        if not n or n == "?" or (out and out[-1] == n):
            continue
        if len(out) >= 2 and out[-2] == n:
            out.pop()
            continue
        out.append(n)
    return out[:limit]


def _runs(S, mp=None):
    """A match's running ways (its samples, every 0.5 s: tick, steamid, side, round, t, X, Y, Z, zone): each player's
    run from his spawn to the first site he entered, each CT's from one site to the other with no stop in between.
    t: the time to the way's end as the training server counts it (its last 140 u: the end's ring)."""
    out = []
    if S is None or not len(S):
        return out
    S = S.sort_values(["round", "steamid", "t"])
    for (rnd, sid), g in S.groupby(["round", "steamid"], sort=False):
        side = g.side.iloc[0]
        if len(g) < 5 or side not in ("T", "CT"):
            continue
        t = g.t.to_numpy(float)
        P = g[["X", "Y", "Z"]].to_numpy(float)
        tk = g.tick.to_numpy(np.int64)
        zones = g.zone.to_numpy(object)
        site = [SITE.get(z) if isinstance(z, str) else None for z in zones]
        step = np.r_[0.0, np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1]))]
        gap = np.r_[False, np.diff(t) > 0.75]   # a sample missing: dead, or not read

        def running(a, b):
            s = step[a + 1:b + 1]
            return len(s) >= 4 and not gap[a + 1:b + 1].any() and int((s < RUN).sum()) <= 1

        def run(kind, frm, a, b):
            dt = float(t[b] - t[a])
            v = float(step[a + 1:b + 1].sum()) / max(0.5, dt)
            return {"kind": kind, "side": side, "from": frm, "to": site[b], "t": round(dt - min(0.5, END_R / max(1.0, v)), 2),
                    "zones": _route([z for z in zones[a + 1:b] if z != zones[a]], mp), "P": P[a:b + 1], "tick0": int(tk[a]), "tick1": int(tk[b]), "sid": str(sid), "round": int(rnd)}
        if t[0] <= 0.6:   # there at the round's start: his spawn
            k = next((i for i in range(len(t)) if site[i]), None)
            if k is not None and k >= 4 and t[k] - t[0] <= 45 and running(0, k):
                out.append(run("spawn", side, 0, k))
        if side != "CT":
            continue
        i = 0
        while i < len(t) - 1:   # a CT's rotation: his last sample on a site, then the other site, running all the way
            if site[i] and site[i + 1] != site[i]:
                j = next((q for q in range(i + 1, len(t)) if site[q]), None)
                if j is None:
                    break
                if site[j] != site[i] and j - i >= 4 and t[j] - t[i] <= 40 and running(i, j):
                    out.append(run("rotate", site[i], i, j))
                i = j
                continue
            i += 1
    return out


def _resample(P, k=32):
    P = np.asarray(P, float)
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))]
    if d[-1] <= 0:
        return None
    u = np.linspace(0, d[-1], k)
    return np.c_[np.interp(u, d, P[:, 0]), np.interp(u, d, P[:, 1])]


def _length(Q):
    Q = np.asarray(Q, float)
    return float(np.hypot(*np.diff(Q[:, :2], axis=0).T).sum()) if len(Q) > 1 else 0.0


def _at(Q, L):
    """The point of a line at L u along it (on the ground: its height between its points)."""
    Q = np.asarray(Q, float)
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(Q[:, :2], axis=0).T))]
    i = int(np.clip(np.searchsorted(d, L) - 1, 0, len(Q) - 2))
    a = 0.0 if d[i + 1] <= d[i] else (L - d[i]) / (d[i + 1] - d[i])
    return Q[i] + (Q[i + 1] - Q[i]) * min(1.0, max(0.0, a))


def marks(line):
    """A way's checkpoints: one every 450 u along its line, and its end: [x, y, z, its share of the way]."""
    total = _length(line)
    out = []
    L = CP_EVERY
    while total > 0 and L < total - CP_EVERY / 2:
        p = _at(line, L)
        out.append([round(float(p[0]), 1), round(float(p[1]), 1), round(float(p[2]), 1), round(L / total, 3)])
        L += CP_EVERY
    e = np.asarray(line[-1], float)
    out.append([round(float(e[0]), 1), round(float(e[1]), 1), round(float(e[2]), 1), 1.0])
    return out


def _simple_line(P):
    """A way from half-second samples: its turns kept within 16 u (the 2-tick line's smoothing would flatten them)."""
    from wily.training import train
    Q = np.asarray(P, float)[:, :3]
    keep = train._rdp(Q, 16.0) if len(Q) > 2 else list(range(len(Q)))
    return [[round(float(v), 1) for v in Q[i]] for i in keep]


def _ways(runs, pro, mp):
    """The ways: runs grouped by their kind, side, start, site and first three places; for each start and site the two
    most run (8 runs at least), the base's median time, its fastest runs' (10th percentile), the pros'. "_cands": the
    runs nearest to its most typical one (one of them is read again from its demo for the line)."""
    groups = {}
    for r in runs:
        groups.setdefault((r["kind"], r["side"], r["from"], r["to"], tuple(r["zones"])), []).append(r)
    pros = {}
    for r in pro or []:
        pros.setdefault((r["kind"], r["side"], r["from"], r["to"], tuple(r["zones"])), []).append(r["t"])
    best = {}
    for key, g in groups.items():
        if len(g) >= MIN_RUNS:
            best.setdefault(key[:4], []).append((len(g), key))
    out = []
    for head, ks in sorted(best.items()):
        for n, key in sorted(ks, reverse=True)[:2]:
            g = groups[key]
            A = [x for x in (_resample(r["P"]) for r in g)]
            ok = [i for i, a in enumerate(A) if a is not None]
            if len(ok) < MIN_RUNS:
                continue
            M = np.array([A[i] for i in ok])
            dist = np.array([np.mean(np.hypot(*(M - m).transpose(2, 0, 1))) for m in M])
            order = [ok[i] for i in np.argsort(dist)]
            ts = np.array([r["t"] for r in g], float)
            pt = pros.get(key) or []
            kind, side, frm, to = head
            out.append({"id": f"{kind}:{side}:{frm}>{to}:{'>'.join(key[4])}", "kind": kind, "side": side, "from": frm, "to": to,
                        "via": list(key[4]), "n": len(g), "base": round(float(np.median(ts)), 2),
                        "best": round(float(np.percentile(ts, 10)), 2), "pro": round(float(np.median(pt)), 2) if len(pt) >= 3 else None,
                        "pro_n": len(pt), "_cands": [g[i] for i in order[:6]]})
    return out


def _finish(w, P, mp, fine=True):
    """A way's line on the ground, its checkpoints, its start and the way it faces, from its run's positions (fine: read
    from its demo every 2 ticks, else its half-second samples)."""
    from wily.training import train
    P = np.asarray(P, float)
    line = train._ground_line(P, mp) if fine else _simple_line(P)
    start = [round(float(v), 1) for v in P[0]]
    line[0] = start
    total = _length(line)
    ahead = _at(line, min(150.0, total))
    w.update(start=start, yaw=round(_bearing(start, ahead), 1), len=round(total), line=line, marks=marks(line))
    return w


# ---------------------------------------------------------------- the jumps

def _jumps(T, J, K, rounds, mid, mp=None):
    """A demo's jumps onto something. T: its players' ticks around the jumps (every 2 ticks: steamid, tick, X, Y, Z,
    is_airborne, ducking, last_place_name, team_num, g: the ground entity, pawn), J: its player_jump events (tick,
    user_steamid), K: its kills (tick, attacker_steamid, attacker_X/Y/Z), rounds: [(freeze end, end)]. Each jump:
    its takeoff, its landing (the first tick on the ground after it), its run-up's start (back while he ran, 0.6 s at
    most, same floor), crouched in the air or not, its speed, and the kills its jumper made from up there."""
    from wily.insights import nades
    out = []
    if T is None or not len(T) or J is None or not len(J):
        return out
    T = T.copy()
    T["steamid"] = T.steamid.astype(str)
    pawns = set(T.pawn.dropna().astype("int64")) if "pawn" in T else set()
    T = T.set_index(["steamid", "tick"]).sort_index()
    if K is not None and len(K):
        K = K.copy()
        K["attacker_steamid"] = K.attacker_steamid.astype(str)
    for k, sid in zip(J.tick.astype(int), J.user_steamid.astype(str)):
        rs = [a for a, b in rounds if a <= k <= b]
        if not rs:   # the freeze time, the warm-up, between two rounds
            continue
        try:
            g = T.loc[sid].loc[k - 40:k + 80]
        except KeyError:
            continue
        if len(g) < 20:
            continue
        ticks = g.index.to_numpy()
        i0 = int(np.searchsorted(ticks, k))
        if i0 >= len(g) - 4:
            continue
        air = g.is_airborne.astype(object).eq(True).to_numpy()
        land = next((i for i in range(i0 + 3, len(g)) if not air[i]), None)
        if land is None:
            continue
        P = g[["X", "Y", "Z"]].to_numpy(float)
        climb = float(P[land, 2] - P[i0, 2])
        if not CLIMB[0] <= climb <= CLIMB[1]:
            continue
        if "g" in g:
            gr = g.g.iloc[land]
            if gr == gr and gr is not None and int(gr) in pawns:   # on a teammate: a boost (boosts.py)
                continue
        duck = bool(g.ducking.iloc[i0:land + 1].astype(object).eq(True).any()) if "ducking" in g else False
        i8 = max(0, i0 - 4)
        speed = float(np.hypot(*(P[i0, :2] - P[i8, :2]))) / max(1e-3, (ticks[i0] - ticks[i8]) / 64)
        a = i0
        while a > 0 and ticks[i0] - ticks[a - 1] <= 40 and abs(P[a - 1, 2] - P[i0, 2]) < 24:
            dt = (ticks[a] - ticks[a - 1]) / 64
            if dt <= 0 or dt > 4 / 64 or np.hypot(*(P[a, :2] - P[a - 1, :2])) / dt < 100:
                break
            a -= 1
        kills = 0
        if K is not None and len(K):
            q = K[(K.attacker_steamid == sid) & (K.tick > ticks[land]) & (K.tick <= ticks[land] + 15 * 64)]
            if len(q):
                kills = int(((np.hypot(q.attacker_X.to_numpy(float) - P[land, 0], q.attacker_Y.to_numpy(float) - P[land, 1]) < 150)
                             & (np.abs(q.attacker_Z.to_numpy(float) - P[land, 2]) < 40)).sum())
        pl = g.last_place_name.astype(object).to_numpy() if "last_place_name" in g else [None] * len(g)
        tm = g.team_num.iloc[i0] if "team_num" in g else None
        out.append({"mid": str(mid), "sid": sid, "tick0": int(ticks[i0]), "tick1": int(ticks[land]),
                    "from": [round(float(v), 1) for v in P[i0]], "to": [round(float(v), 1) for v in P[land]],
                    "start": [round(float(v), 1) for v in P[a]], "climb": round(climb, 1), "duck": duck, "speed": round(speed),
                    "t": round((k - rs[0]) / 64, 1), "side": {2: "T", 3: "CT"}.get(int(tm) if tm == tm and tm is not None else 0),
                    "kills": kills, "zone": nades.humanize(pl[land], mp) if isinstance(pl[land], str) and pl[land] else None,
                    "from_zone": nades.humanize(pl[i0], mp) if isinstance(pl[i0], str) and pl[i0] else None})
    return out


def _jump_spots(rows, mp=None, keep=20, least=(6, 4)):
    """The jumps of the base grouped by their takeoff (72 u) and their landing (56 u, same heights): the spots 6 jumps
    of 4 matches at least made, outside the spawns, the most used first (matches, and the kills from up there twice)."""
    groups = []
    for x in sorted(rows, key=lambda x: (round(x["to"][0]), round(x["to"][1]), round(x["to"][2]))):
        for g in groups:
            c = g[0]
            if math.dist(c["to"][:2], x["to"][:2]) < 56 and abs(c["to"][2] - x["to"][2]) < 20 \
                    and math.dist(c["from"][:2], x["from"][:2]) < 72 and abs(c["from"][2] - x["from"][2]) < 24:
                g.append(x)
                break
        else:
            groups.append([x])
    out = []
    for g in groups:
        ms = {x["mid"] for x in g}
        if len(g) < least[0] or len(ms) < least[1]:
            continue
        zone = Counter(x["zone"] for x in g if x["zone"]).most_common(1)
        zone = zone[0][0] if zone else "?"
        if "spawn" in zone.lower():
            continue
        To = np.array([x["to"] for x in g], float)
        med = np.median(To, axis=0)
        to = g[int(np.argmin(np.hypot(To[:, 0] - med[0], To[:, 1] - med[1]) + np.abs(To[:, 2] - med[2])))]["to"]
        frm = np.median(np.array([x["from"] for x in g], float), axis=0)
        run = float(np.mean([x["speed"] >= 150 for x in g]))
        duck = float(np.mean([bool(x["duck"]) for x in g]))
        # 16/10, the user's video: "c'est bien de le mentionner qu'il est faisable en slow, dans ce sens-là ça ne fait pas
        # de bruit": the base's jumps of it taken walking (Shift, under 135 u/s)
        slow = float(np.mean([20 <= x["speed"] < 135 for x in g]))
        start = frm
        ups = [x for x in g if x["speed"] >= 150 and math.dist(x["start"][:2], x["from"][:2]) > 40]
        if run >= 0.5 and ups:   # a run-up: the most typical one (its way in, and its takeoff near the spot's)
            b = np.radians([_bearing(x["start"], x["from"]) for x in ups])
            mb = math.degrees(math.atan2(np.sin(b).mean(), np.cos(b).mean()))
            pick = min(ups, key=lambda x: abs((_bearing(x["start"], x["from"]) - mb + 180) % 360 - 180) + math.dist(x["from"][:2], frm[:2]) / 10)
            start = np.asarray(pick["start"], float)
        how = ("run+" if run >= 0.5 else "") + ("duck" if duck >= 0.6 else "")
        how = {"run+": "run", "": "jump"}.get(how, how)
        sides = Counter(x["side"] for x in g if x["side"])
        out.append({"id": f"{round(to[0])}:{round(to[1])}:{round(to[2])}", "from": [round(float(v), 1) for v in frm], "to": to,
                    "start": [round(float(v), 1) for v in start], "yaw": round(_bearing(start if math.dist(start[:2], to[:2]) > 16 else frm, to), 1),
                    "climb": round(float(np.median([x["climb"] for x in g])), 1), "duck": round(duck, 2), "run": round(run, 2), "how": how,
                    "slow": round(slow, 2), "hard": 1 if duck >= 0.6 and run >= 0.5 else 0,
                    "n": len(g), "matches": len(ms), "kills": int(sum(x["kills"] for x in g)), "zone": zone,
                    "from_zone": (Counter(x["from_zone"] for x in g if x["from_zone"]).most_common(1) or [("?", 0)])[0][0],
                    "side": sides.most_common(1)[0][0] if sides else "T", "t_med": round(float(np.median([x["t"] for x in g])), 1)})
    out.sort(key=lambda s: -(s["matches"] + 2 * s["kills"]))
    return out[:keep]


def _kz_spots(rows, mp=None, keep=8):
    """The hard jumps (19/10, his 17/10 video: "ce que je veux c'est du KZ, des solo jumps très durs à réussir mais
    possibles, qui te permettent d'accéder à des endroits plus vite": Fachwerk's crouched jump onto B's wooden box): a
    climb only a crouched jump makes (58 u and more), or a long one (150 to 300 u) with a climb; rare in the base for that
    very reason (the most used ones came first and buried them): 4 jumps of 3 matches are enough. The ones that make a
    position first (the kills from up there), then the hardest."""
    def hard(x):
        d = math.dist(x["from"][:2], x["to"][:2])
        return x["climb"] >= 58 or (150 <= d <= 300 and x["climb"] >= 24)
    out = _jump_spots([x for x in rows if hard(x)], mp, keep=60, least=(4, 3))
    for s in out:
        s.update(kz=True, hard=3)
    out.sort(key=lambda s: -(s["matches"] + 3 * s["kills"] + (6 if s["climb"] >= 58 else 0)))
    return out[:keep]


def rejump(mp):
    """The jumps chosen again from the ones the last build kept (no demo read): the routes as they are."""
    data = load(mp, build=False) or {}
    try:
        J = pd.read_parquet(path(mp).replace(".json", "_jumps.parquet"))
    except Exception:
        return None
    rows = []
    for r in J.to_dict("records"):
        for k in ("from", "to", "start"):
            if isinstance(r.get(k), str):
                r[k] = json.loads(r[k])
        rows.append(r)
    data["jumps"] = _jumps_of(rows, mp)
    data["strong"] = True   # the few strong ones (19/10): the drills' rules of that map follow them (_cands)
    with open(path(mp), "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    return data


STRONG_MAX = 6   # 19/10, his video: "retenir 30 sauts par map, ça crée de la surcharge cognitive"


def _jumps_of(rows, mp):
    """The map's few strong jumps (19/10, his 23:00 video: "ce sont strictement les seuls sauts qui m'intéressent", the
    jumps everyone knows are of no use, "des jumps peu connus ... qui permettent de faire des kills ou de surprendre"):
    - high ground: a chain of jumps that climbs 98 u or more onto a spot a kill was made from (Fachwerk: the shed to B
      high, from the cart or by the low wall, "on a le même point d'atterrissage"; the crate of Outside Long), and the
      other ways onto that same spot (a single crouched jump);
    - a silent tip: a jump from one place to another (a way round, "prendre tes adversaires dans leur dos") the base
      jumps running, done walking by a few (5 at least): nobody hears you come (Mid's stairs to Apps, Back of A to the A
      corridor);
    STRONG_MAX in all, the high ones first."""
    spawn = lambda z: "spawn" in str(z or "").lower()
    groups = []   # the chains by where they land
    for c in sorted(_boost_spots(rows, keep=60), key=lambda c: -c["n"]):
        g = next((g for g in groups if math.dist(g[0]["to"][:2], c["to"][:2]) <= 64 and abs(g[0]["to"][2] - c["to"][2]) <= 24), None)
        (g.append(c) if g else groups.append([c]))
    high = []
    for g in groups:
        if max(c["climb"] for c in g) >= 98 and sum(c["kills"] for c in g) >= 1 and not spawn(g[0]["zone"]):
            high.append(dict(g[0], why="high", kz=True, hard=3))
    # one way up, once (22/10, his test video on Dust2's Under A: "celui-là et le deuxième que tu m'as proposé c'est les
    # mêmes, juste il y a une marche en moins"): from the same start onto the same spot, the one that climbs the most
    one = []
    for h in sorted(high, key=lambda c: -c["climb"]):
        if not any(math.dist(h["from"][:2], o["from"][:2]) <= 64 and math.dist(h["to"][:2], o["to"][:2]) <= 96 for o in one):
            one.append(h)
    high = one
    singles = _jump_spots(rows, mp, keep=500, least=(4, 3))
    # the same landing point (his "même point d'atterrissage", 12 u in height: Outside Long's lower box next to the
    # crate is another spot)
    ways = [dict(s, why="high", kz=True, hard=3) for s in singles if s["climb"] >= 56
            and any(math.dist(h["to"][:2], s["to"][:2]) <= 64 and abs(h["to"][2] - s["to"][2]) <= 12 for h in high)]
    tips = [dict(s, why="silent", how="walk", hard=2) for s in singles
            if s["zone"] != s["from_zone"] and not spawn(s["zone"]) and not spawn(s["from_zone"])
            and round(s["slow"] * s["n"]) >= 5 and s["slow"] <= 0.15 and s["n"] >= 1.5 * s["matches"]]
    tips.sort(key=lambda s: -s["n"])
    return (high + ways + tips[:2])[:STRONG_MAX]


def _boost_spots(rows, keep=8):
    """The solo boosts (17/10, his 16/10 video: "c'est vraiment des solo boosts ou des jumps très compliqués à faire"):
    jumps in a row by one player, each from where the last one landed (64 u, 1.5 s), higher than one jump reaches (80 u
    and more above the first takeoff). Grouped by their first takeoff and their last landing: 3 of 2 matches at least."""
    by = {}
    for x in rows:
        if "tick0" in x:
            by.setdefault((x["mid"], x["sid"]), []).append(x)
    chains = []
    for js in by.values():
        js.sort(key=lambda x: x["tick0"])
        cur = [js[0]]
        for a, b in zip(js, js[1:]):
            if b["tick0"] - a["tick1"] <= 96 and math.dist(a["to"][:2], b["from"][:2]) <= 64 and abs(a["to"][2] - b["from"][2]) <= 24:
                cur.append(b)
                continue
            if len(cur) >= 2:
                chains.append(cur)
            cur = [b]
        if len(cur) >= 2:
            chains.append(cur)
    chains = [c for c in chains if c[-1]["to"][2] - c[0]["from"][2] >= 80]
    groups = []
    for c in chains:
        for g in groups:
            h = g[0]
            if len(h) == len(c) and math.dist(h[-1]["to"][:2], c[-1]["to"][:2]) < 56 and abs(h[-1]["to"][2] - c[-1]["to"][2]) < 20 \
                    and math.dist(h[0]["from"][:2], c[0]["from"][:2]) < 96:
                g.append(c)
                break
        else:
            groups.append([c])
    out = []
    for g in groups:
        ms = {c[0]["mid"] for c in g}
        if len(g) < 3 or len(ms) < 2:
            continue
        steps = len(g[0])
        med = lambda pts: [round(float(v), 1) for v in np.median(np.array(pts, float), axis=0)]
        frm, to = med([c[0]["from"] for c in g]), med([c[-1]["to"] for c in g])
        marks = [med([c[i]["to"] for c in g]) for i in range(steps - 1)]
        # where each next jump really leaves from (26/10, Train's T Upper: up to 64 u past where the last one landed, a
        # 155 u jump from the ring itself no run reaches)
        takeoffs = [med([c[i]["from"] for c in g]) for i in range(1, steps)]
        # how they take each one (26/10, Overpass's Upper Park: 63 u up at 230 u/s after 60-150 u of run-up, never from a
        # standstill): its run-up's start (their own, on what they stood on; the takeoff itself when they had none) and
        # its takeoff speed
        runs, speeds = [], []
        for i in range(steps):
            ups = [c[i] for c in g if math.dist(c[i]["start"][:2], c[i]["from"][:2]) > 40 and abs(c[i]["start"][2] - c[i]["from"][2]) < 24]
            runs.append(med([x["start"] for x in ups]) if len(ups) * 2 >= len(g) else (takeoffs[i - 1] if i else frm))
            speeds.append(round(float(np.median([float(c[i]["speed"]) for c in g])), 1))
        zone = Counter(c[-1]["zone"] for c in g if c[-1]["zone"]).most_common(1)
        duck = float(np.mean([any(bool(x["duck"]) for x in c) for c in g]))
        sides = Counter(c[0]["side"] for c in g if c[0]["side"])
        out.append({"id": f"boost:{round(to[0])}:{round(to[1])}:{round(to[2])}", "from": frm, "to": to, "start": frm, "marks": marks, "takeoffs": takeoffs, "runs": runs, "speeds": speeds,
                    "yaw": round(_bearing(frm, marks[0] if marks else to), 1), "climb": round(to[2] - frm[2], 1), "steps": steps,
                    "duck": round(duck, 2), "run": 0.0, "how": "duck" if duck >= 0.6 else "jump", "slow": 0.0,
                    "n": len(g), "matches": len(ms), "kills": int(sum(c[-1]["kills"] for c in g)), "zone": zone[0][0] if zone else "?",
                    "from_zone": (Counter(c[0]["from_zone"] for c in g if c[0]["from_zone"]).most_common(1) or [("?", 0)])[0][0],
                    "side": sides.most_common(1)[0][0] if sides else "T",
                    "t_med": round(float(np.median([c[0]["t"] for c in g])), 1), "hard": 2})
    out.sort(key=lambda s: -(s["matches"] + 2 * s["kills"]))
    return out[:keep]


# ---------------------------------------------------------------- the build (the coach's PC)

def _deep_dirs(base, mp):
    out = []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return out
    for d in names:
        try:
            with open(os.path.join(base, d, "meta.json"), encoding="utf-8") as f:
                if json.load(f).get("map") == mp:
                    out.append(d)
        except (OSError, ValueError):
            continue
    return out


SAMPLE_COLS = ["tick", "steamid", "side", "round", "t", "X", "Y", "Z", "zone"]


def _match_runs(base, d, mp):
    try:
        S = pd.read_parquet(os.path.join(base, d, "samples.parquet"), columns=SAMPLE_COLS)
    except Exception:
        return []
    rs = _runs(S, mp)
    for r in rs:
        r["mid"] = d
    return rs


def _rounds(d):
    try:
        R = pd.read_parquet(os.path.join(config.DEEP, d, "rounds.parquet"), columns=["start_tick", "end_tick"])
        return [(int(a), int(b)) for a, b in zip(R.start_tick, R.end_tick) if a == a and b == b]
    except Exception:
        return []


def _takeoffs(dp, rounds):
    """The jumps onto something from the players' state, every 4 ticks (15/10: Valve's matchmaking demos don't record
    player_jump, the base's 120 Mirage demos gave none): a player off the ground then back on it 32 to 72 u higher
    (8 u of margin: the exact heights are read again every 2 ticks). Each at the last tick he was on the ground."""
    ticks = [t for a, b in rounds for t in range(a, b, 4)]
    if not ticks:
        return None
    A = dp.parse_ticks(["Z", "is_airborne"], ticks=ticks)
    if not len(A):
        return None
    A = A.sort_values(["steamid", "tick"])
    rows = []
    for sid, g in A.groupby("steamid", sort=False):
        air = g.is_airborne.astype(object).eq(True).to_numpy()
        Z, tk = g.Z.to_numpy(float), g.tick.to_numpy()
        i = 1
        while i < len(g):
            if air[i] and not air[i - 1] and tk[i] - tk[i - 1] <= 4:
                j = i
                while j < len(g) and air[j] and tk[j] - tk[i] <= 96:
                    j += 1
                if j < len(g) and not air[j] and CLIMB[0] - 8 <= Z[j] - Z[i - 1] <= CLIMB[1] + 8:
                    rows.append((int(tk[i - 1]), sid))
                i = j
            i += 1
    return pd.DataFrame(rows, columns=["tick", "user_steamid"]) if rows else None


def _demo_jumps(d, mp):
    """One demo of the base: its jumps onto something."""
    from demoparser2 import DemoParser
    dp = DemoParser(config.demo(d))
    rounds = _rounds(d)
    try:
        J = dp.parse_event("player_jump")
    except Exception:
        J = None
    if not isinstance(J, pd.DataFrame) or not len(J) or "user_steamid" not in J:
        J = _takeoffs(dp, rounds)
    if not isinstance(J, pd.DataFrame) or not len(J):
        return []
    J = J[[any(a <= int(k) <= b for a, b in rounds) for k in J.tick]]
    if not len(J):
        return []
    want = sorted({t for k in J.tick.astype(int) for t in range(k - 40, k + 81, 2)})
    T = dp.parse_ticks(["X", "Y", "Z", "is_airborne", "ducking", "last_place_name", "team_num",
                        "CCSPlayerPawn.m_hGroundEntity", "CCSPlayerController.m_hPlayerPawn"], ticks=want)
    T = T.rename(columns={"CCSPlayerPawn.m_hGroundEntity": "g", "CCSPlayerController.m_hPlayerPawn": "pawn"})
    try:
        K = dp.parse_event("player_death", player=["X", "Y", "Z"])
    except Exception:
        K = None
    if isinstance(K, pd.DataFrame) and not {"attacker_steamid", "attacker_X", "attacker_Y", "attacker_Z"} <= set(K.columns):
        K = None
    return _jumps(T, J, K, rounds, d, mp)


def _demo_way(r):
    """A way's run read again from its demo, every 2 ticks (None without its demo)."""
    f = config.demo(r['mid'])
    if not os.path.exists(f):
        return None
    from demoparser2 import DemoParser
    T = DemoParser(f).parse_ticks(["X", "Y", "Z"], ticks=list(range(r["tick0"], r["tick1"] + 1, 2)))
    T = T[T.steamid.astype(str) == r["sid"]].sort_values("tick")
    return T[["X", "Y", "Z"]].to_numpy(float) if len(T) >= 10 else None


def _build(mp, matches=MATCHES, demos=DEMOS, log=print, jumps_only=False):
    """jumps_only: the demos' jumps kept beside (<map>_jumps.parquet), the map's drills as they are (20/10: read before its
    demos go to Drive, the user: "libérer E des 1 965 démos"; its strong jumps chosen later, on his go: rejump)"""
    os.makedirs(MO_D, exist_ok=True)
    t0 = time.time()
    dirs = _deep_dirs(config.DEEP, mp)
    runs = []
    for d in ([] if jumps_only else dirs[-matches:]):
        runs += _match_runs(config.DEEP, d, mp)
    pro = []
    pdir = os.path.join(config.OUT, "deep_pro")
    for d in ([] if jumps_only else _deep_dirs(pdir, mp)):
        pro += _match_runs(pdir, d, mp)
    ways = [] if jumps_only else _ways(runs, pro, mp)
    with_dem = [d for d in reversed(dirs) if config.has_demo(d)][:demos]
    jrows = []
    for d in with_dem:
        config.wait_for_match_end(what="momentum")   # your match first
        try:
            jrows += _demo_jumps(d, mp)
        except Exception as e:
            log("momentum", d, e)
    try:   # every jump kept beside (19/10: the drills' choice tried again without reading the demos, 15 min a map)
        pd.DataFrame([{k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in r.items()} for r in jrows]).to_parquet(
            path(mp).replace(".json", "_jumps.parquet"))
    except Exception as e:
        log("momentum jumps kept", mp, e)
    if jumps_only:
        log(f"momentum {mp}: {len(jrows)} jumps kept from {len(with_dem)} demos in {time.time() - t0:.0f} s")
        return None
    out = {"v": V, "routes": [], "jumps": _jumps_of(jrows, mp), "strong": True}
    for w in ways:
        cands = w.pop("_cands")
        P = None
        for r in cands:   # the most typical run whose demo is here, every 2 ticks (else its samples)
            try:
                P = _demo_way(r)
            except Exception as e:
                log("momentum way", r["mid"], e)
            if P is not None:
                break
        out["routes"].append(_finish(w, P, mp) if P is not None else _finish(w, cands[0]["P"], mp, fine=False))
    with open(path(mp), "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    log(f"momentum {mp}: {len(out['routes'])} ways ({len(runs)} runs, {len(pro)} of pros), {len(out['jumps'])} jumps "
        f"({len(jrows)} from {len(with_dem)} demos) in {time.time() - t0:.0f} s")
    return out


# ---------------------------------------------------------------- the drills

# what each level works on (rework_entrainement.md, section 4: the bases for all, the ways and the jumps from
# Intermediate; nothing locked until the training level is done)
# the jumps first (16/10, his video: "ce n'est pas du tout ce genre de trajet que je pense, c'est vraiment des solo boosts
# ou des jumps très compliqués à faire"), the timed ways after
# 19/10, his 17/10 video: no more dead stops ("nul à chier, ça n'a aucun intérêt", he died on purpose to skip them);
# a route only when the time is not full ("si vraiment il y a trop de temps, on met de la course"): the order is the
# priority, each variant's drills all once before the next variant
# 20/10, the user: "fais disparaître tous les trajets des momentums": the jumps only, at every level (the ways' data
# still built: _ways, routes; no drill of them)
VARIANTS = {"debut": ["jump"], "inter": ["jump"], None: ["jump"]}
SECS = {"route": 75, "jump": 70, "stop": 60, "silent": 50}
REPS = {"route": 3, "jump": 5, "stop": 8, "silent": 2}
JUMP_GOAL = 3   # landings of a jump drill
WALK = 100.0   # u/s: the silent walk's time allowed (a rifle walks at 112 u/s, a knife at 130)


def _id(mp, v, key):
    return f"momentum:{mp}:{v}:{key}"


def _spawn_name(side):
    return i18n.tr("T spawn") if side == "T" else i18n.tr("CT spawn")


def _silent(w):
    """The last 750 u of a way into a site: its line, its start, its length."""
    line = np.asarray(w["line"], float)
    total = _length(line)
    if total < 300:
        return None
    L0 = max(0.0, total - SILENT_LEN)
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(line[:, :2], axis=0).T))]
    p = _at(line, L0)
    rest = [[round(float(v), 1) for v in p]] + [list(map(float, q)) for q, dd in zip(line, d) if dd > L0 + 1]
    n = _length(rest)
    ahead = _at(rest, min(150.0, n))
    return {"line": rest, "start": [round(float(p[0]), 1), round(float(p[1]), 1), round(float(p[2]) + 2, 1)],
            "yaw": round(_bearing(p, ahead), 1), "len": n}


# 17/10: every jump played by the guided self-test's bot (tools/momentum_check.py); one it never landed, higher and
# crouched after each miss, is left out ("tout défini comme parfaitement prêt à être testé par un humain")
CHECKED = os.path.join(config.HERE, "resources", "momentum_checked.json")


HIS = os.path.join(config.HERE, "resources", "momentum_his.json")


def his(mp):
    """The jumps the user showed on that map (20/10, his recording: a smoke where each one starts, one where it lands;
    resources/momentum_his.json): the map's jumps, the base's left out (3 of his 7 on Fachwerk are in none of its 6,991
    jumps: no rule on the base finds them)."""
    out = []
    for x in (config.read_json(HIS, {}) or {}).get(mp) or []:
        out.append({"id": x["id"], "his": True, "kind": x["kind"], "from": x["from"], "to": x["to"], "start": x["from"], "marks": [],
                    "yaw": round(_bearing(x["from"], x["to"]), 1), "climb": round(x["to"][2] - x["from"][2], 1), "how": x["how"],
                    "side": x["side"], "zone": x["zone"], "from_zone": "", "n": 0, "matches": 0, "kills": 0,
                    "slow": 1.0 if x["how"] == "walk" else 0.0, "hard": 3, "why": x["kind"]})
    return out


def _his_name(k):
    """Its name (20/10: three of them "JUMP · B Site" in Prepare's list)."""
    return {"his:b-high-cart": i18n.tr("B high from the cart"), "his:b-high-wall": i18n.tr("B high by the low wall"),
            "his:window": i18n.tr("Mid's stairs to the window"), "his:antipush": i18n.tr("the anti-push boost"),
            "his:antipush-bis": i18n.tr("the anti-push, one jump further"),
            "his:long-crate": i18n.tr("Long's crate to crate"), "his:long-corridor": i18n.tr("behind the corridor"),
            "his:b-high-point": i18n.tr("B's high point")}.get(k, "")


def _his_why(k):
    """Why that jump of his (his words, 19/10 23:00 and 20/10)."""
    return {"his:b-high-cart": i18n.tr("from the cart onto the wooden plank: B high early, the Ts up there don't expect you"),
            "his:b-high-wall": i18n.tr("by the low wall, the same landing on B high"),
            "his:window": i18n.tr("Mid's stairs to the window, walked: nobody hears you come into Apps"),
            "his:antipush": i18n.tr("a solo boost against their push"),
            "his:antipush-bis": i18n.tr("from where the anti-push boost lands, one more jump: tricky to get in"),
            "his:long-crate": i18n.tr("crate to crate: another line over Long, a double peek"),
            "his:long-corridor": i18n.tr("behind the corridor, walked: you come out behind them"),
            "his:b-high-point": i18n.tr("the spot that puts you up high")}.get(k, "")


def _never_landed():
    return {x["id"] for x in (config.read_json(CHECKED, {}) or {}).get("jumps") or [] if x.get("ok") is False}


def mine(mp):
    """Your own jumps on that map (19/10: saved on the training server with !jump, the plugin's recorder writing
    coach/jumps.jsonl), as the base's are: a chain's first takeoff, each landing a ring, the last one the blue ring;
    first of all the jumps (hard 3), the last one of a name winning."""
    from wily.training import replay
    out = {}
    try:
        with open(os.path.join(replay.COACH, "jumps.jsonl"), encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                js = [j for j in r.get("jumps") or [] if j.get("from") and j.get("to")]
                if r.get("map") != mp or not js:
                    continue
                frm, to = js[0]["from"], js[-1]["to"]
                nxt = js[1]["from"] if len(js) > 1 else to
                duck = any((j.get("duck") or 0) >= 0.6 for j in js)
                out[r.get("name")] = {
                    "id": f"mine:{int(r.get('t') or 0)}", "mine": True, "name": r.get("name"), "from": frm, "to": to, "start": frm,
                    "marks": [j["to"] for j in js[:-1]], "takeoffs": [j["from"] for j in js[1:]], "yaw": round(_bearing(frm, nxt), 1), "climb": round(to[2] - frm[2], 1), "steps": len(js),
                    "duck": 1.0 if duck else 0.0, "run": float(np.mean([(j.get("speed") or 0) >= 150 for j in js])), "how": "duck" if duck else "jump",
                    "slow": float(np.mean([bool(j.get("slow")) for j in js])), "n": 0, "matches": 0, "kills": 0, "zone": r.get("name"),
                    "from_zone": "", "side": "CT" if r.get("team") == 3 else "T", "t_med": 0, "hard": 3}
    except OSError:
        pass
    return list(out.values())


def _cands(data, mp=None):
    """Each variant's exercises on the map: (key, its data)."""
    routes, jumps = data.get("routes") or [], data.get("jumps") or []
    out = _never_landed() if mp else set()
    h = his(mp) if mp else []
    m = mine(mp) if mp else []
    # a map where you saved your own jumps (!jump) has yours only, as one you marked has (23/10, the user: "pour momentum
    # d2 fait que les moments personnels enregistrés")
    jumps = m + (h or ([] if m else [s for s in jumps if _id(mp, "jump", s["id"]) not in out]))
    # 16/10, his video on Mirage's Side Alley stairs and Fachwerk's Bridge crates: "cet exercice, ce n'est pas du tout ce
    # genre de truc que je veux", "ça aussi, ça ne m'intéresse pas": a jump everyone makes is no drill. The solo boosts,
    # the hard ones (crouched, with a run-up), the ones that make a position (a kill from up there for 1 jump in 7)
    # 19/10, his 23:00 video: a map built again since keeps only its few strong ones (_jumps_of), the others theirs till
    # then (his way: Fachwerk first, one map, then all of them)
    strong = bool(data.get("strong")) or bool(h) or bool(m)
    jumps = [s for s in jumps if s.get("mine") or s.get("his") or (s.get("why") if strong else s.get("marks") or s.get("hard") or (s.get("kills") or 0) >= 0.15 * max(1, s.get("n") or 0))]
    # one way up, once (22/10, his Dust2 test: two Under A boosts "les mêmes, juste il y a une marche en moins"): the base's
    # from the same start onto the same spot, the one that climbs the most (the maps built before _jumps_of did it)
    one = []
    for j in sorted(jumps, key=lambda c: (not (c.get("mine") or c.get("his")), -(c.get("climb") or 0))):
        if j.get("mine") or j.get("his") or not any(math.dist(j["from"][:2], o["from"][:2]) <= 64 and math.dist(j["to"][:2], o["to"][:2]) <= 96
                                                    for o in one if not (o.get("mine") or o.get("his"))):
            one.append(j)
    jumps = [j for j in jumps if j in one]
    # 19/10, the same video: "je ne veux pas avoir 20 ou 30 momentum à retenir sur la carte": one way per run (the one
    # the base takes most, from a spawn to a site, from a site to the other), and the silent walk-in a T's only (a CT
    # walking to his own site has no one to surprise), one per site
    one = {}
    for w in sorted(routes, key=lambda w: -w["n"]):
        one.setdefault((w["kind"], w["side"], w.get("from"), w["to"]) if strong else w["id"], w)
    routes = list(one.values())
    spawns = [w for w in routes if w["kind"] == "spawn"]
    stops = {}
    for w in spawns:   # one per side: its spawn, open ground to run left and right
        stops.setdefault(w["side"], w)
    silent = [w for w in sorted(spawns, key=lambda w: (w["side"] != "T", -w["n"])) if (w["side"] == "T" or not strong) and _length(w["line"]) >= 300]
    if NO_WAYS:   # 20/10: no way drills any more (timed runs, rotations, silent walk-ins, dead stops)
        routes, stops, silent = [], {}, []
    return {"route": [(w["id"], w) for w in routes], "jump": [(s["id"], s) for s in jumps],
            "stop": [(side, w) for side, w in stops.items()], "silent": [(w["id"], w) for w in silent]}


NO_WAYS = True   # 20/10, the user: "fais disparaître tous les trajets des momentums"


def count(mp):
    """How many momentum exercises the map has (Prepare's focus tile): its jumps."""
    c = _cands(load(mp, build=False) or {}, mp)
    return sum(len(v) for k, v in c.items() if k != "stop")


def has(mp):
    d = load(mp, build=False) or {}
    return bool(d.get("jumps") or his(mp) or mine(mp))


# Prepare's Momentum choice (20/10, the user: "pour la nouvelle version des entraînements Momentum, rework la façon de
# présenter, on n'est plus en fonction du temps"; then "fais disparaître tous les trajets des momentums"): the map's
# jumps, each once
PICKS = {"jumps": ["jump"]}


def offer(sid, mp, guns, rifle):
    """[{key, label, n, items}] of the map: its jumps (none: no choice)."""
    jumps = [d["title"] for d in drills(sid, mp, 0, guns, rifle, pick="jumps") if d["variant"] == "jump"]
    return [{"key": "jumps", "label": i18n.tr("The jumps"), "n": len(jumps), "items": jumps}] if jumps else []


def drills(sid, mp, secs, guns, rifle, items=None, nsess=0, pick=None):
    """The Momentum block: as many drills as its time holds, in the order of the player's level, each variant's in a row
    (Crossfire's way, 14/10); in each variant the ones missed and due first (the training's boxes), then the ones never
    played, the most used first, then the others. guns: (T rifle, CT rifle, pistol) as train._my_guns gives them.
    pick (PICKS): those variants only, each drill once, whatever secs says."""
    from wily.training import replay
    data = load(mp, build=False) or {}
    C = _cands(data, mp)
    if not C["jump"]:
        return []
    items = items or {}
    order = [v for v in VARIANTS.get(crossfire.level_of(sid), VARIANTS[None]) if C[v] and (not pick or PICKS.get(pick) is None or v in PICKS[pick])]
    if not order:
        return []
    tr_, cr_, _ = guns

    def rank(v):
        def r(x):
            it = items.get(_id(mp, v, x[0]))
            n = x[1].get("matches") or x[1].get("n") or 0
            # never played: the hard ones first (solo boosts, then crouched run-up jumps: 16/10, "des jumps très compliqués")
            return (1, -(x[1].get("hard") or 0), -n) if it is None else (0, it["box"], 0) if it["next"] <= nsess else (2, it["next"], 0)
        return sorted(C[v], key=r)
    ranked = {v: rank(v) for v in order}
    seq = [(v, kx) for v in order for kx in ranked[v]]   # every drill once, by priority, before any comes again
    out, total, k = [], 0, 0
    while (k < len(seq)) if pick else (total < secs - 20 and k < max(12, secs // 25)):
        v, (key, x) = seq[k % len(seq)]
        k += 1
        did = _id(mp, v, key)
        box = (items.get(did) or {}).get("box", 0)
        side = x.get("side") or "T"
        team = 2 if side == "T" else 3
        gun = replay._item(tr_ if team == 2 else cr_) or rifle[team]
        pistol = "weapon_glock" if team == 2 else "weapon_usp_silencer"
        d = {"id": did, "kind": "momentum", "mode": "momentum", "variant": v, "map": mp, "team": team, "seconds": SECS[v],
             "count": REPS[v], "level": min(1, box), "armor": 100, "helmet": True}
        if v == "route":
            frm = _spawn_name(side) if x["kind"] == "spawn" else x["from"]
            title = (i18n.tr("RUN · {a} → {b}", a=frm, b=x["to"]) if x["kind"] == "spawn" else i18n.tr("ROTATE · {a} → {b}", a=frm, b=x["to"]))
            tip = (i18n.tr("via {via}", via=" → ".join(x["via"])) + " · " if x["via"] else "") \
                + i18n.tr("knife out, through every ring: the base runs it in {base} s, its fastest in {best} s", base=x["base"], best=x["best"]) \
                + (" · " + i18n.tr("the pros: {pro} s", pro=x["pro"]) if x.get("pro") else "")
            d.update(title=title, tip=tip, weapons=["weapon_knife"], me={"pos": x["start"], "ang": [0, x["yaw"]]},
                     line=x["line"], marks=x["marks"], par=x["base"], best=x["best"], pro=x.get("pro") or 0)
        elif v == "jump" and x.get("mine"):   # yours, saved with !jump: its rings if it is a chain, the blue one
            d.update(title=i18n.tr("YOUR JUMP · {name}", name=x["name"]),
                     tip=(i18n.trn(x["steps"], "{n} jump in a row", "{n} jumps in a row") + " · " if x["steps"] > 1 else "")
                         + i18n.tr("from the green ring, land in the blue one") + " · " + i18n.tr("yours, saved with !jump"),
                     weapons=[gun, "weapon_knife"], me={"pos": x["start"], "ang": [0, x["yaw"]]}, target=x["to"], marks=x["marks"], takeoffs=x.get("takeoffs") or [], runs=x.get("runs") or [], speeds=x.get("speeds") or [],
                     **{"from": x["from"]}, how=x["how"], goal=max(2, JUMP_GOAL - 1))
        elif v == "jump" and x.get("his"):   # his own (20/10): its words, why it is worth it
            nm = _his_name(x["id"]) or x["zone"]
            title = (i18n.tr("SILENT JUMP · {zone}", zone=nm) if x["kind"] == "silent" else i18n.tr("SOLO BOOST · {zone}", zone=nm)
                     if x["kind"] == "boost" else i18n.tr("JUMP · {zone}", zone=nm))
            first = (i18n.tr("walk it (Shift held): not a sound, they don't hear you come") if x["how"] == "walk"
                     else i18n.tr(HOW.get(x["how"], HOW["jump"])))
            d.update(title=title, tip=f"{first} · {_his_why(x['id'])} · " + i18n.tr("from the green ring, land in the blue one"),
                     weapons=[gun, "weapon_knife"], me={"pos": x["start"], "ang": [0, x["yaw"]]}, target=x["to"],
                     **{"from": x["from"]}, how=x["how"], goal=JUMP_GOAL)
        elif v == "jump" and x.get("marks"):   # a solo boost: its steps' rings, then the blue one
            d.update(title=i18n.tr("SOLO BOOST · {zone}", zone=x["zone"]),
                     tip=i18n.trn(x["steps"], "{n} jump in a row", "{n} jumps in a row") + " · " + i18n.tr("land on each ring, the next jump from there, the last one in the blue ring")
                         + " · " + i18n.trn(x["matches"], "the base does it in {n} match", "the base does it in {n} matches"),
                     weapons=[gun, "weapon_knife"], me={"pos": x["start"], "ang": [0, x["yaw"]]}, target=x["to"], marks=x["marks"], takeoffs=x.get("takeoffs") or [], runs=x.get("runs") or [], speeds=x.get("speeds") or [],
                     **{"from": x["from"]}, how=x["how"], goal=max(2, JUMP_GOAL - 1))
        elif v == "jump" and x.get("why") == "silent":   # walked, nobody hears it: the walk is the drill
            d.update(title=i18n.tr("SILENT JUMP · {zone}", zone=x["zone"]),
                     tip=i18n.tr("walk it (Shift held): not a sound, they don't hear you come · most players jump it running")
                         + " · " + i18n.tr("from the green ring, land in the blue one"),
                     weapons=[gun, "weapon_knife"], me={"pos": x["start"], "ang": [0, x["yaw"]]}, target=x["to"],
                     **{"from": x["from"]}, how="walk", goal=JUMP_GOAL)
        elif v == "jump":
            how = i18n.tr(HOW.get(x["how"], HOW["jump"]))
            d.update(title=i18n.tr("JUMP · {zone}", zone=x["zone"]),
                     tip=f"{how} · " + i18n.tr("from the green ring, land in the blue one") + " · "
                         + (i18n.tr("doable walking (Shift): not a sound") + " · " if (x.get("slow") or 0) >= 0.4 else "")
                         + i18n.trn(x["matches"], "the base jumps it in {n} match", "the base jumps it in {n} matches")
                         + (" · " + i18n.trn(x["kills"], "{n} kill from up there", "{n} kills from up there") if x.get("kills") else ""),
                     weapons=[gun, "weapon_knife"], me={"pos": x["start"], "ang": [0, x["yaw"]]}, target=x["to"],
                     **{"from": x["from"]}, how=x["how"], goal=JUMP_GOAL)
        elif v == "stop":
            d.update(title=i18n.tr("STOP DEAD · {zone}", zone=_spawn_name(side)),
                     tip=i18n.tr("run left and right (A, D) at full speed; on STOP, stop dead: tap the other key (counter-strafe)"),
                     weapons=["weapon_knife", pistol, gun], me={"pos": x["start"], "ang": [0, x["yaw"]]})
        else:
            s = _silent(x)
            if s is None:
                continue
            limit = round(s["len"] / WALK + 3, 1)
            d.update(title=i18n.tr("SILENT · into {site}", site=x["to"]),
                     tip=i18n.tr("walk in (Shift), not one footstep heard: {s} s at most", s=limit),
                     weapons=["weapon_knife", pistol, gun], me={"pos": s["start"], "ang": [0, s["yaw"]]},
                     line=s["line"], marks=marks(s["line"]), par=limit)
        out.append(d)
        total += SECS[v]
    out.sort(key=lambda d: order.index(d["variant"]))
    return out


if __name__ == "__main__":
    # python -m wily.training.momentum [map ...]: the maps' data built again (every bomb map of the base by default)
    sys.stdout.reconfigure(encoding="utf-8")
    from wily.training import train
    config.low_priority()
    only = "--jumps-only" in sys.argv
    for m in [a for a in sys.argv[1:] if not a.startswith("--")] or list(train.base_maps()):
        _build(m, jumps_only=only)
