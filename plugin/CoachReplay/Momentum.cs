// Momentum (14/10, rework_entrainement.md section 9; the user: "Momentum: a dedicated movement training mode built to
// improve your map mobility, pathing, and jump precision using real map assets"): moving on the real maps, from the
// base's real rounds (momentum.py builds the drills). No bot: you, the map, and what is measured. A drill is a series of
// reps, each one from its start, still:
// - route: a real way against the clock (a spawn to a site, a CT rotation), knife out. Its checkpoints in order (rings
//   on the ground, the gold line until you ran it once); at each one your time against the base's pace, at the end
//   against the base's runs of that way, its fastest ones and the pros'. A checkpoint missed: off the way, that run
//   counts for nothing. Three runs;
// - jump: a jump the base's players make onto something: from the green ring, land in the blue one, on top. A jump far
//   from the green ring is no try; a landing below says why (short, or not crouched in the air where the base's jumpers
//   crouch). Three landings, five tries at most;
// - stop: counter-strafing: run left and right at full speed, STOP comes on the screen. Measured: the time from your
//   speed's drop to an accurate stop (34 % of your top speed: Leetify's moving shot), and whether you then went the
//   other way (the other key held too long). Eight stops;
// - silent: the last stretch of a real way into a site, walked in the time given: each footstep and each jump heard.
using System.Globalization;
using System.Numerics;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Utils;

namespace CoachReplay;

public partial class CoachReplay
{
    bool MoOn => drill is { Mode: "momentum" };
    const float CpR = 120f, EndR = 140f;   // how near a checkpoint and a way's end count (momentum.py: CP_R, END_R)
    const float StopShare = 0.34f;   // an accurate stop: under 34 % of your top speed
    const double BrakeOk = 0.12;   // s from the drop to the stop: a counter-strafe (about 0.08), a key let go (about 0.2)
    int moRep, moRepAt, moNext, moMissed, moSteps, moHops;
    // 16/10, the user's video: "il faudrait que le compteur commence quand je commence à me déplacer", "la vitesse du
    // perso": a run's clock from your first step, your speed on the screen
    bool moMoved;
    float moSpeed;
    // a solo boost (17/10, his 16/10 video: "c'est vraiment des solo boosts ou des jumps très compliqués à faire"): jumps in
    // a row, each landing on a ring (the drill's marks) the next one leaves from, the last one in the blue ring
    int moChain, moChainAt;
    string moStage = "";   // ready, run, jump, air, strafe, brake, over, after, dead
    readonly List<(bool valid, double time, int missed)> moRuns = new();
    readonly List<(bool ok, double time, int steps, int hops, int missed)> moWalks = new();
    readonly List<(bool ok, string why, float off, bool duck)> moJumps = new();
    readonly List<(double react, double brake, bool over, string why)> moStops = new();
    int moAirAt;   // a jump: when it left the ground
    float moAirHv;   // its speed on the ground then: a silent jump's (how "walk") heard from 140 u/s (Shift: 130 at most)
    bool moWasGround = true;   // on the ground at the tick before (a takeoff seen without the game's player_jump)
    int moStuck = -1;   // since when it hangs in the air without moving: wedged in the scenery
    bool moAirDuck, moHinted;   // crouched in the air; the jump's reminder said
    // a stop: at full speed since, the STOP due at, said at, the speed's drop, the stop; the top speed and the way then
    int moFastSince = -1, moStopDue = -1, moStopAt = -1, moDropAt = -1, moStillAt = -1;
    float moTop;
    Vector2 moWay;
    // a guided self-test (17/10, the user: "notify moi quand tu auras tout testé et tout défini comme parfaitement prêt à
    // être testé par un humain"): a bot in your place runs the ways, walks the silent ones, stops dead on STOP and makes
    // the jumps with the game's own physics, the drill measuring it as it measures you
    float mgS;        // a run: its distance along the line
    int mgNext;       // a jump's next moment
    int mgDir = 1;    // a strafe's way
    int mgGround;     // ticks on the ground in a row (a teleport leaves it in the air for a tick: no jump before it stood)
    float[]? mgTo;    // the ring its jump goes to
    int mgProbe;      // how far back from the green ring it stands (8 u a step): a ring just past a box's edge
    bool mgPlaced;    // put on its spot since its last jump
    int mgLift;       // its jumps' height over the landing, raised after each miss (36, 64, 96, 128 u), crouched in the air after one

    void RegisterMomentum()
    {
        RegisterEventHandler<EventPlayerJump>((e, _) => { MoJump(e.Userid); return HookResult.Continue; });
        RegisterEventHandler<EventPlayerFootstep>((e, _) => { MoStep(e.Userid); return HookResult.Continue; });
    }

    static string Sec(double s, int d = 2) => s.ToString(d == 1 ? "F1" : "F2", CultureInfo.InvariantCulture);
    static float Flat(Vector3 a, float[] b) => new Vector2(a.X - b[0], a.Y - b[1]).Length();

