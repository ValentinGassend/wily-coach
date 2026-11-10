"""Your own setups (19/10, his 17/10 video: the Fachwerk one he showed on the training server, "celui-là faut que tu me
le retiennes absolument", and "l'idée c'est que tu me trouves des trucs comme ça sur toutes les zones"): thrown on the
training server, each good throw kept with !keep, the whole saved with !setup <name>. The plugin's recorder
(Recorder.cs) writes coach/setups.jsonl: where you stood, your aim, your speed, in the air or crouched, the grenade's own
start and where it popped. Each setup becomes a run of Stuff drills from its spots, in its order, like a clip's
(train.clip_drills, _whole_clips): its technique and its click read from the throw itself."""
import json
import math
import os

import numpy as np

from wily.core import config, i18n

# CS2's throw speeds by click (wily/insights/nades.py _phys); the thrower's own velocity is added 1.25 times
SPEEDS = (("left click", 675.0), ("left + right click", 438.75), ("right click", 202.5))


def _file():
    from wily.training import replay
    return os.path.join(replay.COACH, "setups.jsonl")


def load(mp=None, test=False):
    """The setups you saved (on that map), the last one of a name winning; a guided self-test's own (its bot's) only
    when asked."""
    out = {}
    try:
        with open(_file(), encoding="utf-8") as f:
            for ln in f:
                try:
                    s = json.loads(ln)
                except ValueError:
                    continue
                if s.get("throws") and (not mp or s.get("map") == mp) and bool(s.get("test")) == test:
                    out[(s.get("map"), s.get("name"))] = s
    except OSError:
        pass
    return list(out.values())


def how(t):
    """The technique the recorder saw: in the air (a jumpthrow), moving forward (a run-throw), crouched."""
    v = t.get("vel") or [0.0, 0.0, 0.0]
    yaw = math.radians((t.get("ang") or [0.0, 0.0])[1])
    fwd = v[0] * math.cos(yaw) + v[1] * math.sin(yaw)
    crouch = (t.get("duck") or 0) >= 0.5
    run = fwd > 60
    if not t.get("ground", True):
        h = "forward + jumpthrow" if run else "jumpthrow"
    elif run:   # walking forward (20/10: his exec B flash, Shift + W at 130 u/s, was called a run-throw)
        h = "walking" if fwd < 160 else "run-throw (moving forward)"
    else:
        return "crouching" if crouch else "standing still"
    return h + (" + crouching" if crouch else "")


def click(t):
    """The click from the grenade's own start: its speed less the thrower's, the nearest of a left, both or right one."""
    nv, v = t.get("nade_v"), t.get("vel") or [0.0, 0.0, 0.0]
    if not nv:
        return "left click"
    s = math.sqrt(sum((a - 1.25 * b) ** 2 for a, b in zip(nv, v)))
    return min(SPEEDS, key=lambda c: abs(c[1] - s))[0]


_LANDS = {}


def zone_at(mp, p):
    """The place a grenade popped, named as the base's own throws that landed nearest call it, its height counted twice
    (21/10: Fachwerk's T Main exit is under Heaven's floor, 160 u lower: "Molotov → Heaven" for a fire on T Main)."""
    if mp not in _LANDS:
        try:
            import pandas as pd
            N = pd.read_parquet(os.path.join(config.OUT, "population", "nades.parquet"), columns=["map", "land_X", "land_Y", "land_Z", "land_zone"])
            N = N[(N["map"] == mp) & N.land_X.notna() & N.land_zone.notna()]
            _LANDS[mp] = (N[["land_X", "land_Y", "land_Z"]].to_numpy(float), N.land_zone.to_numpy())
        except Exception:
            _LANDS[mp] = None
    L = _LANDS[mp]
    if not L or not len(L[0]) or not p:
        return None
    dz = np.nan_to_num(L[0][:, 2] - p[2]) if len(p) > 2 and p[2] is not None else 0.0
    d = np.sqrt((L[0][:, 0] - p[0]) ** 2 + (L[0][:, 1] - p[1]) ** 2 + (2 * dz) ** 2)
    i = int(d.argmin())
    if d[i] > 400:   # a place the base's grenades never land (20/10: his smoke to CT spawn, "Smoke → ?"): where its players stand
        try:
            from wily.training import train
            S = train._zone_samples(mp)
            k = np.hypot(S.X.to_numpy() - p[0], S.Y.to_numpy() - p[1])
            j = int(k.argmin())
            return str(S["name"].iloc[j]) if k[j] < 600 and str(S["name"].iloc[j]) not in ("", "nan", "None") else None
        except Exception:
            return None
    from wily.insights import nades
    return nades.humanize(L[1][i], mp)


