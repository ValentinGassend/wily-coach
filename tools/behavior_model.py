"""Why players look and move where they do, and what they do with it (29/10, the user: "évaluer le positionnement des joueurs
adverses, des joueurs alliés, le positionnement du viseur de chacun ... à chaque moment, et évaluer toutes les possibilités
que ce joueur a ... pourquoi ce joueur regarde tel ou tel endroit, et quelle information a ce joueur, de quand ça date,
quelle information nouvelle il a, et pourquoi il agit comme ça ... établir des récurrences et des principes très fins ...
définir une action à faire en fonction de chaque événement et de chaque combinaison ... des standards ... par cartes, par
armes").

Every 0.25 s of a live round, for each living player, from the whole demo:
- him: his 128 u cell, side, weapon (rifle, awp, smg, pistol, heavy, other), health, crouched, scoped, flashed;
- what his team knows of the enemies: each enemy's last sight by one of them (when, where) and the last sound of it a
  teammate could hear (a footstep within 1100 u, a shot within 2000 u): its kind, its age (under 1 s, 3 s, 8 s, 20 s, or
  none), its direction (8 sectors) and distance (under 600 u, 1500 u, further); "new": learned in the last 0.5 s;
- his team: teammates within 600 u, the direction the nearest one looks;
- the grenades: a smoke up within 1200 u and its direction, a fire within 600 u, a flash popped near him in the last second;
- the round: its moment (before 25 s, before 60 s, after), the numbers (more alive, as many, fewer), the bomb down;
- what he did: where he looked (36 bins of 10 deg, its pitch) and why it reads so (the info he had, a smoke's edge, the way
  his nearest teammate looks too, his danger: where the killers of the players who died in his cell stood, or the place's
  standard), and how he moved over the next second (held, walked, ran, which way) with his real way over the next 4 s.
Seeing an enemy: a fight, counted apart (its own cases).

The cases are kept at four levels, from the place alone to every parameter, each case with its looks, its reasons, its
moves and a real way of each move; the bots use the finest case with enough players in it (Look.cs, Move.cs). Across all
cases, the principles: how often players look at the info they have by its age and distance, at a smoke's edge, apart from
their teammate, at their danger; how they move by the numbers and the info (out/knowledge/behavior/principles.json).

Usage: python tools/behavior_model.py <demo or folder> [...] [--out <dir>]
"""
import glob
import json
import math
import os
import sys
import time
from collections import defaultdict

import numpy as np
from demoparser2 import DemoParser

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wily.core import config  # noqa: E402

OUT = os.path.join(config.OUT, "knowledge", "behavior")
STEP = 16
CELL, ZC = 128.0, 96.0
STEP_RANGE, SHOT_RANGE, SMOKE_RANGE, FIRE_RANGE, FLASH_RANGE = 1100.0, 2000.0, 1200.0, 600.0, 700.0
AGES = (64, 192, 512, 1280)   # ticks: 1 s, 3 s, 8 s, 20 s
WEAPON = {"awp": "awp", "ssg08": "awp", "g3sg1": "awp", "scar20": "awp",
          "ak47": "rifle", "m4a1": "rifle", "m4a1_silencer": "rifle", "m4a4": "rifle", "galilar": "rifle", "famas": "rifle",
          "aug": "rifle", "sg556": "rifle", "mac10": "smg", "mp9": "smg", "mp7": "smg", "mp5sd": "smg", "ump45": "smg",
          "p90": "smg", "bizon": "smg", "nova": "heavy", "xm1014": "heavy", "mag7": "heavy", "sawedoff": "heavy",
          "m249": "heavy", "negev": "heavy"}
PISTOLS = {"glock", "hkp2000", "usp_silencer", "p250", "fiveseven", "tec9", "cz75a", "deagle", "revolver", "elite"}


