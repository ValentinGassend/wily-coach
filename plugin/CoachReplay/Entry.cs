// An exec played as its entry (20/10, his 16:24 video: "une fois que j'ai fait les quatre stuff d'affilée, l'idée c'est
// de reproduire l'exec sur le même timing que je viens de faire ... les stuff vont partir comme moi je les ai envoyés
// juste avant, mais par contre sur la session, je vais être à la place de la personne qui entre, du coup ce serait bien
// de me mettre des bots sans arme, sans rien, juste pour que je sache quelles lignes décalent ... je sais que je dois
// regarder derrière la caisse ... derrière ce muret, sur le bomb site, mais je sais que charrette j'ai pas regardé,
// hauteur j'ai pas regardé, porte j'ai pas regardé, et que les ennemis vont être partiellement aveuglés"): the exec's
// grenades thrown by a teammate as you threw them in its whole drill just before (the try that had them all up at once:
// their own start and speed, their moments), else his setup's own at their moment in his exec; you armed on its spot
// nearest the site; on the site its CTs unarmed, never firing: the ones its grenades are for (a blue post: covered) and
// the ones none of them covers (a red post: to check). Done when the red ones are down; the card then says what each
// grenade did to its own (blinded, burned).
// A site defense played as its defender (21/10, the user: "fais-moi pareil ... finis les stuff de Fachwerk pour la partie
// défensive"; mode "hold"): the same, the other way round: its grenades thrown by a CT teammate at the moments you threw
// them after GO in its whole drill, you armed on its post, and the Ts of a real take of the base running their own ways
// in at their own pace, unarmed, never firing (wily/training/execs.py hold). Done when they are all down.
using System.Globalization;
using System.Numerics;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;

namespace CoachReplay;

public partial class CoachReplay
{
    bool EntryOn => drill is { Kind: "nade", Mode: "entry" or "hold" };
    bool HoldOn => drill is { Kind: "nade", Mode: "hold" };
    // the whole exec's try that had them all up at once: each grenade as you threw it, and when (tick)
    readonly List<(Nade n, int tick)> execThrows = new();
    readonly Dictionary<string, List<(Nade n, float at)>> entryThrows = new();
    readonly HashSet<int> entryDown = new();   // the enemies down (their bot index)
    // the ones you took down while its flash still had them blinded (22/10 eve, the user: "faire gagner peut-être plus de
    // points si tu tues des ennemis qui sont aveuglés lors d'une exécution. Ça veut dire que tu profites de la flash
    // travaillée, ça veut dire que tu es dans le bon timing pour jouer"): 40 points more each
    readonly HashSet<int> entryBlindKills = new();
    const int BlindKillPts = 40;
    readonly Dictionary<int, float> entryBlind = new();   // the longest each was blinded (s)
    int entryLeft;
    float entryLast;   // the moment its last grenade is thrown (s after GO)
    // the sky view (22/10 eve, the user: "à la place d'attendre bêtement sur la POV d'une personne armée ... avoir un point
    // de vue du ciel sur tous les premiers stuff ... la smoke tomber, la deuxième smoke tomber, la molo tomber ... les flash
    // et les HE ne sont pas intéressantes à voir vu de haut ... une fois que les smokes et les molos sont envoyés ...
    // réenvoyer les trois stuffs quasiment en instantané ... on POV joueur qui va devoir entrer ... on laisse dérouler avec
    // les derniers stuffs"): an entry's smokes and fires thrown seen from above, then your own eyes, the same smokes and
    // fires dropped again where they landed, the flashes and HEs coming as they came after them
    bool entrySky;
    float entryPovAt;   // when your own eyes came back (s after GO): the drill's clock from then
    int entrySkyLeft;
    readonly List<(Nade n, float at)> entryArea = new(), entrySupport = new();
    readonly List<(string type, Vector3 at)> entrySkyPops = new();
    // 22/10 eve, the user on the first sky view: "c'est très important que la caméra soit vraiment ... à fond en train de
    // regarder en bas ... une vue du ciel à 100%", "on lève peut-être aussi le bandeau ... ça cache l'endroit où la molo
    // atterrit", "raccrocher un point de transition entre la vue du ciel et la POV personnage ... on sait où on se situe,
    // dans quel timing on se situe, et on n'est pas forcément surpris par le moment où on doit reprendre le clavier":
    // straight down, no card over it, you marked on the ground, then the camera down into your eyes before you play
    readonly List<CBeam> entryMarks = new();
    Vector3 flyFrom, flyTo, flyAngFrom, flyAngTo;
    int flyStart = -1, flyEnd;
    // you on your way in meanwhile (23/10, the user: "montrer, pendant la vue du ciel, ton personnage qui avance sur le
    // chemin des T de la base jusqu'à son départ"): the base's Ts' way up to your start, walked while they land
    List<Vector3>? skyWalk;
    int skyWalkAt, skyWalkTicks;

