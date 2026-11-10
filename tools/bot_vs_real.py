"""The training's bots against real players (29/10, the user: "tu vas record ce que tu proposes sur la gestion des bots, et tu
vas comparer la gestion de tes bots au comportement de vrais joueurs dans de vraies parties ... récupère vraiment le maximum
d'informations sur les vraies parties avec des vrais joueurs pour les comparer avec ce que tu peux enregistrer sur les
entraînements et pousser le plus les entraînements à aller vers ce que font les vrais joueurs"). The same measures on both,
from demos, tick by tick:
- a recorded training session (his game's `record`): its bots of the attacking side (Ts), its live drills;
- real matches of the base on that map (every whole one in Google Drive's own cache, E:\\DriveCache): the Ts from the freeze
  time's end to the plant, near the bombsites the drills attack.
Measured: how they move (speeds, Shift, stops and how long, brakes, starts, jumps, crouching, jerks, how straight, their
distance to a teammate), how they look (head turns, flicks, pitch, off the nearest enemy, off their way, the same angle as a
teammate), how they fight (what they do once an enemy sees them, their speed at their shots, bursts, from seen to a first
shot) and their grenades.

    python tools/bot_vs_real.py [recorded demo] [--real N] [--map de_mirage] [--workers 2]
    ->   out/knowledge/bot_vs_real_<map>.json (bots, real, and each measure side by side)"""
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wily.core import config  # noqa: E402

FLAGS = "CCSPlayerPawn.m_fFlags"
DUCK = "CCSPlayerPawn.CCSPlayer_MovementServices.m_bDucked"
SPOT = "CCSPlayerPawn.m_bSpotted"
WALK = "CCSPlayerPawn.m_bIsWalking"
PROPS = ["X", "Y", "Z", "yaw", "pitch", "team_num", "is_alive", "user_id", FLAGS, DUCK, SPOT, WALK]
SITES = {"de_mirage": [(-340.0, -1600.0), (-1510.0, 330.0)]}   # A, B: the middle of the defense drills' posts
NEAR = 1800.0
RATE = 64
NADES = {"weapon_smokegrenade", "weapon_flashbang", "weapon_hegrenade", "weapon_molotov", "weapon_incgrenade", "weapon_decoy"}
LISTS = ("duck_speed", "turn", "seen_stop", "seen_speed", "restart_s", "look_stopped", "look_moving", "look_vs_way", "stop_s", "duel_rad", "duel_lat",
         "brake_s", "start_s", "straight", "mate_d", "pitch", "shot_v", "burst", "seen_shot_s")
COUNTS = ("ticks", "stop", "walk", "run", "fast", "moving_ticks", "shift", "stops", "jumps", "duck_moving", "duck_still", "jerks",
          "seen", "seen_back", "seen_on", "flicks", "overlap", "overlap_n", "shots", "nades", "smoke", "flash", "he", "molotov")


def windows(p, bots):
    """The live play: for real matches the freeze time's end to the plant (or the round's end); for a training session each
    round from 3 s after its start (its countdown) to its end."""
    ev = dict(p.parse_events(["round_freeze_end", "round_start", "bomb_planted", "round_end"]))
    get = lambda k: sorted(ev[k]["tick"].tolist()) if k in ev and len(ev[k]) else []  # noqa: E731
    starts = [t + 3 * RATE for t in get("round_start")] if bots else get("round_freeze_end")
    ends = sorted(get("round_end") + ([] if bots else get("bomb_planted")))
    spans = []
    for a in starts:
        b = next((e for e in ends if e > a), None)
        spans.append((a, b if b else 10 ** 9))

    def inside(tk):
        m = np.zeros(len(tk), dtype=bool)
        for a, b in spans:
            m |= (tk >= a) & (tk < b)
        return m
    return inside


