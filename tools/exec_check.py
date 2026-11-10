"""The site takes and defenses checked on the training server (19/10, his 21:19 video: "prépare une prise de B ... l'idée
c'est d'avoir les trois stuff en même temps sur le bombsite").

    python tools/exec_check.py [maps] [keys]     T:A,T:B,CT:A,CT:B by default (each one the map has)

Each one's block as Prepare builds it (wily/training/execs.py: its lineups one by one, then all of them at once), in a
session of its own that the guided self-test plays: the guide throws each lineup as its words say, then all of them in a
row from their spots (Exec.cs ExecGuide). Says, for each, whether all of them were up on the site at the same moment and
which one was not; out/selftest/execs_checked.json keeps it (tools/checks/check_training.py reads it).
Each lineup step by step (20/10, Steps.cs): the guide goes to its spot turned away, then aims, holds the wrong clicks then
the right ones, then throws: each step must count in order, the aim not before it aims, the clicks not on the wrong ones.
Then its entry (Entry.cs): its grenades thrown for you as the whole exec's try threw them, its CTs measured, the ones to
check taken down. A defense (21/10): the same, its Ts of a real take running in through them, each taken down once it
went through its grenade's place (blinded, burned: measured)."""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from wily.core import config  # noqa: E402
from wily.training import execs, replay, train  # noqa: E402
import train_selftest as T  # noqa: E402

BOOK = os.path.join(config.OUT, "selftest", "execs_checked.json")   # per map and key: all of them up at once or not


def run(mp, key):
    sid0 = str(config.settings().get("own_steamid") or "")
    s = train.build(sid0, 10, mp, 2, "nade", record=False, tag="selftest", exec_key=key)
    sid = s["id"]
    n = sum(len(b["drills"]) for b in s["blocks"])
    replay.start(mp)
    replay.keep()
    replay.rcon("sv_hibernate_when_empty 0")
    time.sleep(1)
    replay.rcon(f"css_selftest {sid} 4 1 guided")
    t0 = time.time()
    while time.time() - t0 < 60 * n + 120:
        time.sleep(5)
        replay.keep()
        if any(e.get("ev") == "end" for e in T._events(sid)):
            break
    cur, out, pops = None, [], {}
    for e in T._events(sid):
        if e.get("ev") == "placed":
            cur = e.get("drill")
        elif e.get("ev") in ("expop", "step", "guide_step", "exec_marks") or str(e.get("ev")).startswith("entry_"):
            if cur:
                pops.setdefault(cur, []).append(e)
        elif e.get("ev") == "finish" and cur:
            out.append((cur, e.get("outcome")))
    return s, out, pops


def steps_ok(ev):
    """A step-by-step try: its steps counted in order (1 the spot, 2 the aim, 3 the clicks), the aim only once the
    guide aimed, the clicks only once it held the right ones. -> (ok, words)"""
    tries, cur, phase = [], [], None
    for e in ev:
        if e["ev"] == "guide_step":
            phase = e.get("do") or ""
            if phase.startswith("spot") and cur:
                tries.append(cur)
                cur = []
        elif e["ev"] == "step":
            cur.append((e["i"], phase))
    if cur:
        tries.append(cur)
    if not tries:
        return False, "no step counted"
    for t in tries:
        got = [i for i, _ in t]
        if got != [1, 2, 3][:len(got)] or len(got) < 3:
            return False, f"steps {got}"
        if t[1][1] not in ("aim", "wrong clicks", "right clicks"):
            return False, "the aim counted before it aimed"
        if t[2][1] != "right clicks":
            return False, f"the clicks counted on '{t[2][1]}'"
    return True, f"steps 1-2-3 in order ({len(tries)} {'try' if len(tries) == 1 else 'tries'}), the wrong clicks refused"


