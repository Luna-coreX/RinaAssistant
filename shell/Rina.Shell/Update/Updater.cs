using System.IO;
using System.Net.Http;
using System.Security.Cryptography;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Update;

/// <summary>Что делать с найденным выпуском.</summary>
public enum Verdict
{
    /// <summary>Проверить не удалось: сеть, адрес, испорченные метаданные.</summary>
    Unknown,

    /// <summary>Стоит свежее некуда.</summary>
    UpToDate,

    /// <summary>Обновляется только оболочка.</summary>
    ShellOnly,

    /// <summary>Обновляется только ядро.</summary>
    CoreOnly,

    /// <summary>Обновляются обе части.</summary>
    Both,

    /// <summary>Пара несовместима: ставить нельзя.</summary>
    Incompatible,
}

/// <summary>Исход проверки: что нашли и что с этим делать.</summary>
public sealed record Found(Verdict Verdict, string Explanation,
                           Part? Shell = null, Part? Core = null,
                           bool MustUpdate = false);

/// <summary>
/// Клиент обновлений.
/// </summary>
/// <remarks>
/// <para>
/// Задачи плана <c>4.0-U03</c>, <c>U04</c>, <c>U05</c>. Решение о версиях —
/// [ADR 0004](../../../docs/adr/0004-versioning-and-compatibility.md),
/// форма метаданных — [MANIFEST.md](../../../docs/updates/MANIFEST.md).
/// </para>
/// <para>
/// <b>Живёт в оболочке.</b> Скачать файл и положить его на диск — работа
/// системного слоя ([ADR 0009](../../../docs/adr/0009-system-layer.md)), а
/// заменять файлы ядра может только тот, кто ядро останавливает. Оболочка
/// к тому же переживает ядро и имеет, где показать вопрос.
/// </para>
/// <para>
/// <b>Совместимость проверяется до установки, а решает всё равно
/// рукопожатие.</b> Здесь сверяются объявленные наборы версий протокола —
/// это позволяет не качать пару, которая всё равно не поздоровается.
/// Ошибка в такой проверке стоит бесполезной закачки; ошибка в проверке,
/// которой доверяют как последней инстанции, стоит отказа от обновления,
/// которое работало бы.
/// </para>
/// <para>
/// <b>Установки здесь нет.</b> Проверенный файл кладётся в отдельную папку
/// и ждёт: подмена файлов на работающей программе — работа установщика
/// (<c>4.0-I01</c>), и делать её наполовину в двух местах хуже, чем в
/// одном целиком.
/// </para>
/// </remarks>
public sealed class Updater
{
    /// <summary>Откуда берутся метаданные.</summary>
    /// <remarks>
    /// Актив релиза, а не описание и не имя тега: из строки тега нельзя
    /// узнать ни хэша, ни адреса. Своего сервера пока нет — это
    /// <c>4.0-U13</c>, и он изменит адрес, а не форму.
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

    /// <summary>Куда кладётся проверенное и ждущее установки.</summary>
    public static string Staging => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "RinaAssistant", "updates");

    /// <summary>
    /// Спросить, есть ли что-то новее.
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

        // Схема данных: откат ограничен данными, а не совместимостью
        // процессов (ADR 0004). Ядро, которое не прочитает написанное, —
        // не обновление, а потеря.
        if (core is not null && core.DataSchema > 0 && core.DataSchema < dataSchema)
            // Ключ перевода — один литерал, а не склейка: извлекатель
            // строк берёт первый и на этом останавливается, и половина
            // фразы уехала бы в таблицу как самостоятельная строка.
            return Refuse(S("ядро {0} читает данные схемы {1}, а на диске уже {2}",
                            core.Version, core.DataSchema, dataSchema));

        // Пара, которая не поздоровается, не стоит закачки.
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
    /// Достать метаданные из релиза.
    /// </summary>
    /// <remarks>
    /// Ищется актив с именем <c>manifest.json</c>. Его отсутствие — не
    /// «обновлений нет», а «источник говорит не то, что мы понимаем», и
    /// разница важна: первое успокаивает, второе требует внимания.
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
    /// Скачать часть и проверить хэш.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>Хэш считается по дороге, а не потом.</b> Второе чтение файла с
    /// диска ради проверки стоит времени и позволяет подменить файл между
    /// записью и проверкой.
    /// </para>
    /// <para>
    /// <b>Несовпадение — не «повреждён», а «не тот файл».</b> Он удаляется
    /// целиком: половина обновления, оставшаяся на диске, однажды
    /// окажется установленной.
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
            // Оборвалась закачка — файла быть не должно: недокачанное,
            // оставшееся на диске, однажды окажется установленным.
            try { if (File.Exists(target)) File.Delete(target); } catch { }
            Platform.Journal.Update("download",
                $"part={part.Name} version={part.Version} "
                + $"result=fail note={error.GetType().Name}");
            return (false, "", error.Message);
        }
    }

    /// <summary>
    /// Только HTTPS.
    /// </summary>
    /// <remarks>
    /// Обновление по открытому каналу — это приглашение подменить его по
    /// дороге. Хэш из тех же метаданных от этого не спасает: подменивший
    /// ответ подменит и хэш.
    /// </remarks>
    private static string Https(string url)
    {
        if (!url.StartsWith("https://", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException(
                S("источник обновлений обязан быть https, а это «{0}»", url));
        return url;
    }
}
