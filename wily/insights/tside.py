"""What the T side does, round after round, in every demo of the base: which site they hit and when, how many go,
where they come from, where the first duel happens, and what they did on the previous rounds of the half.

Feeds the CT side of the in-game sheet: the odds of A or B on the next round, from the kind of round (pistol,
round 2, eco, force, full) and from what the T did before (the same site after a win, the other one after a loss...).
Writes out/population/tside/<match>.parquet (one row per round).
Usage: python -m wily.insights.tside
"""
import os
import sys

import numpy as np
import pandas as pd

from wily.core import config
from wily.core import ledger
from wily.core.i18n import N_, tr, trn
from wily.insights import midround
from wily.demos.deep import read_nades   # a match with no grenade has an empty table without columns

OUT = os.path.join(config.OUT, "population", "tside")
ZONES = os.path.join(config.OUT, "population", "tside_zones.json")   # which zones lead to which site, per map
LANES = os.path.join(config.OUT, "population", "tside_lanes.json")   # how each site is entered, per map (lanes.py)
RUSH = 30.0          # site taken in the first 30 s (timer above 1:25): a rush
LATE = 75.0          # site taken after 75 s (timer under 0:40): a late hit
LONE = 1000.0        # a T with no teammate within 1000 units (about 25 m) is alone
ROUND_TIME = 115.0
DYN_FR = {"rush": N_("rush"), "fast": N_("fast push by 1-2 Ts"), "exec": N_("execute"), "late": N_("late hit"), "none": N_("no attack")}
CONTEXTS = ["pistol", "r2_win", "r2_loss", "eco", "force", "full"]
CTX_FR = {"pistol": N_("Pistol round"), "r2_win": N_("Round 2, Ts won the pistol"), "r2_loss": N_("Round 2, Ts lost the pistol"),
          "eco": "T eco", "force": N_("T force-buy"), "full": N_("T full buy")}
BUY_FR = {"eco": "eco", "force": "force-buy", "full": N_("full buy")}


def humanize(z, mp=None):
    from wily.demos.map_analysis import humanize as h
    return h(z, mp) if z else z


def five_v_five(R):
    """Wingman demos (2v2, one site) say nothing about 5v5 habits."""
    return len(R) and R.T_n.max() >= 4 and R.CT_n.max() >= 4


def _paths(T_, kd):
    """Every T's way through the map in the round: 'zone@t>zone@t>...>†@t' (raw place names, a change of zone at a
    time, † when killed), one T per ';'. Tells the route of an attack: through a main, through mid, or both."""
    dead = {}
    if len(kd) and "victim" in kd:
        for v, t, s in zip(kd.victim, kd.t, kd.victim_side):
            if s == "T" and v == v:
                dead.setdefault(v, float(t))
    out = []
    for sid, x in T_.sort_values("t").groupby("steamid"):
        seq, last = [], None
        for z, t in zip(x.zone, x.t):
            if isinstance(z, str) and z and z != "?" and z != last:
                seq.append(f"{z}@{t:.0f}")
                last = z
        if sid in dead:
            seq.append(f"†@{dead[sid]:.0f}")
        if seq:
            out.append(">".join(seq))
    return ";".join(out) or None


def analyze(ddir):
    """-> one row per round: the site the T hit (A, B or '-' when they never did), when, with how many."""
    meta = midround._meta(ddir)
    mname = meta.get("map")
    sites = midround.site_centers().get(mname)
    fr = os.path.join(ddir, "rounds.parquet")
    if not sites or not os.path.exists(fr):
        return pd.DataFrame()
    R = pd.read_parquet(fr).sort_values("round")
    if not five_v_five(R):
        return pd.DataFrame()
    S = pd.read_parquet(os.path.join(ddir, "samples.parquet"), columns=["steamid", "side", "round", "t", "X", "Y", "Z", "zone", "health"])
    S = S[(S.steamid != 0) & (S.health > 0)]
    fd = os.path.join(ddir, "duels.parquet")
    dcols = ["round", "t", "victim", "killer_side", "victim_side", "victim_zone", "killer_zone", "victim_mate_dist", "killer_mate_dist", "traded"]
    D = pd.read_parquet(fd).reindex(columns=dcols) if os.path.exists(fd) else pd.DataFrame()
    # teams: the T of the first round are team a, whatever side they play later
    first = S[S["round"] == R["round"].min()]
    team_a = set(first[first.side == "T"].steamid)
    team_b = set(first[first.side == "CT"].steamid)
    rows, score, prev_team, half = [], {"a": 0, "b": 0}, None, -1
    rih = 0
    for _, r in R.iterrows():
        rnd = int(r["round"])
        g = S[S["round"] == rnd]
        tset = set(g[g.side == "T"].steamid)
        if not tset:
            continue
        team = "a" if len(tset & team_a) >= len(tset & team_b) else "b"
        if team != prev_team:  # sides swapped: a new half (or overtime half)
            half, rih, prev_team = half + 1, 0, team
        rih += 1
        T_ = g[g.side == "T"]
        # the site is the game's own area (nav place BombsiteA / BombsiteB): exact, even on stacked sites (Nuke)
        in_site = {L: T_[T_.zone == f"Bombsite{L}"] for L in ("A", "B")}

        def first_n(x, k=2, lo=0.0, hi=1e9):
            x = x[(x.t >= lo) & (x.t <= hi)]
            c = x.groupby("t").steamid.nunique()
            ok = c[c >= k]
            return float(ok.index[0]) if len(ok) else None
        plant_site = r.get("plant_site") if r.get("plant_site") in ("A", "B") else None
        plant_t = float(r.plant_t) if plant_site and pd.notna(r.get("plant_t")) else None
        hit = None
        if plant_site:
            x = in_site[plant_site]
            ft = first_n(x, 2, plant_t - 25, plant_t)
            if ft is None:
                ft = first_n(x, 1, plant_t - 25, plant_t)
            hit = (plant_site, ft if ft is not None else max(plant_t - 3, 0.0))
        else:
            cand = [(x, L_) for x, L_ in ((first_n(in_site["A"]), "A"), (first_n(in_site["B"]), "B")) if x is not None]
            if cand:
                t0, L_ = min(cand)
                hit = (L_, t0)
        kd = D[D["round"] == rnd].sort_values("t") if len(D) else D
        entered = hit is not None
        # T fights after the first 12 s (before they got in): tells the side of an attack stopped before the site
        ev = kd[(kd.t >= 12) & (kd.t < (hit[1] if hit else 1e9))] if len(kd) else kd
        t_events = [(z, float(t)) for z, t in zip(ev[ev.victim_side == "T"].victim_zone, ev[ev.victim_side == "T"].t)] +                    [(z, float(t)) for z, t in zip(ev[ev.killer_side == "T"].killer_zone, ev[ev.killer_side == "T"].t)] if len(ev) else []
        rec = {"map": mname, "round": rnd, "half": half, "rih": rih, "t_team": team, "entered": entered,
               "score_t": score[team], "score_ct": score["b" if team == "a" else "a"],
               "T_buy": r.T_buy, "CT_buy": r.CT_buy, "winner": r.winner, "reason": r.reason,
               "T_won": r.winner == "T", "plant_site": plant_site, "plant_t": plant_t, "end_t": float(r.end_t) if pd.notna(r.end_t) else None,
               "site": "-", "hit_t": None, "n_exec": None, "n_push": None, "lurk_other": None, "approaches": None, "pre_zones": None,
               "t_events": ";".join(f"{z}@{t:.1f}" for z, t in t_events if isinstance(z, str) and z) or None,
               "first_zone": None, "first_t": None, "first_t_side_won": None, "t_alive_hit": None, "ct_alive_hit": None,
               "fc_alone": None, "t_deaths": None, "ct_deaths": None, "bunch_t": None, "bunch_zone": None,
               "t_paths": _paths(T_, kd)}
        if len(kd):
            k0 = kd.iloc[0]
            # the T of the first duel: alone (no teammate within LONE units) or with others
            md = k0.victim_mate_dist if k0.victim_side == "T" else k0.killer_mate_dist if k0.killer_side == "T" else None
            rec.update(first_zone=humanize(k0.victim_zone, mname), first_t=float(k0.t), first_t_side_won=k0.killer_side == "T",
                       fc_alone=bool(md > LONE) if md is not None and md == md else None)
            # who died where and when: a T killed alone and not traded is flagged
            td = kd[kd.victim_side == "T"]
            lone = (td.victim_mate_dist.fillna(0) > LONE) & ~td.traded.fillna(False).astype(bool)
            rec["t_deaths"] = ";".join(f"{humanize(z, mname) if isinstance(z, str) and z != '?' else '?'}@{t:.1f}@{int(l)}"
                                       for z, t, l in zip(td.victim_zone, td.t, lone)) or None
            cd = kd[kd.victim_side == "CT"]
            rec["ct_deaths"] = ";".join(f"{humanize(z, mname) if isinstance(z, str) and z != '?' else '?'}@{t:.1f}"
                                        for z, t in zip(cd.victim_zone, cd.t)) or None
            # 3 Ts down within 10 s: the push died there
            tt = td.t.to_numpy()
            for i in range(len(tt) - 2):
                if tt[i + 2] - tt[i] <= 10:
                    zz = td[(td.t >= tt[i]) & (td.t <= tt[i] + 10)].victim_zone.dropna()
                    rec.update(bunch_t=float(tt[i]), bunch_zone=humanize(zz.mode().iloc[0], mname) if len(zz) else None)
                    break
        if hit:
            site, ht = hit
            other = "B" if site == "A" else "A"
            x = in_site[site]
            hitters = set(x[(x.t >= ht) & (x.t <= ht + 6)].steamid)
            # where the players who took the site came from, 3 to 6 s earlier
            skip = T_.zone.str.startswith("Bombsite") | T_.zone.isin(["?", "TSpawn", "CTSpawn"])
            before = T_[T_.steamid.isin(hitters) & (T_.t >= ht - 6) & (T_.t <= ht - 3) & ~skip]
            came = before.groupby("steamid").zone.agg(lambda z: z.mode().iloc[0]) if len(before) else pd.Series(dtype=object)
            # every zone each T went through in the 20 s before: learns which zones lead to which site
            pre = T_[(T_.t >= ht - 20) & (T_.t <= ht - 2) & ~skip]
            pre_zones = ";".join(",".join(sorted(set(z))) for _, z in pre.groupby("steamid").zone) if len(pre) else None
            # a T still next to the other site when this one is taken (lurk, or a split)
            oc, orad = sites[other]["c"], sites[other]["r"]
            at = T_[(T_.t >= ht - 1) & (T_.t <= ht + 1) & ~T_.steamid.isin(hitters)]
            lurk = bool((midround._dist(at.X.values, at.Y.values, at.Z.values, oc) <= orad).any()) if len(at) else False
            deaths_before = kd[kd.t < ht] if len(kd) else kd
            # the Ts of the push: the ones who got in, plus the ones killed on the way in the last 10 s
            died_on_way = int(((deaths_before.victim_side == "T") & (deaths_before.t >= ht - 10)).sum()) if len(kd) else 0
            rec.update(site=site, hit_t=round(ht, 1), n_exec=int(len(hitters)), n_push=int(len(hitters)) + died_on_way,
                       lurk_other=lurk, pre_zones=pre_zones,
                       approaches=",".join(humanize(z, mname) for z in came.values) if len(came) else None,
                       t_alive_hit=int(r.T_n) - int((deaths_before.victim_side == "T").sum()) if len(kd) else int(r.T_n),
                       ct_alive_hit=int(r.CT_n) - int((deaths_before.victim_side == "CT").sum()) if len(kd) else int(r.CT_n))
        rows.append(rec)
        if r.winner in ("T", "CT"):
            score[team if r.winner == "T" else ("b" if team == "a" else "a")] += 1
    return pd.DataFrame(rows)


REQ = ("t_deaths", "t_paths")   # the columns a match's file must have (an older version's is analyzed again)


def _outdated(f):
    """A file written by an older version (no deaths per round yet) is analyzed again."""
    import pyarrow.parquet as pq
    try:
        names = pq.read_schema(f).names
    except Exception:
        return True
    return "map" in names and any(c not in names for c in REQ)


def run_all(log=print, force=False):
    """The matches whose T side is missing, older than their rounds or written by an older version (the ones found
    up to date before are not opened again: ledger.py, 15/10)."""
    os.makedirs(OUT, exist_ok=True)
    led = ledger.Ledger("tside", version=list(REQ))
    have = ledger.names(OUT)
    n = 0
    for mid, stamp in ledger.folders(config.DEEP).items():
        if not force and mid in have and led.settled(mid, stamp):
            continue
        d = os.path.join(config.DEEP, mid)
        f = os.path.join(OUT, f"{mid}.parquet")
        src = os.path.join(d, "rounds.parquet")
        if not os.path.exists(src) or not os.path.exists(os.path.join(d, "samples.parquet")):
            continue
        if not force and mid in have and os.path.getmtime(f) >= os.path.getmtime(src) and not _outdated(f):
            led.mark(mid, stamp)
            continue
        try:
            analyze(d).to_parquet(f)
            led.mark(mid, stamp)
            n += 1
        except Exception as e:
            log(f"[{mid}] T side: {e}")
    led.save()
    return n


# 07/10, the user: "qu'est-ce qui prend autant de temps ?": a plan read the base's 3,049 per-match files from the hard
# disk 3 or 4 times (its situations, the Live checks, the teammates' spots), 2 min each. Now one consolidated file per
# state of the base (its files' count and newest date), and the table kept in memory for the next callers (15 min idle)
ALL = os.path.join(config.OUT, "population", "tside_all.parquet")
_MEM = {}


def _base_state():
    try:   # one read of the folder (os.scandir has the dates: no file opened, 15/10)
        with os.scandir(OUT) as it:
            st = {e.name: e.stat().st_mtime for e in it if e.name.endswith(".parquet")}
        fs = [f for f in os.listdir(OUT) if f in st]
    except OSError:
        return None, []
    newest = max(st.values(), default=0.0)
    return f"{len(fs)}:{newest:.0f}", fs


def _raw(state, fs):
    """Every match's rounds in one table: the consolidated file when it matches the base, else read and written."""
    import json
    side = ALL + ".json"
    try:
        if json.load(open(side, encoding="utf-8")).get("state") == state:
            return pd.read_parquet(ALL)
    except (OSError, ValueError):
        pass
    def prep(x, f):
        if len(x):
            x["match"] = f[:-8]
        return x
    df = ledger.stacked(OUT, "tside", prep=prep, skip_empty=True)   # only the new matches' files read (15/10)
    if not len(df):
        return pd.DataFrame()
    try:
        tmp = ALL + f".{os.getpid()}.tmp"
        df.to_parquet(tmp)
        os.replace(tmp, ALL)
        json.dump({"state": state}, open(side, "w", encoding="utf-8"))
    except Exception as e:   # a column parquet refuses: the next call reads the files again
        print("tside: no consolidated copy:", e, flush=True)
    return df


def load():
    """The base's T side, round by round, with its directions, dynamics and sequences (a copy: callers may change it)."""
    import threading
    state, fs = _base_state()
    hit = _MEM.get("df")
    if hit is None or hit[0] != state:
        hit = (state, _load(state, fs))
        _MEM["df"] = hit
    t = _MEM.get("timer")
    if t:
        t.cancel()
    t = threading.Timer(900, lambda: _MEM.pop("df", None))   # the memory back after 15 min without a caller
    t.daemon = True
    t.start()
    _MEM["timer"] = t
    return hit[1].copy()


# 16/10 (the user: "encore beaucoup beaucoup trop long"): the table as load() gives it kept on disk with its matches'
# dates; a new match's rounds read with the zones and lanes learned on the base before it and joined to it (the whole
# base read and learned again at each new match: 10 s). Learned again once the base has grown 5 % since, or when a
# match of before left (tside.nades.fresh keeps the tendencies the same way, until 15 %).
PROC = os.path.join(config.OUT, "population", "tside_proc.parquet")
GROW = 0.05


