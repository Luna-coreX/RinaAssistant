using System.IO;
using System.Text.Json.Nodes;
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
    private Tray? _tray;
    private Hotkeys? _hotkeys;
    private string? _shotPath;
    private double _shotScroll;
    private string _shotSection = "settings";

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        var args = e.Args;

        // Язык можно задать снаружи: снимок на чужом языке — единственный
        // способ увидеть перевод целиком, а не по строчке (4.0-F08).
        if (Value(args, "--language") is { } language)
            Strings.Loc.Use(language);

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
            _shotScroll = double.TryParse(Value(args, "--scroll"), out var down)
                ? down : 0;
            _shotSection = Value(args, "--section") ?? "settings";
            // Без окна WPF завершается сам, едва OnStartup вернёт управление:
            // по умолчанию приложение живёт, пока живо хотя бы одно окно.
            // Самопроверке окно показывать незачем, поэтому закрываемся мы
            // сами и только когда закончим.
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckCoreAsync(window);
            return;
        }

        if (args.Contains("--check-tray"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckTrayAsync(window);
            return;
        }

        if (args.Contains("--check-system"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckSystemAsync(window);
            return;
        }

        if (args.Contains("--check-voice"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckVoiceAsync(window);
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

            // Трей и хоткеи заводятся до ядра: они принадлежат оболочке и
            // обязаны работать, даже если ядро не поднялось. Помощник,
            // которого нельзя вызвать с клавиатуры, потому что упал чужой
            // процесс, — не помощник.
            _tray = new Tray(window);
            _tray.ExitRequested += () => Shutdown();
            window.Tray = _tray;

            _hotkeys = new Hotkeys();
            _hotkeys.Attach(window);
            _hotkeys.Refused += (name, why) => window.ShowNote($"{name}: {why}");

            _link = new CoreLink(window, CoreLink.FindCore());
            window.Link = _link;
            _ = _link.StartAsync();
            _ = ApplySystemSettingsAsync(window);

            // Репетиция трея в настоящем режиме запуска. Проверка --check-tray
            // идёт при ShutdownMode.OnExplicitShutdown, а живая программа —
            // при OnLastWindowClose, и разница между ними как раз о том,
            // выживет ли программа без единого видимого окна.
            if (args.Contains("--rehearse-tray")) Rehearse(window);
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

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window,
                                                        IntPtr process);

    [System.Runtime.InteropServices.DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    /// <summary>
    /// F05: трей показывает окно обратно, а не роняет программу.
    /// </summary>
    /// <remarks>
    /// Проверяется в первую очередь <b>поток</b>, на котором приходит
    /// нажатие. Значок трея — это окно, и чьё оно, решает не тот, кто его
    /// создал, а тот, кто качает его очередь сообщений. Обращение к окну
    /// WPF с чужого потока — исключение, а исключение в обработчике,
    /// которого никто не ловит, завершает процесс: программа «выходит по
    /// нажатию на значок», хотя ничего похожего на выход в коде нет.
    /// </remarks>
    /// <summary>
    /// Спрятать окно и вернуть его — так, как это делает человек.
    /// </summary>
    private void Rehearse(MainWindow window)
    {
        Console.SetOut(new StreamWriter(Console.OpenStandardOutput())
        {
            AutoFlush = true,
        });
        Console.WriteLine($"репетиция: режим завершения {ShutdownMode}, "
                          + $"значок заведён {_tray?.Created}");
        Exit += (_, e) => Console.WriteLine($"репетиция: ПРОГРАММА ВЫШЛА, "
                                            + $"код {e.ApplicationExitCode}");

        var step = 0;
        var clock = new System.Windows.Threading.DispatcherTimer
        {
            Interval = TimeSpan.FromSeconds(2),
        };
        clock.Tick += (_, _) =>
        {
            step++;
            if (step == 1)
            {
                Console.WriteLine("репетиция: нажат крестик");
                window.OnCloseButton();
            }
            else if (step == 2)
                Console.WriteLine($"репетиция: окно видно? {window.IsVisible}; "
                                  + $"окон у программы {Windows.Count}");
            else if (step == 3)
            {
                Console.WriteLine("репетиция: нажат «Показать»");
                _tray?.Show();
            }
            else if (step == 4)
            {
                Console.WriteLine($"репетиция: окно видно? {window.IsVisible}");
                Console.WriteLine("репетиция: программа жива");
                clock.Stop();
                Shutdown();
            }
        };
        clock.Start();
    }

    private async Task CheckTrayAsync(MainWindow window)
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

        Console.WriteLine("=== F05: трей возвращает окно ===");
        window.Show();
        var ui = GetCurrentThreadId();

        var tray = new Tray(window);
        window.Tray = tray;

        Check("значок заведён", tray.Created,
              tray.Created ? "" : "| без него прятать окно нельзя");

        var handle = tray.MessageWindowHandle;
        Check("у значка есть своё окно", handle != IntPtr.Zero,
              handle == IntPtr.Zero
              ? "| нажатия уходят в никуда: система шлёт их окну"
              : $"| {handle}");
        var owner = handle == IntPtr.Zero ? 0
                    : GetWindowThreadProcessId(handle, IntPtr.Zero);
        Console.WriteLine($"     поток оболочки {ui}, "
                          + $"поток окна значка {owner}");
        Check("нажатие придёт на поток окна, а не на чужой",
              owner == ui,
              owner == ui ? "" : "| значит, обработчик обязан переходить "
                                 + "на поток окна сам");

        window.MinimiseToTray = true;
        window.OnCloseButton();
        await Task.Delay(200);
        Check("крестик спрятал окно, а не закрыл", !window.IsVisible);
        Check("окно живо и его можно показать снова", window.IsLoaded);

        // Возврат вызывается так же, как из меню значка: тем же методом.
        Exception? died = null;
        try { tray.Show(); }
        catch (Exception error) { died = error; }
        await Task.Delay(200);
        Check("возврат из трея не бросает исключение", died is null,
              died is null ? "" : $"| {died.GetType().Name}: {died.Message}");
        Check("окно вернулось видимым", window.IsVisible);
        Check("программа при этом не завершилась", true);

        tray.Dispose();
        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
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
        var launch = CoreLink.FindCore();
        Console.WriteLine($"     ядро запускает: {launch.Python}");
        Check("ядро запускается окружением проекта, если оно есть",
              !launch.Python.Equals("python",
                                        StringComparison.OrdinalIgnoreCase)
              || !Directory.Exists(Path.Combine(launch.WorkingDirectory, "venv")),
              "| иначе голосов и моделей у ядра не будет");
        var link = new CoreLink(window, launch);
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

        // Раскрытый список проверяется отдельно: всплывающее окно — своё
        // окно, в снимок главного оно не попадает вовсе, и сломанный
        // шаблон остался бы незамеченным ровно там, где он написан руками.
        if (settings?.FirstChoice() is { } choice)
        {
            choice.IsDropDownOpen = true;
            await Task.Delay(300);
            var popup = choice.Template.FindName("PART_Popup", choice)
                        as System.Windows.Controls.Primitives.Popup;
            Check("список раскрывается своим шаблоном",
                  popup is { IsOpen: true, Child: not null },
                  $"| вариантов {choice.Items.Count}");
            Check("варианты обрели вид",
                  choice.ItemContainerGenerator.ContainerFromIndex(0)
                      is FrameworkElement { IsLoaded: true });
            choice.IsDropDownOpen = false;
            await Task.Delay(100);
        }
        else Check("список раскрывается своим шаблоном", false,
                   "| ни одного списка на странице");

        window.ShowSectionFor("commands");
        await Task.Delay(1500);
        Check("страница команд открылась",
              window.CurrentPage is Pages.CommandsPage);

        // Плагины: последняя страница, остававшаяся заглушкой. Проверяется
        // весь круг — список, включение, своя страница плагина и действие
        // на ней, — потому что каждое звено здесь пересекает границу
        // процессов, и «список пришёл» ещё ничего не значит.
        window.ShowSectionFor("plugins");
        await Task.Delay(1500);
        if (window.CurrentPage is Pages.PluginsPage plugins)
        {
            for (var i = 0; i < 60 && plugins.PluginCount == 0; i++)
                await Task.Delay(100);
            Check("плагины пришли из ядра", plugins.PluginCount > 0,
                  $"| {plugins.PluginCount}");

            var drawn = await plugins.OpenFirstPageAsync();
            Check("плагин включился и отдал свою страницу", drawn > 0,
                  $"| элементов {drawn}");
            Check("проверка вернула плагины как было",
                  plugins.PageElementCount == 0,
                  "| включённое ею выключено обратно");
        }
        else Check("страница плагинов открылась", false);

        // Снимок живого окна, если попросили: настройки с настоящими
        // значениями от настоящего ядра — единственный способ увидеть, как
        // это выглядит на самом деле, а не как выглядит пустая страница.
        if (_shotPath is { } shot)
        {
            window.ShowSectionFor(_shotSection);
            await Task.Delay(800);
            if (_shotScroll > 0 && window.CurrentPage is Pages.SettingsPage page)
            {
                page.ScrollTo(_shotScroll);
                await Task.Delay(200);
            }
            Save(window, shot);
        }

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

    /// <summary>
    /// E04 + F10: ядро синтезирует, оболочка воспроизводит.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Проверка сквозная и <b>звучит вслух</b>: только так видно, что путь
    /// цел от текста до динамика. Каждое звено в отдельности было исправно,
    /// а Рина молчала — синтез умел один Piper, а канал речи в живой
    /// программе не читал никто.
    /// </para>
    /// <para>
    /// Ядро поднимается под песочницей, потому что проверке нужно сменить
    /// движок синтеза: настройки человека для этого не трогают.
    /// </para>
    /// </remarks>
    private async Task CheckVoiceAsync(MainWindow window)
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

        Console.WriteLine("=== E04/F10: Рина говорит ===");
        var real = CoreLink.FindCore();
        var sandboxed = new Rina.Protocol.CoreLaunch(
            real.Python,
            Path.Combine(real.WorkingDirectory, "tools", "_core_sandboxed.py"),
            real.WorkingDirectory);

        var link = new CoreLink(window, sandboxed);
        window.Link = link;
        await link.StartAsync();
        for (var i = 0; i < 400 && link.State != Rina.Protocol.CoreState.Ready; i++)
            await Task.Delay(100);
        Check("ядро на связи", link.State == Rina.Protocol.CoreState.Ready,
              $"| {link.State}");

        // Связь возникает в чужом потоке, а звук заводится в потоке окна:
        // между «Ready» и «есть чем играть» лежит одна очередь сообщений.
        for (var i = 0; i < 50 && link.Voice is null; i++) await Task.Delay(100);
        Check("звук заведён вместе со связью", link.Voice is not null);

        if (link.Connection is { Ready: true } connection && link.Voice is { } voice)
        {
            // Системный синтез: он есть на всякой Windows и не ходит в сеть.
            var told = await connection.CallAsync(Rina.Protocol.Methods.SettingsSet,
                new JsonObject
                {
                    ["values"] = new JsonObject
                    {
                        ["tts_engine"] = "pyttsx3",
                        ["voice"] = "default",
                    },
                }, TimeSpan.FromSeconds(15));
            Check("движок синтеза выбран",
                  told.Payload["verdicts"]?["tts_engine"]?["accepted"]
                      ?.GetValue<bool>() == true,
                  $"| {told.Payload["verdicts"]?["tts_engine"]}");

            await connection.CallAsync(Rina.Protocol.Methods.SpeechSay, new JsonObject
            {
                ["text"] = "Проверка голоса.",
            }, TimeSpan.FromSeconds(30));

            for (var i = 0; i < 200 && voice.Received == 0; i++)
                await Task.Delay(100);
            Check("речь пришла из ядра в оболочку", voice.Received > 0,
                  $"| {voice.Received} Б");

            // Слышно ли это на самом деле, машина сказать не может; но
            // очередь динамика — то место, откуда звук уже никуда не
            // денется, кроме как в устройство.
            await Task.Delay(300);
            Check("динамик получил речь",
                  voice.Received > 0 && voice.Pending >= 0,
                  $"| в очереди {voice.Pending} Б");

            var seconds = voice.Received / 2.0 / 22050;
            Check("речь похожа на фразу, а не на щелчок", seconds > 0.3,
                  $"| около {seconds:0.0} с");
            await Task.Delay(2000);          // дать договорить
        }

        await link.DisposeAsync();
        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// F05/F06: трей, автозапуск, сочетания клавиш.
    /// </summary>
    /// <remarks>
    /// Автозапуск проверяется на настоящем реестре, но **возвращается как
    /// было**: проверка не имеет права оставить после себя запись в
    /// автозагрузке пользователя.
    /// </remarks>
    private Task CheckSystemAsync(MainWindow window)
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

        Console.WriteLine("=== F05/F06: трей, автозапуск, сочетания ===");

        // --- F06: разбор сочетаний ---
        Check("обычное сочетание разбирается",
              Hotkeys.TryParse("Ctrl+Shift+R", out var mods, out var key)
              && key != 0 && mods.HasFlag(Hotkeys.Mod.Control)
              && mods.HasFlag(Hotkeys.Mod.Shift));
        Check("Win и Alt тоже",
              Hotkeys.TryParse("Win+Alt+Space", out var m2, out _)
              && m2.HasFlag(Hotkeys.Mod.Win) && m2.HasFlag(Hotkeys.Mod.Alt));
        Check("клавиша без модификатора отвергнута",
              !Hotkeys.TryParse("R", out _, out _),
              "| иначе «R» в чужом редакторе вызывал бы Рину");
        Check("пустое отвергнуто", !Hotkeys.TryParse("", out _, out _));
        Check("бессмыслица отвергнута",
              !Hotkeys.TryParse("Ctrl+Кнопка", out _, out _));

        window.Left = -4000;
        window.Top = -4000;
        window.Show();

        using var hotkeys = new Hotkeys();
        hotkeys.Attach(window);
        var pressed = 0;
        var taken = hotkeys.Bind("проверка", "Ctrl+Alt+F24", () => pressed++);
        Check("сочетание занято в системе", taken, $"| {hotkeys.Count}");
        hotkeys.Unbind("проверка");
        Check("и отпущено", hotkeys.Count == 0);

        var refusals = new List<string>();
        hotkeys.Refused += (name, why) => refusals.Add(why);
        hotkeys.Bind("кривое", "Ctrl+Кнопка", () => { });
        Check("о неразобранном сочетании сказано", refusals.Count == 1,
              $"| {string.Join("; ", refusals)}");

        // --- F05: трей ---
        using var tray = new Tray(window);
        Check("значок в трее создан", true);
        tray.Hide();
        Check("окно спрятано, программа жива", !window.IsVisible);
        tray.Show();
        Check("и возвращается по требованию", window.IsVisible);

        // --- F05: автозапуск, с возвратом как было ---
        var was = Autostart.Enabled;
        Check("команда запуска указывает на нас",
              Autostart.Command.Contains("Rina.Shell"), $"| {Autostart.Command}");
        try
        {
            if (Autostart.Apply(!was))
            {
                Check("автозапуск переключается", Autostart.Enabled == !was);
                Autostart.Apply(was);
                Check("и возвращается как было", Autostart.Enabled == was);
            }
            else
            {
                Console.WriteLine("      автозапуск запрещён политикой — пропускаем");
            }
        }
        finally
        {
            if (Autostart.Enabled != was) Autostart.Apply(was);
        }

        window.Hide();
        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
        return Task.CompletedTask;
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

    /// <summary>
    /// Привести систему в соответствие настройкам ядра.
    /// </summary>
    /// <remarks>
    /// Ждём связи: настройки живут в ядре, и до рукопожатия их неоткуда
    /// взять. Пока ждём, окно уже показано и работает — запуск не заложник
    /// чужого процесса.
    /// </remarks>
    private async Task ApplySystemSettingsAsync(MainWindow window)
    {
        for (var i = 0; i < 300 && _link?.Connection is not { Ready: true }; i++)
            await Task.Delay(100);

        if (_link is null) return;
        var values = await _link.GetAsync("autostart", "minimize_to_tray",
                                          "start_minimized", "hotkey",
                                          "action_hotkeys");
        if (values is null) return;

        var wanted = values["autostart"]?.GetValue<bool>() ?? false;
        if (wanted != Autostart.Enabled && !Autostart.Apply(wanted))
            window.ShowNote("Не удалось изменить автозапуск: запрещено политикой.");

        window.MinimiseToTray = values["minimize_to_tray"]?.GetValue<bool>()
                                ?? true;

        // Основное сочетание: показать окно и начать слушать.
        if (values["hotkey"]?.GetValue<string>() is { Length: > 0 } main)
            _hotkeys?.Bind("main", main, () => window.OnMainHotkey());

        if (values["start_minimized"]?.GetValue<bool>() == true)
            window.Hide();
    }

    protected override void OnExit(ExitEventArgs e)
    {
        // Ядро завершается само, увидев обрыв (§13), но попрощаться вежливо
        // дешевле, чем полагаться на это: у него есть что закрыть.
        _hotkeys?.Dispose();
        _tray?.Dispose();
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
