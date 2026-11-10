"""Stuff spots probed on the training server, by the game's own collisions (22/10, his test video: "le spot ... il est
censé être dans un coin, en tout cas je suis censé pouvoir me bloquer contre un mur", "c'est le long d'un mur mais pas
dans un coin"): a bot stood on each spot and pushed 16 ways (the plugin's css_dbgprobe); a way it can't go is a wall.
A corner you lock yourself into stops it on a whole arc (two walls, or a wall and a crate: 90 degrees or more); a straight
wall only on the ways straight into it (about 45 degrees: it slides along it the other ways).

    python tools/spot_probe.py <map> x,y,z [x,y,z ...]     those spots
    python tools/spot_probe.py --labels                     the spots he judged in his videos (calibration)

resources/spots_probed.json keeps each spot's 16 distances (map|x|y|z rounded); wily/training/train.py reads it."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from wily.core import config  # noqa: E402
from wily.training import replay  # noqa: E402
import lineup_check  # noqa: E402

BOOK = os.path.join(HERE, "resources", "spots_probed.json")
BLOCK = 6.0   # pushed this little along a way: a wall that way


def key(mp, p):
    return f"{mp}|{round(p[0])}|{round(p[1])}|{round(p[2])}"


def probe(p, tries=3):
    """The 16 distances from p (east first, counterclockwise), None when the plugin said nothing."""
    f = lineup_check._log_file()
    for _ in range(tries):
        start = os.path.getsize(f)
        replay.keep()
        replay.rcon(f"css_dbgprobe {p[0]} {p[1]} {p[2]}")
        t0, again = time.time(), False
        while time.time() - t0 < 12 and not again:
            time.sleep(0.5)
            with open(f, encoding="utf-8", errors="replace") as fh:
                fh.seek(start)
                for line in fh:
                    if "dbgprobe: no bot" in line or "dbgprobe: the bot is gone" in line:
                        again = True
                        break
                    tail = line.split("dbgprobe ", 1)[1] if "dbgprobe " in line else ""
                    if ":" in tail:
                        try:
                            v = [float(x) for x in tail.split(":", 1)[1].split()[:16]]
                        except ValueError:
                            continue
                        if len(v) == 16:
                            return v
        time.sleep(2)
    return None


def arc(v, block=BLOCK):
    """The widest run of ways blocked in a row (in ways of 22.5 degrees) and how many are blocked."""
    b = [x is not None and 0 <= x < block for x in v]
    if all(b):
        return 16, 16
    best = run = 0
    for i in range(32):
        run = run + 1 if b[i % 16] else 0
        best = max(best, run)
    return min(best, 16), sum(b)


def corner(v):
    """A corner you lock yourself into (22/10, calibrated on the spots he judged): 5 to 12 ways blocked in a row (his
    good ones 5 to 10, the "along a wall" ones 0 or 1), never 15 or 16 blocked (inside a wall: "je suis bloqué")."""
    a, n = arc(v)
    return 5 <= a <= 12 and n < 15


def run(mp, spots):
    book = config.read_json(BOOK, {}) or {}
    replay.start(mp)
    replay.keep()
    replay.rcon("sv_hibernate_when_empty 0")
    out = {}
    for p in spots:
        k = key(mp, p)
        v = probe(p)
        if v is None:
            print(f"  {k}: no answer", flush=True)
            continue
        book[k] = {"d": v, "checked": time.strftime("%Y-%m-%d")}
        a, n = arc(v)
        out[k] = v
        print(f"  {k}: blocked {n}/16, widest arc {a} ({'inside a wall' if n >= 15 else 'CORNER' if 5 <= a <= 12 else 'along a wall' if a >= 1 else 'open'})  {' '.join(f'{x:.0f}' for x in v)}", flush=True)
        config.write_json(BOOK, book)
    return out


def labels():
    """The spots he judged (22/10 video): good = "dans un coin", bad = along a wall, in the open, on a crate's middle."""
    from wily.training import setups
    D = config.read_json(os.path.join(HERE, "resources", "defenses.json"), {}) or {}
    T = config.read_json(os.path.join(HERE, "resources", "takes.json"), {}) or {}
    good_roles = {"TB_smoke_window", "CA_molotov", "CA_smoke_short"}
    rows = []
    for book in (D, T):
        for k, rec in book.items():
            mp = k.split("|")[0]
            for t in rec["throws"]:
                rows.append((mp, t["found"], t["pos"], t["found"] in good_roles))
    for s in setups.load("de_fachwerk") or []:
        for th in s.get("throws") or []:
            if th.get("ground") and th.get("pos"):
                rows.append(("de_fachwerk", "his:" + str(s.get("name")), th["pos"], True))
    return rows


def main():
    if sys.argv[1] == "--labels":
        rows = labels()
        by = {}
        for mp, name, p, good in rows:
            by.setdefault(mp, []).append((name, p, good))
        for mp, rs in by.items():
            res = run(mp, [p for _, p, _ in rs])
            for name, p, good in rs:
                v = res.get(key(mp, p))
                if v is None:
                    continue
                a, n = arc(v)
                print(f"{mp:11} {name[:28]:28} {'GOOD' if good else 'bad '} -> arc {a:2} blocked {n:2} {'corner' if a >= 4 else ''}", flush=True)
        return
    mp = sys.argv[1]
    run(mp, [[float(c) for c in a.split(",")] for a in sys.argv[2:]])


if __name__ == "__main__":
    main()
