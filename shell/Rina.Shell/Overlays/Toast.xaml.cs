using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Threading;

namespace Rina.Shell.Overlays;

/// <summary>
/// Rina's reply on top of the screen — in a window of its own, not a
/// system notification.
/// </summary>
/// <remarks>
/// <para>
/// Noted by a person: in 3.1.0 the reply was shown in its own window;
/// after the move, in a system notification. The difference is not
/// cosmetic.
/// </para>
/// <para>
/// <b>A system notification is mail, not conversation.</b> It goes to the
/// notification centre, waits there, is shown by Windows' rules (including
/// "do not disturb", under which it is not seen at all) and looks like a
/// message from an application. An answer to "what time is it" is not a
/// message from an application but a line in a conversation: it is needed
/// now, for two seconds, and there is no point keeping it.
/// </para>
/// <para>
/// <b>The window does not take focus.</b> <c>ShowActivated=false</c> is
/// mandatory: a person talks to Rina without breaking off their own work,
/// and a window that intercepts typing in someone else's editor is worse
/// than silence.
/// </para>
/// <para>
/// <b>One window, not one per line.</b> A second line replaces the text in
/// the same window and extends its life: a stack of cards in the corner is
/// noise, not conversation.
/// </para>
/// </remarks>
public partial class Toast : Window
{
    private readonly DispatcherTimer _hide = new();

    /// <summary>How long an ordinary line lives.</summary>
    public static readonly TimeSpan Normal = TimeSpan.FromSeconds(6);

    /// <summary>A short one — for "listening", "done" and the like.</summary>
    public static readonly TimeSpan Short = TimeSpan.FromSeconds(2.6);

    public Toast()
    {
        InitializeComponent();
        _hide.Tick += (_, _) => FadeOut();
        // A click hides it: the line has been read, and there is no point
        // waiting for it to go.
        MouseLeftButtonDown += (_, _) => FadeOut();
    }

    /// <summary>What is shown right now — for the end-to-end check.</summary>
    public string Shown => Body.Text;

    /// <summary>
    /// Show a line. A repeat call replaces the text rather than breeding windows.
    /// </summary>
    public void Say(string text, TimeSpan? life = null)
    {
        if (string.IsNullOrWhiteSpace(text)) return;

        Body.Text = text;
        Place();
        if (!IsVisible) Show();

        Card.BeginAnimation(OpacityProperty, new DoubleAnimation(
            Card.Opacity, 1, TimeSpan.FromMilliseconds(140)));
        Slide.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(
            Slide.Y, 0, TimeSpan.FromMilliseconds(140)));

        _hide.Stop();
        _hide.Interval = life ?? Normal;
        _hide.Start();
    }

    /// <summary>Remove at once: the conversation continued in the window.</summary>
    public void Dismiss()
    {
        _hide.Stop();
        FadeOut();
    }

    private void FadeOut()
    {
        _hide.Stop();
        var fade = new DoubleAnimation(Card.Opacity, 0,
                                       TimeSpan.FromMilliseconds(180));
        fade.Completed += (_, _) => { if (Card.Opacity <= 0.01) Hide(); };
        Card.BeginAnimation(OpacityProperty, fade);
        Slide.BeginAnimation(TranslateTransform.YProperty, new DoubleAnimation(
            Slide.Y, 12, TimeSpan.FromMilliseconds(180)));
    }

    /// <summary>
    /// The bottom right corner of the working area.
    /// </summary>
    /// <remarks>
    /// The working area, not the screen: otherwise the window lands under
    /// the taskbar. The margin is the same as for system notifications —
    /// a person already knows where to look.
    /// </remarks>
    private void Place()
    {
        var area = SystemParameters.WorkArea;
        UpdateLayout();
        var height = Card.ActualHeight > 0 ? Card.ActualHeight : 80;
        Left = area.Right - Width - 24;
        Top = area.Bottom - height - 24;
    }
}
