"""What the In game page showed during your matches, checked against what happened in them (from the match's demo).

During a match the page sends, a few times per round, what it shows: the CT read of the site (A / B / no hit) and of a
rush, the T side's path 1, the buy it advises, the site it finds after the plant. They are kept in out/live/ (one file
per day). Once the match's demo is analyzed, every round is compared with what the demo says: where the Ts went, if
they rushed, which play they ran, what your team bought, where the bomb went down. Per match and per map: how often
the read was right, and the rounds won when the team followed path 1 or not."""
import datetime as dt
import json
import math
import os
import re
import threading
import time

from wily.core import config

LIVE = os.path.join(config.OUT, "live")
_LOCK = threading.Lock()
KEYS = {"map", "round", "side", "bucket", "elapsed", "money", "score", "read", "paths", "buy", "key", "site", "p_site", "nades"}


def log(body):
    """One snapshot of the page (sent by the page itself): kept as one line of the day's file."""
    if not isinstance(body, dict) or not re.fullmatch(r"[a-z0-9_]{3,40}", str(body.get("map") or "")):
        return False
    rec = {k: body[k] for k in KEYS if k in body}
    if len(json.dumps(rec)) > 6000:
        return False
    rec["ts"] = round(time.time(), 1)
    os.makedirs(LIVE, exist_ok=True)
    with _LOCK, open(os.path.join(LIVE, dt.date.today().strftime("%Y%m%d") + ".jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return True


def _logs():
    out = []
    if os.path.isdir(LIVE):
        for fn in sorted(os.listdir(LIVE)):
            if fn.endswith(".jsonl"):
                for line in open(os.path.join(LIVE, fn), encoding="utf-8"):
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    return out


_BY = {"state": None, "by": {}}


def _rounds_of(mid):
    """The base's T side rounds of one match (16/10: the table split by match once per state of the base, not copied
    and filtered again for each of your matches: 61 times a plan)."""
    from wily.insights import tside
    st = tside._base_state()[0]
    if st is None or _BY["state"] != st:
        df = tside.load()
        _BY.update(state=st, by={k: g for k, g in df.groupby(df.match.astype(str), sort=False)})
    return _BY["by"].get(str(mid))


def _truth(mid, sid):
    """The match's rounds as the demo tells them: site, tempo, play, plant site, both buys, who won, your side."""
    import pandas as pd
    g = _rounds_of(mid)
    if g is None or not len(g):
        return None
    side = {}
    f = os.path.join(config.DEEP, str(mid), "loadout.parquet")
    if os.path.exists(f):
        L = pd.read_parquet(f, columns=["round", "steamid", "side"])
        mine = L[L.steamid.astype(str) == str(sid)]
        side = {int(r): s for r, s in zip(mine["round"], mine.side)}
    rows = {}
    for r in g.itertuples():
        rows[int(r.round)] = {"site": r.site, "dyn": r.dyn, "play": r.play if isinstance(r.play, str) else None,
                              "plant": r.plant_site if isinstance(r.plant_site, str) else None, "T_won": bool(r.T_won),
                              "T_buy": r.T_buy, "CT_buy": r.CT_buy, "side": side.get(int(r.round))}
    return rows


def _site_of_play(p):
    return None if not p or p == "none" else (p[-1] if p.startswith(("rush", "split")) else p[0])


def check_match(sid, m, logs):
    """One match: its snapshots (same map, during the match) against its rounds."""
    try:
        start = dt.datetime.fromisoformat(m["time"]).timestamp()
    except (KeyError, ValueError, TypeError):
        return None
    span = 60 * (5 + 2.5 * (m.get("rounds") or 24))
    snaps = [x for x in logs if x.get("map") == m.get("map") and start - 600 <= x.get("ts", 0) <= start + span]
    if not snaps:
        return None
    truth = _truth(m["id"], sid)
    if not truth:
        return None
    by = {}
    for x in snaps:   # the last snapshot of each moment wins (the page may send it again after a reload)
        by[(int(x.get("round") or 0), x.get("bucket"))] = x
    ct = {"n": 0, "right": 0, "logloss": 0.0, "rush_n": 0, "rush_right": 0}
    t = {"n": 0, "followed": 0, "won_f": 0, "won_nf": 0, "n_nf": 0, "site_same": 0}
    buy = {"n": 0, "same": 0}
    plant = {"n": 0, "right": 0}
    rounds = []
    for rnd, tr in sorted(truth.items()):
        my = tr["side"]
        if my not in ("T", "CT"):
            continue
        rec = {"round": rnd, "side": my}
        snap = by.get((rnd, "t20")) or by.get((rnd, "fz"))
        if my == "CT" and snap and isinstance(snap.get("read"), dict):
            rd = snap["read"]
            real = tr["site"] if tr["site"] in ("A", "B") else "none"
            p = max(0.01, min(0.99, (rd.get(real) if real != "none" else rd.get("none", 0)) / 100))
            guess = max(("A", "B", "none"), key=lambda k: rd.get(k, 0))
            ct["n"] += 1
            ct["right"] += guess == real
            ct["logloss"] += -math.log(p)
            rec.update(read=guess, real=real, p=round(100 * p), dist=[rd.get("A", 0), rd.get("B", 0), rd.get("none", 0)])
            fz = by.get((rnd, "fz")) or snap
            if isinstance((fz or {}).get("read"), dict) and fz["read"].get("rush") is not None:
                said, did = fz["read"]["rush"] >= 40, tr["dyn"] == "rush"
                ct["rush_n"] += 1
                ct["rush_right"] += said == did
                rec.update(rush_said=fz["read"]["rush"], rush=did)
        fz = by.get((rnd, "fz"))
        if my == "T" and fz and fz.get("paths"):
            p1 = fz["paths"][0].get("k")
            won = tr["T_won"]
            follow = tr["play"] == p1
            t["n"] += 1
            t["followed"] += follow
            t["site_same"] += _site_of_play(tr["play"]) == _site_of_play(p1)
            if follow:
                t["won_f"] += won
            else:
                t["n_nf"] += 1
                t["won_nf"] += won
            rec.update(p1=p1, play=tr["play"], won=won, wr=fz["paths"][0].get("wr"))
        if fz and fz.get("buy"):
            team = tr["T_buy"] if my == "T" else tr["CT_buy"]
            adv = {"half": "eco"}.get(fz["buy"], fz["buy"])
            if team in ("eco", "force", "full"):
                buy["n"] += 1
                buy["same"] += adv == team
                rec.update(buy=fz["buy"], team_buy=team)
        pl = by.get((rnd, "plant"))
        if pl and pl.get("site") and tr["plant"] in ("A", "B"):
            plant["n"] += 1
            plant["right"] += pl["site"] == tr["plant"]
            rec.update(site_said=pl["site"], plant=tr["plant"], p_site=pl.get("p_site"))
        if len(rec) > 2:
            rounds.append(rec)
    if not rounds:
        return None
    return {"mid": m["id"], "map": m["map"], "time": m["time"], "snapshots": len(snaps),
            "ct": ct, "t": t, "buy": buy, "plant": plant, "rounds": rounds}


def summary(res):
    """Per map, every checked match together: the numbers the page shows."""
    maps = {}
    for r in res.values():
        a = maps.setdefault(r["map"], {"matches": 0, "ct_n": 0, "ct_right": 0, "ct_ll": 0.0, "rush_n": 0, "rush_right": 0,
                                       "t_n": 0, "followed": 0, "won_f": 0, "won_nf": 0, "n_nf": 0, "buy_n": 0, "buy_same": 0, "plant_n": 0, "plant_right": 0})
        a["matches"] += 1
        a["ct_n"] += r["ct"]["n"]
        a["ct_right"] += r["ct"]["right"]
        a["ct_ll"] += r["ct"]["logloss"]
        a["rush_n"] += r["ct"]["rush_n"]
        a["rush_right"] += r["ct"]["rush_right"]
        for k in ("followed", "won_f", "won_nf", "n_nf"):
            a[k] += r["t"][k]
        a["t_n"] += r["t"]["n"]
        a["buy_n"] += r["buy"]["n"]
        a["buy_same"] += r["buy"]["same"]
        a["plant_n"] += r["plant"]["n"]
        a["plant_right"] += r["plant"]["right"]
    pct = lambda x, n: round(100 * x / n) if n else None
    return {m: {"matches": a["matches"], "site_right": pct(a["ct_right"], a["ct_n"]), "site_n": a["ct_n"],
                "site_logloss": round(a["ct_ll"] / a["ct_n"], 3) if a["ct_n"] else None,
                "rush_right": pct(a["rush_right"], a["rush_n"]), "rush_n": a["rush_n"],
                "followed": pct(a["followed"], a["t_n"]), "t_n": a["t_n"], "win_followed": pct(a["won_f"], a["followed"]),
                "win_other": pct(a["won_nf"], a["n_nf"]), "buy_same": pct(a["buy_same"], a["buy_n"]), "buy_n": a["buy_n"],
                "plant_right": pct(a["plant_right"], a["plant_n"]), "plant_n": a["plant_n"]} for m, a in maps.items()}


def _shrink(fit, neutral, n, k=40):
    """Few rounds checked: the fit stays close to 'no change'. 40 rounds: half of it."""
    return neutral + (fit - neutral) * n / (n + k)


def calibrate(res):
    """The automatic calibration of the live read, from every checked round (all maps together, per map once a map has
    enough): a temperature for the site read (above 1: the read was too sure of itself, its odds get flatter; below
    1: it was too shy), the same for the plant site, a correction of the rush odds, and of the paths' win %."""
    rows = [r for m in res.values() for r in m.get("rounds", [])]
    lg = lambda p: math.log(p / (1 - p))
    sg = lambda z: 1 / (1 + math.exp(-z))
    cl = lambda p: min(.97, max(.03, p))
    out = {"maps": {}}

    def site_t(rs):
        best, bl = 1.0, None
        for i in range(10, 61):
            T = i / 20
            ll = 0.0
            for r in rs:
                w = [max(1e-3, v / 100) ** (1 / T) for v in r["dist"]]
                k = {"A": 0, "B": 1, "none": 2}[r["real"]]
                ll -= math.log(w[k] / sum(w))
            if bl is None or ll < bl:
                best, bl = T, ll
        return best
    site = [r for r in rows if r.get("dist") and r.get("real") in ("A", "B", "none") and sum(r["dist"]) > 0]
    out["site_n"] = len(site)
    out["site_T"] = round(_shrink(site_t(site), 1.0, len(site)), 2) if site else 1.0
    by_map = {}
    for m in res.values():
        by_map.setdefault(m["map"], []).extend(r for r in m.get("rounds", []) if r in site)
    for mp, rs in by_map.items():
        if len(rs) >= 40:
            out["maps"][mp] = {"site_T": round(_shrink(site_t(rs), out["site_T"], len(rs)), 2), "site_n": len(rs)}
    # rush: a slope and a shift on the log-odds (1 and 0: unchanged)
    rush = [(cl(r["rush_said"] / 100), bool(r["rush"])) for r in rows if r.get("rush_said") is not None and "rush" in r]
    out["rush_n"] = len(rush)
    a_b = (1.0, 0.0)
    if rush:
        bl = None
        zs = [lg(p) for p, _ in rush]
        spread = (sum((z - sum(zs) / len(zs)) ** 2 for z in zs) / len(zs)) ** .5
        for ai in (range(5, 16) if spread >= .3 else (10,)):   # the same odds every time: only the shift can be measured
            for bi in range(-20, 21):
                a, b = ai / 10, bi / 10
                ll = -sum(math.log(sg(a * lg(p) + b) if y else 1 - sg(a * lg(p) + b)) for p, y in rush)
                if bl is None or ll < bl:
                    a_b, bl = (a, b), ll
    out["rush"] = [round(_shrink(a_b[0], 1.0, len(rush)), 2), round(_shrink(a_b[1], 0.0, len(rush)), 2)]
    # the plant site: how sure the page should be
    pl = [(cl(r["p_site"] / 100), r["site_said"] == r["plant"]) for r in rows if r.get("p_site") and r.get("plant")]
    out["plant_n"] = len(pl)
    tb = 1.0
    if pl:
        bl = None
        for i in range(10, 61):
            T = i / 20
            ll = -sum(math.log(sg(lg(p) / T) if y else 1 - sg(lg(p) / T)) for p, y in pl)
            if bl is None or ll < bl:
                tb, bl = T, ll
    out["plant_T"] = round(_shrink(tb, 1.0, len(pl)), 2)
    # the paths: the % shown against the rounds won when the team followed path 1
    pa = [(cl(r["wr"] / 100), bool(r["won"])) for r in rows if r.get("wr") is not None and r.get("p1") and r.get("play") == r.get("p1")]
    out["path_n"] = len(pa)
    d = 0.0
    if pa:
        bl = None
        for di in range(-15, 16):
            dd = di / 10
            ll = -sum(math.log(sg(lg(p) + dd) if y else 1 - sg(lg(p) + dd)) for p, y in pa)
            if bl is None or ll < bl:
                d, bl = dd, ll
    out["path_d"] = round(_shrink(d, 0.0, len(pa)), 2)
    return out


def run(sid):
    """Every match of the player with snapshots: checked (again when its demo got analyzed since), saved with the
    player, and the per-map numbers returned for the plan."""
    path = os.path.join(config.player_dir(sid), "livecheck.json")
    old = config.read_json(path, {}) or {}
    logs = _logs()
    if not logs:
        return {"maps": summary(old.get("matches", {})), "matches": [], "calib": calibrate(old.get("matches", {}))}
    site = os.path.join(config.OUT, "site", "players", f"{sid}.json")
    try:
        matches = json.load(open(site, encoding="utf-8")).get("matches") or []
    except (OSError, ValueError):
        matches = []
    res = dict(old.get("matches", {}))
    for m in matches:
        try:
            r = check_match(sid, m, logs)
        except Exception as e:   # one match that can't be read doesn't stop the others
            print(f"live check {m.get('id')}: {e}", flush=True)
            r = None
        if r:
            res[str(m["id"])] = r
    config.write_json(path, {"matches": res, "updated": dt.datetime.now().isoformat(timespec="minutes")})
    last = sorted(res.values(), key=lambda r: r["time"], reverse=True)[:5]
    return {"maps": summary(res), "matches": [{k: v for k, v in r.items() if k != "rounds"} | {"rounds": r["rounds"][:30]} for r in last],
            "calib": calibrate(res)}
