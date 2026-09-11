using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Shapes;

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

        // There is no list of "what kind of command this is" any more.
        //
        // It named the command's one action, and a command with several
        // actions had to choose "sequence" first before it had anywhere to
        // put them — so the shape of the thing depended on how many of it
        // there were. A command is a graph now, and a simple one is a graph
        // of one node.
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

        if (existing is not null) Fill(existing);
        DrawSteps();
        ShowSummary();
    }

    //: Other commands this one may call. Filled from outside, because the
    //: list of commands belongs to the page that has it.
    private readonly List<(string Value, string Title)> _callable = [];

    /// <summary>Which commands may be called from here.</summary>
    /// <remarks>
    /// This one is left out of its own list. A command calling itself is
    /// refused by the core at run time, and offering it here would be
    /// offering something that will not work — a window should not propose
    /// what the thing behind it will decline.
    /// </remarks>
    public void CanCall(IEnumerable<(string Id, string Name)> commands)
    {
        _callable.Clear();
        foreach (var (id, name) in commands)
            if (id != _id)
                _callable.Add((id, name));
    }

    private void Fill(JsonObject command)
    {
        PageTitle.Text = S("Правка команды");
        _id = command["id"]?.GetValue<string>() ?? "";

        foreach (var phrase in command["triggers"]?.AsArray() ?? [])
            _triggers.Add(phrase?.GetValue<string>() ?? "");
        DrawTriggers();

        Response.Text = command["response"]?.GetValue<string>() ?? "";

        // A command of any other kind becomes a graph of one node. That is
        // what it always was; it simply had no picture of itself. Cards
        // written by every earlier version open here without conversion,
        // and a person who wanted to add a second step can now do it
        // without first re-declaring what they are making.
        var kind = command["type"]?.GetValue<string>() ?? "app";
        if (kind == "sequence")
        {
            foreach (var step in command["steps"]?.AsArray()
                                 .OfType<JsonObject>() ?? [])
                _chain.Add(step.DeepClone());
        }
        else
        {
            var only = NewStep(kind);
            foreach (var field in new[] { "target", "value", "name",
                                          "condition", "count" })
                if (command[field] is { } had) only[field] = had.DeepClone();
            _chain.Add(only);
        }
        DrawSteps();
        ShowSummary();
    }

    /// <summary>
    /// Which kinds are plain enough to stand alone as a whole command.
    /// </summary>
    /// <remarks>
    /// A graph of one node is saved as the ordinary card it is —
    /// `app`, `website`, `speak` — rather than as a sequence wrapping one
    /// step. The card stays the shape it has always been, files written by
    /// older versions still read, and nothing in the core has to learn that
    /// a sequence of one is the same as the thing inside it.
    /// </remarks>
    private static bool StandsAlone(string kind) =>
        kind is "app" or "folder" or "website" or "speak" or "system";

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
        var said = _triggers.Count == 0
            ? S("Скажите фразу…")
            : string.Join(S(" или "), _triggers.Select(p => $"«{p}»"));

        var happens = _chain.Count == 0
            ? S("ничего — шагов пока нет")
            : string.Join(S(", затем "),
                          _chain.OfType<JsonObject>()
                              .Select(step => DescribeStep(step)
                                  .Replace(" · ", " ")));

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

    /// <summary>
    /// Say if anything in the graph cannot be undone.
    /// </summary>
    /// <remarks>
    /// The whole graph, not the one node selected. A destroying step three
    /// nodes down is still a destroying step, and a warning that only
    /// showed while that node happened to be selected would be a warning
    /// nobody sees.
    /// </remarks>
    private void ShowWarning()
    {
        ShowSummary();
        var destructive = Anywhere(_chain).Any(
            step => step["type"]?.GetValue<string>() == "system"
                    && _actions.Any(
                        a => a.Destructive
                             && a.Value == step["target"]?.GetValue<string>()));
        Warning.Text = destructive
            ? S("В команде есть необратимое действие — Рина спросит подтверждение.")
            : "";
        Warning.Visibility = destructive ? Visibility.Visible
                                         : Visibility.Collapsed;
    }

    /// <summary>Every step of the graph, at every depth.</summary>
    private static IEnumerable<JsonObject> Anywhere(JsonArray steps)
    {
        foreach (var step in steps.OfType<JsonObject>())
        {
            yield return step;
            foreach (var branch in new[] { "steps", "otherwise" })
                if (step[branch] is JsonArray inner)
                    foreach (var deeper in Anywhere(inner))
                        yield return deeper;
        }
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

    // -- the inspector: the selected node, in full (4.0b-A09) ---------------

    /// <summary>
    /// Show whichever node is selected, and nothing else.
    /// </summary>
    /// <remarks>
    /// The fields used to sit in the row itself, which meant every row was
    /// as wide as its widest field and a graph of them could not be read at
    /// a glance. A node now carries its name on the canvas and its details
    /// here: the canvas answers "what shape is this", the inspector answers
    /// "what exactly does this one do", and neither has to do both.
    /// </remarks>
    private void ShowPicked()
    {
        Picked.Children.Clear();
        if (_picked is null)
        {
            PickedTitle.Text = S("НИЧЕГО НЕ ВЫБРАНО");
            PickedHint.Visibility = Visibility.Visible;
            return;
        }
        PickedHint.Visibility = Visibility.Collapsed;

        var step = _picked;
        var kind = step["type"]?.GetValue<string>() ?? "speak";
        var known = _stepKinds.FirstOrDefault(k => k.Value == kind);
        PickedTitle.Text = ((known.Icon ?? "") + " "
                            + (known.Title ?? kind)).ToUpperInvariant();

        foreach (var control in Fields(step, kind))
            Picked.Children.Add(control);

        // Moving and removing live here too: they are about the node, and
        // three small controls on every card of the canvas would be three
        // things competing with the one thing a node is for — saying what
        // it is.
        var hands = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Margin = new Thickness(0, 14, 0, 0),
        };
        hands.Children.Add(Hand("↑", S("Выше"), () => Move(-1)));
        hands.Children.Add(Hand("↓", S("Ниже"), () => Move(+1)));
        hands.Children.Add(Hand("✕", S("Убрать шаг"), Remove));
        Picked.Children.Add(hands);
    }

    private IEnumerable<UIElement> Fields(JsonObject step, string kind)
    {
        var made = new List<UIElement>();

        void Label(string said) => made.Add(new TextBlock
        {
            Text = said,
            Style = (Style)FindResource("Text.Meta"),
            Margin = new Thickness(0, 8, 0, 4),
        });

        void Field(string key, string hint)
        {
            var box = new TextBox
            {
                Style = (Style)FindResource("Field"),
                Text = step[key]?.GetValue<string>() ?? "",
            };
            Styles.Ui.SetHint(box, hint);
            box.TextChanged += (_, _) =>
            {
                step[key] = box.Text;
                DrawSteps();
                ShowSummary();
            };
            made.Add(box);
        }

        void Choice(IEnumerable<(string Value, string Title)> options,
                    string key)
        {
            var pick = new ComboBox
            {
                Style = (Style)FindResource("Choice"),
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
                ShowWarning();
            };
            made.Add(pick);
        }

        switch (kind)
        {
            case "system":
                // A fresh step picks the first harmless action rather than
                // nothing: an empty dropdown in a node somebody just added
                // is a question with no default answer.
                if ((step["target"]?.GetValue<string>() ?? "").Length == 0
                    && _actions.FirstOrDefault(a => !a.Destructive)
                        is { Value.Length: > 0 } safe)
                    step["target"] = safe.Value;
                Label(S("Какое действие"));
                Choice(_actions.Select(a => (a.Value, a.Destructive
                           ? a.Title + S(" — необратимо") : a.Title)),
                       "target");
                break;

            case "pause":
                Label(S("Сколько секунд"));
                Field("target", S("секунд"));
                break;

            case "repeat":
                Label(S("Сколько раз"));
                var times = new TextBox
                {
                    Style = (Style)FindResource("Field"),
                    Text = ((int)Number(step["count"])).ToString(),
                };
                times.TextChanged += (_, _) =>
                {
                    step["count"] = int.TryParse(times.Text, out var n)
                        ? Math.Clamp(n, 0, _maxRepeat) : 1;
                    DrawSteps();
                    ShowSummary();
                };
                made.Add(times);
                break;

            case "while":
            case "if":
                Label(S("Условие"));
                Choice(_conditions, "condition");
                var asks = step["condition"]?.GetValue<string>() ?? "";
                // Only a condition that asks about something gets a field
                // for it: "today is a weekday" has nothing to fill in, and
                // a box beside it would be a question with no answer.
                if (asks is "var_is" or "var_set")
                {
                    Label(S("Имя значения"));
                    Field("name", S("например, режим"));
                }
                if (asks is "after" or "before")
                {
                    Label(S("Во сколько"));
                    Field("value", "18:00");
                }
                else if (asks is "exists" or "missing")
                {
                    Label(S("Путь"));
                    Field("value", S("путь"));
                }
                else if (asks is "app_active" or "app_running")
                {
                    Label(S("Какая программа"));
                    Field("value", S("например, chrome"));
                }
                else if (asks == "date_is")
                {
                    Label(S("Какое число"));
                    Field("value", "1");
                }
                else if (asks == "var_is")
                {
                    Label(S("Равно чему"));
                    Field("value", S("значение"));
                }
                break;

            case "set":
                Label(S("Имя значения"));
                Field("name", S("например, режим"));
                Label(S("Что запомнить"));
                Field("value", S("значение"));
                break;

            case "call":
                Label(S("Какую команду вызвать"));
                Choice(_callable, "target");
                break;

            case "stop":
                Label(S("Дальше ничего не выполнится."));
                break;

            default:
                Label(kind switch
                {
                    "app" => S("Какую программу открыть"),
                    "folder" => S("Какую папку открыть"),
                    "website" => S("Какой адрес открыть"),
                    _ => S("Что произнести"),
                });
                Field("target", kind switch
                {
                    "app" => S(@"например, C:\Program Files\App\app.exe"),
                    "folder" => S(@"например, D:\Проекты"),
                    "website" => S("например, github.com"),
                    _ => S("что произнести"),
                });
                if (kind is "app" or "folder")
                {
                    var browse = new Button
                    {
                        Style = (Style)FindResource("Btn"),
                        Content = S("Обзор…"),
                        HorizontalAlignment = HorizontalAlignment.Left,
                        Margin = new Thickness(0, 8, 0, 0),
                    };
                    browse.Click += (_, _) =>
                    {
                        var got = Pick(kind);
                        if (got is null) return;
                        step["target"] = got;
                        DrawSteps();
                        ShowSummary();
                    };
                    made.Add(browse);
                }
                break;
        }
        return made;
    }

    private Button Hand(string mark, string tip, Action press)
    {
        var button = new Button
        {
            Style = (Style)FindResource("Btn.Quiet"),
            Content = mark,
            Width = 30,
            Height = 30,
            ToolTip = tip,
        };
        button.Click += (_, _) => press();
        return button;
    }

    private void Move(int delta)
    {
        if (_pickedOwner is null || _picked is null) return;
        var to = _pickedAt + delta;
        if (to < 0 || to >= _pickedOwner.Count) return;
        var moving = _pickedOwner[_pickedAt];
        _pickedOwner.RemoveAt(_pickedAt);
        _pickedOwner.Insert(to, moving);
        _pickedAt = to;
        DrawSteps();
        ShowSummary();
    }

    private void Remove()
    {
        if (_pickedOwner is null) return;
        _pickedOwner.RemoveAt(_pickedAt);
        _picked = null;
        _pickedOwner = null;
        DrawSteps();
        ShowSummary();
    }

    /// <summary>What may go in here.</summary>
    /// <remarks>
    /// The nesting limit belongs to the core and arrives with the kinds. A
    /// window that let a person build something the core will refuse to run
    /// would be lying to them while they worked.
    /// </remarks>
    private void OfferKinds(FrameworkElement near, JsonArray steps, int at)
    {
        var menu = new ContextMenu { PlacementTarget = near };
        foreach (var (value, title, icon) in _stepKinds)
        {
            var item = new MenuItem { Header = icon + "  " + title };
            item.Click += (_, _) =>
            {
                var made = NewStep(value);
                steps.Insert(Math.Clamp(at, 0, steps.Count), made);
                _picked = made;
                _pickedOwner = steps;
                _pickedAt = at;
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
        ["condition"] = kind is "if" or "while" ? "after" : "",
        ["value"] = kind is "if" or "while" ? "18:00" : "",
        ["name"] = "",
    };

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

    /// <summary>A step in human words: the kind and what exactly.</summary>
    private string DescribeStep(JsonObject step)
    {
        var kind = step["type"]?.GetValue<string>() ?? "";
        var target = step["target"]?.GetValue<string>() ?? "";
        var known = _stepKinds.FirstOrDefault(k => k.Value == kind);
        var title = known.Title ?? kind;

        // A system action's target is a code from a list, and there is no
        // point showing it to a person: the action has a name.
        if (kind == "system")
        {
            var named = _actions.FirstOrDefault(a => a.Value == target);
            return $"{title} · {(named.Title.Length > 0 ? named.Title : target)}";
        }
        return target.Length > 0 ? $"{title} · {target}" : title;
    }

    private void OnSave(object sender, RoutedEventArgs e)
    {
        if (_triggers.Count == 0)
        {
            Note.Text = S("Нужна хотя бы одна фраза.");
            return;
        }
        if (_chain.Count == 0)
        {
            Note.Text = S("Нужен хотя бы один шаг.");
            return;
        }

        var command = Card();
        // The number is assigned by the core; we send our own only when
        // editing one that already exists — otherwise editing would turn
        // into creating a twin.
        if (_id.Length > 0) command["id"] = _id;

        Saved?.Invoke(command);
    }

    /// <summary>The card as the core expects it.</summary>
    /// <remarks>
    /// <para>
    /// One place, used by saving and by trying alike. Two builders would
    /// part company the first time a field was added, and a trial would
    /// then be a trial of something slightly different from what gets
    /// saved — the one thing a trial must not be.
    /// </para>
    /// <para>
    /// <b>A graph of one plain node is saved as the plain card it is.</b>
    /// A sequence wrapping a single "open the browser" would be a new shape
    /// for a thing that has had a shape since 2.0.0: files from older
    /// versions would still read, but files written here would stop reading
    /// in them, and the list would start calling every command a sequence.
    /// </para>
    /// </remarks>
    private JsonObject Card()
    {
        var only = _chain.Count == 1 ? _chain[0] as JsonObject : null;
        var alone = only is not null
                    && StandsAlone(only["type"]?.GetValue<string>() ?? "");

        var card = new JsonObject
        {
            ["enabled"] = true,
            ["type"] = alone ? only!["type"]!.DeepClone() : "sequence",
            ["triggers"] = new JsonArray(
                _triggers.Select(p => (JsonNode)p!).ToArray()),
            ["match"] = "contains",
            ["target"] = alone ? (only!["target"]?.DeepClone() ?? "") : "",
            ["response"] = Response.Text.Trim(),
            ["steps"] = alone
                ? new JsonArray()
                : new JsonArray(_chain.Select(s => s!.DeepClone()).ToArray()),
        };
        return card;
    }

    /// <summary>The person wants to see it happen (`4.0b-A09`).</summary>
    public event Action<JsonObject>? Tried;

    /// <summary>
    /// Assemble a graph out of steps — for the end-to-end check.
    /// </summary>
    /// <remarks>
    /// The check cannot click, and a command assembled by hand would be
    /// testing `JsonObject` rather than the editor. So it goes the way a
    /// person does: put a node in at a place, fill in what it acts on,
    /// move one, save.
    /// </remarks>
    public bool BuildSequenceForCheck(
        string phrase, IEnumerable<(string Kind, string Target)> steps)
    {
        _triggers.Clear();
        _triggers.Add(phrase);
        DrawTriggers();

        _chain.Clear();
        foreach (var (kind, target) in steps)
        {
            var step = NewStep(kind);
            step["target"] = target;
            _chain.Add(step);
        }
        DrawSteps();
        if (_chain.Count == 0) return false;

        // And the order: lift the last node one place and put it back.
        var wasFirst = _chain[0]?["target"]?.GetValue<string>();
        var wasLast = _chain[^1]?["target"]?.GetValue<string>();
        _picked = _chain[^1] as JsonObject;
        _pickedOwner = _chain;
        _pickedAt = _chain.Count - 1;
        Move(-1);
        Move(+1);
        if (_chain[0]?["target"]?.GetValue<string>() != wasFirst) return false;
        if (_chain[^1]?["target"]?.GetValue<string>() != wasLast) return false;

        OnSave(this, new RoutedEventArgs());
        return true;
    }

    /// <summary>Close it as a person would — for the check.</summary>
    public void CancelForCheck() => OnCancel(this, new RoutedEventArgs());

    /// <summary>Start from an empty canvas — for the check.</summary>
    public void ClearForCheck()
    {
        _chain.Clear();
        _picked = null;
        _pickedOwner = null;
        DrawSteps();
    }

    /// <summary>Put a node in at a place — for the check.</summary>
    public void InsertStepForCheck(int at, string kind, string target = "")
    {
        var step = NewStep(kind);
        if (target.Length > 0) step["target"] = target;
        _chain.Insert(Math.Clamp(at, 0, _chain.Count), step);
        DrawSteps();
        ShowSummary();
    }

    /// <summary>Put a node inside another one — for the check.</summary>
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

    /// <summary>Select a node — for the check.</summary>
    public bool PickForCheck(int at)
    {
        if (at < 0 || at >= _chain.Count) return false;
        _picked = _chain[at] as JsonObject;
        _pickedOwner = _chain;
        _pickedAt = at;
        DrawSteps();
        return _picked is not null;
    }

    /// <summary>Is the inspector showing something — for the check.</summary>
    public bool InspectorShows => _picked is not null
                                  && Picked.Children.Count > 0;

    /// <summary>How many nodes are drawn on the canvas — for the check.</summary>
    public int NodesDrawn => Board.Children.OfType<Border>()
        .Count(b => b.Width > 100);

    /// <summary>How many wires are drawn — for the check.</summary>
    public int WiresDrawn => Board.Children.OfType<Polyline>().Count();

    /// <summary>The steps as the core will get them — for the check.</summary>
    public JsonArray ChainForCheck => _chain;

    /// <summary>Which kinds the window offers as steps — for the check.</summary>
    public string[] StepKindsOffered =>
        _stepKinds.Select(k => k.Value).ToArray();

    /// <summary>The card that would be saved — for the check.</summary>
    public JsonObject CardForCheck() => Card();

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
    /// <remarks>
    /// A simple command is a graph of one node now, so filling one in means
    /// putting that node on the canvas. There is no "kind of command" to
    /// choose first.
    /// </remarks>
    public void FillForCheck(string phrase, string kind, string target)
    {
        _triggers.Clear();
        _triggers.Add(phrase);
        DrawTriggers();
        _chain.Clear();
        var only = NewStep(kind);
        only["target"] = target;
        _chain.Add(only);
        DrawSteps();
        ShowSummary();
    }

    private void OnCancel(object sender, RoutedEventArgs e) =>
        Cancelled?.Invoke();

    /// <summary>
    /// Try it without saving.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Assembling a command and finding out whether it does what was meant
    /// were two separate acts: save, close the editor, find the row, press
    /// «Выполнить» — and if it was wrong, open it again. Trying four times
    /// left four commands to delete.
    /// </para>
    /// <para>
    /// <b>Phrases are not needed for this.</b> A phrase is how a command is
    /// found when spoken; a trial is pressed, not said.
    /// </para>
    /// </remarks>
    private void OnTry(object sender, RoutedEventArgs e)
    {
        if (_chain.Count == 0)
        {
            Note.Text = S("Нечего пробовать: шагов пока нет.");
            return;
        }
        Note.Text = S("Пробую…");
        // The last run's colours go before the next one starts. Left on,
        // they would be read as this run's, and a person would see a
        // scenario "already finished" a moment before it began.
        TrialStarting();
        Tried?.Invoke(Card());
    }

    /// <summary>Press «Проверить» — for the check.</summary>
    public void TryForCheck() => OnTry(this, new RoutedEventArgs());
}