    // a grenade of yours in the whole exec's try: kept as thrown (Recorder.cs RecThrow)
    void ExecKeep(string type, bool inc, float[]? p, float[]? v)
    {
        if (!ExecOn || !nadeWait || p == null || v == null) return;
        execThrows.Add((new Nade { Type = type, Inc = inc, By = "mate", P = p, V = v }, Server.TickCount));
        // the teammate's smoke lies there already: yours as soon as your own left your hand (22/10 eve: given at its pop,
        // 4 s of waiting a player never has; the whole exec 1 s too long for its first smoke)
        if (type == "smoke") ExecGive();
    }

    // the whole exec done (all up at once): its throws for its entry or its defense, their moments after GO
    void ExecKept()
    {
        if (drill == null || execThrows.Count == 0) return;
        entryThrows[drill.Id.Replace("exec:", "entry:")] = execThrows.Select(x => (x.n, (x.tick - t0) / 64f)).ToList();
    }

    Scenario EntryScenario(Drill d)
    {
        var s = new Scenario { Id = d.Id, Map = d.Map, Kind = "nade", Title = d.Title, Team = d.Team };
        var me = d.Me ?? new Spot();
        s.Players.Add(new Track { Sid = "me", Name = "you", Team = d.Team, Me = true, Hp = 100, Armor = 100, Helmet = true, Weapons = d.Weapons,
            Active = d.Weapons.LastOrDefault() ?? "weapon_knife", Path = new[] { me.Pos[0], me.Pos[1], me.Pos[2], me.Ang[1], me.Ang[0] } });
        var m0 = d.Members.FirstOrDefault()?.Me ?? me;   // the teammate who throws them, out of your way
        s.Players.Add(new Track { Sid = "mate", Name = T("teammate"), Team = d.Team, Hp = 100, Weapons = new() { "weapon_knife" }, Active = "weapon_knife",
            Path = new[] { m0.Pos[0], m0.Pos[1], m0.Pos[2], m0.Ang[1], 0f }, Hold = true, Still = true });
        var run = HoldModeOf(d) && d.Runners.Count >= d.Bots.Count;
        if (run) s.Step = Math.Max(1, d.Step);   // a defense: the Ts on their ways, at their samples' pace
        for (int i = 0; i < d.Bots.Count; i++)
        {
            var b = d.Bots[i];
            if (run)
                s.Players.Add(new Track { Sid = $"foe{i}", Name = b.Zone ?? "?", Team = 5 - d.Team, Hp = 100, Weapons = new() { "weapon_knife" }, Active = "weapon_knife",
                    Path = d.Runners[i].Path, Runner = true });
            else
                s.Players.Add(new Track { Sid = $"foe{i}", Name = b.Zone ?? "?", Team = 5 - d.Team, Hp = 100, Weapons = new() { "weapon_knife" }, Active = "weapon_knife",
                    Path = new[] { b.Pos[0], b.Pos[1], b.Pos[2], b.Ang[1], b.Ang[0] }, Hold = true, Still = true, Duck = b.Duck });
        }
        return s;
    }

    static bool HoldModeOf(Drill d) => d.Mode == "hold";

    int EntryIndex(Track t) => t.Sid.StartsWith("foe") && int.TryParse(t.Sid[3..], out var i) ? i : -1;

    // Place() is done: a post over each of them, blue the covered ones, red the ones to check
    void EntryPlaced()
    {
        entryDown.Clear(); entryBlind.Clear(); entryBlindKills.Clear(); runStall.Clear(); runOn.Clear();
        ClearLine();
        var blue = System.Drawing.Color.FromArgb(255, 90, 180, 255);
        var red = System.Drawing.Color.FromArgb(255, 255, 70, 70);
        if (!HoldOn)   // a defense's Ts move: no post over them
            foreach (var b in drill!.Bots)
                BeamNow(new Vector3(b.Pos[0], b.Pos[1], b.Pos[2] + 80), new Vector3(b.Pos[0], b.Pos[1], b.Pos[2] + 150), b.Seq >= 0 ? blue : red, 3f);
        entryLeft = drill!.Bots.Count(b => b.Seq < 0);
    }

    // GO: the teammate throws them as you did, from 1 s on
    void EntryGo()
    {
        var d = drill!;
        var list = entryThrows.TryGetValue(d.Id, out var mine) ? mine
            : d.Members.Where(m => m.HisNade != null).Select((m, i) => (m.HisNade!, m.At > 0 || i == 0 ? m.At : i * 3f)).ToList();
        // an entry: from 1 s on, the first one first; a defense: at their moments after GO (the Ts come on the clock)
        var first = mine != null ? list.Select(x => x.Item2).DefaultIfEmpty(0f).Min() : 0f;
        list = list.Select(x => (x.Item1, HoldOn ? MathF.Max(0f, x.Item2 - 1f) : x.Item2 - first)).ToList();
        if (selftest) St("entry_plan", new() { ["from"] = entryThrows.ContainsKey(d.Id) ? "your exec" : "his setup", ["at"] = list.Select(x => MathF.Round(x.Item2, 1)).ToList() });
        entryPovAt = 0f;
        entrySky = false;
        skyWalk = null;
        if (!HoldOn && list.Any(x => IsArea(x.Item1)) && Humans().Any(h => h.PawnIsAlive))
        {
            EntrySky(list);
            return;
        }
        EntryRun(list, 1f);
        Html(HoldOn ? $"<font color='#ff8a3d'>{T("GO")}</font> · {T("they come: your stuff goes as you threw it, hold the site")}"
            : $"<font color='#ff8a3d'>{T("GO")}</font> · {T("your exec goes as you threw it: go in when it is up")} · {F("{n} to check (red)", "n", entryLeft)}", 3);
    }

