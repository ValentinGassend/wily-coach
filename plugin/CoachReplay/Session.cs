// The training session: one Play in the app, then everything follows on its own, block after block (aim on the map,
// stuff, situations), in the time chosen. The screen says what to do; each drill scores points, a streak multiplies
// them, a miss is tried once more right away (repetition), and each drill is written to coach/results.jsonl for the app
// (Leitner boxes: what you missed comes back next session).
//
// Commands during a session: !n skips the drill, !pause / !resume, !stop ends the session.
using System.Globalization;
using System.Numerics;
using System.Text.Json;
using System.Text.Json.Serialization;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Commands;
using Microsoft.Extensions.Logging;
using CVector = CounterStrikeSharp.API.Modules.Utils.Vector;
using Trace = CounterStrikeSharp.API.Modules.Utils.Trace;
using TraceOptions = CounterStrikeSharp.API.Modules.Utils.TraceOptions;
using Masks = CounterStrikeSharp.API.Modules.Utils.Masks;

namespace CoachReplay;

public class Spot
{
    [JsonPropertyName("pos")] public float[] Pos { get; set; } = new float[3];
    [JsonPropertyName("ang")] public float[] Ang { get; set; } = new float[2];   // pitch, yaw
    [JsonPropertyName("zone")] public string? Zone { get; set; }
    [JsonPropertyName("at")] public float At { get; set; }   // prefire: when it peeks (s after the start)
    [JsonPropertyName("poly")] public List<float[]> Poly { get; set; } = new();   // defend: the place's ground outline (06/10)
    [JsonPropertyName("duck")] public bool Duck { get; set; }   // prefire: an angle held crouched
    [JsonPropertyName("seq")] public int Seq { get; set; } = -1;   // prefire: its rank in the order the way shows them (07/10)
    [JsonPropertyName("see")] public float[]? See { get; set; }   // a smoke's victim on his way in: what it keeps him from seeing (20/10)
    [JsonPropertyName("li")] public int Li { get; set; }   // prefire: the gold line's point from where it is seen first
    [JsonPropertyName("react")] public bool React { get; set; }   // prefire: a CT that steps off its angle when your shot misses it, then peeks again (23/10)
}

public class Drill
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("kind")] public string Kind { get; set; } = "";
    [JsonPropertyName("map")] public string Map { get; set; } = "";
    [JsonPropertyName("title")] public string Title { get; set; } = "";
    [JsonPropertyName("tip")] public string Tip { get; set; } = "";
    [JsonPropertyName("team")] public int Team { get; set; }
    [JsonPropertyName("me")] public Spot? Me { get; set; }
    [JsonPropertyName("bots")] public List<Spot> Bots { get; set; } = new();
    [JsonPropertyName("weapons")] public List<string> Weapons { get; set; } = new();
    [JsonPropertyName("bot_weapons")] public List<string> BotWeapons { get; set; } = new();
    [JsonPropertyName("type")] public string Type { get; set; } = "";
    [JsonPropertyName("item")] public string Item { get; set; } = "";
    [JsonPropertyName("how")] public string How { get; set; } = "";
    [JsonPropertyName("click")] public string Click { get; set; } = "";   // "" when the demos don't tell
    [JsonPropertyName("target")] public float[]? Target { get; set; }   // stuff: where it lands (x, y, and z when known)
    [JsonPropertyName("victims")] public List<Spot> Victims { get; set; } = new();   // stuff: the enemies' spots it is for
    [JsonPropertyName("level")] public int Level { get; set; }
    [JsonPropertyName("scenario")] public string? Scenario { get; set; }
    [JsonPropertyName("mode")] public string Mode { get; set; } = "";   // aim: prefire, defend, or "" (your duel spots)
    [JsonPropertyName("seconds")] public int Seconds { get; set; } = 75;
    [JsonPropertyName("alive")] public int Alive { get; set; } = 3;
    [JsonPropertyName("goal")] public int Goal { get; set; } = 8;   // defend: the frags that make it a success
    [JsonPropertyName("posts")] public List<Spot> Posts { get; set; } = new();   // defend: the spots to hold in turn, then free
    [JsonPropertyName("free")] public bool Free { get; set; } = true;   // defend: the free phase on the site after them (none for a shotgun's close corners, 24/10)
    [JsonPropertyName("armor")] public int Armor { get; set; } = 100;   // both sides (a pistol defense: no helmet)
    [JsonPropertyName("helmet")] public bool Helmet { get; set; } = true;
    [JsonPropertyName("tracks")] public List<EntryTrack> Tracks { get; set; } = new();   // defend: real hits on the site
    [JsonPropertyName("route")] public List<string> Route { get; set; } = new();   // prefire: the places of the way
    [JsonPropertyName("line")] public List<float[]> Line { get; set; } = new();   // prefire: the way, drawn on the ground
    [JsonPropertyName("variant")] public string Variant { get; set; } = "";   // the aim map: flick, strafe, duel
    [JsonPropertyName("count")] public int Count { get; set; } = 3;   // the aim map: targets at once
    [JsonPropertyName("clock")] public float Clock { get; set; }   // the round's clock at GO (s left; 0: none)
    [JsonPropertyName("mate")] public Spot? Mate { get; set; }   // a boost: the teammate you stand on (06/10)
    [JsonPropertyName("step")] public int Step { get; set; } = 2;   // its tracks' ticks per frame (a rush, from the 0.5 s samples: 32)
    [JsonPropertyName("rush_at")] public float RushAt { get; set; }   // a timing smoke: the round's time (s) the real rush gets to its spot (07/10)
    [JsonPropertyName("marks")] public List<float[]> Marks { get; set; } = new();   // momentum: a way's checkpoints (x, y, z, its share of the way)
    [JsonPropertyName("par")] public float Par { get; set; }   // momentum: the base's time on that way (s); a silent walk's time allowed
    [JsonPropertyName("best")] public float Best { get; set; }   // momentum: the base's fastest runs of it (their 10th percentile)
    [JsonPropertyName("pro")] public float Pro { get; set; }   // momentum: the pros' time (0: no pro run of it)
    [JsonPropertyName("from")] public float[]? From { get; set; }   // momentum: a jump's takeoff
    [JsonPropertyName("members")] public List<Drill> Members { get; set; } = new();   // an exec: its lineups (Exec.cs)
    [JsonPropertyName("drop")] public float[]? Drop { get; set; }   // an exec: where a teammate's smoke lies
    [JsonPropertyName("aim_from")] public string AimFrom { get; set; } = "";   // stuff: "crouch", aimed crouched then thrown standing
    [JsonPropertyName("his_nade")] public Nade? HisNade { get; set; }   // stuff: his setup's grenade itself, where it left his hand and how fast
    [JsonPropertyName("steps")] public bool Steps { get; set; }   // stuff: step by step, from near its spot (Steps.cs)
    [JsonPropertyName("start")] public float[]? Start { get; set; }   // stuff step by step: where you start, near its spot
    [JsonPropertyName("at")] public float At { get; set; }   // an exec's grenade: its moment in his own exec (s after the first)
    [JsonPropertyName("jump")] public float[]? Jump { get; set; }   // his jumpthrow: what his jump adds to its speed up, its height over his standing eye
    [JsonPropertyName("place")] public string Place { get; set; } = "";   // where it is thrown from, as the base names it
    [JsonPropertyName("arrive")] public float Arrive { get; set; }   // a defense's whole drill: s after GO the Ts get onto the site
    [JsonPropertyName("runners")] public List<EntryTrack> Runners { get; set; } = new();   // a defense played: the Ts' ways in (not a rush's Tracks)
    [JsonPropertyName("aim_tol")] public float AimTol { get; set; }   // stuff: the yellow circle's radius (degrees) its throw allows; 0: 0.9 (23/10, measured: tighter where it bounces)
    [JsonPropertyName("approach")] public List<float[]> Approach { get; set; } = new();   // an entry: the base's Ts' way up to your start, walked under the sky view (23/10)
    [JsonIgnore] public bool Rush => Kind == "nade" && Tracks.Count > 0;
}

public class EntryTrack
{
    [JsonPropertyName("zone")] public string Zone { get; set; } = "";
    [JsonPropertyName("path")] public float[] Path { get; set; } = Array.Empty<float>();
    [JsonPropertyName("nades")] public List<Nade> Nades { get; set; } = new();   // the grenades its player threw on the way (f: its frame)
    [JsonPropertyName("post")] public int Post { get; set; } = -1;   // the post it walks into the sight of (-1: any, the free part)
    [JsonPropertyName("arrive")] public float Arrive { get; set; } = -1f;   // a rush: s after GO it gets to the grenade's spot
    [JsonPropertyName("kind")] public string Kind { get; set; } = "";   // Crossfire: the base's peek it is ("swing": a wide one, at a run)
}

public class Block
{
    [JsonPropertyName("map")] public string Map { get; set; } = "";
    [JsonPropertyName("kind")] public string Kind { get; set; } = "";
    [JsonPropertyName("seconds")] public int Seconds { get; set; }
    [JsonPropertyName("drills")] public List<Drill> Drills { get; set; } = new();
}

public class Session
{
    [JsonPropertyName("id")] public string Id { get; set; } = "";
    [JsonPropertyName("minutes")] public int Minutes { get; set; }
    [JsonPropertyName("maps")] public List<string> Maps { get; set; } = new();
    [JsonPropertyName("difficulty")] public int Difficulty { get; set; } = 2;
    [JsonPropertyName("seed")] public int? Seed { get; set; }   // the tests' fixed set (29/10): the same draws each run
    [JsonPropertyName("blocks")] public List<Block> Blocks { get; set; } = new();
}

public partial class CoachReplay
{
    Session? sess;
    int blockIdx = -1, tries, points, streak, okN, doneN, drillNo, sessGen, waitFile;
    DateTime blockEnd;
    readonly LinkedList<Drill> queue = new();
    Drill? drill;
    // aim: the targets come one by one
    readonly List<int> aimOrder = new();
    readonly List<double> reacts = new();
    int aimNext, aimSpawn, aimHs, frags, deaths, plants, lastHud;
    readonly Dictionary<int, float> peekAt = new();   // prefire: the bots still hidden, and when they peek
    int lineAt, lastPeek;   // prefire: how far along the gold line you got (its point), the last one that peeked (tick)
    // stuff: three throws, the camera on your grenade, then from their side
    int attempts;
    bool nadeWait;
    int rushIn = -1;   // a timing smoke: the tick the first runner got to its spot (-1: not yet)
    readonly HashSet<int> rushOut = new();   // the runners seen away from its spot: only they can get there (17/10)
    float rushDelay;   // the runners' wait before they start (guided: 2 s, the spot: 1 s, alone: the real timing)
    string nadeStage = "";   // "throw": your throws (the camera follows them), "theirs": watching it from their spot
    // your throw's pop (where their side's flash victim turns to), the bounces before it (19/10, his video: "les flashs
    // sont mieux quand on n'entend pas les flashs rebondir sur le sol")
    Vector3? nadePop;
    int nadeBounces;
    bool pracOn;   // CS2's grenade practice views are on (stuff drills only)
    CDynamicProp? cam;
    CBaseCSGrenadeProjectile? camNade;
    Vector3 camDir = new(1, 0, 0);
    int camEnd, theirsDmg;
    float theirsFlash;
    (bool ok, string outcome, int pts, string detail)? theirsRes;
    DateTime attemptEnd;
    // the session's clock: the real one; a self-test's runs on its game time (sped up, its blocks and its throws' waits
    // too: 17/10, a Vertigo stuff session went past its time-out, each throw waited 25 real seconds with nobody to throw)
    DateTime Clock => selftest ? stClock0.AddSeconds((Server.TickCount - stTick0) / 64.0) : DateTime.UtcNow;
    readonly List<float[]> nadePops = new();   // stuff: where your throws of this drill popped (the app learns the lineups that don't land)
    static Random Rng = new();   // a self-test sets its seed: the same picks each run (SelfTest.cs)
    string introHtml = "";
    // the blocks: defending a site (CT), the push routes (T), aim on hostage maps, the stuff, the situations
    static readonly Dictionary<string, string> KindName = new() { ["defend"] = N("DEFENSE"), ["push"] = N("PUSH"), ["aim"] = N("AIM"), ["nade"] = N("STUFF"),
        ["situation"] = N("SITUATION"), ["wallbang"] = N("WALLBANG"), ["crossfire"] = N("CROSSFIRE"), ["momentum"] = N("MOMENTUM") };
    // a drill's end as the screen and the chat say it (the results keep the English word: the app reads them)
    static readonly Dictionary<string, string> OutcomeName = new() { ["cleared"] = N("CLEARED"), ["done"] = N("DONE"), ["timeout"] = N("TIME'S UP"),
        ["dead"] = N("DEAD"), ["won"] = N("WON"), ["survived"] = N("SURVIVED"), ["traded"] = N("TRADED"), ["kill"] = N("KILL, THEN DEAD"),
        ["passive"] = N("NO KILL"), ["defused"] = N("DEFUSED"), ["exploded"] = N("BOMB EXPLODED"), ["late"] = N("LATE"), ["in time"] = N("IN TIME"),
        ["perfect"] = N("PERFECT"), ["good"] = N("GOOD"), ["miss"] = N("MISS"), ["no throw"] = N("NO THROW"), ["skipped"] = N("SKIPPED"),
        ["held"] = N("HELD") };
    string Shown(string outcome) => OutcomeName.TryGetValue(outcome, out var s) ? T(s) : outcome.ToUpper();
    static readonly Dictionary<string, string> KindColor = new() { ["defend"] = "#4fc3a1", ["push"] = "#ff8a3d", ["aim"] = "#ff8a3d", ["nade"] = "#5ab4ff", ["situation"] = "#e0a030", ["wallbang"] = "#c792ea", ["crossfire"] = "#ff8a3d", ["momentum"] = "#56d4c8" };
    int postIdx = -1;   // a defense: the spot you hold now (Posts), Posts.Count: free
    // a defense in waves, not in time (30/10, the user: "arrête de faire les situations toujours en termes de temps. Par
    // exemple, j'ai 7 vagues parce que j'attends dans un coin, mais si je les rush ... 10 vagues"): 6 waves over its posts,
    // each post its share of them (a post's time at most 1.5 its share of the drill's, a wave that never ends no stall)
    const int DefendWaves = 6;
    int postWaveN, postAt;
    bool defendDone;

    // the attackers just spawned on your radar a moment, a red dot where each one is (30/10, the user: "ça serait bien d'avoir
    // un petit indicateur sur la carte quoi, en mode point rouge, de où les ennemis sont quand ils respawnent ... juste quand
    // ils spawnent"): spotted by you 2 s from their spawn
    void RadarTick()
    {
        if (radarUntil.Count == 0) return;
        var h = Humans().FirstOrDefault(x => x.PawnIsAlive);
        var now = Server.TickCount;
        foreach (var (sl, until) in radarUntil.ToList())
        {
            if (now >= until || h == null) { radarUntil.Remove(sl); continue; }
            if (Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value is not { LifeState: (byte)LifeState_t.LIFE_ALIVE } pw) continue;
            pw.EntitySpottedState.Spotted = true;
            pw.EntitySpottedState.SpottedByMask[h.Slot / 32] |= 1u << (h.Slot % 32);
            Utilities.SetStateChanged(pw, "CCSPlayerPawn", "m_entitySpottedState");
        }
    }
    readonly Dictionary<int, int> radarUntil = new();   // an attacker on your radar till then: where it spawned (30/10)
    // a defense's attackers come in waves, all of them at once (09/10): the wave's number, its first death (tick), the
    // next one called
    int wave, waveFirstDead = -1;
    bool waveDue;
    // 29/10 (the user: "il faut absolument que les bots veuillent attaquer la zone de bon site ... l'objectif est ... de tuer
    // un maximum de bots par vague ... un maximum de vagues ... en simulant que c'est une vraie attaque de terroristes sur ma
    // défense et que mon objectif est de garder le bon site sans qu'ils le prennent"): each wave held (all of it down before
    // it took the site) or lost (an attacker 3 s on the site, a plant, or you down); a wave that never came to the fight (the
    // bots' fault) counts for nothing. The drill: a wave faced at least, 3 of 4 held, more kills than deaths
    int waveKills, waveOnSite, wavesFaced, wavesHeld;
    bool waveLost, waveFaced, waveGone;
    void WaveEnd(bool down)
    {
        // lost: the site taken, a plant, you down; held: one of it down by you and none of that (the ones the plugin took
        // off away from the fight failed their attack too: 29/10, lab 24, "gone" with 3 down by you counted against you);
        // a wave with no kill and no taking was no fight
        if (waveLost || waveKills > 0)
        {
            wavesFaced++;
            postWaveN++;
            if (!waveLost) wavesHeld++;
            Log("wave {w}: {r}, {k} down by you{g}", wave, waveLost ? "lost" : "held", waveKills, down ? "" : " (the rest taken off)");
        }
        waveKills = 0; waveOnSite = 0; waveLost = false; waveFaced = false; waveGone = false;
    }
    int preKillAt;   // prefire: the last kill (tick); the last ones shown after 8 s without one (09/10)
    readonly HashSet<int> beaconed = new();
    // the aim map: when each target came, the last kill, the strafers' way and its end
    readonly Dictionary<int, int> cameAt = new();
    readonly Dictionary<int, (int sign, int until)> strafe = new();
    int lastKill;
    List<Vector3> rangeTheirs = new();
    // 07/10: the aim range left aim_map (an unsigned 2023 file the game no longer loads from a server) for a map with
    // cover: a spot of theirs you can't see from yours is dropped for the map (a target unseen 3 s moves on)
    // the spots themselves, not their place in rangeTheirs: that list is built again for each drill and narrowed by a
    // cone that depends on the variant (a duel's is 60 deg where a flick's is 80), while this set is only emptied when
    // the map changes, so kept as numbers its entries came to mean other spots from one drill to the next (13/10)
    readonly List<Vector3> rangeBlind = new();

    bool Blind(Vector3 p) => rangeBlind.Any(q => Vector3.Distance(q, p) < 2f);
    readonly Dictionary<int, int> rangeSeenAt = new();
    string rangeMap = "";
    bool rangeSpots;   // a target has been seen this drill: the game's spotting works for them, so unseen means hidden
    readonly List<(Drill d, bool ok, string outcome)> sessDone = new();   // this session's drills, each one's last try
    readonly List<(Drill d, bool ok, string outcome)> lastDone = new();   // the last session's (!again)
    Session? lastSess;
    int againN;

    void RegisterSession()
    {
        AddCommand("css_session", "start a training session: css_session <id>", (p, c) => CmdSession(p, c));
        AddCommand("css_report", "tell Wily's author what's wrong or what you'd want, from where you are: !report <text>", (p, c) => Report(p, c.ArgString));
        AddCommand("css_pause", "pause the session (the block's clock waits): !resume goes on", (p, c) => Pause(p));
        AddCommand("css_resume", "go on with a paused session", (p, c) => Resume(p));
        AddCommand("css_go", "go on with a paused session", (p, c) => Resume(p));
        AddCommand("css_again", "the last session's drills again: !again <number>[,<number>], missed or all", (p, c) => Again(p, c.ArgString));
        RegisterWorkshopGuard();
        RegisterCrossfire();
        RegisterMomentum();
        RegisterSelfTest();
        RegisterRecorder();
        RegisterSandbox();
        RegisterEventHandler<EventSmokegrenadeDetonate>((e, _) => { NadeHit(e.Userid, e.X, e.Y, e.Z, "smoke"); return HookResult.Continue; });
        RegisterEventHandler<EventFlashbangDetonate>((e, _) => { NadeHit(e.Userid, e.X, e.Y, e.Z, "flash"); return HookResult.Continue; });
        RegisterEventHandler<EventHegrenadeDetonate>((e, _) => { NadeHit(e.Userid, e.X, e.Y, e.Z, "he"); return HookResult.Continue; });
        RegisterEventHandler<EventMolotovDetonate>((e, _) => { NadeHit(e.Userid, e.X, e.Y, e.Z, "molotov"); return HookResult.Continue; });
        RegisterExec();
        RegisterSteps();
        RegisterEventHandler<EventBombPlanted>((e, _) => { BombPlanted(); return HookResult.Continue; });
        // your stuff's good use (23/10): what your flashes, HEs and fires did, the ones you killed blinded; your shots in a
        // prefire (its CTs that react)
        RegisterEventHandler<EventPlayerBlind>((e, _) => { UtilBlindEv(e); return HookResult.Continue; });
        RegisterEventHandler<EventPlayerHurt>((e, _) => { UtilHurt(e); return HookResult.Continue; });
        RegisterEventHandler<EventPlayerDeath>((e, _) => { UtilDeath(e); return HookResult.Continue; });
        RegisterEventHandler<EventWeaponFire>((e, _) => { if (e.Userid is { IsValid: true, IsBot: false } && !(e.Weapon ?? "").Contains("knife")) PreShot(); return HookResult.Continue; });
        RegisterListener<Listeners.OnEntitySpawned>(ent =>
        {
            if (sess == null || nadeStage != "throw" || !ent.DesignerName.EndsWith("_projectile")) return;
            var h = ent.Handle;
            Server.NextFrame(() => CamStart(h));   // its thrower is set on the next frame
        });
    }

    static string MapName(string m)
    {
        if (m == "aim_botz") return "Aim Botz";
        var n = m.Replace("de_", "").Replace("cs_", "").Replace("ar_", "");
        return string.Join(" ", n.Split('_', StringSplitOptions.RemoveEmptyEntries).Select(w => char.ToUpper(w[0]) + w[1..]));
    }

    // 07/10, the user's pick for the aim block: Aim Botz (Steam Workshop), loaded by its id. Its own config (run at its
    // load) sets 123 things for its own play: undone before any other map, and the ones that matter undone by each Setup
    public static readonly Dictionary<string, string> Workshop = new() { ["aim_botz"] = "3070244462" };
    static readonly string[] AfterWorkshop = {
        "game_type 0", "game_mode 1", "sv_cheats 0", "sv_infinite_ammo 0", "bot_all_weapons", "bot_join_team any", "bot_join_delay 0",
        "mp_humanteam any", "mp_allowspectators 1", "mp_respawn_on_death_ct 0", "mp_respawn_on_death_t 0", "weapon_auto_cleanup_time 0",
        "weapon_max_before_cleanup 0", "mp_ct_default_primary \"\"", "mp_ct_default_secondary weapon_hkp2000", "mp_t_default_primary \"\"",
        "mp_t_default_secondary weapon_glock", "mp_t_default_melee weapon_knife", "mp_free_armor 0", "mp_max_armor 2", "mp_buy_anywhere 0",
        "mp_startmoney 800", "sv_autobuyammo 0", "sv_buy_status_override -1", "mp_weapons_allow_heavyassaultsuit 0", "mp_drop_knife_enable 0",
        "mp_disconnect_kills_players 0", "mp_force_pick_time 15", "spec_freeze_time 3", "bot_quota 0", "bot_kick" };

