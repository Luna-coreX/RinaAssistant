using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell;

/// <summary>
/// The window's link to the core: state, finish, events.
/// </summary>
/// <remarks>
/// <para>
/// Plan items <c>4.0-F07</c> (themes) and <c>4.0-F12</c> (showing the
/// link).
/// </para>
/// <para>
/// <b>Everything that comes from the core is carried into the window's
/// thread.</b> The reading pump lives in a thread of its own, and elements
/// may only be touched from the interface thread. This is exactly the
/// reason a Qt adapter existed in 3.1.0: the core always worked in the
/// background, and all that changed is that it now sits in another
/// process.
/// </para>
/// <para>
/// <b>The finish is chosen by the person and stored by the core.</b> The
/// shell does not read the settings file — it asks (<c>4.0-B06</c>,
/// ADR 0006). Until the core answers, the window is already drawn with the
/// default finish: waiting for the core in order to show the window would
/// make startup a hostage of another process.
/// </para>
/// </remarks>
public sealed class CoreLink : IAsyncDisposable
{
    private const string FinishKey = "finish";

    private readonly MainWindow _window;
    private readonly CoreSupervisor _boss;

    public CoreLink(MainWindow window, CoreLaunch launch)
    {
        _window = window;
        _boss = new CoreSupervisor(launch);

        _boss.StateChanged += (state, why) => OnUi(() =>
            _window.ShowCoreState(state, why));

        // Not `OnUi(async () => ...)`: the `Func<Task>` overload called
        // itself, because `() => _ = work()` is a `Func<Task>` too. A stack
        // overflow on the very first connection. The overload is gone: the
        // caller starts anything asynchronous, and one and the same simple
        // function does the carrying into the window's thread.
        _boss.Connected += connection => OnUi(
            () => { _ = LoadFinishAsync(connection); });

        _boss.Connected += connection => OnUi(
            () => { _ = LoadLanguageAsync(connection); });

        _boss.EventReceived += message => OnUi(() =>
        {
            _window.OnCoreEvent(message);
            CoreEvent?.Invoke(message);
        });

        _boss.Connected += connection =>
            connection.RequestReceived += request => OnUi(
                () => { _ = OnCoreRequestAsync(connection, request); });

        // Sound is set up together with the link. Before that it was
        // absent from the live program altogether: `AudioLink` existed, was
        // checked, and was created by nobody but the check itself. The core
        // dutifully synthesised and sent speech into a data channel nobody
        // read — Rina answered in text and stayed silent.
        _boss.Connected += connection => OnUi(() => StartVoice(connection));

        // Plugin sections appear once the core is connected: before that
        // there is nobody to ask.
        _boss.Connected += connection => OnUi(
            () => { _ = RefreshPluginSectionsAsync(); });
    }

    /// <summary>
    /// Ask which plugins have a page of their own and give them a section.
    /// </summary>
    /// <remarks>
    /// Called after a plugin is switched on as well: the section must
    /// appear at once rather than after a restart. The list comes from the
    /// core whole, and the shell compares it with its own — that way
    /// switching off takes the section away without a separate message
    /// about it.
    /// </remarks>
    public async Task RefreshPluginSectionsAsync()
    {
        if (_boss.Connection is not { Ready: true } connection) return;
        if (!connection.MayCall(Methods.PluginsList)) return;

        try
        {
            var answer = await connection.CallAsync(Methods.PluginsList, null,
                                                    TimeSpan.FromSeconds(15));
            if (answer.IsError) return;

            var listed = (answer.Payload["items"]?.AsArray() ?? [])
                .OfType<JsonObject>()
                .Where(p => p["enabled"]?.GetValue<bool>() == true
                            && p["has_page"]?.GetValue<bool>() == true)
                .Select(p => (p["plugin_id"]?.GetValue<string>() ?? "",
                              p["page_title"]?.GetValue<string>()
                              ?? p["name"]?.GetValue<string>() ?? "",
                              p["page_icon"]?.GetValue<string>() ?? ""))
                .Where(p => p.Item1.Length > 0)
                .ToList();

            OnUi(() => _window.ShowPluginSections(listed));
        }
        catch
        {
            // We did not get to ask — the column stays as it was. A
            // plugin's section is not worth showing a person an error for.
        }
    }

