using System.IO;
using System.Net.Http;
using System.Security.Cryptography;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Update;

    /// <summary>The check did not go through: network, address, broken metadata.</summary>
public enum Verdict
{
    /// <summary>Nothing newer exists.</summary>
    Unknown,

    /// <summary>Only the shell updates.</summary>
    UpToDate,

    /// <summary>Only the core updates.</summary>
    ShellOnly,

    /// <summary>Both parts update.</summary>
    CoreOnly,

    /// <summary>The pair is incompatible: it must not be installed.</summary>
    Both,

/// <summary>The outcome of a check: what was found and what to do about it.</summary>
    Incompatible,
}

/// <summary>The outcome of a check: what was found and what to do about it.</summary>
public sealed record Found(Verdict Verdict, string Explanation,
                           Part? Shell = null, Part? Core = null,
                           bool MustUpdate = false);

/// <summary>
/// The update client.
/// </summary>
/// <remarks>
/// <para>
/// Plan items <c>4.0-U03</c>, <c>U04</c>, <c>U05</c>. The versioning
/// decision is
/// [ADR 0004](../../../docs/adr/0004-versioning-and-compatibility.md); the
/// shape of the metadata is
/// [MANIFEST.md](../../../docs/updates/MANIFEST.md).
/// </para>
/// <para>
/// <b>It lives in the shell.</b> Downloading a file and putting it on disk
/// is system-layer work
/// ([ADR 0009](../../../docs/adr/0009-system-layer.md)), and only whoever
/// stops the core can replace the core's files. The shell also outlives
/// the core and has somewhere to show the question.
/// </para>
/// <para>
/// <b>Compatibility is checked before installing, and the handshake
/// decides all the same.</b> What is compared here are the declared sets
/// of protocol versions — that lets us avoid downloading a pair that would
/// fail the handshake anyway. A mistake here costs a pointless download; a
/// mistake in a check trusted as the last word would cost a refused update
/// that would in fact have worked.
/// </para>
/// <para>
/// <b>There is no installing here.</b> A verified file is placed in a
/// separate folder and waits: swapping files under a running program is
/// the installer's job (<c>4.0-I01</c>), and doing half of it in two
/// places is worse than doing all of it in one.
/// </para>
/// </remarks>
public sealed class Updater
{
    /// <remarks>
    /// A release asset, not the description and not the tag name: a tag
    /// string tells you neither a hash nor an address. There is no server
    /// of our own yet — that is <c>4.0-U13</c>, and it will change the
    /// address, not the shape.
    /// </remarks>
    public const string Source =
        "https://api.github.com/repos/Luna-corex/RinaAssistant/releases/latest";

    private readonly HttpClient _web;
    private readonly int[] _protocol;

    public Updater(int[] shellProtocol, HttpClient? web = null)
    {
        _protocol = shellProtocol;
        _web = web ?? new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
        if (!_web.DefaultRequestHeaders.Contains("User-Agent"))
            _web.DefaultRequestHeaders.Add("User-Agent", "RinaAssistant");
    }