    void ChangeMap(string map)
    {
        if (Workshop.ContainsKey(Server.MapName) && !Workshop.ContainsKey(map))
            foreach (var c in AfterWorkshop) Server.ExecuteCommand(c);
        Server.ExecuteCommand(Workshop.TryGetValue(map, out var id) ? $"host_workshop_map {id}" : $"changelevel {map}");
    }

    // 08/10, his warm-up video (20:29 and 20:30): Aim Botz runs its own logic at each round start through its command
    // entities (a point_servercommand and a point_clientcommand, both "@servercommand"): its config again (bot_quota 12,
    // its bots on T, respawns...), bot_add_t, then a check that, short of its 12 bots, sends "restart". The round restart
    // of each drill set it off, and a Workshop map can't be loaded by its name here: the server was left with no map and
    // the player in the menu. On a Workshop map the plugin sets everything itself: the map's command entities are
    // removed, and a load by name goes through the map's Workshop id.
    int wsCut;

    // aimed crouched, thrown standing: said in place of "standing still" (20/10, his video: "il faut m'indiquer que je
    // dois prendre mon repère accroupi": it was only in the chat)
    string HowClick(Drill d)
    {
        var how = d.AimFrom == "crouch" ? T("aim crouched, throw standing") : How(d.How);
        return d.Click != "" ? $"{how} · {How(d.Click)}" : how;
    }

    // a stuff drill's technique and click, the first thing read (19/10, his video: "les types de clics et les types de
    // mouvements à faire, peut-être ce qu'il y a à mettre le plus en valeur")
    string HowBig(Drill d) => $"<font color='#ffd34d' class='fontSize-l'>{HowClick(d).ToUpper()}</font>";

    // the drill's instruction, the banner's first line whatever comes (23/10, the user: "la première ligne du bandeau doit
    // toujours être la consigne : c'est fait pour la défense, à étendre partout")
    static string Big(string s, string color = "#ffd34d") => $"<font color='{color}' class='fontSize-l'>{s}</font>";

    string Order(Drill d) => d.Kind switch
    {
        "nade" when d.Mode == "exec" => Big((d.Arrive > 0 ? T("each one on its spot, all of them before they are on the site") : T("all of them up on the site at the same moment")).ToUpperInvariant()),
        "nade" when d.Mode == "entry" => Big(T("your exec goes as you threw it: go in when it is up").ToUpperInvariant(), "#ff8a3d"),
        "nade" when d.Mode == "hold" => Big(T("they come: your stuff goes as you threw it, hold the site").ToUpperInvariant(), "#ff8a3d"),
        "nade" => HowBig(d),
        "momentum" => d.How == "walk" ? Big(T("WALK IT: Shift held")) : Big(T("JUMP FROM THE GREEN RING, LAND IN THE BLUE ONE"), "#56d4c8"),
        "situation" => Big(string.IsNullOrEmpty(cur?.Goal) ? T("survive") : cur!.Goal, "#e0a030"),
        _ => d.Mode switch
        {
            "prefire" => Big($"🟨 {T("follow the gold line").ToUpperInvariant()} · {T("CLEAR EACH ANGLE")}", "#ff8a3d"),
            "defend" => Big(d.Posts.Count > 0 ? $"🟩 {F("stay in {zone}, the green zone", "zone", d.Posts[0].Zone)}" : $"🟩 {T("HOLD THE SITE: THEY KEEP COMING")}", "#5ad15a"),
            "crossfire" => Big(d.Variant switch { "peek" => T("PEEK IT: STOP, THEN SHOOT"), "spray" => T("ONE SPRAY FOR BOTH, WITHOUT LETTING GO"), _ => T("HOLD THE ANGLE: CROSSHAIR WHERE THEY COME OUT") }, "#ff8a3d"),
            "range" => Big(T("KILL THEM ONE AFTER THE OTHER"), "#ff8a3d"),
            _ when d.Id.StartsWith("wallbang") => Big(T("SHOOT THROUGH THE WALL AT THE RED MARK"), "#c792ea"),
            _ when d.Id.StartsWith("boost") => Big(T("UP ON YOUR TEAMMATE: KILL THEM FROM THERE"), "#c792ea"),
            _ => Big(T("FIND THE TARGET, KILL IT"), "#ff8a3d"),
        },
    };

    // your last throw of this drill, kept in the banner till the next one (23/10, the user: "après chaque lancer : écart à
    // l'impact et temps d'aveuglement de la victime dans le bandeau, pas seulement dans le chat")
    string nadeLast = "";
    string NadeLastLine() => nadeLast == "" ? "" : $"<br><font color='#56d4c8'>{nadeLast}</font>";

    // the angles from an eye to a point (pitch, yaw)
    static Vector3 LookAt(Vector3 eye, Vector3 at)
    {
        var d = at - eye;
        return new Vector3(-MathF.Atan2(d.Z, MathF.Sqrt(d.X * d.X + d.Y * d.Y)) * 180f / MathF.PI, MathF.Atan2(d.Y, d.X) * 180f / MathF.PI, 0f);
    }

    static bool MapLogic(string n) => n.StartsWith("logic_") || n.StartsWith("math_") || n.StartsWith("trigger_")
        || n is "point_servercommand" or "point_clientcommand" or "point_broadcastclientcommand" or "point_script" or "point_template"
            or "game_player_equip" or "player_weaponstrip" or "game_ui" or "game_text" or "env_hudhint";

    void RegisterWorkshopGuard()
    {
        // its logic removed as it spawns (each round restart makes it again): its console commands, its scripts, relays,
        // counters, timers, templates and triggers. 08/10 22:58, his second warm-up: its weapon handling took the drill's
        // rifle at his spawn (@weapon_relay.kill.primary: a Glock and a knife left) and its kill zones killed the strafing
        // targets 15 times in 11 s. Walls, floors and spawns stay. (Reading an output's connections to stop only some of
        // them crashed the server: CounterStrikeSharp's layout of them is off.)
        RegisterListener<Listeners.OnEntitySpawned>(ent =>
        {
            if (!MapLogic(ent.DesignerName) || !Workshop.ContainsKey(Server.MapName)) return;
            ent.Remove();
            if (wsCut++ == 0) Log("workshop map: its own logic removed ({c}...)", ent.DesignerName);
        });
        RegisterListener<Listeners.OnMapStart>(_ => { wsCut = 0; TicksReset(); });
        AddCommand("css_dbgfire", "an input to the entities of that name: css_dbgfire <name> <input> [value]", (p, c) =>
        {
            var n = 0;
            foreach (var e in Utilities.GetAllEntities())
                if (e.IsValid && e.Entity?.Name == c.GetArg(1)) { e.AcceptInput(c.GetArg(2), null, null, c.ArgCount > 3 ? c.GetArg(3) : ""); n++; }
            c.ReplyToCommand($"{n} entities");
        });
        foreach (var cmd in new[] { "restart", "map", "changelevel" })
            AddCommandListener(cmd, (p, info) =>
            {
                if (p != null) return HookResult.Continue;   // a player's own console: the game's rules
                var target = cmd == "restart" || info.ArgCount < 2 ? Server.MapName : info.GetArg(1);
                if (!Workshop.TryGetValue(target, out var id)) return HookResult.Continue;
                Log("workshop map: \"{c}\" by name stopped", info.GetCommandString);
                if (cmd != "restart") Server.NextFrame(() => Server.ExecuteCommand($"host_workshop_map {id}"));
                return HookResult.Stop;
            }, HookMode.Pre);
    }

    // the screen: the drill's line stays all the time (sent again every 0.4 s), an event shows above it for a few seconds
    string hudMain = "", hudFlash = "";
    // 23/10 eve, the user live: "le bandeau d'information ne cesse d'apparaître et de disparaître, ce qui crée des flashs
    // visuels": with CS2 1.41.9.2 the panel came back as a blank white box between two sends (sent every 26 ticks for
    // 1 s). Each send showed it white a moment (24 pictures each: sent every 8 ticks 11 white, every 26 ticks 6-8, every
    // 64 none): sent now when its instruction (first line) changes, a number in it (a countdown) at most every half second,
    // else again every 1.5 s, shown 2 s. css_hud <seconds> <ticks> [gap ticks] while it is tried out.
    // 29/10 (the user, Mirage's defense: "le bandeau d'informations ... re clignote"): its countdown sent every 32 ticks, in
    // the white range; now a number at most every 64 ticks (none white at that pace), a new instruction 24 ticks after the
    // last send at the soonest (in and out of the green zone at its edge it was sent at once each time)
    int hudDur = 2, hudEvery = 96, hudGap = 64, hudOrderGap = 24;
    bool hudOrder;
    bool hudDirty;
    DateTime hudFlashUntil;
    int hudSent;
    void Html(string html, int secs = 3) { hudFlash = html; hudFlashUntil = DateTime.UtcNow.AddSeconds(secs); SendHud(); }
    void SetMain(string html)
    {
        if (html == hudMain) return;
        static string First(string s) { var k = s.IndexOf("<br>", StringComparison.Ordinal); return k < 0 ? s : s[..k]; }
        var order = First(html) != First(hudMain);
        hudMain = html;
        if (order && Server.TickCount - hudSent >= hudOrderGap) SendHud(); else { hudDirty = true; hudOrder |= order; }
    }
    void SendHud()
    {
        hudSent = Server.TickCount;
        hudDirty = false; hudOrder = false;
        var fl = DateTime.UtcNow < hudFlashUntil ? hudFlash : "";
        // the drill's instruction always on top while it is played (23/10, the user: "la première ligne du bandeau doit
        // toujours être la consigne"): an event goes under its first line; a drill's result (done) on top
        string h;
        var k = hudMain.IndexOf("<br>", StringComparison.Ordinal);
        if (fl != "" && hudMain != "" && phase is "live" or "countdown")
            h = k < 0 ? $"{hudMain}<br>{fl}" : $"{hudMain[..k]}<br>{fl}{hudMain[k..]}";
        else h = fl != "" && hudMain != "" ? $"{fl}<br>{hudMain}" : fl + hudMain;
        if (h == "") return;
        foreach (var p in Humans()) p.PrintToCenterHtml(h, hudDur);
    }
    void HudTick()
    {
        if (hudTestUntil > 0) HudTestTick();
        if (sess == null && hudFlash == "") return;
        var dt = Server.TickCount - hudSent;
        if (dt < 0 || (hudDirty && dt >= (hudOrder ? hudOrderGap : hudGap)) || dt >= hudEvery) SendHud();   // < 0: sent on the map before (TicksReset)
    }

    // the server's tick count starts again from 0 on each map, the plugin's stamps stay (24/10, the real-client battery:
    // coach/steps_live.json not written for the 14.7 min the map before had lasted, so neither the driver nor the Live
    // page saw a toggle; the banner not sent again but on a new instruction; you unhurt till protectUntil): all from 0
    void TicksReset()
    {
        stLiveAt = hudSent = protectUntil = tradeUntil = cfGlowUntil = flashUntil = 0;
        guideFlyUntil = guideNext = botsLiveAt = preKillAt = stLast = moAirAt = moChainAt = 0;
    }

    // css_hudtest same|tick|len <seconds>: a banner of its own while no session runs, to tell its white flashes apart
    // (23/10 eve): the same words sent again, words changing every second at the same length, or at another length
    string hudTestMode = "";
    int hudTestFrom, hudTestUntil;
    void HudTestTick()
    {
        var now = Server.TickCount;
        if (now >= hudTestUntil) { hudTestUntil = 0; hudFlash = ""; return; }
        var s = (now - hudTestFrom) / 64;
        var text = hudTestMode switch
        {
            "tick" => $"<font color='#ffd34d'>TEST DU BANDEAU</font><br>la même longueur · {s % 10} s",
            "len" => $"<font color='#ffd34d'>TEST DU BANDEAU</font><br>une longueur qui change{new string('.', s % 6)}",
            _ => "<font color='#ffd34d'>TEST DU BANDEAU</font><br>les mêmes mots renvoyés",
        };
        if (text != hudFlash) { hudFlash = text; hudFlashUntil = DateTime.UtcNow.AddSeconds(30); SendHud(); }
    }

    // prefire: the way, a gold line on the ground
    readonly List<CBeam> beams = new();
    void DrawLine(List<float[]> pts)
    {
        ClearLine();
        var gold = System.Drawing.Color.FromArgb(255, 255, 205, 60);
        for (int i = 0; i + 1 < pts.Count; i++)
        {
            var a = new Vector3(pts[i][0], pts[i][1], pts[i][2] + 8);
            var b = new Vector3(pts[i + 1][0], pts[i + 1][1], pts[i + 1][2] + 8);
            Beam(a, b, gold, 5f);   // 06/10: a line you see from afar ("le path à prendre au sol avec un trait"; no arrows: "pas besoin de flèches")
        }
    }
    void ClearLine() { foreach (var b in beams) if (b.IsValid) b.Remove(); beams.Clear(); beamQ.Clear(); crossBeams.Clear(); crossFor = null; }

    // a situation's zone: its place's outline (or a ring when the place is unknown), light blue
    void DrawZone(Scenario s)
    {
        var blue = System.Drawing.Color.FromArgb(255, 90, 180, 255);
        if (s.ZonePoly.Count >= 3)
            for (int i = 0; i < s.ZonePoly.Count; i++)
            {
                var a = s.ZonePoly[i]; var b = s.ZonePoly[(i + 1) % s.ZonePoly.Count];
                Beam(new Vector3(a[0], a[1], a[2] + 6), new Vector3(b[0], b[1], b[2] + 6), blue, 4f);
            }
        else if (s.ZoneAt is { Length: >= 3 } at)
            for (int i = 0; i < 24; i++)
            {
                float a0 = i * MathF.PI / 12, a1 = (i + 1) * MathF.PI / 12;
                Beam(new Vector3(at[0] + 250 * MathF.Cos(a0), at[1] + 250 * MathF.Sin(a0), at[2] + 6),
                     new Vector3(at[0] + 250 * MathF.Cos(a1), at[1] + 250 * MathF.Sin(a1), at[2] + 6), blue, 3f);
            }
    }

    // the beams spawned a few a tick (28/10 01:02, the third overflow kick of the night, each at a drill's start: its round
    // restart and its marks, rings or zone outline, 30-70 beams, all in one tick: "Too many queued messages")
    readonly Queue<(Vector3 a, Vector3 b, System.Drawing.Color c, float w, bool cross)> beamQ = new();
    const int BeamsATick = 8;
    void Beam(Vector3 a, Vector3 b2, System.Drawing.Color c, float w, bool cross = false) => beamQ.Enqueue((a, b2, c, w, cross));
    void BeamTick()
    {
        for (var k = 0; k < BeamsATick && beamQ.Count > 0; k++)
        {
            var (a, b2, c, w, cross) = beamQ.Dequeue();
            if (BeamNow(a, b2, c, w) is { } made && cross) crossBeams.Add(made);
        }
    }

    CBeam? BeamNow(Vector3 a, Vector3 b2, System.Drawing.Color c, float w)
    {
        var b = Utilities.CreateEntityByName<CBeam>("beam");
        if (b == null) return null;
        b.Render = c;
        b.Width = w;
        b.Teleport(a, Vector3.Zero, Vector3.Zero);
        b.EndPos.X = b2.X; b.EndPos.Y = b2.Y; b.EndPos.Z = b2.Z;
        // nothing in the way: a line drawn, never a wall (30/10: the client stopped 38 u off a spot inside its 18 u ring on
        // Train and Dust2, the stand's ring a wall since 29/10's game update; bots slid along a zone's outline)
        b.Collision.SolidType = SolidType_t.SOLID_NONE;
        b.Collision.SolidFlags |= 4;   // FSOLID_NOT_SOLID
        b.DispatchSpawn();
        beams.Add(b);
        return b;
    }

    // stuff: where it must land: a beam standing there (from under your feet to well above when its height is not
    // known), and a ring on the ground of the PERFECT zone when it is
    void DrawMark(float x, float y, float z, float? ground, float r)
    {
        var blue = System.Drawing.Color.FromArgb(255, 90, 180, 255);
        Beam(new Vector3(x, y, (ground ?? z) - (ground == null ? 300 : 0)), new Vector3(x, y, (ground ?? z) + (ground == null ? 500 : 260)), blue, 5f);
        if (ground == null) return;
        for (int i = 0; i < 16; i++)
        {
            var a0 = i * MathF.PI / 8; var a1 = (i + 1) * MathF.PI / 8;
            Beam(new Vector3(x + r * MathF.Cos(a0), y + r * MathF.Sin(a0), ground.Value + 4), new Vector3(x + r * MathF.Cos(a1), y + r * MathF.Sin(a1), ground.Value + 4), blue, 3f);
        }
    }

    // stuff: where you stand, a green ring at your feet (06/10: "le repère de où moi je dois me mettre, il n'y en a pas")
    // a run-throw's step (19/10, his 17/10 video: "celle-là elle est compliquée, faudrait d'autres repères quand c'est à
    // lancer en courant"): the base's run-throws leave the hand at a step's speed (about 150 u/s: a W pressed as the click
    // is let go, wily/insights/nades.py), not a full run's: an arrow from the green ring the way you step, and the words
    static bool Stepped(Drill d) { var h = d.How.ToLowerInvariant(); return h.Contains("forward") || h.Contains("run"); }

    string StepHint(Drill d) => d.AimFrom == "crouch" ? $"<br><font color='#56d4c8'>{T("take the aim crouched (the yellow circle), then stand up and throw")}</font>"
        : !Stepped(d) ? (d.How.ToLowerInvariant().Contains("jumpthrow")
        ? $"<br><font color='#56d4c8'>{T("aim in the yellow circle standing, then jump and let go without moving the mouse")}</font>" : "")
        : "<br><font color='#56d4c8'>" + (d.How.ToLowerInvariant().Contains("jump")
        ? T("from the green ring: W, jump and let the click go at the same moment (no run-up)")
        : T("from the green ring: W and let the click go at the same moment (no run-up)")) + "</font>";

    void DrawStep(Drill d)
    {
        if (d.Me == null || !Stepped(d)) return;
        var teal = System.Drawing.Color.FromArgb(255, 86, 212, 200);
        float y = d.Me.Ang[1] * MathF.PI / 180;
        var fw = new Vector3(MathF.Cos(y), MathF.Sin(y), 0);
        var side = new Vector3(-fw.Y, fw.X, 0);
        var a = new Vector3(d.Me.Pos[0], d.Me.Pos[1], d.Me.Pos[2] + 3) + fw * 20f;
        var b = a + fw * 40f;
        Beam(a, b, teal, 1.5f);
        Beam(b, b - fw * 12f + side * 8f, teal, 1.5f);
        Beam(b, b - fw * 12f - side * 8f, teal, 1.5f);
    }

    void DrawStand(Spot me)
    {
        var green = System.Drawing.Color.FromArgb(255, 90, 230, 90);
        var c = new Vector3(me.Pos[0], me.Pos[1], me.Pos[2] + 3);
        for (int i = 0; i < 12; i++)
        {
            float a0 = i * MathF.PI / 6, a1 = (i + 1) * MathF.PI / 6;
            Beam(c + new Vector3(18 * MathF.Cos(a0), 18 * MathF.Sin(a0), 0), c + new Vector3(18 * MathF.Cos(a1), 18 * MathF.Sin(a1), 0), green, 1.5f);
        }
    }

    // the good use of your stuff (23/10, the user: "les points récompensent surtout les kills. Ajouter ... le bon usage du
    // stuff, comme le bonus « tué aveuglé »"): the enemies your flashes blind a second or more, your grenades' damage, the
    // ones you kill still blinded (an exec's entry counts its own)
    int utilBlind, utilDmg, utilBlindKills;
    int UtilPts => utilBlind * 15 + utilDmg / 3 + utilBlindKills * BlindKillPts;
    string UtilDetail() => utilBlind + utilDmg + utilBlindKills == 0 ? ""
        : $" · {F("stuff +{p}: {b} blinded, {d} HP, {k} killed blinded", "p", UtilPts, "b", utilBlind, "d", utilDmg, "k", utilBlindKills)}";
    bool UtilOn => sess != null && phase == "live" && cur != null && cur.Kind != "nade" && !MoOn;

    void UtilBlindEv(EventPlayerBlind e)
    {
        if (!UtilOn || e.Attacker is not { IsValid: true, IsBot: false } || e.Userid is not { IsValid: true, IsBot: true } v) return;
        if (!bots.TryGetValue(v.Slot, out var t) || t.Team == cur!.Team || e.BlindDuration < 1f) return;
        utilBlind++;
        Html($"<font color='#ffd34d'>💥 {F("blinded {s} s: +{p}", "s", e.BlindDuration.ToString("F1", CultureInfo.InvariantCulture), "p", 15)}</font>", 1);
    }

    void UtilHurt(EventPlayerHurt e)
    {
        if (!UtilOn || e.Attacker is not { IsValid: true, IsBot: false } || e.Userid is not { IsValid: true, IsBot: true } v) return;
        if (!bots.TryGetValue(v.Slot, out var t) || t.Team == cur!.Team) return;
        var w = e.Weapon ?? "";
        if (w.Contains("hegrenade") || w.Contains("inferno") || w.Contains("molotov") || w.Contains("incgrenade")) utilDmg += e.DmgHealth;
    }

    void UtilDeath(EventPlayerDeath e)
    {
        if (!UtilOn || e.Attacker is not { IsValid: true, IsBot: false } || e.Userid is not { IsValid: true, IsBot: true } v) return;
        if (!bots.TryGetValue(v.Slot, out var t) || t.Team == cur!.Team) return;
        if (v.PlayerPawn.Value is { } vp && vp.BlindUntilTime > Server.CurrentTime)
        {
            utilBlindKills++;
            Html($"<font color='#ffd34d'>💥 {F("down blinded: +{p}", "p", BlindKillPts)}</font>", 1);
        }
    }

