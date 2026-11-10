"""A site's takes and defenses from real throws, under his rules (22/10, his test video: "un stuff qui part d'un spot qui
est dans un coin, qui n'a pas une vision directe sur la personne ciblée, qui atterrit à un endroit clé", "va voir les
stuffs de pro ... les stuffs partent en général d'un peu plus loin ... ils sont plus safe", "des stuff de défense c'est
des stuff qui doit être envoyé depuis le bombsite", "le coéquipier visible de tous les ennemis, c'est pas du tout une
exec"; the first Dust2 had none of it: corners found from where players stood, nothing about who sees the thrower).

For each place a take or a defense needs (tools/defense_build.py's CONF, its places from the base):
- the throws of the pro and LAN base (out/deep_pro) and of the players' base that land on it, by the spot they leave from
  (the pros' first);
- only from the right side: a defense from its site, a take from outside it;
- only a spot the base's duels never link to the place it lands on or, for a take, to the site's defenders (out of their
  sight: "il ne doit pas pouvoir me décaler en moins de 2 secondes");
- only a spot the game itself locks you into (tools/spot_probe.py: a bot pushed 16 ways is stopped on an arc of 5 to
  12 of them; never all 16: inside a wall);
- thrown on the server from that spot with the base's own aim and way, kept when it lands there.

    python tools/stuff_build.py <map> [CT:A,CT:B,T:A,T:B]

out/selftest/lineup_finder_<map>_<role>_v2.json, read by tools/defense_build.py (its CONF names the _v2 files)."""
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from wily.core import config  # noqa: E402
from wily.training import navmesh, replay, train  # noqa: E402
import lineup_finder as LF  # noqa: E402
import spot_probe as SP  # noqa: E402

TOL = {"smoke": 110.0, "molotov": 130.0, "he": 160.0, "flash": 220.0}
SITE_R = 750.0      # a defense's spot: on its site (the site's middle this near)
OUT_R = 650.0       # a take's spot: outside the site
EXPO = 0.02         # duels per match of the base between the spot and the place (or the site's defenders): out of sight
PROBE_N = int(os.environ.get("PROBE_N", 16))   # spots probed per place, the best first (a probe is a second at 4x)
WAYS = ("still", "jump", "W", "WJ")
CLICKS = ("left", "both", "right")
PLAN_F = os.path.join(config.HERE, "resources", "stuff_plan.json")
# places he approved, tried first (type, place, the base's moment)
SEARCH = 2   # how a corner's throw is searched (2, 22/10: its pitch scanned whole): a role searched another way is made again
# roles kept as found today whatever their search (--keep PTA_smoke1,PTA_smoke2: lineups already played in his own game,
# 22/10: Dust2's exec A smokes, "parfait" from the real client)
KEEP = set(sys.argv[sys.argv.index("--keep") + 1].split(",")) if "--keep" in sys.argv else set()
MUST = {"de_dust2|T:B": [("smoke", [-1304.8, 2660.2, 129.9], 11.0), ("smoke", [-1232.3, 2295.3, 7.2], 14.4)],   # each take's and defense's places, the pros' way
        # Dust2's A from Long: the cross's smoke Under A and Short's (22/10, both played in his game; the user on Short's: "la
        # smoke arrive pour couvrir les premières lignes short, donc potentiellement les lignes d'AWP, et aider tes teammates
        # terroristes short")
        "de_dust2|T:A": [("smoke", [1140.1, 2157.8, 3.7], 20.3), ("smoke", [513.6, 2153.6, 98.1], 31.1)]}
HOW_WORDS = {"still": "standing still", "jump": "jumpthrow", "W": "run-throw (moving forward)", "WJ": "forward + jumpthrow"}
# the ways a corner's throw is searched, by kind: a flash may be run-thrown too, its run starting in the corner (23/10, the
# user: "si les flashs sont des runthrow et que le début de la course d'élan est depuis un angle, tu peux prendre en compte
# les runthrow"; Dust2's Long flashes were all run-throws from the open ground)
CORNER_WAYS = {"flash": ("still", "jump", "W", "WJ")}


def run_back(pos, yaw, ks=(32, 64, 96, 128)):
    """Where a run-throw's run starts: back along its aim from where it is let go (the base's spot is the release, in the
    open; its run can start in a corner behind it)."""
    yr = math.radians(yaw)
    return [[round(pos[0] - k * math.cos(yr), 1), round(pos[1] - k * math.sin(yr), 1), pos[2]] for k in ks]


