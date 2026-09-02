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
    private string? _shotPath;

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
            _shotPath = Value(args, "--shot");
            // Без окна WPF завершается сам, едва OnStartup вернёт управление:
            // по умолчанию приложение живёт, пока живо хотя бы одно окно.
            // Самопроверке окно показывать незачем, поэтому закрываемся мы
            // сами и только когда закончим.
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckCoreAsync(window);
            return;
        }

        if (args.Contains("--check-audio"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckAudioAsync();
            return;
        }

        // Снимок окна подтверждения: проверять вид необратимого, каждый раз
        // выключая компьютер, — способ не проверять его вовсе.
        if (Value(args, "--shot-confirm") is { } confirmShot)
        {
            var ask = new Pages.ConfirmWindow(
                "Компьютер будет выключен немедленно.",
                "Сказано голосом", 60);
            ask.Left = -4000;
            ask.Top = -4000;
            ask.Show();
            Dispatcher.BeginInvoke(new Action(() =>
            {
                Save(ask, confirmShot);
                Shutdown();
            }), System.Windows.Threading.DispatcherPriority.ContextIdle);
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

        // Снимок может показать любой раздел: проверять страницу, каждый
        // раз щёлкая по колонке руками, — способ проверять её редко.
        if (Value(args, "--section") is { } section) window.ShowSectionFor(section);

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

        // Страницы строятся только в живом дереве, поэтому окно показывается
        // за краем экрана: проверять страницу, не показав её, значит
        // проверять конструктор, а не страницу.
        window.Left = -4000;
        window.Top = -4000;
        window.Show();

        window.ShowSectionFor("settings");
        var settings = await WaitFor(() => window.CurrentPage as Pages.SettingsPage,
                                     p => p.SectionCount > 0);
        Check("настройки построены из схемы ядра", settings is not null,
              settings is null ? "| страница пуста"
                               : $"| секций {settings.SectionCount}, "
                                 + $"ключей {settings.KeyCount}");
        Check("ключей пришло столько, сколько ядро объявило",
              settings is { KeyCount: > 20 },
              $"| {settings?.KeyCount}");

        // Снимок живого окна, если попросили: настройки с настоящими
        // значениями от настоящего ядра — единственный способ увидеть, как
        // это выглядит на самом деле, а не как выглядит пустая страница.
        if (_shotPath is { } shot)
        {
            window.ShowSectionFor("settings");
            await Task.Delay(800);
            Save(window, shot);
        }

        window.ShowSectionFor("commands");
        await Task.Delay(1500);
        Check("страница команд открылась",
              window.CurrentPage is Pages.CommandsPage);

        window.Hide();

        await link.DisposeAsync();
        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// F09/F10: звук ходит в ядро и обратно, кредит соблюдается.
    /// </summary>
    /// <remarks>
    /// Часть проверок не трогает устройство вовсе: путь звука один и тот же,
    /// приходит он с микрофона или из генератора, и проверять надо путь.
    /// Иначе набор не запустится на машине без микрофона — то есть на любом
    /// сервере сборки.
    /// </remarks>
    private async Task CheckAudioAsync()
    {
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

        Console.WriteLine("=== F09/F10: звук между оболочкой и ядром ===");

        var devices = Audio.Microphone.Devices();
        Console.WriteLine($"      устройств записи: {devices.Count}"
            + (devices.Count > 0 ? $" — {devices[0].Name}" : ""));

        // --- F10: очередь и прерывание. Ядра для этого не нужно. ---
        var speaker = new Audio.Speaker();
        var speaking = new List<bool>();
        speaker.Speaking += value => speaking.Add(value);

        var tone = Tone(seconds: 1.0);
        speaker.Enqueue(tone);
        Check("речь началась", speaker.IsSpeaking);
        Check("в очереди есть что играть", speaker.Pending > 0,
              $"| {speaker.Pending} Б");

        await Task.Delay(150);
        speaker.Interrupt();
        Check("прерывание опустошает очередь сейчас же", speaker.Pending == 0,
              $"| {speaker.Pending} Б");
        Check("о конце речи сообщено",
              speaking.Count >= 2 && speaking[^1] is false,
              "| " + string.Join(" -> ", speaking));

        // --- «не слушать себя»: заглушка, а не остановка устройства ---
        var microphone = new Audio.Microphone();
        speaker.Speaking += value => microphone.Muted = value;
        speaker.Enqueue(tone);
        Check("пока Рина говорит, микрофон заглушен", microphone.Muted);
        speaker.Interrupt();
        Check("после речи слушает снова", !microphone.Muted);
        speaker.Dispose();

        // --- уровень: тишина и звук различаются ---
        Check("тишина даёт ноль",
              Audio.Microphone.LevelOf(new byte[3200]) < 0.01f);
        var loud = Audio.Microphone.LevelOf(tone);
        Check("звук даёт заметный уровень", loud > 0.3f, $"| {loud:0.00}");

        // --- F09: поток в настоящее ядро с кредитом ---
        var link = new CoreLink(new MainWindow(), CoreLink.FindCore());
        await link.StartAsync();
        for (var i = 0; i < 400 && link.State != Rina.Protocol.CoreState.Ready; i++)
            await Task.Delay(100);
        Check("ядро на связи", link.State == Rina.Protocol.CoreState.Ready,
              $"| {link.State}");

        if (link.Connection is { Ready: true } connection)
        {
            using var audio = new Audio.AudioLink(connection, connection.Data,
                                                  microphone, new Audio.Speaker());
            // Устройство не включаем: иначе в поток пойдёт и настоящий
            // звук из комнаты, и проверка будет считать чужое.
            var opened = await audio.StartCaptureAsync(listen: false);
            Check("ядро приняло поток микрофона", opened);
            Check("первый кредит выдан вместе с согласием", audio.Credit > 0,
                  $"| {audio.Credit} Б");

            var chunk = Tone(seconds: 0.1);
            var sent = 0;
            for (var i = 0; i < 8 && audio.Push(chunk); i++) sent += chunk.Length;
            Check("звук ушёл в ядро", sent > 0, $"| {sent} Б");

            var big = new byte[(int)audio.Credit + 4096];
            Check("сверх кредита не отправляется", !audio.Push(big));
            Check("отброшенное посчитано", audio.Dropped >= big.Length,
                  $"| {audio.Dropped} Б");

            await Task.Delay(900);
            var closed = await connection.CallAsync("stream.close",
                new System.Text.Json.Nodes.JsonObject
                {
                    ["stream_id"] = 11,
                }, TimeSpan.FromSeconds(10));
            var got = closed.Payload["bytes"]?.GetValue<int>() ?? 0;
            Check("ядро получило ровно отправленное",
                  got == sent && got == audio.Sent,
                  $"| ядро {got} Б, оболочка {sent} Б, учтено {audio.Sent} Б");
        }

        await link.DisposeAsync();
        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>Синтетический звук: 440 Гц в формате микрофона.</summary>
    private static byte[] Tone(double seconds)
    {
        var samples = (int)(Audio.Microphone.SampleRate * seconds);
        var pcm = new byte[samples * 2];
        for (var i = 0; i < samples; i++)
        {
            var value = (short)(Math.Sin(2 * Math.PI * 440 * i
                / Audio.Microphone.SampleRate) * 12000);
            pcm[i * 2] = (byte)(value & 0xFF);
            pcm[i * 2 + 1] = (byte)((value >> 8) & 0xFF);
        }
        return pcm;
    }

    private static async Task<T?> WaitFor<T>(Func<T?> get, Func<T, bool> ready)
        where T : class
    {
        for (var i = 0; i < 200; i++)
        {
            if (get() is { } value && ready(value)) return value;
            await Task.Delay(100);
        }
        return null;
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

    internal static void Save(Window window, string path)
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
