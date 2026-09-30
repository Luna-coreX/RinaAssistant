using System.Net;
using System.Net.Http;

namespace Rina.Shell.Update;

/// <summary>
/// An update source that answers with whatever it was told to.
/// </summary>
/// <remarks>
/// <para>
/// The checks need it. Updates cannot be verified against the real
/// GitHub: what is there today is not there tomorrow, and a check that
/// depends on someone else's release goes red for reasons unrelated to
/// the code. And there are exactly six outcomes to verify, five of which
/// cannot be reproduced against a live source at all.
/// </para>
/// <para>
/// It lives next to the client rather than in the check: what is being
/// substituted is the client's <b>input</b>, and the substitute has to
/// speak the same language as the real source. Sitting in a check file it
/// would have to restate the shape of GitHub's answer — a second time and
/// with discrepancies.
/// </para>
/// </remarks>
public sealed class Fake : HttpMessageHandler
{
    private readonly Dictionary<string, (string Body, byte[]? Bytes)> _answers
        = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>How many times it was asked — the checks look at this too.</summary>
    public int Asked { get; private set; }

    public Fake Says(string url, string body)
    {
        _answers[url] = (body, null);
        return this;
    }

    public Fake Gives(string url, byte[] bytes)
    {
        _answers[url] = ("", bytes);
        return this;
    }

    /// <summary>A GitHub release answer with one asset.</summary>
    public static string Release(string manifestUrl) =>
        "{\"assets\": [{\"name\": \"manifest.json\", "
        + $"\"browser_download_url\": \"{manifestUrl}\"}}]}}";

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request, CancellationToken token)
    {
        Asked++;
        var url = request.RequestUri?.ToString() ?? "";
        if (!_answers.TryGetValue(url, out var answer))
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.NotFound));

        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = answer.Bytes is not null
                ? new ByteArrayContent(answer.Bytes)
                : new StringContent(answer.Body),
        });
    }
}