    private Audio.Speaker? _speaker;
    private Audio.AudioLink? _voice;

    /// <summary>The speaker and the sound channel; `null` while there is no link.</summary>
    public Audio.AudioLink? Voice => _voice;

    /// <summary>
    /// Set up sound on a new link.
    /// </summary>
    /// <remarks>
    /// The old household is thrown away: a new link means a different core,
    /// and the previous core's speech stream is not continued but begun
    /// afresh.
    /// </remarks>
    private void StartVoice(CoreConnection connection)
    {
        _voice?.Dispose();
        _speaker?.Dispose();

        _speaker = new Audio.Speaker();
        _voice = new Audio.AudioLink(connection, connection.Data,
                                     new Audio.Microphone(), _speaker);

        // The strip shows a real level rather than one and the same
        // number: an instrument whose needle knows two positions is a lamp.
        _voice.Level += level => OnUi(() => _window.ShowLevel(level));
        _ = ApplyAudioSettingsAsync();
    }

    /// <summary>The devices the person chose — from the core's settings.</summary>
    private async Task ApplyAudioSettingsAsync()
    {
        var values = await GetAsync("input_device", "output_device");
        if (values is null || _voice is null) return;
        _voice.UseDevices(values["input_device"]?.GetValue<string>() ?? "default",
                          values["output_device"]?.GetValue<string>() ?? "default");
    }

    public CoreState State => _boss.State;

    /// <summary>Which attempt at raising the core is under way.</summary>
    public int Attempt => _boss.Attempt;

    /// <summary>The current link; `null` while there is none.</summary>
    public CoreConnection? Connection => _boss.Connection;

    /// <summary>Core events for the pages. Already in the window's thread.</summary>
    public event Action<Envelope>? CoreEvent;

    public Task StartAsync() => _boss.StartAsync();

    /// <summary>Ask the core for the interface language and apply it.</summary>
    /// <remarks>
    /// There is one setting for the whole program and it lives in the core,
    /// while each side translates itself
    /// ([ADR 0007](../../docs/adr/0007-localisation.md)): the interface's
    /// words belong to the shell, Rina's lines to the core.
    /// </remarks>
    private async Task LoadLanguageAsync(CoreConnection connection)
    {
        try
        {
            var answer = await connection.CallAsync(Methods.SettingsGet,
                new JsonObject { ["keys"] = new JsonArray(LanguageKey) },
                TimeSpan.FromSeconds(10));
            var language = answer.Payload["values"]?[LanguageKey]
                           ?.GetValue<string>();
            if (language is not null) OnUi(() => Strings.Loc.Use(language));
        }
        catch
        {
            // We did not get to ask — we stay in the original language. A
            // program in Russian is better than a program that did not open
            // because of a language.
        }
    }

    private const string LanguageKey = "ui_language";

    /// <summary>Ask the core for the chosen finish and apply it.</summary>
    private async Task LoadFinishAsync(CoreConnection connection)
    {
        try
        {
            var answer = await connection.CallAsync(Methods.SettingsGet,
                new JsonObject
                {
                    ["keys"] = new JsonArray(FinishKey, "accent"),
                }, TimeSpan.FromSeconds(10));
            var finish = answer.Payload["values"]?[FinishKey]?.GetValue<string>();
            var accent = answer.Payload["values"]?["accent"]?.GetValue<string>();
            if (finish is not null) OnUi(() =>
            {
                App.ApplyFinish(finish);
                // The accent after the finish: it replaces the finish's
                // colours, and the reverse order would bring the original
                // back for the very first frame.
                App.ApplyAccent(finish, accent ?? App.DefaultAccent);
                _window.ShowFinish(finish);
            });
        }
        catch
        {
            // We could not ask — we stay with the one already drawn. A
            // finish is not worth showing a person an error for.
        }
    }

