// Every player of a live drill, tick by tick, to a file (29/10, the user: "tu vas record ce que tu proposes sur la gestion
// des bots, et tu vas comparer la gestion de tes bots au comportement de vrais joueurs dans de vraies parties"): his game's
// own demo holds no bot (none in its players' table), so the plugin writes them: css_botrec <name> to coach/botrec/<name>.csv,
// css_botrec stop. A line a player a tick: tick, slot, steamid (0: a bot), team, x, y, z, yaw, pitch, flags, ducked,
// spotted, walking; a shot: "F", tick, slot, weapon. tools/bot_vs_real.py reads it as it reads a real match's demo.
using System.Globalization;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;

namespace CoachReplay;

public partial class CoachReplay
{
    StreamWriter? botRec;

    void BotRecLoad()
    {
        AddCommand("css_botrec", "every player of a live drill to coach/botrec/<name>.csv: css_botrec <name>|stop", (p, c) =>
        {
            if (p != null) return;
            botRec?.Flush(); botRec?.Dispose(); botRec = null;
            var name = c.GetArg(1);
            if (string.IsNullOrWhiteSpace(name) || name == "stop" || name.Contains('/') || name.Contains('\\') || name.Contains("..")) { Log("botrec: off"); return; }
            var d = Path.Combine(Dir, "botrec");
            Directory.CreateDirectory(d);
            botRec = new StreamWriter(Path.Combine(d, name + ".csv"), false) { AutoFlush = false };
            botRec.WriteLine("tick,slot,steamid,team,x,y,z,yaw,pitch,flags,ducked,spotted,walking");
            Log("botrec: {n}", name);
        });
        RegisterEventHandler<EventWeaponFire>((e, _) =>
        {
            if (botRec != null && phase == "live" && e.Userid is { IsValid: true } u)
                botRec.WriteLine($"F,{Server.TickCount},{u.Slot},{e.Weapon}");
            return HookResult.Continue;
        });
    }

    void BotRecTick()
    {
        if (botRec == null || phase != "live") return;
        var ic = CultureInfo.InvariantCulture;
        foreach (var pl in Utilities.GetPlayers())
        {
            if (pl is not { IsValid: true, PawnIsAlive: true } || pl.TeamNum < 2 || pl.PlayerPawn.Value is not { } pw || pw.AbsOrigin is not { } o || pw.EyeAngles is not { } ea) continue;
            var duck = pw.MovementServices != null && new CCSPlayer_MovementServices(pw.MovementServices.Handle).Ducked;
            botRec.WriteLine(string.Join(",", Server.TickCount, pl.Slot, pl.IsBot ? 0 : (long)pl.SteamID, pl.TeamNum,
                o.X.ToString("F1", ic), o.Y.ToString("F1", ic), o.Z.ToString("F1", ic), ea.Y.ToString("F2", ic), ea.X.ToString("F2", ic),   // a head's sway is hundredths a tick
                pw.Flags, duck ? 1 : 0, pw.EntitySpottedState.Spotted ? 1 : 0, pw.IsWalking ? 1 : 0));
        }
        if (Server.TickCount % 640 == 0) botRec.Flush();
    }
}
