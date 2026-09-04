using NAudio.Wave;

namespace Rina.Shell.Audio;

/// <summary>
/// Speech playback: a queue of chunks and instant interruption.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-F10</c>. The core synthesises, the shell plays. The
/// split is a matter of principle: the models live where the ML ecosystem
/// is, and playback lives where latency is low and audio is native.
/// </para>
/// <para>
/// <b>A queue of chunks, not a whole file.</b> Speech begins before
/// synthesis has finished — otherwise every reply would carry a pause the
/// length of the synthesis, and Rina would answer late exactly where being
/// late matters most.
/// </para>
/// <para>
/// <b>Interruption is instant and leaves no tail.</b> A "stop" mid-sentence
/// has to cut it off now, not play out what is already buffered: someone
/// who interrupted Rina and then heard another half-second of speech will
/// interrupt her again. So the queue is cleared and the device buffer is
/// flushed.
/// </para>
/// </remarks>
public sealed class Speaker : IDisposable
{
    private WaveFormat _format;
    private readonly object _lock = new();
    private WaveOutEvent? _device;
    private BufferedWaveProvider? _buffer;

    /// <summary>Rina is speaking. While she is, the microphone does not hear itself.</summary>
    public event Action<bool>? Speaking;

    public bool IsSpeaking { get; private set; }

    /// <summary>How many bytes are lying unplayed.</summary>
    public int Pending
    {
        get { lock (_lock) return _buffer?.BufferedBytes ?? 0; }
    }

    /// <summary>Where to output. Applies to the next device.</summary>
    public int Device { get; set; }

    public static IReadOnlyList<AudioDevice> Devices()
    {
        var found = new List<AudioDevice>();
        for (var i = 0; i < WaveOut.DeviceCount; i++)
            found.Add(new AudioDevice(i, WaveOut.GetCapabilities(i).ProductName));
        return found;
    }

    /// <summary>By name — a number; not found — the default device.</summary>
    /// <remarks>Why by name — see <see cref="Microphone.IndexOf"/>.</remarks>
    public static int IndexOf(string name) => Devices()
        .FirstOrDefault(d => d.Name == name)?.Index ?? 0;

    public Speaker(int sampleRate = Microphone.SampleRate,
                   int bits = Microphone.Bits, int channels = Microphone.Channels)
        => _format = new WaveFormat(sampleRate, bits, channels);

    /// <summary>Add a chunk to the queue; playback starts by itself.</summary>
    public void Enqueue(ReadOnlySpan<byte> pcm)
    {
        if (pcm.Length == 0) return;
        lock (_lock)
        {
            Ensure();
            _buffer!.AddSamples(pcm.ToArray(), 0, pcm.Length);
            if (_device!.PlaybackState != PlaybackState.Playing) _device.Play();
        }
        SetSpeaking(true);
    }

    /// <summary>
    /// Switch to another sample rate.
    /// </summary>
    /// <remarks>
    /// Engines speak at different rates: Edge at 24000, the system one at
    /// 22050. The rate arrives in `format` when the stream is opened;
    /// playing one rate through a device set up for another means hearing
    /// Rina lower and slower than she speaks.
    /// </remarks>
    public void Reopen(int sampleRate)
    {
        lock (_lock)
        {
            if (_device is not null && _format.SampleRate == sampleRate) return;
            _device?.Stop();
            _device?.Dispose();
            _device = null;
            _buffer = null;
            _format = new WaveFormat(sampleRate, Microphone.Bits,
                                     Microphone.Channels);
        }
    }

    private void Ensure()
    {
        if (_device is not null) return;
        _buffer = new BufferedWaveProvider(_format)
        {
            // A second and a half of audio. More means longer to drain on
            // an interruption; less risks clicks on a slow machine.
            BufferDuration = TimeSpan.FromSeconds(1.5),
            DiscardOnBufferOverflow = true,
        };
        _device = new WaveOutEvent
        {
            DesiredLatency = 100,
            DeviceNumber = WaveOut.DeviceCount > 0
                ? Math.Clamp(Device, 0, WaveOut.DeviceCount - 1) : 0,
        };
        _device.Init(_buffer);
    }

    /// <summary>Speech ended by itself: the queue is empty.</summary>
    public void Finish()
    {
        if (Pending == 0) SetSpeaking(false);
    }

    /// <summary>
    /// Cut the speech off right now.
    /// </summary>
    /// <remarks>
    /// The order matters: stop the device first, then clear the buffer. The
    /// other way round means letting the device play out what it has
    /// already taken.
    /// </remarks>
    public void Interrupt()
    {
        lock (_lock)
        {
            _device?.Stop();
            _buffer?.ClearBuffer();
        }
        SetSpeaking(false);
    }

    private void SetSpeaking(bool value)
    {
        if (IsSpeaking == value) return;
        IsSpeaking = value;
        Speaking?.Invoke(value);
    }

    public void Dispose()
    {
        Interrupt();
        _device?.Dispose();
        _device = null;
        _buffer = null;
    }
}
