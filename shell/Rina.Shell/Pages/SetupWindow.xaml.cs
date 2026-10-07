using System.Text.Json.Nodes;
using System.Windows;
using System.Linq;
using System.Windows.Controls;
using Rina.Protocol;
using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// The first run: a few questions, then the models.
/// </summary>
/// <remarks>
/// <para>
/// Plan item <c>4.0b-A14</c>. What it asks is deliberately short. A wizard
/// is a bill presented before anything has been given, and every question
/// in it is one a person answers without yet knowing what it changes — so
/// only the ones that make the difference between working and not are here.
/// Everything else is in the settings, where it can be answered by somebody
/// who has seen the program work.
/// </para>
/// <para>
/// <b>The steps are the shell's, the values are the core's.</b> Nothing new
/// is invented for storage: the wake word and the engines are ordinary
/// settings, written through <c>settings.set</c>. Only two questions belong
/// to the core alone — whether this is a first run, and which models can be
/// had — and both have their own methods, because neither is a setting.
/// </para>
/// </remarks>
public partial class SetupWindow : Window
{
    private readonly CoreLink _link;
    private readonly List<Step> _steps = [];
    private int _at;

    /// <summary>One step: a heading, a body, and what to keep from it.</summary>
    private sealed record Step(string Title, string Note,
                               Func<FrameworkElement> Build,
                               Func<Task>? Keep = null);

    public SetupWindow(CoreLink link)
    {
        InitializeComponent();
        // It arrives rather than being simply there (`4.0b-E04`).
        Arrival.Animate(this);
        _link = link;
        _steps.Add(new Step(
            S("Здравствуйте"),
            S("Рина — голосовой помощник на этом компьютере. Несколько вопросов, и всё."),
            BuildGreeting));
        // Asked because the plan says so (`4.0b-E14`), though it is not
        // a question of working or not: the persona names the person, and
        // the name has to come from somewhere other than its text. Empty is
        // an answer — pressing «Дальше» on a blank field is how somebody
        // declines, and nothing asks twice.
        NameStep = _steps.Count;
        _steps.Add(new Step(
            S("Как к вам обращаться"),
            S("Рина будет называть вас этим именем. Можно оставить пустым."),
            BuildName, KeepName));
        // «Как вас звать» until the step above arrived: it meant what to
        // call her, and read as "what is your name". Next to a step that
        // really asks that, the two would have said the same words about
        // opposite things.
        _steps.Add(new Step(
            S("Как её позвать"),
            S("По этому слову Рина понимает, что обращаются к ней."),
            BuildWake, KeepWake));
        ModelsStep = _steps.Count;
        _steps.Add(new Step(
            S("Что доустановить"),
            S("И слух, и голос работают по пакету и модели — их размер в установщик не помещается."),
            BuildModels));
        // Whether to keep the conversation (decided 2026-10-07, after the
        // audit's I-2). It used to be kept by default, without a word: the
        // most personal thing the program stores, on because nobody said
        // otherwise. Asked here, unticked, like the telemetry below.
        HistoryStep = _steps.Count;
        _steps.Add(new Step(
            S("Помнить разговор"),
            S("История — что вы сказали и что ответила Рина. Хранится только на этом компьютере."),
            BuildHistory, KeepHistory));
        // The beta's telemetry (`4.0b-D05`): asked here because a switch
        // nobody is told about is a switch nobody turns on, and unticked
        // because it is off until a person says otherwise. What leaves and
        // what never does is on the step itself, not behind a link.
        TelemetryStep = _steps.Count;
        _steps.Add(new Step(
            S("Помочь бете"),
            S("Бета нужна, чтобы узнать, чем пользуются и где что-то не получается. Помочь можно, а можно и нет."),
            BuildTelemetry, KeepTelemetry));
        _steps.Add(new Step(
            S("Готово"),
            S("Выбранное скачается в фоне. Пользоваться можно уже сейчас."),
            BuildDone, KeepAll));
        Show(0);
    }

    /// <summary>Which step has the models on it.</summary>
    /// <remarks>
    /// Counted as the steps are laid out rather than written as a number.
    /// It was a literal `2` in three places here and two in the check, and
    /// the name step moved it: a literal would have read the greeting's
    /// contents as "the ticked models" without a word.
    /// </remarks>
    public int ModelsStep { get; }

