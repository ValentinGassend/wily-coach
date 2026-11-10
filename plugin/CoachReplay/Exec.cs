// The whole of a site take or defense at once (19/10, his 21:19 video: "prépare une prise de B. À ce moment-là, tu vas me
// dropper une smoke au sol, et tu vas me donner une smoke et une molo. Et moi, je vais devoir reproduire les trois stuff
// ... l'idée, c'est d'avoir les trois stuff en même temps sur le bombsite ... même s'ils ne sont pas tous envoyés en même
// temps"): its lineups (Members, each worked on its own just before it: wily/training/execs.py), their grenades in your
// hands but the second smoke, a teammate's, given once your first one is thrown (a grenade made on the floor by the plugin
// crashed the server, 20/10); their spots, aims and rings all drawn; done when all of them are up on their spots at the
// same moment (a smoke 17 s, a fire 7 s, a flash or an HE within 5 s).
using System.Globalization;
using System.Numerics;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;

namespace CoachReplay;

public partial class CoachReplay
{
    bool ExecOn => drill is { Kind: "nade", Mode: "exec" };
    readonly Dictionary<int, int> exUp = new();   // a member: the tick its grenade stays up till
    // a defense (21/10): the members whose grenade came down on its spot. Not all up at once: each at its own moment
    // (a flash or an HE is up for an instant, thrown from four corners), all of them before the Ts are on the site
    readonly HashSet<int> exLanded = new();
    bool DefenseOn => drill is { Mode: "exec", Arrive: > 0 };
    int exBest, exPops;   // the most up at once; the grenades popped this try
    // a take's HEs: on their spots this try, whenever, before its flash (30/10, the user: "s'il y a des HE dans les setups de
    // stuff, forcément, elle ne peut pas être active en même temps que les autres stuff ... tu peux les exclure de timing
    // d'activité pour valider le stuff. Par contre, il faut qu'elle soit présente dans l'exec ... tant que c'est pas le dernier
    // stuff à envoyer s'il y a des flashs. En fait, les flashs, c'est systématiquement le dernier stuff à envoyer")
    readonly HashSet<int> exHe = new();
    bool exFlashed;   // a flash of this try popped
    readonly Dictionary<int, float> exOff = new();   // a member: how far from its spot its last grenade came down (23/10: said in the banner)
    int exGuide, exGuideAt;   // a guided self-test: the next member its bot throws, and when
    bool exGiven;   // the teammate's smoke given
    // a flying flash's vertical speed at the last tick: a bounce on the floor turns it up (19/10, his video: "les flashs
    // sont mieux quand on n'entend pas les flashs rebondir sur le sol"); off a wall it goes on (a pop around a corner)
    readonly Dictionary<uint, float> flashVz = new();
    int flashUntil;

    // how long a grenade counts as up: a smoke, a fire; a flash and an HE are a moment, counted 5 s (20/10, the guided
    // test: an HE 1.5 s and the flash thrown 3 s after it were never up together, every grenade on its spot)
    static float ExecLasts(string type) => type switch { "smoke" => 17f, "molotov" => 7f, _ => 5f };

    void RegisterExec()
    {
        RegisterEventHandler<EventGrenadeBounce>((e, _) => { NadeBounce(e.Userid); return HookResult.Continue; });
        RegisterListener<Listeners.OnEntitySpawned>(ent =>
        {
            if (ent.DesignerName == "flashbang_projectile") flashUntil = Server.TickCount + 4 * 64;
            // your first smoke thrown: the teammate's in your hands at once (20/10, his video: "il faudrait que je la
            // récupère avant qu'elle n'explose": given when it popped, 6 s later, it came too late)
            if (ent.DesignerName == "smokegrenade_projectile" && ExecOn && !exGiven)
            {
                var h = ent.Handle;
                Server.NextFrame(() =>
                {
                    var g = new CBaseCSGrenadeProjectile(h);
                    if (g.IsValid && g.Thrower.Value?.OriginalController.Value is { IsValid: true, IsBot: false }) AddTimer(0.4f, ExecGive);
                });
            }
        });
        RegisterListener<Listeners.OnTick>(() =>
        {
            if (Server.TickCount > flashUntil) { if (flashVz.Count > 0) flashVz.Clear(); return; }
            foreach (var f in Utilities.FindAllEntitiesByDesignerName<CBaseEntity>("flashbang_projectile"))
                if (f.IsValid && f.AbsVelocity is { } v) flashVz[f.Index] = v.Z;
        });
    }

