// Bots fighting by the plugin's hand (28/10, the user: "faire jouer un vrai joueur, comme si c'était un vrai joueur ... que
// l'IA joue systématiquement de la même manière, et systématiquement comme un joueur l'aurait joué ... avec un temps de
// réaction réaliste, sans wallhack, sans vue à travers les smokes non plus ... qu'il ne soit pas non plus trop nul").
// A bot freed to fight you (Free) stays the plugin's: the game's AI stopped (bot_stop), each tick the plugin writes its own
// command (its view and IN_ATTACK, in CBasePlayerController::OnSimulateUserCommands: see css_dbgaim), the game moving and
// firing it like any player (its weapon, its recoil, its spread). It sees you only when the game has you spotted by it (no
// wall) and no smoke is on the line, in front of it; it reacts after a player's reaction time (your lobbies' level: 0.32 s
// from spotted to a first hit, tools/bot_calib.py), turns onto you like a hand (fast, slowing on you, a little off, then
// settling), fires stopped: taps far, bursts mid way, sprays close, pulling part of its recoil down; you lost from sight,
// it holds where it saw you last and never fires through the wall. Every number drawn from a seed of the drill, the bot
// and its try: the same fight each run. Tests only for now: css_scripted 1 (the battery's), off for players.
using System.Numerics;
using System.Runtime.InteropServices;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Memory.DynamicFunctions;

namespace CoachReplay;

public partial class CoachReplay
{
    bool scripted;
    MemoryFunctionVoid<nint>? simCmd;
    nint srvBase;
    int fightTries;   // freed fighters since the drill began: each one's seed

    sealed class Fighter
    {
        public Random Rng = new(1);
        public int NoticeAt = -1, ReactTicks, LastSeen = -1, BurstLeft, RestUntil, Since;
        public Vector3 View, Err, Last;
        public bool HasLast, Fire;
        public bool Walk;    // walking in to your zone this tick (Walk.cs Hunt): Shift held
        public int HurtBy = -1, HurtAt = -100000;   // the one who last hit it, when (it turns to him, seen or not)
        public float Comp;   // the share of its recoil it pulls down
        public Vector3 Res;  // the off-head it settles on (redrawn each burst)
        public float Drop;   // how far under your head its burst goes (u): its first at your chest, each next one higher
        public int TargetSlot = -1;   // the one it fights
        public Track? T;     // its way, and where on it it was when it began to fight (taken up again when you are gone)
        public float FreedF;
        public int StepUntil, StepSide = 1;   // a strafe or a step back between its bursts: till when, its last side
        public int CrouchUntil;   // a burst fired crouched far off (real Ts: crouched 19 % of the time they stand; v4 never)
        public bool CrouchHold;   // it holds an angle crouched, waiting (drawn once a fight)
        public Vector3 Shown;     // its eyes as shown: its aim, with its sway while it sees nobody
        public char Move = 's';   // its move in the duel: a across, s still, t on along its way, b back along it
        public int WayK = -1;     // the frame of its way it is nearest to (on or back along it)
        public Vector2 StepDir;
    }
    readonly Dictionary<int, Fighter> fighters = new();

    // the bots' level (BotLv: the session's, or the measure's css_botlevel; 0 easy .. 3 expert; 1 = your lobbies': 0.32 s
    // from spotted to a first hit). 29/10 lab 9, Mirage's
    // B at normal: 13 deaths for no kill, each wave on you 0.4-0.9 s after it saw you: it reacted the same far off its
    // crosshair as on it, settled exactly on your head and turned at 1100 deg/s
    float LvReact => BotLv switch { 0 => 0.36f, 1 => 0.27f, 2 => 0.22f, _ => 0.18f };        // s before its hand moves, on its crosshair
    float LvPerDeg => BotLv switch { 0 => 0.0045f, 1 => 0.0035f, 2 => 0.0028f, _ => 0.0022f };   // s more per degree off it
    // a defense's attackers less sure of their aim, as quick to react (03/11, the user: "le module de défense ... est autant perdu
    // parce que les bots sont très forts"; round 17: 6 defenses of 34 passed, the rest of the blocks 82-100 %): they come into a
    // site clearing its angles, not on one they hold
    float DefMul => drill?.Mode == "defend" ? 1.5f : 1f;
    float LvResidual => DefMul * (BotLv switch { 0 => 1.6f, 1 => 1.0f, 2 => 0.7f, _ => 0.45f });          // deg its aim stays off, drawn per burst
    // deg a tick at most (30/10, the user: "c'est un peu comme s'ils mettaient un headshot avant de me regarder ... on a
    // l'impression qu'ils sont même pas en train de me regarder, qu'ils me headshot déjà": 576-1024 deg/s at levels 1-3)
    float LvTurn => BotLv switch { 0 => 4f, 1 => 6f, 2 => 8f, _ => 11f };
    float LvComp => BotLv switch { 0 => 0.3f, 1 => 0.5f, 2 => 0.65f, _ => 0.8f };              // its recoil pulled down
    // where each burst goes (03/11, the user: "une fois que le temps de réaction est passé, ils mettent un headshot
    // instantanément, alors qu'en vraie partie, c'est pas forcément des headshots instantanés, et même pas souvent, et c'est
    // plus des body shots ... et les headshots viennent des fois jamais, des fois beaucoup plus tard"): the body (12-22 u under
    // the eyes, chest or stomach), the head only for a burst drawn so, never the first; a head hit also from the spray's climb
    float LvHeadP => BotLv switch { 0 => 0.12f, 1 => 0.2f, 2 => 0.3f, _ => 0.4f };   // a burst's chance to go for the head
    static float BodyDrop(Random rng) => 12f + 10f * (float)rng.NextDouble();