    /// <summary>Read the settings the shell is in charge of.</summary>
    /// <remarks>
    /// The tray, autostart and hotkeys are stored in the core and carried
    /// out by the shell: the core holds the intent, the shell brings the
    /// system into line. The registry and the keyboard are the system, and
    /// in 4.0 the system layer belongs to the shell.
    /// </remarks>
    public async Task<JsonObject?> GetAsync(params string[] keys)
    {
        if (_boss.Connection is not { Ready: true } connection) return null;
        try
        {
            var answer = await connection.CallAsync(Methods.SettingsGet,
                new JsonObject
                {
                    ["keys"] = new JsonArray(keys.Select(k => (JsonNode)k!)
                                                 .ToArray()),
                }, TimeSpan.FromSeconds(10));
            return answer.IsError ? null : answer.Payload["values"]?.AsObject();
        }
        catch { return null; }
    }

    /// <summary>Change the finish and remember the choice in the core.</summary>
    public async Task SetFinishAsync(string finish)
    {
        App.ApplyFinish(finish);
        if (_boss.Connection is not { Ready: true } connection) return;
        try
        {
            await connection.CallAsync(Methods.SettingsSet, new JsonObject
            {
                ["values"] = new JsonObject { [FinishKey] = finish },
            }, TimeSpan.FromSeconds(10));
        }
        catch
        {
            // Already shown; if it was not remembered we shall find out at the next start.
        }
    }

    /// <summary>
    /// The core asks for permission — ask the person (<c>4.0-F11</c>, §11).
    /// </summary>
    /// <remarks>
    /// <para>
    /// One window for everything dangerous: two simultaneous questions
    /// about something irreversible are two ways of agreeing without
    /// looking.
    /// </para>
    /// <para>
    /// <b>Refusal by default.</b> Whatever happens — the window was closed,
    /// the deadline passed, the shell did not understand the request — the
    /// answer is "no". Consent is only ever explicit.
    /// </para>
    /// </remarks>
    private async Task OnCoreRequestAsync(CoreConnection connection,
                                          Envelope request)
    {
        // --- the system layer (ADR 0009) -------------------------------
        // The core decided what to do; the shell touches the machine. The
        // answer is a fact, not a suggestion: the words are the core's to
        // say.
        if (request.Method == "system.do")
        {
            var action = request.Payload["action"]?.GetValue<string>() ?? "";
            var (ok, detail) = Platform.Machine.Do(action);
            Platform.Journal.Action(action, ok);
            await connection.ReplyAsync(request, new JsonObject
            {
                ["ok"] = ok,
                ["detail"] = detail,
            });
            return;
        }

        if (request.Method == "apps.index")
        {
            await ReplyIndexAsync(connection, request);
            return;
        }

        if (request.Method == "apps.launch")
        {
            var launch = request.Payload["launch"]?.GetValue<string>() ?? "";
            var kind = request.Payload["kind"]?.GetValue<string>() ?? "file";
            var outcome = Platform.Launcher.Start(launch, kind, trusted: false);

            // Something unsigned needs consent on its first launch. The
            // shell asks, not the core: the shell has the window, and the
            // shell is what sees the signature.
            if (outcome.NeedsTrust)
                outcome = await AskTrustAsync(launch, kind);

            await connection.ReplyAsync(request, new JsonObject
            {
                ["ok"] = outcome.Ok,
                ["reason"] = outcome.Reason,
            });
            return;
        }

        // The core opens a speech stream with a request of its own: sound
        // has a format, and the rate is declared rather than guessed. An
        // answer is obligatory — otherwise the core waits in silence.
        if (request.Method == Methods.StreamOpen)
        {
            var kind = request.Payload["kind"]?.GetValue<string>() ?? "";
            var rate = request.Payload["format"]?["rate"]?.GetValue<int>()
                       ?? Audio.Microphone.SampleRate;
            // The core puts the stream number in the envelope; without it there is nothing to open.
            var stream = request.StreamId
                         ?? request.Payload["stream_id"]?.GetValue<int>() ?? 0;
            var credit = stream == 0
                         ? 0 : _voice?.StartPlayback(stream, kind, rate) ?? 0;
            await connection.ReplyAsync(request, new JsonObject
            {
                ["accepted"] = credit > 0,
                ["credit"] = credit,
            });
            return;
        }

        if (request.Method == Methods.StreamClose)
        {
            _voice?.StopPlayback();
            await connection.ReplyAsync(request, new JsonObject
            {
                ["closed"] = true,
            });
            return;
        }

        if (request.Method != Methods.PermissionRequest)
        {
            // A method the shell does not know is no reason to stay
            // silent: the core is waiting for an answer, and silence turns
            // into its timeout.
            await connection.ReplyAsync(request, new JsonObject
            {
                ["granted"] = false,
                // The reason goes to the core and to the log, not to the person.
                ["reason"] = "the shell does not know this request", // not UI
            });
            return;
        }

        var preview = request.Payload["preview"]?.GetValue<string>()
                      ?? S("Точно выполнить?");
        var reason = request.Payload["reason"]?.GetValue<string>() ?? "";
        var ttl = request.Payload["ttl"]?.GetValue<int>() ?? 60;

        var granted = false;
        try
        {
            _asking?.Withdraw();
            var window = new Pages.ConfirmWindow(preview, reason, ttl);
            if (_window.IsVisible) window.Owner = _window;
            _asking = window;
            window.ShowDialog();
            granted = window.Result == Pages.Consent.Granted;
        }
        catch
        {
            granted = false;        // не смогли спросить — значит не разрешено
        }
        finally
        {
            _asking = null;
        }

        await connection.ReplyAsync(request, new JsonObject
        {
            ["request_id"] = request.Payload["request_id"]?.DeepClone(),
            ["granted"] = granted,
            ["scope"] = "once",
        });
    }

