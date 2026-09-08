using System.IO;
using System.IO.Compression;
using System.Text;
using System.Text.Json.Nodes;

using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Platform;

/// <summary>
/// A diagnostic bundle: both layers' journals, the versions and the state,
/// into one archive.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-I03</c>. Looking into a complaint begins with
/// questions whose answers a person does not know and is not obliged to
/// know: which version of the core, which of the protocol, what was in the
/// journal, whether recognition is on. Collecting that by hand is ten
/// steps through folders hidden away in <c>AppData</c>.
/// </para>
/// <para>
/// <b>The shell collects it.</b> The archive, the files and the details
/// of the operating system are the system layer (ADR 0009). The core hands
/// over what only it knows, and hands it over by ordinary methods: it does
/// not give secret keys out by itself, and that does not have to be
/// repeated here.
/// </para>
/// <para>
/// <b>Free text does not travel.</b> A value picked from an enumeration
/// is not the person's own text, and it is written as it is; everything
/// else is replaced by its length. The rule is the same as in the call
/// journal (<c>core/audit.py</c>), and it is deliberately strict: it
/// catches both a harmless key combination and a path to a model with the
/// person's name in it. One explainable rule is better than a list of
/// exceptions that one day nobody remembers to extend.
/// </para>
/// <para>
/// <b>The journals travel as they are, and that is said out loud.</b>
/// They are where the answer to "what happened" lives, which is what the
/// bundle is collected for. But the <c>log_texts</c> setting permits the
/// text of spoken lines to be written into the journal — and if it is on,
/// the person must find out **before** they send the archive, not after.
/// That is why its value stands in the explanation's first line.
/// </para>
/// </remarks>
public static class Diagnostics
{
    /// <summary>What came of it: the path to the archive, or the reason
    /// for refusing.</summary>
    public sealed record Result(bool Ok, string Path, string Problem);

    /// <summary>Where to suggest saving: a name with a timestamp, so that
    /// nothing is overwritten.</summary>
    public static string SuggestedName() =>
        $"rina-diagnostics-{DateTime.Now:yyyy-MM-dd-HHmm}.zip";

    private static string DataDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "RinaAssistant");

    /// <summary>
    /// Collect the bundle.
    /// </summary>
    /// <remarks>
    /// The core may be off the line — and that is the commonest case the
    /// bundle is collected for. Then the versions and the settings are
    /// unavailable while the journals are available; the bundle is built
    /// from what there is, and what is missing is named rather than
    /// skipped silently.
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

    /// <summary>Both layers' journals. The rotated ones too: the failure
    /// may have happened before the rotation.</summary>
    private static void AddLogs(ZipArchive archive)
    {
        var logs = Path.Combine(DataDir, "logs");
        if (!Directory.Exists(logs)) return;
        foreach (var file in Directory.EnumerateFiles(logs))
        {
            try
            {
                // We read without getting in the way of writing: the
                // journal is open for appending by both processes, and an
                // ordinary read trips over the sharing mode. A bundle
                // that cannot be collected while the program is running
                // is useless — that is exactly when it is looked into.
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
                // One journal read short is no reason to end up with no bundle.
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

    /// <summary>The settings, and whether the text of spoken lines was
    /// written into the journal.</summary>
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
    /// A value in a form fit for sending.
    /// </summary>
    /// <remarks>
    /// A value picked from an enumeration is not the person's own text,
    /// and it travels as it is. Free text, a list and a dictionary turn
    /// into a length and a size: "how much" answers almost every question
    /// an investigation asks, "what exactly" answers none of them.
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

        // The first line, because this is the one thing the person must
        // find out before sending rather than after.
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
