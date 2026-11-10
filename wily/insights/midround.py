"""Mid-round movement and decisions, for every player of every demo (and pro demos):
rotations (reaction to a site hit, travel time, route, deaths on the way), anchoring, lurking, post-plant,
retakes, man-advantage thrown, saves in lost rounds, noise near enemies; pulled by a fake (CT: set up on the site
that gets hit and gone from it when the Ts arrive) and the re-peek after a kill (dead within 8 s of your first kill
of the round), with their rounds per match (fake_rounds, repeek_rounds) for the match page.

Needs deep.py's samples/duels (+ rounds.py's rounds/loadout/steps for matchmaking demos).
Writes out/population/midround/<match>.parquet (one row per player) and .../routes/<match>.parquet (one row per rotation).
Usage: python -m wily.insights.midround             # every demo (matchmaking + pro)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

from wily.core import config
from wily.core import ledger
from wily.core.i18n import N_

OUT = os.path.join(config.OUT, "population", "midround")
OUT_R = os.path.join(config.OUT, "population", "routes")
OUT_PRO = os.path.join(config.OUT, "population", "midround_pro")
OUT_PRO_R = os.path.join(config.OUT, "population", "routes_pro")
SITES = os.path.join(config.OUT, "population", "sites.json")
DEEP_PRO = os.path.join(config.OUT, "deep_pro")
HEAR = 1100          # running footsteps are heard up to ~1100 units
ALONE = 1200         # no teammate within this distance = isolated
ROUND_TIME = 115.0
BOMB_TIME = 40.0
ZW = 1.5             # height weight in distances (stacked sites: Nuke, Vertigo)
SETUP_T = 25.0       # a CT's setup: where he stands 25 s into the round (8 s before the hit at most)
PULLED = 600         # left the site by that much when the Ts hit it: pulled away
REPEEK_S = 8.0       # dead this soon after your first kill of the round: the advantage given back


def _meta(ddir):
    try:
        return json.load(open(os.path.join(ddir, "meta.json"), encoding="utf-8"))
    except Exception:
        return {}


def site_centers(rebuild=False):
    """Bomb site centers and radius per map, learned from every sample standing in BombsiteA/B."""
    if os.path.exists(SITES) and not rebuild:
        return json.load(open(SITES, encoding="utf-8"))
    acc = {}
    for base in (config.DEEP, DEEP_PRO):
        if not os.path.exists(base):
            continue
        for mid in os.listdir(base):
            d = os.path.join(base, mid)
            m = _meta(d).get("map")
            f = os.path.join(d, "samples.parquet")
            if not m or m.startswith("cs_") or not os.path.exists(f) or len(acc.get(m, {}).get("A", [])) > 40000:
                continue
            s = pd.read_parquet(f, columns=["X", "Y", "Z", "zone"])
            for L in ("A", "B"):
                pts = s[s.zone == f"Bombsite{L}"][["X", "Y", "Z"]].to_numpy()
                if len(pts):
                    acc.setdefault(m, {}).setdefault(L, []).extend(pts[::3].tolist())
    out = {}
    for m, v in acc.items():
        if len(v.get("A", [])) < 50 or len(v.get("B", [])) < 50:
            continue
        out[m] = {}
        for L in ("A", "B"):
            P = np.array(v[L])
            c = np.median(P, axis=0)
            d = np.sqrt(((P[:, :2] - c[:2]) ** 2).sum(1) + ((P[:, 2] - c[2]) * ZW) ** 2)
            out[m][L] = {"c": [float(x) for x in c], "r": float(np.percentile(d, 85)) + 150}
    os.makedirs(os.path.dirname(SITES), exist_ok=True)
    json.dump(out, open(SITES, "w", encoding="utf-8"))
    return out


def _dist(X, Y, Z, c):
    return np.sqrt((X - c[0]) ** 2 + (Y - c[1]) ** 2 + ((Z - c[2]) * ZW) ** 2)


def _route(zones, limit=5):
    out = []
    for z in zones:
        if z and z != "?" and (not out or out[-1] != z):
            out.append(z)
    # drop one-sample flickers between two identical names (A B A -> A)
    clean = []
    for z in out:
        if len(clean) >= 2 and clean[-2] == z:
            clean.pop()
            continue
        clean.append(z)
    return clean[:limit]


def analyze(ddir, pro=False):
    """-> (players DataFrame, rotations DataFrame) for one demo."""
    meta = _meta(ddir)
    mname = meta.get("map")
    sites = site_centers().get(mname)
    S = pd.read_parquet(os.path.join(ddir, "samples.parquet"))
    D = pd.read_parquet(os.path.join(ddir, "duels.parquet")) if os.path.exists(os.path.join(ddir, "duels.parquet")) else pd.DataFrame()
    has_r = os.path.exists(os.path.join(ddir, "rounds.parquet"))
    R = pd.read_parquet(os.path.join(ddir, "rounds.parquet")).set_index("round") if has_r else None
    L = pd.read_parquet(os.path.join(ddir, "loadout.parquet")) if has_r else None
    ST = pd.read_parquet(os.path.join(ddir, "steps.parquet")) if has_r and os.path.exists(os.path.join(ddir, "steps.parquet")) else None
    S = S[S.steamid != 0]
    names = S.drop_duplicates("steamid").set_index("steamid")["name"].to_dict()
    acc = {s: {"steamid": s, "name": names.get(s), "map": mname, "rounds": 0} for s in names}

    def add(s, k, v=1.0):
        if s in acc:
            acc[s][k] = acc[s].get(k, 0.0) + v

    def note(s, k, rnd):   # the rounds behind a count, for the match page
        if s in acc:
            acc[s].setdefault(k, []).append(rnd)

    wcls = {}
    if L is not None and len(L):
        wcls = {(int(r), int(s)): w for r, s, w in zip(L["round"], L.steamid, L.wclass)}
        equip = {(int(r), int(s)): e for r, s, e in zip(L["round"], L.steamid, L.equip)}
    else:
        equip = {}
    rot_rows = []
    for rnd, g in S.groupby("round"):
        rnd = int(rnd)
        g = g.sort_values("t")
        players = g.drop_duplicates("steamid").set_index("steamid")["side"].to_dict()
        for s in players:
            add(s, "rounds")
        kd = D[D["round"] == rnd].sort_values("tick") if len(D) else D
        death_t = {int(v): float(t) for v, t in zip(kd.victim, kd.t)} if len(kd) else {}
        last_t = g.groupby("steamid").t.max().to_dict()
        rinfo = R.loc[rnd] if R is not None and rnd in R.index else None
        end_t = float(rinfo.end_t) if rinfo is not None and pd.notna(rinfo.end_t) else float(g.t.max())
        winner = rinfo.winner if rinfo is not None else None
        plant_t = float(rinfo.plant_t) if rinfo is not None and pd.notna(rinfo.get("plant_t")) else None
        plant_site = rinfo.plant_site if rinfo is not None and plant_t is not None else None
        times = np.sort(g.t.unique())
        pos = {s: gg for s, gg in g.groupby("steamid")}

        # ---------- man advantage and lost causes (need only deaths) ----------
        alive = {"T": sum(1 for v in players.values() if v == "T"), "CT": sum(1 for v in players.values() if v == "CT")}
        adv_seen = set()
        for _, k in kd.iterrows():
            v, vs = int(k.victim), k.victim_side
            if vs not in alive:
                continue
            mine, theirs = alive[vs], alive["CT" if vs == "T" else "T"]
            if mine > theirs and not k.traded:
                add(v, "adv_throw")
            alive[vs] -= 1
            for s, sd in players.items():  # rounds where a player (alive) saw his team ahead
                if s not in adv_seen and sd in alive and death_t.get(s, 1e9) > k.t and alive[sd] > alive["CT" if sd == "T" else "T"]:
                    adv_seen.add(s)
            # last alive vs 3+: a round usually lost
            if alive[vs] == 1:
                last = [s for s, sd in players.items() if sd == vs and death_t.get(s, 1e9) > k.t]
                enemies = alive["CT" if vs == "T" else "T"]
                if last and enemies >= 3:
                    s = last[0]
                    left = (BOMB_TIME - (k.t - plant_t)) if (vs == "CT" and plant_t is not None and k.t >= plant_t) else \
                        (ROUND_TIME - k.t if vs == "T" and plant_t is None else None)
                    if left is not None and left <= 30:
                        add(s, "lost_n")
                        if s in death_t:
                            add(s, "lost_died")
                            if equip.get((rnd, s), 0) >= 3000:
                                add(s, "lost_died_rich")
                        elif winner == vs:
                            add(s, "lost_won")
                        else:
                            add(s, "lost_saved")
        for s in adv_seen:
            add(s, "adv_rounds")
            if winner and players.get(s) == winner:
                add(s, "adv_won")

        # ---------- after your first kill: dead within 8 s (the advantage given back) ----------
        if len(kd):
            ek = kd[kd.killer_side != kd.victim_side]
            first_kill = ek.drop_duplicates("killer").set_index("killer").t.to_dict()
            for k_, tk in first_kill.items():
                k_ = int(k_)
                add(k_, "kill_rounds")
                td = death_t.get(k_)
                if td is not None and 0 < td - float(tk) <= REPEEK_S:
                    add(k_, "repeek")
                    note(k_, "repeek_rounds", rnd)

        # ---------- isolated early deaths ----------
        for _, k in kd.iterrows():
            v = int(k.victim)
            if k.get("victim_mate_dist") is not None and pd.notna(k.get("victim_mate_dist")) and k.victim_mate_dist > ALONE \
                    and not k.traded and (k.victim_mates_alive or 0) >= 2:
                add(v, "isolated_deaths")

        if not sites or plant_site not in (None, "A", "B"):
            continue
        # ---------- which site gets hit, and when ----------
        T_ = g[g.side == "T"]
        dA = _dist(T_.X.values, T_.Y.values, T_.Z.values, sites["A"]["c"])
        dB = _dist(T_.X.values, T_.Y.values, T_.Z.values, sites["B"]["c"])
        inA = T_.t.values[dA <= sites["A"]["r"] * 1.3]
        inB = T_.t.values[dB <= sites["B"]["r"] * 1.3]

        def first_two(ts):
            u, c = np.unique(ts, return_counts=True)
            ok = u[c >= 2]
            return float(ok[0]) if len(ok) else None
        hit = None
        if plant_site:
            ts = inA if plant_site == "A" else inB
            ft = first_two(ts[(ts >= plant_t - 25) & (ts <= plant_t)])
            hit = (plant_site, ft if ft is not None else max(plant_t - 3, 0))
        else:
            fa, fb = first_two(inA), first_two(inB)
            cand = [(x, L_) for x, L_ in ((fa, "A"), (fb, "B")) if x is not None]
            if cand:
                t0, L_ = min(cand)
                hit = (L_, t0)
        if not hit:
            continue
        site, hit_t = hit
        other = "B" if site == "A" else "A"
        cS, rS = sites[site]["c"], sites[site]["r"] * 1.3
        cO, rO = sites[other]["c"], sites[other]["r"] * 2.0
        for s, side in players.items():
            gg = pos.get(s)
            if gg is None:
                continue
            dt = death_t.get(s, last_t.get(s, end_t) + 0.5)
            if dt < hit_t:
                continue
            before = gg[gg.t <= hit_t]
            if not len(before):
                continue
            p0 = before.iloc[-1]
            d0S = float(_dist(p0.X, p0.Y, p0.Z, cS))
            d0O = float(_dist(p0.X, p0.Y, p0.Z, cO))
            region = "site" if d0S <= rS else ("other" if d0O <= rO and d0O < d0S else "mid")
            t_set = min(SETUP_T, hit_t - 8.0)
            if side == "CT" and t_set >= 12:   # set up on the site that got hit: still there when the Ts came?
                st0 = gg[gg.t <= t_set]
                if len(st0):
                    q = st0.iloc[-1]
                    dset = float(_dist(q.X, q.Y, q.Z, cS))
                    if dset <= rS:
                        add(s, "fake_n")
                        if region != "site" and d0S - dset >= PULLED:
                            add(s, "fake_pulled")
                            note(s, "fake_rounds", rnd)
            if side == "CT":
                if region == "site":
                    add(s, "anchor_n")
                    surv = dt - hit_t
                    add(s, "anchor_hold5", float(surv >= 5))
                    kills_after = kd[(kd.killer == s) & (kd.t >= hit_t - 1)]
                    add(s, "anchor_kills", float(len(kills_after)))
                    continue
                # a CT away from the hit site: did he rotate, how fast, by which route, did he make it
                if hit_t < 20 or (region == "mid" and d0S <= rS * 2.5):
                    continue  # rush before setups are done, or a mid player already next to the site
                w = gg[(gg.t >= max(hit_t - 10, 15)) & (gg.t <= min(dt, end_t))]
                if len(w) < 3:
                    continue
                d = _dist(w.X.values, w.Y.values, w.Z.values, cS)
                tt = w.t.values
                i0 = 0
                dstart = d[i0]
                need = max(700.0, 0.35 * (dstart - rS))
                moved = dstart - d.min() >= need
                add(s, "rot_needed")
                if not moved:
                    add(s, "rot_stayed")
                    continue
                j = int(np.argmax(d <= dstart - 250)) if (d <= dstart - 250).any() else None
                t_start = float(tt[j]) if j is not None else float(tt[0])
                arr = np.where((d <= rS) & (tt >= t_start))[0]
                t_arr = float(tt[arr[0]]) if len(arr) else None
                died_way = t_arr is None and dt <= end_t and s in death_t
                route = _route(w.zone.values[j if j is not None else 0: (arr[0] + 1) if len(arr) else len(w)])
                react = t_start - hit_t
                add(s, "rot_done")
                add(s, "rot_early", float(react < -3 and region == "other"))
                if react >= -3:
                    add(s, "rot_react_sum", max(react, 0.0))
                    add(s, "rot_react_n")
                if t_arr is not None:
                    add(s, "rot_arrived")
                    add(s, "rot_travel_sum", t_arr - t_start)
                    add(s, "rot_travel_n")
                    if plant_t is not None and t_arr <= plant_t:
                        add(s, "rot_before_plant")
                if died_way:
                    add(s, "rot_died_way")
                rot_rows.append({"map": mname, "round": rnd, "steamid": s, "name": names.get(s), "from": region, "to": site,
                                 "start_zone": p0.zone, "hit_t": round(hit_t, 1), "react": round(react, 1),
                                 "travel": None if t_arr is None else round(t_arr - t_start, 1), "arrived": t_arr is not None,
                                 "died_way": bool(died_way), "route": " > ".join(route), "wclass": wcls.get((rnd, s)),
                                 "planted": plant_t is not None, "won": winner == "CT" if winner else None})
            else:  # T
                gt = g[(g.side == "T") & (g.t == p0.t) & (g.steamid != s)]
                near = np.sqrt((gt.X - p0.X) ** 2 + (gt.Y - p0.Y) ** 2).min() if len(gt) else 9e9
                lurk = region != "site" and d0S > rS * 2 and near > ALONE
                if lurk:
                    add(s, "lurk_n")
                    lk = kd[(kd.killer == s) & (kd.t >= hit_t - 5)]
                    add(s, "lurk_kills", float(len(lk)))
                    add(s, "lurk_died", float(s in death_t and death_t[s] <= end_t))
                elif region != "site":
                    w = gg[(gg.t >= hit_t) & (gg.t <= dt)]
                    d = _dist(w.X.values, w.Y.values, w.Z.values, cS)
                    arr = np.where(d <= rS)[0]
                    add(s, "t_follow_n")
                    if len(arr) and w.t.values[arr[0]] - hit_t > 10:
                        add(s, "t_late")

        # ---------- after the plant ----------
        if plant_t is not None:
            for s, side in players.items():
                dt = death_t.get(s, 1e9)
                if dt <= plant_t:
                    continue
                if side == "T":
                    add(s, "pp_n")
                    add(s, "pp_survived", float(dt > end_t))
                    add(s, "pp_kills", float(len(kd[(kd.killer == s) & (kd.t > plant_t)])))
                    add(s, "pp_won", float(winner == "T"))
                else:
                    add(s, "rt_n")
                    add(s, "rt_won", float(winner == "CT"))
                    if s in death_t:
                        k = kd[kd.victim == s]
                        if len(k):
                            k = k.iloc[0]
                            md = k.get("victim_mate_dist")
                            if (k.victim_mates_alive or 0) >= 1 and pd.notna(md) and md > 900 and not k.traded:
                                add(s, "rt_solo_death")

    # ---------- noise ----------
    if ST is not None and len(ST):
        a = ST[ST.enemy_dist.notna() & (ST.enemy_dist <= HEAR)]
        for s, n in a.groupby("steamid").size().items():
            add(int(s), "steps_audible", float(n))
        cl = a[a.mates_alive == 0]
        for s, n in cl.groupby("steamid").size().items():
            add(int(s), "steps_clutch", float(n))
        lu = a[(a.side == "T") & (a.mate_dist.fillna(0) > ALONE) & (a.mates_alive >= 2)]
        for s, n in lu.groupby("steamid").size().items():
            add(int(s), "steps_alone", float(n))
        clr = ST[ST.mates_alive == 0].groupby("steamid")["round"].nunique()
        for s, n in clr.items():
            add(int(s), "clutch_rounds", float(n))
    for a in acc.values():
        for k in ("fake_rounds", "repeek_rounds"):
            a[k] = ",".join(str(r) for r in a.get(k, []))
    rows = pd.DataFrame(list(acc.values()))
    rows["match"] = os.path.basename(os.path.normpath(ddir))
    rows["pro"] = pro
    return rows, pd.DataFrame(rot_rows)


def _one(args):
    ddir, out, out_r, pro = args
    mid = os.path.basename(ddir)
    try:
        rows, rot = analyze(ddir, pro)
        rows.to_parquet(os.path.join(out, f"{mid}.parquet"))
        rot.to_parquet(os.path.join(out_r, f"{mid}.parquet"))
        return mid, len(rot)
    except Exception as e:
        import traceback
        return mid, f"ERROR {e} {traceback.format_exc()[-400:]}"


def run_all(workers=6, log=print, force=False):
    site_centers(rebuild=force or not os.path.exists(SITES))
    todo = []
    for base, out, out_r, pro in ((config.DEEP, OUT, OUT_R, False), (DEEP_PRO, OUT_PRO, OUT_PRO_R, True)):
        if not os.path.exists(base):
            continue
        os.makedirs(out, exist_ok=True)
        os.makedirs(out_r, exist_ok=True)
        have = set() if force else ledger.names(out)   # 15/10: one read of the folder, not a file check per match
        for mid in os.listdir(base):
            if mid in have:
                continue
            d = os.path.join(base, mid)
            if not os.path.exists(os.path.join(d, "samples.parquet")):
                continue
            if not pro and not os.path.exists(os.path.join(d, "rounds.parquet")):
                continue
            todo.append((d, out, out_r, pro))
    if not todo:
        return 0
    log(f"Mid-round: {len(todo)} demo(s)…")
    from concurrent.futures import ProcessPoolExecutor
    if len(todo) == 1:   # one new match (a sync's): here, no process started for it (16/10: 1 s of the extraction; it
        mid, res = _one(todo[0])   # reads the tables only, never a demo)
        if isinstance(res, str):
            log(f"  [{mid}] {res}")
        return 1
    with ProcessPoolExecutor(min(workers, len(todo))) as ex:
        for i, (mid, res) in enumerate(ex.map(_one, todo), 1):
            if isinstance(res, str):
                log(f"  [{mid}] {res}")
    return len(todo)


def load(pro=False):
    """Every match's table as one (kept consolidated: only the new matches' files are read, ledger.py)."""
    return ledger.stacked(OUT_PRO if pro else OUT, "midround_pro" if pro else "midround")


def load_routes(pro=False):
    """Every match's rotations as one (kept consolidated: only the new matches' files are read, ledger.py)."""
    return ledger.stacked(OUT_PRO_R if pro else OUT_R, "routes_pro" if pro else "routes",
                          prep=lambda d, f: d.dropna(axis=1, how="all"), skip_empty=True)


# ---------- benchmarks ----------
# metric: (numerator, denominator, min denominator, label, higher_is_better, unit, scale)
BENCH = {
    "rot_react": ("rot_react_sum", "rot_react_n", 4, N_("time before rotating after the site is hit"), False, " s", 1),
    "rot_died": ("rot_died_way", "rot_done", 5, N_("rotations where you die on the way"), False, "%", 100),
    "rot_early": ("rot_early", "rot_done", 5, N_("rotations started before the hit (anticipated)"), None, "%", 100),
    "rot_stayed": ("rot_stayed", "rot_needed", 5, N_("hits on the other site where you stay in place"), None, "%", 100),
    "anchor_hold": ("anchor_hold5", "anchor_n", 5, N_("hits on your site where you hold at least 5 s"), True, "%", 100),
    "anchor_kpr": ("anchor_kills", "anchor_n", 5, N_("kills per attack faced as anchor"), True, "", 1),
    "lurk_kpr": ("lurk_kills", "lurk_n", 5, N_("kills per lurk round"), True, "", 1),
    "lurk_died": ("lurk_died", "lurk_n", 5, N_("lurk rounds where you die"), False, "%", 100),
    "t_late": ("t_late", "t_follow_n", 5, N_("executes where you arrive more than 10 s after the others"), False, "%", 100),
    "pp_surv": ("pp_survived", "pp_n", 5, N_("survival after the plant (T)"), True, "%", 100),
    "pp_kpr": ("pp_kills", "pp_n", 5, N_("kills after the plant (T)"), True, "", 1),
    "rt_solo": ("rt_solo_death", "rt_n", 5, N_("deaths alone in a retake (CT)"), False, "%", 100),
    "adv_throw": ("adv_throw", "adv_rounds", 8, N_("man advantages thrown (untraded death)"), False, "%", 100),
    "adv_conv": ("adv_won", "adv_rounds", 8, N_("rounds won after having the advantage"), True, "%", 100),
    "lost_died": ("lost_died", "lost_n", 3, N_("lost-cause rounds where you die instead of saving"), False, "%", 100),
    "isolated": ("isolated_deaths", "rounds", 30, N_("isolated deaths (no teammate nearby) per 24 rounds"), False, "", 24),
    "steps_alone": ("steps_alone", "rounds", 30, N_("audible steps when alone as T, per 24 rounds"), False, "", 24),
    "steps_clutch": ("steps_clutch", "clutch_rounds", 3, N_("audible steps per clutch"), False, "", 1),
    "fake_pulled": ("fake_pulled", "fake_n", 5, N_("hits on your site after you had left it (pulled by a fake)"), False, "%", 100),
    "repeek": ("repeek", "kill_rounds", 8, N_("rounds with a kill where you die within 8 s of it"), False, "%", 100),
}


def _pool(df):
    num = [c for v in BENCH.values() for c in v[:2]]
    cols = [c for c in set(num) if c in df.columns]
    g = df.groupby("steamid")[cols].sum(min_count=1).fillna(0)
    g["name"] = df.groupby("steamid")["name"].last()
    g["matches"] = df.groupby("steamid").size()
    return g


def _ratios(P, m):
    a, b, mn, _, _, _, sc = BENCH[m]
    if a not in P.columns or b not in P.columns:
        return pd.Series(dtype=float)
    ok = P[b] >= mn
    return (P.loc[ok, a] / P.loc[ok, b] * sc).astype(float)


def bench(steamid):
    """The player's mid-round numbers vs every player of the base and vs pros (pooled over matches)."""
    sid = int(steamid)
    pop = load()
    if not len(pop):
        return None
    P = _pool(pop)
    if sid not in P.index:
        return None
    pro = load(pro=True)
    PR = _pool(pro) if len(pro) else None
    me = P.loc[sid]
    others = P.drop(index=sid)
    out = {"n_players": int(len(others)), "n_pros": 0 if PR is None else int(len(PR)), "matches": int(me["matches"]), "metrics": {}}
    for m, (a, b, mn, label, hib, unit, sc) in BENCH.items():
        s = _ratios(others, m)
        if len(s) < 20:
            continue
        you = float(me[a]) / float(me[b]) * sc if a in me and b in me and me[b] >= mn else None
        prov = _ratios(PR, m) if PR is not None else pd.Series(dtype=float)
        pct = None
        if you is not None and hib is not None:
            pct = float((s < you).mean() * 100) if hib else float((s > you).mean() * 100)
        out["metrics"][m] = {"label": label, "you": None if you is None else round(you, 2), "n_you": float(me.get(b, 0)),
                             "median": round(float(s.median()), 2), "good": round(float(s.quantile(.75 if hib else .25)), 2) if hib is not None else None,
                             "pro": round(float(prov.median()), 2) if len(prov) >= 8 else None, "n_pro": int(len(prov)),
                             "percentile": None if pct is None else round(pct), "higher_better": hib, "unit": unit, "n": int(len(s))}
    return out


