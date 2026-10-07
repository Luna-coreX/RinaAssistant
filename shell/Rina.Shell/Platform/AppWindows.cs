using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;

namespace Rina.Shell.Platform;

/// <summary>
/// Other programs' windows: close, minimise, expand (<c>4.0b-K08</c>).
/// </summary>
/// <remarks>
/// <para>
/// The decision is [ADR 0009](../../../docs/adr/0009-system-layer.md): the
/// core decides which program and says what happened; the shell finds the
/// windows and touches them, and answers with a fact.
/// </para>
/// <para>
/// <b>A window is closed the way its own close button closes it</b> — the
/// window's system command <c>SC_CLOSE</c>, never a terminated process. A
/// program with unsaved work asks about it; a program that lives in the
/// tray goes there. Both are reported rather than hidden: a window still
/// on the screen a moment later is <c>left</c>, and a process still alive
/// once its windows are gone is <c>still_running</c>.
/// </para>
/// <para>
/// <b>Which windows count.</b> The ones the task switcher shows: visible,
/// not cloaked, without an owner, not tool windows — and never Rina's own,
/// nor the desktop and the taskbar. A dialog goes with the window that owns
/// it.
/// </para>
/// <para>
/// <b>What is read about a window</b> is its process — the executable's
/// path, its description, the package of a Store app — to match it against
/// the program that was named. Not its title: a title is the name of the
/// document a person has open, and nothing here needs it (<c>T-19</c>).
/// Nothing leaves but the program's name, and only the one acted on.
/// </para>
/// </remarks>
public static class AppWindows
{
    /// <summary>A program the core found in the index for the name said.</summary>
    public sealed record Candidate(string Name, string Launch, string Kind);

    /// <summary>
    /// What the core asked about: <c>active</c>, <c>all</c>, or <c>app</c>
    /// with the index's candidates and the name's spellings.
    /// </summary>
    public sealed record Target(string Which, IReadOnlyList<Candidate> Apps,
                                IReadOnlyList<string> Names);

    /// <summary>The fact that goes back to the core.</summary>
    public sealed record Outcome(bool Ok, string Reason = "",
                                 string Program = "",
                                 IReadOnlyList<string>? Programs = null,
                                 int Done = 0, int Left = 0,
                                 bool StillRunning = false,
                                 int Refused = 0);

    /// <summary>What may be asked.</summary>
    public static readonly string[] Actions =
        ["close", "minimize", "expand", "maximize", "restore"];

    /// <summary>How long a closed window is given to go.</summary>
    /// <remarks>
    /// Long enough for an ordinary program to close and for one with
    /// unsaved work to put its question on the screen — after which the
    /// window still there is asking, not closing.
    /// </remarks>
    private static readonly TimeSpan CloseWait = TimeSpan.FromSeconds(2);

    /// <summary>How long a process is given to exit after its windows.</summary>
    /// <remarks>
    /// A browser takes a moment to wind down; without this pause it would
    /// be reported as «left running in the tray» every time.
    /// </remarks>
    private static readonly TimeSpan ExitWait = TimeSpan.FromMilliseconds(1500);

    /// <summary>Window classes that are the desktop, not a program.</summary>
    private static readonly HashSet<string> ShellClasses = new(StringComparer.Ordinal)
    {
        "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
    };

    /// <summary>
    /// Parts of Windows that own windows a person never thinks of as
    /// programs: the Start menu, the search, the touch keyboard. They are
    /// cloaked while hidden; this is for the moment they are not.
    /// </summary>
    private static readonly HashSet<string> ShellProcesses = new(StringComparer.OrdinalIgnoreCase)
    {
        "ShellExperienceHost", "StartMenuExperienceHost", "SearchHost",
        "SearchApp", "TextInputHost", "LockApp",
    };

    // --- Win32 -------------------------------------------------------------

    private delegate bool EnumProc(IntPtr window, IntPtr data);

    [DllImport("user32.dll")]
    private static extern bool EnumWindows(EnumProc callback, IntPtr data);

    [DllImport("user32.dll")]
    private static extern bool IsWindow(IntPtr window);

    [DllImport("user32.dll")]
    private static extern bool IsWindowVisible(IntPtr window);

