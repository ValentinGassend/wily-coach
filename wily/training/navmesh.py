"""The map's navigation mesh, read from the game's own files (22/10, his test video: "le spot ... il est censé être dans
un coin, en tout cas je suis censé pouvoir me bloquer contre un mur", "c'est le long d'un mur mais pas dans un coin"):
where a player can stand, and where the walls are, so a stuff spot is one you lock yourself into, not "somewhere along a
wall" found from where the base's players happened to stand.

The .nav comes out of the map's .vpk (CS2's or the training server's copy), no download. CS2's nav (version 35 and 36:
36 has a longer header) is polygons of corners shared by the areas; each area's edge lists the areas it opens onto. An
edge opening onto nothing is the mesh's border: a wall, a crate, a drop. The mesh is laid out for a player's centre, so a
player pressed into a corner stands on a border vertex where two border edges meet.

    corner(mp, p)       -> {"corner": bool, "walls": [angle of each wall touching p], "angle": between the two, ...}
    on_mesh(mp, p)      -> whether a player's centre can stand there (a spawn or a bot not inside a wall)"""
import io
import math
import os
import struct

import numpy as np

from wily.core import config

NAV_D = os.path.join(config.OUT, "nav")
_NAV = {}


def _vpks(mp):
    """Where the map's package is: CS2's own maps, the training server's, a community map's first part."""
    from wily.training import replay
    out = []
    try:
        from wily.core import steamlink   # noqa: F401  (CS2's install folder when known)
    except Exception:
        pass
    roots = [os.path.join(config.settings().get("cs2_dir") or "", "game", "csgo", "maps"),
             r"C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\maps",
             os.path.join(getattr(replay, "SERVER", r"E:\CS2Server"), "game", "csgo", "maps"),
             r"E:\CS2Server\game\csgo\maps"]
    for r in roots:
        f = os.path.join(r, mp + ".vpk")
        if r and os.path.isfile(f):
            out.append(f)
    addons = os.path.join(r"E:\CS2Server\game\csgo_community_addons", mp)
    if os.path.isdir(addons):
        out += sorted(os.path.join(addons, f) for f in os.listdir(addons) if f.endswith(".vpk"))
    return out


def _nav_bytes(mp):
    f = os.path.join(NAV_D, mp + ".nav")
    if os.path.isfile(f):
        with open(f, "rb") as fh:
            return fh.read()
    import vpk
    for p in _vpks(mp):
        try:
            data = vpk.open(p).get_file(f"maps/{mp}.nav").read()
        except Exception:
            continue
        os.makedirs(NAV_D, exist_ok=True)
        with open(f, "wb") as fh:
            fh.write(data)
        return data
    return None


def _corner_block(d):
    """Where the corner list starts: a count, then that many points on the map (36's header is longer than 35's)."""
    for off in range(12, 4096):
        n = struct.unpack_from("I", d, off)[0]
        if not 100 < n < 500000 or off + 4 + 12 * 6 > len(d):
            continue
        pts = [struct.unpack_from("fff", d, off + 4 + 12 * j) for j in range(6)]
        if all(all(math.isfinite(v) and abs(v) < 20000 for v in q) and (abs(q[0]) > 1e-3 or abs(q[1]) > 1e-3) for q in pts):
            return off
    raise ValueError("no corner list found")


def _parse(d):
    f = io.BytesIO(d)
    f.seek(_corner_block(d))
    nc = struct.unpack("I", f.read(4))[0]
    corners = np.frombuffer(f.read(12 * nc), dtype=np.float32).reshape(nc, 3).astype(float)
    npoly = struct.unpack("I", f.read(4))[0]
    polys = []
    for _ in range(npoly):
        k = f.read(1)[0]
        polys.append(list(struct.unpack(f"{k}I", f.read(4 * k))))
        f.read(4)
    # the area list: its count (one per polygon in the maps read so far), then areas that read back cleanly
    end = f.tell()
    for off in range(end, end + 2048):
        na = struct.unpack_from("I", d, off)[0]
        if not 0 < na <= 4 * npoly:
            continue
        try:
            areas = _areas(d, off + 4, na, polys, corners)
        except (struct.error, IndexError, ValueError):
            continue
        return areas, _ladders(d, _AREAS_END[0], areas)
    raise ValueError("no area list found")


_AREAS_END = [0]


