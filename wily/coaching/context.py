"""Playing context of a player: sessions, time of day, games in a row, loss streaks, party (solo / duo / stack),
best partners, and the pre-session check-ins of the journal (sleep, energy, warm-up).

Performance of a match = rating approximating HLTV 2.0 (flashed.gg reverse engineering), or Leetify's rating
when the match only comes from Leetify. Everything is compared to the player's own average.
"""
import datetime as dt
import json
import math
import os
from collections import Counter, defaultdict

import pandas as pd

from wily.core import config
from wily.core.i18n import N_, tr

SESSION_GAP_MIN = 45        # more than 45 min between two games = new session
JOURNAL = os.path.join(config.OUT, "journal")
RATING_SRC = {"label": "flashed.gg, HLTV 2.0 rating rebuilt", "url": "https://flashed.gg/posts/reverse-engineering-hltv-rating/"}


def rating(kills, deaths, assists, adr, kast, rounds):
    """Approximation of HLTV Rating 2.0 (multiple regression by flashed.gg)."""
    r = max(rounds, 1)
    kpr, dpr, apr = kills / r, deaths / r, assists / r
    impact = 2.13 * kpr + 0.42 * apr - 0.41
    return 0.0073 * kast + 0.3591 * kpr - 0.5329 * dpr + 0.2372 * impact + 0.0032 * adr + 0.1587


def digest(sid, mids):
    """{match: what the plan reads of its positions}: its players in the first round [steamid, side, name], and the
    player's own zones after 5 s, per side, each with its count in the order they first appear. Kept per match
    (ledger.py), read again only when its folder changes (16/10: three modules opened each of the player's samples,
    some of them three times, at every plan)."""
    from wily.app import pipeline
    from wily.core import ledger
    sid = int(sid)
    dirs = ledger.folders(config.DEEP)
    ask = set(mids) | set(pipeline.player_matches(sid))   # every caller asks the same ones: the ledger keeps them all

    def read(mid):
        f = os.path.join(config.DEEP, mid, "samples.parquet")
        if not os.path.exists(f):
            return None
        try:
            s = pd.read_parquet(f, columns=["steamid", "name", "side", "round", "t", "zone"])
        except Exception:   # an older extraction without the names
            s = pd.read_parquet(f, columns=["steamid", "side", "round", "t", "zone"])
        r1 = s[s["round"] == s["round"].min()].drop_duplicates("steamid")
        names = r1["name"].tolist() if "name" in r1 else [None] * len(r1)
        first = [[int(p), sd, nm if isinstance(nm, str) and nm else None] for p, sd, nm in zip(r1.steamid, r1.side, names)]
        me = s[(s.steamid == sid) & (s.t >= 5) & (s.zone != "?")]
        zones = {}
        for side, g in me.groupby("side"):
            n = g.zone.value_counts()
            zones[side] = [[z, int(n[z])] for z in pd.unique(g.zone) if z == z]
        return {"first": first, "zones": zones}
    return ledger.per_match(f"digest_{sid}", {m: dirs[m] for m in sorted(ask) if m in dirs}, read)


def _teams(dg):
    """{steamid: side in round 1} from a match's digest."""
    return {p: sd for p, sd, _ in (dg or {}).get("first") or []}


def _local(t):
    if not t:
        return None
    if t.endswith("Z") or "+" in t[10:]:
        return dt.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    return dt.datetime.fromisoformat(t)