def _files():
    try:
        with os.scandir(OUT) as it:
            return {e.name: e.stat().st_mtime_ns for e in it if e.name.endswith(".parquet")}
    except OSError:
        return {}


def _load(state, fs):
    import json
    now = _files()
    try:
        meta = json.load(open(PROC + ".json", encoding="utf-8"))
        old, learned = meta["files"], int(meta["learned"])
        todo = [f for f in fs if old.get(f) != now.get(f)]   # new, or written again
        if all(f in now for f in old) and len(now) <= learned * (1 + GROW) and len(todo) <= learned * GROW:
            df = _joined(pd.read_parquet(PROC), todo)
            if df is not None:
                if todo:
                    _keep(df, now, learned)
                return df
    except Exception as e:   # no table kept, or a new match it can't take: learned again, as before
        if not isinstance(e, (OSError, ValueError, KeyError)):
            print("tside: learned again:", type(e).__name__, e, flush=True)
    df = _learned(state, fs)
    if len(df):
        _keep(df, now, len(now))
    return df


def _keep(df, files, learned):
    import json
    try:
        tmp = f"{PROC}.{os.getpid()}.tmp"
        df.to_parquet(tmp)
        os.replace(tmp, PROC)
        json.dump({"files": files, "learned": learned}, open(PROC + ".json", "w", encoding="utf-8"))
    except Exception as e:   # a column parquet refuses: learned again next time
        print("tside: table not kept:", e, flush=True)
        try:
            os.remove(PROC + ".json")
        except OSError:
            pass


def _joined(kept, todo):
    """The table kept, with the matches of todo (new, or written again) read with the zones and lanes it was learned
    with. None: they can't be read that way (learned again)."""
    import json
    from wily.insights import lanes as LN
    if not todo:
        return kept
    parts = []
    for f in todo:
        try:
            x = pd.read_parquet(os.path.join(OUT, f))
        except Exception:   # a file being written: learned again, as before
            return None
        if len(x):
            x["match"] = f[:-8]
            parts.append(x)
    kept = kept[~kept["match"].isin({f[:-8] for f in todo})]
    if not parts:
        return kept.reset_index(drop=True)
    zs = json.load(open(ZONES, encoding="utf-8"))
    new = _sequences(_dynamics(_directions(pd.concat(parts, ignore_index=True), zs=zs)))
    if "play" in kept:
        new = LN.classify(new, _lanes(), LN.geo())
    for c in kept.columns.intersection(new.columns):   # the types of the kept table (a column all empty in the new rows)
        if new[c].dtype != kept[c].dtype:
            try:
                new[c] = new[c].astype(kept[c].dtype)
            except (TypeError, ValueError):
                pass
    return pd.concat([kept, new], ignore_index=True).sort_values(["match", "half", "round"]).reset_index(drop=True)


def _learned(state, fs):
    df = _raw(state, fs)
    if not len(df):
        return pd.DataFrame()
    zs = zone_sites(df)
    try:   # kept for the round-by-round story of a single match (no need to load the whole base)
        import json
        tmp = ZONES + f".{os.getpid()}.tmp"
        json.dump(zs, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, ZONES)
    except OSError:
        pass
    df = _sequences(_dynamics(_directions(df, zs=zs)))
    return _with_plays(df)


def _with_plays(df):
    """Lanes of every site and the play of every round (lanes.py); kept on disk for single matches."""
    import json
    from wily.insights import lanes as LN
    try:
        G = LN.geo()
        ls, mem = LN.learn(df, G)
        df = LN.classify(df, ls, G, mem)
        tmp = LANES + f".{os.getpid()}.tmp"
        json.dump(ls, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, LANES)
    except Exception as e:   # the rest of the reading stays usable
        print(f"plays unavailable ({e})")
    return df


