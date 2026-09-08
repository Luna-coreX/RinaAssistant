using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;
using System.Windows.Threading;

namespace Rina.Shell;

/// <summary>
/// The living background: patches of light drifting under the face.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0b-A06</c>. Several large, very soft fields of light
/// float under the working area, each on a period of its own. The periods
/// do not divide into one another, so the picture never comes back round:
/// there is no loop for the eye to catch and nothing to start counting.
/// </para>
/// <para>
/// <b>The colours are the finish's own, and that is the whole defence
/// against the cliché.</b> The category always arrives at a purple-to-blue
/// glow (<c>4.0-R02</c>). The way not to arrive there is not to own a
/// colour the panel does not have: every tint lies within a hair of
/// <c>FACE</c> in value and differs only in cast — so what moves reads as
/// light on a panel rather than as a picture behind glass.
/// </para>
/// <para>
/// <b>Text stays readable wherever a patch drifts.</b> The tints are
/// checked against the ink in <c>check_contrast.py</c>, not against the
/// panel alone: a background that moves under the words has to be legible
/// in every position it can reach. A living background that costs a person
/// one line of unreadable text has not earned its place.
/// </para>
/// <para>
/// <b>No blur, deliberately.</b> A blurred layer this size costs real GPU
/// time on every frame, and it would be spent softening an edge that need
/// never be hard: a radial gradient fading to nothing has no edge to begin
/// with. The design system's ban on blur survives intact — this never
/// needed it.
/// </para>
/// <para>
/// <b>It stops, and stopping is part of the task rather than an
/// optimisation afterwards.</b> Usage mode number one is "in the
/// background while working, the window minimised or in the tray"
/// (<c>4.0-R01</c>). A window nobody is looking at has no right to turn
/// frames. A <c>Storyboard</c> with <c>RepeatBehavior.Forever</c> would go
/// on ticking while the window is hidden — WPF has no reason to think
/// otherwise — so the clock is ours and can be stopped.
/// </para>
/// <para>
/// <b>Reduced motion is obeyed.</b> A person who asked the system for
/// fewer animations meant it: for some people a moving background brings on
/// a headache. Then the patches stand still where they are. They do not
/// vanish — the depth is not the movement.
/// </para>
/// </remarks>
public sealed class Backdrop
{
    /// <summary>A patch of light and how it travels.</summary>
    /// <remarks>
    /// The shift is a <c>TranslateTransform</c> rather than
    /// <c>Canvas.Left</c>. Setting an attached position asks for a layout
    /// pass, and a layout pass thirty times a second for four ellipses is
    /// paid by the same person whose battery this whole thing is careful
    /// about. A render transform never leaves the composition.
    /// </remarks>
    private sealed record Drift(Ellipse Shape, TranslateTransform Shift,
                                double Turn, double Lean, double Phase);

    /// <summary>
    /// The rates the patches travel at, as multiples of the period.
    /// </summary>
    /// <remarks>
    /// Chosen not to divide into one another. With round ratios the patches
    /// would meet in the same arrangement every few minutes, and a
    /// background that repeats is one a person starts waiting for.
    /// </remarks>
    private static readonly double[] Turns = [1.00, 0.61, 1.41, 0.79];
    private static readonly double[] Leans = [0.83, 1.27, 0.55, 1.09];

    private readonly Canvas _sky;
    private readonly DispatcherTimer _clock = new();
    private readonly List<Drift> _drifts = [];

    private readonly double _period;
    private readonly double _amplitude;
    private bool _visible;

    public Backdrop(Canvas sky)
    {
        _sky = sky;
        _period = Token("Background.Period", 42);
        _amplitude = Token("Background.Amplitude", 0.34);
        var fps = Token("Background.Fps", 30);

        _clock.Interval = TimeSpan.FromMilliseconds(1000.0 / Math.Max(1, fps));
        _clock.Tick += (_, _) => Advance();

        // Windows says when its own settings change, and "show animations in
        // windows" is one of them. Without this, lifting reduced motion
        // would leave the background standing until the window was touched.
        SystemParameters.StaticPropertyChanged += (_, _) => Settle();
        Asked += Settle;

        _sky.SizeChanged += (_, _) => Render();
        Build();
    }

    /// <summary>How far along its period the drift is, in [0, 1).</summary>
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

