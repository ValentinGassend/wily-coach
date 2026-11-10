"""Where Stuff puts you, probed on the training server (22/10, his test video: "là je suis bloqué dans le mur ... ça tu
dois le détecter pendant l'autotest", "je spawn en endroits où je suis bloqué"): each step-by-step drill's start, each
whole drill's, an entry's and a defense's spot (its post), a bot stood there and pushed 16 ways (tools/spot_probe.py);
one it can't move from at all is inside a wall or a prop. out/selftest/starts_checked.json keeps them (its "stuck" list:
tools/checks/check_training.py reads it).

    python tools/start_check.py [maps]"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from wily.core import config  # noqa: E402
from wily.training import execs, replay  # noqa: E402
import spot_probe as SP  # noqa: E402

BOOK = os.path.join(config.OUT, "selftest", "starts_checked.json")


def starts(sid, mp):
    """[(what, where)] of every Stuff block of the map."""
    out = []
    for x in execs.offer(sid, mp):
        key = x["key"]
        try:
            seq, _ = execs.sequence(sid, mp, key)
        except Exception as e:
            print(f"{mp} {key}: {e}", flush=True)
            continue
        for d in seq:
            for k in ("start",):
                if d.get(k) and len(d[k]) >= 3:
                    out.append((f"{key} {d.get('title')} (start)", d[k]))
            me = (d.get("me") or {}).get("pos")
            if me and d.get("mode") in ("entry", "hold", "exec"):
                out.append((f"{key} {d.get('title')} ({d.get('mode')})", me))
    seen, uniq = set(), []
    for w, p in out:
        k = tuple(round(v) for v in p[:3])
        if k not in seen:
            seen.add(k)
            uniq.append((w, p))
    return uniq


def main():
    maps = sys.argv[1].split(",") if len(sys.argv) > 1 else ["de_fachwerk", "de_dust2"]
    sid = str(config.settings().get("own_steamid") or "")
    book = config.read_json(BOOK, {}) or {}
    for mp in maps:
        todo = starts(sid, mp)
        replay.start(mp)
        replay.keep()
        replay.rcon("sv_hibernate_when_empty 0")
        replay.rcon("sv_cheats 1")
        replay.rcon("host_timescale 4")
        stuck = []
        try:
            for what, p in todo:
                v = SP.probe(p)
                if v is None:
                    continue
                a, n = SP.arc(v)
                if n >= 15:
                    stuck.append({"what": what, "pos": p})
                print(f"  {mp} {what[:70]:70} {'STUCK' if n >= 15 else 'ok'} ({n} blocked)", flush=True)
        finally:
            replay.rcon("host_timescale 1")
            replay.rcon("sv_cheats 0")
        book[mp] = {"checked": time.strftime("%Y-%m-%d"), "n": len(todo), "stuck": stuck}
        config.write_json(BOOK, book)
        print(f"{mp}: {len(todo)} spots, {len(stuck)} stuck", flush=True)


if __name__ == "__main__":
    main()