JUMP_V = 301.99   # CS2's jump impulse (u/s up); gravity 800


def stand_pos(t):
    """Where the thrower stood: a jumpthrow's release is in the air (20/10, his video: "le repère de position est un peu
    trop haut, au moment où j'envoie ma grenade, du coup il est en l'air ... impossible de reprendre le même repère
    visuel"): the floor under it, from its height in the jump (its speed up then); its aim the same (aimed standing,
    the jump without a move of the mouse: his smoke to B high standing and in a jumpthrow, -33.3/-64.1 and -33.5/-64.5)."""
    p = list(t["pos"])
    if t.get("ground", True):
        return p
    vz = (t.get("vel") or [0, 0, 0])[2]
    h = max(0.0, (JUMP_V ** 2 - min(abs(vz), JUMP_V) ** 2) / 1600.0)
    return [p[0], p[1], round(p[2] - h, 1)]


def aim_of(t):
    """His aim as his grenade left his hand: a throw from still feet goes where his view was, its yaw read from the
    grenade's own speed (22/10 eve, exec B's molotov: recorded -100.15, its grenade -100.27; that tenth of a degree put
    the fire on the cart, "la Molo fait aucun dégât parce qu'elle n'est pas envoyée précisément au bon endroit"); else
    his view as recorded."""
    a = list(t["ang"])
    nv, v = t.get("nade_v"), t.get("vel") or [0, 0, 0]
    if nv and t.get("ground", True) and math.hypot(v[0], v[1]) < 5 and math.hypot(nv[0], nv[1]) > 50:
        yaw = math.degrees(math.atan2(nv[1], nv[0]))
        if abs((yaw - a[1] + 540) % 360 - 180) < 1.0:
            a[1] = round(yaw, 3)
    return a


def jump_of(t):
    """His jumpthrow's moment, from his grenade itself (its speed up and its height as it left his hand; the recorded
    player speed is read some ticks late: 151 u/s for 212): what the jump adds to its speed up, and how high above his
    standing eye it left (the words' throw then: aim and click as said, these two his). None: no grenade data."""
    nv, na = t.get("nade_v"), t.get("nade_at")
    if not nv or not na:
        return None
    el = math.radians(10.0 - t["ang"][0] * 80.0 / 90.0)
    c = click(t)
    speed, dz = {"left click": (675.0, 0.0), "left + right click": (438.75, -6.0), "right click": (202.5, -12.0)}.get(c, (675.0, 0.0))
    add = nv[2] - speed * math.sin(el)
    rise = na[2] - (stand_pos(t)[2] + 64.0 + 16.0 * math.sin(el) + dz)
    return [round(add, 1), round(rise, 1)]


def drills(mp, test=False):
    """Your setups on that map as Stuff drills, each grenade from where you threw it, in the order you threw them."""
    from wily.training import train
    out = []
    for s in load(mp, test):
        key = f"{int(s.get('t') or 0)}"
        ts = [t for t in s["throws"] if t.get("pos") and t.get("ang") and t.get("pop")]
        for i, t in enumerate(ts):
            typ = t.get("type")
            team = int(t.get("team") or 2) if int(t.get("team") or 0) in (2, 3) else 2
            item = train.NADE_ITEM[typ][team] if typ == "molotov" else train.NADE_ITEM.get(typ)
            if not item:
                continue
            name = {"smoke": i18n.tr("Smoke"), "flash": i18n.tr("Flash"), "he": "HE", "molotov": i18n.tr("Molotov")}[typ]
            to = zone_at(mp, t["pop"]) or "?"
            out.append({"id": f"setup:{key}:{i}", "kind": "nade", "map": mp, "clip": f"setup:{key}", "step": i,
                        "title": f"{s['name']} · {name} → {to} ({i + 1}/{len(ts)})",
                        "tip": i18n.tr("your setup, saved with !setup: thrown in this order"),
                        "team": team, "type": typ, "item": item, "how": how(t), "click": click(t),
                        "me": {"pos": stand_pos(t), "ang": aim_of(t)}, "target": t["pop"], "victims": [], "_vic": ["T" if team == 2 else "CT", None],
                        # aimed crouched, thrown standing (20/10, his exec B molotov: "c'est un repère que tu prends accroupi,
                        # ensuite tu te relèves, t'envoies", "que le repère se prend bien accroupi")
                        **({"aim_from": "crouch"} if t.get("aim") == "crouch" else {}),
                        # his grenade itself, for the self-test's victims (where it left his hand, how fast)
                        **({"his_nade": {"type": typ, "inc": bool(t.get("inc")), "p": t["nade_at"], "v": t["nade_v"]}}
                           if t.get("nade_at") and t.get("nade_v") else {}),
                        # a jumpthrow: his own moment in the jump (his speed up, his height then): the guided bot lets go
                        # there too (20/10: his exec A smoke 2, a long flat one onto a roof, let go 0.12 s into the jump,
                        # landed 333 u off from a bind's moment)
                        **({"jump": jump_of(t)} if not t.get("ground", True) and jump_of(t) else {}),
                        # where he throws it from, said as the base names it (the entry's teammate says it in the chat)
                        "place": zone_at(mp, t["pos"]) or "",
                        # its moment in his own exec (s after the first one: 20/10, "reproduire l'exec sur le même timing")
                        **({"at": s["timing"][i]} if len(s.get("timing") or []) == len(ts) else {}),
                        "clock": 0, "weight": 40})
    return out


