using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text.Json.Nodes;
using Rina.Protocol.Transport;

namespace Rina.Protocol;

/// <summary>How to start the core.</summary>
/// <param name="Python">The interpreter.</param>
/// <param name="Script">The path to <c>rina_core.py</c>.</param>
/// <param name="WorkingDirectory">The project root.</param>
/// <param name="ExtraArguments">What to append to the command line, the
/// journal level for instance.</param>
public sealed record CoreLaunch(string Python, string Script,
                                string WorkingDirectory,
                                IReadOnlyList<string>? ExtraArguments = null);

/// <summary>
/// One link between the shell and the core: the process, the channels,
/// the handshake, the conversation.
/// </summary>
/// <remarks>
/// <para>
/// The order is mandatory and not obvious: <b>the pipes are raised first,
/// the core is started after</b>. The core connects as a client and waits
/// for the channel to appear; started earlier, it waits for nothing for
/// exactly as long as we spend creating the pipes. The reverse order would
/// work almost always — and that is what makes it worse.
/// </para>
/// <para>
/// <b>One pump reads the channel, not whoever asked.</b> The first
/// edition read inside <c>CallAsync</c>, and that worked exactly until the
/// second reader: events arrive unrequested, and there is nobody to hear
/// them while nobody is asking anything. Now the answers are sorted by
/// <c>correlation_id</c> and the events go to subscribers — which is also
/// what the supervisor (<c>4.0-E07</c>) needs, as it has to hear the
/// channel all the time.
/// </para>
/// <para>
/// The reply to a command is <c>accepted</c>, not text: the answer itself
/// arrives as an <c>assistant.response</c> event, when there is one.
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

    /// <summary>
    /// The version of the data format on disk (ADR 0004).
    /// </summary>
    /// <remarks>
    /// The fourth independent version. It arrives in the handshake rather
    /// than as a setting: `config_version` is the store's state and is not
    /// given out as a setting. But it is what limits a rollback.
    /// </remarks>
    public int DataVersion { get; private set; }
    public string SessionId { get; private set; } = "";
    public bool Ready { get; private set; }

    /// <summary>The core's events, arriving unrequested (§10).</summary>
    public event Action<Envelope>? EventReceived;

    /// <summary>The link broke: the core died or closed the channel.</summary>
    public event Action<string>? Broken;

    /// <summary>
    /// The core is asking for something (§1: it has exactly two kinds of
    /// request — a permission, and data the shell owns).
    /// </summary>
    public event Action<Envelope>? RequestReceived;

    /// <summary>Unfamiliar events: ignored silently, but worth
    /// counting.</summary>
    public List<string> IgnoredEvents { get; } = [];

    /// <summary>The data channel: sound and screen frames, past the JSON
    /// (§2).</summary>
    public DataChannel Data => _data;

    /// <summary>When anything last arrived from the core (§13).</summary>
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

        // The core's journal is read straight away and in the background.
        // Not only for debugging: the pipe is not large, and a process
        // with nowhere to write its error stream will one day block on
        // writing to it. Besides, 4.0-F12 is obliged to show the state of
        // the link, and the last line of the core's journal is the most
        // intelligible thing to show when it breaks.
        _core.ErrorDataReceived += (_, e) =>
        {
            if (e.Data is not null) lock (_coreLog) _coreLog.AppendLine(e.Data);
        };
        _core.BeginErrorReadLine();

        // The core may die without connecting — and then waiting for the
        // pipe until the deadline is pointless. We wait for both outcomes
        // at once.
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

    /// <summary>The channel's only reader.</summary>
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
                // A reply to a request nobody is waiting for is no reason
                // to fall over: whoever waited may have given up on their
                // own deadline.
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

    /// <summary>The handshake (§4): versions as sets, capabilities as a
    /// list.</summary>
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
        DataVersion = answer.Payload["data_version"]?.GetValue<int>() ?? 0;
        SessionId = answer.Payload["session_id"]?.GetValue<string>() ?? "";
        Ready = true;
    }

    /// <summary>Whether the core can do this method (§4).</summary>
    public bool MayCall(string method)
    {
        if (!Ready) return false;
        if (!Methods.Capability.TryGetValue(method, out var capability))
            return false;
        return capability is null || CoreCapabilities.Contains(capability);
    }

    /// <summary>A request and the reply to it.</summary>
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
    /// Reply to a request from the core.
    /// </summary>
    /// <remarks>
    /// The trace and the version are inherited from the request: an
    /// end-to-end chain (§14) has to be a property of the construction, or
    /// it will one day be forgotten.
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

    /// <summary>Wait for the named event.</summary>
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
    /// Ask whether it is alive (§13).
    /// </summary>
    /// <remarks>
    /// A method of its own rather than a timer inside: deciding when to
    /// ask is the supervisor's business, as it knows both about the
    /// silence and about how many times there has been no answer. Here
    /// there is only the question itself.
    /// </remarks>
    public Task<Envelope> PingAsync(TimeSpan timeout,
                                    CancellationToken token = default) =>
        CallAsync(Methods.Ping, null, timeout, token);

    private void Dispatch(Envelope message)
    {
        if (!Events.All.Contains(message.Method ?? ""))
        {
            // §3: an unknown event is ignored silently. The asymmetry
            // with a request is deliberate — a missed request is a lost
            // action, a missed event only a lost notification.
            IgnoredEvents.Add(message.Method ?? "");
            return;
        }
        EventReceived?.Invoke(message);
    }

    /// <summary>What the core has written to its error stream by
    /// now.</summary>
    public string CoreLog { get { lock (_coreLog) return _coreLog.ToString(); } }

    /// <summary>The core's process id. Needed by the supervisor and the
    /// journal: with two processes, "which of the cores" is a question
    /// asked often.</summary>
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
            // The core shuts down by itself when it sees the break
            // (§13). We wait a little and only then kill it: killing at
            // once means not letting it close the store.
            if (!_core.WaitForExit(5000)) _core.Kill(entireProcessTree: true);
        }
        _core?.Dispose();
        _stopping.Dispose();
    }
}
