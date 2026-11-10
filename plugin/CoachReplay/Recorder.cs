// The throw recorder (19/10, his 17/10 video: he showed his Fachwerk setup on the training server, "celui-là faut que tu
// me le retiennes absolument", and nothing kept where he stood and aimed): every grenade a player throws here, in a
// session or not, written to coach/throws.jsonl once it popped: where he stood, his aim, his speed, in the air or not,
// crouched or not, the grenade's own start and speed (the click it was), and where it popped. The app turns them into
// lineups and setups (wily/training/setups.py).
using System.Globalization;
using System.Numerics;
using System.Text.Json;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Utils;

namespace CoachReplay;

public partial class CoachReplay
{
    // the throws not popped yet: each player's, in the order thrown, with their grenade's entity
    readonly List<(int slot, string type, Dictionary<string, object?> rec, int tick, uint idx)> recPending = new();
    // each player's last throw (popped or not: 20/10, his !keep right after a smoke, 6 to 8 s before it popped, kept the
    // grenade before it), and the ones he kept with !keep for the setup he names with !setup
    readonly Dictionary<int, Dictionary<string, object?>> recLast = new();
    readonly Dictionary<int, List<Dictionary<string, object?>>> recKept = new();
    // his jumps too (19/10, the KZ he wants in Momentum: "je te donne des exemples de ce que j'attends"): each player's
    // jump in the air (its takeoff), and his last chain of jumps (each from where the last one landed, 2 s at most)
    readonly Dictionary<int, (Vector3 from, float speed, bool slow, int tick, float duck)> recAir = new();
    readonly Dictionary<int, (List<Dictionary<string, object?>> jumps, int landed)> recChain = new();
    // his moves (22/10, the user: "te montrer comment j'interagis, comme ça tu enregistres ce qui se passe sur mon clavier
    // ... comme ça tu comprends comment je passe le passage"): each tick from !rec to !rec again, his keys as the game
    // gets them, where he stands, his speed and his view, written to coach/moves/<name>.jsonl (no keyboard read: the
    // game's own buttons, here only)
    readonly Dictionary<int, (string name, int start, List<string> rows)> recMoves = new();

    void RegisterRecorder()
    {
        RegisterListener<Listeners.OnEntitySpawned>(ent =>
        {
            if (!ent.DesignerName.EndsWith("_projectile")) return;
            var h = ent.Handle;
            var name = ent.DesignerName;
            Server.NextFrame(() => RecThrow(h, name));   // its thrower and its speed are set on the next frame
        });
        RegisterEventHandler<EventSmokegrenadeDetonate>((e, _) => { RecPop(e.Userid, "smoke", e.X, e.Y, e.Z); return HookResult.Continue; });
        RegisterEventHandler<EventFlashbangDetonate>((e, _) => { RecPop(e.Userid, "flash", e.X, e.Y, e.Z); return HookResult.Continue; });
        RegisterEventHandler<EventHegrenadeDetonate>((e, _) => { RecPop(e.Userid, "he", e.X, e.Y, e.Z); return HookResult.Continue; });
        RegisterEventHandler<EventMolotovDetonate>((e, _) => { RecPop(e.Userid, "molotov", e.X, e.Y, e.Z); return HookResult.Continue; });
        RegisterEventHandler<EventPlayerJump>((e, _) => { RecJump(e.Userid); return HookResult.Continue; });
        RegisterListener<Listeners.OnTick>(RecTick);
        AddCommand("css_jump", "your last jump (or jumps in a row) saved for your Momentum: !jump <name>", (p, c) => RecJumpSave(p, c.ArgString));
        AddCommand("css_rec", "your moves recorded (keys, place, speed, view: each tick) till !rec again: !rec <name>", (p, c) => RecMoves(p, c.ArgString));
        // !keep after a good throw, !setup and a name once the setup is complete: his own setups, in the order thrown
        AddCommand("css_keep", "the last grenade you threw kept for your setup: !keep", (p, _) => RecKeep(p));
        AddCommand("css_setup", "the grenades you kept saved as a setup: !setup <name>", (p, c) => RecSetup(p, c.ArgString));
    }

    void RecJump(CCSPlayerController? u)
    {
        if (u is not { IsValid: true } || (u.IsBot && !IsGuide(u)) || u.PlayerPawn.Value is not { AbsOrigin: { } o } pw) return;
        var v = pw.AbsVelocity;
        var sp = v == null ? 0f : new Vector2(v.X, v.Y).Length();
        var duck = pw.MovementServices == null ? 0f : new CCSPlayer_MovementServices(pw.MovementServices.Handle).DuckAmount;
        recAir[u.Slot] = (new Vector3(o.X, o.Y, o.Z), sp, sp < 140f, Server.TickCount, duck);   // under 140 u/s: a walk's (Shift), not heard
    }

