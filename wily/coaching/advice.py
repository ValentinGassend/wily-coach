"""Rule-based coaching advice from a player's analyzed matches (works for any SteamID)."""
from wily.insights.nades import _timer  # the game clock (1:55 at the start of the round)
from wily.core.i18n import num, tr, trn
import json
import os
from collections import defaultdict

PRICE = {"Flashbang": 200, "Smoke Grenade": 300, "High Explosive Grenade": 300, "Molotov": 400,
         "Incendiary Grenade": 500, "Decoy Grenade": 50}
PISTOLS = {"glock", "hkp2000", "usp_silencer", "p250", "fiveseven", "tec9", "cz75a", "deagle", "elite", "revolver"}
RIFLES = {"ak47", "m4a1", "m4a1_silencer", "aug", "sg556", "famas", "galilar"}
MAPN = lambda m: m.split("_", 1)[-1].capitalize()


def pl(n, word, plural=None):
    n = int(n)
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def pct(a, b):
    return round(100 * a / b) if b else None


def load_matches(pdir):
    out = []
    mdir = os.path.join(pdir, "matches")
    for mid in os.listdir(mdir) if os.path.exists(mdir) else []:
        f = os.path.join(mdir, mid, "stats.json")
        if os.path.exists(f):
            st = json.load(open(f, encoding="utf-8"))
            if not st.get("error"):
                out.append(st)
    return sorted(out, key=lambda s: s["match"].get("time") or "")


def metrics(stats):
    """Aggregate the per-match stats into the numbers the rules use."""
    M = defaultdict(float)
    spray = defaultdict(lambda: [0, 0.0])
    pist = [0, 0.0]
    rifl = [0, 0.0]
    for st in stats:
        o, ut = st["overview"], st["utility"]
        M["matches"] += 1
        M["rounds"] += st["rounds"]
        M["kills"] += o["kills"]
        M["deaths"] += o["deaths"]
        M["damage"] += o["damage"]
        M["traded"] += o["trades"]["my_deaths_traded"]
        M["open_w"] += o["opening_duels"]["won"]
        M["open_l"] += o["opening_duels"]["lost"]
        M["clutch"] += len(o["clutches"])
        M["clutch_w"] += sum(1 for c in o["clutches"] if c["won"])
        M["flash_thrown"] += ut["flashes_thrown"]
        M["flash_en"] += ut["enemies_flashed_1s+"]
        M["flash_mates"] += ut["teammates_flashed_1s+"]
        M["util_dmg"] += ut["utility_damage"]
        M["buy_mismatch"] += sum(1 for f in st["economy_flags"] if f["issue"] == "buy_mismatch")
        M["hs_kills"] += o["hs_kill_pct"] * o["kills"] / 100
        xh = (st["aim"].get("crosshair_placement") or {}).get("median_error_deg")
        if xh is not None:
            M["xh_sum"] += xh
            M["xh_n"] += 1
        for r in st["per_round"]:
            for g in r["grenades_unused_at_death"]:
                M["nades_unused"] += 1
                M["nades_value"] += PRICE.get(g, 0)
            M["nades_bought"] += len(r["grenades_bought"])
            left, tmin = r.get("money_left_after_buy"), r.get("team_min_start_money")
            if left is not None and left >= 3000 and tmin is not None and tmin < 2500 and r.get("team_buy") != "eco":
                M["drops_missed"] += 1
            d = r.get("death")
            if d:
                M["early_deaths"] += d["time_s"] <= 20
                M["last_alive_deaths"] += d["mates_alive_before"] == 0
                M["untraded_3"] += (not d["traded"]) and d["mates_alive_before"] >= 3
        for k, v in st["aim"]["spray_rifles"].items():
            spray[k][0] += v["shots"]
            spray[k][1] += v["shots"] * v["hit_pct"] / 100
        for w, v in st["aim"]["by_weapon"].items():
            if v.get("shots_while_moving_pct") is None:
                continue
            acc = pist if w in PISTOLS else rifl if w in RIFLES else None
            if acc is not None:
                acc[0] += v["shots"]
                acc[1] += v["shots"] * v["shots_while_moving_pct"] / 100
    M = dict(M)
    M["trade_pct"] = pct(M.get("traded", 0), M.get("deaths", 0))
    M["adr"] = round(M.get("damage", 0) / M["rounds"], 1) if M.get("rounds") else None
    M["hs"] = pct(M.get("hs_kills", 0), M.get("kills", 0))
    M["xh"] = round(M["xh_sum"] / M["xh_n"], 1) if M.get("xh_n") else None
    M["spray"] = {k: (v[0], round(100 * v[1] / v[0], 1) if v[0] else None) for k, v in spray.items()}
    M["pistol_moving"] = round(100 * pist[1] / pist[0]) if pist[0] >= 15 else None
    M["pistol_shots"] = pist[0]
    M["rifle_moving"] = round(100 * rifl[1] / rifl[0]) if rifl[0] >= 30 else None
    return M


