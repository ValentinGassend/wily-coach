"""Experiments: the player tests something for a few games (a weapon, a position, a habit, a warm-up, a session limit)
and the coach measures it on the following matches, compared with the matches before the start.

Stored in out/experiments/<steamid>.json. Evaluated from the analyzed matches (no manual input).
"""
import datetime as dt
import json
import math
import os
import uuid

import pandas as pd

from wily.core import config
from wily.coaching import context
from wily.core.i18n import N_, tr

DIR = os.path.join(config.OUT, "experiments")

# metric: (label, unit, higher_is_better)
METRICS = {
    "rating": (N_("match rating (≈ HLTV 2.0 rating)"), "", True),
    "adr": (N_("damage per round"), "", True),
    "traded_pct": (N_("deaths traded"), "%", True),
    "nades_unused_pr": (N_("grenades that died with you per round"), "", False),
    "xhair": (N_("crosshair offset before the duel"), "°", False),
    "pistol_moving": (N_("pistol shots fired while moving"), "%", False),
    "isolated_pr": (N_("isolated deaths per round"), "", False),
    "adv_throw": (N_("man advantages thrown (per advantage round)"), "%", False),
    "rot_died": (N_("deaths during a rotation"), "%", False),
    "rt_solo": (N_("deaths alone in a retake"), "%", False),
    "steps_alone_pr": (N_("audible steps when you are alone, per round"), "", False),
    "open_win": (N_("opening duels won"), "%", True),
    "weapon_duels": (N_("duels won with the weapon"), "%", True),
    "weapon_adr": (N_("damage per round with the weapon"), "", True),
    "zone_duels": (N_("duels won in the zone"), "%", True),
    "first_game": (N_("rating of the first game of the session"), "", True),
    "ct_full_duels": (N_("duels won on your CT full buys"), "%", True),
    "call_before_death": (N_("deaths with a call in the 10 s before"), "%", True),
}

