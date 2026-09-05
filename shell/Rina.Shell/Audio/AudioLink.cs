using System.Text.Json.Nodes;
using Rina.Protocol;
using Rina.Protocol.Transport;

namespace Rina.Shell.Audio;

/// <summary>
/// Sound between the microphone, the core and the speaker.
/// </summary>
/// <remarks>
/// <para>
/// Plan items <c>4.0-F09</c> and <c>4.0-F10</c>: capture into the core and
/// playback out of the core, both over the data channel with
/// backpressure.
/// </para>
/// <para>
/// <b>The credit is honoured, not assumed.</b> The receiver announces how
/// many bytes it is ready to take; the sender has no right to keep more
/// than that in flight. The microphone is a source that cannot wait: it
/// gives out a chunk every hundred milliseconds regardless of whether the
/// core keeps up. Without credit the queue would grow in silence, and the
/// failure would look like "the program ate a gigabyte".
/// </para>
/// <para>
/// <b>What to do with a chunk there is no credit for.</b> It is dropped,
/// not accumulated. For sound that is right: a stale chunk of speech is of
/// no use to anyone, and it is better to lose a hundred milliseconds than
/// to fall a second behind and recognise yesterday's words. What is
/// dropped is counted — losing it in silence is not allowed.
/// </para>
/// <para>
/// <b>Rina does not listen to herself.</b> While playback is going on,
/// capture is muted. Otherwise synthesised speech reaches the microphone,
/// is recognised as a command, and Rina answers herself — in 3.1.0 a
/// counter of speakers saved us from this, and the reason has not gone
/// anywhere.
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

    /// <summary>How many bytes were dropped for want of credit.</summary>
    public long Dropped { get; private set; }

    /// <summary>How many bytes went to the core.</summary>
    public long Sent { get; private set; }

    /// <summary>How many bytes of speech were received from the core.</summary>
    public long Received { get; private set; }

    /// <summary>How much of what was received is not yet played.</summary>
    public int Pending => _speaker.Pending;

    /// <summary>The microphone level, 0..1 — for the instrument strip.</summary>
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
    /// Which devices to use. The names come from the core's settings.
    /// </summary>
    /// <remarks>
    /// The core stores the choice but does not see the devices themselves:
    /// sound in 4.0 belongs to the shell (<c>4.0-F09</c>). So the name is
    /// resolved here, and "default" is not a name but a mark meaning "not
    /// chosen".
    /// </remarks>
    public void UseDevices(string input, string output)
    {
        _inputDevice = input is "default" or "" ? 0 : Microphone.IndexOf(input);
        _speaker.Device = output is "default" or "" ? 0 : Speaker.IndexOf(output);
    }

    private int _inputDevice;

    /// <summary>
    /// Open a stream of sound into the core.
    /// </summary>
    /// <param name="deviceIndex">
    /// The device number; <c>-1</c> means whatever is chosen in settings.
    /// </param>
    /// <param name="listen">
    /// Whether to switch the device on. Opening a stream and starting to
    /// listen are different actions: sound may come from a file during a
    /// voice check, and then the microphone is not needed at all.
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

        // The core issues the first credit together with its consent to open the stream.
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
    /// Send a chunk of sound to the core. <c>false</c> — not enough credit.
    /// </summary>
    /// <remarks>
    /// Open to the outside rather than only to the microphone: sound comes
    /// from places other than a device — from a file during a voice check,
    /// from a recording while a complaint is being looked into. The path
    /// must be the same one, or it is not the path being checked.
    /// </remarks>
    public bool Push(ReadOnlySpan<byte> chunk)
    {
        var stream = _inputStream;
        if (stream == 0) return false;

        // The credit is checked before sending, not after: "already sent,
        // sorry" is not backpressure but an impression of it.
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

    /// <summary>How many bytes may be sent right now.</summary>
    public long Credit => Interlocked.Read(ref _credit);

    private void OnEvent(Envelope message)
    {
        if (message.Method != "stream.credit") return;
        if (message.StreamId != _inputStream) return;
        Interlocked.Add(ref _credit,
                        message.Payload["bytes"]?.GetValue<int>() ?? 0);
    }

    /// <summary>Listen to the data channel: synthesised speech comes from there.</summary>
    private async Task ReadAsync(CancellationToken token)
    {
        try
        {
            while (!token.IsCancellationRequested)
            {
                var frame = await _data.ReceiveAsync(token).ConfigureAwait(false);
                Received += frame.Payload.Length;
                _speaker.Enqueue(frame.Payload);
                // Credit is returned as playback proceeds, not as data is
                // received: otherwise the core will pack our queue a minute
                // ahead, and "stop" stops being instant.
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

    /// <summary>
    /// The core opened a speech stream: start listening to the data channel.
    /// </summary>
    /// <remarks>
    /// Reading the channel used to begin only together with microphone
    /// capture — that is, speech could be heard only if Rina had been
    /// listened to beforehand. Playback and capture are independent: Rina
    /// answers what was typed by hand too.
    ///
    /// Returns the credit issued: the receiver announces how much it is
    /// ready to take, and this is no formality — a speaker is slower than a
    /// wire.
    /// </remarks>
    public int StartPlayback(int streamId, string kind, int sampleRate)
    {
        if (kind != OutputKind) return 0;

        _outputStream = streamId;
        _speaker.Reopen(sampleRate);

        if (_reading is null)
        {
            _reading = new CancellationTokenSource();
            _ = Task.Run(() => ReadAsync(_reading.Token));
        }
        return PlaybackCredit;
    }

    /// <summary>How many bytes of speech the shell is ready to take at once.</summary>
    /// <remarks>
    /// Half a second of sound at 24 kHz. Any more and "stop" stops being
    /// instant: what can be cut off is what has not been sent yet, not what
    /// is already lying in our queue.
    /// </remarks>
    private const int PlaybackCredit = 24000 * 2 / 2;

    private int _outputStream;

    /// <summary>The speech stream was closed by the core.</summary>
    public void StopPlayback()
    {
        _outputStream = 0;
        _speaker.Interrupt();
    }

    /// <summary>Cut the speech off: "stop" is obliged to be instant.</summary>
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
