// Stuff step by step (20/10, his 16:24 video: "découper la première partie de l'apprentissage, donc stuff par stuff, en
// séquence qui se valide petit à petit ... je ne dois pas apparaître déjà au bon endroit, je dois me déplacer ... tu
// détectes que je suis dans la bonne position ... tu m'indiques que je dois me concentrer sur ma visée ... une fois que
// tu détectes que mon clic gauche ou mon clic droit ou les deux sont maintenus ... tu me donnes les indications de
// mouvement ... tu vérifies que le stuff est bien apparu au bon endroit, et si c'est le cas, tu passes au stuff
// suivant"): an exec's grenades one by one, from near their spot (wily/training/execs.py, train.start_near): the green
// ring reached and stood still in, the crosshair held in the yellow circle (crouched when the aim is taken crouched),
// the clicks held, then the move; its landing checked as any stuff drill's. A grenade let go before the move is a miss.
// 22/10 eve, the user: "avoir ce toggle on quand on est sur le bon spot, le toggle on quand on vise au bon endroit, mais
// par contre si ... on part du bon spot, le toggle bon spot se repasse en off ... ne pas pouvoir utiliser ses clics tant
// qu'on n'est ni à la fois au bon spot, ni à la fois en train de viser au bon endroit ... Une fois qu'on a déverrouillé
// le bon clic, on a donc accès au bon mouvement": the spot and the aim are toggles as they are now (the spot off again
// once you leave it), the grenade's pin stays in (its clicks locked) till both are on at once, the throw is armed when
// the right clicks pull it there, then the move; the toggles written 16 times a second to coach/steps_live.json (the
// real-client test reads them, tools/real_client.py).
using System.Numerics;
using System.Text.Json;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Utils;

namespace CoachReplay;

public partial class CoachReplay
{
    bool StepsOn => drill is { Kind: "nade", Steps: true, Me: not null } && !drill.Rush && drill.Mode != "exec";
    int stepIdx;           // 0 the spot, 1 the aim, 2 the clicks, 3 the move
    int stepAtThrow = -1;  // the step you were on when the grenade left your hand (-1: not thrown yet)
    string? stepMove;      // how it left your hand, when it is not its technique (null: right)
    // a guided self-test: the guide's clicks and crouch as it plays them (a bot's own buttons are the game's), its phase
    PlayerButtons stButtons;
    bool stDuck;
    int stStepPhase, stStepAt;
    bool stArmed;          // its pin pulled with the right clicks while on the spot and aimed: the move is yours
    bool stSpot, stAim;    // the two toggles as they are now
    readonly float[] stAng = new float[2];   // the view a tick ago, how fast it turns
    int stAngAt, stAimSince = -1;
    float stRate;
    int stUnpinned;        // ticks armed with the pin back in (the grenade put away): armed no more after 16
    int stLiveAt, stLiveBusy;

    const float StepR = 10f;      // the green ring: 10 u of the spot at most, stopped
    const float StepAim = 0.9f;   // the yellow circle: 0.9 degree around the aim
    // its own when measured (23/10, the user: "le rond de visée de 0,9° est trop large pour les lancers sensibles au rebond",
    // tools/aim_tolerance.py: how far the landing moves for a tenth of a degree)
    static float AimTolOf(Drill d) => d.AimTol > 0.05f ? d.AimTol : StepAim;

    void RegisterSteps()
    {
        RegisterListener<Listeners.OnEntitySpawned>(ent =>
        {
            if (!ent.DesignerName.EndsWith("_projectile") || !StepsOn) return;
            var h = ent.Handle;
            Server.NextFrame(() =>
            {
                if (!StepsOn || !nadeWait || nadeStage != "throw" || stVictims || stepAtThrow >= 0) return;
                var g = new CBaseCSGrenadeProjectile(h);
                if (!g.IsValid) return;
                var tc = g.Thrower.Value?.OriginalController.Value;
                if (tc is not { IsValid: true } || (tc.IsBot && !IsGuide(tc))) return;
                stepAtThrow = stepIdx;
                if (!tc.IsBot && tc.PlayerPawn.Value is { } pw) stepMove = StepWrongMove(drill!, pw, g);   // the guide's throw is no move
            });
        });
    }

