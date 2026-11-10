// The map's navigation mesh for the bots of the plugin's hand (30/10, round 11: a bot off its recorded way had no way round a
// wall: Train's T Upper ledge and spawn stairs, Fachwerk's Apps, Mirage's Apartments, bots sliding along a wall or standing a
// minute, the user: "plus du tout de bots qui bug dans les murs"). tools/nav_export.py writes coach/nav/<map>.json from the
// map's own .nav: its floor areas (corners) and their links (the edge's middle, how far the floor rises past it). A way is
// found from area to area (A*, a jump over 18 u worth 600 u of walking, none over a crouched jump's 66 u, as the real-client
// test's tools/real_client.route_areas): the middles of the edges it crosses, then the point itself.
using System.Numerics;
using System.Text.Json;
using CounterStrikeSharp.API;

namespace CoachReplay;

public partial class CoachReplay
{
    string? navMap;
    Vector3[][] navPts = Array.Empty<Vector3[]>();       // each area's corners
    Vector3[] navCen = Array.Empty<Vector3>();           // its middle
    (float X0, float Y0, float X1, float Y1)[] navBox = Array.Empty<(float, float, float, float)>();
    // its links: the edge's middle, how far the floor rises past it; a ladder's (Lad its index): from its foot up to its top,
    // or from its top down to its foot (30/10, the user: "fix le map mesh": Overpass's bots above the ladder down to Connector
    // went round by Playground, the mesh read without its ladders)
    List<(int To, Vector3 Mid, float Rise, int Lad)>[] navLinks = Array.Empty<List<(int, Vector3, float, int)>>();
    (Vector3 Foot, Vector3 Top)[] navLad = Array.Empty<(Vector3, Vector3)>();
    // the mesh's links found shut in the game (30/10, round 13, Train: bots on the mesh's way swung side to side 20-30 s at a
    // passage it has open and the game had shut, a door, a gate, a train's car): a bot that got no nearer its next point in
    // 3 s by it marks that link, the ways after it go round. For the drill (its doors set anew at the next)
    readonly HashSet<(int, int)> navBlocked = new();
    readonly Dictionary<int, (int Next, float Best, int At, int Last)> navProg = new();   // its last call too: a hold is no try
    readonly Dictionary<int, (Vector3 Goal, int At)> navFail = new();   // its last way not found: to what, when
    readonly Dictionary<(int, int), List<int>> navGrid = new();   // 256 u cells -> the areas over them
    const float NavCell = 256f;

