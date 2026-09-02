using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace Rina.Shell;

public partial class App
{
    /// <summary>
    /// Разбор аргументов и запуск.
    /// </summary>
    /// <remarks>
    /// <c>--shot &lt;файл&gt;</c> рисует окно в PNG и выходит. Это не отладочная
    /// прихоть: интерфейс, который никто не видел, проверен не был, а гонять
    /// человека смотреть на окно после каждой правки — способ перестать
    /// смотреть вовсе. Снимок делает тот же код, что рисует настоящее окно.
    /// </remarks>
    private CoreLink? _link;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        var args = e.Args;
        var finish = Value(args, "--finish") ?? "silver";
        ApplyFinish(finish);

        var window = new MainWindow();
        window.ShowFinish(finish);

        // Сквозная самопроверка: поднять настоящее ядро, дождаться связи,
        // сказать, что получилось, и выйти. Снимок показывает, как окно
        // выглядит; это показывает, что оно живое.
        if (args.Contains("--check-core"))
        {
            // Без окна WPF завершается сам, едва OnStartup вернёт управление:
            // по умолчанию приложение живёт, пока живо хотя бы одно окно.
            // Самопроверке окно показывать незачем, поэтому закрываемся мы
            // сами и только когда закончим.
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckCoreAsync(window);
            return;
        }

        var shot = Value(args, "--shot");
        if (shot is null)
        {
            // Ядро поднимается после того, как окно показано, а не до:
            // человек должен увидеть программу сразу, а не через секунду,
            // которую тратит чужой процесс на запуск. Состояние связи он
            // при этом видит с первой же отрисовки (4.0-F12).
            window.Show();
            _link = new CoreLink(window, CoreLink.FindCore());
            window.Link = _link;
            _ = _link.StartAsync();
            return;
        }

        // Снимок может изображать состояние связи: проверять индикацию,
        // дожидаясь настоящего обрыва, — способ проверять её редко.
        if (Value(args, "--core-state") is { } state)
            window.ShowCoreState(Enum.Parse<Rina.Protocol.CoreState>(state, true),
                                 Value(args, "--core-reason") ?? "");

        window.Width = 940;
        window.Height = 620;
        window.WindowStartupLocation = WindowStartupLocation.Manual;
        window.Left = -4000;              // рисуем за краем: снимок нужен,
        window.Top = -4000;               // мелькание окна — нет
        window.Show();
        Dispatcher.BeginInvoke(new Action(() =>
        {
            Save(window, shot);
            Shutdown();
        }), System.Windows.Threading.DispatcherPriority.ContextIdle);
    }

    private async Task CheckCoreAsync(MainWindow window)
    {
        // Вывод в файл буферизуется блоками, и если процесс убьют по сроку,
        // буфер пропадёт вместе с ответом на вопрос «почему так долго».
        Console.SetOut(new StreamWriter(Console.OpenStandardOutput())
        {
            AutoFlush = true,
        });

        var fails = 0;
        void Check(string label, bool ok, string detail = "")
        {
            if (!ok) fails++;
            Console.WriteLine($"  {(ok ? "OK  " : "FAIL")}  {label} {detail}");
        }

        Console.WriteLine("=== F07/F12: оболочка поднимает ядро и спрашивает вид ===");
        var link = new CoreLink(window, CoreLink.FindCore());
        window.Link = link;
        var seen = new List<Rina.Protocol.CoreState>();
        window.CoreStateShown += state => seen.Add(state);

        await link.StartAsync();
        for (var i = 0; i < 400 && link.State != Rina.Protocol.CoreState.Ready; i++)
            await Task.Delay(100);

        Check("ядро на связи", link.State == Rina.Protocol.CoreState.Ready,
              $"| {link.State}");
        Check("состояние доехало до окна", seen.Count > 0,
              "| " + string.Join(" → ", seen));
        Check("окно показывает связь словами",
              window.CoreStateTextValue.Contains("ядро"),
              $"| «{window.CoreStateTextValue}»");

        // Отделку оболочка не читает из файла, а спрашивает у ядра.
        await Task.Delay(1500);
        Check("отделка получена от ядра",
              window.FinishValue is "silver" or "black",
              $"| {window.FinishValue}");

        await link.DisposeAsync();
        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        // Ядро завершается само, увидев обрыв (§13), но попрощаться вежливо
        // дешевле, чем полагаться на это: у него есть что закрыть.
        _link?.DisposeAsync().AsTask().Wait(TimeSpan.FromSeconds(6));
        base.OnExit(e);
    }

    private static string? Value(string[] args, string name)
    {
        var at = Array.IndexOf(args, name);
        return at >= 0 && at + 1 < args.Length ? args[at + 1] : null;
    }

    private static void Save(Window window, string path)
    {
        var source = PresentationSource.FromVisual(window);
        var dpi = source?.CompositionTarget?.TransformToDevice.M11 ?? 1.0;
        var width = (int)(window.ActualWidth * dpi);
        var height = (int)(window.ActualHeight * dpi);

        var bitmap = new RenderTargetBitmap(width, height, 96 * dpi, 96 * dpi,
                                            PixelFormats.Pbgra32);
        bitmap.Render(window);

        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        using var file = File.Create(path);
        encoder.Save(file);
        Console.WriteLine($"снимок: {Path.GetFullPath(path)} ({width}x{height})");
    }
}
