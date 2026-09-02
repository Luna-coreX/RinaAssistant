using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Rina.Protocol;

/// <summary>Тип сообщения управляющего канала (§3).</summary>
public static class MessageType
{
    public const string Request = "request";
    public const string Response = "response";
    public const string Event = "event";
    public const string Error = "error";
}

/// <summary>
/// Конверт: поля, которые есть на каждом сообщении без исключений (§3).
/// </summary>
/// <remarks>
/// <para>
/// <b>Незнакомые поля конверта пропускаются молча.</b> Правила совместимости
/// (§4) разрешают добавить необязательное поле, не меняя версию протокола;
/// получатель, спотыкающийся о такое поле, превращает это разрешение в ложь и
/// делает ступенчатое обновление невозможным. <c>System.Text.Json</c> ведёт
/// себя так по умолчанию, и это тот случай, когда умолчание верное.
/// </para>
/// <para>
/// Нагрузка держится как <see cref="JsonNode"/>, а не разбирается в типы: у
/// каждого метода она своя, а конверт обязан оставаться одним на всех.
/// Разбор нагрузки — дело того, кто знает метод.
/// </para>
/// </remarks>
public sealed record Envelope
{
    [JsonPropertyName("v")] public int Version { get; init; } = ProtocolVersion.Current;
    [JsonPropertyName("type")] public string Type { get; init; } = MessageType.Request;
    [JsonPropertyName("id")] public string Id { get; init; } = "";
    [JsonPropertyName("method")] public string? Method { get; init; }
    [JsonPropertyName("correlation_id")] public string? CorrelationId { get; init; }
    [JsonPropertyName("stream_id")] public int? StreamId { get; init; }
    [JsonPropertyName("timestamp")] public double Timestamp { get; init; }
    [JsonPropertyName("trace_id")] public string TraceId { get; init; } = "";
    [JsonPropertyName("payload")] public JsonObject Payload { get; init; } = new();

    public bool IsError => Type == MessageType.Error;
    public bool IsEvent => Type == MessageType.Event;

    /// <summary>Код ошибки, если это ошибка; иначе пусто.</summary>
    public string ErrorCode =>
        IsError ? Payload["code"]?.GetValue<string>() ?? "" : "";

    /// <summary>Человеческий текст ошибки (§5: код и текст разделены).</summary>
    public string ErrorMessage =>
        IsError ? Payload["message"]?.GetValue<string>() ?? "" : "";

    public static Envelope Request(string method, JsonObject? payload,
                                   string id, string traceId) => new()
    {
        Type = MessageType.Request,
        Id = id,
        Method = method,
        TraceId = traceId,
        Timestamp = Clock.Now(),
        Payload = payload ?? new JsonObject(),
    };

    private static readonly JsonSerializerOptions Options = new()
    {
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false,
    };

    public byte[] Encode() =>
        System.Text.Encoding.UTF8.GetBytes(JsonSerializer.Serialize(this, Options));

    public static Envelope Decode(ReadOnlySpan<byte> raw)
    {
        var text = System.Text.Encoding.UTF8.GetString(raw);
        var envelope = JsonSerializer.Deserialize<Envelope>(text, Options)
            ?? throw new ProtocolException(ErrorCodes.ProtocolInvalidEnvelope,
                                           "сообщение обязано быть объектом");
        envelope.RequireComplete();
        return envelope;
    }

    /// <summary>
    /// Проверить, что конверт полон (§15.1).
    /// </summary>
    /// <remarks>
    /// Проверяется у получателя, хотя отправитель уже проверил у себя. Это не
    /// недоверие к ядру: сообщение могло прийти от другой его версии, и
    /// «отсутствие обязательного поля — протокольная ошибка» есть требование
    /// спецификации, а не пожелание.
    /// </remarks>
    public void RequireComplete()
    {
        var missing = new List<string>();
        if (Version < 1) missing.Add("v");
        if (string.IsNullOrEmpty(Type)) missing.Add("type");
        if (string.IsNullOrEmpty(Id)) missing.Add("id");
        if (Timestamp <= 0) missing.Add("timestamp");
        if (string.IsNullOrEmpty(TraceId)) missing.Add("trace_id");

        if (Type is MessageType.Request or MessageType.Event
            && string.IsNullOrEmpty(Method))
            missing.Add("method");
        if (Type is MessageType.Response or MessageType.Error
            && string.IsNullOrEmpty(CorrelationId))
            missing.Add("correlation_id");

        if (missing.Count > 0)
            throw new ProtocolException(
                ErrorCodes.ProtocolInvalidEnvelope,
                "в конверте нет обязательных полей: " + string.Join(", ", missing));
    }
}

/// <summary>Время в том виде, в каком его понимает протокол: секунды с эпохи.</summary>
public static class Clock
{
    public static double Now() =>
        DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
}

/// <summary>
/// Идентификаторы сообщений, уникальные в пределах сессии.
/// </summary>
/// <remarks>
/// Префикс называет сторону (<c>s-</c> оболочка), чтобы в общем журнале двух
/// процессов было видно отправителя без обращения к содержимому. Счётчик, а
/// не случайность: пропуск номера виден глазом.
/// </remarks>
public sealed class IdGenerator(string prefix)
{
    private int _n;
    public string Next() => $"{prefix}{Interlocked.Increment(ref _n):D4}";
}

/// <summary>Начало цепочки трассировки (§14).</summary>
public static class Trace
{
    public static string New() => "t-" + Guid.NewGuid().ToString("N")[..12];
}

/// <summary>Нарушение протокола, замеченное оболочкой.</summary>
public sealed class ProtocolException(string code, string message)
    : Exception($"{code}: {message}")
{
    public string Code { get; } = code;
    public string Reason { get; } = message;
}
