// The training tested without a player (16/10, the user: "regarde aussi comment faire toi-même ce genre de tests pour
// éviter de me faire perdre du temps humain à tester tous les modes pendant autant de temps sur toutes les maps"):
// css_selftest <session> [timescale] plays a session with nobody on the server (no player to wait for), its clock sped
// up, and writes what a tester looks for into coach/selftest/<session>.jsonl: each drill and the bots it asked for
// against the ones that came, every time a bot left its way and was put back on it (where, how far), each bot's place
// against its way every half second, every log line (glows, frees, the drill's flow), each drill's end. Its results go
// there too, never into your progress (results.jsonl). tools/train_selftest.py plays every module on every map with it
// and reads them. What needs your hands (your shots, your jumps, your stops) is not played: a bot doesn't take your spot.
using System.Globalization;
using System.Numerics;
using System.Text.Json;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Commands;
using CounterStrikeSharp.API.Modules.Cvars;
using CounterStrikeSharp.API.Modules.Memory;
using CounterStrikeSharp.API.Modules.Memory.DynamicFunctions;

namespace CoachReplay;

public partial class CoachReplay
{
    bool selftest;
    bool stGuided;   // css_selftest ... guided: a bot throws the stuff drills as their words say (GuideTick)
    int guideNext;
    readonly HashSet<uint> guideFly = new();   // its grenades in the air: their flight noted every 8 ticks
    int guideFlyUntil;   // looked for only in the seconds after its throw (all the entities read: a cost)
    string stId = "";
    DateTime stClock0;   // the session's clock on game time (Session.cs Clock)
    int stTick0;
    int stLast;

