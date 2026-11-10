"""Crossfire: the warm-up's aim on the real maps, from real duels (13/10, the user: "Crossfire : simule de vrais duels
avec des bots utilisant des mouvements réalistes pour travailler le counter-strafing et la tenue d'angles + spray
practice: two bots picking the same angle at 2 different positions and 2 different timings, one spray, 30 bullets at
most"). It replaces the aim map at the warm-up's start.

From the base's demos (on the coach's PC, shipped with the base like the entries): rifle duels where one player held
still and the other came into his sight moving. out/train_crossfire/
<map>.json keeps, for each spot (a side, a place, one angle) at least 3 duels were fought from:
- where he stood and where his crosshair was when the peeker came into sight (the angle to hold);
- the real peeks: each peeker's way over the 1.25 s before the enemy team saw him, up to the kill (every 2 ticks);
- pairs of peeks onto about the same angle, one from the left, one from the right (v3): the spray drill's two bots."""
import json
import math
import os
import random
from collections import Counter

import numpy as np
import pandas as pd

from wily.core import config
from wily.core import i18n
from wily.training import replay

CF_D = os.path.join(config.OUT, "train_crossfire")
STEP = 2   # ticks per frame of a peek's way
RIFLES = {"ak47", "m4a1", "m4a1_silencer", "galilar", "famas", "sg556", "aug"}
WIN = 160   # ticks read before each kill (2.5 s)


DEMOS = 200   # demos read per map (13/10: 30 gave Mirage 7 spots)
# 2 (14/10, his test on Inferno): no jump-peek (a bot can't jump: put on the jump's top, standing, it stayed stuck in
# the ceiling of Apps), the spray's two enemies come with their real peeks ("faut pas qu'ils spawn, faut qu'ils me
# peekent, à des timings différents")
# 3 (14/10, his second test): a peek starts out of sight half a second at least ("il spawn déjà sur moi"); the spray's
# two come onto one angle from both sides ("un qui peek à gauche, un qui peek à droite, sur le même angle")
# 4 (14/10, his third test): a spot is a place whatever the angle ("des gens qui viennent de l'appartement aussi, de
# banane aussi": the enemy glows where it comes from); the spray at short and mid range ("de Pit jusqu'à Library
# c'est trop long")
V = 4


def load(mp, build=True):
    """The map's crossfire data (cached); {} where it can't be built (a player's copy, a hostage map, no demo)."""
    os.makedirs(CF_D, exist_ok=True)
    cf = os.path.join(CF_D, f"{mp}.json")
    try:
        c = json.load(open(cf, encoding="utf-8"))
        if c.get("v") in (3, V):   # v3: the same format (its spots one angle each): kept until rebuilt
            return c
    except (OSError, ValueError):
        pass
    if not build or mp.startswith("cs_") or config.role() == "client":
        return {}
    return replay.in_worker(_build, mp, DEMOS)


def _yaw_mean(a):
    a = np.radians(np.asarray(a, float))
    return float(np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean())))


