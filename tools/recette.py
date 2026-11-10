"""The recette's list (28/10, the user: "une session intensive de tous les éléments qui posent problème ... uniquement à
moi"): every drill whose latest test failed, from the battery's own logs (out/realtest/rt_bat_<map>_<focus>[_<exec>].log,
each the latest run of its block). A drill's last verdict in its log decides: ✘ goes in, ✔ stays out; one skipped (a lab's
COACH_ONLY) has none and is left as it was. Momentum is hidden from everyone: never in it.

Usage: python tools/recette.py   ->   out/realtest/recette.json ([{map, focus, exec, id, title, result}]); the app's
/api/train/recette plays it (his "recette" setting only)."""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from wily.core import config  # noqa: E402
from wily.training import train  # noqa: E402

LOGS = os.path.join(config.OUT, "realtest")
OUT = os.path.join(LOGS, "recette.json")
# its id, a place's name with spaces in it too (30/10: Crossfire's "...:CT:A Site:-720:-2151:peek" cut at its space, 14 of
# its 33 drills read), then the drill's mode as a lone word
DRILL = re.compile(r"DRILL \d+(?: \[\w+\])?: (.*) -> (.+?)(?: (?:[a-z_]+|None))?\s*$")   # a drill with no mode: "None" (30/10)
RESULT = re.compile(r"-> ([✔✘]) (.*)")


def verdicts(path, first=False):
    """{drill id: (✔ or ✘, its title, its result)} by its last verdict in that log (the recette: a drill passed on its retry
    is no problem left), or its first (the measure, 29/10: a drill failed is played again at once, "ENCORE"; his rule counts
    the try, not the second chance)."""
    out, cur = {}, None
    for ln in open(path, encoding="utf-8", errors="replace"):
        m = DRILL.search(ln)
        if m:
            cur = (m.group(2), m.group(1).strip()[:90])
            continue
        r = RESULT.search(ln)
        if r and cur and not (first and cur[0] in out):
            out[cur[0]] = (r.group(1), cur[1], r.group(2).strip()[:160])
    return out


def main():
    rows = []
    for f in sorted(glob.glob(os.path.join(LOGS, "rt_bat_*.log"))):
        tag = os.path.basename(f)[len("rt_bat_"):-len(".log")]
        parts = tag.split("_")
        if len(parts) < 2:
            continue
        mp, focus = "de_" + parts[0], parts[1]
        ex = parts[2][:-1] + ":" + parts[2][-1] if len(parts) > 2 and len(parts[2]) >= 2 else None   # CTA -> CT:A
        if focus not in train.FOCUS:   # momentum (hidden), crossfire's own runs
            continue
        for did, (v, title, res) in verdicts(f).items():
            if v == "✘":
                rows.append({"map": mp, "focus": focus, "exec": ex, "id": did, "title": title, "result": res})
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    by = {}
    for x in rows:
        by.setdefault(f"{x['map']} {x['focus']}" + (f" {x['exec']}" if x["exec"] else ""), []).append(x["id"])
    for k, v in by.items():
        print(f"{k}: {len(v)}")
    print(len(rows), "drills failed ->", OUT)


if __name__ == "__main__":
    main()
