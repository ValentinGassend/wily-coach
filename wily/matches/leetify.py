"""Public data from a SteamID alone: profile resolution (Steam) and Leetify public API; the Leetify-only diagnosis of a
player without demos, against the Leetify stats of the base's players."""
import bisect
import glob
import json
import os
import re
import urllib.request

from wily.core import config
from wily.core.i18n import tr

API = "https://api-public.cs-prod.leetify.com"


_LAST = [0.0]
MIN_GAP = 3.2  # Leetify's public API allows roughly one request every 3 seconds


def _get(url, timeout=20, tries=4):
    import time
    import urllib.error
    for attempt in range(tries):
        wait = MIN_GAP - (time.time() - _LAST[0])
        if wait > 0 and "leetify" in url:
            time.sleep(wait)
        _LAST[0] = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 wily-coach"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < tries - 1:
                time.sleep(15 * (attempt + 1))
                continue
            raise


def resolve_steamid(s):
    """SteamID64, profile URL (/profiles/<id> or /id/<vanity>) or vanity name -> (steamid64, name)."""
    s = str(s).strip().rstrip("/")
    m = re.search(r"(7656\d{13})", s)
    url = f"https://steamcommunity.com/profiles/{m.group(1)}" if m else \
        (s if s.startswith("http") else f"https://steamcommunity.com/id/{s}")
    try:
        xml = _get(url + "/?xml=1").decode("utf-8", "replace")
        sid = re.search(r"<steamID64>(\d+)</steamID64>", xml)
        name = re.search(r"<steamID><!\[CDATA\[(.*?)\]\]>", xml)
        if sid:
            return int(sid.group(1)), name.group(1) if name else None
    except Exception:
        pass
    return (int(m.group(1)), None) if m else (None, None)


def profile(steamid):
    try:
        return json.loads(_get(f"{API}/v3/profile?steam64_id={steamid}"))
    except Exception:
        return None


def matches(steamid):
    try:
        return json.loads(_get(f"{API}/v3/profile/matches?steam64_id={steamid}"))
    except Exception:
        return []


# ---------- the Leetify-only diagnosis against the base's players (04/10) ----------
LDIR = os.path.join(config.OUT, "population", "leetify")      # profiles saved by the base loop (grow.py)
REF_F = os.path.join(config.OUT, "population", "leetify_ref.json")
MIN_REF = 30   # players with the stat in the reference: under that, the fixed limits
# metric -> (higher is better, weak limit, strong limit): the fixed limits are the quartiles of 138 players of the
# base with Leetify (04/10), used while the reference is too small; the definitions are Leetify's
# (https://leetify.com/blog/leetify-stats-glossary/)
LMETRICS = {
    "preaim": (False, 10.6, 8.7),   # degrees from first sight to damage; lower is better (Leetify's top 3 % near 8°)
    "counter_strafing_good_shots_ratio": (True, 74.9, 82.7),   # % of shots under 34 % of the weapon's max speed
    "reaction_time_ms": (False, 604.0, 528.0),   # time to damage, not a reflex: never near 200 ms (Leetify)
    "flashbang_hit_friend_per_flashbang": (False, 0.42, 0.27),
    "utility_on_death_avg": (False, 347.0, 211.0),   # $ of grenades unused at each death
    "ct_opening_duel_success_percentage": (True, 38.9, 50.6),
    "t_opening_duel_success_percentage": (True, 34.4, 45.7),
    "traded_deaths_success_percentage": (True, 47.2, 54.5),
}
LFMT = {"preaim": "{:.1f}°", "counter_strafing_good_shots_ratio": "{:.0f}%", "reaction_time_ms": "{:.0f} ms",
        "flashbang_hit_friend_per_flashbang": "{:.2f}", "utility_on_death_avg": "${:.0f}", "ct_opening_duel_success_percentage": "{:.0f}%",
        "t_opening_duel_success_percentage": "{:.0f}%", "traded_deaths_success_percentage": "{:.0f}%"}
BANDS = (10000, 15000, 20000, 25000)   # Premier rating levels: under 10,000, 10-15k, 15-20k, 20-25k, 25k+


def _band(premier):
    try:
        return sum(float(premier) >= b for b in BANDS)
    except (TypeError, ValueError):
        return None