    /// <summary>Where the verified and pending files are put.</summary>
    public static string Staging => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "RinaAssistant", "updates");

    /// <summary>
    /// Ask whether anything newer exists.
    /// </summary>
    public async Task<Found> CheckAsync(string shellVersion, string coreVersion,
                                        int dataSchema,
                                        CancellationToken token = default)
    {
        Manifest manifest;
        try
        {
            manifest = Manifest.Parse(await FetchManifestAsync(token));
        }
        catch (Exception error)
        {
            var why = S("не удалось спросить источник: {0}", error.Message);
            Platform.Journal.Update("check", $"result=fail note={why}");
            return new Found(Verdict.Unknown, why);
        }

        if (!manifest.Ok)
        {
            Platform.Journal.Update("check", $"result=fail note={manifest.Problem}");
            return new Found(Verdict.Unknown, manifest.Problem);
        }

        var shell = Newer(manifest.Shell, shellVersion);
        var core = Newer(manifest.Core, coreVersion);

        Platform.Journal.Update("check",
            $"shell={shellVersion}→{manifest.Shell?.Version ?? "—"} "
            + $"core={coreVersion}→{manifest.Core?.Version ?? "—"} "
            + $"channel={manifest.Channel}");

        if (shell is null && core is null)
            return new Found(Verdict.UpToDate, S("Установлена последняя версия."));

        // The data schema: a rollback is bounded by data, not by process
        // compatibility (ADR 0004). A core that will not read what has been
        // written is not an update but a loss.
        if (core is not null && core.DataSchema > 0 && core.DataSchema < dataSchema)
            return Refuse(S("ядро {0} читает данные схемы {1}, а на диске уже {2}",
                            core.Version, core.DataSchema, dataSchema));

        // A pair that will not shake hands is not worth downloading.
        var willSpeak = shell?.Protocol ?? _protocol;
        var willHear = core?.Protocol ?? _protocol;
        if (willSpeak.Length > 0 && willHear.Length > 0
            && !willSpeak.Intersect(willHear).Any())
            return Refuse(S("оболочка говорит [{0}], ядро слышит [{1}]",
                            string.Join(", ", willSpeak),
                            string.Join(", ", willHear)));

        var must = (shell?.MustUpdate ?? false) || (core?.MustUpdate ?? false);
        var verdict = shell is not null && core is not null ? Verdict.Both
                    : shell is not null ? Verdict.ShellOnly
                    : Verdict.CoreOnly;

        return new Found(verdict, Describe(verdict, shell, core), shell, core,
                         must);
    }

    private static Found Refuse(string why)
    {
        Platform.Journal.Update("check", $"result=incompatible note={why}");
        return new Found(Verdict.Incompatible,
            S("Обновление не подходит к тому, что установлено: {0}.", why));
    }

    private static string Describe(Verdict verdict, Part? shell, Part? core)
        => verdict switch
        {
            Verdict.ShellOnly => S("Есть новая оболочка {0}.", shell!.Version),
            Verdict.CoreOnly => S("Есть новое ядро {0}.", core!.Version),
            _ => S("Есть обновление: оболочка {0}, ядро {1}.",
                   shell!.Version, core!.Version),
        };

    private static Part? Newer(Part? part, string installed)
        => part is not null && Manifest.Compare(part.Version, installed) > 0
            ? part : null;

    /// <summary>
    /// Fetch the metadata out of the release.
    /// </summary>
    /// <remarks>
    /// It looks for an asset named <c>manifest.json</c>. Its absence is not
    /// "there are no updates" but "the source is saying something we do not
    /// understand", and the difference matters: the first reassures, the
    /// second calls for attention.
    /// </remarks>
    private async Task<string> FetchManifestAsync(CancellationToken token)
    {
        var release = await _web.GetStringAsync(Source, token);
        var assets = System.Text.Json.Nodes.JsonNode.Parse(release)?["assets"]
                     ?.AsArray();
        var url = assets?.FirstOrDefault(
            a => a?["name"]?.GetValue<string>() == "manifest.json")
            ?["browser_download_url"]?.GetValue<string>();

        if (string.IsNullOrEmpty(url))
            throw new InvalidOperationException(
                S("в релизе нет manifest.json"));

        return await _web.GetStringAsync(Https(url), token);
    }

    /// <summary>
    /// Download a part and verify the hash.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>The hash is computed on the way, not afterwards.</b> Reading the
    /// file back off disk to verify it costs time and leaves a gap in
    /// which the file can be swapped.
    /// </para>
    /// <para>
    /// <b>A mismatch is not "damaged" but "the wrong file".</b> It is
    /// deleted whole: half an update left on disk will one day end up
    /// installed.
    /// </para>
    /// </remarks>
    public async Task<(bool Ok, string Path, string Problem)> DownloadAsync(
        Part part, IProgress<double>? progress = null,
        CancellationToken token = default)
    {
        var target = Path.Combine(Staging, $"{part.Name}-{part.Version}.bin");
        try
        {
            Directory.CreateDirectory(Staging);

            using var answer = await _web.GetAsync(
                Https(part.Url), HttpCompletionOption.ResponseHeadersRead, token);
            answer.EnsureSuccessStatusCode();

            var total = answer.Content.Headers.ContentLength ?? part.Size;
            using var sha = SHA256.Create();
            await using (var source = await answer.Content.ReadAsStreamAsync(token))
            await using (var file = File.Create(target))
            {
                var buffer = new byte[81920];
                long done = 0;
                int read;
                while ((read = await source.ReadAsync(buffer, token)) > 0)
                {
                    sha.TransformBlock(buffer, 0, read, null, 0);
                    await file.WriteAsync(buffer.AsMemory(0, read), token);
                    done += read;
                    if (total > 0) progress?.Report((double)done / total);
                }
                sha.TransformFinalBlock([], 0, 0);
            }

            var got = Convert.ToHexString(sha.Hash!).ToLowerInvariant();
            if (got != part.Sha256)
            {
                File.Delete(target);
                var why = S("хэш не сошёлся: ждали {0}…, получили {1}…",
                            part.Sha256[..8], got[..8]);
                Platform.Journal.Update("download",
                    $"part={part.Name} version={part.Version} "
                    + $"result=fail note={why}");
                return (false, "", why);
            }

            Platform.Journal.Update("download",
                $"part={part.Name} version={part.Version} result=ok "
                + $"sha256={got[..16]}");
            return (true, target, "");
        }
        catch (Exception error)
        {
            // The download broke off — no file should remain: something
            // half-downloaded and left on disk will one day end up installed.
            try { if (File.Exists(target)) File.Delete(target); } catch { }
            Platform.Journal.Update("download",
                $"part={part.Name} version={part.Version} "
                + $"result=fail note={error.GetType().Name}");
            return (false, "", error.Message);
        }
    }

    /// <summary>
    /// HTTPS only.
    /// </summary>
    /// <remarks>
    /// An update over an open channel is an invitation to swap it in
    /// transit. The hash from the same metadata is no protection: whoever
    /// swapped the answer will swap the hash too.
    /// </remarks>
    private static string Https(string url)
    {
        if (!url.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException(
                S("источник обновлений обязан быть https, а это «{0}»", url));
        return url;
    }
}