TEMPLATES = {
    "weapon_swap": {"cat": "Weapon", "title": N_("Replace {weapon} with {alt}"), "metric": "weapon_duels", "min": 25, "unit_n": "duels",
                    "how": [N_("For 5 games, buy {alt} every time you would have bought {weapon}."), N_("The coach compares your duels and your damage with each of the two weapons.")]},
    "weapon_keep": {"cat": "Weapon", "title": N_("Play {weapon} first"), "metric": "weapon_adr", "min": 20, "unit_n": "rounds",
                    "how": [N_("Buy {weapon} as soon as the economy allows, for 5 games.")]},
    "zone": {"cat": "Position", "title": "Play {zone_name} on {map_name} as {side}", "metric": "zone_duels", "min": 12, "unit_n": "duels",
             "how": ["On {map_name} as {side}, take {zone_name} whenever it's free, for 3 to 5 games on this map.", "The coach measures your duels in the zone."]},
    "trade_distance": {"cat": "Habit", "title": N_("Stay within trade distance"), "metric": "isolated_pr", "min": 4, "unit_n": "games",
                       "how": [N_("Before every duel, a teammate must be able to avenge you within 2 seconds."), N_("If nobody covers you: fall back or wait.")]},
    "nades_40s": {"cat": "Habit", "title": N_("40-second rule: grenades thrown"), "metric": "nades_unused_pr", "min": 4, "unit_n": "games",
                  "how": [N_("As T, at 1:15 on the clock, all your grenades must be gone."), N_("As CT, slow down the first contact with a molotov or an HE.")]},
    "advantage": {"cat": "Habit", "title": N_("With a man advantage, I play the trade"), "metric": "adv_throw", "min": 4, "unit_n": "games",
                  "how": [N_("As soon as your team has one more player: no more solo duels, you play in pairs and run the clock."), N_("Regroup on a site rather than looking for one more kill.")]},
    "rotation": {"cat": "Mi-round", "title": N_("Rotations through the safe route, on the right signal"), "metric": "rot_died", "min": 4, "unit_n": "games",
                 "how": [N_("Only rotate on solid info (bomb seen, 3 players, 2 flashes or more)."), N_("Take the route that keeps you covered and call 'rotating'.")]},
    "retake_group": {"cat": "Mi-round", "title": N_("Grouped retake, never alone"), "metric": "rt_solo", "min": 4, "unit_n": "games",
                     "how": [N_("Bomb planted: wait for your teammates and go in on the same flash."), N_("Alone against 3 or more with little time: save your weapon.")]},
    "silent": {"cat": "Habit", "title": N_("Walk (Shift) when you are alone"), "metric": "steps_alone_pr", "min": 4, "unit_n": "games",
               "how": [N_("As soon as you are more than 1,200 units away from a teammate as T, and in every clutch: Shift."), N_("Silent reload (hold R) if an enemy is close.")]},
    "prefire": {"cat": "Training", "title": N_("10 min of prefire before playing"), "metric": "xhair", "min": 5, "unit_n": "games",
                "how": [N_("Before each session: 10 minutes of a prefire map (workshop) on the map you are about to play."), N_("In game: crosshair at head height on the next angle, not on the floor.")]},
    "counter_strafe": {"cat": "Training", "title": N_("Counter-strafe with pistols"), "metric": "pistol_moving", "min": 5, "unit_n": "games",
                       "how": [N_("Aim Botz, 5 min with a pistol: A-D, stop, one shot, never while moving."), N_("Pistol-only Deathmatch for 5 min before the session.")]},
    "warmup": {"cat": "Session", "title": N_("15-min warm-up before the 1st game"), "metric": "first_game", "min": 4, "unit_n": "sessions",
               "how": [N_("5 min of Aim Botz or Aim Rush, 5 min of Deathmatch, 5 min of lineups on the day's map."), N_("Note it in the pre-session journal.")]},
    "session_limit": {"cat": "Session", "title": N_("At most 3 games per session, stop after 2 losses"), "metric": "rating", "min": 6, "unit_n": "games",
                      "how": [N_("After 3 games or 2 losses in a row: a break of at least 30 minutes, or end of session.")]},
    "full_rifle_ct": {"cat": "Weapon", "title": N_("Full buy as CT: an M4, not the MAG-7"), "metric": "ct_full_duels", "min": 25, "unit_n": "duels",
                      "how": [N_("As CT, when your team full-buys: M4A1-S or M4A4, not the MAG-7 (the buy card shows the M4)."),
                              N_("Keep the MAG-7 for force-buys if you like it there."),
                              N_("The coach compares your duels on CT full buys before and after.")]},
    "calls": {"cat": "Habit", "title": N_("Call before the duel, say 'flash'"), "metric": "call_before_death", "min": 4, "unit_n": "games",
              "how": [N_("Say what you see (where, how many) before you take the duel, not after: your rounds with a call before your death are won far more often."),
                      N_("Say 'flash' before you throw it: your teammates turn away and peek behind it."),
                      N_("Measured on your recorded matches (Your calls on).")]},
    "opening": {"cat": "Habit", "title": N_("Only open with a flash"), "metric": "open_win", "min": 5, "unit_n": "games",
                "how": [N_("No more dry opening duels: flash (yours or a teammate's) or you leave the opening to someone else.")]},
}


def _file(sid):
    return os.path.join(DIR, f"{sid}.json")


def load(sid):
    f = _file(sid)
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else []


