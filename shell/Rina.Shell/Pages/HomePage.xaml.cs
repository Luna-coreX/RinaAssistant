using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
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
        Greeting.Text = Openings[Today]();
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

        // What the list is laid over, blurred, so the panel is see-through
        // without cutting the figure off at its edge (4.0b-E02). The flow
        // behind it is added later, when the background arrives.
        Glaze.Follow(TodoOver, Screen, (double)FindResource("Glass.Blur"));

        // The glass under the list hangs out past the panel on every side —
        // a blur fades where its element ends, and without the overhang the
        // fade showed as a pale rim all the way round. It is cut back here
        // and not by the border: a border rounds its own line and does not
        // clip what stands inside it, so the three points of corner have to
        // be taken off by hand.
        TodoRoom.SizeChanged += (_, _) =>
        {
            var round = ((CornerRadius)FindResource("Radius.Max")).TopLeft;
            TodoRoom.Clip = new RectangleGeometry(
                new Rect(0, 0, TodoRoom.ActualWidth, TodoRoom.ActualHeight),
                round, round);
        };

        ShowDoing();
    }

    private Backdrop? _backdrop;

    /// <summary>Move at the background's pace — see <see cref="Figure"/>.</summary>
    public void FollowClock(Backdrop backdrop)
    {
        _backdrop = backdrop;
        backdrop.Ticked += OnTick;

        // The list of things to do lies over this screen, so it is glass and
        // shows the flow through it (4.0b-E02). Asked of the background
        // rather than of the window: the page is handed the flow already,
        // and a page that reaches up to its window is the first step back
        // towards the god object.
        Glaze.Follow(TodoGlass, backdrop.Under,
                     (double)FindResource("Glass.Blur"));
    }

    /// <summary>What the figure is doing — for the check.</summary>
    public Doing Doing => _figure.State;

    /// <summary>How far the figure has swelled — for the check.</summary>
    public double Swell => _figure.Swell;

    /// <summary>The figure's cheapest frame, in milliseconds — for the check.</summary>
    public double FigureFrameMs => _figure.BestFrameMs;

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

    /// <summary>
    /// The lines Rina opens with.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Kept by the shell rather than by the core, and that is the same
    /// boundary as everywhere: this is not something Rina says — nothing
    /// is spoken, and the core may not even be up when the home screen
    /// draws — it is something the screen shows. What she says is the
    /// core's; what is written on a panel is the shell's.
    /// </para>
    /// <para>
    /// <b>One per run, not one per visit.</b> Chosen when the program
    /// starts and kept: a line that changed every time somebody came
    /// back to the home screen would be a thing moving in the corner of
    /// the eye, which is the opposite of filling an emptiness.
    /// </para>
    /// </remarks>
    private static readonly Func<string>[] Openings =
    [
        () => S("Чем могу помочь?"),
        () => S("С чего начнём?"),
        () => S("Я вас слушаю."),
        () => S("Что сделаем сегодня?"),
        () => S("Готова помочь."),
        () => S("Скажите — или напишите."),
    ];

    private static readonly int Today = Random.Shared.Next(Openings.Length);

    /// <summary>What is written over the figure — for the check.</summary>
    public string Opening => Greeting.Text;

    /// <summary>Hide the opening — for the check.</summary>
    /// <remarks>
    /// The figure is measured against the ring of screen around it, and
    /// this line stands inside that ring. Words in the sample make the
    /// reading a reading of the words.
    /// </remarks>
    public void BareForCheck() => Greeting.Visibility = Visibility.Collapsed;

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
            Ticking(false);
            return;
        }

        Remote.Visibility = Visibility.Visible;
        Ticking(true);
        Track.Text = playing.Title;
        // Not everything says who: a browser tab often gives a title alone,
        // and an empty line under it would look like something failed to
        // load rather than like something that was never there.
        Artist.Text = playing.Artist;
        Artist.Visibility = playing.Artist.Length > 0
            ? Visibility.Visible : Visibility.Collapsed;
        ShowLine();
        Hold.Content = playing.Running ? "\u23F8" : "\u25B6";
    }

    /// <summary>
    /// The length, and where in it we are.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Redrawn on a tick rather than on an event: the register reports a
    /// position when the source volunteers one, and a bar that waits for
    /// that stands still and then jumps a handful of seconds. Half a
    /// second is fast enough that the movement reads as movement and
    /// cheap enough to cost nothing.
    /// </para>
    /// <para>
    /// <b>Not touched while a person is dragging it.</b> A tick that
    /// writes the playing position into the slider under a moving hand
    /// pulls the thumb out from under it, which feels like the interface
    /// arguing.
    /// </para>
    /// </remarks>
    private void ShowLine()
    {
        var spot = _remote?.Where();
        if (spot is null)
        {
            // A live stream, or a browser tab that gives a title and
            // nothing else. A bar with no end to it is a bar that lies.
            Line.Visibility = Visibility.Collapsed;
            return;
        }

        Line.Visibility = Visibility.Visible;
        Seek.IsEnabled = spot.Seekable;
        Length.Text = Clocked(spot.Length);
        if (_scrubbing) return;

        _writing = true;
        Seek.Maximum = spot.Length.TotalSeconds;
        Seek.Value = spot.At.TotalSeconds;
        _writing = false;
        At.Text = Clocked(spot.At);
    }

    /// <summary>A length, in the shortest form that is not a riddle.</summary>
    /// <remarks>
    /// Minutes and seconds for a song, hours for a recording that has
    /// them. "0:03:12" for a three-minute track reads as a stopwatch;
    /// "3:12" reads as a song.
    /// </remarks>
    private static string Clocked(TimeSpan span) =>
        span.TotalHours >= 1
            ? $"{(int)span.TotalHours}:{span.Minutes:00}:{span.Seconds:00}"
            : $"{span.Minutes}:{span.Seconds:00}";

    private System.Windows.Threading.DispatcherTimer? _tick;
    private bool _scrubbing;
    private bool _writing;

    /// <summary>The tick runs only while there is a bar to move.</summary>
    /// <remarks>
    /// Nothing is playing most of the time, and a timer waking twice a
    /// second to redraw a hidden panel is a thing nobody notices and
    /// nobody stops.
    /// </remarks>
    private void Ticking(bool on)
    {
        if (!on)
        {
            _tick?.Stop();
            return;
        }

        _tick ??= Beat();
        _tick.Start();
    }

    private System.Windows.Threading.DispatcherTimer Beat()
    {
        var beat = new System.Windows.Threading.DispatcherTimer
        {
            Interval = TimeSpan.FromMilliseconds(500),
        };
        beat.Tick += (_, _) => ShowLine();
        // The page is built afresh on every visit to the section, and a
        // timer left running would keep a dead page redrawing itself.
        Unloaded += (_, _) => beat.Stop();
        return beat;
    }

    /// <summary>A person took hold of the bar.</summary>
    private void OnScrubStart(object sender,
                              System.Windows.Controls.Primitives
                                    .DragStartedEventArgs e) =>
        _scrubbing = true;

    /// <summary>And let go — that is where they meant.</summary>
    private async void OnScrubEnd(object sender,
                                  System.Windows.Controls.Primitives
                                        .DragCompletedEventArgs e)
    {
        _scrubbing = false;
        if (_remote is not null)
            await _remote.Seek(TimeSpan.FromSeconds(Seek.Value));
    }

    /// <summary>While the hand moves, the figure under it follows.</summary>
    private void OnScrubbing(object sender,
                             RoutedPropertyChangedEventArgs<double> e)
    {
        if (_writing) return;
        At.Text = Clocked(TimeSpan.FromSeconds(e.NewValue));
    }

    private TodoList? _todo;

    /// <summary>Open or close the list of things waiting (`4.0b-A13`).</summary>
    private void OnTodo(object sender, RoutedEventArgs e)
    {
        if (TodoLayer.Visibility == Visibility.Visible) HideTodo();
        else ShowTodo();
    }

    /// <summary>A click beside the panel puts it away.</summary>
    private void OnTodoAway(object sender, MouseButtonEventArgs e) =>
        HideTodo();

    /// <summary>A click inside it does not.</summary>
    private void OnTodoInside(object sender, MouseButtonEventArgs e) =>
        e.Handled = true;

    /// <summary>
    /// Bring the list up — appearing rather than switching on.
    /// </summary>
    /// <remarks>
    /// Fades and rises a little, over the same span as a section change
    /// (SYSTEM §7): it is the same kind of event — something arrived — and
    /// two different speeds for one kind of event is how an interface stops
    /// feeling like one thing.
    /// </remarks>
    private void ShowTodo()
    {
        _todo ??= new TodoList(_link);
        if (TodoBody.Content is null) TodoBody.Content = _todo;
        _ = _todo.ReloadAsync();

        TodoLayer.Visibility = Visibility.Visible;
        var span = (Duration)FindResource("Motion.Panel");
        var ease = (System.Windows.Media.Animation.IEasingFunction)
            FindResource("Ease.In");

        TodoPanel.BeginAnimation(OpacityProperty,
            new System.Windows.Media.Animation.DoubleAnimation
            {
                From = 0, To = 1, Duration = span, EasingFunction = ease,
            });
        TodoRise.BeginAnimation(
            System.Windows.Media.TranslateTransform.YProperty,
            new System.Windows.Media.Animation.DoubleAnimation
            {
                From = 12, To = 0, Duration = span, EasingFunction = ease,
            });
    }

    /// <summary>Put it away, and only then stop drawing it.</summary>
    private void HideTodo()
    {
        var span = (Duration)FindResource("Motion.Panel");
        var fade = new System.Windows.Media.Animation.DoubleAnimation
        {
            From = 1, To = 0, Duration = span,
            EasingFunction = (System.Windows.Media.Animation.IEasingFunction)
                FindResource("Ease.Out"),
        };
        // Hidden when the fade has finished, not before: collapsing it at
        // once is the switching-off this animation exists to avoid.
        fade.Completed += (_, _) => TodoLayer.Visibility = Visibility.Collapsed;
        TodoPanel.BeginAnimation(OpacityProperty, fade);
    }

    /// <summary>Open it from outside — for the check.</summary>
    public TodoList OpenTodoForCheck()
    {
        ShowTodo();
        return _todo!;
    }

    /// <summary>Put it away from outside — for the check.</summary>
    public void HideTodoForCheck() => HideTodo();

    /// <summary>Is the list on the screen — for the check.</summary>
    /// <remarks>
    /// Not the same question as <see cref="TodoShowing"/>, and the
    /// difference is what a whole block of the home check was getting
    /// wrong. A page the window has replaced keeps every property it had:
    /// its layer is still "visible", its list still holds the row that was
    /// written, and none of it is anywhere a person could look. Size is the
    /// part a detached page cannot fake — nothing measures what is not in a
    /// window.
    /// </remarks>
    public bool TodoOnScreen =>
        TodoPanel.IsVisible && TodoPanel.ActualWidth > 0
        && TodoPanel.ActualHeight > 0;

    /// <summary>The panel, in points — for the check.</summary>
    public string TodoSizeForCheck =>
        $"{TodoPanel.ActualWidth:0}x{TodoPanel.ActualHeight:0}, "
        + $"IsVisible={TodoPanel.IsVisible}";

    /// <summary>Is the list up — for the check.</summary>
    public bool TodoShowing => TodoLayer.Visibility == Visibility.Visible;

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

    /// <summary>
    /// Where each part of the player sits — for the check.
    /// </summary>
    /// <remarks>
    /// "The cover on top, the name below it, then the buttons, and the
    /// length at the bottom" was asked for in words, and words are how it
    /// would come back. Four numbers going up is the same sentence in a
    /// form that fails on its own.
    /// </remarks>
    public IReadOnlyList<(string What, double Top)> RemoteParts() =>
    [
        ("название", Above(Track)),                      // not UI
        ("кнопки", Above(Back)),                         // not UI
        ("полоска", Above(Seek)),                        // not UI
    ];

    private double Above(FrameworkElement what) =>
        what.TransformToAncestor(Remote).Transform(new Point(0, 0)).Y;

    /// <summary>The bar, as it reads — or nothing when there is none.</summary>
    public string RemoteLine => Line.Visibility == Visibility.Visible
        ? $"{At.Text} / {Length.Text}" : "";

    /// <summary>What the bar is set to — for the check.</summary>
    public (double At, double Length, bool Movable) RemoteBar =>
        (Seek.Value, Seek.Maximum, Seek.IsEnabled);

    /// <summary>What the remote is showing — for the check.</summary>
    public string RemoteShows => Remote.Visibility == Visibility.Visible
        ? $"{Artist.Text} — {Track.Text}" : "";

    /// <summary>
    /// Say what she is doing — to whoever reads the screen aloud.
    /// </summary>
    /// <remarks>
    /// The caption under the figure is gone: the figure says this already,
    /// and a word repeating it was a second voice saying the same thing.
    /// The **information** stays, on the figure itself, because a screen
    /// reader has no figure to look at. Taking a caption off the screen and
    /// taking it away from somebody who cannot see the screen are different
    /// acts, and only the first was asked for.
    /// </remarks>
    private void ShowDoing() =>
        System.Windows.Automation.AutomationProperties.SetName(Face,
            _figure.State switch
            {
                Doing.Listening => S(Word("Слушаю")),
                Doing.Thinking => S(Word("Думаю")),
                Doing.Talking => S(Word("Говорю")),
                _ => S(Word("Жду")),
            });

    /// <summary>What she is doing, in words — for the check.</summary>
    public string DoingSaid =>
        System.Windows.Automation.AutomationProperties.GetName(Face);
}
