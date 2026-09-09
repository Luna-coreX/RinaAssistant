using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;

namespace Rina.Shell;

/// <summary>What Rina is doing, as the figure shows it.</summary>
/// <remarks>
/// Four and no more. Every one of them is a state a person can tell apart
/// without being told, and every one comes from something that actually
/// happens — not from a timer that makes the picture look busy. A fifth
/// would have to be invented, and an invented state is a lie told slowly.
/// </remarks>
public enum Doing
{
    /// <summary>Waiting. Nothing is being asked of her.</summary>
    Idle,

    /// <summary>A person is speaking into the microphone right now.</summary>
    Listening,

    /// <summary>An answer is being worked out: `assistant.thinking`.</summary>
    Thinking,

    /// <summary>She is speaking: her own sound is being played.</summary>
    Talking,
}

/// <summary>
/// The figure on the home screen: an iridescent vortex.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0b-A07</c>, second edition. The first was a flat disc of
/// the background's own flow — honest about being one substance with the
/// window, and flat. What was asked for instead was a sphere: a dark core
/// with thin-film colour swirling over it, the way oil looks on water or a
/// soap bubble looks against a light.
/// </para>
/// <para>
/// <b>Three things make it a sphere rather than a circle.</b> The surface
/// normal is worked out per point, so the shading falls off towards the
/// rim. The colour is driven by the <i>grazing angle</i> — how far from
/// facing you the surface is — which is exactly what makes a real film
/// iridescent, and it is why the colour bands hug the edge instead of
/// lying flat across it. And the flow is sampled through a vortex: the
/// angle is twisted by an amount that depends on the radius, so the bands
/// wind in rather than drift past.
/// </para>
/// <para>
/// <b>The spectrum is turned to the accent.</b> A free rainbow belongs to
/// nobody; this one starts at the colour the rest of the window is using
/// and travels from there. Change the accent and the vortex changes with
/// it, the same as the background.
/// </para>
/// <para>
/// <b>It shares the background's clock</b> rather than keeping one of its
/// own. Every reason the background stops — the window hidden, the system
/// asked for stillness — is a reason the figure stops, and a second clock
/// would be a second place to remember that.
/// </para>
/// </remarks>
public sealed class Figure
{
    /// <summary>How many points across the sphere is computed.</summary>
    /// <remarks>
    /// Larger than the first edition's: this one has an edge that is looked
    /// at — the rim is where the colour lives — and a rim computed too
    /// coarsely reads as a jagged circle no amount of smoothing hides.
    /// </remarks>
    private const int Side = 200;

    private readonly Image _view;
    private readonly WriteableBitmap _film;
    private readonly byte[] _pixels = new byte[Side * Side * 4];

    private double _turn;
    private double _breath;

    //: What is followed towards its target rather than switched to it.
    //: `_churned` is the flow's own clock, kept separately because its
    //: **pace** is what a state changes: multiplying the shared elapsed
    //: time by a changing rate would jerk the field back and forth as the
    //: rate moved.
    private double _spin = 0.35;
    private double _twist = 0.9;
    private double _churn = 0.8;
    private double _burst;
    private double _churned;
    private double _hue;
    private double _loud;
    private double _shown;

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

    /// <summary>How loud it is — a voice heard, or her own. From 0 to 1.</summary>
    public double Loud => _loud;

    /// <summary>How far the sphere has swelled beyond its resting size.</summary>
    /// <remarks>
    /// Public because "the states look different" is otherwise a matter of
    /// opinion. This is the number the check compares between states: a
    /// figure whose four states render the same picture has four names and
    /// one behaviour.
    /// </remarks>
    public double Swell { get; private set; }

    /// <summary>Say what is happening, and how loudly.</summary>
    public void Show(Doing state, double loud = 0)
    {
        State = state;
        _loud = Math.Clamp(loud, 0, 1);
    }

    /// <summary>Take the hue of the accent that is on.</summary>
    /// <remarks>
    /// The hue, not the colour: the spectrum is generated, and what the
    /// accent decides is where it starts. Read out of the live brush rather
    /// than out of a table, because the accent is swapped at run time and a
    /// table would hold the one that was set at build.
    /// </remarks>
    public void Build()
    {
        if (Application.Current?.TryFindResource("Color.Signal") is Color tone)
            _hue = Hue(tone);
    }