def save(sid, exps):
    os.makedirs(DIR, exist_ok=True)
    json.dump(exps, open(_file(sid), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def title_of(template, params):
    t = TEMPLATES[template]
    p = dict(params or {})
    if "map" in p:
        p["map_name"] = p["map"].split("_")[-1].capitalize()
    return tr(t["title"], **p)


def start(sid, template, params=None):
    if template not in TEMPLATES:
        raise ValueError("unknown experiment")
    exps = load(sid)
    e = {"id": uuid.uuid4().hex[:8], "template": template, "params": params or {}, "title": title_of(template, params),
         "started": dt.datetime.now().isoformat(timespec="minutes"), "status": "active", "ended": None}
    exps.append(e)
    save(sid, exps)
    return e


def stop(sid, eid, status="stopped"):
    exps = load(sid)
    for e in exps:
        if e["id"] == eid:
            e["status"] = status
            e["ended"] = dt.datetime.now().isoformat(timespec="minutes")
    save(sid, exps)
    return exps


# ---------- per-match values ----------
def _mid_rows(mid, sid):
    f = os.path.join(config.OUT, "population", "midround", f"{mid}.parquet")
    if not os.path.exists(f):
        return None
    r = pd.read_parquet(f)
    r = r[r.steamid == sid]
    return r.iloc[0] if len(r) else None


_VA = {"sig": None, "idx": {}}


def _voice_by_match():
    """{match: its first aligned recording's analysis with deaths}, the analyses read once while none changes (16/10:
    every analysis read again for each match of each experiment, 1,936 files a plan)."""
    import glob
    fs = glob.glob(os.path.join(config.OUT, "voice", "*.analysis.json"))
    sig = []
    for fa in fs:
        try:
            st = os.stat(fa)
            sig.append((fa, st.st_mtime_ns, st.st_size))
        except OSError:
            sig.append((fa, None, None))
    if sig != _VA["sig"]:
        idx = {}
        for fa in fs:
            try:
                a = json.load(open(fa, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if a.get("aligned") and a.get("deaths"):
                idx.setdefault(str(a.get("match")), {k: a[k] for k in ("deaths", "silent_deaths") if k in a})
        _VA.update(sig=sig, idx=idx)
    return _VA["idx"]


def match_values(sid, m, st, template, params):
    """-> (value, weight) or (k, n) counts for proportion metrics, for one match."""
    metric = TEMPLATES[template]["metric"]
    o = st["overview"]
    rounds = max(st["rounds"], 1)
    if metric == "rating":
        return context.rating(o["kills"], o["deaths"], o["assists"], o["adr"], o["kast_pct"], rounds), 1
    if metric == "adr":
        return o["adr"], 1
    if metric == "traded_pct":
        d = o["trades"]["my_deaths"]
        return (100 * o["trades"]["my_deaths_traded"] / d, 1) if d else (None, 0)
    if metric == "nades_unused_pr":
        return sum(len(r["grenades_unused_at_death"]) for r in st["per_round"]) / rounds, 1
    if metric == "xhair":
        v = (st["aim"].get("crosshair_placement") or {}).get("median_error_deg")
        return (v, 1) if v is not None else (None, 0)
    if metric == "pistol_moving":
        from wily.coaching.advice import PISTOLS
        sh = mv = 0.0
        for w, v in st["aim"]["by_weapon"].items():
            if w in PISTOLS and v.get("shots_while_moving_pct") is not None:
                sh += v["shots"]
                mv += v["shots"] * v["shots_while_moving_pct"] / 100
        return (100 * mv / sh, 1) if sh >= 5 else (None, 0)
    if metric == "open_win":
        w, l = o["opening_duels"]["won"], o["opening_duels"]["lost"]
        return (100 * w / (w + l), 1) if w + l else (None, 0)
    if metric in ("isolated_pr", "adv_throw", "rot_died", "rt_solo", "steps_alone_pr"):
        r = _mid_rows(m["id"], sid)
        if r is None:
            return None, 0
        g = lambda k: float(r.get(k)) if pd.notna(r.get(k)) else 0.0
        if metric == "isolated_pr":
            return g("isolated_deaths") / max(g("rounds"), 1), 1
        if metric == "steps_alone_pr":
            return g("steps_alone") / max(g("rounds"), 1), 1
        if metric == "adv_throw":
            return ("k", g("adv_throw"), g("adv_rounds"))
        if metric == "rot_died":
            return ("k", g("rot_died_way"), g("rot_done"))
        if metric == "rt_solo":
            return ("k", g("rt_solo_death"), g("rt_n"))
    if metric in ("weapon_duels", "weapon_adr"):
        w = params.get("alt") if template == "weapon_swap" and params.get("_phase") == "trial" else params.get("weapon")
        if metric == "weapon_duels":
            f = os.path.join(config.DEEP, str(m["id"]), "deaths_w.parquet")
            if not os.path.exists(f):
                return None, 0
            dw = pd.read_parquet(f)
            k = int(((dw.killer == sid) & (dw.killer_weapon_name == w)).sum())
            d = int(((dw.victim == sid) & (dw.victim_weapon == w)).sum())
            return ("k", k, k + d)
        f = os.path.join(config.DEEP, str(m["id"]), "loadout.parquet")
        if not os.path.exists(f):
            return None, 0
        L = pd.read_parquet(f)
        x = L[(L.steamid == sid) & (L.primary == w)]
        return (float(x.damage.mean()), len(x)) if len(x) else (None, 0)
    if metric == "zone_duels":
        if m["map"] != params.get("map"):
            return None, 0
        f = os.path.join(config.DEEP, str(m["id"]), "duels.parquet")
        if not os.path.exists(f):
            return None, 0
        D = pd.read_parquet(f)
        side = params.get("side")
        k = int(((D.killer == sid) & (D.killer_zone == params.get("zone")) & (D.killer_side == side)).sum())
        d = int(((D.victim == sid) & (D.victim_zone == params.get("zone")) & (D.victim_side == side)).sum())
        return ("k", k, k + d)
    if metric == "ct_full_duels":
        d = os.path.join(config.DEEP, str(m["id"]))
        if not (os.path.exists(os.path.join(d, "duels.parquet")) and os.path.exists(os.path.join(d, "loadout.parquet"))):
            return None, 0
        L = pd.read_parquet(os.path.join(d, "loadout.parquet"), columns=["round", "steamid", "side", "team_buy"])
        full = set(L[(L.steamid == sid) & (L.side == "CT") & (L.team_buy == "full")]["round"].astype(int))
        if not full:
            return None, 0
        D = pd.read_parquet(os.path.join(d, "duels.parquet"), columns=["round", "killer", "victim"])
        D = D[D["round"].astype(int).isin(full)]
        k, dd = int((D.killer == sid).sum()), int((D.victim == sid).sum())
        return ("k", k, k + dd)
    if metric == "call_before_death":
        a = _voice_by_match().get(str(m["id"]))
        if a:
            return ("k", a["deaths"] - a["silent_deaths"], a["deaths"])
        return None, 0
    if metric == "first_game":
        return (m.get("_first_rating"), 1) if m.get("_first_rating") is not None else (None, 0)
    return None, 0


def _summ(vals):
    props = [v for v in vals if isinstance(v, tuple) and len(v) == 3 and v[0] == "k"]
    if props:
        k = sum(v[1] for v in props)
        n = sum(v[2] for v in props)
        return {"kind": "prop", "k": k, "n": n, "value": round(100 * k / n, 1) if n else None, "games": len(props)}
    xs = [(v[0], v[1]) for v in vals if isinstance(v, tuple) and len(v) == 2 and v[0] is not None and v[1]]
    if not xs:
        return {"kind": "mean", "value": None, "n": 0, "games": 0}
    w = sum(b for _, b in xs)
    mean = sum(a * b for a, b in xs) / w
    sd = pd.Series([a for a, _ in xs]).std() if len(xs) > 1 else None
    return {"kind": "mean", "value": round(mean, 2), "n": len(xs), "sd": None if sd is None or math.isnan(sd) else float(sd), "games": len(xs)}


def evaluate(sid, e, hist=None, stats_by_id=None):
    """Baseline (15 matches before the start) vs trial (matches after the start)."""
    sid = int(sid)
    hist = hist if hist is not None else context.history(sid)
    stats_by_id = stats_by_id or {}
    tpl = TEMPLATES[e["template"]]
    t0 = dt.datetime.fromisoformat(e["started"])
    t1 = dt.datetime.fromisoformat(e["ended"]) if e.get("ended") else None
    # first game of each session, for the warm-up experiment
    prev_end = None
    for m in hist:
        m["_first_rating"] = m["perf"] if (prev_end is None or (m["start"] - prev_end).total_seconds() > context.SESSION_GAP_MIN * 60) else None
        prev_end = m["end"]
    before = [m for m in hist if m["start"] < t0 and m["source"] == "demo"][-15:]
    after = [m for m in hist if m["start"] >= t0 and (t1 is None or m["start"] <= t1) and m["source"] == "demo"]

    def vals(ms, phase):
        out = []
        for m in ms:
            st = stats_by_id.get(m["id"])
            if st is None:
                f = os.path.join(config.player_dir(sid), "matches", m["id"], "stats.json")
                if not os.path.exists(f):
                    continue
                st = json.load(open(f, encoding="utf-8"))
                stats_by_id[m["id"]] = st
            p = dict(e.get("params") or {}, _phase=phase)
            out.append(match_values(sid, m, st, e["template"], p))
        return out
    b, a = _summ(vals(before, "base")), _summ(vals(after, "trial"))
    label, unit, hib = METRICS[tpl["metric"]]
    need = tpl["min"]
    have = a["n"] if tpl["unit_n"] in ("duels", "rounds") else a["games"]
    verdict, z = "in progress", None
    if a["value"] is not None and b["value"] is not None:
        if a["kind"] == "prop" and b["kind"] == "prop" and a["n"] and b["n"]:
            p = (a["k"] + b["k"]) / (a["n"] + b["n"])
            se = math.sqrt(max(p * (1 - p), 1e-6) * (1 / a["n"] + 1 / b["n"])) * 100
            z = (a["value"] - b["value"]) / se if se else None
        elif a["kind"] == "mean" and b["kind"] == "mean" and a["n"] >= 2 and b["n"] >= 2:
            se = math.sqrt((a.get("sd") or 1) ** 2 / a["n"] + (b.get("sd") or 1) ** 2 / b["n"])
            z = (a["value"] - b["value"]) / se if se else None
    if have >= need and z is not None:
        good = z if hib else -z
        verdict = "it works" if good >= 1.64 else "it hurts" if good <= -1.64 else "no clear effect"
    elif have >= need:
        verdict = "not enough data to compare yet"
    return {**e, "title": title_of(e["template"], e.get("params") or {}), "category": tpl["cat"], "how": [tr(h, **{**(e.get("params") or {}), "map_name": (e.get("params") or {}).get("map", "").split("_")[-1].capitalize()}) for h in tpl["how"]],
            "metric": tr(label), "unit": unit, "higher_better": hib, "before": b, "after": a, "progress": [min(have, need), need, tpl["unit_n"]],
            "z": None if z is None else round(z, 2), "verdict": verdict}


def suggestions(sid, adv, mid_bench=None, weapons_info=None, ctx=None, cross=None):
    """Experiments worth running, from the player's own weak points."""
    S = []
    rid = [r["id"] for r in (adv or {}).get("rules", [])]

    def add(template, why, params=None, prio=5):
        S.append({"template": template, "params": params or {}, "title": title_of(template, params), "why": why,
                  "category": TEMPLATES[template]["cat"], "metric": tr(METRICS[TEMPLATES[template]["metric"]][0]), "prio": prio})
    for s in (weapons_info or {}).get("suggestions", []):
        if s["kind"] == "weapon_weak":
            alt = {"M4A1-S": "M4A4", "M4A4": "M4A1-S", "Galil AR": "XM1014", "FAMAS": "XM1014", "MP9": "MP5-SD", "MAC-10": "Galil AR",
                   "Desert Eagle": "P250", "MAG-7": "MP9", "Nova": "XM1014"}.get(s["weapon"])   # same side, same price range
            # never the AK for the Galil (03/11, a tester's report: "Says replace AK with Galil. Pls dont have it say that"):
            # the T side's rifle has no equal, a weak AK is worked on, not swapped
            if alt:
                add("weapon_swap", s["text"], {"weapon": s["weapon"], "alt": alt}, 8)
        elif s["kind"] == "weapon_strong":
            add("weapon_keep", s["text"], {"weapon": s["weapon"]}, 3)
    if "trade" in rid or "lastalive" in rid:
        add("trade_distance", tr("Your deaths rarely get traded: this is the most profitable thing to work on."), prio=9)
    if "nades" in rid:
        add("nades_40s", tr("You often die with grenades in your pockets."), prio=7)
    if "xhair" in rid:
        add("prefire", tr("Your crosshair is far from the head when the duel starts."), prio=7)
    if "pistol" in rid:
        add("counter_strafe", tr("Many of your pistol shots are fired while moving."), prio=6)
    if "open" in rid or "early" in rid:
        add("opening", tr("Your opening duels cost rounds."), prio=6)
    MB = (mid_bench or {}).get("metrics", {})
    if (MB.get("adv_throw") or {}).get("percentile") is not None and MB["adv_throw"]["percentile"] <= 35:
        add("advantage", tr("You throw away the man advantage more often than {p}% of players.", p=f"{100 - MB['adv_throw']['percentile']:.0f}"), prio=8)
    if (MB.get("rot_died") or {}).get("percentile") is not None and MB["rot_died"]["percentile"] <= 35:
        add("rotation", tr("You often die during your rotations."), prio=7)
    if (MB.get("rt_solo") or {}).get("percentile") is not None and MB["rt_solo"]["percentile"] <= 35:
        add("retake_group", tr("You often die alone in retakes."), prio=7)
    if (MB.get("steps_alone") or {}).get("percentile") is not None and MB["steps_alone"]["percentile"] <= 40:
        add("silent", tr("You make noise within enemy earshot when you are alone: the basics of your lurker role."), prio=6)
    recs = (ctx or {}).get("recs", [])
    if any(r["kind"] in ("stop", "tilt") for r in recs) or (ctx and ctx["sessions"]["max_games"] >= 4):
        add("session_limit", tr("Long sessions or sessions after losses lower your rating."), prio=5)
    add("warmup", tr("Measure the effect of a real warm-up on your first game."), prio=4)
    # positions the base wins in and the player rarely plays
    for m in (cross or {}).get("maps", [])[:3]:
        for side, Sd in m["sides"].items():
            pz = [z for z in Sd.get("pool_zones", []) if (z.get("win") or 0) >= 56 and z["k"] + z["d"] >= 12 and z["my_presence"] < 4
                  and "spawn" not in z["key"].lower() and z["t_med"] <= 45]
            if pz:
                z = pz[0]
                add("zone", tr("On {map} as {side}, players in the base win {p}% of their duels in {zone} and you almost never go there.", map=m['map'].split('_')[-1].capitalize(), side=side, p=z['win'], zone=z['name']),
                    {"map": m["map"], "side": side, "zone": z["key"], "zone_name": z["name"]}, 4)
                break
    seen, out = set(), []
    for s in sorted(S, key=lambda x: -x["prio"]):
        key = (s["template"], json.dumps(s["params"], sort_keys=True))
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out[:8]


def report(sid, adv=None, mid_bench=None, weapons_info=None, ctx=None, cross=None):
    hist = context.history(sid)
    cache = {}
    exps = [evaluate(sid, e, hist, cache) for e in load(sid) if e.get("template") in TEMPLATES]   # an unknown one (older code): left aside, never fatal
    active = {(e["template"], json.dumps({k: v for k, v in e["params"].items()}, sort_keys=True)) for e in exps if e["status"] == "active"}
    sug = [s for s in suggestions(sid, adv, mid_bench, weapons_info, ctx, cross) if (s["template"], json.dumps(s["params"], sort_keys=True)) not in active]
    return {"experiments": exps, "suggested": sug, "templates": {k: {"cat": v["cat"], "title": v["title"]} for k, v in TEMPLATES.items()}}