def route_refs(rebuild=False):
    """Per map and target site: routes used by the base and by pros, with travel time and deaths on the way."""
    f = os.path.join(config.OUT, "population", "route_refs.json")
    n = len(os.listdir(OUT_R)) + (len(os.listdir(OUT_PRO_R)) if os.path.exists(OUT_PRO_R) else 0) if os.path.exists(OUT_R) else 0
    if os.path.exists(f) and not rebuild:
        cur = json.load(open(f, encoding="utf-8"))
        if cur.get("_n") == n:
            return cur
    res = {"_n": n}
    for who, df in (("base", load_routes()), ("pro", load_routes(pro=True))):
        if not len(df):
            continue
        df = df[df.route.notna() & (df.route != "")].copy()
        df["r3"] = df.route.map(lambda r: " > ".join(r.split(" > ")[:3]))
        for (mp, to), g in df.groupby(["map", "to"]):
            ok = g[g.react >= -3]
            timing = {"react_med": round(float(ok.react.median()), 1) if len(ok) >= 5 else None,
                      "travel_med": round(float(g.travel.dropna().median()), 1) if g.travel.notna().sum() >= 5 else None,
                      "died_way": round(100 * g.died_way.mean()), "n": int(len(g))}
            routes = []
            for r, gg in g.groupby("r3"):
                if len(gg) < 3:
                    continue
                routes.append({"route": r, "n": int(len(gg)), "travel": None if gg.travel.notna().sum() < 2 else round(float(gg.travel.dropna().median()), 1),
                               "died": round(100 * gg.died_way.mean()), "arrived": round(100 * gg.arrived.mean())})
            routes.sort(key=lambda x: -x["n"])
            byw = {}
            if who == "base" and "wclass" in g and g.wclass.notna().any():
                for w, gw in g[g.wclass.notna()].groupby("wclass"):
                    if len(gw) >= 6:
                        top = gw.r3.value_counts().head(2)
                        byw[w] = {"n": int(len(gw)), "died": round(100 * gw.died_way.mean()),
                                  "travel": None if gw.travel.notna().sum() < 3 else round(float(gw.travel.dropna().median()), 1),
                                  "routes": [{"route": r, "n": int(n)} for r, n in top.items()]}
            res.setdefault(mp, {}).setdefault(to, {})[who] = {"timing": timing, "routes": routes[:6], "by_weapon": byw}
    json.dump(res, open(f, "w", encoding="utf-8"), ensure_ascii=False)
    return res


