"""A flash thrown from a spot you find again that pops where you want it (20/10, the user on his exec B: "il faudrait
trouver une flash qui pop au-dessus de la sortie d'en bas ... je ferai exploser une flash où je veux que la flash
explose et tu trouveras un endroit").

    python tools/flash_finder.py <map> [--target x,y,z | --last] [--near x,y ...] [--zone NAME] [--sweep] [--keep N]
    ... --wide [--spots 8]      every way: still, jumpthrow, run-throw, running jumpthrow, each click, a grid of aims
                                around each, a bounce off a wall allowed (not the floor: heard), the closest refined

--last: where the last flash you threw on the training server popped (coach/throws.jsonl). --near: spots within 700 u
of these (an exec's own spots: his corners). The candidates: the places the base's players stand (their side), with a
wall or a corner by them (train.spot_walls), 300 to 1400 u from it (--zone: in that place only, the way in a take
throws from: 20/10, the only two found for his exec B flash were on B site itself); for each, a standing throw and a jumpthrow with each
click, aimed by CS2's throw (wily/insights/nades.py _phys: 10 degrees over the aim, 675 / 439 / 203 u/s, a flash pops
1.62 s after it leaves the hand, gravity 320). The best ones thrown on the server by a bot (css_dbgthrow), their aim
corrected twice from where they popped (--sweep: and the aims around it, 3 degrees apart up to 12 up and down, 2 aside:
a roof or an arch on the way stops the one the model gives); kept: 120 u from it at most, not bouncing on the floor. Written to
out/selftest/flash_finder_<map>.json, best first. The training server must be free."""
import argparse
import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from wily.core import config  # noqa: E402
from wily.training import replay, train  # noqa: E402
import lineup_check  # noqa: E402

FUSE, G = 1.62, 320.0
CLICK = {"left": (675.0, 0.0), "both": (438.75, -6.0), "right": (202.5, -12.0)}
HOWS = {"still": "still", "jump": "jump", "W": "W", "WJ": "WJ"}   # css_dbgthrow's words (the plugin's throw model)


def flight(pos, pitch, yaw, how, click, crouch=False, t=FUSE):
    """Where a throw is t s after it leaves the hand (no wall): the plugin's own model (SelfTest.cs WordsNade)."""
    speed, dz = CLICK[click]
    el, yr = math.radians(10 - pitch * 80 / 90), math.radians(yaw)
    fw = np.array([math.cos(el) * math.cos(yr), math.cos(el) * math.sin(yr), math.sin(el)])
    v = fw * speed + (np.array([0, 0, 265.0]) if how == "jump" else 0)
    src = np.array([pos[0], pos[1], pos[2] + (46 if crouch else 64)]) + fw * 16 + np.array([0, 0, dz])
    return src + v * t + np.array([0, 0, -0.5 * G * t * t])


def aim(pos, target, how, click):
    """The aim (pitch, yaw) whose flight passes nearest the target at the fuse, and how far (u)."""
    yaw = math.degrees(math.atan2(target[1] - pos[1], target[0] - pos[0]))
    best = None
    for pitch in np.arange(-89, 89.1, 0.5):
        e = float(np.linalg.norm(flight(pos, pitch, yaw, how, click) - np.asarray(target, float)))
        if best is None or e < best[0]:
            best = (e, float(pitch))
    return best[1], yaw, best[0]


def spots(mp, target, side, near, keep, zone=None, every=False):
    S = train._zone_samples(mp)
    X, Y, Z = S.X.to_numpy(), S.Y.to_numpy(), S.Z.to_numpy()
    d = np.hypot(X - target[0], Y - target[1])
    m = (d > 300) & (d < 1400) & (Z < target[2] + 50) & (Z > target[2] - 500)
    if near:
        m &= np.min([np.hypot(X - a[0], Y - a[1]) for a in near], axis=0) < 700
    if zone:
        m &= S["name"].astype(str).to_numpy() == zone
    cells = {}
    for x, y, z in zip(X[m], Y[m], Z[m]):
        cells.setdefault((round(x / 48), round(y / 48)), []).append((x, y, z))
    out = []
    for pts in cells.values():
        if len(pts) < 20:
            continue
        p = [float(np.median([q[i] for q in pts])) for i in range(3)]
        if not train.spot_walls(mp, p)["ok"]:
            continue
        if every:   # each spot, whatever the model says (a wide search throws them all)
            out.append({"pos": [round(v, 1) for v in p], "model_off": 0, "how": "still", "click": "left"})
            continue
        for how in ("still", "jump"):
            for click in CLICK:
                pitch, yaw, e = aim(p, target, how, click)
                if e < 90:
                    out.append({"pos": [round(v, 1) for v in p], "how": how, "click": click, "pitch": round(pitch, 2), "yaw": round(yaw, 2), "model_off": round(e)})
    out.sort(key=lambda c: (c["model_off"], c["how"] != "still", c["click"] != "left"))
    return out[:keep]


