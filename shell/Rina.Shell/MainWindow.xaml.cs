using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell;

/// <summary>
/// The main window: the frame, the column of sections, the room for a
/// section.
/// </summary>
/// <remarks>
/// <para>
/// <b>The window only routes.</b> It knows which sections exist and where
/// to show them, and nothing about their contents. Pages are independent;
/// otherwise the window becomes the god object that block B was started to
/// get rid of, only now in another language.
/// </para>
/// <para>
/// Five sections is the <c>4.0-R04</c> decision, not 3.1.0's eight tabs.
/// "History" was absorbed by "Dialogue", "Hotkeys" went into "Settings",
/// and "About" into the foot of the column.
/// </para>
/// </remarks>
public partial class MainWindow : Window
{
    /// <summary>The sections in the order they stand in the column.</summary>
    private static readonly (string Name, string Title)[] SectionList =
    [
        ("dialog", Word("Диалог")),
        ("commands", Word("Команды")),
        ("reminders", Word("Напоминания")),
        ("plugins", Word("Плагины")),
        ("settings", Word("Настройки")),
    ];

    private readonly Dictionary<string, Func<UIElement>> _pages;

    //: Sections of switched-on plugins: `plugin:<id>` → what to call it.
    //:
    //: Noted by a person: in 3.1.0 a plugin with a tab of its own got a
    //: place in the column; after the move its page lived inside the plugin
    //: list. The difference matters: a section says "I use this", a card in
    //: a list says "I installed this". Notes are opened every day, the
    //: plugin list once a month.
    private readonly List<(string Name, string Title)> _pluginSections = [];

    public MainWindow()
    {
        InitializeComponent();
        Pane.RenderTransform = _paneRise;

        // Pages are created lazily and are handed a link, not the window:
        // a section that reaches up to its parent is the first step towards
        // the god object that block B was started to get rid of.
        _pages = new Dictionary<string, Func<UIElement>>
        {
            ["dialog"] = () => new Pages.DialoguePage(Link),
            ["commands"] = () => new Pages.CommandsPage(Link),
            ["reminders"] = () => new Pages.RemindersPage(Link),
            ["plugins"] = () => new Pages.PluginsPage(Link),
            ["settings"] = () => new Pages.SettingsPage(Link),
            ["about"] = () => new Pages.AboutPage(Link),
        };

        BuildSections();
        ShowSection("dialog");

        Strings.Loc.Changed += OnLanguageChanged;
        Closed += (_, _) => Strings.Loc.Changed -= OnLanguageChanged;
    }

    /// <summary>
    /// Rebuild the interface in the new language.
    /// </summary>
    /// <remarks>
    /// Pages are built afresh rather than patched line by line: labels live
    /// in the markup, in the pages' code and in the settings layout, and
    /// walking them all would mean a fourth list of the same strings. The
    /// open section stays open — the person changed the language, not the
    /// place they were standing.
    /// </remarks>
    private void OnLanguageChanged()
    {
        var open = _section;
        BuildSections();
        _section = "";
        ShowSection(open);

        // And the footer: it translates when called, but after a language
        // change nobody called it again — the line stayed as it was written
        // last time. A translation that happens once is not a translation.
        ShowCoreState(_coreState, _coreReason);
    }

    private void BuildSections()
    {
        Sections.Children.Clear();
        foreach (var (name, title) in SectionList.Select(
                     s => (s.Name, S(s.Title)))
                 .Concat(_pluginSections))
        {
            var item = new RadioButton
            {
                Content = title,
                Tag = name,
                GroupName = "sections",
                Style = (Style)FindResource("Nav.Item"),
            };
            item.Checked += (_, _) => ShowSection(name);
            Sections.Children.Add(item);
        }
    }

    /// <summary>What is shown right now — for the checks.</summary>
    public object? CurrentPage => Pane.Content;

    /// <summary>Open a section from outside — for screenshots and checks.</summary>
    public void ShowSectionFor(string section) => ShowSection(section);

