"""The stuff drills' words checked on the training server (17/10, the user: "fais des tests bot guidés pour les stuff en
respectant les consignes affichées pour voir si tout fonctionne").

    python tools/train_selftest.py --guided --modules nade --runs NAME    a bot throws each lineup as its words say
    python tools/lineup_check.py NAME [map]                               the ones it missed, thrown every other way
    python tools/lineup_check.py --repick                                  the ways chosen again from the throws made
    python tools/lineup_check.py --all [maps]                              every lineup the app can give, thrown as told
    python tools/lineup_check.py --all [maps] --out                        only the ones left out, thrown again (a rule changed)

A lineup the guided bot missed is thrown every way its spot and aim allow (still, jump, forward, forward + jump; a left,
a both, a right click) with the plugin's css_dbgthrow (CS2's throw as the base's flights measured it, the game flying
it). resources/lineups_checked.json then keeps, matched on the lineup's id, spot and aim: the way that lands (its words
corrected: train.py) or none (the lineup left out). Nothing else is touched; the training server is free meanwhile."""
import glob
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from wily.core import config  # noqa: E402
from wily.training import replay  # noqa: E402

OUT = os.path.join(config.OUT, "selftest")
CHECKED = os.path.join(HERE, "resources", "lineups_checked.json")
LOGS = os.path.join(replay.CSGO, "addons", "counterstrikesharp", "logs")
OK1 = {"flash": 120, "he": 120, "molotov": 120, "smoke": 70}   # the plugin's PERFECT and GOOD (Session.cs NadeResult)
OK2 = {"flash": 260, "he": 260, "molotov": 240, "smoke": 110}
HOW = {"still": "standing still", "jump": "jumpthrow", "W": "run-throw (moving forward)", "WJ": "forward + jumpthrow"}
CLICK = {"left": "left click", "both": "left + right click", "right": "right click"}


def _log_file():
    return max(glob.glob(os.path.join(LOGS, "log-CoachReplay*.txt")), key=os.path.getmtime)


def missed(runs, only=None):
    """{drill id: drill} of a guided campaign's lineups that never landed (perfect, good or in time)."""
    res = {}
    for sid in (config.read_json(os.path.join(OUT, f"runs_{runs}.json"), {}) or {}).get("sessions") or []:
        p = os.path.join(replay.COACH, "selftest", sid + ".jsonl")
        sf = os.path.join(replay.COACH, "sessions", sid + ".json")
        if not (os.path.exists(p) and os.path.exists(sf)):
            continue
        info = {d["id"]: d for b in json.load(open(sf, encoding="utf-8"))["blocks"] for d in b["drills"]}
        cur, outs = None, {}
        for line in open(p, encoding="utf-8"):
            e = json.loads(line)
            if e["ev"] == "placed":
                cur = e["drill"]
            elif e["ev"] == "finish" and cur:
                outs.setdefault(cur, []).append(e["outcome"])
        for k, o in outs.items():
            d = info.get(k)
            if d and d.get("kind") == "nade" and d.get("me") and d.get("target") and (not only or d["map"] == only) \
                    and not any(x in ("perfect", "good", "in time") for x in o):
                res[k] = d
    return res


def off(d, pop, bounces=0):
    """Why a pop near its spot is no landing (19/10, his video), None when it is one: a molotov burst in the air ("la
    molotov explose avant d'atterrir"), a smoke on another floor, a flash heard bouncing ("quand on les entend rebondir, il
    faudrait éviter de mettre ce genre de stuff"). The plugin's own rules (Session.cs NadeHit)."""
    tg = d.get("target") or []
    if d["type"] == "flash" and bounces:
        return "bounced"
    if not pop or len(pop) < 3 or len(tg) < 3:
        return None
    dz = pop[2] - tg[2]
    if d["type"] == "molotov" and dz > 64:
        return "in the air"
    if d["type"] == "smoke" and abs(dz) > 96:
        return "another floor"
    return None


def throw(d, how, click):
    """Its pop (x, y, z, bounces) thrown that way, None when it never popped, "again" when the server had no bot yet."""
    me = d["me"]
    typ = "inc" if "incgrenade" in (d.get("item") or "") else d["type"]
    f = _log_file()
    start = os.path.getsize(f)
    replay.rcon(f"css_dbgthrow {me['pos'][0]} {me['pos'][1]} {me['pos'][2]} {me['ang'][0]} {me['ang'][1]} {typ} {how} {click}"
                + (" crouch" if "crouch" in (d.get("how") or "") else ""))
    t0 = time.time()
    while time.time() - t0 < 10:
        time.sleep(0.5)
        with open(f, encoding="utf-8", errors="replace") as fh:
            fh.seek(start)
            for line in fh:
                if "dbgthrow pop" in line:
                    w = line.split("dbgthrow pop")[1].split()
                    return tuple(float(v) for v in w[1:4]) + (int(w[5]) if len(w) > 5 and w[4] == "bounces" else 0,)
                if "no bot, one added" in line:
                    return "again"
    return None


