using System.Linq;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// What Rina knows about a person (<c>4.0b-B01</c>).
/// </summary>
/// <remarks>
/// <para>
/// One page for everything kept locally. The groups and their entries come
/// from the core, which walks its own store to assemble them; what a group
/// is <b>called</b> is decided here, because interface strings belong to the
/// shell (<c>4.0-F08</c>, ADR 0006).
/// </para>
/// <para>
/// <b>A group this page does not recognise is shown anyway</b>, under its
/// own identifier and with a line saying as much. The same rule as for an
/// unfamiliar settings key, and here it carries more weight: this is the one
/// screen that promises to be complete, and a category dropped in silence
/// would make that promise a lie told by the screen a person opened in order
/// to be told the truth.
/// </para>
/// </remarks>
public partial class PrivacyPage : UserControl
{
    private readonly CoreLink? _link;

    //: Which groups are opened out. Kept across a refresh: a person who
    //: opened the history and pressed "refresh" meant to see the history
    //: again, not to be put back at the top.
    private readonly HashSet<string> _open = [];

    /// <summary>How many entries a group shows before it is opened out.</summary>
    private const int Few = 5;

    public PrivacyPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;
        Loaded += async (_, _) => await ReloadAsync();
    }

    /// <summary>
    /// What each group is called, and what it is.
    /// </summary>
    /// <remarks>
    /// The note matters as much as the title. "Статистика" tells a person
    /// nothing about what is being kept; "сколько раз какая команда
    /// выполнялась" tells them they are looking at a record of their own
    /// habits, which is the thing they came here to find out.
    /// </remarks>
    private static (string Title, string Note) Named(string id) => id switch
    {
        "aliases" => (S("Выученные слова"),
            S("Как вы называете программы — Рина запомнила это из ваших поправок.")),
        "history" => (S("История разговора"),
            S("Сказанное и напечатанное вами, и ответы Рины. Ведётся, пока включено в настройках.")),
        "reminders" => (S("Напоминания"),
            S("То, о чём вы просили напомнить.")),
        "todo" => (S("Дела"), S("Список того, что ждёт.")),
        "commands" => (S("Свои команды"),
            S("Фразы, которые вы завели, и что по ним происходит.")),
        "stats" => (S("Статистика команд"),
            S("Сколько раз какая команда выполнялась и когда в последний раз.")),
        "plugins" => (S("Плагины"),
            S("Какие включены и что они у себя сохранили.")),
        "folders" => (S("Папки поиска программ"),
            S("Где вы велели искать программы.")),
        "settings" => (S("Изменённые настройки"),
            S("Только то, что вы меняли сами: нетронутое по умолчанию ничего о вас не говорит.")),
        _ => (id, S("Оболочка не знает, что это за данные, — поэтому показывает как есть.")),
    };

    public async Task ReloadAsync()
    {
        Groups.Children.Clear();
        var told = await Ask(Methods.PrivacyInventory);
        if (told is null)
        {
            // Said out loud rather than left blank. "Nothing is kept" and
            // "we could not ask" look the same on an empty page, and on
            // this page of all pages they must not.
            Empty.Content = EmptyState.For(
                S("Не удалось спросить"),
                S("Ядро не на связи, поэтому опись показать нечем."));
            Empty.Visibility = Visibility.Visible;
            return;
        }

        var groups = (told["groups"] as JsonArray ?? []).OfType<JsonObject>()
            .ToList();
        var total = groups.Sum(g => (int)Number(g["count"]));

        Empty.Visibility = total == 0 ? Visibility.Visible : Visibility.Collapsed;
        if (total == 0)
        {
            Empty.Content = EmptyState.For(
                S("Пока ничего"),
                S("Рина ещё ничего о вас не запомнила: поговорите с ней, и здесь появятся записи."));
            Note.Text = "";
            return;
        }

        foreach (var group in groups) Groups.Children.Add(Card(group));
        Note.Text = S("Всего записей: {0}", total);
    }

    private UIElement Card(JsonObject group)
    {
        var id = group["id"]?.GetValue<string>() ?? "";
        var count = (int)Number(group["count"]);
        var items = (group["items"] as JsonArray ?? []).OfType<JsonObject>()
            .ToList();
        var (title, note) = Named(id);

        var body = new StackPanel();
        var head = new Grid();
        head.ColumnDefinitions.Add(new ColumnDefinition());
        head.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });

        var words = new StackPanel();
        words.Children.Add(new TextBlock
        {
            Text = title,
            Style = (Style)FindResource("Text.Body"),
        });
        words.Children.Add(new TextBlock
        {
            Text = note,
            Style = (Style)FindResource("Text.Meta"),
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 2, 0, 0),
        });
        head.Children.Add(words);

        var many = new TextBlock
        {
            Text = count.ToString(),
            Style = (Style)FindResource("Text.Figure"),
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(16, 0, 0, 0),
        };
        Grid.SetColumn(many, 1);
        head.Children.Add(many);
        body.Children.Add(head);

        // An empty group is shown, with its zero. "Nothing is kept here" is
        // an answer a person came for, and a group that disappears when it
        // empties leaves them to wonder whether it ever existed.
        if (count > 0)
        {
            var opened = _open.Contains(id);
            var shown = opened ? items : items.Take(Few).ToList();

            var rows = new StackPanel { Margin = new Thickness(0, 12, 0, 0) };
            foreach (var item in shown) rows.Children.Add(Row(item));
            body.Children.Add(rows);

            if (items.Count > Few)
            {
                var more = new Button
                {
                    Style = (Style)FindResource("Btn.Quiet"),
                    Content = opened
                        ? S("Свернуть")
                        : S("Показать все {0}", items.Count),
                    HorizontalAlignment = HorizontalAlignment.Left,
                    Width = double.NaN,
                    Margin = new Thickness(0, 8, 0, 0),
                    Padding = new Thickness(8, 0, 8, 0),
                };
                more.Click += async (_, _) =>
                {
                    if (!_open.Remove(id)) _open.Add(id);
                    await ReloadAsync();
                };
                body.Children.Add(more);
            }
        }

        return new Border
        {
            Style = (Style)FindResource("Card"),
            Margin = new Thickness(0, 0, 0, 12),
            Child = body,
        };
    }

    private UIElement Row(JsonObject item)
    {
        var row = new Grid { Margin = new Thickness(0, 0, 0, 6) };
        row.ColumnDefinitions.Add(new ColumnDefinition());
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });

        var what = item["what"]?.GetValue<string>() ?? "";
        var detail = item["detail"]?.GetValue<string>() ?? "";
        var where = item["where"]?.GetValue<string>() ?? "";

        var words = new StackPanel();
        words.Children.Add(new TextBlock
        {
            Text = what,
            Style = (Style)FindResource("Text.Body"),
            TextWrapping = TextWrapping.Wrap,
        });

        // The two lesser fields on one line, and only the ones that are
        // there: "· " in front of nothing is a row reporting a field the
        // entry does not have.
        var aside = string.Join(" · ",
            new[] { detail, where }.Where(part => part.Length > 0));
        if (aside.Length > 0)
            words.Children.Add(new TextBlock
            {
                Text = aside,
                Style = (Style)FindResource("Text.Meta"),
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 1, 0, 0),
            });
        row.Children.Add(words);

        var when = Number(item["when"]);
        if (when > 0)
        {
            var stamp = new TextBlock
            {
                Text = DateTimeOffset.FromUnixTimeSeconds((long)when)
                    .LocalDateTime.ToString("dd.MM HH:mm"),
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Top,
                Margin = new Thickness(16, 0, 0, 0),
            };
            Grid.SetColumn(stamp, 1);
            row.Children.Add(stamp);
        }

        return row;
    }

    private async void OnRefresh(object sender, RoutedEventArgs e) =>
        await ReloadAsync();

    /// <summary>
    /// Draw an inventory handed in from outside — for the check.
    /// </summary>
    /// <remarks>
    /// The one thing that cannot be checked against a live core: a group
    /// this page has never heard of. The core only ever sends the groups it
    /// has, and the failure being guarded against is what happens the day
    /// it sends one more — so the one more is handed in here.
    /// </remarks>
    public void ShowForCheck(JsonArray groups)
    {
        Groups.Children.Clear();
        Empty.Visibility = Visibility.Collapsed;
        foreach (var group in groups.OfType<JsonObject>())
            Groups.Children.Add(Card(group));
    }

    /// <summary>How many groups are drawn — for the check.</summary>
    public int GroupsShown => Groups.Children.Count;

    /// <summary>
    /// Is a group with this identifier on the screen — for the check.
    /// </summary>
    /// <remarks>
    /// By what the card says, not by counting cards: the failure this
    /// guards against is a group being dropped, and a count would stay
    /// right while the wrong groups were shown.
    /// </remarks>
    public bool ShowsGroup(string title) =>
        Groups.Children.OfType<Border>()
            .SelectMany(card => Deep(card).OfType<TextBlock>())
            .Any(words => words.Text == title);

    /// <summary>Everything written on the page — for the check.</summary>
    public string[] Said =>
        Groups.Children.OfType<Border>()
            .SelectMany(card => Deep(card).OfType<TextBlock>())
            .Select(words => words.Text)
            .ToArray();

    /// <summary>
    /// A number from the answer, whatever shape it arrived in.
    /// </summary>
    /// <remarks>
    /// <c>GetValue&lt;double&gt;()</c> throws on a node that holds an
    /// integer, and JSON does not distinguish the two: a timestamp of
    /// exactly zero arrives as `0`, not `0.0`. The page died on it — and
    /// the first thing it died on was a group nobody had claimed, which is
    /// to say the exact case this page exists to survive.
    /// </remarks>
    private static double Number(JsonNode? node)
    {
        if (node is not JsonValue value) return 0;
        if (value.TryGetValue<double>(out var exact)) return exact;
        if (value.TryGetValue<long>(out var whole)) return whole;
        if (value.TryGetValue<int>(out var small)) return small;
        // Last resort, through the text. `TryGetValue` answers about the
        // CLR type the node happens to hold, not about the number in the
        // JSON: a node made from an `int` says no to `long` as readily as
        // to `double`, and every "no" here is a count that renders as zero
        // and a group whose contents then go unshown.
        return double.TryParse(value.ToJsonString(),
                               System.Globalization.NumberStyles.Any,
                               System.Globalization.CultureInfo.InvariantCulture,
                               out var told) ? told : 0;
    }

    private static IEnumerable<DependencyObject> Deep(DependencyObject root)
    {
        var count = System.Windows.Media.VisualTreeHelper
            .GetChildrenCount(root);
        for (var i = 0; i < count; i++)
        {
            var child = System.Windows.Media.VisualTreeHelper
                .GetChild(root, i);
            yield return child;
            foreach (var deeper in Deep(child)) yield return deeper;
        }
    }

    private async Task<JsonObject?> Ask(string method,
                                        JsonObject? payload = null)
    {
        if (_link is null) return null;
        return await _link.AskAsync(method, payload);
    }
}
