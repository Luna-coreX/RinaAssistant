using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Rina.Shell.Styles;

/// <summary>
/// Small properties the standard controls do not have.
/// </summary>
/// <remarks>
/// <para>
/// The first was the hint inside a field. Made an attached property
/// rather than thirteen hand-made overlays on top of thirteen fields:
/// overlays drift apart, while a property works everywhere the field is
/// drawn by our style.
/// </para>
/// <para>
/// <b>A hint is not a value.</b> It goes out the moment text appears in the
/// field, and it takes no part in saving or validation. A field where the
/// hint pretends to be a value is a way to one day save the words
/// "for example, C:\Program Files" as a path.
/// </para>
/// </remarks>
public static class Ui
{
    /// <summary>What to show in an empty field.</summary>
    public static readonly DependencyProperty HintProperty =
        DependencyProperty.RegisterAttached(
            "Hint", typeof(string), typeof(Ui),
            new PropertyMetadata(""));

    public static string GetHint(DependencyObject element)
        => (string)element.GetValue(HintProperty);

    public static void SetHint(DependencyObject element, string value)
        => element.SetValue(HintProperty, value);

    /// <summary>
    /// The space between things standing in a row.
    /// </summary>
    /// <remarks>
    /// <para>
    /// WPF has no gap on a panel, so every row of buttons in this
    /// program was written without one and every row of buttons was
    /// stuck together — «Экспорт|Очистить», «Новая команда|Импорт|
    /// Экспорт», and so on down almost every page. Noticed by the
    /// person using it, on a screenshot where the two buttons read as
    /// one wide one with a line through it.
    /// </para>
    /// <para>
    /// A property on the panel rather than a margin on each child: a
    /// margin has to be left off the last one, which is a thing to
    /// remember every time a button is added and a thing nobody
    /// remembers. Here the panel spaces whatever it happens to
    /// contain, including what is added later.
    /// </para>
    /// </remarks>
    public static readonly DependencyProperty GapProperty =
        DependencyProperty.RegisterAttached(
            "Gap", typeof(double), typeof(Ui),
            new PropertyMetadata(0.0, OnGapChanged));

    public static double GetGap(DependencyObject element)
        => (double)element.GetValue(GapProperty);

    public static void SetGap(DependencyObject element, double value)
        => element.SetValue(GapProperty, value);

    private static void OnGapChanged(DependencyObject where,
                                     DependencyPropertyChangedEventArgs e)
    {
        if (where is not Panel panel) return;
        panel.Loaded -= SpaceOut;
        panel.Loaded += SpaceOut;
        if (panel.IsLoaded) SpaceOut(panel, new RoutedEventArgs());
    }

    private static void SpaceOut(object sender, RoutedEventArgs e)
    {
        if (sender is not Panel panel) return;
        var gap = GetGap(panel);
        if (gap <= 0) return;
        // Down the column or along the row, whichever this panel is.
        // A `StackPanel` says so itself; anything else is laid out
        // side by side often enough that a row is the safe guess.
        var sideways = panel is not StackPanel stack
                       || stack.Orientation == Orientation.Horizontal;
        var seen = panel.Children.OfType<FrameworkElement>()
                        .Where(child => child.Visibility != Visibility.Collapsed)
                        .ToList();
        for (var i = 0; i < seen.Count; i++)
        {
            var last = i == seen.Count - 1;
            var was = seen[i].Margin;
            // Only the side this panel stacks along, and only what was
            // not set by hand: a child with its own margin asked for
            // it, and taking that away would move something somebody
            // placed deliberately.
            seen[i].Margin = sideways
                ? new Thickness(was.Left, was.Top,
                                last ? was.Right : Math.Max(was.Right, gap),
                                was.Bottom)
                : new Thickness(was.Left, was.Top, was.Right,
                                last ? was.Bottom : Math.Max(was.Bottom, gap));
        }
    }

    /// <summary>What a button is washed with under the pointer.</summary>
    /// <remarks>
    /// <para>
    /// A property rather than a second template, because a template is
    /// sixty lines of arrangement and the arrangement is the same: what
    /// differs between an ordinary button and the primary one is a colour.
    /// A copied template is two places to fix the next time the button
    /// changes, and one of them always gets missed.
    /// </para>
    /// <para>
    /// It exists because the general highlight is the panel's own face, and
    /// the primary button's face is ink: laying the panel over it left its
    /// text — the panel's colour — on the panel's colour, at a contrast of
    /// 1.1 where 4.5 is needed. Noticed by the person using it, on a white
    /// button whose black text went black-on-dark under the pointer.
    /// </para>
    /// </remarks>
    public static readonly DependencyProperty WarmProperty =
        DependencyProperty.RegisterAttached(
            "Warm", typeof(Brush), typeof(Ui), new PropertyMetadata(null));

    public static Brush? GetWarm(DependencyObject element)
        => (Brush?)element.GetValue(WarmProperty);

    public static void SetWarm(DependencyObject element, Brush? value)
        => element.SetValue(WarmProperty, value);

    /// <summary>And what it is washed with while it is held down.</summary>
    public static readonly DependencyProperty SunkProperty =
        DependencyProperty.RegisterAttached(
            "Sunk", typeof(Brush), typeof(Ui), new PropertyMetadata(null));

    public static Brush? GetSunk(DependencyObject element)
        => (Brush?)element.GetValue(SunkProperty);

    public static void SetSunk(DependencyObject element, Brush? value)
        => element.SetValue(SunkProperty, value);
}
