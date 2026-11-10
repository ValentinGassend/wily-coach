// The coach's replays: a situation of your own demo played again. The bots follow exactly the recorded paths of the
// other players (where they went, where they looked) and fight on their own once they have seen you for a human
// reaction time; you take your own spot (actor) or watch it all (spec: a bot plays your spot too). A bot killed in the
// demo dies at the same moment only if its killer is still alive here (you changed the story: it lives on); one you
// killed in the demo waits for you at the end of its path. Bots never hurt each other. The bomb is planted where and when
// it was (already ticking when the situation starts after the plant), each one has the defuse kit he had, and the
// dead drop their guns. Each try is appended to coach/results.jsonl.
//
// Commands (console, rcon, or chat with !): css_replay <id> [actor|spec], css_r (again), css_n / css_p (next,
// previous of this map), css_spec (switch actor/spec), css_list, css_diff <0-3>, css_stop; css_replay <id> <mode> <0-3>
// also sets the bots' level.
using System.Numerics;
using System.Text.Json;
using System.Text.Json.Serialization;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Commands;
using CounterStrikeSharp.API.Modules.Cvars;
using CounterStrikeSharp.API.Modules.Memory;
using CounterStrikeSharp.API.Modules.Memory.DynamicFunctions;
using CounterStrikeSharp.API.Modules.Utils;
using Microsoft.Extensions.Logging;
using CVector = CounterStrikeSharp.API.Modules.Utils.Vector;

namespace CoachReplay;

public class Track
{
    [JsonPropertyName("sid")] public string Sid { get; set; } = "";
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("team")] public int Team { get; set; }
    [JsonPropertyName("me")] public bool Me { get; set; }
    [JsonPropertyName("hp")] public int Hp { get; set; } = 100;
    [JsonPropertyName("armor")] public int Armor { get; set; }
    [JsonPropertyName("helmet")] public bool Helmet { get; set; }
    [JsonPropertyName("weapons")] public List<string> Weapons { get; set; } = new();
    [JsonPropertyName("active")] public string? Active { get; set; }
    [JsonPropertyName("path")] public float[] Path { get; set; } = Array.Empty<float>();
    [JsonPropertyName("death")] public int Death { get; set; } = -1;
    [JsonPropertyName("killer")] public string Killer { get; set; } = "";
    [JsonPropertyName("kw")] public string KillWeapon { get; set; } = "";   // the gun it was killed with in the match
    [JsonPropertyName("hold")] public bool Hold { get; set; }   // stays on its spot (aim targets): only its aim is its own
    [JsonIgnore] public bool Still { get; set; }   // a prefire's, a wallbang's or a flick's target: its body and its aim held, never firing (06/10)
    [JsonIgnore] public bool Duck { get; set; }   // held crouched, like the players who hold that angle
    [JsonIgnore] public bool Strafe { get; set; }   // an aim map's strafing target: moved left and right by the session
    [JsonPropertyName("places")] public List<JsonElement> Places { get; set; } = new();   // your route in the match: [frame, place]
    [JsonIgnore] public float Start { get; set; }   // the frame its path starts at (a defense's attacker: when it spawned)
    [JsonPropertyName("at")] public string? At { get; set; }   // its place at the start
    [JsonPropertyName("kit")] public bool Kit { get; set; }   // a CT's defuse kit
    [JsonIgnore] public List<Nade> TrackNades { get; set; } = new();   // a defense's attacker: the grenades of the real hit it walks
    [JsonIgnore] public int NadeNext { get; set; }
    [JsonIgnore] public bool Runner { get; set; }   // a timing smoke's rusher: runs its way, never stops to fight (07/10)
    [JsonIgnore] public float Warp { get; set; }   // frames its way's clock waited for it (it couldn't run the real player's speed)
    [JsonIgnore] public List<(int F, float Rise)>? Jumps { get; set; }   // its way's jumps (CoachReplay.JumpsOf), for JumpsFor
    [JsonIgnore] public float[]? JumpsFor { get; set; }
    [JsonIgnore] public int JumpDone { get; set; } = -1;   // the last of them it jumped (or let go)
    [JsonIgnore] public float SpawnF { get; set; }   // the frame of its way it was put on (a wave's attacker: further on when its start was taken)
    [JsonPropertyName("duck")] public int[] DuckFrames { get; set; } = Array.Empty<int>();   // the frames the real player was crouched at
    [JsonIgnore] HashSet<int>? duckSet;
    public bool DuckAt(int i) => (duckSet ??= new HashSet<int>(DuckFrames)).Contains(i);
    // another bot's way taken (a defense's attacker to your zone, 29/10): its points, its crouches, its jumps; no grenade, no death
    public void TakeWay(float[] path)
    {
        Path = path; DuckFrames = Array.Empty<int>(); duckSet = null; Jumps = null; JumpsFor = null; JumpDone = -1;
        TrackNades = new(); NadeNext = 0; Death = -1; Killer = "";
    }
    public int Frames => Path.Length / 5;
}

public class Bomb
{
    [JsonPropertyName("f")] public int F { get; set; }   // the frame it is planted at (0: already ticking at the start)
    [JsonPropertyName("pos")] public float[] Pos { get; set; } = new float[3];
    [JsonPropertyName("site")] public int Site { get; set; }   // 0 A, 1 B
    [JsonPropertyName("left")] public float Left { get; set; } = 40;   // seconds to the explosion once it is down here
    [JsonPropertyName("by")] public string By { get; set; } = "";   // the planter
}

public class Nade
{
    [JsonPropertyName("f")] public int F { get; set; }
    [JsonPropertyName("type")] public string Type { get; set; } = "";
    [JsonPropertyName("by")] public string By { get; set; } = "";
    [JsonPropertyName("inc")] public bool Inc { get; set; }
    [JsonPropertyName("life")] public int Life { get; set; }
    [JsonPropertyName("p")] public float[] P { get; set; } = new float[3];
    [JsonPropertyName("v")] public float[] V { get; set; } = new float[3];
}

public class Scenario
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("map")] public string Map { get; set; } = "";
    [JsonPropertyName("kind")] public string Kind { get; set; } = "death";
    [JsonPropertyName("title")] public string Title { get; set; } = "";
    [JsonPropertyName("rate")] public int Rate { get; set; } = 64;
    [JsonPropertyName("step")] public int Step { get; set; } = 2;
    [JsonPropertyName("key")] public int Key { get; set; }
    [JsonPropertyName("team")] public int Team { get; set; }
    [JsonPropertyName("players")] public List<Track> Players { get; set; } = new();
    [JsonPropertyName("nades")] public List<Nade> Nades { get; set; } = new();
    [JsonPropertyName("danger")] public string Danger { get; set; } = "";
    [JsonPropertyName("goal")] public string Goal { get; set; } = "";
    [JsonPropertyName("bomb")] public Bomb? Bomb { get; set; }   // planted in the window (or before it)
    [JsonPropertyName("plant")] public string Plant { get; set; } = "";   // the bomb in the real round, said on screen
    [JsonPropertyName("line")] public List<float[]> Line { get; set; } = new();   // your way in the match, drawn on the ground
    [JsonPropertyName("clock")] public float Clock { get; set; }   // the real round's clock at the start (s left; 0: unknown)
    // who died in the round before the window, where (06/10: "il faut savoir où mes alliés meurent pour savoir où sont les
    // ennemis"), and where the players went before it (the doors and the vents they opened or broke)
    [JsonPropertyName("dead")] public List<Dead> Dead { get; set; } = new();
    [JsonPropertyName("trail")] public List<float[]> Trail { get; set; } = new();
    // where it happens (07/10): its place's outline on the ground, the gold line only up to it; play it your way there
    [JsonPropertyName("zone_name")] public string ZoneName { get; set; } = "";
    [JsonPropertyName("zone_at")] public float[]? ZoneAt { get; set; }
    [JsonPropertyName("zone_poly")] public List<float[]> ZonePoly { get; set; } = new();
    [JsonPropertyName("lost")] public string Lost { get; set; } = "";   // lost in advance (no kit, no time): skipped
}

public class Dead
{
    [JsonPropertyName("pos")] public float[] Pos { get; set; } = new float[3];
    [JsonPropertyName("team")] public int Team { get; set; }
    [JsonPropertyName("at")] public string At { get; set; } = "";
    [JsonPropertyName("clock")] public string Clock { get; set; } = "";   // the round's clock when it happened (1:23)
}

public partial class CoachReplay : BasePlugin
{
    public override string ModuleName => "CoachReplay";
    public override string ModuleVersion => "1.0";
    public override string ModuleAuthor => "wily-coach";

    string Dir => System.IO.Path.GetFullPath(System.IO.Path.Combine(ModuleDirectory, "..", "..", "..", "..", "coach"));
    Scenario? cur;
    string mode = "actor";
    string phase = "idle";   // idle, setup, countdown, live, done
    readonly Dictionary<int, Track> bots = new();   // controller slot -> track
    readonly HashSet<string> gone = new();   // tracks dead here
    readonly HashSet<int> free = new();   // slots whose path is over: the bot plays on its own
    readonly Dictionary<int, int> contact = new();   // ticks a scripted bot has seen you: then it plays on its own, like a player
    readonly Dictionary<int, int> engaged = new();   // the tick a scripted bot started fighting you: it keeps the real player's moves 1.5 s
    readonly Dictionary<int, int> sawYou = new();   // the last tick each bot had you in sight (the game's spotting): its bullets hurt you only then
    const int SawTicks = 96;
    const int EngageTicks = 96;
    int t0, countdownEnd, kills, dmg, generation, lastBeat, nextNade;
    bool awaitRestart;
    int emptyTries;   // a drill set up again because its bots did not come
    int refusedFor = -1;   // the setup (generation) whose refused bots got a round restart
    CCSGameRules? rules;   // the center text's blink fix (OnTick)
    const int MinHp = 40;   // a situation: at least that many HP (2 HP in the match: dead before you could do anything)
    // a bot on its recorded path keeps the real player's aim this long after it has seen you, then fights on its own: a
    // player's reaction time (04/10, "as if they had lag": they used to aim at you the very tick they saw you)
    const int ReactTicks = 13;
    // the aim map's duels: the ticks a target must have seen you before its shots hurt (0.47 s at Easy to 0.23 s at Expert)
    int DuelReact => BotLv switch { 0 => 30, 1 => 24, 2 => 19, _ => 15 };
    // a bot on its path notices you this close, or when you shoot this close (a silenced gun: half): it then plays on
    // its own (04/10: "expert bots that don't even look at me")
    const float Near = 350f, OnYou = 128f, Earshot = 1200f;
    const string NullModel = "models/props_doors/null.vmdl";   // an empty model of the game (the grenade camera's)
    bool bombLive, bombDone;   // a situation: the bomb is down here / the demo's plant is done (or will not be)
    int protectUntil;   // a defense: you just came back, nothing hurts you until this tick
    int defDeadAt = -1;   // a defense: the tick you were found dead with the drill not knowing it (SessionTick)
    bool humanDead, traded;   // a situation: you died, and your killer died within 3 s
    int tradeKiller = -1, tradeUntil;
    string? builtFor;   // the situation the bots on the server were made for
    int difficulty = 2;
    // the bots' own level under the session's, for the measure only (css_botlevel, console; 29/10, the user: "mesurer avec
    // des bots plus faciles que pour toi"): the drills stay the session's (its format, its waves), the bots fight at it
    int botLevel = -1;
    int BotLv => botLevel >= 0 ? botLevel : difficulty;
    double devSum; int devN;   // how far the bots drift from their path between two ticks (checked in spec mode)
    // CSmokeGrenadeProjectile::Create(origin, angles, velocity, angular impulse, thrower, item definition, team): a smoke made
    // any other way never pops. Found in this server's server.dll (unique); null after a game update that moved it: no smokes
    // 23/10, CS2 1.41.9.2: the function compiled anew (its frame set up another way), the old signature found nowhere and
    // no smoke thrown by a bot any more (the guided self-test missed every one): the newest first, then the older ones
    static readonly string[] SmokeSigs = {
        "48 89 5C 24 ? 48 89 6C 24 ? 48 89 74 24 ? 57 41 56 41 57 48 83 EC ? 48 8B B4 24 ? ? ? ? 4D 8B F8 4C 8B C2",
        "48 8B C4 48 89 58 ? 48 89 68 ? 48 89 70 ? 57 41 56 41 57 48 81 EC ? ? ? ? 48 8B B4 24 ? ? ? ? 4D 8B F8 4C 8B C2" };
    MemoryFunctionWithReturn<nint, nint, nint, nint, nint, int, int, nint>? smokeCreate;
    // CHEGrenadeProjectile::Create(origin, angles, velocity, angular impulse, thrower, item definition): sets its fuse and think
    // CBasePlayerController::OnSimulateUserCommands(controller): runs a player's queued commands (its "RunCommand" scope),
    // found by its strings in 1.41.9.2's server.dll (28/10: the bots' own commands, the user's "vrais joueurs")
    [System.Runtime.InteropServices.DllImport("kernel32.dll")]
    static extern nint VirtualQuery(nint addr, out MemInfo info, nint len);
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    struct MemInfo { public nint Base, AllocBase; public uint AllocProtect; public nint Size; public uint State, Protect, Type; }
    // memory the process may read (committed, not a guard page, a read right): a pointer checked before it is followed
    static bool Readable(nint a, int len)
    {
        if (a < 0x10000) return false;
        if (VirtualQuery(a, out var m, System.Runtime.InteropServices.Marshal.SizeOf<MemInfo>()) == 0) return false;
        if (m.State != 0x1000 || (m.Protect & 0x100) != 0 || (m.Protect & 0x66) == 0) return false;   // MEM_COMMIT, PAGE_GUARD, R/RW/RX/RWX
        return a + len <= m.Base + m.Size;
    }
    // the game's own server.dll (csgo/bin/win64; Metamod's stub has the same name, 28/10 23:30)
    static nint GameServerDll() => System.Diagnostics.Process.GetCurrentProcess().Modules.Cast<System.Diagnostics.ProcessModule>()
        .FirstOrDefault(m => m.ModuleName.Equals("server.dll", StringComparison.OrdinalIgnoreCase)
                             && (m.FileName ?? "").Contains(System.IO.Path.Combine("csgo", "bin", "win64"), StringComparison.OrdinalIgnoreCase))?.BaseAddress ?? 0;
    static long Rd64(nint a) => System.Runtime.InteropServices.Marshal.ReadInt64(a);
    static int Rd32(nint a) => System.Runtime.InteropServices.Marshal.ReadInt32(a);
    const string SimCmdSig = "40 55 53 56 57 41 55 41 56 48 8D AC 24 08 F9 FF FF 48 81 EC F8 07 00 00 4C 8B F1 48 C7 44 24 48 ? ? ? ? 48 8D 1D ? ? ? ?";
    const string HeSig = "48 89 5C 24 ? 48 89 6C 24 ? 48 89 74 24 ? 57 48 83 EC 50 48 8B AC 24 ? ? ? ? 49 8B F8 4C 8B C2 0F 29 74 24 ? 48 8B D1 0F 29 7C 24";
    MemoryFunctionWithReturn<nint, nint, nint, nint, nint, int, nint>? heCreate;
    // CMolotovProjectile::Create(origin, angles, velocity, angular impulse, thrower, item definition: 46 molotov, 48 incendiary)
    const string MolotovSig = "48 8B C4 48 89 58 ? 48 89 70 ? 48 89 78 ? 4C 89 40 ? 55 41 54 41 55 41 56 41 57 48 8D 6C 24 ? 48 81 EC ? ? ? ? 45 33 FF";
    MemoryFunctionWithReturn<nint, nint, nint, nint, nint, int, nint>? molotovCreate;

