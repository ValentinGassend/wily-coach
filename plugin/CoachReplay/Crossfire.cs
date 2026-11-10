// Crossfire (13/10, the user: "simule de vrais duels avec des bots utilisant des mouvements réalistes pour travailler le
// counter-strafing et la tenue d'angles + spray practice: two bots picking the same angle at 2 different positions and
// 2 different timings, kill the first and the second with one and only spray, 30 bullets at most without stop
// shooting"). It replaces the aim map at the warm-up's start, on the session's real map (crossfire.py builds the drills
// from the base's duels). A drill is a series of reps:
// - hold: you on a spot the base holds, crosshair on its angle; an enemy comes out with a real player's peek (his way,
//   his speed, his stops, every 2 ticks), after a wait that changes each time, and fights you once it has seen you a
//   player's reaction time (the bots' level);
// - peek: the other way round: you start where a real peek started, the enemy holds the angle; your shots fired while
//   moving are counted (counter-strafe);
// - spray: two enemies come out nearly on one line from your spot, one deeper, each with the real peek that brought a
//   player there, the second 0.3 to 0.9 s after the first; they don't shoot. Both must die in one spray: no gap
//   between two bullets longer than the gun's rate, 30 bullets (the magazine; it is not refilled).
// 14/10, his test on Inferno: an enemy off its way (its peek over, hit, or close to you) stops where it is and fights you
// there, never roams away on the game's AI ("le bot il s'en va"); at each rep of a hold or a peek, the enemy glows
// through the walls a moment first, where it is ("pour savoir quel angle je dois regarder").
// Measured: duels won, headshots, how far your crosshair was from the enemy's head when he came into your sight, the
// time to kill from then, the shots fired while moving; for the spray: the clean sprays, their bullets, why one failed.
using System.Globalization;
using System.Numerics;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Utils;

namespace CoachReplay;

public partial class CoachReplay
{
    bool CfSpray => drill is { Mode: "crossfire", Variant: "spray" };

    int cfRep, cfWon, cfLost, cfNone, cfHs, cfRepAt, cfSeenAt, cfShots, cfMoving;
    int cfPeekAt;   // a hold's enemy leaves its start then (its wait over)
    float cfOff = -1;
    bool cfResolved = true;
    readonly HashSet<int> cfHiding = new();   // bots taken away between two reps: their deaths count for nothing
    // 14/10, his third test: "il spawne en face de moi" (a peek's start in your sight, the bot shooting before it moved):
    // a start where you and it see each other at once is dropped for the drill and the rep starts again from another
    readonly HashSet<object> cfBad = new();
    object? cfCur;
    int cfTries;
    readonly List<(bool won, float off, double ttk)> cfLog = new();
    // the spray: when each enemy comes out, the spray's first and last bullet (ticks), its bullets, the kills
    int spAppear1, spAppear2, spFirst, spLast, spBullets, spKills, spKill1At, spMag = 30, spEmptyAt = -1;
    // when you first saw each of the pair (the game's spotting), and the pairs one of which never came into your sight this
    // drill (30/10, the user on Train's A Site, 0/5 "trop lent" like the test: its 3 s ran from a guessed moment, the second
    // one planted behind its cover still unseen)
    readonly Dictionary<int, int> spSeen = new();
    // when each of the pair sets off: its spotting before that is the last rep's, still on it (30/10, his review: Ramp and
    // Apps "trop lent" with 0 bullets, both counted seen the tick the rep began, their 3 s gone before they came out)
    readonly Dictionary<int, int> spGo = new();
    bool spWasted;   // bullets fired before either came out this rep: the magazine filled again at the first's sight
    int spUnseen;
    readonly List<CBaseModelEntity> cfGlow = new();   // the enemy's glow at a rep's start (two props: a relay and the glow)
    int cfGlowN, cfGlowSlot = -1, cfGlowUntil;   // whose glow, until when (it is on your radar meanwhile)
    readonly List<(string outcome, int bullets, double transfer)> spLog = new();
    const int SprayGap = 12;   // ticks between two bullets beyond which the spray stopped (a rifle fires every 6 to 7)
    const float MovingShot = 75f;   // u/s: over 34 % of a rifle's speed the shot is inaccurate (Leetify's measure)
    readonly Dictionary<string, object> drillExtra = new();   // a drill's measures, written with its result
    // a peek's moment never one to learn (23/10, the user: "délais de peek variables pour casser le prefire au timing"):
    // early, on time or late, never twice the same in a row
    int cfLastWait = -1;
    // the base's moves (23/10, the user: "peeks des bots avec les mouvements de la base (jiggle, wide swing)"): its real
    // peek as it was (a wide swing when it was one), or a jiggle first: it shows itself, goes back out of your sight along
    // its way, waits a moment, then comes. 1 armed, 2 going back, 3 waiting, 0 none
    int cfJig, cfJigAt, cfJigLen;
    float cfJigF;
    readonly HashSet<int> cfJiggling = new();   // the bots it moves itself meanwhile (OnTick leaves them alone)
    string cfKind = "";

    void RegisterCrossfire()
    {
        RegisterEventHandler<EventWeaponFire>((e, _) => { CfShot(e.Userid, e.Weapon ?? ""); return HookResult.Continue; });
    }

    Scenario CrossfireScenario(Drill d)
    {
        var s = new Scenario { Id = d.Id, Map = d.Map, Kind = "aim", Title = d.Title, Team = d.Team };
        var me = d.Me ?? new Spot();
        s.Players.Add(new Track { Sid = "me", Name = "you", Team = d.Team, Me = true, Hp = 100, Armor = d.Armor, Helmet = d.Helmet, Weapons = d.Weapons,
            Active = d.Weapons.LastOrDefault(), Path = new[] { me.Pos[0], me.Pos[1], me.Pos[2], me.Ang[1], me.Ang[0] } });
        var foe = 5 - d.Team;
        var w = d.BotWeapons;
        Track Bot(int k, string name, float[] path, bool hold, bool still) => new()
        {
            // with pistols no helmet: a pistol round's (30/10, his review: "enlève les casques des joueurs en face"); its knife
            // aside (31/10: counted, it kept every helmet on, his head hits 64 damage)
            Sid = $"cf{k}", Name = name, Team = foe, Hp = 100, Armor = 100, Helmet = !w.Where(x => !x.Contains("knife") && !x.Contains("grenade") && !x.Contains("flash") && !x.Contains("molotov")).All(x => Pistols.Any(p => x.EndsWith(p))), Weapons = w, Active = w.LastOrDefault(),
            Path = path, Hold = hold, Still = still,
        };
        float[] At(Spot b) => new[] { b.Pos[0], b.Pos[1], b.Pos[2], b.Ang[1], b.Ang[0] };
        if (d.Variant == "hold" && d.Tracks.Count > 0)
        {
            var tr = d.Tracks[Rng.Next(d.Tracks.Count)];
            s.Players.Add(Bot(0, tr.Zone, tr.Path, false, false));
        }
        else if (d.Variant == "peek" && d.Bots.Count > 0)
            s.Players.Add(Bot(0, d.Bots[0].Zone ?? "?", At(d.Bots[0]), true, false));
        else if (d.Variant == "spray" && d.Bots.Count >= 2)
            for (int k = 0; k < 2; k++) s.Players.Add(Bot(k, d.Bots[k].Zone ?? "?", d.Tracks.Count > k ? d.Tracks[k].Path : At(d.Bots[k]), false, false));
        // the doors on every real peek's way open, as in their matches (a rep takes any of them)
        foreach (var tr in d.Tracks)
            for (int i = 0; i + 2 < tr.Path.Length; i += 20) s.Trail.Add(new[] { tr.Path[i], tr.Path[i + 1], tr.Path[i + 2] });
        return s;
    }

