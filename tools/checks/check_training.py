"""The training's checks for what a human found that the bots did not (19/10, the user: "il faut aussi que tu penses à
corriger tes propres vérifications pour éviter d'avoir de nouveau ce genre de problèmes"), after his 17/10 video:

- prepare: Stuff picked on the Prepare page, a Momentum session started (an older refresh of the card, answered after
  the click, drew the module picked before). A headless browser on the app's page: Momentum clicked, then Stuff, the
  Momentum answer held back 3 s, WARM-UP: the session asked for must be Stuff (the request is caught, nothing starts);
- join: "CS2 left the server while loading the map (NETWORK_DISCONNECT_LOOPSHUTDOWN)" said in red while the game was
  loading the server's new map: a map change is no refusal, an unsigned map still is;
- momentum: no dead stops ("nul à chier, aucun intérêt"), the routes only after the jumps and the silent walks;
- momentum_pick: his 19/10 23:00 video, "ce sont strictement les seuls sauts qui m'intéressent": Fachwerk's jumps are
  his, no other (the two ways onto B high, the crate of Outside Long, walked: Mid's stairs to Apps and Back of A to the
  A corridor), and no map rebuilt since has more than a few ("je ne veux pas avoir 20 ou 30 momentum à retenir");
- exposure: no stuff (a flash aside) thrown onto a place its thrower already sees ("j'envoie le stuff à un endroit que
  je vois déjà": the base's duels between the spot and the landing, 150 u around it, under 10);
- setups: a setup saved with !keep / !setup read back with its technique and its click;
- jumps: a jump chain saved with !jump read back as a Momentum drill (its rings, crouched, silent);
- victims: no "from their side" on a spot the guided bot found the grenade does nothing to (tools/victim_check.py);
- stuff_rules: his 19/10 21:19 video: no molotov bursting in the air ("la molotov explose avant d'atterrir"), no flash
  its thrower sees pop ("je flash un endroit que je vois en ligne directe"), no flash heard bouncing on the floor, a
  smoke 110 u off at most ("la smoke n'est pas bien", 129 u off and counted good): each lineup a checked map gives was
  thrown by the guide under those rules (tools/lineup_check.py, tools/victim_check.py), the ones he named are gone;
- execs: the same video's "prise de B", "exec A", "défense", "anti-rush": each site's take and defense on Fachwerk, three
  grenades or more of two kinds, four in the hands, and the guide got all of them up at once (tools/exec_check.py);
- prepare_exec: "à la place d'avoir 10 minutes, ici j'aurai exec A": Prepare's Stuff block on Fachwerk offers the takes
  and defenses instead of a time, and the session asked for is the one clicked (Exec B).

    python tools/checks/check_training.py [prepare|join|momentum|exposure|setups ...]   (all of them by default)
The app must run on 127.0.0.1:8765 for "prepare"."""
import json
import math
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from wily.core import config  # noqa: E402

MAPS = ["de_mirage", "de_nuke", "de_inferno", "de_dust2", "de_ancient", "de_anubis", "de_overpass", "de_train", "de_vertigo",
        "de_cache", "de_boulder", "de_fachwerk"]
PORT = int(os.environ.get("COACH_PORT", 8765))


