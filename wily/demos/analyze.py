"""Extract coaching stats for one player from a CS2 demo.

Usage: python -m wily.demos.analyze <demo.dem> [steamid64] > stats.json
analyze() reads the demo in steps: the rounds' bounds (_bounds), the money snapshots (_snapshots), the events
(_events), then each round (kills, opening, trades, KAST, clutch, money, grenades), then the aim (_aim), the
grenades over the match (_utility), the economy flags and the death timing, and the pro insights (pro_analyst).
"""
import json
from wily.base import pro_analyst
import math
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

ME_DEFAULT = None  # defaults to the Steam account logged in on this PC (config.logged_in_account)
TICKRATE = 64
TRADE_WINDOW = 5 * TICKRATE

GRENADES = {"weapon_flashbang", "weapon_hegrenade", "weapon_smokegrenade",
            "weapon_molotov", "weapon_incgrenade", "weapon_decoy"}
GRENADE_INV = {"Flashbang", "High Explosive Grenade", "Smoke Grenade",
               "Molotov", "Incendiary Grenade", "Decoy Grenade"}
RIFLES = {"weapon_ak47", "weapon_m4a1", "weapon_m4a1_silencer", "weapon_aug",
          "weapon_sg556", "weapon_famas", "weapon_galilar", "weapon_awp",
          "weapon_ssg08", "weapon_scar20", "weapon_g3sg1"}
PISTOLS = {"weapon_glock", "weapon_usp_silencer", "weapon_hkp2000", "weapon_p250",
           "weapon_fiveseven", "weapon_tec9", "weapon_cz75a", "weapon_deagle",
           "weapon_elite", "weapon_revolver"}
# ~34% of max speed: beyond this, first-shot accuracy collapses
MOVING_THRESHOLD = {"rifle": 75, "pistol": 85}


def weapon_class(w):
    if w in RIFLES:
        return "rifle"
    if w in PISTOLS:
        return "pistol"
    if w in GRENADES:
        return "grenade"
    if "knife" in w or w == "weapon_taser":
        return "melee"
    return "smg_shotgun"


WEAPON_ALIASES = {"m4a1_silencer": "m4a1", "usp_silencer": "hkp2000", "m4a1_silencer_off": "m4a1",
                  "usp_silencer_off": "hkp2000", "knife_t": "knife"}


def norm_weapon(w):
    w = w.replace("weapon_", "")
    return WEAPON_ALIASES.get(w, w)


