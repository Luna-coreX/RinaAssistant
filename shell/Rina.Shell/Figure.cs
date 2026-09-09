using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace Rina.Shell;

/// <summary>What Rina is doing, as the figure shows it.</summary>
/// <remarks>
/// Four and no more. Every one of them is a state a person can tell apart
/// without being told, and every one comes from something that actually
/// happens in the core — not from a timer that makes the picture look busy.
/// A fifth would have to be invented, and an invented state is a lie told
/// slowly.
/// </remarks>
public enum Doing
{
    /// <summary>Waiting. Nothing is being asked of her.</summary>
    Idle,

    /// <summary>The microphone is open: `listening.capturing`.</summary>
    Listening,

    /// <summary>An answer is being worked out: `assistant.thinking`.</summary>
    Thinking,

    /// <summary>She is speaking: there is her own audio still to play.</summary>
    Talking,
}

/// <summary>
/// The figure on the home screen: the flow, gathered into a disc.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0b-A07</c>. The same field as the background
/// (<see cref="Flow"/>), sampled in a circle and read with the same
/// palette — so the figure is not an object placed on the background but
/// the background looked at closely. One substance, seen twice.
/// </para>
/// <para>
/// <b>Every state comes from something real.</b> Listening is the
/// microphone being open, thinking is the core saying so, talking is her
/// own speech still waiting to be played. Nothing here is driven by a timer
/// pretending to be activity: a figure that looks busy while nothing
/// happens teaches a person to stop believing it, and then it cannot report
/// anything at all.
/// </para>
/// <para>
/// <b>It shares the background's clock</b> rather than keeping one of its
/// own. All the reasons the background stops — the window hidden, the
/// system asked for stillness — are reasons the figure stops too, and a
/// second clock would be a second place to remember them, which is a second
/// place to forget them.
/// </para>
/// </remarks>
public sealed class Figure
{
    /// <summary>How many points across the disc is computed.</summary>
    /// <remarks>
    /// A third of the background's pixels. The disc is small on screen and
    /// its features are large, so this is what it has; more would be paid
    /// for on every frame and seen by nobody.
    /// </remarks>
    private const int Side = 132;

    private readonly Image _view;
    private readonly WriteableBitmap _film;
    private readonly byte[] _pixels = new byte[Side * Side * 4];
    private readonly float[] _field = new float[Side * Side];

    private (byte R, byte G, byte B)[] _ramp = [];
    private double _turn;
    private double _breath;

    public Figure(Image view)
    {
        _view = view;
        _film = new WriteableBitmap(Side, Side, 96, 96, PixelFormats.Bgra32,
                                    null);
        _view.Source = _film;
        RenderOptions.SetBitmapScalingMode(_view, BitmapScalingMode.Fant);
    }

    /// <summary>What she is doing now.</summary>
    public Doing State { get; private set; } = Doing.Idle;

    /// <summary>How loud it is, while listening. Zero the rest of the time.</summary>
    public double Level { get; private set; }

    /// <summary>How far the disc has swelled beyond its resting size.</summary>
    /// <remarks>
    /// Public because "the states look different" is otherwise a matter of
    /// opinion. This is the number the check compares between states: a
    /// figure whose four states render the same picture has four names and
    /// one behaviour.
    /// </remarks>
    public double Swell { get; private set; }

    /// <summary>Say what is happening. Anything else is not the figure's business.</summary>
    public void Show(Doing state, double level = 0)
    {
        State = state;
        Level = state is Doing.Listening ? Math.Clamp(level, 0, 1) : 0;
    }

    /// <summary>Take the palette of the finish and accent that are on.</summary>
    public void Build(string accent, int steps)
    {
        var ramp = new List<(byte, byte, byte)>();
        var known = string.IsNullOrEmpty(accent)
            ? "Amber"
            : char.ToUpperInvariant(accent[0]) + accent[1..].ToLowerInvariant();
        for (var at = 0; at < steps; at++)
            if (Application.Current?.TryFindResource(
                    $"Color.Nebula.{known}.{at}") is Color stop)
                ramp.Add((stop.R, stop.G, stop.B));
        _ramp = [.. ramp];
    }