def throws(mp):
    """The map's throws: the pro and LAN base's (src pro) and the players' base's (src base). Cached per map."""
    f = os.path.join(config.OUT, "selftest", f"throws_{mp}.parquet")
    srcs = [os.path.join(config.OUT, "pro", "matches.json"), os.path.join(config.OUT, "population", "nades.parquet")]
    # made again when the pro base or the players' base changed since (22/10: Settings' "Add demos" adds pro maps)
    if os.path.exists(f) and all(not os.path.exists(x) or os.path.getmtime(x) <= os.path.getmtime(f) for x in srcs):
        return pd.read_parquet(f)
    cols = ["type", "side", "X", "Y", "Z", "pitch", "yaw", "jump", "speed", "crouch", "walk", "click", "land_X", "land_Y", "land_Z",
            "t", "enemies_blind", "damage"]
    parts = []
    P = os.path.join(config.OUT, "deep_pro")
    for d in sorted(os.listdir(P)) if os.path.isdir(P) else []:
        try:
            if (json.load(open(os.path.join(P, d, "meta.json"), encoding="utf-8")) or {}).get("map") != mp:
                continue
            G = pd.read_parquet(os.path.join(P, d, "grenades.parquet"), columns=cols)
        except Exception:
            continue
        G["src"], G["match"] = "pro", d
        parts.append(G)
    try:
        N = pd.read_parquet(os.path.join(config.OUT, "population", "nades.parquet"), columns=["map", "match"] + cols,
                            filters=[("map", "==", mp)])
        N = N.drop(columns=["map"])
        N["src"] = "base"
        N["match"] = N["match"].astype(str)
        parts.append(N)
    except Exception as e:
        print("players' base:", e, flush=True)
    T = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols + ["src", "match"])
    T = T.dropna(subset=["X", "Y", "Z", "land_X", "land_Y", "pitch", "yaw"])
    T.to_parquet(f)
    return T


def _way(r):
    """The base's way of a throw, in css_dbgthrow's words."""
    run = (r.get("speed") or 0) >= 60 and not r.get("walk")
    j = bool(r.get("jump"))
    return ("WJ" if run else "jump") if j else ("W" if run else "still")


def _click(r):
    c = str(r.get("click") or "").lower()
    return "both" if ("both" in c or "middle" in c) else "right" if "right" in c else "left"


def nade_start(pos, pitch, yaw, how, click, crouch=False):
    """The grenade's start and speed as the plugin throws these words (SelfTest.cs css_dbgthrow)."""
    speed, dz = LF.CLICK[click]
    el, yr = math.radians(10 - pitch * 80 / 90), math.radians(yaw)
    fw = np.array([math.cos(el) * math.cos(yr), math.cos(el) * math.sin(yr), math.sin(el)])
    flat = np.array([math.cos(yr), math.sin(yr), 0.0])
    add = (np.array([0.0, 0.0, 265.0]) if how in ("jump", "WJ") else 0.0) + (flat * 190.0 if how in ("W", "WJ") else 0.0)
    src = np.array([pos[0], pos[1], pos[2] + (46.0 if crouch else 64.0)]) + fw * 16 + np.array([0.0, 0.0, dz])
    return src, fw * speed + add


