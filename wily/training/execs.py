"""Site takes and site defenses with grenades (19/10, his 21:19 video: "on va maintenant fonctionner par blocs ... un
stuff de prise de B", "à la place d'avoir 10 minutes, ici j'aurai exec A ... ça mettra l'exec A plus l'exec B", "côté
terreau des prises de bombsite, et des défenses de bombsite, ou des défenses d'anti-rush, côté CT", "on connaît beaucoup
de stuff, mais on ne sait pas quand les utiliser, dans quelles conditions, sur quel timing et quelles combinaisons
faire").

A take (T) of a site: the lineups thrown from one way in (its zone: Bridge for Fachwerk's B, Long for its A) that land
on the site (1100 u of its centre), two smokes at most (the second one a teammate's, dropped at your feet), a molotov,
an HE, two flashes, four in your hands. A defense (CT): the ones thrown from the site (900 u of it) toward where the Ts
come, four at most. Yours first: a setup you saved on the training server (!keep, !setup) is that side's for its site.
Each lineup is worked on its own first, as any Stuff drill; then the whole (the plugin's "exec" drill, Exec.cs): all of
them in your hands, done when all of them are up on the site at the same moment. The anti-rush (CT): the map's timing
smokes and molotovs against a real rush."""
import math
import os
import re
from collections import Counter

from wily.core import config, i18n

T_REACH, CT_REACH = 1100.0, 900.0
CAP = {"T": {"smoke": 2, "molotov": 1, "he": 1, "flash": 2}, "CT": {"smoke": 1, "molotov": 1, "he": 1, "flash": 2}}
ORDER = {"smoke": 0, "molotov": 1, "he": 2, "flash": 3}   # his: the smokes, the fire, then the support flashes
HAND = 4   # CS2's grenades a player carries (ammo_grenade_limit_total)
KEYS = ("T:A", "T:B", "T:AB", "CT:A", "CT:B", "CT:AB", "CT:rush")
PLAN_F = os.path.join(config.HERE, "resources", "stuff_plan.json")   # the maps built again under his rules (tools/stuff_build.py)


def _rebuilt(mp):
    """The map's takes and defenses built again from corners under his rules (22/10, tools/stuff_build.py): it offers only
    those and his own setups, never the base's grenades grouped by site (his test video: "des stuff de défense c'est des
    stuff qui doit être envoyé depuis le bombsite", "un stuff qui part d'un spot qui est dans un coin")."""
    return any(k.split("|")[0] == mp for k in (config.read_json(PLAN_F, {}) or {}))


def _sites(mp):
    from wily.training import train
    return {k[-1]: v["center"] for k, v in (train.site_data(mp).get("sites") or {}).items() if v.get("center")}


def _from(d):
    k = d["id"].split(":")[-1]
    return k.split(">")[0] if ">" in k else None


def _nearest(C, p):
    return min(C, key=lambda s: math.dist(C[s][:2], p[:2])) if C else None


def _cap(grp, side):
    """Its best ones by kind (CAP), four in your hands (a dropped smoke on top when there are two), in his order."""
    n, out = Counter(), []
    for e in sorted(grp, key=lambda e: -(e.get("weight") or 1.0)):
        if n[e["type"]] < CAP[side].get(e["type"], 1):
            n[e["type"]] += 1
            out.append(e)
    most = HAND + (1 if n["smoke"] >= 2 else 0)
    while len(out) > most:   # the least useful of the support ones out first
        out.remove(min((e for e in out if e["type"] in ("flash", "he")), key=lambda e: e.get("weight") or 1.0, default=out[-1]))
    return sorted(out, key=lambda e: (ORDER.get(e["type"], 9), -(e.get("weight") or 1.0)))


def _still(d):
    """An anti-rush lineup as a plain one (its runners, its timing out): a defense's grenade."""
    if not d.get("tracks"):
        return d
    e = {k: v for k, v in d.items() if k not in ("tracks", "step", "rush_at")}
    e["title"] = e["title"].replace(i18n.tr("ANTI-RUSH {nade} → {zone}", nade="", zone="").split("→")[0].strip(), "").strip()
    return e


def _takes(d, c):
    """A take's grenade lands on the site or past it, not on the way to it (20/10, his video on the composed A from Outside
    Long: "ça permet de prendre les zones en amont du bomb-site, mais ça ne permet pas de prendre le bomb-site"): from its
    spot, 80 % of the way to the site's centre at least; a flash pops over the site (700 u of its centre)."""
    p, t = d["me"]["pos"], d["target"]
    if d["type"] == "flash":
        return math.dist(t[:2], c[:2]) <= 700
    return math.dist(p[:2], t[:2]) >= 0.8 * math.dist(p[:2], c[:2])