    /// <summary>One frame, at the background's own pace.</summary>
    public void Advance(double elapsed, double step)
    {
        if (_ramp.Length == 0) return;

        // Each state moves the disc differently, and the differences are
        // what a person reads. Thinking turns fastest — that is the one
        // state with nothing else to show, because nothing is coming in and
        // nothing is going out. Listening barely turns and answers the
        // voice instead.
        var (spin, swell, churn) = State switch
        {
            Doing.Listening => (0.15, 0.10 + Level * 0.30, 1.0),
            Doing.Thinking => (1.60, 0.05, 2.4),
            Doing.Talking => (0.55, 0.14, 1.7),
            _ => (0.22, 0.0, 0.7),
        };

        _turn += step * spin;
        _breath += step * (State is Doing.Idle ? 0.6 : 1.4);

        // Breathing under everything: even at rest the disc is alive, or it
        // reads as a picture rather than as something waiting.
        Swell = swell + Math.Sin(_breath * 2 * Math.PI) * 0.035;

        Paint((float)(elapsed * churn), (float)_turn);
    }

    private void Paint(float z, float turn)
    {
        var ramp = _ramp;
        var pixels = _pixels;
        var field = _field;
        var half = Side / 2f;
        // The disc keeps a margin inside the bitmap: the rim fades out, and
        // a fade that runs into the edge of the image is a cut, not a fade.
        var radius = half * (float)(0.80 + Swell);
        var cos = MathF.Cos(turn);
        var sin = MathF.Sin(turn);

        Parallel.For(0, Side, y =>
        {
            var dy = (y - half) / half;
            for (var x = 0; x < Side; x++)
            {
                var dx = (x - half) / half;

                // Turning the coordinates rather than the image: rotating
                // a bitmap resamples it and softens the whole disc a little
                // more on every frame.
                var u = (dx * cos - dy * sin) * 2.2f;
                var v = (dx * sin + dy * cos) * 2.2f;

                // One level of warp here, two in the background. The disc is
                // a third of the size and is looked at directly; the second
                // level would cost as much as the first and show detail
                // finer than the disc has room for.
                var qx = Flow.Fbm(u, v, z);
                var qy = Flow.Fbm(u + 5.2f, v + 1.3f, z);

                // Stretched, and only here. Domain-warped noise spends most
                // of its time near the middle of its range, which is right
                // for a background — it must not compete — and wrong for
                // the one thing on the screen a person is looking at. The
                // same palette, used across more of its width.
                var f = Flow.Fbm(u + qx, v + qy, z) * 1.9f;
                field[y * Side + x] = Math.Clamp(f, -1f, 1f);
            }
        });

        Parallel.For(0, Side, y =>
        {
            var dy = y - half;
            var row = y * Side * 4;
            for (var x = 0; x < Side; x++)
            {
                var dx = x - half;
                var far = MathF.Sqrt(dx * dx + dy * dy);
                var at = row + x * 4;

                // The rim fades over a tenth of the radius. A hard edge
                // would make the disc a sticker; this makes it a thing seen
                // through something.
                var soft = radius * 0.10f;
                var alpha = far >= radius ? 0f
                          : far <= radius - soft ? 1f
                          : (radius - far) / soft;

                if (alpha <= 0f)
                {
                    pixels[at + 3] = 0;
                    continue;
                }

                var (red, green, blue) = Flow.Shade(ramp, field[y * Side + x]);
                pixels[at] = blue;
                pixels[at + 1] = green;
                pixels[at + 2] = red;
                pixels[at + 3] = (byte)(alpha * 255);
            }
        });

        _film.WritePixels(new Int32Rect(0, 0, Side, Side), pixels, Side * 4, 0);
    }
}