    private void ShowSection(string section)
    {
        if (!_pages.TryGetValue(section, out var build)) return;
        _section = section;
        Pane.Content = build();

        // A transition between sections is 220 ms (SYSTEM §7). An
        // appearance, not a "slide-in": movement is obliged to answer the
        // question "what changed", and here the contents changed, not their
        // position. An instrument panel does not travel.
        // `From` is given deliberately. Without it the animation starts
        // from the property's current value — and that is held by the
        // **previous** animation, which finished at one (`HoldEnd`).
        // Assigning `Opacity = 0` changes the base value, which the held
        // animation overrides, and that is why no dip happened: the first
        // transition after startup was visible, every later one was not.
        var span = (Duration)FindResource("Motion.Panel");
        var ease = (System.Windows.Media.Animation.IEasingFunction)
            FindResource("Ease.In");

        Pane.BeginAnimation(OpacityProperty,
            new System.Windows.Media.Animation.DoubleAnimation
            {
                From = 0,
                To = 1,
                Duration = span,
                EasingFunction = ease,
            });

        // Opacity alone is not enough for the transition to **read**. The
        // system's curve (`0.2, 0, 0, 1`) starts sharply: by a third of the
        // way the panel is already eighty per cent visible, and the eye
        // takes that for an instant substitution. A small rise — six points
        // — says "the contents have arrived" without turning the panel into
        // a travelling carousel: what moves is the section's contents, not
        // the instrument itself.
        _paneRise.BeginAnimation(System.Windows.Media.TranslateTransform.YProperty,
            new System.Windows.Media.Animation.DoubleAnimation
            {
                From = 6,
                To = 0,
                Duration = span,
                EasingFunction = ease,
            });

        foreach (var child in Sections.Children.OfType<RadioButton>())
            if ((string?)child.Tag == section && child.IsChecked != true)
                child.IsChecked = true;
    }

    /// <summary>The shift by which a section's contents "arrive".</summary>
    private readonly System.Windows.Media.TranslateTransform _paneRise = new();

    /// <summary>The section panel's opacity — for the motion check.</summary>
    public double PaneOpacity => Pane.Opacity;

    /// <summary>How far the contents still have to travel — for the check.</summary>
    public double PaneRise => _paneRise.Y;

    /// <summary>The link to the core; set at startup (<c>4.0-F07</c>, <c>F12</c>).</summary>
    public CoreLink? Link
    {
        get => _link;
        set
        {
            _link = value;
            // A section shown before the link appeared has to be built
            // again: it has already told the person there is no core.
            ShowSection(_section);
        }
    }

    private CoreLink? _link;
    private string _section = "dialog";

    private string _finish = "black";

    /// <summary>What the window says about the link — for the self-check.</summary>
    public string CoreStateTextValue => CoreStateText.Text;

    /// <summary>Which finish is showing now — for the self-check.</summary>
    public string FinishValue => _finish;

    /// <summary>The state changed. The self-check listens.</summary>
    public event Action<CoreState>? CoreStateShown;

    /// <summary>
    /// Show the state of the link to the core (<c>4.0-F12</c>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// The state is always visible rather than shown on request: §13
    /// requires that the window not look frozen, and a person must
    /// understand what is happening without pressing anything.
    /// </para>
    /// <para>
    /// A fault is coloured with the accent, not with red. There is no red
    /// in the palette at all (§2 of the design system): the colour of
    /// danger wears out through repetition, and where every unpleasantness
    /// is painted with it, it stops meaning "careful". "The core does not
    /// answer" is an error, not a danger.
    /// </para>
    /// </remarks>
    private CoreState _coreState = CoreState.Stopped;
    private string _coreReason = "";

    public void ShowCoreState(CoreState state, string reason)
    {
        var text = state switch
        {
            CoreState.Ready => S("ядро на связи"),
            CoreState.Starting => S("ядро запускается"),
            CoreState.Reconnecting => S("связь потеряна, поднимаем"),
            CoreState.Failed => S("ядро не отвечает"),
            _ => S("ядро не запускалось"),
        };
        // Remembered: after a language change the footer has to be
        // rewritten, and by then nobody will send the state again.
        _coreState = state;
        _coreReason = reason;
        // The reason comes from `Rina.Protocol` — a library with no
        // translations, and rightly so: its business is the wire, not
        // language. The window assembles the commonest phrase itself; the
        // rest it shows as it is — a technical detail in the log's language
        // is more honest than a crooked translation of it.
        // The words are assembled by the window, not by the supervisor:
        // `Rina.Protocol` does not know the interface's language (F08), and
        // it used to send a ready-made Russian phrase — which reached the
        // footer past the translation table and stayed Russian under an
        // English interface.
        var about = state switch
        {
            CoreState.Ready when reason.Length > 0 => S("ядро {0}", reason),
            CoreState.Reconnecting when Link?.Attempt > 1
                => S("попытка {0}", Link.Attempt),
            _ => reason,
        };

        CoreStateText.Text = about.Length > 0 ? $"{text} · {about}" : text;
        CoreStateText.SetResourceReference(
            ForegroundProperty,
            state is CoreState.Ready or CoreState.Stopped ? "C.InkFaint"
                                                          : "C.Signal");
        CoreStateShown?.Invoke(state);
    }

