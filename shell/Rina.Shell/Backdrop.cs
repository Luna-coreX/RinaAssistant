using System.Windows;
using System.Windows.Media;
using System.Windows.Threading;

namespace Rina.Shell;

/// <summary>
/// The living background: a panel lit from a slowly moving direction.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0b-A06</c>. What moves is the light, not a picture: the
/// sheen gradient of the current finish drifts across the face at a period
/// measured in tens of seconds. It is deliberately below the threshold of
/// noticing — a background that catches the eye is a background that gets
/// switched off.
/// </para>
/// <para>
/// <b>It stops, and stopping is part of the task rather than an
/// optimisation afterwards.</b> Usage mode number one is "in the
/// background while working, the window minimised or in the tray"
/// (<c>4.0-R01</c>). A window the person cannot see has no right to turn
/// frames: an invisible animation is a fan running all day for nothing.
/// </para>
/// <para>
/// <b>A timer rather than a WPF animation, for exactly that reason.</b> A
/// <c>Storyboard</c> with <c>RepeatBehavior.Forever</c> goes on ticking
/// while the window is hidden — WPF has no reason to think otherwise. Here
/// stopping is the point, so the clock is ours and can be stopped.
/// </para>
/// <para>
/// <b>Reduced motion is obeyed.</b> A person who asked the system to show
/// fewer animations meant it: for some people a moving background brings on
/// a headache. Then the backdrop is a single static frame of the same
/// finish — it does not disappear, because the depth is not the movement.
/// </para>
/// </remarks>
public sealed class Backdrop
{
    private readonly FrameworkElement _target;
    private readonly DispatcherTimer _clock = new();
    private readonly TranslateTransform _drift = new();

    private double _period = 24;
    private double _amplitude = 0.06;
    private bool _visible;

    public Backdrop(FrameworkElement target)
    {
        _target = target;
        _target.RenderTransform = _drift;

        _period = Token("Background.Period", 24);
        _amplitude = Token("Background.Amplitude", 0.06);
        var fps = Token("Background.Fps", 30);

        _clock.Interval = TimeSpan.FromMilliseconds(1000.0 / Math.Max(1, fps));
        _clock.Tick += (_, _) => Advance();

        // Windows says when its own settings change, and "show animations
        // in windows" is one of them. Without this, lifting reduced motion
        // would leave the background standing until the window was touched
        // — the same "eventually" as above, only the other way round.
        SystemParameters.StaticPropertyChanged += (_, _) => Settle();
        Asked += Settle;
        Render();
    }

    /// <summary>How far along its period the drift is, in [0, 1).</summary>
    /// <remarks>
    /// Public because it is the only honest way to check that the backdrop
    /// stopped. "It is not moving" cannot be seen in a screenshot, and a
    /// check that measures whether the timer object exists would agree with
    /// its author. This is measured across time: the phase advances while
    /// it runs and stands still while it does not.
    /// </remarks>
    public double Phase { get; private set; }

    /// <summary>Is the clock ticking right now.</summary>
    public bool Running => _clock.IsEnabled;

    /// <summary>
    /// Does the system want less movement.
    /// </summary>
    /// <remarks>
    /// <c>ClientAreaAnimation</c> is Windows' own "show animations in
    /// windows" switch. It is what a person turns off, and it is what we
    /// obey — inventing a setting of our own beside it would mean asking
    /// twice about one thing.
    /// </remarks>
    public static bool WantsStillness =>
        Stillness ?? !SystemParameters.ClientAreaAnimation;

    /// <summary>Answer the question above without asking the system.</summary>
    /// <remarks>
    /// For the motion check, and only for it. Whether reduced motion is
    /// obeyed is a branch that depends on the developer's own Windows
    /// setting: on a machine with animations on, the branch is never
    /// reached, and a check that cannot reach it checks half. Breaking the
    /// obedience deliberately proved exactly that — the check stayed green.
    ///
    /// `null` means "ask the system", and that is what it is in the
    /// application.
    /// </remarks>
    public static bool? Stillness
    {
        get => _stillness;
        set
        {
            _stillness = value;
            Asked?.Invoke();
        }
    }

    private static bool? _stillness;

    /// <summary>Somebody changed <see cref="Stillness"/>.</summary>
    /// <remarks>
    /// The override has to reach a running backdrop the same way the real
    /// setting does, or the check would be exercising a path the
    /// application does not have.
    /// </remarks>
    private static event Action? Asked;

    /// <summary>
    /// Run or stop, to match whether there is anybody to look.
    /// </summary>
    /// <remarks>
    /// One method for both, because the caller has one thing to say: is the
    /// window visible to a person right now. Two methods would let a caller
    /// start twice and stop once.
    /// </remarks>
    public void Follow(bool visible)
    {
        _visible = visible;
        Settle();
    }

    /// <summary>Bring the clock into line with both of its reasons.</summary>
    /// <remarks>
    /// There are two inputs — whether anybody is looking, and whether the
    /// system was asked for less movement — and they change independently.
    /// The first edition consulted the second only inside <c>Follow</c>,
    /// which the window calls on its own events: a person switching
    /// animations off in Windows kept a moving background until they next
    /// activated the window. The promise was kept eventually, and
    /// "eventually" is not what it says.
    /// </remarks>
    private void Settle()
    {
        var wanted = _visible && !WantsStillness;
        if (wanted == Running) return;
        if (wanted) _clock.Start();
        else _clock.Stop();
    }

    private void Advance()
    {
        // Stillness can be asked for while we are running, and then this is
        // where we hear about it: one tick late at most.
        if (WantsStillness)
        {
            Settle();
            return;
        }

        // A fraction of the period per tick, from the interval rather than
        // from a count of ticks: a tick that arrived late must move the
        // drift further, or the movement slows down under load instead of
        // keeping its promised period.
        Phase = (Phase + _clock.Interval.TotalSeconds / _period) % 1.0;
        Render();
    }

    private void Render()
    {
        // A whole revolution, so the end meets the beginning: a drift that
        // jumped back at the end of its period would be the one thing about
        // it a person does notice.
        var span = _target.ActualHeight > 0 ? _target.ActualHeight : 600;
        _drift.Y = Math.Sin(Phase * 2 * Math.PI) * span * _amplitude;
        _drift.X = Math.Cos(Phase * 2 * Math.PI) * span * _amplitude * 0.5;
    }

    private static double Token(string key, double fallback) =>
        Application.Current?.TryFindResource(key) is double value
            ? value : fallback;
}
