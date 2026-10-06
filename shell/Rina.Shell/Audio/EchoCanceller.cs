using System.Runtime.InteropServices;

namespace Rina.Shell.Audio;

/// <summary>
/// Her own voice taken out of the microphone (<c>4.0b-V10</c>).
/// </summary>
/// <remarks>
/// <para>
/// <b>Why.</b> Through speakers rather than headphones Rina's voice comes
/// back into the microphone, is recognised — misheard, so no comparison of
/// words catches it — and she answers her own words. The shell is the one
/// place that has both signals: what the microphone hears and what the
/// speaker is playing.
/// </para>
/// <para>
/// <b>With what.</b> Windows' own Voice Capture DSP (<c>CLSID_CWMAudioAEC</c>,
/// <c>mfwmaaec.dll</c>, in every Windows since Vista): acoustic echo
/// cancellation and the suppression of what is left of it. Nothing to
/// download, no library to ship.
/// </para>
/// <para>
/// <b>In filter mode, not source mode.</b> In source mode the DSP opens the
/// devices itself and produces nothing while the speaker has no active
/// stream — the microphone would go deaf whenever she is quiet, unless
/// silence were played all the time, which keeps the computer from
/// sleeping. In filter mode the shell hands it the microphone and, as the
/// far end, exactly the sound the speaker is given to play: her voice and
/// nothing else, and silence when she is quiet.
/// </para>
/// <para>
/// <b>Alignment.</b> The far end is taken when the speaker's device reads
/// it, which is a little ahead of it being heard, and handed over in step
/// with the microphone, sample for sample. The canceller models the echo
/// path over <see cref="EchoLength"/>; a lead of a tenth or two of a second
/// is inside it. How far ahead it may run is bounded
/// (<see cref="MaxLead"/>), so a drift between the two clocks cannot grow.
/// </para>
/// <para>
/// <b>When it cannot work</b> — the object will not create, a format is
/// refused — the microphone goes on unprocessed and the reason is written
/// to the shell's log once. Hearing her own voice is the defect this
/// fixes; not hearing the person at all would be a worse one.
/// </para>
/// </remarks>
public sealed class EchoCanceller : IDisposable
{
    /// <summary>The rate everything here runs at: the microphone's.</summary>
    public const int Rate = Microphone.SampleRate;

    /// <summary>How long an echo path the canceller models, in ms.</summary>
    public const int EchoLength = 512;

    /// <summary>How far the far end may run ahead of the microphone.</summary>
    /// <remarks>
    /// The speaker's device reads ahead by its buffers; more than this is
    /// a drift between two clocks, and the oldest part is let go.
    /// </remarks>
    private static readonly int MaxLead = Rate * 3 / 10;

    private readonly object _lock = new();
    private readonly Queue<short> _farEnd = new();
    private IMediaObject? _dmo;
    private bool _failed;
    private long _clock;

    /// <summary>Set once something failed; then nothing is processed.</summary>
    public string Failure { get; private set; } = "";

    /// <summary>Whether the canceller is in use.</summary>
    public bool Enabled { get; set; } = true;

    /// <summary>How many microphone chunks went through it.</summary>
    public long Processed { get; private set; }

    // --- the far end -----------------------------------------------------------

    /// <summary>
    /// What the speaker's device has just read to play: 16-bit mono PCM at
    /// <paramref name="sampleRate"/>.
    /// </summary>
    public void Played(byte[] pcm, int sampleRate)
    {
        if (!Enabled || _failed || pcm.Length < 2) return;
        var samples = Resample(pcm, sampleRate);
        lock (_lock)
        {
            foreach (var sample in samples) _farEnd.Enqueue(sample);
            while (_farEnd.Count > MaxLead) _farEnd.Dequeue();
        }
    }

    /// <summary>
    /// To the canceller's rate, by linear interpolation after a light
    /// smoothing when coming down.
    /// </summary>
    /// <remarks>
    /// The far end only has to resemble what reaches the microphone, and
    /// the microphone's own capture is band-limited at 8 kHz; the smoothing
    /// keeps most of what lies above that from folding back into the band.
    /// </remarks>
    public static short[] Resample(ReadOnlySpan<byte> pcm, int sampleRate)
    {
        var count = pcm.Length / 2;
        var input = new short[count];
        for (var i = 0; i < count; i++)
            input[i] = (short)(pcm[2 * i] | (pcm[2 * i + 1] << 8));
        if (sampleRate == Rate || sampleRate <= 0) return input;

        if (sampleRate > Rate && count > 2)
        {
            var smooth = new short[count];
            smooth[0] = input[0];
            smooth[count - 1] = input[count - 1];
            for (var i = 1; i < count - 1; i++)
                smooth[i] = (short)((input[i - 1] + 2 * input[i] + input[i + 1]) / 4);
            input = smooth;
        }

        var length = (int)((long)count * Rate / sampleRate);
        var output = new short[length];
        var step = (double)sampleRate / Rate;
        for (var i = 0; i < length; i++)
        {
            var at = i * step;
            var left = (int)at;
            var right = Math.Min(left + 1, count - 1);
            var part = at - left;
            output[i] = (short)(input[left] + (input[right] - input[left]) * part);
        }
        return output;
    }

