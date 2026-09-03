using System.IO;
using System.Diagnostics;
using System.Text.Json;
using Microsoft.Win32;

namespace Rina.Shell.Platform;

/// <summary>
/// Индекс установленных программ.
/// </summary>
/// <remarks>
/// <para>
/// Задачи плана <c>4.0-G04</c>, <c>G08</c>, <c>G09</c>, <c>G11</c>.
/// Индекс живёт в оболочке, потому что это <b>данные операционной
/// системы</b>; сопоставление имени с записью — в ядре, потому что это
/// язык ([ADR 0009](../../../docs/adr/0009-system-layer.md)).
/// </para>
/// <para>
/// <b>Рабочий стол и «Загрузки» не сканируются.</b> В 3.1.0 рабочий стол
/// обходился по умолчанию, и это было ошибкой: туда попадает скачанное, а
/// индексировать скачанное значит предлагать запуск чему угодно, что
/// человек когда-то сохранил. Portable-программы добавляются папкой
/// вручную и видны списком в настройках. Запрет проверяется, а не
/// подразумевается: <see cref="Forbidden"/> отрезает такие пути даже если
/// их подсунули явной настройкой.
/// </para>
/// <para>
/// <b>Порядок источников — от системного к пользовательскому</b>
/// (<c>4.0-G08</c>): зарегистрированные системой пути → меню «Пуск» →
/// пакеты → `PATH` → добавленные папки. При совпадении имён побеждает тот,
/// что выше: у системной записи больше оснований быть тем, что человек
/// имел в виду.
/// </para>
/// <para>
/// <b>Путь приводится к каноническому виду</b> (<c>4.0-G11</c>): symlink
/// или junction из доверенной папки наружу иначе провёл бы запуск мимо
/// всех проверок. Записи с исчезнувшими файлами при переиндексации
/// выбрасываются — индекс, помнящий удалённое, однажды запустит не то.
/// </para>
/// </remarks>
public static class AppIndex
{
    /// <summary>Порядок источников: чем меньше, тем весомее.</summary>
    public static readonly string[] SourceOrder =
        ["app_paths", "start_menu", "uwp", "path", "folder"];

    /// <summary>
    /// Каталоги, которые не индексируются никогда.
    /// </summary>
    /// <remarks>
    /// Сюда попадает скачанное и временное. Список именно запрещающий, а
    /// не «не сканируемый по умолчанию»: разница в том, что человек может
    /// добавить папку руками, и «Загрузки» он добавить не должен даже так.
    /// </remarks>
    public static readonly Environment.SpecialFolder[] ForbiddenFolders =
    [
        Environment.SpecialFolder.Desktop,
        Environment.SpecialFolder.CommonDesktopDirectory,
    ];

    /// <summary>Лежит ли путь там, откуда запускать нельзя.</summary>
    public static bool Forbidden(string path)
    {
        var full = Canonical(path);
        if (full.Length == 0) return true;

        foreach (var folder in ForbiddenFolders)
        {
            var root = Environment.GetFolderPath(folder);
            if (root.Length > 0 && Inside(full, root)) return true;
        }

        var profile = Environment.GetFolderPath(
            Environment.SpecialFolder.UserProfile);
        foreach (var name in new[] { "Downloads", "Загрузки" })
            if (Inside(full, Path.Combine(profile, name))) return true;

        return Inside(full, Path.GetTempPath());
    }

