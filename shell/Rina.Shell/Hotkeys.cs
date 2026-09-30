using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Input;
using System.Windows.Interop;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell;

/// <summary>
/// Global hotkeys.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-F06</c>.
/// </para>
/// <para>
/// <b>Handling happens as early as possible, and this is an architectural
/// requirement rather than fussing over speed.</b> In 5.0 the kill switch
/// goes here — a hotkey that instantly revokes every permission and cuts
/// off control of the computer (<c>5.0-D08</c>). It cannot wait in a
/// queue: if it ends up behind the window's message handling, behind a
/// busy core or behind anything else at all, it will fire when it is
/// already too late.
/// </para>
/// <para>
/// So the message is intercepted at the very start of the window
/// procedure, before any logic, and the handler is called straight from
/// there. Everything it does is obliged to be fast; anything long is moved
/// to another thread by the handler itself.
/// </para>
/// <para>
/// <b>Registration with the system, not keyboard interception.</b>
/// `RegisterHotKey` asks the system to send a message and does not see the
/// other keypresses. A global keyboard hook would see everything a person
/// types — for a program whose settings offer "do not record the text of
/// lines", that would be a contradiction of itself.
/// </para>
/// </remarks>
public sealed class Hotkeys : IDisposable
{
    private const int WmHotkey = 0x0312;

    /// <summary>Modifiers in the form the system expects them.</summary>
    [Flags]
    public enum Mod
    {
        Alt = 0x0001,
        Control = 0x0002,
        Shift = 0x0004,
        Win = 0x0008,
        NoRepeat = 0x4000,
    }

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool RegisterHotKey(IntPtr window, int id,
                                              uint modifiers, uint key);

    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool UnregisterHotKey(IntPtr window, int id);

    private readonly Dictionary<int, Action> _bound = [];
    private readonly Dictionary<string, int> _byName = [];
    private HwndSource? _source;
    private IntPtr _handle;
    private int _next = 1;

    /// <summary>A hotkey could not be registered: another program holds it.</summary>
    public event Action<string, string>? Refused;

    public void Attach(Window window)
    {
        _handle = new WindowInteropHelper(window).EnsureHandle();
        _source = HwndSource.FromHwnd(_handle);
        _source?.AddHook(OnMessage);
    }

    private IntPtr OnMessage(IntPtr hwnd, int message, IntPtr wParam,
                             IntPtr lParam, ref bool handled)
    {
        // Before everything else. No parsing and no dictionary lookup
        // beyond a single one: this is where the kill switch's path begins.
        if (message != WmHotkey) return IntPtr.Zero;
        if (_bound.TryGetValue(wParam.ToInt32(), out var act))
        {
            handled = true;
            act();
        }
        return IntPtr.Zero;
    }

    /// <summary>
    /// Register a hotkey. `false` means it did not work, and that is not an
    /// exception.
    /// </summary>
    /// <remarks>
    /// A hotkey held by another program is an ordinary matter, not a
    /// failure: a person may have anything installed. They must find out
    /// about it and choose another one rather than guess why it does not
    /// work.
    /// </remarks>
    public bool Bind(string name, string combination, Action action)
    {
        Unbind(name);
        if (!TryParse(combination, out var modifiers, out var key))
        {
            Refused?.Invoke(name, S("не разобрал сочетание «{0}»", combination));
            return false;
        }

        var id = _next++;
        if (!RegisterHotKey(_handle, id, (uint)(modifiers | Mod.NoRepeat), key))
        {
            Refused?.Invoke(name, S("«{0}» занято другой программой", combination));
            return false;
        }
        _bound[id] = action;
        _byName[name] = id;
        return true;
    }

    public void Unbind(string name)
    {
        if (!_byName.TryGetValue(name, out var id)) return;
        UnregisterHotKey(_handle, id);
        _bound.Remove(id);
        _byName.Remove(name);
    }

    /// <summary>How many hotkeys are registered right now.</summary>
    public int Count => _bound.Count;

    /// <summary>
    /// "Ctrl+Shift+R" → modifiers and a key code.
    /// </summary>
    /// <remarks>
    /// The notation is the same as in 3.1.0: settings carry over as they
    /// are, and making a person retype seven hotkeys for the sake of a new
    /// format would be a loss with no gain.
    /// </remarks>
    public static bool TryParse(string combination, out Mod modifiers,
                                out uint key)
    {
        modifiers = 0;
        key = 0;
        if (string.IsNullOrWhiteSpace(combination)) return false;

        foreach (var part in combination.Split('+',
                     StringSplitOptions.RemoveEmptyEntries
                     | StringSplitOptions.TrimEntries))
        {
            switch (part.ToLowerInvariant())
            {
                case "ctrl" or "control": modifiers |= Mod.Control; break;
                case "shift": modifiers |= Mod.Shift; break;
                case "alt": modifiers |= Mod.Alt; break;
                case "win": modifiers |= Mod.Win; break;
                default:
                    if (!Enum.TryParse<Key>(part, true, out var parsed))
                        return false;
                    key = (uint)KeyInterop.VirtualKeyFromKey(parsed);
                    break;
            }
        }
        // A hotkey without a modifier would take the key over the whole
        // system: a person would press "R" in someone else's editor and
        // summon Rina.
        return key != 0 && modifiers != 0;
    }

    public void Dispose()
    {
        foreach (var id in _bound.Keys.ToArray()) UnregisterHotKey(_handle, id);
        _bound.Clear();
        _byName.Clear();
        _source?.RemoveHook(OnMessage);
        _source = null;
    }
}
