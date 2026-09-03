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
            Empty.Text = S("Ядро не на связи — список недоступен.");
            Empty.Visibility = Visibility.Visible;
            return;
        }

        _link.CoreEvent += OnCoreEvent;
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
        Empty.Visibility = _items.Count == 0 ? Visibility.Visible
                                             : Visibility.Collapsed;
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
