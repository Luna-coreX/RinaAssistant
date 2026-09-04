using System.Buffers.Binary;
using System.IO.Pipes;

namespace Rina.Protocol.Transport;

/// <summary>A data-channel frame (§2).</summary>
/// <param name="StreamId">Which stream it belongs to.</param>
/// <param name="Seq">Sequence number within the stream.</param>
/// <param name="Payload">The bytes.</param>
public readonly record struct DataFrame(int StreamId, long Seq, byte[] Payload);

/// <summary>
/// The data channel: audio and screen frames, bypassing JSON.
/// </summary>
/// <remarks>
/// <para>
/// A separate pipe, not a field in a message. Base64 inside JSON inflates
/// the volume by a third, but volume is not the point: encoded audio would
/// queue up behind commands, and a button press would wait for a second of
/// speech to go by. Measured in <c>4.0-D07</c>: 301,968 bytes against 166
/// before the command.
/// </para>
/// <para>
/// The frame header is binary and short: length of the remainder, stream
/// number, sequence number. The sequence number exists to spot losses while
/// debugging — without it a missing chunk of audio looks like "Rina misheard
/// part of it", and the cause gets hunted in recognition rather than in the
/// channel.
/// </para>
/// </remarks>
public sealed class DataChannel : IDisposable
{
    /// <summary>The limit for one frame (§2). Smaller than the control one on purpose.</summary>
    public const int FrameLimit = 256 * 1024;

    private readonly NamedPipeServerStream _pipe;
    private readonly byte[] _buffer = new byte[64 * 1024];
    private readonly List<byte> _pending = [];
    private readonly SemaphoreSlim _writing = new(1, 1);
    private readonly Dictionary<int, long> _seq = [];

    public string PipeName { get; }

    public DataChannel(string session)
    {
        PipeName = $"rina.{session}.data";
        _pipe = new NamedPipeServerStream(
            PipeName, PipeDirection.InOut, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous);
    }

    public Task AcceptAsync(CancellationToken token = default) =>
        _pipe.WaitForConnectionAsync(token);

    public bool Connected => _pipe.IsConnected;

    public async Task SendAsync(int streamId, ReadOnlyMemory<byte> payload,
                                CancellationToken token = default)
    {
        if (payload.Length + 12 > FrameLimit)
            throw new ProtocolException(ErrorCodes.ProtocolFrameTooLarge,
                $"a {payload.Length} B data frame exceeds the {FrameLimit} B limit");

        await _writing.WaitAsync(token).ConfigureAwait(false);
        try
        {
            _seq.TryGetValue(streamId, out var seq);
            _seq[streamId] = ++seq;

            var frame = new byte[16 + payload.Length];
            BinaryPrimitives.WriteUInt32BigEndian(frame, (uint)(12 + payload.Length));
            BinaryPrimitives.WriteUInt32BigEndian(frame.AsSpan(4), (uint)streamId);
            BinaryPrimitives.WriteInt64BigEndian(frame.AsSpan(8), seq);
            payload.Span.CopyTo(frame.AsSpan(16));

            await _pipe.WriteAsync(frame, token).ConfigureAwait(false);
            await _pipe.FlushAsync(token).ConfigureAwait(false);
        }
        catch (IOException e) { throw new ChannelClosedException(e.Message); }
        finally { _writing.Release(); }
    }

    /// <summary>Forget a stream's numbering: the next stream with that id starts at one.</summary>
    public void Forget(int streamId) => _seq.Remove(streamId);

    public async Task<DataFrame> ReceiveAsync(CancellationToken token = default)
    {
        while (true)
        {
            if (TryTake(out var frame)) return frame;

            int read;
            try
            {
                read = await _pipe.ReadAsync(_buffer, token).ConfigureAwait(false);
            }
            catch (IOException e) { throw new ChannelClosedException(e.Message); }

            if (read == 0) throw new ChannelClosedException("the core closed the data channel");
            _pending.AddRange(_buffer.AsSpan(0, read).ToArray());
        }
    }

    private bool TryTake(out DataFrame frame)
    {
        frame = default;
        if (_pending.Count < 4) return false;

        var span = System.Runtime.InteropServices.CollectionsMarshal.AsSpan(_pending);
        var size = BinaryPrimitives.ReadUInt32BigEndian(span[..4]);
        // The limit is checked against the declared length, before any
        // memory is allocated: otherwise it protects against nothing.
        if (size > FrameLimit)
            throw new ProtocolException(ErrorCodes.ProtocolFrameTooLarge,
                $"the declared data frame size of {size} B exceeds the limit");
        if (size < 12)
            throw new ProtocolException(ErrorCodes.ProtocolInvalidPayload,
                "the data frame is shorter than its own header");
        if (_pending.Count < 4 + size) return false;

        var body = span.Slice(4, (int)size);
        var streamId = (int)BinaryPrimitives.ReadUInt32BigEndian(body[..4]);
        var seq = BinaryPrimitives.ReadInt64BigEndian(body.Slice(4, 8));
        frame = new DataFrame(streamId, seq, body[12..].ToArray());
        _pending.RemoveRange(0, 4 + (int)size);
        return true;
    }

    public void Dispose()
    {
        try { if (_pipe.IsConnected) _pipe.Disconnect(); } catch { /* уже нет */ }
        _pipe.Dispose();
        _writing.Dispose();
    }
}
