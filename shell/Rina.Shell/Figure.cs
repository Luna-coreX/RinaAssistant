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
    private double _gloss = 70;
    private double _lamp = 0.42;
    private double _spray = 0.10;

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

    /// <summary>The cheapest frame the figure has painted, in milliseconds.</summary>
    /// <remarks>
    /// The figure is the most expensive thing on the home screen, and
    /// until now nothing watched it. The cheapest rather than the last:
    /// a single frame can be interrupted by anything at all, and what is
    /// being asked is what the work costs, not what the machine was doing
    /// at the time. The same measure and the same reasoning as the
    /// background's.
    /// </remarks>
    public double BestFrameMs { get; private set; }

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
        //
        // **And how hard the light sits on it** (`4.0b-E05`). The
        // highlight is the one thing on a round body that says outright
        // how hard its surface is, and a state is a hardness as much as a
        // pace: waiting is soft, effort is tight and glassy, a voice
        // flickers with what is being said.
        //
        // **And where the light sits on it** (`4.0b-E05`). The last
        // number is how far towards the eye the lamp stands: at nothing
        // it grazes the body from the side and the highlight lies out by
        // the rim; nearer one it comes round to the front and the
        // highlight walks in towards the middle. That walk is what makes
        // a change of state read as the body turning rather than as the
        // picture being swapped — waiting looks away, hearing turns
        // towards you, effort is lit from the side because a long shadow
        // is what effort looks like.
        //
        // The last number is the spray: how much of the body is thrown
        // off it as motes. Separate from the fraying of the rim, because
        // the two are different things — one is the surface losing its
        // shape, the other is dust in the light around it — and a state
        // can want one without the other.
        var (spin, swell, twist, churn, burst, gloss, lamp, spray)
            = State switch
        {
            Doing.Listening => (0.5, 0.09 + _loud * 0.20, 1.1, 1.3,
                                _loud * 0.30, 95.0, 0.74,
                                0.30 + _loud * 0.45),
            Doing.Thinking => (2.1, 0.04, 2.6, 2.2, 0.16, 240.0, 0.26, 0.22),
            Doing.Talking => (0.9, 0.05 + _loud * 0.16, 1.4, 1.6,
                              0.10 + _loud * 0.55, 70.0 + _loud * 120.0,
                              0.48 + _loud * 0.22, 0.40 + _loud * 0.55),
            _ => (0.35, 0.0, 0.9, 0.8, 0.0, 70.0, 0.42, 0.10),
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
        _gloss = Follow(_gloss, gloss, 0.06);
        _lamp = Follow(_lamp, lamp, 0.06);
        _spray = Follow(_spray, spray, 0.06);

        _turn += step * _spin;
        _breath += step * (State is Doing.Idle ? 0.5 : 1.2);
        _churned += step * _churn;

        Swell = _shown + Math.Sin(_breath * 2 * Math.PI) * 0.028;

        var began = System.Diagnostics.Stopwatch.GetTimestamp();
        Paint((float)_churned, (float)_turn, (float)_twist, (float)_burst,
              (float)_gloss, (float)_lamp, (float)_spray);
        var spent = (System.Diagnostics.Stopwatch.GetTimestamp() - began)
                    * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
        BestFrameMs = BestFrameMs is 0 ? spent : Math.Min(BestFrameMs, spent);
    }

    /// <summary>One value moving towards another. Nothing here jumps.</summary>
    private static double Follow(double have, double want, double pace) =>
        have + (want - have) * pace;

    /// <summary>
    /// One frame of the sphere (<c>4.0b-E05</c>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>The pattern lives on the ball, not on the disc.</b> This is the
    /// whole of the second edition. The flow used to be sampled by the
    /// angle and the distance from the middle — a flat mapping, which
    /// carries no depth however it is shaded: the bands ran across the rim
    /// at the same size they had in the centre, and a texture that does not
    /// foreshorten reads as painted on glass in front of a ball. Now the
    /// sample point is the surface normal itself, turned about the
    /// vertical. Near the rim the normal barely moves as the eye travels,
    /// so the pattern crowds together there by itself — which is what
    /// makes a sphere look like one.
    /// </para>
    /// <para>
    /// <b>The light is fixed and the surface turns under it.</b> The
    /// highlight and the shadowed side therefore stay where they are while
    /// the pattern travels through them, and that is the difference
    /// between a rotating body and a rotating picture.
    /// </para>
    /// <para>
    /// Three terms of light, and each says something different: the
    /// diffuse says which way the surface faces, the specular says how
    /// hard it is, the rim says where it ends. The dark core is left
    /// almost black — a film is a film because what is under it is not.
    /// </para>
    /// </remarks>
    /// <summary>
    /// One frame of the sphere (<c>4.0b-E05</c>, third edition).
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>Ribbons, not patches.</b> The second edition drove the colour
    /// straight off the noise, and noise gives blotches: the body was
    /// mottled where the reference a person brought is banded. So the
    /// colour now runs along a <i>phase</i> — a number that grows with the
    /// angle and with the distance from the middle, so its level lines are
    /// spirals — and the noise only warps that phase instead of being it.
    /// The bands come out as smooth arcs winding into the centre, and
    /// because the hue runs along the same phase, neighbouring ribbons are
    /// neighbouring colours.
    /// </para>
    /// <para>
    /// <b>The pattern lives on the ball.</b> The sample point for the warp
    /// is the surface normal, turned about the vertical: near the rim the
    /// normal barely moves as the eye travels, so the pattern crowds
    /// together there by itself, which is what makes a sphere look like
    /// one. A flat mapping carries no depth however it is shaded.
    /// </para>
    /// <para>
    /// <b>The light stands still and the surface turns under it.</b> The
    /// highlight and the shadowed side stay where they are while the
    /// ribbons travel through them — the difference between a rotating
    /// body and a rotating picture.
    /// </para>
    /// <para>
    /// <b>The spectrum is still the accent's.</b> The hue starts at the
    /// colour the rest of the window is using and travels from there, and
    /// how far it travels is one number. A free rainbow belongs to nobody.
    /// </para>
    /// </remarks>
    private void Paint(float z, float turn, float twist, float burst,
                       float gloss, float lamp, float spray)
    {
        var pixels = _pixels;
        var half = Side / 2f;
        var radius = half * (float)(0.78 + Swell);
        var hue = (float)_hue;

        // Upper left, and as far towards the eye as the state asks. One
        // light: a body lit from everywhere is a ring. It does not follow
        // the surface — that would be a headlamp, and a headlamp shows
        // nothing about shape.
        var depth = Math.Clamp(lamp, 0.05f, 0.95f);
        var across = MathF.Sqrt(1f - depth * depth);
        var lightX = -0.68f * across;
        var lightY = -0.73f * across;
        var lightZ = depth;

        var halfLen = MathF.Sqrt(lightX * lightX + lightY * lightY
                                 + (lightZ + 1f) * (lightZ + 1f));
        var hx = lightX / halfLen;
        var hy = lightY / halfLen;
        var hz = (lightZ + 1f) / halfLen;

        // Where the motes are thrown this second. It wanders rather than
        // standing: dust thrown always to the same side is a picture of
        // dust.
        var throwAt = z * 0.31f;

        Parallel.For(0, Side, y =>
        {
            var dy = y - half;
            var row = y * Side * 4;
            for (var x = 0; x < Side; x++)
            {
                var dx = x - half;
                var reachOut = MathF.Sqrt(dx * dx + dy * dy);
                var at = row + x * 4;
                var about = MathF.Atan2(dy, dx);

                // **The rim is thrown outward unevenly.** Growing and
                // shrinking is a balloon; what was asked for is the thing
                // scattering. So the radius is a number per direction,
                // pushed out by the flow at the angle being looked at.
                var scatter = burst <= 0.001f ? 0f
                    : Flow.Fbm(MathF.Cos(about) * 1.7f,
                               MathF.Sin(about) * 1.7f, z * 1.6f) * burst;
                var edge = radius * (1f + scatter);
                var far = reachOut / edge;

                if (far >= 1.02f)
                {
                    Spark(pixels, at, x, y, far, about, hue, spray,
                          throwAt, z);
                    continue;
                }

                // The normal: a ball, not a coin. `face` is the part of it
                // pointing at the eye — one in the middle, nothing at the
                // rim — and the two across are what is left.
                var inside = MathF.Min(far, 1f);
                var face = MathF.Sqrt(MathF.Max(0f, 1f - inside * inside));
                var graze = 1f - face;
                var nx = dx / edge;
                var ny = dy / edge;

                // The surface point, wound about the axis pointing at you.
                var wind = turn + twist * face;
                var cw = MathF.Cos(wind);
                var sw = MathF.Sin(wind);
                var sx = nx * cw - ny * sw;
                var sy = nx * sw + ny * cw;

                // The phase the ribbons run along. Its level lines are
                // spirals: the angle carries it round, the radius carries
                // it outward, and the twist drags the inner turns further
                // than the outer ones.
                var warp = Flow.Fbm(sx * 1.25f, sy * 1.25f,
                                    face * 1.0f + z * 0.9f) * 2.3f;
                var phase = about * 2f + inside * 9.4f + turn * 1.6f
                            + twist / (inside + 0.42f) + warp;

                // Smooth arcs with dark water between them. `sin` rather
                // than the noise itself: noise gives blotches, and what
                // was asked for is bands.
                // Two sets of bands over one another — broad arcs with
                // finer striations inside them. One frequency alone gives
                // corduroy; a real film has structure at more than one
                // size, and that is most of what separates it from a
                // striped ball.
                var wave = MathF.Sin(phase) * 0.5f + 0.5f;
                // A whole multiple, and that is not a taste. The phase
                // carries the angle, which jumps by two full turns where
                // `atan2` wraps; a sine of it comes back to itself across
                // that jump only if its multiplier is a whole number.
                // At 2.7 the finer bands tore a notch down one side of
                // the body — a join in a sphere.
                var fine = MathF.Sin(phase * 3f + 1.1f) * 0.5f + 0.5f;
                var mixed = wave * 0.74f + fine * 0.26f;
                var crest = Math.Clamp((mixed - 0.40f) / 0.30f, 0f, 1f);
                crest *= crest * (3f - 2f * crest);

                // Thin-film colour. **Every term of it has to come back
                // to where it started**, and the first version of this
                // did not: the hue ran along the raw phase, and the phase
                // carries the angle, which jumps by a full turn where
                // `atan2` wraps. The result was a clean coloured seam
                // straight across the body — a join in a sphere, which is
                // the one thing a sphere does not have.
                //
                // So the sweep is carried by the radius, which has no
                // wrap, and the ribbon-to-ribbon difference by the sine
                // of the phase, which is periodic by construction.
                // **A quarter turn out of step with the brightness.**
                // Both used to run off the same sine, so only the half
                // of the spectrum that coincided with a crest was ever
                // lit: the body had a cool half of its range and no warm
                // one, whatever the numbers said it should have. With
                // the cosine, a ribbon passes through the middle of the
                // range at its brightest and takes its two edges with
                // it — which is how a film changes colour across a band
                // rather than between bands.
                // **One-sided, and that is the design speaking.** A
                // symmetric sweep puts a stretch of red a third of the
                // way round from amber, and there is no red in this
                // system — danger is drawn with hatching precisely so
                // that no colour has to mean it. So the film travels
                // from the accent **upward** only: amber into yellow,
                // green, cyan, the near edge of blue. Half a turn of
                // range, and none of it borrowed from a meaning.
                var sweep = MathF.Cos(phase) * 0.5f + 0.5f;
                var shade = hue + inside * Spectrum * 0.40f
                            + sweep * Spectrum * 0.92f
                            + fine * 0.04f + graze * 0.14f + z * 0.01f;

                // Three terms of light over a nearly black core.
                var diffuse = MathF.Max(0f, nx * lightX + ny * lightY
                                            + face * lightZ);
                var spec = MathF.Pow(
                    MathF.Max(0f, nx * hx + ny * hy + face * hz), gloss);
                var rim = graze * graze * graze;

                // The colour lives in a band around the dark middle: a
                // vortex is a hole with light around it, and lighting the
                // whole disc gives a bead.
                // Tight, because a vortex is a hole with light around
                // it. Wide, the colour reaches the middle and the body
                // becomes a bead.
                var band = MathF.Exp(-(inside - 0.74f) * (inside - 0.74f) * 11f);

                var lit = 0.012f
                          + crest * band * (0.14f + 0.90f * diffuse) * 0.98f
                          + diffuse * diffuse * 0.07f
                          + rim * 0.24f
                          + spec * 0.30f;

                // The highlight washes towards white, the way a highlight
                // does: colour belongs to the film, the spot is the light.
                var sat = Math.Clamp(0.58f + 0.20f * crest - spec * 0.50f,
                                     0f, 1f);

                var (red, green, blue) = FromHue(shade, sat,
                                                 Math.Clamp(lit, 0f, 1f));

                // The rim fades, and a little of the body spills past the
                // radius — a hard circle would read as a sticker.
                var alpha = inside < 0.88f ? 1f
                          : Math.Clamp((1.02f - far) / 0.14f, 0f, 1f);

                pixels[at] = blue;
                pixels[at + 1] = green;
                pixels[at + 2] = red;
                pixels[at + 3] = (byte)(alpha * 255);
            }
        });

        _film.WritePixels(new Int32Rect(0, 0, Side, Side), pixels, Side * 4, 0);
    }

    //: How far round the spectrum the film travels over one ribbon.
    //:
    //: The one number that keeps this the project's figure rather than a
    //: free rainbow: the hue starts at the accent and moves from there.
    //: Larger and the bands turn into a colour wheel that belongs to
    //: nobody; smaller and the iridescence goes, and with it the only
    //: reason the body reads as a film at all.
    private const float Spectrum = 0.46f;

    /// <summary>
    /// A mote of the body, thrown clear of it.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Asked for from a picture a person brought: the body throws off a
    /// spray of fine lights, thickest on one side. They are not particles
    /// with a life of their own — there is no list of them anywhere, and
    /// nothing is stepped forward each frame. Each point of the picture
    /// asks a fixed hash whether it is a mote and how bright it is now,
    /// which costs one multiply and no memory, and gives motes that hold
    /// still while the light on them changes.
    /// </para>
    /// <para>
    /// Thickest where the flow is throwing at this instant, and that
    /// direction wanders: dust thrown always to the same side is a
    /// picture of dust.
    /// </para>
    /// </remarks>
    private static void Spark(byte[] pixels, int at, int x, int y, float far,
                              float about, float hue, float spray,
                              float throwAt, float z)
    {
        pixels[at + 3] = 0;
        if (spray <= 0.004f) return;

        var out0 = far - 1f;
        if (out0 > 0.42f) return;

        // Thinning with distance, and thickest on the side being thrown.
        var side = MathF.Cos(about - throwAt * 6.283f) * 0.5f + 0.5f;
        var density = spray * (0.18f + 0.82f * side * side)
                      * MathF.Exp(-out0 * 8f);

        var die = Hash(x, y, 1);
        if (die > density * 0.30f) return;

        // Each mote has a beat of its own, so the spray twinkles rather
        // than switching on and off together.
        var own = Hash(x, y, 2);
        var twinkle = 0.35f + 0.65f
            * (MathF.Sin((z * 5.5f + own * 6.283f)) * 0.5f + 0.5f);

        var shade = hue + own * 0.5f;
        var (red, green, blue) = FromHue(shade, 0.55f,
                                         Math.Clamp(twinkle * 0.9f, 0f, 1f));
        pixels[at] = blue;
        pixels[at + 1] = green;
        pixels[at + 2] = red;
        pixels[at + 3] = (byte)(twinkle * 220f);
    }

    /// <summary>A fixed number in 0..1 for a point. The same every frame.</summary>
    private static float Hash(int x, int y, int salt)
    {
        unchecked
        {
            var h = x * 374761393 + y * 668265263 + salt * 1274126177;
            h = (h ^ (h >> 13)) * 1274126177;
            return ((h ^ (h >> 16)) & 0xFFFF) / 65535f;
        }
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