def sid(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def view_error_deg(ex, ey, ez, pitch, yaw, tx, ty, tz):
    p, y = math.radians(pitch), math.radians(yaw)
    view = np.array([math.cos(p) * math.cos(y), math.cos(p) * math.sin(y), -math.sin(p)])
    to = np.array([tx - ex, ty - ey, tz - ez])
    n = np.linalg.norm(to)
    if n < 1:
        return None
    to /= n
    total = math.degrees(math.acos(max(-1.0, min(1.0, float(view @ to)))))
    # vertical error: difference between aimed pitch and needed pitch
    need_pitch = -math.degrees(math.asin(max(-1.0, min(1.0, to[2]))))
    return total, pitch - need_pitch  # >0 = aiming too low


def _bounds(p):
    """The rounds: [freeze end, next freeze end), with their start, buy end and end; the match's last tick."""
    freeze = p.parse_event("round_freeze_end")["tick"].tolist()
    buyend = p.parse_event("buytime_ended")["tick"].tolist() if "buytime_ended" in p.list_game_events() else []
    poststart = p.parse_event("round_poststart")["tick"].tolist()
    ends = p.parse_event("round_officially_ended")["tick"].drop_duplicates().tolist()
    last_tick = int(p.parse_event("cs_win_panel_match")["tick"].max()) if "cs_win_panel_match" in p.list_game_events() else None

    # round boundaries: [freeze_end, next freeze_end)
    rounds = []
    for i, ft in enumerate(freeze):
        nxt = freeze[i + 1] if i + 1 < len(freeze) else (last_tick or ft + 200 * TICKRATE) + 1
        start = max([t for t in poststart if t <= ft], default=ft - 20 * TICKRATE)
        be = min([t for t in buyend if ft <= t < nxt], default=ft + 20 * TICKRATE)
        end = min([t for t in ends if ft < t <= nxt], default=nxt - 1)
        rounds.append({"n": i + 1, "start": start, "freeze_end": ft, "buy_end": be, "end": end, "next": nxt})
    return rounds, last_tick


def _round_of(rounds):
    """tick -> its round's number (None outside the rounds)."""
    def round_of(tick):
        for r in rounds:
            if r["start"] <= tick < r["next"]:
                return r["n"]
        return None
    return round_of


def _snapshots(p, rounds, last_tick):
    """Money, equipment, inventory, score and life of everyone at the key ticks of each round: at(tick, steamid, col)."""
    # ---------- snapshots at key ticks ----------
    snap_ticks = sorted({r["start"] + 1 for r in rounds} | {r["freeze_end"] for r in rounds}
                        | {r["buy_end"] for r in rounds} | {r["end"] for r in rounds}
                        | ({last_tick} if last_tick else set()))
    snap = p.parse_ticks(["team_num", "balance", "current_equip_value", "inventory", "team_rounds_total",
                          "is_alive", "has_helmet", "has_defuser", "armor_value", "round_start_equip_value"], ticks=snap_ticks)
    snap["steamid"] = snap["steamid"].map(sid)
    snap = snap.set_index(["tick", "steamid"]).sort_index()

    def at(tick, steamid, col):
        try:
            v = snap.loc[(tick, steamid), col]
        except KeyError:
            return None
        if isinstance(v, pd.Series):  # duplicated rows (reconnect)
            v = v.iloc[0]
        if isinstance(v, float) and math.isnan(v):
            return None
        return v
    return at


def _events(p, me, round_of):
    """The demo's events: deaths, damage (the real damage: not more than the health left), your shots, flashes."""
    # ---------- events ----------
    deaths = p.parse_event("player_death", player=["X", "Y", "last_place_name"], other=["total_rounds_played"])
    for c in ("attacker_steamid", "user_steamid", "assister_steamid"):
        deaths[c] = deaths[c].map(sid)
    deaths["round"] = deaths["tick"].map(round_of)
    deaths = deaths[deaths["round"].notna()]

    hurt = p.parse_event("player_hurt")
    for c in ("attacker_steamid", "user_steamid"):
        hurt[c] = hurt[c].map(sid)
    hurt["round"] = hurt["tick"].map(round_of)
    hurt = hurt.sort_values("tick")
    hp = {}
    real = []
    for _, h in hurt.iterrows():
        key = (h["round"], h.user_steamid)
        before = hp.get(key, 100)
        real.append(min(int(h.dmg_health), before))
        hp[key] = max(int(h.health), 0)
    hurt["real_dmg"] = real

    fires = p.parse_event("weapon_fire", player=["velocity_X", "velocity_Y"])
    fires["user_steamid"] = fires["user_steamid"].map(sid)
    myfires = fires[fires.user_steamid == me].copy()
    myfires["round"] = myfires["tick"].map(round_of)
    myfires["speed"] = np.hypot(myfires["user_velocity_X"], myfires["user_velocity_Y"])

    blind = p.parse_event("player_blind")
    for c in ("attacker_steamid", "user_steamid"):
        blind[c] = blind[c].map(sid)
    if len(blind):
        blind["round"] = blind["tick"].map(round_of)
    return deaths, hurt, myfires, blind


# the events analyze() reads, in one pass of the demo (onepass.py, 15/10: 28 reads of the demo before)
EVENTS = {"round_freeze_end": ((), ()), "buytime_ended": ((), ()), "round_poststart": ((), ()),
          "round_officially_ended": ((), ()), "cs_win_panel_match": ((), ()),
          "player_death": (("X", "Y", "last_place_name"), ("total_rounds_played",)), "player_hurt": ((), ()),
          "weapon_fire": (("velocity_X", "velocity_Y"), ()), "player_blind": ((), ())}


def analyze(path, me):
    from wily.demos import onepass
    p = onepass.Parser(path, EVENTS)
    header = p.parse_header()
    players = p.parse_player_info()
    players["steamid"] = players["steamid"].map(sid)
    if me not in set(players["steamid"]):
        return {"error": "player_not_in_demo", "map": header.get("map_name")}
    names = dict(zip(players.steamid, players.name))
    rounds, last_tick = _bounds(p)
    round_of = _round_of(rounds)
    at = _snapshots(p, rounds, last_tick)
    deaths, hurt, myfires, blind = _events(p, me, round_of)

    # team per round (for me and everyone)
    def team_of(steamid, r):
        return at(r["freeze_end"], steamid, "team_num")

    # ---------- per round ----------
    per_round = []
    totals = Counter()
    death_list = []
    opening = {"won": 0, "lost": 0}
    trades = {"my_deaths_traded": 0, "my_deaths": 0, "trade_kills": 0}
    clutches = []
    multikills = Counter()
    kast_rounds = 0
    my_side_rounds = Counter()
    score = {"me": 0, "them": 0}
    foes_of = {}   # round -> the enemies' SteamIDs (the pro insights count your flashes on them only)

    # your inventory just before each of your deaths, in one read of the demo (one read per death before, 15/10)
    mine = deaths[deaths.user_steamid == me]
    inv_all = p.parse_ticks(["inventory"], ticks=sorted({int(t) - 2 for t in mine.tick}), players=[me]) if len(mine) else None

    for idx, r in enumerate(rounds):
        myteam = team_of(me, r)
        if myteam is None:
            continue
        side = "T" if myteam == 2 else "CT"
        my_side_rounds[side] += 1
        mates = [s for s in players.steamid if team_of(s, r) == myteam]
        foes = [s for s in players.steamid if team_of(s, r) not in (None, myteam)]
        foes_of[r["n"]] = set(foes)

        # winner from score change
        after_tick = rounds[idx + 1]["freeze_end"] if idx + 1 < len(rounds) else (last_tick or r["end"])
        my_before = at(r["freeze_end"], me, "team_rounds_total") or 0
        my_after = at(after_tick, me, "team_rounds_total")
        foe_ref = foes[0] if foes else None
        foe_after = at(after_tick, foe_ref, "team_rounds_total") if foe_ref else None
        won = None
        if my_after is not None:
            won = bool(my_after > my_before)
        if my_after is not None and foe_after is not None:
            score = {"me": int(my_after), "them": int(foe_after)}

        rd = deaths[deaths["round"] == r["n"]].sort_values("tick")
        rh = hurt[(hurt["round"] == r["n"]) & (hurt.attacker_steamid == me)]
        enemy_hurt = rh[rh.user_steamid.isin(foes)]
        dmg = int(enemy_hurt["real_dmg"].sum())

        my_kills = rd[(rd.attacker_steamid == me) & (rd.user_steamid.isin(foes))]
        my_death = rd[rd.user_steamid == me]
        my_assists = rd[(rd.assister_steamid == me) & (rd.user_steamid.isin(foes))]
        k, d, a = len(my_kills), len(my_death), len(my_assists)
        if k >= 2:
            multikills[f"{k}k"] += 1

        # opening duel
        if len(rd):
            first = rd.iloc[0]
            if first.attacker_steamid == me:
                opening["won"] += 1
            elif first.user_steamid == me:
                opening["lost"] += 1
            open_flag = "won" if first.attacker_steamid == me else ("lost" if first.user_steamid == me else None)
        else:
            open_flag = None

        # trades
        traded = False
        death_info = None
        if d:
            dt = my_death.iloc[0]
            trades["my_deaths"] += 1
            killer = dt.attacker_steamid
            revenge = rd[(rd.user_steamid == killer) & (rd.attacker_steamid.isin(mates)) &
                         (rd.tick > dt.tick) & (rd.tick <= dt.tick + TRADE_WINDOW)]
            traded = len(revenge) > 0
            trades["my_deaths_traded"] += int(traded)
            before = rd[rd.tick < dt.tick]
            mates_alive = len([m for m in mates if m != me and m not in set(before.user_steamid)])
            foes_alive = len([f for f in foes if f not in set(before.user_steamid)])
            death_info = {
                "round": r["n"], "side": side,
                "time_s": round((dt.tick - r["freeze_end"]) / TICKRATE, 1),
                "killer_weapon": dt.weapon, "headshot": bool(dt.headshot),
                "distance": round(float(dt.distance), 1) if pd.notna(dt.distance) else None,
                "traded": traded, "mates_alive_before": mates_alive, "foes_alive_before": foes_alive,
                "place": dt.get("user_last_place_name") or None,
                "pos": [round(float(dt.user_X)), round(float(dt.user_Y))],
            }
        for _, kk in my_kills.iterrows():
            victim_kills = rd[(rd.attacker_steamid == kk.user_steamid) & (rd.user_steamid.isin(mates)) &
                              (rd.tick < kk.tick) & (rd.tick >= kk.tick - TRADE_WINDOW)]
            if len(victim_kills):
                trades["trade_kills"] += 1

        survived = d == 0
        if k or a or survived or traded:
            kast_rounds += 1

        clutch = _clutch(rd, mates, foes, me, r["n"])
        if clutch:
            clutch["won"] = won
            clutches.append(clutch)

        equip, left, start_money, inv, team_equip, team_money_start, foe_equip = _money(at, r["freeze_end"], me, mates, foes)
        buy_type = _buy_type

        # utility
        nades_bought = [x for x in inv if x in GRENADE_INV]
        thrown = myfires[(myfires["round"] == r["n"]) & (myfires.weapon.isin(GRENADES))].weapon.tolist()
        unused_at_death = []
        if d:
            dt_tick = int(my_death.iloc[0].tick)
            inv_death = inv_all[inv_all.tick == dt_tick - 2] if inv_all is not None and len(inv_all) else []
            if len(inv_death):
                unused_at_death = [x for x in inv_death.iloc[0]["inventory"] if x in GRENADE_INV]
            death_info["unused_grenades"] = unused_at_death
            death_list.append(death_info)

        rb = blind[(blind.attacker_steamid == me) & (blind["tick"] >= r["start"]) & (blind["tick"] < r["next"])]
        util_dmg = int(enemy_hurt[enemy_hurt.weapon.isin(["hegrenade", "inferno", "molotov", "incgrenade"])]["real_dmg"].sum())

        per_round.append({
            "round": r["n"], "side": side, "won": won,
            "kills": k, "deaths": d, "assists": a, "damage": dmg,
            "opening": open_flag, "clutch": clutch,
            "start_money_approx": int(start_money) if start_money is not None else None,
            "equip_value": int(equip) if equip is not None else None,
            "money_left_after_buy": int(left) if left is not None else None,
            "my_buy": buy_type(equip),
            "team_avg_equip": int(np.mean(team_equip)) if team_equip else None,
            "team_buy": buy_type(np.mean(team_equip)) if team_equip else None,
            "team_min_start_money": int(min(team_money_start)) if team_money_start else None,
            "enemy_avg_equip": int(np.mean(foe_equip)) if foe_equip else None,
            "weapons": [x for x in inv if x not in GRENADE_INV and "nife" not in x and x != "C4"],
            "grenades_bought": nades_bought, "grenades_thrown": [t.replace("weapon_", "") for t in thrown],
            "grenades_unused_at_death": unused_at_death,
            "enemies_flashed": int(((rb.user_steamid.isin(foes)) & (rb.blind_duration > 1.0)).sum()),
            "teammates_flashed": int(((rb.user_steamid.isin(mates)) & (rb.user_steamid != me) & (rb.blind_duration > 1.0)).sum()),
            "utility_damage": util_dmg,
            "death": death_info,
        })
        totals.update({"kills": k, "deaths": d, "assists": a, "damage": dmg})

    n_rounds = len(per_round)
    by_weapon, hs_pct, spray, bursts, crosshair = _aim(p, me, myfires, hurt, deaths)
    util = _utility(me, myfires, blind, deaths, per_round)
    eco_flags = _economy_flags(per_round)
    timing = _death_timing(death_list)

    return {
        "demo": path.split("\\")[-1],
        "map": header.get("map_name"),
        "server": header.get("server_name"),
        "player": {"steamid": str(me), "name": names.get(me)},
        "rounds": n_rounds, "final_score": score,
        "result": "win" if score["me"] > score["them"] else ("loss" if score["me"] < score["them"] else "draw"),
        "rounds_per_side": dict(my_side_rounds),
        "overview": {
            **totals, "adr": round(totals["damage"] / max(n_rounds, 1), 1),
            "kd": round(totals["kills"] / max(totals["deaths"], 1), 2),
            "hs_kill_pct": hs_pct, "kast_pct": round(100 * kast_rounds / max(n_rounds, 1), 1),
            "opening_duels": opening, "multikills": dict(multikills),
            "trades": trades, "clutches": clutches,
            "rounds_won_on_side": {s: sum(1 for r in per_round if r["side"] == s and r["won"]) for s in ("T", "CT")},
        },
        "aim": {"by_weapon": by_weapon, "spray_rifles": spray, "burst_lengths": dict(bursts), "crosshair_placement": crosshair},
        "utility": util,
        "economy_flags": eco_flags,
        "death_timing": timing,
        "deaths": death_list,
        "per_round": per_round,
        "pro_insights": pro_analyst.pro_insights(me, per_round, deaths, hurt, blind, foes_of, TICKRATE),
    }


def _clutch(rd, mates, foes, me, n):
    """A clutch: the moment you are the last one alive on your team with enemies left (the round's deaths in order)."""
    alive_mates = set(mates)
    alive_foes = set(foes)
    clutch = None
    for _, ev in rd.iterrows():
        alive_mates.discard(ev.user_steamid)
        alive_foes.discard(ev.user_steamid)
        if clutch is None and alive_mates == {me} and alive_foes:
            clutch = {"round": n, "vs": len(alive_foes)}
    return clutch


def _money(at, ft, me, mates, foes):
    """At the freeze end: your equipment, money left, money at the start (approx), inventory; your team's and the
    enemies' equipment, your team's money at the start."""
    equip = at(ft, me, "current_equip_value")
    left = at(ft, me, "balance")
    carried = at(ft, me, "round_start_equip_value") or 0
    start_money = (left + equip - carried) if left is not None and equip is not None else None
    inv = at(ft, me, "inventory") or []
    team_equip = [at(ft, m, "current_equip_value") or 0 for m in mates]
    team_money_start = []
    for m in mates:
        l, e, c = at(ft, m, "balance"), at(ft, m, "current_equip_value"), at(ft, m, "round_start_equip_value")
        if l is not None and e is not None:
            team_money_start.append(l + e - (c or 0))
    foe_equip = [at(ft, f, "current_equip_value") or 0 for f in foes]
    return equip, left, start_money, inv, team_equip, team_money_start, foe_equip


def _buy_type(v):
    if v is None:
        return None
    return "eco" if v < 1500 else ("force/half" if v < 3700 else "full")


def _aim(p, me, myfires, hurt, deaths):
    """Per weapon (accuracy, kills, shots while moving), headshots, the spray by bullet index, the bursts' lengths and
    the crosshair placement before your first shot of each fight."""
    # ---------- aim ----------
    myfires["wn"] = myfires.weapon.map(norm_weapon)
    by_weapon = {}
    for wn, g in myfires[~myfires.weapon.isin(GRENADES)].groupby("wn"):
        cls = weapon_class("weapon_" + wn if not wn.startswith("weapon_") else wn)
        if wn in ("m4a1", "hkp2000"):
            cls = "rifle" if wn == "m4a1" else "pistol"
        if cls == "melee":
            continue
        hits = hurt[(hurt.attacker_steamid == me) & (hurt.weapon.map(norm_weapon) == wn)]
        wk = deaths[(deaths.attacker_steamid == me) & (deaths.weapon.map(norm_weapon) == wn)]
        thr = MOVING_THRESHOLD.get(cls)
        by_weapon[wn] = {
            "class": cls, "shots": int(len(g)), "hits": int(len(hits)),
            "accuracy_pct": round(100 * len(hits) / len(g), 1) if len(g) else None,
            "kills": int(len(wk)), "hs_kills": int(wk.headshot.sum()),
            "shots_while_moving_pct": round(100 * (g.speed > thr).mean(), 1) if thr else None,
            "median_speed_when_firing": round(float(g.speed.median()), 1),
        }
    kills_all = deaths[(deaths.attacker_steamid == me) & (deaths.user_steamid != me)]
    hs_pct = round(100 * kills_all.headshot.mean(), 1) if len(kills_all) else 0

    # spray: accuracy by bullet index in a burst (rifles)
    rf = myfires[myfires.weapon.isin(RIFLES - {"weapon_awp", "weapon_ssg08"})].sort_values("tick")
    burst_idx = []
    last_t, i = -999, 0
    for t in rf["tick"]:
        i = i + 1 if t - last_t <= 10 else 1
        burst_idx.append(i)
        last_t = t
    rf = rf.assign(burst=burst_idx)
    my_hurt_ticks = set(hurt[hurt.attacker_steamid == me]["tick"])
    rf["hit"] = rf["tick"].apply(lambda t: any((t + dtk) in my_hurt_ticks for dtk in range(0, 3)))
    spray = {}
    for lo, hi, label in ((1, 1, "bullet_1"), (2, 3, "bullets_2-3"), (4, 8, "bullets_4-8"), (9, 99, "bullets_9+")):
        s = rf[(rf.burst >= lo) & (rf.burst <= hi)]
        if len(s):
            spray[label] = {"shots": int(len(s)), "hit_pct": round(100 * s.hit.mean(), 1)}
    bursts = Counter()
    for b, nxt in zip(burst_idx, burst_idx[1:] + [1]):
        if nxt == 1:
            bursts["1" if b == 1 else ("2-3" if b <= 3 else ("4-8" if b <= 8 else "9+"))] += 1

    # crosshair placement: angle to enemy head ~125ms before my first shot of each engagement
    eng = hurt[(hurt.attacker_steamid == me)].sort_values("tick")
    eng = eng[~eng.weapon.isin(["hegrenade", "inferno", "molotov", "incgrenade", "flashbang", "smokegrenade"])]
    samples = []
    last_hit = {}
    for _, h in eng.iterrows():
        v = h.user_steamid
        if v in last_hit and h.tick - last_hit[v] < 3 * TICKRATE:
            last_hit[v] = h.tick
            continue
        last_hit[v] = h.tick
        f = myfires[(myfires.tick <= h.tick) & (myfires.tick >= h.tick - TICKRATE) & (~myfires.weapon.isin(GRENADES))]
        if not len(f):
            continue
        samples.append((int(f.tick.min()) - 8, v))
    xh = []
    if samples:
        tk = sorted({t for t, _ in samples})
        pos = p.parse_ticks(["X", "Y", "Z", "pitch", "yaw", "ducking"], ticks=tk)
        pos["steamid"] = pos["steamid"].map(sid)
        pos = pos.set_index(["tick", "steamid"])
        for t, v in samples:
            try:
                m, e = pos.loc[(t, me)], pos.loc[(t, v)]
            except KeyError:
                continue
            eye = 46 if m.get("ducking", False) else 64
            head = 46 if e.get("ducking", False) else 64
            res = view_error_deg(m.X, m.Y, m.Z + eye, m.pitch, m.yaw, e.X, e.Y, e.Z + head)
            if res:
                xh.append(res)
    crosshair = None
    if xh:
        tot = np.array([a for a, _ in xh])
        vert = np.array([b for _, b in xh])
        crosshair = {
            "engagements": len(xh),
            "median_error_deg": round(float(np.median(tot)), 1),
            "pct_within_5deg": round(100 * float((tot <= 5).mean()), 1),
            "pct_over_15deg": round(100 * float((tot > 15).mean()), 1),
            "median_vertical_error_deg": round(float(np.median(vert)), 1),
            "note": "angle between view direction and enemy head ~125ms before first shot; vertical >0 = aimed below head",
        }
    return by_weapon, hs_pct, spray, bursts, crosshair


def _utility(me, myfires, blind, deaths, per_round):
    """Your grenades over the match: thrown, flashes on enemies and teammates, flash assists, damage, unused at death."""
    # ---------- utility totals ----------
    my_blinds = blind[blind.attacker_steamid == me]
    util = {
        "flashes_thrown": int((myfires.weapon == "weapon_flashbang").sum()),
        "smokes_thrown": int((myfires.weapon == "weapon_smokegrenade").sum()),
        "he_thrown": int((myfires.weapon == "weapon_hegrenade").sum()),
        "molotovs_thrown": int(myfires.weapon.isin(["weapon_molotov", "weapon_incgrenade"]).sum()),
        "enemies_flashed_1s+": sum(r["enemies_flashed"] for r in per_round),
        "teammates_flashed_1s+": sum(r["teammates_flashed"] for r in per_round),
        "flash_assists": int(((deaths.assister_steamid == me) & deaths.assistedflash).sum()),
        "utility_damage": sum(r["utility_damage"] for r in per_round),
        "grenades_unused_at_death": sum(len(r["grenades_unused_at_death"]) for r in per_round),
        "self_flashed_1s+": int(((my_blinds.user_steamid == me) & (my_blinds.blind_duration > 1.0)).sum()),
    }
    return util


def _economy_flags(per_round):
    """The rounds where your buy differs from your team's, or you kept $3,000 on a full buy."""
    # ---------- economy flags ----------
    eco_flags = []
    for r in per_round:
        if r["my_buy"] and r["team_buy"] and r["my_buy"] != r["team_buy"] and r["round"] not in (1, 13):
            eco_flags.append({"round": r["round"], "issue": "buy_mismatch", "me": r["my_buy"],
                              "team": r["team_buy"], "my_equip": r["equip_value"],
                              "team_avg": r["team_avg_equip"], "won": r["won"]})
        if r["money_left_after_buy"] and r["money_left_after_buy"] >= 3000 and r["my_buy"] == "full":
            eco_flags.append({"round": r["round"], "issue": "big_unspent_money_on_full_buy",
                              "left": r["money_left_after_buy"]})
    return eco_flags


def _death_timing(death_list):
    """When you die in the round, and the untraded deaths with 3 teammates or more alive."""
    # ---------- death timing ----------
    dts = [d["time_s"] for d in death_list]
    timing = {
        "deaths_first_20s": sum(t <= 20 for t in dts),
        "deaths_20_60s": sum(20 < t <= 60 for t in dts),
        "deaths_after_60s": sum(t > 60 for t in dts),
        "deaths_with_3plus_mates_alive_untraded": sum(1 for d in death_list if not d["traded"] and d["mates_alive_before"] >= 3),
    }
    return timing


if __name__ == "__main__":
    from wily.core import config
    me = int(sys.argv[2]) if len(sys.argv) > 2 else (ME_DEFAULT or config.logged_in_account()[0])
    out = analyze(sys.argv[1], me)
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)))
