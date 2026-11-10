// The sandbox (19/10, his video: "le problème c'est que j'ai pas de stuff si je mets stop ... j'aimerais être en
// sandbox"): once a session of yours ends (its time, or !stop), or with !sandbox, the map is yours: every grenade, never
// used up, a buy menu anywhere, no round end, back alive at once, no bot. What you throw and jump there is recorded
// (Recorder.cs): !keep a good throw, !setup <name> saves the kept ones, !jump <name> your last jump.
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Cvars;

namespace CoachReplay;

public partial class CoachReplay
{
    bool sandbox;
    int noclipOff;   // the sandbox's own noclip off as it ends, let through

    void RegisterSandbox()
    {
        AddCommand("css_sandbox", "the map to yourself: every grenade, never used up: !sandbox", (p, _) => SandboxOn(p));
        // your last grenade thrown again (20/10, the user: "il faudrait que la touche F5 fasse re-throw le dernier stuff
        // envoyé en mode sandbox"): the app binds F5 to it (a console command: nothing said in a chat; unknown elsewhere)
        AddCommand("css_rt", "your last grenade thrown again, in the sandbox: F5", (p, _) =>
        {
            if (!sandbox) { Say(p, T("F5 rethrows your last grenade in the sandbox only")); return; }
            Server.ExecuteCommand("sv_rethrow_last_grenade");
        });
        // your noclip key in the sandbox only (28/10, the user: "activer l'autorisation de noclip uniquement quand les
        // entraînements sont finis et que je suis en mode sandbox": his noclip is on Alt, an Alt-Tab toggled it in a drill;
        // the test driver keeps sv_cheats on for setang): a player's noclip refused outside it
        AddCommandListener("noclip", (p, info) =>
        {
            if (p == null || sandbox || noclipOff > 0) { if (noclipOff > 0) noclipOff--; return HookResult.Continue; }
            Log("noclip refused: not in the sandbox");
            // and his game told again that he walks (29/10, the user in a test: "je suis actuellement en noclip sans le
            // vouloir": the server kept him walking, his game, with the test's cheats on, flew on its own prediction)
            var who = p;
            AddTimer(0.05f, () => { if (who.IsValid && who.PawnIsAlive && who.PlayerPawn.Value is { } pw) Freeze(pw, false); });
            AddTimer(0.5f, () => { if (who.IsValid && who.PawnIsAlive && who.PlayerPawn.Value is { } pw) Freeze(pw, false); });
            return HookResult.Handled;
        }, HookMode.Pre);
        RegisterEventHandler<EventPlayerSpawn>((e, _) =>
        {
            if (sandbox && e.Userid is { IsValid: true, IsBot: false } u)
                AddTimer(0.3f, () => { if (sandbox && u.IsValid) SandboxKit(u); });   // after the game's own loadout
            return HookResult.Continue;
        });
    }

    void SandboxOn(CCSPlayerController? p)
    {
        if (sess != null) { Say(p, T("a session is running: !stop first")); return; }
        sandbox = true;
        foreach (var cmd in new[] { "mp_warmup_end", "mp_ignore_round_win_conditions 1", "mp_freezetime 0", "mp_roundtime 60",
                     "mp_roundtime_defuse 60", "mp_roundtime_hostage 60", "mp_buy_anywhere 1", "mp_buytime 99999", "mp_maxmoney 65535",
                     "mp_startmoney 65535", "mp_afterroundmoney 65535", "mp_respawn_on_death_ct 1", "mp_respawn_on_death_t 1",
                     "ammo_grenade_limit_total 5", "mp_solid_teammates 0", "bot_quota 0", "bot_kick" })
            Server.ExecuteCommand(cmd);
        try { ConVar.Find("sv_infinite_ammo")?.SetValue(1); } catch (Exception) { }   // a grenade thrown stays in hand
        // your noclip key works (20/10, his video: "pour pouvoir noclip avec ma touche de noclip"): the server's cheats on
        Server.ExecuteCommand("sv_cheats 1");
        Prac(true);   // the grenade's trail after the throw
        // and here (20/10, his video: "une caméra grenade en aperçu en bas à gauche comme j'ai avec l'exec practice, et le
        // tracé de la trajectoire de la flash aussi"): the practice camera with the path while you aim, its trail 10 s;
        // never in a drill (04/10: there, finding the throw without it is the drill)
        Server.ExecuteCommand("sv_grenade_trajectory_prac_pipreview 1");
        Server.ExecuteCommand("sv_grenade_trajectory_prac_trailtime 10");
        foreach (var h in Humans()) SandboxKit(h);
        Html($"<font color='#56d4c8'>{T("SANDBOX")}</font><br><font class='fontSize-s'>{T("every grenade, never used up · !keep after a good throw, !setup and a name saves them · !jump and a name saves your last jump")}</font>", 8);
        All($"{T("SANDBOX")} · {T("every grenade, never used up · !keep after a good throw, !setup and a name saves them · !jump and a name saves your last jump")}");
    }

    // his grenades, each once (one of each kind, two flashes): the ones he has are not given again
    void SandboxKit(CCSPlayerController h)
    {
        if (!h.PawnIsAlive || h.PlayerPawn.Value is not { } pw) return;
        var have = pw.WeaponServices?.MyWeapons.Select(w => w.Value?.DesignerName).Where(n => n != null).ToList() ?? new List<string?>();
        var molly = pw.TeamNum == 3 ? "weapon_incgrenade" : "weapon_molotov";
        foreach (var w in new[] { "weapon_smokegrenade", "weapon_flashbang", "weapon_hegrenade", molly })
            if (!have.Contains(w)) h.GiveNamedItem(w);
        h.GiveNamedItem("item_assaultsuit");
    }

    // a session starts: the sandbox's own settings back (the drills set the round's again, Setup)
    void SandboxOff()
    {
        if (!sandbox) return;
        Ammo(false);
        Prac(false);
        // your noclip off while the cheats are still on, then walking (20/10, his Momentum after the sandbox: "comme si mon
        // personnage était à moitié en train de voler", till the whole server was restarted)
        foreach (var h in Humans())
        {
            if (h.PlayerPawn.Value is not { } pw) continue;
            if (pw.MoveType == MoveType_t.MOVETYPE_NOCLIP) { noclipOff++; h.ExecuteClientCommandFromServer("noclip"); }
            Freeze(pw, false);   // walking whatever it was (22/10: the bug came back after a sandbox without noclip)
        }
        sandbox = false;   // after its own noclip off (28/10: refused outside the sandbox)
        foreach (var cmd in new[] { "sv_cheats 0", "ammo_grenade_limit_total 4", "mp_maxmoney 16000", "mp_startmoney 800", "mp_afterroundmoney 0",
                     "mp_buy_anywhere 0", "mp_respawn_on_death_ct 0", "mp_respawn_on_death_t 0" })
            Server.ExecuteCommand(cmd);
    }
}