WALK_U = 1100.0   # u on the mesh from one of its grenades' spots to the next at most: 5 s of a player's run


def _walkable(mp, grp):
    """Its grenades one player can throw one after the other (03/11, Anubis's exec A from A Main: its flash's spot on Mid's
    floor 533 u off the molotov's, 2,587 u by the mesh, 12 s of run, the molotov's 7 s of fire long gone, "2/3 at once"
    every round): each one within WALK_U of the one before by the mesh (the first ones kept, a far one dropped)."""
    try:
        from wily.training import navmesh
    except Exception:
        return grp
    out = []
    for e in grp:
        p = (e.get("me") or {}).get("pos")
        if out and p:
            q = out[-1]["me"]["pos"]
            r = navmesh.route(mp, q, p)
            ln = sum(math.dist(r[i][:2], r[i + 1][:2]) for i in range(len(r) - 1)) if r else 1.3 * math.dist(q[:2], p[:2])
            if ln > WALK_U:
                continue
        out.append(e)
    return out


def _ok(grp):
    kinds = {e["type"] for e in grp}
    return len(grp) >= 3 and len(kinds) >= 2 and bool(kinds & {"smoke", "molotov"})


def plan(sid, mp, drills=None):
    """{key: {side, site, members (the lineups, in order), mine, frm}} for each site's take and defense the map has."""
    from wily.training import setups, train
    C = _sites(mp)
    if not C:
        return {}
    if drills is None:
        drills = train.nade_drills(sid, mp)
    from wily.insights import nades
    out = {}
    plain = [d for d in drills if d.get("kind") == "nade" and d.get("me") and d.get("target") and (d["team"] == 3 or not d.get("tracks"))]
    for side, team in (() if _rebuilt(mp) else (("T", 2), ("CT", 3))):
        own = [d for d in plain if d["team"] == team]
        for site, c in C.items():
            if side == "T":   # thrown from outside the site, landing on it, from one way in (its zone)
                cand = [d for d in own if math.dist(d["target"][:2], c[:2]) <= T_REACH and math.dist(d["me"]["pos"][:2], c[:2]) > math.dist(d["target"][:2], c[:2])
                        and _takes(d, c)]
                ways = {_from(d) for d in cand if _from(d)}
            else:   # thrown from the site (its anti-rush ones too, without their runners): all of them one defense
                cand = [_still(d) for d in own if math.dist(d["me"]["pos"][:2], c[:2]) <= CT_REACH]
                ways = {None}
            best = None
            for frm in ways:
                grp = _cap([d for d in cand if frm is None or _from(d) == frm], side)
                if side == "T":   # one player's run from one to the next (03/11)
                    grp = _walkable(mp, grp)
                score = (len({e["type"] for e in grp}), len(grp), sum(e.get("weight") or 1.0 for e in grp))
                if _ok(grp) and (best is None or score > best[0]):
                    best = (score, frm, grp)
            if best:
                out[f"{side}:{site}"] = {"side": side, "site": site, "members": best[2], "mine": False, "frm": nades.humanize(best[1], mp) if best[1] else None}
    # a site's defense found and checked by Wily (21/10, resources/defenses.json): that site's, over the base's
    for site, rec in _defenses(mp).items():
        ms = _defense_members(mp, site, rec)
        if len(ms) >= 2:
            out[f"CT:{site}"] = {"side": "CT", "site": site, "members": ms, "mine": False, "frm": None, "rec": rec}
    # a site's take found and checked by Wily (21/10, Dust2: resources/takes.json), over the base's
    for site, rec in _wily_takes(mp).items():
        # one player's run from one to the next, three of them at least (03/11; his rule of 22/10: three or nothing)
        ms = _walkable(mp, _defense_members(mp, site, rec, side="T"))
        if len(ms) >= 3:
            out[f"T:{site}"] = {"side": "T", "site": site, "members": ms, "mine": False, "frm": rec.get("from"), "wily": True}
    # yours first (a setup saved with !setup): that side's take or defense of the site its grenades land nearest
    by = {}
    for d in setups.drills(mp):
        by.setdefault(d["clip"], []).append(d)
    for clip, ms in by.items():
        ms.sort(key=lambda d: d.get("step", 0))
        side = "T" if ms[0]["team"] == 2 else "CT"
        mid = [sorted(d["target"][i] for d in ms)[len(ms) // 2] for i in (0, 1)]
        site = _nearest(C, mid)
        if site and len(ms) >= 2:
            out[f"{side}:{site}"] = {"side": side, "site": site, "members": ms, "mine": True, "frm": ms[0]["title"].split(" · ")[0]}
    # an attack's grenades in a player's order (30/10, Inferno's B: its molotov 2nd, its 7 s of fire gone before its flash
    # came 4th, 3 of 4 up at once; the user: "les flashs, c'est systématiquement le dernier stuff à envoyer"): its smokes,
    # its HEs, its molotovs, its flashes last, each one's number its new place; yours as you saved them
    rank = {"smoke": 0, "he": 1, "molotov": 2, "flash": 3}
    for x in out.values():
        if x["side"] == "T" and not x.get("mine"):
            ms = sorted(x["members"], key=lambda m: rank.get(m.get("type"), 1))
            x["members"] = [dict(m, title=re.sub(r"\(\d+/\d+\)$", f"({i + 1}/{len(ms)})", m["title"])) if m.get("title") else m for i, m in enumerate(ms)]
    return out


def title(x):
    if x.get("rec"):   # a defense of Wily's: the site's name
        return i18n.tr("Defense {site}", site=x["site"]).upper()
    if x.get("mine"):   # yours: its name (20/10: "EXEC A · from exec a from long"), once when it is that name already
        head = i18n.tr("Exec {site}", site=x["site"]) if x["side"] == "T" else i18n.tr("Defense {site}", site=x["site"])
        same = re.sub(r"\W", "", str(x["frm"]).lower()) in {re.sub(r"\W", "", head.lower()), f"exec{x['site'].lower()}"}
        return head.upper() if same else f'{head.upper()} · «{x["frm"]}»'
    return (i18n.tr("EXEC {site} · from {zone}", site=x["site"], zone=x["frm"] or "?") if x["side"] == "T"
            else i18n.tr("DEFENSE {site} · its grenades", site=x["site"]))


def _item(x, m):
    """A grenade of it as Prepare lists it: a setup of yours without its name and its number in front (20/10)."""
    t = m["title"]
    if x.get("mine") and t.startswith(f'{x["frm"]} · '):
        t = t[len(x["frm"]) + 3:]
    return re.sub(r"\s*\(\d+/\d+\)$", "", t)   # its number: the list's own (21/10: "1. Flash → Bridge (1/4)")


def drill(mp, x):
    """The whole of it at once: the plugin's exec drill (Exec.cs)."""
    from wily.training import train
    ms = x["members"]
    team = 2 if x["side"] == "T" else 3
    smokes = [m for m in ms if m["type"] == "smoke"]
    drop = None
    hand = [m["item"] for m in ms]
    if len(smokes) >= 2:   # the second smoke a teammate's, given once your first is up (his: "tu vas me dropper une smoke au sol")
        hand.remove(smokes[1]["item"])
        p = smokes[0]["me"]["pos"]
        drop = [p[0], p[1], p[2]]
    key = f"exec:{mp}:{x['side']}:{x['site']}"
    rec = x.get("rec") or {}
    return {"id": key, "kind": "nade", "mode": "exec", "map": mp, "team": team, "title": title(x),
            # a defense: GO when its defender is on his site, all of them up before the Ts get onto it (the base's fast
            # takes), on the round's clock
            **({"arrive": rec["arrive"], "clock": round(115 - rec["go"], 1)} if rec else {}),
            "tip": i18n.tr("all of them up on the site at the same moment") + (" · " + i18n.tr("a teammate's smoke comes to you once your first one is thrown") if drop else ""),
            "type": "exec", "item": hand[0], "weapons": hand, "drop": drop, "me": ms[0]["me"], "victims": [], "level": 0,
            "start": train.start_near(mp, ms[0]["me"]["pos"], ms[0]["me"]["ang"][1]),
            "seconds": 30 + 10 * len(ms), **({} if rec else {"clock": 0}),
            # aimed crouched: its circle and its card the same as on its own (20/10: the whole exec drew the molotov's from
            # the standing eye); his grenade itself and its moment in his exec (the entry, Entry.cs)
            "members": [{k: m[k] for k in ("id", "title", "type", "item", "how", "click", "me", "target")} | {"kind": "nade"}
                        | {k: m[k] for k in ("aim_from", "his_nade", "at", "jump", "place") if m.get(k) is not None} for m in ms]}


def entry(mp, x):
    """The exec played as its entry (20/10, his video: "je vais être à la place de la personne qui entre ... des bots sans
    arme, sans rien, juste pour que je sache quelles lignes décalent ... charrette j'ai pas regardé, hauteur j'ai pas
    regardé, porte j'ai pas regardé, et que les ennemis vont être partiellement aveuglés"): its grenades thrown for you
    as you threw them in the whole exec just before (the plugin keeps that try; else his setup's own, at their moment),
    you armed from its spot nearest the site; on the site the CT spots its grenades are for (each one's victims the
    guided bot found taking it: covered) and the ones the base's CTs hold it from that none covers (to check), unarmed.
    None: a defense's (CT), or a site the map has no data of."""
    from wily.training import train
    if x["side"] != "T":
        return None
    S = (train.site_data(mp).get("sites") or {}).get(f"Bombsite{x['site']}")
    if not S or not S.get("center"):
        return None
    c = S["center"]
    ms = x["members"]
    me = min((m["me"]["pos"] for m in ms), key=lambda p: math.dist(p[:2], c[:2]))
    bots = _entry_bots(mp, x, S, me)
    if not any(b["seq"] < 0 for b in bots):
        return None
    d = drill(mp, x)
    # you start where the exec's first grenade does, near its spot (20/10, his video: "ça serait bien que je commence à peu
    # près là où mon teammate commence ... un endroit où je spawne pour les premiers stuff histoire qu'on soit un peu tous
    # dans le même rythme"): on the teammate's timing, not waiting by the site
    me = d.get("start") or ms[0]["me"]["pos"]
    # now its smokes and fires are seen from above first (Entry.cs's sky view): by where its flashes are thrown, a step
    # toward the site (22/10 eve, the user: "fait commencer le joueur un peu plus proche du bon site ... le joueur a
    # théoriquement eu le temps de s'avancer un peu ... mets-le à proximité de l'endroit où le coéquipier envoie les
    # flashs ... pour qu'il soit assez prêt pour profiter du stuff de son teammate")
    sup = [m for m in ms if m.get("type") in ("flash", "he") and m.get("me")]
    if sup:
        from wily.training import navmesh
        p = sup[-1]["me"]["pos"]
        dl = math.dist(p[:2], c[:2]) or 1.0
        q = [p[0] + (c[0] - p[0]) / dl * 70.0, p[1] + (c[1] - p[1]) / dl * 70.0, p[2]]
        me = [round(float(v), 1) for v in (navmesh.nearest(mp, q, r=48.0) or p)]
    yaw = round(math.degrees(math.atan2(c[1] - me[1], c[0] - me[0])), 1)
    try:   # your way in walked under the sky view (23/10, Entry.cs): the base's Ts' own up to your start
        way = train.approach(mp, me)
    except Exception as e:
        print("entry approach", mp, e, flush=True)
        way = []
    return {"id": f"entry:{mp}:{x['side']}:{x['site']}", "kind": "nade", "mode": "entry", "map": mp, "team": 2, "approach": way,
            "title": f"{title(x)} · {i18n.tr('AS ITS ENTRY')}",
            "tip": i18n.tr("your exec thrown for you as you just did it: go in armed, clear the spots its grenades don't cover"),
            "type": "entry", "item": "weapon_ak47", "weapons": ["weapon_knife", "weapon_glock", "weapon_ak47"],
            "me": {"pos": me, "ang": [0.0, yaw]}, "bots": bots, "members": d["members"], "victims": [], "level": 0,
            "seconds": 45, "clock": 0}


ENTRY_F = os.path.join(config.HERE, "resources", "entry_spots.json")
MAX_CT = 10   # the CTs a map's spawns take (20/10: "team 3: 10 bots for 11 tracks", a red post without its bot, never cleared)
# the names of his marked spots (resources/entry_spots.json), said in your language
_ENTRY_NAMES = (i18n.N_("the cart"), i18n.N_("the lower exit"), i18n.N_("the sandbags"), i18n.N_("the plank"), i18n.N_("close"),
                i18n.N_("the low wall"), i18n.N_("the corner"), i18n.N_("the short"))


def _entry_bots(mp, x, S, me):
    """The CTs its entry meets, all of them on the site (20/10, his video: "je ne veux personne en bas, je ne veux personne
    ici, moi je veux que les joueurs soient vraiment sur l'espace de bombsite ... le joueur dans la smoke-porte, je m'en
    fous, le joueur dans la smoke-hauteur, je m'en fous aussi, tu peux les faire disparaître, l'idée c'est de montrer
    l'intérêt justement d'avoir ces stuff, pour éviter qu'il y ait des joueurs dans ces zones-là, et s'il y en a comme
    le joueur au niveau de la charrette, l'idée c'est qu'il brûle"): the ones he marked on that site
    (resources/entry_spots.json), else the base's CTs who hold it from its own place (the place most of its spots near
    its centre are in) and the ones its fire or HE is for; none in a smoke's place. Each turned to the line its spot's
    CTs held (their duels), covered (seq: the grenade of it meant for it) or to check (-1)."""
    from wily.training import train
    c = S["center"]
    ms = x["members"]
    kind = {m["type"]: i for i, m in reversed(list(enumerate(ms)))}

    def face(p):
        return train._real_line(mp, "CT", p) or [0.0, round(math.degrees(math.atan2(me[1] - p[1], me[0] - p[0])), 1)]

    his = (config.read_json(ENTRY_F, {}) or {}).get(f"{mp}|{x['site']}")
    if his:
        return _his_bots(mp, x, S, his, kind, face)
    bots = []
    for i, m in enumerate(ms):   # the ones its fire and its HE are for
        if m["type"] not in ("molotov", "he"):
            continue
        side_, t_med = m.get("_vic") or [None, None]
        for v in train._victims(mp, m["team"], m["type"], m.get("target"), m["me"]["pos"], side_, t_med, checked=True):
            if all(math.dist(v["pos"][:2], b["pos"][:2]) > 120 for b in bots):
                bots.append({"pos": v["pos"], "ang": v["ang"], "zone": re.sub(r"\s*\(\d+/\d+\)$", "", m["title"].split(" · ")[-1]), "seq": i})
    holds = train._site_holds(S)
    near = Counter(h.get("zone") for h in holds if math.dist(h["pos"][:2], c[:2]) <= 400 and h.get("zone"))
    place = near.most_common(1)[0][0] if near else None
    smokes = [m["target"] for m in ms if m["type"] == "smoke" and m.get("target")]
    for h in holds:   # the base's CTs on the site itself, none in a smoke's place
        if len(bots) >= 8:
            break
        if h.get("zone") != place or math.dist(h["pos"][:2], c[:2]) > 700 or any(math.dist(h["pos"][:2], t[:2]) < 250 for t in smokes):
            continue
        if all(math.dist(h["pos"][:2], b["pos"][:2]) > 160 for b in bots):
            bots.append({"pos": h["pos"], "ang": face(h["pos"]), "zone": h.get("zone") or "?", "seq": -1})
    return bots


def _his_bots(mp, x, S, his, kind, face):
    """His marked CTs crossed with the base's (20/10, his video: "croiser les endroits où je t'envoie des grenades avec les
    positions fortes que tu as dans les datas ... peut-être que j'en ai oublié et peut-être que les positions que je
    t'ai données ne sont pas tout à fait exactes et qu'il faut un tout petit peu repositionner les joueurs"): each one on
    the base's nearest CT spot of a take within 80 u (one tuned by hand, 'fixed', stays), then the base's spots met 25
    times at least in the site's own place that none of his is near (160 u) and no smoke of it covers (200 u), 3 at
    most."""
    from wily.insights import nades
    from wily.training import train
    takes = train.take_spots(mp, x["site"])
    smokes = [m["target"] for m in x["members"] if m["type"] == "smoke" and m.get("target")]

    def place(p):
        t = min((t for t in takes if math.dist(t["pos"][:2], p[:2]) <= 200), key=lambda t: math.dist(t["pos"][:2], p[:2]), default=None)
        return (nades.humanize(t["zone"], mp) or t["zone"]) if t else "?"

    bots = []
    for b in his[:MAX_CT]:
        p = list(b["pos"])
        near = None if b.get("fixed") else min((t for t in takes if math.dist(t["pos"][:2], p[:2]) <= 80 and abs(t["pos"][2] - p[2]) < 40),
                                                key=lambda t: math.dist(t["pos"][:2], p[:2]), default=None)
        if near:
            p = list(near["pos"])
        bots.append({"pos": p, "ang": face(p), "zone": i18n.tr(b["name"]) if b.get("name") else place(p), "duck": bool(b.get("duck")),
                     "seq": kind.get(b.get("by"), -1) if b.get("by") else -1, "his": list(b["pos"])})
    # one standing where a fire or an HE of it really hurts (the guided bot's victims that took it): covered by it
    for i, m in enumerate(x["members"]):
        if m["type"] not in ("molotov", "he"):
            continue
        side_, t_med = m.get("_vic") or [None, None]
        hit = train._victims(mp, m["team"], m["type"], m.get("target"), m["me"]["pos"], side_, t_med, checked=True)
        for q in bots:
            if q["seq"] < 0 and any(math.dist(q["pos"][:2], v["pos"][:2]) <= 40 for v in hit):
                q["seq"] = i
    c = S["center"]
    here = Counter(t["zone"] for t in takes if math.dist(t["pos"][:2], c[:2]) <= 400)
    own = here.most_common(1)[0][0] if here else None
    added = 0
    for t in takes:
        if added >= 3 or len(bots) >= MAX_CT:
            break
        if t["n"] < 25 or t["zone"] != own or any(math.dist(t["pos"][:2], q["pos"][:2]) < 160 for q in bots)                 or any(math.dist(t["pos"][:2], sm[:2]) < 200 for sm in smokes):
            continue
        bots.append({"pos": t["pos"], "ang": face(t["pos"]), "zone": i18n.tr("{place} (from the base)", place=nades.humanize(own, mp) or own),
                     "duck": t["crouch"] * 2 > t["n"], "seq": -1})
        added += 1
    return bots


DEF_F = os.path.join(config.HERE, "resources", "defenses.json")
# what each grenade of a defense is for, said in your language (resources/defenses.json "why")
_DEF_WHY = (i18n.N_("cuts Heaven's view onto the site: they have to come down to see you"),
            i18n.N_("closes T Main's exit when they come: they wait or they burn"),
            i18n.N_("a flash over the Bridge's exit: the ones holding it blinded when you re-peek, never you"),
            i18n.N_("hits the ones stacked on the Bridge before they come in"),
            i18n.N_("closes Long's exit: they have to cross it to come in"),
            i18n.N_("burns the ones who rush through Long's exit"),
            i18n.N_("hits the ones stacked at Long's exit"),
            i18n.N_("a flash over Long for your re-peek, never in your eyes"),
            # Dust2's (21/10): its defenses' and its takes'
            i18n.N_("a flash at Long's corner for your re-peek, never in your eyes"),
            i18n.N_("closes Long Doors: they have to cross it to come out"),
            i18n.N_("burns the bottom of Catwalk: the ones coming up Short wait or burn"),
            i18n.N_("closes Short: they have to cross it to come onto the site"),
            i18n.N_("burns the tunnel's exit when they rush: they wait or they burn"),
            i18n.N_("a flash at the tunnel's exit for your re-peek, never in your eyes"),
            i18n.N_("hits the ones stacked in the tunnel before they come out"),
            i18n.N_("closes the tunnel once the fire is out: they have to cross it to come in"),
            i18n.N_("cuts the cross from CT spawn: they can't see you cross onto the site"),
            i18n.N_("burns the site's corner: the one hiding there moves or burns"),
            i18n.N_("hits the one at the back of the site (Goose)"),
            i18n.N_("a flash over Long's exit as you come out: the ones holding the site blinded"),
            i18n.N_("closes B Doors: the CTs rotating from mid can't see in"),
            i18n.N_("closes Window: nobody shoots you from above as you come in"),
            i18n.N_("a flash over the site as you come out of the tunnel"),
            i18n.N_("burns the back of the site: the one hiding there moves or burns"),
            # 22/10: the places of a take or a defense the pros' way (tools/stuff_build.py), said with their place
            i18n.N_("closes {zone}: the ones holding it can't see you come in"),
            i18n.N_("burns {zone}: the one hiding there moves or burns"),
            i18n.N_("hits the ones holding {zone}"),
            i18n.N_("a flash over {zone} as you come in: the ones holding it blinded"),
            i18n.N_("closes {zone}: they have to cross it to come onto the site"),
            i18n.N_("burns {zone} when they come: they wait or they burn"),
            i18n.N_("hits the ones stacked at {zone}"),
            i18n.N_("a flash over {zone} for your re-peek, never in your eyes"))
WHY_T = {"smoke": _DEF_WHY[-8], "molotov": _DEF_WHY[-7], "he": _DEF_WHY[-6], "flash": _DEF_WHY[-5]}
WHY_CT = {"smoke": _DEF_WHY[-4], "molotov": _DEF_WHY[-3], "he": _DEF_WHY[-2], "flash": _DEF_WHY[-1]}


def _defenses(mp):
    """The site defenses of Wily's on that map (resources/defenses.json, tools/defense_build.py): {site: record}."""
    # one withdrawn ("withdrawn": why) is not offered (30/10, his review: Inferno's B and Dust2's A broke his rules)
    return {k.split("|")[1]: v for k, v in (config.read_json(DEF_F, {}) or {}).items()
            if "|" in k and k.split("|")[0] == mp and not v.get("withdrawn")}


TAKE_F = os.path.join(config.HERE, "resources", "takes.json")


def _wily_takes(mp):
    """The site takes of Wily's on that map (resources/takes.json, tools/defense_build.py, 21/10: Dust2): {site: record}."""
    return {k.split("|")[1]: v for k, v in (config.read_json(TAKE_F, {}) or {}).items() if "|" in k and k.split("|")[0] == mp}


def _defense_members(mp, site, rec, side="CT"):
    """A defense's grenades (or a take's, side "T") as Stuff drills, in its order: each from its corner, its aim, its
    technique, its grenade's own start and speed (the one thrown on the server: the victims and the teammate replay it),
    its moment after GO."""
    from wily.training import setups, train
    out = []
    team = 3 if side == "CT" else 2
    n = len(rec.get("throws") or [])
    see = rec.get("post")
    if side == "T":   # a take's smokes: the CTs' view of where its entry crosses (21/10), else its spot nearest the site
        S = (train.site_data(mp).get("sites") or {}).get(f"Bombsite{site}") or {}
        c = S.get("center")
        spots = [t["pos"] for t in rec.get("throws") or []]
        see = rec.get("see") or (min(spots, key=lambda p: math.dist(p[:2], c[:2])) if c and spots else None)
    for i, t in enumerate(rec.get("throws") or []):
        typ = t["type"]
        item = train.NADE_ITEM[typ][team] if typ == "molotov" else train.NADE_ITEM.get(typ)
        if not item:
            continue
        name = {"smoke": i18n.tr("Smoke"), "flash": i18n.tr("Flash"), "he": "HE", "molotov": i18n.tr("Molotov")}[typ]
        kind = "defense" if side == "CT" else "take"
        out.append({"id": f"{kind}:{mp}:{site}:{i}", "kind": "nade", "map": mp, "clip": f"{kind}:{mp}:{site}", "step": i,
                    "title": f"{name} → {setups.zone_at(mp, t['target']) or '?'} ({i + 1}/{n})", "tip": i18n.tr(t["why"], zone=t.get("why_zone") or "?"),
                    "team": team, "type": typ, "item": item, "how": t["how"], "click": t["click"],
                    "me": {"pos": t["pos"], "ang": t["ang"]}, "target": t["target"], "victims": [], "_vic": [side, t.get("t")],
                    **({"_see": t.get("see") or see} if (t.get("see") or see) else {}),   # a smoke: the view onto its post (a take: the crossing it hides) it cuts
                    "his_nade": {"type": typ, "inc": typ == "molotov", "p": t["nade_at"], "v": t["nade_v"]},
                    "place": setups.zone_at(mp, t["pos"]) or "", "at": t.get("at", 0.0), "clock": 0, "weight": 40})
    return out


def hold(mp, x):
    """A site defense played as its defender (21/10, the T exec's entry the other way round): its grenades thrown for you
    by a CT teammate at the moments you threw them after GO in its whole drill (else at the base's), you armed on its
    post, and the Ts of the base's typical takes through each of its grenades' places (train._rush: their own ways, their
    own pace, one per way, 6 at most), unarmed, on the round's clock from its GO. None: no such take in the base."""
    from wily.training import train
    rec = x["rec"]
    T0 = float(rec["go"])
    E = train._early(mp)
    runners = []
    for m in x["members"]:
        # a typical take, as its moments, its Ts on to the site; a flash's place is the floor under its pop
        tg = [m["target"][0], m["target"][1], m["me"]["pos"][2]] if m["type"] == "flash" else m["target"]
        R = train._rush(mp, tg, 2.5, max(0.0, T0 - 2.0), E, q=(0.4, 0.6), after=12.0)
        if not R:
            continue
        t_go = 115.0 - float(R["clock"])
        for tr in R["tracks"]:
            p = list(tr["path"])
            if any(math.dist(p[:2], q["path"][:2]) < 150 for q in runners):
                continue   # one per way in
            pad = int(round((t_go - T0) / 0.5))   # on the defense's clock: still on their spot until their own moment
            p = p[:5] * pad + p if pad > 0 else p[-pad * 5:]
            if len(p) < 20:
                continue
            runners.append({"zone": tr["zone"], "path": p, "arrive": round(float(tr["arrive"]) + t_go - T0, 1)})
    runners = runners[:6]
    if not runners:
        return None
    post = rec["post"]
    end = runners[0]["path"][-5:-2]
    d = drill(mp, x)
    return {"id": f"entry:{mp}:CT:{x['site']}", "kind": "nade", "mode": "hold", "map": mp, "team": 3,
            "title": f"{title(x)} · {i18n.tr('AS ITS DEFENDER')}",
            "tip": i18n.tr("your defense thrown for you as you just did it: the Ts of a real take come in, hold the site"),
            "type": "hold", "item": "weapon_m4a1", "weapons": ["weapon_knife", "weapon_usp_silencer", "weapon_m4a1"],
            "me": {"pos": post, "ang": [0.0, round(math.degrees(math.atan2(end[1] - post[1], end[0] - post[0])), 1)]},
            "bots": [{"pos": r["path"][:3], "ang": [0.0, r["path"][3]], "zone": r["zone"], "seq": -1} for r in runners],
            "runners": runners, "step": train.RUSH_STEP, "members": d["members"], "victims": [], "level": 0,
            "seconds": 45, "clock": round(115 - T0, 1)}


def offer(sid, mp):
    """Prepare's choices on that map: each take and defense it has, A and B together, the anti-rush."""
    from wily.training import train
    ds = train.nade_drills(sid, mp)
    P = plan(sid, mp, ds)
    rush = [d for d in ds if d.get("tracks")]
    out = []
    for side in ("T", "CT"):
        one = [k for k in (f"{side}:A", f"{side}:B") if k in P]
        for k in one:
            x = P[k]
            out.append({"key": k, "side": side, "label": i18n.tr("Exec {site}", site=x["site"]) if side == "T" else i18n.tr("Defense {site}", site=x["site"]),
                        "n": len(x["members"]), "mine": x["mine"], "items": [_item(x, m) for m in x["members"]], "title": title(x)})
        if len(one) == 2:
            out.append({"key": f"{side}:AB", "side": side, "label": i18n.tr("Exec A + B") if side == "T" else i18n.tr("Defense A + B"),
                        "n": sum(len(P[k]["members"]) for k in one), "mine": any(P[k]["mine"] for k in one), "items": [], "title": ""})
    if rush:
        out.append({"key": "CT:rush", "side": "CT", "label": i18n.tr("Anti-rush"), "n": len(rush), "mine": False, "items": [d["title"] for d in rush], "title": ""})
    return out


def sequence(sid, mp, key, ds=None):
    """The block's drills: for each site of the key, its lineups one by one (worked as any Stuff drill), then all of them
    at once; the anti-rush: its drills. Their seconds (the block's time)."""
    from wily.training import train
    ds = train.nade_drills(sid, mp) if ds is None else ds
    if key == "CT:rush":
        out = [d for d in ds if d.get("tracks")]
        return out, sum(train.EST["nade"] for _ in out) * 2
    side, sites = key.split(":")
    P = plan(sid, mp, ds)
    out, secs = [], 0
    for site in sites:
        x = P.get(f"{side}:{site}")
        if not x:
            continue
        t = title(x)
        n = len(x["members"])
        prev = None
        for k, m in enumerate(x["members"]):
            m = dict(m, title=f"{t} · {k + 1}/{n} · {_item(x, m)}", tip=i18n.tr("remember it: all of them together come after") + (f" · {m['tip']}" if m.get("tip") else ""))
            m.pop("clip", None)
            # step by step (20/10, his video: "découper la première partie de l'apprentissage, donc stuff par stuff, en
            # séquence qui se valide petit à petit"): you walk to its spot from near it, then the aim, the clicks, the move
            # (the plugin's Steps.cs checks each one), its landing last
            m["steps"] = True
            m["start"] = train.start_near(mp, m["me"]["pos"], m["me"]["ang"][1], prev)
            prev = m["me"]["pos"]
            out.append(m)
            secs += train.EST["nade"] * 2
        e = drill(mp, x)
        out.append(e)
        secs += e["seconds"] * 3
        en = hold(mp, x) if x.get("rec") else entry(mp, x)   # then as its entry, armed (20/10, his video), or its defender
        if en:
            out.append(en)
            secs += en["seconds"] * 2
    return out, secs
