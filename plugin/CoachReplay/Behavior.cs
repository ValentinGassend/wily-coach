// The behaviour model's tables (29/10, the user: "évaluer ... le positionnement du viseur de chacun ... quelle information a ce
// joueur, de quand ça date, quelle information nouvelle il a, et pourquoi il agit comme ça ... définir une action à faire en
// fonction de chaque événement et en fonction de chaque combinaison"). tools/behavior_model.py read every whole demo of the
// base: for each player every 0.25 s, his place, what his team knew of the enemies (the last sight by one of them, the last
// footstep or shot a teammate could hear: its kind, its age, its direction), his weapon, the numbers, and what he did: where
// he looked and why, how he moved and his real way. behavior/<map>.json keeps it at three levels: the place; the place and
// that info; the place, the info, the weapon and the numbers. Here each side's info is kept the same way, from the game (the
// spotting of its players, the footsteps and shots its players can hear), and a bot (css_scripted) looks and moves as the
// finest case with enough players in it says; none: the older tables (Look.cs, Move.cs).
using System.Numerics;
using System.Text.Json;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;

namespace CoachReplay;

public partial class CoachReplay
{
    string? behMap;
    float behCell = 128f, behZ = 96f;
    sealed class BehCase
    {
        public int N;
        public (float Yaw, float Pitch, int C)[] Look = Array.Empty<(float, float, int)>();
        public string Why = "", Mv = "h";
        public float MvShare;
        public Vector3[] Way = Array.Empty<Vector3>();
    }
    readonly Dictionary<string, BehCase> behTab = new();
    // each side's knowledge of the other: an enemy's slot -> (tick, where) of its last sight by one of the side / its last
    // sound one of the side could hear
    readonly Dictionary<int, Dictionary<int, (int T, Vector3 P)>> sideSeen = new() { [2] = new(), [3] = new() };
    readonly Dictionary<int, Dictionary<int, (int T, Vector3 P)>> sideHeard = new() { [2] = new(), [3] = new() };
    readonly Dictionary<string, int> behUsed = new();

