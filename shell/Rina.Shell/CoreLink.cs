using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using Rina.Protocol;

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

        _boss.EventReceived += message => OnUi(() =>
        {
            _window.OnCoreEvent(message);
            CoreEvent?.Invoke(message);
        });

        _boss.Connected += connection =>
            connection.RequestReceived += request => OnUi(
                () => { _ = OnCoreRequestAsync(connection, request); });
    }

    public CoreState State => _boss.State;

    /// <summary>Текущая связь; `null`, пока её нет.</summary>
    public CoreConnection? Connection => _boss.Connection;

    /// <summary>События ядра для страниц. Уже в потоке окна.</summary>
    public event Action<Envelope>? CoreEvent;

    public Task StartAsync() => _boss.StartAsync();

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
        if (request.Method != Methods.PermissionRequest)
        {
            // Метод, которого оболочка не знает, — не повод молчать: ядро
            // ждёт ответа, и молчание превратится в его таймаут.
            await connection.ReplyAsync(request, new JsonObject
            {
                ["granted"] = false,
                ["reason"] = "оболочка не умеет этот запрос",
            });
            return;
        }

        var preview = request.Payload["preview"]?.GetValue<string>()
                      ?? "Точно выполнить?";
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
        return new CoreLaunch("python", Path.Combine(root, "rina_core.py"), root);
    }
}
