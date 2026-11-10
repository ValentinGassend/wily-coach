"""Momentum's jumps checked on the training server (17/10, the user: "notify moi quand tu auras tout testé et tout défini
comme parfaitement prêt à être testé par un humain").

    python tools/momentum_check.py [maps]           the jumps and solo boosts not checked yet, played by the guide
    python tools/momentum_check.py [maps] --again   all of them again

Each map's jump drills, all of them (not the few a session draws), in a session of their own that the guided self-test
plays (css_selftest ... guided: a bot in your place on the green ring jumps onto each ring with the game's physics, higher
and crouched after a miss: Momentum.cs MoGuideDrive). resources/momentum_checked.json keeps, per drill id, whether the guide
landed it; momentum.py leaves out the ones it never landed. Nothing else is touched."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from wily.core import config  # noqa: E402
from wily.training import crossfire, momentum, replay, train  # noqa: E402
import train_selftest as T  # noqa: E402

CHECKED = os.path.join(HERE, "resources", "momentum_checked.json")
MAPS = ["de_mirage", "de_nuke", "de_inferno", "de_dust2", "de_ancient", "de_anubis", "de_overpass", "de_train", "de_vertigo",
        "de_cache", "de_boulder", "de_fachwerk"]


def jump_drills(sid, mp):
    """Every jump drill of the map, each once (the block's builder, its order made jumps only)."""
    data = momentum.load(mp, build=False) or {}
    variants, level, out = momentum.VARIANTS, crossfire.level_of, momentum._never_landed
    momentum.VARIANTS, crossfire.level_of, momentum._never_landed = {None: ["jump"]}, (lambda s: None), set   # the ones left out too
    try:
        # the map's own (his marked ones, 20/10: counted without the map, the base's were, one of his 7 left out)
        n = len(momentum._cands(data, mp)["jump"])
        if not n:
            return []
        ds = momentum.drills(sid, mp, momentum.SECS["jump"] * n + 30, train._my_guns(sid), train.RIFLE)
    finally:
        momentum.VARIANTS, crossfire.level_of, momentum._never_landed = variants, level, out
    seen, out = set(), []
    for d in ds:
        if d["variant"] == "jump" and d["id"] not in seen:
            seen.add(d["id"])
            out.append(d)
    return out


def play(mp, drills, log=print):
    """The drills in a session of their own, played by the guide: {drill id: [landed, tries]} (a drill put on the server
    is in it even with no try: the guide never got off the ground there)."""
    sid = time.strftime("selftest_%Y%m%d_%H%M%S")
    sess = {"id": sid, "minutes": 0, "where": mp, "maps": [mp], "difficulty": 2, "level": {}, "warmup": False, "focus": "momentum",
            "blocks": [{"map": mp, "kind": "momentum", "seconds": sum(d["seconds"] for d in drills), "drills": drills}]}
    config.write_json(os.path.join(train.SESS, sid + ".json"), sess)
    replay.start(mp)
    replay.keep()
    replay.rcon("sv_hibernate_when_empty 0")
    time.sleep(1)
    replay.rcon(f"css_selftest {sid} 4 1 guided")
    t0, limit = time.time(), sum(d["seconds"] for d in drills) * 2 / 4 + 240
    while time.time() - t0 < limit:
        time.sleep(5)
        replay.keep()
        if any(e.get("ev") == "end" for e in T._events(sid)):
            break
    res, cur = {}, None
    for e in T._events(sid):
        if e.get("ev") == "placed":
            cur = e.get("drill")
            res.setdefault(cur, [0, 0])
        elif e.get("ev") == "mojump" and cur:
            res[cur][1] += 1
            res[cur][0] += bool(e.get("ok"))
    log(f"{mp}: session {sid}, {round(time.time() - t0)} s", flush=True)
    return res


def main():
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    maps = a[0].split(",") if a else MAPS
    sid = str(config.settings().get("own_steamid") or "")
    book = config.read_json(CHECKED, {}) or {}
    rows = {x["id"]: x for x in book.get("jumps") or []}
    for mp in maps:
        ds = [d for d in jump_drills(sid, mp) if "--again" in sys.argv or (rows.get(d["id"]) or {}).get("ok") is None]
        if not ds:
            print(f"{mp}: nothing to check", flush=True)
            continue
        res = play(mp, ds)
        for d in ds:
            placed = d["id"] in res
            landed, tries = res.get(d["id"], (0, 0))
            # played and no jump at all: its green ring is nowhere to stand (17/10: 45 u over the floor against a wall,
            # the guide fell off it or stuck in the wall behind it): a ring in the air for you too, left out
            rows[d["id"]] = {"id": d["id"], "map": mp, "title": d.get("title"), "boost": bool(d.get("marks")),
                             "ok": (landed > 0) if placed else None, "landed": landed, "tries": tries, "checked": time.strftime("%Y-%m-%d"),
                             **({"why": "no place to jump from"} if placed and not tries else {})}
            print(f"  {str(d.get('title'))[:34]:34} {'LANDS' if landed else 'never landed' if tries else 'no place to jump from' if placed else 'not played'}"
                  f" ({landed}/{tries})", flush=True)
        config.write_json(CHECKED, {"v": 1, "jumps": sorted(rows.values(), key=lambda x: x["id"])})


if __name__ == "__main__":
    main()