    // a bounce of your flash before it pops (a guided self-test's bot's, css_dbgthrow's): on the floor, they hear it
    void NadeBounce(CCSPlayerController? u)
    {
        if (u is not { IsValid: true }) return;
        var mine = sess != null && cur?.Kind == "nade" && nadeStage == "throw" && nadeWait && (!u.IsBot || IsGuide(u));
        var dbg = dbgThrowBy >= 0 && u.Slot == dbgThrowBy;
        if (!mine && !dbg) return;
        // its flash in the air (the game's event tells the thrower only)
        var f = Utilities.FindAllEntitiesByDesignerName<CBaseCSGrenadeProjectile>("flashbang_projectile")
            .LastOrDefault(e => e.IsValid && e.Thrower.Value?.OriginalController.Value is { } tc && tc.Slot == u.Slot);
        if (f == null) return;   // not a flash
        var before = flashVz.TryGetValue(f.Index, out var b) ? b : 0f;
        AddTimer(0.05f, () =>
        {
            var after = f.IsValid && f.AbsVelocity is { } v ? v.Z : 0f;
            var floor = before < -10f && after > 10f;
            if (dbg) { if (floor) dbgBounces++; else dbgWalls++; }
            if (mine && floor) nadeBounces++;
        });
    }

    Scenario ExecScenario(Drill d)
    {
        var s = new Scenario { Id = d.Id, Map = d.Map, Kind = "nade", Title = d.Title, Team = d.Team };
        var me = d.Members.FirstOrDefault()?.Me ?? d.Me ?? new Spot();
        var w = new List<string> { "weapon_knife" };
        w.AddRange(d.Weapons);
        // from near its first spot, as its grenades one by one (20/10, his video: "que je spawne pas exactement sur les
        // endroits de stuff, mais comme le truc d'avant, un peu plus loin")
        var (st, sa) = d.Start is { Length: >= 3 } && d.Me != null ? StepsStart(d) : (new Vector3(me.Pos[0], me.Pos[1], me.Pos[2]), new Vector3(me.Ang[0], me.Ang[1], 0f));
        s.Players.Add(new Track { Sid = "me", Name = "you", Team = d.Team, Me = true, Hp = 100, Armor = 100, Helmet = true, Weapons = w,
            Active = d.Weapons.FirstOrDefault() ?? "weapon_knife", Path = new[] { st.X, st.Y, st.Z, sa.Y, sa.X } });
        if (selftest && stGuided)   // the guided self-test's thrower: each member from its spot as its words say (ExecGuide)
            s.Players.Add(new Track { Sid = "guide", Name = "guide", Team = d.Team, Hp = 100, Weapons = new() { "weapon_knife" }, Active = "weapon_knife",
                Path = new[] { me.Pos[0], me.Pos[1], me.Pos[2], me.Ang[1], me.Ang[0] }, Hold = true, Still = true });
        return s;
    }