def history(steamid):
    """Every known match of the player, oldest first."""
    sid = int(steamid)
    pdir = config.player_dir(sid)
    reg = {}
    rp = os.path.join(config.CACHE, "matches.json")
    if os.path.exists(rp):
        reg = json.load(open(rp))
    out, seen = [], set()
    mdir = os.path.join(pdir, "matches")
    mids = os.listdir(mdir) if os.path.exists(mdir) else []
    dg = digest(sid, mids)
    for mid in mids:
        f = os.path.join(mdir, mid, "stats.json")
        if not os.path.exists(f):
            continue
        st = json.load(open(f, encoding="utf-8"))
        if st.get("error") or not st.get("match", {}).get("time"):
            continue
        o = st["overview"]
        start = _local(st["match"]["time"])
        dur = st["match"].get("duration_s") or (reg.get(mid) or {}).get("duration_s") or st["rounds"] * 110
        teams = _teams(dg.get(mid))
        me_side = teams.get(sid)
        mates = sorted(p for p, sd in teams.items() if sd == me_side and p != sid) if me_side else []
        out.append({"id": mid, "source": "demo", "start": start, "end": start + dt.timedelta(seconds=dur), "map": st["map"],
                    "mode": st.get("mode"), "result": st["result"], "rounds": st["rounds"],
                    "score": [st["final_score"]["me"], st["final_score"]["them"]],
                    "perf": round(rating(o["kills"], o["deaths"], o["assists"], o["adr"], o["kast_pct"], st["rounds"]), 3),
                    "kills": o["kills"], "deaths": o["deaths"], "adr": o["adr"], "mates": mates})
        seen.add(str(mid))
    lf = os.path.join(config.CACHE, f"leetify_{sid}.json")
    if os.path.exists(lf):
        from wily.matches import matchlist
        for m in json.load(open(lf, encoding="utf-8")) or []:
            code = str(m.get("data_source_match_id", ""))
            try:
                mid = str(matchlist.decode_sharecode(code)[0]) if code.startswith("CSGO-") else m["id"]
            except Exception:
                mid = m["id"]
            if mid in seen:
                continue
            me = next((x for x in m.get("stats", []) if x.get("steam64_id") == str(sid)), None)
            if not me:
                continue
            end = _local(m["finished_at"])
            rounds = me.get("rounds_count") or 20
            won, lost = me.get("rounds_won", 0), me.get("rounds_lost", 0)
            out.append({"id": mid, "source": "leetify", "start": end - dt.timedelta(seconds=rounds * 105), "end": end,
                        "map": m.get("map_name"), "mode": m.get("data_source"), "result": "win" if won > lost else "loss" if lost > won else "draw",
                        "rounds": rounds, "score": [won, lost], "perf": None, "leetify": me.get("leetify_rating"),
                        "kills": me.get("total_kills"), "deaths": me.get("total_deaths"), "adr": me.get("dpr"), "mates": []})
            seen.add(mid)
    # matches known from Valve (Steam history sync, last 8 matches): no demo, but date, score, own K/A/D and the 10 players
    acc = sid - 76561197960265728
    for mid, r in reg.items():
        accs = r.get("accounts") or []
        if mid in seen or acc not in accs or not r.get("time") or len(r.get("team_scores") or []) != 2:
            continue
        i = accs.index(acc)
        team = 0 if i < len(accs) // 2 else 1
        mine, theirs = r["team_scores"][team], r["team_scores"][1 - team]
        st = (r.get("stats") or [])[i] if i < len(r.get("stats") or []) else {}
        rounds = r.get("rounds") or (mine + theirs)
        start = _local(r["time"])
        k, d, a = st.get("k"), st.get("d"), st.get("a")
        out.append({"id": mid, "source": "steam", "start": start, "end": start + dt.timedelta(seconds=r.get("duration_s") or rounds * 110),
                    "map": None, "mode": None, "result": "win" if mine > theirs else "loss" if mine < theirs else "draw",
                    "rounds": rounds, "score": [mine, theirs], "perf": None,
                    "raw": None if k is None or d is None else (k - d) / max(rounds, 1),
                    "kills": k, "deaths": d, "adr": None,
                    "mates": sorted(x + 76561197960265728 for j, x in enumerate(accs) if x != acc and (0 if j < len(accs) // 2 else 1) == team)})
        seen.add(mid)
    out.sort(key=lambda m: m["start"])
    # Valve-only matches: K/A/D per round expressed on the rating scale of the player's demo matches
    dm = [m for m in out if m["source"] == "demo" and m.get("perf") is not None and m.get("kills") is not None]
    sv = [m for m in out if m["source"] == "steam" and m.get("raw") is not None]
    if sv:
        raw_d = [(m["kills"] - m["deaths"]) / max(m["rounds"], 1) for m in dm]
        if len(dm) >= 3:
            rm, rs = sum(raw_d) / len(raw_d), (pd.Series(raw_d).std() or 0.3)
            pm, ps = sum(m["perf"] for m in dm) / len(dm), (pd.Series([m["perf"] for m in dm]).std() or 0.25)
        else:
            rm, rs, pm, ps = 0.0, 0.3, 1.0, 0.25
        for m in sv:
            m["perf"] = round(pm + (m["raw"] - rm) / rs * ps, 3)
    # Leetify-only matches: express Leetify's rating on the same scale (z-score within the player)
    lv = [m["leetify"] for m in out if m.get("leetify") is not None]
    dv = [m["perf"] for m in out if m.get("perf") is not None]
    if lv:
        lm, ls = sum(lv) / len(lv), (pd.Series(lv).std() or 1)
        dm = sum(dv) / len(dv) if dv else 1.0
        ds = (pd.Series(dv).std() if len(dv) > 2 else 0.25) or 0.25
        for m in out:
            if m.get("perf") is None and m.get("leetify") is not None:
                m["perf"] = round(dm + (m["leetify"] - lm) / ls * ds, 3)
    return out


def journal(steamid):
    f = os.path.join(JOURNAL, f"{steamid}.json")
    return json.load(open(f, encoding="utf-8")) if os.path.exists(f) else []


def add_checkin(steamid, entry):
    os.makedirs(JOURNAL, exist_ok=True)
    j = journal(steamid)
    e = {k: entry.get(k) for k in ("sleep_h", "energy", "mood", "warmup", "caffeine", "party", "note")}
    e["time"] = dt.datetime.now().isoformat(timespec="minutes")
    j.append(e)
    json.dump(j, open(os.path.join(JOURNAL, f"{steamid}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return e


# the factors' titles and groups: English keys while comparing (plan.py and review.py look for "Group", "solo"), in the
# player's language in the output (key: the English one)
_LABELS = [N_("Time of day"), N_("Game in the session"), N_("After the previous result"), N_("Group"), N_("Day"), N_("Rest before the session"),
           N_("Sleep (journal)"), N_("Warm-up (journal)"), N_("Energy (journal)"), N_("morning (6am-12pm)"), N_("afternoon (12pm-6pm)"),
           N_("evening (6pm-11pm)"), N_("night (11pm-6am)"), N_("1st game"), N_("2nd game"), N_("3rd game"), N_("4th game and later"),
           N_("after a win"), N_("after a loss"), N_("after 2+ losses"), N_("solo"), N_("duo"), N_("group of 3"), N_("group of 4"), N_("group of 5"),
           N_("weekend"), N_("weekday"), N_("under 12 h"), N_("12 h or more"), N_("under 6 h"), N_("6 h to 7.5 h"), N_("7.5 h or more"),
           N_("no warm-up"), N_("warmed up"), N_("low (1-2)"), N_("medium (3)"), N_("high (4-5)")]


def _bucket_hour(h):
    return "morning (6am-12pm)" if 6 <= h < 12 else "afternoon (12pm-6pm)" if 12 <= h < 18 else "evening (6pm-11pm)" if 18 <= h < 23 else "night (11pm-6am)"


def _stats(ms):
    n = len(ms)
    w = sum(1 for m in ms if m["result"] == "win")
    l = sum(1 for m in ms if m["result"] == "loss")
    pf = [m["perf"] for m in ms if m.get("perf") is not None]
    mean = sum(pf) / len(pf) if pf else None
    sd = pd.Series(pf).std() if len(pf) > 1 else None
    return {"n": n, "w": w, "l": l, "winrate": round(100 * w / n) if n else None,
            "perf": None if mean is None else round(mean, 2), "sd": None if sd is None or math.isnan(sd) else sd}


def _cmp(group, rest):
    """Strength of the difference in performance between a group and the rest (z of the means)."""
    if group["perf"] is None or rest["perf"] is None or group["n"] < 2 or rest["n"] < 2:
        return None
    se = math.sqrt((group["sd"] or 0.25) ** 2 / group["n"] + (rest["sd"] or 0.25) ** 2 / rest["n"])
    return round((group["perf"] - rest["perf"]) / se, 2) if se else None


def _level(z, n):
    """About fifteen groups are compared (game of the session, time of day, group, previous result...): with the
    usual 2 standard errors, one of them would look 'reliable' by chance every few weeks. Hence 2.5 and 6 games."""
    if z is None:
        return "not enough data"
    if abs(z) >= 2.5 and n >= 6:
        return "reliable"
    if abs(z) >= 1.5 and n >= 4:
        return "trend"
    return "no clear gap"


def analyze(steamid):
    ms = history(steamid)
    if not ms:
        return None
    sid = int(steamid)
    # sessions
    sessions, cur = [], []
    for m in ms:
        if cur and (m["start"] - cur[-1]["end"]).total_seconds() > SESSION_GAP_MIN * 60:
            sessions.append(cur)
            cur = []
        cur.append(m)
    if cur:
        sessions.append(cur)
    prev_end = None
    for si, s in enumerate(sessions):
        rest_h = None if prev_end is None else (s[0]["start"] - prev_end).total_seconds() / 3600
        streak = 0
        for i, m in enumerate(s):
            m["session"] = si
            m["index"] = i + 1
            m["prev"] = "1st game" if i == 0 else ("after 2+ losses" if streak <= -2 else "after a loss" if streak == -1 else "after a win")
            m["rest_h"] = rest_h if i == 0 else 0
            streak = (min(streak, 0) - 1) if m["result"] == "loss" else (max(streak, 0) + 1 if m["result"] == "win" else 0)
        prev_end = s[-1]["end"]
    # party: teammates met at least twice on the same side, or Steam friends (when the friend list is public)
    cnt = Counter(p for m in ms for p in m["mates"])
    try:
        from wily.matches import steamlink
        steam_friends = steamlink.cached_friends(sid)
    except Exception:
        steam_friends = set()
    friends = {p for p, c in cnt.items() if c >= 2} | (set(cnt) & steam_friends)
    for m in ms:
        m["party"] = [p for p in m["mates"] if p in friends]
        m["party_size"] = 1 + len(m["party"]) if m["source"] in ("demo", "steam") else None
    # journal: the latest check-in within 6 h before the match
    J = journal(sid)
    for m in ms:
        best = None
        for e in J:
            t = _local(e["time"])
            if t <= m["start"] + dt.timedelta(minutes=30) and (m["start"] - t).total_seconds() <= 6 * 3600:
                best = e
        m["checkin"] = best
    overall = _stats(ms)

    def factor(title, key_fn, order=None):
        groups = defaultdict(list)
        for m in ms:
            k = key_fn(m)
            if k is not None:
                groups[k].append(m)
        rows = []
        for k, g in groups.items():
            others = [m for m in ms if key_fn(m) is not None and key_fn(m) != k]
            st, so = _stats(g), _stats(others)
            z = _cmp(st, so)
            rows.append({"group": k, **{a: b for a, b in st.items() if a != "sd"}, "delta": None if st["perf"] is None or so["perf"] is None else round(st["perf"] - so["perf"], 2),
                         "z": z, "level": _level(z, st["n"])})
        if order:
            rows.sort(key=lambda r: order.index(r["group"]) if r["group"] in order else 99)
        return {"title": title, "rows": rows}

    F = [
        factor("Time of day", lambda m: _bucket_hour(m["start"].hour),
               ["morning (6am-12pm)", "afternoon (12pm-6pm)", "evening (6pm-11pm)", "night (11pm-6am)"]),
        factor("Game in the session", lambda m: "4th game and later" if m["index"] >= 4 else f"{ORD[m['index']]} game",
               ["1st game", "2nd game", "3rd game", "4th game and later"]),
        factor("After the previous result", lambda m: m["prev"], ["1st game", "after a win", "after a loss", "after 2+ losses"]),
        factor("Group", lambda m: None if m["party_size"] is None else ("solo" if m["party_size"] == 1 else "duo" if m["party_size"] == 2 else f"group of {m['party_size']}"),
               ["solo", "duo", "group of 3", "group of 4", "group of 5"]),
        factor("Day", lambda m: "weekend" if m["start"].weekday() >= 5 else "weekday", ["weekday", "weekend"]),
        factor("Rest before the session", lambda m: None if m["index"] != 1 or m["rest_h"] is None else ("under 12 h" if m["rest_h"] < 12 else "12 h or more"),
               ["under 12 h", "12 h or more"]),
        factor("Sleep (journal)", lambda m: None if not m["checkin"] or m["checkin"].get("sleep_h") in (None, "") else
               ("under 6 h" if float(m["checkin"]["sleep_h"]) < 6 else "6 h to 7.5 h" if float(m["checkin"]["sleep_h"]) < 7.5 else "7.5 h or more"),
               ["under 6 h", "6 h to 7.5 h", "7.5 h or more"]),
        factor("Warm-up (journal)", lambda m: None if not m["checkin"] or not m["checkin"].get("warmup") else
               ("no warm-up" if m["checkin"]["warmup"] == "none" else "warmed up"), ["no warm-up", "warmed up"]),
        factor("Energy (journal)", lambda m: None if not m["checkin"] or not m["checkin"].get("energy") else
               ("low (1-2)" if int(m["checkin"]["energy"]) <= 2 else "medium (3)" if int(m["checkin"]["energy"]) == 3 else "high (4-5)"),
               ["low (1-2)", "medium (3)", "high (4-5)"]),
    ]
    F = [f for f in F if f["rows"]]
    # partners
    partners = []
    for p in friends:
        g = [m for m in ms if p in m["party"]]
        st = _stats(g)
        partners.append({"steamid": str(p), "name": config.display_name(p, _name_of(p, g)), **{a: b for a, b in st.items() if a != "sd"}})
    partners.sort(key=lambda x: -x["n"])
    unknown = [p["steamid"] for p in partners if p["name"] == p["steamid"]]
    if unknown:  # partners seen only in Valve's match info: ask Steam for their names (needs the API key)
        try:
            from wily.matches import steamlink
            got = steamlink.names(unknown)
            for p in partners:
                p["name"] = got.get(p["steamid"], p["name"])
        except Exception:
            pass
    # sessions summary
    slen = [len(s) for s in sessions]
    tilt = sum(1 for s in sessions for i in range(2, len(s)) if s[i - 1]["result"] == "loss" and s[i - 2]["result"] == "loss")
    recs = recommendations(F, overall, sessions, partners)
    for f in F:   # the output in the player's language, the English kept as the key
        f["key"], f["title"] = f["title"], tr(f["title"])
        for r in f["rows"]:
            r["key"], r["group"] = r["group"], tr(r["group"])
    return {"n": len(ms), "overall": {a: b for a, b in overall.items() if a != "sd"}, "factors": F, "partners": partners,
            "sessions": {"n": len(sessions), "avg_games": round(sum(slen) / len(slen), 1), "max_games": max(slen),
                         "games_after_2_losses": tilt, "last": [{"start": s[0]["start"].isoformat(timespec="minutes"), "games": len(s),
                                                               "record": f"{sum(1 for m in s if m['result'] == 'win')}-{sum(1 for m in s if m['result'] == 'loss')}",
                                                               "perf": [m["perf"] for m in s]} for s in sessions[-6:]]},
            "sources_count": Counter(m["source"] for m in ms), "journal_n": len(J), "recs": recs, "rating_source": RATING_SRC,
            "matches": [{"id": m["id"], "start": m["start"].isoformat(timespec="minutes"), "map": m["map"], "result": m["result"], "perf": m["perf"],
                         "index": m["index"], "party_size": m["party_size"], "source": m["source"]} for m in ms]}


def _name_of(p, ms):
    for m in ms:
        f = os.path.join(config.DEEP, str(m["id"]), "samples.parquet")
        if os.path.exists(f):
            s = pd.read_parquet(f, columns=["steamid", "name"])
            x = s[s.steamid == p]
            if len(x):
                return x.name.iloc[0]
    return str(p)


ORD = {1: "1st", 2: "2nd", 3: "3rd"}


def _fr(v):
    return f"{v:.2f}"


def recommendations(F, overall, sessions, partners):
    """Personal rules drawn from the player's own history: a rule (stop, break, time slot, group) only when the gap
    is reliable, never from a handful of games."""
    R = []
    sure = lambda r: r and r["level"] == "reliable"
    fx = {f["title"]: {r["group"]: r for r in f["rows"]} for f in F}
    idx = fx.get("Game in the session", {})
    late = idx.get("4th game and later") if sure(idx.get("4th game and later")) else idx.get("3rd game")
    if sure(late) and (late["delta"] or 0) < 0:
        a, b, n, lim = _fr(late['perf']), _fr(overall['perf']), late['n'], 2 if late['group'].startswith('3') else 3
        R.append({"kind": "stop", "level": late["level"], "text": tr("Your games from the 4th of a session on are clearly worse (rating {a} vs {b} on average, over {n} games): set yourself a limit of {lim} games per session.", a=a, b=b, n=n, lim=lim)
                  if late["group"].startswith("4") else tr("Your 3rd games of a session are clearly worse (rating {a} vs {b} on average, over {n} games): set yourself a limit of {lim} games per session.", a=a, b=b, n=n, lim=lim)})
    after = fx.get("After the previous result", {}).get("after 2+ losses")
    if sure(after) and (after["delta"] or 0) < 0:
        R.append({"kind": "tilt", "level": after["level"], "text": tr("After 2 losses in a row: {w}% wins and a rating of {r} ({n} games). Rule: a break of at least 30 min, or end the session.", w=after['winrate'], r=_fr(after['perf']), n=after['n'])})
    hours = fx.get("Time of day", {})
    good = [r for r in hours.values() if sure(r) and (r["delta"] or 0) > 0]
    bad = [r for r in hours.values() if sure(r) and (r["delta"] or 0) < 0]
    for r in good[:1]:
        R.append({"kind": "hour", "level": r["level"], "text": tr("You play best in the {slot}: rating {r} over {n} games. Schedule your ranked sessions in that slot.", slot=tr(r['group']), r=_fr(r['perf']), n=r['n'])})
    for r in bad[:1]:
        R.append({"kind": "hour", "level": r["level"], "text": tr("In the {slot}, your rating drops to {r} ({n} games): keep that slot for Deathmatch or lineup practice.", slot=tr(r['group']), r=_fr(r['perf']), n=r['n'])})
    grp = fx.get("Group", {})
    solo, duo = grp.get("solo"), grp.get("duo")
    if solo and duo and solo["perf"] is not None and duo["perf"] is not None and (sure(solo) or sure(duo)):
        better = "as a duo" if duo["perf"] > solo["perf"] else "solo"
        kw = dict(a=_fr(max(duo['perf'], solo['perf'])), b=_fr(min(duo['perf'], solo['perf'])), d=duo['n'], s=solo['n'])
        R.append({"kind": "party", "level": _level(duo.get("z"), duo["n"]) if better == "as a duo" else _level(solo.get("z"), solo["n"]),
                  "text": tr("You perform better as a duo: rating {a} vs {b} ({d} games as a duo, {s} solo).", **kw) if better == "as a duo"
                  else tr("You perform better solo: rating {a} vs {b} ({d} games as a duo, {s} solo).", **kw)})
    for p in partners[:2]:
        if p["n"] >= 3:
            R.append({"kind": "partner", "level": "trend" if p["n"] >= 5 else "not enough data",
                      "text": tr("With {name}: {w} wins, {l} losses, rating {r} ({n} games together).", name=p['name'], w=p['w'], l=p['l'], r=_fr(p['perf']), n=p['n'])})
    return R


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    r = analyze(sys.argv[1] if len(sys.argv) > 1 else config.logged_in_account()[0])
    print(json.dumps(r, ensure_ascii=False, indent=1, default=str)[:6000])
