using NAudio.Wave;

namespace Rina.Shell.Audio;

/// <summary>Устройство ввода, как его называют человеку.</summary>
public sealed record AudioDevice(int Index, string Name);

/// <summary>
/// Микрофон: захват, уровень, заготовка распознавания тишины.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-F09</c>. Микрофон принадлежит оболочке: у неё низкая
/// задержка и нативный доступ к устройствам, а модели распознавания живут в
/// ядре (<c>4.0-E03</c>). Ровно поэтому звук течёт по каналу данных, а не
/// внутри JSON.
/// </para>
/// <para>
/// <b>Формат прибит гвоздями: 16 кГц, моно, 16 бит.</b> Не потому, что
/// другого не бывает, а потому, что это формат, который понимают и Vosk, и
/// Whisper, и передавать что-то иное значило бы пересчитывать его на той
/// стороне — в процессе, у которого и без того есть чем заняться.
/// </para>
/// <para>
/// <b>Заготовка тишины (VAD), а не сама тишина.</b> Уровень считается, порог
/// есть, решение «речь или нет» — нет: настоящее определение речи живёт в
/// ядре рядом с распознаванием. Здесь ровно столько, чтобы полоса уровня
/// показывала правду и чтобы <c>5.0</c> было куда встроить настоящий VAD.
/// </para>
/// </remarks>
public sealed class Microphone : IDisposable
{
    public const int SampleRate = 16000;
    public const int Channels = 1;
    public const int Bits = 16;

    private WaveInEvent? _device;
    private bool _muted;

    /// <summary>Пришёл кусок звука. Уже в нужном формате.</summary>
    public event Action<byte[]>? Captured;

    /// <summary>Уровень 0..1 — для полосы прибора.</summary>
    public event Action<float>? Level;

    /// <summary>Захват идёт.</summary>
    public bool Running { get; private set; }

    /// <summary>
    /// Не слушать себя.
    /// </summary>
    /// <remarks>
    /// Пока Рина говорит, захват продолжается, но наружу не идёт. Именно
    /// заглушить, а не остановить: остановка и запуск устройства занимают
    /// десятки миллисекунд, и на каждой реплике они превратились бы в
    /// проглоченное начало следующей фразы.
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
    /// Найти устройство по имени. Не нашлось — устройство по умолчанию.
    /// </summary>
    /// <remarks>
    /// Настройка хранит имя, а не номер, потому что номера перетасовываются
    /// от втыкания наушников: сохранённая «единица» назавтра оказывается
    /// другим микрофоном молча. Имя же либо совпадает, либо честно не
    /// находится — и тогда работает устройство по умолчанию, а не случайное.
    /// </remarks>
    public static int IndexOf(string name) => Devices()
        .FirstOrDefault(d => d.Name == name)?.Index ?? 0;

    /// <summary>
    /// Послушать устройство и вернуть самый громкий кусок.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Для проверки микрофона из настроек. Отвечает на вопрос «слышно ли
    /// вас вообще» — не на «понимает ли она слова»: это разные вопросы, и
    /// первый закрывает большинство жалоб. Заодно работает и там, где
    /// распознавание выключено вовсе.
    /// </para>
    /// <para>
    /// Устройство открывается своё, а не то, что уже слушает Рина:
    /// проверять надо выбранное в настройках, даже если сейчас слушается
    /// другое.
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
            // Текст исключения читает разработчик в журнале.
            throw new InvalidOperationException(
                "устройств записи не найдено");                // не интерфейс

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
    /// Громкость куска: среднеквадратичное по образцам.
    /// </summary>
    /// <remarks>
    /// Среднеквадратичное, а не пик: пик подскакивает от одного щелчка и
    /// делает полосу дёрганой, а прибору положено показывать состояние, а не
    /// вздрагивать.
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
        // Слух логарифмичен, и линейный уровень выглядит мёртвым: обычная
        // речь даёт 0.05–0.15 и почти не сдвинула бы полосу.
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
