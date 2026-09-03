using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// Конструктор команды: фразы, действие, ответ.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-F04</c>. Страница команд умела показывать, включать,
/// выполнять и удалять — но не заводить, и потому у нового человека была
/// пуста навсегда: первую команду взять было неоткуда.
/// </para>
/// <para>
/// <b>Виды действий приходят от ядра</b> (<c>commands.kinds</c>), а не
/// написаны здесь. Выполнять их ядру, и список у него; оболочка, знающая
/// его наизусть, разошлась бы молча — показала бы действие, которого нет,
/// или спрятала бы новое. То же правило, что у списков в настройках.
/// </para>
/// <para>
/// <b>Необратимое помечено ещё в конструкторе.</b> Подтверждение спросит
/// ядро при срабатывании (§11), но узнать, что «выключить компьютер»
/// необратимо, человек должен здесь — а не в тот раз, когда фраза совпала
/// случайно.
/// </para>
/// </remarks>
public partial class CommandEditor : UserControl
{
    private readonly List<string> _triggers = [];
    private readonly List<(string Value, string Title, bool Destructive)>
        _actions = [];
    private string _id = "";

    /// <summary>Человек сохранил команду; страница перечитывает список.</summary>
    public event Action<JsonObject>? Saved;

    /// <summary>Человек передумал.</summary>
    public event Action? Cancelled;

    public CommandEditor(JsonObject kinds, JsonObject? existing = null)
    {
        InitializeComponent();

        foreach (var kind in kinds["kinds"]?.AsArray()
                             .OfType<JsonObject>() ?? [])
            Kind.Items.Add(new ComboBoxItem
            {
                Content = $"{kind["icon"]?.GetValue<string>()} "
                          + kind["title"]?.GetValue<string>(),
                Tag = kind["value"]?.GetValue<string>(),
            });

        foreach (var action in kinds["actions"]?.AsArray()
                               .OfType<JsonObject>() ?? [])
            _actions.Add((action["value"]?.GetValue<string>() ?? "",
                          action["title"]?.GetValue<string>() ?? "",
                          action["destructive"]?.GetValue<bool>() ?? false));

        foreach (var (value, title, destructive) in _actions)
            Action.Items.Add(new ComboBoxItem
            {
                Content = destructive ? title + S(" — необратимо") : title,
                Tag = value,
            });
        Action.SelectionChanged += (_, _) => ShowWarning();

        if (existing is not null) Fill(existing);
        else Kind.SelectedIndex = 0;
    }

    private void Fill(JsonObject command)
    {
        Legend.Text = S("ПРАВКА КОМАНДЫ");
        _id = command["id"]?.GetValue<string>() ?? "";

        foreach (var phrase in command["triggers"]?.AsArray() ?? [])
            _triggers.Add(phrase?.GetValue<string>() ?? "");
        DrawTriggers();

        var kind = command["type"]?.GetValue<string>() ?? "app";
        Kind.SelectedItem = Kind.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == kind)
            ?? Kind.Items.OfType<ComboBoxItem>().FirstOrDefault();

