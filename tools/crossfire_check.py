"""Crossfire's hold spots checked on the training server (23/10 eve, the user on Mirage's Window: "faut bien se rendre
compte qu'ils ne sont pas cachés à la base. Ils sont derrière absolument rien à la base. Ils sont déjà pile en face de
moi"; the base's Ts had been unseen at Top Mid behind the round's smokes, the drill has none): from each spot's eyes, the
bullet's line to each of its peeks' start, head and chest (the plugin's css_dbglos, the map's own walls); a start in
plain sight is no peek. resources/crossfire_checked.json keeps per map and spot which starts are seen; crossfire.drills
leaves those out, and a hold spot with fewer than 3 others.

    python tools/crossfire_check.py [maps] [--again]"""
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from wily.core import config  # noqa: E402
from wily.training import crossfire, replay  # noqa: E402
import lineup_check as LC  # noqa: E402

BOOK = os.path.join(HERE, "resources", "crossfire_checked.json")


REACH = {}   # the last check's: per spot, each peek seen once on its way


def key(mp, sp):
    return f"{mp}|{round(sp['pos'][0])}|{round(sp['pos'][1])}|{round(sp['pos'][2])}"


def check(mp, spots, log=print):
    """{spot key: [seen per peek]} for these spots: the bullet's lines from the spot's eyes to its body, 7 heights and its
    shoulders, all traced by the plugin in one go from a file (css_dbglosfile; 24/10: one RCON call each lost most of
    them); seen when any is clear. (23/10 eve: two bots' own spotted masks called all of Window's starts hidden, the 3 he
    saw in plain sight too: bots stopped do not spot.)"""
    import json
    rows, who = [], []
    for sp in spots:
        e = sp["pos"]
        for i, p in enumerate(sp.get("peeks") or []):
            s0 = p["path"][:3]
            dx, dy = s0[1] - e[1], -(s0[0] - e[0])
            n = max(1.0, (dx * dx + dy * dy) ** 0.5)
            for up, side in [(h, 0) for h in (66, 58, 48, 38, 28, 18, 8)] + [(52, 12), (52, -12)]:
                rows.append([round(e[0], 1), round(e[1], 1), round(e[2] + 64, 1),
                             round(s0[0] + side * dx / n, 1), round(s0[1] + side * dy / n, 1), round(s0[2] + up, 1)])
                who.append((key(mp, sp), i))
            # its way after its start, head and chest at 8 of its frames (27/10, Nuke's Squeaky: its peeks ended at Mini,
            # never once in the holder's sight, "6 sans duel" twice): a peek that never comes into sight is no peek
            P = p["path"]
            nf = len(P) // 5
            for k in sorted({int(nf * f) for f in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.99)}):
                q = P[k * 5:k * 5 + 3]
                for up in (62, 40):
                    rows.append([round(e[0], 1), round(e[1], 1), round(e[2] + 64, 1), round(q[0], 1), round(q[1], 1), round(q[2] + up, 1)])
                    who.append((key(mp, sp), ("reach", i)))
    fin, fout = os.path.join(replay.COACH, "los_in.json"), os.path.join(replay.COACH, "los_out.json")
    with open(fin, "w", encoding="utf-8") as fh:
        json.dump(rows, fh)
    t_ask = time.time()
    for _ in range(3):   # the first one may only add the bot it traces past
        replay.rcon("css_dbglosfile")
        t0 = time.time()
        while time.time() - t0 < 10:
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
        log(f"{mp}: the plugin did not trace the lines", flush=True)
        return None
    out = {key(mp, sp): [False] * len(sp.get("peeks") or []) for sp in spots}
    reach = {key(mp, sp): [False] * len(sp.get("peeks") or []) for sp in spots}
    for (k, i), f in zip(who, res):
        if f > 0.98:
            if isinstance(i, tuple):
                reach[k][i[1]] = True
            else:
                out[k][i] = True
    REACH.clear()
    REACH.update(reach)
    log(f"{mp}: {len(res)} lines traced", flush=True)
    return out


def main():
    maps = [a for a in sys.argv[1:] if not a.startswith("--")] or ["de_mirage"]
    book = config.read_json(BOOK, {}) or {}
    for mp in maps:
        spots = [sp for sp in (crossfire.load(mp, build=False) or {}).get("spots") or [] if sp.get("peeks")]
        if "--again" not in sys.argv:   # never checked, or checked before the reach was (27/10)
            spots = [sp for sp in spots if key(mp, sp) not in book or (book[key(mp, sp)] or {}).get("reach") is None]
        if not spots:
            print(mp, "nothing to check", flush=True)
            continue
        replay.start(mp)
        replay.keep()
        replay.rcon("sv_hibernate_when_empty 0")
        res = check(mp, spots)
        if res is None:
            print(mp, "the plugin did not answer every line: nothing kept", flush=True)
            continue
        for sp in spots:
            k = key(mp, sp)
            book[k] = {"seen": res[k], "reach": REACH.get(k), "zone": sp.get("zone"), "side": sp.get("side"), "checked": time.strftime("%Y-%m-%d")}
            n, s = len(res[k]), sum(res[k])
            ok = sum(1 for a, b in zip(res[k], REACH.get(k) or [True] * n) if not a and b)
            print(f"  {sp.get('side')} {sp.get('zone')} {[round(v) for v in sp['pos']]}: {s}/{n} starts in plain sight, "
                  f"{n - sum(REACH.get(k) or [True] * n)} never in sight -> {ok} peeks" + (" -> no hold drill" if ok < 3 else ""), flush=True)
        config.write_json(BOOK, book)
    print("written", BOOK, flush=True)


if __name__ == "__main__":
    main()
