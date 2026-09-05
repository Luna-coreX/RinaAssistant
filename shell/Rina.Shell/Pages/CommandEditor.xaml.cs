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
    private readonly List<JsonObject> _steps = [];
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
            Kind.Items.Add(new ComboBoxItem
            {
                Content = $"{kind["icon"]?.GetValue<string>()} "
                          + kind["title"]?.GetValue<string>(),
                Tag = kind["value"]?.GetValue<string>(),
            });

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
        Legend.Text = S("ПРАВКА КОМАНДЫ");
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
            _steps.Add((JsonObject)step.DeepClone());
        DrawSteps();
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
        if (kind == "sequence" && StepKind.Items.Count == 0) FillStepKinds();
        Note.Text = "";
        ShowWarning();
    }

    private void ShowWarning()
    {
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
            drop.Click += (_, _) => { _triggers.Remove(phrase); DrawTriggers(); };
            row.Children.Add(drop);
            Phrases.Children.Add(row);
        }
    }

    /// <summary>
    /// Step kinds — the same as a command's, minus the sequence itself.
    /// </summary>
    /// <remarks>
    /// A sequence inside a sequence is not forbidden by the core, but it is
    /// absent from the editor: "a step that is itself a list of steps"
    /// turns a plain chain into a tree, and a person assembling "open the
    /// browser and minimise the window" did not have a tree in mind.
    /// </remarks>
    private void FillStepKinds()
    {
        foreach (var item in Kind.Items.OfType<ComboBoxItem>())
        {
            if ((string?)item.Tag == "sequence") continue;
            StepKind.Items.Add(new ComboBoxItem
            {
                Content = item.Content,
                Tag = item.Tag,
            });
        }
        foreach (var (value, title, destructive) in _actions)
            StepAction.Items.Add(new ComboBoxItem
            {
                Content = destructive ? title + S(" — необратимо") : title,
                Tag = value,
            });
        if (StepKind.Items.Count > 0) StepKind.SelectedIndex = 0;
    }

    private string StepSelectedKind =>
        (StepKind.SelectedItem as ComboBoxItem)?.Tag as string ?? "app";

    private void OnStepKindChanged(object sender, SelectionChangedEventArgs e)
    {
        var kind = StepSelectedKind;
        var system = kind == "system";
        StepAction.Visibility = system ? Visibility.Visible
                                       : Visibility.Collapsed;
        StepTarget.Visibility = system ? Visibility.Collapsed
                                       : Visibility.Visible;
        StepBrowse.Visibility = kind is "app" or "folder"
            ? Visibility.Visible : Visibility.Collapsed;
    }

    private void OnStepBrowse(object sender, RoutedEventArgs e)
    {
        if (StepSelectedKind == "folder")
        {
            var folder = new Microsoft.Win32.OpenFolderDialog();
            if (folder.ShowDialog() == true) StepTarget.Text = folder.FolderName;
            return;
        }
        var file = new Microsoft.Win32.OpenFileDialog
        {
            Filter = S("Программы (*.exe;*.lnk)|*.exe;*.lnk|Все файлы|*.*"),
        };
        if (file.ShowDialog() == true) StepTarget.Text = file.FileName;
    }

    private void OnAddStep(object sender, RoutedEventArgs e)
    {
        var kind = StepSelectedKind;
        var target = kind == "system"
            ? (StepAction.SelectedItem as ComboBoxItem)?.Tag as string ?? ""
            : StepTarget.Text.Trim();
        if (target.Length == 0)
        {
            Note.Text = S("Шагу нужно указать, что делать.");
            return;
        }

        // A step has neither phrases nor an answer of its own: the command
        // as a whole is what fires and what answers, and a step is what it
        // does along the way.
        _steps.Add(new JsonObject
        {
            ["type"] = kind,
            ["target"] = target,
            ["enabled"] = true,
            ["triggers"] = new JsonArray(),
            ["match"] = "contains",
            ["response"] = "",
            ["steps"] = new JsonArray(),
        });
        StepTarget.Clear();
        Note.Text = "";
        DrawSteps();
    }

    /// <summary>Show the steps with their order and buttons.</summary>
    private void DrawSteps()
    {
        Steps.Children.Clear();
        StepsEmpty.Visibility = _steps.Count == 0 ? Visibility.Visible
                                                  : Visibility.Collapsed;

        for (var at = 0; at < _steps.Count; at++)
        {
            var index = at;
            var step = _steps[at];
            var row = new Grid { Margin = new Thickness(0, 0, 0, 4) };
            row.ColumnDefinitions.Add(new ColumnDefinition
            {
                Width = GridLength.Auto,
            });
            row.ColumnDefinitions.Add(new ColumnDefinition
            {
                Width = new GridLength(1, GridUnitType.Star),
            });
            for (var i = 0; i < 3; i++)
                row.ColumnDefinitions.Add(new ColumnDefinition
                {
                    Width = GridLength.Auto,
                });

            // A number, not a bullet: a person reads "first this, then
            // that", and the order has to be visible, not implied.
            var number = new TextBlock
            {
                Text = $"{index + 1}.",
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(0, 0, 8, 0),
            };
            Grid.SetColumn(number, 0);
            row.Children.Add(number);

            var what = new TextBlock
            {
                Text = DescribeStep(step),
                Style = (Style)FindResource("Text.Body"),
                VerticalAlignment = VerticalAlignment.Center,
                TextTrimming = TextTrimming.CharacterEllipsis,
            };
            Grid.SetColumn(what, 1);
            row.Children.Add(what);

            var up = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = "↑",
                IsEnabled = index > 0,
            };
            up.Click += (_, _) => Move(index, -1);
            Grid.SetColumn(up, 2);
            row.Children.Add(up);

            var down = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = "↓",
                IsEnabled = index < _steps.Count - 1,
            };
            down.Click += (_, _) => Move(index, +1);
            Grid.SetColumn(down, 3);
            row.Children.Add(down);

            var drop = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Убрать"),
            };
            drop.Click += (_, _) => { _steps.RemoveAt(index); DrawSteps(); };
            Grid.SetColumn(drop, 4);
            row.Children.Add(drop);

            Steps.Children.Add(row);
        }
    }

    private void Move(int index, int delta)
    {
        var to = index + delta;
        if (to < 0 || to >= _steps.Count) return;
        (_steps[index], _steps[to]) = (_steps[to], _steps[index]);
        DrawSteps();
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
        if (kind == "sequence" && _steps.Count == 0)
        {
            Note.Text = S("Нужен хотя бы один шаг.");
            return;
        }

        var command = new JsonObject
        {
            ["enabled"] = true,
            ["type"] = kind,
            ["triggers"] = new JsonArray(
                _triggers.Select(t => (JsonNode)t!).ToArray()),
            ["match"] = "contains",
            ["target"] = target,
            ["response"] = Response.Text.Trim(),
            ["steps"] = new JsonArray(
                _steps.Select(step => step.DeepClone()).ToArray()),
        };
        // The number is assigned by the core; we send our own only when
        // editing one that already exists — otherwise editing would turn
        // into creating a twin.
        if (_id.Length > 0) command["id"] = _id;

        Saved?.Invoke(command);
    }

    private void OnCancel(object sender, RoutedEventArgs e) => Cancelled?.Invoke();

    /// <summary>
    /// Assemble a sequence out of steps — for the end-to-end check.
    /// </summary>
    /// <remarks>
    /// The check cannot click buttons, and a command assembled by hand
    /// would be testing `JsonObject` rather than the editor. Here it goes
    /// the same way: pick the kind, add the steps, save.
    /// </remarks>
    public bool BuildSequenceForCheck(string phrase,
                                      IEnumerable<(string Kind, string Target)> steps)
    {
        _triggers.Clear();
        _triggers.Add(phrase);
        DrawTriggers();

        Kind.SelectedItem = Kind.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == "sequence");
        if (SelectedKind != "sequence") return false;

        foreach (var (kind, target) in steps)
        {
            StepKind.SelectedItem = StepKind.Items.OfType<ComboBoxItem>()
                .FirstOrDefault(item => (string?)item.Tag == kind);

            // A system step's target is picked from a list, not typed: the
            // first edition of the check typed it — and the system step
            // silently failed to be added, because the list stayed empty.
            if (kind == "system")
                StepAction.SelectedItem = StepAction.Items
                    .OfType<ComboBoxItem>()
                    .FirstOrDefault(item => (string?)item.Tag == target);
            else
                StepTarget.Text = target;

            OnAddStep(this, new RoutedEventArgs());
        }
        if (_steps.Count == 0) return false;

        // And the order: lift the last step to the top and put it back.
        var wasFirst = _steps[0]["target"]?.GetValue<string>();
        Move(_steps.Count - 1, -1);
        Move(_steps.Count - 2, +1);
        if (_steps[0]["target"]?.GetValue<string>() != wasFirst) return false;

        OnSave(this, new RoutedEventArgs());
        return true;
    }

    /// <summary>How many steps were assembled — for the check.</summary>
    public int StepCount => _steps.Count;
}
