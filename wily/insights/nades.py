"""Grenades that work, from where you play.

For every map and side, the throws of the base grouped by where they are thrown from and where they land, with what
they did (flash: enemies blinded and kills in the next 3 s; HE and molotov: damage to enemies; smoke: how often it is
thrown, rounds won when it is) and the moment of the round when they work best.
Then, for a player: the throws from the zones they play, the order in which to buy utility there, and their own habits
(what they throw, what they still hold when they die).
Writes out/population/nades.parquet (every throw) and nades_summary.json (groups per map and side).
Usage: python -m wily.insights.nades
"""
import json
import math
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

from wily.core import config
from wily.core.i18n import N_, tr, trn

OUT = os.path.join(config.OUT, "population", "nades.parquet")
SUMMARY = os.path.join(config.OUT, "population", "nades_summary.json")
# CS2 prices, checked on the equipment values of the demos (the CT incendiary costs 500 $)
PRICE = {"flash": 200, "smoke": 300, "he": 300, "molotov": {"T": 400, "CT": 500}}
TYPES = ("smoke", "flash", "molotov", "he")
TYPE_FR = {"flash": "flash", "smoke": "smoke", "he": "HE", "molotov": "molotov"}
ROUND_TIME = 115.0
# moments of the round, in seconds after the freeze time (the timer starts at 1:55)
WINDOWS = [("debut", 0, 20), ("prise", 20, 40), ("action", 40, 70), ("fin", 70, 999)]
WINDOW_FR = {"debut": N_("start of the round (1:55 to 1:35)"), "prise": N_("info gathering (1:35 to 1:15)"), "action": N_("site attack (1:15 to 0:45)"),
             "fin": N_("end of the round (after 0:45)"), "post": {"T": N_("after the plant"), "CT": N_("retake")}}
COLS = ["map", "match", "round", "t", "type", "thrower", "side", "zone", "land_zone", "X", "Y", "Z", "pitch", "yaw", "px", "py",
        "level", "land_px", "land_py", "land_level", "land_X", "land_Y", "land_Z", "jump", "speed", "crouch", "walk", "click",
        "flight_s", "damage", "enemies_blind", "mates_blind", "kills_after", "post", "won", "buy", "self_kill", "died"]


def humanize(z, mp=None):
    from wily.demos.map_analysis import humanize as h
    return h(z, mp) if isinstance(z, str) and z else None


def _timer(t):
    left = max(0.0, ROUND_TIME - float(t))
    return f"{int(left // 60)}:{int(left % 60):02d}"


VERSION = 5   # bump when the summary changes (texts, fields): the cache is rebuilt


def fresh(cached, stamp, slack=0.85):
    """A cache stamped "v<version>-<matches>-<time>" stays good while the base has not grown by more than 15% since: the
    base grows by itself now (grow.py, a match every few minutes) and computing it again each time made every plan
    wait (04/10: the grenade summary computed 6 times in one plan build)."""
    try:
        cv, cn, _ = str(cached).split("-")
        v, n, _ = str(stamp).split("-")
        return cv == v and int(cn) >= slack * int(n)
    except ValueError:
        return False


def _stamp():
    """The base's grenade files: how many, the latest date (16/10: from the matches' facts, ledger.py; only the folders
    without a meta.json, an extraction cut short, are checked one by one)."""
    from wily.core import ledger
    n, latest = 0, 0.0
    facts = ledger.match_facts() if os.path.exists(config.DEEP) else {}
    for f in facts.values():
        if f.get("grenades") is not None:
            n += 1
            latest = max(latest, f["grenades"])
    for mid in os.listdir(config.DEEP) if os.path.exists(config.DEEP) else []:
        if mid in facts:
            continue
        f = os.path.join(config.DEEP, mid, "grenades.parquet")
        if os.path.exists(f):
            n += 1
            latest = max(latest, os.path.getmtime(f))
    return f"v{VERSION}-{n}-{int(latest)}"


def map_counts():
    """{map: the base's matches with a grenade file} (its matches' facts, ledger.py)."""
    from wily.core import ledger
    c = Counter()
    for m, f in (ledger.match_facts() if os.path.exists(config.DEEP) else {}).items():
        if f.get("grenades") is not None and f.get("map") and not m.startswith("."):
            c[f["map"]] += 1
    return dict(c)


def fresh_maps(cached, now, slack=0.85, least=3):
    """No map grew by more than 15 % since (3 matches at least): the whole base's 15 % let a small map wait (22/10: the
    table 11 days old, Fachwerk's 34 matches in it of its 44, the base grown by 5 % only)."""
    if not isinstance(cached, dict):
        return False
    return all(n - cached.get(mp, 0) < least or cached.get(mp, 0) >= slack * n for mp, n in now.items())