def reference(rebuild=False):
    """The Leetify stats of the base's players (the profiles the app built, the players the base loop looked up):
    per metric the sorted values, overall and per Premier level. Rebuilt once a tenth more players are saved."""
    files = glob.glob(os.path.join(config.OUT, "players", "*", "advice.json")) + glob.glob(os.path.join(LDIR, "*.json"))
    try:
        with open(REF_F, encoding="utf-8") as fh:
            cur = json.load(fh)
        if not rebuild and cur.get("_files", 0) >= 0.9 * len(files):
            return cur
    except (OSError, ValueError):
        pass
    rows = {}
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                a = json.load(fh)
        except (OSError, ValueError):
            continue
        L = a.get("leetify") if f.endswith("advice.json") else a
        if not isinstance(L, dict) or not L.get("stats"):
            continue
        sid = os.path.basename(os.path.dirname(f)) if f.endswith("advice.json") else os.path.basename(f)[:-5]
        rows[sid] = (L["stats"], _band((L.get("ranks") or {}).get("premier")))
    ref = {"_files": len(files), "n": len(rows), "metrics": {}}
    for k in LMETRICS:
        allv, by = [], {}
        for st, b in rows.values():
            v = st.get(k)
            if isinstance(v, (int, float)):
                allv.append(float(v))
                if b is not None:
                    by.setdefault(str(b), []).append(float(v))
        ref["metrics"][k] = {"all": sorted(allv), "by_band": {b: sorted(v) for b, v in by.items()}}
    try:
        config.write_json(REF_F, ref)
    except OSError:
        pass
    return ref


def _better_than(vals, v, hib):
    """Share of the reference doing worse than v (100: the best)."""
    if not vals:
        return None
    below = bisect.bisect_left(vals, v) / len(vals) * 100
    return below if hib else 100 - bisect.bisect_right(vals, v) / len(vals) * 100