    [DllImport("user32.dll")]
    private static extern bool IsIconic(IntPtr window);

    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr window);

    [DllImport("user32.dll")]
    private static extern IntPtr GetWindow(IntPtr window, uint command);

    [DllImport("user32.dll")]
    private static extern IntPtr GetAncestor(IntPtr window, uint flags);

    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")]
    private static extern IntPtr GetWindowLongPtr(IntPtr window, int index);

    [DllImport("user32.dll")]
    private static extern int GetWindowTextLength(IntPtr window);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetClassName(IntPtr window, StringBuilder name, int size);

    [DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window, out uint processId);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after,
                                              string? className, string? title);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool PostMessage(IntPtr window, uint message,
                                           IntPtr wParam, IntPtr lParam);

    [DllImport("user32.dll")]
    private static extern bool ShowWindowAsync(IntPtr window, int command);

    [DllImport("dwmapi.dll")]
    private static extern int DwmGetWindowAttribute(IntPtr window, int attribute,
                                                    out int value, int size);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint access, bool inherit, uint id);

    [DllImport("kernel32.dll")]
    private static extern bool CloseHandle(IntPtr handle);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool QueryFullProcessImageName(IntPtr process, uint flags,
                                                         StringBuilder name, ref uint size);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern int GetPackageFamilyName(IntPtr process, ref uint length,
                                                   StringBuilder? name);

    private const uint GwOwner = 4;
    private const uint GwHwndNext = 2;
    private const uint GaRootOwner = 3;
    private const int GwlExStyle = -20;
    private const long WsExToolWindow = 0x00000080;
    private const long WsExAppWindow = 0x00040000;
    private const long WsExNoActivate = 0x08000000;
    private const int DwmwaCloaked = 14;
    private const uint WmSysCommand = 0x0112;
    private const int ScClose = 0xF060;
    private const int SwMaximize = 3;
    private const int SwShowNoActivate = 4;
    private const int SwMinimize = 6;
    private const int SwShowMinNoActive = 7;
    private const int SwRestore = 9;
    private const uint ProcessQueryLimited = 0x1000;
    private const int ErrorAccessDenied = 5;

    // --- what a window is ----------------------------------------------------

    /// <summary>The program behind a window, as far as it can be read.</summary>
    private sealed record Owner(uint Pid, string Path, string Package,
                                string Description, string Product)
    {
        /// <summary>One program, whatever window of it this is.</summary>
        public string Key => Package.Length > 0 ? Package.ToLowerInvariant()
            : Path.Length > 0 ? Path.ToLowerInvariant() : $"pid:{Pid}";

        public string ExeName => System.IO.Path.GetFileNameWithoutExtension(Path);

        /// <summary>What a person would call it.</summary>
        public string Display => Description.Length > 0 ? Description
            : Product.Length > 0 ? Product : ExeName;
    }

    // --- the entry point ---------------------------------------------------

    /// <summary>Do <paramref name="action"/> to the windows the target names.</summary>
    public static async Task<Outcome> DoAsync(string action, Target target)
    {
        if (!Actions.Contains(action)) return new Outcome(false, "unknown");
        try
        {
            return target.Which switch
            {
                "active" => await ActiveAsync(action),
                "all" => await AllAsync(action),
                "app" => await ProgramAsync(action, target),
                _ => new Outcome(false, "unknown"),
            };
        }
        catch (Exception error)
        {
            ShellLog.Error("windows.do", error);
            return new Outcome(false, "internal");
        }
    }

    private static async Task<Outcome> ActiveAsync(string action)
    {
        if (action == "restore") return new Outcome(false, "unknown");
        var window = Front();
        if (window == IntPtr.Zero) return new Outcome(false, "no_window");
        var owner = OwnerOf(window);
        return await ActAsync(action, [window], owner.Display,
                              new Dictionary<IntPtr, Owner> { [window] = owner });
    }

    private static async Task<Outcome> AllAsync(string action)
    {
        var windows = Listed();
        switch (action)
        {
            case "minimize":
            {
                var shown = windows.Where(w => !IsIconic(w)).ToList();
                // Without activation: minimising a dozen windows one after
                // another would otherwise hand the focus down the stack.
                foreach (var window in shown) ShowWindowAsync(window, SwShowMinNoActive);
                return new Outcome(true, Done: shown.Count);
            }
            case "restore":
            {
                var minimised = windows.Where(IsIconic).ToList();
                // From the bottom up, so the one that was on top ends on top.
                minimised.Reverse();
                foreach (var window in minimised) ShowWindowAsync(window, SwShowNoActivate);
                return new Outcome(true, Done: minimised.Count);
            }
            case "close":
            {
                var (done, left, _, refused) = await CloseAsync(windows, new());
                // Asking and refusing are told apart: a window of a program
                // running as administrator did not take the command at all,
                // and «it is asking something» would send the person to
                // look for a question that is not there.
                return new Outcome(true, Done: done, Left: left, Refused: refused);
            }
            default:
                return new Outcome(false, "unknown");
        }
    }

    private static async Task<Outcome> ProgramAsync(string action, Target target)
    {
        if (action == "restore") return new Outcome(false, "unknown");

        var owners = new Dictionary<IntPtr, Owner>();
        var scored = new List<(IntPtr Window, Owner Owner, int Score, string Name)>();
        var targets = target.Apps.Select(c => (Candidate: c, Exe: ExeOf(c))).ToList();
        foreach (var window in Listed())
        {
            var owner = OwnerOf(window);
            owners[window] = owner;
            var (score, name) = Match(owner, targets, target.Names);
            if (score > 0) scored.Add((window, owner, score, name));
        }
        if (scored.Count == 0) return new Outcome(false, "not_running");

        var best = scored.Max(s => s.Score);
        var programs = scored.Where(s => s.Score == best)
                             .GroupBy(s => s.Owner.Key).ToList();
        if (programs.Count > 1)
            return new Outcome(false, "ambiguous",
                Programs: programs.Select(g => g.First().Name).Distinct().ToList());

        var chosen = programs[0].ToList();
        return await ActAsync(action, chosen.Select(s => s.Window).ToList(),
                              chosen[0].Name, owners);
    }

    /// <summary>Do one thing to the windows of one program.</summary>
    private static async Task<Outcome> ActAsync(string action, List<IntPtr> windows,
                                                string program,
                                                Dictionary<IntPtr, Owner> owners)
    {
        switch (action)
        {
            case "close":
            {
                var (done, left, running, refused) = await CloseAsync(windows, owners);
                if (done == 0 && left == 0 && refused > 0)
                    return new Outcome(false, "refused", program);
                return new Outcome(true, "", program, Done: done, Left: left,
                                   StillRunning: running);
            }
            case "minimize":
                foreach (var window in windows) ShowWindowAsync(window, SwMinimize);
                return new Outcome(true, "", program, Done: windows.Count);
            case "expand":
            case "maximize":
                foreach (var window in windows)
                {
                    // «Развернуть» a minimised window brings it back as it
                    // was; one already on the screen is expanded to the
                    // full screen, as the window's own button would.
                    var command = action == "expand" && IsIconic(window)
                        ? SwRestore : SwMaximize;
                    ShowWindowAsync(window, command);
                }
                // Best effort: Windows lets a background process bring a
                // window forward only in some circumstances. The window is
                // expanded either way.
                SetForegroundWindow(windows[0]);
                return new Outcome(true, "", program, Done: windows.Count);
            default:
                return new Outcome(false, "unknown");
        }
    }

    /// <summary>
    /// Close the windows as by their close button and see what became of
    /// them: (closed, still there, a process left running, refused).
    /// </summary>
    private static async Task<(int Done, int Left, bool Running, int Refused)>
        CloseAsync(IReadOnlyList<IntPtr> windows, Dictionary<IntPtr, Owner> owners)
    {
        var sent = new List<IntPtr>();
        var refused = 0;
        foreach (var window in windows)
        {
            if (PostMessage(window, WmSysCommand, (IntPtr)ScClose, IntPtr.Zero))
                sent.Add(window);
            // A program running as administrator does not take messages
            // from one that is not (UIPI). That is a refusal, not a fault.
            else if (Marshal.GetLastWin32Error() == ErrorAccessDenied)
                refused++;
        }

        var deadline = DateTime.UtcNow + CloseWait;
        while (DateTime.UtcNow < deadline && sent.Any(Shown))
            await Task.Delay(100);

        var left = sent.Count(Shown);
        var done = sent.Count - left;

        // The windows that went: did their programs go with them?
        var gone = sent.Where(w => !Shown(w) && owners.ContainsKey(w))
                       .Select(w => owners[w].Pid).Distinct().ToList();
        var running = false;
        if (gone.Count > 0)
        {
            var exitBy = DateTime.UtcNow + ExitWait;
            while (DateTime.UtcNow < exitBy && (running = gone.Any(Alive)))
                await Task.Delay(100);
        }
        return (done, left, running, refused);
    }

    // --- which windows -----------------------------------------------------

    /// <summary>The windows a person would call windows, top first.</summary>
    private static List<IntPtr> Listed()
    {
        var found = new List<IntPtr>();
        var own = (uint)Environment.ProcessId;
        EnumWindows((window, _) =>
        {
            if (Counts(window, own)) found.Add(window);
            return true;
        }, IntPtr.Zero);
        return found;
    }

    /// <summary>
    /// The window the person is working in — or, when that is Rina's
    /// own, the one right under her: a command typed into Rina is about
    /// the window she was opened over.
    /// </summary>
    private static IntPtr Front()
    {
        var own = (uint)Environment.ProcessId;
        var front = GetForegroundWindow();
        if (front == IntPtr.Zero) return IntPtr.Zero;
        var root = GetAncestor(front, GaRootOwner);
        if (root != IntPtr.Zero) front = root;

        GetWindowThreadProcessId(front, out var pid);
        if (pid != own) return Counts(front, own) ? front : IntPtr.Zero;

        for (var next = GetWindow(front, GwHwndNext); next != IntPtr.Zero;
             next = GetWindow(next, GwHwndNext))
        {
            if (Counts(next, own) && !IsIconic(next)) return next;
        }
        return IntPtr.Zero;
    }

    private static bool Counts(IntPtr window, uint own)
    {
        if (!IsWindowVisible(window) || Cloaked(window)) return false;
        if (GetWindow(window, GwOwner) != IntPtr.Zero) return false;
        var style = GetWindowLongPtr(window, GwlExStyle).ToInt64();
        if ((style & WsExToolWindow) != 0 && (style & WsExAppWindow) == 0) return false;
        if ((style & WsExNoActivate) != 0) return false;
        if (GetWindowTextLength(window) == 0) return false;
        if (ShellClasses.Contains(ClassOf(window))) return false;
        GetWindowThreadProcessId(window, out var pid);
        if (pid == own || pid == 0) return false;
        try
        {
            using var process = Process.GetProcessById((int)pid);
            if (ShellProcesses.Contains(process.ProcessName)) return false;
        }
        catch { return false; }
        return true;
    }

    /// <summary>On the screen: it exists, it is visible and not cloaked.</summary>
    private static bool Shown(IntPtr window) =>
        IsWindow(window) && IsWindowVisible(window) && !Cloaked(window);

    private static bool Cloaked(IntPtr window) =>
        DwmGetWindowAttribute(window, DwmwaCloaked, out var cloaked, sizeof(int)) == 0
        && cloaked != 0;

    private static string ClassOf(IntPtr window)
    {
        var name = new StringBuilder(256);
        return GetClassName(window, name, name.Capacity) > 0 ? name.ToString() : "";
    }

    private static bool Alive(uint pid)
    {
        try
        {
            using var process = Process.GetProcessById((int)pid);
            return !process.HasExited;
        }
        catch { return false; }
    }

    // --- whose window ------------------------------------------------------

    /// <summary>
    /// The program behind a window. A Store app's window belongs to the
    /// frame host, and the app is the process of the content inside it.
    /// </summary>
    private static Owner OwnerOf(IntPtr window)
    {
        var source = window;
        if (ClassOf(window) == "ApplicationFrameWindow")
        {
            var content = FindWindowEx(window, IntPtr.Zero,
                                       "Windows.UI.Core.CoreWindow", null);
            if (content != IntPtr.Zero) source = content;
        }
        GetWindowThreadProcessId(source, out var pid);
        var (path, package) = Read(pid);
        string description = "", product = "";
        if (path.Length > 0)
        {
            try
            {
                var info = FileVersionInfo.GetVersionInfo(path);
                description = (info.FileDescription ?? "").Trim();
                product = (info.ProductName ?? "").Trim();
            }
            catch { /* a file that cannot be read has no description */ }
        }
        return new Owner(pid, path, package, description, product);
    }

    /// <summary>
    /// The executable's path and the package's family name, by the limited
    /// query right — the one a program running as administrator still
    /// answers to.
    /// </summary>
    private static (string Path, string Package) Read(uint pid)
    {
        var handle = OpenProcess(ProcessQueryLimited, false, pid);
        if (handle == IntPtr.Zero) return ("", "");
        try
        {
            var path = new StringBuilder(1024);
            var size = (uint)path.Capacity;
            var file = QueryFullProcessImageName(handle, 0, path, ref size)
                ? path.ToString() : "";

            uint length = 0;
            var package = "";
            // 122 is ERROR_INSUFFICIENT_BUFFER: the process is packaged.
            if (GetPackageFamilyName(handle, ref length, null) == 122 && length > 0)
            {
                var name = new StringBuilder((int)length);
                if (GetPackageFamilyName(handle, ref length, name) == 0)
                    package = name.ToString();
            }
            return (file, package);
        }
        finally
        {
            CloseHandle(handle);
        }
    }

    // --- is it the one that was named --------------------------------------

    /// <summary>
    /// How surely a window's program is the one named, and what to call it:
    /// 3 — the same executable or package as an index entry; 2 — the same
    /// name; 1 — the name with a vendor in front («Microsoft Word» for
    /// «Word») or the executable inside a longer name («telegram» in
    /// «Telegram Desktop»); 0 — another program.
    /// </summary>
    private static (int Score, string Name) Match(
        Owner owner, List<(Candidate Candidate, string Exe)> targets,
        IReadOnlyList<string> names)
    {
        var best = (Score: 0, Name: "");
        foreach (var (candidate, exe) in targets)
        {
            var score = 0;
            if (candidate.Kind == "uwp")
            {
                var family = candidate.Launch.Split('!')[0];
                if (owner.Package.Length > 0
                    && string.Equals(family, owner.Package, StringComparison.OrdinalIgnoreCase))
                    score = 3;
            }
            else if (exe.Length > 0 && owner.Path.Length > 0
                     && string.Equals(exe, owner.Path, StringComparison.OrdinalIgnoreCase))
            {
                score = 3;
            }
            if (score == 0) score = ByName(owner, candidate.Name);
            if (score > best.Score) best = (score, candidate.Name);
        }
        foreach (var name in names)
        {
            var score = ByName(owner, name);
            if (score > best.Score) best = (score, owner.Display);
        }
        return best;
    }

    private static int ByName(Owner owner, string name)
    {
        var wanted = Words(name);
        if (wanted.Count == 0) return 0;
        var exe = Words(owner.ExeName);
        var labels = new[] { Words(owner.Description), Words(owner.Product), exe };
        if (labels.Any(l => l.Count > 0 && l.SequenceEqual(wanted))) return 2;
        foreach (var label in labels.Take(2))
        {
            if (label.Count > wanted.Count && label.TakeLast(wanted.Count).SequenceEqual(wanted))
                return 1;
        }
        if (exe.Count > 0 && exe.All(w => w.Length >= 3 && wanted.Contains(w))) return 1;
        return 0;
    }

    private static List<string> Words(string text) =>
        new string(text.ToLowerInvariant()
                       .Select(c => char.IsLetterOrDigit(c) ? c : ' ').ToArray())
            .Split(' ', StringSplitOptions.RemoveEmptyEntries).ToList();

    /// <summary>
    /// The executable an index entry starts: the path itself, or what a
    /// Start-menu shortcut points at. Empty when that cannot be read — the
    /// entry is then matched by its name.
    /// </summary>
    private static string ExeOf(Candidate candidate)
    {
        if (candidate.Kind != "file") return "";
        var launch = candidate.Launch;
        if (launch.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)) return launch;
        if (!launch.EndsWith(".lnk", StringComparison.OrdinalIgnoreCase)) return "";
        // The same reading the launch checks use (`Shortcut`), rather than a
        // second one through the scripting host.
        return Shortcut.Read(launch)?.Path ?? "";
    }
}