    // a wallbang: where to shoot in the wall and the bullet's way to each target (23/10, the user: "montrer où tirer dans
    // le mur (le point de passage) et la trajectoire jusqu'à la cible"): from your eyes on your spot to its head, the
    // wall's face it goes in at (a red cross there), its way to it from you and on through to the head (thin red lines);
    // at Easy each one glows through the wall
    void WallMarks()
    {
        if (drill?.Me == null || cur == null) return;
        var me = Humans().FirstOrDefault(h => h.PawnIsAlive)?.PlayerPawn.Value;
        var red = System.Drawing.Color.FromArgb(255, 255, 70, 70);
        var eye = new Vector3(drill.Me.Pos[0], drill.Me.Pos[1], drill.Me.Pos[2] + 64f);
        var shot = new TraceOptions { InteractsWith = Masks.ShotBrushOnly };
        var n = 0;
        foreach (var (sl, t) in bots)
        {
            if (t.Team == cur.Team || gone.Contains(t.Sid)) continue;
            var c = Utilities.GetPlayerFromSlot(sl);
            var head = Pos(t, 0) + new Vector3(0f, 0f, t.Duck ? 44f : 62f);
            var tr = Trace.TraceEndShape(new CVector(eye.X, eye.Y, eye.Z), new CVector(head.X, head.Y, head.Z), me ?? c?.PlayerPawn.Value, shot);
            if (tr.Fraction >= 0.98f) continue;   // nothing between: no wall to shoot through
            var dir = Vector3.Normalize(head - eye);
            var hit = eye + (head - eye) * tr.Fraction - dir * 2f;
            var right = Vector3.Normalize(new Vector3(-dir.Y, dir.X, 0f));
            var up = Vector3.Normalize(Vector3.Cross(right, dir));
            Beam(hit - right * 7f - up * 7f, hit + right * 7f + up * 7f, red, 1.2f);
            Beam(hit - right * 7f + up * 7f, hit + right * 7f - up * 7f, red, 1.2f);
            Beam(eye + dir * 60f, hit, red, 0.3f);   // its way from you to the wall
            Beam(hit + dir * 4f, head, red, 0.4f);   // and on through it to the head
            n++;
            if (difficulty == 0 && c != null) CfGlowMake(c, cfGlowN, 600f);   // Easy: seen through it
        }
        if (selftest) St("wall_marks", new() { ["n"] = n });
        Log("wallbang: {n} marks on the wall", n);
    }

    // a situation: an ally down, a red cross where it fell, a post over it seen from afar
    void DrawX(Vector3 p)
    {
        var red = System.Drawing.Color.FromArgb(255, 255, 70, 70);
        Beam(p + new Vector3(-22, -22, 4), p + new Vector3(22, 22, 4), red, 3f);
        Beam(p + new Vector3(-22, 22, 4), p + new Vector3(22, -22, 4), red, 3f);
        Beam(p + new Vector3(0, 0, 4), p + new Vector3(0, 0, 90), red, 2f);
    }

    // stuff: a small yellow ring 150 u ahead on the aim, from your eyes: the crosshair in it, the map's own marks seen
    // through it (19/10, his 17/10 video: the two green crosses, 150 and 40 u ahead, came apart as you stand a hair
    // higher, "pourquoi il y a deux croix l'une par-dessus l'autre", "ta grosse croix ne permet pas de savoir ce que je
    // vise ... un rond permettrait justement d'avoir des croisements de lignes")
    // the aim circle's beams and the eye it was drawn for (30/10, his review on Dust2's A smoke: "l'indication du repère visuel
    // n'est pas bon", the banner's words right): drawn again from your own eye once you stand still on the spot
    readonly List<CBeam> crossBeams = new();
    Vector3 crossEye;
    Drill? crossFor;

    void DrawCross(Drill d, Vector3? eyeAt = null)
    {
        if (d.Me == null) return;
        // aimed crouched (20/10, his exec B molotov: "c'est un repère que tu prends accroupi, ensuite tu te relèves"): the
        // circle seen from the crouched eye
        var eye = eyeAt ?? new Vector3(d.Me.Pos[0], d.Me.Pos[1], FloorZ(d.Me.Pos) + (CrouchAim(d) ? 46 : 64));
        crossEye = eye; crossFor = d;
        float p = d.Me.Ang[0] * MathF.PI / 180, y = d.Me.Ang[1] * MathF.PI / 180;
        var fw = new Vector3(MathF.Cos(p) * MathF.Cos(y), MathF.Cos(p) * MathF.Sin(y), -MathF.Sin(p));
        var right = new Vector3(MathF.Sin(y), -MathF.Cos(y), 0);
        var up = Vector3.Normalize(Vector3.Cross(right, fw));
        var yellow = System.Drawing.Color.FromArgb(255, 255, 211, 77);
        var at = eye + fw * 150f;
        var r = 150f * MathF.Tan(AimTolOf(d) * MathF.PI / 180f);   // 0.9 degree around the aim (a crosshair's width), less for a throw its bounce makes touchy (23/10)
        for (int i = 0; i < 16; i++)
        {
            float a0 = i * MathF.PI / 8, a1 = (i + 1) * MathF.PI / 8;
            Beam(at + (right * MathF.Cos(a0) + up * MathF.Sin(a0)) * r, at + (right * MathF.Cos(a1) + up * MathF.Sin(a1)) * r, yellow, 0.5f, true);
        }
        // four short marks around it, to find it at a glance (20/10, his video: "des fois c'est un peu compliqué de voir le
        // cercle de visée"); the ring itself stays a crosshair's width
        foreach (var dir in new[] { right, -right, up, -up })
            Beam(at + dir * (r * 2f), at + dir * (r * 4.5f), yellow, 0.45f, true);
    }

    // you still on the spot (16 u), on the ground: the circle from your own eye, its height and its place (150 u off, 2 u
    // aside is a degree); drawn again once your eye moved 1.5 u
    void CrossFollow()
    {
        if (drill?.Me == null || crossFor != drill) return;
        var h = Humans().FirstOrDefault(x => x.PawnIsAlive)?.PlayerPawn.Value;
        if (h?.AbsOrigin is not { } o || (h.Flags & (uint)CounterStrikeSharp.API.Modules.Utils.PlayerFlags.FL_ONGROUND) == 0) return;
        if (new Vector2(o.X - drill.Me.Pos[0], o.Y - drill.Me.Pos[1]).Length() > 16f) return;
        if (h.AbsVelocity is { } v && new Vector2(v.X, v.Y).Length() > 5f) return;
        var eye = new Vector3(o.X, o.Y, o.Z + (CrouchAim(drill) ? 46f : 64f));
        if (Vector3.Distance(eye, crossEye) < 1.5f) return;
        foreach (var b in crossBeams) if (b.IsValid) b.Remove();
        beams.RemoveAll(b => crossBeams.Contains(b));
        crossBeams.Clear();
        var keep = beamQ.Where(x => !x.cross).ToList();   // the old circle's beams not drawn yet: never
        beamQ.Clear();
        foreach (var x in keep) beamQ.Enqueue(x);
        DrawCross(drill, eye);
    }

    // the floor under a spot (23/10 eve, the user live on Mirage's exec A: "tu vises au bon endroit, mais l'indication de
    // visée n'est pas au bon endroit", its smoke and its flash, both jumpthrows): a jumpthrow's spot is where the base's
    // player let go, some 20 u up in his jump; the circle seen from an eye 64 u over that point was 8 degrees off the one of
    // a player standing there. Its own height when nothing is under it within 60 u (a spot on a box keeps the box's top).
    float FloorZ(float[] pos)
    {
        var ign = (CBaseEntity?)Humans().FirstOrDefault(h => h.PawnIsAlive)?.PlayerPawn.Value
                  ?? Utilities.GetPlayers().FirstOrDefault(x => x.PlayerPawn.Value != null)?.PlayerPawn.Value;
        if (ign == null) return pos[2];
        var shot = new TraceOptions { InteractsWith = Masks.ShotBrushOnly };
        var tr = Trace.TraceEndShape(new CVector(pos[0], pos[1], pos[2] + 8f), new CVector(pos[0], pos[1], pos[2] - 60f), ign, shot);
        return tr.Fraction >= 1f ? pos[2] : MathF.Min(pos[2], pos[2] + 8f - 68f * tr.Fraction);
    }

    // a flash's pop: a ring in the air where it pops, nothing standing in your view (20/10, his video: "le trait bleu de
    // la flash, de l'endroit où est censé pop la flash, me bloque la visée sur le repère visuel que je suis censé prendre")
    void DrawPop(float[] tg, float r)
    {
        var blue = System.Drawing.Color.FromArgb(255, 90, 180, 255);
        for (int i = 0; i < 16; i++)
        {
            var a0 = i * MathF.PI / 8; var a1 = (i + 1) * MathF.PI / 8;
            Beam(new Vector3(tg[0] + r * MathF.Cos(a0), tg[1] + r * MathF.Sin(a0), tg[2]), new Vector3(tg[0] + r * MathF.Cos(a1), tg[1] + r * MathF.Sin(a1), tg[2]), blue, 2f);
        }
    }

    // CS2's grenade practice views (stuff drills only): the trail after the throw. Never the landing preview while you
    // aim (04/10: "the camera at the bottom left is a bit of a cheat": in a match you find the throw without it)
    void Prac(bool on)
    {
        if (on == pracOn) return;
        pracOn = on;
        Server.ExecuteCommand("sv_grenade_trajectory_prac_pipreview 0");
        Server.ExecuteCommand($"sv_grenade_trajectory_prac_trailtime {(on ? 4 : 0)}");
    }

    // the grenade camera: your view follows your grenade (a camera prop as your view entity), you wait meanwhile
    void CamStart(nint h)
    {
        if (sess == null || drill == null || cur?.Kind != "nade" || nadeStage != "throw" || cam != null || ExecOn) return;   // an exec: no camera, you go on throwing
        var nd = new CBaseCSGrenadeProjectile(h);
        if (!nd.IsValid || nd.Thrower.Value?.OriginalController.Value is not { IsBot: false } c) return;
        var pawn = c.PlayerPawn.Value;
        if (pawn?.CameraServices == null) return;
        var cp = Utilities.CreateEntityByName<CDynamicProp>("prop_dynamic");
        if (cp == null) return;
        cp.DispatchSpawn();
        // an empty model, drawn by nobody: without a model it was the ERROR model, its shadow following your grenade
        // (04/10: "the shadow of the Gmod ERROR is still there")
        cp.SetModel(NullModel);
        cp.RenderMode = RenderMode_t.kRenderNone;
        Utilities.SetStateChanged(cp, "CBaseModelEntity", "m_nRenderMode");
        cp.AcceptInput("DisableShadow");
        cam = cp; camNade = nd; camEnd = Server.TickCount + 8 * 64;   // at most 8 s
        camDir = new Vector3(1, 0, 0);
        CamTick();
        pawn.CameraServices.ViewEntity.Raw = cp.EntityHandle.Raw;
        Utilities.SetStateChanged(pawn, "CBasePlayerPawn", "m_pCameraServices");
        Freeze(pawn, true);
    }

    void CamTick()
    {
        if (cam == null) return;
        if (!cam.IsValid) { cam = null; return; }
        SkyWalkTick();   // an entry's sky view: you on your way in (Entry.cs)
        if (EntryFlyTick()) return;   // an entry's sky view coming down into your eyes (Entry.cs)
        if (camNade != null && camNade.IsValid && camNade.AbsOrigin is { } o)
        {
            var pos = new Vector3(o.X, o.Y, o.Z);
            var v = camNade.AbsVelocity;
            var vel = v == null ? Vector3.Zero : new Vector3(v.X, v.Y, v.Z);
            if (vel.Length() > 60) camDir = Vector3.Normalize(vel);   // landed: the last way it went
            var at = pos - camDir * 90 + new Vector3(0, 0, 20);
            var look = pos - at;
            var yaw = MathF.Atan2(look.Y, look.X) * 180 / MathF.PI;
            var pitch = -MathF.Atan2(look.Z, MathF.Sqrt(look.X * look.X + look.Y * look.Y)) * 180 / MathF.PI;
            cam.Teleport(at, new Vector3(pitch, yaw, 0), Vector3.Zero);
        }
        if (Server.TickCount >= camEnd) CamStop();
    }

    void CamStop()
    {
        var cp = cam;
        cam = null; camNade = null;
        foreach (var h in Humans())
        {
            var pawn = h.PlayerPawn.Value;
            if (pawn?.CameraServices == null) continue;
            pawn.CameraServices.ViewEntity.Raw = uint.MaxValue;
            AddTimer(0.3f, () => { if (pawn.IsValid) Utilities.SetStateChanged(pawn, "CBasePlayerPawn", "m_pCameraServices"); });
            if (nadeStage == "throw") Freeze(pawn, false);
        }
        if (cp != null) AddTimer(0.4f, () => { if (cp.IsValid) cp.Remove(); });
    }

    // the smokes and fires on the ground: gone (a missed throw's, your own before their side's)
    static void ClearNades()
    {
        foreach (var cls in new[] { "smokegrenade_projectile", "molotov_projectile", "incendiarygrenade_projectile", "inferno" })
            foreach (var e in Utilities.FindAllEntitiesByDesignerName<CBaseEntity>(cls))
                if (e.IsValid) e.Remove();
    }