    void BehLoad()
    {
        var mp = Server.MapName;
        if (mp == behMap) return;
        behMap = mp; behTab.Clear();
        var fn = Path.Combine(Dir, "behavior", $"{mp}.json");
        if (!File.Exists(fn)) { Log("behavior: no table for {m}", mp); return; }
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(fn));
            var r = doc.RootElement;
            if (r.TryGetProperty("cell", out var ce)) behCell = ce.GetSingle();
            if (r.TryGetProperty("zcell", out var ze)) behZ = ze.GetSingle();
            foreach (var k in r.GetProperty("keys").EnumerateObject())
            {
                var v = k.Value;
                behTab[k.Name] = new BehCase
                {
                    N = v.GetProperty("n").GetInt32(),
                    Look = v.GetProperty("look").EnumerateArray().Select(b => (b[0].GetSingle(), b[1].GetSingle(), b[2].GetInt32())).ToArray(),
                    Why = v.GetProperty("why").GetString() ?? "",
                    Mv = v.GetProperty("mv").GetString() ?? "h",
                    MvShare = v.GetProperty("mv_share").GetSingle(),
                    Way = v.GetProperty("way").EnumerateArray().Select(p => new Vector3(p[0].GetSingle(), p[1].GetSingle(), p[2].GetSingle())).ToArray(),
                };
            }
            Log("behavior: {n} cases read for {m}", behTab.Count, mp);
        }
        catch (Exception e) { Log("behavior: {m}", e.Message); }
    }

    // the game's footsteps this drill, the bots' and yours (30/10: running bots unheard? said in the log at each drill's end)
    int stepsBots, stepsYou, stepsOurs;

    // the bots' steps, played by the plugin (30/10, his review: "s'il n'est pas en shift ... qu'il court pour de vrai, j'aimerais
    // l'entendre pour de vrai"; round 13: the game's own footsteps 1 in 90 s for bots moved by their speed, none of their legs'
    // input): a bot on the ground running over a walk's speed (150 u/s), not crouched, no Shift, a step every 0.3 s (0.35 under
    // 200 u/s), the game's sound of its side (T_/CT_Default.StepLeft, the game's soundevents); none where the game stepped
    // it itself in the last 0.3 s
    readonly Dictionary<int, int> gameStepAt = new();
    readonly Dictionary<int, int> ourStepAt = new();

    void StepSounds()
    {
        var now = Server.TickCount;
        foreach (var sl in bots.Keys)
        {
            if (Utilities.GetPlayerFromSlot(sl) is not { IsValid: true, IsBot: true, PawnIsAlive: true } c || c.PlayerPawn.Value is not { } pw) continue;
            if ((pw.Flags & (uint)CounterStrikeSharp.API.Modules.Utils.PlayerFlags.FL_ONGROUND) == 0 || pw.IsWalking) continue;
            if (pw.MovementServices != null && new CCSPlayer_MovementServices(pw.MovementServices.Handle).Ducked) continue;
            var v = pw.AbsVelocity is { } av ? MathF.Sqrt(av.X * av.X + av.Y * av.Y) : 0f;
            if (v < 150f) continue;
            var every = v >= 200f ? 19 : 22;   // ticks
            // ticks start again at 0 with each map: a step of the map before is none (31/10, Nuke: none played at all after Fachwerk)
            int Last(Dictionary<int, int> d) { var v = d.GetValueOrDefault(sl, -1000); return v > now ? -1000 : v; }
            if (now - Last(gameStepAt) < every || now - Last(ourStepAt) < every) continue;
            ourStepAt[sl] = now;
            stepsOurs++;
            try { pw.EmitSound(pw.TeamNum == 2 ? "T_Default.StepLeft" : "CT_Default.StepLeft"); }
            catch (Exception) { }
        }
    }

    void BehEvents()
    {
        RegisterEventHandler<EventPlayerFootstep>((e, _) =>
        {
            BehSound(e.Userid, 1100f);
            if (e.Userid is { IsValid: true } u) { if (u.IsBot) { stepsBots++; gameStepAt[u.Slot] = Server.TickCount; } else stepsYou++; }
            return HookResult.Continue;
        });
        RegisterEventHandler<EventWeaponFire>((e, _) => { BehSound(e.Userid, 2000f); return HookResult.Continue; });
    }

    // a sound made by `who`: heard by the other side when one of its living players is within `range`
    void BehSound(CCSPlayerController? who, float range)
    {
        if (who is not { IsValid: true } || who.TeamNum < 2 || who.PlayerPawn.Value?.AbsOrigin is not { } o) return;
        var at = new Vector3(o.X, o.Y, o.Z);
        var other = who.TeamNum == 2 ? 3 : 2;
        if (Utilities.GetPlayers().Any(p => p is { IsValid: true, PawnIsAlive: true } && p.TeamNum == other && p.PlayerPawn.Value?.AbsOrigin is { } po
                && Vector3.Distance(new Vector3(po.X, po.Y, po.Z), at) < range))
            sideHeard[other][who.Slot] = (Server.TickCount, at);
    }

    // each tick: every player spotted by one of the other side is seen by that side
    void BehSightTick()
    {
        if (!scripted || behTab.Count == 0) return;
        var now = Server.TickCount;
        var players = Utilities.GetPlayers().Where(p => p is { IsValid: true, PawnIsAlive: true } && p.TeamNum >= 2).ToList();
        foreach (var p in players)
        {
            var pp = p.PlayerPawn.Value;
            if (pp?.AbsOrigin is not { } o) continue;
            var mk = pp.EntitySpottedState.SpottedByMask;
            uint m0 = mk[0], m1 = mk[1];
            var other = p.TeamNum == 2 ? 3 : 2;
            if (players.Any(q => q.TeamNum == other && q.Slot < 64 && ((q.Slot < 32 ? m0 : m1) & (1u << (q.Slot % 32))) != 0))
                sideSeen[other][p.Slot] = (now, new Vector3(o.X, o.Y, o.Z));
        }
    }

    // a side's info as the model keys it: "none", or its freshest sight or sound of a living enemy: "<seen|heard><age>|<sector>"
    (string Key, Vector3? At) BehInfo(int team, Vector3 at)
    {
        var now = Server.TickCount;
        var other = team == 2 ? 3 : 2;
        var living = Utilities.GetPlayers().Where(p => p is { IsValid: true, PawnIsAlive: true } && p.TeamNum == other).Select(p => p.Slot).ToHashSet();
        (string Kind, int T, Vector3 P)? best = null;
        foreach (var (kind, book) in new[] { ("seen", sideSeen[team]), ("heard", sideHeard[team]) })
            foreach (var (s, x) in book)
                if (living.Contains(s) && (best == null || x.T > best.Value.T)) best = (kind, x.T, x.P);
        if (best is not { } b) return ("none", null);
        var dt = now - b.T;
        var age = dt <= 64 ? 0 : dt <= 192 ? 1 : dt <= 512 ? 2 : dt <= 1280 ? 3 : -1;
        if (age < 0) return ("none", null);
        return ($"{b.Kind}{age}|{Sector(b.P.X - at.X, b.P.Y - at.Y)}", b.P);
    }

    static string WClass(CCSPlayerPawn pw)
    {
        var n = pw.WeaponServices?.ActiveWeapon.Value?.DesignerName ?? "";
        return n is "weapon_awp" or "weapon_ssg08" or "weapon_g3sg1" or "weapon_scar20" ? "awp"
             : n is "weapon_ak47" or "weapon_m4a1" or "weapon_m4a1_silencer" or "weapon_galilar" or "weapon_famas" or "weapon_aug" or "weapon_sg556" ? "rifle" : "other";
    }

    // the finest case for a bot there now: the place, its info, its weapon and the numbers; then the place and its info; then
    // the place
    BehCase? BehCaseFor(int team, CCSPlayerPawn pw, Vector3 at, out string level)
    {
        level = "";
        if (behTab.Count == 0) return null;
        var side = team == 2 ? "T" : "CT";
        var cell = $"{side}|{(int)MathF.Floor(at.X / behCell)}|{(int)MathF.Floor(at.Y / behCell)}|{(int)MathF.Floor(at.Z / behZ)}";
        var (ik, _) = BehInfo(team, at);
        var adv = Math.Sign(Alive(team) - Alive(team == 2 ? 3 : 2));
        if (behTab.TryGetValue($"L2|{cell}|{ik}|{WClass(pw)}|{adv}", out var c)) { level = "L2"; return c; }
        if (behTab.TryGetValue($"L1|{cell}|{ik}", out c)) { level = "L1"; return c; }
        if (behTab.TryGetValue($"L0|{cell}", out c)) { level = "L0"; return c; }
        return null;
    }

    void BehSay()
    {
        if (behUsed.Count == 0) return;
        Log("behavior: {s}", string.Join(", ", behUsed.OrderByDescending(k => k.Value).Select(k => $"{k.Key} {k.Value}")));
        behUsed.Clear();
    }
}
