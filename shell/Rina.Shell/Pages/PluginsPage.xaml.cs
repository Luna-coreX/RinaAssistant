using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using Rina.Protocol;

using static Rina.Shell.Strings.Loc;

namespace Rina.Shell.Pages;

/// <summary>
/// Плагины: что установлено, что включено и что плагин говорит о себе.
/// </summary>
/// <remarks>
/// <para>
/// Задача плана <c>4.0-F04</c>, последняя её часть.
/// </para>
/// <para>
/// <b>Страницу плагина рисует оболочка, а описывает плагин.</b> Это решение
/// 3.1.0 (<c>plugins/page_spec.py</c>), принятое ещё до разделения
/// процессов: плагин перестал возвращать готовый виджет и стал возвращать
/// список элементов. Тогда это было предусмотрительностью, сейчас — тем
/// единственным, благодаря чему страница плагина, написанного на Python,
/// рисуется в другом процессе на другом языке без единой правки в самом
/// плагине.
/// </para>
/// <para>
/// <b>Незнакомый элемент показывается, а не пропускается.</b> То же правило
/// с зубами, что и для незнакомой настройки в
/// [ADR 0006](../../../docs/adr/0006-settings-ownership.md): плагин
/// использовал элемент, которого оболочка не знает, — и молчаливый пропуск
/// сделал бы часть его страницы невидимой без единого следа.
/// </para>
/// <para>
/// <b>Сбойный плагин остаётся в списке.</b> Человек поставил его сам и
/// должен увидеть причину; исчезнувший плагин выглядит как «я его не
/// ставил».
/// </para>
/// </remarks>
public partial class PluginsPage : UserControl
{
    private readonly CoreLink? _link;
    private readonly Dictionary<string, string> _names = [];
    private string _open = "";

    /// <summary>Сколько плагинов показано — для сквозной проверки.</summary>
    public int PluginCount => Items.Children.Count;

    /// <summary>Сколько элементов на открытой странице плагина.</summary>
    public int PageElementCount => PageBody.Children.Count;

    /// <summary>Список получен и разложен.</summary>
    public event Action? Ready;

    public PluginsPage(CoreLink? link)
    {
        InitializeComponent();
        _link = link;

        if (_link is null)
        {
            Note.Text = S("Ядро не на связи — плагины недоступны.");
            return;
        }
        Loaded += async (_, _) => await LoadAsync();
    }

    /// <summary>
    /// Включить первый плагин со своей страницей и открыть её.
    /// </summary>
    /// <remarks>
    /// Для сквозной проверки: щёлкать по карточкам она не умеет, а пройти
    /// весь круг — список, включение, страница — обязана.
    ///
    /// <b>И вернуть как было.</b> Проверка идёт на настоящем ядре, то есть
    /// на настройках человека; оставить после себя включённые плагины она
    /// права не имеет. Ровно то же правило, по которому проверка автозапуска
    /// возвращает запись в реестре.
    /// </remarks>
    /// <returns>Сколько элементов было на странице, пока она была открыта.</returns>
    /// <param name="keepOpen">
    /// Оставить включённым и раскрытым. Нужно снимку: он делается **после**
    /// вызова, и вернуть всё как было значило бы снять пустой список.
    /// Настройки человека при этом всё равно возвращаются — включённым
    /// остаётся плагин, но не запись о нём.
    /// </param>
    public async Task<int> OpenFirstPageAsync(bool keepOpen = false)
    {
        var got = await Ask(Methods.PluginsList);
        if (got?["items"] is not JsonArray items) return 0;

        _wasEnabled = items.OfType<JsonObject>()
            .Where(p => p["enabled"]?.GetValue<bool>() == true)
            .Select(p => p["plugin_id"]?.GetValue<string>() ?? "")
            .ToHashSet();
        var wasEnabled = _wasEnabled;

        try
        {
            foreach (var plugin in items.OfType<JsonObject>())
            {
                var id = plugin["plugin_id"]?.GetValue<string>() ?? "";
                if (id.Length == 0 || plugin["broken"]?.GetValue<bool>() == true)
                    continue;

                // Страница есть только у включённого: выключенный плагин не
                // загружен, и спрашивать его не о чем.
                await SetEnabledAsync(id, true);
                var after = await Ask(Methods.PluginsList);
                var hasPage = after?["items"]?.AsArray()
                    .OfType<JsonObject>()
                    .FirstOrDefault(p => p["plugin_id"]?.GetValue<string>() == id)
                    ?["has_page"]?.GetValue<bool>() ?? false;
                if (!hasPage) continue;

                _open = id;
                await ShowPageAsync();
                // Считаем сейчас: возврат состояния ниже страницу закроет,
                // и спрашивать после было бы поздно.
                return PageElementCount;
            }
            return 0;
        }
        finally
        {
            // При `keepOpen` возврат откладывается до `RestoreAsync`: снимок
            // делается после, и вернуть состояние здесь значило бы снять
            // пустой список.
            var now = keepOpen ? null : await Ask(Methods.PluginsList);
            foreach (var plugin in now?["items"]?.AsArray()
                                   ?.OfType<JsonObject>() ?? [])
            {
                var id = plugin["plugin_id"]?.GetValue<string>() ?? "";
                if (plugin["enabled"]?.GetValue<bool>() == true
                    && !wasEnabled.Contains(id))
                    await SetEnabledAsync(id, false);
            }
        }
    }