def botrec(path):
    """A css_botrec file as a demo's ticks and shots (tools' columns): his game's demo holds no bot."""
    rows, shots = [], []
    for ln in open(path, encoding="utf-8"):
        f = ln.strip().split(",")
        if f[0] == "tick":
            continue
        if f[0] == "F":
            shots.append((int(f[1]), int(f[2]), f[3] if f[3].startswith("weapon_") else "weapon_" + f[3]))
            continue
        rows.append(f)
    df = pd.DataFrame(rows, columns=["tick", "user_id", "steamid", "team_num", "X", "Y", "Z", "yaw", "pitch", FLAGS, DUCK, SPOT, WALK])
    for c in ("tick", "user_id", "team_num", FLAGS):
        df[c] = df[c].astype("int64")
    for c in ("X", "Y", "Z", "yaw", "pitch"):
        df[c] = df[c].astype(float)
    for c in (DUCK, SPOT, WALK):
        df[c] = df[c] == "1"
    df["steamid"] = pd.to_numeric(df["steamid"], errors="coerce").fillna(0)
    df["is_alive"] = True
    return df, pd.DataFrame(shots, columns=["tick", "user_user_id", "weapon"])


def empty():
    return {**{k: [] for k in LISTS}, **{k: 0 for k in COUNTS}, "moving_s": 0.0}


def wrap(a):
    return np.abs(((a + 540.0) % 360.0) - 180.0)