    // Place() is done: the counters from zero; the spray's enemies wait (dead) for their moment
    void CfPlaced()
    {
        cfRep = cfWon = cfLost = cfNone = cfHs = cfShots = cfMoving = 0;
        cfLog.Clear(); spLog.Clear(); cfHiding.Clear(); drillExtra.Clear(); cfBad.Clear(); spUnseen = 0; cfPinned.Clear(); cfSeek.Clear();
        cfResolved = true;
        aimOrder.Clear();
        aimOrder.AddRange(bots.Keys);
        CfGlowOff();
        if (!CfSpray && bots.FirstOrDefault(b => b.Value.Sid == "cf0") is { Value: not null } kv && Utilities.GetPlayerFromSlot(kv.Key) is { IsValid: true } c0)
            CfGlowOn(c0, 3.2f);   // the countdown's 3 s: where the first one waits
    }

    void CfGo() => CfNext();

    // the next rep, or the drill's end
    void CfNext()
    {
        if (drill == null || cur == null || phase != "live") return;
        if (cfRep >= Math.Max(1, drill.Count) || (Server.TickCount - t0) / 64f >= drill.Seconds) { Finish("done"); return; }
        cfRep++;
        cfResolved = false;
        cfTries = 0;
        foreach (var sl in cfSeek) free.Remove(sl);
        cfSeek.Clear();
        cfPlantAt.Clear(); cfStrict.Clear();
        CfGlowOff();
        cfRepAt = Server.TickCount;
        cfSeenAt = -1;
        cfOff = -1;
        var me = cur.Players.First(p => p.Me);
        var at = Pos(me, 0);
        var face = Upright(Ang(me, 0));
        if (drill.Variant == "peek" && drill.Tracks.Count > 0 && cfRep > 1)
        {   // where a real peek started, turned the way it went
            var tr = CfPick(drill.Tracks);
            cfCur = tr.Path;
            at = new Vector3(tr.Path[0], tr.Path[1], tr.Path[2]);
            face = new Vector3(0, tr.Path[3], 0);
            // turned toward its zone, not its head (30/10, the user: "je suis quasiment dos à lui quand je spawn ... que je
            // regarde plus ou moins dans sa zone, pas forcément exactement là où il y a sa tête"): 25 deg off it at most
            if (drill.Bots.Count > 0 && drill.Bots[0].Pos is { Length: >= 2 } hp0)
                face = new Vector3(0, MathF.Atan2(hp0[1] - at.Y, hp0[0] - at.X) * 180f / MathF.PI + (float)(Rng.NextDouble() * 50.0 - 25.0), 0);
        }
        else if (drill.Variant == "peek" && drill.Tracks.Count > 0)
            cfCur = drill.Tracks[0].Path;
        foreach (var h in Humans())
        {
            var fresh = !h.PawnIsAlive;
            if (fresh) { h.Respawn(); Loadout(h, me, 100); }
            var pw = h.PlayerPawn.Value;
            if (pw == null) continue;
            pw.Teleport(at, face, Vector3.Zero);
            if (!fresh)
            {   // alive: the same guns (no draw time), full again
                pw.Health = 100;
                Utilities.SetStateChanged(pw, "CBaseEntity", "m_iHealth");
                FullMag(h);
            }
        }
        protectUntil = Server.TickCount + 32;
        // hold: you hold the angle, they come to you (30/10, the user: "dans ces situations là de tenir l'angle, je ne suis pas
        // censé bouger et c'est les ennemis qui sont censés me piquer ... empêche moi de me déplacer"): held on its spot all
        // the rep; peek: still while the enemy glows (else "je peux le pré-shot"), then yours to peek
        // pinned on the ground, its speed held at none (the slowdown of a hit), not frozen: frozen he was "comme si j'étais en
        // l'air ... ma visée est imprécise, comme si j'étais en noclip" (30/10, the air's spread)
        cfPinUntil = drill.Variant == "hold" ? int.MaxValue : drill.Variant == "peek" && cfRep > 1 ? Server.TickCount + 96 : 0;
        foreach (var h in Humans()) if (h.PlayerPawn.Value is { } hp) Freeze(hp, false);
        if (drill.Variant == "hold") CfPeeker();
        else if (drill.Variant == "peek") CfHolder();
        else CfSprayArm();
    }

    // hold: the enemy comes out with one of the real peeks, after a wait of its own
    void CfPeeker()
    {
        if (drill == null || cur == null || drill.Tracks.Count == 0) return;
        var (sl, t) = bots.FirstOrDefault(b => b.Value.Sid == "cf0");
        var c = t == null ? null : Utilities.GetPlayerFromSlot(sl);
        if (t == null || c == null || !c.IsValid) return;
        var first = cfRep == 1;   // the countdown showed this one where it waits: the same way
        var shown = first && cfTries == 0 ? drill.Tracks.FirstOrDefault(x => x.Path == t.Path) : null;
        var tr = shown ?? CfPick(drill.Tracks);
        // a start you already see from your spot is no peek (23/10 eve, the user on Mirage's Window: "ils ne sont pas
        // cachés à la base ... derrière absolument rien ... ils bougent pas"; the base's T had been unseen there behind the
        // round's smokes): dropped, another one, the bullet's line from your eyes to its head and chest
        for (int k = 0; k < drill.Tracks.Count && (CfStartSeen(tr) || !CfEverSeen(tr)); k++)
        {
            cfBad.Add(tr.Path);
            Log("crossfire: a start in plain sight or a peek never in it, dropped ({n})", cfBad.Count);
            tr = CfPick(drill.Tracks);
        }
        cfCur = tr.Path;
        t.Path = tr.Path;
        t.Hold = t.Still = false;   // planted at the last rep's end: on its way again
        t.TrackNades = new();
        t.NadeNext = 0;
        var b0 = (cfLastWait + 1 + Rng.Next(2)) % 3;
        cfLastWait = b0;
        var rnd = (float)Rng.NextDouble();
        // checked in sight first (0.6 s); it glows 1.5 s first: then it comes, early, on time or late
        var wait = first ? 0.8f + rnd * 0.8f : b0 switch { 0 => 0.35f + 0.5f * rnd, 1 => 1.4f + 1.0f * rnd, _ => 3.0f + 1.8f * rnd };
        cfJig = !first && difficulty >= 1 && t.Frames > 40 && Rng.NextDouble() < 0.35 ? 1 : 0;
        cfJiggling.Clear();
        cfKind = cfJig == 1 ? "jiggle" : tr.Kind;
        t.Start = (Server.TickCount - t0) / (float)cur.Step + wait * 64f / cur.Step;
        cfPeekAt = Server.TickCount + (int)(wait * 64f);
        if (!c.PawnIsAlive) c.Respawn();
        Loadout(c, t);
        free.Remove(sl); contact.Remove(sl); engaged.Remove(sl); sawYou.Remove(sl); gone.Remove(t.Sid);
        if (c.PlayerPawn.Value is { } pw) { pw.Teleport(Pos(t, 0), Upright(Ang(t, 0)), Vector3.Zero); Freeze(pw, false); UnpinPawn(pw); }   // it waits on its start, then walks its way
        cfPinned.Remove(sl);
        c.PlayerName = tr.Zone;
        Utilities.SetStateChanged(c, "CBasePlayerController", "m_iszPlayerName");
        if (!first) CfGlowOn(c, 1.5f);
    }

