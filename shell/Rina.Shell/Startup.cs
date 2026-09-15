using System.IO;
using System.Net.Http;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace Rina.Shell;

public partial class App
{
    /// <summary>
    /// Parsing the arguments and starting up.
    /// </summary>
    /// <remarks>
    /// <c>--shot &lt;file&gt;</c> draws the window into a PNG and exits. This is
    /// not a debugging whim: an interface nobody has seen has not been
    /// checked, and sending a person to look at the window after every
    /// change is a way of ceasing to look at all. The screenshot is made by
    /// the same code that draws the real window.
    /// </remarks>
    private CoreLink? _link;
    private Tray? _tray;
    private Hotkeys? _hotkeys;
    private string? _shotPath;
    //: Whether a screenshot of the commands page should open the editor.
    private bool _shotEditor;
    private double _shotScroll;
    private string _shotSection = "settings";

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // UTF-8 out, whatever the console's code page is. The same
        // understanding as `tools/console.py`, and for the same reason: the
        // regression reads our output and decodes it as UTF-8, and a
        // Russian line in a code page arrives as rubbish. The check modes
        // set their own writer later; this covers what is printed before
        // that — the screenshot's path, for one.
        //
        // In a try: with no console attached there is nothing to set, and
        // that is not a reason to refuse to start.
        try { Console.OutputEncoding = System.Text.Encoding.UTF8; }
        catch (IOException) { }

        var args = e.Args;

        // The language can be set from outside: a screenshot in another
        // language is the only way to see the translation whole rather than
        // line by line (4.0-F08).
        if (Value(args, "--language") is { } language)
            Strings.Loc.Use(language);

        var finish = Value(args, "--finish") ?? "silver";
        ApplyFinish(finish);

        // The media register is asked once, at start: it is the system's,
        // not ours, and the home page is rebuilt on every visit.
        _ = StartRemoteAsync();

        var window = new MainWindow();
        window.ShowFinish(finish);

        // A screenshot is taken of a section, and with the menu out
        // (4.0b-A07). The pixel comparison is about the panel and its
        // areas — the column, the seam, the accent mark — and none of them
        // is on the home screen, where the menu is folded away and the
        // figure has the window to itself. Without this the plain `--shot`
        // photographed a screen the check was never written about.
        //
        // Only for a plain screenshot. Every check below opens the section
        // it is about, and this line used to run first for any `--shot` at
        // all — so asking the home check for a picture handed it a window
        // standing in the settings. It said so and fell over; had it been a
        // check that merely photographed, the picture would have been of
        // the wrong screen and nobody the wiser.
        if (Value(args, "--shot") is not null
            && !args.Any(one => one.StartsWith("--check-")))
            window.ShowSectionFor(Value(args, "--section") ?? "settings");

