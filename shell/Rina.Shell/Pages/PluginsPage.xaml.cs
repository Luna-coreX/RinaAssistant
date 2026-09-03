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
    public async Task<int> OpenFirstPageAsync()
    {
        var got = await Ask(Methods.PluginsList);
        if (got?["items"] is not JsonArray items) return 0;

        var wasEnabled = items.OfType<JsonObject>()
            .Where(p => p["enabled"]?.GetValue<bool>() == true)
            .Select(p => p["plugin_id"]?.GetValue<string>() ?? "")
            .ToHashSet();

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
            var now = await Ask(Methods.PluginsList);
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

    private async Task LoadAsync()
    {
        var got = await Ask(Methods.PluginsList);
        if (got?["items"] is not JsonArray items) return;

        Items.Children.Clear();
        foreach (var item in items.OfType<JsonObject>())
            Items.Children.Add(BuildRow(item));

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
        PageLegend.Text = _open.ToUpperInvariant();
        foreach (var element in elements.OfType<JsonObject>())
            PageBody.Children.Add(BuildElement(element));
    }

    /// <summary>
    /// Один элемент описания страницы.
    /// </summary>
    /// <remarks>
    /// Виды взяты из <c>plugins/page_spec.py</c>. Незнакомый вид не
    /// пропускается: плагин что-то сказал, и оболочка обязана это показать,
    /// даже если не знает как, — иначе часть страницы исчезнет без следа.
    /// </remarks>
    private FrameworkElement BuildElement(JsonObject element)
    {
        var kind = element["kind"]?.GetValue<string>() ?? "";
        var text = element["text"]?.GetValue<string>() ?? "";

        switch (kind)
        {
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

            default:
                return new TextBlock
                {
                    Text = $"[{kind}] {text}",
                    Style = (Style)FindResource("Text.Meta"),
                    TextWrapping = TextWrapping.Wrap,
                    ToolTip = S("оболочка не знает такого элемента страницы"),
                };
        }
    }

    private async Task ActAsync(string action)
    {
        var got = await Ask(Methods.PluginsAction, new JsonObject
        {
            ["plugin_id"] = _open,
            ["action"] = action,
        });
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
