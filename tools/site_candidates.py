"""Where a map's players really put each grenade for a site, side by side (21/10, the user: "mets en place le même principe
qu'on a établi sur Fachwerk ... sur la map sur laquelle tu auras le plus de datasets"): the places a site's takes (T) or
defenses (CT) are built on, before any lineup is chosen.

    python tools/site_candidates.py <map> [--side T|CT|both]      -> out/selftest/site_candidates_<map>.json

For each site and side: the base's grenades of that side landing 1600 u of the site at most, by type, their landings
grouped in 160 u cells (same floor), each place with how many times, its median moment of the round, what it did (a
flash: enemies blinded; an HE or a molotov: damage), how often that side won the round, where it is thrown from most.
The most thrown first; tools/lineup_finder.py then finds a lineup from a corner onto each chosen place."""
import json
import math
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from wily.core import config  # noqa: E402
from wily.training import train  # noqa: E402


def places(mp, side, site, N):
    S = train.site_data(mp)["sites"][f"Bombsite{site}"]
    c = S["center"]
    M = N[(N.side == side) & (np.hypot(N.land_X - c[0], N.land_Y - c[1]) < 1600)]
    out = []
    for typ, G in M.groupby("type"):
        G = G.assign(cx=(G.land_X // 160).astype(int), cy=(G.land_Y // 160).astype(int), cz=(G.land_Z // 120).astype(int))
        for (cx, cy, cz), g in G.groupby(["cx", "cy", "cz"]):
            if len(g) < 12:
                continue
            land = [round(float(g.land_X.median()), 1), round(float(g.land_Y.median()), 1), round(float(g.land_Z.median()), 1)]
            eff = None
            if typ == "flash":
                eff = round(float(g.enemies_blind.mean()), 2)
            elif typ in ("he", "molotov"):
                eff = round(float(g.damage.mean()), 1)
            out.append({"type": typ, "n": len(g), "land": land, "to": str(g.land_zone.mode().iloc[0]) if g.land_zone.notna().any() else "?",
                        "from": str(g.zone.mode().iloc[0]) if g.zone.notna().any() else "?",
                        "from_at": [round(float(g.X.median()), 1), round(float(g.Y.median()), 1), round(float(g.Z.median()), 1)],
                        "t": round(float(g.t.median()), 1), "eff": eff, "won": round(float(g.won.mean()), 2),
                        "to_site": round(math.dist(land[:2], c[:2]))})
    out.sort(key=lambda r: -r["n"])
    return out


def main():
    mp = sys.argv[1]
    side = sys.argv[sys.argv.index("--side") + 1] if "--side" in sys.argv else "both"
    N = pd.read_parquet(os.path.join(config.OUT, "population", "nades.parquet"), filters=[("map", "==", mp)])
    N = N[N.land_X.notna()]
    print(f"{mp}: {len(N)} grenades, {N['match'].nunique()} matches", flush=True)
    res = {}
    for sd in (["T", "CT"] if side == "both" else [side]):
        for site in ("A", "B"):
            P = places(mp, sd, site, N)
            res[f"{sd}:{site}"] = P
            print(f"== {sd} {site}: {len(P)} places thrown 12+ times", flush=True)
            for typ in ("smoke", "flash", "molotov", "he"):
                for r in [r for r in P if r["type"] == typ][:6]:
                    print(f"  {typ:7} n={r['n']:4} t={r['t']:5} {r['from']:>14} -> {r['to']:<14} eff={r['eff']} won={r['won']} land={r['land']} from={r['from_at']} {r['to_site']} u from the site", flush=True)
    config.write_json(os.path.join(config.OUT, "selftest", f"site_candidates_{mp}.json"), res)


if __name__ == "__main__":
    main()