    public override void Load(bool hotReload)
    {
        loadedAt = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        Directory.CreateDirectory(System.IO.Path.Combine(Dir, "scenarios"));
        StartIo();
        foreach (var sig in SmokeSigs)
        {
            try { smokeCreate = new(sig); Log("smokes: signature {i} of {n}", Array.IndexOf(SmokeSigs, sig) + 1, SmokeSigs.Length); break; }
            catch (Exception e) { smokeCreate = null; Log("no smokes with signature {i}: {m}", Array.IndexOf(SmokeSigs, sig) + 1, e.Message); }
        }
        try { heCreate = new(HeSig); } catch (Exception e) { heCreate = null; Log("no HE: {m}", e.Message); }
        try { molotovCreate = new(MolotovSig); } catch (Exception e) { molotovCreate = null; Log("no molotov: {m}", e.Message); }
        RegisterListener<Listeners.OnTick>(OnTick);
        CombatLoad();   // css_scripted: bots fighting by the plugin's hand (Combat.cs, tests)
        BotRecLoad();   // css_botrec: every player of a live drill to a file (BotRec.cs, tests)
        LookEvents();   // your shots, heard by the bots (Look.cs)
        MoveEvents();   // every player's shots, heard by the other side (Move.cs)
        BehEvents();   // footsteps and shots each side hears (Behavior.cs)
        RegisterListener<Listeners.OnServerPrecacheResources>(m => m.AddResource(NullModel));
        RegisterListener<Listeners.OnMapStart>(mapName =>
        {
            rules = null;
            // a drill of another map left from an ended session: forgotten, not played on this one (03/11, round 18: Anubis's
            // boost "retried" on Ancient after the change, its defense session never got a drill started)
            if (sess == null && cur != null && !string.IsNullOrEmpty(cur.Map) && !string.Equals(cur.Map, mapName, StringComparison.OrdinalIgnoreCase))
            {
                Log("map {m}: {d} of {o} forgotten", mapName, cur.Id, cur.Map);
                cur = null; drill = null;
            }
            phase = cur != null || sess != null ? "setup" : "idle";
            AddTimer(4f, () => { Server.ExecuteCommand("sv_hibernate_when_empty 0"); if (sess != null) SessionResume(); else if (cur != null) Setup(); });
        });
        RegisterEventHandler<EventRoundStart>(OnRoundStart);
        RegisterEventHandler<EventPlayerDeath>(OnDeath);
        // the bots' scripted deaths (a target waiting for its turn, a death of the demo) stay out of your kill feed
        RegisterEventHandler<EventPlayerDeath>((e, info) =>
        {
            if (cur != null && e.Userid is { IsValid: true, IsBot: true } v && (e.Attacker is not { IsValid: true } || e.Attacker.Slot == v.Slot))
                info.DontBroadcast = true;
            return HookResult.Continue;
        }, HookMode.Pre);
        RegisterEventHandler<EventPlayerHurt>(OnHurt);
        // your bullets as the server has them, for the real-client test's aim (26/10: its shots missed 3 to 6 times in a row
        // at 500-850 u): where each one went against the nearest enemy head on its line, and your hits (bots_live.json)
        RegisterEventHandler<EventBulletImpact>((e, _) => { MeImpact(e); return HookResult.Continue; });
        // a vent shot through breaks (29/10, the user on Cache: "même si tu tires à travers, elle est supposée se casser ... et
        // là elle se casse jamais"): an impact within 48 u of a whole one
        RegisterEventHandler<EventBulletImpact>((e, _) =>
        {
            var at = new Vector3(e.X, e.Y, e.Z);
            foreach (var v in Utilities.FindAllEntitiesByDesignerName<CBaseEntity>("prop_dynamic"))
                if (v.IsValid && v.Health > 0 && v.AbsOrigin is { } vo && Vector3.Distance(at, new Vector3(vo.X, vo.Y, vo.Z)) < 48f
                    && ((v.Entity?.Name ?? "") + (v.CBodyComponent?.SceneNode?.GetSkeletonInstance()?.ModelState.ModelName ?? "")).Contains("vent", StringComparison.OrdinalIgnoreCase))
                { v.AcceptInput("Break"); Log("broken by a bullet: a vent at {x:F0} {y:F0} {z:F0}", vo.X, vo.Y, vo.Z); }
            return HookResult.Continue;
        });
        RegisterEventHandler<EventPlayerHurt>((e, _) =>
        {
            if (e.Attacker is { IsValid: true, IsBot: false } && e.Userid is { IsValid: true, IsBot: true } v)
            {
                meHits.Add(new() { ["t"] = Server.TickCount, ["slot"] = v.Slot, ["group"] = e.Hitgroup, ["dmg"] = e.DmgHealth });
                if (meHits.Count > 12) meHits.RemoveAt(0);
            }
            return HookResult.Continue;
        });
        RegisterEventHandler<EventPlayerConnectFull>((e, _) =>
        {
            if (e.Userid is { IsBot: false }) { if (sess != null) AddTimer(3f, SessionResume); else if (cur != null) AddTimer(2f, Setup); }
            return HookResult.Continue;
        });
        RegisterListener<Listeners.OnEntityTakeDamagePre>(OnTakeDamage);
        // your shots: the bots on their path that hear them react (they fight on their own)
        RegisterEventHandler<EventWeaponFire>((e, _) =>
        {
            if (cur == null || phase != "live" || mode != "actor" || drill?.Mode == "crossfire" || e.Userid is not { IsValid: true, IsBot: false } h) return HookResult.Continue;   // Crossfire: the real peek, heard or not
            var w = e.Weapon ?? "";
            if (w.Contains("knife") || w.Contains("grenade") || w.Contains("flashbang") || w.Contains("molotov") || w.Contains("decoy")) return HookResult.Continue;
            if (h.PlayerPawn.Value?.AbsOrigin is not { } o) return HookResult.Continue;
            var me = new Vector3(o.X, o.Y, o.Z);
            var r = e.Silenced || w.Contains("silencer") ? Earshot / 2 : Earshot;
            foreach (var (slot, t) in bots.ToList())
            {
                if (t.Hold || t.Team == cur.Team || free.Contains(slot) || gone.Contains(t.Sid)) continue;   // your enemies
                var c = Utilities.GetPlayerFromSlot(slot);
                if (c?.PlayerPawn.Value?.AbsOrigin is { } bo && Vector3.Distance(new Vector3(bo.X, bo.Y, bo.Z), me) < r)
                { Free(slot, c, t); Log("heard {n}", t.Name); }
            }
            return HookResult.Continue;
        });
        // a situation's bomb: defused or blown up, the situation is over
        RegisterEventHandler<EventBombDefused>((e, _) => { if (cur is { Kind: "death" or "clutch" } && phase == "live") Finish("defused"); return HookResult.Continue; });
        RegisterEventHandler<EventBombExploded>((e, _) => { if (cur is { Kind: "death" or "clutch" } && phase == "live") Finish("exploded"); return HookResult.Continue; });
        RegisterEventHandler<EventBombPlanted>((e, _) => { if (cur is { Kind: "death" or "clutch" }) bombLive = bombDone = true; return HookResult.Continue; });
        RegisterEventHandler<EventSmokegrenadeDetonate>((e, _) => { Log("smoke pops {x:F0} {y:F0}", e.X, e.Y); return HookResult.Continue; });
        RegisterEventHandler<EventFlashbangDetonate>((e, _) => { Log("flash pops {x:F0} {y:F0}", e.X, e.Y); return HookResult.Continue; });
        RegisterEventHandler<EventHegrenadeDetonate>((e, _) => { Log("he pops {x:F0} {y:F0}", e.X, e.Y); return HookResult.Continue; });
        RegisterEventHandler<EventInfernoStartburn>((e, _) => { Log("fire {x:F0} {y:F0}", e.X, e.Y); return HookResult.Continue; });
        Server.ExecuteCommand("sv_hibernate_when_empty 0");
        RegisterSession();
        AddCommand("css_replay", "play a scenario: css_replay <id> [actor|spec]", (p, c) => CmdReplay(p, c));
        AddCommand("css_r", "the same situation again", (p, c) => { if (cur != null) Setup(); });
        AddCommand("css_n", "next situation of this map (in a session: skip the drill)", (p, c) => { if (sess != null) SkipDrill(); else Cycle(1); });
        AddCommand("css_p", "previous situation of this map", (p, c) => Cycle(-1));
        AddCommand("css_spec", "switch between playing your spot and watching", (p, c) => { mode = mode == "spec" ? "actor" : "spec"; if (cur != null) Setup(); });
        AddCommand("css_list", "situations of this map", (p, c) => { foreach (var s in List()) Say(p, s); });
        AddCommand("css_diff", "bot difficulty 0-3", (p, c) => { if (int.TryParse(c.GetArg(1), out var d)) difficulty = Math.Clamp(d, 0, 3); Say(p, F("difficulty {n}", "n", difficulty)); if (cur != null) Setup(); });
        AddCommand("css_dbg", "state of the bots", (p, c) =>
        {
            foreach (var cls in new[] { "smokegrenade_projectile", "hegrenade_projectile", "flashbang_projectile", "molotov_projectile" })
                foreach (var e in Utilities.FindAllEntitiesByDesignerName<CBaseCSGrenadeProjectile>(cls))
                    Log("dbg {c} at {x:F0} {y:F0} {z:F0} vel {v:F0} det {d:F1} now {n:F1} think {t} live {l} smoke {s}", cls, e.AbsOrigin?.X, e.AbsOrigin?.Y, e.AbsOrigin?.Z,
                        e.AbsVelocity?.Length(), e.DetonateTime, Server.CurrentTime, e.NextThinkTick, e.IsLive, cls.StartsWith("smoke") ? new CSmokeGrenadeProjectile(e.Handle).DidSmokeEffect : null);
            foreach (var b in Utilities.GetPlayers().Where(x => x is { IsValid: true }))
                Log("dbg {n} slot {s} team {t} alive {a} life {l} hp {h}", b.PlayerName, b.Slot, b.Team, b.PawnIsAlive, b.PlayerPawn.Value?.LifeState, b.PlayerPawn.Value?.Health);
        });
        AddCommand("css_dbgbots", "the players' body angle, aim, move type, speed and kit; the bomb; the guns on the ground", (p, c) =>
        {
            foreach (var b in Utilities.GetPlayers().Where(x => x is { IsValid: true, PawnIsAlive: true }))
            {
                var pw = b.PlayerPawn.Value;
                if (pw == null) continue;
                var r = pw.AbsRotation; var e = pw.EyeAngles; var v = pw.AbsVelocity;
                var kit = pw.ItemServices == null ? (bool?)null : new CCSPlayer_ItemServices(pw.ItemServices.Handle).HasDefuser;
                Log("dbgbots {n} body {bp:F1} {by:F1} {br:F1} eye {ep:F1} {ey:F1} move {m} speed {s:F0} kit {k} free {f} life {l} hp {h}", b.PlayerName,
                    r?.X, r?.Y, r?.Z, e?.X, e?.Y, pw.MoveType, v == null ? -1 : Math.Sqrt(v.X * v.X + v.Y * v.Y), kit, free.Contains(b.Slot), pw.LifeState, pw.Health);
            }
            foreach (var c4 in Utilities.FindAllEntitiesByDesignerName<CPlantedC4>("planted_c4"))
                Log("dbgbots bomb at {x:F0} {y:F0} {z:F0} site {s} ticking {t} blows in {l:F1} s", c4.AbsOrigin?.X, c4.AbsOrigin?.Y, c4.AbsOrigin?.Z,
                    c4.BombSite, c4.BombTicking, c4.C4Blow - Server.CurrentTime);
            Log("dbgbots guns on the ground: {n}", Utilities.FindAllEntitiesByDesignerName<CBasePlayerWeapon>("weapon_").Count(w => w.OwnerEntity.Value == null));
        });
        // the In game page's numpad keys say a path with CS2's chat wheel "Ping Site A": what the server makes of it
        // (a ping entity, and where), tried with a bot
        AddCommand("css_dbgping", "a bot uses the chat wheel's Ping Site A: the pings made, and where", (p, c) =>
        {
            var b = Utilities.GetPlayers().FirstOrDefault(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true }
                                                                && x.PlayerPawn.Value?.LifeState == (byte)LifeState_t.LIFE_ALIVE);
            if (b == null) { Log("dbgping: no bot alive"); return; }
            var arg = c.ArgCount > 1 ? c.GetArg(1) : "CW.GoA";
            var before = Utilities.GetAllEntities().Select(e => e.Index).ToHashSet();
            // a CW.* item through the chat wheel's command; anything else as it is (player_ping: a ping where it looks)
            b.ExecuteClientCommandFromServer(arg.StartsWith("CW.") ? $"playerchatwheel {arg} \"#Chatwheel_aplan\"" : c.ArgString);
            AddTimer(0.5f, () =>
            {
                foreach (var e in Utilities.GetAllEntities().Where(e => !before.Contains(e.Index) || (e.DesignerName != null && e.DesignerName.Contains("ping"))))
                {
                    var be = new CBaseEntity(e.Handle);
                    Log("dbgping new or ping entity {d} at {x:F0} {y:F0} {z:F0}", e.DesignerName, be.AbsOrigin?.X, be.AbsOrigin?.Y, be.AbsOrigin?.Z);
                }
                foreach (var s in Utilities.FindAllEntitiesByDesignerName<CBaseEntity>("func_bomb_target"))
                    Log("dbgping site trigger at {x:F0} {y:F0} {z:F0}", s.AbsOrigin?.X, s.AbsOrigin?.Y, s.AbsOrigin?.Z);
                Log("dbgping: {n} by {b} ({a})", "done", b.PlayerName, arg);
            });
        });
        AddCommand("css_dbgspawns", "the map's spawn points", (p, c) =>
        {
            foreach (var cls in new[] { "info_player_terrorist", "info_player_counterterrorist" })
                foreach (var e in Utilities.FindAllEntitiesByDesignerName<SpawnPoint>(cls))
                    Log("dbgspawns {c} {x:F0} {y:F0} {z:F0} yaw {w:F0} enabled {on} priority {pr}", cls, e.AbsOrigin?.X, e.AbsOrigin?.Y, e.AbsOrigin?.Z, e.AbsRotation?.Y, e.Enabled, e.Priority);
        });
        AddCommand("css_dbgbreak", "the map's breakables", (p, c) =>
        {
            foreach (var cls in new[] { "func_breakable", "func_breakable_surf", "prop_dynamic", "prop_physics_multiplayer" })
                foreach (var e in Utilities.FindAllEntitiesByDesignerName<CBaseEntity>(cls))
                    Log("dbgbreak {c} {n} {x:F0} {y:F0} {z:F0} hp {h}", cls, e.Entity?.Name, e.AbsOrigin?.X, e.AbsOrigin?.Y, e.AbsOrigin?.Z, e.Health);
        });
        AddCommand("css_dbgbreakat", "break the breakables near x y z", (p, c) =>
        {
            if (float.TryParse(c.GetArg(1), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var x)
                && float.TryParse(c.GetArg(2), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var y)
                && float.TryParse(c.GetArg(3), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var z))
                Break(new List<Vector3> { new(x, y, z) });
            AddTimer(1f, () =>
            {
                foreach (var e in Utilities.FindAllEntitiesByDesignerName<CBaseEntity>("prop_dynamic").Where(e => (e.Entity?.Name ?? "").Contains("vent")))
                    Log("dbgbreakat after: {n} valid {v} hp {h}", e.Entity?.Name, e.IsValid, e.Health);
            });
        });
        AddCommand("css_dbgboost", "two bots of a team: one held still (crouched with 1), the other put on its head: css_dbgboost [duck 0|1] [u over its top, default 100]", (p, c) =>
        {
            // 28/10, the user on the boosts: "vérifie que le joueur n'est pas un tout petit peu en conflit avec la tête du bot
            // en dessous". The one below held 0.5 s first (its crouch settled), the other put `up` u over its box's top, then
            // each tick for 1.5 s: on the ground or not for the game, what it stands on, its feet over the box's top
            var duck = c.ArgCount > 1 && c.GetArg(1) == "1";
            var up = c.ArgCount > 2 && float.TryParse(c.GetArg(2), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var uv) ? uv : 100f;
            var bs = Utilities.GetPlayers().Where(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true }).GroupBy(x => x.Team).FirstOrDefault(g => g.Count() >= 2)?.Take(2).ToList();
            if (bs == null || bs[0].PlayerPawn.Value?.AbsOrigin == null || bs[1].PlayerPawn.Value == null) { Log("dbgboost: two living bots of one team needed"); return; }
            var how = c.ArgCount > 3 ? c.GetArg(3) : "zombie";   // their AI idle by bot_zombie, or by bot_stop ("stop": do they fall then?)
            Zombie(how == "zombie");
            Server.ExecuteCommand($"bot_stop {(how == "stop" ? 1 : 0)}");
            var a = bs[0].PlayerPawn.Value!; var b = bs[1].PlayerPawn.Value!;
            var at = new Vector3(a.AbsOrigin!.X, a.AbsOrigin.Y, a.AbsOrigin.Z);
            Freeze(a, true);
            Freeze(b, false);
            b.Teleport(at + new Vector3(60f, 0f, 0f), null, Vector3.Zero);
            var tm = AddTimer(0.05f, () => { if (a.IsValid) { a.Teleport(at, null, Vector3.Zero); HoldAim(a, new Vector3(0, 90, 0), duck); } }, CounterStrikeSharp.API.Modules.Timers.TimerFlags.REPEAT);
            AddTimer(0.5f, () =>
            {
                if (!a.IsValid || !b.IsValid || a.Collision == null) return;
                var top = at.Z + a.Collision.Maxs.Z;
                b.Teleport(new Vector3(at.X, at.Y, top + up), null, Vector3.Zero);
                int n = 0, onG = 0; string? gent = null; float gapMin = 999f, gapMax = -999f;
                var tick = AddTimer(0.015625f, () =>
                {
                    if (!a.IsValid || !b.IsValid || b.AbsOrigin == null || a.Collision == null || a.AbsOrigin == null) return;
                    var g = b.AbsOrigin.Z - (a.AbsOrigin.Z + a.Collision.Maxs.Z);
                    if (n++ < 32) return;   // its first half second: falling, landing
                    if ((b.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0) onG++;
                    gent ??= b.GroundEntity?.Value?.DesignerName;
                    gapMin = Math.Min(gapMin, g); gapMax = Math.Max(gapMax, g);
                }, CounterStrikeSharp.API.Modules.Timers.TimerFlags.REPEAT);
                AddTimer(1.5f, () =>
                {
                    tick.Kill(); tm.Kill();
                    var da = a.MovementServices == null ? -1f : new CCSPlayer_MovementServices(a.MovementServices.Handle).DuckAmount;
                    Log("dbgboost " + how + " duck {d} up {u}: below duck amount {da:F2} top {t:F1} (maxs {m:F1}); on top: on the ground {g}/{n} ticks, stands on {e}, feet {lo:F2} to {hi:F2} u over the top, vel {v} (solid teammates {s})",
                        duck, up, da, top, a.Collision?.Maxs.Z ?? -1f, onG, Math.Max(0, n - 32), gent ?? "-", gapMin, gapMax,
                        b.AbsVelocity is { } bv ? $"{bv.X:F1} {bv.Y:F1} {bv.Z:F1}" : "-", ConVar.Find("mp_solid_teammates")?.GetPrimitiveValue<int>());
                });
            });
        });
        // 28/10, lab 4: you rest 0.6 u over a standing teammate's head at Dust2's Top Mid and the game has you off the ground
        // (at Short Stairs, right on it: on the ground). You put `up` u over the nearest teammate bot's box top, then for 1 s:
        // on the ground or not, on what, your feet over its top: css_dbgboostme [up]
        AddCommand("css_dbgboostme", "you put over the nearest teammate bot's head: css_dbgboostme [u over its top]", (p, c) =>
        {
            var up = c.ArgCount > 1 && float.TryParse(c.GetArg(1), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var uv) ? uv : 0f;
            var h = Humans().FirstOrDefault(x => x.PawnIsAlive);
            var hp = h?.PlayerPawn.Value;
            if (h == null || hp?.AbsOrigin == null) { Log("dbgboostme: nobody alive"); return; }
            var ho = new Vector3(hp.AbsOrigin.X, hp.AbsOrigin.Y, hp.AbsOrigin.Z);
            var mate = Utilities.GetPlayers().Where(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true } && x.Team == h.Team && x.PlayerPawn.Value?.AbsOrigin != null)
                .OrderBy(x => { var o = x.PlayerPawn.Value!.AbsOrigin!; return Vector3.Distance(new Vector3(o.X, o.Y, o.Z), ho); }).FirstOrDefault();
            var mp = mate?.PlayerPawn.Value;
            if (mp?.AbsOrigin == null || mp.Collision == null) { Log("dbgboostme: no teammate bot"); return; }
            var mo = new Vector3(mp.AbsOrigin.X, mp.AbsOrigin.Y, mp.AbsOrigin.Z);
            hp.Teleport(new Vector3(mo.X, mo.Y, mo.Z + mp.Collision.Maxs.Z + up), null, Vector3.Zero);
            int n = 0, onG = 0; string? gent = null; float lo = 999f, hi = -999f;
            var tm = AddTimer(0.015625f, () =>
            {
                if (!hp.IsValid || hp.AbsOrigin == null || !mp.IsValid || mp.AbsOrigin == null || mp.Collision == null) return;
                if (n++ < 32) return;
                var g = hp.AbsOrigin.Z - (mp.AbsOrigin.Z + mp.Collision.Maxs.Z);
                lo = Math.Min(lo, g); hi = Math.Max(hi, g);
                if ((hp.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0) onG++;
                gent ??= hp.GroundEntity?.Value?.DesignerName;
            }, CounterStrikeSharp.API.Modules.Timers.TimerFlags.REPEAT);
            AddTimer(1.5f, () =>
            {
                tm.Kill();
                Log("dbgboostme up {u}: on the ground {g}/{n} ticks, on {e}, feet {lo:F2} to {hi:F2} u over its top (its maxs {m:F1}, duck {d:F2}, its z {z:F1}), you {mv}, solid teammates {s}",
                    up, onG, Math.Max(0, n - 32), gent ?? "-", lo, hi, mp.Collision?.Maxs.Z ?? -1f,
                    mp.MovementServices == null ? -1f : new CCSPlayer_MovementServices(mp.MovementServices.Handle).DuckAmount, mp.AbsOrigin?.Z ?? 0f,
                    hp.MoveType.ToString(), ConVar.Find("mp_solid_teammates")?.GetPrimitiveValue<int>());
            });
        });
        AddCommand("css_dbgents", "the map's entity classes and how many of each", (p, c) =>
        {
            foreach (var g in Utilities.GetAllEntities().Where(e => e.DesignerName != null).GroupBy(e => e.DesignerName).OrderBy(g => g.Key))
                Log("dbgents {d} {n}", g.Key, g.Count());
        });
        AddCommand("css_dbgdoors", "the map's doors: class and position", (p, c) =>
        {
            foreach (var d in Utilities.FindAllEntitiesByDesignerName<CBaseEntity>("prop_door_rotating"))
            {
                try
                {
                    var o = d.AbsOrigin;
                    var n = d.CBodyComponent?.SceneNode;
                    Log("dbgdoors #{i} valid {v} origin {o} node {n} at {x:F0} {y:F0} {z:F0}", d.Index, d.IsValid, o != null, n != null,
                        o?.X ?? n?.AbsOrigin?.X, o?.Y ?? n?.AbsOrigin?.Y, o?.Z ?? n?.AbsOrigin?.Z);
                }
                catch (Exception ex) { Log("dbgdoors #{i}: {m}", d.Index, ex.Message); }
            }
        });
        AddCommand("css_dbgline", "draw a test line (3 segments) and count the beams", (p, c) =>
        {
            DrawLine(new List<float[]> { new[] { 0f, 0f, 0f }, new[] { 200f, 0f, 0f }, new[] { 200f, 200f, 0f }, new[] { 0f, 200f, 0f } });
            Log("dbgline: {n} beams drawn, {m} in the world", beams.Count, Utilities.FindAllEntitiesByDesignerName<CBeam>("beam").Count());
            AddTimer(2f, () => { ClearLine(); Log("dbgline: cleared, {m} in the world", Utilities.FindAllEntitiesByDesignerName<CBeam>("beam").Count()); });
        });
        AddCommand("css_stop", "stop the replay (or the session)", (p, c) =>
        {
            if (sess != null) { EndSession(true); return; }
            cur = null; phase = "idle"; bots.Clear(); builtFor = null; Server.ExecuteCommand("bot_quota 0"); Server.ExecuteCommand("bot_kick");
        });
    }

    void Say(CCSPlayerController? p, string s) { if (p == null) Log("{s}", s); else p.PrintToChat($" \x04[coach]\x01 {s}"); }

    void All(string s) { foreach (var p in Humans()) p.PrintToChat($" \x04[coach]\x01 {s}"); Log("{s}", s); }

    static IEnumerable<CCSPlayerController> Humans() => Utilities.GetPlayers().Where(p => p is { IsValid: true, IsBot: false, IsHLTV: false });

    List<string> List()
    {
        var map = Server.MapName;
        return Directory.GetFiles(System.IO.Path.Combine(Dir, "scenarios"), "*.json").Select(f => System.IO.Path.GetFileNameWithoutExtension(f)!)
            .Where(id => Peek(id)?.Map == map).OrderBy(x => x).ToList();
    }

    Scenario? Peek(string id)
    {
        var f = System.IO.Path.Combine(Dir, "scenarios", id + ".json");
        if (!File.Exists(f)) return null;
        try { return CutJumps(JsonSerializer.Deserialize<Scenario>(File.ReadAllText(f))); } catch (Exception e) { Log($"{id}: {e.Message}"); return null; }
    }

    // a way ends at its first step of more than 300 u (17/10, the self-test: a round's end tick was the next round's start,
    // everyone back on a spawn; files built before replay.py cut them)
    static Scenario? CutJumps(Scenario? s)
    {
        foreach (var t in s?.Players ?? new())
            for (var k = 0; k + 1 < t.Frames; k++)
                if (new Vector2(t.Path[k * 5 + 5] - t.Path[k * 5], t.Path[k * 5 + 6] - t.Path[k * 5 + 1]).Length() > 300f)
                {
                    t.Path = t.Path[..((k + 1) * 5)];
                    if (t.Death >= k + 1) t.Death = -1;
                    break;
                }
        return s;
    }

    void CmdReplay(CCSPlayerController? p, CommandInfo c)
    {
        UseUi(ReadUi());   // the app's language (written with the situation)
        var s = Peek(c.GetArg(1));
        if (s == null) { Say(p, F("no scenario {id}", "id", c.GetArg(1))); return; }
        if (c.ArgCount > 2 && (c.GetArg(2) == "spec" || c.GetArg(2) == "actor")) mode = c.GetArg(2);
        if (c.ArgCount > 3 && int.TryParse(c.GetArg(3), out var d)) difficulty = Math.Clamp(d, 0, 3);
        cur = s;
        if (Server.MapName != s.Map) { phase = "setup"; ChangeMap(s.Map); return; }
        Setup();
    }

    void Cycle(int d)
    {
        var l = List();
        if (l.Count == 0) return;
        var i = cur == null ? -1 : l.IndexOf(cur.Id);
        cur = Peek(l[((i + d) % l.Count + l.Count) % l.Count]);
        if (cur != null) Setup();
    }

    // the bots (one per recorded player but you), their names, your team; then a clean round
    void Setup()
    {
        if (cur == null) return;
        var g = ++generation;
        gone.Clear(); free.Clear(); contact.Clear(); engaged.Clear(); sawYou.Clear(); botHop.Clear(); botAt.Clear(); spawnHeldN.Clear(); wayHead.Clear(); botStill.Clear(); botProg.Clear(); botFrozen.Clear(); botGround.Clear(); stepTries.Clear();
        if (mode == "actor" && !Humans().Any() && !selftest) { phase = "waiting"; return; }   // starts when you join
        phase = "setup";
        // the same situation again: the same bots, only a clean round (fast retries)
        var diff = drill?.Mode == "defend" ? Math.Max(0, BotLv - 1) : BotLv;   // a defense: three at a time, one level easier
        var key = $"{cur.Id}|{mode}|{diff}";
        if (builtFor == key && bots.Count > 0 && bots.Keys.All(sl => Utilities.GetPlayerFromSlot(sl) is { IsValid: true, IsBot: true }))
        {
            // the same bots on the new try's own tracks: a defense's attackers kept the last try's start and way, and
            // its retry's waited a minute at their entrance (09/10 17:51: "les bots étaient freeze")
            var fresh = cur.Players.Where(t => !t.Me || mode == "spec").ToList();
            foreach (var team in new[] { 2, 3 })
            {
                var slots = bots.Where(b => b.Value.Team == team).Select(b => b.Key).ToList();
                var tr = fresh.Where(t => t.Team == team).ToList();
                for (int i = 0; i < Math.Min(slots.Count, tr.Count); i++)
                {
                    bots[slots[i]] = tr[i];
                    if (Utilities.GetPlayerFromSlot(slots[i]) is { IsValid: true } bc)
                    { bc.PlayerName = tr[i].Me ? tr[i].Name + " (you)" : tr[i].Name; Utilities.SetStateChanged(bc, "CBasePlayerController", "m_iszPlayerName"); }
                }
            }
            Teams();
            awaitRestart = true;
            Server.ExecuteCommand("mp_restartgame 1");
            // no round start 4 s on: placed anyway (29/10, lab 15: Anubis's R15 and Cache's R13, a bomb's situations whose
            // bots had all been freed at the window's end: their retry never started, nothing logged, the session gave up)
            Log("retry {id}: round restart asked", cur.Id);
            AddTimer(4f, () => { if (g == generation && awaitRestart) { awaitRestart = false; Log("retry {id}: no round start in 4 s, placed anyway", cur?.Id); Place(); } });
            return;
        }
        bots.Clear();
        builtFor = key;
        // a situation as it was: the dead drop their gun and their kit, to pick up like in the match (the round restart
        // of each try clears the ground); the drills keep the ground clean
        var drop = cur.Kind is "death" or "clutch" ? 1 : 0;
        // the game's clock says the real round's time (from GO: the countdown first), 04/10 "put the real timing of the
        // game"; a drill's too: when its angles get fought, when its lineup is thrown, an aim drill's own time (06/10: "le
        // vrai temps in-game de la situation, pas 58 minutes"); without one: an hour
        var rt = (cur.Clock > 0 ? (cur.Clock + (cur.Kind is "death" or "clutch" ? 5 : 3)) / 60f : 60f).ToString("0.###", System.Globalization.CultureInfo.InvariantCulture);
        foreach (var cmd in new[] { "mp_warmup_end", "mp_ignore_round_win_conditions 1", "mp_freezetime 0", $"mp_roundtime {rt}",
                     $"mp_roundtime_defuse {rt}", $"mp_roundtime_hostage {rt}", "mp_buytime 0", "mp_autoteambalance 0", "mp_limitteams 0",
                     "mp_friendlyfire 0", "mp_autokick 0", "mp_halftime 0", "mp_maxrounds 99", "mp_match_can_clinch 0",
                     "mp_give_player_c4 0", $"mp_death_drop_gun {drop}", $"mp_death_drop_defuser {drop}", "mp_c4timer 40",
                     "mp_randomspawn 0", "bot_quota_mode normal", $"mp_solid_teammates {(drill?.Id.StartsWith("boost") == true ? 1 : 0)}",   // no teammate's path blocks yours (04/10); a boost: you stand on one
                     "mp_playercashawards 0", "mp_teamcashawards 0",
                     "bot_join_after_player 0", "bot_chatter off", "sv_hibernate_when_empty 0", "sv_falldamage_scale 0",
                     // Aim Botz's own config (07/10): respawns, knives, a team for bots and you, the ground cleaned in 3 s
                     "mp_respawn_on_death_ct 0", "mp_respawn_on_death_t 0", "bot_all_weapons", "bot_join_team any", "mp_humanteam any",
                     "weapon_auto_cleanup_time 0", "weapon_max_before_cleanup 0", "mp_free_armor 0", "mp_buy_anywhere 0",
                     $"bot_difficulty {diff}", "bot_quota 0", "bot_kick" })   // quota 0 first: kicked with the last drill's quota (10), the game added 10 of its own and a prefire got none (06/10)
            Server.ExecuteCommand(cmd);
        var want = cur.Players.Where(t => !t.Me || mode == "spec").ToList();
        AddBots(g, want, 0);
    }

    // a bot really in the game (a kicked one stays listed a moment, leaving)
    static bool Here(CCSPlayerController p) => p is { IsValid: true, IsBot: true } && p.Connected == PlayerConnectedState.Connected;
    static bool Coming(CCSPlayerController p) => p is { IsValid: true, IsBot: true }
                                                 && p.Connected is PlayerConnectedState.Connected or PlayerConnectedState.Connecting or PlayerConnectedState.Reconnecting;
    static bool Leaving(CCSPlayerController p) => p is { IsValid: true, IsBot: true } && p.Connected != PlayerConnectedState.Disconnected
                                                  && p.Connected != PlayerConnectedState.NeverConnected;

    // the old bots gone first: added while they leave, the team still looks full and the new ones are refused (03/10:
    // a prefire with no bot, a clutch's enemy that was a leaving bot); then the new ones, every one in before the roles
    void AddBots(int g, List<Track> want, int tries)
    {
        AddTimer(0.25f, () =>
        {
            if (g != generation || cur == null) return;
            if (Utilities.GetPlayers().Any(Leaving) && tries < 16) { if (tries == 8) Server.ExecuteCommand("bot_kick"); AddBots(g, want, tries + 1); return; }
            AddTimer(0.75f, () =>   // gone: the game still counts them a moment (04/10: 1 CT of 4 right after 10 CTs left)
            {
                if (g != generation || cur == null) return;
                foreach (var t in want) Server.ExecuteCommand(t.Team == 2 ? "bot_add_t" : "bot_add_ct");
                Teams();
                WaitBots(g, want, 0);
            });
        });
    }

    void WaitBots(int g, List<Track> want, int tries)
    {
        AddTimer(0.3f, () =>
        {
            if (g != generation || cur == null) return;
            var all = want.GroupBy(t => t.Team).All(k => Utilities.GetPlayers().Count(p => Here(p) && (int)p.Team == k.Key) >= k.Count());
            // 09/10 (CS2 build of 08/10): a team that held 10 bots refuses new ones ("Could not add bot to the game: Team is
            // full") although they were kicked: the ones who left still count until a round restart (a 2nd and 3rd prefire
            // of a map skipped, "the bots did not come"). Not one of a team's bots coming: one restart, then ask again
            var none = want.GroupBy(t => t.Team).Where(k => !Utilities.GetPlayers().Any(p => Coming(p) && (int)p.Team == k.Key)).Select(k => k.Key).ToList();
            if (none.Count > 0 && tries == 2 && refusedFor != g)
            {
                refusedFor = g;
                var left = Utilities.GetPlayers().Count(p => p is { IsValid: true, IsBot: true } && none.Contains((int)p.Team) && p.Connected == PlayerConnectedState.Disconnected);
                Log("team {t}: no bot came ({l} left still listed): a round restart, then again", string.Join("+", none), left);
                Server.ExecuteCommand("mp_restartgame 1");
                AddTimer(1.6f, () =>
                {
                    if (g != generation || cur == null) return;
                    foreach (var k in want.GroupBy(t => t.Team))
                    {
                        var miss = k.Count() - Utilities.GetPlayers().Count(p => Coming(p) && (int)p.Team == k.Key);
                        for (int i = 0; i < miss; i++) Server.ExecuteCommand(k.Key == 2 ? "bot_add_t" : "bot_add_ct");
                    }
                    Teams();
                    WaitBots(g, want, 3);
                });
                return;
            }
            if (!all && tries < 14)
            {
                if (tries % 4 == 3)   // still short: ask again for the missing ones (the ones on their way count)
                    foreach (var k in want.GroupBy(t => t.Team))
                    {
                        var miss = k.Count() - Utilities.GetPlayers().Count(p => Coming(p) && (int)p.Team == k.Key);
                        for (int i = 0; i < miss; i++) Server.ExecuteCommand(k.Key == 2 ? "bot_add_t" : "bot_add_ct");
                    }
                WaitBots(g, want, tries + 1);
                return;
            }
            Roles(g, want);
        });
    }

    void Roles(int g, List<Track> want)
    {
        {
            foreach (var team in new[] { 2, 3 })
            {
                var tracks = want.Where(t => t.Team == team).ToList();
                var bs = Utilities.GetPlayers().Where(p => Here(p) && (int)p.Team == team).ToList();
                for (int i = 0; i < Math.Min(tracks.Count, bs.Count); i++)
                {
                    bots[bs[i].Slot] = tracks[i];
                    bs[i].PlayerName = tracks[i].Me ? tracks[i].Name + " (you)" : tracks[i].Name;
                    Utilities.SetStateChanged(bs[i], "CBasePlayerController", "m_iszPlayerName");
                }
                if (bs.Count != tracks.Count) Log($"team {team}: {bs.Count} bots for {tracks.Count} tracks");
                foreach (var extra in bs.Skip(tracks.Count)) Server.ExecuteCommand($"kickid {extra.UserId}");   // a bot the game added on its own
            }
            Server.ExecuteCommand($"bot_quota {bots.Count}");   // the game keeps that many: no bot added on its own
            // a drill without its bots (or a situation without any enemy): once more from scratch, then skipped
            var foes = want.Count(t => t.Team != cur!.Team);
            if (want.Count > 0 && (bots.Count == 0 || (mode == "actor" && foes > 0 && !bots.Values.Any(t => t.Team != cur!.Team))))
            {
                Log("no bots for {id} ({n} of {w})", cur!.Id, bots.Count, want.Count);
                if (emptyTries++ < 1) { builtFor = null; Setup(); return; }
                emptyTries = 0;
                if (sess != null && drill != null) { phase = "live"; DrillDone(false, "skipped", 0, "the bots did not come"); }
                return;
            }
            emptyTries = 0;
            awaitRestart = true;
            Server.ExecuteCommand("mp_restartgame 1");
        }
    }

    void Teams()
    {
        if (cur == null) return;
        var team = mode == "spec" ? CsTeam.Spectator : (CsTeam)cur.Team;
        foreach (var h in Humans())
        {
            if (h.Team == team) continue;
            // from one side to the other: switch without dying (ChangeTeam kills you); from the menu: join
            if (h.Team is CsTeam.Terrorist or CsTeam.CounterTerrorist && team is CsTeam.Terrorist or CsTeam.CounterTerrorist) h.SwitchTeam(team);
            else h.ChangeTeam(team);
        }
    }

    HookResult OnRoundStart(EventRoundStart e, GameEventInfo i)
    {
        if (!awaitRestart || cur == null) return HookResult.Continue;
        awaitRestart = false;
        Log("retry {id}: round started", cur.Id);
        var g = generation;
        AddTimer(0.3f, () => { if (g == generation) Place(); });
        return HookResult.Continue;
    }

    static void Loadout(CCSPlayerController c, Track t, int? hp = null)
    {
        var pawn = c.PlayerPawn.Value;
        if (pawn == null) return;
        c.RemoveWeapons();
        // bots get no grenades: the demo's are thrown again by the plugin, their own AI would throw others. No bot gets
        // the bomb (the demo's plant is the plugin's); you get it when you carried it
        var nade = (string w) => c.IsBot && (w.Contains("grenade") || w.Contains("flashbang") || w.Contains("molotov") || w.Contains("decoy"));
        var skip = (string w) => nade(w) || (w == "weapon_c4" && c.IsBot);
        foreach (var w in t.Weapons.Where(w => w != t.Active && !skip(w))) c.GiveNamedItem(w);
        if (!string.IsNullOrEmpty(t.Active) && !skip(t.Active)) c.GiveNamedItem(t.Active);
        if (t.Kit && t.Team == 3) c.GiveNamedItem("item_defuser");
        pawn.Health = Math.Max(1, hp ?? t.Hp);
        Utilities.SetStateChanged(pawn, "CBaseEntity", "m_iHealth");
        pawn.ArmorValue = t.Armor;
        Utilities.SetStateChanged(pawn, "CCSPlayerPawn", "m_ArmorValue");
        if (pawn.ItemServices != null) new CCSPlayer_ItemServices(pawn.ItemServices.Handle).HasHelmet = t.Helmet;
        if (c.InGameMoneyServices != null) { c.InGameMoneyServices.Account = 0; Utilities.SetStateChanged(c, "CCSPlayerController", "m_pInGameMoneyServices"); }
        if (!string.IsNullOrEmpty(t.Active) && t.Active != "weapon_c4") c.ExecuteClientCommandFromServer($"use {t.Active}");
    }

    static void Freeze(CCSPlayerPawn pawn, bool on)
    {
        pawn.MoveType = on ? MoveType_t.MOVETYPE_OBSOLETE : MoveType_t.MOVETYPE_WALK;
        Schema.SetSchemaValue(pawn.Handle, "CBaseEntity", "m_nActualMoveType", on ? 1 : 2);
        Utilities.SetStateChanged(pawn, "CBaseEntity", "m_MoveType");
        // the game told of the actual one too (22/10, his test video: "je suis encore avec le bug noclip": walking on
        // the server while his game still predicted the noclip it had been in, "à moitié en train de voler")
        try { Utilities.SetStateChanged(pawn, "CBaseEntity", "m_nActualMoveType"); } catch (Exception) { }
    }

    // a still target's view on its angle, crouched or standing, every tick (its own AI idles: bot_zombie)
    readonly Dictionary<int, int> botHop = new();   // a driven bot in a crouch-jump: its slot -> the tick it jumped
    // a driven bot's place the tick before (its real speed: the game's kept the speed it was given while it was stuck in
    // something, 17/10), and for how many ticks it hasn't moved while its way runs
    readonly Dictionary<int, Vector3> botAt = new();
    readonly Dictionary<int, int> botStill = new();
    readonly Dictionary<int, int> botFrozen = new();   // for how many ticks it hasn't moved a hair though it was given a speed
    readonly Dictionary<int, bool> botGround = new();   // on the ground before this tick's teleport (a teleport clears the flag)
    readonly Dictionary<int, int> stepTries = new();   // its step hops since it last ran freely

    // put on its start again (a drill's start, a wave's respawn): what was measured of its motion before is no more
    // where a grenade thrown so comes down first, about (0.05 s steps, the game's 0.4 gravity, its first hit): within r of a spot
    static bool NadeLandsNear(Nade nd, CCSPlayerPawn by, Vector3 spot, float r)
    {
        var p = new Vector3(nd.P[0], nd.P[1], nd.P[2]);
        var v = new Vector3(nd.V[0], nd.V[1], nd.V[2]);
        var opt = new TraceOptions { InteractsWith = Masks.ShotBrushOnly };
        for (int k = 0; k < 80; k++)
        {
            var q = p + v * 0.05f;
            v.Z -= 320f * 0.05f;
            float fr;
            try { fr = Trace.TraceEndShape(new CVector(p.X, p.Y, p.Z), new CVector(q.X, q.Y, q.Z), by, opt).Fraction; }
            catch (Exception) { return false; }
            if (fr < 1f) { p = Vector3.Lerp(p, q, fr); break; }
            p = q;
        }
        return new Vector2(p.X - spot.X, p.Y - spot.Y).Length() < r;
    }

    void ForgetMotion(int slot)
    {
        botAt.Remove(slot); botStill.Remove(slot); botProg.Remove(slot); botFrozen.Remove(slot); stepTries.Remove(slot); botHop.Remove(slot); wayK.Remove(slot); walkAsk.Remove(slot);
        spawnHeldN.Remove(slot); wayHead.Remove(slot);
    }
    readonly Dictionary<int, int> spawnHeldN = new();   // ticks its way's clock waited for it on its spawn
    readonly Dictionary<int, (int T, Vector3 At, float F)> botProg = new();   // its headway: from where, since when, its way's frame then

    static void Crouch(CCSPlayerPawn pawn, bool on)
    {
        if (pawn.MovementServices == null) return;
        var mv = new CCSPlayer_MovementServices(pawn.MovementServices.Handle);
        if (mv.DuckOverride != on) mv.DuckOverride = on;
    }

    static void HoldAim(CCSPlayerPawn pawn, Vector3 a, bool duck)
    {
        if (pawn.EyeAngles is { } eye && (Math.Abs(eye.X - a.X) > 0.01f || Math.Abs(((eye.Y - a.Y + 540f) % 360f) - 180f) > 0.01f))
        { eye.X = a.X; eye.Y = a.Y; Utilities.SetStateChanged(pawn, "CCSPlayerPawn", "m_angEyeAngles"); }
        if (pawn.MovementServices != null)
        {
            var mv = new CCSPlayer_MovementServices(pawn.MovementServices.Handle);
            if (mv.DuckOverride != duck) mv.DuckOverride = duck;
        }
    }

    // the game's bots idle or not (bot_zombie: a cheat setting the plugin sets itself, never sv_cheats for you): still
    // targets never turn to you nor fire (06/10)
    static void Zombie(bool on)
    {
        try { ConVar.Find("bot_zombie")?.SetValue(on); } catch (Exception) { }
    }

    // by the console (28/10 23:03: SetValue(true) on bot_stop crashed the server, an access violation in the native
    // SetConvarValue, his game on it; false had never failed)
    static void BotStop(bool on) => Server.ExecuteCommand($"bot_stop {(on ? 1 : 0)}");

    // a kill in an aim drill: the magazine full again, like on aim maps (07/10: "à chaque fois que je tue quelqu'un, je
    // redeviens full chargeur"); never a sniper's ("au sniper les balles c'est important")
    static readonly HashSet<string> Snipers = new() { "weapon_awp", "weapon_ssg08", "weapon_g3sg1", "weapon_scar20" };

    static void FullMag(CCSPlayerController h)
    {
        var w = h.PlayerPawn.Value?.WeaponServices?.ActiveWeapon.Value;
        if (w == null || !w.IsValid || Snipers.Contains(w.DesignerName)) return;
        var max = w.VData?.MaxClip1 ?? 0;
        if (max <= 0 || w.Clip1 >= max) return;
        w.Clip1 = max;
        Utilities.SetStateChanged(w, "CBasePlayerWeapon", "m_iClip1");
    }

    // the game's bots never fire (bot_dont_shoot, a cheat setting set the same way): a timing smoke's runners (07/10)
    static void DontShoot(bool on)
    {
        try { ConVar.Find("bot_dont_shoot")?.SetValue(on); } catch (Exception) { }
    }

    // the aim map: the guns never run dry (reloads stay)
    static void Ammo(bool on)
    {
        try { ConVar.Find("sv_infinite_ammo")?.SetValue(on ? 2 : 0); } catch (Exception) { }
    }

    // a teleport's angles turn the whole body: with a pitch the player leans, his head off his feet, and his view goes
    // through walls (04/10, the video: "my character leans", "my view through the wall"). Bodies stay upright: only the
    // yaw; you look up or down yourself
    static Vector3 Upright(Vector3 ang) => new(0, ang.Y, 0);

    // the map's doors near these points (a door in the way of a real player's path was open in the match; one in a
    // grenade's way, open for the pro who threw it): each turned, without its motion, to whichever of its states (open
    // one way, the other, closed) leaves these points the freest. 17/10, the self-test and css_dbgdoor: the game's "Open"
    // swung Overpass's B door into the attackers' way (the real players had it open the other way), and its motion
    // leaves an entity_blocker over its swing
    void OpenDoors(IEnumerable<Vector3> pts, float r = 96f)
    {
        var doors = Utilities.FindAllEntitiesByDesignerName<CPropDoorRotating>("prop_door_rotating").Where(d => d.IsValid && d.AbsOrigin != null).ToList();
        if (doors.Count == 0) return;
        var all = pts.ToList();
        var set = 0;
        foreach (var d in doors)
        {
            var h = new Vector3(d.AbsOrigin!.X, d.AbsOrigin.Y, d.AbsOrigin.Z);
            var near = all.Where(p => Vector3.DistanceSquared(p, h) < r * r).ToList();
            if (near.Count == 0 || d.Collision is not { } col) continue;
            // its leaf: its longer side in its own frame, from the hinge (its origin)
            var alongY = col.Maxs.Y - col.Mins.Y >= col.Maxs.X - col.Mins.X;
            float lo = alongY ? col.Mins.Y : col.Mins.X, hi = alongY ? col.Maxs.Y : col.Maxs.X;
            float zlo = h.Z + col.Mins.Z - 8f, zhi = h.Z + col.Maxs.Z;
            int Crossed(QAngle a)
            {
                var th = a.Y * MathF.PI / 180f;
                var axis = alongY ? new Vector2(-MathF.Sin(th), MathF.Cos(th)) : new Vector2(MathF.Cos(th), MathF.Sin(th));
                var h2 = new Vector2(h.X, h.Y);
                return near.Count(p => p.Z > zlo && p.Z < zhi && SegDist(new Vector2(p.X, p.Y), h2 + axis * lo, h2 + axis * hi) < 18f);
            }
            var best = new[] { d.RotationOpenForward, d.RotationOpenBack, d.RotationClosed }.OrderBy(Crossed).First();   // open first on a tie
            d.Teleport(null, new Vector3(best.X, best.Y, best.Z), null);
            set++;
        }
        if (set > 0) Log("{n} door(s) set", set);
    }

    // the map's other doors (a gate or a panel the map's own logic moves: a prop_dynamic) a way goes right through:
    // open in that match, out of the way here, neither seen nor solid (17/10, the self-test: cs_shelter's gate at -964
    // 1094, closed here, the bots stopped against it). A thin, wide, tall one only, crossed within its width
    void OpenGates(List<Vector3> pts)
    {
        var n = 0;
        foreach (var e in Utilities.FindAllEntitiesByDesignerName<CBaseModelEntity>("prop_dynamic"))
        {
            if (!e.IsValid || e.AbsOrigin == null || e.Collision is not { } col || col.SolidType == SolidType_t.SOLID_NONE) continue;
            float sx = col.Maxs.X - col.Mins.X, sy = col.Maxs.Y - col.Mins.Y, sz = col.Maxs.Z - col.Mins.Z;
            if (Math.Min(sx, sy) > 16f || Math.Max(sx, sy) < 40f || sz < 48f) continue;
            var thinX = sx < sy;
            var o = e.AbsOrigin;
            var th = (e.AbsRotation?.Y ?? 0f) * MathF.PI / 180f;
            float cs = MathF.Cos(th), sn = MathF.Sin(th);
            bool Through(Vector3 p)
            {   // in its own frame: within 8 u of its plane, inside its width and height
                float dx = p.X - o.X, dy = p.Y - o.Y, lx = dx * cs + dy * sn, ly = -dx * sn + dy * cs, lz = p.Z - o.Z;
                var thin = thinX ? lx > col.Mins.X - 8f && lx < col.Maxs.X + 8f : ly > col.Mins.Y - 8f && ly < col.Maxs.Y + 8f;
                var wide = thinX ? ly > col.Mins.Y + 4f && ly < col.Maxs.Y - 4f : lx > col.Mins.X + 4f && lx < col.Maxs.X - 4f;
                return thin && wide && lz > col.Mins.Z - 8f && lz < col.Maxs.Z;
            }
            if (!pts.Any(Through)) continue;
            e.AcceptInput("DisableCollision");
            e.RenderMode = RenderMode_t.kRenderNone;
            Utilities.SetStateChanged(e, "CBaseModelEntity", "m_nRenderMode");
            n++;
            Log("gate out of the way: #{i} at {x:F0} {y:F0} {z:F0}", e.Index, o.X, o.Y, o.Z);
        }
        if (n > 0) Log("{n} gate(s) out of the way", n);
    }

    static float SegDist(Vector2 p, Vector2 a, Vector2 b)
    {
        var ab = b - a;
        var t = Math.Clamp(Vector2.Dot(p - a, ab) / Math.Max(1e-3f, ab.LengthSquared()), 0f, 1f);
        return Vector2.Distance(p, a + ab * t);
    }

    // the map's breakables near these points broken (a vent cover, a window the players went through). Nuke's vent is a
    // prop_dynamic named nuke_vent (448 -1403 -416), not a func_breakable
    void Break(List<Vector3> pts, float r = 72f)
    {
        var n = 0;
        foreach (var cls in new[] { "func_breakable", "func_breakable_surf", "prop_dynamic" })
            foreach (var e in Utilities.FindAllEntitiesByDesignerName<CBaseEntity>(cls))
            {
                if (!e.IsValid || e.AbsOrigin == null) continue;
                var name = (e.Entity?.Name ?? "").ToLowerInvariant();
                // its model's name too (29/10, Cache's two vents: prop_dynamic with no name, models/de_cache_s2/newvent/newvent.vmdl;
                // the user: "les vents ... pas cassées alors que dans la situation réelle elles sont supposées être cassées")
                if (cls == "prop_dynamic") name += " " + (e.CBodyComponent?.SceneNode?.GetSkeletonInstance()?.ModelState.ModelName ?? "").ToLowerInvariant();
                if (cls == "prop_dynamic" && (e.Health <= 0 || !(name.Contains("vent") || name.Contains("window") || name.Contains("glass")))) continue;
                var o = new Vector3(e.AbsOrigin.X, e.AbsOrigin.Y, e.AbsOrigin.Z);
                if (pts.Any(p => Vector3.DistanceSquared(p, o) < r * r)) { e.AcceptInput("Break"); n++; Log("broken: {c} {n}", cls, name); }
            }
        if (n > 0) Log("{n} breakable(s) broken", n);
    }

    // a path's point at a (fractional) frame
    static Vector3 PathAt(Track t, float ft)
    {
        var i = Math.Clamp((int)ft, 0, Math.Max(0, t.Frames - 2));
        return t.Frames < 2 ? Pos(t, 0) : Vector3.Lerp(Pos(t, i), Pos(t, i + 1), Math.Clamp(ft - i, 0f, 1f));
    }

    // a bot leaves its recorded path and plays on its own: it moves again by itself, with its grenades
    void Free(int slot, CCSPlayerController c, Track t)
    {
        if (drill?.Mode == "crossfire" && phase == "live" && CfPlant(c, t)) return;   // Crossfire: it stops there and fights you (14/10)
        if (!free.Add(slot)) return;
        if (FightScripted(slot, c, t)) return;   // css_scripted: it fights by the plugin's hand, not the game's AI
        var pw = c.PlayerPawn.Value;
        if (pw != null && pw.IsValid) Freeze(pw, false);
        if (phase == "live") Arm(c, t);
        // the planter off its way before the plant: it carries the bomb, the game's AI plants it if it lives (06/10: "il
        // n'y avait personne sur le B, impossible qu'ils plantent: le seul qui allait planter est mort")
        if (phase == "live" && cur?.Bomb is { F: > 0 } b && !bombDone && t.Sid == b.By && t.Team == 2)
        { c.GiveNamedItem("weapon_c4"); bombDone = true; Log("{n} plays on its own with the bomb", t.Name); }
    }

    // a bot playing on its own: its grenades back (the AI throws them). A situation: the ones it had in the match; a
    // defense's attacker: a flash and a molotov
    void Arm(CCSPlayerController? c, Track t)
    {
        if (c == null || !c.IsValid || !c.PawnIsAlive) return;
        var nades = t.Weapons.Where(w => w.Contains("grenade") || w.Contains("flashbang") || w.Contains("molotov")).ToList();
        if (nades.Count == 0 && drill?.Mode == "defend") nades = new() { "weapon_flashbang", t.Team == 2 ? "weapon_molotov" : "weapon_incgrenade" };
        foreach (var w in nades) c.GiveNamedItem(w);
    }

    static Vector3 Pos(Track t, int i) => new(t.Path[i * 5], t.Path[i * 5 + 1], t.Path[i * 5 + 2]);

    // 17/10 (the self-test: 2 of 3 bots put back up or down were where the real player had jumped, onto a box, a ledge,
    // over a rail: the bot ran into it while its way went 57 u up, then a teleport): the jumps of its way, read from its
    // height alone. A takeoff from flat ground, its peak 30 to 75 u up 0.19 to 0.5 s later, then down again (a stair goes
    // on up). Not from a rush's 0.5 s samples
    List<(int F, float Rise)> JumpsOf(Track t)
    {
        if (t.Jumps != null && ReferenceEquals(t.JumpsFor, t.Path)) return t.Jumps;
        var js = new List<(int F, float Rise)>();
        var fps = (cur?.Rate ?? 64) / (float)Math.Max(1, cur?.Step ?? 2);
        if (fps >= 16f)
        {
            float Z(int k) => t.Path[k * 5 + 2];
            int lo = (int)(0.19f * fps), hi = (int)(0.5f * fps), look = (int)(0.65f * fps);
            int back = Math.Max(2, (int)(0.1f * fps)), down = Math.Max(3, (int)(0.2f * fps));
            for (var k = back; k < t.Frames - lo; k++)
            {
                if (Z(k + 1) - Z(k) <= 96f / fps || Math.Abs(Z(k) - Z(k - back)) >= 6f) continue;
                var m = k;
                for (var j = k + 1; j <= Math.Min(t.Frames - 1, k + look); j++) if (Z(j) > Z(m)) m = j;
                var rise = Z(m) - Z(k);
                var after = Math.Min(t.Frames - 1, m + down);
                // down again after its peak, or slowing as a thrown body does (its first half twice its second: a crouch-
                // jump onto a box landed at its peak; a stair climbs evenly)
                var ballistic = Z(k + (m - k) / 2) - Z(k) >= 1.8f * (Z(m) - Z(k + (m - k) / 2));
                if (m - k < lo || m - k > hi || rise < 30f || rise > 75f || (after - m == down && Z(after) > Z(m) - 3f && !ballistic)) continue;
                js.Add((k, rise));
                k = m;
            }
        }
        t.JumpsFor = t.Path;
        t.JumpDone = -1;
        return t.Jumps = js;
    }

    // the jump of its way it has come to: at its takeoff by its own pace (a bot behind its way's clock jumps where the
    // player did, not when), the height it rises; null when none
    float? JumpHere(Track t, int i, Vector3 here, float speed)
    {
        var fps = cur!.Rate / (float)cur.Step;
        foreach (var (k, rise) in JumpsOf(t))
        {
            if (k <= t.JumpDone) continue;
            if (k > i + (int)(0.5f * fps)) break;   // far ahead of it yet
            if (k < i - (int)fps) { t.JumpDone = k; continue; }   // a second behind: let go
            var p = Pos(t, k);
            if (Math.Abs(p.Z - here.Z) > 24f) continue;   // not on that level
            var q = Pos(t, Math.Min(t.Frames - 1, k + 2)) - Pos(t, Math.Max(0, k - 2));
            var dir = new Vector2(q.X, q.Y);
            var rel = new Vector2(here.X - p.X, here.Y - p.Y);
            var reach = Math.Max(10f, speed * 2.5f / 64f);   // two ticks and a half of its run
            var at = dir.Length() < 8f
                ? rel.Length() <= 16f   // a jump on the spot
                : Vector2.Dot(rel, Vector2.Normalize(dir)) >= -reach && Math.Abs(rel.X * dir.Y - rel.Y * dir.X) / dir.Length() < 56f;   // beside its way by what it jumped onto (Inferno's Banana: 41 u)
            if (!at) continue;
            t.JumpDone = k;
            return rise;
        }
        return null;
    }

    // its way climbs or comes down on the spot there (a ladder): no legs climb one, it is carried along its way
    static bool Climbing(Track t, int i, int half)
    {
        var a = Pos(t, Math.Max(0, i - half));
        var b = Pos(t, Math.Min(t.Frames - 1, i + half));
        var dz = Math.Abs(b.Z - a.Z);
        return dz > 20f && new Vector2(b.X - a.X, b.Y - a.Y).Length() < 0.5f * dz;
    }
    static Vector3 Ang(Track t, int i) => new(t.Path[i * 5 + 4], t.Path[i * 5 + 3], 0);

    // everyone on the first frame, loadouts of the demo, 3 s to look around, then it plays. The doors the real players
    // went through are open (04/10: shot through a door that was open for them in the match, closed here). A bot on
    // its path walks it (OnTick); an aim target holds its spot without moving
    void Place()
    {
        if (cur == null) return;
        // a defense's later waves too: their ways are its other tracks (17/10, the self-test: Nuke's attackers stuck at
        // the ramp's doors, closed for every way but the first wave's)
        var ways = cur.Players.Select(t => t.Path).Concat(drill?.Tracks.Select(x => x.Path) ?? Enumerable.Empty<float[]>());
        var went = ways.SelectMany(p => Enumerable.Range(0, p.Length / 5).Select(k => new Vector3(p[k * 5], p[k * 5 + 1], p[k * 5 + 2])))
            .Concat(cur.Trail.Where(p => p.Length >= 3).Select(p => new Vector3(p[0], p[1], p[2]))).ToList();   // every frame: a door's leaf is 2 u thick
        OpenDoors(went);
        OpenGates(went);
        navBlocked.Clear(); navProg.Clear();   // the passages found shut: anew with this drill's doors (Nav.cs)
        Break(went.Where((_, k) => k % 4 == 0).ToList());   // a vent the players went through was broken (06/10, Nuke: "la vent est censée être cassée")
        foreach (var (slot, t) in bots)
        {
            var c = Utilities.GetPlayerFromSlot(slot);
            if (c == null || !c.IsValid) continue;
            if (!c.PawnIsAlive) c.Respawn();
            Loadout(c, t);
            t.NadeNext = 0;
            var pw = c.PlayerPawn.Value;
            if (pw == null) continue;
            pw.Teleport(Pos(t, 0), Upright(Ang(t, 0)), Vector3.Zero);
            // a boost's teammate walking, still by bot_zombie (27/10 21:24, Dust2's Top Mid: on a frozen one, the game had you
            // off the ground at 64 shots of 66, the AWP's in-air spread; the 16 u put-back alone did not change it)
            Freeze(pw, t.Hold && t.Sid != "mate");
            ForgetMotion(slot);
        }
        var me = cur.Players.FirstOrDefault(t => t.Me);
        if (drill?.Mate != null)   // 24/10: a boost's player left at the spawn, what happens told
            foreach (var h in Humans())
            {
                var hh = h;
                Log("place: boost, you team {t} (drill's {d}), mode {m}, to {p}", (int)h.Team, me?.Team ?? -1, mode, me == null ? "-" : R3(Pos(me, 0)));
                AddTimer(0.6f, () => { var o = hh.PlayerPawn.Value?.AbsOrigin; if (o != null) Log("place: boost, you at {x:F0} {y:F0} {z:F0}", o.X, o.Y, o.Z); });
            }
        if (mode == "actor" && me != null)
            foreach (var h in Humans())
            {
                if ((int)h.Team != me.Team) continue;
                if (!h.PawnIsAlive) h.Respawn();
                Loadout(h, me, cur.Kind is "death" or "clutch" ? Math.Max(MinHp, me.Hp) : null);
                var pawn = h.PlayerPawn.Value;
                if (pawn == null) continue;
                // a boost: 10 u over the teammate's head, dropped onto it (24/10, the real test of Mirage's Short boost: put
                // 0.5 u over the crouched one's top, both boxes touching, the move refused and you left at your spawn).
                // Over its STANDING head at least (28/10, lab 4, Dust2's Top Mid: put 10 u over the crouched one's top before
                // it had crouched, inside its standing box: both stuck, your feet 8.5 u in its head, never on the ground)
                var mz = drill?.Mate?.Pos is { Length: >= 3 } mp3 ? mp3[2] : float.NaN;
                var up = drill?.Mate != null ? new Vector3(0f, 0f, float.IsNaN(mz) ? 10f : Math.Max(10f, mz + 72f + 4f - Pos(me, 0).Z)) : Vector3.Zero;
                pawn.Teleport(Pos(me, 0) + up, Upright(Ang(me, 0)), Vector3.Zero);
                Freeze(pawn, true);
                if (drill?.Mate == null) continue;
                // a boost: held over it while the teammate settles and crouches, then put 2 u over its box's real top and let go
                // (28/10, lab 5: on a crouched one settled on the floor, put 10 u to -0.3 u over its top, you were on the
                // ground 63 ticks of 63; dropped on it while it crouched under you it rose 9 u into your feet)
                var hp = pawn; var at = Pos(me, 0); var ang = Upright(Ang(me, 0)); var gen = generation;
                AddTimer(0.5f, () =>
                {
                    if (gen != generation || !hp.IsValid) return;
                    var mt = bots.FirstOrDefault(b => b.Value.Sid == "mate");
                    var ms = mt.Value == null ? null : Utilities.GetPlayerFromSlot(mt.Key)?.PlayerPawn.Value;
                    // crouched just after its teleport (off the ground for the game) it went 9 u up and stayed there (28/10, lab 6:
                    // z 9.2-10.9 on a 0.2-1.9 spot, your head in Top Mid's arch): back on its spot first
                    if (ms?.AbsOrigin is { } mo0 && mt.Value != null && mo0.Z - Pos(mt.Value, 0).Z > 2f) ms.Teleport(Pos(mt.Value, 0), null, Vector3.Zero);
                    AddTimer(0.25f, () =>
                    {
                        if (gen != generation || !hp.IsValid) return;
                        var ok = ms is { IsValid: true, AbsOrigin: not null, Collision: not null };
                        var z = ok ? ms!.AbsOrigin!.Z + ms.Collision!.Maxs.Z + 2f : at.Z + 10f;
                        hp.Teleport(new Vector3(at.X, at.Y, z), ang, Vector3.Zero);
                        Freeze(hp, false);
                        Log("place: boost, you over its top at {z:F1} (its z {m:F1}, maxs {x:F1})", z, ok ? ms!.AbsOrigin!.Z : 0f, ok ? ms!.Collision!.Maxs.Z : 0f);
                    });
                });
            }
        LookSay(); WalkSay(); MoveSay(); BehSay(); roams.Clear(); utilDone.Clear(); sideSeen[2].Clear(); sideSeen[3].Clear(); sideHeard[2].Clear(); sideHeard[3].Clear();
        fighters.Clear(); fightTries = 0; lookNow.Clear(); lookPick.Clear(); wayEyes.Clear(); wayK.Clear(); walkAsk.Clear(); wayBackAt.Clear(); huntProg.Clear(); navWay.Clear(); knifeOut.Clear(); sitHunt = false; foeSeenOnce = false; sitExch = -1;
        if (scripted) { LookLoad(); MoveLoad(); BehLoad(); NavLoad(); }   // where bots look and what they do there, for this map (Look.cs, Move.cs, Behavior.cs)
        kills = dmg = 0; devSum = 0; devN = 0;
        humanDead = traded = false; tradeKiller = -1;
        // the demo's plant: already down at the start, or later by its planter (yours later: you plant it yourself)
        bombLive = false;
        bombDone = cur.Bomb == null || (cur.Bomb.F > 0 && mode == "actor" && cur.Players.Any(t => t.Me && t.Sid == cur.Bomb.By));
        SessionPlaced();
        phase = "countdown";
        var cd = cur.Kind is "death" or "clutch" ? 5 : 3;   // a situation: time to read it and get ready
        countdownEnd = Server.TickCount + cd * 64;
        var g = generation;
        for (int s = cd; s >= 1; s--)
        {
            var n = s;
            AddTimer(cd - n, () => { if (g == generation && !SessionCount(n)) foreach (var h in Humans()) h.PrintToCenter($"{cur?.Title}   {n}"); });
        }
    }

    void Go()
    {
        // a situation whose enemies are all dead already (a bot that left): not a win, set up again (once)
        if (mode == "actor" && cur is { Kind: "death" or "clutch" })
        {
            var foes = bots.Where(b => b.Value.Team != cur.Team).Select(b => Utilities.GetPlayerFromSlot(b.Key)).ToList();
            if (foes.Count > 0 && foes.All(c => c == null || !c.IsValid || !c.PawnIsAlive))
            {
                Log("{id}: no enemy alive at the start, set up again", cur.Id);
                if (emptyTries++ < 1) { builtFor = null; Setup(); return; }
                emptyTries = 0;   // still none: skipped, never a win for nothing
                if (sess != null && drill != null) { phase = "live"; DrillDone(false, "skipped", 0, "no enemy at the start"); return; }
            }
            emptyTries = 0;
        }
        phase = "live";
        t0 = Server.TickCount;
        nextNade = 0;
        if (cur?.Bomb is { F: <= 0 } && !bombDone) PlantBomb();   // after the plant: it ticks from the first second
        // an aim drill: a reaction time before a target can hurt you (04/10, Office: killed 0.06 s after GO)
        if (cur?.Kind == "aim") protectUntil = Server.TickCount + 48;
        SessionGo();
        foreach (var h in Humans()) { var pw = h.PlayerPawn.Value; if (pw != null) Freeze(pw, false); h.PrintToCenter(T("GO")); }
    }

    bool Alive(string sid)
    {
        if (gone.Contains(sid)) return false;
        return true;
    }

    // the bots as they are, for the real-client test that plays the drills in his own game (22/10 eve, tools/real_client.py,
    // out/selftest/logs/play_module.py): coach/bots_live.json, 16 times a second while a drill is live (the server's own
    // state, written by the plugin: nothing read from the game's memory)
    int botsLiveAt, botsLiveBusy;
    readonly List<Dictionary<string, object?>> meImpacts = new(), meHits = new(), meRawImpacts = new();
    int meImpactTick = -1;

    // your bullet by one of the plugin's bots (160 u): it turns to you as a player turns to a shot that missed him by a little
    // (30/10, the user: "ils ne réagissent pas quand je leur tire dessus ou quand je tire à côté")
    void ShotNear(CCSPlayerController h, Vector3 at, Vector3 from)
    {
        // never a crossfire's: its enemies wait behind their cover for their peek (30/10, his review: the spray's second one
        // stopped where his spray at the first one landed, never out, "plus de balles")
        if (!ScriptedDrill || phase != "live" || drill?.Mode == "crossfire") return;
        foreach (var (sl, t) in bots.ToList())
        {
            if (t.Team == h.TeamNum || Utilities.GetPlayerFromSlot(sl) is not { IsValid: true, PawnIsAlive: true } c || c.PlayerPawn.Value?.AbsOrigin is not { } bo) continue;
            if (Vector3.Distance(new Vector3(bo.X, bo.Y, bo.Z + 36f), at) > 160f) continue;
            if (!fighters.ContainsKey(sl) && !t.Strafe) Free(sl, c, t);
            if (fighters.TryGetValue(sl, out var fh))
            { fh.HurtBy = h.Slot; fh.HurtAt = Server.TickCount; fh.Last = from; fh.HasLast = true; fh.LastSeen = Server.TickCount; }
        }
    }

    void MeImpact(EventBulletImpact e)
    {
        if (e.Userid is not { IsValid: true, IsBot: false } h || h.PlayerPawn.Value is not { AbsOrigin: { } mo } mpw) return;
        ShotNear(h, new Vector3(e.X, e.Y, e.Z), new Vector3(mo.X, mo.Y, mo.Z + 62f));
        var now = Server.TickCount;
        if (now == meImpactTick) return;   // a bullet through a wall: its first impact only
        meImpactTick = now;
        var eye = new Vector3(mo.X, mo.Y, mo.Z + (mpw.ViewOffset?.Z ?? 64f));
        var d = new Vector3(e.X, e.Y, e.Z) - eye;
        var len = d.Length();
        if (len < 1f) return;
        var u = d / len;
        // the impact itself and the eyes it left from (27/10: which view a shot sent right after a setang took)
        meRawImpacts.Add(new() { ["t"] = now, ["at"] = new[] { R1(e.X), R1(e.Y), R1(e.Z) }, ["eye"] = new[] { R1(eye.X), R1(eye.Y), R1(eye.Z) },
            ["yaw"] = R1(MathF.Atan2(u.Y, u.X) * 180f / MathF.PI), ["pitch"] = R1(-MathF.Asin(Math.Clamp(u.Z, -1f, 1f)) * 180f / MathF.PI),
            ["eyeang"] = mpw.EyeAngles is { } ea0 ? new[] { R1(ea0.X), R1(ea0.Y) } : null });
        if (meRawImpacts.Count > 12) meRawImpacts.RemoveAt(0);
        var side = Vector3.Normalize(new Vector3(u.Y, -u.X, 0));   // to the right as you look along it
        Dictionary<string, object?>? best = null;
        var bestMiss = float.MaxValue;
        foreach (var c in Utilities.GetPlayers())
        {
            if (c is not { IsValid: true, IsBot: true } || !c.PawnIsAlive || c.TeamNum == h.TeamNum || c.PlayerPawn.Value is not { AbsOrigin: { } o } pw) continue;
            var head = new Vector3(o.X, o.Y, o.Z + (pw.ViewOffset?.Z ?? 64f) - 2f);
            var along = Vector3.Dot(head - eye, u);
            if (along <= 0) continue;
            var miss = eye + u * along - head;   // where the line went by, from the head's centre (not rewound to your view)
            if (miss.Length() >= bestMiss) continue;
            bestMiss = miss.Length();
            best = new() { ["t"] = now, ["slot"] = c.Slot, ["across"] = R1(Vector3.Dot(miss, side)), ["up"] = R1(miss.Z), ["dist"] = R1(along),
                ["wall"] = len < along - 16f };
        }
        if (best == null) return;
        meImpacts.Add(best);
        if (meImpacts.Count > 12) meImpacts.RemoveAt(0);
    }


    void BotsLive()
    {
        var now = Server.TickCount;
        var me = Humans().FirstOrDefault();
        var mePw = me?.PlayerPawn.Value;
        var shots = mePw?.ShotsFired ?? 0;   // a spray on: every tick, its recoil followed (26/10)
        if ((now - botsLiveAt < (shots > 0 ? 1 : 2) && now >= botsLiveAt) || sess == null || phase != "live") return;   // 32 a second
        if (Interlocked.Exchange(ref botsLiveBusy, 1) == 1) return;
        botsLiveAt = now;
        // your eyes, for a bullet's line to each of them (23/10: the game's spotting stays on a while after one is gone:
        // the test shot magazines into walls)
        CVector? meEye = mePw?.AbsOrigin is { } mo ? new CVector(mo.X, mo.Y, mo.Z + (mePw.ViewOffset?.Z ?? 64f)) : null;
        var shotLine = new TraceOptions { InteractsWith = Masks.ShotBrushOnly };
        var rows = new List<Dictionary<string, object?>>();
        foreach (var c in Utilities.GetPlayers())
        {
            if (c is not { IsValid: true, IsBot: true } || !c.PawnIsAlive || c.PlayerPawn.Value is not { AbsOrigin: { } o } pw) continue;
            var duck = pw.MovementServices == null ? 0f : new CCSPlayer_MovementServices(pw.MovementServices.Handle).DuckAmount;
            // seen by you: the game's own spotting (its radar's line of sight)
            var seen = me != null && me.Slot < 64 && (pw.EntitySpottedState.SpottedByMask[me.Slot / 32] & (1u << (me.Slot % 32))) != 0;
            var eye = o.Z + (pw.ViewOffset?.Z ?? (64f - 18f * duck));   // its eyes: where its head is
            // what of it a bullet of yours gets to now: its head, else its chest (nothing in between but players)
            string? los = null;
            var chest = false;   // its chest in your line too (27/10, Cache's Quad spray: aimed at a chest behind a crate, 14 bullets in it)
            float[]? part = null;   // neither: the first of its other parts a bullet gets to (27/10, Anubis's Canals boost: its
            // second one 10 s in the base's sight from there, head and chest behind a crate, never shot at)
            if (meEye != null && me!.PawnIsAlive)
            {
                chest = Trace.TraceEndShape(meEye, new CVector(o.X, o.Y, eye - 22f), mePw!, shotLine).Fraction > 0.98f;
                if (Trace.TraceEndShape(meEye, new CVector(o.X, o.Y, eye - 2f), mePw!, shotLine).Fraction > 0.98f) los = "head";
                else if (chest) los = "chest";
                else
                {
                    var sx = meEye.Y - o.Y; var sy = -(meEye.X - o.X); var sn = MathF.Max(1f, MathF.Sqrt(sx * sx + sy * sy));
                    foreach (var (up, side) in new[] { (-12f, 11f), (-12f, -11f), (-36f, 0f), (-46f, 0f), (-56f, 0f) })
                    {
                        var q = new CVector(o.X + side * sx / sn, o.Y + side * sy / sn, eye + up);
                        if (Trace.TraceEndShape(meEye, q, mePw!, shotLine).Fraction > 0.98f) { los = "body"; part = new[] { R1(q.X), R1(q.Y), R1(q.Z) }; break; }
                    }
                }
            }
            rows.Add(new() { ["slot"] = c.Slot, ["name"] = c.PlayerName, ["team"] = c.TeamNum, ["pos"] = new[] { R1(o.X), R1(o.Y), R1(o.Z) }, ["duck"] = MathF.Round(duck, 2),
                ["eye"] = R1(eye), ["seen"] = seen, ["los"] = los, ["chest"] = chest, ["part"] = part, ["hp"] = pw.Health,
                // its speed now, the server's (02/11: the driver's from two reads lagged a bot slowing to shoot, its MAG-7
                // led 30-35 u past them at 150 u)
                ["vel"] = pw.AbsVelocity is { } bv ? new[] { R1(bv.X), R1(bv.Y), R1(bv.Z) } : null,
                // its body's top for the game (28/10, the user on the boosts: "vérifie que le joueur n'est pas un tout petit peu
                // en conflit avec la tête du bot en dessous"): its collision box's height over its feet
                ["top"] = pw.Collision is { } cb ? R1(o.Z + cb.Maxs.Z) : null });
        }
        // your recoil as the server has it (26/10, his order: "perfectionne-toi sur toute la partie spray"): a bullet leaves
        // along your eyes plus twice the aim punch (weapon_recoil_scale), its base at its tick and how fast it moves
        float[]? punch = null, punchVel = null;
        int punchTick = 0;
        if (mePw?.AimPunchServices is { } aps)
        {
            punch = new[] { MathF.Round(aps.PredictableBaseAngle.X, 3), MathF.Round(aps.PredictableBaseAngle.Y, 3) };
            punchVel = new[] { MathF.Round(aps.PredictableBaseAngleVel.X, 3), MathF.Round(aps.PredictableBaseAngleVel.Y, 3) };
            punchTick = aps.PredictableBaseTick;
        }
        var json = JsonSerializer.Serialize(new Dictionary<string, object?> { ["t"] = now, ["drill"] = drill?.Id, ["mode"] = drill?.Mode, ["kind"] = cur?.Kind,
            ["me_team"] = me?.TeamNum, ["me_alive"] = me?.PawnIsAlive ?? false, ["me_scoped"] = mePw?.IsScoped ?? false,
            ["me_hp"] = mePw?.Health,   // your health (02/11: the driver hides once hurt, as a player does)
            ["me_shots"] = shots, ["me_punch"] = punch, ["me_punch_vel"] = punchVel, ["me_punch_tick"] = punchTick,
            ["me_ang"] = mePw?.EyeAngles is { } ea ? new[] { MathF.Round(ea.X, 3), MathF.Round(ea.Y, 3) } : null, ["bots"] = rows,
            ["me_impacts"] = meImpacts.ToList(), ["me_hits"] = meHits.ToList(), ["me_raw_impacts"] = meRawImpacts.ToList(),
            ["me_eye"] = meEye is { } me3 ? new[] { R1(me3.X), R1(me3.Y), R1(me3.Z) } : null,   // where your bullets leave from (26/10: getpos's height checked)
            // what is in your hands and its clip (27/10, Fachwerk's situation: shots with no bullet out, its clip empty,
            // the test never reloaded)
            ["me_weapon"] = mePw?.WeaponServices?.ActiveWeapon.Value?.DesignerName, ["me_clip"] = mePw?.WeaponServices?.ActiveWeapon.Value?.Clip1,
            // how long before it can fire (s): a gun just drawn can't (30/10, round 13, Boulder's R8: the knife put away, three
            // Deagle shots in its draw, no bullet out)
            ["me_ready"] = mePw?.WeaponServices?.ActiveWeapon.Value is { IsValid: true } aw0 ? MathF.Round(MathF.Max(0f, (aw0.NextPrimaryAttackTick - Server.TickCount) / 64f), 2) : null,
            // your speed (27/10, Nuke's Outside boost: scoped AWP shots 100-240 u off at 1888 u, the feet sliding on the head?)
            ["me_vel"] = mePw?.AbsVelocity is { } mv ? new[] { R1(mv.X), R1(mv.Y), R1(mv.Z) } : null,
            // on the ground for the game (27/10, Inferno's Banana boost on a crouched mate: AK taps 50-140 u off at 1034 u
            // standing still, as if in the air)
            ["me_ground"] = mePw != null && (mePw.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0,
            // how you move and what you stand on for the game (28/10, the boosts: off the ground on a bot's head at every
            // shot; the user: "est-ce que c'est le jeu ... qui considère qu'on est en l'air", a noclip left by an Alt-Tab?)
            ["me_move"] = mePw?.MoveType.ToString(), ["me_gent"] = mePw?.GroundEntity?.Value?.DesignerName,
            ["me_feet"] = mePw?.AbsOrigin is { } mf ? R1(mf.Z) : null, ["me_mins"] = mePw?.Collision is { } mc ? R1(mc.Mins.Z) : null,
            // the planted bomb (27/10, Inferno's R16 situation: 2 kills, then the bomb blew, the test never went to it)
            ["bomb"] = BombLive(),
            // a defense: the post held now (its index; its count: the free part) and the bombsite's own box (30/10, the user:
            // "si c'est zone libre, ben le bon site"): the test driver moves in it to take its duels one by one
            ["post"] = drill?.Mode == "defend" ? postIdx : null,
            ["site_box"] = drill?.Mode == "defend" && SiteBox() is { } sbx ? new[] { R1(sbx.Lo.X), R1(sbx.Lo.Y), R1(sbx.Lo.Z), R1(sbx.Hi.X), R1(sbx.Hi.Y), R1(sbx.Hi.Z) } : null });
        if (!Io(() =>
            {
                try
                {
                    var f = System.IO.Path.Combine(Dir, "bots_live.json");
                    File.WriteAllText(f + ".tmp", json);
                    File.Move(f + ".tmp", f, true);
                }
                catch (Exception) { }
                finally { botsLiveBusy = 0; }
            })) botsLiveBusy = 0;
    }

    void OnTick()
    {
        while (toGame.TryDequeue(out var back)) { try { back(); } catch (Exception e) { Log("io: {m}", e.Message); } }
        try { BeamTick(); } catch (Exception e) { Log("beams: {m}", e.Message); }
        // the center text (the drill's card) blinks off every second while the game rules say a restart is
        // pending: set on every tick (CS2FlashingHtmlHudFix, the workaround found by Poggu)
        rules ??= Utilities.FindAllEntitiesByDesignerName<CCSGameRulesProxy>("cs_gamerules").FirstOrDefault()?.GameRules;
        if (rules != null) rules.GameRestart = rules.RestartRoundTime < Server.CurrentTime;
        var now = Server.TickCount;
        if (now - lastBeat >= 64 || now < lastBeat) { lastBeat = now; Beat(); }   // the tick count starts over with each map
        if (now < hudSent) hudSent = 0;
        HudTick();
        CamTick();
        BotsLive();
        CfRadar();   // a Crossfire enemy shown at a rep's start: on your radar too
        if (cur == null || (phase != "countdown" && phase != "live")) return;
        if (phase == "countdown" && now >= countdownEnd) Go();
        var f = phase == "live" ? (now - t0) / (float)cur.Step : 0f;
        var mePawn = Humans().Select(h => h.PlayerPawn.Value).FirstOrDefault(p => p != null && p.IsValid && p.LifeState == (byte)LifeState_t.LIFE_ALIVE);
        uint[]? seen = null;
        if (mePawn != null && mode == "actor") { var m = mePawn.EntitySpottedState.SpottedByMask; seen = new[] { m[0], m[1] }; }
        if (seen != null)
            foreach (var sl in bots.Keys)
                if ((seen[sl / 32] & (1u << (sl % 32))) != 0) sawYou[sl] = now;
        BehSightTick();   // what each side sees of the other (Behavior.cs)
        FightTick(mePawn, seen);   // the bots fighting by the plugin's hand (Combat.cs)
        BotRecTick();   // css_botrec (BotRec.cs)
        if (phase == "live") StepSounds();   // the bots' running steps (Behavior.cs)
        var lookSmokes = scripted && lookTab.Count > 0 ? SmokesUp() : null;   // for where they look (Look.cs)
        var sightSmokes = lookSmokes ?? (ScriptedDrill ? SmokesUp() : null);   // for what they see (Combat.cs)
        Vector3? mePos = mode == "actor" && mePawn?.AbsOrigin is { } mo ? new Vector3(mo.X, mo.Y, mo.Z) : null;
        var meSid = cur.Players.FirstOrDefault(t => t.Me)?.Sid ?? "";
        int maxFrames = 0;
        foreach (var (slot, t) in bots)
        {
            maxFrames = Math.Max(maxFrames, t.Frames);
            if (free.Contains(slot) || gone.Contains(t.Sid)) continue;
            var c = Utilities.GetPlayerFromSlot(slot);
            var pawn = c?.PlayerPawn.Value;
            if (c == null || pawn == null || !c.PawnIsAlive)
            {   // why, at a drill's very start (26/10: a boost's target gone at 0, killed by the world 8 s later: alive by then)
                gone.Add(t.Sid);
                Log("gone {n} at {f}{why}", t.Name, (int)f, f < 1 ? $" ({(c == null ? "no player" : pawn == null ? "no pawn" : $"life {pawn.LifeState}, hp {pawn.Health}, at {R3(pawn.AbsOrigin is { } go ? new Vector3(go.X, go.Y, go.Z) : Vector3.Zero)[2]}")})" : "");
                continue;
            }
            if (t.Strafe) continue;   // an aim map's strafing target: the session moves it
            if (cfJiggling.Contains(slot)) continue;   // a Crossfire jiggle: it moves it itself (Crossfire.cs)
            if (t.Hold)
            {
                // a target on its spot. A prefire's, a wallbang's or a flick's holds its angle and never fires (06/10: "fais
                // pas bouger les bots sur le préfire"); a duel's aims on its own and counts how long it has seen you
                // put back only once it drifted: a teleport every tick also moved the ground under the one standing on a
                // boost's bot, likely counted as in the air then (11/10, a tester: "22 boost didnt work. Scoped weapons
                // are odd": a sniper's shot in the air goes anywhere)
                var at0 = pawn.AbsOrigin;
                // a boost's teammate: 16 u (27/10, the plugin's own on-ground flag: up on a crouched one you were off the
                // ground at every shot, its 2 u put-back moving it under you)
                if (at0 == null || Vector3.DistanceSquared(new Vector3(at0.X, at0.Y, at0.Z), Pos(t, 0)) > (t.Sid == "mate" ? 256f : 4f))
                    pawn.Teleport(Pos(t, 0), t.Still ? Upright(Ang(t, 0)) : null, Vector3.Zero);
                if (t.Still) HoldAim(pawn, Ang(t, 0), t.Duck);
                else if (phase == "live" && seen != null && (seen[slot / 32] & (1u << (slot % 32))) != 0) contact[slot] = contact.GetValueOrDefault(slot) + 1;
                continue;
            }
            var ft = f - t.Start;
            var i = Math.Max(0, (int)ft);
            // a defense's attacker throws the grenades of the real hit it walks, at their moment
            // only from where the real player threw it (96 u of its eyes; it waits 1.5 s at most to get there, else none): 29/10,
            // lab 24, walking as a player, slower than the real one, it was in the blast of its own HE, killed by it twice
            while (phase == "live" && t.NadeNext < t.TrackNades.Count && t.TrackNades[t.NadeNext].F <= ft)
            {
                var nd = t.TrackNades[t.NadeNext];
                var eyeAt = pawn.AbsOrigin is { } no ? new Vector3(no.X, no.Y, no.Z + 64f) : Vector3.Zero;
                // none on you in your first 10 s at a post (30/10, his review on Inferno's A: "je spawn à l'endroit qui se fait
                // stuff", two smokes popped on Top Mid as he got there)
                if (drill?.Mode == "defend" && Server.TickCount - postAt < 10 * 64 && NadeLandsNear(nd, pawn, DefendSpot(), 350f))
                { Log("nade {t} of {n} not thrown: on your spot as you got there", nd.Type, t.Name); t.NadeNext++; }
                else if (Vector3.Distance(eyeAt, new Vector3(nd.P[0], nd.P[1], nd.P[2])) < 96f) { ThrowAs(c, pawn, nd); t.NadeNext++; }
                else if (ft - nd.F > 1.5f * cur.Rate / cur.Step) { Log("nade {t} of {n} not thrown: not where it was thrown from", nd.Type, t.Name); t.NadeNext++; }
                else break;   // not there yet
            }
            if (i >= t.Frames - 1 && drill?.Mode == "defend" && sess != null && !engaged.ContainsKey(slot)
                && !(mePos is { } mp0 && pawn.AbsOrigin is { } bo && Vector3.Distance(mp0, new Vector3(bo.X, bo.Y, bo.Z)) < 1200))
            {   // a defense's attacker at the end of its way far from you: another one comes on a real way (06/10: "un mec
                // dans mon spawn, derrière": it roamed on its own). A post's way ends at the post (09/10): one near you
                // there plays on and fights you ("si je ne les tue pas quand ils passent devant moi, après ils ne sont plus là")
                gone.Add(t.Sid);
                pawn.CommitSuicide(false, true);
                Log("again {n} at {f}", t.Name, (int)f);
                continue;
            }
            if (i >= t.Frames - 1)
            {
                // the end of its recorded path: a death in the demo (by a player still alive here, or the world), or the
                // window is over / you were the killer: the bot plays on from there
                if (t.Death >= 0 && t.Killer != meSid && (t.Killer == "" || !cur.Players.Any(q => q.Sid == t.Killer) || Alive(t.Killer)))
                { DemoKill(c, pawn, t); gone.Add(t.Sid); Log("demo kill {n} at {f}", t.Name, (int)f); }
                else { Free(slot, c, t); Log("free {n} at {f} (death {d}, killer {k})", t.Name, (int)f, t.Death, t.Killer); }
                continue;
            }
            var a = Math.Clamp(ft - i, 0f, 1f);
            var p0 = Pos(t, i); var p1 = Pos(t, i + 1);
            var pos = Vector3.Lerp(p0, p1, a);
            if (phase == "live" && mode == "spec" && pawn.AbsOrigin != null)
            { var o = pawn.AbsOrigin; devSum += Vector3.Distance(new Vector3(o.X, o.Y, o.Z), pos); devN++; }
            // it has seen you for a reaction time: it fights you now, its aim is the game's. For 1.5 s it still moves the
            // way the real player moved there (his peek, his strafe, his stop: 06/10, "les bots ne se déplacent pas comme des
            // joueurs"), then it plays on its own
            var eng = engaged.TryGetValue(slot, out var et);
            if (eng && Server.TickCount - et > EngageTicks) { Free(slot, c, t); continue; }
            // your teammates never come in contact with you (29/10, lab 14: a teammate of the plugin's hand saw you, fought,
            // found no enemy, went on its way at its start again, every 1.5 s)
            var spots = seen != null && (seen[slot / 32] & (1u << (slot % 32))) != 0;
            // css_scripted: it sees you as it does in its fight (29/10, the user: "un espèce de on-off"): you in front of its
            // eyes, no smoke on the line, tick after tick. On the game's spotting alone it was freed with you behind it or in a
            // smoke, stood staring at a wall, went on its way 1.5 s later and was freed again 0.2 s after
            if (ScriptedDrill && t.Team != cur.Team && !eng)
            {
                if (spots) spots = SeesFront(slot, pawn, mePawn, sightSmokes);
                if (!spots) contact.Remove(slot);
            }
            if (!eng && !t.Runner && phase == "live" && t.Team != cur.Team && spots && (contact[slot] = contact.GetValueOrDefault(slot) + 1) >= (drill?.Mode == "crossfire" ? DuelReact : ReactTicks))
            {
                engaged[slot] = Server.TickCount; eng = true; Log("contact {n} at {f}", t.Name, (int)f);
                if (ScriptedDrill) { Free(slot, c, t); continue; }   // css_scripted: it fights at once, by the plugin's hand
                // Crossfire (14/10, his test: "il tire bizarrement" while walking): it has seen you, it stops and shoots
                if (drill?.Mode == "crossfire" && !CfSpray) { Free(slot, c, t); continue; }
            }
            var here = pawn.AbsOrigin is { } ho ? new Vector3(ho.X, ho.Y, ho.Z) : pos;
            // a defense's attacker only once on you (27/10, Vertigo B: freed 350 u from you hidden in your zone, the game walked
            // it off and its wave was taken off unseen; its way now clears your zone, the user: "les adversaires ... ne se
            // dirigent pas vers la zone")
            var onYou = drill?.Mode == "defend" ? OnYou : Near;
            if (phase == "live" && mePos != null && t.Team != cur.Team && !t.Runner && drill?.Mode != "crossfire" && Vector3.DistanceSquared(here, mePos.Value) < onYou * onYou)
            {   // you are right on it: a player would notice you, path or not
                Free(slot, c, t); Log("close {n} at {f}", t.Name, (int)f); continue;
            }
            // the real player's way and facing; until it reacts, the real player's aim too (not yet yours)
            var y0 = t.Path[i * 5 + 3]; var dy = ((t.Path[i * 5 + 8] - y0 + 540f) % 360f) - 180f;
            var pitch = t.Path[i * 5 + 4] + (t.Path[i * 5 + 9] - t.Path[i * 5 + 4]) * a;
            var face = new Vector3(0, y0 + dy * a, 0);
            // css_scripted: where players look there, with what its team knows of you (Look.cs), not the real player's own
            if (selftest && lookSmokes != null && ScriptedDrill && phase == "live" && !eng && t.Team != cur.Team && ft >= 0f)
            {   // a self-test: its eyes since the plugin set them, and its legs
                lookChk[0]++;
                if (dbgLook == -2) dbgLook = slot;
                if (slot == dbgLook && dbgLookN > 0 && pawn.EyeAngles is { } de0)
                    Log("dbglook {t} tick start eyes {ex:F1} {ey:F1} lookNow {lx:F1} {ly:F1}", Server.TickCount, de0.X, de0.Y,
                        lookNow.TryGetValue(slot, out var dl) ? dl.X : float.NaN, lookNow.TryGetValue(slot, out dl) ? dl.Y : float.NaN);
                if (lookNow.TryGetValue(slot, out var ln0) && pawn.EyeAngles is { } e0)
                {
                    var fd = AngDiff(ln0, new Vector3(e0.X, e0.Y, 0f)).Length();
                    if (fd > 2f) lookChk[1]++;
                    if (fd > 10f) lookChk[2]++;
                }
                var wv = new Vector2(p1.X - p0.X, p1.Y - p0.Y).Length() * cur.Rate / cur.Step;
                if (wv > 100f && pawn.AbsVelocity is { } lv && new Vector2(lv.X, lv.Y).Length() < 20f) lookChk[5]++;
            }
            if (lookSmokes != null && ScriptedDrill && phase == "live" && !eng && t.Team != cur.Team)
            {
                var look = LookFor(slot, t, pos, new Vector3(pitch, face.Y, 0), mePawn, lookSmokes);
                SetEyes(pawn, look); face = new Vector3(0, look.Y, 0); pitch = look.X;   // its body upright, its eyes up or down (the look's pitch kept below, not the demo's)
            }
            if (ft < 0f)
            {   // not its time yet (a rush's runners wait at their start): set there only when off it (29/10: no teleport in sight)
                if (Vector3.DistanceSquared(here, p0) > 16f) { pawn.Teleport(p0, face, Vector3.Zero); botAt[slot] = p0; }
                else { pawn.Teleport(null, face, Vector3.Zero); botAt[slot] = here; }
                continue;
            }
            // it walks: its speed takes it to where the path is at the next tick, and the game moves it (its legs move
            // like a player's; moved by teleports it slid, 04/10). Too far from its path (a closed door, a box it
            // jumped on in the match), or not live yet: put back on it
            var next = PathAt(t, ft + 1f / cur.Step) - here;
            // its real speed, from where it was the tick before (17/10, the self-test: bots stuck in something kept the
            // 1,215 u/s they were given and never moved, 2.5 s each: read from the game they ran, so their way's clock
            // waited for them). Not moving for 12 ticks while its way runs on: put back on it at once
            var realV = botAt.TryGetValue(slot, out var was) ? new Vector2(here.X - was.X, here.Y - was.Y).Length() * 64f : -1f;
            var moved = realV >= 0f ? Vector3.Distance(here, was) * 64f : -1f;   // up and down too
            botAt[slot] = here;
            var wayV = new Vector2(p1.X - p0.X, p1.Y - p0.Y).Length() * cur.Rate / cur.Step;
            // just put on its way's start (a wave's respawn) and not moving yet: the game holds a new spawn still for a few
            // ticks (17/10, the self-test: put back 0.3 s after each wave's respawn), its way's clock waits for it
            // 0.6 s of it at most (30/10, his review on Dust2's Long: a wave's second spawned in the doors, its clock held there
            // 46 s, "frame 9 of 837", never came: "il est double porte, donc injouable"); then the unstick rules below
            var spawnHold = !eng && phase == "live" && wayV > 60f && ft - t.SpawnF < 0.6f * cur.Rate / cur.Step && realV >= 0f && realV < 20f
                            && Vector3.Distance(here, PathAt(t, t.SpawnF)) < 8f && spawnHeldN.GetValueOrDefault(slot) < 40;
            if (spawnHold) { t.Start += 1f / cur.Step; spawnHeldN[slot] = spawnHeldN.GetValueOrDefault(slot) + 1; }
            // caught in the floor (off the ground and not a hair of motion, not even falling; or it keeps the speed it is
            // given): lifted 6 u out of it. Stopped by a wall it stands on the ground, and hops (below)
            var frozenN = !spawnHold && !eng && phase == "live" && moved >= 0f && moved < 3f && wayV > 40f
                          && ((pawn.Flags & (uint)PlayerFlags.FL_ONGROUND) == 0 || (pawn.AbsVelocity is { } fz && new Vector2(fz.X, fz.Y).Length() > 40f))
                          ? botFrozen.GetValueOrDefault(slot) + 1 : 0;
            botFrozen[slot] = frozenN;
            if (frozenN == 6)
            {   // a hop out of it (29/10: it was lifted 6 u, a teleport)
                pawn.Teleport(null, null, new Vector3(pawn.AbsVelocity?.X ?? 0f, pawn.AbsVelocity?.Y ?? 0f, 160f));
                if (selftest) St("hop", new() { ["bot"] = t.Sid, ["f"] = R1(ft), ["at"] = R3(here), ["kind"] = "unstick" });
            }
            var stillN = !spawnHold && realV >= 0f && realV < Math.Max(20f, 0.5f * wayV) && wayV > 40f && !eng ? botStill.GetValueOrDefault(slot) + 1 : 0;
            botStill[slot] = stillN;
            if (stillN == 0 && realV > 0.8f * wayV) stepTries.Remove(slot);   // going again: its next step hop the low one
            // stopped on the ground it hops a little (below); no headway in half a second while its way ran on: stuck
            var stuck = false;
            if (eng || !botProg.TryGetValue(slot, out var pg)) botProg[slot] = (Server.TickCount, here, ft);
            else if (Server.TickCount - pg.T >= 32)
            {
                var wayRan = Vector3.Distance(PathAt(t, ft), PathAt(t, Math.Max(0f, pg.F)));   // a walk too (Inferno: 73 u/s)
                stuck = wayRan > 32f && Vector3.Distance(here, pg.At) < Math.Min(32f, 0.3f * wayRan) && new Vector2(next.X, next.Y).Length() > 24f;
                botProg[slot] = (Server.TickCount, here, ft);
            }
            if (realV < 0f) realV = pawn.AbsVelocity is { } av ? new Vector2(av.X, av.Y).Length() : 0f;
            // in the air (falling to its way below, in its own jump, thrown up by a slope it ran up): no put-back up or down,
            // it lands first (17/10, the self-test: drops and jumps put back at their peak)
            var air = (pawn.Flags & (uint)PlayerFlags.FL_ONGROUND) == 0;
            botGround[slot] = !air;
            var zMax = air ? 160f : 56f;
            if (eng && (new Vector2(next.X, next.Y).Length() > 72f || Math.Abs(next.Z) > zMax)) { Free(slot, c, t); continue; }   // fighting, off its way: on its own
            if (phase != "live")
            {   // before it starts: put on its way (its place for the drill)
                pawn.Teleport(pos, face, Vector3.Zero);
                botAt[slot] = pos;
                botStill.Remove(slot);
                botProg.Remove(slot);
            }
            else WalkWay(slot, c, t, pawn, here, ft, i, face, eng, stillN, realV, mePos);   // 29/10: by its speed alone, no put-back (Walk.cs)
            if (!eng && pawn.EyeAngles is { } eye && Math.Abs(eye.X - pitch) > 0.5f)
            { eye.X = pitch; Utilities.SetStateChanged(pawn, "CCSPlayerPawn", "m_angEyeAngles"); }
            if (ScriptedDrill && !eng && pawn.EyeAngles is { } we1) wayEyes[slot] = new Vector3(we1.X, we1.Y, 0f);   // kept through its command (Combat.cs SimPost)
            if (slot == dbgLook && dbgLookN > 0 && pawn.EyeAngles is { } de1)
            { Log("dbglook {t} tick end eyes {ex:F1} {ey:F1} rot {r:F1}", Server.TickCount, de1.X, de1.Y, pawn.AbsRotation?.Y ?? float.NaN); if (--dbgLookN == 0) dbgLook = -1; }
        }
        if (phase != "live") return;
        StSample(f);   // a self-test: each bot against its way, every half second
        GuideTick();   // a guided self-test: the stuff thrown as its words say
        if (!bombDone && cur.Bomb != null && f >= cur.Bomb.F)   // the demo's plant: its planter alive here and still on its way
        {
            var pl = bots.FirstOrDefault(kv => kv.Value.Sid == cur.Bomb.By);
            if (gone.Contains(cur.Bomb.By)) { bombDone = true; Log("no plant: its planter is dead here"); }
            else if (pl.Value != null && free.Contains(pl.Key)) { bombDone = true; Log("no plant: its planter plays on its own"); }
            else PlantBomb();
        }
        SessionTick();
        if (cur == null || phase != "live" || cur.Kind is "aim" or "nade" or "momentum") return;   // their end is the session's
        while (nextNade < cur.Nades.Count && cur.Nades[nextNade].F <= f) Throw(cur.Nades[nextNade++]);
        if (mode == "spec" && devN > 0 && (now - t0) % 320 == 0)
            Log($"drift {devSum / devN:F1} u over {devN} samples");
        if (humanDead)   // you died: traded or not, the drill ends (the bots keep moving meanwhile)
        {
            if (traded) Finish("traded");
            else if (now > tradeUntil) Finish("dead");
            return;
        }
        // a CT once the bomb is down wins by the defuse, not by the last kill; the window then lasts until it is defused
        // or blows up
        var defuse = bombLive && cur.Team == 3;
        var foes = bots.Where(b => b.Value.Team != cur.Team).ToList();
        if (mode == "actor" && foes.Count > 0 && foes.All(b => gone.Contains(b.Value.Sid)) && !defuse) { Finish("won"); return; }
        // nobody coming to you never happens (30/10, the user: "Quand personne vient là où tu es, c'est ni censé être compté
        // comme quelque chose de neutre, ni un fail, c'est censé ne jamais arriver en fait"): seen one of them yet; from a
        // second before your death in the match, the ones still on their way come for you (Walk.cs Hunt: where their side
        // last saw or heard you, else where you are, by the mesh); no end before one of them came into your sight (20 s more
        // at most)
        var hs = Humans().FirstOrDefault(x => x.PawnIsAlive);
        if (!foeSeenOnce && hs != null && foes.Any(b => Utilities.GetPlayerFromSlot(b.Key)?.PlayerPawn.Value is { } bp
                && bp.LifeState == (byte)LifeState_t.LIFE_ALIVE && (bp.EntitySpottedState.SpottedByMask[hs.Slot / 32] & (1u << (hs.Slot % 32))) != 0))
            foeSeenOnce = true;
        var meT = cur.Players.FirstOrDefault(p => p.Me);
        var meDeath = meT != null && meT.Death > 0 ? meT.Death : maxFrames;
        // no duel yet, whoever was glimpsed (31/10, round 15: a glimpse early on, by the game's spotting, kept the hunt off and
        // ended the drill at its time with no fight: 5 of Train's situations, 4 of Overpass's, 4 of Nuke's "aucun kill")
        // 02/11 17:20, the user: "fais en sorte que les bots viennent jouer des duels contre moi": no kill of yours yet, they come,
        // a duel without a kill too (4 drills of round 16 fought and survived with no kill)
        if (ScriptedDrill && mode == "actor" && !sitHunt && kills == 0 && f >= meDeath - 64 / cur.Step)
        {
            sitHunt = true;
            foreach (var (sl, t) in foes)
                if (!free.Contains(sl) && !gone.Contains(t.Sid) && Utilities.GetPlayerFromSlot(sl) is { IsValid: true, PawnIsAlive: true } fc)
                {
                    Free(sl, fc, t);
                    if (fighters.TryGetValue(sl, out var fh)) fh.Since = now - 200;   // on the hunt at once
                }
            Log("situation: past your death in the match, no kill of yours yet: they come for you");
        }
        // the hunt as it goes, every 3 s: each hunter's distance to you, its speed, held or not (02/11, round 15, Mirage's R15:
        // 29 s of hunt, none of them came, nothing said where they were)
        if (sitHunt && sitExch < 0 && hs?.PlayerPawn.Value?.AbsOrigin is { } hso && now % 192 == 0)
            Log("hunt: " + string.Join(", ", foes.Where(b => !gone.Contains(b.Value.Sid)).Select(b =>
            {
                var bp = Utilities.GetPlayerFromSlot(b.Key)?.PlayerPawn.Value;
                if (bp?.AbsOrigin is not { } bo || bp.LifeState != (byte)LifeState_t.LIFE_ALIVE) return b.Value.Name + " down";
                var held = huntProg.TryGetValue(b.Key, out var hp0) && now < hp0.HoldUntil ? " held" : "";
                var v = bp.AbsVelocity is { } av ? new Vector2(av.X, av.Y).Length() : 0f;
                return $"{b.Value.Name} {Vector3.Distance(new Vector3(bo.X, bo.Y, bo.Z), new Vector3(hso.X, hso.Y, hso.Z)):F0} u {v:F0} u/s{held}";
            })));
        var endF = cur.Kind == "clutch" ? maxFrames + 64 * 10 / cur.Step : maxFrames + 64 * 2 / cur.Step;
        // no end before a kill of yours (or your death), 30 s more at most (02/11 17:20, his rules: they come and duel you)
        if (f >= endF + (bombLive ? 45 * 64 / cur.Step : 0)
            && (mode != "actor" || kills >= 1 && (sitExch < 0 || Server.TickCount - sitExch > 3 * 64) || f >= endF + 30 * 64 / cur.Step))
            Finish(mode == "spec" ? "watched" : "survived");
    }

    // a death of the demo, as it was heard and seen: its killer's shots (the sound of its gun, where it stands) and the kill
    // feed's line, then the death (04/10: "when the Ts kill my teammates I hear them shoot: I want the real situation")
    void DemoKill(CCSPlayerController c, CCSPlayerPawn pawn, Track t)
    {
        var kc = bots.Where(b => b.Value.Sid == t.Killer).Select(b => Utilities.GetPlayerFromSlot(b.Key)).FirstOrDefault(x => x is { IsValid: true, PawnIsAlive: true });
        if (kc?.PlayerPawn.Value is { } kp)
        {
            // the gun of the match's kill (the killer takes it out), else the one it holds
            var w = t.KillWeapon != "" ? t.KillWeapon : kp.WeaponServices?.ActiveWeapon.Value?.DesignerName?.Replace("weapon_", "") ?? "";
            if (t.KillWeapon != "") kc.ExecuteClientCommandFromServer($"use weapon_{t.KillWeapon}");
            if (ShotSound.TryGetValue(w, out var snd))
                for (int k = 0; k < (w is "awp" or "ssg08" or "deagle" or "revolver" ? 1 : 3); k++)
                    AddTimer(0.09f * k, () => { if (kp.IsValid) kp.EmitSound(snd); });
            try
            {
                var ev = NativeAPI.CreateEvent("player_death", true);
                NativeAPI.SetEventPlayerController(ev, "userid", c.Handle);
                NativeAPI.SetEventPlayerController(ev, "attacker", kc.Handle);
                NativeAPI.SetEventString(ev, "weapon", w == "" ? "world" : w);
                NativeAPI.FireEvent(ev, false);
            }
            catch (Exception e) { Log("kill feed: {m}", e.Message); }
        }
        pawn.CommitSuicide(false, true);   // its own death event stays out of the feed (the Pre hook)
    }

    // the sound event of each gun's shot
    static readonly Dictionary<string, string> ShotSound = new()
    {
        ["ak47"] = "Weapon_AK47.Single", ["m4a1"] = "Weapon_M4A1.Single", ["m4a1_silencer"] = "Weapon_M4A1.Silenced", ["awp"] = "Weapon_AWP.Single",
        ["deagle"] = "Weapon_DEagle.Single", ["glock"] = "Weapon_Glock.Single", ["hkp2000"] = "Weapon_HKP2000.Single", ["usp_silencer"] = "Weapon_USP.SilencedShot",
        ["p250"] = "Weapon_P250.Single", ["tec9"] = "Weapon_Tec9.Single", ["fiveseven"] = "Weapon_FiveSeven.Single", ["cz75a"] = "Weapon_CZ75A.Single",
        ["elite"] = "Weapon_Elite.Single", ["revolver"] = "Weapon_Revolver.Single", ["famas"] = "Weapon_FAMAS.Single", ["galilar"] = "Weapon_GalilAR.Single",
        ["aug"] = "Weapon_AUG.Single", ["sg556"] = "Weapon_SG556.Single", ["ssg08"] = "Weapon_SSG08.Single", ["scar20"] = "Weapon_SCAR20.Single",
        ["g3sg1"] = "Weapon_G3SG1.Single", ["mp9"] = "Weapon_MP9.Single", ["mac10"] = "Weapon_MAC10.Single", ["mp7"] = "Weapon_MP7.Single",
        ["mp5sd"] = "Weapon_MP5SD.Single", ["ump45"] = "Weapon_UMP45.Single", ["p90"] = "Weapon_P90.Single", ["bizon"] = "Weapon_bizon.Single",
        ["nova"] = "Weapon_Nova.Single", ["xm1014"] = "Weapon_XM1014.Single", ["mag7"] = "Weapon_Mag7.Single", ["sawedoff"] = "Weapon_Sawedoff.Single",
        ["m249"] = "Weapon_M249.Single", ["negev"] = "Weapon_Negev.Single",
    };

    // the planted bomb as bots_live.json says it: where, the seconds left, being defused (and its seconds)
    static Dictionary<string, object?>? BombLive()
    {
        var c4 = Utilities.FindAllEntitiesByDesignerName<CPlantedC4>("planted_c4").FirstOrDefault(x => x.IsValid && x.BombTicking && !x.HasExploded);
        if (c4?.AbsOrigin is not { } o) return null;
        return new Dictionary<string, object?> { ["pos"] = new[] { MathF.Round(o.X, 1), MathF.Round(o.Y, 1), MathF.Round(o.Z, 1) },
            ["left"] = MathF.Round(c4.C4Blow - Server.CurrentTime, 1), ["defusing"] = c4.BeingDefused,
            ["defuse_left"] = c4.BeingDefused ? MathF.Round(c4.DefuseCountDown - Server.CurrentTime, 1) : null };
    }

    // the demo's bomb on the ground where it was planted, ticking with the time it had left: the game's own planted_c4,
    // made the way retake servers plant it, and the game told (HUD, bots)
    void PlantBomb()
    {
        bombDone = true;
        var b = cur?.Bomb;
        if (b == null) return;
        try
        {
            foreach (var old in Utilities.FindAllEntitiesByDesignerName<CPlantedC4>("planted_c4")) old.Remove();
            var c4 = Utilities.CreateEntityByName<CPlantedC4>("planted_c4");
            if (c4?.AbsOrigin == null) return;
            c4.AbsOrigin.X = b.Pos[0]; c4.AbsOrigin.Y = b.Pos[1]; c4.AbsOrigin.Z = b.Pos[2];
            c4.HasExploded = false;
            c4.BombSite = b.Site;
            c4.BombTicking = true;
            c4.CannotBeDefused = false;
            c4.DispatchSpawn();
            var left = Math.Max(3f, b.Left);
            Server.NextFrame(() =>
            {
                if (!c4.IsValid) return;
                c4.C4Blow = Server.CurrentTime + left;
                Utilities.SetStateChanged(c4, "CPlantedC4", "m_flC4Blow");
            });
            if (rules != null) { rules.BombPlanted = true; rules.BombDefused = false; }
            bombLive = true;
            var by = bots.Where(kv => kv.Value.Sid == b.By).Select(kv => Utilities.GetPlayerFromSlot(kv.Key)).FirstOrDefault(x => x is { IsValid: true })
                     ?? Utilities.GetPlayers().FirstOrDefault(x => x is { IsValid: true } && (int)x.Team == 2);
            if (by != null)
            {
                var ev = NativeAPI.CreateEvent("bomb_planted", true);
                NativeAPI.SetEventPlayerController(ev, "userid", by.Handle);
                NativeAPI.SetEventInt(ev, "site", b.Site);
                NativeAPI.FireEvent(ev, false);
            }
            Log("bomb planted at {x:F0} {y:F0} {z:F0} site {s}, {l:F1} s left", b.Pos[0], b.Pos[1], b.Pos[2], b.Site, left);
        }
        catch (Exception e) { Log("bomb: {m}", e.Message); }
    }

    // a grenade of the demo, thrown again from the same point at the same speed, if its thrower is alive here (yours: you
    // throw it yourself)
    void Throw(Nade n)
    {
        if (cur == null || gone.Contains(n.By) || (mode == "actor" && cur.Players.Any(t => t.Me && t.Sid == n.By))) return;
        var slot = bots.Where(b => b.Value.Sid == n.By).Select(b => (int?)b.Key).FirstOrDefault();
        var c = slot == null ? null : Utilities.GetPlayerFromSlot(slot.Value);
        var pawn = c?.PlayerPawn.Value;
        if (c == null || pawn == null || !c.PawnIsAlive) return;
        ThrowAs(c, pawn, n);
    }

    // the game's own Create for a smoke, an HE or a molotov. Its byte patterns above are of the Windows build: on Linux
    // the same code is in libserver.so, built for another ABI, so nothing there can match them, and libserver.so keeps
    // no symbol to reach it by name either. A MemoryFunction of a pattern that was not found is not null and only fails
    // when it is called, so every grenade of every bot raised "Invalid function pointer" and was dropped, once per
    // grenade. Said once per type now, with what it means, instead of at every throw.
    // Making the projectile ourselves is not a way out, and that is measured, not assumed (13/10): built by hand a smoke
    // comes up with no fuse and no think (det 0.00, think -1) where a flashbang comes up with both from its own Spawn,
    // which is why flashes are the only ones that go off here. Writing the fuse and the think by hand changes nothing:
    // 2 s later the fuse had passed, the think tick was still the one written, the smoke had not gone off. The engine
    // schedules thinks itself, so a smoke, an HE or a molotov simply cannot be set off from here without that function.
    // -> true when the game threw it; false when this server cannot, and then it is not thrown at all rather than
    // dropped in the world as an object that never goes off.
    bool GameThrow(CCSPlayerController c, CCSPlayerPawn pawn, Nade n)
    {
        if (n.Type is not ("smoke" or "he" or "molotov")) return false;
        if (n.Type == "smoke" ? smokeCreate == null : n.Type == "he" ? heCreate == null : molotovCreate == null) return false;
        var o = new CVector(n.P[0], n.P[1], n.P[2]);
        var v = new CVector(n.V[0], n.V[1], n.V[2]);
        var spin = new CVector(600, 0, 0);
        try
        {
            if (n.Type == "smoke") smokeCreate!.Invoke(o.Handle, new QAngle(0, 0, 0).Handle, v.Handle, spin.Handle, pawn.Handle, 45, c.TeamNum);
            else if (n.Type == "he") heCreate!.Invoke(o.Handle, new QAngle(0, 0, 0).Handle, v.Handle, spin.Handle, pawn.Handle, 44);
            else molotovCreate!.Invoke(o.Handle, new QAngle(0, 0, 0).Handle, v.Handle, spin.Handle, pawn.Handle, n.Inc ? 48 : 46);
            return true;
        }
        catch (Exception ex)
        {
            if (n.Type == "smoke") smokeCreate = null;
            else if (n.Type == "he") heCreate = null;
            else molotovCreate = null;
            Log("nade {t}: this server cannot throw one ({m}); the bots' {t} are off for this server", n.Type, ex.Message);
            return false;
        }
    }

    void ThrowAs(CCSPlayerController c, CCSPlayerPawn pawn, Nade n)
    {
        var cls = n.Type switch { "smoke" => "smokegrenade_projectile", "flash" => "flashbang_projectile", "he" => "hegrenade_projectile",
            "molotov" => "molotov_projectile", "decoy" => "decoy_projectile", _ => "" };
        if (cls == "") return;
        try
        {
            if (n.Type is "smoke" or "he" or "molotov")
            {
                if (!GameThrow(c, pawn, n))
                    return;
                Log("nade {t} by {n} at {f}", n.Type, c.PlayerName, n.F);
                return;
            }
            var e = Utilities.CreateEntityByName<CBaseCSGrenadeProjectile>(cls);
            if (e == null) return;
            if (n.Inc) new CMolotovProjectile(e.Handle).IsIncGrenade = true;
            var pos = new Vector3(n.P[0], n.P[1], n.P[2]);
            var vel = new Vector3(n.V[0], n.V[1], n.V[2]);
            e.InitialPosition.X = pos.X; e.InitialPosition.Y = pos.Y; e.InitialPosition.Z = pos.Z;
            e.InitialVelocity.X = vel.X; e.InitialVelocity.Y = vel.Y; e.InitialVelocity.Z = vel.Z;
            e.Elasticity = 0.33f;
            e.IsLive = false;
            e.DmgRadius = 350f;
            e.Damage = 99f;
            e.TeamNum = c.TeamNum;
            e.Thrower.Raw = c.PlayerPawn.Raw;
            e.OriginalThrower.Raw = c.PlayerPawn.Raw;
            e.OwnerEntity.Raw = c.PlayerPawn.Raw;
            e.Teleport(pos, Vector3.Zero, vel);
            e.DispatchSpawn();
            e.AcceptInput("InitializeSpawnFromWorld");
            e.AcceptInput("FireUser1", pawn, pawn);
            Log("nade {t} by {n} at {f}", n.Type, c.PlayerName, n.F);
        }
        catch (Exception ex) { Log("nade {t}: {m}", n.Type, ex.Message); }
    }

    HookResult OnDeath(EventPlayerDeath e, GameEventInfo i)
    {
        if (cur == null || phase != "live") return HookResult.Continue;
        var v = e.Userid;
        if (v != null && v.IsValid && bots.TryGetValue(v.Slot, out var t)) gone.Add(t.Sid);
        // how far, and a headshot or not, for a duel's death (02/11: the MAG-7 posts' deaths, no distance to read them by)
        var dd = v?.PlayerPawn.Value?.AbsOrigin is { } vo && e.Attacker?.PlayerPawn.Value?.AbsOrigin is { } ao && e.Attacker != v
            ? $" {Vector3.Distance(new Vector3(vo.X, vo.Y, vo.Z), new Vector3(ao.X, ao.Y, ao.Z)):F0} u{(e.Headshot ? " HS" : "")}" : "";
        Log("death {f}/{s}: {v} by {a} ({w}){d}", (Server.TickCount - t0) / cur.Step, cur.Id, v?.PlayerName, e.Attacker?.PlayerName, e.Weapon, dd);
        if (e.Attacker is { IsValid: true, IsBot: false } && v != null && v.IsBot) kills++;
        if (drill?.Kind == "aim" && !CfSpray && e.Attacker is { IsValid: true, IsBot: false } killer && v is { IsBot: true })   // a spray: one magazine for both
            AddTimer(0.05f, () => { if (killer.IsValid) FullMag(killer); });
        if (humanDead && v != null && v.IsValid && v.Slot == tradeKiller && Server.TickCount <= tradeUntil) traded = true;   // your killer died right after: traded
        if (cur.Kind is "death" or "clutch" && v is { IsValid: true, IsBot: true } && bots.TryGetValue(v.Slot, out var tv) && tv.Team == cur.Team
            && v.PlayerPawn.Value?.AbsOrigin is { } dp)
            DrawX(new Vector3(dp.X, dp.Y, dp.Z));   // an ally down: where it fell, where the enemies are (06/10)
        // Momentum: a fall, or a kill typed to start again, is that rep missed and you back on its start (MoTick). 16/10:
        // it ended the whole drill ("dead"), every jump and stop drill of his Mirage and Fachwerk sessions after one try
        if (MoOn && v is { IsValid: true, IsBot: false }) return HookResult.Continue;
        if (SessionDeath(e, v)) return HookResult.Continue;   // a defense: you come back
        if (mode == "actor" && v is { IsValid: true, IsBot: false })
        {
            // a situation: 3 s to see if a teammate trades you (your killer dead), unless nobody is left to
            var mates = bots.Any(b => b.Value.Team == cur.Team && !gone.Contains(b.Value.Sid));
            if (cur.Kind is "death" or "clutch" && mates && e.Attacker is { IsValid: true, IsBot: true } k)
            {
                humanDead = true; tradeKiller = k.Slot; tradeUntil = Server.TickCount + 3 * 64;
                return HookResult.Continue;
            }
            AddTimer(0.1f, () => Finish("dead"));
        }
        return HookResult.Continue;
    }

    HookResult OnHurt(EventPlayerHurt e, GameEventInfo i)
    {
        if (phase == "live" && e.Attacker is { IsValid: true, IsBot: true } && e.Userid is { IsValid: true, IsBot: false })
            sitExch = Server.TickCount;   // one of them hurt you: a duel (a situation's end waits for one)
        if (phase == "live" && e.Attacker is { IsValid: true, IsBot: false } && e.Userid is { IsBot: true } v)
        {
            dmg += e.DmgHealth;
            sitExch = Server.TickCount;
            // hit: it reacts like a player (a target stays; a situation's or a defense's holder too, 30/10, the user: "ils ne
            // réagissent pas quand je leur tire dessus")
            if (bots.TryGetValue(v.Slot, out var hit) && (!hit.Hold || ScriptedDrill) && !hit.Strafe) Free(v.Slot, v, hit);
            // a fighter of the plugin's hand turns to the one who hit it, and holds there if it cannot see him (a smoke)
            if (fighters.TryGetValue(v.Slot, out var fh) && e.Attacker.PlayerPawn.Value?.AbsOrigin is { } ao)
            {
                fh.HurtBy = e.Attacker.Slot; fh.HurtAt = Server.TickCount;
                fh.Last = new Vector3(ao.X, ao.Y, ao.Z + 62f); fh.HasLast = true; fh.LastSeen = Server.TickCount;
            }
        }
        return HookResult.Continue;
    }

    // bots never hurt each other: only the demo (a recorded death) or you kill a bot
    HookResult OnTakeDamage(CEntityInstance victim, CTakeDamageInfo info)
    {
        if (cur == null) return HookResult.Continue;
        try
        {
            // stuff: your own grenades never hurt you; from their side, what they would take is counted
            if (cur.Kind == "nade" && victim.DesignerName == "player" && new CCSPlayerPawn(victim.Handle).OriginalController.Value is { IsBot: false })
            {
                if (nadeStage != "theirs") return HookResult.Handled;
                // from their side you take it, never to death (04/10: "I don't see the damage it does to me")
                var vp = new CCSPlayerPawn(victim.Handle);
                theirsDmg += (int)info.Damage;
                info.Damage = Math.Min(info.Damage, Math.Max(0, vp.Health - 1));
                return HookResult.Continue;
            }
            if (victim.DesignerName == "player" && Server.TickCount < protectUntil && new CCSPlayerPawn(victim.Handle).OriginalController.Value is { IsBot: false })
                return HookResult.Handled;   // a defense: you just came back on your spot
            if (victim.DesignerName == "player" && (phase == "setup" || phase == "countdown") && new CCSPlayerPawn(victim.Handle).OriginalController.Value is { IsBot: false })
                return HookResult.Handled;   // before GO nothing hurts you (06/10: killed during an aim drill's countdown, a minute on the floor)
            var att = info.Attacker.Value;
            var hurt = info.Inflictor.Value?.DesignerName == "trigger_hurt" || att?.DesignerName == "trigger_hurt";   // logged "by null (trigger_hurt)"
            if (victim.DesignerName == "player" && hurt && new CCSPlayerPawn(victim.Handle).OriginalController.Value is { IsBot: false })
                return HookResult.Handled;   // a map hurt zone (Boulder): no death by the map in training
            if (victim.DesignerName != "player" || att == null || att.DesignerName != "player") return HookResult.Continue;
            var vc = new CCSPlayerPawn(victim.Handle).OriginalController.Value;
            var ac = new CCSPlayerPawn(att.Handle).OriginalController.Value;
            // a bot on its recorded path dies only as recorded (a demo death is the bot on itself); one playing on its own
            // (it saw you) can be shot by anyone: your teammates can trade you
            // an exec's entry: its teammate's grenades hurt them (20/10, his video: "lui il est censé brûler de la molotov,
            // j'aimerais bien qu'il meure pour de vrai de la molotov": never one burned, bots never hurt bots)
            if (EntryOn && ac is { IsBot: true } && bots.TryGetValue(ac.Slot, out var mt) && mt.Sid == "mate") return HookResult.Continue;
            if (vc is { IsBot: true } && ac is { IsBot: true } && vc.Slot != ac.Slot && !free.Contains(vc.Slot)) return HookResult.Handled;
            if (drill?.Mode == "prefire" && vc is { IsBot: false } && ac is { IsBot: true }) return HookResult.Handled;   // prefire: they don't shoot
            // 09/10, his defense video: "je me prends des balles à travers les portes alors que l'ennemi ne m'a jamais vu": a
            // bot's bullets hurt you only if it had you in sight the last 1.5 s (the game's own spotting, a closed door hides
            // you); its grenades always do
            var inf = info.Inflictor.Value?.DesignerName ?? "";
            var nade = inf.Contains("projectile") || inf.Contains("grenade") || inf == "inferno";
            if (vc is { IsBot: false } && ac is { IsBot: true } && !nade && Server.TickCount - sawYou.GetValueOrDefault(ac.Slot, -100000) > SawTicks)
                return HookResult.Handled;
            // the aim map: still and strafing targets never hurt you; a duel's only once it has seen you a player's reaction
            // time (06/10: "ils me préfirent, ils savent où je suis, c'est un temps de réaction terrible")
            if (drill?.Mode == "range" && vc is { IsBot: false } && ac is { IsBot: true } && (drill.Variant != "duel" || contact.GetValueOrDefault(ac.Slot) < DuelReact))
                return HookResult.Handled;
            // Crossfire (13/10): the same, its enemies fight you once they have seen you a player's reaction time; a spray's never
            if (drill?.Mode == "crossfire" && vc is { IsBot: false } && ac is { IsBot: true } && (CfSpray || contact.GetValueOrDefault(ac.Slot) < DuelReact))
                return HookResult.Handled;
        }
        catch (Exception) { }
        return HookResult.Continue;
    }

    void Finish(string outcome)
    {
        if (cur == null || phase != "live") return;
        phase = "done";
        var alive = (Server.TickCount - t0) / 64.0;
        Log("footsteps: bots {b} (+{o} played by the plugin), you {y} in {s:F0} s", stepsBots, stepsOurs, stepsYou, alive);
        stepsBots = stepsYou = stepsOurs = 0;
        if (sess != null && drill != null) { SessionFinish(outcome, alive); return; }
        ClearLine();
        if (mode == "actor") outcome = SitOutcome(outcome);
        var line = JsonSerializer.Serialize(new Dictionary<string, object> {
            ["id"] = cur.Id, ["t"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(), ["outcome"] = outcome, ["mode"] = mode,
            ["kills"] = kills, ["dmg"] = dmg, ["alive_s"] = Math.Round(alive, 1), ["difficulty"] = difficulty,
            ["drift"] = devN > 0 ? Math.Round(devSum / devN, 1) : -1 });
        Append("results.jsonl", line);
        var good = outcome is "won" or "survived" or "traded" or "kill" || BombWon(outcome);
        All($"{(good ? "\x04" : "\x02")}{Shown(outcome)}\x01 · {SitDetail(alive)} — {T("again in 3 s (!n next · !p previous · !spec · !stop)")}");
        var g = generation;
        AddTimer(3f, () => { if (g == generation && phase == "done" && cur != null) Setup(); });
    }

    // a situation's try: your kills, your damage, how long you lived
    string SitDetail(double alive) => $"{Tn(kills, "{n} kill", "{n} kills")} · {F("{n} dmg", "n", dmg)} · {alive.ToString("F1", System.Globalization.CultureInfo.InvariantCulture)} s";

    // a situation's outcome: a kill or a trade is needed. won / survived with no kill of yours: passive; dead after a
    // kill: kill (one for one); traded and dead stay
    string SitOutcome(string o) => o switch
    {
        "won" or "survived" => kills >= 1 ? o : "passive",
        "dead" => kills >= 1 ? "kill" : "dead",
        // a death's situation is won by its goal said on screen, "un kill, ou se faire trader": the bomb's end after a kill
        // of yours is no fail (31/10, round 13, Anubis: 3 kills, "bombe explosée", failed); a clutch's is its round's
        "exploded" or "defused" when cur?.Kind == "death" && !BombWon(o) && kills >= 1 => "kill",
        _ => o,   // the bomb decides: defused or exploded
    };

    // the bomb's end is yours when you defuse it as a CT, or it blows up as a T
    bool BombWon(string o) => (o == "defused" && cur?.Team == 3) || (o == "exploded" && cur?.Team == 2);

    // the app's control file (08/10, a player's server it could no longer log into: its password lost by the app, then
    // 127.0.0.1 refused, and the server run with rights the app can't kill): coach/control.json, written by replay.py.
    // "rcon": the app's password, set here; "quit": a request made after this plugin loaded, the server stops itself.
    // A local file of the server's own folder: no password needed, and nothing more than the app can already do.
    long loadedAt, ctlSeen;
    void Control()   // the io thread's
    {
        try
        {
            var f = System.IO.Path.Combine(Dir, "control.json");
            if (!File.Exists(f)) return;
            var seen = File.GetLastWriteTimeUtc(f).Ticks;
            if (seen == ctlSeen) return;
            ctlSeen = seen;
            using var doc = JsonDocument.Parse(File.ReadAllText(f));
            var root = doc.RootElement;
            if (root.TryGetProperty("rcon", out var pw) && pw.ValueKind == JsonValueKind.String
                && System.Text.RegularExpressions.Regex.IsMatch(pw.GetString() ?? "", "^[0-9a-f]{8,64}$"))
            {
                var p = pw.GetString();
                OnGame(() => Server.ExecuteCommand($"rcon_password {p}"));
            }
            if (root.TryGetProperty("quit", out var q) && q.ValueKind == JsonValueKind.Number && q.GetInt64() > loadedAt)
            {
                Log("control: the app asked the server to stop");
                OnGame(() => Server.ExecuteCommand("quit"));
            }
        }
        catch (Exception e) { Log("control: {m}", e.Message); }
    }

    // 08/10, his 22:55 warm-up: the game froze 0.2 to 1.3 s at a time and dropped him seven times ("Too many queued
    // messages", NETWORK_DISCONNECT_OVERFLOW): this plugin's file reads and writes ran on the game's thread (the heartbeat
    // each second, the logs, the results) and waited on the hard disk E: (OBS recorded there; a 20-byte write took 811 ms).
    // They now run on one thread of their own; what the game has to do with them comes back to its thread (OnTick).
    readonly System.Collections.Concurrent.BlockingCollection<Action> io = new(512);
    readonly System.Collections.Concurrent.ConcurrentQueue<Action> toGame = new();
    int beatBusy;

    void StartIo()
    {
        new Thread(() => { foreach (var a in io.GetConsumingEnumerable()) { try { a(); } catch (Exception) { } } })
            { IsBackground = true, Name = "coach-io" }.Start();
    }

    public override void Unload(bool hotReload) { io.CompleteAdding(); }

    bool Io(Action a) { try { return !io.IsAddingCompleted && io.TryAdd(a); } catch (InvalidOperationException) { return false; } }
    void OnGame(Action a) => toGame.Enqueue(a);
    void Log(string msg, params object?[] args) { StLog(msg, args); if (!Io(() => Logger.LogInformation(msg, args))) Logger.LogInformation(msg, args); }
    void Append(string file, string line) => Io(() => File.AppendAllText(System.IO.Path.Combine(Dir, file), line + "\n"));

    // a player back from a drop off his team (28/10 00:22, Train's defense: kicked by an overflow as a drill began, back in
    // 5 s as a spectator; its attackers walked a site nobody held, 0 kills, the next drill never live, the session lost)
    int teamFixAt = -100000, noPawnSince = -1;
    void TeamFix()
    {
        if (sess == null || drill == null || cur == null || mode == "spec" || Server.TickCount - teamFixAt < 640) { noPawnSince = -1; return; }   // 01:02: a Momentum's too
        // or back on its team but with no living body where nobody dies (01:16, Mirage's exec A: back from the kick in 2 s,
        // its walk 30 s on 0, 0, -64; a quick reconnect fires no "connect full", the drill never run again)
        // a defense too, alive for the game but at the map's origin (03/11, round 21, Dust2's B with the AWP: after its
        // retry's round restart the player read 0, 0, 0 the whole drill, 207 s, its waves walked a site nobody held; the
        // dead-player respawn never fired, the pawn "alive")
        bool AtOrigin(CCSPlayerController h) => h.PawnIsAlive && h.PlayerPawn.Value?.AbsOrigin is { } o && MathF.Abs(o.X) < 1f && MathF.Abs(o.Y) < 1f;
        var noBody = phase == "live" && (cur.Kind is "nade" or "momentum" && Humans().Any(h => !h.PawnIsAlive)
                                         || drill.Mode == "defend" && Humans().Any(AtOrigin));
        noPawnSince = noBody ? (noPawnSince < 0 ? Server.TickCount : noPawnSince) : -1;
        var offTeam = Humans().Any(h => h.Team is CsTeam.None or CsTeam.Spectator);
        if (!offTeam && !(noBody && Server.TickCount - noPawnSince > 3 * 64)) return;
        noPawnSince = -1;
        teamFixAt = Server.TickCount;
        Log("a player off his team in a drill: on its team, the drill again");
        Teams();
        var g = sessGen;
        AddTimer(1.5f, () => { if (g == sessGen && sess != null && drill != null) RunDrill(drill); });
    }

    // a player left in noclip outside the sandbox walks again (28/10: an Alt-Tab, his noclip key, in a drill)
    void NoclipFix()
    {
        if (sandbox) return;
        foreach (var h in Humans())
            if (h.PawnIsAlive && h.PlayerPawn.Value is { } pw && pw.MoveType == MoveType_t.MOVETYPE_NOCLIP)
            { Freeze(pw, false); Log("noclip off: {n} not in the sandbox", h.PlayerName); }
    }

    void Beat()
    {
        try { TeamFix(); } catch (Exception) { }
        try { NoclipFix(); } catch (Exception) { }
        try
        {
            var o = new Dictionary<string, object?> { ["t"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(), ["humans"] = Humans().Count(),
                ["scenario"] = cur?.Id, ["state"] = phase, ["mode"] = mode, ["map"] = Server.MapName };
            foreach (var (k, v) in SessionBeat()) o[k] = v;
            var json = JsonSerializer.Serialize(o);
            if (Interlocked.Exchange(ref beatBusy, 1) == 1) return;   // the last one still on its way to the disk: this one skipped
            if (!Io(() =>
                {
                    try
                    {   // written beside, then put in place: the app never reads half of it
                        var f = System.IO.Path.Combine(Dir, "live.json");
                        File.WriteAllText(f + ".tmp", json);
                        File.Move(f + ".tmp", f, true);
                    }
                    catch (Exception) { }
                    finally { Control(); beatBusy = 0; }
                })) beatBusy = 0;
        }
        catch (Exception) { }
    }
}
