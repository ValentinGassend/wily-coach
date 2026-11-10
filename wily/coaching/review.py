"""Cold review ("bilan"): what changed in the last session compared with the matches before, how much,
the likely reasons (time of day, session length, maps, group, sleep, experiments started), what was tested
and what to test next. Every "why" is a coincidence worth checking, not a proof: the text says so.
The page shows it in three tiers (04/10): a quick brief (the record, the rating's trend match by match, what works,
what slips, the one thing for next time), a brief per map of the session (record, rating, sides, what to play and
to avoid there) and the deep dive (every change with its possible reasons, the pro insights summed over the
session, the focus areas, the tests). New keys only: the page of an older plan still reads it.
"""
import datetime as dt
import json
import math
import os
from collections import Counter

import pandas as pd

from wily.core import i18n
from wily.core.i18n import N_, tr, trn

KPI = {  # key: (label, unit, higher is better)
    "rating": (N_("Match rating (≈ HLTV 2.0)"), "", True),
    "adr": (N_("Damage per round"), "", True),
    "traded": (N_("Deaths traded"), "%", True),
    "isolated": (N_("Isolated deaths (per 24 rounds)"), "", False),
    "adv_throw": (N_("Man advantages thrown"), "%", False),
    "nades": (N_("Grenades that died with you (per 24 rounds)"), "", False),
    "xhair": (N_("Crosshair offset before the duel"), "°", False),
    "open": (N_("Opening duels won"), "%", True),
}
# experiments whose measure is one of these numbers
EXP_KPI = {"trade_distance": "isolated", "nades_40s": "nades", "prefire": "xhair", "advantage": "adv_throw", "opening": "open",
           "session_limit": "rating", "warmup": "rating", "rotation": "isolated", "retake_group": "isolated", "silent": "isolated"}
RULE_KPI = {"trade": "traded", "nades": "nades", "xhair": "xhair", "open": "open", "early": "isolated", "lastalive": "isolated",
            "hold": "isolated", "flash": "traded"}