    // how your grenade left your hand against its technique (20/10, his video: "j'ai fait une erreur typiquement, tu ne
    // l'as pas détecté, tu me dis que mes mouvements sont corrects, mais en fait, j'ai jumpthrow"): in the air or not,
    // moving or not (setups.py's own lines: 60 u/s a walk, 160 a run), crouched or not. null: its technique
    string? StepWrongMove(Drill d, CCSPlayerPawn pw, CBaseCSGrenadeProjectile? g = null)
    {
        var h = d.How.ToLowerInvariant();
        var air = (pw.Flags & (uint)PlayerFlags.FL_ONGROUND) == 0;
        var me = d.Me!;
        var sp = pw.AbsVelocity is { } v ? MathF.Sqrt(v.X * v.X + v.Y * v.Y) : 0f;
        var duck = pw.MovementServices == null ? 0f : new CCSPlayer_MovementServices(pw.MovementServices.Handle).DuckAmount;
        bool jump = h.Contains("jumpthrow"), run = h.Contains("run") || h.Contains("forward"), walk = h.Contains("walking");
        bool crouched = h.Contains("crouch") && d.AimFrom != "crouch";
        if (air && !jump) return T("you jumped: this one is thrown with your feet on the ground");
        if (!air && jump) return T("not a jumpthrow: jump and let go at the same moment");
        if (!run && !walk && sp > 60f) return T("you were moving: this one is thrown standing still");
        if ((run || walk) && sp < 40f) return T("thrown standing still: this one is thrown moving forward");
        if (crouched && duck < 0.5f) return T("thrown standing: this one is thrown crouched");
        if (!crouched && !jump && duck > 0.5f) return T("thrown crouched: stand up to throw it");
        // from its spot: a throw that is not a run-throw leaves from the green ring (a jumpthrow a few units off it)
        if (!run && !walk && pw.AbsOrigin is { } o && MathF.Sqrt((o.X - me.Pos[0]) * (o.X - me.Pos[0]) + (o.Y - me.Pos[1]) * (o.Y - me.Pos[1])) > StepR + 8f)
            return T("thrown off the green ring: let go on the spot");
        // a jumpthrow let go as the jump starts (22/10 eve, the user on exec A's flash 5: "le moment du lancer est pas bon
        // par rapport au vrai moment ... tu lances quand tu es déjà en train de retomber"): what the jump adds to the
        // grenade's speed up, against his own (setups.jump_of) or a bind's
        if (jump && g is { IsValid: true } && g.AbsVelocity is { } gv && pw.EyeAngles is { } ea)
        {
            var el = (10f - ea.X * 80f / 90f) * MathF.PI / 180f;
            var speed = d.Click.Contains("right") ? (d.Click.Contains("left") ? 438.75f : 202.5f) : 675f;
            var add = gv.Z - speed * MathF.Sin(el);
            var want = d.Jump is { Length: >= 2 } j ? j[0] : 265f;
            if (selftest) St("jump_release", new() { ["add"] = R1(add), ["want"] = want });
            if (add < 0f) return T("let go as you came down: let go as you jump");
            if (add < want - 70f) return T("let go late in the jump: let go as you jump");
        }
        return null;
    }

    static bool IsGrenade(string name) => name is "weapon_smokegrenade" or "weapon_flashbang" or "weapon_hegrenade" or "weapon_molotov"
        or "weapon_incgrenade" or "weapon_decoy";

    // a drill (or a try of it) starts: its first step
    void StepsReset()
    {
        stepIdx = 0; stepAtThrow = -1; stepMove = null; stArmed = false; stUnpinned = 0; stSpot = stAim = false; stAimSince = -1;
        stButtons = 0; stDuck = false; stStepPhase = 0; stStepAt = Server.TickCount + 64;
    }

    // whose steps they are: yours; a guided self-test's guide when nobody plays
    CCSPlayerController? StepWho()
    {
        var h = Humans().FirstOrDefault(x => x.PawnIsAlive);
        if (h != null || !(selftest && stGuided)) return h;
        var slot = bots.Where(kv => kv.Value.Sid == "guide").Select(kv => (int?)kv.Key).FirstOrDefault();
        return slot != null && Utilities.GetPlayerFromSlot(slot.Value) is { IsValid: true, PawnIsAlive: true } c ? c : null;
    }

    // how far the crosshair is from the aim (degrees), and which way to move it: down (+) or up, right (+) or left
    static float AimOff(QAngle e, float[] want, out float down, out float right)
    {
        down = want[0] - e.X;
        var dy = ((want[1] - e.Y + 540f) % 360f) - 180f;
        right = -dy * MathF.Cos(want[0] * MathF.PI / 180f);
        return MathF.Sqrt(down * down + right * right);
    }

    // aimed crouched: a throw taken crouched, or thrown crouched on the floor; a jumpthrow crouched in the air is aimed
    // standing (20/10, his exec A flash: the crouch comes in the jump)
    static bool CrouchAim(Drill d) { var h = d.How.ToLowerInvariant(); return d.AimFrom == "crouch" || (h.Contains("crouch") && !h.Contains("jumpthrow")); }

