using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell;

/// <summary>
/// Связь окна с ядром: состояние, отделка, события.
/// </summary>
/// <remarks>
/// <para>
/// Задачи плана <c>4.0-F07</c> (темы) и <c>4.0-F12</c> (индикация связи).
/// </para>
/// <para>
/// <b>Всё, что приходит от ядра, переносится в поток окна.</b> Насос чтения
/// живёт в своём потоке, а трогать элементы можно только из потока
/// интерфейса. Это ровно та причина, по которой в 3.1.0 существовал
/// Qt-адаптер: ядро всегда работало в фоне, менялось лишь то, что теперь
/// оно в другом процессе.
/// </para>
/// <para>
/// <b>Отделку выбирает человек, а хранит ядро.</b> Оболочка не читает файл
/// настроек — она спрашивает (<c>4.0-B06</c>, ADR 0006). Пока ядро не
/// ответило, окно уже нарисовано с той отделкой, что стоит по умолчанию:
/// ждать ядра, чтобы показать окно, значило бы сделать запуск заложником
/// чужого процесса.
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

        // Не `OnUi(async () => ...)`: перегрузка по `Func<Task>` вызывала
        // саму себя, потому что `() => _ = work()` — тоже `Func<Task>`.
        // Переполнение стека при первом же подключении. Перегрузки больше
        // нет: асинхронное запускает вызывающий, а перенос в поток окна
        // делает одна и та же простая функция.
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

        // Звук заводится вместе со связью. До этого его в живой программе
        // не было вовсе: `AudioLink` существовал, был проверен и не создан
        // никем, кроме самой проверки. Ядро исправно синтезировало и слало
        // речь в канал данных, который никто не читал, — Рина отвечала
        // текстом и молчала.
        _boss.Connected += connection => OnUi(() => StartVoice(connection));
    }

    private Audio.Speaker? _speaker;
    private Audio.AudioLink? _voice;

    /// <summary>Динамик и канал звука; `null`, пока нет связи.</summary>
    public Audio.AudioLink? Voice => _voice;

    /// <summary>
    /// Завести звук на новой связи.
    /// </summary>
    /// <remarks>
    /// Старое хозяйство выбрасывается: связь новая — значит ядро другое, и
    /// поток речи прежнего ядра не продолжается, а начинается заново.
    /// </remarks>
    private void StartVoice(CoreConnection connection)
    {
        _voice?.Dispose();
        _speaker?.Dispose();

        _speaker = new Audio.Speaker();
        _voice = new Audio.AudioLink(connection, connection.Data,
                                     new Audio.Microphone(), _speaker);
        _ = ApplyAudioSettingsAsync();
    }

    /// <summary>Выбранные человеком устройства — из настроек ядра.</summary>
    private async Task ApplyAudioSettingsAsync()
    {
        var values = await GetAsync("input_device", "output_device");
        if (values is null || _voice is null) return;
        _voice.UseDevices(values["input_device"]?.GetValue<string>() ?? "default",
                          values["output_device"]?.GetValue<string>() ?? "default");
    }

    public CoreState State => _boss.State;

    /// <summary>Текущая связь; `null`, пока её нет.</summary>
    public CoreConnection? Connection => _boss.Connection;

    /// <summary>События ядра для страниц. Уже в потоке окна.</summary>
    public event Action<Envelope>? CoreEvent;

    public Task StartAsync() => _boss.StartAsync();

    /// <summary>Спросить у ядра язык интерфейса и применить его.</summary>
    /// <remarks>
    /// Настройка одна на программу и живёт в ядре, а переводит себя каждая
    /// сторона сама ([ADR 0007](../../docs/adr/0007-localisation.md)):
    /// слова интерфейса — оболочка, реплики Рины — ядро.
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
            // Не спросили — остаёмся на языке оригинала. Программа на
            // русском лучше, чем программа, не открывшаяся из-за языка.
        }
    }

    private const string LanguageKey = "ui_language";

    /// <summary>Спросить у ядра выбранную отделку и применить её.</summary>
    private async Task LoadFinishAsync(CoreConnection connection)
    {
        try
        {
            var answer = await connection.CallAsync(Methods.SettingsGet,
                new JsonObject { ["keys"] = new JsonArray(FinishKey) },
                TimeSpan.FromSeconds(10));
            var finish = answer.Payload["values"]?[FinishKey]?.GetValue<string>();
            if (finish is not null) OnUi(() =>
            {
                App.ApplyFinish(finish);
                _window.ShowFinish(finish);
            });
        }
        catch
        {
            // Не смогли спросить — остаёмся с той, что уже нарисована.
            // Отделка не то, ради чего стоит показывать человеку ошибку.
        }
    }

    /// <summary>Прочитать настройки, которыми распоряжается оболочка.</summary>
    /// <remarks>
    /// Трей, автозапуск и хоткеи хранятся в ядре, а исполняются оболочкой:
    /// ядро хранит намерение, оболочка приводит систему в соответствие.
    /// Реестр и клавиатура — система, а системный слой в 4.0 принадлежит
    /// оболочке.
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

    /// <summary>Сменить отделку и запомнить выбор в ядре.</summary>
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
            // Показали уже; не запомнилось — узнаем при следующем запуске.
        }
    }

    /// <summary>
    /// Ядро просит разрешения — спросить человека (<c>4.0-F11</c>, §11).
    /// </summary>
    /// <remarks>
    /// <para>
    /// Окно одно на всё опасное: два одновременных вопроса о необратимом —
    /// это два способа согласиться не глядя.
    /// </para>
    /// <para>
    /// <b>Отказ по умолчанию.</b> Что бы ни случилось — закрыли окно, истёк
    /// срок, оболочка не поняла запрос — ответ «нет». Согласие бывает только
    /// явным.
    /// </para>
    /// </remarks>
    private async Task OnCoreRequestAsync(CoreConnection connection,
                                          Envelope request)
    {
        // Ядро открывает поток речи своим запросом: у звука есть формат, и
        // частоту объявляют, а не угадывают. Ответить обязательно — иначе
        // ядро ждёт и молчит.
        if (request.Method == Methods.StreamOpen)
        {
            var kind = request.Payload["kind"]?.GetValue<string>() ?? "";
            var rate = request.Payload["format"]?["rate"]?.GetValue<int>()
                       ?? Audio.Microphone.SampleRate;
            // Ядро кладёт номер потока в конверт; без него открывать нечего.
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
            // Метод, которого оболочка не знает, — не повод молчать: ядро
            // ждёт ответа, и молчание превратится в его таймаут.
            await connection.ReplyAsync(request, new JsonObject
            {
                ["granted"] = false,
                // Причина уезжает в ядро и в журнал, а не человеку.
                ["reason"] = "оболочка не умеет этот запрос", // не интерфейс
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

    /// <summary>Сказать Рине то, что набрано.</summary>
    /// <remarks>
    /// Ответ придёт событием, а не этим вызовом: команда может думать
    /// секундами и сказать по дороге несколько вещей.
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

    /// <summary>Переключить настройку, которой распоряжается человек.</summary>
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

    /// <summary>Послушать один раз — по сочетанию клавиш.</summary>
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

    private static void OnUi(Action work)
    {
        var dispatcher = Application.Current?.Dispatcher;
        if (dispatcher is null || dispatcher.CheckAccess()) work();
        else dispatcher.BeginInvoke(work);
    }

    public ValueTask DisposeAsync() => _boss.DisposeAsync();

    /// <summary>Где лежит ядро относительно оболочки.</summary>
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
    /// Каким Python запускать ядро.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Окружение проекта, если оно есть, — и только потом тот `python`,
    /// который найдётся в `PATH`. Разница не косметическая: голоса, модели
    /// распознавания и звук стоят <b>в окружении</b>, а не в системном
    /// интерпретаторе. Запущенное «просто питоном» ядро поднимается, отвечает
    /// на всё и честно сообщает, что ни одного движка синтеза и ни одного
    /// движка распознавания нет, — программа выглядит работающей и не делает
    /// ровно того, ради чего она есть.
    /// </para>
    /// <para>
    /// В 3.1.0 вопроса не было: программу запускали тем же интерпретатором,
    /// в котором она жила. Разделив процессы, мы отдали выбор интерпретатора
    /// оболочке — и обязаны выбирать осознанно.
    /// </para>
    /// </remarks>
    public static string Interpreter(string root)
    {
        string[] candidates =
        [
            Path.Combine(root, "venv", "Scripts", "python.exe"),
            Path.Combine(root, ".venv", "Scripts", "python.exe"),
        ];
        return candidates.FirstOrDefault(File.Exists) ?? "python";
    }
}
