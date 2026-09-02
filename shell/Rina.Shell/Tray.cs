using System.Drawing;
using System.Windows;
using H.NotifyIcon.Core;

namespace Rina.Shell;

/// <summary>
/// Значок в трее: окно можно закрыть, не выключив Рину.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-F05</c>.
/// </para>
/// <para>
/// <b>Зачем это вообще.</b> Голосовой помощник, живущий только пока открыто
/// окно, — не помощник, а программа. Напоминание, поставленное голосом,
/// обязано сработать при закрытом окне (<c>4.0-E05</c>), и хоткей обязан
/// работать оттуда же (<c>4.0-F06</c>). Трей — то место, где программа
/// остаётся, не занимая экрана.
/// </para>
/// <para>
/// <b>Крестик сворачивает, а не выключает</b> — но только если так велено
/// настройкой. Программа, которая не закрывается по крестику вопреки
/// ожиданию, воспринимается как сломанная; поэтому поведение выбирает
/// человек, а по умолчанию оно то же, что в 3.1.0.
/// </para>
/// <para>
/// <b>Значок рисуется, а не берётся из файла.</b> Ресурс-иконку пришлось бы
/// держать в четырёх размерах ради разных плотностей экрана, а здесь нужен
/// один знак: точка цвета акцента на тёмном. Единственный фирменный знак
/// живёт в подвале колонки (<c>4.0-R09</c>), и тащить его в трей значило бы
/// заводить второй.
/// </para>
/// </remarks>
public sealed class Tray : IDisposable
{
    private readonly TrayIconWithContextMenu _icon;
    private readonly Window _window;
    private Icon? _drawn;

    /// <summary>
    /// Получилось ли завести значок.
    /// </summary>
    /// <remarks>
    /// Спрашивать обязательно: если значка нет, прятать окно нельзя —
    /// вернуть его будет нечем, и программа станет недостижимой, оставаясь
    /// живой. Из двух неприятностей «крестик закрыл, хотя просили свернуть»
    /// лучше, чем «программа исчезла».
    /// </remarks>
    public bool Created { get; private set; }

    /// <summary>Человек попросил выйти совсем.</summary>
    public event Action? ExitRequested;

    public Tray(Window window, string title = "Rina Assistant")
    {
        _window = window;
        _drawn = Draw();
        _icon = new TrayIconWithContextMenu
        {
            Icon = _drawn.Handle,
            ToolTip = title,
            ContextMenu = new PopupMenu
            {
                Items =
                {
                    new PopupMenuItem("Показать", (_, _) => Show()),
                    new PopupMenuSeparator(),
                    new PopupMenuItem("Выйти", (_, _) => ExitRequested?.Invoke()),
                },
            },
        };
        _icon.MessageWindow.MouseEventReceived += (_, e) =>
        {
            if (e.MouseEvent == MouseEvent.IconLeftMouseUp) Show();
        };
        // Окно значка создаётся явно, и без этой строки значка не было
        // вовсе. `Create()` у значка заводит запись в области уведомлений,
        // но окно, которому система шлёт нажатия, остаётся несозданным —
        // дескриптор нулевой, нажатия уходят в никуда. Снаружи это выглядит
        // как «трей не работает», а изнутри — как будто всё сделано.
        _icon.MessageWindow.Create();
        _icon.Create();
        Created = _icon.MessageWindow.IsCreated;
    }

    /// <summary>
    /// Значок: точка акцента на тёмном.
    /// </summary>
    /// <remarks>
    /// Цвет берётся из ресурсов — тех же токенов, что и всё остальное.
    /// Второй источник правды о фирменном цвете разошёлся бы с первым.
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

    /// <summary>Окно, которому система шлёт нажатия по значку.</summary>
    /// <remarks>
    /// Наружу — ради проверки: значок это прежде всего окно, и важно, на
    /// каком потоке оно качает свою очередь сообщений.
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

    public void Dispose()
    {
        _icon.Dispose();
        _drawn?.Dispose();
        _drawn = null;
    }
}
