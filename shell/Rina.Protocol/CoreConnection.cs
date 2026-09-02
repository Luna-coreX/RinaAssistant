using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.Json.Nodes;
using Rina.Protocol.Transport;

namespace Rina.Protocol;

/// <summary>Как запускать ядро.</summary>
/// <param name="Python">Интерпретатор.</param>
/// <param name="Script">Путь к <c>rina_core.py</c>.</param>
/// <param name="WorkingDirectory">Корень проекта.</param>
/// <param name="ExtraArguments">Что дописать к строке запуска, например уровень журнала.</param>
public sealed record CoreLaunch(string Python, string Script,
                                string WorkingDirectory,
                                IReadOnlyList<string>? ExtraArguments = null);

/// <summary>
/// Одна связь оболочки с ядром: процесс, каналы, рукопожатие, разговор.
/// </summary>
/// <remarks>
/// <para>
/// Порядок обязателен и неочевиден: <b>сначала подняты трубы, потом запущено
/// ядро</b>. Ядро подключается клиентом и ждёт появления канала; если запустить
/// его раньше, оно будет ждать впустую ровно столько, сколько мы провозимся с
/// созданием труб. Обратный порядок работал бы почти всегда — и тем хуже.
/// </para>
/// <para>
/// <b>Канал читает один насос, а не тот, кто спросил.</b> Первая редакция
/// читала прямо в <c>CallAsync</c>, и это работало ровно до второго читателя:
/// события приходят без запроса, и услышать их некому, пока никто ничего не
/// спрашивает. Теперь ответы разбираются по <c>correlation_id</c>, а события
/// уходят подписчикам — это же нужно и надзору (<c>4.0-E07</c>), которому
/// слышать канал надо постоянно.
/// </para>
/// <para>
/// Ответ на команду — <c>accepted</c>, а не текст: сам ответ приходит событием
/// <c>assistant.response</c>, когда появится.
/// </para>
/// </remarks>
public sealed class CoreConnection : IAsyncDisposable
{
    private readonly IdGenerator _ids = new("s-");
    private readonly ControlChannel _control;
    private readonly DataChannel _data;
    private readonly ConcurrentDictionary<string, TaskCompletionSource<Envelope>>
        _pending = new();
    private readonly System.Text.StringBuilder _coreLog = new();
    private readonly CancellationTokenSource _stopping = new();
    private Process? _core;
    private Task? _pump;

    public string Session { get; }
    public int NegotiatedVersion { get; private set; }
    public IReadOnlyList<string> CoreCapabilities { get; private set; } = [];
    public string CoreVersion { get; private set; } = "";
    public string SessionId { get; private set; } = "";
    public bool Ready { get; private set; }

    /// <summary>События ядра, пришедшие без запроса (§10).</summary>
    public event Action<Envelope>? EventReceived;

    /// <summary>Связь оборвалась: ядро умерло или закрыло канал.</summary>
    public event Action<string>? Broken;

    /// <summary>
    /// Ядро о чём-то просит (§1: у него ровно два вида запросов — разрешение
    /// и данные, которыми владеет оболочка).
    /// </summary>
    public event Action<Envelope>? RequestReceived;

    /// <summary>Незнакомые события: их игнорируют молча, но считать полезно.</summary>
    public List<string> IgnoredEvents { get; } = [];

    /// <summary>Канал данных: звук и кадры экрана, мимо JSON (§2).</summary>
    public DataChannel Data => _data;

    /// <summary>Когда в последний раз что-либо пришло от ядра (§13).</summary>
    public DateTimeOffset LastHeard { get; private set; } = DateTimeOffset.UtcNow;

    public CoreConnection(string? session = null)
    {
        Session = session ?? Guid.NewGuid().ToString("N")[..12];
        _control = new ControlChannel(Session, "control");
        _data = new DataChannel(Session);
    }

