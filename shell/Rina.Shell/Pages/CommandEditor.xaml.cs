using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// The command editor: phrases, action, answer.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0-F04</c>. The commands page could show, switch on, run
/// and delete — but not create, and so for a new person it was empty
/// forever: there was nowhere to get a first command from.
/// </para>
/// <para>
/// <b>Action kinds come from the core</b> (<c>commands.kinds</c>) rather
/// than being written down here. The core is what runs them, and it has
/// the list; a shell that knew the list by heart would drift apart from it
/// in silence — showing an action that does not exist, or hiding a new
/// one. The same rule as for the lists in settings.
/// </para>
/// <para>
/// <b>What is irreversible is marked in the editor already.</b>
/// Confirmation will be asked for by the core when it fires (§11), but
/// finding out that "shut down the computer" is irreversible has to happen
/// here — not on the occasion when the phrase matched by accident.
/// </para>
/// </remarks>
public partial class CommandEditor : UserControl
{
    private readonly List<string> _triggers = [];
    //: Steps of the sequence, in order. The order is the meaning: "open
    //: the browser, then the folder" and the reverse are different
    //: commands.
    //: The steps, at every level. A `JsonArray` rather than a list of
    //: objects, because a branch inside a step is a `JsonArray` too: one
    //: shape for all levels is what lets one function draw them all.
    private readonly JsonArray _chain = [];

    //: Kinds a step may be, what a condition may ask, and the limits — all
    //: from the core (`commands.kinds`). The window offers exactly what the
    //: core will run: a window offering more would be lying while a person
    //: works, and one offering less would hide a capability with nothing to
    //: notice it by.
    private readonly List<(string Value, string Title, string Icon)>
        _stepKinds = [];
    private readonly List<(string Value, string Title)> _conditions = [];
    private int _maxRepeat = 50;
    private int _maxDepth = 5;
    private readonly List<(string Value, string Title, bool Destructive)>
        _actions = [];
    private string _id = "";

    /// <summary>The person saved the command; the page re-reads the list.</summary>
    public event Action<JsonObject>? Saved;

    /// <summary>The person changed their mind.</summary>
    public event Action? Cancelled;

    public CommandEditor(JsonObject kinds, JsonObject? existing = null)
    {
        InitializeComponent();

        foreach (var kind in kinds["kinds"]?.AsArray()
                             .OfType<JsonObject>() ?? [])
        {
            // What is only ever a step does not appear here. A command of
            // kind "wait" would do nothing on purpose; one that is only a
            // repeat says nothing about what it repeats. The core says which
            // those are — it is a statement about meaning, not presentation.
            if (kind["step_only"]?.GetValue<bool>() == true) continue;
            Kind.Items.Add(new ComboBoxItem
            {
                Content = $"{kind["icon"]?.GetValue<string>()} "
                          + kind["title"]?.GetValue<string>(),
                Tag = kind["value"]?.GetValue<string>(),
            });
        }

        foreach (var kind in kinds["kinds"]?.AsArray()
                             .OfType<JsonObject>() ?? [])
        {
            // Steps are every kind minus the sequence itself. A sequence
            // inside a sequence is not forbidden by the core, but a plain
            // chain turning into a tree is not what somebody assembling
            // "open the browser and minimise the window" had in mind — and
            // repeating and choosing now cover what nesting was reached for.
            if (kind["value"]?.GetValue<string>() == "sequence") continue;
            _stepKinds.Add((kind["value"]?.GetValue<string>() ?? "",
                            kind["title"]?.GetValue<string>() ?? "",
                            kind["icon"]?.GetValue<string>() ?? "•"));
        }

        foreach (var one in kinds["conditions"]?.AsArray()
                            .OfType<JsonObject>() ?? [])
            _conditions.Add((one["value"]?.GetValue<string>() ?? "",
                             one["title"]?.GetValue<string>() ?? ""));

        if (kinds["limits"] is JsonObject limits)
        {
            _maxRepeat = (int)Number(limits["repeat"]);
            _maxDepth = (int)Number(limits["depth"]);
        }

        foreach (var action in kinds["actions"]?.AsArray()
                               .OfType<JsonObject>() ?? [])
            _actions.Add((action["value"]?.GetValue<string>() ?? "",
                          action["title"]?.GetValue<string>() ?? "",
                          action["destructive"]?.GetValue<bool>() ?? false));

        foreach (var (value, title, destructive) in _actions)
            Action.Items.Add(new ComboBoxItem
            {
                Content = destructive ? title + S(" — необратимо") : title,
                Tag = value,
            });
        Action.SelectionChanged += (_, _) => ShowWarning();

        if (existing is not null) Fill(existing);
        else Kind.SelectedIndex = 0;
    }