def retake_routes(min_n=3):
    """Per map, site and starting zone of a CT: the ways players of the base rotate to the site (first zones of the
    route), how long it takes and how often they die on the way."""
    from wily.demos.map_analysis import humanize
    df = load_routes()
    out = {}
    if not len(df):
        return out
    df = df[df.route.notna() & (df.route != "")].copy()
    df["r3"] = df.route.map(lambda r: tuple(r.split(" > ")[:3]))
    for (mp, to, sz), g in df.groupby(["map", "to", "start_zone"]):
        if len(g) < min_n or not isinstance(sz, str):
            continue
        rs = []
        for r, gg in g.groupby("r3"):
            if len(gg) < 2:
                continue
            tr = gg.travel.dropna()
            rs.append({"route": [humanize(z, mp) for z in r], "n": int(len(gg)), "died": round(100 * gg.died_way.mean()),
                       "travel": round(float(tr.median()), 1) if len(tr) else None})
        if not rs:
            continue
        rs.sort(key=lambda x: (-x["n"], x["died"]))
        tr = g.travel.dropna()
        out.setdefault(mp, {}).setdefault(to, {})[humanize(sz, mp)] = {
            "n": int(len(g)), "died": round(100 * g.died_way.mean()), "travel": round(float(tr.median()), 1) if len(tr) else None,
            "routes": rs[:2]}
    return out


def player_routes(steamid):
    """The player's own rotations per map and site, next to the base and pro references."""
    sid = int(steamid)
    df = load_routes()
    if not len(df):
        return {}
    me = df[df.steamid == sid]
    refs = route_refs()
    out = {}
    for (mp, to), g in me.groupby(["map", "to"]):
        ref = refs.get(mp, {}).get(to, {})
        ok = g[g.react >= -3]
        out.setdefault(mp, {})[to] = {
            "n": int(len(g)), "arrived": int(g.arrived.sum()), "died_way": int(g.died_way.sum()),
            "react_med": round(float(ok.react.median()), 1) if len(ok) else None,
            "travel_med": round(float(g.travel.dropna().median()), 1) if g.travel.notna().any() else None,
            "routes": {r: int(n) for r, n in g.route.map(lambda r: " > ".join(r.split(" > ")[:3])).value_counts().head(3).items()},
            "last": [{"round": int(x["round"]), "route": x.route, "react": x.react, "travel": x.travel, "died_way": bool(x.died_way), "wclass": x.wclass}
                     for _, x in g.tail(6).iterrows()],
            "ref": ref,
        }
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(run_all(force="--force" in sys.argv))
