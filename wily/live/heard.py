"""What your team could hear in a match and what you did with it, after the match, from its demo (never live: no
sound radar). Valve's demos keep no voice (none in the 67 demos of your matches, 04/10), but they keep where everyone
was (samples.parquet, every 0.5 s) and the game's sound events: shots, reloads, scopes, grenade throws, the bomb's
plant and defuse. A running player makes footsteps: the demo's own footstep events are a few per round (324 in a
match whose players ran 2,384 s), so running is read from the positions (faster than 140 u/s: walking with shift is
130 at most).

The distances at which a sound gives you something to call are rough (the game plays sounds farther, quieter, through
walls, and these ignore the walls): a running enemy 1,100 u, a shot 2,000 (silenced 500), a reload or a grenade's pin
700, a scope 500, the bomb's plant 1,400 and defuse 1,100.

  moments(mid, sid)                      the enemies' sounds your team could hear, who heard each one
  analyze(mid, sid, live, mine, team)    with your calls: called or not, how fast, the right place, and around the
                                         ones you did not call (a fight, a teammate who heard it too, far)
  after_calls(mid, sid, live, team)      after a teammate's call naming a place (your team's sound, recorded when
                                         your team agreed): where you went, and how fast"""
import os

import numpy as np
import pandas as pd

from wily.core import config

HEAR = {"step": 1100, "shot": 2000, "quiet": 500, "throw": 700, "reload": 700, "scope": 500, "plant": 1400, "defuse": 1100}
KIND_RANK = ("plant", "defuse", "shot", "quiet", "step", "reload", "scope", "throw")   # what a moment is named after
RUN = 140            # u/s
GAP = 3.0            # s between two sounds of the same enemies: the same moment
BEFORE, AFTER, LONGEST = 1.0, 4.0, 10.0   # a call counts for a moment from 1 s before you hear it to 4 s after its
                                          # last sound, 10 s after you first heard it at most
FAR = 0.7            # all its sounds beyond 70% of their distance: far
NADES = {"weapon_hegrenade", "weapon_flashbang", "weapon_smokegrenade", "weapon_molotov", "weapon_incgrenade", "weapon_decoy"}
EVENTS = {"weapon_fire": None, "weapon_reload": "reload", "weapon_zoom": "scope", "bomb_beginplant": "plant", "bomb_begindefuse": "defuse"}
TICKRATE = 64
COLS = ["round", "t", "steamid", "kind", "X", "Y", "Z", "place", "other"]


def sounds(mid):
    """The match's sound events, cached next to its other files (sounds.parquet): round, t (s since the end of the
    freeze time), steamid, kind, X, Y, Z, place; and its hits (kind "hurt": steamid hit by other), for the fights."""
    d = os.path.join(config.DEEP, mid)
    f = os.path.join(d, "sounds.parquet")
    if os.path.exists(f):
        return pd.read_parquet(f)
    dem, rf = config.demo(mid), os.path.join(d, "rounds.parquet")
    if not (os.path.exists(dem) and os.path.exists(rf)):
        return None
    from demoparser2 import DemoParser
    R = pd.read_parquet(rf).sort_values("round")
    st, en, rn = R.start_tick.to_numpy(), R.end_tick.to_numpy(), R["round"].to_numpy()
    ev = dict(DemoParser(dem).parse_events(list(EVENTS) + ["player_hurt"], player=["X", "Y", "Z", "last_place_name"]))
    parts = []
    for name, kind in EVENTS.items():
        e = ev.get(name)
        if e is None or not len(e):
            continue
        if name == "weapon_fire":
            w = e["weapon"].astype(str)
            e = e[~w.str.contains("knife|bayonet|taser|c4", regex=True)]
            w = e["weapon"].astype(str)
            quiet = e["silenced"].fillna(False).astype(bool) if "silenced" in e else False
            k = np.where(w.isin(NADES), "throw", np.where(quiet, "quiet", "shot"))
        else:
            k = kind
        parts.append(pd.DataFrame({"tick": e.tick, "steamid": e.user_steamid, "kind": k, "X": e.user_X, "Y": e.user_Y, "Z": e.user_Z,
                                   "place": e.user_last_place_name, "other": None}))
    h = ev.get("player_hurt")
    if h is not None and len(h):
        parts.append(pd.DataFrame({"tick": h.tick, "steamid": h.user_steamid, "kind": "hurt", "X": h.user_X, "Y": h.user_Y, "Z": h.user_Z,
                                   "place": h.user_last_place_name, "other": h.attacker_steamid}))
    if not parts:
        S = pd.DataFrame(columns=COLS)
    else:
        S = pd.concat(parts, ignore_index=True)
        S["steamid"] = pd.to_numeric(S.steamid, errors="coerce")
        S["other"] = pd.to_numeric(S.other, errors="coerce")
        tk = S.tick.to_numpy()
        i = np.searchsorted(st, tk, side="right") - 1
        ok = (i >= 0) & (tk <= en[np.clip(i, 0, None)])
        S, i = S[ok].copy(), i[ok]
        S["round"] = rn[i]
        S["t"] = ((S.tick.to_numpy() - st[i]) / TICKRATE).round(2)
        S = S.dropna(subset=["steamid"])
        S["steamid"] = S.steamid.astype("int64")
        S["place"] = S.place.fillna("").astype(str)
        S = S[COLS].reset_index(drop=True)
    S.to_parquet(f)
    return S