    // from their side: you stand where the enemies it is for stand, on the line they hold there, and the same grenade comes again
    void Theirs((bool ok, string outcome, int pts, string detail) res)
    {
        if (drill == null || drill.Victims.Count == 0) { DrillDone(res.ok, res.outcome, res.pts, res.detail); return; }
        if (selftest && stGuided) { GuideVictims(res); return; }   // the guide checks each of them (SelfTest.cs)
        // the best one first, the next one on a try again (20/10, his video: "la personne qui l'a subi était mieux sur la
        // version d'avant": one of two at random each time)
        var v = drill.Victims[tries % drill.Victims.Count];
        nadeStage = "theirs"; theirsDmg = 0; theirsFlash = 0; theirsRes = res;
        var face = VictimFace(drill, v);
        foreach (var h in Humans())
        {
            var pawn = h.PlayerPawn.Value;
            if (pawn == null || !h.PawnIsAlive) continue;
            pawn.Teleport(new Vector3(v.Pos[0], v.Pos[1], v.Pos[2]), Upright(face), Vector3.Zero);
            Freeze(pawn, true);
        }
        SetMain($"{Big($"👁 {T("FROM THEIR SIDE")} · {T("where they really stand: watch it come")}", "#5ab4ff")}<br>{drill.Title}{NadeLastLine()}");
        var g = sessGen;
        AddTimer(0.8f, () =>
        {
            if (g != sessGen || nadeStage != "theirs") return;
            // your own throw's smoke or fire goes first: only the one coming at you (04/10: "a double smoke")
            ClearNades();
            Server.ExecuteCommand("sv_cheats 1");   // only for this: the same grenade again
            Server.ExecuteCommand("sv_rethrow_last_grenade");
            Server.ExecuteCommand("sv_cheats 0");
        });
        AddTimer(12f, () => TheirsDone(g));   // in case it never pops
    }

    // where a victim looks: the line it holds; a flash's turned to where it pops (19/10, his video: "n'oublie pas de bien
    // orienter la personne qui subit la flash vers l'endroit où est la flash, là j'ai dû me retourner à la main")
    Vector3 VictimFace(Drill d, Spot v)
    {
        if (d.Type == "flash" && nadePop is { } fp)
            return LookAt(new Vector3(v.Pos[0], v.Pos[1], v.Pos[2] + 64), fp);
        return new Vector3(v.Ang[0], v.Ang[1], 0);
    }

    // it popped on them: what it did, then the drill ends
    void TheirsPopped()
    {
        if (drill == null || nadeStage != "theirs") return;
        var g = sessGen;
        AddTimer(0.2f, () =>
        {
            if (g != sessGen) return;
            foreach (var h in Humans()) theirsFlash = Math.Max(theirsFlash, h.PlayerPawn.Value?.FlashDuration ?? 0);
        });
        AddTimer(drill.Type switch { "smoke" => 5f, "molotov" => 4f, "flash" => 3f, _ => 2.5f }, () => TheirsDone(g));
    }

    void TheirsDone(int g)
    {
        if (g != sessGen || nadeStage != "theirs" || theirsRes == null || drill == null) return;
        nadeStage = "";
        foreach (var h in Humans()) { var pw = h.PlayerPawn.Value; if (pw != null) Freeze(pw, false); }
        var what = drill.Type switch
        {
            "flash" => theirsFlash > 0.3f ? F("blinded {s} s here", "s", theirsFlash.ToString("F1", CultureInfo.InvariantCulture)) : T("not blinded from here: it pops out of their sight"),
            "smoke" => T("their view through it: cut"),
            _ => theirsDmg > 0 ? F("−{hp} HP here", "hp", theirsDmg) : T("no damage here"),
        };
        nadeLast += $" · {what}";   // the throw's line keeps what it did to them (23/10)
        var r = theirsRes.Value;
        theirsRes = null;
        // a damage grenade that hurt nobody where they stand is no landing (27/10, the user: "si un stuff utilisé pour mettre
        // des dégâts ... ne fait pas de dégâts sur la personne, sur le point de vue de la personne qui l'a subi, c'est
        // peut-être qu'elle a explosé en l'air. Typiquement sur Inferno, t'as validé une molotov qui a explosé en l'air")
        if (r.ok && drill.Type is "molotov" or "he" or "incgrenade" && theirsDmg <= 0)
        {
            Log("their side: {t} did no damage, the throw not counted", drill.Type);
            r = (false, "miss", 0, r.detail);
        }
        DrillDone(r.ok, r.outcome, r.pts, $"{r.detail} · {F("from their side: {what}", "what", what)}");
    }

    // prefire: where the last ones are (the game's place names: "BombsiteA" -> "Bombsite A")
    string LeftPlaces()
    {
        var names = bots.Where(b => !gone.Contains(b.Value.Sid) && !peekAt.ContainsKey(b.Key))
            .Select(b => Utilities.GetPlayerFromSlot(b.Key)?.PlayerPawn.Value?.LastPlaceName)
            .Where(n => !string.IsNullOrEmpty(n))
            .Select(n => System.Text.RegularExpressions.Regex.Replace(n!, "(?<=[a-z])(?=[A-Z0-9])", " ")).Distinct();
        return string.Join(", ", names);
    }

    void CmdSession(CCSPlayerController? p, CommandInfo c)
    {
        var id = c.GetArg(1);
        var f = System.IO.Path.Combine(Dir, "sessions", id + ".json");
        Io(() =>   // a session is 1-2 MB of JSON: read and parsed off the game's thread (08/10)
        {
            Session? s = null;
            string? err = null;
            var u = ReadUi();   // the app's language: written with the session
            try { if (File.Exists(f)) s = JsonSerializer.Deserialize<Session>(File.ReadAllText(f)); else err = "?"; }
            catch (Exception e) { err = e.Message; }
            OnGame(() =>
            {
                UseUi(u);
                if (err == "?") err = F("no session {id}", "id", id);
                if (err != null) { Say(p is { IsValid: true } ? p : null, err); return; }
                if (s == null || s.Blocks.Count == 0) { sess = null; return; }
                StartSession(s);
            });
        });
    }

    // a situation's file (the whole round of the demo, hundreds of KB) read by the io thread: null while it loads
    readonly Dictionary<string, Scenario?> scLoaded = new();
    readonly HashSet<string> scLoading = new();
    Scenario? PeekSoon(string id, out bool pending)
    {
        pending = false;
        if (scLoaded.Remove(id, out var s)) return s;
        pending = true;
        if (scLoading.Add(id))
            Io(() => { var r = Peek(id); OnGame(() => { scLoading.Remove(id); scLoaded[id] = r; }); });
        return null;
    }

    void StartSession(Session s)
    {
        SandboxOff();
        sess = s;
        difficulty = Math.Clamp(sess.Difficulty, 0, 3);
        if (sess.Seed is int sd) Rng = new Random(sd);
        mode = "actor";
        blockIdx = -1; points = streak = okN = doneN = drillNo = 0; drill = null; queue.Clear(); cur = null;
        sessDone.Clear();
        paused = false;   // 24/10: the last session's pause kept, a resume in its welcome started its block twice: ended at once
        Log("session {id}: {n} blocks", sess.Id, sess.Blocks.Count);
        if (!Humans().Any() && !selftest) { phase = "waiting"; return; }   // starts when you join (a self-test: nobody comes)
        Welcome();
        AddTimer(4f, () => { if (sess == s && blockIdx < 0 && !paused) NextBlock(); });
    }

    // the drills of the session that just ended, played again: one or some (!again 3, !again 2,5), the missed ones
    // (!again missed) or all of them (!again all), in their order, all of them whatever the time (04/10: "a recap with
    // inputs to replay the situations I missed, the defenses, the prefires, or restart the whole session")
    void Again(CCSPlayerController? p, string arg)
    {
        if (lastSess == null || lastDone.Count == 0) { Say(p, T("no session to play again yet")); return; }
        if (sess != null) { Say(p, T("a session is running: !stop first")); return; }
        arg = arg.Trim().ToLowerInvariant();
        var pick = arg is "" or "all" ? lastDone.Select(x => x.d).ToList()
            : arg == "missed" ? lastDone.Where(x => !x.ok).Select(x => x.d).ToList()
            : arg.Split(new[] { ',', ' ' }, StringSplitOptions.RemoveEmptyEntries).Select(x => int.TryParse(x, out var n) ? n - 1 : -1)
                 .Where(n => n >= 0 && n < lastDone.Count).Distinct().Select(n => lastDone[n].d).ToList();
        if (pick.Count == 0) { Say(p, arg == "missed" ? T("nothing missed: well played") : T("!again and a drill's number, missed or all")); return; }
        var blocks = new List<Block>();
        foreach (var d in pick)   // the drills of one map and one kind in a row: one block
        {
            var kind = d.Kind != "aim" ? d.Kind : d.Mode == "defend" ? "defend" : d.Mode == "prefire" ? "push" : d.Mode == "crossfire" ? "crossfire" : "aim";
            if (blocks.Count > 0 && blocks[^1].Map == d.Map && blocks[^1].Kind == kind) blocks[^1].Drills.Add(d);
            else blocks.Add(new Block { Map = d.Map, Kind = kind, Seconds = 3600, Drills = new() { d } });
        }
        StartSession(new Session { Id = $"{lastSess.Id}_again{++againN}", Minutes = lastSess.Minutes, Difficulty = lastSess.Difficulty,
            Maps = blocks.Select(b => b.Map).Distinct().ToList(), Blocks = blocks });
    }

    // 07/10, the user: "fais une commande report sur le serveur d'entraînement aussi": a note to Wily's author with the
    // drill and where you stand (coach/reports.jsonl; the app sends it within half a minute)
    void Report(CCSPlayerController? p, string? text)
    {
        text = (text ?? "").Trim().Trim('"').Trim();
        if (text.Length == 0) { Say(p, T("!report and what's wrong, or what you'd want: it goes to Wily's author with this drill and where you stand")); return; }
        var pw = p?.PlayerPawn.Value;
        var o = pw?.AbsOrigin;
        var a = pw?.EyeAngles;
        var rec = new Dictionary<string, object?>
        {
            ["t"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(), ["text"] = text.Length > 2000 ? text[..2000] : text,
            ["session"] = sess?.Id, ["block"] = sess != null && blockIdx >= 0 && blockIdx < sess.Blocks.Count ? sess.Blocks[blockIdx].Kind : null,
            ["drill"] = drill?.Id, ["drill_title"] = drill?.Title ?? cur?.Title, ["map"] = Server.MapName, ["phase"] = phase,
            ["pos"] = o == null ? null : new[] { o.X, o.Y, o.Z }, ["ang"] = a == null ? null : new[] { a.X, a.Y }
        };
        try
        {
            Append("reports.jsonl", JsonSerializer.Serialize(rec));
            Say(p, T("📨 noted: it goes to Wily's author with this drill and where you stand. Thanks!"));
        }
        catch (Exception e) { Log("report: {m}", e.Message); Say(p, F("couldn't keep it, sorry: the app's \"{tag}\" tag works too", "tag", T("alpha · report"))); }
    }

    void Welcome()
    {
        if (sess == null) return;
        var order = string.Join(" → ", sess.Blocks.Select(b => T(KindName[b.Kind])).Distinct());
        Html($"<font color='#e0a030'>{F("TRAINING · {n} MIN", "n", sess.Minutes)}</font><br><font class='fontSize-l'>{string.Join(" · ", sess.Maps.Select(MapName))}</font><br>{order}", 4);
        All($"{F("Training {n} min", "n", sess.Minutes)} · {string.Join(", ", sess.Maps.Select(MapName))} · {order}. "
            + T("!n skips a drill, !pause pauses (!resume), !stop ends, !report and a few words tells Wily's author."));
    }

    // 09/10, his warm-up: "si je mets stop, ça se met en pause ? Il faudrait pouvoir la mettre en pause, et la reprendre":
    // the drill stops, the bots go, the block's clock waits; !resume plays that drill again from its start
    bool paused;
    DateTime pausedAt;

    void Pause(CCSPlayerController? p)
    {
        if (sess == null) { Say(p, T("no session running")); return; }
        if (paused) { Say(p, T("already paused: !resume goes on")); return; }
        paused = true;
        entrySky = false; flyStart = -1;
        pausedAt = Clock;
        sessGen++; generation++;   // the timers on their way (next drill, a bot back, the setup) do nothing
        phase = "paused";
        ClearLine();
        if (cam != null) CamStop();
        bots.Clear(); builtFor = null;
        Server.ExecuteCommand("bot_quota 0");
        Server.ExecuteCommand("bot_kick");
        SetMain(PausedHtml());
        All(T("Paused · the block's clock waits · !resume goes on (that drill again from its start)."));
    }

    string PausedHtml() => $"<font color='#e0a030'>⏸ {T("PAUSED")}</font><br>{F("the block's clock waits · {cmd} goes on", "cmd", "<b>!resume</b>")}";

    void Resume(CCSPlayerController? p)
    {
        if (sess == null) { Say(p, T("no session running")); return; }
        if (!paused) { Say(p, T("not paused")); return; }
        paused = false;
        if (blockEnd != DateTime.MinValue) blockEnd += Clock - pausedAt;
        SetMain("");
        All(T("Go on."));
        // paused before its first block began (22/10 eve: the pause cancelled the block on its way, the resume found none)
        if (blockIdx < 0) { var s0 = sess; AddTimer(1f, () => { if (sess == s0 && blockIdx < 0 && !paused) NextBlock(); }); return; }
        if (drill != null) RunDrill(drill); else NextDrill();
    }

    // after a map change, or when you join the server
    void SessionResume()
    {
        if (sess == null || !Humans().Any()) return;
        if (paused) { SetMain(PausedHtml()); return; }
        // its first block only while it has none yet (10/11, round 27, Vertigo's Crossfire: the game came back on the server 2 s
        // into the welcome, this timer was set a second time and fired after the session's own had begun the block: the next
        // block, the session's end, "0/0 exercices"; a session of several blocks lost its first)
        if (blockIdx < 0) { Welcome(); var s1 = sess; AddTimer(4f, () => { if (sess == s1 && blockIdx < 0 && !paused) NextBlock(); }); return; }
        var b = sess.Blocks[blockIdx];
        if (Server.MapName != b.Map) { ChangeMap(b.Map); return; }
        if (drill != null) RunDrill(drill); else NextDrill();
    }

    void NextBlock()
    {
        if (sess == null) return;
        blockIdx++;
        if (blockIdx >= sess.Blocks.Count) { EndSession(); return; }
        var b = sess.Blocks[blockIdx];
        queue.Clear();
        foreach (var d in b.Drills) queue.AddLast(d);
        blockEnd = DateTime.MinValue;   // the block's clock starts with its first drill (after a map change)
        drill = null;
        if (Server.MapName != b.Map)
        {
            phase = "setup"; cur = null;
            Html($"<font color='#e0a030'>{T("NEXT MAP")}</font><br><font class='fontSize-l'>{MapName(b.Map)}</font>", 4);
            AddTimer(2f, () => ChangeMap(b.Map));
            return;
        }
        NextDrill();
    }

    void NextDrill()
    {
        if (sess == null) return;
        var b = sess.Blocks[blockIdx];
        if (blockEnd == DateTime.MinValue) blockEnd = Clock.AddSeconds(b.Seconds);
        if (queue.Count == 0 || Clock > blockEnd) { NextBlock(); return; }
        drill = queue.First!.Value;
        queue.RemoveFirst();
        tries = 0;
        drillNo++;
        RunDrill(drill);
    }

    void RunDrill(Drill d)
    {
        if (sess == null) return;
        sessGen++;
        var pending = false;
        var s = d.Kind switch { "situation" => d.Scenario != null ? PeekSoon(d.Scenario, out pending) : null, "aim" => d.Mode == "range" ? RangeScenario(d) : d.Mode == "crossfire" ? CrossfireScenario(d) : AimScenario(d),
            "nade" => NadeScenario(d), "momentum" => MomentumScenario(d), _ => null };
        if (pending)
        {
            var gp = sessGen;
            AddTimer(0.2f, () => { if (gp == sessGen && drill == d) RunDrill(d); });
            return;
        }
        if (s == null && d.Kind == "situation" && waitFile++ < 20)   // the app is still building it from the demo
        {
            Html($"<font color='#e0a030'>{T(KindName["situation"])}</font><br>{F("loading {title}…", "title", d.Title)}", 2);
            var g = sessGen;
            AddTimer(2f, () => { if (g == sessGen && drill == d) RunDrill(d); });
            return;
        }
        waitFile = 0;
        if (s == null) { Log("drill {id}: nothing to play", d.Id); NextDrill(); return; }
        if (!string.IsNullOrEmpty(s.Lost))
        {   // 07/10: "la situation est perdue d'avance, autant pas me la faire jouer"
            All($"\x10{T(KindName["situation"])}\x01 {d.Title}: {s.Lost} · {T("skipped")}");
            StFinish("skipped", 0);   // a self-test: its end (no drill played, none left hanging)
            Html($"<font color='#e0a030'>{Shown("skipped")}</font> · {d.Title}<br>{s.Lost}", 3);
            var g2 = sessGen;
            AddTimer(3f, () => { if (g2 == sessGen) NextDrill(); });
            return;
        }
        cur = s;
        // an aim drill's own time on the game's clock (09/10, his defense: "le temps d'en haut finit avant le temps de la
        // situation", 10 s before): the round's clock ends with the drill; a stuff drill keeps its throw's real moment
        if (d.Kind == "aim" && d.Seconds > 0) cur.Clock = d.Seconds;
        else if (d.Kind == "momentum" && d.Seconds > 0) cur.Clock = d.Seconds * 1.5f;   // its last rep starts before 1.5 times its time
        else if (d.Kind != "situation" && d.Clock > 0) cur.Clock = d.Clock + (d.Rush ? rushDelay : 0);   // a rush's wait: its arrival stays on the real clock
        rushIn = -1;
        rushOut.Clear();
        mode = "actor";
        aimOrder.Clear(); reacts.Clear(); aimHs = 0; aimNext = 0; attempts = 0; nadeWait = false; frags = deaths = plants = 0;
        wave = 0; waveFirstDead = -1; waveDue = false; beaconed.Clear();
        waveKills = waveOnSite = wavesFaced = wavesHeld = 0; waveLost = waveFaced = waveGone = false; waveStartAt = waveT0Of = Server.TickCount;
        nadePops.Clear();
        nadeLast = ""; utilBlind = utilDmg = utilBlindKills = 0; defHeld = defHeldAt = 0;
        if (d.Kind == "nade") ClearNades();
        cameAt.Clear(); strafe.Clear(); lastKill = 0;
        // the targets that must stay still idle: a prefire's, a wallbang's, the aim map's flicks and strafers (06/10)
        // a boost's by bot_stop (28/10, server 2's bots: a bot_zombie runs no command, no physics at all: the teammate below
        // never settled on the floor nor crouched, its box 9 u up into your feet, you never on the ground for the game, the
        // in-air spread at every shot; stopped, it stands and crouches for real and one put on its head lands on it, on the
        // ground: 63 ticks of 63)
        Zombie((d.Kind == "aim" && (d.Mode == "prefire" || d.Id.StartsWith("wallbang") || (d.Mode == "range" && d.Variant != "duel")))
               || (d.Kind == "momentum" && selftest && stGuided) || d.Mode == "entry");   // a guided Momentum: the guide moves only as MoGuideDrive says; an entry's CTs, unarmed
        DontShoot(d.Rush || (d.Mode == "crossfire" && d.Variant == "spray") || d.Mode is "entry" or "hold");   // a defense's Ts run unarmed   // Crossfire's spray: two targets, nothing else   // a rush's runners run their way like a situation's players (driven, not idle), and never fire
        // Aim Botz's config stops them (07/10): off; a boost's on; css_scripted's defenses on (Combat.cs: the game's AI
        // stopped, the plugin drives them, their fights too). A situation's keep it: your teammates play on their AI, its
        // enemies fighting you are driven through their own command (their AI's moves and buttons taken out)
        BotStop(d.Id.StartsWith("boost") || (scripted && d.Mode == "defend"));
        Ammo(d.Kind == "aim");   // 07/10: "chargeur infini dans le sens où ... il faut que je recharge": the reserve never ends
        Intro(d);
        Setup();
    }

    string Left() { var l = blockEnd - Clock; return l.TotalSeconds > 0 ? $"{(int)l.TotalMinutes}:{l.Seconds:D2}" : T("last"); }

    void Intro(Drill d)
    {
        // a silent jump: walking, first and big (20/10, his video: "l'information à mettre en avant c'est en marchant")
        var how = d.Kind == "situation" && cur != null ? SituationText() : d.Mode == "exec" ? ExecIntro(d) : d.Mode is "entry" or "hold" ? d.Tip
            : d.Mode == "momentum" && d.How == "walk" ? $"<font color='#ffd34d' class='fontSize-l'>{T("WALK IT: Shift held")}</font><br>{d.Tip}"
            : d.Kind != "nade" ? d.Tip : d.Level switch
        {
            // the aim always shown (19/10, his video: "tu ne peux pas me dire de trouver la visée de lancer, ce n'est pas
            // jouable"): a level up turns you away from it, never hides it
            0 or 1 when d.Rush => $"{HowBig(d)}<br>{F("a real rush gets to the blue ring at {t}: your grenade must be up before · it comes at GO", "t", RoundClock(d.RushAt))}",
            _ when d.Rush => $"{HowBig(d)}<br>{T("they rush: your grenade up on its spot in time · it comes at GO")}",
            _ when d.Steps => $"{HowBig(d)}<br><font class='fontSize-s'>{T("step by step, each one checked")}</font>",
            _ => $"{HowBig(d)}<br>{T("crosshair in the yellow circle · it must land in the blue ring · stand in the green ring")}{StepHint(d)}",
        };        var again = tries > 0 ? $" · {T("AGAIN")}" : "";
        // the instruction first (23/10, the user: "la première ligne du bandeau doit toujours être la consigne"), then the
        // drill, then the rest of its words (the instruction said once)
        var order = Order(d);
        var rest = d.Kind == "situation" ? string.Join("<br>", how.Split("<br>").Skip(1)) : how.Replace(order, "");
        if (rest.StartsWith("<br>")) rest = rest[4..];
        introHtml = $"{order}<br><font color='{KindColor[d.Kind]}'>{T(KindName[d.Kind])}{again}</font> · {d.Title} · {Left()} · ⭐ {points}{(rest != "" ? $"<br>{rest}" : "")}";
        hudFlash = "";
        SetMain(introHtml);
        var plain = System.Text.RegularExpressions.Regex.Replace(how.Replace("<br>", " · "), "<[^>]+>", "");
        All($"\x10{T(KindName[d.Kind])}{again}\x01 {d.Title} — {plain}");
    }

    Scenario AimScenario(Drill d)
    {
        var s = new Scenario { Id = d.Id, Map = d.Map, Kind = "aim", Title = d.Title, Team = d.Team };
        var me = d.Me ?? new Spot();
        s.Players.Add(new Track { Sid = "me", Name = "you", Team = d.Team, Me = true, Hp = 100, Armor = d.Armor, Helmet = d.Helmet, Weapons = d.Weapons,
            Active = d.Weapons.LastOrDefault(), Path = new[] { me.Pos[0], me.Pos[1], me.Pos[2], me.Ang[1], me.Ang[0] } });
        if (d.Mode == "defend")   // a few attackers at a time on real hits' ways, with their grenades, then the game's AI
        {
            for (int k = 0; k < Math.Min(d.Alive, Math.Max(d.Bots.Count, d.Tracks.Count)); k++)
            {
                var tr = PickTrack(d, 0);
                var b = d.Bots.Count > 0 ? d.Bots[Rng.Next(d.Bots.Count)] : new Spot();
                var path = tr?.Path ?? new[] { b.Pos[0], b.Pos[1], b.Pos[2], b.Ang[1], b.Ang[0] };
                var nades = tr?.Nades ?? new();
                var lead = WayLead(path, d.Posts.Count > 0 ? d.Posts[0].Pos : d.Me?.Pos, s.Rate / (float)s.Step);
                s.Players.Add(new Track { Sid = $"att{k}", Name = tr?.Zone ?? b.Zone ?? $"Attacker {k + 1}", Team = 5 - d.Team, Hp = 100, Armor = d.Armor, Helmet = d.Helmet,
                    Weapons = d.BotWeapons, Active = d.BotWeapons.FirstOrDefault(w => w.Contains("ak47") || w.Contains("m4")) ?? d.BotWeapons.LastOrDefault(),
                    Path = path, TrackNades = nades, Start = -lead, SpawnF = lead, NadeNext = FirstNade(nades, lead) });
            }
            return s;
        }
        for (int k = 0; k < d.Bots.Count; k++)
        {
            var b = d.Bots[k];
            s.Players.Add(new Track { Sid = $"target{k}", Name = b.Zone ?? $"Target {k + 1}", Team = 5 - d.Team, Hp = 100, Armor = 100, Helmet = true,
                Weapons = d.BotWeapons, Active = d.BotWeapons.LastOrDefault(), Path = new[] { b.Pos[0], b.Pos[1], b.Pos[2], b.Ang[1], b.Ang[0] }, Hold = true,
                Still = d.Mode == "prefire" || d.Id.StartsWith("wallbang") || d.Id.StartsWith("boost"), Duck = b.Duck });
        }
        if (d.Mate is { } m)   // a boost: the teammate below, still, crouched when the boost was on a crouched one
            s.Players.Add(new Track { Sid = "mate", Name = m.Zone ?? "your boost", Team = d.Team, Hp = 100, Armor = 100, Helmet = true,
                Weapons = d.Weapons, Active = d.Weapons.LastOrDefault(), Path = new[] { m.Pos[0], m.Pos[1], m.Pos[2], m.Ang[1], m.Ang[0] }, Hold = true, Still = true, Duck = m.Duck });
        return s;
    }

    // a defense's attacker: a real hit that walks into the sight of the post you hold (06/10: "les bots n'attaquent pas
    // ma zone"), any of them once you play free
    static EntryTrack? PickTrack(Drill d, int post)
    {
        if (d.Tracks.Count == 0) return null;
        var mine = d.Tracks.Where(t => post < d.Posts.Count ? t.Post == post : t.Post < 0).ToList();
        if (mine.Count == 0) mine = d.Tracks;
        return mine[Rng.Next(mine.Count)];
    }

    // the aim map (06/10, the user: "fais le travail d'aim sur une map d'aim, ensuite lance les maps que j'ai choisies"):
    // you at the middle of your side's spawns, the targets on the other side's, turned to you
    Scenario RangeScenario(Drill d)
    {
        var s = new Scenario { Id = d.Id, Map = d.Map, Kind = "aim", Title = d.Title, Team = d.Team, Clock = d.Clock };
        List<(Vector3 p, float yaw)> Of(string cls)
        {   // the spawns the game uses (some maps hold a disabled second set)
            var all = Utilities.FindAllEntitiesByDesignerName<SpawnPoint>(cls).Where(e => e.AbsOrigin != null).ToList();
            var on = all.Where(e => e.Enabled).ToList();
            return (on.Count > 0 ? on : all).Select(e => (new Vector3(e.AbsOrigin!.X, e.AbsOrigin.Y, e.AbsOrigin.Z), e.AbsRotation?.Y ?? 0f)).ToList();
        }
        var mineY = Of(d.Team == 2 ? "info_player_terrorist" : "info_player_counterterrorist");
        var theirsY = Of(d.Team == 2 ? "info_player_counterterrorist" : "info_player_terrorist");
        var mine = mineY.Select(x => x.p).ToList();
        rangeTheirs = theirsY.Select(x => x.p).ToList();
        if (d.Map != rangeMap) { rangeBlind.Clear(); rangeMap = d.Map; }
        rangeSeenAt.Clear(); rangeSpots = false;
        var mid = mine.Count > 0 ? new Vector3(mine.Average(p => p.X), mine.Average(p => p.Y), mine.Average(p => p.Z)) : Vector3.Zero;
        var me = mine.Count > 0 ? mine.OrderBy(p => Vector3.Distance(p, mid)).First() : Vector3.Zero;
        var far = rangeTheirs.Count > 0 ? new Vector3(rangeTheirs.Average(p => p.X), rangeTheirs.Average(p => p.Y), rangeTheirs.Average(p => p.Z)) : me + new Vector3(1000, 0, 0);
        var flat = new Vector2(far.X - me.X, far.Y - me.Y).Length();
        var face = flat > 200 ? YawTo(me, far) : mineY.FirstOrDefault(x => Vector3.Distance(x.p, me) < 1f).yaw;   // around you: the map's own way
        if (flat <= 200) far = me + new Vector3(1000 * MathF.Cos(face * MathF.PI / 180), 1000 * MathF.Sin(face * MathF.PI / 180), 0);
        float Off(Vector3 p) => MathF.Abs(((YawTo(me, p) - face) % 360 + 540) % 360 - 180);
        foreach (var cone in d.Variant == "duel" ? new[] { 60f, 90f, 120f, 180f } : new[] { 80f, 100f, 130f, 180f })
        {   // a duel's shooters in front only; enough spots to change places
            var front = rangeTheirs.Where(p => Off(p) <= cone).ToList();
            if (front.Count >= 8 || cone >= 180f) { rangeTheirs = front; break; }
        }
        s.Players.Add(new Track { Sid = "me", Name = "you", Team = d.Team, Me = true, Hp = 100, Armor = 100, Helmet = true, Weapons = d.Weapons,
            Active = d.Weapons.LastOrDefault(), Path = new[] { me.X, me.Y, me.Z, YawTo(me, far), 0f } });
        var order = rangeTheirs.Where(p => !Blind(p)).OrderBy(_ => Rng.Next()).ToList();
        if (order.Count == 0) order = rangeTheirs.OrderBy(_ => Rng.Next()).ToList();
        for (int k = 0; k < Math.Max(1, d.Count); k++)
        {
            var p = order.Count > 0 ? order[k % order.Count] : far;
            s.Players.Add(new Track { Sid = $"target{k}", Name = $"Target {k + 1}", Team = 5 - d.Team, Hp = 100, Armor = 100, Helmet = true,
                Weapons = d.BotWeapons, Active = d.BotWeapons.LastOrDefault(), Path = new[] { p.X, p.Y, p.Z, YawTo(p, me), 0f },
                Hold = d.Variant != "strafe", Still = d.Variant == "flick", Strafe = d.Variant == "strafe" });
        }
        return s;
    }

    static float YawTo(Vector3 a, Vector3 b) => MathF.Atan2(b.Y - a.Y, b.X - a.X) * 180 / MathF.PI;

    // a prefire's bot: its spot in the drill (its track is "target<k>")
    Spot? BotSpot(Track t) => drill != null && int.TryParse(t.Sid.Replace("target", ""), out var k) && k >= 0 && k < drill.Bots.Count ? drill.Bots[k] : null;

    // a target of the aim map down: another one on a free spot of their side, turned to you
    void RangeAgain(int g, int slot)
    {
        if (g != generation || phase != "live" || cur == null || drill == null || !bots.TryGetValue(slot, out var t)) return;
        var c = Utilities.GetPlayerFromSlot(slot);
        if (c == null || !c.IsValid) return;
        var me = Humans().Select(h => h.PlayerPawn.Value?.AbsOrigin).FirstOrDefault(o => o != null) is { } mo ? new Vector3(mo.X, mo.Y, mo.Z) : Pos(cur.Players.First(p => p.Me), 0);
        var taken = bots.Where(b => b.Key != slot && !gone.Contains(b.Value.Sid)).Select(b => Pos(b.Value, 0)).ToList();
        var free_ = rangeTheirs.Where(p => !Blind(p) && taken.All(q => Vector3.Distance(p, q) > 120) && Vector3.Distance(p, Pos(t, 0)) > 120).ToList();
        if (free_.Count == 0) free_ = rangeTheirs.Where(p => !Blind(p)).ToList();
        if (free_.Count == 0) free_ = rangeTheirs;
        var p = free_.Count > 0 ? free_[Rng.Next(free_.Count)] : Pos(t, 0);
        t.Path = new[] { p.X, p.Y, p.Z, YawTo(p, me), 0f };
        c.Respawn();
        Loadout(c, t);
        if (c.PlayerPawn.Value is { } pw) { pw.Teleport(p, new Vector3(0, YawTo(p, me), 0), Vector3.Zero); Freeze(pw, !t.Strafe && t.Hold); }
        gone.Remove(t.Sid);
        contact.Remove(slot);
        strafe.Remove(slot);
        cameAt[slot] = Server.TickCount;
    }

    // the aim map's strafers: left and right across your line, a stop now and then (counter-strafe practice), 200 u
    // around their spot at most, turned to you
    // a target nobody can see from your spot (cover between): moved after 3 s, its spot dropped for the map. Only once a
    // target has been seen this drill (the game's spotting works for these bots: unseen then means hidden)
    void RangeBlindTick()
    {
        var me = Humans().Select(h => h.PlayerPawn.Value).FirstOrDefault(p => p != null && p.IsValid && p.LifeState == (byte)LifeState_t.LIFE_ALIVE);
        if (me == null) return;
        var m = me.EntitySpottedState.SpottedByMask;
        var now = Server.TickCount;
        foreach (var (slot, t) in bots.ToList())
        {
            if (gone.Contains(t.Sid)) continue;
            if ((m[slot / 32] & (1u << (slot % 32))) != 0) { rangeSeenAt[slot] = now; rangeSpots = true; continue; }
            if (!rangeSpots) continue;
            var since = Math.Max(cameAt.GetValueOrDefault(slot, t0), rangeSeenAt.GetValueOrDefault(slot, 0));
            if (now - since < 3 * 64) continue;
            var here = Pos(t, 0);
            if (!Blind(here) && rangeTheirs.Count(q => !Blind(q)) > 4)
            {
                rangeBlind.Add(here);
                Log("range: their spot {s} unseen from yours, dropped ({n} left)", $"{here.X:F0} {here.Y:F0}", rangeTheirs.Count(q => !Blind(q)));
            }
            rangeSeenAt[slot] = now;
            RangeAgain(generation, slot);
        }
    }

    void StrafeTick()
    {
        var mo = Humans().Select(h => h.PlayerPawn.Value?.AbsOrigin).FirstOrDefault(o => o != null);
        if (mo == null) return;
        var me = new Vector3(mo.X, mo.Y, mo.Z);
        foreach (var (slot, t) in bots)
        {
            if (!t.Strafe || gone.Contains(t.Sid)) continue;
            var pw = Utilities.GetPlayerFromSlot(slot)?.PlayerPawn.Value;
            if (pw?.AbsOrigin is not { } o || pw.LifeState != (byte)LifeState_t.LIFE_ALIVE) continue;
            var here = new Vector3(o.X, o.Y, o.Z);
            var to = new Vector3(me.X - here.X, me.Y - here.Y, 0);
            if (to.Length() < 1) continue;
            var spot = Pos(t, 0);
            if (here.Z < spot.Z - 40)
            {   // off its ledge (Aim Botz's walkways are narrow, 08/10): back on its spot, going the other way
                pw.Teleport(spot, new Vector3(0, MathF.Atan2(to.Y, to.X) * 180 / MathF.PI, 0), Vector3.Zero);
                strafe[slot] = (strafe.TryGetValue(slot, out var was) && was.sign != 0 ? -was.sign : 1, Server.TickCount + Rng.Next(20, 50));
                continue;
            }
            var side = Vector3.Normalize(new Vector3(-to.Y, to.X, 0));
            var off = Vector3.Dot(here - Pos(t, 0), side);
            (int sign, int until) st = strafe.TryGetValue(slot, out var s0) ? s0 : (Rng.Next(2) * 2 - 1, Server.TickCount + Rng.Next(20, 50));
            if (Math.Abs(off) > 200 && Math.Sign(off) == st.sign) st = (-st.sign, Server.TickCount + Rng.Next(20, 50));
            else if (Server.TickCount >= st.until)
                st = st.sign != 0 && Rng.Next(4) == 0 ? (0, Server.TickCount + Rng.Next(12, 30)) : (st.sign == 0 ? Rng.Next(2) * 2 - 1 : -st.sign, Server.TickCount + Rng.Next(20, 56));
            strafe[slot] = st;
            var v = side * (st.sign * 230f);
            var yaw = MathF.Atan2(to.Y, to.X) * 180 / MathF.PI;
            pw.Teleport(null, new Vector3(0, yaw, 0), new Vector3(v.X, v.Y, pw.AbsVelocity?.Z ?? 0f));
            HoldAim(pw, new Vector3(0, yaw, 0), false);
        }
    }

    // a situation: what to do, your route in the match, who got you and from where
    // the essentials only (06/10, the user: "moins d'infos écrites, que l'essentiel, pour nous pousser à les lire"): the
    // goal, how many on each side and where your dead allies fell (red crosses on the ground), the bomb, who got you
    string SituationText()
    {
        var mine = cur?.Players.FirstOrDefault(p => p.Me);
        var lines = new List<string> { string.IsNullOrEmpty(cur?.Goal) ? T("survive") : cur!.Goal };
        if (mine != null && cur != null)
        {
            var al = cur.Players.Count(p => p.Team == mine.Team);
            var en = cur.Players.Count(p => p.Team != mine.Team);
            var dead = cur.Dead.Where(x => x.Team == mine.Team && x.At != "").Select(x => x.At).Distinct().ToList();
            lines.Add($"{al}v{en}{(dead.Count > 0 ? $" · {F("allies dead: {where} (red crosses)", "where", string.Join(", ", dead))}" : "")}");
        }
        if (!string.IsNullOrEmpty(cur?.Plant)) lines.Add($"💣 {cur!.Plant}");   // planted or not: what you have to do (04/10)
        if (!string.IsNullOrEmpty(cur?.Danger)) lines.Add($"⚠ {cur!.Danger}");
        if (!string.IsNullOrEmpty(cur?.ZoneName) || cur?.ZonePoly.Count >= 3)
            lines.Add("🔵 " + (string.IsNullOrEmpty(cur!.ZoneName) ? T("it happens in the blue zone: play it your way") : F("it happens in {zone} (blue): play it your way", "zone", cur.ZoneName)));
        return string.Join("<br>", lines);
    }

    static string RoundLeft(float s) { var l = (int)Math.Max(0, s); return $"{l / 60}:{l % 60:D2}"; }

    // a situation's two sides as they are now: you and your teammates up (their health), the enemies up
    string TeamsLine()
    {
        if (cur == null) return "";
        var me = Humans().FirstOrDefault();
        var mates = bots.Where(b => b.Value.Team == cur.Team && !b.Value.Me).Select(b => Utilities.GetPlayerFromSlot(b.Key))
            .Where(c => c is { IsValid: true, PawnIsAlive: true }).Select(c => c!.PlayerPawn.Value?.Health ?? 0).ToList();
        var foes = bots.Count(b => b.Value.Team != cur.Team && Utilities.GetPlayerFromSlot(b.Key) is { IsValid: true, PawnIsAlive: true });
        var mine = (me is { PawnIsAlive: true } ? 1 : 0) + mates.Count;
        return $"👥 {mine}v{foes} · " + (mates.Count > 0 ? F("teammates: {hp}", "hp", string.Join(" · ", mates.Select(x => $"{x} HP"))) : T("no teammate left"));
    }

    // a situation's own route (23/10, for the real-client test: "rejouer ton trajet de la démo comme chemin à suivre, pour
    // que mon pilote puisse juger"): your track in the match, 4 points a second, written once it is set up
    // (coach/route_live.json)
    void RouteLive()
    {
        var me = cur?.Players.FirstOrDefault(p => p.Me);
        if (cur == null || me == null || me.Frames < 2) return;
        var pts = new List<float[]>();
        var every = Math.Max(1, (int)(cur.Rate / (float)cur.Step / 4f));
        for (int i = 0; i < me.Frames; i += every)
            pts.Add(new[] { R1(me.Path[i * 5]), R1(me.Path[i * 5 + 1]), R1(me.Path[i * 5 + 2]), MathF.Round(i * cur.Step / (float)cur.Rate, 2) });
        var json = JsonSerializer.Serialize(new Dictionary<string, object?> { ["drill"] = drill?.Id, ["scenario"] = cur.Id, ["death"] = me.Death,
            ["step"] = cur.Step, ["rate"] = cur.Rate, ["route"] = pts });
        Io(() => { try { File.WriteAllText(System.IO.Path.Combine(Dir, "route_live.json"), json); } catch (Exception) { } });
    }

    Scenario NadeScenario(Drill d)
    {
        if (d.Mode == "exec") return ExecScenario(d);
        if (d.Mode is "entry" or "hold") return EntryScenario(d);
        var s = new Scenario { Id = d.Id, Map = d.Map, Kind = "nade", Title = d.Title, Team = d.Team };
        var me = d.Me ?? new Spot();
        float pitch = me.Ang[0], yaw = me.Ang[1];
        if (d.Level >= 1) { yaw += (float)(Rng.NextDouble() * 120 - 60); pitch = 0; }   // the spot, not the aim
        var (st0, sa0) = d.Steps && d.Me != null ? StepsStart(d) : (new Vector3(me.Pos[0], me.Pos[1], me.Pos[2]), new Vector3(pitch, yaw, 0f));
        if (d.Steps) { pitch = 0f; yaw = sa0.Y; }   // step by step: near its spot, turned to it (Steps.cs)
        // a timing smoke: the grenade comes at GO (none thrown during the countdown, the runners still)
        s.Players.Add(new Track { Sid = "me", Name = "you", Team = d.Team, Me = true, Hp = 100, Weapons = d.Rush ? new() { "weapon_knife" } : new() { "weapon_knife", d.Item },
            Active = d.Rush ? "weapon_knife" : d.Item, Path = new[] { st0.X, st0.Y, st0.Z, yaw, pitch } });
        if (d.Rush)
        {   // the real rush's runners, on their way at their pace (07/10)
            s.Step = Math.Max(1, d.Step);
            rushDelay = Math.Max(0, 2 - d.Level);
            var w = d.BotWeapons.Count > 0 ? d.BotWeapons : new() { "weapon_knife", d.Team == 3 ? "weapon_ak47" : "weapon_m4a1" };
            for (int k = 0; k < d.Tracks.Count; k++)
                s.Players.Add(new Track { Sid = $"rush{k}", Name = d.Tracks[k].Zone, Team = 5 - d.Team, Hp = 100, Armor = 100, Helmet = true,
                    // knife out (17/10, the self-test: Fachwerk's rusher put back 74 u ahead 1.75 s in, every run: the real one ran
                    // 243 u/s, a rifle carries 215): a runner never stops to fight, its pace is the drill
                    Weapons = w, Active = w.Contains("weapon_knife") ? "weapon_knife" : w.Last(), Path = d.Tracks[k].Path, Runner = true, Start = rushDelay * 64f / s.Step });
        }
        if (selftest && stGuided && d.Me != null)   // a guided self-test's thrower: on your spot, on the cross's aim (SelfTest.cs)
            s.Players.Add(new Track { Sid = "guide", Name = "guide", Team = d.Team, Hp = 100, Weapons = new() { "weapon_knife", d.Item }, Active = d.Item,
                Path = d.Steps ? new[] { st0.X, st0.Y, st0.Z, yaw, 0f } : new[] { d.Me.Pos[0], d.Me.Pos[1], d.Me.Pos[2], d.Me.Ang[1], d.Me.Ang[0] },
                Hold = true, Still = true, Duck = d.How.Contains("crouch") });
        return s;
    }

    // Place() is done: the aim targets but the first wait (dead) for their turn
    void SessionPlaced()
    {
        StPlaced();
        if (cur is { Kind: "death" or "clutch" } && cur.Line.Count > 1) DrawLine(cur.Line);   // your way in the match, up to the zone
        if (cur is { Kind: "death" or "clutch" }) DrawZone(cur);
        if (cur is { Kind: "death" or "clutch" })   // the allies dead before it: where they fell
            foreach (var x in cur.Dead.Where(x => x.Team == cur.Team && x.Pos.Length >= 3)) DrawX(new Vector3(x.Pos[0], x.Pos[1], x.Pos[2]));
        if (sess == null || cur == null) return;
        if (drill?.Mode == "prefire" && drill.Line.Count > 1) DrawLine(drill.Line);
        if (drill?.Mode == "prefire") PreReactReset();
        if (drill?.Id.StartsWith("wallbang") == true) { var gw = generation; AddTimer(0.4f, () => { if (gw == generation) WallMarks(); }); }   // the targets on their spots first
        if (cur is { Kind: "death" or "clutch" }) RouteLive();
        if (cur.Kind == "momentum") MoPlaced();
        else if (cur.Kind == "aim" && drill?.Mode == "crossfire") CfPlaced();
        else if (cur.Kind == "aim" && drill?.Mode == "range")
        {
            aimOrder.Clear();
            aimOrder.AddRange(bots.Keys);
            foreach (var sl in bots.Keys) cameAt[sl] = Server.TickCount + 3 * 64;
        }
        else if (cur.Kind == "aim" && drill?.Mode is "prefire" or "defend")
        {
            aimOrder.Clear();
            aimOrder.AddRange(bots.Keys);
            peekAt.Clear();
            lineAt = 0; lastPeek = Server.TickCount;
            if (drill.Mode == "prefire")   // the ones that peek later wait, hidden, for their turn (07/10: one after the other, in the
                foreach (var (slot, t) in bots)   // order your way shows them, not three at once in front of you)
                {
                    var b = BotSpot(t);
                    var ordered = drill.Bots.Any(x => x.Seq >= 0);
                    var at = b?.At ?? 0f;
                    if (ordered ? (b == null || b.Seq > 0 || b.Li > 1 || at > 0.3f) : at > 0.3f)
                    { peekAt[slot] = at; Utilities.GetPlayerFromSlot(slot)?.PlayerPawn.Value?.CommitSuicide(false, true); }
                }
        }
        else if (cur.Kind == "aim")
        {
            aimOrder.Clear();
            aimOrder.AddRange(bots.Where(b => b.Value.Team != cur.Team).Select(b => b.Key).OrderBy(_ => Rng.Next()));
            for (int k = 1; k < aimOrder.Count; k++) Utilities.GetPlayerFromSlot(aimOrder[k])?.PlayerPawn.Value?.CommitSuicide(false, true);
            aimNext = 1;
            // you start turned to the first target
            if (aimOrder.Count > 0 && bots.TryGetValue(aimOrder[0], out var first))
            {
                var me = cur.Players.First(p => p.Me);
                var d = Pos(first, 0) - Pos(me, 0);
                var yaw = MathF.Atan2(d.Y, d.X) * 180 / MathF.PI;
                foreach (var h in Humans()) h.PlayerPawn.Value?.Teleport(Pos(me, 0), new Vector3(0, yaw, 0), Vector3.Zero);
            }
        }
        if (cur.Kind == "nade") { nadeWait = true; attemptEnd = Clock.AddSeconds(30); }   // a throw during the countdown counts
        Prac(cur.Kind == "nade");
        nadeStage = cur.Kind == "nade" ? "throw" : "";
        nadePop = null; nadeBounces = 0; stVictims = false;
        StepsReset();
        if (cur.Kind == "nade" && drill?.Target is { Length: >= 2 } tg && drill.Me != null)
        {
            ClearLine();
            var r = drill.Type switch { "flash" or "he" or "molotov" => 120f, _ => 70f };   // the PERFECT zone
            // a flash pops in the air: its ring there (none standing in front of your landmark); else the beam from your feet's height
            if (drill.Type == "flash" && tg.Length >= 3) DrawPop(tg, r);
            else DrawMark(tg[0], tg[1], drill.Me.Pos[2], tg.Length >= 3 && drill.Type != "flash" ? tg[2] : null, r);
            DrawStand(drill.Me);
            DrawStep(drill);
            DrawCross(drill);   // 06/10: "il manque de repères, je n'ai aucun repère visuel"; at every level (19/10)
            // the doors in its way open, as for the player who threw it (04/10: the HE through Squeaky hit the closed door);
            // what breaks in its way broken, as it usually is in a match (09/10, his video: "le volet est souvent cassé aussi,
            // c'est un peu comme l'histoire des vents sur Nuke"). Along its flight as its words throw it (17/10: the straight
            // line from your eyes missed what stands under the arc)
            var arc = NadeArc(drill);
            OpenDoors(arc, 128f);
            Break(arc, 72f);
        }
        if (ExecOn) ExecPlaced();
        if (EntryOn) { nadeWait = false; nadeStage = ""; Prac(false); EntryPlaced(); }   // its entry: no throw of yours (Entry.cs)
    }

    // the countdown of a drill keeps its card on screen; false: not in a session
    bool SessionCount(int n)
    {
        if (sess == null || drill == null) return false;
        SetMain($"{introHtml}<br><font class='fontSize-xl'>{n}</font>");
        return true;
    }

    void SessionGo()
    {
        if (sess == null || cur == null) return;
        aimSpawn = Server.TickCount;
        lastHud = Server.TickCount;
        if (cur.Kind == "aim" && string.IsNullOrEmpty(drill?.Mode)) AimCard();
        if (drill?.Mode == "prefire") { Html($"<font color='#ff8a3d'>{T("GO")}</font> · {F("clear {n}", "n", aimOrder.Count)} · {drill.Seconds} s", 2); preKillAt = Server.TickCount; }
        if (drill?.Mode == "range") { Html($"<font color='#ff8a3d'>{T("GO")}</font> · {Tn(drill.Goal, "{n} kill", "{n} kills")} · {drill.Seconds} s", 2); lastKill = Server.TickCount; foreach (var sl in bots.Keys) cameAt[sl] = Server.TickCount; }
        if (drill?.Mode == "crossfire") CfGo();
        if (drill?.Mode == "momentum") MoGo();
        if (EntryOn) EntryGo();
        if (drill?.Mode == "defend")
        {
            postIdx = -1; postWaveN = 0; postAt = Server.TickCount; defendDone = false; radarUntil.Clear();
            foreach (var sl in Attackers()) radarUntil[sl] = Server.TickCount + 128;   // the first ones on your radar 2 s
            Html($"<font color='#ff8a3d'>{T("HOLD")}</font> · 🌊 {DefendWaves} · {T("they are coming")}", 2);
            var g0 = generation;
            AddTimer(12f, () => WaveStale(g0, 0));   // the first ones too, as each wave (StartWave)
        }
        if (drill is { Rush: true })
        {
            foreach (var h in Humans())
            {
                if (!h.PawnIsAlive) continue;
                h.GiveNamedItem(drill.Item);
                h.ExecuteClientCommandFromServer($"use {drill.Item}");
            }
            Html($"<font color='#ff5a5a'>{T("THEY RUSH")}</font>{(drill.Level < 2 ? $" · {F("there at {t}", "t", RoundClock(drill.RushAt))}" : "")}", 2);
        }
    }

    static string RoundClock(float t) { var l = (int)Math.Max(0, 115 - t); return $"{l / 60}:{l % 60:D2}"; }

    // a timing smoke: the first runner on its spot before it is up: late (07/10)
    void RushCheck()
    {
        if (drill is not { Rush: true } || cur == null || rushIn >= 0 || drill.Target is not { Length: >= 2 } tg) return;
        foreach (var (slot, t) in bots)
        {
            if (t.Team == cur.Team) continue;
            var o = Utilities.GetPlayerFromSlot(slot)?.PlayerPawn.Value?.AbsOrigin;
            if (o == null) continue;
            var dz = tg.Length >= 3 ? Math.Abs(o.Z - tg[2]) : 0f;
            if (MathF.Sqrt((o.X - tg[0]) * (o.X - tg[0]) + (o.Y - tg[1]) * (o.Y - tg[1])) > 240f || dz > 140f) { rushOut.Add(slot); continue; }   // train.py's RUSH_R, RUSH_DZ
            // 17/10, Vertigo's smoke to Pit: a runner starting 223 u from it (in the pit below) was there at 0 s, the
            // drill lost before the throw. One that never was away has not come: it counts once it left and came back
            if (!rushOut.Contains(slot)) continue;
            rushIn = Server.TickCount;
            Log("rush: {n} on the spot at {s:F1} s", t.Name, (rushIn - t0) / 64.0);
            if (!nadeWait) return;   // up already (scored at its pop)
            nadeWait = false;
            DrillDone(false, "late", 0, F("{who} got there before your grenade", "who", t.Name));
            return;
        }
    }

    // a defense in turns: each spot to hold for its share of the time (marked on the ground, you are put on it), then free
    // (04/10: "a specific work on positions: backsite is my job, then that one, then free")
    // atWave: between two waves (StartWave), the post's waves over; each tick only its time cap moves you on mid-wave
    void DefendPost(float el, bool atWave = false)
    {
        if (drill == null || cur == null || drill.Posts.Count == 0) return;
        var n = drill.Posts.Count + (drill.Free ? 1 : 0);
        var per = Math.Max(1, (int)Math.Round(DefendWaves / (double)n));
        var now0 = Server.TickCount;
        int ph;
        if (postIdx < 0) ph = 0;
        // its time cap a guard only, 5x its share (30/10, his review: at 1.5x Mirage's A and Dust2's A moved on mid-wave, the
        // waves 25 to 50 s long, "3 vagues tenues sur 4"; 04/11, his order: "assure-toi de faire toutes les vagues, rajoute du
        // temps pour la défense", rounds 20-22 drills of 4 or 5 waves faced at 3x)
        else if (atWave && postWaveN >= per || (now0 - postAt) / 64f > 5f * drill.Seconds / n) ph = postIdx + 1;
        else return;
        if (ph >= n) { defendDone = true; return; }   // its waves over: the drill's end (the tick, below)
        postWaveN = 0; postAt = now0;
        var moved = postIdx >= 0;   // not the drill's start
        postIdx = ph;
        ClearLine();
        if (moved && !atWave) NewWave();   // the next post's attackers, all at once (the last ones walked to the post you left)
        if (ph >= drill.Posts.Count)
        {   // 09/10, his defense video: "téléporte-moi sur le bombsite quand je suis en free pour vraiment montrer un
            // changement": back on the site (the drill's start), turned the way they come, refilled like at a post
            var me0 = cur.Players.FirstOrDefault(t => t.Me);
            if (drill.Me is { } site)
                foreach (var h in Humans())
                    if (h.PawnIsAlive && h.PlayerPawn.Value is { } pw0)
                    {
                        pw0.Teleport(new Vector3(site.Pos[0], site.Pos[1], site.Pos[2]), new Vector3(0, site.Ang[1], 0), Vector3.Zero);
                        if (me0 != null) Loadout(h, me0, 100);
                    }
            Html($"<font color='#4fc3a1'>{T("FREE")}</font> · {T("on the site: play it where you want")}", 3);
            return;
        }
        var p = drill.Posts[ph];
        var at = new Vector3(p.Pos[0], p.Pos[1], p.Pos[2]);
        var green = System.Drawing.Color.FromArgb(255, 79, 195, 161);
        // its corners on the post's floor, a thin line: one corner taken on a box top drew a line through the air at eye
        // height (09/10, Mirage's Van: "est-ce que les lignes ne gênent pas la vue ? typiquement là, ça gêne")
        float Floor(float z) => Math.Clamp(z, p.Pos[2] - 48f, p.Pos[2] + 8f) + 4f;
        if (p.Poly.Count >= 3)   // the place's own shape (06/10: "si c'est Garage, prends tout le Garage")
            for (int i = 0; i < p.Poly.Count; i++)
            {
                var a = p.Poly[i]; var b = p.Poly[(i + 1) % p.Poly.Count];
                Beam(new Vector3(a[0], a[1], Floor(a[2])), new Vector3(b[0], b[1], Floor(b[2])), green, 2f);
            }
        else
            for (int i = 0; i < 16; i++)
            {
                float a0 = i * MathF.PI / 8, a1 = (i + 1) * MathF.PI / 8;
                Beam(at + new Vector3(40 * MathF.Cos(a0), 40 * MathF.Sin(a0), 4), at + new Vector3(40 * MathF.Cos(a1), 40 * MathF.Sin(a1), 4), green, 2f);
            }
        var meT = cur.Players.FirstOrDefault(t => t.Me);
        foreach (var h in Humans())
            if (h.PawnIsAlive && h.PlayerPawn.Value is { } pw)
            {
                pw.Teleport(at, new Vector3(0, p.Ang[1], 0), Vector3.Zero);
                if (meT != null) Loadout(h, meT, 100);
            }
        Html($"<font color='#4fc3a1'>{F("HOLD {zone}", "zone", p.Zone)}</font>" + (drill.Free ? $" · {F("{i}/{n}, then free", "i", ph + 1, "n", drill.Posts.Count)}" : ""), 3);
    }

    // the drill's bombsite as the map has it (func_bomb_target, A or B by the drill's id): its box in the world
    (Vector3 Lo, Vector3 Hi)? siteBox;
    string? siteBoxFor;
    (Vector3 Lo, Vector3 Hi)? SiteBox()
    {
        var b = drill?.Id.Contains("BombsiteB") == true;
        var key = $"{Server.MapName}|{drill?.Id}";
        if (siteBoxFor == key) return siteBox;
        siteBoxFor = key; siteBox = null;
        if (drill?.Id.Contains("Bombsite") != true) return null;
        foreach (var e in Utilities.FindAllEntitiesByDesignerName<CBaseEntity>("func_bomb_target"))
        {
            bool isB;
            try { isB = CounterStrikeSharp.API.Modules.Memory.Schema.GetSchemaValue<bool>(e.Handle, "CBombTarget", "m_bIsBombSiteB"); } catch (Exception) { continue; }
            if (isB != b || e.Collision is not { } col) continue;
            var o = e.AbsOrigin is { } ao ? new Vector3(ao.X, ao.Y, ao.Z) : Vector3.Zero;
            siteBox = (o + new Vector3(col.Mins.X, col.Mins.Y, col.Mins.Z), o + new Vector3(col.Maxs.X, col.Maxs.Y, col.Maxs.Z));
        }
        Log("site box {s}: {b}", b ? "B" : "A", siteBox is { } sb ? $"{sb.Lo.X:F0} {sb.Lo.Y:F0} {sb.Lo.Z:F0} to {sb.Hi.X:F0} {sb.Hi.Y:F0} {sb.Hi.Z:F0}" : "none");
        return siteBox;
    }

    // a defense's site kept (23/10, the user: "ajouter ... le retard imposé (défense)"): its ticks with no attacker on it
    // (400 u of the plant zone, its floor)
    int defHeld, defHeldAt;
    int waveStartAt = -1;   // the tick its wave came (its 45 s check moved on 5 s at a time)
    int waveT0Of = -1;      // the tick its wave came, kept

    void DefendHeld()
    {
        if (drill?.Me == null || cur == null) return;
        var now = Server.TickCount;
        // a wave neither down, nor on the site, nor in a fight with you 45 s on: taken off, the next one comes (02/11, round 16,
        // Nuke's A with the MAG-7 hidden in its corner: its wave 2 walked to and from the zone 5 min, no kill, no taking, the
        // drill never ended); no fight, so it counts for nothing, as before
        if (waveStartAt >= 0 && now - waveStartAt > 45 * 64 && !waveDue && !waveLost && phase == "live")
        {
            var up = Attackers().Where(Up).ToList();
            var waveT0 = waveT0Of >= 0 ? waveT0Of : waveStartAt;
            waveStartAt = now - 40 * 64;   // asked again 5 s on
            // none of it in your sight 4 s; or 70 s whatever (03/11, round 18, Inferno's B with the MAG-7: its wave 4 on 4 min,
            // one of it seeing the shotgun from out of its reach, neither shooting); 70 s whatever its kills too (03/11, round
            // 20, Nuke's A with the MAG-7: one of wave 2 down, the other 4 min in and out of the zone, the 300 s drill gone on
            // that one wave)
            if (up.Count > 0 && (waveKills == 0 && up.All(sl => now - sawYou.GetValueOrDefault(sl, -100000) > 4 * 64) || now - waveT0 > 70 * 64))
            {
                Log("wave {w}: no fight in {s} s, {n} taken off", wave, (now - waveT0) / 64, up.Count);
                waveGone = true;
                foreach (var sl in up) Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value?.CommitSuicide(false, true);
            }
        }
        if (defHeldAt == 0) { defHeldAt = now; return; }
        var dt = now - defHeldAt;
        if (dt < 16) return;
        defHeldAt = now;
        var site = new Vector3(drill.Me.Pos[0], drill.Me.Pos[1], drill.Me.Pos[2]);
        // an attacker on the bombsite itself, the map's own (the box where the bomb is planted), you do not see (29/10, lab
        // 24: within 400 u of your spot, 3 s out of your sight on their way to you, the site was taken 14 times with
        // nobody on it; one in a duel with you is no site taken either); no box known: 400 u of your spot
        var box = SiteBox();
        var meSlot = Humans().FirstOrDefault(h => h.PawnIsAlive)?.Slot ?? -1;
        bool OnSite(CVector o) => box is { } bx
            ? o.X > bx.Lo.X - 24f && o.X < bx.Hi.X + 24f && o.Y > bx.Lo.Y - 24f && o.Y < bx.Hi.Y + 24f && o.Z > bx.Lo.Z - 64f && o.Z < bx.Hi.Z + 64f
            : new Vector2(o.X - site.X, o.Y - site.Y).Length() < 400f && MathF.Abs(o.Z - site.Z) < 160f;
        // you alive on the site or in your zone: the site contested, never taken while you stay there; they take it by killing
        // you (04/11, his rule: "si le client est sur site ça fait une contestation de site et tant que le client ne quitte pas
        // la zone je ne pars pas, par contre pour reprendre le site il faut tuer le joueur dans la zone")
        var contested = Humans().Any(h => h.PawnIsAlive && h.PlayerPawn.Value?.AbsOrigin is { } ho && (OnSite(ho) || InZone(ho)));
        var taken = !contested && Attackers().Any(sl => Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value is { AbsOrigin: { } o } pw && pw.LifeState == (byte)LifeState_t.LIFE_ALIVE
                                          && OnSite(o)
                                          && !(meSlot >= 0 && meSlot < 64 && (pw.EntitySpottedState.SpottedByMask[meSlot / 32] & (1u << (meSlot % 32))) != 0));
        if (!taken) defHeld += dt;
        else
        {   // on the site, uncontested: 8 s of it, the wave took it (04/11, his words: "laisse un peu de temps avant de perdre la
            // défense sur une prise de site"; it was 4 s)
            waveFaced = true;
            waveOnSite += dt;
            if (waveOnSite >= 8 * 64 && !waveLost)
            {
                waveLost = true; Log("wave {w}: the site taken", wave); Html($"<font color='#ff5a5a'>{T("SITE TAKEN")}</font>", 2);
                // the wave lost: over 3 s on, the next one comes (02/11, round 15, Nuke's B: taken at 11:18:05, nobody of it
                // down while the MAG-7 stayed hidden, the wave on 2 min 10 s, the 100 s drill 172 s)
                var gT = generation; var wT = wave;
                AddTimer(3f, () => WaveTakenOff(gT, wT));
            }
        }
        // one of the wave in sight of you: it came to the fight
        if (!waveFaced && Attackers().Any(sl => now - sawYou.GetValueOrDefault(sl, -100000) < 32)) waveFaced = true;
    }

    // you inside the place you hold now (its outline; the free part: the site itself, OnSite's)
    bool InZone(CVector o)
    {
        if (drill == null || postIdx < 0 || postIdx >= drill.Posts.Count) return false;
        var poly = drill.Posts[postIdx].Poly;
        if (poly.Count < 3) return new Vector2(o.X - drill.Posts[postIdx].Pos[0], o.Y - drill.Posts[postIdx].Pos[1]).Length() < 160f;
        bool inside = false;
        for (int i = 0, j = poly.Count - 1; i < poly.Count; j = i++)
            if ((poly[i][1] > o.Y) != (poly[j][1] > o.Y)
                && o.X < (poly[j][0] - poly[i][0]) * (o.Y - poly[i][1]) / ((poly[j][1] - poly[i][1]) == 0 ? 1e-6f : (poly[j][1] - poly[i][1])) + poly[i][0])
                inside = !inside;
        return inside;
    }

    // out of the place you hold (its outline drawn on the ground): the panel says to go back in it
    bool OutOfPost()
    {
        if (drill == null || postIdx < 0 || postIdx >= drill.Posts.Count) return false;
        var poly = drill.Posts[postIdx].Poly;
        if (poly.Count < 3) return false;
        var o = Humans().Where(h => h.PawnIsAlive).Select(h => h.PlayerPawn.Value?.AbsOrigin).FirstOrDefault(v => v != null);
        if (o == null) return false;
        bool inside = false;
        for (int i = 0, j = poly.Count - 1; i < poly.Count; j = i++)   // ray casting on the ground
            if ((poly[i][1] > o.Y) != (poly[j][1] > o.Y) && o.X < (poly[j][0] - poly[i][0]) * (o.Y - poly[i][1]) / (poly[j][1] - poly[i][1]) + poly[i][0])
                inside = !inside;
        return !inside;
    }

    // where you come back in a defense: the spot you hold, or the site's
    Vector3 DefendSpot() => drill != null && postIdx >= 0 && postIdx < drill.Posts.Count
        ? new Vector3(drill.Posts[postIdx].Pos[0], drill.Posts[postIdx].Pos[1], drill.Posts[postIdx].Pos[2])
        : Pos(cur!.Players.First(p => p.Me), 0);

    void SessionTick()
    {
        if (sess == null || cur == null || phase != "live") return;
        // dead without the drill knowing it (killed before GO: OnDeath only counts live deaths; 06/10, a minute on the
        // floor while the aim drill's targets came and went): the drill ends as dead, its retry puts you back on your spot
        if (drill?.Mode is not ("defend" or "range" or "crossfire" or "momentum") && !humanDead && Humans().Any() && Humans().All(h => !h.PawnIsAlive)) { Finish("dead"); return; }
        // dead in a defense with the drill not knowing it (03/11, rounds 18-19: a round restarted, or you put back on your
        // team, at the drill's start before its GO; OnDeath counts live deaths only, so no respawn came: Cache's AWP 84 s and
        // Overpass's B 295 s with nobody at the post, the waves taking the site): back on your post after 3 s dead
        if (drill?.Mode == "defend" && Humans().Any(h => h.TeamNum >= 2) && Humans().Where(h => h.TeamNum >= 2).All(h => !h.PawnIsAlive))
        {
            if (defDeadAt < 0) defDeadAt = Server.TickCount;
            else if (Server.TickCount - defDeadAt > 3 * 64)
            {
                defDeadAt = -1;
                var me0 = cur.Players.First(p => p.Me);
                var face0 = postIdx >= 0 && postIdx < drill.Posts.Count ? new Vector3(0, drill.Posts[postIdx].Ang[1], 0) : Upright(Ang(me0, 0));
                protectUntil = Server.TickCount + 2 * 64;
                foreach (var h in Humans().Where(h => h.TeamNum >= 2)) { h.Respawn(); Loadout(h, me0); h.PlayerPawn.Value?.Teleport(DefendSpot(), face0, Vector3.Zero); }
                Log("defense: you dead with the drill not knowing it, back on your post");
            }
        }
        else defDeadAt = -1;
        var el = (Server.TickCount - t0) / 64f;
        if (drill?.Mode == "crossfire") { CfTick(el); return; }
        if (drill?.Mode == "momentum") { MoTick(el); return; }
        if (EntryOn) { EntryGuide(el); EntryTick(el); return; }
        if (drill?.Mode == "range")
        {
            if (el >= drill.Seconds || frags >= drill.Goal * 2) { Finish(frags >= drill.Goal ? "cleared" : "done"); return; }
            if (drill.Variant == "strafe") StrafeTick();
            RangeBlindTick();
            var avg = reacts.Count > 0 ? $" · {reacts.Average():F2} s" : "";
            var hs = frags > 0 ? $" · {100 * aimHs / frags}% HS" : "";
            SetMain($"{Order(drill)}<br><font color='#ff8a3d'>{drill.Title}</font> · ⚔ {frags}/{drill.Goal}{avg}{hs} · {(int)(drill.Seconds - el)} s");
            return;
        }
        if (drill?.Mode is "prefire" or "defend")
        {
            // a defense: its 6 waves first, its time a guard only (04/11)
            if (el >= (drill.Mode == "defend" ? 6f * drill.Seconds : drill.Seconds) || defendDone) { defendDone = false; Finish(drill.Mode == "prefire" ? "timeout" : "done"); return; }
            if (drill.Mode == "defend") { DefendPost(el); DefendHeld(); RadarTick(); }
            if (drill.Mode == "prefire") PreReactTick();
            // a hidden one peeks at its time, or when you come near its spot (not after you passed it); the last two
            // all peek
            var mo = Humans().Select(h => h.PlayerPawn.Value?.AbsOrigin).FirstOrDefault(o => o != null);
            var mp = mo == null ? (Vector3?)null : new Vector3(mo.X, mo.Y, mo.Z);
            var fewLeft = drill.Mode == "prefire" && aimOrder.Count - frags <= 2;
            bool Near(int sl) => mp != null && bots.TryGetValue(sl, out var tt) && Vector3.Distance(Pos(tt, 0), mp.Value) < 1100;
            var ordered = drill.Mode == "prefire" && drill.Bots.Any(x => x.Seq >= 0);
            if (ordered && mp != null && drill.Line.Count > 1)
            {   // how far along the line you got: its nearest point within 300 u (same floor), never back
                for (int k = lineAt; k < drill.Line.Count; k++)
                {
                    var q = drill.Line[k];
                    if (MathF.Abs(q[2] - mp.Value.Z) < 120 && new Vector2(q[0] - mp.Value.X, q[1] - mp.Value.Y).Length() < 300) lineAt = Math.Max(lineAt, k);
                }
            }
            IEnumerable<int> due;
            if (ordered)
            {   // the next one in the way's order: at its time, or when you reach the line where it's seen; never two at once
                var next = peekAt.Keys.Select(sl => (sl, b: bots.TryGetValue(sl, out var tt) ? BotSpot(tt) : null)).Where(x => x.b != null)
                    .OrderBy(x => x.b!.Seq).FirstOrDefault();
                var ready = next.b != null && Server.TickCount - lastPeek >= 48 && (next.b.At <= el || lineAt >= next.b.Li - 1 || fewLeft);
                due = ready ? new[] { next.sl } : Array.Empty<int>();
            }
            else due = peekAt.Where(kv => kv.Value <= el || fewLeft || Near(kv.Key)).Select(kv => kv.Key).ToList();
            foreach (var slot in due.ToList())
            {   // its time: it peeks
                lastPeek = Server.TickCount;
                peekAt.Remove(slot);
                if (!bots.TryGetValue(slot, out var t)) continue;
                var c = Utilities.GetPlayerFromSlot(slot);
                if (c == null || !c.IsValid) continue;
                c.Respawn();
                Loadout(c, t);
                if (c.PlayerPawn.Value is { } pw) { pw.Teleport(Pos(t, 0), Upright(Ang(t, 0)), Vector3.Zero); Freeze(pw, true); }
                gone.Remove(t.Sid);
            }
            // the last ones not found in 8 s since your last kill: an orange post over each (09/10: one held Lower Tunnels,
            // behind the way, 37 s to find it: "et je ne trouve pas les derniers")
            if (drill.Mode == "prefire" && aimOrder.Count - frags <= 2 && Server.TickCount - preKillAt > 8 * 64) Beacons();
            {
                var left = (int)(drill.Seconds - el);
                var n = aimOrder.Count - frags;
                var where = drill.Mode == "prefire" && n <= 3 ? LeftPlaces() : "";
                SetMain(drill.Mode == "prefire"
                    ? $"{Order(drill)}<br><font color='#ff8a3d'>{drill.Title}</font> · {(where != "" ? F("{n} left: {where}", "n", n, "where", where) : F("{n} left", "n", n))}{(beaconed.Count > 0 ? $" ({T("orange posts")})" : "")}"
                      + $" · ⏱ {(int)el}/{(int)PrePar()} s<br><font class='fontSize-s'>{string.Join(" → ", drill.Route)}</font>"
                    // the green zone first and big, zone or site said (22/10 eve, the user: "préciser si c'est de la défense de
                    // zone ou de la défense de bomb site ... le plus important c'est quand même de dire que bah faut rester
                    // dans la zone verte"), the drill's own line under it
                    : (drill.Posts.Count == 0 || postIdx < 0 ? "" : postIdx < drill.Posts.Count
                          ? (OutOfPost() ? $"<font color='#ff5a5a' class='fontSize-l'>⚠ {F("back in {zone} (the green zone)", "zone", drill.Posts[postIdx].Zone)}</font><br>"
                                         : $"<font color='#5ad15a' class='fontSize-l'>🟩 {((drill.Posts[postIdx].Zone ?? "").Contains("Site") ? T("BOMBSITE DEFENSE") : T("ZONE DEFENSE"))} · {F("stay in {zone}, the green zone", "zone", drill.Posts[postIdx].Zone)}</font><br>")
                          : $"<font class='fontSize-s'>{T("free")}</font><br>")
                      + $"<font color='#ff8a3d'>{drill.Title}</font> · 🌊 {F("wave {w} · {h} held", "w", wave, "h", wavesHeld)} / {DefendWaves} · ⚔ {frags} · ☠ {deaths}");
            }
            return;
        }
        if (cur.Kind is "death" or "clutch")   // the drill's line and the next place of your route in the match
        {
            var me = cur.Players.FirstOrDefault(p => p.Me);
            var fr = (Server.TickCount - t0) / (float)cur.Step;
            var next = me?.Places.Select(p => (at: p[0].GetInt32(), nm: p[1].GetString())).Where(p => p.at > fr + 8).Select(p => p.nm).FirstOrDefault();
            var bomb = "";
            if (bombLive)   // the bomb's clock, and what it asks of you
                foreach (var c4 in Utilities.FindAllEntitiesByDesignerName<CPlantedC4>("planted_c4"))
                    bomb = $"<font color='#ff5a5a'>💣 {(c4.BombSite == 1 ? "B" : "A")} · {Math.Max(0, c4.C4Blow - Server.CurrentTime):F0} s</font> · {(cur.Team == 3 ? T("defuse it") : T("keep it ticking"))}";
            // the bomb's clock (else the round's) and both sides always (23/10, the user: "le minuteur de bombe et l'état
            // des alliés en permanence"): who is up, your teammates' health
            if (bomb == "" && cur.Clock > 0) bomb = $"⏱ {RoundLeft(cur.Clock - (Server.TickCount - t0) / 64f)}";
            var way = cur.Line.Count > 1 ? T("the gold line takes you to the blue zone") : T("your route in the match");
            SetMain($"{(drill != null ? Order(drill) : "")}<br><font color='#e0a030'>{drill?.Title}</font>{(bomb != "" ? $" · {bomb}" : "")}<br>{TeamsLine()}{(next != null ? $"<br>→ {next} <font class='fontSize-s'>({way})</font>" : "")}");
        }
        if (cur.Kind == "aim" && string.IsNullOrEmpty(drill?.Mode))
            SetMain($"{(drill != null ? Order(drill) : "")}<br><font color='#ff8a3d'>{drill?.Title}</font> · {F("target {i}/{n}", "i", Math.Max(1, aimNext), "n", aimOrder.Count)}");
        if (ExecOn) ExecTick();
        else if (StepsOn && nadeStage == "throw") SetMain(StepsTick());
        else if (cur.Kind == "nade" && drill != null && nadeStage != "theirs")   // their side keeps its own card
            SetMain($"{HowBig(drill)}<br><font color='#5ab4ff'>{drill.Title}</font> · {(drill.Rush ? (drill.Level < 2 ? F("they get there at {t}", "t", RoundClock(drill.RushAt)) : T("in time")) : F("throw {i}/3", "i", Math.Min(3, attempts + 1)))}"
                    + NadeLastLine());
        // a target not found in 12 s goes away (missed), the next one comes
        if (cur.Kind == "aim" && aimSpawn > 0 && Server.TickCount - aimSpawn > 12 * 64)
        {
            aimSpawn = 0;
            var slot = aimOrder.ElementAtOrDefault(aimNext - 1);
            Html($"<font color='#ff5a5a'>{T("MISSED")}</font> · {T("next one")}", 1);
            Utilities.GetPlayerFromSlot(slot)?.PlayerPawn.Value?.CommitSuicide(false, true);
        }
        if (cur.Kind == "aim" && Server.TickCount - t0 > 120 * 64) Finish("timeout");
        // a grenade of yours still in the air: the try's time waits for its landing (27/10 19:22, Dust2's A smoke to Long:
        // a 20 s walk to its spot, its 4.5 s flight popped once the try was counted "no throw", ignored: raté 3 times)
        if (cur.Kind == "nade" && nadeWait && Clock > attemptEnd && !recPending.Any(x => Server.TickCount - x.tick < 12 * 64))
        { if (ExecOn) ExecOver(); else NadeResult(double.NaN); }
        if (cur.Kind == "nade") RushCheck();
        if (cur.Kind == "nade") CrossFollow();
    }

    // true: handled here (a defense: you come back instead of the drill ending)
    bool SessionDeath(EventPlayerDeath e, CCSPlayerController? v)
    {
        if (sess != null && EntryOn && v != null) return EntryDeath(e, v);
        if (sess == null || cur?.Kind != "aim" || drill == null || v == null) return false;
        if (drill.Mode == "crossfire") return CfDeath(e, v);
        if (drill.Mode == "prefire")
        {
            if (!v.IsBot) return false;
            if (e.Attacker is { IsValid: true, IsBot: false }) { frags++; if (e.Headshot) aimHs++; preKillAt = Server.TickCount; }
            if (peekAt.ContainsKey(v.Slot)) return false;   // a hidden one going to wait for its timing
            var left = bots.Count(b => !gone.Contains(b.Value.Sid) && b.Key != v.Slot) + peekAt.Count;
            if (left == 0) AddTimer(0.3f, () => Finish("cleared"));
            else Html($"<font color='#ff8a3d'>{F("{n} left", "n", left)}</font>{(e.Headshot ? " · HS" : "")}", 1);
            return false;
        }
        if (drill.Mode == "range")
        {
            var g = generation;
            if (!v.IsBot)   // a duel lost: back on your spot in 1 s
            {
                deaths++;
                AddTimer(1f, () =>
                {
                    if (g != generation || phase != "live" || cur == null) return;
                    var me = cur.Players.First(p => p.Me);
                    protectUntil = Server.TickCount + 64;
                    foreach (var h in Humans()) { h.Respawn(); Loadout(h, me); h.PlayerPawn.Value?.Teleport(Pos(me, 0), Upright(Ang(me, 0)), Vector3.Zero); }
                });
                return true;
            }
            if (e.Attacker is { IsValid: true, IsBot: false })
            {
                frags++;
                if (e.Headshot) aimHs++;
                var now = Server.TickCount;   // from the later of its coming and your last kill: the time to find it and kill it
                reacts.Add((now - Math.Max(lastKill, cameAt.GetValueOrDefault(v.Slot, t0))) / 64.0);
                lastKill = now;
            }
            var sl0 = v.Slot;
            AddTimer(drill.Variant == "flick" ? 0.25f + (float)Rng.NextDouble() * 0.45f : 0.6f + (float)Rng.NextDouble() * 0.6f, () => RangeAgain(g, sl0));
            return false;
        }
        if (drill.Mode == "defend")
        {
            var g = generation;
            if (!v.IsBot)   // you: back on the spot in 1.5 s, out of reach for 2 s
            {
                deaths++;
                waveLost = true; waveFaced = true;   // the wave that got you won it
                AddTimer(1.5f, () =>
                {
                    if (g != generation || phase != "live" || cur == null) return;
                    var me = cur.Players.First(p => p.Me);
                    var spot = DefendSpot();
                    // the wave that got you goes, a new one comes from the entrances, all of it at once (09/10): no death
                    // the moment you are back (04/10, "the spawn kill problem is very annoying"), nobody already in front
                    // of you (09/10 on Fachwerk's Long A: "pareil je spawn devant eux")
                    NewWave();
                    protectUntil = Server.TickCount + 2 * 64;
                    var face = postIdx >= 0 && postIdx < drill.Posts.Count ? new Vector3(0, drill.Posts[postIdx].Ang[1], 0) : Upright(Ang(me, 0));
                    foreach (var h in Humans()) { h.Respawn(); Loadout(h, me); h.PlayerPawn.Value?.Teleport(spot, face, Vector3.Zero); }
                });
                return true;
            }
            if (e.Attacker is { IsValid: true, IsBot: false }) { frags++; if (e.Headshot) aimHs++; waveKills++; waveFaced = true; }
            AddTimer(0.1f, () => WaveCheck(g));   // the next ones once this wave is down
            return false;
        }
        if (!v.IsBot) return false;
        if (e.Attacker is { IsValid: true, IsBot: false } && aimSpawn > 0)
        {
            reacts.Add((Server.TickCount - aimSpawn) / 64.0);
            if (e.Headshot) aimHs++;
            Html($"<font color='#ff8a3d'>{T("HIT")}</font> {reacts[^1]:F2} s{(e.Headshot ? " · HS" : "")} · {reacts.Count}/{aimOrder.Count}", 1);
        }
        aimSpawn = 0;
        if (aimNext < aimOrder.Count)
        {
            var slot = aimOrder[aimNext++];
            var g = generation;
            AddTimer(0.4f + (float)Rng.NextDouble() * 1.2f, () =>
            {
                if (g != generation || phase != "live" || !bots.TryGetValue(slot, out var t)) return;
                var c = Utilities.GetPlayerFromSlot(slot);
                if (c == null || !c.IsValid) return;
                c.Respawn();
                Loadout(c, t);
                if (c.PlayerPawn.Value is { } pw) { pw.Teleport(Pos(t, 0), Upright(Ang(t, 0)), Vector3.Zero); Freeze(pw, true); }
                gone.Remove(t.Sid);
                free.Remove(slot);
                aimSpawn = Server.TickCount;
                AimCard();
            });
        }
        else AddTimer(0.4f, () => Finish(reacts.Count == aimOrder.Count ? "cleared" : "done"));
        return false;
    }

    // a prefire's reference time: the drill's own (the base's), else its gold line at a careful run (180 u/s) and a moment
    // for each angle
    float PrePar()
    {
        if (drill == null) return 0f;
        if (drill.Par > 0) return drill.Par;
        var len = 0f;
        for (int i = 0; i + 1 < drill.Line.Count; i++)
            len += new Vector2(drill.Line[i + 1][0] - drill.Line[i][0], drill.Line[i + 1][1] - drill.Line[i][1]).Length();
        return MathF.Max(8f, len / 180f + 0.4f * drill.Bots.Count);
    }

    // a prefire's CTs that react as the base's do (23/10, the user: "quelques CT qui réagissent comme ceux de la base"; the
    // report: "ils ne bougent pas après un premier tir manqué"): your shot while it was in your sight, and it still up a
    // moment later, it steps off its angle out of your sight, then swings back onto it a second or so later, once
    readonly Dictionary<int, (int stage, int at, Vector3 from, Vector3 to)> preReact = new();
    int preShot, preMoved;

    void PreReactReset() { preReact.Clear(); preShot = 0; preMoved = 0; }

    void PreShot() { if (drill?.Mode == "prefire" && phase == "live") preShot = Server.TickCount; }

    void PreReactTick()
    {
        if (drill == null || cur == null) return;
        var now = Server.TickCount;
        var h = Humans().FirstOrDefault(x => x.PawnIsAlive);
        var me = h?.PlayerPawn.Value;
        if (h == null || me?.AbsOrigin == null) return;
        var eye = new CVector(me.AbsOrigin.X, me.AbsOrigin.Y, me.AbsOrigin.Z + (me.ViewOffset?.Z ?? 64f));
        foreach (var (sl, t) in bots.ToList())
        {
            var b = BotSpot(t);
            if (b == null || !b.React || gone.Contains(t.Sid) || peekAt.ContainsKey(sl)) continue;
            var pw = Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value;
            if (pw?.AbsOrigin == null || pw.LifeState != (byte)LifeState_t.LIFE_ALIVE) continue;
            var st = preReact.GetValueOrDefault(sl);
            var home = new Vector3(b.Pos[0], b.Pos[1], b.Pos[2]);
            switch (st.stage)
            {
                case 0:   // on its angle: your shot missed it (or left it up) while you saw it
                    var seen = (pw.EntitySpottedState.SpottedByMask[h.Slot / 32] & (1u << (h.Slot % 32))) != 0;
                    if (!seen || preShot == 0 || now - preShot < 20 || now - preShot > 40) break;
                    var off = PreCover(eye, me, pw, home);
                    if (off == null) { preReact[sl] = (9, now, home, home); break; }   // nowhere to go: it holds
                    preReact[sl] = (1, now, home, off.Value);
                    preMoved++;
                    if (selftest) St("prefire_react", new() { ["bot"] = t.Sid, ["to"] = R3(off.Value) });
                    Html($"<font color='#ff8a3d'>↩ {T("it stepped off its angle: it will peek again")}</font>", 1);
                    break;
                case 1:   // off its angle quickly (a fifth of a second)
                    var k = Math.Min(1f, (now - st.at) / 13f);
                    t.Path = new[] { st.from.X + (st.to.X - st.from.X) * k, st.from.Y + (st.to.Y - st.from.Y) * k, st.from.Z + (st.to.Z - st.from.Z) * k, b.Ang[1], b.Ang[0] };
                    if (k >= 1f) preReact[sl] = (2, now + 64 + Rng.Next(48), st.from, st.to);
                    break;
                case 2:   // out of your sight a second or so
                    if (now >= st.at) preReact[sl] = (3, now, st.to, st.from);
                    break;
                case 3:   // back onto its angle: a wide swing at a run
                    var k2 = Math.Min(1f, (now - st.at) / 16f);
                    t.Path = new[] { st.from.X + (st.to.X - st.from.X) * k2, st.from.Y + (st.to.Y - st.from.Y) * k2, st.from.Z + (st.to.Z - st.from.Z) * k2, b.Ang[1], b.Ang[0] };
                    if (k2 >= 1f) preReact[sl] = (9, now, st.to, st.to);
                    break;
            }
        }
    }

    // where a prefire's CT steps to: 56 or 80 u to one side of your line, else back from you, on its floor, no wall on the
    // way, out of your sight
    static Vector3? PreCover(CVector eye, CCSPlayerPawn mePw, CCSPlayerPawn pw, Vector3 home)
    {
        var to = new Vector2(home.X - eye.X, home.Y - eye.Y);
        if (to.Length() < 1f) return null;
        var fw = Vector2.Normalize(to);
        var side = new Vector2(-fw.Y, fw.X);
        var shot = new TraceOptions { InteractsWith = Masks.ShotBrushOnly };
        foreach (var d in new[] { side * 56f, -side * 56f, side * 80f, -side * 80f, fw * 64f })
        {
            var p = home + new Vector3(d.X, d.Y, 0f);
            if (Trace.TraceEndShape(new CVector(home.X, home.Y, home.Z + 36f), new CVector(p.X, p.Y, p.Z + 36f), pw, shot).Fraction < 0.99f) continue;
            if (Trace.TraceEndShape(new CVector(p.X, p.Y, p.Z + 8f), new CVector(p.X, p.Y, p.Z - 24f), pw, shot).Fraction >= 1f) continue;   // no floor
            if (Trace.TraceEndShape(eye, new CVector(p.X, p.Y, p.Z + 62f), mePw, shot).Fraction > 0.98f) continue;   // its head in your sight
            if (Trace.TraceEndShape(eye, new CVector(p.X, p.Y, p.Z + 40f), mePw, shot).Fraction > 0.98f) continue;   // its chest
            return p;
        }
        return null;
    }

    // a prefire's bots still up and out (not waiting for their turn): an orange post over each, once
    void Beacons()
    {
        var orange = System.Drawing.Color.FromArgb(255, 255, 140, 40);
        foreach (var (sl, t) in bots)
        {
            if (beaconed.Contains(sl) || peekAt.ContainsKey(sl) || gone.Contains(t.Sid) || !Up(sl)) continue;
            beaconed.Add(sl);
            var p = Pos(t, 0);
            Beam(p + new Vector3(0, 0, 80), p + new Vector3(0, 0, 400), orange, 4f);
        }
    }

    // a defense's attackers come in waves (09/10, his Dust2 A: "il y a 3 bots en vie théoriquement, et j'en croise très
    // rarement 3 en même temps"): one walking in as another one died, they came one by one. Now all of a wave start
    // together on real ways (their tracks start the same time before they come into sight) and the next wave comes once
    // this one is down; one of them staying away from the fight (it has not seen you for 4 s) 10 s after the wave's first
    // death is taken off.
    IEnumerable<int> Attackers() => cur == null ? Enumerable.Empty<int>() : bots.Where(b => b.Value.Team != cur.Team).Select(b => b.Key).ToList();
    static bool Up(int sl) => Utilities.GetPlayerFromSlot(sl) is { IsValid: true, PawnIsAlive: true };

    // where a defense's attacker starts its way: 24 s of it before its point nearest the spot you hold (30/10, the user: "ils
    // sont censés venir à moi et du coup je suis censé pouvoir les tuer avant que le temps s'écoule et que je change de spot":
    // from the real player's start, often the T spawn, walking as players they got there after the spot's 30 s)
    static float WayLead(float[] path, float[]? spot, float fps)
    {
        var n = path.Length / 5;
        if (n < 2 || spot is not { Length: >= 2 }) return 0f;
        int kn = 0; var best = float.MaxValue;
        for (int k = 0; k < n; k++)
        {
            var d = new Vector2(path[k * 5] - spot[0], path[k * 5 + 1] - spot[1]).LengthSquared();
            if (d < best) { best = d; kn = k; }
        }
        var lead = Math.Max(0f, kn - 24f * fps);   // v22: 10 s, all of a wave on you at once (1 drill of 12); v23 18 s: 2 of 6; v20 from its start 4 of 6 but a drill with no wave
        // never before its last stretch in: back from its nearest point while it was ever further away; a way that came near
        // and went off again (a whole round: Mirage's "Palace Alley" ways went to A, back to their spawn, then Palace) starts
        // where it turned for you (30/10, his review: "les bots spawnent dans la rampe ... j'aimerais bien qu'ils spawnent dans
        // le spawn", they came into Palace from the ramp by the site)
        int far = kn; var farD = 0f;
        for (int k = kn; k >= 0; k--)
        {
            var d = new Vector2(path[k * 5] - spot[0], path[k * 5 + 1] - spot[1]).Length();
            if (d > farD) { farD = d; far = k; }
            else if (d < farD - 600f) break;   // a turn back from 600 u nearer (a stroll in a room is no turn)
        }
        return farD >= 800f ? Math.Max(lead, far) : lead;
    }

    // its first grenade from there on (the ones before its start are not its)
    static int FirstNade(List<Nade> nades, float from)
    {
        var i = nades.FindIndex(x => x.F >= from);
        return i < 0 ? nades.Count : i;
    }

    // the attackers still up go (your death, another post): their deaths call the next wave
    void NewWave()
    {
        var up = Attackers().Where(Up).ToList();
        if (up.Count == 0) { WaveCheck(generation); return; }
        foreach (var sl in up) Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value?.CommitSuicide(false, true);
    }

    void WaveCheck(int g)
    {
        if (g != generation || phase != "live" || cur == null || drill?.Mode != "defend" || waveDue) return;
        if (!Attackers().Any(Up))
        {
            waveDue = true;
            var w = wave;
            AddTimer(1.2f + (float)Rng.NextDouble() * 0.8f, () => { if (g == generation && w == wave) StartWave(g); });
            return;
        }
        if (waveFirstDead < 0)
        {
            waveFirstDead = Server.TickCount;
            var w = wave;
            AddTimer(10f, () => WaveStale(g, w));
        }
    }

    void WaveTakenOff(int g, int w)
    {
        if (g != generation || w != wave || waveDue || phase != "live" || cur == null) return;
        var up = Attackers().Where(Up).ToList();
        if (up.Count == 0) return;
        Log("wave {w}: the site taken, {n} taken off", wave, up.Count);
        waveGone = true;
        foreach (var sl in up) Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value?.CommitSuicide(false, true);
    }

    void WaveStale(int g, int w)
    {
        if (g != generation || w != wave || waveDue || phase != "live" || cur == null) return;
        var now = Server.TickCount;
        var up = Attackers().Where(Up).ToList();
        if (up.Count == 0) { WaveCheck(g); return; }
        // still on its way to the zone: not taken off (27/10, the user: "le problème est le comportement des adversaires qui
        // ne se dirigent pas vers la zone"; their ways now walked on to the post, Mirage's waves were taken off at 12 s
        // just as they got there)
        bool Walking(int sl) => !free.Contains(sl) && bots.TryGetValue(sl, out var tr) && (Server.TickCount - t0) / (float)cur.Step - tr.Start < tr.Frames - 1;
        // nor one in the zone by you, looking for you (18:05, Cache: walked to the post, the defender hidden in its zone,
        // 21 waves taken off unseen): only the ones gone off, 700 u away
        var me = Humans().Where(h => h.PawnIsAlive).Select(h => h.PlayerPawn.Value?.AbsOrigin).FirstOrDefault(v => v != null);
        bool Near(int sl) => me != null && Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value?.AbsOrigin is { } bo
                             && new Vector2(bo.X - me.X, bo.Y - me.Y).Length() < 700f;
        if (up.All(sl => now - sawYou.GetValueOrDefault(sl, -100000) > 4 * 64 && !Walking(sl) && !Near(sl)))
        {   // nobody of it in the fight any more: taken off, the next wave comes
            Log("wave {w}: {n} away from the fight, taken off", wave, up.Count);
            waveGone = true;
            foreach (var sl in up) Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value?.CommitSuicide(false, true);
            return;
        }
        AddTimer(2f, () => WaveStale(g, w));   // still fighting: wait
    }

    void StartWave(int g)
    {
        if (g != generation || phase != "live" || cur == null || drill == null) return;
        WaveEnd(!waveGone);   // the last one, the drill's first ones too (v13: never counted, "0 waves held of 0" with 2 kills)
        // its post's waves over: the next post now, before this wave comes (30/10, his review on Nuke's B: the post changed
        // the tick after a wave came and took it off, never fought, "3 vagues tenues sur 5"); all of them over: no wave
        if (drill.Mode == "defend" && drill.Posts.Count > 0 && postIdx >= 0)
        {
            DefendPost(0f, true);
            if (defendDone) return;
        }
        wave++; waveDue = false; waveFirstDead = -1;
        var start = (Server.TickCount - t0) / (float)cur.Step;   // the same for all: they come into sight together
        var n = 0;
        // one after the other, 1.2 s apart (v12: 190 u between two of a wave, real Ts 460 from their nearest teammate)
        foreach (var sl in Attackers())
            if (Utilities.GetPlayerFromSlot(sl) is { IsValid: true } c && !c.PawnIsAlive && bots.TryGetValue(sl, out var t)) { Attacker(c, t, start + n * 1.2f * cur.Rate / cur.Step); n++; }   // the second waits on its start
        Log("wave {w}: {n} attackers", wave, n);
        waveStartAt = Server.TickCount; waveT0Of = Server.TickCount;
        foreach (var sl in Attackers()) radarUntil[sl] = Server.TickCount + 128;   // on your radar 2 s where they spawned
        // a wave that never comes to the fight goes in 12 s, not only once one of it is dead (24/10, the real-client
        // battery on Vertigo's B: the first two saw you in the countdown, went their own way, nobody died, no wave came:
        // 100 s at your post with nobody)
        var w1 = wave;
        AddTimer(12f, () => WaveStale(g, w1));
    }

    // one of the wave: a real hit on the site walked from now with its grenades (it fights once it sees you), or the game's
    // AI from an entrance not right next to you
    void Attacker(CCSPlayerController c, Track t, float start)
    {
        if (cur == null || drill == null) return;
        var slot = c.Slot;
        c.Respawn();
        Loadout(c, t);
        string? zone;
        if (drill.Tracks.Count > 0)
        {
            // a way's start another bot stands on: another way, else this one from further on (17/10, the self-test: two of a
            // wave spawned in each other on Inferno's Apps, neither could move)
            var taken = bots.Keys.Where(k => k != slot).Select(k => Utilities.GetPlayerFromSlot(k)).Where(o => o is { IsValid: true, PawnIsAlive: true })
                .Select(o => o!.PlayerPawn.Value?.AbsOrigin).Where(o => o != null).Select(o => new Vector3(o!.X, o.Y, o.Z)).ToList();
            bool Busy(Vector3 at) => taken.Any(p => Vector3.Distance(p, at) < 48f);
            var tr = PickTrack(drill, postIdx < 0 ? 0 : postIdx)!;
            for (var k = 0; k < 6 && tr.Path.Length >= 3 && Busy(new Vector3(tr.Path[0], tr.Path[1], tr.Path[2])); k++) tr = PickTrack(drill, postIdx < 0 ? 0 : postIdx)!;
            t.Path = tr.Path;
            t.TrackNades = tr.Nades;
            var ahead = WayLead(t.Path, postIdx >= 0 && postIdx < drill.Posts.Count ? drill.Posts[postIdx].Pos : drill.Me?.Pos, cur.Rate / (float)cur.Step);
            t.NadeNext = FirstNade(t.TrackNades, ahead);
            while (ahead < t.Frames - 1 && Busy(PathAt(t, ahead))) ahead += 0.25f * cur.Rate / cur.Step;   // a quarter second on
            t.Start = start - ahead;
            t.SpawnF = ahead;
            t.Warp = 0;   // a new way: its clock on time again
            t.JumpDone = -1;
            zone = tr.Zone;
            free.Remove(slot);
            contact.Remove(slot);
            engaged.Remove(slot);
            var a0 = Math.Min(t.Frames - 1, (int)ahead);
            if (c.PlayerPawn.Value is { } pw) { pw.Teleport(PathAt(t, ahead), Upright(Ang(t, a0)), Vector3.Zero); Freeze(pw, false); }   // it walks its way
            ForgetMotion(slot);
        }
        else
        {
            var me = Pos(cur.Players.First(p => p.Me), 0);
            var far = drill.Bots.Where(b => Vector3.Distance(new Vector3(b.Pos[0], b.Pos[1], b.Pos[2]), me) > 600).ToList();
            if (far.Count == 0) far = drill.Bots;
            var sp = far[Rng.Next(far.Count)];
            zone = sp.Zone;
            c.PlayerPawn.Value?.Teleport(new Vector3(sp.Pos[0], sp.Pos[1], sp.Pos[2]), new Vector3(0, sp.Ang[1], 0), Vector3.Zero);
        }
        if (zone != null) { c.PlayerName = zone; Utilities.SetStateChanged(c, "CBasePlayerController", "m_iszPlayerName"); }
        gone.Remove(t.Sid);
    }

    // a defense: a bomb planted is taken away (and costs points)
    void BombPlanted()
    {
        if (sess == null || drill?.Mode != "defend" || phase != "live") return;
        plants++;
        waveLost = true; waveFaced = true;
        Html($"<font color='#ff5a5a'>{T("PLANTED")}</font> · −60", 2);
        AddTimer(0.2f, () => { foreach (var c4 in Utilities.FindAllEntitiesByDesignerName<CPlantedC4>("planted_c4")) c4.Remove(); });
    }

    // which target, where to look
    void AimCard()
    {
        var slot = aimOrder.ElementAtOrDefault(aimNext - 1);
        var where = bots.TryGetValue(slot, out var t) ? t.Name : "";
        Html($"<font color='#ff8a3d'>{F("TARGET {i}/{n}", "i", aimNext, "n", aimOrder.Count)}</font> → <font class='fontSize-l'>{where}</font>", 2);
    }

    void NadeHit(CCSPlayerController? u, float x, float y, float z, string type)
    {
        if (entrySky && type is "smoke" or "molotov") EntrySkyPop(type, x, y, z);   // the entry's sky view (Entry.cs)
        if (stVictims && type == "smoke") stVicPop = new Vector3(x, y, z);   // the self-test's victims (SelfTest.cs)
        if (stVictims && selftest) St("vpop", new() { ["type"] = type, ["at"] = new[] { R1(x), R1(y), R1(z) } });
        if (sess != null && cur?.Kind == "nade" && (u is { IsValid: true, IsBot: false } || IsGuide(u)))
        {
            if (cam != null) camEnd = Math.Min(camEnd, Server.TickCount + 64);   // the camera stays 1 s on it
            if (nadeStage == "theirs") { TheirsPopped(); return; }
        }
        if (sess == null || drill == null || cur?.Kind != "nade" || phase is not ("live" or "countdown") || !nadeWait || u == null || !u.IsValid || (u.IsBot && !IsGuide(u))) return;
        if (ExecOn) { ExecPop(type, x, y, z); return; }
        var tg = drill.Target;
        if (tg == null || tg.Length < 2) return;
        nadePops.Add(new[] { (float)Math.Round(x), (float)Math.Round(y) });
        nadePop = new Vector3(x, y, z);
        var bounces = nadeBounces;
        nadeBounces = 0;
        // over its spot is no landing (19/10, his video: "visiblement la molotov explose avant d'atterrir", 430 u up and
        // counted landed): a molotov burst in the air, a smoke on another floor
        var dz = tg.Length >= 3 ? z - tg[2] : 0f;
        var off = drill.Type == "molotov" && dz > 64f ? T("it burst in the air, before landing")
            : drill.Type == "smoke" && MathF.Abs(dz) > 96f ? T("it came down on another floor") : null;
        off ??= StepsEarly();   // step by step: let go before the move (Steps.cs)
        if (selftest) St("pop", new() { ["at"] = new[] { R1(x), R1(y), R1(z) }, ["dist"] = R1((float)Math.Sqrt((x - tg[0]) * (x - tg[0]) + (y - tg[1]) * (y - tg[1]))),
            ["dz"] = R1(dz), ["off"] = off, ["bounces"] = bounces, ["guide"] = IsGuide(u) });
        var dist = Math.Sqrt((x - tg[0]) * (x - tg[0]) + (y - tg[1]) * (y - tg[1]));
        if (drill.Type == "molotov" && off == null)
        {   // a molotov lands once its fire burns on the ground, whatever its spot says (27/10 22:13, Inferno's exec B from
            // Banana, the user: "la molotov ... explose en l'air": burst by its 2 s fuse 122 u over the site, no fire, the
            // base's spot itself in the air; 28/10 00:17, Anubis's Walkway: burst by its fuse 30 u over the floor, its fire
            // there, 141 HP from their side): its flames looked for half a second on, as an exec's (Exec.cs)
            var g0 = sessGen;
            AddTimer(0.5f, () =>
            {
                if (g0 != sessGen || drill == null || !nadeWait) return;
                var burns = Utilities.FindAllEntitiesByDesignerName<CInferno>("inferno").Any(f => f.IsValid && f.FireCount > 0 && f.AbsOrigin is { } fo
                    && MathF.Sqrt((fo.X - x) * (fo.X - x) + (fo.Y - y) * (fo.Y - y)) < 220f);
                if (!burns) Log("molotov at {x:F0} {y:F0} {z:F0}: no fire, it burst in the air", x, y, z);
                NadeResult(dist, burns ? null : T("it burst in the air, before landing"));
            });
            return;
        }
        NadeResult(dist, off, drill.Type == "flash" ? bounces : 0);
    }

    // a throw landed (dist from the spot of the pros' throws) or 25 s without one (NaN)
    void NadeResult(double dist, string? off = null, int bounces = 0)
    {
        if (drill == null) return;
        attempts++;
        // a flash or an HE pops in the air, a molotov's fire spreads: wider than a smoke; a smoke 110 u off at most (19/10,
        // his video: "la smoke n'est pas bien", 129 u off and counted good under the 180 u then)
        var (ok1, ok2) = drill.Type switch { "flash" or "he" => (120, 260), "molotov" => (120, 240), _ => (70, 110) };
        var q = double.IsNaN(dist) ? "no throw" : off != null ? "miss" : dist <= ok1 ? "perfect" : dist <= ok2 ? "good" : "miss";
        var away = double.IsNaN(dist) ? "" : off ?? F("{d} u from the spot", "d", Math.Round(dist));
        if (bounces > 0) away += $" · {T("it bounced: they hear it coming")}";
        nadeLast = $"{(q is "perfect" or "good" ? "✔" : "✘")} {F("throw {i}", "i", attempts)}: {(away != "" ? away : Shown(q).ToLower())}";
        if (drill.Rush)
        {   // a timing smoke: up on its spot before the runners, one throw (they ran past otherwise: all again)
            nadeWait = false;
            var el = (Server.TickCount - t0) / 64f - rushDelay;
            var first = drill.Tracks.Where(x => x.Arrive >= 0).Select(x => x.Arrive).DefaultIfEmpty(99f).Min();
            var margin = first - el;
            var before = F("{s} s before them", "s", margin.ToString("F1", CultureInfo.InvariantCulture));
            if (q is "perfect" or "good" && rushIn < 0)
            {
                var pts = (int)((q == "perfect" ? 150 : 100) * (margin < 1.5f ? 1.2 : 1.0) * (1 + 0.25 * drill.Level));
                Html($"<font color='#5ad15a'>✔ {Shown("in time")}</font> · {before}<br>{away}", 3);
                var g1 = sessGen;
                AddTimer(3f, () => { if (g1 == sessGen) DrillDone(true, "in time", pts, $"{before} · {away}"); });   // they run into it
                return;
            }
            DrillDone(false, rushIn >= 0 ? "late" : q, 0, rushIn >= 0 ? $"{T("they were there before it")} · {away}" : away);
            return;
        }
        if (q is "perfect" or "good")
        {
            nadeWait = false;
            var pts = (int)((q == "perfect" ? 150 : 100) * (attempts == 1 ? 1 : attempts == 2 ? 0.6 : 0.35) * (1 + 0.25 * drill.Level));
            var res = (true, q, pts, $"{away} · {F("throw {i}", "i", attempts)}");
            if (drill.Victims.Count == 0) { DrillDone(res.Item1, res.Item2, res.pts, res.Item4); return; }
            Html($"<font color='#5ad15a'>✔ {Shown(q)}</font> {away}<br>{T("now from their side")}", 3);
            var g0 = sessGen;
            AddTimer(1.6f, () => { if (g0 == sessGen) Theirs(res); });   // after the camera
            return;
        }
        if (attempts >= 3) { nadeWait = false; DrillDone(false, "miss", 0, away); return; }
        // once more: back on the spot with a new grenade; after two misses the aim is shown
        var show = attempts >= 1 && drill.Level >= 1;   // the aim from the first miss (04/10: "it lacks cues")
        Html($"<font color='#ff5a5a'>{Shown(q)}</font> {away}<br>{F("throw {i}/3", "i", attempts + 1)}{(show ? $" · {T("here is the aim")}" : "")}", 2);
        nadeWait = false;
        AddTimer(1.2f, ClearNades);
        var g = sessGen;
        AddTimer(1.5f, () =>
        {
            if (g != sessGen || drill == null || cur == null || phase is not ("live" or "countdown")) return;
            var me = drill.Me ?? new Spot();
            foreach (var h in Humans())
            {
                if (!h.PawnIsAlive) continue;
                h.GiveNamedItem(drill.Item);
                h.ExecuteClientCommandFromServer($"use {drill.Item}");
                var t = cur.Players.First(p => p.Me);
                var ang = show ? new Vector3(me.Ang[0], me.Ang[1], 0) : Ang(t, 0);
                if (!StepsOn) h.PlayerPawn.Value?.Teleport(new Vector3(me.Pos[0], me.Pos[1], me.Pos[2]), Upright(ang), Vector3.Zero);
            }
            if (StepsOn) StepsAgain();   // step by step: back near its spot, its steps from the first
            if (show) DrawCross(drill);   // the aim shown: the green cross (your view is not turned to it: the body would lean)
            nadeWait = true;
            attemptEnd = Clock.AddSeconds(25);
        });
    }

    // Finish() of a situation or an aim drill, in a session
    void SessionFinish(string outcome, double alive)
    {
        if (cur == null) return;
        bool ok;
        int pts = 0;
        string detail;
        if (cur.Kind == "momentum") (ok, pts, detail) = MoResult();
        else if (cur.Kind == "aim" && drill?.Mode == "crossfire") (ok, pts, detail) = CfResult();
        else if (cur.Kind == "aim" && drill?.Mode == "prefire")
        {
            ok = outcome == "cleared" || (aimOrder.Count >= 3 && frags >= aimOrder.Count - 1 && outcome != "dead");   // all, or all but one
            var el = (Server.TickCount - t0) / 64.0;
            // its time against the route's reference (23/10, the user: "les points récompensent surtout les kills. Ajouter le
            // temps (prefire)"): 100 at it, 10 more each second under it, none past it by 10 s
            var par = PrePar();
            var fast = ok ? (int)Math.Clamp(100 + 10 * (par - el), 0, 250) : 0;
            pts = frags * 30 + aimHs * 15 + (ok ? 100 + fast : 0) + UtilPts;
            detail = $"{frags}/{aimOrder.Count}{(ok ? $" · {el.ToString("F1", CultureInfo.InvariantCulture)} s ({F("reference {s} s", "s", Math.Round(par))}: +{fast})" : "")} · {aimHs} HS"
                     + (preMoved > 0 ? $" · {Tn(preMoved, "{n} stepped off its angle", "{n} stepped off their angles")}" : "") + UtilDetail();
        }
        else if (cur.Kind == "aim" && drill?.Mode == "range")
        {
            ok = frags >= drill.Goal;
            var avg = reacts.Count > 0 ? reacts.Average() : 0;
            pts = frags * 12 + aimHs * 8 + (int)Math.Max(0, (1.5 - avg) * 4 * frags) - deaths * 20;
            pts = Math.Max(0, pts) + (ok ? 100 : 0);
            detail = $"{Tn(frags, "{n} kill", "{n} kills")} · {(reacts.Count > 0 ? $"{F("{s} s each", "s", avg.ToString("F2", CultureInfo.InvariantCulture))} · " : "")}"
                     + $"{(frags > 0 ? 100 * aimHs / frags : 0)}% HS{(deaths > 0 ? $" · {Tn(deaths, "{n} death", "{n} deaths")}" : "")}";
        }
        else if (cur.Kind == "aim" && drill?.Mode == "defend")
        {
            // its waves (29/10): the one under way at the end counts if it took the site, or if all of it is down
            var faced = wavesFaced; var heldW = wavesHeld;
            if (waveLost) faced++;
            else if (waveKills > 0 && !Attackers().Any(Up)) { faced++; heldW++; }
            // one wave faced and held is the site kept (lab 24: A's waves come 1 to 3 in 90 s, 1 held of 1 with no death failed)
            // held by the weapon you hold against their rifles (30/10, the user: "si déjà j'en gagne plus de la moitié quand je
            // suis au Max 7 et au moins la moitié quand je suis au pistolet contre des AK, ben, c'est quand même réussi ... à la
            // M4, oui, il faut que j'en gagne une écrasante majorité ... 5 sur 6"): a shotgun more than half, a pistol half, a
            // rifle 5 of 6, an AWP 3 of 4; more kills than deaths with a rifle or an AWP
            var cls = drill.Id.Split(':').LastOrDefault() ?? "";
            var need = cls switch { "close" => faced / 2 + 1, "pistol" => (faced + 1) / 2, "rifle" => (faced * 5 + 5) / 6, _ => (faced * 3 + 3) / 4 };
            ok = faced >= 1 && heldW >= need && (cls is "close" or "pistol" || frags >= deaths);   // 03/10: 15 frags for 11 deaths never counted
            // the time the site was kept from them (23/10, the user: "ajouter ... le retard imposé (défense)"): 3 points a
            // second no attacker stood on it; 100 a wave held
            var held = defHeld / 64;
            pts = Math.Max(0, frags * 40 + aimHs * 15 - deaths * 50 - plants * 60) + 3 * held + 100 * heldW + UtilPts;
            var perWave = faced > 0 ? (frags / (double)faced).ToString("F1", CultureInfo.InvariantCulture) : "0";
            detail = $"🌊 {F("{h} waves held of {n}", "h", heldW, "n", faced)} · {F("{k} kills ({p} a wave)", "k", frags, "p", perWave)} · {Tn(deaths, "{n} death", "{n} deaths")} · {aimHs} HS{(plants > 0 ? $" · {Tn(plants, "{n} plant", "{n} plants")}" : "")}"
                     + $" · 🛡 {F("site kept {s} s of {t}", "s", held, "t", Math.Max(held, (Server.TickCount - t0) / 64))}" + UtilDetail();
        }
        else if (cur.Kind == "aim")
        {
            var n = Math.Max(1, aimOrder.Count);
            ok = outcome != "dead" && (reacts.Count == n || (n >= 3 && reacts.Count >= n - 1));
            if (drill?.Id.StartsWith("wallbang") == true) ok = reacts.Count * 2 >= n;   // half of them through the wall (06/10: no retry for playing it another way)
            foreach (var r in reacts) pts += 50 + (int)Math.Max(0, 50 * (1.2 - r) / 1.2);
            pts += aimHs * 20 + (ok ? 100 : 0);
            detail = reacts.Count > 0 ? $"{reacts.Count}/{aimOrder.Count} · {F("{s} s on average", "s", reacts.Average().ToString("F2", CultureInfo.InvariantCulture))} · {aimHs} HS" : T("no kill");
        }
        else
        {
            outcome = SitOutcome(outcome);   // a kill or a trade is needed (04/10); the bomb's end is the round's
            ok = outcome is "won" or "survived" or "traded" or "kill" || BombWon(outcome);
            pts = (outcome == "won" || BombWon(outcome) ? 300 : outcome == "survived" ? 200 : outcome is "traded" or "kill" ? 120 : 0) + 25 * kills + UtilPts;
            detail = SitDetail(alive) + UtilDetail();
        }
        DrillDone(ok, outcome, pts, detail);
    }

    void DrillDone(bool ok, string outcome, int pts, string detail)
    {
        if (sess == null || drill == null) return;
        StFinish(outcome, cur != null ? (Server.TickCount - t0) / 64.0 : 0);   // every drill's end comes here (a self-test notes it)
        phase = "done";
        ClearLine();
        if (drill.Id.StartsWith("wallbang")) CfGlowOff();
        ExecClean();
        if (cam != null) CamStop();
        nadeStage = "";
        if (ok) { streak++; okN++; } else streak = 0;
        var mult = ok ? 1 + 0.1 * Math.Min(5, streak - 1) : 1.0;
        pts = (int)Math.Round(pts * mult);
        points += pts;
        doneN++;
        var di = sessDone.FindIndex(x => x.d == drill);   // the recap: each drill's last try
        if (di >= 0) sessDone[di] = (drill, ok, outcome); else sessDone.Add((drill, ok, outcome));
        var rec = new Dictionary<string, object> { ["session"] = sess.Id, ["drill"] = drill.Id, ["kind"] = drill.Kind, ["map"] = drill.Map, ["ok"] = ok,
            ["outcome"] = outcome, ["points"] = pts, ["detail"] = detail, ["try"] = tries + 1, ["level"] = drill.Level, ["t"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds() };
        if (drill.Kind == "nade" && nadePops.Count > 0 && drill.Target != null) { rec["pops"] = nadePops.ToList(); rec["target"] = drill.Target; }
        if (drill.Mode is "crossfire" or "momentum") { rec["mode"] = drill.Mode; rec["variant"] = drill.Variant; foreach (var (k, x) in drillExtra) rec[k] = x; }
        Write(rec);
        var st = streak >= 2 ? $" · 🔥 x{mult.ToString("F1", CultureInfo.InvariantCulture)}" : "";
        var shown = Shown(outcome);
        Html(ok ? $"<font color='#5ad15a'>✔ {shown}</font> +{pts}{st}<br>{detail}<br>⭐ {points}"
                : $"<font color='#ff5a5a'>✘ {shown}</font><br>{detail}<br>⭐ {points}", 3);
        All($"{(ok ? "\x04✔" : "\x02✘")} {drill.Title}\x01 · {shown.ToLower()} · {detail} · +{pts} ({F("total {n}", "n", points)}){st}");
        tries++;
        var again = !ok && outcome != "skipped" && tries < 2 && Clock < blockEnd && drill.Mode is not ("range" or "crossfire" or "momentum");   // a miss: once more right away (Crossfire's and Momentum's reps are their own)
        var g = ++sessGen;
        AddTimer(3.5f, () =>
        {
            if (g != sessGen || sess == null) return;
            if (again && drill != null) RunDrill(drill); else NextDrill();
        });
    }

    void SkipDrill()
    {
        if (sess == null || drill == null) return;
        tries = 2;
        DrillDone(false, "skipped", 0, "");
    }

    void EndSession(bool early = false)
    {
        if (sess == null) return;
        Write(new Dictionary<string, object> { ["session"] = sess.Id, ["end"] = true, ["points"] = points, ["drills"] = doneN, ["ok"] = okN,
            ["early"] = early, ["t"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds() });
        var wasTest = selftest;   // a self-test's drills are never yours to play again (!again)
        StOff();
        Html($"<font color='#e0a030'>🏁 {T("SESSION DONE")}</font><br><font class='fontSize-l'>{points} pts</font><br>{F("{ok}/{n} drills ✔", "ok", okN, "n", doneN)}<br><font class='fontSize-s'>{T("the recap is in the chat: !again to play some again")}</font>", 10);
        All($"{T("Session done")}: {points} pts · {F("{ok}/{n} drills ✔", "ok", okN, "n", doneN)} — {T("your progress is in the app.")}");
        if (!wasTest) { lastSess = sess; lastDone.Clear(); lastDone.AddRange(sessDone); }
        for (int i = 0; i < lastDone.Count; i++)
        {
            var (d, ok, o) = lastDone[i];
            foreach (var h in Humans()) h.PrintToChat($" {(ok ? "\x04✔" : "\x02✘")} {i + 1}\x01 {d.Title} · {Shown(o).ToLower()}");
        }
        if (lastDone.Count > 0) All(T("Again: !again and a number (one drill), !again missed (the missed ones), !again all (the whole session)."));
        // 13/10, the focus block's recap: what comes back (the app's boxes: a miss is due at the next session there)
        var missed = lastDone.Count(x => !x.ok && x.outcome != "skipped");
        if (missed > 0) All(Tn(missed, "{n} missed drill comes first next time you train there", "{n} missed drills come first next time you train there"));
        ClearLine();
        if (cam != null) CamStop();
        Prac(false);
        SetMain("");
        sess = null; drill = null; cur = null; phase = "idle"; bots.Clear(); builtFor = null; sessGen++; paused = false;
        Zombie(false);
        BotStop(false);   // a boost's (28/10)
        DontShoot(false);
        Ammo(false);
        Server.ExecuteCommand("bot_quota 0");   // or the game adds the last drill's count again
        Server.ExecuteCommand("bot_kick");
        if (!wasTest && Humans().Any()) AddTimer(1.5f, () => { if (sess == null) SandboxOn(null); });   // the map yours now (19/10)
    }

    void Write(Dictionary<string, object> o) => Append(selftest ? StFile(".results.jsonl") : "results.jsonl", JsonSerializer.Serialize(o));   // a self-test: never your progress

    Dictionary<string, object?> SessionBeat() => sess == null ? new() : new()
    {
        ["session"] = sess.Id, ["block"] = blockIdx >= 0 && blockIdx < sess.Blocks.Count ? sess.Blocks[blockIdx].Kind : null,
        ["drill"] = drill?.Title, ["points"] = points, ["ok"] = okN, ["done"] = doneN, ["streak"] = streak,
        ["left"] = blockEnd > Clock ? (int)((paused ? blockEnd + (Clock - pausedAt) : blockEnd) - Clock).TotalSeconds : 0,
        ["paused"] = paused,
    };
}