    static bool IsArea(Nade n) => n.Type is "smoke" or "molotov";

    // the teammate's throws from now on, each `lead` + its moment s from now; he leaves once the last is gone (not after the
    // sky view's: the flashes are still his)
    void EntryRun(List<(Nade, float)> list, float lead, bool leave = true)
    {
        var now = (Server.TickCount - t0) / 64f;
        entryLast = now + lead + list.Select(x => x.Item2).DefaultIfEmpty(0f).Max();
        var g = sessGen;
        foreach (var (n, at0) in list)
        {
            var at = lead - 1f + at0;
            // the teammate where it leaves his hand a moment before (its place is said in the chat); a grenade dropped
            // again where it landed (the sky view's) is no throw of his: he stays put
            if (MathF.Abs(n.V[0]) + MathF.Abs(n.V[1]) + MathF.Abs(n.V[2]) > 100f)
            AddTimer(MathF.Max(0.1f, 0.7f + at), () =>
            {
                if (g != sessGen || !EntryOn || phase != "live") return;
                foreach (var t in bots.Values.Where(t => t.Sid == "mate")) t.Path = new[] { n.P[0], n.P[1], n.P[2] - 64f, t.Path.Length > 3 ? t.Path[3] : 0f, 0f };
            });
            AddTimer(1f + at, () =>
            {
                if (g != sessGen || !EntryOn || phase != "live") return;
                var slot = bots.Where(kv => kv.Value.Sid == "mate").Select(kv => (int?)kv.Key).FirstOrDefault();
                if (slot == null || Utilities.GetPlayerFromSlot(slot.Value) is not { IsValid: true, PawnIsAlive: true } c || c.PlayerPawn.Value is not { } pw) return;
                ThrowAs(c, pw, n);
                if (MathF.Abs(n.V[0]) + MathF.Abs(n.V[1]) + MathF.Abs(n.V[2]) > 100f) EntryCallout(c, pw, n);
                if (selftest) St("entry_throw", new() { ["type"] = n.Type, ["at"] = MathF.Round((Server.TickCount - t0) / 64f, 1) });
                if (n.Type == "flash") AddTimer(1.9f, () => { if (g == sessGen) EntryBlinds(); });   // a flash pops 1.6 s after it is thrown
            });
        }
        // his last grenade gone, the teammate leaves (22/10, his test video: "les ennemis sont allés directement sur mon
        // coéquipier, ils sont restés bloqués contre ... je fais disparaître mon coéquipier"): out of their way, out of
        // the feed (a bot's own death is kept out of it)
        if (leave)
        AddTimer(entryLast - now + 1.5f, () =>
        {
            if (g != sessGen || !EntryOn || phase != "live") return;
            foreach (var kv in bots.Where(kv => kv.Value.Sid == "mate").ToList())
                if (Utilities.GetPlayerFromSlot(kv.Key) is { IsValid: true, PawnIsAlive: true } c) c.PlayerPawn.Value?.CommitSuicide(false, true);
            if (selftest) St("entry_mate_gone", new() { ["at"] = MathF.Round((Server.TickCount - t0) / 64f, 1) });
        });
    }

