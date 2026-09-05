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
        if (described?["schema"] is not JsonObject schema) return;

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
                    .Select(a => (a.Value, a.Title, true)).ToList();
                continue;
            }

            var devices = key == "input_device"
                ? Audio.Microphone.Devices()
                : Audio.Speaker.Devices();
            var listed = new List<(string, string, bool)>
            {
                ("default", S("Устройство по умолчанию"), true),
            };
            listed.AddRange(devices.Select(d => (d.Name, d.Name, true)));
            _options[key] = listed;
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
                              true))
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
                item?["available"]?.GetValue<bool>() ?? true)).ToList();
        }
    }

    private readonly Dictionary<string, List<(string Value, string Title,
                                              bool Available)>> _options = [];

    private void Build()
    {
        Body.Children.Clear();
        var placed = new HashSet<string>();

        foreach (var section in SettingsLayout.Sections)
        {
            var keys = section.Keys.Where(k => _schema.ContainsKey(k.Key))
                                   .ToArray();
            if (keys.Length == 0) continue;
            Body.Children.Add(BuildSection(section.Title,
                                           keys.Select(k => k.Key)));
            foreach (var k in keys) placed.Add(k.Key);
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
        if (strangers.Length > 0)
            Body.Children.Add(BuildSection(SettingsLayout.Other, strangers));
    }

    private UIElement BuildSection(string title, IEnumerable<string> keys)
    {
        var stack = new StackPanel { Margin = new Thickness(0, 0, 0, 32) };
        stack.Children.Add(new TextBlock
        {
            // Translated here: the layout holds a key (see SettingsLayout).
            Text = S(title).ToUpperInvariant(),
            Style = (Style)FindResource("Text.Section"),
            Margin = new Thickness(0, 0, 0, 12),
        });
        foreach (var key in keys) stack.Children.Add(BuildRow(key));
        return stack;
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
    private const double ControlColumn = 296;

    /// <summary>
    /// The width of the control itself inside the column.
    /// </summary>
    /// <remarks>
    /// One for every kind: dropdown, field, path, slider with a number.
    /// Each used to carry its own — 280, 200, 276 — and the right edge
    /// wandered by eighty points. On an instrument the controls stand in a
    /// column, and a column has two sides, not one.
    /// </remarks>
    private const double ControlWidth = 280;

    /// <summary>The width of the checks column. Empty in most rows.</summary>
    private const double ProbeColumn = 150;

    private UIElement BuildRow(string key)
    {
        var spec = _schema[key];
        var row = new Grid { MinHeight = 40 };
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(1, GridUnitType.Star),
        });
        // The control column is one width for the whole page: otherwise
        // every row starts where its own label ended, and the right edge
        // goes ragged. On a front panel the controls stand in a column.
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(ControlColumn),
        });
        // The third column is for the check, and it is **also one width
        // for every row**. With "by content", a row with a button took room
        // from its own label, and its control drifted left of its
        // neighbours': columns belong to the panel, not to the row.
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(ProbeColumn),
        });

        var label = new StackPanel
        {
            VerticalAlignment = VerticalAlignment.Center,
            // The gap between the legend and the control. Without it the
            // hint ran into the field, and two columns read as one.
            Margin = new Thickness(0, 0, 24, 0),
        };
        label.Children.Add(new TextBlock
        {
            Text = SettingsLayout.TitleOf(key),
            Style = (Style)FindResource("Text.Body"),
        });

        var notes = new List<string>();
        if (SettingsLayout.HintOf(key).Length > 0)
            notes.Add(SettingsLayout.HintOf(key));
        if (spec["restart_required"] is not null)
            notes.Add(S("применится после перезапуска"));
        if (!SettingsLayout.Known.Contains(key))
            notes.Add(S("ключ {0} оболочке незнаком", key));
        if (notes.Count > 0)
            label.Children.Add(new TextBlock
            {
                Text = string.Join(" · ", notes),
                Style = (Style)FindResource("Text.Meta"),
                Margin = new Thickness(0, 2, 0, 0),
                TextWrapping = TextWrapping.Wrap,
            });

        Grid.SetColumn(label, 0);
        row.Children.Add(label);

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
            Grid.SetRow(editor, 1);
            Grid.SetColumn(editor, 0);
            Grid.SetColumnSpan(editor, 2);
            editor.HorizontalAlignment = HorizontalAlignment.Left;
            editor.Margin = new Thickness(0, 8, 0, 0);
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

        // A hairline seam between settings — the same device as in the
        // lists: areas of a panel are separated by value and by a seam, not
        // by emptiness between tiles.
        return new Border
        {
            BorderBrush = (System.Windows.Media.Brush)FindResource("C.Seam"),
            BorderThickness = new Thickness(0, 0, 0, 1),
            Padding = new Thickness(0, 8, 0, 10),
            Child = row,
        };
    }

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
        if (key is not ("voice" or "input_device")) return null;

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
        List<(string Value, string Title, bool Available)> known, string current)
    {
        var box = new ComboBox
        {
            Style = (Style)FindResource("Choice"),
            Width = ControlWidth,
        };
        foreach (var (value, title, available) in known)
            box.Items.Add(new ComboBoxItem
            {
                Content = title.Length > 0 ? title : value,
                Tag = value,
                IsEnabled = available,
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

        foreach (var item in items)
        {
            var row = new StackPanel
            {
                Orientation = Orientation.Horizontal,
            };
            row.Children.Add(new TextBlock
            {
                Text = item,
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Center,
                MaxWidth = 220,
                TextTrimming = TextTrimming.CharacterEllipsis,
                ToolTip = item,
            });
            var drop = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Убрать"),
                Tag = item,
            };
            drop.Click += async (_, _) =>
            {
                items.Remove(item);
                await SaveAsync(key, new JsonArray(
                    items.Select(v => (JsonNode)v!).ToArray()));
            };
            row.Children.Add(drop);
            stack.Children.Add(row);
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
            Margin = new Thickness(0, 4, 0, 0),
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
                Margin = new Thickness(0, 0, 8, 0),
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
        List<(string Value, string Title, bool Available)> actions,
        JsonObject? current)
    {
        var stack = new StackPanel();
        var assigned = new JsonObject();
        foreach (var (name, _t, _a) in actions)
        {
            var combination = current?[name]?.GetValue<string>() ?? "";
            if (combination.Length > 0) assigned[name] = combination;
        }

        foreach (var (name, title, _) in actions)
        {
            var row = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 0, 0, 4),
            };
            row.Children.Add(new TextBlock
            {
                Text = title,
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Center,
                Width = 190,
                Margin = new Thickness(0, 0, 8, 0),
            });

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
            row.Children.Add(box);
            stack.Children.Add(row);
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

        foreach (var (word, bound) in current ?? [])
        {
            var line = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 0, 0, 2),
            };
            line.Children.Add(new TextBlock
            {
                Text = DescribeBinding(word, bound),
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Center,
                MaxWidth = 300,
                TextTrimming = TextTrimming.CharacterEllipsis,
                ToolTip = DescribeBinding(word, bound),
                Margin = new Thickness(0, 0, 8, 0),
            });
            var drop = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Забыть"),
            };
            var forgotten = word;
            drop.Click += async (_, _) =>
            {
                var left = new JsonObject();
                foreach (var (other, value) in current ?? [])
                    if (other != forgotten)
                        left[other] = value?.DeepClone();
                await SaveAsync(key, left);
            };
            line.Children.Add(drop);
            stack.Children.Add(line);
        }

        var row = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Margin = new Thickness(0, 4, 0, 0),
        };
        row.Children.Add(new TextBlock
        {
            Text = S("записей: {0}", current?.Count ?? 0),
            Style = (Style)FindResource("Text.Meta"),
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(0, 0, 8, 0),
        });
        var forget = new Button
        {
            Style = (Style)FindResource("Btn"),
            Content = SettingsLayout.ClearWordOf(key),
            IsEnabled = (current?.Count ?? 0) > 0,
        };
        forget.Click += async (_, _) => await SaveAsync(key, new JsonObject());
        row.Children.Add(forget);
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
        if (_link?.Connection is not { Ready: true } connection) return null;
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
