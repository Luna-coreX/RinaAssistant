using System.Text.Json.Nodes;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Update;

/// <summary>
/// One part of a release: the shell or the core.
/// </summary>
/// <remarks>
/// The fields and the reasoning — [MANIFEST.md](../../../docs/updates/MANIFEST.md).
/// </remarks>
public sealed record Part
{
    public required string Name { get; init; }
    public required string Version { get; init; }
    public required string Url { get; init; }
    public required string Sha256 { get; init; }

    /// <summary>The protocol versions this part implements.</summary>
    /// <remarks>
    /// A set, not a number: compatibility is decided by intersecting the
    /// sets (ADR 0004), and a shell holding two versions for the sake of a
    /// staged update has to be able to say so.
    /// </remarks>
    public int[] Protocol { get; init; } = [];

    public long Size { get; init; }
    public string Notes { get; init; } = "";
    public bool MustUpdate { get; init; }

    /// <summary>The on-disk data schema version. The core has one; the shell does not.</summary>
    public int DataSchema { get; init; }

    /// <summary>A hint to the downloader, not a rule (ADR 0004).</summary>
    public string MinOther { get; init; } = "";
    public string MaxOther { get; init; } = "";
}

/// <summary>
/// The release metadata as a whole.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-U02</c>. One file for both parts, because there are
/// two parts and one decision: separate metadata would allow reading the
/// shell's fresh data next to the core's year-old data and calling the
/// pair compatible with no way to check.
/// </para>
/// <para>
/// <b>Parsing invents nothing.</b> A part without an address, a hash or a
/// version is not a part, and it is dropped along with a stated reason.
/// An update installed from half-read metadata is exactly the case where
/// a silent guess costs more than a refusal.
/// </para>
/// </remarks>
public sealed record Manifest
{
    public int Version { get; init; } = 1;
    public string Channel { get; init; } = "stable";
    public string Published { get; init; } = "";
    public string NotesUrl { get; init; } = "";
    public Dictionary<string, Part> Parts { get; init; } = [];

    /// <summary>What is wrong with the metadata; empty means all is well.</summary>
    public string Problem { get; init; } = "";

    public bool Ok => Problem.Length == 0;

    public Part? Shell => Parts.GetValueOrDefault("shell");
    public Part? Core => Parts.GetValueOrDefault("core");

    /// <summary>
    /// Parse the metadata.
    /// </summary>
    /// <remarks>
    /// Returns a manifest with the trouble described rather than throwing:
    /// "we could not read it" is an ordinary outcome of an update check,
    /// and it has to be shown to the person in words, not as an exception
    /// in a log.
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

        // Without any of the three the part is useless: nothing to compare,
        // nowhere to fetch from, or nothing to verify with.
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
    /// Compare versions of the form <c>4.0.10</c>.
    /// </summary>
    /// <remarks>
    /// By numbers, not as strings: "4.0.10" sorts below "4.0.9", and the
    /// tenth patch would never be offered as an update.
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