    private Pages.ConfirmWindow? _asking;

    /// <summary>Say to Rina what was typed.</summary>
    /// <remarks>
    /// The answer will come as an event rather than from this call: a
    /// command may think for seconds and say several things along the way.
    /// </remarks>
    public async Task HandleAsync(string text, string source = "typed")
    {
        if (_boss.Connection is not { Ready: true } connection) return;
        try
        {
            await connection.CallAsync(Methods.CommandHandle, new JsonObject
            {
                ["text"] = text,
                ["source"] = source,
                ["require_wake"] = false,
            }, TimeSpan.FromSeconds(15));
        }
        catch { /* ядро занято или ушло */ }
    }

    /// <summary>Toggle a setting the person is in charge of.</summary>
    public async Task<bool> SetAsync(string key, JsonNode value)
    {
        if (_boss.Connection is not { Ready: true } connection) return false;
        try
        {
            var answer = await connection.CallAsync(Methods.SettingsSet,
                new JsonObject
                {
                    ["values"] = new JsonObject { [key] = value },
                }, TimeSpan.FromSeconds(10));
            return !answer.IsError;
        }
        catch { return false; }
    }

    /// <summary>Listen once — on a hotkey.</summary>
    public async Task ListenOnceAsync()
    {
        if (_boss.Connection is not { Ready: true } connection) return;
        if (!connection.MayCall(Methods.SpeechListenOnce)) return;
        try
        {
            await connection.CallAsync(Methods.SpeechListenOnce, null,
                                       TimeSpan.FromSeconds(10));
        }
        catch { /* ядро занято или ушло */ }
    }

    /// <summary>
    /// Hand the core the program index.
    /// </summary>
    /// <remarks>
    /// Assembled in a background thread: walking the Start menu and
    /// checking signatures takes seconds, and doing that in the window's
    /// thread means freezing the window exactly where the person is waiting
    /// for an answer.
    /// </remarks>
    private async Task ReplyIndexAsync(CoreConnection connection,
                                       Envelope request)
    {
        var refresh = request.Payload["refresh"]?.GetValue<bool>() ?? false;
        var folders = (await GetAsync("program_folders"))?["program_folders"]
                      ?.AsArray().Select(f => f?.GetValue<string>() ?? "")
                      .Where(f => f.Length > 0).ToArray() ?? [];

        var entries = await Task.Run(
            () => Platform.AppIndex.Get(folders, refresh));

        var listed = new JsonArray();
        foreach (var entry in entries)
            listed.Add(new JsonObject
            {
                ["name"] = entry.Name,
                ["launch"] = entry.Launch,
                ["kind"] = entry.Kind,
                ["source"] = entry.Source,
                ["signed"] = entry.Signed,
                ["aliases"] = new JsonArray(
                    entry.Aliases.Select(a => (JsonNode)a!).ToArray()),
                ["checked_at"] = entry.CheckedAt
                    .ToString("yyyy-MM-ddTHH:mm:ssZ"),
            });

        await connection.ReplyAsync(request, new JsonObject
        {
            ["entries"] = listed,
        });
    }

