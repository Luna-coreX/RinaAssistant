using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Linq;
using System.Windows.Controls;
using System.Windows.Input;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>One line on the glass.</summary>
/// <param name="Mine">Said by the person, rather than by Rina.</param>
/// <param name="Said">What was said.</param>
/// <param name="When">The time, as a person reads it.</param>
/// <param name="Pending">Rina is still working on this one.</param>
/// <param name="Failed">It went wrong, and the line says so.</param>
/// <remarks>
/// <para>
/// Who and when used to be one field: a name for Rina, a time for the
/// person. It read as a list because that is what it was — the same column
/// held two different things, so neither could be shown properly. A
/// conversation has two sides, and a message has a time <b>and</b> an
/// author, not one or the other.
/// </para>
/// <para>
/// The two states are here rather than in a second list: what is pending
/// becomes an ordinary message when the answer arrives, and a state kept
/// alongside would have to be married back to it.
/// </para>
/// </remarks>
public sealed record Turn(bool Mine, string Said, string When,
                          bool Pending = false, bool Failed = false);

/// <summary>
/// Dialogue: the main screen. The conversation, the input line, two modes.
/// </summary>
/// <remarks>
/// <para>
/// <b>The page knows nothing about the window.</b> It is handed a link and
/// works with the core itself; the window only decides which page to show.
/// This is a condition of <c>4.0-F03</c>, and it is easy to break — one
/// reach up to the parent for some small thing is enough.
/// </para>
/// <para>
/// <b>The answer arrives as an event, not as a reply to a request.</b> To
/// <c>command.handle</c> the core answers "accepted"; the answer itself
/// turns up as an <c>assistant.response</c> event, when it turns up. That
/// is why the input line is cleared at once, and what the person said
/// appears on the glass first.
/// </para>
/// </remarks>
public partial class DialoguePage : UserControl
{
    private readonly CoreLink? _link;
    private readonly ObservableCollection<Turn> _turns = [];

    public DialoguePage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;
        Turns.ItemsSource = _turns;

        if (_link is null)
        {
            // Not as a line: text in the conversation feed reads as
            // something Rina said, and this is the window talking about itself.
            Empty.Content = EmptyState.For(
                S("Ядро не на связи"),
                S("Разговор ведёт ядро, а связи с ним сейчас нет. Оболочка пробует поднять его заново."),
                onGlass: true);
            Empty.Visibility = Visibility.Visible;
            return;
        }