def ctx_row(cross, name, i):
    for c in cross.get("contexts", []):
        if c["name"] == name:
            return c["rows"][i]
    return {}


def rules(M, cross, per_match=False):
    """Candidate problems, each with a severity score. per_match: thresholds for a single match."""
    n = max(M.get("matches", 1), 1)
    R = []

    def add(key, score, title, short, why, do):
        R.append({"id": key, "score": round(score, 1), "title": title, "short": short, "why": why, "do": do})

    tp = M.get("trade_pct")
    if tp is not None and M.get("deaths", 0) >= (8 if per_match else 20) and tp < 22:
        add("trade", 40 - tp + M.get("untraded_3", 0) / n, tr("Only {p}% of your deaths get traded", p=tp),
            tr("Play within 2 seconds of a teammate"),
            [tr("{a} deaths traded out of {b}.", a=int(M['traded']), b=int(M['deaths'])),
             tr("{n} deaths without a trade while 3 or more teammates were still alive.", n=int(M.get('untraded_3', 0))),
             trn(int(M.get('last_alive_deaths', 0)), "{n} death as the last one alive, {w} clutches won out of {c}.",
                 "{n} deaths as the last one alive, {w} clutches won out of {c}.", w=int(M.get('clutch_w', 0)), c=int(M.get('clutch', 0)))],
            [tr("Before a duel, check that a teammate is within 500 units and sees the angle."),
             tr("On attack, go in second behind a flash."), tr("On defense, play crossfires.")])
    un = M.get("nades_unused", 0)
    if un / n >= (4 if per_match else 6):
        add("nades", un / n * 2.2, tr("{n} grenades died with you (${v})", n=int(un), v=num(M.get('nades_value', 0))),
            tr("Empty your pockets before 40 s"),
            [tr("{n} grenades not thrown when you died, out of {b} in your inventory ({p}%).", n=int(un), b=int(M.get('nades_bought', 0)), p=pct(un, M.get('nades_bought', 0))),
             "{a}: {b}, {c}.".format(a=trn(int(M.get('flash_thrown', 0)), "{n} flash thrown", "{n} flashes thrown"),
                b=trn(int(M.get('flash_en', 0)), "{n} enemy flashed", "{n} enemies flashed"), c=trn(int(M.get('flash_mates', 0)), "{n} teammate flashed", "{n} teammates flashed"))],
            [tr("On attack, throw everything before 40 s into the round."), tr("On defense, molotov or HE at the first sound of a rush."),
             tr("Flash for a teammate who goes in.")])
    if cross and not per_match:
        h, pk = ctx_row(cross, "Movement at the start of the duel", 0), ctx_row(cross, "Movement at the start of the duel", 1)
        if h.get("n", 0) >= 15 and pk.get("n", 0) >= 15 and h["win"] - pk["win"] >= 15:
            add("hold", h["win"] - pk["win"], tr("You win {a}% when holding the angle, {b}% when peeking", a=h['win'], b=pk['win']),
                tr("Hold the angle, don't dry-peek"),
                [tr("{a} of your {b} duels start while moving.", a=pk['n'], b=cross['totals']['my_duels']),
                 tr("Other players: {a}% when holding, {b}% when peeking.", a=h['others_win'], b=pk['others_win'])],
                [tr("Let the enemy come to you."), tr("For info: a grenade or a jiggle-peek (one step, back)."),
                 tr("If you have to peek: flash first.")])
        fl = ctx_row(cross, "Flashes", 0)
        tot = cross["totals"]["my_duels"]
        if tot >= 40 and fl.get("n", 0) / tot < 0.05:
            add("flash", 14, tr("Only {a} duels out of {b} against a flashed enemy", a=fl.get('n', 0), b=tot),
                tr("Flash before every peek"),
                [tr("Your duels almost always happen without a flash from your team.")],
                [tr("Popflash before peeking a known angle."), tr("Ask a teammate for a flash ('flash me X').")])
        hp = ctx_row(cross, "Health at the start of the duel", 1)
        if hp.get("n", 0) >= 10 and hp["win"] < 42:
            add("hp", 12 + (42 - hp["win"]) / 3, tr("Under 50 HP, you win {p}% of your duels", p=hp['win']),
                tr("Hurt: fall back, leave the duel"),
                [tr("{n} duels taken with less than 50 HP.", n=hp['n'])],
                [tr("Fall back one angle, call your HP, cover a teammate's trade.")])
        lo, sh = ctx_row(cross, "Distance", 2), ctx_row(cross, "Distance", 0)
        if lo.get("n", 0) >= 15 and sh.get("n", 0) >= 15 and lo["win"] - sh["win"] >= 10:
            add("range", 8 + (lo["win"] - sh["win"]) / 3, tr("You win {a}% at range, {b}% up close", a=lo['win'], b=sh['win']),
                tr("Play long angles"),
                [tr("Your duels under 10 m are the riskiest.")],
                [tr("Pick deep positions (back of site, long angle)."), tr("Avoid corners where the enemy arrives 3 m away.")])
    pm = M.get("pistol_moving")
    if pm is not None and pm >= 40:
        add("pistol", pm - 22, tr("{p}% of your pistol shots are fired while moving", p=pm),
            tr("Counter-strafe with pistols"),
            [tr("Out of {n} pistol shots.", n=int(M['pistol_shots'])) + (" " + tr("With rifles: only {p}%.", p=M['rifle_moving']) if M.get("rifle_moving") is not None else "")],
            [tr("Full stop, 1 to 3 bullets, strafe."), tr("Warm-up: Aim Botz with the Glock/USP, a full stop before every shot.")])
    sp = M.get("spray", {})
    b1, b9 = sp.get("bullet_1", (0, None)), sp.get("bullets_9+", (0, None))
    if b9[0] >= (15 if per_match else 40) and b9[1] is not None and b9[1] < 12:
        add("spray", 14 + b9[0] / (10 * n), tr("After the 9th bullet, you hit {p}%", p=f"{b9[1]:.0f}"),
            tr("Bursts of 3 to 5 bullets"),
            [tr("1st bullet: {a}% hits. Bullets 9 and up: {b}% ({n} bullets).", a=f"{b1[1]:.0f}", b=f"{b9[1]:.0f}", n=int(b9[0]))],
            [tr("Short burst, strafe, repeat."), tr("Recoil Master: the first 10 bullets of the AK and the M4.")])
    dm = M.get("drops_missed", 0)
    bm = M.get("buy_mismatch", 0)
    if dm >= (2 if per_match else 3) or bm / n >= 5:
        add("eco", 8 + dm * 1.2 + bm / n * 0.5, tr("Your money and your team's are out of sync"),
            tr("Tab before buying, drop above $5,000"),
            [trn(int(dm), "{n} round where you had more than $3,000 left while a teammate couldn't buy.", "{n} rounds where you had more than $3,000 left while a teammate couldn't buy."),
             trn(int(bm), "{n} round where your type of buy differed from the team's.", "{n} rounds where your type of buy differed from the team's.")],
            [tr("Buy like the team (full, force or eco)."), tr("Drop a weapon to a poor teammate as soon as you have more than $5,000.")])
    ed = M.get("early_deaths", 0)
    if M.get("deaths", 0) and ed / M["deaths"] >= 0.2 and ed >= (3 if per_match else 8):
        add("early", 8 + 30 * ed / M["deaths"], tr("{n} deaths in the first 20 seconds", n=int(ed)),
            tr("No free duel before 20 s"),
            [tr("{p}% of your deaths happen before 20 s into the round.", p=pct(ed, M['deaths']))],
            [tr("Start of the round: take info, keep your position, don't open the round alone.")])
    return sorted(R, key=lambda r: -r["score"])