def sid_(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def sector(dx, dy):
    return int(((math.degrees(math.atan2(dy, dx)) + 360.0 + 22.5) % 360.0) // 45.0)


def yaw_to(dx, dy):
    return math.degrees(math.atan2(dy, dx))


def adiff(a, b):
    return abs((a - b + 540.0) % 360.0 - 180.0)


def wclass(name):
    n = str(name or "").lower().replace("weapon_", "").replace("-", "").replace(" ", "")
    n = {"m4a1s": "m4a1_silencer", "uspsx": "usp_silencer", "usps": "usp_silencer", "p2000": "hkp2000", "sg553": "sg556",
         "galil": "galilar", "ppbizon": "bizon", "dualberettas": "elite", "r8revolver": "revolver", "desertdeagle": "deagle",
         "ssg08": "ssg08", "mp5": "mp5sd"}.get(n, n)
    return WEAPON.get(n) or ("pistol" if n in PISTOLS else "other")


def age_band(dt):
    for i, a in enumerate(AGES):
        if dt <= a:
            return i
    return None


def dist_band(d):
    return 0 if d < 600 else (1 if d < 1500 else 2)


def cell_of(side, x, y, z):
    return f"{side}|{int(math.floor(x / CELL))}|{int(math.floor(y / CELL))}|{int(math.floor(z / ZC))}"


def load_danger(mp):
    fn = os.path.join(config.OUT, "knowledge", "danger_util", f"{mp}.json")
    try:
        return json.load(open(fn, encoding="utf-8")).get("danger") or {}
    except (OSError, ValueError):
        return {}


def demo_rows(path):
    """-> map, [sample]: each a dict of its cases' keys and its labels."""
    p = DemoParser(path)
    mp = p.parse_header().get("map_name") or "?"
    # asked whether listed or not (round_end is parsed though the demo's list leaves it out); the missing ones come back absent
    want = ["round_freeze_end", "round_end", "weapon_fire", "player_footstep", "smokegrenade_detonate", "smokegrenade_expired",
            "inferno_startburn", "inferno_expire", "flashbang_detonate", "bomb_planted"]
    ev = dict(p.parse_events(want, player=["X", "Y", "Z"]))
    ticks_of = lambda e: sorted(int(t) for t in ev[e]["tick"]) if e in ev else []
    fe, re_ = ticks_of("round_freeze_end"), ticks_of("round_end")
    live = [(a, next((r for r in re_ if r > a), None)) for a in fe]
    live = [(a, b) for a, b in live if b]
    if not live:
        return mp, []
    ticks = sorted({t for a, b in live for t in range(a, b, STEP)})
    df = p.parse_ticks(["X", "Y", "Z", "yaw", "pitch", "team_num", "is_alive", "approximate_spotted_by", "active_weapon_name",
                        "health", "ducking", "is_scoped", "flash_duration"], ticks=ticks)
    df["steamid"] = df.steamid.map(sid_)
    by_tick = defaultdict(list)
    for r in df.itertuples():
        if not r.is_alive or r.team_num not in (2, 3):
            continue
        sb = r.approximate_spotted_by
        by_tick[int(r.tick)].append({"sid": r.steamid, "team": int(r.team_num), "x": float(r.X), "y": float(r.Y), "z": float(r.Z),
                                     "yaw": float(r.yaw), "pitch": float(r.pitch), "w": wclass(r.active_weapon_name), "hp": int(r.health or 0),
                                     "duck": bool(r.ducking), "scoped": bool(r.is_scoped), "flash": float(r.flash_duration or 0),
                                     "sb": {sid_(x) for x in sb} if isinstance(sb, (list, np.ndarray)) else set()})

    def pts(e, xs="user_X", ys="user_Y", zs="user_Z", who="user_steamid"):
        if e not in ev:
            return []
        d = ev[e]
        cx = xs if xs in d.columns else ("x" if "x" in d.columns else None)
        cy = ys if ys in d.columns else ("y" if "y" in d.columns else None)
        cz = zs if zs in d.columns else ("z" if "z" in d.columns else None)
        if cx is None:
            return []
        out = []
        for r in d.itertuples():
            out.append((int(r.tick), sid_(getattr(r, who, 0)) if who in d.columns else 0, float(getattr(r, cx)), float(getattr(r, cy)),
                        float(getattr(r, cz)) if cz else 0.0))
        return out
    steps = pts("player_footstep")
    shots = pts("weapon_fire")
    smk_on = [(t, x, y) for t, _, x, y, _ in pts("smokegrenade_detonate", "x", "y", "z")]
    smk_off = [(t, x, y) for t, _, x, y, _ in pts("smokegrenade_expired", "x", "y", "z")]
    fire_on = [(t, x, y) for t, _, x, y, _ in pts("inferno_startburn", "x", "y", "z")]
    fire_off = [(t, x, y) for t, _, x, y, _ in pts("inferno_expire", "x", "y", "z")]
    flashes = [(t, x, y) for t, _, x, y, _ in pts("flashbang_detonate", "x", "y", "z")]
    plants = [(t, x, y) for t, _, x, y, _ in pts("bomb_planted")]

    def spans(ons, offs, life):
        """(start, end, x, y) of each smoke or fire: from its start to its own end event, else `life` ticks"""
        out_ = []
        for to, x, y in ons:
            te = next((tf for tf, xf, yf in offs if tf >= to and math.hypot(xf - x, yf - y) < 64), to + life)
            out_.append((to, min(te, to + life), x, y))
        return out_

    def active(sp, t):
        return [(x, y) for a, b, x, y in sp if a <= t <= b]
    smk_sp, fire_sp = spans(smk_on, smk_off, 22 * 64), spans(fire_on, fire_off, 8 * 64)
    danger = load_danger(mp)
    pos = {(t, r["sid"]): (r["x"], r["y"], r["z"]) for t, rows in by_tick.items() for r in rows}
    team_of = {}
    seen_by = {2: {}, 3: {}}    # team -> enemy -> (tick, x, y): last sight by one of the team
    heard_by = {2: {}, 3: {}}   # team -> enemy -> (tick, x, y): last sound a teammate could hear
    si = hi = 0
    out = []
    for t in ticks:
        rows = by_tick.get(t, [])
        if not rows:
            continue
        rnd = next(((a, b) for a, b in live if a <= t < b), None)
        for r in rows:
            team_of[r["sid"]] = r["team"]
        alive = {2: [r for r in rows if r["team"] == 2], 3: [r for r in rows if r["team"] == 3]}
        for r in rows:   # sights: an enemy spotted by one of a team
            for tm in (2, 3):
                if r["team"] != tm and any(team_of.get(o) == tm for o in r["sb"]):
                    seen_by[tm][r["sid"]] = (t, r["x"], r["y"])
        while si < len(steps) and steps[si][0] <= t:   # sounds: footsteps and shots, heard by a team's living player near
            st, ss, sx, sy, _ = steps[si]; si += 1
            for tm in (2, 3):
                if team_of.get(ss) not in (None, tm) and any(math.hypot(m["x"] - sx, m["y"] - sy) < STEP_RANGE for m in alive[tm]):
                    heard_by[tm][ss] = (st, sx, sy)
        while hi < len(shots) and shots[hi][0] <= t:
            st, ss, sx, sy, _ = shots[hi]; hi += 1
            for tm in (2, 3):
                if team_of.get(ss) not in (None, tm) and any(math.hypot(m["x"] - sx, m["y"] - sy) < SHOT_RANGE for m in alive[tm]):
                    heard_by[tm][ss] = (st, sx, sy)
        smokes = active(smk_sp, t)
        fires = active(fire_sp, t)
        planted = next(((x, y) for pt, x, y in plants if rnd and rnd[0] <= pt <= t), None)
        nm = {2: len(alive[2]), 3: len(alive[3])}
        for r in rows:
            team, x, y, z = r["team"], r["x"], r["y"], r["z"]
            side = "T" if team == 2 else "CT"
            fighting = any(o["team"] != team and r["sid"] in o["sb"] for o in rows)
            # the info: the freshest of the team's sights and sounds of a living enemy
            best = None
            for kind, book in (("seen", seen_by[team]), ("heard", heard_by[team])):
                for e, (et, ex, ey) in book.items():
                    if not any(o["sid"] == e for o in alive[5 - team]):
                        continue
                    if best is None or et > best[1]:
                        best = (kind, et, ex, ey)
            info, ipt = "none", None
            if best:
                ab = age_band(t - best[1])
                if ab is not None:
                    d = math.hypot(best[2] - x, best[3] - y)
                    info = f"{best[0]}{ab}{'n' if t - best[1] <= 32 else ''}|{sector(best[2] - x, best[3] - y)}|{dist_band(d)}"
                    ipt = (best[2], best[3])
            mates = [m for m in alive[team] if m["sid"] != r["sid"]]
            near = sorted(mates, key=lambda m: math.hypot(m["x"] - x, m["y"] - y))
            n600 = sum(1 for m in near if math.hypot(m["x"] - x, m["y"] - y) < 600)
            mate_view = int(((near[0]["yaw"] + 360.0) % 360.0) // 45.0) if near and math.hypot(near[0]["x"] - x, near[0]["y"] - y) < 900 else -1
            sm = min(smokes, key=lambda s: math.hypot(s[0] - x, s[1] - y), default=None)
            sm_sec = sector(sm[0] - x, sm[1] - y) if sm and math.hypot(sm[0] - x, sm[1] - y) < SMOKE_RANGE else -1
            fire = any(math.hypot(fx - x, fy - y) < FIRE_RANGE for fx, fy in fires)
            flashed = any(0 <= t - ft <= 64 and math.hypot(fx - x, fy - y) < FLASH_RANGE for ft, fx, fy in flashes) or r["flash"] > 0.5
            phase = 0 if not rnd or t - rnd[0] < 25 * 64 else (1 if t - rnd[0] < 60 * 64 else 2)
            adv = (nm[team] > nm[5 - team]) - (nm[team] < nm[5 - team])
            hp = 0 if r["hp"] < 40 else (1 if r["hp"] < 80 else 2)
            cell = cell_of(side, x, y, z)
            # why he looks there: his info, a smoke's edge, as his teammate, his danger, else the place's standard
            yaw = r["yaw"]
            why = "standard"
            if ipt and adiff(yaw, yaw_to(ipt[0] - x, ipt[1] - y)) < 20:
                why = "info"
            elif sm_sec >= 0 and adiff(yaw, yaw_to(sm[0] - x, sm[1] - y)) < 30:
                why = "smoke"
            elif mate_view >= 0 and int(((yaw + 360.0) % 360.0) // 45.0) == mate_view:
                why = "same_as_mate"
            else:
                dz = danger.get(cell)
                if dz and dz[8] >= 3:
                    top = max(range(8), key=lambda i: dz[i])
                    if int(((yaw + 360.0 + 22.5) % 360.0) // 45.0) == top:
                        why = "danger"
            p1 = pos.get((t + 4 * STEP, r["sid"]))
            mv = None
            if p1:
                d1 = math.hypot(p1[0] - x, p1[1] - y)
                mv = "h" if d1 < 35.0 else ("w" if d1 < 140.0 else "r") + str(sector(p1[0] - x, p1[1] - y))
            seg = []
            for k in range(1, 17):
                q = pos.get((t + k * STEP, r["sid"]))
                if q is None:
                    break
                seg.append((round(q[0]), round(q[1]), round(q[2])))
            # the cases a cell keeps (a finer one per cell would be millions: those parameters go to the principles):
            # the place; with its info (kind, age, direction); with its weapon (awp, rifle, other) and the numbers too
            ik = "none" if info == "none" else info.split("|")[0].rstrip("n") + "|" + info.split("|")[1]
            # 29/10 04:00: two levels a cell (a third with the weapon and the numbers made 250 000 cases for 50 demos of a map
            # and filled the PC's memory): those go to the principles, across the cells
            keys = [cell, f"{cell}|{ik}"]
            out.append({"keys": keys, "fight": fighting, "ybin": int(((yaw + 360.0) % 360.0) // 10.0), "pitch": r["pitch"], "why": why,
                        "mv": mv, "seg": seg, "info": info.split("|")[0], "dist": info.split("|")[-1] if info != "none" else "-",
                        "adv": adv, "w": r["w"], "scoped": r["scoped"], "duck": r["duck"], "phase": phase, "planted": int(bool(planted)),
                        "mates": min(n600, 2), "smoke": int(sm_sec >= 0), "fire": int(fire), "flashed": int(flashed), "hp": hp})
    return mp, out


def add(model, principles, samples):
    for s in samples:
        tag = "F" if s["fight"] else "L"   # a fight's cases apart
        for lv, k in enumerate(s["keys"]):
            e = model.setdefault(f"{tag}{lv}|{k}", {"n": 0, "yaw": {}, "pitch": {}, "why": {}, "mv": {}, "seg": {}})
            e["n"] += 1
            b = str(s["ybin"])
            e["yaw"][b] = e["yaw"].get(b, 0) + 1
            e["pitch"][b] = round(e["pitch"].get(b, 0.0) + s["pitch"], 1)
            e["why"][s["why"]] = e["why"].get(s["why"], 0) + 1
            if s["mv"]:
                e["mv"][s["mv"]] = e["mv"].get(s["mv"], 0) + 1
                if s["mv"] not in e["seg"] and len(s["seg"]) >= 8 and lv >= 1:
                    e["seg"][s["mv"]] = s["seg"]
        if s["fight"]:
            continue
        for pk in (f"why|info={s['info']}|dist={s['dist']}", f"why|w={s['w']}|scoped={int(s['scoped'])}", f"why|adv={s['adv']}",
                   f"why|info={s['info']}|w={s['w']}|adv={s['adv']}", f"move|info={s['info']}|w={s['w']}|adv={s['adv']}",
                   f"move|info={s['info']}|dist={s['dist']}|mates={s['mates']}",
                   f"why|mates={s['mates']}", f"why|smoke={s['smoke']}", f"why|flashed={s['flashed']}", f"why|phase={s['phase']}|planted={s['planted']}",
                   f"move|info={s['info']}|adv={s['adv']}", f"move|w={s['w']}|duck={int(s['duck'])}", f"move|hp={s['hp']}|adv={s['adv']}",
                   f"move|fire={s['fire']}", f"move|phase={s['phase']}|planted={s['planted']}", f"move|mates={s['mates']}|info={s['info']}"):
            pr = principles.setdefault(pk, {})
            lab = s["why"] if pk.startswith("why") else (s["mv"][0] if s["mv"] else "?")
            pr[lab] = pr.get(lab, 0) + 1


def export(mp, out_dir=OUT, least=5):
    from wily.training import replay
    fn = os.path.join(out_dir, f"{mp}.json")
    if not os.path.exists(fn):
        return 0
    m = json.load(open(fn, encoding="utf-8"))
    tab = {}
    for k, e in m["cells"].items():
        if e["n"] < least:
            continue
        top = sorted(e["yaw"].items(), key=lambda x: (-x[1], int(x[0])))[:4]
        mv = max(e["mv"].items(), key=lambda x: (x[1], x[0])) if e["mv"] else ("h", 0)
        tab[k] = {"n": e["n"], "look": [[int(b) * 10 + 5 - (360 if int(b) * 10 + 5 > 180 else 0), round(e["pitch"][b] / c, 1), c] for b, c in top],
                  "why": max(e["why"].items(), key=lambda x: (x[1], x[0]))[0], "mv": mv[0], "mv_share": round(mv[1] / max(1, sum(e["mv"].values())), 2),
                  "way": e["seg"].get(mv[0]) or []}
    d = os.path.join(replay.COACH, "behavior")
    os.makedirs(d, exist_ok=True)
    json.dump({"cell": CELL, "zcell": ZC, "keys": tab}, open(os.path.join(d, f"{mp}.json"), "w", encoding="utf-8"))
    return len(tab)


def main(paths, out_dir=OUT):
    files = []
    for a in paths:
        files += sorted(glob.glob(os.path.join(a, "*.dem"))) if os.path.isdir(a) else [a]
    os.makedirs(out_dir, exist_ok=True)
    models, prin = {}, {}
    pfn = os.path.join(out_dir, "principles.json")
    prin = json.load(open(pfn, encoding="utf-8")) if os.path.exists(pfn) else {}
    for f in files:
        t0 = time.time()
        try:
            mp, s = demo_rows(f)
        except Exception as e:
            print(os.path.basename(f), "skipped:", str(e)[:120], flush=True)
            continue
        if mp not in models:
            fn = os.path.join(out_dir, f"{mp}.json")
            models[mp] = json.load(open(fn, encoding="utf-8")) if os.path.exists(fn) else {"demos": [], "cells": {}}
        m = models[mp]
        name = os.path.basename(f) if f.lower().endswith(".dem") else "/".join(os.path.normpath(f).split(os.sep)[-3:])
        if name in m["demos"]:
            continue
        add(m["cells"], prin, s)
        m["demos"].append(name)
        print(f"{name} {mp}: {len(s)} samples ({time.time() - t0:.0f} s)", flush=True)
    for mp, m in models.items():
        json.dump(m, open(os.path.join(out_dir, f"{mp}.json"), "w", encoding="utf-8"))
        print(mp, len(m["demos"]), "demos,", len(m["cells"]), "cases, exported", export(mp, out_dir), flush=True)
    json.dump(prin, open(pfn, "w", encoding="utf-8"), indent=1)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(args or [os.path.join("E:" + os.sep, "SteamLibrary", "steamapps", "common", "Counter-Strike Global Offensive", "game", "csgo", "replays")])