    /// <summary>How many patches of light there are.</summary>
    public int Patches => _drifts.Count;

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
    /// Build the patches for the finish that is on now.
    /// </summary>
    /// <remarks>
    /// The finish is swapped as a whole resource dictionary, and the
    /// patches are brushes built in code from its colours — a dynamic
    /// reference cannot reach inside a gradient stop. So they are built
    /// again, and the phase is kept: the background must not jump when a
    /// person tries a finish on.
    /// </remarks>
    public void Build()
    {
        _sky.Children.Clear();
        _drifts.Clear();

        var count = (int)Token("Nebula.Count", 4);
        var opacity = Token("Nebula.Opacity", 0.55);

        for (var at = 0; at < count; at++)
        {
            if (Application.Current?.TryFindResource($"Color.Nebula{at}")
                is not Color tint) continue;

            var shape = new Ellipse
            {
                IsHitTestVisible = false,
                Fill = new RadialGradientBrush
                {
                    GradientStops =
                    [
                        new GradientStop(tint, 0),
                        // Fading to the same colour at zero alpha rather
                        // than to "Transparent": WPF interpolates through
                        // the colour it is given, and fading to a
                        // transparent black would drag every patch through
                        // a grey haze on its way out.
                        new GradientStop(
                            Color.FromArgb(0, tint.R, tint.G, tint.B), 1),
                    ],
                },
                Opacity = opacity,
            };
            var shift = new TranslateTransform();
            shape.RenderTransform = shift;
            _sky.Children.Add(shape);
            _drifts.Add(new Drift(shape, shift, Turns[at % Turns.Length],
                                  Leans[at % Leans.Length],
                                  at / (double)Math.Max(1, count)));
        }

        // The grain goes on top of the patches and stays there: it is not
        // decoration but the cure for what they do to an 8-bit screen.
        _sky.Children.Add(Grain());

        Render();
    }

    /// <summary>
    /// A grain of noise over the patches — against banding.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A large, very soft gradient rendered in eight bits per channel comes
    /// out in concentric rings: the eye finds an edge between two
    /// neighbouring values where the mathematics has a smooth slope. This
    /// was plainly visible on the first screenshot, and no amount of
    /// choosing colours removes it — the rings are quantisation, not
    /// colour.
    /// </para>
    /// <para>
    /// The cure is the ordinary one: a per-pixel dither of about one value,
    /// which pushes the boundary of a band back and forth and leaves the
    /// eye nothing straight to catch. A tile of 64 is enough — larger costs
    /// memory, smaller starts to read as a pattern of its own.
    /// </para>
    /// </remarks>
    private static UIElement Grain()
    {
        const int side = 64;
        var pixels = new byte[side * side * 4];
        var random = new Random(20260909);
        for (var at = 0; at < pixels.Length; at += 4)
        {
            // White or black, and almost entirely transparent: what is
            // needed is a nudge of one value, not a visible speckle.
            var lit = random.Next(2) == 0;
            var value = (byte)(lit ? 255 : 0);
            pixels[at] = pixels[at + 1] = pixels[at + 2] = value;
            pixels[at + 3] = 6;
        }

        var tile = BitmapSource.Create(side, side, 96, 96,
                                       PixelFormats.Bgra32, null, pixels,
                                       side * 4);
        return new Rectangle
        {
            IsHitTestVisible = false,
            Width = 4096,
            Height = 4096,
            Fill = new ImageBrush(tile)
            {
                TileMode = TileMode.Tile,
                Viewport = new Rect(0, 0, side, side),
                ViewportUnits = BrushMappingMode.Absolute,
            },
        };
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
        // from a count of ticks: a tick that arrived late must move the
        // drift further, or the movement slows down under load instead of
        // keeping its promised period.
        Phase = (Phase + _clock.Interval.TotalSeconds / _period) % 1.0;
        Render();
    }

    private void Render()
    {
        var width = _sky.ActualWidth > 0 ? _sky.ActualWidth : 900;
        var height = _sky.ActualHeight > 0 ? _sky.ActualHeight : 600;
        var size = Math.Min(width, height) * Token("Nebula.Spread", 1.15);

        foreach (var drift in _drifts)
        {
            // `IsNaN` first, and not for tidiness: an Ellipse starts with
            // a Width of NaN, and every comparison with NaN is false — so
            // `Math.Abs(NaN - size) > 0.5` said "the size is right" and the
            // patches were never given one. They came out zero-sized, and
            // the background was simply absent: no error anywhere, nothing
            // in the journal, just a flat panel.
            if (double.IsNaN(drift.Shape.Width)
                || Math.Abs(drift.Shape.Width - size) > 0.5)
            {
                // Size only when it actually changed: this is the one thing
                // here that does cost a layout pass, and it belongs to the
                // window being resized rather than to every frame.
                drift.Shape.Width = size;
                drift.Shape.Height = size;
                Canvas.SetLeft(drift.Shape, width / 2 - size / 2);
                Canvas.SetTop(drift.Shape, height / 2 - size / 2);
            }

            // Two circles at different rates make a curve that does not
            // close: the patch wanders instead of going round. That is the
            // whole of the flowing — no noise, no shader, nothing computed
            // per pixel.
            var a = (Phase * drift.Turn + drift.Phase) * 2 * Math.PI;
            var b = (Phase * drift.Lean + drift.Phase) * 2 * Math.PI;

            drift.Shift.X = Math.Sin(a) * width * _amplitude
                            + Math.Cos(b) * width * _amplitude * 0.4;
            drift.Shift.Y = Math.Cos(a) * height * _amplitude
                            + Math.Sin(b) * height * _amplitude * 0.4;
        }
    }

    private static double Token(string key, double fallback) =>
        Application.Current?.TryFindResource(key) is double value
            ? value : fallback;
}
