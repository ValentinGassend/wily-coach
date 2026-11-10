"""What real players do next, where and when (29/10, the user: "tu as besoin de te nourrir encore beaucoup plus de ce que font
les vrais joueurs dans les démos pour diriger les adversaires, mais aussi les alliés dans le plugin et dans tous les
entraînements"). From the same samples as tools/look_model.py (every 0.25 s of a live round, each living player who sees no
enemy: his 128 u cell and side, what he could know and its direction), what he did over the next second: held (under 35 u),
walked (under 140 u) or ran, and which way (8 sectors); per case, also with the numbers (more of his team alive, as many,
fewer). For each case's most common move, one real way the players took (4 s, a point each 0.25 s): the bots follow it.

Usage: python tools/move_model.py <demo or folder> [...]   ->   out/knowledge/move_model/<map>.json; exported to the plugin
(coach/move/<map>.json: per case its move, its share, its count and its way)."""
import glob
import json
import os
import sys
import time
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import look_model as L  # noqa: E402
from wily.core import config  # noqa: E402

OUT = os.path.join(config.OUT, "knowledge", "move_model")


def add(model, samples):
    for cell, know, sec, ybin, pitch, mv, adv, phase, seg in samples:
        if mv is None:
            continue
        for k in (f"{cell}|{know}|{sec}|{adv}", f"{cell}|{know}|{sec}|x"):   # with the numbers, and whatever they were
            e = model.setdefault(k, {"n": 0, "mv": {}, "seg": {}})
            e["n"] += 1
            e["mv"][mv] = e["mv"].get(mv, 0) + 1
            if mv not in e["seg"] and len(seg) >= 8:   # the first real way of that move kept (the same each time)
                e["seg"][mv] = seg


def export(mp, least=6):
    from wily.training import replay
    fn = os.path.join(OUT, f"{mp}.json")
    if not os.path.exists(fn):
        return 0
    m = json.load(open(fn, encoding="utf-8"))
    tab = {}
    for k, e in m["cells"].items():
        if e["n"] < least or not e["mv"]:
            continue
        mv, c = max(e["mv"].items(), key=lambda x: (x[1], x[0]))
        tab[k] = [mv, round(c / e["n"], 2), e["n"], e["seg"].get(mv) or []]
    d = os.path.join(replay.COACH, "move")
    os.makedirs(d, exist_ok=True)
    json.dump({"cell": L.CELL, "zcell": 96, "keys": tab}, open(os.path.join(d, f"{mp}.json"), "w", encoding="utf-8"))
    return len(tab)


def main(paths):
    try:   # below the training server and his game (a measure may be running)
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    files = []
    for a in paths:
        files += sorted(glob.glob(os.path.join(a, "*.dem"))) if os.path.isdir(a) else [a]
    os.makedirs(OUT, exist_ok=True)
    models = {}
    for f in files:
        t0 = time.time()
        try:
            mp, s = L.demo_samples(f)
        except Exception as e:
            print(os.path.basename(f), "skipped:", e, flush=True)
            continue
        if mp not in models:
            fn = os.path.join(OUT, f"{mp}.json")
            models[mp] = json.load(open(fn, encoding="utf-8")) if os.path.exists(fn) else {"demos": [], "cells": {}}
        m = models[mp]
        name = os.path.basename(f) if f.lower().endswith(".dem") else "/".join(os.path.normpath(f).split(os.sep)[-3:])
        if name in m["demos"]:
            continue
        add(m["cells"], s)
        m["demos"].append(name)
        json.dump(m, open(os.path.join(OUT, f"{mp}.json"), "w", encoding="utf-8"))
        print(f"{name} {mp}: {len(s)} moves ({time.time() - t0:.0f} s)", flush=True)
    for mp, m in models.items():
        moves = Counter()
        for k, e in m["cells"].items():
            if k.endswith("|x"):
                for mv, c in e["mv"].items():
                    moves[mv[0]] += c
        print(mp, len(m["demos"]), "demos,", len(m["cells"]), "keys, held/walked/ran:", dict(moves), "exported:", export(mp), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