    /// <summary>How many models the catalogue offered — for the check.</summary>
    public int Offered => _models.Count;

    /// <summary>How many boxes are ticked on the step shown — for the check.</summary>
    public int TickedNow => TickedIds.Count;

    /// <summary>Which boxes are ticked on the step shown — for the check.</summary>
    /// <remarks>
    /// The names, not the count. A count can only be compared with a
    /// number somebody chose, and the number depends on what this
    /// machine happens to have installed already: the check that asked
    /// "is something ticked" went red the day the developer downloaded
    /// the very model it is about. The rule has nothing to do with how
    /// many — it is that the wizard ticks the catalogue's own choices and
    /// nothing else.
    /// </remarks>
    public IReadOnlyList<string> TickedIds =>
        Stage.Content is DependencyObject root
            ? Boxes(root).Where(b => b.IsChecked == true)
                  .Select(b => b.Tag as string ?? "").ToList()
            : [];

    /// <summary>What the catalogue marks as wanted and not yet here — for the check.</summary>
    public IReadOnlyList<string> WorthTicking =>
        _models.Where(m => (m["wanted"]?.GetValue<bool>() ?? false)
                           && !(m["installed"]?.GetValue<bool>() ?? false))
               .Select(m => m["id"]?.GetValue<string>() ?? "").ToList();

    /// <summary>What the catalogue marks as wanted at all — for the check.</summary>
    public IReadOnlyList<string> Wanted =>
        _models.Where(m => m["wanted"]?.GetValue<bool>() ?? false)
               .Select(m => m["id"]?.GetValue<string>() ?? "").ToList();

    /// <summary>How many boxes the step shown has, ticked or not — for the check.</summary>
    public int BoxesShown =>
        Stage.Content is DependencyObject root ? Boxes(root).Count() : 0;

    /// <summary>Is there anything on the step at all — for the check.</summary>
    public bool StageFilled => Stage.Content is FrameworkElement;

    /// <summary>Open a given step — for the check and for screenshots.</summary>
    public void ShowFor(int at) => Show(at);

    /// <summary>Which models the person left ticked.</summary>
    public IReadOnlyList<string> Chosen => _chosen;

    private readonly List<string> _chosen = [];
    private readonly List<JsonObject> _models = [];
    private TextBox? _name;
    private ComboBox? _form;
    private TextBox? _wake;

    // What is stored, read once by `LoadAsync`, and what the person has
    // made of it since. Shown rather than blanked on a wizard opened again,
    // and compared rather than written blindly: «Дальше» writes only what
    // was changed, so walking past this step disturbs nothing.
    private string _nameWas = "";
    private string _formWas = "neutral";
    private string? _nameNow;
    private string? _formNow;

    /// <summary>The address forms the core offers: the value and its word.</summary>
    private readonly List<(string Value, string Title)> _forms = [];

    /// <summary>Which step asks for the name.</summary>
    public int NameStep { get; }

    /// <summary>Which step asks about the beta's telemetry.</summary>
    public int TelemetryStep { get; }

    // The same pair for the telemetry: what is stored and what was ticked.
    private bool _telemetryWas;
    private bool? _telemetryNow;
    private CheckBox? _telemetryBox;

    /// <summary>Which step asks whether to keep the conversation.</summary>
    public int HistoryStep { get; }

    // What is stored and what was ticked, as for the telemetry.
    private bool _historyWas;
    private bool? _historyNow;
    private CheckBox? _historyBox;

    /// <summary>Is the history box ticked on the step shown — for the check.</summary>
    public bool? HistoryTicked
    {
        get => _historyBox?.IsChecked;
        set
        {
            if (_historyBox is null) return;
            _historyBox.IsChecked = value;
            _historyNow = value == true;
        }
    }

    /// <summary>Is the telemetry box ticked on the step shown — for the check.</summary>
    public bool? TelemetryTicked
    {
        get => _telemetryBox?.IsChecked;
        set
        {
            if (_telemetryBox is null) return;
            _telemetryBox.IsChecked = value;
            _telemetryNow = value == true;
        }
    }

    /// <summary>Keep what the shown step holds, as «Дальше» would — for the check.</summary>
    public Task KeepForCheck() => _steps[_at].Keep?.Invoke() ?? Task.CompletedTask;