    private void Fill(JsonObject command)
    {
        PageTitle.Text = S("Правка команды");
        _id = command["id"]?.GetValue<string>() ?? "";

        foreach (var phrase in command["triggers"]?.AsArray() ?? [])
            _triggers.Add(phrase?.GetValue<string>() ?? "");
        DrawTriggers();

        var kind = command["type"]?.GetValue<string>() ?? "app";
        Kind.SelectedItem = Kind.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == kind)
            ?? Kind.Items.OfType<ComboBoxItem>().FirstOrDefault();

        var target = command["target"]?.GetValue<string>() ?? "";
        Target.Text = target;
        Action.SelectedItem = Action.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == target);
        Response.Text = command["response"]?.GetValue<string>() ?? "";

        foreach (var step in command["steps"]?.AsArray().OfType<JsonObject>()
                             ?? [])
            _chain.Add(step.DeepClone());
        DrawSteps();
        ShowSummary();
    }

    private string SelectedKind =>
        (Kind.SelectedItem as ComboBoxItem)?.Tag as string ?? "app";

    /// <summary>
    /// The target field changes together with the kind.
    /// </summary>
    /// <remarks>
    /// For "program" it is a path, for "site" an address, for "system
    /// action" a choice from a list, and "say out loud" is not about a
    /// target at all but about text. One "target" field for every case
    /// would make a person work out what exactly belongs in it.
    /// </remarks>
    private void OnKindChanged(object sender, SelectionChangedEventArgs e)
    {
        var kind = SelectedKind;
        var picks = kind is "app" or "folder";
        var system = kind == "system";

        TargetRow.Visibility = kind == "sequence" ? Visibility.Collapsed
                                                  : Visibility.Visible;
        Action.Visibility = system ? Visibility.Visible : Visibility.Collapsed;
        Target.Visibility = system ? Visibility.Collapsed : Visibility.Visible;
        Browse.Visibility = picks ? Visibility.Visible : Visibility.Collapsed;

        // The hint changes with the kind: one and the same field takes now
        // a path, now an address, now a phrase, and "What to open" for
        // every case would leave a person guessing in what form.
        Styles.Ui.SetHint(Target, kind switch
        {
            "app" => S(@"например, C:\Program Files\App\app.exe"),
            "folder" => S(@"например, D:\Проекты"),
            "website" => S("например, github.com"),
            "speak" => S("что произнести"),
            _ => "",
        });

        TargetLabel.Text = kind switch
        {
            "app" => S("Какую программу открыть"),
            "folder" => S("Какую папку открыть"),
            "website" => S("Какой адрес открыть"),
            "speak" => S("Что произнести"),
            "system" => S("Какое действие"),
            _ => S("Что открыть"),
        };

        StepsBox.Visibility = kind == "sequence" ? Visibility.Visible
                                                 : Visibility.Collapsed;
        StepsLabel.Visibility = StepsBox.Visibility;
        if (kind == "sequence") DrawSteps();
        TargetLabel.Visibility = TargetRow.Visibility;
        Note.Text = "";
        ShowWarning();
        ShowSummary();
    }

    /// <summary>The whole command in one sentence.</summary>
    /// <remarks>
    /// <para>
    /// Assembled from the same pieces <see cref="OnSave"/> sends, and in
    /// the order a person would say them: what is said, what happens, what
    /// she answers. Everything above this line is the command **in
    /// pieces** — a phrase in one place, a kind in another, a path in a
    /// third — and what is actually being decided is whether the whole does
    /// what was meant.
    /// </para>
    /// <para>
    /// The names of the kinds and of the system actions come from the core,
    /// through the same lists that fill the dropdowns: a summary that
    /// translated `app` into "Программа" on its own would be a second place
    /// where that is decided, and the two would part company in silence.
    /// </para>
    /// </remarks>
    private void ShowSummary()
    {
        var kind = SelectedKind;
        var said = _triggers.Count == 0
            ? S("Скажите фразу…")
            : string.Join(S(" или "), _triggers.Select(p => $"«{p}»"));

        string happens;
        if (kind == "sequence")
            happens = _chain.Count == 0
                ? S("ничего — шагов пока нет")
                : string.Join(S(", затем "),
                              _chain.OfType<JsonObject>()
                                  .Select(step => DescribeStep(step)
                                      .Replace(" · ", " ")));
        else
        {
            var target = kind == "system"
                ? (Action.SelectedItem as ComboBoxItem)?.Tag as string ?? ""
                : Target.Text.Trim();
            happens = target.Length == 0
                ? S("ничего — не указано, что делать")
                : DescribeStep(new JsonObject
                {
                    ["type"] = kind,
                    ["target"] = target,
                }).Replace(" · ", " ");
        }

        var answer = Response.Text.Trim();
        Summary.Text = S("{0} → {1}. Ответит: {2}.", said, happens,
                         answer.Length > 0 ? $"«{answer}»" : S("«Готово»"));
    }

    /// <summary>Enter adds the phrase — the hands are already there.</summary>
    private void OnTriggerKey(object sender, System.Windows.Input.KeyEventArgs e)
    {
        if (e.Key == System.Windows.Input.Key.Enter)
            OnAddTrigger(sender, new RoutedEventArgs());
    }

    private void OnAnythingChanged(object sender, TextChangedEventArgs e) =>
        ShowSummary();

    private void ShowWarning()
    {
        ShowSummary();
        var chosen = (Action.SelectedItem as ComboBoxItem)?.Tag as string ?? "";
        var destructive = SelectedKind == "system"
                          && _actions.Any(a => a.Value == chosen
                                               && a.Destructive);
        Warning.Text = destructive
            ? S("Это действие необратимо — Рина спросит подтверждение.") : "";
        Warning.Visibility = destructive ? Visibility.Visible
                                         : Visibility.Collapsed;
    }

    private void OnAddTrigger(object sender, RoutedEventArgs e)
    {
        var phrase = NewTrigger.Text.Trim();
        if (phrase.Length == 0 || _triggers.Contains(phrase)) return;
        _triggers.Add(phrase);
        NewTrigger.Clear();
        DrawTriggers();
        ShowSummary();
    }

    private void DrawTriggers()
    {
        Phrases.Children.Clear();
        foreach (var phrase in _triggers.ToArray())
        {
            var row = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 0, 0, 4),
            };
            row.Children.Add(new TextBlock
            {
                Text = "«" + phrase + "»",
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Center,
                MinWidth = 240,
            });
            var drop = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Убрать"),
            };
            drop.Click += (_, _) =>
            {
                _triggers.Remove(phrase);
                DrawTriggers();
                ShowSummary();
            };
            row.Children.Add(drop);
            Phrases.Children.Add(row);
        }
    }

    // -- the chain of steps (4.0b-A09) --------------------------------------

    /// <summary>
    /// The steps, drawn as the chain they are.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This is what the plan asked for and what the previous attempt did not
    /// do. There was a list of rows with arrows beside them, which is a
    /// <b>description</b> of a sequence; a person still had to hold its shape
    /// in their head. Here the shape is the picture: steps stand in a column,
    /// what happens inside a repeat or a branch is drawn inside it, and a new
    /// step goes in <b>between</b> two others rather than only at the end.
    /// </para>
    /// <para>
    /// Drawn recursively because the thing is recursive. A repeat contains
    /// steps; so does each branch of a condition; and each of those is an
    /// ordinary step. One function that draws a list of steps and calls
    /// itself is the whole of it — any other arrangement would have a second
    /// place where "what a step looks like" is decided.
    /// </para>
    /// </remarks>
    private void DrawSteps()
    {
        Steps.Children.Clear();
        Steps.Children.Add(Chain(_chain, 0));
        StepsEmpty.Visibility = _chain.Count == 0 ? Visibility.Visible
                                                  : Visibility.Collapsed;
    }

    private UIElement Chain(JsonArray steps, int depth)
    {
        var column = new StackPanel();
        column.Children.Add(Between(steps, 0, depth));
        for (var at = 0; at < steps.Count; at++)
        {
            column.Children.Add(StepCard(steps, at, depth));
            column.Children.Add(Between(steps, at + 1, depth));
        }
        return column;
    }

    /// <summary>
    /// The place between two steps, and the way to put one there.
    /// </summary>
    /// <remarks>
    /// The point of drawing the gaps at all: somebody who realises they
    /// forgot to wait before the second step should be able to say so where
    /// the waiting belongs, instead of adding it at the end and walking it up
    /// with an arrow.
    /// </remarks>
    private UIElement Between(JsonArray steps, int at, int depth)
    {
        var add = new Button
        {
            Style = (Style)FindResource("Btn.Quiet"),
            Content = "+",
            Width = 22,
            Height = 18,
            Opacity = 0.3,
            HorizontalAlignment = HorizontalAlignment.Left,
            ToolTip = S("Вставить шаг сюда"),
        };
        add.MouseEnter += (_, _) => add.Opacity = 1;
        add.MouseLeave += (_, _) => add.Opacity = 0.3;
        add.Click += (_, _) => OfferKinds(add, steps, at, depth);
        return add;
    }

    /// <summary>What may go in here — and what may not, this deep.</summary>
    /// <remarks>
    /// The nesting limit belongs to the core and arrives with the kinds. A
    /// window that let a person build something the core will refuse to run
    /// would be lying to them while they worked.
    /// </remarks>
    private void OfferKinds(FrameworkElement near, JsonArray steps, int at,
                            int depth)
    {
        var menu = new ContextMenu { PlacementTarget = near };
        foreach (var (value, title, icon) in _stepKinds)
        {
            var nests = value is "repeat" or "if";
            if (nests && depth + 2 >= _maxDepth) continue;
            var item = new MenuItem { Header = icon + "  " + title };
            item.Click += (_, _) =>
            {
                steps.Insert(at, NewStep(value));
                DrawSteps();
                ShowSummary();
            };
            menu.Items.Add(item);
        }
        menu.IsOpen = true;
    }

    private static JsonObject NewStep(string kind) => new()
    {
        ["type"] = kind,
        ["target"] = kind == "pause" ? "1" : "",
        ["enabled"] = true,
        ["triggers"] = new JsonArray(),
        ["match"] = "contains",
        ["response"] = "",
        ["steps"] = new JsonArray(),
        ["otherwise"] = new JsonArray(),
        ["count"] = kind == "repeat" ? 2 : 1,
        ["condition"] = kind == "if" ? "after" : "",
        ["value"] = kind == "if" ? "18:00" : "",
    };

    /// <summary>One step: what it is, what it acts on, where it sits.</summary>
    private UIElement StepCard(JsonArray steps, int at, int depth)
    {
        var step = (JsonObject)steps[at]!;
        var kind = step["type"]?.GetValue<string>() ?? "speak";
        var known = _stepKinds.FirstOrDefault(k => k.Value == kind);
        var title = known.Title ?? kind;
        var icon = known.Icon ?? "•";

        var body = new StackPanel();
        var head = new Grid();
        head.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });
        head.ColumnDefinitions.Add(new ColumnDefinition());
        head.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });

        head.Children.Add(new TextBlock
        {
            Text = icon + "  " + title,
            Style = (Style)FindResource("Text.Body"),
            VerticalAlignment = VerticalAlignment.Center,
            MinWidth = 140,
        });

        var middle = What(step, kind);
        Grid.SetColumn(middle, 1);
        head.Children.Add(middle);

        var hands = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            VerticalAlignment = VerticalAlignment.Center,
        };
        hands.Children.Add(Hand("↑", S("Выше"), () => Move(steps, at, -1)));
        hands.Children.Add(Hand("↓", S("Ниже"), () => Move(steps, at, +1)));
        hands.Children.Add(Hand("✕", S("Убрать шаг"), () =>
        {
            steps.RemoveAt(at);
            DrawSteps();
            ShowSummary();
        }));
        Grid.SetColumn(hands, 2);
        head.Children.Add(hands);
        body.Children.Add(head);

        // What happens inside, indented: indentation is how a person already
        // reads "this belongs to that", and it needs no explaining.
        if (kind is "repeat" or "if")
        {
            body.Children.Add(Nested(step, "steps", depth,
                                     kind == "if" ? S("тогда") : ""));
            if (kind == "if")
                body.Children.Add(Nested(step, "otherwise", depth,
                                         S("иначе")));
        }

        return new Border
        {
            Style = (Style)FindResource("Rows.Item"),
            Margin = new Thickness(0, 0, 0, 2),
            Child = body,
        };
    }

    private UIElement Nested(JsonObject step, string branch, int depth,
                             string label)
    {
        var box = new StackPanel { Margin = new Thickness(24, 6, 0, 2) };
        if (label.Length > 0)
            box.Children.Add(new TextBlock
            {
                Text = label,
                Style = (Style)FindResource("Text.Meta"),
                Margin = new Thickness(0, 0, 0, 2),
            });
        if (step[branch] is not JsonArray inner)
        {
            inner = [];
            step[branch] = inner;
        }
        box.Children.Add(Chain(inner, depth + 1));
        return box;
    }

    private Button Hand(string mark, string tip, Action press)
    {
        var button = new Button
        {
            Style = (Style)FindResource("Btn.Quiet"),
            Content = mark,
            Width = 26,
            Height = 26,
            ToolTip = tip,
        };
        button.Click += (_, _) => press();
        return button;
    }

    /// <summary>
    /// The middle of a step: what it acts on, edited where it stands.
    /// </summary>
    /// <remarks>
    /// In place rather than in a form above the list. A separate "new step"
    /// panel meant that changing a step was impossible — one deleted it and
    /// typed it again — and that the thing being edited was never beside the
    /// things it would stand between.
    /// </remarks>
    private UIElement What(JsonObject step, string kind)
    {
        // A wrapping row rather than a horizontal stack.
        //
        // A stack clips what does not fit, and what did not fit was the
        // right-hand end of the time field — a step one could not finish
        // filling in. Shaving pixels off the controls only moves the
        // clipping to the next window size; wrapping survives any of them.
        var row = new WrapPanel
        {
            Orientation = Orientation.Horizontal,
            VerticalAlignment = VerticalAlignment.Center,
        };

        void Field(string key, string hint, double width)
        {
            var box = new TextBox
            {
                Style = (Style)FindResource("Field"),
                Text = step[key]?.GetValue<string>() ?? "",
                Width = width,
                VerticalAlignment = VerticalAlignment.Center,
            };
            Styles.Ui.SetHint(box, hint);
            box.TextChanged += (_, _) =>
            {
                step[key] = box.Text;
                ShowSummary();
            };
            row.Children.Add(box);
        }

        void Choice(IEnumerable<(string Value, string Title)> options,
                    string key, double width)
        {
            var pick = new ComboBox
            {
                Style = (Style)FindResource("Choice"),
                Width = width,
                VerticalAlignment = VerticalAlignment.Center,
            };
            foreach (var (value, said) in options)
                pick.Items.Add(new ComboBoxItem { Content = said, Tag = value });
            pick.SelectedItem = pick.Items.OfType<ComboBoxItem>()
                .FirstOrDefault(i => (string?)i.Tag
                                     == (step[key]?.GetValue<string>() ?? ""));
            pick.SelectionChanged += (_, _) =>
            {
                step[key] = (pick.SelectedItem as ComboBoxItem)?.Tag as string
                            ?? "";
                DrawSteps();
                ShowSummary();
            };
            row.Children.Add(pick);
        }

        switch (kind)
        {
            case "system":
                // A fresh step picks the first harmless action rather than
                // nothing. An empty dropdown in a step somebody just added
                // is a question with no default answer, and the step is
                // invalid until they notice it.
                if ((step["target"]?.GetValue<string>() ?? "").Length == 0
                    && _actions.FirstOrDefault(a => !a.Destructive)
                        is { Value.Length: > 0 } safe)
                    step["target"] = safe.Value;
                Choice(_actions.Select(a => (a.Value, a.Destructive
                           ? a.Title + S(" — необратимо") : a.Title)),
                       "target", 230);
                break;

            case "pause":
                Field("target", S("секунд"), 70);
                row.Children.Add(new TextBlock
                {
                    Text = S("с"),
                    Style = (Style)FindResource("Text.Meta"),
                    VerticalAlignment = VerticalAlignment.Center,
                    Margin = new Thickness(6, 0, 0, 0),
                });
                break;

            case "repeat":
                var times = new TextBox
                {
                    Style = (Style)FindResource("Field"),
                    Text = ((int)Number(step["count"])).ToString(),
                    Width = 60,
                    VerticalAlignment = VerticalAlignment.Center,
                };
                times.TextChanged += (_, _) =>
                {
                    step["count"] = int.TryParse(times.Text, out var n)
                        ? Math.Clamp(n, 0, _maxRepeat) : 1;
                    ShowSummary();
                };
                row.Children.Add(times);
                row.Children.Add(new TextBlock
                {
                    Text = S("раз"),
                    Style = (Style)FindResource("Text.Meta"),
                    VerticalAlignment = VerticalAlignment.Center,
                    Margin = new Thickness(6, 0, 0, 0),
                });
                break;

            case "if":
                // Narrower than it looks like it should be: the row also
                // holds the value and the three controls on the right, and
                // at 210 the time field went off the edge. A step whose
                // right-hand end is off-screen is a step one cannot finish
                // filling in.
                Choice(_conditions, "condition", 180);
                // Only a condition that asks about something gets a field for
                // it: "today is a weekday" has nothing to fill in, and a box
                // beside it would be a question with no answer.
                var asks = step["condition"]?.GetValue<string>() ?? "";
                if (asks is "after" or "before") Field("value", "18:00", 95);
                else if (asks is "exists" or "missing")
                    Field("value", S("путь"), 200);
                break;

            default:
                Field("target", kind switch
                {
                    "app" => S(@"например, C:\Program Files\App\app.exe"),
                    "folder" => S(@"например, D:\Проекты"),
                    "website" => S("например, github.com"),
                    _ => S("что произнести"),
                }, 250);
                if (kind is "app" or "folder")
                {
                    var browse = new Button
                    {
                        Style = (Style)FindResource("Btn"),
                        Content = S("Обзор…"),
                        Margin = new Thickness(8, 0, 0, 0),
                    };
                    browse.Click += (_, _) =>
                    {
                        var picked = Pick(kind);
                        if (picked is null) return;
                        step["target"] = picked;
                        DrawSteps();
                        ShowSummary();
                    };
                    row.Children.Add(browse);
                }
                break;
        }
        return row;
    }

    private static string? Pick(string kind)
    {
        if (kind == "folder")
        {
            var folder = new Microsoft.Win32.OpenFolderDialog();
            return folder.ShowDialog() == true ? folder.FolderName : null;
        }
        var file = new Microsoft.Win32.OpenFileDialog
        {
            Filter = S("Программы (*.exe;*.lnk)|*.exe;*.lnk|Все файлы|*.*"),
        };
        return file.ShowDialog() == true ? file.FileName : null;
    }

    private static double Number(JsonNode? node)
    {
        if (node is not JsonValue value) return 0;
        if (value.TryGetValue<int>(out var small)) return small;
        if (value.TryGetValue<long>(out var whole)) return whole;
        if (value.TryGetValue<double>(out var exact)) return exact;
        return double.TryParse(value.ToJsonString(),
                               System.Globalization.NumberStyles.Any,
                               System.Globalization.CultureInfo.InvariantCulture,
                               out var told) ? told : 0;
    }

    private void Move(JsonArray steps, int at, int delta)
    {
        var to = at + delta;
        if (to < 0 || to >= steps.Count) return;
        var moving = steps[at];
        steps.RemoveAt(at);
        steps.Insert(to, moving);
        DrawSteps();
        ShowSummary();
    }

    /// <summary>A step in human words: the kind and what exactly.</summary>
    private string DescribeStep(JsonObject step)
    {
        var kind = step["type"]?.GetValue<string>() ?? "";
        var target = step["target"]?.GetValue<string>() ?? "";
        var title = Kind.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == kind)
            ?.Content?.ToString() ?? kind;

        // A system action's target is a code from a list, and there is no
        // point showing it to a person: the action has a name.
        if (kind == "system")
        {
            var named = _actions.FirstOrDefault(a => a.Value == target);
            return $"{title} · {(named.Title.Length > 0 ? named.Title : target)}";
        }
        return target.Length > 0 ? $"{title} · {target}" : title;
    }

    private void OnBrowse(object sender, RoutedEventArgs e)
    {
        if (SelectedKind == "folder")
        {
            var folder = new Microsoft.Win32.OpenFolderDialog();
            if (folder.ShowDialog() == true) Target.Text = folder.FolderName;
            return;
        }
        var file = new Microsoft.Win32.OpenFileDialog
        {
            Filter = S("Программы (*.exe;*.lnk)|*.exe;*.lnk|Все файлы|*.*"),
        };
        if (file.ShowDialog() == true) Target.Text = file.FileName;
    }

    private void OnSave(object sender, RoutedEventArgs e)
    {
        if (_triggers.Count == 0)
        {
            Note.Text = S("Нужна хотя бы одна фраза.");
            return;
        }

        var kind = SelectedKind;
        var target = kind == "system"
            ? (Action.SelectedItem as ComboBoxItem)?.Tag as string ?? ""
            : Target.Text.Trim();
        if (kind != "sequence" && target.Length == 0)
        {
            Note.Text = S("Нужно указать, что делать.");
            return;
        }
        if (kind == "sequence" && _chain.Count == 0)
        {
            Note.Text = S("Нужен хотя бы один шаг.");
            return;
        }

        var command = Card(kind, target);
        // The number is assigned by the core; we send our own only when
        // editing one that already exists — otherwise editing would turn
        // into creating a twin.
        if (_id.Length > 0) command["id"] = _id;

        Saved?.Invoke(command);
    }

    /// <summary>The card as the core expects it.</summary>
    /// <remarks>
    /// One place, used by both saving and trying. Two builders would part
    /// company the first time a field was added, and the trial would then
    /// be a trial of something slightly different from what gets saved —
    /// which is the one thing a trial must not be.
    /// </remarks>
    private JsonObject Card(string kind, string target) => new()
    {
        ["enabled"] = true,
        ["type"] = kind,
        ["triggers"] = new JsonArray(
            _triggers.Select(t => (JsonNode)t!).ToArray()),
        ["match"] = "contains",
        ["target"] = target,
        ["response"] = Response.Text.Trim(),
        ["steps"] = new JsonArray(
            _chain.Select(step => step!.DeepClone()).ToArray()),
    };

    /// <summary>The person wants to see it happen (`4.0b-A09`).</summary>
    public event Action<JsonObject>? Tried;

    /// <summary>
    /// Try it without saving.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Assembling a command and finding out whether it does what was meant
    /// were two separate acts: save, close the editor, find the row, press
    /// «Выполнить» — and if it was wrong, open it again. Trying it four
    /// times left four commands to delete.
    /// </para>
    /// <para>
    /// <b>Phrases are not needed for this.</b> A phrase is how the command
    /// is found when spoken; a trial is pressed, not said, so demanding one
    /// would be demanding a thing that has no part in what is about to
    /// happen. What to do is still needed — that is the thing being tried.
    /// </para>
    /// </remarks>
    private void OnTry(object sender, RoutedEventArgs e)
    {
        var kind = SelectedKind;
        var target = kind == "system"
            ? (Action.SelectedItem as ComboBoxItem)?.Tag as string ?? ""
            : Target.Text.Trim();

        if (kind == "sequence" && _chain.Count == 0)
        {
            Note.Text = S("Нечего пробовать: шагов пока нет.");
            return;
        }
        if (kind != "sequence" && target.Length == 0)
        {
            Note.Text = S("Нечего пробовать: не указано, что делать.");
            return;
        }

        Note.Text = S("Пробую…");
        Tried?.Invoke(Card(kind, target));
    }

    private void OnCancel(object sender, RoutedEventArgs e) => Cancelled?.Invoke();

    /// <summary>
    /// Assemble a sequence out of steps — for the end-to-end check.
    /// </summary>
    /// <remarks>
    /// The check cannot click, and a command assembled by hand would be
    /// testing `JsonObject` rather than the editor. So it goes the way a
    /// person does: pick the kind, put a step in at a place, fill in what it
    /// acts on, move one, save.
    /// </remarks>
    public bool BuildSequenceForCheck(
        string phrase, IEnumerable<(string Kind, string Target)> steps)
    {
        _triggers.Clear();
        _triggers.Add(phrase);
        DrawTriggers();

        Kind.SelectedItem = Kind.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == "sequence");
        if (SelectedKind != "sequence") return false;

        _chain.Clear();
        foreach (var (kind, target) in steps)
        {
            var step = NewStep(kind);
            step["target"] = target;
            _chain.Add(step);
        }
        DrawSteps();
        if (_chain.Count == 0) return false;

        // And the order: lift the last step one place and put it back.
        //
        // Up then **down**, not up then up: the first version moved the last
        // step to index 1 and then moved index 1 up again, which walks it to
        // the front instead of returning it. The check caught it, which is
        // the whole reason it puts the order back at all.
        var wasFirst = _chain[0]?["target"]?.GetValue<string>();
        var wasLast = _chain[^1]?["target"]?.GetValue<string>();
        Move(_chain, _chain.Count - 1, -1);
        Move(_chain, _chain.Count - 2, +1);
        if (_chain[0]?["target"]?.GetValue<string>() != wasFirst) return false;
        if (_chain[^1]?["target"]?.GetValue<string>() != wasLast) return false;

        OnSave(this, new RoutedEventArgs());
        return true;
    }

    /// <summary>Close it as a person would — for the check.</summary>
    public void CancelForCheck() => OnCancel(this, new RoutedEventArgs());

    /// <summary>Switch to a sequence — for the check.</summary>
    public void ShowSequenceForCheck()
    {
        Kind.SelectedItem = Kind.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == "sequence");
    }

    /// <summary>Put a step in at a place — for the check.</summary>
    public void InsertStepForCheck(int at, string kind, string target = "")
    {
        var step = NewStep(kind);
        if (target.Length > 0) step["target"] = target;
        _chain.Insert(Math.Clamp(at, 0, _chain.Count), step);
        DrawSteps();
        ShowSummary();
    }

    /// <summary>Put a step inside another one — for the check.</summary>
    public bool NestStepForCheck(int outer, string branch, string kind,
                                 string target = "")
    {
        if (outer < 0 || outer >= _chain.Count) return false;
        if (_chain[outer] is not JsonObject holder) return false;
        if (holder[branch] is not JsonArray inner)
        {
            inner = [];
            holder[branch] = inner;
        }
        var step = NewStep(kind);
        if (target.Length > 0) step["target"] = target;
        inner.Add(step);
        DrawSteps();
        ShowSummary();
        return true;
    }

    /// <summary>The steps as the core will get them — for the check.</summary>
    public JsonArray ChainForCheck => _chain;

    /// <summary>Which kinds the window offers as steps — for the check.</summary>
    public string[] StepKindsOffered =>
        _stepKinds.Select(k => k.Value).ToArray();

    /// <summary>Which kinds it offers as whole commands — for the check.</summary>
    public string[] CommandKindsOffered =>
        Kind.Items.OfType<ComboBoxItem>()
            .Select(i => (string?)i.Tag ?? "").ToArray();



    /// <summary>How many steps were assembled — for the check.</summary>
    public int StepCount => _chain.Count;

    /// <summary>The command read back as one sentence — for the check.</summary>
    public string SummarySaid => Summary.Text;

    /// <summary>
    /// Is the new capability marked as one — for the check.
    /// </summary>
    /// <remarks>
    /// Both halves: the mark is beside <c>Try</c> and both are on screen.
    /// A mark that is present but hidden, or present beside something else,
    /// is not a warning anybody reads — and either would satisfy a check
    /// that only asked whether the element existed.
    /// </remarks>
    /// <summary>
    /// Where the mark sits, in numbers — for the check.
    /// </summary>
    /// <remarks>
    /// Numbers, and the check makes the sentence. The first version
    /// composed its own report here, in Russian, inside a page — and
    /// `check_strings.py` was right to object: a line a person never sees
    /// has no business among the ones that get translated, and a page has
    /// no business writing a check's prose.
    /// </remarks>
    public (bool Seen, double X, double Y, double Width) BetaWhere()
    {
        if (!Try.IsVisible || !TryBeta.IsVisible) return (false, 0, 0, 0);
        var at = TryBeta.TranslatePoint(new Point(0, 0), Try);
        return (true, at.X, at.Y, Try.ActualWidth);
    }

    /// <summary>Is the mark beside the button it belongs to.</summary>
    public bool BetaMarkedWell
    {
        get
        {
            var (seen, x, y, width) = BetaWhere();
            return seen && x >= width && x < width + 40
                   && Math.Abs(y) < Try.ActualHeight;
        }
    }

    /// <summary>Fill in a simple command — for the check.</summary>
    public void FillForCheck(string phrase, string kind, string target)
    {
        _triggers.Clear();
        _triggers.Add(phrase);
        DrawTriggers();
        Kind.SelectedItem = Kind.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == kind);
        Target.Text = target;
        ShowSummary();
    }

    /// <summary>Press «Проверить» — for the check.</summary>
    public void TryForCheck() => OnTry(this, new RoutedEventArgs());
}
