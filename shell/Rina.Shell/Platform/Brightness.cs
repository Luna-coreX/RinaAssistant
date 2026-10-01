using System.Runtime.InteropServices;

namespace Rina.Shell.Platform;

/// <summary>
/// The screen's brightness (<c>4.0b-K04</c>).
/// </summary>
/// <remarks>
/// <para>
/// Two kinds of screen, two ways in, and neither works everywhere:
/// </para>
/// <list type="bullet">
/// <item>a laptop's own panel answers to WMI
/// (<c>WmiMonitorBrightnessMethods</c>) — reliably, where there is one;</item>
/// <item>an external monitor answers to DDC/CI through <c>dxva2.dll</c> —
/// when the monitor supports it and has it switched on in its own menu,
/// which many do not.</item>
/// </list>
/// <para>
/// <b>A screen that cannot be driven is said to be so.</b> When neither
/// way reaches any screen the answer is <c>unsupported</c>, and the core
/// says that in words; a brightness command that "worked" while nothing on
/// the desk changed would teach a person that Rina says things that are not
/// true.
/// </para>
/// <para>
/// WMI is reached through its COM scripting object rather than the
/// <c>System.Management</c> package: it is in every Windows, and a NuGet
/// dependency for two calls would be one more thing to download, sign and
/// keep current.
/// </para>
/// </remarks>
public static class Brightness
{
    /// <summary>What the shell says when no screen takes the command.</summary>
    public const string Unsupported = "unsupported";

    /// <summary>
    /// Set every screen that can be driven to a level from 0 to 100.
    /// </summary>
    public static (bool Ok, string Detail) Set(int level)
    {
        level = Math.Clamp(level, 0, 100);
        var reached = 0;
        if (SetPanel(level)) reached++;
        reached += ForEachMonitor((handle, min, _, max) =>
            SetMonitorBrightness(handle, (uint)(min + (max - min) * level / 100)));
        return reached > 0 ? (true, level.ToString()) : (false, Unsupported);
    }

    /// <summary>Brighter or darker by a step, from where it is now.</summary>
    public static (bool Ok, string Detail) Step(int delta)
    {
        var now = Current();
        if (now is null) return (false, Unsupported);
        return Set(Math.Clamp(now.Value + delta, 0, 100));
    }

    /// <summary>
    /// The brightness now, from 0 to 100 — the panel's, else the first
    /// monitor's — or null when no screen will say.
    /// </summary>
    public static int? Current()
    {
        var panel = PanelLevel();
        if (panel is not null) return panel;
        int? found = null;
        ForEachMonitor((handle, min, now, max) =>
        {
            if (found is null && max > min)
                found = (int)Math.Round(100.0 * (now - min) / (max - min));
            return found is not null;
        });
        return found;
    }

    /// <summary>Can any screen here be driven at all — for the editor.</summary>
    /// <remarks>
    /// Asked by the command editor before a command is saved, so a person
    /// learns at the desk, not at seven in the morning, that this machine's
    /// screen does not take the command. Remembered for a minute: the
    /// question costs a WMI query and a DDC/CI round per monitor, and the
    /// editor asks on every keystroke.
    /// </remarks>
    public static bool Available()
    {
        if (DateTime.UtcNow - _askedAt < TimeSpan.FromMinutes(1))
            return _available;
        _available = Current() is not null;
        _askedAt = DateTime.UtcNow;
        return _available;
    }

    private static bool _available;
    private static DateTime _askedAt = DateTime.MinValue;

    // --- the laptop's panel: WMI ------------------------------------------------
    private static int? PanelLevel()
    {
        try
        {
            foreach (var item in Query("SELECT CurrentBrightness FROM WmiMonitorBrightness"))
                return (int)(byte)item.CurrentBrightness;
        }
        catch (COMException) { }
        catch (Microsoft.CSharp.RuntimeBinder.RuntimeBinderException) { }
        return null;
    }