    // the sky view: above where the smokes and fires land, from your side, 650 u up and more the wider they spread,
    // looking down at their middle; you wait there, still, while the teammate throws them as you did
    void EntrySky(List<(Nade, float)> list)
    {
        var d = drill!;
        entryArea.Clear(); entrySupport.Clear(); entrySkyPops.Clear();
        foreach (var (n, t) in list) (IsArea(n) ? entryArea : entrySupport).Add((n, t));
        var a0 = entryArea.Min(x => x.at);
        var tg = d.Members.Where(m => m.Type is "smoke" or "molotov" && m.Target is { Length: >= 2 }).Select(m => m.Target!).ToList();
        var me = d.Me ?? new Spot();
        float cx = tg.Count > 0 ? tg.Average(t => t[0]) : me.Pos[0], cy = tg.Count > 0 ? tg.Average(t => t[1]) : me.Pos[1];
        var cz = tg.Count > 0 ? tg.Max(t => t.Length >= 3 ? t[2] : me.Pos[2]) : me.Pos[2];
        var spread = 0f;
        foreach (var a in tg) foreach (var b in tg) spread = MathF.Max(spread, MathF.Sqrt((a[0] - b[0]) * (a[0] - b[0]) + (a[1] - b[1]) * (a[1] - b[1])));
        var dx = cx - me.Pos[0]; var dy = cy - me.Pos[1]; var dl = MathF.Max(1f, MathF.Sqrt(dx * dx + dy * dy));
        var h = 700f + 0.7f * spread;
        var at = new Vector3(cx, cy, cz + h);
        var yaw = MathF.Atan2(dy, dx) * 180f / MathF.PI;   // the way you go in, up on the screen
        SkyCam(at, new Vector3(89.9f, yaw, 0f));
        // you, seen from above: a gold cross on the ground where you stand
        entryMarks.Clear();
        var gold = System.Drawing.Color.FromArgb(255, 255, 211, 77);
        var n0 = beams.Count;   // drawn at once (BeamNow): its marks kept by their place in beams
        BeamNow(new Vector3(me.Pos[0] - 70f, me.Pos[1], me.Pos[2] + 4f), new Vector3(me.Pos[0] + 70f, me.Pos[1], me.Pos[2] + 4f), gold, 10f);
        BeamNow(new Vector3(me.Pos[0], me.Pos[1] - 70f, me.Pos[2] + 4f), new Vector3(me.Pos[0], me.Pos[1] + 70f, me.Pos[2] + 4f), gold, 10f);
        entryMarks.AddRange(beams.Skip(n0));
        if (d.Approach.Count >= 2)   // your way in, a gold line on the ground, walked till about when the last one is down
        {
            skyWalk = d.Approach.Select(p => new Vector3(p[0], p[1], p[2])).ToList();
            skyWalk.Add(new Vector3(me.Pos[0], me.Pos[1], me.Pos[2]));
            skyWalkAt = Server.TickCount;
            skyWalkTicks = (int)((1f + entryArea.Max(x => x.at) - a0 + 3.5f) * 64);
            var n1 = beams.Count;
            for (int i = 0; i + 1 < skyWalk.Count; i++) BeamNow(skyWalk[i] + new Vector3(0, 0, 4), skyWalk[i + 1] + new Vector3(0, 0, 4), gold, 4f);
            entryMarks.AddRange(beams.Skip(n1));
            foreach (var hm in Humans()) hm.PlayerPawn.Value?.Teleport(skyWalk[0], new Vector3(0f, yaw, 0f), Vector3.Zero);
            if (selftest) St("entry_walk", new() { ["points"] = skyWalk.Count, ["secs"] = MathF.Round(skyWalkTicks / 64f, 1) });
        }
        entrySky = true;
        entrySkyLeft = entryArea.Count;
        entryLast = 9999f;
        EntryRun(entryArea.Select(x => (x.n, x.at - a0)).ToList(), 1f, leave: false);
        entryLast = 9999f;   // the flashes still to come
        var g = sessGen;
        var last = entryArea.Max(x => x.at) - a0;
        AddTimer(1f + last + 7f, () => { if (g == sessGen) EntryPov(); });   // a smoke that never pops: your eyes back anyway
        if (selftest) St("entry_sky", new() { ["at"] = new[] { MathF.Round(at.X), MathF.Round(at.Y), MathF.Round(at.Z) }, ["area"] = entryArea.Count, ["support"] = entrySupport.Count });
        SetMain("");   // nothing over the places they land on
    }

    // a smoke or a fire of the sky view down: where it landed kept; all down, your eyes back a moment later
    void EntrySkyPop(string type, float x, float y, float z)
    {
        if (!entrySky || !EntryOn) return;
        entrySkyPops.Add((type, new Vector3(x, y, z)));
        if (--entrySkyLeft <= 0)
        {
            var g = sessGen;
            AddTimer(2f, () => { if (g == sessGen) EntryPov(); });
        }
    }

    // your own eyes again: the smokes and fires gone, dropped again where they landed (up in a moment), then the flashes
    // and HEs as long after the last of them as they came in your exec; the drill's clock from now
    void EntryPov()
    {
        if (!entrySky || drill == null || !EntryOn || phase != "live" || flyStart >= 0) return;
        if (drill.Approach.Count >= 2 && drill.Me is { } st)   // on your start whatever the walk did
        {
            skyWalk = null;
            foreach (var hm in Humans()) hm.PlayerPawn.Value?.Teleport(new Vector3(st.Pos[0], st.Pos[1], st.Pos[2]), new Vector3(0f, st.Ang[1], 0f), Vector3.Zero);
        }
        foreach (var b in entryMarks) { if (b.IsValid) b.Remove(); beams.Remove(b); }
        entryMarks.Clear();
        ClearNades();
        var again = new List<(Nade, float)>();
        var pops = entrySkyPops.ToList();
        for (int i = 0; i < entryArea.Count; i++)
        {
            var n = entryArea[i].n;
            var k = pops.FindIndex(pp => pp.type == n.Type);
            if (k >= 0)
            {   // from just above where it landed, no speed: down at once
                var q = pops[k].at;
                pops.RemoveAt(k);
                again.Add((new Nade { Type = n.Type, Inc = n.Inc, By = "mate", P = new[] { q.X, q.Y, q.Z + 24f }, V = new[] { 0f, 0f, -50f } }, 0.12f * i));
            }
            else again.Add((n, 0.12f * i));   // never landed: thrown its own way again
        }
        EntryRun(again, 0.1f, leave: false);   // up again while the camera comes down
        entryLast = 9999f;
        // the camera down into your eyes (1.5 s), then you play
        var pw0 = Humans().FirstOrDefault(h => h.PawnIsAlive)?.PlayerPawn.Value;
        if (cam != null && pw0?.AbsOrigin is { } o && pw0.EyeAngles is { } e && cam.AbsOrigin is { } c0 && cam.AbsRotation is { } r0)
        {
            flyFrom = new Vector3(c0.X, c0.Y, c0.Z); flyAngFrom = new Vector3(r0.X, r0.Y, 0f);
            flyTo = new Vector3(o.X, o.Y, o.Z + 64f); flyAngTo = new Vector3(e.X, e.Y, 0f);
            flyStart = Server.TickCount; flyEnd = flyStart + 96;
            return;
        }
        EntryPovDone();
    }