def search(d):
    """Every way thrown: [(how, click, distance or None, its pop or None, its bounces, why it is no landing)], best first."""
    tg = d["target"]
    tries = []
    for how in HOW:
        for click in CLICK:
            r = None
            for _ in range(3):
                r = throw(d, how, click)
                if r != "again":
                    break
                time.sleep(2)
            pop = [round(v) for v in r[:3]] if isinstance(r, tuple) else None
            b = r[3] if isinstance(r, tuple) else 0
            # its distance to a tenth, judged as the plugin does (21/10: 260.4 u rounded to 260 passed the GOOD zone)
            tries.append((how, click, round(math.hypot(r[0] - tg[0], r[1] - tg[1]), 1) if pop else None, pop, b, off(d, pop, b)))
    return sorted(tries, key=lambda t: (t[2] is None, t[2] or 0))


# among the ways that land, the most natural one: a still throw before a jump, a run, a left click before both, a right one
SIMPLE = [(h, c) for c in ("left", "both", "right") for h in ("still", "jump", "W", "WJ")]


def pick(tries, typ):
    """The way its words should say: the simplest one in the PERFECT zone, else the simplest in the GOOD one, else none."""
    for lim in (OK1[typ], OK2[typ]):
        ok = [(t[0], t[1], t[2]) for t in tries if t[2] is not None and t[2] <= lim and not (t[5] if len(t) > 5 else None)]
        if ok:
            return min(ok, key=lambda t: SIMPLE.index((t[0], t[1])))
    return None


def _row(k, d, tries):
    best = pick(tries, d["type"])
    near = min((t for t in tries if t[2] is not None), key=lambda t: t[2], default=None)
    crouch = " + crouching" if "crouch" in (d.get("how") or "") else ""
    row = {"id": k, "map": d["map"], "type": d["type"], "title": d.get("title"), "pos": d["me"]["pos"], "ang": d["me"]["ang"],
           "ok": bool(best), "was": [d.get("how"), d.get("click")], "dist": (best or near or [None] * 3)[2],
           "tries": [list(t) for t in tries], "checked": time.strftime("%Y-%m-%d")}
    if best:
        row.update(how=(HOW[best[0]] + crouch) if best[0] != "still" or not crouch else "crouching", click=CLICK[best[1]])
    return row


def repick():
    """The ways chosen again from the throws already made (no server)."""
    book = config.read_json(CHECKED, {}) or {}
    rows = []
    for x in book.get("lineups") or []:
        d = {"map": x["map"], "type": x["type"], "title": x.get("title"), "me": {"pos": x["pos"], "ang": x["ang"]},
             "how": (x.get("was") or [None, None])[0], "click": (x.get("was") or [None, None])[1]}
        rows.append(_row(x["id"], d, [tuple(t) for t in x.get("tries") or []]) | {"checked": x.get("checked")})
    config.write_json(CHECKED, {"v": 1, "lineups": rows})
    for r in rows:
        print(f"{r['map']:12} {r['type']:7} {str(r.get('title'))[:30]:30} -> " + (f"{r['how']} / {r['click']} ({r['dist']} u)" if r["ok"] else "none lands"))


def _args(how, click):
    """A lineup's words as css_dbgthrow's: (still|jump|W|WJ, left|both|right), as the guided bot reads them."""
    h, c = (how or "").lower(), (click or "").lower()
    mv = "forward" in h or "run" in h
    k = ("WJ" if mv else "jump") if "jumpthrow" in h else ("W" if mv else "still")
    return k, (("both" if "left" in c else "right") if "right" in c else "left")


def _pool(sid, mp, left_out=False):
    """Every lineup the app can give on that map (its stuff drills, the ones of your clips), each once (17/10: a
    correction changes what a session draws, and a lineup never drawn in a test came up missing). left_out: the ones a
    check left out instead (their check set aside meanwhile: 20/10, a flash heard bouncing off a wall was no fault)."""
    from wily.training import train
    out = {}
    keep = train._checked
    if left_out:
        train._checked = lambda *a: None
    try:
        ds = train.nade_drills(sid, mp) + train.clip_drills(sid, mp)
    finally:
        train._checked = keep
    if left_out:
        ds = [d for d in ds if d.get("me") and (keep(d["id"], d["me"]["pos"], d["me"]["ang"]) or {}).get("ok") is False]
    for d in ds:   # one per lineup and spot: two of one id from two spots both thrown (24/10, Ancient's two Flash → Mid)
        if d.get("kind") == "nade" and d.get("me") and d.get("target"):
            out.setdefault((d["id"], tuple(round(v) for v in d["me"]["pos"])), d)
    return list(out.values())


