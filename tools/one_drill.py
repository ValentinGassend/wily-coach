"""A self-test of chosen drills only: taken from an earlier session's file, put in a session of their own, played on the
training server with nobody (as tools/train_selftest.py does). python tools/one_drill.py <from-session> <drill-id>[,<id>] [reps]"""
import json
import os
import sys
import time

sys.path.insert(0, r"E:\dev\cs2-coach")
sys.path.insert(0, r"E:\dev\cs2-coach\tools")
from wily.training import replay  # noqa: E402
from wily.training import train  # noqa: E402
import train_selftest as T  # noqa: E402

src, ids = sys.argv[1], sys.argv[2].split(",")
reps = int(sys.argv[3]) if len(sys.argv) > 3 else 1
guided = "guided" in sys.argv[4:]
s = json.load(open(os.path.join(train.SESS, src + ".json"), encoding="utf-8"))
drills = [d for b in s["blocks"] for d in b["drills"] if d["id"] in ids] * reps
blk = next(b for b in s["blocks"] if any(d["id"] in ids for d in b["drills"]))
sid = time.strftime("selftest_%Y%m%d_%H%M%S")
sess = dict(s, id=sid, blocks=[dict(blk, drills=drills, seconds=max(60, 90 * len(drills)))])
json.dump(sess, open(os.path.join(train.SESS, sid + ".json"), "w", encoding="utf-8"), ensure_ascii=False)
print(sid, len(drills), "drills on", blk["map"], flush=True)
replay.start(blk["map"])
replay.keep()
replay.rcon("sv_hibernate_when_empty 0")
time.sleep(1)
replay.rcon(f"css_selftest {sid} 4 1" + (" guided" if guided else ""))
t0 = time.time()
while time.time() - t0 < 400:
    time.sleep(5)
    replay.keep()
    if any(e.get("ev") == "end" for e in T._events(sid)):
        break
print("done", round(time.time() - t0), "s", flush=True)
for e in T._events(sid):
    if e.get("ev") == "fix":
        print(e.get("why"), e["name"][:12], "f", e["f"], e["at"], "->", e["want"], "bot_v", e.get("bot_v"), "|", e.get("state"))
    if e.get("ev") == "finish":
        print("finish", e.get("drill"), e.get("outcome"))
