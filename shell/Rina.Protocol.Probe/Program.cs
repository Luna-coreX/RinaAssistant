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

if (fails > 0)
{
    Console.WriteLine();
    Console.WriteLine("--- журнал ядра ---");
    Console.WriteLine(core.CoreLog);
}

Console.WriteLine();
Console.WriteLine($"Проверок: {checks}, ошибок: {fails}");
return fails == 0 ? 0 : 1;

static string FindRoot()
{
    var dir = AppContext.BaseDirectory;
    while (dir is not null && !File.Exists(Path.Combine(dir, "rina_core.py")))
        dir = Path.GetDirectoryName(dir);
    return dir ?? throw new InvalidOperationException(
        "не найден корень проекта: нет rina_core.py вверх по дереву");
}
