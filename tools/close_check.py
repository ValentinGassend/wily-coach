"""Shotguns' posts checked on the training server (03/11, round 19: the MAG-7 defenses passed where a corner of the post
sees the attackers' ways within 307 u at most, Nuke's A and B; they failed every time from 345 u on, Fachwerk's A,
Mirage's A and B, Train's B, Vertigo's B, killed by AKs 200-600 u off where the pump wins close only): from each spot of
the post's green zone (a 40 u grid, as the test player's zone_spots), the bullet's lines to the drill's ways (a point
every 8 frames, 1,000 u of the post at most, 80 u apart) and to the bombsite; the corners' reach as the test player's
corner_spots has it. resources/close_checked.json keeps per map and post its reach; train.practice_drills leaves out a
shotgun's post over CLOSE_CAP (no forced content: a post a pump cannot hold is not offered).

    python tools/close_check.py [maps] [--again]"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from wily.core import config  # noqa: E402
from wily.training import navmesh, replay, train  # noqa: E402

BOOK = os.path.join(HERE, "resources", "close_checked.json")


def key(mp, post):
    return f"{mp}|{round(post['pos'][0])}|{round(post['pos'][1])}|{round(post['pos'][2])}"


def _in_poly(poly, x, y):
    inside, j = False, len(poly) - 1
    for i in range(len(poly)):
        if (poly[i][1] > y) != (poly[j][1] > y) and x < (poly[j][0] - poly[i][0]) * (y - poly[i][1]) / ((poly[j][1] - poly[i][1]) or 1e-9) + poly[i][0]:
            inside = not inside
        j = i
    return inside


def zone_spots(mp, post):
    """The post's green zone as the test player walks it (play_module.zone_spots): a 40 u grid inside its outline on the
    floor near its height, 30 at most, the post itself first."""
    poly, pos = post.get("poly") or [], post["pos"]
    if len(poly) < 3:
        return [list(pos)]
    xs, ys = [q[0] for q in poly], [q[1] for q in poly]
    out, x = [], min(xs)
    while x <= max(xs):
        y = min(ys)
        while y <= max(ys):
            if _in_poly(poly, x, y):
                q = navmesh.nearest(mp, [x, y, pos[2]], r=24.0, dz=40.0)
                if q and abs(q[2] - pos[2]) < 48:
                    out.append([x, y, float(q[2])])
            y += 40
        x += 40
    out.sort(key=lambda q: math.dist(q[:2], pos[:2]))
    step = max(1, len(out) // 30)
    return [list(pos)] + out[::step][:30]


def way_points(drill, k, spots):
    """The drill's ways for post k (and the free ones): a point every 8 frames within 1,000 u of the zone, 80 u apart."""
    pts = []
    for t in drill.get("tracks") or []:
        if t.get("post") not in (None, k):
            continue
        tr = t.get("path") or []
        for i in range(0, len(tr) - 2, 5 * 8):
            q = tr[i:i + 3]
            if len(q) == 3 and min(math.dist(q[:2], c[:2]) for c in spots) < 1000 and all(math.dist(q, o) > 80 for o in pts):
                pts.append(q)
    return pts


def trace(rows, log=print):
    """The plugin's bullet lines from a file (css_dbglosfile): [True when clear, ...], or None."""
    fin, fout = os.path.join(replay.COACH, "los_in.json"), os.path.join(replay.COACH, "los_out.json")
    with open(fin, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    t_ask = time.time()
    for _ in range(3):
        replay.rcon("css_dbglosfile")
        t0 = time.time()
        while time.time() - t0 < 15:
            time.sleep(0.5)
            if os.path.exists(fout) and os.path.getmtime(fout) >= t_ask:
                break
        if os.path.exists(fout) and os.path.getmtime(fout) >= t_ask:
            break
        time.sleep(1.5)
    try:
        res = json.load(open(fout, encoding="utf-8")) if os.path.getmtime(fout) >= t_ask else None
    except (OSError, ValueError):
        res = None
    if not res or len(res) != len(rows):
        log("  the plugin did not trace the lines", flush=True)
        return None
    return [f > 0.98 for f in res]


def reach(spots, pts, site):
    """The corners' reach as corner_spots has it: each spot's farthest way point in sight; the spots seeing the site
    first (unless none does within 400 u); the reach is the best of them, 80 u over it, 220 u at least. -> (reach, the
    best spot's farthest point); (None, None) when no spot sees their ways; None when the plugin did not trace."""
    n = len(pts)
    rows = [[c[0], c[1], c[2] + 64, q[0], q[1], q[2] + 64] for c in spots for q in pts]
    if site:
        rows += [[c[0], c[1], c[2] + 64, site[0], site[1], site[2] + 40] for c in spots]
    res = trace(rows)
    if res is None:
        return None
    sees_site = [res[len(spots) * n + i] for i in range(len(spots))] if site else [True] * len(spots)
    far = {}
    for i, c in enumerate(spots):
        vis = [pts[j] for j in range(n) if res[i * n + j]]
        if vis:
            far[i] = max(math.dist(c[:2], q[:2]) for q in vis)
    if not far:
        return None, None
    pool = {i: v for i, v in far.items() if sees_site[i]}
    if not pool or min(pool.values()) > 400:
        pool = far
    best = min(pool.values())
    return max(220.0, best + 80.0), best


def main():
    maps = [a for a in sys.argv[1:] if not a.startswith("--")] or ["de_mirage"]
    book = config.read_json(BOOK, {}) or {}
    sid = str(config.settings().get("own_steamid") or "")
    for mp in maps:
        drills = [d for d in train.practice_drills(sid, mp) if d.get("mode") == "defend" and str(d.get("id")).endswith(":close")]
        todo = [(d, k, p) for d in drills for k, p in enumerate(d.get("posts") or [])
                if "--again" in sys.argv or key(mp, p) not in book]
        if not todo:
            print(mp, "nothing to check", flush=True)
            continue
        replay.start(mp)
        replay.keep()
        replay.rcon("sv_hibernate_when_empty 0")
        for d, k, p in todo:
            spots = zone_spots(mp, p)
            pts = way_points(d, k, spots)
            if not pts:
                print(f"  {d['id']} post {p.get('zone')}: no way comes near it", flush=True)
                book[key(mp, p)] = {"reach": None, "zone": p.get("zone"), "checked": time.strftime("%Y-%m-%d")}
                continue
            got = reach(spots, pts, d.get("plant_at"))
            if got is None:   # asked again next time
                continue
            cap, best = got
            book[key(mp, p)] = {"reach": round(cap) if cap else None, "zone": p.get("zone"), "spots": len(spots), "points": len(pts),
                                "checked": time.strftime("%Y-%m-%d")}
            ok = cap is not None and cap <= train.CLOSE_CAP
            print(f"  {d['id']} post {p.get('zone')} {[round(v) for v in p['pos']]}: corners within {cap and round(cap)} u "
                  f"({len(spots)} spots, {len(pts)} way points) -> {'kept' if ok else 'no shotgun post'}", flush=True)
        config.write_json(BOOK, book)
    print("written", BOOK, flush=True)


if __name__ == "__main__":
    main()