    // a peek that comes into your sight from your spot at some point of its way (30/10, the user: "parfois j'ai pas de duel
    // ... j'ai vu aucun ennemi"): its head or chest traced from your eyes every eighth of its frames
    bool CfEverSeen(EntryTrack tr)
    {
        var h = Humans().FirstOrDefault(x => x.PawnIsAlive);
        var me = h?.PlayerPawn.Value;
        var m = cur?.Players.FirstOrDefault(p => p.Me);
        var n = tr.Path.Length / 5;
        if (me == null || m == null || n < 2) return true;
        var at = Pos(m, 0);
        var eye = new CounterStrikeSharp.API.Modules.Utils.Vector(at.X, at.Y, at.Z + 64f);
        var shot = new TraceOptions { InteractsWith = Masks.ShotBrushOnly };
        for (int k = 0; k < n; k += 8)
            foreach (var up in new[] { 64f, 50f })
                if (Trace.TraceEndShape(eye, new CounterStrikeSharp.API.Modules.Utils.Vector(tr.Path[k * 5], tr.Path[k * 5 + 1], tr.Path[k * 5 + 2] + up), me, shot).Fraction > 0.98f)
                    return true;
        return false;
    }

    bool CfStartSeen(EntryTrack tr)
    {
        var h = Humans().FirstOrDefault(x => x.PawnIsAlive);
        var me = h?.PlayerPawn.Value;
        var m = cur?.Players.FirstOrDefault(p => p.Me);
        if (me == null || m == null || tr.Path.Length < 3) return false;
        var at = Pos(m, 0);
        var eye = new CounterStrikeSharp.API.Modules.Utils.Vector(at.X, at.Y, at.Z + 64f);
        var shot = new TraceOptions { InteractsWith = Masks.ShotBrushOnly };
        // its body as the game spots it (7 heights, its shoulders), not its head alone (23/10 eve: Window's starts traced
        // hidden by the head and the chest, spotted by the game at once)
        float dx = tr.Path[1] - at.Y, dy = -(tr.Path[0] - at.X), n = MathF.Max(1f, MathF.Sqrt(dx * dx + dy * dy));
        foreach (var (up, side) in new[] { (66f, 0f), (58f, 0f), (48f, 0f), (38f, 0f), (28f, 0f), (18f, 0f), (8f, 0f), (52f, 12f), (52f, -12f) })
            if (Trace.TraceEndShape(eye, new CounterStrikeSharp.API.Modules.Utils.Vector(tr.Path[0] + side * dx / n, tr.Path[1] + side * dy / n, tr.Path[2] + up), me, shot).Fraction > 0.98f) return true;
        return false;
    }

    // peek: the enemy back on the angle it holds, its reaction from zero
    void CfHolder()
    {
        var (sl, t) = bots.FirstOrDefault(b => b.Value.Sid == "cf0");
        var c = t == null ? null : Utilities.GetPlayerFromSlot(sl);
        if (t == null || c == null || !c.IsValid) return;
        if (!c.PawnIsAlive) c.Respawn();
        Loadout(c, t);
        if (drill?.Bots.Count > 0) { var b = drill.Bots[0]; t.Path = new[] { b.Pos[0], b.Pos[1], b.Pos[2], b.Ang[1], b.Ang[0] }; }
        t.Hold = true; t.Still = false;
        contact.Remove(sl); sawYou.Remove(sl); gone.Remove(t.Sid); free.Remove(sl);
        // held on its angle by its speed, on the ground (frozen it shot as in the air, 30/10, the user: "quand tu frises les
        // bots sur un pic, ils ont le problème réciproque, c'est-à-dire qu'ils sont en l'air et du coup, ils sont pas précis")
        if (c.PlayerPawn.Value is { } pw) { pw.Teleport(Pos(t, 0), Upright(Ang(t, 0)), Vector3.Zero); Freeze(pw, false); }
        cfPinned.Add(sl);
        if (cfRep > 1) CfGlowOn(c, 1.5f);   // the first: the countdown showed it
    }

