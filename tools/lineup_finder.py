"""A lineup of any grenade thrown from a spot you find again onto a place (21/10, the user: "fais-moi pareil ... déjà finis
les stuff de Fachwerk pour la partie défensive, histoire de tester si tu as bien compris ce que je voulais et si tu sais
l'appliquer et le contrôler par toi-même"; his rules, 19/10: "on retient un stuff en identifiant une zone depuis
laquelle l'envoyer ... un angle, le long d'un mur", "des éléments visuels sur lesquels poser notre viseur", then the
click and the move). The base's own defensive throws on Fachwerk come from open spots none of its players threw from a
corner (tools: out/selftest/logs/ct_why.py): their places are the targets, the lineups are found here.

    python tools/lineup_finder.py <map> <smoke|molotov|flash|he> --target x,y,z [--near x,y ...] [--zone NAME]
                                  [--keep 24] [--tol 70] [--out NAME]

The candidates: the places the base's players stand with a wall or a corner by them (train.spot_walls), 250 to 1500 u
from the target (--near: within 600 u of these, the defender's own place; --zone: in that place only); for each, a
standing throw and a jumpthrow with each click, aimed by the plugin's throw model (SelfTest.cs WordsNade: 10 degrees
over the aim, 675 / 439 / 203 u/s, 16 u ahead of the eyes, a jump's 265 u/s up; gravity 320): a flash at its pop (1.62
s), the others where they come down to the target's height. The best ones thrown on the server by a bot (css_dbgthrow,
the game flies them: roofs, walls, rolls), their aim corrected three times from where they popped. Kept: within --tol
of it on its floor (96 u up or down), a flash never bouncing on the floor (heard). Written to
out/selftest/lineup_finder_<map>_<out>.json, best first, each with the grenade's own start and speed (the words' throw)
so the victims and the guide replay it exactly. The training server must be free."""
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

G = 320.0
FUSE = 1.62
CLICK = {"left": (675.0, 0.0), "both": (438.75, -6.0), "right": (202.5, -12.0)}
WORDS = {"still": "standing still", "jump": "jumpthrow"}
CLICK_WORDS = {"left": "left click", "both": "left + right click", "right": "right click"}


def start(pos, pitch, yaw, how, click):
    """The grenade's start and speed as the plugin throws these words (SelfTest.cs WordsNade)."""
    speed, dz = CLICK[click]
    el, yr = math.radians(10 - pitch * 80 / 90), math.radians(yaw)
    fw = np.array([math.cos(el) * math.cos(yr), math.cos(el) * math.sin(yr), math.sin(el)])
    v = fw * speed + (np.array([0.0, 0.0, 265.0]) if how in ("jump", "WJ") else 0.0)
    if how in ("W", "WJ"):   # a run-throw (23/10): the run's 190 u/s forward at the release (css_dbgthrow "W")
        v = v + np.array([math.cos(yr), math.sin(yr), 0.0]) * 190.0
    src = np.array([pos[0], pos[1], pos[2] + 64.0]) + fw * 16 + np.array([0.0, 0.0, dz])
    return src, v


def model_off(typ, pos, pitch, yaw, how, click, target):
    """How far the model's flight passes from the target: a flash at its pop, the others where they come down to its
    height (no wall, no bounce)."""
    src, v = start(pos, pitch, yaw, how, click)
    if typ == "flash":
        p = src + v * FUSE + np.array([0.0, 0.0, -0.5 * G * FUSE * FUSE])
        return float(np.linalg.norm(p - np.asarray(target, float)))
    best = None
    for t in np.arange(0.1, 5.0, 1 / 32):
        p = src + v * t + np.array([0.0, 0.0, -0.5 * G * t * t])
        if v[2] - G * t < 0 and p[2] <= target[2] + 8:   # coming down to its height
            return float(math.hypot(p[0] - target[0], p[1] - target[1]))
        best = p
    return 1e9 if best is None else float(np.linalg.norm(best - np.asarray(target, float)))


def aims(typ, pos, target, how, click):
    """The aims whose model flight reaches it: the flattest one and the highest lob (a roof over the target stops a lob,
    a wall before it stops a flat one), [(pitch, yaw, model off)]."""
    yaw = math.degrees(math.atan2(target[1] - pos[1], target[0] - pos[0]))
    P = np.arange(-70, 60.1, 0.5)
    E = np.array([model_off(typ, pos, float(p), yaw, how, click, target) for p in P])
    mins = [i for i in range(len(P)) if E[i] < 120 and (i == 0 or E[i] <= E[i - 1]) and (i == len(P) - 1 or E[i] <= E[i + 1])]
    if not mins:
        i = int(E.argmin())
        return [(float(P[i]), yaw, float(E[i]))]
    out = [(float(P[i]), yaw, float(E[i])) for i in (max(mins), min(mins))]   # pitch up is negative: the flattest first
    return out if out[0][0] != out[1][0] else out[:1]


def aim(typ, pos, target, how, click):
    return aims(typ, pos, target, how, click)[0]


