// Where a bot looks when it sees nobody (29/10, the user: "ce qui joue énormément sur définir les bots comme des cheaters,
// comme des humains ou comme l'IA de CS, c'est ... là où ils regardent sans voir des ennemis ... quand ils regardent à
// travers les murs là où t'es, c'est de la triche. Quand ils regardent complètement dos à là où les ennemis peuvent
// arriver ... on sait que c'est l'IA de CS ... base-toi sur toutes les analyses de toutes les démos ... sois cohérent").
// tools/look_model.py reads the demos: every 0.25 s, each player who saw no enemy, his 128 u cell and side, what he could
// know (an enemy on his radar, spotted by his team; an enemy heard: running within 1100 u, a shot within 2000 u; a smoke up
// within 1200 u; the bomb down), that knowledge's direction in 8 sectors, and where he looked: look/<map>.json keeps, for
// each, the yaw most players had there and their pitch. A bot on its way (css_scripted, tests) looks there: what its team
// knows of you decides (never where you are through a wall, only what the radar and the ears of its team give), its head
// turned like a player's (a quarter of the way a tick, 9 deg at most). No table for its place: the real player's own look.
using System.Numerics;
using System.Text.Json;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;

namespace CoachReplay;

public partial class CoachReplay
{
    string? lookMap;
    float lookCell = 128f, lookZ = 96f;
    readonly Dictionary<string, (int N, (float Yaw, float Pitch, int C)[] Bins)> lookTab = new();   // its most looked-at directions
    readonly Dictionary<string, int[]> dangerTab = new();   // a cell and side: where its players' killers stood (8 sectors), its deaths
    readonly Dictionary<int, Vector3> lookNow = new();   // each bot's head now (pitch, yaw)
    readonly Dictionary<int, (Vector3 Want, int T, string Know)> lookPick = new();   // where it chose to look, when, knowing what
    readonly Dictionary<string, int> lookUsed = new();   // this drill's looks by where they came from (the table's knowledge, or the demo's)
    int youShotAt = -100000; Vector3 youShotFrom;          // your last shot, for the ears of the bots