def load_all(rebuild=False):
    """Every throw of the base (5v5 matchmaking demos), with the round's outcome, the side's buy and the bomb. Made
    again when the base or one of its maps grew (fresh, fresh_maps), from a copy of each match's rows that reads only
    the new or changed matches (22/10: ledger.gathered; it opened the 5,100 matches' four files each time)."""
    from wily.core import ledger
    meta_f = OUT + ".json"
    stamp, counts = _stamp(), map_counts()
    if not rebuild and os.path.exists(OUT) and os.path.exists(meta_f):
        try:
            meta = json.load(open(meta_f, encoding="utf-8"))
            if fresh(meta.get("stamp"), stamp) and fresh_maps(meta.get("maps"), counts):
                cached = pd.read_parquet(OUT)
                if "died" in cached and "land_Z" in cached:   # older files: built again once
                    return cached
        except ValueError:
            pass
    dirs = ledger.folders(config.DEEP)
    items = [(mid, os.path.join(config.DEEP, mid, "grenades.parquet"), st) for mid, st in dirs.items() if not mid.startswith(".")]
    df = ledger.gathered(f"nades_rows_v{VERSION}", items, prep=lambda g, mid: _match_rows(mid, g))
    df = df.reindex(columns=COLS) if len(df) else pd.DataFrame(columns=COLS)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_parquet(OUT)
    json.dump({"stamp": stamp, "maps": counts}, open(meta_f, "w", encoding="utf-8"))
    return df


def _match_rows(mid, g):
    """One match's throws (g: its grenades.parquet) as the table has them; none for a wingman, a hostage map, a match
    without its rounds."""
    none = pd.DataFrame(columns=COLS)
    d = os.path.join(config.DEEP, mid)
    fr = os.path.join(d, "rounds.parquet")
    if not os.path.exists(fr):
        return none
    R = pd.read_parquet(fr)
    if not len(R) or R.T_n.max() < 4 or R.CT_n.max() < 4:  # wingman: other habits
        return none
    try:
        mp = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8")).get("map")
    except (OSError, ValueError):
        return none
    if not mp or mp.startswith("cs_"):
        return none
    g = g[g.side.isin(["T", "CT"])] if len(g) else g
    if not len(g):
        return none
    R = R.set_index("round")
    plant = R["plant_t"] if "plant_t" in R else pd.Series(dtype=float)
    # a pop flash: the thrower himself kills a blinded enemy in the 3 s after it pops
    fd = os.path.join(d, "duels.parquet")
    sk = [0] * len(g)
    died = [0] * len(g)
    if os.path.exists(fd):
        DD = pd.read_parquet(fd, columns=["tick", "killer", "victim", "victim_flashed"])
        if "land_tick" in g:
            D = DD[DD.victim_flashed.fillna(False).astype(bool)]
            byk = {k: np.sort(x.tick.to_numpy()) for k, x in D.groupby("killer")}
            for i, (typ, thr, lt) in enumerate(zip(g.type, g.thrower, g.land_tick)):
                if typ == "flash" and lt == lt and thr in byk:
                    a = byk[thr]
                    sk[i] = int(np.searchsorted(a, lt + 3 * 64, side="right") - np.searchsorted(a, lt, side="right"))
        # the thrower killed in the 4 s after his throw: a lineup thrown where the enemy sees you (09/10, his stuff
        # drills: "et ici on peut me tuer", "la personne qui l'envoie peut mourir, parce que je la vois")
        byv = {v: np.sort(x.tick.to_numpy()) for v, x in DD.groupby("victim")}
        for i, (thr, tk) in enumerate(zip(g.thrower, g.tick)):
            a = byv.get(thr)
            if a is not None and tk == tk:
                died[i] = int(np.searchsorted(a, tk + 4 * 64, side="right") > np.searchsorted(a, tk, side="left"))
    g = g.assign(self_kill=sk, died=died)
    g = g.assign(map=mp, match=mid,
                 post=[bool(pd.notna(plant.get(r)) and t > plant.get(r)) for r, t in zip(g["round"], g.t)],
                 won=[R.winner.get(r) == s for r, s in zip(g["round"], g.side)],
                 buy=[(R[f"{s}_buy"].get(r) if f"{s}_buy" in R else None) for r, s in zip(g["round"], g.side)])
    for c in COLS:
        if c not in g:
            g[c] = None
    return g[COLS]


