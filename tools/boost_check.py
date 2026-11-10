"""The boosts checked on the training server (24/10, the real test of Mirage's Short boost: up on the crouched teammate,
neither of its two targets in sight, a wall 45 u in front of the eyes; the base's players had been higher): from the
eyes up there, the bullet's lines to each target's body (7 heights, its shoulders), traced by the plugin from a file
(css_dbglosfile), on a crouched teammate and on a standing one (18 u higher). resources/boost_checked.json keeps per
map and boost which targets are seen each way; train.boost_drills keeps those, on the teammate that shows them, and
leaves out a boost that shows none.

    python tools/boost_check.py [maps] [--again]"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from wily.core import config  # noqa: E402
from wily.training import replay, train  # noqa: E402

BOOK = os.path.join(HERE, "resources", "boost_checked.json")
STAND = 18.0   # a standing teammate's head over a crouched one's


def key(mp, top):
    return f"{mp}|{round(top[0])}|{round(top[1])}|{round(top[2])}"


def body(eye, v):
    dx, dy = v[1] - eye[1], -(v[0] - eye[0])
    n = max(1.0, (dx * dx + dy * dy) ** 0.5)
    return [[eye[0], eye[1], eye[2], round(v[0] + s * dx / n, 1), round(v[1] + s * dy / n, 1), round(v[2] + up, 1)]
            for up, s in [(h, 0) for h in (66, 58, 48, 38, 28, 18, 8)] + [(52, 12), (52, -12)]]


def trace(rows):
    fin, fout = os.path.join(replay.COACH, "los_in.json"), os.path.join(replay.COACH, "los_out.json")
    with open(fin, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    t_ask = time.time()
    for _ in range(3):
        replay.rcon("css_dbglosfile")
        t0 = time.time()
        while time.time() - t0 < 10:
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
    maps = [a for a in sys.argv[1:] if not a.startswith("--")] or ["de_mirage"]
    sid = str(config.settings().get("own_steamid") or "")
    book = config.read_json(BOOK, {}) or {}
    for mp in maps:
        ds = [d for d in train.boost_drills(sid, mp, raw=True)]
        if "--again" not in sys.argv:
            ds = [d for d in ds if key(mp, d["me"]["pos"]) not in book]
        if not ds:
            print(mp, "nothing to check", flush=True)
            continue
        replay.start(mp)
        replay.keep()
        rows, who = [], []
        for d in ds:
            top = d["me"]["pos"]
            # its top is the base's teammate's: a standing one's already (03/11, Anubis's Canals: checked 18 u too high on a
            # standing one, its near target "in sight", never in the drill, the eyes 18 u lower)
            base_up = 0.0 if (d.get("mate") or {}).get("duck") else -STAND
            for way, dz in (("crouched", base_up), ("standing", base_up + STAND)):
                eye = [top[0], top[1], top[2] + 64 + dz]
                for i, b in enumerate(d["bots"]):
                    for r in body(eye, b["pos"]):
                        rows.append(r)
                        who.append((key(mp, top), way, i))
        res = trace(rows)
        if res is None:
            print(mp, "the plugin did not trace the lines: nothing kept", flush=True)
            continue
        seen = {}
        for (k, way, i), f in zip(who, res):
            s = seen.setdefault(k, {}).setdefault(way, {})
            s[i] = s.get(i, False) or f > 0.98
        for d in ds:
            k = key(mp, d["me"]["pos"])
            n = len(d["bots"])
            rec = {w: [bool(seen.get(k, {}).get(w, {}).get(i)) for i in range(n)] for w in ("crouched", "standing")}
            book[k] = dict(rec, title=d["title"], checked=time.strftime("%Y-%m-%d"))
            print(f"  {d['title']}: on a crouched one {sum(rec['crouched'])}/{n} in sight, on a standing one {sum(rec['standing'])}/{n}", flush=True)
        config.write_json(BOOK, book)
    print("written", BOOK, flush=True)


if __name__ == "__main__":
    main()
