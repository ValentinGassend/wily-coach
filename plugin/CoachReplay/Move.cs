// What a bot does when its real way is over and it sees no enemy (29/10, the user: "tu as besoin de te nourrir encore
// beaucoup plus de ce que font les vrais joueurs dans les démos pour diriger les adversaires, mais aussi les alliés").
// tools/move_model.py reads the demos: for each 128 u cell and side, what the player could know (an enemy on his radar, one
// heard, a smoke up, the bomb down, nothing) and its direction, and the numbers (more of his team alive, as many, fewer),
// what real players did over the next second (held, walked or ran, which way) and one real way they took (4 s). move/<map>.json
// keeps each case's most common move and that way. A fighter of css_scripted (Combat.cs) out of its way decides every 2 s
// like that: holds (looking where players look, Look.cs) or follows that real way at its speed, then decides again; stuck
// half a second, it decides again. Deterministic: the most common move, its first way.
using System.Numerics;
using System.Text.Json;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;

namespace CoachReplay;

public partial class CoachReplay
{
    string? moveMap;
    float moveCell = 128f, moveZ = 96f;
    readonly Dictionary<string, (string Mv, float Share, int N, Vector3[] Way)> moveTab = new();
    readonly Dictionary<string, int> moveUsed = new();
    readonly Dictionary<int, int> lastShotOf = new();   // each player's last shot (the ears of the other side)
    readonly Dictionary<int, Vector3> lastShotAt = new();

    sealed class Roam
    {
        public string Mv = "h";
        public Vector3[] Way = Array.Empty<Vector3>();
        public int I, DecideAt, ProgAt;
        public Vector3 ProgFrom;
    }
    readonly Dictionary<int, Roam> roams = new();
    // tools/danger_util.py: what grenade players throw from a cell, by side and moment of the round, one real throw of it
    // (spot, view, technique, where it landed, its flight) and what it did on average
    readonly Dictionary<string, (string Type, float Share, int N, float[] Thr, float Dmg, float Blind, float Kills)> utilTab = new();
    readonly HashSet<string> utilDone = new();   // a bot's grenade thrown this drill: "slot|type"

