namespace Rina.Protocol;

/// <summary>В каком состоянии связь с ядром (для <c>4.0-F12</c>).</summary>
public enum CoreState
{
    /// <summary>Ещё не запускали.</summary>
    Stopped,
    /// <summary>Запускаем и здороваемся.</summary>
    Starting,
    /// <summary>Ядро отвечает.</summary>
    Ready,
    /// <summary>Связь оборвалась, поднимаем заново.</summary>
    Reconnecting,
    /// <summary>Сдались: ядро не поднимается.</summary>
    Failed,
}

/// <summary>
/// Надзор за ядром: запустить, слушать, перезапустить, показать состояние.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-E07</c>; §13 спецификации.
/// </para>
/// <para>
/// <b>Окно не должно выглядеть зависшим</b> — это прямое требование §13, и
/// оно определяет всё устройство. Поэтому состояние объявляется наружу
/// событием, а не выясняется опросом: тот, кто рисует, обязан узнать об обрыве
/// в тот же миг, а не когда в следующий раз что-нибудь спросит.
/// </para>
/// <para>
/// <b>Молчание не признак смерти; признак смерти — молчание в ответ на прямой
/// вопрос.</b> Отсюда: <c>ping</c> шлётся только после паузы, а мёртвым ядро
/// считается после трёх неотвеченных подряд. Любое пришедшее сообщение
/// засчитывается за ответ: занятый канал спрашивать незачем.
/// </para>
/// <para>
/// <b>Отступ между попытками растёт.</b> Ядро, падающее при старте, иначе
/// перезапускалось бы в цикле и съело бы процессор, пока человек смотрит на
/// «переподключаемся». После нескольких попыток подряд надзор сдаётся и
/// говорит об этом: бесконечное «сейчас-сейчас» — худший вид зависшего окна.
/// </para>
/// <para>
/// <b>Состояние после переподключения собирается заново запросами.</b> §13
/// прямо говорит, что незакрытый вопрос, открытые потоки, выданные разрешения
/// и незавершённые задачи переподключение не переживают. Надзор поэтому не
/// пытается ничего восстановить — он сообщает, что связь новая, и тот, кто
/// рисует, спрашивает заново.
/// </para>
/// </remarks>
public sealed class CoreSupervisor : IAsyncDisposable
{
    private readonly CoreLaunch _launch;
    private readonly CancellationTokenSource _stopping = new();
    private readonly SemaphoreSlim _swap = new(1, 1);
    private Task? _watchdog;

    /// <summary>После какой тишины спрашивать «жив ли» (§13).</summary>
    public TimeSpan Silence { get; init; } = TimeSpan.FromSeconds(5);

    /// <summary>Сколько неотвеченных вопросов подряд считать смертью.</summary>
    public int MissedLimit { get; init; } = 3;

    /// <summary>Сколько ждать подключения ядра к трубам.</summary>
    public TimeSpan ConnectTimeout { get; init; } = TimeSpan.FromSeconds(30);

    /// <summary>Сколько раз пробовать поднять, прежде чем сдаться.</summary>
    public int MaxAttempts { get; init; } = 4;

    /// <summary>С какого отступа начинать между попытками.</summary>
    public TimeSpan FirstBackoff { get; init; } = TimeSpan.FromMilliseconds(200);

    public CoreState State { get; private set; } = CoreState.Stopped;
    public string LastReason { get; private set; } = "";
    public int Restarts { get; private set; }
    public CoreConnection? Connection { get; private set; }

    /// <summary>Состояние сменилось. Первый слушатель этого — <c>4.0-F12</c>.</summary>
    public event Action<CoreState, string>? StateChanged;

    /// <summary>Связь новая: всё, что не переживает обрыв, надо спросить заново.</summary>
    public event Action<CoreConnection>? Connected;

    /// <summary>События ядра, какая бы связь их ни принесла.</summary>
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
            // «Запускаем» человек должен увидеть один раз — при первом
            // старте. Дальше это переподключение, и называть его запуском
            // значит скрывать, что связь уже была и оборвалась.
            Move(first && attempt == 1 ? CoreState.Starting
                                       : CoreState.Reconnecting,
                 attempt == 1 ? (first ? "запускаем ядро" : "поднимаем заново")
                              : $"попытка {attempt}");

            var connection = new CoreConnection();
            try
            {
                await connection.StartAsync(_launch, ConnectTimeout, token)
                                .ConfigureAwait(false);
                await connection.HandshakeAsync(token).ConfigureAwait(false);

                connection.EventReceived += OnEvent;
                connection.Broken += OnBroken;
                Connection = connection;

                Move(CoreState.Ready, $"ядро {connection.CoreVersion}");
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

        Move(CoreState.Failed,
             $"ядро не поднялось за {Attempts(MaxAttempts)}: {LastReason}");
    }

    /// <summary>
    /// «1 попытку», «3 попытки», «5 попыток».
    /// </summary>
    /// <remarks>
    /// Строка видна человеку, а «за 3 попыт(ки)» — не русский язык.
    /// Оболочка отвечает за то, как это читается (ADR 0006 о том же:
    /// представление — её забота).
    /// </remarks>
    private static string Attempts(int n)
    {
        var tail = n % 100 is >= 11 and <= 14 ? "попыток"
            : (n % 10) switch { 1 => "попытку", 2 or 3 or 4 => "попытки",
                                _ => "попыток" };
        return $"{n} {tail}";
    }

    private void OnEvent(Envelope message) => EventReceived?.Invoke(message);

    private void OnBroken(string reason)
    {
        // Сам перезапуск делает сторож: обработчик события зовётся из насоса
        // чтения, и поднимать связь изнутри её же насоса — верный способ
        // получить два ядра.
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
                    // Второй вопрос без ответа на первый — не удвоение
                    // вопроса, а второй неотвеченный: именно они считаются.
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
            Move(CoreState.Reconnecting,
                 old?.CoreExitCode is { } code
                     ? $"ядро вышло с кодом {code}"
                     : LastReason.Length > 0 ? LastReason : "связь оборвалась");

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
            try { await _watchdog.ConfigureAwait(false); } catch { /* всё */ }
        if (Connection is not null)
            await Connection.DisposeAsync().ConfigureAwait(false);
        _stopping.Dispose();
        _swap.Dispose();
    }
}
