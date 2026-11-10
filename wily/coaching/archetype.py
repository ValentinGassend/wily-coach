"""Player archetype from weapons, movement, game sense, playstyle and reactions, relative to the reference base."""
from wily.insights.nades import _timer  # the game clock (1:55 at the start of the round)
from wily.core.i18n import N_, tr
import numpy as np
import pandas as pd

from wily.demos import style

MIN_ROUNDS_REF = 20
ROLES = {
    "awper": {"name": N_("AWPer"), "icon": "🎯",
              "what": N_("Holds long angles and takes the first kill with the AWP. Their economy and positioning set the team's pace."),
              "tips": [N_("Change spot after every shot: an AWPer who re-peeks the same angle gets punished."),
                       N_("Play next to a teammate who trades or flashes for you: the AWP costs $4,750, don't lose it alone."),
                       N_("On an eco, save the AWP rather than playing it 1v3.")],
              "key": [("awp_share", N_("share of kills with the AWP")), ("open_win", N_("opening duels won")), ("hold_share", N_("duels started standing still"))]},
    "entry": {"name": N_("Entry fragger"), "icon": "⚡",
              "what": N_("First onto the site when attacking, to take space. Their death is acceptable if it gets traded."),
              "tips": [N_("Always go in behind a flash (yours or a teammate's), never dry."),
                       N_("Call your entry so your second is ready to trade within the second."),
                       N_("Pre-aim the most likely angles in order: your survival depends on your first bullet.")],
              "key": [("open_rate_T", N_("opening duels taken per round as T")), ("open_win", N_("opening duels won")), ("traded_share", N_("deaths traded"))]},
    "trader": {"name": N_("Second entry / Trader"), "icon": "🔁",
               "what": N_("Follows the entry at short range and trades every death. Turns a lost 1v1 into an even exchange."),
               "tips": [N_("Stay within 500 units of your entry, in the same line of sight."),
                        N_("Pre-aim the angle your teammate will get shot from, not the one they are looking at."),
                        N_("Don't peek at the same time as them: one beat later, then the trade.")],
               "key": [("trade_rate", N_("trades per round")), ("trade_time", N_("trade delay (s)")), ("iso_T", N_("distance to nearest teammate as T"))]},
    "lurker": {"name": N_("Lurker"), "icon": "🐍",
               "what": N_("Plays alone, far from the group, to cut rotations and catch defenders from behind at the right moment."),
               "tips": [N_("Your timing matters more than your aim: strike when the team executes, not before."),
                        N_("Give info: you are often the only one who sees the enemy rotations."),
                        N_("If the round is already lost, save your weapon: a lurker who dies without impact is expensive.")],
               "key": [("iso_T", N_("distance to nearest teammate as T")), ("late_share", N_("share of kills after 0:55")), ("first_duel_t", N_("first duel of the round (clock)"))]},
    "support": {"name": N_("Support"), "icon": "🛡️",
                "what": N_("Prepares the ground with grenades (smokes, flashes, molotovs) and plays so teammates win their duels."),
                "tips": [N_("Learn the full executes of your maps: 2 smokes, 2 flashes, 1 molotov per site."),
                         N_("Flash for your teammates: call it, then throw it over the wall."),
                         N_("Keep a grenade for the retake or the post-plant.")],
                "key": [("util_pr", N_("grenades per round")), ("blind_pr", N_("enemies flashed per round")), ("util_dmg_pr", N_("grenade damage per round"))]},
    "anchor": {"name": N_("Anchor"), "icon": "⚓",
               "what": N_("On defense, holds a site, often alone, and buys time until rotations arrive. Patience and defensive utility."),
               "tips": [N_("Your goal is to delay, not to kill: molotov and smoke at the first noise."),
                        N_("Change position from one round to the next so you don't get pre-aimed."),
                        N_("Play deep when you are alone: fall back and wait for the retake rather than dying 1v3.")],
               "key": [("ct_site", N_("time spent on a site as CT")), ("hold_share", N_("duels started standing still")), ("ct_top", N_("focus on one zone as CT"))]},
    "closer": {"name": N_("Closer / Clutcher"), "icon": "🧊",
               "what": N_("Gets their kills late in the round: post-plant, retake, clutches. Keeps calm when the round is decided."),
               "tips": [N_("Play the clock and the bomb in a clutch: isolate duels one by one."),
                        N_("Stay alive early in the round: your impact comes later."),
                        N_("In the post-plant, play the angles that see the bomb, not the enemy spawn.")],
               "key": [("late_share", N_("share of kills after 0:55")), ("kpr", N_("kills per round")), ("hold_share", N_("duels started standing still"))]},
}
SOURCES = [("Refrag, the roles of a CS2 team", "https://refrag.gg/blog/cs2-team-roles-explained/"),
           ("Esports.gg, every role in CS2", "https://esports.gg/news/counter-strike-2/all-roles-in-cs2/"),
           ("CS2Hype, the entry fragger role", "https://cs2hype.com/roles/entry-fragger"),
           ("CS2Hype, the rifler role", "https://cs2hype.com/roles/rifler")]