    // spray: a pair of spots, each enemy on the real peek that brought a player there, the moments they come out
    void CfSprayArm()
    {
        if (drill == null || cur == null) return;
        var pairs = Enumerable.Range(0, Math.Max(1, drill.Bots.Count / 2)).ToList();
        var p = CfPick(pairs, i => $"pair{i}");
        cfCur = $"pair{p}";
        var deep = Rng.Next(2);   // the near one first, or the deep one
        var now = Server.TickCount;
        var d1 = 0.7 + Rng.NextDouble() * 0.5;   // after the check in sight (0.6 s)
        var d2 = d1 + 0.3 + Rng.NextDouble() * 0.6;   // 14/10: "à des timings différents"
        spGo.Clear();
        foreach (var (sl, t) in bots)
        {
            var k = t.Sid == "cf1" ? 1 : 0;
            var idx = 2 * p + (k ^ deep);
            if (idx >= drill.Bots.Count) continue;
            var b = drill.Bots[idx];
            t.Path = idx < drill.Tracks.Count && drill.Tracks[idx].Path.Length >= 10 ? drill.Tracks[idx].Path : new[] { b.Pos[0], b.Pos[1], b.Pos[2], b.Ang[1], b.Ang[0] };
            t.Hold = t.Still = false;
            var delay = k == 0 ? d1 : d2;
            t.Start = (now - t0) / (float)cur.Step + (float)delay * 64f / cur.Step;
            spGo[sl] = now + (int)(delay * 64);
            // seen about 1.25 s after it sets off (its peek starts 40 frames before the other team saw it)
            var seen = now + (int)(delay * 64) + Math.Min(80, Math.Max(0, t.Frames - 1) * cur.Step);
            if (k == 0) spAppear1 = seen; else spAppear2 = seen;
            var c = Utilities.GetPlayerFromSlot(sl);
            if (c == null || !c.IsValid) continue;
            if (!c.PawnIsAlive) c.Respawn();
            Loadout(c, t);
            free.Remove(sl); contact.Remove(sl); engaged.Remove(sl); sawYou.Remove(sl); gone.Remove(t.Sid);
            if (c.PlayerPawn.Value is { } pw) { pw.Teleport(Pos(t, 0), Upright(Ang(t, 0)), Vector3.Zero); Freeze(pw, false); UnpinPawn(pw); }
            cfPinned.Remove(sl);
        }
        if (spAppear2 < spAppear1) (spAppear1, spAppear2) = (spAppear2, spAppear1);
        spFirst = spLast = spKill1At = spEmptyAt = -1;
        spWasted = false;
        spSeen.Clear();
        spBullets = spKills = 0;
        var w = Humans().FirstOrDefault(x => x.PawnIsAlive)?.PlayerPawn.Value?.WeaponServices?.ActiveWeapon.Value;
        spMag = w is { IsValid: true } && (w.VData?.MaxClip1 ?? 0) > 0 ? w.VData!.MaxClip1 : 30;   // an M4A1-S: 20
    }

    // an enemy off its way (its peek over, hit, close to you, fighting off it): it stops there and fights you, turned to
    // you; the spray's stands still (it never fires). Never the game's AI: it went away (14/10)
    bool CfPlant(CCSPlayerController c, Track t)
    {
        var pw = c.PlayerPawn.Value;
        if (pw?.AbsOrigin == null) return false;
        // a hold's peeker that saw you before you see it: on along its peek till you do (30/10, his hold on Cache's Forklift:
        // 1 duel in 6, each peeker planted behind its cover the tick it saw you, never out, the rep dropped 10 s later)
        // in your sight: the game's spotting (a bullet's line asked too kept them walking past Train's fences and grates, 4 reps of
        // 6 with no duel, 31/10); planted with no line and no shot 2 s on, it walks on (CfPlantWatch)
        if (drill?.Variant == "hold" && !CfSpray && Humans().FirstOrDefault(x => x.PawnIsAlive) is { } hv
            && (pw.EntitySpottedState.SpottedByMask[hv.Slot / 32] & (1u << (hv.Slot % 32))) == 0 && cur != null)
        {
            if ((Server.TickCount - t0) / (float)cur.Step - t.Start < t.Frames - 2) return true;   // not planted, not freed: its recorded peek goes on
            // its peek over, still unseen: on to you by the map's mesh till you see it, then it stops and fights (30/10, his
            // review on Inferno's holds: "il n'y a personne qui se présentait devant moi", planted behind its cover, "no duel")
            if (cfSeek.Add(c.Slot)) { free.Add(c.Slot); Log("crossfire: {n}'s peek over unseen, on to you", t.Name); }
            return true;
        }
        var me = Humans().Select(h => h.PlayerPawn.Value?.AbsOrigin).FirstOrDefault(o => o != null);
        var at = new Vector3(pw.AbsOrigin.X, pw.AbsOrigin.Y, pw.AbsOrigin.Z);
        var yaw = me == null ? pw.EyeAngles?.Y ?? 0f : MathF.Atan2(me.Y - at.Y, me.X - at.X) * 180 / MathF.PI;
        t.Path = new[] { at.X, at.Y, at.Z, yaw, 0f };
        t.Hold = true;
        t.Still = CfSpray;
        Freeze(pw, false);   // held by its speed, on the ground (frozen: the air's spread on its shots)
        cfPinned.Add(c.Slot);
        if (drill?.Variant == "hold" && !CfSpray) cfPlantAt[c.Slot] = Server.TickCount;
        Log("plant {n}", t.Name);
        return true;
    }

    // the enemy through the walls a moment, where it is (a copy of its model that follows it and glows; 14/10: "mettre
    // en surbrillance à travers le mur où est le bot au tout début du round")
    void CfGlowOn(CCSPlayerController c, float secs)
    {
        CfGlowOff();
        var n = ++cfGlowN;
        cfGlowSlot = c.Slot;
        cfGlowUntil = Server.TickCount + (int)(secs * 64);
        // 14/10: made at once after the respawn of a bot killed the rep before, it had no model yet: nothing glowed
        AddTimer(0.15f, () => { if (n == cfGlowN && c.IsValid) CfGlowMake(c, n, secs - 0.15f); });
    }

    void CfGlowMake(CCSPlayerController c, int n, float secs)
    {
        try
        {
            var pw = c.PlayerPawn.Value;
            if (pw == null || !pw.IsValid) return;
            var model = pw.CBodyComponent?.SceneNode?.GetSkeletonInstance()?.ModelState.ModelName;
            if (string.IsNullOrEmpty(model))
                model = c.Team == CsTeam.Terrorist ? "characters/models/tm_phoenix/tm_phoenix.vmdl" : "characters/models/ctm_sas/ctm_sas.vmdl";
            var relay = Utilities.CreateEntityByName<CBaseModelEntity>("prop_dynamic");
            var glow = Utilities.CreateEntityByName<CBaseModelEntity>("prop_dynamic");
            if (relay == null || glow == null) return;
            relay.SetModel(model);
            relay.Spawnflags = 256u;
            relay.RenderMode = RenderMode_t.kRenderNone;
            relay.DispatchSpawn();
            glow.SetModel(model);
            glow.Spawnflags = 256u;
            glow.DispatchSpawn();
            glow.Glow.GlowColorOverride = System.Drawing.Color.FromArgb(255, 255, 80, 60);
            glow.Glow.GlowRange = 5000;
            glow.Glow.GlowRangeMin = 0;
            glow.Glow.GlowTeam = -1;
            glow.Glow.GlowType = 3;
            relay.AcceptInput("FollowEntity", pw, relay, "!activator");
            glow.AcceptInput("FollowEntity", relay, glow, "!activator");
            cfGlow.Add(relay);
            cfGlow.Add(glow);
            Log("glow {n} ({m}) {s} s", c.PlayerName, model, Math.Round(secs, 1));
            AddTimer(Math.Max(0.1f, secs), () => { if (n == cfGlowN) CfGlowOff(); });
        }
        catch (Exception e) { Log("glow: {m}", e.Message); }
    }