    Scenario MomentumScenario(Drill d)
    {
        var s = new Scenario { Id = d.Id, Map = d.Map, Kind = "momentum", Title = d.Title, Team = d.Team };
        var me = d.Me ?? new Spot();
        s.Players.Add(new Track { Sid = "me", Name = "you", Team = d.Team, Me = true, Hp = 100, Armor = d.Armor, Helmet = d.Helmet, Weapons = d.Weapons,
            Active = d.Weapons.LastOrDefault(), Path = new[] { me.Pos[0], me.Pos[1], me.Pos[2], me.Ang[1], me.Ang[0] } });
        // the doors and the vents on the way open, as they were for the base's players (a point every 48 u of its line)
        for (int i = 0; i + 1 < d.Line.Count; i++)
        {
            var a = new Vector3(d.Line[i][0], d.Line[i][1], d.Line[i][2]);
            var b = new Vector3(d.Line[i + 1][0], d.Line[i + 1][1], d.Line[i + 1][2]);
            var n = Math.Max(1, (int)(Vector3.Distance(a, b) / 48));
            for (int k = 0; k < n; k++) { var p = Vector3.Lerp(a, b, k / (float)n); s.Trail.Add(new[] { p.X, p.Y, p.Z }); }
        }
        if (d.From is { Length: >= 3 } f) s.Trail.Add(f);
        if (d.Target is { Length: >= 3 } tg) s.Trail.Add(tg);
        if (selftest && stGuided)   // a guided self-test's runner in your place, moved by MoGuideDrive (the replay leaves it)
            s.Players.Add(new Track { Sid = "guide", Name = "guide", Team = d.Team, Hp = 100, Weapons = d.Weapons, Active = d.Weapons.LastOrDefault(),
                Path = new[] { me.Pos[0], me.Pos[1], me.Pos[2], me.Ang[1], me.Ang[0] }, Strafe = true });
        return s;
    }

    // Place() is done: the counters from zero, the marks on the ground
    void MoPlaced()
    {
        moRep = 0; moStage = "";
        mgNext = mgGround = mgLift = mgProbe = 0;   // the game's tick count starts again with each map: a moment kept from another one waits forever
        mgPlaced = false;
        moRuns.Clear(); moWalks.Clear(); moJumps.Clear(); moStops.Clear(); drillExtra.Clear();
        if (drill == null) return;
        ClearLine();
        var teal = System.Drawing.Color.FromArgb(255, 86, 212, 200);
        var blue = System.Drawing.Color.FromArgb(255, 90, 180, 255);
        var green = System.Drawing.Color.FromArgb(255, 90, 230, 90);
        if (drill.Variant is "route" or "silent")
        {   // the gold line until you ran it once (the training's boxes: level 1), the checkpoints, the end
            // the line always (19/10, his 17/10 video: "il manque le chemin ... on voit les petits ronds mais il n'y a pas
            // le chemin écrit au sol")
            if (drill.Line.Count > 1) DrawLine(drill.Line);
            for (int k = 0; k < drill.Marks.Count; k++)
            {
                var m = drill.Marks[k];
                var last = k == drill.Marks.Count - 1;
                Ring(new Vector3(m[0], m[1], m[2]), last ? 60f : 36f, last ? blue : teal, last ? 3f : 2f);
                Beam(new Vector3(m[0], m[1], m[2] + 4), new Vector3(m[0], m[1], m[2] + (last ? 140 : 70)), last ? blue : teal, last ? 3f : 2f);
            }
        }
        else if (drill.Variant == "jump" && drill.Target is { Length: >= 3 } tg)
        {   // where to jump from, where to land (a post over it: seen from below the box); a solo boost's steps between
            if (drill.From is { Length: >= 3 } f) Ring(new Vector3(f[0], f[1], f[2]), 20f, green, 1.5f);
            foreach (var m in drill.Marks.Where(m => m.Length >= 3))
            {
                Ring(new Vector3(m[0], m[1], m[2]), 28f, teal, 2f);
                Beam(new Vector3(m[0], m[1], m[2] + 4), new Vector3(m[0], m[1], m[2] + 60), teal, 2f);
            }
            Ring(new Vector3(tg[0], tg[1], tg[2]), 36f, blue, 2.5f);
            Beam(new Vector3(tg[0], tg[1], tg[2] + 4), new Vector3(tg[0], tg[1], tg[2] + 110), blue, 3f);
        }
    }

    void Ring(Vector3 c, float r, System.Drawing.Color col, float w)
    {
        for (int i = 0; i < 12; i++)
        {
            float a0 = i * MathF.PI / 6, a1 = (i + 1) * MathF.PI / 6;
            Beam(c + new Vector3(r * MathF.Cos(a0), r * MathF.Sin(a0), 4), c + new Vector3(r * MathF.Cos(a1), r * MathF.Sin(a1), 4), col, w);
        }
    }

    void MoGo() => MoNext();

    bool MoEnough()
    {
        if (drill == null) return true;
        var n = Math.Max(1, drill.Count);
        return drill.Variant switch
        {
            // one run through every ring in the base's time is enough (19/10: "trois fois d'affilée c'est relou ... si je le
            // réussis dans un bon temps du premier coup, pas besoin de le refaire")
            "route" => moRuns.Count >= n || moRuns.Any(r => r.valid && (drill.Par <= 0 || r.time <= drill.Par)),
            "silent" => moWalks.Count >= n || moWalks.Any(w => w.ok),
            "jump" => moJumps.Count(j => j.ok) >= Math.Max(1, drill.Goal) || moJumps.Count >= n,
            _ => moStops.Count >= n,
        };
    }

    // the next rep, or the drill's end
    void MoNext()
    {
        if (drill == null || cur == null || phase != "live") return;
        if (MoEnough() || (Server.TickCount - t0) / 64f >= drill.Seconds * 1.5f) { Finish("done"); return; }
        moRep++;
        moRepAt = Server.TickCount;
        moHinted = false;
        if (drill.Variant is "route" or "silent")
        {   // on the start, still a moment, then the clock (the first one right at GO)
            MoBack(true);
            if (moRep == 1) { MoRun(); return; }
            moStage = "ready";
            foreach (var h in MoPlayers()) if (h.PlayerPawn.Value is { } pw) Freeze(pw, true);
            Html($"<font color='#56d4c8'>{T("READY")}</font> · {F("run {i}/{n}", "i", moRep, "n", Math.Max(1, drill.Count))}", 2);
            var g = generation;
            AddTimer(1.5f, () => { if (g == generation && phase == "live" && moStage == "ready") MoRun(); });
        }
        else if (drill.Variant == "jump") { MoBack(true); moStage = "jump"; moChain = 0; }
        else
        {   // a stop: you stay where you strafe (back on the spot only when far from it)
            MoBack(moRep == 1);
            moStage = "strafe";
            moFastSince = moStopDue = moStopAt = moDropAt = moStillAt = -1;
        }
    }

