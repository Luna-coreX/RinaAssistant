using System.Text.Json.Nodes;
using Rina.Protocol;
using Rina.Protocol.Transport;

namespace Rina.Shell.Audio;

/// <summary>
/// Звук между микрофоном, ядром и динамиком.
/// </summary>
/// <remarks>
/// <para>
/// Задачи плана <c>4.0-F09</c> и <c>4.0-F10</c>: захват в ядро и
/// воспроизведение из ядра, оба по каналу данных с обратным давлением.
/// </para>
/// <para>
/// <b>Кредит соблюдается, а не подразумевается.</b> Приёмник объявляет,
/// сколько байт готов принять; отправитель не имеет права держать в полёте
/// больше. Микрофон — источник, который не умеет ждать: он выдаёт по куску
/// каждые сто миллисекунд независимо от того, успевает ли ядро. Без кредита
/// очередь росла бы молча, и отказ выглядел бы как «программа съела
/// гигабайт».
/// </para>
/// <para>
/// <b>Что делать с куском, на который нет кредита.</b> Он отбрасывается, а
/// не копится. Для звука это верно: устаревший кусок речи никому не нужен,
/// и лучше потерять сто миллисекунд, чем отстать на секунду и распознавать
/// вчерашнее. Отброшенное считается — молча терять нельзя.
/// </para>
/// <para>
/// <b>Рина не слушает себя.</b> Пока идёт воспроизведение, захват заглушен.
/// Иначе синтезированная речь попадёт в микрофон, распознается как команда,
/// и Рина ответит сама себе — в 3.1.0 от этого спасал счётчик говорящих, и
/// причина никуда не делась.
/// </para>
/// </remarks>
public sealed class AudioLink : IDisposable
{
    private const string InputKind = "audio.input";
    private const string OutputKind = "audio.output";

    private readonly CoreConnection _connection;
    private readonly DataChannel _data;
    private readonly Microphone _microphone;
    private readonly Speaker _speaker;

    private int _inputStream;
    private long _credit;
    private CancellationTokenSource? _reading;

    /// <summary>Сколько байт отброшено из-за нехватки кредита.</summary>
    public long Dropped { get; private set; }

    /// <summary>Сколько байт ушло в ядро.</summary>
    public long Sent { get; private set; }

    /// <summary>Уровень микрофона 0..1 — для полосы прибора.</summary>
    public event Action<float>? Level;

    public AudioLink(CoreConnection connection, DataChannel data,
                     Microphone microphone, Speaker speaker)
    {
        _connection = connection;
        _data = data;
        _microphone = microphone;
        _speaker = speaker;

        _microphone.Captured += OnCaptured;
        _microphone.Level += level => Level?.Invoke(level);
        _speaker.Speaking += speaking => _microphone.Muted = speaking;
        _connection.EventReceived += OnEvent;
    }

    /// <summary>
    /// Открыть поток звука в ядро.
    /// </summary>
    /// <param name="listen">
    /// Включать ли устройство. Открыть поток и начать слушать — разные
    /// действия: звук может прийти из файла при проверке голоса, и тогда
    /// микрофон не нужен вовсе.
    /// </param>
    /// <summary>
    /// Какими устройствами пользоваться. Имена — из настроек ядра.
    /// </summary>
    /// <remarks>
    /// Ядро хранит выбор, но самих устройств не видит: звук в 4.0
    /// принадлежит оболочке (<c>4.0-F09</c>). Поэтому имя разрешается здесь,
    /// и «default» — не имя, а признак «не выбирали».
    /// </remarks>
    public void UseDevices(string input, string output)
    {
        _inputDevice = input is "default" or "" ? 0 : Microphone.IndexOf(input);
        _speaker.Device = output is "default" or "" ? 0 : Speaker.IndexOf(output);
    }

    private int _inputDevice;

