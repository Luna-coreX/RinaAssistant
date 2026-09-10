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

        if (count > 0)
        {
            var all = new Button
            {
                Style = (Style)FindResource("Btn.Quiet"),
                Content = "✕",
                ToolTip = S("Забыть всю группу"),
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(12, 0, 0, 0),
            };
            all.Click += async (_, _) =>
            {
                var ask = new ConfirmWindow(
                    S("Забыть всё в разделе «{0}»? Записей: {1}.",
                      title, count),
                    S("Вернуть это будет нельзя."), 0);
                ask.ShowDialog();
                if (ask.Result != Consent.Granted) return;
                await ForgetAsync(id, null);
            };
            Grid.SetColumn(all, 2);
            head.Children.Add(all);
        }
        body.Children.Add(head);

        // An empty group is shown, with its zero. "Nothing is kept here" is
        // an answer a person came for, and a group that disappears when it
        // empties leaves them to wonder whether it ever existed.
        if (count > 0)
        {
            var opened = _open.Contains(id);
            var shown = opened ? items : items.Take(Few).ToList();

            var rows = new StackPanel { Margin = new Thickness(0, 12, 0, 0) };

            // Opened out, entries that carry a time are gathered under the
            // day they happened on, and a day can be forgotten in one
            // press.
            //
            // The plan names "history for a date" among the things that
            // must be removable, and a person thinking about a
            // conversation thinks in days, not in rows: "forget yesterday"
            // is one thought, and ticking forty rows to express it is a
            // chore that ends in giving up. The rule is general rather
            // than about the history — any group whose entries are stamped
            // gets it, because "when" is what makes a day mean anything.
            var day = "";
            foreach (var item in shown)
            {
                var stamped = Number(item["when"]);
                if (opened && stamped > 0)
                {
                    var its = Day(item);
                    if (its != day)
                    {
                        day = its;
                        rows.Children.Add(DayHead(id, its, items));
                    }
                }
                rows.Children.Add(Row(id, item));
            }
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

    /// <summary>A day's heading, and the way to forget that day.</summary>
    private UIElement DayHead(string group, string day, List<JsonObject> all)
    {
        var mine = DayIds(all, day);

        var head = new Grid { Margin = new Thickness(0, 8, 0, 4) };
        head.ColumnDefinitions.Add(new ColumnDefinition());
        head.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });
        head.Children.Add(new TextBlock
        {
            Text = day,
            Style = (Style)FindResource("Text.Section"),
            VerticalAlignment = VerticalAlignment.Center,
        });

        var drop = new Button
        {
            Style = (Style)FindResource("Btn.Quiet"),
            Content = "✕",
            ToolTip = S("Забыть этот день"),
            VerticalAlignment = VerticalAlignment.Center,
        };
        drop.Click += async (_, _) =>
        {
            var ask = new ConfirmWindow(
                S("Забыть всё за {0}? Записей: {1}.", day, mine.Length),
                S("Вернуть это будет нельзя."), 0);
            ask.ShowDialog();
            if (ask.Result != Consent.Granted) return;
            await ForgetAsync(group, mine);
        };
        Grid.SetColumn(drop, 1);
        head.Children.Add(drop);
        return head;
    }

    /// <summary>Which entries fall on this day.</summary>
    /// <remarks>
    /// Its own method so that the check can ask the same question the
    /// button answers. Written inline, it would have been checkable only
    /// through what came out of the store afterwards — and "the right rows
    /// went" cannot tell a correct day from a day that happened to hold
    /// everything.
    /// </remarks>
    private static string[] DayIds(List<JsonObject> all, string day) =>
        all.Where(item => Number(item["when"]) > 0 && Day(item) == day)
            .Select(item => item["id"]?.GetValue<string>() ?? "")
            .ToArray();

    private static string Day(JsonObject item) =>
        DateTimeOffset.FromUnixTimeSeconds((long)Number(item["when"]))
            .LocalDateTime.ToString("dd.MM.yyyy");

    /// <summary>Which entries a day's button would forget — for the check.</summary>
    public static string[] DayIdsForCheck(JsonArray items, string day) =>
        DayIds(items.OfType<JsonObject>().ToList(), day);

    /// <summary>Forget one day of a group — for the check.</summary>
    public Task ForgetDayForCheck(string group, string[] ids) =>
        ForgetAsync(group, ids);

    private UIElement Row(string group, JsonObject item)
    {
        var row = new Grid { Margin = new Thickness(0, 0, 0, 6) };
        row.ColumnDefinitions.Add(new ColumnDefinition());
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });
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

        // One entry, forgotten without being asked twice.
        //
        // The confirmation is kept for a whole group and for everything:
        // asked on every single row it would become the thing a person
        // clicks through without reading, and then it would not be
        // protecting the two operations that need it.
        var drop = new Button
        {
            Style = (Style)FindResource("Btn.Quiet"),
            Content = "✕",
            ToolTip = S("Забыть эту запись"),
            VerticalAlignment = VerticalAlignment.Top,
            Margin = new Thickness(8, 0, 0, 0),
        };
        drop.Click += async (_, _) =>
            await ForgetAsync(group,
                              [item["id"]?.GetValue<string>() ?? ""]);
        Grid.SetColumn(drop, 2);
        row.Children.Add(drop);

        return row;
    }

    /// <summary>
    /// Forget, and say how much went.
    /// </summary>
    /// <remarks>
    /// The number comes from the core, not from what was asked for. "Done"
    /// over an entry still on the screen is how a person learns to
    /// distrust the button they came to this page to trust.
    /// </remarks>
    private async Task ForgetAsync(string group, string[]? ids)
    {
        var payload = new JsonObject { ["group"] = group };
        if (ids is not null)
            payload["ids"] = new JsonArray(
                ids.Select(id => (JsonNode)id!).ToArray());

        var answer = await Ask(Methods.PrivacyForget, payload);
        if (answer is null)
        {
            Note.Text = S("Ядро не на связи.");
            return;
        }
        var gone = (int)Number(answer["forgotten"]);
        Note.Text = gone > 0 ? S("Забыто записей: {0}", gone)
                             : S("Забывать было нечего.");
        await ReloadAsync();
    }

    private async void OnRefresh(object sender, RoutedEventArgs e) =>
        await ReloadAsync();

    /// <summary>
    /// Forget everything on this page (`4.0b-B02`).
    /// </summary>
    /// <remarks>
    /// Everything the page shows, preferences included: a person pressing
    /// this while looking at nine groups means the nine, not six of them.
    /// The confirmation says which, and says the count — "forget
    /// everything" is easy to press and hard to picture.
    /// </remarks>
    private async void OnForgetAll(object sender, RoutedEventArgs e)
    {
        var told = await Ask(Methods.PrivacyInventory);
        var total = (told?["groups"] as JsonArray ?? [])
            .OfType<JsonObject>().Sum(g => (int)Number(g["count"]));
        if (total == 0)
        {
            Note.Text = S("Забывать было нечего.");
            return;
        }

        var ask = new ConfirmWindow(
            S("Рина забудет всё, что здесь показано: записей {0}. Настройки вернутся к значениям по умолчанию.",
              total),
            S("Вернуть это будет нельзя. Команды, дела и напоминания тоже уйдут."),
            0);
        ask.ShowDialog();
        if (ask.Result != Consent.Granted) return;

        var answer = await Ask(Methods.PrivacyForget,
                               new JsonObject { ["everything"] = true });
        if (answer is null)
        {
            Note.Text = S("Ядро не на связи.");
            return;
        }
        Note.Text = S("Забыто записей: {0}", (int)Number(answer["forgotten"]));
        await ReloadAsync();
    }

    /// <summary>
    /// Save everything to a file (`4.0b-B03`).
    /// </summary>
    /// <remarks>
    /// Two formats, and the readable one is the point of the item: the
    /// program could already hand its data to another copy of itself, and
    /// what it could not do was hand it to the person whose data it is.
    /// The `.json` is the same envelope every other export uses, for
    /// moving between machines; the `.txt` is for reading.
    /// </remarks>
    private async void OnExport(object sender, RoutedEventArgs e)
    {
        var told = await Ask(Methods.PrivacyExport);
        if (told is null)
        {
            Note.Text = S("Ядро не на связи.");
            return;
        }

        var save = new Microsoft.Win32.SaveFileDialog
        {
            FileName = S("Что Рина знает обо мне"),
            DefaultExt = ".txt",
            Filter = S("Читаемый текст (*.txt)|*.txt|Данные (*.json)|*.json"),
        };
        if (save.ShowDialog() != true) return;

        var asText = !save.FileName.EndsWith(".json",
                                             StringComparison.OrdinalIgnoreCase);
        try
        {
            System.IO.File.WriteAllText(
                save.FileName,
                asText ? Readable(told) : told.ToJsonString(new()
                {
                    WriteIndented = true,
                    Encoder = System.Text.Encodings.Web.JavaScriptEncoder
                        .UnsafeRelaxedJsonEscaping,
                }),
                System.Text.Encoding.UTF8);
            Note.Text = S("Сохранено: {0}", save.FileName);
        }
        catch (Exception why)
        {
            // Named, not swallowed. "Could not save" sends a person
            // looking; "the folder is read-only" tells them where to look.
            Note.Text = S("Не сохранилось: {0}", why.Message);
        }
    }

    /// <summary>
    /// The whole inventory as something a person can read.
    /// </summary>
    /// <remarks>
    /// Rendered here rather than in the core because it needs the group
    /// names, and those belong to the shell (ADR 0006). Which is also why
    /// a group the shell does not know keeps its identifier here too — the
    /// same rule as on the screen, and for the same reason: a file that
    /// claims to hold everything must not quietly hold less.
    /// </remarks>
    public static string Readable(JsonObject told)
    {
        var out_ = new System.Text.StringBuilder();
        out_.AppendLine(S("Что Рина знает обо мне"));

        var at = Number(told["exported_at"]);
        out_.AppendLine(S("Выгружено: {0} · версия {1}",
            at > 0 ? DateTimeOffset.FromUnixTimeSeconds((long)at)
                        .LocalDateTime.ToString("dd.MM.yyyy HH:mm")
                   : "—",
            told["app_version"]?.GetValue<string>() ?? "—"));
        out_.AppendLine(S("Всё это хранилось на этом компьютере."));

        foreach (var group in (told["payload"]?["groups"] as JsonArray ?? [])
                     .OfType<JsonObject>())
        {
            var id = group["id"]?.GetValue<string>() ?? "";
            var count = (int)Number(group["count"]);
            var (title, note) = Named(id);

            out_.AppendLine();
            out_.AppendLine($"{title.ToUpperInvariant()} ({count})");
            out_.AppendLine(note);
            if (count == 0)
            {
                out_.AppendLine(S("  — пусто"));
                continue;
            }

            foreach (var item in (group["items"] as JsonArray ?? [])
                         .OfType<JsonObject>())
            {
                var aside = string.Join(" · ", new[]
                {
                    item["detail"]?.GetValue<string>() ?? "",
                    item["where"]?.GetValue<string>() ?? "",
                }.Where(part => part.Length > 0));
                var when = Number(item["when"]);
                var stamp = when > 0
                    ? DateTimeOffset.FromUnixTimeSeconds((long)when)
                        .LocalDateTime.ToString("dd.MM.yyyy HH:mm") + "  "
                    : "";
                out_.Append("  • ").Append(stamp)
                    .Append(item["what"]?.GetValue<string>() ?? "");
                if (aside.Length > 0) out_.Append("  (").Append(aside).Append(')');
                out_.AppendLine();
            }
        }
        return out_.ToString();
    }

    /// <summary>Forget one group from outside — for the check.</summary>
    public Task ForgetGroupForCheck(string group) => ForgetAsync(group, null);

    /// <summary>Forget one entry from outside — for the check.</summary>
    public Task ForgetEntryForCheck(string group, string id) =>
        ForgetAsync(group, [id]);

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