def one(path, mp, bots):
    """Its accumulators for one demo (Ts: the bots of a training session, or a real match's players)."""
    s = empty()
    if path.lower().endswith(".csv"):   # the plugin's own record of a training session (css_botrec): its live drills only
        df, fire = botrec(path)
        inside = lambda tk: np.ones(len(tk), dtype=bool)  # noqa: E731
    else:
        from demoparser2 import DemoParser
        p = DemoParser(path)
        df = p.parse_ticks(PROPS)
        inside = windows(p, bots)
        fire = dict(p.parse_events(["weapon_fire"], player=["user_id"])).get("weapon_fire")   # its shooter's id with it
    df = df[df["is_alive"] == True]   # noqa: E712
    df = df[inside(df["tick"].to_numpy())]
    sid = pd.to_numeric(df["steamid"], errors="coerce").fillna(0)
    ts = df[(df["team_num"] == 2) & ((sid == 0) if bots else (sid != 0))]
    # 8 times a second: the nearest enemy (where it should look) and the nearest teammate (its spacing, its angle)
    en = df[(df["team_num"] == 3) & (df["tick"] % 8 == 0)][["tick", "X", "Y"]].rename(columns={"X": "ex", "Y": "ey"})
    mates = ts[ts["tick"] % 8 == 0][["tick", "user_id", "X", "Y", "yaw"]].rename(columns={"user_id": "mu", "X": "mx", "Y": "my", "yaw": "myaw"})
    sites = SITES.get(mp, [])
    for uid, g in ts.groupby("user_id"):
        g = g.sort_values("tick").reset_index(drop=True)
        if len(g) < RATE:
            continue
        x, y, z = g["X"].to_numpy(float), g["Y"].to_numpy(float), g["Z"].to_numpy(float)
        tk = g["tick"].to_numpy()
        yaw, pitch = g["yaw"].to_numpy(float), g["pitch"].to_numpy(float)
        near = np.zeros(len(x), dtype=bool)
        for cx, cy in sites:
            near |= np.hypot(x - cx, y - cy) < NEAR
        dt = np.diff(tk) / RATE
        ok = (dt > 0) & (dt < 0.1)
        v = np.zeros(len(x))
        step = np.hypot(np.diff(x), np.diff(y))
        v[1:][ok] = step[ok] / dt[ok]
        put = np.r_[False, v[1:] > 600]   # a spawn or a placement of the drill: no motion
        vs = pd.Series(np.where(put, 0, v)).rolling(max(1, int(0.1 * RATE)), min_periods=1).mean().to_numpy()
        ground = (g[FLAGS].fillna(0).astype("int64").to_numpy() & 1) == 1
        duck = g[DUCK].astype(bool).to_numpy()
        spot = g[SPOT].astype(bool).to_numpy()
        shift = g[WALK].astype(bool).to_numpy()
        m = near & np.r_[False, ok] & ~put
        s["ticks"] += int(m.sum())
        s["stop"] += int((m & (vs < 10)).sum()); s["walk"] += int((m & (vs >= 10) & (vs < 135)).sum())
        s["run"] += int((m & (vs >= 135) & (vs <= 260)).sum()); s["fast"] += int((m & (vs > 260) & ground).sum())
        moving = m & (vs > 30)
        s["moving_ticks"] += int(moving.sum()); s["moving_s"] += float(moving.sum()) / RATE
        s["shift"] += int((moving & shift).sum())
        s["duck_still"] += int((m & duck & (vs < 10)).sum())
        # stops (over 100 u/s, then under 20) and how long they stand; brakes (200 to 30) and starts (20 to 200)
        st, since, brake_at, start_at = False, -1, -1, -1
        for j in np.nonzero(m)[0]:
            if vs[j] > 200:
                if start_at >= 0:
                    s["start_s"].append((j - start_at) / RATE); start_at = -1
                brake_at = j
            if vs[j] < 30 and brake_at >= 0:
                if j - brake_at < RATE:
                    s["brake_s"].append((j - brake_at) / RATE)
                brake_at = -1
            if vs[j] > 100:
                if st and since >= 0:
                    s["stop_s"].append((j - since) / RATE)
                st, since = False, -1
            elif vs[j] < 20:
                if not st and vs[max(0, j - int(0.4 * RATE)):j].max(initial=0) > 100:
                    s["stops"] += 1; st, since = True, j
                start_at = j
        # jumps: off the ground, up 12 u or more within 0.3 s (a drop goes down)
        for j in np.nonzero(m[1:] & ground[:-1] & ~ground[1:])[0] + 1:
            if z[j:j + int(0.3 * RATE)].max(initial=z[j]) - z[j - 1] > 12:
                s["jumps"] += 1
        dm = m & duck & (vs > 30) & ground
        s["duck_moving"] += int(dm.sum()); s["duck_speed"] += vs[dm][::4].tolist()
        dy = wrap(np.diff(yaw))
        s["turn"] += (dy[ok] / dt[ok])[m[1:][ok]][::4].tolist()
        q = int(0.25 * RATE)
        if len(yaw) > q:
            fl = (wrap(yaw[q:] - yaw[:-q]) > 90) & m[q:]
            s["flicks"] += int((fl & ~np.r_[False, fl[:-1]]).sum())
        s["pitch"] += pitch[m][::16].tolist()
        # jerks: its speed up then down again by 60 u/s or more while it moves
        up, ext = None, None
        for j in np.nonzero(moving)[0]:
            val = vs[j]
            if ext is None:
                ext = val; continue
            if up is None:
                if abs(val - ext) >= 60:
                    up, ext = val > ext, val
                continue
            if (up and val > ext) or (not up and val < ext):
                ext = val
            elif abs(val - ext) >= 60:
                s["jerks"] += 1; up, ext = not up, val
        # how straight: over 2 s moving, how far it got against the way it walked
        w = 2 * RATE
        cum = np.r_[0.0, np.cumsum(np.where(ok & ~put[1:], step, 0.0))]
        for j in range(0, len(x) - w, w):
            if moving[j:j + w].mean() > 0.8 and cum[j + w] - cum[j] > 100:
                s["straight"].append(float(np.hypot(x[j + w] - x[j], y[j + w] - y[j]) / (cum[j + w] - cum[j])))
        # 8 times a second: off the nearest enemy, its nearest teammate and the same angle as one near
        near_en = {}
        k8 = (tk % 8 == 0) & m
        e8 = pd.DataFrame({"tick": tk[k8], "x": x[k8], "y": y[k8], "yaw": yaw[k8], "vs": vs[k8]})
        if len(e8):
            en_m = e8.merge(en, on="tick")
            if len(en_m):
                en_m["d"] = np.hypot(en_m["ex"] - en_m["x"], en_m["ey"] - en_m["y"])
                en_m = en_m.loc[en_m.groupby("tick")["d"].idxmin()]
                en_m = en_m[en_m["d"] < 2000]
                near_en = dict(zip(en_m["tick"].tolist(), zip(en_m["ex"].tolist(), en_m["ey"].tolist())))
                off = wrap(en_m["yaw"].to_numpy() - np.degrees(np.arctan2(en_m["ey"] - en_m["y"], en_m["ex"] - en_m["x"])))
                s["look_stopped"] += off[en_m["vs"].to_numpy() < 20].tolist()
                s["look_moving"] += off[en_m["vs"].to_numpy() >= 100].tolist()
            mm = e8.merge(mates[mates["mu"] != uid], on="tick")
            if len(mm):
                mm["d"] = np.hypot(mm["mx"] - mm["x"], mm["my"] - mm["y"])
                s["mate_d"] += mm.groupby("tick")["d"].min().tolist()
                close = mm[mm["d"] < 900]
                if len(close):
                    same = close.assign(same=wrap(close["yaw"] - close["myaw"]) < 25).groupby("tick")["same"].any()
                    s["overlap"] += int(same.sum()); s["overlap_n"] += int(len(same))
        # off its way, running
        if len(x) > q:
            mvdir = np.degrees(np.arctan2(y[q:] - y[:-q], x[q:] - x[:-q]))
            run = (m & (vs >= 135))[q:]
            s["look_vs_way"] += wrap(yaw[q:] - mvdir)[run][::8].tolist()
        # its shots: its speed then, its bursts; its grenades
        mine = fire[fire["user_user_id"] == uid] if fire is not None and len(fire) else pd.DataFrame(columns=["tick", "weapon"])
        guns = np.sort(mine[~mine["weapon"].isin(NADES | {"weapon_knife", "weapon_c4"})]["tick"].to_numpy())
        for t_ in guns:
            j = int(np.searchsorted(tk, t_))
            if 0 < j < len(tk) and m[j]:
                s["shots"] += 1; s["shot_v"].append(float(vs[j]))
        if len(guns):
            b, last = 1, guns[0]
            for t_ in guns[1:]:
                if t_ - last <= 0.15 * RATE:
                    b += 1
                else:
                    s["burst"].append(b); b = 1
                last = t_
            s["burst"].append(b)
        for t_, w_ in zip(mine[mine["weapon"].isin(NADES)]["tick"].tolist(), mine[mine["weapon"].isin(NADES)]["weapon"].tolist()):
            j = int(np.searchsorted(tk, t_))
            if 0 < j < len(tk) and m[j]:
                s["nades"] += 1
                s[{"weapon_smokegrenade": "smoke", "weapon_flashbang": "flash", "weapon_hegrenade": "he"}.get(w_, "molotov")] += 1
        # seen by an enemy (its spotted flag on): its next second and a half, and its first shot after
        for j in np.nonzero(m[1:] & spot[1:] & ~spot[:-1])[0] + 1:
            e = min(len(x), j + int(1.5 * RATE))
            if e - j < RATE:
                continue
            s["seen"] += 1
            seg = vs[j:e]
            s["seen_stop"].append(float((seg < 20).mean())); s["seen_speed"].append(float(seg.mean()))
            d0 = np.array([x[j] - x[max(0, j - int(0.5 * RATE))], y[j] - y[max(0, j - int(0.5 * RATE))]])
            d1 = np.array([x[e - 1] - x[j], y[e - 1] - y[j]])
            if np.linalg.norm(d0) > 20 and np.linalg.norm(d1) > 20:
                s["seen_back" if d0 @ d1 < 0 else "seen_on"] += 1
            sl = np.nonzero(seg < 20)[0]
            if len(sl):
                go = np.nonzero(vs[j + sl[0]:] > 100)[0]
                if len(go):
                    s["restart_s"].append(float(go[0]) / RATE)
            # its moves in the duel against the nearest enemy: toward him (+), away (-), across
            for k in range(j, e, 8):
                en_k = near_en.get(int(tk[k]))
                if en_k is None or k < 4 or k + 4 >= len(x):
                    continue
                dvec = np.array([en_k[0] - x[k], en_k[1] - y[k]]); dn = np.linalg.norm(dvec)
                if dn < 1:
                    continue
                dvec /= dn
                vv = np.array([x[k + 4] - x[k - 4], y[k + 4] - y[k - 4]]) * RATE / 8
                rad = float(vv @ dvec)
                s["duel_rad"].append(rad); s["duel_lat"].append(float(np.linalg.norm(vv - rad * dvec)))
            nxt = guns[(guns >= tk[j]) & (guns < tk[j] + 3 * RATE)]
            if len(nxt):
                s["seen_shot_s"].append(float(nxt[0] - tk[j]) / RATE)
    return s


