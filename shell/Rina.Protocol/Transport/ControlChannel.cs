using System.Buffers.Binary;
using System.IO.Pipes;

namespace Rina.Protocol.Transport;

/// <summary>Та сторона закрылась.</summary>
public sealed class ChannelClosedException(string message) : Exception(message);

/// <summary>
/// Кадрирование управляющего канала: длина, затем полезная нагрузка (§2).
/// </summary>
/// <remarks>
/// <b>Предел проверяется по заявленной длине, до выделения памяти.</b> Иначе
/// он не защищает ни от чего: сторона, объявившая кадр в четыре гигабайта,
/// добьётся своего ровно тем, что мы честно дождёмся его целиком.
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
                $"сообщение {body.Length} Б больше предела {ControlFrameLimit} Б");

        var frame = new byte[4 + body.Length];
        BinaryPrimitives.WriteUInt32BigEndian(frame, (uint)body.Length);
        body.CopyTo(frame, 4);
        return frame;
    }
}

/// <summary>
/// Управляющий канал: именованная труба, которую держит оболочка.
/// </summary>
/// <remarks>
/// <para>
/// <b>Сервером выступает оболочка, ядро подключается клиентом</b> — это
/// решение ADR 0002. Инверсия привычной раскладки снимает зависимость с
/// Python-стороны (там клиент это обычный <c>open()</c>) и совпадает с тем,
/// что оболочка и так запускает ядро и следит за ним.
/// </para>
/// <para>
/// <b>Права доступа — незакрытый долг.</b> ADR 0002 выбрал именованный канал
/// именно потому, что у него есть дескриптор безопасности, и обещал ограничить
/// доступ пользователем сессии. Здесь труба создаётся с умолчаниями: это
/// делается до выпуска, задача <c>4.0-G07</c>, и пока оболочка не выпущена,
/// долг виден — а не забыт.
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

    /// <summary>Дождаться, пока ядро подключится.</summary>
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
    /// Прочитать следующее сообщение.
    /// </summary>
    /// <remarks>
    /// Пустое чтение из трубы означает закрытие, и об этом говорит исключение,
    /// а не пустой результат: «сейчас ничего нет» и «всё кончилось» — разные
    /// вещи, и вызывающий, который их путает, крутит пустой цикл вместо
    /// завершения.
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
                throw new ChannelClosedException("ядро закрыло канал");

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
                $"объявленный размер кадра {size} Б больше предела");

        if (_pending.Count < 4 + size) return false;

        frame = _pending.GetRange(4, (int)size).ToArray();
        _pending.RemoveRange(0, 4 + (int)size);
        return true;
    }

    private static ReadOnlySpan<byte> CollectionsMarshalSpan(List<byte> list, int count)
        => System.Runtime.InteropServices.CollectionsMarshal.AsSpan(list)[..count];

    public void Dispose()
    {
        try { if (_pipe.IsConnected) _pipe.Disconnect(); } catch { /* уже нет */ }
        _pipe.Dispose();
    }
}