def _steps(P):
    """Running players' footsteps, from their positions: a sound at each sample faster than RUN."""
    P = P.sort_values(["steamid", "round", "t"])
    g = P.groupby(["steamid", "round"])
    v = np.hypot(g.X.diff(), g.Y.diff()) / g.t.diff()
    s = P[(v > RUN) & (P.health > 0)]
    return pd.DataFrame({"round": s["round"], "t": s.t, "steamid": s.steamid, "kind": "step", "X": s.X, "Y": s.Y, "Z": s.Z,
                         "place": s.zone.fillna("").astype(str)})


class _Where:
    """Where a player was at a moment of a round (the nearest sample, within a second), None once dead."""

    def __init__(self, P, died):
        self.d = {k: (g.t.to_numpy(), g[["X", "Y", "Z"]].to_numpy(float), g.health.to_numpy())
                  for k, g in P.sort_values("t").groupby(["round", "steamid"])}
        self.died = died

    def at(self, r, s, t):
        if (r, s) in self.died and t > self.died[(r, s)]:
            return None
        x = self.d.get((r, s))
        if x is None or not len(x[0]):
            return None
        ts, xyz, hp = x
        i = int(np.searchsorted(ts, t))
        i = min(max(i, 0), len(ts) - 1)
        if i > 0 and abs(ts[i - 1] - t) < abs(ts[i] - t):
            i -= 1
        if abs(ts[i] - t) > 1.0 or hp[i] <= 0:
            return None
        return xyz[i]


def _load(mid):
    d = os.path.join(config.DEEP, mid)
    if not all(os.path.exists(os.path.join(d, f)) for f in ("samples.parquet", "loadout.parquet")):
        return None
    E = sounds(mid)
    if E is None:
        return None
    P = pd.read_parquet(os.path.join(d, "samples.parquet"))
    L = pd.read_parquet(os.path.join(d, "loadout.parquet"))
    died = {(int(x.round), int(x.steamid)): float(x.died_t) for x in L.itertuples() if pd.notna(x.died_t)}
    side = {(int(x.round), int(x.steamid)): x.side for x in L.itertuples()}
    names = P.drop_duplicates("steamid").set_index("steamid")["name"].to_dict()
    return E, P, died, side, names


