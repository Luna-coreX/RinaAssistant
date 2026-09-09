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
    private readonly Image? _calmView;
    private readonly DispatcherTimer _clock = new();
    private readonly WriteableBitmap _film;
    private readonly WriteableBitmap? _calmFilm;
    private readonly byte[] _pixels = new byte[Wide * High * 4];
    private readonly byte[] _calm = new byte[Wide * High * 4];
    private readonly byte[] _before = new byte[Wide * High * 4];
    private readonly byte[] _mark = new byte[Wide * High * 4];
    private double _sinceMark;

    /// <summary>The field, before it is turned into colour.</summary>
    /// <remarks>
    /// Kept as its own array so the two layers are two paintings of one
    /// field rather than two fields. Were the calm layer computed
    /// separately it would drift out of step with the vivid one, and the
    /// window would show the same flow twice at different moments — which
    /// reads, immediately and unmistakably, as broken.
    /// </remarks>
    private readonly float[] _field = new float[Wide * High];

    private (byte R, byte G, byte B)[] _calmRamp = [];

    private readonly double _period;

    /// <summary>How far the field has travelled, in periods.</summary>
    /// <remarks>
    /// It does not start at zero, and that is not decoration. At a whole
    /// number every octave of the noise sits exactly on a lattice plane at
    /// once, and the smoothing curve is flat at a plane — so the flow very
    /// nearly stops. Since all four octaves are whole together only at zero,
    /// starting there gave the stillest moment the field has, and it gave it
    /// at the moment a person first looks. An offset with no round factors
    /// puts the octaves out of step, where they belong.
    /// </remarks>
    private double _elapsed = 13.37;

    private double _scale = 2.6;
    private double _warp = 1.1;
    private double _drift = 0.55;
    private (byte R, byte G, byte B)[] _ramp = [];
    private bool _visible;

    public Backdrop(Image view, Image? calmView = null)
    {
        _view = view;
        _calmView = calmView;
        _period = Token("Background.Period", 90);
        var fps = Token("Background.Fps", 20);

        _film = new WriteableBitmap(Wide, High, 96, 96, PixelFormats.Bgra32,
                                    null);
        _view.Source = _film;
        RenderOptions.SetBitmapScalingMode(_view, BitmapScalingMode.Fant);

        if (_calmView is not null)
        {
            _calmFilm = new WriteableBitmap(Wide, High, 96, 96,
                                            PixelFormats.Bgra32, null);
            _calmView.Source = _calmFilm;
            RenderOptions.SetBitmapScalingMode(_calmView,
                                               BitmapScalingMode.Fant);
        }

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

    /// <summary>
    /// How much the picture itself changed since the previous frame, in
    /// values per channel.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The one number that would have caught the defect a person reported as
    /// "the background is fast and jerky, as if limited to five frames".
    /// Until this existed the motion check watched the <b>phase</b>, and the
    /// phase advanced perfectly while the picture stood still: time was not
    /// interpolated in the noise, so the field was frozen between the whole
    /// numbers of the lattice and snapped when it crossed one.
    /// </para>
    /// <para>
    /// A check that measures the clock instead of the picture agrees with
    /// its author about everything except what the person can see. This
    /// measures the picture: greater than zero means it moves at all, and
    /// small means it moves smoothly rather than in jumps.
    /// </para>
    /// </remarks>
    public double FrameChange { get; private set; }

    /// <summary>The cheapest frame so far, in milliseconds.</summary>
    /// <remarks>
    /// The number the check holds to a ceiling, and the last one is not.
    /// The question is whether a frame <b>can</b> be computed inside its
    /// budget, and a single slice of wall-clock answers a different one:
    /// whether the scheduler was kind just then. Under the full regression —
    /// a dozen processes at once — the last frame drifted over the ceiling
    /// and turned the check red on a machine that was merely busy. A check
    /// that fails by luck is a check that gets ignored.
    ///
    /// The best is still an honest measure of the thing: a frame that
    /// cannot fit even once does not fit, and a field four times the size
    /// failed on this number by a factor of three.
    /// </remarks>
    public double BestFrameMs { get; private set; }

    /// <summary>
    /// How much the picture has moved over the last second, in values.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The number that answers the question a person actually asks, which
    /// is "is this moving" — and they ask it by looking for a second or
    /// two, not by comparing consecutive frames.
    /// </para>
    /// <para>
    /// <see cref="FrameChange"/> was not wrong, it was answering something
    /// else. It caught a frozen field, which is what it was written for.
    /// It could not catch a field that moves by a hundredth of a value per
    /// frame — arithmetically alive, visually a photograph — and that is
    /// exactly what a person reported: "the animations are static". A
    /// measurement can be honest and still be about the wrong quantity.
    /// </para>
    /// </remarks>
    public double DriftPerSecond { get; private set; }

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

    /// <summary>A frame has passed: how far the field is, and by how much.</summary>
    public event Action<double, double>? Ticked;

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
        var accent = App.CurrentAccent;

        _ramp = Ramp(accent, steps, calm: false);
        _calmRamp = Ramp(accent, steps, calm: true);
        _scale = Token("Nebula.Scale", 2.6);
        _drift = Token("Background.Drift", 0.55);
        _warp = Token("Nebula.Warp", 1.1);
        Repaint();
    }

    /// <summary>One palette of the flow, by accent.</summary>
    /// <remarks>
    /// Read, not computed. Both palettes are worked out by
    /// <c>tools/nebula.py</c> and written into the finish's resources by the
    /// generator, and the checks use that same module. A second
    /// implementation of the same formula parts company with the first at
    /// its first change, and does it quietly: both sides go on producing
    /// plausible colours, and only a person sees that the check was
    /// measuring a palette nobody paints.
    /// </remarks>
    private static (byte R, byte G, byte B)[] Ramp(string accent, int steps,
                                                   bool calm)
    {
        // The accent is a lower-case name in the settings and a capitalised
        // one in the resources, because the generator writes resource keys
        // the way XAML keys are written. Asking with the settings' spelling
        // found nothing, `TryFindResource` returned null without complaint,
        // and the whole background silently vanished — the motion check
        // caught it, which is the only reason this took minutes.
        var known = string.IsNullOrEmpty(accent)
            ? "Amber"
            : char.ToUpperInvariant(accent[0]) + accent[1..].ToLowerInvariant();
        var name = calm ? "Calm." : "";
        var ramp = new List<(byte, byte, byte)>();
        for (var at = 0; at < steps; at++)
            if (Application.Current?.TryFindResource(
                    $"Color.Nebula.{known}.{name}{at}") is Color stop)
                ramp.Add((stop.R, stop.G, stop.B));
        return [.. ramp];
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
        // Two clocks, and they are not the same thing. `_elapsed` is where
        // the field is and only ever grows; `Phase` is how far round the
        // period we are, and it wraps. The checks watch the phase because a
        // number that wraps can be compared with itself.
        var step = _clock.Interval.TotalSeconds / _period;
        _elapsed += step;
        Phase = (Phase + step) % 1.0;
        Repaint();

        // Anything else that moves at the flow's pace hangs off this, and
        // not off a clock of its own. Every reason this one stops — the
        // window hidden, the system asked for stillness — is a reason they
        // stop too, and a second clock would be a second place to remember
        // that, which is a second place to forget it.
        Ticked?.Invoke(_elapsed, step);
    }

    /// <summary>Compute one frame of the flow.</summary>
    /// <summary>Compute the field afresh, then paint both layers from it.</summary>
    private void Repaint()
    {
        // The clock starts here and not inside `Paint`. When the work was
        // split in two, the stopwatch stayed with the cheap half — the
        // colouring — and the expensive half, the field itself, walked out
        // from under the measurement. The check went on reporting a frame
        // eight times cheaper than it was, and stayed green while doing it.
        // A measurement that keeps its old name after its subject has moved
        // is worse than none: it is trusted.
        var started = System.Diagnostics.Stopwatch.GetTimestamp();
        Sample();
        Paint();
        var spent = (System.Diagnostics.Stopwatch.GetTimestamp() - started)
                    * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
        LastFrameMs = spent;
        BestFrameMs = BestFrameMs is 0 ? spent : Math.Min(BestFrameMs, spent);
    }

    /// <summary>Work out the field, once, without any colour in it.</summary>
    /// <remarks>
    /// Separated from the painting because the two layers are two readings
    /// of one field, not two fields. Computed separately they would drift
    /// out of step, and the window would show the same flow twice at
    /// different moments — which reads, immediately, as broken.
    /// </remarks>
    private void Sample()
    {

        // Time is the third coordinate of the noise, and it goes along a
        // line. The first edition sent it round a circle so the flow would
        // return to itself without a seam, and paid for that with a fourth
        // dimension it then failed to interpolate — the seam was avoided and
        // the movement was lost.
        //
        // A loop was never needed. The coordinate grows by one every
        // `period` seconds, so a week of running leaves it in the thousands,
        // where a float still has five digits after the point. Nobody
        // watches a background long enough to notice that it does not
        // repeat, and nobody would thank us if it did.
        var z = (float)_elapsed;

        var scale = (float)_scale;
        var warp = (float)_warp;
        var field = _field;

        // The field travels sideways as well as morphing in place, and the
        // sideways part is what makes it read as moving at all. Morphing
        // alone changes the picture just as much by any measure, and the
        // eye does not see it: it tracks features going somewhere, and a
        // feature that stays put while changing shape is a still picture
        // being redrawn. Without this the background measured 0.24 values
        // of change per second and a person called it static — both were
        // true at once.
        var slide = (float)(_elapsed * _drift);
        var slideY = slide * 0.62f;

        Parallel.For(0, High, y =>
        {
            var v = (float)y / High * scale + slideY;
            var row = y * Wide;
            for (var x = 0; x < Wide; x++)
            {
                var u = (float)x / Wide * scale * ((float)Wide / High)
                        + slide;

                // Domain warping: the field's own coordinates are bent by
                // the field, twice. One level gives clouds; two give the
                // filaments and eddies that read as liquid.
                var qx = Flow.Fbm(u, v, z);
                var qy = Flow.Fbm(u + 5.2f, v + 1.3f, z);

                var rx = Flow.Fbm(u + warp * qx + 1.7f, v + warp * qy + 9.2f, z);
                var ry = Flow.Fbm(u + warp * qx + 8.3f, v + warp * qy + 2.8f, z);

                field[row + x] = Flow.Fbm(u + warp * rx, v + warp * ry, z);
            }
        });
    }

    /// <summary>Turn the field into the two pictures.</summary>
    private void Paint()
    {
        if (_ramp.Length == 0) return;

        Ink(_field, _ramp, _pixels);
        _film.WritePixels(new Int32Rect(0, 0, Wide, High), _pixels, Wide * 4, 0);

        if (_calmFilm is not null && _calmRamp.Length > 0)
        {
            // The calm layer is the same field in the calm palette, and then
            // softened. Both halves matter: the palette alone would give a
            // grey version of the same sharp picture, and the softening
            // alone would give a blurred bright one. A person reads on this
            // layer, and reading wants both.
            Ink(_field, _calmRamp, _calm);
            Soften(_calm);
            _calmFilm.WritePixels(new Int32Rect(0, 0, Wide, High), _calm,
                                  Wide * 4, 0);
        }

        // How far the picture moved, before the new frame becomes the old
        // one. Every fourth pixel and one channel: this is a measure of
        // movement, not a comparison of images, and it is paid for on every
        // frame.
        var moved = 0L;
        for (var at = 0; at < _pixels.Length; at += 16)
            moved += Math.Abs(_pixels[at] - _before[at]);
        FrameChange = moved / (double)(_pixels.Length / 16);
        Array.Copy(_pixels, _before, _pixels.Length);

        // And against a frame from a second ago. A second is roughly how
        // long a person looks at a background before deciding whether it is
        // alive, so it is the interval the question is actually about.
        _sinceMark += _clock.Interval.TotalSeconds;
        if (_sinceMark >= 1.0)
        {
            var drifted = 0L;
            for (var at = 0; at < _pixels.Length; at += 16)
                drifted += Math.Abs(_pixels[at] - _mark[at]);
            DriftPerSecond = drifted / (double)(_pixels.Length / 16)
                             / _sinceMark;
            Array.Copy(_pixels, _mark, _pixels.Length);
            _sinceMark = 0;
        }
    }

    /// <summary>Colour a field with a palette.</summary>
    private static void Ink(float[] field, (byte R, byte G, byte B)[] ramp,
                            byte[] pixels)
    {
        Parallel.For(0, High, y =>
        {
            var from = y * Wide;
            var to = y * Wide * 4;
            for (var x = 0; x < Wide; x++)
            {
                var (red, green, blue) = Flow.Shade(ramp, field[from + x]);
                var at = to + x * 4;
                pixels[at] = blue;
                pixels[at + 1] = green;
                pixels[at + 2] = red;
                pixels[at + 3] = 255;
            }
        });
    }

    /// <summary>A small blur, for the layer one reads on.</summary>
    /// <remarks>
    /// <para>
    /// A box blur over three points, run once along each axis. Not a
    /// <c>BlurEffect</c>: that one blurs the element after it has been
    /// enlarged to the size of the window, which is hundreds of times the
    /// pixels — the whole reason this field is computed small is not to pay
    /// that.
    /// </para>
    /// <para>
    /// The design system's ban on blur is untouched. That ban is about
    /// blurring the <b>interface</b> — a soft edge instead of a real one.
    /// This softens the background beneath it, which is the opposite move:
    /// it is what makes the edges above read as edges.
    /// </para>
    /// </remarks>
    private static void Soften(byte[] pixels)
    {
        var pass = new byte[pixels.Length];
        Array.Copy(pixels, pass, pixels.Length);

        Parallel.For(0, High, y =>
        {
            var row = y * Wide * 4;
            for (var x = 1; x < Wide - 1; x++)
                for (var channel = 0; channel < 3; channel++)
                {
                    var at = row + x * 4 + channel;
                    pixels[at] = (byte)((pass[at - 4] + pass[at]
                                         + pass[at + 4]) / 3);
                }
        });

        Array.Copy(pixels, pass, pixels.Length);
        Parallel.For(1, High - 1, y =>
        {
            var row = y * Wide * 4;
            var step = Wide * 4;
            for (var x = 0; x < Wide; x++)
                for (var channel = 0; channel < 3; channel++)
                {
                    var at = row + x * 4 + channel;
                    pixels[at] = (byte)((pass[at - step] + pass[at]
                                         + pass[at + step]) / 3);
                }
        });
    }

    private static double Token(string key, double fallback) =>
        Application.Current?.TryFindResource(key) is double value
            ? value : fallback;
}