    Vector3 DrawOff(Random rng, float r)
    {
        var a = (float)(rng.NextDouble() * Math.PI * 2); var m = r * (0.4f + 0.9f * (float)rng.NextDouble());
        return new Vector3(MathF.Sin(a) * m, MathF.Cos(a) * m, 0f);
    }

    // a stable hash (string.GetHashCode changes with each process): FNV-1a
    static int Seed(string s)
    {
        unchecked
        {
            uint h = 2166136261;
            foreach (var ch in s) { h ^= ch; h *= 16777619; }
            return (int)(h & 0x7fffffff);
        }
    }

    void CombatLoad()
    {
        CombatDebug();
        AddCommand("css_scripted", "freed bots fight by the plugin's hand (tests): css_scripted 0|1", (p, c) =>
        {
            if (p != null) return;
            var on = c.ArgCount > 1 && c.GetArg(1) == "1";
            if (on == scripted) { Log("scripted: {s} already", on ? "on" : "off"); return; }
            if (on)
            {
                srvBase = GameServerDll();
                try { simCmd = new(SimCmdSig); simCmd.Hook(SimPre, HookMode.Pre); simCmd.Hook(SimPost, HookMode.Post); }
                catch (Exception e) { Log("scripted: no command hook ({m}), off", e.Message); simCmd = null; return; }
                if (srvBase == 0) { simCmd.Unhook(SimPre, HookMode.Pre); simCmd = null; Log("scripted: no server.dll, off"); return; }
                if (!RttiVtables(srvBase))   // this game's own classes (Rtti.cs): a CS2 update moves them
                { simCmd.Unhook(SimPre, HookMode.Pre); simCmd.Unhook(SimPost, HookMode.Post); simCmd = null; Log("scripted: the command's classes not found in this server.dll, off"); return; }
            }
            else
            {
                try { simCmd?.Unhook(SimPre, HookMode.Pre); simCmd?.Unhook(SimPost, HookMode.Post); } catch (Exception) { }
                simCmd = null;
                fighters.Clear();
            }
            scripted = on;
            Log("scripted: {s}", on ? "on" : "off");
        });
        AddCommand("css_dbglook", "one bot on its way traced tick by tick: its eyes before and after the plugin and its command: css_dbglook [ticks]", (p, c) =>
        {
            if (p != null) return;
            dbgLook = -2; dbgLookN = int.TryParse(c.GetArg(1), out var n) ? n : 96;
            Log("dbglook: armed for {n} ticks", dbgLookN);
        });
        AddCommand("css_waycmd", "a bot on its way: its command's view the plugin's (1, default) or the game's (0), to compare", (p, c) =>
        {
            if (p != null) return;
            if (c.ArgCount > 1) wayCmd = c.GetArg(1) != "0";
            Log("waycmd: {w}", wayCmd);
        });
        AddCommand("css_botlevel", "the bots' own level for the measure: css_botlevel 0-3, or -1 (the session's)", (p, c) =>
        {
            if (p != null) return;
            if (c.ArgCount > 1 && int.TryParse(c.GetArg(1), out var l)) botLevel = Math.Clamp(l, -1, 3);
            Log("botlevel: {l} (bots at {b})", botLevel, BotLv);
        });
    }

