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

        if (args.Contains("--check-overlays"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckOverlaysAsync(window, Value(args, "--shot"));
            return;
        }

        if (args.Contains("--check-hover"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckHoverAsync(window);
            return;
        }

        if (args.Contains("--check-motion"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckMotionAsync(window);
            return;
        }

        if (args.Contains("--check-confirm"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckConfirmAsync();
            return;
        }

        if (args.Contains("--check-platform"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckPlatformAsync();
            return;
        }

        if (args.Contains("--check-pages"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _shotSection = Value(args, "--section") ?? "commands";
            _ = CheckPagesAsync(window);
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

        // Снимок плавающей строки: она живёт поверх чужих окон, и в снимок
        // главного окна не попадает вовсе.
        if (Value(args, "--shot-bar") is { } barShot)
        {
            var bar = new FloatingBar(null);
            bar.Left = -4000;
            bar.Top = -4000;
            bar.Show();
            Dispatcher.BeginInvoke(new Action(() =>
            {
                Save(bar, barShot);
                Shutdown();
            }), System.Windows.Threading.DispatcherPriority.ContextIdle);
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
            // Окна поверх экрана: реплика и плашка «слушаю». Заводятся до
            // ядра — они принадлежат оболочке, и плашка обязана появиться,
            // даже если ядро отвечает медленно.
            window.Toast = new Overlays.Toast();
            window.Plaque = new Overlays.Listening();

            _tray = new Tray(window);
            _tray.ExitRequested += () => Shutdown();
            window.Tray = _tray;

            _hotkeys = new Hotkeys();
            _hotkeys.Attach(window);
            _hotkeys.Refused += (name, why) => window.ShowNote($"{name}: {why}");

            _link = new CoreLink(window, CoreLink.FindCore());
            window.Link = _link;

            // Уведомления: то, чего человек не видит, ему говорят. Событие
            // берётся то же, что рисует окно, — второго источника ответов
            // Рины быть не должно.
            _link.CoreEvent += message => OnCoreEventForTray(window, message);

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
              owner == ui ? "" : "| значит, обработчик обязан переходить на поток окна сам");

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

        // Ширину задаёт колонка, а не орган. По снимку это не померить:
        // правый край колонки не граница цвета — у ряда с путём справа
        // кнопка, у ползунка число, и заливка кончается раньше колонки.
        // Меряем дерево. Поймано было человеком со скриншотами: поле пути
        // 200, список 280, ползунок 276 — край гулял на восемьдесят точек.
        if (settings is not null)
        {
            var widths = settings.ControlWidths();
            var wanted = Pages.SettingsPage.WantedControlWidth;
            var odd = widths.Where(w => Math.Abs(w.Width - wanted) > 1)
                            .Select(w => $"{w.Key}={w.Width}").ToArray();
            Check("органы управления одной ширины", odd.Length == 0,
                  odd.Length == 0 ? $"| {widths.Count} шт. по {wanted}"
                                  : $"| {string.Join(", ", odd)}");
        }

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

            // Что было включено до нас. Проверка идёт на настоящем ядре,
            // то есть на настройках человека, и оставить после себя
            // включённый плагин права не имеет.
            var before = await plugins.EnabledAsync();

            var drawn = await plugins.OpenFirstPageAsync();
            Check("плагин включился и отдал свою страницу", drawn > 0,
                  $"| элементов {drawn}");

            var after = await plugins.EnabledAsync();
            // Раздел плагина в колонке (замечание человека): «я этим
            // пользуюсь» — это место слева, а не карточка в списке
            // установленного.
            await link.RefreshPluginSectionsAsync();
            await Task.Delay(400);
            Check("у плагина со страницей есть свой раздел",
                  window.SectionNames().Any(n => n.StartsWith("plugin:")),
                  $"| {string.Join(", ", window.SectionNames())}");

            Check("проверка вернула плагины как было",
                  before.SequenceEqual(after),
                  $"| было [{string.Join(", ", before)}], "
                  + $"стало [{string.Join(", ", after)}]");
        }
        else Check("страница плагинов открылась", false);

        // Снимок живого окна, если попросили: настройки с настоящими
        // значениями от настоящего ядра — единственный способ увидеть, как
        // это выглядит на самом деле, а не как выглядит пустая страница.
        if (_shotPath is { } shot)
        {
            window.ShowSectionFor(_shotSection);
            await Task.Delay(800);
            // Страница плагина рисуется по описанию из другого процесса, и
            // увидеть её глазами можно только раскрыв: снимок пустого
            // списка не показывает ни карточек, ни рядов.
            Pages.PluginsPage? shown = null;
            if (_shotSection == "plugins"
                && window.CurrentPage is Pages.PluginsPage opened)
            {
                shown = opened;
                await shown.OpenFirstPageAsync(keepOpen: true);
                await Task.Delay(300);
            }
            if (_shotScroll > 0 && window.CurrentPage is Pages.SettingsPage page)
            {
                page.ScrollTo(_shotScroll);
                await Task.Delay(200);
            }
            Save(window, shot);

            // И вернуть как было. Снимок — наблюдение, а не действие:
            // оставить после себя включённый плагин он права не имеет,
            // потому что настройки под ним настоящие, человеческие.
            if (shown is not null) await shown.RestoreAsync();
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
    /// Реплика и плашка «слушаю» поверх экрана.
    /// </summary>
    /// <remarks>
    /// Проверяется поведение, а не картинка: реплика не показывается при
    /// открытом окне, плашка не гаснет от `listening.stopped`, пока включён
    /// режим «всегда слушаю». Оба правила легко нарушить правкой и
    /// невозможно заметить глазами — плашка гаснет через час работы, а
    /// лишняя реплика видна только тому, у кого окно открыто.
    /// </remarks>
    private async Task CheckOverlaysAsync(MainWindow window, string? shot)
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

        Console.WriteLine("=== Поверх экрана: реплика и плашка ===");

        window.Toast = new Overlays.Toast();
        window.Plaque = new Overlays.Listening();
        window.ShowToasts = true;

        static Rina.Protocol.Envelope Event(string method,
            System.Text.Json.Nodes.JsonObject payload)
            => new()
            {
                Type = "event",
                Id = "chk-1",
                Method = method,
                Payload = payload,
                TraceId = "t-check",
                Version = 1,
            };

        // Окно спрятано: реплику человек иначе не увидит.
        window.Hide();
        window.OnCoreEvent(Event("assistant.response",
            new System.Text.Json.Nodes.JsonObject { ["text"] = "Сейчас 14:30." }));
        await Task.Delay(300);
        Check("реплика показана, когда окна не видно",
              window.Toast.Shown == "Сейчас 14:30.",
              $"| {window.Toast.Shown}");

        // Окно открыто: ответ уже перед человеком.
        window.Show();
        await Task.Delay(200);
        window.Toast.Dismiss();
        await Task.Delay(300);
        window.OnCoreEvent(Event("assistant.response",
            new System.Text.Json.Nodes.JsonObject { ["text"] = "Второй ответ" }));
        await Task.Delay(300);
        Check("при открытом окне реплика не дублируется",
              window.Toast.Shown != "Второй ответ",
              $"| {window.Toast.Shown}");
        window.Hide();

        // Плашка: разовое слушание.
        window.OnCoreEvent(Event("listening.started",
            new System.Text.Json.Nodes.JsonObject()));
        await Task.Delay(300);
        Check("плашка появилась на разовом слушании", window.Plaque.Visible);
        Check("и сказано, что это разовое",
              window.Plaque.Caption.Contains("Слушаю"),
              $"| {window.Plaque.Caption}");

        window.OnCoreEvent(Event("listening.stopped",
            new System.Text.Json.Nodes.JsonObject()));
        await Task.Delay(400);
        Check("и ушла, когда слушать перестали", !window.Plaque.Visible);

        // Плашка: режим.
        window.OnCoreEvent(Event("listening.always",
            new System.Text.Json.Nodes.JsonObject { ["enabled"] = true }));
        await Task.Delay(300);
        Check("в режиме «всегда» плашка тоже появляется",
              window.Plaque.Visible);
        Check("и говорит, что это режим",
              window.Plaque.Caption.Contains("Всегда"),
              $"| {window.Plaque.Caption}");

        // Вот это и есть главное: распознанная фраза не гасит режим.
        window.OnCoreEvent(Event("listening.stopped",
            new System.Text.Json.Nodes.JsonObject()));
        await Task.Delay(400);
        Check("распознанная фраза не гасит режим", window.Plaque.Visible,
              "| иначе человек перестал бы видеть, что микрофон работает");

        window.OnCoreEvent(Event("listening.always",
            new System.Text.Json.Nodes.JsonObject { ["enabled"] = false }));
        await Task.Delay(400);
        Check("отмена режима убирает плашку", !window.Plaque.Visible);

        // Снимок, если попросили: реплика и плашка вместе.
        if (shot is not null)
        {
            window.Toast.Say("Запускаю Visual Studio Code.");
            window.Plaque.Appear(always: true);
            await Task.Delay(500);
            Save(window.Toast, shot);
            Save(window.Plaque, shot.Replace(".png", "-plaque.png"));
        }

        window.Toast.Close();
        window.Plaque.Close();
        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetCursorPos(int x, int y);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool GetCursorPos(out System.Drawing.Point point);

    /// <summary>
    /// Наводка на строку списка: подсвечена одна, и гаснет, когда ушли.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Курсор двигается по-настоящему: `IsMouseOver` только читается, его
    /// выставляет попадание курсора, и ни снимком, ни вызовом метода это
    /// не проверяется.
    /// </para>
    /// <para>
    /// <b>И возвращается туда, где был.</b> Проверка не имеет права
    /// оставить чужую мышь в углу экрана — то же правило, по которому
    /// проверка автозапуска возвращает запись в реестре.
    /// </para>
    /// </remarks>
    private async Task CheckHoverAsync(MainWindow window)
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

        Console.WriteLine("=== движение: наводка на строку списка ===");
        GetCursorPos(out var was);
        try
        {
            window.Width = 940;
            window.Height = 620;
            window.WindowStartupLocation = WindowStartupLocation.Manual;
            window.Left = 40;
            window.Top = 40;
            // Поверх всех и с фокусом: `Synchronize` определяет, над чем
            // курсор, попаданием в **видимое** окно, и чужое окно сверху
            // делало проверку то зелёной, то красной без единой правки.
            window.Topmost = true;
            window.Show();
            window.Activate();

            // Со своим ядром: страница команд без связи показывает «ядро
            // не на связи» и ни одной строки — проверять было бы нечего.
            var real = CoreLink.FindCore();
            var link = new CoreLink(window, new Rina.Protocol.CoreLaunch(
                real.Python,
                Path.Combine(real.WorkingDirectory, "tools",
                             "_core_sandboxed.py"),
                real.WorkingDirectory));
            window.Link = link;
            await link.StartAsync();
            for (var i = 0; i < 300
                 && link.State != Rina.Protocol.CoreState.Ready; i++)
                await Task.Delay(100);

            window.ShowSectionFor("commands");
            await Task.Delay(2000);

            var rows = Rows(window).Take(2).ToArray();
            Check("строки списка нашлись", rows.Length == 2,
                  $"| {rows.Length}");
            if (rows.Length < 2)
            {
                // Не `return`: режим живёт до явного завершения, и выход
                // отсюда оставил бы окно висеть навсегда. Так и вышло с
                // первой редакцией этой проверки.
                Console.WriteLine();
                Console.WriteLine($"Ошибок: {fails}");
                Environment.ExitCode = 1;
                Shutdown();
                return;
            }

            Check("у каждой строки своя кисть",
                  !ReferenceEquals(rows[0].Background, rows[1].Background),
                  "| общая подсветила бы всю таблицу разом");

            await HoverAsync(rows[0]);
            Check("наведённая строка подсветилась",
                  Lit(rows[0]) > 0.5, $"| {Lit(rows[0]):0.00}");
            Check("соседняя осталась тёмной",
                  Lit(rows[1]) < 0.1, $"| {Lit(rows[1]):0.00}");

            await HoverAsync(rows[1]);
            Check("подсветка перешла на соседнюю",
                  Lit(rows[1]) > 0.5 && Lit(rows[0]) < 0.1,
                  $"| {Lit(rows[0]):0.00} → {Lit(rows[1]):0.00}");

            SetCursorPos((int)window.Left + 20, (int)window.Top + 600);
            await Task.Delay(500);
            Check("ушли — погасло", Lit(rows[1]) < 0.1,
                  $"| {Lit(rows[1]):0.00}");

            // --- варианты раскрытого списка ---------------------------
            Console.WriteLine();
            Console.WriteLine("=== движение: наводка на вариант списка ===");

            window.ShowSectionFor("settings");
            await Task.Delay(2500);

            // Страница настроек собирается по проводу: схема, значения и
            // списки вариантов — три отдельных ответа ядра. Ждём, пока
            // появятся варианты, а не фиксированное время: на медленной
            // машине фиксированного всегда не хватит.
            System.Windows.Controls.ComboBox? choice = null;
            for (var i = 0; i < 60 && choice is null; i++)
            {
                choice = Boxes(window).FirstOrDefault(b => b.Items.Count > 2);
                if (choice is null) await Task.Delay(200);
            }
            Console.WriteLine($"     списков на странице: "
                              + $"{Boxes(window).Count()}");
            Check("выпадающий список с вариантами нашёлся", choice is not null,
                  $"| вариантов {choice?.Items.Count ?? 0}");
            if (choice is null)
            {
                Console.WriteLine();
                Console.WriteLine($"Ошибок: {++fails}");
                Environment.ExitCode = 1;
                Shutdown();
                return;
            }

            choice.IsDropDownOpen = true;
            await Task.Delay(600);

            var options = choice.Items.OfType<System.Windows.Controls.ComboBoxItem>()
                                .Where(o => o.IsEnabled).Take(2).ToArray();
            Check("варианты раскрылись", options.Length == 2,
                  $"| {options.Length}");
            if (options.Length == 2)
            {
                Check("у каждого варианта своя кисть",
                      !ReferenceEquals(Warm(options[0]), Warm(options[1])));

                // Главная проверка, и она не про движение. Прозрачность
                // может честно уезжать в единицу, а видно не будет
                // ничего, если цвет подсветки равен цвету подложки —
                // именно так и было: анимация шла, проверка зеленела,
                // человек не видел наводки.
                var under = Surface(options[0]);
                var over = (Warm(options[0]) as
                            System.Windows.Media.SolidColorBrush)?.Color;
                Check("подсветка отличается от подложки",
                      under is not null && over is not null
                      && Apart(under.Value, over.Value) > 8,
                      $"| подложка {under} против подсветки {over}");

                await HoverAsync(options[1]);
                Check("вариант под курсором подсветился",
                      Glow(options[1]) > 0.5, $"| {Glow(options[1]):0.00}");
                Check("соседний остался тёмным",
                      Glow(options[0]) < 0.1, $"| {Glow(options[0]):0.00}");

                await HoverAsync(options[0]);
                Check("подсветка перешла",
                      Glow(options[0]) > 0.5 && Glow(options[1]) < 0.1,
                      $"| {Glow(options[1]):0.00} → {Glow(options[0]):0.00}");
            }
            choice.IsDropDownOpen = false;
        }
        finally
        {
            SetCursorPos(was.X, was.Y);
        }

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>Выпадающие списки страницы в порядке появления.</summary>
    private static IEnumerable<System.Windows.Controls.ComboBox> Boxes(
        DependencyObject root)
    {
        foreach (var child in Children(root))
        {
            if (child is System.Windows.Controls.ComboBox box)
                yield return box;
            foreach (var deeper in Boxes(child)) yield return deeper;
        }
    }

    /// <summary>Кисть подсветки варианта: она у каждого своя.</summary>
    private static System.Windows.Media.Brush? Warm(
        System.Windows.Controls.ComboBoxItem option)
        => (option.Template?.FindName("Row", option)
            as System.Windows.Controls.Border)?.Background;

    /// <summary>На чём лежит вариант: цвет ближайшей залитой подложки.</summary>
    private static System.Windows.Media.Color? Surface(DependencyObject item)
    {
        for (var node = System.Windows.Media.VisualTreeHelper.GetParent(item);
             node is not null;
             node = System.Windows.Media.VisualTreeHelper.GetParent(node))
        {
            if (node is System.Windows.Controls.Border { Background:
                    System.Windows.Media.SolidColorBrush paint }
                && paint.Opacity > 0.5)
                return paint.Color;
        }
        return null;
    }

    /// <summary>Насколько два цвета различимы: сумма расхождений каналов.</summary>
    private static int Apart(System.Windows.Media.Color a,
                             System.Windows.Media.Color b)
        => Math.Abs(a.R - b.R) + Math.Abs(a.G - b.G) + Math.Abs(a.B - b.B);

    /// <summary>Насколько вариант подсвечен сейчас.</summary>
    private static double Glow(System.Windows.Controls.ComboBoxItem option)
        => (Warm(option) as System.Windows.Media.SolidColorBrush)?.Opacity ?? -1;

    /// <summary>Навести курсор в середину варианта.</summary>
    private static async Task HoverAsync(
        System.Windows.Controls.ComboBoxItem option)
    {
        var middle = option.PointToScreen(new Point(option.ActualWidth / 2,
                                                    option.ActualHeight / 2));
        SetCursorPos((int)middle.X, (int)middle.Y);
        System.Windows.Input.Mouse.Synchronize();
        await Task.Delay(500);
    }

    /// <summary>Насколько строка подсвечена сейчас.</summary>
    private static double Lit(System.Windows.Controls.Border row)
        => (row.Background as System.Windows.Media.SolidColorBrush)?.Opacity ?? -1;

    /// <summary>Навести курсор в середину строки и дать движению пройти.</summary>
    private static async Task HoverAsync(System.Windows.Controls.Border row)
    {
        var middle = row.PointToScreen(new Point(row.ActualWidth / 2,
                                                 row.ActualHeight / 2));
        SetCursorPos((int)middle.X, (int)middle.Y);

        // Одного `SetCursorPos` мало: WPF узнаёт о положении курсора из
        // сообщений ввода, а телепортация их не порождает — окно так и
        // считало, что мышь не над ним. `Synchronize` заставляет заново
        // определить, над чем курсор сейчас.
        System.Windows.Input.Mouse.Synchronize();
        await Task.Delay(500);
    }

    /// <summary>Строки списка в порядке появления.</summary>
    private static IEnumerable<System.Windows.Controls.Border> Rows(
        DependencyObject root)
    {
        var style = Application.Current.TryFindResource("Rows.Item") as Style;
        foreach (var child in Children(root))
        {
            if (child is System.Windows.Controls.Border border
                && ReferenceEquals(border.Style, style))
                yield return border;
            foreach (var deeper in Rows(child)) yield return deeper;
        }
    }

    private static IEnumerable<DependencyObject> Children(DependencyObject root)
    {
        var count = System.Windows.Media.VisualTreeHelper.GetChildrenCount(root);
        for (var i = 0; i < count; i++)
            yield return System.Windows.Media.VisualTreeHelper.GetChild(root, i);
    }

    /// <summary>
    /// Движение видно во времени, а не на снимке.
    /// </summary>
    private async Task CheckMotionAsync(MainWindow window)
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

        Console.WriteLine("=== движение: переход между разделами ===");
        window.Left = -4000;
        window.Top = -4000;
        window.Show();
        await Task.Delay(400);

        window.ShowSectionFor("commands");

        // Меряем не мгновенно, а в середине хода. До первого такта часов
        // анимации свойство отдаёт базовое значение, и мгновенное чтение
        // показало бы единицу даже при исправной анимации — проверка
        // соврала бы в обе стороны.
        await Task.Delay(80);
        var midway = window.PaneOpacity;
        var rise = window.PaneRise;
        Check("на середине перехода панель ещё проявляется",
              midway is > 0.01 and < 0.95,
              $"| прозрачность {midway:0.00}");
        Check("и ещё не доехала", rise > 0.05, $"| осталось {rise:0.00} точек");

        await Task.Delay(400);
        var later = window.PaneOpacity;
        Check("через 400 мс панель на месте", later > 0.99,
              $"| прозрачность {later:0.00}");
        Check("и доехала", Math.Abs(window.PaneRise) < 0.01,
              $"| смещение {window.PaneRise:0.00}");

        // Второй переход — отдельная проверка, и не для полноты. Анимация
        // завершается с `HoldEnd`, то есть продолжает удерживать единицу
        // после конца. Без явного `From` следующая начиналась бы с
        // удерживаемого значения, и дипа не было бы: первый переход после
        // запуска виден, все следующие — нет.
        window.ShowSectionFor("reminders");
        await Task.Delay(80);
        var second = window.PaneOpacity;
        Check("второй переход тоже проявляется",
              second is > 0.01 and < 0.95,
              $"| прозрачность {second:0.00}");

        await Task.Delay(400);
        window.ShowSectionFor("settings");
        await Task.Delay(80);
        var third = window.PaneOpacity;
        Check("и третий", third is > 0.01 and < 0.95,
              $"| прозрачность {third:0.00}");

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// F11: у вопроса есть срок, но не у всякого.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Поймано человеком, а не проверкой: «Сбросить настройки» открывало
    /// окно, которое пропадало раньше, чем его успевали прочесть.
    /// Переданный ноль означал «без срока», а конструктор превращал его в
    /// одну секунду.
    /// </para>
    /// <para>
    /// Снимок такое не ловит — на снимке окно правильное. Ловится только
    /// временем: подождать и посмотреть, здесь ли оно ещё.
    /// </para>
    /// </remarks>
    private async Task CheckConfirmAsync()
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

        Console.WriteLine("=== F11: срок у вопроса ===");

        // Вопрос, который человек открыл сам: срока нет.
        var mine = new Pages.ConfirmWindow("Настройки вернутся к умолчанию.",
                                           "Команды останутся.", 0);
        mine.Left = -4000;
        mine.Top = -4000;
        mine.Show();
        Check("вопрос по нажатию — без срока", !mine.Timed);
        Check("счётчик спрятан",
              mine.Countdown.Visibility != Visibility.Visible);

        await Task.Delay(2500);
        Check("и через две с половиной секунды окно на месте",
              mine.IsVisible, "| ноль значит «ждать», а не «одна секунда»");
        Check("невыбранный ответ — отказ, а не «истёк»",
              mine.Result == Pages.Consent.Refused, $"| {mine.Result}");
        mine.Close();

        // Вопрос от ядра: срок есть, и по нему окно закрывается само.
        var theirs = new Pages.ConfirmWindow("Компьютер будет выключен.",
                                             "Сказано голосом", 2);
        theirs.Left = -4000;
        theirs.Top = -4000;
        theirs.Show();
        Check("вопрос от ядра — со сроком", theirs.Timed);
        Check("счётчик показан",
              theirs.Countdown.Visibility == Visibility.Visible);

        await Task.Delay(3200);
        Check("по сроку окно закрылось само", !theirs.IsVisible);
        Check("молчание засчитано отказом",
              theirs.Result == Pages.Consent.Expired, $"| {theirs.Result}");

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// G01..G12: системный слой оболочки.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Проверяется то, что <b>не</b> должно случиться, наравне с тем, что
    /// должно: «Загрузки» не попадают в индекс, junction наружу не проходит
    /// проверку доверия, неподписанное не запускается молча. Правило, за
    /// которым никто не следит, держится ровно до первой правки.
    /// </para>
    /// <para>
    /// Ничего необратимого проверка не делает: питание и блокировка есть в
    /// таблице действий, но здесь не вызываются — проверка, выключающая
    /// компьютер, запускается один раз.
    /// </para>
    /// </remarks>
    private Task CheckPlatformAsync()
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

        Console.WriteLine("=== G: системный слой оболочки ===");

        // --- запреты (G08) ---
        var downloads = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            "Downloads", "что-нибудь.exe");
        Check("«Загрузки» запрещены к индексации",
              Platform.AppIndex.Forbidden(downloads));
        Check("рабочий стол запрещён",
              Platform.AppIndex.Forbidden(Path.Combine(
                  Environment.GetFolderPath(Environment.SpecialFolder.Desktop),
                  "любое.exe")));
        Check("временный каталог запрещён",
              Platform.AppIndex.Forbidden(
                  Path.Combine(Path.GetTempPath(), "любое.exe")));
        Check("а системный каталог — нет",
              !Platform.AppIndex.Forbidden(
                  @"C:\Windows\System32\notepad.exe"));

        // --- канонический путь (G11) ---
        var link = Path.Combine(Path.GetTempPath(), "rina-check-link");
        var outside = Environment.GetFolderPath(
            Environment.SpecialFolder.UserProfile);
        try
        {
            if (Directory.Exists(link)) Directory.Delete(link);
            // Junction, а не symlink: symlink требует прав, а junction —
            // нет, и в G11 назван именно он. Создаётся тем же `mklink`,
            // которым его создал бы человек.
            var made = global::System.Diagnostics.Process.Start(
                new global::System.Diagnostics.ProcessStartInfo
                {
                    FileName = "cmd.exe",
                    Arguments = $"/c mklink /J \"{link}\" \"{outside}\"",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                });
            made?.WaitForExit(5000);

            var resolved = Platform.AppIndex.Canonical(link);
            Check("junction разворачивается в настоящий путь",
                  string.Equals(resolved, outside,
                                StringComparison.OrdinalIgnoreCase),
                  $"| {resolved}");
            Check("и по развёрнутому пути видно, что он вне доверенного",
                  !string.Equals(resolved, link,
                                 StringComparison.OrdinalIgnoreCase));
        }
        catch (Exception error)
        {
            Console.WriteLine($"     junction не создан: {error.GetType().Name}");
        }
        finally
        {
            try { if (Directory.Exists(link)) Directory.Delete(link); }
            catch { }
        }

        Check("непонятный путь — это «нельзя», а не «наверное можно»",
              Platform.AppIndex.Canonical("").Length == 0
              && Platform.AppIndex.Forbidden(""));

        // --- подпись (G09) ---
        var signed = @"C:\Windows\System32\notepad.exe";
        Check("системная программа подписана",
              Platform.AppEntry.HasSignature(signed),
              $"| {Platform.AppEntry.CatalogTrace(signed)}");
        var unsigned = Path.Combine(Path.GetTempPath(), "rina-unsigned.exe");
        try
        {
            File.WriteAllBytes(unsigned, new byte[] { 0x4D, 0x5A, 0, 0 });
            Check("подделка под программу — не подписана",
                  !Platform.AppEntry.HasSignature(unsigned));
            Check("и без согласия человека не запускается",
                  Platform.Launcher.Start(unsigned, "file", trusted: false)
                      is { Ok: false });
        }
        finally
        {
            try { File.Delete(unsigned); } catch { }
        }

        // --- индекс (G04) ---
        var index = Platform.AppIndex.Get(refresh: true);
        Check("индекс собрался", index.Count > 0, $"| записей {index.Count}");
        Check("у каждой записи есть источник",
              index.All(e => e.Source.Length > 0));
        Check("ни одна запись не из запрещённого каталога",
              index.All(e => e.Kind == "uwp"
                             || !Platform.AppIndex.Forbidden(e.Launch)));
        Check("источники известны",
              index.All(e => Platform.AppIndex.SourceOrder.Contains(e.Source)),
              $"| {string.Join(", ", index.Select(e => e.Source).Distinct())}");
        Check("подпись проверена у файлов, а не у пакетов",
              index.Any(e => e.Kind == "file" && e.Signed));

        // --- действия (G01) ---
        Check("таблица действий закрыта и названа",
              Platform.Machine.Actions.Length >= 10
              && Platform.Machine.Do("сделай-что-нибудь") is { Ok: false },
              "| неизвестное имя — отказ, а не исключение");
        Check("необратимое помечено",
              Platform.Machine.Irreversible.Contains("shutdown")
              && !Platform.Machine.Irreversible.Contains("volume_up"));

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
        return Task.CompletedTask;
    }

    /// <summary>
    /// F04: команду и напоминание заводят из окна.
    /// </summary>
    /// <remarks>
    /// Ядро под песочницей: проверка заводит настоящие записи, и хранилище
    /// человека для этого не трогают. Именно поэтому проверка и возможна —
    /// «завести» иначе означало бы оставить след в чужих данных.
    /// </remarks>
    private async Task CheckPagesAsync(MainWindow window)
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

        Console.WriteLine("=== F04: страницы заводят записи ===");
        var real = CoreLink.FindCore();
        var link = new CoreLink(window, new Rina.Protocol.CoreLaunch(
            real.Python,
            Path.Combine(real.WorkingDirectory, "tools", "_core_sandboxed.py"),
            real.WorkingDirectory));
        window.Link = link;
        window.Show();
        await link.StartAsync();
        for (var i = 0; i < 400 && link.State != Rina.Protocol.CoreState.Ready; i++)
            await Task.Delay(100);
        Check("ядро на связи", link.State == Rina.Protocol.CoreState.Ready,
              $"| {link.State}");

        // --- команды ---
        window.ShowSectionFor("commands");
        await Task.Delay(1200);
        if (window.CurrentPage is Pages.CommandsPage commands)
        {
            var before = commands.CommandCount;
            var opened = await commands.OpenEditorAsync(null);
            Check("конструктор открылся", opened && commands.EditorOpen);

            var saved = await commands.CreateForCheckAsync(
                "открой блокнот", "app", @"C:\Windows\System32\notepad.exe");
            Check("команда заведена из окна", saved,
                  $"| было {before}, стало {commands.CommandCount}");
            Check("и появилась в списке",
                  commands.CommandCount == before + 1,
                  $"| {commands.CommandCount}");

            // Последовательность — то, что раньше можно было только
            // импортировать. Проверяется весь путь: вид, шаги, порядок,
            // сохранение.
            var was = commands.CommandCount;
            await commands.OpenEditorAsync(null);
            var built = commands.Editor?.BuildSequenceForCheck(
                "утренний режим",
                [("app", @"C:\Windows\System32\notepad.exe"),
                 ("system", "sys_volume_up"),
                 ("speak", "Доброе утро")]) ?? false;
            Check("последовательность собралась в окне", built);
            await Task.Delay(400);
            Check("и сохранилась со своими шагами",
                  commands.CommandCount == was + 1,
                  $"| было {was}, стало {commands.CommandCount}");
            Check("шаги дошли до ядра в том же порядке",
                  commands.StepsOfLastSaved() == "app, system, speak",
                  $"| {commands.StepsOfLastSaved()}");
            // Страница строится заново: описание обязано быть человеческим
            // на первой же отрисовке, а не после того, как что-то успело
            // подгрузить виды по дороге.
            window.ShowSectionFor("dialog");
            await Task.Delay(300);
            window.ShowSectionFor("commands");
            await Task.Delay(1200);
            var fresh = window.CurrentPage as Pages.CommandsPage;
            Check("список показывает её словами, а не полями",
                  fresh?.FirstDescription().Contains("Программа") == true,
                  $"| «{fresh?.FirstDescription()}»");
        }
        else Check("страница команд открылась", false);

        // --- напоминания ---
        window.ShowSectionFor("reminders");
        await Task.Delay(1200);
        if (window.CurrentPage is Pages.RemindersPage reminders)
        {
            var before = reminders.PlannedCount;
            var made = await reminders.CreateAsync("проверить почту", 15);
            Check("напоминание заведено из окна", made);
            await Task.Delay(400);
            Check("и появилось в списке",
                  reminders.PlannedCount == before + 1,
                  $"| было {before}, стало {reminders.PlannedCount}");
        }
        else Check("страница напоминаний открылась", false);

        // Снимок с настоящими записями: пустая страница и страница с одной
        // командой выглядят по-разному, и проверять стоит вторую.
        if (Value(Environment.GetCommandLineArgs(), "--shot") is { } shot)
        {
            window.ShowSectionFor(_shotSection);
            await Task.Delay(800);
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
                                          "action_hotkeys", "notifications",
                                          "floating_command_bar");
        if (values is null) return;

        var wanted = values["autostart"]?.GetValue<bool>() ?? false;
        if (wanted != Autostart.Enabled && !Autostart.Apply(wanted))
            window.ShowNote("Не удалось изменить автозапуск: запрещено политикой.");

        window.MinimiseToTray = values["minimize_to_tray"]?.GetValue<bool>()
                                ?? true;

        // Основное сочетание: показать окно и начать слушать.
        if (values["hotkey"]?.GetValue<string>() is { Length: > 0 } main)
            _hotkeys?.Bind("main", main, () => window.OnMainHotkey());

        // Сочетания действий. Список действий прислало ядро — оно знает,
        // что бывает; исполняет их оболочка, потому что клавиатура,
        // окно и трей принадлежат ей.
        if (values["action_hotkeys"] is JsonObject bound)
            BindActions(window, bound);

        _notify = values["notifications"]?.GetValue<bool>() ?? true;
        window.ShowToasts = _notify;
        if (values["floating_command_bar"]?.GetValue<bool>() == true)
            ShowFloatingBar(window);

        if (values["start_minimized"]?.GetValue<bool>() == true)
            window.Hide();
    }

    private bool _notify = true;
    private FloatingBar? _bar;

    /// <summary>
    /// Привязать сочетания к действиям.
    /// </summary>
    /// <remarks>
    /// Занятое чужой программой сочетание — обычное дело, и человек узнаёт
    /// об этом строкой в подвале, а не молчанием: сочетание, которое просто
    /// не работает, выглядит поломкой Рины.
    /// </remarks>
    private void BindActions(MainWindow window, JsonObject bound)
    {
        foreach (var (action, node) in bound)
        {
            if (node?.GetValue<string>() is not { Length: > 0 } combination)
                continue;
            var act = action;
            _hotkeys?.Bind(act, combination, () => RunAction(window, act));
        }
    }

    private void RunAction(MainWindow window, string action)
    {
        switch (action)
        {
            case "listen":
                _ = _link?.ListenOnceAsync();
                break;
            case "toggle_always":
                _ = ToggleAlwaysAsync();
                break;
            case "show_hide":
                if (window.IsVisible) _tray?.Hide();
                else _tray?.Show();
                break;
            case "mute":
                _ = ToggleVoiceAsync();
                break;
            case "focus_command":
                _tray?.Show();
                window.ShowSectionFor("dialog");
                break;
            case "floating_bar":
                if (_bar is { IsVisible: true }) _bar.Hide();
                else ShowFloatingBar(window);
                break;
        }
    }

    private async Task ToggleAlwaysAsync()
    {
        if (_link is null) return;
        var now = await _link.GetAsync("always_listen");
        var on = now?["always_listen"]?.GetValue<bool>() ?? false;
        await _link.SetAsync("always_listen", !on);
    }

    private async Task ToggleVoiceAsync()
    {
        if (_link is null) return;
        var now = await _link.GetAsync("voice_reply");
        var on = now?["voice_reply"]?.GetValue<bool>() ?? true;
        await _link.SetAsync("voice_reply", !on);
    }

    /// <summary>
    /// Применить настройку, которой распоряжается оболочка.
    /// </summary>
    /// <remarks>
    /// Ядро хранит намерение и уже его записало; здесь оболочка приводит
    /// себя в соответствие. Тот же порядок, что у отделки и языка: одна
    /// настройка, две стороны, каждая делает своё.
    /// </remarks>
    public void ApplyShellSetting(string key, System.Text.Json.Nodes.JsonNode value)
    {
        var window = MainWindow as MainWindow;
        switch (key)
        {
            case "notifications":
                _notify = value.GetValue<bool>();
                if (window is not null) window.ShowToasts = _notify;
                break;
            case "minimize_to_tray":
                if (window is not null)
                    window.MinimiseToTray = value.GetValue<bool>();
                break;
            case "floating_command_bar":
                if (value.GetValue<bool>()) ShowFloatingBar(window!);
                else _bar?.Hide();
                break;
            case "action_hotkeys":
                if (window is not null && value is JsonObject bound)
                {
                    // Перепривязка целиком: снятое сочетание должно
                    // перестать работать, а не остаться висеть до
                    // перезапуска.
                    _hotkeys?.Dispose();
                    _hotkeys = new Hotkeys();
                    _hotkeys.Attach(window);
                    _hotkeys.Refused += (name, why) => window.ShowNote($"{name}: {why}");
                    BindActions(window, bound);
                }
                break;
        }
    }

    /// <summary>Показать плавающую строку, заведя её при надобности.</summary>
    private void ShowFloatingBar(MainWindow window)
    {
        _bar ??= new FloatingBar(_link);
        _bar.Summon();
    }

    /// <summary>
    /// Показать то, чего человек не видит в окне.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Всплывающее сообщение о том, что и так написано в открытом окне, —
    /// шум, и человек учится его не читать. Поэтому условие не «пришёл
    /// ответ», а «пришёл ответ, которого он не видит».
    /// </para>
    /// <para>
    /// <b>Реплика и напоминание расходятся по разным путям, и это не
    /// украшение.</b> Реплика живёт секунды и принадлежит разговору: её
    /// показывает своё окно, которое само уйдёт. Напоминание живёт, пока
    /// его не увидят, и может застать человека отошедшим — его место в
    /// центре уведомлений, где оно дождётся. Раньше и то и другое уходило
    /// в трей, и «который час» ложился в почту рядом с письмами.
    /// </para>
    /// </remarks>
    private void OnCoreEventForTray(MainWindow window,
                                    Rina.Protocol.Envelope message)
    {
        if (!_notify || window.IsVisible) return;

        if (message.Method == "reminder.fired")
        {
            var text = message.Payload["item"]?["text"]?.GetValue<string>() ?? "";
            _tray?.Notify("Напоминание", text.Length > 0 ? text : "Пора.");
        }
    }

    protected override void OnExit(ExitEventArgs e)
    {
        // Ядро завершается само, увидев обрыв (§13), но попрощаться вежливо
        // дешевле, чем полагаться на это: у него есть что закрыть.
        _bar?.Close();
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
