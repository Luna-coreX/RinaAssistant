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
        var told = await Ask(Methods.CommandsList);
        _items.Clear();
        if (told?["items"] is JsonArray items)
        {
            foreach (var item in items)
            {
                _items.Add(new UserCommand(
                    item?["id"]?.GetValue<string>() ?? "",
                    item?["name"]?.GetValue<string>() ?? S("без имени"),
                    Describe(item),
                    item?["enabled"]?.GetValue<bool>() ?? true));
            }
        }

        Legend.Text = S("МОИ КОМАНДЫ · {0}", _items.Count);
        Empty.Visibility = _items.Count == 0 ? Visibility.Visible
                                             : Visibility.Collapsed;
    }

    /// <summary>Из чего команда состоит — словами, а не полями.</summary>
    private static string Describe(JsonNode? item)
    {
        var kind = item?["kind"]?.GetValue<string>() ?? "";
        var target = item?["target"]?.GetValue<string>() ?? "";
        var steps = item?["steps"] as JsonArray;
        return kind switch
        {
            "app" => S("Программа · {0}", target),
            "url" => S("Ссылка · {0}", target),
            "path" => S("Папка или файл · {0}", target),
            "sequence" => S("Последовательность · шагов {0}",
                            steps?.Count ?? 0),
            _ => target.Length > 0 ? target : kind,
        };
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
