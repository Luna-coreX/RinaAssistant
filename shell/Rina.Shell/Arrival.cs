using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;

namespace Rina.Shell;

/// <summary>
/// How a window of its own arrives (<c>4.0b-E04</c>).
/// </summary>
/// <remarks>
/// <para>
/// Every separate window used to be simply there: a list, a wizard, a
/// warning, the floating line. Asked for by the person using it —
/// "windows appearing" was one of the four things named — and it is the
/// same rule as everywhere else in the system: movement answers the
/// question "what changed". A window that is suddenly there does not
/// answer it; it leaves the eye to work out whether something appeared or
/// the screen was always like that.
/// </para>
/// <para>
/// One place rather than five. Five copies of a fade would part company at
/// the first change to the duration, and the duration is a token.
/// </para>
/// <para>
/// <b>Deaf until it has arrived.</b> An element at zero opacity in WPF is
/// still hit-testable, so a window fading in over a fifth of a second can
/// take a click meant for what was underneath — and one of these windows
/// is the one that asks about something irreversible. It listens only once
/// it can be seen.
/// </para>
/// </remarks>
internal static class Arrival
{
    /// <summary>Make this window fade and rise into place when it is shown.</summary>
    public static void Animate(Window window)
    {
        if (window.Content is not UIElement content) return;

        var rise = new TranslateTransform();
        content.RenderTransform = rise;
        content.Opacity = 0;
        content.IsHitTestVisible = false;

        window.Loaded += (_, _) =>
        {
            var span = (Duration)window.FindResource("Motion.Panel");
            var ease = (IEasingFunction)window.FindResource("Ease.In");

            // Half a row of travel: enough to read as arriving, not enough
            // to read as sliding in from somewhere. An instrument panel
            // does not travel (SYSTEM §7) — the same reason the section
            // change rises a little rather than sliding across.
            var from = (double)window.FindResource("Size.Row") / 2;
            rise.BeginAnimation(TranslateTransform.YProperty,
                new DoubleAnimation
                {
                    From = from, To = 0, Duration = span,
                    EasingFunction = ease,
                });

            var show = new DoubleAnimation
            {
                From = 0, To = 1, Duration = span, EasingFunction = ease,
            };
            show.Completed += (_, _) => content.IsHitTestVisible = true;
            content.BeginAnimation(UIElement.OpacityProperty, show);
        };
    }
}
