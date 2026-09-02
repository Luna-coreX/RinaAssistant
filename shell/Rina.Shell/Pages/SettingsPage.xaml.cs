using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

namespace Rina.Shell.Pages;

/// <summary>
/// Настройки: десять секций одной панелью.
/// </summary>
/// <remarks>
/// <para>
/// Здесь встречаются две половины [ADR 0006](../../../docs/adr/0006-settings-ownership.md).
/// Ядро прислало смысл — тип, умолчание, перечисление, диапазон, зависимость,
/// признак «нужен перезапуск». Оболочка знает вид — подписи и секции
/// (<see cref="SettingsLayout"/>). Ни одна половина не может быть выведена
/// из другой, и в этом всё решение.
/// </para>
/// <para>
/// <b>Зависимые поля гаснут, а не прячутся.</b> «Адрес модели» при
/// выключенной модели бесполезен, но спрятать его значит заставить человека
/// гадать, куда он делся. Выключенное обязано читаться как выключенное, а не
/// как отсутствующее — то же правило, что и в дизайн-системе про контраст.
/// </para>
/// <para>
/// <b>Предупреждение — не отказ.</b> «Адрес не локальный» значит, что
/// значение записано, а человеку сказано, чем это обернётся. Решать ему.
/// </para>
/// </remarks>
public partial class SettingsPage : UserControl
{
    private readonly CoreLink? _link;
    private readonly Dictionary<string, JsonObject> _schema = [];
    private readonly Dictionary<string, JsonNode?> _values = [];
    private readonly Dictionary<string, FrameworkElement> _editors = [];

    /// <summary>Сколько секций построено — для сквозной проверки.</summary>
    public int SectionCount => Body.Children.Count;

    /// <summary>Ключей, которые ядро прислало, а оболочка разложила.</summary>
    public int KeyCount => _schema.Count;

    /// <summary>Первый выпадающий список — для сквозной проверки.</summary>
    public ComboBox? FirstChoice() =>
        _editors.Values.OfType<ComboBox>().FirstOrDefault(b => b.Items.Count > 0);

    /// <summary>
    /// Прокрутить на столько-то — чтобы снимок доставал ниже сгиба.
    /// </summary>
    /// <remarks>
    /// Половина экрана настроек не видна на первом экране, и проверять
    /// снимком только верх значит не проверять список папок, выбор модели и
    /// выбор устройств — ровно то, что здесь и делалось.
    /// </remarks>
    public void ScrollTo(double offset) => Scroll.ScrollToVerticalOffset(offset);

    /// <summary>Готово: схема получена и разложена.</summary>
    public event Action? Ready;

    public SettingsPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;

