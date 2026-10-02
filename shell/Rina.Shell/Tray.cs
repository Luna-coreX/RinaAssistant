using System.Drawing;
using System.Windows;
using H.NotifyIcon.Core;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell;

/// <summary>
/// The tray icon: the window can be closed without switching Rina off.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-F05</c>.
/// </para>
/// <para>
/// <b>Why this exists at all.</b> A voice assistant that lives only while
/// a window is open is not an assistant but a program. A reminder set by
/// voice is obliged to go off with the window closed (<c>4.0-E05</c>), and
/// the hotkey is obliged to work from there too (<c>4.0-F06</c>). The tray
/// is the place where a program stays without taking up the screen.
/// </para>
/// <para>
/// <b>The close button minimises rather than switches off</b> — but only
/// if a setting says so. A program that does not close on the close button
/// against expectation is taken for a broken one; so the behaviour is
/// chosen by the person, and by default it is the same as in 3.1.0.
/// </para>
/// <para>
/// <b>The icon is Rina's sphere</b> (<c>4.0b-D06</c>), the same file as
/// the program's own icon, so the tray, the taskbar and the shortcut show
/// one mark. It used to be an accent dot drawn here, to avoid keeping a
/// file in several sizes; the file now exists for the program anyway, and
/// a frame of the size the screen's scaling asks for is taken from it. The
/// dot stays as the fallback for a resource that cannot be read.
/// </para>
/// </remarks>
public sealed class Tray : IDisposable
{
    private readonly TrayIconWithContextMenu _icon;
    private readonly Window _window;
    private Icon? _drawn;

    /// <summary>
    /// Whether the icon was created.
    /// </summary>
    /// <remarks>
    /// Asking is obligatory: with no icon the window must not be hidden —
    /// there would be nothing to bring it back with, and the program would
    /// become unreachable while staying alive. Of two unpleasantnesses,
    /// "the close button closed it although we asked to minimise" is better
    /// than "the program vanished".
    /// </remarks>
    public bool Created { get; private set; }

    /// <summary>The person asked to quit for good.</summary>
    public event Action? ExitRequested;

    public Tray(Window window, string title = "Rina Assistant")
    {
        _window = window;
        _drawn = Load() ?? Draw();
        _icon = new TrayIconWithContextMenu
        {
            Icon = _drawn.Handle,
            ToolTip = title,
            ContextMenu = new PopupMenu
            {
                Items =
                {
                    new PopupMenuItem(S("Показать"), (_, _) => Show()),
                    new PopupMenuSeparator(),
                    new PopupMenuItem(S("Выйти"), (_, _) => ExitRequested?.Invoke()),
                },
            },
        };
        _icon.MessageWindow.MouseEventReceived += (_, e) =>
        {
            if (e.MouseEvent == MouseEvent.IconLeftMouseUp) Show();
        };
        // The icon's window is created explicitly, and without this line
        // there was no icon at all. The icon's `Create()` adds an entry to
        // the notification area, but the window the system sends clicks to
        // stays uncreated — the handle is zero and the clicks go nowhere.
        // From the outside this looks like "the tray does not work", and
        // from the inside as if everything had been done.
        _icon.MessageWindow.Create();
        _icon.Create();
        Created = _icon.MessageWindow.IsCreated;
    }

    /// <summary>The program's icon file, as the shell's resource.</summary>
    public static readonly Uri IconUri = new("pack://application:,,,/Assets/rina.ico");

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int index);

    /// <summary>The width of a small icon at the screen's scaling.</summary>
    private const int SmallIconWidth = 49;

    /// <summary>
    /// The sphere, in the frame the tray wants: 16 px at 100 %, 20 at
    /// 125 %, 24 at 150 %, 32 at 200 %. Null when the resource cannot be
    /// read — then the dot is drawn.
    /// </summary>
    private static Icon? Load()
    {
        try
        {
            var side = GetSystemMetrics(SmallIconWidth);
            if (side <= 0) side = 16;
            var resource = Application.GetResourceStream(IconUri);
            if (resource is null) return null;
            using var stream = resource.Stream;
            return new Icon(stream, new System.Drawing.Size(side, side));
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// The fallback icon: an accent dot on dark.
    /// </summary>
    /// <remarks>
    /// The colour is taken from the resources — the same tokens as
    /// everything else. A second source of truth about the brand colour
    /// would part company with the first.
    /// </remarks>
    private static Icon Draw()
    {
        var accent = System.Drawing.Color.FromArgb(232, 99, 31);
        if (Application.Current?.TryFindResource("Color.Signal")
            is System.Windows.Media.Color colour)
            accent = System.Drawing.Color.FromArgb(colour.R, colour.G, colour.B);

        using var bitmap = new Bitmap(32, 32);
        using (var canvas = Graphics.FromImage(bitmap))
        {
            canvas.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            canvas.Clear(System.Drawing.Color.Transparent);
            using var brush = new SolidBrush(accent);
            canvas.FillEllipse(brush, 8, 8, 16, 16);
        }
        return Icon.FromHandle(bitmap.GetHicon());
    }

    /// <summary>The window the system sends icon clicks to.</summary>
    /// <remarks>
    /// Exposed for the check's sake: an icon is first of all a window, and
    /// what matters is which thread pumps its message queue.
    /// </remarks>
    public IntPtr MessageWindowHandle => _icon.MessageWindow.Handle;

    public void Show()
    {
        _window.Show();
        if (_window.WindowState == WindowState.Minimized)
            _window.WindowState = WindowState.Normal;
        _window.Activate();
    }

    public void Hide() => _window.Hide();

    /// <summary>
    /// Tell the person what they cannot see.
    /// </summary>
    /// <remarks>
    /// A notification is shown only when the window is not in view: a
    /// pop-up about something already written in an open window is noise,
    /// and a person learns not to read it. The `notifications` setting
    /// outranks this: switched off means do not show it at all.
    /// </remarks>
    public void Notify(string title, string message)
    {
        if (!Created) return;
        try
        {
            _icon.ShowNotification(title, message);
        }
        catch
        {
            // Windows is within its rights not to show it: quiet hours,
            // policy, a full queue. That is no reason to fall over — a
            // notification is not an obligation.
        }
    }

    public void Dispose()
    {
        _icon.Dispose();
        _drawn?.Dispose();
        _drawn = null;
    }
}