ORDER = {"smoke": 0, "molotov": 1, "he": 2, "flash": 3}   # his own: the smokes, then the fire, then the support flashes
CAP = {"smoke": 2, "molotov": 1, "he": 1, "flash": 2}   # a player's inventory, a teammate's dropped smoke on top (his own)


def compose(mp, drills):
    """The base's lineups made into setups (19/10, "travailler par blocs de stuff ... lancés depuis les mêmes endroits",
    "trouve-moi des trucs comme ça sur toutes les zones"): of one side, thrown within 250 u of each other (one floor),
    landing within 900 u of each other, three or more of two kinds or more with a smoke or a fire among them: one block,
    thrown in his order (smokes, molotov and HE, then flashes). Its lineups keep their own words (each checked by the
    guided bot); drawn as a clip's are, the whole block in its order (train._whole_clips). A lineup is in one block at
    most, the biggest first. Returns the drills, the members tagged."""
    from wily.insights import nades
    cand = [d for d in drills if d.get("kind") == "nade" and not d.get("clip") and not d.get("tracks") and d.get("me") and d.get("target")]   # an anti-rush keeps its own run
    used, blocks = set(), []
    for d in cand:
        p = d["me"]["pos"]
        grp = [e for e in cand if e["team"] == d["team"] and math.dist(e["me"]["pos"][:2], p[:2]) <= 250
               and abs(e["me"]["pos"][2] - p[2]) <= 64 and math.dist(e["target"][:2], d["target"][:2]) <= 900]
        blocks.append(grp)
    for grp in sorted(blocks, key=len, reverse=True):
        grp = [e for e in grp if e["id"] not in used]
        if len(grp) < 3:
            continue
        p0 = grp[0]["me"]["pos"][:2]
        grp.sort(key=lambda e: math.dist(e["me"]["pos"][:2], p0))   # the nearest to its first spot first
        n = {}
        grp = [e for e in grp if n.setdefault(e["type"], 0) < CAP.get(e["type"], 1) and not n.update({e["type"]: n[e["type"]] + 1})]
        kinds = {e["type"] for e in grp}
        if len(grp) < 3 or len(kinds) < 2 or not kinds & {"smoke", "molotov"}:
            continue
        grp.sort(key=lambda e: (ORDER.get(e["type"], 9), e["id"]))
        frm = Counter_name([e["id"].split(":")[-1].split(">")[0] for e in grp if ">" in e["id"]], mp, nades)
        to = Counter_name([e["id"].split(":")[-1].split(">")[1] for e in grp if ">" in e["id"]], mp, nades)
        key = f"setupb:{mp}:{grp[0]['id']}"
        for k, e in enumerate(grp):
            used.add(e["id"])
            e.update(clip=key, step=k, title=i18n.tr("SETUP · {to} from {frm}", to=to, frm=frm) + f" · {e['title']} ({k + 1}/{len(grp)})",
                     tip=i18n.tr("a setup: these grenades from the same place, in this order") + (f" · {e['tip']}" if e.get("tip") else ""))
    return drills


def Counter_name(keys, mp, nades):
    """The zone most of them name, as the app says it."""
    if not keys:
        return "?"
    from collections import Counter
    return nades.humanize(Counter(keys).most_common(1)[0][0], mp)