def _bearing(a, b):
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _build(mp, demos=DEMOS):
    from demoparser2 import DemoParser
    from wily.insights import nades
    os.makedirs(CF_D, exist_ok=True)
    cf = os.path.join(CF_D, f"{mp}.json")
    dirs = []
    for d in sorted(os.listdir(config.DEEP), reverse=True):
        try:
            if json.load(open(os.path.join(config.DEEP, d, "meta.json"), encoding="utf-8")).get("map") == mp \
                    and config.has_demo(d):
                dirs.append(d)
        except (OSError, ValueError):
            continue
    rows = []
    for d in dirs[:demos]:
        config.wait_for_match_end(what="crossfire")   # your match first
        try:
            D = pd.read_parquet(os.path.join(config.DEEP, d, "duels.parquet"))
            D = D[D.weapon.isin(RIFLES) & (D.killer_side != D.victim_side) & D.killer_side.isin(["T", "CT"])]
            hold_k = (D.killer_speed < 60) & (D.victim_speed > 110)   # the killer held, the victim came
            hold_v = (D.victim_speed < 60) & (D.killer_speed > 110)   # the victim held, the killer came
            D = D[hold_k | hold_v].copy()
            D["holder"] = np.where(hold_k[D.index], "killer", "victim")
            D = D[(D.distance > 7) & (D.distance < 60)]   # meters: 280 to 2,400 u
            if not len(D):
                continue
            want = sorted({t for k in D.tick for t in range(int(k) - WIN, int(k) + 1, STEP)})
            dp = DemoParser(config.demo(d))
            T = dp.parse_ticks(["X", "Y", "Z", "yaw", "pitch", "is_alive", "last_place_name", "spotted", "is_airborne"], ticks=want)
            T["steamid"] = T.steamid.astype(str)
        except Exception as e:
            print("crossfire", d, e, flush=True)
            continue
        T = T.set_index(["steamid", "tick"]).sort_index()
        for _, r in D.iterrows():
            k = int(r.tick)
            hs, ps = (str(r.killer), str(r.victim)) if r.holder == "killer" else (str(r.victim), str(r.killer))
            hside = r.killer_side if r.holder == "killer" else r.victim_side
            try:
                H = T.loc[hs].loc[k - WIN:k]
                P = T.loc[ps].loc[k - WIN:k]
            except KeyError:
                continue
            # this kill's own ticks (2 apart): another duel's window next to it brings ticks of the other parity, a way
            # read with them would play at half speed there
            H = H[(H.index - k) % STEP == 0]
            P = P[(P.index - k) % STEP == 0]
            H = H[H.index.isin(P.index)]
            P = P[P.index.isin(H.index)]
            if len(P) < 40 or len(H) < 40:
                continue
            sp = P.spotted.astype(object).eq(True).to_numpy()
            # the last time he came into the other team's sight before the kill
            ks = len(sp) - 1
            while ks > 0 and sp[ks - 1]:
                ks -= 1
            if not sp[ks] or ks < 20:   # seen from the window's start: no peek to replay
                continue
            j = ks - 1   # the last time they saw him before: his way starts after it, out of sight
            while j >= 0 and not sp[j]:
                j -= 1
            a = max(j + 1, ks - 40)   # 1.25 s before at most
            if ks - a < 16:   # half a second out of sight at least
                continue
            way = P.iloc[a:]
            if way.is_airborne.fillna(False).astype(bool).any():   # a jump on the way: a bot can't replay it
                continue
            W = way[["X", "Y", "Z"]].to_numpy(float)
            if len(W) < 30 or np.hypot(*(W[-1, :2] - W[0, :2])) < 60:
                continue
            Hs = H[["X", "Y", "Z"]].to_numpy(float)[a:]
            if np.hypot(Hs[:, 0] - Hs[0, 0], Hs[:, 1] - Hs[0, 1]).max() > 48:   # he held a spot
                continue
            hk = H.iloc[min(ks, len(H) - 1)]
            path = []
            for x, y, z, yw, pi in zip(way.X, way.Y, way.Z, way.yaw, way.pitch):
                path += [round(float(x), 1), round(float(y), 1), round(float(z), 1), round(float(yw)), round(float(pi))]
            pl = way.last_place_name.fillna("").iloc[0]
            hl = H.last_place_name.fillna("").iloc[-1]
            k16 = max(0, len(W) - 17)   # where he went the last half second: across the holder's sight, to his left or right
            u = W[-1, :2] - np.array([float(hk.X), float(hk.Y)])
            v = W[-1, :2] - W[k16, :2]
            lat = float((u[0] * v[1] - u[1] * v[0]) / (np.hypot(*u) or 1.0))
            rows.append({"side": hside, "lat": lat, "hpos": [float(hk.X), float(hk.Y), float(hk.Z)], "hang": [float(hk.pitch), float(hk.yaw)],
                         "hzone": nades.humanize(hl, mp) if hl else None, "pzone": nades.humanize(pl, mp) if pl else None,
                         "path": path, "end": [float(v) for v in W[-1]], "won": r.holder == "killer", "w": r.weapon})
    out = {"v": V, "spots": []}
    # one spot: a side, a place 80 u around (v4: every way into it), the crosshair on the angle most of its peeks
    # come out at
    groups = []
    for x in sorted(rows, key=lambda x: random.random()):
        for g in groups:
            c = g[0]
            if c["side"] == x["side"] and math.dist(c["hpos"][:2], x["hpos"][:2]) < 80 and abs(c["hpos"][2] - x["hpos"][2]) < 64:
                g.append(x)
                break
        else:
            groups.append([x])
    cand = []
    for g in groups:
        side = g[0]["side"]
        if len(g) < 3:
            continue
        P = np.array([x["hpos"] for x in g])
        med = np.median(P, axis=0)
        me = g[int(np.argmin(np.hypot(P[:, 0] - med[0], P[:, 1] - med[1])))]["hpos"]   # a spot a player really stood on
        ang = [round(float(np.median([x["hang"][0] for x in g])), 1), round(_yaw_mean([x["hang"][1] for x in g]), 1)]
        peeks, ends = [], []
        for x in sorted(g, key=lambda x: random.random()):   # different peeks: their spots 60 u apart
            if all(math.dist(x["end"][:2], e[:2]) > 60 for e in ends):
                ends.append(x["end"])
                peeks.append({"zone": x["pzone"] or "?", "path": x["path"]})
            if len(peeks) == 12:
                break
        took = []
        E = [x["end"] for x in g]
        # the spray's pairs (14/10): two peeks onto about the same angle (12 degrees at most), one coming from the left,
        # the other from the right (each crossed the holder's sight 20 u or more the last half second), not on one spot
        for i in range(len(E)):
            for j in range(i + 1, len(E)):
                a_, b_ = E[i], E[j]
                da, db = math.dist(me[:2], a_[:2]), math.dist(me[:2], b_[:2])
                diff = abs(((_bearing(me, a_) - _bearing(me, b_)) + 180) % 360 - 180)
                li, lj = g[i]["lat"], g[j]["lat"]
                if 300 < min(da, db) and max(da, db) < 1300 and diff <= 12 and 30 < math.dist(a_[:2], b_[:2]) < 700 \
                        and abs(a_[2] - b_[2]) < 120 and min(abs(li), abs(lj)) >= 20 and li * lj < 0 \
                        and all(math.dist(a_, E[p]) > 40 or math.dist(b_, E[q]) > 40 for p, q in took):
                    took.append((i, j))
        # each one with the real peek that brought its player there (the spray's enemies come out, they don't appear)
        pairs = [[{"end": [round(v, 1) for v in E[k]], "path": [round(v) for v in g[k]["path"]]} for k in pq] for pq in took]
        zones = Counter(x["hzone"] for x in g if x["hzone"])
        cand.append({"side": side, "pos": [round(v, 1) for v in me], "ang": ang, "zone": zones.most_common(1)[0][0] if zones else "?",
                     "n": len(g), "won": round(100 * sum(x["won"] for x in g) / len(g)), "peeks": peeks, "pairs": pairs[:6]})
    for side in ("T", "CT"):   # the most fought spots of each side, 14 at most
        out["spots"] += sorted([c for c in cand if c["side"] == side], key=lambda c: -c["n"])[:14]
    json.dump(out, open(cf, "w", encoding="utf-8"), separators=(",", ":"))
    return out