    // its move, the last step, as said once the clicks are held
    string StepMove(Drill d)
    {
        var h = d.How.ToLowerInvariant();
        if (d.AimFrom == "crouch") return T("stand up without moving the mouse, then let go");
        if (h.Contains("jumpthrow") && h.Contains("crouch")) return T("jump, crouch in the air and let go, without moving the mouse");
        if (h.Contains("jumpthrow")) return h.Contains("forward") ? T("W, jump and let go at the same moment") : T("jump and let go at the same moment, without moving the mouse");
        if (h.Contains("walking")) return T("Shift + W and let go");
        if (h.Contains("run") || h.Contains("forward")) return T("W and let go at the same moment");
        return h.Contains("crouch") ? T("let go of the click, still crouched") : T("let go of the click");
    }

    // each tick of a step-by-step drill until its grenade is thrown: the step you are on, its card
    string StepsTick()
    {
        var d = drill!;
        var c = StepWho();
        var pw = c?.PlayerPawn.Value;
        if (c == null || pw?.AbsOrigin is not { } o || pw.EyeAngles is not { } e) return StepsCard(d, "");
        var now = Server.TickCount;
        var me = d.Me!;
        var dist = MathF.Sqrt((o.X - me.Pos[0]) * (o.X - me.Pos[0]) + (o.Y - me.Pos[1]) * (o.Y - me.Pos[1]));
        var speed = pw.AbsVelocity is { } v ? MathF.Sqrt(v.X * v.X + v.Y * v.Y) : 0f;
        var placed = dist <= StepR && MathF.Abs(o.Z - me.Pos[2]) < 32f && speed < 5f;
        var guide = IsGuide(c);
        var duck = guide ? (stDuck ? 1f : 0f) : pw.MovementServices == null ? 0f : new CCSPlayer_MovementServices(pw.MovementServices.Handle).DuckAmount;
        var crouch = CrouchAim(d);
        var off = AimOff(e, me.Ang, out var down, out var right);
        // the crosshair put in the circle, not passing through it (22/10 eve, the user: "le moment où tu déplaces ton
        // curseur, c'est beaucoup trop violent. Et du coup, ton curseur est validé comme correct alors que c'est pas tout à
        // fait le cas"): turning under 30 degrees a second there, held an eighth of a second
        var dt = Math.Max(1, now - stAngAt);
        stRate = (MathF.Abs(e.X - stAng[0]) + MathF.Abs(((e.Y - stAng[1] + 540f) % 360f) - 180f)) * 64f / dt;
        stAng[0] = e.X; stAng[1] = e.Y; stAngAt = now;
        var inCircle = off <= AimTolOf(d) && (crouch ? duck >= 0.9f : duck <= 0.1f) && stRate < 30f;
        if (!inCircle) stAimSince = -1;
        else if (stAimSince < 0) stAimSince = now;
        var aimed = inCircle && now - stAimSince >= 8;
        var btn = guide ? stButtons : c.Buttons;
        bool L = (btn & PlayerButtons.Attack) != 0, R = (btn & PlayerButtons.Attack2) != 0;
        var cl = d.Click.ToLowerInvariant();
        bool wantR = cl.Contains("right"), wantL = !wantR || cl.Contains("left");
        var clicked = L == wantL && R == wantR;
        var unlock = placed && aimed;
        var pin = false;
        if (!guide && stepAtThrow < 0 && pw.WeaponServices?.ActiveWeapon.Value is { IsValid: true } w && IsGrenade(w.DesignerName))
        {
            var gr = new CBaseCSGrenade(w.Handle);
            pin = gr.PinPulled;
            if (!stArmed && !unlock)
            {   // locked: the clicks pull nothing till you are on the spot and aimed, at once
                w.NextPrimaryAttackTick = now + 2;
                w.NextSecondaryAttackTick = now + 2;
                Utilities.SetStateChanged(w, "CBasePlayerWeapon", "m_nNextPrimaryAttackTick");
                Utilities.SetStateChanged(w, "CBasePlayerWeapon", "m_nNextSecondaryAttackTick");
                if (pin) { gr.PinPulled = false; Utilities.SetStateChanged(w, "CBaseCSGrenade", "m_bPinPulled"); pin = false; }
            }
        }
        if (stepAtThrow < 0)
        {
            if (!stArmed && unlock && clicked && (guide || pin))
            {
                stArmed = true;
                stUnpinned = 0;
                if (selftest) St("step", new() { ["i"] = 3, ["dist"] = R1(dist), ["off"] = MathF.Round(off, 2), ["duck"] = R1(duck), ["L"] = L, ["R"] = R });
            }
            else if (stArmed && !guide && !pin && ++stUnpinned > 16) stArmed = false;   // put away, not thrown: its clicks again
            else if (pin) stUnpinned = 0;
            var reach = stArmed ? 3 : !placed ? 0 : !aimed ? 1 : 2;
            if (reach != stepIdx && selftest && !stArmed) St("step", new() { ["i"] = reach, ["dist"] = R1(dist), ["off"] = MathF.Round(off, 2), ["duck"] = R1(duck), ["L"] = L, ["R"] = R });
            stepIdx = reach;
        }
        stSpot = placed; stAim = aimed;
        StepsLive(d, new[] { o.X, o.Y, o.Z }, new[] { e.X, e.Y }, placed, aimed, clicked, unlock, pin, dist, speed, off, duck);
        if (stepAtThrow >= 0) return StepsCard(d, T("in the air…"));
        return StepsCard(d, stepIdx switch
        {
            0 => $"{T("go to the green ring and stop there")} · {dist:F0} u",
            1 => (crouch ? T("crouch, crosshair in the yellow circle") : T("crosshair in the yellow circle"))
                 + (crouch && duck < 0.9f ? $" · {T("crouch")}" : !crouch && duck > 0.1f ? $" · {T("stand up")}" : "")
                 + (off > AimTolOf(d) ? $" · {(MathF.Abs(down) > 0.3f ? (down > 0 ? "↓" : "↑") : "")}{(MathF.Abs(right) > 0.3f ? (right > 0 ? "→" : "←") : "")} {off:F1}°" : ""),
            2 => F("hold {click}", "click", How(d.Click != "" ? d.Click : "left click")),
            _ => StepMove(d),
        });
    }

