using System.Collections.ObjectModel;
using System.Linq;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// Working sessions: what is going on now, and what went on before
/// (<c>4.0b-A02</c>, <c>4.0b-A05</c>).
/// </summary>
/// <remarks>
/// <para>
/// <b>The open one stands above the list rather than first in it.</b> It is
/// a different thing from the rest: it has no end, its length grows while
/// you look at it, and it is the only one anything can be done to. As the
/// first row it read as the newest of the finished ones, and the button to
/// close it sat in a column where every other row had nothing.
/// </para>
/// <para>
/// <b>The page shows and closes; it does not start.</b> A session is opened
/// by saying what it is for, and a field here with a button beside it would
/// be a second way in that has to be kept in step with the first. Closing
/// is here because it is the one thing a person wants when they have
/// already stopped working and are looking at the window.
/// </para>
/// <para>
/// <b>What is written down depends on two switches, and the page says so
/// when they are off.</b> A row that shows only a name and a length, with
/// no explanation, reads as a session that recorded nothing because nothing
/// happened — rather than as one that was not allowed to look.
/// </para>
/// </remarks>
public partial class SessionsPage : UserControl
{
    private readonly CoreLink? _link;
    private readonly ObservableCollection<Past> _items = [];

    /// <summary>One finished session, as a row.</summary>
    private sealed record Past(string Goal, string Detail, string Spent);

    public SessionsPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;
        Items.ItemsSource = _items;

        if (_link is null)
        {
            Show(EmptyState.For(S("Ядро не на связи"),
                 S("Сессии живут в ядре, а связи с ним сейчас нет.")));
            return;
        }

        Loaded += async (_, _) => await ReloadAsync();
    }

    /// <summary>How many past sessions are shown — for the check.</summary>
    public int Shown => _items.Count;

    /// <summary>Is a session open, by what the page shows — for the check.</summary>
    public bool ShowsOpen => Open.Visibility == Visibility.Visible;

    /// <summary>Is this goal on the page right now — for the check.</summary>
    /// <remarks>
    /// By text rather than by count: a count races the first load and is a
    /// hostage to whatever an earlier run left in the store.
    /// </remarks>
    public bool ShowsForCheck(string goal) =>
        OpenGoal.Text.Contains(goal, StringComparison.Ordinal)
        || _items.Any(one => one.Goal.Contains(goal, StringComparison.Ordinal));

    private async Task ReloadAsync()
    {
        var told = await Ask(Methods.SessionsList);
        _items.Clear();
        JsonNode? open = null;
        var past = new List<JsonNode>();

        if (told?["items"] is JsonArray items)
        {
            foreach (var item in items)
            {
                if (item is null) continue;
                var finished = item["finished"]?.GetValue<double>() ?? 0;
                if (finished <= 0) open = item; else past.Add(item);
            }
        }

        // Newest first. The store keeps them in the order they were
        // opened, which is the right order to write and the wrong one to
        // read: what somebody wants is yesterday, not the first day they
        // ever used the thing.
        past.Sort((a, b) => (b["finished"]?.GetValue<double>() ?? 0)
                  .CompareTo(a["finished"]?.GetValue<double>() ?? 0));
        foreach (var one in past)
            _items.Add(new Past(
                one["goal"]?.GetValue<string>() ?? "",
                Detail(one),
                Spell(one["spent"]?.GetValue<double>() ?? 0)));

        ShowOpen(open);
        Legend.Visibility = _items.Count > 0 ? Visibility.Visible
                                             : Visibility.Collapsed;
        if (_items.Count > 0)
            Legend.Text = S("ПРОШЛЫЕ · {0}", _items.Count);

        Show(_items.Count > 0 || open is not null ? null : EmptyState.For(
            S("Пока ни одной сессии"),
            S("Сессия — это отрезок работы с названием. Начните голосом или строкой, и здесь останется, сколько он шёл и что в нём было."),
            S("«начни сессию над отчётом»")));
    }

    private void ShowOpen(JsonNode? open)
    {
        Open.Visibility = open is null ? Visibility.Collapsed
                                       : Visibility.Visible;
        CloseRow.Visibility = Open.Visibility;
        if (open is null) return;

        OpenGoal.Text = open["goal"]?.GetValue<string>() ?? "";
        OpenDetail.Text = Detail(open);
        OpenSpent.Text = Spell(open["spent"]?.GetValue<double>() ?? 0);
        OpenFocus.Visibility = (open["focus"]?.GetValue<bool>() ?? false)
            ? Visibility.Visible : Visibility.Collapsed;
    }

    /// <summary>What the session collected, in one line.</summary>
    /// <remarks>
    /// Empty parts are left out rather than said as "notes: none". A list
    /// of absences is longer than the thing itself and tells a person
    /// nothing they did not know.
    /// </remarks>
    private static string Detail(JsonNode one)
    {
        var parts = new List<string>();
        if (one["notes"] is JsonArray notes && notes.Count > 0)
            parts.Add(S("заметок {0}", notes.Count));
        if (one["commands"] is JsonArray done && done.Count > 0)
            parts.Add(S("команд {0}", done.Count));
        if (one["apps"] is JsonObject apps && apps.Count > 0)
            parts.Add(S("программ {0}", apps.Count));
        if (one["folders"] is JsonArray where && where.Count > 0)
            parts.Add(string.Join(", ",
                where.Select(f => f?.GetValue<string>() ?? "")));
        return parts.Count > 0 ? string.Join(" · ", parts)
                               : S("ничего не записано");
    }

    /// <summary>A stretch of time, as a person would say it.</summary>
    private static string Spell(double seconds)
    {
        var whole = (int)Math.Max(0, seconds);
        var hours = whole / 3600;
        var minutes = whole % 3600 / 60;
        if (hours > 0 && minutes > 0) return S("{0} ч {1} мин", hours, minutes);
        if (hours > 0) return S("{0} ч", hours);
        if (minutes > 0) return S("{0} мин", minutes);
        return S("меньше минуты");
    }

    private async void OnFinish(object sender, RoutedEventArgs e)
    {
        await Ask(Methods.SessionsFinish,
                  new JsonObject { ["note"] = Note.Text.Trim() });
        Note.Text = "";
        await ReloadAsync();
    }

    /// <summary>
    /// Show the empty state instead of the list, or take it away.
    /// </summary>
    private void Show(FrameworkElement? nothing)
    {
        Empty.Content = nothing;
        Empty.Visibility = nothing is null ? Visibility.Collapsed
                                           : Visibility.Visible;
        List.Visibility = nothing is null ? Visibility.Visible
                                          : Visibility.Collapsed;
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
