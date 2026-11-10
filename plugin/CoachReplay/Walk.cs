// A bot on its way, live (29/10, the user, watching Mirage's defense: "il faut toujours que les bots ... se dirigent vers là
// où je suis censé défendre par le chemin relativement court ... je veux plus du tout de téléportation, plus du tout de bots
// qui bug dans les murs. Ni de bots qui se déplacent beaucoup trop vite"). It moves by its speed alone, a player's with its
// weapon at most and a player's legs (no jump from 0 to full speed), the game's walls and floors with it; its way's clock
// follows it (the way waits when it is behind). It used to be put back on its way once 72 u off (a teleport, at times into a
// wall) and to catch up at up to 1.6 times its speed. A defense's attacker that lost its way, or was held 2 s, takes the
// shortest real way to your zone among its drill's attackers' ways.
using System.Numerics;
using CounterStrikeSharp.API;
using CounterStrikeSharp.API.Core;
using CounterStrikeSharp.API.Modules.Utils;

namespace CoachReplay;

public partial class CoachReplay
{
    // a self-test's count of its walking this drill: ticks, over its speed, off its way (over 160 u), lost, ways to your zone
    readonly int[] walkChk = new int[5];
    // each bot's place on its way (the frame it was nearest to last tick, on that way) and where it stood: its real speed
    readonly Dictionary<int, (float[] Path, int K, Vector3 At)> wayK = new();
    // each bot's speed asked last tick and the ticks it has been held under half of it (a wall, a step): a speed slower than
    // its way's, as it gets going again, is no block (29/10, the user: "les bots s'arrêtent ... pour reprendre une demi-seconde
    // plus tard ... et ils le font en sautant": each start after a stop was taken for a block, and hopped)
    readonly Dictionary<int, (float Want, float Asked, int Held, Vector2 Dir)> walkAsk = new();
    readonly Dictionary<int, int> walkStuck = new();
    readonly Dictionary<int, bool> wayShift = new();   // a bot on its way at a walk's speed: Shift held in its command   // a self-test: ticks standing while its way runs on   // the speed it wants, the one it was given

    void WalkSay()
    {
        if (walkChk[0] > 0)
            Log("walkcheck: {n} ticks walking, over a player's speed {o}, off its way {f}, lost {l}, ways to your zone {z}",
                walkChk[0], walkChk[1], walkChk[2], walkChk[3], walkChk[4]);
        Array.Clear(walkChk);
    }

    // the speed to give so that it moves at `v` once the game's friction has had this tick (sv_friction 5.2, sv_stopspeed 80),
    // on the ground: a speed set alone loses 6.5 u/s a tick when slow (29/10, v6: 6 u/s more a tick never got one going, 70 %
    // of the time stopped)
    static Vector2 PastFriction(Vector2 v, bool ground)
    {
        var s = v.Length();
        return !ground || s < 1f ? v : v * ((s + 6.5f) / s);   // v7, the speed's share: 1.5 % of the time over a player's speed
    }

    // the frame of its way nearest to it between a and b, its height counting three times (tol: none further up or down)
    static (int K, float D) NearOnWay(Track t, Vector3 here, int a, int b, float tol)
    {
        int k = -1; var best = float.MaxValue;
        for (int j = Math.Max(0, a); j <= Math.Min(t.Frames - 1, b); j++)
        {
            var q = Pos(t, j); var dz = q.Z - here.Z;
            if (Math.Abs(dz) > tol) continue;
            var d = new Vector2(q.X - here.X, q.Y - here.Y).LengthSquared() + 9f * dz * dz;
            if (d < best) { best = d; k = j; }
        }
        return (k, k < 0 ? float.MaxValue : MathF.Sqrt(best));
    }

    readonly Dictionary<int, (float[] Path, int K, int Tick)> wayHead = new();   // its last headway on its way: where, when
    readonly Dictionary<int, (int Wave, int N)> spaceHeld = new();   // a defense's attacker held behind its wave's first: ticks, this wave

    // one of its wave nearer the post they go for than it, alive, not in its fight yet, within 220 u of it (WalkWay; the
    // post, not you: where you stand is nothing they know)
    bool WaveAhead(int slot, Vector3 here, Vector3 me)
    {
        var mine = Vector3.Distance(here, me);
        foreach (var sl in Attackers())
        {
            if (sl == slot || engaged.ContainsKey(sl) || !Up(sl)) continue;
            if (Utilities.GetPlayerFromSlot(sl)?.PlayerPawn.Value?.AbsOrigin is not { } o) continue;
            var q = new Vector3(o.X, o.Y, o.Z);
            if (Vector3.Distance(q, here) < 220f && Vector3.Distance(q, me) < mine - 30f) return true;
        }
        return false;
    }