    // --- the microphone ------------------------------------------------------------

    /// <summary>
    /// The microphone chunk with her voice taken out — or as it came, when
    /// the canceller is off or failed.
    /// </summary>
    /// <remarks>
    /// Called on the microphone's own thread, and only there: the object is
    /// created on it on first use, so every call reaches it in the same
    /// apartment.
    /// </remarks>
    public byte[] Process(byte[] microphone)
    {
        if (!Enabled || _failed || microphone.Length < 2) return microphone;
        try
        {
            _dmo ??= Create();
            var samples = microphone.Length / 2;
            var far = new byte[samples * 2];
            lock (_lock)
            {
                for (var i = 0; i < samples && _farEnd.Count > 0; i++)
                {
                    var value = _farEnd.Dequeue();
                    far[2 * i] = (byte)value;
                    far[2 * i + 1] = (byte)(value >> 8);
                }
            }

            // Both streams carry the same moment: the canceller lines them
            // up by these, and they are in step by construction.
            var duration = samples * 10_000_000L / Rate;
            Feed(0, microphone, _clock, duration);
            Feed(1, far, _clock, duration);
            _clock += duration;

            var cleaned = Drain(microphone.Length);
            Processed++;
            // The canceller keeps a frame or two to itself at first; until
            // it gives sound back, the person is heard as is rather than
            // not at all.
            return cleaned.Length == 0 ? microphone : cleaned;
        }
        catch (Exception error)
        {
            Fail(error.Message);
            return microphone;
        }
    }

    private void Feed(int stream, byte[] data, long time, long duration)
    {
        var buffer = new Buffer(data.Length);
        buffer.Load(data);
        Check(_dmo!.ProcessInput(stream, buffer,
                                 InputSyncPoint | InputTime | InputTimeLength,
                                 time, duration), "ProcessInput");
    }

    private byte[] Drain(int expected)
    {
        var collected = new List<byte>(expected);
        var buffer = new Buffer(Math.Max(expected * 2, 3200));
        var output = new[] { new OutputBuffer { Buffer = buffer } };
        for (var round = 0; round < 16; round++)
        {
            buffer.SetLength(0);
            output[0].Status = 0;
            var result = _dmo!.ProcessOutput(0, 1, output, out _);
            if (result == SFalse) break;            // nothing ready yet
            Check(result, "ProcessOutput");
            collected.AddRange(buffer.Read());
            if ((output[0].Status & OutputIncomplete) == 0) break;
        }
        return collected.ToArray();
    }

    // --- making the object -----------------------------------------------------------

    private static IMediaObject Create()
    {
        var type = Type.GetTypeFromCLSID(ClsidVoiceCapture, throwOnError: true)!;
        var dmo = (IMediaObject)Activator.CreateInstance(type)!;
        var store = (IPropertyStore)dmo;

        Set(store, SystemMode, PropVariant.Int(SingleChannelAec));
        Set(store, SourceMode, PropVariant.Bool(false));
        Set(store, FeatureMode, PropVariant.Bool(true));
        Set(store, EchoLengthKey, PropVariant.Int(EchoLength));
        // Noise suppression on, gain control off: the core's segmenter
        // judges a phrase by its loudness, and a gain that moves on its own
        // would move that judgement with it.
        Set(store, NoiseSuppression, PropVariant.Int(1));
        Set(store, GainControl, PropVariant.Bool(false));
        // Two passes of suppression over what cancellation leaves: through
        // a speaker, what is left is her voice, and her voice is exactly
        // what must not reach recognition.
        Set(store, EchoSuppression, PropVariant.Int(2));

        var format = MediaType.Pcm(Rate);
        try
        {
            Check(dmo.SetInputType(0, ref format.Value, 0), "SetInputType(0)");
            Check(dmo.SetInputType(1, ref format.Value, 0), "SetInputType(1)");
            Check(dmo.SetOutputType(0, ref format.Value, 0), "SetOutputType");
        }
        finally
        {
            format.Free();
        }
        Check(dmo.AllocateStreamingResources(), "AllocateStreamingResources");
        Platform.ShellLog.Info("echo cancellation on (Voice Capture DSP, "
                               + "filter mode)");
        return dmo;
    }

