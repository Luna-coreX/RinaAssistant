using System.Text.Json.Nodes;
using Rina.Protocol;

// F02: оболочка запускает настоящее ядро и разговаривает с ним по
// именованному каналу.
//
// Это вторая половина требования 4.0-D16: conformance-набор на Python гонял
// mock-оболочку против настоящего ядра, здесь настоящая оболочка идёт против
// настоящего ядра. Никаких заглушек — процесс, труба, байты.
//
// Проверка написана консольной, а не на xunit: у неё нет ни одной внешней
// зависимости, и она выглядит так же, как проверки на стороне ядра. Набор,
// который не собрать без сети, однажды не соберётся.

var root = FindRoot();
var checks = 0;
var fails = 0;

void Check(string label, bool ok, string detail = "")
{
    checks++;
    if (!ok) fails++;
    Console.WriteLine($"  {(ok ? "OK  " : "FAIL")}  {label} {detail}");
}

Console.WriteLine("=== F02: оболочка говорит с ядром через именованный канал ===");
Console.WriteLine($"корень: {root}");

var launch = new CoreLaunch(
    Python: "python",
    // Ядро под песочницей: побочные эффекты обезврежены в самом дочернем
    // процессе, и хранилище уведено во временную папку. Запускать здесь
    // rina_core.py напрямую значило бы писать в данные пользователя.
    Script: Path.Combine(root, "tools", "_core_sandboxed.py"),
    WorkingDirectory: root,
    // Подробный журнал: если проба упадёт, причина должна быть видна сразу,
    // а не после второго запуска с другими ключами.
    ExtraArguments: ["--log-level", "DEBUG"]);

await using var core = new CoreConnection();
Console.WriteLine($"сессия: {core.Session}");

try
{
    await core.StartAsync(launch, TimeSpan.FromSeconds(30));
    Check("ядро подключилось к обеим трубам", true);
    Check("процесс ядра жив", core.CoreAlive);

    await core.HandshakeAsync();
    Check("рукопожатие состоялось", core.Ready);
    Check("выбрана версия протокола 1", core.NegotiatedVersion == 1,
          $"| {core.NegotiatedVersion}");
    Check("ядро назвало себя", core.CoreVersion.Length > 0, $"| {core.CoreVersion}");
    Check("ядро назвало идентификатор сессии", core.SessionId.Length == 32);
    Check("возможности получены от настоящего ядра",
          core.CoreCapabilities.Contains(Capabilities.Stt)
          && core.CoreCapabilities.Contains(Capabilities.Reminders),
          "| " + string.Join(", ", core.CoreCapabilities));

    Check("метод объявленной возможности звать можно",
          core.MayCall(Methods.RemindersList));
    Check("метод возможности, которой нет, звать нельзя",
          !core.MayCall(Methods.WindowFocus));
    Check("выдуманный метод звать нельзя", !core.MayCall("рина.станцуй"));

    // --- команда: ответ «принято», сам ответ приходит событием ---
    var heard = new List<string>();
    var texts = new List<string>();
    core.EventReceived += e =>
    {
        heard.Add(e.Method ?? "");
        if (e.Method == Events.AssistantResponse)
            texts.Add(e.Payload["text"]?.GetValue<string>() ?? "");
    };

    var trace = Trace.New();
    var accepted = await core.CallAsync(Methods.CommandHandle, new JsonObject
    {
        ["text"] = "который час",
        ["source"] = "typed",
    }, traceId: trace);

    Check("ответ на команду — «принято»",
          accepted.Payload["accepted"]?.GetValue<bool>() == true,
          $"| {accepted.Payload.ToJsonString()}");
    Check("ответ несёт трассировку запроса", accepted.TraceId == trace);

    // Ждём щедро. Первая нераспознанная команда в чистом профиле стоит
    // около тридцати секунд: индекс установленных программ строится по
    // требованию, обходом диска. Тридцать секунд ожидания давали провал
    // ровно на границе — событие приходило секундой позже.
    var said = await core.WaitForEventAsync(Events.AssistantResponse,
                                            TimeSpan.FromSeconds(120));
    Check("Рина ответила событием, а не ответом на запрос", said is not null,
          "| " + string.Join(", ", heard));
    if (said is not null)
    {
        Check("ответ несёт ту же трассировку", said.TraceId == trace,
              $"| {said.TraceId}");
        Console.WriteLine($"      сказано: «{texts.FirstOrDefault()}»");
    }

    // --- неизвестный метод: ошибка кодом, а не обрыв ---
    var refused = await core.CallAsync("рина.станцуй");
    Check("неизвестный метод даёт ошибку",
          refused.IsError && refused.ErrorCode == ErrorCodes.ProtocolUnknownMethod,
          $"| {refused.ErrorCode}");
    Check("у кода известны категория и повторяемость",
          ErrorCodes.Catalogue[refused.ErrorCode].Category == ErrorCategory.Protocol
          && !ErrorCodes.Catalogue[refused.ErrorCode].Retryable);

    // --- незнакомое событие: молчание, а не падение ---
    Check("незнакомых событий не приходило", core.IgnoredEvents.Count == 0,
          "| " + string.Join(", ", core.IgnoredEvents));

    // --- настройки: смысл от ядра, вид от оболочки (ADR 0006) ---
    var described = await core.CallAsync(Methods.SettingsDescribe, new JsonObject
    {
        ["keys"] = new JsonArray("volume", "log_level"),
    });
    var schema = described.Payload["schema"]?.AsObject();
    Check("ядро отдало схему", schema is not null && schema.Count == 2);
    Check("с типом и границами",
          schema?["volume"]?["type"]?.GetValue<string>() == "integer"
          && schema?["volume"]?["high"]?.GetValue<int>() == 100);
    Check("раскладку ядро не описывает",
          described.Payload["layout"] is null
          || described.Payload["layout"]!.GetValueKind()
             == System.Text.Json.JsonValueKind.Null);

    var written = await core.CallAsync(Methods.SettingsSet, new JsonObject
    {
        ["values"] = new JsonObject { ["volume"] = 63, ["log_level"] = "ЧТО-ТО" },
    });
    var verdicts = written.Payload["verdicts"]?.AsObject();
    Check("верное значение принято",
          verdicts?["volume"]?["accepted"]?.GetValue<bool>() == true);
    Check("неверное отклонено своим кодом",
          verdicts?["log_level"]?["code"]?.GetValue<string>()
          == ErrorCodes.SettingsInvalidValue,
          $"| {verdicts?["log_level"]?.ToJsonString()}");
}
catch (Exception e)
{
    Check($"без исключений: {e.GetType().Name}", false, $"| {e.Message}");
}