        if (_link is null)
        {
            Note.Text = "Ядро не на связи — настройки недоступны.";
            return;
        }
        Loaded += async (_, _) => await LoadAsync();
    }

    private async Task LoadAsync()
    {
        var described = await Ask(Methods.SettingsDescribe);
        if (described?["schema"] is not JsonObject schema) return;

        // Пропускаются два признака, и они значат разное. `obsolete` —
        // «заменено» (пять палитр 3.1.0 уступили двум отделкам). `secret` —
        // «служебное»: состояние хранилища, а не настройка, и показывать его
        // человеку незачем, как и писать в журнал.
        foreach (var (key, spec) in schema)
            if (spec is JsonObject entry
                && entry["obsolete"] is null && entry["secret"] is null)
                _schema[key] = entry;

        var got = await Ask(Methods.SettingsGet, new JsonObject
        {
            ["keys"] = new JsonArray(_schema.Keys
                .Select(k => (JsonNode)k!).ToArray()),
        });
        if (got?["values"] is JsonObject values)
            foreach (var (key, value) in values)
                _values[key] = value?.DeepClone();

        await LoadOptionsAsync();
        Build();
        Ready?.Invoke();
    }

    /// <summary>
    /// Спросить у ядра списки, которые оно объявило изменчивыми.
    /// </summary>
    /// <remarks>
    /// Схема говорит, что набор значений есть, но не какой: «какие голоса
    /// установлены» вчерашним быть не может. Устройства при этом
    /// перечисляет оболочка — их знает она (<see cref="SettingsLayout.ShellKnows"/>).
    /// </remarks>
    private async Task LoadOptionsAsync()
    {
        _options.Clear();

        foreach (var key in SettingsLayout.ShellKnows)
        {
            if (!_schema.ContainsKey(key)) continue;
            var devices = key == "input_device"
                ? Audio.Microphone.Devices()
                : Audio.Speaker.Devices();
            var listed = new List<(string, string, bool)>
            {
                ("default", "Устройство по умолчанию", true),
            };
            listed.AddRange(devices.Select(d => (d.Name, d.Name, true)));
            _options[key] = listed;
        }

        var dynamic = _schema.Where(pair => pair.Value["dynamic"] is not null)
                             .Select(pair => pair.Key).ToArray();
        if (dynamic.Length == 0) return;

        var told = await Ask(Methods.SettingsOptions, new JsonObject
        {
            ["keys"] = new JsonArray(dynamic.Select(k => (JsonNode)k!).ToArray()),
        });
        if (told?["options"] is not JsonObject answered) return;

        foreach (var (key, list) in answered)
        {
            if (list is not JsonArray items) continue;
            _options[key] = items.Select(item => (
                item?["value"]?.GetValue<string>() ?? "",
                item?["title"]?.GetValue<string>() ?? "",
                item?["available"]?.GetValue<bool>() ?? true)).ToList();
        }
    }

    private readonly Dictionary<string, List<(string Value, string Title,
                                              bool Available)>> _options = [];

    private void Build()
    {
        Body.Children.Clear();
        var placed = new HashSet<string>();

        foreach (var section in SettingsLayout.Sections)
        {
            var keys = section.Keys.Where(k => _schema.ContainsKey(k.Key))
                                   .ToArray();
            if (keys.Length == 0) continue;
            Body.Children.Add(BuildSection(section.Title,
                                           keys.Select(k => k.Key)));
            foreach (var k in keys) placed.Add(k.Key);
        }

        // Правило с зубами из ADR 0006: незнакомый ключ показывается, а не
        // прячется. Ядро завело настройку, оболочку не обновили — и без
        // этой секции настройка стала бы недостижимой незаметно.
        var strangers = _schema.Keys
            .Where(k => !placed.Contains(k)
                        && !SettingsLayout.Elsewhere.Contains(k))
            .OrderBy(k => k, StringComparer.Ordinal)
            .ToArray();
        if (strangers.Length > 0)
            Body.Children.Add(BuildSection(SettingsLayout.Other, strangers));
    }

    private UIElement BuildSection(string title, IEnumerable<string> keys)
    {
        var stack = new StackPanel { Margin = new Thickness(0, 0, 0, 32) };
        stack.Children.Add(new TextBlock
        {
            Text = title.ToUpperInvariant(),
            Style = (Style)FindResource("Text.Section"),
            Margin = new Thickness(0, 0, 0, 12),
        });
        foreach (var key in keys) stack.Children.Add(BuildRow(key));
        return stack;
    }

    private UIElement BuildRow(string key)
    {
        var spec = _schema[key];
        var row = new Grid { MinHeight = 40, Margin = new Thickness(0, 0, 0, 6) };
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        var label = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        label.Children.Add(new TextBlock
        {
            Text = SettingsLayout.TitleOf(key),
            Style = (Style)FindResource("Text.Body"),
        });

        var notes = new List<string>();
        if (SettingsLayout.HintOf(key).Length > 0)
            notes.Add(SettingsLayout.HintOf(key));
        if (spec["restart_required"] is not null)
            notes.Add("применится после перезапуска");
        if (!SettingsLayout.Known.Contains(key))
            notes.Add($"ключ {key} оболочке незнаком");
        if (notes.Count > 0)
            label.Children.Add(new TextBlock
            {
                Text = string.Join(" · ", notes),
                Style = (Style)FindResource("Text.Meta"),
                Margin = new Thickness(0, 2, 0, 0),
                TextWrapping = TextWrapping.Wrap,
            });

        Grid.SetColumn(label, 0);
        row.Children.Add(label);

        var editor = BuildEditor(key, spec);
        _editors[key] = editor;
        Grid.SetColumn(editor, 1);
        row.Children.Add(editor);

        ApplyDependency(key, spec, row);
        return row;
    }

    private FrameworkElement BuildEditor(string key, JsonObject spec)
    {
        var type = spec["type"]?.GetValue<string>() ?? "string";
        var value = _values.GetValueOrDefault(key);

        // Список известных значений — выпадающий список, а не строка.
        // Набор пришёл от того, кто его знает: от ядра или от оболочки.
        if (_options.TryGetValue(key, out var known))
            return known.Count > 0
                ? BuildChoice(key, known, value?.GetValue<string>() ?? "")
                : Nothing();

        // Путь: строка плюс «Обзор…». Каким окном выбирать — решает
        // оболочка, ядро сказало лишь, что это путь.
        // Порядок важен: у списка папок есть и тип «массив», и формат
        // «путь». Массив решает, чем правят; формат — чем добавляют.
        if (type == "array")
            return BuildList(key, value as JsonArray,
                             spec["format"]?.GetValue<string>() ?? "");
        if (type == "object") return BuildMap(key, value as JsonObject);

        if (spec["format"]?.GetValue<string>() is { } format)
            return BuildPath(key, format, Show(value));

        if (type == "boolean")
        {
            var toggle = new CheckBox
            {
                Style = (Style)FindResource("Toggle"),
                IsChecked = value?.GetValue<bool>() ?? false,
                VerticalAlignment = VerticalAlignment.Center,
            };
            toggle.Click += async (_, _) =>
                await SaveAsync(key, toggle.IsChecked == true);
            return toggle;
        }

        if (spec["choices"] is JsonArray choices)
        {
            var box = new ComboBox
            {
                Style = (Style)FindResource("Choice"),
                Width = 280,
                ItemsSource = choices.Select(c => c!.GetValue<string>()).ToArray(),
                SelectedItem = value?.GetValue<string>(),
            };
            box.SelectionChanged += async (_, _) =>
            {
                if (box.SelectedItem is string chosen)
                    await SaveAsync(key, chosen);
            };
            return box;
        }

        var field = new TextBox
        {
            Style = (Style)FindResource("Field"),
            Width = 260,
            Text = Show(value),
        };
        field.LostFocus += async (_, _) => await SaveAsync(key, Parse(field.Text, type));
        return field;
    }

    /// <summary>
    /// Выпадающий список. Недоступное показано, но выбрать нельзя.
    /// </summary>
    /// <remarks>
    /// Прятать неустановленный движок нельзя: человек не узнает, что такой
    /// вообще бывает, и будет искать его в интернете, стоя перед списком, где
    /// он есть. Показанный и погашенный — это ответ «такое бывает, но у вас
    /// не установлено».
    /// </remarks>
    private FrameworkElement BuildChoice(string key,
        List<(string Value, string Title, bool Available)> known, string current)
    {
        var box = new ComboBox
        {
            Style = (Style)FindResource("Choice"),
            Width = 280,
        };
        foreach (var (value, title, available) in known)
            box.Items.Add(new ComboBoxItem
            {
                Content = title.Length > 0 ? title : value,
                Tag = value,
                IsEnabled = available,
            });

        box.SelectedItem = box.Items.OfType<ComboBoxItem>()
            .FirstOrDefault(item => (string?)item.Tag == current);

        // Сохранённого значения в сегодняшнем наборе может не быть: движок
        // сменили, модель удалили. Пустой список — худший из ответов: он
        // выглядит как «ничего не выбрано», хотя выбрано, и работает.
        if (box.SelectedItem is null && current.Length > 0)
        {
            var stale = new ComboBoxItem
            {
                Content = $"{current} — сейчас недоступно",
                Tag = current,
            };
            box.Items.Insert(0, stale);
            box.SelectedItem = stale;
        }
        box.SelectionChanged += async (_, _) =>
        {
            if (box.SelectedItem is ComboBoxItem { Tag: string chosen })
                await SaveAsync(key, chosen);
        };
        return box;
    }

    /// <summary>
    /// Выбирать не из чего — и это надо сказать, а не дать поле ввода.
    /// </summary>
    /// <remarks>
    /// У «Без озвучки» голосов нет. Поле, куда можно вписать что угодно,
    /// пообещало бы, что вписанное заработает.
    /// </remarks>
    private FrameworkElement Nothing()
    {
        var box = new ComboBox
        {
            Style = (Style)FindResource("Choice"),
            Width = 280,
            IsEnabled = false,
        };
        box.Items.Add(new ComboBoxItem { Content = "выбирать не из чего" });
        box.SelectedIndex = 0;
        return box;
    }

    /// <summary>Путь: поле и «Обзор…».</summary>
    private FrameworkElement BuildPath(string key, string format, string current)
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal };
        var field = new TextBox
        {
            Style = (Style)FindResource("Field"),
            Width = 200,
            Text = current,
            IsReadOnly = true,
            ToolTip = current,
        };
        var browse = new Button
        {
            Style = (Style)FindResource("Btn"),
            Content = "Обзор…",
            Margin = new Thickness(8, 0, 0, 0),
        };
        browse.Click += async (_, _) =>
        {
            var picked = format == "folder" ? PickFolder() : PickFile();
            if (picked is null) return;
            field.Text = picked;
            field.ToolTip = picked;
            await SaveAsync(key, picked);
        };
        row.Children.Add(field);
        row.Children.Add(browse);
        return row;
    }

    private static string? PickFolder()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = "Где лежит модель",
        };
        return dialog.ShowDialog() == true ? dialog.FolderName : null;
    }

    private static string? PickFile()
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Title = "Выберите файл модели",
            Filter = "Модели (*.onnx;*.bin;*.pt)|*.onnx;*.bin;*.pt|Все файлы|*.*",
        };
        return dialog.ShowDialog() == true ? dialog.FileName : null;
    }

    /// <summary>
    /// Список: что в нём есть, что добавить, что убрать.
    /// </summary>
    /// <remarks>
    /// Строка через запятую вместо списка была бы приглашением потерять
    /// путь с запятой в имени. Здесь добавляют и убирают по одному.
    /// </remarks>
    private FrameworkElement BuildList(string key, JsonArray? current,
                                       string format)
    {
        var items = (current ?? []).Select(v => v?.GetValue<string>() ?? "")
                                   .Where(v => v.Length > 0).ToList();
        var stack = new StackPanel { HorizontalAlignment = HorizontalAlignment.Right };

        foreach (var item in items)
        {
            var row = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                HorizontalAlignment = HorizontalAlignment.Right,
            };
            row.Children.Add(new TextBlock
            {
                Text = item,
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Center,
                MaxWidth = 220,
                TextTrimming = TextTrimming.CharacterEllipsis,
                ToolTip = item,
            });
            var drop = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = "Убрать",
                Tag = item,
            };
            drop.Click += async (_, _) =>
            {
                items.Remove(item);
                await SaveAsync(key, new JsonArray(
                    items.Select(v => (JsonNode)v!).ToArray()));
            };
            row.Children.Add(drop);
            stack.Children.Add(row);
        }

        async Task AddAsync(string what)
        {
            if (what.Length == 0 || items.Contains(what)) return;
            items.Add(what);
            await SaveAsync(key, new JsonArray(
                items.Select(v => (JsonNode)v!).ToArray()));
        }

        var adding = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
            Margin = new Thickness(0, 4, 0, 0),
        };

        // Папку выбирают окном, слово набирают. Одна кнопка на оба случая
        // означала бы либо путь с опечаткой, либо выбор папки вместо слова.
        if (format == "folder")
        {
            var add = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = "Добавить папку…",
            };
            add.Click += async (_, _) =>
            {
                if (PickFolder() is { } folder) await AddAsync(folder);
            };
            adding.Children.Add(add);
        }
        else
        {
            var typed = new TextBox
            {
                Style = (Style)FindResource("Field"),
                Width = 150,
                Margin = new Thickness(0, 0, 8, 0),
            };
            var add = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = "Добавить",
            };
            add.Click += async (_, _) =>
            {
                await AddAsync(typed.Text.Trim());
                typed.Clear();
            };
            adding.Children.Add(typed);
            adding.Children.Add(add);
        }
        stack.Children.Add(adding);
        return stack;
    }

    /// <summary>
    /// Словарь: сколько записей и как забыть их все.
    /// </summary>
    /// <remarks>
    /// Выученные соответствия правят не по одному: человек не помнит, какое
    /// слово к какой программе привязалось, — он помнит, что Рина «путает».
    /// Поэтому счётчик и «забыть все», как и было в 3.1.0.
    /// </remarks>
    private FrameworkElement BuildMap(string key, JsonObject? current)
    {
        var row = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            HorizontalAlignment = HorizontalAlignment.Right,
        };
        row.Children.Add(new TextBlock
        {
            Text = $"записей: {current?.Count ?? 0}",
            Style = (Style)FindResource("Text.Meta"),
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(0, 0, 8, 0),
        });
        var forget = new Button
        {
            Style = (Style)FindResource("Btn"),
            Content = SettingsLayout.ClearWordOf(key),
            IsEnabled = (current?.Count ?? 0) > 0,
        };
        forget.Click += async (_, _) => await SaveAsync(key, new JsonObject());
        row.Children.Add(forget);
        return row;
    }

    /// <summary>
    /// Погасить поле, если оно зависит от выключенного.
    /// </summary>
    /// <remarks>
    /// Зависимость знает ядро: только оно понимает, что «адрес модели» без
    /// «отвечать моделью» ничего не значит. Оболочка лишь показывает это.
    /// </remarks>
    private void ApplyDependency(string key, JsonObject spec, Grid row)
    {
        if (spec["depends_on"]?.GetValue<string>() is not { } master) return;
        var on = _values.GetValueOrDefault(master)?.GetValue<bool>() ?? false;
        row.IsEnabled = on;
        row.Opacity = on ? 1.0 : 0.5;
    }

    private static string Show(JsonNode? value) => value switch
    {
        null => "",
        JsonArray array => string.Join(", ",
            array.Select(v => v?.ToString() ?? "")),
        JsonObject => "…",
        _ => value.ToString(),
    };

    private static JsonNode? Parse(string text, string type) => type switch
    {
        "integer" => int.TryParse(text, out var i) ? i : null,
        "number" => double.TryParse(text, out var d) ? d : null,
        "array" => new JsonArray(text.Split(',')
            .Select(p => p.Trim()).Where(p => p.Length > 0)
            .Select(p => (JsonNode)p!).ToArray()),
        _ => text,
    };

    private async Task SaveAsync(string key, JsonNode? value)
    {
        if (value is null) { Note.Text = $"«{SettingsLayout.TitleOf(key)}»: не понял значение."; return; }

        var answer = await Ask(Methods.SettingsSet, new JsonObject
        {
            ["values"] = new JsonObject { [key] = value.DeepClone() },
        });
        if (answer?["verdicts"]?[key] is not JsonObject verdict) return;

        var accepted = verdict["accepted"]?.GetValue<bool>() ?? false;
        var message = verdict["message"]?.GetValue<string>() ?? "";
        var code = verdict["code"]?.GetValue<string>() ?? "";

        // Предупреждение не отказ: значение записано, а человеку сказано,
        // чем это обернётся.
        Note.Text = accepted && message.Length == 0
            ? $"«{SettingsLayout.TitleOf(key)}» сохранено."
            : message;
        Note.SetResourceReference(ForegroundProperty,
            accepted && code.Length == 0 ? "C.InkFaint" : "C.Signal");

        if (accepted)
        {
            _values[key] = value;
            if (key == "finish" && _link is not null)
                await _link.SetFinishAsync(value.GetValue<string>());
            // Смена движка меняет набор голосов: списки перечитываются, а не
            // остаются от прошлого движка.
            if (key is "tts_engine" or "stt_engine") await LoadOptionsAsync();
            Build();          // зависимости могли измениться
        }
    }

    private async Task<JsonObject?> Ask(string method, JsonObject? payload = null)
    {
        if (_link?.Connection is not { Ready: true } connection) return null;
        try
        {
            var answer = await connection.CallAsync(method, payload,
                                                    TimeSpan.FromSeconds(20));
            if (answer.IsError) { Note.Text = answer.ErrorMessage; return null; }
            return answer.Payload;
        }
        catch (Exception error) { Note.Text = error.Message; return null; }
    }
}