    void MoRun()
    {
        moStage = "run";
        moRepAt = Server.TickCount;
        moNext = moMissed = moSteps = moHops = 0;
        moMoved = false;
        mgS = 0f;
        foreach (var h in MoPlayers()) if (h.PlayerPawn.Value is { } pw) Freeze(pw, false);
        Html($"<font color='#56d4c8'>{T("GO")}</font>", 1);
    }

    // the start a drill puts you on, on something that holds you (27/10 20:27, Overpass's Upper Park: the base's run-up
    // start, the median of where its players began, hung off the box's top over the floor 43 u below; put there you fell at
    // once, "tombé" 5 times in 13 s): the base's start when a floor is under your feet there, else the first spot that has
    // one on its way to the green ring, else the ring itself. Once per drill.
    string? moStartFor;
    Vector3 moStartAt;
    Vector3 MoStart(Vector3 start)
    {
        if (drill == null || drill.From is not { Length: >= 3 } f) return start;
        if (moStartFor == drill.Id) return moStartAt;
        var ign = (CBaseEntity?)Humans().FirstOrDefault(h => h.PawnIsAlive)?.PlayerPawn.Value;
        if (ign == null) return start;
        var opt = new TraceOptions { InteractsWith = Masks.PlayerSolidBrushOnly };
        bool Holds(Vector3 p)
        {   // under the feet's middle or a corner of them, 14 u down at most
            foreach (var (dx, dy) in new[] { (0f, 0f), (12f, 12f), (-12f, 12f), (12f, -12f), (-12f, -12f) })
                if (Trace.TraceEndShape(new CounterStrikeSharp.API.Modules.Utils.Vector(p.X + dx, p.Y + dy, p.Z + 8f),
                        new CounterStrikeSharp.API.Modules.Utils.Vector(p.X + dx, p.Y + dy, p.Z - 14f), ign, opt).Fraction < 1f) return true;
            return false;
        }
        var ring = new Vector3(f[0], f[1], f[2]);
        var at = ring;
        if (Holds(start)) at = start;
        else
        {
            var d = ring - start;
            var L = d.Length();
            for (var s = 8f; s < L; s += 8f)
            {
                var q = start + d * (s / L);
                if (Holds(q)) { at = q; break; }
            }
            Log("momentum start {a} off its floor: {b}", R3(start), R3(at));
        }
        moStartFor = drill.Id;
        moStartAt = at;
        return at;
    }

    // you on the drill's start, alive, still (always: a new rep; else only when far from it)
    void MoBack(bool always)
    {
        var me = cur?.Players.FirstOrDefault(p => p.Me);
        if (me == null) return;
        foreach (var h in MoPlayers())
        {
            var fresh = !h.PawnIsAlive;
            if (fresh) { h.Respawn(); Loadout(h, me, 100); }
            var pw = h.PlayerPawn.Value;
            if (pw == null) continue;
            var at = MoStart(Pos(me, 0));
            if (!always && !fresh && pw.AbsOrigin is { } o && Vector3.Distance(new Vector3(o.X, o.Y, o.Z), at) < 400) continue;
            pw.Teleport(at, Upright(Ang(me, 0)), Vector3.Zero);
            Freeze(pw, false);   // walking (20/10: still half in the sandbox's noclip, "comme si mon personnage était à moitié en train de voler")
        }
    }

    CCSPlayerController? MoGuide() => selftest && stGuided
        ? bots.Where(kv => kv.Value.Sid == "guide").Select(kv => Utilities.GetPlayerFromSlot(kv.Key)).FirstOrDefault(c => c is { IsValid: true })
        : null;

    IEnumerable<CCSPlayerController> MoPlayers() => MoGuide() is { } g ? new[] { g } : Humans();

    CCSPlayerPawn? MoPawn() => MoPlayers().Select(h => h.PlayerPawn.Value)
        .FirstOrDefault(p => p != null && p.IsValid && p.LifeState == (byte)LifeState_t.LIFE_ALIVE);

    // each tick of a momentum drill: its rep, the screen
    void MoTick(float el)
    {
        if (drill == null || cur == null) return;
        if (el > drill.Seconds * 2 + 60) { Finish("timeout"); return; }   // never stuck
        var now = Server.TickCount;
        var pw = MoPawn();
        if (pw?.AbsOrigin == null)
        {   // dead (a fall off the map): that rep missed, back on the start
            if (moStage is not ("dead" or "after"))
            {
                MoMiss(T("fell"));
                moStage = "dead";
            }
        }
        else
        {
            if (selftest && stGuided) MoGuideDrive(pw, now);
            var at = new Vector3(pw.AbsOrigin.X, pw.AbsOrigin.Y, pw.AbsOrigin.Z);
            moSpeed = pw.AbsVelocity is { } mv ? new Vector2(mv.X, mv.Y).Length() : 0f;
            if (moStage == "run" && !moMoved)
            {
                if (moSpeed > 30f) moMoved = true;
                else moRepAt = now;   // still on the start: the clock waits
            }
            // wedged in the scenery: off the ground, not moving a hair for 2 s (22/10, Dust2's mid doors jump: the guide hung
            // there 3 minutes, the drill never went on): that try missed, back on the start
            var hv = pw.AbsVelocity;
            var hang = (pw.Flags & (uint)PlayerFlags.FL_ONGROUND) == 0 && (hv == null || MathF.Abs(hv.X) + MathF.Abs(hv.Y) + MathF.Abs(hv.Z) < 1f);
            if (moStage is "jump" or "air" && hang)
            {
                if (moStuck < 0) moStuck = now;
                else if (now - moStuck > 128)
                {
                    moStuck = -1;
                    moStage = "after";
                    St("mojump", new() { ["ok"] = false, ["why"] = "stuck", ["at"] = R3(at) });
                    MoBack(true);
                    MoMiss(T("stuck in the scenery: back on the start"));
                    return;
                }
            }
            else moStuck = -1;
            switch (moStage)
            {
                case "run": MoRunTick(at, now); break;
                case "jump": MoJumpWait(pw, at, now); break;
                case "air": MoAirTick(pw, at, now); break;
                case "strafe" or "brake" or "over": MoStopTick(pw, now); break;
            }
        }
        SetMain($"{Order(drill)}<br><font color='#56d4c8'>{drill.Title}</font> · {MoLine(now)}<br><font class='fontSize-s'>{drill.Tip}</font>");
    }

