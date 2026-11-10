"""A map's sites as tools/defense_build.py's CONF has them, read from the base (23/10, the user: "faire toutes les
recherches sur toutes les cartes et tous les autotests sans vraie connexion humaine"), what Mirage's was by hand:

    python tools/site_conf.py <map>      -> out/selftest/site_conf_<map>.json

- a defense (CT): its GO, its whole limit and its post from tools/site_timing.py (out/selftest/site_timing_<map>.json,
  made first when missing), none when its Ts are on the site less than 4 s after its GO;
- a take (T): its way in, the zone the base's Ts come from most onto the site in the round's first 40 s (train._early:
  the last zone before the site's), and where its entry crosses ("see"), the Ts' duel spot most met in that zone within
  1100 u of the site's middle (train._spots).
The roles stay empty: tools/stuff_build.py plans them (resources/stuff_plan.json). A map in CONF keeps its own."""
import json
import math
import os
import subprocess
import sys
from collections import Counter

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from wily.core import config  # noqa: E402
from wily.training import train  # noqa: E402

MIN_WINDOW = 4.0   # a defense's seconds from GO to the base's fast takes on the site: its grenades thrown and up by then


def entries(mp, site):
    """{zone: how many of the base's Ts came onto the site from it} (each T of each round once, its first time in)."""
    E = train._early(mp)
    if not len(E):
        return Counter()
    E = E.sort_values(["d", "round", "sid", "t"])
    z = E.zone.astype(str).to_numpy()
    key = (E.d.to_numpy().astype(np.int64) * 100000 + E["round"].to_numpy().astype(np.int64) * 100) * 1000 + E.sid.cat.codes.to_numpy()
    cuts = np.r_[0, np.nonzero(np.diff(key))[0] + 1, len(key)]
    want, out = f"Bombsite{site}", Counter()
    for a, b in zip(cuts[:-1], cuts[1:]):
        t = z[a:b]
        hit = np.nonzero(t == want)[0]
        if not len(hit) or hit[0] == 0:
            continue
        prev = [x for x in t[:hit[0]][::-1] if x and x not in ("nan", "None", want)]
        if prev:
            out[prev[0]] += 1
    return out


def take(mp, site, S, sp):
    from wily.insights import nades
    c = S[f"Bombsite{site}"]["center"]
    ways = entries(mp, site)
    for zone, n in ways.most_common(4):
        cells = sorted((h for h in sp.get("T") or [] if math.dist(h[:2], c[:2]) < 1100 and train.zone_raw(mp, h[:3]) == zone),
                       key=lambda h: -h[3])
        if cells:
            return {"from": nades.humanize(zone, mp), "see": [round(float(v), 1) for v in cells[0][:3]], "roles": [],
                    "_way": {"zone": zone, "entries": n, "of": sum(ways.values()), "spot_n": int(cells[0][3])}}
    return None


def main():
    mp = sys.argv[1]
    f = os.path.join(config.OUT, "selftest", f"site_timing_{mp}.json")
    if not os.path.exists(f):
        subprocess.run([sys.executable, os.path.join(HERE, "tools", "site_timing.py"), mp], cwd=HERE, check=True)
    timing = json.load(open(f, encoding="utf-8"))
    S = train.site_data(mp).get("sites") or {}
    sp = train._spots(mp)
    out = {"CT": {}, "T": {}}
    for site in ("A", "B"):
        if not (S.get(f"Bombsite{site}") or {}).get("center"):
            print(f"{mp} {site}: no site in the map's data", flush=True)
            continue
        t = timing.get(site) or {}
        if t.get("go") is not None and t.get("on_site") is not None and t.get("post"):
            if t["on_site"] - t["go"] >= MIN_WINDOW:
                out["CT"][site] = {"go": t["go"], "on_site": t["on_site"], "post": t["post"], "roles": []}
            else:   # Nuke's A: its CTs on it at 12 s, its fast takes too: no grenade from the site lands before them
                print(f"{mp} CT {site}: {t['on_site'] - t['go']:.1f} s from GO to the Ts on it: no defense from the site, not searched", flush=True)
        else:
            print(f"{mp} CT {site}: no clock in the base ({t})", flush=True)
        x = take(mp, site, S, sp)
        if x:
            out["T"][site] = x
        else:
            print(f"{mp} T {site}: no way in found", flush=True)
    out = {k: v for k, v in out.items() if v}
    dst = os.path.join(config.OUT, "selftest", f"site_conf_{mp}.json")
    config.write_json(dst, out)
    for side, sites in out.items():
        for site, v in sites.items():
            print(mp, side, site, {k: v[k] for k in v if k != "roles"}, flush=True)
    print("written", dst, flush=True)


if __name__ == "__main__":
    main()
