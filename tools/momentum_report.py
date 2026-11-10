"""A guided Momentum campaign: each drill the guide played (runs, walks, stops, jumps and boost steps), as the drill
measured it. python tools/momentum_report.py <runs-name> [-v]"""
import collections
import json
import os
import sys

C = r"E:\CS2Server\game\csgo\coach"
OUT = r"E:\dev\cs2-coach\out\selftest"
verbose = "-v" in sys.argv
runs = json.load(open(os.path.join(OUT, f"runs_{sys.argv[1]}.json")))["sessions"]
tot = collections.Counter()
for sid in runs:
    p = os.path.join(C, "selftest", sid + ".jsonl")
    if not os.path.exists(p):
        continue
    sess = json.load(open(os.path.join(C, "sessions", sid + ".json"), encoding="utf-8"))
    info = {d["id"]: d for b in sess["blocks"] for d in b["drills"]}
    cur, rows = None, []
    for line in open(p, encoding="utf-8"):
        e = json.loads(line)
        if e["ev"] == "placed":
            cur = {"id": e.get("drill"), "map": e.get("map"), "ev": [], "out": None}
            rows.append(cur)
        elif cur is None:
            continue
        elif e["ev"] in ("guided", "mojump", "mostep", "morun", "mowalk", "mostop"):
            cur["ev"].append(e)
        elif e["ev"] == "finish":
            cur["out"] = e.get("outcome")
        elif e["ev"] == "log" and any(w in e.get("msg", "") for w in ("rror", "xception")):
            cur["ev"].append(e)
    for r in rows:
        d = info.get(r["id"]) or {}
        v = d.get("variant") or "?"
        ev = r["ev"]
        if v == "route":
            s = " ".join(f"{'ok' if x['valid'] else 'OFF'}:{x['time']}s/{x['par']}" + (f"(-{x['missed']}cp)" if x["missed"] else "") for x in ev if x["ev"] == "morun")
        elif v == "silent":
            s = " ".join(f"{'ok' if x['ok'] else 'NO'}:{x['time']}s/{x['par']} steps{x['steps']}" for x in ev if x["ev"] == "mowalk")
        elif v == "stop":
            s = " ".join(("ok" if not x["why"] else "NO") + f":{int(x['brake'] * 1000)}ms" for x in ev if x["ev"] == "mostop")
        else:
            s = " ".join((f"step{x['step']}" if x["ev"] == "mostep" else f"{'LAND' if x['ok'] else 'miss'}(off {x['off']} dz {x['dz']} {x['why'][:30]})")
                         for x in ev if x["ev"] in ("mostep", "mojump"))
            s += f" · {sum(1 for x in ev if x['ev'] == 'guided')} launches, {len(d.get('marks') or [])} rings"
        tot[(v, r["out"])] += 1
        print(f"{(r['map'] or '')[3:]:9} {v:6} {str(d.get('title'))[:34]:34} {str(r['out']):8} {s[:150]}")
        if verbose:
            for x in ev:
                print("     ", {k: x[k] for k in x if k not in ("tick", "phase", "map", "drill")})
print()
for (v, o), n in sorted(tot.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
    print(f"  {v:7} {str(o):10} {n}")
