using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace Rina.Shell;

/// <summary>
/// The living background: a slow flow of light under the working area.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0b-A06</c>. A field of fractal noise whose own domain is
/// warped by more noise — the standard road to a liquid, marbled,
/// nebula-like flow. It is computed rather than drawn: there is no picture
/// to loop and nothing to come back round to.
/// </para>
/// <para>
/// <b>Why not soft gradients.</b> The first edition drifted a few large
/// radial patches and could not produce this: overlapping ellipses give
/// smooth blobs, never a filament or an eddy. What makes a flow read as
/// liquid is that its own coordinates are bent by noise, and that has to be
/// evaluated per pixel.
/// </para>
/// <para>
/// <b>Computed small and stretched.</b> The field has no detail finer than
/// its own features, so a low resolution loses nothing and costs a
/// fraction: it is computed a couple of hundred points across and enlarged
/// with smoothing. That is what makes a per-pixel effect affordable on the
/// CPU at all, and it is why there is no shader — WPF's shader model is old
/// enough that fitting this into it would cost more than the effect is
/// worth.
/// </para>
/// <para>
/// <b>Text stays readable, and this is the one limit that does not
/// move.</b> Every stop of the ramp is checked against the ink <b>and</b>
/// the legends at 4.5 in <c>check_contrast.py</c>. A background that moves
/// under the words is not one surface but every colour it can reach, and a
/// living background that costs a person one unreadable line has not earned
/// its place. On a dark finish that ceiling is low, so the flow shows itself
/// in hue rather than in brightness — which is how a dark nebula looks
/// anyway.
/// </para>
/// <para>
/// <b>It stops when nobody is looking</b>, and obeys the system's request
/// for less movement. See <see cref="Follow"/> and
/// <see cref="WantsStillness"/>: usage mode number one is "in the
/// background while working, the window minimised or in the tray", and a
/// window nobody sees has no right to turn frames.
/// </para>
/// </remarks>
public sealed class Backdrop
{
    /// <summary>How many points across the field is computed.</summary>
    /// <remarks>
    /// Small on purpose. The flow has no detail finer than its own
    /// features, so this is not a compromise on quality but the resolution
    /// the picture actually has; anything above it would be spent computing
    /// the same value twice.
    /// </remarks>
    private const int Wide = 288;
    private const int High = 162;

    private readonly Image _view;
    private readonly DispatcherTimer _clock = new();
    private readonly WriteableBitmap _film;
    private readonly byte[] _pixels = new byte[Wide * High * 4];

    private readonly double _period;
    private double _scale = 2.6;
    private double _warp = 1.1;
    private (byte R, byte G, byte B)[] _ramp = [];
    private bool _visible;

    public Backdrop(Image view)
    {
        _view = view;
        _period = Token("Background.Period", 90);
        var fps = Token("Background.Fps", 20);

        _film = new WriteableBitmap(Wide, High, 96, 96, PixelFormats.Bgra32,
                                    null);
        _view.Source = _film;
        RenderOptions.SetBitmapScalingMode(_view, BitmapScalingMode.Fant);

        _clock.Interval = TimeSpan.FromMilliseconds(1000.0 / Math.Max(1, fps));
        _clock.Tick += (_, _) => Advance();

        // Windows says when its own settings change, and "show animations in
        // windows" is one of them. Without this, lifting reduced motion
        // would leave the background standing until the window was touched.
        SystemParameters.StaticPropertyChanged += (_, _) => Settle();
        Asked += Settle;

        Build();
    }

    /// <summary>How far along its period the flow is, in [0, 1).</summary>
    /// <remarks>
    /// Public because it is the only honest way to check that the backdrop
    /// stopped. "It is not moving" cannot be seen in a screenshot, and a
    /// check that measured whether a timer object exists would agree with
    /// its author. This is measured across time: the phase advances while
    /// it runs and stands still while it does not.
    /// </remarks>
    public double Phase { get; private set; }

    /// <summary>Is the clock ticking right now.</summary>
    public bool Running => _clock.IsEnabled;

    /// <summary>How many stops the flow's ramp has.</summary>
    public int Steps => _ramp.Length;

    /// <summary>How long the last frame took to compute, in milliseconds.</summary>
    /// <remarks>
    /// Measured and asserted, not assumed. The whole argument for stopping
    /// the background when nobody looks is that frames cost a person
    /// something; a frame whose cost was never measured makes that argument
    /// on trust. This is the number the motion check holds to a ceiling.
    /// </remarks>
    public double LastFrameMs { get; private set; }

