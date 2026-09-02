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
/// Связь оболочки с ядром: запуск процесса, каналы, рукопожатие, разговор.
/// </summary>
/// <remarks>
/// <para>
/// Порядок обязателен и неочевиден: <b>сначала подняты трубы, потом запущено
/// ядро</b>. Ядро подключается клиентом и ждёт появления канала; если запустить
/// его раньше, оно будет ждать впустую ровно столько, сколько мы провозимся с
/// созданием труб. Обратный порядок работал бы почти всегда — и тем хуже.
/// </para>
/// <para>
/// Ответ на команду — <c>accepted</c>, а не текст: сам ответ приходит событием
/// <c>assistant.response</c>, когда появится. Поэтому здесь есть и ожидание
/// ответа на запрос, и подписка на события, и это разные вещи.
/// </para>
/// </remarks>
public sealed class CoreConnection : IAsyncDisposable
{
    private readonly IdGenerator _ids = new("s-");
    private readonly ControlChannel _control;
    private readonly ControlChannel _data;
    private Process? _core;
    private readonly System.Text.StringBuilder _coreLog = new();

    public string Session { get; }
    public int NegotiatedVersion { get; private set; }
    public IReadOnlyList<string> CoreCapabilities { get; private set; } = [];
    public string CoreVersion { get; private set; } = "";
    public string SessionId { get; private set; } = "";
    public bool Ready { get; private set; }

    /// <summary>События, пришедшие без запроса (§10).</summary>
    public event Action<Envelope>? EventReceived;

    /// <summary>Незнакомые события: их игнорируют молча, но считать полезно.</summary>
    public List<string> IgnoredEvents { get; } = [];

    public CoreConnection(string? session = null)
    {
        Session = session ?? Guid.NewGuid().ToString("N")[..12];
        _control = new ControlChannel(Session, "control");
        _data = new ControlChannel(Session, "data");
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
        // труба ядра невелика, и процесс, которому некуда писать в поток
        // ошибок, однажды встанет на записи в него. К тому же 4.0-F12 обязан
        // показывать состояние связи, а последняя строка журнала ядра —
        // самое внятное, что можно показать при обрыве.
        _core.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null) lock (_coreLog) _coreLog.AppendLine(e.Data);
        };
        _core.BeginErrorReadLine();

        var done = await Task.WhenAny(accepting, Task.Delay(timeout, token))
                             .ConfigureAwait(false);
        if (done != accepting)
            throw new ChannelClosedException(
                $"ядро не подключилось за {timeout.TotalSeconds:0} с");
        await accepting.ConfigureAwait(false);
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

        var answer = await CallAsync(Methods.Hello, hello, token)
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

    /// <summary>
    /// Запрос и ответ на него. События, пришедшие по пути, не теряются.
    /// </summary>
    public async Task<Envelope> CallAsync(string method, JsonObject? payload = null,
                                          CancellationToken token = default,
                                          string? traceId = null)
    {
        var request = Envelope.Request(method, payload, _ids.Next(),
                                       traceId ?? Trace.New());
        await _control.SendAsync(request, token).ConfigureAwait(false);

        while (true)
        {
            var message = await _control.ReceiveAsync(token).ConfigureAwait(false);
            if (message.IsEvent)
            {
                Dispatch(message);
                continue;
            }
            if (message.CorrelationId == request.Id)
                return message;
            // Ответ на чужой запрос: в 4.0 запросов в полёте по одному, но
            // терять чужое молча — привычка, которая аукнется на первом же
            // параллельном вызове.
            Dispatch(message);
        }
    }

    /// <summary>Читать канал, пока не придёт названное событие.</summary>
    public async Task<Envelope?> WaitForEventAsync(string method, TimeSpan timeout,
                                                   CancellationToken token = default)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(token);
        cts.CancelAfter(timeout);
        try
        {
            while (true)
            {
                var message = await _control.ReceiveAsync(cts.Token)
                                            .ConfigureAwait(false);
                Dispatch(message);
                if (message.IsEvent && message.Method == method) return message;
            }
        }
        catch (OperationCanceledException) { return null; }
    }

    private void Dispatch(Envelope message)
    {
        if (message.IsEvent && !Events.All.Contains(message.Method ?? ""))
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

    public bool CoreAlive => _core is { HasExited: false };
    public int? CoreExitCode => _core is { HasExited: true } p ? p.ExitCode : null;

    public async ValueTask DisposeAsync()
    {
        try
        {
            if (Ready && _core is { HasExited: false })
                await CallAsync(Methods.CoreShutdown).ConfigureAwait(false);
        }
        catch { /* ядро уже могло уйти */ }

        _control.Dispose();
        _data.Dispose();

        if (_core is { HasExited: false })
        {
            // Ядро завершается само, увидев обрыв (§13). Ждём недолго и лишь
            // потом убиваем: убить сразу значит не дать ему закрыть хранилище.
            if (!_core.WaitForExit(5000)) _core.Kill(entireProcessTree: true);
        }
        _core?.Dispose();
    }
}
