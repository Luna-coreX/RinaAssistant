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
    //: Шаги последовательности, по порядку. Порядок и есть смысл: «открой
    //: браузер, потом папку» и наоборот — разные команды.
    private readonly List<JsonObject> _steps = [];
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

        foreach (var step in command["steps"]?.AsArray().OfType<JsonObject>()
                             ?? [])
            _steps.Add((JsonObject)step.DeepClone());
        DrawSteps();
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

        // Подсказка меняется вместе с видом: в одно и то же поле кладут
        // то путь, то адрес, то фразу, и «Что открыть» на все случаи
        // заставляло бы человека догадываться, в каком виде.
        Styles.Ui.SetHint(Target, kind switch
        {
            "app" => S(@"например, C:\Program Files\App\app.exe"),
            "folder" => S(@"например, D:\Проекты"),
            "website" => S("например, github.com"),
            "speak" => S("что произнести"),
            _ => "",
        });

        TargetLabel.Text = kind switch
        {
            "app" => S("Какую программу открыть"),
            "folder" => S("Какую папку открыть"),
            "website" => S("Какой адрес открыть"),
            "speak" => S("Что произнести"),
            "system" => S("Какое действие"),
            _ => S("Что открыть"),
        };

        StepsBox.Visibility = kind == "sequence" ? Visibility.Visible
                                                 : Visibility.Collapsed;
        if (kind == "sequence" && StepKind.Items.Count == 0) FillStepKinds();
        Note.Text = "";
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

    /// <summary>
    /// Виды шага — те же, что у команды, кроме самой последовательности.
    /// </summary>
    /// <remarks>
    /// Последовательность внутри последовательности не запрещена ядром, но
    /// в конструкторе её нет: «шаг, который сам список шагов» превращает
    /// понятную цепочку в дерево, а человек, собирающий «открой браузер и
    /// сверни окно», дерева не имел в виду.
    /// </remarks>
    private void FillStepKinds()
    {
        foreach (var item in Kind.Items.OfType<ComboBoxItem>())
        {
            if ((string?)item.Tag == "sequence") continue;
            StepKind.Items.Add(new ComboBoxItem
            {
                Content = item.Content,
                Tag = item.Tag,
            });
        }
        foreach (var (value, title, destructive) in _actions)
            StepAction.Items.Add(new ComboBoxItem
            {
                Content = destructive ? title + S(" — необратимо") : title,
                Tag = value,
            });
        if (StepKind.Items.Count > 0) StepKind.SelectedIndex = 0;
    }

    private string StepSelectedKind =>
        (StepKind.SelectedItem as ComboBoxItem)?.Tag as string ?? "app";

    private void OnStepKindChanged(object sender, SelectionChangedEventArgs e)
    {
        var kind = StepSelectedKind;
        var system = kind == "system";
        StepAction.Visibility = system ? Visibility.Visible
                                       : Visibility.Collapsed;
        StepTarget.Visibility = system ? Visibility.Collapsed
                                       : Visibility.Visible;
        StepBrowse.Visibility = kind is "app" or "folder"
            ? Visibility.Visible : Visibility.Collapsed;
    }

    private void OnStepBrowse(object sender, RoutedEventArgs e)
    {
        if (StepSelectedKind == "folder")
        {
            var folder = new Microsoft.Win32.OpenFolderDialog();
            if (folder.ShowDialog() == true) StepTarget.Text = folder.FolderName;
            return;
        }
        var file = new Microsoft.Win32.OpenFileDialog
        {
            Filter = S("Программы (*.exe;*.lnk)|*.exe;*.lnk|Все файлы|*.*"),
        };
        if (file.ShowDialog() == true) StepTarget.Text = file.FileName;
    }

    private void OnAddStep(object sender, RoutedEventArgs e)
    {
        var kind = StepSelectedKind;
        var target = kind == "system"
            ? (StepAction.SelectedItem as ComboBoxItem)?.Tag as string ?? ""
            : StepTarget.Text.Trim();
        if (target.Length == 0)
        {
            Note.Text = S("Шагу нужно указать, что делать.");
            return;
        }

        // У шага нет ни фраз, ни своего ответа: срабатывает и отвечает
        // команда целиком, а шаг — то, что она делает по дороге.
        _steps.Add(new JsonObject
        {
            ["type"] = kind,
            ["target"] = target,
            ["enabled"] = true,
            ["triggers"] = new JsonArray(),
            ["match"] = "contains",
            ["response"] = "",
            ["steps"] = new JsonArray(),
        });
        StepTarget.Clear();
        Note.Text = "";
        DrawSteps();
    }

    /// <summary>Показать шаги с их порядком и кнопками.</summary>
    private void DrawSteps()
    {
        Steps.Children.Clear();
        StepsEmpty.Visibility = _steps.Count == 0 ? Visibility.Visible
                                                  : Visibility.Collapsed;

        for (var at = 0; at < _steps.Count; at++)
        {
            var index = at;
            var step = _steps[at];
            var row = new Grid { Margin = new Thickness(0, 0, 0, 4) };
            row.ColumnDefinitions.Add(new ColumnDefinition
            {
                Width = GridLength.Auto,
            });
            row.ColumnDefinitions.Add(new ColumnDefinition
            {
                Width = new GridLength(1, GridUnitType.Star),
            });
            for (var i = 0; i < 3; i++)
                row.ColumnDefinitions.Add(new ColumnDefinition
                {
                    Width = GridLength.Auto,
                });

            // Номер, а не маркер: человек читает «сначала первый, потом
            // второй», и порядок должен быть виден, а не подразумеваться.
            var number = new TextBlock
            {
                Text = $"{index + 1}.",
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Center,
                Margin = new Thickness(0, 0, 8, 0),
            };
            Grid.SetColumn(number, 0);
            row.Children.Add(number);

            var what = new TextBlock
            {
                Text = DescribeStep(step),
                Style = (Style)FindResource("Text.Body"),
                VerticalAlignment = VerticalAlignment.Center,
                TextTrimming = TextTrimming.CharacterEllipsis,
            };
            Grid.SetColumn(what, 1);
            row.Children.Add(what);

            var up = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = "↑",
                IsEnabled = index > 0,
            };
            up.Click += (_, _) => Move(index, -1);
            Grid.SetColumn(up, 2);
            row.Children.Add(up);

            var down = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = "↓",
                IsEnabled = index < _steps.Count - 1,
            };
            down.Click += (_, _) => Move(index, +1);
            Grid.SetColumn(down, 3);
            row.Children.Add(down);

            var drop = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Убрать"),
            };
            drop.Click += (_, _) => { _steps.RemoveAt(index); DrawSteps(); };
            Grid.SetColumn(drop, 4);
            row.Children.Add(drop);

            Steps.Children.Add(row);
        }
    }

    private void Move(int index, int delta)
    {
        var to = index + delta;
        if (to < 0 || to >= _steps.Count) return;
        (_steps[index], _steps[to]) = (_steps[to], _steps[index]);
        DrawSteps();
    }

    /// <summary>Шаг человеческими словами: вид и что именно.</summary>
    private string DescribeStep(JsonObject step)
    {
        var kind = step["type"]?.GetValue<string>() ?? "";
        var target = step["target"]?.GetValue<string>() ?? "";
        var title = Kind.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == kind)
            ?.Content?.ToString() ?? kind;

        // У системного действия цель — код из перечня, и показывать его
        // человеку незачем: у действия есть название.
        if (kind == "system")
        {
            var named = _actions.FirstOrDefault(a => a.Value == target);
            return $"{title} · {(named.Title.Length > 0 ? named.Title : target)}";
        }
        return target.Length > 0 ? $"{title} · {target}" : title;
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
        if (kind == "sequence" && _steps.Count == 0)
        {
            Note.Text = S("Нужен хотя бы один шаг.");
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
            ["steps"] = new JsonArray(
                _steps.Select(step => step.DeepClone()).ToArray()),
        };
        // Номер назначает ядро; свой посылаем только когда правим уже
        // заведённую — иначе правка превратилась бы в создание двойника.
        if (_id.Length > 0) command["id"] = _id;

        Saved?.Invoke(command);
    }

    private void OnCancel(object sender, RoutedEventArgs e) => Cancelled?.Invoke();

    /// <summary>
    /// Собрать последовательность из шагов — для сквозной проверки.
    /// </summary>
    /// <remarks>
    /// Проверка не умеет щёлкать по кнопкам, а собранная руками команда
    /// проверяла бы не конструктор, а `JsonObject`. Здесь проходит тот же
    /// путь: выбрать вид, добавить шаги, сохранить.
    /// </remarks>
    public bool BuildSequenceForCheck(string phrase,
                                      IEnumerable<(string Kind, string Target)> steps)
    {
        _triggers.Clear();
        _triggers.Add(phrase);
        DrawTriggers();

        Kind.SelectedItem = Kind.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == "sequence");
        if (SelectedKind != "sequence") return false;

        foreach (var (kind, target) in steps)
        {
            StepKind.SelectedItem = StepKind.Items.OfType<ComboBoxItem>()
                .FirstOrDefault(item => (string?)item.Tag == kind);

            // У системного шага цель выбирают из списка, а не набирают:
            // первая редакция проверки набирала — и системный шаг молча не
            // добавлялся, потому что список оставался пустым.
            if (kind == "system")
                StepAction.SelectedItem = StepAction.Items
                    .OfType<ComboBoxItem>()
                    .FirstOrDefault(item => (string?)item.Tag == target);
            else
                StepTarget.Text = target;

            OnAddStep(this, new RoutedEventArgs());
        }
        if (_steps.Count == 0) return false;

        // И порядок: последний шаг поднимаем наверх и опускаем обратно.
        var wasFirst = _steps[0]["target"]?.GetValue<string>();
        Move(_steps.Count - 1, -1);
        Move(_steps.Count - 2, +1);
        if (_steps[0]["target"]?.GetValue<string>() != wasFirst) return false;

        OnSave(this, new RoutedEventArgs());
        return true;
    }

    /// <summary>Сколько шагов собрано — для проверки.</summary>
    public int StepCount => _steps.Count;
}