def _num(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def per_match(st, mid):
    """The numbers of one match, from stats.json and the mid-round row."""
    from wily.coaching import context
    o = st["overview"]
    r = max(st["rounds"], 1)
    v = {"rating": context.rating(o["kills"], o["deaths"], o["assists"], o["adr"], o["kast_pct"], r), "adr": o["adr"],
         "nades": sum(len(x["grenades_unused_at_death"]) for x in st["per_round"]) / r * 24,
         "xhair": (st["aim"].get("crosshair_placement") or {}).get("median_error_deg")}
    d = o["trades"]["my_deaths"]
    v["traded"] = 100 * o["trades"]["my_deaths_traded"] / d if d else None
    ow, ol = o["opening_duels"]["won"], o["opening_duels"]["lost"]
    v["open"] = 100 * ow / (ow + ol) if ow + ol else None
    if mid is not None:
        rounds = _num(mid.get("rounds")) or r
        v["isolated"] = (_num(mid.get("isolated_deaths")) or 0) / max(rounds, 1) * 24
        ar = _num(mid.get("adv_rounds")) or 0
        v["adv_throw"] = 100 * (_num(mid.get("adv_throw")) or 0) / ar if ar >= 3 else None
    return v


def _insights_of(sid, st):
    """A match's pro insights (pro_analyst), computed again from its demo when its stats.json has none or the first
    version's (then saved in it): a few seconds a match, once."""
    pi = st.get("pro_insights")
    if isinstance(pi, dict) and pi.get("v") == 2:
        return pi
    from wily.core import config
    mid = str((st.get("match") or {}).get("match_id") or "")
    dem = config.demo(mid)
    if not mid or not os.path.exists(dem):
        return None
    try:
        from wily.demos import analyze
        pi = analyze.analyze(dem, int(sid)).get("pro_insights")
    except Exception:
        return None
    if not isinstance(pi, dict):
        return None
    st["pro_insights"] = pi
    f = os.path.join(config.player_dir(sid), "matches", mid, "stats.json")
    try:
        with open(f, encoding="utf-8") as fh:
            cur = json.load(fh)
        cur["pro_insights"] = pi
        config.write_json(f, cur, default=str)
    except (OSError, ValueError):
        pass
    return pi


def _map_name(mp):
    return str(mp).split("_")[-1].capitalize()


# ---------- the analyst's reads (04/10) ----------
# read -> (where its base reference is: "mid" = the mid-round benchmarks, "ref" = the base benchmarks, its metric
# there, the fewest cases to say anything, higher is better)
READ_REF = {"repeek": ("mid", "repeek", 8, False), "untraded": ("ref", "untraded_pct", 8, False),
            "flash": ("ref", "flash_used_pct", 6, True), "fake": ("mid", "fake_pulled", 4, False),
            "clutch": ("ref", "clutch_multi_pct", 4, False)}
READ_GAP = 5   # percent points from the base median: less says nothing
_ROWS = {}


def _rows(path):
    """A base file (population or mid-round: one row per player of a match) by player, read once while unchanged."""
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return None
    hit = _ROWS.get(path)
    if hit and hit[0] == mt:
        return hit[1]
    try:
        df = pd.read_parquet(path)
        df.index = df.steamid.astype(str)
    except Exception:
        df = None
    if len(_ROWS) > 4000:
        _ROWS.clear()
    _ROWS[path] = (mt, df)
    return df


def _rl(x):
    return [int(r) for r in str(x or "").split(",") if r.strip().isdigit()]


def _cnt(r, k):
    v = _num(r.get(k)) if r is not None else None
    return int(v) if v is not None else None


def match_reads(sid, mid, st):
    """What an analyst points at in one match for one player, each read with the rounds behind it: re-peek after a
    kill, deaths without impact, flashes your team uses and the death spots (the match's analysis), pulled by a fake
    and the 1v2+ clutches (the base's numbers of that match). None without any."""
    from wily.core import config
    out = {}
    pi = st.get("pro_insights")
    if isinstance(pi, dict) and pi.get("v") == 2:
        for k in ("repeek", "untraded", "flash"):
            if isinstance(pi.get(k), dict) and pi[k].get("of"):
                out[k] = {"value": int(pi[k]["value"]), "of": int(pi[k]["of"]), "rounds": list(pi[k].get("rounds") or [])}
        if pi.get("spots"):   # by name, as players call them; a bombsite is where a CT anchor dies: the role, not a habit
            from wily.insights import nades
            sp = Counter()
            for k, v in pi["spots"].items():
                if not str(k).startswith("Bombsite"):
                    sp[nades.humanize(k, st.get("map")) or str(k)] += int(v)
            out["spots"] = dict(sp.most_common())
    sid = str(sid)
    mr = _rows(os.path.join(config.OUT, "population", "midround", f"{mid}.parquet"))
    r = mr.loc[sid] if mr is not None and sid in mr.index else None
    if r is not None and not isinstance(r, pd.Series):
        r = r.iloc[0]
    if r is not None:
        n = _cnt(r, "fake_n")
        if n:
            out["fake"] = {"value": _cnt(r, "fake_pulled") or 0, "of": n, "rounds": _rl(r.get("fake_rounds"))}
        n = _cnt(r, "kill_rounds")
        if n and "repeek" not in out:
            out["repeek"] = {"value": _cnt(r, "repeek") or 0, "of": n, "rounds": _rl(r.get("repeek_rounds"))}
    po = _rows(os.path.join(config.OUT, "population", f"{mid}.parquet"))
    r = po.loc[sid] if po is not None and sid in po.index else None
    if r is not None and not isinstance(r, pd.Series):
        r = r.iloc[0]
    if r is not None:
        n = _cnt(r, "clutch_n")
        if n:
            out["clutch"] = {"value": _cnt(r, "clutch_multi") or 0, "of": n, "won": _cnt(r, "clutch_won") or 0,
                             "rounds": _rl(r.get("clutch_multi_rounds")), "all": _rl(r.get("clutch_rounds"))}
        n = _cnt(r, "dead_n")
        if n and "untraded" not in out:
            out["untraded"] = {"value": _cnt(r, "untraded_n") or 0, "of": n, "rounds": []}
        n = _cnt(r, "flash_blind")
        if n and "flash" not in out:
            out["flash"] = {"value": _cnt(r, "flash_used") or 0, "of": n, "rounds": []}
    return out or None


def _ref(kind, metric, mb, bench):
    """The base's (and the pros') reference of a read: from the mid-round benchmarks or the base benchmarks."""
    src = (mb if kind == "mid" else bench) or {}
    m = (src.get("metrics") or {}).get(metric)
    if not m:
        return None
    return {"median": m.get("median"), "good": m.get("good"), "pro": m.get("pro"), "higher_rank": m.get("higher_rank_median"),
            "you_all": m.get("you"), "percentile": m.get("percentile"), "n": m.get("n")}


def reads(sid, sts, mb=None, bench=None, where_max=6, catch_up=True):
    """The reads summed over a set of matches (a session, or all of them), each against the base (median, higher
    ranks, pros when the pro demos tell) with a verdict, and the matches and rounds where it happened. catch_up: the
    matches analyzed before the reads get theirs from their demo (a few seconds each; the session only)."""
    tot, where, n = {}, {}, 0
    spots, deaths_on = Counter(), Counter()
    for st in sts:
        mid = str((st.get("match") or {}).get("match_id") or "")
        if mid and catch_up:
            _insights_of(sid, st)
        r = match_reads(sid, mid, st) if mid else None
        if not r:
            continue
        n += 1
        for k in READ_REF:
            x = r.get(k)
            if not x:
                continue
            t = tot.setdefault(k, {"value": 0, "of": 0})
            t["value"] += x["value"]
            t["of"] += x["of"]
            if k == "clutch":
                t["won"] = t.get("won", 0) + x.get("won", 0)
            if x.get("rounds"):
                where.setdefault(k, []).append({"id": mid, "map": st["map"], "time": (st.get("match") or {}).get("time"),
                                                "rounds": x["rounds"]})
        for place, c in (r.get("spots") or {}).items():
            spots[(st["map"], place)] += c
        deaths_on[st["map"]] += (r.get("untraded") or {}).get("of") or 0   # all your deaths on that map
    items = []
    for k, (kind, metric, mn, hib) in READ_REF.items():
        t = tot.get(k)
        if not t or not t["of"]:
            continue
        pct = 100 * t["value"] / t["of"]
        ref = _ref(kind, metric, mb, bench)
        sev = None
        if t["of"] >= mn and ref and ref.get("median") is not None:
            worse = (ref["median"] - pct) if hib else (pct - ref["median"])
            good = ref.get("good")
            if worse >= READ_GAP:
                sev = "high" if worse >= 3 * READ_GAP else "medium"
            elif good is not None and ((pct >= good) if hib else (pct <= good)):
                sev = "positive"
        ws = sorted(where.get(k, []), key=lambda w: str(w.get("time") or ""), reverse=True)[:where_max]
        items.append({"id": k, "value": t["value"], "of": t["of"], "pct": round(pct), "won": t.get("won"),
                      "enough": t["of"] >= mn, "severity": sev, "ref": ref, "where": ws})
    for (mp, place), c in spots.most_common(5):   # bombsites are left out per match (the anchor's role), and the
        if c >= 4 and c >= 0.3 * deaths_on[mp] and not str(mp).startswith("cs_"):   # hostage maps (the fight is at the hostages)
            items.append({"id": "spot", "severity": "medium", "value": c, "of": deaths_on[mp], "map": mp,
                          "place": place, "enough": True})
    order = {"high": 0, "medium": 1, None: 2, "positive": 3}
    items.sort(key=lambda x: order.get(x["severity"], 2))
    return {"matches": n, "items": items}


def pro_summary(sid, sts, mb=None, bench=None):
    """The reads of the session's matches, against the base (what the review's deep dive shows)."""
    return reads(sid, sts, mb, bench)


def map_briefs(recent, by_id, adv):
    """Each map of the session: record, rating, damage, round wins per side, and what to play and to avoid there
    (the map advice, per side)."""
    out = {}
    for r in recent:
        st = by_id.get(r["id"]) or {}
        m = out.setdefault(r["map"], {"map": r["map"], "games": 0, "wins": 0, "losses": 0, "ratings": [], "adr": [],
                                      "T": [0, 0], "CT": [0, 0]})
        m["games"] += 1
        m["wins"] += r["result"] == "win"
        m["losses"] += r["result"] == "loss"
        m["ratings"].append(r["rating"])
        m["adr"].append(r["adr"])
        for side in ("T", "CT"):
            m[side][0] += int(((st.get("overview") or {}).get("rounds_won_on_side") or {}).get(side) or 0)
            m[side][1] += int((st.get("rounds_per_side") or {}).get(side) or 0)
    res = []
    for mp, m in out.items():
        adv_m = ((adv or {}).get("maps") or {}).get(mp) or {}
        sides = {}
        for side in ("T", "CT"):
            x = adv_m.get(side) or {}
            b = x.get("bullets") or []
            sides[side] = {"won": m[side][0], "of": m[side][1], "record": x.get("record"),
                           "play": next((y["text"] for y in b if y.get("kind") == "exploit"), None),
                           "avoid": next((y["text"] for y in b if y.get("kind") == "avoid"), None)}
        res.append({"map": mp, "games": m["games"], "wins": m["wins"], "losses": m["losses"],
                    "rating": round(sum(m["ratings"]) / len(m["ratings"]), 2), "adr": round(sum(m["adr"]) / len(m["adr"]), 1),
                    "sides": sides})
    res.sort(key=lambda x: (-x["games"], -x["rating"]))
    return res


def _mean_sd(xs):
    xs = [x for x in xs if x is not None]
    if not xs:
        return None, None, 0
    m = sum(xs) / len(xs)
    sd = pd.Series(xs).std() if len(xs) > 1 else None
    return m, (None if sd is None or math.isnan(sd) else float(sd)), len(xs)


# the windows the Review can show (07/10, the user: "la dernière session exactement comme tu fais, mais un bouton pour
# changer en last 7 days, this week, this month"): each compared with as many matches just before it (12 at least)
def _md(d):
    """A day and month as the player's language writes them (i18n.day_month)."""
    return i18n.day_month(d)


PERIODS = {"7d": N_("the last 7 days"), "week": N_("this week"), "month": N_("this month"), "30d": N_("the last 30 days"),
           "all": N_("all your matches")}   # 16/10, the user: "rajoute un filtre pour all"


def _window(rows, period, now=None):
    """The matches of a period (rows sorted by time): the last session, or a span of the calendar until now."""
    now = now or dt.datetime.now()
    if period == "all":   # every analyzed match: nothing before it to compare with
        return list(rows)
    if period == "7d":
        start = now - dt.timedelta(days=7)
    elif period == "30d":
        start = now - dt.timedelta(days=30)
    elif period == "week":   # since Monday
        start = (now - dt.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return None
    return [r for r in rows if r["time"] >= start]


def periods(sid, stats, mid_rows, ctx, exps, adv, mb=None):
    """The other windows of the Review, by key (None: fewer than 2 matches in it)."""
    out = {}
    for k in PERIODS:
        try:
            out[k] = build(sid, stats, mid_rows, ctx, exps, adv, mb, period=k)
        except Exception as e:
            print(f"review {k}: {e}", flush=True)
            out[k] = None
    return out


def build(sid, stats, mid_rows, ctx, exps, adv, mb=None, period="session"):
    """-> the review, or None without at least 3 dated matches with a demo. period: "session" (the last session, or
    the last 3 matches) or a key of PERIODS."""
    rows, by_id = [], {}
    for st in stats:
        t = (st.get("match") or {}).get("time")
        if not t:
            continue
        rows.append({"id": st["match"]["match_id"], "time": dt.datetime.fromisoformat(t), "map": st["map"], "result": st["result"],
                     "score": st["final_score"], **per_match(st, mid_rows.get(st["match"]["match_id"]))})
        by_id[st["match"]["match_id"]] = st
    rows.sort(key=lambda r: r["time"])
    if len(rows) < 3:
        return None
    ms = (ctx or {}).get("matches") or []
    if period in PERIODS:   # a span of the calendar, against as many matches just before it
        recent = _window(rows, period)
        if not recent or len(recent) < 2:
            return None
        before = [r for r in rows if r["time"] < recent[0]["time"]][-max(12, len(recent)):]
        label = trn(len(recent), "{period} ({n} game)", "{period} ({n} games)", period=tr(PERIODS[period]))   # 16/10: was left in English
    else:
        # recent window: the last session when it has 2 games or more, else the last 3 matches
        last = rows[-1]
        recent = [last]
        for r in reversed(rows[:-1]):
            gap = (recent[-1]["time"] - r["time"]).total_seconds() / 3600
            if gap <= 3.5:
                recent.append(r)
            else:
                break
        recent = list(reversed(recent))
        if len(recent) < 2:
            recent = rows[-3:]
        before = [r for r in rows if r["time"] < recent[0]["time"]][-12:]
        label = (tr("your last session ({n} games, on {date})", n=len(recent), date=_md(recent[0]['time'])) if len(recent) >= 2 and
                 (recent[-1]["time"] - recent[0]["time"]).total_seconds() < 6 * 3600 else trn(len(recent), "your last match", "your last {n} matches"))
    # context of each window, for the reasons
    def share_late(win):
        return sum(1 for r in win if r["time"].hour >= 23 or r["time"].hour < 6) / max(len(win), 1)
    wr = {}
    for side in ("T", "CT"):
        for mp, x in ((adv or {}).get("maps") or {}).items():
            rec = (x.get(side) or {}).get("record")
            if rec and rec[1]:
                w, t = wr.get(mp, (0, 0))
                wr[mp] = (w + rec[0], t + rec[1])
    map_win = {mp: 100 * w / t for mp, (w, t) in wr.items() if t >= 15}
    worst_map = min(map_win, key=map_win.get) if len(map_win) >= 2 else None
    best_map = max(map_win, key=map_win.get) if len(map_win) >= 2 else None
    reasons_bad, reasons_good = [], []
    if before and share_late(recent) >= 0.5 and share_late(before) < 0.3:
        n = sum(1 for r in recent if r["time"].hour >= 23 or r["time"].hour < 6)
        reasons_bad.append(tr("{n} of these {m} games after 11pm", n=n, m=len(recent)))
    if len(recent) >= 4 and period not in PERIODS:   # a span of days is not one sitting
        reasons_bad.append(tr("a session of {n} games in a row: fatigue builds up after each game", n=len(recent)))
    half = max(2, math.ceil(len(recent) / 2))
    if worst_map and sum(1 for r in recent if r["map"] == worst_map) >= half:
        reasons_bad.append(tr("{n} game(s) on {map}, your hardest map ({p}% of rounds won)", n=sum(1 for r in recent if r['map'] == worst_map),
                              map=worst_map.split('_')[-1].capitalize(), p=f"{map_win[worst_map]:.0f}"))
    if best_map and sum(1 for r in recent if r["map"] == best_map) >= half:
        reasons_good.append(tr("{n} game(s) on {map}, your best map ({p}% of rounds won)", n=sum(1 for r in recent if r['map'] == best_map),
                               map=best_map.split('_')[-1].capitalize(), p=f"{map_win[best_map]:.0f}"))
    party = {m["id"]: m.get("party_size") for m in ms}
    pr = [party.get(r["id"]) for r in recent if party.get(r["id"])]
    pb = [party.get(r["id"]) for r in before if party.get(r["id"])]
    if pr and pb:
        solo_r, solo_b = sum(1 for p in pr if p == 1) / len(pr), sum(1 for p in pb if p == 1) / len(pb)
        grp = next((f for f in (ctx or {}).get("factors", []) if f.get("key", f["title"]) == "Group"), None)
        solo_perf = next((row["delta"] for row in (grp or {}).get("rows", []) if row.get("key", row["group"]) == "solo"), None)
        if solo_r - solo_b >= 0.5:
            (reasons_bad if (solo_perf or 0) < 0 else reasons_good).append(tr("you played solo more often than usual"))
        elif solo_b - solo_r >= 0.5:
            (reasons_good if (solo_perf or 0) < 0 else reasons_bad).append(tr("you played in a group more often than usual"))
    started = [e for e in (exps or {}).get("experiments", []) if e.get("started") and
               dt.datetime.fromisoformat(e["started"]) <= recent[-1]["time"] and dt.datetime.fromisoformat(e["started"]) >= (before[-1]["time"] if before else rows[0]["time"])]
    changes, stable = [], []
    for k, (lab, unit, hib) in KPI.items():
        a, sa, na = _mean_sd([r.get(k) for r in recent])
        b, sb, nb = _mean_sd([r.get(k) for r in before])
        if a is None or b is None or na < 2 or nb < 2:
            continue
        se = math.sqrt((sa or abs(a) * 0.2 or 1) ** 2 / na + (sb or abs(b) * 0.2 or 1) ** 2 / nb)
        z = (a - b) / se if se else 0
        better = (a > b) == hib
        item = {"key": k, "label": lab, "unit": unit, "higher_better": hib, "before": round(b, 2), "after": round(a, 2),
                "delta": round(a - b, 2), "better": better, "z": round(z, 2), "n_before": nb, "n_after": na,
                # 8 indicators compared on a few games: 2.5 standard errors before calling a gap clear (with 2, one
                # session in three would show a "clear" change that is only chance)
                "level": "clear" if abs(z) >= 2.5 else "trend" if abs(z) >= 1.5 else None, "why": []}
        if item["level"] is None:
            stable.append(lab)
            continue
        for e in started:
            if EXP_KPI.get(e["template"]) == k:
                item["why"].append(tr("matches the experiment '{title}' started on {date}", title=e['title'], date=_md(dt.datetime.fromisoformat(e['started']))))
        if k in ("rating", "adr", "traded", "open"):
            item["why"] += reasons_good if better else reasons_bad
        changes.append(item)
    changes.sort(key=lambda c: -abs(c["z"]))
    # the three axes of the moment, with their trend
    axes = []
    for r in ((adv or {}).get("rules") or [])[:3]:
        k = RULE_KPI.get(r.get("id"))
        a, _, na = _mean_sd([x.get(k) for x in recent]) if k else (None, None, 0)
        b, _, nb = _mean_sd([x.get(k) for x in before]) if k else (None, None, 0)
        trend = None
        if a is not None and b is not None and na and nb:
            hib = KPI[k][2]
            trend = "better" if (a > b) == hib and abs(a - b) > 0.05 * max(abs(b), 1) else "worse" if abs(a - b) > 0.05 * max(abs(b), 1) else "stable"
        axes.append({"id": r.get("id"), "title": r.get("title"), "short": r.get("short"), "do": (r.get("do") or [])[:2],
                     "drills": (r.get("drills") or [])[:1], "kpi": k, "kpi_label": tr(KPI[k][0]) if k else None, "unit": KPI[k][1] if k else None,
                     "before": None if b is None else round(b, 2), "after": None if a is None else round(a, 2), "trend": trend,
                     "sources": (r.get("sources") or [])[:2]})
    wins = sum(1 for r in recent if r["result"] == "win")
    losses = sum(1 for r in recent if r["result"] == "loss")
    ex = exps or {}
    active = [e for e in ex.get("experiments", []) if e["status"] == "active"]
    done = [e for e in ex.get("experiments", []) if e["status"] != "active"]
    nxt = None
    worse = [c for c in changes if not c["better"]]
    if worse:
        nxt = tr("Fix what is slipping: {what} ({a} → {b}).", what=tr(worse[0]['label']).lower(), a=f"{worse[0]['before']:g}", b=f"{worse[0]['after']:g}")
    elif axes:
        nxt = tr("Stay on track with your #1 focus: {what}.", what=(axes[0]['short'] or "").lower())
    # 13/10, the user: "get few data on dot hover (map, result, rating, adr)": each dot carries its score and ADR too
    trend = [{"id": r["id"], "time": r["time"].isoformat(timespec="minutes"), "map": r["map"], "result": r["result"],
              "score": r.get("score"), "adr": round(r["adr"], 1) if r.get("adr") is not None else None,
              "rating": round(r["rating"], 2), "recent": r in recent} for r in before + recent]
    try:
        # the session's matches get their reads from their demo when they miss them; a longer span reads what is there
        pro = reads(sid, [by_id[r["id"]] for r in recent if r["id"] in by_id], mb, (adv or {}).get("bench"), catch_up=period not in PERIODS)
    except Exception as e:   # a bonus: never the review's end
        pro = {"matches": 0, "items": [], "error": str(e)[:200]}
    return {"label": label, "period": period, "since": recent[0]["time"].isoformat(timespec="minutes"),
            "trend": trend, "maps": map_briefs(recent, by_id, adv), "pro": pro,
            "session": {"games": len(recent), "wins": wins, "losses": losses,
                        "matches": [{"id": r["id"], "time": r["time"].isoformat(timespec="minutes"), "map": r["map"], "result": r["result"],
                                     "score": r["score"], "rating": round(r["rating"], 2)} for r in recent]},
            "n_before": len(before), "changes": changes, "stable": stable, "axes": axes, "next": nxt,
            "tests": {"active": active, "done": done[-4:], "suggested": ex.get("suggested", [])[:3]}}


def write_periods(sid):
    """The Review's windows of a player computed again from their saved analysis and written to their page (the plan's
    other parts untouched): for the profiles whose plan was built before the periods (07/10)."""
    from wily.core import config
    from wily.insights import midround
    from wily.app import build_app
    sid = int(sid)
    pdir = config.player_dir(sid)
    f = os.path.join(pdir, "advice.json")
    adv = json.load(open(f, encoding="utf-8"))
    PL = adv.get("plan") or {}
    stats = []
    mdir = os.path.join(pdir, "matches")
    for mid in os.listdir(mdir) if os.path.exists(mdir) else []:
        g = os.path.join(mdir, mid, "stats.json")
        if os.path.exists(g):
            st = json.load(open(g, encoding="utf-8"))
            if not st.get("error"):
                stats.append(st)
    mid_rows = {}
    for st in stats:
        g = os.path.join(midround.OUT, f"{st['match']['match_id']}.parquet")
        if os.path.exists(g):
            r = pd.read_parquet(g)
            r = r[r.steamid == sid]
            if len(r):
                mid_rows[st["match"]["match_id"]] = r.iloc[0].to_dict()
    P = periods(sid, stats, mid_rows, PL.get("context"), PL.get("experiments"), adv, (PL.get("mid") or {}).get("bench"))
    adv.setdefault("plan", {})["review_periods"] = P
    config.write_json(f, adv, separators=(",", ":"), default=str)
    build_app.write_player(str(sid))
    return {k: (v or {}).get("label") for k, v in P.items()}


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:]:
        print(s, write_periods(s))