    private static void Set(IPropertyStore store, PropertyKey key, PropVariant value)
        => Check(store.SetValue(ref key, ref value), $"SetValue({key.Id})");

    private static void Check(int result, string what)
    {
        if (result < 0)
            throw new COMException($"{what}: 0x{result:X8}", result);
    }

    private void Fail(string why)
    {
        if (_failed) return;
        _failed = true;
        Failure = why;
        Platform.ShellLog.Warn($"echo cancellation unavailable, the "
                               + $"microphone goes unprocessed: {why}");
    }

    public void Dispose()
    {
        if (_dmo is not null)
        {
            try { _dmo.FreeStreamingResources(); } catch { /* going anyway */ }
            Marshal.FinalReleaseComObject(_dmo);
            _dmo = null;
        }
    }

    // --- COM ---------------------------------------------------------------------

    private static readonly Guid ClsidVoiceCapture =
        new("745057c7-f353-4f2d-a7ee-58434477730e");

    //: The Voice Capture DSP's properties, from wmcodecdsp.h: one format
    //: id, and ids counted from PID_FIRST_USABLE (2).
    private static readonly Guid AecFormat = new("6f52c567-0360-4bd2-9617-ccbf1421c939");
    private static readonly PropertyKey SystemMode = new(AecFormat, 2);
    private static readonly PropertyKey SourceMode = new(AecFormat, 3);
    private static readonly PropertyKey FeatureMode = new(AecFormat, 5);
    private static readonly PropertyKey EchoLengthKey = new(AecFormat, 7);
    private static readonly PropertyKey NoiseSuppression = new(AecFormat, 8);
    private static readonly PropertyKey GainControl = new(AecFormat, 9);
    private static readonly PropertyKey EchoSuppression = new(AecFormat, 10);
    private const int SingleChannelAec = 0;

    private const int InputSyncPoint = 0x1;
    private const int InputTime = 0x2;
    private const int InputTimeLength = 0x4;
    private const int OutputIncomplete = 0x01000000;
    private const int SFalse = 1;

    [StructLayout(LayoutKind.Sequential)]
    private readonly struct PropertyKey(Guid format, int id)
    {
        public readonly Guid Format = format;
        public readonly int Id = id;
    }

    /// <summary>A PROPVARIANT holding a 32-bit integer or a boolean.</summary>
    [StructLayout(LayoutKind.Explicit, Size = 24)]
    private struct PropVariant
    {
        [FieldOffset(0)] public ushort Type;
        [FieldOffset(8)] public int Value;

        public static PropVariant Int(int value) => new() { Type = 3, Value = value };

        // VARIANT_TRUE is -1, and a VT_BOOL holds it in sixteen bits.
        public static PropVariant Bool(bool value) =>
            new() { Type = 11, Value = value ? 0xFFFF : 0 };
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct DmoMediaType
    {
        public Guid MajorType;
        public Guid SubType;
        public int FixedSizeSamples;
        public int TemporalCompression;
        public int SampleSize;
        public Guid FormatType;
        public IntPtr Unknown;
        public int FormatSize;
        public IntPtr Format;
    }

    /// <summary>16-bit mono PCM at a rate, with its format block.</summary>
    private sealed class MediaType
    {
        public DmoMediaType Value;

        public static MediaType Pcm(int rate)
        {
            // WAVEFORMATEX: tag, channels, rate, bytes/s, align, bits, extra.
            var block = Marshal.AllocCoTaskMem(18);
            Marshal.WriteInt16(block, 0, 1);
            Marshal.WriteInt16(block, 2, 1);
            Marshal.WriteInt32(block, 4, rate);
            Marshal.WriteInt32(block, 8, rate * 2);
            Marshal.WriteInt16(block, 12, 2);
            Marshal.WriteInt16(block, 14, 16);
            Marshal.WriteInt16(block, 16, 0);
            return new MediaType
            {
                Value = new DmoMediaType
                {
                    MajorType = new Guid("73647561-0000-0010-8000-00aa00389b71"),
                    SubType = new Guid("00000001-0000-0010-8000-00aa00389b71"),
                    FixedSizeSamples = 1,
                    TemporalCompression = 0,
                    SampleSize = 0,
                    FormatType = new Guid("05589f81-c356-11ce-bf01-00aa0055595a"),
                    FormatSize = 18,
                    Format = block,
                },
            };
        }

