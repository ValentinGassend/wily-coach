"""The player's own CS2 driven for a real test (22/10, the user: "lancer pour de vrai mon jeu sur mon ordi, interagir pour
de vrai avec le jeu et faire les vrais tests en temps réel ... sans que j'aie à toucher ni le clavier ni la souris ...
que tu puisses record"): the game started with its console on a local port (-netconport, -insecure: no VAC, no
official match meanwhile), each command sent there as a bind would send it; what it printed read back from that port
or its console log (-condebug); its window captured (a picture, or a video with ffmpeg) to look at what the player sees.

The player moves as a player moves (22/10, the user: "je veux pas que tu déplaces mon joueur en téléportation ... avec les
touches de déplacement classiques, de saut ... en accroupi, en courant ... pour mesurer le temps que un joueur moyen met
à aller à ces endroits-là"): forward held, the view turned toward the next point of the map's mesh between here and
there (wily/training/navmesh.py), walked (Shift) the last steps, stopped on the spot; a jump when it is stuck. The view
turns with setang, as a mouse would (the training server's sv_cheats on for it); the position never jumps.

    python tools/real_client.py cmd "<console command>"     one command to the game, and what it printed
    python tools/real_client.py pos                           where the player stands and looks
    python tools/real_client.py walk <map> x,y,z              walked there, its time
    python tools/real_client.py shot <file.png>               the game's window, now

Nothing reaches the keyboard or the mouse of the PC: the commands go to the game's own console."""
import ctypes
import ctypes.wintypes
import heapq
import math

import numpy as np
import os
import re
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

PORT = int(os.environ.get("CS2_NETCON", 2121))
CONSOLE = os.path.join("E:" + os.sep, "SteamLibrary", "steamapps", "common", "Counter-Strike Global Offensive", "game", "csgo", "console.log")
PLUGIN_LOGS = os.path.join("E:" + os.sep, "CS2Server", "game", "csgo", "addons", "counterstrikesharp", "logs")
FFMPEG = "ffmpeg"
_S = None


# ---------------------------------------------------------------- the game's console

def _sock():
    global _S
    if _S is None:
        _S = socket.create_connection(("127.0.0.1", PORT), timeout=5)
        _S.settimeout(0.02)
    return _S


def _drain():
    """What the console printed so far, thrown away, without waiting (22/10 eve: a 20 ms wait after each command kept
    the walking loop at 10 a second, the player ran 25 u between two looks)."""
    s_ = _sock()
    try:
        s_.setblocking(False)
        while True:
            try:
                if not s_.recv(65536):
                    break
            except (BlockingIOError, OSError):
                break
    finally:
        try:
            s_.settimeout(0.02)
        except OSError:
            pass


def send(*cmds, gap=0.0):
    """Console commands to the game, in order (gap: seconds between two of them)."""
    global _S
    for c in cmds:
        for _ in range(2):
            try:
                _sock().sendall((c + "\n").encode("utf-8"))
                break
            except OSError:
                _S = None
        if gap:
            time.sleep(gap)
    _drain()


def ask(cmd, wait=0.25, until=None):
    """A command and what the game printed for it (the port streams the whole console: read a moment, or until a
    regular expression matches)."""
    _drain()
    send_raw = (cmd + "\n").encode("utf-8")
    _sock().sendall(send_raw)
    out, t0 = "", time.time()
    while time.time() - t0 < wait:
        try:
            b = _sock().recv(65536)
            if b:
                out += b.decode("utf-8", "replace")
                if until and re.search(until, out):
                    break
        except OSError:
            time.sleep(0.005)
    return out


EYE = 64.0   # getpos gives the eyes (standing): the feet are this far under them (26/10: the server's own eyes, me_eye
# in bots_live.json, are getpos's to 0.4 u, 63.6 u over the feet it was put on; 58 put every foot 6 u high)

POS_RE = r"setpos (-?[\d.]+) (-?[\d.]+) (-?[\d.]+);\s*setang (-?[\d.]+) (-?[\d.]+)"


_MARK = [0]




def rejoin(server="127.0.0.1:27015", wait=45.0):
    """Back on the training server when his game dropped off it (27/10 23:25: NETWORK_DISCONNECT_OVERFLOW as a drill's
    round restarted, his client in its menu, the driver walking 30 s on (0, 0, -64), the session lost): his console's
    last "Disconnected from server" after its last joined one -> connect, till a real place is read again.
    -> True when it rejoined, False when it was on the server (or could not tell)."""
    try:
        sz = os.path.getsize(CONSOLE)
        with open(CONSOLE, "rb") as f:
            f.seek(max(0, sz - 400000))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return False
    out_at = tail.rfind("Disconnected from server")
    in_at = tail.rfind("CGameClientConnectPrerequisite connection succeeded")
    if out_at < 0 or out_at < in_at:
        return False
    for _ in range(2):
        send(f"connect {server}")
        t0 = time.time()
        while time.time() - t0 < wait:
            time.sleep(2.0)
            p = getpos()
            if p and (abs(p[0]) > 1 or abs(p[1]) > 1):
                time.sleep(3.0)   # spawned and placed
                return True
    return False

def livepos():
    """(x, y, z, pitch, yaw) of the player as the training server last wrote it (bots_live.json: its eyes and its view), no
    console round trip (getpos: up to 0.5 s); getpos when the server has nothing."""
    foes()
    e, a = LIVE.get("me_eye"), LIVE.get("me_ang")
    if e and a and len(e) >= 3 and len(a) >= 2:
        return (float(e[0]), float(e[1]), float(e[2]), float(a[0]), float(a[1]))
    return getpos()


def getpos():
    """(x, y, z, pitch, yaw) of the player now, or None: the answer to this very question, a marker echoed after it (an
    answer still on its way from the question before is never taken: 22/10, the user: "tu tournes trop vite par rapport à
    ce que tu enregistres ... à chaque fois que tu enregistres, c'est un poil trop tard")."""
    _MARK[0] += 1
    m = f"__wp{_MARK[0]}__"
    out = ask(f"getpos;echo {m}", wait=0.5, until=rf"(?m)^{m}")
    i = out.rfind(m)
    found = list(re.finditer(POS_RE, out[:i])) if i >= 0 else []
    return tuple(float(v) for v in found[-1].groups()) if found else None


def cheats():
    """The training server's sv_cheats on (setang, getpos; the plugin turns it off after each "from their side" replay
    of a grenade: sv_rethrow_last_grenade needs it)."""
    try:
        from wily.training import replay
        replay.rcon("sv_cheats 1")
    except Exception as e:
        print("sv_cheats:", e, flush=True)


# ---------------------------------------------------------------- moving as a player moves

_NB = {}


def _graph(mp):
    from wily.training import navmesh
    if mp not in _NB:
        N = navmesh.load(mp)
        A = N["areas"]
        nb = {aid: {x for e in ar["edges"] for x in e if x in A} for aid, ar in A.items()}
        # a link a jump is needed for: the floor on the other side of the edge more than a step (18 u) above the edge
        # itself (a low wall, a crate, a ledge: 22/10 eve, the user: "tu avais encore un petit bout d'un muret ... tu as
        # avancé sur le muret"), up to a crouched jump's 66 u; higher: no way up there
        jump, rise = {}, {}
        for aid, ar in A.items():
            P = ar["pts"]
            for i, conn in enumerate(ar["edges"]):
                p, q = P[i], P[(i + 1) % len(P)]
                mid = (p + q) / 2
                for v in conn:
                    if v in A:
                        up = navmesh._plane_z(A[v]["pts"], mid[0], mid[1]) - mid[2]
                        rise[(aid, v)] = up
                        if up > 18:
                            jump[(aid, v)] = up
        _NB[mp] = (N, nb, {aid: ar["pts"].mean(axis=0) for aid, ar in A.items()}, jump, rise)
    return _NB[mp]


def _area(mp, p):
    """The floor area a point is on (a spot pressed into its corner is a little off the mesh: the nearest floor of it)."""
    from wily.training import navmesh
    N = _graph(mp)[0]
    ar = navmesh._area_at(N, p)
    if ar is None:
        q = navmesh.nearest(mp, p, r=80.0, dz=64.0)
        ar = navmesh._area_at(N, q) if q else None
    return ar


def navmesh_z(mp, p, r=24.0):
    """The floor's height under or over a point (the mesh's, r u around it, 40 u up or down), a huge number when none."""
    from wily.training import navmesh
    q = navmesh.nearest(mp, p, r=r, dz=40.0)
    return float(q[2]) if q else 1e9


def route_areas(mp, a, b):
    """The mesh's way from a to b: (points, areas, rises): areas[k] the floor area crossed k-th, points[k] the middle of
    the edge out of it (the last point b itself, in b's area), rises[k] how much higher the floor is past that edge (a
    jump over 18 u). A low wall or a crate is gone round when round is not much longer (a jump costs 600 u of walking);
    above a crouched jump (66 u) is no way. ([b], [], [0]) when a or b is off the mesh."""
    N, nb, cen, jump, rise = _graph(mp)
    sa, sb = _area(mp, a), _area(mp, b)
    if not sa or not sb:
        return [list(b)], [], [0.0]
    s, t = sa["id"], sb["id"]

    def dist(u, v):
        up = jump.get((u, v), 0.0)
        return None if up > 66 else math.dist(cen[u][:3], cen[v][:3]) + (600.0 if up else 0.0)
    best, prev, q = {s: 0.0}, {}, [(0.0, s)]
    while q:
        f, u = heapq.heappop(q)
        if u == t:
            break
        for v in nb[u]:
            d = dist(u, v)
            if d is None:
                continue
            g = best[u] + d
            if g < best.get(v, 1e18):
                best[v], prev[v] = g, u
                heapq.heappush(q, (g + math.dist(cen[v][:3], cen[t][:3]), v))
    if t not in prev and s != t:
        return [list(b)], [], [0.0]
    route = [t]
    while route[-1] != s:
        route.append(prev[route[-1]])
    route.reverse()
    A = N["areas"]
    pts, ups = [], []
    for u, v in zip(route, route[1:]):
        P, seg = A[u]["pts"], None
        for i, conn in enumerate(A[u]["edges"]):
            if v in conn:
                seg = (P[i], P[(i + 1) % len(P)])
                break
        mid = (seg[0] + seg[1]) / 2 if seg is not None else cen[v]
        pts.append([float(x) for x in mid] + ([[float(x) for x in seg[0]], [float(x) for x in seg[1]]] if seg is not None else []))
        ups.append(float(rise.get((u, v), 0.0)))
    return pts + [list(b)], route, ups + [0.0]


def _portal(w, a, b, inset=16.0):
    """Where a walk from a to b goes through the edge w (its middle, then its two ends): where the straight line crosses
    it, else its end nearest that line, inset from the walls (22/10 eve: the middle of a long edge took the player 110 u
    aside and back)."""
    if len(w) < 5:
        return w[:3]
    p, q = np.array(w[3][:2]), np.array(w[4][:2])
    L = float(np.linalg.norm(q - p))
    if L < 2 * inset + 1:
        return w[:3]
    u = (q - p) / L
    p2, q2 = p + u * inset, q - u * inset
    A, B = np.array(a[:2], float), np.array(b[:2], float)
    d, e = B - A, q2 - p2
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) > 1e-6:
        t = ((p2[0] - A[0]) * e[1] - (p2[1] - A[1]) * e[0]) / den
        r = ((p2[0] - A[0]) * d[1] - (p2[1] - A[1]) * d[0]) / den
        if 0 <= r <= 1 and t >= 0:
            x = p2 + r * e
            return [float(x[0]), float(x[1]), w[2]]
    n = np.array([-d[1], d[0]]) / (float(np.linalg.norm(d)) or 1.0)
    end = p2 if abs(float((p2 - A) @ n)) < abs(float((q2 - A) @ n)) else q2
    return [float(end[0]), float(end[1]), w[2]]


def path(mp, a, b):
    """The mesh's way from a to b: the middle of each edge it crosses, then b."""
    return route_areas(mp, a, b)[0]


def clear(mp, a, b, dz=60.0):
    """No wall of the mesh (an edge opening onto nothing) between a and b on their floor: a straight run is possible."""
    N = _graph(mp)[0]
    S = N["segs"]
    if not len(S):
        return True
    z = min(a[2], b[2])
    k = (S[:, 4] > z - dz) & (S[:, 4] < max(a[2], b[2]) + dz)
    k &= (np.minimum(S[:, 0], S[:, 2]) <= max(a[0], b[0])) & (np.maximum(S[:, 0], S[:, 2]) >= min(a[0], b[0]))
    k &= (np.minimum(S[:, 1], S[:, 3]) <= max(a[1], b[1])) & (np.maximum(S[:, 1], S[:, 3]) >= min(a[1], b[1]))
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    for x1, y1, x2, y2, _, _ in S[k]:
        d1 = (bx - ax) * (y1 - ay) - (by - ay) * (x1 - ax)
        d2 = (bx - ax) * (y2 - ay) - (by - ay) * (x2 - ax)
        d3 = (x2 - x1) * (ay - y1) - (y2 - y1) * (ax - x1)
        d4 = (x2 - x1) * (by - y1) - (y2 - y1) * (bx - x1)
        if d1 * d2 < 0 and d3 * d4 < 0:
            return False
    return True


def clear_to(mp, a, goal, short=24.0):
    """clear() to 24 u short of goal: a spot pressed into its corner is past the mesh's own edge there (22/10 eve: the
    smoke to Arch's spot, the last steps never taken, thrown 27 u off it into the wall)."""
    d = math.hypot(goal[0] - a[0], goal[1] - a[1])
    if d <= short:
        return True
    k = (d - short) / d
    return clear(mp, a, [a[0] + (goal[0] - a[0]) * k, a[1] + (goal[1] - a[1]) * k, goal[2]], dz=30.0)


def _ang(a):
    return (a + 180) % 360 - 180


def look(pitch, yaw, secs=0.6):
    """The view turned there as a hand turns a mouse (22/10 eve, the user: "le moment où tu déplaces ton curseur, c'est
    beaucoup trop violent"): fast at first, slower and slower onto it (an ease-out over secs), the last tenth of a degree
    in small steps, then still."""
    p0 = getpos()
    if not p0:
        send(f"setang {pitch} {yaw} 0")
        return
    n = max(4, int(secs / 0.025))
    dp, dy = pitch - p0[3], _ang(yaw - p0[4])
    for k in range(1, n + 1):
        f = 1 - (1 - k / n) ** 3
        send(f"setang {p0[3] + dp * f:.3f} {p0[4] + dy * f:.3f} 0")
        time.sleep(secs / n)
    send(f"setang {pitch} {yaw} 0")
    time.sleep(0.05)


def lock_corner(mp, spot, secs=0.3):
    """Into its corner (22/10 eve, the user: "chaque spot est censé être un endroit dans lequel tu peux te bloquer dans un
    coin, c'est-à-dire que tu peux avancer sans bouger, en regardant une certaine direction"): turned to where its walls
    are (the mesh's edges within 40 u of it, the nearest the most), walked into them a moment, Shift held: the walls stop
    the player on it. -> (moved u, off u from the spot after), or None (no wall by it)."""
    N = _graph(mp)[0]
    S = N["segs"]
    k = np.abs(S[:, 4] - spot[2]) < 40
    vx = vy = 0.0
    for x1, y1, x2, y2, z, aid in S[k]:
        a, b = np.array([x1, y1]), np.array([x2, y2])
        d = b - a
        t = max(0.0, min(1.0, float((np.array(spot[:2]) - a) @ d) / (float(d @ d) or 1.0)))
        q = a + t * d
        r = math.hypot(q[0] - spot[0], q[1] - spot[1])
        if r < 40:
            w = 1.0 / max(r, 2.0)
            vx += w * (q[0] - spot[0]) / max(r, 1e-6)
            vy += w * (q[1] - spot[1]) / max(r, 1e-6)
    if math.hypot(vx, vy) < 1e-6:
        return None
    p0 = getpos()
    if not p0:
        return None
    yaw = math.degrees(math.atan2(vy, vx))
    look(0.0, yaw, secs=0.3)
    send("+speed", "+forward")
    time.sleep(secs)
    send("-forward")
    time.sleep(0.25)
    send("-speed")
    p1 = getpos()
    if not p1:
        return None
    return round(math.hypot(p1[0] - p0[0], p1[1] - p0[1]), 1), round(math.hypot(p1[0] - spot[0], p1[1] - spot[1]), 1)


def crouch_jump():
    """A jump, crouched in the air at once (the feet up: a low wall's edge, a crate), the crouch let go once landed."""
    send("+jump")
    time.sleep(0.05)
    send("+duck")
    time.sleep(0.05)
    send("-jump")
    return time.time()


