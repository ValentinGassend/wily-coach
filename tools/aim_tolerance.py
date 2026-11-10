"""Each lineup's own yellow circle, measured on the training server (23/10, the user: "le rond de visée de 0,9° est trop
large pour les lancers sensibles au rebond", "tolérance par lancer : mesurer de combien l'impact bouge quand la visée
bouge d'un dixième de degré, et resserrer le rond pour les lancers sensibles").

    python tools/aim_tolerance.py [maps] [--again] [--budget S]

Every lineup the app gives on each map (its stuff drills, your clips' and setups', each site take's and defense's
members) thrown as its words say, then with its aim a tenth of a degree up, down, left and right (css_dbgthrow, the game
flying it). How far its landing moves for that tenth is its sensitivity; the circle is the aim that keeps it within half
of its PERFECT zone (70 u a smoke, 120 the others), 0.9 degree at most, 0.25 at least; one that lands on another floor or
does not pop at all a tenth off gets the smallest. resources/aim_tolerance.json keeps each one (train.aim_tol reads it,
the plugin draws the circle that size and checks the aim in it)."""
import copy
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from wily.core import config  # noqa: E402
from wily.training import replay, train  # noqa: E402
import lineup_check as LC  # noqa: E402

PERFECT = {"smoke": 70.0, "flash": 120.0, "he": 120.0, "molotov": 120.0}
TOL_MAX, TOL_MIN = 0.9, 0.25
STEP = 0.1


def pool(sid, mp):
    """The lineups of the map the app can give, each once: [drill]."""
    from wily.training import execs
    out = {}
    ds = list(LC._pool(sid, mp))
    for key in execs.KEYS:
        try:
            cands, _ = execs.sequence(sid, mp, key)
        except Exception:
            continue
        for d in cands or []:
            ds.append(d)
            ds += [dict(m, map=m.get("map") or mp) for m in d.get("members") or []]
    for d in ds:
        me = d.get("me") or {}
        if d.get("kind", "nade") != "nade" or d.get("mode") in ("exec", "entry", "hold") or not d.get("target") or len(me.get("pos") or []) < 3:
            continue
        d = dict(d, map=d.get("map") or mp)
        out.setdefault(train.aim_key(mp, d["type"], me["pos"], me["ang"]), d)
    return out


def land(d, how, click):
    r = None
    for _ in range(3):
        r = LC.throw(d, how, click)
        if r != "again":
            break
        time.sleep(2)
    return r if isinstance(r, tuple) else None


def measure(d):
    """(sensitivity in u per tenth of a degree, the circle in degrees, the landings)."""
    how, click = LC._args(d.get("how"), d.get("click"))
    replay.keep()
    r0 = land(d, how, click)
    if r0 is None:
        return None, None, []
    tg = d["target"]
    sens, pops = 0.0, [[round(v) for v in r0[:3]]]
    for dp, dy in ((STEP, 0.0), (-STEP, 0.0), (0.0, STEP), (0.0, -STEP)):
        x = copy.deepcopy(d)
        x["me"]["ang"] = [d["me"]["ang"][0] + dp, d["me"]["ang"][1] + dy]
        replay.keep()
        r = land(x, how, click)
        if r is None or (len(tg) >= 3 and abs(r[2] - r0[2]) > 96):   # not popped, or another floor: as touchy as can be
            sens = 1e9
            pops.append(None)
            continue
        pops.append([round(v) for v in r[:3]])
        sens = max(sens, math.hypot(r[0] - r0[0], r[1] - r0[1]))
    half = PERFECT.get(d["type"], 120.0) / 2
    tol = TOL_MIN if sens >= 1e8 else max(TOL_MIN, min(TOL_MAX, STEP * half / max(sens, 0.01)))
    return round(min(sens, 9999.0), 1), round(tol, 2), pops


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    maps = args[0].split(",") if args else ["de_fachwerk", "de_dust2", "de_mirage"]
    budget = float(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else None
    sid = str(config.settings().get("own_steamid") or "")
    book = config.read_json(train.AIM_TOL_F, {}) or {}
    t0 = time.time()
    for mp in maps:
        todo = pool(sid, mp)
        print(f"{mp}: {len(todo)} lineups", flush=True)
        replay.start(mp)
        replay.keep()
        replay.rcon("sv_hibernate_when_empty 0")
        replay.rcon("sv_cheats 1")
        replay.rcon("host_timescale 4")   # nobody on it: the game's own physics, faster
        try:
            for k, d in todo.items():
                if k in book and "--again" not in sys.argv:
                    continue
                if budget is not None and time.time() - t0 > budget:
                    print("slice over", flush=True)
                    return
                sens, tol, pops = measure(d)
                if tol is None:
                    print(f"  {d['type']:7} {str(d.get('title'))[:40]:40} never popped", flush=True)
                    continue
                book[k] = {"map": mp, "type": d["type"], "title": d.get("title"), "sens": sens, "tol": tol, "pops": pops,
                           "checked": time.strftime("%Y-%m-%d")}
                config.write_json(train.AIM_TOL_F, book)
                print(f"  {d['type']:7} {str(d.get('title'))[:40]:40} {sens} u per 0.1 deg -> circle {tol} deg", flush=True)
        finally:
            replay.rcon("host_timescale 1")
            replay.rcon("sv_cheats 0")


if __name__ == "__main__":
    main()