WEAPON_FR = {"ak47": "AK-47", "m4a1": "M4A4", "m4a1_silencer": "M4A1-S", "awp": "AWP", "ssg08": "Scout", "deagle": "Desert Eagle",
             "galilar": "Galil", "famas": "FAMAS", "aug": "AUG", "sg556": "SG 553", "mac10": "MAC-10", "mp9": "MP9", "mp7": "MP7",
             "ump45": "UMP-45", "p90": "P90", "glock": "Glock", "usp_silencer": "USP-S", "hkp2000": "P2000", "p250": "P250",
             "tec9": "Tec-9", "fiveseven": "Five-SeveN", "cz75a": "CZ75", "mag7": "MAG-7", "nova": "Nova", "xm1014": "XM1014"}


def aggregate(df):
    """Per-player pooled features."""
    g = df.groupby("steamid")
    s = lambda c: g[c].sum()

    def wmean(col, w):
        x = df[[col, w, "steamid"]].dropna()
        x = x[x[w] > 0]
        return (x[col] * x[w]).groupby(x.steamid).sum() / x.groupby("steamid")[w].sum()
    out = pd.DataFrame({"name": g["name"].last(), "rounds": s("rounds"), "t_rounds": s("t_rounds"), "ct_rounds": s("ct_rounds"),
                        "kills": s("kills"), "deaths": s("deaths"), "matches": g.size()})
    k = out.kills.clip(lower=1)
    out["kpr"] = out.kills / out.rounds.clip(lower=1)
    for c in ("awp", "rifle", "smg", "shotgun", "pistol", "deagle"):
        out[f"{c}_share"] = s(f"k_{c}") / k
    out["open_rate"] = s("open_att") / out.rounds.clip(lower=1)
    out["open_rate_T"] = s("open_att_T") / out.t_rounds.clip(lower=1)
    out["open_win"] = s("open_won") / s("open_att").clip(lower=1)
    out["trade_rate"] = s("trade_kills") / out.rounds.clip(lower=1)
    out["traded_share"] = s("traded_deaths") / out.deaths.clip(lower=1)
    out["hs_share"] = s("hs_kills") / k
    out["late_share"] = s("late_kills") / k
    out["early_share"] = s("early_kills") / k
    util = s("flashes") + s("smokes") + s("molotovs") + s("hes")
    out["util_pr"] = util / out.rounds.clip(lower=1)
    out["flash_pr"] = s("flashes") / out.rounds.clip(lower=1)
    out["blind_pr"] = s("flash_enemies") / out.rounds.clip(lower=1)
    out["util_dmg_pr"] = s("util_dmg") / out.rounds.clip(lower=1)
    out["iso_T"] = wmean("iso_T", "t_rounds")
    out["iso_CT"] = wmean("iso_CT", "ct_rounds")
    out["move_share"] = wmean("move_share", "duels")
    out["hold_share"] = wmean("hold_share", "duels")
    out["scoped"] = wmean("scoped_share", "duels")
    out["first_duel_t"] = wmean("first_duel_t", "rounds")
    out["duel_len_won"] = wmean("duel_len_won", "kills")
    out["trade_time"] = wmean("trade_time", "trade_kills")
    out["ct_site"] = wmean("ct_site_share", "ct_rounds")
    out["ct_top"] = wmean("ct_top_zone_share", "ct_rounds")
    return out