    // each tick: a jump in the air landed (on the ground again, 6 ticks after its takeoff at least): kept in his chain
    // each player's ground the tick before: a takeoff is seen leaving it going up (20/10, his "!jump" four times: "no jump
    // yet", the game's player_jump never came, as in Momentum 16/10)
    readonly Dictionary<int, bool> recGround = new();

    void RecMoves(CCSPlayerController? p, string? name)
    {
        if (p is not { IsValid: true }) return;
        if (recMoves.Remove(p.Slot, out var r))
        {
            var lines = r.rows;
            var f = System.IO.Path.Combine(Dir, "moves", $"{r.name}.jsonl");
            Io(() =>
            {
                System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(f)!);
                File.WriteAllLines(f, lines);
            });
            Say(p, $"⏺ {lines.Count} ticks ({lines.Count / 64f:F1} s) → coach/moves/{r.name}.jsonl");
            Log("moves recorded {0}: {1} ticks", r.name, lines.Count);
            return;
        }
        var n = string.Concat((name ?? "").Trim().Select(ch => char.IsLetterOrDigit(ch) || ch is '-' or '_' ? ch : '_'));
        n = Server.MapName + "_" + (n == "" ? "moves" : n) + "_" + DateTime.Now.ToString("HHmmss");   // the map first: his ways of each
        recMoves[p.Slot] = (n, Server.TickCount, new List<string>());
        Say(p, $"⏺ {T("recording your moves")}: !rec {T("again to stop")}");
        Log("moves recording {0}", n);
    }

    void RecMovesTick()
    {
        foreach (var slot in recMoves.Keys.ToList())
        {
            var c = Utilities.GetPlayerFromSlot(slot);
            if (c is not { IsValid: true } || c.PlayerPawn.Value is not { AbsOrigin: { } o } pw) continue;
            var (name, start, rows) = recMoves[slot];
            var v = pw.AbsVelocity;
            var e = pw.EyeAngles;
            var duck = pw.MovementServices == null ? 0f : new CCSPlayer_MovementServices(pw.MovementServices.Handle).DuckAmount;
            var ground = (pw.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0;
            rows.Add(string.Create(CultureInfo.InvariantCulture,
                $"{{\"t\":{Server.TickCount - start},\"p\":[{o.X:F1},{o.Y:F1},{o.Z:F1}],\"v\":[{v?.X ?? 0:F0},{v?.Y ?? 0:F0},{v?.Z ?? 0:F0}],\"a\":[{e?.X ?? 0:F2},{e?.Y ?? 0:F2}],\"b\":{(ulong)c.Buttons},\"g\":{(ground ? 1 : 0)},\"d\":{duck:F2},\"w\":\"{pw.WeaponServices?.ActiveWeapon.Value?.DesignerName}\"}}"));
            if (rows.Count > 64 * 600) RecMoves(c, null);   // 10 minutes at most: written, stopped
        }
    }

    void RecTick()
    {
        if (recMoves.Count > 0) RecMovesTick();
        foreach (var u in Humans().Concat(selftest && stGuided ? bots.Where(kv => kv.Value.Sid == "guide").Select(kv => Utilities.GetPlayerFromSlot(kv.Key)).OfType<CCSPlayerController>() : Enumerable.Empty<CCSPlayerController>()))
        {
            if (!u.IsValid || !u.PawnIsAlive || u.PlayerPawn.Value is not { } pw0) continue;
            var g = (pw0.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0;
            var was = recGround.TryGetValue(u.Slot, out var w) && w;
            recGround[u.Slot] = g;
            if (was && !g && pw0.AbsVelocity is { } v0 && v0.Z > 120f && !recAir.ContainsKey(u.Slot)) RecJump(u);
        }
        if (recAir.Count == 0) return;
        foreach (var slot in recAir.Keys.ToList())
        {
            var (from, sp, slow, tick, duck0) = recAir[slot];
            var c = Utilities.GetPlayerFromSlot(slot);
            if (c?.PlayerPawn.Value is not { AbsOrigin: { } o } pw || !c.PawnIsAlive) { recAir.Remove(slot); continue; }
            var duck = pw.MovementServices == null ? 0f : new CCSPlayer_MovementServices(pw.MovementServices.Handle).DuckAmount;
            if (duck > duck0) recAir[slot] = (from, sp, slow, tick, duck);
            if (Server.TickCount - tick < 6 || (pw.Flags & (uint)PlayerFlags.FL_ONGROUND) == 0) continue;
            recAir.Remove(slot);
            var j = new Dictionary<string, object?>
            {
                ["from"] = R3(from), ["to"] = new[] { R1(o.X), R1(o.Y), R1(o.Z) }, ["speed"] = R1(sp), ["slow"] = slow,
                ["duck"] = MathF.Round(Math.Max(duck, duck0), 2), ["air"] = MathF.Round((Server.TickCount - tick) / 64f, 2),
            };
            var chain = recChain.TryGetValue(slot, out var ch) && Server.TickCount - ch.landed <= 128 && ch.jumps.Count > 0
                        && ch.jumps[^1]["to"] is float[] last && Vector2.Distance(new Vector2(last[0], last[1]), new Vector2(from.X, from.Y)) <= 96f
                ? ch.jumps : new List<Dictionary<string, object?>>();   // from where the last one landed: one chain
            chain.Add(j);
            recChain[slot] = (chain, Server.TickCount);
            if (selftest) St("recjump", new() { ["from"] = j["from"], ["to"] = j["to"], ["chain"] = chain.Count });
        }
    }

    void RecJumpSave(CCSPlayerController? p, string? name)
    {
        if (p is not { IsValid: true }) return;
        name = (name ?? "").Trim().Trim('"').Trim();
        if (!recChain.TryGetValue(p.Slot, out var ch) || ch.jumps.Count == 0) { Say(p, T("no jump yet: jump it, then !jump and a name")); return; }
        if (name.Length == 0) { Say(p, T("!jump and a name, for example: !jump heaven from B")); return; }
        var rec = new Dictionary<string, object?>
        {
            ["t"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(), ["name"] = name.Length > 60 ? name[..60] : name, ["map"] = Server.MapName,
            ["team"] = p.PlayerPawn.Value is { } pw ? (int)pw.TeamNum : 0, ["jumps"] = ch.jumps.ToList(),
        };
        Append("jumps.jsonl", JsonSerializer.Serialize(rec));
        Say(p, Tn(ch.jumps.Count, "📌 jump saved: {name} · Wily gives it to you in your Momentum", "📌 {n} jumps in a row saved: {name} · Wily gives them to you in your Momentum", "name", rec["name"]));
        recChain.Remove(p.Slot);
    }

    void RecKeep(CCSPlayerController? p, Dictionary<string, object?>? which = null)
    {
        if (p is not { IsValid: true }) return;
        var last = which ?? (recLast.TryGetValue(p.Slot, out var l) ? l : null);
        if (last == null) { Say(p, T("no grenade to keep yet: throw it, then !keep")); return; }
        var kept = recKept.TryGetValue(p.Slot, out var k) ? k : recKept[p.Slot] = new();
        if (kept.Contains(last)) { Say(p, T("already kept: throw the next one")); return; }
        kept.Add(last);
        var what = (last["type"] as string) switch { "smoke" => T("Smoke"), "flash" => T("Flash"), "molotov" => T("Molotov"), _ => "HE" };
        Say(p, F("✔ kept: {what} · {n} in this setup · !setup and a name to save it", "what", what, "n", kept.Count));
    }

    void RecSetup(CCSPlayerController? p, string? name)
    {
        if (p is not { IsValid: true }) return;
        name = (name ?? "").Trim().Trim('"').Trim();
        if (!recKept.TryGetValue(p.Slot, out var kept) || kept.Count == 0) { Say(p, T("nothing kept yet: !keep after each good throw, then !setup and a name")); return; }
        if (name.Length == 0) { Say(p, T("!setup and a name, for example: !setup B take")); return; }
        var rec = new Dictionary<string, object?>
        {
            ["t"] = DateTimeOffset.UtcNow.ToUnixTimeSeconds(), ["name"] = name.Length > 60 ? name[..60] : name, ["map"] = Server.MapName,
            ["throws"] = kept.ToList(),
        };
        if (p.IsBot) rec["test"] = true;
        var n = kept.Count;
        kept.Clear();
        recLast.Remove(p.Slot);   // the next !keep is for the next throw, not the last one of this setup
        var tries = 0;
        void Save()
        {   // a kept smoke still rolling: written once it popped (12 s at most), where it popped with it
            var rolling = ((List<Dictionary<string, object?>>)rec["throws"]!).Any(t => !t.ContainsKey("pop") && recPending.Any(x => x.rec == t));
            if (rolling && tries++ < 12) { AddTimer(1f, Save); return; }
            Append("setups.jsonl", JsonSerializer.Serialize(rec));
            if (p.IsValid) Say(p, F("📌 setup saved: {name} · {n} grenades · Wily gives it to you in your Stuff training", "name", rec["name"], "n", n));
        }
        Save();
    }

    static string? RecType(string designer) => designer switch
    {
        "smokegrenade_projectile" => "smoke",
        "flashbang_projectile" => "flash",
        "hegrenade_projectile" => "he",
        "molotov_projectile" => "molotov",   // an incendiary's too
        _ => null,
    };

    void RecThrow(nint h, string designer)
    {
        try
        {
            var type = RecType(designer);
            // their side's grenade (the game's rethrow of yours, the guide's at the victims) is not a throw of yours
            if (type == null || nadeStage == "theirs" || stVictims) return;
            var g = new CBaseCSGrenadeProjectile(h);
            if (!g.IsValid || g.Thrower.Value?.OriginalController.Value is not { IsValid: true } c || (c.IsBot && !IsGuide(c))) return;   // a guided self-test's bot too, marked
            var pw = c.PlayerPawn.Value;
            if (pw?.AbsOrigin is not { } o || pw.EyeAngles is not { } a) return;
            // an exec's second smoke, a teammate's drop: yours the moment your first one leaves your hand, whatever the drill
            // waits for (27/10, Inferno's exec B: given only at its pop, 3-4 s more between the two smokes, never all up)
            if (ExecOn && type == "smoke" && !c.IsBot) ExecGive();
            // the whole exec's try: each grenade as it left (Entry.cs; the guide's from each spot of it, not from its hands)
            if (g.AbsOrigin is { } ga && g.AbsVelocity is { } gv)
                ExecKeep(type, designer == "molotov_projectile" && pw.TeamNum == 3, new[] { ga.X, ga.Y, ga.Z }, new[] { gv.X, gv.Y, gv.Z });
            // the game's rethrow of your last grenade (his F5 bind: sv_rethrow_last_grenade) starts where that one did, not
            // from your hands: not a throw of yours (20/10)
            if (g.AbsOrigin is { } go && Vector3.Distance(new Vector3(go.X, go.Y, go.Z), new Vector3(o.X, o.Y, o.Z + 64f)) > 96f) return;
            var v = pw.AbsVelocity;
            var duck = pw.MovementServices == null ? 0f : new CCSPlayer_MovementServices(pw.MovementServices.Handle).DuckAmount;
            var rec = new Dictionary<string, object?>
            {
                ["t"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0,
                ["map"] = Server.MapName,
                ["type"] = type,
                ["inc"] = designer == "molotov_projectile" && pw.TeamNum == 3,
                ["team"] = (int)pw.TeamNum,
                ["pos"] = new[] { R1(o.X), R1(o.Y), R1(o.Z) },
                ["ang"] = new[] { MathF.Round(a.X, 2), MathF.Round(a.Y, 2) },
                ["vel"] = v == null ? null : new[] { R1(v.X), R1(v.Y), R1(v.Z) },
                ["ground"] = (pw.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0,
                ["duck"] = MathF.Round(duck, 2),
                ["nade_at"] = g.AbsOrigin is { } p ? new[] { R1(p.X), R1(p.Y), R1(p.Z) } : null,
                ["nade_v"] = g.AbsVelocity is { } nv ? new[] { R1(nv.X), R1(nv.Y), R1(nv.Z) } : null,
                ["session"] = sess?.Id,
                ["drill"] = drill?.Id,
            };
            if (c.IsBot) rec["test"] = true;
            recPending.Add((c.Slot, type, rec, Server.TickCount, g.Index));
            if (!c.IsBot) recLast[c.Slot] = rec;
            AddTimer(15f, () =>
            {   // never popped (in the void, a decoy's way): kept anyway
                var i = recPending.FindIndex(x => x.rec == rec);
                if (i < 0) return;
                recPending.RemoveAt(i);
                Append("throws.jsonl", JsonSerializer.Serialize(rec));
            });
        }
        catch (Exception) { }
    }

    void RecPop(CCSPlayerController? u, string type, float x, float y, float z)
    {
        if (u is not { IsValid: true } || (u.IsBot && !IsGuide(u))) return;
        // the one whose grenade is where it popped (a smoke thrown later can pop first: it stops rolling sooner), else the
        // oldest of that player's of that kind
        var at = new Vector3(x, y, z);
        float Off(uint idx) => Utilities.GetEntityFromIndex<CBaseEntity>((int)idx) is { IsValid: true, AbsOrigin: { } o } ? Vector3.Distance(new Vector3(o.X, o.Y, o.Z), at) : float.MaxValue;
        var mine = recPending.Select((p, k) => (p, k)).Where(x => x.p.slot == u.Slot && x.p.type == type).ToList();
        if (mine.Count == 0) return;
        var near = mine.Select(x => (x.k, d: Off(x.p.idx))).OrderBy(x => x.d).First();
        var i = near.d < 64f ? near.k : mine[0].k;
        var rec = recPending[i].rec;
        rec["pop"] = new[] { R1(x), R1(y), R1(z) };
        rec["flight"] = MathF.Round((Server.TickCount - recPending[i].tick) / 64f, 2);
        recPending.RemoveAt(i);
        Append("throws.jsonl", JsonSerializer.Serialize(rec));
        if (u.IsBot) RecKeep(u, rec);   // a guided self-test's bot keeps each throw (its setup saved at the end, SelfTest.cs StOff)
    }
}
