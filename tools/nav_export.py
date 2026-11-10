"""Each map's navigation mesh for the training server's plugin (30/10, round 11: a bot off its recorded way had no way round
a wall: Train's T Upper ledge and spawn stairs, Fachwerk's Apps, Mirage's Apartments, bots sliding or standing for a
minute). From the map's own .nav (wily/training/navmesh.py): its floor areas (corners) and their links, each link's edge
middle and how far the floor rises past it (a jump over 18 u, no way over a crouched jump's 66 u), as the real-client
test walks it (tools/real_client.route_areas). The plugin's Nav.cs finds its ways on it.

    python tools/nav_export.py [map ...]   ->   <server>/game/csgo/coach/nav/<map>.json (both training servers)"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from wily.training import navmesh  # noqa: E402

MAPS = ["de_train", "de_boulder", "de_overpass", "de_mirage", "de_dust2", "de_fachwerk", "de_nuke", "de_inferno", "de_cache",
        "de_anubis", "de_ancient", "de_vertigo"]
OUTS = [r"E:\CS2Server\game\csgo\coach\nav", r"E:\CS2Server2\game\csgo\coach\nav"]


def export(mp):
    N = navmesh.load(mp)
    if not N:
        return None
    A = N["areas"]
    areas, links = [], []
    for aid, ar in A.items():
        P = ar["pts"]
        areas.append([int(aid)] + [round(float(v), 1) for v in P.reshape(-1)])
        for i, conn in enumerate(ar["edges"]):
            p, q = P[i], P[(i + 1) % len(P)]
            mid = (p + q) / 2
            for v in conn:
                if v not in A:
                    continue
                up = navmesh._plane_z(A[v]["pts"], mid[0], mid[1]) - mid[2]
                links.append([int(aid), int(v), round(float(mid[0]), 1), round(float(mid[1]), 1), round(float(mid[2]), 1), round(float(up), 1)])
    # its ladders (30/10, the user: "fix le map mesh"): each one's foot and top, the areas off each end
    ladders = [[int(L["id"]), *[round(v, 1) for v in L["bottom"]], *[round(v, 1) for v in L["top"]], [int(a) for a in L["bottoms"]],
                [int(a) for a in L["tops"]]] for L in N.get("ladders") or []]
    return {"map": mp, "areas": areas, "links": links, "ladders": ladders}


def main():
    maps = sys.argv[1:] or MAPS
    for mp in maps:
        d = export(mp)
        if d is None:
            print(mp, "no nav")
            continue
        for o in OUTS:
            if os.path.isdir(os.path.dirname(o)):
                os.makedirs(o, exist_ok=True)
                with open(os.path.join(o, f"{mp}.json"), "w", encoding="utf-8") as f:
                    json.dump(d, f, separators=(",", ":"))
        print(mp, len(d["areas"]), "areas", len(d["links"]), "links", len(d["ladders"]), "ladders", flush=True)


if __name__ == "__main__":
    main()
