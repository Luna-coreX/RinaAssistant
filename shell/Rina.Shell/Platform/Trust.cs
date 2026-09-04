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

    private static string Path => System.IO.Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "RinaAssistant", "trusted.json");

    /// <summary>Whether the file is signed or the person already allowed it.</summary>
    public static bool Allowed(string path)
    {
        var canonical = AppIndex.Canonical(path);
        if (canonical.Length == 0) return false;
        if (AppEntry.HasSignature(canonical)) return true;

        lock (Lock)
        {
            Load();
            return _allowed!.ContainsKey(canonical.ToLowerInvariant());
        }
    }

    /// <summary>Remember an "always".</summary>
    public static void Remember(string path)
    {
        var canonical = AppIndex.Canonical(path);
        if (canonical.Length == 0) return;
        lock (Lock)
        {
            Load();
            _allowed![canonical.ToLowerInvariant()] = DateTime.UtcNow;
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