def main():
    maps = sys.argv[1].split(",") if len(sys.argv) > 1 else ["de_fachwerk"]
    keys = sys.argv[2].split(",") if len(sys.argv) > 2 else ["T:A", "T:B", "CT:A", "CT:B"]
    sid0 = str(config.settings().get("own_steamid") or "")
    bad = 0
    for mp in maps:
        have = {x["key"] for x in execs.offer(sid0, mp)}
        for key in keys:
            if key not in have:
                print(f"{mp} {key}: none on this map", flush=True)
                continue
            s, out, pops = run(mp, key)
            titles = {d["id"]: d["title"] for b in s["blocks"] for d in b["drills"]}
            steps = {d["id"] for b in s["blocks"] for d in b["drills"] if d.get("steps")}
            for did, o in out:
                ok = o in ("perfect", "good", "in time", "cleared", "held")
                bad += (did.startswith("exec:") or did.startswith("entry:") or key == "CT:rush") and not ok
                extra = ""
                if did.startswith("exec:"):
                    extra = " · " + ", ".join(f"{p['type']} {p['dist']} u{' ' + p['why'] if p.get('why') else ''}" for p in pops.get(did, []) if p["ev"] == "expop")
                elif did in steps:
                    sok, words = steps_ok(pops.get(did, []))
                    bad += not sok
                    ok = ok and sok
                    extra = " · " + words
                elif did.startswith("entry:"):
                    ev = pops.get(did, [])
                    plan = next((e for e in ev if e["ev"] == "entry_plan"), {})
                    thrown = [e for e in ev if e["ev"] == "entry_throw"]
                    bots = [e for e in ev if e["ev"] == "entry_bot"]
                    calls = [e for e in ev if e["ev"] == "entry_callout"]
                    if len(calls) != len(thrown):   # each grenade said in the chat (20/10)
                        bad += 1
                        ok = False
                    if plan.get("from") != "your exec":
                        bad += 1
                        ok = False
                    extra = (f" · from {plan.get('from')} at {plan.get('at')} · {len(thrown)} thrown, {len(calls)} said ({', '.join(str(c.get('place')) for c in calls)}) · "
                             + ", ".join(f"{b['zone']}{'' if b['seq'] < 0 else ' (covered)'}: blind {b['blind']} s{' hurt' if b['hurt'] else ''}{' down' if b['down'] else ''}" for b in bots))
                print(f"  {mp} {key} {'OK  ' if ok else 'MISS'} {titles.get(did, did)[:70]:70} {o}{extra}", flush=True)
            ex = [o for did, o in out if did.startswith("exec:")]
            if key == "CT:rush":   # the anti-rush: no whole exec, each grenade up before its real rush (21/10)
                ex = ["in time" if out and all(o == "in time" for _, o in out) else "late"]
                if len(out) < len({d["id"] for b in s["blocks"] for d in b["drills"]}):
                    ex = ["never ended"]
            if not ex or ex == ["never ended"]:   # never ended: the server stopped, or the drill hung
                bad += 1
                print(f"  {mp} {key} MISS {s['blocks'][0]['drills'][-1]['title'][:70]:70} never ended (the server stopped or the drill hung)", flush=True)
            book = config.read_json(BOOK, {}) or {}
            book[f"{mp}|{key}"] = {"ok": any(o in ("perfect", "good", "in time") for o in ex), "tries": ex, "session": s["id"], "checked": time.strftime("%Y-%m-%d"),
                                   "members": [d["id"] for b in s["blocks"] for d in b["drills"] if d.get("mode") not in ("exec", "entry", "hold")],
                                   "steps": all(steps_ok(pops.get(did, []))[0] for did, _ in out if did in steps),
                                   "entry": [o for did, o in out if did.startswith("entry:")],
                                   "marks": [e["marks"] for did, _ in out if did.startswith("exec:") for e in pops.get(did, []) if e["ev"] == "exec_marks"],
                                   "difficulty": s.get("difficulty")}
            config.write_json(BOOK, book)
            print(f"{mp} {key}: {s['id']}", flush=True)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