def _lanes():
    import json
    try:
        return json.load(open(LANES, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def zone_sites(df):
    """For every zone of a map: in how many rounds the T who went through it then got into A, or into B."""
    out = {}
    ent = df[df.entered.fillna(False).astype(bool) & df.site.isin(["A", "B"])]
    for mp, g in ent.groupby("map"):
        cnt = {}
        for site, pz in zip(g.site, g.pre_zones):
            for z in {z for p in str(pz or "").split(";") for z in p.split(",") if z}:
                c = cnt.setdefault(z, [0, 0])
                c[site == "B"] += 1
        out[mp] = {z: c for z, c in cnt.items() if sum(c) >= 15}
    return out


def _directions(df, lean=0.7, zs=None):
    """An attack stopped before the site still has a side: where the T fought, when those zones lead to one site
    in at least 70 % of the rounds where the T got in. Also counts the fights of that push in its first 10 s."""
    zs = zone_sites(df) if zs is None else zs
    site, when, many = df.site.tolist(), [None] * len(df), [None] * len(df)
    for i, (mp, ent, evs) in enumerate(zip(df["map"], df.entered, df.t_events)):
        if ent or not isinstance(evs, str):
            continue
        votes = {"A": [], "B": []}
        for e in evs.split(";"):
            z, _, t = e.rpartition("@")
            if z in ("BombsiteA", "BombsiteB"):
                votes[z[-1]].append(float(t))
                continue
            c = zs.get(mp, {}).get(z)
            if c:
                pA = c[0] / sum(c)
                if pA >= lean:
                    votes["A"].append(float(t))
                elif pA <= 1 - lean:
                    votes["B"].append(float(t))
        top = max(votes, key=lambda k: len(votes[k]))
        if len(votes[top]) >= 2 and len(votes[top]) > len(votes["B" if top == "A" else "A"]):
            t0 = min(votes[top])
            site[i], when[i], many[i] = top, t0, sum(1 for t in votes[top] if t <= t0 + 10)
    df["site"] = site
    df["stop_t"] = when
    df["stop_n"] = many
    df["entered"] = df.entered.fillna(False).astype(bool)
    return df


def _deaths_list(s, lone_flag=True):
    """'zone@t@1;...' -> [(zone, t, alone)]"""
    out = []
    for e in str(s or "").split(";"):
        p = e.split("@")
        if len(p) >= 2:
            try:
                out.append((p[0], float(p[1]), p[2] == "1" if lone_flag and len(p) > 2 else False))
            except ValueError:
                pass
    return out


def _dynamics(df):
    """The shape of each attack, as the CT side sees it in the kill feed: a rush (3+ Ts on a site in the first 30 s),
    a fast push by 1-2 Ts, an execute, a late hit (after 75 s), or no attack; and the Ts lost alone before it
    (no teammate within 1000 units, not traded)."""
    if "t_deaths" not in df:
        df["t_deaths"] = None
    ent = df.entered.to_numpy(dtype=bool)
    ht = pd.to_numeric(df.hit_t, errors="coerce").to_numpy(dtype=float)
    stt = pd.to_numeric(df.stop_t, errors="coerce").to_numpy(dtype=float)
    commit = np.where(ent, ht, stt)
    push = df.n_push if "n_push" in df else df.n_exec
    grp = np.where(ent, pd.to_numeric(push, errors="coerce").to_numpy(dtype=float),
                   pd.to_numeric(df.get("stop_n"), errors="coerce").to_numpy(dtype=float) if "stop_n" in df else np.nan)
    has = df.site.isin(["A", "B"]).to_numpy() & ~np.isnan(commit)
    dyn = np.where(~has, "none", np.where(commit <= RUSH, np.where(np.nan_to_num(grp) >= 3, "rush", "fast"),
                                          np.where(commit <= LATE, "exec", "late")))
    lone_n, lone_zone, lone_t = [], [], []
    for c, s in zip(commit, df.t_deaths):
        lim = c if c == c else 60.0
        lo = [(z, t) for z, t, a in _deaths_list(s) if a and t < lim]
        lone_n.append(len(lo))
        lone_zone.append(lo[0][0] if lo else None)
        lone_t.append(lo[0][1] if lo else None)
    df["commit"], df["grp"], df["dyn"] = commit, grp, dyn
    df["lone_n"], df["lone_zone"], df["lone_t"] = lone_n, lone_zone, lone_t
    return df


def _context(r):
    return _ctx(r.rih, r.pistol_won, r.T_buy)


def _ctx(rih, pistol_won, T_buy):
    if rih == 1:
        return "pistol"
    if rih == 2 and pistol_won is not None:
        return "r2_win" if pistol_won else "r2_loss"
    return T_buy if T_buy in ("eco", "force", "full") else None


def _sequences(df):
    """What the same T team did before, in the same half: last site, won or lost, streak, how often each site."""
    df = df.sort_values(["match", "half", "round"]).reset_index(drop=True)
    cols = {k: [] for k in ("prev_site", "prev_won", "streak", "nA", "nB", "pistol_won", "losses", "prev_dyn", "prev_lone",
                            "rush_before", "n_before")}
    # 16/10: the columns read as lists, the rows in their order (sorted: each team's half in a row), not row by row
    # through pandas (97,845 rows: most of the time of a plan's T side)
    col = lambda c: df[c].tolist() if c in df else [None] * len(df)
    key = object()
    for m_, h_, dyn, lone_n, rih, T_won, site in zip(df["match"].tolist(), df["half"].tolist(), col("dyn"), col("lone_n"),
                                                      df.rih.tolist(), df.T_won.tolist(), df.site.tolist()):
        if (m_, h_) != key:   # a new team's half
            key = (m_, h_)
            last_site, last_won, streak, nA, nB, pw, losses = None, None, 0, 0, 0, None, 0
            last_dyn, last_lone, rushes, nb = None, None, 0, 0
        cols["prev_site"].append(last_site)
        cols["prev_won"].append(last_won)
        cols["streak"].append(streak)
        cols["nA"].append(nA)
        cols["nB"].append(nB)
        cols["pistol_won"].append(pw)
        cols["losses"].append(losses)
        cols["prev_dyn"].append(last_dyn)
        cols["prev_lone"].append(last_lone)
        cols["rush_before"].append(rushes)
        cols["n_before"].append(nb)
        last_dyn, last_lone = dyn, bool(lone_n or 0)
        rushes += dyn == "rush"
        nb += 1
        if rih == 1:
            pw = bool(T_won)
        losses = 0 if T_won else losses + 1
        last_won = bool(T_won)
        if site in ("A", "B"):
            streak = streak + 1 if site == last_site else 1
            last_site = site
            nA += site == "A"
            nB += site == "B"
        else:
            last_site, streak = "-", 0
    for k, v in cols.items():
        df[k] = v
    df["ctx"] = [_ctx(a, b, c) for a, b, c in zip(df.rih.tolist(), df.pistol_won.tolist(), df.T_buy.tolist())]
    return df


# ---------- what the CT side can expect ----------
def _pct(x):
    return int(round(100 * x)) if x == x else None


def _timer(t):
    left = max(0, ROUND_TIME - t)
    return f"{int(left // 60)}:{int(left % 60):02d}"


def _profile(g):
    """Odds of A / B / no hit, rushes, how many go in, where from, first duel."""
    n = len(g)
    hits = g[g.site.isin(["A", "B"]) & g.entered]
    out = {"n": int(n), "A": _pct((g.site == "A").mean()), "B": _pct((g.site == "B").mean()), "none": _pct((g.site == "-").mean()),
           "t_win": _pct(g.T_won.mean())}
    if len(hits) >= 5:
        out["rush"] = _pct((hits.hit_t <= RUSH).mean())
        out["hit_timer"] = _timer(hits.hit_t.median())
        out["lurk"] = _pct(hits.lurk_other.mean())
        for L in ("A", "B"):
            h = hits[hits.site == L]
            if len(h) >= 5:
                ap = pd.Series([z for v in h.approaches.dropna() for z in v.split(",") if z]).value_counts(normalize=True)
                out[f"{L}_detail"] = {"n": int(len(h)), "timer": _timer(h.hit_t.median()), "rush": _pct((h.hit_t <= RUSH).mean()),
                                      "t_win": _pct(h.T_won.mean()),
                                      "from": [{"zone": z, "pct": _pct(p)} for z, p in ap.head(2).items() if p >= 0.15]}
    fz = g.first_zone.dropna().value_counts(normalize=True)
    if len(g.first_zone.dropna()) >= 8:
        out["first"] = [{"zone": z, "pct": _pct(p)} for z, p in fz.head(3).items()]
        out["first_timer"] = _timer(g.first_t.dropna().median())
    if "dyn" in g:   # the shape of the attacks, and how often they lose a T alone before it
        vc = g.dyn.value_counts(normalize=True)
        out["dyn"] = {k: _pct(vc.get(k, 0.0)) for k in DYN_FR}
        out["rush_all"] = out["dyn"]["rush"]
        out["lone"] = _pct((g.lone_n > 0).mean())
    return out


def _switch_table(df):
    """After a hit on one site, how often the next hit is on the other one, by result and streak."""
    h = df[df.site.isin(["A", "B"]) & df.prev_site.isin(["A", "B"])]
    out = []
    for label, sel in ((N_("after a site take they won"), h.prev_won == True),
                       (N_("after a site take they lost"), h.prev_won == False),
                       (N_("after 2+ takes of the same site, the last one lost"), (h.streak >= 2) & (h.prev_won == False)),
                       (N_("after 2+ takes of the same site, the last one won"), (h.streak >= 2) & (h.prev_won == True))):
        x = h[sel]
        if len(x) >= 15:
            out.append({"label": label, "n": int(len(x)), "switch": _pct((x.site != x.prev_site).mean())})
    return out


def _after_table(g, min_n=12):
    """Where the next attack goes, after an attack on A or B won or lost (and after two in a row on the same site)."""
    out = []
    d = g[g.prev_site.isin(["A", "B"])]
    for last in ("A", "B"):
        for won in (True, False):
            for two in (False, True):
                x = d[(d.prev_site == last) & (d.prev_won == won) & ((d.streak >= 2) if two else True)]
                if len(x) >= min_n:
                    out.append({"last": last, "won": won, "twice": two, "n": int(len(x)),
                                "A": _pct((x.site == "A").mean()), "B": _pct((x.site == "B").mean()), "none": _pct((x.site == "-").mean())})
    return out


def _fit(X, y, off, l2=1.0, it=30):
    """Logistic regression with an offset (the map's own odds), a little ridge, Newton steps."""
    b = np.zeros(X.shape[1])
    for _ in range(it):
        z = off + X @ b
        p = 1 / (1 + np.exp(-z))
        W = p * (1 - p)
        g = X.T @ (y - p) - l2 * b
        H = X.T @ (X * W[:, None]) + l2 * np.eye(X.shape[1])
        step = np.linalg.solve(H, g)
        b += step
        if np.abs(step).max() < 1e-6:
            break
    se = np.sqrt(np.diag(np.linalg.inv(H)))
    return b, se


FEATURES = ["repeat_won", "repeat_lost", "streak2", "pref"]
FEATURES_FR = {"repeat_won": N_("the same site after a take they won"), "repeat_lost": N_("the same site after a take they lost"),
               "streak2": N_("the same site after 2 takes in a row or more"), "pref": N_("the site they took most this half")}


def _features(d):
    """+1 pushes toward A, -1 toward B."""
    sgn = np.where(d.prev_site == "A", 1.0, np.where(d.prev_site == "B", -1.0, 0.0))
    won = d.prev_won.fillna(False).astype(bool).values
    tot = (d.nA + d.nB).values.astype(float)
    return np.column_stack([sgn * won, sgn * ~won, sgn * (d.streak.values >= 2),
                            np.where(tot > 0, (d.nA.values - d.nB.values) / np.sqrt(np.maximum(tot, 1)), 0.0)])


def model(df):
    """A or B on the next round: the map's odds for this kind of round, moved by what the T did before (fit on every
    map of the base together, since 'going back after a win' does not depend on the map)."""
    h = df[df.site.isin(["A", "B"]) & df.ctx.notna()].copy()
    if len(h) < 200:
        return None
    base = {}
    for (mp, c), g in h.groupby(["map", "ctx"]):
        base[(mp, c)] = ((g.site == "A").sum() + 3 * (h[h["map"] == mp].site == "A").mean(), len(g) + 3)
    pA = np.array([base[(m, c)][0] / base[(m, c)][1] for m, c in zip(h["map"], h.ctx)])
    off = np.log(pA / (1 - pA))
    X = _features(h)
    y = (h.site == "A").values.astype(float)
    b, se = _fit(X, y, off)
    keep = {k: round(float(v), 3) if abs(v) >= 1.5 * e else 0.0 for k, v, e in zip(FEATURES, b, se)}
    return {"beta": keep, "raw": {k: round(float(v), 3) for k, v in zip(FEATURES, b)}, "se": {k: round(float(v), 3) for k, v in zip(FEATURES, se)},
            "n": int(len(h)), "fr": FEATURES_FR}


TEMPO = ["rush_won", "half_excess"]
TEMPO_FR = {"rush_won": N_("they rushed and won the last round"), "half_excess": N_("they rushed more than usual this half")}


def _rush_rates(df):
    """P(rush) per map, and per map and kind of round (pulled toward the map's rate when there are few rounds)."""
    r_map = df.groupby("map").dyn.agg(lambda s: (s == "rush").mean()).to_dict()
    r_ctx = {}
    for (mp, c), g in df[df.ctx.notna()].groupby(["map", "ctx"]):
        r_ctx[(mp, c)] = float(((g.dyn == "rush").sum() + 10 * r_map[mp]) / (len(g) + 10))
    return r_map, r_ctx


def _tempo_x(d, r_map):
    """The features of the tempo model: a rush they won last round, and how many more rushes than the map's usual
    rate they did in the half so far (0 before the 3rd round of the half)."""
    rm = d["map"].map(r_map).fillna(0.2).to_numpy(dtype=float)
    nb = d.n_before.to_numpy(dtype=float)
    rw = ((d.prev_dyn == "rush") & d.prev_won.fillna(False).astype(bool)).to_numpy(dtype=float)
    ex = np.where(nb >= 2, (d.rush_before.to_numpy(dtype=float) - nb * rm) / np.sqrt(np.maximum(nb, 1)), 0.0)
    return np.column_stack([rw, ex])


def tempo_model(df):
    """Will the T rush this round? The map's rate for this kind of round, moved by what this team did in the half
    (fit on every map together). Rushes do not predict the next site, but a team that rushes keeps rushing."""
    if "dyn" not in df:
        return None
    d = df[(df.n_before >= 1) & df.ctx.notna()]
    if len(d) < 300:
        return None
    r_map, r_ctx = _rush_rates(df)
    p0 = np.clip(np.array([r_ctx[(m, c)] for m, c in zip(d["map"], d.ctx)]), .02, .98)
    off = np.log(p0 / (1 - p0))
    X = _tempo_x(d, r_map)
    y = (d.dyn == "rush").to_numpy(dtype=float)
    b, se = _fit(X, y, off)
    return {"beta": {k: round(float(v), 3) if abs(v) >= 1.5 * e else 0.0 for k, v, e in zip(TEMPO, b, se)},
            "raw": {k: round(float(v), 3) for k, v in zip(TEMPO, b)}, "se": {k: round(float(v), 3) for k, v in zip(TEMPO, se)},
            "n": int(len(d)), "fr": TEMPO_FR}


def alone_gamma(df):
    """A T alone at the first duel (no teammate within 1000 units) is often a lurker or an info player: the team is
    elsewhere. Pooled over every map: how much of the zone's usual lean such a contact keeps
    (1 = the same as a group, 0 = no information, below 0 = the other way)."""
    if "fc_alone" not in df:
        return None
    f = df[df.first_zone.notna() & df.site.isin(["A", "B"]) & df.fc_alone.notna()]
    xs, ys, offs = [], [], []
    lo = lambda p: np.log(p / (1 - p))
    for mp, g in f.groupby("map"):
        alone = g.fc_alone.astype(bool)
        grp = g[~alone]
        if len(grp) < 30:
            continue
        prior = float((grp.site == "A").mean())
        lean = grp.groupby("first_zone").site.agg(lambda s: ((s == "A").sum() + 4 * prior) / (len(s) + 4))
        a = g[alone & g.first_zone.isin(lean.index)]
        if not len(a):
            continue
        pg = a.first_zone.map(lean).clip(.03, .97).to_numpy(dtype=float)
        xs += list(lo(pg) - lo(prior))
        ys += list((a.site == "A").to_numpy(dtype=float))
        offs += [lo(prior)] * len(a)
    if len(xs) < 100:
        return None
    b, se = _fit(np.array(xs)[:, None], np.array(ys), np.array(offs), l2=0.1)
    return {"gamma": round(float(b[0]), 3), "se": round(float(se[0]), 3), "n": len(xs),
            "share": _pct(f.fc_alone.astype(bool).mean())}


def _dyn_after(df):
    """What the same team does on the next round after each kind of attack (every map together)."""
    if "dyn" not in df:
        return None
    d = df[df.prev_dyn.notna() & df.prev_won.notna()]
    if len(d) < 300:
        return None
    rows = []
    for key in ("rush", "fast", "exec", "late", "none"):
        for won in (True, False):
            x = d[(d.prev_dyn == key) & (d.prev_won == won)]
            if len(x) < 40:
                continue
            s = x[x.prev_site.isin(["A", "B"])]
            rows.append({"dyn": key, "won": won, "n": int(len(x)), "rush": _pct((x.dyn == "rush").mean()),
                         "same": _pct((s.site == s.prev_site).mean()) if len(s) >= 30 else None,
                         "other": _pct((s.site.isin(["A", "B"]) & (s.site != s.prev_site)).mean()) if len(s) >= 30 else None})
    lone = []
    for flag in (True, False):
        x = d[(d.prev_lone == flag) & (d.prev_won == False)]
        s = x[x.prev_site.isin(["A", "B"])]
        if len(s) >= 40:
            lone.append({"lone": flag, "n": int(len(s)), "same": _pct((s.site == s.prev_site).mean()), "rush": _pct((x.dyn == "rush").mean())})
    return {"rows": rows, "lone": lone, "base_rush": _pct((d.dyn == "rush").mean()), "dyn_fr": DYN_FR}


def econ_table(df):
    """What the T probably buy, from what the CT side can see: pistol won or lost, last round, losses in a row."""
    out = {}
    d = df[(df.rih >= 3) & df.T_buy.isin(["eco", "force", "full"])]
    for key, sel in (("won", d.prev_won == True), ("lost1", (d.prev_won == False) & (d.losses == 1)),
                     ("lost2", (d.prev_won == False) & (d.losses == 2)), ("lost3", (d.prev_won == False) & (d.losses >= 3))):
        x = d[sel]
        if len(x) >= 20:
            vc = x.T_buy.value_counts(normalize=True)
            out[key] = {k: _pct(vc.get(k, 0.0)) for k in ("eco", "force", "full")}
            out[key]["n"] = int(len(x))
    return out


SUMMARY = os.path.join(config.OUT, "population", "tside_summary.json")
VERSION = 32   # bump when the summary changes shape: the cache is rebuilt


def _stamp():
    try:   # one read of the folder (os.scandir has the dates: no file opened, 15/10)
        with os.scandir(OUT) as it:
            ts = [e.stat().st_mtime for e in it if e.name.endswith(".parquet")]
    except OSError:
        ts = []
    return f"v{VERSION}-{len(ts)}-{int(max(ts, default=0))}"


def tendencies(maps, df=None):
    """Per map: odds by kind of round, habits after a win or a loss, and what the live predictor needs."""
    import json
    if df is not None:
        return _tendencies(maps, df)
    try:
        cur = json.load(open(SUMMARY, encoding="utf-8"))
        from wily.insights import nades
        if nades.fresh(cur.get("_stamp"), _stamp()):   # good until the base grows by 15%
            cur["maps"] = {m: v for m, v in cur["maps"].items() if m in maps}
            return cur
    except (OSError, ValueError):
        pass
    df = load()
    # every map of the base at once: the cache then serves any player, whatever their maps
    res = _tendencies(sorted(set(df["map"].unique()) | set(maps)) if len(df) else maps, df)
    if res:
        tmp = SUMMARY + f".{os.getpid()}.tmp"
        json.dump(dict(res, _stamp=_stamp()), open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
        os.replace(tmp, SUMMARY)   # never a half-written file for the other processes
        res["maps"] = {m: v for m, v in res["maps"].items() if m in maps}
    return res


def _tendencies(maps, df):
    if not len(df):
        return None
    res = {"model": model(df), "econ": econ_table(df), "switch_all": _switch_table(df), "rush_s": RUSH, "late_s": LATE, "maps": {},
           "ctx_fr": CTX_FR, "tempo": tempo_model(df), "alone": alone_gamma(df), "dyn_after": _dyn_after(df), "dyn_fr": DYN_FR}
    r_map, r_ctx = _rush_rates(df) if "dyn" in df else ({}, {})
    dirs = _map_dirs()
    _UW_POOL.clear()
    rot = None
    pool = []
    for mp in maps:
        g = df[df["map"] == mp]
        if len(g) < 60:
            continue
        hits = g[g.site.isin(["A", "B"]) & g.ctx.notna()]
        allA = (hits.site == "A").mean() if len(hits) else 0.5
        ctx = {}
        for c in CONTEXTS:
            x = g[g.ctx == c]
            if len(x) >= 8:
                ctx[c] = _profile(x)
                hx = hits[hits.ctx == c]
                ctx[c]["pA_hit"] = round(float(((hx.site == "A").sum() + 3 * allA) / (len(hx) + 3)), 3)
                if (mp, c) in r_ctx:
                    ctx[c]["rush_p"] = round(r_ctx[(mp, c)], 3)
        res["maps"][mp] = {"n_rounds": int(len(g)), "n_matches": int(g.match.nunique()), "all": _profile(g), "ctx": ctx,
                           "after": _after_table(g), "pA_hit": round(float(allA), 3),
                           "rush_p": round(float(r_map[mp]), 3) if mp in r_map else None}
        try:
            res["maps"][mp]["evidence"] = evidence(mp, g, dirs.get(mp, []), pool)
        except Exception as e:  # the rest of the reading stays usable
            print(f"{mp}: in-round evidence unavailable ({e})")
        try:   # your own spot: a fight there or nothing yet (no click)
            res["maps"][mp]["self"] = _self_evidence(mp, g, dirs.get(mp, []))
        except Exception as e:
            print(f"{mp}: own-spot evidence unavailable ({e})")
        try:   # plays (rush, split, one lane), what the radar needs, rotations of the CTs toward each site
            from wily.insights import lanes as LN
            if rot is None:
                rot = midround.retake_routes()
            res["maps"][mp]["rotations"] = rot.get(mp)
            try:   # each rotation drawn as it is walked (the corridors), not straight between zone centers
                rp = _rot_paths(mp, g, dirs.get(mp, [])) or {}
                for site, by in (res["maps"][mp]["rotations"] or {}).items():
                    for sz, e in by.items():
                        w = (rp.get(site) or {}).get(sz) or {}
                        for r in e.get("routes", []):
                            r["pts"] = w.get(" > ".join(r["route"])) or w.get("*")
            except Exception as e:
                print(f"{mp}: rotation walks unavailable ({e})")
            ls = _lanes().get(mp)
            cz = ((res["maps"][mp].get("evidence") or {}).get("contact") or {}).get("zones")
            res["maps"][mp]["plays"] = LN.summary(g, ls, cz) if ls else None
            res["maps"][mp]["geo"] = LN.radar(LN.geo(), mp)
        except Exception as e:
            print(f"{mp}: plays unavailable ({e})")
        try:   # what the T side can lean on: tempo, fakes, CT setups, rotations, smokes that pay
            res["maps"][mp]["tplan"] = _tplan(mp, g, dirs.get(mp, []), res["maps"][mp])
        except Exception as e:
            print(f"{mp}: T plan unavailable ({e})")
        try:   # the T's ways from their spawn to each site, play by play, with how often the round is won
            res["maps"][mp]["t_routes"] = _t_routes(mp, g, dirs.get(mp, []))
        except Exception as e:
            print(f"{mp}: T routes unavailable ({e})")
        try:   # the plays by economy and by the run before the round; the CTs' spots and kill angles by moment
            res["maps"][mp]["play_ctx"] = _play_ctx(g)
            res["maps"][mp]["ct_spots"] = _ct_spots(mp, dirs.get(mp, []))
            res["maps"][mp]["ct_push"] = _ct_push(mp, dirs.get(mp, []))
            res["maps"][mp]["push_answers"] = _push_answers(mp, g)
            res["maps"][mp]["fakes"] = _fakes(mp, g, dirs.get(mp, []))
            res["maps"][mp]["play_timing"] = _play_timing(g)
            res["maps"][mp]["util_war"] = _util_war(mp, g, dirs.get(mp, []))
            res["maps"][mp]["t_timeline"] = _t_timeline(mp, g, dirs.get(mp, []))
            res["maps"][mp]["setplays"] = _setplays(mp, dirs.get(mp, []))
        except Exception as e:
            print(f"{mp}: play contexts / CT spots unavailable ({e})")
        try:   # after the plant: where the Ts hold in the rounds they win
            res["maps"][mp]["postplant"] = _postplant(mp, dirs.get(mp, []))
        except Exception as e:
            print(f"{mp}: post-plant holds unavailable ({e})")
    try:   # the weapons in key rounds (pistol, eco or force against a full buy), every map together
        res["setplay_w"] = setplay_weapons({m: dirs.get(m, []) for m in maps})
    except Exception as e:
        print(f"key-round weapons unavailable ({e})")
    res["retake_all"] = retake_table(pool)
    try:   # the CTs' blocking utility by the two buys and for a rush; the CTs' buy on the Ts' rush
        res["util_econ"] = _util_econ(_UW_POOL)
        res["rush_ct"] = _rush_ct(df)
    except Exception as e:
        print(f"utility by economy unavailable ({e})")
    try:   # situations measured on all maps together (pistol as CT for now)
        res["situations"] = _situations(df, res["maps"])
    except Exception as e:
        print(f"situations unavailable ({e})")
    return res

# ---------- evidence during the round: what the CT side sees, and what it says about the site ----------
WINDOWS = [("early", 0, 20), ("setup", 20, 40), ("hit", 40, 70), ("late", 70, 999)]
STEP = 5


def _map_dirs():
    by = {}
    if not os.path.isdir(config.DEEP):   # a fresh install before its first analysis: no match yet
        return by
    from wily.core import ledger
    facts = ledger.match_facts()   # 15/10: not the 5,000 meta.json read again
    for mid in os.listdir(config.DEEP):
        m = (facts.get(mid) or {}).get("map")
        if m:
            by.setdefault(m, []).append(os.path.join(config.DEEP, mid))
    return by


def _survival(g):
    """Chance that no site has been taken yet at t seconds, for each place the attack ends up going.
    The longer a round goes quiet, the more the late option becomes likely: this is the likelihood of 'still nothing'."""
    ts = list(range(0, 101, STEP))
    out = {"t": ts}
    for site in ("A", "B", "-"):
        x = g[g.site == site]
        if len(x) < 10:
            continue
        if site == "-":
            c = x.end_t.fillna(ROUND_TIME).to_numpy(dtype=float)
        else:
            c = np.where(x.entered.to_numpy(dtype=bool), x.hit_t.to_numpy(dtype=float), x.stop_t.to_numpy(dtype=float))
            c = np.where(np.isnan(c), ROUND_TIME, c)
        out["none" if site == "-" else site] = [round(float((c > t).mean()) + 1e-3, 4) for t in ts]
    return out


def _contact(g, top=8):
    """Where the first duel of the round happens, for each place the attack ends up going (smoothed)."""
    f = g[g.first_zone.notna()]
    if len(f) < 30:
        return None
    zones = f.first_zone.value_counts().head(top).index.tolist()
    res = {"zones": zones, "lik": {}, "lik_g": {}, "t": {}}
    # lik: every first duel; lik_g: only the ones where the T had a teammate close (the user said "2+ Ts")
    grp = f[f.fc_alone.notna() & ~f.fc_alone.fillna(False).astype(bool)] if "fc_alone" in f else f.iloc[0:0]
    for key, src in (("lik", f), ("lik_g", grp)):
        for site in ("A", "B", "-"):
            x = src[src.site == site]
            if len(x) < 10:
                continue
            vc = x.first_zone.where(x.first_zone.isin(zones), "other").value_counts()
            tot = len(x) + len(zones) + 1
            res[key]["none" if site == "-" else site] = {z: round(float((vc.get(z, 0) + 1) / tot), 4) for z in zones + ["other"]}
    for z in zones:
        res["t"][z] = _timer(f[f.first_zone == z].first_t.median())
    return res


def _compass(dx, dy):
    if (dx * dx + dy * dy) ** 0.5 < 14:
        return "center"
    a = np.degrees(np.arctan2(-dy, dx)) % 360   # radar: y goes down
    return ["east", "north-east", "north", "north-west", "west", "south-west", "south", "south-east"][int(((a + 22.5) % 360) // 45)]


def _plants_and_retakes(mp, dirs):
    """Where the bomb goes down on each site (spots on the radar), how the round ends from there, and how often the
    CT side wins the retake by the number of players alive on each side when the bomb is planted."""
    from sklearn.cluster import DBSCAN
    from wily.demos.map_analysis import ZoneMap
    try:
        zm = ZoneMap(mp)
    except Exception:
        return None, None, None
    sites = midround.site_centers().get(mp) or {}
    rows = []
    for d in dirs:
        fr = os.path.join(d, "rounds.parquet")
        if not os.path.exists(fr):
            continue
        R = pd.read_parquet(fr)
        if not five_v_five(R) or "plant_X" not in R:
            continue
        P = R[R.plant_site.isin(["A", "B"]) & R.plant_X.notna() & R.plant_t.notna()]
        if not len(P):
            continue
        fd = os.path.join(d, "duels.parquet")
        D = pd.read_parquet(fd, columns=["round", "t", "victim_side"]) if os.path.exists(fd) else pd.DataFrame(columns=["round", "t", "victim_side"])
        for _, r in P.iterrows():
            dd = D[(D["round"] == r["round"]) & (D.t < r.plant_t)]
            rows.append({"site": r.plant_site, "x": float(r.plant_X), "y": float(r.plant_Y), "t": float(r.plant_t), "win_t": r.winner == "T",
                         "ct": int(r.CT_n) - int((dd.victim_side == "CT").sum()), "tt": int(r.T_n) - int((dd.victim_side == "T").sum())})
    if len(rows) < 20:
        return None, None, None
    df = pd.DataFrame(rows)
    px, py = zm.px(df.x.to_numpy(), df.y.to_numpy())
    df["px"], df["py"] = np.asarray(px, dtype=float), np.asarray(py, dtype=float)
    plants, retakes = {}, {}
    for site, g in df.groupby("site"):
        c = sites.get(site, {}).get("c")
        level = zm.level(c[2])[0] if c else None
        cx, cy = (np.asarray(zm.px([c[0]], [c[1]])[0])[0], np.asarray(zm.px([c[0]], [c[1]])[1])[0]) if c else (g.px.median(), g.py.median())
        lab = DBSCAN(eps=16, min_samples=max(3, int(0.04 * len(g)))).fit(g[["px", "py"]].to_numpy()).labels_
        g = g.assign(cl=lab)
        spots = []
        for k, s in g[g.cl >= 0].groupby("cl"):
            mx, my = float(s.px.mean()), float(s.py.mean())
            spots.append({"n": int(len(s)), "share": round(100 * len(s) / len(g)), "px": [round(mx), round(my)], "level": level,
                          "where": _compass(mx - cx, my - cy), "timer": _timer(s.t.median()), "t_win": round(100 * float(s.win_t.mean()))})
        spots.sort(key=lambda x: -x["n"])
        plants[site] = {"n": int(len(g)), "timer": _timer(g.t.median()), "t_win": round(100 * float(g.win_t.mean())), "spots": spots[:3],
                        "t_q": [round(float(g.t.quantile(q)), 1) for q in (0.25, 0.5, 0.75)]}
        rt = []
        for (ct, tt), s in g.groupby(["ct", "tt"]):
            if len(s) >= 6 and ct >= 1 and tt >= 1:
                rt.append({"ct": int(ct), "t": int(tt), "n": int(len(s)), "ct_win": round(100 * (1 - float(s.win_t.mean())))})
        retakes[site] = sorted(rt, key=lambda x: (-x["ct"], x["t"]))
    return plants, retakes, df[["ct", "tt", "win_t"]]


def _deaths(mp, dirs, site_of):
    """Where the players of each side die, by moment of the round, overall and when the attack goes A or B."""
    rows = []
    for d in dirs:
        fd = os.path.join(d, "duels.parquet")
        fr = os.path.join(d, "rounds.parquet")
        if not os.path.exists(fd) or not os.path.exists(fr):
            continue
        R = pd.read_parquet(fr, columns=["T_n", "CT_n"])
        if not five_v_five(R):
            continue
        mid = os.path.basename(d)
        D = pd.read_parquet(fd, columns=["round", "t", "victim_side", "victim_zone"])
        D = D.assign(site=[site_of.get((mid, int(r)), "-") for r in D["round"]])
        rows.append(D)
    if not rows:
        return None
    df = pd.concat(rows, ignore_index=True)
    df = df[df.victim_zone.notna() & (df.victim_zone != "?")]
    df["w"] = pd.cut(df.t, [lo for _, lo, _ in WINDOWS] + [999], labels=[k for k, _, _ in WINDOWS], right=False)
    out = {}
    for side, g in df.groupby("victim_side"):
        if side not in ("T", "CT"):
            continue
        res = {}
        for key, sel in (("all", slice(None)), ("A", g.site == "A"), ("B", g.site == "B")):
            x = g[sel] if key != "all" else g
            wins = {}
            for w, xw in x.groupby("w", observed=True):
                if len(xw) < 15:
                    continue
                vc = xw.victim_zone.value_counts(normalize=True).head(3)
                wins[str(w)] = {"n": int(len(xw)), "zones": [{"zone": humanize(z, mp), "pct": _pct(p)} for z, p in vc.items()]}
            res[key] = wins
        out[side] = res
    return out


MULTI_R = 45   # radar pixels: two kills of a round from closer than this are "from the same spot"


def multi_events(kills):
    """Multi-kills from one spot: kills of one player in one round (sorted by time), grouped while they come from
    within MULTI_R of the first one. kills: dicts with px, level, t, zone. Returns the groups of 2 kills or more."""
    out, cur = [], []
    for k in sorted(kills, key=lambda k: k["t"]):
        if cur and (k["level"] != cur[0]["level"] or np.hypot(k["px"][0] - cur[0]["px"][0], k["px"][1] - cur[0]["px"][1]) > MULTI_R):
            out.append(cur) if len(cur) >= 2 else None
            cur = []
        cur.append(k)
    if len(cur) >= 2:
        out.append(cur)
    return [{"px": [float(np.mean([k["px"][0] for k in e])), float(np.mean([k["px"][1] for k in e]))], "level": e[0]["level"],
             "n": len(e), "t": float(e[0]["t"]), "zone": max(sorted(set(k["zone"] for k in e), key=str), key=[k["zone"] for k in e].count)} for e in out]


def multi_spots(events, r=30, top=12, min_n=1):
    """The multi-kill events grouped by spot (same level, within r pixels of the group's center): where on the radar
    players got 2+ kills from the same place, the most frequent first."""
    cl = []
    for e in sorted(events, key=lambda e: -e["n"]):
        c = next((c for c in cl if c["level"] == e["level"] and np.hypot(c["x"] / c["n"] - e["px"][0], c["y"] / c["n"] - e["px"][1]) <= r), None)
        if c is None:
            c = {"level": e["level"], "x": 0.0, "y": 0.0, "n": 0, "best": 0, "ts": [], "zones": []}
            cl.append(c)
        c["x"] += e["px"][0]
        c["y"] += e["px"][1]
        c["n"] += 1
        c["best"] = max(c["best"], e["n"])
        c["ts"].append(e["t"])
        c["zones"].append(e["zone"])
    cl = [c for c in cl if c["n"] >= min_n]
    cl.sort(key=lambda c: (-c["n"], -c["best"]))
    return [{"px": [round(c["x"] / c["n"]), round(c["y"] / c["n"])], "level": c["level"], "n": c["n"], "best": c["best"],
             "t_med": round(float(np.median(c["ts"]))), "zone": max(sorted(set(c["zones"]), key=str), key=c["zones"].count)} for c in cl[:top]]   # ties: one order


def _t_routes(mp, g, dirs, top=2):
    """T side, per play: the ways the players of the base walk from their spawn to the site, the most taken first, each
    drawn as the walk of one real player (the most typical of the ones who took that way: the medoid), with when they
    pass there, and how often the round is won when one takes it."""
    play_of = {(str(m), int(r)): (p, w) for m, r, p, w in zip(g.match, g["round"], g.play, g.T_won) if isinstance(p, str) and p != "none"}
    if not play_of:
        return None
    ways = {}
    for d in dirs:
        mid = os.path.basename(d)
        f = os.path.join(d, "samples.parquet")
        if not os.path.exists(f):
            continue
        S = pd.read_parquet(f, columns=["steamid", "side", "round", "t", "px", "py", "level", "zone", "health"])
        S = S[(S.side == "T") & S.px.notna()].sort_values("t")
        for (rnd, sid), x in S.groupby(["round", "steamid"]):
            pw = play_of.get((mid, int(rnd)))
            if not pw:
                continue
            play, won = pw
            target = "Bombsite" + (play[-1] if play.startswith(("rush", "split")) else play[0])
            zs, pts = [], []
            for z, t, px_, py_, lv, hp in zip(x.zone, x.t, x.px, x.py, x.level, x.health):
                if hp is not None and hp <= 0:
                    break
                pts.append((float(px_), float(py_), lv, float(t)))
                if isinstance(z, str) and z and (not zs or zs[-1] != z):
                    if z in zs:   # back to a zone already passed: the loop is cut
                        zs = zs[:zs.index(z) + 1]
                    else:
                        zs.append(z)
                if zs and zs[-1] == target:
                    break
            if len(zs) < 3 or zs[-1] != target or len(pts) < 4:
                continue
            e = ways.setdefault((play, tuple(zs)), {"r": set(), "w": set(), "tr": []})
            e["r"].add((mid, int(rnd)))
            if won:
                e["w"].add((mid, int(rnd)))
            if len(e["tr"]) < 80:
                e["tr"].append(pts)

    def resample(pts, k=60):
        xy = np.array([[p[0], p[1]] for p in pts])
        d = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
        if d[-1] <= 0:
            return None
        s = np.linspace(0, d[-1], k)
        idx = np.clip(np.searchsorted(d, s), 0, len(pts) - 1)
        return np.c_[np.interp(s, d, xy[:, 0]), np.interp(s, d, xy[:, 1])], [pts[i][2] for i in idx], [pts[i][3] for i in idx]

    out = {}
    for play in sorted({p for p, _ in ways}):
        best = sorted(((zs, e) for (p, zs), e in ways.items() if p == play), key=lambda kv: -len(kv[1]["r"]))[:top]
        res = []
        for zs, e in best:
            if len(e["r"]) < 4:
                continue
            rs = [r for r in (resample(t) for t in e["tr"]) if r is not None]
            if not rs:
                continue
            A = np.array([r[0] for r in rs])
            med = int(np.argmin([np.mean(np.hypot(*(A - a).transpose(2, 0, 1))) for a in A]))   # the most typical walk
            xy, lv, ts = rs[med]
            sm = xy.copy()   # a light smoothing (3 points) that keeps the corridor: the player's wobble goes, the corners stay
            sm[1:-1] = (xy[:-2] + xy[1:-1] + xy[2:]) / 3
            xy = sm
            res.append({"n": len(e["r"]), "win": round(100 * len(e["w"]) / len(e["r"])), "zones": [humanize(z, mp) for z in zs],
                        "pts": [[round(float(a)), round(float(b)), l, round(float(t))] for (a, b), l, t in zip(xy, lv, ts)]})
        if res:
            out[play] = res
    return out or None


def _walk_medoid(paths, k=40):
    """The most typical of several walks (the medoid, resampled along its length), lightly smoothed: the player's
    wobble goes, the corners of the corridor stay. Each point: x, y, level."""
    def resample(pts):
        xy = np.array([[p[0], p[1]] for p in pts])
        d = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
        if d[-1] <= 0:
            return None
        u = np.linspace(0, d[-1], k)
        idx = np.clip(np.searchsorted(d, u), 0, len(pts) - 1)
        return np.c_[np.interp(u, d, xy[:, 0]), np.interp(u, d, xy[:, 1])], [pts[i][2] for i in idx]
    rs = [r for r in (resample(p) for p in paths if len(p) >= 3) if r is not None]
    if not rs:
        return None
    A = np.array([r[0] for r in rs])
    xy, lv = rs[int(np.argmin([np.mean(np.hypot(*(A - a).transpose(2, 0, 1))) for a in A]))]
    sm = xy.copy()
    sm[1:-1] = (xy[:-2] + xy[1:-1] + xy[2:]) / 3
    return [[round(float(a)), round(float(b)), l] for (a, b), l in zip(sm, lv)]


def _rot_paths(mp, g, dirs):
    """CT rotations as walked: in the rounds the Ts hit a site (after 20 s, not a rush), each CT away from it who goes
    there and makes it: his walk from the moment he leaves to the site. Grouped like the rotation stats (site, start
    zone, first 3 zones of the route), the most typical walk of each group."""
    sites = midround.site_centers().get(mp)
    hits = {(str(m), int(r)): (st, float(t)) for m, r, st, t in zip(g.match, g["round"], g.site, g.hit_t)
            if st in ("A", "B") and t == t and t is not None and t >= 20}
    if not sites or not hits:
        return None
    walks = {}
    for d in dirs:
        mid = os.path.basename(d)
        f = os.path.join(d, "samples.parquet")
        if not os.path.exists(f):
            continue
        S = pd.read_parquet(f, columns=["steamid", "side", "round", "t", "X", "Y", "Z", "px", "py", "level", "zone", "health"])
        S = S[(S.side == "CT") & S.px.notna() & (S.health > 0)].sort_values("t")
        for (rnd, sid), x in S.groupby(["round", "steamid"]):
            h = hits.get((mid, int(rnd)))
            if not h:
                continue
            site, hit_t = h
            other = "B" if site == "A" else "A"
            cS, rS = sites[site]["c"], sites[site]["r"] * 1.3
            cO, rO = sites[other]["c"], sites[other]["r"] * 2.0
            before = x[x.t <= hit_t]
            if not len(before):
                continue
            p0 = before.iloc[-1]
            d0S = float(midround._dist(p0.X, p0.Y, p0.Z, cS))
            d0O = float(midround._dist(p0.X, p0.Y, p0.Z, cO))
            region = "site" if d0S <= rS else ("other" if d0O <= rO and d0O < d0S else "mid")
            if region == "site" or (region == "mid" and d0S <= rS * 2.5):
                continue
            w = x[x.t >= max(hit_t - 10, 15)]
            if len(w) < 3:
                continue
            dd = midround._dist(w.X.values, w.Y.values, w.Z.values, cS)
            if dd[0] - dd.min() < max(700.0, 0.35 * (dd[0] - rS)):
                continue
            j = int(np.argmax(dd <= dd[0] - 250)) if (dd <= dd[0] - 250).any() else 0
            arr = np.where((dd <= rS) & (np.arange(len(dd)) >= j))[0]
            if not len(arr):
                continue
            a = int(arr[0])
            route = midround._route(list(w.zone.values[j:a + 1]))
            key = " > ".join(humanize(z, mp) for z in route[:3])
            sz = humanize(p0.zone, mp) if isinstance(p0.zone, str) else None
            if not sz:
                continue
            pts = [(float(px_), float(py_), lv) for px_, py_, lv in zip(w.px.values[max(0, j - 2):a + 1], w.py.values[max(0, j - 2):a + 1], w.level.values[max(0, j - 2):a + 1])]
            e = walks.setdefault(site, {}).setdefault(sz, {})
            for k_ in (key, "*"):   # the route's own walks, and every walk from this zone (a route without enough)
                lst = e.setdefault(k_, [])
                if len(lst) < 60:
                    lst.append(pts)
    out = {}
    for site, by in walks.items():
        for sz, routes in by.items():
            for k_, paths in routes.items():
                if len(paths) >= 2:
                    m = _walk_medoid(paths)
                    if m:
                        out.setdefault(site, {}).setdefault(sz, {})[k_] = m
    return out or None


def _play_timing(g, bw=7.0, k=8.0, min_n=10.0):
    """Each play: when to be on the site to win the most rounds, at equal numbers. A fast arrival often comes with a
    round where nobody died on the way (an easy round): the raw curve favours rushes. So the numbers alive at the hit
    are taken out first (the map's rounds won by man difference at the hit, T alive minus CT alive); around each
    moment (every round weighted by how close its arrival is, 7 s), what the rounds won beyond their numbers say, pulled
    toward the play's average when few rounds are around; the best moment with at least 10 rounds' worth. Pistol rounds
    apart (another tempo). -> {play: {"pistol"|"other": {best, lo, hi, win, mean, n, curve}}}"""
    x = g[g.hit_t.notna() & g.play.notna() & (g.play != "none") & g.t_alive_hit.notna() & g.ct_alive_hit.notna()].copy()
    if not len(x):
        return None
    x["d"] = (x.t_alive_hit - x.ct_alive_hit).clip(-3, 3)
    out = {}
    for grp, xs in (("pistol", x[x.T_buy == "pistol"]), ("other", x[x.T_buy != "pistol"])):
        ref = xs if len(xs) >= 60 else x
        adv = ref.groupby("d").T_won.mean()
        for play, q in xs.groupby("play"):
            if len(q) < 15:
                continue
            t, y = q.hit_t.to_numpy(float), q.T_won.astype(float).to_numpy()
            r = y - q.d.map(adv).fillna(float(ref.T_won.mean())).to_numpy(float)   # beyond what the numbers give
            m = float(y.mean())
            base = m + float(r.sum()) / (len(r) + k)   # the play's level on the same scale (beyond the numbers)
            best, curve = None, []
            for c in np.arange(8, 106, 1.0):
                w = np.exp(-0.5 * ((t - c) / bw) ** 2)
                ne = float(w.sum())
                if ne < min_n:
                    continue
                v = m + float((w * r).sum()) / (ne + k)
                if c % 5 == 0:
                    curve.append([int(c), round(100 * v)])   # the whole curve (every 5 s): what the In game panel draws
                if c <= 100 and (best is None or v > best[1]):
                    best = (float(c), v, ne)
            if best:
                c, v, ne = best
                out.setdefault(play, {})[grp] = {"best": round(c, 1), "lo": round(max(0.0, c - 5), 1), "hi": round(c + 5, 1),
                                                 "win": round(100 * v), "mean": round(100 * base), "n": int(round(ne)), "curve": curve}
    return out or None


UTIL_DUR = {"molotov": 7.0, "smoke": 18.0}   # a molotov burns about 7 s, a smoke stays about 18 s
_UW_POOL = []   # the hits of every map, for _util_econ


def _util_econ(hits):
    """Every map together: the Ts' rounds won on a hit that meets the CTs' blocking utility still active, after it is
    spent, or with none thrown before, at equal numbers alive, by the Ts' buy (eco or force: "low"; full), by the CTs'
    buy, and for a rush or not. Against a force-buy or a rush, a molotov or smoke on the hit costs the Ts much more."""
    if not hits:
        return None
    H = pd.DataFrame(hits)
    H = H[H.d.notna()]
    out = {}
    for key, sel in (("T_low", H.tb == "low"), ("T_full", H.tb == "full"), ("CT_low", H.cb == "low"), ("CT_full", H.cb == "full"),
                     ("rush", H.rush.astype(bool)), ("slow", ~H.rush.astype(bool))):
        h = H[sel]
        if len(h) < 100:
            continue
        adv = h.groupby("d").won.mean()
        res = h.won - h.d.map(adv)
        base = float(h.won.mean())
        out[key] = {c: [int(len(x)), round(100 * (base + float(res[x.index].mean())))] for c, x in h.groupby("cat") if len(x) >= 40}
    return out or None


def _rush_ct(df):
    """How the CTs' buy moves the Ts' rush (logit shifts on the map's rate for the Ts' buy, every map together; kept
    when clear of the noise): Ts rush far more into CTs on an eco. Pistol rounds and round 2 aside (their kind of
    round already says the CTs' buy)."""
    if "dyn" not in df or "CT_buy" not in df:
        return None
    r_map, r_ctx = _rush_rates(df)
    d = df[df.ctx.isin(["eco", "force", "full"]) & df.CT_buy.isin(["eco", "force", "full"])]
    if len(d) < 500:
        return None
    p0 = np.clip(np.array([r_ctx[(m, c)] for m, c in zip(d["map"], d.ctx)]), .02, .98)
    X = np.column_stack([(d.CT_buy == b).to_numpy(dtype=float) for b in ("eco", "force", "full")])
    y = (d.dyn == "rush").to_numpy(dtype=float)
    b, se = _fit(X, y, np.log(p0 / (1 - p0)))
    return {k: round(float(v), 3) if abs(v) >= 1.5 * e else 0.0 for k, v, e in zip(("eco", "force", "full"), b, se)}


def _util_war(mp, g, dirs):
    """Around each site: the CTs' blocking utility on the way to it (their molotovs and smokes landing on that side of
    the map), and what it does to the hits there. A hit while one is still burning or standing ("active"), after the
    last one ended ("spent"), or with none thrown before ("kept"): the rounds won by the Ts, at equal numbers alive at
    the hit (the map's rounds won by man difference taken out). For each usual one (type, where it lands): how often,
    when it is thrown and when it ends, the Ts killed within 500 units of it in the next 8 s, its thrower alive 10 s
    later, and the Ts' rounds won when a hit meets it active. Pistol rounds aside."""
    from wily.coaching import team
    regions = (team.map_meta().get(mp) or {}).get("regions") or {}
    reg = lambda z: "A" if z == "BombsiteA" else "B" if z == "BombsiteB" else regions.get(z)
    rows = {(str(m), int(r)): x for m, r, x in zip(g.match, g["round"], g.itertuples()) if x.T_buy != "pistol"}
    ectx = lambda b: "pistol" if b == "pistol" else "full" if b == "full" else "low"
    n_ctx = {}
    for x in rows.values():
        n_ctx[ectx(x.CT_buy)] = n_ctx.get(ectx(x.CT_buy), 0) + 1
    hits, util = [], []
    for d in dirs:
        mid = os.path.basename(d)
        fg, fd = os.path.join(d, "grenades.parquet"), os.path.join(d, "duels.parquet")
        if not os.path.exists(fg):
            continue
        G = read_nades(fg, columns=["round", "t", "type", "side", "thrower", "land_X", "land_Y", "land_px", "land_py", "land_level", "land_zone"])
        G = G[(G.side == "CT") & G.type.isin(list(UTIL_DUR)) & (G.t <= 75)]
        D = pd.read_parquet(fd, columns=["round", "t", "victim", "victim_side", "victim_X", "victim_Y"]) if os.path.exists(fd) else pd.DataFrame()
        for (mid_r, x) in ((k, v) for k, v in rows.items() if k[0] == mid):
            rnd = mid_r[1]
            ct = G[G["round"] == rnd]
            ct = ct.assign(region=ct.land_zone.map(reg), end=ct.t + ct.type.map(UTIL_DUR))
            h = float(x.hit_t) if x.site in ("A", "B") and x.hit_t == x.hit_t else None
            if h is not None:
                on = ct[(ct.region == x.site) & (ct.t <= h)]
                cat = "active" if ((on.end >= h)).any() else "spent" if len(on) else "kept"
                hits.append({"site": x.site, "cat": cat, "won": bool(x.T_won), "tb": ectx(x.T_buy), "cb": ectx(x.CT_buy), "rush": x.dyn == "rush",
                             "d": float(np.clip(x.t_alive_hit - x.ct_alive_hit, -3, 3)) if x.t_alive_hit == x.t_alive_hit and x.ct_alive_hit == x.ct_alive_hit else np.nan})
            dr = D[(D["round"] == rnd)] if len(D) else D
            for u in ct.itertuples():
                if u.region not in ("A", "B"):
                    continue
                near = after = 0
                if len(dr):
                    w = dr[(dr.victim_side == "T") & (dr.t >= u.t) & (dr.t <= u.t + 8)]
                    near = int((np.hypot(w.victim_X - u.land_X, w.victim_Y - u.land_Y) < 500).sum())
                    after = bool(((dr.victim == u.thrower) & (dr.t >= u.t) & (dr.t <= u.t + 10)).any())
                util.append({"site": u.region, "type": u.type, "land": humanize(u.land_zone, mp) if isinstance(u.land_zone, str) else None,
                             "t": float(u.t), "px": float(u.land_px), "py": float(u.land_py), "level": u.land_level, "near": near,
                             "alive": not after, "key": (mid, rnd), "ctx": ectx(x.CT_buy),
                             "met": h is not None and x.site == u.region and u.t <= h <= u.t + UTIL_DUR[u.type], "won": bool(x.T_won)})
    if not hits:
        return None
    _UW_POOL.extend(hits)
    H = pd.DataFrame(hits)
    H = H[H.d.notna()]
    adv = H.groupby("d").won.mean()
    H["res"] = H.won - H.d.map(adv)
    base = float(H.won.mean())
    U = pd.DataFrame(util) if util else pd.DataFrame(columns=["site"])
    n_rounds = len(rows)
    out = {}
    for site in ("A", "B"):
        h = H[H.site == site]
        if len(h) < 30:
            continue
        cats = {c: [int(len(x)), round(100 * (base + float(x.res.mean())))] for c, x in h.groupby("cat") if len(x) >= 10}
        u = U[U.site == site] if len(U) else U
        items = []
        for (ty, la), x in (u.groupby(["type", "land"]) if len(u) else []):
            rounds = x.key.nunique()
            if rounds < 8:
                continue
            met = x[x.met]
            items.append({"type": ty, "land": la, "share": round(100 * rounds / max(1, n_rounds)), "t": round(float(x.t.median()), 1),
                          "end": round(float(x.t.median()) + UTIL_DUR[ty], 1), "near": round(float(x.near.mean()), 2),
                          "alive": round(100 * float(x.alive.mean())), "px": [round(float(x.px.median())), round(float(x.py.median()))],
                          "level": x.level.mode().iloc[0] if x.level.notna().any() else None,
                          "met_n": int(len(met)), "met_t_won": round(100 * float(met.won.mean())) if len(met) >= 8 else None,
                          "ctx": {c: round(100 * x[x.ctx == c].key.nunique() / n) for c, n in n_ctx.items() if n >= 20}})   # their buy
        items.sort(key=lambda z: -z["share"])
        out[site] = {"hits": cats, "n": int(len(h)), "util": items[:5]}
    return out or None


T_UTIL_DUR = {"smoke": 18.0, "molotov": 7.0, "flash": 2.0, "he": 1.0}


def _t_timeline(mp, g, dirs):
    """For the CT side, per T economy (pistol, eco or force, full buy): when the Ts are on each site (the rounds where
    they take it around each moment, every 5 s, as a share of the rounds), and their utility landing on that side of
    the map before the hit (type, where it lands, how often, when it is thrown, how long it lasts)."""
    from wily.coaching import team
    regions = (team.map_meta().get(mp) or {}).get("regions") or {}
    reg = lambda z: "A" if z == "BombsiteA" else "B" if z == "BombsiteB" else regions.get(z)
    ctx = lambda b: "pistol" if b == "pistol" else "full" if b == "full" else "low"
    g = g.assign(ctx=g.T_buy.map(ctx))
    rows = {(str(m), int(r)): x for m, r, x in zip(g.match, g["round"], g.itertuples())}
    tu = []
    for d in dirs:
        mid = os.path.basename(d)
        fg = os.path.join(d, "grenades.parquet")
        if not os.path.exists(fg):
            continue
        G = read_nades(fg, columns=["round", "t", "type", "side", "land_zone"])
        G = G[(G.side == "T") & (G.t <= 80)]
        for u in G.itertuples():
            x = rows.get((mid, int(u.round)))
            r_ = reg(u.land_zone)
            if x is None or r_ not in ("A", "B") or (x.hit_t == x.hit_t and u.t > x.hit_t):
                continue
            tu.append({"ctx": x.ctx, "site": r_, "type": u.type, "land": humanize(u.land_zone, mp) if isinstance(u.land_zone, str) else None,
                       "t": float(u.t), "key": (mid, int(u.round))})
    U = pd.DataFrame(tu) if tu else pd.DataFrame(columns=["ctx", "site", "type", "land", "t", "key"])
    out = {}
    for c, gc in g.groupby("ctx"):
        n = len(gc)
        if n < 30:
            continue
        e = {"n": int(n)}
        for site in ("A", "B"):
            h = gc[(gc.site == site) & gc.hit_t.notna()].hit_t.to_numpy(float)
            curve = [[t0, round(100 * float(((h >= t0 - 5) & (h < t0 + 5)).sum()) / n, 1)] for t0 in range(5, 106, 5)]
            u = U[(U.ctx == c) & (U.site == site)]
            items = []
            for (ty, la), x in (u.groupby(["type", "land"]) if len(u) else []):
                rr = x.key.nunique()
                if rr >= 6 and 100 * rr / n >= 5:
                    items.append({"type": ty, "land": la, "share": round(100 * rr / n), "t": round(float(x.t.median()), 1),
                                  "end": round(float(x.t.median()) + T_UTIL_DUR.get(ty, 2.0), 1)})
            items.sort(key=lambda z: -z["share"])
            e[site] = {"share": round(100 * len(h) / n), "curve": curve, "util": items[:4]}
        out[c] = e
    return out or None


def _momentum(g):
    """For every round: the T side's run before it in the half (w2 = won the last 2+, w1, l1, l2 = lost 2-3, l4 = 4+)."""
    out = {}
    for (m, h), x in g.sort_values("round").groupby(["match", "half"]):
        run = 0
        for r, won in zip(x["round"], x.T_won):
            out[(m, int(r))] = "w2" if run >= 2 else "w1" if run == 1 else "l1" if run == -1 else "l4" if run <= -4 else "l2" if run <= -2 else "-"
            run = (max(run, 0) + 1) if won else (min(run, 0) - 1)
    return out


def _play_ctx(g):
    """The plays' rounds won by economy (T buy | CT buy) and by the T's run before the round: what the live page needs
    to rank the plays for the round being played, not for an average round. The run is measured beyond the economy
    (rounds won against the rounds the two buys predicted), since a run of wins mostly means the other side is broke."""
    mo = _momentum(g)
    g = g.assign(mo=[mo.get((m, int(r)), "-") for m, r in zip(g.match, g["round"])])
    allp = float(g.T_won.mean()) if len(g) else 0.5
    mr = {k: (float(x.T_won.sum()) + 10 * allp) / (len(x) + 10) for k, x in g.groupby(["T_buy", "CT_buy"])}
    g = g.assign(ex=[mr.get((a, b), allp) for a, b in zip(g.T_buy, g.CT_buy)])
    p = g[g.play.notna()]
    mu, mm = {}, {}
    for (pl, tb, cb), x in p.groupby(["play", "T_buy", "CT_buy"]):
        mu.setdefault(pl, {})[f"{tb}|{cb}"] = [int(len(x)), int(x.T_won.sum())]
    for (pl, b), x in p.groupby(["play", "mo"]):
        mm.setdefault(pl, {})[b] = [int(len(x)), int(x.T_won.sum()), round(float(x.ex.sum()), 2)]
    allmo = {b: [int(len(x)), int(x.T_won.sum()), round(float(x.ex.sum()), 2)] for b, x in p.groupby("mo")}
    mx = {f"{a}|{b}": [int(len(x)), int(x.T_won.sum())] for (a, b), x in g.groupby(["T_buy", "CT_buy"])}   # the map's rounds by economy
    return {"mu": mu, "mo": mm, "mo_all": allmo, "mx": mx, "all": [int(len(p)), int(p.T_won.sum())]}


def _ct_spots(mp, dirs, cell=26):
    """What the T side meets, by moment of the round: where the CTs stand most (share of their time), and where they
    kill the Ts from (with the spots where they kill a lot for the little time they spend there: the angles the Ts
    forget to check)."""
    pres, kills = [], []
    for d in dirs[:60]:
        fs, fd = os.path.join(d, "samples.parquet"), os.path.join(d, "duels.parquet")
        if not os.path.exists(fs) or not os.path.exists(fd):
            continue
        S = pd.read_parquet(fs, columns=["side", "t", "px", "py", "level", "zone", "health"])
        pres.append(S[(S.side == "CT") & S.px.notna() & (S.health > 0)][["t", "px", "py", "level", "zone"]])
        D = pd.read_parquet(fd, columns=["t", "killer_side", "victim_side", "killer_px", "killer_py", "killer_level", "killer_zone"])
        kills.append(D[(D.killer_side == "CT") & (D.victim_side == "T") & D.killer_px.notna()])
    if not pres or not kills:
        return None
    P, K = pd.concat(pres, ignore_index=True), pd.concat(kills, ignore_index=True)
    edges, names = [lo for _, lo, _ in WINDOWS] + [999], [k for k, _, _ in WINDOWS]
    P["w"], K["w"] = pd.cut(P.t, edges, labels=names, right=False), pd.cut(K.t, edges, labels=names, right=False)
    P["c"] = list(zip(P.level, (P.px // cell).astype(int), (P.py // cell).astype(int)))
    K["c"] = list(zip(K.killer_level, (K.killer_px // cell).astype(int), (K.killer_py // cell).astype(int)))
    out = {}
    for w in names:
        p, k = P[P.w == w], K[K.w == w]
        if len(p) < 200 or len(k) < 30:
            continue
        pc, kc = p.groupby("c"), k.groupby("c")
        share = pc.size() / len(p)
        hold = []
        for c, n in share.sort_values(ascending=False).items():   # the CTs' spots now, not two in the same place
            x = pc.get_group(c)
            pt = (float(x.px.mean()), float(x.py.mean()))
            if any(h["level"] == c[0] and np.hypot(h["px"][0] - pt[0], h["px"][1] - pt[1]) < 2.2 * cell for h in hold):
                continue
            hold.append({"px": [round(pt[0]), round(pt[1])], "level": c[0], "share": round(100 * float(n), 1), "zone": humanize(x.zone.mode().iloc[0], mp) if x.zone.notna().any() else None})
            if len(hold) == 8:
                break
        danger = []
        avg = len(k) / max(1, len(p))
        for c, x in kc:
            if len(x) < 6:
                continue
            seen = int(share.get(c, 0) * len(p))
            rate = len(x) / max(seen, 1)   # kills for the CT time spent there
            danger.append({"px": [round(float(x.killer_px.mean())), round(float(x.killer_py.mean()))], "level": c[0], "kills": int(len(x)),
                           "share": round(100 * len(x) / len(k), 1), "zone": humanize(x.killer_zone.mode().iloc[0], mp) if x.killer_zone.notna().any() else None,
                           "sneaky": bool(rate >= 3 * avg and len(x) >= 8)})
        danger.sort(key=lambda z: -z["kills"])
        dd = []
        for z in danger:
            if any(h["level"] == z["level"] and np.hypot(h["px"][0] - z["px"][0], h["px"][1] - z["px"][1]) < 2.2 * cell for h in dd):
                continue
            dd.append(z)
            if len(dd) == 8:
                break
        out[w] = {"hold": hold, "danger": dd, "n": int(len(k))}
    return out or None


PUSH_MAX_T = 50   # pushes before 1:05 on the clock: later, a CT on the T side is a retake or a flank


def _ctx_of(r):
    return ("pistol" if r.CT_buy == "pistol" else "anti_eco" if r.CT_buy == "full" and r.T_buy == "eco"
            else r.CT_buy if r.CT_buy in ("eco", "force", "full") else None)


_PUSH_ROWS = {}   # map -> the pushes of _ct_push, one row per round, for _push_answers


def _fakes(mp, g, dirs, shown_t=30.0, k=60):
    """Show one site, hit the other: per target site, the rounds where two Ts or more stood in the other site's region
    before shown_t s and the hit went to the target; the Ts' rounds won at equal economy (each round against what its
    two buys win on the map) against the direct hits; the hit's time; the medoid walk of the Ts who showed the other
    site, then reached the target bombsite. None when the regions make it meaningless (fakes over 60% of the hits)."""
    import re
    from wily.coaching import team
    regions = (team.map_meta().get(mp) or {}).get("regions") or {}
    reg = lambda z: "A" if z == "BombsiteA" else "B" if z == "BombsiteB" else regions.get(z)
    G = g[(g.T_buy != "pistol") & g.site.isin(["A", "B"]) & g.t_paths.notna()]
    if len(G) < 150:
        return None
    allp = float(G.T_won.mean())
    mr = {kk: (float(x.T_won.sum()) + 10 * allp) / (len(x) + 10) for kk, x in G.groupby(["T_buy", "CT_buy"])}
    rows = []
    for x in G.itertuples():
        other = "B" if x.site == "A" else "A"
        pl = [[(m.group(1), float(m.group(2))) for m in re.finditer(r"([A-Za-z\u2020]+)@([\d.]+)", p)] for p in str(x.t_paths).split(";")]
        shown = sum(1 for p in pl if any(reg(z) == other and t <= shown_t for z, t in p))
        rows.append({"key": (str(x.match), int(x.round)), "site": x.site, "fake": shown >= 2, "won": bool(x.T_won), "hit_t": x.hit_t,
                     "res": float(x.T_won) - mr.get((x.T_buy, x.CT_buy), allp)})
    R = pd.DataFrame(rows)
    out = {}
    for site in ("A", "B"):
        q = R[R.site == site]
        fk, dr = q[q.fake], q[~q.fake]
        if len(fk) < 20 or len(dr) < 20 or len(fk) > 0.6 * len(q):
            continue
        out[site] = {"n": int(len(fk)), "won": round(100 * (allp + float(fk.res.mean()))), "won_direct": round(100 * (allp + float(dr.res.mean()))),
                     "t_hit": round(float(fk.hit_t.median()), 1), "keys": set(fk.key)}
    if not out:
        return None
    # the walk: a T in the other site's region before shown_t s, then on the target bombsite, in those rounds
    walks = {site: [] for site in out}
    for d in dirs:
        mid = os.path.basename(d)
        fs = os.path.join(d, "samples.parquet")
        if not os.path.exists(fs):
            continue
        need = {(mid, r): site for site, o in out.items() for (m_, r) in o["keys"] if m_ == mid}
        if not need:
            continue
        S = pd.read_parquet(fs, columns=["steamid", "side", "round", "t", "px", "py", "level", "zone", "health"])
        S = S[(S.side == "T") & S.px.notna()].sort_values("t")
        for (rnd, sid), x in S[S["round"].isin([r for (_, r) in need])].groupby(["round", "steamid"]):
            site = need.get((mid, int(rnd)))
            if not site or len(walks[site]) >= 80:
                continue
            other, pts, showed, arrived, zs = ("B" if site == "A" else "A"), [], False, False, []
            for z, t, px_, py_, lv, hp in zip(x.zone, x.t, x.px, x.py, x.level, x.health):
                if hp is not None and hp <= 0:
                    break
                pts.append((float(px_), float(py_), lv, float(t)))
                if isinstance(z, str) and z and (not zs or zs[-1] != z):
                    zs.append(z)
                if reg(z) == other and t <= shown_t:
                    showed = True
                if showed and z == "Bombsite" + site:
                    arrived = True
                    break
            if showed and arrived and len(pts) >= 6:
                walks[site].append((pts, zs))
    for site, o in list(out.items()):
        o.pop("keys")
        W = walks.get(site) or []
        if len(W) < 4:
            continue
        def resample(pts, kk=k):
            xy = np.array([[p[0], p[1]] for p in pts])
            dd = np.r_[0, np.cumsum(np.hypot(*np.diff(xy, axis=0).T))]
            if dd[-1] <= 0:
                return None
            ss = np.linspace(0, dd[-1], kk)
            idx = np.clip(np.searchsorted(dd, ss), 0, len(pts) - 1)
            return np.c_[np.interp(ss, dd, xy[:, 0]), np.interp(ss, dd, xy[:, 1])], [pts[i][2] for i in idx], [pts[i][3] for i in idx]
        rs, zz = [], []
        for w, zs in W:
            r_ = resample(w)
            if r_ is not None:
                rs.append(r_)
                zz.append(zs)
        A = np.array([r[0] for r in rs])
        med = int(np.argmin([np.mean(np.hypot(*(A - a).transpose(2, 0, 1))) for a in A]))
        xy, lv, ts = rs[med]
        sm = xy.copy()
        sm[1:-1] = (xy[:-2] + xy[1:-1] + xy[2:]) / 3
        o["route"] = {"n": len(W), "win": o["won"], "zones": [humanize(z, mp) for z in zz[med]],
                      "pts": [[round(float(a)), round(float(b)), l, round(float(t))] for (a, b), l, t in zip(sm, lv, ts)]}
    return out or None





def _push_answers(mp, g):
    """When the CTs push past a neutral zone (pistol rounds aside): the Ts' rounds won by their answer, the site they
    hit (A, B) and when (fast: on the site before 1:10; late: after), at equal economy (each round against what its two
    buys win on this map). Per gate pushed through at least 25 times; answers with 10 rounds or more."""
    P = _PUSH_ROWS.get(mp)
    if P is None or not len(P) or "hit_t" not in g:
        return None
    G = g[g.T_buy != "pistol"]
    allp = float(G.T_won.mean())
    mr = {k: (float(x.T_won.sum()) + 10 * allp) / (len(x) + 10) for k, x in G.groupby(["T_buy", "CT_buy"])}
    G = G.assign(res=G.T_won.astype(float) - [mr.get((a, b), allp) for a, b in zip(G.T_buy, G.CT_buy)],
                 key=list(zip(G.match.astype(str), G["round"].astype(int))))
    P = P.assign(key=list(zip(P.mid.astype(str), P["round"].astype(int))))
    out = []
    for gate, x in P.groupby("gate"):
        r = G[G.key.isin(set(x.key))]
        if len(r) < 25:
            continue
        base = float(r.T_won.mean())
        ans = []
        for site in ("A", "B"):
            for tempo, sel in (("fast", r.hit_t <= 45), ("late", r.hit_t > 45)):
                q = r[(r.site == site) & sel]
                if len(q) >= 10:
                    ans.append({"site": site, "tempo": tempo, "n": int(len(q)), "won": round(100 * (base + float(q.res.mean())))})
        if len(ans) >= 2:
            ans.sort(key=lambda a: -a["won"])
            out.append({"gate": gate, "n": int(len(r)), "won": round(100 * base), "answers": ans[:3]})
    return out or None


def _ct_push(mp, dirs, cell=24):
    """CT pushes past the neutral zones. A neutral zone is where the Ts and the CTs who run get at the same time (the
    first arrivals of each side, round after round, within 2 s); past it, the Ts usually get there first. A CT alive
    on that side before 1:05 has pushed: through which neutral zone (the nearest one), when, by the CTs' kind of round
    (pistol, eco, force, full, full against the Ts' eco), and what came of it (a kill for the CT, the CT's death)."""
    first, early, n_ctx, duels = [], [], {}, []
    for di, d in enumerate(dirs):
        fs, fr, fd = (os.path.join(d, x) for x in ("samples.parquet", "rounds.parquet", "duels.parquet"))
        if not (os.path.exists(fs) and os.path.exists(fr)):
            continue
        R = pd.read_parquet(fr)
        if not len(R) or not five_v_five(R):
            continue
        S = pd.read_parquet(fs, columns=["steamid", "side", "round", "t", "px", "py", "level", "zone", "health"])
        S = S[(S.health > 0) & S.px.notna() & S.side.isin(["T", "CT"])]
        S = S.assign(cx=(S.px // cell).astype(int), cy=(S.py // cell).astype(int))
        # the first arrival of each side in each cell, per round
        fa = S[S.t <= 60].groupby(["round", "side", "level", "cx", "cy"]).t.min().reset_index()
        first.append(fa.assign(d=di))
        ctx = {int(r.round): _ctx_of(r) for r in R.itertuples()}
        for c in ctx.values():
            if c:
                n_ctx[c] = n_ctx.get(c, 0) + 1
        ct = S[(S.side == "CT") & (S.t <= PUSH_MAX_T)]
        early.append(ct.assign(d=di, ctx=ct["round"].map(ctx)))
        if os.path.exists(fd):
            D = pd.read_parquet(fd, columns=["round", "t", "killer", "victim", "killer_side", "victim_side"])
            duels.append(D.assign(d=di))
    if not first:
        return None
    F = pd.concat(first, ignore_index=True)
    q = F.groupby(["side", "level", "cx", "cy"]).t.agg(lambda x: float(x.quantile(.2)) if len(x) >= 8 else np.nan).unstack("side")
    if "T" not in q or "CT" not in q:
        return None
    q = q.dropna(subset=["T"])
    neutral = q[q.CT.notna() & ((q["T"] - q["CT"]).abs() <= 2)]
    tside_ = q[(q["T"] <= 35) & (q.CT.isna() | (q.CT - q["T"] >= 3))]   # the Ts get there clearly first
    if not len(neutral) or not len(tside_):
        return None
    # a real push goes past the line: T-side cells at least 2 cells (about 6 m) from any cell the CTs reach as soon as
    # the Ts or sooner (a CT holding an angle one step out is not pushing)
    ctr = q[q.CT.notna() & (q.CT - q["T"] < 3)].reset_index()
    tset = set()
    for (lv, cx, cy) in tside_.index:
        o = ctr[ctr.level == lv]
        if not len(o) or float(np.min(np.hypot(o.cx - cx, o.cy - cy))) >= 2:
            tset.add((lv, cx, cy))
    nz = neutral.reset_index()
    nz = nz.assign(px=(nz.cx + .5) * cell, py=(nz.cy + .5) * cell)
    # the zone name of each neutral cell (the most seen in it)
    E = pd.concat(early, ignore_index=True)
    zcell = E.groupby(["level", "cx", "cy"]).zone.agg(lambda z: z.mode().iloc[0] if z.notna().any() else None)
    nz["zone"] = [zcell.get((r.level, r.cx, r.cy)) for r in nz.itertuples()]
    E = E[E.ctx.notna()]
    E = E[[k in tset for k in zip(E.level, E.cx, E.cy)]]
    if not len(E):
        return None
    Dd = pd.concat(duels, ignore_index=True) if duels else pd.DataFrame(columns=["d", "round", "t", "killer", "victim"])
    pushes = []
    for (di, rnd), g in E.sort_values("t").groupby(["d", "round"]):
        p = g.iloc[0]
        cand = nz[nz.level == p.level]
        if not len(cand):
            continue
        dist = np.hypot(cand.px - p.px, cand.py - p.py)
        gate = cand.iloc[int(np.argmin(dist.values))]
        dd = Dd[(Dd.d == di) & (Dd["round"] == rnd) & (Dd.t >= p.t - 1) & (Dd.t <= p.t + 15)]
        pushes.append({"mid": os.path.basename(dirs[di]), "round": int(rnd), "ctx": p.ctx, "t": float(p.t), "px": float(p.px), "py": float(p.py), "level": p.level,
                       "gate": humanize(gate.zone, mp) if gate.zone else None, "gx": float(gate.px), "gy": float(gate.py),
                       "kill": bool((dd.killer == p.steamid).any()), "died": bool((dd.victim == p.steamid).any())})
    if not pushes:
        return None
    P = pd.DataFrame(pushes)
    _PUSH_ROWS[mp] = P
    out = {}
    for c, g in P.groupby("ctx"):
        n = n_ctx.get(c, 0)
        if n < 20:
            continue
        gates = []
        for (gname, lv), x in g.groupby(["gate", "level"]):
            if len(x) < 3:
                continue
            gates.append({"gate": gname, "level": lv, "share": round(100 * len(x) / n, 1), "n": int(len(x)), "t_med": round(float(x.t.median()), 1),
                          "kill": round(100 * float(x.kill.mean())), "died": round(100 * float(x.died.mean())),
                          "from": [round(float(x.gx.median())), round(float(x.gy.median()))], "to": [round(float(x.px.median())), round(float(x.py.median()))]})
        gates.sort(key=lambda x: -x["share"])
        out[c] = {"n": int(n), "push": round(100 * len(g) / n), "gates": gates[:5]}
    return out or None


def _postplant(mp, dirs, cell=26):
    """After the plant, each site: where the Ts hold (each T's median spot 3 to 30 s after the plant) and how often the
    round is won from there, the spots taken often enough first by their rounds won."""
    rows = []
    for d in dirs:
        fr, fs = os.path.join(d, "rounds.parquet"), os.path.join(d, "samples.parquet")
        if not (os.path.exists(fr) and os.path.exists(fs)):
            continue
        R = pd.read_parquet(fr)
        if not five_v_five(R) or "plant_site" not in R or "plant_t" not in R:   # older extractions have no plant columns
            continue
        R = R[R.plant_site.isin(["A", "B"]) & R.plant_t.notna()]
        if not len(R):
            continue
        S = pd.read_parquet(fs, columns=["steamid", "side", "round", "t", "px", "py", "level", "zone", "health"])
        S = S[(S.side == "T") & S.px.notna() & (S.health > 0)].merge(R[["round", "plant_site", "plant_t", "winner"]], on="round")
        S = S[(S.t >= S.plant_t + 3) & (S.t <= S.plant_t + 30)]
        if not len(S):
            continue
        h = S.groupby(["round", "steamid"]).agg(px=("px", "median"), py=("py", "median"), level=("level", "first"), zone=("zone", "first"),
                                                 site=("plant_site", "first"), won=("winner", lambda w: w.iloc[0] == "T")).reset_index()
        rows.append(h)
    if not rows:
        return None
    H = pd.concat(rows, ignore_index=True)
    H["c"] = list(zip(H.level, (H.px // cell).astype(int), (H.py // cell).astype(int)))
    out = {}
    for site, g in H.groupby("site"):
        base = float(g.won.mean())
        cand = []
        for c, x in g.groupby("c"):
            if len(x) < 6:
                continue
            cand.append({"px": [round(float(x.px.mean())), round(float(x.py.mean()))], "level": c[0], "n": int(len(x)), "win": round(100 * float(x.won.mean())),
                         "zone": humanize(x.zone.mode().iloc[0], mp) if x.zone.notna().any() else None,
                         "s": (float(x.won.sum()) + 10 * base) / (len(x) + 10)})
        cand.sort(key=lambda z: -z["s"])
        res = []
        for z in cand:   # not two holds in the same place
            if not any(r["level"] == z["level"] and np.hypot(r["px"][0] - z["px"][0], r["px"][1] - z["px"][1]) < 2 * cell for r in res):
                res.append({k: v for k, v in z.items() if k != "s"})
            if len(res) == 4:
                break
        out[site] = {"base": round(100 * base), "n": int(len(g)), "holds": res}
    return out or None


KEY_SITS = ("pistol", "eco_full", "force_full", "eco_force")
W_GROUP = {**{w: "close" for w in ("Tec-9", "Five-SeveN", "CZ75-Auto", "Dual Berettas", "MAC-10", "MP9", "MP7", "UMP-45", "P90", "PP-Bizon",
                                  "MP5-SD", "XM1014", "MAG-7", "Nova", "Sawed-Off")},
           **{w: "long" for w in ("Desert Eagle", "R8 Revolver", "SSG 08", "AK-47", "M4A1-S", "M4A4", "Galil AR", "FAMAS", "AWP", "AUG", "SG 553")},
           **{w: "default" for w in ("Glock-18", "USP-S", "P2000", "P250")}}


def _key_rows(d):
    """One match: the players' rounds in key situations (pistol, eco or force-buy against a full buy) with their weapon,
    and the kills and deaths of those players (where on the radar)."""
    fl, fd, fr = (os.path.join(d, f) for f in ("loadout.parquet", "duels.parquet", "rounds.parquet"))
    if not (os.path.exists(fl) and os.path.exists(fd) and os.path.exists(fr)):
        return None
    R = pd.read_parquet(fr, columns=["round", "T_buy", "CT_buy", "T_n", "CT_n"])
    if not five_v_five(R):
        return None
    L = pd.read_parquet(fl, columns=["round", "steamid", "side", "primary", "wclass", "pistol", "team_buy", "kills", "damage", "won", "died_t"])
    L = L.merge(R[["round", "T_buy", "CT_buy"]], on="round", how="left")
    enemy = np.where(L.side == "T", L.CT_buy, L.T_buy)
    L["sit"] = np.where(L.team_buy == "pistol", "pistol", np.where((L.team_buy == "eco") & (enemy == "full"), "eco_full",
                        np.where((L.team_buy == "force") & (enemy == "full"), "force_full",
                                 np.where((L.team_buy == "eco") & (enemy == "force"), "eco_force", None))))
    L = L[L.sit.notna() & L.side.isin(["T", "CT"])].copy()
    if not len(L):
        return None
    L["weapon"] = np.where((L.wclass != "pistol") & L.primary.notna(), L.primary, L.pistol)
    L["group"] = L.weapon.map(W_GROUP).fillna("other")
    L["steamid"] = L.steamid.astype(str)
    L["match"] = os.path.basename(d)
    D = pd.read_parquet(fd, columns=["round", "t", "killer", "victim", "killer_side", "victim_side", "killer_px", "killer_py", "killer_level",
                                     "killer_zone", "victim_px", "victim_py", "victim_level", "victim_zone"])
    D = D[D.killer_side != D.victim_side].assign(killer=lambda x: x.killer.astype(str), victim=lambda x: x.victim.astype(str))
    cols = ["round", "steamid", "side", "sit", "weapon", "group"]
    k = D.merge(L[cols], left_on=["round", "killer"], right_on=["round", "steamid"])
    k = k[k.killer_px.notna()][["side", "sit", "weapon", "group", "t", "killer_px", "killer_py", "killer_level", "killer_zone"]]
    v = D.merge(L[cols], left_on=["round", "victim"], right_on=["round", "steamid"])
    v = v[v.victim_px.notna()][["side", "sit", "weapon", "group", "t", "victim_px", "victim_py", "victim_level", "victim_zone"]]
    ren = lambda p: {f"{p}_px": "px", f"{p}_py": "py", f"{p}_level": "level", f"{p}_zone": "zone"}
    return L[["match", "round", "steamid", "side", "sit", "weapon", "group", "kills", "damage", "won", "died_t"]], k.rename(columns=ren("killer")), v.rename(columns=ren("victim"))


def setplay_weapons(by_map):
    """Every map together: in each key situation and side, what each weapon does (damage and kills per round, rounds
    won, alive at the end), for the weapons played often enough."""
    rows = [r[0] for ds in by_map.values() for d in ds for r in [_key_rows(d)] if r]
    if not rows:
        return None
    P = pd.concat(rows, ignore_index=True)
    out = {}
    for (side, sit), x in P.groupby(["side", "sit"]):
        ws = []
        for w, y in x.groupby("weapon"):
            if len(y) >= 30 and isinstance(w, str):
                ws.append({"w": w, "group": W_GROUP.get(w, "other"), "n": int(len(y)), "kpr": round(float(y.kills.mean()), 2),
                           "adr": round(float(y.damage.mean())), "win": round(100 * float(y.won.mean())), "alive": round(100 * float(y.died_t.isna().mean()))})
        ws.sort(key=lambda z: -z["adr"])
        out.setdefault(side, {})[sit] = ws
    return out


def _setplays(mp, dirs, cell=26):
    """Key rounds on this map, each side (pistol, eco or force-buy against a full buy): the spots that pay, for every
    weapon family (close range: Tec-9, SMGs, shotguns; long range: Deagle, scout, rifles; the default pistols) and for
    all together: kills from there against the deaths of the same family there; a spot the side rarely plays is a
    surprise for the other side."""
    got = [r for r in (_key_rows(d) for d in dirs) if r]
    if not got:
        return None
    P, K, V = (pd.concat([g_[i] for g_ in got], ignore_index=True) for i in range(3))
    for x in (K, V):
        x["c"] = list(zip(x.level, (x.px // cell).astype(int), (x.py // cell).astype(int)))

    def spots(k, v, every_k, top=3):
        vc, out = v.groupby("c").size(), []
        for c, x in k.groupby("c"):
            n_k, n_d = len(x), int(vc.get(c, 0))
            if n_k < 4:
                continue
            ratio = (n_k + 1) / (n_k + n_d + 2)
            share = float((every_k.c == c).mean()) if len(every_k) else 0
            out.append({"px": [round(float(x.px.mean())), round(float(x.py.mean()))], "level": c[0], "k": n_k, "d": n_d,
                        "zone": humanize(x.zone.mode().iloc[0], mp) if x.zone.notna().any() else None, "t_med": round(float(x.t.median())),
                        "surprise": bool(ratio >= 0.6 and share < 0.03), "s": ratio * np.log1p(n_k)})
        out.sort(key=lambda z: -z["s"])
        res = []
        for z in out:   # not two spots in the same place
            if not any(r["level"] == z["level"] and np.hypot(r["px"][0] - z["px"][0], r["px"][1] - z["px"][1]) < 2 * cell for r in res):
                res.append({k_: v_ for k_, v_ in z.items() if k_ != "s"})
            if len(res) == top:
                break
        return res

    out = {}
    for (side, sit), x in P.groupby(["side", "sit"]):
        if len(x) < 40:
            continue
        k_all, v_all = K[(K.side == side) & (K.sit == sit)], V[(V.side == side) & (V.sit == sit)]
        groups = {gname: spots(k_all[k_all.group == gname], v_all[v_all.group == gname], k_all) for gname in ("close", "long", "default")}
        rr = x.groupby(["match", "round"]).won.first()
        out.setdefault(side, {})[sit] = {"n": int(len(rr)), "win": round(100 * float(rr.mean())), "spots": spots(k_all, v_all, k_all),
                                         "groups": {k_: v_ for k_, v_ in groups.items() if v_}}
    return out or None


def _multi(mp, dirs):
    """Per side: the exact spots where the players of the base got two kills or more in a round from the same place."""
    ev = {"T": [], "CT": []}
    for d in dirs:
        fd, fr = os.path.join(d, "duels.parquet"), os.path.join(d, "rounds.parquet")
        if not os.path.exists(fd) or not os.path.exists(fr) or not five_v_five(pd.read_parquet(fr, columns=["T_n", "CT_n"])):
            continue
        D = pd.read_parquet(fd, columns=["round", "t", "killer", "killer_side", "victim_side", "killer_px", "killer_py", "killer_level", "killer_zone"])
        D = D[D.killer_side.isin(["T", "CT"]) & (D.killer_side != D.victim_side) & D.killer_px.notna() & D.killer_zone.notna()]
        for (side, _, _), x in D.groupby(["killer_side", "round", "killer"]):
            if len(x) >= 2:
                ev[side] += multi_events([{"px": [a, b], "level": lv, "t": t, "zone": humanize(z, mp)}
                                          for a, b, lv, t, z in zip(x.killer_px, x.killer_py, x.killer_level, x.t, x.killer_zone)])
    return {s: multi_spots(e, top=16, min_n=2) for s, e in ev.items() if e}


def evidence(mp, g, dirs, pool=None):
    site_of = {(m, int(r)): s for m, r, s in zip(g.match, g["round"], g.site)}
    plants, retakes, rows = _plants_and_retakes(mp, dirs)
    if pool is not None and rows is not None:
        pool.append(rows)
    try:
        multi = _multi(mp, dirs)
    except Exception as e:   # the radar just shows no base multi-kills
        print(f"{mp}: multi-kill spots unavailable ({e})")
        multi = None
    return {"survival": _survival(g), "contact": _contact(g), "plants": plants, "retakes": retakes,
            "deaths": _deaths(mp, dirs, site_of), "windows": {k: [lo, hi] for k, lo, hi in WINDOWS}, "multi": multi}


SELF_T = [20, 30, 40, 50]


def _self_evidence(mp, g, dirs):
    """What a CT sees from their own spot, without clicking anything: where they stand at 15 s (A, B or mid) and
    whether they were in a fight (hurt, a kill or dead) by 20, 30, 40 and 50 s. For each region and moment, how often
    that happens for each place the attack goes, on every CT of the base: a quiet B at 30 s tilts toward A, a fight
    at B toward B. Used as a likelihood (where a CT stands does not depend on where the Ts go)."""
    from wily.coaching import team
    from wily.demos.map_analysis import humanize
    reg = (team.map_meta().get(mp) or {}).get("regions") or {}
    site_of = {(str(m), int(r)): ("none" if s == "-" else s) for m, r, s in zip(g.match, g["round"], g.site) if s in ("A", "B", "-")}
    cnt = {}
    for d in dirs:
        mid = os.path.basename(d)
        fs, fd = os.path.join(d, "samples.parquet"), os.path.join(d, "duels.parquet")
        if not os.path.exists(fs) or not any(k[0] == mid for k in site_of):
            continue
        S = pd.read_parquet(fs, columns=["steamid", "side", "round", "t", "zone", "health"])
        S = S[(S.side == "CT") & (S.steamid != 0) & (S.t <= max(SELF_T))]
        if not len(S):
            continue
        z15 = S[(S.t >= 12) & (S.t <= 18)].groupby(["round", "steamid"]).zone.agg(lambda z: z.mode().iloc[0])
        hurt = S[S.health < 100].groupby(["round", "steamid"]).t.min()
        parts = [hurt]
        if os.path.exists(fd):
            D = pd.read_parquet(fd, columns=["round", "t", "killer", "victim"])
            for col in ("killer", "victim"):
                x = D.groupby(["round", col]).t.min()
                x.index.names = ["round", "steamid"]
                parts.append(x)
        first = pd.concat(parts, axis=1).min(axis=1)
        for (rnd, sid), z in z15.items():
            site = site_of.get((mid, int(rnd)))
            if site is None:
                continue
            region = reg.get(z, "mid")
            c = first.get((rnd, sid), np.nan)
            for t in SELF_T:
                e = cnt.setdefault((region, t), {}).setdefault(site, [0, 0])
                e[0] += bool(c == c and c <= t)
                e[1] += 1
    lik = {}
    for (region, t), by in cnt.items():
        row = {"contact": {}, "quiet": {}, "n": {}}
        for site in ("A", "B", "none"):
            k, n = by.get(site, [0, 0])
            row["contact"][site] = round((k + 1) / (n + 2), 4)   # a fight by t at this spot, when the attack goes there
            row["quiet"][site] = round((n - k + 1) / (n + 2), 4)
            row["n"][site] = n
        lik.setdefault(region, {})[str(t)] = row
    names = {}
    for key, region in reg.items():
        names[humanize(key, mp)] = region
    return {"t": SELF_T, "regions": names, "lik": lik} if lik else None


def _zone_regions(mp, TS):
    """Zone key -> A / B / mid with the lanes and the levels (stacked sites on Nuke), as the team plan reads them."""
    from wily.coaching import team
    from wily.demos.map_analysis import humanize
    meta = (team.map_meta().get(mp) or {}).get("regions") or {}
    zones = ((TS or {}).get("geo") or {}).get("zones") or {}
    zm = [{"key": k, "name": humanize(k, mp), **({"px": zones[humanize(k, mp)]["px"], "level": zones[humanize(k, mp)].get("level")}
                                                if humanize(k, mp) in zones else {})} for k in meta]
    R = team.Regions(TS or {}, {"zones_meta": zm}, meta)
    return {z["key"]: R.of(z["name"]) for z in zm}


def _tplan(mp, g, dirs, TS):
    """What the T side can lean on, from the base: the tempo that wins by kind of round, fakes (first contact on the
    other site, then the hit), where the CTs stand 20 s in, how fast the CTs of the other site arrive after the hit,
    and the smokes that pay off toward each site (rounds won when thrown vs the side's average)."""
    import collections
    from wily.demos.map_analysis import humanize
    k2r = _zone_regions(mp, TS)
    n2r = {humanize(k, mp): r for k, r in k2r.items()}
    pct = lambda x: int(round(100 * float(x.mean()))) if len(x) else None
    out = {"tempo": {}, "fake": {}, "setup": {}, "rotation": {}, "smokes": {}}
    d = g[g.dyn.isin(["rush", "fast", "exec", "late"])]
    for c, x in d.groupby("ctx"):
        out["tempo"][c] = {k: [int(len(y)), pct(y.T_won.astype(bool))] for k, y in x.groupby("dyn") if len(y) >= 8}
    h = g[g.site.isin(["A", "B"])].assign(fr=lambda x: x.first_zone.map(n2r))
    h = h[h.fr.isin(["A", "B"])]
    for kind, y in (("switch", h[h.fr != h.site]), ("direct", h[h.fr == h.site])):
        out["fake"][kind] = [int(len(y)), pct(y.T_won.astype(bool))]
    info = {(str(m), int(r)): (s_, ht, c) for m, r, s_, ht, c in zip(g.match, g["round"], g.site, g.hit_t, g.ctx)}
    setups, rot = collections.defaultdict(collections.Counter), {"A": [], "B": []}
    for dd in dirs:
        mid = os.path.basename(dd)
        f = os.path.join(dd, "samples.parquet")
        if not os.path.exists(f):
            continue
        S = pd.read_parquet(f, columns=["steamid", "side", "round", "t", "zone", "health"])
        S = S[(S.side == "CT") & (S.health > 0) & (S.t <= 90)]
        S = S.assign(reg=S.zone.map(k2r).fillna("mid"))
        for rnd, x in S.groupby("round"):
            k = (mid, int(rnd))
            if k not in info:
                continue
            site, hit_t, ctx = info[k]
            at = x[(x.t >= 18) & (x.t <= 22)].groupby("steamid").reg.agg(lambda r: r.mode().iloc[0])
            if len(at) >= 4:
                c = collections.Counter(at)
                setups[ctx][(c.get("A", 0), c.get("B", 0), c.get("mid", 0))] += 1
                setups["all"][(c.get("A", 0), c.get("B", 0), c.get("mid", 0))] += 1
            if site in ("A", "B") and hit_t == hit_t:
                ah = x[(x.t >= hit_t - 1) & (x.t <= hit_t + 1)].groupby("steamid").reg.agg(lambda r: r.mode().iloc[0])
                for sid, rg in ah.items():
                    if rg != site:
                        later = x[(x.steamid == sid) & (x.t > hit_t) & (x.reg == site)].t
                        rot[site].append(float(later.min() - hit_t) if len(later) else np.nan)
    for c, cnt in setups.items():
        tot = sum(cnt.values())
        if tot >= 20:
            out["setup"][c] = {"n": tot, "top": [[a, b, m_, int(round(100 * k / tot))] for (a, b, m_), k in cnt.most_common(4)],
                               "light": {L: int(round(100 * sum(k for (a, b, _), k in cnt.items() if (a if L == "A" else b) <= 1) / tot)) for L in ("A", "B")}}
    for L, xs in rot.items():
        r = pd.Series(xs, dtype=float)
        if r.notna().sum() >= 15:
            out["rotation"][L] = {"n": int(r.notna().sum()), "med": round(float(r.median()), 1), "q25": round(float(r.quantile(.25)), 1),
                                  "arrive": int(round(100 * r.notna().mean()))}
    try:   # smokes toward each site: rounds won when thrown vs the side's average (nades summary)
        from wily.insights import nades
        T = ((nades.summary().get("maps") or {}).get(mp) or {}).get("T") or {}
        for x in (T.get("types") or {}).get("smoke", {}).get("groups", []):
            L = k2r.get(x.get("to_key"))
            # thrown from the site itself = after taking it: it follows the win more than it makes it, left out
            if L in ("A", "B") and x.get("n", 0) >= 10 and x.get("win") is not None and x.get("base_win") is not None                     and not str(x.get("from_key", "")).startswith("Bombsite"):
                out["smokes"].setdefault(L, []).append({k: x.get(k) for k in ("from", "to", "n", "win", "base_win", "timer", "t_med", "how", "setpos")})
        for L in out["smokes"]:
            out["smokes"][L] = sorted(out["smokes"][L], key=lambda x: -(x["win"] - x["base_win"]) * min(x["n"], 60) ** .5)[:4]
    except Exception as e:
        print(f"{mp}: smokes for the T plan unavailable ({e})")
    return out


SIT_OF = {("pistol", None): "pistol"}


def _sit(mine, theirs):
    """Economic situation from one player's side: their team's buy against the other team's."""
    if mine == "pistol":
        return "pistol"
    return {("full", "eco"): "anti_eco", ("full", "full"): "full_full", ("force", "full"): "force_full", ("eco", "full"): "eco_full"}.get((mine, theirs))


def situ_rows(df, mids=None, who=None):
    """One row per player and round (or only one player's): side, situation, won, died before 20 s, kills."""
    buys = {(str(m), int(r)): (t, c) for m, r, t, c in zip(df.match, df["round"], df.T_buy, df.CT_buy)}
    rows = []
    for mid in (mids if mids is not None else df.match.astype(str).unique()):
        f = os.path.join(config.DEEP, str(mid), "loadout.parquet")
        if not os.path.exists(f):
            continue
        L = pd.read_parquet(f, columns=["round", "steamid", "side", "died_t", "won", "kills"])
        if who is not None:
            L = L[L.steamid == int(who)]
        for r in L.itertuples():
            b = buys.get((str(mid), int(r.round)))
            if not b:
                continue
            s_ = _sit(*((b[0], b[1]) if r.side == "T" else (b[1], b[0])))
            if s_:
                rows.append({"side": r.side, "sit": s_, "won": bool(r.won), "early": bool(r.died_t == r.died_t and r.died_t < 20), "kills": r.kills})
    return pd.DataFrame(rows)


def situ_table(d):
    """{side: {situation: [rounds, % won, % died before 20 s, kills per round]}}"""
    out = {}
    if not len(d):
        return out
    for (side, s_), x in d.groupby(["side", "sit"]):
        out.setdefault(side, {})[s_] = [int(len(x)), int(round(100 * x.won.mean())), int(round(100 * x.early.mean())), round(float(x.kills.mean()), 2)]
    return out


def situ_player(sid):
    """The same table for one player, on their own matches (their recurrences by situation)."""
    from wily.app import pipeline
    df = load()
    return situ_table(situ_rows(df, pipeline.player_matches(sid), who=sid)) if len(df) else {}


def _situations(df, maps_summary):
    """Situations measured on every map together (a map alone has too few rounds). Pistol as CT: what wins when the
    Ts rush (CT kevlars, grenades bought, CTs on the hit site 5 s before the hit) and when they don't."""
    rows = []
    p = df[df.ctx == "pistol"]
    for (mid, mp), g in p.groupby(["match", "map"]):
        d = os.path.join(config.DEEP, str(mid))
        f = os.path.join(d, "loadout.parquet")
        if not os.path.exists(f) or mp not in maps_summary:
            continue
        L = pd.read_parquet(f, columns=["round", "side", "armor", "nades"])
        k2r = _zone_regions(mp, maps_summary[mp])
        S = pd.read_parquet(os.path.join(d, "samples.parquet"), columns=["steamid", "side", "round", "t", "zone", "health"])
        S = S[(S.side == "CT") & (S.health > 0)]
        for r in g.itertuples():
            ct = L[(L["round"] == r.round) & (L.side == "CT")]
            if len(ct) < 4:
                continue
            on = None
            if r.site in ("A", "B") and r.hit_t == r.hit_t:
                x = S[(S["round"] == r.round) & (S.t >= r.hit_t - 6) & (S.t <= r.hit_t - 4)]
                on = int((x.groupby("steamid").zone.agg(lambda z: z.mode().iloc[0]).map(k2r) == r.site).sum())
            rows.append({"rush": r.dyn == "rush", "ct_won": not bool(r.T_won), "kev": int((ct.armor > 0).sum()), "nades": int(ct.nades.sum()), "on": on})
    d = pd.DataFrame(rows)
    if not len(d):
        return {}
    out = {"n": int(len(d)), "rush_share": int(round(100 * d.rush.mean()))}
    for key, x in (("rush", d[d.rush]), ("no_rush", d[~d.rush])):
        cell = lambda y: [int(len(y)), int(round(100 * y.ct_won.mean()))] if len(y) >= 15 else None
        out[key] = {"kevlar": {"0-2": cell(x[x.kev <= 2]), "3-4": cell(x[(x.kev >= 3) & (x.kev <= 4)]), "5": cell(x[x.kev == 5])},
                    "nades": {"0-1": cell(x[x.nades <= 1]), "2+": cell(x[x.nades >= 2])},
                    "on_site": {"0": cell(x[x.on == 0]), "1": cell(x[x.on == 1]), "2+": cell(x[x.on >= 2])}}
    res = {"pistol_ct": out}
    try:   # every player of the base, by side and situation: the reference for each player's own recurrences
        res["base_by_side"] = situ_table(situ_rows(df))
    except Exception as e:
        print("situations by side unavailable:", e)
    # economic situations: who is on eco, force or full on each side, and what costs rounds there (a death before
    # 20 s on your side), with the T tempo that wins in each
    rows = []
    for mid, g in df.groupby("match"):
        f = os.path.join(config.DEEP, str(mid), "duels.parquet")
        if not os.path.exists(f):
            continue
        D = pd.read_parquet(f, columns=["round", "t", "victim_side"])
        early = D[D.t < 20].groupby(["round", "victim_side"]).size()
        for r in g.itertuples():
            rows.append({"T_buy": r.T_buy, "CT_buy": r.CT_buy, "T_won": bool(r.T_won), "dyn": r.dyn,
                         "ct_early": int(early.get((r.round, "CT"), 0)) > 0, "t_early": int(early.get((r.round, "T"), 0)) > 0})
    e = pd.DataFrame(rows)
    pc = lambda x: int(round(100 * float(x.mean())))
    for key, sel in (("ct_anti_eco", (e.T_buy == "eco") & (e.CT_buy == "full")), ("t_anti_eco", (e.CT_buy == "eco") & (e.T_buy == "full")),
                     ("full_full", (e.CT_buy == "full") & (e.T_buy == "full")), ("t_force", (e.T_buy == "force") & (e.CT_buy == "full")),
                     ("ct_force", (e.CT_buy == "force") & (e.T_buy == "full")), ("t_eco", (e.T_buy == "eco") & (e.CT_buy == "full"))):
        x = e[sel]
        if len(x) < 60:
            continue
        c = {"n": int(len(x)), "t_win": pc(x.T_won), "rush": pc(x.dyn == "rush")}
        for side, col in (("CT", "ct_early"), ("T", "t_early")):
            y, z = x[x[col]], x[~x[col]]
            if len(y) >= 20 and len(z) >= 20:
                won = (lambda q: pc(~q.T_won)) if side == "CT" else (lambda q: pc(q.T_won))
                c[f"early_{side}"] = [won(z), won(y), int(len(y))]   # win with no early death, with one, rounds with one
        c["tempo"] = {k: [int(len(y)), pc(y.T_won)] for k, y in x.groupby("dyn") if len(y) >= 15 and k != "none"}
        res[key] = c
    return res


def retake_table(pool):
    """Retakes on every map together: the CT side's chances by players alive on each side when the bomb goes down."""
    if not pool:
        return []
    df = pd.concat(pool, ignore_index=True)
    out = []
    for (ct, tt), s in df.groupby(["ct", "tt"]):
        if len(s) >= 15 and ct >= 1 and tt >= 1:
            out.append({"ct": int(ct), "t": int(tt), "n": int(len(s)), "ct_win": round(100 * (1 - float(s.win_t.mean())))})
    return sorted(out, key=lambda x: (-x["ct"], x["t"]))


_SI = {}


def _story_inputs():
    """The zones, lanes and map geometry every match's story reads: read once for the stories of a page build (16/10:
    3 files, 5 MB, read again for each of the player's matches), again when one changes or after 30 s."""
    import json
    import time
    from wily.insights import lanes as LN
    def stamp(p):
        try:
            st = os.stat(p)
            return st.st_mtime_ns, st.st_size
        except OSError:
            return None
    key = (stamp(ZONES), stamp(LANES), stamp(LN.GEO))
    hit = _SI.get("v")
    if hit and hit[0] == key and time.monotonic() - hit[1] < 30:
        return hit[2]
    try:
        zs = json.load(open(ZONES, encoding="utf-8"))
    except (OSError, ValueError):
        zs = {}
    try:
        G = LN.geo()
    except Exception as e:   # the story goes on without the plays, as before
        G = e
    v = (zs, _lanes(), G)
    _SI["v"] = (key, time.monotonic(), v)
    return v


def match_story(mid):
    """Round by round, for one match: where the Ts went and how (rush, execute...), who died where and when (the Ts
    killed alone flagged), the plant and the result. Times in seconds since the end of the freeze time."""
    import json
    f = os.path.join(OUT, f"{mid}.parquet")
    if not os.path.exists(f):
        return None
    df = pd.read_parquet(f)
    if not len(df) or "t_deaths" not in df:
        return None
    zs, ls, G = _story_inputs()
    df = _dynamics(_directions(df, zs=zs))
    try:   # the play of each round, with the lanes this match's Ts used
        from wily.insights import lanes as LN
        if isinstance(G, Exception):
            raise G
        df = LN.classify(df, ls, G)
        mp = df["map"].iloc[0]
        df["play_name"] = [LN.name(p, ls.get(mp), [int(i) for i in str(u).split(",") if i != ""]) for p, u in zip(df.play, df.play_lanes)]
    except Exception:
        df["play"], df["play_name"] = None, None
    num = lambda v: round(float(v), 1) if v is not None and v == v else None
    out = []
    for _, r in df.sort_values("round").iterrows():
        out.append({"r": int(r["round"]), "team": r.t_team, "site": r.site, "in": bool(r.entered), "dyn": r.dyn,
                    "play": r.get("play"), "play_name": r.get("play_name"),
                    "at": num(r.commit), "grp": int(r.grp) if r.grp == r.grp and r.grp is not None else None,
                    "plant": [r.plant_site, num(r.plant_t)] if r.plant_site in ("A", "B") else None,
                    "tw": bool(r.T_won), "why": r.reason, "end": num(r.end_t),
                    "lurk": bool(r.lurk_other) if isinstance(r.lurk_other, (bool, np.bool_)) else None,
                    "td": [[z, round(t, 1), a] for z, t, a in _deaths_list(r.t_deaths)],
                    "cd": [[z, round(t, 1)] for z, t, _ in _deaths_list(r.get("ct_deaths"), lone_flag=False)],
                    "fc": [r.first_zone, num(r.first_t), None if r.fc_alone is None or r.fc_alone != r.fc_alone else bool(r.fc_alone)]
                          if isinstance(r.first_zone, str) else None,
                    "bunch": [r.bunch_zone, num(r.bunch_t)] if r.bunch_t is not None and r.bunch_t == r.bunch_t else None})
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(run_all(force="--force" in sys.argv), "demos analyzed")