    // the card: each grenade's technique and click, in order
    string ExecIntro(Drill d) => string.Join("<br>", d.Members.Select((m, i) => $"{i + 1}. {Short(m)} · <font color='#ffd34d'>{HowClick(m).ToUpper()}</font>"))
        + (difficulty >= 2 ? $"<br>{T("no mark: as in a match")}" : "") + (d.Drop != null ? $"<br>{T("a teammate's smoke comes to you once your first one is thrown")}" : "");   // its instruction is the card's first line (Order)

    static string Short(Drill m) => m.Title.Split(" · ").Last();

    // Place() is done: every spot, aim and ring drawn
    void ExecPlaced()
    {
        exUp.Clear(); exLanded.Clear(); exOff.Clear(); exBest = 0; exPops = 0; exGuide = 0; exGuideAt = Server.TickCount + 2 * 64; exGiven = false;
        exHe.Clear(); exFlashed = false;
        execThrows.Clear();   // this try's throws, for its entry (Entry.cs)
        ClearLine();
        var marks = difficulty < 2;   // Hard and Expert: none, as in a match
        if (selftest) St("exec_marks", new() { ["marks"] = marks, ["difficulty"] = difficulty });
        foreach (var m in drill!.Members)
        {
            if (m.Me == null || m.Target is not { Length: >= 2 } tg) continue;
            if (marks)
            {
                if (m.Type == "flash" && tg.Length >= 3) DrawPop(tg, 120f);
                else DrawMark(tg[0], tg[1], m.Me.Pos[2], tg.Length >= 3 && m.Type != "flash" ? tg[2] : null, m.Type is "flash" or "he" or "molotov" ? 120f : 70f);
                DrawStand(m.Me);
                DrawStep(m);
                DrawCross(m);
            }
            var arc = NadeArc(m);
            OpenDoors(arc, 128f);
            Break(arc, 72f);
        }
        attemptEnd = Clock.AddSeconds(Math.Max(30, drill.Seconds));
    }

    // your first smoke is thrown: the teammate's in your hands (his "je demande à mon pote de me dropper une smoke")
    void ExecGive()
    {
        if (exGiven || drill?.Drop == null) return;
        exGiven = true;
        foreach (var h in Humans().Where(h => h.PawnIsAlive)) h.GiveNamedItem("weapon_smokegrenade");
        Html($"<font color='#56d4c8'>{T("a teammate dropped you his smoke")}</font>", 2);
        Log("exec: the teammate's smoke given");
    }

    void ExecClean() => exGiven = false;

    // a grenade of yours popped: the member it is for (its kind, the nearest spot not up yet), up if it landed there
    void ExecPop(string type, float x, float y, float z)
    {
        var now = Server.TickCount;
        int best = -1;
        float bd = float.MaxValue;
        for (int i = 0; i < drill!.Members.Count; i++)
        {
            var m = drill.Members[i];
            if (m.Type != type || m.Target is not { Length: >= 2 } tg) continue;
            var dd = MathF.Sqrt((x - tg[0]) * (x - tg[0]) + (y - tg[1]) * (y - tg[1]))
                     + ((DefenseOn ? exLanded.Contains(i) : exUp.TryGetValue(i, out var until) && until > now) ? 10000f : 0f);
            if (dd < bd) { bd = dd; best = i; }
        }
        if (type == "smoke") ExecGive();
        if (best < 0) return;
        exPops++;
        var mm = drill.Members[best];
        var d0 = bd % 10000f;
        exOff[best] = d0;
        var ok2 = type switch { "flash" or "he" => 260f, "molotov" => 240f, _ => 110f };
        var dz = mm.Target!.Length >= 3 ? z - mm.Target[2] : 0f;
        var why = d0 > ok2 ? F("{d} u from the spot", "d", Math.Round(d0)) : type == "molotov" && dz > 64f ? T("it burst in the air, before landing")
            : type == "smoke" && MathF.Abs(dz) > 96f ? T("it came down on another floor")
            : type == "he" && exFlashed && !DefenseOn ? T("after the flash: the flash goes last") : null;
        if (type == "flash") exFlashed = true;
        if (selftest) St("expop", new() { ["i"] = best, ["type"] = type, ["at"] = new[] { R1(x), R1(y), R1(z) }, ["dist"] = R1(d0), ["why"] = why });
        // in the log too (27/10, Ancient's exec B: "2/3 up at once at best", which one missed said nowhere)
        Log("exec pop {i} {type}: {d:F0} u from its spot, dz {dz:F0}{why}", best + 1, type, d0, dz, why != null ? " · " + why : "");
        var n = drill.Members.Count;
        if (DefenseOn)
        {
            if (why == null) exLanded.Add(best);
            exBest = Math.Max(exBest, exLanded.Count);
            Html(why != null ? $"<font color='#ff5a5a'>✘ {Short(mm)}</font> · {why}" : $"<font color='#5ad15a'>✔ {Short(mm)}</font> · {F("{a}/{b} on their spots", "a", exLanded.Count, "b", n)}", 2);
            if (exLanded.Count >= n)
            {
                nadeWait = false;
                var el = (Server.TickCount - t0) / 64f;
                if (el > drill.Arrive)
                {
                    // under a second said to the tenth (30/10, his review on Dust2's A: "0 s après leur arrivée", failed)
                    var late = el - drill.Arrive;
                    DrillDone(false, "late", 25 * n, F("all {n} on their spots, but {s} s after they were on the site", "n", n, "s", late.ToString(late < 1f ? "F1" : "F0", CultureInfo.InvariantCulture)));
                    return;
                }
                ExecKept();   // its throws, as you threw them, for its defense (Entry.cs)
                DrillDone(true, "perfect", 100 + 50 * n, F("all {n} on their spots, {s} s after GO, before they were on the site", "n", n, "s", el.ToString("F0", CultureInfo.InvariantCulture)));
                return;
            }
            if (exPops >= n)
            {
                var g0 = sessGen;
                AddTimer(2f, () => { if (g0 == sessGen && nadeWait && ExecOn) ExecOver(); });
            }
            return;
        }
        if (why == null && type == "molotov")
        {   // a molotov up only once its fire burns on the ground (27/10, the user: "si un stuff utilisé pour mettre des dégâts
            // ... ne fait pas de dégâts sur la personne ... c'est peut-être qu'elle a explosé en l'air. Typiquement sur Inferno,
            // t'as validé une molotov qui a explosé en l'air"): its flames looked for half a second on
            var g0 = sessGen;
            var b0 = best;
            AddTimer(0.5f, () =>
            {
                if (g0 != sessGen || !nadeWait || !ExecOn || drill == null) return;
                var burns = Utilities.FindAllEntitiesByDesignerName<CInferno>("inferno").Any(f => f.IsValid && f.FireCount > 0 && f.AbsOrigin is { } fo
                    && MathF.Sqrt((fo.X - x) * (fo.X - x) + (fo.Y - y) * (fo.Y - y)) < 220f);
                Log("exec pop {i} molotov: {b}", b0 + 1, burns ? "its fire on the ground" : "no fire, it burst in the air");
                if (!burns)
                {
                    exOff[b0] = 9999f;
                    Html($"<font color='#ff5a5a'>✘ {Short(drill.Members[b0])}</font> · {T("it burst in the air, before landing")}", 2);
                    ExecCount(false);
                    return;
                }
                exUp[b0] = Server.TickCount + (int)(ExecLasts("molotov") * 64);
                ExecCount(true, drill.Members[b0]);
            });
            return;
        }
        if (why == null) exUp[best] = now + (int)(ExecLasts(type) * 64);
        if (why == null && type == "he") exHe.Add(best);   // up for good this try: an HE is no grenade to have up with the others
        if (why != null) Html($"<font color='#ff5a5a'>✘ {Short(mm)}</font> · {why}", 2);
        ExecCount(why == null, mm);
    }

    // how many are up now: all of them, the drill's done; all thrown and not up together, the try is over
    void ExecCount(bool said, Drill? mm = null)
    {
        if (drill == null) return;
        var now = Server.TickCount;
        var n = drill.Members.Count;
        // its HEs counted once on their spots, whenever (before the flash), the rest up at once
        var upN = Enumerable.Range(0, n).Count(i => drill.Members[i].Type == "he" ? exHe.Contains(i) : exUp.TryGetValue(i, out var u) && u > now);
        exBest = Math.Max(exBest, upN);
        if (said && mm != null) Html($"<font color='#5ad15a'>✔ {Short(mm)}</font> · {F("{a}/{b} up", "a", upN, "b", n)}", 2);
        if (upN >= n)
        {
            nadeWait = false;
            var el = (Server.TickCount - t0) / 64f;
            ExecKept();   // its throws, as you threw them, for its entry or its defense (Entry.cs)
            DrillDone(true, "perfect", 100 + 50 * n, F("all {n} up at once, {s} s after GO", "n", n, "s", el.ToString("F0", CultureInfo.InvariantCulture)));
            return;
        }
        if (exPops >= n)   // all of them thrown, not up together: the try is over
        {
            var g = sessGen;
            AddTimer(2f, () => { if (g == sessGen && nadeWait && ExecOn) ExecOver(); });
        }
    }

    // each tick: what is up and for how long, the time left; a guided self-test's bot throws the next one
    void ExecTick()
    {
        var now = Server.TickCount;
        var left = Math.Max(0, (int)(attemptEnd - Clock).TotalSeconds);
        // each one's landing said (23/10, the user: "après chaque lancer : écart à l'impact ... dans le bandeau"): how far
        // from its spot, a miss in red
        string Off(int i) => exOff.TryGetValue(i, out var o) ? $" · {Math.Round(o)} u" : "";
        var parts = drill!.Members.Select((m, i) => DefenseOn ? (exLanded.Contains(i) ? $"<font color='#5ad15a'>✔ {Short(m)}{Off(i)}</font>" : exOff.ContainsKey(i) ? $"<font color='#ff5a5a'>✘ {Short(m)}{Off(i)}</font>" : $"○ {Short(m)}")
            : exUp.TryGetValue(i, out var u) && u > now ? $"<font color='#5ad15a'>✔ {Short(m)}{Off(i)} · {(u - now) / 64} s</font>" : exOff.ContainsKey(i) ? $"<font color='#ff5a5a'>✘ {Short(m)}{Off(i)}</font>" : $"○ {Short(m)}");
        var come = drill.Arrive > 0 ? (int)Math.Ceiling(drill.Arrive - (now - t0) / 64f) : -1;   // a defense: when they are on the site
        SetMain($"{Order(drill)}<br><font color='#5ab4ff'>{drill.Title}</font> · {left} s"
                + (come >= 0 ? $" · <font color='#ff5a5a'>{(come > 0 ? F("they are on the site in {s} s", "s", come) : T("they are on the site"))}</font>" : "")
                + $"<br><font class='fontSize-s'>{string.Join(" · ", parts)}</font>");
        if (selftest && stGuided) ExecGuide(now);
    }

    void ExecGuide(int now)
    {
        if (!nadeWait || now < exGuideAt || exGuide >= drill!.Members.Count) return;
        if (DefenseOn && (now - t0) / 64f < drill.Members[exGuide].At) return;   // a defense: each one at its moment after GO
        var slot = bots.Where(kv => kv.Value.Sid == "guide").Select(kv => (int?)kv.Key).FirstOrDefault();
        if (slot == null || Utilities.GetPlayerFromSlot(slot.Value) is not { IsValid: true, PawnIsAlive: true } c || c.PlayerPawn.Value is not { } pw) return;
        var m = drill.Members[exGuide++];
        if (m.Me == null) return;
        exGuideAt = now + (DefenseOn ? 96 : 3 * 64);   // a defense: the run to its next corner
        var nd = WordsNade(m);
        St("guided", new() { ["member"] = exGuide - 1, ["how"] = m.How, ["click"] = m.Click, ["type"] = m.Type, ["target"] = m.Target });
        ThrowAs(c, pw, nd);
    }

    // its time is up, not all of them together
    void ExecOver()
    {
        nadeWait = false;
        DrillDone(false, "miss", 25 * exBest, DefenseOn ? F("{a}/{b} on their spots", "a", exBest, "b", drill!.Members.Count)
            : F("{a}/{b} up at once at best", "a", exBest, "b", drill!.Members.Count));
    }
}