def merge(a, b):
    for k in LISTS:
        a[k] += b[k]
    for k in COUNTS:
        a[k] += b[k]
    a["moving_s"] += b["moving_s"]
    return a


def duel_shares(s):
    r, l = np.array(s["duel_rad"]), np.array(s["duel_lat"])
    if not len(r):
        return None
    sp = np.hypot(r, l)
    still = sp < 30
    across = ~still & (l >= np.abs(r))
    back = ~still & ~across & (r < 0)
    toward = ~still & ~across & (r >= 0)
    return [round(100 * float(a.mean()), 1) for a in (still, across, back, toward)]


def report(s):
    n = max(1, s["ticks"])
    mv = max(1.0, s["moving_s"])
    q = lambda k, p: round(float(np.percentile(s[k], p)), 2) if len(s[k]) else None  # noqa: E731
    pct = lambda a, b: round(100 * a / max(1, b), 1)  # noqa: E731
    mean_pct = lambda k, f: round(100 * float(np.mean(f(np.array(s[k])))), 1) if s[k] else None  # noqa: E731
    return {
        "seconds": round(n / RATE),
        "move: stopped / walking / running %": [pct(s["stop"], n), pct(s["walk"], n), pct(s["run"], n)],
        "move: faster than a player %": round(100 * s["fast"] / n, 2),
        "move: Shift-walking, of moving %": pct(s["shift"], s["moving_ticks"]),
        "move: stops a minute moving": round(60 * s["stops"] / mv, 1),
        "move: stood still s p50/p90": [q("stop_s", 50), q("stop_s", 90)],
        "move: brake 200->30 u/s s p50": q("brake_s", 50),
        "move: start 20->200 u/s s p50": q("start_s", 50),
        "move: jumps a minute moving": round(60 * s["jumps"] / mv, 1),
        "move: crouched moving % / its speed p50": [pct(s["duck_moving"], s["moving_ticks"]), q("duck_speed", 50)],
        "move: crouched stopped, of stopped %": pct(s["duck_still"], s["stop"]),
        "move: speed jerks a minute moving": round(60 * s["jerks"] / 2 / mv, 1),
        "move: straight over 2 s p50 (1 = a line)": q("straight", 50),
        "move: nearest teammate u p50": q("mate_d", 50),
        "look: head turn deg/s p50/p90/p99": [q("turn", 50), q("turn", 90), q("turn", 99)],
        "look: flicks over 90 deg a minute": round(60 * s["flicks"] / max(1, n / RATE), 1),
        "look: pitch p10/p50/p90": [q("pitch", 10), q("pitch", 50), q("pitch", 90)],
        "look: stopped, off the nearest enemy deg p50/p90": [q("look_stopped", 50), q("look_stopped", 90)],
        "look: stopped, over 90 deg off him %": mean_pct("look_stopped", lambda a: a > 90),
        "look: moving, off the nearest enemy deg p50": q("look_moving", 50),
        "look: running, off its way deg p50/p90": [q("look_vs_way", 50), q("look_vs_way", 90)],
        "look: the same angle as a teammate near %": pct(s["overlap"], s["overlap_n"]),
        "fight: seen by an enemy": s["seen"],
        "fight: then stopped % of 1.5 s / its speed": [mean_pct("seen_stop", lambda a: a),
                                                        round(float(np.mean(s["seen_speed"])), 1) if s["seen_speed"] else None],
        "fight: then back / on": [s["seen_back"], s["seen_on"]],
        "fight: stood before going again s p50/p90": [q("restart_s", 50), q("restart_s", 90)],
        "fight: from seen to a first shot s p50": q("seen_shot_s", 50),
        "fight: shots stopped (under 40 u/s) %": mean_pct("shot_v", lambda a: a < 40),
        "fight: speed at a shot p50/p90": [q("shot_v", 50), q("shot_v", 90)],
        "fight: shots a burst p50/p90": [q("burst", 50), q("burst", 90)],
        "duel: still / across / back / toward % (1.5 s after seen)": duel_shares(s),
        "duel: speed across / along p50": [q("duel_lat", 50), q("duel_rad", 50)],
        "nades: a minute": round(60 * s["nades"] / max(1, n / RATE), 2),
        "nades: smoke / flash / he / molotov": [s["smoke"], s["flash"], s["he"], s["molotov"]],
    }