    // the toggles as they are now, for whoever drives or watches the drill (the real-client test): coach/steps_live.json,
    // every 4 ticks, written beside then put in place (never read half written)
    void StepsLive(Drill d, float[] o, float[] e, bool spot, bool aim, bool clicks, bool unlock, bool pin, float dist, float speed, float off, float duck)
    {
        var now = Server.TickCount;
        if ((now - stLiveAt < 4 && now >= stLiveAt) || Interlocked.Exchange(ref stLiveBusy, 1) == 1) return;
        stLiveAt = now;
        var me = d.Me!;
        var json = JsonSerializer.Serialize(new Dictionary<string, object?> { ["t"] = now, ["drill"] = d.Id, ["try"] = Math.Min(3, attempts + 1),
            ["spot"] = spot, ["aim"] = aim, ["clicks"] = clicks, ["unlock"] = unlock, ["pin"] = pin, ["armed"] = stArmed,
            ["thrown"] = stepAtThrow >= 0, ["move"] = stepMove, ["step"] = stepIdx, ["dist"] = R1(dist), ["dz"] = R1(o[2] - me.Pos[2]),
            ["speed"] = R1(speed), ["aim_off"] = MathF.Round(off, 2), ["turn"] = R1(stRate), ["duck"] = MathF.Round(duck, 2),
            ["pos"] = new[] { R1(o[0]), R1(o[1]), R1(o[2]) }, ["ang"] = new[] { MathF.Round(e[0], 2), MathF.Round(e[1], 2) } });
        if (!Io(() =>
            {
                try
                {
                    var f = System.IO.Path.Combine(Dir, "steps_live.json");
                    File.WriteAllText(f + ".tmp", json);
                    File.Move(f + ".tmp", f, true);
                }
                catch (Exception) { }
                finally { stLiveBusy = 0; }
            })) stLiveBusy = 0;
    }

    // the card: the drill, its four toggles as they are now (on green, off grey; the clicks locked till the spot and the
    // aim are on together), what to do now
    string StepsCard(Drill d, string now)
    {
        var names = new[] { T("the spot"), T("the aim"), T("the clicks"), T("the move") };
        var on = new[] { stSpot || stArmed, stAim || stArmed, stArmed, stepAtThrow >= 0 && stepMove == null };
        var bar = string.Join(" · ", names.Select((n, i) => on[i] ? $"<font color='#5ad15a'>✔ {n}</font>"
            : i == 2 && !(stSpot && stAim) ? $"<font color='#8a8a8a'>🔒 {n}</font>"
            : i == stepIdx ? $"<font color='#ffd34d'>{i + 1}. {n}</font>" : $"<font color='#8a8a8a'>{i + 1}. {n}</font>"));
        // what to do now first (23/10: the instruction on top), then the drill and its toggles, then your last throw
        return (now != "" ? $"<font color='#ffd34d' class='fontSize-l'>{now}</font><br>" : "")
               + $"<font color='#5ab4ff'>{d.Title}</font> · {F("throw {i}/3", "i", Math.Min(3, attempts + 1))}<br><font class='fontSize-s'>{bar}</font>{NadeLastLine()}";
    }

