"""The training tested without a player (16/10, the user: "regarde aussi comment faire toi-même ce genre de tests pour
éviter de me faire perdre du temps humain à tester tous les modes pendant autant de temps sur toutes les maps").

Each module of each map played on the training server with nobody on it (the plugin's css_selftest: no player to wait
for, the clock sped up), then what a tester looks for, read from what the plugin wrote (coach/selftest/<session>.jsonl):
- bots asked for and not there (the game refused them: "team is full");
- a bot off its way, put back on it by a teleport (a door, a box, a ceiling: what he saw as "il s'est téléporté");
- a bot standing still while its way goes on ("le bot est bloqué"), or far above or below its way ("dans le toit");
- a drill ending on its time-out (its flow stuck), errors in the log;
- Crossfire's glows made.
What needs a player's hands (shots, jumps, stops) isn't played: those parts still need him.

    python tools/train_selftest.py                      every module of every map with drills (long: hours)
    python tools/train_selftest.py --maps de_mirage --modules crossfire,defend --minutes 3 --timescale 4
    python tools/train_selftest.py --report             the report again from what the last runs wrote

Never while CS2 is open (a match, its menu, the training server with you on it): it waits, and stops if CS2 opens.
The report: out/selftest/report.html (and report.json)."""
import argparse
import collections
import html
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # run as a script: the root, for wily

from wily.core import config   # noqa: E402

OUT = os.path.join(config.OUT, "selftest")


def _client_open():
    """CS2's game (not the training server) is running."""
    try:
        import psutil
        for p in psutil.process_iter(["name", "cmdline"]):
            if (p.info.get("name") or "").lower() == "cs2.exe" and "-dedicated" not in " ".join(p.info.get("cmdline") or []):
                return True
    except Exception:
        pass
    return False