    private static bool Inside(string path, string root)
    {
        if (root.Length == 0) return false;
        var canonical = Canonical(root);
        if (canonical.Length == 0) return false;
        if (!canonical.EndsWith(Path.DirectorySeparatorChar))
            canonical += Path.DirectorySeparatorChar;
        return path.StartsWith(canonical, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Канонический путь: без symlink, junction и «..».
    /// </summary>
    /// <remarks>
    /// Пустая строка — путь не разрешился, и это ответ «нельзя», а не
    /// «наверное можно». Проверка доверия, споткнувшаяся о неразрешимый
    /// путь, обязана отказать: непонятный путь и есть повод отказать.
    /// </remarks>
    public static string Canonical(string path)
    {
        if (string.IsNullOrWhiteSpace(path)) return "";
        try
        {
            var full = Path.GetFullPath(path);
            var link = File.Exists(full) ? new FileInfo(full).ResolveLinkTarget(true)
                     : Directory.Exists(full)
                       ? new DirectoryInfo(full).ResolveLinkTarget(true)
                       : null;
            return link?.FullName ?? full;
        }
        catch
        {
            return "";
        }
    }

    // ----------------------------------------------------------------- сбор

    /// <summary>Собрать индекс заново.</summary>
    public static List<AppEntry> Build(IEnumerable<string>? folders = null)
    {
        var found = new List<AppEntry>();
        found.AddRange(FromAppPaths());
        found.AddRange(FromStartMenu());
        found.AddRange(FromPackages());
        found.AddRange(FromPath());
        foreach (var folder in folders ?? [])
            found.AddRange(FromFolder(folder));

        // Один и тот же Telegram приходит и из меню «Пуск», и из PATH.
        // Побеждает источник выше по списку: у системной записи больше
        // оснований быть тем, что человек имел в виду.
        var best = new Dictionary<string, AppEntry>(StringComparer.OrdinalIgnoreCase);
        foreach (var entry in found)
        {
            var key = entry.Name.Trim().ToLowerInvariant();
            if (key.Length == 0) continue;
            if (!best.TryGetValue(key, out var current)
                || Weight(entry.Source) < Weight(current.Source))
                best[key] = entry;
        }
        return best.Values.OrderBy(e => e.Name, StringComparer.CurrentCulture)
                          .ToList();
    }

    private static int Weight(string source)
    {
        var at = Array.IndexOf(SourceOrder, source);
        return at < 0 ? SourceOrder.Length : at;
    }

    /// <summary>Зарегистрированные системой пути запуска (App Paths).</summary>
    /// <remarks>
    /// Самый весомый источник: сюда программа попадает, объявив себя при
    /// установке, — то есть по решению установщика, а не по тому, что файл
    /// где-то лежит.
    /// </remarks>
    private static IEnumerable<AppEntry> FromAppPaths()
    {
        const string branch =
            @"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths";
        foreach (var root in new[] { Registry.LocalMachine, Registry.CurrentUser })
        {
            RegistryKey? paths = null;
            try { paths = root.OpenSubKey(branch); } catch { }
            if (paths is null) continue;

            using (paths)
                foreach (var name in Safe(() => paths.GetSubKeyNames()))
                {
                    string? target = null;
                    try
                    {
                        using var item = paths.OpenSubKey(name);
                        target = item?.GetValue("")?.ToString()?.Trim('"');
                    }
                    catch { }

                    var path = Canonical(target ?? "");
                    if (path.Length == 0 || !File.Exists(path)) continue;
                    if (Forbidden(path)) continue;

                    yield return new AppEntry
                    {
                        Name = FriendlyName(path, name),
                        Launch = path,
                        Source = "app_paths",
                        Aliases = [Path.GetFileNameWithoutExtension(name)],
                        Signed = AppEntry.HasSignature(path),
                    };
                }
        }
    }

    /// <summary>Ярлыки меню «Пуск» — то, что человек видит сам.</summary>
    private static IEnumerable<AppEntry> FromStartMenu()
    {
        var roots = new[]
        {
            Environment.GetFolderPath(Environment.SpecialFolder.StartMenu),
            Environment.GetFolderPath(Environment.SpecialFolder.CommonStartMenu),
        };

        foreach (var root in roots)
        {
            if (root.Length == 0 || !Directory.Exists(root)) continue;
            foreach (var link in Walk(root, "*.lnk"))
            {
                var name = Path.GetFileNameWithoutExtension(link);
                if (Junk(name)) continue;
                var path = Canonical(link);
                if (path.Length == 0 || Forbidden(path)) continue;

                yield return new AppEntry
                {
                    Name = name,
                    Launch = path,
                    Source = "start_menu",
                    Aliases = [name],
                    // Подпись у ярлыка не спрашиваем: подписан не ярлык, а
                    // то, на что он показывает, и раскрывать цель ярлыка
                    // ради этого — работа для запуска, а не для обхода.
                    Signed = true,
                };
            }
        }
    }

    /// <summary>Пакеты Магазина: у них нет пути, есть AppID.</summary>
    private static IEnumerable<AppEntry> FromPackages()
    {
        var listed = new List<AppEntry>();
        try
        {
            // Пакеты перечисляет PowerShell: своего API у .NET для этого
            // нет, а COM-интерфейс пакетов потребовал бы обёртки ради
            // одного вызова.
            var process = Process.Start(new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = "-NoProfile -NonInteractive -Command \"Get-StartApps | Where-Object AppID -like '*!*' | ForEach-Object { $_.Name + '|' + $_.AppID }\"",
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true,
                StandardOutputEncoding = System.Text.Encoding.UTF8,
            });
            if (process is null) return listed;

            var output = process.StandardOutput.ReadToEnd();
            process.WaitForExit(8000);

            foreach (var line in output.Split('\n'))
            {
                var parts = line.Trim().Split('|');
                if (parts.Length != 2 || parts[0].Length == 0) continue;
                if (Junk(parts[0])) continue;
                listed.Add(new AppEntry
                {
                    Name = parts[0],
                    Launch = parts[1],
                    Kind = "uwp",
                    Source = "uwp",
                    Aliases = [parts[0]],
                    // Пакет Магазина подписан по определению: неподписанный
                    // туда не попадает.
                    Signed = true,
                });
            }
        }
        catch
        {
            // PowerShell выключен политикой или недоступен — это не повод
            // остаться без индекса вовсе.
        }
        return listed;
    }

    /// <summary>Программы из PATH — только существующие файлы.</summary>
    private static IEnumerable<AppEntry> FromPath()
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var folder in (Environment.GetEnvironmentVariable("PATH") ?? "")
                     .Split(Path.PathSeparator))
        {
            if (folder.Trim().Length == 0 || !Directory.Exists(folder)) continue;
            foreach (var file in Walk(folder, "*.exe", depth: 0))
            {
                var path = Canonical(file);
                if (path.Length == 0 || Forbidden(path)) continue;
                if (!seen.Add(Path.GetFileNameWithoutExtension(path))) continue;

                yield return new AppEntry
                {
                    Name = FriendlyName(path, Path.GetFileNameWithoutExtension(path)),
                    Launch = path,
                    Source = "path",
                    Aliases = [Path.GetFileNameWithoutExtension(path)],
                    Signed = AppEntry.HasSignature(path),
                };
            }
        }
    }

    /// <summary>Папка, добавленная человеком: portable-программы.</summary>
    private static IEnumerable<AppEntry> FromFolder(string folder)
    {
        if (!Directory.Exists(folder) || Forbidden(folder)) yield break;

        foreach (var file in Walk(folder, "*.exe"))
        {
            var path = Canonical(file);
            if (path.Length == 0) continue;

            // Junction внутри добавленной папки, ведущий наружу, не должен
            // протаскивать в индекс что попало (4.0-G11).
            if (!Inside(path, folder) || Forbidden(path)) continue;
            var name = Path.GetFileNameWithoutExtension(path);
            if (Junk(name)) continue;

            yield return new AppEntry
            {
                Name = FriendlyName(path, name),
                Launch = path,
                Source = "folder",
                Aliases = [name],
                Signed = AppEntry.HasSignature(path),
            };
        }
    }

    // -------------------------------------------------------------- мелочи

    private static readonly string[] JunkWords =
    [
        "uninstall", "удалить", "readme", "changelog", "help", "справка",
        "manual", "документация", "website", "сайт", "support",
    ];

    private static bool Junk(string name)
    {
        var lower = name.ToLowerInvariant();
        return JunkWords.Any(word => lower.Contains(word));
    }

    /// <summary>Имя из ресурсов файла, если оно там осмысленное.</summary>
    private static string FriendlyName(string path, string fallback)
    {
        try
        {
            var described = FileVersionInfo.GetVersionInfo(path).FileDescription;
            if (!string.IsNullOrWhiteSpace(described)) return described.Trim();
        }
        catch { }
        return fallback;
    }

    private static IEnumerable<T> Safe<T>(Func<IEnumerable<T>> source)
    {
        // Перебор реестра спотыкается о ветки без прав. Ронять из-за
        // этого весь индекс нельзя.
        try
        {
            return source().ToList();
        }
        catch
        {
            return [];
        }
    }

    /// <summary>
    /// Обойти дерево, пропуская то, что не открылось.
    /// </summary>
    /// <remarks>
    /// <c>EnumerateFiles</c> с <c>AllDirectories</c> для этого не годится:
    /// он бросает на первой недоступной папке, и обход прекращается
    /// целиком. Так и вышло — из меню «Пуск» не пришло ни одной записи,
    /// хотя ярлыков там сотни. Обход своими руками: недоступная ветка
    /// пропускается, соседние остаются.
    /// </remarks>
    private static IEnumerable<string> Walk(string root, string pattern,
                                            int depth = 8)
    {
        var pending = new Queue<(string Path, int Left)>();
        pending.Enqueue((root, depth));

        while (pending.Count > 0)
        {
            var (folder, left) = pending.Dequeue();

            string[] files;
            try { files = Directory.GetFiles(folder, pattern); }
            catch { continue; }
            foreach (var file in files) yield return file;

            if (left <= 0) continue;
            string[] folders;
            try { folders = Directory.GetDirectories(folder); }
            catch { continue; }
            foreach (var next in folders) pending.Enqueue((next, left - 1));
        }
    }

    // --------------------------------------------------------------- кэш

    private static string CachePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "RinaAssistant", "app_index.json");

    /// <summary>Как устроен файл кэша; растёт при смене формата.</summary>
    private const int CacheVersion = 2;

    private static List<AppEntry>? _memory;

    /// <summary>
    /// Индекс: из памяти, из файла или заново.
    /// </summary>
    /// <remarks>
    /// Сборка занимает секунды, поэтому кэш есть. Записи с исчезнувшими
    /// файлами при чтении выбрасываются: индекс, помнящий удалённое,
    /// однажды запустит не то (<c>4.0-G11</c>).
    /// </remarks>
    public static List<AppEntry> Get(IEnumerable<string>? folders = null,
                                     bool refresh = false)
    {
        if (!refresh && _memory is not null) return _memory;
        if (!refresh)
        {
            var cached = Load();
            if (cached is not null) return _memory = cached;
        }

        var built = Build(folders);
        Save(built);
        return _memory = built;
    }

    private static List<AppEntry>? Load()
    {
        try
        {
            if (!File.Exists(CachePath)) return null;
            using var file = File.OpenRead(CachePath);
            var stored = JsonSerializer.Deserialize<Cache>(file);
            if (stored is null || stored.Version != CacheVersion) return null;

            var alive = stored.Entries
                .Where(e => e.Kind == "uwp" || File.Exists(e.Launch))
                .ToList();
            return alive.Count > 0 ? alive : null;
        }
        catch
        {
            return null;
        }
    }

    private static void Save(List<AppEntry> entries)
    {
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(CachePath)!);
            using var file = File.Create(CachePath);
            JsonSerializer.Serialize(file, new Cache
            {
                Version = CacheVersion,
                Entries = entries,
            });
        }
        catch
        {
            // Не записался кэш — программа работает, просто медленнее.
        }
    }

    private sealed class Cache
    {
        public int Version { get; set; }
        public List<AppEntry> Entries { get; set; } = [];
    }
}