def _ladders(d, off, A):
    """The map's ladders, right after its areas (30/10, the user: "fix le map mesh": Overpass's bots above the ladder down to
    Connector went round by Playground, the mesh read without them): a count, then 68 bytes each: its id, its width, its top
    and its bottom (x y z), its length, its direction, the 4 areas off its top and the 3 off its bottom (0: none). Checked
    against the areas' own lists (the ladders up and down from each); none kept when they don't match."""
    try:
        n = struct.unpack_from("I", d, off)[0]
        if n > 512:
            return []
        out = []
        for k in range(n):
            o = off + 4 + 68 * k
            lid, width = struct.unpack_from("If", d, o)
            top, bot = struct.unpack_from("3f", d, o + 8), struct.unpack_from("3f", d, o + 20)
            tops = [a for a in struct.unpack_from("4I", d, o + 40) if a and a in A]
            bots = [a for a in struct.unpack_from("3I", d, o + 56) if a and a in A]
            if not top[2] > bot[2] or not tops or not bots:
                return []
            out.append({"id": lid, "width": width, "top": [float(v) for v in top], "bottom": [float(v) for v in bot],
                        "tops": sorted(set(tops)), "bottoms": sorted(set(bots))})
        listed = {l for a in A.values() for side in a.get("ladders") or [] for l in side}
        if listed and not listed <= {x["id"] for x in out}:
            return []
        return out
    except struct.error:
        return []


def _areas(d, off, na, polys, corners):
    f = io.BytesIO(d)
    f.seek(off)
    out = {}
    for _ in range(na):
        aid = struct.unpack("I", f.read(4))[0]
        f.read(8)   # its dynamic attribute flags
        f.read(1)   # its hull
        pi = struct.unpack("I", f.read(4))[0]
        if pi >= len(polys):
            raise ValueError("polygon index")
        idx = polys[pi]
        f.read(4)
        edges = []
        for _ in range(len(idx)):   # each edge: the areas it opens onto
            n = struct.unpack("I", f.read(4))[0]
            if n > 64:
                raise ValueError("connections")
            edges.append([struct.unpack("II", f.read(8))[0] for _ in range(n)])
        f.read(5)   # legacy hiding spots and encounters
        lad = []
        for _ in range(2):   # ladders up from it, down from it
            n = struct.unpack("I", f.read(4))[0]
            if n > 64:
                raise ValueError("ladders")
            lad.append(list(struct.unpack(f"{n}I", f.read(4 * n))))
        out[aid] = {"id": aid, "pts": corners[idx], "edges": edges, "ladders": lad}
    _AREAS_END[0] = f.tell()
    return out


def load(mp):
    """{area id: {pts: N x 3 corners, edges: [area ids each edge opens onto]}}, or None (no nav for that map)."""
    if mp not in _NAV:
        d = _nav_bytes(mp)
        A = None
        L = []
        if d:
            try:
                A, L = _parse(d)
            except Exception as e:
                print("navmesh", mp, e, flush=True)
        _NAV[mp] = dict(_index(A), ladders=L) if A else None
    return _NAV[mp]


def _index(A):
    """The areas with their border segments (the edges opening onto nothing), each kept with the area's height."""
    segs = []
    for a in A.values():
        P = a["pts"]
        for i, conn in enumerate(a["edges"]):
            if not conn:
                p, q = P[i], P[(i + 1) % len(P)]
                segs.append((p[0], p[1], q[0], q[1], (p[2] + q[2]) / 2, a["id"]))
    S = np.asarray(segs, float) if segs else np.zeros((0, 6))
    ids = list(A)
    box = np.array([[A[i]["pts"][:, 0].min(), A[i]["pts"][:, 0].max(), A[i]["pts"][:, 1].min(), A[i]["pts"][:, 1].max()] for i in ids], float)
    return {"areas": A, "segs": S, "ids": ids, "box": box.reshape(-1, 4)}


def _area_at(N, p, dz=48.0):
    """The area under a point: its corners around it, its floor within dz (the lowest above-floor match)."""
    best = None
    B = N["box"]   # the areas whose box holds it (22/10: each of a session's spawns looped over Dust2's whole mesh)
    near = np.nonzero((B[:, 0] - 1 <= p[0]) & (p[0] <= B[:, 1] + 1) & (B[:, 2] - 1 <= p[1]) & (p[1] <= B[:, 3] + 1))[0]
    for j in near:
        a = N["areas"][N["ids"][j]]
        P = a["pts"]
        if not _inside(P[:, :2], p[:2]):
            continue
        z = float(P[:, 2].mean())
        if abs(p[2] - z) <= dz and (best is None or abs(p[2] - z) < best[0]):
            best = (abs(p[2] - z), a)
    return best[1] if best else None


