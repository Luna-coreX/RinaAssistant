using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>Своя команда, как её видит человек.</summary>
public sealed record UserCommand(string Id, string Name, string What,
                                 bool Enabled);

/// <summary>
/// Команды: то, чему человек научил Рину сам.
/// </summary>
/// <remarks>
/// Раздел стал возможен только после того, как в протоколе появились методы
/// (<c>4.0-F04</c>): до этого у него было место в архитектуре и ни одного
/// способа что-либо сделать. Выключение отдельно от удаления — это разные
/// намерения, и в инвентаре поверхности они записаны отдельными строками.
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
            Empty.Text = S("Ядро не на связи — команды недоступны.");
            Empty.Visibility = Visibility.Visible;
            return;
        }
        Loaded += async (_, _) => await ReloadAsync();
    }

    private async Task ReloadAsync()
    {
        // Виды спрашиваются до списка: иначе первая отрисовка успевает
        // показать «app» вместо «Программа». Так и было — и увидел это не
        // прогон проверки, а снимок: проверка щёлкала конструктор раньше и
        // получала виды заодно, а человек просто открывает страницу.
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
        Empty.Visibility = _items.Count == 0 ? Visibility.Visible
                                             : Visibility.Collapsed;
    }

    /// <summary>
    /// Как назвать команду в списке.
    /// </summary>
    /// <remarks>
    /// Имени у команды нет: есть фразы, по которым она срабатывает, — и
    /// первая из них и есть то, чем человек её называет. Поле «имя»
    /// оболочка сначала спрашивала у ядра и получала пустоту: ядро хранит
    /// `triggers`, и имени в нём никогда не было.
    /// </remarks>
    private static string NameOf(JsonObject command)
    {
        var first = command["triggers"]?.AsArray().FirstOrDefault()
                    ?.GetValue<string>();
        return string.IsNullOrWhiteSpace(first) ? S("без имени") : first;
    }

    /// <summary>Из чего команда состоит — словами, а не полями.</summary>
    /// <remarks>
    /// Виды называются так же, как их называет ядро (`commands.kinds`):
    /// оболочка знала свои — `url`, `path` — и не узнавала ни одного
    /// настоящего. Незнакомый вид показывается как есть, а не прячется.
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

    /// <summary>Как описана первая команда — для сквозной проверки.</summary>
    public string FirstDescription() =>
        _items.Count > 0 ? _items[0].What : "";

    /// <summary>
    /// Завести команду так же, как её заводит человек.
    /// </summary>
    /// <remarks>
    /// Проверка не умеет печатать в поля и нажимать кнопки, но обязана
    /// пройти тот же путь: конструктор собирает карточку, ядро назначает
    /// номер, список перечитывается. Обход этого пути проверял бы
    /// протокол, а не страницу.
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

    private readonly Dictionary<string, JsonObject> _raw = [];
    private JsonObject? _kinds;

    /// <summary>Показан ли сейчас конструктор — для сквозной проверки.</summary>
    public bool EditorOpen => EditorBox.Content is not null;

    /// <summary>Сколько команд в списке — для сквозной проверки.</summary>
    public int CommandCount => _items.Count;

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
    /// Открыть конструктор — на пустом месте или над существующей.
    /// </summary>
    /// <remarks>
    /// Создание и правка — одно окно и один метод у ядра
    /// (`commands.save`): для человека это одно действие, он правит
    /// карточку и сохраняет. Разделять их значит заставить его помнить,
    /// заведена команда или ещё нет.
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
            // «Пропущено» названо отдельно: человек должен понимать, что уже
            // настроенное не затёрли, а не гадать, куда делись команды.
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