def strengths(M, cross):
    S = []
    if M.get("xh") is not None and M["xh"] <= 4:
        S.append(tr("Good crosshair placement ({d}° median offset before your duels)", d=M['xh']))
    if M.get("hs") and M["hs"] >= 50:
        S.append(tr("{p}% of kills are headshots", p=M['hs']))
    if M.get("adr") and M["adr"] >= 80:
        S.append(tr("{n} damage per round", n=M['adr']))
    if cross:
        h = ctx_row(cross, "Movement at the start of the duel", 0)
        if h.get("n", 0) >= 15 and h["win"] >= 60:
            S.append(tr("{p}% of duels won when holding the angle", p=h['win']))
    return S


def map_plans(stats, cross):
    """Per map and side: record, zones to exploit/avoid, timings, key grenades."""
    rec = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for st in stats:
        for r in st["per_round"]:
            rec[st["map"]][r["side"]][0] += bool(r["won"])
            rec[st["map"]][r["side"]][1] += 1
    plans = {}
    for m in cross.get("maps", []):
        hostage = m["map"].startswith("cs_")
        plans[m["map"]] = {}
        for side, S in m["sides"].items():
            role = ("defense" if side == "T" else "attack") if hostage else ("attack" if side == "T" else "defense")
            ex = sorted([z for z in S["zones"] if z["verdict"] == "exploit"], key=lambda z: -(z["k"] - z["d"]))[:3]
            av = sorted([z for z in S["zones"] if z["verdict"] == "avoid"], key=lambda z: -(z["d"] - z["k"]))[:3]
            freq = S["zones"][:3]
            bullets = []
            for z in ex:
                bullets.append({"kind": "exploit", "text": tr("<b>Play {zone} more</b>: {k}-{d} for you, other players win {p}% there.", zone=z['name'], k=z['k'], d=z['d'], p=z['others_win'])})
            for z in av:
                kf = ", " + tr("killed from {zones}", zones=", ".join(k['zone'] for k in z['killed_from'])) if z["killed_from"] else ""
                bullets.append({"kind": "avoid", "text": tr("<b>{zone}: avoid it or change your approach</b> ({k}-{d}{more}).", zone=z['name'], k=z['k'], d=z['d'], more=kf)})
            pz = S.get("pool_zones", [])
            opp = [z for z in pz if (z["win"] or 0) >= 56 and z["k"] + z["d"] >= 12 and z["my_presence"] < 4
                   and "spawn" not in z["key"].lower() and z["t_med"] <= 45][:2]
            for z in opp:
                hold = ", " + tr("mostly holding the angle") if (z['hold_pct'] or 0) >= 55 else ""
                bullets.append({"kind": "try", "text": tr("<b>Worth a try: {zone}</b>. {side}s in the base win {p}% of their duels there ({n} duels{hold}, around {t}). You only spend {m}% of your time there.",
                                                          zone=z['name'], side=side, p=z['win'], n=z['k'] + z['d'], hold=hold, t=_timer(z['t_med']), m=f"{z['my_presence']:.0f}")})
            mine_ok = {z["key"] for z in S["zones"] if z["k"] + z["d"] >= 3 and (z["win"] or 0) >= 55}
            trap = [z for z in pz[::-1] if (z["win"] or 100) <= 40 and z["k"] + z["d"] >= 12 and z["my_presence"] >= 4 and "spawn" not in z["key"].lower()
                    and z["key"] not in {a["key"] for a in av} and z["key"] not in mine_ok][:1]
            for z in trap:
                bullets.append({"kind": "avoid", "text": tr("<b>{zone}: trap zone</b>. {side}s in the base only win {p}% of their duels there ({n} duels), and you spend {m}% of your time there.",
                                                            zone=z['name'], side=side, p=z['win'], n=z['k'] + z['d'], m=f"{z['my_presence']:.0f}")})
            for z in freq:
                if z["early_contact_s"] is not None and z["early_contact_s"] < 60:
                    bullets.append({"kind": "timing", "text": tr("<b>{zone}</b> ({p}% of your time): first contacts around {t}, have a grenade ready before.", zone=z['name'], p=round(z['presence']), t=_timer(z['early_contact_s']))})
            # key grenades: one per type, favouring reproducible throws with evidence
            key, seen = [], set()
            for i, l in enumerate(S["lineups"]):
                if l["type"] in seen:
                    continue
                strong = (l["type"] == "smoke" and l["uses"] >= 3) or (l["type"] == "flash" and (l.get("enemies_blind_avg") or 0) >= 0.8) \
                    or (l["type"] in ("molotov", "he") and ((l.get("damage_avg") or 0) >= 8 or l["uses"] >= 4))
                if strong:
                    key.append(i)
                    seen.add(l["type"])
            w, t = rec[m["map"]][side]
            plans[m["map"]][side] = {"role": role, "record": [w, t], "bullets": bullets, "key_nades": key[:4]}
    return plans


