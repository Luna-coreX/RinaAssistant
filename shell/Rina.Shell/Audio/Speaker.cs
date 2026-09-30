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

    /// <summary>How many bytes the queue can hold in all.</summary>
    /// <remarks>
    /// Public so that "nothing was discarded" can be asserted rather than
    /// believed: without knowing the ceiling, a check cannot tell a queue
    /// that refused from one that swallowed.
    /// </remarks>
    public int Room
    {
        get { lock (_lock) { Ensure(); return _buffer!.BufferLength; } }
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

    /// <summary>
    /// How many times the queue ran dry while she was still speaking.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This is what "her speech glitches sometimes" is, counted.
    /// <c>BufferedWaveProvider</c> pads an empty queue with silence
    /// rather than complaining, so an underrun is heard by a person
    /// and recorded by nobody: the device plays on, the sentence has a
    /// hole in it, and every log in both processes says the reply went
    /// out whole.
    /// </para>
    /// <para>
    /// Counted here rather than guessed at from timings, because the
    /// two explanations — the sender being late and the receiver being
    /// starved of credit — look identical from outside and want
    /// opposite fixes.
    /// </para>
    /// </remarks>
    public int DryRuns { get; private set; }

    //: Whether the queue is empty **now**, seen by the watcher. A hole
    //: is this going true and then more sound arriving.
    private bool _ranDry;

    /// <summary>Add a chunk to the queue; playback starts by itself.</summary>
    public void Enqueue(ReadOnlySpan<byte> pcm)
    {
        if (pcm.Length == 0) return;
        var loud = Loudness(pcm);
        lock (_lock)
        {
            Ensure();
            // Sound arriving after the queue emptied means the queue
            // should not have emptied: what played in between was
            // silence nobody asked for.
            if (_ranDry && _device?.PlaybackState == PlaybackState.Playing)
            {
                DryRuns++;
                _ranDry = false;
            }
            _draining = false;
            _buffer!.AddSamples(pcm.ToArray(), 0, pcm.Length);
            _written += pcm.Length;
            _said.Enqueue((_written, loud));
            Wake();
        }
        SetSpeaking(true);
        WatchForSilence();
    }

    /// <summary>How loud what is being played **right now** is, from 0 to 1.</summary>
    /// <remarks>
    /// <para>
    /// Lined up with playback rather than with arrival. The level of a
    /// chunk is worked out when it is handed over, but it is answered for
    /// only when the ear reaches it: the position being played is what has
    /// been written less what is still waiting, and the chunk covering that
    /// position is the one that is sounding.
    /// </para>
    /// <para>
    /// Without lining up, the figure would pulse to a sentence the core had
    /// finished synthesising and not yet finished saying — ahead of the
    /// voice by the depth of the buffer, which is however long the last
    /// sentence was. A mouth that moves before the sound is worse than one
    /// that does not move at all.
    /// </para>
    /// </remarks>
    public double Speech
    {
        get
        {
            lock (_lock)
            {
                if (_buffer is null) return 0;
                var at = _written - _buffer.BufferedBytes;
                while (_said.Count > 1 && _said.Peek().End <= at)
                    _said.Dequeue();
                return _said.Count > 0 && IsSpeaking ? _said.Peek().Loud : 0;
            }
        }
    }

    //: Where each chunk ends, and how loud it was. Trimmed as the ear
    //: passes each one, so it never grows beyond what is still to play.
    private readonly Queue<(long End, double Loud)> _said = new();
    private long _written;

    /// <summary>The loudness of a chunk of 16-bit sound.</summary>
    private static double Loudness(ReadOnlySpan<byte> pcm)
    {
        if (pcm.Length < 2) return 0;
        double sum = 0;
        var count = 0;
        // Every eighth sample. This runs on the audio path, and the answer
        // is a bar on a screen: an eighth of the samples gives the same
        // answer to within far less than a person can see.
        for (var at = 0; at + 1 < pcm.Length; at += 16)
        {
            var sample = (short)(pcm[at] | (pcm[at + 1] << 8)) / 32768.0;
            sum += sample * sample;
            count++;
        }
        // Root mean square, then opened out: speech spends most of its time
        // quiet, and a linear scale would leave the figure nearly still
        // through an entire sentence.
        return count == 0 ? 0 : Math.Clamp(Math.Sqrt(sum / count) * 3.2, 0, 1);
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
            // Five seconds, and **nothing is discarded**.
            //
            // It was a second and a half with discarding on, and that is
            // what a person heard as "fragments of words all through her
            // speech". The core sends a whole utterance as fast as its
            // credit allows; everything past the second and a half was
            // dropped on the floor without a word, so what played was the
            // beginning, then a hole, then whatever fitted next.
            //
            // Discarding is the wrong answer to a full queue in any case:
            // the queue is full because the sender was allowed to send too
            // much, and the place to say so is the credit, not the bin. Now
            // credit is only returned as the queue drains (`RoomAsync`), so
            // it cannot fill in the first place — and if it ever does, we
            // would rather hear about it than lose a sentence quietly.
            BufferDuration = TimeSpan.FromSeconds(5),
            DiscardOnBufferOverflow = false,
        };
        _device = new WaveOutEvent
        {
            DesiredLatency = 100,
            DeviceNumber = WaveOut.DeviceCount > 0
                ? Math.Clamp(Device, 0, WaveOut.DeviceCount - 1) : 0,
        };
        _device.Init(_buffer);
    }

    /// <summary>
    /// Wait until the queue has room again — that is what credit means.
    /// </summary>
    /// <remarks>
    /// The receiver announces how much it is ready to take, and it is ready
    /// to take what it has room for. Returning credit the moment sound
    /// arrives says "I took it" when what happened is "I put it somewhere",
    /// and the somewhere has a bottom.
    /// </remarks>
    public async Task RoomAsync(int wanted, CancellationToken token)
    {
        // Two and a half seconds in hand, not one.
        //
        // Credit goes back one chunk at a time and each return is a
        // call that waits for its answer — eighty-five milliseconds of
        // sound per round trip down the pipe. A second of cushion is
        // eleven such trips; anything that makes them slower than the
        // sound they pay for drains the queue, and a drained queue is
        // played as silence rather than reported.
        //
        // The cushion is nearly free. It was kept at a second so that
        // "stop" would be instant, and that reasoning does not hold:
        // interrupting clears the queue outright (`Interrupt`), so what
        // is in it costs nothing to throw away. What a wider cushion
        // does cost is memory — a hundred and twenty kilobytes — and
        // the buffer holds five seconds, so it still cannot overflow.
        var ceiling = Math.Max(wanted, _format.AverageBytesPerSecond * 5 / 2);
        while (!token.IsCancellationRequested && Pending > ceiling)
            await Task.Delay(30, token).ConfigureAwait(false);
    }

    /// <summary>Speech ended by itself: the queue is empty.</summary>
    public void Finish()
    {
        if (Pending == 0) SetSpeaking(false);
    }

    /// <summary>
    /// Notice, unaided, that there is nothing left to play.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>This is why she stopped hearing after her first reply.</b> The
    /// end of speech was announced from one place only — the core closing
    /// the speech stream — and the core opens that stream once and closes
    /// it only if the sample rate changes. In an ordinary session the close
    /// never comes. So <c>IsSpeaking</c> latched true at the first
    /// utterance and stayed true, and with it the microphone stayed muted,
    /// because muting is what "Rina is speaking" is for: she must not hear
    /// herself. She never heard anything again either.
    /// </para>
    /// <para>
    /// A speaker knows it has finished when its queue has been empty for a
    /// moment. The grace matters: between chunks the queue empties briefly
    /// while an utterance is still going on, and declaring the end there
    /// would unmute the microphone into the middle of her own sentence.
    /// </para>
    /// <para>
    /// The core closing the stream still means the end — see
    /// <see cref="Drain"/>. This is not instead of that but underneath it:
    /// a promise kept only when somebody remembers to say so is kept by
    /// accident.
    /// </para>
    /// </remarks>
    private void WatchForSilence()
    {
        if (Interlocked.Exchange(ref _watching, 1) == 1) return;
        _ = Task.Run(async () =>
        {
            try
            {
                var quiet = 0;
                while (IsSpeaking)
                {
                    await Task.Delay(50).ConfigureAwait(false);
                    if (Pending == 0) _ranDry = true;
                    quiet = Pending == 0 ? quiet + 1 : 0;
                    if (quiet < 5) continue;      // a quarter of a second
                    lock (_lock) _device?.Stop();
                    SetSpeaking(false);
                    break;
                }
            }
            finally { Interlocked.Exchange(ref _watching, 0); }
        });
    }

    private int _watching;

    /// <summary>
    /// No more sound is coming. What is already here still has to be heard.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The core closes the stream when it has finished <b>sending</b>, and
    /// up to a second and a half of it is still sitting unplayed. Until
    /// this existed the close called <see cref="Interrupt"/>, which stops
    /// the device and empties the buffer — so the tail of every single
    /// utterance was thrown away. That is what a person heard as speech
    /// that breaks off.
    /// </para>
    /// <para>
    /// Draining is also when a short phrase finally starts: shorter than
    /// the pre-roll, it would otherwise sit in the buffer waiting for a
    /// fullness that is never coming.
    /// </para>
    /// </remarks>
    public void Drain()
    {
        lock (_lock)
        {
            if (_buffer is null) { SetSpeaking(false); return; }
            _draining = true;
            Wake();
        }

        // Polled rather than awaited: NAudio says nothing when a buffered
        // provider runs out — there is no "finished" to subscribe to, only
        // a count that reaches zero.
        _ = Task.Run(async () =>
        {
            while (Pending > 0) await Task.Delay(40);
            lock (_lock) _device?.Stop();
            SetSpeaking(false);
        });
    }

    //: Sound has stopped arriving; what is here is being played out.
    private bool _draining;

    /// <summary>Start the device once there is enough to play without gaps.</summary>
    /// <remarks>
    /// <b>Not on the first chunk.</b> Speech arrives as it is synthesised,
    /// which is near enough to real time that a device started on the first
    /// chunk runs the buffer dry between chunks — and a buffered provider
    /// pads what it lacks with silence, so the gaps are heard rather than
    /// reported. A fifth of a second in hand costs a fifth of a second of
    /// delay and removes the whole class.
    /// </remarks>
    private void Wake()
    {
        if (_device is null || _buffer is null) return;
        if (_device.PlaybackState == PlaybackState.Playing) return;

        // Four hundred milliseconds rather than two hundred. The
        // first gap is the likeliest: the sender is still opening its
        // connection to the service while the first chunk plays.
        var preRoll = _format.AverageBytesPerSecond * 2 / 5;
        if (!_draining && _buffer.BufferedBytes < preRoll) return;
        _device.Play();
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
            _draining = false;
            _device?.Stop();
            _buffer?.ClearBuffer();
            _said.Clear();
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
