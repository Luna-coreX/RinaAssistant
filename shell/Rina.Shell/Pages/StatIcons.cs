using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;

namespace Rina.Shell.Pages;

/// <summary>
/// The pictures a plugin's figure may carry (<c>4.0b-K06</c>).
/// </summary>
/// <remarks>
/// <para>
/// Drawn here, in the window's own ink, from a closed list of names
/// (<c>plugins/page_spec.py::ICONS</c>): a plugin says "rain", and what rain
/// looks like is the shell's to decide. A plugin shipping pictures would put
/// another hand's drawing in the middle of this one, and a picture taken from
/// a file would be one more thing arriving from another process.
/// </para>
/// <para>
/// Line drawings on a 24×24 grid, round caps and joins, one weight — the same
/// manner as the window's marks. An unknown name draws nothing, rather than
/// something broken.
/// </para>
/// </remarks>
public static class StatIcons
{
    // The pieces, in grid units. The cloud has two heights: alone it sits
    // in the middle; with something falling from it, it sits higher.
    private const string Cloud =
        "M 7.5,18 H 17 A 3.5,3.5 0 0 0 17.4,11.03 A 5.5,5.5 0 1 0 6.9,10.2 "
        + "A 4,4 0 1 0 7.5,18 Z";
    private const string CloudHigh =
        "M 7.5,15 H 17 A 3.5,3.5 0 0 0 17.4,8.03 A 5.5,5.5 0 1 0 6.9,7.2 "
        + "A 4,4 0 1 0 7.5,15 Z";
    private const string Sun =
        "M 16,12 A 4,4 0 1 1 8,12 A 4,4 0 1 1 16,12 Z "
        + "M 12,2.5 V 4.5 M 12,19.5 V 21.5 M 2.5,12 H 4.5 M 19.5,12 H 21.5 "
        + "M 5.3,5.3 L 6.7,6.7 M 17.3,17.3 L 18.7,18.7 "
        + "M 5.3,18.7 L 6.7,17.3 M 17.3,6.7 L 18.7,5.3";
    private const string Moon =
        "M 19,14.5 A 7.5,7.5 0 1 1 9.5,5 A 6,6 0 0 0 19,14.5 Z";
    // A small sun or moon peeking out from behind a cloud.
    private const string SunBehind =
        "M 10.2,7.6 A 2.8,2.8 0 1 0 5.5,9.8 "
        + "M 7.5,2.5 V 3.6 M 2.5,7.5 H 3.6 M 3.9,3.9 L 4.7,4.7 M 11.1,3.9 L 10.3,4.7";
    private const string MoonBehind =
        "M 10.8,7.8 A 4,4 0 1 1 5.2,3.2 A 3.2,3.2 0 0 0 10.8,7.8";
    private const string PartlyCloud =
        "M 9,20 H 18 A 3,3 0 0 0 18.3,14.03 A 4.6,4.6 0 0 0 9.5,13.3 "
        + "A 3.4,3.4 0 0 0 9,20 Z";
    private const string Rain = "M 8.5,17.5 L 7.5,20.5 M 12.5,17.5 L 11.5,20.5 M 16.5,17.5 L 15.5,20.5";
    private const string Drizzle = "M 8.5,18.5 V 18.6 M 12.5,19.5 V 19.6 M 16.5,18.5 V 18.6 M 10.5,21 V 21.1 M 14.5,21 V 21.1";
    private const string Snow =
        "M 8.5,17.5 V 20.5 M 7.2,18.25 L 9.8,19.75 M 7.2,19.75 L 9.8,18.25 "
        + "M 15.5,17.5 V 20.5 M 14.2,18.25 L 16.8,19.75 M 14.2,19.75 L 16.8,18.25";
    private const string Bolt = "M 12.8,15.5 L 10.6,19 H 13.4 L 11.2,22.5";
    private const string Fog = "M 4,8.5 H 20 M 3,12.5 H 21 M 5,16.5 H 19 M 7,20.5 H 17";

    private static readonly Dictionary<string, string> Drawings = new()
    {
        ["clear"] = Sun,
        ["clear_night"] = Moon,
        ["partly"] = SunBehind + " " + PartlyCloud,
        ["partly_night"] = MoonBehind + " " + PartlyCloud,
        ["cloudy"] = Cloud,
        ["fog"] = Fog,
        ["drizzle"] = CloudHigh + " " + Drizzle,
        ["rain"] = CloudHigh + " " + Rain,
        ["snow"] = CloudHigh + " " + Snow,
        ["storm"] = CloudHigh + " " + Bolt,
    };

    //: Currencies are their own sign in a ring: a picture of a coin would
    //: say less than the sign everybody already reads.
    private static readonly Dictionary<string, string> Signs = new()
    {
        ["dollar"] = "$",
        ["euro"] = "€",
    };

    /// <summary>The picture for a name, or null for a name not on the list.</summary>
    public static FrameworkElement? For(string name, double size,
                                        FrameworkElement owner)
    {
        var ink = (Brush)owner.FindResource("C.Ink");
        if (Drawings.TryGetValue(name, out var data))
        {
            var path = new Path
            {
                Data = Geometry.Parse(data),
                Stroke = ink,
                StrokeThickness = 1.6,
                StrokeStartLineCap = PenLineCap.Round,
                StrokeEndLineCap = PenLineCap.Round,
                StrokeLineJoin = PenLineJoin.Round,
                Width = 24,
                Height = 24,
            };
            return new Viewbox { Child = new Canvas { Width = 24, Height = 24, Children = { path } },
                                 Width = size, Height = size };
        }
        if (Signs.TryGetValue(name, out var sign))
            return new Border
            {
                Width = size * 0.82,
                Height = size * 0.82,
                CornerRadius = new CornerRadius(size),
                BorderBrush = ink,
                BorderThickness = new Thickness(1.6),
                Child = new TextBlock
                {
                    Text = sign,
                    Foreground = ink,
                    FontSize = size * 0.42,
                    HorizontalAlignment = HorizontalAlignment.Center,
                    VerticalAlignment = VerticalAlignment.Center,
                },
            };
        return null;
    }

    /// <summary>The names drawn here — for the check against the plugin side.</summary>
    public static IEnumerable<string> Names => Drawings.Keys.Concat(Signs.Keys);
}