    // its grenade popped: let go before the move, a miss whatever its landing
    string? StepsEarly() => !StepsOn || stepAtThrow < 0 ? null : stepAtThrow < 3
        ? T("let go before the move: the green ring, the aim, the clicks, then the move") : stepMove;

    // where a try starts: near the spot (its start), turned to it
    (Vector3 at, Vector3 ang) StepsStart(Drill d)
    {
        var me = d.Me!;
        if (d.Start is not { Length: >= 3 } s) return (new Vector3(me.Pos[0], me.Pos[1], me.Pos[2]), new Vector3(0f, me.Ang[1], 0f));
        return (new Vector3(s[0], s[1], s[2]), new Vector3(0f, MathF.Atan2(me.Pos[1] - s[1], me.Pos[0] - s[0]) * 180f / MathF.PI, 0f));
    }

    // a guided self-test plays the steps as a player would, each one wrong first (the drill must not count it), then
    // right: on its start, to the spot turned 25° away, the aim, the wrong clicks then the right ones, then the throw as
    // its words say (SelfTest.cs WordsNade)
    void StepsGuide(CCSPlayerController c, CCSPlayerPawn pw)
    {
        var d = drill!;
        var now = Server.TickCount;
        var slot = c.Slot;
        if (!bots.TryGetValue(slot, out var t) || now < stStepAt) return;
        var me = d.Me!;
        var cl = d.Click.ToLowerInvariant();
        bool wantR = cl.Contains("right"), wantL = !wantR || cl.Contains("left");
        var right = (wantL ? PlayerButtons.Attack : 0) | (wantR ? PlayerButtons.Attack2 : 0);
        var wrong = wantL && wantR ? PlayerButtons.Attack : wantR ? PlayerButtons.Attack : PlayerButtons.Attack2;
        switch (stStepPhase)
        {
            case 0:   // on the spot, turned away: the spot counts, not the aim
                t.Path = new[] { me.Pos[0], me.Pos[1], me.Pos[2], me.Ang[1] + 25f, me.Ang[0] };
                St("guide_step", new() { ["do"] = "spot, aim 25° off" });
                stStepPhase = 1; stStepAt = now + 64;
                break;
            case 1 when stepIdx >= 1:   // the aim (crouched when it is taken crouched)
                t.Path = new[] { me.Pos[0], me.Pos[1], me.Pos[2], me.Ang[1], me.Ang[0] };
                stDuck = CrouchAim(d);
                St("guide_step", new() { ["do"] = "aim", ["step"] = stepIdx });
                stStepPhase = 2; stStepAt = now + 64;
                break;
            case 2 when stepIdx >= 2:   // the wrong clicks first
                stButtons = wrong;
                St("guide_step", new() { ["do"] = "wrong clicks", ["step"] = stepIdx });
                stStepPhase = 3; stStepAt = now + 64;
                break;
            case 3:   // then the right ones (still on the clicks step: the wrong ones must not have counted)
                St("guide_step", new() { ["do"] = "right clicks", ["step"] = stepIdx });
                stButtons = right;
                stStepPhase = 4; stStepAt = now + 32;
                break;
            case 4 when stepIdx >= 3:   // the move: thrown as its words say
                St("guide_step", new() { ["do"] = "throw", ["step"] = stepIdx });
                stButtons = 0; stDuck = false;
                guideNext = now + 4 * 64;
                guideFlyUntil = now + 6 * 64;
                guideLast = WordsNade(d);
                St("guided", new() { ["how"] = d.How, ["click"] = d.Click, ["type"] = d.Type, ["target"] = d.Target, ["steps"] = true });
                ThrowAs(c, pw, guideLast);
                stStepPhase = 5;
                break;
        }
    }

    // a try again of a step-by-step drill: you (or the guide) back on its start, its steps from the first
    void StepsAgain()
    {
        if (drill == null) return;
        var (at, ang) = StepsStart(drill);
        foreach (var h in Humans().Where(h => h.PawnIsAlive)) h.PlayerPawn.Value?.Teleport(at, ang, Vector3.Zero);
        if (selftest && stGuided)
            foreach (var t in bots.Values.Where(t => t.Sid == "guide"))
                t.Path = new[] { at.X, at.Y, at.Z, ang.Y, 0f };
        StepsReset();
    }
}