def moments(mid, sid, data=None):
    """The enemies' sounds your team could hear, grouped: sounds of the same enemies less than GAP apart, at the same
    place. -> [{"round", "t0", "t1", "enemies", "kind", "kinds", "place", "heard": {steamid: {"t", "q"}}}]: q, the
    nearest of its sounds for that listener, as a share of its distance (1 = at the limit)."""
    data = data or _load(mid)
    if data is None:
        return None
    E, P, died, side, names = data
    sid = int(sid)
    W = _Where(P, died)
    snd = pd.concat([E[E.kind != "hurt"][COLS[:-1]], _steps(P)], ignore_index=True)
    out = []
    for (r, s), g in snd.sort_values("t").groupby(["round", "steamid"]):
        r, s = int(r), int(s)
        my, his = side.get((r, sid)), side.get((r, s))
        if my is None or his is None or his == my:
            continue
        mates = [p for (rr, p), sd in side.items() if rr == r and sd == my]
        cur = None
        for x in g.itertuples(index=False):
            if (r, s) in died and x.t > died[(r, s)] + 0.2:
                break   # a dead enemy makes no sound
            heard = {}
            for m in mates:
                p = W.at(r, m, x.t)
                if p is None:
                    continue
                q = float(np.sqrt((p[0] - x.X) ** 2 + (p[1] - x.Y) ** 2 + (p[2] - x.Z) ** 2)) / HEAR[x.kind]
                if q <= 1:
                    heard[m] = q
            if not heard:
                continue
            if cur is None or x.t - cur["t1"] > GAP:
                cur = {"round": r, "enemies": {s}, "t0": float(x.t), "t1": float(x.t), "kinds": {}, "places": {}, "heard": {}}
                out.append(cur)
            cur["t1"] = float(x.t)
            cur["kinds"][x.kind] = cur["kinds"].get(x.kind, 0) + 1
            if x.place:
                cur["places"][x.place] = cur["places"].get(x.place, 0) + 1
            for m, q in heard.items():
                h = cur["heard"].setdefault(m, {"t": float(x.t), "q": q, "last": float(x.t)})
                h["q"], h["last"] = min(h["q"], q), float(x.t)
    for m in out:
        m["place"] = max(m["places"], key=m["places"].get) if m["places"] else ""
    # several enemies at the same place at the same time: one moment ("2 at B")
    out.sort(key=lambda m: (m["round"], m["t0"]))
    merged = []
    for m in out:
        o = next((o for o in reversed(merged[-6:]) if o["round"] == m["round"] and o["place"] == m["place"] and m["t0"] <= o["t1"] + 1.5), None)
        if o is None:
            merged.append(m)
            continue
        o["enemies"] |= m["enemies"]
        o["t1"] = max(o["t1"], m["t1"])
        for k, n in m["kinds"].items():
            o["kinds"][k] = o["kinds"].get(k, 0) + n
        for p, h in m["heard"].items():
            q = o["heard"].get(p)
            if q is None:
                o["heard"][p] = dict(h)
            else:
                q["t"], q["q"], q["last"] = min(q["t"], h["t"]), min(q["q"], h["q"]), max(q["last"], h["last"])
    for m in merged:
        m["kind"] = next(k for k in KIND_RANK if k in m["kinds"])
        m["enemies"] = sorted(m["enemies"])
        del m["places"]
    return merged


def _place_info(map_name):
    """raw place -> (callout, side of the map)."""
    try:
        from wily.coaching import team
        from wily.demos.map_analysis import humanize
        regs = (team.map_meta().get(map_name) or {}).get("regions") or {}
        return {k: (humanize(k, map_name), v) for k, v in regs.items() if k != "?"}, humanize
    except Exception:
        return {}, (lambda k, m: k)


def _phrases(utts, live, offset=0.0):
    """Phrases of a recording placed in their round: [(round, t in the round, text)]; offset: where the file starts
    in the recording (the team's sound starts when it was switched on)."""
    starts = sorted(live.items())
    out = []
    for u in utts or []:
        t = float(u["start"]) + offset
        r = None
        for i, (rr, t0) in enumerate(starts):
            nxt = starts[i + 1][1] if i + 1 < len(starts) else float("inf")
            if t0 - 1 <= t < nxt - 1:
                r = (rr, t - t0)
                break
        if r:
            out.append((r[0], r[1], u["text"]))
    return out


def _call(text, map_name, pos_re):
    """A short phrase that gives an information (a sentence that names a place is not a call):
    {"zone": callout or None, "site", "regs": sides named}."""
    from wily.live import voice
    c = voice.parse_call(text, map_name)
    if not c and not (voice.classify(text, pos_re)["info"] and len(text.split()) <= 6):
        return None
    c = c or {}
    return {"zone": c.get("zone"), "site": c.get("site"), "regs": c.get("regs") or []}


def _right(call, place, info):
    """The call names the moment's place (True), another place (False), or none (None)."""
    if not (call["zone"] or call["site"] or call["regs"]):
        return None
    name, reg = info.get(place, (None, None))
    if call["zone"] and name and call["zone"] == name:
        return True
    if reg in ("A", "B") and (call["site"] == reg or reg in call["regs"]):
        return True
    return False