    /// <summary>An event from the core. For now — only the level strip.</summary>
    public void OnCoreEvent(Envelope message)
    {
        // Sorting events out by section is 4.0-F04. What stays here is
        // what belongs to the instrument as a whole rather than to a
        // section: the level strip and what is seen on top of the screen.
        if (message.Method is "listening.capturing")
            ShowLevel(message.Payload["active"]?.GetValue<bool>() == true
                      ? 0.4f : 0f);

        Overlay(message);
    }

    /// <summary>
    /// Show the microphone level with an afterglow.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>A sign of direction, not a decoration</b> (`DIRECTION` §4). The
    /// strip does not switch between "off" and "on": after a phrase has
    /// been heard the trace fades over about a second, and the panel shows
    /// not only that Rina is listening <i>now</i> but also that she has
    /// just been hearing something. Instant switching is a straight "not in
    /// the style" by the twelve questions of §6, and before this change the
    /// strip did exactly that — it jumped.
    /// </para>
    /// <para>
    /// <b>Fast up, slow down.</b> The rise shows what is happening now, and
    /// it must not be late; the fall shows what has already passed, and it
    /// has nowhere to hurry. One duration for both directions would give
    /// either a sluggish reaction or a flicker.
    /// </para>
    /// </remarks>
    public void ShowLevel(float level)
    {
        var wanted = Math.Clamp(level, 0f, 1f) * ActualWidth;
        var now = Level.ActualWidth;

        // The rise takes the press duration: the strip is the microphone,
        // and its upward movement is the same "now" as a button's.
        var rising = wanted > now;
        var span = rising ? (Duration)FindResource("Motion.Press")
                          : (Duration)FindResource("Motion.Afterglow");

        var glide = new global::System.Windows.Media.Animation.DoubleAnimation
        {
            To = wanted,
            Duration = span,
            EasingFunction = (global::System.Windows.Media.Animation.IEasingFunction)
                FindResource(rising ? "Ease.In" : "Ease.Out"),
            FillBehavior = global::System.Windows.Media.Animation
                .FillBehavior.HoldEnd,
        };
        Level.BeginAnimation(WidthProperty, glide);
        LevelShown = level;
    }

    /// <summary>Which level was shown last — for the end-to-end check.</summary>
    public float LevelShown { get; private set; }

    /// <summary>What is seen on top of the screen: a line and the "listening" plaque.</summary>
    public Overlays.Toast? Toast { get; set; }

    /// <summary>The listening plaque.</summary>
    public Overlays.Listening? Plaque { get; set; }

    /// <summary>Whether to show lines on top of the screen (a setting).</summary>
    public bool ShowToasts { get; set; } = true;

    /// <summary>
    /// An event from the core — into the windows on top of the screen.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>A line is shown when the window is not visible.</b> If the person
    /// is looking at the dialogue, the answer is already in front of them,
    /// and duplicating it with a card in the corner means showing one and
    /// the same thing twice.
    /// </para>
    /// <para>
    /// <b>The "listening" plaque is always shown.</b> Here it is the other
    /// way round: the right to know that the microphone is working does not
    /// depend on whether the window is open — it is precisely when the
    /// window is closed that this matters.
    /// </para>
    /// </remarks>
    private void Overlay(Envelope message)
    {
        switch (message.Method)
        {
            case "listening.started":
                Plaque?.Appear(always: false);
                break;

            case "listening.stopped":
                if (Plaque is { } stopping && !stopping.Always)
                    stopping.Vanish();
                break;

            case "listening.always":
                var on = message.Payload["enabled"]?.GetValue<bool>() == true;
                if (on) Plaque?.Appear(always: true);
                else Plaque?.Vanish();
                break;

            case "assistant.response":
                if (ShowToasts && !IsVisible)
                    Toast?.Say(message.Payload["text"]?.GetValue<string>() ?? "");
                break;

            case "assistant.error":
                if (ShowToasts && !IsVisible)
                    Toast?.Say(message.Payload["text"]?.GetValue<string>() ?? "",
                               Overlays.Toast.Short);
                break;
        }
    }

