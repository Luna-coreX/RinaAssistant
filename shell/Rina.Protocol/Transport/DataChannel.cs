using System.Buffers.Binary;
using System.IO.Pipes;

namespace Rina.Protocol.Transport;

/// <summary>Кадр канала данных (§2).</summary>
/// <param name="StreamId">К какому потоку относится.</param>
/// <param name="Seq">Порядковый номер в пределах потока.</param>
/// <param name="Payload">Байты.</param>
public readonly record struct DataFrame(int StreamId, long Seq, byte[] Payload);

/// <summary>
/// Канал данных: звук и кадры экрана, мимо JSON.
/// </summary>
/// <remarks>
/// <para>
/// Отдельная труба, а не поле в сообщении. Base64 внутри JSON раздувает
/// объём на треть, но дело не в объёме: закодированный звук встал бы в одну
/// очередь с командами, и нажатие кнопки ждало бы, пока проедет секунда речи.
/// Измерено в <c>4.0-D07</c>: 301 968 байт против 166 до команды.
/// </para>
/// <para>
/// Заголовок кадра двоичный и короткий: длина остатка, номер потока,
/// порядковый номер. Номер нужен для обнаружения потерь при отладке — без
/// него пропавший кусок звука выглядит как «Рина расслышала не всё», и
/// причину ищут в распознавании, а не в канале.
/// </para>
/// </remarks>
public sealed class DataChannel : IDisposable
{
    /// <summary>Предел одного кадра (§2). Меньше управляющего намеренно.</summary>
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
                $"кадр данных {payload.Length} Б больше предела {FrameLimit} Б");

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

    /// <summary>Забыть номера потока: следующий с тем же номером начнёт с единицы.</summary>
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

            if (read == 0) throw new ChannelClosedException("ядро закрыло канал данных");
            _pending.AddRange(_buffer.AsSpan(0, read).ToArray());
        }
    }

    private bool TryTake(out DataFrame frame)
    {
        frame = default;
        if (_pending.Count < 4) return false;

        var span = System.Runtime.InteropServices.CollectionsMarshal.AsSpan(_pending);
        var size = BinaryPrimitives.ReadUInt32BigEndian(span[..4]);
        // Предел по заявленной длине, до выделения памяти: иначе он не
        // защищает ни от чего.
        if (size > FrameLimit)
            throw new ProtocolException(ErrorCodes.ProtocolFrameTooLarge,
                $"объявленный размер кадра данных {size} Б больше предела");
        if (size < 12)
            throw new ProtocolException(ErrorCodes.ProtocolInvalidPayload,
                "кадр данных короче собственного заголовка");
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
