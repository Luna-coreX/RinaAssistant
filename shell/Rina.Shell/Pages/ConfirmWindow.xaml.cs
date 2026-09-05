using System.Windows;
using System.Windows.Threading;

namespace Rina.Shell.Pages;

/// <summary>What the person decided.</summary>
public enum Consent
{
    /// <summary>Agreed explicitly.</summary>
    Granted,
    /// <summary>Refused explicitly.</summary>
    Refused,
    /// <summary>Did not answer in time — the same as a refusal.</summary>
    Expired,
}

/// <summary>
/// The confirmation window: one point for every dangerous action.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-F11</c>; §11 of the spec.
/// </para>
/// <para>
/// <b>A preview is shown, not the name of the action.</b> "The computer
/// will be shut down immediately" is something a person has time to take
/// in; <c>power_action</c> means nothing. This is a direct requirement of
/// §11, and the text comes from the core: only it knows what will actually
/// happen.
/// </para>
/// <para>
/// <b>Refusal by default.</b> No answer in time means "no". Not "keep
/// waiting" and not "silence means consent": silence may mean nobody saw
/// the window at all.
/// </para>
/// <para>
/// <b>Closing the window is the same as refusing.</b> The close button,
/// Escape and "Cancel" do one and the same thing, because a person who
/// closes a window asking about a dangerous action is quite certainly not
/// agreeing.
/// </para>
/// </remarks>
public partial class ConfirmWindow : Window
{
    private readonly DispatcherTimer _timer = new()
    {
        Interval = TimeSpan.FromSeconds(1),
    };
    private DateTimeOffset _deadline;

    /// <summary>The person's decision. Refusal until they answer.</summary>
    public Consent Result { get; private set; } = Consent.Expired;

    /// <summary>Whether the question has a deadline. Without one the window waits as long as it takes.</summary>
    public bool Timed { get; }

    /// <param name="ttlSeconds">
    /// How many seconds to wait for an answer. <b>Zero or less — wait
    /// without a deadline.</b>
    /// </param>
    /// <remarks>
    /// <para>
    /// Not every question needs a deadline. It exists for what was started
    /// <b>by voice</b>: the person said "shut down the computer", walked
    /// away, and the window must not hang there until morning — silence
    /// then means "no".
    /// </para>
    /// <para>
    /// A question the person opened themselves by pressing something is a
    /// different matter: they are sitting in front of the screen and
    /// already looking at the window. A deadline here would mean the window
    /// disappearing while they read — and that is exactly what happened
    /// with "Reset settings": `Math.Max(ttl, 1)` turned the zero that was
    /// passed into one second, and the window vanished before it could be
    /// read.
    /// </para>
    /// </remarks>
    public ConfirmWindow(string preview, string reason, int ttlSeconds)
    {
        InitializeComponent();
        Preview.Text = preview;
        Reason.Text = reason;

        Timed = ttlSeconds > 0;
        if (Timed)
        {
            _deadline = DateTimeOffset.UtcNow.AddSeconds(ttlSeconds);
            _timer.Tick += OnTick;
            _timer.Start();
            Tick();
        }
        else
        {
            // There is no reading, so we do not hold space for one: an
            // empty cell where the counter goes would read as "something is
            // about to appear here".
            Countdown.Visibility = Visibility.Collapsed;
            // Without a deadline "did not answer" is impossible, so the
            // default refusal is a different one: the window was closed —
            // they refused.
            Result = Consent.Refused;
        }

        // Dangerous things are not confirmed out of momentum: focus is on
        // the refusal, not on the action. Space and Enter then refuse, and
        // an accidental press breaks nothing.
        Loaded += (_, _) => Refuse.Focus();
        Closed += (_, _) => _timer.Stop();
    }

    private void OnTick(object? sender, EventArgs e) => Tick();

    private void Tick()
    {
        var left = _deadline - DateTimeOffset.UtcNow;
        if (left <= TimeSpan.Zero)
        {
            Result = Consent.Expired;
            _timer.Stop();
            Close();
            return;
        }
        // Monospaced digits and a constant width: an instrument reading
        // must not twitch once a second (§3 of the design system).
        Countdown.Text = $"{(int)left.TotalMinutes:00}:{left.Seconds:00}";
    }

    private void OnConfirm(object sender, RoutedEventArgs e)
    {
        Result = Consent.Granted;
        Close();
    }

    private void OnRefuse(object sender, RoutedEventArgs e)
    {
        Result = Consent.Refused;
        Close();
    }

    /// <summary>The question closed itself: the person answered by voice.</summary>
    public void Withdraw()
    {
        Result = Consent.Expired;
        Close();
    }
}
