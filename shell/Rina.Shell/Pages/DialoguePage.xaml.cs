using System.Collections.ObjectModel;
using System.IO;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>Одна реплика на стекле.</summary>
/// <param name="Who">Время для человека, имя для Рины.</param>
/// <param name="Said">Что сказано.</param>
public sealed record Turn(string Who, string Said);

/// <summary>
/// Диалог: главный экран. Разговор, строка ввода, два режима.
/// </summary>
/// <remarks>
/// <para>
/// <b>Страница ничего не знает про окно.</b> Она получает связь и работает
/// с ядром сама; окно только решает, какую страницу показать. Это условие
/// <c>4.0-F03</c>, и нарушить его легко — достаточно один раз дотянуться до
/// родителя за чем-нибудь мелким.
/// </para>
/// <para>
/// <b>Ответ приходит событием, а не ответом на запрос.</b> На
/// <c>command.handle</c> ядро отвечает «принято»; сам ответ появляется
/// событием <c>assistant.response</c>, когда появится. Поэтому строка ввода
/// очищается сразу, а на стекле сначала возникает сказанное человеком.
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
            // Не репликой: строка в ленте разговора читается как сказанное
            // Риной, а это говорит окно о самом себе.
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

    /// <summary>Показать разговор, который уже был.</summary>
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
            _turns.Add(new Turn(kind == "assistant" ? S("Рина") : When(stamp), text));
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

    private static string When(double unix) =>
        DateTimeOffset.FromUnixTimeMilliseconds((long)(unix * 1000))
            .ToLocalTime().ToString("HH:mm");

    private void OnCoreEvent(Envelope message)
    {
        switch (message.Method)
        {
            case Events.SpeechRecognized:
                Add(When(message.Timestamp),
                    message.Payload["text"]?.GetValue<string>() ?? "");
                break;
            case Events.AssistantResponse:
            case Events.AssistantError:
                Add(S("Рина"), message.Payload["text"]?.GetValue<string>() ?? "");
                break;
        }
    }

    private void Add(string who, string said)
    {
        if (said.Length == 0) return;
        _turns.Add(new Turn(who, said));
        ShowEmpty();
        ScrollToEnd();
    }

    /// <summary>
    /// Объяснить пустое стекло.
    /// </summary>
    /// <remarks>
    /// Разговор, которого ещё не было, — не поломка и не «загружается».
    /// Пустое стекло без объяснения читается именно так, особенно на первом
    /// запуске, когда человек ещё не знает, что сюда можно писать.
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

        // Сказанное появляется на стекле сразу, не дожидаясь ядра: человек
        // должен видеть, что его услышали, а не гадать, дошло ли.
        Add(When(Clock.Now()), text);
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
        // Файл выбирает и пишет оболочка: диалог выбора места — её работа,
        // а ядро отдаёт содержимое (§6 спецификации).
        var told = await Ask(Methods.HistoryExport);
        if (told?["items"] is not JsonArray items) return;

        var path = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            $"rina-history-{DateTime.Now:yyyy-MM-dd-HHmm}.json");
        await File.WriteAllTextAsync(path, items.ToJsonString());
        Add("", S("Разговор выгружен: {0}", path));
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