def build(pdir):
    from wily.coaching import advice_ref
    from wily.base import reference
    stats = load_matches(pdir)
    cp = os.path.join(pdir, "cross.json")
    cross = json.load(open(cp, encoding="utf-8")) if os.path.exists(cp) else {}
    M = metrics(stats)
    steamid = os.path.basename(os.path.normpath(pdir))
    try:
        bench = reference.benchmarks(steamid)
    except Exception:
        bench = None
    R = advice_ref.enrich(rules(M, cross), bench)
    per_match = {}
    for st in stats:
        m1 = metrics([st])
        r1 = rules(m1, None, per_match=True)[:3]
        o = st["overview"]
        res = {"win": tr("Win"), "loss": tr("Loss"), "draw": tr("Draw")}[st["result"]]
        per_match[st["match"]["match_id"]] = {
            "summary": tr("{res} {a}-{b} on {map}: {k} kills, {d} deaths, {adr} damage per round, KAST {kast}%.", res=res, a=st['final_score']['me'],
                          b=st['final_score']['them'], map=MAPN(st['map']), k=o['kills'], d=o['deaths'], adr=o['adr'], kast=o['kast_pct']),
            "priorities": [{"level": "high" if i == 0 else "mid", "tags": [], "title": r["title"], "evidence": r["why"], "fix": r["do"]} for i, r in enumerate(r1)]}
    st_ = advice_ref.strengths_from_bench(bench) or strengths(M, cross)
    try:
        from wily.coaching import archetype
        xp = ((bench or {}).get("metrics", {}).get("xhair") or {}).get("percentile")
        arch = archetype.profile(steamid, xp)
    except Exception:
        arch = None
    try:
        from wily.base import proref
        pros = proref.for_player(steamid)
    except Exception:
        pros = None
    return {"metrics": {k: v for k, v in M.items() if not isinstance(v, dict)}, "rules": R, "strengths": st_, "bench": bench, "archetype": arch, "pros": pros,
            "maps": map_plans(stats, cross), "match_notes": per_match}


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(build(sys.argv[1]), ensure_ascii=False, indent=1))
