using NAudio.Wave;

namespace Rina.Shell.Audio;

/// <summary>An input device, as it is named to a person.</summary>
public sealed record AudioDevice(int Index, string Name);

/// <summary>
/// The microphone: capture, level, the beginnings of silence detection.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-F09</c>. The microphone belongs to the shell: it has low
/// latency and native access to devices, while the recognition models live
/// in the core (<c>4.0-E03</c>). That is exactly why audio flows over the
/// data channel rather than inside JSON.
/// </para>
/// <para>
/// <b>The format is nailed down: 16 kHz, mono, 16 bit.</b> Not because
/// nothing else exists, but because this is the format both Vosk and Whisper
/// understand, and sending anything else would mean resampling it on the
/// other side — in a process that has plenty to do already.
/// </para>
/// <para>
/// <b>The beginnings of silence detection (VAD), not the thing itself.</b>
/// The level is measured and a threshold exists; the "speech or not"
/// decision does not: real speech detection lives in the core next to
/// recognition. There is exactly enough here for the level strip to tell the
/// truth and for <c>5.0</c> to have somewhere to fit a real VAD.
/// </para>
/// </remarks>
public sealed class Microphone : IDisposable
{
    public const int SampleRate = 16000;
    public const int Channels = 1;
    public const int Bits = 16;

    private WaveInEvent? _device;
    private bool _muted;

    /// <summary>A chunk of audio arrived. Already in the right format.</summary>
    public event Action<byte[]>? Captured;

    /// <summary>Level 0..1 — for the instrument strip.</summary>
    public event Action<float>? Level;

    /// <summary>Capture is running.</summary>
    public bool Running { get; private set; }

    /// <summary>
    /// Do not listen to oneself.
    /// </summary>
    /// <remarks>
    /// While Rina is speaking, capture continues but nothing goes out.
    /// Muted, not stopped: stopping and starting a device take tens of
    /// milliseconds, and on every reply those would turn into a swallowed
    /// beginning of the next phrase.
    /// </remarks>
    public bool Muted
    {
        get => _muted;
        set => _muted = value;
    }

    public static IReadOnlyList<AudioDevice> Devices()
    {
        var found = new List<AudioDevice>();
        for (var i = 0; i < WaveInEvent.DeviceCount; i++)
            found.Add(new AudioDevice(i, WaveInEvent.GetCapabilities(i).ProductName));
        return found;
    }

    /// <summary>
    /// Find a device by name. Not found — the default device.
    /// </summary>
    /// <remarks>
    /// The setting stores a name, not a number, because numbers get
    /// reshuffled when headphones are plugged in: a saved "one" silently
    /// becomes a different microphone tomorrow. A name either matches or
    /// honestly does not — and then the default device is used, not a random
    /// one.
    /// </remarks>
    public static int IndexOf(string name) => Devices()
        .FirstOrDefault(d => d.Name == name)?.Index ?? 0;

    /// <summary>
    /// Listen to the device and return the loudest chunk.
    /// </summary>
    /// <remarks>
    /// <para>
    /// For the microphone check in settings. It answers "can you be heard at
    /// all" — not "does she understand the words": these are different
    /// questions, and the first one closes most complaints. It also works
    /// where recognition is switched off entirely.
    /// </para>
    /// <para>
    /// It opens a device of its own rather than the one Rina is already
    /// listening to: what must be checked is the one chosen in settings,
    /// even if something else is being listened to right now.
    /// </para>
    /// </remarks>
    public static async Task<(bool Ok, float Loudest, string Reason)>
        ProbeAsync(string deviceName, TimeSpan howLong)
    {
        var index = deviceName is "default" or "" ? 0 : IndexOf(deviceName);
        var loudest = 0f;

        try
        {
            using var probe = new Microphone();
            probe.Level += level =>
            {
                if (level > loudest) loudest = level;
            };
            probe.Start(index);
            await Task.Delay(howLong);
            probe.Stop();
        }
        catch (Exception error)
        {
            return (false, 0f, error.Message);
        }
        return (true, loudest, "");
    }

    public void Start(int deviceIndex = 0, int chunkMilliseconds = 100)
    {
        if (Running) return;
        if (WaveInEvent.DeviceCount == 0)
            // The exception text is read by a developer in the log.
            throw new InvalidOperationException(
                "no recording devices found");                 // not UI

        _device = new WaveInEvent
        {
            DeviceNumber = Math.Clamp(deviceIndex, 0, WaveInEvent.DeviceCount - 1),
            WaveFormat = new WaveFormat(SampleRate, Bits, Channels),
            BufferMilliseconds = chunkMilliseconds,
        };
        _device.DataAvailable += OnData;
        _device.StartRecording();
        Running = true;
    }

    private void OnData(object? sender, WaveInEventArgs e)
    {
        var chunk = e.Buffer.AsSpan(0, e.BytesRecorded).ToArray();
        Level?.Invoke(LevelOf(chunk));
        if (!_muted) Captured?.Invoke(chunk);
    }

    /// <summary>
    /// Loudness of a chunk: root mean square over the samples.
    /// </summary>
    /// <remarks>
    /// Root mean square, not peak: a peak jumps on a single click and makes
    /// the strip twitchy, whereas an instrument is supposed to show a state
    /// rather than flinch.
    /// </remarks>
    public static float LevelOf(ReadOnlySpan<byte> pcm)
    {
        if (pcm.Length < 2) return 0;
        double sum = 0;
        var samples = pcm.Length / 2;
        for (var i = 0; i + 1 < pcm.Length; i += 2)
        {
            var value = (short)(pcm[i] | (pcm[i + 1] << 8)) / 32768.0;
            sum += value * value;
        }
        var rms = Math.Sqrt(sum / samples);
        // Hearing is logarithmic, and a linear level looks dead: ordinary
        // speech gives 0.05–0.15 and would barely move the strip.
        return (float)Math.Clamp(Math.Sqrt(rms) * 1.4, 0, 1);
    }

    public void Stop()
    {
        if (!Running) return;
        _device?.StopRecording();
        Running = false;
    }

    public void Dispose()
    {
        Stop();
        if (_device is not null) _device.DataAvailable -= OnData;
        _device?.Dispose();
        _device = null;
    }
}
