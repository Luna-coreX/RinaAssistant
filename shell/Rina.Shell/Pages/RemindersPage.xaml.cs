using System.Collections.ObjectModel;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>Запланированное, как его видит человек.</summary>
public sealed record Planned(string Id, string Kind, string Text, string When);

/// <summary>
/// Напоминания: что запланировано и как это снять.
/// </summary>
/// <remarks>
/// Список приходит от ядра, и сработавшее тоже: планировщик живёт там
/// (<c>4.0-E05</c>), а страница лишь показывает. Поэтому она подписана на
/// <c>reminder.fired</c> — иначе сработавший таймер остался бы в списке до
/// следующего захода в раздел, и человек увидел бы неправду.
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
        // Сработало — значит в списке его больше нет.
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
    /// Показать пустое состояние вместо списка или убрать его.
    /// </summary>
    /// <remarks>
    /// Они делят одно место, а не соседствуют: список и объяснение, почему
    /// список пуст, одновременно не бывают верны.
    /// </remarks>
    private void Show(FrameworkElement? nothing)
    {
        Empty.Content = nothing;
        Empty.Visibility = nothing is null ? Visibility.Collapsed
                                           : Visibility.Visible;
        List.Visibility = nothing is null ? Visibility.Visible
                                          : Visibility.Collapsed;
    }

    /// <summary>Готовые отсрочки: минуты от «сейчас».</summary>
    /// <remarks>
    /// Список короткий нарочно. Напоминание «через сколько-то» человек
    /// ставит на бегу, и выбор из пяти строк быстрее, чем поле, куда надо
    /// вписать число и выбрать единицу.
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
    /// Завести напоминание.
    /// </summary>
    /// <remarks>
    /// Время уходит в ядро **меткой**, а не словами: у окна есть часы, и
    /// составлять фразу «напомни через пятнадцать минут» ради того, чтобы
    /// ядро разобрало её обратно, значило бы проверять разбор вместо
    /// намерения. Разбор остаётся там, где он нужен, — в голосе.
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
            // «19:30» — сегодня, а если время уже прошло, то завтра:
            // человек, ставящий напоминание на утро вечером, имеет в виду
            // завтрашнее утро, а не прошедшее.
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

    /// <summary>Сколько напоминаний показано — для сквозной проверки.</summary>
    public int PlannedCount => _items.Count;

    /// <summary>
    /// Завести напоминание снаружи — для сквозной проверки.
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
    /// Сколько осталось.
    /// </summary>
    /// <remarks>
    /// Показания прибора не должны дёргаться при смене значения, поэтому
    /// цифры моноширинные (§3), а формат — постоянной ширины: «09:59» и
    /// «10:00» занимают одинаковое место.
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