def throw(c):
    d = {"type": "flash", "me": {"pos": c["pos"], "ang": [c["pitch"], c["yaw"]]}, "how": ""}
    k = HOWS.get(c["how"], "still")
    for _ in range(3):
        r = lineup_check.throw(d, k, c["click"])
        if r != "again":
            return r
        time.sleep(2)
    return None


def wide(mp, target, near, zone, nspots, log=print):
    """20/10, the user, on his exec B's flash none of the standing throws reached: "me laisser chercher plus large :
    flashs en courant ou qui ricochent sur un mur -> fait". The spots (a wall by them, that place) nearest his own,
    each way of throwing, a grid of aims around the bearing to it (24 degrees aside, 21 up and down), thrown on the
    server; a pop 400 u from it at most kept, its aim then corrected four times from where it popped (a wall's bounce
    is no model's). A bounce on the floor never: they hear it."""
    S = spots(mp, target, None, near, 999, zone, every=True)
    seen, P = set(), []
    for c in S:   # one per spot, nearest his own spots first
        k = (round(c["pos"][0] / 48), round(c["pos"][1] / 48))
        if k not in seen:
            seen.add(k)
            P.append(c["pos"])
    if near:
        P.sort(key=lambda p: min(math.dist(p[:2], a[:2]) for a in near))
    P = P[:nspots]
    log(f"{len(P)} spots: {P}", flush=True)
    tries = []
    for p in P:
        bear = math.degrees(math.atan2(target[1] - p[1], target[0] - p[0]))
        for how in HOWS:
            for click in CLICK:
                m = "jump" if how in ("jump", "WJ") else "still"
                pitch0, _, _ = aim(p, target, m, click)
                for dp in (-21, -14, -7, 0, 7, 14, 21):
                    for dy in (-24, -16, -8, 0, 8, 16, 24):
                        replay.keep()
                        c = {"pos": p, "how": how, "click": click, "pitch": round(max(-89.0, min(89.0, pitch0 + dp)), 2), "yaw": round(bear + dy, 2)}
                        r = throw(c)
                        if not isinstance(r, tuple):
                            continue
                        off = float(np.hypot(target[0] - r[0], target[1] - r[1]))
                        if r[3] or abs(r[2] - target[2]) > 200:
                            continue   # heard on the floor, or another height
                        c.update(pop=[round(v) for v in r[:3]], off=round(off))
                        tries.append(c)
                log(f"  {p} {how} {click}: best so far {min((t['off'] for t in tries), default=None)} u", flush=True)
    tries.sort(key=lambda t: t["off"])
    found = []
    for c in [t for t in tries if t["off"] <= 400][:15]:   # the closest refined
        c = dict(c)
        for _ in range(4):
            if c["off"] <= 60:
                break
            p = np.asarray(c["pos"][:2], float)
            want, got = math.atan2(target[1] - p[1], target[0] - p[0]), math.atan2(c["pop"][1] - p[1], c["pop"][0] - p[0])
            t = dict(c, yaw=round(c["yaw"] + math.degrees((want - got + math.pi) % (2 * math.pi) - math.pi), 2),
                     pitch=round(max(-89.0, min(89.0, c["pitch"] - (math.dist(p, target[:2]) - math.dist(p, c["pop"][:2])) / 40)), 2))
            replay.keep()
            r = throw(t)
            if not isinstance(r, tuple) or r[3]:
                break
            off = round(float(np.hypot(target[0] - r[0], target[1] - r[1])))
            if off >= c["off"]:
                break
            c = dict(t, pop=[round(v) for v in r[:3]], off=off)
        log(f"  refined {c['how']} {c['click']} from {c['pos']} aim {c['pitch']} {c['yaw']}: {c['off']} u off", flush=True)
        if c["off"] <= 120 and abs(c["pop"][2] - target[2]) <= 120:
            found.append(c)
    return found, tries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("--target")
    ap.add_argument("--last", action="store_true")
    ap.add_argument("--near", nargs="*", default=[])
    ap.add_argument("--keep", type=int, default=30)
    ap.add_argument("--zone")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--wide", action="store_true")
    ap.add_argument("--spots", type=int, default=8)
    a = ap.parse_args()
    if a.last:
        T = [json.loads(ln) for ln in open(os.path.join(replay.COACH, "throws.jsonl"), encoding="utf-8") if ln.strip()]
        T = [t for t in T if t.get("map") == a.map and t.get("type") == "flash" and t.get("pop") and not t.get("test")]
        target = T[-1]["pop"]
        print(f"your last flash popped at {target} ({time.strftime('%d/%m %H:%M', time.localtime(T[-1]['t']))})", flush=True)
    else:
        target = [float(v) for v in a.target.split(",")]
    near = [[float(v) for v in s.split(",")] for s in a.near]
    if a.wide:
        replay.start(a.map)
        replay.keep()
        replay.rcon("sv_hibernate_when_empty 0")
        cheats = "true" in (replay.rcon("sv_cheats") or "")
        replay.rcon("sv_cheats 1")
        replay.rcon("host_timescale 4")   # the search 4 times faster (the self-tests' way)
        try:
            found, tries = wide(a.map, target, near, a.zone, a.spots)
        finally:
            replay.rcon("host_timescale 1")
            if not cheats:
                replay.rcon("sv_cheats 0")
        found.sort(key=lambda c: (c["off"], c["how"] != "still"))
        out = os.path.join(config.OUT, "selftest", f"flash_finder_{a.map}.json")
        config.write_json(out, {"target": target, "found": found, "tries": len(tries), "t": time.time()})
        print(f"{len(found)} found ({len(tries)} pops heard nowhere on the floor): {out}", flush=True)
        for c in found[:8]:
            print(f"  {c['how']:5} {c['click']:5} from {c['pos']} aim {c['pitch']} {c['yaw']}: pops at {c['pop']}, {c['off']} u off", flush=True)
        return
    cands = spots(a.map, target, None, near, a.keep, a.zone)
    print(f"{len(cands)} candidates from spots with a wall by them", flush=True)
    replay.start(a.map)
    replay.keep()
    replay.rcon("sv_hibernate_when_empty 0")
    found = []
    for c in cands:
        replay.keep()
        r = None
        for _ in range(3):   # its aim corrected from where it popped
            r = throw(c)
            if not isinstance(r, tuple):
                break
            off = np.asarray(target[:2], float) - np.asarray(r[:2], float)
            c["pop"], c["bounces"] = [round(v) for v in r[:3]], r[3]
            c["off"] = round(float(np.hypot(*off)))
            if c["off"] <= 60 or c["off"] > 300:
                break   # there, or stopped by a wall on its way (no aim near this one gets it there)
            # the yaw toward the target; the pitch by the distance short or long, a degree per 40 u
            p = np.asarray(c["pos"][:2], float)
            want, got = math.atan2(target[1] - p[1], target[0] - p[0]), math.atan2(r[1] - p[1], r[0] - p[0])
            c["yaw"] = round(c["yaw"] + math.degrees((want - got + math.pi) % (2 * math.pi) - math.pi), 2)
            short = math.dist(p, target[:2]) - math.dist(p, r[:2])
            c["pitch"] = round(max(-89.0, min(89.0, c["pitch"] - short / 40)), 2)
        ok = isinstance(r, tuple) and c.get("off", 999) <= 120 and not c.get("bounces")
        if not ok and a.sweep:   # the aims around the model's: something on its way
            base = (c["pitch"], c["yaw"])
            for dp in (-12, -9, -6, -3, 3, 6, 9, 12):
                for dy in (-2, 0, 2):
                    replay.keep()
                    t = dict(c, pitch=round(max(-89.0, min(89.0, base[0] + dp)), 2), yaw=round(base[1] + dy, 2))
                    r2 = throw(t)
                    if not isinstance(r2, tuple):
                        continue
                    off2 = round(float(np.hypot(target[0] - r2[0], target[1] - r2[1])))
                    if off2 <= 120 and not r2[3] and abs(r2[2] - target[2]) <= 120:
                        c.update(t, pop=[round(v) for v in r2[:3]], bounces=0, off=off2)
                        ok = True
                        break
                if ok:
                    break
            if ok:
                print(f"    swept: aim {c['pitch']} {c['yaw']} pops {c['off']} u off", flush=True)
        print(f"  {c['how']:5} {c['click']:5} from {c['pos']} aim {c['pitch']} {c['yaw']}: "
              + (f"pops {c.get('off')} u off{', bounces on the floor' if c.get('bounces') else ''}" if isinstance(r, tuple) else "no pop")
              + ("  OK" if ok else ""), flush=True)
        if ok:
            found.append(c)
    found.sort(key=lambda c: (c["off"], c["how"] != "still"))
    out = os.path.join(config.OUT, "selftest", f"flash_finder_{a.map}.json")
    config.write_json(out, {"target": target, "found": found, "t": time.time()})
    print(f"{len(found)} found: {out}", flush=True)


if __name__ == "__main__":
    main()