    /// <param name="deviceIndex">
    /// Номер устройства; <c>-1</c> — то, что выбрано в настройках.
    /// </param>
    public async Task<bool> StartCaptureAsync(int deviceIndex = -1,
                                              bool listen = true)
    {
        if (!_connection.MayCall(Methods.StreamOpen)) return false;

        _inputStream = 11;
        _credit = 0;
        Dropped = Sent = 0;

        var answer = await _connection.CallAsync(Methods.StreamOpen, new JsonObject
        {
            ["stream_id"] = _inputStream,
            ["kind"] = InputKind,
            ["format"] = new JsonObject
            {
                ["encoding"] = "pcm_s16le",
                ["rate"] = Microphone.SampleRate,
                ["channels"] = Microphone.Channels,
            },
        }, TimeSpan.FromSeconds(10));
        if (answer.IsError) return false;

        // Первый кредит ядро выдаёт вместе с согласием открыть поток.
        Interlocked.Add(ref _credit,
                        answer.Payload["credit"]?.GetValue<int>() ?? 0);

        _reading = new CancellationTokenSource();
        _ = Task.Run(() => ReadAsync(_reading.Token));
        if (listen)
            _microphone.Start(deviceIndex < 0 ? _inputDevice : deviceIndex);
        return true;
    }

    public async Task StopCaptureAsync()
    {
        _microphone.Stop();
        if (_inputStream == 0) return;

        var closing = _inputStream;
        _inputStream = 0;
        try
        {
            await _connection.CallAsync(Methods.StreamClose, new JsonObject
            {
                ["stream_id"] = closing,
            }, TimeSpan.FromSeconds(5));
        }
        catch { /* ядро могло уйти раньше */ }
        _data.Forget(closing);
    }

    private void OnCaptured(byte[] chunk) => Push(chunk);

    /// <summary>
    /// Отправить кусок звука в ядро. <c>false</c> — не хватило кредита.
    /// </summary>
    /// <remarks>
    /// Открыт наружу, а не только для микрофона: звук приходит и не с
    /// устройства — из файла при проверке голоса, из записи при разборе
    /// жалобы. Путь при этом обязан быть тот же самый, иначе проверяется
    /// не он.
    /// </remarks>
    public bool Push(ReadOnlySpan<byte> chunk)
    {
        var stream = _inputStream;
        if (stream == 0) return false;

        // Кредит проверяется до отправки, а не после: «уже отправил,
        // извините» — не обратное давление, а его изображение.
        if (Interlocked.Read(ref _credit) < chunk.Length)
        {
            Dropped += chunk.Length;
            return false;
        }
        Interlocked.Add(ref _credit, -chunk.Length);
        Sent += chunk.Length;
        _ = _data.SendAsync(stream, chunk.ToArray());
        return true;
    }

    /// <summary>Сколько байт разрешено отправить прямо сейчас.</summary>
    public long Credit => Interlocked.Read(ref _credit);

    private void OnEvent(Envelope message)
    {
        if (message.Method != "stream.credit") return;
        if (message.StreamId != _inputStream) return;
        Interlocked.Add(ref _credit,
                        message.Payload["bytes"]?.GetValue<int>() ?? 0);
    }

    /// <summary>Слушать канал данных: оттуда приходит синтезированная речь.</summary>
    private async Task ReadAsync(CancellationToken token)
    {
        try
        {
            while (!token.IsCancellationRequested)
            {
                var frame = await _data.ReceiveAsync(token).ConfigureAwait(false);
                _speaker.Enqueue(frame.Payload);
                // Кредит возвращается по мере воспроизведения, а не приёма:
                // иначе ядро набьёт нам очередь на минуту вперёд, и «стоп»
                // перестанет быть мгновенным.
                await _connection.CallAsync(Methods.StreamCredit, new JsonObject
                {
                    ["stream_id"] = frame.StreamId,
                    ["bytes"] = frame.Payload.Length,
                }, TimeSpan.FromSeconds(5)).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) { /* закрываемся */ }
        catch (ChannelClosedException) { /* ядро ушло */ }
    }

    /// <summary>Оборвать речь: «стоп» обязан быть мгновенным.</summary>
    public void Interrupt() => _speaker.Interrupt();

    public void Dispose()
    {
        _reading?.Cancel();
        _connection.EventReceived -= OnEvent;
        _microphone.Captured -= OnCaptured;
        _microphone.Dispose();
        _speaker.Dispose();
        _reading?.Dispose();
    }
}
