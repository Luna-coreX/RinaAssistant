using System.IO;
using System.Diagnostics;
using System.Text.Json;
using Microsoft.Win32;

namespace Rina.Shell.Platform;

/// <summary>
/// The index of installed programs.
/// </summary>
/// <remarks>
/// <para>
/// Plan items <c>4.0-G04</c>, <c>G08</c>, <c>G09</c>, <c>G11</c>. The
/// index lives in the shell because it is <b>operating system data</b>;
/// matching a name against an entry lives in the core because that is
/// language ([ADR 0009](../../../docs/adr/0009-system-layer.md)).
/// </para>
/// <para>
/// <b>The desktop and Downloads are not scanned.</b> In 3.1.0 the desktop
/// was walked by default, and that was a mistake: downloaded things land
/// there, and indexing what was downloaded means offering to launch
/// anything the person ever saved. Portable programs are added as a
/// folder by hand and are visible as a list in settings. The prohibition
/// is enforced, not assumed: <see cref="Forbidden"/> cuts such paths off
/// even when an explicit setting slipped them in.
/// </para>
/// <para>
/// <b>Sources run from system to user</b> (<c>4.0-G08</c>): paths
/// registered by the system → the Start menu → packages → `PATH` → added
/// folders. When names collide the higher one wins: a system entry has
/// more claim to being what the person meant.
/// </para>
/// <para>
/// <b>Paths are resolved to canonical form</b> (<c>4.0-G11</c>): a
/// symlink or junction leading out of a trusted folder would otherwise
/// carry a launch past every check. Entries whose files have vanished are
/// dropped on reindex — an index that remembers deleted things will one
/// day launch the wrong one.
/// </para>
/// </remarks>
public static class AppIndex
{
    /// <summary>Source order: the smaller, the weightier.</summary>
    public static readonly string[] SourceOrder =
        ["app_paths", "start_menu", "uwp", "path", "folder"];

    /// <summary>
    /// Directories that are never indexed.
    /// </summary>
    /// <remarks>
    /// Downloaded and temporary things land here. The list forbids rather
    /// than merely "not scanned by default": the difference is that a
    /// person may add a folder by hand, and Downloads is one they must not
    /// be able to add even that way.
    /// </remarks>
    public static readonly Environment.SpecialFolder[] ForbiddenFolders =
    [
        Environment.SpecialFolder.Desktop,
        Environment.SpecialFolder.CommonDesktopDirectory,
    ];

    /// <summary>Whether the path is somewhere we must not launch from.</summary>
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
    /// The canonical path: no symlink, no junction, no "..".
    /// </summary>
    /// <remarks>
    /// An empty string means the path did not resolve, and that is an
    /// answer of "no", not of "probably yes". A trust check that stumbled
    /// over an unresolvable path is obliged to refuse: an unclear path is
    /// itself grounds to refuse.
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

    // --------------------------------------------------------- gathering

    /// <summary>Build the index from scratch.</summary>
    public static List<AppEntry> Build(IEnumerable<string>? folders = null)
    {
        var found = new List<AppEntry>();
        found.AddRange(FromAppPaths());
        found.AddRange(FromStartMenu());
        found.AddRange(FromPackages());
        found.AddRange(FromPath());
        foreach (var folder in folders ?? [])
            found.AddRange(FromFolder(folder));

        // The same Telegram arrives both from the Start menu and from
        // PATH. The source higher up the list wins: a system entry has
        // more claim to being what the person meant.
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

    /// <summary>Launch paths registered by the system (App Paths).</summary>
    /// <remarks>
    /// The weightiest source: a program lands here by declaring itself at
    /// install time — that is, by the installer's decision, not because a
    /// file happens to lie somewhere.
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

    /// <summary>Start menu shortcuts — what the person sees themselves.</summary>
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
                    // We do not ask a shortcut for a signature: what is
                    // signed is not the shortcut but what it points at, and
                    // resolving the target for that is work for launching,
                    // not for a sweep.
                    Signed = true,
                };
            }
        }
    }

    /// <summary>Store packages: they have no path, they have an AppID.</summary>
    private static IEnumerable<AppEntry> FromPackages()
    {
        var listed = new List<AppEntry>();
        try
        {
            // PowerShell enumerates the packages: .NET has no API of its
            // own for this, and the package COM interface would want a
            // wrapper for the sake of one call.
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
                    // A Store package is signed by definition: an
                    // unsigned one does not get in there.
                    Signed = true,
                });
            }
        }
        catch
        {
            // PowerShell disabled by policy or unavailable — no reason to
            // be left without an index entirely.
        }
        return listed;
    }

    /// <summary>Programs from PATH — existing files only.</summary>
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

    /// <summary>A folder the person added: portable programs.</summary>
    private static IEnumerable<AppEntry> FromFolder(string folder)
    {
        if (!Directory.Exists(folder) || Forbidden(folder)) yield break;

        foreach (var file in Walk(folder, "*.exe"))
        {
            var path = Canonical(file);
            if (path.Length == 0) continue;

            // A junction inside an added folder that leads outside must
            // not drag whatever it likes into the index (4.0-G11).
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

    // ------------------------------------------------------- small things

    // Words that mark a shortcut as junk. Both languages on purpose: on a
    // Russian Windows the Start menu says «Удалить», on an English one it
    // says «Uninstall», and the index sees whichever the system wrote.
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

    /// <summary>The name from the file's resources, when it is meaningful.</summary>
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
        // Walking the registry stumbles over branches without rights.
        // The whole index must not fall over because of that.
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
    /// Walk the tree, skipping whatever would not open.
    /// </summary>
    /// <remarks>
    /// <c>EnumerateFiles</c> with <c>AllDirectories</c> will not do here:
    /// it throws on the first inaccessible folder and the walk stops
    /// altogether. That is exactly what happened — not a single entry
    /// arrived from the Start menu, though there are hundreds of shortcuts
    /// there. Hence a walk of our own: an unreadable branch is skipped and
    /// its neighbours remain.
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

    // --------------------------------------------------------------- cache

    private static string CachePath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "RinaAssistant", "app_index.json");

    /// <summary>How the cache file is shaped; grows when the format changes.</summary>
    private const int CacheVersion = 2;

    private static List<AppEntry>? _memory;

    /// <summary>
    /// The index: from memory, from the file, or built afresh.
    /// </summary>
    /// <remarks>
    /// Building takes seconds, hence the cache. Entries whose files have
    /// vanished are dropped while reading: an index that remembers deleted
    /// things will one day launch the wrong one (<c>4.0-G11</c>).
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
            // The cache did not write — the program works, only slower.
        }
    }

    private sealed class Cache
    {
        public int Version { get; set; }
        public List<AppEntry> Entries { get; set; } = [];
    }
}