        var target = command["target"]?.GetValue<string>() ?? "";
        Target.Text = target;
        Action.SelectedItem = Action.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == target);
        Response.Text = command["response"]?.GetValue<string>() ?? "";
    }

    private string SelectedKind =>
        (Kind.SelectedItem as ComboBoxItem)?.Tag as string ?? "app";

    /// <summary>
    /// Поле цели меняется вместе с видом.
    /// </summary>
    /// <remarks>
    /// У «программы» это путь, у «сайта» — адрес, у «системного действия» —
    /// выбор из списка, а «озвучить» вообще не про цель, а про текст.
    /// Одно поле «цель» на все случаи заставило бы человека знать, что
    /// именно в него положено вписать.
    /// </remarks>
    private void OnKindChanged(object sender, SelectionChangedEventArgs e)
    {
        var kind = SelectedKind;
        var picks = kind is "app" or "folder";
        var system = kind == "system";

        TargetRow.Visibility = kind == "sequence" ? Visibility.Collapsed
                                                  : Visibility.Visible;
        Action.Visibility = system ? Visibility.Visible : Visibility.Collapsed;
        Target.Visibility = system ? Visibility.Collapsed : Visibility.Visible;
        Browse.Visibility = picks ? Visibility.Visible : Visibility.Collapsed;

        TargetLabel.Text = kind switch
        {
            "app" => S("Какую программу открыть"),
            "folder" => S("Какую папку открыть"),
            "website" => S("Какой адрес открыть"),
            "speak" => S("Что произнести"),
            "system" => S("Какое действие"),
            _ => S("Что открыть"),
        };

        // Последовательность из нескольких шагов конструктором пока не
        // собирается: у неё своё устройство, и делать её половину — значит
        // показать человеку поле, которое ничего не соберёт. Такие команды
        // приходят импортом и правятся как есть.
        Note.Text = kind == "sequence"
            ? S("Последовательность собирается импортом, а не здесь.") : "";
        ShowWarning();
    }

    private void ShowWarning()
    {
        var chosen = (Action.SelectedItem as ComboBoxItem)?.Tag as string ?? "";
        var destructive = SelectedKind == "system"
                          && _actions.Any(a => a.Value == chosen
                                               && a.Destructive);
        Warning.Text = destructive
            ? S("Это действие необратимо — Рина спросит подтверждение.") : "";
        Warning.Visibility = destructive ? Visibility.Visible
                                         : Visibility.Collapsed;
    }

    private void OnAddTrigger(object sender, RoutedEventArgs e)
    {
        var phrase = NewTrigger.Text.Trim();
        if (phrase.Length == 0 || _triggers.Contains(phrase)) return;
        _triggers.Add(phrase);
        NewTrigger.Clear();
        DrawTriggers();
    }

    private void DrawTriggers()
    {
        Phrases.Children.Clear();
        foreach (var phrase in _triggers.ToArray())
        {
            var row = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 0, 0, 4),
            };
            row.Children.Add(new TextBlock
            {
                Text = "«" + phrase + "»",
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Center,
                MinWidth = 240,
            });
            var drop = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Убрать"),
            };
            drop.Click += (_, _) => { _triggers.Remove(phrase); DrawTriggers(); };
            row.Children.Add(drop);
            Phrases.Children.Add(row);
        }
    }

    private void OnBrowse(object sender, RoutedEventArgs e)
    {
        if (SelectedKind == "folder")
        {
            var folder = new Microsoft.Win32.OpenFolderDialog();
            if (folder.ShowDialog() == true) Target.Text = folder.FolderName;
            return;
        }
        var file = new Microsoft.Win32.OpenFileDialog
        {
            Filter = S("Программы (*.exe;*.lnk)|*.exe;*.lnk|Все файлы|*.*"),
        };
        if (file.ShowDialog() == true) Target.Text = file.FileName;
    }

    private void OnSave(object sender, RoutedEventArgs e)
    {
        if (_triggers.Count == 0)
        {
            Note.Text = S("Нужна хотя бы одна фраза.");
            return;
        }

        var kind = SelectedKind;
        var target = kind == "system"
            ? (Action.SelectedItem as ComboBoxItem)?.Tag as string ?? ""
            : Target.Text.Trim();
        if (kind != "sequence" && target.Length == 0)
        {
            Note.Text = S("Нужно указать, что делать.");
            return;
        }

        var command = new JsonObject
        {
            ["enabled"] = true,
            ["type"] = kind,
            ["triggers"] = new JsonArray(
                _triggers.Select(t => (JsonNode)t!).ToArray()),
            ["match"] = "contains",
            ["target"] = target,
            ["response"] = Response.Text.Trim(),
        };
        // Номер назначает ядро; свой посылаем только когда правим уже
        // заведённую — иначе правка превратилась бы в создание двойника.
        if (_id.Length > 0) command["id"] = _id;

        Saved?.Invoke(command);
    }

    private void OnCancel(object sender, RoutedEventArgs e) => Cancelled?.Invoke();
}
