"""A site's clock in the base (21/10, for a map's defenses and takes, as tools/defense_build.py needs it):

    python tools/site_timing.py <map>

- "go": when the base's CTs get onto the site (the median round's first CT within 350 u of its middle): a defense's GO.
- "on_site": when the Ts' takes are on it (the first quarter of the rounds whose Ts reach it in the first 40 s): a
  defense's whole limit.
- "post": the CT spot the base holds most when its Ts take the site (train.take_spots), in the site's own place.
Read from 60 of the map's demos (CTs) and train._early (Ts)."""
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
from wily.core import config  # noqa: E402
from wily.training import train  # noqa: E402


def main():
    mp = sys.argv[1]
    S = train.site_data(mp)["sites"]
    dirs = train._map_dirs(mp)[-60:]
    E = train._early(mp)
    out = {}
    FLOOR = 200   # 23/10, Nuke: B 352 u under A and 228 u beside it, its CTs and Ts were A's; on the site's own floor
    for site in ("A", "B"):
        c = S[f"Bombsite{site}"]["center"]
        takes = [t for t in train.take_spots(mp, site) if t.get("zone") == f"Bombsite{site}"] or train.take_spots(mp, site)
        post = max(takes, key=lambda t: t["n"])["pos"] if takes else None
        firsts, at_post = [], []
        for d in dirs:
            try:
                P = pd.read_parquet(os.path.join(config.OUT, "deep", d, "samples.parquet"), columns=["side", "round", "t", "X", "Y", "Z"])
            except Exception:
                continue
            P = P[(P.side == "CT") & (P.t <= 40)]
            firsts += list(P[(np.hypot(P.X - c[0], P.Y - c[1]) < 350) & (np.abs(P.Z - c[2]) < FLOOR)].groupby("round").t.min())
            if post:
                at_post += list(P[(np.hypot(P.X - post[0], P.Y - post[1]) < 250) & (np.abs(P.Z - post[2]) < 120)].groupby("round").t.min())
        # GO: the median round's first CT on the site's middle, or sooner the defenders who go to its post straight away
        # (their first quarter): Dust2's A was set by hand to 5 s, its CTs holding Long from outside the site (21/10)
        go_mid = round(float(np.median(firsts)), 1) if firsts else None
        go_post = round(float(np.quantile(at_post, 0.25)), 1) if at_post else None
        go = min(x for x in (go_mid, go_post) if x is not None) if (go_mid is not None or go_post is not None) else None
        T = E[(np.hypot(E.X.to_numpy() - c[0], E.Y.to_numpy() - c[1]) < 350)
              & (np.abs(E.Z.to_numpy() - c[2]) < FLOOR)].groupby(["d", "round"], observed=True).t.min()
        on = round(float(T.quantile(0.25)), 1) if len(T) else None
        out[site] = {"go": go, "on_site": on, "post": post, "go_mid": go_mid, "go_post": go_post, "ct_rounds": len(firsts), "t_rounds": int(len(T))}
        print(site, out[site], flush=True)
    config.write_json(os.path.join(config.OUT, "selftest", f"site_timing_{mp}.json"), out)


if __name__ == "__main__":
    main()
