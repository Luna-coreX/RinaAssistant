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
        Items.ItemsSource = _items;

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

        Legend.Text = S("МОИ КОМАНДЫ · {0}", _items.Count);
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
    }

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
        EditorBox.Content = null;
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
    public CommandEditor? Editor => EditorBox.Content as CommandEditor;

    /// <summary>Whether the editor is showing right now — for the end-to-end check.</summary>
    public bool EditorOpen => EditorBox.Content is not null;

    /// <summary>How many commands are in the list — for the end-to-end check.</summary>
    public int CommandCount => _items.Count;

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
        BuiltinLegend.Text = found > 0
            ? S("УМЕЕТ СРАЗУ · программ найдено: {0}", found)
            : S("УМЕЕТ СРАЗУ");

        var got = await Ask(Methods.CommandsBuiltin);
        Builtin.Children.Clear();

        foreach (var item in got?["items"]?.AsArray().OfType<JsonObject>()
                             ?? [])
        {
            var card = new Border
            {
                Style = (Style)FindResource("Rows.Item"),
            };
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
            card.Child = about;
            Builtin.Children.Add(card);
        }

        // The last row has no seam: it would coincide with the edge of the
        // block and cross out the rounding.
        if (Builtin.Children.Count > 0
            && Builtin.Children[^1] is Border tail)
            tail.BorderThickness = new Thickness(0);

        BuiltinCount = Builtin.Children.Count;
    }

    /// <summary>How many built-in skills are shown — for the check.</summary>
    public int BuiltinCount { get; private set; }

    private async Task<JsonObject?> KindsAsync()
        => _kinds ??= await Ask(Methods.CommandsKinds);

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
        editor.Cancelled += () => EditorBox.Content = null;
        editor.Saved += async command =>
        {
            var saved = await Ask(Methods.CommandsSave, new JsonObject
            {
                ["command"] = command,
            });
            if (saved is null) return;
            EditorBox.Content = null;
            Note.Text = S("Команда сохранена.");
            await ReloadAsync();
        };
        EditorBox.Content = editor;
        return true;
    }

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
        var told = await Ask(Methods.CommandsExport);
        if (told?["commands"] is not JsonArray commands) return;

        var path = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            $"rina-commands-{DateTime.Now:yyyy-MM-dd-HHmm}.json");
        await File.WriteAllTextAsync(path, commands.ToJsonString());
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
            var text = await File.ReadAllTextAsync(dialog.FileName);
            if (JsonNode.Parse(text) is not JsonArray commands)
            {
                Note.Text = S("В файле не список команд.");
                return;
            }
            var done = await Ask(Methods.CommandsImport, new JsonObject
            {
                ["commands"] = commands.DeepClone(),
            });
            var added = done?["added"]?.GetValue<int>() ?? 0;
            var skipped = done?["skipped"]?.GetValue<int>() ?? 0;
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
