// The tables of the bots of the plugin's hand read off the game's thread (10/11, round 26, Inferno's first drill: its setup read
// them there, on the game's thread, 10.0 s for the map's 17 MB of cases on a busy disk; the server frozen that long, the
// player's connection choked, timed out 13 s on, and he came back with no body for the whole drill, "6 sans duel". On 04/11
// each map's first drill froze the server 0.3 to 6.7 s the same way, Dust2's 6.7 s, Cache's 3.7 s. 08/10's rule, forgotten
// for these: no file read on the game's thread, a frame of 0.2 s already drops him). Asked for as soon as the map is known
// (its start, the bots put in the plugin's hand, a drill's setup): read and parsed on a thread of their own, put in place
// on the game's thread the tick after. Till then they are empty and the bots keep to their demo's own ways and looks, as on a
// map with no table.
using System.Numerics;
using CounterStrikeSharp.API;

namespace CoachReplay;

public partial class CoachReplay
{
    string? tabMap;   // the map whose tables were asked for: in place, or on their way

    void TablesAsk(string? map = null)
    {
        var mp = map ?? Server.MapName;
        if (!scripted || string.IsNullOrEmpty(mp) || mp == tabMap) return;
        tabMap = mp;
        // the last map's go now, and what the bots kept from them
        lookTab = new(); dangerTab = new(); lookNow.Clear(); lookPick.Clear();
        moveTab = new(); utilTab = new(); roams.Clear();
        behTab = new();
        navPts = Array.Empty<Vector3[]>(); navCen = Array.Empty<Vector3>(); navBox = Array.Empty<(float, float, float, float)>();
        navLinks = Array.Empty<List<(int, Vector3, float, int)>>(); navLad = Array.Empty<(Vector3, Vector3)>();
        navGrid = new(); navBlocked.Clear(); navProg.Clear(); navFail.Clear();
        var dir = Dir;
        var asked = DateTime.UtcNow;
        new Thread(() =>
        {
            var set = new List<Action>();
            string? err = null;
            // nothing thrown out of this thread: it would take the server down with it
            try { set.Add(LookRead(dir, mp)); set.Add(MoveRead(dir, mp)); set.Add(BehRead(dir, mp)); set.Add(NavRead(dir, mp)); }
            catch (Exception e) { err = e.Message; }
            var secs = (DateTime.UtcNow - asked).TotalSeconds;
            OnGame(() =>
            {
                if (err != null) Log("tables: {m}", err);
                if (tabMap != mp) return;   // another map since: its own are on their way
                foreach (var put in set) put();
                Log("tables: {m} read in {s:F1} s, off the game's thread", mp, secs);
            });
        }) { IsBackground = true, Name = "coach-tables", Priority = ThreadPriority.BelowNormal }.Start();
    }
}
