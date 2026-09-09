namespace Rina.Shell;

/// <summary>
/// The flow: fractal noise with its own domain warped by more noise.
/// </summary>
/// <remarks>
/// <para>
/// The arithmetic of the living background (<c>4.0b-A06</c>), pulled out of
/// <see cref="Backdrop"/> when a second thing needed it — the figure on the
/// home screen (<c>4.0b-A07</c>). The figure is the same flow gathered into
/// a disc, and that is the point: one field, seen twice.
/// </para>
/// <para>
/// Pulled out rather than copied. A formula written twice parts company at
/// the first change to it, and does it quietly — both sides go on producing
/// plausible pictures, and only a person sees that the disc and the
/// background stopped being the same substance. The same reason
/// <c>tools/nebula.py</c> is one module and not one per caller.
/// </para>
/// </remarks>
public static class Flow
{
    /// <summary>A value of the field -> a colour of the ramp.</summary>
    public static (byte R, byte G, byte B) Shade(
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
    public static float Fbm(float x, float y, float z)
    {
        var sum = 0f;
        var weight = 0.5f;
        for (var octave = 0; octave < 4; octave++)
        {
            sum += weight * Noise(x, y, z);
            x *= 2.03f;
            y *= 2.03f;
            // Time speeds up with the octaves, but far less than space does.
            // At the same factor the fine detail would boil while the large
            // forms barely moved, and the picture would read as static shapes
            // with static noise crawling over them.
            z *= 1.27f;
            weight *= 0.5f;
        }
        return sum * 2f - 1f;
    }

    /// <summary>Smooth value noise on a three-dimensional lattice.</summary>
    /// <remarks>
    /// <para>
    /// Two coordinates are the place and the third is time, and all three
    /// are interpolated. The third one is the whole point of this method's
    /// second edition.
    /// </para>
    /// <para>
    /// <b>The first edition did not interpolate time at all.</b> It floored
    /// the time coordinate and fed the whole number straight to the hash, so
    /// the field stood perfectly still while time stayed inside one cell of
    /// the lattice and then snapped to an unrelated field when it crossed
    /// into the next. A person watching it saw a jerk every few seconds and
    /// nothing in between, and read that as a low frame rate — which it was
    /// not: every frame was computed, and every frame was identical. The
    /// frames were never the problem, and no amount of raising their number
    /// would have helped.
    /// </para>
    /// </remarks>
    internal static float Noise(float x, float y, float z)
    {
        int xi = (int)MathF.Floor(x), yi = (int)MathF.Floor(y),
            zi = (int)MathF.Floor(z);
        float xf = x - xi, yf = y - yi, zf = z - zi;

        // Smoothstep on all three axes: linear interpolation leaves the
        // lattice visible as a grid of creases — in space as a mesh, in
        // time as a pulse.
        float u = xf * xf * (3 - 2 * xf);
        float v = yf * yf * (3 - 2 * yf);
        float w = zf * zf * (3 - 2 * zf);

        float near = Plane(xi, yi, zi, u, v);
        float far = Plane(xi, yi, zi + 1, u, v);
        return near * (1 - w) + far * w;
    }

    /// <summary>One time-slice of the lattice, interpolated in place.</summary>
    private static float Plane(int xi, int yi, int zi, float u, float v)
    {
        float c00 = Hash(xi, yi, zi);
        float c10 = Hash(xi + 1, yi, zi);
        float c01 = Hash(xi, yi + 1, zi);
        float c11 = Hash(xi + 1, yi + 1, zi);
        return (c00 * (1 - u) + c10 * u) * (1 - v)
             + (c01 * (1 - u) + c11 * u) * v;
    }

    /// <summary>A repeatable number in [0, 1) from three whole coordinates.</summary>
    private static float Hash(int x, int y, int z)
    {
        unchecked
        {
            var n = x * 374761393 + y * 668265263 + z * 1274126177;
            n = (n ^ (n >> 13)) * 1274126177;
            return ((n ^ (n >> 16)) & 0x7fffffff) / (float)0x7fffffff;
        }
    }

}