def candidates(mp, side, typ, target, site_c, takes_holds=None):
    """The spots its throws leave from, the pros' first: [{pos, pitch, yaw, how, click, n, pro, expo, src}]."""
    T = throws(mp)
    tol = TOL[typ]
    m = ((T["type"] == typ) & (T["side"] == side) & (np.hypot(T.land_X - target[0], T.land_Y - target[1]) <= tol)
         & (np.abs(T.land_Z - target[2]) <= (200 if typ == "flash" else 96)))
    G = T[m].copy()
    if not len(G):
        return []
    G["cx"], G["cy"], G["cz"] = (G.X // 16).astype(int), (G.Y // 16).astype(int), (G.Z // 32).astype(int)
    n_matches = max(1, len(train._map_dirs(mp)))
    out = []
    for (cx, cy, cz), g in G.groupby(["cx", "cy", "cz"]):
        if len(g) < 2 and not (g.src == "pro").any():
            continue   # one player's once: not a lineup
        # its most common aim (a spot can have two lineups onto the same place)
        g = g.assign(ap=(g.pitch / 2).round(), ay=((g.yaw % 360) / 2).round())
        k = g.groupby(["ap", "ay"]).size().idxmax()
        a = g[(g.ap == k[0]) & (g.ay == k[1])]
        pos = [float(a.X.median()), float(a.Y.median()), float(a.Z.median())]
        d_site = math.hypot(pos[0] - site_c[0], pos[1] - site_c[1])
        if side == "CT" and d_site > SITE_R:
            continue
        if side == "T" and d_site < OUT_R:
            continue
        expo = train._exposed(mp, pos, target, 150, 120) / n_matches
        if expo > EXPO:
            continue
        if side == "T" and takes_holds:   # the teammate out of the site's defenders' sight
            hold = sum(train._exposed(mp, pos, h, 150, 120) for h in takes_holds) / n_matches
            if hold > EXPO:
                continue
        r = a.iloc[len(a) // 2].to_dict()
        out.append({"pos": [round(v, 1) for v in pos], "pitch": round(float(a.pitch.median()), 2),
                    "yaw": round(float(np.degrees(np.arctan2(np.sin(np.radians(a.yaw)).mean(), np.cos(np.radians(a.yaw)).mean()))), 2),
                    "how": _way(r), "click": _click(r), "crouch": bool(r.get("crouch")), "n": int(len(g)), "pro": int((g.src == "pro").sum()),
                    "expo": round(expo, 4), "t_med": round(float(g.t.median()), 1) if "t" in g else None,
                    "land": [round(float(a.land_X.median()), 1), round(float(a.land_Y.median()), 1), round(float(a.land_Z.median()), 1)]})
    out.sort(key=lambda c: -(3 * c["pro"] + c["n"]))
    return out


def verify(typ, c, target):
    """Thrown from its spot with the base's aim: its own way first, then the others; the nearest miss corrected from
    where it popped (a long lineup a few units off its spot lands a little off), then its aim swept.
    -> (c with how/click/pitch/yaw as thrown, the pop, off) or None."""
    tol = TOL[typ]
    order = [(c["how"], c["click"])] + [(h, k) for h in WAYS for k in CLICKS if (h, k) != (c["how"], c["click"])]
    best = None
    for how, click in order[:6]:
        t = dict(c, how=how, click=click)
        replay.keep()
        r = LF.throw(typ, t)
        ok, off = LF.judge(typ, r, target, tol)
        if ok:
            return t, r, off
        if off is not None and abs(r[2] - target[2]) <= 96 and (best is None or off < best[2]):
            best = (t, r, off)
    if best and best[2] <= 600:
        t, r, off = best
        for _ in range(3):   # its aim corrected from where it popped
            p = np.asarray(t["pos"][:2], float)
            want, got = math.atan2(target[1] - p[1], target[0] - p[0]), math.atan2(r[1] - p[1], r[0] - p[0])
            t = dict(t, yaw=round(t["yaw"] + math.degrees((want - got + math.pi) % (2 * math.pi) - math.pi), 2),
                     pitch=round(max(-89.0, min(89.0, t["pitch"] - (math.dist(p, target[:2]) - math.dist(p, r[:2])) / 40)), 2))
            replay.keep()
            r2 = LF.throw(typ, t)
            ok2, off2 = LF.judge(typ, r2, target, tol)
            if ok2:
                return t, r2, off2
            if off2 is None or off2 >= off:
                break
            r, off = r2, off2
    sw = LF.sweep(typ, c, target, tol)
    if sw and sw[2]:
        return sw[0], sw[1], sw[3]
    for how in (c["how"], "still"):   # its pitch scanned whole, its own way, then still
        got = scan(typ, c["pos"], target, how, c["click"] if how == c["how"] else "left", tol)
        if got and got[2]:
            return dict(c, **{k: got[0][k] for k in ("how", "click", "pitch", "yaw")}), got[1], got[3]
        if how == "still":
            break
    return None


def _correct(typ, c, r, target, tol):
    """Its aim corrected from where it popped, 3 times at most (tools/lineup_finder.py's own loop): -> (c, r, ok, off)."""
    ok, off = LF.judge(typ, r, target, tol)
    pos = c["pos"]
    for _ in range(3):
        if ok or off is None or off > 600 or abs(r[2] - target[2]) > 96:
            break
        p = np.asarray(pos[:2], float)
        want, got = math.atan2(target[1] - p[1], target[0] - p[0]), math.atan2(r[1] - p[1], r[0] - p[0])
        c2 = dict(c, yaw=round(c["yaw"] + math.degrees((want - got + math.pi) % (2 * math.pi) - math.pi), 2),
                  pitch=round(max(-89.0, min(89.0, c["pitch"] - (math.dist(p, target[:2]) - math.dist(p, r[:2])) / 40)), 2))
        replay.keep()
        r2 = LF.throw(typ, c2)
        ok2, off2 = LF.judge(typ, r2, target, tol)
        if off2 is None or off2 >= off:
            break
        c, r, ok, off = c2, r2, ok2, off2
    return c, r, ok, off


def scan(typ, pos, target, how, click, tol):
    """Its pitch swept 4 degrees at a time from a lob to a flat throw, at the place (22/10, Fachwerk's B molotov: the
    model's aims all went over the roof its place is under, popped up there, and the search stopped there; this
    morning's 11 u lineup was not found again): the nearest landing on its floor, then corrected. -> (c, r, ok, off)."""
    yaw = round(math.degrees(math.atan2(target[1] - pos[1], target[0] - pos[0])), 2)
    best = None

    def one(pitch):
        nonlocal best
        c = {"pos": pos, "how": how, "click": click, "pitch": round(float(pitch), 2), "yaw": yaw}
        replay.keep()
        r = LF.throw(typ, c)
        ok, off = LF.judge(typ, r, target, tol)
        if ok or (off is not None and abs(r[2] - target[2]) <= 96 and (best is None or off < best[3])):
            best = (c, r, ok, off)
        return ok
    # a throw every 8 to 10 degrees (a second each at 4x: a corner's whole scan in 10 to 15 s), then around the best
    for pitch in (-50, -40, -30, -21, -13, -6, 0, 8, 16):
        if one(pitch):
            return best
    if best and best[3] <= 600:
        p0 = best[0]["pitch"]
        for dp in (-3, 3):
            if one(p0 + dp):
                return best
        return _correct(typ, best[0], best[1], target, tol)
    return best


def land_from(typ, pos, target, tol):
    """From a corner, the aim that lands it on the place: the model's aims for each way (the natural ones first), each
    thrown on the server and corrected from where it popped; none of them: its pitch scanned whole (a still throw, then
    a jumpthrow, left click). -> (c, pop, off) or None."""
    for how in CORNER_WAYS.get(typ, ("still", "jump")):
        for click in ("left", "both", "right"):
            for pitch, yaw, e in LF.aims(typ, pos, target, how, click):
                if e > 120:
                    continue
                c = {"pos": pos, "how": how, "click": click, "pitch": round(pitch, 2), "yaw": round(yaw, 2)}
                replay.keep()
                r = LF.throw(typ, c)
                c, r, ok, off = _correct(typ, c, r, target, tol)
                if ok:
                    return c, r, off
    for how in ("still", "jump"):   # a jumpthrow scanned only when no still throw came near it on its floor
        got = scan(typ, pos, target, how, "left", tol)
        if got and got[2]:
            return got[0], got[1], got[3]
        if got and got[3] is not None and got[3] <= 2 * tol:
            break
    return None


def corners_around(mp, side, typ, target, site_c, holds, cs, r=200.0, n=12):
    """The mesh's corners around where the base throws it from (its spots in the open: the pros line it up on landmarks,
    not from a corner), on their floor, on its side, out of sight: [pos], the nearest the pros' spots first."""
    n_matches = max(1, len(train._map_dirs(mp)))
    out = []
    for c in cs[:8]:
        for q in navmesh.corner_points(mp, c["pos"], r=r, dz=24.0):
            q = [float(x) for x in q]
            if any(math.dist(q[:2], o[:2]) < 24 for o in out):
                continue
            d_site = math.hypot(q[0] - site_c[0], q[1] - site_c[1])
            if (side == "CT" and d_site > SITE_R) or (side == "T" and d_site < OUT_R):
                continue
            if train._exposed(mp, q, target, 150, 120) / n_matches > EXPO:
                continue
            if side == "T" and holds and sum(train._exposed(mp, q, h, 150, 120) for h in holds) / n_matches > EXPO:
                continue
            out.append(q)
    return out[:n]


RANGE = {"smoke": 1300.0, "molotov": 900.0, "he": 1000.0, "flash": 1100.0}   # a still or jump throw's reach, roughly


def site_corners(mp, side, typ, target, site_c, n=5):
    """A defense's corners on its own site in the grenade's reach of the place, the nearest it first, out of its sight
    (22/10, Dust2's B: the tunnel's exit molotov thrown from the back of the site, a corner there)."""
    n_matches = max(1, len(train._map_dirs(mp)))
    out = []
    for q in navmesh.corner_points(mp, site_c, r=SITE_R, dz=160.0):
        q = [float(x) for x in q]
        d = math.hypot(q[0] - target[0], q[1] - target[1])
        if d > RANGE[typ] or d < 250:
            continue
        if train._exposed(mp, q, target, 150, 120) / n_matches > EXPO:
            continue
        out.append((d, q))
    out.sort()
    return [q for _, q in out[:n]]


def _probe(q):
    """A spot's 16 ways (spot_probe), probed again when it is just short of a corner (3 or 4 ways blocked in a row: the
    bot's pushes land a way either side, 22/10: Fachwerk's B smoke corner 6 ways then 4): the best of three. -> v or None."""
    best = None
    for _ in range(3):
        v = SP.probe(q)
        if v is None:
            continue
        a, nb = SP.arc(v)
        if best is None or (nb < 15 and a > SP.arc(best)[0]):
            best = v
        if not 3 <= a <= 4 or nb >= 15:
            break
    return best


def build_role(mp, side, site, role, typ, target, site_c, holds):
    cs = candidates(mp, side, typ, target, site_c, holds)
    print(f"{mp} {side}:{site} {role} ({typ}): {len(cs)} spots from the base's throws there on its side, out of sight", flush=True)
    found = []
    for c in cs[:PROBE_N]:
        spot, why = None, ""
        # its own spot, else a corner a few units off it (a pro against a wall next to a corner: the same throw): the
        # mesh's corners near it, and along its wall both ways (the wall the probe found it against)
        todo, tried = [c["pos"]] + navmesh.corner_points(mp, c["pos"], dz=24.0)[:3], 0
        if typ == "flash" and c["how"] in ("W", "WJ"):   # a run-throw: its run started in a corner behind it, maybe
            for q in run_back(c["pos"], c["yaw"]):
                todo += navmesh.corner_points(mp, q, r=48.0, dz=24.0)[:1]
        while todo and tried < (13 if typ == "flash" and c["how"] in ("W", "WJ") else 9):
            q = todo.pop(0)
            tried += 1
            v = _probe(q)
            if v is None:
                continue
            a, nb = SP.arc(v)
            book = config.read_json(SP.BOOK, {}) or {}
            book[SP.key(mp, q)] = {"d": v, "checked": time.strftime("%Y-%m-%d")}
            config.write_json(SP.BOOK, book)
            if nb < 15 and 5 <= a <= 12:
                spot = q
                break
            why = why or f"{'inside a wall' if nb >= 15 else 'no corner'} (arc {a}, {nb} blocked)"
            if tried == 1 and 1 <= nb <= 6:   # against one wall: its corner is along it
                ang = [i * 22.5 for i, x in enumerate(v) if x < SP.BLOCK]
                nx = sum(math.cos(math.radians(t)) for t in ang)
                ny = sum(math.sin(math.radians(t)) for t in ang)
                tx, ty = -ny, nx
                L = math.hypot(tx, ty) or 1.0
                for k in (16, 32, 48):
                    for sgn in (1, -1):
                        todo.append([round(q[0] + sgn * k * tx / L, 1), round(q[1] + sgn * k * ty / L, 1), q[2]])
        if not spot:
            print(f"  {c['pos']} ({c['pro']} pro, {c['n']} throws): {why or 'no probe answer'}, no corner near it either", flush=True)
            continue
        moved = round(math.dist(spot[:2], c["pos"][:2]), 1)
        c = dict(c, pos=spot, moved=moved)
        got = verify(typ, c, target)
        if not got:
            print(f"  {c['pos']} corner (arc {a}): its throw never lands there", flush=True)
            continue
        t, r, off = got
        src, vel = nade_start(t["pos"], t["pitch"], t["yaw"], t["how"], t["click"], t.get("crouch"))
        found.append(dict(t, pop=[round(x, 1) for x in r[:3]], off=round(off), bounces=r[3], arc=a, blocked=nb,
                          how_words=HOW_WORDS[t["how"]] + (" + crouching" if t.get("crouch") else ""), click_words=LF.CLICK_WORDS[t["click"]],
                          nade_at=[round(float(x), 1) for x in src], nade_v=[round(float(x), 1) for x in vel]))
        print(f"  KEPT {t['pos']} ({c['pro']} pro, {c['n']} throws, seen {c['expo']}/match, {c.get('moved', 0)} u off its spot): corner arc {a}, "
              f"{HOW_WORDS[t['how']]} {LF.CLICK_WORDS[t['click']]} -> {round(off)} u off", flush=True)
        if len(found) >= 3:
            break
    if not found:   # no pro spot is a corner: the corners around them, then (a defense) its site's own corners in reach
        extra = site_corners(mp, side, typ, target, site_c) if side == "CT" else []
        for q in corners_around(mp, side, typ, target, site_c, holds, cs) + extra:
            v = _probe(q)
            if v is None:
                continue
            book = config.read_json(SP.BOOK, {}) or {}
            book[SP.key(mp, q)] = {"d": v, "checked": time.strftime("%Y-%m-%d")}
            config.write_json(SP.BOOK, book)
            a, nb = SP.arc(v)
            if nb >= 15 or a < 5 or a > 12:
                continue
            got = land_from(typ, q, target, TOL[typ])
            if not got:
                print(f"  corner {[round(x) for x in q]} (arc {a}): nothing lands there from it", flush=True)
                continue
            t, r, off = got
            src, vel = nade_start(t["pos"], t["pitch"], t["yaw"], t["how"], t["click"])
            found.append(dict(t, pop=[round(x, 1) for x in r[:3]], off=round(off), bounces=r[3], arc=a, blocked=nb, n=0, pro=0, corner_only=True,
                              how_words=HOW_WORDS[t["how"]], click_words=LF.CLICK_WORDS[t["click"]],
                              nade_at=[round(float(x), 1) for x in src], nade_v=[round(float(x), 1) for x in vel]))
            print(f"  KEPT corner {[round(x) for x in q]} (arc {a}) near the pros' spots: {HOW_WORDS[t['how']]} {LF.CLICK_WORDS[t['click']]} -> {round(off)} u off", flush=True)
            if len(found) >= 2:
                break
    found.sort(key=lambda x: (x["how"] != "still", -x.get("pro", 0), x["off"]))
    f = os.path.join(config.OUT, "selftest", f"lineup_finder_{mp}_{role}_v2.json")
    config.write_json(f, {"map": mp, "type": typ, "target": target, "near": [], "found": found, "built": time.strftime("%Y-%m-%d"),
                          "search": SEARCH, "rules": "22/10: corner, side, out of sight, real throws"})
    return found


def places(mp, side, site):
    """A take's or a defense's places the pros' way (22/10: the first Dust2 had places nobody throws safely): where the pro
    and LAN base (then the players' base) throws in the round's first 45 s, a take's from outside its site onto it, a
    defense's from its site onto the Ts' ways, the most thrown first (a pro's throw counting 3), a take's smoke never on
    its own entry. -> [(type, target, t_med, pro throws, all throws)], the ones a safe spot throws (candidates)."""
    T = throws(mp)
    S = train.site_data(mp).get("sites") or {}
    c = (S.get(f"Bombsite{site}") or {}).get("center")
    if not c:
        return []
    P = T[(T.side == side) & (T.t <= 45)]
    # 23/10, Nuke: its B 352 u under A and 228 u beside it; a throw by or onto the other site's floor is the other's
    o = (S.get(f"Bombsite{'B' if site == 'A' else 'A'}") or {}).get("center")
    if o and len(c) > 2 and len(o) > 2 and abs(c[2] - o[2]) > 200:
        def other(x, y, z):
            return (np.hypot(x - o[0], y - o[1]) < 900) & (np.abs(z - o[2]) < np.abs(z - c[2]))
        P = P[~other(P.land_X, P.land_Y, P.land_Z) & ~other(P.X, P.Y, P.Z)]
    dl = np.hypot(P.land_X - c[0], P.land_Y - c[1])
    dp = np.hypot(P.X - c[0], P.Y - c[1])
    L = P[(dl <= 900) & (dp >= OUT_R)] if side == "T" else P[(dp <= SITE_R) & (dl >= 300) & (dl <= 1500)]
    if not len(L):
        return []
    L = L.assign(lx=(L.land_X // 150).astype(int), ly=(L.land_Y // 150).astype(int), w=np.where(L.src == "pro", 3, 1))
    holds = [h["pos"] for h in train.take_spots(mp, site)[:8]] if side == "T" else None
    import defense_build as DB
    see = ((DB.CONF.get(mp) or {}).get(side) or {}).get(site, {}).get("see") if side == "T" else None
    out = []
    # the places he approved first (22/10, his test video on Dust2's B: "comme le stuff porte et le stuff window B,
    # l'endroit où ils tombent c'est bien parce que c'est des endroits clés")
    for typ, land, t_med in MUST.get(f"{mp}|{side}:{site}", []):
        if candidates(mp, side, typ, land, c, holds):
            out.append((typ, land, t_med, 0, 0))
    for (typ, lx, ly), w in L.groupby(["type", "lx", "ly"]).w.sum().sort_values(ascending=False).items():
        g = L[(L.type == typ) & (L.lx == lx) & (L.ly == ly)]
        if len(g) < 8:
            continue
        # its landing: the most common floor of the cell (a cell can hold a doorway and the roof over it)
        g = g.assign(fz=(g.land_Z // 48).astype(int))
        g = g[g.fz == g.fz.mode().iloc[0]]
        land = [round(float(g.land_X.median()), 1), round(float(g.land_Y.median()), 1), round(float(g.land_Z.median()), 1)]
        if typ != "flash" and navmesh.on_mesh(mp, land, dz=40) is False:
            continue   # on a roof or a ledge nobody walks: it does nothing (Dust2's B Doors: a smoke 218 u up on its roof)
        if see and typ == "smoke" and math.dist(see[:2], land[:2]) < 350:
            continue   # a take's smoke on its own entry: you come out blind (Dust2's B: one on the tunnel's exit)
        if see and math.dist(land[:2], c[:2]) > math.dist(see[:2], c[:2]):
            continue   # a take's grenade behind its own entry (Dust2's B: an HE, a flash in its own tunnel): the CTs' side only
        if any(o[0] == typ and math.dist(o[1][:2], land[:2]) < 300 for o in out):
            continue
        if not candidates(mp, side, typ, land, c, holds):
            continue
        out.append((typ, land, round(float(g.t.median()), 1), int((g.src == "pro").sum()), int(len(g))))
        if len(out) >= 16:
            break
    return out


def _los(rows, timeout=3.0):
    """Bullet lines traced by the plugin on the server (css_dbglosfile, its brushes only): [[x1, y1, z1, x2, y2, z2], ...]
    -> [True when clear, ...], or None when it did not answer."""
    fin, fout = os.path.join(replay.COACH, "los_in.json"), os.path.join(replay.COACH, "los_out.json")
    try:
        with open(fin, "w", encoding="utf-8") as fh:
            json.dump(rows, fh)
        t_ask = time.time()
        replay.rcon("css_dbglosfile", wait=0.02)
        while time.time() - t_ask < timeout:
            time.sleep(0.05)
            if os.path.exists(fout) and os.path.getmtime(fout) >= t_ask - 0.05:
                res = json.load(open(fout, encoding="utf-8"))
                if len(res) == len(rows):
                    return [f > 0.98 for f in res]
    except Exception:
        return None
    return None


def thrower_seen(x):
    """An HE's or a molotov's victims see its thrower (30/10, his review on Dust2's A HE: "les personnes qui subissent la HE
    peuvent me voir en vue directe quand je l'envoie, donc je peux mourir"): a line clear from his eyes on the spot to a
    player's eyes where it pops or 60 u around it. None: the server did not answer (the base's duels judge alone)."""
    e = [x["pos"][0], x["pos"][1], x["pos"][2] + 64]
    p = x["pop"]
    rows = [e + [p[0] + dx, p[1] + dy, p[2] + 60] for dx, dy in ((0, 0), (60, 0), (-60, 0), (0, 60), (0, -60))]
    res = _los(rows)
    return None if res is None else any(res)


def flash_landmark(x, reach=1500.0):
    """A flash aimed at something to find again (30/10, his review on Inferno's B flash: "il n'y a aucun repère visuel ... je
    pourrais pas la refaire en match"): its aim from his eyes meets the map within 1,500 u, a wall's or a roof's edge, not
    the open sky. None: the server did not answer."""
    e = [x["pos"][0], x["pos"][1], x["pos"][2] + (46 if x.get("crouch") else 64)]
    p, y = math.radians(x["pitch"]), math.radians(x["yaw"])
    d = [math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), -math.sin(p)]
    res = _los([e + [e[i] + d[i] * reach for i in range(3)]])
    return None if res is None else not res[0]


def _puts_out(r, keep):
    """A smoke on its own stack's molotov puts the fire out, a flash in its own smoke blinds nobody (CS2): never within
    220 u (a molotov) or 200 u (a flash) of one of its own smokes, up and down counted as defense_build.pick counts them
    (22/10, Fachwerk's B: Heaven's smoke 160 u over T Main's flash is not around it)."""
    clash = {"smoke": {"molotov": 220, "flash": 200}, "molotov": {"smoke": 220}, "flash": {"smoke": 200}}.get(r[0], {})
    return any(k[0] in clash and math.dist(k[1][:3], r[1][:3]) < clash[k[0]] for k in keep)


def plan(mp, side, site, n_max=4):
    """The places tried, in order: [(role, type, target, t_med, pro throws)] (the first of each kind kept by main when its
    lineup is found: at most 2 smokes and one of each other kind, all within 12 s of each other in the base: thrown
    together, 22/10: "la flash est quand même un peu plus lente que la molo et la HE")."""
    rows = places(mp, side, site)
    if side == "CT":   # a defense: one way in held by a stack thrown together (its fullest, then the others as spares)
        from wily.training import setups
        by = {}
        for r in rows:
            by.setdefault(setups.zone_at(mp, r[1]) or "?", []).append(r)
        def greedy(rs):
            kinds, keep = {}, []
            for r in rs:
                if kinds.get(r[0], 0) >= (2 if r[0] == "smoke" else 1) or (keep and abs(r[2] - keep[0][2]) > 10):
                    continue
                if _puts_out(r, keep):
                    continue
                kinds[r[0]] = kinds.get(r[0], 0) + 1
                keep.append(r)
            return keep[:4]

        def stack(rs):   # the fullest stack (a molotov and an HE and a flash beat a smoke alone), then the most thrown
            best = []
            for i in range(len(rs)):
                k = greedy([rs[i]] + rs[:i] + rs[i + 1:])
                if (len(k), sum(r[3] for r in k)) > (len(best), sum(r[3] for r in best)):
                    best = k
            return best
        zones = sorted(by, key=lambda z: -(1000 * min(4, len(stack(by[z]))) + sum(r[3] for r in stack(by[z]))))
        rows = [r for z in zones for r in stack(by[z]) + [x for x in by[z] if x not in stack(by[z])]]
    out, k = [], {}
    for typ, land, t_med, pro, n in rows:
        k[typ] = k.get(typ, 0) + 1
        out.append((f"P{side}{site}_{typ}{k[typ]}", typ, land, t_med, pro))
    return out


def roles(mp, side, site):
    """Its places as tools/defense_build.py's CONF has them: (role, type, target)."""
    import defense_build as DB
    out = []
    for r, _, _ in DB.CONF[mp][side][site]["roles"]:
        for name in r.split("|"):
            name = name.replace("_v2", "")
            R = config.read_json(os.path.join(config.OUT, "selftest", f"lineup_finder_{mp}_{name}.json"), {}) or {}
            if R.get("target"):
                out.append((name, R["type"], R["target"]))
    return out


def main():
    mp = sys.argv[1]
    keys = sys.argv[2].split(",") if len(sys.argv) > 2 else ["CT:A", "CT:B", "T:A", "T:B"]
    replay.start(mp)
    replay.keep()
    replay.rcon("sv_hibernate_when_empty 0")
    fast()
    try:
        _main(mp, keys)
    finally:
        replay.rcon("host_timescale 1")
        replay.rcon("sv_cheats 0")


def fast():
    """The server's clock 4 times as fast (nobody on it: the probes and the throws are the game's own physics, faster)."""
    replay.rcon("sv_cheats 1")
    replay.rcon("host_timescale 4")


def _main(mp, keys):
    S = train.site_data(mp).get("sites") or {}
    import defense_build as DB
    for key in keys:
        side, site = key.split(":")
        c = (S.get(f"Bombsite{site}") or {}).get("center")
        if not c:
            continue
        if site not in ((DB.CONF.get(mp) or {}).get(side) or {}):   # no clock or no way in read from the base (tools/site_conf.py)
            print(f"{mp} {key}: no site config, not searched", flush=True)
            continue
        holds = [h["pos"] for h in train.take_spots(mp, site)[:8]] if side == "T" else None
        rows = plan(mp, side, site)
        if len(rows) < 3:   # too few throws in the base for 3 places (Fachwerk: 28 matches): its places as defense_build has them
            # too, after the base's own (22/10: Fachwerk's A, its Outside Long places out of a site corner's reach, the
            # base's molotov and flash by the site within it)
            import defense_build as DB
            t_of = {n: t for r, _, t in DB.CONF[mp][side][site]["roles"] for n in r.split("|")}
            rows = rows + [(f"{name}W", typ, target, t_of.get(name, 0.0), 0) for name, typ, target in roles(mp, side, site)]
        print(f"{mp} {key}: {len(rows)} places to try: {', '.join(f'{r[0]} {r[3]} s ({r[4]} pro)' for r in rows)}", flush=True)
        kept, kinds = [], {}
        from wily.training import setups
        for i, (role, typ, target, t_med, n) in enumerate(rows):
            if len(kept) >= 4 or kinds.get(typ, 0) >= (2 if typ == "smoke" else 1):
                continue
            # a defense: one smoke a way in at most (30/10, his review on Inferno's B: two smokes on Banana, "s'ils crossent la
            # première smoke, ils crossent la deuxième. Et s'ils crossent pas la première, la deuxième est inutile")
            if side == "CT" and typ == "smoke" and any(k["type"] == "smoke" and setups.zone_at(mp, k["target"]) == setups.zone_at(mp, target) for k in kept):
                continue
            if kept and abs(t_med - kept[0]["t"]) > (10 if side == "CT" else 12):
                continue
            if _puts_out((typ, target), [(k["type"], k["target"]) for k in kept]):
                continue
            if kept and side == "CT":   # one way in, the stack's own; a second one when the first gives less than 3 grenades
                # (22/10, Fachwerk's B: T Main's molotov and flash, Heaven's smoke and HE, its two ways in)
                from wily.training import setups
                zs = {setups.zone_at(mp, k["target"]) for k in kept}
                can = len(kept) + sum(1 for r in rows[i + 1:] if setups.zone_at(mp, r[2]) in zs)   # the ones in at best
                # another way in: its smoke or its molotov always welcome (30/10, his review on Dust2's A: "la deuxième smoke,
                # c'est vraiment le doublon de la première ... Ça serait limite bien de trouver une smoke ou une molo short")
                if setups.zone_at(mp, target) not in zs and can >= 3 and typ not in ("smoke", "molotov"):
                    continue
            f = os.path.join(config.OUT, "selftest", f"lineup_finder_{mp}_{role}_v2.json")
            R = config.read_json(f, {}) or {}
            # built today already (a slice run in the foreground) from the throws as they are (22/10: the base's table
            # built again, Fachwerk's 34 matches become 44: the morning's roles made again)
            src = os.path.join(config.OUT, "selftest", f"throws_{mp}.parquet")
            if (R.get("built") == time.strftime("%Y-%m-%d") and "--again" not in sys.argv and R.get("target")
                    and math.dist(R["target"][:2], target[:2]) < 50 and not (os.path.exists(src) and os.path.getmtime(f) < os.path.getmtime(src))
                    and (R.get("search") == SEARCH or role in KEEP)):
                found = R.get("found")
            else:
                found = build_role(mp, side, site, role, typ, target, c, holds)
            # where it really pops: out of its spot's sight, and (a flash, an HE) someone of the base in its reach
            import defense_build as DB
            n_matches = max(1, len(train._map_dirs(mp)))
            found = [x for x in found or [] if DB.reachable(mp, x["pos"], c)   # never a boost's spot (23/10 eve)
                     and train._exposed(mp, x["pos"], x["pop"], 150, 120) / n_matches <= EXPO
                     and (typ not in ("flash", "he") or DB._has_victims(mp, typ, x, 3 if side == "CT" else 2))
                     and not train._thrower_sees(mp, typ, x["pos"], x["pop"])   # 22/10: Fachwerk B's flash, 3.3 s in his eyes
                     and not (side == "CT" and typ == "molotov" and (train.molotov_blocks(mp, x["pop"], t_med + 1.5)[0] or 1.0) < DB.BLOCKS)]   # 22/10: walked round
            # his 30/10 rules, judged on the server: an HE's or a molotov's thrower out of its victims' sight; a flash aimed
            # at a landmark
            if typ in ("he", "molotov"):
                found = [x for x in found if thrower_seen(x) is not True]
            if typ == "flash":
                found = [x for x in found if flash_landmark(x) is not False]
            if found and kept and side == "T":   # one player throws them all in a row: spots 6 s of running apart at most (the smokes first, up 17 s)
                first = kept[0]["pos"]
                found = [x for x in found if math.dist(x["pos"][:2], first[:2]) <= 1500]
                # and from the same way in (22/10, Dust2's exec A from Long: its flash from Short Stairs)
                z0 = train.zone_raw(mp, first)
                if z0:
                    way = train.way_zones(mp, z0, f"Bombsite{site}")
                    found = [x for x in found if train.zone_raw(mp, x["pos"]) in way]
            if found:
                kept.append({"role": role, "type": typ, "target": target, "t": t_med, "pro": n, "pos": found[0]["pos"]})
                kinds[typ] = kinds.get(typ, 0) + 1
            book = config.read_json(PLAN_F, {}) or {}
            book[f"{mp}|{key}"] = kept
            config.write_json(PLAN_F, book)


if __name__ == "__main__":
    main()
