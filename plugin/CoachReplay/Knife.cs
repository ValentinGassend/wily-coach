// The knife out to run where nobody can be (30/10, the user: "Pour gagner en vitesse de déplacement, prends ton couteau aussi.
// C'est ce que font très souvent les joueurs. Surtout quand ils partent du spawn ... Ou sur les zones où ils sont 100% sûrs
// qu'il n'y a personne. Ils prennent leur couteau pour gagner en vitesse de déplacement par rapport à leur arme principale"):
// one of your enemies on its way, 1,800 u from you or more, its side with no news of you for 3 s (seen or heard), runs with
// its knife (250 u/s; a rifle 215-225, Walk.cs's caps); its gun again within 1,400 u, at any news, and before it fights
// (Combat.cs FightScripted). Its switches 1.5 s apart at least.
using System.Numerics;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;

namespace CoachReplay;

public partial class CoachReplay
{
    readonly Dictionary<int, (bool On, int At)> knifeOut = new();
    static readonly string[] Pistols = { "glock", "hkp2000", "usp_silencer", "p250", "fiveseven", "tec9", "cz75a", "deagle", "revolver", "elite" };

    // its gun: a primary first, else its pistol
    static string? GunOf(Track t)
    {
        var all = new[] { t.Active }.Concat(t.Weapons).Where(w => !string.IsNullOrEmpty(w) && w.StartsWith("weapon_")
            && !w.Contains("knife") && !w.Contains("bayonet") && w != "weapon_c4" && !w.Contains("grenade") && !w.Contains("flashbang")
            && !w.Contains("molotov") && !w.Contains("decoy") && w != "weapon_taser").ToList();
        return all.FirstOrDefault(w => !Pistols.Any(p => w.EndsWith(p))) ?? all.FirstOrDefault();
    }

    // its speed crouched: a third of its weapon's (30/10, the user: "ils se déplacent accroupis beaucoup trop vite"; round
    // 11: 90 u/s at the median crouched, the knife's third for every weapon and the friction's top-up over it, 2.5 % of it
    // over 150 u/s, a fight's strafe crouched; real Ts 72, an AK's third 73): 0.315 of it, its top-up making it 0.34
    static float CrouchCap(CCSPlayerPawn pw) =>
        0.315f * (KnifeIn(pw) ? 250f : WClass(pw) switch { "awp" => 200f, "rifle" => 220f, _ => 240f });

    static bool KnifeIn(CCSPlayerPawn pw) =>
        pw.WeaponServices?.ActiveWeapon.Value?.DesignerName is { } n && (n.Contains("knife") || n.Contains("bayonet"));

    void KnifeTick(int slot, CCSPlayerController c, Track t, Vector3 here, Vector3? mePos)
    {
        if (cur == null || t.Team == cur.Team || mePos is not { } me) return;
        var now = Server.TickCount;
        var d = Vector3.Distance(here, me);
        var news = false;
        foreach (var book in new[] { sideSeen.GetValueOrDefault(t.Team), sideHeard.GetValueOrDefault(t.Team) })
            if (book != null && book.Values.Any(k => now - k.T < 192)) news = true;
        (bool On, int At) k = knifeOut.TryGetValue(slot, out var k0) ? k0 : (false, -1000);
        var want = k.On ? d > 1400f && !news : d > 1800f && !news;
        if (want == k.On || now - k.At < 96) return;
        var gun = GunOf(t);
        if (gun == null) return;
        c.ExecuteClientCommandFromServer(want ? "use weapon_knife" : $"use {gun}");
        knifeOut[slot] = (want, now);
    }

    // its gun in its hands before it fights (drawn from the knife: the draw is its own delay, as a player's)
    void GunUp(int slot, CCSPlayerController c, Track t, CCSPlayerPawn pw)
    {
        if (!(knifeOut.TryGetValue(slot, out var k) && k.On) && !KnifeIn(pw)) return;
        if (GunOf(t) is { } gun) c.ExecuteClientCommandFromServer($"use {gun}");
        knifeOut[slot] = (false, Server.TickCount);
    }
}