def light_advice(prof, ms, steamid):
    """Diagnosis from Leetify's aggregated stats when no demo is available: each stat against the Leetify stats of the
    base's players (and of your Premier level), a weakness in their worst quarter, a strength in their best."""
    st, rt = prof.get("stats", {}), prof.get("rating", {})
    R, S = [], []
    ref = reference()
    band = _band((prof.get("ranks") or {}).get("premier"))

    def judge(k):
        """-> (verdict "weak"/"strong"/None, how far from the base 0-100, the comparison's words)."""
        v = st.get(k)
        if not isinstance(v, (int, float)):
            return None, 0, ""
        hib, weak, strong = LMETRICS[k]
        M = ref["metrics"].get(k) or {}
        vals, lvl = M.get("all") or [], (M.get("by_band") or {}).get(str(band)) or []
        if len(vals) >= MIN_REF:
            pct = _better_than(vals, v, hib)
            med = vals[len(vals) // 2]
            fm = LFMT[k].format
            words = tr("base median {v}", v=fm(med)) + (", " + tr("players of your level {v}", v=fm(lvl[len(lvl) // 2])) if len(lvl) >= 15 else "") + \
                " · " + tr("better than {p}% of {n} players with Leetify", p=f"{pct:.0f}", n=len(vals))
            return ("weak" if pct <= 25 else "strong" if pct >= 75 else None), 25 - pct, words
        bad = v <= weak if hib else v >= weak
        good = v >= strong if hib else v <= strong
        return ("weak" if bad else "strong" if good else None), 10, tr("the base's worst quarter starts at {v}", v=LFMT[k].format(weak))

    def add(score, title, short, why, do, key):   # key: the rule's id, the same in every language
        R.append({"id": key, "score": score, "title": title, "short": short, "why": why, "do": do})

    g = lambda k: st.get(k)
    vd, gap, words = judge("preaim")
    if vd == "strong":
        S.append(tr("Good crosshair placement ({v}°, {how})", v=f"{g('preaim'):.1f}", how=words))
    elif vd == "weak":
        add(10 + gap / 2, tr("Crosshair poorly placed before duels: {v}°", v=f"{g('preaim'):.1f}"), tr("Crosshair at head height"),
            [tr("Average angle your crosshair moves from first seeing the enemy to hitting them (Leetify)."), words],
            [tr("Pre-aim angles at head height while moving."), tr("Training map: Prefire / crosshair placement.")], "Crosshair at head height")
    vd, gap, words = judge("counter_strafing_good_shots_ratio")
    cs = g("counter_strafing_good_shots_ratio")
    if vd == "strong":
        S.append(tr("Clean counter-strafing ({p}% good shots, {how})", p=f"{cs:.0f}", how=words))
    elif vd == "weak":
        add(12 + gap / 2, tr("Only {p}% of shots properly counter-strafed", p=f"{cs:.0f}"), tr("Counter-strafe before shooting"),
            [tr("Shots fired under 34% of the weapon's max speed, where inaccuracy kicks in (Leetify)."), words],
            [tr("Tap the opposite direction before every shot, with pistols and rifles.")], "Counter-strafe before shooting")
    fr, fo = g("flashbang_hit_friend_per_flashbang"), g("flashbang_hit_foe_per_flashbang")
    vd, gap, words = judge("flashbang_hit_friend_per_flashbang")
    if vd == "weak":
        add(12 + gap / 2, tr("Your flashes blind {v} teammates per flash", v=f"{fr:.2f}"), tr("Flash for your teammates, not on them"),
            [tr("Enemies blinded per flash: {v}.", v=f"{fo or 0:.2f}"), tr("Flashes leading to a kill: {p}%.", p=f"{g('flashbang_leading_to_kill') or 0:.0f}"), words],
            [tr("Call your flash before throwing it."), tr("Learn 2 popflashes per site: they pop above the wall, not on your team.")], "Flash for your teammates, not on them")
    ud = g("utility_on_death_avg")
    vd, gap, words = judge("utility_on_death_avg")
    if vd == "weak":
        add(10 + gap / 2, tr("${v} of grenades in your pockets at each death on average", v=f"{ud:.0f}"), tr("Empty your pockets before 40 s"),
            [tr("Average value of unused grenades when you die."), words], [tr("Throw your grenades before the contact.")], "Empty your pockets before 40 s")
    for side, k in (("CT", "ct_opening_duel_success_percentage"), ("T", "t_opening_duel_success_percentage")):
        vd, gap, words = judge(k)
        if vd == "weak":
            add(8 + gap / 2, tr("Opening duels as {side}: {p}% won", side=side, p=f"{g(k):.0f}"), tr("Don't take the first duel alone as {side}", side=side),
                [tr("Opening duel win rate (Leetify)."), words], [tr("Leave the opening to a teammate or take it with a flash.")], f"Don't take the first duel alone as {side}")
    trd = g("traded_deaths_success_percentage")
    vd, gap, words = judge("traded_deaths_success_percentage")
    if vd == "weak":
        add(12 + gap / 2, tr("Only {p}% of your 'tradable' deaths get traded", p=f"{trd:.0f}"), tr("Play within 2 seconds of a teammate"),
            [tr("When a trade was possible, it happened this share of the time."), words], [tr("Stay within trade range of a teammate.")], "Play within 2 seconds of a teammate")
    rtm = g("reaction_time_ms")
    vd, gap, words = judge("reaction_time_ms")
    if vd == "weak":
        add(8 + gap / 4, tr("Time to damage of {v} ms", v=f"{rtm:.0f}"), tr("Warm up before playing"),
            [tr("From first seeing the enemy to your first damage (Leetify): crosshair placement counts as much as reflexes."), words],
            [tr("10 minutes of Aim Botz and deathmatch before each session.")], "Warm up before playing")
    by_map = {}
    for m in ms:
        me = next((x for x in m.get("stats", []) if x.get("steam64_id") == str(steamid)), None)
        if not me:
            continue
        b = by_map.setdefault(m["map_name"], {"n": 0, "w": 0, "k": 0, "d": 0, "dmg": 0, "rounds": 0})
        b["n"] += 1
        b["w"] += me.get("rounds_won", 0) > me.get("rounds_lost", 0)
        b["k"] += me.get("total_kills", 0)
        b["d"] += me.get("total_deaths", 0)
        b["dmg"] += me.get("total_damage", 0)
        b["rounds"] += me.get("rounds_count", 0)
    return {"rules": sorted(R, key=lambda r: -r["score"]), "strengths": S, "maps": {}, "match_notes": {},
            "leetify": {"name": prof.get("name"), "ratings": rt, "stats": st, "ranks": prof.get("ranks"), "total_matches": prof.get("total_matches"),
                        "winrate": prof.get("winrate"), "by_map": by_map,
                        "recent": [{"time": m["finished_at"], "source": m["data_source"], "map": m["map_name"],
                                    "score": [t["score"] for t in m["team_scores"]],
                                    "me": next(({k: x.get(k) for k in ("total_kills", "total_deaths", "total_assists", "dpr", "rounds_won", "rounds_lost",
                                                                        "accuracy_head", "counter_strafing_shots_good_ratio", "flashbang_hit_friend", "flashbang_hit_foe", "leetify_rating")}
                                                for x in m.get("stats", []) if x.get("steam64_id") == str(steamid)), None)} for m in ms[:30]]}}