    public async Task StartAsync(CoreLaunch launch, TimeSpan timeout,
                                 CancellationToken token = default)
    {
        var accepting = Task.WhenAll(_control.AcceptAsync(token),
                                     _data.AcceptAsync(token));

        var start = new ProcessStartInfo
        {
            FileName = launch.Python,
            ArgumentList = { "-u", launch.Script, "--transport", "pipe",
                             "--session", Session },
            WorkingDirectory = launch.WorkingDirectory,
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            UseShellExecute = false,
        };
        foreach (var extra in launch.ExtraArguments ?? [])
            start.ArgumentList.Add(extra);

        _core = Process.Start(start)
            ?? throw new InvalidOperationException("ядро не запустилось");

        // Журнал ядра вычитывается сразу и в фоне. Не только ради отладки:
        // труба невелика, и процесс, которому некуда писать в поток ошибок,
        // однажды встанет на записи в него. К тому же 4.0-F12 обязан
        // показывать состояние связи, а последняя строка журнала ядра —
        // самое внятное, что можно показать при обрыве.
        _core.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null) lock (_coreLog) _coreLog.AppendLine(e.Data);
        };
        _core.BeginErrorReadLine();

        // Ядро может умереть, не подключившись, — и тогда ждать трубу до
        // конца срока бессмысленно. Ждём оба исхода сразу.
        var exited = WaitForExitAsync(_core);
        var done = await Task.WhenAny(accepting, exited, Task.Delay(timeout, token))
                             .ConfigureAwait(false);
        if (done == exited)
            throw new ChannelClosedException(
                $"ядро вышло с кодом {_core.ExitCode}, не подключившись");
        if (done != accepting)
            throw new ChannelClosedException(
                $"ядро не подключилось за {timeout.TotalSeconds:0} с");
        await accepting.ConfigureAwait(false);

        _pump = Task.Run(PumpAsync);
    }

    private static Task WaitForExitAsync(Process process)
    {
        var tcs = new TaskCompletionSource();
        process.EnableRaisingEvents = true;
        process.Exited += (_, _) => tcs.TrySetResult();
        if (process.HasExited) tcs.TrySetResult();
        return tcs.Task;
    }

    /// <summary>Единственный читатель канала.</summary>
    private async Task PumpAsync()
    {
        try
        {
            while (!_stopping.IsCancellationRequested)
            {
                var message = await _control.ReceiveAsync(_stopping.Token)
                                            .ConfigureAwait(false);
                LastHeard = DateTimeOffset.UtcNow;

                if (message.IsEvent) { Dispatch(message); continue; }

                if (message.Type == MessageType.Request)
                {
                    RequestReceived?.Invoke(message);
                    continue;
                }

                if (message.CorrelationId is { } id
                    && _pending.TryRemove(id, out var waiting))
                    waiting.TrySetResult(message);
                // Ответ на запрос, которого никто не ждёт, — не повод падать:
                // ждавший мог сдаться по своему сроку.
            }
        }
        catch (OperationCanceledException) { /* закрываемся */ }
        catch (Exception e)
        {
            Ready = false;
            FailPending(e);
            Broken?.Invoke(e.Message);
        }
    }

    private void FailPending(Exception cause)
    {
        foreach (var id in _pending.Keys.ToArray())
            if (_pending.TryRemove(id, out var waiting))
                waiting.TrySetException(cause);
    }

    /// <summary>Рукопожатие (§4): версии наборами, возможности списком.</summary>
    public async Task HandshakeAsync(CancellationToken token = default)
    {
        var hello = new JsonObject
        {
            ["protocol_versions"] = new JsonArray(ProtocolVersion.Current),
            ["shell_version"] = "4.0.0",
            ["capabilities"] = new JsonArray(
                Capabilities.Shell.Select(c => (JsonNode)c!).ToArray()),
            ["locale"] = "ru",
        };

        var answer = await CallAsync(Methods.Hello, hello, token: token)
            .ConfigureAwait(false);
        if (answer.IsError)
            throw new ProtocolException(answer.ErrorCode, answer.ErrorMessage);

        NegotiatedVersion = answer.Payload["protocol_version"]?.GetValue<int>() ?? 0;
        if (NegotiatedVersion != ProtocolVersion.Current)
            throw new ProtocolException(
                ErrorCodes.ProtocolIncompatible,
                $"ядро выбрало версию {NegotiatedVersion}, оболочка понимает "
                + ProtocolVersion.Current);

        CoreCapabilities = answer.Payload["capabilities"]?.AsArray()
            .Select(n => n!.GetValue<string>()).ToArray() ?? [];
        CoreVersion = answer.Payload["core_version"]?.GetValue<string>() ?? "";
        SessionId = answer.Payload["session_id"]?.GetValue<string>() ?? "";
        Ready = true;
    }

    /// <summary>Умеет ли ядро этот метод (§4).</summary>
    public bool MayCall(string method)
    {
        if (!Ready) return false;
        if (!Methods.Capability.TryGetValue(method, out var capability))
            return false;
        return capability is null || CoreCapabilities.Contains(capability);
    }

    /// <summary>Запрос и ответ на него.</summary>
    public async Task<Envelope> CallAsync(string method, JsonObject? payload = null,
                                          TimeSpan? timeout = null,
                                          CancellationToken token = default,
                                          string? traceId = null)
    {
        var request = Envelope.Request(method, payload, _ids.Next(),
                                       traceId ?? Trace.New());
        var waiting = new TaskCompletionSource<Envelope>(
            TaskCreationOptions.RunContinuationsAsynchronously);
        _pending[request.Id] = waiting;

        try
        {
            await _control.SendAsync(request, token).ConfigureAwait(false);
            var limit = timeout ?? TimeSpan.FromSeconds(30);
            var done = await Task.WhenAny(waiting.Task, Task.Delay(limit, token))
                                 .ConfigureAwait(false);
            if (done != waiting.Task)
                throw new TimeoutException(
                    $"ядро не ответило на {method} за {limit.TotalSeconds:0} с");
            return await waiting.Task.ConfigureAwait(false);
        }
        finally
        {
            _pending.TryRemove(request.Id, out _);
        }
    }

    /// <summary>
    /// Ответить на запрос ядра.
    /// </summary>
    /// <remarks>
    /// Трассировка и версия наследуются от запроса: сквозная цепочка (§14)
    /// обязана быть свойством конструкции, иначе её однажды забудут.
    /// </remarks>
    public async Task ReplyAsync(Envelope request, JsonObject payload,
                                 CancellationToken token = default)
    {
        var answer = new Envelope
        {
            Type = MessageType.Response,
            Id = _ids.Next(),
            CorrelationId = request.Id,
            TraceId = request.TraceId,
            Version = request.Version,
            Timestamp = Clock.Now(),
            Payload = payload,
        };
        await _control.SendAsync(answer, token).ConfigureAwait(false);
    }

    /// <summary>Дождаться названного события.</summary>
    public async Task<Envelope?> WaitForEventAsync(string method, TimeSpan timeout,
                                                   CancellationToken token = default)
    {
        var waiting = new TaskCompletionSource<Envelope>(
            TaskCreationOptions.RunContinuationsAsynchronously);

        void Watch(Envelope e)
        {
            if (e.Method == method) waiting.TrySetResult(e);
        }

        EventReceived += Watch;
        try
        {
            var done = await Task.WhenAny(waiting.Task, Task.Delay(timeout, token))
                                 .ConfigureAwait(false);
            return done == waiting.Task ? await waiting.Task.ConfigureAwait(false)
                                        : null;
        }
        finally { EventReceived -= Watch; }
    }

    /// <summary>
    /// Спросить «жив ли» (§13).
    /// </summary>
    /// <remarks>
    /// Отдельный метод, а не таймер внутри: решать, когда спрашивать, — дело
    /// надзора, который знает и про тишину, и про то, сколько раз уже не
    /// ответили. Здесь только сам вопрос.
    /// </remarks>
    public Task<Envelope> PingAsync(TimeSpan timeout,
                                    CancellationToken token = default) =>
        CallAsync(Methods.Ping, null, timeout, token);

    private void Dispatch(Envelope message)
    {
        if (!Events.All.Contains(message.Method ?? ""))
        {
            // §3: неизвестное событие игнорируется молча. Асимметрия с
            // запросом намеренна — пропущенный запрос есть потерянное
            // действие, пропущенное событие лишь потерянное уведомление.
            IgnoredEvents.Add(message.Method ?? "");
            return;
        }
        EventReceived?.Invoke(message);
    }

    /// <summary>Что ядро написало в поток ошибок к этому моменту.</summary>
    public string CoreLog { get { lock (_coreLog) return _coreLog.ToString(); } }

    /// <summary>Номер процесса ядра. Нужен надзору и журналу: в двух
    /// процессах «какое из ядер» — вопрос, который задают часто.</summary>
    public int? CorePid => _core?.Id;

    public bool CoreAlive => _core is { HasExited: false };
    public int? CoreExitCode => _core is { HasExited: true } p ? p.ExitCode : null;

    public async ValueTask DisposeAsync()
    {
        try
        {
            if (Ready && _core is { HasExited: false })
                await CallAsync(Methods.CoreShutdown,
                                timeout: TimeSpan.FromSeconds(5))
                    .ConfigureAwait(false);
        }
        catch { /* ядро уже могло уйти */ }

        await _stopping.CancelAsync().ConfigureAwait(false);
        if (_pump is not null)
            try { await _pump.ConfigureAwait(false); } catch { /* уже всё */ }

        _control.Dispose();
        _data.Dispose();

        if (_core is { HasExited: false })
        {
            // Ядро завершается само, увидев обрыв (§13). Ждём недолго и лишь
            // потом убиваем: убить сразу значит не дать ему закрыть хранилище.
            if (!_core.WaitForExit(5000)) _core.Kill(entireProcessTree: true);
        }
        _core?.Dispose();
        _stopping.Dispose();
    }
}
