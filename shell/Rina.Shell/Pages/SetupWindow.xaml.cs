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
        _link = link;
        _steps.Add(new Step(
            S("Здравствуйте"),
            S("Рина — голосовой помощник на этом компьютере. Несколько вопросов, и всё."),
            BuildGreeting));
        _steps.Add(new Step(
            S("Как вас звать"),
            S("По этому слову Рина понимает, что обращаются к ней."),
            BuildWake, KeepWake));
        _steps.Add(new Step(
            S("Что доустановить"),
            S("Распознавание работает по пакету и модели — их размер в установщик не помещается."),
            BuildModels));
        _steps.Add(new Step(
            S("Готово"),
            S("Выбранное скачается в фоне. Пользоваться можно уже сейчас."),
            BuildDone, KeepAll));
        Show(0);
    }

    /// <summary>How many models the catalogue offered — for the check.</summary>
    public int Offered => _models.Count;

    /// <summary>How many boxes are ticked on the step shown — for the check.</summary>
    public int TickedNow =>
        Stage.Content is DependencyObject root
            ? Boxes(root).Count(b => b.IsChecked == true) : 0;

    /// <summary>Is there anything on the step at all — for the check.</summary>
    public bool StageFilled => Stage.Content is FrameworkElement;

    /// <summary>Open a given step — for the check and for screenshots.</summary>
    public void ShowFor(int at) => Show(at);

    /// <summary>Which models the person left ticked.</summary>
    public IReadOnlyList<string> Chosen => _chosen;

    private readonly List<string> _chosen = [];
    private readonly List<JsonObject> _models = [];
    private TextBox? _wake;

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

    private FrameworkElement BuildWake()
    {
        var stack = new StackPanel();
        _wake = new TextBox
        {
            Style = (Style)FindResource("Field"),
            Text = "Рина",
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

        foreach (var model in _models)
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
        return stack;
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
    private async Task KeepWake()
    {
        var said = _wake?.Text?.Trim() ?? "";
        if (said.Length > 0)
            await _link.SetAsync("wake_words", new JsonArray(said));
    }

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
        if (_at == 2) Show(2);
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
        if (_at == 2) { _chosen.Clear(); Gather(Stage); }

        var keep = _steps[_at].Keep;
        if (keep is not null) await keep();

        if (_at < _steps.Count - 1) { Show(_at + 1); return; }
        DialogResult = true;
        Close();
    }

    private void OnBack(object sender, RoutedEventArgs e)
    {
        if (_at == 2) { _chosen.Clear(); Gather(Stage); }
        Show(_at - 1);
    }
}
