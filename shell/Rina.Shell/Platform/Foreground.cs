using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;

namespace Rina.Shell.Platform;

/// <summary>
/// Watching which program is in front of the person right now.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0b-A03</c>. The decision is
/// [ADR 0009](../../../docs/adr/0009-system-layer.md): the shell touches
/// the machine. This is a new capability and, unlike the rest of the
/// system layer, <b>a new privacy surface</b> — see <c>T-19</c> in
/// [the threat model](../../../docs/security/THREAT-MODEL.md).
/// </para>
/// <para>
/// <b>Off until switched on.</b> The watch does not start with the
/// application; it starts when the person turns <c>watch_apps</c> on, and
/// stops when they turn it off. Knowing which programs somebody opens is
/// information of the same kind as the text of their words, and it is not
/// collected by default.
/// </para>
/// <para>
/// <b>What leaves here is a path, and only when it changes.</b> Not the
/// window title — a person changes that themselves by opening somebody
/// else's file in an editor, so sending it would mean sending the name of
/// a document they are reading. Not a stream of events either: Windows
/// reports the foreground window on every switch, including back and
/// forth between two windows, and the core has nothing to do with the
/// repeats.
/// </para>
/// <para>
/// <b>Nothing is remembered here.</b> Only the previous path, and only to
/// tell a repeat from a change. There is no history, no timing, no count
/// of switches — because a history that does not exist cannot leak.
/// </para>
/// </remarks>
public sealed class Foreground : IDisposable
{
    /// <summary>The foreground window changed.</summary>
    private const uint EventSystemForeground = 0x0003;

    /// <summary>Do not inject a DLL into the observed process, and do not
    /// deliver our own events back to us.</summary>
    private const uint WinEventOutOfContext = 0x0000;
    private const uint WinEventSkipOwnProcess = 0x0002;

    private delegate void WinEventProc(
        IntPtr hook, uint evt, IntPtr window, int obj, int child,
        uint thread, uint time);

    [DllImport("user32.dll")]
    private static extern IntPtr SetWinEventHook(
        uint min, uint max, IntPtr module, WinEventProc callback,
        uint process, uint thread, uint flags);

    [DllImport("user32.dll")]
    private static extern bool UnhookWinEvent(IntPtr hook);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(
        IntPtr window, out uint processId);

    private readonly Action<string> _report;

    // The delegate is held in a field on purpose: Windows keeps only an
    // unmanaged pointer to it, and a delegate that only the P/Invoke call
    // referenced would be collected — after which the callback lands on
    // freed memory. It does not crash at once, which is worse.
    private readonly WinEventProc _callback;

    private IntPtr _hook;
    private string _last = "";

    public Foreground(Action<string> report)
    {
        _report = report;
        _callback = OnForegroundChanged;
    }

    /// <summary>Is the watch running right now.</summary>
    public bool Watching => _hook != IntPtr.Zero;

    /// <summary>
    /// Start or stop the watch to match the setting.
    /// </summary>
    /// <remarks>
    /// One method for both, because the caller has one thing to say: what
    /// the person chose. Two methods would let a caller start a watch
    /// twice and stop it once.
    /// </remarks>
    public void Follow(bool wanted)
    {
        if (wanted == Watching) return;
        if (wanted) Start(); else Stop();
    }

    private void Start()
    {
        _hook = SetWinEventHook(
            EventSystemForeground, EventSystemForeground, IntPtr.Zero,
            _callback, 0, 0,
            WinEventOutOfContext | WinEventSkipOwnProcess);

        // The window that is already in front counts as a change: a person
        // who switches the setting on while sitting in the editor means
        // exactly that editor, and waiting for them to alt-tab away and
        // back would look like the setting did not work.
        if (Watching) Report(GetForegroundWindow());
    }

    private void Stop()
    {
        if (Watching) UnhookWinEvent(_hook);
        _hook = IntPtr.Zero;
        // The last path is forgotten along with the watch: it is the only
        // thing this class holds, and holding it while not watching would
        // mean keeping a trace of what the person was doing when they
        // switched the watch off.
        _last = "";
    }

    private void OnForegroundChanged(IntPtr hook, uint evt, IntPtr window,
                                     int obj, int child, uint thread,
                                     uint time)
    {
        Report(window);
    }

    private void Report(IntPtr window)
    {
        var path = PathOf(window);
        if (path.Length == 0 || string.Equals(path, _last,
                                              StringComparison.OrdinalIgnoreCase))
            return;
        _last = path;
        try { _report(path); }
        catch { /* the core will be told next time; a watch must not fall over a reply */ }
    }

    /// <summary>
    /// The executable behind the window, or an empty string.
    /// </summary>
    /// <remarks>
    /// The path of a process is not always readable: a system process
    /// belongs to a different session, and a 64-bit process is not
    /// readable from a 32-bit one. An empty string is the honest answer —
    /// better than a process name that matches nothing in the index and
    /// would look like a program that is not installed.
    /// </remarks>
    private static string PathOf(IntPtr window)
    {
        if (window == IntPtr.Zero) return "";
        try
        {
            GetWindowThreadProcessId(window, out var pid);
            if (pid == 0) return "";
            using var process = Process.GetProcessById((int)pid);
            return process.MainModule?.FileName ?? "";
        }
        catch
        {
            return "";
        }
    }

    public void Dispose() => Stop();
}