def analyze(mid, sid, live, mine, team=None, team_offset=0.0, map_name=None):
    """live: round -> its start in seconds of the recording; mine: your microphone's phrases; team: your team's (the
    team's sound, recorded only when your team agreed)."""
    from wily.live import voice
    data = _load(mid)
    if data is None or not live:
        return None
    E, P, died, side, names = data
    sid = int(sid)
    M = moments(mid, sid, data)
    if M is None:
        return None
    rounds = set(live)
    M = [m for m in M if m["round"] in rounds]
    info, humanize = _place_info(map_name)
    pos_re = voice._pos_re(map_name)
    mine_c = [(r, t, x, _call(x, map_name, pos_re)) for r, t, x in _phrases(mine, live)]
    mine_c = [c for c in mine_c if c[3]]
    team_c = [(r, t, x, _call(x, map_name, pos_re)) for r, t, x in _phrases(team, live, team_offset)] if team else []
    team_c = [c for c in team_c if c[3]]
    mine_any = _phrases(mine, live)
    fights = E[E.kind.isin(["shot", "quiet", "hurt"])]
    rows = []
    for m in M:
        r = m["round"]
        me = m["heard"].get(sid)
        mates = [p for p in m["heard"] if p != sid]
        row = {"round": r, "t": round(me["t"] if me else m["t0"], 1), "place": humanize(m["place"], map_name) if m["place"] else "",
               "n": len(m["enemies"]), "kind": m["kind"], "who": [names.get(p, "?") for p in sorted(m["heard"], key=lambda p: m["heard"][p]["t"])],
               "you": me is not None, "mates": len(mates)}
        if team is not None:
            row["team_called"] = any(c[0] == r and m["t0"] - BEFORE <= c[1] <= m["t1"] + AFTER for c in team_c)
        if me is None:
            rows.append(row)
            continue
        t0, t1 = me["t"], max(me["last"], m["t1"])
        calls = [c for c in mine_c if c[0] == r and t0 - BEFORE <= c[1] <= min(t1 + AFTER, t0 + LONGEST)
                 and _right(c[3], m["place"], info) is not False]   # a call naming another place is about another enemy
        f = fights[(fights["round"] == r) & (fights.t >= t0 - 2) & (fights.t <= t1 + 2)]
        fight = bool(len(f[(f.kind != "hurt") & (f.steamid == sid)]) or len(f[(f.kind == "hurt") & ((f.steamid == sid) | (f.other == sid))]))
        you_died = (r, sid) in died and t0 <= died[(r, sid)] <= t1 + 4
        enemy_died = any((r, e) in died and t0 <= died[(r, e)] <= t1 + 4 for e in m["enemies"])
        far = me["q"] > FAR
        talking = any(rr == r and t0 - 1.5 <= tt <= t0 for rr, tt, x in mine_any if not any(c[0] == rr and c[1] == tt for c in calls))
        row.update(fight=fight, you_died=you_died, enemy_died=enemy_died, far=far, talking=talking, q=round(me["q"], 2))
        if calls:
            c = calls[0]
            row.update(called=c[2], react=round(c[1] - t0, 1), right=_right(c[3], m["place"], info))
        else:
            row["called"] = None
            row["why"] = ("fight" if fight else "you_died" if you_died else "enemy_died" if enemy_died else "shared" if mates
                          else "far" if far else "talking" if talking else "none")
        rows.append(row)
    heard_rows = [x for x in rows if x["you"]]
    mine_rows = [x for x in heard_rows if not x["fight"]]   # what you could call: outside your own fights
    called = [x for x in mine_rows if x["called"]]
    split = lambda xs: {"n": len(xs), "called": sum(1 for x in xs if x.get("called"))}
    who = {}
    for m in M:
        for p in m["heard"]:
            if p != sid:
                w = who.setdefault(p, {"name": names.get(p, "?"), "heard": 0, "only": 0})
                w["heard"] += 1
                w["only"] += len(m["heard"]) == 1
    res = {"v": 1, "moments": len(M), "heard": len(heard_rows), "fights": split([x for x in heard_rows if x["fight"]]),
           "callable": len(mine_rows), "called": len(called),
           "react_s": round(float(np.median([x["react"] for x in called])), 1) if called else None,
           "right": sum(1 for x in called if x.get("right") is True),   # the call named the place (else: no place in it)
           "alone": split([x for x in mine_rows if not x["mates"]]), "shared": split([x for x in mine_rows if x["mates"]]),
           "far": split([x for x in mine_rows if x["far"]]), "near": split([x for x in mine_rows if not x["far"]]),
           "by_kind": {k: split([x for x in mine_rows if x["kind"] == k]) for k in KIND_RANK if any(x["kind"] == k for x in mine_rows)},
           "why_not": {k: sum(1 for x in mine_rows if x.get("why") == k) for k in ("you_died", "enemy_died", "shared", "far", "talking", "none")},
           "missed_by_you": sum(1 for x in rows if not x["you"]),
           "mates": sorted(who.values(), key=lambda w: -w["heard"]),
           # the moments you heard, for the page (what it shows of each)
           "list": [{k: x[k] for k in ("round", "t", "place", "n", "kind", "who", "called", "react", "right", "why", "team_called", "fight") if k in x}
                    for x in heard_rows][:160]}
    if team is not None:
        res["team_called"] = sum(1 for x in rows if x.get("team_called"))   # every moment your team could hear (05/10: a KeyError on the ones you didn't)
        res["team_only"] = sum(1 for x in rows if not x["you"] and x.get("team_called"))
    return res