    /// <summary>One frame, at the background's own pace.</summary>
    public void Advance(double elapsed, double step)
    {
        // How each state moves, and the differences are what a person
        // reads without being told which is which.
        //
        //   idle      — a slow, even drift and nothing else;
        //   listening — grows with the voice it hears, and quickens a
        //               little, because something is arriving;
        //   thinking  — the vortex winds inward and spins up: the one state
        //               with nothing coming in and nothing going out, so
        //               what it has to show is effort;
        //   talking   — pulses with her own voice, which is the only thing
        //               here that has a rhythm of its own.
        var (spin, swell, twist, churn, burst) = State switch
        {
            Doing.Listening => (0.5, 0.09 + _loud * 0.20, 1.1, 1.3,
                                _loud * 0.30),
            Doing.Thinking => (2.1, 0.04, 2.6, 2.2, 0.16),
            Doing.Talking => (0.9, 0.05 + _loud * 0.16, 1.4, 1.6,
                              0.10 + _loud * 0.55),
            _ => (0.35, 0.0, 0.9, 0.8, 0.0),
        };

        // **Everything is followed, not assigned.** The first edition eased
        // only the swell and switched the rest — the spin, the twist, the
        // pace of the flow — the instant the state changed, and a person
        // saw the sphere's insides jump while its outside grew smoothly.
        // Half a transition looks worse than none: the smooth part makes
        // the jump conspicuous.
        _shown = Follow(_shown, swell, swell > _shown ? 0.16 : 0.05);
        _spin = Follow(_spin, spin, 0.06);
        _twist = Follow(_twist, twist, 0.06);
        _churn = Follow(_churn, churn, 0.06);
        _burst = Follow(_burst, burst, burst > _burst ? 0.22 : 0.06);

        _turn += step * _spin;
        _breath += step * (State is Doing.Idle ? 0.5 : 1.2);
        _churned += step * _churn;

        Swell = _shown + Math.Sin(_breath * 2 * Math.PI) * 0.028;
        Paint((float)_churned, (float)_turn, (float)_twist, (float)_burst);
    }

    /// <summary>One value moving towards another. Nothing here jumps.</summary>
    private static double Follow(double have, double want, double pace) =>
        have + (want - have) * pace;