MOVES = os.path.join("E:" + os.sep, "CS2Server", "game", "csgo", "coach", "moves")
JUMP, DUCK = 2, 4   # the game's buttons


def his_route(mp, a, b, near=150.0):
    """A way he walked himself (!rec on the training server, coach/moves/<map>_*.jsonl) from near a to near b:
    [(x, y, z, jump?, duck delay in ticks)] every quarter second and at each of his jumps, or None."""
    import glob
    import json
    best = None
    for f in glob.glob(os.path.join(MOVES, f"{mp}_*.jsonl")):
        try:
            rows = [json.loads(l) for l in open(f, encoding="utf-8")]
        except (OSError, ValueError):
            continue
        far = lambda r, q: math.dist(r["p"][:2], q[:2]) + 3 * abs(r["p"][2] - q[2])   # the same floor first (a ledge above is far)
        da = [far(r, a) for r in rows]
        db = [far(r, b) for r in rows]
        if not rows:
            continue
        i = min(range(len(rows)), key=lambda k: da[k])
        j = min(range(len(rows)), key=lambda k: db[k])
        if da[i] <= near and db[j] <= near and j != i and (best is None or da[i] + db[j] < best[0]):
            # forward as he went; backward (down his ledges: walked off, no jumps) when the goal is before
            seg = rows[i:j + 1] if j > i else [dict(r, b=r["b"] & ~(JUMP | DUCK)) for r in reversed(rows[j:i + 1])]
            best = (da[i] + db[j], seg)
    if not best:
        return None
    rows, out = best[1], []
    for k, r in enumerate(rows):
        jump = bool(r["b"] & JUMP) and not (k and rows[k - 1]["b"] & JUMP)
        if jump:
            dk = next((m - k for m in range(k, min(len(rows), k + 40)) if rows[m]["b"] & DUCK), None)
            out.append((r["p"][0], r["p"][1], r["p"][2], True, dk))
        elif k % 16 == 0:
            out.append((r["p"][0], r["p"][1], r["p"][2], False, None))
    return out


def follow_route(route, tol=12.0, timeout=25.0):
    """His way followed: run to each point, his jumps where he jumped them, crouched as many ticks after as he did."""
    t0, jumps = time.time(), 0
    send("+forward")
    for x, y, z, jump, dk in route:
        while time.time() - t0 < timeout:
            p = getpos()
            if not p:
                continue
            d = math.hypot(x - p[0], y - p[1])
            if d <= (16.0 if jump else tol + 20.0):
                break
            want = math.degrees(math.atan2(y - p[1], x - p[0]))
            send(f"setang 0 {want:.2f} 0")
            time.sleep(0.02)
        if jump:
            send("+jump")
            if dk is not None:
                time.sleep(max(0.0, dk / 64.0))
                send("+duck")
            time.sleep(0.05)
            send("-jump")
            jumps += 1
            time.sleep(0.35)
            send("-duck")
    send("-forward")
    return jumps


def _hop(up):
    """Up onto what is in front: a jump, crouched in the air from a low wall's height (22/10: "un saut into
    accroupissement en l'air qu'il fallait faire pour passer le petit rebord du muret")."""
    if up > 30:
        return crouch_jump()
    send("+jump")
    time.sleep(0.06)
    send("-jump")
    return time.time()


G, VZ, ACC = 800.0, 301.99, 5.5   # CS2: gravity, a jump's speed up, sv_accelerate


def air_time(h, crouch=False):
    """Seconds from a jump's takeoff till its feet come down to h u above it (a crouch in the air lifts the feet 9 u:
    a 64 u crate), None when it never gets that high."""
    h = h - (9.0 if crouch else 0.0)
    disc = VZ * VZ - 2 * G * h
    if disc < 0 and h <= VZ * VZ / (2 * G) + 8:   # at the very top of what a jump reaches (26/10, Train's T Upper: 62-66 u
        return VZ / G * 1.15                      # up, the base's players made it): just past the jump's top
    return None if disc < 0 else (VZ + disc ** 0.5) / G


def duck_on_takeoff(z0, timeout=0.25):
    """The crouch in the air the moment the feet leave the ground (27/10, Ancient's A Site: 62-66 u climbs, a crouch-jump's
    whole height, short every time; a duck sent 50 ms after the jump reaches his unfocused game 0.1-0.4 s late, past the
    top of the jump): positions read till it rises 3 u, then +duck (50 ms at least after +jump: same frame, no lift)."""
    t0 = time.time()
    time.sleep(0.03)
    while time.time() - t0 < timeout:
        q = getpos()
        if q and q[2] > z0 + 3:
            break
    send("+duck")


def climb_to(p_to, timeout=1.5):
    """Up onto a ledge right in front (26/10, Boulder's T Mid: 52-60 u up for 12-60 u ahead, a crouch-jump's whole
    height; a run-up fell off the step it stood on, or met the face before the feet were over its edge): turned to it,
    walked into it till its face stops you (or right under its point), then a crouch-jump with W held: the feet slide
    onto it once they are over the edge. -> the feet where it landed, or None."""
    p = getpos()
    if not p:
        return None
    yaw = math.degrees(math.atan2(p_to[1] - p[1], p_to[0] - p[0]))
    look(0.0, yaw, secs=0.15)
    if abs(_ang(yaw - p[4])) > 10:
        wait_view(yaw)
    send("+speed", "+forward")
    t0 = time.time()
    last = (t0, p[:2])
    cur, t_turn = yaw, t0
    while time.time() - t0 < timeout:
        q = getpos()
        if not q:
            continue
        dq = math.hypot(p_to[0] - q[0], p_to[1] - q[1])
        if dq < 18:
            break
        now = time.time()
        if now - last[0] > 0.12:
            # against its face, once it walks (27/10 19:08: his W comes 0.1-0.4 s late, "stopped" read before it moved,
            # the climb jumped from 20-40 u off)
            if math.dist(last[1], q[:2]) < 2 and (math.dist(p[:2], q[:2]) > 3 or now - t0 > 0.5):
                break
            last = (now, q[:2])
        # kept turned to it (27/10 19:08, Overpass, Mirage, Train: walked along a face 50-220 u past its point)
        want = math.degrees(math.atan2(p_to[1] - q[1], p_to[0] - q[0]))
        if dq > 24 and abs(_ang(want - cur)) > 20 and now - t_turn > VIEW_LAG:
            send(f"setang 0 {want:.2f} 0")
            cur, t_turn = want, now
        time.sleep(0.01)
    send("+jump")
    time.sleep(0.05)   # off the ground first: a duck in the same frame as the jump loses its lift (his game unfocused draws
    send("+duck")      # a frame in 20 ms; 26/10, Train's A Site: 4 climbs in 5 stayed on the floor with 20 ms; 27/10 17:08: a
    time.sleep(0.4)    # duck sent once the takeoff was read came later, Nuke's climbs short: back to 50 ms)
    send("-forward")   # on top: W let go, not walked off its far side (26/10, Back of B: 50-80 u past it)
    time.sleep(0.3)
    send("-jump", "-duck", "-forward", "-speed")
    brake(0.35, slow=20.0)   # stopped there for sure (27/10, Anubis's B Main: a W let go late walked it 400 u off)
    q = getpos()
    return (q[0], q[1], q[2] - EYE) if q else None


def step_to(pt, tol=6.0, timeout=1.2):
    """A few steps straight on what it stands on (a box's top: no mesh there), walked (Shift), stopped on it."""
    t0 = time.time()
    held = False
    while time.time() - t0 < timeout:
        p = getpos()
        if not p:
            continue
        d = math.hypot(pt[0] - p[0], pt[1] - p[1])
        if d <= tol:
            break
        want = math.degrees(math.atan2(pt[1] - p[1], pt[0] - p[0]))
        if held and d < tol + 24:   # the last steps in taps, each one stopped for sure (27/10: a W let go late ran it
            send("-forward")        # 66 u past its point, off a box's top)
            held = False
            brake(0.3, slow=15.0)
            continue
        if not held and d < tol + 24:
            if abs(_ang(want - p[4])) > 3:   # turned first, the view given time to take (27/10 17:10, Nuke's Roof: a tap sent
                send(f"setang 0 {want:.2f} 0")   # right after the setang went the old way, 54 u forward for a run-up back)
                time.sleep(VIEW_LAG)
            send("+speed", "+forward")
            time.sleep(0.05 if d < tol + 10 else 0.09)
            send("-forward")
            brake(0.3, slow=15.0)
            continue
        send(f"setang 0 {want:.2f} 0")
        if not held:
            send("+speed", "+forward")
            held = True
        time.sleep(0.01)
    send("-forward", "-speed")
    brake(0.3, slow=15.0)   # stopped there for sure (27/10: a W let go late ran it 66 u past, off a box's top)
    p = getpos()
    return (p[0], p[1], p[2] - EYE) if p else None


def run_jump(takeoff, p_to, speed=240.0, crouch=False, timeout=2.5):
    """A jump as the base's players make it (26/10, their records: 63 u up at 230 u/s after 60-150 u of run-up, hardly
    ever from a standstill): a run from where you stand straight at its takeoff (Shift under 140 u/s, their speed),
    the jump the moment it is reached (a frame early, for the console's delay), turned to where it lands, crouched in
    the air when asked, W held through the air and let go as it comes down. -> the feet where it landed, or None."""
    p = getpos()
    if not p:
        return None
    walk = speed < 140
    v = 130.0 if walk else 250.0
    yaw = math.degrees(math.atan2(takeoff[1] - p[1], takeoff[0] - p[0]))
    look(0.0, yaw, secs=0.12)
    ux, uy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    if walk:   # Shift down before W (27/10, his Fachwerk window jump: both in one send, "entendu" 4 times in 4)
        send("+speed")
        time.sleep(0.06)
    send("+forward")
    t0 = time.time()
    while time.time() - t0 < timeout:
        q = getpos()
        if not q:
            continue
        rem = (takeoff[0] - q[0]) * ux + (takeoff[1] - q[1]) * uy   # how far its takeoff still is, along the run
        if rem <= 4 + v * 0.03:
            break
        if math.hypot(takeoff[0] - q[0], takeoff[1] - q[1]) > 30:   # steered at it (not right over it: no spin)
            send(f"setang 0 {math.degrees(math.atan2(takeoff[1] - q[1], takeoff[0] - q[0])):.2f} 0")
        time.sleep(0.005)
    q = getpos() or p
    send(f"setang 0 {math.degrees(math.atan2(p_to[1] - q[1], p_to[0] - q[0])):.2f} 0", "+jump")
    if crouch:
        time.sleep(0.05)
        send("+duck")
    time.sleep(0.5)
    send("-forward")
    time.sleep(0.25)
    send("-jump", "-duck", "-forward", "-speed")
    time.sleep(0.15)
    brake(0.35, slow=20.0)   # down by now (0.9 s): stopped on it for sure (27/10: a W let go late ran it off small tops)
    q = getpos()
    return (q[0], q[1], q[2] - EYE) if q else None


def climbs(p_from, p_to):
    """A jump that is a climb up a ledge in front (much higher, little further): climb_to's, not a run's."""
    # 26/10, Train's lab: walked 50-80 u at a face it slid along it off the box, or ran past a ledge with no face: a climb
    # only when the ledge is right there
    return p_to[2] - p_from[2] >= 30 and math.hypot(p_to[0] - p_from[0], p_to[1] - p_from[1]) <= 15


def wait_view(yaw, tol=4.0, timeout=0.6):
    """Till the game's view is turned to yaw (28/10 16:46, Nuke's Outside: a chain's first jump 46 deg off its line 4 times
    in 5, made once with the same aim: VIEW_LAG's fixed 0.2 s not always enough): its yaw read again, `timeout` s at most.
    -> True when it is within tol."""
    t0 = time.time()
    time.sleep(0.05)
    while time.time() - t0 < timeout:
        q = getpos()
        if q and abs(_ang(yaw - q[4])) <= tol:
            return True
        time.sleep(0.03)
    return False


def jump_to(p_from, p_to, timeout=3.0):
    """One jump of a chain as a player makes it (23/10): turned to where it lands, the speed it needs (its length over
    its time in the air: a run, a walk, or nearly none) taken where it stands, then the jump, crouched in the air when it
    climbs more than 40 u, W let go once down (26/10, Train's lab: the run-up's step back fell off the box it stood on;
    the speed now comes forward from a standstill, sv_accelerate x the walk or run speed a second). -> the feet where
    it landed, or None."""
    here = getpos()   # from where it stands now, not where the last jump was read (26/10: still sliding, 38 deg off)
    if here:
        p_from = (here[0], here[1], here[2] - EYE)
    h = p_to[2] - p_from[2]
    crouch = h > 40
    t_air = air_time(h, crouch) or air_time(h, True)
    if t_air is None:
        return None
    d = math.hypot(p_to[0] - p_from[0], p_to[1] - p_from[1])
    v = d / t_air * (1.08 if h > 40 else 1.0)   # a high ledge: a hair past its point (26/10, T Upper: 2-15 u short, on the
    yaw = math.degrees(math.atan2(p_to[1] - p_from[1], p_to[0] - p_from[0]))   # lower lip under it)
    look(0.0, yaw, secs=0.15)
    if here and abs(_ang(yaw - here[4])) > 10:   # its view there before W (27/10 20:05, Train's Back of B: a chain's 2nd
        wait_view(yaw)                           # jump 93 deg from the 1st, off 40 deg between the two, 45-60 u past it)
    walk = v <= 120
    t_acc = 0.0 if v < 20 else min(v, 250.0) / (ACC * (130.0 if walk else 250.0))
    send(*(["+speed"] if walk else []), "+forward")
    time.sleep(t_acc)
    send("+jump")
    if crouch:
        time.sleep(0.05)   # off the ground first (see climb_to)
        send("+duck")
    time.sleep(max(0.12, t_air * 0.6 - (0.05 if crouch else 0.0)))
    if v < 40:
        send("-forward")
    # W held till it is down: its push over a ledge's edge when the body meets its face (27/10 17:08, Nuke's Outside: let go
    # before the landing, 0 of 4 where the lab had 4 of 4: it slid along the face), then stopped there for sure (Anubis's
    # B Main: W held on walked it 49 u off the small box)
    time.sleep(max(0.05, t_air * 0.4) + 0.05)
    send("-jump", "-duck", "-forward", "-speed")
    brake(0.35, slow=20.0)
    p = getpos()
    return (p[0], p[1], p[2] - EYE) if p else None


# ---------------------------------------------------------------- the floor around a jump (tools/jump_probe.py)

GEO_DIR = os.path.join(HERE, "out", "realtest", "jump_geo")
_GEO = {}


def _geo(mp):
    """The map's traced floor around its jumps: [(point, {(i, j): floor z, or "x" in a solid, or None})], one per
    landing or takeoff point of a jump (i, j its 4 u steps from the point)."""
    if mp in _GEO:
        return _GEO[mp]
    out = []
    try:
        import json
        b = json.load(open(os.path.join(GEO_DIR, f"{mp}.json"), encoding="utf-8"))
        st = float(b.get("step") or 4)
        for j in (b.get("jumps") or {}).values():
            for p, cells in zip(j["pts"], j["grid"]):
                g = {}
                for x, y, z in cells:
                    g[(round((x - p[0]) / st), round((y - p[1]) / st))] = z
                out.append((p, g, st))
    except (OSError, ValueError, KeyError):
        out = []
    _GEO[mp] = out
    return out


def top_of(mp, P, near=24.0):
    """The traced floor around a jump's point (the one traced nearest it, within 24 u): (its point, grid, step), or
    None."""
    best = None
    for p, g, st in _geo(mp):
        d = math.dist(p[:3], P[:3])
        if d <= near and (best is None or d < best[0]):
            best = (d, p, g, st)
    return best[1:] if best else None