    // under the sky view, each tick: you on your way in, at an even pace, turned the way you walk; there, you wait
    void SkyWalkTick()
    {
        if (skyWalk == null || !entrySky || flyStart >= 0) return;
        var k = Math.Clamp((Server.TickCount - skyWalkAt) / (float)Math.Max(64, skyWalkTicks), 0f, 1f);
        var total = 0f;
        for (int i = 0; i + 1 < skyWalk.Count; i++) total += Vector3.Distance(skyWalk[i], skyWalk[i + 1]);
        var want = total * k;
        var at = skyWalk[^1];
        var dir = Vector3.Zero;
        for (int i = 0; i + 1 < skyWalk.Count; i++)
        {
            var l = Vector3.Distance(skyWalk[i], skyWalk[i + 1]);
            if (want <= l) { at = Vector3.Lerp(skyWalk[i], skyWalk[i + 1], l > 0f ? want / l : 1f); dir = skyWalk[i + 1] - skyWalk[i]; break; }
            want -= l;
        }
        foreach (var hm in Humans())
            if (hm.PlayerPawn.Value is { } pw && pw.IsValid)
                pw.Teleport(at, dir.Length() > 0.1f ? new Vector3(0f, MathF.Atan2(dir.Y, dir.X) * 180f / MathF.PI, 0f) : null, Vector3.Zero);
        if (k >= 1f) skyWalk = null;
    }

    // each tick of the camera's way down (Session.cs CamTick): eased in and out, then your own eyes
    bool EntryFlyTick()
    {
        if (flyStart < 0 || cam == null || !cam.IsValid) return false;
        var k = Math.Clamp((Server.TickCount - flyStart) / (float)(flyEnd - flyStart), 0f, 1f);
        var f = k * k * (3f - 2f * k);
        // the view up from the ground before the end (22/10 eve, the user: "redresser la cam sur la fin de la transition
        // pour que la cam regarde en direction de là où le joueur regarde plutôt que regarder le sol jusqu'à la fin"):
        // its pitch your own by two thirds of the way
        var kp = Math.Clamp((k - 0.05f) / 0.6f, 0f, 1f);
        var fp = kp * kp * (3f - 2f * kp);
        var dyaw = ((flyAngTo.Y - flyAngFrom.Y + 540f) % 360f) - 180f;
        cam.Teleport(Vector3.Lerp(flyFrom, flyTo, f), new Vector3(flyAngFrom.X + (flyAngTo.X - flyAngFrom.X) * fp, flyAngFrom.Y + dyaw * fp, 0f), Vector3.Zero);
        if (k >= 1f) { flyStart = -1; EntryPovDone(); }
        return true;
    }

    // in your eyes: the flashes and HEs as long after the smokes and fires as they came in your exec (1.5 s at least,
    // said on the card), the drill's clock from now
    void EntryPovDone()
    {
        if (drill == null || !EntryOn || phase != "live") return;
        entrySky = false;
        CamStop();
        foreach (var h in Humans()) if (h.PlayerPawn.Value is { } pw) Freeze(pw, false);
        entryPovAt = (Server.TickCount - t0) / 64f;
        var lastArea = entryArea.Max(x => x.at);
        var support = entrySupport.Select(x => (x.n, MathF.Max(1.5f, x.at - lastArea))).ToList();
        EntryRun(support, 0f);
        if (selftest) St("entry_pov", new() { ["at"] = MathF.Round(entryPovAt, 1), ["support"] = support.Count });
        Log("entry: your eyes back, {0} grenade(s) to come", support.Count);   // the real-client test plays it from here
        var first = support.Select(x => x.Item2).DefaultIfEmpty(0f).Min();
        var nm = support.Count == 0 ? "" : support.OrderBy(x => x.Item2).First().n.Type == "flash" ? T("Flash") : "HE";
        Html($"<font color='#ff8a3d'>▶ {T("GO")}</font> · {(support.Count > 0 ? $"{nm} {F("in {s} s", "s", Math.Round(first + 1.6f).ToString(CultureInfo.InvariantCulture))} · " : "")}{F("{n} to check (red)", "n", entryLeft)}", 3);
    }

