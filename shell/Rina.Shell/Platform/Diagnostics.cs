using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.Json.Nodes;

using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Platform;

/// <summary>
/// Диагностический пакет: журналы обоих слоёв, версии и состояние — в архив.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-I03</c>. Разбор жалобы начинается с вопросов, ответы
/// на которые человек не знает и не обязан знать: какая версия ядра, какая
/// протокола, что было в журнале, включено ли распознавание. Собрать это
/// руками — десять шагов по папкам, которые спрятаны в <c>AppData</c>.
/// </para>
/// <para>
/// <b>Собирает оболочка.</b> Архив, файлы и сведения об операционной
/// системе — системный слой (ADR 0009). Ядро отдаёт то, что знает только
/// оно, и отдаёт обычными методами: секретные ключи оно наружу не выдаёт
/// само, и здесь это не приходится повторять.
/// </para>
/// <para>
/// <b>Свободный текст не уезжает.</b> Значение, выбранное из перечня, —
/// это не текст человека, и оно пишется как есть; всё остальное
/// заменяется длиной. Правило то же, что в журнале вызовов
/// (<c>core/audit.py</c>), и оно намеренно строгое: под него попадает и
/// безобидное сочетание клавиш, и путь к модели, в котором стоит имя
/// человека. Одно объяснимое правило лучше списка исключений, который
/// однажды забудут пополнить.
/// </para>
/// <para>
/// <b>Журналы едут как есть, и об этом сказано.</b> В них и есть ответ на
/// «что произошло», ради которого пакет собирают. Но настройка
/// <c>log_texts</c> разрешает писать в журнал тексты реплик — и если она
/// включена, человек обязан узнать об этом **до** того, как отправит
/// архив, а не после. Поэтому её значение стоит в пояснении первой
/// строкой.
/// </para>
/// </remarks>
public static class Diagnostics
{
    /// <summary>Что получилось: путь к архиву либо причина отказа.</summary>
    public sealed record Result(bool Ok, string Path, string Problem);

    /// <summary>Куда предложить сохранить: имя со временем, чтобы не затирать.</summary>
    public static string SuggestedName() =>
        $"rina-diagnostics-{DateTime.Now:yyyy-MM-dd-HHmm}.zip";