    private static bool SetPanel(int level)
    {
        try
        {
            var done = false;
            foreach (var method in Query("SELECT * FROM WmiMonitorBrightnessMethods"))
            {
                var given = method.Methods_.Item("WmiSetBrightness")
                    .InParameters.SpawnInstance_();
                given.Properties_.Item("Timeout").Value = 0;
                given.Properties_.Item("Brightness").Value = (byte)level;
                method.ExecMethod_("WmiSetBrightness", given);
                done = true;
            }
            return done;
        }
        catch (COMException) { return false; }
        catch (Microsoft.CSharp.RuntimeBinder.RuntimeBinderException) { return false; }
    }

    /// <summary>The objects a WMI query in <c>root\WMI</c> returns.</summary>
    /// <remarks>
    /// On a desktop the classes exist and the query fails with "not
    /// supported" — that is the ordinary answer, and it surfaces as a
    /// <see cref="COMException"/> the callers turn into "no panel".
    /// </remarks>
    private static IEnumerable<dynamic> Query(string wql)
    {
        var type = Type.GetTypeFromProgID("WbemScripting.SWbemLocator");
        if (type is null) yield break;
        dynamic locator = Activator.CreateInstance(type)!;
        dynamic services = locator.ConnectServer(".", @"root\WMI");
        foreach (var item in services.ExecQuery(wql))
            yield return item;
    }

    // --- external monitors: DDC/CI ---------------------------------------------------
    private delegate bool OnMonitor(IntPtr handle, uint min, uint now, uint max);

    /// <summary>
    /// Call <paramref name="act"/> for every monitor that reports its
    /// brightness over DDC/CI. Returns how many it succeeded on.
    /// </summary>
    /// <remarks>
    /// A monitor that does not answer <c>GetMonitorBrightness</c> is
    /// skipped rather than tried: it either lacks DDC/CI or has it switched
    /// off, and setting a value it cannot report would be setting it blind.
    /// The physical handles are released every time — they are a resource
    /// of the driver, not of this process.
    /// </remarks>
    private static int ForEachMonitor(OnMonitor act)
    {
        var done = 0;
        var screens = new List<IntPtr>();
        EnumDisplayMonitors(IntPtr.Zero, IntPtr.Zero,
            (screen, _, _, _) => { screens.Add(screen); return true; },
            IntPtr.Zero);
        foreach (var screen in screens)
        {
            if (!GetNumberOfPhysicalMonitorsFromHMONITOR(screen, out var count)
                || count == 0)
                continue;
            var physical = new PhysicalMonitor[count];
            if (!GetPhysicalMonitorsFromHMONITOR(screen, count, physical))
                continue;
            try
            {
                foreach (var one in physical)
                    if (GetMonitorBrightness(one.Handle, out var min,
                                             out var now, out var max)
                        && act(one.Handle, min, now, max))
                        done++;
            }
            finally
            {
                DestroyPhysicalMonitors(count, physical);
            }
        }
        return done;
    }

    private delegate bool MonitorEnum(IntPtr screen, IntPtr dc, IntPtr rect,
                                      IntPtr data);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct PhysicalMonitor
    {
        public IntPtr Handle;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 128)]
        public string Description;
    }

    [DllImport("user32.dll")]
    private static extern bool EnumDisplayMonitors(IntPtr dc, IntPtr clip,
                                                   MonitorEnum callback,
                                                   IntPtr data);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool GetNumberOfPhysicalMonitorsFromHMONITOR(
        IntPtr screen, out uint count);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool GetPhysicalMonitorsFromHMONITOR(
        IntPtr screen, uint count, [Out] PhysicalMonitor[] monitors);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool DestroyPhysicalMonitors(
        uint count, PhysicalMonitor[] monitors);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool GetMonitorBrightness(IntPtr monitor,
                                                    out uint min,
                                                    out uint now,
                                                    out uint max);

    [DllImport("dxva2.dll", SetLastError = true)]
    private static extern bool SetMonitorBrightness(IntPtr monitor,
                                                    uint level);
}
