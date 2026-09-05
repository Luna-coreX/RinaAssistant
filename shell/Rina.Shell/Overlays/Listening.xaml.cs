using System.Windows;
using System.Windows.Media.Animation;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Overlays;

/// <summary>
/// The "listening" plaque, on top of the screen.
/// </summary>
/// <remarks>
/// <para>
/// Noted by a person: in 3.1.0 both "always listen" being on and a call by
/// hotkey were visible on screen; after the move they were not.
/// </para>
/// <para>
/// <b>A microphone working unnoticed is not an interface detail.</b> A
/// person has the right to see that they are being listened to without
/// opening a window and without recalling whether they pressed something
/// half an hour ago. So the plaque stays up for the whole time of
/// listening rather than blinking for a second.
/// </para>
/// <para>
/// <b>Two states, not one.</b> A one-off "listening" comes from a hotkey
/// and lasts a few seconds; "always listening" is a mode, on until it is
/// cancelled. They look different because they mean different things: the
/// first ends by itself, the second does not.
/// </para>
/// <para>
/// Top centre, not a corner: there it is seen without looking away from
/// whatever the person is doing, and it does not argue with notifications
/// in the bottom right.
/// </para>
/// </remarks>
public partial class Listening : Window
{
    private bool _always;

    public Listening()
    {
        InitializeComponent();
    }

    /// <summary>
    /// The "always listening" mode.
    /// </summary>
    /// <remarks>
    /// Needed from outside: one-off listening ends with a
    /// `listening.stopped` event, and the plaque has to go on it — but not
    /// while the mode is on. Otherwise the first recognised phrase would
    /// put out the sign that the microphone is still working.
    /// </remarks>
    public bool Always => _always && IsVisible;

    /// <summary>Is the plaque visible — for the end-to-end check.</summary>
    public bool Visible => IsVisible && Card.Opacity > 0.5;

    /// <summary>What it says — for the end-to-end check.</summary>
    public string Caption => Label.Text;

    /// <summary>
    /// Show it. <paramref name="always"/> is the mode, not one-off listening.
    /// </summary>
    public void Appear(bool always)
    {
        _always = always;
        Label.Text = always ? S("Всегда слушаю") : S("Слушаю…");
        Place();
        if (!IsVisible) Show();

        Card.BeginAnimation(OpacityProperty, new DoubleAnimation(
            Card.Opacity, 1, TimeSpan.FromMilliseconds(140)));
        Pulse();
    }

    /// <summary>Hide it. The "always" mode is not put out this way — only by cancelling.</summary>
    public void Vanish()
    {
        _always = false;
        Dot.BeginAnimation(OpacityProperty, null);
        var fade = new DoubleAnimation(Card.Opacity, 0,
                                       TimeSpan.FromMilliseconds(180));
        fade.Completed += (_, _) => { if (Card.Opacity <= 0.01) Hide(); };
        Card.BeginAnimation(OpacityProperty, fade);
    }

    /// <summary>
    /// The dot breathes while listening goes on.
    /// </summary>
    /// <remarks>
    /// Slower in "always" mode: fast blinking for an hour on end is an
    /// irritant, not a message.
    /// </remarks>
    private void Pulse()
    {
        var beat = new DoubleAnimation(1.0, 0.35, new Duration(
            TimeSpan.FromMilliseconds(_always ? 1600 : 900)))
        {
            AutoReverse = true,
            RepeatBehavior = RepeatBehavior.Forever,
            EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut },
        };
        Dot.BeginAnimation(OpacityProperty, beat);
    }

    private void Place()
    {
        var area = SystemParameters.WorkArea;
        UpdateLayout();
        Left = area.Left + (area.Width - ActualWidth) / 2;
        Top = area.Top + 24;
    }
}
