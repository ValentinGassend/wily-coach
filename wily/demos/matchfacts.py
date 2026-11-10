"""Facts from a match's demo that the round data doesn't keep, to settle what is felt in game with what happened:

- blocks: a sudden stop (running, then stopped within 1/8 s) against a teammate right in front, within 50 units:
  who blocks you, whom you block (probable: a stop near a teammate can also be a choice);
- flashes: a flash that blinds an enemy for 1 s or more, then who shoots within 2.5 s (a teammate, you, nobody), and
  a teammate hit by an enemy in the 1.5 s before your flash pops (peeked before it); the same for your teammates'
  flashes and you; team flashes (who blinds you, whom you blind);
- odd kills of each enemy: through smoke, through a wall on a player the killer never saw, on a player the killer
  never saw in the 3 s before (a prefire, or more), very fast first hits after first seeing (under 0.15 s), against
  the rest of the lobby; with their Steam bans (Steam's official API, the player's own key, only the steamids).
  Indicators, not proof: a list worth reporting in Overwatch rather than a reason to tilt mid-game.

Usage: python -m wily.demos.matchfacts <steamid> [n_matches]   (the demos of the player's latest matches, cached per match)
Writes out/players/<sid>/facts/<match>.json"""
import datetime as dt
import json
import math
import os
import sys

import numpy as np
import pandas as pd

from wily.core import config

TICK = 64
STEP = 4            # ticks between positions for the blocks (1/16 s)
LOOK = 3 * TICK     # look back 3 s for "saw"
FLASH_MIN = 1.0     # s of blindness for a flash that counts
USE_S = 2.5         # a shot within 2.5 s uses the flash
EARLY_S = 1.5       # hit in the 1.5 s before the flash pops: peeked before it
NADES = ("hegrenade", "inferno", "molotov", "incgrenade", "flashbang", "smokegrenade", "decoy", "knife", "world")