    /// <summary>Какие плагины включены сейчас — для сквозной проверки.</summary>
    public async Task<string[]> EnabledAsync()
    {
        var now = await Ask(Methods.PluginsList);
        return (now?["items"]?.AsArray() ?? [])
            .OfType<JsonObject>()
            .Where(p => p["enabled"]?.GetValue<bool>() == true)
            .Select(p => p["plugin_id"]?.GetValue<string>() ?? "")
            .OrderBy(id => id, StringComparer.Ordinal)
            .ToArray();
    }

    /// <summary>Что было включено до того, как мы вмешались.</summary>
    private HashSet<string> _wasEnabled = [];

    /// <summary>
    /// Вернуть включённое как было.
    /// </summary>
    /// <remarks>
    /// Нужно снимку: он раскрывает страницу плагина, а значит включает
    /// плагин — и обязан выключить обратно. Настройки под проверкой
    /// настоящие, человеческие; то же правило, по которому проверка
    /// автозапуска возвращает запись в реестре.
    /// </remarks>
    public async Task RestoreAsync()
    {
        _open = "";
        var now = await Ask(Methods.PluginsList);
        foreach (var plugin in now?["items"]?.AsArray()
                               ?.OfType<JsonObject>() ?? [])
        {
            var id = plugin["plugin_id"]?.GetValue<string>() ?? "";
            if (plugin["enabled"]?.GetValue<bool>() == true
                && !_wasEnabled.Contains(id))
                await SetEnabledAsync(id, false);
        }
    }

    private async Task LoadAsync()
    {
        var got = await Ask(Methods.PluginsList);
        if (got?["items"] is not JsonArray items) return;

        Items.Children.Clear();
        foreach (var item in items.OfType<JsonObject>())
        {
            var id = item["plugin_id"]?.GetValue<string>() ?? "";
            if (id.Length > 0)
                _names[id] = item["name"]?.GetValue<string>() ?? id;
            Items.Children.Add(BuildRow(item));
        }

        Empty.Visibility = items.Count == 0 ? Visibility.Visible
                                            : Visibility.Collapsed;
        Legend.Text = items.Count == 0 ? S("УСТАНОВЛЕННЫЕ")
                                       : S("УСТАНОВЛЕННЫЕ · {0}", items.Count);
        Ready?.Invoke();
    }

