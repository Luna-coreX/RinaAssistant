using System.Windows;
using System.Windows.Controls;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// A section stub: a heading and an honest admission that there is no
/// content yet.
/// </summary>
/// <remarks>
/// The real pages are <c>4.0-F04</c>. The stub is not here "so that
/// something is": it verifies the very thing <c>F03</c> was written for —
/// that the window routes and a section draws itself. An empty pane would
/// not have shown that.
/// </remarks>
public static class Placeholder
{
    public static UIElement For(string title)
    {
        var stack = new StackPanel();
        stack.Children.Add(new TextBlock
        {
            Text = title,
            Style = (Style)Application.Current.FindResource("Text.Title"),
        });
        stack.Children.Add(new TextBlock
        {
            Text = S("Раздел появится в 4.0-F04."),
            Style = (Style)Application.Current.FindResource("Text.Body"),
            Margin = new Thickness(0, 16, 0, 0),
        });
        return stack;
    }
}