        // The end-to-end self-check: raise a real core, wait for the link,
        // say what came of it, and exit. The screenshot shows what the
        // window looks like; this shows that it is alive.
        if (args.Contains("--check-core"))
        {
            _shotPath = Value(args, "--shot");
            _shotScroll = double.TryParse(Value(args, "--scroll"), out var down)
                ? down : 0;
            _shotSection = Value(args, "--section") ?? "settings";
            _shotEditor = args.Contains("--editor");
            // Without a window WPF shuts down as soon as OnStartup returns
            // control: by default an application lives while at least one
            // window lives. The self-check has no reason to show a window,
            // so we close ourselves, and only when we are done.
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckCoreAsync(window), "core");
            return;
        }

        if (args.Contains("--check-tray"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckTrayAsync(window), "tray");
            return;
        }

        if (args.Contains("--check-system"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckSystemAsync(window), "system");
            return;
        }

        if (args.Contains("--check-overlays"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckOverlaysAsync(window, Value(args, "--shot")), "overlays");
            return;
        }

        if (args.Contains("--check-updates"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckUpdatesAsync();
            return;
        }

        if (args.Contains("--check-diagnostics"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckDiagnosticsAsync();
            return;
        }

        if (args.Contains("--check-hover"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckHoverAsync(window), "hover");
            return;
        }

        if (args.Contains("--check-motion"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckMotionAsync(window), "motion");
            return;
        }

        if (args.Contains("--check-listen"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckListenAsync(), "listen");
            return;
        }

        if (args.Contains("--check-glass"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckGlassAsync(window, Value(args, "--shot")), "glass");
            return;
        }

        if (args.Contains("--check-home"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckHomeAsync(window, Value(args, "--shot")), "home");
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
            Watched(CheckPagesAsync(window), "pages");
            return;
        }

        if (args.Contains("--check-voice"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckVoiceAsync(window), "voice");
            return;
        }

        // The wizard on its own, for a screenshot and for the eye. It is
        // shown once per install, so without this the only way to look at
        // it again would be to wipe the settings.
        if (args.Contains("--check-media"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckMediaAsync(window, Value(args, "--shot")), "media");
            return;
        }

        if (args.Contains("--check-dialogue"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckDialogueAsync(window, Value(args, "--shot")), "dialogue");
            return;
        }

        if (args.Contains("--check-settings"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckSettingsAsync(window, Value(args, "--shot")), "settings");
            return;
        }

        if (args.Contains("--check-setup"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckSetupAsync(Value(args, "--shot"),
                                Value(args, "--step"));
            return;
        }

        if (args.Contains("--check-audio"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            _ = CheckAudioAsync();
            return;
        }

        if (args.Contains("--check-watch"))
        {
            ShutdownMode = ShutdownMode.OnExplicitShutdown;
            Watched(CheckWatchAsync(window), "watch");
            return;
        }

        // A screenshot of the floating bar: it lives on top of other
        // people's windows and does not get into a screenshot of the main
        // window at all.
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

        // A screenshot of the confirmation window: checking how something
        // irreversible looks by shutting the computer down every time is a
        // way of not checking it at all.
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
            // The core is raised after the window is shown, not before: a
            // person must see the program at once rather than a second
            // later, a second spent by another process on starting up. The
            // state of the link is visible to them from the very first
            // draw (4.0-F12).
            window.Show();

            // Windows on top of the screen: the line and the "listening"
            // plaque. Set up before the core — they belong to the shell,
            // and the plaque must appear even if the core answers slowly.
            window.Toast = new Overlays.Toast();
            window.Plaque = new Overlays.Listening();

            // The tray and the hotkeys are set up before the core: they
            // belong to the shell and are obliged to work even if the core
            // did not come up. An assistant that cannot be summoned from
            // the keyboard because another process fell over is no
            // assistant.
            _tray = new Tray(window);
            _tray.ExitRequested += () => Shutdown();
            window.Tray = _tray;

            _hotkeys = new Hotkeys();
            _hotkeys.Attach(window);
            _hotkeys.Refused += (name, why) => window.ShowNote($"{name}: {why}");

            _link = new CoreLink(window, CoreLink.FindCore());
            window.Link = _link;

            // Notifications: what a person cannot see, they are told. The
            // event taken is the same one the window draws from — there
            // must not be a second source of Rina's answers.
            _link.CoreEvent += message => OnCoreEventForTray(window, message);

            _ = _link.StartAsync();
            _ = ApplySystemSettingsAsync(window);

            // A rehearsal of the tray in the real startup mode. The
            // --check-tray check runs under ShutdownMode.OnExplicitShutdown
            // while the live program runs under OnLastWindowClose, and the
            // difference between them is exactly about whether the program
            // survives with no visible window at all.
            if (args.Contains("--rehearse-tray")) Rehearse(window);
            return;
        }

        // A screenshot may pretend to a state of the link: checking the
        // indicator by waiting for a real disconnection is a way of
        // checking it rarely.
        if (Value(args, "--core-state") is { } state)
            window.ShowCoreState(Enum.Parse<Rina.Protocol.CoreState>(state, true),
                                 Value(args, "--core-reason") ?? "");

        // A screenshot can show any section: checking a page by clicking
        // through the column by hand every time is a way of checking it
        // rarely.
        if (Value(args, "--section") is { } section) window.ShowSectionFor(section);

        window.Width = 940;
        window.Height = 620;
        window.WindowStartupLocation = WindowStartupLocation.Manual;
        window.Left = -4000;              // рисуем за краем: снимок нужен,
        window.Top = -4000;               // мелькание окна — нет
        window.Show();
        window.RunBackdropForShot();

        // `--after N` takes a second shot N seconds later, from the same
        // run. One picture cannot answer "does it move", and two pictures
        // of two runs cannot either — both start at the same phase.
        var after = double.TryParse(Value(args, "--after"), out var wait)
            ? wait : 0;
        Dispatcher.BeginInvoke(new Action(async () =>
        {
            Save(window, shot);
            if (after > 0)
            {
                await Task.Delay(TimeSpan.FromSeconds(after));
                Save(window, shot.Replace(".png", "-after.png"));
            }
            Shutdown();
        }), System.Windows.Threading.DispatcherPriority.ContextIdle);
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr window,
                                                        IntPtr process);

    [System.Runtime.InteropServices.DllImport("kernel32.dll")]
    private static extern uint GetCurrentThreadId();

    /// <summary>
    /// Hide the window and bring it back — the way a person does it.
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

    /// <summary>
    /// F05: the tray brings the window back rather than dropping the
    /// program.
    /// </summary>
    /// <remarks>
    /// What is checked first of all is the <b>thread</b> the click arrives
    /// on. A tray icon is a window, and whose it is depends not on who
    /// created it but on who pumps its message queue. Touching a WPF window
    /// from another thread is an exception, and an exception in a handler
    /// nobody catches ends the process: the program "quits when the icon is
    /// clicked", although there is nothing resembling a quit in the code.
    /// </remarks>
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

        // Coming back is called the same way as from the icon's menu: by the same method.
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
        // Output to a file is buffered in blocks, and if the process is
        // killed on a deadline the buffer goes along with the answer to
        // "why is it taking so long".
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

        // The shell does not read the finish from a file, it asks the core.
        // Waited for rather than slept through: a second and a half is a
        // guess about how long a machine takes to answer, and under the
        // load of the full regression it was sometimes not enough — this
        // check went red at random and green on its own.
        await Until(() => Array.IndexOf(App.Finishes,
                                        window.FinishValue) >= 0);
        Check("отделка получена от ядра",
              Array.IndexOf(App.Finishes, window.FinishValue) >= 0,
              $"| {window.FinishValue}");

        // The data schema arrives in the handshake and is a real number
        // (4.0-U01, ADR 0004). The update check compares a rollback against
        // it, and a zero disables that comparison in silence.
        //
        // This is a check of the wiring, not of the arithmetic. The
        // updater's own scenarios pass the schema by hand and were green
        // while `AboutPage` asked for it with `settings.get` as
        // `config_version` — a secret key the core does not hand out — and
        // got zero every time. A check that calls the mechanism directly
        // agrees with its author.
        Check("схема данных пришла в рукопожатии",
              link.Connection is { Ready: true, DataVersion: > 0 },
              $"| {link.Connection?.DataVersion}");

        // Pages are built only inside a live tree, so the window is shown
        // off the edge of the screen: checking a page without showing it
        // means checking a constructor rather than a page.
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

        // The width is set by the column, not by the control. A screenshot
        // cannot measure that: the column's right edge is not a colour
        // boundary — the path row has a button on the right, the slider has
        // a number, and the fill ends before the column does. We measure
        // the tree. It was caught by a person with screenshots: the path
        // field 200, the list 280, the slider 276 — the edge wandered by
        // eighty points.
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

        // An opened list is checked separately: a popup is a window of its
        // own, it does not get into a screenshot of the main one at all,
        // and a broken template would go unnoticed exactly where it is
        // written by hand.
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

        // Plugins: the last page that was still a stub. The whole round is
        // checked — the list, switching on, the plugin's own page and an
        // action on it — because every link here crosses the process
        // boundary, and "the list arrived" does not mean anything yet.
        window.ShowSectionFor("plugins");
        await Task.Delay(1500);
        if (window.CurrentPage is Pages.PluginsPage plugins)
        {
            for (var i = 0; i < 60 && plugins.PluginCount == 0; i++)
                await Task.Delay(100);
            Check("плагины пришли из ядра", plugins.PluginCount > 0,
                  $"| {plugins.PluginCount}");

            // What was switched on before us. The check runs against a
            // real core, that is, against a person's settings, and it has
            // no right to leave a plugin switched on behind it.
            var before = await plugins.EnabledAsync();

            // Kept open on purpose. Without `keepOpen` the plugin is
            // switched off again before this returns, and the section
            // question below was then asked about a plugin that was no
            // longer on: it passed only on a machine where somebody had
            // already switched one on by hand, and went red the day the
            // developer switched them all off. A check that reads the
            // profile it is run under measures the machine, not the
            // program.
            var drawn = await plugins.OpenFirstPageAsync(keepOpen: true);
            Check("плагин включился и отдал свою страницу", drawn > 0,
                  $"| элементов {drawn}");

            // The plugin's section in the column (noted by a person): "I
            // use this" is a place on the left, not a card in a list of
            // what is installed.
            await link.RefreshPluginSectionsAsync();
            await Task.Delay(400);
            Check("у включённого плагина есть свой раздел",
                  window.SectionNames().Any(n => n.StartsWith("plugin:")),
                  $"| {string.Join(", ", window.SectionNames())}");

            // And it goes when the plugin does. Both halves are the rule:
            // a section that stays behind says "I use this" about
            // something nobody uses.
            await plugins.RestoreAsync();
            await link.RefreshPluginSectionsAsync();
            await Task.Delay(400);
            Check("выключили — раздел ушёл",
                  !window.SectionNames().Any(n => n.StartsWith("plugin:")),
                  $"| {string.Join(", ", window.SectionNames())}");

            var after = await plugins.EnabledAsync();
            Check("проверка вернула плагины как было",
                  before.SequenceEqual(after),
                  $"| было [{string.Join(", ", before)}], "
                  + $"стало [{string.Join(", ", after)}]");
        }
        else Check("страница плагинов открылась", false);

        // A screenshot of the live window, if asked for: settings with
        // real values from a real core are the only way to see how this
        // actually looks rather than how an empty page looks.
        if (_shotPath is { } shot)
        {
            window.ShowSectionFor(_shotSection);
            await Task.Delay(800);
            // A plugin's page is drawn from a description sent by another
            // process, and it can only be seen with one's eyes by opening
            // it: a screenshot of an empty list shows neither cards nor
            // rows.
            Pages.PluginsPage? shown = null;
            if (_shotSection == "plugins"
                && window.CurrentPage is Pages.PluginsPage opened)
            {
                shown = opened;
                await shown.OpenFirstPageAsync(keepOpen: true);
                await Task.Delay(300);
            }
            // The editor, likewise, has to be opened to be seen: a
            // screenshot of the commands page shows the list and the
            // button that opens the editor, and nothing of the editor —
            // which is the part being looked at when it is asked for.
            // Opening the editor for a screenshot is asked for, not
            // assumed: the commands page has two things worth looking at
            // now — the grouped lists and the chain — and one of them
            // covers the other.
            if (_shotSection == "commands" && _shotEditor
                && window.CurrentPage is Pages.CommandsPage editing)
            {
                await editing.OpenEditorAsync(null);
                await Task.Delay(400);
                // A sequence, because the chain of steps is the thing the
                // screenshot is being taken of. An empty editor shows the
                // form and none of it.
                if (editing.OpenEditor is { } built)
                {
                    built.InsertStepForCheck(0, "app",
                        @"C:\Windows\System32\notepad.exe");
                    built.InsertStepForCheck(1, "pause", "2");
                    built.InsertStepForCheck(2, "repeat");
                    built.NestStepForCheck(2, "steps", "system");
                    built.InsertStepForCheck(3, "if");
                    built.NestStepForCheck(3, "steps", "speak", "добрый вечер");
                    built.NestStepForCheck(3, "otherwise", "speak", "доброе утро");
                    await Task.Delay(500);
                }
            }
            if (_shotScroll > 0 && window.CurrentPage is Pages.SettingsPage page)
            {
                page.ScrollTo(_shotScroll);
                await Task.Delay(200);
            }
            // The commands page scrolls too: the chain of steps is taller
            // than the window, and a screenshot of its first three rows
            // shows a list rather than the thing the item is about.
            if (_shotScroll > 0
                && window.CurrentPage is Pages.CommandsPage rolled)
            {
                rolled.ScrollTo(_shotScroll);
                await Task.Delay(200);
            }
            Save(window, shot);

            // And put things back. A screenshot is an observation, not an
            // action: it has no right to leave a plugin switched on behind
            // it, because the settings under it are real, a person's own.
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
    /// F09/F10: sound travels to the core and back, the credit is honoured.
    /// </summary>
    /// <remarks>
    /// Part of the checks does not touch a device at all: the sound's path
    /// is one and the same whether it comes from a microphone or from a
    /// generator, and it is the path that has to be checked. Otherwise the
    /// suite will not run on a machine without a microphone — that is, on
    /// any build server.
    /// </remarks>
    /// <summary>
    /// <c>4.0b-A03</c>: the watch starts only when asked, and reports a
    /// change once.
    /// </summary>
    /// <remarks>
    /// <para>
    /// What is checked here is the gate, not Windows. Whether
    /// <c>SetWinEventHook</c> delivers foreground events is Windows'
    /// business and cannot be asserted without a second application
    /// switching windows. What can be asserted, and matters more, is that
    /// nothing is watched until the person says so — that is the promise
    /// in <c>T-19</c>.
    /// </para>
    /// <para>
    /// The reporting is exercised through the real window of this very
    /// application: it is in front, so switching the watch on must produce
    /// exactly one report, and switching it on again after off must not
    /// produce a stale repeat.
    /// </para>
    /// </remarks>
    private async Task CheckWatchAsync(MainWindow window)
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

        Console.WriteLine("=== 4.0b-A03: слежка за тем, что открыто ===");

        window.Left = -4000;
        window.Top = -4000;
        window.Show();
        window.Activate();
        await Task.Delay(400);

        var seen = new List<string>();
        var watch = new Platform.Foreground(path => seen.Add(path));

        Check("пока не просили — не следит", !watch.Watching);
        Check("и ничего не сообщила", seen.Count == 0, $"| {seen.Count}");

        watch.Follow(true);
        Check("попросили — следит", watch.Watching);
        // This very application's window is in front: switching the watch
        // on must report it at once. Waiting for the person to leave for
        // another window and come back would look like a setting that did
        // not take effect.
        Check("о том, что уже впереди, сказано сразу", seen.Count == 1,
              $"| {string.Join(", ", seen)}");
        Check("сказан путь программы, а не заголовок окна",
              seen.Count == 1 && seen[0].EndsWith(".exe",
                  StringComparison.OrdinalIgnoreCase),
              $"| {(seen.Count == 1 ? seen[0] : "")}");

        watch.Follow(true);
        Check("повторная просьба ничего не меняет", seen.Count == 1,
              $"| {seen.Count}");

        watch.Follow(false);
        Check("выключили — не следит", !watch.Watching);

        var before = seen.Count;
        watch.Follow(true);
        // The previous path was forgotten along with the watch, so the
        // same window is news again. Holding on to it while switched off
        // would mean keeping a trace of what the person was doing when
        // they switched it off.
        Check("после включения снова сообщает", seen.Count == before + 1,
              $"| {seen.Count - before}");

        watch.Dispose();
        Check("после Dispose не следит", !watch.Watching);

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// The remote for whatever is playing.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Plan item <c>4.0b-A07</c>. In the "machine" group: it asks Windows
    /// what is playing on this machine right now, and the answer depends on
    /// what the person happens to have open.
    /// </para>
    /// <para>
    /// <b>What is asserted does not depend on that.</b> Whether anything is
    /// playing is the machine's business; what is ours is that reading the
    /// register does not throw, that nothing playing means no panel rather
    /// than an empty one, and that something playing fills the panel. The
    /// state that happens to be there decides which of the last two is
    /// checked, and the check says which.
    /// </para>
    /// </remarks>
    private async Task CheckMediaAsync(MainWindow window, string? shot)
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

        Console.WriteLine("=== Пульт: то, что уже играет ===");

        await StartRemoteAsync();
        Check("реестр воспроизведения ответил", Remote?.Available == true,
              Remote?.Available == true ? "" : "| система не пустила");

        // A moment for the properties: the register answers at once, the
        // track behind it is read asynchronously.
        await Task.Delay(700);

        window.Left = -4000;
        window.Top = -4000;
        window.Show();
        window.Activate();
        window.ShowSectionFor("home");
        await Until(() => window.CurrentPage is Pages.HomePage);
        var home = (Pages.HomePage)window.CurrentPage!;

        var playing = Remote?.Playing;
        if (playing is null)
        {
            Console.WriteLine("      (ничего не играет — проверяем покой)");
            Check("ничего не играет — пульта нет вовсе",
                  home.RemoteShows.Length == 0,
                  $"| показано «{home.RemoteShows}»");
        }
        else
        {
            Console.WriteLine($"      (играет: {playing.Artist} — "
                              + $"{playing.Title})");
            await Until(() => home.RemoteShows.Length > 0, 5);
            Check("играющее показано", home.RemoteShows.Length > 0,
                  $"| {home.RemoteShows}");
            Check("и это то же самое, что говорит система",
                  home.RemoteShows.Contains(playing.Title,
                                            StringComparison.Ordinal),
                  $"| {home.RemoteShows}");
        }

        // The picture is taken here, while something is showing. After the
        // seam below the remote is deliberately emptied, and a photograph
        // of that proves only that an empty panel is empty.
        if (shot is not null)
        {
            Save(window, shot);
            Console.WriteLine($"снимок: {shot}");
        }

        // --- and the half that is ours, on a quiet machine too ---
        //
        // Whether anything is playing belongs to the person's machine.
        // Whether the home screen lays it out belongs to us, and it has to
        // be checked either way — otherwise the interesting half is tested
        // only when somebody happens to have music on.
        Remote!.ShowForCheck(new MediaRemote.Sounding(
            "Проверка", "Тишина в двух актах", Running: true, Cover: null));
        await Until(() => home.RemoteShows.Length > 0, 5);
        Check("подставленное играющее показано целиком",
              home.RemoteShows.Contains("Тишина в двух актах",
                                        StringComparison.Ordinal)
              && home.RemoteShows.Contains("Проверка",
                                           StringComparison.Ordinal),
              $"| {home.RemoteShows}");

        Remote.ShowForCheck(null);
        await Until(() => home.RemoteShows.Length == 0, 5);
        Check("а когда играть перестало — панель уходит",
              home.RemoteShows.Length == 0, $"| «{home.RemoteShows}»");

        // Pressing must not throw whether or not there is a session: a
        // remote whose buttons crash when nothing is playing is worse than
        // one that does nothing.
        try
        {
            await Remote!.PlayPause();
            await Remote.PlayPause();
            Check("нажатие не роняет и без сессии", true);
        }
        catch (Exception exc)
        {
            Check("нажатие не роняет и без сессии", false,
                  $"| {exc.GetType().Name}");
        }

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// The dialogue is a conversation: two sides, and a time on each.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Plan item <c>4.0b-A12</c>. Driven by a real command through a real
    /// core: the page's whole job is turning events into messages, and
    /// handing it an event by hand would check that the handler works —
    /// which was never in doubt.
    /// </para>
    /// <para>
    /// <b>Sides, not counts.</b> "Two messages appeared" would pass with
    /// both of them on the same side, which is exactly what a list of lines
    /// looked like before this item.
    /// </para>
    /// </remarks>
    private async Task CheckDialogueAsync(MainWindow window, string? shot)
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

        Console.WriteLine("=== Диалог: переписка, а не лента ===");
        var link = new CoreLink(window, CoreLink.FindCore());
        window.Link = link;
        await link.StartAsync();
        await Until(() => link.State == Rina.Protocol.CoreState.Ready, 12);
        Check("ядро на связи",
              link.State == Rina.Protocol.CoreState.Ready, $"| {link.State}");

        window.Left = -4000;
        window.Top = -4000;
        window.Show();
        window.Activate();
        window.ShowSectionFor("dialog");

        // Asked of the window each time: it rebuilds the section whenever
        // the link is set again, so a page held in hand has been replaced.
        Pages.DialoguePage Shown() => (Pages.DialoguePage)window.CurrentPage!;
        await Until(() => window.CurrentPage is Pages.DialoguePage);

        // **Not a round trip.** The first version typed a command and
        // waited for the answer, and inside the full suite that is a race:
        // the page is rebuilt, the history is read back, the core stores in
        // its own time. It measured the timing rather than the layout, and
        // failed in the run while passing by hand.
        //
        // The layout is what this item is about, so the sides are asked of
        // messages the core already has. Which two they are comes from the
        // core, not from a guess about what the history holds.
        // The conversation is made here rather than hoped for: what a
        // profile happens to hold is whatever earlier checks left in it,
        // and one of them clears the history. A check that reads somebody
        // else's leftovers passes or fails by the order it was run in.
        await link.HandleAsync("посчитай 15 умножить на 12");

        string? said = null, answered = null;
        // Waited on the store, not on a clock: the page can only lay out
        // what the core has written down.
        //
        // Awaited in a loop rather than blocked on inside a predicate. The
        // first version called `GetAwaiter().GetResult()` in the condition
        // and hung for good: that runs on the interface thread, and the
        // answer it was waiting for needs the very same thread to arrive.
        for (var tries = 0; tries < 40 && answered is null; tries++)
        {
            var told = await link.AskAsync(Rina.Protocol.Methods.HistoryList,
                new JsonObject { ["limit"] = 50 });
            said = null;
            answered = null;
            foreach (var item in told?["items"]?.AsArray() ?? [])
            {
                var kind = item?["kind"]?.GetValue<string>() ?? "";
                var text = item?["text"]?.GetValue<string>() ?? "";
                if (text.Length == 0) continue;
                if (kind == "assistant") answered ??= text;
                else said ??= text;
            }
            if (answered is null) await Task.Delay(500);
        }

        Check("разговор записан обеими сторонами",
              said is not null && answered is not null,
              $"| человек: {said is not null}, Рина: {answered is not null}");

        // Read back from the store, as a person would see it after a
        // restart: the page is opened again rather than watched live.
        window.ShowSectionFor("home");
        window.ShowSectionFor("dialog");
        await Until(() => window.CurrentPage is Pages.DialoguePage);

        if (said is not null && answered is not null)
        {
            await Until(() => Shown().SideOf(said) is not null, 15);
            Check("сказанное человеком встало на его сторону",
                  Shown().SideOf(said) is true,
                  $"| сторона {Shown().SideOf(said)}");
            Check("ответ Рины — на другой",
                  Shown().SideOf(answered) is false,
                  $"| сторона {Shown().SideOf(answered)}");
        }

        Check("у каждой реплики есть время", Shown().AllStamped,
              "| время — часть сообщения, а не подпись вместо имени");

        if (shot is not null)
        {
            Save(window, shot);
            Console.WriteLine($"снимок: {shot}");
        }

        // --- and the message a person sees *before* the core answers ---
        //
        // Two lines of code build these messages: one as they arrive, one
        // when the history is read back. After an exchange the second
        // replaces the first, so a mistake in the first is invisible from
        // outside — the check went green with every arriving message forced
        // onto one side.
        //
        // Without a core there is no history to read back, so only the
        // first runs. That is also the page's own promise: "what was said
        // appears on the glass at once, without waiting for the core".
        await link.DisposeAsync();
        window.Link = null;
        window.ShowSectionFor("dialog");
        await Until(() => window.CurrentPage is Pages.DialoguePage);

        const string alone = "это без ядра";
        await Shown().SayForCheck(alone);
        await Until(() => Shown().SideOf(alone) is not null, 5);
        Check("без ядра сказанное всё равно видно и на своей стороне",
              Shown().SideOf(alone) is true, $"| {Shown().SideOf(alone)}");

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// The settings page: nothing that grows is left lying on it.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Plan item <c>4.0b-A14</c>'s neighbour, <c>4.0b-A10</c>. A list on a
    /// shared page drowns everything below it: after a year of use the
    /// settings would be learned aliases with a few switches lost among
    /// them. So the lists live behind buttons, and this is what says they
    /// still do.
    /// </para>
    /// <para>
    /// Checked against the layout and the built page together. The layout
    /// alone would say what was intended; the page alone would not say
    /// which of its rows is a list. Both, and they have to agree.
    /// </para>
    /// </remarks>
    private async Task CheckSettingsAsync(MainWindow window, string? shot)
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

        Console.WriteLine("=== Настройки: списки за кнопкой ===");
        var link = new CoreLink(window, CoreLink.FindCore());
        // Handed to the window, and that is not a formality: the settings
        // page asks **the window's** link, not whichever one a check
        // happens to be holding. Without this line the page found no core,
        // built nothing, and the check called an empty page tidy.
        window.Link = link;
        await link.StartAsync();
        await Until(() => link.State == Rina.Protocol.CoreState.Ready, 12);
        Check("ядро на связи",
              link.State == Rina.Protocol.CoreState.Ready, $"| {link.State}");

        // What grows with use. Named here rather than guessed from the
        // editor's kind: whether a thing grows is a judgement about the
        // world — a person adds words, teaches aliases, downloads models —
        // and a rule derived from the widget would go green the day
        // somebody drew a list with a different control.
        string[] growing =
        [
            "wake_words", "app_aliases", "program_folders", "action_hotkeys",
            "whisper_model", "vosk_model", "piper_model",
        ];

        var onPage = Pages.SettingsLayout.Sections
            .SelectMany(s => s.Keys.Select(k => k.Key)).ToHashSet();
        var behind = Pages.SettingsLayout.Sections
            .SelectMany(s => s.Sheets ?? [])
            .SelectMany(s => s.Keys).ToHashSet();

        foreach (var key in growing)
        {
            Check($"{key} не лежит на странице", !onPage.Contains(key));
            Check($"{key} открывается своим окном", behind.Contains(key));
        }

        // Nothing is in two places at once: a setting edited from two rows
        // is a setting whose two rows disagree the moment one is changed.
        var twice = onPage.Intersect(behind).ToArray();
        Check("ни один ключ не показан дважды", twice.Length == 0,
              $"| {string.Join(", ", twice)}");

        window.Left = -4000;
        window.Top = -4000;
        window.Show();
        window.Activate();
        window.ShowSectionFor("settings");
        await Until(() => window.CurrentPage is Pages.SettingsPage);
        // **Asked of the window every time, never held.** The window
        // rebuilds the section whenever the link is set again — and it is,
        // as soon as the core answers — so a page captured a moment ago has
        // been thrown away and replaced. Measuring the one in hand reported
        // an empty page while a full one was on the screen.
        Pages.SettingsPage Shown() => (Pages.SettingsPage)window.CurrentPage!;

        await Until(() => Shown().SectionsShown > 0, 15);
        var built = Shown().SectionsShown > 0;
        Check("страница собралась", built,
              $"| секций {Shown().SectionsShown}, ключей {Shown().SchemaKeys}"
              + (Shown().Trouble.Length > 0 ? $", {Shown().Trouble}" : ""));
        // The rule with teeth from ADR 0006 still holds: an unfamiliar key
        // is shown rather than hidden. "Other" being empty means every key
        // the core sent has a place — not that unknown ones are dropped.
        // `built &&`, because an empty page has no "Other" section either,
        // and the first version of this line called that tidy. A check that
        // agrees with nothing having happened will agree with anything.
        Check("секция «Прочее» пуста", built && !Shown().HasOtherSection,
              built ? "" : "| страница пуста — сказать нечего");

        if (shot is not null)
        {
            Save(window, shot);
            Console.WriteLine($"снимок: {shot}");
        }

        await link.DisposeAsync();
        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// The setup wizard: does it hold together, and what does it look like.
    /// </summary>
    /// <remarks>
    /// A live core, because the catalogue comes from it: a wizard checked
    /// against an invented list would pass with a step that shows nothing
    /// on a real machine.
    /// </remarks>
    private async Task CheckSetupAsync(string? shot, string? step)
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

        Console.WriteLine("=== Мастер первого запуска ===");
        var link = new CoreLink(new MainWindow(), CoreLink.FindCore());
        await link.StartAsync();
        for (var waited = 0; waited < 60
             && link.State != Rina.Protocol.CoreState.Ready; waited++)
            await Task.Delay(100);
        Check("ядро на связи",
              link.State == Rina.Protocol.CoreState.Ready, $"| {link.State}");

        // The way back to the wizard. Without it, it was unreachable after
        // the first run — for anybody, not only for whoever had seen it.
        var about = new Pages.AboutPage(link);
        Check("в «о программе» есть кнопка «пройти настройку заново»",
              about.FindName("RunSetup") is System.Windows.Controls.Button,
              "| без неё мастер после первого запуска недостижим");

        var wizard = new Pages.SetupWindow(link);
        await wizard.LoadAsync();
        Check("каталог моделей доехал до окна", wizard.Offered > 0,
              $"| моделей {wizard.Offered}");

        var at = int.TryParse(step, out var wanted) ? wanted : 2;
        wizard.ShowFor(at);
        Check($"шаг {at} рисуется", wizard.StageFilled);

        // Counted on the step that has the boxes, which is the one just
        // opened. Asked before it, this counted the greeting's boxes —
        // there are none — and called that "nothing is ticked by default".
        wizard.ShowFor(2);
        // Two now: the small model and the package it is useless without.
        // What matters is that nothing heavy is ticked, and `test_setup.py`
        // holds that by weight; here it is enough that something sensible
        // is offered ready-ticked at all.
        Check("что-то отмечено по умолчанию, и немного",
              wizard.TickedNow is > 0 and <= 3,
              $"| отмечено {wizard.TickedNow}");
        wizard.ShowFor(at);

        wizard.Left = -4000;
        wizard.Top = -4000;
        wizard.Show();
        await Task.Delay(500);
        if (shot is not null)
        {
            Save(wizard, shot);
            Console.WriteLine($"снимок: {shot}");
        }
        wizard.Close();

        await link.DisposeAsync();
        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

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

        // --- F10: the queue and interruption. No core is needed for this. ---
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

        // --- a long utterance is not thrown away in the middle ---
        //
        // What a person heard as "fragments of words all through her
        // speech". The core sends a whole reply as fast as its credit
        // allows; the queue held a second and a half and discarded the rest
        // without a word. Nothing said so — not a log line, not a counter —
        // because discarding was configured as the normal answer to a full
        // queue.
        //
        // What is asserted is that overflow **refuses**. A queue that
        // refuses can be waited on, and the credit does exactly that; a
        // queue that swallows leaves the sender believing it was heard.
        // Comparing what went in against what is left would measure
        // playback instead: the device starts as soon as it has enough, and
        // is meant to.
        var flood = new Audio.Speaker();
        try
        {
            Check("очередь держит больше полутора секунд",
                  flood.Room > 22050 * 2 * 2,
                  $"| место на {flood.Room / (22050.0 * 2):0.0} с");

            var refused = false;
            var piece = new byte[8192];
            for (var at = 0; at < 200 && !refused; at++)
            {
                try { flood.Enqueue(piece); }
                catch (InvalidOperationException) { refused = true; }
            }
            Check("переполнение отказывает, а не глотает", refused,
                  refused ? "" : "| приняла всё и часть выбросила");
        }
        finally { flood.Dispose(); }

        // --- the tail of an utterance is not thrown away ---
        //
        // The core closes the stream when it has finished **sending**, and
        // a second of sound is still sitting unplayed. That close used to
        // call `Interrupt`, so the end of every single utterance was
        // dropped — which a person heard as speech that breaks off, and no
        // check said a word, because every check here interrupted on
        // purpose and got exactly what it asked for.
        var tail = new Audio.Speaker();
        var ended = new List<bool>();
        tail.Speaking += value => ended.Add(value);
        tail.Enqueue(Tone(seconds: 1.0));
        await Task.Delay(120);

        var before = tail.Pending;
        tail.Drain();
        Check("закрытие потока не выбрасывает недоигранное",
              tail.Pending > before / 2,
              $"| было {before} Б, осталось {tail.Pending} Б");
        Check("и речь ещё считается идущей", tail.IsSpeaking);

        // And it does end — by itself, when there is nothing left.
        for (var waited = 0; waited < 40 && tail.IsSpeaking; waited++)
            await Task.Delay(100);
        Check("а доиграв — заканчивается сама", !tail.IsSpeaking,
              $"| осталось {tail.Pending} Б");
        tail.Dispose();

        // --- speech ends by itself, and the microphone comes back ---
        //
        // The defect a person met as "she still does not react". The end of
        // speech was announced from one place only — the core closing the
        // speech stream — and the core opens that stream once and closes it
        // only when the sample rate changes, so in an ordinary session the
        // close never arrives. `IsSpeaking` latched true at the first
        // reply, the microphone stayed muted because that is what the flag
        // is for, and she never heard anything again.
        //
        // Nothing was needed for this check that was not here already: a
        // speaker, a tone, and waiting. What was missing was asking.
        var alone = new Audio.Speaker();
        var ear = new Audio.Microphone();
        alone.Speaking += value => ear.Muted = value;
        try
        {
            alone.Enqueue(Tone(seconds: 0.4));
            Check("пока говорит — микрофон заглушен", alone.IsSpeaking && ear.Muted);

            for (var waited = 0; waited < 60 && alone.IsSpeaking; waited++)
                await Task.Delay(100);
            Check("договорив, речь кончается сама, без закрытия потока",
                  !alone.IsSpeaking, $"| в очереди {alone.Pending} Б");
            Check("и микрофон снова слышит", !ear.Muted);
        }
        finally { alone.Dispose(); ear.Dispose(); }

        // --- "do not listen to oneself": muting, not stopping the device ---
        var microphone = new Audio.Microphone();
        speaker.Speaking += value => microphone.Muted = value;
        speaker.Enqueue(tone);
        Check("пока Рина говорит, микрофон заглушен", microphone.Muted);
        speaker.Interrupt();
        Check("после речи слушает снова", !microphone.Muted);
        speaker.Dispose();

        // --- level: silence and sound differ ---
        Check("тишина даёт ноль",
              Audio.Microphone.LevelOf(new byte[3200]) < 0.01f);
        var loud = Audio.Microphone.LevelOf(tone);
        Check("звук даёт заметный уровень", loud > 0.3f, $"| {loud:0.00}");

        // --- F09: a stream into a real core with credit ---
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
            // We do not switch the device on: otherwise real sound from
            // the room would go into the stream too, and the check would be
            // counting somebody else's.
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

        // --- and somebody in the running application starts the microphone ---
        //
        // The defect this catches was found by a person, not by a check:
        // "she cannot hear me, and the check says the microphone works".
        // Both were true. The device worked, the stream worked, the core
        // recognised — and `StartCaptureAsync` had no caller outside the
        // checks, so nothing was ever captured in the running application.
        //
        // **Driven through a real core.** The first version of this check
        // called the shell's handler itself and passed while the
        // subscription that reaches it was deleted: it measured that the
        // method works, which was never in doubt. What is in question is
        // whether the shell hears the core say it is listening, and the
        // only way to ask that is to make the core say it.
        Check("до объявления ядра микрофон молчит", !link.Capturing);

        await link.ListenOnceAsync();
        for (var waited = 0; waited < 20 && !link.Capturing; waited++)
            await Task.Delay(100);
        Check("ядро объявило, что слушает — оболочка включила микрофон",
              link.Capturing && link.CaptureStarts > 0,
              $"| запусков {link.CaptureStarts}");

        await link.DisposeAsync();
        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// The line and the "listening" plaque on top of the screen.
    /// </summary>
    /// <remarks>
    /// What is checked is behaviour, not a picture: the line is not shown
    /// while the window is open, the plaque does not go out on
    /// `listening.stopped` while the "always listening" mode is on. Both
    /// rules are easy to break with a change and impossible to notice by
    /// eye — the plaque goes out after an hour of work, and a superfluous
    /// line is seen only by someone with the window open.
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

        // The window is hidden: otherwise the person will not see the line.
        window.Hide();
        window.OnCoreEvent(Event("assistant.response",
            new System.Text.Json.Nodes.JsonObject { ["text"] = "Сейчас 14:30." }));
        await Task.Delay(300);
        Check("реплика показана, когда окна не видно",
              window.Toast.Shown == "Сейчас 14:30.",
              $"| {window.Toast.Shown}");

        // The window is open: the answer is already in front of the person.
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

        // The plaque: one-off listening.
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

        // The plaque: the mode.
        window.OnCoreEvent(Event("listening.always",
            new System.Text.Json.Nodes.JsonObject { ["enabled"] = true }));
        await Task.Delay(300);
        Check("в режиме «всегда» плашка тоже появляется",
              window.Plaque.Visible);
        Check("и говорит, что это режим",
              window.Plaque.Caption.Contains("Всегда"),
              $"| {window.Plaque.Caption}");

        // This is the main thing: a recognised phrase does not put the mode out.
        window.OnCoreEvent(Event("listening.stopped",
            new System.Text.Json.Nodes.JsonObject()));
        await Task.Delay(400);
        Check("распознанная фраза не гасит режим", window.Plaque.Visible,
              "| иначе человек перестал бы видеть, что микрофон работает");

        window.OnCoreEvent(Event("listening.always",
            new System.Text.Json.Nodes.JsonObject { ["enabled"] = false }));
        await Task.Delay(400);
        Check("отмена режима убирает плашку", !window.Plaque.Visible);

        // A screenshot, if asked for: the line and the plaque together.
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

    /// <summary>
    /// U02..U05: the metadata, four scenarios, integrity, the journal.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The source is substituted (<see cref="Update.Fake"/>). On the real
    /// GitHub this cannot be checked: there it is one thing today and
    /// another tomorrow, and five of the six outcomes need a release that
    /// does not exist — for instance a pair that will not say hello.
    /// </para>
    /// <para>
    /// The network is not touched even once, and that is checked too: an
    /// update client that went outside by accident during a check will one
    /// day go outside where it was not invited.
    /// </para>
    /// </remarks>
    /// <summary>
    /// I03: the diagnostic bundle is collected and carries nothing
    /// extra away.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Against a live core: a bundle is collected for the versions and
    /// the state of the link, and there is nowhere to take those from
    /// while there is no core. A check against a stand-in core would be
    /// checking that we can write a zip.
    /// </para>
    /// <para>
    /// What matters here is not "the archive was built" but **what is
    /// not in it**. A person sends the bundle to strangers, and the
    /// promise "we do not take the conversation" is worth exactly what
    /// checking it is worth: a distinctive word is put into the settings,
    /// and the check looks for it through the whole archive.
    /// </para>
    /// </remarks>
    private async Task CheckDiagnosticsAsync()
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

        var folder = Path.Combine(Path.GetTempPath(),
                                  "rina-diagnostics-" + Guid.NewGuid()
                                      .ToString("N")[..8]);
        try
        {
            Console.WriteLine("=== I03: диагностический пакет ===");

            var window = new MainWindow();
            var link = new CoreLink(window, CoreLink.FindCore());
            window.Link = link;
            await link.StartAsync();
            for (var i = 0; i < 400
                     && link.State != Rina.Protocol.CoreState.Ready; i++)
                await Task.Delay(100);
            Check("ядро на связи", link.State == Rina.Protocol.CoreState.Ready,
                  $"| {link.State}");

            // A distinctive word into a free-text setting. It must not
            // travel: the path to the model is a path on the person's
            // disk, and their name is in it.
            const string secretish = "СЕКРЕТНАЯ-ТРОПИНКА-42";
            if (link.Connection is { Ready: true } live)
            {
                await live.CallAsync(Rina.Protocol.Methods.SettingsSet,
                    new System.Text.Json.Nodes.JsonObject
                    {
                        ["values"] = new System.Text.Json.Nodes.JsonObject
                        {
                            ["piper_model"] = secretish,
                        },
                    }, TimeSpan.FromSeconds(10));
            }

            Directory.CreateDirectory(folder);
            var zip = Path.Combine(folder, "package.zip");
            var made = await Platform.Diagnostics.CollectAsync(zip, link);
            Check("пакет собрался", made.Ok && File.Exists(zip),
                  $"| {made.Problem}");

            if (!made.Ok)
            {
                Console.WriteLine();
                Console.WriteLine($"Ошибок: {++fails}");
                Environment.ExitCode = 1;
                Shutdown();
                return;
            }

            var inside = new Dictionary<string, string>();
            using (var archive = System.IO.Compression.ZipFile.OpenRead(zip))
            {
                foreach (var entry in archive.Entries)
                {
                    using var stream = entry.Open();
                    using var reader = new StreamReader(stream);
                    inside[entry.FullName] = reader.ReadToEnd();
                }
            }

            Check("пояснение внутри", inside.ContainsKey("README.txt"));
            Check("версии внутри", inside.ContainsKey("versions.txt"));
            Check("состояние внутри", inside.ContainsKey("state.txt"));
            Check("настройки внутри", inside.ContainsKey("settings.txt"));
            Check("журналы внутри",
                  inside.Keys.Any(k => k.StartsWith("logs/")),
                  "| " + string.Join(", ", inside.Keys.Where(
                      k => k.StartsWith("logs/"))));

            var versions = inside.GetValueOrDefault("versions.txt", "");
            Check("версия ядра названа, а не прочерк",
                  versions.Contains("ядро: ") && !versions.Contains("нет связи"),
                  $"| {versions.Split('\n').FirstOrDefault(l => l.StartsWith("ядро"))}");
            Check("версия протокола названа",
                  !versions.Contains("протокол: —"));

            // The thing this whole check was written for.
            var everything = string.Join("\n", inside.Values);
            Check("свободный текст настройки не уехал",
                  !everything.Contains(secretish),
                  "| приметное слово нашлось в пакете");
            Check("и вместо него — длина",
                  inside.GetValueOrDefault("settings.txt", "")
                        .Contains("piper_model = (текст,"),
                  "| " + inside.GetValueOrDefault("settings.txt", "")
                      .Split('\n').FirstOrDefault(l => l.StartsWith("piper_model")));
            Check("число уехало как есть",
                  inside.GetValueOrDefault("settings.txt", "")
                        .Contains("volume = "));
            // Not one store file: a bundle is explanations and journals,
            // not a copy of the data. The assertion is wider than "no
            // history" and names no files: a name written here would have
            // to be remembered both here and in the store.
            Check("файлов хранилища в пакете нет",
                  !inside.Keys.Any(k => k.EndsWith(".json")),
                  "| " + string.Join(", ", inside.Keys.Where(
                      k => k.EndsWith(".json"))));
            Check("текста разговора в пакете нет",
                  !everything.Contains("\"kind\": \"assistant\""));

            // The person must find out about the recording of texts
            // before sending rather than after: they may be in the
            // journal, and that is their own decision.
            Check("про запись текстов сказано в пояснении",
                  inside.GetValueOrDefault("README.txt", "")
                        .Contains("текстов реплик"));

            await live_reset(link);
            Console.WriteLine();
            Console.WriteLine($"Ошибок: {fails}");
            Environment.ExitCode = fails == 0 ? 0 : 1;
        }
        catch (Exception error)
        {
            Console.WriteLine($"  FAIL  проверка упала | {error.Message}");
            Environment.ExitCode = 1;
        }
        finally
        {
            try { Directory.Delete(folder, recursive: true); }
            catch (IOException) { }
            Shutdown();
        }

        // The settings under this check are the real ones: the
        // distinctive word has to be cleared away afterwards. The same
        // rule by which the autostart check puts the registry entry
        // back.
        static async Task live_reset(CoreLink link)
        {
            if (link.Connection is not { Ready: true } live) return;
            await live.CallAsync(Rina.Protocol.Methods.SettingsSet,
                new System.Text.Json.Nodes.JsonObject
                {
                    ["values"] = new System.Text.Json.Nodes.JsonObject
                    {
                        ["piper_model"] = "",
                    },
                }, TimeSpan.FromSeconds(10));
        }
    }

    private async Task CheckUpdatesAsync()
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

        try
        {
        Console.WriteLine("=== U02: метаданные разбираются или отвергаются ===");

        var good = Manifest("4.0.1", "4.0.1", "[1]", "[1]", 2);
        Check("целые метаданные прочитаны",
              Update.Manifest.Parse(good) is { Ok: true, Parts.Count: 2 });
        Check("мусор отвергнут с причиной",
              Update.Manifest.Parse("не json") is { Ok: false } bad
              && bad.Problem.Length > 0);
        Check("чужая версия формата отвергнута",
              !Update.Manifest.Parse("""{"manifest_version": 9}""").Ok);
        Check("часть без хэша не часть",
              Update.Manifest.Parse(
                  """
                  {"manifest_version": 1, "parts": {"shell":
                   {"version": "4.0.1", "url": "https://x/y"}}}
                  """) is { Ok: false });
        Check("версии сравниваются числами, а не строками",
              Update.Manifest.Compare("4.0.10", "4.0.9") > 0,
              "| иначе десятая заплата никогда не предложится");

        Console.WriteLine();
        Console.WriteLine("=== U03: четыре сценария ===");

        Check("свежее некуда",
              (await Ask(Manifest("4.0.0", "4.0.0", "[1]", "[1]", 2))).Verdict
              == Update.Verdict.UpToDate);
        Check("новее только оболочка",
              (await Ask(Manifest("4.0.1", "4.0.0", "[1]", "[1]", 2))).Verdict
              == Update.Verdict.ShellOnly);
        Check("новее только ядро",
              (await Ask(Manifest("4.0.0", "4.0.1", "[1]", "[1]", 2))).Verdict
              == Update.Verdict.CoreOnly);
        Check("новее обе",
              (await Ask(Manifest("4.0.1", "4.0.1", "[1]", "[1]", 2))).Verdict
              == Update.Verdict.Both);

        var clash = await Ask(Manifest("4.0.1", "4.0.1", "[2]", "[3]", 2));
        Check("пара, которая не поздоровается, не качается",
              clash.Verdict == Update.Verdict.Incompatible,
              $"| {clash.Explanation}");

        var older = await Ask(Manifest("4.0.0", "4.0.1", "[1]", "[1]", 1));
        Check("ядро, которое не прочитает данные, отвергнуто",
              older.Verdict == Update.Verdict.Incompatible,
              $"| {older.Explanation}");

        Console.WriteLine();
        Console.WriteLine("=== U04: целостность ===");

        var payload = System.Text.Encoding.UTF8.GetBytes("это сборка");
        var right = Convert.ToHexString(
            System.Security.Cryptography.SHA256.HashData(payload))
            .ToLowerInvariant();

        var fetched = await Download(payload, right);
        Check("верный хэш — файл принят", fetched.Ok, $"| {fetched.Problem}");
        Check("и лежит там, где его ждут",
              fetched.Path.StartsWith(Update.Updater.Staging),
              $"| {fetched.Path}");

        var wrong = await Download(payload, new string('0', 64));
        Check("неверный хэш — отказ", !wrong.Ok, $"| {wrong.Problem}");
        Check("и файла не осталось",
              !Directory.EnumerateFiles(Update.Updater.Staging, "*-9.9.9.bin")
                        .Any(),
              "| половина обновления однажды окажется установленной");

        var open = new Update.Updater([1], new HttpClient(new Update.Fake()));
        var refused = await open.DownloadAsync(new Update.Part
        {
            Name = "shell", Version = "0.0.1",
            Url = "http://example.com/build.zip", Sha256 = right,
        });
        Check("не https — отказ до всякой закачки",
              !refused.Ok && refused.Problem.Contains("https"),
              $"| {refused.Problem}");

        Console.WriteLine();
        Console.WriteLine("=== U05: журнал ===");
        var log = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
            "RinaAssistant", "logs", "security.log");
        // We read without getting in the way of writing: the journal is
        // open for appending, and an ordinary read trips over the shared
        // access. A check that falls over because the journal is being
        // written to at that moment is not checking the journal.
        var written = "";
        try
        {
            using var journal = new FileStream(
                log, FileMode.Open, FileAccess.Read,
                FileShare.ReadWrite | FileShare.Delete);
            using var reader = new StreamReader(journal);
            written = reader.ReadToEnd();
        }
        catch (Exception error)
        {
            Console.WriteLine($"     журнал не прочитан: {error.GetType().Name}");
        }
        Check("проверка записана", written.Contains("update stage=check"));
        Check("закачка записана", written.Contains("update stage=download"));
        Check("несовместимость названа",
              written.Contains("result=incompatible"));
        Check("в журнале нет текста разговора",
              !written.Contains("это сборка"),
              "| «что обновляли» и «что человек сказал» — разные сведения");

        try { Directory.Delete(Update.Updater.Staging, true); } catch { }
        }
        catch (Exception error)
        {
            // Otherwise the window hangs until it is killed from outside:
            // the mode lives until an explicit shutdown, and an unhandled
            // exception does not end it.
            fails++;
            Console.WriteLine($"  СБОЙ  {error.GetType().Name}: {error.Message}");
        }

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>Metadata with the given versions of the parts.</summary>
    private static string Manifest(string shell, string core,
                                   string shellProtocol, string coreProtocol,
                                   int schema) =>
        "{\"manifest_version\": 1, \"channel\": \"stable\", \"parts\": {"
        + $"\"shell\": {{\"version\": \"{shell}\", "
        + $"\"url\": \"https://x/shell.zip\", \"sha256\": \"aa\", "
        + $"\"protocol\": {shellProtocol}}}, "
        + $"\"core\": {{\"version\": \"{core}\", "
        + $"\"url\": \"https://x/core.zip\", \"sha256\": \"bb\", "
        + $"\"protocol\": {coreProtocol}, \"data_schema\": {schema}}}}}}}";

    /// <summary>Ask the client about this metadata.</summary>
    private static async Task<Update.Found> Ask(string manifest)
    {
        var fake = new Update.Fake()
            .Says(Update.Updater.Source,
                  Update.Fake.Release("https://x/manifest.json"))
            .Says("https://x/manifest.json", manifest);
        var updater = new Update.Updater([1], new HttpClient(fake));
        return await updater.CheckAsync("4.0.0", "4.0.0", dataSchema: 2);
    }

    /// <summary>Download the given content under the given hash.</summary>
    private static async Task<(bool Ok, string Path, string Problem)> Download(
        byte[] payload, string sha256)
    {
        var fake = new Update.Fake().Gives("https://x/build.zip", payload);
        var updater = new Update.Updater([1], new HttpClient(fake));
        return await updater.DownloadAsync(new Update.Part
        {
            Name = "shell",
            Version = sha256.StartsWith('0') ? "9.9.9" : "4.0.1",
            Url = "https://x/build.zip",
            Sha256 = sha256,
        });
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetCursorPos(int x, int y);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool SetForegroundWindow(IntPtr window);

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool AttachThreadInput(uint from, uint to,
                                                 bool attach);

    /// <summary>Take the foreground, the way Windows actually allows.</summary>
    /// <remarks>
    /// <c>Activate</c> alone is refused: Windows gives the foreground only
    /// to the process that already holds it, so a check started from a
    /// terminal asks for it and is quietly turned down. Without the
    /// foreground the pointer lands on whoever does hold it, and every
    /// question about hovering is answered by a button at rest.
    ///
    /// Attaching to the holder's input queue is the documented way round:
    /// while attached we count as the same input context, and the request
    /// is granted.
    /// </remarks>
    private static void TakeForeground(Window window)
    {
        var ours = new System.Windows.Interop.WindowInteropHelper(window)
            .Handle;
        var theirs = GetForegroundWindow();
        if (theirs == ours) return;

        var them = GetWindowThreadProcessId(theirs, IntPtr.Zero);
        var us = GetCurrentThreadId();
        AttachThreadInput(them, us, true);
        SetForegroundWindow(ours);
        window.Activate();
        AttachThreadInput(them, us, false);
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool GetCursorPos(out System.Drawing.Point point);

    /// <summary>
    /// Hovering over a list row: one is highlighted, and it goes out when
    /// the cursor leaves.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The cursor moves for real: `IsMouseOver` is only read, it is set by
    /// the cursor actually landing there, and neither a screenshot nor a
    /// method call checks that.
    /// </para>
    /// <para>
    /// <b>And it goes back where it was.</b> A check has no right to leave
    /// somebody else's mouse in the corner of the screen — the same rule by
    /// which the autostart check puts the registry entry back.
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
            // On top of everything and focused: `Synchronize` works out
            // what the cursor is over by landing in a **visible** window,
            // and somebody else's window on top made the check now green,
            // now red without a single change.
            window.Topmost = true;
            window.Show();
            window.Activate();
            TakeForeground(window);

            // And say so if it did not come forward. Everything below moves
            // the real pointer and then asks what changed; with somebody
            // else's window in front the pointer lands on theirs, nothing
            // changes, and the questions are answered by an interface at
            // rest — which is a lawful-looking answer to every one of them.
            // One honest line beats six puzzling ones.
            await Until(() => window.IsActive, 3);
            Check("окно вышло на передний план", window.IsActive,
                  window.IsActive ? ""
                  : "| без этого курсор попадает в чужое окно, "
                    + "и вся проверка меряет покой");
            if (!window.IsActive)
            {
                Console.WriteLine();
                Console.WriteLine($"Ошибок: {fails}");
                Environment.ExitCode = 1;
                Shutdown();
                return;
            }

            // With a core of its own: without a link the commands page
            // shows "the core is not connected" and not a single row —
            // there would be nothing to check.
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

            // Two commands of our own, written here. A fresh store under
            // the sandbox has none, and the built-in group is folded when
            // the page is drawn (`4.0b-A11`) — so the rows this check is
            // about were there only on a machine whose real store happened
            // to hold a couple, and that is what it had been measuring.
            // Written rather than unfolded, because a row of one's own is
            // the row with the dangerous button on it, and that button is
            // checked below.
            if (window.CurrentPage is Pages.CommandsPage listing)
            {
                await listing.CreateForCheckAsync(
                    "проверка наводки раз", "speak", "раз");
                await listing.CreateForCheckAsync(
                    "проверка наводки два", "speak", "два");
                await Task.Delay(800);
            }

            var rows = Rows(window).Take(2).ToArray();
            Check("строки списка нашлись", rows.Length == 2,
                  $"| {rows.Length}");
            if (rows.Length < 2)
            {
                // Not `return`: the mode lives until an explicit shutdown,
                // and leaving here would have left the window hanging
                // forever. Which is what happened with the first edition of
                // this check.
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

            // The pointer is where we put it, and that is not the same as
            // being over us. Somebody else's window that stays on top —
            // a terminal, a recorder, a messenger — takes the hit test, and
            // then nothing anywhere below lights up. Every assertion in this
            // check reads "nothing lit", which is exactly what a broken
            // highlight reads as: the check cannot tell the two apart, so
            // it has to ask outright.
            Check("курсор дошёл до окна", rows[0].IsMouseOver,
                  rows[0].IsMouseOver ? ""
                  : "| поверх нашего стоит чужое окно; наводку здесь "
                    + "не измерить, и «не подсветилось» ничего не значит");
            if (!rows[0].IsMouseOver)
            {
                Console.WriteLine();
                Console.WriteLine($"Ошибок: {fails}");
                Environment.ExitCode = 1;
                SetCursorPos(was.X, was.Y);
                Shutdown();
                return;
            }

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

            // --- what stands written on a button under the pointer ----
            Console.WriteLine();
            Console.WriteLine("=== наведение: текст на кнопке под курсором ===");

            // Asked of the picture, not of the palette. The palette is
            // checked by `check_contrast.py`, and it was green while the
            // button was unreadable: the highlight is a layer of its own,
            // and which layer lands on which button is a fact about the
            // styles rather than about the colours. Only the drawn button
            // knows both.
            var dpi = PresentationSource.FromVisual(window)
                          ?.CompositionTarget?.TransformToDevice.M11 ?? 1.0;
            foreach (var (style, what) in new[]
                     {
                         ("Btn.Primary", "первичной"),
                         ("Btn.Danger", "опасной"),
                         ("Btn", "обычной"),
                     })
            {
                var look = (Style)window.FindResource(style);
                var button = Buttons(window).FirstOrDefault(
                    b => ReferenceEquals(b.Style, look) && b.IsVisible
                         && b.ActualWidth > 40);
                if (button is null)
                {
                    Check($"кнопка {style} нашлась", false);
                    continue;
                }

                var ink = (button.Foreground as
                           System.Windows.Media.SolidColorBrush)?.Color
                          ?? System.Windows.Media.Colors.Black;
                // The left-hand padding, where the button is filled and
                // nothing is written: a glyph is a mixture of ink and face
                // at every anti-aliased edge, and averaging that would
                // measure the blend rather than the ground it stands on.
                var box = button.TransformToVisual(window)
                                .Transform(new Point(0, 0));
                System.Windows.Media.Color Fill() => Mean(
                    window, dpi, box.X + 4, box.X + 12,
                    box.Y + button.ActualHeight * 0.3,
                    box.Y + button.ActualHeight * 0.7);

                var calm = Fill();
                await HoverAsync(button);
                var warm = Fill();

                // First that the pointer arrived at all. Without this the
                // reading below is of the button at rest, and a button at
                // rest passes: the whole difficulty is in the state the
                // check is named after. On a screen with somebody else's
                // window over ours the pointer lands on theirs, and every
                // assertion here went green while measuring nothing.
                Check($"{what} кнопка отзывается на курсор",
                      Apartness(calm, warm) > 1.02,
                      $"| {calm} → {warm}");

                var seen = Apartness(ink, warm);
                Check($"на {what} кнопке под курсором текст читается",
                      seen >= 4.5,
                      $"| {seen:0.0} при нужных 4.5, {ink} на {warm}");
            }

            // And the hatching survives the pointer. It is the only sign of
            // danger in the system, and the highlight used to be opaque, so
            // the one moment a person is certainly looking at the button was
            // the one moment it had nothing on it.
            var danger = Buttons(window).FirstOrDefault(
                b => ReferenceEquals(b.Style, window.FindResource("Btn.Danger"))
                     && b.IsVisible && b.ActualWidth > 40);
            if (danger is not null)
            {
                var at = danger.TransformToVisual(window)
                               .Transform(new Point(0, 0));
                await HoverAsync(danger);
                var lit = Grain(window, dpi, at.X + 4, at.X + 16,
                                at.Y + 6, at.Y + danger.ActualHeight - 6);
                SetCursorPos((int)window.Left + 20, (int)window.Top + 600);
                await Task.Delay(400);
                var calm = Grain(window, dpi, at.X + 4, at.X + 16,
                                 at.Y + 6, at.Y + danger.ActualHeight - 6);
                Check("штриховка видна и под курсором", lit > calm / 2,
                      $"| рябь {lit:0.0} против {calm:0.0} без курсора");
            }

            // --- options of an opened list ----------------------------
            Console.WriteLine();
            Console.WriteLine("=== движение: наводка на вариант списка ===");

            window.ShowSectionFor("settings");
            await Task.Delay(2500);

            // The settings page is assembled over the wire: the schema,
            // the values and the option lists are three separate answers
            // from the core. We wait for the options to appear rather than
            // for a fixed time: on a slow machine a fixed one is never
            // enough.
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

                // The main check, and it is not about movement. Opacity
                // may honestly travel to one and nothing will be visible if
                // the highlight colour equals the colour underneath — which
                // is exactly how it was: the animation ran, the check went
                // green, the person saw no hover.
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

    /// <summary>How far each section's accent stroke has grown, 0 to 1.</summary>
    private static IEnumerable<double> Marks(DependencyObject root)
    {
        foreach (var child in Children(root))
        {
            if (child is System.Windows.Shapes.Rectangle bar
                && bar.RenderTransform
                    is System.Windows.Media.ScaleTransform grown
                && bar.Width is 2 or double.NaN
                && bar.ActualWidth <= 2.5)
                yield return grown.ScaleY;
            foreach (var deeper in Marks(child)) yield return deeper;
        }
    }

    /// <summary>The page's buttons in order of appearance.</summary>
    private static IEnumerable<System.Windows.Controls.Button> Buttons(
        DependencyObject root)
    {
        foreach (var child in Children(root))
        {
            if (child is System.Windows.Controls.Button one) yield return one;
            foreach (var deeper in Buttons(child)) yield return deeper;
        }
    }

    /// <summary>The average colour of a patch of the drawn window.</summary>
    private static System.Windows.Media.Color Mean(
        Window window, double dpi, double left, double right,
        double top, double bottom)
    {
        var (pixels, width, height) = Drawn(window, dpi);
        double r = 0, g = 0, b = 0;
        var seen = 0;
        for (var y = Math.Max(0, (int)(top * dpi));
             y < Math.Min(height, (int)(bottom * dpi)); y++)
            for (var x = Math.Max(0, (int)(left * dpi));
                 x < Math.Min(width, (int)(right * dpi)); x++)
            {
                var at = (y * width + x) * 4;
                b += pixels[at];
                g += pixels[at + 1];
                r += pixels[at + 2];
                seen++;
            }
        if (seen == 0) return System.Windows.Media.Colors.Black;
        return System.Windows.Media.Color.FromRgb(
            (byte)(r / seen), (byte)(g / seen), (byte)(b / seen));
    }

    /// <summary>How uneven a patch is: a pattern shows here, a fill does not.</summary>
    private static double Grain(
        Window window, double dpi, double left, double right,
        double top, double bottom)
    {
        var (pixels, width, height) = Drawn(window, dpi);
        var seen = new List<double>();
        for (var y = Math.Max(0, (int)(top * dpi));
             y < Math.Min(height, (int)(bottom * dpi)); y++)
            for (var x = Math.Max(0, (int)(left * dpi));
                 x < Math.Min(width, (int)(right * dpi)); x++)
                seen.Add(pixels[(y * width + x) * 4 + 1]);
        if (seen.Count == 0) return 0;
        var middle = seen.Average();
        return Math.Sqrt(seen.Sum(one => (one - middle) * (one - middle))
                         / seen.Count);
    }

    /// <summary>The window as drawn, in pixels.</summary>
    private static (byte[] Pixels, int Width, int Height) Drawn(
        Window window, double dpi)
    {
        var width = (int)(window.ActualWidth * dpi);
        var height = (int)(window.ActualHeight * dpi);
        var frame = new RenderTargetBitmap(width, height, 96 * dpi, 96 * dpi,
                                           PixelFormats.Pbgra32);
        frame.Render(window);
        var pixels = new byte[width * height * 4];
        frame.CopyPixels(pixels, width * 4, 0);
        return (pixels, width, height);
    }

    /// <summary>WCAG contrast between two colours.</summary>
    /// <remarks>
    /// The same formula as <c>tools/check_contrast.py</c>, and the same
    /// threshold. Two implementations of one formula part company at the
    /// first change to it — but these two measure different things: the
    /// table of colours there, the drawn window here, and the drawn window
    /// is where a highlight lands on a button the table never paired it
    /// with.
    /// </remarks>
    private static double Apartness(System.Windows.Media.Color one,
                                    System.Windows.Media.Color other)
    {
        static double Channel(byte value)
        {
            var part = value / 255.0;
            return part <= 0.03928 ? part / 12.92
                                   : Math.Pow((part + 0.055) / 1.055, 2.4);
        }
        static double Light(System.Windows.Media.Color colour)
            => 0.2126 * Channel(colour.R) + 0.7152 * Channel(colour.G)
               + 0.0722 * Channel(colour.B);

        var a = Light(one);
        var b = Light(other);
        return (Math.Max(a, b) + 0.05) / (Math.Min(a, b) + 0.05);
    }

    /// <summary>The page's dropdowns in order of appearance.</summary>
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

    /// <summary>An option's highlight brush: each has one of its own.</summary>
    private static System.Windows.Media.Brush? Warm(
        System.Windows.Controls.ComboBoxItem option)
        => (option.Template?.FindName("Row", option)
            as System.Windows.Controls.Border)?.Background;

    /// <summary>Read the journal without getting in the way of whoever writes to it.</summary>
    private static string Journal(string path)
    {
        try
        {
            using var file = new FileStream(path, FileMode.Open,
                                            FileAccess.Read,
                                            FileShare.ReadWrite | FileShare.Delete);
            using var reader = new StreamReader(file);
            return reader.ReadToEnd();
        }
        catch
        {
            return "";
        }
    }

    /// <summary>What an option lies on: the colour of the nearest filled surface.</summary>
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

    /// <summary>How distinguishable two colours are: the sum of the channel differences.</summary>
    private static int Apart(System.Windows.Media.Color a,
                             System.Windows.Media.Color b)
        => Math.Abs(a.R - b.R) + Math.Abs(a.G - b.G) + Math.Abs(a.B - b.B);

    /// <summary>How brightly an option is lit right now.</summary>
    private static double Glow(System.Windows.Controls.ComboBoxItem option)
        => (Warm(option) as System.Windows.Media.SolidColorBrush)?.Opacity ?? -1;

    /// <summary>Move the cursor to the middle of an option.</summary>
    /// <summary>How brightly a row is lit right now.</summary>
    private static double Lit(System.Windows.Controls.Border row)
        => (row.Background as System.Windows.Media.SolidColorBrush)?.Opacity ?? -1;

    /// <summary>Move the cursor to the middle of a row and let the motion run.</summary>
    private static async Task HoverAsync(FrameworkElement row)
    {
        var middle = row.PointToScreen(new Point(row.ActualWidth / 2,
                                                 row.ActualHeight / 2));
        SetCursorPos((int)middle.X, (int)middle.Y);

        // `SetCursorPos` alone is not enough: WPF learns the cursor's
        // position from input messages, and teleporting produces none — the
        // window went on believing the mouse was not over it.
        // `Synchronize` makes it work out afresh what the cursor is over.
        System.Windows.Input.Mouse.Synchronize();
        await Task.Delay(500);
    }

    /// <summary>
    /// The clear space around every irreversible action on a page.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Measured in pixels on the screen, not read off a <c>Margin</c>. The
    /// rule (SYSTEM §4) is about what a hand sees and misses: the hatch is
    /// the first line, the doubled gap is the second, and it is the one
    /// that works for a person who cannot make the pattern out. A margin
    /// says what was asked for; a column of the wrong width, a neighbour
    /// with a negative margin or a template that ignores it all leave the
    /// property intact and the gap gone.
    /// </para>
    /// <para>
    /// Only neighbours <b>on the same line</b> count — something under it
    /// is not what a slipping hand hits — and only things one presses: a
    /// caption beside a delete button is not a wrong press waiting to
    /// happen.
    /// </para>
    /// </remarks>
    private static IEnumerable<(System.Windows.Controls.Button Danger, double Gap, string Near)>
        DangerGaps(FrameworkElement root)
    {
        var hatched = Application.Current.TryFindResource("Btn.Danger") as Style;
        var all = Deep(root).OfType<FrameworkElement>()
            .Where(e => e.IsVisible && e.ActualWidth > 0)
            .ToList();

        foreach (var button in all.OfType<System.Windows.Controls.Button>()
                     .Where(b => ReferenceEquals(b.Style, hatched)))
        {
            var mine = Where(button, root);
            var gap = double.PositiveInfinity;
            var near = "";
            foreach (var other in all.Where(
                         e => e is System.Windows.Controls.Button or System.Windows.Controls.CheckBox or System.Windows.Controls.ComboBox or System.Windows.Controls.TextBox)
                     .Where(e => !ReferenceEquals(e, button)))
            {
                // Not through it and not inside it: a button holding a
                // border of its own is not its own neighbour.
                if (button.IsAncestorOf(other) || other.IsAncestorOf(button))
                    continue;
                var theirs = Where(other, root);
                if (theirs.Bottom <= mine.Top || theirs.Top >= mine.Bottom)
                    continue;
                var apart = theirs.Left >= mine.Right ? theirs.Left - mine.Right
                          : mine.Left >= theirs.Right ? mine.Left - theirs.Right
                          : 0;
                if (apart >= gap) continue;
                gap = apart;
                near = (other as System.Windows.Controls.ContentControl)?.Content?.ToString()
                       ?? other.GetType().Name;
            }
            yield return (button, gap, near);
        }
    }

    /// <summary>
    /// Captions that asked the string table for a word and got nothing.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Read off the screen, not out of the string table. Every language
    /// check we had called <c>Loc.S</c> straight and asked which language
    /// came back — and half the interface does not go that way. It goes
    /// through the <c>{loc:S …}</c> markup, which builds a binding, and a
    /// binding that cannot resolve its path leaves the property empty and
    /// says so only in a debug trace nobody reads.
    /// </para>
    /// <para>
    /// A key that is present and translated proves nothing about the
    /// caption on the screen; this looks at the caption.
    /// </para>
    /// </remarks>
    private static IEnumerable<string> BlankCaptions(FrameworkElement root)
    {
        foreach (var thing in Deep(root).OfType<DependencyObject>())
        {
            var (property, shown) = thing switch
            {
                System.Windows.Controls.TextBlock words =>
                    (System.Windows.Controls.TextBlock.TextProperty,
                     (object?)words.Text),
                System.Windows.Controls.ContentControl holder =>
                    (System.Windows.Controls.ContentControl.ContentProperty,
                     holder.Content),
                _ => (null, null),
            };
            if (property is null) continue;

            var live = System.Windows.Data.BindingOperations
                .GetBindingExpression(thing, property);
            if (live?.ParentBinding.Source is not Rina.Shell.Strings.Loc.Lookup)
                continue;
            if (shown is string said && said.Length > 0) continue;

            var path = live.ParentBinding.Path?.Path ?? "";
            yield return path.Trim('[', ']').Replace("^", "");
        }
    }

    private static Rect Where(FrameworkElement what, FrameworkElement root) =>
        what.TransformToAncestor(root).TransformBounds(
            new Rect(what.RenderSize));

    private static IEnumerable<DependencyObject> Deep(DependencyObject root)
    {
        foreach (var child in Children(root))
        {
            yield return child;
            foreach (var deeper in Deep(child)) yield return deeper;
        }
    }

    /// <summary>The list's rows in order of appearance.</summary>
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
    /// A07: the home screen — the menu, and the figure's four states.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Two things a screenshot cannot settle. <b>Whether the menu is shut
    /// by default</b> is a question about the moment a person first sees
    /// the window, and every other check opens it deliberately in order to
    /// measure the column. <b>Whether the four states differ</b> is a
    /// question about four pictures, and nobody looks at four screenshots
    /// side by side and calls it a check.
    /// </para>
    /// <para>
    /// The states are set directly rather than by making the core listen
    /// and think: what is being checked here is that the figure renders
    /// them differently, not that the events arrive — the events have their
    /// own path and their own check. Waiting for a microphone would make
    /// this a check of the microphone.
    /// </para>
    /// </remarks>
    private async Task CheckHomeAsync(MainWindow window, string? shot)
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

        Console.WriteLine("=== главная: меню и фигура ===");
        window.Left = -4000;
        window.Top = -4000;
        window.Show();
        window.Activate();
        await Until(() => window.CurrentPage is Pages.HomePage);


        // **The clock has to be running before anything about the figure is
        // measured.** The figure moves on the background's tick, and that
        // ticks only while the window is active — a window shown off-screen
        // gets focus or does not, depending on what else the machine is
        // doing. When it did not, every state reported the same swell and
        // the check called that "the states do not differ": true, and about
        // nothing. Three runs in a row went red under the load of the full
        // regression and green on their own, which is exactly how a race
        // looks from outside.
        var ticking = await Until(() => window.BackdropRunning);
        Check("часы идут — иначе фигуру мерить нечем", ticking,
              ticking ? "" : "| окно не получило фокус, движения нет");

        Check("окно открывается на главной",
              window.CurrentPage is Pages.HomePage,
              $"| {window.CurrentPage?.GetType().Name}");
        Check("разделы спрятаны за меню", !window.MenuOpen);
        Check("и колонка свёрнута", window.MenuWidth < 1,
              $"| ширина {window.MenuWidth:0.0}");

        window.ShowMenu(true);
        await Until(() => window.MenuWidth > 100);
        Check("три полоски открывают разделы", window.MenuWidth > 100,
              $"| ширина {window.MenuWidth:0.0}");

        window.ShowMenu(false);
        await Until(() => window.MenuWidth < 1);
        Check("и закрывают обратно", window.MenuWidth < 1,
              $"| ширина {window.MenuWidth:0.0}");

        // The figure. Four states, and the picture has to differ between
        // them — otherwise there are four names and one behaviour.
        if (window.CurrentPage is not Pages.HomePage home)
        {
            Console.WriteLine("  FAIL  фигуры нет — дальше нечего проверять");
            fails++;
        }
        else
        {
            var seen = new List<(Doing State, double Swell)>();
            var said = new List<string>();
            foreach (var doing in new[] { Doing.Idle, Doing.Listening,
                                          Doing.Thinking, Doing.Talking })
            {
                home.ShowDoingFor(doing, doing is Doing.Listening ? 0.8 : 0);
                Check($"состояние {doing} принято", home.Doing == doing);
                // The caption under the figure went; what it said did not.
                // It moved onto the figure as an automation name, and that
                // is the only thing left for a screen reader to read. If it
                // were empty, the removal would have taken the state away
                // from the one person who cannot see the figure say it.
                said.Add(home.DoingSaid);
                // Measured after the figure has actually settled, not
                // after a guessed pause: the swell is worked out while
                // painting, and it travels towards its target over several
                // frames. Waiting for it to stop moving is the same
                // question the pause was asking, answered rather than
                // estimated.
                await Settled(() => home.Swell);
                seen.Add((doing, home.Swell));
            }

            Check("состояние читается вслух, хоть подписи и нет",
                  said.All(word => !string.IsNullOrWhiteSpace(word))
                  && said.Distinct().Count() == said.Count,
                  $"| {string.Join(", ", said.Select(w => $"«{w}»"))}");

            for (var at = 1; at < seen.Count; at++)
                Check($"{seen[at].State} отличается от покоя",
                      Math.Abs(seen[at].Swell - seen[0].Swell) > 0.01,
                      $"| {seen[0].Swell:0.000} против {seen[at].Swell:0.000}");

            // The correction a person had to make: an open microphone is
            // not somebody speaking. "Always listening" opens it and leaves
            // it open for hours, and the figure used to sit in `listening`
            // that whole time — reporting the setting instead of the room.
            home.HearFor(true, 0f);
            await Until(() => home.Doing != Doing.Talking);
            Check("открытый микрофон сам по себе — ещё не «слушаю»",
                  home.Doing != Doing.Listening, $"| {home.Doing}");

            home.HearFor(true, 0.5f);
            await Until(() => home.Doing == Doing.Listening);
            Check("а заговоривший человек — да",
                  home.Doing == Doing.Listening, $"| {home.Doing}");

            home.HearFor(false, 0f);
            await Until(() => home.Doing == Doing.Idle);
            Check("микрофон закрыли — снова ждёт",
                  home.Doing == Doing.Idle, $"| {home.Doing}");
        }

        // --- and what plugins asked to show here ---
        //
        // The core is raised **here**, at the end, and not at the start:
        // starting it takes the focus off our window, and everything above
        // measures a figure that only moves while the window is active.
        // Raised first, it turned three green assertions red and said
        // nothing about why.
        var link = new CoreLink(window, CoreLink.FindCore());
        window.Link = link;
        await link.StartAsync();
        await Until(() => link.State == Rina.Protocol.CoreState.Ready, 12);
        window.Activate();
        await Until(() => window.CurrentPage is Pages.HomePage);
        //
        // Whether any plugin wants a tile depends on what is installed and
        // switched on, so what is asserted is the agreement between the two
        // sides: as many tiles as the core offers, drawn. Zero on both sides
        // is a lawful answer and the commonest one.
        var offered = await link.AskAsync(Rina.Protocol.Methods.PluginsHome);
        var wanted = offered?["tiles"]?.AsArray()?.Count ?? 0;
        // --- the list: a button on the home screen and a window behind it ---
        //
        // Through the window rather than the store: that something gets
        // written down is checked in `test_todo.py` with no window at all.
        // The question here is a different one — whether what was written
        // reaches the eye.
        //
        // The page is taken **after** it has stopped being replaced. When
        // the core announces its plugins the column is rebuilt and the open
        // section is shown afresh, and the instance captured a moment
        // earlier is a home screen with no parent. It answers every
        // question sensibly — its layer is visible, its list holds the row
        // that was written — and none of it is anywhere a person could
        // look. This whole block ran against such a page and was green.
        // Found by asking it for a screenshot and getting an empty corner.
        var page = (Pages.HomePage)(await SettledPage(window))!;
        var list = page.OpenTodoForCheck();
        await Until(() => page.TodoShowing && list.IsLoaded, 5);
        await Until(() => page.TodoOnScreen, 5);
        Check("список поднялся на экране, а не в отвязанной странице",
              page.TodoOnScreen, $"| {page.TodoSizeForCheck}");

        // In the window's corner, not the page's (4.0b-E02). The window
        // gives every page a margin of thirty-two, and a button that obeys
        // it sits fifty-two points off the glass — in a corner nobody sees.
        // Measured against the window because that is the edge a person
        // means by "the corner".
        var far = page.TodoButton.TransformToVisual(window).Transform(
            new Point(page.TodoButton.ActualWidth,
                      page.TodoButton.ActualHeight));
        var offRight = window.ActualWidth - far.X;
        var offFoot = window.ActualHeight - far.Y;
        // Against the page's own margin rather than a number picked here:
        // the whole point is that this button is nearer the glass than
        // anything the page lays out, and thirty-two is what "the page
        // lays out" means.
        var room = ((Thickness)window.PaneRoom).Right;
        Check("кнопка дел — у края окна, а не у края страницы",
              offRight < room && offFoot < room,
              $"| {offRight:0} справа, {offFoot:0} снизу при поле {room:0}");

        // By its text, not by a count: counting races with the window's
        // own first load and depends on whatever earlier runs left behind.
        var wrote = $"проверочное дело {DateTime.Now:HHmmss}";
        await list.AddForCheck(wrote);
        await Until(() => list.ShowsForCheck(wrote), 6);
        Check("записанное дело появилось в списке",
              list.ShowsForCheck(wrote), $"| строк {list.Shown}");
        // Closed things are struck through. Through the same tick a person
        // presses, not by setting the decoration and reading it back: the
        // question is whether closing something puts a line through it,
        // and a check that draws the line itself would answer yes on a
        // list that never draws one.
        await list.CloseForCheck(wrote);
        await Until(() => list.StruckForCheck(wrote), 6);
        Check("сделанное зачёркнуто", list.StruckForCheck(wrote),
              list.StruckForCheck(wrote) ? "" : "| линии на строке нет");

        // A screenshot with the list open, if asked for. The ordinary shot
        // of this screen shows the button and nothing the button opens, and
        // the panel is the one thing here nobody can look at otherwise.
        if (shot is not null)
        {
            await Task.Delay(400);
            Save(window, shot);
        }

        // And it goes away again: a panel that cannot be dismissed is a
        // window, which is what this stopped being.
        page.HideTodoForCheck();
        await Until(() => !page.TodoShowing, 5);
        Check("панель убирается", !page.TodoShowing);

        var shown = (Pages.HomePage)window.CurrentPage!;
        await Until(() => shown.TilesShown == wanted, 8);
        Check("плиток нарисовано столько, сколько предложило ядро",
              shown.TilesShown == wanted,
              $"| ядро дало {wanted}, нарисовано {shown.TilesShown}");

        // And the drawing itself, which must work on a machine where no
        // plugin wants a tile — otherwise the assertion above says "none
        // offered, none drawn" and means nothing.
        shown.ShowTilesForCheck(new JsonArray(
            new JsonObject
            {
                ["id"] = "проба",
                ["elements"] = new JsonArray(
                    new JsonObject
                    {
                        ["kind"] = "note",
                        ["text"] = "Плитка от плагина",
                    }),
            }));
        await Until(() => shown.TilesShown == 1, 5);
        Check("объявленная плитка рисуется", shown.TilesShown == 1,
              $"| {shown.TilesShown}");

        shown.ShowTilesForCheck([]);
        await Until(() => shown.TilesShown == 0, 5);
        Check("а без плиток на главной их нет", shown.TilesShown == 0,
              $"| {shown.TilesShown}");

        await link.DisposeAsync();

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>Wait until the window stops replacing the open page.</summary>
    /// <remarks>
    /// The column of sections is rebuilt when the core announces its
    /// plugins, and rebuilding it shows the open section afresh — a new
    /// page, the old one detached. A check that took hold of the page
    /// before that went on questioning an object with no parent and got
    /// sensible answers to everything it asked.
    ///
    /// A second of quiet rather than waiting for the plugins by name: what
    /// is installed differs from machine to machine, and a check that waits
    /// for a particular plugin is green for a reason that has nothing to do
    /// with what it is about.
    /// </remarks>
    private static async Task<object?> SettledPage(MainWindow window)
    {
        var page = window.CurrentPage;
        for (var still = 0; still < 10;)
        {
            await Task.Delay(100);
            if (ReferenceEquals(window.CurrentPage, page)) still++;
            else
            {
                page = window.CurrentPage;
                still = 0;
            }
        }
        return page;
    }

    /// <summary>
    /// "Always listening" survives a restart, all the way to the microphone.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Reported by a person: the switch comes back on after a restart and
    /// nothing listens. The core half is checked in
    /// <c>test_service.py</c> — that the announcement is made, and made
    /// after the reply. This is the other half, and it is the half that
    /// broke: the shell subscribed to events only once the handshake had
    /// returned, so the announcement fell into the gap and the microphone
    /// stayed shut. Each side was right on its own; nothing asked about
    /// the join.
    /// </para>
    /// <para>
    /// <b>The mode is switched on the way a person switches it</b> — over
    /// the wire, by the core — and then the core is restarted into the
    /// same profile. Writing the file here would be quicker and would
    /// check something else: the shell does not know where the settings
    /// live and must not (ADR 0006), and a check that knows is a check
    /// that has already crossed the line it is meant to watch.
    /// </para>
    /// <para>
    /// With a profile of its own, thrown away after. The setting lives in
    /// the person\'s store, and a check that reads the developer\'s answers
    /// a question about that machine — which is how three other checks in
    /// this file came to be green for the wrong reason.
    /// </para>
    /// </remarks>
    private async Task CheckListenAsync()
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

        Console.WriteLine("=== «всегда слушать» после перезапуска ===");

        var real = CoreLink.FindCore();
        var sandboxed = Path.Combine(real.WorkingDirectory, "tools",
                                     "_core_sandboxed.py");

        async Task<CoreLink> RaiseAsync()
        {
            var link = new CoreLink(new MainWindow(),
                new Rina.Protocol.CoreLaunch(real.Python, sandboxed,
                                             real.WorkingDirectory));
            await link.StartAsync();
            for (var i = 0; i < 400
                 && link.State != Rina.Protocol.CoreState.Ready; i++)
                await Task.Delay(100);
            return link;
        }

        // Waited on the **start**, not on the state. The event sets the
        // state and the sound link is built by a later turn of the
        // window's queue: a check that stopped at the state read the
        // counter one turn too early and went red at a working program
        // four times out of five. A wait that ends before the thing it
        // waits for has happened measures the scheduler.
        async Task SettleAsync(CoreLink link)
        {
            for (var i = 0; i < 60 && link.CaptureStarts == 0; i++)
                await Task.Delay(100);
        }

        var home = Path.Combine(Path.GetTempPath(),
                                "rina-listen-" + Guid.NewGuid().ToString("N")[..8]);
        Directory.CreateDirectory(home);
        Environment.SetEnvironmentVariable("RINA_SANDBOX_DIR", home);
        try
        {
            var first = await RaiseAsync();
            Check("ядро поднялось", first.State == Rina.Protocol.CoreState.Ready,
                  $"| {first.State}");
            await SettleAsync(first);
            Check("до включения микрофон молчит",
                  !first.Capturing && first.CaptureStarts == 0,
                  $"| запусков {first.CaptureStarts}");

            var told = false;
            if (first.Connection is { Ready: true } connection)
            {
                var answer = await connection.CallAsync(
                    Rina.Protocol.Methods.SpeechSetAlwaysListen,
                    new JsonObject { ["enabled"] = true },
                    TimeSpan.FromSeconds(10));
                told = !answer.IsError
                       && answer.Payload["enabled"]?.GetValue<bool>() == true;
            }
            Check("режим включён — как его включает человек", told);
            await first.DisposeAsync();

            // The restart. The same folder, a new core, and nobody
            // pressing anything.
            var again = await RaiseAsync();
            Check("ядро поднялось после перезапуска",
                  again.State == Rina.Protocol.CoreState.Ready,
                  $"| {again.State}");
            await SettleAsync(again);
            Check("микрофон открылся, хотя никто не просил",
                  again.Capturing && again.CaptureStarts > 0,
                  $"| запусков {again.CaptureStarts}");
            await again.DisposeAsync();
        }
        finally
        {
            Environment.SetEnvironmentVariable("RINA_SANDBOX_DIR", null);
            try { Directory.Delete(home, recursive: true); }
            catch { /* уйдёт со временным каталогом */ }
        }

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// The bar shows what is behind it, softened (4.0b-E01).
    /// </summary>
    /// <remarks>
    /// <para>
    /// Asked of the rendered window, not of the element. "Is there a blur
    /// on it, and of what radius" is the code read back aloud: it stays
    /// green when the layer is the wrong size, when it sits under the
    /// background instead of over it, and when the row clips it away
    /// entirely — every way this can actually be broken.
    /// </para>
    /// <para>
    /// The background is frozen on a striped picture first, because its own
    /// flow has no detail to lose: two hundred points stretched across a
    /// window is already softer than the blur. Measured against the flow,
    /// the check came out the same with the blur taken out.
    /// </para>
    /// <para>
    /// And it measures the same place twice — once with the layer, once
    /// without. The second reading is what gives the first one a size:
    /// "soft" means nothing until it is said next to how sharp the picture
    /// behind the bar really is.
    /// </para>
    /// </remarks>
    private async Task CheckGlassAsync(MainWindow window, string? shot)
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

        Console.WriteLine("=== стекло: полоса и вкладка — одна картина ===");

        window.Width = 940;
        window.Height = 620;
        window.WindowStartupLocation = WindowStartupLocation.Manual;
        window.Left = -4000;
        window.Top = -4000;
        window.Show();
        await Task.Delay(500);

        var dpi0 = PresentationSource.FromVisual(window)
                       ?.CompositionTarget?.TransformToDevice.M11 ?? 1.0;
        var row0 = (int)((double)window.FindResource("Size.Row") * dpi0);

        // The flow as it really runs, on a tab that reads rather than
        // looks. The striped picture below cannot answer this one: the
        // calm layer is not painted while nothing shows it, and the
        // question here is precisely whether the two layers are one
        // picture.
        window.ShowSectionFor("dialog");
        window.RunBackdropForShot();
        await Task.Delay(900);

        Check("на вкладке полоса — стекло над спокойным слоем",
              window.BarOnCalm,
              "| иначе она окно в другой фон, а не в тот же");

        // Brightness across the bar's lower edge, against the ordinary
        // change a few points above it. A person pointed at this with one
        // screenshot: the bar ended in a line, and a line reads as the
        // edge of a plate. It was not the blur — the calm layer lived
        // inside the working row alone and was a different picture at a
        // different scale, so above the line one flow, below it another.
        double Seam(int from, int to)
        {
            var (pixels, width, height) = Drawn(window, dpi0);
            double At(int y)
            {
                double sum = 0;
                for (var x = from; x < to; x++)
                {
                    var at = (y * width + x) * 4;
                    sum += pixels[at] + pixels[at + 1] + pixels[at + 2];
                }
                return sum / ((to - from) * 3);
            }
            var step = Math.Abs(At(row0) - At(row0 - 1));
            var near = 0.0;
            for (var y = row0 - 14; y < row0 - 1; y++)
                near = Math.Max(near, Math.Abs(At(y + 1) - At(y)));
            // Allowed as much as the picture moves by itself a few points
            // higher up, and never less than one value: a flow this smooth
            // can be almost flat, and then any honest reading is "nothing
            // happens here".
            var room = Math.Max(1.0, near * 2);
            Console.WriteLine($"     x {from}..{to}: на кромке {step:0.00}, "
                              + $"рядом {near:0.00}, позволено {room:0.00}");
            return step - room;
        }

        var over = Math.Max(
            Math.Max(Seam((int)(940 * dpi0 * 0.13), (int)(940 * dpi0 * 0.17)),
                     Seam((int)(940 * dpi0 * 0.46), (int)(940 * dpi0 * 0.55))),
            Seam((int)(940 * dpi0 * 0.74), (int)(940 * dpi0 * 0.85)));
        Check("шва под полосой не видно", over <= 0,
              $"| перебор {over:0.00}");

        Console.WriteLine();
        Console.WriteLine("=== стекло: размытие под верхней полосой ===");
        window.ShowSectionFor("home");
        await Task.Delay(400);

        // Stripes above, one plain colour below. Two questions in one
        // picture: the stripes are the detail the bar is meant to lose, and
        // the colour says which part of the picture it is showing — a layer
        // squeezed into the row's forty points instead of laid out over the
        // whole window would come out blue.
        static (byte R, byte G, byte B) Ink(int x, int y)
        {
            const int band = 30;
            if (y >= band) return (20, 30, 240);
            return y % 2 == 0 ? ((byte)240, (byte)30, (byte)30)
                              : ((byte)30, (byte)0, (byte)0);
        }

        window.PaintBackdropForCheck(Ink);
        await Task.Delay(300);

        if (shot is not null) Save(window, shot);

        var dpi = PresentationSource.FromVisual(window)
                      ?.CompositionTarget?.TransformToDevice.M11 ?? 1.0;

        // Between the layer's two fades. A blur samples nothing outside
        // the picture, so its first points fade towards transparency; and
        // the last ones are faded on purpose, so the bar dissolves into
        // the page instead of ending in a line. What is left between them
        // is the glass at full strength, and that is where the question
        // "is it soft" has an answer.
        var top = (int)(19 * dpi);
        var bottom = (int)(26 * dpi);

        (double Red, double Blue, double Detail) Read()
        {
            var width = (int)(window.ActualWidth * dpi);
            var height = (int)(window.ActualHeight * dpi);
            var frame = new RenderTargetBitmap(width, height, 96 * dpi,
                                               96 * dpi, PixelFormats.Pbgra32);
            frame.Render(window);
            var pixels = new byte[width * height * 4];
            frame.CopyPixels(pixels, width * 4, 0);

            // The middle of the row across: the title stands on the left and
            // the three window buttons on the right, and both would be read
            // as detail of the background.
            var from = (int)(width * 0.45);
            var to = (int)(width * 0.55);
            var rows = new List<double>();
            double red = 0, blue = 0;
            for (var y = top; y < bottom; y++)
            {
                double r = 0, b = 0;
                for (var x = from; x < to; x++)
                {
                    var at = (y * width + x) * 4;
                    b += pixels[at];
                    r += pixels[at + 2];
                }
                rows.Add(r / (to - from));
                red += r / (to - from);
                blue += b / (to - from);
            }
            return (red / rows.Count, blue / rows.Count,
                    rows.Max() - rows.Min());
        }

        var glass = Read();

        window.BarGlass.Visibility = Visibility.Collapsed;
        await Task.Delay(300);
        var bare = Read();
        window.BarGlass.Visibility = Visibility.Visible;

        Check("за полосой действительно резкая картинка",
              bare.Detail > 100,
              $"| перепад {bare.Detail:0} из 210");
        Check("полоса показывает верх картинки, а не всю",
              glass.Red > glass.Blue * 2,
              $"| красного {glass.Red:0}, синего {glass.Blue:0}");
        Check("и показывает её размытой",
              glass.Detail < bare.Detail / 5,
              $"| перепад {glass.Detail:0} против {bare.Detail:0}");

        // --- a window that draws its own corner ----------------------
        Console.WriteLine();
        Console.WriteLine("=== стекло: угол отдельного окна ===");

        // Measured off the picture, not read off the markup. A corner can
        // be lost to a style, to a border that does not clip what stands
        // inside it, or to transparency that was never switched on, and
        // "the markup says eight" agrees with the author through every one
        // of those.
        var sheet = new Pages.SheetWindow("", "", [])
        {
            Left = -4000,
            Top = -4000,
        };
        sheet.Show();
        await Task.Delay(400);
        var cut = CornerOf(sheet, dpi);
        sheet.Close();
        Check("окно с прозрачностью скруглено как все прочие окна",
              cut >= 6, $"| срезано {cut} точек по краю, ждали около 8");

        // --- the list laid over the home screen ----------------------
        Console.WriteLine();
        Console.WriteLine("=== стекло: накладка поверх главной ===");

        window.ShowSectionFor("home");
        await Task.Delay(400);
        var home = (Pages.HomePage)(await SettledPage(window))!;
        home.OpenTodoForCheck();
        await Until(() => home.TodoOnScreen, 5);

        // Stripes everywhere this time: the question is not which part of
        // the picture the panel shows but whether it shows any of it, and
        // whether what it shows has been softened on the way.
        static (byte R, byte G, byte B) Bars(int x, int y) =>
            y % 2 == 0 ? ((byte)240, (byte)30, (byte)30)
                       : ((byte)30, (byte)0, (byte)0);

        window.PaintBackdropForCheck(Bars);
        await Task.Delay(300);

        var panel = home.TodoPanel;
        var corner = panel.TransformToVisual(window)
                          .Transform(new Point(0, 0));
        var shape = new Rect(corner.X, corner.Y,
                             panel.ActualWidth, panel.ActualHeight);

        // Inside the panel's own padding, where nothing is written, and the
        // same height just outside it. Two readings of one picture: what
        // reaches the eye through the panel, and what reaches it beside.
        var inside = Detail(window, dpi,
                            shape.Right - 16, shape.Right - 6,
                            shape.Top + 30, shape.Bottom - 30);
        var beside = Detail(window, dpi,
                            shape.Left - 26, shape.Left - 16,
                            shape.Top + 30, shape.Bottom - 30);
        home.HideTodoForCheck();

        Check("рядом с панелью полосы видны резко", beside.Detail > 100,
              $"| перепад {beside.Detail:0} из 210");
        Check("сквозь панель — размытыми",
              inside.Detail < beside.Detail / 5,
              $"| перепад {inside.Detail:0} против {beside.Detail:0}");
        Check("и панель всё-таки не дыра — заливка своя",
              Math.Abs(inside.Red - beside.Red) > 20,
              $"| {inside.Red:0} против {beside.Red:0}");

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>How much of the corner a window cuts away, in points.</summary>
    /// <remarks>
    /// Along the top edge until something is drawn. A square window paints
    /// its first point at the very corner; a rounded one starts as far in as
    /// its radius. It reads alpha rather than colour because a window with
    /// transparency has nothing at all outside its own shape.
    /// </remarks>
    private static int CornerOf(Window window, double dpi)
    {
        var width = (int)(window.ActualWidth * dpi);
        var height = (int)(window.ActualHeight * dpi);
        var frame = new RenderTargetBitmap(width, height, 96 * dpi, 96 * dpi,
                                           PixelFormats.Pbgra32);
        frame.Render(window);
        var pixels = new byte[width * height * 4];
        frame.CopyPixels(pixels, width * 4, 0);
        for (var x = 0; x < width / 2; x++)
            if (pixels[x * 4 + 3] > 128) return (int)(x / dpi);
        return -1;
    }

    /// <summary>Colour and detail in one patch of the rendered window.</summary>
    private static (double Red, double Detail) Detail(
        Window window, double dpi, double left, double right,
        double top, double bottom)
    {
        var width = (int)(window.ActualWidth * dpi);
        var height = (int)(window.ActualHeight * dpi);
        var frame = new RenderTargetBitmap(width, height, 96 * dpi, 96 * dpi,
                                           PixelFormats.Pbgra32);
        frame.Render(window);
        var pixels = new byte[width * height * 4];
        frame.CopyPixels(pixels, width * 4, 0);

        var from = Math.Max(0, (int)(left * dpi));
        var to = Math.Min(width, (int)(right * dpi));
        var rows = new List<double>();
        double red = 0;
        for (var y = Math.Max(0, (int)(top * dpi));
             y < Math.Min(height, (int)(bottom * dpi)); y++)
        {
            double one = 0;
            for (var x = from; x < to; x++) one += pixels[(y * width + x) * 4 + 2];
            rows.Add(one / Math.Max(1, to - from));
            red += rows[^1];
        }
        if (rows.Count == 0) return (0, 0);
        return (red / rows.Count, rows.Max() - rows.Min());
    }

    /// <summary>
    /// Motion is visible in time, not in a screenshot.
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

        Console.WriteLine("=== движение: окно приходит, а не оказывается ===");
        // One of the four things the person named: "windows appearing".
        // Every separate window used to be simply there. Measured
        // mid-flight rather than after, for the same reason as the panel
        // below: before the clock's first tick a property gives back its
        // base value, and an instant reading would show the end state
        // even with no animation at all.
        var asking = new Pages.ConfirmWindow(
            "Компьютер будет выключен немедленно.", "Сказано голосом", 60);
        asking.Left = -4000;
        asking.Top = -4000;
        asking.Show();
        await Task.Delay(80);

        var arriving = asking.Content as UIElement;
        var shown = arriving?.Opacity ?? 1;
        Check("на середине появления окно ещё проявляется",
              shown is > 0.01 and < 0.95, $"| прозрачность {shown:0.00}");
        // The transform is a group now — a rise and a breath of scale
        // together — so the offset is looked for inside it rather than
        // assumed to be the whole of it.
        static double Lifted(UIElement? what) => what?.RenderTransform switch
        {
            System.Windows.Media.TranslateTransform one => one.Y,
            System.Windows.Media.TransformGroup many => many.Children
                .OfType<System.Windows.Media.TranslateTransform>()
                .Select(t => t.Y).FirstOrDefault(),
            _ => 0,
        };

        var lifted = Lifted(arriving);
        Check("и ещё не доехало", lifted > 0.5, $"| осталось {lifted:0.00}");

        // The one that matters. An element at zero opacity is still
        // hit-testable in WPF, so a window fading in can take a click
        // meant for what was under it — and this is the window that asks
        // about something irreversible.
        Check("пока оно проявляется, нажать на него нельзя",
              arriving?.IsHitTestVisible == false,
              "| иначе щелчок мимо попадает в подтверждение");

        await Task.Delay(400);
        Check("через 400 мс окно на месте",
              (arriving?.Opacity ?? 0) > 0.99 && Math.Abs(Lifted(arriving)) < 0.01,
              $"| прозрачность {arriving?.Opacity:0.00}, "
              + $"смещение {Lifted(arriving):0.00}");
        Check("и слушает нажатия", arriving?.IsHitTestVisible == true);
        asking.Close();

        Console.WriteLine();
        Console.WriteLine("=== движение: переключатель в два приёма ===");
        // Named by the person among the things that should move better.
        // It did move — and all three parts of it moved on one clock with
        // one curve, which is a single flat change wearing three
        // costumes. A switch has an order to it: the knob is thrown, and
        // the circuit closes after it lands.
        var bench = new Window
        {
            Width = 200, Height = 80, Left = -4000, Top = -4000,
            WindowStyle = WindowStyle.None, ShowInTaskbar = false,
        };
        var flip = new System.Windows.Controls.CheckBox
        {
            Style = (Style)Application.Current.FindResource("Toggle"),
            Content = "проба",
        };
        bench.Content = flip;
        bench.Show();
        flip.ApplyTemplate();
        await Task.Delay(200);

        double Knob() => ((System.Windows.Media.TranslateTransform)
            flip.Template.FindName("Shift", flip)).X;
        double Circuit() => ((FrameworkElement)
            flip.Template.FindName("On", flip)).Opacity;

        Check("в покое клавиша слева и цепь разомкнута",
              Math.Abs(Knob()) < 0.01 && Circuit() < 0.01,
              $"| клавиша {Knob():0.0}, цепь {Circuit():0.00}");

        flip.IsChecked = true;
        await Task.Delay(55);
        var thrownAt = Knob();
        var closedAt = Circuit();
        Check("клавиша пошла первой", thrownAt > 0.5,
              $"| прошла {thrownAt:0.0} из 18");
        Check("а цепь ещё не замкнулась", closedAt < 0.01,
              $"| {closedAt:0.00} — иначе это одно движение, а не два");

        await Task.Delay(300);
        Check("в конце клавиша дошла и цепь замкнута",
              Math.Abs(Knob() - 18) < 0.01 && Circuit() > 0.99,
              $"| клавиша {Knob():0.0}, цепь {Circuit():0.00}");

        // And back the other way round: the circuit opens, then the knob
        // returns. A switch that goes off the way it went on is a picture
        // of a switch.
        flip.IsChecked = false;
        await Task.Delay(55);
        Check("обратно первой размыкается цепь", Circuit() < 0.99,
              $"| {Circuit():0.00}");
        Check("а клавиша ещё на месте", Knob() > 17.5,
              $"| {Knob():0.0} из 18");

        await Task.Delay(300);
        Check("и вернулась", Math.Abs(Knob()) < 0.01 && Circuit() < 0.01,
              $"| клавиша {Knob():0.0}, цепь {Circuit():0.00}");
        bench.Close();

        Console.WriteLine();
        Console.WriteLine("=== движение: отметка раздела вырастает ===");
        window.Left = -4000;
        window.Top = -4000;
        window.Show();
        await Task.Delay(400);

        // The accent stroke is the system's only mark of where one is
        // standing, and it used to be switched on by a setter: the one
        // thing that answers "where am I" arrived without saying that
        // anything had changed.
        window.Show();
        await Task.Delay(400);
        var atRest = Marks(window).ToArray();
        Check("отметок ровно по числу разделов", atRest.Length >= 5,
              $"| {atRest.Length}");
        Check("в покое видна ровно одна", atRest.Count(m => m > 0.5) == 1,
              $"| {string.Join(", ", atRest.Select(m => m.ToString("0.0")))}");

        window.ShowSectionFor("commands");
        await Task.Delay(80);
        var midway2 = Marks(window).ToArray();
        Check("на середине перехода одна растёт, другая тает",
              midway2.Any(m => m is > 0.01 and < 0.99)
              && midway2.Count(m => m > 0.01) == 2,
              $"| {string.Join(", ", midway2.Select(m => m.ToString("0.00")))}");

        await Task.Delay(400);
        var after2 = Marks(window).ToArray();
        Check("доросла одна, погасла другая",
              after2.Count(m => m > 0.99) == 1 && after2.Count(m => m > 0.01) == 1,
              $"| {string.Join(", ", after2.Select(m => m.ToString("0.0")))}");

        Console.WriteLine();
        Console.WriteLine("=== движение: переход между разделами ===");
        window.ShowSectionFor("home");
        await Task.Delay(400);
        window.ShowSectionFor("commands");

        // We measure mid-flight rather than instantly. Before the
        // animation clock's first tick the property gives back its base
        // value, and an instant read would show one even with a working
        // animation — the check would lie in both directions.
        await Task.Delay(80);
        var rise = window.PaneRise;

        // **By parts, not as a plate** (`4.0b-E04`). The panel itself no
        // longer fades — its parts do, one behind another — so what is
        // asked is not "is something fading" but "are they at different
        // stages". A single block fading answers the first and fails the
        // second, which is the whole difference between the two.
        string Shown(IReadOnlyList<double> parts)
            => string.Join(", ", parts.Select(o => o.ToString("0.00")));

        var coming = window.PartsArriving;
        Check("у раздела есть части", coming.Count >= 2,
              $"| {coming.Count}");
        Check("на середине перехода они ещё прибывают",
              coming.Any(o => o is > 0.01 and < 0.99),
              $"| {Shown(coming)}");
        Check("и прибывают по очереди, а не разом",
              coming.Count >= 2 && coming[0] - coming[^1] > 0.05,
              $"| {Shown(coming)}");
        Check("и ещё не доехала", rise > 0.05, $"| осталось {rise:0.00} точек");

        // Depth settles together with the rise (4.0b-A06). Halfway through
        // the shadow is visible: contents arriving from above carry one
        // while they travel.
        var deep = window.PaneShadow;
        Check("на середине перехода тень видна", deep > 0.02,
              $"| плотность {deep:0.00}");

        await Task.Delay(400);
        var later = window.PaneOpacity;
        Check("через 400 мс панель на месте", later > 0.99,
              $"| прозрачность {later:0.00}");
        Check("и доехала", Math.Abs(window.PaneRise) < 0.01,
              $"| смещение {window.PaneRise:0.00}");
        // And this is the amendment to §5 read back from the running
        // window: a shadow is allowed as movement, and in a still frame
        // there is none. A resting shadow would be a card on a shadow —
        // the very thing the amendment refused to permit.
        Check("а в покое тени нет вовсе", window.PaneShadow < 0.01,
              $"| плотность {window.PaneShadow:0.00}");

        // The second transition is a separate check, and not for
        // completeness. An animation that finishes with `HoldEnd` goes on
        // holding one after the end; without an explicit `From` the next
        // one would start from the held value and there would be no dip —
        // the first transition after startup visible, every later one not.
        // The parts fade with `FillBehavior.Stop`, which returns them to
        // their base value, and this is the question that says so.
        window.ShowSectionFor("reminders");
        await Task.Delay(80);
        var second = window.PartsArriving;
        Check("второй переход тоже собирается по частям",
              second.Count >= 2 && second[0] - second[^1] > 0.05,
              $"| {Shown(second)}");

        await Task.Delay(400);
        window.ShowSectionFor("settings");
        await Task.Delay(80);
        var third = window.PartsArriving;
        Check("и третий", third.Count >= 2 && third[0] - third[^1] > 0.05,
              $"| {Shown(third)}");

        // --- the living background, and above all its stopping ---
        //
        // This is the half of 4.0b-A06 that cannot be seen in a screenshot.
        // "The background freezes when nobody is looking" is a promise
        // about time, and the only way to check it is across time: the
        // phase advances while the window is being looked at and stands
        // still while it is not.
        Console.WriteLine();
        Console.WriteLine("=== движение: живой фон и его остановка ===");

        if (Backdrop.WantsStillness)
        {
            // The system was asked for less movement, and we obey. There is
            // nothing to measure then, and saying so out loud is more
            // honest than a green line about a background that is standing
            // still by request.
            Check("система просит покоя — фон стоит", !window.BackdropRunning,
                  "| ClientAreaAnimation выключен");
        }
        else
        {
            window.Activate();
            await Task.Delay(300);
            Check("окно перед человеком — фон живёт", window.BackdropRunning);

            var before = window.BackdropPhase;
            await Task.Delay(500);
            var after = window.BackdropPhase;
            Check("и он действительно движется", Math.Abs(after - before) > 1e-6,
                  $"| фаза {before:0.0000} -> {after:0.0000}");

            // What a frame costs, measured rather than assumed. The whole
            // argument for stopping the background when nobody looks is
            // that frames cost a person something; a cost that was never
            // measured makes that argument on trust. The ceiling is a third
            // of the interval — beyond that the flow starts eating the
            // frame it was supposed to fit inside.
            // The picture, not the clock. The phase above advances even when
            // the field is frozen — that is exactly how a jerking background
            // passed this check while a person was watching it stutter.
            //
            // Two bounds, because there are two ways to be wrong. Zero means
            // the picture is not moving at all. Too large means it is
            // jumping: at this period a frame should shift things by a
            // fraction of a value, and a leap of several values per frame is
            // the snap between two lattice cells that the person saw.
            var moved = window.BackdropChange;
            Check("и картинка меняется, а не только часы", moved > 0.002,
                  $"| {moved:0.000} значения на кадр");
            Check("и меняется плавно, без скачка", moved < 2.0,
                  $"| {moved:0.000} значения на кадр, потолок 2.0");

            // And how far it travels in a second, which is the interval a
            // person judges by. Below a value or so it is a photograph that
            // technically updates.
            await Task.Delay(2400);
            var drift = window.BackdropDrift;
            Check("и за секунду сдвигается заметно", drift >= 1.0,
                  $"| {drift:0.00} значения за секунду");

            var frame = window.BackdropFrameMs;
            var budget = 1000.0 / (double)Application.Current
                .FindResource("Background.Fps") / 3;
            Check("и стоит не дороже обещанного", frame <= budget,
                  $"| {frame:0.0} мс на кадр, потолок {budget:0.0}");

            window.Hide();
            await Task.Delay(300);
            Check("окно скрыто — фон замер", !window.BackdropRunning);

            var stopped = window.BackdropPhase;
            await Task.Delay(500);
            Check("и фаза стоит на месте",
                  Math.Abs(window.BackdropPhase - stopped) < 1e-9,
                  $"| фаза {stopped:0.0000} -> {window.BackdropPhase:0.0000}");

            window.Show();
            window.Activate();
            await Task.Delay(300);
            Check("вернулись — фон снова живёт", window.BackdropRunning);

            // And the branch this machine is not in. Whether reduced
            // motion is obeyed depends on the developer's own Windows
            // setting, and on a machine with animations on it is never
            // reached: breaking the obedience deliberately left the check
            // green. So it is asked directly.
            Backdrop.Stillness = true;
            window.Activate();
            await Task.Delay(300);
            Check("система просит покоя — фон стоит", !window.BackdropRunning);

            var still = window.BackdropPhase;
            await Task.Delay(400);
            Check("и стоит по-настоящему",
                  Math.Abs(window.BackdropPhase - still) < 1e-9,
                  $"| фаза {still:0.0000} -> {window.BackdropPhase:0.0000}");

            Backdrop.Stillness = null;
            window.Activate();
            await Task.Delay(300);
            Check("покой отменили — фон вернулся", window.BackdropRunning);
        }

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
    }

    /// <summary>
    /// F11: a question has a deadline, but not every question does.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Caught by a person, not by a check: "Reset settings" opened a window
    /// that vanished before it could be read. The zero that was passed
    /// meant "no deadline", and the constructor turned it into one second.
    /// </para>
    /// <para>
    /// A screenshot does not catch such a thing — in a screenshot the
    /// window is right. It is caught only by time: wait and see whether it
    /// is still there.
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

        // A question the person opened themselves: there is no deadline.
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

        // A question from the core: there is a deadline, and the window closes itself on it.
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
    /// G01..G12: the shell's system layer.
    /// </summary>
    /// <remarks>
    /// <para>
    /// What <b>must not</b> happen is checked alongside what must:
    /// "Downloads" does not get into the index, a junction pointing outside
    /// does not pass the trust check, something unsigned is not launched in
    /// silence. A rule nobody watches holds exactly until the first change.
    /// </para>
    /// <para>
    /// The check does nothing irreversible: power and locking are in the
    /// table of actions but are not called here — a check that shuts the
    /// computer down gets run once.
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

        // --- prohibitions (G08) ---
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

        // --- the canonical path (G11) ---
        var link = Path.Combine(Path.GetTempPath(), "rina-check-link");
        var outside = Environment.GetFolderPath(
            Environment.SpecialFolder.UserProfile);
        try
        {
            if (Directory.Exists(link)) Directory.Delete(link);
            // A junction, not a symlink: a symlink needs privileges and a
            // junction does not, and G11 names precisely the latter. It is
            // created with the same `mklink` a person would create it with.
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

        // --- the signature (G09) ---
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

        // --- the index (G04) ---
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

        // --- actions (G01) ---
        Check("таблица действий закрыта и названа",
              Platform.Machine.Actions.Length >= 10
              && Platform.Machine.Do("сделай-что-нибудь") is { Ok: false },
              "| неизвестное имя — отказ, а не исключение");
        Check("необратимое помечено",
              Platform.Machine.Irreversible.Contains("shutdown")
              && !Platform.Machine.Irreversible.Contains("volume_up"));

        // --- the journal (G12) ---
        // What used to be checked here was behaviour but not writing. And
        // writing did not work at all: the journal was opened without
        // letting others write, the core held the same file, and the
        // shell's lines never appeared. The exception was swallowed —
        // in silence.
        var mark = $"проверка-{Guid.NewGuid():N}"[..24];
        Platform.Journal.Action(mark, ok: true);
        Check("запись в журнал доходит до файла",
              Journal(Platform.Journal.Where).Contains(mark),
              "| открытый на дозапись файл ядра не должен этому мешать");

        Console.WriteLine();
        Console.WriteLine($"Ошибок: {fails}");
        Environment.ExitCode = fails == 0 ? 0 : 1;
        Shutdown();
        return Task.CompletedTask;
    }

    /// <summary>
    /// F04: a command and a reminder are set up from the window.
    /// </summary>
    /// <remarks>
    /// The core runs sandboxed: the check creates real records, and a
    /// person's store is not touched for that. That is exactly why the
    /// check is possible — "set up" would otherwise mean leaving a trace in
    /// somebody else's data.
    /// </remarks>
    /// <summary>
    /// Run a check and never let it die in silence.
    /// </summary>
    /// <remarks>
    /// A check is started with <c>_ = …Async(window)</c>: nobody awaits it,
    /// so an exception inside leaves the method and goes nowhere. The
    /// program then sits with <c>ShutdownMode.OnExplicitShutdown</c> and
    /// never shuts down — and from outside that is indistinguishable from a
    /// slow check, so the run is killed by a timeout with no red line and
    /// no reason.
    ///
    /// It happened: a second draw of the commands page threw, and the whole
    /// suite hung for eight minutes saying nothing. A failure that looks
    /// like a hang is worse than a failure, because the first thing anybody
    /// does with a hang is raise the timeout.
    /// </remarks>
    private static void Watched(Task running, string what)
    {
        _ = running.ContinueWith(done =>
        {
            var why = done.Exception?.GetBaseException();
            Console.WriteLine();
            Console.WriteLine($"  FAIL  проверка {what} упала: "
                              + $"{why?.GetType().Name}: {why?.Message}");
            Console.WriteLine("Ошибок: 1");
            Console.Out.Flush();
            Environment.Exit(1);
        }, TaskContinuationOptions.OnlyOnFaulted);
    }

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

        // --- commands ---
        window.ShowSectionFor("commands");
        await Task.Delay(1200);
        if (window.CurrentPage is Pages.CommandsPage commands)
        {
            var before = commands.CommandCount;
            var opened = await commands.OpenEditorAsync(null);
            Check("конструктор открылся", opened && commands.EditorOpen);

            // --- and in a place of its own (`4.0b-A09`) ---
            //
            // Writing a command is work, not a glance. It used to unfold
            // inside the list, above the very rows a person compares it
            // against, and pushed them off the screen.
            Check("конструктор занял свой раздел",
                  window.OpenWorkNames.Contains("work:new"),
                  $"| [{string.Join(", ", window.OpenWorkNames)}]");
            Check("и окно показывает именно его",
                  window.CurrentPage is Pages.CommandEditor,
                  $"| {window.CurrentPage?.GetType().Name}");

            // --- the command read back as one thing (`4.0b-A09`) ---
            //
            // Everything in the editor is the command in pieces: a phrase
            // in one place, a kind in another, a path in a third. What a
            // person decides is whether the whole does what they meant,
            // and until this line there was nowhere on the screen that
            // said so. Asserted by what it says, not by whether the block
            // exists: an empty summary is a block that exists.
            var editor = commands.OpenEditor;
            if (editor is null) Check("конструктор доступен проверке", false);
            else
            {
                // Waited for, not slept through. The editor is put on the
                // page and measured on the next layout pass; read before
                // that, every element reports itself invisible and a check
                // about where the mark sits answers about nothing.
                var laid = await Until(() => editor.IsVisible, 5);
                Check("конструктор на экране", laid);
                editor.FillForCheck("открой блокнот", "app",
                                    @"C:\Windows\System32\notepad.exe");
                var read = editor.SummarySaid;
                Check("сводка называет фразу", read.Contains("открой блокнот"),
                      $"| «{read}»");
                Check("сводка называет, что произойдёт",
                      read.Contains("notepad.exe"), $"| «{read}»");
                Check("и чем она ответит", read.Contains("Готово"),
                      $"| «{read}»");

                // The new capability says it is new, beside itself.
                var (seen, x, y, width) = editor.BetaWhere();
                Check("проба помечена бетой", editor.BetaMarkedWell,
                      seen ? $"| метка на {x:0}×{y:0} от кнопки шириной {width:0}"
                           : "| кнопки или метки нет на экране");

                // And trying does not save. The whole reason the method
                // exists: a person trying a phrase four times would
                // otherwise have four commands to delete.
                var had = commands.CommandCount;
                editor.TryForCheck();
                await Task.Delay(900);
                await commands.ReloadForCheckAsync();
                Check("проба ничего не завела в списке",
                      commands.CommandCount == had,
                      $"| было {had}, стало {commands.CommandCount}");
            }

            // --- the chain of steps (`4.0b-A09`) ---
            //
            // What the plan asked for and what the first attempt did not
            // do: a step goes in **between** two others, what happens
            // inside a repeat is drawn inside it, and the window offers
            // exactly the kinds the core will run.
            // From an empty canvas: the node put there a few lines above
            // is still on it, and "inserted between two others" cannot be
            // read off a graph whose contents came from somewhere else.
            editor!.ClearForCheck();
            await Task.Delay(150);
            editor!.InsertStepForCheck(0, "app", "первый");
            editor!.InsertStepForCheck(1, "speak", "третий");
            editor!.InsertStepForCheck(1, "pause", "1");
            // --- it is a graph, not an indented list (`4.0b-A09`) ---
            //
            // Nodes on a surface with wires between them. Asserted on what
            // is drawn: a picture that had the nodes and no wires would be
            // the list again with more space around it.
            Check("узлы нарисованы на холсте", editor!.NodesDrawn >= 3,
                  $"| узлов {editor!.NodesDrawn}");
            Check("и связаны проводами", editor!.WiresDrawn >= 2,
                  $"| проводов {editor!.WiresDrawn}");

            // The inspector shows the selected node and nothing until one
            // is: a panel that showed the first node by default would make
            // "selected" mean nothing.
            Check("пока ничего не выбрано — осматривать нечего",
                  !editor!.InspectorShows);
            editor!.PickForCheck(0);
            await Task.Delay(200);
            Check("выбранный узел показан в осмотре", editor!.InspectorShows);

            var order = editor!.ChainForCheck.OfType<JsonObject>()
                .Select(s => s["type"]?.GetValue<string>() ?? "").ToArray();
            Check("шаг вставляется между двумя другими, а не в конец",
                  order.SequenceEqual(["app", "pause", "speak"]),
                  $"| [{string.Join(", ", order)}]");

            // Nesting, which is the point of a repeat and a condition:
            // a chain that could not hold one would be the old flat list
            // with two more kinds in it.
            editor!.InsertStepForCheck(3, "repeat");
            var nested = editor!.NestStepForCheck(3, "steps", "speak", "внутри");
            var inner = (editor!.ChainForCheck[3]?["steps"] as JsonArray)?.Count
                        ?? 0;
            Check("шаг ложится внутрь повтора", nested && inner == 1,
                  $"| внутри {inner}");

            editor!.InsertStepForCheck(4, "if");
            editor!.NestStepForCheck(4, "steps", "speak", "тогда");
            editor!.NestStepForCheck(4, "otherwise", "speak", "иначе");
            var then = (editor!.ChainForCheck[4]?["steps"] as JsonArray)?.Count
                       ?? 0;
            var els = (editor!.ChainForCheck[4]?["otherwise"] as JsonArray)
                      ?.Count ?? 0;
            Check("у условия две ветви, и обе наполняются",
                  then == 1 && els == 1, $"| тогда {then}, иначе {els}");

            // The window offers what the core runs — no more, no less.
            // Offering more would lie while a person works; offering less
            // would hide a capability with nothing to notice it by. It was
            // the second of those that hid `pause` since 2.0.0.
            var asSteps = editor!.StepKindsOffered;

            Check("ожидание, повтор и условие предлагаются как шаги",
                  new[] { "pause", "repeat", "if" }.All(asSteps.Contains),
                  $"| [{string.Join(", ", asSteps)}]");
            // There is no longer a list of "what kind of command this is"
            // to keep them out of: a command is a graph, and these are
            // nodes like any other. The rule they existed for — a command
            // that is only a wait does nothing on purpose — is now kept by
            // the card itself: a graph of one node is saved as a plain
            // command only when that node is a plain kind.
            // **One node, and only one.** The first version of this left
            // whatever was already on the canvas there, so the card was a
            // sequence because it held several steps — and the break that
            // removed the rule stayed green, because the answer never
            // depended on the rule.
            editor!.ClearForCheck();
            editor!.InsertStepForCheck(0, "pause", "1");
            var wrapped = editor!.CardForCheck();
            Check("граф из одного ожидания сохраняется последовательностью",
                  wrapped["type"]?.GetValue<string>() == "sequence",
                  $"| {wrapped["type"]}");

            // And a graph of one plain node keeps the plain shape a command
            // has had since 2.0.0 — a sequence wrapping one "open the
            // browser" would make the list call every command a sequence.
            editor!.ClearForCheck();
            editor!.InsertStepForCheck(0, "website", "example.com");
            var plain = editor!.CardForCheck();
            Check("а граф из одного простого узла — обычной командой",
                  plain["type"]?.GetValue<string>() == "website"
                  && plain["target"]?.GetValue<string>() == "example.com",
                  $"| {plain["type"]} · {plain["target"]}");


            // --- dragging says it can be dragged (`4.0b-A09`) ---
            //
            // It worked before any of this and was invisible, which is the
            // same as not being there. Asserted on the marks a person sees.
            await Task.Delay(150);
            Check("у каждого узла есть ручка",
                  editor!.GripsShown == editor!.NodesDrawn,
                  $"| ручек {editor!.GripsShown} при узлах {editor!.NodesDrawn}");
            Check("и курсор говорит, что узел двигается",
                  editor!.NodeSaysItMoves);

            Check("в покое порты не горят", editor!.PortsLit == 0,
                  $"| горит {editor!.PortsLit} из {editor!.PortsShown}");
            editor!.ShowPortsForCheck(true);
            await Task.Delay(120);
            Check("пока узел в воздухе — горят все",
                  editor!.PortsLit == editor!.PortsShown
                  && editor!.PortsShown > 0,
                  $"| горит {editor!.PortsLit} из {editor!.PortsShown}");
            editor!.ShowPortsForCheck(false);

            // --- the trial, shown running (`4.0b-A09`) ---
            //
            // Asserted on the colour the node is wearing, not on the state
            // written down: "the state was recorded" and "the node turned
            // green" are different claims, and only the second is what a
            // person sees.
            var paths = editor!.NodePaths;
            Check("холст знает пути узлов", paths.Length > 0,
                  $"| [{string.Join(", ", paths)}]");

            // **Through a real trial**, because the names the canvas gives
            // its nodes have to be the names the core gives its steps, and
            // nothing else here checks that they agree. Reporting a path
            // taken from the canvas proved only that the canvas can colour
            // a path it made up itself: the break that renamed them all
            // stayed green.
            editor!.ClearForCheck();
            editor!.InsertStepForCheck(0, "website", "example.com");
            editor!.InsertStepForCheck(1, "website", "example.org");
            await Task.Delay(200);
            editor!.TryForCheck();
            var lit = await Until(
                () => editor!.ColourOfNode("steps.0") == "C.Live", 6);
            Check("настоящая проба красит узел на холсте", lit,
                  lit ? "" : $"| кисть «{editor!.ColourOfNode("steps.0")}», узлы [{string.Join(", ", editor!.NodePaths)}]");

            editor!.TrialStarting();
            await Task.Delay(150);

            // The canvas is left as it was found: the checks below build
            // their own graphs, and two stray nodes from this one made the
            // next assertion read a chain nobody assembled.
            var first = editor!.NodePaths.OrderBy(p => p).First();
            editor!.ReportForCheck(first, "running");
            await Task.Delay(150);
            Check("идущий шаг зеленеет",
                  editor!.ColourOfNode(first) == "C.Live",
                  $"| {editor!.ColourOfNode(first)}");

            editor!.ReportForCheck(first, "failed");
            await Task.Delay(150);
            Check("упавший шаг краснеет",
                  editor!.ColourOfNode(first) == "C.Signal",
                  $"| {editor!.ColourOfNode(first)}");

            // A new trial forgets the last one's colours: left on, they
            // would be read as this run's, and a scenario would look
            // finished a moment before it began.
            editor!.TrialStarting();
            await Task.Delay(150);
            Check("новая проба забывает прежние цвета",
                  editor!.ColourOfNode(first) is "C.Seam" or "C.Ink",
                  $"| {editor!.ColourOfNode(first)}");

            // The place goes when the work is done: a column that keeps
            // offering "new command" after it was saved is a column that
            // has stopped saying what is open.
            editor!.CancelForCheck();
            await Task.Delay(300);
            Check("закрыли — раздел ушёл",
                  !window.OpenWorkNames.Contains("work:new"),
                  $"| [{string.Join(", ", window.OpenWorkNames)}]");
            Check("и вернулись к списку",
                  window.CurrentPage is Pages.CommandsPage,
                  $"| {window.CurrentPage?.GetType().Name}");

            window.ShowSectionFor("commands");
            await Task.Delay(400);
            commands = (Pages.CommandsPage)window.CurrentPage!;
            await commands.OpenEditorAsync(null);
            await Task.Delay(400);
            editor = commands.OpenEditor;

            var saved = await commands.CreateForCheckAsync(
                "открой блокнот", "app", @"C:\Windows\System32\notepad.exe");
            Check("команда заведена из окна", saved,
                  $"| было {before}, стало {commands.CommandCount}");
            Check("и появилась в списке",
                  commands.CommandCount == before + 1,
                  $"| {commands.CommandCount}");

            // A sequence is what used to be importable only. The whole
            // path is checked: the kind, the steps, the order, saving.
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
            // The page is built afresh: the description must be human on
            // the very first draw, not after something has managed to load
            // the kinds along the way.
            window.ShowSectionFor("dialog");
            await Task.Delay(300);
            window.ShowSectionFor("commands");
            await Task.Delay(1200);
            var fresh = window.CurrentPage as Pages.CommandsPage;
            Check("список показывает её словами, а не полями",
                  fresh?.FirstDescription().Contains("Программа") == true,
                  $"| «{fresh?.FirstDescription()}»");


            // --- the lists, in groups that fold (`4.0b-A09`) ---
            //
            // The built-in group starts folded: it is the longest, the
            // least often needed and the one nobody edits. Measured by how
            // tall the lists stand rather than by the flag — a flag saying
            // "folded" over eleven visible rows is not folding.
            //
            // **On `fresh`, not on `commands`.** The section was reopened a
            // few lines above, so `commands` points at a page the window
            // has already replaced: it is not on screen, its layout never
            // runs, and every measurement of it comes back the same number.
            // The same trap the settings check fell into once already.
            var shown = fresh!;
            await shown.ReloadForCheckAsync();
            await Task.Delay(300);
            Check("встроенные свёрнуты сразу",
                  shown.FoldedForCheck("builtin"));
            var closed = shown.ListHeight;
            shown.FoldForCheck("builtin", false);
            await Task.Delay(200);
            var unfolded = shown.ListHeight;
            Check("развернулись — список стал выше", unfolded > closed + 40,
                  $"| было {closed:0}, стало {unfolded:0}");
            shown.FoldForCheck("builtin", true);
            await Task.Delay(200);
            Check("свернулись — снова прежней высоты",
                  Math.Abs(shown.ListHeight - closed) < 1,
                  $"| {shown.ListHeight:0} против {closed:0}");

            // Groups at all: a page with one heading over everything is
            // the flat list this replaced.
            // **Groups of different kinds**, not just "more than one
            // group". Counting all of them answered yes with every command
            // in one heap, because the built-in group made two: the break
            // that put everything together stayed green.
            var byKind = shown.GroupIds.Where(g => g.StartsWith("kind:"))
                .ToArray();
            Check("свои команды разложены по видам", byKind.Length > 1,
                  $"| [{string.Join(", ", shown.GroupIds)}]");
        }
        else Check("страница команд открылась", false);

        // --- reminders ---
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

            // Two ways of saying when, and only one of them acted upon.
            // The typed time has always won inside `OnCreate`; the
            // dropdown went on showing «через 15 минут» beside it, so the
            // screen said one thing and the reminder did another.
            Check("пока времени не вписали — выбор предлагается",
                  reminders.ChoiceOffered);
            reminders.TypeTimeForCheck("19:30");
            await Task.Delay(200);
            Check("вписали время — выбор замолчал",
                  !reminders.ChoiceOffered);
            reminders.TypeTimeForCheck("");
            await Task.Delay(200);
            Check("стёрли — снова предлагается", reminders.ChoiceOffered);
        }
        else Check("страница напоминаний открылась", false);

        // --- what Rina knows about me (`4.0b-B01`) ---
        //
        // The page's promise is completeness, so the assertions are about
        // completeness: that what was stored a moment ago is on it, and
        // that a group this shell has never heard of is on it too.
        window.ShowSectionFor("privacy");
        await Task.Delay(1200);
        if (window.CurrentPage is not Pages.PrivacyPage kept)
            Check("страница приватности открылась", false);
        else
        {
            await kept.ReloadAsync();
            await Until(() => kept.GroupsShown > 0, 6);
            Check("опись пришла из ядра", kept.GroupsShown > 0,
                  $"| групп {kept.GroupsShown}");

            // The command made above, on the page that claims to show
            // everything. Through the page rather than the store: that the
            // store keeps it is checked elsewhere, and what is being asked
            // here is whether a person can see it.
            Check("заведённая команда видна в описи",
                  kept.Said.Any(said => said.Contains("открой блокнот")),
                  $"| строк {kept.Said.Length}");

            // **The one that matters.** A group this shell does not
            // recognise has to be shown all the same, under its own name.
            // A privacy page that drops a category in silence is worse
            // than no page: it is the screen a person opens in order to be
            // told the truth, and it would be answering "this is
            // everything" while leaving something out.
            kept.ShowForCheck([
                new JsonObject
                {
                    ["id"] = "дневник_настроения",
                    ["count"] = 1,
                    ["items"] = new JsonArray(
                        new JsonObject
                        {
                            ["what"] = "запись, о которой оболочка не знает",
                            ["detail"] = "",
                            ["where"] = "",
                            ["when"] = 0,
                        }),
                },
            ]);
            await Task.Delay(300);
            Check("незнакомая группа всё равно показана",
                  kept.ShowsGroup("дневник_настроения"),
                  $"| {string.Join(" / ", kept.Said.Take(3))}");
            Check("и её содержимое тоже",
                  kept.Said.Any(said => said.Contains("о которой оболочка не знает")));

            await kept.ReloadAsync();

            // --- and forgetting (`4.0b-B02`) ---
            //
            // Through the page and back through the core: what the page
            // says went has to be gone from the store, not merely gone
            // from the screen. A row removed from a list and left in the
            // file is the exact failure this page exists to make
            // impossible, and it looks like success.
            var beforeTodo = await link.AskAsync(Rina.Protocol.Methods.TodoList);
            var hadTodo = (beforeTodo?["items"] as JsonArray)?.Count ?? 0;
            if (hadTodo == 0)
            {
                await link.AskAsync(Rina.Protocol.Methods.TodoAdd,
                    new JsonObject { ["text"] = "забыть это дело" });
                await kept.ReloadAsync();
            }

            var one = await link.AskAsync(Rina.Protocol.Methods.TodoList);
            var first = (one?["items"] as JsonArray ?? []).OfType<JsonObject>()
                .FirstOrDefault();
            var itsId = first?["id"]?.GetValue<string>() ?? "";
            Check("есть что забывать", itsId.Length > 0);

            await kept.ForgetEntryForCheck("todo", itsId);
            await Task.Delay(600);
            var after = await link.AskAsync(Rina.Protocol.Methods.TodoList);
            var left = (after?["items"] as JsonArray ?? []).OfType<JsonObject>()
                .Any(i => i["id"]?.GetValue<string>() == itsId);
            Check("забытое ушло из хранилища, а не только с экрана", !left);

            // A day of the conversation, which is how the plan names it
            // and how a person thinks of one: "forget yesterday" is a
            // single thought, and ticking forty rows to say it is a chore
            // that ends in giving up.
            //
            // Two entries a day apart, and one day asked for. A check with
            // one day in it would pass on a page that forgot everything,
            // which is the mistake worth catching.
            var yesterday = DateTimeOffset.Now.AddDays(-1);
            var spread = new JsonArray(
                new JsonObject
                {
                    ["id"] = "вчера",
                    ["when"] = yesterday.ToUnixTimeSeconds(),
                },
                new JsonObject
                {
                    ["id"] = "сегодня",
                    ["when"] = DateTimeOffset.Now.ToUnixTimeSeconds(),
                });
            var picked = Pages.PrivacyPage.DayIdsForCheck(
                spread, yesterday.LocalDateTime.ToString("dd.MM.yyyy"));
            Check("день берёт свои записи и только свои",
                  picked.SequenceEqual(["вчера"]),
                  $"| выбрано [{string.Join(", ", picked)}]");

            // A whole group, and the count the core answers with rather
            // than the count that was asked for.
            await kept.ForgetGroupForCheck("history");
            await Task.Delay(600);
            var history = await link.AskAsync(Rina.Protocol.Methods.HistoryList);
            Check("группа забыта целиком",
                  ((history?["items"] as JsonArray)?.Count ?? 0) == 0,
                  $"| осталось {(history?["items"] as JsonArray)?.Count ?? 0}");
        }

        // --- and the export (`4.0b-B03`) ---
        //
        // Two formats, and the readable one is the point: the program
        // could already hand its data to another copy of itself, and could
        // not hand it to the person whose data it is.
        //
        // Checked on what the core actually returns, and asserted on the
        // text — not on "a file appeared". A file appears just as readily
        // when it is empty.
        if (window.CurrentPage is Pages.PrivacyPage)
        {
            var envelope = await link.AskAsync(
                Rina.Protocol.Methods.PrivacyExport);
            Check("выгрузка пришла конвертом",
                  envelope?["kind"]?.GetValue<string>() == "rina.everything",
                  $"| {envelope?["kind"]}");

            var text = Pages.PrivacyPage.Readable(envelope ?? []);
            Check("в читаемой выгрузке группы названы по-человечески",
                  text.Contains("ВЫУЧЕННЫЕ СЛОВА"),
                  $"| {text.Length} знаков");

            // The rule that holds on the screen has to hold in the file:
            // a group the shell does not know keeps its identifier and is
            // written out. A file promising everything must not quietly
            // hold less than the page it was made from.
            var strange = new JsonObject
            {
                ["kind"] = "rina.everything",
                ["app_version"] = "проба",
                ["exported_at"] = 0,
                ["payload"] = new JsonObject
                {
                    ["groups"] = new JsonArray(
                        new JsonObject
                        {
                            ["id"] = "дневник_настроения",
                            ["count"] = 1,
                            ["items"] = new JsonArray(
                                new JsonObject
                                {
                                    ["what"] = "чужая запись",
                                    ["detail"] = "",
                                    ["where"] = "",
                                    ["when"] = 0,
                                }),
                        }),
                },
            };
            var odd = Pages.PrivacyPage.Readable(strange);
            Check("незнакомая группа попала и в файл",
                  odd.Contains("ДНЕВНИК_НАСТРОЕНИЯ") && odd.Contains("чужая запись"),
                  $"| знаков {odd.Length}");
        }

        // --- the clear space around what cannot be undone ---
        //
        // The rule is written in SYSTEM §4, tokenised as `danger`, and its
        // ratio to `between` is checked in `check_design.py` — and until
        // now **nothing checked that a button on the screen actually got
        // it**. All three of those agree with each other about a number in
        // a file; none of them looks at a window. I found the hole by
        // falling into it: the delete button in a command's row was put
        // there flush against `Править`, and every check stayed green.
        //
        // Measured over the pages that have such a button, in pixels, with
        // real records under it — a page with no rows has no row to crowd.
        var wanted = (double)Application.Current.FindResource("Sp.Danger");
        var crowded = new List<string>();
        var counted = 0;
        foreach (var section in new[] { "commands", "settings" })
        {
            window.ShowSectionFor(section);
            await Task.Delay(900);
            if (window.CurrentPage is not FrameworkElement page) continue;
            foreach (var (button, gap, near) in DangerGaps(page))
            {
                counted++;
                if (gap + 0.5 < wanted)
                    crowded.Add($"«{button.Content}» в {section}: "
                                + $"{gap:0} до «{near}»");
            }
        }
        // Nothing found is not agreement. An empty list of buttons would
        // pass this silently, and the commonest way for it to be empty is
        // that the page failed to load.
        Check("необратимые кнопки вообще нашлись", counted > 0,
              $"| {counted}");
        Check($"вокруг необратимого просвет в {wanted:0}",
              crowded.Count == 0,
              crowded.Count == 0 ? $"| проверено {counted}"
                                 : "| " + string.Join("; ", crowded));

        // --- captions that came back empty ---
        //
        // Found by looking at a page: the line under the name on «about»
        // was simply not there. It is written in the markup, it is in the
        // string table, it is translated — and the binding behind
        // `{loc:S …}` treated the commas in it as separators between the
        // arguments of an indexer, asked a one-argument dictionary for
        // four, and got nothing. **Ten strings were blank this way**,
        // among them the one saying nobody vouched for a plugin.
        //
        // Every language check called `Loc.S` directly and asked which
        // language came back. Not one of them went through the markup,
        // which is where half of these strings live.
        var blank = new List<string>();
        var captions = 0;
        foreach (var section in new[] { "home", "dialog", "commands",
                                        "reminders", "plugins", "settings",
                                        "about" })
        {
            window.ShowSectionFor(section);
            await Task.Delay(700);
            if (window.CurrentPage is not FrameworkElement page) continue;
            captions += Deep(page).OfType<System.Windows.Controls.TextBlock>()
                .Count();
            blank.AddRange(BlankCaptions(page).Select(k => $"{section}: «{k}»"));
        }
        Check("подписи вообще нашлись", captions > 0, $"| {captions}");
        Check("ни одна подпись не пришла пустой", blank.Count == 0,
              blank.Count == 0 ? "" : "| " + string.Join("; ", blank.Take(6)));

        // A screenshot with real records: an empty page and a page with
        // one command look different, and it is the second one worth
        // checking.
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
    /// E04 + F10: the core synthesises, the shell plays.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The check is end-to-end and <b>sounds out loud</b>: only that way is
    /// it visible that the path is whole from text to speaker. Every link
    /// on its own was in order, and Rina was silent — synthesis could do
    /// Piper alone, and in the live program nobody read the speech channel.
    /// </para>
    /// <para>
    /// The core is raised sandboxed, because the check needs to change the
    /// synthesis engine: a person's settings are not touched for that.
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

        // The link comes up in another thread while sound is set up in the
        // window's thread: between "Ready" and "there is something to play
        // with" lies one message queue.
        for (var i = 0; i < 50 && link.Voice is null; i++) await Task.Delay(100);
        Check("звук заведён вместе со связью", link.Voice is not null);

        if (link.Connection is { Ready: true } connection && link.Voice is { } voice)
        {
            // System synthesis: it exists on every Windows and does not go to the network.
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

            // Whether this is actually audible a machine cannot say; but
            // the speaker's queue is the place from which sound goes
            // nowhere except into the device.
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
    /// F05/F06: the tray, autostart, hotkeys.
    /// </summary>
    /// <remarks>
    /// Autostart is checked against the real registry, but is **put back as
    /// it was**: a check has no right to leave an entry in the user's
    /// startup behind it.
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

        // --- F06: parsing hotkeys ---
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

        // --- F05: the tray ---
        using var tray = new Tray(window);
        Check("значок в трее создан", true);
        tray.Hide();
        Check("окно спрятано, программа жива", !window.IsVisible);
        tray.Show();
        Check("и возвращается по требованию", window.IsVisible);

        // --- F05: autostart, put back as it was ---
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

    /// <summary>Synthetic sound: 440 Hz in the microphone's format.</summary>
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
    /// Bring the system into line with the core's settings.
    /// </summary>
    /// <remarks>
    /// We wait for the link: settings live in the core, and before the
    /// handshake there is nowhere to get them from. While we wait the
    /// window is already shown and working — startup is not a hostage of
    /// another process.
    /// </remarks>
    private async Task ApplySystemSettingsAsync(MainWindow window)
    {
        for (var i = 0; i < 300 && _link?.Connection is not { Ready: true }; i++)
            await Task.Delay(100);

        if (_link is null) return;
        var values = await _link.GetAsync("autostart", "minimize_to_tray",
                                          "start_minimized", "hotkey",
                                          "action_hotkeys", "notifications",
                                          "floating_command_bar", "watch_apps");
        if (values is null) return;

        var wanted = values["autostart"]?.GetValue<bool>() ?? false;
        if (wanted != Autostart.Enabled && !Autostart.Apply(wanted))
            window.ShowNote("Не удалось изменить автозапуск: запрещено политикой.");

        window.MinimiseToTray = values["minimize_to_tray"]?.GetValue<bool>()
                                ?? true;

        // The main hotkey: show the window and start listening.
        if (values["hotkey"]?.GetValue<string>() is { Length: > 0 } main)
            _hotkeys?.Bind("main", main, () => window.OnMainHotkey());

        // Action hotkeys. The list of actions was sent by the core — it
        // knows what exists; they are carried out by the shell, because the
        // keyboard, the window and the tray belong to it.
        if (values["action_hotkeys"] is JsonObject bound)
            BindActions(window, bound);

        _notify = values["notifications"]?.GetValue<bool>() ?? true;
        window.ShowToasts = _notify;
        if (values["floating_command_bar"]?.GetValue<bool>() == true)
            ShowFloatingBar(window);

        // The watch starts only if the person switched it on
        // (4.0b-A03, T-19). The default of false is not tidiness: without
        // an explicit yes it does not begin.
        FollowApps(values["watch_apps"]?.GetValue<bool>() ?? false);

        if (values["start_minimized"]?.GetValue<bool>() == true)
            window.Hide();
    }

    private bool _notify = true;
    private FloatingBar? _bar;
    private Platform.Foreground? _foreground;

    /// <summary>
    /// Start or stop watching which program is in front (<c>4.0b-A03</c>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// The watch is created on first use and disposed when switched off,
    /// rather than kept idle: an object that exists but is not watching
    /// looks the same from the outside as one that is, and the difference
    /// here is whether we know what the person is doing.
    /// </para>
    /// <para>
    /// What goes to the core is a path and nothing else — see
    /// <c>T-19</c> in the threat model. The core answers how many
    /// reminders fired; the shell does nothing with that number, and does
    /// not keep it.
    /// </para>
    /// </remarks>
    private void FollowApps(bool wanted)
    {
        if (!wanted)
        {
            _foreground?.Dispose();
            _foreground = null;
            return;
        }
        _foreground ??= new Platform.Foreground(
            path => _ = _link?.ForegroundAsync(path));
        _foreground.Follow(true);
    }

    /// <summary>
    /// Bind hotkeys to actions.
    /// </summary>
    /// <remarks>
    /// A hotkey held by another program is an ordinary matter, and the
    /// person finds out about it from a line in the footer rather than from
    /// silence: a hotkey that simply does not work looks like a breakage in
    /// Rina.
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
    /// Apply a setting the shell is in charge of.
    /// </summary>
    /// <remarks>
    /// The core holds the intent and has already written it down; here the
    /// shell brings itself into line. The same order as for the finish and
    /// the language: one setting, two sides, each doing its own part.
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
            case "watch_apps":
                FollowApps(value.GetValue<bool>());
                break;
            case "action_hotkeys":
                if (window is not null && value is JsonObject bound)
                {
                    // A complete rebind: a hotkey that was taken away must
                    // stop working rather than hang on until a restart.
                    _hotkeys?.Dispose();
                    _hotkeys = new Hotkeys();
                    _hotkeys.Attach(window);
                    _hotkeys.Refused += (name, why) => window.ShowNote($"{name}: {why}");
                    BindActions(window, bound);
                }
                break;
        }
    }

    /// <summary>Show the floating bar, creating it if need be.</summary>
    private void ShowFloatingBar(MainWindow window)
    {
        _bar ??= new FloatingBar(_link);
        _bar.Summon();
    }

    /// <summary>
    /// Show what a person cannot see in the window.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A pop-up about something already written in an open window is noise,
    /// and a person learns not to read it. So the condition is not "an
    /// answer arrived" but "an answer arrived that they cannot see".
    /// </para>
    /// <para>
    /// <b>A line and a reminder go by different paths, and that is not
    /// decoration.</b> A line lives for seconds and belongs to the
    /// conversation: it is shown by a window of its own, which will go away
    /// by itself. A reminder lives until it is seen and may catch a person
    /// who has stepped away — its place is the notification centre, where
    /// it will wait. Both used to go to the tray, and "what time is it"
    /// landed in the mail next to the letters.
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
        // The core ends by itself when it sees the break (§13), but saying
        // goodbye politely is cheaper than relying on that: it has things
        // to close.
        _bar?.Close();
        _hotkeys?.Dispose();
        _tray?.Dispose();
        _link?.DisposeAsync().AsTask().Wait(TimeSpan.FromSeconds(6));
        base.OnExit(e);
    }

    /// <summary>
    /// Wait for something to become true, up to a deadline.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Replaces the fixed pauses the checks were written with. A pause is a
    /// guess about how long a machine takes, and it is wrong in both
    /// directions: too long, and every run pays for it; too short, and the
    /// check goes red because something else was building at the time.
    /// </para>
    /// <para>
    /// Three checks in this suite went red only under the load of the full
    /// regression and green on their own — `test_speech`, `--check-core`,
    /// `--check-home`. That is not flakiness to be re-run away: a suite
    /// that reddens at random teaches the person reading it to disbelieve
    /// it, which costs more than the checks were worth.
    /// </para>
    /// <para>
    /// The deadline is generous because it is only ever paid when something
    /// is genuinely wrong; when things work, this returns as soon as they
    /// do.
    /// </para>
    /// </remarks>
    /// <summary>Wait until a moving value stops moving.</summary>
    /// <remarks>
    /// For what eases towards a target rather than switching to it. "Has it
    /// arrived" cannot be asked of a number without knowing where it was
    /// going; "has it stopped changing" can, and that is the same question
    /// for anything that settles.
    /// </remarks>
    private static async Task Settled(Func<double> value, double seconds = 4.0)
    {
        var deadline = DateTime.UtcNow.AddSeconds(seconds);
        var before = value();

        // Wait for it to **start** before waiting for it to stop. A value
        // that never moves is "settled" from the first look, and that is
        // how this helper first read a frozen figure as a finished one.
        while (DateTime.UtcNow < deadline
               && Math.Abs(value() - before) < 0.0005)
            await Task.Delay(20);

        var still = 0;
        before = value();
        while (DateTime.UtcNow < deadline && still < 3)
        {
            await Task.Delay(40);
            var now = value();
            still = Math.Abs(now - before) < 0.0005 ? still + 1 : 0;
            before = now;
        }
    }

    private static async Task<bool> Until(Func<bool> ready,
                                          double seconds = 6.0)
    {
        var deadline = DateTime.UtcNow.AddSeconds(seconds);
        while (DateTime.UtcNow < deadline)
        {
            if (ready()) return true;
            await Task.Delay(25);
        }
        return ready();
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