def walled_near(mp, p, r=64.0):
    """The nearest place by p the base's players stand on with a wall or a corner by it, same floor, r u at most."""
    G = train._occupancy(mp)
    X, Y, Z = G[:, 0] * 8.0, G[:, 1] * 8.0, G[:, 2] * 16.0
    m = (np.abs(X - p[0]) < r) & (np.abs(Y - p[1]) < r) & (np.abs(Z - p[2]) < 24)
    cand = sorted((math.hypot(x - p[0], y - p[1]), float(x), float(y)) for x, y in zip(X[m], Y[m]))
    for d, x, y in cand:
        if d > r:
            break
        q = [x, y, float(p[2])]
        if train.spot_walls(mp, q)["ok"]:
            return q
    return None


def seeds(mp, typ, target, side, near):
    """The base's own throws of it that landed there (120 u, same floor), from a spot with a wall by it (theirs or the
    nearest one, 64 u at most): their aim moved to that spot (its bearing to it, the model's pitch for the shift), their
    jump or not, the click whose model landing is nearest theirs. Walked and run throws start a still one."""
    import pandas as pd
    N = pd.read_parquet(os.path.join(config.OUT, "population", "nades.parquet"), filters=[("map", "==", mp), ("side", "==", side), ("type", "==", typ)])
    M = N[(np.hypot(N.land_X - target[0], N.land_Y - target[1]) < 120) & (np.abs(N.land_Z - target[2]) < 60)]
    if near and len(M):
        M = M[np.min([np.hypot(M.X - a[0], M.Y - a[1]) for a in near], axis=0) < 700]
    out, seen = [], set()
    for r in M.itertuples():
        p0 = [float(r.X), float(r.Y), float(r.Z)]
        sp = walled_near(mp, p0)
        if sp is None:
            continue
        how = "jump" if r.jump else "still"
        click = min(CLICK, key=lambda c: model_off(typ, p0, float(r.pitch), float(r.yaw), how, c, [r.land_X, r.land_Y, r.land_Z]))
        k = (round(sp[0] / 24), round(sp[1] / 24), how, click)
        if k in seen:
            continue
        seen.add(k)
        dyaw = math.degrees(math.atan2(target[1] - sp[1], target[0] - sp[0]) - math.atan2(target[1] - p0[1], target[0] - p0[0]))
        m0 = aim(typ, p0, target, how, click)[0]
        m1 = aim(typ, sp, target, how, click)[0]
        out.append({"pos": [round(v, 1) for v in sp], "how": how, "click": click, "pitch": round(float(r.pitch) + (m1 - m0), 2),
                    "yaw": round(float(r.yaw) + dyaw, 2), "model_off": 0, "walls": train.spot_walls(mp, sp)["walls"], "seed": True})
    return out


def spots(mp, typ, target, near, zone, keep):
    S = train._zone_samples(mp)
    X, Y, Z = S.X.to_numpy(), S.Y.to_numpy(), S.Z.to_numpy()
    d = np.hypot(X - target[0], Y - target[1])
    m = (d > 250) & (d < 1500) & (Z < target[2] + 300) & (Z > target[2] - 500)
    if near:
        m &= np.min([np.hypot(X - a[0], Y - a[1]) for a in near], axis=0) < 600
    if zone:
        m &= S["name"].astype(str).to_numpy() == zone
    cells = {}
    for x, y, z in zip(X[m], Y[m], Z[m]):
        cells.setdefault((round(x / 32), round(y / 32)), []).append((x, y, z))
    out = []
    for pts in cells.values():
        if len(pts) < 15:
            continue
        p = [float(np.median([q[i] for q in pts])) for i in range(3)]
        w = train.spot_walls(mp, p)
        if not w["ok"]:
            continue
        for how in ("still", "jump"):
            for click in CLICK:
                for pitch, yaw, e in aims(typ, p, target, how, click):
                    if e < 120:
                        out.append({"pos": [round(v, 1) for v in p], "how": how, "click": click, "pitch": round(pitch, 2), "yaw": round(yaw, 2),
                                    "model_off": round(e), "walls": w["walls"]})
    # the natural ones first: a still throw before a jump, a left click before the others, the model's nearest
    out.sort(key=lambda c: (c["model_off"] > 40, c["how"] != "still", c["click"] != "left", c["model_off"]))
    seen, uniq = set(), []
    for c in out:   # one try per spot, way and arc
        k = (round(c["pos"][0] / 32), round(c["pos"][1] / 32), c["how"], c["click"], c["pitch"] < -35)
        if k not in seen:
            seen.add(k)
            uniq.append(c)
    return uniq[:keep]


def throw(typ, c):
    d = {"type": typ, "me": {"pos": c["pos"], "ang": [c["pitch"], c["yaw"]]}, "how": "", "item": ""}
    for _ in range(3):
        r = lineup_check.throw(d, c["how"], c["click"])
        if r != "again":
            return r
        time.sleep(2)
    return None