    // a still camera as your view (the grenade camera's prop: Session.cs), you frozen meanwhile
    void SkyCam(Vector3 at, Vector3 ang)
    {
        if (cam != null) CamStop();
        var cp = Utilities.CreateEntityByName<CDynamicProp>("prop_dynamic");
        if (cp == null) return;
        cp.DispatchSpawn();
        cp.SetModel(NullModel);
        cp.RenderMode = RenderMode_t.kRenderNone;
        Utilities.SetStateChanged(cp, "CBaseModelEntity", "m_nRenderMode");
        cp.AcceptInput("DisableShadow");
        cp.Teleport(at, ang, Vector3.Zero);
        cam = cp; camNade = null; camEnd = Server.TickCount + 60 * 64;
        foreach (var hm in Humans())
        {
            var pawn = hm.PlayerPawn.Value;
            if (pawn?.CameraServices == null) continue;
            pawn.CameraServices.ViewEntity.Raw = cp.EntityHandle.Raw;
            Utilities.SetStateChanged(pawn, "CBasePlayerPawn", "m_pCameraServices");
            Freeze(pawn, true);
        }
    }

    // the teammate says it as a player does (20/10, his video: "avoir dans le chat, comme si c'était un vrai coéquipier qui
    // envoie une smoke ... une flash, une molotov ... et du coup la voix qui dit « I'm throwing a flashbang »"): the game's
    // radio line in the chat (his team, his place) and its own voice line (the Elite Crew's), in your ears
    static readonly Dictionary<string, string[]> Callout = new()
    {
        ["smoke"] = new[] { "leet.t_smoke01", "leet.t_smoke02", "leet.t_smoke03" },
        ["flash"] = new[] { "leet.t_flashbang01", "leet.t_flashbang03", "leet.t_flashbang04" },
        ["molotov"] = new[] { "leet.t_molotov01", "leet.t_molotov02", "leet.t_molotov04", "leet.t_molotov05" },
        ["he"] = new[] { "leet.t_grenade01", "leet.t_grenade02", "leet.t_grenade03", "leet.t_grenade05" },
    };
    // a CT teammate's (the SWAT's): soundevents/vo/agents/game_sounds_swat
    static readonly Dictionary<string, string[]> CalloutCT = new()
    {
        ["smoke"] = new[] { "swat.ct_smoke01", "swat.ct_smoke02", "swat.ct_smoke03" },
        ["flash"] = new[] { "swat.ct_flashbang01", "swat.ct_flashbang02", "swat.ct_flashbang03" },
        ["molotov"] = new[] { "swat.ct_molotov01", "swat.ct_molotov02", "swat.ct_molotov03", "swat.ct_molotov04" },
        ["he"] = new[] { "swat.ct_grenade01", "swat.ct_grenade04", "swat.ct_grenade05", "swat.ct_grenade06" },
    };

    void EntryCallout(CCSPlayerController mate, CCSPlayerPawn pw, Nade n)
    {
        var word = n.Type switch { "smoke" => T("Smoke!"), "flash" => T("Flashbang!"), "he" => T("HE grenade!"), _ => n.Inc ? T("Incendiary!") : T("Molotov!") };
        // its place as the base names it (the member thrown from there), else the game's own name for it
        var m0 = drill?.Members.FirstOrDefault(m => m.Me != null && m.Place != "" && MathF.Sqrt((m.Me.Pos[0] - n.P[0]) * (m.Me.Pos[0] - n.P[0]) + (m.Me.Pos[1] - n.P[1]) * (m.Me.Pos[1] - n.P[1])) < 150f);
        var place = m0?.Place ?? pw.LastPlaceName;
        var line = $" \x10[{(mate.TeamNum == 3 ? "CT" : "T")}]\x01 \x04{mate.PlayerName}\x01{(string.IsNullOrEmpty(place) ? "" : $" @\x05{place}\x01")} : {word}";
        foreach (var h in Humans())
        {
            h.PrintToChat(line);
            if (h.PlayerPawn.Value is not { } hp || !(mate.TeamNum == 3 ? CalloutCT : Callout).TryGetValue(n.Type, out var vo)) continue;
            try
            {
                var f = new CounterStrikeSharp.API.Modules.Utils.RecipientFilter();
                f.Add(h);
                hp.EmitSound(vo[Rng.Next(vo.Length)], f, 1f, 1f);
            }
            catch (Exception) { }
        }
        if (selftest) St("entry_callout", new() { ["type"] = n.Type, ["place"] = place, ["line"] = line });
    }

    // a flash popped: how long each of them is blinded (the longest kept)
    void EntryBlinds()
    {
        foreach (var (slot, t) in bots)
        {
            var i = EntryIndex(t);
            if (i < 0 || Utilities.GetPlayerFromSlot(slot)?.PlayerPawn.Value is not { } pw) continue;
            var f = pw.FlashDuration;
            if (f > entryBlind.GetValueOrDefault(i)) entryBlind[i] = f;
        }
    }