    void CfGlowOff()
    {
        foreach (var e in cfGlow) if (e.IsValid) e.Remove();
        cfGlow.Clear();
        cfGlowUntil = 0;
        cfGlowN++;   // one still to be made: not any more
    }

    // while it glows, the enemy is on your radar too (the game's own spotting, set each tick)
    void CfRadar()
    {
        if (cfGlowSlot < 0 || Server.TickCount > cfGlowUntil) return;
        var pw = Utilities.GetPlayerFromSlot(cfGlowSlot)?.PlayerPawn.Value;
        var h = Humans().FirstOrDefault();
        if (pw == null || !pw.IsValid || h == null) return;
        pw.EntitySpottedState.Spotted = true;
        pw.EntitySpottedState.SpottedByMask[h.Slot / 32] |= 1u << (h.Slot % 32);
        Utilities.SetStateChanged(pw, "CCSPlayerPawn", "m_entitySpottedState");
    }

    // a start not dropped yet for this drill (all dropped: any)
    T CfPick<T>(IList<T> xs, Func<T, object>? key = null)
    {
        key ??= x => x!;
        var ok = xs.Where(x => !cfBad.Contains(key(x))).ToList();
        return ok.Count > 0 ? ok[Rng.Next(ok.Count)] : xs[Rng.Next(xs.Count)];
    }

    // you and an enemy see each other the moment a rep starts (before anyone moved): that start is dropped, the rep
    // starts again from another one (4 tries at most)
    void CfStartCheck(int now)
    {
        if (drill == null || cfResolved || cfTries >= 4 || now - cfRepAt < 6 || now - cfRepAt > 40 || cfCur == null) return;
        // a hold's starts are judged when picked, by the bullet's lines to its body (CfStartSeen): the game's spotted masks
        // keep the last start's a few ticks after it was moved, and dropped start after start in a row (24/10, Mirage:
        // 130 drops in 7 minutes, every 6 ticks). A peek's starts are the ones its holder does not see, traced beforehand
        // (tools/crossfire_check.py): the same masks dropped all six of Nuke's Squeaky, 4 times a rep (24/10)
        if (drill.Variant is "hold" or "peek") return;
        var h = Humans().FirstOrDefault(x => x.PawnIsAlive);
        var me = h?.PlayerPawn.Value;
        if (h == null || me == null) return;
        var mine = me.EntitySpottedState.SpottedByMask;
        var seen = false;
        foreach (var (sl, t) in bots)
        {
            var pw = Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value;
            if (pw == null || pw.LifeState != (byte)LifeState_t.LIFE_ALIVE || gone.Contains(t.Sid)) continue;
            var theirs = pw.EntitySpottedState.SpottedByMask;
            if ((mine[sl / 32] & (1u << (sl % 32))) != 0 || (theirs[h.Slot / 32] & (1u << (h.Slot % 32))) != 0) seen = true;
        }
        if (!seen) return;
        cfBad.Add(cfCur);
        cfTries++;
        Log("crossfire: a start in sight, dropped ({n})", cfBad.Count);
        cfRepAt = now;
        cfSeenAt = -1;
        protectUntil = now + 32;
        if (drill.Variant == "hold") CfPeeker();
        else if (drill.Variant == "spray") CfSprayArm();
        else if (drill.Tracks.Count > 0)
        {
            var tr = CfPick(drill.Tracks);
            cfCur = tr.Path;
            foreach (var x in Humans())
                x.PlayerPawn.Value?.Teleport(new Vector3(tr.Path[0], tr.Path[1], tr.Path[2]), new Vector3(0, tr.Path[3], 0), Vector3.Zero);
            CfHolder();
        }
    }

    // a rep over: the enemies still standing taken away, so that none is seen moving to the next rep's start
    void CfHideLater()
    {
        var g = generation;
        AddTimer(0.45f, () =>
        {
            if (g != generation || phase != "live") return;
            foreach (var (sl, _) in bots)
                if (Utilities.GetPlayerFromSlot(sl) is { IsValid: true, PawnIsAlive: true } c && !(drill?.Variant == "peek"))
                { cfHiding.Add(sl); c.PlayerPawn.Value?.CommitSuicide(false, true); }
        });
    }

    // each tick of a crossfire drill: the moments, the first sight, the spray's rules, the screen
    int cfPinUntil;   // you held on your spot till then (a hold: its whole rep; a peek: while the enemy glows)
    readonly HashSet<int> cfPinned = new();   // bots held on their spot the same way (a peek's holder, a planted one)

    // a pin over: the full speed back at once (30/10, his review: "les premiers déplacements sont hyper lents" after a peek's
    // pin, the game's own slow-down left to come back by itself)
    static void UnpinPawn(CCSPlayerPawn? hp)
    {
        if (hp == null || hp.VelocityModifier >= 1f) return;
        hp.VelocityModifier = 1f;
        Utilities.SetStateChanged(hp, "CCSPlayerPawn", "m_flVelocityModifier");
    }
    bool cfMePinned;

    static void PinPawn(CCSPlayerPawn hp)
    {
        if (hp.LifeState != (byte)LifeState_t.LIFE_ALIVE) return;
        if (hp.VelocityModifier > 0f) { hp.VelocityModifier = 0f; Utilities.SetStateChanged(hp, "CCSPlayerPawn", "m_flVelocityModifier"); }
        if (hp.AbsVelocity is { } av && (av.X != 0f || av.Y != 0f)) hp.Teleport(null, null, new Vector3(0f, 0f, av.Z));
    }

    void CfPin()
    {
        foreach (var sl in cfPinned)
            if (Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value is { } bp) PinPawn(bp);
        if (cfResolved && drill?.Variant != "hold" || Server.TickCount >= cfPinUntil)
        {
            if (cfMePinned) { cfMePinned = false; foreach (var h in Humans()) UnpinPawn(h.PlayerPawn.Value); }
            return;
        }
        cfMePinned = true;
        foreach (var h in Humans())
            if (h.PlayerPawn.Value is { } hp) PinPawn(hp);
    }

    // a bullet's line from your eyes to its head or its chest, its walls only (players and smokes aside)
    static bool CfLine(CCSPlayerPawn? me, CCSPlayerPawn bot)
    {
        if (me?.AbsOrigin is not { } mo || bot.AbsOrigin is not { } bo) return false;
        var eye = new CounterStrikeSharp.API.Modules.Utils.Vector(mo.X, mo.Y, mo.Z + (me.ViewOffset?.Z ?? 64f));
        var top = bo.Z + (bot.ViewOffset?.Z ?? 64f);
        var shot = new TraceOptions { InteractsWith = Masks.ShotBrushOnly };
        try
        {
            foreach (var dz in new[] { 2f, 22f })
                if (Trace.TraceEndShape(eye, new CounterStrikeSharp.API.Modules.Utils.Vector(bo.X, bo.Y, top - dz), me, shot).Fraction > 0.98f) return true;
        }
        catch (Exception) { return true; }   // no trace: the game's spotting alone, as before
        return false;
    }