    void NavLoad()
    {
        var mp = Server.MapName;
        if (mp == navMap) return;
        navMap = mp; navGrid.Clear(); navBlocked.Clear(); navProg.Clear(); navFail.Clear();
        navPts = Array.Empty<Vector3[]>(); navCen = Array.Empty<Vector3>(); navBox = Array.Empty<(float, float, float, float)>();
        navLinks = Array.Empty<List<(int, Vector3, float, int)>>(); navLad = Array.Empty<(Vector3, Vector3)>();
        var fn = Path.Combine(Dir, "nav", $"{mp}.json");
        if (!File.Exists(fn)) { Log("nav: none for {m}", mp); return; }
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(fn));
            var r = doc.RootElement;
            var ids = new Dictionary<int, int>();
            var pts = new List<Vector3[]>();
            foreach (var a in r.GetProperty("areas").EnumerateArray())
            {
                var v = a.EnumerateArray().Select(x => x.GetSingle()).ToArray();
                var p = new Vector3[(v.Length - 1) / 3];
                for (int i = 0; i < p.Length; i++) p[i] = new Vector3(v[1 + 3 * i], v[2 + 3 * i], v[3 + 3 * i]);
                ids[(int)v[0]] = pts.Count;
                pts.Add(p);
            }
            navPts = pts.ToArray();
            navCen = navPts.Select(p => p.Aggregate(Vector3.Zero, (s, q) => s + q) / p.Length).ToArray();
            navBox = navPts.Select(p => (p.Min(q => q.X), p.Min(q => q.Y), p.Max(q => q.X), p.Max(q => q.Y))).ToArray();
            navLinks = navPts.Select(_ => new List<(int, Vector3, float, int)>()).ToArray();
            foreach (var l in r.GetProperty("links").EnumerateArray())
            {
                var v = l.EnumerateArray().Select(x => x.GetSingle()).ToArray();
                if (ids.TryGetValue((int)v[0], out var u) && ids.TryGetValue((int)v[1], out var w))
                    navLinks[u].Add((w, new Vector3(v[2], v[3], v[4]), v[5], -1));
            }
            // its ladders: [id, foot x y z, top x y z, [areas off its foot], [areas off its top]]
            var lads = new List<(Vector3, Vector3)>();
            if (r.TryGetProperty("ladders", out var la))
                foreach (var l in la.EnumerateArray())
                {
                    var e = l.EnumerateArray().ToArray();
                    if (e.Length < 9) continue;
                    var foot = new Vector3(e[1].GetSingle(), e[2].GetSingle(), e[3].GetSingle());
                    var top = new Vector3(e[4].GetSingle(), e[5].GetSingle(), e[6].GetSingle());
                    var li = lads.Count;
                    lads.Add((foot, top));
                    var bots = e[7].EnumerateArray().Select(x => x.GetInt32()).Where(ids.ContainsKey).Select(x => ids[x]).ToList();
                    var tops = e[8].EnumerateArray().Select(x => x.GetInt32()).Where(ids.ContainsKey).Select(x => ids[x]).ToList();
                    foreach (var b in bots)
                        foreach (var t in tops)
                        {
                            navLinks[b].Add((t, foot, 0f, li));
                            navLinks[t].Add((b, top, 0f, li));
                        }
                }
            navLad = lads.ToArray();
            for (int i = 0; i < navBox.Length; i++)
            {
                var b = navBox[i];
                for (int cx = (int)MathF.Floor(b.X0 / NavCell); cx <= (int)MathF.Floor(b.X1 / NavCell); cx++)
                    for (int cy = (int)MathF.Floor(b.Y0 / NavCell); cy <= (int)MathF.Floor(b.Y1 / NavCell); cy++)
                    {
                        if (!navGrid.TryGetValue((cx, cy), out var lst)) navGrid[(cx, cy)] = lst = new List<int>();
                        lst.Add(i);
                    }
            }
            Log("nav: {n} areas, {l} ladders read for {m}", navPts.Length, navLad.Length, mp);
        }
        catch (Exception e) { Log("nav: {m}", e.Message); navPts = Array.Empty<Vector3[]>(); }
    }

    // the floor's height of an area under (x, y): its corners' plane (the first three), else their mean
    static float NavZ(Vector3[] p, float x, float y)
    {
        if (p.Length < 3) return p.Average(q => q.Z);
        var n = Vector3.Cross(p[1] - p[0], p[2] - p[0]);
        return MathF.Abs(n.Z) < 1e-4f ? p.Average(q => q.Z) : p[0].Z - (n.X * (x - p[0].X) + n.Y * (y - p[0].Y)) / n.Z;
    }

    static bool NavInside(Vector3[] p, float x, float y)
    {
        bool c = false;
        for (int i = 0, j = p.Length - 1; i < p.Length; j = i++)
            if ((p[i].Y > y) != (p[j].Y > y) && x < (p[j].X - p[i].X) * (y - p[i].Y) / (p[j].Y - p[i].Y + 1e-6f) + p[i].X) c = !c;
        return c;
    }

    // the area a point stands on (its feet within 64 u up or down), else the nearest whose middle is within 120 u
    int NavArea(Vector3 at)
    {
        if (navPts.Length == 0) return -1;
        int best = -1; var bd = float.MaxValue;
        for (int cx = (int)MathF.Floor(at.X / NavCell) - 1; cx <= (int)MathF.Floor(at.X / NavCell) + 1; cx++)
            for (int cy = (int)MathF.Floor(at.Y / NavCell) - 1; cy <= (int)MathF.Floor(at.Y / NavCell) + 1; cy++)
            {
                if (!navGrid.TryGetValue((cx, cy), out var lst)) continue;
                foreach (var i in lst)
                {
                    var b = navBox[i];
                    var inside = at.X >= b.X0 - 1 && at.X <= b.X1 + 1 && at.Y >= b.Y0 - 1 && at.Y <= b.Y1 + 1 && NavInside(navPts[i], at.X, at.Y);
                    var dz = MathF.Abs(NavZ(navPts[i], at.X, at.Y) - at.Z);
                    var d = inside ? dz : new Vector2(navCen[i].X - at.X, navCen[i].Y - at.Y).Length() + 2f * MathF.Abs(navCen[i].Z - at.Z) + 1000f;
                    if (inside && dz > 64f || !inside && d > 1120f) continue;
                    if (d < bd) { bd = d; best = i; }
                }
            }
        return best;
    }

    // a way on the mesh from a to b: the middles of the edges it crosses (a ladder: its end where it gets on, then the other
    // one, climbed to: Climb), then b; null when either is off the mesh or none joins
    List<Vector3>? NavRoute(Vector3 a, Vector3 b, int maxAreas = 4000) => NavRouteC(a, b, maxAreas)?.Pts;

    (List<Vector3> Pts, List<bool> Climb, List<(int, int)> Link)? NavRouteC(Vector3 a, Vector3 b, int maxAreas = 4000)
    {
        int s = NavArea(a), t = NavArea(b);
        if (s < 0 || t < 0) return null;
        if (s == t) return (new List<Vector3> { b }, new List<bool> { false }, new List<(int, int)> { (-1, -1) });
        var g = new Dictionary<int, float> { [s] = 0f };
        var prev = new Dictionary<int, (int From, Vector3 Mid, int Lad)>();
        var q = new PriorityQueue<int, float>();
        q.Enqueue(s, Vector3.Distance(navCen[s], navCen[t]));
        var seen = 0;
        while (q.TryDequeue(out var u, out _))
        {
            if (u == t) break;
            if (++seen > maxAreas) return null;
            foreach (var (v, mid, rise, lad) in navLinks[u])
            {
                if (rise > 66f) continue;   // no crouched jump gets up there
                if (navBlocked.Contains((u, v))) continue;   // shut in the game
                // a ladder: its length climbed slower than a walk, and a moment to get on
                var cost = lad >= 0 ? g[u] + Vector3.Distance(navCen[u], mid) + 1.5f * Vector3.Distance(navLad[lad].Foot, navLad[lad].Top) + 100f
                                      + Vector3.Distance(mid == navLad[lad].Foot ? navLad[lad].Top : navLad[lad].Foot, navCen[v])
                    : g[u] + Vector3.Distance(navCen[u], mid) + Vector3.Distance(mid, navCen[v]) + (rise > 18f ? 600f : 0f);
                if (g.TryGetValue(v, out var gv) && gv <= cost) continue;
                g[v] = cost; prev[v] = (u, mid, lad);
                q.Enqueue(v, cost + Vector3.Distance(navCen[v], navCen[t]));
            }
        }
        if (!prev.ContainsKey(t)) return null;
        var steps = new List<(Vector3 Mid, int Lad, int From, int To)>();
        for (var c = t; c != s; c = prev[c].From) steps.Add((prev[c].Mid, prev[c].Lad, prev[c].From, c));
        steps.Reverse();
        var pts = new List<Vector3>();
        var climb = new List<bool>();
        var link = new List<(int, int)>();
        foreach (var (mid, lad, from, to) in steps)
        {
            pts.Add(mid); climb.Add(false); link.Add((from, to));
            if (lad < 0) continue;
            // its other end, climbed to: over the top's floor a little going up (feet on it), its foot going down
            var up = mid == navLad[lad].Foot;
            var end = up ? navLad[lad].Top + new Vector3(0f, 0f, 16f) : navLad[lad].Foot;
            pts.Add(end); climb.Add(true); link.Add((from, to));
        }
        pts.Add(b); climb.Add(false); link.Add((-1, -1));
        return (pts, climb, link);
    }

    // how long the mesh's way from a to b is (its ladders climbed); -1: none
    float NavLen(Vector3 a, Vector3 b)
    {
        try
        {
            var r = NavRouteC(a, b);
            if (r == null) return -1f;
            var len = 0f; var p = a;
            foreach (var q in r.Value.Pts) { len += Vector3.Distance(p, q); p = q; }
            return len;
        }
        catch (Exception) { return -1f; }
    }

    // on a ladder of its mesh way (at its foot or top, 48 u): its speed up or down it, pressed to it; null: not climbing
    Vector3? NavClimb(int slot, Vector3 here)
    {
        if (!navWay.TryGetValue(slot, out var w) || w.Next >= w.Pts.Count || !w.Climb[w.Next]) return null;
        var p = w.Pts[w.Next];
        if (new Vector2(p.X - here.X, p.Y - here.Y).Length() > 48f) return null;   // not on it yet
        var dz = p.Z - here.Z;
        if (MathF.Abs(dz) < 6f) return null;
        return new Vector3(Math.Clamp((p.X - here.X) * 4f, -100f, 100f), Math.Clamp((p.Y - here.Y) * 4f, -100f, 100f), MathF.Sign(dz) * 200f);
    }

    // each bot's mesh way while it is off its own (its goal, its points, the next one, when found)
    readonly Dictionary<int, (Vector3 Goal, List<Vector3> Pts, int Next, int At, List<bool> Climb, List<(int, int)> Link)> navWay = new();

    // where to head for now to get to `goal` from `here` round the walls: the next point of its mesh way (found again when the
    // goal moved 96 u, every 2 s, or once it is 200 u off it); the goal itself when the mesh has none
    // trying: it is asked to go now (a way's stand, its speed 0, gets no nearer and shuts nothing: 30/10)
    Vector3 NavSteer(int slot, Vector3 here, Vector3 goal, bool trying = true)
    {
        try { return NavSteer0(slot, here, goal, trying); }
        catch (Exception e) { navWay.Remove(slot); if (navErr++ < 5) Log("nav: {m}", e.Message); return goal; }   // never the tick's end
    }
    int navErr;

    Vector3 NavSteer0(int slot, Vector3 here, Vector3 goal, bool trying = true)
    {
        var now = Server.TickCount;
        // on a ladder: its way kept (found again from on it, it would start from the floor it left)
        var onLadder = navWay.TryGetValue(slot, out var w) && w.Next < w.Pts.Count && w.Climb[w.Next]
                       && new Vector2(w.Pts[w.Next].X - here.X, w.Pts[w.Next].Y - here.Y).Length() < 48f;
        if (!onLadder && (!navWay.TryGetValue(slot, out w) || Vector3.Distance(w.Goal, goal) > 96f || now - w.At > 128
            || w.Next < w.Pts.Count && new Vector2(w.Pts[w.Next].X - here.X, w.Pts[w.Next].Y - here.Y).Length() > 200f))
        {
            // a way not found is not looked for again each tick: a second, unless the goal went 200 u off (31/10, round 15,
            // Boulder's hunts: no way to you, its search of up to 4,000 areas each tick for each hunter, the server at 4 fps,
            // his game rolling back)
            if (navFail.TryGetValue(slot, out var nf) && now - nf.At < 64 && now >= nf.At && Vector3.Distance(nf.Goal, goal) < 200f)
                return goal;
            var r = NavRouteC(here, goal);
            if (r == null) { navWay.Remove(slot); navFail[slot] = (goal, now); return goal; }
            navFail.Remove(slot);
            w = (goal, r.Value.Pts, 0, now, r.Value.Climb, r.Value.Link);
        }
        // past a point once within 40 u of it (its height aside), or once the next one is nearer; a ladder's end once its
        // feet got there (up: on the top's floor; down: at its foot), never skipped
        while (w.Next < w.Pts.Count - 1)
        {
            var p = w.Pts[w.Next];
            var d = new Vector2(p.X - here.X, p.Y - here.Y).Length();
            if (w.Climb[w.Next])
            {
                if (d < 48f && (p.Z > w.Pts[Math.Max(0, w.Next - 1)].Z ? here.Z >= p.Z - 20f : here.Z <= p.Z + 20f)) { w.Next++; continue; }
                break;
            }
            var dn = new Vector2(w.Pts[w.Next + 1].X - here.X, w.Pts[w.Next + 1].Y - here.Y).Length();
            if (d < 40f || !w.Climb[w.Next + 1] && dn < d - 20f && d < 120f) w.Next++;
            else break;
        }
        // its headway to its next point: none in 3 s within 200 u of it (on no ladder) -> that link shut, the way found again
        var nx = Math.Min(w.Next, w.Pts.Count - 1);
        var dnx = new Vector2(w.Pts[nx].X - here.X, w.Pts[nx].Y - here.Y).Length();
        if (!navProg.TryGetValue(slot, out var pg) || pg.Next != nx || dnx < pg.Best - 24f || now - pg.Last > 16 || !trying) pg = (nx, dnx, now, now);
        navProg[slot] = pg = (pg.Next, pg.Best, pg.At, now);
        // never the last links by its goal (you, a player in the way, or a box it stands on: 30/10, Overpass's B, 4 shut in a minute)
        if (now - pg.At > 192 && dnx < 200f && !w.Climb[nx] && w.Link[nx].Item1 >= 0 && Vector3.Distance(w.Pts[nx], goal) > 150f)
        {
            var (u, v) = w.Link[nx];
            navBlocked.Add((u, v)); navBlocked.Add((v, u));
            Log("nav: shut in the game near {x:F0} {y:F0} {z:F0}, ways round it from now on", w.Pts[nx].X, w.Pts[nx].Y, w.Pts[nx].Z);
            navProg.Remove(slot); navWay.Remove(slot);
            return NavSteer0(slot, here, goal);
        }
        navWay[slot] = w;
        return w.Pts[Math.Min(w.Next, w.Pts.Count - 1)];
    }
}
