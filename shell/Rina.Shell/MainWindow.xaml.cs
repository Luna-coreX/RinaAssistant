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
        ("home", Word("Главная")),
        ("dialog", Word("Диалог")),
        ("commands", Word("Команды")),
        ("reminders", Word("Напоминания")),
        // Beside the reminders, because the two answer neighbouring
        // questions — what is coming, and what has been going on — and a
        // person looking for one often wants the other. Not merged with
        // them: a reminder fires and a session merely runs, and a column
        // that called both "напоминания" would be naming the timer.
        ("sessions", Word("Сессии")),
        ("plugins", Word("Плагины")),
        // Between the plugins and the settings, not inside them. It is the
        // page that makes "privacy-first" a thing a person can check rather
        // than a claim, and a claim one has to go looking for inside the
        // settings is a claim nobody reads.
        ("privacy", Word("Приватность")),
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
        // One number, one source: the assembly. It used to be typed into
        // the markup here and read from the assembly on «about», and the
        // two would have parted company at the first release.
        Version.Text = App.ShellVersion;
        Pane.RenderTransform = _paneRise;

        // The living background (4.0b-A06). It follows whether there is
        // anybody to look: hidden, minimised or behind another window means
        // nobody, and then it stops. See Backdrop for why that is the task
        // rather than an optimisation.
        _backdrop = new Backdrop(Backdrop, BackdropCalm);

        // The bar shows the same picture, blurred (`4.0b-E01`). The same
        // bitmap rather than a second one: two pictures of one flow would
        // drift apart by a frame and the seam would show exactly where the
        // bar ends.
        //
        // *Which* picture is decided by `FollowGlass`: there are two
        // layers and the bar must be on the one the page is on.
        BarGlass.Effect = new System.Windows.Media.Effects.BlurEffect
        {
            Radius = (double)FindResource("Glass.Blur"),
            KernelType = System.Windows.Media.Effects.KernelType.Gaussian,
            RenderingBias = System.Windows.Media.Effects.RenderingBias
                .Performance,
        };
        // Laid out over the whole window and cut to the bar by the row's
        // clip: that is what makes it show what is behind the bar rather
        // than the whole flow squeezed into forty points.
        //
        // **And it dissolves rather than ends.** Cut off, the blurred
        // picture meets the sharp one along a line, and a line is read as
        // the edge of a thing: measured across it, the brightness jumped
        // by five units, and the bar became a plate with a rim — which is
        // the very thing the blur was added to avoid. Noticed by the
        // person using it, in one screenshot.
        //
        // The fade is in the picture's own coordinates, so it moves with
        // the window: the mask is relative, the row is not.
        var fade = new System.Windows.Media.LinearGradientBrush
        {
            StartPoint = new Point(0, 0),
            EndPoint = new Point(0, 1),
        };
        BarGlass.OpacityMask = fade;
        void Dissolve()
        {
            var tall = Math.Max(ActualHeight > 0 ? ActualHeight : Height, 1);
            var row = (double)FindResource("Size.Row");
            var soft = (double)FindResource("Glass.Fade");
            fade.GradientStops.Clear();
            fade.GradientStops.Add(new System.Windows.Media.GradientStop(
                System.Windows.Media.Colors.Black, 0));
            fade.GradientStops.Add(new System.Windows.Media.GradientStop(
                System.Windows.Media.Colors.Black,
                Math.Max(0, (row - soft) / tall)));
            fade.GradientStops.Add(new System.Windows.Media.GradientStop(
                System.Windows.Media.Colors.Transparent, row / tall));
        }

        SizeChanged += (_, _) =>
        {
            BarGlass.Height = ActualHeight;
            Dissolve();
        };
        BarGlass.Height = Height;
        Dissolve();
        // The flow takes its colour from the accent, so it has to be told
        // when the accent changes — and it is changed from two places, the
        // settings page and the link's first hello, neither of which should
        // know that a background exists.
        App.AccentChanged += () => _backdrop.Build();
        IsVisibleChanged += (_, _) => FollowBackdrop();
        StateChanged += (_, _) => FollowBackdrop();
        Activated += (_, _) => FollowBackdrop();
        Deactivated += (_, _) => FollowBackdrop();
        Loaded += (_, _) => FollowBackdrop();

        // Pages are created lazily and are handed a link, not the window:
        // a section that reaches up to its parent is the first step towards
        // the god object that block B was started to get rid of.
        _pages = new Dictionary<string, Func<UIElement>>
        {
            ["home"] = () =>
            {
                // The figure moves at the background's pace, and is given
                // that pace here rather than taking one of its own: every
                // reason the background stops is a reason the figure stops.
                var page = new Pages.HomePage(Link);
                page.FollowClock(_backdrop);
                return page;
            },
            ["dialog"] = () => new Pages.DialoguePage(Link),
            ["commands"] = () => new Pages.CommandsPage(Link),
            ["reminders"] = () => new Pages.RemindersPage(Link),
            ["sessions"] = () => new Pages.SessionsPage(Link),
            ["plugins"] = () => new Pages.PluginsPage(Link),
            ["privacy"] = () => new Pages.PrivacyPage(Link),
            ["settings"] = () => new Pages.SettingsPage(Link),
            ["about"] = () => new Pages.AboutPage(Link),
        };

        BuildSections();
        ShowSection("home");
        FollowGlass();

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

    //: Sections that exist only while something is open in them: a command
    //: being written (`4.0b-A09`). They sit under the fixed ones and go when
    //: the work is done.
    private readonly List<(string Name, string Title)> _openWork = [];

    private void BuildSections()
    {
        Sections.Children.Clear();
        foreach (var (name, title) in SectionList.Select(
                     s => (s.Name, S(s.Title)))
                 .Concat(_pluginSections)
                 .Concat(_openWork))
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

    /// <summary>
    /// Open a command in a place of its own (<c>4.0b-A09</c>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// Writing a command is work, not a glance. It used to unfold inside
    /// the list, above the very rows a person was comparing it against, and
    /// it pushed them off the screen: the thing being written and the
    /// things it should not clash with could not be seen together, and
    /// there was nowhere to put a chain of eight steps.
    /// </para>
    /// <para>
    /// A section rather than a window. A window would take the focus and
    /// have to be dismissed; a section is a place one goes and comes back
    /// from, and the column already says which places there are. It stands
    /// under the fixed sections and leaves when the work is done — the
    /// menu tells the truth about what is open.
    /// </para>
    /// </remarks>
    public void OpenWork(string id, string title, Func<UIElement> page)
    {
        var name = "work:" + id;
        if (!_openWork.Any(w => w.Name == name))
            _openWork.Add((name, title));
        _pages[name] = page;
        BuildSections();
        ShowSection(name);
    }

    /// <summary>The work is done; the place goes with it.</summary>
    public void CloseWork(string id, string back = "commands")
    {
        var name = "work:" + id;
        _openWork.RemoveAll(w => w.Name == name);
        _pages.Remove(name);
        BuildSections();
        ShowSection(back);
    }

    /// <summary>Which pieces of work are open — for the check.</summary>
    public string[] OpenWorkNames => _openWork.Select(w => w.Name).ToArray();

    /// <summary>What is shown right now — for the checks.</summary>
    public object? CurrentPage => Pane.Content;

    /// <summary>The room a page is given — for the check.</summary>
    public object PaneRoom => Pane.Margin;

    /// <summary>Open a section from outside — for screenshots and checks.</summary>
    /// <remarks>
    /// The menu is opened along with it, and that is not a convenience for
    /// the checks: a section is chosen **from** the menu, so a person who
    /// is looking at a section they just picked has had the menu open a
    /// moment ago. A screenshot taken with it shut would be a picture of a
    /// state nobody arrives at by choosing.
    /// </remarks>
    public void ShowSectionFor(string section)
    {
        ShowMenu(true);
        ShowSection(section);
    }

    /// <summary>Is the section menu open.</summary>
    public bool MenuOpen { get; private set; }

    /// <summary>How wide the menu is right now — for the check.</summary>
    /// <remarks>
    /// "It is closed" cannot be seen in a screenshot taken at the wrong
    /// moment: the column takes 220 ms to fold away, and a picture caught
    /// halfway shows a half-open menu that is neither state. This is the
    /// number, and it is read after the movement is over.
    /// </remarks>
    public double MenuWidth => MenuColumn.Width.Value;

    private void OnMenu(object sender, RoutedEventArgs e) =>
        ShowMenu(!MenuOpen);

    /// <summary>Fold the section menu out or away.</summary>
    /// <remarks>
    /// The width is animated rather than switched, and the same 220 ms as a
    /// section change (SYSTEM §7): the menu is part of the instrument, and
    /// a part of an instrument that appears instantly reads as a part that
    /// was hidden rather than as one that was folded away.
    /// </remarks>
    public void ShowMenu(bool open)
    {
        if (MenuOpen == open) return;
        MenuOpen = open;

        var wide = (GridLength)FindResource("Col.LegendColumn");
        var from = MenuColumn.Width.Value;
        var to = open ? wide.Value : 0;
        var span = (Duration)FindResource("Motion.Panel");
        var ease = (System.Windows.Media.Animation.IEasingFunction)
            FindResource("Ease.In");

        // A GridLength cannot be animated by WPF's own animations — there is
        // no GridLengthAnimation in the framework, and writing one would be
        // a class for one property. A clock that assigns the width is the
        // ordinary way round it, and here it is the cheaper one too.
        var clock = new System.Windows.Media.Animation.DoubleAnimation
        {
            From = from,
            To = to,
            Duration = span,
            EasingFunction = ease,
        };
        var carrier = new System.Windows.Controls.Border();
        carrier.SetValue(System.Windows.FrameworkElement.WidthProperty, from);
        carrier.SizeChanged += (_, _) =>
            MenuColumn.Width = new GridLength(carrier.Width);
        carrier.BeginAnimation(System.Windows.FrameworkElement.WidthProperty,
                               clock);

        // The carrier is not in the tree, so it raises no SizeChanged. The
        // width is followed by the rendering clock instead — one line, and
        // no invisible element pretending to be part of the window.
        System.Windows.Media.CompositionTarget.Rendering -= FollowMenu;
        _menuCarrier = carrier;
        System.Windows.Media.CompositionTarget.Rendering += FollowMenu;
    }

    private System.Windows.Controls.Border? _menuCarrier;

    private void FollowMenu(object? sender, EventArgs e)
    {
        if (_menuCarrier is null) return;
        var width = _menuCarrier.Width;
        MenuColumn.Width = new GridLength(double.IsNaN(width) ? 0 : width);
        var wanted = MenuOpen
            ? ((GridLength)FindResource("Col.LegendColumn")).Value : 0;
        if (Math.Abs(width - wanted) < 0.5)
        {
            MenuColumn.Width = new GridLength(wanted);
            System.Windows.Media.CompositionTarget.Rendering -= FollowMenu;
            _menuCarrier = null;
        }
    }

    private void ShowSection(string section)
    {
        if (!_pages.TryGetValue(section, out var build)) return;
        _section = section;
        Pane.Content = build();

        // The home screen shows the flow as it is; every other section
        // shows it calmed and softened (4.0b-A06, 4.0b-A07). This is the
        // place that decision finally lands: until there was a screen one
        // *looks* at, the vivid layer had nowhere to be but under the
        // window's own bars, where it read as a stripe rather than as a
        // difference between screens.
        BackdropCalm.Visibility = section is "home"
            ? Visibility.Collapsed : Visibility.Visible;
        FollowGlass();

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

        // The section arrives in parts, not as a plate (`4.0b-E04`). When
        // it has parts they do the fading and the panel does not: two
        // fades over one another give a soft grey smear instead of an
        // arrival, and the second one is invisible anyway.
        if (Arrive(Pane.Content as UIElement))
        {
            Pane.BeginAnimation(OpacityProperty, null);
            Pane.Opacity = 1;
        }
        else
        {
            Pane.BeginAnimation(OpacityProperty,
                new System.Windows.Media.Animation.DoubleAnimation
                {
                    From = 0,
                    To = 1,
                    Duration = span,
                    EasingFunction = ease,
                });
        }

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

        // And the shadow settles with it (4.0b-A06). Contents arriving from
        // above carry their shadow while they travel; when they have come
        // to rest it is gone. Without this the rise reads as a picture
        // sliding rather than as a layer settling — opacity and offset
        // alone say "something appeared", not "something came to rest".
        //
        // **It goes to nothing, not to a resting shadow**, and that is the
        // exact wording of the amendment to §5 of the design system: a
        // shadow is allowed as movement, and in a still frame there is
        // none. Letting it settle at the "raised" level would have been a
        // card on a shadow — the thing the amendment does not permit — and
        // the code would have quietly said something other than the
        // document.
        Pane.Effect = _paneLift;
        _paneLift.Color = (System.Windows.Media.Color)FindResource("Color.Shadow");
        Lift(System.Windows.Media.Effects.DropShadowEffect.BlurRadiusProperty,
             (double)FindResource("Lift.Floating.Blur"),
             (double)FindResource("Lift.Raised.Blur"), span, ease);
        Lift(System.Windows.Media.Effects.DropShadowEffect.ShadowDepthProperty,
             (double)FindResource("Lift.Floating.Y"), 0, span, ease);
        Lift(System.Windows.Media.Effects.DropShadowEffect.OpacityProperty,
             (double)FindResource("Lift.Floating.Opacity"), 0, span, ease);

        foreach (var child in Sections.Children.OfType<RadioButton>())
            if ((string?)child.Tag == section && child.IsChecked != true)
                child.IsChecked = true;
    }

    /// <summary>The shift by which a section's contents "arrive".</summary>
    private readonly System.Windows.Media.TranslateTransform _paneRise = new();

    /// <summary>The living background, and its clock (<c>4.0b-A06</c>).</summary>
    private readonly Backdrop _backdrop;

    /// <summary>The shadow under the section's contents.</summary>
    /// <remarks>
    /// Held in a field because it is animated: a section that has just
    /// arrived settles onto the panel, and the depth of its shadow is what
    /// says so. Reaching for the effect through the visual tree on every
    /// transition would work and would be a way to lose it after the first
    /// change to the markup.
    /// </remarks>
    private readonly System.Windows.Media.Effects.DropShadowEffect _paneLift =
        new() { Direction = 270, ShadowDepth = 0, BlurRadius = 0, Opacity = 0 };

    /// <summary>Is the background moving right now — for the check.</summary>
    public bool BackdropRunning => _backdrop.Running;

    /// <summary>How far along its period the background is — for the check.</summary>
    public double BackdropPhase => _backdrop.Phase;

    /// <summary>What one frame of the background costs — for the check.</summary>
    public double BackdropFrameMs => _backdrop.BestFrameMs;

    /// <summary>How much the background's picture moved — for the check.</summary>
    public double BackdropChange => _backdrop.FrameChange;

    /// <summary>Run the background regardless of focus — for screenshots.</summary>
    /// <remarks>
    /// A screenshot is taken from a window drawn off the edge of the
    /// screen, and such a window is not active. The background follows
    /// activity on purpose — nobody is looking at an inactive window — so
    /// every screenshot until now was of the field's opening phase, and two
    /// shots of two runs looked identical for a reason that had nothing to
    /// do with the field.
    /// </remarks>
    public void RunBackdropForShot() => _backdrop.Follow(true);

    /// <summary>
    /// The bar is glass over whichever layer the page is on.
    /// </summary>
    /// <remarks>
    /// There are two flows — the vivid one and the calm one — and the
    /// page shows one of them. The bar used to blur the vivid one always,
    /// so on every tab but the home screen it was a window onto a
    /// different background from the one beneath it. That is what "the
    /// bar does not blend with the tab" meant, and no amount of softening
    /// the edge would have fixed it: the two pictures were different
    /// pictures.
    /// </remarks>
    private void FollowGlass()
        => BarGlass.Source = BackdropCalm.Visibility == Visibility.Visible
            ? BackdropCalm.Source : Backdrop.Source;

    /// <summary>Which flow the bar is glass over — for the check.</summary>
    public bool BarOnCalm => ReferenceEquals(BarGlass.Source,
                                             BackdropCalm.Source);

    //: The parts of the section that arrived last — for the check.
    private IReadOnlyList<UIElement> _arrived = [];

    /// <summary>How far each part of the section has arrived — for the check.</summary>
    public IReadOnlyList<double> PartsArriving
        => _arrived.Select(part => part.Opacity).ToList();

    /// <summary>
    /// The section's parts arrive one after another (<c>4.0b-E04</c>).
    /// </summary>
    /// <remarks>
    /// <para>
    /// A section used to arrive as one plate: the whole panel faded and
    /// rose together. That says "something appeared" and nothing else. A
    /// screen has parts — a title, a list, the row of buttons under it —
    /// and they are what a person looks for. Arriving in that order, they
    /// say what the screen is made of while it is being made.
    /// </para>
    /// <para>
    /// The step is small and the count is capped, so the whole arrival
    /// still fits inside the section change it belongs to: five steps of
    /// twenty-four milliseconds and a state's worth of fade at the end is
    /// two hundred and eighty, against the panel's two hundred and
    /// twenty. A stagger that outlasts the transition stops being a
    /// transition and becomes a loading screen.
    /// </para>
    /// <para>
    /// Only where a page really has parts. A page whose root holds one
    /// thing is left to the panel's own arrival — inventing divisions in
    /// it would be movement that reports a structure the page does not
    /// have.
    /// </para>
    /// </remarks>
    private bool Arrive(UIElement? page)
    {
        var parts = Parts(page);
        _arrived = parts;
        if (parts.Count < 2) return false;

        // A fade and nothing else. The panel itself already rises and
        // sets its shadow down (`4.0b-A06`); giving every part a rise of
        // its own on top of that meant each one travelled twice, and
        // three things moving at once do not read as one arrival — they
        // read as a jerk.
        var span = (Duration)FindResource("Motion.State");
        var ease = (System.Windows.Media.Animation.IEasingFunction)
            FindResource("Ease.In");
        // A duration in the dictionary, like every other span: the step
        // between parts is a length of time, and keeping it as a bare
        // number here would be a second way of saying what `tokens.json`
        // already says.
        var step = (Duration)FindResource("Motion.Stagger");

        for (var at = 0; at < parts.Count; at++)
        {
            // Capped rather than spread: on a page of ten rows the last
            // one would arrive a quarter of a second after the first, and
            // by then a person has already read the top of the screen.
            var wait = TimeSpan.FromTicks(
                step.TimeSpan.Ticks * Math.Min(at, 5));

            // **Held at nothing until its turn.** `BeginTime` alone does
            // not do that: while a clock is still in its delay WPF gives
            // back the property's *base* value, which here is one. So a
            // part that was to arrive third stood fully visible for its
            // first fifty milliseconds, blinked out, and only then faded
            // in. Measured: at thirty milliseconds the four parts read
            // 0.53, 0.20, 1.00, 1.00 — the stagger a person saw was two
            // parts fading and two flashing.
            //
            // Key frames say the wait out loud instead: nothing, nothing
            // still, then the fade. `Stop` at the end so the property
            // goes back to belonging to the page.
            var fade = new System.Windows.Media.Animation
                .DoubleAnimationUsingKeyFrames
            {
                Duration = new Duration(wait + span.TimeSpan),
                FillBehavior = System.Windows.Media.Animation
                    .FillBehavior.Stop,
            };
            fade.KeyFrames.Add(new System.Windows.Media.Animation
                .DiscreteDoubleKeyFrame(0, System.Windows.Media.Animation.KeyTime.FromTimeSpan(TimeSpan.Zero)));
            fade.KeyFrames.Add(new System.Windows.Media.Animation
                .DiscreteDoubleKeyFrame(0, System.Windows.Media.Animation.KeyTime.FromTimeSpan(wait)));
            fade.KeyFrames.Add(new System.Windows.Media.Animation
                .EasingDoubleKeyFrame(1,
                    System.Windows.Media.Animation.KeyTime.FromTimeSpan(wait + span.TimeSpan))
                { EasingFunction = ease });
            parts[at].BeginAnimation(OpacityProperty, fade);
        }
        return true;
    }

    /// <summary>The first place where a page really has more than one thing.</summary>
    private static IReadOnlyList<UIElement> Parts(UIElement? page)
    {
        var at = page;
        for (var deep = 0; deep < 4 && at is not null; deep++)
        {
            if (at is Panel holder)
            {
                var seen = holder.Children.OfType<UIElement>()
                    .Where(child => child.Visibility == Visibility.Visible)
                    .ToList();
                if (seen.Count >= 2) return seen;
                at = seen.FirstOrDefault();
                continue;
            }
            at = at switch
            {
                ContentControl one => one.Content as UIElement,
                Border edge => edge.Child,
                _ => null,
            };
        }
        return [];
    }

    /// <summary>Freeze the background on a picture the check drew — for the check.</summary>
    public void PaintBackdropForCheck(
        Func<int, int, (byte R, byte G, byte B)> ink)
        => _backdrop.PaintForCheck(ink);

    /// <summary>How much the background moved over a second — for the check.</summary>
    public double BackdropDrift => _backdrop.DriftPerSecond;

    /// <summary>
    /// Let the background run only while there is somebody to look.
    /// </summary>
    /// <remarks>
    /// Being active is part of it, not only being visible: a window left
    /// open behind a browser is on screen and is not being looked at, and
    /// that is the commonest case of all — usage mode number one is "in the
    /// background while working".
    /// </remarks>
    private void FollowBackdrop() =>
        _backdrop.Follow(IsVisible && WindowState != WindowState.Minimized
                         && IsActive);

    /// <summary>One property of the settling shadow.</summary>
    private void Lift(DependencyProperty property, double from, double to,
                      Duration span,
                      System.Windows.Media.Animation.IEasingFunction ease) =>
        _paneLift.BeginAnimation(property,
            new System.Windows.Media.Animation.DoubleAnimation
            {
                From = from,
                To = to,
                Duration = span,
                EasingFunction = ease,
            });

    /// <summary>The section panel's opacity — for the motion check.</summary>
    public double PaneOpacity => Pane.Opacity;

    /// <summary>How visible the section's shadow is — for the motion check.</summary>
    /// <remarks>
    /// Opacity rather than blur: the blur is what the shadow is made of,
    /// the opacity is whether there is one at all. The check has to be able
    /// to say "in a still frame there is no shadow", and only this answers
    /// that.
    /// </remarks>
    public double PaneShadow => _paneLift.Opacity;

    /// <summary>How far the contents still have to travel — for the check.</summary>
    public double PaneRise => _paneRise.Y;

    /// <summary>The link to the core; set at startup (<c>4.0-F07</c>, <c>F12</c>).</summary>
    public CoreLink? Link
    {
        get => _link;
        set
        {
            var had = _link is not null;
            _link = value;
            // A section shown **before** the link appeared has to be built
            // again: it has already told the person there is no core.
            //
            // One that was built with a link is left alone. Rebuilding it
            // throws away what is on it, and the replacement shows only
            // what the core has already stored — so a message typed a
            // moment ago vanished, because storing it and showing it do not
            // happen at the same instant. A person reconnecting mid-sentence
            // watched their own words disappear.
            if (!had || value is null) ShowSection(_section);
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

        // A scenario being tried says which step it is on (`4.0b-A09`).
        // Passed to whatever is open, because only the editor has a canvas
        // to light up and only while it is showing one.
        if (message.Method == "command.step"
            && Pane.Content is Pages.CommandEditor editing)
            editing.StepReported(
                message.Payload["path"]?.GetValue<string>() ?? "",
                message.Payload["state"]?.GetValue<string>() ?? "");

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

            // A conversation is open: the wake word may be left out for a
            // while (`4.0b-E06`). Shown because it has to be — for as
            // long as this stands, a phrase near the machine counts as
            // addressed to it.
            case "listening.conversation":
                var talking = message.Payload["open"]?.GetValue<bool>() == true;
                if (talking)
                    Plaque?.Converse(
                        message.Payload["seconds"]?.GetValue<double>() ?? 0);
                else Plaque?.Hush();
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
    public void ShowFinish(string finish)
    {
        _finish = finish;
        // The patches are made of the finish's colours, and the finish is
        // swapped as a whole dictionary: they have to be built again, or
        // the background would keep the colours of the finish before last.
        _backdrop.Build();
    }

    private async void OnSwitchFinish(object sender, RoutedEventArgs e)
    {
        // The finishes are equal (4.0-R08), so the button walks the ring
        // rather than choosing from a list: there is no main one to return
        // to. With two it was a toggle; a third arrived with 4.0b-A06, and
        // a toggle over three would have quietly hidden one of them.
        _finish = App.NextFinish(_finish);
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
