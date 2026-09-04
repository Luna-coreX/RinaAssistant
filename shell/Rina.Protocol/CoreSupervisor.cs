namespace Rina.Protocol;

/// <summary>The state of the link to the core (for <c>4.0-F12</c>).</summary>
public enum CoreState
{
    /// <summary>Not started yet.</summary>
    Stopped,
    /// <summary>Starting it and saying hello.</summary>
    Starting,
    /// <summary>The core answers.</summary>
    Ready,
    /// <summary>The link broke; bringing it back up.</summary>
    Reconnecting,
    /// <summary>Given up: the core will not come up.</summary>
    Failed,
}

/// <summary>
/// Supervising the core: start it, listen, restart, show the state.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-E07</c>; §13 of the specification.
/// </para>
/// <para>
/// <b>The window must not look frozen</b> — that is a direct requirement of
/// §13, and it shapes everything here. The state is therefore announced
/// outward by an event rather than found by polling: whoever draws must learn
/// of a break at that instant, not the next time it happens to ask something.
/// </para>
/// <para>
/// <b>Silence is not a sign of death; the sign of death is silence in answer
/// to a direct question.</b> Hence: <c>ping</c> is sent only after a pause,
/// and the core counts as dead after three unanswered in a row. Any message
/// that arrives counts as an answer: there is no point questioning a busy
/// channel.
/// </para>
/// <para>
/// <b>The gap between attempts grows.</b> A core that crashes at startup
/// would otherwise restart in a loop and eat the processor while the person
/// stares at "reconnecting". After several attempts in a row the supervisor
/// gives up and says so: an endless "any moment now" is the worst kind of
/// frozen window.
/// </para>
/// <para>
/// <b>State after a reconnect is gathered afresh by asking.</b> §13 says
/// plainly that an open question, open streams, granted permissions and
/// unfinished tasks do not survive a reconnect. The supervisor therefore
/// restores nothing — it reports that the link is new, and whoever draws asks
/// again.
/// </para>
/// </remarks>
public sealed class CoreSupervisor : IAsyncDisposable
{
    private readonly CoreLaunch _launch;
    private readonly CancellationTokenSource _stopping = new();
    private readonly SemaphoreSlim _swap = new(1, 1);
    private Task? _watchdog;

    /// <summary>After how much silence to ask "are you alive" (§13).</summary>
    public TimeSpan Silence { get; init; } = TimeSpan.FromSeconds(5);

    /// <summary>How many unanswered questions in a row count as death.</summary>
    public int MissedLimit { get; init; } = 3;

    /// <summary>How long to wait for the core to connect to the pipes.</summary>
    public TimeSpan ConnectTimeout { get; init; } = TimeSpan.FromSeconds(30);

    /// <summary>How many times to try bringing it up before giving up.</summary>
    public int MaxAttempts { get; init; } = 4;

    /// <summary>The gap to start from between attempts.</summary>
    public TimeSpan FirstBackoff { get; init; } = TimeSpan.FromMilliseconds(200);

    public CoreState State { get; private set; } = CoreState.Stopped;
    public string LastReason { get; private set; } = "";
    public int Restarts { get; private set; }

    /// <summary>
    /// Which attempt is in progress. One means the first.
    /// </summary>
    /// <remarks>
    /// A number, not a phrase about it. This assembly does not know the
    /// interface language and must not: composing «попытка 3» here would put
    /// a Russian string on the panel past the translation table, which is
    /// exactly what F08 forbids — and is what used to happen.
    /// </remarks>
    public int Attempt { get; private set; }
    public CoreConnection? Connection { get; private set; }

    /// <summary>The state changed. Its first listener is <c>4.0-F12</c>.</summary>
    public event Action<CoreState, string>? StateChanged;

    /// <summary>The link is new: whatever does not survive a break must be asked again.</summary>
    public event Action<CoreConnection>? Connected;

    /// <summary>Core events, whichever link brought them.</summary>
    public event Action<Envelope>? EventReceived;

    public CoreSupervisor(CoreLaunch launch) => _launch = launch;

    public async Task StartAsync(CancellationToken token = default)
    {
        await ConnectAsync(first: true, token).ConfigureAwait(false);
        _watchdog = Task.Run(() => WatchAsync(_stopping.Token), CancellationToken.None);
    }