def real_demos(mp, n):
    fn = os.path.join(config.OUT, "knowledge", "behavior", f"{mp}.json")
    names = json.load(open(fn, encoding="utf-8")).get("demos", [])
    want = {tuple(x.split("/")) for x in names}
    got = []
    for dp, _, fs in os.walk(r"E:\DriveCache"):
        for f in fs:
            p = os.path.join(dp, f)
            if tuple(os.path.normpath(p).split(os.sep)[-3:]) in want:
                got.append(p)
    got.sort(key=lambda p: -os.path.getsize(p))
    return got[:n]


def _job(a):
    path, mp = a
    import warnings
    warnings.filterwarnings("ignore")
    try:
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception:
        pass
    try:
        return path, one(path, mp, False), None
    except Exception as e:
        return path, None, str(e)[:120]


def main():
    import warnings
    warnings.filterwarnings("ignore")
    args = [a for i, a in enumerate(sys.argv[1:], 1) if not a.startswith("--") and not sys.argv[i - 1].startswith("--")]
    mp = sys.argv[sys.argv.index("--map") + 1] if "--map" in sys.argv else "de_mirage"
    nreal = int(sys.argv[sys.argv.index("--real") + 1]) if "--real" in sys.argv else 1000
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 2
    out = os.path.join(config.OUT, "knowledge", f"bot_vs_real_{mp}.json")
    res = config.read_json(out, {}) or {}
    if args:
        res["bots"] = report(one(args[0], mp, True))
        res["bots_demo"] = os.path.basename(args[0])
        print("bots:", json.dumps(res["bots"], ensure_ascii=False), flush=True)
    if nreal > 0:
        acc, nd = empty(), 0
        with ProcessPoolExecutor(workers) as ex:
            for path, s, err in ex.map(_job, [(p, mp) for p in real_demos(mp, nreal)]):
                if s is None:
                    print("skipped", os.path.basename(path), err, flush=True)
                    continue
                merge(acc, s); nd += 1
                if nd % 10 == 0:
                    print(nd, "demos read", flush=True)
        res["real"] = report(acc)
        res["real_demos"] = nd
        print("real:", json.dumps(res["real"], ensure_ascii=False), flush=True)
    if "bots" in res and "real" in res:
        res["side_by_side"] = {k: {"bots": res["bots"].get(k), "real": res["real"].get(k)} for k in res["real"]}
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("->", out)


if __name__ == "__main__":
    main()
