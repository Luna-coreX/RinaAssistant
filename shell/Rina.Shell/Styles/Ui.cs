using System.Windows;

namespace Rina.Shell.Styles;

/// <summary>
/// Small properties the standard controls do not have.
/// </summary>
/// <remarks>
/// <para>
/// So far there is one — the hint inside a field. Made an attached property
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
}