    // a defense played as its defender: a T stopped on its way 2 s (its real player waited behind the smoke) or at its way's
    // end short of you comes on to you by the map's mesh, unarmed as it is (30/10, his review on Inferno's B and Dust2's A:
    // "si moi je vais pas chercher les joueurs derrière les smokes, jamais je croise les joueurs ... jamais ils avancent sur
    // le bon site"; Dust2's three stood 33 s outside Long)
    readonly Dictionary<int, (Vector3 At, int Tick)> runStall = new();
    readonly HashSet<int> runOn = new();
    void HoldRunners()
    {
        if (!HoldOn || cur == null || phase != "live") return;
        if (Humans().FirstOrDefault(h => h.PawnIsAlive)?.PlayerPawn.Value?.AbsOrigin is not { } mo) return;
        var goal = new Vector3(mo.X, mo.Y, mo.Z);
        var now = Server.TickCount;
        foreach (var (sl, t) in bots.ToList())
        {
            if (!t.Runner || Utilities.GetPlayerFromSlot(sl) is not { IsValid: true, PawnIsAlive: true } || Utilities.GetPlayerFromSlot(sl)!.PlayerPawn.Value is not { AbsOrigin: { } o } pw) continue;
            var here = new Vector3(o.X, o.Y, o.Z);
            if (!runOn.Contains(sl))
            {
                var ft = (now - t0) / (float)cur.Step - t.Start;
                if (ft < 0f) continue;   // not its time yet
                var ended = free.Contains(sl) || ft >= t.Frames - 1;
                if (!ended)
                {
                    if (!runStall.TryGetValue(sl, out var st) || Vector3.Distance(st.At, here) > 48f) { runStall[sl] = (here, now); continue; }
                    if (now - st.Tick < 2 * 64) continue;
                }
                runOn.Add(sl);
                free.Add(sl);   // off its recorded way: moved here from now on
                Log("hold: {n} {w}, comes on to you", t.Name, ended ? "at its way's end" : "stopped on its way");
            }
            var to = new Vector2(goal.X - here.X, goal.Y - here.Y);
            var dist = to.Length();
            if (navPts.Length > 0)
            {
                var stp = NavSteer(sl, here, goal);
                if (NavClimb(sl, here) is { } lv) { pw.Teleport(null, null, lv); continue; }   // a ladder of its mesh way
                var ts = new Vector2(stp.X - here.X, stp.Y - here.Y);
                if (ts.Length() > 1f) to = ts;
            }
            var cv = pw.AbsVelocity is { } av ? new Vector2(av.X, av.Y) : Vector2.Zero;
            var want = dist < 150f || to.Length() < 1f ? Vector2.Zero : Vector2.Normalize(to) * (dist > 700f ? 230f : 200f);
            var dv = want - cv;
            if (dv.Length() > 24f) dv = Vector2.Normalize(dv) * 24f;
            var v = PastFriction(cv + dv, (pw.Flags & (uint)CounterStrikeSharp.API.Modules.Utils.PlayerFlags.FL_ONGROUND) != 0);
            var yaw = want.Length() > 1f ? MathF.Atan2(want.Y, want.X) * 180f / MathF.PI : MathF.Atan2(goal.Y - here.Y, goal.X - here.X) * 180f / MathF.PI;
            SetEyes(pw, new Vector3(0f, yaw, 0f));
            pw.Teleport(null, new Vector3(0f, yaw, 0f), new Vector3(v.X, v.Y, pw.AbsVelocity?.Z ?? 0f));
        }
    }

    void EntryTick(float el)
    {
        var d = drill!;
        HoldRunners();
        if (entrySky)
        {
            SetMain("");   // the sky view: nothing over it
            return;
        }
        el -= entryPovAt;   // its clock from your own eyes back
        var left = (int)Math.Max(0, d.Seconds - el);
        if (el >= d.Seconds) { EntryEnd(false); return; }
        var todo = d.Bots.Select((b, i) => (b, i)).Where(x => x.b.Seq < 0 && !entryDown.Contains(x.i)).Select(x => x.b.Zone).Distinct();
        var cover = d.Members.Select(Short);
        // what is left to do first and big (23/10: the instruction on top), then the drill, then what its grenades cover
        SetMain($"{Big(HoldOn ? F("{n} to stop: {where}", "n", todo.Count(), "where", string.Join(", ", todo)) : F("to check: {where}", "where", string.Join(", ", todo)), "#ff5a5a")}"
                + $"<br><font color='#ff8a3d'>{d.Title}</font> · {left} s · ⭐ {points}"
                + $"<br><font class='fontSize-s' color='#5ab4ff'>{F("covered: {what}", "what", string.Join(" · ", cover))}</font>");
    }

    // an enemy down: yours to check, or one of theirs; you down (your own fire): the try is over
    bool EntryDeath(EventPlayerDeath e, CCSPlayerController v)
    {
        if (!v.IsBot) return false;
        if (!bots.TryGetValue(v.Slot, out var t) || EntryIndex(t) is var i && i < 0) return false;
        if (e.Attacker is { IsValid: true, IsBot: false } && v.PlayerPawn.Value is { } vp && vp.BlindUntilTime > Server.CurrentTime && entryBlindKills.Add(i))
        {
            Html($"<font color='#ffd34d'>💥 {F("down blinded: +{p}", "p", BlindKillPts)}</font>", 1);
            Log("entry: down blinded {0}", i);
        }
        EntryHit(i);
        return false;
    }