    void WalkWay(int slot, CCSPlayerController c, Track t, CCSPlayerPawn pawn, Vector3 here, float ft, int i, Vector3 face, bool eng,
                 int stillN, float realV, Vector3? mePos)
    {
        var fps = cur!.Rate / (float)cur.Step;
        if (selftest) walkChk[0]++;
        if (!eng && ScriptedDrill) KnifeTick(slot, c, t, here, mePos);   // its knife out far from you (Knife.cs)
        // one behind the other (03/11, round 19, Train's B: the first of a wave held 2 s by a wall, the second, 1.2 s behind,
        // came up to it, both saw you the same tick 600 u off, you dead in 0.55 s; real Ts 460 u from their nearest teammate):
        // a defense's attacker not fighting waits while one of its wave nearer your zone, not fighting either, is within 220 u
        // of it; 3 s a wave at most. Its fight starts the trade: it comes on then, a second behind
        if (!eng && drill?.Mode == "defend" && WaveAhead(slot, here, DefendSpot()))
        {
            var sh = spaceHeld.TryGetValue(slot, out var s0) && s0.Wave == wave ? s0 : (wave, 0);
            if (sh.Item2 < 3 * 64)
            {
                spaceHeld[slot] = (wave, sh.Item2 + 1);
                pawn.Teleport(null, face, Vector3.Zero);
                if (wayHead.TryGetValue(slot, out var wh0)) wayHead[slot] = (wh0.Path, wh0.K, Server.TickCount);   // a wait, no headway lost
                return;
            }
        }
        // where it is on its way: the frame nearest to it, from where it was last tick to a second and a half on, never back
        // (a peek and back is followed: 29/10, server 2, the two legs taken one for the other held it at the turn), its
        // height counting three times; off it (it fell, it was pushed): the nearest point of its way's rest on its floor
        var had = wayK.TryGetValue(slot, out var wk) && ReferenceEquals(wk.Path, t.Path) && wk.K <= i + 2f * fps;   // else a new way, a new life
        var from = had ? wk.K : Math.Max(0, i - (int)(0.5f * fps));
        var (k0, d0) = NearOnWay(t, here, from, from + (int)(1.5f * fps), 9999f);
        if (d0 > 160f)
        {
            (k0, d0) = NearOnWay(t, here, from, t.Frames - 1, 40f);
            if (selftest) walkChk[2]++;
        }
        // held: it wants to go (over 60 u/s) and gets under half the speed it was given (its legs' own, a little over its real
        // one: 29/10 16:15, the given speed alone never passed 60 against a step, so nothing was held, nothing hopped: stuck)
        // its speed along where it was sent, not its speed: sliding along a wall is held too (30/10, Train's T Upper: two bots
        // slid crouched along a ledge, 440 u east and west at 80 u/s for 100 s, never held, never hopped, never another way)
        walkAsk.TryGetValue(slot, out var wa);
        var along = had && realV >= 0f && wa.Dir != Vector2.Zero ? Vector2.Dot(new Vector2(here.X - wk.At.X, here.Y - wk.At.Y) * 64f, wa.Dir) : realV;
        var held = wa.Want > 60f && realV >= 0f && along < Math.Max(10f, 0.4f * wa.Asked) ? wa.Held + 1 : 0;   // v7: 'given over 10' never came against a ledge, getting going slowly
        // no headway on its way for 2 s while it wants to go: held too (30/10, round 13, Train's B: two attackers ran 110 s to
        // and fro along a passage at T Upper the real players went through, closed here, a gap in the map's own mesh: sideways
        // to it, never "held", their way's clock waiting for them; the wave never came)
        var nowT = Server.TickCount;
        // a slow stretch counts too (31/10, Nuke's A: the last of a wave held 97 s where its real player walked slowly, its way's
        // clock waiting for it, never "wanting" 60 u/s); a real stand moves its anchor on (above); a fight is no headway to make
        if (!wayHead.TryGetValue(slot, out var wh) || !ReferenceEquals(wh.Path, t.Path) || k0 > wh.K || eng) wayHead[slot] = wh = (t.Path, k0, nowT);
        var noHead = nowT - wh.Tick > 128;
        if (k0 < 0 || d0 > 600f || held > 128 || noHead)
        {   // lost, or held 2 s by something: another way, not through that spot
            if (selftest) walkChk[3]++;
            if (noHead) Log("scripted: {n} no headway on its way for 2 s at {x:F0} {y:F0} {z:F0}", t.Name, here.X, here.Y, here.Z);
            botStill.Remove(slot); wayK.Remove(slot); wayHead.Remove(slot);
            walkAsk.Remove(slot);
            if (WayToZone(t, here, mePos, held > 128 || noHead ? here : null)) return;
            if (WayBack(t, here, i, held > 128)) return;
            Free(slot, c, t); Log("free {n} at {f} (lost its way)", t.Name, (int)ft);
            return;
        }
        // a stand on its way (its real player stood there, holding an angle): its anchor goes on with its clock while it stands
        // there too, and its way on when his did (30/10, round 11: the anchor the first frame of the stand, its clock held
        // 0.35 s past it, the stand never over: Inferno's havenN still 30 s, envy 14 s, the situations' enemies never came)
        if (k0 >= 0)
            while (k0 + 1 < t.Frames && k0 + 1 <= ft && Pos(t, k0 + 1) is var q1
                   && new Vector2(q1.X - here.X, q1.Y - here.Y).Length() < 12f && MathF.Abs(q1.Z - here.Z) < 24f) k0++;
        // its real speed (where it stood last tick: the game's walls in it)
        var cv = had && realV >= 0f ? new Vector2(here.X - wk.At.X, here.Y - wk.At.Y) * 64f : pawn.AbsVelocity is { } av0 ? new Vector2(av0.X, av0.Y) : Vector2.Zero;
        wayK[slot] = (t.Path, k0, here);
        // its way's clock a third of a second ahead of it at most (the way waits for it), never behind it
        var lead = 0.35f * fps;
        if (ft > k0 + lead) { var w = ft - (k0 + lead); t.Start += w; t.Warp += w; }
        else if (ft < k0) t.Start -= k0 - ft;
        var ka = Math.Min(t.Frames - 1f, k0 + lead);
        var aim = PathAt(t, ka);
        var a2 = PathAt(t, Math.Min(t.Frames - 1f, ka + 1f));
        var segV = new Vector2(a2.X - aim.X, a2.Y - aim.Y).Length() * fps;
        var segVz = (a2.Z - aim.Z) * fps;
        var ladder = pawn.MoveType == MoveType_t.MOVETYPE_LADDER;
        if (ladder || Climbing(t, k0, Math.Max(1, (int)(fps / 8f))))
        {   // up or down a ladder: along its way, by its speed too
            var to3 = aim - here;
            var v3 = to3.Length() < 4f ? Vector3.Zero : Vector3.Normalize(to3) * Math.Min(200f, Math.Max(80f, 3f * to3.Length()));
            pawn.Teleport(null, face, v3);
            return;
        }
        // off its way (64 u): to its nearest point by the map's mesh, round the walls in between (30/10, round 11: straight at
        // it into a wall, sliding or held, 15-25 s lost, then lost; Nav.cs); its speed and its rise still its way's
        // (its height aside: on stairs it counts three times in d0); the mesh's point only where an edge lies in between
        var near0 = Pos(t, k0);
        if (navPts.Length > 0 && new Vector2(near0.X - here.X, near0.Y - here.Y).Length() > 64f)
        {
            var st = NavSteer(slot, here, near0, segV > 60f);
            if (NavClimb(slot, here) is { } lv) { pawn.Teleport(null, face, lv); return; }   // a ladder of its mesh way
            if (Vector3.Distance(st, near0) > 1f) aim = st;
        }
        else navWay.Remove(slot);
        // a player's speed with its weapon; a walk stays a walk (silent, 06/10)
        var cap = KnifeIn(pawn) ? 250f : WClass(pawn) switch { "awp" => 200f, "rifle" => 225f, _ => 245f };
        if (segV < 135f) cap = Math.Min(cap, 126f);
        // crouched: a third of it, as the game's (0.34; 29/10, the user: "parfois, ils se déplacent très vite accroupis")
        var duck = botHop.ContainsKey(slot) ? false : t.DuckFrames.Length > 0 && t.DuckAt(k0);
        var ducked = pawn.MovementServices != null && new CCSPlayer_MovementServices(pawn.MovementServices.Handle).Ducked;
        if (duck || ducked) cap = Math.Min(cap, CrouchCap(pawn));   // v4: 120 u/s crouched (a hop's crouch), real Ts 71
        // Shift held at a walk's speed: its walk the game's own (real Ts: 29 % of their moving; v7 never)
        var shift = cap <= 126f && !duck && !ducked;
        if (pawn.IsWalking != shift) { pawn.IsWalking = shift; Utilities.SetStateChanged(pawn, "CCSPlayerPawn", "m_bIsWalking"); }
        wayShift[slot] = shift;   // its command holds Shift then (Combat.cs SimPre: the game sets it walking from it)
        var to = new Vector2(aim.X - here.X, aim.Y - here.Y);
        var want = to.Length() < 4f ? Vector2.Zero : Vector2.Normalize(to) * Math.Min(cap, Math.Max(segV, 3f * to.Length()));
        // a player's legs: 24 u/s more or less each tick (the game's acceleration); getting going from a walk or a stop
        // slower, 6 u/s a tick under 130 (v4 went from 20 to 200 u/s in 0.16 s, real Ts in 0.7: they start, then run)
        var dv = want - cv;
        var acc = want.Length() > cv.Length() ? (cv.Length() < 150f ? 4f : 24f) : 32f;   // v7: 0.2 s from 20 to 200 u/s, real Ts 0.7; v8 braked in 0.39 s, real 0.23
        if (dv.Length() > acc) dv = Vector2.Normalize(dv) * acc;
        var v = cv + dv;
        if (v.Length() > cap) v = Vector2.Normalize(v) * cap;
        if (selftest && realV > 255f) walkChk[1]++;   // its real speed, the game's: from where it was the tick before
        var vz = pawn.AbsVelocity?.Z ?? 0f;
        if (!botHop.ContainsKey(slot)) vz = Math.Min(vz, Math.Max(0f, segVz) + 60f);   // a slope's push up kept tick after tick: a launch
        var ground = (pawn.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0;
        if (botHop.TryGetValue(slot, out var hopAt))
        {
            if ((ground && Server.TickCount - hopAt > 8) || Server.TickCount - hopAt > 64) { botHop.Remove(slot); Crouch(pawn, false); }   // landed (or a second: on a ladder)
        }
        else if (!eng && ground && JumpHere(t, k0, here, realV) is { } rise)
        {   // its way jumps here: so does it (crouched for a high one, as the player did: 66 u instead of 57)
            vz = rise > 58f ? 301.99f : Math.Clamp(MathF.Sqrt(1600f * rise), 180f, 301.99f);
            botHop[slot] = Server.TickCount;
            if (rise > 58f) Crouch(pawn, true);
            if (selftest) St("hop", new() { ["bot"] = t.Sid, ["f"] = R1(ft), ["at"] = R3(here), ["kind"] = "jump", ["rise"] = R1(rise) });
        }
        else if (!eng && ground && aim.Z - here.Z > 24f && aim.Z - here.Z < 72f && to.Length() < 64f && held >= 3)
        {   // blocked by a box or a ledge its way goes up onto: a crouch-jump
            vz = 300f;
            botHop[slot] = Server.TickCount;
            Crouch(pawn, true);
            if (selftest) St("hop", new() { ["bot"] = t.Sid, ["f"] = R1(ft), ["at"] = R3(here), ["kind"] = "blocked" });
        }
        else if (!eng && ground && (held >= 10 && aim.Z - here.Z > 6f || held >= 24))   // its way goes up there, or a kerb (v4: 11.7 jumps a minute, v9 3.1, real 6.4)
        {   // held on the ground while its way runs on: a step's hop, 18 u up first, higher only when that wasn't enough
            var tries = stepTries.GetValueOrDefault(slot);
            stepTries[slot] = tries + 1;
            vz = tries == 0 ? 170f : Math.Clamp(MathF.Sqrt(1600f * (Math.Max(aim.Z - here.Z, 12f) + 8f)), 190f, 240f);
            botHop[slot] = Server.TickCount;
            if (selftest) St("hop", new() { ["bot"] = t.Sid, ["f"] = R1(ft), ["at"] = R3(here), ["kind"] = "step" });
        }
        else if (t.DuckFrames.Length > 0) Crouch(pawn, duck);   // crouched where the real player was
        if (held == 0) stepTries.Remove(slot);   // going again: its next step hop the low one
        walkAsk[slot] = (want.Length(), v.Length(), held, want.Length() > 1f ? Vector2.Normalize(want) : Vector2.Zero);
        if (selftest)
        {   // a self-test: a bot standing a second while its way runs on, said once (what it was asked, where it aims)
            var sn = realV < 20f && segV > 100f ? walkStuck.GetValueOrDefault(slot) + 1 : 0;
            walkStuck[slot] = sn;
            if (sn == 64)
                Log("stuckdbg {n} at {x:F0} {y:F0} {z:F0}: aim {ax:F0} {ay:F0} {az:F0} ({d:F0} u), way {sv:F0} u/s, want {w:F0}, given {g:F0}, held {h}, hop {hp}, ground {gr}, duck {dk}, k {k} ft {ft:F1} of {fr}",
                    t.Name, here.X, here.Y, here.Z, aim.X, aim.Y, aim.Z, (aim - here).Length(), segV, want.Length(), v.Length(), held, botHop.ContainsKey(slot), ground, ducked, k0, ft, t.Frames);
        }
        var vg = PastFriction(v, ground && !botHop.ContainsKey(slot));
        pawn.Teleport(null, eng ? null : face, new Vector3(vg.X, vg.Y, vz));   // its speed only; fighting: its own aim
    }

    // a defense's attacker no way takes nearer your zone (29/10, v5: they camped at their ways' ends by the site; real Ts
    // go on in, clearing): it walks on to your spot (Shift, a player's legs), its eyes where players look there and on what
    // its side knows (Look.cs), till 200 u of it; held by something, it tries 50 deg to a side, then the other
    readonly Dictionary<int, (int Since, int Side)> hunt = new();
    bool sitHunt, foeSeenOnce;   // a situation: its enemies come for you now (past your death in the match); one came into your sight
    int sitExch = -1;   // a situation: the last tick you and one of them hurt each other (a duel), -1 none yet
    // its nearest to its goal and since when, holding till, its tries; its last tick hunting and its goal (another life, another
    // goal: anew)
    readonly Dictionary<int, (float Best, int At, int HoldUntil, int Fails, int Last, Vector2 Goal)> huntProg = new();
    readonly Dictionary<int, (Vector3 At, int Until)> huntAt = new();   // the point of your zone it heads for, till when
    // the mesh's length to its goal, asked once each half second at most (its search is the server's: 31/10, 4 fps when each
    // tick asked it for each hunter)
    readonly Dictionary<int, (int At, float Len)> huntLen = new();
    float HuntMeshLen(int slot, Vector3 here, Vector3 g, int now)
    {
        if (huntLen.TryGetValue(slot, out var hl) && now - hl.At < 32 && now >= hl.At) return hl.Len;
        var len = NavLen(here, g);
        huntLen[slot] = (now, len);
        return len;
    }

    bool Hunt(int slot, Fighter fi, CCSPlayerPawn pw, List<Vector3> smokes)
    {
        if (cur == null || !(drill?.Mode == "defend" || sitHunt) || pw.AbsOrigin is not { } o) return false;
        var here = new Vector3(o.X, o.Y, o.Z);
        var now = Server.TickCount;
        // where to (29/10, lab 24: walked to 200 u of your spot they stood there, often behind a box, and took the site
        // unseen): you where its side last saw or heard you (5 s at most), else a point of your zone, another once it got
        // there (it clears the zone till it finds you)
        Vector3? goal = null;
        var me = Humans().FirstOrDefault(h => h.PawnIsAlive);
        var team = fi.T?.Team ?? pw.TeamNum;
        if (me != null)
            foreach (var book in new[] { sideSeen.GetValueOrDefault(team), sideHeard.GetValueOrDefault(team) })
                if (book != null && book.TryGetValue(me.Slot, out var kn) && now - kn.T < 5 * 64 && (goal == null)) goal = kn.P;
        if (goal == null)
        {
            if (!huntAt.TryGetValue(slot, out var ha) || now > ha.Until || new Vector2(ha.At.X - here.X, ha.At.Y - here.Y).Length() < 120f)
            {
                var poly = postIdx >= 0 && postIdx < drill.Posts.Count ? drill.Posts[postIdx].Poly : null;
                Vector3 c0 = postIdx >= 0 && postIdx < drill.Posts.Count && drill.Posts[postIdx].Pos is { Length: >= 3 } sp ? new Vector3(sp[0], sp[1], sp[2])
                           : mePawnNow?.AbsOrigin is { } mo ? new Vector3(mo.X, mo.Y, mo.Z) : here;
                var at = c0;
                if (poly is { Count: >= 3 })
                {   // between its middle and one of its corners, drawn
                    var cx = poly.Average(p => p[0]); var cy = poly.Average(p => p[1]);
                    var k = poly[fi.Rng.Next(poly.Count)];
                    var f = 0.3f + 0.5f * (float)fi.Rng.NextDouble();
                    at = new Vector3(cx + (k[0] - cx) * f, cy + (k[1] - cy) * f, c0.Z);
                }
                huntAt[slot] = ha = (at, now + (sitHunt ? 64 : 6 * 64));   // a situation's hunt: you as you go, each second (30/10: 6 s behind you, never met)
            }
            goal = ha.At;
        }
        var g = goal.Value;
        var to = new Vector2(g.X - here.X, g.Y - here.Y);
        // there: the next point soon; by the mesh too, not through a wall (02/11, round 16, Mirage's R15 in Apps: a hunter stood
        // 38 u from him on a wall's other side, "there", neither of them ever in the other's sight)
        if (to.Length() < 40f && (navPts.Length == 0 || HuntMeshLen(slot, here, g, now) < 120f)) { pw.Teleport(null, null, new Vector3(0f, 0f, pw.AbsVelocity?.Z ?? 0f)); return true; }
        var cv = pw.AbsVelocity is { } av ? new Vector2(av.X, av.Y) : Vector2.Zero;
        // no nearer by 48 u in 4 s (a wall it slides along, a ledge over your zone): it holds 3 s from where it is, its eyes on
        // your zone, as a player holds from above, then walks again, aside the other way first (30/10, Train's T Upper: two
        // attackers slid along a ledge 100 s, never in a fight; Mirage's B: held for good after 3 tries, 90 s still)
        var g2 = new Vector2(g.X, g.Y);
        (float Best, int At, int HoldUntil, int Fails, int Last, Vector2 Goal) pr = huntProg.TryGetValue(slot, out var pr0) && now - pr0.Last < 64 && Vector2.Distance(pr0.Goal, g2) < 150f ? pr0 : (to.Length(), now, 0, 0, now, g2);
        if (to.Length() < pr.Best - 48f) pr = (to.Length(), now, pr.HoldUntil, 0, now, g2);
        else if (now >= pr.HoldUntil && now - Math.Max(pr.At, pr.HoldUntil) > 256)
        {
            pr = (to.Length(), now, now + 192, pr.Fails + 1, now, g2);
            hunt[slot] = (now + 192, pr.Fails % 2 == 0 ? 1 : -1);
        }
        huntProg[slot] = (pr.Best, pr.At, pr.HoldUntil, pr.Fails, now, g2);
        if (now < pr.HoldUntil)
        {
            var eye = new Vector3(here.X, here.Y, here.Z + (pw.ViewOffset?.Z ?? 64f));
            var want0 = AngTo(eye, new Vector3(g.X, g.Y, g.Z + 48f));
            fi.View = Turn(slot, fi.View, want0);
            SetEyes(pw, fi.View);
            var nv0 = cv.Length() < 5f ? Vector2.Zero : cv * 0.8f;   // stopped as a player stops
            pw.Teleport(null, new Vector3(0f, fi.View.Y, 0f), new Vector3(nv0.X, nv0.Y, pw.AbsVelocity?.Z ?? 0f));
            return true;
        }
        if (!hunt.TryGetValue(slot, out var h)) h = (now, 0);
        // its way there by the map's mesh, round the walls (Nav.cs); straight where the mesh has none
        if (navPts.Length > 0)
        {
            var st = NavSteer(slot, here, g);
            if (NavClimb(slot, here) is { } lv) { pw.Teleport(null, new Vector3(0f, fi.View.Y, 0f), lv); return true; }   // a ladder of its mesh way
            var ts = new Vector2(st.X - here.X, st.Y - here.Y);
            if (ts.Length() > 1f) to = ts;
        }
        // held: no nearer at 20 u/s 0.75 s after it set off, or after its last turn aside (sliding along a wall is held too):
        // the other side next
        var toward = to.Length() > 1f ? Vector2.Dot(cv, Vector2.Normalize(to)) : 0f;
        if (now - h.Since > 48 && toward < 20f) h = (now, h.Side <= 0 ? 1 : -1);
        else if (h.Side != 0 && now - h.Since > 64 && cv.Length() > 60f) h = (now, 0);   // round it: straight on again
        hunt[slot] = h;
        var dir = Vector2.Normalize(to);
        if (h.Side != 0)
        {
            var a = h.Side * 50f * MathF.PI / 180f;
            dir = new Vector2(dir.X * MathF.Cos(a) - dir.Y * MathF.Sin(a), dir.X * MathF.Sin(a) + dir.Y * MathF.Cos(a));
        }
        // far off it runs (its knife out if it has it), near it walks in (30/10: a situation's hunters came from far)
        // by its distance to you, not to its mesh way's next point (02/11, round 15, Fachwerk's hunts: 2,000 u off, 140-150 u/s
        // all the way, the next point always under 900 u; 15 s and more to come, the drill's end before them)
        var runs = new Vector2(g.X - here.X, g.Y - here.Y).Length() > 900f;
        var want = dir * (runs ? (KnifeIn(pw) ? 245f : 215f) : 126f);
        fi.Walk = !runs;   // a walk's speed, Shift held (Combat.cs SimPre)
        if (pw.IsWalking != !runs) { pw.IsWalking = !runs; Utilities.SetStateChanged(pw, "CCSPlayerPawn", "m_bIsWalking"); }
        var dv = want - cv;
        var acc = cv.Length() < 150f ? 4f : 24f;
        if (dv.Length() > acc) dv = Vector2.Normalize(dv) * acc;
        var v = cv + dv;
        if (fi.T != null && lookTab.Count > 0) fi.View = LookFor(slot, fi.T, here, fi.View, mePawnNow, smokes);
        SetEyes(pw, fi.View);
        v = PastFriction(v, (pw.Flags & (uint)PlayerFlags.FL_ONGROUND) != 0);
        pw.Teleport(null, new Vector3(0f, fi.View.Y, 0f), new Vector3(v.X, v.Y, pw.AbsVelocity?.Z ?? 0f));
        return true;
    }

    // the shortest real way to your zone from where it stands (29/10): among its drill's attackers' ways (all of them, not
    // only the few on the server), a point of one on its floor 250 u from it at most (none within 120 u of where it was held,
    // `avoid`), then that way up to its point nearest your zone (your spot, or you once you play free), the rest straight:
    // the least of its distance to that point and that walk
    // a situation's bot off its own way or held on it: on again at the nearest point of the rest of its way on its floor
    // (40 u up or down, as its walk finds it), 500 u at most, past the spot it was held at; its clock set there, so it walks to it (30/10,
    // Train's situations: lost 89 u off its way, freed, released back onto the same frame, lost again every 1.5 s for 30 s)
    bool WayBack(Track t, Vector3 here, int i, bool past)
    {
        if (cur == null || drill?.Mode == "defend") return false;
        var fps = cur.Rate / (float)cur.Step;
        var from = past ? i + (int)(0.5f * fps) : Math.Max(0, i - (int)fps);
        int bk = -1; var best = 500f;
        for (int k = from; k < t.Frames; k++)
        {
            var q = Pos(t, k);
            if (Math.Abs(q.Z - here.Z) > 40f) continue;
            var d = new Vector2(q.X - here.X, q.Y - here.Y).Length();
            if (d < best) { best = d; bk = k; }
        }
        // the same stretch of its way (a second of it) a third time: no more (Fachwerk's Apps: frames 372-374 taken again 30 times)
        if (bk < 0 || wayBackAt.TryGetValue(t.Sid, out var wb) && Math.Abs(wb.K - bk) < fps && wb.N >= 2) return false;
        wayBackAt[t.Sid] = (bk, Math.Abs(wb.K - bk) < fps ? wb.N + 1 : 1);
        t.Start = (Server.TickCount - t0) / (float)cur.Step - bk;
        Log("scripted: {n} back on its way at frame {k} of {f} ({d:F0} u)", t.Name, bk, t.Frames, best);
        return true;
    }
    readonly Dictionary<string, (int K, int N)> wayBackAt = new();

    readonly Dictionary<Track, (float[] W, int K, int Tick, int N)> wayZonePick = new();   // its last pick, and how many times in a row
    readonly Dictionary<Track, int> wayZoneMesh = new();   // by the mesh till then: asked again each tick by its fight, said once

    bool WayToZone(Track t, Vector3 here, Vector3? mePos, Vector3? avoid = null)
    {
        if (cur == null || drill?.Mode != "defend") return false;
        if (wayZoneMesh.TryGetValue(t, out var meshTill) && Server.TickCount < meshTill) return false;
        Vector3? goal = postIdx >= 0 && postIdx < drill.Posts.Count && drill.Posts[postIdx].Pos is { Length: >= 3 } sp
            ? new Vector3(sp[0], sp[1], sp[2]) : mePos;
        if (goal is not { } g) return false;
        static Vector3 P(float[] w, int k) => new(w[k * 5], w[k * 5 + 1], w[k * 5 + 2]);
        float[]? bw = null; string bn = ""; int bk = -1; var best = float.MaxValue; var bnear = 0f;
        foreach (var (w, wn) in drill.Tracks.Select(e => (e.Path, e.Zone)).Append((t.Path, t.Name)))
        {
            var n = w.Length / 5;
            if (n < 8) continue;
            // its cost to your zone from each of its frames, from its end back: there, or a step on and from there
            var cost = new float[n];
            var near = new float[n];   // the nearest it gets to your zone from there on
            cost[n - 1] = near[n - 1] = Vector3.Distance(P(w, n - 1), g);
            for (int k = n - 2; k >= 0; k--)
            {
                var dk = Vector3.Distance(P(w, k), g);
                cost[k] = Math.Min(dk, Vector3.Distance(P(w, k), P(w, k + 1)) + cost[k + 1]);
                near[k] = Math.Min(dk, near[k + 1]);
            }
            for (int k = 0; k < n - 4; k++)
            {
                var q = P(w, k);
                if (Math.Abs(q.Z - here.Z) > 48f) continue;
                var d = new Vector2(q.X - here.X, q.Y - here.Y).Length();
                if (d > 250f || avoid is { } av && Vector3.Distance(q, av) < 120f) continue;
                var s = 1.5f * d + cost[k];
                if (s < best && near[k] < Vector3.Distance(here, g) - 100f) { best = s; bw = w; bn = wn; bk = k; bnear = near[k]; }
            }
        }
        // none, or none that takes it nearer your zone than it is (29/10, v5: at their ways' ends by the site, 87 % of their
        // stops within 1,200 u of you, a way that ended there taken again and again, a minute and a half on a spot). Judged by
        // how near the way gets, not by its length (30/10, Mirage's B: a way's walk had to be 100 u shorter than the straight
        // line, so no bent way was ever taken: two attackers straight at you into the Apartments' walls, stood 90 s)
        if (bw == null) return false;
        // the mesh's way clearly shorter than any real one (40 % and 200 u): by the mesh instead, the ladders too (30/10, his
        // review on Overpass: "s'ils sont juste au-dessus de l'échelle qui mène à connecteur, ils passent par jardin d'enfants
        // ... alors qu'ils pourraient juste descendre connecteur")
        var meshLen = navPts.Length > 0 ? NavLen(here, g) : -1f;
        if (meshLen > 0f && best > 1.4f * meshLen + 200f)
        {
            Log("scripted: {n} to your zone by the map's mesh ({m:F0} u, its best real way {b:F0})", t.Name, meshLen, best);
            wayZoneMesh[t] = Server.TickCount + 6 * 64;
            return false;
        }
        // the same point of the same way again and again, never got to (30/10, Overpass: "Alley heads for your zone on Tunnels's
        // way (frame 142)" every 2 s for 40 s): the third time by the mesh
        var now = Server.TickCount;
        var again = wayZonePick.TryGetValue(t, out var wp) && ReferenceEquals(wp.W, bw) && Math.Abs(wp.K - bk) < 16 && now - wp.Tick < 8 * 64;
        wayZonePick[t] = (bw, bk, now, again ? wp.N + 1 : 1);
        if (again && wp.N + 1 >= 3)
        {
            Log("scripted: {n} never got to its way's point, to your zone by the map's mesh", t.Name);
            wayZoneMesh[t] = now + 6 * 64;
            wayZonePick.Remove(t);
            return false;
        }
        if (!ReferenceEquals(bw, t.Path)) t.TakeWay(bw);   // another one's way: its points; no crouch, no grenade, no death
        t.Start = (Server.TickCount - t0) / (float)cur.Step - bk;
        if (selftest) walkChk[4]++;
        Log("scripted: {n} heads for your zone on {w}'s way (frame {k} of {f})", t.Name, bn, bk, bw.Length / 5);
        return true;
    }
}
