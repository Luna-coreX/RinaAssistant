using System.Text.Json.Nodes;
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
        _figure.Build();

        if (_link is not null)
        {
            _link.CoreEvent += OnCoreEvent;
            _link.Level += OnLevel;
        }
        App.AccentChanged += OnAccentChanged;

        // The remote is the window's, not the page's: the page is rebuilt on
        // every visit, and asking Windows for the media register each time
        // would be a system call for a thing that has not changed.
        // Asked once, when the page appears: a tile is a glance, not a
        // stream, and a plugin that wants to change it says so by the
        // ordinary means — the page is rebuilt on every visit anyway.
        Loaded += async (_, _) => await ShowTilesAsync();

        _remote = App.Remote;
        if (_remote is not null)
        {
            _remote.Changed += ShowPlaying;
            ShowPlaying();
        }

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

    /// <summary>Feed a microphone and a level, without a microphone.</summary>
    /// <remarks>
    /// For the check, and through the real path: this sets exactly what the
    /// events set and then asks <see cref="Settle"/>, so what is checked is
    /// the rule, not a shortcut past it. Whether an open microphone alone
    /// makes her "listening" is the question that was got wrong once, and
    /// it cannot be settled by speaking into a real one.
    /// </remarks>
    public void HearFor(bool open, float level)
    {
        _mic = open;
        if (!open) _heard = 0;
        OnLevel(level);
        Settle();
        ShowDoing();
    }

    private void OnTick(double elapsed, double step)
    {
        if (!_held) Settle();
        _figure.Advance(elapsed, step);
    }

    /// <summary>Work out what she is doing, from what is actually true.</summary>
    /// <remarks>
    /// <para>
    /// Thinking wins, because it is the only one of the four the core
    /// declares outright. Then talking, read from the sound being played —
    /// not from `assistant.response`, which arrives when the text is ready
    /// and would light the figure for the length of a message rather than
    /// of a sentence said aloud.
    /// </para>
    /// <para>
    /// <b>And listening is a voice, not an open microphone.</b> That was
    /// wrong in the first edition: the microphone opens when "always
    /// listening" is switched on or a hotkey is pressed, and it then stays
    /// open for hours. The figure sat in `listening` the whole time and
    /// said nothing about anybody speaking. What it shows now is that
    /// somebody <i>is speaking</i> — the level is above the floor — which
    /// is what a person meant when they asked to see it react when they
    /// start to talk.
    /// </para>
    /// </remarks>
    private void Settle()
    {
        if (_thinking) { Retune(Doing.Thinking); return; }

        var speech = _link?.Speech ?? 0;
        if (_link?.Speaking == true && speech > 0)
        {
            Retune(Doing.Talking, speech);
            return;
        }

        // A floor, and a fall that lags the rise. Speech is not a steady
        // sound — there are gaps between words — and without the lag the
        // figure would drop back to waiting inside every pause.
        _heard *= 0.90;
        if (_mic && _heard > Floor) Retune(Doing.Listening, _heard);
        else Retune(Doing.Idle);
    }

    //: Below this a level is a room, not a voice. Anything lower and the
    //: figure answers the fridge.
    private const double Floor = 0.06;

    private bool _mic;
    private bool _thinking;
    private double _heard;

    private void OnLevel(float level)
    {
        if (level > _heard) _heard = level;
    }

    private void OnCoreEvent(Envelope message)
    {
        switch (message.Method)
        {
            case "listening.capturing":
                // Only whether the microphone is open. Whether anybody is
                // speaking into it is a different question, answered above.
                _mic = message.Payload["active"]?.GetValue<bool>() == true;
                if (!_mic) _heard = 0;
                break;
            case "assistant.thinking":
                _thinking = message.Payload["active"]?.GetValue<bool>() == true;
                break;
        }
    }

    private void Retune(Doing doing, double loud = 0)
    {
        var changed = _figure.State != doing;
        _figure.Show(doing, loud);
        if (changed) ShowDoing();
    }

    private void OnAccentChanged() => _figure.Build();

    private readonly MediaRemote? _remote;

    /// <summary>
    /// Draw what plugins asked to show here.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The same elements as a plugin's own tab, drawn by the same view: a
    /// plugin declares and does not draw (ADR 0010), and having two
    /// renderers would mean two ideas of what a card is.
    /// </para>
    /// <para>
    /// <b>Nothing is shown while there is nothing.</b> Most people have no
    /// plugin that wants a tile, and an empty frame reserved for one is a
    /// hole in the screen.
    /// </para>
    /// </remarks>
    private async Task ShowTilesAsync()
    {
        if (_link is null) return;
        var told = await _link.AskAsync(Methods.PluginsHome);
        Tiles.Items.Clear();

        foreach (var tile in told?["tiles"]?.AsArray() ?? [])
        {
            if (tile is not JsonObject one) continue;
            var id = one["id"]?.GetValue<string>() ?? "";
            if (one["elements"] is not JsonArray elements
                || elements.Count == 0) continue;

            var view = new PluginView(_link, id);
            view.Draw(elements);
            view.Margin = new Thickness(0, 0, 12, 12);
            view.MaxWidth = 208;
            Tiles.Items.Add(view);
        }
    }

    /// <summary>How many tiles are showing — for the check.</summary>
    public int TilesShown => Tiles.Items.Count;

    /// <summary>Draw these tiles, as if the core had offered them.</summary>
    /// <remarks>
    /// The two halves belong to different people, as with the remote.
    /// Whether any plugin wants a tile depends on what is installed and
    /// switched on; drawing what is offered is ours, and it has to be
    /// checkable on a machine with no such plugin. Without this the
    /// assertion read "the core offered none and none were drawn" — true,
    /// and about nothing.
    /// </remarks>
    public void ShowTilesForCheck(JsonArray tiles)
    {
        Tiles.Items.Clear();
        foreach (var tile in tiles)
        {
            if (tile is not JsonObject one) continue;
            if (one["elements"] is not JsonArray elements
                || elements.Count == 0) continue;
            var view = new PluginView(_link, one["id"]?.GetValue<string>() ?? "");
            view.Draw(elements);
            view.MaxWidth = 208;
            Tiles.Items.Add(view);
        }
    }

    /// <summary>
    /// Show what is playing — or nothing at all.
    /// </summary>
    /// <remarks>
    /// Hidden when nothing is playing, rather than shown empty. Most of the
    /// time nothing is, and a panel with three dead buttons and two blank
    /// lines reads as a fault rather than as a rest.
    /// </remarks>
    private void ShowPlaying()
    {
        var playing = _remote?.Playing;
        if (playing is null || playing.Title.Length == 0)
        {
            Remote.Visibility = Visibility.Collapsed;
            return;
        }

        Remote.Visibility = Visibility.Visible;
        Track.Text = playing.Title;
        // Not everything says who: a browser tab often gives a title alone,
        // and an empty line under it would look like something failed to
        // load rather than like something that was never there.
        Artist.Text = playing.Artist;
        Artist.Visibility = playing.Artist.Length > 0
            ? Visibility.Visible : Visibility.Collapsed;
        Cover.Source = playing.Cover;
        Hold.Content = playing.Running ? "\u23F8" : "\u25B6";
    }

    private async void OnPrevious(object sender, RoutedEventArgs e)
    {
        if (_remote is not null) await _remote.Previous();
    }

    private async void OnPlayPause(object sender, RoutedEventArgs e)
    {
        if (_remote is not null) await _remote.PlayPause();
    }

    private async void OnNext(object sender, RoutedEventArgs e)
    {
        if (_remote is not null) await _remote.Next();
    }

    /// <summary>What the remote is showing — for the check.</summary>
    public string RemoteShows => Remote.Visibility == Visibility.Visible
        ? $"{Artist.Text} — {Track.Text}" : "";

    private void ShowDoing() => DoingText.Text = _figure.State switch
    {
        Doing.Listening => S(Word("Слушаю")),
        Doing.Thinking => S(Word("Думаю")),
        Doing.Talking => S(Word("Говорю")),
        _ => S(Word("Жду")),
    };
}