        _link.CoreEvent += OnCoreEvent;
        Loaded += async (_, _) => await LoadAsync();
    }

    /// <summary>Show the conversation that has already happened.</summary>
    private async Task LoadAsync()
    {
        var told = await Ask(Methods.HistoryList,
                             new JsonObject { ["limit"] = 200 });
        if (told?["items"] is not JsonArray items) return;

        _turns.Clear();
        foreach (var item in items)
        {
            var kind = item?["kind"]?.GetValue<string>() ?? "";
            var text = item?["text"]?.GetValue<string>() ?? "";
            var stamp = item?["ts"]?.GetValue<double>() ?? 0;
            _turns.Add(new Turn(kind != "assistant", text, Clock(stamp)));
        }
        ShowEmpty();
        ScrollToEnd();

        var values = await Ask(Methods.SettingsGet, new JsonObject
        {
            ["keys"] = new JsonArray("voice_reply", "always_listen"),
        });
        VoiceReply.IsChecked = values?["values"]?["voice_reply"]?
            .GetValue<bool>() ?? false;
        AlwaysListen.IsChecked = values?["values"]?["always_listen"]?
            .GetValue<bool>() ?? false;
    }

    private static string Clock(double unix) =>
        DateTimeOffset.FromUnixTimeMilliseconds((long)(unix * 1000))
            .ToLocalTime().ToString("HH:mm");

    private void OnCoreEvent(Envelope message)
    {
        switch (message.Method)
        {
            case Events.SpeechRecognized:
                Add(true, message.Payload["text"]?.GetValue<string>() ?? "",
                    Clock(message.Timestamp));
                break;
            case Events.AssistantResponse:
                Add(false, message.Payload["text"]?.GetValue<string>() ?? "",
                    Clock(message.Timestamp));
                break;
            case Events.AssistantError:
                Add(false, message.Payload["text"]?.GetValue<string>() ?? "",
                    Clock(message.Timestamp), failed: true);
                break;
            case Events.AssistantThinking:
                // A long answer says it is coming. Silence and thinking look
                // the same from outside, and the difference is a minute of
                // a person wondering whether they were heard.
                if (message.Payload["active"]?.GetValue<bool>() == true)
                    ShowPending();
                else
                    DropPending();
                break;
        }
    }

    private void Add(bool mine, string said, string when,
                     bool failed = false)
    {
        if (said.Length == 0) return;
        // Rina's answer replaces the "thinking" line rather than landing
        // under it: they are the same message at two moments of its life.
        if (!mine) DropPending();
        _turns.Add(new Turn(mine, said, when, Failed: failed));
        ShowEmpty();
        ScrollToEnd();
    }

    /// <summary>Rina is working on an answer.</summary>
    private void ShowPending()
    {
        if (_turns.Any(turn => turn.Pending)) return;
        _turns.Add(new Turn(false, S("Думаю…"), Clock(Now()), Pending: true));
        ShowEmpty();
        ScrollToEnd();
    }

    private void DropPending()
    {
        for (var at = _turns.Count - 1; at >= 0; at--)
            if (_turns[at].Pending) _turns.RemoveAt(at);
    }

    private static double Now() =>
        DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;

    /// <summary>How many messages are on the glass — for the check.</summary>
    public int Messages => _turns.Count;

    /// <summary>The last few messages, for a check that failed.</summary>
    public string TailForCheck(int count) =>
        string.Join(" | ", _turns.TakeLast(count)
            // Latin, because this line is read by whoever is looking at a
            // failed check and never by a person using Rina. Russian here
            // is indistinguishable, to `check_strings.py`, from a label
            // that forgot to go through the translation — and it is right
            // not to be able to tell.
            .Select(turn => (turn.Mine ? "me:" : "her:")
                            + turn.Said[..Math.Min(24, turn.Said.Length)]));

    /// <summary>Which side a message carrying this text sits on.</summary>
    /// <remarks>
    /// By its text, not by its place in the list. Two different lines build
    /// these messages — one as they arrive, one when the history is read
    /// back — and counting sides let each of them cover for the other:
    /// forcing everything the first built onto one side left the check
    /// green, because the second still laid the history out correctly.
    ///
    /// `null` means no such message.
    /// </remarks>
    public bool? SideOf(string fragment)
    {
        var found = _turns.LastOrDefault(
            turn => turn.Said.Contains(fragment, StringComparison.Ordinal));
        return found?.Mine;
    }

    /// <summary>Does every message carry a time — for the check.</summary>
    public bool AllStamped => _turns.All(turn => turn.When.Length > 0);

    /// <summary>Say something, as if typed — for the check.</summary>
    /// <remarks>
    /// Through the same path the send button uses. Adding the message to
    /// the list directly would check that a list can hold two things.
    /// </remarks>
    public async Task SayForCheck(string text)
    {
        Input.Text = text;
        await SendAsync();
    }

    /// <summary>Is a "thinking" line showing — for the check.</summary>
    public bool Thinking => _turns.Any(turn => turn.Pending);

    /// <summary>
    /// Explain the empty glass.
    /// </summary>
    /// <remarks>
    /// A conversation that has not happened yet is neither a breakage nor
    /// "loading". Empty glass without an explanation reads as exactly that,
    /// especially on the first run, when the person does not yet know they
    /// can write here.
    /// </remarks>
    private void ShowEmpty()
    {
        var nothing = _turns.Count == 0;
        Empty.Content = nothing
            ? EmptyState.For(
                S("Разговор пуст"),
                S("Скажите вслух или напишите ниже. Всё сказанное окажется здесь и переживёт перезапуск."),
                S("«который час» · «запусти браузер» · «посчитай 15 * 12»"),
                onGlass: true)
            : null;
        Empty.Visibility = nothing ? Visibility.Visible : Visibility.Collapsed;
    }

    private void ScrollToEnd() => Dispatcher.BeginInvoke(
        new Action(() => Scroll.ScrollToEnd()),
        System.Windows.Threading.DispatcherPriority.Loaded);

    private async void OnSend(object sender, RoutedEventArgs e) => await SendAsync();

    private async void OnInputKey(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Enter) await SendAsync();
    }

    private async Task SendAsync()
    {
        var text = Input.Text.Trim();
        if (text.Length == 0) return;

        // What was said appears on the glass at once, without waiting for
        // the core: a person has to see they were heard, not guess whether
        // it got through.
        Add(true, text, Clock(Now()));
        Input.Clear();

        await Ask(Methods.CommandHandle, new JsonObject
        {
            ["text"] = text,
            ["source"] = "typed",
        });
    }

    private async void OnVoiceReply(object sender, RoutedEventArgs e) =>
        await Ask(Methods.SettingsSet, new JsonObject
        {
            ["values"] = new JsonObject
            {
                ["voice_reply"] = VoiceReply.IsChecked == true,
            },
        });

    private async void OnAlwaysListen(object sender, RoutedEventArgs e) =>
        await Ask(Methods.SpeechSetAlwaysListen, new JsonObject
        {
            ["enabled"] = AlwaysListen.IsChecked == true,
        });

    private async void OnClear(object sender, RoutedEventArgs e)
    {
        await Ask(Methods.HistoryClear);
        _turns.Clear();
    }

    private async void OnExport(object sender, RoutedEventArgs e)
    {
        // The shell picks the file and writes it: the save dialogue is its
        // job, and the core hands over the content (§6 of the spec).
        // The whole contents of the file, together with its kind and
        // format version: a history file must be distinguishable from a
        // command file, or the first import into the wrong place will
        // parse it as its own.
        var told = await Ask(Methods.HistoryExport);
        if (told is null) return;

        var path = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            $"rina-history-{DateTime.Now:yyyy-MM-dd-HHmm}.json");
        await File.WriteAllTextAsync(path, told.ToJsonString(
            new System.Text.Json.JsonSerializerOptions { WriteIndented = true }));
        Add(false, S("Разговор выгружен: {0}", path), Clock(Now()));
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