def _sid(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def fdir(sid):
    return os.path.join(config.player_dir(int(sid)), "facts")


def analyze(mid, sid):
    sid = int(sid)
    dem = config.demo(mid)
    d = os.path.join(config.DEEP, str(mid))
    if not (os.path.exists(dem) and os.path.exists(os.path.join(d, "rounds.parquet")) and os.path.exists(os.path.join(d, "samples.parquet"))):
        return None
    from demoparser2 import DemoParser
    p = DemoParser(dem)
    R = pd.read_parquet(os.path.join(d, "rounds.parquet")).sort_values("start_tick")
    S = pd.read_parquet(os.path.join(d, "samples.parquet"), columns=["steamid", "name", "round", "side"]).drop_duplicates(["steamid", "round"])
    side = {(int(r), int(s_)): sd for s_, r, sd in zip(S.steamid, S["round"], S.side)}
    names = dict(zip(S.steamid.astype(int), S.name))
    if not any(k[1] == sid for k in side):
        return None
    starts, ends, rnums = R.start_tick.to_numpy(int), R.end_tick.to_numpy(int), R["round"].to_numpy(int)

    def rnd_of(t):
        i = int(np.searchsorted(starts, t, side="right")) - 1
        return int(rnums[i]) if 0 <= i < len(rnums) and t <= ends[i] + 5 * TICK else None

    def ev(name):
        try:
            x = p.parse_event(name)
        except Exception:
            return pd.DataFrame()
        for c in ("attacker_steamid", "user_steamid"):
            if c in x:
                x[c] = x[c].map(_sid)
        if len(x):
            x["round"] = [rnd_of(int(t)) for t in x.tick]
            x = x[x["round"].notna()]
        return x
    deaths, blind, det, hurt = ev("player_death"), ev("player_blind"), ev("flashbang_detonate"), ev("player_hurt")
    hurt_w = hurt[~hurt.weapon.isin(NADES)] if len(hurt) else hurt
    sd = lambda r, s_: side.get((int(r), int(s_)))
    mates = lambda r: {s_ for (rr, s_), v in side.items() if rr == r and v == sd(r, sid) and s_ != sid}

    # ---------- blocks ----------
    ticks = sorted({t for a, b in zip(starts, ends) for t in range(int(a), int(b), STEP)})
    pos = p.parse_ticks(["X", "Y", "Z", "is_alive"], ticks=ticks)
    pos["steamid"] = pos["steamid"].map(_sid)
    pos = pos[pos.is_alive.astype(bool)]
    by, on = {}, {}
    for (r_i, a, b) in zip(rnums, starts, ends):
        team = mates(int(r_i)) | {sid}
        if len(team) < 2:
            continue
        P = pos[(pos.tick >= a) & (pos.tick < b) & pos.steamid.isin(team)]
        W = {s_: g.set_index("tick")[["X", "Y", "Z"]] for s_, g in P.groupby("steamid")}
        for A in W:
            g = W[A]
            if len(g) < 4:
                continue
            xy = g[["X", "Y"]].to_numpy(float)
            tk = g.index.to_numpy(int)
            v = np.r_[np.nan, np.hypot(*(np.diff(xy, axis=0).T)) * TICK / STEP]
            last = -10 ** 9
            for i in range(3, len(tk)):
                if tk[i] - tk[i - 3] != 3 * STEP or tk[i] - last < 2 * TICK:
                    continue
                if not (np.nanmean(v[i - 2:i]) >= 150 and v[i] <= 60):
                    continue
                dirv = xy[i - 1] - xy[i - 3]
                nd = np.hypot(*dirv)
                if nd < 1:
                    continue
                for B in W:
                    if B == A or tk[i] not in W[B].index:
                        continue
                    q = W[B].loc[tk[i]]
                    rel = np.array([q.X - xy[i][0], q.Y - xy[i][1]])
                    dist = np.hypot(*rel)
                    if dist <= 50 and abs(q.Z - g.loc[tk[i]].Z) < 50 and dist > 0 and float(dirv @ rel) / (nd * dist) >= 0.5:
                        last = tk[i]
                        if A == sid:
                            by[B] = by.get(B, 0) + 1
                        elif B == sid:
                            on[A] = on.get(A, 0) + 1
                        break

    # ---------- flashes ----------
    def flash_rows():
        out = []
        if not len(det) or not len(blind):
            return out
        for x in det.itertuples():
            r, thr, t = int(x.round), int(x.user_steamid), int(x.tick)
            if sd(r, thr) is None:
                continue
            b = blind[(blind.attacker_steamid == thr) & (blind.tick >= t - 16) & (blind.tick <= t + 16)]
            long_ = (b.blind_duration >= FLASH_MIN).to_numpy(bool) if len(b) else None
            en = b[np.array([sd(r, v) not in (None, sd(r, thr)) for v in b.user_steamid], bool) & long_] if len(b) else b
            fr = b[np.array([sd(r, v) == sd(r, thr) and v != thr for v in b.user_steamid], bool) & long_] if len(b) else b
            h = hurt_w[(hurt_w.tick >= t) & (hurt_w.tick <= t + USE_S * TICK)] if len(hurt_w) else hurt_w
            h_team = h[[sd(r, a) == sd(r, thr) and sd(r, v) not in (None, sd(r, thr)) for a, v in zip(h.attacker_steamid, h.user_steamid)]] if len(h) else h
            e = hurt_w[(hurt_w.tick >= t - EARLY_S * TICK) & (hurt_w.tick < t)] if len(hurt_w) else hurt_w
            e = e[[sd(r, v) == sd(r, thr) and v != thr and sd(r, a) not in (None, sd(r, thr)) for a, v in zip(e.attacker_steamid, e.user_steamid)]] if len(e) else e
            out.append({"r": r, "thrower": thr, "enemies": int(len(en)), "mates": [(int(v), float(du)) for v, du in zip(fr.user_steamid, fr.blind_duration)],
                        "shooters": set(int(a) for a in h_team.attacker_steamid), "early": set(int(v) for v in e.user_steamid)})
        return out
    FL = flash_rows()
    mine = [f for f in FL if f["thrower"] == sid and f["enemies"]]
    theirs = [f for f in FL if f["thrower"] != sid and f["enemies"] and sd(f["r"], f["thrower"]) == sd(f["r"], sid)]
    flashes = {"yours": {"n": len(mine), "mate_used": sum(1 for f in mine if f["shooters"] - {sid}),
                         "self_used": sum(1 for f in mine if f["shooters"] == {sid}), "unused": sum(1 for f in mine if not f["shooters"]),
                         "mate_early": sum(1 for f in mine if f["early"])},
               "theirs": {"n": len(theirs), "you_used": sum(1 for f in theirs if sid in f["shooters"]),
                          "you_early": sum(1 for f in theirs if sid in f["early"])}}
    tf_by, tf_on = {}, 0
    for f in FL:
        for v, du in f["mates"]:
            if v == sid and f["thrower"] != sid:
                tf_by[f["thrower"]] = tf_by.get(f["thrower"], 0) + 1
            if f["thrower"] == sid:
                tf_on += 1

    # ---------- odd kills, per enemy ----------
    kills = deaths[(deaths.attacker_steamid != 0) & (deaths.attacker_steamid != deaths.user_steamid)] if len(deaths) else deaths
    first, lastk = [], {}
    for x in (hurt_w.sort_values("tick").itertuples() if len(hurt_w) else []):
        a, v = int(x.attacker_steamid), int(x.user_steamid)
        if not a or a == v or sd(x.round, a) == sd(x.round, v):
            continue
        k = (a, v)
        if k not in lastk or x.tick - lastk[k] > LOOK:
            first.append((int(x.tick), a, v))
        lastk[k] = x.tick
    want = set()
    for t, a, v in first:
        want.update(range(max(t - LOOK, 0), t + 1, 2))
    for t in kills.tick:
        want.update(range(max(int(t) - LOOK, 0), int(t) + 1, 2))
    seen = {}
    if want:
        sp = p.parse_ticks(["approximate_spotted_by"], ticks=sorted(want))
        for t, s_, by_ in zip(sp.tick, sp.steamid.map(_sid), sp.approximate_spotted_by):
            seen[(int(t), s_)] = {_sid(o) for o in (by_ if isinstance(by_, (list, np.ndarray)) else [])}

    def first_seen(obs, tgt, t_end):
        for t in range(max(t_end - LOOK, 0), t_end + 1, 2):   # the same ticks as the ones read
            if obs in seen.get((t, tgt), ()):
                return t
        return None
    E = {}
    def row(s_):
        return E.setdefault(s_, {"steamid": str(s_), "name": names.get(s_, "?"), "kills": 0, "unseen": 0, "wallbang_unseen": 0, "thrusmoke": 0,
                                 "blind": 0, "reacts": []})
    for x in kills.itertuples():
        a, v, t = int(x.attacker_steamid), int(x.user_steamid), int(x.tick)
        if sd(x.round, a) == sd(x.round, v):
            continue
        e = row(a)
        e["kills"] += 1
        saw = first_seen(a, v, t) is not None
        pen = bool(getattr(x, "penetrated", 0))
        if not saw and not pen:
            e["unseen"] += 1
        if not saw and pen:
            e["wallbang_unseen"] += 1
        if bool(getattr(x, "thrusmoke", False)):
            e["thrusmoke"] += 1
        if bool(getattr(x, "attackerblind", False)):
            e["blind"] += 1
    for t, a, v in first:
        ts = first_seen(a, v, t)
        if ts is not None:
            row(a)["reacts"].append((t - ts) / TICK)
    rows = []
    for s_, e in E.items():
        rs = e.pop("reacts")
        e["react_med"] = round(float(np.median(rs)), 2) if len(rs) >= 5 else None
        e["fast"] = round(100 * float(np.mean([r < 0.15 for r in rs]))) if len(rs) >= 5 else None
        e["n_react"] = len(rs)
        e["odd"] = e["unseen"] + e["wallbang_unseen"] + e["thrusmoke"]
        rows.append(e)
    lobby_odd = [e["odd"] / e["kills"] for e in rows if e["kills"] >= 3]
    lobby_fast = [e["fast"] for e in rows if e["fast"] is not None]
    med_odd = float(np.median(lobby_odd)) if lobby_odd else 0.0
    med_fast = float(np.median(lobby_fast)) if lobby_fast else 0.0
    my_side = {r: sd(r, sid) for r in set(rnums.tolist())}
    enemy = set()
    for (r, s_), v in side.items():
        if my_side.get(r) and v and v != my_side[r]:
            enemy.add(s_)
    for e in rows:
        s_ = int(e["steamid"])
        e["enemy"] = s_ in enemy
        share = e["odd"] / e["kills"] if e["kills"] else 0
        e["flag"] = bool(e["enemy"] and e["kills"] >= 4 and ((e["odd"] >= 5 and share >= max(0.4, 2 * med_odd))
                                                            or (e["fast"] is not None and e["n_react"] >= 12 and e["fast"] >= max(35, 2 * med_fast))))
    meta = json.load(open(os.path.join(d, "meta.json"), encoding="utf-8")) if os.path.exists(os.path.join(d, "meta.json")) else {}
    nm = lambda s_: names.get(int(s_), "?")
    res = {"mid": str(mid), "map": meta.get("map"), "rounds": int(len(R)),
           "blocks": {"by": sorted([{"name": nm(k), "n": v} for k, v in by.items()], key=lambda z: -z["n"]), "by_n": sum(by.values()),
                      "on": sorted([{"name": nm(k), "n": v} for k, v in on.items()], key=lambda z: -z["n"]), "on_n": sum(on.values())},
           "flashes": flashes,
           "teamflash": {"by": sorted([{"name": nm(k), "n": v} for k, v in tf_by.items()], key=lambda z: -z["n"]), "by_n": sum(tf_by.values()), "on_n": tf_on},
           "enemies": sorted([e for e in rows if e["enemy"]], key=lambda z: (-z["flag"], -z["odd"])),
           "all": rows,   # every player's row (the player's own too), for a player's own profile
           "lobby": {"odd_share": round(100 * med_odd), "fast": round(med_fast)}}
    os.makedirs(fdir(sid), exist_ok=True)
    json.dump(res, open(os.path.join(fdir(sid), f"{mid}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return res


def bans(steamids):
    """Steam bans of these players: Steam's official API with the player's own key (out/settings.json); only the
    steamids are sent. {steamid: {"vac": n, "game": n, "days": days since the last ban}}."""
    from wily.matches import steamlink
    key = steamlink.api_key()
    ids = sorted({str(s_) for s_ in steamids if s_})
    if not key or not ids:
        return {}
    out = {}
    for i in range(0, len(ids), 100):
        code, j = steamlink._api("ISteamUser/GetPlayerBans/v1/", key=key, steamids=",".join(ids[i:i + 100]))
        for x in (j or {}).get("players", []) if code == 200 else []:
            out[str(x.get("SteamId"))] = {"vac": int(x.get("NumberOfVACBans") or 0), "game": int(x.get("NumberOfGameBans") or 0),
                                          "days": int(x.get("DaysSinceLastBan") or 0)}
    return out


def summary(sid, limit=10):
    """The player's latest matches with facts: blocks and flashes added up, team flashes by teammate, and the flagged
    or banned enemies (with their Steam bans, refreshed)."""
    d = fdir(sid)
    if not os.path.isdir(d):
        return None
    from wily.app import pipeline
    reg = pipeline.registry()
    fs = []
    for f in os.listdir(d):
        if f.endswith(".json"):
            mid = f[:-5]
            fs.append(((reg.get(mid) or {}).get("time") or "", mid))
    fs = sorted(fs, reverse=True)[:limit]
    if not fs:
        return None
    M = [dict(json.load(open(os.path.join(d, mid + ".json"), encoding="utf-8")), time=t) for t, mid in fs]
    add = lambda k, kk: sum(m[k][kk] for m in M)
    fy = {k: sum(m["flashes"]["yours"][k] for m in M) for k in ("n", "mate_used", "self_used", "unused", "mate_early")}
    ft = {k: sum(m["flashes"]["theirs"][k] for m in M) for k in ("n", "you_used", "you_early")}
    by, tf = {}, {}
    for m in M:
        for x in m["blocks"]["by"]:
            by[x["name"]] = by.get(x["name"], 0) + x["n"]
        for x in m["teamflash"]["by"]:
            tf[x["name"]] = tf.get(x["name"], 0) + x["n"]
    sus = [dict(e, mid=m["mid"], map=m["map"], time=m["time"]) for m in M for e in m["enemies"] if e["flag"]]
    try:
        B = bans([e["steamid"] for m in M for e in m["enemies"]])
    except Exception:
        B = {}
    banned = [dict(e, mid=m["mid"], map=m["map"], time=m["time"]) for m in M for e in m["enemies"]
              if (B.get(e["steamid"]) or {}).get("vac") or (B.get(e["steamid"]) or {}).get("game")]
    keyed = {}
    for e in sus + banned:
        k = (e["steamid"], e["mid"])
        b = B.get(e["steamid"]) or {}
        keyed[k] = {"name": e["name"], "steamid": e["steamid"], "mid": e["mid"], "map": e["map"], "time": e["time"], "kills": e["kills"],
                    "unseen": e["unseen"], "wallbang_unseen": e["wallbang_unseen"], "thrusmoke": e["thrusmoke"], "fast": e["fast"],
                    "react_med": e["react_med"], "flag": e["flag"], "vac": b.get("vac", 0), "game": b.get("game", 0), "ban_days": b.get("days"),
                    "ban_after": bool((b.get("vac") or b.get("game")) and e["time"] and b.get("days") is not None
                                      and b["days"] <= (dt.datetime.now() - dt.datetime.fromisoformat(e["time"][:16])).days)}   # banned since this match
    return {"matches": len(M), "rounds": sum(m["rounds"] for m in M),
            "blocks": {"by_n": add("blocks", "by_n"), "on_n": add("blocks", "on_n"),
                       "by": sorted([{"name": k, "n": v} for k, v in by.items()], key=lambda z: -z["n"])[:4]},
            "flashes": {"yours": fy, "theirs": ft},
            "teamflash": {"by_n": add("teamflash", "by_n"), "on_n": add("teamflash", "on_n"),
                          "by": sorted([{"name": k, "n": v} for k, v in tf.items()], key=lambda z: -z["n"])[:4]},
            "suspects": sorted(sorted(keyed.values(), key=lambda z: z["time"] or "", reverse=True), key=lambda z: (-(z["vac"] + z["game"] > 0), -z["flag"]))[:12],
            "bans_checked": bool(B)}


def profile(sid, n=20):
    """A player's own kills over their latest matches against their lobbies: odd kills (unseen, through smoke) and very
    fast first hits, match by match and in total, with the lobby's medians. Indicators, not proof."""
    run(sid, n, only_missing=False)
    d = fdir(sid)
    rows = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        m = json.load(open(os.path.join(d, f), encoding="utf-8"))
        me = next((e for e in m.get("all") or [] if e["steamid"] == str(sid)), None)
        if me:
            rows.append({"mid": m["mid"], "map": m["map"], "kills": me["kills"], "odd": me["odd"], "unseen": me["unseen"], "smoke": me["thrusmoke"],
                         "fast": me["fast"], "n_react": me["n_react"], "react_med": me["react_med"],
                         "lobby_odd": m["lobby"]["odd_share"], "lobby_fast": m["lobby"]["fast"]})
    if not rows:
        return None
    K = sum(r["kills"] for r in rows)
    F = [r for r in rows if r["fast"] is not None]
    nr = sum(r["n_react"] for r in F)
    return {"matches": len(rows), "kills": K, "odd_share": round(100 * sum(r["odd"] for r in rows) / max(K, 1)),
            "lobby_odd": round(sum(r["lobby_odd"] for r in rows) / len(rows)),
            "fast": round(sum(r["fast"] * r["n_react"] for r in F) / max(nr, 1)) if F else None, "n_react": nr,
            "lobby_fast": round(sum(r["lobby_fast"] for r in rows) / len(rows)),
            "react_med": round(float(np.median([r["react_med"] for r in F if r["react_med"] is not None])), 2) if F else None,
            "per_match": rows}


def run(sid, n=10, only_missing=True):
    """The facts of the player's latest n matches with a demo (the ones not done yet)."""
    from wily.app import pipeline
    reg = pipeline.registry()
    ms = sorted(pipeline.player_matches(int(sid)), key=lambda m: (reg.get(m) or {}).get("time") or "", reverse=True)
    done = 0
    for mid in ms:
        if done >= n:
            break
        if not config.has_demo(mid):
            continue
        done += 1
        if only_missing and os.path.exists(os.path.join(fdir(sid), f"{mid}.json")):
            continue
        try:
            r = analyze(mid, sid)
            print(mid, "facts" if r else "skipped", flush=True)
        except Exception as e:
            print(mid, "facts impossible:", e, flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    config.low_priority()
    run(int(sys.argv[1]), int(sys.argv[2]) if len(sys.argv) > 2 else 10)