    // a fight between two bots by the plugin's hand, server 2, nobody on it (28/10): a stopped T, turned 90 deg off, fights a
    // stopped CT 800 u up Dust2's mid as it would fight you; when it noticed, fired, hit, killed: css_dbgfight [seconds]
    void CombatDebug()
    {
        AddCommand("css_dbgfight", "a bot fights another by the plugin's hand (Combat.cs), its timings", (p, c) =>
        {
            var secs = c.ArgCount > 1 && float.TryParse(c.GetArg(1), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var sv) ? sv : 3f;
            var t = Utilities.GetPlayers().FirstOrDefault(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true, Team: CounterStrikeSharp.API.Modules.Utils.CsTeam.Terrorist });
            var ct = Utilities.GetPlayers().FirstOrDefault(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true, Team: CounterStrikeSharp.API.Modules.Utils.CsTeam.CounterTerrorist });
            if (t?.PlayerPawn.Value == null || ct?.PlayerPawn.Value == null) { Log("dbgfight: a T bot and a CT bot needed"); return; }
            if (!scripted) { Log("dbgfight: css_scripted 1 first"); return; }
            Zombie(false); BotStop(true);
            var tp = t.PlayerPawn.Value; var cp = ct.PlayerPawn.Value;
            tp.Teleport(new Vector3(-417f, -1f, 20f), new Vector3(0f, 0f, 0f), Vector3.Zero);   // looking 86 deg off the CT
            cp.Teleport(new Vector3(-367f, 802f, 16f), new Vector3(0f, -90f, 0f), Vector3.Zero);
            t.GiveNamedItem("weapon_ak47");
            cp.Health = 100;
            var start = Server.TickCount + 64;
            int fired = -1, hit = -1, killed = -1, shots = 0, hits = 0;
            var ts = t.Slot;
            HookResult F(EventWeaponFire e, GameEventInfo i) { if (e.Userid?.Slot == ts) { shots++; if (fired < 0) fired = Server.TickCount; } return HookResult.Continue; }
            HookResult H(EventPlayerHurt e, GameEventInfo i) { if (e.Attacker?.Slot == ts) { hits++; if (hit < 0) hit = Server.TickCount; if (e.Health <= 0 && killed < 0) killed = Server.TickCount; } return HookResult.Continue; }
            RegisterEventHandler<EventWeaponFire>(F);
            RegisterEventHandler<EventPlayerHurt>(H);
            Fighter? fi = null;
            var tm = AddTimer(1f / 64f, () =>
            {
                if (Server.TickCount < start || !tp.IsValid || !cp.IsValid) return;
                if (fi == null)
                {
                    fi = new Fighter { Rng = new Random(Seed("dbgfight|1")), Since = Server.TickCount, Comp = 0.7f };
                    if (tp.EyeAngles is { } ea) fi.View = new Vector3(ea.X, ea.Y, 0f);
                    fighters[ts] = fi;
                }
                var m = cp.EntitySpottedState.SpottedByMask;
                FightTick(cp.LifeState == (byte)LifeState_t.LIFE_ALIVE ? cp : null, new[] { m[0], m[1] });
            }, CounterStrikeSharp.API.Modules.Timers.TimerFlags.REPEAT);
            AddTimer(secs + 1f, () =>
            {
                tm.Kill();
                fighters.Remove(ts);
                DeregisterEventHandler<EventWeaponFire>(F);
                DeregisterEventHandler<EventPlayerHurt>(H);
                BotStop(false);
                int at(int k) => k < 0 ? -1 : (int)MathF.Round((k - start) * 1000f / 64f);
                Log("dbgfight: noticed {n} ms, first shot {f} ms, first hit {h} ms, kill {k} ms; {s} shots, {x} hits (ms from the start; its reaction drawn {r} ticks)",
                    fi == null || fi.NoticeAt < 0 ? -1 : at(fi.NoticeAt), at(fired), at(hit), at(killed), shots, hits, fi?.ReactTicks ?? -1);
            });
        });
    }

    // the drills it plays: a defense's attackers, a situation's enemies
    bool ScriptedDrill => scripted && (drill?.Mode == "defend" || cur?.Kind is "death" or "clutch");

    // Free(): a bot that would play on its own fights by the plugin's hand instead
    bool FightScripted(int slot, CCSPlayerController c, Track t)
    {
        if (!ScriptedDrill || phase != "live") return false;   // your teammates too (29/10): they fight the enemy bots the same way
        var pw = c.PlayerPawn.Value;
        if (pw == null || !pw.IsValid) return false;
        var now = Server.TickCount;
        var fi = new Fighter { Rng = new Random(Seed($"{drill?.Id}|{t.Sid}|{fightTries++}")), Since = now, T = t,
                               FreedF = cur == null ? 0f : (now - t0) / (float)cur.Step - t.Start };
        fi.Comp = LvComp * (0.85f + 0.3f * (float)fi.Rng.NextDouble());
        // v9: 4 % of their stops crouched, v14 7, real Ts 19-20; 30/10, his review: "dès qu'ils me voient, restent accroupis"
        fi.CrouchHold = fi.Rng.NextDouble() < 0.35;
        fi.Res = DrawOff(fi.Rng, LvResidual);
        if (pw.EyeAngles is { } ea) fi.View = new Vector3(ea.X, ea.Y, 0f);
        fi.Shown = fi.View;
        // freed at its contact (it saw you ReactTicks): noticed then, its reaction counted from its first sight of you
        if (contact.GetValueOrDefault(slot) > 0 && sawYou.TryGetValue(slot, out var saw) && now - saw < 8 && mePawnNow?.AbsOrigin is { } mo0 && pw.AbsOrigin is { } bo0)
        {
            var off0 = AngDiff(fi.View, AngTo(new Vector3(bo0.X, bo0.Y, bo0.Z + 64f), new Vector3(mo0.X, mo0.Y, mo0.Z + 63f))).Length();
            fi.NoticeAt = now;
            fi.ReactTicks = Math.Max(2, ReactTicksFor(fi.Rng, off0) - contact[slot]);
            fi.Err = DrawOff(fi.Rng, 1.5f * LvResidual);
        }
        // its duel goes on from its walk: on along its way at its speed till it has reacted (29/10: it stopped dead the tick it
        // saw you, "ça se voit qu'il change de mode")
        // ... across, from the speed it has (v17: on along its way toward you 42 % of the duel's first 1.5 s, real Ts 17, across
        // 45: a T seen is mostly peeking already); its legs take it there a little at a time, no stop
        fi.Move = 'a';
        fi.StepSide = fi.Rng.NextDouble() < 0.5 ? 1 : -1;
        fi.StepUntil = now + 26 + fi.Rng.Next(32);
        fighters[slot] = fi;
        GunUp(slot, c, t, pw);   // its gun out of its knife first (Knife.cs)
        wayEyes.Remove(slot);
        Freeze(pw, false);
        Log("scripted: {n} fights by the plugin's hand", t.Name);
        return true;
    }

    CCSPlayerPawn? mePawnNow;   // you, as FightTick last saw you (a fighter freed at its contact measures how far off you were)

    // its reaction: the level's, more the further you are off its crosshair (a player sees you later at the edge of his
    // screen), a little drawn: in ticks
    int ReactTicksFor(Random rng, float offDeg) =>
        (int)MathF.Round((LvReact + LvPerDeg * Math.Min(offDeg, 70f) + 0.06f * (float)rng.NextDouble()) * 64f);   // 03/11: no slower in a defense, his words

    // the smokes up now: a line through one is no sight (the game's spotting may not cut it)
    List<Vector3> SmokesUp()
    {
        var up = new List<Vector3>();
        foreach (var s in Utilities.FindAllEntitiesByDesignerName<CSmokeGrenadeProjectile>("smokegrenade_projectile"))
            if (s.IsValid && s.DidSmokeEffect && s.AbsOrigin is { } o && Server.TickCount - s.SmokeEffectTickBegin < 22 * 64)
                up.Add(new Vector3(o.X, o.Y, o.Z + 40f));
        return up;
    }

    static bool ThroughSmoke(Vector3 a, Vector3 b, List<Vector3> smokes)
    {
        var d = b - a; var len2 = d.LengthSquared();
        if (len2 < 1f) return false;
        foreach (var s in smokes)
        {
            var k = Math.Clamp(Vector3.Dot(s - a, d) / len2, 0f, 1f);
            if (Vector3.DistanceSquared(a + d * k, s) < 130f * 130f) return true;
        }
        return false;
    }

    // its aim punch as the server has it (the bullets leave along the view plus twice it: weapon_recoil_scale)
    static Vector3 Punch(CCSPlayerPawn pw) => pw.AimPunchServices is { } aps ? new Vector3(aps.PredictableBaseAngle.X, aps.PredictableBaseAngle.Y, 0f) : Vector3.Zero;

    static Vector3 AngTo(Vector3 from, Vector3 to)
    {
        var d = to - from;
        return new Vector3(-MathF.Atan2(d.Z, new Vector2(d.X, d.Y).Length()) * 180f / MathF.PI, MathF.Atan2(d.Y, d.X) * 180f / MathF.PI, 0f);
    }

    static Vector3 AngDiff(Vector3 from, Vector3 to) => new(to.X - from.X, ((to.Y - from.Y + 540f) % 360f) - 180f, 0f);

    // a player in its sight as in a player's (its way's contact and its fight test it the same, 29/10): the game has him
    // spotted by it, no smoke on the line, and him in front of its eyes (80 deg each side, 60 up or down)
    static bool InCone(Vector3 view, Vector3 eye, Vector3 head)
    {
        var off = AngDiff(view, AngTo(eye, head));
        return MathF.Abs(off.Y) < 80f && MathF.Abs(off.X) < 60f;
    }

    static bool SeesFront(int slot, CCSPlayerPawn bot, CCSPlayerPawn? target, List<Vector3>? smokes)
    {
        if (slot >= 64 || target?.AbsOrigin is not { } to || bot.AbsOrigin is not { } bo || bot.EyeAngles is not { } ea) return false;
        var mk = target.EntitySpottedState.SpottedByMask;
        if ((mk[slot / 32] & (1u << (slot % 32))) == 0) return false;
        var eye = new Vector3(bo.X, bo.Y, bo.Z + (bot.ViewOffset?.Z ?? 64f));
        var head = new Vector3(to.X, to.Y, to.Z + (target.ViewOffset?.Z ?? 64f) - 1f);
        return (smokes == null || !ThroughSmoke(eye, head, smokes)) && InCone(new Vector3(ea.X, ea.Y, 0f), eye, head);
    }

    void FightTick(CCSPlayerPawn? mePawn, uint[]? seen)
    {
        mePawnNow = mePawn;
        if (fighters.Count == 0) return;
        var now = Server.TickCount;
        var smokes = SmokesUp();
        foreach (var slot in fighters.Keys.ToList())
        {
            var fi = fighters[slot];
            var pw = Utilities.GetPlayerFromSlot(slot)?.PlayerPawn.Value;
            if (pw == null || !pw.IsValid || pw.LifeState != (byte)LifeState_t.LIFE_ALIVE || pw.AbsOrigin == null) { fighters.Remove(slot); continue; }
            fi.Fire = false; fi.Walk = false;
            fi.Shown = fi.View;   // its eyes as its aim, till its sway below
            // its enemy out of its sight 1.5 s: it goes on its way (a defense's attackers come to your zone, 28/10 lab 8: stopped
            // where they had seen you, Mirage's B held 100 s with nobody coming)
            // 29/10: a defense's attacker after 0.75 s, on toward your zone, its eyes where it saw you (Look.cs: its side's info)
            var lostFor = drill?.Mode == "defend" || sitHunt ? 48 : 96;
            var lost = (fi.LastSeen >= 0 ? now - fi.LastSeen : now - fi.Since) > lostFor;
            if (fi.T != null && lost && !sitHunt && Release(slot, fi, pw)) continue;   // a situation's hunt: no way back
            if (lost && Hunt(slot, fi, pw, smokes)) { fi.NoticeAt = -1; fi.Shown = fi.View; continue; }   // no way on: it walks on in (Walk.cs)
            var o = pw.AbsOrigin; var eye = new Vector3(o.X, o.Y, o.Z + (pw.ViewOffset?.Z ?? 64f));
            // its target (29/10, the user: "diriger les adversaires, mais aussi les alliés"): the nearest player of the other
            // side it sees (the game's spotting, no smoke on the line): you, or a bot of your team; none: the last one
            var team = fi.T?.Team ?? pw.TeamNum;
            CCSPlayerPawn? tp = null; var best = float.MaxValue; var tSlot = -1;
            foreach (var pl in Utilities.GetPlayers())
            {
                if (pl is not { IsValid: true, PawnIsAlive: true } || pl.Slot == slot || pl.TeamNum == team || pl.TeamNum < 2) continue;
                var pp = pl.PlayerPawn.Value;
                if (pp?.AbsOrigin is not { } po) continue;
                var mk = pp.EntitySpottedState.SpottedByMask;
                if (slot >= 64 || (mk[slot / 32] & (1u << (slot % 32))) == 0) continue;
                var hh = new Vector3(po.X, po.Y, po.Z + (pp.ViewOffset?.Z ?? 64f) - 1f);
                if (ThroughSmoke(eye, hh, smokes)) continue;
                // one it has not noticed: only in front of it (spotted behind it, it stood still, its last sight fresh, forever)
                // or the one who just hit it, wherever (30/10, the user: "quand je retire dessus, ils regardent n'importe où")
                // or one right by it (300 u: heard, his steps, 30/10, the user: "un ennemi littéralement juste derrière mon allié.
                // C'est impossible que l'allié ne l'ait pas vu")
                if (!(pl.Slot == fi.TargetSlot && fi.NoticeAt >= 0) && !(pl.Slot == fi.HurtBy && now - fi.HurtAt < 128)
                    && Vector3.Distance(eye, hh) > 300f && !InCone(fi.View, eye, hh)) continue;
                var dd = Vector3.Distance(eye, hh);
                if (dd < best) { best = dd; tp = pp; tSlot = pl.Slot; }
            }
            var sees = tp != null;
            if (sees && tSlot != fi.TargetSlot) { fi.TargetSlot = tSlot; fi.NoticeAt = -1; }   // another one: a reaction of its own
            if (tp == null && fi.TargetSlot >= 0)
                tp = Utilities.GetPlayerFromSlot(fi.TargetSlot) is { PawnIsAlive: true } lp ? lp.PlayerPawn.Value : null;
            // nobody in its sight 1.5 s and its real way over: what players did there (Move.cs), its eyes where they look
            if (!sees && drill?.Mode != "defend" && !sitHunt && (fi.LastSeen >= 0 ? now - fi.LastSeen : now - fi.Since) > 96 && RoamTick(slot, fi, pw, smokes))
            {
                if (fi.T != null && lookTab.Count > 0) { fi.View = LookFor(slot, fi.T, new Vector3(o.X, o.Y, o.Z), fi.View, mePawnNow, smokes); SetEyes(pw, fi.View); }
                fi.NoticeAt = -1;
                continue;
            }
            if (tp?.AbsOrigin == null) { HoldAim(pw, fi.View, false); continue; }
            var mo = tp.AbsOrigin; var head = new Vector3(mo.X, mo.Y, mo.Z + (tp.ViewOffset?.Z ?? 64f) - 1f);
            var dist = Vector3.Distance(eye, head);
            var want = AngTo(eye, head);
            var off = AngDiff(fi.View, want);
            if (sees)
            {
                // you in front of it (a player's sight, 80 deg each side); once noticed, followed
                if (fi.NoticeAt < 0 && (MathF.Abs(off.Y) < 80f && MathF.Abs(off.X) < 60f || tSlot == fi.HurtBy && now - fi.HurtAt < 128 || dist < 300f))
                {
                    fi.NoticeAt = now;
                    fi.ReactTicks = ReactTicksFor(fi.Rng, off.Length());
                    fi.Err = DrawOff(fi.Rng, 1.5f * LvResidual);   // where its hand lands first, off your head (deg)
                    fi.Drop = BodyDrop(fi.Rng);   // its first burst at your body
                }
                fi.LastSeen = now; fi.Last = head; fi.HasLast = true;
            }
            else if (fi.NoticeAt >= 0 && now - fi.LastSeen > 24) fi.NoticeAt = -1;   // lost: a new reaction when you show again
            var aimAt = (Vector3?)null;
            // its reaction holds its flick (30/10, the user: "le moment où le bot apparaît dans mon écran, le moment où le bot
            // détecte que lui me voit, et le moment où le bot commence à me tirer dessus ... beaucoup trop long"; round 11, level
            // 0: 0.83 s from your sight of it to its first shot, its level's reaction 0.36 s, the hand moving only after it then
            // settling to a head's width; the levels were taken from your lobbies' 0.32 s from spotted to a first HIT): its hand
            // moves from 55 % of it, its first shot at its end
            var handAt = (int)(fi.ReactTicks * 0.55f);
            var wantA = AngTo(eye, new Vector3(head.X, head.Y, head.Z - fi.Drop));   // where its burst goes: under your head
            if (fi.NoticeAt >= 0 && now - fi.NoticeAt >= handAt) aimAt = wantA + fi.Err + fi.Res;
            else if (!sees && fi.HasLast) aimAt = AngTo(eye, fi.Last);   // holds where it saw you
            if (aimAt is { } tgt)
            {
                // its recoil pulled down in part: the bullets leave along the view plus twice the punch
                var punch = Punch(pw);
                tgt -= punch * 2f * fi.Comp;
                var d = AngDiff(fi.View, tgt);
                var n = d.Length();
                // a hand's turn: a third of the way each tick, at least 0.4 deg, at most the level's (6-16 deg a tick)
                var step = n <= 0.4f ? n : Math.Clamp(n * 0.33f, 0.4f, LvTurn);
                if (n > 0f) fi.View += d * (step / n);
                fi.View = new Vector3(Math.Clamp(fi.View.X, -89f, 89f), ((fi.View.Y + 540f) % 360f) - 180f, 0f);
                if (fi.NoticeAt >= 0 && now - fi.NoticeAt >= handAt) fi.Err *= 0.86f;   // settling on you
                if (fi.Err.Length() < 0.15f) fi.Err = Vector3.Zero;
            }
            // fire: on you, seen, stopped
            // it fires once its hand is where it means it (its own error with it: it believes it is on you)
            var onYou = AngDiff(fi.View + Punch(pw) * 2f * fi.Comp, wantA + fi.Res).Length();
            // on you to fire: a chest's width for a burst's first bullet (a player fires as his flick lands, not once it is on
            // the head to the unit), a head's for the next ones
            var tol = Math.Max(0.45f, MathF.Atan2(fi.BurstLeft > 0 ? 7f : 12f, dist) * 180f / MathF.PI);
            var v = pw.AbsVelocity is { } av ? new Vector2(av.X, av.Y).Length() : 0f;
            // stopped to fire, or slow and near (real Ts: 56 % of shots stopped, 31 u/s at the median; v7: 84 %, 0)
            if (sees && fi.NoticeAt >= 0 && now - fi.NoticeAt >= fi.ReactTicks && onYou < tol && v < (dist < 500f ? 130f : 90f) && now >= fi.RestUntil)
            {
                if (fi.BurstLeft <= 0)
                {
                    // a tap, a burst, a spray; the R8 fires once its hammer is back: its trigger held 22 ticks a shot (29/10,
                    // the user: "pour tirer un revolver, il faut clic gauche un peu plus longtemps que les autres armes")
                    fi.BurstLeft = pw.WeaponServices?.ActiveWeapon.Value?.DesignerName == "weapon_revolver" ? 22
                                 : dist > 1400f ? 1 : dist > 650f ? 7 + fi.Rng.Next(14) : 30 + fi.Rng.Next(16);   // ticks held: a tap, 1-3 shots, 5-7 (v5: 1 shot at the 90th, real Ts 6)
                    if (dist > 400f && fi.Rng.NextDouble() < 0.45) fi.CrouchUntil = now + fi.BurstLeft + 24;   // a burst crouched, off a way (v7: 0.8 % of their stops crouched, real 19)
                }
                fi.Fire = true;
                fi.BurstLeft--;
                if (fi.BurstLeft <= 0)
                {
                    fi.RestUntil = now + (dist > 1400f ? 14 + fi.Rng.Next(6) : 9 + fi.Rng.Next(5)); fi.Res = DrawOff(fi.Rng, LvResidual);
                    fi.Drop = fi.Rng.NextDouble() < LvHeadP ? 2f : BodyDrop(fi.Rng);   // its next one: the body mostly, the head seldom
                    // 29/10 (tools/bot_vs_real.py, 131 real Mirage matches: a T an enemy sees is stopped 21 % of the next
                    // 1.5 s and moves at 106 u/s on average, 43 % of them back; 56 % of shots are fired stopped): after a
                    // burst a strafe (a side, then the other) or a step back for a moment, mostly; then it stops and fires
                }
            }
            else if (fi.BurstLeft > 0 && fi.BurstLeft < 30 && !sees) fi.BurstLeft = 0;
            // its legs once it fights: a strafe or a step back between its bursts (a player's speed with its gun, 30 u/s more
            // a tick), else stopped to shoot as a counter-strafe stops a player (a fifth of its speed off each tick: 200 to 30
            // in 0.13 s; real Ts 0.23 s; it was set to 0 at once)
            // its legs in the duel (29/10, the user: "ça se voit qu'il change de mode et le mode combat n'a rien d'un vrai
            // joueur"; tools/bot_vs_real.py, 40 real Mirage matches, the 1.5 s after an enemy sees a T: still 26 %, across 45 %,
            // back 11 %, toward 17 %; v11: 39, 39, 0.7, 22, it never backed off): a move drawn every 0.25-0.6 s with real Ts'
            // shares, across (a side, then the other), still, on along its own way or back along it (to the cover the real
            // player came from); slowed to fire as it is about to (a counter-strafe, a fifth of its speed off each tick; real
            // Ts' shots 55 % under 40 u/s, 31 at the median), its move again after; kept on a moment once you are gone
            if (fi.NoticeAt >= 0 || (fi.LastSeen >= 0 && now - fi.LastSeen < lostFor))
            {
                if (now >= fi.StepUntil)
                {
                    var r = fi.Rng.NextDouble();
                    // v12: across 13 %, toward 44 (its first walk on); v15: back 4, toward 33 (real 11 and 17): on along its way
                    // seldom drawn, back more
                    fi.Move = r < 0.56 ? 'a' : r < 0.78 ? 's' : r < 0.81 ? 't' : 'b';
                    // across: the same side half of the time, longer (v13: 36 stops a minute, real Ts 15; a side each time)
                    if (fi.Move == 'a' && fi.Rng.NextDouble() < 0.5) fi.StepSide = -fi.StepSide;
                    if (fi.Move != 's') fi.CrouchUntil = 0;   // up to move
                    fi.StepUntil = now + (fi.Move is 'a' or 'b' ? 26 + fi.Rng.Next(32) : 16 + fi.Rng.Next(23));
                }
                var cv = pw.AbsVelocity is { } av2 ? new Vector2(av2.X, av2.Y) : Vector2.Zero;
                var toE = new Vector2(head.X - eye.X, head.Y - eye.Y);
                toE = toE.Length() > 1f ? Vector2.Normalize(toE) : Vector2.UnitX;
                var gun = WClass(pw) == "awp" ? 150f : 200f;
                var go = fi.Move switch
                {
                    'a' => new Vector2(-toE.Y, toE.X) * fi.StepSide * gun,
                    't' => AlongWay(fi, pw, 1) * Math.Clamp(cv.Length(), 130f, gun),   // on at the speed it has
                    // back along its way, else straight away from you (v16: off its way it stood: 4.6 % back, real Ts 11)
                    'b' => (AlongWay(fi, pw, -1) is { } bw && bw != Vector2.Zero ? bw : -toE) * gun,
                    _ => Vector2.Zero,
                };
                var aiming = sees && fi.NoticeAt >= 0 && now - fi.NoticeAt >= fi.ReactTicks - 8 && now >= fi.RestUntil - 4;
                var ground = (pw.Flags & (uint)CounterStrikeSharp.API.Modules.Utils.PlayerFlags.FL_ONGROUND) != 0;
                Vector2 nv;
                // about to fire: braking to a shot's speed, not to a stop (v14: 73 % of its shots stopped, real Ts 55, 32 u/s at
                // the median; 29 stops a minute, real 15); still when its move is
                var shotV = dist < 500f ? 110f : 70f;
                // backing off it goes on: no brake to fire (v18: backing off 0.5 % of the duel, real Ts 11: drawn, it braked to
                // fire at once and went back a few ticks between two bursts; a T who breaks the line does not stop to shoot)
                var shoots = (aiming || fi.Fire) && fi.Move != 'b';
                if (shoots && cv.Length() > shotV) nv = cv * 0.8f;
                else if (shoots && go.Length() >= 1f) nv = cv;   // fires as it goes, slow
                else if (go.Length() < 1f) nv = cv.Length() < 5f ? Vector2.Zero : cv * 0.8f;
                else
                {
                    var dv = go - cv;
                    if (dv.Length() > 30f) dv = Vector2.Normalize(dv) * 30f;
                    nv = PastFriction(cv + dv, ground);
                }
                // crouched (a burst far off, an angle held): a crouch's speed, never a strafe's
                var crouchNow = CrouchFire(fi, sees, v, dist, now)
                                || pw.MovementServices != null && new CCSPlayer_MovementServices(pw.MovementServices.Handle).Ducked;
                if (crouchNow && nv.Length() > CrouchCap(pw)) nv = Vector2.Normalize(nv) * CrouchCap(pw);
                if ((nv - cv).Length() > 0.5f) pw.Teleport(null, null, new Vector3(nv.X, nv.Y, pw.AbsVelocity?.Z ?? 0f));
            }
            // a head never quite still (v7: still half the time, real Ts 2.8 deg/s at the median)
            // its sway over its aim while it sees nobody (its aim as it is the moment it does)
            fi.Shown = sees ? fi.View : fi.View + Sway(slot, now, 0.7f);
            // crouched to hold or to fire still (v15: 6.5 % of its stops crouched, real Ts 20)
            // crouched only while it sees you or fires (30/10, the user: "il reste énormément accroupi, même si je ne suis plus
            // dans son champ de vision ... une fois que le joueur s'en va, il reste rarement accroupi")
            HoldAim(pw, fi.Shown, CrouchFire(fi, sees, v, dist, now));
        }
    }

    // crouched: only to fire, stopped, its legs still (30/10, his review: they crouched the moment they saw him and stayed so,
    // one peeked him crouched on Nuke's stairs; a player crouches to spray far off, never to peek): a burst far off, or its
    // crouched hold once it fires beyond 400 u
    static bool CrouchFire(Fighter fi, bool sees, float v, float dist, int now)
        => sees && fi.Fire && fi.Move == 's' && v < 40f && (now < fi.CrouchUntil || (fi.CrouchHold && dist > 400f));

    // the way's direction from where it stands, on (+1) or back (-1) along its own way, a third of a second of it
    Vector2 AlongWay(Fighter fi, CCSPlayerPawn pw, int dir)
    {
        if (cur == null || fi.T is not { Frames: > 2 } t || pw.AbsOrigin is not { } o) return Vector2.Zero;
        var here = new Vector3(o.X, o.Y, o.Z);
        var fps = cur.Rate / (float)cur.Step;
        var from = fi.WayK >= 0 ? fi.WayK : Math.Clamp((int)fi.FreedF, 0, t.Frames - 1);
        var (k, d) = NearOnWay(t, here, from - (int)fps, from + (int)fps, 9999f);
        if (k < 0 || d > 200f) return Vector2.Zero;
        fi.WayK = k;
        var at = Pos(t, Math.Clamp(k + dir * (int)(0.35f * fps), 0, t.Frames - 1));
        var to = new Vector2(at.X - here.X, at.Y - here.Y);
        return to.Length() < 8f ? Vector2.Zero : Vector2.Normalize(to);
    }

    // back on its way from the nearest point of it ahead of where it began to fight (no teleport: its way's clock set to it)
    bool Release(int slot, Fighter fi, CCSPlayerPawn pw)
    {
        var t = fi.T!;
        if (cur == null || pw.AbsOrigin == null || t.Frames < 2) return false;
        var here = new Vector3(pw.AbsOrigin.X, pw.AbsOrigin.Y, pw.AbsOrigin.Z);
        int k = -1; var best = float.MaxValue;
        if (drill?.Mode == "defend")
        {   // a defense's attacker: the shortest real way to your zone, its own or another's (29/10, Walk.cs)
            if (!WayToZone(t, here, mePawnNow?.AbsOrigin is { } mo ? new Vector3(mo.X, mo.Y, mo.Z) : null)) return false;
            k = (int)((Server.TickCount - t0) / (float)cur.Step - t.Start);
        }
        else
        {
            for (int i = Math.Clamp((int)fi.FreedF, 0, t.Frames - 1); i < t.Frames; i++)
            {
                var d = Vector3.DistanceSquared(Pos(t, i), here);
                if (d < best) { best = d; k = i; }
            }
            if (k < 0 || k >= t.Frames - 2 || best > 200f * 200f) return false;   // its way over or far: it holds there
            t.Start = (Server.TickCount - t0) / (float)cur.Step - k;
        }
        fighters.Remove(slot); free.Remove(slot); engaged.Remove(slot); contact.Remove(slot); ForgetMotion(slot);
        // its look on its way from where its eyes are (29/10: from the one it had before its fight, snapped to)
        lookNow[slot] = fi.View; lookPick.Remove(slot); wayEyes[slot] = fi.View;
        Crouch(pw, false);   // up again to walk (a burst may have been crouched)
        Log("scripted: {n} goes on its way (frame {k} of {f})", t.Name, k, t.Frames);
        return true;
    }

    int dbgLook = -1, dbgLookN;   // css_dbglook: the bot traced (-2: the next one on its way), ticks left
    readonly Dictionary<int, Vector3> wayEyes = new();   // a bot on its way: its eyes as the plugin left them this tick

    // after its command (29/10, css_dbglook on server 2): the game had moved its eyes again, every tick, 3 to 8 deg off the
    // plugin's and lagging behind its turns (the bot's own aim and its error, bot_stop or not): put back where the plugin set
    // them, its fight's view for a fighter
    HookResult SimPost(DynamicHook h)
    {
        if (!wayCmd || !ScriptedDrill || phase != "live") return HookResult.Continue;
        var ctl = h.GetParam<nint>(0);
        if (ctl == 0) return HookResult.Continue;
        var pc = new CCSPlayerController(ctl);
        if (!pc.IsValid || !pc.IsBot || pc.PlayerPawn.Value is not { } pw || pw.EyeAngles is not { } eye) return HookResult.Continue;
        if (pc.Slot == dbgLook && dbgLookN > 0) Log("dbglook {t} after cmd eyes {ex:F1} {ey:F1}", Server.TickCount, eye.X, eye.Y);
        Vector3 want;
        if (fighters.TryGetValue(pc.Slot, out var fi)) want = fi.Shown;
        else if (bots.ContainsKey(pc.Slot) && !free.Contains(pc.Slot) && wayEyes.TryGetValue(pc.Slot, out var we)) want = we;
        else return HookResult.Continue;
        if (Math.Abs(eye.X - want.X) > 0.05f || Math.Abs(((eye.Y - want.Y + 540f) % 360f) - 180f) > 0.05f)
        { eye.X = want.X; eye.Y = want.Y; Utilities.SetStateChanged(pw, "CCSPlayerPawn", "m_angEyeAngles"); }
        return HookResult.Continue;
    }

    // its command, as the game runs it: its view and IN_ATTACK (the CInButtonState's first mask, +0x60)
    HookResult SimPre(DynamicHook h)
    {
        var onWays = wayCmd && ScriptedDrill && phase == "live";
        if (fighters.Count == 0 && !onWays) return HookResult.Continue;
        var ctl = h.GetParam<nint>(0);
        if (ctl == 0) return HookResult.Continue;
        var pc = new CCSPlayerController(ctl);
        if (!pc.IsValid) return HookResult.Continue;
        Vector3 view; var fire = false;
        if (fighters.TryGetValue(pc.Slot, out var fi)) { view = fi.View; fire = fi.Fire; }
        // a bot on its way (29/10, the user: "ils se retournent en regardant le mur ... un espèce de on-off"): its command
        // carried the game's own view (bot_stop's frozen one, the AI's) against the plugin's, tick after tick; now the view
        // the plugin gave it, no button, no step (its walk is its speed, the plugin's)
        else if (onWays && pc.IsBot && bots.ContainsKey(pc.Slot) && !free.Contains(pc.Slot) && pc.PlayerPawn.Value?.EyeAngles is { } ea)
            view = new Vector3(ea.X, ea.Y, 0f);
        else return HookResult.Continue;
        var arr = (nint)Rd64(ctl + 0x4c8); var idx = Rd32(ctl + 0x4d0);
        var el = arr + Math.Max(0, idx) * 0xA0;
        if (arr == 0 || idx < 0 || !Readable(el, 0xA0) || Rd64(el + 0x58) - srvBase != VtInButton) return HookResult.Continue;
        var b = (nint)Rd64(el + 0x40);
        var qa = Readable(b, 0x48) && Rd64(b) - srvBase == VtBasePB ? (nint)Rd64(b + 0x40) : 0;
        if (qa != 0 && Readable(qa, 0x28) && Rd64(qa) - srvBase == VtQAngle)
        {
            if (pc.Slot == dbgLook && dbgLookN > 0 && pc.PlayerPawn.Value?.EyeAngles is { } de)
                Log("dbglook {t} cmd {qx:F1} {qy:F1} eyes {ex:F1} {ey:F1} queue {q} idx {i}", Server.TickCount, BitConverter.Int32BitsToSingle(Rd32(qa + 0x18)),
                    BitConverter.Int32BitsToSingle(Rd32(qa + 0x1C)), de.X, de.Y, Rd32(ctl + 0x4c4) & 0x7fffffff, Rd32(ctl + 0x4d0));
            Marshal.WriteInt32(qa + 0x18, BitConverter.SingleToInt32Bits(view.X));
            Marshal.WriteInt32(qa + 0x1C, BitConverter.SingleToInt32Bits(view.Y));
        }
        // its buttons and moves are the plugin's alone (29/10, the situations: their AI runs, for your teammates): IN_ATTACK
        // or nothing, no step (it stands to fight, as it counter-strafed)
        // Shift for a bot walking its way (30/10: real Ts walk with Shift 31 % of their moving, v19 never: the game's own
        // m_bIsWalking set by hand was taken back by its command each tick); IN_SPEED is 0x10000 in CS2
        // and for one walking in to your zone (30/10, v25: 18 % of its moving at 100-135 u/s walking, the hunters' 126 u/s run)
        // Shift at a walk's speed only: faster it runs and is heard (30/10, his review: "s'il n'est pas en shift ... qu'il court
        // pour de vrai, j'aimerais l'entendre pour de vrai"; a way's clock lead ran it with Shift held)
        var spd = pc.PlayerPawn.Value?.AbsVelocity is { } sv ? MathF.Sqrt(sv.X * sv.X + sv.Y * sv.Y) : 0f;
        var buttons = (fire ? 1L : 0L) | ((fi == null ? wayShift.GetValueOrDefault(pc.Slot) : fi.Walk) && spd <= 150f ? 0x10000L : 0L);
        Marshal.WriteInt64(el + 0x60, buttons);
        if (Readable(b, 0x60) && Rd64(b) - srvBase == VtBasePB)
        {
            Marshal.WriteInt32(b + 0x58, 0); Marshal.WriteInt32(b + 0x5C, 0);   // forwardmove, leftmove
            var bp = (nint)Rd64(b + 0x38);
            if (bp != 0 && Readable(bp, 0x20) && Rd64(bp) - srvBase == VtButtonPB) Marshal.WriteInt64(bp + 0x18, buttons);
        }
        return HookResult.Continue;
    }
}