SPRAY_MAX = 600   # 27/10, his order "limiter la distance de l'exercice de spray": the real-client battery's sprays passed
# up to ~650 u and failed from 750 u on (Overpass's Water 900, Ancient's Alley 800-1180, Vertigo's Elevator 1000); 16:30,
# round 4 with the driver's aim fixed: 350 u 5/5, 500-615 u 4/5 or 2/5 (Dust2's A site 525-643 u: 4-8 hits of 21-30), a
# spray's control no longer the point past 600 u


SEEN_SLACK = 40   # 10/11: the spray starts a moment after the first one is seen, a few steps nearer


def _near_pairs(sp, mp=None):
    """The spot's spray pairs at short and mid range (SPRAY_MAX at most; 14/10 already: "de Pit jusqu'à Library c'est
    trop long"), the farther ones left out: where their ways end, and where the holder first sees each of the two
    (tools/crossfire_check.py; 10/11, round 28: Inferno's T Apps sprayed at 600-711 u, its far one in plain sight down its
    corridor from 760 u while its way ends at 522 u), and clear of cover where they stop (pair_ok). A pair one of whose two
    is never seen is left out too (the drill would wait for it). All the pairs within SPRAY_MAX by their ends while that
    spot is not traced."""
    near = [i for i, pr in enumerate(sp.get("pairs") or []) if all(math.dist(sp["pos"][:2], q["end"][:2]) < SPRAY_MAX for q in pr)]
    seen = None
    if mp:
        book = config.read_json(os.path.join(config.HERE, "resources", "crossfire_checked.json"), {}) or {}
        rec = book.get(f"{mp}|{round(sp['pos'][0])}|{round(sp['pos'][1])}|{round(sp['pos'][2])}") or {}
        if rec.get("pairs") is not None and len(rec["pairs"]) == len(sp.get("pairs") or []):
            seen = rec["pairs"]
    return [sp["pairs"][i] for i in near if seen is None or seen[i] is None or pair_ok(seen[i])]