    /// <summary>Does the system want less movement.</summary>
    public static bool WantsStillness =>
        Stillness ?? !SystemParameters.ClientAreaAnimation;

    /// <summary>Answer the question above without asking the system.</summary>
    /// <remarks>
    /// For the motion check, and only for it. Whether reduced motion is
    /// obeyed is a branch that depends on the developer's own Windows
    /// setting: on a machine with animations on, the branch is never
    /// reached, and a check that cannot reach it checks half. Breaking the
    /// obedience deliberately proved exactly that — the check stayed green.
    ///
    /// <c>null</c> means "ask the system", and that is what it is in the
    /// application.
    /// </remarks>
    public static bool? Stillness
    {
        get => _stillness;
        set { _stillness = value; Asked?.Invoke(); }
    }

    private static bool? _stillness;

    /// <summary>Somebody changed <see cref="Stillness"/>.</summary>
    private static event Action? Asked;

    /// <summary>
    /// Take the ramp of the finish that is on now, and repaint.
    /// </summary>
    /// <remarks>
    /// The finish is swapped as a whole resource dictionary, so the colours
    /// have to be read again. The phase is kept: the flow must not jump when
    /// a person tries a finish on.
    /// </remarks>
    public void Build()
    {
        var steps = (int)Token("Nebula.Steps", 5);
        var ramp = new List<(byte, byte, byte)>();
        for (var at = 0; at < steps; at++)
            if (Application.Current?.TryFindResource($"Color.Nebula{at}")
                is Color stop)
                ramp.Add((stop.R, stop.G, stop.B));

        _ramp = [.. ramp];
        _scale = Token("Nebula.Scale", 2.6);
        _warp = Token("Nebula.Warp", 1.1);
        Paint();
    }

    /// <summary>Run or stop, to match whether there is anybody to look.</summary>
    /// <remarks>
    /// One method for both, because the caller has one thing to say: is the
    /// window visible to a person right now. Two methods would let a caller
    /// start twice and stop once.
    /// </remarks>
    public void Follow(bool visible)
    {
        _visible = visible;
        Settle();
    }

    /// <summary>Bring the clock into line with both of its reasons.</summary>
    /// <remarks>
    /// There are two inputs — whether anybody is looking, and whether the
    /// system was asked for less movement — and they change independently.
    /// The first edition consulted the second only inside <c>Follow</c>,
    /// which the window calls on its own events: a person switching
    /// animations off in Windows kept a moving background until they next
    /// activated the window. The promise was kept eventually, and
    /// "eventually" is not what it says.
    /// </remarks>
    private void Settle()
    {
        var wanted = _visible && !WantsStillness;
        if (wanted == Running) return;
        if (wanted) _clock.Start();
        else _clock.Stop();
    }

    private void Advance()
    {
        // Stillness can be asked for while we are running, and then this is
        // where we hear about it: one tick late at most.
        if (WantsStillness)
        {
            Settle();
            return;
        }

        // A fraction of the period per tick, from the interval rather than
        // from a count of ticks: a tick that arrived late must move the flow
        // further, or the movement slows down under load instead of keeping
        // its promised period.
        Phase = (Phase + _clock.Interval.TotalSeconds / _period) % 1.0;
        Paint();
    }

