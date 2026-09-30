using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;

namespace Rina.Protocol;

/// <summary>Control-channel message type (§3).</summary>
public static class MessageType
{
    public const string Request = "request";
    public const string Response = "response";
    public const string Event = "event";
    public const string Error = "error";
}

/// <summary>
/// The envelope: the fields present on every message without exception (§3).
/// </summary>
/// <remarks>
/// <para>
/// <b>Unknown envelope fields are skipped in silence.</b> The compatibility
/// rules (§4) permit adding an optional field without changing the protocol
/// version; a receiver that trips over such a field turns that permission
/// into a lie and makes staged updates impossible.
/// <c>System.Text.Json</c> behaves this way by default, and this is the case
/// where the default is the right one.
/// </para>
/// <para>
/// The payload is held as a <see cref="JsonNode"/> rather than parsed into
/// types: every method has its own, and the envelope has to stay one and the
/// same for all of them. Parsing the payload is the business of whoever knows
/// the method.
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

    /// <summary>The error code, if this is an error; empty otherwise.</summary>
    public string ErrorCode =>
        IsError ? Payload["code"]?.GetValue<string>() ?? "" : "";

    /// <summary>Human text of the error (§5: code and text are separate).</summary>
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
                                           "a message must be an object");
        envelope.RequireComplete();
        return envelope;
    }

    /// <summary>
    /// Check that the envelope is complete (§15.1).
    /// </summary>
    /// <remarks>
    /// Checked at the receiver even though the sender already checked at
    /// home. This is not distrust of the core: the message could have come
    /// from a different version of it, and "a missing mandatory field is a
    /// protocol error" is a requirement of the specification, not a wish.
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
                "the envelope is missing mandatory fields: " + string.Join(", ", missing));
    }
}

/// <summary>Time as the protocol understands it: seconds since the epoch.</summary>
public static class Clock
{
    public static double Now() =>
        DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
}

/// <summary>
/// Message identifiers, unique within a session.
/// </summary>
/// <remarks>
/// The prefix names the side (<c>s-</c> for the shell) so that a shared log
/// of two processes shows the sender without looking at the contents. A
/// counter rather than randomness: a skipped number is visible to the eye.
/// </remarks>
public sealed class IdGenerator(string prefix)
{
    private int _n;
    public string Next() => $"{prefix}{Interlocked.Increment(ref _n):D4}";
}

/// <summary>The start of a trace chain (§14).</summary>
public static class Trace
{
    public static string New() => "t-" + Guid.NewGuid().ToString("N")[..12];
}

/// <summary>A protocol violation noticed by the shell.</summary>
public sealed class ProtocolException(string code, string message)
    : Exception($"{code}: {message}")
{
    public string Code { get; } = code;
    public string Reason { get; } = message;
}