def _inside(poly, q, eps=2.0):
    """q in the polygon (its border counted in, eps u around it: a corner spot stands on it)."""
    n = len(poly)
    inside = False
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if _dist_seg(q, (x1, y1), (x2, y2)) <= eps:
            return True
        if (y1 > q[1]) != (y2 > q[1]):
            x = x1 + (q[1] - y1) * (x2 - x1) / (y2 - y1)
            if x > q[0]:
                inside = not inside
    return inside


def _dist_seg(q, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((q[0] - ax) * dx + (q[1] - ay) * dy) / L))
    return math.hypot(q[0] - (ax + t * dx), q[1] - (ay + t * dy))


def on_mesh(mp, p, dz=48.0):
    """A player's centre can stand there: on an area of the mesh, its floor within dz. None: no mesh for the map."""
    N = load(mp)
    if not N:
        return None
    return _area_at(N, p, dz) is not None


def _plane_z(P, x, y):
    """The area's floor height at (x, y): the plane through its corners."""
    A = np.c_[P[:, 0], P[:, 1], np.ones(len(P))]
    c, *_ = np.linalg.lstsq(A, P[:, 2], rcond=None)
    return float(c[0] * x + c[1] * y + c[2])


def nearest(mp, p, r=48.0, dz=48.0, inset=4.0):
    """The nearest point a player's centre can stand on, on p's floor (its height within dz), r u of p at most: p itself
    on the mesh, else the nearest point of an area, inset u inside its border (22/10, his test video: "la personne qui
    cible le stuff est à moitié dans le mur": a victim stood where the base's player was, in the air or half in a wall).
    -> [x, y, z] or None (none that near; no mesh: None too, see on_mesh)."""
    N = load(mp)
    if not N:
        return None
    B = N["box"]
    near = np.nonzero((B[:, 0] - r <= p[0]) & (p[0] <= B[:, 1] + r) & (B[:, 2] - r <= p[1]) & (p[1] <= B[:, 3] + r))[0]
    best = None
    for j in near:
        P = N["areas"][N["ids"][j]]["pts"]
        if _inside(P[:, :2], p[:2], eps=0.0):
            q = (float(p[0]), float(p[1]))
        else:   # the nearest point of its border, a little inside it (toward its middle)
            q, dq = None, None
            for i in range(len(P)):
                a, b = P[i, :2], P[(i + 1) % len(P), :2]
                ab = b - a
                L = float(ab @ ab)
                t = 0.0 if L == 0 else max(0.0, min(1.0, float((np.asarray(p[:2]) - a) @ ab) / L))
                c = a + t * ab
                d = math.hypot(c[0] - p[0], c[1] - p[1])
                if dq is None or d < dq:
                    q, dq = c, d
            m = P[:, :2].mean(axis=0)
            v = m - q
            n = math.hypot(v[0], v[1])
            q = (float(q[0] + v[0] / n * min(inset, n)), float(q[1] + v[1] / n * min(inset, n))) if n > 0 else (float(q[0]), float(q[1]))
        d = math.hypot(q[0] - p[0], q[1] - p[1])
        z = _plane_z(P, q[0], q[1])
        if d <= r and abs(z - p[2]) <= dz and (best is None or (d, abs(z - p[2])) < best[0]):
            best = ((d, abs(z - p[2])), [round(q[0], 1), round(q[1], 1), round(z + 1.0, 1)])
    return best[1] if best else None


TOUCH = 14.0     # a wall's border this close to a player's centre: he is against it (the mesh is laid out for his centre)
CORNER = 45.0    # two walls this far apart in direction: they make a corner he locks into, not one straight wall