    string MoLine(int now)
    {
        if (drill == null) return "";
        var n = Math.Max(1, drill.Count);
        var t = moStage == "run" ? (now - moRepAt) / 64.0 : 0;
        return drill.Variant switch
        {
            "route" => $"{F("run {i}/{n}", "i", Math.Max(1, moRep), "n", n)} · ⏱ {Sec(t, 1)} s · {F("checkpoint {i}/{n}", "i", Math.Min(moNext + 1, drill.Marks.Count), "n", drill.Marks.Count)}"
                       + (drill.Par > 0 ? $" · {F("base {s} s", "s", Sec(drill.Par, 1))}" : "") + $" · {(int)moSpeed} u/s",
            "silent" => $"👣 {moSteps} · ⏱ {Sec(t, 1)} / {Sec(drill.Par, 1)} s · {(int)moSpeed} u/s",
            "jump" => $"{F("{a}/{b} landed", "a", moJumps.Count(j => j.ok), "b", Math.Max(1, drill.Goal))} · {F("try {i}/{n}", "i", Math.Min(n, moJumps.Count + 1), "n", n)} · {(int)moSpeed} u/s",
            _ => $"{F("stop {i}/{n}", "i", Math.Max(1, moRep), "n", n)} · ✔ {moStops.Count(s => s.why == "")}"
                 + (moStage == "strafe" ? $" · {T("run left and right (A, D)")}" : ""),
        };
    }