    private static string DataDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "RinaAssistant");

    /// <summary>
    /// Собрать пакет.
    /// </summary>
    /// <remarks>
    /// Ядро может быть не на связи — и это самый частый случай, ради
    /// которого пакет и собирают. Тогда версии и настройки недоступны, а
    /// журналы доступны; пакет собирается из того, что есть, и отсутствие
    /// названо, а не пропущено молча.
    /// </remarks>
    public static async Task<Result> CollectAsync(string zipPath, CoreLink? link)
    {
        try
        {
            if (File.Exists(zipPath)) File.Delete(zipPath);
            Directory.CreateDirectory(Path.GetDirectoryName(zipPath)
                                      ?? Directory.GetCurrentDirectory());

            var connection = link?.Connection;
            var settings = await SettingsAsync(connection);

            using var archive = ZipFile.Open(zipPath, ZipArchiveMode.Create);
            Write(archive, "README.txt", Readme(settings));
            Write(archive, "versions.txt", Versions(connection));
            Write(archive, "state.txt", await StateAsync(link));
            Write(archive, "settings.txt", settings.Text);
            AddLogs(archive);
            return new Result(true, zipPath, "");
        }
        catch (Exception error)
        {
            return new Result(false, "", error.Message);
        }
    }

    private static void Write(ZipArchive archive, string name, string body)
    {
        var entry = archive.CreateEntry(name);
        using var stream = entry.Open();
        using var writer = new StreamWriter(stream, new UTF8Encoding(false));
        writer.Write(body);
    }

    /// <summary>Журналы обоих слоёв. Ротации тоже: сбой мог быть до неё.</summary>
    private static void AddLogs(ZipArchive archive)
    {
        var logs = Path.Combine(DataDir, "logs");
        if (!Directory.Exists(logs)) return;
        foreach (var file in Directory.EnumerateFiles(logs))
        {
            try
            {
                // Читаем, не мешая писать: журнал открыт на дозапись обоими
                // процессами, и обычное чтение спотыкается о разделяемый
                // доступ. Пакет, который не собирается, пока программа
                // работает, бесполезен — её ровно тогда и разбирают.
                using var source = new FileStream(
                    file, FileMode.Open, FileAccess.Read,
                    FileShare.ReadWrite | FileShare.Delete);
                var entry = archive.CreateEntry(
                    "logs/" + Path.GetFileName(file));
                using var target = entry.Open();
                source.CopyTo(target);
            }
            catch (IOException)
            {
                // Один недочитанный журнал — не повод остаться без пакета.
            }
        }
    }

    private static string Versions(CoreConnection? connection)
    {
        var lines = new StringBuilder();
        lines.AppendLine("оболочка: " + (typeof(Diagnostics).Assembly
            .GetName().Version?.ToString() ?? "—"));
        lines.AppendLine("ядро: " + (connection?.CoreVersion is { Length: > 0 } c
            ? c : "нет связи"));
        lines.AppendLine("протокол: " + (connection is { Ready: true } r
            ? r.NegotiatedVersion.ToString() : "—"));
        lines.AppendLine("схема данных: " + (connection is { DataVersion: > 0 } d
            ? d.DataVersion.ToString() : "—"));
        lines.AppendLine();
        lines.AppendLine("система: " + Environment.OSVersion);
        lines.AppendLine("разрядность: " + (Environment.Is64BitProcess
            ? "64" : "32"));
        lines.AppendLine(".NET: " + Environment.Version);
        return lines.ToString();
    }

    private static async Task<string> StateAsync(CoreLink? link)
    {
        var lines = new StringBuilder();
        lines.AppendLine("связь: " + (link?.State.ToString() ?? "нет"));
        lines.AppendLine("попытка поднять ядро: " + (link?.Attempt ?? 0));

        var connection = link?.Connection;
        if (connection is { Ready: true })
        {
            lines.AppendLine("возможности ядра: "
                             + string.Join(", ", connection.CoreCapabilities));
        }

        lines.AppendLine();
        lines.AppendLine("плагины:");
        try
        {
            if (connection is { Ready: true } ready)
            {
                var answer = await ready.CallAsync(Methods.PluginsList,
                    new JsonObject(), TimeSpan.FromSeconds(10));
                foreach (var item in answer.Payload["plugins"] as JsonArray
                                     ?? [])
                {
                    var plugin = item as JsonObject;
                    var id = plugin?["id"]?.GetValue<string>() ?? "?";
                    var on = plugin?["enabled"]?.GetValue<bool>() ?? false;
                    var error = plugin?["error"]?.GetValue<string>() ?? "";
                    lines.AppendLine($"  {id}: "
                                     + (on ? "включён" : "выключен")
                                     + (error.Length > 0 ? $", сбой: {error}" : ""));
                }
            }
            else
            {
                lines.AppendLine("  неизвестно: ядро не на связи");
            }
        }
        catch (Exception error)
        {
            lines.AppendLine("  не спросили: " + error.Message);
        }
        return lines.ToString();
    }

    /// <summary>Настройки и то, писались ли в журнал тексты реплик.</summary>
    private sealed record Settings(string Text, bool TextsLogged, bool Known);

    private static async Task<Settings> SettingsAsync(CoreConnection? connection)
    {
        if (connection is not { Ready: true } ready)
            return new Settings("ядро не на связи — настройки не спрашивали"
                                + Environment.NewLine, false, false);
        try
        {
            var schema = (await ready.CallAsync(Methods.SettingsDescribe,
                new JsonObject(), TimeSpan.FromSeconds(10)))
                .Payload["schema"] as JsonObject ?? [];
            var keys = new JsonArray();
            foreach (var pair in schema) keys.Add(pair.Key);
            var values = (await ready.CallAsync(Methods.SettingsGet,
                new JsonObject { ["keys"] = keys }, TimeSpan.FromSeconds(10)))
                .Payload["values"] as JsonObject ?? [];

            var texts = false;
            var lines = new StringBuilder();
            foreach (var pair in schema.OrderBy(p => p.Key,
                                                StringComparer.Ordinal))
            {
                var value = values[pair.Key];
                if (value is null) continue;
                if (pair.Key == "log_texts")
                    texts = value.GetValue<bool>();
                lines.AppendLine($"{pair.Key} = "
                                 + Safe(pair.Value as JsonObject, value));
            }
            return new Settings(lines.ToString(), texts, true);
        }
        catch (Exception error)
        {
            return new Settings("не спросили: " + error.Message
                                + Environment.NewLine, false, false);
        }
    }

    /// <summary>
    /// Значение в виде, пригодном для отправки.
    /// </summary>
    /// <remarks>
    /// Выбранное из перечня — это не текст человека, и оно едет как есть.
    /// Свободный текст, список и словарь превращаются в длину и размер:
    /// «сколько» отвечает почти на все вопросы разбора, «что именно» — ни на
    /// один из них.
    /// </remarks>
    private static string Safe(JsonObject? spec, JsonNode value)
    {
        var kind = spec?["type"]?.GetValue<string>() ?? "string";
        var chosen = spec?["choices"] is JsonArray { Count: > 0 }
                     || spec?["dynamic"]?.GetValue<bool>() == true;

        if (kind is "boolean" or "integer" or "number") return value.ToString();
        if (kind == "array")
            return $"[{(value as JsonArray)?.Count ?? 0} шт.]";
        if (kind == "object")
            return $"{{{(value as JsonObject)?.Count ?? 0} записей}}";
        if (chosen) return value.ToString();

        var text = value.GetValue<string>() ?? "";
        return text.Length == 0 ? "(пусто)" : $"(текст, {text.Length} знаков)";
    }

    private static string Readme(Settings settings)
    {
        var lines = new StringBuilder();
        lines.AppendLine("Диагностический пакет Рины");
        lines.AppendLine("==========================");
        lines.AppendLine();

        // Первой строкой — потому что это единственное, что человек обязан
        // узнать до отправки, а не после.
        lines.AppendLine(settings.Known
            ? (settings.TextsLogged
                ? "ВНИМАНИЕ: запись текстов реплик была ВКЛЮЧЕНА "
                  + "(настройка log_texts)."
                  + Environment.NewLine
                  + "Это значит, что в logs/ могли попасть тексты того, что "
                  + "вы говорили Рине," + Environment.NewLine
                  + "и того, что она отвечала. Посмотрите журналы перед "
                  + "отправкой."
                : "Запись текстов реплик была выключена: тексты того, что вы "
                  + "говорили," + Environment.NewLine
                  + "в журналы не писались — только длина.")
            : "Настройки спросить не удалось: ядро не было на связи.");
        lines.AppendLine();

        lines.AppendLine("Что внутри");
        lines.AppendLine("  versions.txt  версии оболочки, ядра, протокола и "
                         + "схемы данных, сведения о системе");
        lines.AppendLine("  state.txt     состояние связи и список плагинов");
        lines.AppendLine("  settings.txt  настройки (см. ниже про значения)");
        lines.AppendLine("  logs/         журналы обоих слоёв как есть");
        lines.AppendLine();

        lines.AppendLine("Чего внутри нет");
        lines.AppendLine("  История разговора, ваши команды и напоминания "
                         + "сюда не попадают.");
        lines.AppendLine("  В settings.txt значение едет как есть только "
                         + "тогда, когда оно выбрано");
        lines.AppendLine("  из перечня. Свободный текст, пути и адреса "
                         + "заменены длиной, списки и");
        lines.AppendLine("  словари — количеством: «сколько» отвечает почти "
                         + "на все вопросы разбора,");
        lines.AppendLine("  «что именно» — ни на один. Правило намеренно "
                         + "строгое, поэтому под него");
        lines.AppendLine("  попало и безобидное: сочетание клавиш видно как "
                         + "длина, а не как текст.");
        lines.AppendLine();
        lines.AppendLine("Архив можно открыть и прочитать целиком до того, "
                         + "как отправлять.");
        return lines.ToString();
    }
}