def pair_ok(rec):
    """A spray pair as tools/crossfire_check.py traced it: both seen first within SPRAY_MAX + SEEN_SLACK, both with head
    and chest in the holder's line where they stop (10/11, round 28: Vertigo's Side stopped out of his sight, 2 of 3
    bullets into the wall; Train's A Site with its chest behind the train's edge)."""
    seen_ok = all(d is not None and d <= SPRAY_MAX + SEEN_SLACK for d in rec.get("seen") or [None])
    return seen_ok and all(rec.get("open") or [False])


def level_of(sid):
    """The player's training level (rework_entrainement.md, section 4): the app's level key (Premier rating, else the
    Competitive rank) from his analysis; None when unknown."""
    try:
        adv = json.load(open(os.path.join(config.player_dir(str(sid)), "advice.json"), encoding="utf-8"))
        return ((adv.get("plan") or {}).get("level") or {}).get("key")
    except (OSError, ValueError):
        return None


# what each level works on (13/10, the user: "l'apprentissage du stuff et du spray transfer n'est pas forcément la
# priorité chez le débutant, la priorité c'est déjà de garder des angles, d'avoir le crosshair au bon endroit")
VARIANTS = {"debut": ["hold", "peek"], "inter": ["hold", "peek", "hold", "spray"], None: ["hold", "peek", "spray"]}
SECS = {"hold": 75, "peek": 75, "spray": 60}
REPS = {"hold": 6, "peek": 6, "spray": 5}


def _id(mp, side, sp, v):
    return f"crossfire:{mp}:{side}:{sp['zone']}:{round(sp['pos'][0])}:{round(sp['pos'][1])}:{v}"


def _kind(path):
    """A real peek's kind (23/10, the user: "peeks des bots avec les mouvements de la base (jiggle, wide swing)"): a wide
    swing when it ran into your sight, 180 u/s and more from 0.75 to 0.25 s before the kill (its frames 2 ticks apart; a
    quarter of Mirage's peeks), else a plain peek."""
    n = len(path) // 5
    if n < 30:
        return ""
    a, b = path[(n - 24) * 5:(n - 24) * 5 + 2], path[(n - 8) * 5:(n - 8) * 5 + 2]
    return "swing" if math.dist(a, b) * 2 >= 180 else ""