def check_all(maps):
    """Each lineup of the pool thrown once as its words say; one that misses thrown every other way (search)."""
    sid = str(config.settings().get("own_steamid") or "")
    book = config.read_json(CHECKED, {}) or {}
    rows = {(x["id"], tuple(round(v) for v in x["pos"])): x for x in book.get("lineups") or []}
    tot = bad = 0
    # --budget S: no new lineup after S seconds (21/10: run in slices in the foreground, the ones thrown today skipped
    # by the next slice)
    budget = float(sys.argv[sys.argv.index("--budget") + 1]) if "--budget" in sys.argv else None
    t0 = time.time()
    for mp in maps:
        ds = _pool(sid, mp, "--out" in sys.argv)
        replay.start(mp)
        replay.keep()
        replay.rcon("sv_hibernate_when_empty 0")
        for i, d in enumerate(ds):
            key = (d["id"], tuple(round(v) for v in d["me"]["pos"]))
            if (rows.get(key) or {}).get("checked") == time.strftime("%Y-%m-%d") and "--again" not in sys.argv and "--out" not in sys.argv:
                continue   # thrown today already
            if budget is not None and time.time() - t0 > budget:
                left = sum((rows.get((x["id"], tuple(round(v) for v in x["me"]["pos"]))) or {}).get("checked") != time.strftime("%Y-%m-%d") for x in ds[i:])
                print(f"{mp}: slice over, {left} lineups left for the next one", flush=True)
                print(f"{tot} lineups thrown, {tot - bad} as told, {bad} searched", flush=True)
                return
            replay.keep()
            k, cl = _args(d.get("how"), d.get("click"))
            r = None
            for _ in range(3):
                r = throw(d, k, cl)
                if r != "again":
                    break
                time.sleep(2)
            tg = d["target"]
            raw = math.hypot(r[0] - tg[0], r[1] - tg[1]) if isinstance(r, tuple) else None
            dist = round(raw) if raw is not None else None   # judged unrounded, as the plugin does (21/10: 260.4 u passed as 260)
            pop = [round(v) for v in r[:3]] if isinstance(r, tuple) else None
            why = off(d, pop, r[3] if isinstance(r, tuple) else 0)
            key = (d["id"], tuple(round(v) for v in d["me"]["pos"]))
            tot += 1
            if raw is not None and raw <= OK2[d["type"]] and not why:
                rows[key] = {"id": d["id"], "map": mp, "type": d["type"], "title": d.get("title"), "pos": d["me"]["pos"], "ang": d["me"]["ang"],
                             "ok": True, "was": [d.get("how"), d.get("click")], "dist": dist, "tries": [[k, cl, dist, pop, r[3], None]],
                             "checked": time.strftime("%Y-%m-%d"), "how": d.get("how"), "click": d.get("click")}
                print(f"{mp:12} {d['type']:7} {str(d.get('title'))[:30]:30} lands as told ({dist} u)", flush=True)
            else:
                bad += 1
                row = _row(d["id"], d, search(d))
                rows[key] = row
                print(f"{mp:12} {d['type']:7} {str(d.get('title'))[:30]:30} MISSED ({dist} u{', ' + why if why else ''}) -> "
                      + (f"{row['how']} / {row['click']} ({row['dist']} u)" if row["ok"] else "none lands: left out"), flush=True)
            config.write_json(CHECKED, {"v": 1, "lineups": sorted(rows.values(), key=lambda x: (x["map"], x["id"]))})
    print(f"{tot} lineups thrown, {tot - bad} as told, {bad} searched", flush=True)


def main():
    if sys.argv[1] == "--repick":
        repick()
        return
    if sys.argv[1] == "--all":
        check_all(sys.argv[2].split(",") if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else ["de_mirage", "de_nuke", "de_inferno", "de_dust2", "de_ancient", "de_anubis",
                                                                     "de_overpass", "de_train", "de_vertigo", "de_cache", "de_boulder", "de_fachwerk"])
        return
    runs = sys.argv[1]
    only = sys.argv[2] if len(sys.argv) > 2 else None
    todo = missed(runs, only)
    print(f"{len(todo)} lineups the guided bot missed", flush=True)
    book = config.read_json(CHECKED, {}) or {}
    rows = {(x["id"], tuple(round(v) for v in x["pos"])): x for x in book.get("lineups") or []}
    for k, d in sorted(todo.items(), key=lambda kv: kv[1]["map"]):
        replay.start(d["map"])
        replay.keep()   # nobody on it: the app's idle stop would end it
        replay.rcon("sv_hibernate_when_empty 0")
        row = _row(k, d, search(d))
        rows[(k, tuple(round(v) for v in d["me"]["pos"]))] = row
        print(f"{d['map']:12} {d['type']:7} {str(d.get('title'))[:30]:30} was {d.get('how')!s:26} {d.get('click') or '-':18} -> "
              + (f"{row['how']} / {row['click']} ({row['dist']} u)" if row["ok"] else f"none lands (nearest {row['dist']} u)"), flush=True)
        config.write_json(CHECKED, {"v": 1, "lineups": sorted(rows.values(), key=lambda x: (x["map"], x["id"]))})


if __name__ == "__main__":
    main()