    private void Move(CoreState state, string reason)
    {
        State = state;
        LastReason = reason;
        StateChanged?.Invoke(state, reason);
    }

    private async Task ConnectAsync(bool first, CancellationToken token)
    {
        var backoff = FirstBackoff;
        for (var attempt = 1; attempt <= MaxAttempts; attempt++)
        {
            // "Starting" is something the person should see once — at the
            // first start. After that it is a reconnect, and calling it a
            // start hides the fact that the link existed and broke.
            Attempt = attempt;
            Move(first && attempt == 1 ? CoreState.Starting
                                       : CoreState.Reconnecting, "");

            var connection = new CoreConnection();
            try
            {
                await connection.StartAsync(_launch, ConnectTimeout, token)
                                .ConfigureAwait(false);
                await connection.HandshakeAsync(token).ConfigureAwait(false);

                connection.EventReceived += OnEvent;
                connection.Broken += OnBroken;
                Connection = connection;

                // The reason is the version, not a phrase about it:
                // `Rina.Protocol` does not know the interface language and
                // must not; the window composes the caption.
                Move(CoreState.Ready, connection.CoreVersion);
                Connected?.Invoke(connection);
                return;
            }
            catch (Exception e)
            {
                await connection.DisposeAsync().ConfigureAwait(false);
                Move(CoreState.Reconnecting, e.Message);
                if (attempt == MaxAttempts) break;
                await Task.Delay(backoff, token).ConfigureAwait(false);
                backoff *= 2;
            }
        }

        Move(CoreState.Failed, LastReason);
    }

    private void OnEvent(Envelope message) => EventReceived?.Invoke(message);

    private void OnBroken(string reason)
    {
        // The restart itself is done by the watchdog: an event handler is
        // called from the read pump, and bringing the link up from inside
        // its own pump is a sure way to end up with two cores.
        LastReason = reason;
    }

    private async Task WatchAsync(CancellationToken token)
    {
        var missed = 0;
        while (!token.IsCancellationRequested)
        {
            try
            {
                await Task.Delay(TimeSpan.FromMilliseconds(250), token)
                          .ConfigureAwait(false);
            }
            catch (OperationCanceledException) { return; }

            var connection = Connection;
            if (State == CoreState.Failed) return;
            if (connection is null) continue;

            var dead = !connection.CoreAlive || !connection.Ready;
            if (!dead && DateTimeOffset.UtcNow - connection.LastHeard > Silence)
            {
                try
                {
                    await connection.PingAsync(Silence, token).ConfigureAwait(false);
                    missed = 0;
                }
                catch (OperationCanceledException) { return; }
                catch
                {
                    // A second question with no answer to the first is not
                    // the question doubled but a second unanswered one:
                    // those are what get counted.
                    if (++missed >= MissedLimit)
                        dead = true;
                }
            }

            if (!dead) continue;

            missed = 0;
            await RestartAsync(token).ConfigureAwait(false);
        }
    }

    private async Task RestartAsync(CancellationToken token)
    {
        if (!await _swap.WaitAsync(0, token).ConfigureAwait(false)) return;
        try
        {
            var old = Connection;
            Connection = null;
            Restarts++;
            // Technical text, not a phrase for a person: an exit code and a
            // system error are what the developer reads in the log. Whether
            // any of it reaches the panel, and in what words, is the
            // window's decision.
            Move(CoreState.Reconnecting,
                 old?.CoreExitCode is { } code
                     ? $"core exited with code {code}"
                     : LastReason.Length > 0 ? LastReason : "link broke");

            if (old is not null)
            {
                old.EventReceived -= OnEvent;
                old.Broken -= OnBroken;
                await old.DisposeAsync().ConfigureAwait(false);
            }

            await ConnectAsync(first: false, token).ConfigureAwait(false);
        }
        finally { _swap.Release(); }
    }

    public async ValueTask DisposeAsync()
    {
        await _stopping.CancelAsync().ConfigureAwait(false);
        if (_watchdog is not null)
            try { await _watchdog.ConfigureAwait(false); } catch { /* done */ }
        if (Connection is not null)
            await Connection.DisposeAsync().ConfigureAwait(false);
        _stopping.Dispose();
        _swap.Dispose();
    }
}