    /// <summary>
    /// Ask about something unsigned and launch it if permission was given.
    /// </summary>
    /// <remarks>
    /// Everything one can decide by is shown: the name, the full path, the
    /// absence of a signature. "Always trust" is remembered and is taken
    /// back in settings (<c>4.0-G10</c>).
    /// </remarks>
    private async Task<Platform.Launcher.Outcome> AskTrustAsync(string launch,
                                                                string kind)
    {
        var path = Platform.AppIndex.Canonical(launch);
        var answer = await OnUiAsync(() =>
        {
            var source = Platform.AppIndex.Get()
                .FirstOrDefault(e => string.Equals(
                    e.Launch, path, StringComparison.OrdinalIgnoreCase))
                ?.Source ?? "";
            var ask = new Pages.TrustWindow(path, source);
            ask.ShowDialog();
            return ask.Answer;
        });

        if (answer == Pages.TrustWindow.Reply.Never)
            // The reason goes to the core, not to the person: Rina answers
            // in words. It is a code rather than a phrase — matching on a
            // substring of prose breaks on the first translation, and
            // breaks silently.
            return new Platform.Launcher.Outcome(false, "refused");

        if (answer == Pages.TrustWindow.Reply.Always)
            Platform.Trust.Remember(path);

        return Platform.Launcher.Start(launch, kind, trusted: true);
    }

    private static Task<T> OnUiAsync<T>(Func<T> work)
    {
        var dispatcher = Application.Current?.Dispatcher;
        if (dispatcher is null || dispatcher.CheckAccess())
            return Task.FromResult(work());
        return dispatcher.InvokeAsync(work).Task;
    }

    private static void OnUi(Action work)
    {
        var dispatcher = Application.Current?.Dispatcher;
        if (dispatcher is null || dispatcher.CheckAccess()) work();
        else dispatcher.BeginInvoke(work);
    }

    public ValueTask DisposeAsync() => _boss.DisposeAsync();

    /// <summary>Where the core lies relative to the shell.</summary>
    public static CoreLaunch FindCore()
    {
        var dir = AppContext.BaseDirectory;
        while (dir is not null && !File.Exists(Path.Combine(dir, "rina_core.py")))
            dir = Path.GetDirectoryName(dir);
        var root = dir ?? AppContext.BaseDirectory;
        return new CoreLaunch(Interpreter(root),
                              Path.Combine(root, "rina_core.py"), root);
    }

    /// <summary>
    /// Which Python to run the core with.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The project's environment, if there is one — and only then whatever
    /// `python` turns up in `PATH`. The difference is not cosmetic: the
    /// voices, the recognition models and the sound are installed <b>in the
    /// environment</b>, not in the system interpreter. A core started with
    /// "just python" comes up, answers everything, and honestly reports
    /// that there is not one synthesis engine and not one recognition
    /// engine — the program looks as if it works and does exactly none of
    /// what it exists for.
    /// </para>
    /// <para>
    /// In 3.1.0 the question did not arise: the program was started with
    /// the same interpreter it lived in. By splitting the processes we
    /// handed the choice of interpreter to the shell — and we are obliged
    /// to choose deliberately.
    /// </para>
    /// </remarks>
    public static string Interpreter(string root)
    {
        string[] candidates =
        [
            // Привезённый нами рантайм — первым (ADR 0011). У человека
            // сработает он и только он: это ровно тот интерпретатор, на
            // котором мы проверяли, и он не зависит от того, что стоит на
            // машине.
            Path.Combine(AppContext.BaseDirectory, "runtime", "python",
                         "python.exe"),

            // Дальше — разработка. Окружение проекта, потом `PATH`.
            Path.Combine(root, "venv", "Scripts", "python.exe"),
            Path.Combine(root, ".venv", "Scripts", "python.exe"),
        ];
        return candidates.FirstOrDefault(File.Exists) ?? "python";
    }
}
