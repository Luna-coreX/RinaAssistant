using System.Buffers.Binary;
using System.IO.Pipes;

namespace Rina.Protocol.Transport;

/// <summary>The other side has closed.</summary>
public sealed class ChannelClosedException(string message) : Exception(message);

/// <summary>
/// Control-channel framing: length, then payload (§2).
/// </summary>
/// <remarks>
/// <b>The limit is checked against the declared length, before any memory is
/// allocated.</b> Otherwise it protects against nothing: a side that declares
/// a four-gigabyte frame gets exactly what it wanted the moment we honestly
/// wait for all of it.
/// </remarks>
public static class Framing
{
    public const int ControlFrameLimit = 1024 * 1024;

    public static byte[] Encode(Envelope envelope)
    {
        var body = envelope.Encode();
        if (body.Length > ControlFrameLimit)
            throw new ProtocolException(
                ErrorCodes.ProtocolFrameTooLarge,
                $"a {body.Length} B message exceeds the {ControlFrameLimit} B limit");

        var frame = new byte[4 + body.Length];
        BinaryPrimitives.WriteUInt32BigEndian(frame, (uint)body.Length);
        body.CopyTo(frame, 4);
        return frame;
    }
}

/// <summary>
/// The control channel: a named pipe held by the shell.
/// </summary>
/// <remarks>
/// <para>
/// <b>The shell is the server and the core connects as a client</b> — that is
/// the ADR 0002 decision. Inverting the usual arrangement takes the
/// dependency off the Python side (a client there is a plain <c>open()</c>)
/// and matches the fact that the shell starts the core and supervises it
/// anyway.
/// </para>
/// <para>
/// <b>Access rights are an open debt.</b> ADR 0002 chose a named pipe
/// precisely because it has a security descriptor, and promised to restrict
/// access to the session's user. Here the pipe is created with defaults: that
/// is to be done before release, plan item <c>4.0-G07</c>, and while the
/// shell is unreleased the debt is visible — not forgotten.
/// </para>
/// </remarks>
public sealed class ControlChannel : IDisposable
{
    private readonly NamedPipeServerStream _pipe;
    private readonly byte[] _buffer = new byte[64 * 1024];
    private readonly List<byte> _pending = [];

    public string PipeName { get; }

    public ControlChannel(string session, string channel = "control")
    {
        PipeName = $"rina.{session}.{channel}";
        _pipe = new NamedPipeServerStream(
            PipeName, PipeDirection.InOut, 1,
            PipeTransmissionMode.Byte, PipeOptions.Asynchronous);
    }

    /// <summary>Wait for the core to connect.</summary>
    public async Task AcceptAsync(CancellationToken token = default) =>
        await _pipe.WaitForConnectionAsync(token).ConfigureAwait(false);

    public bool Connected => _pipe.IsConnected;

    public async Task SendAsync(Envelope envelope, CancellationToken token = default)
    {
        var frame = Framing.Encode(envelope);
        try
        {
            await _pipe.WriteAsync(frame, token).ConfigureAwait(false);
            await _pipe.FlushAsync(token).ConfigureAwait(false);
        }
        catch (IOException e)
        {
            throw new ChannelClosedException(e.Message);
        }
    }

    /// <summary>
    /// Read the next message.
    /// </summary>
    /// <remarks>
    /// An empty read from the pipe means closure, and that is reported by an
    /// exception rather than an empty result: "there is nothing right now"
    /// and "it is all over" are different things, and a caller that confuses
    /// them spins an empty loop instead of finishing.
    /// </remarks>
    public async Task<Envelope> ReceiveAsync(CancellationToken token = default)
    {
        while (true)
        {
            if (TryTakeFrame(out var frame))
                return Envelope.Decode(frame);

            int read;
            try
            {
                read = await _pipe.ReadAsync(_buffer, token).ConfigureAwait(false);
            }
            catch (IOException e)
            {
                throw new ChannelClosedException(e.Message);
            }

            if (read == 0)
                throw new ChannelClosedException("the core closed the channel");

            _pending.AddRange(_buffer.AsSpan(0, read).ToArray());
        }
    }

    private bool TryTakeFrame(out byte[] frame)
    {
        frame = [];
        if (_pending.Count < 4) return false;

        var size = BinaryPrimitives.ReadUInt32BigEndian(
            CollectionsMarshalSpan(_pending, 4));
        if (size > Framing.ControlFrameLimit)
            throw new ProtocolException(
                ErrorCodes.ProtocolFrameTooLarge,
                $"the declared frame size of {size} B exceeds the limit");

        if (_pending.Count < 4 + size) return false;

        frame = _pending.GetRange(4, (int)size).ToArray();
        _pending.RemoveRange(0, 4 + (int)size);
        return true;
    }

    private static ReadOnlySpan<byte> CollectionsMarshalSpan(List<byte> list, int count)
        => System.Runtime.InteropServices.CollectionsMarshal.AsSpan(list)[..count];

    public void Dispose()
    {
        try { if (_pipe.IsConnected) _pipe.Disconnect(); } catch { /* already gone */ }
        _pipe.Dispose();
    }
}
