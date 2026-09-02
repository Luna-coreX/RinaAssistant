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
    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        var args = e.Args;
        var finish = Value(args, "--finish") ?? "silver";
        ApplyFinish(finish);

        var window = new MainWindow();
        var shot = Value(args, "--shot");
        if (shot is null)
        {
            window.Show();
            return;
        }

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
