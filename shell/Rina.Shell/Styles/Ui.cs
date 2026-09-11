using System.Windows;
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