    // a hold's peeker planted in your sight by the game's spotting: no bullet's line to it and no shot 2 s on (spotted through
    // a gap, 30/10 Dust2's Pit): on to you again till a real line (31/10)
    readonly Dictionary<int, int> cfPlantAt = new();
    readonly HashSet<int> cfStrict = new();
    void CfPlantWatch()
    {
        if (cfPlantAt.Count == 0 || cfResolved) return;
        var hv = Humans().FirstOrDefault(x => x.PawnIsAlive);
        foreach (var (sl, at) in cfPlantAt.ToList())
        {
            if (Server.TickCount - at < 128) continue;
            cfPlantAt.Remove(sl);
            if (hv == null || !bots.TryGetValue(sl, out var t) || Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value is not { } pw
                || pw.LifeState != (byte)LifeState_t.LIFE_ALIVE || CfLine(hv.PlayerPawn.Value, pw)) continue;
            cfPinned.Remove(sl);
            t.Hold = false;
            UnpinPawn(pw);
            cfStrict.Add(sl);   // its next stop: a real line only
            if (cfSeek.Add(sl)) { free.Add(sl); Log("crossfire: {n} planted out of a bullet's line, on to you", t.Name); }
        }
    }

    // a hold's peekers on their way to you past their peek's end (CfPlant), each tick till you see them
    readonly HashSet<int> cfSeek = new();
    void CfSeekTick()
    {
        if (cfSeek.Count == 0) return;
        var hv = Humans().FirstOrDefault(x => x.PawnIsAlive);
        if (hv?.PlayerPawn.Value?.AbsOrigin is not { } mo) return;
        var goal = new Vector3(mo.X, mo.Y, mo.Z);
        foreach (var sl in cfSeek.ToList())
        {
            if (Utilities.GetPlayerFromSlot(sl) is not { IsValid: true, PawnIsAlive: true } c || c.PlayerPawn.Value is not { AbsOrigin: { } o } pw
                || !bots.TryGetValue(sl, out var t)) { cfSeek.Remove(sl); free.Remove(sl); continue; }
            var here = new Vector3(o.X, o.Y, o.Z);
            if ((pw.EntitySpottedState.SpottedByMask[hv.Slot / 32] & (1u << (hv.Slot % 32))) != 0 && (!cfStrict.Contains(sl) || CfLine(hv.PlayerPawn.Value, pw)))
            {   // in your sight: it stops there and fights you
                cfSeek.Remove(sl); free.Remove(sl);
                CfPlant(c, t);
                continue;
            }
            var to = new Vector2(goal.X - here.X, goal.Y - here.Y);
            if (navPts.Length > 0)
            {
                var st = NavSteer(sl, here, goal);
                if (NavClimb(sl, here) is { } lv) { pw.Teleport(null, null, lv); continue; }
                var ts = new Vector2(st.X - here.X, st.Y - here.Y);
                if (ts.Length() > 1f) to = ts;
            }
            var cv = pw.AbsVelocity is { } av ? new Vector2(av.X, av.Y) : Vector2.Zero;
            var want = to.Length() < 1f || new Vector2(goal.X - here.X, goal.Y - here.Y).Length() < 150f ? Vector2.Zero : Vector2.Normalize(to) * 200f;
            var dv = want - cv;
            if (dv.Length() > 24f) dv = Vector2.Normalize(dv) * 24f;
            var v = PastFriction(cv + dv, (pw.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0);
            var yaw = MathF.Atan2(goal.Y - here.Y, goal.X - here.X) * 180f / MathF.PI;
            SetEyes(pw, new Vector3(0f, yaw, 0f));
            pw.Teleport(null, new Vector3(0f, yaw, 0f), new Vector3(v.X, v.Y, pw.AbsVelocity?.Z ?? 0f));
        }
    }

    void CfTick(float el)
    {
        CfPin();
        CfSeekTick();
        CfPlantWatch();
        if (drill == null || cur == null) return;
        var now = Server.TickCount;
        CfStartCheck(now);
        CfJiggleTick(now);
        if (!cfResolved)
        {
            if (CfSpray)
            {
                // its magazine to the last bullet: a kill on the 29th or 30th counts (30/10, his review: "je tue les gens ... au
                // bout de la 29e balle ... ça me compte comme raté, comme si j'avais fini mon chargeur"), its death a few ticks on
                if (spFirst >= 0 && spKills < 2 && Clip() == 0) { if (spEmptyAt < 0) spEmptyAt = now; else if (now - spEmptyAt > 24) CfSprayEnd("out of ammo"); }
                else if (SprayLetGo(now)) CfSprayEnd("released");
                else
                {   // its 3 s from the moment you saw the second one; one never in your sight: that pair again, not on you
                    var hs = Humans().FirstOrDefault(x => x.PawnIsAlive);
                    if (hs != null)
                        foreach (var (sl, _) in bots)
                            if (!spSeen.ContainsKey(sl) && !(spGo.TryGetValue(sl, out var go) && now < go + 8)
                                && Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value is { LifeState: (byte)LifeState_t.LIFE_ALIVE } bp
                                && (bp.EntitySpottedState.SpottedByMask[hs.Slot / 32] & (1u << (hs.Slot % 32))) != 0)
                            {
                                if (spSeen.Count == 0 && spWasted) { spWasted = false; SprayRefill(hs); }
                                spSeen[sl] = now;
                            }
                    var both = spSeen.Count >= 2 ? spSeen.Values.Max() : -1;
                    if (both >= 0 ? now - both > 3 * 64 : now - spAppear2 > 5 * 64) CfSprayEnd(both >= 0 || spUnseen >= 3 ? "too slow" : "unseen");
                }
            }
            else
            {
                CfSight();
                if (now - cfRepAt > (drill.Variant == "peek" ? 12 : 10) * 64) CfEnd(null, false);   // no duel came of it
            }
        }
        var left = Math.Max(0, (int)(drill.Seconds - el));
        var n = Math.Max(1, drill.Count);
        var line = CfSpray
            ? $"{F("spray {i}/{n}", "i", Math.Max(1, cfRep), "n", n)} · ✔ {spLog.Count(x => x.outcome == "clean")} · {spBullets}/{spMag}"
            : $"{F("duel {i}/{n}", "i", Math.Max(1, cfRep), "n", n)} · ✔ {cfWon} · ✘ {cfLost}";
        SetMain($"{Order(drill)}<br><font color='#ff8a3d'>{drill.Title}</font> · {line} · {left} s");
        if (el > drill.Seconds * 2 + 30) Finish("timeout");   // never stuck
    }

    // a jiggle, each tick: its peek till it shows to you, back along its way a third of a second, a moment there, then its
    // peek again from where it went back to; it never fights you meanwhile
    void CfJiggleTick(int now)
    {
        if (cfJig == 0 || drill?.Variant != "hold" || cur == null || cfResolved) { cfJiggling.Clear(); return; }
        var (sl, t) = bots.FirstOrDefault(b => b.Value.Sid == "cf0");
        var h = Humans().FirstOrDefault(x => x.PawnIsAlive);
        var pw = t == null ? null : Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value;
        if (t == null || h == null || pw == null || pw.LifeState != (byte)LifeState_t.LIFE_ALIVE || free.Contains(sl)) { cfJig = 0; cfJiggling.Clear(); return; }
        var fps = cur.Rate / (float)cur.Step;
        var f = (now - t0) / (float)cur.Step;
        switch (cfJig)
        {
            case 1:   // its peek till you see it
                if ((pw.EntitySpottedState.SpottedByMask[h.Slot / 32] & (1u << (h.Slot % 32))) == 0) return;
                cfJigF = f - t.Start;
                cfJig = 2; cfJigAt = now; cfJigLen = 20 + Rng.Next(8);
                cfJiggling.Add(sl);
                contact.Remove(sl);
                if (selftest) St("jiggle", new() { ["f"] = R1(cfJigF) });
                break;
            case 2:   // back along its way
                {
                    var back = (now - cfJigAt) / 64f * fps;
                    var at = PathAt(t, Math.Max(0f, cfJigF - back));
                    var prev = PathAt(t, Math.Max(0f, cfJigF - back + fps / 64f));
                    pw.Teleport(at, null, (at - prev) * 64f);
                    contact.Remove(sl);
                    if (now - cfJigAt >= cfJigLen) { cfJig = 3; cfJigF = Math.Max(0f, cfJigF - back); cfJigAt = now + 24 + Rng.Next(48); }
                    break;
                }
            case 3:   // a moment out of your sight, then the real peek from there
                pw.Teleport(PathAt(t, cfJigF), null, Vector3.Zero);
                contact.Remove(sl);
                if (now < cfJigAt) return;
                t.Start = f - cfJigF;
                cfJig = 0;
                cfJiggling.Remove(sl);
                cfSeenAt = -1; cfOff = -1;   // the duel is the one it comes back for
                ForgetMotion(sl);
                break;
        }
    }

    // the enemy came into your sight: where your crosshair was (degrees from its head), when
    void CfSight()
    {
        if (cfSeenAt >= 0) return;
        var h = Humans().FirstOrDefault(x => x.PawnIsAlive);
        var me = h?.PlayerPawn.Value;
        if (h == null || me?.AbsOrigin == null || me.EyeAngles == null) return;
        foreach (var (sl, t) in bots)
        {
            if (gone.Contains(t.Sid)) continue;
            var pw = Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value;
            if (pw?.AbsOrigin == null || pw.LifeState != (byte)LifeState_t.LIFE_ALIVE) continue;
            var m = pw.EntitySpottedState.SpottedByMask;
            if ((m[h.Slot / 32] & (1u << (h.Slot % 32))) == 0) continue;
            var duck = me.MovementServices == null ? 0f : new CCSPlayer_MovementServices(me.MovementServices.Handle).DuckAmount;
            var eye = new Vector3(me.AbsOrigin.X, me.AbsOrigin.Y, me.AbsOrigin.Z + 64 - 18 * duck);
            var head = new Vector3(pw.AbsOrigin.X, pw.AbsOrigin.Y, pw.AbsOrigin.Z + 62);
            cfSeenAt = Server.TickCount;
            cfOff = AngleOff(eye, me.EyeAngles.X, me.EyeAngles.Y, head);
            return;
        }
    }

    // your gun's magazine now (-1: none)
    int Clip()
    {
        var w = Humans().FirstOrDefault(x => x.PawnIsAlive)?.PlayerPawn.Value?.WeaponServices?.ActiveWeapon.Value;
        return w == null || !w.IsValid ? -1 : w.Clip1;
    }

    static float AngleOff(Vector3 eye, float pitch, float yaw, Vector3 at)
    {
        float p = pitch * MathF.PI / 180, y = yaw * MathF.PI / 180;
        var fw = new Vector3(MathF.Cos(p) * MathF.Cos(y), MathF.Cos(p) * MathF.Sin(y), -MathF.Sin(p));
        var to = at - eye;
        if (to.Length() < 1) return 0;
        return MathF.Acos(Math.Clamp(Vector3.Dot(fw, Vector3.Normalize(to)), -1f, 1f)) * 180 / MathF.PI;
    }

    // a shot of yours: moving or stopped; the spray's bullets and its gaps
    void CfShot(CCSPlayerController? p, string weapon)
    {
        if (drill?.Mode != "crossfire" || phase != "live" || p is not { IsValid: true, IsBot: false }) return;
        if (weapon.Contains("knife") || weapon.Contains("grenade") || weapon.Contains("flashbang") || weapon.Contains("molotov") || weapon.Contains("decoy")) return;
        var v = p.PlayerPawn.Value?.AbsVelocity;
        var speed = v == null ? 0f : MathF.Sqrt(v.X * v.X + v.Y * v.Y);
        cfShots++;
        if (speed > MovingShot) cfMoving++;
        if (!CfSpray || cfResolved) return;
        var now = Server.TickCount;
        // none of them out yet: not the spray (30/10, his review: his left click still down from the rep before fired the next
        // rep's magazine away, "je perds le round sur ça"); the magazine full again when the first one comes out
        if (spSeen.Count == 0) { spWasted = true; return; }
        if (SprayLetGo(now)) { CfSprayEnd("released"); return; }
        if (spFirst < 0) spFirst = now;
        spLast = now;
        spBullets++;
    }

    // a death in a crossfire drill; true: handled (yours: back on your spot at the next rep)
    bool CfDeath(EventPlayerDeath e, CCSPlayerController v)
    {
        if (v.IsBot && cfHiding.Remove(v.Slot)) return false;   // taken away between two reps
        var byYou = e.Attacker is { IsValid: true, IsBot: false };
        if (CfSpray)
        {
            if (v.IsBot && byYou && !cfResolved)
            {
                spKills++;
                if (spKills == 1) spKill1At = Server.TickCount;
                else CfSprayEnd("clean");
            }
            return !v.IsBot;
        }
        if (cfResolved) return !v.IsBot;
        if (v.IsBot) { CfEnd(byYou ? true : null, byYou && e.Headshot); return false; }
        CfEnd(false, false);
        return true;
    }

    // a duel's end: won, lost, or none (it never came)
    void CfEnd(bool? won, bool hs)
    {
        if (cfResolved) return;
        cfResolved = true;
        cfJig = 0; cfJiggling.Clear();
        var ttk = cfSeenAt >= 0 ? (Server.TickCount - cfSeenAt) / 64.0 : -1;
        if (won == true) { cfWon++; if (hs) cfHs++; }
        else if (won == false) cfLost++;
        else cfNone++;
        if (won != null) cfLog.Add((won.Value, cfOff, ttk));
        var off = cfOff >= 0 ? $" · {Math.Round(cfOff)}°" : "";
        var how = drill?.Variant == "hold" ? cfKind switch { "jiggle" => $" · {T("a jiggle")}", "swing" => $" · {T("a wide swing")}", _ => "" } : "";   // the peek it was
        Html(won == true ? $"<font color='#5ad15a'>✔ {T("WON")}</font>{(ttk >= 0 ? $" · {ttk.ToString("F2", CultureInfo.InvariantCulture)} s" : "")}{off}{(hs ? " · HS" : "")}{how}"
            : won == false ? $"<font color='#ff5a5a'>✘ {T("LOST")}</font>{off}{how}" : $"<font color='#e0a030'>{T("NO DUEL")}</font>", 1);
        CfHideLater();
        var g = generation;
        AddTimer(won == false ? 1.4f : 0.9f, () => { if (g == generation && phase == "live") CfNext(); });
    }

    // let go: a gap in your spray once both were in your sight and you had fired at them. A gap before the second came out is
    // no fault, nothing to shoot at (30/10, his review on Apps: the first dead, the second out 0.6 s later, his 2 kills
    // counted "lâché")
    bool SprayLetGo(int now)
    {
        if (spFirst < 0 || spKills >= 2 || now - spLast <= SprayGap || spSeen.Count < 2) return false;
        return spLast >= spSeen.Values.Max();
    }

    void SprayRefill(CCSPlayerController h)
    {
        if (h.PlayerPawn.Value?.WeaponServices?.ActiveWeapon.Value is not { IsValid: true } w || (w.VData?.MaxClip1 ?? 0) <= 0) return;
        w.Clip1 = w.VData!.MaxClip1;
        Utilities.SetStateChanged(w, "CBasePlayerWeapon", "m_iClip1");
        spEmptyAt = -1;
    }

    void CfSprayEnd(string outcome)
    {
        if (cfResolved) return;
        cfResolved = true;
        if (outcome == "unseen")
        {   // one of the pair never came into your sight: not your spray, another pair (3 at most a drill)
            spUnseen++;
            if (cfCur != null) cfBad.Add(cfCur);
            Log("crossfire: a spray's pair never in sight, again ({n})", spUnseen);
            CfHideLater();
            cfRep--;
            var g0 = generation;
            AddTimer(1.3f, () => { if (g0 == generation && phase == "live") CfNext(); });
            return;
        }
        var transfer = outcome == "clean" && spKill1At >= 0 ? (Server.TickCount - spKill1At) / 64.0 : -1;
        spLog.Add((outcome, spBullets, transfer));
        Html(outcome == "clean"
            ? $"<font color='#5ad15a'>✔ {T("CLEAN SPRAY")}</font> · {Tn(spBullets, "{n} bullet", "{n} bullets")}{(transfer >= 0 ? $" · {T("transfer")} {transfer.ToString("F2", CultureInfo.InvariantCulture)} s" : "")}"
            : $"<font color='#ff5a5a'>✘ {T(outcome switch { "released" => N("YOU LET GO"), "out of ammo" => N("OUT OF AMMO"), _ => N("TOO SLOW") })}</font> · {Tn(spBullets, "{n} bullet", "{n} bullets")}", 1);
        CfHideLater();
        var g = generation;
        AddTimer(1.3f, () => { if (g == generation && phase == "live") CfNext(); });
    }

    // the drill's result: ok, points, the line said (and the measures written with it)
    (bool ok, int pts, string detail) CfResult()
    {
        if (drill == null) return (false, 0, "");
        if (CfSpray)
        {
            var n = spLog.Count;
            var clean = spLog.Where(x => x.outcome == "clean").ToList();
            var ok = n > 0 && clean.Count * 5 >= n * 3;   // 3 clean of 5
            var pts = clean.Count * 80 + (ok ? 100 : 0);
            var why = spLog.Where(x => x.outcome != "clean").GroupBy(x => x.outcome)
                .Select(g => $"{T(g.Key switch { "released" => N("let go"), "out of ammo" => N("out of ammo"), _ => N("too slow") })} ×{g.Count()}");
            drillExtra["sprays"] = spLog.Select(x => new Dictionary<string, object> { ["outcome"] = x.outcome, ["bullets"] = x.bullets, ["transfer"] = Math.Round(x.transfer, 2) }).ToList();
            var detail = F("{a}/{b} clean sprays", "a", clean.Count, "b", n)
                         + (clean.Count > 0 ? $" · {F("{n} bullets on average", "n", Math.Round(clean.Average(x => x.bullets)))}" : "")
                         + string.Concat(why.Select(w => $" · {w}"));
            return (ok, pts, detail);
        }
        var duels = cfWon + cfLost;
        // and duels in most of its reps: reps with no duel are no wins (30/10, the user: "il meurt de lui-même, sauf que tu le
        // comptes comme si je l'avais tué": Forklift's hold passed on 1 duel in 6)
        var won = duels > 0 && cfWon * 3 >= duels * 2 && duels >= cfNone;   // 2 of 3 (4 of 6)
        var offs = cfLog.Where(x => x.off >= 0).Select(x => x.off).ToList();
        var ttks = cfLog.Where(x => x.won && x.ttk >= 0).Select(x => x.ttk).ToList();
        var points = Math.Max(0, cfWon * 40 + cfHs * 15 - cfLost * 10 + 10 * offs.Count(o => o <= 5)) + (won ? 100 : 0);
        drillExtra["duels"] = cfLog.Select(x => new Dictionary<string, object> { ["won"] = x.won, ["off"] = Math.Round(x.off, 1), ["ttk"] = Math.Round(x.ttk, 2) }).ToList();
        drillExtra["shots"] = cfShots;
        drillExtra["moving_shots"] = cfMoving;
        var text = F("{a}/{b} duels won", "a", cfWon, "b", duels) + $" · {cfHs} HS"
                   + (offs.Count > 0 ? $" · {F("crosshair {a}° from their heads when they came", "a", Math.Round(offs.Average()))}" : "")
                   + (ttks.Count > 0 ? $" · {F("{s} s to kill", "s", ttks.Average().ToString("F2", CultureInfo.InvariantCulture))}" : "")
                   + (drill.Variant == "peek" && cfShots > 0 ? $" · {F("{p}% of your shots while moving", "p", 100 * cfMoving / cfShots)}" : "")
                   + (cfNone > 0 ? $" · {Tn(cfNone, "{n} without a duel", "{n} without a duel")}" : "");
        return (won, points, text);
    }
}