def _window(t, post):
    if post:
        return "post"
    for k, lo, hi in WINDOWS:
        if lo <= t < hi:
            return k
    return "fin"


def _eff(x, typ):
    """How well a set of throws worked: share of flashes that blind an enemy (1.5 s or more), damage of HE and molotovs."""
    if typ == "flash":
        return float((x.enemies_blind.fillna(0) >= 1).mean())
    if typ in ("he", "molotov"):
        return float(x.damage.fillna(0).mean())
    return None


def _how(b, fit=None):
    """How a throw was made, from the thrower at the release: in the air (the jumpthrow), moving (running over 150 u/s,
    walking under it or with the walk key), crouching; else standing still. fit: what its flight says (_phys): a bind's
    jump or W the demo does not show."""
    pat = fit[0] if fit else None
    how = []
    if pat in ("W", "WJ"):
        how.append("forward + jumpthrow" if pat == "WJ" else "run-throw (moving forward)")
    elif b.jump or pat == "jump":
        how.append("jumpthrow")
    if not how and b.speed > 150:
        how.append("running")
    elif not how and (b.walk or 20 < b.speed <= 150):
        how.append("walking")
    if b.crouch:
        how.append("crouching")
    return " + ".join(how) or "standing still"


# The throw that sent a grenade where it went off (09/10, his stuff drills: "non, c'est une running molly", "c'est
# gauche-droite", "il faut prendre le repère debout puis jump"): a CS2 demo writes the thrower at the click's release,
# still on the ground and still standing when a bind jumps or runs on that tick, and the grenade leaves 0.11 s later
# with his velocity then. Its flight tells: CS2 throws 10° above the aim (the aim's angle x 0.89), at 675 u/s with a
# left click, 439 with both, 203 with a right one, plus 1.25 x the thrower's own velocity; gravity 320 u/s². Fitted
# on the base: 1.61 s from leaving the hand to a flash's or an HE's pop, a molotov goes off on the ground. Only a clean
# fit counts (a bounce off a wall fits none): nothing added (standing), a bind's jump (about 265 u/s up), a bind's W
# (about 190 u/s forward), both.
PHYS_DT, PHYS_G2 = 0.11, 160.0
PHYS_V = {"left": 675.0, "middle": 438.75, "right": 202.5}
PHYS_DZ = {"left": 0.0, "middle": -6.0, "right": -12.0}


def _phys(X, Y, Z, pitch, yaw, crouch, lx, ly, lz, flight):
    """-> (pattern: still | jump | W | WJ, click: left | middle | right), or None when no clean throw explains it."""
    try:
        vals = [float(v) for v in (X, Y, Z, pitch, yaw, lx, ly, lz, flight)]
    except (TypeError, ValueError):
        return None
    if any(v != v for v in vals) or vals[8] - PHYS_DT <= 0.2:
        return None
    X, Y, Z, pitch, yaw, lx, ly, lz, flight = vals
    T = flight - PHYS_DT
    # it went off on the aim's line (a jump or a W adds nothing sideways): off it, it bounced off a wall
    if math.hypot(lx - X, ly - Y) < 150 or abs(((math.degrees(math.atan2(ly - Y, lx - X)) - yaw) + 180) % 360 - 180) > 6:
        return None
    el, yr = math.radians(10.0 - pitch * (80.0 / 90.0)), math.radians(yaw)
    F = np.array([math.cos(el) * math.cos(yr), math.cos(el) * math.sin(yr), math.sin(el)])
    to = np.array([lx - X, ly - Y, lz - Z - (46.0 if crouch else 64.0) + PHYS_G2 * T * T]) - F * 16.0
    fit = []   # (how far from the throw, pattern, click, clean)
    for click, a in PHYS_V.items():
        u = (to - np.array([0.0, 0.0, PHYS_DZ[click]])) / T - a * F   # 1.25 x the thrower's velocity as it left
        fw = u[0] * math.cos(yr) + u[1] * math.sin(yr)
        side = -u[0] * math.sin(yr) + u[1] * math.cos(yr)
        flat, up = math.hypot(fw, side), float(u[2])
        run = click != "right"   # a running lob: a bounce more likely than that throw
        fit += [(flat + abs(up), "still", click, flat < 60 and abs(up) < 70),
                (flat + abs(up - 265), "jump", click, flat < 70 and 190 < up < 340),
                (abs(fw - 190) + abs(side) + abs(up), "W", click, run and 110 < fw < 340 and abs(side) < 70 and abs(up) < 70),
                (abs(fw - 190) + abs(side) + abs(up - 265), "WJ", click, run and 110 < fw < 340 and abs(side) < 70 and 190 < up < 340)]
    fit.sort()
    # the throw that explains it best, clean and well ahead of any other (a bounce fits two of them about as badly: the
    # CT flash to Banana, "bizarre... soit un running, soit gauche-droite")
    best, second = fit[0], fit[1]
    return best[1:3] if best[3] and best[0] <= 0.75 * second[0] else None