    private void Paint(float z, float turn, float twist, float burst)
    {
        var pixels = _pixels;
        var half = Side / 2f;
        var radius = half * (float)(0.86 + Swell);
        var hue = (float)_hue;

        Parallel.For(0, Side, y =>
        {
            var dy = y - half;
            var row = y * Side * 4;
            for (var x = 0; x < Side; x++)
            {
                var dx = x - half;
                var reachOut = MathF.Sqrt(dx * dx + dy * dy);
                var at = row + x * 4;

                // **The rim is thrown outward unevenly.** Growing and
                // shrinking is a balloon; what was asked for is the thing
                // scattering — parts of it flung further than others and
                // coming back at their own pace. So the radius is not one
                // number: it is a number per direction, pushed out by the
                // flow itself at the angle being looked at. Loud enough and
                // the sphere frays; quiet and it closes back into a circle.
                var about = MathF.Atan2(dy, dx);
                var scatter = burst <= 0.001f ? 0f
                    : Flow.Fbm(MathF.Cos(about) * 1.7f,
                               MathF.Sin(about) * 1.7f, z * 1.6f) * burst;
                var far = reachOut / (radius * (1f + scatter));

                if (far >= 1.06f)
                {
                    pixels[at + 3] = 0;
                    continue;
                }

                // The sphere's normal, and with it the grazing angle. This
                // is the whole difference between a ball and a coin: `face`
                // is one looking straight at you and nothing at the rim.
                var inside = MathF.Min(far, 1f);
                var face = MathF.Sqrt(MathF.Max(0f, 1f - inside * inside));
                var graze = 1f - face;

                // The vortex. The angle is twisted by an amount that grows
                // towards the middle, so what would have been rings becomes
                // a spiral being drawn in.
                var angle = MathF.Atan2(dy, dx) + turn + twist / (inside + 0.35f);
                var reach = inside * 2.1f;
                var u = MathF.Cos(angle) * reach;
                var v = MathF.Sin(angle) * reach;

                var qx = Flow.Fbm(u, v, z);
                var qy = Flow.Fbm(u + 5.2f, v + 1.3f, z);
                var field = Flow.Fbm(u + qx, v + qy, z);

                // Thin-film colour. The hue runs mostly with the flow and
                // only a little with the grazing angle — that order matters
                // and the first attempt had it the other way round, which
                // gave concentric rings of rainbow: a hue driven by the
                // radius can only make rings, because the radius is a
                // circle. Driven by the flow, it follows the vortex, and
                // the bands wind.
                var shade = hue + field * 1.05f + graze * 0.46f
                            + inside * 0.28f + z * 0.02f;

                // **The sphere is dark, and the colour lives in arcs.** Only
                // the crests of the flow light up, and only inside a band
                // near the rim where a real film is brightest. The first
                // attempt lit the whole disc and came out a rainbow
                // doughnut — bright everywhere is the same as nowhere.
                var wave = field * 0.5f + 0.5f;
                var crest = Math.Clamp((wave - 0.42f) / 0.34f, 0f, 1f);
                crest *= crest * (3f - 2f * crest);

                var band = MathF.Exp(-(inside - 0.74f) * (inside - 0.74f) * 7f);

                // Light from one side, so the colour gathers into a
                // crescent instead of ringing the sphere evenly. A film lit
                // from everywhere is a ring; a film lit from somewhere is a
                // sphere, and the difference is the only thing separating
                // this from a doughnut.
                var side = (dx * 0.72f - dy * 0.69f) / radius;
                var lamp = 0.34f + 0.66f * Math.Clamp(side * 0.5f + 0.5f, 0f, 1f);

                var lit = 0.03f + crest * band * lamp * 1.05f
                          + graze * graze * 0.12f;
                var sat = 0.54f + 0.32f * crest;

                var (red, green, blue) = FromHue(shade, sat,
                                                 Math.Clamp(lit, 0f, 1f));

                // The rim itself fades, and a little of the sphere spills
                // past the radius — a hard circle would read as a sticker.
                var alpha = inside < 0.86f ? 1f
                          : Math.Clamp((1.06f - far) / 0.20f, 0f, 1f);

                pixels[at] = blue;
                pixels[at + 1] = green;
                pixels[at + 2] = red;
                pixels[at + 3] = (byte)(alpha * 255);
            }
        });

        _film.WritePixels(new Int32Rect(0, 0, Side, Side), pixels, Side * 4, 0);
    }

    /// <summary>A colour from a place on the spectrum. Hue wraps at one.</summary>
    private static (byte R, byte G, byte B) FromHue(float hue, float sat,
                                                    float value)
    {
        hue -= MathF.Floor(hue);
        var sector = hue * 6f;
        var step = sector - MathF.Floor(sector);
        var p = value * (1 - sat);
        var q = value * (1 - sat * step);
        var t = value * (1 - sat * (1 - step));

        var (r, g, b) = (int)sector switch
        {
            0 => (value, t, p),
            1 => (q, value, p),
            2 => (p, value, t),
            3 => (p, q, value),
            4 => (t, p, value),
            _ => (value, p, q),
        };
        return ((byte)(r * 255), (byte)(g * 255), (byte)(b * 255));
    }

    /// <summary>Where on the spectrum a colour sits, from 0 to 1.</summary>
    private static double Hue(Color tone)
    {
        double r = tone.R / 255.0, g = tone.G / 255.0, b = tone.B / 255.0;
        var high = Math.Max(r, Math.Max(g, b));
        var low = Math.Min(r, Math.Min(g, b));
        var span = high - low;
        if (span <= 0.0001) return 0;
        var hue = high == r ? (g - b) / span
                : high == g ? 2 + (b - r) / span
                            : 4 + (r - g) / span;
        return (hue / 6.0 + 1.0) % 1.0;
    }
}
