using System.IO;
using System.Text.Json;

namespace Rina.Shell.Platform;

/// <summary>
/// What the person has allowed to run unsigned.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-G10</c>. Before an unsigned file runs for the first
/// time, the person is shown its name, full path, source and the absence
/// of a signature, and offered "once", "always" or "cancel". An "always"
/// is kept here and revoked in settings.
/// </para>
/// <para>
/// <b>The key is the canonical path, not the name.</b> Trusting
/// "updater.exe" as such would mean trusting any file by that name;
/// trusting a specific path at least means a specific file.
/// </para>
/// <para>
/// <b>Consent lives with the shell.</b> This is not a setting about how
/// Rina behaves but a record of what the person permitted the system
/// layer, and it is kept where the system layer is
/// ([ADR 0009](../../../docs/adr/0009-system-layer.md)).
/// </para>
/// </remarks>
public static class Trust
{
    private static readonly object Lock = new();
    private static Dictionary<string, DateTime>? _allowed;

    private static string Path =>
        System.IO.Path.Combine(DataFolder.Roaming, "trusted.json");

    /// <summary>
    /// Programs whose signature says nothing about what they will do: they
    /// run whatever command they are handed (audit 2026-10-07, M-3).
    /// </summary>
    /// <remarks>
    /// A shortcut to a signed <c>powershell.exe</c> with a command in its
    /// arguments is not a signed program being started — it is that
    /// command. For these, given arguments, the signature does not answer
    /// the question, and consent is about the target and the command
    /// together: the same host with another command is asked about again.
    /// </remarks>
    public static readonly HashSet<string> Hosts = new(StringComparer.OrdinalIgnoreCase)
    {
        "cmd.exe", "powershell.exe", "pwsh.exe", "wscript.exe", "cscript.exe",
        "mshta.exe", "rundll32.exe", "regsvr32.exe", "msiexec.exe",
        "explorer.exe", "conhost.exe", "wsl.exe", "bash.exe",
        "python.exe", "pythonw.exe", "py.exe", "pyw.exe", "node.exe",
        "java.exe", "javaw.exe",
    };

    /// <summary>Does this target run a command it is handed.</summary>
    public static bool RunsCommand(string path, string arguments) =>
        arguments.Trim().Length > 0
        && Hosts.Contains(System.IO.Path.GetFileName(path));

    private static string Key(string canonical, string arguments) =>
        RunsCommand(canonical, arguments)
            ? canonical.ToLowerInvariant() + " " + arguments.Trim()
            : canonical.ToLowerInvariant();

    /// <summary>Whether the file is signed or the person already allowed it.</summary>
    /// <param name="path">What runs — for a shortcut, its target.</param>
    /// <param name="arguments">What the shortcut hands it.</param>
    public static bool Allowed(string path, string arguments = "")
    {
        var canonical = AppIndex.Canonical(path);
        if (canonical.Length == 0) return false;
        if (!RunsCommand(canonical, arguments)
            && AppEntry.HasSignature(canonical)) return true;

        lock (Lock)
        {
            Load();
            return _allowed!.ContainsKey(Key(canonical, arguments));
        }
    }

    /// <summary>Remember an "always".</summary>
    public static void Remember(string path, string arguments = "")
    {
        var canonical = AppIndex.Canonical(path);
        if (canonical.Length == 0) return;
        lock (Lock)
        {
            Load();
            _allowed![Key(canonical, arguments)] = DateTime.UtcNow;
            Save();
        }
        Journal.Trusted(canonical);
    }

    /// <summary>Revoke consent.</summary>
    public static void Forget(string path)
    {
        lock (Lock)
        {
            Load();
            if (_allowed!.Remove(AppIndex.Canonical(path).ToLowerInvariant()))
                Save();
        }
    }

    /// <summary>
    /// Revoke these, or all of them — for the privacy page (audit
    /// 2026-10-07, H-4). How many went.
    /// </summary>
    /// <remarks>
    /// Here and not by deleting the file: the list lives in memory as well,
    /// and the next "always" would write the old one straight back.
    /// </remarks>
    public static int ForgetMany(IEnumerable<string>? paths)
    {
        lock (Lock)
        {
            Load();
            var before = _allowed!.Count;
            if (paths is null)
                _allowed.Clear();
            else
                foreach (var path in paths)
                    _allowed.Remove(path.ToLowerInvariant());
            var gone = before - _allowed.Count;
            if (gone > 0) Save();
            return gone;
        }
    }

    /// <summary>What is allowed — for showing in settings.</summary>
    public static IReadOnlyDictionary<string, DateTime> All()
    {
        lock (Lock)
        {
            Load();
            return new Dictionary<string, DateTime>(_allowed!);
        }
    }

    private static void Load()
    {
        if (_allowed is not null) return;
        try
        {
            _allowed = File.Exists(Path)
                ? JsonSerializer.Deserialize<Dictionary<string, DateTime>>(
                      File.ReadAllText(Path)) ?? []
                : [];
        }
        catch
        {
            // A corrupted trust file reads as empty: better to ask the
            // person again than to allow something on the strength of junk.
            _allowed = [];
        }
    }

    private static void Save()
    {
        try
        {
            Directory.CreateDirectory(
                System.IO.Path.GetDirectoryName(Path)!);
            File.WriteAllText(Path, JsonSerializer.Serialize(_allowed));
        }
        catch
        {
            // Not written — the consent lasts until the next restart.
        }
    }
}