def judge(typ, r, target, tol):
    """(kept, off): within tol of it on its floor; a flash never bouncing on the floor."""
    if not isinstance(r, tuple):
        return False, None
    off = float(math.hypot(target[0] - r[0], target[1] - r[1]))
    ok = off <= tol and abs(r[2] - target[2]) <= (200 if typ == "flash" else 96) and not (typ == "flash" and r[3])
    return ok, off


def sweep(typ, c, target, tol):
    """Its aim around (2 and 4 degrees up and down, 1.5 aside): the best landing on its floor, (c, r, ok, off) or None."""
    best = None
    for dp in (-2, 2, -4, 4):
        for dy in (0, -1.5, 1.5):
            t = dict(c, pitch=round(max(-89.0, min(89.0, c["pitch"] + dp)), 2), yaw=round(c["yaw"] + dy, 2))
            replay.keep()
            r = throw(typ, t)
            ok, off = judge(typ, r, target, tol)
            if off is None or abs(r[2] - target[2]) > 96:
                continue
            if best is None or off < best[3]:
                best = (t, r, ok, off)
            if ok:
                return best
    return best


def find(mp, typ, target, near, zone, keep, tol, side="CT", stop=3, log=print):
    sd = seeds(mp, typ, target, side, near)
    # a still throw first, then a corner more closed in, then nearest the defender's own place
    sd.sort(key=lambda c: (c["how"] != "still", -c["walls"], min((math.dist(c["pos"][:2], a[:2]) for a in near), default=0)))
    cands = (sd + spots(mp, typ, target, near, zone, keep))[:keep]
    log(f"{len(cands)} candidates: {len(sd)} from the base's own throws there, moved to a corner; the rest from the model", flush=True)
    # the server only now (21/10, Dust2's cross smoke: 40 min of candidates with it up and nobody on it, the app's idle
    # stop took it down and the first throw found it refused)
    replay.start(mp)
    replay.keep()
    replay.rcon("sv_hibernate_when_empty 0")
    found = []
    for c in cands:
        if len(found) >= stop:   # enough to choose from
            break
        replay.keep()
        r = throw(typ, c)
        ok, off = judge(typ, r, target, tol)
        if not ok and (off is None or off > 300 or abs(r[2] - target[2]) > 96):   # another floor, or far: its aim swept
            sw = sweep(typ, c, target, tol)
            if sw:
                c, r, ok, off = sw
        for _ in range(3):   # its aim corrected from where it popped
            if ok or off is None or off > 600 or abs(r[2] - target[2]) > 96:
                break
            p = np.asarray(c["pos"][:2], float)
            want, got = math.atan2(target[1] - p[1], target[0] - p[0]), math.atan2(r[1] - p[1], r[0] - p[0])
            c = dict(c, yaw=round(c["yaw"] + math.degrees((want - got + math.pi) % (2 * math.pi) - math.pi), 2),
                     pitch=round(max(-89.0, min(89.0, c["pitch"] - (math.dist(p, target[:2]) - math.dist(p, r[:2])) / 40)), 2))
            replay.keep()
            r2 = throw(typ, c)
            ok2, off2 = judge(typ, r2, target, tol)
            if off2 is None or off2 >= off:
                break
            r, ok, off = r2, ok2, off2
        if isinstance(r, tuple):
            log(f"  {c['how']:5} {c['click']:5} from {c['pos']} aim {c['pitch']} {c['yaw']}: {round(off)} u off, z {round(r[2])}"
                f"{' bounces' if r[3] else ''}{' KEPT' if ok else ''}", flush=True)
        if ok:
            src, v = start(c["pos"], c["pitch"], c["yaw"], c["how"], c["click"])
            found.append(dict(c, pop=[round(x, 1) for x in r[:3]], off=round(off), bounces=r[3],
                              how_words=WORDS[c["how"]], click_words=CLICK_WORDS[c["click"]],
                              nade_at=[round(float(x), 1) for x in src], nade_v=[round(float(x), 1) for x in v]))
    found.sort(key=lambda c: (c["how"] != "still", c["off"]))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("map")
    ap.add_argument("type", choices=["smoke", "molotov", "flash", "he"])
    ap.add_argument("--target", required=True)
    ap.add_argument("--near", nargs="*", default=[])
    ap.add_argument("--zone")
    ap.add_argument("--keep", type=int, default=24)
    ap.add_argument("--tol", type=float, default=70)
    ap.add_argument("--out", default="")
    ap.add_argument("--side", default="CT")
    ap.add_argument("--stop", type=int, default=3)
    a = ap.parse_args()
    target = [float(v) for v in a.target.split(",")]
    near = [[float(v) for v in s.split(",")] for s in a.near]
    found = find(a.map, a.type, target, near, a.zone, a.keep, a.tol, a.side, a.stop)
    f = os.path.join(config.OUT, "selftest", f"lineup_finder_{a.map}_{a.out or a.type}.json")
    config.write_json(f, {"map": a.map, "type": a.type, "target": target, "near": near, "found": found})
    print(f"{len(found)} found: {f}", flush=True)


if __name__ == "__main__":
    main()
