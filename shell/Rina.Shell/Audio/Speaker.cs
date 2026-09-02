using NAudio.Wave;

namespace Rina.Shell.Audio;

/// <summary>
/// Воспроизведение речи: очередь кусков и мгновенное прерывание.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-F10</c>. Ядро синтезирует, оболочка воспроизводит.
/// Разделение принципиальное: модели живут там, где ML-экосистема, а
/// воспроизведение — там, где низкая задержка и нативное аудио.
/// </para>
/// <para>
/// <b>Очередь кусков, а не файл целиком.</b> Речь начинается раньше, чем
/// синтез закончен, — иначе после каждой реплики была бы пауза длиной в
/// синтез, и Рина отвечала бы с задержкой ровно там, где важнее всего её
/// не иметь.
/// </para>
/// <para>
/// <b>Прерывание мгновенное и без хвоста.</b> «Стоп» посреди фразы обязан
/// оборвать её сейчас, а не доиграть то, что уже в буфере: человек,
/// перебивший Рину и услышавший ещё полсекунды речи, перебьёт её снова.
/// Поэтому очередь чистится, а буфер устройства сбрасывается.
/// </para>
/// </remarks>
public sealed class Speaker : IDisposable
{
    private WaveFormat _format;
    private readonly object _lock = new();
    private WaveOutEvent? _device;
    private BufferedWaveProvider? _buffer;

    /// <summary>Рина говорит. Пока да — микрофон не слушает себя.</summary>
    public event Action<bool>? Speaking;

    public bool IsSpeaking { get; private set; }

    /// <summary>Сколько байт лежит непроигранными.</summary>
    public int Pending
    {
        get { lock (_lock) return _buffer?.BufferedBytes ?? 0; }
    }

    /// <summary>Куда выводить. Применится к следующему устройству.</summary>
    public int Device { get; set; }

    public static IReadOnlyList<AudioDevice> Devices()
    {
        var found = new List<AudioDevice>();
        for (var i = 0; i < WaveOut.DeviceCount; i++)
            found.Add(new AudioDevice(i, WaveOut.GetCapabilities(i).ProductName));
        return found;
    }

    /// <summary>По имени — номер; не нашлось — устройство по умолчанию.</summary>
    /// <remarks>Почему по имени — см. <see cref="Microphone.IndexOf"/>.</remarks>
    public static int IndexOf(string name) => Devices()
        .FirstOrDefault(d => d.Name == name)?.Index ?? 0;

    public Speaker(int sampleRate = Microphone.SampleRate,
                   int bits = Microphone.Bits, int channels = Microphone.Channels)
        => _format = new WaveFormat(sampleRate, bits, channels);

    /// <summary>Добавить кусок в очередь; воспроизведение начнётся само.</summary>
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
    /// Перейти на другую частоту.
    /// </summary>
    /// <remarks>
    /// Движки говорят на разных частотах: Edge на 24000, системный на 22050.
    /// Частота приходит в `format` при открытии потока; проиграть чужую в
    /// прежнем устройстве значит услышать Рину ниже и медленнее, чем она
    /// говорит.
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
            // Полторы секунды звука. Больше — значит дольше выгребать при
            // прерывании; меньше — риск щелчков на медленной машине.
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

    /// <summary>Речь кончилась сама: очередь пуста.</summary>
    public void Finish()
    {
        if (Pending == 0) SetSpeaking(false);
    }

    /// <summary>
    /// Оборвать речь сейчас же.
    /// </summary>
    /// <remarks>
    /// Порядок важен: сначала остановить устройство, потом вычистить буфер.
    /// Наоборот — значит дать устройству доиграть то, что оно уже забрало.
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