        public void Free()
        {
            if (Value.Format != IntPtr.Zero) Marshal.FreeCoTaskMem(Value.Format);
            Value.Format = IntPtr.Zero;
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct OutputBuffer
    {
        [MarshalAs(UnmanagedType.Interface)] public IMediaBuffer Buffer;
        public int Status;
        public long Timestamp;
        public long Duration;
    }

    [ComImport, Guid("59eff8b9-938c-4a26-82f2-95cb84cdc837"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMediaBuffer
    {
        [PreserveSig] int SetLength(int length);
        [PreserveSig] int GetMaxLength(out int length);
        [PreserveSig] int GetBufferAndLength(IntPtr buffer, IntPtr length);
    }

    /// <summary>A block of unmanaged memory the DSP reads from or writes into.</summary>
    /// <remarks>
    /// **Freed by the finalizer, never by hand.** A DMO may keep an input
    /// buffer after `ProcessInput` returns and read it during a later
    /// `ProcessOutput`; freeing the memory once the call came back was an
    /// access violation on the first run. The object stays alive for as long
    /// as the DSP holds a reference to it, and its memory with it.
    /// </remarks>
    [ComVisible(true)]
    private sealed class Buffer : IMediaBuffer
    {
        private IntPtr _memory;
        private readonly int _capacity;
        private int _length;

        public Buffer(int capacity)
        {
            _capacity = capacity;
            _memory = Marshal.AllocHGlobal(capacity);
        }

        public void Load(byte[] data)
        {
            Marshal.Copy(data, 0, _memory, Math.Min(data.Length, _capacity));
            _length = Math.Min(data.Length, _capacity);
        }

        public byte[] Read()
        {
            var data = new byte[_length];
            Marshal.Copy(_memory, data, 0, _length);
            return data;
        }

        public int SetLength(int length)
        {
            if (length > _capacity) return unchecked((int)0x80070057);  // E_INVALIDARG
            _length = length;
            return 0;
        }

        public int GetMaxLength(out int length)
        {
            length = _capacity;
            return 0;
        }

        public int GetBufferAndLength(IntPtr buffer, IntPtr length)
        {
            if (buffer != IntPtr.Zero) Marshal.WriteIntPtr(buffer, _memory);
            if (length != IntPtr.Zero) Marshal.WriteInt32(length, _length);
            return 0;
        }

        ~Buffer()
        {
            if (_memory == IntPtr.Zero) return;
            Marshal.FreeHGlobal(_memory);
            _memory = IntPtr.Zero;
        }
    }

    [ComImport, Guid("d8ad0f58-5494-4102-97c5-ec798e59bcf4"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IMediaObject
    {
        // The order of the vtable, every method — unused ones included.
        [PreserveSig] int GetStreamCount(out int inputs, out int outputs);
        [PreserveSig] int GetInputStreamInfo(int index, out int flags);
        [PreserveSig] int GetOutputStreamInfo(int index, out int flags);
        [PreserveSig] int GetInputType(int index, int typeIndex, IntPtr type);
        [PreserveSig] int GetOutputType(int index, int typeIndex, IntPtr type);
        [PreserveSig] int SetInputType(int index, ref DmoMediaType type, int flags);
        [PreserveSig] int SetOutputType(int index, ref DmoMediaType type, int flags);
        [PreserveSig] int GetInputCurrentType(int index, IntPtr type);
        [PreserveSig] int GetOutputCurrentType(int index, IntPtr type);
        [PreserveSig] int GetInputSizeInfo(int index, out int size, out int lookahead, out int alignment);
        [PreserveSig] int GetOutputSizeInfo(int index, out int size, out int alignment);
        [PreserveSig] int GetInputMaxLatency(int index, out long latency);
        [PreserveSig] int SetInputMaxLatency(int index, long latency);
        [PreserveSig] int Flush();
        [PreserveSig] int Discontinuity(int index);
        [PreserveSig] int AllocateStreamingResources();
        [PreserveSig] int FreeStreamingResources();
        [PreserveSig] int GetInputStatus(int index, out int flags);
        [PreserveSig] int ProcessInput(int index, IMediaBuffer buffer, int flags, long time, long duration);
        [PreserveSig] int ProcessOutput(int flags, int count,
            [In, Out, MarshalAs(UnmanagedType.LPArray, SizeParamIndex = 1)] OutputBuffer[] buffers,
            out int status);
        [PreserveSig] int Lock(int locked);
    }

    [ComImport, Guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        [PreserveSig] int GetCount(out int count);
        [PreserveSig] int GetAt(int index, out PropertyKey key);
        [PreserveSig] int GetValue(ref PropertyKey key, out PropVariant value);
        [PreserveSig] int SetValue(ref PropertyKey key, ref PropVariant value);
        [PreserveSig] int Commit();
    }
}
