using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media.Animation;

namespace Rina.Shell.Styles;

/// <summary>
/// Scrolling that moves instead of jumping (<c>4.0b-E04</c>).
/// </summary>
/// <remarks>
/// <para>
/// A wheel notch in WPF moves the view three lines at once, with nothing
/// in between: the page is in one place and then in another. Asked for by
/// the person using it, and it belongs with the rest of the movement — a
/// jump says "you are somewhere else now" and leaves the eye to find out
/// where; a slide says "you went down", which is what happened.
/// </para>
/// <para>
/// <b>The target is remembered, not read back.</b> Wheel notches come in
/// bursts of three or four, and each one has to add to where the last was
/// heading rather than to where the view has got to so far — otherwise
/// four quick notches move the page by barely more than one, which feels
/// like the wheel slipping.
/// </para>
/// <para>
/// An attached property rather than a class of its own: what is wanted is
/// a line in the markup at the scroller it applies to. It is deliberately
/// not an implicit style — the templates of a dropdown, a text field and a
/// list each carry a scroller inside, and animating those would be
/// changing controls we were not asked about.
/// </para>
/// </remarks>
public static class Smooth
{
    /// <summary>Scroll this viewer by sliding.</summary>
    public static readonly DependencyProperty ScrollingProperty =
        DependencyProperty.RegisterAttached(
            "Scrolling", typeof(bool), typeof(Smooth),
            new PropertyMetadata(false, OnScrolling));

    public static bool GetScrolling(DependencyObject element)
        => (bool)element.GetValue(ScrollingProperty);

    public static void SetScrolling(DependencyObject element, bool value)
        => element.SetValue(ScrollingProperty, value);

    /// <summary>Where the view is heading. Animated; the view follows it.</summary>
    /// <remarks>
    /// WPF has no animatable offset on a scroller — <c>VerticalOffset</c>
    /// is read-only and moved by a method. So the animation runs on a
    /// property of our own, and every value it passes through is handed to
    /// that method.
    /// </remarks>
    private static readonly DependencyProperty GoingToProperty =
        DependencyProperty.RegisterAttached(
            "GoingTo", typeof(double), typeof(Smooth),
            new PropertyMetadata(0.0, (element, changed) =>
            {
                if (element is ScrollViewer view)
                    view.ScrollToVerticalOffset((double)changed.NewValue);
            }));

    //: Where the last notch was heading, per scroller. Kept beside the
    //: control rather than in a dictionary: a dictionary outlives the
    //: pages, and pages here are built afresh on every section change.
    private static readonly DependencyProperty AimedAtProperty =
        DependencyProperty.RegisterAttached(
            "AimedAt", typeof(double), typeof(Smooth),
            new PropertyMetadata(double.NaN));

    private static void OnScrolling(DependencyObject element,
                                    DependencyPropertyChangedEventArgs changed)
    {
        if (element is not ScrollViewer view) return;
        if ((bool)changed.NewValue) view.PreviewMouseWheel += OnWheel;
        else view.PreviewMouseWheel -= OnWheel;
    }

    private static void OnWheel(object sender, MouseWheelEventArgs turned)
    {
        if (sender is not ScrollViewer view) return;
        if (view.ScrollableHeight <= 0) return;

        // Somebody else's scroller inside ours — a list with its own
        // scrolling, say — keeps the notch. Without this, a wheel over an
        // inner list would slide the page behind it instead.
        if (turned.OriginalSource is DependencyObject from
            && Inner(from, view) is not null)
            return;

        turned.Handled = true;

        var aim = (double)view.GetValue(AimedAtProperty);
        // Forgotten when it has gone stale: the view can also be moved by
        // dragging the bar or by a page scrolling itself, and aiming from
        // where a slide was heading a minute ago would jump.
        if (double.IsNaN(aim)
            || Math.Abs(aim - view.VerticalOffset) > view.ViewportHeight)
            aim = view.VerticalOffset;

        // Three lines a notch, as the system's own scrolling does: the
        // movement is what changes here, not how far a notch takes you.
        var step = turned.Delta / 120.0 * 3 * 16;
        aim = Math.Clamp(aim - step, 0, view.ScrollableHeight);
        view.SetValue(AimedAtProperty, aim);

        var span = (Duration)view.FindResource("Motion.Panel");
        var ease = (IEasingFunction)view.FindResource("Ease.In");
        // **Held, not stopped.** `Stop` returns the property to its base
        // value when the slide ends — and the callback dutifully carried
        // the view back there: it slid down and then snapped to the top.
        // `From` is given each time instead, so the next notch starts
        // where the view actually is rather than where the last held
        // value says it should be.
        view.BeginAnimation(GoingToProperty, new DoubleAnimation
        {
            From = view.VerticalOffset,
            To = aim,
            Duration = span,
            EasingFunction = ease,
            FillBehavior = FillBehavior.HoldEnd,
        });
    }

    /// <summary>A scroller of its own between this element and ours.</summary>
    private static ScrollViewer? Inner(DependencyObject from, ScrollViewer ours)
    {
        for (var at = from; at is not null && at != ours;
             at = System.Windows.Media.VisualTreeHelper.GetParent(at))
            if (at is ScrollViewer nested && nested != ours
                && nested.ScrollableHeight > 0)
                return nested;
        return null;
    }
}
