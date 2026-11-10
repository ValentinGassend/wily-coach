// The classes the command hook checks before it writes into a bot's command (Combat.cs SimPre), found by their names in this
// server.dll at each css_scripted (MSVC RTTI: the type descriptor ".?AV<name>@@", its complete object locator, the vtable
// right after the pointer to it). 29/10: CS2 1.41.9.3 (08:21) moved them all by 0x10 to 0x18, every check failed and from
// then on no bot of the plugin's hand fired, nothing said (a day of measures with attackers that never shot).
using System.Runtime.InteropServices;
using System.Text;

namespace CoachReplay;

public partial class CoachReplay
{
    // 1.41.9.3's, till css_scripted finds this server.dll's own
    static long VtInButton = 0x17a2380, VtBasePB = 0x1849568, VtQAngle = 0x188dcb8, VtButtonPB = 0x1849388, VtUserCmd = 0x17b5440;

    static int GameServerSize() => System.Diagnostics.Process.GetCurrentProcess().Modules.Cast<System.Diagnostics.ProcessModule>()
        .FirstOrDefault(m => m.ModuleName.Equals("server.dll", StringComparison.OrdinalIgnoreCase)
                             && (m.FileName ?? "").Contains(Path.Combine("csgo", "bin", "win64"), StringComparison.OrdinalIgnoreCase))?.ModuleMemorySize ?? 0;

    static int Find(byte[] img, byte[] what, int from)
    {
        for (int i = Array.IndexOf(img, what[0], from); i >= 0 && i <= img.Length - what.Length; i = Array.IndexOf(img, what[0], i + 1))
        {
            int k = 1;
            while (k < what.Length && img[i + k] == what[k]) k++;
            if (k == what.Length) return i;
        }
        return -1;
    }

    // a class's primary vtable as an RVA (-1: not found)
    static long VtableOf(byte[] img, long mbase, string name)
    {
        var td = Find(img, Encoding.ASCII.GetBytes($".?AV{name}@@\0"), 0);
        if (td < 0) return -1;
        td -= 0x10;   // the descriptor itself: its vtable pointer and its spare before the name
        var tdb = BitConverter.GetBytes((uint)td);
        for (int j = Find(img, tdb, 0); j >= 0; j = Find(img, tdb, j + 1))
        {
            var col = j - 12;
            if (col < 0 || col % 4 != 0 || BitConverter.ToUInt32(img, col) != 1 || BitConverter.ToUInt32(img, col + 4) != 0
                || BitConverter.ToUInt32(img, col + 20) != (uint)col) continue;
            var at = Find(img, BitConverter.GetBytes(mbase + col), 0);
            if (at >= 0) return at + 8;
        }
        return -1;
    }

    bool RttiVtables(nint mbase)
    {
        var size = GameServerSize();
        if (mbase == 0 || size <= 0) return false;
        var img = new byte[size];
        try { Marshal.Copy(mbase, img, 0, size); }
        catch (Exception e) { Log("rtti: {m}", e.Message); return false; }
        long a = VtableOf(img, mbase, "CInButtonState"), b = VtableOf(img, mbase, "CBaseUserCmdPB"), q = VtableOf(img, mbase, "CMsgQAngle"),
             p = VtableOf(img, mbase, "CInButtonStatePB"), u = VtableOf(img, mbase, "CUserCmd");
        Log("rtti: CInButtonState {a:X}, CBaseUserCmdPB {b:X}, CMsgQAngle {q:X}, CInButtonStatePB {p:X}, CUserCmd {u:X}", a, b, q, p, u);
        if (a < 0 || b < 0 || q < 0 || p < 0) return false;
        VtInButton = a; VtBasePB = b; VtQAngle = q; VtButtonPB = p;
        if (u >= 0) VtUserCmd = u;
        return true;
    }
}