def check_prepare():
    import asyncio
    from playwright.async_api import async_playwright
    sent = []

    async def run():
        async with async_playwright() as pw:
            b = await pw.chromium.launch(channel="chrome")   # the installed Chrome, headless, a profile of its own
            pg = await b.new_page()

            async def preview(route):
                if "focus=momentum" in route.request.url:
                    await asyncio.sleep(15)   # an older refresh answering after the click on another module (only this one held,
                    # longer than a plan takes to build)
                await route.continue_()

            async def session(route):
                sent.append(json.loads(route.request.post_data or "{}"))
                await route.fulfill(status=200, content_type="application/json", body=json.dumps({"blocks": [{"kind": "nade", "seconds": 600}]}))

            await pg.route("**/api/train/preview*", preview)
            await pg.route("**/api/train/session", session)
            # the app's "how did it go?" after his last session (20/10: over every click): never asked here, never answered
            # for him (his own prompt stays his)
            await pg.route("**/api/feedback/pending", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
            await pg.goto(f"http://127.0.0.1:{PORT}/prepare")
            await pg.wait_for_selector("[data-pmode=block]", timeout=60000)
            await pg.click("[data-pmode=block]")
            await pg.wait_for_selector("[data-pmap=de_fachwerk]", timeout=60000)
            await pg.click("[data-pmap=de_fachwerk]")
            await pg.wait_for_selector("[data-pfocus=nade]:not([disabled])", timeout=90000)
            await pg.click("[data-pfocus=momentum]")
            await pg.click("[data-pfocus=nade]")
            await asyncio.sleep(20)   # the held-back Momentum answer arrives meanwhile
            pressed = await pg.get_attribute("[data-pfocus=nade]", "aria-pressed")
            await pg.click("[data-pwgo]")
            for _ in range(20):
                if sent:
                    break
                await asyncio.sleep(0.5)
            await b.close()
            return pressed

    pressed = asyncio.run(run())
    if not sent:
        return False, "no session asked for"
    return sent[0].get("focus") == "nade" and pressed == "true", f"asked {sent[0].get('focus')!r}, Stuff shown pressed: {pressed}"


def check_prepare_exec():
    import asyncio
    from playwright.async_api import async_playwright
    sent = []

    async def run():
        async with async_playwright() as pw:
            b = await pw.chromium.launch(channel="chrome")
            pg = await b.new_page()

            async def session(route):
                sent.append(json.loads(route.request.post_data or "{}"))
                await route.fulfill(status=200, content_type="application/json", body=json.dumps({"blocks": [{"kind": "nade", "seconds": 600}]}))

            await pg.route("**/api/train/session", session)
            # the app's "how did it go?" after his last session (20/10: over every click): never asked here, never answered
            # for him (his own prompt stays his)
            await pg.route("**/api/feedback/pending", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
            await pg.goto(f"http://127.0.0.1:{PORT}/prepare")
            await pg.wait_for_selector("[data-pmode=block]", timeout=60000)
            await pg.click("[data-pmode=block]")
            await pg.wait_for_selector("[data-pmap=de_fachwerk]", timeout=60000)
            await pg.click("[data-pmap=de_fachwerk]")
            await pg.wait_for_selector("[data-pfocus=nade]:not([disabled])", timeout=90000)
            await pg.click("[data-pfocus=nade]")
            await pg.wait_for_selector("[data-pwex='T:B']", timeout=120000)
            durations = await pg.locator("[data-pwlen]").count()
            labels = await pg.locator("[data-pwex]").all_inner_texts()
            shown.extend([await x.get_attribute("data-pwex") for x in await pg.locator("[data-pwex]").all()])
            await pg.click("[data-pwex='T:B']")
            await pg.click("[data-pwgo]")
            for _ in range(20):
                if sent:
                    break
                await asyncio.sleep(0.5)
            await b.close()
            return durations, labels

    from wily.training import execs
    shown = []
    durations, labels = asyncio.run(run())
    if not sent:
        return False, f"no session asked for (choices: {labels})"
    # the page's choices are the map's own (execs.offer: his execs, Wily's checked ones; 22/10: no anti-rush, nothing the
    # base grouped by site on a map built again under his rules)
    want = [o["key"] for o in execs.offer(str(config.settings().get("own_steamid") or ""), "de_fachwerk")]
    ok = (sent[0].get("focus") == "nade" and sent[0].get("exec") == "T:B" and durations == 0 and shown == want
          and "CT:rush" not in shown)
    return ok, f"asked {sent[0].get('focus')!r} {sent[0].get('exec')!r}, {durations} duration buttons, choices {shown} (the map's {want}): {labels}"


def check_prepare_momentum():
    """20/10, the user: "pour la nouvelle version des entraînements Momentum, rework la façon de présenter, on n'est plus en
    fonction du temps": Prepare's Momentum block offers its jumps, its ways or all of it, no time; the one clicked is asked."""
    import asyncio
    from playwright.async_api import async_playwright
    sent = []

    async def run():
        async with async_playwright() as pw:
            b = await pw.chromium.launch(channel="chrome")
            pg = await b.new_page()

            async def session(route):
                sent.append(json.loads(route.request.post_data or "{}"))
                await route.fulfill(status=200, content_type="application/json", body=json.dumps({"blocks": [{"kind": "momentum", "seconds": 600}]}))

            await pg.route("**/api/train/session", session)
            await pg.route("**/api/feedback/pending", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
            await pg.goto(f"http://127.0.0.1:{PORT}/prepare")
            await pg.wait_for_selector("[data-pmode=block]", timeout=60000)
            await pg.click("[data-pmode=block]")
            await pg.wait_for_selector("[data-pmap=de_fachwerk]", timeout=60000)
            await pg.click("[data-pmap=de_fachwerk]")
            await pg.wait_for_selector("[data-pfocus=momentum]:not([disabled])", timeout=90000)
            await pg.click("[data-pfocus=momentum]")
            await pg.wait_for_selector("[data-pwmo=jumps]", timeout=120000)
            durations = await pg.locator("[data-pwlen]").count()
            labels = await pg.locator("[data-pwmo]").all_inner_texts()
            items = await pg.locator(".pp-items li").all_inner_texts()
            await pg.click("[data-pwmo=jumps]")
            summary = await pg.inner_text("[data-psum]")
            await pg.click("[data-pwgo]")
            for _ in range(20):
                if sent:
                    break
                await asyncio.sleep(0.5)
            await b.close()
            return durations, labels, summary, items

    durations, labels, summary, items = asyncio.run(run())
    if not sent:
        return False, f"no session asked for (choices: {labels})"
    # the jumps only (20/10: "fais disparaître tous les trajets des momentums"): his 8 on Fachwerk, no way among them
    ways = [i for i in items if not any(w in i for w in ("SAUT", "JUMP", "BOOST"))]
    ok = sent[0].get("focus") == "momentum" and sent[0].get("exec") == "jumps" and durations == 0 and len(labels) == 1 and len(items) == len(HIS_JUMPS) and not ways
    return ok, f"asked {sent[0].get('focus')!r} {sent[0].get('exec')!r}, {durations} duration buttons, choices {[l.splitlines()[0] for l in labels]}, {len(items)} listed{', ways: ' + str(ways) if ways else ''}, card: {summary!r}"


def check_weapon():
    """20/10, the user: "il faudrait pouvoir choisir son arme (ak, m4a4, m4a1s, usp, glock, deagle, awp)": each choice in
    the blocks fought with one, a rifle in the main one's place (a pistol round stays one), a pistol alone; Stuff untouched;
    and Prepare sends the one clicked."""
    from wily.training import train
    bad = []
    for k, w in train.WEAPONS.items():
        for ws in (["weapon_knife", "weapon_glock", "weapon_ak47"], ["weapon_knife", "weapon_usp_silencer"], ["weapon_ak47", "weapon_knife"], ["weapon_smokegrenade"]):
            got = train._swap(ws, w)
            if ws == ["weapon_smokegrenade"]:
                want = ws
            elif w in train.PISTOLS:
                want = [x for x in ws if x == "weapon_knife" or x == ws[[i for i, y in enumerate(ws) if y != "weapon_knife"][0]]]
                want = [w if x != "weapon_knife" else x for x in want]
            else:
                want = [w if x == "weapon_ak47" else x for x in ws]
            if got != want:
                bad.append(f"{k} on {ws}: {got}")
    import asyncio
    from playwright.async_api import async_playwright
    sent = []

    async def run():
        async with async_playwright() as pw:
            b = await pw.chromium.launch(channel="chrome")
            pg = await b.new_page()

            async def session(route):
                sent.append(json.loads(route.request.post_data or "{}"))
                await route.fulfill(status=200, content_type="application/json", body=json.dumps({"blocks": [{"kind": "defend", "seconds": 600}]}))

            await pg.route("**/api/train/session", session)
            await pg.route("**/api/feedback/pending", lambda r: r.fulfill(status=200, content_type="application/json", body="{}"))
            await pg.goto(f"http://127.0.0.1:{PORT}/prepare")
            await pg.wait_for_selector("[data-pmode=block]", timeout=60000)
            await pg.click("[data-pmode=block]")
            await pg.wait_for_selector("[data-pmap=de_fachwerk]", timeout=60000)
            await pg.click("[data-pmap=de_fachwerk]")
            await pg.wait_for_selector("[data-pfocus=nade]:not([disabled])", timeout=90000)
            await pg.click("[data-pfocus=nade]")   # Stuff first: no weapon to pick there, once its site takes are shown
            await pg.wait_for_selector("[data-pchoice] [data-pwex]", timeout=120000)
            on_stuff = await pg.locator("[data-pwgun]").count()
            await pg.wait_for_selector("[data-pfocus=defend]:not([disabled])", timeout=90000)
            await pg.click("[data-pfocus=defend]")
            await pg.wait_for_selector("[data-pwgun=awp]", timeout=60000)
            await pg.click("[data-pwgun=awp]")
            card = await pg.inner_text(".pp-sum-what")
            await pg.click("[data-pwgo]")
            for _ in range(20):
                if sent:
                    break
                await asyncio.sleep(0.5)
            await b.close()
            return card, on_stuff

    card, on_stuff = asyncio.run(run())
    if not sent or sent[0].get("weapon") != "awp" or sent[0].get("focus") != "defend":
        bad.append(f"asked {sent[:1]}")
    if "AWP" not in card:
        bad.append(f"the card says {card!r}")
    if on_stuff:
        bad.append("a weapon to pick on a Stuff block")
    return not bad, "; ".join(bad[:4]) or f"7 weapons swapped right in every kind of loadout; Prepare sent the AWP ({card.strip()}), none offered on Stuff"


def check_jumpthrow():
    """20/10, his 12:32 video: "tous les stuffs envoyés en jumpthrow ont le mauvais repère visuel et de position ... le
    repère de position est un peu trop haut, au moment où j'envoie ma grenade il est en l'air": each jumpthrow of his
    setups stands on the floor where he stood to aim before he jumped: within 4 u of his own standing throws from the
    same corner (coach/throws.jsonl, 24 u around)."""
    from wily.training import setups
    # his throws are on the app's own server, wherever the checks run (24/10: run on the second one, COACH_CS2SERVER,
    # they read its throws, none of his)
    coach = os.path.join(config.settings().get("cs2server") or r"E:\CS2Server", "game", "csgo", "coach")
    T = [json.loads(ln) for ln in open(os.path.join(coach, "throws.jsonl"), encoding="utf-8") if ln.strip()]
    floor = [t["pos"] for t in T if t.get("ground") and not t.get("test")]
    bad, n = [], 0
    for su in setups.load("de_fachwerk"):
        for t in su["throws"]:
            if t.get("ground", True):
                continue
            z = [p[2] for p in floor if math.dist(p[:2], t["pos"][:2]) <= 24]
            if not z:
                continue
            n += 1
            got = setups.stand_pos(t)[2]
            if abs(got - min(z)) > 4:
                bad.append(f"{su['name']} {t['type']}: {got} for a floor at {min(z)}")
    if not n:
        return False, "no jumpthrow of his with a standing throw from the same corner"
    return not bad, "; ".join(bad[:4]) or f"{n} jumpthrows of his setups on the floor, within 4 u of where he stands there"


def check_join():
    from wily.training import train
    f = os.path.join(tempfile.mkdtemp(), "console.log")
    train._console = lambda: f
    cut = "Disconnection during connection phase. Sign-on state: 5 (SIGNONSTATE_SPAWN). Disconnect reason: NETWORK_DISCONNECT_LOOPSHUTDOWN\n"
    bad = "Disconnection during connection phase. Sign-on state: 3 (SIGNONSTATE_CONNECTED). Disconnect reason: NETWORK_DISCONNECT_KICKED\n"
    sig = "Signature failed for maps/aim_map.vpk\n" + bad
    out = []
    ws = "Signature failed for E:\\SteamLibrary\\steamapps\\workshop\\content\\730\\3802004803\\3802004803.vpk (reason: 0)\n"
    user = "Disconnection during connection phase. Sign-on state: 3 (SIGNONSTATE_NEW). Disconnect reason: NETWORK_DISCONNECT_DISCONNECT_BY_USER.\n"
    for text, want_none in ((cut, True), (bad, False), (sig, False), (cut + bad, False), (ws + user, True), (ws + cut, True), (ws + bad, False)):
        open(f, "w", encoding="utf-8").write(text)
        r = train._refused_since(0)
        out.append((r is None) == want_none)
    return all(out), f"{sum(out)}/{len(out)} console cases read right"


def check_momentum():
    from wily.training import crossfire, momentum, train
    sid = str(config.settings().get("own_steamid") or "")
    level = crossfire.level_of
    bad = []
    try:
        for lv in (None, "inter", "debut"):
            crossfire.level_of = lambda s, lv=lv: lv
            for mp in MAPS:
                ds = momentum.drills(sid, mp, 1200, train._my_guns(sid), train.RIFLE)
                vs = [d["variant"] for d in ds]
                if "stop" in vs:
                    bad.append(f"{mp} {lv}: a dead stop")
                if {"route", "silent"} & set(vs):   # 20/10, the user: "fais disparaître tous les trajets des momentums"
                    bad.append(f"{mp} {lv}: a way ({', '.join(sorted({'route', 'silent'} & set(vs)))})")
                if "route" not in vs:
                    continue
                i = vs.index("route")   # no jump nor walk given for the first time after a route
                first = {}
                for k, d in enumerate(ds):
                    first.setdefault(d["id"], k)
                late = [d["title"] for d in ds if d["variant"] != "route" and first[d["id"]] > i]
                if late:
                    bad.append(f"{mp} {lv}: {late[0]} only after a route")
    finally:
        crossfire.level_of = level
    return not bad, "; ".join(bad[:4]) or "no dead stop, no way (timed run, rotation, silent walk-in): the jumps only"


# Fachwerk's jumps as he showed them (20/10, rush/20261020_blockout_023626.mp4: a smoke where each starts, one where it
# lands): where each lands, walked or not. 19/10's reading of his 23:00 video was wrong on 5 of them (the B high one
# ended on the cart, both silent ones elsewhere): the check holds his own marks now
HIS_JUMPS = {"B high from the cart": ([1293, -421, 11], [1435, -210, 2], False), "B high by the low wall": ([1260, -224, -46], [1434, -210, 2], False),
             "Mid's stairs to the window": ([37, 118, 64], [73, -49, 130], True), "anti-push boost": ([356, 888, -2], [515, 940, 14], False),
             "Long's crate to crate": ([-837, 52, 96], [-1078, 50, 95], False), "behind the corridor": ([-1152, -1647, -13], [-1267, -1553, 7], True),
             "B's high point": ([1028, -615, 8], [1187, -756, 26], False),
             "the anti-push, one jump further": ([508.8, 946.5, 13.9], [409, 1128.3, 56], False)}   # 20/10 22:27, an HE at each end   # where he stood when he dropped each smoke: takeoff, landing, walked


def check_momentum_pick():
    from wily.training import momentum, train
    sid = str(config.settings().get("own_steamid") or "")
    bad = []
    for mp in MAPS:
        data = momentum.load(mp, build=False) or {}
        if not data.get("strong") and not momentum.his(mp):
            continue
        C = momentum._cands(data, mp)
        js = [x for _, x in C["jump"] if not x.get("mine")]
        if len(js) > max(momentum.STRONG_MAX, len(momentum.his(mp))):
            bad.append(f"{mp}: {len(js)} jumps")
        ds = momentum.drills(sid, mp, 3600, train._my_guns(sid), train.RIFLE)
        n = len({d["id"] for d in ds})
        if n > 16:
            bad.append(f"{mp}: {n} Momentum drills")
        if mp != "de_fachwerk":
            continue
        near = lambda x: min(HIS_JUMPS, key=lambda k: math.dist(x["from"], HIS_JUMPS[k][0]) + math.dist(x["to"], HIS_JUMPS[k][1]))
        for name, (frm, land, walk) in HIS_JUMPS.items():
            got = [x for x in js if near(x) == name and math.dist(x["to"][:2], land[:2]) <= 32 and math.dist(x["from"][:2], frm[:2]) <= 32]
            if len(got) != 1:
                bad.append(f"{name}: {len(got)} drills")
            elif walk and got[0].get("how") != "walk":
                bad.append(f"{name}: not walked")
        for x in js:
            if not any(math.dist(x["to"][:2], l[:2]) <= 32 for _, l, _ in HIS_JUMPS.values()):
                bad.append(f"another jump: {x['zone']} {[round(v) for v in x['to']]}")
        walk = [d for d in ds if d["variant"] == "jump" and d.get("how") == "walk"]
        if any("Shift" not in d["tip"] and "Maj" not in d["tip"] for d in walk):
            bad.append("a silent jump's words don't say to walk")
    return not bad, "; ".join(bad[:5]) or f"Fachwerk's jumps are his {len(HIS_JUMPS)} as he marked them, the silent ones walked; no map with too many"


def check_exposure():
    from wily.training import train
    sid = str(config.settings().get("own_steamid") or "")
    bad = []
    for mp in MAPS:
        for d in train.nade_drills(sid, mp):
            if d["type"] == "flash" or not d.get("target"):
                continue
            land, pos = d["target"], d["me"]["pos"]
            l3 = land if len(land) >= 3 else [land[0], land[1], pos[2]]
            n = train._exposed(mp, pos, l3, 150, 120)
            if n >= 10:
                bad.append(f"{mp} {d['title']} ({n})")
    return not bad, "; ".join(bad[:4]) or "no stuff thrown onto a place its thrower sees"


def check_setups():
    from wily.training import setups
    f = os.path.join(tempfile.mkdtemp(), "setups.jsonl")
    t0 = {"type": "smoke", "team": 2, "pos": [-1161.3, -462.5, 0.0], "ang": [-52.66, -112.35], "vel": [0, 0, 0], "ground": True,
          "duck": 0, "nade_v": [-200, -480, 560], "pop": [1395, -767, 10]}
    t1 = dict(t0, ang=[-40, -100], vel=[0, 0, 280], ground=False, nade_v=[-120, -650, 600])
    t2 = dict(t0, type="molotov", duck=0.9, nade_v=[0, -430, 80])
    t3 = dict(t0, type="flash", nade_v=[30, -190, 110])
    yaw = math.radians(-112.35)
    t4 = dict(t0, vel=[200 * math.cos(yaw), 200 * math.sin(yaw), 0])
    rec = {"t": 1, "name": "check", "map": "de_fachwerk", "throws": [t0, t1, t2, t3, t4]}
    open(f, "w", encoding="utf-8").write(json.dumps(rec) + "\n" + json.dumps(dict(rec, name="bot", test=True)) + "\n")
    keep = setups._file
    setups._file = lambda: f
    try:
        ds = setups.drills("de_fachwerk")
        tests = setups.drills("de_fachwerk", test=True)
    finally:
        setups._file = keep
    got = [(d["how"], d["click"]) for d in ds]
    want = [("standing still", "left click"), ("jumpthrow", "left click"), ("crouching", "left + right click"),
            ("standing still", "right click"), ("run-throw (moving forward)", "left click")]
    ok = got == want and len(tests) == 5 and all(d["clip"] == ds[0]["clip"] for d in ds)
    return ok, f"read {got}" if not ok else "5 throws read back right, the test setup kept apart"


def check_jumps():
    from wily.training import momentum, replay
    d = tempfile.mkdtemp()
    rec = {"t": 2, "name": "heaven from B", "map": "de_fachwerk", "team": 2, "jumps": [
        {"from": [1300, -400, -90], "to": [1320, -380, -30], "speed": 90, "slow": True, "duck": 0.9, "air": 0.6},
        {"from": [1322, -378, -30], "to": [1340, -300, 30], "speed": 60, "slow": True, "duck": 0.2, "air": 0.5}]}
    open(os.path.join(d, "jumps.jsonl"), "w", encoding="utf-8").write(json.dumps(rec) + chr(10))
    keep = replay.COACH
    replay.COACH = d
    try:
        m = momentum.mine("de_fachwerk")
    finally:
        replay.COACH = keep
    ok = len(m) == 1 and m[0]["steps"] == 2 and m[0]["marks"] == [[1320, -380, -30]] and m[0]["how"] == "duck" and m[0]["slow"] == 1.0         and m[0]["hard"] == 3
    return ok, "a saved chain of 2 jumps read back: its ring, crouched, silent" if ok else f"read {m}"


def check_victims():
    from wily.training import train
    book = config.read_json(train.VICTIMS_CHECKED, {}) or {}
    if not book:
        return False, "no victim checked yet (python tools/victim_check.py)"
    sid = str(config.settings().get("own_steamid") or "")
    bad, n = [], 0
    for mp in sorted({r["map"] for r in book.values()}):
        for d in train._setups_of(mp, train.nade_drills(sid, mp)) + train.clip_drills(sid, mp):
            if d.get("kind") != "nade" or d.get("tracks"):
                continue
            side_, t_med = d.pop("_vic", [None, None])
            vs = train._victims(mp, d["team"], d["type"], d.get("target"), d["me"]["pos"], side_, t_med)
            rec = book.get(train.victim_key(mp, d["type"], d["me"]["pos"], d["target"]))
            for v in vs:
                n += 1
                if rec and any(not c["hit"] and math.dist(c["pos"][:2], v["pos"][:2]) < 24 for c in rec["victims"]):
                    bad.append(f"{mp} {d['title']}")
    return not bad, "; ".join(bad[:4]) or f"{n} victims shown, none the bot found untouched"


# the lineups he found wrong in his 19/10 21:19 video (Fachwerk): the molotov that burst in the air, the two flashes thrown
# onto a place their thrower sees
HIS_BAD_STUFF = {"nade:de_fachwerk:T:molotov:LongA>BombsiteA": "burst in the air", "nade:de_fachwerk:CT:flash:Short>LongA": "seen by its thrower",
                 "nade:de_fachwerk:T:flash:LongA>LongA": "seen by its thrower"}


def check_stuff_rules():
    from wily.training import train
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import lineup_check
    bad = []
    if lineup_check.OK2["smoke"] != 110 or lineup_check.OK1["smoke"] != 70:
        bad.append("lineup_check's smoke zone is not the plugin's")
    if "_ => (70, 110)" not in open(os.path.join(ROOT, "plugin", "CoachReplay", "Session.cs"), encoding="utf-8").read():
        bad.append("the plugin's smoke zone is not 70 / 110 u")
    sid = str(config.settings().get("own_steamid") or "")
    book = config.read_json(lineup_check.CHECKED, {}) or {}
    # the maps thrown again under these rules (a try's bounces and why it is no landing kept): Fachwerk first, then one
    # map, then all (his way, 19/10)
    maps = sorted({x["map"] for x in book.get("lineups") or [] if any(len(t) >= 6 for t in x.get("tries") or [])} & set(MAPS))
    if not maps:
        return False, "no map thrown under these rules yet (python tools/lineup_check.py --all de_fachwerk --again)"
    n = 0
    for mp in maps:
        ds = [d for d in train.nade_drills(sid, mp) + train.clip_drills(sid, mp) if d.get("kind") == "nade" and d.get("me")]
        for d in ds:
            n += 1
            if d["id"] in HIS_BAD_STUFF:
                bad.append(f"{d['title']}: {HIS_BAD_STUFF[d['id']]}")
            elif not d["id"].startswith("setup:") and not train._checked(d["id"], d["me"]["pos"], d["me"]["ang"]):
                bad.append(f"{mp} {d['title']}: never thrown by the guide")
            if d["type"] == "flash" and not d["id"].startswith("setup:") and train._thrower_sees(mp, "flash", d["me"]["pos"], d["target"]):   # his own: his call
                bad.append(f"{mp} {d['title']}: its thrower sees it pop")
    return not bad, "; ".join(bad[:5]) or f"{n} lineups on {', '.join(maps)}: each thrown under his rules, none he named"


def check_execs():
    from wily.training import execs
    sid = str(config.settings().get("own_steamid") or "")
    mp = "de_fachwerk"
    P = execs.plan(sid, mp)
    bad, said = [], []
    for key in ("T:A", "T:B", "CT:A", "CT:B"):
        x = P.get(key)
        if not x:   # a defense needs three lineups from spots you find again (20/10): none is a fault only for the takes
            if key.startswith("T:"):
                bad.append(f"no {key}")
            continue
        said.append(key)
        ms = x["members"]
        kinds = {m["type"] for m in ms}
        e = execs.drill(mp, x)
        if len(ms) < 3 or len(kinds) < 2 or len(e["weapons"]) > execs.HAND:
            bad.append(f"{key}: {len(ms)} grenades, {len(kinds)} kinds, {len(e['weapons'])} in the hands")
        rec = (config.read_json(os.path.join(config.OUT, "selftest", "execs_checked.json"), {}) or {}).get(f"{mp}|{key}")
        if not rec:
            bad.append(f"{key}: never played by the guide (tools/exec_check.py)")
        elif rec["members"] != [m["id"] for m in ms]:
            bad.append(f"{key}: changed since the guide played it")
        elif not rec["ok"]:
            bad.append(f"{key}: the guide never got all of them up at once ({', '.join(rec['tries'])})")
    return not bad, "; ".join(bad[:5]) or f"Fachwerk's {', '.join(said)}: all of them up at once by the guide"


def check_exec_steps():
    """20/10, his 16:24 video: an exec learnt stuff by stuff, each one step by step from near its spot ("je ne dois pas
    apparaître déjà au bon endroit ... tu détectes que je suis dans la bonne position ... viser ... les clics ... le
    mouvement"), then all of them, then as its entry with unarmed CTs ("quelles lignes décalent"): Fachwerk's takes each
    start 150 to 260 u from their spot, the guide's steps counted in order and never on a wrong aim or wrong clicks, its
    entry with spots to check and covered ones, thrown as the whole exec's try threw them, cleared."""
    from wily.training import execs
    sid = str(config.settings().get("own_steamid") or "")
    mp = "de_fachwerk"
    bad, said = [], []
    book = config.read_json(os.path.join(config.OUT, "selftest", "execs_checked.json"), {}) or {}
    for key in ("T:A", "T:B"):
        out, _ = execs.sequence(sid, mp, key)
        steps = [d for d in out if d.get("steps")]
        en = [d for d in out if d.get("mode") == "entry"]
        if not steps or not en:
            bad.append(f"{key}: {len(steps)} step drills, {len(en)} entry")
            continue
        for d in steps:
            st = d.get("start")
            if not st or not 140 <= math.dist(st[:2], d["me"]["pos"][:2]) <= 270:
                bad.append(f"{key} {d['title'][-30:]}: start {st}")
        b = en[0]["bots"]
        if not any(x["seq"] < 0 for x in b) or not any(x["seq"] >= 0 for x in b):
            bad.append(f"{key}: entry bots {[(x['zone'], x['seq']) for x in b]}")
        ex = next(d for d in out if d.get("mode") == "exec")
        if not ex.get("start") or not 140 <= math.dist(ex["start"][:2], ex["me"]["pos"][:2]) <= 270:
            bad.append(f"{key}: the whole exec starts on its first spot ({ex.get('start')})")
        rec = book.get(f"{mp}|{key}") or {}
        if (rec.get("difficulty") or 0) >= 2 and any(rec.get("marks") or [True]):
            bad.append(f"{key}: marks drawn at difficulty {rec.get('difficulty')} ({rec.get('marks')})")
        if not rec.get("steps"):
            bad.append(f"{key}: the guide's steps not counted right (tools/exec_check.py)")
        if "cleared" not in (rec.get("entry") or []):
            bad.append(f"{key}: entry {rec.get('entry')}")
        said.append(f"{key} {len(steps)} step drills, entry {sum(x['seq'] < 0 for x in b)} to check / {sum(x['seq'] >= 0 for x in b)} covered")
    # his execs' entries: his CTs (20/10, an HE at each), each on the base's take spot 80 u of it at most (one tuned by hand
    # where it was), the base's most met ones added (3 at most), none in a smoke; his molotov's own covered by it
    for site in ("A", "B"):
        out, _ = execs.sequence(sid, mp, f"T:{site}")
        en = next(d for d in out if d.get("mode") == "entry")
        bots, ms = en["bots"], en["members"]
        his = (config.read_json(execs.ENTRY_F, {}) or {}).get(f"{mp}|{site}") or []
        mine = [b for b in bots if b.get("his")]
        smokes = [m["target"] for m in ms if m["type"] == "smoke"]
        if len(mine) != len(his):
            bad.append(f"exec {site}'s entry: {len(mine)} of his {len(his)} CTs")
        for b, h in zip(mine, his):
            if math.dist(b["pos"][:2], h["pos"][:2]) > (0.5 if h.get("fixed") else 80):
                bad.append(f"exec {site}'s entry: {h.get('name') or h['pos']} moved {round(math.dist(b['pos'][:2], h['pos'][:2]))} u")
            if h.get("by") and (b["seq"] < 0 or ms[b["seq"]]["type"] != h["by"]):
                bad.append(f"exec {site}'s entry: {h.get('name')} not covered by its {h['by']}")
        if len(bots) - len(mine) > 3:
            bad.append(f"exec {site}'s entry: {len(bots) - len(mine)} CTs added")
        for b in bots:
            if b["seq"] < 0 and any(math.dist(b["pos"][:2], t[:2]) < 150 for t in smokes):
                bad.append(f"exec {site}'s entry: {b['zone']} inside a smoke")
        said.append(f"entry {site}: {len(mine)} his + {len(bots) - len(mine)} from the base")
    # his exec B: his flash of 16:42 (from his molotov spot, jumpthrow, left + right click)
    x = execs.plan(sid, mp).get("T:B") or {}
    fl = [m for m in x.get("members") or [] if m["type"] == "flash"]
    if not fl or math.dist(fl[0]["me"]["pos"][:2], [1578.8, 608.6]) > 4 or fl[0]["how"] != "jumpthrow" or fl[0]["click"] != "left + right click":
        bad.append(f"exec B's flash is not his of 16:42: {[(m['me']['pos'], m['how'], m['click']) for m in fl]}")
    return not bad, "; ".join(bad[:5]) or " · ".join(said) + " · steps in order, wrong clicks refused, entries cleared"


def check_defenses():
    """21/10, the user: "finis les stuff de Fachwerk pour la partie défensive, histoire de tester si tu as bien compris ce
    que je voulais et si tu sais l'appliquer et le contrôler par toi-même": Fachwerk's defenses of A and B, Wily's own
    (resources/defenses.json), held to his rules: each grenade from a spot with a wall by it (one you find again), a
    smoke never on the defense's own molotov, each one's victims taking it (the base's Ts there at its moment), a flash
    never seen by its thrower, then the guide: each one step by step in order, all of them up before the base's fast takes
    are on the site, then held as its defender against a real take's Ts."""
    from wily.training import execs, train
    sid = str(config.settings().get("own_steamid") or "")
    mp = "de_fachwerk"
    bad, said = [], []
    vic = config.read_json(os.path.join(config.HERE, "resources", "victims_checked.json"), {}) or {}
    book = config.read_json(os.path.join(config.OUT, "selftest", "execs_checked.json"), {}) or {}
    P = execs.plan(sid, mp)
    rebuilt = execs._rebuilt(mp)
    for site in ("A", "B"):
        rec = execs._defenses(mp).get(site)
        x = P.get(f"CT:{site}")
        if x and x.get("mine"):   # his own (a setup saved with !setup): checked as his (check_setups)
            said.append(f"{site} yours")
            continue
        if not x and rebuilt:
            # 22/10, built again under his rules (tools/stuff_build.py: from corners on the site, out of sight, real
            # throws): no site of the map reaching three of them, none offered rather than one he would not take
            said.append(f"{site} none (no 3 grenades from the site's corners)")
            continue
        if not rec or not x or not x.get("rec"):
            bad.append(f"no defense of {site}" if not x else f"defense {site}: offered, never built nor checked by Wily")
            continue
        ms = x["members"]
        if len(ms) < 3 or len({m["type"] for m in ms}) < 3:
            bad.append(f"defense {site}: {len(ms)} grenades, {len({m['type'] for m in ms})} kinds")
        fires = [m["target"] for m in ms if m["type"] == "molotov"]
        for m in ms:
            if not train.spot_walls(mp, m["me"]["pos"])["ok"]:
                bad.append(f"defense {site} {m['type']}: an open spot {m['me']['pos']}")
            if m["type"] == "smoke" and any(math.dist(m["target"], f) < 220 for f in fires):
                bad.append(f"defense {site}: its smoke on its molotov")
            v = vic.get(train.victim_key(mp, m["type"], m["me"]["pos"], m["target"]))
            if not v:
                bad.append(f"defense {site} {m['type']}: its victims never checked (tools/victim_check.py)")
            elif m["type"] != "smoke" and not any(e["hit"] for e in v["victims"]):
                bad.append(f"defense {site} {m['type']}: none of its {len(v['victims'])} victims takes it")
            elif m["type"] == "flash" and (v.get("thrower") or {}).get("seen"):
                bad.append(f"defense {site}: its flash blinds its thrower ({v['thrower'].get('flash')} s)")
        r = book.get(f"{mp}|CT:{site}") or {}
        if not r:
            bad.append(f"defense {site}: never played by the guide (tools/exec_check.py)")
        else:
            if r.get("members") != [m["id"] for m in ms]:
                bad.append(f"defense {site}: changed since the guide played it")
            if not r.get("ok"):
                bad.append(f"defense {site}: never all up before they are on the site ({', '.join(r.get('tries') or [])})")
            if not r.get("steps"):
                bad.append(f"defense {site}: the guide's steps not counted right")
            if "held" not in (r.get("entry") or []):
                bad.append(f"defense {site}: as its defender {r.get('entry')}")
        said.append(f"{site} {'+'.join(m['type'] for m in ms)} up within {rec['arrive']} s")
    return not bad, "; ".join(bad[:6]) or "Fachwerk's defenses " + " · ".join(said) + ": none offered that he would not take"


def check_no_rush():
    """22/10, his test video: "sincèrement, pour l'instant fais disparaître toutes les parties anti-rush ... si je ne te
    dis pas l'inverse, fais disparaître les parties anti-rush": no anti-rush drill in Stuff, no anti-rush block in
    Prepare, on any map with lineups, and no base's grenades grouped by site on a map built again under his rules."""
    from wily.training import execs, train
    sid = str(config.settings().get("own_steamid") or "")
    bad, n = [], 0
    if train.RUSH_ON:
        bad.append("train.RUSH_ON is on")
    for mp in ("de_fachwerk", "de_dust2", "de_mirage", "de_inferno", "de_nuke", "de_ancient", "de_anubis", "de_train"):
        try:
            ds = train.nade_drills(sid, mp)
        except Exception as e:
            bad.append(f"{mp}: {type(e).__name__}")
            continue
        n += len(ds)
        rush = [d["title"] for d in ds if d.get("tracks")]
        if rush:
            bad.append(f"{mp}: {len(rush)} anti-rush drills ({rush[0]})")
        keys = [o["key"] for o in execs.offer(sid, mp)]
        if "CT:rush" in keys:
            bad.append(f"{mp}: Prepare offers the anti-rush")
        if execs._rebuilt(mp):
            P = execs.plan(sid, mp, ds)
            loose = [k for k, x in P.items() if not (x.get("mine") or x.get("rec") or x.get("wily"))]
            if loose:
                bad.append(f"{mp}: the base's {', '.join(loose)} offered on a map built again")
    return not bad, "; ".join(bad[:5]) or f"no anti-rush drill among {n} lineups of 8 maps, none in Prepare; rebuilt maps offer only Wily's and his"


def check_dust2():
    """21/10, the user: "mets en place le même principe qu'on a établi sur Fachwerk ... sur la map sur laquelle tu auras le
    plus de datasets" (Dust2, 928 matches): its takes and defenses of A and B, Wily's own (resources/takes.json,
    resources/defenses.json), held to the same rules as Fachwerk's: three grenades at least each, from spots with a wall
    by them, a smoke never on its side's own molotov, each one's victims taking it, a flash never seen by its thrower;
    then the guide: each one step by step in order, a take all up at once then its entry cleared, a defense all on their
    spots before the Ts are on the site then held as its defender."""
    return _check_rebuilt("de_dust2")


def check_mirage():
    """23/10, the user: "tester de travailler une autre carte de cs en autonomie du début à la fin": Mirage (916 matches)
    built alone, held to the same rules as Dust2's."""
    return _check_rebuilt("de_mirage")


def check_rebuilt():
    """23/10, the user: "faire toutes les recherches sur toutes les cartes et de faire tous les autotests sans vraie
    connexion humaine": each map built alone after Mirage (its sites read from the base: tools/site_conf.py), held to
    the same rules; a map whose search is not over yet is said, not failed."""
    import glob
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import defense_build as DB
    maps = sorted(os.path.basename(f)[len("site_conf_"):-len(".json")]
                  for f in glob.glob(os.path.join(config.OUT, "selftest", "site_conf_*.json")))
    maps = [m for m in maps if m not in dict.keys(DB.CONF)]   # Fachwerk, Dust2, Mirage: their own checks
    plan = config.read_json(os.path.join(ROOT, "resources", "stuff_plan.json"), {}) or {}
    bad, said = [], []
    for mp in maps:
        if not any(k.startswith(mp + "|") for k in plan):
            said.append(f"{mp}: not searched yet")
            continue
        ok, why = _check_rebuilt(mp)
        (said if ok else bad).append(why if ok else f"{mp}: {why}")
    if not maps:
        return True, "no map built alone besides Mirage yet"
    return not bad, "; ".join(bad[:4]) or " | ".join(said)


def _check_rebuilt(mp):
    from wily.training import execs, train
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import defense_build as DB
    sid = str(config.settings().get("own_steamid") or "")
    bad, said = [], []
    vic = config.read_json(os.path.join(config.HERE, "resources", "victims_checked.json"), {}) or {}
    book = config.read_json(os.path.join(config.OUT, "selftest", "execs_checked.json"), {}) or {}
    P = execs.plan(sid, mp)
    probed = config.read_json(os.path.join(config.HERE, "resources", "spots_probed.json"), {}) or {}
    n_matches = max(1, len(train._map_dirs(mp)))
    for key in ("T:A", "T:B", "CT:A", "CT:B"):
        x = P.get(key)
        side, site = key.split(":")
        mine = x and (x.get("rec") if side == "CT" else x.get("wily"))
        if not mine:   # its rules give no 3 grenades for it (22/10, Dust2's B: no corner reaches its places): not offered
            said.append(f"{key} none (no corner reaches 3 places)")
            continue
        ms = x["members"]
        # 22/10, his test video: "un stuff qui part d'un spot qui est dans un coin, qui n'a pas une vision directe sur la
        # personne ciblée": each spot a corner the game locks you into (tools/spot_probe.py), out of its place's sight
        for m in ms:
            k = f"{mp}|{round(m['me']['pos'][0])}|{round(m['me']['pos'][1])}|{round(m['me']['pos'][2])}"
            v = (probed.get(k) or {}).get("d")
            if not v:
                bad.append(f"{key} {m['type']}: its spot never probed (tools/spot_probe.py)")
            else:
                b = [0 <= d_ < 6.0 for d_ in v]
                run = best = 0
                for i in range(32):
                    run = run + 1 if b[i % 16] else 0
                    best = max(best, run)
                if not (5 <= min(best, 16) <= 13 and sum(b) <= 14):   # as defense_build.corner_ok (24/10)
                    bad.append(f"{key} {m['type']}: no corner at {m['me']['pos']} (arc {min(best, 16)}, {sum(b)} blocked)")
            if train._exposed(mp, m["me"]["pos"], m["target"], 150, 120) / n_matches > 0.02:
                bad.append(f"{key} {m['type']}: its place sees its spot")
        if len(ms) < 3 or len({m["type"] for m in ms}) < 2:
            bad.append(f"{key}: {len(ms)} grenades, {len({m['type'] for m in ms})} kinds")
        fires = [m["target"] for m in ms if m["type"] == "molotov"]
        for m in ms:
            # the mesh's walls only where the game never probed it: a probed corner is one the game locks you into
            # (24/10: Inferno's B defense smokes, corners in the game, open by the mesh's edges)
            if not train.spot_walls(mp, m["me"]["pos"])["ok"] and DB.corner_ok(mp, m["me"]["pos"]) is not True:
                bad.append(f"{key} {m['type']}: an open spot {m['me']['pos']}")
            if m["type"] == "smoke" and any(math.dist(m["target"], f) < 220 for f in fires):
                bad.append(f"{key}: its smoke on its molotov")
            v = vic.get(train.victim_key(mp, m["type"], m["me"]["pos"], m["target"]))
            if not v:
                bad.append(f"{key} {m['type']}: its victims never checked (tools/victim_check.py)")
            elif m["type"] != "smoke" and not any(e["hit"] for e in v["victims"]):
                bad.append(f"{key} {m['type']}: none of its {len(v['victims'])} victims takes it")
            elif m["type"] == "flash" and (v.get("thrower") or {}).get("seen"):
                bad.append(f"{key}: its flash blinds its thrower ({v['thrower'].get('flash')} s)")
        r = book.get(f"{mp}|{key}") or {}
        if not r:
            bad.append(f"{key}: never played by the guide (tools/exec_check.py)")
        else:
            if r.get("members") != [m["id"] for m in ms]:
                bad.append(f"{key}: changed since the guide played it")
            if not r.get("ok"):
                bad.append(f"{key}: the guide's whole drill {', '.join(r.get('tries') or [])}")
            if not r.get("steps"):
                bad.append(f"{key}: the guide's steps not counted right")
            if ("held" if side == "CT" else "cleared") not in (r.get("entry") or []):
                bad.append(f"{key}: played {'as its defender' if side == 'CT' else 'as its entry'} {r.get('entry')}")
        said.append(f"{key} {'+'.join(m['type'] for m in ms)}")
    # 22/10, the user: "ne force pas le contenu si tu ne le trouves pas fiable": a site with no 3 grenades passing every
    # rule (corner, out of sight, victims, a molotov they don't walk round) has none, the map may have none at all
    name = mp.replace("de_", "").capitalize()
    return not bad, "; ".join(bad[:6]) or f"{name}'s " + " · ".join(said) + ": from corners, out of sight, victims taking them, played by the guide"


CHECKS = {"prepare": check_prepare, "victims": check_victims, "jumps": check_jumps, "join": check_join, "momentum": check_momentum,
          "momentum_pick": check_momentum_pick, "exposure": check_exposure, "setups": check_setups, "stuff_rules": check_stuff_rules,
          "execs": check_execs, "prepare_exec": check_prepare_exec, "prepare_momentum": check_prepare_momentum, "weapon": check_weapon, "jumpthrow": check_jumpthrow,
          "exec_steps": check_exec_steps, "defenses": check_defenses, "dust2": check_dust2, "mirage": check_mirage, "rebuilt": check_rebuilt,
          "no_rush": check_no_rush}


def main():
    names = [a for a in sys.argv[1:] if a in CHECKS] or list(CHECKS)
    fails = 0
    for n in names:
        try:
            ok, why = CHECKS[n]()
        except Exception as e:
            ok, why = False, f"{type(e).__name__}: {e}"
        fails += not ok
        print(f"{'PASS' if ok else 'FAIL'} {n}: {why}", flush=True)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