    /// <summary>Compute one frame of the flow.</summary>
    private void Paint()
    {
        if (_ramp.Length == 0) return;
        var started = System.Diagnostics.Stopwatch.GetTimestamp();

        // Time is the third and fourth coordinate of the noise, and it goes
        // round a circle rather than along a line: at the end of the period
        // the field is where it started, so there is no seam — and no drift
        // into ever-larger numbers, where floating point starts to grain.
        var angle = Phase * 2 * Math.PI;
        var zx = (float)(Math.Cos(angle) * 0.8);
        var zy = (float)(Math.Sin(angle) * 0.8);

        var scale = (float)_scale;
        var warp = (float)_warp;
        var ramp = _ramp;
        var pixels = _pixels;

        Parallel.For(0, High, y =>
        {
            var v = (float)y / High * scale;
            var row = y * Wide * 4;
            for (var x = 0; x < Wide; x++)
            {
                var u = (float)x / Wide * scale * ((float)Wide / High);

                // Domain warping: the field's own coordinates are bent by
                // the field, twice. One level gives clouds; two give the
                // filaments and eddies that read as liquid.
                var qx = Fbm(u, v, zx, zy);
                var qy = Fbm(u + 5.2f, v + 1.3f, zx, zy);

                var rx = Fbm(u + warp * qx + 1.7f, v + warp * qy + 9.2f,
                             zx, zy);
                var ry = Fbm(u + warp * qx + 8.3f, v + warp * qy + 2.8f,
                             zx, zy);

                var f = Fbm(u + warp * rx, v + warp * ry, zx, zy);

                var (red, green, blue) = Shade(ramp, f);
                var at = row + x * 4;
                pixels[at] = blue;
                pixels[at + 1] = green;
                pixels[at + 2] = red;
                pixels[at + 3] = 255;
            }
        });

        _film.WritePixels(new Int32Rect(0, 0, Wide, High), pixels, Wide * 4, 0);

        LastFrameMs = (System.Diagnostics.Stopwatch.GetTimestamp() - started)
                      * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
    }

    /// <summary>A value of the field -> a colour of the ramp.</summary>
    private static (byte R, byte G, byte B) Shade(
        (byte R, byte G, byte B)[] ramp, float value)
    {
        value = Math.Clamp(value * 0.5f + 0.5f, 0f, 0.999f);
        var place = value * (ramp.Length - 1);
        var low = (int)place;
        var mix = place - low;
        var a = ramp[low];
        var b = ramp[Math.Min(low + 1, ramp.Length - 1)];
        return ((byte)(a.R + (b.R - a.R) * mix),
                (byte)(a.G + (b.G - a.G) * mix),
                (byte)(a.B + (b.B - a.B) * mix));
    }

    /// <summary>Fractal noise: four octaves, each finer and quieter.</summary>
    /// <remarks>
    /// Four and not seven. Every further octave is another pass over every
    /// pixel, and past this its features fall below what the enlargement can
    /// show — it would be paid for and not seen. The number was raised from
    /// three once the frame was measured and found to cost a fifth of its
    /// budget: detail one can afford is detail worth having.
    /// </remarks>
    private static float Fbm(float x, float y, float zx, float zy)
    {
        var sum = 0f;
        var weight = 0.5f;
        for (var octave = 0; octave < 4; octave++)
        {
            sum += weight * Noise(x, y, zx, zy);
            x *= 2.03f;
            y *= 2.03f;
            zx *= 2.03f;
            zy *= 2.03f;
            weight *= 0.5f;
        }
        return sum * 2f - 1f;
    }

    /// <summary>Smooth value noise on a lattice.</summary>
    /// <remarks>
    /// Four coordinates, because time here is a circle: two are the place
    /// and two are where we are on that circle. Going round rather than
    /// along is what lets the flow return to itself without a jump.
    /// </remarks>
    private static float Noise(float x, float y, float zx, float zy)
    {
        int xi = (int)MathF.Floor(x), yi = (int)MathF.Floor(y);
        int ax = (int)MathF.Floor(zx * 8), ay = (int)MathF.Floor(zy * 8);
        float xf = x - xi, yf = y - yi;

        // Smoothstep on both axes: linear interpolation would leave the
        // lattice visible as a grid of creases.
        float u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);

        float c00 = Hash(xi, yi, ax, ay);
        float c10 = Hash(xi + 1, yi, ax, ay);
        float c01 = Hash(xi, yi + 1, ax, ay);
        float c11 = Hash(xi + 1, yi + 1, ax, ay);

        return (c00 * (1 - u) + c10 * u) * (1 - v)
             + (c01 * (1 - u) + c11 * u) * v;
    }

    /// <summary>A repeatable number in [0, 1) from four whole coordinates.</summary>
    private static float Hash(int x, int y, int zx, int zy)
    {
        unchecked
        {
            var n = x * 374761393 + y * 668265263 + zx * 1274126177
                    + zy * 1103515245;
            n = (n ^ (n >> 13)) * 1274126177;
            return ((n ^ (n >> 16)) & 0x7fffffff) / (float)0x7fffffff;
        }
    }

    private static double Token(string key, double fallback) =>
        Application.Current?.TryFindResource(key) is double value
            ? value : fallback;
}