def top_weapons(df, steamid):
    c = {}
    for tw in df[df.steamid == steamid].top_weapons.dropna():
        for part in tw.split(";"):
            if ":" in part:
                w, n = part.rsplit(":", 1)
                c[w] = c.get(w, 0) + int(n)
    return sorted(c.items(), key=lambda x: -x[1])[:4]


def pct_table(ref, cols):
    return {c: ref[c].dropna().sort_values().to_numpy() for c in cols}


def pct(sorted_vals, v):
    if v is None or pd.isna(v) or not len(sorted_vals):
        return None
    return float(np.searchsorted(sorted_vals, v, side="right") / len(sorted_vals) * 100)


def _pcts(sorted_vals, col):
    """pct() of every value of a column: a list of floats and None."""
    if not len(sorted_vals):
        return [None] * len(col)
    na = col.isna().to_numpy()
    v = col.to_numpy(dtype=float, na_value=np.nan)
    p = np.searchsorted(sorted_vals, v, side="right") / len(sorted_vals) * 100
    return [None if n else float(x) for n, x in zip(na, p)]


def scores(P):
    """Role scores (0-100) from percentiles P (dict metric -> percentile)."""
    p = lambda k, inv=False: (100 - P[k] if inv else P[k]) if P.get(k) is not None else 50
    sc = {
        "awper": 0.6 * p("awp_share") + 0.4 * p("scoped"),
        "entry": 0.45 * p("open_rate_T") + 0.25 * p("move_share") + 0.3 * p("first_duel_t", True),
        "trader": 0.5 * p("trade_rate") + 0.3 * p("iso_T", True) + 0.2 * p("trade_time", True),
        "lurker": 0.55 * p("iso_T") + 0.25 * p("first_duel_t") + 0.2 * p("late_share"),
        "support": 0.45 * p("util_pr") + 0.35 * p("blind_pr") + 0.2 * p("open_rate", True),
        "anchor": 0.4 * p("ct_site") + 0.3 * p("ct_top") + 0.3 * p("hold_share"),
        "closer": 0.6 * p("late_share") + 0.4 * p("kpr"),
    }
    return sc


def damp_awp(sc, awp_share):
    """An AWPer score only means something for players who actually kill with the AWP."""
    sc = dict(sc)
    sc["awper"] *= min(1.0, (awp_share or 0) / 0.25)
    return sc


def role_of(row, P, sc):
    if (row.get("awp_share") or 0) >= 0.25:
        return "awper"
    return max((k for k in sc if k != "awper"), key=sc.get)


_CACHE = {}


def reference():
    if "ref" not in _CACHE:
        df = style.load()
        agg = aggregate(df)
        ref = agg[agg.rounds >= MIN_ROUNDS_REF].copy()
        cols = [c for c in agg.columns if c not in ("name", "rounds", "t_rounds", "ct_rounds", "kills", "deaths", "matches")]
        T = pct_table(ref, cols)
        # archetype of every reference player, to compare a player with his peers
        roles = []
        PC = {c: _pcts(T[c], ref[c]) for c in cols}   # 16/10: each column at once, the same numbers as pct()
        for i, r in enumerate(ref.to_dict("records")):
            P = {c: PC[c][i] for c in cols}
            roles.append(role_of(r, P, damp_awp(scores(P), r["awp_share"])))
        ref["role"] = roles
        _CACHE["ref"] = (df, agg, ref, T, cols)
    return _CACHE["ref"]