def top_aim(mp, P, frm=None, margin=8.0, deep=False):
    """Where to land on a jump's point's top (27/10, the real-client lab: the base's landing points are their jumpers'
    feet, often past a crate's edge, the body on it, the point over the void; the driver came down right under them,
    50-63 u below): the spot nearest the point whose floor is the point's (-8..+10 u) all round it for `margin` u, on
    the side it is jumped from when two are as near. -> (x, y, z) or None when its floor was not traced."""
    t = top_of(mp, P)
    if not t:
        return None
    p, g, st = t
    top = {k for k, z in g.items() if isinstance(z, float) and -8.0 <= z - P[2] <= 10.0}
    if not top:
        return None
    ox, oy = (P[0] - p[0]) / st, (P[1] - p[1]) / st   # the point in the grid's steps (the traced one may be a few u off)

    def cost(k):
        c = math.hypot(k[0] - ox, k[1] - oy)
        if frm is not None:   # a hair nearer the side it comes from
            c += 0.15 * math.hypot(p[0] + k[0] * st - frm[0], p[1] + k[1] * st - frm[1]) / st
        return c
    def no_drop(q):   # the way there from frm on its floor or onto the top, never over a lower floor (27/10, Train's A
        # site: its spot 24 u off the base's point across a gap, walked into the gap)
        if frm is None:
            return True
        x1, y1 = p[0] + q[0] * st, p[1] + q[1] * st
        L = math.hypot(x1 - frm[0], y1 - frm[1])
        for j in range(1, int(L // 4) + 1):
            x, y = frm[0] + (x1 - frm[0]) * j * 4 / L, frm[1] + (y1 - frm[1]) * j * 4 / L
            z = g.get((round((x - p[0]) / st), round((y - p[1]) / st)))
            if isinstance(z, float) and z < frm[2] - 18 and not (-8.0 <= z - P[2] <= 10.0):
                return False
        return True
    # the nearest of its spots in from the edge, near the base's point first (27/10, Train's A site: a climb aimed 24 u
    # aside slid along the face off its start's ledge): 16 u from it at most, then 28, then anywhere on its top;
    # the way there never over a lower floor; else the best one as before
    k, first = None, None
    pools = {}
    # deep: in from the edge before near the point (27/10 20:19, Boulder's A Site: a crate set at 45 deg, its corner aimed
    # 9 u off the point, slid along its face 5 times in 5; a jump that failed is aimed so its next rep)
    tiers = (((margin, 16), (margin, 28), (margin / 2, 16), (margin / 2, 28), (0.0, 16), (0.0, 1e9)) if deep
             else ((margin, 16), (margin / 2, 16), (0.0, 16), (margin, 28), (margin / 2, 28), (0.0, 1e9)))
    for mg_, far in tiers:
        m = max(0, int(round(mg_ / st)))
        if m not in pools:
            pools[m] = sorted((q for q in top if all((q[0] + a, q[1] + b) in top for a in range(-m, m + 1) for b in range(-m, m + 1))), key=cost)
        for c in pools[m][:60]:
            if math.hypot(c[0] - ox, c[1] - oy) * st > far:
                break
            if first is None:
                first = c
            if no_drop(c):
                k = c
                break
        if k is not None:
            break
    k = k or first
    if k is None:
        return None
    zs = sorted(g[q] for q in top if abs(q[0] - k[0]) <= 2 and abs(q[1] - k[1]) <= 2)
    return (p[0] + k[0] * st, p[1] + k[1] * st, zs[len(zs) // 2] if zs else P[2])


def climb_aim(mp, P0, frm):
    """Where a climb up to a jump's point aims: the base's point when its top is within 16 u of it and the way there from
    `frm`, on 24 u past it, comes onto that top (their way up: Dust2's mid door, aimed aside it slid along the face),
    else the top's own spot nearest it (27/10 19:08, Vertigo's A Ramp: its 2nd point 12 u off the top, over the box it
    is climbed from, the way to it along the face: climbed 4 times in 5 into the void beside it, 70 u down).
    -> [x, y, z]"""
    t0 = top_aim(mp, P0, frm, margin=0.0)
    if t0 is None or frm is None:
        return list(P0)
    if math.dist(t0[:2], P0[:2]) > 16:
        return list(t0)
    p, g, st = top_of(mp, P0)
    L = math.hypot(P0[0] - frm[0], P0[1] - frm[1])
    if L < 1:
        return list(t0)
    ux, uy = (P0[0] - frm[0]) / L, (P0[1] - frm[1]) / L
    for k in range(0, int((L + 24) // 2) + 1):
        x, y = frm[0] + ux * 2 * k, frm[1] + uy * 2 * k
        z = g.get((round((x - p[0]) / st), round((y - p[1]) / st)))
        if isinstance(z, float) and -8.0 <= z - P0[2] <= 10.0:
            return list(P0)
    # straight into its face: the top's spot nearest where it stands, 24 u of the point at most, 4 u in (27/10 20:04,
    # Train's A Site: aimed 30 deg off the face, it slid along it off the ledge it stood on, 0 of 5)
    best = None
    for (i, j), z in g.items():
        if not (isinstance(z, float) and -8.0 <= z - P0[2] <= 10.0):
            continue
        x, y = p[0] + i * st, p[1] + j * st
        if math.hypot(x - P0[0], y - P0[1]) > 24:
            continue
        d = math.hypot(x - frm[0], y - frm[1])
        if best is None or d < best[0]:
            best = (d, x, y, z)
    if best is None:
        return list(t0)
    d, x, y, z = best
    if d > 1:
        x, y = x + (x - frm[0]) / d * 4, y + (y - frm[1]) / d * 4
    return [x, y, z]


def face_aim(mp, P0, frm, inset=8.0, near=40.0):
    """A jump onto a top straight at its nearest edge: the top's spot nearest where it stands (40 u of the point at
    most), `inset` u past it the way it comes (28/10 00:45, Boulder's A Site: a crate set at 45 deg, aimed at its corner
    from 50 u off, it slid along its face 6 times in 6, 45-50 deg off). -> [x, y, z] or None (no top traced)."""
    t = top_of(mp, P0)
    if not t or frm is None:
        return None
    p, g, st = t
    best = None
    for (i, j), z in g.items():
        if not (isinstance(z, float) and -8.0 <= z - P0[2] <= 10.0):
            continue
        x, y = p[0] + i * st, p[1] + j * st
        if math.hypot(x - P0[0], y - P0[1]) > near:
            continue
        d = math.hypot(x - frm[0], y - frm[1])
        if best is None or d < best[0]:
            best = (d, x, y, z)
    if best is None:
        return None
    d, x, y, z = best
    if d > 1:
        x, y = x + (x - frm[0]) / d * inset, y + (y - frm[1]) / d * inset
    return [x, y, z]


def face_dist(mp, P, frm, aim):
    """How far its top's edge is from `frm`, along the way from `frm` to `aim` (walked back from `aim` 2 u at a time
    till the floor is no longer the top's): u, or None when the edge is not in the traced grid."""
    t = top_of(mp, P)
    if not t:
        return None
    p, g, st = t
    L = math.hypot(aim[0] - frm[0], aim[1] - frm[1])
    if L < 1:
        return 0.0
    ux, uy = (frm[0] - aim[0]) / L, (frm[1] - aim[1]) / L
    s = 0.0
    while s <= L:
        x, y = aim[0] + ux * s, aim[1] + uy * s
        z = g.get((round((x - p[0]) / st), round((y - p[1]) / st)), "out")
        if z == "out":
            return None
        if not (isinstance(z, float) and -8.0 <= z - P[2] <= 10.0):
            return max(0.0, L - s)
        s += 2.0
    return 0.0


_LINES = {}


def _lines(mp):
    """The map's traced floor along each jump's line: [(from, to, [(s along it, floor - from's z, or None)])], its
    middle line only (tools/jump_probe.py: 24 u before its takeoff to 24 u past its landing)."""
    if mp in _LINES:
        return _LINES[mp]
    out = []
    try:
        import json
        b = json.load(open(os.path.join(GEO_DIR, f"{mp}.json"), encoding="utf-8"))
        for j in (b.get("jumps") or {}).values():
            pts = j["pts"]
            for k in range(1, len(pts)):
                a, c = pts[k - 1], pts[k]
                L = math.hypot(c[0] - a[0], c[1] - a[1]) or 1.0
                ux, uy = (c[0] - a[0]) / L, (c[1] - a[1]) / L
                prof = []
                for x, y, z in (j["line"][k] or [])[1::3]:   # the middle one of each three
                    s = (x - a[0]) * ux + (y - a[1]) * uy
                    prof.append((s, (z - a[2]) if isinstance(z, float) else None))
                out.append((a, c, prof))
    except (OSError, ValueError, KeyError, IndexError):
        out = []
    _LINES[mp] = out
    return out


def takeoff_edge(mp, F, P, near=24.0):
    """How far along the jump's line from F its takeoff's floor goes on before the gap (27/10, his Fachwerk jumps: the
    green ring is where he started, the crate's or the wall's edge 4-45 u further; jumped at the ring they all fell
    short, from the edge each is a 250 u/s jump): u, or None when its line was not traced."""
    best = None
    for a, c, prof in _lines(mp):
        d = math.dist(a[:3], F[:3]) + math.dist(c[:3], P[:3])
        if d <= 2 * near and (best is None or d < best[0]):
            best = (d, prof)
    if not best:
        return None
    last, prev = None, None
    for s, z in sorted(best[1]):
        if s < -1:
            continue
        # the floor gone (a drop, a rise: more than a step from the spot before; a ramp or stairs go on): its edge is the
        # last spot before (27/10, his Fachwerk anti-push: its start on a slope, 15 u over the floor at its ring)
        if z is None or (prev is not None and abs(z - prev) > 12) or (prev is None and abs(z) > 24):
            if z is not None and prev is not None and z > prev:   # a rise: the landing's own face, no gap to take off at
                return None
            break
        last, prev = s, z
    return last


def room_behind(mp, F, P, most=48.0):
    """How far back from F, away from P, its floor goes on (the traced grid around F: 48 u at most): u."""
    t = top_of(mp, F)
    if not t:
        return 0.0
    p, g, st = t
    L = math.hypot(P[0] - F[0], P[1] - F[1]) or 1.0
    ux, uy = (F[0] - P[0]) / L, (F[1] - P[1]) / L
    s, prev = 0.0, g.get((round((F[0] - p[0]) / st), round((F[1] - p[1]) / st)))
    if not isinstance(prev, float):
        return 0.0
    while s + 4 <= most:
        x, y = F[0] + ux * (s + 4), F[1] + uy * (s + 4)
        z = g.get((round((x - p[0]) / st), round((y - p[1]) / st)), "out")
        if not (isinstance(z, float) and abs(z - prev) <= 10):   # a step at most from the spot before (stairs go on)
            break
        s, prev = s + 4, z
    return s


_MOJ = {}


def up_chain(mp, goal):
    """A spot up on crates the mesh does not reach (27/10, Anubis's exec A flash on Canals' crates, 80 u over the floor:
    24-36 s round and round under it): one of the map's Momentum chains (the base's jumps up there, out/train_momentum)
    whose landing steps come by it -> [its start, its steps up to the one by the spot], or None."""
    if mp not in _MOJ:
        try:
            import json
            _MOJ[mp] = json.load(open(os.path.join(HERE, "out", "train_momentum", f"{mp}.json"), encoding="utf-8")).get("jumps") or []
        except (OSError, ValueError):
            _MOJ[mp] = []
    best = None
    for j in _MOJ[mp]:
        pts = [j["from"]] + list(j.get("marks") or []) + [j["to"]]
        for k in range(1, len(pts)):
            q = pts[k]
            d = math.hypot(q[0] - goal[0], q[1] - goal[1])
            if d < 64 and abs(q[2] - goal[2]) < 24 and (best is None or d < best[0]):
                best = (d, [list(p[:3]) for p in pts[:k + 1]])
    return best[1] if best else None


def climb_up(mp, goal):
    """Up onto a spot on crates by a Momentum chain of the map (up_chain): walked to its start, each step climbed or
    jumped (climb_to right under it, jump_to else). -> True when up there (by the spot's height)."""
    ch = up_chain(mp, goal)
    if not ch:
        return False
    walk_to(mp, ch[0], tol=12.0, timeout=12.0)
    for q in ch[1:]:
        p = getpos()
        if not p:
            return False
        at = (p[0], p[1], p[2] - EYE)
        if q[2] - at[2] < 12:   # already this high (the walk got it there)
            continue
        A = top_aim(mp, q, at, margin=0.0)
        tgt = list(A) if A and math.dist(A[:2], q[:2]) > 16 else list(q)
        if math.hypot(tgt[0] - at[0], tgt[1] - at[1]) <= 30:
            climb_to(tgt)
        else:
            jump_to(at, tgt)
    p = getpos()
    return bool(p) and abs(p[2] - EYE - goal[2]) < 30


OPP = {"forward": "back", "back": "forward", "left": "right", "right": "left"}   # CS2's own strafe keys


def brake(timeout=0.35, slow=30.0):
    """Stopped for sure (27/10: a W let go reaches his unfocused game 0.1-0.4 s late, now and then later still: Inferno's
    situations shot on the run, its B molotov's spot run past and back 50 u for 10 s): while two positions 50 ms apart
    still show it moving, every movement key let go again and the one against its motion tapped. -> its speed then."""
    t0, sp = time.time(), 0.0
    a, ta = getpos(), time.time()
    while time.time() - t0 < timeout:
        time.sleep(0.05)
        b, tb = getpos(), time.time()
        if not (a and b) or tb - ta < 0.02:
            a, ta = b, tb
            continue
        vx, vy = (b[0] - a[0]) / (tb - ta), (b[1] - a[1]) / (tb - ta)
        sp = math.hypot(vx, vy)
        if sp < slow:
            return sp
        # every movement key let go again, no tap against it (27/10 18:15, Cache's Heaven: a tap's "-back" reaching the game
        # late walked it 150 u back off its crate, its next jump backwards): the floor's friction stops it (215 to 60 u/s
        # in a quarter second)
        send("-forward", "-back", "-left", "-right")
        a, ta = getpos(), time.time()
    return sp


def halt(held):
    """Stopped (CS2 shoots true only standing still): each movement key let go, then checked stopped (brake: a key let go
    can reach his game late; no counter-strafe tap, its own let-go late as well)."""
    # let go only (27/10 18:15: the opposite key's tap let go late walked it the other way), then stopped for sure
    send(*["-" + k for k in held], "-forward", "-back", "-left", "-right")
    held.clear()
    brake()


# the night's straight-at-it fallbacks in walk_to: OFF (27/10 08:06: with them Dust2's CT defense A smoke took 18-23 s
# where round 2 took 4.5 s, the walker fell off its ledge; Mirage's exec A 0/6). COACH_DIRECT=1 to try them again.
WALK_DIRECT = bool(os.environ.get("COACH_DIRECT"))


def _direct(goal, timeout=6.0):
    """Straight at a spot close by, hopped up onto it when its face stops the feet (a crate's top the mesh only reaches
    by a long way round: 26/10, Mirage's A Ramp jumpthrow smoke, 150 u off and 21 u up, an 800 u detour and 41 s of
    failed hops). -> True when on it."""
    t0, last, hops, walking = time.time(), (time.time(), None), 0, False
    send("-speed", "+forward")
    try:
        while time.time() - t0 < timeout:
            p = getpos()
            if not p:
                continue
            x, y, fz = p[0], p[1], p[2] - EYE
            d = math.hypot(goal[0] - x, goal[1] - y)
            if d < 26 and abs(fz - goal[2]) < 16:
                return True
            if d < 40 and goal[2] - fz > 12:   # right under it (a crate's top): climbed, not run past (27/10, Mirage's A
                # Ramp smoke: run under its crate and past it, then lost 450 u off)
                send("-forward", "-speed")
                q = climb_to(goal)
                if q and math.hypot(goal[0] - q[0], goal[1] - q[1]) < 26 and abs(q[2] - goal[2]) < 16:
                    return True
                hops += 1
                if hops >= 3:
                    return False
                send("+forward")
                continue
            send(f"setang 0 {math.degrees(math.atan2(goal[1] - y, goal[0] - x)):.2f} 0")
            if (d < 120) != walking:
                walking = d < 120
                send("+speed" if walking else "-speed")
            if time.time() - last[0] > 0.3:
                if last[1] is not None and math.dist(last[1], (x, y)) < 5:   # its face in the way
                    if goal[2] - fz <= 12 or hops >= 4:
                        return False
                    _hop(goal[2] - fz)
                    hops += 1
                last = (time.time(), (x, y))
            time.sleep(0.01)
        return False
    finally:
        send("-forward", "-speed", "-duck", "-jump")


def _walks_to(mp, p, goal):
    """The mesh has a walk from where you stand to the floor area of goal (its last area that one)."""
    try:
        ga = _area(mp, goal)
        if ga is None:
            return False
        _, areas, ups = route_areas(mp, (p[0], p[1], p[2] - EYE), goal)
        return bool(areas) and areas[-1] == ga["id"] and max(ups or [0.0]) <= 66
    except Exception:
        return False


def walk_to(mp, goal, tol=5.0, timeout=30.0, walk_from=160.0, trace=None, stop=None, face=None, through=False, then=None,
            times=None, t_go=None, settle_from=72.0, _detour=False):
    """Walked to goal with the movement keys as a player walks there (22/10 eve, the user: "tu avances plus vite que tu ne
    tournes ... tu tournes, mais c'est déjà trop tard ... tu reviens en arrière ... tu sautes par-dessus ... en boucle";
    "entre le point et toi, tu avais encore un petit bout d'un muret ... tu as avancé sur le muret ... tu étais décalé à
    gauche alors que toi, tu pensais que tu étais sur le point"): along the mesh's way area after area (where it stands
    says which edge is next, never a point "passed" on the far side of a wall), round a low wall unless a jump saves a
    lot; turned on the spot when the next edge is far off the view, forward once it is ahead; Shift from walk_from
    units; the last steps straight only from inside the goal's own floor area, never from on top of something; positions
    read fresh. face: a callable giving a point to keep the view on while it goes (an angle, a head: 23/10, the user:
    "déplacement parfait, aim parfaite"), strafed its way then (forward, back, left, right as the way lies from the view);
    stop: a callable on the feet, stopped dead there (counter-strafed) once it holds. through: a point on the way, not a
    spot: run at full speed and on as soon as it is within tol (26/10, Boulder's situations: Shift from 160 u of each of
    his points, 200 u apart, walked the whole way, 16 of his 43 points in 29 s). then: more such points after it, run
    one after the other without a stop (27/10, the user: "tu as encore des gros problèmes sur les déplacements ... le seul
    relativement correct, c'est la partie stuff. Mais quand on est sur du jeu de situation, on doit suivre des
    directions": his way in a situation walked by this walker, his own floor points); times (with t_go): his time at
    each of them, waited for there when it is early.
    -> {"secs", "off", "dz", "jumps", "path", "his", "replans", "gi": how many of the points it got to}."""
    t0 = time.time()
    p = getpos()
    if not p:
        return {"secs": None, "off": None, "dz": None, "jumps": 0, "path": [], "his": False, "replans": 0}
    pre = 0
    # a spot up on crates higher than a crouch jump (60 u over the feet or more), a Momentum chain of the map landing by
    # it (the mesh may have the crates' tops, not a way up there): that chain first (27/10 19:20, Mirage's exec A: its
    # smokes' boxes 45 and 55 u up, climbed right under them this morning, sent at 40 u to a chain 400 u off, 1/7)
    # (only where no walk gets there: 30/10, Anubis's exec A, its flash 116 u up on Mid's floor, a jump chain 14 s where
    # the stairs take 5)
    if not through and stop is None and then is None and goal[2] - (p[2] - EYE) > 60 and not _walks_to(mp, p, goal) and up_chain(mp, goal):
        pre += 1 if climb_up(mp, goal) else 0
        p = getpos() or p
    route = his_route(mp, (p[0], p[1], p[2] - EYE), goal)
    if route:   # his own way (22/10: "au moins tu passes le jump compliqué"), the mesh's for the rest
        pre = follow_route(route, timeout=timeout)
        p = getpos() or p
    ga = _area(mp, goal)
    near_goal = set()
    if ga is not None:
        nbs = _graph(mp)[1]
        near_goal = {v for v in nbs.get(ga["id"], ()) if abs(_graph(mp)[4].get((ga["id"], v), 0.0)) < 8}
    pts, areas, ups = route_areas(mp, (p[0], p[1], p[2] - EYE), goal)
    pts0 = list(pts)   # its first way, for a detour (the taps stuck against something)
    k, jumps, walking, hop, replans = 0, 0, False, 0.0, 0
    # close by in a straight line, far round by the mesh, a climb a jump makes: straight at it and up
    straight = math.hypot(goal[0] - p[0], goal[1] - p[1])
    length = sum(math.dist(a[:2], b[:2]) for a, b in zip([p[:2]] + [q[:2] for q in pts], [q[:2] for q in pts]))
    direct = (WALK_DIRECT and not route and stop is None and face is None and straight < 220 and length > 2.5 * straight + 150
              and -20 < goal[2] - (p[2] - EYE) < 66 and _direct(goal))
    held = set()
    last = (time.time(), p[:2])
    unface = 0.0   # till when the view is let go of its point (stuck strafing: a plain walk, its hops)
    climbed = 0.0
    near_since, best_d = None, 1e9   # close by and no nearer for a while: straight at it (27/10, Cache's B molotov: round
    # and round 45-50 u off its spot for 7-11 s, its corner off the mesh's areas)
    chained = then is not None   # a chain (his way): each of its points on a budget
    then = list(then or [])
    gi = 0
    # a chain's point given up when it takes much longer than a run there (27/10, Fachwerk's R2: 113 s and 112 hops on
    # its first point, the whole drill gone): 3 s more than at 150 u/s
    goal_t0, goal_budget = time.time(), 3.0 + math.hypot(goal[0] - p[0], goal[1] - p[1]) / 150.0
    send("-forward", "-back", "-left", "-right", "-speed", "-duck", "-jump")
    while not direct and time.time() - t0 < timeout:
        p = getpos()
        if not p:
            continue
        x, y, fz = p[0], p[1], p[2] - EYE
        d_goal = math.hypot(goal[0] - x, goal[1] - y)
        if chained and time.time() - goal_t0 > goal_budget:   # this point given up: the caller goes on past it
            halt(held)
            send("-speed")
            return {"secs": round(time.time() - t0, 2), "off": round(d_goal, 1), "dz": round(fz - goal[2], 1), "jumps": jumps + pre,
                    "his": bool(route), "replans": replans, "gave_up": True, "path": [], "gi": gi}
        if stop is not None and stop((x, y, fz)):   # far enough (a target in sight): stopped dead there
            halt(held)
            send("-speed")
            return {"secs": round(time.time() - t0, 2), "off": round(d_goal, 1), "dz": round(fz - goal[2], 1), "jumps": jumps + pre,
                    "his": bool(route), "replans": replans, "stopped": True, "path": [[round(v) for v in w[:2]] for w in pts], "gi": gi}
        here = _area(mp, (x, y, fz))
        # by it on its own floor: its area or one next to it on the same level (a spot pressed into its corner has a
        # sliver of an area), and no wall of the mesh across the straight line left
        inside = ga is None or (here is not None and (here["id"] == ga["id"] or (here["id"] in near_goal and abs(fz - goal[2]) < 10)))
        if through and d_goal < tol and abs(fz - goal[2]) < 40 and then:   # on to the next one, keys held
            gi += 1
            if times and t_go is not None and gi - 1 < len(times) and time.time() - t_go < times[gi - 1] - 0.5:
                halt(held)   # there before him: waited for his time there, an eye out
                walking = False
                send("-speed")
                while time.time() - t_go < times[gi - 1] - 0.5:
                    q = getpos()
                    if q and stop is not None and stop((q[0], q[1], q[2] - EYE)):
                        return {"secs": round(time.time() - t0, 2), "off": 0.0, "dz": 0.0, "jumps": jumps + pre, "his": bool(route),
                                "replans": replans, "stopped": True, "path": [], "gi": gi}
                    time.sleep(0.05)
            goal = then.pop(0)
            goal_t0, goal_budget = time.time(), 3.0 + math.hypot(goal[0] - x, goal[1] - y) / 150.0
            ga = _area(mp, goal)
            near_goal = set()
            if ga is not None:
                nbs = _graph(mp)[1]
                near_goal = {v for v in nbs.get(ga["id"], ()) if abs(_graph(mp)[4].get((ga["id"], v), 0.0)) < 8}
            pts, areas, ups = route_areas(mp, (x, y, fz), goal)
            k, last = 0, (time.time(), (x, y))
            continue
        if through and d_goal < tol and abs(fz - goal[2]) < 40:
            gi += 1
            send(*["-" + kk for kk in held], "-speed")
            return {"secs": round(time.time() - t0, 2), "off": round(d_goal, 1), "dz": round(fz - goal[2], 1), "jumps": jumps + pre,
                    "his": bool(route), "replans": replans, "through": True, "path": [[round(v) for v in w[:2]] for w in pts], "gi": gi}
        if not through and stop is None and 18 < goal[2] - fz < 66 and d_goal < 96 and time.time() - climbed > 1.5:
            # (96 u: 27/10, Mirage's A Ramp smoke 45 u up on its ledge, the walker round and round 70-500 u off it 50 s)
            # its spot up on a crate the mesh does not reach (27/10, Cache's B molotov: 36 u up, 14 u off it, round and
            # round under it for 20 s): a crouch-jump into it, W held (climb_to), then on as before
            send(*["-" + kk for kk in held], "-speed")
            held.clear()
            walking = False
            climb_to(goal)
            climbed = time.time()
            jumps += 1
            continue
        if inside and d_goal < 26 and abs(fz - goal[2]) < 16 and clear_to(mp, (x, y, fz), goal):
            break   # the last steps straight
        if not through and stop is None and d_goal < settle_from and abs(fz - goal[2]) < 16 and clear(mp, (x, y, fz), goal, dz=30.0):
            # close by in the open: the last steps in turned pulses (27/10, Inferno's B defense smoke: round and round its
            # spot 50 u off for 10-15 s, the view taking the turns 0.2 s late)
            break
        if WALK_DIRECT and 26 < d_goal < 70 and stop is None and not through:   # (27/10: from 5 u off it ran 36 u past: not that close)
            if d_goal < best_d - 4:
                best_d, near_since = d_goal, time.time()
            elif near_since is not None and time.time() - near_since > 1.5 and abs(fz - goal[2]) < 40:
                send(*["-" + kk for kk in held], "-speed")
                held.clear()
                if _direct(goal, timeout=3.0):
                    break
                near_since, best_d = time.time(), d_goal
        if here is not None and areas:
            if here["id"] in areas[k:]:
                k = areas.index(here["id"], k)
            elif here["id"] not in areas and time.time() - hop > 0.8 and replans < 6:   # off the way (on a wall, round a
                # corner): the way again from here
                pts, areas, ups = route_areas(mp, (x, y, fz), goal)
                k, replans = 0, replans + 1
        k = min(k, len(pts) - 1)
        nxt = pts[k + 1][:3] if k + 1 < len(pts) else pts[k][:3]
        w = _portal(pts[k], (x, y), nxt)
        if math.hypot(w[0] - x, w[1] - y) < 10 and k < len(pts) - 1:   # on the edge itself: aim past it
            w = nxt
        # a sharp turn at that edge (round a low wall's end): walked into it, so as not to run past it
        sharp = k < len(pts) - 1 and abs(_ang(math.degrees(math.atan2(nxt[1] - w[1], nxt[0] - w[0])) - math.degrees(math.atan2(w[1] - y, w[0] - x)))) > 70             and math.hypot(w[0] - x, w[1] - y) < 70
        want = math.degrees(math.atan2(w[1] - y, w[0] - x))
        if trace is not None and (not trace or time.time() - t0 - trace[-1][0] > 0.25):
            trace.append((round(time.time() - t0, 1), round(x), round(y), round(fz), k, [round(v) for v in w[:3]], round(d_goal)))
        tgt = face((x, y, fz)) if face is not None and time.time() > unface else None
        if tgt is not None:   # the view on its point, the feet strafed along the way
            vy = math.degrees(math.atan2(tgt[1] - y, tgt[0] - x))
            vp = -math.degrees(math.atan2(tgt[2] - p[2], math.hypot(tgt[0] - x, tgt[1] - y)))
            send(f"setang {vp:.2f} {vy:.2f} 0")
            rel = _ang(want - vy)
            keys = {kk for kk, on in (("forward", abs(rel) < 67.5), ("back", abs(rel) > 112.5),
                                       ("left", 22.5 < rel < 157.5), ("right", -157.5 < rel < -22.5)) if on}
            for kk in OPP:
                if kk in keys and kk not in held:
                    send("+" + kk)
                    held.add(kk)
                elif kk not in keys and kk in held:
                    send("-" + kk)
                    held.discard(kk)
            turn = 0.0
        else:
            for kk in list(held - {"forward"}):   # back to a plain walk: the strafes let go
                send("-" + kk)
                held.discard(kk)
            turn = _ang(want - p[4])
            # far off the view: stopped, turned on the spot first (a hand turning, 40 degrees a step); on a way run
            # through (his situations) only a turn back (27/10: stops at each corner, 9.5 s for his 6.5)
            if abs(turn) > (100 if through else 60):
                if "forward" in held:
                    send("-forward")
                    held.discard("forward")
                send(f"setang 0 {p[4] + max(-40.0, min(40.0, turn)):.2f} 0")
                time.sleep(0.03)
                continue
            if abs(turn) > 1.5:
                send(f"setang 0 {p[4] + max(-20.0, min(20.0, turn)):.2f} 0")
            if "forward" not in held:
                send("+forward")
                held.add("forward")
        slow = not through and (d_goal < walk_from or abs(turn) > 30 or sharp)   # a way run through: run on, round corners too
        if slow != walking:
            send("+speed" if slow else "-speed")
            walking = slow
        up = ups[min(k, len(ups) - 1)]
        if up > 18 and math.hypot(pts[k][0] - x, pts[k][1] - y) < 50 and time.time() - hop > 0.8 and abs(turn) < 25:   # its way's own climbs, strafing too
            hop = _hop(up)
            jumps += 1
        if time.time() - last[0] > (1.5 if face is not None and time.time() > unface else 0.7):   # no way forward for 0.7 s:
            # a jump (crouched in the air every other time), then the way again from here; strafing with the view held, never
            # a jump (23/10, the user: "tu sautes en boucle parce que t'as un ennemi qui te fait peur"): the way again, and
            # the view let go 1.5 s, walked the plain way (26/10, Boulder's A Main prefire: 60 s against a corner strafing)
            if math.dist(last[1], (x, y)) < 6 and face is not None and time.time() > unface:
                if replans < 6:
                    pts, areas, ups = route_areas(mp, (x, y, fz), goal)
                    k, replans = 0, replans + 1
                unface = time.time() + 1.5
            elif math.dist(last[1], (x, y)) < 6:
                hop = _hop(40 if jumps % 2 else 20)
                jumps += 1
                if jumps % 3 == 0 and replans < 6:
                    pts, areas, ups = route_areas(mp, (x, y, fz), goal)
                    k, replans = 0, replans + 1
            last = (time.time(), (x, y))
        if time.time() - hop > 0.5:
            send("-duck")
        time.sleep(0.01)
    send(*["-" + kk for kk in held], "-speed")
    held.clear()
    brake(0.4, slow=15.0)   # stopped by it first (27/10: a W let go late ran it past its spot)
    best_tap, flat_taps, stuck = 1e9, 0, False
    for _ in range(12):   # onto it: short walked taps, straight inside its area
        p = getpos()
        if not p:
            break
        d = math.hypot(goal[0] - p[0], goal[1] - p[1])
        if d <= tol:
            break
        # three taps without a step nearer: against something the mesh does not have (30/10, Train's exec A smokes: come in
        # 50 u east of the base's way, 38 u off the spot behind a post, still for 23 s, the smokes gone before the flash)
        if d > best_tap - 1.5:
            flat_taps += 1
            if flat_taps >= 3:
                stuck = True
                break
        else:
            best_tap, flat_taps = d, 0
        if d > 80 or not clear_to(mp, (p[0], p[1], p[2] - EYE), goal):   # not by it, or a wall in between: no taps
            break   # through it (the caller walks again)
        if p[2] - EYE > goal[2] + 12:   # up on something: off it first, back the way it came
            send("+back")
            time.sleep(0.2)
            send("-back")
            time.sleep(0.25)
            continue
        want = math.degrees(math.atan2(goal[1] - p[1], goal[0] - p[0]))
        if abs(_ang(want - p[4])) > 3:   # turned first, the view given time to take (a tap right after a setang goes the old way)
            send(f"setang 0 {want:.2f} 0")
            time.sleep(VIEW_LAG)
        send("+speed", "+forward")
        time.sleep(0.04 if d < 10 else 0.07 if d < 20 else min(0.35, d / 200.0))   # a pulse for the way left
        send("-forward")
        time.sleep(0.08)
        brake(0.3, slow=15.0)   # its tap a tap (27/10: let go late, 50 u past and back again)
    send("-speed", "-forward", "-back")
    p = getpos()
    if stuck and not _detour and p:
        # out to a point of its first way 60-220 u off the spot, the earliest, then in again along the way from there
        back = [q for q in pts0[:-1] if 60 < math.hypot(q[0] - goal[0], q[1] - goal[1]) < 220]
        if back:
            walk_to(mp, list(back[0][:3]), tol=12.0, timeout=5.0, walk_from=walk_from, _detour=True)
            w2 = walk_to(mp, goal, tol=tol, timeout=max(4.0, timeout - (time.time() - t0)), walk_from=walk_from,
                         settle_from=settle_from, _detour=True)
            return dict(w2, secs=round(time.time() - t0, 2), jumps=(w2.get("jumps") or 0) + jumps + pre, detour=True)
    off = math.hypot(goal[0] - p[0], goal[1] - p[1]) if p else None
    return {"secs": round(time.time() - t0, 2), "off": round(off, 1) if off is not None else None,
            "dz": round(p[2] - EYE - goal[2], 1) if p else None, "jumps": jumps + pre, "his": bool(route), "replans": replans,
            "path": [[round(v) for v in w[:2]] for w in pts]}


def ladders(route):
    """His way's ladders (27/10, his order: "les éléments particuliers des cartes comme échelle sur Nuke"; Nuke's hut:
    z -364 to -118 at one spot): runs of points that rise 30 u or more each while moving less than 20 u -> [(start,
    end)], start the last point at the ladder's foot, end the first one at its top."""
    out, k, n = [], 1, len(route)
    flat = lambda k: math.hypot(route[k][0] - route[k - 1][0], route[k][1] - route[k - 1][1])
    while k < n:
        # 30 u a point (Nuke's hut), or 12 u a point standing still (27/10, Train's Back of B: 20 u a point, x and y
        # the same, never taken for one: 12 s under it)
        fast = route[k][2] - route[k - 1][2] >= 30 and flat(k) < 20
        if fast or (route[k][2] - route[k - 1][2] >= 12 and flat(k) < 8):
            a = k - 1
            while k < n and route[k][2] - route[k - 1][2] >= 8 and flat(k) < 24:
                k += 1
            # a ladder climbs on; a jump onto a crate rises a point or two (Nuke's crates: taken for ladders, W held into
            # them 6 s): the slow way 3 points of it at least
            if route[k - 1][2] - route[a][2] >= 70 and (fast or k - 1 - a >= 3):   # no jump climbs 70 u
                out.append((a, k - 1))
        k += 1
    return out


def climb_ladder(foot, top, face_yaw, after, timeout=6.0):
    """Up a ladder as a player climbs it: facing it, the view up, W held till the feet are at its top, then off it
    toward where his way goes next. -> the feet then, or None."""
    send(f"setang -70 {face_yaw:.2f} 0", "-speed", "+forward")
    t0 = time.time()
    try:
        while time.time() - t0 < timeout:
            p = getpos()
            if p and p[2] - EYE >= top[2] - 12:
                break
            time.sleep(0.02)
        p = getpos()
        if p:
            send(f"setang 0 {math.degrees(math.atan2(after[1] - p[1], after[0] - p[0])):.2f} 0")
        time.sleep(0.5)   # off it, onto the top
    finally:
        send("-forward")
    p = getpos()
    return (p[0], p[1], p[2] - EYE) if p else None


def _why(why, i, t0):
    """Where a pursue's time went, in the log (COACH_SHOTLOG): his points done, its hops, climbs, waits, detours."""
    if os.environ.get("COACH_SHOTLOG"):
        secs = time.time() - t0
        print(f"      pursue: his points {why['i0']}->{i} ({(i - why['i0']) * 0.25:.2f} s of his) in {secs:.2f} s · hops {why['hops']} · climbs {why['climbs']}"
              f" · waits {why['waits']:.1f} s · detours {why['detours']} · ladders {why['ladders']}", flush=True)


def pursue(route, i=0, stop=None, timeout=60.0, near=48.0, clock=None, keep=False, mp=None):
    """His own way run as he ran it (26/10, Train's and Boulder's situations: walked point to point on the mesh it went
    3 times slower than him, the fights over before it came): at full speed, the view along it, steered at each frame
    to his next point not reached yet (every quarter second of his), a hop when stuck; stopped dead the moment stop()
    holds; clock(): his point of now (26/10, Overpass: run flat out it came 4 s before the fight, nobody there yet),
    never more than 2 ahead of it, waited for there. -> {"i": his point reached, "stopped", "secs"}."""
    t0 = time.time()
    n = len(route)
    if not n:
        return {"i": 0, "stopped": False, "secs": 0.0}
    p = getpos()
    if p and i == 0:   # from the point of his nearest to where it was put (26/10: his first one 200 u off, behind a
        # wall: 40 s against it)
        i = min(range(max(1, n // 2)), key=lambda k: math.hypot(route[k][0] - p[0], route[k][1] - p[1]) + 3 * abs(route[k][2] - (p[2] - EYE)))
    send("-back", "-left", "-right", "-speed", "+forward")
    held = {"forward"}
    last, hopped = (time.time(), None), 0.0
    lads = [(a, b) for a, b in ladders(route) if b >= i]
    why = {"hops": 0, "climbs": 0, "waits": 0.0, "detours": 0, "ladders": 0, "i0": i}   # where its time goes (the log)
    try:
        while time.time() - t0 < timeout:
            # the server's word each step, not the console's (30/10, his order on the reaction: in a situation 1.6 s at the
            # median from their line opening to a fight, each step a getpos round trip; his route needs no unit's precision)
            p = livepos()
            if not p:
                continue
            x, y, fz = p[0], p[1], p[2] - EYE
            if stop is not None and stop((x, y, fz)):
                halt(held)
                held.clear()
                _why(why, i, t0)
                return {"i": i, "stopped": True, "secs": round(time.time() - t0, 2)}
            # a ladder of his way at hand: climbed as he climbed it
            lad = next(((a, b) for a, b in lads if a - 2 <= i <= a + 1 and math.hypot(route[a][0] - x, route[a][1] - y) < 60), None)
            if lad:
                a, b = lad
                pa = route[a - 1] if a else route[a]
                face = math.degrees(math.atan2(route[a][1] - pa[1], route[a][0] - pa[0])) if math.hypot(route[a][0] - pa[0], route[a][1] - pa[1]) > 2                     else math.degrees(math.atan2(route[a][1] - y, route[a][0] - x))
                after = route[min(n - 1, b + 1)]
                climb_ladder(route[a], route[b], face, after)
                why["ladders"] += 1
                lads.remove(lad)
                i = min(n - 1, b + 1)
                send("+forward")
                held.add("forward")
                last = (time.time(), None)
                continue
            # on past every point of his within reach, or one a later point is nearer than, never ahead of his clock
            cap = n - 1 if clock is None else max(0, min(n - 1, clock() + 2))
            # the height counts (27/10, Nuke's hut: his points on its roof right over the feet were taken as reached, its
            # ladder skipped, stuck under it)
            d3 = lambda q: math.hypot(q[0] - x, q[1] - y) + 2 * abs(q[2] - fz)
            while i < cap and not any(a - 2 <= i <= a for a, _ in lads) and (d3(route[i]) < near or d3(route[i + 1]) < d3(route[i])):
                i += 1
            while i < cap and any(a - 2 <= i < a for a, _ in lads) and d3(route[i]) < near:   # up to its ladder's foot
                i += 1
            if abs(route[i][2] - fz) > 60 and not any(a - 2 <= i <= b for a, b in lads):
                # off his way's level (fell further than where he jumped down): on from the next point of his at this
                # level (27/10, Nuke's hut: the mesh's way back to his point went 1200 u round), the mesh only when none
                j = next((k for k in range(i + 1, min(n, i + 48)) if abs(route[k][2] - fz) < 40), None)
                if j is not None:
                    i = j
                elif mp is not None:
                    send("-forward")
                    held.discard("forward")
                    why["detours"] += 1
                    walk_to(mp, route[i], tol=40.0, timeout=6.0)
                    send("+forward")
                    held.add("forward")
                    last = (time.time(), None)
                    continue
            # his way goes up right ahead (a crate he jumped onto: his next point higher, close): climbed now (27/10,
            # Anubis's R9: under it, his point beyond it mid-jump 34 u up, never "reached", back and forth 15 s)
            up_nx = route[min(n - 1, i + 1)]
            if (up_nx[2] - fz > 16 and math.hypot(up_nx[0] - x, up_nx[1] - y) < 64 and time.time() - hopped > 0.8
                    and not any(a - 2 <= i <= bb for a, bb in lads)):
                land = next((route[k] for k in range(i + 1, min(n - 1, i + 8))
                             if 16 < route[k][2] - fz < 66 and abs(route[k + 1][2] - route[k][2]) < 8), None)
                if land is not None:
                    climb_to(land)
                    why["climbs"] += 1
                    hopped = time.time()
                    send("+forward")
                    held.add("forward")
                    last = (time.time(), None)
                    i = route.index(land) if land in route else i
                    continue
            if i >= n - 1 and math.hypot(route[-1][0] - x, route[-1][1] - y) < near:
                break
            if i >= cap and cap < n - 1 and math.hypot(route[i][0] - x, route[i][1] - y) < near:
                if "forward" in held:   # ahead of him: waited for his time there
                    send("-forward")
                    held.discard("forward")
                time.sleep(0.02)
                why["waits"] += 0.02
                continue
            if "forward" not in held:
                send("+forward")
                held.add("forward")
            q = route[i]
            send(f"setang 0 {math.degrees(math.atan2(q[1] - y, q[0] - x)):.2f} 0")
            if time.time() - last[0] > 0.5:   # stuck: a hop (crouched every other time), on again
                if last[1] is not None and math.dist(last[1], (x, y)) < 8 and time.time() - hopped > 0.8:
                    up = max(route[k][2] for k in range(i, min(n, i + 4))) - fz
                    if up > 16:   # his way climbs there (27/10, Train's R4: 11 s against a ledge he jumped up, the hops
                        # too low): a crouch-jump into it, W held; at where he stood up there, not at a point of his in
                        # the air (27/10, Inferno's Apps: his point 34 u up was mid-jump, 10-15 s under it): the first of
                        # his next ones 16-66 u up whose next one is as high (on a floor)
                        land = next((route[k] for k in range(i, min(n - 1, i + 8))
                                     if 16 < route[k][2] - fz < 66 and abs(route[k + 1][2] - route[k][2]) < 8), None)
                        climb_to(land or route[min(n - 1, i + 1)])
                        why["climbs"] += 1
                        hopped = time.time()
                        send("+forward")
                    else:
                        why["hops"] += 1
                        hopped = _hop(40 if int(hopped) % 2 else 20)
                last = (time.time(), (x, y))
            time.sleep(0.01)
    finally:
        if not keep:
            send(*["-" + k for k in held], "-duck", "-jump")
    if keep:   # on again at the next call: W still held (27/10, Overpass: let go every 2 s, 4-8 s behind his clock)
        send("-duck", "-jump")
    _why(why, i, t0)
    return {"i": i, "stopped": False, "secs": round(time.time() - t0, 2)}


KEYS = {"left": ["attack"], "right": ["attack2"], "both": ["attack", "attack2"]}


def _click(words):
    w = (words or "").lower()
    return "both" if ("left + right" in w or "both" in w or "gauche + droit" in w) else "right" if "right" in w or "droit" in w else "left"


def press(click):
    keys = KEYS[_click(click)]
    send(*[f"+{k}" for k in keys])
    return keys


def release(how, keys):
    """The grenade let go its way: still, crouched, on the move (W), a jumpthrow let go as the jump starts (22/10 eve,
    the user on exec A's flash 5: "c'est clic gauche, clic droit, accroupi et jump throw accroupi. Toi, tu as juste jump
    throw et en plus le moment du lancer est pas bon ... tu lances quand tu es déjà en train de retomber"): the jump, the
    crouch a tick after (in the air it is instant: his !rec, duck 1.0 the tick he pressed it), let go a tick later: the
    grenade's speed up about 272 u/s from the jump, his own 272.7."""
    h = (how or "").lower()
    up = [f"-{k}" for k in keys]
    if "forward" in h or "run" in h:
        send("+forward")
        time.sleep(0.25)
    elif "walking" in h:
        send("+speed", "+forward")
        time.sleep(0.3)
    if "jump" in h:
        send("+jump")
        time.sleep(0.02)
        if "crouch" in h:
            send("+duck")
        time.sleep(0.018)
        send(*up)
        time.sleep(0.3)
        send("-jump")
        time.sleep(0.45)
    else:
        if "crouch" in h:
            send("+duck")
            time.sleep(0.35)
        send(*up)
    time.sleep(0.25)
    send("-forward", "-duck", "-speed")


BOTS_LIVE = os.path.join("E:" + os.sep, "CS2Server", "game", "csgo", "coach", "bots_live.json")


def foes():
    """The enemy bots alive as the plugin sees them now (coach/bots_live.json, 32 a second): [{slot, pos, eye, duck,
    seen}], seen = the game's own spotting of them by you."""
    import json
    try:
        with open(BOTS_LIVE, encoding="utf-8") as fh:
            B = json.load(fh)
    except (OSError, ValueError):
        return []
    LIVE.clear()
    LIVE.update(B)
    me = B.get("me_team")
    LIFE["alive"] = B.get("me_alive", True)
    sc = bool(B.get("me_scoped", False))
    if sc and not LIFE.get("scoped"):   # when its scope came up (scope_up: one up 0.35 s already is steady)
        LIFE["scoped_at"] = time.time()
    LIFE["scoped"] = sc
    out = [b for b in B.get("bots") or [] if me is not None and b.get("team") != me]
    t = B.get("t") or 0
    for b in out:
        b["t_read"] = t
    for b in out:   # its speed, from where it was a read ago (a running T is led, not shot behind)
        prev = _LAST.get(b["slot"])
        if isinstance(b.get("vel"), list):   # the server's own, now (02/11: the plugin's; two reads lagged a bot slowing)
            pass
        elif prev and 0 < t - prev[0] <= 32:
            dt = (t - prev[0]) / 64.0
            b["vel"] = [(b["pos"][i] - prev[1][i]) / dt for i in range(3)]
        elif prev and prev[0] == t:
            b["vel"] = prev[2]
        if prev is None or prev[0] != t:
            _LAST[b["slot"]] = (t, b["pos"], b.get("vel") or [0.0, 0.0, 0.0])
    return out


_LAST = {}


LIFE = {"alive": True}   # you alive, as the plugin last said
LIVE = {}   # bots_live.json as foes() last read it (26/10: your bullets' impacts and hits too)


def head_of(b, lead=0.0):
    """Where to put the crosshair on it: its head, its chest when only its chest is in a bullet's line (bots_live "los"),
    lead s ahead of it when it moves."""
    z = b.get("eye")
    if z is None:
        z = b["pos"][2] + 64 - 18 * (b.get("duck") or 0)
    v = b.get("vel") or [0.0, 0.0, 0.0]
    return [b["pos"][0] + v[0] * lead, b["pos"][1] + v[1] * lead, z - (22 if b.get("los") == "chest" else 2) + v[2] * lead]


# 27/10, the plugin's raw impacts (scratchpad angle_test.py): a shot sent 0-140 ms after a setang left along the view
# before it, though the server's eyes had the new one; from 150-200 ms on, along the new one (his unfocused game's
# subtick input): the view a bullet takes is about VIEW_LAG old. Every miss of the night after a flick, every moving
# one missed "0.45 s behind", the spray pull that looked "stronger early": that lag.
VIEW_LAG = 0.2
# a shotgun's lead, times LEAD (03/11: 1.5; 04/11, rounds 23-24: its misses on crossers then 45 ahead of them, 1 behind,
# 37 u at the median, at 1.0 27 behind and 12 ahead: the bots' strafes turn back, no lead fits; on still ones 10 hits of 10)
# 10/11: at 1.0 all 63 of its blasts at crossers (80+ u/s, rounds 23-26) went 7-38 u ahead of them, 21 u at the median, none
# behind (the plugin's impacts): its lead cut to under a third
PUMP_LEAD = 0.3
# an AWP's lead, times LEAD (10/11: at 1.0, 167 of its 197 shots at crossers in rounds 23-28 went ahead of them, 20 u at the
# median at 150-400 u, 18 behind; a single shot, its bolt after a miss: cut as the shotgun's was)
SNIPER_LEAD = 0.4
# a rifle's tap past 600 u, times LEAD (10/11: 309 of its 379 taps at crossers in rounds 23-28 went ahead of them, 17-20 u at
# the median with 23-26 u of lead, 7 to 11 % of them hit; its bursts closer were within 7 u, kept as they are)
FAR_LEAD = 0.3
SHOT_LAG = 0.13   # the settle before a shot only (30/10, his order: his 0.3 s, a first damage in 0.4-0.5 s; 0.2 held its first shot 0.36 s at the median)
PRESS_R8 = 0.33   # the R8's left click held till its hammer falls (29/10)


R8 = {"seen": False}   # the weapon_deagle in his hands seen with 8 rounds: an R8


def revolver():
    """The R8 in his hands (the plugin's own word for his weapon). The game names the R8 a weapon_deagle (its item 64): its
    8-round clip tells it apart, a Deagle holds 7 (03/11: 65 of 103 "deagle" shots never left, all with 8 rounds, clicked
    0.05 s where the R8's hammer needs its 0.33 s hold)."""
    w = str(LIVE.get("me_weapon") or "")
    if w == "weapon_revolver":
        return True
    if w != "weapon_deagle":
        R8["seen"] = False
        return False
    if (LIVE.get("me_clip") or 0) >= 8:
        R8["seen"] = True
    return R8["seen"]


SEMI = ("hkp2000", "usp_silencer", "glock", "p250", "fiveseven", "tec9", "deagle", "elite")


def semi_auto():
    """A pistol that fires once a click in his hands (the plugin's word for his weapon; the CZ75 and the R8 not)."""
    w = str(LIVE.get("me_weapon") or "")
    return any(w.endswith(k) for k in SEMI) and not revolver()
VIEW = {"moved": 0.0, "ang": None}
PUMP_AIM = [False]   # a pump shotgun in the hands in fight(): a turn of 8 u at its distance is a move (aim_at)   # when the view last turned more than a degree, and to what


def aim_at(h, p=None):
    """The crosshair on that point at once (23/10, the user: "aim parfaite") -> (pitch, yaw) sent, or None."""
    p = p or getpos()
    if not p:
        return None
    yaw = math.degrees(math.atan2(h[1] - p[1], h[0] - p[0]))
    pitch = -math.degrees(math.atan2(h[2] - p[2], math.hypot(h[0] - p[0], h[1] - p[1])))
    a = VIEW["ang"]
    # a turn of 8 u at its distance is a move (1 deg far off; 02/11, round 16, Ancient's MAG-7: tracking one at 150 u turned
    # the view over a degree each 10 ms, the settle at its 0.3 s cap before every blast, 0 kills, 6 deaths)
    # a shotgun's only (02/11 19:10: for every weapon, the rifles' K/D fell from 2.9 to 1.5 after 16:55, their shots taking a view
    # still turning)
    thr = max(1.0, math.degrees(math.atan2(8.0, max(1.0, math.dist(h[:3], p[:3]))))) if PUMP_AIM[0] else 1.0
    if a is None or abs(a[0] - pitch) > thr or abs((a[1] - yaw + 540) % 360 - 180) > thr:
        VIEW["moved"] = time.time()
    VIEW["ang"] = (pitch, yaw)
    send(f"setang {pitch:.3f} {yaw:.3f} 0")
    return pitch, yaw


def settle(point, p, cap=0.3):
    """Tracked with the view till it has been on it for VIEW_LAG (the view a shot takes is that old): point() each 10 ms
    (a moving one led by LEAD), at most cap s. -> the last point aimed at, or None when it is gone."""
    t0, h = time.time(), None
    while True:
        h = point()
        if h is None:
            return None
        aim_at(h, p)
        if time.time() - VIEW["moved"] >= SHOT_LAG or time.time() - t0 > cap:
            return h
        time.sleep(0.01)


def view_on(ang, tol=0.6, cap=0.06):
    """Till the server has your eyes at those angles (bots_live.json me_ang), cap s at most (26/10, the plugin's impacts:
    the first shot of a duel left 70-108 u wide, into the wall, the click before the view had moved) -> True when there."""
    import json
    t0 = time.time()
    while time.time() - t0 < cap:
        try:
            with open(BOTS_LIVE, encoding="utf-8") as fh:
                a = json.load(fh).get("me_ang")
        except (OSError, ValueError):
            a = None
        if a and abs(a[0] - ang[0]) < tol and abs((a[1] - ang[1] + 180) % 360 - 180) < tol:
            return True
        time.sleep(0.004)
    return False


# how much of the server's aim punch to pull down (26/10, Mirage's spray lab, the plugin's impacts: 2.0, the
# weapon_recoil_scale, put the bullets lower and lower, -70 to -120 u by the 10th at 700 u; 1.0 higher and higher,
# +20 to +45 u; 1.3 within 10 u, 5 clean sprays in 5 at 470-640 u, 13 bullets instead of 27). COACH_RECOIL to try one.
# 27/10 09:20 Inferno spray lab, the first bullet now settled (see VIEW_LAG): 1.5 with no punch prediction put Quad's
# sprays within +-6 u up (3/5 clean); 2.0 a hair low (Apps 4/5); 2.0 with 0.05-0.15 s of prediction 45-260 u low
RECOIL_SCALE = float(os.environ.get("COACH_RECOIL") or 1.5)
PUNCH_AHEAD = float(os.environ.get("COACH_PUNCH_AHEAD") or 0.0)
# per weapon (27/10): the AK went high with 1.3 (Vertigo's T Corridor +11 to +19 u at 510 u, Mirage's Palace) and low
# with 2.0 (Mirage's A Site -70 to -120 u by its 10th bullet); the M4s high with 1.3 (Boulder's Drop +30 to +70 u at
# 900 u, Train's A Site +20 to +65 u), clean with 2.0 (Drop 4/5, A Site 3/5 in round 2)
# ... and then Mirage's Connector with 1.8: its 11th-17th bullets 36-75 u low. The pull a spray needs looks stronger early
# than late; one 1.5 for all, between those errors, till a lab maps it bullet by bullet.
PULL = {}


def pull(weapon=None):
    w = str(weapon or LIVE.get("me_weapon") or "")
    if os.environ.get("COACH_RECOIL"):
        return RECOIL_SCALE
    return next((v for k, v in PULL.items() if k in w), RECOIL_SCALE)


def recoil():
    """Your aim punch as the training server has it now (bots_live.json, every tick while you shoot: 26/10), moved on
    by its speed to the file's tick -> ((pitch, yaw), shots fired); ((0, 0), 0) when unknown."""
    import json
    try:
        with open(BOTS_LIVE, encoding="utf-8") as fh:
            B = json.load(fh)
    except (OSError, ValueError):
        return (0.0, 0.0), 0
    LIVE.clear()
    LIVE.update(B)
    p, v = B.get("me_punch") or [0.0, 0.0], B.get("me_punch_vel") or [0.0, 0.0]
    # moved on to the file's tick, and on by the view's lag (the view set now is the one a bullet takes that much later)
    dt = max(0.0, min(0.1, ((B.get("t") or 0) - (B.get("me_punch_tick") or 0)) / 64.0)) + PUNCH_AHEAD
    return (p[0] + v[0] * dt, p[1] + v[1] * dt), B.get("me_shots") or 0


# each weapon's spray learned bullet by bullet (30/10, round 13, Train's A Site: 0/5, the same bullets wrong spray after spray,
# its 5th-12th 15-30 u high at 525 u, its 10th-12th 20-30 u left): the aim moved for its n-th bullet by what its n-th bullets
# missed by before, as a hand learns a pattern (degrees: the recoil is an angle, the same at any range); a transfer's flick
# (over 6 deg) not learnt from
SPRAY_TABLE = os.path.join(HERE, "out", "realtest", "spray_table.json")
SPRAY_GAIN, SPRAY_MAX, SPRAY_OUTLIER = 0.1, 4.0, 9.0   # 10/11: 0.25 ran the AK's row off to the caps (294 sprays, bullets 8-30 at +-4 deg, alternating; Train's T Main 3-7 hits of 30), its row reset; 30/10 23:58: at 0.35/4.0/6.0 bullets 5-7 sat at +4 deg (the transfer's misses learnt); 31/10 02:40: the first target's bullets only now, its 4th-8th 3-8 deg high at 500 u were all cut as outliers at 4


def _spray_table():
    import json
    try:
        with open(SPRAY_TABLE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _spray_learn(weapon, imp):
    """After a spray: each bullet's miss (its impact by the target, up and across) moved into that weapon's table."""
    import json
    if not weapon or not imp:
        return
    T = _spray_table()
    row = T.setdefault(weapon, {"n": [[0.0, 0.0] for _ in range(31)], "sprays": 0})
    imp = sorted(imp)
    first = imp[0][1]   # its first target's bullets only: the transfer's flick to the second is no pattern (30/10)
    for i, x in enumerate(imp[:30], 1):
        if x[1] != first:
            break
        d_ = x[4] or 0
        if d_ < 50 or x[5]:   # a bullet a wall stopped: not learnt (10/11, a hidden one's or a flip's, not the pattern's)
            continue
        ep, ey = math.degrees(math.atan2(float(x[3]), d_)), math.degrees(math.atan2(float(x[2]), d_))
        if abs(ep) > SPRAY_OUTLIER or abs(ey) > SPRAY_OUTLIER:
            continue
        row["n"][i][0] = max(-SPRAY_MAX, min(SPRAY_MAX, row["n"][i][0] + SPRAY_GAIN * ep))
        row["n"][i][1] = max(-SPRAY_MAX, min(SPRAY_MAX, row["n"][i][1] + SPRAY_GAIN * ey))
    row["sprays"] += 1
    try:
        with open(SPRAY_TABLE, "w", encoding="utf-8") as fh:
            json.dump(T, fh)
    except OSError:
        pass


def spray(target, eye, secs=3.5, keep=None, pre=None, pace=None):
    """One spray (26/10, his order: "perfectionne-toi sur toute la partie spray"): the crosshair put 100 times a second
    where target() says, less twice the recoil the server has for you (the pull a player's hand learns); held while
    keep() says the drill goes on, even with nobody in sight: then on pre() (where the next one is, behind its wall: it
    comes out there), else the last line. The view on it before the first bullet (26/10, the plugin's impacts: the
    first one always 84 u right, into the wall). pace: a bullet every pace s instead of the trigger held (far off, the
    spread of a held spray hit 5-7 bullets in 27 at 890 u; the drill lets go of a spray only past 12 ticks between two).
    -> seconds held."""
    stand_still()
    h0 = settle(lambda: target() or (pre() if pre is not None else None), eye)   # on it for VIEW_LAG first (27/10:
    # the first two bullets of a spray left 80-125 u wide, along the view before the flick)
    t0, last = time.time(), h0
    seen_imp, seen_hit = set(), set()   # the spray's bullets as the plugin saw them (the shot log)
    corr = [0.0, 0.0]   # its own correction from its bullets' impacts (pitch, yaw), the spray's own
    t_from = LIVE.get("t") or 0
    weapon = str(LIVE.get("me_weapon") or "")
    learnt = (_spray_table().get(weapon) or {}).get("n") or [[0.0, 0.0]] * 31   # its n-th bullet's aim, learnt
    next_shot, down, held_on = t0, False, False
    beat = pace
    try:
        while time.time() - t0 < secs:
            h = target()
            # nobody in a bullet's line: a bullet each 0.17 s keeps the spray going (the drill lets go of it past 12 ticks)
            # on half the bullets (26/10, Dust2's A Site: 15-20 bullets into the wall between the two, clips emptied)
            beat = pace if h is not None else (pace or 0.13)
            if beat is None:   # held
                if not held_on:
                    send("+attack")
                    held_on, down = True, True
            else:   # one bullet a beat: pressed, let go 50 ms later (27/10, Inferno's Pit: his game unfocused draws a frame
                # in 20-40 ms, a 20 ms press fell between two, no bullet, the gap past 12 ticks: "lâché" 5 times in 5)
                if held_on:   # from held to beats: the next bullet soon, or the gap since the last one lets it go
                    send("-attack")
                    held_on, down = False, False
                    next_shot = time.time() + 0.05
                press = PRESS_R8 if revolver() else 0.05
                if down and time.time() >= next_shot - beat + press:
                    send("-attack")
                    down = False
                if time.time() >= next_shot:
                    send("+attack")
                    down, next_shot = True, max(next_shot + max(beat, press + 0.2), time.time() + max(beat, press + 0.2) * 0.5)
            if h is None:   # nobody in a bullet's line: the trigger still going, on where the next one is (or the last
                # line), its recoil still pulled down (the drill counts a gap of 12 ticks between two bullets as let go)
                if keep is not None and not keep():
                    break
                h = (pre() if pre is not None else None) or last
                if h is None:
                    time.sleep(0.01)
                    continue
            last = h
            yaw = math.degrees(math.atan2(h[1] - eye[1], h[0] - eye[0]))
            pitch = -math.degrees(math.atan2(h[2] - eye[2], math.hypot(h[0] - eye[0], h[1] - eye[1])))
            (pp, py), nshot = recoil()
            k = pull()
            # its climb pulled less as the spray goes on (30/10, round 11: Train's and Dust2's sprays at 1.5 all along, their
            # 7th-23rd bullets 10-70 u low into the wall at 520 u, the early ones on; 27/10 already: "stronger early than
            # late"): the full pull to the 6th bullet, down to 0.8 of it by the 10th
            kp = k * (1.0 - 0.2 * min(1.0, max(0.0, (nshot - 6) / 4.0)))   # 2/3 of it overshot (Nuke's M4: its 15th-30th 20-50 u high)
            lp, ly = learnt[min(30, max(1, nshot + 1))]
            send(f"setang {pitch - kp * pp + corr[0] + lp:.3f} {yaw - k * py + corr[1] + ly:.3f} 0")
            for x in LIVE.get("me_impacts") or []:
                if x.get("t", 0) >= t_from:
                    key = (x["t"], x["slot"], x["across"], x["up"], x.get("dist"), x.get("wall"))
                    if key not in seen_imp and x.get("dist"):
                        # where it went by the target, the next ones moved the other way by half of it (30/10, his order:
                        # "améliore encore le spray": a hand follows its tracers; the AK's late bullets went low, the M4's
                        # high, one pull for all could not be right for both): pitch is down, yaw is left
                        d_ = max(50.0, float(x["dist"]))
                        corr[0] = max(-3.0, min(3.0, corr[0] + 0.2 * math.degrees(math.atan2(float(x["up"]), d_))))   # 0.5 swung it (its impacts 2-3 bullets late: Dust2, +60 then -100 u)
                        corr[1] = max(-3.0, min(3.0, corr[1] + 0.2 * math.degrees(math.atan2(float(x["across"]), d_))))
                    seen_imp.add(key)
            for x in LIVE.get("me_hits") or []:
                if x.get("t", 0) >= t_from:
                    seen_hit.add((x["t"], x["slot"], x["group"], x["dmg"]))
            time.sleep(0.01)
    finally:
        send("-attack")
    if pace is None and len(seen_imp) >= 5 and os.environ.get("COACH_SPRAY_LEARN"):   # a held spray's bullets: its table
        # learns from them when asked only (10/11: learning in every run, the AK's row ran off to the caps, then labs'
        # misses moved both rows within an hour: no two runs of the test client were the same client)
        _spray_learn(weapon, list(seen_imp))
    if os.environ.get("COACH_SHOTLOG") and seen_imp:   # 26/10: is a miss the pull's (one side always) or the spread's?
        imp = sorted(seen_imp)
        miss = [x for x in imp if not any(h[0] == x[0] for h in seen_hit)]
        mean = lambda v: sum(v) / len(v) if v else 0.0
        print(f"      spray: {len(imp)} bullets, {len(seen_hit)} hits ({sum(1 for h in seen_hit if h[2] == 1)} head), "
              f"{round(mean([x[4] or 0 for x in imp]))} u; misses {len(miss)}: across {mean([x[2] for x in miss]):+.1f}, "
              f"up {mean([x[3] for x in miss]):+.1f}, by bullet "
              + " ".join(f"{i}:{x[2]:+.0f}/{x[3]:+.0f}{'w' if x[5] else ''}" for i, x in enumerate(imp, 1)
                         if not any(h[0] == x[0] for h in seen_hit))[:400], flush=True)
    return round(time.time() - t0, 2)


def scope_up(timeout=0.9):
    """A sniper's scope up and steady before the shot (26/10, Dust2's Top Mid boost: every AWP shot left unscoped,
    100-380 u off at 1600-2500 u; a click during the bolt is lost, one as the game zooms back in by itself takes it off):
    clicked only when the server says it is down, checked again, steady 0.35 s once up. -> True when up."""
    t0, clicked = time.time(), 0.0
    foes()
    # up and steady already (02/11, round 16, Fachwerk's AWP: held scoped, 0.35 s more before each shot, "in 0.35 s" every
    # time, the bots' whole reaction): at once
    if LIFE.get("scoped") and time.time() - LIFE.get("scoped_at", time.time()) >= 0.35:
        return True
    while time.time() - t0 < timeout:
        foes()
        if LIFE.get("scoped"):
            time.sleep(max(0.0, 0.35 - (time.time() - LIFE.get("scoped_at", time.time()))))
            foes()
            if LIFE.get("scoped"):
                return True
            continue
        if time.time() - clicked > 0.3:   # down: one click, then the server's word on it
            send("+attack2")
            time.sleep(0.06)   # a frame of his unfocused game at least (27/10, Mirage's AWP peek: 30 ms clicks, never scoped, 0 shots)
            send("-attack2")
            clicked = time.time()
        time.sleep(0.03)
    return bool(LIFE.get("scoped"))


def reload_if_empty(wait=3.5):
    """Its clip empty (bots_live.json me_clip, 27/10: a situation's shots left nothing, the test never reloaded): R,
    then waited for bullets in it again. -> True when it reloaded."""
    if LIVE.get("me_clip") != 0:
        return False
    send("+reload")
    time.sleep(0.05)
    send("-reload")
    t0 = time.time()
    while time.time() - t0 < wait:
        foes()
        if (LIVE.get("me_clip") or 0) > 0:
            break
        time.sleep(0.05)
    return True


def nearest(p, bs):
    return min(bs, key=lambda b: math.dist(p[:2], b["pos"][:2])) if bs and p else None


# how far ahead of a moving one to aim, in seconds of its run (27/10: the plugin's impacts put the bullets behind them at
# 0.06 and at 0.2 alike, the server's lag compensation in that reading; hits on ones crossing at 60+ u/s: Fachwerk 79 %,
# Nuke 28 % at 0.06, no gain at 0.2; 27/10 lab on Cache's rifle defenses: -0.15 and 0.0 alike, the drills passed, 12
# kills 0 deaths at 0.0, the few shots at ones crossing fast hit none at any lead): 0.06, as when the holds passed.
# 27/10: the view's own lag (see aim_at) taken for the lead it needs; 02/11, with the server's own speed of them (bots_live
# "vel"), the misses against their speed across the line (round 16, 360 shots since 12:00): 0.02-0.12 s wanted, 0.04 at the
# median, 0.2 led 15 u past one at 100 u/s (the MAG-7's misses at 120-220 u, the AWP's at 400-3,000 u)
# 02/11 19:10: back to VIEW_LAG. The miss measure above is against their position at the impact's tick, but the game hits
# them where your view showed them (its lag compensation); its rifle K/D by the server's log: 5.1-6.1 at 0.2 (10:15-13:55),
# 1.4-2.9 at 0.05 (13:55-19:00)
LEAD = float(os.environ.get("COACH_LEAD") or VIEW_LAG)


# holding fire on fast-crossing ones: off (27/10 07:50, Mirage's rifle defenses 3-5 kills where round 2 made 13-18: the
# Ts went by while it waited). COACH_HOLDFIRE=1 to try it again.
HOLD_FIRE = bool(os.environ.get("COACH_HOLDFIRE"))


GUNLESS = ("knife", "bayonet", "c4", "grenade", "flashbang", "molotov", "decoy", "healthshot", "taser")


def gun_ready(timeout=1.5):
    """Till the gun in your hands can fire (the plugin's me_ready: its draw, its bolt), 1.5 s at most (30/10, round 13,
    Boulder's R8: the knife put away, three Deagle shots in its draw, no bullet out, then a reload). -> it can."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        foes()
        r = LIVE.get("me_ready")
        if r is None or float(r) <= 0.02:
            return True
        time.sleep(min(0.05, float(r)))
    return False


# a gun's draw after a switch, waited for before its first shot (04/11, rounds 23-24: Cache's R18 clutch, its R8 drawn from the
# shotgun, its first shot "no impact" twice; Inferno's R17, its AK out of the knife, the same; the plugin's me_ready read
# right after the switch still the weapon before): no shot leaves in a draw anyway
DRAW_S = 0.9


def gun_in_hand():
    """A gun in your hands (27/10, Inferno's situations: shots with no bullet out, the knife or the bomb in hand, slot1 does
    nothing without a primary): the primary, else the pistol, ready to fire. -> the weapon then."""
    w = str(LIVE.get("me_weapon") or "")
    if w and not any(x in w for x in GUNLESS):
        gun_ready()
        return w
    w0 = w   # what was in the hands (nothing known: read again, no draw to wait for)
    # each slot waited for till its gun is in the hands, 0.6 s at most (31/10, round 14, Boulder's R21: 0.15 s, the knife still
    # in hand, its "shots" knife swings at 364 u)
    for slot in ("slot1", "slot2"):
        send(slot)
        t0 = time.time()
        while time.time() - t0 < 0.6:
            time.sleep(0.05)
            foes()
            w = str(LIVE.get("me_weapon") or "")
            if w and not any(x in w for x in GUNLESS):
                # its draw waited for only out of a knife, the bomb or a grenade known in hand: a weapon read as nothing a
                # moment is a gun already out (04/11, round 25: "[? None]" 4-9 times a map in defenses, the rifles' K/D
                # fell from 69/15 to 72/45 with 0.9 s of nothing each time)
                if w0 and any(x in w0 for x in GUNLESS):
                    time.sleep(max(0.0, DRAW_S - (time.time() - t0)))
                gun_ready()
                return w
    return w

BLOCKED, MISS = {}, {}   # slot -> until when it is left alone (shot twice from here without a scratch), misses in a row
MISS_AT = {}   # slot -> (where you stood, misses from there): many from one spot, it is left alone longer (you move)


FIRST = {}   # slot -> when a bullet's line to it opened (the shot log: how long it took to shoot)
ZCORR = {}   # slot -> (u added to its aim point's height from its last shots' misses, when, its last miss)
# on a boost only (02/11 19:40: made for one, its eyes off up on a teammate; on for every drill since 12:45, the rifles' K/D
# never came back to the morning's 5-6, 2.5 with the lead put back)
ZCORR_ON = [False]


def seen_now():
    """The ones seen and worth a shot now (not one just found behind something)."""
    t = time.time()
    fs = foes()
    for b in fs:
        if not b.get("los"):
            FIRST.pop(b["slot"], None)
        elif b["slot"] not in FIRST:
            FIRST[b["slot"]] = t
    return [b for b in fs if b.get("los") and BLOCKED.get(b["slot"], 0) < t]   # a bullet's line to it, traced by the server


STILL = 60.0   # u/s: a rifle shoots true under about a third of its run (the AK runs at 215)


def stand_still(timeout=0.5, track=None, p=None):
    """Stopped dead before a shot, by the server's word (27/10, Inferno's situations: 29 shots in 35 left at 150-240 u/s;
    his unfocused game takes a W let go 0.1-0.4 s late, sometimes later still): while the server sees you move, every
    movement key let go and the one against your motion tapped, as a player counter-strafes; 0.5 s at most. -> the
    speed it was left at. track: the point to keep the crosshair on meanwhile (30/10, the user: "si le client a un meilleur
    temps de réaction ... le taux de réussite sera beaucoup plus élevé": its first shot 1.13 s after their line opened at
    the median, the stop then the aim one after the other; a player's counter-strafe and flick are one move)."""
    t0, tapped, s = time.time(), 0.0, 0.0
    while True:
        foes()   # the plugin's file: your speed (me_vel), 16-32 times a second
        if track is not None:
            h = track()
            if h is not None:
                aim_at(h, p)
        v = LIVE.get("me_vel") or [0.0, 0.0, 0.0]
        s = math.hypot(v[0], v[1])
        if s < STILL or time.time() - t0 > timeout or LIVE.get("me_ground") is False:
            return s
        if time.time() - tapped > 0.15:   # the keys let go again, no tap against the motion (see brake)
            send("-forward", "-back", "-left", "-right", "-speed")
            tapped = time.time()
        time.sleep(0.02)


def fight(sniper=False, timeout=6.0, reach=None, pump=None, far_switch=False):
    """While one of them is seen: standing dead still, the crosshair on its head, one shot, the recoil back at rest
    before the next (23/10, the user: "t'as vidé deux chargeurs dans le vide, t'as pas du tout fait attention au recul");
    its health read after each: two shots without a scratch and it is behind something (the game's spotting keeps a
    while after it is gone): left alone 2 s, the feet move on (a sniper: scoped first, its bolt waited). -> how many
    of them went down."""
    down, t0, dry = 0, time.time(), 0
    foes()
    w_ = gun_in_hand()
    if sniper and not any(x in str(w_) for x in ("awp", "ssg08", "scar20", "g3sg1")):
        # its sniper in the hands, not the pistol (27/10, Mirage's AWP peek: the USP in hand, its right click the
        # silencer, never scoped: 11 fights, no shot)
        send("slot1")
        time.sleep(0.5)
        foes()
    # a sniper by what is in the hands too (27/10, Anubis's R9 situation: his AWP shot unscoped, the drill naming no weapon)
    sniper = sniper or any(w in str(LIVE.get("me_weapon") or "") for w in ("awp", "ssg08", "scar20", "g3sg1"))
    # a shotgun by what is in the hands too: its reach and its pump (02/11, round 15, Dust2's situations: his MAG-7 fired at
    # 800-930 u, its clicks during the pump taken for lost taps)
    w_in = str(LIVE.get("me_weapon") or "")
    if any(x in w_in for x in ("mag7", "nova", "xm1014", "sawedoff")):
        pump = pump or (0.3 if "xm1014" in w_in else 0.9)
        reach = reach or (350.0 if "xm1014" in w_in else 170.0)   # 04/11: the MAG-7's 170 u (play_module's REACH)
    PUMP_AIM[0] = bool(pump)   # its settle's turn by distance (aim_at), for a shotgun only
    while time.time() - t0 < timeout:
        if reload_if_empty() or dry >= 2:   # an empty clip (or two shots with no bullet out): reloaded first
            # not with bullets in the clip (31/10, round 15, Train's R3: a full M4's taps lost, its reload did nothing, 2.5 s
            # gone in a duel)
            if dry >= 2 and not (isinstance(LIVE.get("me_clip"), int) and LIVE.get("me_clip") > 0):
                send("+reload")
                time.sleep(0.05)
                send("-reload")
                time.sleep(2.5)
            dry = 0
        p = livepos()   # the server's word, no console round trip (30/10: 0.31 s from their line to the fight at the median)
        seen = [b for b in seen_now() if reach is None or (p and math.dist(p[:2], b["pos"][:2]) <= reach)]   # a shotgun's reach
        # a pump shotgun waits for its head or chest: an arm out of cover is no shot (31/10, round 15, Train B's MAG-7: three
        # pumps at 108 u into the only part out, 19 a shot, while its AK shot back; 11 of his 13 deaths there)
        if pump:
            seen = [b for b in seen if b.get("los") != "body" or (p and math.dist(p[:2], b["pos"][:2]) < 90)]
        # a shotgun with them all out of its reach, in a situation: the pistol drawn, the fight with it (04/11, round 22,
        # Cache's R18 clutch with an XM1014 and an R8: 17 aims in 5.5 s, no shot, dead to one 400+ u off, every round; a
        # defense's shotgun waits in its corner instead)
        if not seen and far_switch and pump and seen_now():
            send("slot2")
            t_sw = time.time()
            while time.time() - t_sw < 0.8:
                time.sleep(0.05)
                foes()
                if not any(x in str(LIVE.get("me_weapon") or "") for x in ("mag7", "nova", "xm1014", "sawedoff")):
                    break
            w_now = str(LIVE.get("me_weapon") or "")
            if not any(x in w_now for x in ("mag7", "nova", "xm1014", "sawedoff")):
                print(f"      shotgun out of reach: {w_now} drawn", flush=True)
                pump, reach = None, None
                PUMP_AIM[0] = False
                time.sleep(max(0.0, DRAW_S - (time.time() - t_sw)))
                gun_ready()
                continue
        if not seen:
            break
        b = nearest(p, seen)
        if not b:
            break
        hp0 = b.get("hp", 100)
        # one hit from down (40 hp or less: any bullet kills it; a helmet's headshot leaves 11-13): no rest for the weapon's
        # accuracy, two bullets at its chest at once (10/11, rounds 24-26: 17 of 54 deaths in rifle duels came with the bot at
        # 40 hp or less, the next shot 0.58-0.77 s after the one that hurt it)
        finish = not sniper and not pump and not revolver() and not semi_auto() and isinstance(hp0, (int, float)) and hp0 <= 40
        # crossing fast: the crosshair kept on it, the shot when it slows (27/10, labs on Inferno's Banana and Cache:
        # shots at ones crossing at 60+ u/s never hit, at any lead from -0.45 to +0.2, 0 of 71; still ones 36-68 %;
        # bots stop to fight), a second of that at most
        mv = b.get("vel") or [0.0, 0.0, 0.0]
        if p:
            lx, ly = b["pos"][0] - p[0], b["pos"][1] - p[1]
            ll = math.hypot(lx, ly) or 1.0
            vlat = abs(mv[0] * ly - mv[1] * lx) / ll
            first = FIRST.get(b["slot"], time.time())
            # never close in nor with a shotgun (27/10, Boulder's MAG-7 posts: waiting on rushers 0-1 kills, 3 deaths)
            if HOLD_FIRE and vlat > 80 and time.time() - first < 1.0 and not pump and not sniper and ll > 500:   # (an AWP's hold lost its duels)
                aim_at(head_of(b), p)
                time.sleep(0.03)
                continue
        if sniper:   # scoped, the server's word on it (scope_up), never a shot without it
            if not scope_up():
                continue
            p = livepos() or p   # the plugin's word (02/11: the console's getpos, 0.1-0.5 s before each AWP shot)
            b = next((x for x in foes() if x["slot"] == b["slot"]), b)   # where it is now, after the scope
        slot = b["slot"]
        drop = 14 if sniper else 8 if pump else 10 if finish else 0   # an AWP: its chest (a body shot kills, twice the mark far off); a
        # shotgun: its neck, the pellets' cloud over head and chest (26/10, Boulder's MAG-7)

        # a shotgun leads them more (03/11, rounds 20-21: its misses on movers 27 behind them, 12 ahead, at 170 u and 150 u/s
        # across; the M4's 127 behind, 113 ahead)
        lead = LEAD * (PUMP_LEAD if pump else SNIPER_LEAD if sniper else
                       FAR_LEAD if p and math.dist(p[:2], b["pos"][:2]) > 600 else 1.0)

        def point(slot=slot, drop=drop):
            nonlocal b
            bb = next((x for x in foes() if x["slot"] == slot), None)
            if bb is None:
                return None
            b = bb
            if b.get("los") == "body" and b.get("part"):   # head and chest hidden: the part a bullet gets to (plugin, 27/10)
                v = b.get("vel") or [0.0, 0.0, 0.0]
                return [b["part"][0] + v[0] * lead, b["part"][1] + v[1] * lead, b["part"][2]]
            hh = head_of(b, lead=lead)
            zc, zt = ZCORR.get(slot, (0.0, 0.0, None))[:2]
            # its chest only when the plugin has it in a bullet's line (02/11, round 16, Dust2's Long: an AWP shot 1.4 u off
            # the chest's middle at 965 u, a still one, no damage: into its cover, its head out)
            dr = drop if b.get("chest", True) else 0
            return [hh[0], hh[1], hh[2] - dr + (zc if time.time() - zt < 10 else 0.0)]
        t_in = time.time()   # where its first shot's time goes (30/10, his order: his 0.3 s, a first damage in 0.4-0.5 s)
        stand_still(track=point, p=p)   # the feet dead still first (27/10: W let go late, shots on the run), the crosshair on it meanwhile
        t_st = time.time()
        h = settle(point, p)   # the view on it for VIEW_LAG before the click, tracking it (27/10)
        t_se = time.time()
        if h is None:
            continue
        # its blast on their stop at every distance (04/11, rounds 23-24: every MAG-7 blast at one standing hit, 10 of 10, at
        # movers 19 %; the bots stop to shoot); a rifle's too past 600 u (04/11, rounds 23-25: its hits there on still ones
        # 54 %, on slow ones 25 %, on runners 13 % of 344 shots)
        if (pump or sniper or (p and math.dist(p[:2], b["pos"][:2]) > 600)) and not finish:
            # one big shot timed on its stop, as a player waits for the other's counter-strafe (02/11, round 16, Mirage's
            # MAG-7: its blasts 12-78 u off strafers at 120-250 u, either side; the bots slow to a fifth to shoot): 0.25 s
            # at most, the crosshair on it meanwhile
            t_w = time.time()
            while time.time() - t_w < 0.25:
                v_ = (next((x for x in foes() if x["slot"] == b["slot"]), None) or {}).get("vel") or [0.0, 0.0, 0.0]
                if math.hypot(v_[0], v_[1]) < 70:
                    break
                h_ = point()
                if h_ is None:
                    break
                aim_at(h_, p)
                time.sleep(0.02)
        if sniper:
            time.sleep(0.03)
        far = p and math.dist(p[:2], b["pos"][:2]) > 600
        foes()   # the state the shot leaves in: scoped, your own speed (the shot log)
        sc_before, v_me, gnd = LIFE.get("scoped"), LIVE.get("me_vel") or [0.0, 0.0, 0.0], LIVE.get("me_ground")
        wpn = f"{str(LIVE.get('me_weapon') or '?').replace('weapon_', '')} {LIVE.get('me_clip')}"
        if (LIVE.get("me_ready") or 0) > 0.02:   # its pump, its bolt, its draw: the click waits till it can fire
            gun_ready(timeout=1.0)
        clip0 = LIVE.get("me_clip")
        ready0 = LIVE.get("me_ready") or 0
        t_shot = LIVE.get("t") or 0
        near = p is not None and math.dist(p[:2], b["pos"][:2]) < 600 and not sniper and not pump and not revolver()
        t_fire = time.time()   # the click itself (30/10: the log timed the shot after the pump's 0.85 s, 1.1-1.7 s "after its line")
        if finish and not near:   # far off: two bullets (0.09 s a bullet for an M4), then at it again (10/11); close in, the
            # burst below, on its chest
            send("+attack")
            time.sleep(0.16)
            send("-attack")
            time.sleep(0.12)
        elif near and semi_auto():
            # a pistol close: one bullet a click, then the crosshair back on it, its kick let go, not pulled (03/11, round
            # 19: the burst's 0.45 s pull after its one bullet left the view under it; the next tap with no settle went with
            # it: the P2000's 16.6 u under the head at the median, 37-45 u in the legs at 590 u, the Glock 10, the Tec-9 11)
            send("+attack")
            time.sleep(0.05)
            send("-attack")
            t_b = time.time()
            while time.time() - t_b < 0.25:   # its accuracy back (26/10, Boulder's pistols: a 0.25 s rest)
                hh = point()
                if hh is None:
                    break
                aim_at(hh, p)
                time.sleep(0.01)
        elif near:
            # close: a burst, its recoil pulled down on it as it goes (30/10: 22 of its deaths in Fachwerk's defense, most
            # with the crosshair 0-11 deg on its killer 100-400 u off, one tap a 0.25 s rest against a bot's spray)
            send("+attack")
            t_b = time.time()
            try:
                while time.time() - t_b < 0.45:
                    hh = point()
                    if hh is None:
                        break
                    if finish and b.get("los") != "body":   # one hit from down: its chest, the bigger mark (10/11)
                        hh = [hh[0], hh[1], hh[2] - 10]
                    yw = math.degrees(math.atan2(hh[1] - p[1], hh[0] - p[0]))
                    pt = -math.degrees(math.atan2(hh[2] - p[2], math.hypot(hh[0] - p[0], hh[1] - p[1])))
                    (rpp, rpy), _ = recoil()
                    kk = pull()
                    send(f"setang {pt - kk * rpp:.3f} {yw - kk * rpy:.3f} 0")
                    time.sleep(0.01)
            finally:
                send("-attack")
            time.sleep(0.12)
        else:
            send("+attack")
            # a frame of his unfocused game at least (27/10: 20 ms presses lost, "no impact"); the R8 fires only once its hammer
            # is back, the click held about 0.3 s (29/10, the user at Cache's R3, B halls: "quand tu cliques gauche ... tu
            # charges un petit peu le clic, mais tu tires jamais")
            time.sleep(PRESS_R8 if revolver() else 0.05)
            send("-attack")
            # the weapon's accuracy back before the next tap: far off, a 0.25 s rest left the bullets 8 u around the head
            # at 850 u (26/10, Boulder's pistols)
            # a pump shotgun fires once in 0.85 s: a click before that is lost (26/10: "no impact" every other shot)
            # an AWP's bolt: 1.46 s, slept here (10/11: a night with the bolt left to the caller, walked out of their sight
            # meanwhile, whatever their distance: its kills for a death fell from 4.0 to 2.5 on round 27's first four maps while
            # the rifle's and the pistol's rose; taken back)
            rest = 1.5 if sniper else pump if pump else 0.4 if far else 0.25
            if sniper or pump or revolver():
                time.sleep(rest)
            else:
                # its rest cut short once the tap left it one hit from down, or down (10/11, Inferno's rifles in round 26: hit
                # to 11-13 hp, the next tap 0.45 s on, dead meanwhile): at it again at once (finish), 0.08 s for the hit to show
                t_r = time.time()
                while time.time() - t_r < rest:
                    time.sleep(0.02)
                    if time.time() - t_r < 0.08:
                        continue
                    nb = next((x for x in foes() if x["slot"] == b["slot"]), None)
                    hp1 = nb.get("hp") if nb is not None else None
                    if nb is None or (isinstance(hp1, (int, float)) and isinstance(hp0, (int, float)) and hp1 <= 40 and hp1 < hp0):
                        break
        cur = next((x for x in foes() if x["slot"] == b["slot"]), None)
        # its bullets' height on it corrected shot by shot, as a player sees his go low (02/11, round 15, Anubis's Canals boost:
        # 15 Glock bullets 25-28 u under the head at 531 u, one after the other): 0.7 of the miss, 40 u at most, 10 s
        imp0 = next((x for x in LIVE.get("me_impacts") or [] if x.get("t", 0) >= t_shot and x.get("slot") == b["slot"]), None)
        if imp0 is not None and not pump and b.get("los") != "body" and ZCORR_ON[0]:
            # its miss against the point aimed at (the plugin's "up" is from its head; an AWP aims 14 u under it, a chest 20)
            want_up = -(drop if b.get("chest", True) else 0) - (20 if b.get("los") == "chest" else 0)
            zc, zt, m0 = ZCORR.get(b["slot"], (0.0, 0.0, None))
            if time.time() - zt >= 10:
                zc, m0 = 0.0, None
            miss = float(imp0.get("up") or 0.0) - want_up
            # two misses the same way in a row, 6 u at least: half of it taken back; else what it had fades (02/11, Mirage's
            # A at 1,000 u: 0.7 of each miss swung it -29, -34, -12, +12, +19 u on a still one, its crouches 18 u each)
            if abs(miss) > 6 and m0 is not None and (miss > 0) == (m0 > 0):
                zc -= 0.5 * miss
            else:
                zc *= 0.7
            ZCORR[b["slot"]] = (max(-40.0, min(40.0, zc)), time.time(), miss)
        lost = ""
        if not near and not sniper and not pump and not revolver() and isinstance(clip0, int) and clip0 > 0 and ready0 <= 0.02 \
                and LIVE.get("me_clip") == clip0 and (LIVE.get("t") or 0) > t_shot + 4 and LIFE.get("alive", True):
            # a tap with no bullet out, the clip the same and the plugin's word fresh: pressed again at once, held longer
            # (31/10, round 15's situations: Train's R3, a full M4's three taps at 806 u, none out; 31 of Cache's and 11 of
            # Train's taps with the clip the same after; his game, unfocused, sleeps 20 ms a frame)
            lost = f" (tap lost: clip {clip0}, ready {LIVE.get('me_ready')}, {(LIVE.get('t') or 0) - t_shot} ticks on; pressed again)"
            send("+attack")
            time.sleep(0.12)
            send("-attack")
            time.sleep(0.4 if far else 0.25)
            cur = next((x for x in foes() if x["slot"] == b["slot"]), None)
        if os.environ.get("COACH_SHOTLOG"):
            # where the bullet went by its head (the plugin's impact, not rewound to your view) and what it hit
            imp = next((x for x in LIVE.get("me_impacts") or [] if x.get("t", 0) >= t_shot and x.get("slot") == b["slot"]), None)
            dry = 0 if any(x.get("t", 0) >= t_shot for x in LIVE.get("me_impacts") or []) else dry + 1
            hit = next((x for x in LIVE.get("me_hits") or [] if x.get("t", 0) >= t_shot and x.get("slot") == b["slot"]), None)
            mv = b.get("vel") or [0.0, 0.0, 0.0]
            lx, ly = b["pos"][0] - p[0], b["pos"][1] - p[1]
            ll = math.hypot(lx, ly) or 1.0
            vlat = (mv[0] * ly - mv[1] * lx) / ll   # its speed across the line, + to the right as you look at it
            print(f"      shot at {b.get('name')} {round(math.dist(p[:2], b['pos'][:2]))} u, {b.get('los')}, "
                  f"moving {math.hypot(mv[0], mv[1]):.0f} u/s ({vlat:+.0f} across), "
                  + (f"bullet {imp['across']:+.1f} right {imp['up']:+.1f} up{' (wall)' if imp.get('wall') else ''} "
                     f"{imp['t'] - (b.get('t_read') or t_shot)} ticks after its position was read, " if imp else "no impact, ")
                  + (f"hit group {hit['group']} {hit['dmg']}, " if hit else "")
                  + f"[{wpn}] "
                  + f"{t_fire - FIRST.get(b['slot'], t_fire):.2f} s after its line opened "
                  + f"(in {t_in - FIRST.get(b['slot'], t_in):.2f}, stop {t_st - t_in:.2f}, settle {t_se - t_st:.2f}), scoped {sc_before} as it left, "
                  f"you at {math.hypot(v_me[0], v_me[1]):.0f} u/s {v_me[2]:+.0f} up{'' if gnd in (None, True) else ' OFF THE GROUND'}, "
                  f"hp {hp0} -> {cur.get('hp') if cur else 'down'}, you {'alive' if LIFE.get('alive', True) else 'DOWN'}{lost}", flush=True)
        if cur is None:
            down += 1
            MISS.pop(b["slot"], None)
            continue
        if cur.get("hp", 100) < hp0:
            MISS[b["slot"]] = 0
            MISS_AT.pop(b["slot"], None)
            continue
        MISS[b["slot"]] = MISS.get(b["slot"], 0) + 1
        at, n = MISS_AT.get(b["slot"], (None, 0))
        n = n + 1 if at is not None and p and math.dist(at[:2], p[:2]) < 40 else 1
        MISS_AT[b["slot"]] = (p, n)
        if n >= 9:   # 9 bullets from the same spot without a scratch: the sliver the server's line sees is no shot from
            # here; left alone 4 s, the feet go on (30/10, Boulder's Church prefire: 42 bullets in 70 s into the wall's edge,
            # 11 u left and 10 u low each time, never a step)
            BLOCKED[b["slot"]] = time.time() + 4.0
            MISS[b["slot"]] = 0
            MISS_AT.pop(b["slot"], None)
            break
        if MISS[b["slot"]] >= 3:   # 26/10: the line is the server's own trace now, so misses are the aim's, not a wall
            # (Train's T Main hold: two duels lost with the crosshair 0 deg off their head): left alone only a moment
            BLOCKED[b["slot"]] = time.time() + 0.6
            MISS[b["slot"]] = 0
            break
    return down


STEPS_LIVE = os.path.join("E:" + os.sep, "CS2Server", "game", "csgo", "coach", "steps_live.json")


def steps_live():
    """The step-by-step drill's toggles as the plugin sees them now (Steps.cs, 16 times a second): spot, aim, clicks,
    unlock, armed, thrown, move, dist, dz, speed, aim_off, duck, pos, ang; {} when none."""
    import json
    try:
        with open(STEPS_LIVE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def wait_steps(cond, timeout=2.0, drill=None):
    """The toggles once cond(toggles) holds (and, given, for that drill), or None when the time ran out."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        L = steps_live()
        if L and (drill is None or L.get("drill") == drill) and cond(L):
            return L
        time.sleep(0.03)
    return None


# ---------------------------------------------------------------- what the player sees, what the server said

def window():
    """The game's window on the screen: (x, y, w, h) of its picture, or None."""
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def each(h, _):
        n = user32.GetWindowTextLengthW(h)
        if n and user32.IsWindowVisible(h):
            b = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, b, n + 1)
            if b.value.strip() == "Counter-Strike 2":
                found.append(h)
        return True
    user32.EnumWindows(each, 0)
    if not found:
        return None
    h = found[0]
    r = ctypes.wintypes.RECT()
    user32.GetClientRect(h, ctypes.byref(r))
    p = ctypes.wintypes.POINT(0, 0)
    user32.ClientToScreen(h, ctypes.byref(p))
    return p.x, p.y, r.right - r.left, r.bottom - r.top


def shot(path_):
    """The game's window as a picture (what the player sees now)."""
    from PIL import ImageGrab
    w = window()
    if not w:
        return None
    x, y, ww, hh = w
    if x <= -30000 or ww <= 0 or hh <= 0:   # put away (minimized): no picture, the test goes on (22/10: a crash then)
        return None
    try:
        img = ImageGrab.grab(bbox=(x, y, x + ww, y + hh), all_screens=True)
        os.makedirs(os.path.dirname(os.path.abspath(path_)), exist_ok=True)
        img.save(path_)
    except Exception as e:
        print("shot:", e, flush=True)
        return None
    return path_


def record(path_, seconds):
    """A video of the game's window, seconds long at most, in the background: the ffmpeg process (stop it to end)."""
    w = window()
    if not w:
        return None
    x, y, ww, hh = w
    os.makedirs(os.path.dirname(os.path.abspath(path_)), exist_ok=True)
    return subprocess.Popen([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "gdigrab", "-framerate", "30",
                             "-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{ww}x{hh}", "-i", "desktop",
                             "-t", str(int(seconds)), "-c:v", "h264_nvenc", "-preset", "p4", "-b:v", "6M", path_],
                            stdin=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def stop(p):
    """A recording ended cleanly (its file playable)."""
    if p and p.poll() is None:
        try:
            p.stdin.write(b"q")
            p.stdin.flush()
            p.wait(timeout=15)
        except Exception:
            p.kill()


def plugin_log():
    import glob
    fs = glob.glob(os.path.join(PLUGIN_LOGS, "log-CoachReplay*.txt"))
    return max(fs, key=os.path.getmtime) if fs else None


def plugin_size():
    f = plugin_log()
    return (f, os.path.getsize(f)) if f else (None, 0)


def after(mark, line):
    """The mark just past that plugin line (the first one since mark holding its words): what the plugin said after it is
    still to be read (23/10 eve: the next drill announced 3.5 s after a success; the mark put at the log's end missed it,
    the driver waited 45 s for nothing and paused the session)."""
    words = (line or "").split("CoachReplay", 1)[-1].strip()[:30]
    f, start = mark
    f2 = plugin_log()
    base = start if f2 == f else 0
    txt = plugin_since(mark)
    # looked for as wait_plugin gave it, the chat's colour codes left out (24/10: a verdict's "✘ PEEK · Squeaky ·"
    # never found, the mark put at the log's end, past the next drill already announced: the session left paused)
    keep = [k for k, ch in enumerate(txt) if ch >= " " or ch == chr(10)]
    flat = "".join(txt[k] for k in keep)
    i = flat.find(words) if words else -1
    if i < 0:
        return plugin_size()
    j = flat.find(chr(10), i)
    end = len(txt) if j < 0 else keep[j] + 1
    return (f2, base + len(txt[:end].encode("utf-8")))


_PS = {}   # (log file, start) -> [read up to, its decoder, the text since start]


def plugin_since(mark):
    """The training server's lines (its plugin's log) since that mark. Read on from where the last call left it (30/10:
    the drill loops ask 20-50 times a second, each read the whole drill's log again)."""
    import codecs
    f, start = mark
    f2 = plugin_log()
    if not f2:
        return ""
    if f2 != f:
        start = 0
    key = (f2, start)
    e = _PS.get(key)
    if e is None:
        if len(_PS) > 8:
            _PS.clear()
        e = _PS[key] = [start, codecs.getincrementaldecoder("utf-8")("replace"), ""]
    with open(f2, "rb") as fh:
        fh.seek(e[0])
        data = fh.read()
    if data:
        e[0] += len(data)
        e[2] += e[1].decode(data)
    return e[2]


_WS = {}   # (mark, needles) -> how far its lines were looked at


def wait_plugin(mark, needles, timeout=20.0):
    """The first plugin line since mark holding one of the needles (or None when the time ran out)."""
    t0 = time.time()
    key = (mark[0], mark[1], tuple(needles))
    while True:
        # the lines not looked at yet for these needles (a line found is found again by the next same ask)
        txt = plugin_since(mark)
        i = _WS.get(key, 0)
        j = txt.rfind(chr(10), i) + 1
        while i < j:
            k = txt.find(chr(10), i) + 1
            ln = "".join(ch for ch in txt[i:k] if ch >= " ")   # the chat's colour codes the plugin's lines keep
            if any(n in ln for n in needles):
                _WS[key] = i
                return ln
            i = k
        if len(_WS) > 64:
            _WS.clear()
        _WS[key] = j
        # its wait within its time (30/10, round 13: the drill loops ask with 0.01-0.05 s and each ask slept 0.3 s, two a
        # loop: a seen enemy shot at 1.04 s after its line opened at the median in Overpass's defenses)
        left = timeout - (time.time() - t0)
        if left <= 0:
            return None
        time.sleep(min(0.3, left))


def main():
    a = sys.argv[1:]
    if a[0] == "cmd":
        print(ask(a[1], wait=1.0)[-2000:])
    elif a[0] == "pos":
        cheats()
        print(getpos())
    elif a[0] == "walk":
        cheats()
        print(walk_to(a[1], [float(v) for v in a[2].split(",")]))
    elif a[0] == "shot":
        print(shot(a[1]))
    elif a[0] == "window":
        print(window())


if __name__ == "__main__":
    main()