    void LookLoad()
    {
        var mp = Server.MapName;
        if (mp == lookMap) return;
        lookMap = mp; lookTab.Clear(); lookNow.Clear(); lookPick.Clear(); dangerTab.Clear();
        var fn = Path.Combine(Dir, "look", $"{mp}.json");
        if (!File.Exists(fn)) { Log("look: no table for {m}", mp); return; }
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(fn));
            var r = doc.RootElement;
            if (r.TryGetProperty("cell", out var ce)) lookCell = ce.GetSingle();
            if (r.TryGetProperty("zcell", out var ze)) lookZ = ze.GetSingle();
            foreach (var k in r.GetProperty("keys").EnumerateObject())
                lookTab[k.Name] = (k.Value[0].GetInt32(), k.Value[1].EnumerateArray().Select(b => (b[0].GetSingle(), b[1].GetSingle(), b[2].GetInt32())).ToArray());
            Log("look: {n} places read for {m}", lookTab.Count, mp);
            var dfn = Path.Combine(Dir, "danger", $"{mp}.json");   // tools/danger_util.py: where the killers stood
            if (File.Exists(dfn))
            {
                using var dd = JsonDocument.Parse(File.ReadAllText(dfn));
                foreach (var k in dd.RootElement.GetProperty("keys").EnumerateObject())
                    dangerTab[k.Name] = k.Value.EnumerateArray().Select(x => x.GetInt32()).ToArray();
                Log("look: {n} danger cells read for {m}", dangerTab.Count, mp);
            }
        }
        catch (Exception e) { Log("look: {m}", e.Message); }
    }

    // what this drill's looks came from, said once it is over (and cleared)
    void LookSay()
    {
        if (lookChk[0] > 0)   // its look's continuity this drill (29/10, the user's "on-off")
            Log("lookcheck: {n} ticks on its way, its eyes moved by another than the plugin {f} (over 10 deg {g}), turns over 5 deg {t}, picks {p}, held under 20 u/s on a way over 100 u/s {s}",
                lookChk[0], lookChk[1], lookChk[2], lookChk[3], lookChk[4], lookChk[5]);
        Array.Clear(lookChk);
        if (lookUsed.Count == 0) return;
        Log("look: {s}", string.Join(", ", lookUsed.OrderByDescending(k => k.Value).Select(k => $"{k.Key} {k.Value}")));
        lookUsed.Clear();
    }

    // a self-test's count of its look's continuity: ticks, moved by another (over 2 deg), by over 10 deg, turned over 5 deg
    // in a tick, new picks, held still while its way ran
    readonly int[] lookChk = new int[6];
    bool wayCmd = true;   // css_waycmd 0: a bot on its way keeps the game's own view in its command (to compare)

    void LookEvents()
    {
        RegisterEventHandler<EventWeaponFire>((e, _) =>
        {
            if (e.Userid is { IsValid: true, IsBot: false } u && u.PlayerPawn.Value?.AbsOrigin is { } o)
            { youShotAt = Server.TickCount; youShotFrom = new Vector3(o.X, o.Y, o.Z); }
            return HookResult.Continue;
        });
    }

    static int Sector(float dx, float dy) => (int)(((MathF.Atan2(dy, dx) * 180f / MathF.PI + 360f + 22.5f) % 360f) / 45f);

    // what its team knows of you, as the demos' players knew of their enemies (see the file's head)
    (string Know, int Sec) Knows(int slot, Track t, Vector3 at, CCSPlayerPawn? mePawn, List<Vector3> smokes)
    {
        var now = Server.TickCount;
        if (mePawn?.AbsOrigin is { } mo)
        {
            var me = new Vector3(mo.X, mo.Y, mo.Z);
            // on its radar: seen by one of its team in the last 2 s
            var dot = bots.Any(b => b.Value.Team == t.Team && sawYou.TryGetValue(b.Key, out var s) && now - s < 128);
            if (dot) return ("dot", Sector(me.X - at.X, me.Y - at.Y));
            var v = mePawn.AbsVelocity is { } av ? new Vector2(av.X, av.Y).Length() : 0f;
            if (v > 135f && Vector3.Distance(me, at) < 1100f) return ("heard", Sector(me.X - at.X, me.Y - at.Y));
            if (now - youShotAt < 96 && Vector3.Distance(youShotFrom, at) < 2000f) return ("heard", Sector(youShotFrom.X - at.X, youShotFrom.Y - at.Y));
        }
        var c4 = Utilities.FindAllEntitiesByDesignerName<CPlantedC4>("planted_c4").FirstOrDefault(x => x.IsValid && x.BombTicking && !x.HasExploded);
        if (c4?.AbsOrigin is { } co) return ("planted", Sector(co.X - at.X, co.Y - at.Y));
        Vector3? sm = null; var best = 1200f;
        foreach (var s in smokes) { var d = Vector3.Distance(s, at); if (d < best) { best = d; sm = s; } }
        if (sm is { } ss) return ("smoke", Sector(ss.X - at.X, ss.Y - at.Y));
        return ("none", -1);
    }

    // its eyes only (HoldAim would also stand it up: a crouched one stays crouched)
    static void SetEyes(CCSPlayerPawn pawn, Vector3 a)
    {
        if (pawn.EyeAngles is { } eye && (Math.Abs(eye.X - a.X) > 0.01f || Math.Abs(((eye.Y - a.Y + 540f) % 360f) - 180f) > 0.01f))   // its sway too (v7-v9: still half the time; real Ts 0.04 deg a tick at the median)
        { eye.X = a.X; eye.Y = a.Y; Utilities.SetStateChanged(pawn, "CCSPlayerPawn", "m_angEyeAngles"); }
    }

    // its head this tick: the table's look for its place and what its team knows, else the real player's (`demo`).
    // 29/10 (the user: "un endroit d'humain, puis ... ils se retournent en regardant le mur, puis ... au bon endroit ... il
    // faudrait un espèce de lerping ... une continuité logique ... pas qu'il y ait un espèce de on-off"): one look, held like
    // a player's and turned to like a hand. It changed every 128 u cell (each one's best direction, or the real player's
    // where the table had nothing, snapped to at once), and as its teammates' views moved
    Vector3 LookFor(int slot, Track t, Vector3 at, Vector3 demo, CCSPlayerPawn? mePawn, List<Vector3> smokes)
    {
        if (lookTab.Count == 0) return demo;
        var now = Server.TickCount;
        var side = t.Team == 2 ? "T" : "CT";
        var cell = $"{side}|{(int)MathF.Floor(at.X / lookCell)}|{(int)MathF.Floor(at.Y / lookCell)}|{(int)MathF.Floor(at.Z / lookZ)}";
        var (know, sec) = Knows(slot, t, at, mePawn, smokes);
        var bpw = Utilities.GetPlayerFromSlot(slot)?.PlayerPawn.Value;
        var cur0 = lookNow.TryGetValue(slot, out var h) ? h : bpw?.EyeAngles is { } ea ? new Vector3(ea.X, ea.Y, 0f) : demo;
        var hasPick = lookPick.TryGetValue(slot, out var lp);
        var news = $"{know}|{sec}";
        (int N, (float Yaw, float Pitch, int C)[] Bins) l;
        // the behaviour model first (Behavior.cs): the finest case of its place, its side's info, its weapon, the numbers
        if (bpw != null && BehCaseFor(t.Team, bpw, at, out var blv) is { Look.Length: > 0 } bc)
        { l = (bc.N, bc.Look); behUsed[$"look {blv}"] = behUsed.GetValueOrDefault($"look {blv}") + 1; }
        else if (lookTab.TryGetValue($"{cell}|{know}|{sec}", out l)) lookUsed[know] = lookUsed.GetValueOrDefault(know) + 1;
        else if (lookTab.TryGetValue($"{cell}|none|-1", out l)) lookUsed[know + ">none"] = lookUsed.GetValueOrDefault(know + ">none") + 1;
        else
        {   // nothing there: its look kept 2 s, then the real player's, turned to
            lookUsed["demo"] = lookUsed.GetValueOrDefault("demo") + 1;
            var keep = hasPick && now - lp.T < 128;
            if (!keep) lookPick[slot] = (demo, now, news);
            return Turn(slot, cur0, keep ? lp.Want : demo);
        }
        // 29/10, the user: "là où on regarde, en fonction de là où nos alliés regardent, là où nos alliés sont ... là où les gens
        // se font le plus tuer": among the directions players looked at there, each weighed by how often, more where the
        // killers of the players who died there stood, less where a teammate near (900 u) looks already
        dangerTab.TryGetValue(cell, out var dz);
        float? runDir = bpw?.AbsVelocity is { } rv && new Vector2(rv.X, rv.Y).Length() > 150f ? MathF.Atan2(rv.Y, rv.X) * 180f / MathF.PI : null;
        var mates = Utilities.GetPlayers().Where(p => p is { IsValid: true, PawnIsAlive: true } && p.TeamNum == t.Team && p.Slot != slot)
            .Select(p => p.PlayerPawn.Value).Where(pp => pp?.AbsOrigin != null && pp.EyeAngles != null
                && Vector3.Distance(new Vector3(pp.AbsOrigin!.X, pp.AbsOrigin.Y, pp.AbsOrigin.Z), at) < 900f).Select(pp => pp!.EyeAngles!.Y).ToList();
        var bestW = -1f; var want = demo; var pickW = 0f;
        // running: never more than 100 deg off its way (30/10, v25's 1,437 s: a third of its running looking back, two thirds of
        // that at you through walls 1,460 u off, your shots heard; real Ts 38 deg at the median, 101 at the 90th). Weighed down
        // a tenth, the look back of its cell won still where players there ran the other way
        static float Off(float a, float b) => MathF.Abs(((a - b + 540f) % 360f) - 180f);
        foreach (var b in l.Bins)
        {
            if (runDir is { } rd0 && Off(b.Yaw, rd0) > 100f) continue;
            var w = b.C / (float)Math.Max(1, l.N);
            if (dz is { Length: 9 } && dz[8] > 0)
                w *= 1f + 1.5f * dz[(int)(((b.Yaw + 360f + 22.5f) % 360f) / 45f)] / dz[8];
            if (mates.Any(my => MathF.Abs(((my - b.Yaw + 540f) % 360f) - 180f) < 25f)) w *= 0.45f;
            var bw = new Vector3(b.Pitch, b.Yaw, 0f);
            if (hasPick && AngDiff(lp.Want, bw).Length() < 20f) pickW = Math.Max(pickW, w);   // its look is one of them
            if (w > bestW) { bestW = w; want = bw; }
        }
        // its look kept 0.75 s at least, then left for a clearly better one (1.25 times its weight here); for news (what its
        // team knows changed: a sight, a sound) at once, a quarter of a second after its last change at the soonest
        var fresh = hasPick && lp.Know != news && now - lp.T >= 16;
        // none ahead of it: the real player's own if it is, else its way's direction with the first one's pitch
        if (bestW < 0f && runDir is { } rd1 && Off(demo.Y, rd1) > 100f) want = new Vector3(l.Bins.Length > 0 ? l.Bins[0].Pitch : 0f, rd1, 0f);
        // its look kept unless it ran round a corner and it is behind it now
        var behind = hasPick && runDir is { } rd2 && Off(lp.Want.Y, rd2) > 100f;
        if (hasPick && !fresh && !behind && (now - lp.T < 64 || bestW < 1.4f * pickW)) want = lp.Want;   // v8: 6 flicks a minute, real Ts 3
        else { lookPick[slot] = (want, now, news); if (selftest && hasPick) lookChk[4]++; }
        return Turn(slot, cur0, want);
    }

    // a hand's turn onto a look: a fifth of the way each tick, 5 deg a tick at most (320 deg/s; it was 9 deg, 576 deg/s), 8
    // for a big one (real Ts' fastest: 487 deg/s, v4's 320); still, a head is never quite still (v4's half of the time,
    // real Ts' 2.8 deg/s at the median): a slow sway, its own a bot
    Vector3 Turn(int slot, Vector3 cur0, Vector3 want)
    {
        var d = AngDiff(cur0, want);
        var n = d.Length();
        var step = n <= 0.4f ? n : Math.Clamp(n * 0.2f, 0.4f, n > 45f ? 8f : 5f);
        var next = n > 0f ? cur0 + d * (step / n) : cur0;
        var tk = Server.TickCount;
        next = new Vector3(Math.Clamp(next.X, -89f, 89f), ((next.Y + 540f) % 360f) - 180f, 0f);
        if (selftest && step > 5.01f) lookChk[3]++;
        lookNow[slot] = next;
        return next + Sway(slot, tk);   // shown with its sway, kept without it
    }

    // a head's sway, 1.5 deg each side over 2-3 s, 0.6 up and down, its own a bot, shown over its look (lab 24: added into
    // the look the next tick's turn took it back, 0.003 deg a tick were left; real Ts' heads 0.04 deg a tick at the median)
    static Vector3 Sway(int slot, int tk, float k = 1f) =>
        new(0.6f * k * MathF.Sin(tk * 0.031f + 2f * slot), 1.5f * k * MathF.Sin(tk * 0.045f + slot), 0f);
}