    /// <summary>How many address forms the name step offers — for the check.</summary>
    public int FormsOffered => _form?.Items.Count ?? 0;

    /// <summary>Which address form is chosen on the step shown — for the check.</summary>
    public string FormChosen
    {
        get => (_form?.SelectedItem as ComboBoxItem)?.Tag as string ?? "";
        set
        {
            if (_form is null) return;
            foreach (var item in _form.Items.OfType<ComboBoxItem>())
                if (item.Tag as string == value) _form.SelectedItem = item;
        }
    }

    /// <summary>What was typed as the person's name — for the check.</summary>
    public string NameTyped
    {
        get => _name?.Text ?? "";
        set { if (_name is not null) _name.Text = value; }
    }

    // ----------------------------------------------------------------- steps
    private FrameworkElement BuildGreeting()
    {
        var stack = new StackPanel();
        foreach (var line in new[]
                 {
                     S("Голос и распознавание — на вашем компьютере."),
                     S("Ничего не уходит в сеть без вашего ведома."),
                     S("Всё это потом можно поменять в настройках."),
                 })
            stack.Children.Add(new TextBlock
            {
                Text = "— " + line,
                Style = (Style)FindResource("Text.Body"),
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 0, 0, 8),
            });
        return stack;
    }

    private FrameworkElement BuildName()
    {
        var stack = new StackPanel();
        // Every visit builds the step anew, and a person walks back and
        // forth: what they typed is carried over, or a name typed a step ago
        // comes back as whatever is stored.
        var name = new TextBox
        {
            Style = (Style)FindResource("Field"),
            Text = _nameNow ?? _nameWas,
            Width = 260,
            HorizontalAlignment = HorizontalAlignment.Left,
        };
        name.TextChanged += (_, _) => _nameNow = name.Text;
        _name = name;
        // The same example the settings field shows, taken from there: one
        // name for one question, wherever it is asked.
        Styles.Ui.SetHint(name, SettingsLayout.HintInField("user_name"));
        stack.Children.Add(name);

        // On the same step because it is the same question — how to address
        // somebody — and Russian asks it twice: by name and by gender. Left
        // out when the core did not answer, rather than offered with words
        // the shell would have had to invent.
        _form = null;
        if (_forms.Count == 0) return stack;
        stack.Children.Add(new TextBlock
        {
            Text = SettingsLayout.TitleOf("address_form"),
            Style = (Style)FindResource("Text.Meta"),
            Margin = new Thickness(0, 16, 0, 6),
        });
        var form = new ComboBox
        {
            Style = (Style)FindResource("Choice"),
            Width = 260,
            HorizontalAlignment = HorizontalAlignment.Left,
        };
        var wanted = _formNow ?? _formWas;
        foreach (var (value, title) in _forms)
        {
            var item = new ComboBoxItem { Content = title, Tag = value };
            form.Items.Add(item);
            if (value == wanted) form.SelectedItem = item;
        }
        form.SelectionChanged += (_, _) =>
            _formNow = (form.SelectedItem as ComboBoxItem)?.Tag as string;
        _form = form;
        stack.Children.Add(form);
        return stack;
    }

    private FrameworkElement BuildWake()
    {
        var stack = new StackPanel();
        _wake = new TextBox
        {
            Style = (Style)FindResource("Field"),
            // Through the translation like anything else a person sees:
            // in an English window the word to call her by is "Rina".
            Text = S("Рина"),
            Width = 260,
            HorizontalAlignment = HorizontalAlignment.Left,
        };
        stack.Children.Add(_wake);
        stack.Children.Add(new TextBlock
        {
            Text = S("Например: «Рина, поставь таймер на десять минут»."),
            Style = (Style)FindResource("Text.Meta"),
            Margin = new Thickness(0, 10, 0, 0),
        });
        return stack;
    }

    private FrameworkElement BuildModels()
    {
        var stack = new StackPanel();
        if (_models.Count == 0)
        {
            stack.Children.Add(new TextBlock
            {
                Text = S("Ядро не на связи — скачать пока нечего."),
                Style = (Style)FindResource("Text.Body"),
                TextWrapping = TextWrapping.Wrap,
            });
            return stack;
        }

        foreach (var purpose in new[] { "stt", "tts" })
        {
            var group = _models
                .Where(m => (m["purpose"]?.GetValue<string>() ?? "stt")
                            == purpose)
                .ToArray();
            if (group.Length == 0) continue;

            // Headed, because the list has two halves and they answer
            // different questions. Until the voice was added there was
            // only one, and a flat list of five things with no telling
            // which was which is what the second half would have made of
            // it.
            stack.Children.Add(new TextBlock
            {
                Text = purpose == "stt" ? S("Чтобы слышать")
                                        : S("Чтобы говорить"),
                Style = (Style)FindResource("Text.Section"),
                Margin = new Thickness(0, stack.Children.Count == 0 ? 0 : 18,
                                       0, 10),
            });
            BuildGroup(stack, group);
        }
        return stack;
    }

    private void BuildGroup(StackPanel stack, JsonObject[] group)
    {
        foreach (var model in group)
        {
            var id = model["id"]?.GetValue<string>() ?? "";
            var size = model["size"]?.GetValue<long>() ?? 0;
            var ours = model["ours"]?.GetValue<bool>() ?? false;
            var have = model["installed"]?.GetValue<bool>() ?? false;

            var box = new CheckBox
            {
                Style = (Style)FindResource("Toggle"),
                Content = $"{model["title"]?.GetValue<string>()} · "
                          + Weighed(size),
                Tag = id,
                // Ticked in advance only where the catalogue says so, and it
                // says so for the small model alone. The full Russian Vosk
                // is two gigabytes: a box ticked for somebody is a box they
                // do not read, and they would agree to that download by not
                // noticing it.
                IsChecked = !have && (model["wanted"]?.GetValue<bool>()
                                      ?? false),
                // What the engine fetches for itself is shown and not
                // offered: we do not drive that transfer, and a tick that
                // starts nothing is a lie about who is in charge.
                IsEnabled = ours && !have,
                Margin = new Thickness(0, 0, 0, 4),
            };
            stack.Children.Add(box);

            var note = model["note"]?.GetValue<string>() ?? "";
            var kind = model["kind"]?.GetValue<string>() ?? "model";
            if (have)
                note = kind == "package" ? S("Уже установлено.")
                                         : S("Уже скачано.");
            else if (!ours) note = S("Скачается само при первом обращении.");
            if (note.Length > 0)
                stack.Children.Add(new TextBlock
                {
                    Text = note,
                    Style = (Style)FindResource("Text.Meta"),
                    TextWrapping = TextWrapping.Wrap,
                    Margin = new Thickness(28, 0, 0, 14),
                });
        }
    }

    private FrameworkElement BuildHistory()
    {
        var stack = new StackPanel();
        var box = new CheckBox
        {
            Style = (Style)FindResource("Toggle"),
            Content = S("Сохранять историю разговора"),
            IsChecked = _historyNow ?? _historyWas,
        };
        box.Click += (_, _) => _historyNow = box.IsChecked == true;
        _historyBox = box;
        stack.Children.Add(box);
        foreach (var line in new[]
                 {
                     S("Сохранённая история видна в разделе «Диалог». Выгрузить её в файл или стереть — целиком или по дням — можно в разделе «Приватность»."),
                     S("Если не сохранять, сказанное нигде не записывается."),
                     S("Решение можно поменять в настройках, в разделе «Приватность»."),
                 })
            stack.Children.Add(new TextBlock
            {
                Text = line,
                Style = (Style)FindResource("Text.Body"),
                TextWrapping = TextWrapping.Wrap,
                MaxWidth = 440,
                HorizontalAlignment = HorizontalAlignment.Left,
                Margin = new Thickness(0, 12, 0, 0),
            });
        return stack;
    }

    private async Task KeepHistory()
    {
        var wanted = _historyNow ?? _historyWas;
        if (wanted != _historyWas
            && await _link.SetAsync("save_history", JsonValue.Create(wanted)))
            _historyWas = wanted;
    }

    private FrameworkElement BuildTelemetry()
    {
        var stack = new StackPanel();
        var box = new CheckBox
        {
            Style = (Style)FindResource("Toggle"),
            Content = S("Отправлять обезличенную статистику беты"),
            IsChecked = _telemetryNow ?? _telemetryWas,
        };
        box.Click += (_, _) => TelemetryClicked();
        _telemetryBox = box;
        stack.Children.Add(box);
        foreach (var (title, said) in TelemetryConsent.Explained())
        {
            stack.Children.Add(new TextBlock
            {
                Text = title,
                Style = (Style)FindResource("Text.Meta"),
                Margin = new Thickness(0, 14, 0, 2),
            });
            stack.Children.Add(new TextBlock
            {
                Text = said,
                Style = (Style)FindResource("Text.Body"),
                TextWrapping = TextWrapping.Wrap,
                MaxWidth = 440,
                HorizontalAlignment = HorizontalAlignment.Left,
            });
        }
        return stack;
    }

    /// <summary>
    /// The box was clicked: a tick is asked about once more, a clearing is not.
    /// </summary>
    private void TelemetryClicked()
    {
        if (_telemetryBox is null) return;
        if (_telemetryBox.IsChecked == true && !TelemetryConsent.Ask(this))
            _telemetryBox.IsChecked = false;
        _telemetryNow = _telemetryBox.IsChecked == true;
    }

    /// <summary>Click the telemetry box as a person would — for the check.</summary>
    public void ClickTelemetryForCheck(bool on)
    {
        if (_telemetryBox is null) return;
        _telemetryBox.IsChecked = on;
        TelemetryClicked();
    }

    private async Task KeepTelemetry()
    {
        // Only a change is written, like the name: walking past the step on
        // a wizard opened again leaves the choice as it was.
        var wanted = _telemetryNow ?? _telemetryWas;
        if (wanted != _telemetryWas
            && await _link.SetAsync("telemetry", JsonValue.Create(wanted)))
            _telemetryWas = wanted;
    }

    private FrameworkElement BuildDone()
    {
        var stack = new StackPanel();
        var picked = _chosen.Count > 0
            ? S("Скачаем: ") + string.Join(", ", _chosen)
            : S("Скачивать нечего — распознавание можно включить позже.");
        stack.Children.Add(new TextBlock
        {
            Text = picked,
            Style = (Style)FindResource("Text.Body"),
            TextWrapping = TextWrapping.Wrap,
        });

        // Said here rather than found out later. On a second computer it
        // turned out that nothing at all gives Rina a voice out of the
        // box: the runtime carries what decodes sound and nothing that
        // makes it. She heard, understood, answered in text, and a person
        // spent an evening deciding the sound was broken.
        if (!Speaks())
            stack.Children.Add(new TextBlock
            {
                Text = S("Голоса пока нет: Рина будет слышать и отвечать текстом. Это поправимо в «Настройках»."),
                Style = (Style)FindResource("Text.Meta"),
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, 10, 0, 0),
            });
        stack.Children.Add(new TextBlock
        {
            Text = S("Ход скачивания виден в настройках, там же его можно остановить."),
            Style = (Style)FindResource("Text.Meta"),
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 12, 0, 0),
        });
        return stack;
    }

    /// <summary>Bytes as a person reads them.</summary>
    /// <remarks>
    /// Whole megabytes below a gigabyte and one decimal above: the number
    /// is here so somebody can decide whether to spend it, and "1.9 GB"
    /// decides that where "1946 MB" makes them do arithmetic first.
    /// </remarks>
    private static string Weighed(long bytes) =>
        bytes >= 1024L * 1024 * 1024
            ? S("{0} ГБ", (bytes / (1024.0 * 1024 * 1024)).ToString("0.0"))
            : S("{0} МБ", bytes / (1024 * 1024));

    // ------------------------------------------------------------ keeping
    private async Task KeepName()
    {
        // Only what changed is written. The field shows what is stored, so a
        // blank here is a decision — the name was there and was removed —
        // and writing it is right; an untouched field writes nothing, so
        // walking past the step leaves the settings as they were.
        var said = (_nameNow ?? _nameWas).Trim();
        if (said != _nameWas
            && await _link.SetAsync("user_name", JsonValue.Create(said)))
            _nameWas = said;

        var form = _formNow ?? _formWas;
        if (form != _formWas
            && await _link.SetAsync("address_form", JsonValue.Create(form)))
            _formWas = form;
    }

    private async Task KeepWake()
    {
        var said = _wake?.Text?.Trim() ?? "";
        if (said.Length > 0)
            await _link.SetAsync("wake_words", new JsonArray(said));
    }

    /// <summary>Will she have anything to speak with when this is done.</summary>
    /// <remarks>
    /// Counted from what is on the machine plus what was just ticked. A
    /// package already installed is as good as one chosen, and the
    /// question a person has is about the end state, not about this
    /// evening's downloads.
    /// </remarks>
    public bool Speaks()
        => _models.Any(m => (m["purpose"]?.GetValue<string>() ?? "stt") == "tts"
                            && (m["installed"]?.GetValue<bool>() == true
                                || _chosen.Contains(
                                    m["id"]?.GetValue<string>() ?? "")));

    private Task KeepAll()
    {
        // Read out of the boxes rather than tracked as they are clicked: a
        // person walks back and forth through a wizard, and a list kept up
        // to date by events is a list that disagrees with the screen the
        // first time somebody goes back.
        _chosen.Clear();
        return Task.CompletedTask;
    }

    private void Gather(DependencyObject root)
    {
        foreach (var box in Boxes(root))
            if (box.IsChecked == true && box.Tag is string id)
                _chosen.Add(id);
    }

    private static IEnumerable<CheckBox> Boxes(DependencyObject root)
    {
        if (root is CheckBox box) yield return box;
        var count = System.Windows.Media.VisualTreeHelper
            .GetChildrenCount(root);
        for (var at = 0; at < count; at++)
            foreach (var deeper in Boxes(
                         System.Windows.Media.VisualTreeHelper
                             .GetChild(root, at)))
                yield return deeper;
    }

    // ------------------------------------------------------------ moving
    /// <summary>Ask the core what can be downloaded.</summary>
    public async Task LoadAsync()
    {
        var told = await _link.AskAsync(Methods.ModelsCatalogue, null);
        foreach (var item in told?["items"]?.AsArray() ?? [])
            if (item is JsonObject model) _models.Add(model);

        // The name step's two answers: what is stored now, and the forms
        // with their words. Asked of the core like the settings page asks
        // it — the words for the forms are the core's, and a second list of
        // them here would part company with the first.
        var stored = await _link.AskAsync(Methods.SettingsGet, new JsonObject
        {
            ["keys"] = new JsonArray((JsonNode)"user_name",
                                     (JsonNode)"address_form",
                                     (JsonNode)"telemetry",
                                     (JsonNode)"save_history"),
        });
        _telemetryWas = stored?["values"]?["telemetry"]?.GetValue<bool>() ?? false;
        _historyWas = stored?["values"]?["save_history"]?.GetValue<bool>() ?? false;
        _nameWas = stored?["values"]?["user_name"]?.GetValue<string>() ?? "";
        _formWas = stored?["values"]?["address_form"]?.GetValue<string>()
                   ?? "neutral";
        var offered = await _link.AskAsync(Methods.SettingsOptions, new JsonObject
        {
            ["keys"] = new JsonArray((JsonNode)"address_form"),
        });
        foreach (var item in offered?["options"]?["address_form"]?.AsArray() ?? [])
            _forms.Add((item?["value"]?.GetValue<string>() ?? "",
                        item?["title"]?.GetValue<string>() ?? ""));

        if (_at == ModelsStep || _at == NameStep) Show(_at);
    }

    private void Show(int at)
    {
        _at = Math.Clamp(at, 0, _steps.Count - 1);
        var step = _steps[_at];
        Heading.Text = step.Title;
        Subheading.Text = step.Note;
        Stage.Content = step.Build();
        Where.Text = S("Шаг {0} из {1}", _at + 1, _steps.Count);
        BtnBack.IsEnabled = _at > 0;
        BtnNext.Content = _at == _steps.Count - 1 ? S("Начать") : S("Дальше");
    }

    private async void OnNext(object sender, RoutedEventArgs e)
    {
        // The models are read off the screen as we leave that step, not when
        // the wizard ends: by then the boxes have been replaced by the last
        // step's contents and there is nothing left to read.
        if (_at == ModelsStep) { _chosen.Clear(); Gather(Stage); }

        var keep = _steps[_at].Keep;
        if (keep is not null) await keep();

        if (_at < _steps.Count - 1) { Show(_at + 1); return; }
        DialogResult = true;
        Close();
    }

    private void OnBack(object sender, RoutedEventArgs e)
    {
        if (_at == ModelsStep) { _chosen.Clear(); Gather(Stage); }
        Show(_at - 1);
    }
}
