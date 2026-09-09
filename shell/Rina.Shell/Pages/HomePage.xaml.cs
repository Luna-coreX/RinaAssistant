using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// The home screen: the figure, and what Rina is doing right now.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0b-A07</c>. The screen a person ends up on without
/// choosing it, and the one that has to be worth looking at when there is
/// nothing to read.
/// </para>
/// <para>
/// <b>The page reads events; it does not decide anything.</b> Which state
/// the figure shows follows from what the core says and from whether there
/// is speech of Rina's own left to play. There is no timer here inventing
/// activity: a figure that looks busy while nothing is happening teaches a
/// person to stop believing it, and after that it cannot report anything.
/// </para>
/// <para>
/// <b>Talking is read from the audio, not from a message.</b> The core
/// sends the text of an answer and then the sound of it; the moment she
/// actually stops speaking is the moment the last frame has been played,
/// and only the shell knows that. Taking `assistant.response` for "talking"
/// would light the figure up for the length of a message rather than for
/// the length of a sentence spoken aloud.
/// </para>
/// </remarks>
public partial class HomePage : UserControl
{
    //: There may be no link. This is the page that opens first, before the
    //: core has been raised, and a home screen that cannot be shown without
    //: a connection would leave a person looking at nothing during the very
    //: seconds when they most want to see that something is happening.
    private readonly CoreLink? _link;
    private readonly Figure _figure;

    public HomePage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;
        _figure = new Figure(Face);
        _figure.Build(App.CurrentAccent, Steps);

        if (_link is not null)
        {
            _link.CoreEvent += OnCoreEvent;
            _link.Level += OnLevel;
        }
        App.AccentChanged += OnAccentChanged;

        // The page is built anew on every switch to it, so what it
        // subscribed to has to be let go on the way out. Without this the
        // dead pages went on receiving events and repainting figures that
        // were no longer on screen — invisible, and paid for.
        Unloaded += (_, _) =>
        {
            if (_link is not null)
            {
                _link.CoreEvent -= OnCoreEvent;
                _link.Level -= OnLevel;
            }
            App.AccentChanged -= OnAccentChanged;
            if (_backdrop is not null) _backdrop.Ticked -= OnTick;
        };

        ShowDoing();
    }

    private Backdrop? _backdrop;

    /// <summary>How many stops the flow's palette has, from the tokens.</summary>
    private static int Steps =>
        Application.Current?.TryFindResource("Nebula.Steps") is double count
            ? (int)count : 5;

    /// <summary>Move at the background's pace — see <see cref="Figure"/>.</summary>
    public void FollowClock(Backdrop backdrop)
    {
        _backdrop = backdrop;
        backdrop.Ticked += OnTick;
    }

    /// <summary>What the figure is doing — for the check.</summary>
    public Doing Doing => _figure.State;

    /// <summary>How far the figure has swelled — for the check.</summary>
    public double Swell => _figure.Swell;

    /// <summary>Say what is happening, without waiting for an event.</summary>
    /// <remarks>
    /// <para>
    /// For the check, and for nothing else — the same arrangement as
    /// <see cref="Backdrop.Stillness"/> and for the same reason: whether the
    /// four states look different cannot be found out by waiting for a
    /// person to speak into a microphone.
    /// </para>
    /// <para>
    /// It <b>holds</b>, and it has to. Without holding, the very next frame
    /// put the state back: the tick below decides between talking and idle
    /// from the audio, and with no core there is no audio, so a state set
    /// from outside lived a fiftieth of a second. The check caught that
    /// itself — talking measured the same as idle.
    /// </para>
    /// </remarks>
    public void ShowDoingFor(Doing doing, double level = 0)
    {
        _held = true;
        _figure.Show(doing, level);
        ShowDoing();
    }

    //: Somebody outside is saying what the state is; the audio is not to
    //: argue with them. Never set in the running application.
    private bool _held;

    private void OnTick(double elapsed, double step)
    {
        _figure.Advance(elapsed, step);
        // Talking is not an event: it is the state of the audio, and the
        // audio does not announce itself. Asked once a frame, where the
        // answer is already needed.
        if (!_held && _figure.State is not (Doing.Listening or Doing.Thinking))
            Retune(_link?.Speaking == true ? Doing.Talking : Doing.Idle);
    }

    private void OnLevel(float level)
    {
        if (_figure.State is Doing.Listening)
            _figure.Show(Doing.Listening, level);
    }

    private void OnCoreEvent(Envelope message)
    {
        switch (message.Method)
        {
            case "listening.capturing":
                Retune(message.Payload["active"]?.GetValue<bool>() == true
                       ? Doing.Listening : Doing.Idle);
                break;
            case "assistant.thinking":
                Retune(message.Payload["active"]?.GetValue<bool>() == true
                       ? Doing.Thinking : Doing.Idle);
                break;
        }
    }

    private void Retune(Doing doing)
    {
        if (_figure.State == doing) return;
        _figure.Show(doing);
        ShowDoing();
    }

    private void OnAccentChanged() =>
        _figure.Build(App.CurrentAccent, Steps);

    private void ShowDoing() => DoingText.Text = _figure.State switch
    {
        Doing.Listening => S(Word("Слушаю")),
        Doing.Thinking => S(Word("Думаю")),
        Doing.Talking => S(Word("Говорю")),
        _ => S(Word("Жду")),
    };
}
