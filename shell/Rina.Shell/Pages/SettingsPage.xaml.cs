using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// Settings: ten sections in one panel.
/// </summary>
/// <remarks>
/// <para>
/// Here the two halves of
/// [ADR 0006](../../../docs/adr/0006-settings-ownership.md) meet. The core
/// sent the meaning — the type, the default, the enumeration, the range,
/// the dependency, the "needs a restart" mark. The shell knows the
/// appearance — the labels and the sections
/// (<see cref="SettingsLayout"/>). Neither half can be derived from the
/// other, and that is the whole decision.
/// </para>
/// <para>
/// <b>Dependent fields go dim, they do not hide.</b> "Model address" is
/// useless while the model is off, but hiding it makes a person guess
/// where it went. What is switched off must read as switched off rather
/// than as missing — the same rule as the design system's one about
/// contrast.
/// </para>
/// <para>
/// <b>A warning is not a refusal.</b> "The address is not local" means the
/// value was written down and the person was told what it will lead to.
/// The decision is theirs.
/// </para>
/// </remarks>
public partial class SettingsPage : UserControl
{
    private readonly CoreLink? _link;
    private readonly Dictionary<string, JsonObject> _schema = [];
    private readonly Dictionary<string, JsonNode?> _values = [];
    private readonly Dictionary<string, FrameworkElement> _editors = [];

    /// <summary>How many sections were built — for the end-to-end check.</summary>
    public int SectionCount => Body.Children.Count;

    /// <summary>Keys the core sent and the shell laid out.</summary>
    public int KeyCount => _schema.Count;

    /// <summary>The first dropdown — for the end-to-end check.</summary>
    public ComboBox? FirstChoice() =>
        _editors.Values.OfType<ComboBox>().FirstOrDefault(b => b.Items.Count > 0);

    /// <summary>
    /// Scroll down by so much — so a screenshot reaches below the fold.
    /// </summary>
    /// <remarks>
    /// Half the settings screen is not visible on the first screenful, and
    /// checking only the top by screenshot means not checking the folder
    /// list, the model choice and the device choice — which is exactly what
    /// was happening here.
    /// </remarks>
    public void ScrollTo(double offset) => Scroll.ScrollToVerticalOffset(offset);

    /// <summary>
    /// The widths of every control — for the column check.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The width is set by the column, not by the control. This used to be
    /// checked by eye, by one person with screenshots: the path field was
    /// 200 wide, the dropdown 280, the slider with a number 276, and the
    /// right edge wandered by eighty points.
    /// </para>
    /// <para>
    /// A screenshot cannot measure that: the column's right edge is not a
    /// colour boundary — the path row has a button on the right, the
    /// slider has a number, and the fill ends before the column does. So
    /// what is measured is the tree, not the picture.
    /// </para>
    /// <para>
    /// Toggles and instrument buttons are not included: they do not occupy
    /// the column but stand at its left edge — the column's width is of no
    /// use to them.
    /// </para>
    /// </remarks>
    public IReadOnlyList<(string Key, double Width)> ControlWidths()
    {
        var found = new List<(string, double)>();
        foreach (var (key, editor) in _editors)
        {
            if (editor is CheckBox) continue;        // переключатель
            if (double.IsNaN(editor.Width)) continue; // растущий по месту
            found.Add((key, editor.Width));
        }
        return found;
    }

    /// <summary>What width a control is obliged to have.</summary>
    public static double WantedControlWidth => ControlWidth;

    /// <summary>Ready: the schema has arrived and been laid out.</summary>
    public event Action? Ready;

    public SettingsPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;

        // A download reports itself as an ordinary long task (§9), and this
        // page is where it is watched. Unsubscribed on unload: the page is
        // built afresh on every visit to the section, and a handler left
        // behind would keep a dead page updating its own controls.
        if (_link is not null)
        {
            _link.CoreEvent += OnTaskEvent;
            Unloaded += (_, _) => _link.CoreEvent -= OnTaskEvent;
        }

        // The gap is taken from a token rather than typed as a number:
        // "twice the usual" is `Sp.Danger`, and a second place with 64
        // written in it would part company with the first one day.
        Bottom.Margin = new Thickness(0, (double)FindResource("Sp.Danger"),
                                      0, 0);

