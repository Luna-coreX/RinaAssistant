using System.IO;
using System.Text;

namespace Rina.Shell.Platform;

/// <summary>
/// Журнал безопасности со стороны оболочки.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-G12</c>: по журналу должно быть видно, что и откуда
/// запускалось — <b>без содержимого разговора</b>. Текст команды сюда не
/// попадает никогда, даже при включённой настройке `log_texts`: «что
/// запускали» и «что человек сказал» — разные сведения, и держать их в
/// одном файле незачем.
/// </para>
/// <para>
/// <b>Пишется в тот же файл, что и у ядра</b>
/// (<c>%APPDATA%\RinaAssistant\logs\security.log</c>). Два файла на одну
/// хронологию значили бы, что при разборе происшествия их надо сшивать
/// руками по времени, и первая же несостыковка часов сделает это
/// невозможным.
/// </para>
/// <para>
/// <b>Отказ записать не отменяет действие.</b> Журнал — свидетельство, а
/// не разрешение; программа, отказавшаяся запускать программу из-за
/// занятого файла журнала, была бы хуже, а не безопаснее.
/// </para>
/// </remarks>
public static class Journal
{
    private static readonly object Lock = new();

    /// <summary>Куда пишется журнал — чтобы проверка искала там же.</summary>
    public static string Where => Path;

    private static string Path => System.IO.Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "RinaAssistant", "logs", "security.log");

    /// <summary>Запуск программы: что, откуда, с согласием или нет, чем кончилось.</summary>
    public static void Launch(string what, string kind, bool trusted, bool ok,
                              string note = "")
    {
        var source = kind == "uwp" ? "uwp" : SourceOf(what);
        Write($"launch app={Name(what)} path={what} source={source} "
              + $"trusted={(trusted ? "да" : "нет")} "
              + $"result={(ok ? "ok" : "fail")}"
              + (note.Length > 0 ? $" note={note}" : ""));
    }

    /// <summary>Человек разрешил неподписанному запускаться всегда.</summary>
    public static void Trusted(string path)
        => Write($"trust path={path} scope=always");

    /// <summary>
    /// Обновления: проверка, закачка, целостность, установка.
    /// </summary>
    /// <remarks>
    /// Задача плана <c>4.0-U05</c>. Пишется туда же, куда запуски: разбор
    /// происшествия «после какого обновления это началось» невозможен,
    /// если обновления лежат в одном файле, а запуски в другом.
    /// </remarks>
    public static void Update(string stage, string detail)
        => Write($"update stage={stage} {detail}");

    /// <summary>Системное действие: громкость, питание, снимок.</summary>
    public static void Action(string action, bool ok)
        => Write($"system action={action} result={(ok ? "ok" : "fail")}");

    private static string Name(string what)
    {
        try
        {
            return System.IO.Path.GetFileName(what);
        }
        catch
        {
            return what;
        }
    }

    /// <summary>
    /// Откуда взялась запись — по её месту в индексе.
    /// </summary>
    /// <remarks>
    /// Спрашивается индекс, а не путь: «откуда узнали» и «где лежит» —
    /// разные вещи, и в журнале нужна первая.
    /// </remarks>
    private static string SourceOf(string path)
    {
        try
        {
            return AppIndex.Get().FirstOrDefault(
                e => string.Equals(e.Launch, path,
                                   StringComparison.OrdinalIgnoreCase))
                ?.Source ?? "unknown";
        }
        catch
        {
            return "unknown";
        }
    }

    private static void Write(string line)
    {
        try
        {
            var stamped = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} | SECURITY | "
                          + $"shell | {line}{Environment.NewLine}";
            lock (Lock)
            {
                Directory.CreateDirectory(
                    System.IO.Path.GetDirectoryName(Path)!);

                // Открываем, разрешая писать и другим. Тот же файл держит
                // ядро своим журналом, и `File.AppendAllText` открывает
                // его без права другим писать — то есть **никогда** не
                // может дописать, пока ядро живо. Записи оболочки не
                // появлялись вовсе, а исключение проглатывалось: журнал
                // не имеет права ронять то, что он записывает.
                using var file = new FileStream(
                    Path, FileMode.Append, FileAccess.Write,
                    FileShare.ReadWrite | FileShare.Delete);
                var bytes = Encoding.UTF8.GetBytes(stamped);
                file.Write(bytes, 0, bytes.Length);
            }
        }
        catch
        {
            // Журнал — свидетельство, а не разрешение: не записалось —
            // действие всё равно состоялось, и молчать об этом честнее,
            // чем ронять запуск. Молчание здесь и стоило того, что записи
            // не было полгода: поэтому проверка теперь читает файл.
        }
    }
}
