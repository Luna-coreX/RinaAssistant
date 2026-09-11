using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>A command of one's own, as a person sees it.</summary>
public sealed record UserCommand(string Id, string Name, string What,
                                 bool Enabled);

/// <summary>
/// Commands: what a person has taught Rina themselves.
/// </summary>
/// <remarks>
/// The section became possible only once the protocol had methods
/// (<c>4.0-F04</c>): before that it had a place in the architecture and no
/// way of doing anything. Switching off is separate from deleting because
/// these are different intents, and in the surface inventory they are
/// written down as separate lines.
/// </remarks>
public partial class CommandsPage : UserControl
{
    private readonly CoreLink? _link;
    private readonly ObservableCollection<UserCommand> _items = [];

    public CommandsPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;

        if (_link is null)
        {
            Empty.Content = EmptyState.For(
                S("Ядро не на связи"),
                S("Команды живут в ядре, а связи с ним сейчас нет."));
            Empty.Visibility = Visibility.Visible;
            return;
        }
        Loaded += async (_, _) =>
        {
            await ReloadAsync();
            // The built-in list is re-read once: it does not change
            // because the person added a command of their own.
            await ShowBuiltinAsync();
        };
    }

    private async Task ReloadAsync()
    {
        // Kinds are asked for before the list: otherwise the first draw
        // manages to show "app" instead of "Program". And so it did — and
        // what saw it was not a check run but a screenshot: the check
        // clicked the editor open earlier and got the kinds along the way,
        // whereas a person simply opens the page.
        await KindsAsync();
        var told = await Ask(Methods.CommandsList);
        _items.Clear();
        if (told?["items"] is JsonArray items)
        {
            foreach (var item in items)
            {
                if (item is not JsonObject command) continue;
                _raw[command["id"]?.GetValue<string>() ?? ""] = command;
                _items.Add(new UserCommand(
                    command["id"]?.GetValue<string>() ?? "",
                    NameOf(command),
                    Describe(command),
                    command["enabled"]?.GetValue<bool>() ?? true));
            }
        }

        Legend.Text = _programsFound > 0
            ? S("СВОИ И ВСТРОЕННЫЕ · программ найдено: {0}", _programsFound)
            : S("СВОИ И ВСТРОЕННЫЕ");
        // Here the empty state does not take over the page: below it is a
        // list of what Rina can do without any commands of one's own, and
        // that is far more useful than emptiness.
        Empty.Content = _items.Count == 0
            ? EmptyState.For(
                S("Своих команд пока нет"),
                S("Своя команда — это фраза и то, что по ней происходит: открыть программу, сказать текст, сделать несколько дел подряд."))
            : null;
        Empty.Visibility = _items.Count == 0 ? Visibility.Visible
                                             : Visibility.Collapsed;
        DrawGroups();
    }

    //: The built-in skills as **data**, not as ready-made rows.
    //:
    //: Rows were kept at first, and the second draw threw: an element that
    //: still belongs to the panel from the previous draw cannot be added to
    //: a new one. Clearing the group column does not detach what is inside
    //: the columns it held. The failure did not look like a failure — the
    //: check task died unobserved and the program sat there — which is why
    //: the harness now says so out loud.
    private readonly List<JsonObject> _builtin = [];
    private int _programsFound;

    //: The order and the names of the kinds, as the core gives them. Kept
    //: so the page groups in the same order the editor offers, and calls a
    //: kind what the editor calls it.
    private readonly List<string> _kindOrder = [];
    private readonly Dictionary<string, string> _kindTitles = [];

    /// <summary>
    /// What to call a command in the list.
    /// </summary>
    /// <remarks>
    /// A command has no name: it has the phrases it fires on — and the
    /// first of them is what the person calls it by. The shell first asked
    /// the core for a "name" field and got emptiness back: the core stores
    /// `triggers`, and a name was never in there.
    /// </remarks>
    private static string NameOf(JsonObject command)
    {
        var first = command["triggers"]?.AsArray().FirstOrDefault()
                    ?.GetValue<string>();
        return string.IsNullOrWhiteSpace(first) ? S("без имени") : first;
    }

    /// <summary>What a command is made of — in words, not in fields.</summary>
    /// <remarks>
    /// Kinds are named the way the core names them (`commands.kinds`): the
    /// shell knew its own — `url`, `path` — and recognised not a single
    /// real one. An unfamiliar kind is shown as it is rather than hidden.
    /// </remarks>
    private string Describe(JsonNode? item)
    {
        var kind = item?["type"]?.GetValue<string>() ?? "";
        var target = item?["target"]?.GetValue<string>() ?? "";
        var steps = item?["steps"] as JsonArray;
        if (kind == "sequence")
            return S("Последовательность · шагов {0}", steps?.Count ?? 0);

        var title = _kinds is null ? kind
            : _kinds["kinds"]?.AsArray().OfType<JsonObject>()
                .FirstOrDefault(k => k["value"]?.GetValue<string>() == kind)
                ?["title"]?.GetValue<string>() ?? kind;
        return target.Length > 0 ? $"{title} · {target}" : title;
    }

    /// <summary>How the first command is described — for the end-to-end check.</summary>
    public string FirstDescription() =>
        _items.Count > 0 ? _items[0].What : "";

    /// <summary>
    /// Set up a command the same way a person sets one up.
    /// </summary>
    /// <remarks>
    /// The check cannot type into fields and press buttons, but it must go
    /// the same way: the editor assembles the card, the core assigns a
    /// number, the list is re-read. Going around that path would be testing
    /// the protocol rather than the page.
    /// </remarks>
    public async Task<bool> CreateForCheckAsync(string phrase, string kind,
                                                string target)
    {
        var kinds = await KindsAsync();
        if (kinds is null) return false;

        var saved = await Ask(Methods.CommandsSave, new JsonObject
        {
            ["command"] = new JsonObject
            {
                ["enabled"] = true,
                ["type"] = kind,
                ["triggers"] = new JsonArray(phrase),
                ["match"] = "contains",
                ["target"] = target,
                ["response"] = "",
            },
        });
        if (saved is null) return false;
        _editor = null;
        await ReloadAsync();
        return true;
    }

    /// <summary>Step kinds of the last saved sequence — for the check.</summary>
    public string StepsOfLastSaved()
    {
        var sequence = _raw.Values.LastOrDefault(
            c => c["type"]?.GetValue<string>() == "sequence");
        var steps = sequence?["steps"]?.AsArray().OfType<JsonObject>() ?? [];
        return string.Join(", ", steps.Select(
            s => s["type"]?.GetValue<string>() ?? "?"));
    }

    private readonly Dictionary<string, JsonObject> _raw = [];
    private JsonObject? _kinds;

    /// <summary>The open editor — for the end-to-end check.</summary>
    public CommandEditor? Editor => _editor;

    /// <summary>Whether the editor is open right now — for the check.</summary>
    /// <remarks>
    /// The editor no longer lives inside this page, so "is it open" is no
    /// longer "is there something in that box". It is open while this page
    /// holds it and the window has a place for it.
    /// </remarks>
    public bool EditorOpen => _editor is not null;

    /// <summary>How many commands are in the list — for the end-to-end check.</summary>
    public int CommandCount => _items.Count;

    /// <summary>Scroll the page — so a screenshot can reach the chain.</summary>
    public void ScrollTo(double offset) =>
        Scroll.ScrollToVerticalOffset(offset);

    /// <summary>Re-read the list — for the check.</summary>
    public Task ReloadForCheckAsync() => ReloadAsync();

    /// <summary>
    /// Built-in skills, and how many programs were found.
    /// </summary>
    /// <remarks>
    /// The list comes from the core: these are the phrases people say to
    /// her, that is, her vocabulary (`4.0-F08`). The number of programs the
    /// shell counts itself — the index lives with it (ADR 0009), and asking
    /// the core, which asked the shell in the first place, would mean
    /// driving a number over the wire.
    /// </remarks>
    private async Task ShowBuiltinAsync()
    {
        // The program count first: it is read from the cache and comes
        // instantly, while the built-in list waits for the core's answer.
        // The other order would leave the heading without its number for
        // the whole wait.
        var found = await Task.Run(() => Platform.AppIndex.Get().Count);
        _programsFound = found;

        var got = await Ask(Methods.CommandsBuiltin);
        _builtin.Clear();

        foreach (var item in got?["items"]?.AsArray().OfType<JsonObject>()
                             ?? [])
        {
            _builtin.Add(item);
        }
        DrawGroups();

        BuiltinCount = _builtin.Count;
    }

    /// <summary>How many built-in skills are shown — for the check.</summary>
    public int BuiltinCount { get; private set; }

    private async Task<JsonObject?> KindsAsync()
    {
        if (_kinds is not null) return _kinds;
        _kinds = await Ask(Methods.CommandsKinds);
        // The order and the names are kept as they arrive, so the page
        // groups in the core's order and calls a kind what the editor
        // calls it. Two lists of names for one set of kinds would part
        // company at the first addition.
        foreach (var kind in _kinds?["kinds"]?.AsArray().OfType<JsonObject>()
                             ?? [])
        {
            var value = kind["value"]?.GetValue<string>() ?? "";
            _kindOrder.Add(value);
            _kindTitles[value] = kind["title"]?.GetValue<string>() ?? "";
        }
        return _kinds;
    }

    // -- the lists, in groups that fold (4.0b-A09) --------------------------

    //: Which groups are folded. Kept on the page rather than in the
    //: settings: it is where somebody happens to be looking right now, not
    //: a preference, and a preference is a thing one has to find and undo.
    private readonly HashSet<string> _folded = [];

    //: Whether the folding has been set up once. The built-in group starts
    //: folded — it is the longest, the least often needed and the one
    //: nobody edits — but only the first time, so folding it open and
    //: pressing "refresh" does not fold it shut again.
    private bool _foldedOnce;

    /// <summary>Draw the commands, grouped by what they do.</summary>
    /// <remarks>
    /// <para>
    /// Grouped by kind rather than by a group a person names. Nothing new is
    /// stored: the kind is already on every command, and a page that
    /// organises itself out of what is there cannot go out of step with it.
    /// A named group would be a new field, a new editor for it, and a new
    /// way for a command to end up somewhere nobody looks.
    /// </para>
    /// <para>
    /// The order of the groups is the core's order of kinds, so the page
    /// and the editor's dropdown agree about which comes first. An
    /// unfamiliar kind gets a group of its own under its own name — the
    /// same rule as everywhere else here.
    /// </para>
    /// </remarks>
    private void DrawGroups()
    {
        Groups.Children.Clear();
        _drawn.Clear();

        var order = _kindOrder.ToList();
        var mine = _items
            .GroupBy(c => _raw.TryGetValue(c.Id, out var raw)
                          ? raw["type"]?.GetValue<string>() ?? "" : "")
            .OrderBy(g => order.IndexOf(g.Key) < 0 ? int.MaxValue
                                                   : order.IndexOf(g.Key));

        foreach (var group in mine)
            Groups.Children.Add(Group(
                "kind:" + group.Key, KindTitle(group.Key),
                group.Count(), Rows(group)));

        if (_builtin.Count > 0)
        {
            if (!_foldedOnce)
            {
                _folded.Add("builtin");
                _foldedOnce = true;
            }
            Groups.Children.Add(Group("builtin", S("УМЕЕТ СРАЗУ"),
                                      _builtin.Count, BuiltinRows()));
        }
    }

    /// <summary>One group: a heading that folds, and what is under it.</summary>
    private UIElement Group(string id, string title, int count, UIElement body)
    {
        _drawn.Add(id);
        var open = !_folded.Contains(id);

        var head = new Grid { Margin = new Thickness(0, 0, 0, 8) };
        head.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });
        head.ColumnDefinitions.Add(new ColumnDefinition());

        // The chevron points the way it will go, which is the convention
        // every list of this shape already uses.
        head.Children.Add(new TextBlock
        {
            Text = open ? "⌄" : "›",
            Style = (Style)FindResource("Text.Meta"),
            Width = 16,
            VerticalAlignment = VerticalAlignment.Center,
        });
        var words = new TextBlock
        {
            Text = $"{title} · {count}",
            Style = (Style)FindResource("Text.Section"),
            VerticalAlignment = VerticalAlignment.Center,
        };
        Grid.SetColumn(words, 1);
        head.Children.Add(words);

        // The whole heading is the target, not the chevron alone: a person
        // aiming at a group aims at its name.
        //
        // A border that takes a click rather than a button. A button
        // centres what is in it — the template does, and setting the
        // content alignment does not overrule it — so the headings sat in
        // the middle of the page above rows that began at the left edge.
        var press = new Border
        {
            Background = System.Windows.Media.Brushes.Transparent,
            Padding = new Thickness(0, 6, 0, 2),
            Cursor = System.Windows.Input.Cursors.Arrow,
            Child = head,
        };
        press.MouseLeftButtonDown += (_, _) =>
        {
            if (!_folded.Remove(id)) _folded.Add(id);
            DrawGroups();
        };
        press.MouseEnter += (_, _) => head.Opacity = 0.75;
        press.MouseLeave += (_, _) => head.Opacity = 1;

        var column = new StackPanel { Margin = new Thickness(0, 0, 0, 12) };
        column.Children.Add(press);
        if (open) column.Children.Add(body);
        return column;
    }

    private UIElement Rows(IEnumerable<UserCommand> commands)
    {
        var list = new ItemsControl
        {
            ItemsSource = commands.ToList(),
            ItemTemplate = (DataTemplate)FindResource("CommandRow"),
        };
        return new Border
        {
            Style = (Style)FindResource("Rows"),
            Child = list,
        };
    }

    private UIElement BuiltinRows()
    {
        var column = new StackPanel();
        foreach (var item in _builtin)
        {
            var about = new StackPanel();
            about.Children.Add(new TextBlock
            {
                Text = "«" + (item["phrase"]?.GetValue<string>() ?? "") + "»",
                Style = (Style)FindResource("Text.Body"),
            });
            about.Children.Add(new TextBlock
            {
                Text = item["what"]?.GetValue<string>() ?? "",
                Style = (Style)FindResource("Text.Meta"),
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 2, 0, 0),
            });
            column.Children.Add(new Border
            {
                Style = (Style)FindResource("Rows.Item"),
                Child = about,
            });
        }
        // The last row has no seam: it would coincide with the edge of the
        // block and cross out the rounding.
        if (column.Children.Count > 0
            && column.Children[^1] is Border tail)
            tail.BorderThickness = new Thickness(0);
        return new Border
        {
            Style = (Style)FindResource("Rows"),
            Child = column,
        };
    }

    /// <summary>What a group of commands of one kind is called.</summary>
    /// <remarks>
    /// The core's word for the kind, because the core is what runs it and
    /// the editor's dropdown says the same. A kind this shell does not know
    /// keeps its identifier: a group nobody named is still a group, and
    /// hiding it would hide the commands in it.
    /// </remarks>
    private string KindTitle(string kind) =>
        _kindTitles.TryGetValue(kind, out var said) && said.Length > 0
            ? said.ToUpperInvariant()
            : (kind.Length > 0 ? kind.ToUpperInvariant() : S("ПРОЧЕЕ"));

    /// <summary>How many groups are drawn — for the check.</summary>
    public int GroupsShown => Groups.Children.Count;

    //: The identifiers of the groups drawn, in order. Kept as they are
    //: built, because the check needs to tell a group of one kind from a
    //: group of another and the panel holds only elements.
    private readonly List<string> _drawn = [];

    /// <summary>Which groups are drawn — for the check.</summary>
    public string[] GroupIds => _drawn.ToArray();

    /// <summary>Is this group folded — for the check.</summary>
    public bool FoldedForCheck(string id) => _folded.Contains(id);

    /// <summary>Fold or unfold one — for the check.</summary>
    public void FoldForCheck(string id, bool folded)
    {
        if (folded) _folded.Add(id);
        else _folded.Remove(id);
        DrawGroups();
    }

    /// <summary>How tall the lists stand — for the check.</summary>
    /// <remarks>
    /// <para>
    /// Height rather than a count of rows. Counting was tried and could not
    /// be made to say the truth: rows of a person's own commands come from
    /// a template inside an <c>ItemsControl</c> and exist in the tree only
    /// once something has laid them out, while the built-in ones are added
    /// by hand and are there at once. The number came out as eleven
    /// built-in rows with the two above them missing — neither the rows on
    /// the screen nor anything else.
    /// </para>
    /// <para>
    /// What folding does is make the page shorter, and that is what is
    /// measured. It is also what a person sees, which is the better thing
    /// for a check to be looking at.
    /// </para>
    /// </remarks>
    public double ListHeight
    {
        get
        {
            Groups.UpdateLayout();
            return Groups.ActualHeight;
        }
    }

    private static IEnumerable<DependencyObject> Deep(DependencyObject root)
    {
        var count = System.Windows.Media.VisualTreeHelper.GetChildrenCount(root);
        for (var i = 0; i < count; i++)
        {
            var child = System.Windows.Media.VisualTreeHelper.GetChild(root, i);
            yield return child;
            foreach (var deeper in Deep(child)) yield return deeper;
        }
    }

    private async void OnCreate(object sender, RoutedEventArgs e)
        => await OpenEditorAsync(null);

    private async void OnEdit(object sender, RoutedEventArgs e)
    {
        if ((sender as Button)?.Tag is not string id) return;
        await OpenEditorAsync(_raw.GetValueOrDefault(id));
    }

    /// <summary>
    /// Open the editor — on a blank slate or over an existing command.
    /// </summary>
    /// <remarks>
    /// Creating and editing are one window and one core method
    /// (`commands.save`): for a person this is one action — they edit the
    /// card and save it. Separating them would mean making them remember
    /// whether the command exists yet.
    /// </remarks>
    public async Task<bool> OpenEditorAsync(JsonObject? existing)
    {
        var kinds = await KindsAsync();
        if (kinds is null) return false;

        var editor = new CommandEditor(kinds, existing);
        var id = existing?["id"]?.GetValue<string>() ?? "new";
        var title = existing is null
            ? S("Новая команда")
            : "✎  " + NameOf(existing);

        // The editor opens in a place of its own rather than inside the
        // list. It used to unfold above the very rows a person was
        // comparing it against and push them off the screen: the thing
        // being written and the things it must not clash with could not be
        // seen together, and a chain of eight steps had nowhere to go.
        var window = Window.GetWindow(this) as MainWindow;

        void Done()
        {
            _editor = null;
            window?.CloseWork(id);
        }

        editor.Cancelled += Done;
        editor.Saved += async command =>
        {
            var saved = await Ask(Methods.CommandsSave, new JsonObject
            {
                ["command"] = command,
            });
            if (saved is null) return;
            Done();
            Note.Text = S("Команда сохранена.");
            await ReloadAsync();
        };
        // A trial does not close the editor and does not touch the list:
        // the person is still assembling, and the point of trying is to go
        // on changing it afterwards.
        editor.Tried += async command =>
            await Ask(Methods.CommandsTry, new JsonObject
            {
                ["command"] = command,
            });

        _editor = editor;
        if (window is null)
        {
            // No window to put a section in — a check holding the page on
            // its own. The editor still exists and still works; it simply
            // has nowhere to be shown, and saying so is better than
            // pretending it opened.
            return false;
        }
        window.OpenWork(id, title, () => editor);
        return true;
    }

    //: The open editor — so a check can reach it.
    private CommandEditor? _editor;

    /// <summary>The editor now open, if any — for the check.</summary>
    public CommandEditor? OpenEditor => _editor;

    private async void OnToggle(object sender, RoutedEventArgs e)
    {
        if (sender is not CheckBox box || box.Tag is not string id) return;
        await Ask(Methods.CommandsSetEnabled, new JsonObject
        {
            ["id"] = id,
            ["enabled"] = box.IsChecked == true,
        });
        await ReloadAsync();
    }

    private async void OnRun(object sender, RoutedEventArgs e)
    {
        if ((sender as Button)?.Tag is not string id) return;
        await Ask(Methods.CommandRunById, new JsonObject
        {
            ["command_id"] = id,
        });
        Note.Text = S("Выполняю…");
    }

    private async void OnDelete(object sender, RoutedEventArgs e)
    {
        if ((sender as Button)?.Tag is not string id) return;
        await Ask(Methods.CommandsDelete, new JsonObject { ["id"] = id });
        await ReloadAsync();
    }

    private async void OnExport(object sender, RoutedEventArgs e)
    {
        // The core hands over **the whole contents of the file**,
        // together with its kind and format version (§6). The shell
        // neither parses nor reassembles it: it picks a place and writes.
        // It used to pull the list out of here and write a bare array —
        // and the file stopped being distinguishable from any other
        // array, the history among them.
        var told = await Ask(Methods.CommandsExport);
        if (told is null) return;

        var path = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            $"rina-commands-{DateTime.Now:yyyy-MM-dd-HHmm}.json");
        await File.WriteAllTextAsync(path, told.ToJsonString(
            new System.Text.Json.JsonSerializerOptions { WriteIndented = true }));
        Note.Text = S("Выгружено: {0}", path);
    }

    private async void OnImport(object sender, RoutedEventArgs e)
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Filter = S("Команды Рины (*.json)|*.json"),
            Title = S("Откуда взять команды"),
        };
        if (dialog.ShowDialog() != true) return;

        try
        {
            // The shell reads the file — it has the picker; the core
            // judges it. "Is this the right file", "is the format newer
            // than ours", "what of it may be let through" are meaning,
            // and meaning lives in the core (ADR 0006). What is left here
            // is to parse the JSON and pass it on as it is.
            var text = await File.ReadAllTextAsync(dialog.FileName);
            if (JsonNode.Parse(text) is not JsonNode content)
            {
                Note.Text = S("Файл не разобрался как JSON.");
                return;
            }
            var done = await Ask(Methods.CommandsImport, new JsonObject
            {
                ["file"] = content.DeepClone(),
            });
            // The core's refusal has already been put into the label —
            // "this is not a command file". Carrying on would overwrite
            // the reason with a report of "0 added", that is, say that
            // nothing happened instead of what actually did.
            if (done is null) return;

            var added = done["added"]?.GetValue<int>() ?? 0;
            var skipped = done["skipped"]?.GetValue<int>() ?? 0;
            // "Skipped" is named separately: a person has to understand
            // that what was already set up was not overwritten, rather than
            // guess where their commands went.
            Note.Text = S("Добавлено {0}, пропущено как уже известные {1}.",
                          added, skipped);
            await ReloadAsync();
        }
        catch (Exception error)
        {
            Note.Text = S("Не прочиталось: {0}", error.Message);
        }
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
