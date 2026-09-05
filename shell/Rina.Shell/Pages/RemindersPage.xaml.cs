using System.Collections.ObjectModel;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>Something planned, as a person sees it.</summary>
public sealed record Planned(string Id, string Kind, string Text, string When);

/// <summary>
/// Reminders: what is planned and how to take it off.
/// </summary>
/// <remarks>
/// The list comes from the core, and so does what has fired: the scheduler
/// lives there (<c>4.0-E05</c>), and the page only shows things. That is
/// why it subscribes to <c>reminder.fired</c> — otherwise a timer that had
/// gone off would stay in the list until the next visit to the section,
/// and the person would be shown an untruth.
/// </remarks>
public partial class RemindersPage : UserControl
{
    private readonly CoreLink? _link;
    private readonly ObservableCollection<Planned> _items = [];

    public RemindersPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;
        Items.ItemsSource = _items;

        if (_link is null)
        {
            Show(EmptyState.For(S("Ядро не на связи"),
                            S("Список напоминаний живёт в ядре, а связи с ним сейчас нет.")));
            return;
        }

        _link.CoreEvent += OnCoreEvent;
        FillDelays();
        Loaded += async (_, _) => await ReloadAsync();
    }

    private void OnCoreEvent(Envelope message)
    {
        // It fired — so it is no longer in the list.
        if (message.Method is Events.ReminderFired) _ = ReloadAsync();
    }

    private async Task ReloadAsync()
    {
        var told = await Ask(Methods.RemindersList);
        _items.Clear();
        if (told?["items"] is JsonArray items)
        {
            foreach (var item in items)
            {
                var kind = item?["kind"]?.GetValue<string>() ?? "";
                _items.Add(new Planned(
                    item?["id"]?.GetValue<string>() ?? "",
                    kind switch
                    {
                        "timer" => S("Таймер"),
                        "alarm" => S("Будильник"),
                        _ => S("Напоминание"),
                    },
                    item?["text"]?.GetValue<string>() ?? "",
                    Until(item?["fire_at"]?.GetValue<double>() ?? 0)));
            }
        }

        Legend.Text = S("ЗАПЛАНИРОВАНО · {0}", _items.Count);
        if (_items.Count == 0)
            Show(EmptyState.For(
                S("Пока ни одного напоминания"),
                S("Здесь окажется всё, о чём вы попросите напомнить — полем выше или голосом."),
                S("«напомни через 15 минут выключить духовку»")));
        else Show(null);
    }

    /// <summary>
    /// Show the empty state instead of the list, or take it away.
    /// </summary>
    /// <remarks>
    /// They share one place rather than sitting side by side: a list and an
    /// explanation of why the list is empty are never both true at once.
    /// </remarks>
    private void Show(FrameworkElement? nothing)
    {
        Empty.Content = nothing;
        Empty.Visibility = nothing is null ? Visibility.Collapsed
                                           : Visibility.Visible;
        List.Visibility = nothing is null ? Visibility.Visible
                                          : Visibility.Collapsed;
    }

    /// <summary>Ready-made delays: minutes from "now".</summary>
    /// <remarks>
    /// The list is short on purpose. A "in so many minutes" reminder is set
    /// on the run, and picking one of five lines is faster than a field
    /// where a number has to be typed and a unit chosen.
    /// </remarks>
    private static readonly (int Minutes, string Title)[] Delays =
    [
        (5, Word("через 5 минут")),
        (15, Word("через 15 минут")),
        (30, Word("через 30 минут")),
        (60, Word("через час")),
        (180, Word("через 3 часа")),
        (1440, Word("завтра в это же время")),
    ];

    private void FillDelays()
    {
        foreach (var (minutes, title) in Delays)
            When.Items.Add(new ComboBoxItem
            {
                Content = S(title),
                Tag = minutes,
            });
        When.SelectedIndex = 1;
    }

    /// <summary>
    /// Set up a reminder.
    /// </summary>
    /// <remarks>
    /// The time goes to the core as a **stamp**, not as words: the window
    /// has a clock, and composing the phrase "remind me in fifteen minutes"
    /// just so the core could parse it back would mean testing the parser
    /// instead of the intent. Parsing stays where it is needed — in the
    /// voice.
    /// </remarks>
    private async void OnCreate(object sender, RoutedEventArgs e)
    {
        var text = What.Text.Trim();
        if (text.Length == 0)
        {
            Note.Text = S("О чём напомнить?");
            return;
        }

        var when = DateTime.Now;
        var typed = AtTime.Text.Trim();
        if (typed.Length > 0)
        {
            // "19:30" means today, and tomorrow if the time has already
            // passed: a person setting an evening reminder for the morning
            // means tomorrow morning, not the one gone by.
            if (!TimeSpan.TryParse(typed, out var at))
            {
                Note.Text = S("Время пишется как 19:30.");
                return;
            }
            when = DateTime.Today + at;
            if (when <= DateTime.Now) when = when.AddDays(1);
        }
        else
        {
            var minutes = (When.SelectedItem as ComboBoxItem)?.Tag as int? ?? 15;
            when = when.AddMinutes(minutes);
        }

        var answer = await Ask(Methods.RemindersCreate, new JsonObject
        {
            ["text"] = text,
            ["fire_at"] = new DateTimeOffset(when).ToUnixTimeMilliseconds()
                          / 1000.0,
        });
        if (answer is null) return;

        What.Clear();
        AtTime.Clear();
        Note.Text = S("Напомню {0}", when.ToString("dd.MM HH:mm"));
        await ReloadAsync();
    }

    /// <summary>How many reminders are shown — for the end-to-end check.</summary>
    public int PlannedCount => _items.Count;

    /// <summary>
    /// Set up a reminder from outside — for the end-to-end check.
    /// </summary>
    public async Task<bool> CreateAsync(string text, int minutes)
    {
        What.Text = text;
        AtTime.Text = "";
        When.SelectedItem = When.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (int?)item.Tag == minutes)
            ?? When.SelectedItem;
        OnCreate(this, new RoutedEventArgs());
        for (var i = 0; i < 50 && What.Text.Length > 0; i++)
            await Task.Delay(100);
        return What.Text.Length == 0;
    }

    /// <summary>
    /// How much is left.
    /// </summary>
    /// <remarks>
    /// An instrument reading must not twitch when the value changes, so the
    /// digits are monospaced (§3) and the format is of constant width:
    /// "09:59" and "10:00" take up the same room.
    /// </remarks>
    private static string Until(double fireAt)
    {
        var left = DateTimeOffset.FromUnixTimeMilliseconds((long)(fireAt * 1000))
                   - DateTimeOffset.UtcNow;
        if (left < TimeSpan.Zero) return S("сейчас");
        return left.TotalHours >= 1
            ? $"{(int)left.TotalHours:00}:{left.Minutes:00}:{left.Seconds:00}"
            : $"{left.Minutes:00}:{left.Seconds:00}";
    }

    private async void OnCancel(object sender, RoutedEventArgs e)
    {
        if ((sender as Button)?.Tag is not string id) return;
        await Ask(Methods.RemindersCancel, new JsonObject { ["id"] = id });
        await ReloadAsync();
    }

    private async Task<JsonObject?> Ask(string method, JsonObject? payload = null)
    {
        if (_link?.Connection is not { Ready: true } connection) return null;
        try
        {
            var answer = await connection.CallAsync(method, payload,
                                                    TimeSpan.FromSeconds(20));
            return answer.IsError ? null : answer.Payload;
        }
        catch { return null; }
    }
}
