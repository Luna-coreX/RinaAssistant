using System.Net;
using System.Net.Http;

namespace Rina.Shell.Update;

/// <summary>
/// Источник обновлений, отвечающий заранее заданным.
/// </summary>
/// <remarks>
/// <para>
/// Нужен проверке. Обновления нельзя проверить на настоящем GitHub: там
/// сегодня одно, завтра другое, и проверка, зависящая от чужого релиза,
/// краснеет по причинам, к коду не относящимся. А проверить надо ровно
/// шесть исходов, из которых пять на живом источнике не воспроизвести.
/// </para>
/// <para>
/// Живёт рядом с клиентом, а не в проверке: подменяется <b>вход</b>
/// клиента, и подмена обязана говорить на том же языке, что настоящий
/// источник. Стой она в файле проверки, ей пришлось бы повторять форму
/// ответа GitHub — второй раз и с расхождениями.
/// </para>
/// </remarks>
public sealed class Fake : HttpMessageHandler
{
    private readonly Dictionary<string, (string Body, byte[]? Bytes)> _answers
        = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>Сколько раз спрашивали — проверка смотрит и на это.</summary>
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

    /// <summary>Ответ релиза GitHub с одним активом.</summary>
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