def _first_server_humans():
    """The humans on the app's own training server (its plugin's heartbeat), where his game is when it trains."""
    p = config.settings().get("cs2server") or r"E:\CS2Server"
    try:
        h = json.load(open(os.path.join(p, "game", "csgo", "coach", "live.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return (h.get("humans") or 0) if time.time() - (h.get("t") or 0) < 8 else 0


def _busy():
    """Why it can't run now (None: nobody playing): CS2's game open, a match, someone on the training server.
    On a second server (COACH_CS2PORT; 24/10: its self-test waited 2 h while the real-client tests drove his game on
    the first one), his game on the app's server is no reason: only a real match is."""
    from wily.training import replay
    beside = replay.PORT != 27015 and _first_server_humans()
    if _client_open() and not beside:
        return "CS2 is open"
    if config.in_match() and not beside:
        return "a match is going on"
    h = replay.heartbeat() or {}
    return f"{h.get('humans')} player(s) on the training server" if h.get("humans") else None


def _free():
    return _busy() is None


def _st_dir():
    from wily.training import replay
    return os.path.join(replay.CSGO, "coach", "selftest")


def _events(sid):
    f = os.path.join(_st_dir(), f"{sid}.jsonl")
    out = []
    try:
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


class Busy(Exception):
    """CS2 opened, or someone plays on the training server: the self-test waits for them."""


def run_one(sid_player, mp, module, minutes, ts, log=print, guided=False):
    """One module on one map: its session built (never in your progress), played with nobody, until its end."""
    from wily.training import replay
    from wily.training import train
    import random
    random.seed(f"{mp}|{module}")   # the same drills each run: runs compared drill for drill
    sess = train.build(sid_player, minutes, where=mp, difficulty=2, focus=module, record=False, tag="selftest")
    sid = sess["id"]
    first = sess["blocks"][0]["map"]
    n = sum(len(b["drills"]) for b in sess["blocks"])
    log(f"{mp} · {module}: session {sid}, {n} drills on {first}")
    # the situations' rounds are built from their demos behind the first one (train.build's thread, 2-4 s each): 4 times
    # faster than the game, the self-test got to one before it was ("nothing to play", 17/10): all of them first
    want = [d["id"] for b in sess["blocks"] for d in b["drills"] if d.get("kind") == "situation"]
    t_ = time.time()
    while want and time.time() - t_ < 120 and not all(os.path.exists(os.path.join(replay.SCEN, f"{w}.json")) for w in want):
        time.sleep(2)
    replay.start(first)
    replay.keep()   # nobody on it: the app's idle stop would end it mid-drill (replay.keep)
    replay.rcon("sv_hibernate_when_empty 0")
    time.sleep(1)
    replay.rcon(f"css_selftest {sid} {ts} 1" + (" guided" if guided else ""))   # guided: a bot throws the stuff as told
    t0 = time.time()
    limit = minutes * 60 / ts * (3.2 if guided else 1.6) + 180   # its game clock: sped up (less when the PC is busy; a guided one throws more)
    while time.time() - t0 < limit:
        time.sleep(5)
        replay.keep()
        why = _busy()
        if why:   # you came: the training server is yours (stopped: your game gets the PC)
            try:
                replay.rcon("css_stop")
            except OSError:
                pass
            replay.stop()
            raise Busy(f"{why}: the self-test waits")
        ev = _events(sid)
        if any(e.get("ev") == "end" for e in ev):
            log(f"  done in {time.time() - t0:.0f} s, {sum(e.get('ev') == 'finish' for e in ev)} drills played")
            return sid
    replay.rcon("css_stop")
    log(f"  stopped after {limit:.0f} s (no end)")
    return sid


# ---------- what a tester looks for ----------
STILL_V = 20.0      # u/s: a bot this slow while its way moves on is stuck
WAY_MOVES = 60.0    # u: its way moved this much in the half second
HIGH = 48.0         # u above or below its way: on a box or a ceiling, or under the floor
FAR = 150.0         # u from its way while on it


def analyze(sid):
    """{drill: findings} of one self-test session."""
    ev = _events(sid)
    res = collections.OrderedDict()

    def D(e):
        k = e.get("drill") or "?"
        if k not in res:
            res[k] = {"drill": k, "map": e.get("map"), "kind": None, "mode": None, "variant": None, "title": None, "placed": [],
                      "fixes": [], "stuck": [], "high": [], "far": [], "logs": collections.Counter(), "errors": [], "outcome": None,
                      "secs": None, "glows": 0, "samples": 0, "jumps": []}
        return res[k]
    prev = {}   # bot -> (f, want, at, speed, state)
    for e in ev:
        k = e.get("ev")
        if k == "placed":
            d = D(e)
            d.update(kind=e.get("kind"), mode=e.get("mode"), variant=e.get("variant"), title=e.get("title"))
            d["placed"].append((e.get("want"), e.get("have"), e.get("alive")))
            prev.clear()
        elif k == "fix":
            D(e)["fixes"].append(e)
        elif k == "mojump":   # a Momentum jump's try: landed or not (a guided self-test's bot makes them)
            D(e)["jumps"].append((bool(e.get("ok")), e.get("why") or "", e.get("dz")))
        elif k == "finish":
            d = D(e)
            d["outcome"], d["secs"] = e.get("outcome"), e.get("secs")
        elif k == "log":
            d = D(e)
            msg = e.get("msg") or ""
            word = msg.split(" ")[0].rstrip(":")
            d["logs"][word] += 1
            if word == "glow" and ":" not in msg.split(" ")[0]:
                d["glows"] += 1
            low = msg.lower()
            if any(w in low for w in ("error", "exception", "failed", "full", "nothing to play", "glow:", "io:")):
                d["errors"].append(msg[:200])
        elif k == "s":
            d = D(e)
            d["samples"] += 1
            for row in e.get("bots") or []:
                bot, alive, at, want, speed, state, ground = (row + [None] * 7)[:7]
                if not alive or not at or not want or state != "path":
                    prev.pop((d["drill"], bot), None)
                    continue
                dz = at[2] - want[2]
                dxy = math.hypot(at[0] - want[0], at[1] - want[1])
                if abs(dz) > HIGH and dxy < FAR and ground is not False:   # in the air (a jump, a drop): on its way to land
                    d["high"].append({"bot": bot, "at": at, "want": want, "dz": round(dz)})
                if dxy > FAR:
                    d["far"].append({"bot": bot, "at": at, "want": want, "dxy": round(dxy)})
                p = prev.get((d["drill"], bot))
                still = bool(p and speed is not None and speed < STILL_V and math.hypot(want[0] - p[0][0], want[1] - p[0][1]) > WAY_MOVES)
                n = (p[2] + 1) if (p and still) else (1 if still else 0)
                if n == 2:   # a second half second in a row: stuck (one alone is a start or a stop)
                    d["stuck"].append({"bot": bot, "at": at, "want": want, "speed": speed})
                prev[(d["drill"], bot)] = (want, at, n)
    return list(res.values())


# the modules whose drills end on their own without a player (a defense's clock, a duel nobody came to, a replayed round,
# a missed run): a time-out there is a stuck flow; a prefire or a lineup waits for the player (its time-out is expected)
SELF_ENDING = {"defend", "crossfire", "situation", "momentum"}


def _spot(p):
    return f"{p[0]:.0f} {p[1]:.0f} {p[2]:.0f}" if p else "?"


def report(sids):
    """out/selftest/report.html and report.json from the sessions' findings."""
    os.makedirs(OUT, exist_ok=True)
    rows, items = [], []
    for sid in sids:
        for d in analyze(sid):
            if d["drill"] == "?":
                continue
            missing = sum(1 for w, h, _ in d["placed"] if w and (h or 0) < w)
            row = {"session": sid, "map": d["map"], "module": d["mode"] or d["kind"], "drill": d["drill"], "title": d["title"],
                   "outcome": d["outcome"], "secs": d["secs"], "missing_bots": missing, "fixes": len(d["fixes"]), "stuck": len(d["stuck"]),
                   "high": len(d["high"]), "far": len(d["far"]), "glows": d["glows"], "errors": d["errors"][:5],
                   "landed": f"{sum(1 for ok, _, _ in d['jumps'] if ok)}/{len(d['jumps'])}" if d["jumps"] else None,
                   "logs": dict(d["logs"].most_common(8))}
            rows.append(row)
            for f in d["fixes"][:3]:
                items.append({"severity": 2 if f.get("dxy", 0) > 200 or abs(f.get("dz", 0)) > 80 else 1, "what": "put back on its way",
                              "map": d["map"], "drill": d["title"] or d["drill"], "bot": f.get("name") or f.get("bot"),
                              "where": _spot(f.get("at")), "detail": f"{f.get('dxy')} u off, {f.get('dz')} u high, at frame {f.get('f')}"})
            for s in d["stuck"][:2]:
                items.append({"severity": 2, "what": "stuck while its way goes on", "map": d["map"], "drill": d["title"] or d["drill"],
                              "bot": s["bot"], "where": _spot(s["at"]), "detail": f"{s['speed']} u/s"})
            for h in d["high"][:2]:
                items.append({"severity": 2, "what": "above or below its way", "map": d["map"], "drill": d["title"] or d["drill"],
                              "bot": h["bot"], "where": _spot(h["at"]), "detail": f"{h['dz']} u"})
            # 22/10: Fachwerk's stairs-to-window jump missed in each of the guide's tries since 20/10, "0 issues" said: a jump
            # it never lands is one nobody checked
            if len(d["jumps"]) >= 2 and not any(ok for ok, _, _ in d["jumps"]):
                whys = collections.Counter(w for _, w, _ in d["jumps"])
                items.append({"severity": 2, "what": "a jump the guide never landed", "map": d["map"], "drill": d["title"] or d["drill"],
                              "bot": "guide", "where": "", "detail": f"0/{len(d['jumps'])}: {whys.most_common(1)[0][0][:60]}, "
                                                                      f"{d['jumps'][-1][2]} u off the landing's height"})
            if missing:
                items.append({"severity": 3, "what": "bots missing", "map": d["map"], "drill": d["title"] or d["drill"], "bot": "",
                              "where": "", "detail": f"{missing} placement(s) short"})
            if d["outcome"] == "timeout" and (d["mode"] or d["kind"]) in SELF_ENDING:
                items.append({"severity": 3, "what": "ended on its time-out (stuck flow)", "map": d["map"], "drill": d["title"] or d["drill"],
                              "bot": "", "where": "", "detail": f"{d['secs']} s"})
            for err in d["errors"][:3]:
                items.append({"severity": 3, "what": "error in the log", "map": d["map"], "drill": d["title"] or d["drill"], "bot": "",
                              "where": "", "detail": err})
            if (d["mode"] == "crossfire") and d["variant"] in ("hold", "peek") and not d["glows"]:
                items.append({"severity": 2, "what": "no glow made", "map": d["map"], "drill": d["title"] or d["drill"], "bot": "",
                              "where": "", "detail": ""})
    # the places bots were put back on their way again and again, whatever the drill: a door, a narrow passage, a box
    spots = collections.Counter()
    for sid in sids:
        for d in analyze(sid):
            for f in d["fixes"]:
                at = f.get("at")
                if at:
                    spots[(d["map"], round(at[0] / 96) * 96, round(at[1] / 96) * 96, round(at[2] / 64) * 64)] += 1
    for (mp, x, y, z), n in spots.most_common():
        if n >= 4:
            items.append({"severity": 2, "what": "bots put back here again and again", "map": mp, "drill": "", "bot": "",
                          "where": f"{x} {y} {z}", "detail": f"{n} times (a door, a narrow passage, a box?)"})
    items.sort(key=lambda x: (-x["severity"], x["map"] or "", x["drill"] or ""))
    json.dump({"t": time.time(), "sessions": sids, "drills": rows, "issues": items}, open(os.path.join(OUT, "report.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    by = collections.defaultdict(lambda: collections.Counter())
    for r in rows:
        c = by[(r["map"], r["module"])]
        c["drills"] += 1
        for k in ("missing_bots", "fixes", "stuck", "high", "far", "glows"):
            c[k] += r[k]
        c["timeouts"] += r["outcome"] == "timeout"
        c["errors"] += len(r["errors"])
    E = html.escape
    head = "".join(f"<th>{h}</th>" for h in ("Map", "Module", "Drills", "Bots missing", "Put back", "Stuck", "Above/below", "Far", "Time-outs", "Errors", "Glows"))
    body = "".join(f"<tr><td>{E(str(mp))}</td><td>{E(str(md))}</td>" + "".join(f"<td class='{'bad' if c[k] and k not in ('drills', 'glows') else ''}'>{c[k]}</td>"
                                                                            for k in ("drills", "missing_bots", "fixes", "stuck", "high", "far", "timeouts", "errors", "glows")) + "</tr>"
                   for (mp, md), c in sorted(by.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))))
    lst = "".join(f"<tr class='s{i['severity']}'><td>{E(i['what'])}</td><td>{E(str(i['map']))}</td><td>{E(str(i['drill']))}</td><td>{E(str(i['bot']))}</td>"
                  f"<td><code>{E(i['where'])}</code></td><td>{E(i['detail'])}</td></tr>" for i in items[:400])
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Training self-test</title><style>
body{{font:14px system-ui,sans-serif;margin:20px;background:#0b1017;color:#e8edf4}} table{{border-collapse:collapse;margin:10px 0}}
td,th{{border:1px solid #223044;padding:4px 8px;text-align:left}} .bad{{color:#ff5d6c;font-weight:600}} .s3 td:first-child{{color:#ff5d6c}}
.s2 td:first-child{{color:#f0b54a}} code{{color:#8d99ab}}</style></head><body>
<h1>Training self-test</h1><p>{time.strftime('%d/%m %H:%M')} · {len(sids)} session(s) · {len(rows)} drills played without a player.
"Put back": the bot left its way and was teleported onto it. Positions are setpos coordinates.</p>
<h2>By map and module</h2><table><tr>{head}</tr>{body}</table>
<h2>Issues ({len(items)})</h2><table><tr><th>What</th><th>Map</th><th>Drill</th><th>Bot</th><th>Where</th><th>Detail</th></tr>{lst}</table></body></html>"""
    f = os.path.join(OUT, "report.html")
    open(f, "w", encoding="utf-8").write(page)
    return f, rows, items


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--maps", default="")
    ap.add_argument("--modules", default="")
    ap.add_argument("--minutes", type=int, default=4)
    ap.add_argument("--timescale", type=float, default=4)
    ap.add_argument("--report", action="store_true", help="the report again from the last runs")
    ap.add_argument("--resume", action="store_true", help="on with the last run: the maps and modules it played skipped")
    ap.add_argument("--guided", action="store_true", help="the stuff drills thrown by a bot as their words say (spot, aim, technique)")
    ap.add_argument("--runs", default="", help="a name of its own for this campaign's list (another one left as it is)")
    a = ap.parse_args()
    runs_f = os.path.join(OUT, f"runs_{a.runs}.json" if a.runs else "runs.json")
    os.makedirs(OUT, exist_ok=True)
    if a.report:
        sids = (config.read_json(runs_f, {}) or {}).get("sessions") or []
        f, rows, items = report(sids)
        print(f"{len(rows)} drills, {len(items)} issues: {f}")
        return
    from wily.training import train
    # 17/10, the user: "lance la partie drive en parallèle de la campagne de test": the demo archiving
    # (tools/archive_demos.py) goes on beside it (no "analysis running" mark from here)
    sid_player = str(config.settings().get("own_steamid") or "")
    maps = [m for m in a.maps.split(",") if m] or list(dict.fromkeys(list(train.maps(sid_player)) + list(train.base_maps())))
    want = [m for m in a.modules.split(",") if m] or list(train.FOCUS)
    last = config.read_json(runs_f, {}) or {}
    sids = list(last.get("sessions") or []) if a.resume else []
    done = set(last.get("done") or []) if a.resume else set()
    try:
        for mp in maps:
            counts = train.module_counts(sid_player, mp)
            for module in want:
                if not counts.get(module) or f"{mp}|{module}" in done:
                    continue
                while not _free():
                    print("CS2 is open or someone plays on the training server: waiting", flush=True)
                    time.sleep(60)
                for _ in range(20):
                    try:
                        sids.append(run_one(sid_player, mp, module, a.minutes, a.timescale, guided=a.guided))
                        done.add(f"{mp}|{module}")
                        break
                    except Busy as e:   # played again once you're done
                        print(e, flush=True)
                        while not _free():
                            time.sleep(60)
                    except KeyboardInterrupt:
                        raise
                    except Exception as e:
                        print(f"{mp} · {module}: {type(e).__name__}: {e}", flush=True)
                        break
                config.write_json(runs_f, {"sessions": sids, "done": sorted(done)})
    except KeyboardInterrupt as e:
        print(e or "stopped", flush=True)
    try:   # the training server closed again: nobody needs it now
        from wily.training import replay
        if _free():
            replay.stop()
    except Exception:
        pass
    f, rows, items = report(sids)
    print(f"{len(rows)} drills, {len(items)} issues: {f}")


if __name__ == "__main__":
    main()
