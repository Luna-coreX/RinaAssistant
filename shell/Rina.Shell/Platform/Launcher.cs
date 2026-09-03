using System.IO;
using System.Diagnostics;

namespace Rina.Shell.Platform;

/// <summary>
/// Запуск программ и учёт того, что запускалось.
/// </summary>
/// <remarks>
/// <para>
/// Задачи плана <c>4.0-G05</c>, <c>G10</c>, <c>G11</c>, <c>G12</c>.
/// </para>
/// <para>
/// <b>Между «Рина решила» и «процесс запущен» стоит эта проверка.</b> Путь
/// приводится к каноническому виду, запрещённые каталоги отсекаются, а
/// неподписанный файл при первом запуске требует согласия человека. Ядро
/// решает, <i>что</i> запустить; отвечает за то, <i>можно ли</i>, —
/// оболочка ([ADR 0009](../../../docs/adr/0009-system-layer.md)).
/// </para>
/// <para>
/// <b>Записывается каждый запуск</b> (<c>4.0-G12</c>): что, откуда,
/// спрашивали ли согласие, чем кончилось. Текста команды в журнале нет —
/// он под настройкой <c>log_texts</c> и в системный журнал не попадает
/// никогда: «что запускали» и «что человек сказал» — разные сведения, и
/// смешивать их в одном файле незачем.
/// </para>
/// </remarks>
public static class Launcher
{
    /// <summary>Чем кончился запуск.</summary>
    /// <param name="Ok">Процесс пошёл.</param>
    /// <param name="Reason">Почему не пошёл — для ядра, не для человека.</param>
    /// <param name="NeedsTrust">Нужно согласие на неподписанное.</param>
    public sealed record Outcome(bool Ok, string Reason = "",
                                 bool NeedsTrust = false);

    /// <summary>
    /// Запустить то, что назвало ядро.
    /// </summary>
    /// <param name="launch">Путь к файлу или AppID пакета.</param>
    /// <param name="kind">«file» или «uwp».</param>
    /// <param name="trusted">
    /// Человек уже согласился на этот неподписанный файл.
    /// </param>
    public static Outcome Start(string launch, string kind, bool trusted)
    {
        if (string.IsNullOrWhiteSpace(launch))
            return new Outcome(false, "пусто");

        if (kind == "uwp")
        {
            // У пакета нет пути: запускается через shell-протокол.
            var started = Shell($"shell:AppsFolder\\{launch}");
            Journal.Launch(launch, "uwp", trusted: true, ok: started);
            return started ? new Outcome(true)
                : new Outcome(false, "пакет не запустился");
        }

        var path = AppIndex.Canonical(launch);
        if (path.Length == 0 || !File.Exists(path))
        {
            Journal.Launch(launch, "file", trusted, ok: false, note: "нет файла");
            return new Outcome(false, "файла нет");
        }

        // Запрет сильнее согласия: «Загрузки» не запускаются, даже если
        // человек однажды сказал «всегда доверять» чему-то оттуда.
        if (AppIndex.Forbidden(path))
        {
            Journal.Launch(path, "file", trusted, ok: false,
                           note: "запрещённый каталог");
            return new Outcome(false, "запрещённый каталог");
        }

        // Неподписанное — только с согласия, и только в первый раз.
        if (!trusted && !Trust.Allowed(path))
        {
            Journal.Launch(path, "file", trusted: false, ok: false,
                           note: "нужно согласие");
            return new Outcome(false, "нужно согласие", NeedsTrust: true);
        }

        var ran = Shell(path);
        Journal.Launch(path, "file", trusted || Trust.Allowed(path), ran);
        return ran ? new Outcome(true) : new Outcome(false, "не запустилось");
    }

    /// <summary>
    /// Запуск средствами оболочки системы.
    /// </summary>
    /// <remarks>
    /// <c>UseShellExecute</c> обязателен: так запускаются и ярлыки, и
    /// пакеты, и файлы с ассоциацией — тем же способом, каким это делает
    /// проводник. Своего разбора ярлыков мы не пишем.
    /// </remarks>
    private static bool Shell(string what)
    {
        try
        {
            var started = Process.Start(new ProcessStartInfo
            {
                FileName = what,
                UseShellExecute = true,
                WorkingDirectory = SafeFolder(what),
            });
            return started is not null || File.Exists(what);
        }
        catch
        {
            return false;
        }
    }

    /// <summary>
    /// Рабочий каталог — папка самой программы.
    /// </summary>
    /// <remarks>
    /// Иначе им станет каталог Рины, и программа, ищущая файлы рядом с
    /// собой, их не найдёт. Для пакетов и протоколов каталога нет — пусто.
    /// </remarks>
    private static string SafeFolder(string what)
    {
        try
        {
            return File.Exists(what) ? Path.GetDirectoryName(what) ?? "" : "";
        }
        catch
        {
            return "";
        }
    }
}