    void EntryHit(int i)
    {
        if (!entryDown.Add(i) || drill == null) return;
        if (selftest) St("entry_down", new() { ["i"] = i, ["zone"] = drill.Bots[i].Zone, ["seq"] = drill.Bots[i].Seq });
        Log("entry: down {0}", i);
        var n = drill.Bots.Count(b => b.Seq < 0) - drill.Bots.Select((b, k) => (b, k)).Count(x => x.b.Seq < 0 && entryDown.Contains(x.k));
        if (n <= 0) AddTimer(0.5f, () => { if (EntryOn && phase == "live") EntryEnd(true); });
        else Html($"<font color='#ff8a3d'>{F("{n} to check", "n", n)}</font>", 1);
    }

    // the end: the ones to check down or not, and what each grenade did to its own
    void EntryEnd(bool ok)
    {
        var d = drill!;
        var el = (Server.TickCount - t0) / 64f - entryPovAt;
        var parts = new List<string>();
        for (int k = 0; k < d.Members.Count; k++)
        {
            // a flash blinds any of them, a fire burns any; a smoke keeps its place empty (20/10, his video: "l'idée c'est
            // de montrer l'intérêt justement d'avoir ces stuff, pour éviter qu'il y ait des joueurs dans ces zones-là")
            var m = d.Members[k];
            var all = Enumerable.Range(0, d.Bots.Count);
            // a flash's victims' blind times said (23/10, the user: "temps d'aveuglement de la victime dans le bandeau")
            var bl = all.Select(i => entryBlind.GetValueOrDefault(i)).Where(s => s > 0.5f).OrderByDescending(s => s).ToList();
            var what = m.Type == "flash" ? F("{n} blinded", "n", bl.Count) + (bl.Count > 0 ? $" ({string.Join(", ", bl.Select(s => s.ToString("F1", CultureInfo.InvariantCulture)))} s)" : "")
                : m.Type is "molotov" or "he" ? F("{n} burned", "n", all.Count(EntryHurt))
                : T("its place kept empty");
            if (parts.Any(x => x.StartsWith(Short(m)))) continue;
            parts.Add($"{Short(m)}: {what}");
        }
        if (selftest)
            foreach (var (b, i) in d.Bots.Select((b, i) => (b, i)))
                St("entry_bot", new() { ["i"] = i, ["zone"] = b.Zone, ["seq"] = b.Seq, ["blind"] = MathF.Round(entryBlind.GetValueOrDefault(i), 2), ["hurt"] = EntryHurt(i), ["down"] = entryDown.Contains(i) });
        if (entryBlindKills.Count > 0) parts.Insert(0, F("{n} down blinded by your flashes (+{p} each)", "n", entryBlindKills.Count, "p", BlindKillPts));
        var detail = string.Join(" · ", parts);
        var notDown = d.Bots.Where((b, i) => b.Seq < 0 && !entryDown.Contains(i)).Count();
        if (ok) DrillDone(true, HoldOn ? "held" : "cleared", 100 + 30 * d.Bots.Count(b => b.Seq < 0) + BlindKillPts * entryBlindKills.Count,
            $"{(HoldOn ? F("held in {s} s", "s", el.ToString("F0", CultureInfo.InvariantCulture)) : F("checked in {s} s", "s", el.ToString("F0", CultureInfo.InvariantCulture)))} · {detail}");
        else DrillDone(false, "timeout", 20 * entryDown.Count(i => d.Bots[i].Seq < 0) + BlindKillPts * entryBlindKills.Count, $"{(HoldOn ? F("{n} got through", "n", notDown) : F("{n} not checked", "n", notDown))} · {detail}");
    }

    bool EntryHurt(int i)
    {
        foreach (var (slot, t) in bots)
            if (EntryIndex(t) == i) return Utilities.GetPlayerFromSlot(slot)?.PlayerPawn.Value is not { } pw || pw.Health < 100;
        return false;
    }

    // a guided self-test: once the last grenade is up, the ones to check taken down for you (it can't aim)
    void EntryGuide(float el)
    {
        if (!(selftest && stGuided) || drill == null) return;
        if (HoldOn)
        {   // a defense: each T once it went through its grenade's place (what it did to them measured) and the last
            // grenade is up (a later one is for the ones still coming), one a tick
            for (int i = 0; i < drill.Bots.Count && i < drill.Runners.Count; i++)
                if (!entryDown.Contains(i) && el >= MathF.Max(drill.Runners[i].Arrive + 2.5f, entryLast + 2.5f))
                {
                    EntryHit(i);
                    return;
                }
            return;
        }
        if (el < entryLast + 4f) return;   // its last grenade up first
        foreach (var (b, i) in drill.Bots.Select((b, i) => (b, i)).ToList())
            if (b.Seq < 0 && !entryDown.Contains(i))
            {
                EntryHit(i);
                return;   // one a tick
            }
    }
}