        if (_link is null)
        {
            // Not as a line in the footer: an empty page with a note at
            // the bottom reads as "still loading" rather than as "nothing
            // to show".
            Empty.Content = EmptyState.For(
                S("Ядро не на связи"),
                S("Настройки хранит ядро, а связи с ним сейчас нет. Оболочка пробует поднять его заново."));
            Empty.Visibility = Visibility.Visible;
            Scroll.Visibility = Visibility.Collapsed;
            Bottom.Visibility = Visibility.Collapsed;
            return;
        }
        Loaded += async (_, _) => await LoadAsync();
    }

    private async Task LoadAsync()
    {
        var described = await Ask(Methods.SettingsDescribe);
        if (described?["schema"] is not JsonObject schema)
        {
            // Said out loud rather than returned from in silence. An empty
            // settings page looks like a page with no settings, and that is
            // indistinguishable from a page that could not ask. Whoever
            // meets it — a person or a check — is owed the difference.
            if (Note.Text.Length == 0)
                Note.Text = S("Настройки не пришли: ядро не описало их.");
            Ready?.Invoke();
            return;
        }

        // Two marks are skipped, and they mean different things.
        // `obsolete` is "replaced" (3.1.0's five palettes gave way to two
        // finishes). `secret` is "internal": the state of the store rather
        // than a setting, and there is no point showing it to a person, any
        // more than writing it to the log.
        foreach (var (key, spec) in schema)
            if (spec is JsonObject entry
                && entry["obsolete"] is null && entry["secret"] is null)
                _schema[key] = entry;

        var got = await Ask(Methods.SettingsGet, new JsonObject
        {
            ["keys"] = new JsonArray(_schema.Keys
                .Select(k => (JsonNode)k!).ToArray()),
        });
        if (got?["values"] is JsonObject values)
            foreach (var (key, value) in values)
                _values[key] = value?.DeepClone();

        await LoadOptionsAsync();
        Build();
        Ready?.Invoke();
    }

    /// <summary>
    /// Ask the core for the lists it declared changeable.
    /// </summary>
    /// <remarks>
    /// The schema says a set of values exists, but not which one: "which
    /// voices are installed" cannot be yesterday's answer. Devices,
    /// meanwhile, are enumerated by the shell — it is what knows them
    /// (<see cref="SettingsLayout.ShellKnows"/>).
    /// </remarks>
    private async Task LoadOptionsAsync()
    {
        _options.Clear();

        foreach (var key in SettingsLayout.ShellKnows)
        {
            if (!_schema.ContainsKey(key)) continue;

            if (key == "accent")
            {
                // The choices are those of the finish selected right now.
                var finish = _values.GetValueOrDefault("finish")
                                 ?.GetValue<string>() ?? "black";
                _options[key] = App.Accents(finish)
                    .Select(a => (a.Value, a.Title, true, "")).ToList();
                continue;
            }

            var devices = key == "input_device"
                ? Audio.Microphone.Devices()
                : Audio.Speaker.Devices();
            var listed = new List<(string, string, bool, string)>
            {
                ("default", S("Устройство по умолчанию"), true, ""),
            };
            listed.AddRange(devices.Select(d => (d.Name, d.Name, true, "")));
            _options[key] = listed;
        }

        var catalogue = await Ask(Methods.ModelsCatalogue);
        _models.Clear();
        foreach (var item in catalogue?["items"]?.AsArray() ?? [])
            if (item is JsonObject model)
            {
                _models.Add(model);
                var task = model["task_id"]?.GetValue<string>() ?? "";
                if (task.Length > 0)
                    _byTask[task] = model["id"]?.GetValue<string>() ?? "";
            }

        // What a hotkey can be assigned to belongs to the core: it is what
        // performs the actions, and it has the list. Without this the
        // dictionary fell through to the general editor and showed
        // "entries: 0" instead of a list of actions.
        if (_schema.ContainsKey("action_hotkeys"))
        {
            var listed = await Ask(Methods.HotkeysActions);
            var actions = (listed?["items"]?.AsArray().OfType<JsonObject>()
                           ?? [])
                .Select(a => (a["value"]?.GetValue<string>() ?? "",
                              a["title"]?.GetValue<string>() ?? "",
                              true, ""))
                .Where(a => a.Item1.Length > 0)
                .ToList();
            if (actions.Count > 0) _options["action_hotkeys"] = actions;
        }

        var dynamic = _schema.Where(pair => pair.Value["dynamic"] is not null)
                             .Select(pair => pair.Key).ToArray();
        if (dynamic.Length == 0) return;

        var told = await Ask(Methods.SettingsOptions, new JsonObject
        {
            ["keys"] = new JsonArray(dynamic.Select(k => (JsonNode)k!).ToArray()),
        });
        if (told?["options"] is not JsonObject answered) return;

        foreach (var (key, list) in answered)
        {
            if (list is not JsonArray items) continue;
            _options[key] = items.Select(item => (
                item?["value"]?.GetValue<string>() ?? "",
                item?["title"]?.GetValue<string>() ?? "",
                item?["available"]?.GetValue<bool>() ?? true,
                item?["reason"]?.GetValue<string>() ?? "")).ToList();
        }
    }

    private readonly Dictionary<string, List<(string Value, string Title,
                                              bool Available,
                                              string Reason)>> _options = [];

    private void Build()
    {
        Body.Children.Clear();
        _shelves.Clear();
        var placed = new HashSet<string>();

        foreach (var section in SettingsLayout.Sections)
        {
            var keys = section.Keys.Where(k => _schema.ContainsKey(k.Key))
                                   .ToArray();
            var sheets = (section.Sheets ?? [])
                .Where(s => s.Keys.Any(_schema.ContainsKey))
                .ToArray();
            if (keys.Length == 0 && sheets.Length == 0) continue;

            Body.Children.Add(BuildSection(section.Title,
                                           keys.Select(k => k.Key), sheets));
            foreach (var k in keys) placed.Add(k.Key);
            // A key behind a button is placed. Counting it a stranger would
            // print it twice — once in its window and once in "Other" —
            // and the second copy would edit the same setting from a place
            // nobody meant it to be edited from.
            foreach (var sheet in sheets)
                foreach (var key in sheet.Keys) placed.Add(key);
        }

        // The rule with teeth from ADR 0006: an unfamiliar key is shown,
        // not hidden. The core added a setting, the shell was not updated —
        // and without this section the setting would have become
        // unreachable unnoticed.
        var strangers = _schema.Keys
            .Where(k => !placed.Contains(k)
                        && !SettingsLayout.Elsewhere.Contains(k))
            .OrderBy(k => k, StringComparer.Ordinal)
            .ToArray();
        HasOtherSection = strangers.Length > 0;
        if (strangers.Length > 0)
            Body.Children.Add(BuildSection(SettingsLayout.Other, strangers));
        SectionsShown = Body.Children.Count;
        // The page's own columns, by the same measurement as a sheet's.
        Widen(_shelves.SelectMany(shelf => shelf.Rows).Select(row => row.Row));
        Sift();
    }

    /// <summary>
    /// A section, and what a person might call the things in it.
    /// </summary>
    /// <remarks>
    /// Gathered while the panel is built rather than read off the screen
    /// afterwards: the words are the ones the layout used — the name, the
    /// small print, the key — and they are known here and nowhere else.
    /// </remarks>
    private readonly List<(UIElement Whole, IReadOnlyList<(UIElement Row,
                           string Words)> Rows)> _shelves = [];

    /// <summary>
    /// Show only what the search matches.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Asked for: forty settings in nine sections is past the point where
    /// scrolling and reading is finding. Matched on the name, the
    /// explanation under it and the key the core uses — a person who read
    /// «tts_engine» in the log should find it by that.
    /// </para>
    /// <para>
    /// <b>Hidden, not rebuilt.</b> Rebuilding the panel on every
    /// keystroke would throw away the control a person is looking at, and
    /// with it whatever they had half-typed into it.
    /// </para>
    /// <para>
    /// A section whose rows have all gone goes with them: a heading over
    /// nothing is a promise that there is something under it.
    /// </para>
    /// </remarks>
    private void Sift()
    {
        var asked = (Find?.Text ?? "").Trim();
        Shown = 0;

        foreach (var (whole, rows) in _shelves)
        {
            var left = 0;
            foreach (var (row, words) in rows)
            {
                var fits = asked.Length == 0
                    || words.Contains(asked,
                                      StringComparison.CurrentCultureIgnoreCase);
                row.Visibility = fits ? Visibility.Visible
                                      : Visibility.Collapsed;
                if (fits) left++;
            }
            whole.Visibility = left > 0 ? Visibility.Visible
                                        : Visibility.Collapsed;
            Shown += left;
        }

        // Said out loud rather than left as an empty panel: an empty
        // panel is what a broken one looks like.
        if (Empty.Visibility == Visibility.Visible && asked.Length == 0) return;
        NoMatch.Visibility = Shown == 0 && asked.Length > 0
            ? Visibility.Visible : Visibility.Collapsed;
        NoMatch.Text = S("Ничего не нашлось по «{0}»", asked);
    }

    /// <summary>How many settings the search leaves — for the check.</summary>
    public int Shown { get; private set; }

    /// <summary>How many sections are left standing — for the check.</summary>
    public int ShelvesShown => _shelves.Count(
        shelf => shelf.Whole.Visibility == Visibility.Visible);

    /// <summary>
    /// The panel's ruling: how many rows, how many carry a seam, and how
    /// far their controls' left edges spread.
    /// </summary>
    /// <remarks>
    /// Two sentences a person said about this page — "too close to the
    /// line compared with everything else, and another one is missing" —
    /// as two numbers. The row that opens a sheet was built apart from
    /// the others: no seam of its own, and a button a hundred and fifty
    /// points right of every control on the page, because it reserved
    /// two columns where a row has three.
    /// </remarks>
    public (int Rows, int Seamed, double Spread, int Measured) Ruled()
    {
        // Laid out first: the widths are read off the arranged tree,
        // and the panel may have been rebuilt a moment ago.
        UpdateLayout();

        // **Every row, not every framed row.** The first version asked
        // only the borders, so a row built without one was not counted
        // as unseamed — it was not counted at all, and the break that
        // took the frame off the sheet openers stayed green.
        var rows = _shelves.SelectMany(shelf => shelf.Rows)
                           .Select(row => row.Row)
                           .OfType<FrameworkElement>()
                           .Where(row => row.IsVisible)
                           .ToArray();

        var seamed = 0;
        var edges = new List<double>();
        foreach (var row in rows)
        {
            if (row is Border { BorderThickness.Bottom: >= 1 }) seamed++;
            var grid = row as Grid ?? (row as Border)?.Child as Grid;
            var control = grid?.Children.OfType<FrameworkElement>()
                .FirstOrDefault(c => Grid.GetColumn(c) == 1
                                     && Grid.GetColumnSpan(c) == 1
                                     && c.ActualWidth > 0);
            if (control is null) continue;
            edges.Add(control.TransformToAncestor(Body)
                             .Transform(new Point(0, 0)).X);
        }
        return (rows.Length, seamed,
                edges.Count > 0 ? edges.Max() - edges.Min() : 0,
                edges.Count);
    }

    /// <summary>What the page says when nothing matched — for the check.</summary>
    public string NoMatchSaid => NoMatch.Visibility == Visibility.Visible
        ? NoMatch.Text : "";

    /// <summary>Search for this — for the check.</summary>
    public void FindForCheck(string asked)
    {
        Find.Text = asked;
        UpdateLayout();
    }

    private void OnFind(object sender, TextChangedEventArgs e) => Sift();

    //: What can be downloaded, and what is happening to it. Filled from
    //: `models.catalogue`, kept fresh by `task.progress`.
    private readonly List<JsonObject> _models = [];

    //: Which model each running task belongs to. The catalogue says so when
    //: the page opens; the events afterwards carry only a task id.
    private readonly Dictionary<string, string> _byTask = [];

    private readonly Dictionary<string, ProgressBar> _bars = [];
    private readonly Dictionary<string, TextBlock> _states = [];
    private readonly Dictionary<string, Button> _buttons = [];

    /// <summary>
    /// The models: what is downloaded, what is downloading, and the stop.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Its own block rather than a setting, because it is not one: a model
    /// is a file that is there or is not, and the thing a person wants to
    /// do about it is start or stop a transfer. Dressing that as a setting
    /// would give it a value to save and nothing to save it as.
    /// </para>
    /// <para>
    /// <b>Opened during a download, it shows the download.</b> The state
    /// comes with the catalogue rather than only from the events that
    /// follow: a page that learned about transfers only by watching them
    /// start would show a model as "not installed" halfway through fetching
    /// it, and offer to fetch it again.
    /// </para>
    /// </remarks>
    private UIElement BuildDownloads()
    {
        _bars.Clear();
        _states.Clear();
        _buttons.Clear();

        // Away from the seam above it, and inset on the right by exactly
        // as much as the controls are. Butted against the seam the heading
        // read as a caption belonging to the row above — reported as "too
        // close to the line compared with everything else"; and its
        // buttons ended sixteen points to the right of every control on
        // the sheet, which is the gap between the column and the control
        // standing in it. Sixteen written out here would be sixteen in two
        // places.
        var stack = new StackPanel
        {
            Margin = new Thickness(0, (double)FindResource("Sp.Between"),
                                   ControlColumn - ControlWidth,
                                   (double)FindResource("Sp.Between")),
        };
        stack.Children.Add(new TextBlock
        {
            Text = S("Скачивание моделей").ToUpperInvariant(),
            Style = (Style)FindResource("Text.Section"),
            Margin = new Thickness(0, 0, 0, 12),
        });

        foreach (var model in _models)
        {
            var id = model["id"]?.GetValue<string>() ?? "";
            var ours = model["ours"]?.GetValue<bool>() ?? false;
            var row = new Grid { Margin = new Thickness(0, 0, 0, 16) };
            row.ColumnDefinitions.Add(new ColumnDefinition());
            row.ColumnDefinitions.Add(new ColumnDefinition
            {
                Width = GridLength.Auto,
            });

            var left = new StackPanel();
            left.Children.Add(new TextBlock
            {
                Text = $"{model["title"]?.GetValue<string>()} · "
                       + Weighed(model["size"]?.GetValue<long>() ?? 0),
                Style = (Style)FindResource("Text.Body"),
            });

            var said = new TextBlock
            {
                Style = (Style)FindResource("Text.Meta"),
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 2, 16, 0),
            };
            left.Children.Add(said);
            _states[id] = said;

            var bar = new ProgressBar
            {
                Height = 3,
                Minimum = 0,
                Maximum = 1,
                Margin = new Thickness(0, 8, 16, 0),
                Visibility = Visibility.Collapsed,
                Foreground = (System.Windows.Media.Brush)
                    FindResource("C.Signal"),
                Background = (System.Windows.Media.Brush)
                    FindResource("C.FaceLow"),
                BorderThickness = new Thickness(0),
            };
            left.Children.Add(bar);
            _bars[id] = bar;

            row.Children.Add(left);

            var button = new Button
            {
                Style = (Style)FindResource("Btn"),
                Tag = id,
                MinWidth = 132,
                VerticalAlignment = VerticalAlignment.Top,
            };
            button.Click += OnModelButton;
            Grid.SetColumn(button, 1);
            row.Children.Add(button);
            _buttons[id] = button;

            stack.Children.Add(row);
            ShowModel(model, id, ours);
        }
        return stack;
    }

    /// <summary>Put one model's row into the state the catalogue reports.</summary>
    private void ShowModel(JsonObject model, string id, bool ours)
    {
        var installed = model["installed"]?.GetValue<bool>() ?? false;
        var state = model["state"]?.GetValue<string>() ?? "";
        var button = _buttons[id];
        var said = _states[id];
        var bar = _bars[id];

        if (state is "downloading" or "unpacking")
        {
            var done = model["done"]?.GetValue<long>() ?? 0;
            var total = model["total"]?.GetValue<long>() ?? 0;
            ShowRunning(id, state, done, total);
            _byTask[model["task_id"]?.GetValue<string>() ?? ""] = id;
            return;
        }

        bar.Visibility = Visibility.Collapsed;
        if (installed)
        {
            said.Text = S("Скачано.");
            button.Content = S("Скачано");
            button.IsEnabled = false;
        }
        else if (!ours)
        {
            said.Text = S("Скачается само при первом обращении.");
            button.Content = S("Скачается само");
            button.IsEnabled = false;
        }
        else
        {
            said.Text = model["note"]?.GetValue<string>() ?? "";
            // A package is installed, a model is downloaded. The same
            // button does both, and calling both "download" would leave a
            // person wondering where the thing they downloaded went.
            button.Content = model["kind"]?.GetValue<string>() == "package"
                ? S("Установить") : S("Скачать");
            button.IsEnabled = true;
        }
    }

    private void ShowRunning(string id, string state, long done, long total)
    {
        if (!_bars.TryGetValue(id, out var bar)) return;
        bar.Visibility = Visibility.Visible;
        // A share of one, not a percentage: the number is drawn here, and
        // whoever draws it decides how many digits fit.
        bar.Value = total > 0 ? Math.Clamp(done / (double)total, 0, 1) : 0;
        bar.IsIndeterminate = total <= 0;

        _states[id].Text = state == "unpacking"
            ? S("Распаковываю…")
            : S("{0} из {1}", Weighed(done), Weighed(total));
        _buttons[id].Content = S("Остановить");
        _buttons[id].IsEnabled = true;
    }

    private async void OnModelButton(object sender, RoutedEventArgs e)
    {
        if (sender is not Button button || button.Tag is not string id) return;

        var task = _byTask.FirstOrDefault(pair => pair.Value == id).Key;
        if (task is { Length: > 0 })
        {
            // Stopping goes through the ordinary task cancellation (§9):
            // a download is a long task, and it was deliberately not given
            // machinery of its own.
            await Ask(Methods.TaskCancel,
                      new JsonObject { ["task_id"] = task });
            return;
        }

        button.IsEnabled = false;
        var told = await Ask(Methods.ModelsFetch, new JsonObject
        {
            ["ids"] = new JsonArray(id),
        });
        foreach (var started in told?["tasks"]?.AsArray() ?? [])
            if (started is JsonObject one)
                _byTask[one["task_id"]?.GetValue<string>() ?? ""] =
                    one["id"]?.GetValue<string>() ?? "";
        ShowRunning(id, "downloading", 0, 0);
    }

    /// <summary>An event from the core: a download moved.</summary>
    private void OnTaskEvent(Envelope message)
    {
        var task = message.Payload["task_id"]?.GetValue<string>() ?? "";
        if (!_byTask.TryGetValue(task, out var id)) return;

        if (message.Method == "task.progress")
        {
            // The share comes ready-made; the bytes are in the note, which
            // the core wrote for a person to read.
            var share = message.Payload["fraction"]?.GetValue<double>() ?? -1;
            if (_bars.TryGetValue(id, out var bar))
            {
                bar.Visibility = Visibility.Visible;
                bar.IsIndeterminate = share < 0;
                if (share >= 0) bar.Value = Math.Clamp(share, 0, 1);
            }
            if (_states.TryGetValue(id, out var said))
                said.Text = message.Payload["note"]?.GetValue<string>() ?? "";
            if (_buttons.TryGetValue(id, out var stop))
                stop.Content = S("Остановить");
            return;
        }

        // Anything final: ask the catalogue again rather than working out
        // the new state here. Whether a model counts as installed is the
        // core's answer — it knows where the folder went — and guessing it
        // from "the task finished" would be right until the first failure
        // that still left a folder behind.
        if (message.Method is "task.done" or "task.failed" or "task.cancelled")
        {
            _byTask.Remove(task);
            _ = RefreshModelsAsync();
        }
    }

    private async Task RefreshModelsAsync()
    {
        var told = await Ask(Methods.ModelsCatalogue);
        if (told?["items"] is not JsonArray items) return;
        _models.Clear();
        foreach (var item in items)
            if (item is JsonObject model) _models.Add(model);
        Build();
    }

    /// <summary>Bytes as a person reads them.</summary>
    private static string Weighed(long bytes) =>
        bytes >= 1024L * 1024 * 1024
            ? S("{0} ГБ", (bytes / (1024.0 * 1024 * 1024)).ToString("0.0"))
            : S("{0} МБ", bytes / (1024 * 1024));

    /// <summary>How many keys the schema brought — for the check.</summary>
    public int SchemaKeys => _schema.Count;

    /// <summary>What went wrong while loading, if anything — for the check.</summary>
    public string Trouble => Note.Text;

    /// <summary>How many sections were drawn — for the check.</summary>
    public int SectionsShown { get; private set; }

    /// <summary>Is there an "Other" section — for the check.</summary>
    /// <remarks>
    /// It holds the keys the core sent and the layout has no place for
    /// (ADR 0006). Empty is the goal; **hiding** them would not be — a key
    /// with nowhere to go must be visible somewhere, or it becomes
    /// unreachable and nobody notices.
    /// </remarks>
    public bool HasOtherSection { get; private set; }

    private UIElement BuildSection(string title, IEnumerable<string> keys,
                                   Sheet[]? sheets = null)
    {
        var stack = new StackPanel { Margin = new Thickness(0, 0, 0, 32) };
        stack.Children.Add(new TextBlock
        {
            // Translated here: the layout holds a key (see SettingsLayout).
            Text = S(title).ToUpperInvariant(),
            Style = (Style)FindResource("Text.Section"),
            Margin = new Thickness(0, 0, 0, 12),
        });

        var rows = new List<(UIElement, string)>();
        foreach (var key in keys)
        {
            var row = BuildRow(key, ProbeColumn);
            stack.Children.Add(row);
            rows.Add((row, $"{SettingsLayout.TitleOf(key)} "
                           + $"{SettingsLayout.HintOf(key)} {key}"));
        }
        foreach (var sheet in sheets ?? [])
        {
            var row = BuildOpener(sheet);
            stack.Children.Add(row);
            rows.Add((row, $"{S(sheet.Title)} {S(sheet.Note)} "
                           + string.Join(" ", sheet.Keys)));
        }
        _shelves.Add((stack, rows));
        return stack;
    }

    /// <summary>A row that opens a list in a window of its own.</summary>
    /// <remarks>
    /// It looks like every other row — a name, an explanation, and a control
    /// in the same column — because it is one. What is behind it is a list
    /// rather than a switch, and that is the only difference a person needs
    /// to see.
    /// </remarks>
    private UIElement BuildOpener(Sheet sheet)
    {
        // **The same three columns as every other row.** Built with two,
        // its button had the check's column to itself and stood a
        // hundred and fifty points right of every control on the page.
        var row = Ranks(ProbeColumn);

        var left = Legend(S(sheet.Title), [S(sheet.Note)]);
        Grid.SetColumn(left, 0);
        row.Children.Add(left);

        var open = new Button
        {
            Style = (Style)FindResource("Btn"),
            Content = S("Открыть"),
            Width = ControlWidth,
            HorizontalAlignment = HorizontalAlignment.Left,
            VerticalAlignment = VerticalAlignment.Center,
        };
        open.Click += (_, _) => ShowSheet(sheet);
        Grid.SetColumn(open, 1);
        row.Children.Add(open);
        return Framed(row);
    }

    /// <summary>Open one list in its window.</summary>
    private void ShowSheet(Sheet sheet)
    {
        var window = MakeSheet(sheet);
        window.Owner = Window.GetWindow(this);
        window.ShowDialog();
    }

    /// <summary>The same window, built but not shown.</summary>
    /// <remarks>
    /// Split off so a check can measure a sheet. <c>ShowDialog</c> does
    /// not come back until a person closes the window, so a check that
    /// went through <c>ShowSheet</c> would hang rather than measure —
    /// and a sheet nobody can measure is how a button came to stand past
    /// the right edge for a whole release.
    /// </remarks>
    internal SheetWindow MakeSheet(Sheet sheet)
    {
        // The editors are built here, by the same code that would have put
        // them on the page. The window holds them and knows nothing about
        // settings: a window that could also build one would be a second
        // place where that is decided.
        // The check column is the page's, not every surface's. A sheet
        // holding words or hotkeys has nothing to check, and the hundred
        // and fifty points it reserved were taken off the editor: on the
        // hotkeys sheet the last button went past the edge — reported as
        // "the buttons are eaten".
        var probes = sheet.Keys.Any(HasProbe) ? ProbeColumn : 0;

        // A sheet of one key does not repeat its own name. The window is
        // headed «Слова активации / С этих слов начинается обращение к
        // Рине», and the row underneath said exactly that again, word for
        // word. A sheet of several needs the names: it is the only thing
        // telling Whisper's line from Vosk's.
        var alone = sheet.Keys.Length == 1;
        var rows = sheet.Keys.Where(_schema.ContainsKey)
                             .Select(k => BuildRow(k, probes, named: !alone))
                             .ToList();

        // The models are a list too, and they live behind the same kind of
        // button rather than at the bottom of the page where they landed
        // when they were new.
        if (sheet.Keys.Contains("whisper_model") && _models.Count > 0)
            rows.Add(BuildDownloads());

        Widen(rows);
        return new SheetWindow(S(sheet.Title), S(sheet.Note), rows);
    }

    /// <summary>
    /// Let each column fit the widest thing standing in it.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The page's control column is 316, and one control does not fit in
    /// it: the hotkey recorder — a field and two buttons — wants 364. On
    /// the page that never showed, because the hotkey moved onto a sheet
    /// of its own; on the sheet it stood out past the window, and the
    /// last button was simply not there. Reported as "the buttons are
    /// eaten".
    /// </para>
    /// <para>
    /// The check column went the same way for a smaller reason: it is a
    /// hundred and fifty, «Проверить микрофон» fitted in that in one
    /// typeface and lost its last three letters in the next. A width
    /// written down is a width measured against whatever was on the
    /// screen the day it was written.
    /// </para>
    /// <para>
    /// Widened rather than the control narrowed, and asked of the
    /// control — <c>Measure</c> — instead of written down again here,
    /// where it would go stale the first time a word changed length.
    /// </para>
    /// </remarks>
    private void Widen(IEnumerable<UIElement> rows)
    {
        var grids = rows.OfType<Border>()
                        .Select(border => border.Child)
                        .OfType<Grid>()
                        .Where(grid => grid.ColumnDefinitions.Count == 3)
                        .ToArray();
        if (grids.Length == 0) return;

        foreach (var column in new[] { 1, 2 })
        {
            var wanted = grids[0].ColumnDefinitions[column].Width.Value;
            // A column nobody stands in stays as it is — nought for a
            // sheet with nothing to check, and that is the point of it.
            if (wanted <= 0) continue;

            foreach (var child in grids
                         .SelectMany(g => g.Children.OfType<FrameworkElement>())
                         .Where(c => Grid.GetColumn(c) == column
                                     && Grid.GetColumnSpan(c) == 1))
            {
                child.Measure(new Size(double.PositiveInfinity,
                                       double.PositiveInfinity));
                wanted = Math.Max(wanted, child.DesiredSize.Width
                                          + child.Margin.Left
                                          + child.Margin.Right);
            }

            foreach (var grid in grids)
                grid.ColumnDefinitions[column].Width = new GridLength(wanted);
        }
    }

    /// <summary>
    /// Controls given less room than they asked for — for the check.
    /// </summary>
    /// <remarks>
    /// A button whose word does not fit says a different word:
    /// «Проверить микро». Reported by eye, and by eye is how it would
    /// come back — so it is a number: what the control asked for
    /// against what it got.
    /// </remarks>
    public (int Pinched, string Worst) Squeezed()
    {
        UpdateLayout();
        var worst = "";
        var over = 0.0;
        var pinched = 0;
        foreach (var control in _shelves
                     .SelectMany(shelf => shelf.Rows)
                     .SelectMany(row => Inside(row.Row))
                     .Where(c => c.IsVisible && c.ActualWidth > 0))
        {
            control.Measure(new Size(double.PositiveInfinity,
                                     double.PositiveInfinity));
            var short_ = control.DesiredSize.Width - control.ActualWidth;
            if (short_ <= 0.5) continue;
            pinched++;
            if (short_ <= over) continue;
            over = short_;
            worst = control is ContentControl { Content: { } said }
                ? $"«{said}» не хватило {short_:0}"              // not UI
                : $"{control.GetType().Name} не хватило {short_:0}"; // not UI
        }
        return (pinched, worst);
    }

    private static IEnumerable<FrameworkElement> Inside(UIElement row)
    {
        if (row is not Border { Child: Grid grid }) yield break;
        foreach (var child in grid.Children.OfType<FrameworkElement>())
            if (child is System.Windows.Controls.Primitives.ButtonBase
                      or ComboBox)
                yield return child;
    }

    /// <summary>
    /// The width of the column of controls.
    /// </summary>
    /// <remarks>
    /// One for the whole page. The column used to be "by content", and
    /// every row started its control where its own label ended — the right
    /// edge was ragged, and the panel read as a list rather than as an
    /// instrument.
    /// </remarks>
    private const double ControlColumn = 316;

    /// <summary>
    /// The width of the control itself inside the column.
    /// </summary>
    /// <remarks>
    /// One for every kind: dropdown, field, path, slider with a number.
    /// Each used to carry its own — 280, 200, 276 — and the right edge
    /// wandered by eighty points. On an instrument the controls stand in a
    /// column, and a column has two sides, not one.
    ///
    /// Twenty wider than it was, because the text face is. «Edge Neural
    /// (онлайн, естественный)» fitted in two hundred and eighty and lost
    /// its closing bracket the day the face changed: a column measured
    /// against one typeface is a column measured against nothing.
    /// </remarks>
    private const double ControlWidth = 300;

    /// <summary>The width of the checks column. Empty in most rows.</summary>
    private const double ProbeColumn = 150;

    /// <summary>The three columns every row on a panel stands in.</summary>
    /// <remarks>
    /// The control column is one width for the whole page: otherwise
    /// every row starts where its own label ended, and the right edge
    /// goes ragged. On a front panel the controls stand in a column.
    ///
    /// The third is for the check, and it is <b>also one width for every
    /// row</b>. With "by content", a row with a button took room from its
    /// own label, and its control drifted left of its neighbours':
    /// columns belong to the panel, not to the row.
    /// </remarks>
    private static Grid Ranks(double probeColumn)
    {
        var row = new Grid { MinHeight = 40 };
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(1, GridUnitType.Star),
        });
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(ControlColumn),
        });
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(probeColumn),
        });
        return row;
    }

    /// <summary>The name and the small print, in the first column.</summary>
    /// <remarks>
    /// The title wraps. Trimmed to the column it was cut mid-word —
    /// «Замечать, какие программы откры» — because the column is what is
    /// left after the control and the check have taken theirs. A name a
    /// person cannot read is not a name.
    /// </remarks>
    private StackPanel Legend(string title, IEnumerable<string> notes)
    {
        var label = new StackPanel
        {
            VerticalAlignment = VerticalAlignment.Center,
            // The gap between the legend and the control. Without it the
            // hint ran into the field, and two columns read as one.
            Margin = new Thickness(0, 0, 24, 0),
        };
        label.Children.Add(new TextBlock
        {
            Text = title,
            Style = (Style)FindResource("Text.Body"),
            TextWrapping = TextWrapping.Wrap,
        });

        var said = notes.Where(n => n.Length > 0).ToArray();
        if (said.Length > 0)
            label.Children.Add(new TextBlock
            {
                Text = string.Join(" · ", said),
                Style = (Style)FindResource("Text.Meta"),
                Margin = new Thickness(0, 2, 0, 0),
                TextWrapping = TextWrapping.Wrap,
            });
        return label;
    }

    /// <summary>
    /// A row in its frame: the padding, and the seam under it.
    /// </summary>
    /// <remarks>
    /// A hairline seam between settings — the same device as in the
    /// lists: areas of a panel are separated by value and by a seam, not
    /// by emptiness between tiles.
    ///
    /// <b>One frame for every kind of row.</b> The row that opens a sheet
    /// used to be built apart from this — a bare grid with sixteen points
    /// under it — so it had no seam of its own and stood hard against the
    /// one above. Reported as "too close to the line compared with
    /// everything else, and another one is missing". Both were the same
    /// omission.
    /// </remarks>
    private Border Framed(UIElement row) => new()
    {
        BorderBrush = (System.Windows.Media.Brush)FindResource("C.Seam"),
        BorderThickness = new Thickness(0, 0, 0, 1),
        Padding = new Thickness(0, 8, 0, 10),
        Child = row,
    };

    private UIElement BuildRow(string key, double probeColumn,
                               bool named = true)
    {
        var spec = _schema[key];
        var row = Ranks(probeColumn);

        var notes = new List<string>();
        if (SettingsLayout.HintOf(key).Length > 0)
            notes.Add(SettingsLayout.HintOf(key));
        if (spec["restart_required"] is not null)
            notes.Add(S("применится после перезапуска"));
        if (!SettingsLayout.Known.Contains(key))
            notes.Add(S("ключ {0} оболочке незнаком", key));

        var label = Legend(SettingsLayout.TitleOf(key), notes);
        Grid.SetColumn(label, 0);
        if (named) row.Children.Add(label);

        var editor = BuildEditor(key, spec);
        _editors[key] = editor;

        // The check stands alongside, but in a column of its own.
        if (BuildProbe(key) is { } probe)
        {
            Grid.SetColumn(probe, 2);
            probe.VerticalAlignment = VerticalAlignment.Center;
            probe.Margin = new Thickness(8, 0, 0, 0);
            row.Children.Add(probe);
        }

        // A list editor goes under the label at full width. Alongside it
        // is cramped: the label squeezes into a column of letters, and it
        // still does not fit. The mark is the value's make-up, not the
        // key's name: a new setting of the same sort will get this by
        // itself.
        var type = spec["type"]?.GetValue<string>() ?? "string";
        if (type is "array" or "object")
        {
            row.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            row.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            Grid.SetRow(editor, named ? 1 : 0);
            Grid.SetColumn(editor, 0);
            Grid.SetColumnSpan(editor, 3);
            // Stretched, not left: the rows inside are two columns, and a
            // column that is only as wide as its contents is not a column
            // — the buttons huddled against the words in the left half of
            // the window with three hundred points of nothing beside them.
            editor.HorizontalAlignment = HorizontalAlignment.Stretch;
            editor.Margin = new Thickness(0, named ? 8 : 0, 0, 0);
        }
        else
        {
            Grid.SetColumn(editor, 1);
            // Left inside its own column, not right along the window's
            // edge: a shared left edge is what makes a column out of
            // controls.
            editor.HorizontalAlignment = HorizontalAlignment.Left;
            editor.VerticalAlignment = VerticalAlignment.Center;
        }
        row.Children.Add(editor);

        ApplyDependency(key, spec, row);
        return Framed(row);
    }

    /// <summary>Whether this setting has a check of its own.</summary>
    /// <remarks>
    /// Asked before the row is built, because the column for it is
    /// reserved across the whole surface — and a surface with nothing to
    /// check must not reserve it.
    /// </remarks>
    private static bool HasProbe(string key) =>
        key is "voice" or "input_device";

    /// <summary>
    /// A check next to the setting it checks.
    /// </summary>
    /// <remarks>
    /// <para>
    /// A sound setting without a check is a blind choice: a person picks
    /// the engine, the voice and the device, and finds out whether it works
    /// the next time they talk to Rina. So the button stands here and not
    /// in a separate "diagnostics" nobody visits.
    /// </para>
    /// <para>
    /// The voice is checked by the core — it is what synthesises; the
    /// microphone by the shell — the devices are its. The same boundary as
    /// everywhere (ADR 0009).
    /// </para>
    /// </remarks>
    private FrameworkElement? BuildProbe(string key)
    {
        if (!HasProbe(key)) return null;

        var probe = new Button
        {
            Style = (Style)FindResource("Btn"),
            Content = key == "voice" ? S("Проверить голос")
                                     : S("Проверить микрофон"),
            Margin = new Thickness(8, 0, 0, 0),
            VerticalAlignment = VerticalAlignment.Center,
        };
        probe.Click += async (_, _) =>
        {
            probe.IsEnabled = false;
            try
            {
                if (key == "voice") await TestVoiceAsync();
                else await TestMicrophoneAsync();
            }
            finally { probe.IsEnabled = true; }
        };
        return probe;
    }

    /// <summary>Say a test phrase and hear it.</summary>
    private async Task TestVoiceAsync()
    {
        Note.Text = S("Говорю…");
        Note.SetResourceReference(ForegroundProperty, "C.InkFaint");

        var answer = await Ask(Methods.SpeechTest);
        if (answer is null) return;

        var ok = answer["ok"]?.GetValue<bool>() ?? false;
        // Saying "it worked" is not enough: the person may not have heard
        // it, and then the matter is not the synthesis but the output
        // device. Hence the duration too.
        Note.Text = ok
            ? S("Сказала: «{0}» — {1} с. Не слышно? Проверьте динамик.",
                answer["text"]?.GetValue<string>() ?? "",
                answer["seconds"]?.GetValue<double>() ?? 0)
            : S("Не вышло: {0}", answer["reason"]?.GetValue<string>() ?? "");
        Note.SetResourceReference(ForegroundProperty,
                                  ok ? "C.InkFaint" : "C.Signal");
    }

    /// <summary>
    /// Listen to the microphone for a couple of seconds and say what can be
    /// heard.
    /// </summary>
    /// <remarks>
    /// What is checked is the <b>level</b>, not recognition: "can you be
    /// heard at all" and "does she understand the words" are different
    /// questions, and the first one answers most complaints. It also means
    /// the check works where recognition is switched off.
    /// </remarks>
    private async Task TestMicrophoneAsync()
    {
        var device = _values.GetValueOrDefault("input_device")
                         ?.GetValue<string>() ?? "default";
        Note.Text = S("Слушаю две секунды — скажите что-нибудь…");
        Note.SetResourceReference(ForegroundProperty, "C.InkFaint");

        var (ok, loudest, reason) = await Audio.Microphone.ProbeAsync(
            device, TimeSpan.FromSeconds(2));

        if (!ok)
        {
            Note.Text = S("Микрофон не отозвался: {0}", reason);
            Note.SetResourceReference(ForegroundProperty, "C.Signal");
            return;
        }

        // The threshold comes from experience: below five per cent is the
        // silence of a room, not a voice. The exact number matters less
        // here than the person being told what to do next.
        var heard = loudest >= 0.05f;
        Note.Text = heard
            ? S("Слышно: {0}%. Микрофон работает.", (int)(loudest * 100))
            // As one string rather than glued together: a glued one gets
            // translated in pieces, and the table ends up with two
            // fragments instead of a phrase.
            : S("Почти тихо: {0}%. Проверьте, тот ли микрофон выбран.",
                (int)(loudest * 100));
        Note.SetResourceReference(ForegroundProperty,
                                  heard ? "C.InkFaint" : "C.Signal");
    }

    private FrameworkElement BuildEditor(string key, JsonObject spec)
    {
        var type = spec["type"]?.GetValue<string>() ?? "string";
        var value = _values.GetValueOrDefault(key);

        // The order of the checks goes from the value's make-up to its
        // set, not the other way round. A list and a dictionary are edited
        // in their own way, whatever the core enumerated about them: for
        // "action hotkeys" what is enumerated are the dictionary's
        // **keys**, and reading it as a string means dropping the page —
        // which is exactly what happened on the very first live run.
        // A hotkey is pressed, not typed: one typed as a string is a
        // request to know how we spell it, and the person will notice their
        // mistake only from the keys not working.
        if (key == "hotkey")
        {
            var box = new HotkeyBox(value?.GetValue<string>() ?? "");
            box.Changed += async written => await SaveAsync(key, written);
            return box;
        }

        // A number whose both bounds the core has named is dragged, not
        // typed. The rule is general rather than a list of keys: a setting
        // that gains bounds will get a slider by itself.
        if (type is "integer" or "number"
            && spec["low"] is not null && spec["high"] is not null)
        {
            var low = spec["low"]!.GetValue<double>();
            var high = spec["high"]!.GetValue<double>();
            // Too wide a range cannot be set with a mouse: one second out
            // of six hundred would have to be caught. Such a thing stays a
            // field.
            if (high - low <= 200)
                return BuildSlider(key, low, high, type == "integer",
                                   value?.GetValue<double>() ?? low);
        }

        if (type == "array")
            // The folder list has both the "array" type and the "path"
            // format. The array decides how it is edited; the format, how
            // things are added.
            return BuildList(key, value as JsonArray,
                             spec["format"]?.GetValue<string>() ?? "");

        // A dictionary whose keys the core enumerated is not "a counter
        // and forget everything" but a list: a row of its own for every
        // known action.
        if (type == "object")
            return _options.TryGetValue(key, out var actions)
                   && actions.Count > 0
                ? BuildAssignments(key, actions, value as JsonObject)
                : BuildMap(key, value as JsonObject);

        // A list of known values is a dropdown, not a line of text. The
        // set came from whoever knows it: from the core or from the shell.
        if (_options.TryGetValue(key, out var known))
            return known.Count > 0
                ? BuildChoice(key, known, value?.GetValue<string>() ?? "")
                : Nothing();

        if (spec["format"]?.GetValue<string>() is { } format)
            return BuildPath(key, format, Show(value));

        if (type == "boolean")
        {
            var toggle = new CheckBox
            {
                Style = (Style)FindResource("Toggle"),
                IsChecked = value?.GetValue<bool>() ?? false,
                VerticalAlignment = VerticalAlignment.Center,
            };
            toggle.Click += async (_, _) =>
                await SaveAsync(key, toggle.IsChecked == true);
            return toggle;
        }

        if (spec["choices"] is JsonArray choices)
        {
            var box = new ComboBox
            {
                Style = (Style)FindResource("Choice"),
                Width = ControlWidth,
                ItemsSource = choices.Select(c => c!.GetValue<string>()).ToArray(),
                SelectedItem = value?.GetValue<string>(),
            };
            box.SelectionChanged += async (_, _) =>
            {
                if (box.SelectedItem is string chosen)
                    await SaveAsync(key, chosen);
            };
            return box;
        }

        var field = new TextBox
        {
            Style = (Style)FindResource("Field"),
            Width = ControlWidth,
            Text = Show(value),
        };
        Styles.Ui.SetHint(field, SettingsLayout.HintInField(key));
        field.LostFocus += async (_, _) => await SaveAsync(key, Parse(field.Text, type));
        return field;
    }

    /// <summary>
    /// A dropdown. What is unavailable is shown but cannot be chosen.
    /// </summary>
    /// <remarks>
    /// An engine that is not installed must not be hidden: the person will
    /// not learn that such a thing exists at all and will go looking for it
    /// on the internet while standing in front of a list that has it.
    /// Shown and dimmed is the answer "such a thing exists, but you do not
    /// have it installed".
    /// </remarks>
    private FrameworkElement BuildChoice(string key,
        List<(string Value, string Title, bool Available, string Reason)> known,
        string current)
    {
        var box = new ComboBox
        {
            Style = (Style)FindResource("Choice"),
            Width = ControlWidth,
        };
        foreach (var (value, title, available, reason) in known)
            box.Items.Add(new ComboBoxItem
            {
                // Dimmed **and** told why. "Vosk is unavailable" in front of
                // a person who has downloaded the model and set the path
                // says nothing they can act on; the core knew all along that
                // what was missing was the package, and simply kept it.
                Content = available || reason.Length == 0
                    ? (title.Length > 0 ? title : value)
                    : $"{(title.Length > 0 ? title : value)} — {reason}",
                Tag = value,
                IsEnabled = available,
                ToolTip = reason.Length > 0 ? reason : null,
            });

        box.SelectedItem = box.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == current);

        // The saved value may be absent from today's set: the engine was
        // changed, the model deleted. An empty list is the worst of
        // answers: it looks like "nothing is chosen" when something is, and
        // it works.
        if (box.SelectedItem is null && current.Length > 0)
        {
            var stale = new ComboBoxItem
            {
                Content = S("{0} — сейчас недоступно", current),
                Tag = current,
            };
            box.Items.Insert(0, stale);
            box.SelectedItem = stale;
        }
        box.SelectionChanged += async (_, _) =>
        {
            if (box.SelectedItem is ComboBoxItem { Tag: string chosen })
                await SaveAsync(key, chosen);
        };
        return box;
    }

    /// <summary>
    /// There is nothing to choose from — and that has to be said rather
    /// than answered with an input field.
    /// </summary>
    /// <remarks>
    /// "No voice" has no voices. A field one can type anything into would
    /// promise that what was typed will work.
    /// </remarks>
    private FrameworkElement Nothing()
    {
        var box = new ComboBox
        {
            Style = (Style)FindResource("Choice"),
            Width = ControlWidth,
            IsEnabled = false,
        };
        box.Items.Add(new ComboBoxItem { Content = S("выбирать не из чего") });
        box.SelectedIndex = 0;
        return box;
    }

    /// <summary>
    /// A slider with the value beside it.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The number is always visible: a slider answers "roughly how much"
    /// and does not answer "exactly how much", and a person who needs
    /// exactly eighty would otherwise be doomed to push a mouse around.
    /// </para>
    /// <para>
    /// <b>We save on release, not on every movement.</b> Otherwise dragging
    /// from zero to a hundred is a hundred requests to the core and a
    /// hundred writes to disk.
    /// </para>
    /// </remarks>
    private FrameworkElement BuildSlider(string key, double low, double high,
                                         bool whole, double current)
    {
        // The same grid as for a path: the track takes the remainder, the
        // number stands at the column's right edge. The track used to carry
        // its own width, and the number ended up now closer to the edge,
        // now further from it.
        var row = new Grid
        {
            Width = ControlWidth,
            VerticalAlignment = VerticalAlignment.Center,
        };
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(1, GridUnitType.Star),
        });
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });

        var slider = new Slider
        {
            Style = (Style)FindResource("Slide"),
            Minimum = low,
            Maximum = high,
            Value = Math.Clamp(current, low, high),
            IsSnapToTickEnabled = whole,
            TickFrequency = whole ? 1 : (high - low) / 20,
            SmallChange = whole ? 1 : (high - low) / 20,
            LargeChange = whole ? Math.Max(1, (high - low) / 10)
                                : (high - low) / 10,
        };

        var shown = new TextBlock
        {
            Style = (Style)FindResource("Text.Body"),
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(12, 0, 0, 0),
            MinWidth = 44,
            TextAlignment = TextAlignment.Right,
            Text = Format(slider.Value, whole),
        };

        slider.ValueChanged += (_, _) =>
            shown.Text = Format(slider.Value, whole);

        // The mouse was released or the keyboard left — that is when we save.
        slider.PreviewMouseUp += async (_, _) => await SaveSliderAsync(
            key, slider.Value, whole);
        slider.LostKeyboardFocus += async (_, _) => await SaveSliderAsync(
            key, slider.Value, whole);

        Grid.SetColumn(slider, 0);
        Grid.SetColumn(shown, 1);
        row.Children.Add(slider);
        row.Children.Add(shown);
        return row;
    }

    private static string Format(double value, bool whole)
        => whole ? ((int)Math.Round(value)).ToString()
                 : value.ToString("0.00");

    private async Task SaveSliderAsync(string key, double value, bool whole)
    {
        JsonNode node = whole ? (int)Math.Round(value)
                              : Math.Round(value, 2);
        // We do not trouble the core if the value is the same: a mouse
        // released without moving is no reason to write to disk.
        if (_values.GetValueOrDefault(key)?.GetValue<double>() is { } was
            && Math.Abs(was - node.GetValue<double>()) < 1e-9)
            return;
        await SaveAsync(key, node);
    }

    /// <summary>A path: a field and "Browse…".</summary>
    private FrameworkElement BuildPath(string key, string format, string current)
    {
        // A grid, not a row: the field takes everything the button leaves,
        // and the right edge lines up with the neighbouring controls.
        var row = new Grid { Width = ControlWidth };
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(1, GridUnitType.Star),
        });
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });
        var field = new TextBox
        {
            Style = (Style)FindResource("Field"),
            Text = current,
            IsReadOnly = true,
            ToolTip = current,
        };
        Styles.Ui.SetHint(field, SettingsLayout.HintInField(key));
        var browse = new Button
        {
            Style = (Style)FindResource("Btn"),
            Content = S("Обзор…"),
            Margin = new Thickness(8, 0, 0, 0),
        };
        browse.Click += async (_, _) =>
        {
            var picked = format == "folder" ? PickFolder() : PickFile();
            if (picked is null) return;
            field.Text = picked;
            field.ToolTip = picked;
            await SaveAsync(key, picked);
        };
        Grid.SetColumn(field, 0);
        Grid.SetColumn(browse, 1);
        row.Children.Add(field);
        row.Children.Add(browse);
        return row;
    }

    private static string? PickFolder()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = S("Где лежит модель"),
        };
        return dialog.ShowDialog() == true ? dialog.FolderName : null;
    }

    private static string? PickFile()
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Title = S("Выберите файл модели"),
            Filter = S("Модели (*.onnx;*.bin;*.pt)|*.onnx;*.bin;*.pt|Все файлы|*.*"),
        };
        return dialog.ShowDialog() == true ? dialog.FileName : null;
    }

    /// <summary>
    /// A value, and the button that does something to it.
    /// </summary>
    /// <remarks>
    /// <para>
    /// <b>A row is two columns, not two things in a line.</b> Laid out one
    /// after another, every button started where its own word ended: six
    /// words of different lengths gave six buttons at six different
    /// places, and the short words had the button pressed right up
    /// against them. Reported as "this looks bad".
    /// </para>
    /// <para>
    /// So the value takes what there is and the button stands at the
    /// right edge — the same edge for every row, the way the controls on
    /// the page stand in a column. What does not fit is trimmed with an
    /// ellipsis and kept whole in the tooltip.
    /// </para>
    /// </remarks>
    private ValueLine ValueRow(FrameworkElement value, FrameworkElement act)
    {
        var row = new ValueLine { Margin = new Thickness(0, 0, 0, Tight) };
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(1, GridUnitType.Star),
        });
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });
        value.VerticalAlignment = VerticalAlignment.Center;
        value.Margin = new Thickness(0, 0, Inner, 0);
        act.HorizontalAlignment = HorizontalAlignment.Right;
        Grid.SetColumn(value, 0);
        Grid.SetColumn(act, 1);
        row.Children.Add(value);
        row.Children.Add(act);
        return row;
    }

    /// <summary>The space between things inside one row.</summary>
    private double Inner => (double)FindResource("Sp.Inner");

    /// <summary>The space between rows of one list.</summary>
    private double Tight => (double)FindResource("Sp.Tight");

    /// <summary>
    /// A word with a cross in it.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Asked for: "make the wake words and the learned matches into
    /// tags, drop the «Убрать» button and put a cross in the tag
    /// itself". It is the better shape for the thing: six wake words in
    /// a column of rows is a table of one column, and a table of one
    /// column is a list pretending to be data. They are labels, and
    /// labels sit side by side and wrap.
    /// </para>
    /// <para>
    /// <b>The cross is a button with a name.</b> A cross says nothing
    /// to a screen reader and nothing to somebody who has not met the
    /// convention, so it carries «убрать „Рина“» as its automation name
    /// and the same as its tooltip. A mark that only works for people
    /// who already know it is decoration.
    /// </para>
    /// </remarks>
    private Border Chip(string said, string full, Action drop)
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal };
        row.Children.Add(new TextBlock
        {
            Text = said,
            Style = (Style)FindResource("Text.Body"),
            VerticalAlignment = VerticalAlignment.Center,
            MaxWidth = 320,
            TextTrimming = TextTrimming.CharacterEllipsis,
        });

        var cross = new Button
        {
            Style = (Style)FindResource("Btn.Cross"),
            Content = "\uE711",                          // not UI
            Margin = new Thickness(Tight, 0, 0, 0),
            ToolTip = S("Убрать «{0}»", full),
        };
        System.Windows.Automation.AutomationProperties.SetName(
            cross, S("Убрать «{0}»", full));
        cross.Click += (_, _) => drop();
        row.Children.Add(cross);

        return new Border
        {
            Background = (System.Windows.Media.Brush)
                FindResource("C.Glass.Control"),
            BorderBrush = (System.Windows.Media.Brush)FindResource("C.Seam"),
            BorderThickness = new Thickness(1),
            CornerRadius = (CornerRadius)FindResource("Radius.Max"),
            Padding = new Thickness(Inner, 4, 4, 4),
            Margin = new Thickness(0, 0, Tight, Tight),
            ToolTip = full,
            Child = row,
        };
    }

    /// <summary>Where tags live: side by side, wrapping.</summary>
    private static WrapPanel Field() => new()
    {
        Orientation = Orientation.Horizontal,
    };

    /// <summary>
    /// A folder as a card: what it is called, and where it is.
    /// </summary>
    /// <remarks>
    /// Asked for. A path in one trimmed line answers neither question a
    /// person has — «C:\Users\…\vosk-model-small…» told them which
    /// folder only if they could read the middle of it, and the middle
    /// is what the ellipsis ate. The last part of the path is the name;
    /// the whole of it stands underneath, wrapped, because it is the
    /// part one checks.
    /// </remarks>
    private Border Card(string path, Action drop)
    {
        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(1, GridUnitType.Star),
        });
        grid.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });

        var named = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        named.Children.Add(new TextBlock
        {
            Text = Leaf(path),
            Style = (Style)FindResource("Text.Body"),
            TextTrimming = TextTrimming.CharacterEllipsis,
        });
        named.Children.Add(new TextBlock
        {
            Text = path,
            Style = (Style)FindResource("Text.Meta"),
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 2, Inner, 0),
        });
        Grid.SetColumn(named, 0);
        grid.Children.Add(named);

        var cross = new Button
        {
            Style = (Style)FindResource("Btn.Cross"),
            Content = "\uE711",                          // not UI
            VerticalAlignment = VerticalAlignment.Top,
            ToolTip = S("Убрать «{0}»", path),
        };
        System.Windows.Automation.AutomationProperties.SetName(
            cross, S("Убрать «{0}»", path));
        cross.Click += (_, _) => drop();
        Grid.SetColumn(cross, 1);
        grid.Children.Add(cross);

        return new Border
        {
            Style = (Style)FindResource("Card"),
            Margin = new Thickness(0, 0, 0, Tight),
            Child = grid,
        };
    }

    /// <summary>The last part of a path — what the folder is called.</summary>
    private static string Leaf(string path)
    {
        var cut = path.TrimEnd('\\', '/');
        var at = cut.LastIndexOfAny(['\\', '/']);
        return at >= 0 && at + 1 < cut.Length ? cut[(at + 1)..] : cut;
    }

    /// <summary>
    /// A list: what is in it, what to add, what to take away.
    /// </summary>
    /// <remarks>
    /// A comma-separated string instead of a list would be an invitation to
    /// lose a path with a comma in its name. Here things are added and
    /// removed one at a time.
    /// </remarks>
    private FrameworkElement BuildList(string key, JsonArray? current,
                                       string format)
    {
        var items = (current ?? []).Select(v => v?.GetValue<string>() ?? "")
                                   .Where(v => v.Length > 0).ToList();
        var stack = new StackPanel();

        async void Drop(string what)
        {
            items.Remove(what);
            await SaveAsync(key, new JsonArray(
                items.Select(v => (JsonNode)v!).ToArray()));
        }

        // A path is a card and a word is a tag. The mark is the value's
        // make-up, not the key's name: a new list of folders will be
        // cards by itself.
        if (format == "folder")
        {
            foreach (var item in items)
                stack.Children.Add(Card(item, () => Drop(item)));
        }
        else
        {
            var field = Field();
            foreach (var item in items)
                field.Children.Add(Chip(item, item, () => Drop(item)));
            if (items.Count > 0) stack.Children.Add(field);
        }

        async Task AddAsync(string what)
        {
            if (what.Length == 0 || items.Contains(what)) return;
            items.Add(what);
            await SaveAsync(key, new JsonArray(
                items.Select(v => (JsonNode)v!).ToArray()));
        }

        var adding = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Margin = new Thickness(0, Inner, 0, 0),
        };

        // A folder is picked with a dialogue, a word is typed. One button
        // for both cases would mean either a mistyped path or picking a
        // folder instead of a word.
        if (format == "folder")
        {
            var add = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Добавить папку…"),
            };
            add.Click += async (_, _) =>
            {
                if (PickFolder() is { } folder) await AddAsync(folder);
            };
            adding.Children.Add(add);
        }
        else
        {
            var typed = new TextBox
            {
                Style = (Style)FindResource("Field"),
                Width = 170,
                Margin = new Thickness(0, 0, Inner, 0),
            };
            Styles.Ui.SetHint(typed, S("новое слово"));
            var add = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Добавить"),
            };
            add.Click += async (_, _) =>
            {
                await AddAsync(typed.Text.Trim());
                typed.Clear();
            };
            adding.Children.Add(typed);
            adding.Children.Add(add);
        }
        stack.Children.Add(adding);
        return stack;
    }

    /// <summary>
    /// Assignments: a row for every known action.
    /// </summary>
    /// <remarks>
    /// "Entries: 0 · reset all" was honest exactly as long as there was
    /// nowhere to assign a hotkey. A person who sees the counter learns
    /// neither what actions exist nor how to bind to them — and the core
    /// has the list of actions, and it sent it.
    ///
    /// A hotkey is <b>recorded by pressing it</b>. The first edition had it
    /// typed as a string, with an explanation alongside: intercepting the
    /// press would mean the window listening to the whole keyboard. The
    /// explanation was wrong. <c>Hotkeys</c> avoids a <b>global
    /// interceptor</b> — the kind that sees what is typed in other
    /// people's windows; a field reading a press while it holds focus gets
    /// the same events the window receives anyway.
    /// </remarks>
    private FrameworkElement BuildAssignments(string key,
        List<(string Value, string Title, bool Available, string Reason)> actions,
        JsonObject? current)
    {
        var stack = new StackPanel();
        var assigned = new JsonObject();
        foreach (var (name, _t, _a, _r) in actions)
        {
            var combination = current?[name]?.GetValue<string>() ?? "";
            if (combination.Length > 0) assigned[name] = combination;
        }

        foreach (var (name, title, _, _) in actions)
        {
            var named = new TextBlock
            {
                Text = title,
                Style = (Style)FindResource("Text.Meta"),
                TextTrimming = TextTrimming.CharacterEllipsis,
                ToolTip = title,
            };

            var box = new HotkeyBox(current?[name]?.GetValue<string>() ?? "");
            var action = name;
            box.Changed += async written =>
            {
                var next = new JsonObject();
                foreach (var (existing, node) in assigned)
                    if (existing != action && node is not null)
                        next[existing] = node.DeepClone();
                // Empty means "unassign", not "assign emptiness": the key
                // is removed rather than left with an empty string.
                if (written.Length > 0) next[action] = written;
                await SaveAsync(key, next);
            };
            stack.Children.Add(ValueRow(named, box));
        }
        return stack;
    }

    /// <summary>
    /// A dictionary: what has been learned, and how to forget one or all.
    /// </summary>
    /// <remarks>
    /// <para>
    /// The first edition showed only a counter and "forget all", on the
    /// argument that a person does not remember which word got bound to
    /// what. The argument turned out to be half of one: <b>if they do not
    /// remember, then it has to be shown</b>. A person who noticed that
    /// Rina opens the wrong "studio" wants to unbind that one, not to
    /// forget six correct associations along with it.
    /// </para>
    /// <para>
    /// "Forget all" stays: when the muddle is general, going through them
    /// one by one is work without a reason.
    /// </para>
    /// </remarks>
    private FrameworkElement BuildMap(string key, JsonObject? current)
    {
        var stack = new StackPanel();

        var learned = Field();
        foreach (var (word, bound) in current ?? [])
        {
            var said = DescribeBinding(word, bound);
            var forgotten = word;
            async void Forget()
            {
                var left = new JsonObject();
                foreach (var (other, value) in current ?? [])
                    if (other != forgotten)
                        left[other] = value?.DeepClone();
                await SaveAsync(key, left);
            }
            learned.Children.Add(Chip(said, said, Forget));
        }
        if (learned.Children.Count > 0) stack.Children.Add(learned);

        var counted = new TextBlock
        {
            Text = S("записей: {0}", current?.Count ?? 0),
            Style = (Style)FindResource("Text.Meta"),
        };
        var forget = new Button
        {
            Style = (Style)FindResource("Btn"),
            Content = SettingsLayout.ClearWordOf(key),
            IsEnabled = (current?.Count ?? 0) > 0,
        };
        forget.Click += async (_, _) => await SaveAsync(key, new JsonObject());
        var row = ValueRow(counted, forget);
        row.Margin = new Thickness(0, Inner, 0, 0);
        stack.Children.Add(row);
        return stack;
    }

    /// <summary>
    /// "word → what it is bound to" in human words.
    /// </summary>
    /// <remarks>
    /// A learned program stores not only a path but a name — and that is
    /// what we show: a hundred-character path does not answer the question
    /// of what program this is. An action hotkey stores a string and is
    /// shown as it is.
    /// </remarks>
    private static string DescribeBinding(string word, JsonNode? bound)
    {
        var named = bound switch
        {
            JsonObject entry =>
                entry["name"]?.GetValue<string>()
                ?? entry["path"]?.GetValue<string>() ?? "",
            null => "",
            _ => bound.ToString(),
        };
        return named.Length > 0 ? $"«{word}» → {named}" : $"«{word}»";
    }

    /// <summary>
    /// Dim a field if it depends on something switched off.
    /// </summary>
    /// <remarks>
    /// The core knows the dependency: only it understands that "model
    /// address" means nothing without "answer with a model". The shell only
    /// shows it.
    /// </remarks>
    private void ApplyDependency(string key, JsonObject spec, Grid row)
    {
        if (spec["depends_on"]?.GetValue<string>() is not { } master) return;
        var on = _values.GetValueOrDefault(master)?.GetValue<bool>() ?? false;
        row.IsEnabled = on;
        row.Opacity = on ? 1.0 : 0.5;
    }

    private static string Show(JsonNode? value) => value switch
    {
        null => "",
        JsonArray array => string.Join(", ",
            array.Select(v => v?.ToString() ?? "")),
        JsonObject => "…",
        _ => value.ToString(),
    };

    private static JsonNode? Parse(string text, string type) => type switch
    {
        "integer" => int.TryParse(text, out var i) ? i : null,
        "number" => double.TryParse(text, out var d) ? d : null,
        "array" => new JsonArray(text.Split(',')
            .Select(p => p.Trim()).Where(p => p.Length > 0)
            .Select(p => (JsonNode)p!).ToArray()),
        _ => text,
    };

    private async Task SaveAsync(string key, JsonNode? value)
    {
        if (value is null) { Note.Text = S("«{0}»: не понял значение.",
                          SettingsLayout.TitleOf(key));
            return; }

        var answer = await Ask(Methods.SettingsSet, new JsonObject
        {
            ["values"] = new JsonObject { [key] = value.DeepClone() },
        });
        if (answer?["verdicts"]?[key] is not JsonObject verdict) return;

        var accepted = verdict["accepted"]?.GetValue<bool>() ?? false;
        var message = verdict["message"]?.GetValue<string>() ?? "";
        var code = verdict["code"]?.GetValue<string>() ?? "";

        // A warning is not a refusal: the value was written down and the
        // person was told what it will lead to.
        Note.Text = accepted && message.Length == 0
            ? S("«{0}» сохранено.", SettingsLayout.TitleOf(key))
            : message;
        Note.SetResourceReference(ForegroundProperty,
            accepted && code.Length == 0 ? "C.InkFaint" : "C.Signal");

        if (accepted)
        {
            _values[key] = value;
            if (key == "finish" && _link is not null)
            {
                var finish = value.GetValue<string>();
                await _link.SetFinishAsync(finish);
                // The finish changed — the accent is re-picked along with
                // it: each has a set of its own, and the previous name may
                // not be in it. The name is kept if it is.
                App.ApplyAccent(finish,
                    _values.GetValueOrDefault("accent")?.GetValue<string>()
                    ?? App.DefaultAccent);
                await LoadOptionsAsync();
            }
            if (key == "accent")
                App.ApplyAccent(
                    _values.GetValueOrDefault("finish")?.GetValue<string>()
                    ?? "black", value.GetValue<string>());

            // The language is stored in the core, but the interface's
            // words are translated by the shell: there is nobody else to
            // tell it (ADR 0007).
            if (key == "ui_language")
                Strings.Loc.Use(value.GetValue<string>());

            // The shell's own toggles apply on the spot: a setting waiting
            // for a restart reads as a broken one.
            if (key is "floating_command_bar" or "notifications"
                    or "minimize_to_tray" or "action_hotkeys"
                && System.Windows.Application.Current is App app)
                app.ApplyShellSetting(key, value);
            // Changing the engine changes the set of voices: the lists are
            // re-read rather than left over from the previous engine.
            if (key is "tts_engine" or "stt_engine") await LoadOptionsAsync();
            Build();          // зависимости могли измениться
        }
    }

    /// <summary>
    /// Reset the settings to their defaults — with a confirmation.
    /// </summary>
    /// <remarks>
    /// <para>
    /// We ask because it cannot be undone: the previous values are stored
    /// nowhere, and "oh, wrong button" costs a person all their settings.
    /// </para>
    /// <para>
    /// The window says what the reset does <b>not</b> touch. A person
    /// pressing "reset settings" is afraid of losing their commands and
    /// their history — and must see that these stay, before pressing, not
    /// after.
    /// </para>
    /// </remarks>
    private async void OnReset(object sender, RoutedEventArgs e)
    {
        var ask = new ConfirmWindow(
            S("Все настройки вернутся к значениям по умолчанию: голос, устройства, сочетания клавиш, отделка, приватность."),
            S("Команды, история и плагины останутся на месте."),
            0);
        ask.ShowDialog();
        if (ask.Result != Consent.Granted) return;

        var answer = await Ask(Methods.SettingsReset);
        if (answer is null) return;

        Note.Text = S("Настройки сброшены.");
        Note.SetResourceReference(ForegroundProperty, "C.InkFaint");
        await LoadAsync();
    }

    private async Task<JsonObject?> Ask(string method, JsonObject? payload = null)
    {
        if (_link?.Connection is not { Ready: true } connection)
        {
            Note.Text = S("Ядро не на связи.");
            return null;
        }
        try
        {
            var answer = await connection.CallAsync(method, payload,
                                                    TimeSpan.FromSeconds(20));
            if (answer.IsError) { Note.Text = answer.ErrorMessage; return null; }
            return answer.Payload;
        }
        catch (Exception error) { Note.Text = error.Message; return null; }
    }
}

/// <summary>
/// A row of "a value, and what to do with it".
/// </summary>
/// <remarks>
/// A class rather than a plain <c>Grid</c> so a check can find these
/// rows in a built sheet and measure them: that every button in a list
/// stands at the same edge, and that none of them stands past the
/// window's. Both were reported by eye, and by eye is how they came
/// back.
/// </remarks>
internal sealed class ValueLine : Grid;