def _centers(P):
    """Mean position of each place of the match (every player's samples there)."""
    g = P[P.zone.notna() & (P.zone != "")].groupby("zone")[["X", "Y", "Z"]].mean()
    return {k: v.to_numpy(float) for k, v in g.iterrows()}


def after_calls(mid, sid, live, team, team_offset=0.0, map_name=None, horizon=8.0):
    """After each call of your team that names a place (your team's sound): where you went in the next `horizon`
    seconds. -> {"calls", "toward", "away", "stayed", "there", "dead", "react_s", "list"}."""
    data = _load(mid)
    if data is None or not live or not team:
        return None
    E, P, died, side, names = data
    sid = int(sid)
    W = _Where(P, died)
    info, humanize = _place_info(map_name)
    centers = _centers(P)
    pos_re = __import__("wily.live.voice", fromlist=["voice"])._pos_re(map_name)
    out = []
    for r, t, text in _phrases(team, live, team_offset):
        c = _call(text, map_name, pos_re)
        if not c:
            continue
        if c["zone"]:
            keys = [k for k, (n, _) in info.items() if n == c["zone"]]
        elif c["site"]:
            keys = [k for k in (f"Bombsite{c['site']}",) if k in centers] or [k for k, (_, g) in info.items() if g == c["site"]]
        else:
            continue
        pts = [centers[k] for k in keys if k in centers]
        if not pts:
            continue
        goal = np.mean(pts, axis=0)
        row = {"round": r, "t": round(t, 1), "text": text, "to": c["zone"] or c["site"]}
        p0, p1 = W.at(r, sid, t), W.at(r, sid, t + horizon)
        if p0 is None:
            continue   # dead: nothing to read
        d0 = float(np.linalg.norm(p0[:2] - goal[:2]))
        if p1 is None:
            row["went"] = "died"
        elif d0 < 500:
            row["went"] = "there"
        else:
            d1 = float(np.linalg.norm(p1[:2] - goal[:2]))
            row["went"] = "toward" if d0 - d1 > 250 else "away" if d1 - d0 > 250 else "stayed"
            if row["went"] == "toward":   # the first half second you head that way faster than 120 u/s
                prev = d0
                for k in np.arange(t + 0.5, t + horizon + 0.01, 0.5):
                    p = W.at(r, sid, float(k))
                    if p is None:
                        break
                    dk = float(np.linalg.norm(p[:2] - goal[:2]))
                    if prev - dk > 60:
                        row["react"] = round(float(k) - 0.5 - t, 1)
                        break
                    prev = dk
        row["d0"] = round(d0)
        out.append(row)
    n = lambda k: sum(1 for x in out if x["went"] == k)
    rs = [x["react"] for x in out if x.get("react") is not None]
    return {"calls": len(out), "toward": n("toward"), "away": n("away"), "stayed": n("stayed"), "there": n("there"), "died": n("died"),
            "react_s": round(float(np.median(rs)), 1) if rs else None, "list": out[:60]}