def fmt(v, kind):
    if v is None or pd.isna(v):
        return "—"
    if kind == "pct":
        return f"{v * 100:.0f}%"
    if kind == "s":
        return f"{v:.1f} s"
    if kind == "clock":   # a moment of the round: the game clock, as shown in game
        return _timer(v)
    if kind == "u":
        return f"{v:.0f} u"
    return f"{v:.2f}"


KIND = {"awp_share": "pct", "open_win": "pct", "hold_share": "pct", "open_rate_T": "n", "traded_share": "pct", "trade_rate": "n",
        "trade_time": "s", "iso_T": "u", "late_share": "pct", "first_duel_t": "clock", "util_pr": "n", "blind_pr": "n",
        "util_dmg_pr": "n", "ct_site": "pct", "ct_top": "pct", "kpr": "n", "move_share": "pct", "duel_len_won": "s", "hs_share": "pct"}


def profile(steamid, xhair_pct=None):
    df, agg, ref, T, cols = reference()
    sid = str(steamid)
    if sid not in agg.index:
        return None
    r = agg.loc[sid]
    if r.rounds < 15:
        return None
    P = {c: pct(T[c], r[c]) for c in cols}
    sc = damp_awp(scores(P), r.awp_share)
    main = role_of(r.to_dict(), P, sc)
    ranked = sorted(sc.items(), key=lambda x: -x[1])
    second = next((k for k, v in ranked if k != main and v >= 55 and (k != "awper" or (r.awp_share or 0) >= 0.15)), None)
    versatile = sc.get(main, 0) < 60 and main != "awper"
    # traits
    traits = []
    def trait(cond, label, text):
        if cond:
            traits.append({"label": label, "text": text() if callable(text) else text})
    ms, iso, dl, tt, hs, up = P.get("move_share"), P.get("iso_T"), P.get("duel_len_won"), P.get("trade_time"), P.get("hs_share"), P.get("util_pr")
    trait(ms is not None and ms >= 70, tr("Aggressive"), lambda: tr("You engage while moving in {v} of your duels (more than {p}% of players).", v=fmt(r.move_share, 'pct'), p=f"{ms:.0f}"))
    trait(ms is not None and ms <= 30, tr("Patient"), lambda: tr("You wait for the enemy: {v} of your duels start with you standing still.", v=fmt(r.hold_share, 'pct')))
    trait(iso is not None and iso >= 70, tr("Loner"), lambda: tr("On attack, your nearest teammate is at {v} (median), further than for {p}% of players.", v=fmt(r.iso_T, 'u'), p=f"{iso:.0f}"))
    trait(iso is not None and iso <= 30, tr("Team player"), lambda: tr("On attack, you stay grouped: {v} from your nearest teammate (median).", v=fmt(r.iso_T, 'u')))
    trait(dl is not None and dl <= 30, tr("Fast reflexes"), lambda: tr("You finish the duels you win in {v} (median), faster than {p}% of players.", v=fmt(r.duel_len_won, 's'), p=f"{100 - dl:.0f}"))
    trait(dl is not None and dl >= 75, tr("Long duels"), lambda: tr("The duels you win last {v} (median): you win by outlasting rather than with the first shot.", v=fmt(r.duel_len_won, 's')))
    trait(tt is not None and tt <= 30 and r.trade_rate > 0, tr("Trade reflex"), lambda: tr("You avenge a teammate in {v} (median).", v=fmt(r.trade_time, 's')))
    trait(hs is not None and hs >= 75, tr("Headshot machine"), lambda: tr("{v} of your kills are headshots (more than {p}% of players).", v=fmt(r.hs_share, 'pct'), p=f"{hs:.0f}"))
    trait(up is not None and up >= 75, tr("Utility user"), lambda: tr("{v} grenade(s) per round (more than {p}% of players).", v=fmt(r.util_pr, 'n'), p=f"{up:.0f}"))
    trait(up is not None and up <= 25, tr("Few grenades"), lambda: tr("Only {v} grenade per round (fewer than {p}% of players).", v=fmt(r.util_pr, 'n'), p=f"{100 - up:.0f}"))
    fd = P.get("first_duel_t")
    trait(fd is not None and fd <= 25, tr("Early in the round"), lambda: tr("Your first duel comes around {t} on the clock: you play for early contact.", t=_timer(r.first_duel_t)))
    trait(fd is not None and fd >= 75, tr("End of round"), lambda: tr("Your first duel comes around {t} on the clock: you let the round develop.", t=_timer(r.first_duel_t)))
    trait(xhair_pct is not None and xhair_pct >= 75, tr("Good crosshair placement"), lambda: tr("Your crosshair is better placed than {p}% of players before duels.", p=f"{xhair_pct:.0f}"))
    # weapons
    shares = {"AWP": r.awp_share, "rifles": r.rifle_share, "SMG": r.smg_share, "shotguns": r.shotgun_share,
              "pistols": r.pistol_share + r.deagle_share}
    main_w = max(shares, key=lambda k: shares[k] or 0)
    tw = top_weapons(df, sid)
    weapons = {"shares": {k: round(float(v or 0) * 100) for k, v in shares.items()},
               "top": [{"weapon": WEAPON_FR.get(w, w), "kills": n} for w, n in tw]}
    # peers: players of the same archetype in the base
    peers = ref[ref.role == main]
    peer_rows = []
    for m, label in ROLES[main]["key"]:
        if m not in r or peers[m].dropna().empty:
            continue
        top = peers.sort_values("kpr", ascending=False).head(max(5, len(peers) // 4))
        peer_rows.append({"metric": m, "label": label, "you": fmt(r[m], KIND.get(m, "n")),
                          "peers": fmt(peers[m].median(), KIND.get(m, "n")), "best": fmt(top[m].median(), KIND.get(m, "n"))})
    role = ROLES[main]
    name = tr("Versatile rifler, leaning {role}", role=tr(role["name"])) if versatile else tr(role["name"])
    desc = [f"{tr('Versatile profile') if versatile else tr(role['name'])}: {tr(role['what'])}"]
    desc.append(tr("Weapons: {r}% of your kills with rifles, {a}% with the AWP, {s}% with SMGs, {p}% with pistols.", r=weapons['shares']['rifles'],
                   a=weapons['shares']['AWP'], s=weapons['shares']['SMG'], p=weapons['shares']['pistols'])
                + (" " + tr("Favorites: {list}.", list=", ".join(f"{t['weapon']} ({t['kills']})" for t in weapons["top"][:3])) if weapons["top"] else ""))
    desc.append(tr("Movement: {how}, {a} from your nearest teammate on attack and {b} on defense.",
                   how=tr("you often engage while moving") if (r.move_share or 0) > 0.4 else tr("you mostly play standing still"), a=fmt(r.iso_T, 'u'), b=fmt(r.iso_CT, 'u')))
    desc.append(tr("Game sense: {u} grenade(s) and {b} enemy(ies) flashed per round, {t} trade(s) per round, {d} of your deaths traded.",
                   u=fmt(r.util_pr, 'n'), b=fmt(r.blind_pr, 'n'), t=fmt(r.trade_rate, 'n'), d=fmt(r.traded_share, 'pct')))
    desc.append(tr("Reactions: duels won finished in {a}, first duel of the round around {t} on the clock", a=fmt(r.duel_len_won, 's'), t=_timer(r.first_duel_t))
                + (", " + tr("trade in {v}", v=fmt(r.trade_time, 's')) if r.trade_time == r.trade_time and r.trade_rate > 0 else "") + ".")
    return {"role": main, "name": name, "icon": role["icon"], "versatile": bool(versatile),
            "second": {"role": second, "name": tr(ROLES[second]["name"])} if second else None,
            "scores": [{"role": k, "name": tr(ROLES[k]["name"]), "score": round(v)} for k, v in ranked],
            "traits": traits, "weapons": weapons, "description": desc, "what": role["what"], "tips": role["tips"],
            "peers": peer_rows, "n_peers": int(len(peers)), "n_ref": int(len(ref)), "rounds": int(r.rounds),
            "sources": [{"label": a, "url": u} for a, u in SOURCES]}