    /// <summary>
    /// Refresh the plugin sections.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Only a <b>switched-on</b> plugin with a page of its own gets a
    /// section: one that is off is not loaded, and there is nobody to ask
    /// for its page.
    /// </para>
    /// <para>
    /// The open section is kept if it still exists. Otherwise switching one
    /// plugin off would throw the person out of another.
    /// </para>
    /// </remarks>
    public void ShowPluginSections(
        IEnumerable<(string Id, string Title, string Icon)> plugins)
    {
        var wanted = plugins
            .Select(p => ($"plugin:{p.Id}",
                          p.Icon.Length > 0 ? $"{p.Icon}  {p.Title}" : p.Title))
            .ToList();

        if (wanted.Select(w => w.Item1).SequenceEqual(
                _pluginSections.Select(p => p.Name)))
            return;                                  // ничего не изменилось

        foreach (var (name, _) in _pluginSections) _pages.Remove(name);
        _pluginSections.Clear();

        foreach (var (name, title) in wanted)
        {
            var id = name["plugin:".Length..];
            _pluginSections.Add((name, title));
            _pages[name] = () => new Pages.PluginView(Link, id);
        }

        var open = _section;
        BuildSections();
        _section = "";
        ShowSection(_pages.ContainsKey(open) ? open : "dialog");
    }

    /// <summary>Which sections exist right now — for the end-to-end check.</summary>
    public string[] SectionNames() => Sections.Children
        .OfType<System.Windows.Controls.RadioButton>()
        .Select(item => (string)item.Tag)
        .ToArray();

    /// <summary>The finish the window is showing.</summary>
    public void ShowFinish(string finish) => _finish = finish;

    private async void OnSwitchFinish(object sender, RoutedEventArgs e)
    {
        // The two finishes are equal (4.0-R08), so a toggle rather than a
        // list: there is nothing to choose from but between them.
        _finish = _finish == "black" ? "silver" : "black";
        if (Link is not null) await Link.SetFinishAsync(_finish);
        else App.ApplyFinish(_finish);
    }

    /// <summary>
    /// "About" is a section, not a pop-up window.
    /// </summary>
    /// <remarks>
    /// It is not in the column: people go there rarely, and it does not
    /// deserve a permanent place. But a modal window will not do for it
    /// either — it holds links that are followed and versions that are
    /// copied into a fault report.
    /// </remarks>
    private void OnAbout(object sender, MouseButtonEventArgs e)
        => ShowSection("about");

    private void OnMinimise(object sender, RoutedEventArgs e) =>
        WindowState = WindowState.Minimized;

    private void OnMaximise(object sender, RoutedEventArgs e) =>
        WindowState = WindowState == WindowState.Maximized
            ? WindowState.Normal : WindowState.Maximized;

    /// <summary>The tray icon; set at startup (<c>4.0-F05</c>).</summary>
    public Tray? Tray { get; set; }

    /// <summary>Minimise to the tray instead of quitting. The person decides.</summary>
    public bool MinimiseToTray { get; set; } = true;

    /// <summary>
    /// The close button: minimise or quit.
    /// </summary>
    /// <remarks>
    /// A program that does not close on the close button against
    /// expectation is taken for a broken one — so the behaviour is chosen
    /// by the person, not by us on their behalf. Quitting from the tray is
    /// always possible.
    /// </remarks>
    private void OnClose(object sender, RoutedEventArgs e) => OnCloseButton();

    /// <summary>The same as pressing the close button. Separate for the check's sake.</summary>
    /// <remarks>
    /// The window may only be hidden if the tray icon was actually created:
    /// otherwise there is nothing to bring it back with, and the program
    /// keeps running invisible and unreachable. So what is asked is not "is
    /// there a tray object" but "did the icon get created" — the object is
    /// always there.
    /// </remarks>
    public void OnCloseButton()
    {
        if (MinimiseToTray && Tray is { Created: true }) Tray.Hide();
        else System.Windows.Application.Current.Shutdown();
    }

    /// <summary>The main hotkey was pressed (<c>4.0-F06</c>).</summary>
    public void OnMainHotkey()
    {
        Tray?.Show();
        ShowSection("dialog");
        // Listening on a keypress is what the hotkey is for: an assistant
        // is summoned when there is something to say.
        _ = Link?.ListenOnceAsync();
    }

    /// <summary>A short message to the person in the foot of the column.</summary>
    public void ShowNote(string text)
    {
        CoreStateText.Text = text;
        CoreStateText.SetResourceReference(ForegroundProperty, "C.Signal");
    }
}
