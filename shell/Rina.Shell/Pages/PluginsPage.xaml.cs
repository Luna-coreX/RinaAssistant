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
        // Раздел плагина в колонке появляется и исчезает вместе с ним, а
        // не после перезапуска: человек включил заметки — он ждёт их слева.
        if (_link is not null) await _link.RefreshPluginSectionsAsync();
    }

    /// <summary>Показать страницу открытого плагина.</summary>
    private async Task ShowPageAsync()
    {
        Draw();
        // Ждём отрисовку, а не полагаемся на `Loaded`: сразу после этого
        // вызова считают элементы, и «ноль» означал бы не пустую страницу,
        // а то, что её ещё не спросили.
        if (_view is not null) await _view.ReloadAsync();
    }

    /// <summary>
    /// Показать страницу открытого плагина.
    /// </summary>
    /// <remarks>
    /// Рисует <see cref="PluginView"/> — тот же, что и в собственном
    /// разделе плагина. Своя копия рендерера была бы вторым местом, где
    /// схема версии 2 понимается по-своему.
    /// </remarks>
    private void Draw()
    {
        PageBody.Children.Clear();
        if (_open.Length == 0)
        {
            PageBox.Visibility = Visibility.Collapsed;
            return;
        }

        PageBox.Visibility = Visibility.Visible;
        // Имя, а не номер: «NOTES» — то, как плагин называется в файловой
        // системе, а человек знает его как «Заметки».
        PageLegend.Text = (_names.GetValueOrDefault(_open) ?? _open)
            .ToUpperInvariant();

        var view = new PluginView(_link, _open);
        view.Noted += text => Note.Text = text;
        PageBody.Children.Add(view);
        _view = view;
    }

    private PluginView? _view;

    /// <summary>Сколько элементов на открытой странице — для проверки.</summary>
    public int PageElementCount => _view?.ElementCount ?? 0;

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
