using System.Linq;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// The list of things waiting to be done (<c>4.0b-A13</c>).
/// </summary>
/// <remarks>
/// <para>
/// A window rather than a tab. A person opens the list, does something to
/// it and goes back to what they were doing; a tab is where one lives, a
/// window is where one looks in. The same decision as the lists in the
/// settings (<c>4.0b-A10</c>).
/// </para>
/// <para>
/// <b>Closing does not delete.</b> A closed thing stays, greyed, and can be
/// reopened: a person changes their mind, and something that vanished can
/// neither be brought back nor remembered. Deleting is a separate press,
/// and it says so.
/// </para>
/// </remarks>
public partial class TodoWindow : Window
{
    private readonly CoreLink? _link;

    public TodoWindow(CoreLink? link)
    {
        InitializeComponent();
        _link = link;
        Loaded += async (_, _) => await ReloadAsync();
    }

    /// <summary>How many rows are shown — for the check.</summary>
    public int Shown => Items.Children.Count;

    /// <summary>Is this text on the list right now — for the check.</summary>
    /// <remarks>
    /// By text rather than by count. A count is a race with the first load
    /// and a hostage to whatever earlier runs left in the store: the check
    /// caught its own window mid-load, read zero, and then found three.
    /// </remarks>
    public bool ShowsForCheck(string text) =>
        Items.Children.OfType<Grid>()
            .SelectMany(row => row.Children.OfType<CheckBox>())
            .Any(tick => (tick.Content as string)?.Contains(
                text, StringComparison.Ordinal) == true);

    /// <summary>Add one from outside — for the check.</summary>
    public async Task AddForCheck(string text)
    {
        Input.Text = text;
        await AddAsync();
    }

    private async Task ReloadAsync()
    {
        Items.Children.Clear();
        var told = await Ask(Methods.TodoList);
        var all = (told?["items"] as JsonArray ?? []).OfType<JsonObject>()
            .ToList();

        var wanted = ShowDone.IsChecked == true
            ? all
            : all.Where(i => i["done"]?.GetValue<bool>() != true).ToList();

        foreach (var item in wanted) Items.Children.Add(Row(item));

        var open = all.Count(i => i["done"]?.GetValue<bool>() != true);
        Count.Text = open == 0 ? S("Ничего не ждёт")
                               : S("Ждёт: {0}", open);

        // The empty state says which kind of empty it is. "Nothing yet" and
        // "everything is done" are different news, and a person who has just
        // closed the last thing has earned the second one.
        Empty.Visibility = wanted.Count == 0 ? Visibility.Visible
                                             : Visibility.Collapsed;
        if (wanted.Count == 0)
            Empty.Content = EmptyState.For(
                all.Count == 0 ? S("Дел пока нет")
                               : S("Всё сделано"),
                all.Count == 0
                    ? S("Скажите «запиши купить хлеб» — или впишите сюда.")
                    : S("Закрытые никуда не делись: их видно переключателем."));
    }

    private UIElement Row(JsonObject item)
    {
        var id = item["id"]?.GetValue<string>() ?? "";
        var done = item["done"]?.GetValue<bool>() == true;

        var row = new Grid { Margin = new Thickness(0, 0, 0, 4) };
        row.ColumnDefinitions.Add(new ColumnDefinition());
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });

        var tick = new CheckBox
        {
            Content = item["text"]?.GetValue<string>() ?? "",
            IsChecked = done,
            Style = (Style)FindResource("Toggle"),
            VerticalAlignment = VerticalAlignment.Center,
            // A closed one is dimmed rather than struck through: a line
            // through the words makes them harder to read, and the thing a
            // person is scanning for is still the words.
            Opacity = done ? 0.55 : 1.0,
        };
        tick.Click += async (_, _) =>
        {
            await Ask(Methods.TodoClose, new JsonObject
            {
                ["todo_id"] = id,
                ["done"] = tick.IsChecked == true,
            });
            await ReloadAsync();
        };
        row.Children.Add(tick);

        var drop = new Button
        {
            Style = (Style)FindResource("Btn.Quiet"),
            Content = "✕",
            ToolTip = S("Убрать совсем"),
            VerticalAlignment = VerticalAlignment.Center,
        };
        drop.Click += async (_, _) =>
        {
            await Ask(Methods.TodoRemove,
                      new JsonObject { ["todo_id"] = id });
            await ReloadAsync();
        };
        Grid.SetColumn(drop, 1);
        row.Children.Add(drop);

        return row;
    }

    private async void OnAdd(object sender, RoutedEventArgs e) =>
        await AddAsync();

    private async void OnInputKey(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) await AddAsync();
    }

    private async Task AddAsync()
    {
        var text = Input.Text.Trim();
        if (text.Length == 0) return;
        Input.Clear();
        await Ask(Methods.TodoAdd, new JsonObject { ["text"] = text });
        await ReloadAsync();
    }

    private async void OnToggleDone(object sender, RoutedEventArgs e) =>
        await ReloadAsync();

    private void OnClose(object sender, RoutedEventArgs e) => Close();

    private async Task<JsonObject?> Ask(string method,
                                        JsonObject? payload = null)
    {
        if (_link is null) return null;
        return await _link.AskAsync(method, payload);
    }
}
