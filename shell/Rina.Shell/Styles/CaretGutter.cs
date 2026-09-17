using System;
using System.Windows;

namespace Rina.Shell.Styles;

/// <summary>The caret's own gutter, added to a field's padding.</summary>
/// <remarks>
/// <para>
/// A `TextBox` draws its text two device-independent pixels in from
/// where its padding ends — room the caret stands in. A hint drawn
/// as a `TextBlock` has no such room, so the two started two pixels
/// apart even after the padding itself was sorted out: measured at
/// twelve against fourteen.
/// </para>
/// <para>
/// Two, and named here once. Writing it into the markup would put a
/// number nobody can explain next to a padding that comes from the
/// scale; `check-fields` measures both positions, so if WPF ever
/// changes the gutter the check says so rather than the eye.
/// </para>
/// </remarks>
public sealed class CaretGutter : System.Windows.Data.IValueConverter
{
    public const double Pixels = 2.0;

    public object Convert(object value, Type target, object parameter,
                          System.Globalization.CultureInfo culture)
        => value is Thickness pad
            ? new Thickness(pad.Left + Pixels, pad.Top, pad.Right,
                            pad.Bottom)
            : value;

    public object ConvertBack(object value, Type target, object parameter,
                              System.Globalization.CultureInfo culture)
        => throw new NotSupportedException();
}