    // a run or a walk: the checkpoints in order (one reached past another: that one missed), the end
    void MoRunTick(Vector3 at, int now)
    {
        if (drill == null) return;
        var t = (now - moRepAt) / 64.0;
        var M = drill.Marks;
        for (int k = moNext; k < M.Count; k++)
        {
            var m = M[k];
            var last = k == M.Count - 1;
            if (Flat(at, m) > (last ? EndR : CpR) || MathF.Abs(at.Z - m[2]) > 110) continue;
            moMissed += k - moNext;
            moNext = k + 1;
            if (last) { MoArrive(t); return; }
            if (drill.Variant == "route" && drill.Par > 0)
            {   // the base's pace there
                var dv = t - drill.Par * (m.Length > 3 ? m[3] : (k + 1f) / M.Count);
                Html($"<font color='{(dv <= 0 ? "#5ad15a" : "#e0a030")}'>{k + 1}/{M.Count} · {Sec(t, 1)} s · {dv.ToString("+0.0;-0.0;0.0", CultureInfo.InvariantCulture)} s</font>", 1);
            }
            break;
        }
        var limit = drill.Variant == "silent" ? drill.Par + 6 : Math.Max(20, drill.Par * 2 + 8);
        if (t > limit) MoArrive(-1);
    }

    // the way's end (time -1: too slow)
    void MoArrive(double time)
    {
        if (drill == null || moStage != "run") return;
        moStage = "after";
        if (drill.Variant == "route")
        {
            var valid = time >= 0 && moMissed == 0;
            moRuns.Add((valid, time, moMissed));
            St("morun", new() { ["valid"] = valid, ["time"] = Math.Round(time, 2), ["missed"] = moMissed, ["par"] = drill.Par });
            Html(time < 0 ? $"<font color='#ff5a5a'>✘ {T("TOO SLOW")}</font>"
                : !valid ? $"<font color='#ff5a5a'>✘ {T("OFF THE WAY")}</font> · {Tn(moMissed, "{n} checkpoint missed", "{n} checkpoints missed")} · {Sec(time)} s"
                : $"<font color='{(drill.Par <= 0 || time <= drill.Par ? "#5ad15a" : "#e0a030")}'>⏱ {Sec(time)} s</font> · {F("base {s} s", "s", Sec(drill.Par, 1))}"
                  + (drill.Best > 0 ? $" · {F("its fastest {s} s", "s", Sec(drill.Best, 1))}" : "") + (drill.Pro > 0 ? $" · {F("pros {s} s", "s", Sec(drill.Pro, 1))}" : ""), 2);
        }
        else
        {
            var ok = time >= 0 && time <= drill.Par && moSteps == 0 && moHops == 0 && moMissed == 0;
            moWalks.Add((ok, time, moSteps, moHops, moMissed));
            St("mowalk", new() { ["ok"] = ok, ["time"] = Math.Round(time, 2), ["steps"] = moSteps, ["hops"] = moHops, ["missed"] = moMissed, ["par"] = drill.Par });
            Html(ok ? $"<font color='#5ad15a'>✔ {T("NOT HEARD")}</font> · {Sec(time, 1)} s"
                : time < 0 || time > drill.Par ? $"<font color='#ff5a5a'>✘ {T("TOO SLOW")}</font>{(time >= 0 ? $" · {Sec(time, 1)} / {Sec(drill.Par, 1)} s" : "")}"
                : moMissed > 0 ? $"<font color='#ff5a5a'>✘ {T("OFF THE WAY")}</font>"
                : $"<font color='#ff5a5a'>✘ {T("HEARD")}</font> · {Tn(moSteps, "{n} footstep", "{n} footsteps")}{(moHops > 0 ? $" · {Tn(moHops, "{n} jump", "{n} jumps")}" : "")}", 2);
        }
        var g = generation;
        AddTimer(2f, () => { if (g == generation && phase == "live") MoNext(); });
    }

    // a rep lost to a death (a fall off the map)
    void MoMiss(string why)
    {
        if (drill == null) return;
        if (drill.Variant == "route") moRuns.Add((false, -1, 0));
        else if (drill.Variant == "silent") moWalks.Add((false, -1, 0, 0, 0));
        else if (drill.Variant == "jump") moJumps.Add((false, why, -1, false));
        Html($"<font color='#ff5a5a'>✘ {why}</font>", 1);
        var g = generation;
        AddTimer(1f, () => { if (g == generation && phase == "live") MoNext(); });
    }

    // the game's footsteps and jumps: heard on a silent walk; a jump's takeoff
    void MoStep(CCSPlayerController? p)
    {
        if (!MoOn || drill!.Variant != "silent" || moStage != "run" || p is not { IsValid: true } || (p.IsBot && !IsGuide(p)) || phase != "live") return;
        moSteps++;
        Html($"<font color='#ff5a5a'>👣 {T("heard")}</font>", 1);
    }

    void MoJump(CCSPlayerController? p)
    {
        if (!MoOn || p is not { IsValid: true } || (p.IsBot && !IsGuide(p)) || phase != "live") return;
        if (drill!.Variant == "silent" && moStage == "run") { moHops++; Html($"<font color='#ff5a5a'>{T("jump heard")}</font>", 1); return; }
        var o = p.PlayerPawn.Value?.AbsOrigin;
        var v = p.PlayerPawn.Value?.AbsVelocity;
        if (o != null) MoTakeoff(new Vector3(o.X, o.Y, o.Z), v == null ? 0f : new Vector2(v.X, v.Y).Length());
    }

    // a jump's takeoff, from the game's player_jump or seen leaving the ground (16/10: none counted in his 6 jump drills,
    // 2 min on Mirage's Side Alley without a try: the takeoff is watched each tick too)
    void MoTakeoff(Vector3 o, float hv)
    {
        if (drill?.Variant != "jump" || moStage != "jump" || drill.From is not { Length: >= 3 } f) return;
        var step = moChain > 0 && moChain <= drill.Marks.Count && Server.TickCount - moChainAt < 3 * 64 ? drill.Marks[moChain - 1] : null;
        if (step != null && Flat(o, step) <= 96 && MathF.Abs(o.Z - step[2]) <= 32)
        {   // the boost's next jump, from the step it landed on
            moStage = "air";
            moAirAt = Server.TickCount;
            moAirHv = MathF.Max(moAirHv, hv);
            return;
        }
        if (Flat(o, f) > 120 || MathF.Abs(o.Z - f[2]) > 48)
        {   // a hop anywhere else is no try
            Html($"<font color='#e0a030'>{T("from the green ring")}</font>", 1);
            return;
        }
        moStage = "air";
        moAirAt = Server.TickCount;
        moAirDuck = false;
        moAirHv = hv;
    }

    // waiting for the jump: back on the start when you went far, a reminder after 12 s
    void MoJumpWait(CCSPlayerPawn pw, Vector3 at, int now)
    {
        if (drill?.From is not { Length: >= 3 } f) return;
        var ground = (pw.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0;
        var up = pw.AbsVelocity.Z;
        var off = moWasGround && !ground && up > 120;   // off the ground going up: a jump (a step down falls, it doesn't rise)
        moWasGround = ground;
        if (off) { MoTakeoff(at, new Vector2(pw.AbsVelocity.X, pw.AbsVelocity.Y).Length()); if (moStage == "air") return; }
        // off its start without a jump, down on the floor below (20/10, his video: "là je suis tombé au sol, je ne devrais
        // pas pouvoir réessayer sans me mettre une erreur"): that try missed
        if (ground && at.Z < f[2] - 40f && Flat(at, f) < 500f)
        {
            moStage = "after";
            St("mojump", new() { ["ok"] = false, ["why"] = "fell", ["at"] = R3(at) });
            MoMiss(T("fell"));
            return;
        }
        if (Flat(at, f) > 700) { MoBack(true); return; }
        if (!moHinted && now - moRepAt > 12 * 64) { moHinted = true; Html($"<font color='#e0a030'>{T("from the green ring, land in the blue one")}</font>", 2); }
        if (selftest && stGuided && now - moRepAt > 20 * 64)
        {   // a guided self-test's try with no takeoff in 20 s: missed, back on the start (it never waits on one jump for ever)
            moStage = "after";
            St("mojump", new() { ["ok"] = false, ["why"] = "no takeoff", ["at"] = R3(at) });
            MoBack(true);
            MoMiss(T("stuck in the scenery: back on the start"));
        }
    }

    // in the air: crouched or not; landed (on the ground again): on top or not, and why
    void MoAirTick(CCSPlayerPawn pw, Vector3 at, int now)
    {
        if (drill?.Target is not { Length: >= 3 } tg) return;
        var duck = pw.MovementServices == null ? 0f : new CCSPlayer_MovementServices(pw.MovementServices.Handle).DuckAmount;
        if (duck > 0.5f) moAirDuck = true;
        if (now - moAirAt < 6) return;
        var ground = (pw.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0;
        if (!ground && now - moAirAt < 3 * 64) return;
        var dz = at.Z - tg[2];
        var off = Flat(at, tg);
        var ok = ground && dz >= -18 && dz <= 24 && off <= 140;
        // a silent jump (19/10, his video: "tu peux faire ce jump dans ce sens-là en slow, donc sans faire de bruit"):
        // taken running, they heard you come
        var heard = drill.How == "walk" && moAirHv >= 140f;
        if (!ok && ground && moChain < drill.Marks.Count && drill.Marks[moChain] is { Length: >= 3 } mk && Flat(at, mk) <= 96 && MathF.Abs(at.Z - mk[2]) <= 24)
        {   // on the boost's step: the next jump now
            moChain++;
            moChainAt = now;
            St("mostep", new() { ["step"] = moChain, ["at"] = R3(at) });
            moStage = "jump";
            moWasGround = true;
            Html($"<font color='#56d4c8'>✔ {moChain}/{drill.Marks.Count + 1}</font> · {T("now the next jump")}", 1);
            return;
        }
        moStage = "after";
        moChain = 0;
        var crouch = drill.How.Contains("duck");
        var why = ok && heard ? T("heard: walk it (Shift held)") : ok ? "" : dz < -18 ? (crouch && !moAirDuck ? T("crouch in the air: the base's jumpers do") : T("short of the top: jump at the edge of the green ring"))
            : T("on top, but off the blue ring");
        ok = ok && !heard;
        moJumps.Add((ok, why, off, moAirDuck));
        if (!ok && !heard) mgLift++;   // a guided self-test: its next jump higher
        St("mojump", new() { ["ok"] = ok, ["why"] = why, ["off"] = R1(off), ["dz"] = R1(dz), ["chain"] = moChain, ["at"] = R3(at), ["hv"] = R1(moAirHv) });
        Html(ok ? $"<font color='#5ad15a'>✔ {T("LANDED")}</font> · {F("{a}/{b} landed", "a", moJumps.Count(j => j.ok), "b", Math.Max(1, drill.Goal))}"
                : $"<font color='#ff5a5a'>✘ {T("MISSED")}</font> · {why}", 2);
        var g = generation;
        AddTimer(ok ? 1.2f : 1.6f, () => { if (g == generation && phase == "live") MoNext(); });
    }

    // a stop: at full speed 0.25 s, STOP 0.2 to 0.8 s later (still at full speed then); the drop, the stop, the way back
    void MoStopTick(CCSPlayerPawn pw, int now)
    {
        var v = pw.AbsVelocity;
        var vel = new Vector2(v?.X ?? 0f, v?.Y ?? 0f);
        var sp = vel.Length();
        switch (moStage)
        {
            case "strafe":
                if (sp >= 180f) { if (moFastSince < 0) moFastSince = now; }
                else moFastSince = -1;
                if (moFastSince >= 0 && moStopDue < 0 && now - moFastSince >= 16) moStopDue = now + Rng.Next(12, 52);
                if (moStopDue >= 0 && now >= moStopDue)
                {
                    if (sp < 180f) { moStopDue = -1; break; }   // slowed down on its own: full speed again first
                    moStage = "brake";
                    moStopAt = now; moTop = sp; moWay = Vector2.Normalize(vel); moDropAt = moStillAt = -1;
                    Html($"<font color='#ff5a5a' class='fontSize-xl'>■ {T("STOP")}</font>", 1);
                }
                break;
            case "brake":
                if (moDropAt < 0 && sp < 0.92f * moTop) moDropAt = now;
                if (sp <= StopShare * moTop) { moStillAt = now; moStage = "over"; }
                else if (now - moStopAt > 96) MoStopDone(false);   // 1.5 s: no stop
                break;
            case "over":
                if (Vector2.Dot(vel, moWay) < -StopShare * moTop) MoStopDone(true);   // off again the other way
                else if (now - moStillAt >= 20) MoStopDone(false);
                break;
        }
    }

    void MoStopDone(bool over)
    {
        if (drill == null) return;
        moStage = "after";
        var drop = moDropAt >= 0 ? moDropAt : moStopAt;
        var react = (drop - moStopAt) / 64.0;
        var brake = moStillAt >= 0 ? (moStillAt - drop) / 64.0 : -1;
        var why = moStillAt < 0 ? T("no stop") : over ? T("the other key held too long: you went the other way")
            : brake > BrakeOk ? T("a key let go only: tap the other one") : "";
        moStops.Add((react, brake, over, why));
        St("mostop", new() { ["react"] = Math.Round(react, 3), ["brake"] = Math.Round(brake, 3), ["over"] = over, ["why"] = why });
        var ms = brake >= 0 ? $"{Math.Round(brake * 1000)} ms" : "";
        Html(why == "" ? $"<font color='#5ad15a'>✔ {T("DEAD STOP")}</font> · {ms}" : $"<font color='#ff5a5a'>✘ {why}</font>{(ms != "" ? $" · {ms}" : "")}", 1);
        var g = generation;
        AddTimer(0.8f, () => { if (g == generation && phase == "live") MoNext(); });
    }

    // the guide's moves, before the drill looks at it: along the line at a knife's run or a walk, a strafe then a dead stop
    // on STOP, a jump from the green ring (or from the step it landed on) onto the next ring, high enough to clear its edge
    void MoGuideDrive(CCSPlayerPawn pw, int now)
    {
        if (drill == null || pw.AbsOrigin is not { } o) return;
        var at = new Vector3(o.X, o.Y, o.Z);
        var ground = (pw.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0;
        mgGround = ground ? mgGround + 1 : 0;
        if (now % 32 == 0 && moStage is "jump" or "air")   // what it is doing, for the self-test's report
            St("mg", new() { ["stage"] = moStage, ["at"] = R3(at), ["ground"] = ground, ["v"] = pw.AbsVelocity is { } gv ? R3(new Vector3(gv.X, gv.Y, gv.Z)) : null,
                ["move"] = pw.MoveType.ToString(), ["chain"] = moChain, ["next"] = mgNext - now });
        switch (moStage)
        {
            case "run" when drill.Line.Count > 1:
            {
                var speed = drill.Variant == "silent" ? 120f : 245f;
                mgS += speed / 64f;
                var (p, dir) = LineAt(drill.Line, mgS);
                pw.Teleport(p + new Vector3(0f, 0f, 2f), new Vector3(0f, MathF.Atan2(dir.Y, dir.X) * 180f / MathF.PI, 0f), new Vector3(dir.X * speed, dir.Y * speed, 0f));
                break;
            }
            case "jump" when now >= mgNext && drill.From is { Length: >= 3 } f:
            {
                var land = moChain < drill.Marks.Count ? drill.Marks[moChain] : drill.Target;
                if (land is not { Length: >= 3 }) break;
                // onto the green ring first, still; one just past a box's edge (the jumpers' takeoff a hair after they left it:
                // 17/10, Ancient's T Lower, 50 u over the floor it fell to, put back there for ever) a little back on the box
                var back = new Vector2(f[0] - land[0], f[1] - land[1]);
                back = back.Length() > 1f ? Vector2.Normalize(back) : Vector2.Zero;
                var spot = new Vector3(f[0] + back.X * 8f * mgProbe, f[1] + back.Y * 8f * mgProbe, f[2]);
                // the green ring is a takeoff seen a tick after it, crouched: the feet up to 20 u over the floor already (22/10,
                // Dust2's mid doors climb: its floor 13.6 u under it, the guide put back there for ever, then back into the door)
                if (moChain == 0 && ground && (Flat(at, new[] { spot.X, spot.Y }) > 12f || at.Z > spot.Z + 12f || at.Z < spot.Z - 24f))
                {
                    if (mgPlaced && mgProbe < 6)
                    {   // put there, it fell off: further back
                        mgProbe++;
                        spot = new Vector3(f[0] + back.X * 8f * mgProbe, f[1] + back.Y * 8f * mgProbe, f[2]);
                    }
                    mgPlaced = true;
                    pw.Teleport(new Vector3(spot.X, spot.Y, spot.Z + 2f), null, Vector3.Zero);
                    Crouch(pw, false);
                    moWasGround = true;
                    mgNext = now + 24;
                    break;
                }
                if (mgGround < 4) break;
                var dz = land[2] - at.Z;
                var lift = new[] { 36f, 64f, 96f, 128f }[Math.Min(mgLift, 3)];
                var vz = MathF.Max(280f, MathF.Sqrt(1600f * (MathF.Max(dz, 0f) + lift)));   // its top that high over the landing (gravity 800)
                var t = (vz + MathF.Sqrt(MathF.Max(0f, vz * vz - 1600f * dz))) / 800f;
                var flat = new Vector2(land[0] - at.X, land[1] - at.Y);
                var hv = flat.Length() / MathF.Max(0.1f, t);
                if (drill.How == "walk")
                {   // walked (Shift held): off the ground at a walk's speed at most (over 140 u/s they hear you), as high as
                    // the others; the rest of the way in the air, over the ledge (22/10: Fachwerk's stairs to the window, a crouched
                    // jump with the air's push, 92 u over Mid's drop: the game's bare 302 u/s fell into it every try since 20/10)
                    hv = MathF.Min(130f, flat.Length() / MathF.Max(0.1f, t));
                }
                var d = flat.Length() > 1f ? Vector2.Normalize(flat) : Vector2.Zero;
                pw.Teleport(null, new Vector3(0f, MathF.Atan2(d.Y, d.X) * 180f / MathF.PI, 0f), new Vector3(d.X * hv, d.Y * hv, vz));
                Crouch(pw, mgLift > 0);   // the base's jumpers crouch in the air: the feet up
                mgTo = land;
                mgPlaced = false;
                St("guided", new() { ["jump"] = moChain, ["from"] = R3(at), ["to"] = land, ["vz"] = R1(vz), ["hv"] = R1(hv), ["lift"] = lift });
                mgNext = now + 32;
                break;
            }
            case "air" when mgTo is { Length: >= 3 } to:
            {   // over the edge: on toward the ring, as W held in the air does (17/10: Cache's Electrical Box, its jump along
                // the box's side lost its way there and came down where it left, 4 times)
                var flat = new Vector2(to[0] - at.X, to[1] - at.Y);
                if (at.Z > to[2] + 4f && flat.Length() > 4f)
                {
                    var d = Vector2.Normalize(flat) * MathF.Min(250f, MathF.Max(60f, flat.Length() * 6f));
                    pw.Teleport(null, null, new Vector3(d.X, d.Y, pw.AbsVelocity?.Z ?? 0f));
                }
                break;
            }
            case "strafe":
            {
                var yr = (drill.Me?.Ang[1] ?? 0f) * MathF.PI / 180f;
                if (now >= mgNext) { mgDir = -mgDir; mgNext = now + 44; }
                var side = new Vector2(MathF.Sin(yr), -MathF.Cos(yr)) * (250f * mgDir);
                pw.Teleport(null, null, new Vector3(side.X, side.Y, pw.AbsVelocity?.Z ?? 0f));
                break;
            }
            case "brake" or "over":
                pw.Teleport(null, null, new Vector3(0f, 0f, pw.AbsVelocity?.Z ?? 0f));   // the other key tapped: still at once
                break;
        }
    }

    static (Vector3 p, Vector2 dir) LineAt(List<float[]> line, float s)
    {
        for (int i = 0; i + 1 < line.Count; i++)
        {
            var a = new Vector3(line[i][0], line[i][1], line[i][2]);
            var b = new Vector3(line[i + 1][0], line[i + 1][1], line[i + 1][2]);
            var len = Vector3.Distance(a, b);
            if (s <= len || i + 2 == line.Count)
            {
                var d = new Vector2(b.X - a.X, b.Y - a.Y);
                return (Vector3.Lerp(a, b, len > 0f ? Math.Clamp(s / len, 0f, 1f) : 1f), d.Length() > 0f ? Vector2.Normalize(d) : Vector2.UnitX);
            }
            s -= len;
        }
        var l = line[^1];
        return (new Vector3(l[0], l[1], l[2]), Vector2.UnitX);
    }

    // the drill's result: ok, points, the line said (and the measures written with it)
    (bool ok, int pts, string detail) MoResult()
    {
        if (drill == null) return (false, 0, "");
        switch (drill.Variant)
        {
            case "route":
            {
                drillExtra["runs"] = moRuns.Select(r => new Dictionary<string, object> { ["valid"] = r.valid, ["time"] = Math.Round(r.time, 2), ["missed"] = r.missed }).ToList();
                drillExtra["par"] = drill.Par;
                var valid = moRuns.Where(r => r.valid).Select(r => r.time).ToList();
                var off = moRuns.Count(r => !r.valid && r.time >= 0);
                if (valid.Count == 0)
                    return (false, 0, moRuns.Count > 0 ? T("no run through every ring, in order") : T("no run"));
                var best = valid.Min();
                var ok = drill.Par <= 0 || best <= drill.Par;
                var pts = 30 * valid.Count + (ok ? 100 : 0) + (drill.Best > 0 && best <= drill.Best ? 60 : 0) + (drill.Pro > 0 && best <= drill.Pro ? 40 : 0)
                          + (int)Math.Max(0, (drill.Par - best) * 20);
                return (ok, pts, F("best run {s} s", "s", Sec(best)) + $" · {F("base {s} s", "s", Sec(drill.Par, 1))}"
                                 + (drill.Best > 0 ? $" · {F("its fastest {s} s", "s", Sec(drill.Best, 1))}" : "")
                                 + (drill.Pro > 0 ? $" · {F("pros {s} s", "s", Sec(drill.Pro, 1))}" : "")
                                 + (off > 0 ? $" · {Tn(off, "{n} run off the way", "{n} runs off the way")}" : ""));
            }
            case "jump":
            {
                drillExtra["jumps"] = moJumps.Select(j => new Dictionary<string, object> { ["ok"] = j.ok, ["off"] = Math.Round(j.off), ["duck"] = j.duck }).ToList();
                var n = moJumps.Count;
                var landed = moJumps.Count(j => j.ok);
                var ok = landed >= Math.Max(1, drill.Goal);
                var pts = 50 * landed + (ok ? 100 : 0) + (n > 0 && moJumps[0].ok ? 30 : 0);
                var why = moJumps.Where(j => !j.ok).GroupBy(j => j.why).Select(g => $" · {g.Key} ×{g.Count()}");
                return (ok, pts, n == 0 ? T("no jump from the green ring") : F("{a}/{b} landed", "a", landed, "b", n) + string.Concat(why));
            }
            case "stop":
            {
                drillExtra["stops"] = moStops.Select(s => new Dictionary<string, object> { ["react"] = Math.Round(s.react, 3), ["brake"] = Math.Round(s.brake, 3), ["over"] = s.over }).ToList();
                var n = moStops.Count;
                var clean = moStops.Count(s => s.why == "");
                var ok = n > 0 && clean * 4 >= n * 3;   // 6 of 8
                var br = moStops.Where(s => s.brake >= 0).Select(s => s.brake).ToList();
                var rc = moStops.Where(s => s.brake >= 0).Select(s => s.react).ToList();
                var why = moStops.Where(s => s.why != "").GroupBy(s => s.why).Select(g => $" · {g.Key} ×{g.Count()}");
                return (ok, 25 * clean + (ok ? 100 : 0), n == 0 ? T("no stop") : F("{a}/{b} dead stops", "a", clean, "b", n)
                    + (br.Count > 0 ? $" · {F("{ms} ms to stop", "ms", Math.Round(br.Average() * 1000))}" : "")
                    + (rc.Count > 0 ? $" · {F("{ms} ms to react", "ms", Math.Round(rc.Average() * 1000))}" : "") + string.Concat(why));
            }
            default:
            {
                drillExtra["walks"] = moWalks.Select(w => new Dictionary<string, object> { ["ok"] = w.ok, ["time"] = Math.Round(w.time, 2), ["steps"] = w.steps, ["jumps"] = w.hops }).ToList();
                drillExtra["par"] = drill.Par;
                var ok = moWalks.Any(w => w.ok);
                var w0 = moWalks.Where(w => w.ok).Concat(moWalks).FirstOrDefault();
                if (moWalks.Count == 0) return (false, 0, T("no walk"));
                return (ok, ok ? 150 + (moWalks[0].ok ? 50 : 0) : 0, ok ? $"{T("not heard")} · {Sec(w0.time, 1)} / {Sec(drill.Par, 1)} s"
                    : string.Join(" · ", moWalks.Select(w => w.time < 0 || w.time > drill.Par ? T("too slow") : w.missed > 0 ? T("off the way")
                        : Tn(w.steps + w.hops, "{n} sound heard", "{n} sounds heard"))));
            }
        }
    }
}
