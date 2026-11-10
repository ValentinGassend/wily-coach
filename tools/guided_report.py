"""A guided stuff campaign's results: each lineup drill thrown by the bot as its words say, its best pop's distance to
the target, and what its words said (technique, click, type). python tools/guided_report.py <runs-name>"""
import collections
import json
import os
import sys

C = r"E:\CS2Server\game\csgo\coach"
OUT = r"E:\dev\cs2-coach\out\selftest"
runs = json.load(open(os.path.join(OUT, f"runs_{sys.argv[1]}.json")))["sessions"]
rows = {}
for sid in runs:
    p = os.path.join(C, "selftest", sid + ".jsonl")
    if not os.path.exists(p):
        continue
    sess = json.load(open(os.path.join(C, "sessions", sid + ".json"), encoding="utf-8"))
    info = {d["id"]: d for b in sess["blocks"] for d in b["drills"]}
    cur = None
    for line in open(p, encoding="utf-8"):
        e = json.loads(line)
        if e["ev"] == "placed":
            cur = e["drill"]
        r = rows.setdefault(cur, {"map": e.get("map"), "pops": [], "outcomes": [], "throws": 0}) if cur else None
        if r is None:
            continue
        if e["ev"] == "guided":
            r["throws"] += 1
        elif e["ev"] == "pop" and e.get("guide"):
            r["pops"].append(e["dist"])
        elif e["ev"] == "finish":
            r["outcomes"].append(e["outcome"])
    for k, r in rows.items():
        if k in info:
            d = info[k]
            r.update(title=d.get("title"), type=d.get("type"), how=d.get("how"), click=d.get("click"), level=d.get("level"),
                     rush=d.get("rush", False), clip=k.startswith("clip:"))
ok = collections.Counter()
bad = []
for k, r in rows.items():
    if not r.get("type"):
        continue
    good = any(o in ("perfect", "good", "in time") for o in r["outcomes"])
    ok[(r["map"], good)] += 1
    if not good:
        bad.append((r["map"], r["type"], r.get("title"), r.get("how"), r.get("click"), min(r["pops"]) if r["pops"] else None, r["outcomes"], k))
maps = sorted({m for m, _ in ok})
tot_ok = sum(v for (m, g), v in ok.items() if g)
tot = sum(ok.values())
print(f"{tot_ok}/{tot} lineups land as their words say")
for m in maps:
    print(f"  {m:12} {ok[(m, True)]:3} ok  {ok[(m, False)]:3} fail")
print()
for b in sorted(bad, key=lambda x: (x[0], x[1])):
    print(f"{b[0]:12} {b[1]:7} {str(b[2])[:30]:30} {str(b[3])[:26]:26} {str(b[4] or '-'):6} best pop {b[5]} {b[6][:2]} {b[7][:60]}")
print(collections.Counter(b[1] for b in bad), collections.Counter((b[3] or "")[:12] for b in bad))