// ---------------------------------------------------------------------------
// E07: надзор — запустить, заметить смерть, поднять заново.
Console.WriteLine();
Console.WriteLine("=== E07: оболочка следит за ядром ===");

var states = new List<CoreState>();
await using (var boss = new CoreSupervisor(launch)
             {
                 Silence = TimeSpan.FromSeconds(2),
                 ConnectTimeout = TimeSpan.FromSeconds(30),
             })
{
    boss.StateChanged += (state, why) =>
    {
        states.Add(state);
        Console.WriteLine($"      состояние: {state} — {why}");
    };

    await boss.StartAsync();
    Check("надзор поднял ядро", boss.State == CoreState.Ready);
    var firstSession = boss.Connection!.SessionId;
    Check("сессия получена", firstSession.Length == 32);

    // Убиваем ядро так, как это сделал бы сбой: без предупреждения.
    KillCore(boss.Connection!);

    var restored = await WaitUntil(() => boss.State == CoreState.Ready
                                         && boss.Connection is not null
                                         && boss.Connection.SessionId != firstSession,
                                   TimeSpan.FromSeconds(90));
    Check("после падения ядро поднято заново", restored,
          $"| состояние {boss.State}, перезапусков {boss.Restarts}");
    Check("связь новая, а не прежняя",
          boss.Connection?.SessionId is { Length: 32 } s2 && s2 != firstSession);
    Check("состояние проходило через «переподключаемся»",
          states.Contains(CoreState.Reconnecting), "| " + string.Join(" → ", states));
    Check("перезапуск посчитан", boss.Restarts >= 1, $"| {boss.Restarts}");

    if (boss.Connection is not null)
    {
        var alive = await boss.Connection.CallAsync(Methods.RemindersList,
                                                    timeout: TimeSpan.FromSeconds(20));
        Check("с новым ядром снова разговаривают", !alive.IsError,
              $"| {alive.Payload.ToJsonString()}");
    }
}

// Ядро, которое не поднимается вовсе: надзор обязан сдаться, а не крутиться.
await using (var doomed = new CoreSupervisor(
                 launch with { Script = Path.Combine(root, "нет-такого-ядра.py") })
             {
                 MaxAttempts = 3,
                 FirstBackoff = TimeSpan.FromMilliseconds(50),
                 ConnectTimeout = TimeSpan.FromSeconds(5),
             })
{
    var started = DateTime.UtcNow;
    await doomed.StartAsync();
    var spent = DateTime.UtcNow - started;
    Check("надзор сдался, а не крутится вечно",
          doomed.State == CoreState.Failed, $"| {doomed.State}");
    Check("сдался быстро", spent < TimeSpan.FromSeconds(30),
          $"| {spent.TotalSeconds:0.0} с");
    Check("причина названа", doomed.LastReason.Length > 0,
          $"| {doomed.LastReason}");
}

if (fails > 0)
{
    Console.WriteLine();
    Console.WriteLine("--- журнал ядра ---");
    Console.WriteLine(core.CoreLog);
}

Console.WriteLine();
Console.WriteLine($"Проверок: {checks}, ошибок: {fails}");
return fails == 0 ? 0 : 1;

static void KillCore(CoreConnection connection)
{
    // Аварийная смерть: ядру не дают ни попрощаться, ни закрыть хранилище.
    // Именно так это выглядит при настоящем сбое, и надзор обязан справиться
    // с этим, а не только с вежливым завершением.
    if (connection.CorePid is not { } pid) return;
    try
    {
        using var process = System.Diagnostics.Process.GetProcessById(pid);
        process.Kill(entireProcessTree: true);
    }
    catch { /* уже ушло */ }
}

static async Task<bool> WaitUntil(Func<bool> condition, TimeSpan timeout)
{
    var deadline = DateTime.UtcNow + timeout;
    while (DateTime.UtcNow < deadline)
    {
        if (condition()) return true;
        await Task.Delay(100);
    }
    return condition();
}

static string FindRoot()
{
    var dir = AppContext.BaseDirectory;
    while (dir is not null && !File.Exists(Path.Combine(dir, "rina_core.py")))
        dir = Path.GetDirectoryName(dir);
    return dir ?? throw new InvalidOperationException(
        "не найден корень проекта: нет rina_core.py вверх по дереву");
}
