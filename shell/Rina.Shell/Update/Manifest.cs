using System.Text.Json.Nodes;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Update;

/// <summary>
/// Одна часть выпуска: оболочка или ядро.
/// </summary>
/// <remarks>
/// Поля и причины — [MANIFEST.md](../../../docs/updates/MANIFEST.md).
/// </remarks>
public sealed record Part
{
    public required string Name { get; init; }
    public required string Version { get; init; }
    public required string Url { get; init; }
    public required string Sha256 { get; init; }

    /// <summary>Версии протокола, которые часть реализует.</summary>
    /// <remarks>
    /// Набор, а не число: совместимость решает пересечение наборов
    /// (ADR 0004), и оболочка, держащая две версии ради ступенчатого
    /// обновления, обязана уметь это объявить.
    /// </remarks>
    public int[] Protocol { get; init; } = [];

    public long Size { get; init; }
    public string Notes { get; init; } = "";
    public bool MustUpdate { get; init; }

    /// <summary>Версия схемы данных на диске. Есть только у ядра.</summary>
    public int DataSchema { get; init; }

    /// <summary>Подсказка загрузчику, а не правило (ADR 0004).</summary>
    public string MinOther { get; init; } = "";
    public string MaxOther { get; init; } = "";
}

/// <summary>
/// Метаданные выпуска целиком.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-U02</c>. Один файл на обе части, потому что части
/// две, а решение одно: раздельные метаданные позволили бы прочитать
/// свежие данные оболочки рядом с годовалыми данными ядра и счесть пару
/// совместимой, не имея возможности это проверить.
/// </para>
/// <para>
/// <b>Разбор ничего не додумывает.</b> Часть без адреса, без хэша или без
/// версии — это не часть, и она отбрасывается вместе с внятной причиной.
/// Обновление, поставленное по наполовину прочитанным метаданным, — тот
/// самый случай, когда молчаливая догадка стоит дороже отказа.
/// </para>
/// </remarks>
public sealed record Manifest
{
    public int Version { get; init; } = 1;
    public string Channel { get; init; } = "stable";
    public string Published { get; init; } = "";
    public string NotesUrl { get; init; } = "";
    public Dictionary<string, Part> Parts { get; init; } = [];

    /// <summary>Что не так с метаданными; пусто — всё в порядке.</summary>
    public string Problem { get; init; } = "";

    public bool Ok => Problem.Length == 0;

    public Part? Shell => Parts.GetValueOrDefault("shell");
    public Part? Core => Parts.GetValueOrDefault("core");

    /// <summary>
    /// Разобрать метаданные.
    /// </summary>
    /// <remarks>
    /// Возвращает манифест с описанной бедой, а не бросает: «не смогли
    /// прочитать» — обычный исход проверки обновлений, и показать его
    /// человеку надо словами, а не исключением в журнале.
    /// </remarks>
    public static Manifest Parse(string json)
    {
        JsonObject? root;
        try
        {
            root = JsonNode.Parse(json) as JsonObject;
        }
        catch (Exception error)
        {
            return new Manifest
            {
                Problem = S("не разобрали ответ: {0}", error.Message),
            };
        }
        if (root is null) return new Manifest { Problem = S("ответ не объект") };

        var version = root["manifest_version"]?.GetValue<int>() ?? 0;
        if (version != 1)
            return new Manifest
            {
                Problem = S("метаданные версии {0}, а мы умеем 1", version),
            };

        var parts = new Dictionary<string, Part>();
        if (root["parts"] is JsonObject listed)
            foreach (var (name, node) in listed)
            {
                if (node is not JsonObject part) continue;
                var read = Read(name, part);
                if (read is not null) parts[name] = read;
            }

        if (parts.Count == 0)
            return new Manifest { Problem = S("в метаданных нет ни одной части") };

        return new Manifest
        {
            Version = version,
            Channel = root["channel"]?.GetValue<string>() ?? "stable",
            Published = root["published"]?.GetValue<string>() ?? "",
            NotesUrl = root["notes_url"]?.GetValue<string>() ?? "",
            Parts = parts,
        };
    }

    private static Part? Read(string name, JsonObject part)
    {
        var version = part["version"]?.GetValue<string>() ?? "";
        var url = part["url"]?.GetValue<string>() ?? "";
        var hash = part["sha256"]?.GetValue<string>() ?? "";

        // Без любого из трёх часть бесполезна: нечего сравнить, неоткуда
        // взять или нечем проверить.
        if (version.Length == 0 || url.Length == 0 || hash.Length == 0)
            return null;

        return new Part
        {
            Name = name,
            Version = version,
            Url = url,
            Sha256 = hash.ToLowerInvariant(),
            Protocol = part["protocol"]?.AsArray()
                .Select(v => v?.GetValue<int>() ?? 0).Where(v => v > 0)
                .ToArray() ?? [],
            Size = part["size"]?.GetValue<long>() ?? 0,
            Notes = part["notes"]?.GetValue<string>() ?? "",
            MustUpdate = part["must_update"]?.GetValue<bool>() ?? false,
            DataSchema = part["data_schema"]?.GetValue<int>() ?? 0,
            MinOther = part["min_core_version"]?.GetValue<string>() ?? "",
            MaxOther = part["max_core_version"]?.GetValue<string>() ?? "",
        };
    }

    /// <summary>
    /// Сравнить версии вида <c>4.0.10</c>.
    /// </summary>
    /// <remarks>
    /// Числами, а не строками: «4.0.10» строкой меньше «4.0.9», и
    /// обновление на десятую заплату никогда бы не предложилось.
    /// </remarks>
    public static int Compare(string left, string right)
    {
        var a = Numbers(left);
        var b = Numbers(right);
        for (var i = 0; i < Math.Max(a.Length, b.Length); i++)
        {
            var one = i < a.Length ? a[i] : 0;
            var two = i < b.Length ? b[i] : 0;
            if (one != two) return one.CompareTo(two);
        }
        return 0;
    }

    private static int[] Numbers(string version) => version
        .TrimStart('v', 'V')
        .Split('.', '-', '+')
        .Select(piece => int.TryParse(
            new string(piece.TakeWhile(char.IsDigit).ToArray()), out var n)
            ? n : 0)
        .ToArray();
}
