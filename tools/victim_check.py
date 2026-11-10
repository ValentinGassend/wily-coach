"""The stuff drills' victims checked on the training server (19/10, his 17/10 video: "vérifie bien avec tes bots que la POV
de la personne qui subit la flash subit vraiment la flash, ou la smoke ou la molo", "la personne qui subit la smoke
c'est la personne de l'autre côté de la porte, pas celle-là").

    python tools/victim_check.py [maps]      every lineup of each map, its victims each checked by the guide

Each map's lineups, all of them (the ones a session draws from, setups included), with the victims a session gives them,
in a session of their own that the guided self-test plays: the guide throws each as its words say, then stands on each
victim's spot, turned as they are, the same grenade thrown at it again (SelfTest.cs GuideVictims): its flash time, its
health lost, a smoke between it and you. resources/victims_checked.json keeps, per lineup and victim spot, whether it
took it; train.py leaves out the ones that did not (no "from their side" at all when none did)."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from wily.core import config  # noqa: E402
from wily.training import replay, train  # noqa: E402
import train_selftest as T  # noqa: E402

CHECKED = os.path.join(HERE, "resources", "victims_checked.json")
MAPS = ["de_mirage", "de_nuke", "de_inferno", "de_dust2", "de_ancient", "de_anubis", "de_overpass", "de_train", "de_vertigo",
        "de_cache", "de_boulder", "de_fachwerk"]


def key(d):
    return train.victim_key(d["map"], d["type"], d["me"]["pos"], d["target"])


def pool(sid, mp):
    """Every lineup of the map with the victims a session gives it (a rush's runners aside), its site defenses' too
    (21/10, resources/defenses.json)."""
    from wily.training import execs
    out = []
    dfs = [m for site, rec in execs._defenses(mp).items() for m in execs._defense_members(mp, site, rec)]
    dfs += [m for site, rec in execs._wily_takes(mp).items() for m in execs._defense_members(mp, site, rec, side="T")]
    every = train._setups_of(mp, train.nade_drills(sid, mp)) + train.clip_drills(sid, mp) + dfs
    for d in every:
        if d.get("kind") != "nade" or d.get("tracks"):
            continue
        side_, t_med = d.pop("_vic", [None, None])
        d["victims"] = train._victims(mp, d["team"], d["type"], d.get("target"), d["me"]["pos"], side_, t_med, checked=False, see=d.pop("_see", None),
                                      avoid=train.exec_avoid(d, every))
        if d["victims"]:
            d["level"] = 0
            out.append(d)
    return out


def play(mp, drills):
    sid = time.strftime("selftest_%Y%m%d_%H%M%S")
    sess = {"id": sid, "minutes": 0, "where": mp, "maps": [mp], "difficulty": 2, "level": {}, "warmup": False, "focus": "nade",
            "blocks": [{"map": mp, "kind": "nade", "seconds": 40 * len(drills), "drills": drills}]}
    config.write_json(os.path.join(train.SESS, sid + ".json"), sess)
    replay.start(mp)
    replay.keep()
    replay.rcon("sv_hibernate_when_empty 0")
    time.sleep(1)
    replay.rcon(f"css_selftest {sid} 4 1 guided")
    t0 = time.time()
    while time.time() - t0 < 40 * len(drills) / 2 + 300:
        time.sleep(5)
        replay.keep()
        if any(e.get("ev") == "end" for e in T._events(sid)):
            break
    res, cur = {}, None
    for e in T._events(sid):
        if e.get("ev") == "placed":
            cur = e.get("drill")
        elif e.get("ev") in ("victim", "thrower") and cur:
            res.setdefault(cur, []).append(e)
    return sid, res


def check(mp, ds, book):
    """These lineups played by the guide, their victims and a flash's thrower recorded in book."""
    sid, res = play(mp, ds)
    hits = total = 0
    for d in ds:
        own = [e for e in res.get(d["id"]) or [] if e["ev"] == "thrower"]
        got = [e for e in res.get(d["id"]) or [] if e["ev"] == "victim"]
        if not got:
            continue
        book[key(d)] = {"map": mp, "title": d.get("title"), "type": d["type"], "checked": time.strftime("%Y-%m-%d"),
                        "victims": [{"pos": e["pos"], "hit": bool(e["hit"]), "flash": e.get("flash"), "dmg": e.get("dmg"), "cut": e.get("cut")} for e in got]}
        if own:   # a flash: its thrower blinded by it on his spot, turned to it (the place it pops sees him)
            book[key(d)]["thrower"] = {"flash": own[-1].get("flash"), "seen": bool(own[-1].get("seen"))}
            print(f"  {str(d.get('title'))[:50]:50} thrower {'SEES it' if own[-1].get('seen') else 'hidden'} ({own[-1].get('flash')} s)", flush=True)
        # a spot thrown at more than once (a molotov twice): it takes it when it took it each time
        by = {}
        for e in got:
            by.setdefault(tuple(round(c) for c in e["pos"][:2]), []).append(bool(e["hit"]))
        n = sum(all(h) for h in by.values())
        hits += n
        total += len(by)
        print(f"  {str(d.get('title'))[:50]:50} {n}/{len(by)} take it" + (f" ({sum(map(sum, by.values()))}/{len(got)} throws)" if len(got) > len(by) else ""), flush=True)
    print(f"{mp}: {hits}/{total} victims take it ({sid})", flush=True)
    config.write_json(CHECKED, book)


def main():
    maps = sys.argv[1].split(",") if len(sys.argv) > 1 else MAPS
    sid0 = str(config.settings().get("own_steamid") or "")
    book = config.read_json(CHECKED, {}) or {}
    for mp in maps:
        ds = pool(sid0, mp)
        if not ds:
            print(f"{mp}: no lineup with victims", flush=True)
            continue
        check(mp, ds, book)


if __name__ == "__main__":
    main()