    void RegisterSelfTest()
    {
        AddCommand("css_selftest", "the training tested without a player: css_selftest <session> [timescale 1-8] [seed]", (p, c) => CmdSelfTest(p, c));
        // the banner's duration (s) and how often it is sent again (ticks), tried out live (23/10 eve: its white flashes)
        AddCommand("css_hudtest", "the banner tried out: css_hudtest same|tick|len <seconds>", (p, c) =>
        {
            if (p != null) return;
            hudTestMode = c.GetArg(1);
            hudTestFrom = Server.TickCount;
            hudTestUntil = hudTestFrom + 64 * (int.TryParse(c.GetArg(2), out var s) ? Math.Clamp(s, 1, 60) : 8);
            Log("hudtest {m}", hudTestMode);
        });
        AddCommand("css_hud", "the banner: css_hud <seconds> <ticks>", (p, c) =>
        {
            if (p != null) return;   // the server's console or its RCON only
            if (int.TryParse(c.GetArg(1), out var s) && s >= 1 && s <= 30) hudDur = s;
            if (int.TryParse(c.GetArg(2), out var t) && t >= 1 && t <= 640) hudEvery = t;
            if (int.TryParse(c.GetArg(3), out var g) && g >= 1 && g <= 640) hudGap = g;
            Log("hud: {s} s, sent again every {t} ticks, a change after {g}", hudDur, hudEvery, hudGap);
        });
        // 17/10: bots stopped by the map where the real players walked: one driven from a point the way OnTick drives them,
        // its place logged every 4 ticks. css_dbgwalk x y z dx dy [speed 250] [ticks 96] [jump tick]
        AddCommand("css_dbgwalk", "a bot driven from a point: css_dbgwalk x y z dx dy [speed] [ticks] [jump tick]", (p, c) =>
        {
            if (cur != null) { Say(p, "a drill runs: no dbgwalk"); return; }
            var bot = Utilities.GetPlayers().FirstOrDefault(x => x.IsBot && x.PlayerPawn.Value != null);
            if (bot == null) { Server.ExecuteCommand("bot_quota 1"); Server.ExecuteCommand("bot_add_t"); Log("dbgwalk: no bot, one added: again"); return; }
            if (!bot.PawnIsAlive) bot.Respawn();
            float A(int i, float d) => float.TryParse(c.GetArg(i), NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : d;
            var at = new Vector3(A(1, 0), A(2, 0), A(3, 0));
            var dir = Vector2.Normalize(new Vector2(A(4, 0), A(5, 1)));
            var speed = A(6, 250f);
            int ticks = (int)A(7, 96f), jump = (int)A(8, -1f);
            var pw = bot.PlayerPawn.Value!;
            Freeze(pw, false);   // a session's still target left frozen walks no more
            Crouch(pw, A(9, 0f) > 0f);
            var hop = A(10, 301.99f);
            pw.Teleport(at, new Vector3(0, MathF.Atan2(dir.Y, dir.X) * 180f / MathF.PI, 0), Vector3.Zero);
            Log("dbgwalk from {a} dir {d} at {s} u/s for {t} ticks", at, dir, speed, ticks);
            var n = 0;
            dbgWalk = () =>
            {
                if (!pw.IsValid || ++n > ticks) { dbgWalk = null; return; }
                var o = pw.AbsOrigin!;
                var vz = n == jump ? hop : pw.AbsVelocity?.Z ?? 0f;
                if (n % 4 == 0 || n == 1)
                    Log("dbgwalk {n}: at {x:F1} {y:F1} {z:F1} v {v:F0} ground {g} move {m} ground ent {ge}", n, o.X, o.Y, o.Z,
                        pw.AbsVelocity is { } av ? new Vector2(av.X, av.Y).Length() : -1f, (pw.Flags & (uint)CounterStrikeSharp.API.Modules.Utils.PlayerFlags.FL_ONGROUND) != 0, pw.MoveType,
                        pw.GroundEntity?.Value?.DesignerName ?? "-");
                pw.Teleport(null, null, new Vector3(dir.X * speed, dir.Y * speed, vz));
            };
        });
        RegisterListener<Listeners.OnTick>(() => dbgWalk?.Invoke());
        // a door's angles, or set to one of its states without its motion: css_dbgdoor <index> [closed|forward|back]
        AddCommand("css_dbgdoor", "a door's angles, or set: css_dbgdoor <index> [closed|forward|back]", (p, c) =>
        {
            var e = Utilities.GetAllEntities().FirstOrDefault(x => x.IsValid && x.Index == (uint)(int.TryParse(c.GetArg(1), out var i) ? i : -1));
            if (e == null || e.DesignerName != "prop_door_rotating") { Log("dbgdoor: no door {i}", c.GetArg(1)); return; }
            var d = new CPropDoorRotating(e.Handle);
            Log("dbgdoor #{i} rot {r} closed {c} fwd {f} back {b} goal {g} mins {mi} maxs {ma}", e.Index, d.AbsRotation, d.RotationClosed, d.RotationOpenForward,
                d.RotationOpenBack, d.Goal, d.Collision?.Mins, d.Collision?.Maxs);
            var to = c.GetArg(2) switch { "closed" => d.RotationClosed, "forward" => d.RotationOpenForward, "back" => d.RotationOpenBack, _ => null };
            if (to != null) { d.Teleport(null, new Vector3(to.X, to.Y, to.Z), null); Log("dbgdoor #{i} set to {s}", e.Index, c.GetArg(2)); }
        });
        // one throw as a stuff drill's words would say, by any bot, its pop logged: css_dbgthrow <x> <y> <z> <pitch> <yaw>
        // <smoke|flash|he|molotov|inc> <still|jump|W|WJ> <left|both|right> [crouch] (17/10: a lineup the guided bot
        // missed, thrown every other way to find the one its words should say)
        AddCommand("css_dbgthrow", "a throw from words: css_dbgthrow x y z pitch yaw type still|jump|W|WJ left|both|right [crouch]", (p, c) =>
        {
            float A(int i) => float.TryParse(c.GetArg(i), NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0f;
            var bot = Utilities.GetPlayers().FirstOrDefault(x => x.IsBot && x.PlayerPawn.Value != null);
            if (bot == null) { Server.ExecuteCommand("bot_quota 1"); Server.ExecuteCommand("bot_add_t"); Log("dbgthrow: no bot, one added: again"); return; }
            if (!bot.PawnIsAlive) bot.Respawn();
            var pw = bot.PlayerPawn.Value!;
            float pitch = A(4), yaw = A(5);
            string type = c.GetArg(6), how = c.GetArg(7), click = c.GetArg(8);
            var crouch = c.GetArg(9) == "crouch";
            float el = (10f - pitch * 80f / 90f) * MathF.PI / 180f, yr = yaw * MathF.PI / 180f;
            var fw = new Vector3(MathF.Cos(el) * MathF.Cos(yr), MathF.Cos(el) * MathF.Sin(yr), MathF.Sin(el));
            var flat = new Vector3(MathF.Cos(yr), MathF.Sin(yr), 0f);
            var (speed, dz) = click == "right" ? (202.5f, -12f) : click == "both" ? (438.75f, -6f) : (675f, 0f);
            var add = (how is "jump" or "WJ" ? new Vector3(0f, 0f, 265f) : Vector3.Zero) + (how is "W" or "WJ" ? flat * 190f : Vector3.Zero);
            var src = new Vector3(A(1), A(2), A(3) + (crouch ? 46f : 64f)) + fw * 16f + new Vector3(0f, 0f, dz);
            var vel = fw * speed + add;
            dbgThrowBy = bot.Slot;
            dbgBounces = dbgWalls = 0;
            ThrowAs(bot, pw, new Nade { Type = type == "inc" ? "molotov" : type, Inc = type == "inc", By = "dbg", P = new[] { src.X, src.Y, src.Z }, V = new[] { vel.X, vel.Y, vel.Z } });
            Log("dbgthrow {t} {h} {c} from {x:F0} {y:F0}", type, how, click, src.X, src.Y);
        });
        foreach (var ev in new[] { "smoke", "flash", "he", "molotov" })
        {
            var kind = ev;
            void Pop(CCSPlayerController? u, float x, float y, float z)
            { if (dbgThrowBy >= 0 && u is { IsValid: true } && u.Slot == dbgThrowBy) Log("dbgthrow pop {k} {x:F1} {y:F1} {z:F1} bounces {b} walls {w}", kind, x, y, z, dbgBounces, dbgWalls); }
            if (kind == "smoke") RegisterEventHandler<EventSmokegrenadeDetonate>((e, _) => { Pop(e.Userid, e.X, e.Y, e.Z); return HookResult.Continue; });
            else if (kind == "flash") RegisterEventHandler<EventFlashbangDetonate>((e, _) => { Pop(e.Userid, e.X, e.Y, e.Z); return HookResult.Continue; });
            else if (kind == "he") RegisterEventHandler<EventHegrenadeDetonate>((e, _) => { Pop(e.Userid, e.X, e.Y, e.Z); return HookResult.Continue; });
            else RegisterEventHandler<EventMolotovDetonate>((e, _) => { Pop(e.Userid, e.X, e.Y, e.Z); return HookResult.Continue; });
        }
        // a stuff spot's walls, by the game's own collisions (22/10, his test video: "le spot ... il est censé être dans un
        // coin, en tout cas je suis censé pouvoir me bloquer contre un mur"): a bot stood on it and pushed 16 ways, east
        // first, counterclockwise; each way's distance gone along it. A wall stops it: a few units. css_dbgprobe <x> <y> <z>
        // whether two places see each other as the game spots players (23/10 eve, Mirage's Window: starts the bullet's
        // lines called hidden, spotted by the game at once): a CT bot on the first, a T bot on the second, turned to each
        // other, the game's own spotted masks read a moment later. css_dbgsee x1 y1 z1 x2 y2 z2 [tag] -> "dbgsee tag: a b"
        AddCommand("css_dbgsee", "two places' sight as the game spots players: css_dbgsee x1 y1 z1 x2 y2 z2 [tag]", (p, c) =>
        {
            if (p != null) return;
            float A(int i) => float.TryParse(c.GetArg(i), NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0f;
            var tag = c.GetArg(7);
            var ct = Utilities.GetPlayers().FirstOrDefault(x => x.IsBot && x.TeamNum == 3);
            var tt = Utilities.GetPlayers().FirstOrDefault(x => x.IsBot && x.TeamNum == 2);
            if (ct == null || tt == null)
            {
                Server.ExecuteCommand("bot_quota 2");
                if (ct == null) Server.ExecuteCommand("bot_add_ct");
                if (tt == null) Server.ExecuteCommand("bot_add_t");
                Log("dbgsee {tag}: no bots, added: again", tag);
                return;
            }
            if (!ct.PawnIsAlive) ct.Respawn();
            if (!tt.PawnIsAlive) tt.Respawn();
            Server.ExecuteCommand("bot_stop 1");
            var a = new Vector3(A(1), A(2), A(3));
            var b = new Vector3(A(4), A(5), A(6));
            static float Yaw(Vector3 f, Vector3 t) => MathF.Atan2(t.Y - f.Y, t.X - f.X) * 180f / MathF.PI;
            var hp = ct.PlayerPawn.Value;
            var pp = tt.PlayerPawn.Value;
            if (hp == null || pp == null) return;
            hp.Teleport(a, new Vector3(0, Yaw(a, b), 0), Vector3.Zero);
            pp.Teleport(b, new Vector3(0, Yaw(b, a), 0), Vector3.Zero);
            AddTimer(0.35f, () =>
            {
                if (!hp.IsValid || !pp.IsValid) return;
                var seen = (pp.EntitySpottedState.SpottedByMask[ct.Slot / 32] & (1u << (ct.Slot % 32))) != 0;
                var sees = (hp.EntitySpottedState.SpottedByMask[tt.Slot / 32] & (1u << (tt.Slot % 32))) != 0;
                Log("dbgsee {tag}: {a} {b}", tag, seen ? 1 : 0, sees ? 1 : 0);
            });
        });
        // many bullet's lines at once from a file (24/10: one RCON call each lost most of 954 on Mirage): coach/los_in.json
        // [[x1,y1,z1,x2,y2,z2], ...] -> coach/los_out.json [fraction, ...] in the same order
        // a bot made to fire by the plugin (28/10, the user: "forcer l'IA à jouer ... comme un vrai joueur aurait joué"):
        // its AI off (bot_zombie), its view on you, its attack button pressed each tick for n seconds; its shots counted.
        // 28/10, the user's bots "comme un vrai joueur": a bot's own command (its buttons, its view, its moves) rewritten
        // before the game runs it, so it fires and moves by the plugin's hand with the game's own physics and weapons. Is
        // CBasePlayerController::OnSimulateUserCommands (server.dll, its "RunCommand" scope) run for bots, and how is a
        // queued command laid out: css_dbgcmd [seconds]
        AddCommand("css_dbgcmd", "counts OnSimulateUserCommands per player for a while, dumps a bot's queued command", (p, c) =>
        {
            var secs = c.ArgCount > 1 && float.TryParse(c.GetArg(1), NumberStyles.Float, CultureInfo.InvariantCulture, out var sv) ? sv : 2f;
            MemoryFunctionVoid<nint>? fn;
            try { fn = new(SimCmdSig); }
            catch (Exception e) { Log("dbgcmd: no OnSimulateUserCommands: {m}", e.Message); return; }
            var srv = GameServerDll();
            var fire = c.ArgCount > 2 && c.GetArg(2) == "fire";   // IN_ATTACK written into each bot's own command
            var firePb = c.ArgCount > 2 && c.GetArg(2) == "firepb";   // into its message's buttons (CInButtonStatePB) instead
            var noPb = 0;
            var vt = new Dictionary<long, string> { [0x17b5378] = "CCSGOUserCmd", [0x17b53c0] = "CCSGOUserCmd+16", [VtUserCmd] = "CUserCmd",
                [0x18e8930] = "CSGOUserCmdPB", [VtBasePB] = "CBaseUserCmdPB", [VtButtonPB] = "CInButtonStatePB", [VtQAngle] = "CMsgQAngle",
                [0x1849438] = "CSubtickMoveStep", [0x188da38] = "CMsgVector" };
            // only what was found readable is read (28/10 23:25: a value taken for a pointer crashed server 2)
            string What(nint q) => q != 0 && srv != 0 && Readable(q, 8) && vt.TryGetValue(Rd64(q) - srv, out var n) ? n : "";
            void Dump(string tag, nint a, int len)
            {
                for (int o = 0; o < len; o += 8)
                {
                    var v = Rd64(a + o);
                    var f0 = BitConverter.Int32BitsToSingle((int)(v & 0xffffffff)); var f1 = BitConverter.Int32BitsToSingle((int)(v >> 32));
                    Log("dbgcmd: {t}+{o:X2} {v:X16}  f {a:G5} {b:G5}{w}", tag, o, v, f0, f1, What((nint)v) is { Length: > 0 } w ? "  -> " + w : "");
                }
            }
            var calls = new Dictionary<int, int>();
            var dumped = new HashSet<int>();
            var shots = new Dictionary<int, int>();
            var written = 0;
            HookResult OnFire(EventWeaponFire e, GameEventInfo i) { if (e.Userid is { IsValid: true } u) shots[u.Slot] = shots.GetValueOrDefault(u.Slot) + 1; return HookResult.Continue; }
            RegisterEventHandler<EventWeaponFire>(OnFire);
            HookResult Pre(DynamicHook h)
            {
                var ctl = h.GetParam<nint>(0);
                if (ctl == 0) return HookResult.Continue;
                var pc = new CCSPlayerController(ctl);
                var slot = pc.IsValid ? pc.Slot : -1;
                calls[slot] = calls.GetValueOrDefault(slot) + 1;
                if (firePb && pc.IsValid && pc.IsBot && srv != 0)
                {
                    var arr1 = (nint)Rd64(ctl + 0x4c8); var i1 = Rd32(ctl + 0x4d0);
                    var el1 = arr1 + Math.Max(0, i1) * 0xA0;
                    var b1 = arr1 != 0 && i1 >= 0 && Readable(el1, 0xA0) ? (nint)Rd64(el1 + 0x40) : 0;
                    var bp1 = b1 != 0 && Readable(b1, 0x48) && Rd64(b1) - srv == VtBasePB ? (nint)Rd64(b1 + 0x38) : 0;
                    if (bp1 != 0 && Readable(bp1, 0x20) && Rd64(bp1) - srv == VtButtonPB)
                    {
                        System.Runtime.InteropServices.Marshal.WriteInt64(bp1 + 0x18, Rd64(bp1 + 0x18) | 1L);
                        written++;
                    }
                    else noPb++;
                }
                if (fire && pc.IsValid && pc.IsBot && srv != 0)
                {
                    var arr0 = (nint)Rd64(ctl + 0x4c8); var i0 = Rd32(ctl + 0x4d0);
                    var bs = arr0 + Math.Max(0, i0) * 0xA0 + 0x58;   // the command's CInButtonState (its vtable, then 3 masks)
                    if (arr0 != 0 && i0 >= 0 && Readable(bs, 0x20) && Rd64(bs) - srv == VtInButton)
                    {
                        System.Runtime.InteropServices.Marshal.WriteInt64(bs + 8, Rd64(bs + 8) | 1L);
                        written++;
                    }
                }
                if (pc.IsValid && pc.IsBot && dumped.Add(slot) && dumped.Count <= 1)
                {
                    var cnt = Rd32(ctl + 0x4c4) & 0x7fffffff; var arr = (nint)Rd64(ctl + 0x4c8); var idx = Rd32(ctl + 0x4d0);
                    Log("dbgcmd: bot {n} slot {s}: queue {c} at {a:X}, index {i}, server.dll at {b:X}", pc.PlayerName, slot, cnt, arr, idx, srv);
                    if (arr != 0 && idx >= 0 && Readable(arr + idx * 0xA0, 0xA0))
                    {
                        var el = arr + idx * 0xA0;
                        Dump("cmd", el, 0xA0);
                        var b = (nint)Rd64(el + 0x40);   // the base command, if the layout is what it looks like
                        if (Readable(b, 0xC0) && What(b) == "CBaseUserCmdPB")
                        {
                            Dump("base", b, 0xC0);
                            for (int o = 0x18; o < 0xC0; o += 8)
                            {
                                var q = (nint)Rd64(b + o);
                                if (Readable(q, 0x40) && What(q) is { Length: > 0 } w) { Log("dbgcmd: base+{o:X2} -> {w}", o, w); Dump(w, q, 0x40); }
                            }
                        }
                        else Log("dbgcmd: +40 {b:X} is no CBaseUserCmdPB ({w})", b, Readable(b, 8) ? What(b) : "unreadable");
                    }
                }
                return HookResult.Continue;
            }
            fn.Hook(Pre, HookMode.Pre);
            AddTimer(secs, () =>
            {
                fn.Unhook(Pre, HookMode.Pre);
                DeregisterEventHandler<EventWeaponFire>(OnFire);
                if (fire || firePb) Log("dbgcmd {m}: IN_ATTACK written {w} times ({n} commands with no buttons message), shots {s}", firePb ? "firepb" : "fire", written, noPb,
                    string.Join(", ", shots.OrderBy(k => k.Key).Select(k => $"slot {k.Key}: {k.Value}")));
                Log("dbgcmd: in {s} s: {c}", secs, string.Join(", ", calls.OrderBy(k => k.Key).Select(k =>
                {
                    var pl = Utilities.GetPlayerFromSlot(k.Key);
                    return $"slot {k.Key} {(pl?.IsBot == true ? "bot" : "human")} {k.Value}";
                })));
            });
        });
        // the same, one step on: OnSimulateUserCommands copies a queued command, sets it as the controller's current one
        // (+0x708) and calls its virtual 0x828 (the command run). IN_ATTACK written there, before the run (Pre), and what
        // the command holds after it (Post): css_dbgcmd2 [seconds]
        AddCommand("css_dbgcmd2", "IN_ATTACK into a bot's current command before its run (controller virtual 0x828)", (p, c) =>
        {
            var secs = c.ArgCount > 1 && float.TryParse(c.GetArg(1), NumberStyles.Float, CultureInfo.InvariantCulture, out var sv) ? sv : 2f;
            var srv = GameServerDll();
            var any = Utilities.GetPlayers().FirstOrDefault(x => x is { IsValid: true, IsBot: true });
            if (any == null || srv == 0) { Log("dbgcmd2: no bot or no server.dll"); return; }
            VirtualFunctionVoid<nint> vf;
            try { vf = new VirtualFunctionVoid<nint>(any.Handle, 0x828 / 8); }
            catch (Exception e) { Log("dbgcmd2: {m}", e.Message); return; }
            int pre = 0, written = 0, noPb = 0, post = 0, held = 0;
            var shots = new Dictionary<int, int>();
            HookResult OnFire(EventWeaponFire e, GameEventInfo i) { if (e.Userid is { IsValid: true } u) shots[u.Slot] = shots.GetValueOrDefault(u.Slot) + 1; return HookResult.Continue; }
            RegisterEventHandler<EventWeaponFire>(OnFire);
            nint Buttons(nint ctl)
            {
                var cmd = Readable(ctl + 0x708, 8) ? (nint)Rd64(ctl + 0x708) : 0;
                var b = cmd != 0 && Readable(cmd, 0x48) ? (nint)Rd64(cmd + 0x40) : 0;
                var bp = b != 0 && Readable(b, 0x48) && Rd64(b) - srv == VtBasePB ? (nint)Rd64(b + 0x38) : 0;
                return bp != 0 && Readable(bp, 0x20) && Rd64(bp) - srv == VtButtonPB ? bp : 0;
            }
            HookResult Pre(DynamicHook h)
            {
                var ctl = h.GetParam<nint>(0);
                var pc = ctl == 0 ? null : new CCSPlayerController(ctl);
                if (pc == null || !pc.IsValid || !pc.IsBot) return HookResult.Continue;
                pre++;
                var bp = Buttons(ctl);
                if (bp != 0) { System.Runtime.InteropServices.Marshal.WriteInt64(bp + 0x18, Rd64(bp + 0x18) | 1L); written++; }
                else noPb++;
                return HookResult.Continue;
            }
            HookResult Post(DynamicHook h)
            {
                var ctl = h.GetParam<nint>(0);
                var pc = ctl == 0 ? null : new CCSPlayerController(ctl);
                if (pc == null || !pc.IsValid || !pc.IsBot) return HookResult.Continue;
                post++;
                var bp = Buttons(ctl);
                if (bp != 0 && (Rd64(bp + 0x18) & 1L) != 0) held++;
                return HookResult.Continue;
            }
            vf.Hook(Pre, HookMode.Pre);
            vf.Hook(Post, HookMode.Post);
            AddTimer(secs, () =>
            {
                vf.Unhook(Pre, HookMode.Pre);
                vf.Unhook(Post, HookMode.Post);
                DeregisterEventHandler<EventWeaponFire>(OnFire);
                Log("dbgcmd2: {p} runs (pre), IN_ATTACK written {w}, no buttons message {n}; after the run {q}, IN_ATTACK still in it {h}; shots {s}",
                    pre, written, noPb, post, held, string.Join(", ", shots.OrderBy(k => k.Key).Select(k => $"slot {k.Key}: {k.Value}")));
            });
        });
        // what a bot's command holds when its own AI fires (28/10: IN_ATTACK in the buttons message alone fires nothing):
        // two bots of both sides face to face, their AI on; each command kept per bot as it runs, the one of each shot
        // dumped (the command, its base, its buttons, its repeated fields' first entries): css_dbgcmd3 [seconds]
        AddCommand("css_dbgcmd3", "dumps a bot's command at its AI's shots", (p, c) =>
        {
            var secs = c.ArgCount > 1 && float.TryParse(c.GetArg(1), NumberStyles.Float, CultureInfo.InvariantCulture, out var sv) ? sv : 3f;
            var srv = GameServerDll();
            MemoryFunctionVoid<nint>? fn;
            try { fn = new(SimCmdSig); } catch (Exception e) { Log("dbgcmd3: {m}", e.Message); return; }
            var t = Utilities.GetPlayers().FirstOrDefault(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true, Team: CounterStrikeSharp.API.Modules.Utils.CsTeam.Terrorist });
            var ct = Utilities.GetPlayers().FirstOrDefault(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true, Team: CounterStrikeSharp.API.Modules.Utils.CsTeam.CounterTerrorist });
            if (t?.PlayerPawn.Value?.AbsOrigin is not { } to || ct?.PlayerPawn.Value == null || srv == 0) { Log("dbgcmd3: a T bot and a CT bot needed"); return; }
            Zombie(false); BotStop(false); DontShoot(false);
            // Dust2's Top Mid, open: the T at its boost spot, the CT 480 u up mid, facing each other, both with a rifle
            t.PlayerPawn.Value!.Teleport(new Vector3(-465f, -236f, 20f), new Vector3(0f, 90f, 0f), Vector3.Zero);
            ct.PlayerPawn.Value.Teleport(new Vector3(-465f, 244f, 20f), new Vector3(0f, -90f, 0f), Vector3.Zero);
            t.GiveNamedItem("weapon_ak47"); ct.GiveNamedItem("weapon_m4a1");
            var hurt = 0;
            HookResult OnHurt3(EventPlayerHurt e, GameEventInfo i) { hurt++; return HookResult.Continue; }
            RegisterEventHandler<EventPlayerHurt>(OnHurt3);
            var last = new Dictionary<int, List<string>>();
            var dumps = 0;
            string Hex(nint a, int len)
            {
                if (!Readable(a, len)) return "unreadable";
                var sb = new System.Text.StringBuilder();
                for (int o = 0; o < len; o += 8) sb.Append($" +{o:X2}:{Rd64(a + o):X16}");
                return sb.ToString();
            }
            void Rep(List<string> into, string tag, nint field)   // a RepeatedPtrField: its words, then its first entries
            {
                into.Add($"{tag} field{Hex(field, 0x18)}");
                for (int k = 0; k < 3; k++)
                {
                    var w = (nint)Rd64(field + k * 8);
                    if (w > 0x10000 && Readable(w, 0x20))
                    {
                        into.Add($"{tag} word{k} -> {Hex(w, 0x20)}");
                        for (int e = 0; e < 3; e++)
                        {
                            var q = (nint)Rd64(w + 8 + e * 8);
                            if (q > 0x10000 && Readable(q, 0x40)) into.Add($"{tag} word{k} entry{e} vt {Rd64(q) - srv:X} {Hex(q, 0x40)}");
                        }
                    }
                }
            }
            HookResult Pre(DynamicHook h)
            {
                var ctl = h.GetParam<nint>(0);
                var pc = ctl == 0 ? null : new CCSPlayerController(ctl);
                if (pc == null || !pc.IsValid || !pc.IsBot) return HookResult.Continue;
                var arr = (nint)Rd64(ctl + 0x4c8); var idx = Rd32(ctl + 0x4d0);
                var el = arr + Math.Max(0, idx) * 0xA0;
                if (arr == 0 || idx < 0 || !Readable(el, 0xA0)) return HookResult.Continue;
                var L = new List<string> { $"cmd{Hex(el, 0xA0)}" };
                Rep(L, "input_history", el + 0x28);
                var b = (nint)Rd64(el + 0x40);
                if (Readable(b, 0xC0) && Rd64(b) - srv == VtBasePB)
                {
                    L.Add($"base{Hex(b, 0xC0)}");
                    Rep(L, "subtick", b + 0x18);
                    var bp = (nint)Rd64(b + 0x38);
                    if (Readable(bp, 0x30)) L.Add($"buttons{Hex(bp, 0x30)}");
                }
                last[pc.Slot] = L;
                return HookResult.Continue;
            }
            HookResult OnFire(EventWeaponFire e, GameEventInfo i)
            {
                if (e.Userid is { IsValid: true, IsBot: true } u && dumps < 2 && last.TryGetValue(u.Slot, out var L))
                {
                    dumps++;
                    Log("dbgcmd3: {n} fired ({w}), its command:", u.PlayerName, e.Weapon);
                    foreach (var ln in L) Log("dbgcmd3:   {l}", ln);
                }
                return HookResult.Continue;
            }
            fn.Hook(Pre, HookMode.Pre);
            RegisterEventHandler<EventWeaponFire>(OnFire);
            AddTimer(secs, () =>
            {
                fn.Unhook(Pre, HookMode.Pre);
                DeregisterEventHandler<EventWeaponFire>(OnFire);
                DeregisterEventHandler<EventPlayerHurt>(OnHurt3);
                Log("dbgcmd3: over, {d} shots dumped, {h} hurts, T {tw} at {tp}, CT {cw} at {cp}", dumps, hurt,
                    t.PlayerPawn.Value?.WeaponServices?.ActiveWeapon.Value?.DesignerName, t.PlayerPawn.Value?.AbsOrigin?.ToString(),
                    ct.PlayerPawn.Value?.WeaponServices?.ActiveWeapon.Value?.DesignerName, ct.PlayerPawn.Value?.AbsOrigin?.ToString());
            });
        });
        // a bot's aim and shots both by the plugin (28/10: IN_ATTACK in the command's own CInButtonState, +0x58, fires a
        // bot even stopped by bot_stop): a stopped T aims at a stopped CT's head 480 u up Dust2's mid, its view set in its
        // command's viewangles (CMsgQAngle) and its eyes, IN_ATTACK held; its shots and hits: css_dbgaim [seconds]
        AddCommand("css_dbgaim", "a stopped bot aims at another's head and fires, by the plugin's hand", (p, c) =>
        {
            var secs = c.ArgCount > 1 && float.TryParse(c.GetArg(1), NumberStyles.Float, CultureInfo.InvariantCulture, out var sv) ? sv : 2f;
            var srv = GameServerDll();
            MemoryFunctionVoid<nint>? fn;
            try { fn = new(SimCmdSig); } catch (Exception e) { Log("dbgaim: {m}", e.Message); return; }
            var t = Utilities.GetPlayers().FirstOrDefault(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true, Team: CounterStrikeSharp.API.Modules.Utils.CsTeam.Terrorist });
            var ct = Utilities.GetPlayers().FirstOrDefault(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true, Team: CounterStrikeSharp.API.Modules.Utils.CsTeam.CounterTerrorist });
            if (t?.PlayerPawn.Value == null || ct?.PlayerPawn.Value == null || srv == 0) { Log("dbgaim: a T bot and a CT bot needed"); return; }
            Zombie(false); BotStop(true);
            var tp = t.PlayerPawn.Value; var cp = ct.PlayerPawn.Value;
            // where two AI bots had hit each other (28/10, css_dbgcmd3): about 800 u of open mid
            tp.Teleport(new Vector3(-417f, -1f, 20f), new Vector3(0f, 90f, 0f), Vector3.Zero);
            cp.Teleport(new Vector3(-367f, 802f, 16f), new Vector3(0f, -90f, 0f), Vector3.Zero);
            t.GiveNamedItem("weapon_ak47");
            int shots = 0, hits = 0, heads = 0, written = 0, angW = 0;
            var tslot = t.Slot;
            HookResult OnFire(EventWeaponFire e, GameEventInfo i) { if (e.Userid?.Slot == tslot) shots++; return HookResult.Continue; }
            HookResult OnHurtA(EventPlayerHurt e, GameEventInfo i) { if (e.Attacker?.Slot == tslot) { hits++; if (e.Hitgroup == 1) heads++; } return HookResult.Continue; }
            var impacts = new List<string>();
            HookResult OnImpact(EventBulletImpact e, GameEventInfo i) { if (e.Userid?.Slot == tslot && impacts.Count < 12) impacts.Add($"{e.X:F1} {e.Y:F1} {e.Z:F1}"); return HookResult.Continue; }
            var started = Server.TickCount + 64;   // a second to land and draw the rifle
            var fixSeed = c.ArgCount > 2 && c.GetArg(2) == "seed";
            Vector3? fixedAng = null;
            Vector3 Aim()
            {
                var a = tp.AbsOrigin!; var b = cp.AbsOrigin!;
                var d = new Vector3(b.X - a.X, b.Y - a.Y, b.Z + 64f - 2f - (a.Z + 64f));
                return new Vector3(-MathF.Atan2(d.Z, new Vector2(d.X, d.Y).Length()) * 180f / MathF.PI, MathF.Atan2(d.Y, d.X) * 180f / MathF.PI, 0f);
            }
            HookResult Pre(DynamicHook h)
            {
                var ctl = h.GetParam<nint>(0);
                var pc = ctl == 0 ? null : new CCSPlayerController(ctl);
                if (pc == null || !pc.IsValid || pc.Slot != tslot || tp.AbsOrigin == null || cp.AbsOrigin == null || Server.TickCount < started) return HookResult.Continue;
                var arr = (nint)Rd64(ctl + 0x4c8); var idx = Rd32(ctl + 0x4d0);
                var el = arr + Math.Max(0, idx) * 0xA0;
                if (arr == 0 || idx < 0 || !Readable(el, 0xA0) || Rd64(el + 0x58) - srv != VtInButton) return HookResult.Continue;
                var ang = fixSeed ? (fixedAng ??= Aim()) : Aim();   // a fixed point: the CT's head where it stood first
                var b = (nint)Rd64(el + 0x40);
                var qa = Readable(b, 0x48) && Rd64(b) - srv == VtBasePB ? (nint)Rd64(b + 0x40) : 0;
                // the shot's spread from the command's random_seed (CBaseUserCmdPB +0x6C, by its fields' order and the values
                // seen): one fixed per tick from the start, the same bullets each run (css_dbgaim seed)
                if (fixSeed && Readable(b, 0x70) && Rd64(b) - srv == VtBasePB)
                    System.Runtime.InteropServices.Marshal.WriteInt32(b + 0x6C, 7919 * (Server.TickCount - started + 1));
                if (qa != 0 && Readable(qa, 0x28) && Rd64(qa) - srv == VtQAngle)
                {
                    System.Runtime.InteropServices.Marshal.WriteInt32(qa + 0x18, BitConverter.SingleToInt32Bits(ang.X));
                    System.Runtime.InteropServices.Marshal.WriteInt32(qa + 0x1C, BitConverter.SingleToInt32Bits(ang.Y));
                    angW++;
                }
                HoldAim(tp, ang, false);
                System.Runtime.InteropServices.Marshal.WriteInt64(el + 0x60, Rd64(el + 0x60) | 1L);
                written++;
                return HookResult.Continue;
            }
            fn.Hook(Pre, HookMode.Pre);
            RegisterEventHandler<EventWeaponFire>(OnFire);
            RegisterEventHandler<EventPlayerHurt>(OnHurtA);
            RegisterEventHandler<EventBulletImpact>(OnImpact);
            AddTimer(secs + 1f, () =>
            {
                fn.Unhook(Pre, HookMode.Pre);
                DeregisterEventHandler<EventWeaponFire>(OnFire);
                DeregisterEventHandler<EventPlayerHurt>(OnHurtA);
                DeregisterEventHandler<EventBulletImpact>(OnImpact);
                BotStop(false);
                var ea = tp.EyeAngles;
                Log("dbgaim: {s} shots, {h} hits ({hs} in the head), IN_ATTACK {w}, viewangles written {a}; T at {tp}, CT at {cp}, CT hp {hp}; aim {am}, T's eyes {e1:F1} {e2:F1}; impacts {im}",
                    shots, hits, heads, written, angW, tp.AbsOrigin?.ToString(), cp.AbsOrigin?.ToString(), cp.Health,
                    tp.AbsOrigin != null && cp.AbsOrigin != null ? Aim().ToString() : "-", ea?.X ?? 0f, ea?.Y ?? 0f, string.Join(" | ", impacts));
            });
        });
        // 29/10, the user on Cache: "les vents ... pas cassées alors que dans la situation réelle elles sont supposées être
        // cassées ... même si tu tires à travers, elle est supposée se casser ... et là elle se casse jamais": the map's
        // breakable things, what they are: css_dbgbreakables
        AddCommand("css_dbgbreakables", "the map's breakables: class, name, place, health, model, flags", (p, c) =>
        {
            var n = 0;
            foreach (var e in Utilities.GetAllEntities())
            {
                var d = e.DesignerName ?? "";
                if (!(d.Contains("breakable") || d.StartsWith("prop_dynamic") || d.StartsWith("prop_physics"))) continue;
                var be = new CBaseEntity(e.Handle);
                if (!be.IsValid || be.AbsOrigin == null) continue;
                var name = be.Entity?.Name ?? "";
                var model = be.CBodyComponent?.SceneNode?.GetSkeletonInstance()?.ModelState.ModelName ?? "";
                if (d.StartsWith("prop_dynamic") && be.Health <= 0 && !(name + model).Contains("vent", StringComparison.OrdinalIgnoreCase)) continue;
                Log("dbgbreakables {c} '{n}' at {x:F0} {y:F0} {z:F0} hp {h} max {m} model {md}", d, name, be.AbsOrigin.X, be.AbsOrigin.Y, be.AbsOrigin.Z,
                    be.Health, be.MaxHealth, model);
                n++;
            }
            Log("dbgbreakables: {n}", n);
        });
        // css_dbgbotfire [seconds]
        AddCommand("css_dbgbotfire", "the bot nearest you fires at you by the plugin's hand: css_dbgbotfire [seconds]", (p, c) =>
        {
            var secs = c.ArgCount > 1 && float.TryParse(c.GetArg(1), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out var sv) ? sv : 2f;
            // at you, or with nobody on the server at the nearest bot of the other team (28/10: tried on server 2 alone)
            var tgt = Humans().FirstOrDefault(h => h.PawnIsAlive)
                ?? Utilities.GetPlayers().FirstOrDefault(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true } && x.PlayerPawn.Value?.AbsOrigin != null);
            var me = tgt?.PlayerPawn.Value;
            if (tgt == null || me?.AbsOrigin == null) { Log("dbgbotfire: nobody to fire at"); return; }
            var mo = new Vector3(me.AbsOrigin.X, me.AbsOrigin.Y, me.AbsOrigin.Z);
            var bot = Utilities.GetPlayers().Where(x => x is { IsValid: true, IsBot: true, PawnIsAlive: true } && x.PlayerPawn.Value?.AbsOrigin != null
                    && x.Slot != tgt.Slot && x.Team != tgt.Team)
                .OrderBy(x => { var o = x.PlayerPawn.Value!.AbsOrigin!; return Vector3.Distance(new Vector3(o.X, o.Y, o.Z), mo); }).FirstOrDefault();
            if (bot?.PlayerPawn.Value is not { } bp) { Log("dbgbotfire: no bot"); return; }
            // its own AI idle by bot_zombie (default), by bot_stop ("stop"), or on ("ai", bot_dont_shoot): which one lets
            // the plugin's IN_ATTACK fire (28/10: a zombie fired 0 shots of 2 s, it runs no command at all)
            var how = c.ArgCount > 2 ? c.GetArg(2) : "zombie";
            Zombie(how == "zombie");
            Server.ExecuteCommand($"bot_stop {(how == "stop" ? 1 : 0)}");
            Server.ExecuteCommand($"bot_dont_shoot {(how == "ai" ? 1 : 0)}");
            var fired = 0;
            var slot = bot.Slot;
            var hits = 0;
            HookResult OnFire(EventWeaponFire e, GameEventInfo i) { if (e.Userid?.Slot == slot) fired++; return HookResult.Continue; }
            HookResult OnHurt(EventPlayerHurt e, GameEventInfo i) { if (e.Attacker?.Slot == slot) hits++; return HookResult.Continue; }
            RegisterEventHandler<EventWeaponFire>(OnFire);
            RegisterEventHandler<EventPlayerHurt>(OnHurt);
            var t0 = Server.TickCount;
            var tm = AddTimer(0.015625f, () =>
            {
                if (!bp.IsValid || me.AbsOrigin == null || bp.AbsOrigin == null) return;
                var d = new Vector3(me.AbsOrigin.X - bp.AbsOrigin.X, me.AbsOrigin.Y - bp.AbsOrigin.Y, me.AbsOrigin.Z + 56f - bp.AbsOrigin.Z - 64f);
                var yaw = MathF.Atan2(d.Y, d.X) * 180f / MathF.PI;
                var pitch = -MathF.Atan2(d.Z, new Vector2(d.X, d.Y).Length()) * 180f / MathF.PI;
                HoldAim(bp, new Vector3(pitch, yaw, 0), false);
                if (bp.MovementServices != null)
                {
                    var mv = new CCSPlayer_MovementServices(bp.MovementServices.Handle);
                    mv.Buttons.ButtonStates[0] |= 1UL;   // IN_ATTACK
                    Utilities.SetStateChanged(bp, "CBasePlayerPawn", "m_pMovementServices");
                }
            }, CounterStrikeSharp.API.Modules.Timers.TimerFlags.REPEAT);
            AddTimer(secs, () =>
            {
                tm.Kill();
                DeregisterEventHandler<EventWeaponFire>(OnFire);
                DeregisterEventHandler<EventPlayerHurt>(OnHurt);
                Log("dbgbotfire {how}: {n} fired {f} shots in {s} s at {t}, {h} hits (its weapon {w})", how, bot.PlayerName, fired, secs, tgt.PlayerName, hits,
                    bp.WeaponServices?.ActiveWeapon.Value?.DesignerName);
            });
        });
        AddCommand("css_dbglosfile", "the bullet's lines listed in coach/los_in.json, answered in coach/los_out.json", (p, c) =>
        {
            if (p != null) return;
            // its two files read and written off the game's thread, its lines traced on it (10/11, rounds 25-26: the test client
            // asks it a hundred times a defense; 22 of the server's 40 frames over 200 ms on 04/11 and 31 of 66 on 10/11 came
            // with one, up to 1.0 s: the files' reads, writes and renames, on a busy disk)
            var dir = Dir;
            float[][] Read() => JsonSerializer.Deserialize<float[][]>(System.IO.File.ReadAllText(System.IO.Path.Combine(dir, "los_in.json"))) ?? Array.Empty<float[]>();
            void Answer(float[][] rows)
            {
                var ign = Utilities.GetPlayers().FirstOrDefault(x => x.PlayerPawn.Value != null)?.PlayerPawn.Value;
                if (ign == null) { Server.ExecuteCommand("bot_quota 1"); Server.ExecuteCommand("bot_add_t"); Log("dbglosfile: no player, a bot added: again"); return; }
                try
                {
                    var opt = new CounterStrikeSharp.API.Modules.Utils.TraceOptions { InteractsWith = CounterStrikeSharp.API.Modules.Utils.Masks.ShotBrushOnly };
                    // a 7th number 1: what stops a player instead (27/10, Inferno's Second Mid: its balcony's railing and the clips
                    // under it let bullets through, the driver stood on them; tools/jump_probe.py)
                    var optMe = new CounterStrikeSharp.API.Modules.Utils.TraceOptions { InteractsWith = CounterStrikeSharp.API.Modules.Utils.Masks.PlayerSolidBrushOnly };
                    var res = new float[rows.Length];
                    for (int i = 0; i < rows.Length; i++)
                    {
                        var r = rows[i];
                        res[i] = r.Length < 6 ? -1f : CounterStrikeSharp.API.Modules.Utils.Trace.TraceEndShape(
                            new CounterStrikeSharp.API.Modules.Utils.Vector(r[0], r[1], r[2]), new CounterStrikeSharp.API.Modules.Utils.Vector(r[3], r[4], r[5]), ign,
                            r.Length >= 7 && r[6] == 1f ? optMe : opt).Fraction;
                    }
                    var text = JsonSerializer.Serialize(res);
                    void Write()
                    {
                        try
                        {
                            var tmp = System.IO.Path.Combine(dir, "los_out.json.tmp");
                            System.IO.File.WriteAllText(tmp, text);
                            System.IO.File.Move(tmp, System.IO.Path.Combine(dir, "los_out.json"), true);
                        }
                        catch (Exception) { }
                    }
                    if (!Io(Write)) Write();
                    Log("dbglosfile: {n} lines", rows.Length);
                }
                catch (Exception e) { Log("dbglosfile: {m}", e.Message); }
            }
            if (!Io(() =>
                {
                    float[][] rows;
                    try { rows = Read(); }
                    catch (Exception e) { var m = e.Message; OnGame(() => Log("dbglosfile: {m}", m)); return; }
                    OnGame(() => Answer(rows));
                }))
            {   // no io thread (the plugin going down): as before, here
                try { Answer(Read()); } catch (Exception e) { Log("dbglosfile: {m}", e.Message); }
            }
        });
        // a bullet's line between two points (23/10 eve: Crossfire's starts seen from their spot): css_dbglos x y z x y z
        AddCommand("css_dbglos", "a bullet's line between two points: css_dbglos x1 y1 z1 x2 y2 z2 [tag]", (p, c) =>
        {
            float A(int i) => float.TryParse(c.GetArg(i), NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0f;
            var ign = Utilities.GetPlayers().FirstOrDefault(x => x.PlayerPawn.Value != null)?.PlayerPawn.Value;
            if (ign == null) { Server.ExecuteCommand("bot_quota 1"); Server.ExecuteCommand("bot_add_t"); Log("dbglos: no player, a bot added: again"); return; }
            var mask = c.GetArg(8) switch
            {
                "shot" => CounterStrikeSharp.API.Modules.Utils.Masks.Shot,
                "solid" => CounterStrikeSharp.API.Modules.Utils.Masks.Solid,
                "solidbrush" => CounterStrikeSharp.API.Modules.Utils.Masks.SolidBrushOnly,
                "playerbrush" => CounterStrikeSharp.API.Modules.Utils.Masks.PlayerSolidBrushOnly,
                "npcbrush" => CounterStrikeSharp.API.Modules.Utils.Masks.NpcSolidBrushOnly,
                "hull" => CounterStrikeSharp.API.Modules.Utils.Masks.ShotHull,
                _ => CounterStrikeSharp.API.Modules.Utils.Masks.ShotBrushOnly,
            };
            var tr = CounterStrikeSharp.API.Modules.Utils.Trace.TraceEndShape(new CounterStrikeSharp.API.Modules.Utils.Vector(A(1), A(2), A(3)),
                new CounterStrikeSharp.API.Modules.Utils.Vector(A(4), A(5), A(6)), ign,
                new CounterStrikeSharp.API.Modules.Utils.TraceOptions { InteractsWith = mask });
            Log("dbglos {tag}: {f:F3} {m}", c.GetArg(7), tr.Fraction, c.GetArg(8));
        });
        AddCommand("css_dbgprobe", "a spot's walls: a bot pushed 16 ways from it: css_dbgprobe x y z", (p, c) =>
        {
            float A(int i) => float.TryParse(c.GetArg(i), NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : 0f;
            var bot = Utilities.GetPlayers().FirstOrDefault(x => x.IsBot && x.PlayerPawn.Value != null);
            if (bot == null) { Server.ExecuteCommand("bot_quota 1"); Server.ExecuteCommand("bot_add_t"); Log("dbgprobe: no bot, one added: again"); return; }
            if (!bot.PawnIsAlive) bot.Respawn();
            Server.ExecuteCommand("bot_stop 1");
            ProbeWay(bot, new Vector3(A(1), A(2), A(3)), 0, new float[16]);
        });
        // an input to one entity by its index (a door opened the other way, a blocker removed): css_dbgidx <index> <input> [value]
        AddCommand("css_dbgidx", "an input to an entity by index: css_dbgidx <index> <input> [value]", (p, c) =>
        {
            var e = Utilities.GetAllEntities().FirstOrDefault(x => x.IsValid && x.Index == (uint)(int.TryParse(c.GetArg(1), out var i) ? i : -1));
            if (e == null) { Log("dbgidx: no entity {i}", c.GetArg(1)); return; }
            e.AcceptInput(c.GetArg(2), null, null, c.ArgCount > 3 ? c.GetArg(3) : "");
            Log("dbgidx {d} #{i} '{n}': {inp}", e.DesignerName, e.Index, e.Entity?.Name ?? "", c.GetArg(2));
        });
        // the entities whose box holds a point (a brush's origin is anywhere: its box tells): css_dbgbox x y z [margin]
        AddCommand("css_dbgbox", "the entities whose box holds a point: css_dbgbox x y z [margin]", (p, c) =>
        {
            float A(int i, float d) => float.TryParse(c.GetArg(i), NumberStyles.Float, CultureInfo.InvariantCulture, out var v) ? v : d;
            var q = new Vector3(A(1, 0), A(2, 0), A(3, 0));
            var m = A(4, 24f);
            var n = 0;
            foreach (var e in Utilities.GetAllEntities())
            {
                if (!e.IsValid || string.IsNullOrEmpty(e.DesignerName) || e.DesignerName.StartsWith("weapon_")) continue;
                try
                {
                    var b = new CBaseEntity(e.Handle);
                    var o = b.AbsOrigin; var col = b.Collision;
                    if (o == null || col == null) continue;
                    var lo = new Vector3(o.X + col.Mins.X - m, o.Y + col.Mins.Y - m, o.Z + col.Mins.Z - m);
                    var hi = new Vector3(o.X + col.Maxs.X + m, o.Y + col.Maxs.Y + m, o.Z + col.Maxs.Z + m);
                    if (q.X < lo.X || q.Y < lo.Y || q.Z < lo.Z || q.X > hi.X || q.Y > hi.Y || q.Z > hi.Z) continue;
                    if (hi.X - lo.X > 20000) continue;   // the world
                    n++;
                    Log("dbgbox {d} '{nm}' #{i} origin {o} box {lo}..{hi} solid {s} group {g} flags {f}", e.DesignerName, e.Entity?.Name ?? "", e.Index,
                        $"{o.X:F0} {o.Y:F0} {o.Z:F0}", $"{lo.X + m:F0} {lo.Y + m:F0} {lo.Z + m:F0}", $"{hi.X - m:F0} {hi.Y - m:F0} {hi.Z - m:F0}",
                        col.SolidType, col.CollisionGroup, col.SolidFlags);
                }
                catch (Exception ex) { Log("dbgbox #{i}: {m}", e.Index, ex.Message); }
            }
            Log("dbgbox {n} entities hold {q}", n, q);
        });
    }

    Action? dbgWalk;
    // css_dbgprobe: way i of 16 from the spot, 8 pushes at a runner's speed, then how far along it the bot went
    void ProbeWay(CCSPlayerController bot, Vector3 at, int i, float[] res)
    {
        if (i >= 16)
        {
            Server.ExecuteCommand("bot_stop 0");
            Log("dbgprobe {x:F1} {y:F1} {z:F1}: {r}", at.X, at.Y, at.Z, string.Join(" ", res.Select(v => v.ToString("F1", CultureInfo.InvariantCulture))));
            return;
        }
        if (!bot.IsValid || bot.PlayerPawn.Value is not { } pw) { Log("dbgprobe: the bot is gone"); return; }
        pw.Teleport(at + new Vector3(0f, 0f, 2f), null, Vector3.Zero);
        var a = i * MathF.PI / 8f;
        var dir = new Vector3(MathF.Cos(a), MathF.Sin(a), 0f);
        void Push(int k)
        {
            if (!bot.IsValid || bot.PlayerPawn.Value is not { } p2) return;
            if (k < 8) { p2.Teleport(null, null, dir * 250f); AddTimer(0.02f, () => Push(k + 1)); return; }
            var o = p2.AbsOrigin;
            res[i] = o == null ? -1f : MathF.Max(0f, (o.X - at.X) * dir.X + (o.Y - at.Y) * dir.Y);
            p2.Teleport(at + new Vector3(0f, 0f, 2f), null, Vector3.Zero);
            AddTimer(0.05f, () => ProbeWay(bot, at, i + 1, res));
        }
        AddTimer(0.1f, () => Push(0));   // on its feet first
    }

    int dbgThrowBy = -1;   // css_dbgthrow's bot: its pops logged
    int dbgBounces, dbgWalls;   // its flash's bounces before it popped: on the floor, off a wall
    bool stVictims;        // the guide throwing at the victims (GuideVictims): no throw of the drill's, none recorded
    Vector3? stVicPop;     // there, where its smoke popped (Session.cs NadeHit)

    void CmdSelfTest(CCSPlayerController? p, CommandInfo c)
    {
        if (Humans().Any()) { Say(p, "a player is on the server: no self-test"); return; }
        var id = c.GetArg(1);
        if (string.IsNullOrWhiteSpace(id) || id.Contains('/') || id.Contains('\\') || id.Contains("..")) { Say(p, "css_selftest <session> [timescale]"); return; }
        var ts = float.TryParse(c.GetArg(2), NumberStyles.Float, CultureInfo.InvariantCulture, out var x) ? Math.Clamp(x, 1f, 8f) : 1f;
        selftest = true;
        stId = id;
        Rng = new Random(int.TryParse(c.GetArg(3), out var seed) ? seed : 1);   // the same picks each run: runs compared drill for drill
        stGuided = c.GetArg(4) == "guided";
        guideNext = 0;
        stLast = 0;
        stClock0 = DateTime.UtcNow;
        stTick0 = Server.TickCount;
        Io(() => System.IO.Directory.CreateDirectory(System.IO.Path.Combine(Dir, "selftest")));
        Server.ExecuteCommand("sv_hibernate_when_empty 0");   // nobody on it: the game would sleep, and its timers with it
        if (ts > 1f)
        {
            Server.ExecuteCommand("sv_cheats 1");
            Server.ExecuteCommand($"host_timescale {ts.ToString(CultureInfo.InvariantCulture)}");
        }
        St("start", new() { ["timescale"] = ts });
        CmdSession(p, c);
    }

    // the session's end (or a stop): the clock back to normal
    void StOff()
    {
        if (!selftest) return;
        if (stGuided)   // the guide's throws, each kept as it popped, saved as a test setup (Recorder.cs: the whole way checked)
            foreach (var (slot, t) in bots.Where(kv => kv.Value.Sid == "guide").ToList())
                if (Utilities.GetPlayerFromSlot(slot) is { IsValid: true } g) RecSetup(g, $"selftest {stId}");
        St("end", new());
        selftest = false;
        stGuided = false;
        Server.ExecuteCommand("host_timescale 1");
        Server.ExecuteCommand("sv_cheats 0");
    }

    string StFile(string ext = ".jsonl") => System.IO.Path.Combine("selftest", stId + ext);

    void St(string ev, Dictionary<string, object?> o)
    {
        if (!selftest) return;
        o["ev"] = ev;
        o["tick"] = Server.TickCount;
        o["drill"] = drill?.Id;
        o["map"] = Server.MapName;
        o["phase"] = phase;
        try { Append(StFile(), JsonSerializer.Serialize(o)); } catch (Exception) { }
    }

    static float R1(float x) => MathF.Round(x, 1);
    static float[] R3(Vector3 v) => new[] { R1(v.X), R1(v.Y), R1(v.Z) };

    // a drill's bots placed: the ones it asked for, the ones that came, alive
    void StPlaced()
    {
        if (!selftest || cur == null) return;
        var want = cur.Players.Count(t => !t.Me || mode == "spec");
        var alive = bots.Keys.Count(sl => Utilities.GetPlayerFromSlot(sl) is { IsValid: true, PawnIsAlive: true });
        St("placed", new() { ["kind"] = drill?.Kind, ["mode"] = drill?.Mode, ["variant"] = drill?.Variant, ["title"] = drill?.Title,
            ["want"] = want, ["have"] = bots.Count, ["alive"] = alive,
            ["me"] = cur.Players.FirstOrDefault(t => t.Me) is { } me && me.Path.Length >= 3 ? R3(Pos(me, 0)) : null });
    }

    // a bot off its way during the drill, put back on it: where it was, where its way was, how far
    void StFix(Track t, Vector3 here, Vector3 want, float ft, float wayV, float botV, bool eng, string why)
    {
        St("fix", new() { ["why"] = why, ["bot"] = t.Sid, ["name"] = t.Name, ["f"] = R1(ft), ["at"] = R3(here), ["want"] = R3(want),
            ["dxy"] = R1(new Vector2(here.X - want.X, here.Y - want.Y).Length()), ["dz"] = R1(here.Z - want.Z),
            ["warp"] = MathF.Round(t.Warp * (cur?.Step ?? 1) / 64f, 2), ["way_v"] = R1(wayV), ["bot_v"] = R1(botV), ["eng"] = eng,
            // stopped: what is in front of it (another player, a door)
            ["near_bot"] = botV < 30f ? StNear(here, Utilities.GetPlayers().Where(p => p.Slot != SlotOf(t)).Select(p => p.PlayerPawn.Value?.AbsOrigin)) : null,
            ["near_door"] = botV < 30f ? StNear(here, Utilities.FindAllEntitiesByDesignerName<CBaseEntity>("prop_door_rotating").Select(d => d.AbsOrigin)) : null,
            ["near_ents"] = botV < 30f ? StEnts(here) : null,
            ["state"] = botV < 30f ? StState(t) : null });
    }

    static float? StNear(Vector3 here, IEnumerable<CounterStrikeSharp.API.Modules.Utils.Vector?> pts)
    {
        float? best = null;
        foreach (var o in pts)
            if (o != null) { var d = Vector3.Distance(here, new Vector3(o.X, o.Y, o.Z)); if (best == null || d < best) best = d; }
        return best == null ? null : R1(best.Value);
    }

    // the entities around a stopped bot (a sliding door, a prop, the bomb...): what may stand in its way
    static List<string> StEnts(Vector3 here, float r = 96f)
    {
        var skip = new[] { "weapon_", "cs_player", "player", "predicted_viewmodel", "info_", "logic_", "point_", "env_", "game_", "team_", "cs_team", "cs_gamerules", "func_buyzone", "trigger_", "ambient_", "sky_", "worldent", "light_", "post_processing", "tonemap", "cs_minimap", "spotlight" };
        var near = new List<(float d, string n)>();
        foreach (var e in Utilities.GetAllEntities())
        {
            var n = e.DesignerName;
            if (!e.IsValid || string.IsNullOrEmpty(n) || skip.Any(s => n.StartsWith(s))) continue;
            var o = new CBaseEntity(e.Handle).AbsOrigin;
            if (o == null) continue;
            var d = Vector3.Distance(here, new Vector3(o.X, o.Y, o.Z));
            if (d < r) near.Add((d, $"{n}{(string.IsNullOrEmpty(e.Entity?.Name) ? "" : ":" + e.Entity!.Name)}@{(int)d}"));
        }
        return near.OrderBy(x => x.d).Take(6).Select(x => x.n).ToList();
    }

    // a stopped bot's own state: what keeps it from moving (its move type, flags, the speed it may have, its crouch)
    string? StState(Track t)
    {
        var sl = SlotOf(t);
        if (sl < 0 || Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value is not { } pw) return null;
        var mv = pw.MovementServices == null ? null : new CCSPlayer_MovementServices(pw.MovementServices.Handle);
        var actual = Schema.GetSchemaValue<byte>(pw.Handle, "CBaseEntity", "m_nActualMoveType");
        return $"move {pw.MoveType}/{actual} flags {(CounterStrikeSharp.API.Modules.Utils.PlayerFlags)pw.Flags} max {mv?.Maxspeed:F0} duck {mv?.DuckAmount:F2} "
             + $"life {pw.LifeState} hp {pw.Health} vmod {pw.VelocityModifier:F2} defusing {pw.IsDefusing} walking {pw.IsWalking} ground {pw.GroundEntity?.Value?.DesignerName ?? "-"} "
             + $"sim {pw.SimulationTime:F2} now {Server.CurrentTime:F2} stop {Cv("bot_stop")} zombie {Cv("bot_zombie")}";
    }

    // a convar's value as text (23/10: bot_stop and bot_zombie read as bools threw "Reference types must be accessed using
    // GetReferenceValue" in every tick that logged a stopped bot, 2254 times that day: the rest of OnTick skipped, the bot
    // never put back on its way)
    static string Cv(string name)
    {
        try { return ConVar.Find(name)?.StringValue ?? "-"; }
        catch (Exception) { return "?"; }
    }

    int SlotOf(Track t) { foreach (var (s, x) in bots) if (x == t) return s; return -1; }

    // every half second: each bot's place against its way, its speed, what it is doing
    void StSample(float f)
    {
        if (!selftest || cur == null || Server.TickCount - stLast < 32) return;
        stLast = Server.TickCount;
        var rows = new List<object?[]>();
        foreach (var (slot, t) in bots)
        {
            if (t.Strafe && t.Sid == "guide") continue;   // a Momentum guide has no way of its own (MoGuideDrive)
            var c = Utilities.GetPlayerFromSlot(slot);
            var pw = c?.PlayerPawn.Value;
            var o = pw?.AbsOrigin;
            var ft = f - t.Start;
            var want = t.Hold || t.Frames < 2 ? Pos(t, 0) : PathAt(t, Math.Clamp(ft, 0f, Math.Max(0, t.Frames - 1)));
            var v = pw?.AbsVelocity;
            var state = gone.Contains(t.Sid) ? "gone" : free.Contains(slot) ? "free" : t.Hold ? "hold" : ft < 0 ? "wait" : ft >= t.Frames - 1 ? "end" : "path";
            rows.Add(new object?[] { t.Sid, c is { IsValid: true, PawnIsAlive: true }, o == null ? null : new[] { R1(o.X), R1(o.Y), R1(o.Z) }, R3(want),
                v == null ? 0f : R1(new Vector2(v.X, v.Y).Length()), state,
                botGround.GetValueOrDefault(slot, true) });   // on the ground (in a jump: no level finding)
        }
        St("s", new() { ["f"] = R1(f), ["bots"] = rows });
    }

    void StFinish(string outcome, double secs) => St("finish", new() { ["outcome"] = outcome, ["secs"] = Math.Round(secs, 1) });

    // 17/10, the user: "fais des tests bot guidés pour les stuff en respectant les consignes affichées pour voir si tout
    // fonctionne": a bot on the green ring, its aim on the green cross, crouched when the words say so, throws the way the
    // words say (jumpthrow, running, the click), with CS2's throw as the base's flights measured it (wily/insights/nades.py
    // _phys: 10° above the aim, 675 / 439 / 203 u/s for a left / both / right click, 16 u ahead of the eyes, a bind's jump
    // 265 u/s up, a run 190 forward); the game flies it. Its pop is scored as yours: a miss is a drill whose words fail.
    bool IsGuide(CCSPlayerController? u) => stGuided && u is { IsValid: true } && bots.TryGetValue(u.Slot, out var t) && t.Sid == "guide";

    // a stuff drill's flight as its words throw it (the guided bot's throw, no bounce): points every 1/16 s until it is
    // down to the target's height past its top, 4 s at most
    static List<Vector3> NadeArc(Drill d)
    {
        var pts = new List<Vector3>();
        if (d.Me == null) return pts;
        var how = d.How.ToLowerInvariant();
        float el = (10f - d.Me.Ang[0] * 80f / 90f) * MathF.PI / 180f, yr = d.Me.Ang[1] * MathF.PI / 180f;
        var fw = new Vector3(MathF.Cos(el) * MathF.Cos(yr), MathF.Cos(el) * MathF.Sin(yr), MathF.Sin(el));
        var flat = new Vector3(MathF.Cos(yr), MathF.Sin(yr), 0f);
        var (speed, dz) = d.Click.Contains("right") ? (d.Click.Contains("left") ? (438.75f, -6f) : (202.5f, -12f)) : (675f, 0f);
        var v = fw * speed + (how.Contains("jumpthrow") ? new Vector3(0f, 0f, 265f) : Vector3.Zero)
              + (how.Contains("forward") || how.Contains("run") ? flat * 190f : how.Contains("walking") ? flat * 125f : Vector3.Zero);
        var p = new Vector3(d.Me.Pos[0], d.Me.Pos[1], d.Me.Pos[2] + (how.Contains("crouch") ? 46f : 64f)) + fw * 16f + new Vector3(0f, 0f, dz);
        var floor = d.Target is { Length: >= 3 } t3 ? t3[2] : d.Me.Pos[2];
        for (float t = 0f; t <= 4f; t += 1f / 16f)
        {
            var q = p + v * t + new Vector3(0f, 0f, -160f * t * t);   // a grenade's gravity: 320 u/s²
            pts.Add(q);
            if (t > 0.2f && q.Z < floor && v.Z - 320f * t < 0f) break;
        }
        return pts;
    }

    void GuideTick()
    {
        if (selftest && stGuided && Server.TickCount < guideFlyUntil && Server.TickCount % 8 == 0)
            foreach (var e in Utilities.GetAllEntities().Where(e => e.IsValid && e.DesignerName.EndsWith("_projectile")))
            {
                var g = new CBaseCSGrenadeProjectile(e.Handle);
                if (g.AbsOrigin is not { } o) continue;
                if (guideFly.Contains(e.Index) || (g.Thrower.Value?.OriginalController.Value is { } tc && IsGuide(tc) && guideFly.Add(e.Index)))
                    St("fly", new() { ["i"] = e.Index, ["at"] = new[] { R1(o.X), R1(o.Y), R1(o.Z) }, ["v"] = g.AbsVelocity is { } v ? R3(new Vector3(v.X, v.Y, v.Z)) : null });
            }
        if (!selftest || !stGuided || cur?.Kind != "nade" || drill?.Me == null || nadeStage != "throw" || !nadeWait || Server.TickCount < guideNext || ExecOn) return;
        var slot = bots.Where(kv => kv.Value.Sid == "guide").Select(kv => (int?)kv.Key).FirstOrDefault();
        if (slot == null || Utilities.GetPlayerFromSlot(slot.Value) is not { IsValid: true, PawnIsAlive: true } c || c.PlayerPawn.Value is not { } pw) return;
        if (StepsOn) { StepsGuide(c, pw); return; }   // step by step: each step played, wrong first (Steps.cs)
        guideNext = Server.TickCount + 4 * 64;   // one at a time: its pop scored before the next
        guideFlyUntil = Server.TickCount + 6 * 64;
        var d = drill;
        guideLast = WordsNade(d);
        St("guided", new() { ["how"] = d.How, ["click"] = d.Click, ["type"] = d.Type, ["src"] = R3(new Vector3(guideLast.P[0], guideLast.P[1], guideLast.P[2])),
            ["vel"] = R3(new Vector3(guideLast.V[0], guideLast.V[1], guideLast.V[2])), ["target"] = d.Target, ["level"] = d.Level });
        ThrowAs(c, pw, guideLast);
    }

    // a stuff drill's throw as its words say: 10° above the aim, its click's speed 16 u ahead of the eyes, a jump's 265 u/s
    // up, a step's 190 forward (see above)
    static Nade WordsNade(Drill d)
    {
        var me = d.Me!;
        var how = d.How.ToLowerInvariant();
        float el = (10f - me.Ang[0] * 80f / 90f) * MathF.PI / 180f, yr = me.Ang[1] * MathF.PI / 180f;
        var fw = new Vector3(MathF.Cos(el) * MathF.Cos(yr), MathF.Cos(el) * MathF.Sin(yr), MathF.Sin(el));
        var flat = new Vector3(MathF.Cos(yr), MathF.Sin(yr), 0f);
        // "left click", "right click", "left + right click", or "" when the demos don't tell (then a left one)
        var (speed, dz) = d.Click.Contains("right") ? (d.Click.Contains("left") ? (438.75f, -6f) : (202.5f, -12f)) : (675f, 0f);
        var add = Vector3.Zero;
        // his own jumpthrow: let go where he does in the jump (his speed up then, his height); else a bind's moment
        if (how.Contains("jumpthrow")) add += new Vector3(0f, 0f, d.Jump is { Length: >= 2 } j ? j[0] : 265f);
        if (how.Contains("forward") || how.Contains("run")) add += flat * 190f;
        else if (how.Contains("walking")) add += flat * 125f;
        var src = new Vector3(me.Pos[0], me.Pos[1], me.Pos[2] + (how.Contains("crouch") && !how.Contains("jumpthrow") ? 46f : 64f)
                              + (how.Contains("jumpthrow") && d.Jump is { Length: >= 2 } j2 ? j2[1] : 0f)) + fw * 16f + new Vector3(0f, 0f, dz);
        var vel = fw * speed + add;
        return new Nade { Type = d.Type, By = "guide", Inc = d.Item.Contains("incgrenade"), P = new[] { src.X, src.Y, src.Z }, V = new[] { vel.X, vel.Y, vel.Z } };
    }

    Nade? guideLast;   // the guide's last throw: thrown again at the drill's victims

    // a guided self-test's "from their side": the guide on each of the drill's victim spots in turn, turned as they are,
    // the same grenade thrown again, what it did to it measured (19/10, his 17/10 video: "vérifie bien avec tes bots que la
    // POV de la personne qui subit la flash subit vraiment la flash, ou la smoke ou la molo"): its flash time, its health
    // lost, a smoke between it and the line it holds. Then the drill ends as it would.
    void GuideVictims((bool ok, string outcome, int pts, string detail) res)
    {
        var slot = bots.Where(kv => kv.Value.Sid == "guide").Select(kv => (int?)kv.Key).FirstOrDefault();
        if (drill == null || slot == null || guideLast == null || Utilities.GetPlayerFromSlot(slot.Value) is not { IsValid: true } c)
        {
            if (drill != null) DrillDone(res.ok, res.outcome, res.pts, res.detail);
            return;
        }
        var t = bots[slot.Value];
        var path0 = t.Path;
        var vs = drill.Victims.Take(4).ToList();
        // a molotov twice on each (its fire spreads its own way each time; 20/10, the user: "que la personne derrière la
        // charrette brûle 100% du temps"): one it missed once is not one it burns
        if (drill.Type == "molotov") vs = vs.SelectMany(v => new[] { v, v }).ToList();
        var d = drill;
        // his own setup's: his grenade itself, not the guide's from the words (20/10, his exec B molotov: "que la personne
        // derrière la charrette brûle 100% du temps"; the guide's from the words popped 33 u off his)
        var nade = drill.HisNade ?? guideLast;
        var g = sessGen;
        var k = 0;
        var own = false;
        stVictims = true;
        void Next()
        {
            if (g != sessGen || drill != d) return;
            if (k >= vs.Count && d.Type == "flash" && !own && d.Me != null && nadePop is { } fp)
            {   // and on your own spot, turned to it (19/10, his video: "je flash un endroit que je vois en ligne directe ... je
                // me fais tuer"): blinded by it there, the place it pops sees you
                own = true;
                var eye = new Vector3(d.Me.Pos[0], d.Me.Pos[1], d.Me.Pos[2] + (d.How.Contains("crouch") ? 46 : 64));
                var look = LookAt(eye, fp);
                t.Path = new[] { d.Me.Pos[0], d.Me.Pos[1], d.Me.Pos[2], look.Y, look.X };
                if (c.PlayerPawn.Value is not { } pw0) { Next(); return; }
                pw0.Teleport(new Vector3(d.Me.Pos[0], d.Me.Pos[1], d.Me.Pos[2]), Upright(look), Vector3.Zero);
                ClearNades();
                AddTimer(0.6f, () =>
                {
                    if (g != sessGen || drill != d || c.PlayerPawn.Value is not { } q2) return;
                    ThrowAs(c, q2, nade);
                    AddTimer(2.2f, () =>
                    {
                        if (g != sessGen || drill != d || c.PlayerPawn.Value is not { } q3) return;
                        var fl = q3.FlashDuration;
                        St("thrower", new() { ["flash"] = MathF.Round(fl, 2), ["seen"] = fl > 1f, ["pos"] = d.Me.Pos, ["pop"] = R3(fp) });
                        try { q3.FlashDuration = 0; } catch (Exception) { }
                        Next();
                    });
                });
                return;
            }
            if (k >= vs.Count) { t.Path = path0; stVictims = false; DrillDone(res.ok, res.outcome, res.pts, res.detail); return; }
            var v = vs[k];
            var i = k++;
            var face = VictimFace(d, v);
            t.Path = new[] { v.Pos[0], v.Pos[1], v.Pos[2], face.Y, face.X };   // held there by the bots' loop, turned that way
            if (!c.PawnIsAlive) c.Respawn();   // a fire that killed it on the last spot
            var pw = c.PlayerPawn.Value;
            if (pw == null) { Next(); return; }
            pw.Health = 500;   // a fire's 7 s measured whole, never down before its end (20/10: 100 at the first spot, dead for the next)
            Utilities.SetStateChanged(pw, "CBaseEntity", "m_iHealth");
            pw.Teleport(new Vector3(v.Pos[0], v.Pos[1], v.Pos[2]), Upright(face), Vector3.Zero);
            ClearNades();
            AddTimer(0.6f, () =>
            {
                if (g != sessGen || drill != d || c.PlayerPawn.Value is not { } p2) return;
                stVicPop = null;
                ThrowAs(c, p2, nade);
                // a fire spreads for its 7 s (20/10: his cart spot, 165 u from where it bursts, burned 5 s after the throw, measured at 4 s: untouched)
                var wait = d.Type switch { "smoke" => 4.5f, "molotov" => 6.5f, _ => 2.2f };
                // a smoke measured once it has popped, 6 s more at most (20/10: a long one, still rolling 4.5 s after it was
                // thrown, was measured on its way, 700 u off)
                var tries = d.Type == "smoke" ? 12 : 0;
                void Look() => AddTimer(wait, () =>
                {
                    if (g != sessGen || drill != d || c.PlayerPawn.Value is not { } p3) return;
                    if (stVicPop == null && tries-- > 0) { wait = 0.5f; Look(); return; }
                    var eye = new Vector3(v.Pos[0], v.Pos[1], v.Pos[2] + 64);
                    float yr = v.Ang[1] * MathF.PI / 180, pr = v.Ang[0] * MathF.PI / 180;
                    var fw = new Vector3(MathF.Cos(pr) * MathF.Cos(yr), MathF.Cos(pr) * MathF.Sin(yr), -MathF.Sin(pr));
                    float? cut = null;
                    if (d.Type == "smoke" && d.Me != null)
                    {   // the cloud's centre against the line from them to you (the one it is for: them seeing you come),
                        // how near that line passes, between the two
                        var sm = stVicPop ?? Utilities.FindAllEntitiesByDesignerName<CBaseEntity>("smokegrenade_projectile").Select(e => e.AbsOrigin)
                            .Where(o => o != null).Select(o => (Vector3?)new Vector3(o!.X, o.Y, o.Z)).FirstOrDefault();
                        if (sm is { } s1)
                        {
                            // one on his way in: the way on past it, the site he is kept from seeing (20/10, his video: "un
                            // joueur qui rotate du A vers le B, et qui arriverait au niveau du spawn CT"); else you
                            var to = v.See is { Length: >= 3 } s ? s : d.Me.Pos;
                            var you = new Vector3(to[0], to[1], to[2] + 64);
                            var seg = you - eye;
                            var q = new Vector3(s1.X, s1.Y, s1.Z + 40) - eye;
                            var u = Math.Clamp(Vector3.Dot(q, seg) / Math.Max(1f, seg.LengthSquared()), 0f, 1f);
                            cut = (q - seg * u).Length();
                        }
                    }
                    float? fire = null;   // a molotov: its nearest flame to them, how many (20/10: his cart spot, never reached here)
                    var flames = 0;
                    var where = new List<float[]>();
                    if (d.Type == "molotov")
                        try
                        {   // its flames read from the entity itself (this API's FirePositions throws: a Vector span)
                            var off = Schema.GetSchemaOffset("CInferno", "m_firePositions");
                            foreach (var inf in Utilities.FindAllEntitiesByDesignerName<CInferno>("inferno"))
                                for (int q = 0; q < Math.Min(inf.FireCount, 64); q++)
                                {
                                    var f0 = System.Runtime.InteropServices.Marshal.PtrToStructure<Vector3>(inf.Handle + off + q * 12);
                                    flames++;
                                    where.Add(new[] { R1(f0.X), R1(f0.Y), R1(f0.Z) });
                                    var dd = MathF.Sqrt((f0.X - v.Pos[0]) * (f0.X - v.Pos[0]) + (f0.Y - v.Pos[1]) * (f0.Y - v.Pos[1]));
                                    if (fire == null || dd < fire) fire = dd;
                                }
                        }
                        catch (Exception) { }
                    var flash = p3.FlashDuration;
                    var dmg = 500 - p3.Health;
                    var hit = d.Type switch { "flash" => flash > 0.5f, "smoke" => cut is < 144f, _ => dmg > 0 };
                    St("victim", new() { ["i"] = i, ["pos"] = v.Pos, ["ang"] = new[] { MathF.Round(face.X, 1), MathF.Round(face.Y, 1) }, ["type"] = d.Type, ["flash"] = MathF.Round(flash, 2), ["dmg"] = dmg,
                        ["cut"] = cut == null ? null : MathF.Round(cut.Value), ["hit"] = hit, ["fire"] = fire == null ? null : MathF.Round(fire.Value), ["flames"] = flames, ["where"] = where });
                    try
                    {
                        p3.Health = 100;
                        Utilities.SetStateChanged(p3, "CBaseEntity", "m_iHealth");
                        p3.FlashDuration = 0;
                    }
                    catch (Exception) { }
                    Next();
                });
                Look();
            });
        }
        Next();
    }

    // a log line, its {names} filled in order
    void StLog(string msg, object?[] args)
    {
        if (!selftest) return;
        var i = 0;
        var text = System.Text.RegularExpressions.Regex.Replace(msg, @"\{[^}]+\}", m => i < args.Length ? Convert.ToString(args[i++], CultureInfo.InvariantCulture) ?? "" : m.Value);
        St("log", new() { ["msg"] = text });
    }
}
