"""Wily's site defenses and takes, put together from the lineups found from corners (21/10, the user: "finis les stuff de
Fachwerk pour la partie défensive, histoire de tester si tu as bien compris ce que je voulais et si tu sais l'appliquer
et le contrôler par toi-même"; then: "mets en place le même principe ... sur la map sur laquelle tu auras le plus de
datasets": Dust2's takes and defenses).

    python tools/defense_build.py [map]      writes resources/defenses.json (CT) and resources/takes.json (T)

For each site a side's grenades, each with a role on it: the places come from the base (where its players throw each
one most, when, with what effect: tools/site_candidates.py), the lineups from tools/lineup_finder.py (a corner, the aim,
the technique, thrown on the server). Of the ones found for a role: a still throw before a jumpthrow, then the nearest
its place, then the nearest the defender's post or the take's first spot (one more place to remember is one more thing
to learn); a flash its own thrower saw never. A smoke never lands on its own side's molotov (it puts the fire out:
20/10, his exec B, "je pense qu'il se fait éteindre par la fumée"): 220 u of it, up and down counted (Heaven's floor is
160 u over T Main's). A defense: GO when its defender is on his site, "arrive" when the base's fast takes (their first
quarter) are on it, after GO (the whole drill's limit), each grenade's moment from the base's typical takes through its
place. A take: all of them up at once (the T exec), in the order the base throws them."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tools"))
from wily.core import config  # noqa: E402
import lineup_finder  # noqa: E402

OUT = {"CT": os.path.join(HERE, "resources", "defenses.json"), "T": os.path.join(HERE, "resources", "takes.json")}
# per map, side and site: a defense's GO (round time), the Ts' first quarter on the site (round time), the defender's
# post (the base's most held CT spot of its takes: tools/site_timing.py); a take's way in ("from"); each role: the
# finder's file, why, the base's moment of the round
class _Conf(dict):
    """The maps written here, then the ones tools/site_conf.py read from the base (23/10, the user: "faire toutes les
    recherches sur toutes les cartes"): out/selftest/site_conf_<map>.json, a map written here keeping its own."""

    def __missing__(self, mp):
        c = config.read_json(os.path.join(config.OUT, "selftest", f"site_conf_{mp}.json"), None)
        if not c:
            raise KeyError(mp)
        c = {side: {site: dict(v, roles=[tuple(r) for r in v.get("roles") or []]) for site, v in sites.items()}
             for side, sites in c.items()}
        self[mp] = c
        return c

    def get(self, mp, default=None):
        try:
            return self[mp]
        except KeyError:
            return default


CONF = _Conf({
    "de_fachwerk": {"CT": {
        "B": {"go": 6.0, "on_site": 27.8, "post": [1232.2, -534.4, -92.0], "roles": [
            # on Heaven's front edge, where its Ts duel from (the base's most met T spots): the base's own spot at its
            # back left them seeing the post (victim_check, 21/10)
            ("B_smoke2", "cuts Heaven's view onto the site: they have to come down to see you", 10.0),
            ("B_flash", "a flash over the Bridge's exit: the ones holding it blinded when you re-peek, never you", 10.5),
            ("B_he", "hits the ones stacked on the Bridge before they come in", 18.9),   # its exit: the base's hardest-hitting
            ("B_molotov", "closes T Main's exit when they come: they wait or they burn", 14.0)]},
        "A": {"go": 5.0, "on_site": 31.7, "post": [-1102.5, -1400.4, -15.3], "roles": [
            ("A_molotov", "burns the ones who rush through Long's exit", 9.3),
            ("A_he", "hits the ones stacked at Long's exit", 10.2),
            ("A_smoke", "closes Long's exit: they have to cross it to come in", 11.6),
            # from the site over its wall onto Long's end (the base's: popped about 230 u up), not down Long from Long:
            # that one blinded its own thrower 1.17 s (victim_check, 21/10)
            ("A_flash2", "a flash over Long for your re-peek, never in your eyes", 20.5)]}}},
    # 21/10: the base's most thrown places of each (tools/site_candidates.py de_dust2: 928 matches); GO a second and a
    # half before its first grenade when the CTs' arrival on the site's middle is later (they hold Long and the tunnel's
    # exit from outside it: tools/site_timing.py)
    "de_dust2": {
        "CT": {
            "A": {"go": 5.0, "on_site": 26.5, "post": [968.2, 2523.3, 98.4], "roles": [
                ("CA_flash|CA_flash2", "a flash at Long's corner for your re-peek, never in your eyes", 23.8),
                ("CA_smoke_long", "closes Long Doors: they have to cross it to come out", 15.5),
                ("CA_molotov", "burns the bottom of Catwalk: the ones coming up Short wait or burn", 22.1),
                ("CA_smoke_short", "closes Short: they have to cross it to come onto the site", 27.1)]},
            "B": {"go": 5.3, "on_site": 14.5, "post": [-1370.6, 2163.0, 2.0], "roles": [
                ("CB_molotov", "burns the tunnel's exit when they rush: they wait or they burn", 6.8),
                ("CB_flash", "a flash at the tunnel's exit for your re-peek, never in your eyes", 9.7),
                ("CB_he", "hits the ones stacked in the tunnel before they come out", 12.4),
                ("CB_smoke", "closes the tunnel once the fire is out: they have to cross it to come in", 15.6)]}},
        "T": {
            # "see": where its entry crosses, the base's T spot most met there (its smokes judged by the CTs' view of it)
            "A": {"from": "Long A", "see": [1375.0, 2016.0, -7.0], "roles": [
                ("TA_smoke", "cuts the cross from CT spawn: they can't see you cross onto the site", 21.4),
                ("TA_molotov", "burns the site's corner: the one hiding there moves or burns", 27.8),
                ("TA_he", "hits the one at the back of the site (Goose)", 30.1),
                ("TA_flash|TA_flash2", "a flash over Long's exit as you come out: the ones holding the site blinded", 30.0)]},
            "B": {"from": "Upper Tunnel", "see": [-2013.0, 1822.0, 27.0], "roles": [
                ("TB_smoke_doors", "closes B Doors: the CTs rotating from mid can't see in", 14.4),
                ("TB_smoke_window", "closes Window: nobody shoots you from above as you come in", 11.0),
                ("TB_flash|TB_flash3|TB_flash4|TB_flash5|TB_flash6", "a flash over the site as you come out of the tunnel", 10.6),
                ("TB_molotov", "burns the back of the site: the one hiding there moves or burns", 27.3)]}},
    },
    # 23/10, built alone (the user: "tester de travailler une autre carte de cs en autonomie du début à la fin"): the CTs'
    # clock and post from tools/site_timing.py de_mirage (916 matches), each take's way in the base's most used (A Ramp,
    # Apps) and its crossing the Ts' duel spot most met in it; the roles are the ones tools/stuff_build.py plans
    "de_mirage": {
        "CT": {
            "A": {"go": 5.5, "on_site": 21.5, "post": [-576.0, -1341.0, -158.7], "roles": []},
            "B": {"go": 8.5, "on_site": 23.0, "post": [-1308.4, 320.1, -167.1], "roles": []}},
        "T": {
            "A": {"from": "A Ramp", "see": [289.5, -1502.6, -175.8], "roles": []},
            "B": {"from": "Apps", "see": [-1885.1, 737.6, -48.0], "roles": []}},
    },
})


_REACH = {}


def reachable(mp, spot, frm):
    """A player alone walks or jumps onto the spot (23/10 eve, the user on Mirage's B defense: "la grenade ... s'envoie
    depuis un spot qui n'est accessible qu'en boost, donc pas vraiment pertinente sur des utilisateurs qui joueraient
    plutôt en solo queue"; its HE's spot, 74 u over the site's floor, a pro's from a boost): a way on the map's mesh from frm
    (the site's middle) onto it, no climb over a crouched jump's (real_client.route_areas: 66 u)."""
    if not frm:
        return True
    k = (mp, round(spot[0]), round(spot[1]), round(spot[2]), round(frm[0]), round(frm[1]))
    if k not in _REACH:
        try:
            import real_client as RC
            pts, areas, rises = RC.route_areas(mp, frm, spot)
            _REACH[k] = bool(areas) or math.dist(frm[:2], spot[:2]) < 64
        except Exception:
            _REACH[k] = True
    return _REACH[k]


PROBED = os.path.join(HERE, "resources", "spots_probed.json")


def corner_ok(mp, pos):
    """A spot the game locks you into, as tools/checks/check_training.py's rebuilt check judges it (tools/spot_probe.py:
    16 directions from the player, an arc of 5 to 12 of them blocked within 6 u, not all of them; 22/10, the user:
    "chaque spot est censé être un endroit dans lequel tu peux te bloquer dans un coin"). 24/10, the real-client battery:
    Anubis B's HE nook (15 of 16 blocked) and Cache A's Catwalk smoke (an arc of 4) were the two spots the driver never
    stood on. None: never probed."""
    v = ((config.read_json(PROBED, {}) or {}).get(f"{mp}|{round(pos[0])}|{round(pos[1])}|{round(pos[2])}") or {}).get("d")
    if not v:
        return None
    b = [0 <= d < 6.0 for d in v]
    run = best = 0
    for i in range(32):
        run = run + 1 if b[i % 16] else 0
        best = max(best, run)
    # a pocket open on 2 ways at least (24/10: Vertigo B's, an arc of 13, the driver stood on it to the unit and threw
    # it right; Anubis B's HE, 15 of 16 blocked, never stood on)
    return 5 <= min(best, 16) <= 13 and sum(b) <= 14


def pick(found, anchor, mp, typ, target=None, smokes=(), team=3, site_c=None, w=0.1):
    """The one to learn: a still throw before a jumpthrow, then the nearest its place and its anchor (the defender's
    post, the take's first spot); a flash the guided bot saw blind its own thrower never (tools/victim_check.py:
    "jamais dans tes yeux"); a molotov on its place's floor before one on a box above it (21/10, Dust2's A: 66 u up on
    the site's box, its fire burns the box top, not the corner)."""
    from wily.training import train
    ok = [c for c in found if not train._thrower_sees(mp, typ, c["pos"], c["pop"])]
    ok = [c for c in ok if reachable(mp, c["pos"], site_c)]   # never a boost's spot (23/10 eve)
    ok = [c for c in ok if corner_ok(mp, c["pos"]) is not False]   # a corner, probed in the game (24/10)
    # a flash popping inside one of its own smokes blinds nobody (21/10, Dust2's T A: the base's flash over Long's exit
    # pops right above its cross smoke, 55 u from it)
    if typ == "flash":
        ok = [c for c in ok if all(math.dist(c["pop"], s) > SMOKE_R for s in smokes)]
    # one the guide threw at its victims and none took it (21/10, Dust2: CT A's flash over Long Doors and T B's at the
    # tunnel's exit, 0/2; T A's cross smoke from Long Doors, its view not cut): never while another took one; not
    # checked yet counts as maybe
    # out of its place's sight where it really pops (22/10: a molotov judged on its place, 0.013 duels a match, popped
    # where the base's duels see its spot, 0.03), and a flash or an HE with someone in its reach (a pop 690 u over B
    # blinds nobody of the base)
    n_matches = max(1, len(train._map_dirs(mp)))
    ok = [c for c in ok if train._exposed(mp, c["pos"], c["pop"], 150, 120) / n_matches <= 0.02]
    if typ in ("flash", "he"):
        ok = [c for c in ok if _has_victims(mp, typ, c, team)]
    took = lambda c: _took(mp, typ, c)
    if any(took(c) is True for c in ok):
        ok = [c for c in ok if took(c) is True]
    else:
        ok = [c for c in ok if took(c) is not False]
    if not ok:
        return None
    up = lambda c: typ == "molotov" and target is not None and c["pop"][2] - target[2] > 40
    return min(ok, key=lambda c: (c["how"] != "still", up(c), c["off"] + (w * math.dist(c["pos"][:2], anchor[:2]) if anchor else 0.0)))


# how long each takes from the hand to doing its job: a smoke lands and blooms, a molotov bursts on landing, an HE's
# and a flash's fuse
FLIGHT = {"smoke": 2.5, "molotov": 1.5, "he": 1.6, "flash": 1.62}
TYPICAL = (0.4, 0.6)   # the typical takes (by how fast they get there), as the defense played (execs.hold) uses them


def moment(mp, typ, pop, go, E, floor=None):
    """When to throw it, s after GO (21/10: the guide threw them all in 8 s and the Bridge's flash blinded nobody: the
    fast takes' Ts were not there yet): the base's takes through its place (train._rush: the fastest fifth of the
    Ts who reach it; 21/10 again: those asked four grenades from four corners in two seconds, now the typical ones,
    the middle fifth), a flash and an HE popping as the first one gets there, a smoke and a molotov up a second before.
    None when no take of the base goes through it."""
    from wily.training import train
    if typ == "flash" and floor is not None:   # its place: the floor under its pop (a flash pops 200 u up)
        pop = [pop[0], pop[1], floor]
    R = train._rush(mp, pop, FLIGHT[typ], max(0.0, go - 2.0), E, q=TYPICAL)
    if not R:
        return None
    return round(max(0.5, float(R["at"]) - go - FLIGHT[typ] - (1.0 if typ in ("smoke", "molotov") else 0.0)), 1)


def _has_victims(mp, typ, c, team):
    """An enemy of its thrower's team (2: T, 3: CT) of the base in its reach when it pops (a flash 650 u, an HE 350 u:
    train._victims)."""
    from wily.training import train
    return bool(train._victims(mp, team, typ, c["pop"], c["pos"], None, None, checked=False))


def _took(mp, typ, c):
    """True when the guide found one of its victims taking it, False when it found none did, None not checked."""
    from wily.training import train
    book = config.read_json(os.path.join(config.HERE, "resources", "victims_checked.json"), {}) or {}
    rec = book.get(train.victim_key(mp, typ, c["pos"], c["pop"]))
    if not rec or not rec.get("victims"):
        return None
    return any(v.get("hit") for v in rec["victims"])


GAP, MARGIN = 1.5, 0.5   # one player's run to his next corner and throw (Exec.cs: the guide's 1.5 s); landed before they come
# 23/10 eve, his real test of Mirage's A defense: its smoke thrown 9 s after its flash (their corners 1798 u apart on the
# mesh), asked 1.6 s after, the whole 9 s after the Ts were on the site; the guide had made it in time by being put on each
# spot. Between two throws now: the mesh's way run with a grenade in hand, and drawing, aiming and letting it go.
RUN, THROW = 240.0, 1.6   # u/s with a grenade in hand; s from one throw to the next one gone on the same corner (his: 1.8-2.6)


def _leg(mp, a, b):
    """Seconds from a throw at a to the next one at b by the same player."""
    if math.dist(a[:2], b[:2]) < 40 and abs(a[2] - b[2]) < 40:
        return max(GAP, THROW)
    try:
        import real_client as RC
        pts = RC.path(mp, a, b)
        L = sum(math.dist(p[:2], q[:2]) for p, q in zip([a] + pts[:-1], pts))
    except Exception:
        L = 1.4 * math.dist(a[:2], b[:2])
    return THROW + L / RUN


LASTS = {"smoke": 17.0, "molotov": 7.0}   # Exec.cs ExecLasts: how long each one counts as up (a flash, an HE: 5 s)


def _all_up(mp, throws):
    """A take thrown by one player in its order, the mesh's way run between its spots (_leg): the moment they are all up
    together, or None when they never are (24/10, the real-client battery: Anubis's two execs, 6-12 s of running between
    their spots, their first smoke gone before their flash was up)."""
    t, prev, first, last = 0.0, None, 0.0, 1e9
    for x in throws:
        if prev is not None:
            t += _leg(mp, prev, x["pos"])
        up = t + FLIGHT.get(x["type"], 1.6)
        first, last = max(first, up), min(last, up + LASTS.get(x["type"], 5.0))
        prev = x["pos"]
    return round(first, 1) if first <= last else None


def _schedule(throws, arrive, go, mp=None, start=None):
    """A defense's moments one player can throw (21/10, Dust2's CT B: its molotov, flash and HE asked 0.9 s apart from
    three corners, the guide's last one down after the Ts were on the site): between two of them the way from one corner
    to the next (_leg), the first one once he is there from where he starts, each one down before they are on the site,
    each as near its own moment as can be (the order that moves them least). -> True when one player can do it all."""
    import itertools
    best = None
    legs = {}

    def leg(i, j):
        if (i, j) not in legs:
            a = start if i is None else throws[i]["pos"]
            legs[(i, j)] = _leg(mp, a, throws[j]["pos"]) if mp and a is not None else GAP
        return legs[(i, j)]
    for order in itertools.permutations(range(len(throws))):
        rel, nxt, nj = {}, None, None
        for i in reversed(order):
            x = throws[i]
            r = min(x["at"], arrive - FLIGHT[x["type"]] - MARGIN, *([nxt - leg(i, nj)] if nxt is not None else []))
            rel[i], nxt, nj = r, r, i
        early, ok, prev = 0.0, True, None   # the soonest each can go, from where he starts
        for i in order:
            early = (leg(None, i) if start is not None else 0.0) if prev is None else early + leg(prev, i)
            ok = ok and early <= rel[i] + 0.05
            prev = i
        cost = sum(abs(rel[i] - throws[i]["at"]) for i in rel) + (1000 if min(rel.values(), default=0) < 0 or not ok else 0)
        if best is None or cost < best[0]:
            best = (cost, rel, ok)
    for i, r in (best[1] if best else {}).items():
        if abs(r - throws[i]["at"]) >= 0.05:
            print(f"  {throws[i]['found']}: at {round(r, 1)} s, not {throws[i]['at']} (one player's run, down before they come at {arrive})", flush=True)
        throws[i]["at"] = round(max(0.0, r), 1)
        throws[i]["t"] = round(go + throws[i]["at"], 1)
    return bool(best and best[2])


SMOKE_R = 200   # a smoke's cloud and a margin: a flash popping nearer is inside it


BLOCKS = 0.7   # a defense's molotov: 7 of 10 of the Ts by it go through its fire (not round it)


def train_blocks(mp, land, t_pop):
    from wily.training import train
    return train.molotov_blocks(mp, land, t_pop)


def build(mp, side, site, C, E):
    throws = []
    # its smokes picked first: the others are picked out of them (a flash never inside one); a role's lineups from all its
    # searches ("TA_flash|TA_flash2": the place searched again)
    roles = sorted(C["roles"], key=lambda r: "smoke" not in r[0])
    for role, why, t in roles:
        R = {"found": []}
        for r in role.split("|"):
            Ri = config.read_json(os.path.join(config.OUT, "selftest", f"lineup_finder_{mp}_{r}.json"), {}) or {}
            R = {**Ri, "found": R["found"] + (Ri.get("found") or [])} if Ri else R
        role = role.split("|")[0]
        smokes = [x["target"] for x in throws if x["type"] == "smoke"]
        site_c = (((__import__("wily.training.train", fromlist=["train"]).site_data(mp).get("sites") or {})
                   .get(f"Bombsite{site}") or {}).get("center"))
        # a defense's next one near the ones already picked (23/10 eve, his real test of Mirage's A: one player could not
        # run from its flash's corner to its smoke's, 1798 u, before they came): their middle, three times the weight
        if side == "CT" and throws:
            anchor = [sum(x["pos"][k] for x in throws) / len(throws) for k in range(3)]
        else:
            anchor = C.get("post") or (throws[0]["pos"] if throws else None)
        c = pick(R.get("found") or [], anchor, mp, R.get("type"), R.get("target"), smokes,
                 team=3 if side == "CT" else 2, site_c=site_c, w=0.3 if side == "CT" else 0.1)
        if not c:
            print(f"{side} {site} {role}: none found", flush=True)
            continue
        typ = R["type"]
        if side == "CT":
            at = moment(mp, typ, c["pop"], C["go"], E, floor=c["pos"][2])
            at = round(max(0.0, t - C["go"]), 1) if at is None else at   # no take through it: the base's moment
            when = f"at {at} s after GO (the base's: {round(t - C['go'], 1)})"
            if typ == "molotov":   # a fire they walk round blocks nothing (22/10, Dust2's A: 58 % went round it)
                share, n = train_blocks(mp, c["pop"], C["go"] + at + FLIGHT["molotov"])
                if share is not None and share < BLOCKS:
                    print(f"{side} {site} {role}: its fire goes round ({round(100 * (1 - share))} % of {n} Ts walk past it): left out", flush=True)
                    continue
        else:
            at, when = None, f"the base's moment {t}"
        from wily.training import setups
        throws.append({"type": typ, "pos": c["pos"], "ang": [c["pitch"], c["yaw"]], "how": c["how_words"], "click": c["click_words"],
                       "target": c["pop"], "nade_at": c["nade_at"], "nade_v": c["nade_v"], "why": why,
                       "why_zone": setups.zone_at(mp, c["pop"]) or "", "src": c.get("src") or ("pro" if c.get("pro") else None),
                       "t": round(C["go"] + at, 1) if at is not None else t, "t_base": t, "at": at, "off": c["off"], "found": role})
        print(f"{side} {site} {role}: {typ} {c['how_words']} {c['click_words']} from {c['pos']} aim {c['pitch']} {c['yaw']} -> {c['pop']} ({c['off']} u off its place), {when}", flush=True)
    if side == "T" and C.get("see"):   # a take's smoke away from its entry's crossing: the CTs looking at where the Ts come
        # out by it, through it (22/10, the user on Dust2's exec A smoke to Short: "faut que la personne qui subisse la smoke
        # soit dans la short, soit ... sur le site en train de regarder short"): the Ts' duel spot most met by its landing,
        # its floor, off the site (the site's own: the fights after the plant); one by the crossing keeps the crossing's
        from wily.training import train
        for x in [x for x in throws if x["type"] == "smoke"]:
            L = x["target"]
            if math.dist(L[:2], C["see"][:2]) <= 500:
                continue
            near = [h for h in train._spots(mp)["T"] if h[3] >= 8 and math.dist(h[:2], L[:2]) <= 450 and abs(h[2] - L[2]) < 100
                    and train.zone_raw(mp, h[:3]) != f"Bombsite{site}"]
            if near:   # and the CTs beyond it turned to the site, in Short coming back to it (22/10, the same smoke: "la
                # personne ... soit en train de rotate du mid dans la short pour aller en A, soit en défense avancée short,
                # du coup plutôt orienté mid, et du coup pareil en rota pour revenir sur le bomb site")
                ctr = ((train.site_data(mp).get("sites") or {}).get(f"Bombsite{site}") or {}).get("center")
                x["see"] = [[round(float(v), 1) for v in max(near, key=lambda h: h[3])[:3]]] + ([ctr] if ctr else [])
    fires = [x["target"] for x in throws if x["type"] == "molotov"]
    for x in [x for x in throws if x["type"] == "smoke"]:
        d = min((math.dist(x["target"], f) for f in fires), default=1e9)
        if d < 220:
            print(f"{side} {site} {x['found']}: lands on the molotov's fire ({round(d)} u): left out", flush=True)
            throws.remove(x)
    if side == "CT":
        arrive = round(C["on_site"] - C["go"], 1)
        from wily.training import train
        first = min(throws, key=lambda x: x["at"])["pos"] if throws else None
        start = train.start_near(mp, first, 0.0) if first else None   # where the plugin puts him (execs.drill)
        start = (start or {}).get("pos") if isinstance(start, dict) else start
        base = [dict(x) for x in throws]
        while throws and not _schedule(throws, arrive, C["go"], mp, start):
            # one player cannot throw them all before they come: the one the farthest from the others left out, the rest
            # tried again (none offered below 3)
            far = max(throws, key=lambda x: sum(math.dist(x["pos"][:2], y["pos"][:2]) for y in throws))
            print(f"{side} {site} {far['found']}: too far from the others for one player before they come at {arrive} s: left out", flush=True)
            throws = [dict(y) for y in base if y["found"] != far["found"] and any(t["found"] == y["found"] for t in throws)]
            base = [dict(y) for y in throws]
            if len(throws) < 3:
                break
        throws.sort(key=lambda x: x["at"])   # in the order they are needed
        return {"go": C["go"], "arrive": round(C["on_site"] - C["go"], 1), "post": C["post"], "throws": throws,
                "about": "Wily's: the places from the base's CT grenades of this site, the lineups found from corners and thrown on the server"}
    # a take: all up at once (Exec.cs: a smoke counts 17 s, a fire 7, a flash or an HE 5), so the ones that last first and
    # the flash last, as you come out (21/10, Dust2's B: the base's order threw its flash 17 s before its molotov, never up
    # together), each the base's order among its kind, 1.5 s apart as one teammate would chain them
    RANK = {"smoke": 0, "molotov": 1, "he": 2, "flash": 3}
    throws.sort(key=lambda x: (RANK.get(x["type"], 1), x["t_base"]))
    while len(throws) >= 3 and _all_up(mp, throws) is None:
        # one player cannot have them all up together: the one the farthest from the others left out (none offered below 3)
        far = max(throws, key=lambda x: sum(math.dist(x["pos"][:2], y["pos"][:2]) for y in throws))
        print(f"{side} {site} {far['found']}: too far from the others for one player to have them all up at once: left out", flush=True)
        throws = [y for y in throws if y is not far]
    for i, x in enumerate(throws):
        x["at"] = round(1.5 * i, 1)
    return {"from": C["from"], "see": C.get("see"), "throws": throws,
            "about": "Wily's: the places from the base's T grenades of this site, the lineups found from corners and thrown on the server"}


PLAN_F = os.path.join(config.HERE, "resources", "stuff_plan.json")


def planned(mp, side, site, C):
    """Its roles the pros' way when tools/stuff_build.py planned them (22/10): each place's lineup the _v2 one found
    from a corner, out of sight, on its side; its words a template said with its place."""
    from wily.training import execs
    rows = (config.read_json(PLAN_F, {}) or {}).get(f"{mp}|{side}:{site}")
    if not rows:
        return C
    why = execs.WHY_T if side == "T" else execs.WHY_CT
    return dict(C, roles=[(f"{r['role']}_v2", why[r["type"]], r["t"]) for r in rows])


def main():
    mp = sys.argv[1] if len(sys.argv) > 1 else "de_fachwerk"
    from wily.training import train
    E = train._early(mp)
    for side, sites in CONF[mp].items():
        book = config.read_json(OUT[side], {}) or {}
        for site, C in sites.items():
            rec = build(mp, side, site, planned(mp, side, site, C), E)
            if len(rec.get("throws") or []) < 3:   # not a take or a defense: Prepare doesn't offer it (22/10, Dust2's B defense)
                print(f"{side} {site}: {len(rec.get('throws') or [])} grenades only: left out", flush=True)
                book.pop(f"{mp}|{site}", None)
                continue
            book[f"{mp}|{site}"] = rec
        config.write_json(OUT[side], book)
        print("written", OUT[side], flush=True)


if __name__ == "__main__":
    main()