def route(mp, a, b, max_up=18.0):
    """The mesh's way from a to b for a bot walked along it (27/10, a defense's attackers: their real hits' ways end by
    the post they attack, the bot then left to the game or put away, never into the zone you hold): area after area,
    the middle of each edge it crosses, never up more than a step (a bot walked on a path does not jump), a drop fine.
    -> [[x, y, z], ...] from a to b, or [] when either is off the mesh or b is out of reach."""
    import heapq
    N = load(mp)
    if not N:
        return []
    A = N["areas"]

    def area(p):
        ar = _area_at(N, p)
        if ar is None:
            q = nearest(mp, p, r=80.0, dz=64.0)
            ar = _area_at(N, q) if q else None
        return ar
    sa, sb = area(a), area(b)
    if sa is None or sb is None:
        return []
    cen = {}

    def c(u):
        if u not in cen:
            cen[u] = A[u]["pts"].mean(axis=0)
        return cen[u]
    s, t = sa["id"], sb["id"]
    best, prev, q = {s: 0.0}, {}, [(0.0, s)]
    while q:
        f, u = heapq.heappop(q)
        if u == t:
            break
        if f - math.dist(c(u)[:3], c(t)[:3]) > best.get(u, 1e18) + 1e-6:
            continue
        P = A[u]["pts"]
        for i, conn in enumerate(A[u]["edges"]):
            mid = (P[i] + P[(i + 1) % len(P)]) / 2
            for v in conn:
                if v not in A:
                    continue
                if _plane_z(A[v]["pts"], mid[0], mid[1]) - mid[2] > max_up:
                    continue
                g = best[u] + math.dist(c(u)[:3], c(v)[:3])
                if g < best.get(v, 1e18):
                    best[v], prev[v] = g, (u, i)
                    heapq.heappush(q, (g + math.dist(c(v)[:3], c(t)[:3]), v))
    if t != s and t not in prev:
        return []
    chain = [t]
    while chain[-1] != s:
        chain.append(prev[chain[-1]][0])
    chain.reverse()
    out = [[float(a[0]), float(a[1]), float(a[2])]]
    for v in chain[1:]:
        u, i = prev[v]
        P = A[u]["pts"]
        mid = (P[i] + P[(i + 1) % len(P)]) / 2
        out.append([float(mid[0]), float(mid[1]), float(mid[2])])
    out.append([float(b[0]), float(b[1]), float(b[2])])
    return out


def walls(mp, p, r=TOUCH, dz=48.0):
    """The border segments touching p (its floor): [(direction of the wall in degrees 0-180, distance)]."""
    N = load(mp)
    if not N:
        return None
    S = N["segs"]
    if not len(S):
        return []
    near = S[(np.abs(S[:, 4] - p[2]) <= dz) & (np.minimum(S[:, 0], S[:, 2]) - r <= p[0]) & (np.maximum(S[:, 0], S[:, 2]) + r >= p[0])
             & (np.minimum(S[:, 1], S[:, 3]) - r <= p[1]) & (np.maximum(S[:, 1], S[:, 3]) + r >= p[1])]
    out = []
    for x1, y1, x2, y2, _, _ in near:
        d = _dist_seg(p, (x1, y1), (x2, y2))
        if d <= r and math.hypot(x2 - x1, y2 - y1) > 1:
            out.append((round(math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180, 1), round(d, 1)))
    return out


def corner(mp, p, r=TOUCH):
    """Whether p is a corner a player locks into: two walls touching it, not parallel. -> {corner, walls, angle, near}
    near: the distance to the nearest corner of the mesh's border (a spot a few units off one still counts as found again
    once you know it). None: no mesh for the map."""
    W = walls(mp, p, r)
    if W is None:
        return None
    angle = 0.0
    for i in range(len(W)):
        for j in range(i + 1, len(W)):
            a = abs(W[i][0] - W[j][0])
            angle = max(angle, min(a, 180 - a))
    return {"corner": angle >= CORNER, "walls": W, "angle": round(angle, 1), "against": bool(W)}


def corner_points(mp, p, r=48.0, dz=48.0):
    """The mesh's corners near p on its floor, the nearest first: where two of its border edges meet at 45 degrees or
    more (a player's centre pressed into the corner of two walls stands there). Each one a spot to probe on the server
    (tools/spot_probe.py): a pro's throw a few units off a corner is the same throw from the corner."""
    N = load(mp)
    if not N or not len(N["segs"]):
        return []
    S = N["segs"]
    S = S[np.abs(S[:, 4] - p[2]) <= dz]
    ends = []   # (x, y, z, direction of its edge)
    for x1, y1, x2, y2, z, _ in S:
        a = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
        for x, y in ((x1, y1), (x2, y2)):
            if math.hypot(x - p[0], y - p[1]) <= r:
                ends.append((x, y, z, a))
    out = []
    for i, (x, y, z, a) in enumerate(ends):
        for j in range(i + 1, len(ends)):
            x2, y2, _, b = ends[j]
            d = abs(a - b)
            if math.hypot(x - x2, y - y2) <= 2.0 and min(d, 180 - d) >= 45:
                q = [round(x, 1), round(y, 1), round(z, 1)]
                if all(math.dist(q[:2], o[:2]) > 8 for o in out):
                    out.append(q)
    out.sort(key=lambda q: math.hypot(q[0] - p[0], q[1] - p[1]))
    return out
