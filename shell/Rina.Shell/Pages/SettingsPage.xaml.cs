using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

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

    /// <summary>
    /// Ширины всех органов управления — для проверки столбца.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Ширину задаёт колонка, а не орган. Проверялось это глазами и одним
    /// человеком со скриншотами: поле пути было шириной 200, выпадающий
    /// список 280, ползунок с числом 276, и правый край гулял на
    /// восемьдесят точек.
    /// </para>
    /// <para>
    /// По снимку такое не померить: правый край колонки не является
    /// границей цвета — у ряда с путём справа кнопка, у ползунка число, и
    /// заливка кончается раньше самой колонки. Поэтому меряется дерево, а
    /// не картинка.
    /// </para>
    /// <para>
    /// Переключатели и кнопки-приборы сюда не входят: они не занимают
    /// колонку, а стоят у её левого края — им ширина колонки ни к чему.
    /// </para>
    /// </remarks>
    public IReadOnlyList<(string Key, double Width)> ControlWidths()
    {
        var found = new List<(string, double)>();
        foreach (var (key, editor) in _editors)
        {
            if (editor is CheckBox) continue;        // переключатель
            if (double.IsNaN(editor.Width)) continue; // растущий по месту
            found.Add((key, editor.Width));
        }
        return found;
    }

    /// <summary>Какой ширины обязан быть орган управления.</summary>
    public static double WantedControlWidth => ControlWidth;

    /// <summary>Готово: схема получена и разложена.</summary>
    public event Action? Ready;

    public SettingsPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;

        // Просвет берётся из токена, а не набирается числом: «вдвое больше
        // обычного» — это `Sp.Danger`, и второе место, где написано 64,
        // однажды разошлось бы с первым.
        Bottom.Margin = new Thickness(0, (double)FindResource("Sp.Danger"),
                                      0, 0);

        if (_link is null)
        {
            Note.Text = S("Ядро не на связи — настройки недоступны.");
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

            if (key == "accent")
            {
                // Варианты — те, что есть у выбранной сейчас отделки.
                var finish = _values.GetValueOrDefault("finish")
                                 ?.GetValue<string>() ?? "black";
                _options[key] = App.Accents(finish)
                    .Select(a => (a.Value, a.Title, true)).ToList();
                continue;
            }

            var devices = key == "input_device"
                ? Audio.Microphone.Devices()
                : Audio.Speaker.Devices();
            var listed = new List<(string, string, bool)>
            {
                ("default", S("Устройство по умолчанию"), true),
            };
            listed.AddRange(devices.Select(d => (d.Name, d.Name, true)));
            _options[key] = listed;
        }

        // Чему можно назначить сочетание — у ядра: исполняет действия оно,
        // и список у него. Без этого словарь падал в общий редактор и
        // показывал «записей: 0» вместо перечня действий.
        if (_schema.ContainsKey("action_hotkeys"))
        {
            var listed = await Ask(Methods.HotkeysActions);
            var actions = (listed?["items"]?.AsArray().OfType<JsonObject>()
                           ?? [])
                .Select(a => (a["value"]?.GetValue<string>() ?? "",
                              a["title"]?.GetValue<string>() ?? "",
                              true))
                .Where(a => a.Item1.Length > 0)
                .ToList();
            if (actions.Count > 0) _options["action_hotkeys"] = actions;
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
            // Переводим здесь: в раскладке лежит ключ (см. SettingsLayout).
            Text = S(title).ToUpperInvariant(),
            Style = (Style)FindResource("Text.Section"),
            Margin = new Thickness(0, 0, 0, 12),
        });
        foreach (var key in keys) stack.Children.Add(BuildRow(key));
        return stack;
    }

    /// <summary>
    /// Ширина колонки органов управления.
    /// </summary>
    /// <remarks>
    /// Одна на всю страницу. Раньше колонка была «по содержимому», и
    /// каждый ряд начинал орган там, где кончалась его подпись, — правый
    /// край рвался, а панель читалась как список, а не как прибор.
    /// </remarks>
    private const double ControlColumn = 296;

    /// <summary>
    /// Ширина самого органа управления внутри колонки.
    /// </summary>
    /// <remarks>
    /// Одна на все виды: выпадающий список, поле, путь, ползунок с числом.
    /// Раньше каждый носил свою — 280, 200, 276, — и правый край гулял на
    /// восемьдесят точек. У прибора органы стоят в столбец, а столбец
    /// имеет две стороны, а не одну.
    /// </remarks>
    private const double ControlWidth = 280;

    /// <summary>Ширина колонки проверок. Пустая у большинства рядов.</summary>
    private const double ProbeColumn = 150;

    private UIElement BuildRow(string key)
    {
        var spec = _schema[key];
        var row = new Grid { MinHeight = 40 };
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(1, GridUnitType.Star),
        });
        // Колонка органов управления одной ширины на всю страницу: иначе
        // каждый ряд начинается там, где кончился его собственный, и
        // правый край рвётся. У лицевой панели органы стоят в столбец.
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(ControlColumn),
        });
        // Третья колонка — для проверки, и она **тоже одной ширины на все
        // ряды**. С «по содержимому» ряд с кнопкой отбирал место у своей
        // подписи, и его орган уезжал левее соседних: колонки принадлежат
        // панели, а не ряду.
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(ProbeColumn),
        });

        var label = new StackPanel
        {
            VerticalAlignment = VerticalAlignment.Center,
            // Просвет между легендой и органом. Без него подсказка
            // упиралась в поле, и две колонки читались как одна.
            Margin = new Thickness(0, 0, 24, 0),
        };
        label.Children.Add(new TextBlock
        {
            Text = SettingsLayout.TitleOf(key),
            Style = (Style)FindResource("Text.Body"),
        });

        var notes = new List<string>();
        if (SettingsLayout.HintOf(key).Length > 0)
            notes.Add(SettingsLayout.HintOf(key));
        if (spec["restart_required"] is not null)
            notes.Add(S("применится после перезапуска"));
        if (!SettingsLayout.Known.Contains(key))
            notes.Add(S("ключ {0} оболочке незнаком", key));
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

        // Проверка стоит рядом, но в своей колонке.
        if (BuildProbe(key) is { } probe)
        {
            Grid.SetColumn(probe, 2);
            probe.VerticalAlignment = VerticalAlignment.Center;
            probe.Margin = new Thickness(8, 0, 0, 0);
            row.Children.Add(probe);
        }

        // Редактор-список встаёт под подписью во всю ширину. Рядом ему
        // тесно: подпись сжимается в столбик из букв, а сам он всё равно
        // не помещается. Признак — устройство значения, а не имя ключа:
        // новая настройка того же рода получит это сама.
        var type = spec["type"]?.GetValue<string>() ?? "string";
        if (type is "array" or "object")
        {
            row.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            row.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            Grid.SetRow(editor, 1);
            Grid.SetColumn(editor, 0);
            Grid.SetColumnSpan(editor, 2);
            editor.HorizontalAlignment = HorizontalAlignment.Left;
            editor.Margin = new Thickness(0, 8, 0, 0);
        }
        else
        {
            Grid.SetColumn(editor, 1);
            // Влево внутри своей колонки, а не вправо по краю окна: общий
            // левый край и делает из органов столбец.
            editor.HorizontalAlignment = HorizontalAlignment.Left;
            editor.VerticalAlignment = VerticalAlignment.Center;
        }
        row.Children.Add(editor);

        ApplyDependency(key, spec, row);

        // Волосяной шов между настройками — то же средство, что и в
        // списках: области панели отделяются значением и швом, а не
        // пустотой между плитками.
        return new Border
        {
            BorderBrush = (System.Windows.Media.Brush)FindResource("C.Seam"),
            BorderThickness = new Thickness(0, 0, 0, 1),
            Padding = new Thickness(0, 8, 0, 10),
            Child = row,
        };
    }

    /// <summary>
    /// Проверка рядом с настройкой, которую она проверяет.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Настройка звука без проверки — выбор вслепую: человек ставит движок,
    /// голос и устройство, а узнаёт, работает ли, при следующем обращении к
    /// Рине. Поэтому кнопка стоит здесь, а не в отдельной «диагностике»,
    /// куда никто не ходит.
    /// </para>
    /// <para>
    /// Голос проверяет ядро — синтезирует оно; микрофон оболочка — устройства
    /// у неё. Та же граница, что и везде (ADR 0009).
    /// </para>
    /// </remarks>
    private FrameworkElement? BuildProbe(string key)
    {
        if (key is not ("voice" or "input_device")) return null;

        var probe = new Button
        {
            Style = (Style)FindResource("Btn"),
            Content = key == "voice" ? S("Проверить голос")
                                     : S("Проверить микрофон"),
            Margin = new Thickness(8, 0, 0, 0),
            VerticalAlignment = VerticalAlignment.Center,
        };
        probe.Click += async (_, _) =>
        {
            probe.IsEnabled = false;
            try
            {
                if (key == "voice") await TestVoiceAsync();
                else await TestMicrophoneAsync();
            }
            finally { probe.IsEnabled = true; }
        };
        return probe;
    }

    /// <summary>Сказать пробную фразу и услышать её.</summary>
    private async Task TestVoiceAsync()
    {
        Note.Text = S("Говорю…");
        Note.SetResourceReference(ForegroundProperty, "C.InkFaint");

        var answer = await Ask(Methods.SpeechTest);
        if (answer is null) return;

        var ok = answer["ok"]?.GetValue<bool>() ?? false;
        // Сказать «получилось» мало: человек мог не услышать, и тогда дело
        // не в синтезе, а в устройстве вывода. Поэтому и длительность.
        Note.Text = ok
            ? S("Сказала: «{0}» — {1} с. Не слышно? Проверьте динамик.",
                answer["text"]?.GetValue<string>() ?? "",
                answer["seconds"]?.GetValue<double>() ?? 0)
            : S("Не вышло: {0}", answer["reason"]?.GetValue<string>() ?? "");
        Note.SetResourceReference(ForegroundProperty,
                                  ok ? "C.InkFaint" : "C.Signal");
    }

    /// <summary>
    /// Послушать микрофон пару секунд и сказать, что слышно.
    /// </summary>
    /// <remarks>
    /// Проверяется <b>уровень</b>, а не распознавание: «слышно ли вас
    /// вообще» и «понимает ли она слова» — разные вопросы, и первый
    /// отвечает на большинство жалоб. Заодно проверка работает и там, где
    /// распознавание выключено.
    /// </remarks>
    private async Task TestMicrophoneAsync()
    {
        var device = _values.GetValueOrDefault("input_device")
                         ?.GetValue<string>() ?? "default";
        Note.Text = S("Слушаю две секунды — скажите что-нибудь…");
        Note.SetResourceReference(ForegroundProperty, "C.InkFaint");

        var (ok, loudest, reason) = await Audio.Microphone.ProbeAsync(
            device, TimeSpan.FromSeconds(2));

        if (!ok)
        {
            Note.Text = S("Микрофон не отозвался: {0}", reason);
            Note.SetResourceReference(ForegroundProperty, "C.Signal");
            return;
        }

        // Порог из опыта: ниже пяти процентов — это тишина комнаты, а не
        // голос. Точное число тут менее важно, чем то, что человеку
        // сказано, что делать дальше.
        var heard = loudest >= 0.05f;
        Note.Text = heard
            ? S("Слышно: {0}%. Микрофон работает.", (int)(loudest * 100))
            // Одной строкой, а не склейкой: склеенная переводится по
            // кускам, и в таблице оказываются два обрывка вместо фразы.
            : S("Почти тихо: {0}%. Проверьте, тот ли микрофон выбран.",
                (int)(loudest * 100));
        Note.SetResourceReference(ForegroundProperty,
                                  heard ? "C.InkFaint" : "C.Signal");
    }

    private FrameworkElement BuildEditor(string key, JsonObject spec)
    {
        var type = spec["type"]?.GetValue<string>() ?? "string";
        var value = _values.GetValueOrDefault(key);

        // Порядок разбора — от устройства значения к его набору, а не
        // наоборот. Список и словарь правят по-своему, что бы ядро о них
        // ни перечислило: у «сочетаний действий» перечислены **ключи**
        // словаря, и прочитать его как строку значит уронить страницу —
        // ровно это и случилось при первом же живом прогоне.
        // Сочетание клавиш нажимают, а не набирают: набранное строкой —
        // это просьба знать, как мы его пишем, и ошибку человек заметит
        // только по тому, что клавиши не работают.
        if (key == "hotkey")
        {
            var box = new HotkeyBox(value?.GetValue<string>() ?? "");
            box.Changed += async written => await SaveAsync(key, written);
            return box;
        }

        // Число, у которого ядро назвало обе границы, тянут, а не
        // набирают. Правило общее, а не список ключей: настройка, у
        // которой границы появятся, получит ползунок сама.
        if (type is "integer" or "number"
            && spec["low"] is not null && spec["high"] is not null)
        {
            var low = spec["low"]!.GetValue<double>();
            var high = spec["high"]!.GetValue<double>();
            // Слишком широкий диапазон мышью не выставить: секунду из
            // шестисот придётся ловить. Такое остаётся полем.
            if (high - low <= 200)
                return BuildSlider(key, low, high, type == "integer",
                                   value?.GetValue<double>() ?? low);
        }

        if (type == "array")
            // У списка папок есть и тип «массив», и формат «путь». Массив
            // решает, чем правят; формат — чем добавляют.
            return BuildList(key, value as JsonArray,
                             spec["format"]?.GetValue<string>() ?? "");

        // Словарь, у которого ядро перечислило ключи, — это не «счётчик и
        // забыть все», а список: каждому известному действию своя строка.
        if (type == "object")
            return _options.TryGetValue(key, out var actions)
                   && actions.Count > 0
                ? BuildAssignments(key, actions, value as JsonObject)
                : BuildMap(key, value as JsonObject);

        // Список известных значений — выпадающий список, а не строка.
        // Набор пришёл от того, кто его знает: от ядра или от оболочки.
        if (_options.TryGetValue(key, out var known))
            return known.Count > 0
                ? BuildChoice(key, known, value?.GetValue<string>() ?? "")
                : Nothing();

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
                Width = ControlWidth,
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
            Width = ControlWidth,
            Text = Show(value),
        };
        Styles.Ui.SetHint(field, SettingsLayout.HintInField(key));
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
            Width = ControlWidth,
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
                Content = S("{0} — сейчас недоступно", current),
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
            Width = ControlWidth,
            IsEnabled = false,
        };
        box.Items.Add(new ComboBoxItem { Content = S("выбирать не из чего") });
        box.SelectedIndex = 0;
        return box;
    }

    /// <summary>
    /// Ползунок со значением рядом.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Число видно всегда: ползунок отвечает на «примерно сколько», а на
    /// «ровно сколько» не отвечает, и человек, которому нужно ровно
    /// восемьдесят, иначе обречён возить мышью.
    /// </para>
    /// <para>
    /// <b>Сохраняем не на каждое движение, а когда отпустили.</b> Иначе
    /// протаскивание от нуля до ста — это сто запросов к ядру и сто
    /// записей на диск.
    /// </para>
    /// </remarks>
    private FrameworkElement BuildSlider(string key, double low, double high,
                                         bool whole, double current)
    {
        // Та же сетка, что у пути: дорожка занимает остаток, число стоит у
        // правого края колонки. Раньше дорожка носила свою ширину, и число
        // оказывалось то ближе, то дальше от края.
        var row = new Grid
        {
            Width = ControlWidth,
            VerticalAlignment = VerticalAlignment.Center,
        };
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(1, GridUnitType.Star),
        });
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });

        var slider = new Slider
        {
            Style = (Style)FindResource("Slide"),
            Minimum = low,
            Maximum = high,
            Value = Math.Clamp(current, low, high),
            IsSnapToTickEnabled = whole,
            TickFrequency = whole ? 1 : (high - low) / 20,
            SmallChange = whole ? 1 : (high - low) / 20,
            LargeChange = whole ? Math.Max(1, (high - low) / 10)
                                : (high - low) / 10,
        };

        var shown = new TextBlock
        {
            Style = (Style)FindResource("Text.Body"),
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(12, 0, 0, 0),
            MinWidth = 44,
            TextAlignment = TextAlignment.Right,
            Text = Format(slider.Value, whole),
        };

        slider.ValueChanged += (_, _) =>
            shown.Text = Format(slider.Value, whole);

        // Отпустили мышь или ушли с клавиатуры — тогда и сохраняем.
        slider.PreviewMouseUp += async (_, _) => await SaveSliderAsync(
            key, slider.Value, whole);
        slider.LostKeyboardFocus += async (_, _) => await SaveSliderAsync(
            key, slider.Value, whole);

        Grid.SetColumn(slider, 0);
        Grid.SetColumn(shown, 1);
        row.Children.Add(slider);
        row.Children.Add(shown);
        return row;
    }

    private static string Format(double value, bool whole)
        => whole ? ((int)Math.Round(value)).ToString()
                 : value.ToString("0.00");

    private async Task SaveSliderAsync(string key, double value, bool whole)
    {
        JsonNode node = whole ? (int)Math.Round(value)
                              : Math.Round(value, 2);
        // Не трогаем ядро, если значение то же: отпущенная без движения
        // мышь не повод писать на диск.
        if (_values.GetValueOrDefault(key)?.GetValue<double>() is { } was
            && Math.Abs(was - node.GetValue<double>()) < 1e-9)
            return;
        await SaveAsync(key, node);
    }

    /// <summary>Путь: поле и «Обзор…».</summary>
    private FrameworkElement BuildPath(string key, string format, string current)
    {
        // Сетка, а не строка: поле занимает всё, что осталось от кнопки, и
        // правый край совпадает с соседними органами.
        var row = new Grid { Width = ControlWidth };
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = new GridLength(1, GridUnitType.Star),
        });
        row.ColumnDefinitions.Add(new ColumnDefinition
        {
            Width = GridLength.Auto,
        });
        var field = new TextBox
        {
            Style = (Style)FindResource("Field"),
            Text = current,
            IsReadOnly = true,
            ToolTip = current,
        };
        Styles.Ui.SetHint(field, SettingsLayout.HintInField(key));
        var browse = new Button
        {
            Style = (Style)FindResource("Btn"),
            Content = S("Обзор…"),
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
        Grid.SetColumn(field, 0);
        Grid.SetColumn(browse, 1);
        row.Children.Add(field);
        row.Children.Add(browse);
        return row;
    }

    private static string? PickFolder()
    {
        var dialog = new Microsoft.Win32.OpenFolderDialog
        {
            Title = S("Где лежит модель"),
        };
        return dialog.ShowDialog() == true ? dialog.FolderName : null;
    }

    private static string? PickFile()
    {
        var dialog = new Microsoft.Win32.OpenFileDialog
        {
            Title = S("Выберите файл модели"),
            Filter = S("Модели (*.onnx;*.bin;*.pt)|*.onnx;*.bin;*.pt|Все файлы|*.*"),
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
        var stack = new StackPanel();

        foreach (var item in items)
        {
            var row = new StackPanel
            {
                Orientation = Orientation.Horizontal,
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
                Content = S("Убрать"),
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
            Margin = new Thickness(0, 4, 0, 0),
        };

        // Папку выбирают окном, слово набирают. Одна кнопка на оба случая
        // означала бы либо путь с опечаткой, либо выбор папки вместо слова.
        if (format == "folder")
        {
            var add = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Добавить папку…"),
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
                Width = 170,
                Margin = new Thickness(0, 0, 8, 0),
            };
            Styles.Ui.SetHint(typed, S("новое слово"));
            var add = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Добавить"),
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
    /// Назначения: строка на каждое известное действие.
    /// </summary>
    /// <remarks>
    /// «Записей: 0 · сбросить все» было честно ровно до тех пор, пока
    /// назначить сочетание было негде. Человек, увидевший счётчик, не
    /// узнает ни какие действия бывают, ни как к ним привязаться, — а
    /// список действий у ядра есть, и он его прислал.
    ///
    /// Сочетание <b>записывают нажатием</b>. Первая редакция набирала его
    /// строкой, и рядом стояло объяснение: перехват нажатия означал бы,
    /// что окно слушает клавиатуру целиком. Объяснение было неверным.
    /// <c>Hotkeys</c> избегает <b>глобального перехватчика</b> — того, что
    /// видит набранное в чужих окнах; поле, читающее нажатие, пока на нём
    /// фокус, получает те же события, которые окну и так приходят.
    /// </remarks>
    private FrameworkElement BuildAssignments(string key,
        List<(string Value, string Title, bool Available)> actions,
        JsonObject? current)
    {
        var stack = new StackPanel();
        var assigned = new JsonObject();
        foreach (var (name, _t, _a) in actions)
        {
            var combination = current?[name]?.GetValue<string>() ?? "";
            if (combination.Length > 0) assigned[name] = combination;
        }

        foreach (var (name, title, _) in actions)
        {
            var row = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 0, 0, 4),
            };
            row.Children.Add(new TextBlock
            {
                Text = title,
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Center,
                Width = 190,
                Margin = new Thickness(0, 0, 8, 0),
            });

            var box = new HotkeyBox(current?[name]?.GetValue<string>() ?? "");
            var action = name;
            box.Changed += async written =>
            {
                var next = new JsonObject();
                foreach (var (existing, node) in assigned)
                    if (existing != action && node is not null)
                        next[existing] = node.DeepClone();
                // Пустое — это «снять», а не «назначить пустоту»: ключ
                // убирается, а не остаётся с пустой строкой.
                if (written.Length > 0) next[action] = written;
                await SaveAsync(key, next);
            };
            row.Children.Add(box);
            stack.Children.Add(row);
        }
        return stack;
    }

    /// <summary>
    /// Словарь: что выучено, и как забыть одно или всё.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Первая редакция показывала только счётчик и «забыть все» — с доводом,
    /// что человек не помнит, какое слово к чему привязалось. Довод оказался
    /// половинчатым: <b>не помнит — значит, надо показать</b>. Человек,
    /// заметивший, что Рина открывает не тот «студио», хочет отвязать именно
    /// его, а не забыть заодно шесть верных соответствий.
    /// </para>
    /// <para>
    /// «Забыть все» остаётся: когда путаница общая, перебирать по одному —
    /// работа без причины.
    /// </para>
    /// </remarks>
    private FrameworkElement BuildMap(string key, JsonObject? current)
    {
        var stack = new StackPanel();

        foreach (var (word, bound) in current ?? [])
        {
            var line = new StackPanel
            {
                Orientation = Orientation.Horizontal,
                Margin = new Thickness(0, 0, 0, 2),
            };
            line.Children.Add(new TextBlock
            {
                Text = DescribeBinding(word, bound),
                Style = (Style)FindResource("Text.Meta"),
                VerticalAlignment = VerticalAlignment.Center,
                MaxWidth = 300,
                TextTrimming = TextTrimming.CharacterEllipsis,
                ToolTip = DescribeBinding(word, bound),
                Margin = new Thickness(0, 0, 8, 0),
            });
            var drop = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = S("Забыть"),
            };
            var forgotten = word;
            drop.Click += async (_, _) =>
            {
                var left = new JsonObject();
                foreach (var (other, value) in current ?? [])
                    if (other != forgotten)
                        left[other] = value?.DeepClone();
                await SaveAsync(key, left);
            };
            line.Children.Add(drop);
            stack.Children.Add(line);
        }

        var row = new StackPanel
        {
            Orientation = Orientation.Horizontal,
            Margin = new Thickness(0, 4, 0, 0),
        };
        row.Children.Add(new TextBlock
        {
            Text = S("записей: {0}", current?.Count ?? 0),
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
        stack.Children.Add(row);
        return stack;
    }

    /// <summary>
    /// «слово → чему привязано» человеческими словами.
    /// </summary>
    /// <remarks>
    /// У выученной программы хранится не только путь, но и имя — его и
    /// показываем: путь длиной в сто знаков не отвечает на вопрос, что это
    /// за программа. Сочетание действий хранит строку и показывается как
    /// есть.
    /// </remarks>
    private static string DescribeBinding(string word, JsonNode? bound)
    {
        var named = bound switch
        {
            JsonObject entry =>
                entry["name"]?.GetValue<string>()
                ?? entry["path"]?.GetValue<string>() ?? "",
            null => "",
            _ => bound.ToString(),
        };
        return named.Length > 0 ? $"«{word}» → {named}" : $"«{word}»";
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
        if (value is null) { Note.Text = S("«{0}»: не понял значение.",
                          SettingsLayout.TitleOf(key));
            return; }

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
            ? S("«{0}» сохранено.", SettingsLayout.TitleOf(key))
            : message;
        Note.SetResourceReference(ForegroundProperty,
            accepted && code.Length == 0 ? "C.InkFaint" : "C.Signal");

        if (accepted)
        {
            _values[key] = value;
            if (key == "finish" && _link is not null)
            {
                var finish = value.GetValue<string>();
                await _link.SetFinishAsync(finish);
                // Отделка сменилась — акцент перевыбирается вместе с ней:
                // набор у каждой свой, и прежнее имя может в нём не
                // значиться. Имя при этом сохраняется, если значится.
                App.ApplyAccent(finish,
                    _values.GetValueOrDefault("accent")?.GetValue<string>()
                    ?? App.DefaultAccent);
                await LoadOptionsAsync();
            }
            if (key == "accent")
                App.ApplyAccent(
                    _values.GetValueOrDefault("finish")?.GetValue<string>()
                    ?? "black", value.GetValue<string>());

            // Язык хранится в ядре, но слова интерфейса переводит оболочка:
            // сказать ей об этом больше некому (ADR 0007).
            if (key == "ui_language")
                Strings.Loc.Use(value.GetValue<string>());

            // Переключатели оболочки применяются на месте: настройка,
            // ждущая перезапуска, читается как сломанная.
            if (key is "floating_command_bar" or "notifications"
                    or "minimize_to_tray" or "action_hotkeys"
                && System.Windows.Application.Current is App app)
                app.ApplyShellSetting(key, value);
            // Смена движка меняет набор голосов: списки перечитываются, а не
            // остаются от прошлого движка.
            if (key is "tts_engine" or "stt_engine") await LoadOptionsAsync();
            Build();          // зависимости могли измениться
        }
    }

    /// <summary>
    /// Сбросить настройки к умолчаниям — с подтверждением.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Спрашиваем, потому что отменить нельзя: прежние значения нигде не
    /// хранятся, и «ой, не то нажал» стоит человеку всех его настроек.
    /// </para>
    /// <para>
    /// В окне сказано, чего сброс <b>не</b> касается. Человек, нажимающий
    /// «сбросить настройки», боится потерять команды и историю — и должен
    /// увидеть, что они остаются, до нажатия, а не после.
    /// </para>
    /// </remarks>
    private async void OnReset(object sender, RoutedEventArgs e)
    {
        var ask = new ConfirmWindow(
            S("Все настройки вернутся к значениям по умолчанию: голос, устройства, сочетания клавиш, отделка, приватность."),
            S("Команды, история и плагины останутся на месте."),
            0);
        ask.ShowDialog();
        if (ask.Result != Consent.Granted) return;

        var answer = await Ask(Methods.SettingsReset);
        if (answer is null) return;

        Note.Text = S("Настройки сброшены.");
        Note.SetResourceReference(ForegroundProperty, "C.InkFaint");
        await LoadAsync();
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