def _lineup_fit(c, b, typ):
    """How b's lineup is thrown, from flights (flash, HE, molotov: a smoke rolls on): b's own clean fit, else the one most
    of the clean fits of the throws from its spot and aim agree on (12 u, 0.7°)."""
    if typ not in ("flash", "he", "molotov") or "land_Z" not in c:
        return None
    one = lambda r: _phys(r.X, r.Y, r.Z, r.pitch, r.yaw, bool(r.crouch), r.land_X, r.land_Y, r.land_Z, r.flight_s)
    own = one(b)
    if own:
        return own
    same = c[((c.X - b.X).abs() < 12) & ((c.Y - b.Y).abs() < 12) & ((c.pitch - b.pitch).abs() < 0.7)
             & ((((c.yaw - b.yaw) + 180) % 360 - 180).abs() < 0.7) & (c.crouch.astype(bool) == bool(b.crouch))]
    fits = [f for f in (one(r) for r in same.head(40).itertuples()) if f]
    if len(fits) < 2:
        return None
    top, n = Counter(fits).most_common(1)[0]
    return top if n >= 0.6 * len(fits) else None


def groups(df, side_rounds):
    """Throws grouped by (type, thrown from, lands in), per map and side, with effect and timing."""
    out = {}
    df = df[df.zone.notna() & df.land_zone.notna() & (df.zone != "?") & (df.land_zone != "?")]
    for (mp, side), g in df.groupby(["map", "side"]):
        rounds = side_rounds.get((mp, side), 0)
        if rounds < 60:
            continue
        # after a plant, the rounds still running at each 10 s slice and how many this side won: a late throw only
        # happens in a round that lasted, so each slice is read against those (else late throws look like wins)
        pr = g[g.post.astype(bool) & g.te.notna()].drop_duplicates(["match", "round"]) if "te" in g else g.iloc[:0]
        alive = [float(pr[pr.te >= 10 * b].won.mean()) if int((pr.te >= 10 * b).sum()) >= 20 else None for b in range(4)]
        res = {}
        for typ in TYPES:
            t = g[g.type == typ]
            if len(t) < 20:
                continue
            prior = _eff(t, typ)
            if typ == "flash":
                prior_k = float((t.kills_after.fillna(0) >= 1).mean())
                prior_s = float((t.self_kill.fillna(0) >= 1).mean()) if "self_kill" in t else 0.0
            full = t[t.buy == "full"]
            base_win = float(g[g.buy == "full"].drop_duplicates(["match", "round"]).won.mean()) if typ == "smoke" and len(full) else None
            lst = []
            for (z, lz), c in t.groupby(["zone", "land_zone"]):
                if len(c) < 8:
                    continue
                n = len(c)
                e = {"n": int(n), "players": int(c.thrower.nunique()), "per100": round(100 * n / rounds, 1)}
                if "died" in c:   # how often its thrower dies in the 4 s after it (seen from where it lands, or in a fight)
                    e["died"] = round(100 * float(c.died.fillna(0).astype(float).mean()))
                if typ == "flash":
                    blind = float((c.enemies_blind.fillna(0) >= 1).sum())
                    e["blind"] = round(100 * (blind + prior * 10) / (n + 10))
                    e["kill"] = round(100 * (float((c.kills_after.fillna(0) >= 1).sum()) + prior_k * 10) / (n + 10))
                    e["team"] = round(100 * float((c.mates_blind.fillna(0) >= 1).mean()))
                    e["self"] = round(100 * (float((c.self_kill.fillna(0) >= 1).sum()) + prior_s * 10) / (n + 10)) if "self_kill" in c else None   # pop flash
                    score = e["blind"] / 100 + 0.5 * e["kill"] / 100 - 0.5 * e["team"] / 100
                elif typ in ("he", "molotov"):
                    e["dmg"] = round((float(c.damage.fillna(0).sum()) + prior * 10) / (n + 10))
                    e["hit"] = round(100 * float((c.damage.fillna(0) > 0).mean()))
                    # a molotov mostly closes a passage (the enemy waits or goes around): how often it is used counts
                    # as much as its damage; an HE is worth its damage
                    score = e["dmg"] / 25 if typ == "he" else 0.6 * min(1.0, e["per100"] / 25) + 0.4 * min(1.0, e["dmg"] / 20)
                else:
                    fc = c[c.buy == "full"].drop_duplicates(["match", "round"])
                    if len(fc) >= 10 and base_win is not None:
                        e["win"] = round(100 * float(fc.won.mean()))
                        e["base_win"] = round(100 * base_win)
                    score = min(1.0, e["per100"] / 25)
                # when it is thrown, and when it works
                c = c.assign(w=[_window(tt, p) for tt, p in zip(c.t, c.post)])
                wins = {}
                for w, cw in c.groupby("w"):
                    wins[w] = {"n": int(len(cw)), "t": round(float(cw.t.median()), 1)}   # its usual moment in that window (Live's timeline, 09/10)
                    ew = _eff(cw, typ)
                    if ew is not None:
                        wins[w]["eff"] = round(100 * (ew * len(cw) + prior * 5) / (len(cw) + 5)) if typ == "flash" else round((ew * len(cw) + prior * 5) / (len(cw) + 5))
                # after the plant, when on the bomb's clock (10/10, the user: "la molo si tu l'envoies à 15 secondes de la
                # fin, t'as plus de chance de gagner le round que si tu l'envoies au tout début"): its usual moment after
                # the plant and the 10 s slice whose rounds were won most (few throws: closer to all of them)
                post_tp = None
                pc = c[c.post.astype(bool) & c.tp.notna()] if "tp" in c else c.iloc[:0]
                if len(pc) >= 5:
                    w0, sl = float(pc.won.mean()), (pc.tp // 10).clip(0, 3)
                    sh = {}
                    for b, cb in pc.groupby(sl):
                        a = alive[int(b)] if alive[int(b)] is not None else w0
                        if len(cb) >= 3:
                            sh[int(b)] = ((len(cb) * float(cb.won.mean()) + 5 * a) / (len(cb) + 5), a)
                    bb = max(sh, key=lambda b: sh[b][0] - sh[b][1]) if sh else None   # the slice that adds most to the rounds still running
                    post_tp = {"t": round(float(pc.tp.median()), 1),
                               **({"best": round(float(pc[sl == bb].tp.median()), 1), "win": round(100 * sh[bb][0]), "base": round(100 * sh[bb][1])}
                                  if bb is not None else {"base": round(100 * w0)})}
                usual = max(wins, key=lambda k: wins[k]["n"])
                best = usual
                if typ != "smoke":
                    ok = {k: v for k, v in wins.items() if v["n"] >= 5 and "eff" in v}
                    if ok:
                        best = max(ok, key=lambda k: ok[k]["eff"])
                # the usual way to throw it: most common spot among throws you can repeat from a spot (standing, crouching or
                # a jumpthrow without moving): a running throw's release point is not where you start running (04/10:
                # "you say running jump: it goes way too far")
                rep = c.assign(cell=list(zip((c.px // 20).astype(int), (c.py // 20).astype(int))), repro=c.speed < 20)
                pool = rep[rep.repro] if rep.repro.any() else rep
                cell = pool.cell.value_counts().index[0]
                cand = pool[pool.cell == cell]
                # a jumpthrow lineup: the demos often miss the jump (a jumpthrow bind releases on the tick of the jump,
                # still on the ground), so a third of the spot's throws in the air make it one, and its reference throw
                # is one of them (06/10, Overpass smoke to Canal: 44% in the air, said "standing still")
                if cand.jump.astype(bool).mean() >= 0.3 and cand.jump.astype(bool).any():
                    cand = cand[cand.jump.astype(bool)]
                if typ == "flash":
                    cand = cand.sort_values("enemies_blind", ascending=False)
                elif typ in ("he", "molotov"):
                    cand = cand.sort_values("damage", ascending=False)
                b = cand.iloc[0]
                fit = _lineup_fit(c, b, typ)   # the bind's jump or W and the click its flight tells (09/10)
                lst.append({"from_key": z, "from": humanize(z, mp), "to_key": lz, "to": humanize(lz, mp), "score": round(float(score), 3), **e,
                            "t_med": round(float(c.t.median()), 1), "timer": _timer(c.t.median()),
                            "timer_span": [_timer(c.t.quantile(0.25)), _timer(c.t.quantile(0.75))],
                            "windows": wins, "usual": usual, "best": best, "post": round(100 * float(c.post.mean())), "post_tp": post_tp,
                            "how": _how(b, fit), "click": fit[1] if fit else b.click, "flight_s": None if pd.isna(b.flight_s) else float(b.flight_s),
                            "from_px": [round(float(cand.px.mean())), round(float(cand.py.mean()))], "level": b.level,
                            "to_px": [round(float(c.land_px.median())), round(float(c.land_py.median()))], "land_level": b.land_level,
                            "setpos": f"setpos {b.X:.1f} {b.Y:.1f} {b.Z:.1f}; setang {b.pitch:.2f} {b.yaw:.2f} 0"})
            lst.sort(key=lambda x: -x["score"])
            res[typ] = {"prior": None if prior is None else (round(100 * prior) if typ == "flash" else round(prior)), "groups": lst}
            if typ == "flash":
                res[typ]["self_prior"] = round(100 * prior_s, 1)   # the map's pop flashes: the thrower's own kill after it
        out.setdefault(mp, {})[side] = {"rounds": int(rounds), "types": res}
    return out


def _plant_ts():
    """(match, round) -> the plant's moment and the round's end, seconds into the round."""
    out = {}
    for mid in os.listdir(config.DEEP):
        try:
            R = pd.read_parquet(os.path.join(config.DEEP, mid, "rounds.parquet"), columns=["round", "plant_t", "end_t"])
        except Exception:
            continue
        for r, t, e in zip(R["round"], R["plant_t"], R["end_t"]):
            if t is not None and t == t:
                out[(mid, int(r))] = (float(t), float(e) if e is not None and e == e else np.nan)
    return out


def _side_rounds():
    """Rounds played per map and side in the base (5v5 only), to turn counts into 'per 100 rounds'."""
    cnt = {}
    for mid in os.listdir(config.DEEP):
        d = os.path.join(config.DEEP, mid)
        fr = os.path.join(d, "rounds.parquet")
        if not os.path.exists(fr):
            continue
        R = pd.read_parquet(fr, columns=["T_n", "CT_n"])
        if not len(R) or R.T_n.max() < 4 or R.CT_n.max() < 4:
            continue
        try:
            mp = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8")).get("map")
        except (OSError, ValueError):
            continue
        for s in ("T", "CT"):
            cnt[(mp, s)] = cnt.get((mp, s), 0) + len(R)
    return cnt


BUY_NAME = {"flash": "flash", "smoke": "smoke", "HE": "he", "molotov": "molotov"}


def payoff():
    """What utility pays off, from the buys of every player of the base:
    rounds won by number of grenades bought per type of round, and, when only one grenade is bought (force and full
    buys), rounds won by its type against no grenade at all, per side (pulled toward 'no grenade' when rare)."""
    from wily.insights import buys
    B = buys.load()
    if not len(B):
        return {}
    out = {"count": {}, "single": {}}
    for rt in ("eco", "force", "full"):
        x = B[B.rtype == rt]
        x = x.assign(nn=x.util_n.clip(upper=4))
        t = x.groupby("nn").agg(n=("won", "size"), win=("won", "mean"), adr=("damage", "mean"))
        out["count"][rt] = {int(k): {"n": int(v.n), "win": round(100 * v.win), "adr": round(v.adr)} for k, v in t.iterrows() if v.n >= 30}
    B = B[B.util_known.fillna(False).astype(bool) & B.rtype.isin(["force", "full"])]
    for side in ("T", "CT"):
        x = B[B.side == side]
        none = x[x.util_n == 0]
        w0 = float(none.won.mean()) if len(none) else 0.5
        res = {"none": {"n": int(len(none)), "win": round(100 * w0)}}
        one = x[x.util_n == 1]
        for u, g in one.groupby("util"):
            typ = BUY_NAME.get(u)
            if typ:
                k = 150  # rare buys stay close to 'no grenade'
                res[typ] = {"n": int(len(g)), "win": round(100 * float(g.won.mean())),
                            "uplift": round(100 * ((float(g.won.sum()) + w0 * k) / (len(g) + k) - w0), 1)}
        out["single"][side] = res
    return out


def summary(rebuild=False):
    stamp, counts = _stamp(), map_counts()
    if not rebuild and os.path.exists(SUMMARY):
        try:
            cur = json.load(open(SUMMARY, encoding="utf-8"))
            if fresh(cur.get("_stamp"), stamp) and fresh_maps(cur.get("_maps"), counts):
                return cur
        except ValueError:
            pass
    df = load_all()
    PT = _plant_ts()   # each throw after a plant: its seconds since the plant
    key = [(m, int(r)) for m, r in zip(df["match"], df["round"])]
    df = df.assign(tp=[t - PT[k][0] if p and k in PT and t == t else np.nan for k, t, p in zip(key, df["t"], df["post"])],
                   te=[PT[k][1] - PT[k][0] if p and k in PT else np.nan for k, p in zip(key, df["post"])])   # how long the round ran after the plant
    res = {"_stamp": stamp, "_maps": counts, "maps": groups(df, _side_rounds()), "payoff": payoff(), "price": PRICE, "windows": WINDOW_FR}
    json.dump(res, open(SUMMARY, "w", encoding="utf-8"), ensure_ascii=False)
    return res


def _my_zones(cross, mp, side, top=4, min_presence=5.0):
    """The zones you play on this side of this map (everybody goes through the spawns: not a choice)."""
    for m in (cross or {}).get("maps", []):
        if m["map"] == mp:
            zs = [z for z in (m.get("sides", {}).get(side) or {}).get("zones", [])
                  if (z.get("presence") or 0) >= min_presence and "spawn" not in str(z.get("key", "")).lower()]
            return [z["key"] for z in sorted(zs, key=lambda z: -z["presence"])[:top]], {z["key"]: z["presence"] for z in zs}
    return [], {}


def _role(typ, x):
    """anti_rush: a molotov or an HE usually thrown in the first 25 s at an entrance; block: a smoke or a molotov
    that closes an entrance (any time); damage: an HE later in the round."""
    if typ in ("molotov", "he") and (x.get("usual") == "debut" or (x.get("t_med") or 99) <= 25):
        return "anti_rush"
    if typ == "flash":
        return "flash"   # blinds the Ts as they come through
    return "block" if typ in ("smoke", "molotov") else "damage"


POOL = ("from", "to", "from_key", "to_key", "from_px", "to_px", "level", "land_level", "timer", "t_med", "how", "click", "n",
        "per100", "blind", "kill", "dmg", "win", "base_win", "usual", "best", "post")
SLIM = ("from", "to", "from_px", "to_px", "level", "land_level", "timer", "t_med", "how", "click", "setpos", "n", "per100",
        "blind", "kill", "team", "dmg", "hit", "win", "base_win", "usual", "best", "self")


def lane_picks(M, lanes_mp, zones):
    """For each entrance of the Ts (lanes.py): the smoke, molotov, HE and flash that land on it, thrown from your zones
    when some do (else the base's best), with their role. A flash that rarely blinds anyone is left out."""
    out = {}
    for typ, T in M["types"].items():
        for x in T["groups"]:
            if typ == "flash" and (x.get("blind") or 0) < 25:
                continue
            for site, ls in (lanes_mp or {}).items():
                for i, ln in enumerate(ls or []):
                    if x["to"] not in ln.get("zones", []):
                        continue
                    key, yours = f"{site}{i}", (not zones) or x["from_key"] in zones
                    cur = out.setdefault(key, {}).get(typ)
                    if cur is None or (yours, x["score"]) > (cur["yours"], cur["score"]):
                        out[key][typ] = {**{k: x[k] for k in SLIM if k in x}, "score": x["score"], "yours": yours, "role": _role(typ, x)}
    return out


def for_player(sid, maps, cross=None, stats=None, lanes=None):
    """Per map and side: the grenades that work from the zones you play, in buying order, with when and how to throw
    them; and your habits (grenades you throw, grenades you still hold when you die)."""
    S = summary()
    df = load_all()
    mine = df[df.thrower == int(sid)] if len(df) else df
    res = {"price": PRICE, "windows": WINDOW_FR, "payoff": S.get("payoff", {}), "maps": {}}
    for mp in maps:
        for side in ("T", "CT"):
            M = (S["maps"].get(mp) or {}).get(side)
            if not M:
                continue
            zones, pres = _my_zones(cross, mp, side)
            own = mine[(mine["map"] == mp) & (mine.side == side)]
            entry = {"zones": [humanize(z, mp) for z in zones], "personal": bool(zones), "types": {}}
            share = {}
            for typ, T in M["types"].items():
                gs = T["groups"]
                pick = [dict(x) for x in gs if x["from_key"] in zones][:3] if zones else []
                if typ == "flash":   # a pop flash from your zones (you peek behind it yourself: your flashes rarely serve a teammate)
                    sp = T.get("self_prior") or 0
                    pops = sorted([x for x in gs if (not zones or x["from_key"] in zones) and (x.get("self") or 0) >= max(5, 2 * sp) and x["n"] >= 10],
                                  key=lambda x: -(x.get("self") or 0))
                    if pops and all(p_["from_key"] != pops[0]["from_key"] or p_["to_key"] != pops[0]["to_key"] for p_ in pick):
                        pick.append(dict(pops[0]))
                    for p_ in pick:
                        p_["pop"] = (p_.get("self") or 0) >= max(5, 2 * sp)
                other = False
                if not pick:  # nothing thrown from your zones: the best of the side
                    pick, other = [dict(x) for x in gs[:2]], True
                for x in pick:
                    o = own[(own.type == typ) & (own.zone == x["from_key"]) & (own.land_zone == x["to_key"])]
                    x["mine"] = int(len(o))
                    x.pop("windows", None) if typ == "smoke" else None
                # after the plant (retake for the CT, post-plant for the T): throws mostly made once the bomb is down
                post = [dict(x) for x in gs if x.get("post", 0) >= 30]
                post.sort(key=lambda x: (x["from_key"] not in zones, -x["score"]))
                for x in post:
                    x.pop("windows", None)
                entry["types"][typ] = {"prior": T["prior"], "picks": pick, "elsewhere": other, "post": post[:2]}
                share[typ] = sum(x["n"] for x in gs if x["from_key"] in zones) if zones else sum(x["n"] for x in gs[:5])
            # buying order when money is short: what one grenade alone adds to the rounds won on this side (base),
            # plus a bonus when it works well from your zones; a flash that rarely blinds from there is left out
            single = (S.get("payoff", {}).get("single") or {}).get(side, {})
            tot = sum(share.values()) or 1
            order = []
            for typ in TYPES:
                p = entry["types"].get(typ, {}).get("picks") or []
                if not p:
                    continue
                best = p[0]
                if typ == "flash" and best.get("blind", 0) < 20:
                    continue
                strong = (typ == "flash" and best.get("blind", 0) >= 40) or (typ == "he" and best.get("dmg", 0) >= 12) or                          (typ == "smoke" and (best.get("per100", 0) >= 10 or (best.get("win") or 0) - (best.get("base_win") or 0) >= 5)) or                          (typ == "molotov" and best.get("per100", 0) >= 10)
                up = (single.get(typ) or {}).get("uplift", 0.0)
                price = PRICE[typ][side] if isinstance(PRICE[typ], dict) else PRICE[typ]
                order.append({"type": typ, "price": price, "value": round(up + (2 if strong else 0), 1), "uplift": up,
                              "alone": single.get(typ), "strong": strong, "share": round(100 * share.get(typ, 0) / tot),
                              "to": best["to"], "from": best["from"]})
            order.sort(key=lambda o: -o["value"])
            entry["order"] = order
            # every lineup of the base on this side (not only from your zones): the page picks the ones of the path or
            # the site you choose (numpad 1-2-3 on T, 7 / 9 on CT)
            pool = []
            for typ, T in M["types"].items():
                for x in T["groups"]:
                    if typ == "flash" and (x.get("blind") or 0) < 25:
                        continue
                    pool.append({**{k: x[k] for k in POOL if k in x}, "type": typ, "score": x["score"]})
            pool.sort(key=lambda x: -x["score"])
            entry["pool"] = pool[:48]
            entry["none"] = single.get("none")
            entry["mine"] = {t: int((own.type == t).sum()) for t in TYPES}
            if side == "CT" and lanes and lanes.get(mp):   # the grenades that close each entrance of the Ts
                entry["lanes"] = lane_picks(M, lanes[mp], zones)
            res["maps"].setdefault(mp, {})[side] = entry
    # habits: grenades still in hand at death, and grenades thrown per round, against the base
    if stats:
        unused = sum((s.get("utility") or {}).get("grenades_unused_at_death") or 0 for s in stats)
        deaths = sum((s.get("overview") or {}).get("deaths") or 0 for s in stats)
        res["unused_per_death"] = round(unused / deaths, 2) if deaths else None
        res["unused_last"] = [{"map": s.get("map"), "unused": (s.get("utility") or {}).get("grenades_unused_at_death")} for s in stats[-5:]]
    if len(df):
        rounds_me = mine.groupby(["match", "round"]).ngroups if len(mine) else 0
        per = df.groupby(["match", "thrower"]).size()
        res["thrown_per_match_base"] = round(float(per.median()), 1) if len(per) else None
        res["thrown_per_match_me"] = round(float(mine.groupby("match").size().median()), 1) if len(mine) else None
    return res


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    s = summary(rebuild=True)
    print({mp: {side: {t: len(v["groups"]) for t, v in S["types"].items()} for side, S in sides.items()} for mp, sides in s["maps"].items()})
