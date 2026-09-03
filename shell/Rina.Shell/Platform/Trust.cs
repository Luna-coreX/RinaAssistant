using System.IO;
using System.Text.Json;

namespace Rina.Shell.Platform;

/// <summary>
/// Чему человек разрешил запускаться без подписи.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-G10</c>. Перед первым запуском неподписанного файла
/// человеку показывают имя, полный путь, источник и отсутствие подписи, и
/// предлагают «один раз», «всегда» или «отмена». Согласие «всегда»
/// хранится здесь и снимается в настройках.
/// </para>
/// <para>
/// <b>Ключ — канонический путь, а не имя.</b> Доверие к «updater.exe»
/// вообще было бы доверием к любому файлу с таким именем; доверие к
/// конкретному пути хотя бы означает конкретный файл.
/// </para>
/// <para>
/// <b>Согласие живёт у оболочки.</b> Это не настройка поведения Рины, а
/// запись о том, что человек разрешил системному слою, — и хранится там
/// же, где системный слой ([ADR 0009](../../../docs/adr/0009-system-layer.md)).
/// </para>
/// </remarks>
public static class Trust
{
    private static readonly object Lock = new();
    private static Dictionary<string, DateTime>? _allowed;

    private static string Path => System.IO.Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "RinaAssistant", "trusted.json");

    /// <summary>Подписан ли файл или человек его уже разрешил.</summary>
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

    /// <summary>Запомнить согласие «всегда».</summary>
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

    /// <summary>Отозвать согласие.</summary>
    public static void Forget(string path)
    {
        lock (Lock)
        {
            Load();
            if (_allowed!.Remove(AppIndex.Canonical(path).ToLowerInvariant()))
                Save();
        }
    }

    /// <summary>Что разрешено — для показа в настройках.</summary>
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
            // Испорченный файл доверия читается как пустой: лучше спросить
            // человека заново, чем разрешить по мусору.
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
            // Не записалось — согласие продержится до перезапуска.
        }
    }
}
