"""The floor around each Momentum jump, traced on a training server (27/10, the real-client lab: 20 of 39 jump drills
missed, the driver come down right under the base's landing point, 50-63 u below it: those points are where the
base's jumpers stood, the median of their feet, often hanging past a crate's edge, their body on it, the point itself
over the void): around each landing and each takeoff a grid of downward lines (4 u apart, 48 u around it) and along
each jump's line its floor, traced by the plugin from a file (css_dbglosfile). out/realtest/jump_geo/<map>.json keeps
per jump and step the floor's heights; tools/real_client.py reads it to land on the top itself and to know where its
edge is.

    COACH_CS2SERVER=E:\\CS2Server2 COACH_CS2PORT=27016 python tools/jump_probe.py [maps]   (the second server: the
    battery's own server and his game left alone)"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from wily.core import config  # noqa: E402
from wily.training import momentum, replay  # noqa: E402

OUT = os.path.join(HERE, "out", "realtest", "jump_geo")
JUMPS_1 = os.path.join("E:" + os.sep, "CS2Server", "game", "csgo", "coach", "jumps.jsonl")   # his !jump saves (server 1's)
UP, DOWN = 48.0, 112.0   # each line from 48 u over the point's height down to 112 u under it
R, STEP = 48, 4
LOW = 12.0


def jumps_of(mp):
    """Each jump the drills can offer on the map: the base's, his (resources/momentum_his.json) and his !jump saves."""
    out = []
    data = momentum.load(mp, build=False) or {}
    for j in data.get("jumps") or []:
        out.append({"id": j["id"], "pts": [j["from"]] + list(j.get("marks") or []) + [j["to"]]})
    for j in momentum.his(mp):
        out.append({"id": j["id"], "pts": [j["from"], j["to"]]})
    try:
        with open(JUMPS_1, encoding="utf-8") as f:
            for ln in f:
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                js = [j for j in r.get("jumps") or [] if j.get("from") and j.get("to")]
                if r.get("map") == mp and js:
                    out.append({"id": f"mine:{int(r.get('t') or 0)}", "pts": [js[0]["from"]] + [j["to"] for j in js]})
    except OSError:
        pass
    return out


def grid_rows(p):
    """Two lines down at each spot of its grid: from 48 u over the point and from 12 u over it (27/10, Inferno's Second
    Mid: from 48 u up, inside the arch over it, no floor seen where the driver had just stood)."""
    rows = []
    for dx in range(-R, R + 1, STEP):
        for dy in range(-R, R + 1, STEP):
            for up in (UP, LOW):
                rows.append([round(p[0] + dx, 1), round(p[1] + dy, 1), round(p[2] + up, 1), round(p[0] + dx, 1), round(p[1] + dy, 1), round(p[2] - DOWN, 1)])
    return rows


def line_rows(a, b):
    """Its floor along the jump's line, every 4 u, on its middle and 12 u to each side (the body is 32 u wide)."""
    L = math.hypot(b[0] - a[0], b[1] - a[1])
    n = max(2, int(L // 4) + 1)
    ux, uy = ((b[0] - a[0]) / L, (b[1] - a[1]) / L) if L > 0.5 else (1.0, 0.0)
    top = max(a[2], b[2]) + UP
    bot = min(a[2], b[2]) - DOWN
    rows = []
    for k in range(-6, n + 6):   # 24 u before its takeoff and past its landing too
        s = k * L / (n - 1)
        for side in (-12, 0, 12):
            x, y = a[0] + ux * s - uy * side, a[1] + uy * s + ux * side
            rows.append([round(x, 1), round(y, 1), round(top, 1), round(x, 1), round(y, 1), round(bot, 1)])
    return rows, top, bot


def trace(rows):
    """Each line as a player's body meets things (its 7th number 1: the plugin's PlayerSolidBrushOnly; 27/10, Inferno's
    Second Mid: a balcony's railing and the clips under it let bullets through)."""
    fin, fout = os.path.join(replay.COACH, "los_in.json"), os.path.join(replay.COACH, "los_out.json")
    with open(fin, "w", encoding="utf-8") as fh:
        json.dump([r[:6] + [1] for r in rows], fh)
    t_ask = time.time()
    for _ in range(4):   # the first one may only add the bot it traces past
        replay.rcon("css_dbglosfile")
        t0 = time.time()
        while time.time() - t0 < 20:
            time.sleep(0.5)
            if os.path.exists(fout) and os.path.getmtime(fout) >= t_ask:
                try:
                    res = json.load(open(fout, encoding="utf-8"))
                    if len(res) == len(rows):
                        return res
                except (OSError, ValueError):
                    pass
        time.sleep(1.5)
    return None


def main():
    maps = [a for a in sys.argv[1:] if not a.startswith("--")] or ["de_inferno"]
    os.makedirs(OUT, exist_ok=True)
    for mp in maps:
        js = jumps_of(mp)
        if not js:
            print(mp, "no jump", flush=True)
            continue
        replay.start(mp)
        replay.keep()
        rows, who = [], []
        for j in js:
            for k, p in enumerate(j["pts"]):
                for r in grid_rows(p):
                    rows.append(r)
                    who.append((j["id"], "grid", k))
            for k in range(1, len(j["pts"])):
                lr, top, bot = line_rows(j["pts"][k - 1], j["pts"][k])
                for r in lr:
                    rows.append(r)
                    who.append((j["id"], "line", k))
        res = None
        for i in range(0, len(rows), 6000):   # a few thousand a call
            part = trace(rows[i:i + 6000])
            if part is None:
                break
            res = (res or []) + part
        if not res or len(res) != len(rows):
            print(mp, "the plugin did not trace the lines: nothing kept", flush=True)
            continue
        book = {"map": mp, "t": int(time.time()), "r": R, "step": STEP, "jumps": {}}
        for j in js:
            book["jumps"][j["id"]] = {"pts": [[round(v, 1) for v in p[:3]] for p in j["pts"]], "grid": [[] for _ in j["pts"]],
                                      "line": [[] for _ in j["pts"]]}
        pend = {}
        for (jid, what, k), r, f in zip(who, rows, res):
            z = None if f is None or f < 0 else (None if f >= 0.999 else round(r[2] - f * (r[2] - r[5]), 1))
            inside = f is not None and 0 <= f < 0.001   # started in the solid: a wall or a ceiling there
            v = "x" if inside else z
            if what == "grid":   # its two lines: the high one's floor, else the low one's
                key_ = (jid, k, r[0], r[1])
                if key_ not in pend:
                    pend[key_] = v
                    continue
                hi = pend.pop(key_)
                v = hi if isinstance(hi, float) else v if isinstance(v, float) else hi
            book["jumps"][jid][what][k].append([r[0], r[1], v])
        with open(os.path.join(OUT, f"{mp}.json"), "w", encoding="utf-8") as fh:
            json.dump(book, fh)
        print(mp, len(js), "jumps,", len(rows), "lines traced", flush=True)


if __name__ == "__main__":
    main()
