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
    private double _spray;

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
                                0.14 + _loud * 0.25),
            Doing.Thinking => (2.1, 0.04, 2.6, 2.2, 0.16, 240.0, 0.26, 0.06),
            Doing.Talking => (0.9, 0.05 + _loud * 0.16, 1.4, 1.6,
                              0.10 + _loud * 0.55, 70.0 + _loud * 120.0,
                              0.48 + _loud * 0.22, 0.16 + _loud * 0.30),
            _ => (0.35, 0.0, 0.9, 0.8, 0.0, 70.0, 0.42, 0.0),
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
    /// <summary>
    /// One frame of the body (<c>4.0b-E05</c>, fourth edition).
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>The surface is bent, not painted.</b> Every edition before this
    /// one lit the <i>ideal</i> sphere — the normal at each point was the
    /// normal of a perfect ball — and everything else was colour laid on
    /// top. That is why it kept reading as a circle with shadows thrown
    /// over it, which is exactly what it was. Here a height field is
    /// carried on the surface and the normal is bent by its slope, so the
    /// light itself finds the ridges: the highlight breaks into streaks
    /// that run along them, the hollows go dark of their own accord, and
    /// nothing about that is drawn.
    /// </para>
    /// <para>
    /// <b>The slope is measured, not guessed.</b> The field is sampled
    /// three times — here, a step one way across the surface, a step the
    /// other — and the two differences are the gradient. That is the cost
    /// of the whole thing: three readings of the noise instead of one,
    /// and it is what buys a surface instead of a texture.
    /// </para>
    /// <para>
    /// <b>It reflects something.</b> A body this glossy is mostly what is
    /// around it, so there is a room: a cool light above and behind, a
    /// warm one low and to the side, darkness elsewhere. The reflected
    /// direction picks between them. Both lights are the accent's own
    /// colour moved along the spectrum, one up and one down, so the room
    /// belongs to the window it stands in.
    /// </para>
    /// <para>
    /// <b>And the colour splits.</b> The three channels reflect at
    /// slightly different bends, the way glass disperses, which is what
    /// puts the thin coloured fringes on the ridges. One number controls
    /// how far apart they are.
    /// </para>
    /// <para>
    /// The silhouette is displaced too. A perfect circle gives it away
    /// whatever happens inside: the outline is pushed in and out by the
    /// same flow that raises the ridges.
    /// </para>
    /// </remarks>
    private void Paint(float z, float turn, float twist, float burst,
                       float gloss, float lamp, float spray)
    {
        var pixels = _pixels;
        var half = Side / 2f;
        var radius = half * (float)(0.80 + Swell);
        var hue = (float)_hue;

        var spinCos = MathF.Cos(turn);
        var spinSin = MathF.Sin(turn);

        // The room. Cool from above and behind, warm from below and to
        // the side — the two lights a body like this is nearly made of.
        var depth = Math.Clamp(lamp, 0.05f, 0.95f);
        var across = MathF.Sqrt(1f - depth * depth);
        var keyX = -0.62f * across;
        var keyY = -0.74f * across;
        var keyZ = depth;

        // Where the motes are thrown this second, wandering rather than
        // standing still.
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

                // The outline is pushed in and out by the flow. A perfect
                // circle gives the whole thing away however well the
                // inside is lit.
                var swellAt = Flow.Fbm(MathF.Cos(about) * 1.6f,
                                       MathF.Sin(about) * 1.6f,
                                       z * 0.9f, 3);
                var edge = radius * (1f + swellAt * (0.055f + burst));
                var far = reachOut / edge;

                if (far >= 1.0f)
                {
                    Spark(pixels, at, x, y, far, about, hue, spray,
                          throwAt, z);
                    continue;
                }

                // The ideal normal of the ball, before anything is done
                // to it.
                var nx = dx / edge;
                var ny = dy / edge;
                var nz = MathF.Sqrt(MathF.Max(0f, 1f - nx * nx - ny * ny));

                // Into the body's own frame, which turns under the light.
                var px = nx * spinCos + nz * spinSin;
                var pz = -nx * spinSin + nz * spinCos;
                var py = ny;

                // A pair of directions across the surface at this point,
                // to step along when measuring the slope.
                var tLen = MathF.Sqrt(pz * pz + px * px) + 1e-4f;
                var tux = pz / tLen;
                var tuz = -px / tLen;
                var tvx = -px * py / tLen;
                var tvy = (pz * pz + px * px) / tLen;
                var tvz = -py * pz / tLen;

                // The height field, and its slope by two more readings.
                // The twist drags the field round more the deeper into
                // the body you look, so the ridges wind instead of lying
                // in stripes.
                // Coarse and few. Fine noise gives a crust — the first
                // reading of this looked like wet stone — and what is
                // wanted is a handful of large, smooth folds. Two
                // octaves, not four: the detail a height field does not
                // have is detail the light cannot find.
                const float grain = 1.45f;
                const float step = 0.14f;
                float High(float ax, float ay, float az)
                {
                    var wind = twist * 0.5f;
                    var cw = MathF.Cos(wind * az);
                    var sw = MathF.Sin(wind * az);
                    return Flow.Fbm((ax * cw - ay * sw) * grain,
                                    (ax * sw + ay * cw) * grain,
                                    az * grain + z, 2);
                }

                var here = High(px, py, pz);
                var alongU = High(px + tux * step, py, pz + tuz * step);
                var alongV = High(px + tvx * step, py + tvy * step,
                                  pz + tvz * step);
                var slopeU = (alongU - here) / step;
                var slopeV = (alongV - here) / step;

                // The normal, bent by the slope. This is the whole of it:
                // everything below is ordinary lighting of a surface that
                // is genuinely not a sphere any more.
                const float relief = 0.62f;
                var bx = px - relief * (slopeU * tux + slopeV * tvx);
                var by = py - relief * (slopeV * tvy);
                var bz = pz - relief * (slopeU * tuz + slopeV * tvz);
                var bLen = MathF.Sqrt(bx * bx + by * by + bz * bz) + 1e-5f;
                bx /= bLen; by /= bLen; bz /= bLen;

                // Back into view space, where the lights are.
                var mx = bx * spinCos - bz * spinSin;
                var mz = bx * spinSin + bz * spinCos;
                var my = by;

                // Reflected direction, eye straight ahead.
                var dot = mz;                      // m · (0,0,1)
                var rx = 2f * dot * mx;
                var ry = 2f * dot * my;
                var rz = 2f * dot * mz - 1f;

                // Two lights and darkness between them.
                // The cool light is broad — it is most of what the body
                // is made of. The warm one is narrow on purpose: a wide
                // warm light painted the whole lower half of the body
                // brown, which is a globe with two hemispheres, not a
                // thing with gold caught on its ridges.
                var cool = MathF.Max(0f, -ry * 0.62f - rz * 0.30f + 0.52f);
                cool *= cool;
                var glint = MathF.Max(0f, ry * 0.70f + rx * 0.32f + 0.06f);
                var warm = glint * glint;
                warm *= warm * warm * 2.4f;

                var toKey = MathF.Max(0f, mx * keyX + my * keyY + mz * keyZ);
                var sheen = MathF.Pow(toKey, gloss);
                var graze = 1f - MathF.Max(0f, mz);
                var rim = graze * graze * graze;

                var value = 0.018f
                            + cool * 0.78f
                            + warm * 0.70f
                            + toKey * toKey * 0.08f
                            + rim * 0.26f
                            + sheen * 0.50f;

                // The colour of the room, and the fringing. The three
                // channels take slightly different bends, the way glass
                // disperses: that is what draws the thin coloured lines
                // along the ridges.
                // Warm only where it is actually caught: on the narrow
                // light and in the sheen. Everywhere else the body is
                // the cool colour, which is what a glass thing in a dark
                // room looks like.
                var mix = Math.Clamp(warm * 1.5f + sheen * 1.4f, 0f, 1f);
                // Through a curve, so the colour spends little time in
                // the middle of the sweep: a slow crossing puts a green
                // belt round the body, and the two lights are supposed
                // to meet, not blend into a third.
                mix = mix * mix * (3f - 2f * mix);
                // The warm end stops short of the accent itself: at
                // full brightness the accent is orange, and orange next
                // to nothing else reads as red. There is no red here —
                // danger is drawn with hatching so that no colour has to
                // carry it.
                var shade = hue + Spectrum * (1.15f - 0.98f * mix)
                            + slopeU * Fringe;
                var sat = Math.Clamp(0.74f - sheen * 0.72f - mix * 0.16f
                                     - MathF.Abs(slopeV) * 0.06f, 0f, 1f);

                var (red, green, blue) = FromHue(shade, sat,
                                                 Math.Clamp(value, 0f, 1f));

                var alpha = far < 0.93f ? 1f
                          : Math.Clamp((1.0f - far) / 0.07f, 0f, 1f);

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

    //: How far the three channels part company on a ridge.
    //:
    //: Glass disperses, and the thin coloured lines along the crests are
    //: that and nothing else. Larger and the body turns to oil; at zero it
    //: is a grey sculpture with a tinted light on it.
    private const float Fringe = 0.055f;

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