    private UIElement BuildRow(JsonObject plugin)
    {
        var id = plugin["plugin_id"]?.GetValue<string>() ?? "";
        var broken = plugin["broken"]?.GetValue<bool>() ?? false;
        var enabled = plugin["enabled"]?.GetValue<bool>() ?? false;
        var hasPage = plugin["has_page"]?.GetValue<bool>() ?? false;

        var card = new Border
        {
            Style = (Style)FindResource("Card"),
            Margin = new Thickness(0, 0, 0, 6),
        };
        var row = new Grid();
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });

        var icon = new TextBlock
        {
            Text = plugin["icon"]?.GetValue<string>() ?? "🧩",
            FontSize = 20,
            VerticalAlignment = VerticalAlignment.Center,
            Margin = new Thickness(0, 0, 12, 0),
        };
        Grid.SetColumn(icon, 0);
        row.Children.Add(icon);

        var about = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        about.Children.Add(new TextBlock
        {
            Text = plugin["name"]?.GetValue<string>() ?? id,
            Style = (Style)FindResource("Text.Body"),
        });

        // Сбой — вместо описания, а не рядом с ним: причина важнее того,
        // что плагин о себе рассказывал, когда работал.
        var note = broken
            ? plugin["error"]?.GetValue<string>() ?? S("плагин не загрузился")
            : Describe(plugin);
        about.Children.Add(new TextBlock
        {
            Text = note,
            Style = (Style)FindResource("Text.Meta"),
            TextWrapping = TextWrapping.Wrap,
            Margin = new Thickness(0, 2, 0, 0),
            Foreground = broken ? (System.Windows.Media.Brush)FindResource("C.Signal")
                                : (System.Windows.Media.Brush)FindResource("C.InkFaint"),
        });
        Grid.SetColumn(about, 1);
        row.Children.Add(about);

        if (hasPage && enabled)
        {
            var open = new Button
            {
                Style = (Style)FindResource("Btn"),
                Content = _open == id ? S("Скрыть") : S("Открыть"),
                Margin = new Thickness(0, 0, 8, 0),
                VerticalAlignment = VerticalAlignment.Center,
            };
            open.Click += async (_, _) =>
            {
                _open = _open == id ? "" : id;
                await ShowPageAsync();
                await LoadAsync();          // подписи кнопок изменились
            };
            Grid.SetColumn(open, 2);
            row.Children.Add(open);
        }

        var toggle = new CheckBox
        {
            Style = (Style)FindResource("Toggle"),
            IsChecked = enabled,
            // Сбойный включить нельзя: включение ничего не изменит, а
            // переключатель, возвращающийся обратно, выглядит поломкой.
            IsEnabled = !broken,
            VerticalAlignment = VerticalAlignment.Center,
        };
        toggle.Click += async (_, _) => await SetEnabledAsync(id, toggle.IsChecked == true);
        Grid.SetColumn(toggle, 3);
        row.Children.Add(toggle);

        card.Child = row;
        return card;
    }

    private static string Describe(JsonObject plugin)
    {
        var parts = new List<string>();
        var description = plugin["description"]?.GetValue<string>() ?? "";
        if (description.Length > 0) parts.Add(description);
        var version = plugin["version"]?.GetValue<string>() ?? "";
        if (version.Length > 0) parts.Add(S("версия {0}", version));
        var author = plugin["author"]?.GetValue<string>() ?? "";
        if (author.Length > 0 && author != "unknown") parts.Add(author);
        return string.Join(" · ", parts);
    }

    private async Task SetEnabledAsync(string id, bool enabled)
    {
        var answer = await Ask(Methods.PluginsSetEnabled, new JsonObject
        {
            ["plugin_id"] = id,
            ["enabled"] = enabled,
        });
        if (answer?["plugin"] is not JsonObject plugin) return;

        // Ядро вернуло состояние **после** изменения: плагин мог отказаться
        // загружаться, и «включено» было бы неправдой.
        var now = plugin["enabled"]?.GetValue<bool>() ?? false;
        var shown = plugin["name"]?.GetValue<string>() ?? id;
        Note.Text = now == enabled
            ? (now ? S("«{0}» включён.", shown) : S("«{0}» выключен.", shown))
            : S("«{0}» не включился: {1}", shown,
                plugin["error"]?.GetValue<string>() ?? "");
        Note.SetResourceReference(ForegroundProperty,
                                  now == enabled ? "C.InkFaint" : "C.Signal");

        if (!now && _open == id) _open = "";
        await ShowPageAsync();
        await LoadAsync();
    }

    /// <summary>Показать страницу открытого плагина.</summary>
    private async Task ShowPageAsync()
    {
        PageBody.Children.Clear();
        if (_open.Length == 0)
        {
            PageBox.Visibility = Visibility.Collapsed;
            return;
        }

        var got = await Ask(Methods.PluginsPage, new JsonObject
        {
            ["plugin_id"] = _open,
        });
        Draw(got);
    }

    private void Draw(JsonObject? page)
    {
        PageBody.Children.Clear();
        if (page?["elements"] is not JsonArray elements)
        {
            PageBox.Visibility = Visibility.Collapsed;
            return;
        }

        PageBox.Visibility = Visibility.Visible;
        // Имя, а не номер: «NOTES» — то, как плагин называется в файловой
        // системе, а человек знает его как «Заметки».
        PageLegend.Text = (_names.GetValueOrDefault(_open) ?? _open)
            .ToUpperInvariant();
        foreach (var element in elements.OfType<JsonObject>())
            PageBody.Children.Add(BuildElement(element, depth: 0));
    }

    /// <summary>
    /// Докуда рендерер спускается по вложенности.
    /// </summary>
    /// <remarks>
    /// То же число, что в <c>plugins/page_spec.py</c>. Ограничение не про
    /// красоту: описание страницы приходит из другого процесса, и «сколько
    /// угодно вложенных карточек» — способ занять оболочку рисованием
    /// вместо ответа человеку.
    /// </remarks>
    private const int MaxDepth = 4;

    /// <summary>Сколько элементов нарисовано — для сквозной проверки.</summary>
    public int DrawnElements { get; private set; }

    /// <summary>
    /// Содержимое контейнера.
    /// </summary>
    /// <remarks>
    /// Пустой контейнер не рисуется вовсе: карточка без содержимого — это
    /// рамка вокруг ничего, и выглядит она как поломка, которой нет.
    /// </remarks>
    private List<FrameworkElement> BuildChildren(JsonObject element, int depth)
    {
        var made = new List<FrameworkElement>();
        if (element["children"] is not JsonArray children) return made;
        foreach (var child in children.OfType<JsonObject>())
            made.Add(BuildElement(child, depth + 1));
        return made;
    }

    /// <summary>
    /// Один элемент описания страницы.
    /// </summary>
    /// <remarks>
    /// Виды взяты из <c>plugins/page_spec.py</c>. Незнакомый вид не
    /// пропускается: плагин что-то сказал, и оболочка обязана это показать,
    /// даже если не знает как, — иначе часть страницы исчезнет без следа.
    /// </remarks>
    private FrameworkElement BuildElement(JsonObject element, int depth)
    {
        var kind = element["kind"]?.GetValue<string>() ?? "";
        var text = element["text"]?.GetValue<string>() ?? "";
        DrawnElements++;

        // Глубже не спускаемся, и говорим об этом вслух: молча обрезанная
        // страница выглядит как страница, которую плагин так и задумал.
        if (depth >= MaxDepth)
            return new TextBlock
            {
                Text = S("[слишком глубокая вложенность]"),
                Style = (Style)FindResource("Text.Meta"),
            };

        switch (kind)
        {
            // --- контейнеры (схема версии 2, 4.0-H01) ---
            case "card":
                var inside = BuildChildren(element, depth);
                if (inside.Count == 0) return Nothing();
                var card = new Border
                {
                    Style = (Style)FindResource("Card"),
                    Margin = new Thickness(0, 0, 0, 8),
                };
                var body = new StackPanel();
                if (text.Length > 0)
                    body.Children.Add(new TextBlock
                    {
                        Text = text,
                        Style = (Style)FindResource("Text.Body"),
                        Margin = new Thickness(0, 0, 0, 6),
                    });
                foreach (var one in inside) body.Children.Add(one);
                card.Child = body;
                return card;

            case "group":
                var members = BuildChildren(element, depth);
                if (members.Count == 0) return Nothing();
                var group = new StackPanel { Margin = new Thickness(0, 0, 0, 16) };
                if (text.Length > 0)
                    group.Children.Add(new TextBlock
                    {
                        Text = text.ToUpperInvariant(),
                        Style = (Style)FindResource("Text.Section"),
                        Margin = new Thickness(0, 0, 0, 8),
                    });
                foreach (var one in members) group.Children.Add(one);
                return group;

            case "row":
                var side = BuildChildren(element, depth);
                if (side.Count == 0) return Nothing();
                // «Рядом» — просьба, а не приказ: `WrapPanel` сам поставит
                // содержимое столбиком, когда рядом уже не помещается.
                var row = new WrapPanel
                {
                    Orientation = Orientation.Horizontal,
                    Margin = new Thickness(0, 0, 0, 6),
                };
                foreach (var one in side)
                {
                    one.Margin = new Thickness(0, 0, 8, 6);
                    row.Children.Add(one);
                }
                return row;

            case "title":
                return new TextBlock
                {
                    Text = text,
                    Style = (Style)FindResource("Text.Body"),
                    Margin = new Thickness(0, 0, 0, 8),
                };

            case "text":
                return new TextBlock
                {
                    Text = text,
                    Style = (Style)FindResource("Text.Body"),
                    TextWrapping = TextWrapping.Wrap,
                    Margin = new Thickness(0, 0, 0, 6),
                };

            case "note":
                return new TextBlock
                {
                    Text = text,
                    Style = (Style)FindResource("Text.Meta"),
                    TextWrapping = TextWrapping.Wrap,
                    Margin = new Thickness(0, 0, 0, 6),
                };

            case "divider":
                return new Border
                {
                    Height = 1,
                    Margin = new Thickness(0, 10, 0, 10),
                    Background = (System.Windows.Media.Brush)FindResource("C.Seam"),
                };

            case "items":
                var list = new StackPanel { Margin = new Thickness(0, 0, 0, 6) };
                foreach (var one in element["items"]?.AsArray()
                                    ?? new JsonArray())
                    list.Children.Add(new TextBlock
                    {
                        Text = "· " + (one?.GetValue<string>() ?? ""),
                        Style = (Style)FindResource("Text.Body"),
                        TextWrapping = TextWrapping.Wrap,
                        Margin = new Thickness(0, 2, 0, 0),
                    });
                return list;

            case "button":
                var danger = element["variant"]?.GetValue<string>() == "danger";
                var button = new Button
                {
                    Style = (Style)FindResource(danger ? "Btn.Danger" : "Btn"),
                    Content = text,
                    HorizontalAlignment = HorizontalAlignment.Left,
                    Margin = new Thickness(0, 6, 0, 0),
                };
                var action = element["action"]?.GetValue<string>() ?? "";
                button.Click += async (_, _) => await ActAsync(action);
                return button;

            case "input":
                var typed = new TextBox
                {
                    Style = (Style)FindResource("Field"),
                    Width = 220,
                    Text = element["value"]?.GetValue<string>() ?? "",
                    // Подсказка внутри поля — это подсказка, а не значение:
                    // введённое пустым не отправляется вовсе.
                    Tag = text,
                };
                var send = new Button
                {
                    Style = (Style)FindResource("Btn"),
                    Content = element["variant"]?.GetValue<string>() is
                              { Length: > 0 } label ? label : S("Готово"),
                    Margin = new Thickness(8, 0, 0, 0),
                };
                var typedAction = element["action"]?.GetValue<string>() ?? "";
                async Task SendAsync()
                {
                    var written = typed.Text.Trim();
                    if (written.Length == 0) return;
                    typed.Clear();
                    await ActAsync(typedAction, written);
                }
                send.Click += async (_, _) => await SendAsync();
                // Enter — то же, что нажать кнопку: человек, набравший
                // строку, жмёт Enter, а не ищет глазами кнопку.
                typed.KeyDown += async (_, key) =>
                {
                    if (key.Key == System.Windows.Input.Key.Return)
                        await SendAsync();
                };
                var field = new StackPanel
                {
                    Orientation = Orientation.Horizontal,
                    Margin = new Thickness(0, 4, 0, 4),
                };
                field.Children.Add(typed);
                field.Children.Add(send);
                return field;

            case "badge":
                // Метка состояния. Цвет здесь решает оболочка: плагин
                // сказал «предупреждение», а не «оранжевый».
                var tone = element["variant"]?.GetValue<string>() ?? "normal";
                return new Border
                {
                    Background = (System.Windows.Media.Brush)FindResource(
                        tone is "danger" or "warn" ? "C.Signal" : "C.FaceHigh"),
                    CornerRadius = new CornerRadius(10),
                    Padding = new Thickness(10, 3, 10, 3),
                    HorizontalAlignment = HorizontalAlignment.Left,
                    Margin = new Thickness(0, 2, 0, 2),
                    Child = new TextBlock
                    {
                        Text = text,
                        Style = (Style)FindResource("Text.Meta"),
                        Foreground = (System.Windows.Media.Brush)FindResource(
                            tone is "danger" or "warn" ? "C.Face" : "C.Ink"),
                    },
                };

            case "progress":
                var done = element["value"]?.GetValue<double>() ?? 0;
                var bar = new StackPanel { Margin = new Thickness(0, 4, 0, 6) };
                if (text.Length > 0)
                    bar.Children.Add(new TextBlock
                    {
                        Text = text,
                        Style = (Style)FindResource("Text.Meta"),
                        Margin = new Thickness(0, 0, 0, 4),
                    });
                var track = new Border
                {
                    Background = (System.Windows.Media.Brush)FindResource("C.FaceSunk"),
                    CornerRadius = new CornerRadius(3),
                    Height = 6,
                    Width = 240,
                    HorizontalAlignment = HorizontalAlignment.Left,
                };
                track.Child = new Border
                {
                    Background = (System.Windows.Media.Brush)FindResource("C.Signal"),
                    CornerRadius = new CornerRadius(3),
                    Width = Math.Max(0, Math.Min(1, done)) * 240,
                    HorizontalAlignment = HorizontalAlignment.Left,
                };
                bar.Children.Add(track);
                return bar;

            case "table":
                var grid = new Grid { Margin = new Thickness(0, 4, 0, 8) };
                var rows = element["items"]?.AsArray() ?? [];
                var headers = element["value"]?.AsArray();
                var width = Math.Max(
                    headers?.Count ?? 0,
                    rows.OfType<JsonArray>().Select(r => r.Count)
                        .DefaultIfEmpty(0).Max());
                if (width == 0) return Nothing();

                for (var column = 0; column < width; column++)
                    grid.ColumnDefinitions.Add(new ColumnDefinition
                    {
                        Width = new GridLength(1, GridUnitType.Star),
                    });

                var line = 0;
                if (headers is not null && headers.Count > 0)
                {
                    grid.RowDefinitions.Add(new RowDefinition
                    {
                        Height = GridLength.Auto,
                    });
                    for (var column = 0; column < headers.Count; column++)
                    {
                        var head = new TextBlock
                        {
                            Text = headers[column]?.GetValue<string>() ?? "",
                            Style = (Style)FindResource("Text.Section"),
                            Margin = new Thickness(0, 0, 8, 4),
                        };
                        Grid.SetRow(head, 0);
                        Grid.SetColumn(head, column);
                        grid.Children.Add(head);
                    }
                    line = 1;
                }

                foreach (var one in rows.OfType<JsonArray>())
                {
                    grid.RowDefinitions.Add(new RowDefinition
                    {
                        Height = GridLength.Auto,
                    });
                    for (var column = 0; column < one.Count; column++)
                    {
                        var cell = new TextBlock
                        {
                            Text = one[column]?.GetValue<string>() ?? "",
                            Style = (Style)FindResource("Text.Body"),
                            Margin = new Thickness(0, 0, 8, 2),
                            TextTrimming = TextTrimming.CharacterEllipsis,
                        };
                        Grid.SetRow(cell, line);
                        Grid.SetColumn(cell, column);
                        grid.Children.Add(cell);
                    }
                    line++;
                }
                return grid;

            default:
                // Незнакомый вид показывается заметно и с именем: плагин
                // собран под схему новее оболочки, и молчаливый пропуск
                // сделал бы часть его страницы невидимой без следа. Чинят
                // некрасивое; незаметное не чинят.
                return new TextBlock
                {
                    Text = $"[{kind}] {text}",
                    Style = (Style)FindResource("Text.Meta"),
                    TextWrapping = TextWrapping.Wrap,
                    ToolTip = S("оболочка не знает такого элемента страницы"),
                };
        }
    }

    /// <summary>Ничего не рисуем: пустой контейнер — рамка вокруг ничего.</summary>
    private static FrameworkElement Nothing()
        => new StackPanel { Visibility = Visibility.Collapsed };

    private async Task ActAsync(string action, string? value = null)
    {
        var payload = new JsonObject
        {
            ["plugin_id"] = _open,
            ["action"] = action,
        };
        if (value is not null) payload["value"] = value;
        var got = await Ask(Methods.PluginsAction, payload);
        // Ответ несёт новую страницу: кнопка меняет то, что нарисовано
        // рядом с ней, и спрашивать второй раз значило бы показать её
        // устаревшей ровно на один круг.
        Draw(got);
    }

    private async Task<JsonObject?> Ask(string method, JsonObject? payload = null)
    {
        if (_link?.Connection is not { Ready: true } connection) return null;
        if (!connection.MayCall(method))
        {
            Note.Text = S("Ядро не объявило возможность «плагины».");
            return null;
        }
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
