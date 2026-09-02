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
