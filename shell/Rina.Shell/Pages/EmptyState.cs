using System.Windows;
using System.Windows.Controls;

namespace Rina.Shell.Pages;

/// <summary>
/// An empty place that explains itself.
/// </summary>
/// <remarks>
/// <para>
/// From the person: "it looks good, but a bit empty". The examination
/// showed it was not about the amount of decoration but about a section
/// with no entries ending in one grey line with three hundred points of
/// emptiness below it. An instrument panel does not look like that: it has
/// no unfilled bottom.
/// </para>
/// <para>
/// <b>An empty state is a reading, not the absence of one.</b> It answers
/// three questions at once: what lives here, why it is empty now, and what
/// to do so it is not. "Nothing is scheduled" answers half of the first.
/// </para>
/// <para>
/// <b>It takes the whole remainder and centres itself in it.</b> An empty
/// state pinned to the top reads as a truncated page; in the middle of the
/// empty space it reads as the state of the instrument.
/// </para>
/// <para>
/// There is no icon. The design direction forbids an icon without a
/// caption, and an icon with a caption here is the caption that is already
/// there.
/// </para>
/// </remarks>
public static class EmptyState
{
    /// <summary>
    /// Build an empty state.
    /// </summary>
    /// <param name="what">What there is none of yet — in one line.</param>
    /// <param name="why">What appears here and where from.</param>
    /// <param name="how">What to say or press. Optional.</param>
    /// <param name="onGlass">
    /// The empty state lies on the glass field rather than on the panel.
    /// </param>
    /// <remarks>
    /// Glass has colours of its own — `GLASS_TEXT` and `GLASS_DIM`. Not
    /// decoration: the pair "ink on glass" does not appear in the contrast
    /// check, because glass and panel are different surfaces, and panel
    /// paint on glass has been verified by nobody.
    /// </remarks>
    public static FrameworkElement For(string what, string why,
                                       string how = "", bool onGlass = false)
    {
        var stack = new StackPanel
        {
            HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Center,
            MaxWidth = 420,
        };

        var bright = onGlass ? Brush("C.GlassText") : Brush("C.Ink");
        var faint = onGlass ? Brush("C.GlassDim") : Brush("C.InkSoft");

        stack.Children.Add(new TextBlock
        {
            Text = what,
            Style = Find("Text.Body"),
            Foreground = bright,
            HorizontalAlignment = HorizontalAlignment.Center,
            TextAlignment = TextAlignment.Center,
        });

        stack.Children.Add(new TextBlock
        {
            Text = why,
            Style = Find("Text.Meta"),
            Foreground = faint,
            TextWrapping = TextWrapping.Wrap,
            TextAlignment = TextAlignment.Center,
            Margin = new Thickness(0, 8, 0, 0),
        });

        if (how.Length > 0)
        {
            // The example is set in the monospaced face: it is what one
            // says or types verbatim, and verbatim things in this system are
            // set in the figure face.
            stack.Children.Add(new TextBlock
            {
                Text = how,
                Style = Find("Text.Figure"),
                Foreground = faint,
                TextWrapping = TextWrapping.Wrap,
                TextAlignment = TextAlignment.Center,
                Margin = new Thickness(0, 16, 0, 0),
            });
        }

        return stack;
    }

    private static Style Find(string key)
        => (Style)Application.Current.FindResource(key);

    private static System.Windows.Media.Brush Brush(string key)
        => (System.Windows.Media.Brush)Application.Current.FindResource(key);
}