    void MoveLoad()
    {
        var mp = Server.MapName;
        if (mp == moveMap) return;
        moveMap = mp; moveTab.Clear(); roams.Clear(); utilTab.Clear();
        var ufn = Path.Combine(Dir, "util", $"{mp}.json");
        if (File.Exists(ufn))
        {
            try
            {
                // its "NaN"s (no blind nor damage measured: a smoke) read as 0 (30/10: the reader refused them, no map's throw
                // places were ever read, "move: util 'N' is an invalid start of a value")
                using var ud = JsonDocument.Parse(System.Text.RegularExpressions.Regex.Replace(File.ReadAllText(ufn), @"\bNaN\b", "0"));
                foreach (var k in ud.RootElement.GetProperty("keys").EnumerateObject())
                {
                    var v = k.Value;
                    var thr = v.GetProperty("throw").EnumerateArray().Select(x => x.ValueKind switch
                    { JsonValueKind.True => 1f, JsonValueKind.False => 0f, JsonValueKind.Number => x.GetSingle(), _ => 0f }).ToArray();
                    utilTab[k.Name] = (v.GetProperty("type").GetString() ?? "", v.GetProperty("share").GetSingle(), v.GetProperty("n").GetInt32(), thr,
                                       v.GetProperty("damage").GetSingle(), v.GetProperty("blind").GetSingle(), v.GetProperty("kills").GetSingle());
                }
                Log("move: {n} throw places read for {m}", utilTab.Count, mp);
            }
            catch (Exception e) { Log("move: util {m}", e.Message); }
        }
        var fn = Path.Combine(Dir, "move", $"{mp}.json");
        if (!File.Exists(fn)) { Log("move: no table for {m}", mp); return; }
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(fn));
            var r = doc.RootElement;
            if (r.TryGetProperty("cell", out var ce)) moveCell = ce.GetSingle();
            if (r.TryGetProperty("zcell", out var ze)) moveZ = ze.GetSingle();
            foreach (var k in r.GetProperty("keys").EnumerateObject())
            {
                var v = k.Value;
                var way = v[3].EnumerateArray().Select(p => new Vector3(p[0].GetSingle(), p[1].GetSingle(), p[2].GetSingle())).ToArray();
                moveTab[k.Name] = (v[0].GetString() ?? "h", v[1].GetSingle(), v[2].GetInt32(), way);
            }
            Log("move: {n} cases read for {m}", moveTab.Count, mp);
        }
        catch (Exception e) { Log("move: {m}", e.Message); }
    }

    void MoveEvents()
    {
        RegisterEventHandler<EventWeaponFire>((e, _) =>
        {
            if (e.Userid is { IsValid: true } u && u.PlayerPawn.Value?.AbsOrigin is { } o)
            { lastShotOf[u.Slot] = Server.TickCount; lastShotAt[u.Slot] = new Vector3(o.X, o.Y, o.Z); }
            return HookResult.Continue;
        });
    }

    void MoveSay()
    {
        if (moveUsed.Count == 0) return;
        Log("move: {s}", string.Join(", ", moveUsed.OrderByDescending(k => k.Value).Select(k => $"{k.Key} {k.Value}")));
        moveUsed.Clear();
    }

    // what a side knows of the other now, from `at` (the demos' players' cases, Look.cs's for you alone): one of its own sees
    // an enemy (its radar), an enemy running within 1100 u or a shot within 2000 u in the last 1.5 s, the bomb down, a smoke
    (string Know, int Sec) SideKnows(int team, Vector3 at, List<Vector3> smokes)
    {
        var now = Server.TickCount;
        var mine = Utilities.GetPlayers().Where(p => p is { IsValid: true, PawnIsAlive: true } && p.TeamNum == team).Select(p => p.Slot).ToList();
        (float D, Vector3 P)? dot = null, heard = null;
        foreach (var pl in Utilities.GetPlayers())
        {
            if (pl is not { IsValid: true, PawnIsAlive: true } || pl.TeamNum == team || pl.TeamNum < 2) continue;
            var pp = pl.PlayerPawn.Value;
            if (pp?.AbsOrigin is not { } po) continue;
            var p3 = new Vector3(po.X, po.Y, po.Z);
            var d = Vector3.Distance(p3, at);
            var mk = pp.EntitySpottedState.SpottedByMask;
            uint m0 = mk[0], m1 = mk[1];   // copied: the mask is a span, no lambda may hold it
            if (mine.Any(s => s < 64 && ((s < 32 ? m0 : m1) & (1u << (s % 32))) != 0) && (dot == null || d < dot.Value.D)) dot = (d, p3);
            var v = pp.AbsVelocity is { } av ? new Vector2(av.X, av.Y).Length() : 0f;
            if (v > 135f && d < 1100f && (heard == null || d < heard.Value.D)) heard = (d, p3);
            if (lastShotOf.TryGetValue(pl.Slot, out var st) && now - st < 96 && lastShotAt.TryGetValue(pl.Slot, out var sp))
            {
                var ds = Vector3.Distance(sp, at);
                if (ds < 2000f && (heard == null || ds < heard.Value.D)) heard = (ds, sp);
            }
        }
        if (dot is { } dd) return ("dot", Sector(dd.P.X - at.X, dd.P.Y - at.Y));
        if (heard is { } hd) return ("heard", Sector(hd.P.X - at.X, hd.P.Y - at.Y));
        var c4 = Utilities.FindAllEntitiesByDesignerName<CPlantedC4>("planted_c4").FirstOrDefault(x => x.IsValid && x.BombTicking && !x.HasExploded);
        if (c4?.AbsOrigin is { } co) return ("planted", Sector(co.X - at.X, co.Y - at.Y));
        Vector3? sm = null; var best = 1200f;
        foreach (var s in smokes) { var d = Vector3.Distance(s, at); if (d < best) { best = d; sm = s; } }
        if (sm is { } ss) return ("smoke", Sector(ss.X - at.X, ss.Y - at.Y));
        return ("none", -1);
    }

    int Alive(int team) => Utilities.GetPlayers().Count(p => p is { IsValid: true, PawnIsAlive: true } && p.TeamNum == team);

    // a fighter out of its way, nobody in its sight: what players did there. -> true when it moved this tick (its eyes set)
    bool RoamTick(int slot, Fighter fi, CCSPlayerPawn pw, List<Vector3> smokes)
    {
        if (moveTab.Count == 0 || pw.AbsOrigin == null) return false;
        var now = Server.TickCount;
        var at = new Vector3(pw.AbsOrigin.X, pw.AbsOrigin.Y, pw.AbsOrigin.Z);
        var team = fi.T?.Team ?? pw.TeamNum;
        if (!roams.TryGetValue(slot, out var ro)) roams[slot] = ro = new Roam { DecideAt = now };
        var stuck = ro.Mv != "h" && now - ro.ProgAt >= 32 && Vector3.Distance(at, ro.ProgFrom) < 24f;
        if (now >= ro.DecideAt || stuck)
        {
            var side = team == 2 ? "T" : "CT";
            var cell = $"{side}|{(int)MathF.Floor(at.X / moveCell)}|{(int)MathF.Floor(at.Y / moveCell)}|{(int)MathF.Floor(at.Z / moveZ)}";
            var (know, sec) = SideKnows(team, at, smokes);
            var adv = Math.Sign(Alive(team) - Alive(team == 2 ? 3 : 2));
            (string Mv, float Share, int N, Vector3[] Way) m;
            if (BehCaseFor(team, pw, at, out var blv) is { } bc && (bc.Mv == "h" || bc.Way.Length >= 2))   // the behaviour model first
            { m = (bc.Mv, bc.MvShare, bc.N, bc.Way); behUsed[$"move {blv} {bc.Mv[0]}"] = behUsed.GetValueOrDefault($"move {blv} {bc.Mv[0]}") + 1; }
            else if (!(moveTab.TryGetValue($"{cell}|{know}|{sec}|{adv}", out m) || moveTab.TryGetValue($"{cell}|{know}|{sec}|x", out m)
                  || moveTab.TryGetValue($"{cell}|none|-1|x", out m)))
                m = ("h", 0f, 0, Array.Empty<Vector3>());
            if (stuck && m.Mv == ro.Mv) m = ("h", 0f, 0, Array.Empty<Vector3>());   // stuck on that way: it holds this time
            ro.Mv = m.Way.Length < 2 ? "h" : m.Mv;
            ro.Way = m.Way;
            // its way from the point of it nearest to where the bot stands
            ro.I = 0;
            var bd = float.MaxValue;
            for (int i = 0; i < ro.Way.Length; i++) { var d = Vector3.DistanceSquared(ro.Way[i], at); if (d < bd) { bd = d; ro.I = i; } }
            ro.DecideAt = now + 128; ro.ProgAt = now; ro.ProgFrom = at;
            moveUsed[$"{know}:{ro.Mv[0]}"] = moveUsed.GetValueOrDefault($"{know}:{ro.Mv[0]}") + 1;
        }
        TryThrow(slot, team, pw, at);
        if (ro.Mv == "h") return false;
        while (ro.I < ro.Way.Length - 1 && Vector2.Distance(new Vector2(ro.Way[ro.I].X, ro.Way[ro.I].Y), new Vector2(at.X, at.Y)) < 24f) ro.I++;
        var tgt = ro.Way[ro.I];
        var dir = new Vector2(tgt.X - at.X, tgt.Y - at.Y);
        if (dir.Length() < 8f || ro.I >= ro.Way.Length - 1 && dir.Length() < 24f) { ro.Mv = "h"; return false; }
        // a fire on its way: it waits for it (no one walks into a molotov); a teammate right ahead: it keeps its distance
        var nx = new Vector3(tgt.X, tgt.Y, tgt.Z);
        if (Utilities.FindAllEntitiesByDesignerName<CInferno>("inferno").Any(f => f.IsValid && f.FireCount > 0 && f.AbsOrigin is { } fo
                && Vector2.Distance(new Vector2(fo.X, fo.Y), new Vector2(nx.X, nx.Y)) < 170f)) { pw.Teleport(null, null, Vector3.Zero); return true; }
        var ahead = Vector2.Normalize(dir);
        if (Utilities.GetPlayers().Any(p => p is { IsValid: true, PawnIsAlive: true } && p.TeamNum == team && p.Slot != slot && p.PlayerPawn.Value?.AbsOrigin is { } mo
                && Vector2.Distance(new Vector2(mo.X, mo.Y), new Vector2(at.X, at.Y)) < 110f && Vector2.Dot(Vector2.Normalize(new Vector2(mo.X - at.X, mo.Y - at.Y) + new Vector2(0.001f, 0f)), ahead) > 0.6f))
        { pw.Teleport(null, null, Vector3.Zero); return true; }
        var speed = ro.Mv[0] == 'r' ? 245f : 125f;
        var vz = pw.AbsVelocity?.Z ?? 0f;
        var v2 = Vector2.Normalize(dir) * speed;
        pw.Teleport(null, new Vector3(0f, MathF.Atan2(dir.Y, dir.X) * 180f / MathF.PI, 0f), new Vector3(v2.X, v2.Y, vz));
        if (Vector3.Distance(at, ro.ProgFrom) >= 24f) { ro.ProgAt = now; ro.ProgFrom = at; }
        return true;
    }

    // the grenade players throw from where it stands, at that moment of the round, when it is a common and useful one: thrown
    // once a drill by this bot, its eyes along the real throw, its velocity solved from the real landing and flight (a
    // grenade falls at 0.4 of the game's gravity)
    void TryThrow(int slot, int team, CCSPlayerPawn pw, Vector3 at)
    {
        if (utilTab.Count == 0 || cur == null) return;
        var side = team == 2 ? "T" : "CT";
        var secs = (Server.TickCount - t0) / 64f;
        var ph = secs < 25f ? 0 : secs < 60f ? 1 : 2;
        var key = $"{side}|{(int)MathF.Floor(at.X / moveCell)}|{(int)MathF.Floor(at.Y / moveCell)}|{(int)MathF.Floor(at.Z / moveZ)}|{ph}";
        if (!utilTab.TryGetValue(key, out var u) || u.Thr.Length < 13 || u.Share < 0.25f) return;
        if (!(u.Type == "smoke" || u.Blind >= 0.3f || u.Dmg >= 10f || u.Kills >= 0.1f)) return;   // useful, as players used it
        if (!utilDone.Add($"{slot}|{u.Type}")) return;
        var c = Utilities.GetPlayerFromSlot(slot);
        if (c == null) return;
        var eye = new Vector3(at.X, at.Y, at.Z + 64f);
        var land = new Vector3(u.Thr[9], u.Thr[10], u.Thr[11]);
        var T = u.Thr[12] > 0.3f ? Math.Clamp(u.Thr[12], 0.5f, 3.0f) : Math.Clamp(Vector3.Distance(eye, land) / 650f, 0.6f, 2.5f);
        var v = (land - eye) / T + new Vector3(0f, 0f, 0.5f * 320f * T);
        if (v.Length() > 1100f) return;   // no hand throws that far: not from here
        SetEyes(pw, new Vector3(u.Thr[3], u.Thr[4], 0f));
        ThrowAs(c, pw, new Nade { Type = u.Type, Inc = u.Type == "molotov" && team == 3, P = new[] { eye.X, eye.Y, eye.Z }, V = new[] { v.X, v.Y, v.Z } });
        Log("move: {n} throws its {t} as players do there ({k}, {s:P0} of throws there, blinded {b:F1}, damage {d:F0})", c.PlayerName, u.Type, key, u.Share, u.Blind, u.Dmg);
    }
}