AWP_SHARE, AWP_LINE = 0.25, 1100.0   # a spot played with an AWP: a quarter of its kills, its peeks that far


def _line(sp):
    """How far its peeks come out from the spot, their median (u)."""
    ds = sorted(math.dist(sp["pos"][:2], p["path"][-5:-3]) for p in sp.get("peeks") or [] if len(p.get("path") or []) >= 5)
    return ds[len(ds) // 2] if ds else 0.0


def _hidden(mp, sp):
    """A spot's peeks whose start the holder does not see (23/10 eve, the user on Mirage's Window: "ils ne sont pas cachés
    à la base. Ils sont derrière absolument rien"; the base's Ts were unseen there behind the round's smokes): the ones
    tools/crossfire_check.py traced hidden, all of them while it has not traced that spot."""
    book = config.read_json(os.path.join(config.HERE, "resources", "crossfire_checked.json"), {}) or {}
    rec = book.get(f"{mp}|{round(sp['pos'][0])}|{round(sp['pos'][1])}|{round(sp['pos'][2])}")
    peeks = sp.get("peeks") or []
    if not rec or len(rec.get("seen") or []) != len(peeks):
        return peeks
    # and seen once on its way (27/10, Nuke's Squeaky: peeks ending at Mini, never in sight, "6 sans duel")
    reach = rec.get("reach") if len(rec.get("reach") or []) == len(peeks) else [True] * len(peeks)
    return [p for p, seen, r in zip(peeks, rec["seen"], reach) if not seen and r]


def drills(sid, mp, secs, guns, rifle, items=None, nsess=0):
    """The Crossfire block: as many drills as its time holds, in the order of the player's level, on different spots,
    both sides in turn: the ones missed and due first (the training's boxes: items, nsess), then the ones never
    played, the most fought first, then the others. guns: (T rifle, CT rifle, pistol) as train._my_guns gives them;
    rifle: side -> the bots' rifle."""
    data = load(mp, build=False)
    spots = data.get("spots") or []
    if not spots:
        return []
    lv = level_of(sid)
    order = VARIANTS.get(lv, VARIANTS[None])
    tr_, cr_, _ = guns
    by_side = {s: [x for x in spots if x["side"] == s] for s in ("T", "CT")}
    used = {"T": 0, "CT": 0}
    out, total, k = [], 0, 0
    while total < secs - 20 and k < max(12, secs // 30):   # a focus block of 20 min: about 18 drills
        v = order[k % len(order)]
        side = ("CT", "T")[k % 2] if all(by_side.values()) else ("CT" if by_side["CT"] else "T")
        k += 1
        cands = by_side[side]
        if v == "spray":
            cands = [x for x in cands if _near_pairs(x, mp)]
        elif v == "peek":   # you come from where its holder does not see you (tools/crossfire_check.py)
            cands = [x for x in cands if _hidden(mp, x)]
        else:   # a hold: 3 real peeks at least whose start you do not see from the spot (tools/crossfire_check.py)
            cands = [x for x in cands if len(_hidden(mp, x)) >= 3]
        if not cands:
            continue
        items = items or {}

        def rank(x, v=v, side=side):
            it = items.get(_id(mp, side, x, v))
            return (1, -x["n"]) if it is None else (0, it["box"]) if it["next"] <= nsess else (2, it["next"])
        cands = sorted(cands, key=rank)
        sp = cands[used[side] % len(cands)]
        used[side] += 1
        me_side = side if v != "peek" else ("T" if side == "CT" else "CT")   # peek: you are the one who comes
        team = 2 if me_side == "T" else 3
        gun = replay._item(tr_ if me_side == "T" else cr_) or rifle[team]
        pistol = "weapon_glock" if team == 2 else "weapon_usp_silencer"
        foe = rifle[5 - team]
        zone = sp["zone"]
        title = {"hold": i18n.tr("HOLD THE ANGLE · {zone}", zone=zone), "peek": i18n.tr("PEEK · {zone}", zone=zone),
                 "spray": i18n.tr("SPRAY · {zone}", zone=zone)}[v]
        tip = {"hold": i18n.tr("{n} real peeks from the base: crosshair where they come out, kill before they kill you", n=REPS["hold"]),
               "peek": i18n.tr("you peek an angle the base holds there: stop before you shoot (counter-strafe)"),
               "spray": i18n.tr("two enemies come out on the same line, one after the other: kill both in one spray, without letting go, 30 bullets at most")}[v]
        d = {"id": _id(mp, side, sp, v), "kind": "aim", "mode": "crossfire",
             "variant": v, "map": mp, "team": team, "title": title, "tip": tip, "seconds": SECS[v], "count": REPS[v],
             "weapons": ["weapon_knife", pistol, gun], "bot_weapons": ["weapon_knife", foe], "armor": 100, "helmet": True}
        # the guns the spot is played with (23/10, the user: "varier les armes selon le spot (AWP sur les longues lignes,
        # pistolets en début de match)"): the block's first duel a pistol round's (no helmet); a spot its holders hold with
        # an AWP a quarter of the time, on a long line, held with one (yours on a hold, the bot's on a peek)
        if v != "spray":
            if not out:
                d.update(id=d["id"] + ":pistol", title=f"{title} · {i18n.tr('PISTOLS')}", helmet=False,
                         weapons=["weapon_knife", pistol], bot_weapons=["weapon_knife", "weapon_usp_silencer" if team == 2 else "weapon_glock"])
            else:
                try:
                    from wily.training import train
                    share, n_k = train.awp_share(mp, sp["pos"], sp["side"])
                except Exception as e:
                    print("crossfire awp", mp, e, flush=True)
                    share, n_k = 0.0, 0
                if n_k >= 8 and share >= AWP_SHARE and _line(sp) >= AWP_LINE:
                    d.update(id=d["id"] + ":awp", title=f"{title} · AWP")
                    if v == "hold":
                        d["weapons"] = ["weapon_knife", pistol, "weapon_awp"]
                    else:
                        d["bot_weapons"] = ["weapon_knife", "weapon_awp"]
        if v == "hold":
            d.update(me={"pos": sp["pos"], "ang": sp["ang"]}, tracks=[{"zone": p["zone"], "path": p["path"], "kind": _kind(p["path"])} for p in _hidden(mp, sp)])
        elif v == "peek":
            hid = _hidden(mp, sp)
            # each real peek whole, not its start only (24/10, the real-client test of Nuke's Squeaky: the doors on its way
            # stayed shut, the plugin opens those its frames pass through, and nothing showed the way the peek went)
            d.update(me={"pos": hid[0]["path"][:3], "ang": [0, hid[0]["path"][3]]},
                     bots=[{"pos": sp["pos"], "ang": sp["ang"], "zone": sp["zone"]}],
                     tracks=[{"zone": p["zone"], "path": p["path"]} for p in hid])
        else:   # the pairs' two enemies and their real peeks, in the same order
            d.update(me={"pos": sp["pos"], "ang": sp["ang"]},
                     bots=[{"pos": q["end"], "ang": [0, _bearing(q["end"], sp["pos"])], "zone": zone} for pair in _near_pairs(sp, mp) for q in pair],
                     tracks=[{"zone": zone, "path": q["path"]} for pair in _near_pairs(sp, mp) for q in pair])
        out.append(d)
        total += SECS[v]
    # 14/10, the user: "mets tout le travail de spray ensemble, tout le travail de peek ensemble, tout le hold the angle
    # ensemble": each variant's drills in a row, in the level's order
    out.sort(key=lambda d: order.index(d["variant"]))
    return out
